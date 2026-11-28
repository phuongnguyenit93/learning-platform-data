# Session key

> **Chương:** Phân loại key  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Session key là gì?

**Session key (khóa phiên)** là khóa mật mã được thiết lập hoặc dẫn xuất để bảo vệ hoạt động trao đổi dữ liệu trong **một phiên giao tiếp hoặc một phạm vi phiên được xác định**. Trong nhiều giao thức truyền thông bảo mật, session key là **khóa đối xứng có thời gian sử dụng tương đối ngắn**: hai bên dùng các khóa phiên tương ứng để mã hóa, giải mã và xác thực dữ liệu trao đổi.

Ví dụ: khi trình duyệt kết nối với website qua HTTPS, giao thức TLS thực hiện một quá trình bắt tay (handshake), xác thực máy chủ và thiết lập các bí mật cần thiết để hai đầu **dẫn xuất khóa bảo vệ lưu lượng**. Sau đó dữ liệu HTTP được bảo vệ bởi các khóa lưu lượng của kết nối, thường bằng thuật toán mã hóa có xác thực như AES-GCM hoặc ChaCha20-Poly1305.

Điểm cần nhớ: **session key mô tả vai trò và phạm vi sử dụng khóa**, không phải tên một thuật toán mật mã. Tùy giao thức, khóa phiên có thể được tạo ngẫu nhiên, được dẫn xuất từ một bí mật chung hoặc được thiết lập qua cơ chế thỏa thuận khóa. Không nên coi mọi session key là một chuỗi được một bên tự sinh rồi gửi nguyên dạng cho bên còn lại.

Session key giúp giải quyết ba nhu cầu:

1. **Bảo vệ lưu lượng của phiên:** dữ liệu truyền qua mạng được giữ bí mật và chống sửa đổi trái phép theo cơ chế đã chọn.
2. **Giới hạn phạm vi ảnh hưởng:** mỗi phiên hoặc mỗi hướng truyền có thể dùng khóa riêng, tránh dùng một khóa dài hạn cho mọi thông điệp.
3. **Hỗ trợ cơ chế thay khóa và tính bí mật chuyển tiếp:** nếu giao thức dùng thỏa thuận khóa tạm thời đúng cách, việc lộ khóa xác thực dài hạn về sau không nhất thiết làm lộ bản ghi lưu lượng cũ.

## 2. Session key nằm ở đâu trong cách phân loại khóa?

Một khóa có thể được phân loại theo **thuật toán** (đối xứng/bất đối xứng), **mục đích** (mã hóa dữ liệu, ký số, bọc khóa) và **thời gian/phạm vi sử dụng** (dài hạn/phiên). Các trục phân loại này không loại trừ nhau.

| Khái niệm | Đặc trưng | Vai trò điển hình |
| --- | --- | --- |
| **Session key** | Phục vụ một phiên, kết nối hoặc phạm vi giao tiếp được xác định; thường ngắn hạn | Bảo vệ bản ghi TLS, kênh SSH, liên kết bảo mật giữa dịch vụ |
| **Long-term key** (khóa dài hạn) | Được duy trì qua nhiều phiên hoặc được lưu trữ lâu hơn | Private key chứng thư TLS, khóa xác thực thiết bị |
| **Symmetric key** (khóa đối xứng) | Dùng trong thuật toán đối xứng | AES-GCM, ChaCha20-Poly1305, HMAC |
| **Private/public key** | Một cặp khóa bất đối xứng | Xác thực, chữ ký, thỏa thuận khóa trong giao thức thích hợp |
| **DEK** (Data Encryption Key) | Mã hóa dữ liệu trực tiếp | Mã hóa file, bản ghi cơ sở dữ liệu hoặc dữ liệu ứng dụng |
| **KEK** (Key Encryption Key) | Bọc/bảo vệ khóa khác | KMS/HSM bảo vệ DEK dài hạn hoặc theo chính sách |
| **PSK** (Pre-Shared Key) | Bí mật được hai bên biết trước hoặc được thiết lập trước phiên tiếp theo | Xác thực hay khôi phục phiên trong một số giao thức |

Một **session key thường là symmetric key**; ngược lại, không phải khóa đối xứng nào cũng là session key. Khóa AES mã hóa dữ liệu trong cơ sở dữ liệu suốt nhiều tháng có thể là DEK lâu dài, còn khóa AES bảo vệ lưu lượng một kết nối TLS là khóa phiên.

**Session key không đồng nhất với HTTP session ID, cookie, access token hay refresh token.** Những giá trị này liên quan tới danh tính hoặc trạng thái đăng nhập ở tầng ứng dụng. Một người dùng có thể giữ cookie đăng nhập nhiều ngày nhưng trình duyệt thiết lập nhiều kết nối TLS với các bộ khóa phiên khác nhau.

## 3. Khóa phiên được tạo và chia sẻ như thế nào?

Mục tiêu của quá trình thiết lập khóa là để **hai bên hợp lệ có thể tạo ra vật liệu khóa tương ứng**, trong khi người nghe lén đường truyền không tính được khóa phiên chỉ từ dữ liệu công khai của handshake.

### 3.1. Thỏa thuận khóa bằng bí mật tạm thời

Trong mô hình hiện đại như TLS 1.3 có thỏa thuận khóa Diffie–Hellman tạm thời trên đường cong elliptic (**ECDHE**), hai bên trao đổi **giá trị công khai tạm thời**, tính một bí mật chung rồi dùng **hàm dẫn xuất khóa (KDF)** để tạo các khóa và bí mật lưu lượng cần thiết.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: ClientHello + ECDHE key share công khai
    S-->>C: ServerHello + ECDHE key share công khai
    Note over C,S: Mỗi phía tính bí mật chung từ khóa tạm thời của mình
    Note over C,S: Dẫn xuất các traffic secret/key theo handshake
    S-->>C: Bằng chứng xác thực máy chủ + Finished
    C->>S: Finished
    C->>S: Dữ liệu ứng dụng được mã hóa có xác thực
    S-->>C: Dữ liệu ứng dụng được mã hóa có xác thực
~~~

Sơ đồ lược bỏ nhiều thông điệp, thứ tự bảo vệ và chi tiết của TLS 1.3 nhằm tập trung vào vai trò khóa phiên. **Khóa phiên dạng rõ không được gửi trực tiếp qua Internet** trong luồng ECDHE thông thường.

Đối với TLS 1.3, quá trình dẫn xuất khóa còn gắn với **nội dung handshake (transcript)** và hệ thống bí mật có cấu trúc; handshake keys và application traffic keys không phải cùng một khóa. Việc xác thực chứng thư máy chủ và xác minh handshake là cần thiết để chống tấn công đứng giữa; **ECDHE riêng lẻ không tự xác thực danh tính bên đối thoại**.

### 3.2. Dẫn xuất nhiều khóa từ một bí mật chung

Ngay cả khi bắt đầu từ một bí mật chung, giao thức thường không lấy một mảng byte duy nhất để dùng cho mọi mục đích. Nó sử dụng KDF có tách miền (domain separation) để tạo vật liệu khóa cho các hướng và giai đoạn riêng.

~~~text
Bí mật chung từ key agreement
             |
     Key schedule / HKDF
             |
     +-------+---------------------+
     |                             |
Handshake traffic secrets   Application traffic secrets
                                   |
                   +---------------+----------------+
                   |                                |
         Client -> Server key              Server -> Client key
                   |                                |
            Nonce/IV context                 Nonce/IV context
~~~

Đây là mô hình khái niệm. TLS 1.3 quy định key schedule và cách tạo nonce riêng; lập trình viên ứng dụng **không tự chọn các byte hoặc quy tắc dẫn xuất** khi sử dụng thư viện TLS chuẩn.

Việc tách khóa theo hướng truyền giúp hạn chế tái sử dụng cùng tổ hợp khóa và nonce giữa hai hướng. Giao thức cũng phải gắn thứ tự bản ghi, giới hạn sử dụng khóa và thông tin xác thực để tránh tráo đổi, sửa đổi hoặc phát lại trái phép trong phạm vi bảo đảm mà giao thức cung cấp.

### 3.3. Sinh khóa ngẫu nhiên rồi phân phối an toàn

Một số giao thức hoặc hệ thống nội bộ có thể chọn cách một bên sinh khóa phiên bằng **CSPRNG**, sau đó truyền khóa qua cơ chế bọc khóa hoặc kênh trao đổi được bảo vệ, có xác thực. Cách này đòi hỏi thiết kế giao thức đầy đủ, xử lý chống phát lại, danh tính và ranh giới tin cậy; không nên tự tạo giao thức chỉ bằng cách “RSA-encrypt một khóa AES rồi gửi đi”.

Trong ứng dụng thông thường, nên chọn **TLS/SSH/IPsec và thư viện đã được đánh giá**, thay vì tự thiết kế cơ chế thiết lập session key.

## 4. Vòng đời của session key

Session key cũng trải qua vòng đời **tạo, cấp phát, sử dụng, xoay vòng/ngừng dùng và hủy**, nhưng thường diễn ra tự động theo kết nối hoặc phiên bảo mật.

~~~mermaid
flowchart LR
    A[Khởi tạo handshake] --> B[Thỏa thuận / dẫn xuất vật liệu khóa]
    B --> C[Xác thực và xác nhận handshake]
    C --> D[Kích hoạt khóa lưu lượng]
    D --> E[Mã hóa và giải mã bản ghi]
    E --> F{Đổi khóa hay kết thúc?}
    F -->|Key update / rekey| G[Dẫn xuất khóa lưu lượng mới]
    G --> E
    F -->|Đóng kết nối| H[Ngừng dùng và giải phóng khóa phiên]
~~~

### 4.1. Tạo và kích hoạt

Mỗi bên thiết lập bí mật theo giao thức; chỉ bắt đầu dùng khóa lưu lượng khi trạng thái handshake hợp lệ. Với TLS, **việc kiểm tra chứng thư, danh tính máy chủ và thông điệp xác nhận handshake** là điều kiện bảo mật quan trọng.

Một client bỏ qua xác minh chứng thư có thể trao đổi khóa bảo mật với **máy chủ giả mạo**. Khi ấy dữ liệu vẫn được mã hóa trên đường truyền nhưng mã hóa hướng tới sai đối tượng.

### 4.2. Sử dụng

Khóa phiên thường được giữ **trong bộ nhớ của tiến trình hoặc thành phần mật mã**, không ghi vào cơ sở dữ liệu ứng dụng. Phía nhận dùng khóa và thông tin nonce/sequence number thích hợp để giải mã, kiểm tra tính toàn vẹn và xác thực bản ghi.

Mỗi thuật toán/chế độ có giới hạn về số bản ghi, lượng dữ liệu và cách dùng nonce. Đặc biệt, nếu dùng AES-GCM thì **không được lặp lại cùng nonce dưới cùng một khóa**; các thư viện TLS tiêu chuẩn thực hiện quy tắc tạo nonce và đếm bản ghi theo giao thức.

### 4.3. Key update, rekey và cryptoperiod

**Cryptoperiod** của session key là khoảng thời gian khóa được phép dùng cho các thao tác cụ thể. Việc kết thúc kết nối thường chấm dứt khả năng dùng khóa phiên đó cho lưu lượng mới, nhưng một giao thức còn có thể thay khóa ngay khi kết nối đang hoạt động.

- **Key update:** thay vật liệu khóa lưu lượng trong một kết nối theo cơ chế của giao thức; ví dụ TLS 1.3 hỗ trợ cập nhật traffic keys.
- **Rekey / rehandshake:** thiết lập lại các khóa hoặc phiên bảo mật tùy giao thức; tên gọi và thao tác cụ thể khác nhau giữa TLS, SSH, IPsec.
- **Session termination:** khi kết nối đóng, thư viện ngừng dùng khóa và giải phóng vật liệu nhạy cảm theo khả năng của runtime.

Một phiên ứng dụng kéo dài hàng giờ không nhất thiết dùng một khóa lưu lượng duy nhất suốt thời gian đó. Ngược lại, **session resumption** có thể tận dụng bí mật khôi phục phiên đã lưu để thiết lập kết nối mới; không nên suy ra rằng đóng kết nối sẽ xóa mọi bí mật phục vụ việc khôi phục phiên.

### 4.4. Hủy và giảm tồn tại của khóa dạng rõ

Giữ khóa phiên trong RAM vẫn có rủi ro nếu tiến trình bị chiếm, ghi memory dump hoặc bị debug không kiểm soát. Hệ thống nên hạn chế quyền đối với tiến trình, cấm ghi khóa vào log, giảm lưu trữ bản sao vật liệu khóa và dựa vào thư viện mật mã để quản lý vùng nhớ nhạy cảm.

Trong Java, garbage collection **không bảo đảm xóa ngay byte khóa khỏi bộ nhớ**. Không được tuyên bố đã hủy an toàn chỉ nhờ gán biến bằng null; các thư viện mã hóa, KMS/HSM và nền tảng được chọn phải đáp ứng yêu cầu bảo vệ phù hợp.

## 5. Session key, public/private key và forward secrecy

TLS là ví dụ hữu ích để phân biệt **khóa xác thực dài hạn** và **khóa lưu lượng ngắn hạn**.

| Thành phần | Vai trò | Cần giữ bí mật? | Tuổi thọ điển hình |
| --- | --- | --- | --- |
| Public key trong chứng thư máy chủ | Xác minh danh tính/chữ ký của máy chủ theo chuỗi tin cậy | Không; cần đảm bảo nguồn gốc và tính đúng đắn | Theo vòng đời khóa/chứng thư |
| Private key của máy chủ | Tạo chữ ký xác thực handshake hoặc chức năng được cấp phép | **Có**, thường được bảo vệ bởi KMS/HSM/keystore phù hợp | Có thể qua nhiều kết nối |
| Khóa riêng ECDHE tạm thời | Tính bí mật chung cho handshake | **Có**, chỉ tồn tại tạm thời theo cơ chế giao thức | Ngắn, gắn với handshake |
| Traffic key / session key | Mã hóa và xác thực các bản ghi theo hướng truyền | **Có** | Theo kết nối hoặc giai đoạn cập nhật khóa |
| Resumption PSK / ticket secret | Hỗ trợ khôi phục phiên theo cơ chế TLS | **Có** | Theo chính sách ticket/resumption; có thể vượt thời gian của một kết nối |

**Forward secrecy (tính bí mật chuyển tiếp)** nói tới mục tiêu: nếu khóa xác thực dài hạn của máy chủ bị lộ **sau khi các phiên đã kết thúc**, kẻ tấn công chỉ có bản ghi lưu lượng cũ và khóa dài hạn đó **không thể tự động tính lại traffic key của phiên cũ**, khi phiên đã dùng thỏa thuận khóa tạm thời an toàn và các bí mật tạm thời đã được loại bỏ đúng cách.

**Ví dụ đối chiếu:**

- **TLS 1.3 với (EC)DHE:** dùng chia sẻ khóa tạm thời cho đường dẫn thông thường, hỗ trợ forward secrecy với các giả định bảo mật tương ứng.
- **TLS 1.2 dùng RSA key transport kiểu cũ:** nếu attacker ghi lại handshake và sau này lấy được private key RSA, họ có thể giải mã pre-master secret, rồi tính khóa phiên cũ; đây là lý do mô hình đó không có forward secrecy.
- **TLS 1.3 khôi phục bằng PSK:** có những chế độ khôi phục; khi có đóng góp (EC)DHE mới thì có thể giữ forward secrecy tốt hơn. Nếu chỉ dùng PSK mà không có đóng góp (EC)DHE, không nên mặc định phiên có cùng mức forward secrecy.

Forward secrecy **không** bảo vệ trước việc kẻ tấn công chiếm máy chủ khi phiên đang chạy, trích xuất traffic key từ RAM, lấy plaintext ở endpoint hoặc chiếm được bí mật tạm thời của chính phiên. Nó cũng không thay thế xác thực danh tính hay kiểm soát truy cập ứng dụng.

## 6. Session key trong TLS, SSH, IPsec và ứng dụng

| Công nghệ | Session key được dùng thế nào? | Điểm quản lý cần chú ý |
| --- | --- | --- |
| **TLS 1.3 / HTTPS** | Dẫn xuất các traffic key để bảo vệ bản ghi theo hướng truyền và giai đoạn | Kiểm tra chứng thư, chính sách phiên bản/cipher suite, ticket, key update |
| **SSH** | Thỏa thuận khóa và dẫn xuất khóa đối xứng/MAC cho kênh SSH | Xác thực host key, giới hạn rekey, quản lý phiên và quyền truy cập |
| **IPsec / IKE** | Thiết lập Security Association và khóa bảo vệ lưu lượng | Thời hạn SA, rekey, thuật toán và khả năng phối hợp hai bên |
| **Messaging / ứng dụng tùy biến** | Có thể dẫn xuất khóa cho phiên hoặc nhóm trao đổi | Tránh tự phát minh giao thức, cần xác thực hai đầu, chống replay và kiểm soát khóa |

Một kết nối **WebSocket qua WSS** thường dựa vào TLS của lớp truyền tải; ứng dụng không cần tự tạo một session key AES riêng chỉ vì WebSocket tồn tại. Nếu yêu cầu **mã hóa đầu cuối (end-to-end encryption)** vượt ranh giới máy chủ trung gian, bài toán sẽ khác và cần giao thức E2EE được thiết kế riêng.

## 7. KMS và HSM liên quan đến session key ra sao?

**KMS (Key Management Service)** quản lý khóa, chính sách quyền, các thao tác mật mã và audit. **HSM (Hardware Security Module)** là phần cứng giúp giữ và thao tác với một số khóa trong ranh giới bảo vệ được thiết kế chuyên dụng.

Trong kiến trúc TLS phổ biến:

1. **Private key dài hạn** dùng cho việc xác thực máy chủ có thể được bảo vệ bằng HSM, keystore hoặc dịch vụ ký phù hợp.
2. Các đầu TLS thực hiện **handshake và key schedule** để tạo traffic key; thư viện TLS quản lý session key trong ngữ cảnh kết nối.
3. KMS/HSM **không nhất thiết sinh, lưu hoặc ghi audit từng traffic key** của mọi kết nối TLS.
4. Hệ thống an toàn cần kết hợp chính sách cho private key, chứng thư, phiên TLS, cấu hình giao thức, kiểm soát quyền ứng dụng và quan sát bất thường.

Vì vậy, câu “đã dùng KMS/HSM nên mọi session key đều nằm trong HSM” **không mặc nhiên đúng**. Phải kiểm tra kiến trúc TLS của sản phẩm cụ thể, khả năng offload mật mã, nơi giữ khóa phiên và chính sách về key export.

### Session key và envelope encryption khác nhau thế nào?

**Envelope encryption** thường dùng DEK để mã hóa dữ liệu lưu trữ, sau đó bọc DEK bằng KEK do KMS bảo vệ. DEK có thể dùng cho một bản ghi, một file hoặc một nhóm dữ liệu, với yêu cầu đọc dữ liệu cũ kéo dài.

**Session key** chủ yếu bảo vệ giao tiếp trong một phiên hoặc giai đoạn truyền thông. Một bản ghi ứng dụng có thể được bảo vệ bằng **DEK khi nằm trong database** và bằng **TLS traffic key khi đang truyền qua mạng**. Hai lớp này có mục đích, trạng thái và cryptoperiod khác nhau.

~~~mermaid
flowchart LR
    C[Client] -->|TLS traffic key bảo vệ truyền tải| A[Ứng dụng]
    A -->|DEK mã hóa dữ liệu| DB[(Cơ sở dữ liệu)]
    A -->|Wrap / Unwrap DEK theo quyền| KMS[KMS giữ KEK]
    KMS -.->|Không cần lưu từng TLS traffic key| A
~~~

Sơ đồ thể hiện **hai lớp bảo vệ độc lập**. Nếu endpoint ứng dụng có quyền giải mã dữ liệu, tại thời điểm xử lý hợp lệ ứng dụng vẫn có thể thấy plaintext; TLS và encryption at rest không tự thay thế cho kiểm tra quyền nghiệp vụ.

## 8. Ví dụ Java: sử dụng TLS mà không tự quản lý traffic key

Với ứng dụng Java gọi HTTPS, cách an toàn thông thường là để **JSSE/JDK TLS implementation** xác thực phía đối tác và điều khiển khóa phiên. Lập trình viên có thể quan sát phiên TLS mà **không cần truy xuất secret key dạng rõ**.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLSession;

public class TlsSessionDemo {
    public static void main(String[] args) throws Exception {
        // Dùng cấu hình TLS và trust store mặc định của JDK.
        // Java HttpClient thực hiện handshake và kiểm tra hostname/certificate.
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        SSLSession session = response.sslSession()
                .orElseThrow(() ->
                        new IllegalStateException("No TLS session"));

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("TLS protocol: " + session.getProtocol());
        System.out.println("Cipher suite: " + session.getCipherSuite());
        // Không in, lưu hoặc cố trích xuất session key.
    }
}
~~~

Đoạn code yêu cầu kết nối mạng để chạy và chỉ nhằm minh họa cách ứng dụng sử dụng thư viện TLS chuẩn. Giao thức/cipher suite thực tế phụ thuộc vào JDK, cấu hình và máy chủ. Một cipher suite TLS 1.3 có thể có dạng **TLS_AES_128_GCM_SHA256**; tên này không có nghĩa toàn bộ ứng dụng sử dụng một khóa AES duy nhất.

**Không vô hiệu hóa kiểm tra chứng thư hoặc hostname** để “sửa lỗi kết nối”. Nếu cần trust store nội bộ, phải phân phối chứng thư CA đúng quy trình và xác định rõ danh tính máy chủ tin cậy. Không tự dựng handshake bằng RSA/AES, không log TLS session secrets, và không can thiệp vào key schedule trừ khi đang phát triển giao thức chuyên dụng có đánh giá an ninh nghiêm ngặt.

## 9. Vận hành và kiểm toán session key

Các khóa phiên có thể xuất hiện với số lượng rất lớn và được thay đổi liên tục. Vì vậy, mô hình quản lý thường khác với khóa chủ trong KMS:

| Đối tượng | Nên quản lý/giám sát | Không nên làm |
| --- | --- | --- |
| **Khóa xác thực dài hạn** | Nguồn tạo, phạm vi quyền, bảo vệ private key, cert expiry, rotation, audit | Hard-code hoặc chia sẻ private key qua nhiều hệ thống không kiểm soát |
| **Handshake và chính sách TLS** | TLS version, cipher suites, chứng thư/hostname, tình trạng xác thực | Chấp nhận mọi chứng thư hoặc cho phép giao thức yếu ngoài chính sách |
| **Traffic key / session key** | Thuật toán, key update/rekey, giới hạn sử dụng, an toàn bộ nhớ | Ghi raw key vào log, metrics, traces, core dump không bảo vệ |
| **Session ticket / PSK khôi phục** | Vòng đời bí mật, mã hóa/bảo vệ ticket, giới hạn thời hạn, chống replay | Coi ticket/PSK là dữ liệu công khai hoặc cho phép dùng vô hạn |
| **Ứng dụng kinh doanh** | Quyền người dùng, danh tính workload, request/audit liên quan | Coi TLS hợp lệ là bằng chứng người dùng có quyền xem mọi dữ liệu |

Hệ thống có thể log **phiên bản TLS, cipher suite, lỗi handshake, thông tin chứng thư không nhạy cảm, kết quả xác thực và request ID**, tuân theo chính sách dữ liệu cá nhân. **Không log nội dung session key hoặc các bí mật bắt tay**. Các cơ chế xuất TLS key log cho mục đích debug là nhạy cảm cao vì có thể cho phép giải mã lưu lượng đã ghi; chỉ dùng trong môi trường được kiểm soát và xử lý, xóa theo chính sách.

Một số dấu hiệu nên cảnh báo: tỷ lệ handshake thất bại tăng đột ngột, chứng thư sắp hết hạn, máy chủ quay về TLS/cipher suite yếu, nhiều client bỏ xác minh chứng thư, hoạt động bất thường liên quan tới private key hoặc tài liệu key log bị lộ.

## 10. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Vì sao nguy hiểm hoặc sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Session key là private key của server.” | Hai khóa có vai trò và vòng đời khác nhau | Private key thường xác thực; traffic key bảo vệ dữ liệu phiên |
| “HTTP cookie đăng nhập chính là session key.” | Nhầm tầng ứng dụng với khóa mật mã | Cookie/session ID quản lý trạng thái hoặc xác thực, không mặc nhiên mã hóa lưu lượng |
| “Hai bên cần gửi secret key trực tiếp cho nhau.” | Có thể lộ khóa trên đường truyền | Giao thức có thể dùng ECDHE và KDF để dẫn xuất khóa |
| “Mã hóa bằng khóa phiên thì không cần xác thực server.” | Có thể thiết lập khóa với kẻ đứng giữa | Handshake cần xác thực danh tính và bằng chứng hợp lệ |
| “Một khóa AES dùng chung cho mọi kết nối đều ổn.” | Phạm vi ảnh hưởng lớn, rủi ro dùng lại nonce và khó cô lập sự cố | Dùng giao thức thiết lập khóa phiên và chính sách phù hợp |
| “Đóng TLS connection là mọi bí mật đều đã biến mất.” | Resumption secret hoặc bản sao bộ nhớ có thể còn | Quản lý ticket, cache, PSK và bộ nhớ theo chính sách |
| “Forward secrecy bảo vệ kể cả khi endpoint bị chiếm.” | Kẻ tấn công có thể lấy traffic key/plaintext đang sống | Cần bảo vệ endpoint và giới hạn truy cập cùng lúc |
| “KMS tự quản lý mọi traffic key của TLS.” | Nhiều hệ thống TLS tạo/lưu key trong tiến trình | Xác minh ranh giới HSM/KMS và thư viện TLS đang dùng |
| “Thay chứng thư là tự động thay mọi session key đã tạo.” | Kết nối đang sống và ticket/PSK cần chính sách riêng | Quản lý cert, kết nối hiện tại, key update và resumption |
| “Dùng TLS thì dữ liệu trong database đã được mã hóa an toàn.” | TLS chỉ bảo vệ dữ liệu trên kênh truyền | Dùng DEK/KEK và cơ chế encryption at rest khi cần |

## 11. Tình huống thực tế: API thanh toán qua HTTPS

Giả sử ứng dụng di động gọi API thanh toán của doanh nghiệp qua HTTPS. Máy chủ sử dụng TLS 1.3, private key xác thực máy chủ được quản lý theo chính sách khóa dài hạn, còn ứng dụng lưu token đăng nhập để gọi API.

**Khi thiết lập kết nối:**

1. Ứng dụng mở kết nối đến đúng hostname và xác minh chuỗi chứng thư hợp lệ.
2. Hai bên thực hiện handshake; trong mô hình có ECDHE, bí mật tạm thời được kết hợp trong key schedule để tạo các traffic key.
3. Ứng dụng gửi request qua kênh TLS; traffic key bảo vệ dữ liệu trên đường truyền.
4. API tiếp tục kiểm tra **access token, quyền người dùng và quyền thanh toán** ở tầng nghiệp vụ.

**Khi kết nối lâu dài:** thư viện và cấu hình TLS phải tuân thủ giới hạn sử dụng khóa, bộ đếm bản ghi và cơ chế cập nhật khóa được hỗ trợ. Nhiều kết nối khác nhau có thể có vật liệu khóa phiên khác nhau; không lưu traffic key vào bảng session của ứng dụng.

**Khi thay chứng thư hoặc private key máy chủ:** nhóm vận hành cần triển khai chứng thư/khóa mới, kiểm tra chuỗi tin cậy, cân nhắc ảnh hưởng đến kết nối còn hoạt động và session resumption. Việc thay private key **khác** với đổi traffic key của từng kết nối.

**Khi một máy ứng dụng bị xâm nhập:** đối tượng tấn công có thể đọc dữ liệu tại endpoint hoặc khóa phiên đang trong bộ nhớ. Cần xử lý sự cố, giới hạn truy cập và xác định phạm vi ảnh hưởng; không nên chỉ dựa vào forward secrecy để khẳng định dữ liệu không bị lộ.

**Khi dữ liệu thanh toán được lưu:** API nên dùng cơ chế mã hóa dữ liệu lưu trữ thích hợp, chẳng hạn DEK bọc bằng KEK trong KMS, cùng phân quyền và audit. Đây là một vòng đời khóa **riêng** với TLS session key.

## 12. Checklist cho kỹ sư

- [ ] Đã phân biệt session key với private key, public key, DEK, KEK, PSK và cookie/token chưa?
- [ ] Đã dùng giao thức và thư viện bảo mật được duy trì thay vì tự thiết kế key exchange chưa?
- [ ] TLS/SSH/IPsec có xác thực đúng bên đối tác và chọn thuật toán/chế độ được phép không?
- [ ] Đã hiểu thỏa thuận khóa tạm thời, key schedule, khóa theo hướng và giới hạn sử dụng không?
- [ ] Có nguy cơ reuse nonce, vượt giới hạn bản ghi hoặc không thực hiện rekey/key update cần thiết không?
- [ ] Khóa dài hạn được bảo vệ bởi keystore/KMS/HSM thích hợp và có chính sách rotation không?
- [ ] Session ticket, resumption PSK, thời hạn lưu giữ và chống replay đã được xét chưa?
- [ ] Không có raw session key, handshake secret hay plaintext trong logs, tracing hoặc bản dump công khai chứ?
- [ ] Có kiểm soát quyền nghiệp vụ độc lập với việc kết nối TLS đã xác thực không?
- [ ] Khi xử lý sự cố, đã xét khóa đang sống trong RAM, bí mật tạm thời và bí mật khôi phục phiên chưa?
- [ ] Đã tách bảo vệ dữ liệu truyền tải (session key) khỏi bảo vệ dữ liệu lưu trữ (DEK/KEK) chưa?

## 13. Câu hỏi tự kiểm tra

**1. Session key là khóa đối xứng hay bất đối xứng?**  
Trong phần lớn giao thức bảo vệ lưu lượng, session key là khóa đối xứng. Khóa bất đối xứng có thể được dùng trong quá trình xác thực/thỏa thuận để thiết lập các khóa phiên.

**2. Hai bên có nhất thiết phải gửi khóa phiên dạng rõ qua mạng không?**  
Không. Ví dụ, trong handshake sử dụng ECDHE, hai bên trao đổi giá trị công khai và tính bí mật chung để dẫn xuất khóa; khóa lưu lượng dạng rõ không cần truyền trực tiếp.

**3. Session key có phải cookie đăng nhập của người dùng?**  
Không. Cookie là thành phần quản lý trạng thái/xác thực ứng dụng; traffic key TLS bảo vệ dữ liệu trên kết nối. Một cookie có thể tồn tại qua nhiều kết nối TLS khác nhau.

**4. Forward secrecy có nghĩa là gì?**  
Đó là thuộc tính giúp bảo vệ khóa lưu lượng của các phiên cũ trước việc khóa xác thực dài hạn bị lộ về sau, khi giao thức dùng thỏa thuận khóa tạm thời an toàn và loại bỏ bí mật tạm thời đúng cách. Nó không bảo vệ dữ liệu khi endpoint đã bị chiếm và attacker lấy được plaintext hoặc khóa phiên đang hoạt động.

**5. Vì sao không dùng một session key mãi mãi cho mọi kết nối?**  
Vì phạm vi ảnh hưởng sẽ lớn, khó cách ly khi lộ khóa, có nguy cơ vượt giới hạn sử dụng mật mã và làm suy yếu mục tiêu tách biệt phiên.

**6. KMS có phải lưu giữ từng session key TLS mới an toàn không?**  
Không nhất thiết. KMS/HSM thường bảo vệ khóa dài hạn; thư viện TLS quản lý các traffic key theo kết nối. Cần xác minh kiến trúc thực tế và chính sách của sản phẩm.

**7. Đóng kết nối có xóa hết bí mật liên quan tới phiên?**  
Không thể mặc định. Bản sao trong RAM, session ticket và bí mật khôi phục phiên có thể tồn tại lâu hơn; cần thiết kế chính sách tương ứng.

## Ghi nhớ

**Session key là khóa mật mã gắn với một phiên hoặc phạm vi giao tiếp cụ thể, thường là khóa đối xứng có thời gian sử dụng ngắn để bảo vệ lưu lượng.** Trong các giao thức hiện đại, khóa phiên thường được **dẫn xuất sau handshake**, tách theo hướng truyền và thay theo chính sách hoặc giới hạn giao thức. Thiết kế an toàn đòi hỏi xác thực hai đầu, bảo vệ khóa dài hạn, sử dụng thuật toán/nonce đúng, kiểm soát cryptoperiod, xử lý resumption, tránh lộ khóa trong bộ nhớ và log, đồng thời phân biệt khóa bảo vệ truyền tải với DEK/KEK của dữ liệu lưu trữ. KMS/HSM, IAM và kiểm toán bổ trợ cho việc bảo vệ session key theo đúng ranh giới trách nhiệm của mỗi thành phần.
