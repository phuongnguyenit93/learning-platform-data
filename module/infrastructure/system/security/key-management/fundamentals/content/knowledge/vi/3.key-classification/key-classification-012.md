# Static key (Khóa tĩnh)

## 1. Static key là gì?

**Static key (khóa tĩnh)** là khóa mật mã có **vật liệu khóa được duy trì và tái sử dụng qua nhiều lần thao tác, thông điệp hoặc phiên làm việc**, thay vì được tạo mới cho từng phiên ngắn hạn. Trong thuật ngữ của các giao thức thỏa thuận khóa, **static key pair** thường chỉ cặp khóa công khai/riêng tư có tuổi thọ dài hơn một lần bắt tay; cặp khóa đó có thể được dùng để xác thực danh tính hoặc tham gia thiết lập bí mật chung theo giao thức.

Ví dụ:

- Một dịch vụ có private key dùng để **ký nhiều giao dịch**; các hệ thống khác xác minh chữ ký bằng public key tương ứng.
- Một ứng dụng dùng **AES key** được quản lý bởi KMS để mã hóa nhiều đối tượng trong một khoảng thời gian; từng lần mã hóa vẫn cần nonce/IV tuân thủ quy tắc của thuật toán.
- Hai hệ thống dùng **pre-shared key (PSK)** tồn tại qua nhiều lần kết nối để xác thực hoặc làm đầu vào cho cơ chế dẫn xuất khóa phiên.
- Một **Key Encryption Key (KEK)** trong KMS bảo vệ nhiều **Data Encryption Key (DEK)** và có lịch xoay vòng riêng.

Trong chương **Phân loại key** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, phân loại *static* mô tả chủ yếu **thời gian tồn tại và cách tái sử dụng khóa**. Nó không tự nói khóa là đối xứng hay bất đối xứng, dài bao nhiêu bit, có được phép xuất ra ngoài hay dùng thuật toán nào.

> **Không đồng nhất "static key" với "hard-coded key".** Static key có thể được sinh ngẫu nhiên, lưu trong HSM/KMS, phân quyền chặt chẽ và xoay vòng theo chính sách. Hard-coded key là khóa được nhúng cố định vào mã nguồn hoặc artifact; đó là **cách quản lý khóa rủi ro**, không phải định nghĩa của static key.

## 2. Static key khác ephemeral key như thế nào?

**Ephemeral key (khóa tạm thời)** được tạo cho một phiên, lần bắt tay, đối tượng hoặc phạm vi sử dụng ngắn rồi được loại bỏ khi hết nhu cầu. Ranh giới "một phiên" tùy giao thức: không có quy tắc rằng mọi ephemeral key chỉ tồn tại đúng vài giây hoặc mọi static key phải tồn tại nhiều năm.

| Tiêu chí | Static key | Ephemeral key |
|---|---|---|
| Thời gian tồn tại | Thường qua nhiều giao dịch/phiên | Thường trong một phiên hoặc phạm vi ngắn |
| Tái sử dụng | Có thể được tái sử dụng theo thiết kế và chính sách | Thường không tái sử dụng ngoài phạm vi đã định |
| Trường hợp điển hình | Private key ký số, khóa danh tính máy chủ, KEK, PSK lâu dài | Cặp khóa (EC)DHE cho một lần bắt tay, khóa phiên mới sinh |
| Quản lý | Có key ID/version, lưu trữ, phân quyền, xoay vòng và thu hồi | Cần sinh đúng, giới hạn sử dụng và xóa bí mật kịp thời |
| Ảnh hưởng khi bị lộ | Có thể tác động nhiều giao dịch/phiên hoặc dữ liệu lâu dài | Thường giới hạn vào phạm vi mà khóa tạm thời bảo vệ, tùy giao thức |
| Phụ thuộc vào giao thức | Có; cách dùng static key quyết định tính an toàn | Có; chỉ gọi tên ephemeral không tự đảm bảo forward secrecy |

Ví dụ, **static private key** của máy chủ dùng để *xác thực* một phiên TLS có thể cùng tồn tại với **ephemeral (EC)DHE keys** dùng để *thiết lập* khóa phiên. Khi giao thức được thiết kế đúng, việc lộ static signing key **về sau** không tự làm lộ nội dung những phiên cũ đã được bảo vệ bằng (EC)DHE, với giả định bí mật phiên và khóa ephemeral đã được bảo vệ/xóa. Ngược lại, nếu một hệ thống dùng **cùng khóa đối xứng tĩnh trực tiếp** để mã hóa dữ liệu nhiều phiên và khóa đó bị lộ, các bản mã cũ được thu thập có thể trở nên dễ giải mã.

Cần phân biệt thêm:

- **Key lifetime**: thời gian khóa tồn tại hoặc được giữ để dùng.
- **Cryptoperiod**: khoảng thời gian được phép sử dụng khóa cho mục đích nhất định; có thể tách giai đoạn tạo dữ liệu mới với giai đoạn đọc dữ liệu cũ.
- **Session key**: khóa dành cho bảo vệ một phiên; thường ngắn hạn, nhưng tên gọi "session" không tự chứng minh nó sinh ngẫu nhiên hoặc bảo đảm tính bí mật về phía trước.
- **Rotated key**: khóa/phiên bản mới được đưa vào hoạt động. Một static key được rotate vẫn là static key trong khoảng sử dụng của mỗi phiên bản.

## 3. Những dạng static key thường gặp

| Loại | Vai trò | Điều quan trọng khi bảo vệ |
|---|---|---|
| **Static symmetric key** | Mã hóa/giải mã bằng thuật toán đối xứng như AES-GCM | Giới hạn lượng dữ liệu và thời gian dùng; quản lý nonce, bản sao khóa và phạm vi dữ liệu |
| **Static private signing key** | Tạo chữ ký số lâu dài cho dịch vụ/tổ chức | Ngăn export trái phép; phân quyền sign; thu hồi tin cậy khi bị lộ |
| **Static public/private identity key** | Gắn danh tính vào một chủ thể qua chứng chỉ hoặc trust store | Xác thực public key; bảo vệ private key; duy trì vòng đời chứng chỉ |
| **Static key-agreement key** | Tham gia thỏa thuận khóa qua nhiều phiên trong giao thức cho phép | Đánh giá ảnh hưởng khi lộ private key và cách giao thức tạo forward secrecy |
| **Static PSK** | Bí mật chung giữa các bên trong cơ chế xác thực/thiết lập khóa | Cấp phát bảo mật, tách miền tin cậy, thay PSK cho các bên và kiểm soát chia sẻ |
| **Long-lived KEK** | Bọc hoặc mã hóa nhiều DEK trong envelope encryption | KMS/HSM, chính sách wrap/unwrap, rotation, rewrap và audit |
| **Long-lived DEK** | Mã hóa một tập dữ liệu theo thời gian | Rủi ro tập trung dữ liệu; cần chiến lược phân tách và mã hóa lại khi thay DEK |

### 3.1. Static key đối xứng

Cùng một key có thể tham gia nhiều lần mã hóa. Việc này **không tự sai**: các chế độ mã hóa được thiết kế để dùng một khóa cho nhiều thông điệp trong giới hạn xác định. Nhưng **các đầu vào phụ trợ, giới hạn sử dụng và chính sách bảo vệ** quyết định việc tái sử dụng có an toàn hay không.

Chẳng hạn, với **AES-GCM**, khi dùng cùng khóa cho nhiều thông điệp, mỗi lần mã hóa phải có **nonce duy nhất trong phạm vi khóa đó**. Tái sử dụng nonce với cùng key có thể phá tính bí mật và tính xác thực. Nonce không nhất thiết cần bí mật, nhưng **không thể tùy tiện dùng cố định** chỉ vì khóa là static.

### 3.2. Static key bất đối xứng

Một static key pair thường có **private key được bảo vệ** và **public key được phân phối có xác thực**. Static private key có thể dùng để ký số hoặc thỏa thuận khóa theo giao thức cụ thể. Không nên suy ra mọi private key đều dùng được cho cả ký và giải mã: **Ed25519** là cơ chế ký số, **X25519** là cơ chế trao đổi khóa, và **RSA-PSS / RSA-OAEP** phục vụ các mục đích khác nhau.

Một public key có thể được gắn với chủ thể qua chứng chỉ. Kiểm tra chữ ký bằng public key về mặt toán học **chưa đủ** nếu bên nhận không xác nhận nó thuộc đúng danh tính được tin cậy.

### 3.3. Static KEK và DEK trong envelope encryption

Khi dữ liệu nhiều đối tượng được mã hóa bằng các DEK riêng, KMS có thể giữ một KEK tương đối lâu và dùng nó để bảo vệ những DEK đó. KEK là static key theo cách sử dụng qua nhiều thao tác, trong khi DEK có thể ngắn hạn hoặc dài hạn tùy chính sách.

Trong một thiết kế thường gặp, **DEK chỉ tồn tại ở dạng rõ trong bộ nhớ ứng dụng trong thời gian cần thiết**; hệ thống lưu encrypted DEK kèm bản mã dữ liệu. Khi đổi KEK, có thể **rewrap** encrypted DEK mà không cần mã hóa lại bản rõ dữ liệu, nếu cơ chế và quyền truy cập cho phép. Khi thay **chính DEK**, thường phải mã hóa lại dữ liệu tương ứng.

## 4. Static key trong giao thức thiết lập khóa và forward secrecy

**Forward secrecy** (trong bối cảnh phiên liên lạc) là thuộc tính giúp bảo vệ các khóa phiên quá khứ khỏi việc bị giải lộ chỉ vì **khóa dài hạn** bị chiếm đoạt ở thời điểm sau đó, dưới các giả định bảo mật của giao thức. Static key **không nhất thiết** làm mất forward secrecy, cũng như ephemeral key **không tự động** bảo đảm forward secrecy nếu được tích hợp sai.

Xét ba mô hình khái niệm:

| Mô hình | Ý tưởng | Tính chất/rủi ro |
|---|---|---|
| **Dùng một khóa tĩnh trực tiếp làm session encryption key** | Nhiều phiên cùng mã hóa dưới cùng bí mật dài hạn | Lộ khóa về sau có thể làm lộ dữ liệu các phiên cũ đã ghi lại |
| **Static-static DH** | Hai bên dùng khóa thỏa thuận lâu dài, cùng cặp giá trị qua nhiều lần | Nếu bí mật chung không được đổi/không có bảo vệ bổ sung, có nguy cơ ảnh hưởng nhiều phiên khi khóa dài hạn bị lộ |
| **(EC)DHE với khóa ephemeral và xác thực bằng static signing key** | Bí mật phiên được dẫn xuất từ các khóa ephemeral; static signing key xác thực lần bắt tay | Có thể đạt forward secrecy đối với việc lộ khóa xác thực dài hạn về sau, nếu giao thức bảo đảm các điều kiện cần thiết |

~~~mermaid
flowchart TD
    A["Static key: xác thực danh tính"] --> C["Bắt tay được xác thực"]
    B["Ephemeral key pair: trao đổi bí mật phiên"] --> C
    C --> D["KDF dẫn xuất session keys"]
    D --> E["Mã hóa dữ liệu phiên"]
    F["Kết thúc phiên"] --> G["Xóa bí mật ephemeral / session theo khả năng hệ thống"]
~~~

Sơ đồ minh họa **một nhóm giao thức kết hợp static và ephemeral**, không khẳng định mọi giao thức đều dùng đúng thứ tự hoặc cơ chế như vậy. Việc **xác thực transcript, chống can thiệp, tạo entropy đúng và không tái sử dụng ephemeral secret sai cách** là những điều kiện quan trọng để tránh tấn công người đứng giữa và suy yếu bảo mật phiên.

**Ví dụ TLS:** Trong các cấu hình TLS hiện đại sử dụng cơ chế (EC)DHE, khóa private dài hạn gắn với chứng chỉ thường dùng để **ký/xác thực bắt tay**, còn bí mật mã hóa phiên được dẫn xuất từ quá trình trao đổi khóa tạm thời. Vì thế khi đánh giá một static key, phải hỏi: **nó xác thực danh tính hay trực tiếp tạo khóa mã hóa dữ liệu?**

## 5. Lợi ích và đánh đổi khi dùng static key

Static key hữu ích vì các hệ thống thường cần một danh tính mật mã ổn định hoặc một khóa có khả năng được tham chiếu qua nhiều giao dịch.

**Lợi ích:**

- **Danh tính ổn định:** đối tác biết public key hoặc chứng chỉ của dịch vụ để xác minh nhiều chữ ký.
- **Quản lý tập trung:** KMS/HSM lưu các phiên bản khóa, áp chính sách IAM và tạo nhật ký sử dụng.
- **Giảm chi phí phân phối:** không phải gửi một bí mật mới cho mọi thao tác, đặc biệt khi dùng envelope encryption.
- **Hỗ trợ giải mã lịch sử:** có thể giữ khóa/phiên bản cũ theo chính sách để đọc dữ liệu hợp lệ.

**Đánh đổi:**

- **Phạm vi tác động lớn:** một khóa dùng cho quá nhiều tenant, đối tượng hoặc môi trường sẽ trở thành điểm lỗi tập trung.
- **Thời gian phơi lộ dài:** khóa tồn tại lâu tạo nhiều cơ hội bị truy cập sai, sao lưu nhầm hoặc lộ qua log.
- **Khó thu hồi triệt để:** bản sao key material đã rời HSM/KMS không thể bị thu hồi từ xa bằng một cờ trạng thái.
- **Khó chuyển đổi:** dữ liệu, chứng chỉ, verifier hoặc khách hàng có thể vẫn phụ thuộc phiên bản cũ.
- **Nguy cơ do tái sử dụng:** chẳng hạn tái dùng AES-GCM nonce dưới cùng static key.

Vì vậy quyết định chọn static key nên dựa trên **mục đích**, **cryptoperiod**, **phạm vi dữ liệu**, **khả năng xoay vòng**, **cơ chế thu hồi** và **khoản thiệt hại nếu khóa bị lộ**.

## 6. Vòng đời của một static key

Static key vẫn phải đi qua đầy đủ vòng đời quản lý khóa:

~~~mermaid
flowchart LR
    A["Sinh khóa / import an toàn"] --> B["Cấp phát & cấu hình quyền"]
    B --> C["Lưu trong KMS/HSM hoặc kho phù hợp"]
    C --> D["Sử dụng, giám sát và kiểm toán"]
    D --> E["Tạo phiên bản mới / rotation"]
    E --> F["Ngừng dùng khóa cũ cho thao tác mới"]
    F --> G["Thu hồi / disable theo chính sách"]
    G --> H["Lưu giữ có kiểm soát / hủy"]
    E --> D
~~~

| Giai đoạn | Câu hỏi vận hành với static key |
|---|---|
| **Generation** | Khóa được sinh bằng CSPRNG hay HSM đáng tin cậy? Kích thước và thuật toán phù hợp mục đích? |
| **Provisioning** | Public key/chứng chỉ, PSK hoặc quyền sử dụng KMS được cấp qua kênh được xác thực? |
| **Storage** | Private/symmetric key nằm ở đâu? Có xuất được ra ngoài không? Có bản sao backup, cache, image, log không? |
| **Usage** | Dịch vụ nào được encrypt/decrypt/sign/verify/wrap/unwrap? Có giới hạn tenant, môi trường và số lượng thao tác? |
| **Rotation** | Có thể tạo phiên bản mới và chuyển phụ thuộc mà không gián đoạn? Old key còn cần để đọc dữ liệu lịch sử bao lâu? |
| **Revocation** | Khi lộ khóa, có thể chặn ngay thao tác trong KMS và cập nhật tất cả verifier không? |
| **Destruction** | Trước khi xóa vĩnh viễn, đã xử lý dữ liệu mã hóa, backup và yêu cầu pháp lý/lưu giữ chưa? |

### Cryptoperiod và phiên bản khóa

**Cryptoperiod** là khoảng được quy định cho một mục đích sử dụng khóa; có thể phân biệt:

1. **Originator-use period:** khoảng được phép dùng khóa để tạo bản mã/chữ ký mới.
2. **Recipient-use period:** khoảng cần giữ khả năng giải mã/xác minh dữ liệu hoặc thông điệp cũ.

Không nhất thiết hai khoảng trùng nhau. Một KEK/DEK cũ có thể được giữ **chỉ để giải mã dữ liệu còn hợp lệ** trong thời gian chuyển đổi, nhưng không tiếp tục được dùng để mã hóa dữ liệu mới. Các cơ chế trạng thái cụ thể phụ thuộc KMS và chính sách triển khai.

Không có chu kỳ rotation cố định áp dụng cho mọi static key. Một khóa ký liên quan chứng chỉ, một KEK bảo vệ DEK và một khóa phiên có yêu cầu khác nhau. Chọn lịch thay khóa theo rủi ro, khả năng tự động hóa, giới hạn thuật toán và nhu cầu kinh doanh.

## 7. Thiết kế an toàn với static key trong KMS/HSM

**Key Management Service (KMS)** cung cấp API và chính sách quản lý khóa, vòng đời, kiểm toán, phiên bản và thao tác mật mã. **Hardware Security Module (HSM)** là thiết bị/môi trường phần cứng được thiết kế để bảo vệ key material và thực hiện các phép toán mật mã. KMS có thể sử dụng HSM bên dưới; không đồng nghĩa mọi dịch vụ KMS đều cung cấp cùng chính sách hoặc tính năng.

Các biện pháp thiết kế thiết thực:

1. **Sinh trong miền tin cậy:** ưu tiên KMS/HSM hoặc CSPRNG phù hợp. Không lấy một chuỗi khó nhớ, UUID, timestamp hay mật khẩu ngắn rồi coi là static AES key.
2. **Không hard-code bí mật:** giữ private key, PSK và symmetric key ngoài source code, Docker image, tài liệu và repository. Để ứng dụng tham chiếu tới key ID/alias và lấy quyền thao tác theo danh tính workload.
3. **Hạn chế xuất key material:** sử dụng API sign/decrypt/unwrap tại KMS/HSM khi có thể; với DEK dạng rõ bắt buộc ở ứng dụng để mã hóa dữ liệu, giới hạn thời gian lưu trong bộ nhớ và không ghi log.
4. **Áp dụng least privilege:** tách quyền create, encrypt, decrypt, sign, rotate, disable và delete. Không trao quyền xóa/đổi policy cho mọi dịch vụ chỉ cần ký hoặc giải mã.
5. **Phân tách phạm vi:** môi trường production/test, tenant hoặc lớp dữ liệu nhạy cảm cần các khóa/phân quyền riêng tùy rủi ro.
6. **Thiết kế rotation trước khi phát hành:** bản mã mang key ID/version, lưu metadata cần thiết và có lộ trình xử lý dữ liệu cũ.
7. **Kiểm toán:** ghi danh tính gọi, thao tác, kết quả, thời điểm, key ID/version và ngữ cảnh được phép; tránh ghi private key, plaintext hoặc DEK dạng rõ.
8. **Bảo vệ backup và khôi phục:** kiểm kê bản sao và thường xuyên diễn tập đọc dữ liệu lịch sử sau rotation. Không được tự động hủy khóa nếu bản mã hợp lệ còn phụ thuộc.
9. **Giám sát lạm dụng:** cảnh báo đột biến số lần decrypt, sign hoặc unwrap, thay chính sách bất thường và sử dụng khóa từ danh tính/môi trường không dự kiến.

**Cảnh báo:** Khóa nằm trong HSM vẫn có thể bị **lạm dụng thao tác** nếu principal có quyền sign/decrypt quá rộng hoặc bị chiếm quyền. Không xuất private key chỉ giải quyết một phần của bài toán; IAM, xác thực, audit và bảo vệ dữ liệu đầu ra vẫn bắt buộc.

## 8. Static key và nguy cơ tái sử dụng nonce/IV

Một sai lầm nghiêm trọng là nhầm rằng static key phải đi cùng **static IV/nonce**. Thực tế, đây là hai đối tượng khác nhau.

Với AES-GCM:

~~~text
encrypt(key = K, nonce = N1, plaintext = P1, aad = A1)
    -> ciphertext1 + tag1

encrypt(key = K, nonce = N2, plaintext = P2, aad = A2)
    -> ciphertext2 + tag2
~~~

K có thể được dùng lại theo cryptoperiod, nhưng **N1 và N2 phải khác nhau dưới cùng K**. Đặc biệt:

- Không đặt cứng nonce toàn số 0 rồi dùng cho mọi lần mã hóa.
- Không khởi động lại bộ đếm nonce từ 0 cho cùng khóa sau khi service restart.
- Không để hai instance độc lập vô tình cấp cùng nonce cho cùng khóa.
- Nếu tạo nonce ngẫu nhiên, phải đánh giá **xác suất va chạm và giới hạn số thông điệp**; nonce 96 bit ngẫu nhiên không là bảo đảm tuyệt đối khi lưu lượng rất lớn.
- Nếu dùng counter, phải bảo đảm cấp phát **duy nhất, bền vững qua restart** và phân tách rõ giữa các writer, hoặc sử dụng một thiết kế đã được kiểm chứng.
- Khi dữ liệu cần chống tráo đổi giữa tenant/bản ghi, có thể đưa metadata liên quan vào **Additional Authenticated Data (AAD)** và kiểm tra nó khi giải mã.

Các chế độ mã hóa khác có yêu cầu khác với GCM; phải làm theo đặc tả thuật toán và thư viện đang dùng.

## 9. Ví dụ Java: một static AES key cho nhiều bản ghi

Ví dụ dùng **Java Cryptography Architecture (JCA)** để minh họa một khóa AES đã được cung cấp cho lớp mã hóa và dùng cho hai bản ghi, mỗi bản ghi có nonce riêng. Trong hệ thống thực tế, `SecretKey` nên được cấp qua giải pháp quản lý khóa/DEK được bảo vệ bằng KMS theo chính sách; ví dụ **không** triển khai việc lưu khóa bền vững hay quy trình cấp phát.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class StaticAesKeyExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_SIZE = 12;   // 96-bit nonce
    private static final int TAG_SIZE_BITS = 128;

    // Một đối tượng đóng gói nonce riêng và ciphertext chứa authentication tag.
    public record EncryptedRecord(byte[] nonce, byte[] ciphertextWithTag) {}

    public static EncryptedRecord encrypt(
            SecretKey staticKey, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_SIZE];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            staticKey,
            new GCMParameterSpec(TAG_SIZE_BITS, nonce)
        );
        cipher.updateAAD(aad);

        return new EncryptedRecord(nonce, cipher.doFinal(plaintext));
    }

    public static byte[] decrypt(
            SecretKey staticKey, EncryptedRecord record, byte[] aad)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            staticKey,
            new GCMParameterSpec(TAG_SIZE_BITS, record.nonce())
        );
        cipher.updateAAD(aad);

        // Nếu key, nonce, AAD hoặc ciphertext/tag sai, xác thực thất bại.
        return cipher.doFinal(record.ciphertextWithTag());
    }

    public static void demo(SecretKey keyFromManagedService)
            throws GeneralSecurityException {

        byte[] aad1 = "tenant=7;record=A".getBytes(StandardCharsets.UTF_8);
        byte[] aad2 = "tenant=7;record=B".getBytes(StandardCharsets.UTF_8);

        EncryptedRecord a = encrypt(
            keyFromManagedService,
            "Ho so A".getBytes(StandardCharsets.UTF_8),
            aad1
        );
        EncryptedRecord b = encrypt(
            keyFromManagedService,
            "Ho so B".getBytes(StandardCharsets.UTF_8),
            aad2
        );

        byte[] restoredA = decrypt(keyFromManagedService, a, aad1);
        byte[] restoredB = decrypt(keyFromManagedService, b, aad2);

        if (!Arrays.equals(restoredA, "Ho so A".getBytes(StandardCharsets.UTF_8))
                || !Arrays.equals(restoredB, "Ho so B".getBytes(StandardCharsets.UTF_8))) {
            throw new IllegalStateException("Data mismatch");
        }
    }
}
~~~

**Bài học từ ví dụ:**

- **Static key** ở đây là tham số `keyFromManagedService` được giữ nguyên qua hai phép mã hóa, **không** phải một chuỗi hard-coded.
- Hai phép mã hóa sinh nonce khác nhau theo mô hình xác suất; ví dụ ngắn phù hợp để minh họa. Ở hệ thống quy mô lớn, phải thiết kế chiến lược **bảo đảm duy nhất của nonce và giới hạn sử dụng khóa** theo yêu cầu GCM.
- Nonce, ciphertext và tag có thể được lưu cùng bản ghi; AAD phải được xây dựng lại chính xác khi giải mã. Không lưu khóa rõ cùng bản mã.
- Trong mô hình envelope encryption, ứng dụng thường nhận **DEK dạng rõ trong bộ nhớ** trong thời gian cần xử lý; KEK trong KMS quản lý lớp bảo vệ DEK.
- Ứng dụng phải lưu **key ID/version** cho từng đối tượng hoặc nhóm đối tượng để biết khóa nào giải mã khi rotation. Đoạn mã chỉ minh họa phép toán, chưa bao gồm metadata, persistence, truy cập KMS hay xử lý rotation.

**Lưu ý kỹ thuật:** `SecretKey` kiểu đối tượng trong Java không tự đảm bảo vật liệu bí mật nằm trong HSM hoặc có thể bị xóa khỏi JVM; các cam kết này phụ thuộc provider, cách cấp phát và thiết kế hệ thống.

## 10. Ví dụ kiến trúc: static KEK và DEK trong kho lưu trữ nhiều tenant

Một dịch vụ lưu tài liệu theo tenant có thể áp dụng **envelope encryption**:

~~~mermaid
flowchart TB
    C["Ứng dụng đã xác thực"] -->|"Xin quyền wrap/unwrap"| K["KMS: KEK phiên bản v2"]
    C -->|"AES-GCM với DEK"| E["Ciphertext + nonce + tag"]
    K -->|"Bọc DEK"| W["Encrypted DEK"]
    E --> S["Kho tài liệu"]
    W --> S
    M["Key ID/version + tenant + AAD"] --> S
~~~

Giả sử **KEK v2** bảo vệ nhiều DEK và là static key trong khoảng một chu kỳ hoạt động. Mỗi DEK có thể gắn với một đối tượng hoặc phạm vi dữ liệu; ứng dụng không được xem một KEK dùng lâu là lý do để dùng chung DEK trên toàn hệ thống.

Mỗi bản ghi nên đủ thông tin để đọc lại đúng cách:

~~~yaml
# Metadata minh họa, không phải định dạng KMS bắt buộc
tenantId: tenant-7
recordId: doc-402
keyId: kms-documents
keyVersion: v2
encryptedDataKey: "<base64 DEK da duoc boc>"
nonce: "<base64 nonce AES-GCM>"
ciphertextWithTag: "<base64 ban ma va tag>"
algorithm: AES-256-GCM
~~~

**Khi xoay KEK:** tạo v3 và chuyển hoạt động wrap mới sang v3; rewrap encrypted DEK theo kế hoạch; theo dõi đối tượng nào vẫn dùng v2; chỉ disable/hủy v2 khi không còn phụ thuộc hợp lệ. **Khi DEK bị lộ:** xem xét tạo DEK mới và mã hóa lại dữ liệu chịu ảnh hưởng; chỉ rewrap một DEK bị lộ không làm DEK đó trở lại bí mật.

**Khi private key ký số bị lộ:** không áp dụng logic rewrap DEK cho bài toán này. Phải thay cặp khóa ký, thu hồi chứng chỉ hoặc trust với public key cũ và cập nhật các hệ thống xác minh.

## 11. Static key bị lộ: tác động và quy trình ứng phó

Vì static key thường được dùng lại, phạm vi thiệt hại cần được xác định theo **tất cả hoạt động và dữ liệu đã phụ thuộc vào phiên bản đó**.

| Tình huống | Hậu quả có thể có | Việc cần làm |
|---|---|---|
| Static AES DEK lộ cùng dữ liệu mã hóa | Bản mã cũ đã được sao chép có thể bị giải mã | Dừng dùng DEK, lập danh sách dữ liệu, sinh DEK mới và mã hóa lại theo phạm vi |
| Static private signing key lộ | Kẻ tấn công có thể ký giả; verifier cũ tiếp tục tin public key | Thu hồi tin cậy/chứng chỉ, thay khóa và đồng bộ verifier |
| Static PSK bị tiết lộ | Có thể mạo danh bên dùng PSK hoặc ảnh hưởng khóa phiên tùy giao thức | Thay PSK, thu hồi danh tính bị ảnh hưởng và đánh giá phiên/dữ liệu cũ |
| KEK trong KMS còn an toàn nhưng quyền unwrap bị lạm dụng | Tài khoản bị chiếm quyền có thể lấy DEK và tiếp cận bản rõ | Thu hồi quyền, điều tra thao tác KMS, đánh giá dữ liệu có thể bị lộ |
| KEK material bị đánh cắp và encrypted DEK cũ đã bị lấy | Rewrap KEK không vô hiệu hóa các bản sao cũ trong tay đối phương | Đánh giá thay DEK/mã hóa lại và giới hạn tác động tương lai |

Một quy trình ứng phó gồm:

1. **Nhận diện** key ID/version, thuật toán, usage, chủ sở hữu và các hệ thống phụ thuộc.
2. **Cô lập** principal hoặc endpoint bị lạm dụng; thực thi disable/revoke trong KMS/HSM/verifier khi cần.
3. **Sinh khóa thay thế**, cấp quyền tối thiểu, chuyển thao tác mới sang phiên bản mới.
4. **Chuyển dữ liệu và mức tin cậy**: rewrap DEK, re-encrypt dữ liệu, thay chứng chỉ/public key hoặc cập nhật token verification tùy loại khóa.
5. **Kiểm tra phụ thuộc cũ**: backup, cache, client ngoại tuyến, các phiên đã thiết lập và log có vật liệu khóa.
6. **Kiểm toán và xử lý hủy** theo chính sách, tránh làm mất khả năng đọc dữ liệu hợp lệ.

**Giới hạn không thể bỏ qua:** Thu hồi trong KMS không thể xóa một bản sao vật liệu khóa đã ra khỏi vùng kiểm soát, cũng không thể khiến dữ liệu đã bị đọc trái phép trở nên bí mật như trước.

## 12. Sai lầm phổ biến và nguyên tắc phòng tránh

| Sai lầm | Vì sao nguy hiểm? | Cách làm đúng hơn |
|---|---|---|
| Nghĩ static key là phải nhúng trong mã nguồn | Khóa lộ qua Git, artifact, logs hoặc image | Dùng KMS/HSM, secret store thích hợp và tham chiếu key ID |
| Dùng một static AES key cho tất cả tenant và mọi mục đích | Phạm vi tổn thất rất lớn nếu lộ | Phân tách khóa và quyền theo rủi ro, môi trường, tenant, ứng dụng |
| Dùng cùng nonce cố định với static AES-GCM key | Có thể phá bí mật và xác thực | Nonce duy nhất trong phạm vi từng khóa; thiết kế cho restart và đa instance |
| Dùng mật khẩu trực tiếp làm static encryption key | Mật khẩu có thể bị đoán; entropy thấp | Dùng CSPRNG hoặc password-based KDF phù hợp nếu đầu vào là mật khẩu |
| Đổi key alias nhưng giữ nguyên key material sau sự cố | Khóa thực tế vẫn bị lộ | Tạo vật liệu khóa mới, cập nhật dữ liệu/tin cậy và vô hiệu hóa bản cũ |
| Dùng static private key cho mọi loại phép toán | Vi phạm phân tách mục đích, tăng bề mặt bị lạm dụng | Chọn loại khóa/thuật toán đúng và giới hạn key usage |
| Cho rằng static authentication key đồng nghĩa không có forward secrecy | Đánh giá sai giao thức TLS/(EC)DHE | Xem cách thiết lập session key và thời điểm xóa ephemeral secrets |
| Hủy static key trước khi migrate bản mã cũ | Mất khả năng giải mã dữ liệu hợp pháp | Duy trì metadata phiên bản, diễn tập migration và xác minh backup |
| Chỉ nhìn key status mà không thử phép toán thực tế | Quyền/caches ngoài KMS có thể còn hoạt động | Kiểm thử từ chối tại API và mọi verifier liên quan |
| Bỏ qua kiểm toán và giới hạn quyền KMS | Dịch vụ bị chiếm quyền có thể lạm dụng decrypt/sign | IAM least privilege, phân tách nhiệm vụ, cảnh báo sử dụng bất thường |

## 13. Cách chọn static key hay ephemeral key

Không có quy tắc "static luôn kém an toàn" hoặc "ephemeral luôn tốt hơn". Chọn dựa trên **vai trò mật mã**:

1. **Cần danh tính ổn định, ký số hoặc cấp chứng chỉ?** Dùng static private/public key được bảo vệ và có quy trình rotation/revocation. Dùng ephemeral key cho mục đích phiên khi giao thức hỗ trợ.
2. **Cần mã hóa lượng lớn dữ liệu lưu trữ?** Dùng DEK có phạm vi rõ ràng, KEK qua KMS và envelope encryption. Thời hạn từng DEK/KEK phụ thuộc quy mô và rủi ro.
3. **Cần bảo vệ dữ liệu trên kênh truyền?** Dùng giao thức được chuẩn hóa như TLS với thiết lập khóa phiên thích hợp; không tự thiết kế cơ chế static PSK + AES-GCM nếu thiếu phân tích giao thức.
4. **Cần giảm thiệt hại nếu khóa dài hạn lộ?** Tách lớp xác thực tĩnh khỏi khóa phiên khi thích hợp, áp dụng forward secrecy, phạm vi khóa nhỏ và rotate.
5. **Cần giải mã dữ liệu sau nhiều năm?** Lập kế hoạch lưu giữ khóa/phiên bản cùng chính sách truy cập và khôi phục; đừng tùy tiện xóa khóa vì đã hết thời gian tạo dữ liệu mới.

Một static key đáng tin cậy cần có **mục đích cụ thể, chủ sở hữu, key ID/version, cryptoperiod, chính sách phân quyền, nơi lưu trữ, giới hạn sử dụng, kiểm toán và phương án thay thế**.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một private key ký số dùng trong ba tháng rồi được rotate có còn gọi là static key không?

**Trả lời:** Có. Nó được dùng lại qua nhiều thao tác trong một khoảng có quản lý. Static không có nghĩa là vĩnh viễn hoặc không được xoay vòng.

**Câu 2.** Một static AES-256-GCM key có bắt buộc đi cùng một nonce cố định không?

**Trả lời:** Không. Mỗi lần mã hóa bằng GCM dưới cùng khóa phải dùng nonce khác nhau; dùng một nonce cố định lặp lại là lỗi bảo mật nghiêm trọng.

**Câu 3.** Nếu TLS dùng static certificate signing key, các phiên giao tiếp cũ chắc chắn bị giải mã khi private key đó lộ về sau không?

**Trả lời:** Không thể kết luận như vậy. Trong thiết kế bắt tay sử dụng (EC)DHE và có forward secrecy phù hợp, việc lộ khóa xác thực dài hạn sau này không tự giải lộ khóa phiên cũ. Cần xem xét chính xác giao thức và bí mật phiên đã bị lộ hay chưa.

**Câu 4.** Tại sao một KEK được sử dụng qua nhiều lần wrap vẫn có thể an toàn?

**Trả lời:** Vì KEK có thể được bảo vệ trong KMS/HSM với chính sách quyền và cryptoperiod phù hợp. An toàn còn phụ thuộc cách wrap, phạm vi DEK, audit, rotation và xử lý sự cố, chứ không chỉ thời gian tồn tại.

**Câu 5.** Có thể xem rewrap DEK dưới KEK mới là hoàn toàn khắc phục việc DEK đã bị lộ không?

**Trả lời:** Không. Rewrap chỉ thay lớp bảo vệ của DEK; nếu DEK bị lộ, có thể phải sinh DEK khác và mã hóa lại dữ liệu bị ảnh hưởng.

**Câu 6.** Hard-coded key và static key có giống nhau không?

**Trả lời:** Không. Hard-coded mô tả cách nhúng/lưu khóa trong code; static mô tả mô hình sử dụng qua nhiều thao tác hoặc phiên.

**Câu 7.** Điều gì cần lưu cùng bản mã khi ứng dụng có nhiều phiên bản static DEK?

**Trả lời:** Ít nhất cần tham chiếu khóa/phiên bản, thông tin thuật toán và metadata thiết yếu của chế độ mã hóa như nonce, tag và ngữ cảnh AAD được kiểm soát. Tránh lưu key material dạng rõ cùng bản mã.

## 15. Ghi nhớ

**Static key** là khóa có vật liệu được dùng qua nhiều thao tác/phiên trong một khoảng thời gian xác định. Nó có thể là **khóa đối xứng, private/public key bất đối xứng, PSK, DEK hoặc KEK**. Tính "static" không đồng nghĩa yếu, không đồng nghĩa hard-coded và không cấm rotation.

Để thiết kế hệ thống bảo vệ khóa an toàn, luôn hỏi: **Khóa này dùng để ký, mã hóa, xác thực hay bọc khóa? Phạm vi dữ liệu là gì? Khóa nằm ở đâu, ai được dùng và dùng trong bao lâu? Nonce/IV và khóa phiên được xử lý thế nào? Nếu khóa bị lộ, có thể thu hồi và chuyển sang phiên bản mới mà vẫn giữ dữ liệu hợp pháp không?** Các câu hỏi ấy kết nối phân loại khóa với mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập, kiểm toán và toàn bộ vòng đời khóa.
