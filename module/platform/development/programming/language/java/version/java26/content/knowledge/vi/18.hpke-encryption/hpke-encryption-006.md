# Phân biệt dữ liệu ngữ cảnh (info) và dữ liệu xác thực bổ sung (AAD)

HPKE (Hybrid Public Key Encryption) dùng ba thành phần mật mã phối hợp: cơ chế đóng gói khóa (KEM), hàm dẫn xuất khóa (KDF) và thuật toán mã hóa có xác thực kèm dữ liệu bổ sung (AEAD). Khi dùng HPKE, ứng dụng có thể cung cấp hai loại dữ liệu phụ trợ thường dễ nhầm lẫn:

- **Dữ liệu ngữ cảnh (info):** được đưa vào key schedule khi thiết lập HPKE context. Nó ràng buộc khóa được dẫn xuất với mục đích hoặc ngữ cảnh của ứng dụng.
- **Dữ liệu xác thực bổ sung (AAD):** được đưa vào từng thao tác mã hóa/giải mã của AEAD. AAD không bị mã hóa, nhưng được xác thực cùng ciphertext để phát hiện việc sửa đổi metadata.

Java 26 bổ sung API HPKE chuẩn qua **Cipher** với tên thuật toán **HPKE** và lớp **HPKEParameterSpec**. API thuộc module **java.base**, được đánh dấu **Since: 26**, là API Java SE ổn định; không phải preview hay incubator. JDK 27 tiếp tục cung cấp API này. Phần quan trọng khi triển khai là dùng đúng dữ liệu ở đúng giai đoạn, bảo đảm hai phía tái tạo cùng byte và giữ đúng thứ tự thông điệp trong một HPKE context.

## 1. HPKE thiết lập một context như thế nào?

Trong RFC 9180, HPKE chia quy trình thành hai giai đoạn:

1. **Thiết lập context:** KEM tạo shared secret giữa bên gửi và bên nhận; KDF dùng shared secret cùng các tham số để dẫn xuất khóa, nonce cơ sở và exporter secret.
2. **Trao đổi thông điệp:** AEAD dùng khóa và nonce nội bộ của context để mã hóa hoặc giải mã plaintext, đồng thời xác thực AAD.

Các tham số cốt lõi gồm:

| Thành phần | Vai trò |
|---|---|
| KEM | Thỏa thuận shared secret và tạo key encapsulation message |
| KDF | Dẫn xuất khóa và các giá trị bí mật từ shared secret |
| AEAD | Mã hóa plaintext và xác thực ciphertext cùng AAD |
| info | Ràng buộc key schedule với ngữ cảnh do ứng dụng định nghĩa |
| AAD | Gắn metadata của từng thông điệp vào phép xác thực AEAD |
| enc | Key encapsulation message công khai mà sender chuyển cho recipient |

Trong Java, sender tạo Cipher ở chế độ mã hóa bằng public key của recipient. Recipient tạo Cipher ở chế độ giải mã bằng private key tương ứng và cung cấp encapsulation message do sender tạo ra.

HPKE không yêu cầu ứng dụng tự tạo một IV mới cho từng thông điệp. Context duy trì sequence number nội bộ và dẫn xuất nonce riêng cho mỗi lần mã hóa/giải mã. Điều này giúp tránh nonce reuse khi ứng dụng tuân thủ thứ tự thông điệp của context.

## 2. Dữ liệu ngữ cảnh info dùng để làm gì?

Theo RFC 9180, info là dữ liệu do ứng dụng cung cấp, được đưa vào key schedule để gắn khóa dẫn xuất với một ngữ cảnh sử dụng cụ thể. Có thể xem info như một nhãn miền mật mã (domain separation): cùng một khóa công khai và cùng một bộ thuật toán nhưng dùng info khác nhau sẽ tạo context khóa khác nhau.

Ví dụ, một ứng dụng có thể dùng info để phân biệt:

- Tên giao thức và phiên bản giao thức.
- Mục đích của dữ liệu, chẳng hạn payload đơn hàng hoặc bản sao lưu.
- Phiên bản định dạng bản tin.
- Ngữ cảnh tenant hoặc kênh nghiệp vụ, nếu hai bên đã thống nhất chính xác giá trị đó.

Ví dụ một nhãn ngữ cảnh:

    byte[] info = "com.example.orders|v1|order-payload"
            .getBytes(StandardCharsets.UTF_8);

Thông tin này không phải khóa bí mật. Người quan sát có thể biết giá trị info nếu ứng dụng gửi nó trong giao thức. Bảo mật đến từ key schedule HPKE và private key, không đến từ việc giữ bí mật chuỗi info.

### Quy tắc quan trọng

- Sender và recipient phải cung cấp **cùng một chuỗi byte info**.
- info được chọn khi tạo HPKEParameterSpec và áp dụng cho toàn bộ context được khởi tạo từ tham số đó.
- info không phải AAD và không được tự động đưa vào từng ciphertext.
- Nếu hai phía dùng info khác nhau, key schedule tạo ra kết quả khác nhau; recipient không thể xác thực/giải mã ciphertext tương ứng.
- Nếu không cần dữ liệu ngữ cảnh riêng, dùng HPKEParameterSpec.of(...) với info rỗng mặc định. Không gọi withInfo() với mảng rỗng; API ném IllegalArgumentException.
- withInfo(byte[]) yêu cầu giá trị khác null và khác rỗng; API sao chép mảng đầu vào để tránh thay đổi sau khi tạo tham số.
- Để tương thích theo RFC 9180, Oracle khuyến nghị giới hạn info tối đa 64 byte.

Không đưa một cấu trúc lớn hoặc biến đổi theo từng thông điệp vào info. Dữ liệu thay đổi theo từng bản tin nên đặt ở AAD hoặc plaintext tùy yêu cầu về tính bí mật.

## 3. Dữ liệu xác thực bổ sung AAD dùng để làm gì?

AAD là metadata được AEAD xác thực cùng ciphertext nhưng **không được mã hóa**. Người quan sát có thể đọc AAD, nhưng nếu sửa AAD rồi chuyển ciphertext cho recipient, bước xác thực sẽ thất bại.

Các trường hợp phù hợp với AAD:

- Số thứ tự bản tin.
- Loại bản tin hoặc content type.
- Phiên bản header.
- ID luồng hoặc ID giao dịch không cần giữ bí mật.
- Các trường định tuyến hoặc metadata công khai cần được ràng buộc với nội dung đã mã hóa.

Ví dụ, một gói tin có header công khai chứa sequence number và message type. Ứng dụng truyền đúng byte header vào AAD. Khi nhận, recipient đọc header, tái tạo hoặc sử dụng đúng byte header đó làm AAD trước khi giải mã ciphertext. Nếu header bị sửa, tag AEAD không còn hợp lệ.

AAD không được tự động lưu trong ciphertext. Giao thức ứng dụng phải vận chuyển metadata đó hoặc bảo đảm hai bên có thể tái tạo chính xác cùng byte.

### Dùng AAD trong Java

Java cung cấp các overload của **Cipher.updateAAD(...)**:

- updateAAD(byte[]) nhận toàn bộ mảng byte.
- updateAAD(byte[], offset, length) nhận một vùng của mảng.
- updateAAD(ByteBuffer) nhận phần còn lại của buffer.

Với AEAD, cung cấp toàn bộ AAD cho từng thông điệp **trước khi** gọi update(...) hoặc doFinal(...) để xử lý plaintext/ciphertext. HPKE trong Java cho phép gọi lặp lại doFinal() trên cùng context; mỗi lần có thể được đặt trước bởi updateAAD(...) và update(...).

Sender và recipient phải cung cấp AAD giống hệt nhau cho cùng một thông điệp. Chỉ khác một byte, khác thứ tự trường hoặc khác cách mã hóa số/chuỗi cũng khiến xác thực thất bại.

## 4. So sánh info và AAD

| Tiêu chí | info | AAD |
|---|---|---|
| Thời điểm sử dụng | Khi thiết lập HPKE context/key schedule | Trước mỗi lần mã hóa hoặc giải mã một thông điệp |
| API Java | HPKEParameterSpec.withInfo(byte[]) | Cipher.updateAAD(byte[]) |
| Phạm vi | Toàn bộ context | Từng thông điệp |
| Mục đích | Domain separation và ràng buộc mục đích sử dụng của khóa | Xác thực metadata đi kèm ciphertext |
| Hai phía cần giống nhau? | Có, cùng byte info | Có, cùng byte AAD cho từng thông điệp |
| Có bị mã hóa không? | Không phải payload; không tự được vận chuyển | Không |
| Bị sửa đổi thì sao? | Key schedule không khớp; giải mã/xác thực thất bại | AEAD tag không hợp lệ; giải mã thất bại |
| Có thể thay đổi giữa các message trong cùng context? | Không; muốn thay info phải thiết lập context mới | Có; mỗi message có AAD riêng |
| Nên chứa | Tên giao thức, phiên bản, mục đích context | Sequence, message type, header công khai |
| Không nên dùng cho | Secret, payload, metadata thay đổi từng message | Secret hoặc dữ liệu cần giữ kín |

Một cách ghi nhớ:

- **info trả lời:** “Context mật mã này được tạo cho mục đích nào?”
- **AAD trả lời:** “Metadata công khai nào phải được xác thực cùng thông điệp này?”

Không dùng info để thay AAD cho header thay đổi theo từng message. Không dùng AAD để thay info khi cần tách biệt khóa giữa các giao thức hoặc mục đích sử dụng.

## 5. Tạo HPKE context với info trong JDK 26

Ví dụ dưới đây dùng bộ thuật toán được Java 26 định nghĩa:

- KEM: DHKEM(X25519, HKDF-SHA256).
- KDF: HKDF-SHA256.
- AEAD: AES-128-GCM.

Đây là một bộ thuật toán chuẩn trong RFC 9180. Oracle JDK 26 có triển khai HPKE trong SunJCE và hỗ trợ các định danh KEM/KDF/AEAD của RFC 9180. Với provider khác, cần kiểm tra tập thuật toán thực sự được hỗ trợ.

    import java.nio.charset.StandardCharsets;
    import java.security.KeyPair;
    import java.security.KeyPairGenerator;
    import java.util.Arrays;
    import javax.crypto.Cipher;
    import javax.crypto.spec.HPKEParameterSpec;

    public class HpkeInfoExample {
        public static void main(String[] args) throws Exception {
            // Recipient tạo cặp khóa X25519 và công bố public key.
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("X25519");
            KeyPair recipientKeys = generator.generateKeyPair();

            // Nhãn context giống nhau ở sender và recipient.
            byte[] info = "com.example.orders|v1|order-payload"
                    .getBytes(StandardCharsets.UTF_8);

            HPKEParameterSpec senderParameters =
                    HPKEParameterSpec.of(
                            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                            HPKEParameterSpec.KDF_HKDF_SHA256,
                            HPKEParameterSpec.AEAD_AES_128_GCM
                    ).withInfo(info);

            Cipher sender = Cipher.getInstance("HPKE");
            sender.init(
                    Cipher.ENCRYPT_MODE,
                    recipientKeys.getPublic(),
                    senderParameters
            );

            // Đây là KEM encapsulation message, không phải nonce
            // AEAD mà ứng dụng cần tự quản lý.
            byte[] encapsulation = sender.getIV();

            HPKEParameterSpec recipientParameters =
                    HPKEParameterSpec.of(
                            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                            HPKEParameterSpec.KDF_HKDF_SHA256,
                            HPKEParameterSpec.AEAD_AES_128_GCM
                    )
                    .withInfo(info)
                    .withEncapsulation(encapsulation);

            Cipher recipient = Cipher.getInstance("HPKE");
            recipient.init(
                    Cipher.DECRYPT_MODE,
                    recipientKeys.getPrivate(),
                    recipientParameters
            );

            byte[] plaintext = "Order ORD-2026-001"
                    .getBytes(StandardCharsets.UTF_8);

            byte[] ciphertext = sender.doFinal(plaintext);
            byte[] recovered = recipient.doFinal(ciphertext);

            if (!Arrays.equals(plaintext, recovered)) {
                throw new IllegalStateException("HPKE round trip failed");
            }
        }
    }

Trong giao thức thực tế, sender gửi encapsulation cùng ciphertext cho recipient. Recipient cần biết đúng private key tương ứng, bộ định danh thuật toán và info. Encapsulation là dữ liệu công khai của bước KEM; không phải bí mật và không cần mã hóa riêng.

Phương thức Cipher.getIV() có tên chung của JCA, nhưng với HPKE nó trả về key encapsulation message. Khi khởi tạo recipient, truyền giá trị đó vào HPKEParameterSpec.withEncapsulation(byte[]).

## 6. Thêm AAD cho từng thông điệp

AAD nên được mã hóa thành một cấu trúc byte có quy tắc rõ ràng. Không dùng cách nối chuỗi tùy tiện như tenant + sequence + type nếu không có phân cách hoặc length prefix, vì các trường khác nhau có thể tạo cùng một chuỗi byte.

Ví dụ này dùng header cố định gồm:

- 8 byte sequence number (big-endian).
- 1 byte message type.

    import java.nio.ByteBuffer;

    static byte[] makeAad(long sequence, byte messageType) {
        return ByteBuffer.allocate(Long.BYTES + Byte.BYTES)
                .putLong(sequence)
                .put(messageType)
                .array();
    }

Sender và recipient phải gọi hàm theo cùng định dạng và cùng giá trị. Nếu giao thức đã có header nhị phân được serialize, có thể dùng chính byte header đã nhận/gửi làm AAD, miễn là cả hai phía xác thực cùng một biểu diễn.

### Ví dụ hai thông điệp trong cùng context

Sau khi sender và recipient đã được init như ví dụ trước, có thể mã hóa nhiều thông điệp tuần tự:

    byte[] message1 = "Create order".getBytes(StandardCharsets.UTF_8);
    byte[] aad1 = makeAad(0L, (byte) 1);

    sender.updateAAD(aad1);
    byte[] ciphertext1 = sender.doFinal(message1);

    recipient.updateAAD(aad1);
    byte[] recovered1 = recipient.doFinal(ciphertext1);

    byte[] message2 = "Confirm payment".getBytes(StandardCharsets.UTF_8);
    byte[] aad2 = makeAad(1L, (byte) 2);

    sender.updateAAD(aad2);
    byte[] ciphertext2 = sender.doFinal(message2);

    recipient.updateAAD(aad2);
    byte[] recovered2 = recipient.doFinal(ciphertext2);

Mỗi lần doFinal() là một thông điệp HPKE hoàn chỉnh. AAD tương ứng phải được gọi trước doFinal() của thông điệp đó. Sau khi doFinal() hoàn tất, Cipher HPKE có thể tiếp tục xử lý thông điệp tiếp theo trên cùng context; nonce nội bộ được dẫn xuất từ sequence counter.

Trong ví dụ, sequence 0 và 1 vừa được đưa vào header/AAD để xác thực metadata, vừa phản ánh thứ tự mà ứng dụng phải duy trì. Sequence trong AAD không tự điều khiển nonce HPKE; nonce được quản lý nội bộ bởi HPKE context. Giá trị sequence trong AAD giúp recipient phát hiện và xác thực header theo giao thức ứng dụng.

## 7. Vì sao phải giữ đúng thứ tự thông điệp?

HPKE context là stateful. Sender và recipient cùng tiến qua một sequence counter nội bộ:

- Thông điệp đầu tiên dùng nonce dẫn xuất từ sequence 0.
- Thông điệp kế tiếp dùng nonce dẫn xuất từ sequence 1.
- Các thông điệp sau tiếp tục tăng sequence theo quy tắc RFC 9180.

Vì vậy, recipient phải giải mã đúng số lượng và đúng thứ tự ciphertext mà sender đã tạo trong context đó.

Nếu ứng dụng làm mất, bỏ qua hoặc đảo thứ tự một ciphertext, hai phía có thể lệch sequence. Những thông điệp tiếp theo sẽ không được giải mã bằng nonce tương ứng và xác thực AEAD sẽ thất bại. RFC 9180 không thiết kế HPKE context nhiều thông điệp để tự phục hồi sau mất gói.

Cách xử lý ở tầng giao thức:

1. Đưa sequence number vào header công khai và AAD.
2. Chỉ chuyển ciphertext đến cùng context theo thứ tự đã thỏa thuận.
3. Nếu phát hiện mất gói, lệch sequence hoặc context không còn đồng bộ, thiết lập context HPKE mới theo quy trình giao thức.
4. Không tự bỏ qua một record rồi tiếp tục dùng context cũ như thể sequence vẫn khớp.

Nếu hệ thống cần vận chuyển qua mạng có thể reorder/loss, phải có framing, retransmission hoặc cơ chế thiết lập context riêng phù hợp. Không coi HPKE tự cung cấp reliable delivery.

## 8. AAD được xác thực nhưng không được giữ bí mật

AAD là dữ liệu công khai. Người quan sát có thể đọc header/AAD ngay cả khi không thể đọc plaintext. AEAD chỉ bảo đảm dữ liệu AAD không bị sửa đổi mà không bị phát hiện khi recipient xác thực ciphertext.

Ví dụ AAD phù hợp:

- Message type = 2.
- Sequence number = 105.
- Protocol version = 1.
- Content type = application/json.

Ví dụ không phù hợp:

- Password.
- Access token.
- Private customer details.
- Nội dung cần giữ bí mật nhưng không được đưa vào plaintext.

Nếu metadata cần bí mật, hãy đưa nó vào plaintext để HPKE mã hóa. Có thể lặp lại một bản công khai của metadata trong AAD để ràng buộc nó với ciphertext, nhưng không được nhầm AAD với dữ liệu mã hóa.

Khi recipient giải mã, nếu ciphertext hoặc AAD bị thay đổi, AEAD tag không hợp lệ và Cipher ném lỗi xác thực, thường là AEADBadTagException. Ứng dụng không được sử dụng plaintext từ một lần giải mã thất bại.

## 9. info và AAD không thay thế xác thực danh tính sender

Một nhầm lẫn bảo mật quan trọng: info và AAD giúp ràng buộc dữ liệu với context hoặc ciphertext, nhưng không tự xác minh danh tính người gửi.

HPKEParameterSpec.of(...) tạo cấu hình mặc định ở **mode_base**. Base mode mã hóa cho recipient nhưng không xác thực danh tính sender. Bất kỳ ai có public key của recipient đều có thể tạo một ciphertext HPKE hợp lệ ở base mode.

Nếu nghiệp vụ cần xác thực sender, cân nhắc các mode theo RFC 9180:

| Mode | Tham số Java | Ý nghĩa |
|---|---|---|
| Base | HPKEParameterSpec.of(...) | Không xác thực danh tính sender |
| PSK | withPsk(psk, pskId) | Hai phía cùng dùng pre-shared key |
| Auth | withAuthKey(...) | Sender dùng private key của mình; recipient dùng public key tương ứng |
| AuthPSK | withPsk(...) và withAuthKey(...) | Kết hợp PSK với xác thực bằng asymmetric key |

Không phải mọi KEM đều hỗ trợ mode Auth/AuthPSK. Java API có thể nhận withAuthKey(), nhưng việc khởi tạo Cipher sẽ thất bại nếu KEM không hỗ trợ mode đó. Kiểm tra tài liệu provider và kiểm thử đúng bộ thuật toán.

RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy; định danh PSK phải được cấu hình nhất quán. Không lấy một mật khẩu người dùng ngắn rồi đưa thẳng vào withPsk() như một khóa ngẫu nhiên mạnh.

## 10. Những lỗi thường gặp khi dùng info và AAD

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Recipient giải mã thất bại ngay với ciphertext đầu tiên | info không khớp, private key không tương ứng, encapsulation sai, suite khác nhau hoặc ciphertext bị sửa | So sánh tham số HPKE và byte info; kiểm tra encapsulation/key/ciphertext |
| Chỉ thông điệp thứ hai trở đi thất bại | Sender/recipient gọi doFinal khác số lần hoặc sai thứ tự | Ghi sequence ở tầng giao thức và kiểm tra thứ tự xử lý |
| Chỉ một số loại message thất bại | AAD được serialize khác nhau hoặc message type không khớp | So sánh byte AAD thực tế ở hai phía |
| AEADBadTagException | Ciphertext hoặc AAD không đúng với context/sequence hiện tại | Không sử dụng plaintext; kiểm tra header, info, context và thứ tự |
| InvalidAlgorithmParameterException khi init | Provider không hỗ trợ KEM/KDF/AEAD hoặc mode đã chọn | Kiểm tra provider, key type và algorithm identifiers |
| InvalidKeyException khi init | Key type không phù hợp hoặc thiếu encapsulation phía recipient | Kiểm tra public/private key và withEncapsulation |
| IllegalStateException khi updateAAD | Cipher chưa init, sai mode hoặc AAD được gọi sau khi đã bắt đầu xử lý dữ liệu của message | Gọi updateAAD trước update/doFinal cho từng message |

Các giá trị byte cần được so sánh, không chỉ so sánh chuỗi hiển thị trong log. Hai chuỗi nhìn giống nhau vẫn có thể có encoding, normalization hoặc byte representation khác nhau.

## 11. Kiểm thử tính đúng đắn của context và AAD

Nên có các kiểm thử riêng để phát hiện lỗi cấu hình trước khi đưa HPKE vào giao thức thật:

| Thử nghiệm | Thao tác | Kết quả mong đợi |
|---|---|---|
| Round trip cơ bản | Cùng info, cùng suite, cùng encapsulation và plaintext | Recipient khôi phục đúng plaintext |
| Sai info | Recipient dùng info khác sender | Giải mã/xác thực thất bại |
| Sai AAD | Thay một byte AAD trước khi giải mã | AEAD tag không hợp lệ |
| Sai ciphertext | Thay một byte ciphertext | AEAD tag không hợp lệ |
| Sai encapsulation | Dùng encapsulation không thuộc context | Init hoặc giải mã thất bại |
| Sai message type | Recipient tạo AAD với type khác | Xác thực thất bại |
| Sai sequence | Giải mã record với thứ tự không khớp | Xác thực thất bại |
| Mất record | Bỏ một ciphertext rồi xử lý record sau trên cùng context | Context lệch sequence; cần khôi phục theo giao thức |
| Nhiều message đúng thứ tự | Gọi updateAAD/doFinal tuần tự trên cả hai Cipher | Các message giải mã đúng |

Không chỉ test một lần doFinal(). Tính năng dùng lại HPKE context cho nhiều message là điểm quan trọng của API và cần được kiểm thử trong đúng thứ tự.

## 12. Kiểm tra provider và khả năng tương thích

HPKEParameterSpec định nghĩa các hằng định danh chuẩn, nhưng đặc tả API cho phép một implementation HPKE chỉ hỗ trợ một phần các KEM/KDF/AEAD hoặc bổ sung định danh riêng. Không nên suy ra rằng mọi provider Java đều hỗ trợ mọi suite.

Trong Oracle JDK 26, release notes xác nhận triển khai HPKE và hỗ trợ các định danh KEM, KDF, AEAD được định nghĩa trong RFC 9180. Tài liệu SunJCE liệt kê HPKE, DHKEM cho các khóa EC/XDH, HKDF-SHA256/SHA384/SHA512. Tuy vậy, ứng dụng dùng provider bên thứ ba hoặc môi trường runtime tùy biến vẫn cần kiểm tra thực tế.

Có thể kiểm tra provider được chọn:

    Cipher hpke = Cipher.getInstance("HPKE");
    System.out.println("HPKE provider: " + hpke.getProvider().getName());

Nên dùng tên thuật toán chuẩn mà không ghim tên provider nếu không có lý do triển khai cụ thể. Nếu cần phần cứng bảo vệ khóa hoặc provider chuyên biệt, xác minh provider đó có hỗ trợ HPKE và đúng KEM/key type.

Một số lỗi phổ biến:

- NoSuchAlgorithmException: runtime không có provider đăng ký Cipher tên HPKE.
- InvalidKeyException: không có HPKE implementation hỗ trợ key type được cung cấp hoặc thiếu tham số bắt buộc.
- InvalidAlgorithmParameterException: suite hoặc mode không được provider chấp nhận.
- AEADBadTagException: xác thực thông điệp thất bại; nguyên nhân có thể là ciphertext, AAD, info hoặc sequence không khớp.

## 13. Các nguyên tắc bảo mật khi thiết kế giao thức

1. Dùng info để domain-separate context theo giao thức, phiên bản và mục đích sử dụng.
2. Cố định định dạng byte của info và AAD; tránh serialization không xác định thứ tự.
3. Dùng AAD cho header công khai cần xác thực, không dùng cho dữ liệu bí mật.
4. Đặt sequence number và message type trong AAD nếu chúng là một phần của framing.
5. Không tái sử dụng cùng context đồng thời từ nhiều thread nếu ứng dụng không tuần tự hóa thứ tự thao tác trên Cipher.
6. Giữ đúng thứ tự số lượng và thứ tự ciphertext ở recipient.
7. Thiết lập context mới nếu giao thức cần phục hồi sau mất gói hoặc lệch sequence.
8. Không xem info hoặc AAD là bằng chứng xác thực danh tính sender.
9. Chọn mode Auth/PSK phù hợp nếu cần xác thực sender; kiểm tra hỗ trợ KEM/provider.
10. Không ghi private key, PSK, plaintext hoặc dữ liệu nhạy cảm vào log.
11. Xử lý AEADBadTagException như lỗi xác thực; không trả dữ liệu chưa xác thực cho tầng nghiệp vụ.
12. Chọn KEM/KDF/AEAD theo chính sách mật mã và khả năng tương thích của các hệ thống giao tiếp.

## 14. Biên dịch và chạy trên JDK 26

HPKEParameterSpec và Cipher thuộc module java.base. Đây là API Java SE ổn định từ JDK 26, vì vậy không cần bật preview hoặc thêm module incubator.

Biên dịch:

    javac --release 26 -encoding UTF-8 -d out src/HpkeInfoExample.java

Chạy:

    java -cp out HpkeInfoExample

JDK 27 tiếp tục có HPKEParameterSpec và hỗ trợ Cipher HPKE. Khi triển khai, vẫn phải kiểm tra suite và provider cụ thể thay vì chỉ dựa vào phiên bản Java.

## Tài liệu chính thức

- [Java SE 26 API — HPKEParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html): định nghĩa info, PSK, authentication key, encapsulation, algorithm identifiers và hành vi nhiều lần doFinal.
- [Java SE 26 API — Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html): updateAAD, thứ tự đưa AAD vào AEAD và xác thực tag.
- [Oracle — JCA Reference Guide, Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): ví dụ HPKE với X25519, info, encapsulation và các mode xác thực.
- [Oracle — JDK 26 Release Notes, Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận HPKE Cipher và HPKEParameterSpec được bổ sung trong JDK 26.
- [Oracle — JDK 26 Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): hỗ trợ HPKE, DHKEM, HKDF và các dịch vụ mật mã của SunJCE.
- [Java SE 27 API — HPKEParameterSpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html): xác nhận API tiếp tục có trong JDK 27.
- [Oracle — JDK 27 JCA Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): hướng dẫn HPKE trong JDK 27.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): định nghĩa info trong key schedule, AAD trong Seal/Open, sequence counter, message ordering và các mode HPKE.

HPKE trong JDK 26 là API ổn định, không phải preview. Hãy dùng info một lần để định danh mục đích của context; dùng AAD cho metadata công khai của từng thông điệp; giữ byte representation và thứ tự message nhất quán ở hai phía. Cả hai đều không thay thế việc xác thực danh tính sender hoặc thiết kế framing/recovery của giao thức ứng dụng.
