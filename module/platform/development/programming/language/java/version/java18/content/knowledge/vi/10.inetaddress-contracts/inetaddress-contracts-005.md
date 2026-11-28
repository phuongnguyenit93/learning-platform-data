# IP literal và hostname: các đường đi có thể không cần gọi resolver provider

> **Chương:** Hợp đồng `InetAddress` — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học làm rõ sự khác nhau giữa chuỗi địa chỉ IP literal và hostname, các API tạo `InetAddress` trực tiếp, và thời điểm resolver provider có thể được gọi. Các ví dụ cốt lõi chạy từ **Java 18**; API `InetAddress.ofLiteral` được giới thiệu từ **Java 22** sẽ được đánh dấu riêng.

Khi đọc mã Java có `InetAddress.getByName("...")`, nhiều người mặc định rằng mọi đầu vào đều được gửi tới DNS hoặc `InetAddressResolverProvider`. Điều đó không đúng. Chuỗi đầu vào có thể là **IP literal** đã biểu diễn địa chỉ; JDK có thể phân tích trực tiếp và tạo `InetAddress` mà không cần thực hiện hostname lookup. Một số API khác còn cho phép tạo địa chỉ từ byte hoặc lấy loopback mà không phân giải tên.

Phân biệt được các đường đi này giúp bạn hiểu vì sao provider tùy biến không nhìn thấy mọi lời gọi, viết kiểm thử resolver chính xác, và tránh dùng nhầm API phân tích IP như một cơ chế phân giải hostname.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **IP literal** (`192.0.2.10`, `2001:db8::10`) với **hostname** (`api.example.test`).
2. Giải thích vì sao `getByName` và `getAllByName` có thể xử lý literal mà không gọi resolver provider để tra cứu tên.
3. Chọn `getByAddress`, `getLoopbackAddress` hoặc `ofLiteral` khi muốn tạo/parse địa chỉ trực tiếp.
4. Phân biệt phân giải xuôi hostname với reverse lookup qua `getHostName` và `getCanonicalHostName`.
5. Nhận biết cache và các lớp networking phía trên có thể khiến số lần provider được gọi khác số lần API được gọi.
6. Thiết kế và kiểm thử `InetAddressResolverProvider` mà không giả định provider sẽ nhận mọi đầu vào.

## 2. IP literal khác hostname như thế nào?

| Loại đầu vào | Ví dụ | Ý nghĩa |
|---|---|---|
| IPv4 literal | `192.0.2.10` | Bản thân chuỗi đã biểu diễn địa chỉ IPv4 |
| IPv6 literal | `2001:db8::10` | Bản thân chuỗi đã biểu diễn địa chỉ IPv6 |
| Hostname | `api.example.test` | Tên cần được resolver chuyển thành một hoặc nhiều địa chỉ |
| Tên cục bộ | `localhost` | Vẫn là hostname; có thể được xử lý từ hosts hoặc resolver |

`192.0.2.0/24` và `2001:db8::/32` là các dải địa chỉ dành cho tài liệu. Chúng giúp minh họa cú pháp IP mà không chỉ tới một máy chủ Internet thật.

Một cách nhớ hữu ích:

- **IP literal:** “Đây là địa chỉ; hãy phân tích chuỗi này thành cấu trúc địa chỉ.”
- **Hostname:** “Đây là tên; hãy hỏi cơ chế phân giải tên để tìm địa chỉ.”

Hostname có thể được ánh xạ bởi tệp hosts, resolver hệ điều hành, DNS hoặc resolver tùy biến. Vì vậy, từ “hostname lookup” không đồng nghĩa với “chắc chắn có một gói DNS được gửi ra mạng”.

## 3. Những đường đi có thể bỏ qua forward resolver

### 3.1. `getByName` và `getAllByName` nhận IP literal

Hai phương thức quen thuộc có thể nhận cả hostname lẫn IP literal:

```java
InetAddress one = InetAddress.getByName("192.0.2.10");
InetAddress[] all = InetAddress.getAllByName("2001:db8::10");

System.out.println(one.getHostAddress()); // 192.0.2.10
System.out.println(all.length);           // 1
System.out.println(all[0].getHostAddress()); // 2001:db8::10
```

Khi chuỗi được nhận dạng là **IP literal hợp lệ**, JDK phân tích địa chỉ trực tiếp. Không cần tra cứu hostname nên resolver provider không phải xử lý một forward lookup cho đầu vào này. `getAllByName` trả mảng chứa một địa chỉ literal; nó không tìm thêm địa chỉ nào khác cho IP đó.

Ngược lại, khi đầu vào là `api.example.test`, Java cần phân giải tên nếu không có kết quả phù hợp trong cache. Khi đó resolver được chọn cho JVM có thể tham gia.

Điều này giải thích một tình huống thường gặp khi viết provider có log:

```text
getByName("192.0.2.10")        -> tạo địa chỉ từ literal, không có lookupByName
getByName("api.example.test")  -> có thể gọi lookupByName nếu cache không trả kết quả
```

Không thấy log `lookupByName` khi thử IP literal **không phải dấu hiệu provider bị lỗi**.

### 3.2. `getByAddress` tạo địa chỉ từ byte

Nếu chương trình đã có byte của địa chỉ, có thể tạo `InetAddress` mà không phân giải hostname:

```java
import java.net.InetAddress;

public class AddressFromBytes {
    public static void main(String[] args) throws Exception {
        byte[] ipv4 = {(byte) 192, 0, 2, 10};
        InetAddress address4 = InetAddress.getByAddress(ipv4);

        byte[] ipv6 = new byte[] {
                0x20, 0x01, 0x0d, (byte) 0xb8,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10
        };
        InetAddress address6 = InetAddress.getByAddress(ipv6);

        System.out.println(address4.getHostAddress()); // 192.0.2.10
        System.out.println(address6.getHostAddress()); // 2001:db8::10
    }
}
```

Hợp đồng của `getByAddress(byte[])`:

- Mảng 4 byte tạo địa chỉ IPv4.
- Mảng 16 byte tạo địa chỉ IPv6.
- Độ dài khác 4 hoặc 16 byte gây `UnknownHostException`.
- Không cần hostname lookup để tạo địa chỉ.

API còn có overload `getByAddress(String host, byte[] addr)`. Nó tạo địa chỉ từ byte và gắn chuỗi `host` làm tên liên quan tới đối tượng; chuỗi đó **không được phân giải hoặc xác minh** để chứng minh nó thật sự trỏ tới các byte đã truyền.

```java
byte[] ip = {(byte) 192, 0, 2, 10};
InetAddress address =
        InetAddress.getByAddress("api.example.test", ip);

System.out.println(address.getHostAddress()); // 192.0.2.10
System.out.println(address.getHostName());    // api.example.test
```

Đây là cách gắn nhãn tên cho đối tượng địa chỉ, không phải phép kiểm tra DNS. Không dùng overload này để khẳng định bản ghi của hostname đang trỏ tới IP đó.

### 3.3. `getLoopbackAddress` không cần hostname lookup

Khi cần địa chỉ loopback của máy cục bộ, dùng:

```java
InetAddress loopback = InetAddress.getLoopbackAddress();
System.out.println(loopback.getHostAddress());
System.out.println(loopback.isLoopbackAddress());
```

Phương thức trả địa chỉ loopback phù hợp, có thể là IPv4 hoặc IPv6 tùy môi trường/cấu hình. Nó không cần phân giải tên `localhost`.

Đừng nhầm:

| API | Mục đích | Có cần tra cứu hostname? |
|---|---|---|
| `InetAddress.getLoopbackAddress()` | Lấy địa chỉ loopback | Không |
| `InetAddress.getByName("localhost")` | Phân giải hostname `localhost` | Có thể đi qua resolver/cache |
| `InetAddress.getLocalHost()` | Lấy tên host cục bộ rồi phân giải địa chỉ tương ứng | Có thể cần hostname lookup |

`localhost` là một hostname, còn loopback là một loại địa chỉ. Trong ứng dụng chỉ cần bind vào loopback, `getLoopbackAddress()` diễn đạt mục đích rõ hơn.

Một trường hợp đặc biệt nữa: `getByName(null)`, `getByName("")`, `getAllByName(null)` và `getAllByName("")` trả địa chỉ loopback theo hợp đồng API. Đây không phải là bằng chứng hostname rỗng đã được phân giải. Nếu nghiệp vụ yêu cầu hostname bắt buộc, hãy kiểm tra `null`/chuỗi rỗng trước khi gọi API.

### 3.4. `InetAddress.ofLiteral` từ Java 22

Từ **Java 22**, `InetAddress.ofLiteral(String)` cung cấp API chuyên biệt để tạo địa chỉ từ chuỗi IP literal:

```java
import java.net.InetAddress;

public class ParseLiteral {
    public static void main(String[] args) {
        InetAddress address = InetAddress.ofLiteral("2001:db8::10");
        System.out.println(address.getHostAddress());
    }
}
```

`ofLiteral` chỉ nhận chuỗi địa chỉ IPv4/IPv6 literal. Nếu chuỗi không phải literal hợp lệ, API ném `IllegalArgumentException`; nó không dùng resolver để thử coi chuỗi đó có phải hostname hay không.

**Tương thích phiên bản:** không gọi `InetAddress.ofLiteral` trong mã cần biên dịch trên Java 18 hoặc Java 21. Với Java 18, lựa chọn có sẵn là `getByAddress(byte[])` nếu đầu vào của bạn đã ở dạng byte. Nếu đầu vào là chuỗi và yêu cầu bắt buộc chỉ chấp nhận IP literal, cần dùng parser/validator literal phù hợp với baseline Java 18 rồi tạo địa chỉ; đừng dùng `getByName` như một validator literal vì hostname hợp lệ cũng có thể phân giải thành công.

## 4. Khi nào resolver provider được gọi?

Java 18 bổ sung SPI `java.net.spi.InetAddressResolverProvider` (JEP 418). Provider tạo `InetAddressResolver`, với các điểm vào chính:

- `lookupByName(String, LookupPolicy)` phục vụ tra cứu xuôi hostname.
- `lookupByAddress(byte[])` phục vụ tra cứu ngược địa chỉ thành tên.

`lookupByName` được thiết kế để nhận **tên máy**, không phải chuỗi IP literal. Khi gọi API `InetAddress` với literal hợp lệ, JDK xử lý địa chỉ trước đường hostname lookup. Nếu gọi trực tiếp phương thức của resolver tùy biến với chuỗi IP, không nên kỳ vọng provider tự parse literal; hãy tuân theo hợp đồng SPI và chỉ truyền hostname.

Một cách phân loại thực tế:

| Thao tác | Có cần forward hostname lookup? | Khả năng provider tham gia |
|---|---|---|
| `getByName("api.example.test")`, cache miss | Có | Có, qua `lookupByName` |
| `getAllByName("api.example.test")`, cache miss | Có | Có, qua `lookupByName` |
| `getByName("192.0.2.10")` với literal hợp lệ | Không | Không cần gọi `lookupByName` |
| `getAllByName("2001:db8::10")` với literal hợp lệ | Không | Không cần gọi `lookupByName` |
| `getByAddress(byte[])` | Không | Không |
| `getLoopbackAddress()` | Không | Không |
| `getByName("api.example.test")`, cache hit | Không cần lookup mới | Provider có thể không được gọi ở lần gọi đó |
| `getHostName()` khi cần reverse lookup | Không phải forward lookup | Có thể gọi `lookupByAddress` |
| `getCanonicalHostName()` khi cần tìm tên ngược | Không phải forward lookup | Có thể gọi `lookupByAddress` |

Provider là thành phần của **cơ chế phân giải tên trong JVM**, không phải hook chặn mọi nơi tạo `InetAddress`. Nếu ứng dụng cần áp dụng chính sách cho cả hostname và IP literal (ví dụ từ chối một dải IP), hãy kiểm tra đầu vào ở tầng ứng dụng trước khi gọi API mạng.

### 4.1. Cache cũng làm số lần provider được gọi ít hơn số lần gọi API

`InetAddress` cache cả kết quả lookup thành công và thất bại. Khi hostname đã có kết quả cache còn hiệu lực, một lời gọi `getByName` hoặc `getAllByName` có thể được trả lời mà không gọi provider lần nữa.

Ví dụ:

```text
Lần 1: getByName("api.example.test") -> cache miss -> resolver/provider được gọi
Lần 2: getByName("api.example.test") -> cache hit  -> có thể không gọi provider
Lần 3: getAllByName("api.example.test") -> cache hit -> có thể không gọi provider
```

Vì vậy, số dòng log trong `lookupByName` không bằng số lần ứng dụng gọi `InetAddress`. Nếu muốn kiểm thử provider, hãy dùng hostname thử nghiệm riêng, kiểm soát cache/security properties và chạy JVM mới giữa các kịch bản. Đừng dùng DNS công cộng làm fixture có kết quả cố định.

## 5. Forward lookup và reverse lookup là hai đường đi khác nhau

Các phương thức trả chuỗi hostname từ một `InetAddress` có hành vi riêng:

| Phương thức | Ý nghĩa | Có thể phát sinh reverse lookup? |
|---|---|---|
| `getHostAddress()` | Trả chuỗi địa chỉ IP của đối tượng | Không |
| `getHostName()` | Trả tên host đã gắn/ghi nhớ; nếu chưa có, có thể thử tìm tên theo địa chỉ | Có |
| `getCanonicalHostName()` | Thử tìm tên canonical cho địa chỉ | Có |

Ví dụ:

```java
InetAddress literal = InetAddress.getByName("192.0.2.10");
System.out.println(literal.getHostAddress()); // Không cần reverse lookup

// Hai lời gọi sau có thể kích hoạt lookup ngược tùy trạng thái tên đã biết:
System.out.println(literal.getHostName());
System.out.println(literal.getCanonicalHostName());
```

Nếu `InetAddress` được tạo từ `getByAddress("api.example.test", bytes)`, `getHostName()` có thể trả tên đã gắn mà không cần hỏi resolver. Điều đó vẫn không xác minh tên này có bản ghi DNS phù hợp. `getCanonicalHostName()` có thể thực hiện lookup ngược theo hợp đồng của API.

Không dùng reverse DNS làm bằng chứng xác thực danh tính máy chủ. Với HTTPS, xác thực endpoint dựa trên hostname của URL và chứng chỉ TLS hợp lệ (SAN/chuỗi tin cậy), không dựa vào tên reverse trả về từ một IP.

## 6. Đừng nhầm “không gọi resolver” với “không có hoạt động mạng”

Việc phân tích IP literal chỉ tránh **hostname lookup** ở lớp `InetAddress`. Nó không chứng minh địa chỉ có thể truy cập, cũng không loại bỏ các bước mạng khác:

1. Tạo `InetAddress` từ `192.0.2.10` không gửi gói tới địa chỉ đó.
2. Mở `Socket` tới IP và cổng vẫn thực hiện kết nối TCP.
3. Kết nối HTTPS vẫn cần TLS handshake và xác thực chứng chỉ.
4. Gửi HTTP vẫn cần server xử lý request và trả phản hồi.

Tương tự, `InetSocketAddress` có nhiều cách tạo:

```java
InetAddress ip = InetAddress.getByName("192.0.2.10");
InetSocketAddress numericEndpoint = new InetSocketAddress(ip, 443);

InetSocketAddress unresolved =
        InetSocketAddress.createUnresolved("api.example.test", 443);

System.out.println(numericEndpoint.isUnresolved()); // false
System.out.println(unresolved.isUnresolved());      // true
```

`createUnresolved` tạo endpoint giữ hostname mà **chưa phân giải** tại thời điểm tạo. Trạng thái unresolved chỉ giữ lại tên; nó không tự tìm IP và không tự làm cho kết nối hostname hoạt động.

Với API socket chuẩn, endpoint unresolved **không tự được phân giải khi connect**: `Socket.connect` ném `UnknownHostException` nếu `InetSocketAddress` chưa được resolve; `SocketChannel.connect` ném `UnresolvedAddressException`. Nếu muốn dùng socket trực tiếp, ứng dụng phải phân giải hostname trước rồi tạo endpoint với `InetAddress`. Một client cấp cao có thể tự quản lý bước phân giải theo hợp đồng riêng.

Khi dùng HTTP client hoặc proxy, đường đi thực tế còn phụ thuộc client và proxy. Proxy có thể tự phân giải hostname đích ở phía proxy; do đó không nên suy luận rằng mọi lần truy cập URL có IP/hostname đều tạo cùng một chuỗi resolver cục bộ. Bài này mô tả đường đi của các API `InetAddress` và socket trực tiếp.

## 7. Ví dụ quan sát đường đi với resolver tùy biến

Khi kiểm thử `InetAddressResolverProvider`, hãy tách các loại đầu vào để quan sát:

| Đầu vào | Điều muốn kiểm chứng |
|---|---|
| `resolver-test.example.test` | Cache miss của hostname có kích hoạt `lookupByName` không? |
| `192.0.2.10` | Literal có đi qua `lookupByName` không? |
| `2001:db8::10` | IPv6 literal có đi qua `lookupByName` không? |
| `localhost` | Resolver/provider xử lý tên cục bộ ra sao trong môi trường thử nghiệm? |
| Địa chỉ được tạo bằng `getByAddress` rồi gọi `getCanonicalHostName()` | Khi nào `lookupByAddress` được gọi? |

Một provider ghi log để thử nghiệm có thể có dạng khái niệm:

```java
public Stream<InetAddress> lookupByName(
        String host, LookupPolicy policy) throws UnknownHostException {
    System.out.println("forward lookup: " + host);
    return builtin.lookupByName(host, policy);
}

public String lookupByAddress(byte[] address)
        throws UnknownHostException {
    System.out.println("reverse lookup requested");
    return builtin.lookupByAddress(address);
}
```

Đây chỉ là phần thân minh họa bên trong một `InetAddressResolver`; trong mã thật cần lấy `builtin` từ `Configuration.builtinResolver()` khi provider được khởi tạo và triển khai đầy đủ SPI/service registration. Không gọi `InetAddress.getByName(host)` bên trong `lookupByName` để fallback, vì nó có thể quay lại chính resolver tùy biến và gây đệ quy. Dùng resolver tích hợp được cung cấp trực tiếp.

**Kết quả mong đợi cần hiểu đúng:**

- Gọi với hostname chưa cache: log forward lookup có thể xuất hiện.
- Gọi với literal hợp lệ: không cần log forward lookup.
- Gọi lại hostname khi cache còn hiệu lực: không nhất thiết có log mới.
- Gọi phương thức reverse khi tên chưa được lưu: log reverse lookup có thể xuất hiện.

Không dùng số log làm cam kết về số truy vấn DNS ra mạng: resolver tích hợp có thể dùng hosts, cache hệ điều hành hoặc cơ chế tên khác.

## 8. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
|---|---|
| Mọi `getByName` đều gọi DNS | Literal hợp lệ có thể được parse trực tiếp; hostname có thể dùng cache, hosts hoặc resolver khác DNS. |
| `getAllByName("192.0.2.10")` liệt kê mọi IP của máy | Nó trả mảng một địa chỉ tương ứng literal, không liệt kê interface hay DNS record. |
| Provider phải nhìn thấy mọi lần tạo `InetAddress` | Provider chỉ tham gia các đường lookup mà SPI quản lý; `getByAddress`, loopback và literal fast path không cần forward lookup. |
| Không thấy log provider nghĩa là service registration sai | Có thể đầu vào là literal hoặc kết quả hostname đã cache. |
| `getByAddress("api.example.test", bytes)` xác minh hostname | Nó chỉ gắn tên vào đối tượng; không kiểm tra DNS. |
| `getHostAddress()` gọi reverse DNS | Nó chỉ định dạng địa chỉ IP. |
| `getCanonicalHostName()` là cách xác minh server | Reverse lookup không thay thế TLS hostname verification. |
| Tạo `InetAddress` từ literal nghĩa là IP truy cập được | Đó chỉ là đối tượng địa chỉ; kết nối TCP/TLS/HTTP là các bước khác. |
| `createUnresolved` làm socket không cần DNS | Nó chỉ trì hoãn lookup đến khi thao tác kết nối cần địa chỉ. |

Chỉ các literal đúng cú pháp mới đi theo nhánh parse IP. Không dùng chuỗi số bất thường hoặc sai định dạng làm cách biểu diễn IP; nếu cần chấp nhận literal, hãy xác thực theo parser literal thay vì đoán rằng mọi chuỗi trông giống số đều được nhận diện như IP.

## 9. Hướng dẫn lựa chọn API

| Nhu cầu | API phù hợp | Ghi chú |
|---|---|---|
| Phân giải hostname | `InetAddress.getByName(host)` hoặc `getAllByName(host)` | Resolver/provider có thể tham gia nếu cần lookup và cache không trả kết quả. |
| Parse IP literal từ chuỗi trên Java 22+ | `InetAddress.ofLiteral(text)` | Từ chối hostname, không phân giải tên. |
| Tạo địa chỉ từ byte trên Java 18+ | `InetAddress.getByAddress(bytes)` | Không lookup; độ dài phải 4 hoặc 16 byte. |
| Gắn nhãn hostname có sẵn vào địa chỉ byte | `InetAddress.getByAddress(host, bytes)` | Không xác minh mối liên hệ giữa hostname và IP. |
| Lấy loopback | `InetAddress.getLoopbackAddress()` | Không cần phân giải `localhost`. |
| Tạo endpoint socket từ IP đã có | `new InetSocketAddress(inetAddress, port)` | Không cần forward lookup hostname. |
| Giữ hostname chưa phân giải trong endpoint | `InetSocketAddress.createUnresolved(host, port)` | Lookup có thể xảy ra sau khi bắt đầu kết nối. |

Nếu yêu cầu nghiệp vụ là “đầu vào phải là IP literal”, hãy dùng parser literal hoặc xác thực cú pháp trước khi tạo địa chỉ. Nếu yêu cầu là “đầu vào có thể là hostname”, dùng `getByName`/`getAllByName` và xử lý `UnknownHostException`. Đừng trộn hai hợp đồng vào cùng một phép kiểm tra.

## 10. Bài tập tự kiểm tra

1. Vì sao `InetAddress.getByName("192.0.2.10")` có thể không gọi `InetAddressResolver.lookupByName`?
2. `getAllByName("192.0.2.10")` trả về mảng có ý nghĩa gì? Vì sao nó không trả mọi IP của host?
3. So sánh `getByAddress(byte[])` và `getByAddress(host, byte[])`. Overload thứ hai có xác minh hostname không?
4. Vì sao `getLoopbackAddress()` khác `getByName("localhost")` về đường đi?
5. Provider đã log một lần cho hostname. Vì sao các lần gọi tiếp theo có thể không log nữa?
6. `getHostAddress()`, `getHostName()` và `getCanonicalHostName()` khác nhau như thế nào về khả năng phát sinh reverse lookup?
7. Vì sao `InetAddress.ofLiteral` không thể dùng trong mã cần biên dịch trên Java 18?
8. `InetSocketAddress.createUnresolved` có làm cho một kết nối tới hostname không cần resolver không?

**Tiêu chí hoàn thành:** Bạn có thể xác định một đầu vào là IP literal hay hostname, dự đoán được khi nào forward/reverse resolver có thể được gọi, chọn API phù hợp với phiên bản JDK và giải thích rõ vì sao tạo địa chỉ không đồng nghĩa với kết nối được tới dịch vụ.

## 11. Tài liệu chuẩn

- [InetAddress — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): `getByName`, `getAllByName`, `getByAddress`, `getLoopbackAddress` và `ofLiteral`.
- [InetAddress — Java SE 18 API](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/net/InetAddress.html): các API có sẵn trong baseline Java 18.
- [InetAddressResolver — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolver.html): forward và reverse lookup qua resolver SPI.
- [InetAddressResolverProvider — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html): cơ chế cung cấp resolver tùy biến.
- [InetSocketAddress — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetSocketAddress.html): endpoint đã phân giải và `createUnresolved`.
- [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): resolver provider được bổ sung trong Java 18.
