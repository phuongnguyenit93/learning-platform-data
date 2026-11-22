# 18.5. GSSManager, GSSName, GSSCredential và GSSContext

## Mục tiêu và bối cảnh

Sau bài này, bạn có thể giải thích vai trò của bốn đối tượng cốt lõi trong Java GSS-API, tạo tên và ngữ cảnh bảo mật đúng phía client/server, hiểu vòng trao đổi token, kiểm tra thuộc tính bảo mật sau bắt tay, và nhận biết các lỗi Kerberos thường gặp.

**GSS-API (Generic Security Services API)** cung cấp giao diện chung cho các cơ chế xác thực và bảo vệ thông điệp, phổ biến nhất là Kerberos V5. Trong Java 17+, API chuẩn ở package `org.ietf.jgss` thuộc module `java.security.jgss`. Ứng dụng có thể dùng GSS-API để xác thực hai phía, kiểm tra tính toàn vẹn và (nếu cơ chế/ngữ cảnh hỗ trợ) bảo mật nội dung thông điệp.

GSS-API **không tự mở kết nối hay truyền token**: chương trình hoặc giao thức như HTTP/SASL phải chuyển token giữa hai đầu. GSS-API cũng không thay thế bước phân quyền nghiệp vụ sau khi biết người dùng là ai.

## 1. Bản đồ bốn đối tượng

| Thành phần | Trách nhiệm chính | Bạn thường làm gì? |
| --- | --- | --- |
| `GSSManager` | Factory, biết các cơ chế (mechanism) GSS khả dụng | `getInstance()`, `getMechs()`, `createName(...)`, `createCredential(...)`, `createContext(...)` |
| `GSSName` | Biểu diễn danh tính principal theo một kiểu tên, có thể ánh xạ sang tên riêng của cơ chế | Xác định dịch vụ đích `HTTP@api.example.com`; chuẩn hóa bằng `canonicalize(...)` khi cần |
| `GSSCredential` | Tay cầm đối với thông tin xác thực đã có của principal, dành cho khởi tạo hoặc chấp nhận context | Lấy credential của client hoặc service; kiểm tra thời hạn, cơ chế, vai trò |
| `GSSContext` | Phiên bảo mật giữa hai peer, ban đầu chưa được thiết lập | Trao đổi `initSecContext`/`acceptSecContext`; sau đó xác thực danh tính, `wrap`/`unwrap`, `getMIC`/`verifyMIC` |

Luồng phụ thuộc điển hình:

```text
             GSSManager
             ├── tạo GSSName: tên peer/service
             ├── lấy GSSCredential: quyền của chính tiến trình
             └── tạo GSSContext (mỗi kết nối/phiên xác thực)
                         │
       initiator.initSecContext(...) ↔ acceptor.acceptSecContext(...)
                         │
                 isEstablished() == true
                         │
           getSrcName/getTargName, wrap/unwrap, MIC
```

Cần tách bạch ba câu hỏi: **mình là ai** (credential), **mình đang nói chuyện với ai** (peer name), và **hai phía đã xác thực/đồng ý thuộc tính bảo vệ nào** (context). `GSSManager` liên kết chúng.

## 2. GSSManager: điểm vào và lựa chọn cơ chế

Tạo factory mặc định bằng `GSSManager.getInstance()`. Factory có thể liệt kê các cơ chế hiện có qua `getMechs()`, loại tên qua `getNamesForMech(Oid)` và cơ chế tương thích một loại tên qua `getMechsForName(Oid)`.

**OID (Object Identifier)** xác định một cơ chế bằng số, không phải bằng tên lớp Java:

- Kerberos V5 GSS-API: `1.2.840.113554.1.2.2`.
- SPNEGO (cơ chế thương lượng GSS, nếu provider hỗ trợ): `1.3.6.1.5.5.2`. SPNEGO không đồng nghĩa Kerberos thuần; nó có thể thương lượng cơ chế bên trong.
- Tham số `mech = null` trong `createContext` yêu cầu cơ chế mặc định; **không** có nghĩa luôn tự thương lượng SPNEGO.

Ví dụ Java chạy độc lập, không cần KDC, keytab hay ticket vì chỉ kiểm tra cơ chế:

**Tệp `GssCapabilities.java`**

```java
import java.util.Arrays;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.Oid;

public class GssCapabilities {
    public static void main(String[] args) throws Exception {
        GSSManager manager = GSSManager.getInstance();
        Oid kerberos = new Oid("1.2.840.113554.1.2.2");

        System.out.println("Kerberos OID: " + kerberos);
        System.out.println("Kerberos supported: "
                + Arrays.asList(manager.getMechs()).contains(kerberos));
    }
}
```

Chạy trên JDK Java SE 17+ có triển khai GSS-API chuẩn:

```bash
javac GssCapabilities.java
java GssCapabilities
```

Stdout dự kiến:

```text
Kerberos OID: 1.2.840.113554.1.2.2
Kerberos supported: true
```

Việc có OID Kerberos trong danh sách **không** chứng minh máy đã có cấu hình realm, vé Kerberos hay tài khoản để đăng nhập. Nó chỉ xác nhận cơ chế có sẵn trong triển khai JDK.

## 3. GSSName: tên logic, kiểu tên và tên theo cơ chế

`GSSName` không phải chuỗi bất kỳ. Khi gọi `manager.createName(value, nameType)`, tham số `nameType` nói cách diễn giải `value`:

| Kiểu tên | Trường hợp | Điểm cần nhớ |
| --- | --- | --- |
| `GSSName.NT_HOSTBASED_SERVICE` | `"HTTP@api.example.com"` | Dạng GSS host-based là `service@host`, **khác** cách viết principal Kerberos `HTTP/api.example.com@EXAMPLE.COM` |
| `GSSName.NT_USER_NAME` | Tên người dùng ở dạng mà provider chấp nhận | Không suy đoán realm/quyền từ một chuỗi hiển thị |
| `GSSName.NT_EXPORT_NAME` | Nhập tên ở định dạng binary đã export | Dùng cùng định dạng export chuẩn; không coi bytes là UTF-8 tự do |

```java
GSSManager manager = GSSManager.getInstance();
Oid kerberos = new Oid("1.2.840.113554.1.2.2");

// Cần cấu hình Kerberos/realm thích hợp ngay cả khi mới tạo tên
// ở một số provider JDK:
GSSName service = manager.createName(
        "HTTP@api.example.com",
        GSSName.NT_HOSTBASED_SERVICE);

// Chuyển về mechanism name (MN) cho Kerberos khi cần:
GSSName kerberosService = service.canonicalize(kerberos);
```

Đoạn trên **là minh họa tích hợp**, không phải chương trình độc lập: một số triển khai sẽ cố phân giải realm ngay tại `createName` và ném `GSSException` nếu chưa cấu hình Kerberos, dù chưa hề gửi token. Không giả định việc tạo tên chắc chắn hoạt động trên máy trống.

`canonicalize(mechOid)` tạo representation riêng của cơ chế; `isMN()` cho biết đối tượng có phải mechanism name hay không. `GSSName.export()` có thể xuất một MN thành bytes để nhập lại bằng `NT_EXPORT_NAME`; không dùng `getBytes()` trên `toString()` để thay thế. Khi so khớp danh tính bảo mật, dùng quy tắc so sánh tên theo cơ chế và chính sách phân quyền rõ ràng; đừng chỉ cắt chuỗi trước/dưới dấu `@`.

**Cẩn thận với principal dịch vụ:** client có thể tạo tên host-based `HTTP@api.example.com`, trong khi phía Kerberos thực tế có thể cần service principal `HTTP/api.example.com@EXAMPLE.COM` và keytab tương ứng. Việc ánh xạ phụ thuộc realm, DNS và cấu hình nhà cung cấp; tên sai sẽ khiến xác thực thất bại dù client có ticket.

## 4. GSSCredential: danh tính và quyền sử dụng

`GSSCredential` giữ handle tới credential của một principal đã được môi trường cung cấp. `GSSManager.createCredential(...)` **không phải thao tác đăng nhập bằng mật khẩu**: Kerberos ticket hoặc khóa chấp nhận (ví dụ keytab/`Subject` có `KerberosKey`) cần được cung cấp qua JAAS/cơ chế mặc định trước hoặc trong quá trình provider lấy credential.

Ba cờ vai trò:

- `GSSCredential.INITIATE_ONLY`: dùng mở context với peer khác (thường là client).
- `GSSCredential.ACCEPT_ONLY`: dùng chấp nhận context từ client (thường là service).
- `GSSCredential.INITIATE_AND_ACCEPT`: dùng cho cả hai nếu cơ chế và credential thực tế hỗ trợ.

Ví dụ minh họa lấy credential chấp nhận phía server sau khi môi trường Kerberos và JAAS đã chuẩn bị:

```java
GSSManager manager = GSSManager.getInstance();
Oid kerberos = new Oid("1.2.840.113554.1.2.2");
GSSName service = manager.createName(
        "HTTP@api.example.com",
        GSSName.NT_HOSTBASED_SERVICE);

GSSCredential acceptorCred = manager.createCredential(
        service,
        GSSCredential.DEFAULT_LIFETIME,
        kerberos,
        GSSCredential.ACCEPT_ONLY);
try {
    // Tạo context và nhận token trong phiên xác thực...
    System.out.println(acceptorCred.getRemainingLifetime());
} finally {
    acceptorCred.dispose();
}
```

Đây là fragment Java, không có `main` và **không thể chạy thành công nếu thiếu service credential tương ứng**. Đối với client, có thể chỉ định credential đã lấy qua `INITIATE_ONLY` hoặc truyền `null` tại `GSSManager.createContext(peer, mech, null, lifetime)` để provider dùng danh tính khởi tạo mặc định trong ngữ cảnh hiện tại.

Có thể kiểm tra `getName()`, `getMechs()`, `getUsage(...)`, `getRemainingLifetime()`. Tuổi thọ yêu cầu là một **yêu cầu**, không phải cam kết; kiểm tra giá trị thực. `dispose()` khi credential không còn được dùng, tránh giữ handle/tài liệu xác thực lâu không cần thiết. Không ghi credential, keytab, ticket hoặc token vào log.

## 5. GSSContext: trạng thái phiên và hai phía

`GSSContext` biểu diễn một phiên bảo mật với peer, **chưa xác thực ngay tại thời điểm tạo**. Hai cách tạo phải phân biệt:

- **Initiator/client:** `createContext(GSSName peer, Oid mech, GSSCredential myCred, int lifetime)`. Đưa tên peer đích và cơ chế; credential `null` nghĩa là dùng danh tính mặc định của client nếu sẵn có.
- **Acceptor/server:** `createContext(GSSCredential myCred)`. Đưa credential nhận của server; ngữ cảnh sẽ xử lý token mà initiator gửi tới.

Trước lần đầu `initSecContext`, initiator có thể yêu cầu:

| Lệnh | Ý nghĩa | Sau khi thiết lập cần kiểm tra |
| --- | --- | --- |
| `requestMutualAuth(true)` | Client muốn xác thực cả server | `getMutualAuthState()` |
| `requestInteg(true)` | Muốn bảo vệ toàn vẹn | `getIntegState()` |
| `requestConf(true)` | Muốn cho phép bảo mật nội dung | `getConfState()` |
| `requestReplayDet(true)` | Muốn cơ chế phát hiện phát lại thông điệp | `getReplayDetState()` |
| `requestSequenceDet(true)` | Muốn kiểm tra thứ tự thông điệp | `getSequenceDetState()` |
| `requestCredDeleg(true)` | Muốn ủy quyền credential cho server | `getCredDelegState()`; chỉ bật khi thực sự cần |

Các lệnh `request...` là đề nghị, không chứng minh tính năng đã được kích hoạt. Provider và peer có thể quyết định thuộc tính cuối cùng. Nếu ứng dụng yêu cầu mutual authentication/integrity/confidentiality, hãy **từ chối phiên** khi thuộc tính thực tế sau thiết lập không đáp ứng chính sách. Không yêu cầu credential delegation theo mặc định vì điều này mở rộng đặc quyền của bên nhận.

`setChannelBinding(ChannelBinding)` (nếu giao thức hỗ trợ) được gọi **trước bắt tay ở cả hai phía** để ràng buộc xác thực với thông tin kênh bên dưới và giảm nguy cơ chuyển tiếp token giữa kênh. Hai phía phải dùng dữ liệu binding tương thích; cấu hình sai có thể khiến xác thực thất bại.

Sau khi `isEstablished() == true`, context cung cấp `getSrcName()` (initiator), `getTargName()` (acceptor), `getMech()` và trạng thái dịch vụ bảo mật. **Xác thực danh tính không tự quyết định quyền truy cập:** server phải tự kiểm tra principal vừa được xác thực với ACL/role/tenant/endpoint phù hợp.

## 6. Minh họa tạo client và server context bằng Java 17+

Tệp dưới đây **biên dịch được** và thể hiện bốn đối tượng. Các phương thức chỉ được gọi trong ứng dụng đã cấu hình Kerberos và có cơ chế vận chuyển token; chúng không chứa `main` hay giả vờ xác thực thành công khi thiếu KDC/ticket/keytab.

**Tệp `GssSetup.java`**

```java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSCredential;
import org.ietf.jgss.GSSException;
import org.ietf.jgss.GSSManager;
import org.ietf.jgss.GSSName;
import org.ietf.jgss.Oid;

public final class GssSetup {
    private GssSetup() {}

    private static Oid kerberos() throws GSSException {
        return new Oid("1.2.840.113554.1.2.2");
    }

    public static GSSContext newClientContext(String serviceHost)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName server = manager.createName(
                "HTTP@" + serviceHost, GSSName.NT_HOSTBASED_SERVICE);

        // null: dùng initiator credential mặc định trong môi trường hiện tại.
        GSSContext context = manager.createContext(
                server, kerberos(), null, GSSContext.DEFAULT_LIFETIME);

        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        return context;
    }

    public static GSSCredential newServerCredential(String serviceHost)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName service = manager.createName(
                "HTTP@" + serviceHost, GSSName.NT_HOSTBASED_SERVICE);
        return manager.createCredential(
                service,
                GSSCredential.DEFAULT_LIFETIME,
                kerberos(),
                GSSCredential.ACCEPT_ONLY);
    }

    public static GSSContext newServerContext(GSSCredential credential)
            throws GSSException {
        return GSSManager.getInstance().createContext(credential);
    }
}
```

Kiểm tra cú pháp:

```bash
javac GssSetup.java
```

Ví dụ luồng sở hữu tài nguyên ở service: chuẩn bị `GSSCredential` trong `Subject` đã đăng nhập, tạo một `GSSContext` **riêng cho mỗi phiên**, dùng context cho vòng trao đổi token và thao tác thông điệp, rồi `context.dispose()`. Chỉ `credential.dispose()` sau khi các phiên dùng credential đó đã kết thúc; không hủy credential còn đang dùng chung. Không chia sẻ một `GSSContext` cho nhiều client hoặc các luồng xử lý độc lập.

## 7. Thiết lập context là vòng trao đổi token, không phải một lời gọi

Mô hình hai phía:

```text
Client / initiator                          Server / acceptor
  initSecContext(input ban đầu rỗng)
         │ ---- token A ------------------> acceptSecContext(token A)
         │ <--------------- token B ------ (nếu có)
  initSecContext(token B)
         │ ---- token C (nếu có) --------> acceptSecContext(token C)
         · · · tới khi hai phía đều hoàn tất ngữ cảnh · · ·
```

Quy tắc triển khai:

1. Client gọi `initSecContext(byte[] inputBuf, int offset, int len)` lần đầu, thông thường với token đầu vào dài 0. Nếu có output token (khác `null`), **gửi sang server**, kể cả khi `isEstablished()` của client đã là `true`.
2. Server nhận nguyên vẹn một token, gọi `acceptSecContext(...)`, gửi output token nếu có; lặp lại nếu context còn cần token tiếp.
3. Client xử lý token mới qua `initSecContext(...)`; hai phía kiểm tra trạng thái của **context riêng**. Số lượt trao đổi phụ thuộc cơ chế, tùy chọn mutual auth và môi trường.
4. Ứng dụng tự định nghĩa cách chuyển bytes: ví dụ length-prefix trên TCP hoặc trường token của giao thức. Không chuyển nhị phân bằng `new String(token)` rồi khôi phục theo charset; nếu giao thức văn bản thì mã hóa Base64 đúng chuẩn.
5. `null` output nghĩa là không có token cần gửi trong lượt đó. Không tự gửi token giả/chuỗi rỗng thay cho `null`. Không mặc định cả hai phía luôn hoàn tất trong đúng một round-trip.

Ví dụ khung xử lý token trên client. `TokenChannel` là adapter **phải được ứng dụng hiện thực** (đóng gói, giới hạn kích thước, nhận/gửi đầy đủ và xử lý timeout), vì GSS-API không cung cấp socket:

```java
import java.io.IOException;
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSException;

public final class GssTokenFlow {
    private GssTokenFlow() {}

    public interface TokenChannel {
        void send(byte[] token) throws IOException;
        byte[] receive() throws IOException;
    }

    public static void initiate(GSSContext context, TokenChannel channel)
            throws GSSException, IOException {
        byte[] incoming = new byte[0];

        while (!context.isEstablished()) {
            byte[] outgoing = context.initSecContext(
                    incoming, 0, incoming.length);

            // Một phía có thể isEstablished() == true nhưng vẫn cần
            // gửi token cuối cùng cho phía kia.
            if (outgoing != null) {
                channel.send(outgoing);
            }
            if (!context.isEstablished()) {
                incoming = channel.receive(); // trả về đúng một token đầy đủ
                if (incoming == null) {
                    throw new IOException("Peer closed during GSS handshake");
                }
            }
        }
    }

    public static void accept(GSSContext context, TokenChannel channel)
            throws GSSException, IOException {
        while (!context.isEstablished()) {
            byte[] incoming = channel.receive();
            if (incoming == null) {
                throw new IOException("Peer closed during GSS handshake");
            }
            byte[] outgoing = context.acceptSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                channel.send(outgoing);
            }
        }
    }
}
```

`GssTokenFlow.java` biên dịch được bằng `javac GssTokenFlow.java` nhưng **không tự chạy**: còn cần hiện thực `TokenChannel`, credential, giao thức kết thúc handshake và chính sách timeout. Đây là khung tuần tự cho một phiên; khi tích hợp HTTP Negotiate, SASL hoặc giao thức có nhiều trạng thái, phải tuân thủ quy tắc điều khiển token của giao thức đó. Đừng giả định việc một đầu có `isEstablished() == true` chính là xác nhận ứng dụng ở đầu kia đã xử lý hết token cuối.

Sau khi hoàn tất, có thể kiểm tra:

```java
if (!context.isEstablished()
        || !context.getMutualAuthState()
        || !context.getIntegState()) {
    throw new SecurityException("GSS context does not meet policy");
}
GSSName authenticatedClient = context.getSrcName(); // ở phía server
GSSName authenticatedServer = context.getTargName(); // ở phía client
// Tiếp theo phải kiểm tra principal với chính sách ứng dụng.
```

Mã trên là fragment chạy **sau** handshake; nếu chính sách của ứng dụng bắt buộc confidentiality, kiểm tra thêm `getConfState()` và trạng thái privacy thực tế của từng thông điệp.

## 8. Bảo vệ dữ liệu sau khi xác thực

Khi context đã sẵn sàng (thông thường sau `isEstablished()`; API còn có `isProtReady()` cho một số cơ chế), các API xử lý dữ liệu gồm:

- `wrap(data, off, len, MessageProp)`: tạo token bảo vệ toàn vẹn và có thể mã hóa nội dung. `new MessageProp(0, true)` yêu cầu QOP mặc định và privacy; sau `wrap` phải xem lại `getPrivacy()` vì giá trị thực tế có thể khác yêu cầu.
- `unwrap(token, off, len, MessageProp)`: giải mã/xác minh token do context ở peer tạo và trả dữ liệu. Đọc trạng thái trong `MessageProp` để biết cách xử lý.
- `getMIC(data, ..., MessageProp)` tạo mã kiểm tra toàn vẹn (**không** mã hóa hay gói kèm plaintext); `verifyMIC(mic, ..., data, ..., MessageProp)` xác minh ở peer.
- `getWrapSizeLimit(...)` giúp ước lượng kích thước tối đa dữ liệu có thể đưa vào `wrap` với giới hạn token đầu ra của giao thức.

Minh họa hai context **đã được thiết lập và tương ứng với cùng một phiên**:

```java
import java.nio.charset.StandardCharsets;
import org.ietf.jgss.MessageProp;

// clientContext và serverContext là hai context ĐÃ XÁC THỰC.
// Đây là fragment, không phải chương trình chạy độc lập.
byte[] data = "Hello GSS".getBytes(StandardCharsets.UTF_8);

MessageProp outbound = new MessageProp(0, true);
byte[] protectedToken = clientContext.wrap(
        data, 0, data.length, outbound);
if (!outbound.getPrivacy()) {
    throw new SecurityException("Confidentiality was required");
}

// Chuyển protectedToken nguyên vẹn qua TokenChannel/protocol...
MessageProp inbound = new MessageProp(0, false);
byte[] plain = serverContext.unwrap(
        protectedToken, 0, protectedToken.length, inbound);
String received = new String(plain, StandardCharsets.UTF_8);
```

Với trường hợp chỉ cần MIC, tạo MIC trên một context và xác minh với **chính dữ liệu** ở context bên kia:

```java
byte[] mic = clientContext.getMIC(
        data, 0, data.length, new MessageProp(0, false));
serverContext.verifyMIC(
        mic, 0, mic.length,
        data, 0, data.length,
        new MessageProp(0, false));
```

Kết quả không phải chuỗi cố định để đưa vào stdout: token/MIC phụ thuộc khóa phiên, cơ chế và trạng thái context. Dữ liệu bị thay đổi hoặc token không hợp lệ phải được xử lý như lỗi xác minh, không âm thầm tiếp tục.

**GSS bảo vệ từng token theo các thuộc tính context**, còn bảo vệ toàn bộ kênh (metadata, framing, timeout, yêu cầu giao thức, những endpoint không dùng GSS) là quyết định kiến trúc riêng. Nếu dùng TLS cùng GSS, đừng tự suy rằng GSS đã ràng buộc với TLS khi chưa cấu hình channel binding tương thích.

## 9. Điều kiện môi trường thực tế và JAAS

Muốn chạy xác thực Kerberos thật, thường cần các điều kiện sau:

1. **KDC/realm và cấu hình máy:** `krb5.conf`/`krb5.ini` hoặc thuộc tính JVM tương ứng, realm có thể phân giải và đồng hồ máy không lệch vượt giới hạn Kerberos.
2. **Danh tính đích:** service principal phù hợp với host/canonicalization. Ví dụ service `HTTP/api.example.com@EXAMPLE.COM`; DNS, alias và principal phải nhất quán với chính sách triển khai.
3. **Client credential:** ticket từ quá trình login/SSO, cache hoặc `Subject` đã được JAAS cung cấp, tùy cách triển khai.
4. **Server credential:** khóa phục vụ principal phù hợp trong keytab hoặc credential an toàn khác. Tiến trình server phải có quyền đọc nguồn credential, nhưng keytab không được đưa vào Git hoặc log.
5. **Giao thức trao đổi:** vận chuyển token có framing, giới hạn kích thước, timeout, xử lý lỗi và kiểm tra danh tính sau xác thực.

Ví dụ **JAAS config minh họa cho môi trường Kerberos đã được quản trị**:

**Tệp `jaas.conf` (đường dẫn/keytab/principal chỉ là mẫu):**

```properties
KrbClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    doNotPrompt=true;
};

KrbService {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/secure/keytabs/http-api.keytab"
    principal="HTTP/api.example.com@EXAMPLE.COM"
    storeKey=true
    doNotPrompt=true
    isInitiator=false;
};
```

Ứng dụng gọi `LoginContext("KrbClient")` hoặc `LoginContext("KrbService")` và thực hiện thao tác GSS trong `Subject` thích hợp (ví dụ `Subject.doAs(...)` trên Java 17) khi dựa vào mô hình JAAS/Subject. Đường dẫn `-Djava.security.auth.login.config=/secure/jaas.conf` chọn cấu hình JAAS; `-Djava.security.krb5.conf=/secure/krb5.conf` chọn cấu hình Kerberos. Các tùy chọn thực tế phụ thuộc môi trường chạy, JDK/provider và cách dùng ticket cache hoặc keytab.

Lưu ý: `javax.security.auth.useSubjectCredsOnly` ảnh hưởng cách triển khai Kerberos tìm credential trong Java. Không đổi nó thành `false` như một “cách chữa mọi lỗi”; trước hết xác định nguồn credential hợp lệ, `Subject` đang dùng và chính sách bảo mật.

## 10. Các lỗi và hiểu nhầm thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `GSSException: NO_CRED` hoặc “Failed to find any Kerberos tgt” | Ticket/keytab thiếu, JAAS chưa login, dùng sai `Subject`, sai usage initiator/acceptor | Kiểm tra login và credential thực tế; chọn đúng vai trò |
| “Cannot locate default realm” ngay khi `createName` | Realm Kerberos chưa được cấu hình | Kiểm tra `krb5.conf`/`krb5.ini` và cách ánh xạ realm |
| `BAD_NAME` hoặc principal không khớp | Dùng sai kiểu tên, service host hoặc realm | Phân biệt `HTTP@host` với `HTTP/host@REALM`; xác thực service principal có thật |
| `BAD_MECH` | Chỉ định OID không được provider hỗ trợ | Đối chiếu `manager.getMechs()` và cấu hình provider |
| `DEFECTIVE_TOKEN` / token không hợp lệ | Token bị cắt, sửa, mã hóa charset sai hoặc chuyển token của phiên khác | Framing nhị phân đúng, gói Base64 khi cần, không tái sử dụng context/token |
| Server không giải mã được ticket / lỗi integrity Kerberos | Keytab, SPN, kvno, encryption type hoặc realm không khớp | Kiểm tra service identity và khóa được cấp bởi quản trị Kerberos |
| Lỗi clock skew/ticket expired | Đồng hồ lệch hoặc ticket quá hạn | Đồng bộ thời gian, cấp lại ticket hợp lệ |
| `isEstablished()` nhưng thiếu thuộc tính bắt buộc | Lời gọi `request...` không bảo đảm mọi thuộc tính đã được chấp nhận | Kiểm tra `get...State()`, từ chối phiên không đạt policy |

Các trường hợp quan trọng khác:

- **Không so sánh token với chuỗi cố định.** Token có thể khác mỗi phiên, ngay cả khi cùng hai principal.
- **Không trộn context:** token từ phiên A không được đưa vào context của phiên B; không share context cho nhiều kết nối cùng lúc.
- **Không bỏ qua kết quả bảo vệ:** `wrap` có thể không cấp privacy như yêu cầu; đọc `MessageProp.getPrivacy()`; xử lý `GSSException` và các trạng thái supplementary của `MessageProp` liên quan replay/sequence nếu ứng dụng sử dụng.
- **Không dùng tên do client tự khai làm danh tính xác thực:** server chỉ tin `getSrcName()` sau khi chứng thực thành công và kiểm tra quyền.
- **Không mặc định có delegation:** `requestCredDeleg(true)` có tác động bảo mật lớn; chỉ sử dụng với yêu cầu rõ và giới hạn quyền phù hợp.
- **Không dùng API stream cũ chỉ vì tiện:** trên Java 17, ưu tiên phiên bản `byte[]` của `initSecContext`, `acceptSecContext`, `wrap` và `unwrap`; các overload stream đã bị deprecated từ Java 11.
- **Không nhầm GSS-API với SASL:** SASL có cơ chế tên `GSSAPI` và quy tắc giao thức riêng; nó có thể dùng GSS bên dưới nhưng `GSSContext` đơn lẻ không tự triển khai toàn bộ SASL, authorization identity hay thương lượng security layer.

## 11. Tình huống áp dụng và quy trình kiểm tra

**Tình huống:** service Java A cần gọi service B bằng Kerberos.

1. Xác định service B qua danh tính host-based đúng, ví dụ `HTTP@api.example.com`, và chọn cơ chế GSS Kerberos theo OID.
2. A có ticket khởi tạo hợp lệ, B có keytab/credential nhận phù hợp. B tạo `GSSCredential.ACCEPT_ONLY`, mỗi kết nối tạo một context nhận.
3. A tạo initiator context với `GSSName` của B, request mutual auth và các thuộc tính cần thiết.
4. Hai bên trao đổi binary token trong giao thức cho đến khi hoàn tất; chuyển mọi output token cần gửi ngay cả khi trạng thái local đã established.
5. A xác minh đã xác thực server và thuộc tính context cần thiết; B lấy `getSrcName()` rồi quyết định người gọi được phép thực hiện hành động nào.
6. Nếu phải bảo vệ nội dung ứng dụng, dùng `wrap/unwrap` hoặc `MIC` theo yêu cầu; kiểm tra privacy và lỗi xác minh. Cuối phiên gọi `dispose()`, hủy credential khi hết người dùng.

**Checklist QA khi triển khai:** đã dùng đúng kiểu tên và OID? credential đúng role? đã cấu hình realm, ticket, keytab? token được truyền nguyên vẹn và bounded? có timeout? đã xác minh thuộc tính thực tế và danh tính? có kiểm tra authorization? các context/credential được giải phóng hợp lý? có tránh log secret và tránh bật delegation vô cớ?

## 12. Câu hỏi tự kiểm tra

1. Vì sao tạo được `GSSManager` và thấy OID Kerberos vẫn chưa chứng minh đăng nhập Kerberos thành công?
2. `HTTP@api.example.com` là biểu diễn của loại tên nào? Vì sao khác `HTTP/api.example.com@EXAMPLE.COM`?
3. Sự khác nhau giữa `GSSCredential.ACCEPT_ONLY` và `INITIATE_ONLY` là gì? Server có thể dùng credential khởi tạo để `acceptSecContext` một cách mặc định không?
4. Tại sao phải gửi output token cuối ngay cả khi `isEstablished()` ở phía gửi đã là `true`?
5. `requestConf(true)` có đủ chứng minh thông điệp đã được mã hóa không? Cần kiểm tra hai nơi nào?
6. Vì sao xác thực thành công bằng `GSSContext` chưa đủ để quyết định user có quyền xem tài nguyên?
7. `getMIC/verifyMIC` khác `wrap/unwrap` ở điểm nào?
8. Khi phát sinh lỗi “Cannot locate default realm” ngay lúc tạo `GSSName`, bạn sẽ kiểm tra cấu hình nào trước?

## Tài liệu chuẩn

- [Java SE 17 — `org.ietf.jgss` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/package-summary.html)
- [Java SE 17 — `GSSManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html), [`GSSName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSName.html), [`GSSCredential`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSCredential.html), [`GSSContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html).
- [RFC 2743 — Generic Security Service API](https://www.rfc-editor.org/rfc/rfc2743); [RFC 2853 — Java bindings](https://www.rfc-editor.org/rfc/rfc2853); [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178).

**Kết nối ý chính:** `GSSManager` tạo các đối tượng; `GSSName` xác định peer; `GSSCredential` đại diện credential của chính phía đang chạy; `GSSContext` thực hiện xác thực và, sau khi thiết lập, cung cấp thao tác bảo vệ thông điệp. Tính an toàn phụ thuộc cả việc cấu hình danh tính và việc kiểm tra trạng thái/chính sách sau xác thực.