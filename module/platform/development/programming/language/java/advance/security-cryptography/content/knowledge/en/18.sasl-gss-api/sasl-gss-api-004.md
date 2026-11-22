# 18.4. SASL Quality of Protection: `auth`, `auth-int`, `auth-conf` và giới hạn theo mechanism

## 1. Bản chất của Quality of Protection (QOP)

**SASL (Simple Authentication and Security Layer)** là framework để giao thức ứng dụng như LDAP, IMAP hoặc SMTP tích hợp các **mechanism xác thực** có thể thay thế. Ngoài việc chứng thực danh tính, *một số* mechanism còn hỗ trợ **SASL security layer** bảo vệ dữ liệu ứng dụng sau khi phiên xác thực thành công.

**Quality of Protection (QOP)** mô tả mức bảo vệ **được thương lượng thực tế cho phiên SASL**. Ba mức thường gặp:

| QOP | Xác thực | Integrity của dữ liệu qua SASL layer | Confidentiality của dữ liệu qua SASL layer | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `auth` | Có | Không | Không | Chỉ xác thực ở SASL; dữ liệu ứng dụng không được SASL bảo vệ |
| `auth-int` | Có | Có | Không | Bảo vệ tính toàn vẹn; phát hiện sửa đổi trái phép trong phạm vi layer |
| `auth-conf` | Có | Có | Có | Bảo vệ tính toàn vẹn và tính bí mật trong phạm vi layer |

**Integrity không phải encryption.** Ở `auth-int`, thông điệp có thể vẫn đọc được dù việc sửa đổi sẽ bị phát hiện. Ở `auth-conf`, payload được cơ chế bảo vệ cả integrity lẫn confidentiality. Khả năng ngăn phát lại, bảo đảm thứ tự thông điệp, thuật toán mật mã và khóa cụ thể thuộc về mechanism/security context, không thể suy từ một chuỗi QOP mà không kiểm tra ngữ cảnh.

QOP mô tả lớp **SASL**, không thay thế việc đánh giá bảo mật *toàn bộ* kết nối. Ví dụ, PLAIN xác thực bên trong TLS vẫn có SASL QOP `auth` vì TLS mới là lớp mã hóa transport. Ngược lại, `auth-conf` bảo vệ những byte thực sự đi qua SASL security layer; nó không tự che IP, độ dài kết nối, metadata nằm ngoài layer hoặc toàn bộ trao đổi trước khi kích hoạt layer.

## 2. Thương lượng QOP: cấu hình là yêu cầu, không phải kết quả

Trong Java, hằng `Sasl.QOP` là khóa `javax.security.sasl.qop`. Giá trị cấu hình là **danh sách ưu tiên có thứ tự**, phân tách bằng dấu phẩy, ví dụ `"auth-conf,auth-int"`. Java SASL API quy định nếu không cung cấp thuộc tính này thì mặc định là `auth`.

Một QOP chỉ được chọn khi **đồng thời** đáp ứng:

1. Giao thức ứng dụng hỗ trợ SASL và quy định rõ cách đưa security layer vào luồng dữ liệu.
2. Mechanism đã chọn **có khả năng** cung cấp mức đó; SASL framework không tự thêm mã hóa cho mọi mechanism.
3. Client, server, provider, credentials và chính sách cho phép cùng một mức QOP.
4. Exchange xác thực kết thúc thành công; ứng dụng đọc **QOP thực tế** và đối chiếu với mức bảo vệ bắt buộc trước khi gửi dữ liệu nghiệp vụ.

```text
Client: yêu cầu auth-conf,auth-int
                 |
                 v
       Chọn SASL mechanism
                 |
    Exchange challenge / response
                 |
        +--------+--------+
        |                 |
  Không có mức chung   Xác thực thành công
        |                 |
     Thất bại       Đọc QOP được chọn
                          |
                  Kiểm tra chính sách
                          |
              Chấp nhận hoặc từ chối phiên
```

Nếu hai phía không có QOP tương thích, không được tự coi xác thực thành công là đủ để đáp ứng chính sách bảo mật. Nếu giao thức cho phép chọn `auth-int` nhưng ứng dụng yêu cầu confidentiality ở SASL layer, **từ chối phiên trước khi trao đổi dữ liệu ứng dụng**. Không tự đổi chính sách xuống `auth`. Nếu chính sách cho phép mã hóa bằng TLS thay vì security layer của SASL, cần xác minh TLS **riêng biệt** (đặc biệt xác thực máy chủ và cấm downgrade).

### Điều kiện của từng mức

- **`auth`:** phù hợp khi lớp khác đã cung cấp mức bảo vệ cần thiết hoặc chỉ cần xác thực; riêng SASL không bảo vệ nội dung các bản tin tiếp theo.
- **`auth-int`:** phù hợp khi cần chống sửa đổi của payload trong layer nhưng không bắt buộc bí mật dữ liệu **ở chính lớp đó**. Việc có `wrap` không chứng minh payload được mã hóa.
- **`auth-conf`:** dùng khi chính sách yêu cầu cả bí mật và toàn vẹn trong SASL layer. Phải xác thực QOP cuối cùng, đưa mọi thông điệp thuộc phạm vi bảo vệ qua `wrap/unwrap` và tôn trọng giới hạn kích thước.

## 3. Giới hạn phụ thuộc mechanism, provider và giao thức

**Không phải mọi SASL mechanism đều hỗ trợ cả ba mức.** Tên giao thức như LDAP hay SMTP không quyết định QOP, vì cùng một giao thức có thể tích hợp nhiều mechanism khác nhau.

| Mechanism / họ | Có SASL security layer không? | Lưu ý thực tế |
| --- | --- | --- |
| **PLAIN** | **Không** | RFC 4616 xác nhận PLAIN không có security layer. Chỉ sử dụng với kênh bảo vệ phù hợp, thường TLS; không thể cấu hình PLAIN thành `auth-conf` bằng `Sasl.QOP`. |
| **SCRAM** (SCRAM-SHA-256, SCRAM-*-PLUS) | **Không** theo RFC 5802/7677 | SCRAM xác thực; bản PLUS hỗ trợ channel binding với kênh ngoài. Channel binding không phải SASL encryption; cần TLS/SSH hoặc lớp bảo vệ tương ứng cho payload. |
| **EXTERNAL** | Không tự sinh security layer | Nhận danh tính từ kênh đã xác thực từ trước, ví dụ TLS client certificate; bảo vệ dữ liệu do kênh bên ngoài đảm nhiệm. |
| **GSSAPI/Kerberos V5** | **Có thể** có `auth`, `auth-int` và `auth-conf` | RFC 4752 mô tả trao đổi hỗ trợ security layer. Integrity/confidentiality chỉ được chào/chọn nếu GSS context và hai phía thực sự có khả năng. |
| **DIGEST-MD5** (di sản) | RFC 2831 từng mô tả đủ ba mức | **Không dùng cho triển khai mới:** RFC 6331 đã đánh dấu mechanism OBSOLETE và chuyển RFC 2831 sang Historic. |

Với **SASL GSSAPI**, thực tế thường dựa vào Kerberos V5: client cần credential/ticket phù hợp; máy chủ có service principal đúng; service name, hostname, chính sách, quyền ủy nhiệm và provider phải thống nhất. JDK có `JdkSASL` provider hỗ trợ GSSAPI cùng các thuộc tính QOP, nhưng điều đó **không bảo đảm** ứng dụng cuối cùng nhận `auth-conf`. RFC 4752 yêu cầu không quảng bá confidentiality security layer khi GSS context không có cờ khả năng tương ứng. Thư viện của giao thức bên ngoài còn có thể giới hạn các QOP mà nó cho phép.

SASL và **GSS-API** là hai lớp khái niệm: GSS-API cung cấp security context và các thao tác bảo vệ dữ liệu (GSS-Wrap/GSS-Unwrap); SASL quy định cách mechanism tích hợp các thao tác đó vào giao thức. Không lấy một ví dụ GSS-API bất kỳ rồi kết luận cơ chế SASL nào cũng có thể cung cấp cùng thuộc tính.

**Kết luận kiểm tra capability:** đọc tài liệu mechanism **và** provider cụ thể; kiểm tra chính sách hai đầu; xác minh QOP sau handshake; test thực tế trong giao thức ứng dụng. Tuyệt đối không gán `auth-conf` chỉ vì có JDK `javax.security.sasl` hoặc máy chủ hỗ trợ TLS.

## 4. Security layer sau xác thực và ý nghĩa của `wrap/unwrap`

RFC 4422 định nghĩa SASL security layer chỉ được kích hoạt **sau** outcome xác thực thành công, tại vị trí mà giao thức ứng dụng chỉ rõ. Khi lớp bảo vệ đang hoạt động, dữ liệu được xử lý thành các protected buffer.

- Với **`auth`**, không có lớp SASL integrity/confidentiality để xử lý các payload tiếp theo.
- Với **`auth-int`** hoặc **`auth-conf`**, client/server gọi `wrap(plain, offset, len)` để tạo protected buffer; phía nhận gọi `unwrap(protected, offset, len)` để lấy nội dung gốc hoặc phát hiện thất bại xác minh.
- Theo RFC 4422, mỗi protected buffer trên kết nối được đóng khung bằng **4 byte độ dài theo network byte order (big-endian)** trước dữ liệu đã bảo vệ. Giao thức hoặc thư viện cao hơn có thể đã quản lý framing: không được tự thêm một lần nữa.
- Nếu layer không thể bảo vệ hoặc giải mã một buffer, **đóng kết nối**; không chấp nhận payload chưa xác minh hoặc fallback sang truyền plaintext.

```text
Business payload
      |
      +-- QOP auth -----------> Truyền theo giao thức, không qua SASL layer
      |
      +-- QOP auth-int/conf --> wrap(...) --> [4-byte length][protected bytes]
                                                        |
                                                      mạng
                                                        |
                                         kiểm tra frame + unwrap(...)
                                                        |
                                                  Business payload
```

Cần hiểu **buffer maximum** và overhead. `Sasl.MAX_BUFFER` chỉ kích thước buffer nhận tối đa của SASL layer; `Sasl.RAW_SEND_SIZE` là lượng payload gốc tối đa gửi được trong một lần `wrap` do kết quả thương lượng/provider cung cấp. Protected output có thể dài hơn input vì MAC/tag/header/padding. Thuộc tính `Sasl.STRENGTH` cho phép ưu tiên mức mạnh của thuật toán đối với mechanism hỗ trợ, nhưng **không tạo** `auth-conf` nếu mechanism không có lớp mã hóa. Không dùng `MAX_BUFFER` hay `STRENGTH` như bằng chứng duy nhất để chấp nhận chính sách.

Khi dùng TLS **và** SASL layer, lớp ngoài TLS còn có thể bảo vệ transport; dữ liệu chỉ được bảo vệ bởi SASL trong phạm vi thực sự được đưa qua `wrap`. Thời điểm bắt đầu bảo vệ, thứ tự đóng gói, số bytes chấp nhận và chuyển trạng thái phải khớp giao thức ứng dụng; nếu thư viện đã trừu tượng hóa việc đó, ứng dụng nên dùng API chính thức của thư viện.

## 5. Java 17+: kiểm tra yêu cầu QOP an toàn

### 5.1. Ví dụ runnable: logic chính sách

Ví dụ đầu tiên kiểm tra quyết định **ACCEPT/REJECT** với QOP giả định đã được thương lượng. Nó **không thực hiện handshake hay mã hóa**; mục tiêu là kiểm thử quy tắc của ứng dụng trước khi tích hợp mechanism thật.

Tạo tệp `SaslQopPolicyDemo.java`:

```java
import java.util.Map;
import javax.security.sasl.Sasl;

public final class SaslQopPolicyDemo {
    private static boolean acceptable(
            String negotiated, boolean needIntegrity, boolean needPrivacy) {
        boolean valid = "auth".equals(negotiated)
                || "auth-int".equals(negotiated)
                || "auth-conf".equals(negotiated);
        if (!valid) {
            return false;
        }

        boolean hasIntegrity = "auth-int".equals(negotiated)
                || "auth-conf".equals(negotiated);
        boolean hasPrivacy = "auth-conf".equals(negotiated);
        return (!needIntegrity || hasIntegrity)
                && (!needPrivacy || hasPrivacy);
    }

    private static void check(
            String negotiated, boolean needIntegrity, boolean needPrivacy) {
        String result = acceptable(negotiated, needIntegrity, needPrivacy)
                ? "ACCEPT" : "REJECT";
        System.out.println(negotiated + " / I=" + needIntegrity
                + " / C=" + needPrivacy + " => " + result);
    }

    public static void main(String[] args) {
        Map<String, Object> props = Map.of(
                Sasl.QOP, "auth-conf,auth-int");
        System.out.println("QOP preferences: " + props.get(Sasl.QOP));
        check("auth-conf", true, true);
        check("auth-int", true, false);
        check("auth-int", true, true);
        check("auth", true, false);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SaslQopPolicyDemo.java
java SaslQopPolicyDemo
```

Stdout chính xác:

```text
QOP preferences: auth-conf,auth-int
auth-conf / I=true / C=true => ACCEPT
auth-int / I=true / C=false => ACCEPT
auth-int / I=true / C=true => REJECT
auth / I=true / C=false => REJECT
```

Trong chương trình này, `props` là **ưu tiên yêu cầu**; tham số `negotiated` mới là **kết quả đầu vào của kiểm tra**. Trường hợp `auth-int` không đạt yêu cầu secrecy, và `auth` không đạt yêu cầu integrity. QOP không xác định (bao gồm `null`) cũng bị từ chối. Ở hệ thống thật, sau `REJECT` phải đóng phiên và không gửi dữ liệu nghiệp vụ nhạy cảm.

### 5.2. Điểm tích hợp thực với `SaslClient`

Java SASL API nằm trong module `java.security.sasl`: `Sasl.createSaslClient` chọn provider/mechanism, `SaslClient.evaluateChallenge` xử lý token từ server, `SaslClient.isComplete` phản ánh trạng thái exchange, `SaslClient.getNegotiatedProperty` đọc giá trị thương lượng và `SaslClient.wrap/unwrap` xử lý security layer khi có.

Đoạn sau **chỉ minh họa điểm tích hợp** trong một ứng dụng LDAP đã có callback handler, credentials và vòng trao đổi token do giao thức quản lý; đây **không phải chương trình độc lập**:

```java
Map<String, Object> props = Map.of(
        Sasl.QOP, "auth-conf,auth-int");
SaslClient client = Sasl.createSaslClient(
        new String[] {"GSSAPI"},
        null,
        "ldap",
        "directory.example.org",
        props,
        callbackHandler);
if (client == null) {
    throw new SaslException("Khong tim thay SASL mechanism phu hop");
}
```

Cần import `java.util.Map` và `javax.security.sasl.*`; biến `callbackHandler` và Kerberos security context phải được cung cấp bởi môi trường tích hợp thực. Nếu mechanism bị vô hiệu hóa, provider thiếu hoặc thông tin môi trường không hợp lệ, không nên giả định tạo client sẽ thành công. Hoàn tất trao đổi token và xác nhận outcome thành công theo **giao thức ứng dụng** trước khi truy vấn QOP.

Đọc QOP và chặn mọi phiên không đủ confidentiality tại ranh giới trước dữ liệu ứng dụng:

```java
static String requireConfidentialSaslLayer(SaslClient client)
        throws SaslException {
    if (!client.isComplete()) {
        throw new SaslException("SASL handshake chua hoan tat");
    }
    Object value = client.getNegotiatedProperty(Sasl.QOP);
    String qop = value instanceof String ? (String) value : null;
    if (!"auth-conf".equals(qop)) {
        throw new SaslException("QOP khong dap ung: " + qop);
    }
    return qop;
}
```

Đây là **phương thức tích hợp**, đặt trong class có import `Sasl`, `SaslClient`, `SaslException`. Theo hợp đồng API, gọi `getNegotiatedProperty` trước `isComplete()==true` có thể ném `IllegalStateException`; `null` nghĩa là thuộc tính không được thương lượng hoặc không áp dụng. Không so sánh `props.get(Sasl.QOP)` với chính sách rồi kết luận phiên an toàn: nó chỉ chứa danh sách mong muốn ban đầu.

Với phiên `auth-int`/`auth-conf`, sau khi đã kiểm tra QOP, mỗi protected payload phải đi qua `wrap/unwrap`. Phương thức Java SASL cho phép `wrap/unwrap` **chỉ sau khi** trao đổi xác thực hoàn tất *và* integrity/privacy đã được thương lượng. Dùng chúng ở QOP `auth` có thể ném `IllegalStateException`.

### 5.3. Framing minh họa theo RFC 4422

Hai phương thức dưới đây minh họa cơ chế **raw stream do ứng dụng tự xử lý**: prefix độ dài 4 byte, hạn chế kích thước nhận, gọi `wrap/unwrap`. Đoạn này biên dịch được như một class hỗ trợ, nhưng **không tự khởi tạo phiên SASL**, chỉ thích hợp khi peer đã thành công xác thực và protocol yêu cầu chuẩn framing này.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import javax.security.sasl.SaslClient;

final class SaslFrameIO {
    static void send(OutputStream socket, SaslClient client, byte[] plain)
            throws IOException {
        byte[] protectedData = client.wrap(plain, 0, plain.length);
        DataOutputStream out = new DataOutputStream(socket);
        out.writeInt(protectedData.length);
        out.write(protectedData);
        out.flush();
    }

    static byte[] receive(InputStream socket, SaslClient client,
                          int maxFrameBytes) throws IOException {
        if (maxFrameBytes <= 0) {
            throw new IllegalArgumentException("maxFrameBytes");
        }
        DataInputStream in = new DataInputStream(socket);
        int size = in.readInt();
        if (size < 0 || size > maxFrameBytes) {
            throw new IOException("Invalid SASL frame size: " + size);
        }
        byte[] protectedData = new byte[size];
        in.readFully(protectedData);
        return client.unwrap(protectedData, 0, protectedData.length);
    }
}
```

`DataOutputStream.writeInt` sử dụng big-endian, tương ứng network byte order. Trong ứng dụng thật, **còn phải**: kiểm tra kích thước plaintext so với `Sasl.RAW_SEND_SIZE` trước `wrap`; lấy `maxFrameBytes` từ chính sách/kết quả cơ chế hoặc protocol chứ không đoán; xử lý lỗi bằng đóng kết nối; trên server dùng `SaslServer.wrap/unwrap`; và **không tự bọc thêm** nếu thư viện LDAP/IMAP/SMTP đã làm việc này. `SaslException` kế thừa `IOException` nên hai chữ ký `throws IOException` phù hợp.

## 6. Phân biệt rõ SASL QOP và TLS

| Ví dụ | QOP SASL thực tế | Payload được bảo vệ bởi | Kết luận |
| --- | --- | --- | --- |
| **PLAIN + TLS** có xác thực máy chủ | `auth` | TLS | Có thể mã hóa kết nối đúng cách, nhưng PLAIN không tạo SASL security layer. |
| **SCRAM-SHA-256-PLUS + TLS** | `auth` | TLS, kèm channel binding trong authentication | “PLUS” không đồng nghĩa `auth-conf`; channel binding liên kết xác thực với kênh bảo vệ. |
| **GSSAPI `auth-int`** không có TLS | `auth-int` | SASL integrity layer | Có chống sửa đổi trong phạm vi layer; **không có confidentiality** của payload từ riêng layer này. |
| **GSSAPI `auth-conf`** | `auth-conf` | SASL security layer | Dữ liệu thực sự đi qua `wrap` được bảo vệ integrity và confidentiality. |
| **GSSAPI `auth` + TLS** | `auth` | TLS | Có thể đáp ứng yêu cầu *transport encryption*; không đáp ứng điều kiện bắt buộc **SASL QOP phải là `auth-conf`**. |

Quy tắc bảo mật nên phát biểu chính xác: “phải có TLS được xác minh” hay “phải có SASL `auth-conf`”, hoặc cả hai. Mỗi yêu cầu phải được kiểm thử độc lập. Cách phòng tránh downgrade cũng phụ thuộc cơ chế lựa chọn mechanism, danh tính peer và việc bảo vệ kênh trước/sau xác thực, không thể chỉ kiểm tra QOP cuối cùng là đủ.

## 7. Lỗi phổ biến, dấu hiệu và cách sửa

1. **Dùng cấu hình làm bằng chứng:** thấy `Sasl.QOP=auth-conf,auth-int` rồi ghi log “encrypted”. Sửa: chỉ báo mức bảo vệ sau khi đọc `getNegotiatedProperty(Sasl.QOP)` khi authentication thành công.
2. **Yêu cầu privacy với mechanism không có layer:** PLAIN hay SCRAM không cho `auth-conf` từ SASL. Sửa: áp dụng TLS được xác thực hoặc chọn mechanism/protocol phù hợp, không tự hạ chính sách.
3. **Đánh đồng `auth-int` với mã hóa:** integrity không ẩn nội dung. Sửa: đặt yêu cầu confidentiality riêng và kiểm tra `auth-conf` nếu cần ở lớp SASL.
4. **Gọi `getNegotiatedProperty` khi exchange chưa hoàn tất:** API có thể ném `IllegalStateException`. Sửa: kiểm tra `isComplete()` và outcome thành công của giao thức.
5. **Gọi `wrap/unwrap` với QOP `auth`:** API chỉ cho phép sau khi integrity/privacy đã được thương lượng. Sửa: không tự gọi security layer khi nó không tồn tại.
6. **Sai framing hoặc kích thước:** thiếu 4-byte length, vượt max frame, hoặc giả định raw và protected buffer dài bằng nhau. Sửa: tuân thủ protocol, kiểm tra độ dài **trước** cấp phát và chia nhỏ payload đúng raw-send limit.
7. **Tiếp tục khi `unwrap` thất bại:** xử lý dữ liệu lỗi như plaintext làm mất bảo đảm integrity. Sửa: dừng xử lý, đóng kết nối.
8. **GSSAPI chưa sẵn sàng:** principal/Kerberos ticket/service name/hostname/provider không hợp lệ. Sửa: chẩn đoán xác thực/context trước khi xét negotiated QOP.
9. **Tin rằng SASL layer phủ mọi byte:** handshake và metadata ngoài phạm vi có thể không được layer bảo vệ. Sửa: đánh giá rõ phạm vi thông điệp, áp dụng TLS khi cần.
10. **Dùng DIGEST-MD5 vì từng hỗ trợ ba mức:** RFC 6331 đã obsoleted mechanism này. Sửa: chọn giải pháp được duy trì và kiểm chứng.

### Checklist kiểm thử tích hợp

- Ghi nhận mechanism chọn thực tế, provider/version, QOP yêu cầu của hai phía, **QOP thương lượng**, và trạng thái TLS; không log password, raw ticket/token hoặc plaintext nhạy cảm.
- Test một phiên đạt yêu cầu và một phiên bị downgrade/không đủ QOP; trường hợp không đủ **phải thất bại trước khi gửi payload nghiệp vụ**.
- Với `auth-int`, can thiệp protected frame để xác minh bị từ chối; không suy ra confidentiality từ việc test integrity thành công.
- Với `auth-conf`, xác minh dữ liệu đi qua `wrap/unwrap`, thử frame sai độ dài và frame lỗi, kiểm tra xử lý đóng kết nối.
- Test payload lớn để kiểm tra overhead, `MAX_BUFFER`, `RAW_SEND_SIZE`, chunking và giới hạn nhận.
- Kiểm tra TLS và danh tính máy chủ **riêng** nếu hệ thống dựa vào bảo vệ transport.

## 8. Bài tập tình huống và đáp án

**A.** Client yêu cầu `auth-conf,auth-int`, server chỉ có `auth-int`; chính sách ứng dụng bắt buộc bí mật dữ liệu trong SASL layer. **Đáp án:** Có thể chọn `auth-int` về mặt cơ chế, nhưng ứng dụng phải từ chối vì không có confidentiality.

**B.** PLAIN chạy qua TLS và Java trả QOP `auth`. Có mâu thuẫn không? **Không:** PLAIN chỉ xác thực; TLS bảo vệ transport. Hai khái niệm ở hai lớp khác nhau.

**C.** Phiên đã chọn `auth-conf` nhưng ứng dụng viết thẳng payload vào socket, bỏ qua security layer mà protocol yêu cầu. Dữ liệu đã an toàn chưa? **Chưa:** QOP không tự bảo vệ byte đi vòng qua `wrap`.

**D.** `getNegotiatedProperty(Sasl.QOP)` trả `null` sau authentication thành công. Có thể giả sử `auth-conf` không? **Không:** thuộc tính không có/không áp dụng; nếu cần SASL security layer thì từ chối hoặc điều tra provider.

**E.** `SCRAM-SHA-256-PLUS` có chữ “PLUS”. Nó có SASL `auth-conf` không? **Không:** PLUS là cơ chế channel binding với kênh bên ngoài, không phải security layer bảo vệ payload.

## 9. Tài liệu chuẩn và Java API

- [RFC 4422 – SASL, §3.7 Security Layers](https://www.rfc-editor.org/rfc/rfc4422.html): thời điểm cài đặt layer, framing 4 byte, xử lý lỗi và giới hạn buffer.
- [RFC 4752 – GSSAPI/Kerberos V5 SASL mechanism](https://www.rfc-editor.org/rfc/rfc4752.html): thương lượng no layer/integrity/confidentiality và điều kiện GSS context.
- [RFC 4616 – PLAIN](https://www.rfc-editor.org/rfc/rfc4616.html): PLAIN không cung cấp security layer.
- [RFC 5802 – SCRAM](https://www.rfc-editor.org/rfc/rfc5802.html), [RFC 7677 – SCRAM-SHA-256](https://www.rfc-editor.org/rfc/rfc7677.html): SCRAM không thương lượng security layer, channel binding là thuộc tính khác.
- [RFC 6331 – Moving DIGEST-MD5 to Historic](https://www.rfc-editor.org/rfc/rfc6331.html): cảnh báo đối với mechanism di sản.
- [Java SE 21 `Sasl` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html), [`SaslClient` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html) và [Java 17 SASL programming guide](https://docs.oracle.com/en/java/javase/17/security/java-sasl-api-programming-and-deployment-guide1.html): tên thuộc tính, danh sách ưu tiên, kết quả negotiated, `wrap/unwrap` và provider GSSAPI.

**Ghi nhớ:** `auth` chỉ xác thực; `auth-int` thêm integrity; `auth-conf` thêm confidentiality. Mức QOP **thực nhận** phụ thuộc mechanism, provider, hai đầu và giao thức. Không thay thế kiểm chứng kết quả bằng cấu hình mong muốn, và không xem TLS security là một SASL QOP khác.
