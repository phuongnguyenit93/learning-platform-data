# 18.7 — Thiết lập ngữ cảnh GSS, wrap/unwrap, MIC và kiểm tra replay hoặc thứ tự

## 1. Mục tiêu và mô hình cần nắm

Sau bài này, bạn có thể: (1) phân biệt xác thực khi thiết lập `GSSContext` với bảo vệ từng thông điệp sau xác thực; (2) triển khai luồng `initSecContext`/`acceptSecContext` qua kênh truyền có đóng khung token; (3) chọn `wrap`/`unwrap` hay `getMIC`/`verifyMIC` theo yêu cầu bí mật dữ liệu; (4) yêu cầu, xác minh và xử lý đúng replay/sequence detection; (5) tránh coi các cờ GSS là chính sách ứng dụng tự động.

**GSS-API (Generic Security Service API)** là giao diện chung cho cơ chế bảo mật như Kerberos. Trong Java, API chuẩn nằm ở module `java.security.jgss`, package `org.ietf.jgss`. GSS có hai phía: **initiator** (bên khởi tạo, thường là client) và **acceptor** (bên chấp nhận, thường là server). Hai phía trao đổi các **token nhị phân** để xây dựng ngữ cảnh bảo mật, rồi dùng chính ngữ cảnh ấy để bảo vệ dữ liệu. GSS **không tự cung cấp** kết nối TCP, định dạng frame, định tuyến thông điệp, retry hay phân quyền nghiệp vụ. SASL có thể sử dụng cơ chế GSSAPI, nhưng phần này thao tác trực tiếp bằng Java GSS-API.

Các đối tượng chính:

| Thành phần | Vai trò |
|---|---|
| `GSSManager` | Factory tạo `GSSName`, `GSSCredential`, `GSSContext`; liệt kê mechanism. |
| `GSSName` | Danh tính bên gửi/bên nhận hoặc service được nhắm tới. |
| `GSSCredential` | Handle tới thông tin xác thực đã được cấp; API không tự đăng nhập để tạo danh tính. |
| `GSSContext` | Trạng thái xác thực, khóa/sequence của **một phiên**; dùng để tạo/kiểm tra token. |
| `MessageProp` | Chọn QOP/privacy khi gửi; nhận QOP/privacy và trạng thái replay/order khi nhận. |
| `GSSException` | Lỗi token, credential, policy mechanism, timeout/expiry, kiểm tra MIC... |

## 2. Ngữ cảnh GSS được thiết lập như thế nào?

```text
Initiator                                          Acceptor
  |  createContext(target, mechanism, credential)    | createContext(acceptorCredential)
  |  requestMutualAuth/Conf/Integ/Replay/Sequence     |
  |                                                  |
  | -- initSecContext(empty) -> token #1 ----------> |
  |                                   acceptSecContext(token #1)
  | <--------- token #2 (nếu phát sinh) ------------- |
  | initSecContext(token #2)                          |
  | -- token #3 (nếu phát sinh) --------------------> |
  |                      ...                         |
  | isEstablished() trên cả hai phía                  |
  | check get*State(), peer identity, authorization   |
  | ====== ứng dụng bắt đầu trao đổi dữ liệu ======= |
  | -- wrap(plaintext) -> wrapped token ------------> | unwrap(token)
  | -- plaintext + getMIC(plaintext) ---------------> | verifyMIC(token, plaintext)
```

Một lần gọi `initSecContext` hoặc `acceptSecContext` **chưa chắc hoàn thành handshake**. Mỗi lời gọi nhận token trước đó và có thể trả một token mới; ứng dụng phải chuyển **đầy đủ byte của token**, kể cả khi phía tạo token đã báo `isEstablished() == true`. `null` nghĩa là lần gọi không phát sinh token để gửi. Kết quả `isEstablished()` là **trạng thái cục bộ**: giao thức truyền của ứng dụng phải điều phối để hai phía đều sẵn sàng trước khi gửi dữ liệu nghiệp vụ.

1. Chuẩn bị cơ chế và credential hợp lệ. Với Kerberos v5, OID chuẩn là `1.2.840.113554.1.2.2`; phía client thường cần TGT, phía server cần credential nhận cho service principal tương ứng.
2. Initiator tạo `GSSContext` cho **đúng service**, cấu hình các yêu cầu **trước lần `initSecContext` đầu tiên**: `requestMutualAuth(true)`, `requestInteg(true)`, `requestConf(true)`, `requestReplayDet(true)`, `requestSequenceDet(true)`. Không yêu cầu credential delegation nếu ứng dụng không thực sự cần.
3. Acceptor tạo context từ credential có quyền `ACCEPT_ONLY`. Nó không gọi các phương thức `request*` dành cho initiator; chính token thương lượng quyết định dịch vụ cuối cùng.
4. Đổi token qua transport; lặp đến khi cả hai context established. Token GSS **không được** đổi sang chuỗi bằng encoding mặc định, cắt ở byte 0 hoặc nhầm với dữ liệu UTF-8.
5. Khi thành công, kiểm tra trạng thái thực tế: `getMech()`, `getSrcName()`, `getTargName()`, `getMutualAuthState()`, `getIntegState()`, `getConfState()`, `getReplayDetState()`, `getSequenceDetState()`, `getLifetime()`. Một yêu cầu `request*` **không đảm bảo** mechanism sẽ bật tính năng tương ứng.
6. Server xác thực **và** phân quyền danh tính `getSrcName()` cho tài nguyên cụ thể. Client xác nhận service đích/đặc tính xác thực. Khi không đáp ứng chính sách bắt buộc, kết thúc context, không chuyển sang thông điệp nghiệp vụ.

Với `GSSName.NT_HOSTBASED_SERVICE`, Java nhận dạng dạng `service@hostname`, ví dụ `HTTP@app.example.com`; thư viện Kerberos có thể ánh xạ nó thành principal `HTTP/app.example.com@REALM`. Đừng nhầm ký hiệu `@` của host-based GSS name với phần `@REALM` trong principal Kerberos. DNS, realm, SPN và credential phải đồng nhất.

**Lưu ý về thứ tự gọi:** các phương thức `requestReplayDet`, `requestSequenceDet`, `requestConf`, `requestInteg`, `requestMutualAuth` chỉ được initiator yêu cầu **trước** lần `initSecContext` đầu tiên. `setChannelBinding(...)` (nếu dùng) cần đặt **trên cả hai phía, với cùng thông tin binding đã thỏa thuận**, trước khi bắt đầu context. Đối với phần lớn ứng dụng, chỉ cho phép message operations sau `isEstablished()`; `isProtReady()` tồn tại cho trường hợp cơ chế cho phép bảo vệ sớm nhưng cần quy tắc giao thức chặt chẽ.

## 3. Hai cách bảo vệ từng thông điệp

| Đường API | Thông điệp trên đường truyền | Đảm bảo chính |
|---|---|---|
| `wrap(plaintext, ..., new MessageProp(0, true))` → `unwrap(token, ..., prop)` | Một **wrapped token** chứa dữ liệu và thông tin kiểm tra | Integrity; thêm confidentiality **nếu thực tế privacy được áp dụng**. |
| `wrap(..., new MessageProp(0, false))` → `unwrap(...)` | Wrapped token có dữ liệu, không yêu cầu mã hóa | Integrity, dữ liệu không được giữ bí mật. |
| `getMIC(plaintext, ..., prop)` → `verifyMIC(micToken, ..., samePlaintext, ..., prop)` | **Plaintext và MIC token tách biệt** | Kiểm chứng integrity/authenticity; **không mã hóa plaintext**. |

`MessageProp(0, true)` có nghĩa QOP = 0 (mức mặc định) và **yêu cầu privacy**, không phải bằng chứng đã mã hóa. Sau `wrap`, kiểm tra `prop.getPrivacy()`; sau `unwrap`, kiểm tra `prop.getPrivacy()` của token thực nhận. Nếu ứng dụng bắt buộc bí mật mà `getConfState()` hoặc `getPrivacy()` không thỏa, phải từ chối. `getIntegState()` cần được bật cho cả wrap và MIC. MIC được tính trên **đúng chuỗi byte**: chỉ cần thay encoding, dấu xuống dòng hay một byte thì `verifyMIC` không còn khớp. Không dùng `getMIC` như API chữ ký chung độc lập với GSS context.

`getWrapSizeLimit(qop, confReq, maxTokenSize)` ước lượng lượng dữ liệu đầu vào tối đa để wrapped token nằm trong giới hạn transport. Nó **không** thay thế giới hạn frame, kiểm tra kích thước token thực nhận, hay phân mảnh ở lớp ứng dụng.

## 4. Ví dụ Java 17+: tạo context, đổi token, xử lý message

Tệp dưới đây **biên dịch và chạy được trên JDK 17+**. Lệnh `main` chỉ chạy một bài kiểm thử chính sách replay/order bằng `MessageProp` giả lập nên **không cần KDC**. Các phương thức `newInitiator`, `newAcceptor`, `establish...`, `protect`, `open`, `makeMic`, `verifyMic` là mã thực để tích hợp vào client/server **khi đã có credential Kerberos và transport**. Không có dữ liệu Kerberos thật được tạo tự động trong chương trình kiểm thử.

```java
// File: GssLesson.java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.ietf.jgss.*;

public final class GssLesson {
    private GssLesson() {}

    // Chỉ trao đổi token GSS; lớp ứng dụng phải quản lý phase handshake/data.
    public interface TokenPipe {
        void send(byte[] token) throws IOException;
        byte[] receive() throws IOException;
    }

    // Ví dụ framing nhị phân: độ dài int 4 byte + token; hai phía dùng cùng quy ước.
    public static final class FramedPipe implements TokenPipe {
        private static final int MAX_TOKEN = 1_048_576;
        private final DataInputStream in;
        private final DataOutputStream out;

        public FramedPipe(InputStream input, OutputStream output) {
            in = new DataInputStream(input);
            out = new DataOutputStream(output);
        }

        @Override
        public void send(byte[] token) throws IOException {
            if (token == null || token.length > MAX_TOKEN) {
                throw new IOException("Invalid outgoing token length");
            }
            out.writeInt(token.length);
            out.write(token);
            out.flush();
        }

        @Override
        public byte[] receive() throws IOException {
            int size = in.readInt();
            if (size < 0 || size > MAX_TOKEN) {
                throw new IOException("Invalid incoming token length");
            }
            byte[] token = new byte[size];
            in.readFully(token);
            return token;
        }
    }

    private static Oid kerberosV5() throws GSSException {
        return new Oid("1.2.840.113554.1.2.2");
    }

    // Client: đã có default initiator credential, ví dụ TGT của Subject hiện hành.
    public static GSSContext newInitiator(String hostBasedService)
            throws GSSException {
        GSSManager manager = GSSManager.getInstance();
        GSSName server = manager.createName(
                hostBasedService, GSSName.NT_HOSTBASED_SERVICE);
        GSSContext context = manager.createContext(
                server, kerberosV5(), null, GSSContext.DEFAULT_LIFETIME);
        context.requestMutualAuth(true);
        context.requestInteg(true);
        context.requestConf(true);
        context.requestReplayDet(true);
        context.requestSequenceDet(true);
        context.requestCredDeleg(false);
        return context;
    }

    // Server: caller sở hữu acceptorCredential và phải dispose khi xong.
    public static GSSContext newAcceptor(GSSCredential acceptorCredential)
            throws GSSException {
        return GSSManager.getInstance().createContext(acceptorCredential);
    }

    public static void establishInitiator(GSSContext context, TokenPipe link)
            throws GSSException, IOException {
        byte[] incoming = new byte[0]; // Token rỗng chỉ cho lời gọi đầu.
        while (!context.isEstablished()) {
            byte[] outgoing = context.initSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                link.send(outgoing); // Gửi cả khi context vừa established.
            }
            if (!context.isEstablished()) {
                incoming = link.receive();
                if (incoming == null) throw new EOFException("Missing GSS reply");
            }
        }
    }

    public static void establishAcceptor(GSSContext context, TokenPipe link)
            throws GSSException, IOException {
        while (!context.isEstablished()) {
            byte[] incoming = link.receive();
            if (incoming == null) throw new EOFException("Missing GSS request");
            byte[] outgoing = context.acceptSecContext(
                    incoming, 0, incoming.length);
            if (outgoing != null) {
                link.send(outgoing); // Không bỏ final token.
            }
        }
    }

    // Kiểm tra chính sách bắt buộc, không chỉ tin vào request* của client.
    public static void requireServices(GSSContext context,
            boolean requirePrivacy, boolean strictSequence) {
        if (!context.isEstablished()
                || !context.getMutualAuthState()
                || !context.getIntegState()
                || !context.getReplayDetState()
                || (strictSequence && !context.getSequenceDetState())
                || (requirePrivacy && !context.getConfState())) {
            throw new SecurityException("Required GSS service unavailable");
        }
    }

    public static void checkArrival(MessageProp p,
            boolean requirePrivacy, boolean strictSequence) {
        if (p.isDuplicateToken()) {
            throw new SecurityException("Replay: duplicate token");
        }
        if (p.isOldToken()) {
            throw new SecurityException("Replay: old token");
        }
        if (strictSequence && p.isUnseqToken()) {
            throw new SecurityException("Sequence: unsequenced token");
        }
        if (strictSequence && p.isGapToken()) {
            throw new SecurityException("Sequence: gap token");
        }
        if (requirePrivacy && !p.getPrivacy()) {
            throw new SecurityException("Message was not encrypted");
        }
    }

    public static byte[] protect(GSSContext sender, String text,
            boolean requirePrivacy) throws GSSException {
        requireServices(sender, requirePrivacy, false);
        byte[] input = text.getBytes(StandardCharsets.UTF_8);
        MessageProp prop = new MessageProp(0, requirePrivacy);
        byte[] token = sender.wrap(input, 0, input.length, prop);
        if (requirePrivacy && !prop.getPrivacy()) {
            throw new SecurityException("wrap did not apply privacy");
        }
        return token;
    }

    public static String open(GSSContext receiver, byte[] wrappedToken,
            boolean requirePrivacy, boolean strictSequence)
            throws GSSException {
        requireServices(receiver, requirePrivacy, strictSequence);
        MessageProp prop = new MessageProp(0, false);
        byte[] plain = receiver.unwrap(
                wrappedToken, 0, wrappedToken.length, prop);
        checkArrival(prop, requirePrivacy, strictSequence);
        return new String(plain, StandardCharsets.UTF_8);
    }

    public static byte[] makeMic(GSSContext sender, byte[] message)
            throws GSSException {
        requireServices(sender, false, false);
        return sender.getMIC(
                message, 0, message.length, new MessageProp(0, false));
    }

    public static void verifyMic(GSSContext receiver, byte[] micToken,
            byte[] originalMessage, boolean strictSequence)
            throws GSSException {
        requireServices(receiver, false, strictSequence);
        MessageProp prop = new MessageProp(0, false);
        receiver.verifyMIC(
                micToken, 0, micToken.length,
                originalMessage, 0, originalMessage.length, prop);
        checkArrival(prop, false, strictSequence);
    }

    // Chỉ kiểm tra logic chính sách; KHÔNG tạo/kiểm chứng token Kerberos.
    private static String policyResult(MessageProp p, boolean strict) {
        try {
            checkArrival(p, false, strict);
            return "ACCEPT";
        } catch (SecurityException rejected) {
            return "REJECT";
        }
    }

    public static void main(String[] args) {
        MessageProp normal = new MessageProp(0, false);
        MessageProp duplicate = new MessageProp(0, false);
        MessageProp gap = new MessageProp(0, false);
        // Giả lập trạng thái provider sẽ điền sau unwrap/verifyMIC.
        duplicate.setSupplementaryStates(true, false, false, false, 0, null);
        gap.setSupplementaryStates(false, false, false, true, 0, null);
        System.out.println("normal=" + policyResult(normal, true));
        System.out.println("duplicate=" + policyResult(duplicate, true));
        System.out.println("gap_strict=" + policyResult(gap, true));
        System.out.println("gap_relaxed=" + policyResult(gap, false));
    }
}
```

Chạy từ thư mục chứa `GssLesson.java`:

```bash
javac -encoding UTF-8 GssLesson.java
java GssLesson
```

Kết quả chuẩn xác của **bài test chính sách giả lập**:

```text
normal=ACCEPT
duplicate=REJECT
gap_strict=REJECT
gap_relaxed=ACCEPT
```

Giải thích: `setSupplementaryStates` ở `main` chỉ dùng **trong phép thử** để tạo dữ liệu giả; trong xử lý GSS thực, provider điền cờ sau `unwrap`/`verifyMIC`, ứng dụng **không tự đặt cờ**. Việc `gap_relaxed=ACCEPT` minh họa rằng chính sách không bắt buộc thứ tự có thể chấp nhận token đến thiếu predecessor, **không** có nghĩa mọi nghiệp vụ được phép mất hoặc đảo thông điệp.

### 4.1. Kết nối class vào Kerberos thực tế

Trên môi trường có KDC, cấu hình `krb5.conf`, principal/keytab, JAAS/`Subject` hoặc login session phù hợp:

- Client tạo `GSSContext client = GssLesson.newInitiator("HTTP@app.example.com")` sau khi đã có initiator credential/TGT (ví dụ từ `kinit` hoặc Java login flow).
- Server tạo `GSSCredential serviceCred = manager.createCredential(serviceName, GSSCredential.DEFAULT_LIFETIME, kerberosOid, GSSCredential.ACCEPT_ONLY)` bằng principal có keytab/ticket hợp lệ, rồi `GSSContext server = GssLesson.newAcceptor(serviceCred)`.
- Mỗi phía dùng một `TokenPipe` trên connection. Client gọi `establishInitiator(...)`, server gọi `establishAcceptor(...)`. Server gửi token trả về cho client **trước khi** ứng dụng chuyển phase. Khung ví dụ ở trên chỉ chứa length + bytes; nếu dùng chung kênh cho nhiều loại message, bổ sung frame type/state machine và thông điệp kết thúc handshake của ứng dụng để tránh hiểu nhầm final token với dữ liệu.
- Sau khi cả hai bên sẵn sàng, mỗi bên gọi `requireServices(...)`, kiểm tra `getSrcName()`/`getTargName()` đúng danh tính mong đợi; server phân quyền trước khi cho phép xử lý request.
- Sender dùng `protect(context, "lệnh nghiệp vụ", true)` để tạo token, gửi qua kênh; receiver gọi `open(context, token, true, true)` và **chỉ thực hiện tác động nghiệp vụ sau khi mọi kiểm tra thành công**.
- Trường hợp chỉ cần integrity, sender gửi **hai thành phần**: byte `message` và `makeMic(context, message)`. Receiver gọi `verifyMic(context, mic, receivedMessage, true)` rồi mới sử dụng `receivedMessage`. Byte message phải được bảo toàn 100%.

Gọi `dispose()` trên mọi context và credential do ứng dụng sở hữu trong `finally` hoặc cơ chế quản lý tài nguyên tương đương. Không chia sẻ một `GSSContext` cho nhiều luồng đồng thời mà thiếu đồng bộ, bởi các phương thức context không được đảm bảo synchronized. Mỗi phiên/peer có context riêng; context hết hạn cần thiết lập lại theo chính sách, không tự dùng token của context cũ.

**Vì sao ví dụ không giả lập handshake thành công ngay trong `main`?** Kerberos cần credential và KDC thực. In ra “authenticated” từ dữ liệu giả sẽ tạo hiểu lầm về tính an toàn. Có thể kiểm tra biên dịch và logic policy độc lập; muốn chạy handshake thực, cần môi trường Kerberos tương ứng.

## 5. Replay detection và sequence detection: khác nhau ở đâu?

Replay là **phát lại** token cũ; sequence là **thứ tự giao nhận**. Context có thể phát hiện cả hai nhờ metadata/sequence của cơ chế, nhưng kết quả phụ thuộc tính năng thực sự đã thương lượng, phạm vi cửa sổ kiểm tra và cách ứng dụng sử dụng một context.

| Cờ nhận sau `unwrap`/`verifyMIC` | Ý nghĩa thực tế | Chính sách thường dùng |
|---|---|---|
| `isDuplicateToken()` | Token đã được xử lý trước đó trong cửa sổ phát hiện. | Từ chối, không chạy lại side effect. |
| `isOldToken()` | Token quá cũ để kiểm tra chắc việc phát lại. | Từ chối khi yêu cầu chống replay. |
| `isUnseqToken()` | Một token có thứ tự **muộn hơn** đã được xử lý trước token này. | Từ chối nếu giao thức yêu cầu đúng thứ tự. |
| `isGapToken()` | Chưa thấy một hoặc nhiều token tiền nhiệm mong đợi. | Dừng/chờ/báo lỗi theo protocol; từ chối nếu strict ordering. |

Các cờ là **thông tin bổ sung** về token nhận, không đồng nghĩa với “ứng dụng đã an toàn”. Sau `verifyMIC` không ném lỗi và sau `unwrap` trả về plaintext, vẫn phải kiểm tra các cờ trước khi chấp nhận. Với token hỏng, MIC sai, context hết hạn hoặc credential lỗi, API có thể ném `GSSException`; phải fail closed (không giải mã hoặc nhận message lỗi rồi tiếp tục nghiệp vụ). Đừng coi mọi `GSSException` là replay; ghi nhận major code (`getMajor()`, `getMajorString()`) để chẩn đoán có kiểm soát, tránh log secret/token gốc.

**Thứ tự đánh giá hợp lý tại receiver:**

1. Đảm bảo context đã thiết lập, có integrity và replay detection; nếu yêu cầu strict order thì `getSequenceDetState() == true`. Khi muốn mã hóa, cần thêm confidentiality.
2. Đọc **trọn một token**; giới hạn độ dài frame trước cấp phát bộ nhớ.
3. `unwrap` hoặc `verifyMIC`, bắt `GSSException`; không dùng plaintext khi xác minh thất bại.
4. Kiểm tra `duplicate` và `old`; nếu bật strict order, kiểm tra thêm `unseq` và `gap`. Nếu cần privacy, kiểm tra `prop.getPrivacy()`.
5. Chỉ khi đạt các kiểm tra mới parse, authorize và thực hiện nghiệp vụ; kết hợp transaction/idempotency key cho request có side effect.

Ví dụ thứ tự token do sender phát là `T1, T2, T3`:

| Receiver nhìn thấy | Khả năng cờ | Ý nghĩa ứng dụng |
|---|---|---|
| `T1, T2, T3` | Không có cờ bổ sung | Giao nhận đúng thứ tự (khi mechanism hỗ trợ). |
| `T1, T1` | `duplicate` ở lần thứ hai | Request thứ hai không được chạy lại. |
| `T1, T3` | Có thể `gap` tại `T3` | `T2` chưa được xử lý; quyết định chờ hay từ chối. |
| `T1, T3, T2` | Có thể `gap` ở `T3`, `unseq` ở `T2` | Với strict order, không thể âm thầm áp dụng T2 sau T3. |
| Token nằm ngoài cửa sổ kiểm tra | Có thể `old` | Không thể kết luận token mới an toàn; nên từ chối. |

“Có thể” ở trên là chủ ý: chi tiết thời điểm gắn cờ, cửa sổ kiểm tra, việc ném exception và đường đi token phụ thuộc mechanism/provider. Test bảo mật thật cần phát lại/chuyển thứ tự **chính những token đã được provider tạo ra trên hai context đang hoạt động**, không chỉ thao tác `MessageProp` bằng tay. Các cờ cũng chỉ bao quát **một context**; request bị gửi lại ở phiên mới cần chính sách idempotency/replay ở tầng ứng dụng.

### 5.1. Test case cần có khi tích hợp

| Ca thử | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Handshake hợp lệ | Client/service credentials đúng, mutual auth thành công | Cả hai established; identity và các `get*State()` đạt policy. |
| Service principal sai | Client trỏ sai service hoặc server không có key phù hợp | Không chấp nhận peer, không xử lý dữ liệu. |
| Wrapped token bị sửa byte | Thay một byte của token | `unwrap` lỗi MIC/token hoặc từ chối; không có side effect. |
| MIC so với message khác | `getMIC` trên A, `verifyMIC` trên B | Lỗi xác minh; không dùng B. |
| Chế độ bí mật không được cấp | `getConfState()==false` hoặc token `getPrivacy()==false` | Từ chối nếu chính sách cần confidentiality. |
| Phát lại cùng token | `unwrap`/`verifyMIC` hai lần trên cùng context | Cờ duplicate/old hoặc lỗi mechanism; từ chối lần hai. |
| Đảo thứ tự/gap | Gửi T2 trước T1 trên cơ chế có sequence detection | Xử lý theo chính sách strict; không chạy side effect của token sai thứ tự. |
| Context hết hạn | Gọi per-message API sau expiry | Từ chối, tạo phiên mới theo quy trình. |
| Kênh nhận frame dài bất thường | Length vượt giới hạn | Chặn trước khi cấp phát hoặc xử lý GSS token. |

## 6. Các lỗi thiết kế thường gặp và cách tránh

**Nhầm “request” với “đã được cấp”.** `requestReplayDet(true)` chỉ đề nghị dịch vụ. Quyết định nhận message phải dựa trên `getReplayDetState()`, `getSequenceDetState()` và trạng thái token sau khi xử lý.

**Cho rằng `wrap` luôn mã hóa.** Một wrapped token có thể chỉ có integrity. Muốn confidentiality, yêu cầu nó lúc thiết lập context, dùng `MessageProp(0, true)`, kiểm tra `getConfState()` và `getPrivacy()` ở cả bên gửi/bên nhận.

**Cho rằng MIC là mã hóa hoặc chữ ký không phụ thuộc phiên.** MIC không che plaintext; kết quả gắn với context và bytes của message. Khi protocol chuyển đổi JSON, Unicode normalization hay newline giữa sender và receiver, MIC có thể không hợp lệ. Chốt canonical representation hoặc giữ nguyên bytes.

**Bỏ qua cờ supplementary vì `unwrap` đã trả plaintext.** Plaintext có MIC hợp lệ vẫn có thể là replay hoặc sai thứ tự. Đặt check ngay sau GSS operation và trước parse/execute.

**Gộp mọi token vào một luồng mà không có framing/protocol phase.** GSS không đánh dấu kết thúc TCP stream hay phân biệt application frame. Dùng length prefix với giới hạn, phân loại message, xử lý token handshake trước message payload, và tránh deadlock do cả hai chờ nhận.

**Coi bảo vệ GSS là thay thế authorization và idempotency.** GSS xác nhận danh tính theo mechanism và bảo vệ token; ứng dụng vẫn phải kiểm tra role/quyền, request ID và chống thực thi lặp các thao tác như chuyển tiền/ghi trạng thái. Replay window của mechanism không thay thế nhật ký request đã xử lý.

**Dùng sai identity/credential.** Host-based `service@host` khác principal `service/host@REALM`. Credential mặc định có thể không tồn tại hoặc không có quyền `ACCEPT_ONLY`. Sử dụng keytab/JAAS/`Subject` đúng role, không nhúng password trong source hay log token nhạy cảm.

**Quên dọn tài nguyên và xử lý lỗi.** Khi `GSSException` xảy ra trong handshake, không được coi phiên established; đóng context và transport. Khi request bị từ chối do replay/order, đừng tự thực thi lại tác vụ chỉ vì transport retry. GSS context không an toàn để dùng song song tùy tiện; cần khóa hoặc phân chia context theo kết nối.

## 7. Checklist thực hành và tài liệu chuẩn

Trước khi bật GSS trên một dịch vụ, hãy kiểm tra đủ: identity client/service; Kerberos credential hợp lệ; token framing có kích thước tối đa; handshake hai chiều kết thúc rõ ràng; requested và negotiated flags được kiểm tra; `wrap`/`MIC` đúng yêu cầu confidentiality; receiver chặn token duplicate/old/out-of-order trước side effect; authorization/idempotency riêng; cleanup và negative tests.

Tài liệu đối chiếu:

- Java 17 `GSSContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html
- Java 17 `GSSManager` và `GSSCredential`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSManager.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSCredential.html
- Java 17 `MessageProp`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/MessageProp.html
- RFC 2743, GSS-API v2: https://www.rfc-editor.org/rfc/rfc2743.html
- RFC 8353, Java bindings update: https://www.rfc-editor.org/rfc/rfc8353.html

Ghi nhớ: **GSSContext xác lập phiên và danh tính; wrap/unwrap bảo vệ dữ liệu (có hoặc không có mã hóa); MIC kiểm tra nguyên vẹn; replay/order flags cho ứng dụng dữ liệu để quyết định nhận hay từ chối.**