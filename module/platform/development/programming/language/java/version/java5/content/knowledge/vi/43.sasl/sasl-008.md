# wrap, unwrap khi cơ chế hỗ trợ lớp bảo vệ

## 1. Xác thực xong chưa có nghĩa là dữ liệu ứng dụng đã được bảo vệ

SASL (Simple Authentication and Security Layer) là khung tích hợp các cơ chế xác thực vào giao thức mạng. Sau quá trình xác thực, một số cơ chế còn thiết lập được **lớp bảo vệ dữ liệu (security layer)** cho các trao đổi tiếp theo.

Hai phương thức làm việc ở ranh giới này:

- `wrap(outgoing, offset, len)`: nhận các byte dữ liệu ứng dụng, tạo một khối được bảo vệ để gửi cho bên kia.
- `unwrap(incoming, offset, len)`: nhận một khối được bảo vệ từ bên kia, kiểm tra và khôi phục dữ liệu ứng dụng.

Không phải mọi cơ chế SASL đều cung cấp lớp này. Cũng không phải cứ gọi `wrap` là dữ liệu sẽ được mã hóa: mức bảo vệ phụ thuộc kết quả thương lượng. API này vẫn có trong Java hiện hành; bài học tập trung vào hợp đồng API và cách tích hợp, không dựa vào cơ chế xác thực lỗi thời. [Java SASL API Guide](https://docs.oracle.com/en/java/javase/25/security/java-sasl-api-programming-and-deployment-guide1.html)

Ví dụ về nhu cầu: một kết nối đã xác thực người dùng thành công nhưng sau đó gửi lệnh truy vấn ở dạng rõ. Nếu không có TLS hoặc một lớp bảo vệ phù hợp khác, thành công của bước xác thực không tự bảo đảm tính bí mật hay toàn vẹn cho các lệnh đó.

## 2. Phân biệt ba mức QOP

QOP là chất lượng bảo vệ (quality of protection). Các giá trị của `Sasl.QOP` có ý nghĩa:

| QOP đã thương lượng | Bảo vệ dữ liệu ứng dụng bằng SASL | Có gọi wrap/unwrap không? |
|---|---|---|
| `auth` | Chỉ xác thực; không có lớp bảo vệ dữ liệu SASL | Không |
| `auth-int` | Xác thực và bảo vệ tính toàn vẹn | Có |
| `auth-conf` | Xác thực, bảo vệ tính toàn vẹn và tính bí mật | Có |

**Toàn vẹn** giúp phát hiện dữ liệu bị thay đổi; **bí mật** giúp che nội dung. Vì vậy, không được coi `auth-int` là tương đương mã hóa.

Khi tạo đối tượng SASL, cấu hình như sau chỉ biểu thị các mức ứng dụng chấp nhận, theo thứ tự ưu tiên:

~~~java
Map<String, String> properties = Map.of(
    Sasl.QOP, "auth-conf,auth-int"
);
~~~

Đây là đoạn cấu hình, cần import `java.util.Map` và `javax.security.sasl.Sasl`. Nó không ép một cơ chế chỉ hỗ trợ xác thực phải có khả năng bảo vệ dữ liệu. Nếu chính sách bắt buộc bí mật qua SASL, chỉ chấp nhận `auth-conf` và kiểm tra kết quả thực tế sau thương lượng. [Sasl.QOP](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html#QOP)

## 3. Khi nào được gọi?

Đối với `SaslClient`, `wrap` và `unwrap` chỉ hợp lệ sau khi:

1. `isComplete()` trả về `true`.
2. Kết quả `getNegotiatedProperty(Sasl.QOP)` là `auth-int` hoặc `auth-conf`.

Gọi trước khi hoàn tất hoặc với QOP không có toàn vẹn/bí mật sẽ gây `IllegalStateException`. Thuộc tính thương lượng cũng chỉ được đọc sau khi hoàn tất. [SaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClient.html)

Ngoài trạng thái đối tượng, thư viện giao thức phải xử lý đầy đủ thông báo thành công và mọi dữ liệu xác thực cuối cùng theo giao thức đang dùng. Không chuyển sang gửi dữ liệu ứng dụng chỉ vì một phía đã tự thấy `isComplete() == true`. Điểm bắt đầu áp dụng lớp bảo vệ phải khớp ở hai đầu kết nối.

Luồng xử lý đúng là:

~~~text
Thương lượng/xác thực SASL theo giao thức
    -> Xác nhận thành công ở cấp giao thức
    -> Kiểm tra QOP và chính sách ứng dụng
    -> Cài lớp bảo vệ nếu đã thương lượng
    -> Trao đổi dữ liệu ứng dụng qua lớp này
~~~

Nếu cơ chế không có lớp bảo vệ, ứng dụng đi theo đường truyền của giao thức/TLS đã thiết lập, thay vì gọi `wrap` để thử khả năng. Không được tự hạ chính sách từ yêu cầu `auth-conf` xuống `auth` khi gặp lỗi.

## 4. Hai chiều dữ liệu và phần việc của từng bên

Các đối tượng có vai trò đối xứng:

~~~text
Client application bytes
  -> SaslClient.wrap
  -> truyền khối được bảo vệ
  -> SaslServer.unwrap
  -> Server application bytes

Server application bytes
  -> SaslServer.wrap
  -> truyền khối được bảo vệ
  -> SaslClient.unwrap
  -> Client application bytes
~~~

`SaslServer` cũng có điều kiện hoàn tất và QOP tương ứng. Không dùng `client.unwrap(client.wrap(data))` làm phép thử vòng về trên cùng đối tượng: bên gửi và bên nhận phải là các ngữ cảnh đối tác được thiết lập cùng phiên. [SaslServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html)

Ứng dụng không tự tạo MAC, không tự chọn IV và không sửa cấu trúc token mà cơ chế trả về. Những phần đó thuộc cơ chế/provider. Ngược lại, việc đưa khối lên kết nối, giữ thứ tự, xử lý lỗi đọc/ghi và chuyển dữ liệu đã mở gói cho bộ phân tích giao thức là trách nhiệm của lớp tích hợp.

Coi đối tượng SASL là trạng thái của **một phiên kết nối**. Không chia sẻ tùy tiện cho nhiều kết nối hoặc gọi đồng thời từ nhiều luồng khi provider không bảo đảm khả năng đó. Thiết kế đơn giản là một luồng sở hữu chuỗi thao tác SASL của phiên, giữ thứ tự xử lý.

## 5. Đóng khung: wrap không tự gửi dữ liệu

Một lần đọc từ TCP có thể chỉ nhận một phần khối hoặc chứa nhiều khối liên tiếp. Vì vậy, ranh giới của một lần `read` không phải ranh giới token SASL.

Theo lớp bảo vệ SASL, mỗi khối được truyền với độ dài 4 byte, theo thứ tự byte mạng (big-endian):

~~~text
+----------------------+-----------------------------+
| độ dài token: 4 byte | token: đúng số byte đã nêu |
+----------------------+-----------------------------+
~~~

Độ dài này là số byte của **token được bảo vệ**, không phải độ dài dữ liệu ban đầu. Bên nhận đọc đủ header, kiểm tra giới hạn, đọc đủ token, rồi mới mở gói. Các byte header không được đưa vào `unwrap`.

Điểm chuyển từ xác thực sang lớp bảo vệ tuân theo giao thức bao ngoài. Khi đã cài lớp, không trộn các lệnh ứng dụng chưa bảo vệ vào giữa các khối. Nếu lớp bảo vệ không thể tiếp tục tạo hoặc giải mã khối, phải đóng kết nối. [RFC 4422, mục 3.7](https://www.rfc-editor.org/rfc/rfc4422.html#section-3.7)

Trong thư viện LDAP hoặc thư viện giao thức có hỗ trợ SASL, việc này thường đã nằm trong lớp I/O của thư viện. Không tự bọc thêm lần nữa quanh cùng dữ liệu.

## 6. Giới hạn bộ đệm: phân biệt dữ liệu gốc và token

Hai thuộc tính cần hiểu đúng:

| Thuộc tính | Ý nghĩa khi dùng lớp bảo vệ |
|---|---|
| `Sasl.RAW_SEND_SIZE` | Số byte dữ liệu gốc tối đa đưa vào một lần `wrap`; giá trị được thương lượng |
| `Sasl.MAX_BUFFER` | Kích thước bộ đệm nhận tối đa, tính bằng byte |

Giá trị thuộc tính được biểu diễn bằng chuỗi số nguyên. `RAW_SEND_SIZE` không phải kích thước token sau bảo vệ. Token có thể lớn hơn dữ liệu gốc vì thông tin bảo vệ và phần phụ thêm của cơ chế. [Các thuộc tính Sasl](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html#RAW_SEND_SIZE)

Ví dụ tính toán: nếu giá trị thương lượng của `RAW_SEND_SIZE` là 16.000 và cần gửi 40.000 byte thì chia đầu vào thành 16.000, 16.000, 8.000 byte; gọi `wrap` riêng cho từng phần và đóng khung riêng từng token. Không thể dự đoán độ dài token bằng cách cộng một hằng số tùy ý.

Phía nhận còn cần giới hạn riêng của ứng dụng để tránh cấp phát theo độ dài không tin cậy từ mạng. Giới hạn nhận phải phù hợp với cấu hình/provider và giao thức; nên áp dụng mức nhỏ hơn giữa các giới hạn liên quan. Không lấy `RAW_SEND_SIZE` cục bộ làm giới hạn token nhận.

## 7. Ví dụ tích hợp Java 17+: gửi nhiều khối, nhận đủ một khối

Ví dụ dưới đây là một **lớp tích hợp biên dịch được**, không phải chương trình xác thực độc lập. Nó cần một `SaslClient` thật đã thương lượng lớp bảo vệ thành công, cùng các luồng của kết nối tương ứng. Không giả lập mã hóa hoặc hard-code thông tin đăng nhập.

Lưu thành `SaslProtectedIo.java`:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClient;
import javax.security.sasl.SaslException;

public final class SaslProtectedIo {
    private SaslProtectedIo() {
    }

    private static void requireLayer(SaslClient client)
            throws SaslException {
        if (!client.isComplete()) {
            throw new SaslException("SASL exchange is incomplete");
        }

        Object qop = client.getNegotiatedProperty(Sasl.QOP);
        if (!"auth-int".equals(qop) && !"auth-conf".equals(qop)) {
            throw new SaslException("No negotiated SASL security layer");
        }
    }

    private static int rawSendLimit(SaslClient client)
            throws SaslException {
        Object value = client.getNegotiatedProperty(Sasl.RAW_SEND_SIZE);
        if (!(value instanceof String text)) {
            throw new SaslException("Missing raw send limit");
        }

        try {
            int limit = Integer.parseInt(text);
            if (limit <= 0) {
                throw new NumberFormatException("Non-positive limit");
            }
            return limit;
        } catch (NumberFormatException failure) {
            throw new SaslException("Invalid raw send limit", failure);
        }
    }

    public static void send(
            SaslClient client,
            DataOutputStream out,
            byte[] data) throws IOException {
        requireLayer(client);
        int rawLimit = rawSendLimit(client);

        int offset = 0;
        while (offset < data.length) {
            int count = Math.min(rawLimit, data.length - offset);
            byte[] token = client.wrap(data, offset, count);
            out.writeInt(token.length);
            out.write(token);
            offset += count;
        }
        out.flush();
    }

    public static byte[] receive(
            SaslClient client,
            DataInputStream in,
            int maxWrappedBytes) throws IOException {
        requireLayer(client);
        if (maxWrappedBytes <= 0) {
            throw new IllegalArgumentException(
                    "Receive limit must be positive");
        }

        long length = Integer.toUnsignedLong(in.readInt());
        if (length > maxWrappedBytes) {
            throw new IOException("Protected frame exceeds receive limit");
        }

        byte[] token = new byte[(int) length];
        in.readFully(token);
        return client.unwrap(token, 0, token.length);
    }
}
~~~

Biên dịch với JDK 17 trở lên:

~~~shell
javac SaslProtectedIo.java
~~~

Nếu thành công, `javac` không in thông báo và tạo `SaslProtectedIo.class`. Lớp không có `main`; không có stdout chạy mẫu hay yêu cầu chạy `java SaslProtectedIo`.

Những quyết định đáng chú ý trong ví dụ:

- `requireLayer` kiểm tra trạng thái và kết quả thực tế trước khi xử lý dữ liệu. Đây là kiểm tra có lớp bảo vệ, chưa thay thế chính sách riêng yêu cầu bắt buộc `auth-conf`.
- `rawSendLimit` từ chối trường hợp thiếu/sai giới hạn. Đây là lựa chọn chặt chẽ của ví dụ; nếu provider không công bố thuộc tính, cần xử lý theo hợp đồng provider, không tự đoán số byte an toàn.
- `writeInt` ghi header big-endian. `readInt` được đổi thành `long` không dấu trước khi kiểm tra để không hiểu giá trị header lớn thành độ dài âm.
- `readFully` đòi hỏi đủ token; kết nối bị cắt giữa khối sẽ gây lỗi thay vì mở gói dữ liệu thiếu.
- `maxWrappedBytes` là giới hạn đầu vào tin cậy do lớp kết nối cung cấp, phù hợp giới hạn nhận của phiên và ứng dụng. Không lấy nó từ chính header đang kiểm tra.
- `send` coi đầu vào là một đoạn của luồng byte; mảng rỗng không tạo token. Một lần gọi `receive` trả dữ liệu của một khối, không bảo đảm đã có cả một thông điệp ứng dụng.
- Bộ phân tích giao thức phía trên phải tích lũy các byte đã mở gói nếu một thông điệp trải qua nhiều khối. Không biến mỗi token thành một chuỗi UTF-8 riêng: một ký tự có thể bị chia giữa các khối.
- Lớp kết nối phải thiết lập timeout, quản lý luồng và đóng kết nối khi gửi, nhận hoặc kiểm tra bảo vệ thất bại. Không bắt lỗi rồi gửi lại bản rõ; cũng không tiếp tục phiên sau lỗi giữa chừng.
- Khi kết thúc phiên, chủ sở hữu giải phóng đối tượng bằng `dispose()` và đóng tài nguyên kết nối. Ví dụ không tự đóng các luồng do bên gọi truyền vào.

Không có môi trường SASL/provider và máy chủ phù hợp thì chỉ kiểm tra được khả năng biên dịch; muốn kiểm tra mã hóa/toàn vẹn thật phải dùng hai đầu phiên thực.

## 8. Quan hệ với TLS và cơ chế đang dùng

TLS và lớp bảo vệ SASL là hai khả năng khác nhau. Ví dụ, họ SCRAM trong RFC 5802 không thương lượng lớp bảo vệ dữ liệu SASL; nó được thiết kế để kết hợp với lớp ngoài như TLS. Vì vậy, xác thực SCRAM thành công không phải lý do để bắt đầu gọi `wrap` trên dữ liệu ứng dụng. [RFC 5802, mục 1](https://www.rfc-editor.org/rfc/rfc5802.html#section-1)

Ngược lại, cơ chế SASL `GSSAPI` dùng Kerberos có thể thương lượng lớp toàn vẹn hoặc bí mật. Khả năng thực tế còn phụ thuộc provider, cấu hình hai phía và giao thức. Đây là ví dụ về cơ chế có lớp bảo vệ; không có nghĩa mọi hệ thống dùng SASL phải triển khai Kerberos. [RFC 4752, mục 3.3](https://www.rfc-editor.org/rfc/rfc4752.html#section-3.3)

Nếu TLS đã có và giao thức chọn SASL chỉ để xác thực, QOP `auth` không đồng nghĩa toàn bộ kết nối đang truyền bản rõ: dữ liệu có thể được TLS bảo vệ. Ngược lại, không được suy ra TLS đang tồn tại chỉ từ QOP.

Khi hệ thống dùng cả TLS và lớp bảo vệ SASL, thứ tự các lớp phải theo đặc tả giao thức và thư viện. Không tự đảo thứ tự hoặc loại bỏ lớp đã thương lượng để giảm chi phí.

## 9. Các lỗi thường gặp và cách nhận diện

| Hiện tượng hoặc cách làm | Nguyên nhân/cách xử lý |
|---|---|
| `IllegalStateException` khi wrap/unwrap | Kiểm tra hoàn tất và QOP; không dùng lời gọi này để dò khả năng |
| Đã cấu hình `auth-conf` nhưng cho rằng chắc chắn có mã hóa | Phải kiểm tra kết quả thương lượng và thành công ở cấp giao thức |
| Dùng `auth-int` cho dữ liệu cần bí mật mà không có lớp mã hóa khác | Toàn vẹn không che nội dung; kiểm tra đúng chính sách bảo vệ |
| `unwrap` nhận cả 4 byte độ dài | Header thuộc đóng khung, phải tách trước |
| Một lần đọc socket được đưa thẳng vào `unwrap` | Cần đọc đủ một token theo độ dài, không theo ranh giới TCP |
| Dùng `data.length` làm độ dài header | Header phải chứa `token.length` |
| Chia token đã wrap thành nhiều lần unwrap | Cần ghép đủ token gốc trước khi mở gói |
| Gửi đầu vào lớn vượt giới hạn một lần wrap | Chia dữ liệu gốc theo `RAW_SEND_SIZE`, rồi wrap từng phần |
| Lỗi bảo vệ nhưng vẫn tiếp tục đọc hoặc gửi bản rõ | Đóng phiên lỗi; không tự hạ cấp |
| Lưu đối tượng SASL vào biến dùng chung cho nhiều kết nối | Tách trạng thái theo phiên và quản lý vòng đời rõ ràng |

## 10. Tự kiểm tra trước khi đưa vào thư viện kết nối

Với một cặp client/server thật trong môi trường kiểm thử, cần quan sát được:

1. QOP `auth` đi theo đường I/O không dùng lớp SASL; chính sách yêu cầu lớp SASL phải từ chối phiên không đáp ứng.
2. QOP `auth-int` hoặc `auth-conf` truyền dữ liệu đúng theo hai chiều.
3. Dữ liệu lớn hơn `RAW_SEND_SIZE` được chia khối và ghép lại đúng, kể cả dữ liệu UTF-8 nhiều byte.
4. Header quá lớn bị từ chối trước cấp phát; token bị cắt giữa chừng không được xử lý như thông điệp hợp lệ.
5. Dữ liệu bảo vệ bị sửa không được giao cho ứng dụng; lỗi làm đóng kết nối.
6. Không có log chứa mật khẩu, khóa phiên hay dữ liệu ứng dụng nhạy cảm.

Trọng tâm của `wrap`/`unwrap` là sử dụng **đúng lớp bảo vệ đã thương lượng**, với ranh giới khối, giới hạn và vòng đời phù hợp. Chúng không thay thế thương lượng SASL, đặc tả giao thức hoặc chính sách bảo mật của ứng dụng.
