# Xác thực event

## Xác thực event giải quyết vấn đề gì?

Khi application event rời khỏi một tiến trình Spring Modulith để đi qua Kafka, RabbitMQ hoặc một hệ thống tích hợp, consumer cần biết message thực sự đến từ producer được tin cậy và nội dung có còn nguyên vẹn hay không. Broker có thể xác thực kết nối của client, nhưng điều đó chưa tự chứng minh từng event trong message là do đúng module hoặc hệ thống nghiệp vụ tạo ra.

**Xác thực event** là quá trình kiểm tra danh tính nguồn phát và tính toàn vẹn của event trước khi consumer chấp nhận xử lý. Tùy mức độ tin cậy giữa các hệ thống, việc này có thể dùng HMAC, chữ ký số bất đối xứng hoặc một cơ chế xác thực message được chuẩn hóa.

Ví dụ, một consumer nhận OrderRefunded. Nếu một ứng dụng không có quyền phát sự kiện này có thể giả mạo payload, hệ thống có nguy cơ hoàn tiền sai, cập nhật read model sai hoặc kích hoạt quy trình nghiệp vụ trái phép. Xác thực event giúp phát hiện message không có chữ ký hợp lệ, bị sửa sau khi ký hoặc được ký bởi một producer không được phép phát loại event đó.

~~~mermaid
sequenceDiagram
    participant P as Trusted producer
    participant S as Signing component
    participant B as Message broker
    participant V as Consumer verifier
    participant H as Event handler

    P->>S: Event envelope
    S->>S: Canonicalize and sign
    S->>B: Publish signed event
    B->>V: Deliver message
    V->>V: Resolve key and verify signature
    alt Signature valid and producer authorized
        V->>H: Accept verified event
        H->>H: Apply business transaction
    else Invalid or unauthorized
        V-->>B: Reject or quarantine
    end
~~~

Xác thực event là một lớp bảo vệ của hợp đồng giao tiếp. Nó không thay thế việc kiểm tra quyền truy cập broker, phân quyền nghiệp vụ, validation payload hoặc idempotency ở consumer.

## Phân biệt authentication, integrity và authorization

Các khái niệm này liên quan nhưng trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Cách thực hiện |
|---|---|---|
| Authentication | Ai hoặc hệ thống nào đã phát event? | HMAC key identity, chữ ký số hoặc danh tính producer đã xác thực |
| Integrity | Nội dung event có bị thay đổi sau khi ký không? | Kiểm tra MAC hoặc chữ ký trên dữ liệu đã chuẩn hóa |
| Authorization | Producer này có được phép phát event type và tenant này không? | Policy theo producer, event type, tenant và destination |
| Confidentiality | Người không được phép có đọc được payload không? | TLS khi truyền, mã hóa dữ liệu khi lưu hoặc mã hóa payload |
| Replay protection | Một event cũ có bị phát lại để tạo tác động trái phép không? | Event ID, thời hạn hợp lệ, deduplication và policy replay |

Một chữ ký hợp lệ chứng minh message được tạo bởi bên giữ private key tương ứng và nội dung đã ký không bị sửa. Chữ ký không tự chứng minh producer được phép thực hiện mọi hành động nghiệp vụ. Consumer vẫn phải kiểm tra producer identity có quyền phát OrderRefunded hay chỉ được phát OrderPlaced.

Tương tự, TLS bảo vệ kết nối giữa client và broker. Nó không tự cung cấp chữ ký đầu cuối cho message sau khi broker chuyển tiếp qua nhiều thành phần. Nếu cần kiểm chứng nguồn phát qua nhiều hop, cần xác thực ở cấp event hoặc một cơ chế message security tương đương.

## Xác định trust boundary

Trước khi chọn thuật toán, hãy xác định event đi qua những ranh giới nào:

- Listener nội bộ trong cùng ApplicationContext.
- Adapter externalization của Spring Modulith.
- Broker dùng chung cho nhiều ứng dụng.
- Consumer thuộc một bounded context hoặc đội phát triển khác.
- Hệ thống bên ngoài tổ chức.
- Luồng export, archive, replay hoặc xử lý dữ liệu ngoại tuyến.

Trong cùng tiến trình, application event thường được phát qua ApplicationEventPublisher và listener nhận event từ cơ chế nội bộ của Spring. Nếu tiến trình, classpath và quyền thực thi đều thuộc cùng một miền tin cậy, ký mật mã cho từng event nội bộ có thể không đem lại nhiều giá trị.

Khi event được externalize ra broker hoặc hệ thống khác, trust boundary thay đổi. Message có thể được lưu, chuyển tiếp, replay hoặc đọc bởi nhiều ứng dụng. Đây là nơi cần xem xét xác thực producer, integrity, authorization và audit.

Không phải mọi event đều có cùng mức độ rủi ro. Event cập nhật thống kê có thể dùng policy đơn giản hơn event liên quan đến thanh toán, quyền truy cập, hoàn tiền hoặc thay đổi dữ liệu cá nhân. Hãy phân loại theo tác động nghiệp vụ và threat model.

## Chọn HMAC hay chữ ký số?

Hai lựa chọn phổ biến là xác thực bằng khóa bí mật dùng chung và chữ ký số bất đối xứng.

| Tiêu chí | HMAC | Chữ ký số bất đối xứng |
|---|---|---|
| Khóa ký | Bí mật dùng chung giữa bên ký và bên xác minh | Producer giữ private key; consumer dùng public key |
| Xác minh | Bất kỳ bên giữ secret đều có thể tạo MAC hợp lệ | Consumer có public key có thể xác minh nhưng không thể ký |
| Phân phối khóa | Phải bảo vệ secret ở mọi consumer được phép xác minh | Phân phối public key dễ hơn; private key cần bảo vệ nghiêm ngặt |
| Phù hợp | Nhóm producer/consumer nhỏ, cùng miền quản trị | Nhiều consumer, nhiều tổ chức hoặc cần phân tách quyền ký và xác minh |
| Rủi ro chính | Consumer bị lộ secret có thể giả mạo producer | Private key producer bị lộ có thể tạo chữ ký giả cho producer đó |

### HMAC

HMAC kết hợp một khóa bí mật với dữ liệu message để tạo message authentication code. Producer và consumer phải dùng cùng secret. HMAC phù hợp khi các bên cùng thuộc một miền quản trị và việc phân phối secret có thể kiểm soát.

Hạn chế quan trọng: mọi consumer giữ secret đều có khả năng tạo HMAC hợp lệ. Vì vậy, HMAC chứng minh message đến từ một thành viên trong nhóm giữ khóa, nhưng không phân biệt được chính xác thành viên nào đã ký nếu nhiều producer dùng chung một secret.

Nếu cần phân biệt producer, có thể cấp secret riêng cho từng producer và ánh xạ key ID sang producer identity. Không dùng một secret toàn hệ thống cho mọi producer nếu cần giới hạn thiệt hại khi một ứng dụng bị xâm nhập.

### Chữ ký số bất đối xứng

Với chữ ký số, producer ký bằng private key; consumer xác minh bằng public key. Consumer không thể dùng public key để tạo chữ ký mới. Cách này phù hợp khi nhiều consumer cần xác minh cùng một producer nhưng không được phép giả mạo producer đó.

Có thể dùng Ed25519 hoặc ECDSA/RSA theo tiêu chuẩn và thư viện được tổ chức chấp thuận. Hãy chọn thuật toán, kích thước khóa và định dạng chữ ký theo policy bảo mật của hệ thống; không tự thiết kế thuật toán mật mã.

Private key nên được giữ trong KMS, HSM hoặc secret management có kiểm soát. Không nhúng private key vào source code, image container, file cấu hình được commit hoặc payload event.

## Thiết kế envelope có thể xác thực

Một event envelope nên có metadata đủ để xác định nguồn phát, loại event, phiên bản schema và khóa xác minh:

~~~json
{
  "envelopeVersion": 1,
  "eventId": "9f8d8c24-5d75-4a93-8c3b-9d0f7b6b1f12",
  "eventType": "OrderRefunded",
  "schemaVersion": 2,
  "producerId": "payments-service",
  "tenantId": "tenant-42",
  "aggregateId": "order-781",
  "aggregateVersion": 14,
  "occurredAt": "2026-11-25T10:15:30Z",
  "issuedAt": "2026-11-25T10:15:31Z",
  "keyId": "payments-signing-2026-02",
  "algorithm": "HMAC-SHA256",
  "payload": {
    "refundId": "refund-991",
    "amount": "125000.00",
    "currency": "VND"
  },
  "signature": "base64url-signature"
}
~~~

Đây là envelope minh họa do ứng dụng thiết kế, không phải cấu trúc mặc định của Spring Modulith hay Kafka.

Các field quan trọng:

- envelopeVersion xác định cấu trúc envelope.
- eventId nhận diện sự kiện và hỗ trợ deduplication.
- eventType và schemaVersion xác định hợp đồng payload.
- producerId xác định danh tính logic của nguồn phát.
- tenantId xác định phạm vi tenant nếu ứng dụng multi-tenant.
- aggregateId và aggregateVersion hỗ trợ kiểm tra quan hệ nghiệp vụ và thứ tự.
- occurredAt là thời điểm nghiệp vụ xảy ra.
- issuedAt là thời điểm envelope được ký.
- keyId chọn khóa cần dùng để xác minh.
- algorithm xác định thuật toán trong tập được cho phép.
- payload chứa dữ liệu nghiệp vụ.
- signature là MAC hoặc chữ ký trên phần dữ liệu đã quy định.

Không để consumer tin producerId, tenantId hoặc algorithm chỉ vì các field này xuất hiện trong JSON. Chúng là dữ liệu chưa tin cậy cho đến khi chữ ký được xác minh và policy authorization được áp dụng.

## Ký đúng dữ liệu: canonicalization và domain separation

Producer và consumer phải xác minh chính xác cùng một chuỗi byte. Nếu producer ký JSON đã serialize nhưng consumer parse rồi serialize lại với thứ tự field, khoảng trắng hoặc cách biểu diễn số khác, hai bên có thể tạo ra byte khác nhau dù dữ liệu nhìn giống nhau.

Có hai cách phổ biến:

1. **Ký raw bytes:** ký đúng byte payload/envelope trước khi gửi và xác minh trên đúng byte nhận được. Không được có intermediary thay đổi nội dung.
2. **Ký canonical representation:** cả producer và consumer chuẩn hóa envelope theo một quy tắc được công bố, rồi ký/xác minh kết quả chuẩn hóa.

Với JSON, có thể dùng một chuẩn canonicalization như RFC 8785 hoặc một định dạng nhị phân có quy tắc encoding ổn định. Không tự tạo quy tắc chuẩn hóa tùy tiện nếu nhiều ngôn ngữ hoặc nền tảng cùng tham gia.

Dữ liệu được ký cần bao gồm toàn bộ field có ảnh hưởng đến cách consumer xử lý: event ID, event type, schema version, producer, tenant, aggregate metadata, timestamp và payload. Nếu bỏ tenantId khỏi phần ký, một intermediary có thể thay tenant mà chữ ký vẫn hợp lệ.

Không đưa chính field signature vào dữ liệu cần ký. Thay vào đó, xây dựng canonical envelope không có signature, nhưng bao gồm keyId, thuật toán được chọn và phiên bản envelope. Như vậy chữ ký được gắn với đúng key và đúng ngữ cảnh.

Nên dùng domain separation để tránh tái sử dụng chữ ký ở một giao thức khác. Ví dụ, thêm một prefix cố định như EVENT-ENVELOPE-V1 cùng delimiter trước canonical bytes. Prefix phải là hằng số của giao thức, không phải dữ liệu do message tự chọn.

Không cho phép message tự chỉ định một thuật toán tùy ý. Consumer phải có allowlist thuật toán được hỗ trợ và từ chối thuật toán yếu, không xác định hoặc bị cấm. Điều này ngăn một số kiểu downgrade và confusion attack.

## Ví dụ tạo và xác minh HMAC bằng Java

Đoạn code sau minh họa phần tạo MAC trên byte đã canonicalize. Việc serialize envelope, lấy secret từ kho khóa và quản lý key ID thuộc lớp tích hợp của ứng dụng.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class EventMac {

    private EventMac() {}

    public static byte[] sign(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        return mac.doFinal(canonicalBytes);
    }

    public static String encode(byte[] signature) {
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(signature);
    }

    public static boolean verify(
            byte[] secret,
            byte[] canonicalBytes,
            String encodedSignature) throws GeneralSecurityException {

        final byte[] supplied;

        try {
            supplied = Base64.getUrlDecoder().decode(encodedSignature);
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }

        byte[] expected = sign(secret, canonicalBytes);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Một số nguyên tắc trong ví dụ:

- Thuật toán được cố định là HmacSHA256 theo policy của ứng dụng.
- So sánh MAC bằng MessageDigest.isEqual thay vì so sánh chuỗi thông thường.
- Base64 URL-safe chỉ là cách biểu diễn byte signature, không phải cơ chế bảo mật.
- canonicalBytes phải được tạo theo cùng một quy tắc ở producer và consumer.
- secret phải được lấy từ kho khóa an toàn và không được log.
- key ID phải được ánh xạ tới đúng secret và producer identity được cấp quyền.

Không tự tạo secret bằng cách dùng một chuỗi dễ đoán hoặc hard-code vào ứng dụng. Tạo khóa ngẫu nhiên đủ độ mạnh qua KMS hoặc công cụ quản lý khóa được tổ chức phê duyệt.

## Ví dụ ký bằng Ed25519

Khi cần chữ ký bất đối xứng, Java Cryptography Architecture cung cấp API Signature. Ví dụ dưới đây minh họa cách ký bằng private key và xác minh bằng public key đã được tin cậy:

~~~java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class EventSignature {

    private EventSignature() {}

    public static byte[] sign(
            PrivateKey privateKey,
            byte[] canonicalBytes) throws GeneralSecurityException {

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(canonicalBytes);

        return signer.sign();
    }

    public static boolean verify(
            PublicKey publicKey,
            byte[] canonicalBytes,
            byte[] signatureBytes) throws GeneralSecurityException {

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);
        verifier.update(canonicalBytes);

        return verifier.verify(signatureBytes);
    }
}
~~~

Private key chỉ có ở producer hoặc dịch vụ ký được ủy quyền. Consumer chỉ cần public key đã được phân phối qua kênh tin cậy. Không lấy public key từ chính message rồi tin ngay; message có thể bị giả mạo cả khóa lẫn chữ ký.

Trong môi trường production, cần quản lý định dạng key, certificate hoặc public key registry, thời hạn hiệu lực, thu hồi và chuyển đổi thuật toán. Đoạn code chỉ minh họa API JCA, không phải một hệ thống quản lý khóa hoàn chỉnh.

## Quy trình xác minh ở consumer

Consumer nên thực hiện xác minh theo thứ tự có kiểm soát trước khi gọi handler nghiệp vụ:

1. Giới hạn kích thước message và kiểm tra framing cơ bản.
2. Parse phần metadata tối thiểu để lấy envelope version, key ID và thuật toán; xem toàn bộ giá trị là chưa tin cậy.
3. Kiểm tra thuật toán nằm trong allowlist và envelope version được hỗ trợ.
4. Tìm key trong key registry theo key ID và trạng thái hiệu lực.
5. Xác định producer identity gắn với key đó.
6. Tạo canonical bytes từ envelope theo đúng quy tắc, loại bỏ field signature.
7. Xác minh MAC hoặc chữ ký.
8. Kiểm tra producer có quyền phát event type, tenant và destination này không.
9. Kiểm tra timestamp, event ID, schema và các điều kiện chống replay.
10. Chỉ sau đó mới deserialize sâu, validate nghiệp vụ và chuyển event tới handler.

Có thể cần parse một phần envelope trước khi xác minh để biết key ID và version. Phần parse trước xác minh phải giới hạn kích thước, độ sâu và kiểu dữ liệu để tránh payload độc hại gây cạn tài nguyên. Không thực hiện side effect hoặc gọi module API trước khi xác minh thành công.

Nếu xác minh thất bại, không chuyển message tới handler nghiệp vụ. Ghi nhận lỗi bảo mật với metadata an toàn và áp dụng chính sách reject hoặc quarantine.

## Xác thực producer và phân quyền event

Sau khi chữ ký hợp lệ, consumer biết message được ký bởi một key cụ thể. Bước tiếp theo là kiểm tra quyền của producer.

Ví dụ policy:

| Producer identity | Event type được phép | Tenant/scope |
|---|---|---|
| orders-service | OrderPlaced, OrderConfirmed, OrderCancelled | Tenant thuộc phạm vi Orders |
| payments-service | PaymentCaptured, OrderRefunded | Tenant thuộc phạm vi Payments |
| shipping-service | ShipmentCreated, ShipmentDelivered | Tenant thuộc phạm vi Shipping |

Policy có thể được quản lý bằng cấu hình hoặc authorization service. Nên mặc định từ chối event type, producer hoặc tenant chưa được cấp quyền.

Không chỉ kiểm tra eventType. Một producer hợp lệ có thể được phép phát OrderConfirmed nhưng không được phép phát OrderRefunded. Tương tự, producer của tenant A không được phép phát event mang tenant B.

Nếu consumer hỗ trợ nhiều schema version, policy cần xác định producer nào được phép phát version nào trong thời gian chuyển đổi. Khi thu hồi quyền của producer, cần cập nhật key registry và authorization policy để event mới không còn được chấp nhận.

## Chống replay và phân biệt với duplicate delivery

Replay attack xảy ra khi kẻ tấn công lấy một event đã ký hợp lệ rồi phát lại để tạo tác động lần nữa. Tuy nhiên, hệ thống messaging cũng có retry và redelivery hợp lệ. Không thể chặn mọi message lặp chỉ bằng cách từ chối event có timestamp cũ.

Cần phân biệt:

- **Duplicate delivery:** broker hoặc adapter giao lại cùng event do retry, timeout hoặc acknowledgement không rõ ràng.
- **Replay vận hành:** operator chủ động phát lại event cũ để phục hồi consumer hoặc rebuild projection.
- **Replay attack:** bên không được phép phát lại một message hợp lệ nhằm tạo tác động trái phép hoặc vượt policy thời gian.

Các biện pháp phù hợp:

- Giữ event ID ổn định qua retry và replay.
- Dùng unique constraint hoặc inbox/processed-event store theo consumer để chống áp dụng tác động trùng.
- Lưu hash nội dung đã xác minh để phát hiện cùng event ID nhưng payload khác.
- Áp dụng cửa sổ thời gian theo issuedAt khi use case có yêu cầu freshness rõ ràng.
- Dùng nonce hoặc sequence khi giao thức thực sự cần một lần sử dụng và có cách xử lý retry hợp lệ.
- Kiểm tra trạng thái nghiệp vụ hiện tại trước khi chấp nhận replay có tác động.

Nếu một event hợp lệ được giao lại, consumer có thể xác minh chữ ký thành công rồi nhận ra event ID đã xử lý và bỏ qua tác động lần hai. Không nên coi duplicate hợp lệ là lỗi chữ ký.

Với event có thể nằm trong backlog nhiều giờ hoặc được replay sau nhiều ngày, cửa sổ timestamp quá ngắn sẽ làm mất khả năng xử lý hợp lệ. Hãy tách issuedAt khỏi occurredAt và đặt freshness policy theo từng loại event. Event ID deduplication phải được giữ đủ lâu để bao phủ khoảng thời gian retry/replay được cho phép.

## Quản lý và xoay vòng khóa

Khóa ký là tài sản bảo mật quan trọng. Quy trình quản lý khóa cần bao gồm:

- Sinh khóa bằng nguồn ngẫu nhiên an toàn hoặc KMS/HSM.
- Lưu secret/private key trong secret manager hoặc KMS, không lưu trong repository.
- Gắn key ID duy nhất, không tái sử dụng ID cho nội dung khóa khác.
- Giới hạn producer được dùng từng key.
- Phân phối public key qua kênh tin cậy.
- Theo dõi thời điểm tạo, kích hoạt, hết hạn và thu hồi.
- Có quy trình xoay vòng và xử lý message đang nằm trong backlog.
- Có phương án thu hồi khẩn cấp khi nghi ngờ khóa bị lộ.

Một quy trình rotation thường có giai đoạn chồng lấn:

1. Tạo key mới và phân phối public key hoặc secret tới consumer qua kênh bảo mật.
2. Consumer chấp nhận cả key cũ và mới trong thời gian chuyển tiếp.
3. Producer bắt đầu ký bằng key mới và ghi keyId mới vào envelope.
4. Theo dõi tỷ lệ event ký bằng key cũ để xác định backlog còn lại.
5. Ngừng chấp nhận key cũ sau khi hết thời gian hợp lệ hoặc sau khi xử lý backlog theo chính sách.
6. Thu hồi và xóa key cũ theo quy trình quản lý khóa.

Nếu key cũ bị lộ, có thể cần thu hồi ngay cả khi message đã ký bằng key đó còn trong backlog. Khi đó, quyết định chấp nhận event tồn đọng phải dựa trên mức độ ảnh hưởng và quy trình incident response; không tự động tin mọi message có chữ ký từ khóa đã bị thu hồi.

Không ghi secret, private key hoặc toàn bộ signature context nhạy cảm vào log. Key ID có thể được log để truy vết mà không tiết lộ nội dung khóa.

## Kết hợp với bảo mật Kafka và RabbitMQ

Xác thực event bảo vệ message ở cấp ứng dụng. Broker vẫn cần xác thực client và phân quyền destination.

Với Kafka, cân nhắc:

- TLS để bảo vệ kết nối và xác thực certificate khi dùng mTLS.
- SASL/SCRAM hoặc cơ chế xác thực được hạ tầng hỗ trợ.
- ACL giới hạn principal được phép WRITE vào topic và READ từ topic.
- Phân tách producer principal và consumer principal.
- Giới hạn quyền tạo topic, thay đổi cấu hình và quản trị consumer group.

Với RabbitMQ, cân nhắc:

- TLS hoặc mTLS cho kết nối.
- User/vhost và permission theo configure, write, read.
- Giới hạn quyền publish vào exchange và consume từ queue.
- Binding và routing topology do hạ tầng quản lý.
- Xoay vòng credential và giới hạn quyền theo ứng dụng.

Broker authentication xác định client nào được kết nối và thao tác trên destination. Chữ ký event xác định message nào được ký bởi producer sở hữu key. Hai lớp bổ sung cho nhau.

Không gửi credential broker trong event payload hoặc header. Không dùng event signature thay cho TLS; chữ ký không che giấu nội dung message và không bảo vệ mọi metadata trên đường truyền.

## Tích hợp xác thực với Spring Modulith

Spring Modulith cung cấp application event, listener, Event Publication Registry và cơ chế externalization thông qua các integration phù hợp. Các cơ chế này hỗ trợ tổ chức và theo dõi vòng đời giao event; không nên mặc định rằng chỉ cần dùng @Externalized hoặc Event Publication Registry là event đã được ký mật mã.

Với event nội bộ trong cùng ApplicationContext, có thể áp dụng validation và authorization tại ranh giới module theo yêu cầu nghiệp vụ. Với event externalized, lớp adapter hoặc integration cần thực hiện signing trước khi gửi và verification trước khi dispatch tới consumer tin cậy.

Một luồng tích hợp có thể được tổ chức như sau:

1. Module phát event nghiệp vụ trong transaction theo hợp đồng đã công bố.
2. Publication registry theo dõi publication theo cấu hình.
3. Externalization adapter tạo envelope, bổ sung producer metadata và ký canonical representation.
4. Broker nhận message qua kết nối đã xác thực và ACL phù hợp.
5. Consumer adapter nhận raw message, xác minh chữ ký và authorization.
6. Consumer mới chuyển event đã xác minh tới application handler.
7. Handler xử lý idempotent trong transaction nghiệp vụ riêng.

Có thể triển khai một signing component hoặc serializer wrapper tại producer và một verification component tại consumer. Nếu adapter hiện tại không cung cấp extension point phù hợp, cần tích hợp ở lớp messaging gateway hoặc producer/consumer wrapper. Giữ logic ký/xác minh ở ranh giới transport để handler nghiệp vụ không phải tự xử lý secret.

Event Publication Registry theo dõi trạng thái publication. Một publication hoàn tất chỉ cho biết bước giao tương ứng đã được ghi nhận theo semantics của integration; nó không tự chứng minh consumer downstream đã xác minh hoặc xử lý nghiệp vụ thành công.

## Xử lý event có chữ ký không hợp lệ

Event không hợp lệ có thể do lỗi cấu hình, key rotation không đồng bộ, payload bị sửa hoặc hành vi tấn công. Cần phân biệt nguyên nhân:

| Tình huống | Hướng xử lý |
|---|---|
| Signature không khớp | Reject hoặc quarantine; không gọi handler |
| Không tìm thấy key ID | Kiểm tra rotation/registry; giữ hoặc quarantine theo policy |
| Key đã bị thu hồi | Từ chối theo policy và ghi security audit |
| Thuật toán không được phép | Từ chối ngay |
| Envelope version không hỗ trợ | Quarantine để nâng cấp hoặc chuyển đổi |
| Producer không có quyền phát event type | Reject và ghi nhận authorization failure |
| Tenant không khớp phạm vi producer | Reject; điều tra khả năng giả mạo hoặc lỗi mapping |
| Event ID đã xử lý, chữ ký hợp lệ | Bỏ qua tác động trùng theo idempotency policy |

Không retry vô hạn một chữ ký sai. Lỗi signature không tự biến mất khi gửi lại cùng bytes. Nếu nguyên nhân là key registry tạm thời không sẵn sàng, có thể retry kiểm tra khóa có giới hạn. Nếu payload sai hoặc producer không được cấp quyền, cần quarantine và điều tra.

DLT hoặc security quarantine topic có thể giữ message để điều tra, nhưng phải giới hạn quyền đọc và retention. Không tự động replay message không hợp lệ sau khi chỉ sửa header; mọi thay đổi cần có quy trình xác minh nguồn và ký lại có thẩm quyền.

## Kiểm thử xác thực event

Kiểm thử phải chứng minh message hợp lệ được chấp nhận và message bị sửa hoặc không có quyền bị từ chối.

| Tình huống | Điều cần xác nhận |
|---|---|
| Signature hợp lệ | Consumer xác minh thành công và chuyển event tới handler |
| Payload bị sửa một field | Signature verification thất bại |
| Event type hoặc tenant bị sửa | Verification thất bại vì metadata thuộc phần được ký |
| Sai key ID | Không chọn nhầm key hoặc fallback sang key mặc định |
| Key đã hết hạn/thu hồi | Áp dụng đúng policy |
| Thuật toán không nằm trong allowlist | Reject trước khi xử lý nghiệp vụ |
| Signature sai encoding | Từ chối an toàn, không phát sinh exception không kiểm soát |
| Event ID đã xử lý | Xác minh chữ ký rồi bỏ qua tác động trùng |
| Cùng event ID, payload khác | Ghi nhận integrity/security incident |
| Retry hợp lệ | Giữ event ID và chữ ký tương ứng với cùng canonical content |
| Replay ngoài cửa sổ cho phép | Từ chối hoặc yêu cầu quy trình replay được cấp quyền |
| Rotation key | Event dùng key cũ/mới được xử lý theo giai đoạn chuyển đổi |
| Producer không được phép | Signature hợp lệ nhưng authorization vẫn thất bại |

Nên có test vector dùng chung giữa producer và consumer để bảo đảm canonicalization nhất quán. Kiểm thử thêm trường hợp JSON field order, Unicode, số thập phân, null và timestamp để tránh hai implementation tạo byte khác nhau.

Integration test nên xác nhận adapter ký đúng message, broker truyền nguyên metadata cần thiết và consumer xác minh trước handler. Mock verifier không chứng minh pipeline thực tế đang đặt verification ở đúng ranh giới.

## Quan sát và audit

Các log bảo mật nên ghi đủ thông tin để điều tra mà không làm lộ bí mật:

- Event ID và event type.
- Producer identity và key ID.
- Tenant hoặc destination ở dạng phù hợp.
- Kết quả signature verification.
- Kết quả authorization.
- Lý do reject/quarantine theo mã lỗi.
- Correlation ID và trace ID.
- Thời điểm nhận và consumer name.
- Key registry version hoặc policy version nếu cần.

Không ghi secret, private key, token, payload nhạy cảm hoặc byte signature đầy đủ nếu không có nhu cầu điều tra được phê duyệt. Event ID và key ID thường đủ để nối các log liên quan.

Metric nên nhóm theo producer, event type, consumer, kết quả verify và mã lỗi. Không dùng event ID hoặc tenant ID có cardinality lớn làm metric label nếu điều đó gây bùng nổ series.

Theo dõi:

- Tỷ lệ signature verification thất bại.
- Số event bị từ chối do producer không có quyền.
- Số key ID không tìm thấy hoặc đã bị thu hồi.
- Số event bị quarantine.
- Tỷ lệ duplicate hợp lệ bị bỏ qua.
- Tuổi message trong quarantine.
- Thời điểm và tiến độ rotation key.

Một đợt tăng signature failure có thể là lỗi rotation hoặc serialization, nhưng cũng có thể là dấu hiệu payload bị sửa hay producer bị xâm nhập. Cần liên kết metric với audit log và quy trình incident response.

## Quy trình triển khai xác thực event

Khi thêm xác thực cho một event contract, hãy thực hiện theo thứ tự:

1. Xác định trust boundary và mức độ rủi ro của event.
2. Xác định producer identity, consumer và quyền phát event type/tenant.
3. Chọn HMAC hoặc chữ ký số theo mô hình quản trị khóa.
4. Thiết kế envelope versioned và danh sách field phải được ký.
5. Chọn canonicalization hoặc ký raw bytes; công bố quy tắc cho mọi producer/consumer.
6. Quản lý key ID, lưu khóa an toàn, rotation và revocation.
7. Đặt signing tại producer adapter và verification tại consumer boundary.
8. Kiểm tra signature trước side effect, rồi mới áp dụng authorization và validation nghiệp vụ.
9. Kết hợp event ID, deduplication và replay policy để xử lý delivery lặp hợp lệ.
10. Thiết kế reject/quarantine, audit, metric và quy trình xử lý key compromise.
11. Kiểm thử tampering, algorithm downgrade, key rotation, replay và interoperability giữa các implementation.

Xác thực event giúp consumer kiểm chứng nguồn phát và tính toàn vẹn của message khi sự kiện đi qua ranh giới tiến trình. Khi chữ ký gắn với toàn bộ metadata quan trọng, khóa được quản lý an toàn, quyền producer được kiểm tra riêng và consumer chỉ xử lý sau khi xác minh thành công, hệ thống giảm nguy cơ event giả mạo hoặc bị sửa gây tác động nghiệp vụ trái phép.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Java Security Standard Algorithm Names — HMAC and Signature: https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html
- RFC 2104 — HMAC: Keyed-Hashing for Message Authentication: https://www.rfc-editor.org/rfc/rfc2104
- RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA): https://www.rfc-editor.org/rfc/rfc8032
- RFC 8785 — JSON Canonicalization Scheme: https://www.rfc-editor.org/rfc/rfc8785
