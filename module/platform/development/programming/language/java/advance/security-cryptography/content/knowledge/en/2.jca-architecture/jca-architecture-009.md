# 2.9 Tính tương thích và trạng thái thay đổi khi dùng dịch vụ mật mã đồng thời

## 1. Vì sao hai vấn đề này phải được xem xét cùng nhau?

Một ứng dụng Java có thể thực hiện hàng nghìn tác vụ mật mã đồng thời: băm nội dung tải lên, xác minh chữ ký webhook, tính HMAC, mã hóa dữ liệu người dùng, hoặc giải mã các thông điệp đến từ dịch vụ khác. Những tác vụ có thể chạy trên nhiều thread của web server, thread pool, tác vụ bất đồng bộ hoặc nhiều instance ứng dụng.

Để kết quả chính xác và an toàn, cần đồng thời giải quyết **hai nhóm vấn đề độc lập nhưng liên quan**:

1. **Tính tương thích (interoperability / compatibility):** Bên tạo và bên tiêu thụ dữ liệu mật mã có thống nhất thuật toán, tham số, định dạng byte, biểu diễn khóa và phiên bản giao thức không? Các Java Security Provider khác nhau có cùng hỗ trợ những lựa chọn đó không?
2. **Trạng thái và tính đồng thời (state / concurrency):** Một đối tượng JCA đang giữ dữ liệu từ thao tác trước, khóa nào, chế độ ký/xác minh hay mã hóa/giải mã nào? Nếu nhiều thread cùng gọi update, init hoặc doFinal trên đối tượng đó, liệu một yêu cầu có lẫn dữ liệu/trạng thái của yêu cầu khác không?

**Mấu chốt:** “Cùng tên thuật toán” chưa đủ bảo đảm tương thích giữa hai hệ thống; “cùng dùng một đối tượng Java” cũng chưa bảo đảm được phép gọi đồng thời.

### Mục tiêu sau bài

Sau khi học, bạn có thể:

- Phân biệt **engine API**, **provider implementation** và **trạng thái riêng của engine instance** trong JCA.
- Xác định trạng thái thay đổi ở MessageDigest, Mac, Signature, Cipher và ý nghĩa của init, update, digest/sign/verify/doFinal, reset.
- Chọn phạm vi sở hữu đối tượng mật mã an toàn khi chạy đa luồng.
- Nhận diện lỗi do provider/default, tham số, encoding, định dạng khóa và nonce/IV bị dùng lại.
- Thiết kế và kiểm thử hợp đồng byte/thuật toán để nhiều ứng dụng, phiên bản hoặc provider tương tác được với nhau.


## 2. Tách cấu hình provider khỏi trạng thái của mỗi phép toán

Trong JCA/JCE, `getInstance` tạo engine (ví dụ `Cipher`, `Mac`, `Signature`) thông qua implementation của provider. **Provider registry** mô tả khả năng/cấu hình ở mức JVM, còn **engine instance** giữ khóa, mode, tham số và dữ liệu đang xử lý của **một phép toán cụ thể**. Cùng một provider có thể phục vụ nhiều engine độc lập; chia sẻ một engine instance đang xử lý dữ liệu giữa hai request lại là vấn đề khác hẳn.

| Ranh giới | Được chia sẻ khi có chính sách? | Rủi ro nếu nhầm |
| --- | --- | --- |
| Tên thuật toán, cấu hình bất biến, provider đã đăng ký | Có | Cấu hình thay đổi giữa các môi trường gây khác biệt |
| Đối tượng khóa/handle | Có điều kiện theo provider và quyền sử dụng | Lộ khóa, không tương thích HSM hoặc thay khóa giữa chừng |
| `MessageDigest`, `Mac`, `Cipher`, `Signature` đang xử lý | Không mặc định; nên sở hữu theo tác vụ | Xen `init/update/final` từ request khác, gây kết quả sai hoặc rò trạng thái |
| `SecureRandom` | API cho phép dùng đồng thời | Vẫn cần đo contention/entropy tùy provider |

Vì vậy kiểm tra **tương thích giao thức** và **quyền sở hữu state** phải song hành: đúng thuật toán/byte format không cứu được một phép tính bị thread khác xen vào; tách engine theo request cũng không cứu được hai bên không thống nhất IV, AAD, key hay định dạng chữ ký.

## 3. “Tương thích” thực sự bao gồm những lớp nào?

| Lớp | Cần thống nhất | Ví dụ không tương thích |
| --- | --- | --- |
| **API/khả năng hỗ trợ** | Provider có thuật toán và operation cần thiết; JDK/thư viện/hardware có hỗ trợ | JVM A có AES/GCM, provider B không hỗ trợ cấu hình hoặc kích thước khóa tương ứng. |
| **Thuật toán và mode** | Tên/biến thể/thuật toán ký, mã hóa, MAC, digest | Cùng khóa AES nhưng một bên dùng GCM, bên kia dùng CBC; hoặc một bên ký RSASSA-PSS, bên kia xác minh SHA256withRSA/PKCS#1 v1.5. |
| **Tham số mật mã** | Nonce/IV, tag length, salt, iteration count, padding, hash/MGF và tham số phù hợp | Một bên dùng tag GCM 128 bit, bên kia diễn giải 96 bit; RSA-PSS có salt length khác. |
| **Byte input** | UTF-8, thứ tự trường, canonical serialization, AAD, dấu xuống dòng, các byte được ký | Hai bên tưởng ký “cùng JSON” nhưng khoảng trắng, thứ tự key hoặc Unicode encoding khác nhau. |
| **Wire format** | Cách đóng gói version, key ID, IV, ciphertext, tag, signature; Base64/hex nếu có | Một bên gửi ciphertext||tag, bên kia mong tag ở trường riêng; đảo vị trí IV. |
| **Key format / trust** | Thuật toán, mục đích dùng, cách import public/private/secret key, nguồn tin cậy | Public key ở X.509 SubjectPublicKeyInfo nhưng bên nhận đọc như PKCS#8 private key. |
| **Vòng đời và phiên bản** | Phiên bản thông điệp, key rotation, thời gian hiệu lực, chính sách chấp nhận thuật toán | Bản ghi cũ thiếu key ID khi ứng dụng đã xoay khóa. |
| **Môi trường thực thi** | Provider, chính sách/FIPS, token/hardware, khả năng vận hành | HSM không cho xuất private key, hoặc một provider không cho dùng khóa thuộc provider khác. |

**Tương thích chức năng** nghĩa là có thể giải mã/xác minh một cách nhất quán khi dùng cùng giao thức; **an toàn bảo mật** còn đòi hỏi thuật toán, tham số, nguồn khóa và quy tắc sử dụng đúng. Một thiết kế dùng ECB có thể “tương thích” giữa hai provider nhưng không đạt yêu cầu bảo mật dữ liệu ứng dụng.

### Quy tắc thực hành

- Yêu cầu transformation rõ ràng, chẳng hạn **AES/GCM/NoPadding**, thay vì chỉ **AES** rồi phụ thuộc mode/padding mặc định của provider.
- Xác định thuật toán ký kèm tham số chính xác. Với **RSASSA-PSS** phải thống nhất hash, MGF, salt length và trailer field; với **RSA-OAEP** phải thống nhất các tham số OAEP được giao thức sử dụng.
- Tách **định dạng truyền/ghi** khỏi đối tượng engine. Không cố lưu đối tượng Cipher/Signature đang chạy hoặc dựa vào trạng thái nội bộ của provider như một định dạng trao đổi.
- Quy định encoding, field ordering, framing/version và byte sequence trước khi ký hoặc MAC. JSON object bằng nhau về ý nghĩa không mặc nhiên giống nhau ở mức byte.
- Chấp nhận có điều kiện: **getInstance thành công chưa chứng minh init/doFinal sẽ thành công** với khóa, tag/IV hay tham số cụ thể. Cần kiểm thử chính tổ hợp triển khai.


## 4. Đơn vị an toàn là cả chuỗi thao tác, không phải từng method call

Phần vòng đời riêng của từng engine đã có bài giải thích chi tiết. Ở góc nhìn **đa luồng**, điều quan trọng hơn là một **transaction mật mã** phải giữ nguyên quyền sở hữu engine từ lúc khởi tạo cho đến khi có kết quả cuối cùng. Ngay cả khi `doFinal` hoặc `digest` tự reset state, chúng **không tự khóa toàn bộ chuỗi thao tác** để bảo vệ trước thread khác.

| Engine | State mà các lời gọi cùng sửa | Race khi dùng chung một instance | Cách sở hữu an toàn |
| --- | --- | --- | --- |
| `MessageDigest` | Các byte đã `update`, digest state | Băm nhầm phần dữ liệu của request khác; thread kia `digest/reset` trước | Một instance trên mỗi phép băm |
| `Mac` | Key đã `init`, các byte đang tính MAC | Xen `update/doFinal` tạo MAC sai dù cùng key | Một instance theo message; có thể dùng lại **tuần tự** khi API reset |
| `Signature` | Chế độ `initSign/initVerify`, key, message pending | Request khác đổi mode/key hoặc thêm bytes trước khi `sign/verify` | Một instance theo chữ ký |
| `Cipher` | Encrypt/decrypt mode, key, IV, AAD, buffer, authentication state | Key/IV bị ghi đè, plaintext/ciphertext xen kẽ; lỗi GCM nghiêm trọng | Một instance theo bản tin, IV mới cho mỗi lần **mã hóa** GCM cùng key |
| `KeyAgreement` | Private key và pha thỏa thuận đang diễn ra | Peer public key của hai phiên bị trộn | Một instance theo phiên thỏa thuận |
| `SecureRandom` | PRNG state thuộc implementation | **Ngoại lệ được API quy định:** đối tượng có thể gọi đồng thời | Có thể dùng chung sau khi kiểm tra performance/provider |

### 4.1. Vì sao `synchronized` từng lời gọi vẫn chưa đủ?

Giả sử A chạy `mac.update(a)`, sau đó B chạy `mac.update(b)`, cuối cùng A gọi `mac.doFinal()`. **Dù từng phương thức riêng lẻ được khóa**, giá trị A tính có thể là HMAC của `a || b`, không phải `a`. Nếu thật sự dùng một instance chung, phải khóa cả chuỗi `init → update → doFinal` như một giao dịch; đơn giản hơn thường là tạo instance riêng.

Với GCM, còn có invariant **không trùng (key, IV) giữa các lần mã hóa**. Một race trong bộ cấp nonce có thể gây lỗi mật mã ngay cả khi từng Cipher instance hoàn toàn độc lập; vấn đề cấp IV sẽ được kiểm thử ở mục 8. Với AEAD giải mã, không phát tán plaintext chưa kiểm chứng tag.

### 4.2. Vì sao `SecureRandom` là ngoại lệ?

Java quy định `SecureRandom` an toàn cho nhiều thread, bằng khả năng thread-safe của SPI hoặc đồng bộ truy cập do lớp bao quản lý. Tuy nhiên provider có thể chờ entropy/reseed hoặc có contention. Cam kết này **không lan sang** `MessageDigest`, `Mac`, `Signature`, `Cipher` hoặc `KeyAgreement`; các engine ấy cần policy sở hữu riêng.

## 5. Các tình huống lỗi đồng thời điển hình

### 5.1. Đặt engine stateful vào static field hoặc singleton

Một service trong web framework thường là singleton, nghĩa là nhiều request cùng gọi vào một instance service. Nếu service giữ Cipher, Mac hoặc MessageDigest như **field dùng chung**, các method update/init/doFinal tác động lên cùng trạng thái. Dưới tải nhẹ chương trình có thể trông bình thường; dưới tải cao sinh kết quả sai, exception ngẫu nhiên hoặc nguy cơ rò rỉ dữ liệu giữa các request.

**Thiết kế tốt hơn:** một lời gọi xử lý request tạo/khởi tạo engine độc lập, dùng từ đầu đến cuối, rồi loại bỏ; chỉ chia sẻ những cấu hình bất biến, tài liệu key ID và key handle có contract dùng đồng thời phù hợp.

### 5.2. Khóa từng phương thức nhưng quên toàn bộ giao dịch

Nếu chỉ synchronized(update), synchronized(doFinal) riêng lẻ, thread khác vẫn xen vào giữa hai lời gọi. Để chia sẻ một engine stateful bằng khóa, toàn bộ chuỗi thao tác phải được tuần tự hóa. Cách này khó bảo trì, dễ deadlock và làm mất lợi ích xử lý song song. Instance riêng theo tác vụ thường đơn giản hơn.

### 5.3. Dùng ThreadLocal hoặc object pool mà quên reset

**ThreadLocal** có thể giữ một engine riêng cho mỗi thread nhưng không tự giải quyết việc tái sử dụng qua các request trên cùng thread pool. Phải init/reset đúng, tránh tồn đọng context người dùng trước; cân nhắc remove khi không còn cần và xử lý vòng đời thread. Object pool còn cần quy trình checkout → khởi tạo → xử lý → xử lý lỗi → trả lại, kiểm tra loại provider, khóa và tham số.

Riêng **AES-GCM**, tái sử dụng một Cipher trong ThreadLocal không tự tạo nonce mới; **phải thay IV và khởi tạo lại trước mỗi lần mã hóa**. Không vì muốn tối ưu mà giữ IV của request trước.

### 5.4. Chia sẻ buffer mutable

Dù mỗi thread có engine riêng, vẫn có thể gây lỗi nếu cùng thao tác trên một **ByteBuffer**, byte[] đang bị ghi, hoặc tập tham số mutable. Một task sửa input sau khi task khác bắt đầu ký/HMAC có thể khiến chữ ký không khớp. Chỉ chia sẻ dữ liệu thực sự không thay đổi, chuyển quyền sở hữu buffer rõ ràng, hoặc tạo bản sao khi cần.

### 5.5. Nonce bị lặp ở nhiều thread hoặc nhiều instance ứng dụng

Nếu hai thread lấy cùng giá trị counter vì read/modify/write không đồng bộ, chúng có thể dùng trùng IV. Dùng **AtomicLong** hoặc một bộ cấp số duy nhất giúp tránh lặp **trong phạm vi mà bộ cấp số đó thực sự quản lý**. Điều này **không đủ** nếu nhiều JVM/container có cùng khóa nhưng mỗi nơi lại bắt đầu counter từ 0.

Một chiến lược IV/nonce cho production phải được thiết kế **theo từng khóa** và bao phủ restart, nhiều node, backup/restore và lượng message dự kiến. Nếu dùng IV ngẫu nhiên 96 bit, cần đánh giá xác suất va chạm và giới hạn lượng message theo chính sách thuật toán; không gọi xác suất nhỏ là bảo đảm tuyệt đối. Không dùng timestamp đơn thuần, Random, hay IV cố định như một cơ chế cấp nonce an toàn.

### 5.6. “Trùng kết quả” do dữ liệu và provider không thống nhất

Ngay cả khi hoàn toàn không có race, hai hệ thống có thể tạo ra chữ ký/MAC khác nhau do charset, thứ tự field, cách chuẩn hóa JSON, salt length, tag length hoặc thuật toán biến thể khác. **Đừng quy mọi lỗi BadPaddingException, AEADBadTagException hay Signature.verify(false) cho concurrency.** Trước tiên cần xác minh đúng giao thức byte và key ID, sau đó mới cô lập lỗi đồng thời.

## 6. Mô hình sở hữu an toàn: cấu hình chung, engine theo tác vụ

| Thành phần | Có thể chia sẻ? | Điều kiện |
| --- | --- | --- |
| String tên thuật toán/transformation, tham số cấu hình bất biến | Có | Được định nghĩa rõ và không sửa giữa một giao dịch. |
| SecretKey/PublicKey/PrivateKey | Có điều kiện | Key object/handle và provider hỗ trợ cách dùng đang chọn; kiểm soát quyền và vòng đời khóa; không sửa byte nguồn/chia sẻ dữ liệu private key bừa bãi. |
| SecureRandom | Có | API bảo đảm thread-safe; đo throughput/latency của provider cụ thể. |
| MessageDigest, Mac, Signature, Cipher dùng cho các request độc lập | **Nên tách** | Tạo engine riêng cho mỗi thao tác để không chia sẻ trạng thái. |
| Counter cấp IV, trạng thái phiên bản khóa | Có với đồng bộ đúng phạm vi | Phải bảo đảm uniqueness/consistency xuyên các worker/process nếu cùng khóa. |
| Byte array chứa plaintext/key/material | Cần thận trọng | Có thể bị sửa; kiểm soát quyền sở hữu, sao chép và xóa khi thích hợp. |
| Provider configuration / Security provider order | Là cấu hình runtime | Xác định lúc khởi động và coi là hợp đồng triển khai; không sửa provider list liên tục theo request. |

**Mẫu áp dụng cho handler đa luồng:**

1. Xác định rõ operation, algorithm, key ID/version, nonce/AAD và input bytes của request.
2. Tạo engine mới với **getInstance** (và provider nếu thực sự cần pin).
3. Khởi tạo bằng khóa và tham số đúng cho request.
4. Chạy toàn bộ update/finalize trong **cùng task/thread sở hữu engine**; không công bố engine ra singleton.
5. Trả về **bytes kết quả kèm metadata định dạng**, không trả đối tượng Cipher/Mac/Signature.
6. Xử lý exception, không tiếp tục dùng trạng thái lỗi; giải phóng tài nguyên/đóng session khi API/provider yêu cầu.
7. Bảo vệ key lifecycle, kiểm tra authorization và lưu vết phù hợp ở lớp ứng dụng.

Thiết kế per-operation thường là điểm xuất phát an toàn. **Chỉ tối ưu bằng reuse khi đã đo hiệu năng, kiểm chứng contract provider và kiểm soát lifecycle hoàn chỉnh.**

## 7. Ví dụ Java 17+: nhiều tác vụ băm SHA-256 và HMAC chạy song song

Chương trình tạo **32 tác vụ** trong thread pool. Mỗi tác vụ dùng **MessageDigest riêng** và **Mac riêng**, rồi so với hai test vector chuẩn (input và expected output được cố định). Phần cuối kiểm chứng việc digest() và Mac.doFinal() reset state khi tái sử dụng **tuần tự**.

Tạo file **ConcurrentJcaStateDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class ConcurrentJcaStateDemo {
    private static final byte[] HASH = HexFormat.of().parseHex(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    private static final byte[] HMAC = HexFormat.of().parseHex(
            "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8");

    private static boolean calculate() throws Exception {
        byte[] abc = "abc".getBytes(StandardCharsets.US_ASCII);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        boolean hashOk = Arrays.equals(HASH, digest.digest(abc));

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                "key".getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] data = "The quick brown fox jumps over the lazy dog"
                .getBytes(StandardCharsets.US_ASCII);
        boolean macOk = Arrays.equals(HMAC, mac.doFinal(data));
        return hashOk && macOk;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Boolean>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                futures.add(pool.submit(() -> calculate()));
            }
            int ok = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    ok++;
                }
            }
            System.out.println("32 tác vụ đúng: " + ok + "/32");
        } finally {
            pool.shutdown();
        }

        Mac sequential = Mac.getInstance("HmacSHA256");
        sequential.init(new SecretKeySpec(
                "key".getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] bytes = "abc".getBytes(StandardCharsets.US_ASCII);
        System.out.println("Mac doFinal đặt lại trạng thái: " +
                Arrays.equals(sequential.doFinal(bytes), sequential.doFinal(bytes)));

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("MessageDigest digest đặt lại trạng thái: " +
                Arrays.equals(digest.digest(bytes), digest.digest(bytes)));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 ConcurrentJcaStateDemo.java
java ConcurrentJcaStateDemo
~~~

Kết quả:

~~~text
32 tác vụ đúng: 32/32
Mac doFinal đặt lại trạng thái: true
MessageDigest digest đặt lại trạng thái: true
~~~

### Điều ví dụ chứng minh

1. **Mỗi lần calculate() tạo engine riêng** nên các lệnh update/digest/doFinal của các tác vụ không dùng chung trạng thái của một engine.
2. **Test vector xác nhận kết quả bytes**, thay vì chỉ so hai lần tính có thể cùng sai vì một lỗi cài đặt khác.
3. **Cùng một Mac hoặc MessageDigest có thể được dùng lại tuần tự** sau doFinal/digest theo contract của API. Điều này không nói rằng chia sẻ đúng instance đó giữa các task là an toàn.
4. Chuỗi **"key"** chỉ là test vector công khai, **không phải bí mật production**. Trên hệ thống thật, khóa HMAC phải có entropy đủ, được lưu và cấp quyền đúng.
5. Số 32/32 chỉ cho biết phép chạy ví dụ này thành công; không thể dùng một lần chạy để “chứng minh” mọi thao tác, mọi provider hay mọi trường hợp race đều an toàn.

Trong ví dụ, ta cố ý **không** tạo một static MessageDigest/Mac dùng chung. Nếu đặt chúng trong một singleton rồi gọi từ nhiều thread, tính đúng đắn không còn được bảo đảm bởi contract chung.

## 8. Ví dụ Java 17+: AES-GCM đa luồng và IV không bị lặp trong phạm vi ví dụ

Đây là trường hợp quan trọng hơn vì lỗi concurrency có thể biến thành lỗ hổng mật mã dù kết quả giải mã đôi khi trông đúng.

Chương trình tạo **khóa AES mới cho một lần chạy**, dùng một **prefix 4 byte** tạo ngẫu nhiên và một **AtomicLong 8 byte** cấp giá trị khác nhau cho từng message trong cùng JVM. Mỗi task tạo **Cipher riêng**, dùng IV 12 byte mới, AAD cố định, mã hóa rồi giải mã cùng message. Sau đó thử sửa tag để kiểm tra thao tác giải mã bị từ chối.

Mục tiêu của cách cấp IV ở đây chỉ là minh họa **không trùng IV trong một lần chạy với một khóa vừa tạo**. Đây **không phải thuật toán cấp IV production cho khóa được dùng lại qua nhiều lần restart hoặc nhiều node**.

Tạo file **ConcurrentGcmDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class ConcurrentGcmDemo {
    private static final byte[] AAD =
            "orders:v1".getBytes(StandardCharsets.UTF_8);

    private record Envelope(byte[] iv, byte[] ciphertextWithTag) {}

    private static Envelope encrypt(
            SecretKey key, byte[] iv, String message) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        cipher.updateAAD(AAD);
        byte[] result = cipher.doFinal(message.getBytes(StandardCharsets.UTF_8));
        return new Envelope(iv, result);
    }

    private static String decrypt(SecretKey key, Envelope envelope)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, envelope.iv()));
        cipher.updateAAD(AAD);
        byte[] plain = cipher.doFinal(envelope.ciphertextWithTag());
        return new String(plain, StandardCharsets.UTF_8);
    }

    private static byte[] nextIv(byte[] prefix, AtomicLong sequence) {
        long number = sequence.getAndIncrement();
        if (number < 0) {
            throw new IllegalStateException("IV sequence exhausted");
        }
        return ByteBuffer.allocate(12).put(prefix).putLong(number).array();
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] prefix = new byte[4];
        new SecureRandom().nextBytes(prefix);
        AtomicLong sequence = new AtomicLong();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Boolean>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                final int index = i;
                futures.add(pool.submit(() -> {
                    byte[] iv = nextIv(prefix, sequence);
                    String message = "order-" + index;
                    return message.equals(decrypt(key, encrypt(key, iv, message)));
                }));
            }
            int ok = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    ok++;
                }
            }
            System.out.println("GCM song song: " + ok + "/32");

            Envelope original = encrypt(key, nextIv(prefix, sequence), "order-99");
            byte[] modified = original.ciphertextWithTag().clone();
            modified[modified.length - 1] ^= 1;

            try {
                decrypt(key, new Envelope(original.iv(), modified));
                System.out.println("Sai: chấp nhận bản mã sửa");
            } catch (AEADBadTagException expected) {
                System.out.println("Tag sai: đã từ chối");
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 ConcurrentGcmDemo.java
java ConcurrentGcmDemo
~~~

Kết quả:

~~~text
GCM song song: 32/32
Tag sai: đã từ chối
~~~

### Đọc kỹ những điều được và chưa được bảo đảm

- **Cipher riêng cho từng phép toán:** hai task không gọi init/updateAAD/doFinal trên cùng một Cipher instance.
- **Một khóa AES dùng nhiều lần là điều có thể thiết kế**, nhưng **mỗi lần mã hóa AES-GCM với khóa đó phải dùng IV duy nhất**. AtomicLong bảo đảm các lần lấy số không trùng trong phạm vi counter của ví dụ; byte prefix không thay đổi trong lần chạy.
- **Khóa được tạo mới khi chạy chương trình**. Nếu triển khai có khóa tồn tại lâu dài, các JVM khác nhau, khởi động lại hoặc khôi phục snapshot thì counter riêng không bảo đảm toàn cục. Cần thiết kế bộ cấp IV phối hợp với key version và giới hạn sử dụng theo hướng dẫn của thuật toán.
- **Envelope** là record chứa tham chiếu byte[]: record không tự làm byte[] bất biến sâu. Trong ví dụ, buffer chỉ được đọc hoặc clone trước khi sửa; ở ứng dụng thật cần kiểm soát quyền sở hữu, bản sao và dữ liệu có thể bị sửa đồng thời.
- **CiphertextWithTag** là chuỗi byte do JCE GCM trả về với tag gắn cùng bản mã. Khi lưu hoặc truyền, phải định nghĩa rõ format (version, key ID, IV length, IV, ciphertext/tag, AAD rule); người nhận không thể tự đoán các giá trị này.
- **AAD** không bị mã hóa nhưng được xác thực. Nếu bên nhận truyền AAD khác, tag sẽ không hợp lệ. Lỗi AEADBadTagException không chứng minh một cách duy nhất rằng có kẻ tấn công; cũng có thể do dữ liệu hỏng, sai khóa, sai IV hoặc sai AAD.

Ví dụ chỉ minh họa concurrency, state và tính toàn vẹn. Bảo vệ dữ liệu production còn đòi hỏi KMS/secret management, giới hạn lượng dữ liệu/mỗi khóa, rotation, chính sách truy cập và giải mã thông điệp cũ.

## 9. Thiết kế format để các provider và phiên bản ứng dụng tương tác được

**Không truyền đối tượng engine; truyền dữ liệu và tham số được định nghĩa rõ.** Ví dụ cho AES-GCM:

~~~text
Envelope V1 (định dạng do ứng dụng tự quy định, chỉ là ví dụ thiết kế)
  version:          1 byte
  keyIdLength:      1 byte
  keyId:            UTF-8 bytes, keyIdLength byte
  iv:               12 byte
  ciphertextAndTag: phần còn lại (tag 16 byte ở cuối)
  AAD:              bytes được xác định riêng bằng hợp đồng giao thức
~~~

Định dạng trên chỉ là **đề xuất giao thức minh họa**, không phải format do JCA chuẩn hóa. Nếu triển khai cần xác định giới hạn độ dài, xử lý input sai format, version nâng cấp, và byte nào thuộc AAD để bảo vệ metadata trước sửa đổi. Đừng để key ID/tenant ID quan trọng bị thay đổi mà không được xác thực hoặc đối chiếu với ngữ cảnh tin cậy.

Một bản ghi thường cần:

1. **Version:** cho phép đọc dữ liệu cũ khi thay cách đóng gói/thuật toán được hỗ trợ.
2. **Key ID / key version:** giúp chọn đúng khóa khi rotation; phải kiểm tra quyền dùng khóa, không dùng ID đến từ nguồn không đáng tin để truy cập tùy ý.
3. **Algorithm parameters:** IV, tag length, các tham số cần thiết. Có thể cố định trong version để bớt metadata, nhưng phải ghi trong đặc tả.
4. **Payload:** ciphertext và tag hoặc signature/MAC với format/encoding đã thống nhất.
5. **AAD/canonicalization:** quy định chính xác byte dùng làm dữ liệu được xác thực.
6. **Chính sách kiểm tra:** reject unknown version, khóa không hợp lệ, tag/signature sai; không tự fallback sang cơ chế yếu.

### Khóa có thể dùng qua provider khác không?

JCA hướng tới tính tương thích giữa các implementation, nhưng **không nên giả định mọi đối tượng Key đều chuyển được sang mọi provider**.

- Public key thông thường có thể được biểu diễn ở dạng **X.509 SubjectPublicKeyInfo**; private key phần mềm ở dạng **PKCS#8** nếu cho phép export. Cần dùng **KeyFactory** với key spec phù hợp.
- SecretKeySpec có thể mô tả khóa đối xứng từ bytes, nhưng một khóa **HSM/PKCS#11** có thể là handle không xuất được và bị ràng buộc với provider/token.
- Key.getEncoded() **có thể trả null** khi khóa không cho phép xuất dạng mã hóa. Không dùng getEncoded() như một bước mặc định để “di chuyển” private key.
- Khi đưa khóa vào một provider mới, vẫn phải kiểm chứng thuật toán, mục đích sử dụng, policy và khả năng init. Một khóa từ provider A không tự động tương thích với mọi API/provider B.

### Băm, MAC và chữ ký có cần định dạng không?

Có. Ví dụ SHA-256 tạo **32 byte**, nhưng bên khác có thể hiển thị hex chữ thường, hex chữ hoa hay Base64: chúng là cách biểu diễn khác nhau của **cùng bytes**. HMAC cũng cần thống nhất input bytes và thứ tự tính. Chữ ký số còn có đặc tả encoding của chữ ký tùy thuật toán (ví dụ một số định dạng chữ ký ECDSA khác nhau không thể được coi là như nhau). Tên “RSA” đơn lẻ không đủ xác định padding, digest và profile chữ ký.

Nếu dùng JSON cho dữ liệu ký, hãy chuẩn hóa theo một quy tắc rõ hoặc ký đúng raw payload mà giao thức định nghĩa; không chuyển đổi object → JSON lại ở bên nhận rồi mặc định byte giống bản gốc.

## 10. Provider và khả năng tương thích khi triển khai

### 10.1. Định danh provider trong chẩn đoán

Các câu lệnh sau là **mảnh minh họa dùng trong một method có throws phù hợp**, không phải chương trình Java độc lập:

~~~java
var digest = java.security.MessageDigest.getInstance("SHA-256");
System.out.println(digest.getAlgorithm());
System.out.println(digest.getProvider().getName());

var cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
System.out.println(cipher.getAlgorithm());
System.out.println(cipher.getProvider().getName());
~~~

Tên provider in ra **phụ thuộc runtime**, không nên ghi cứng kết quả khi dạy hoặc kiểm thử đa nền tảng. Có thể xem danh sách provider được đăng ký bằng **Security.getProviders()**. Khi kiểm thử, cần ghi lại JDK, provider thực tế, algorithm/transformation, loại khóa và tham số; không log nội dung khóa, plaintext hay bí mật.

### 10.2. Có nên chỉ định provider cụ thể?

- **Không chỉ định provider:** giúp ứng dụng tận dụng cài đặt phù hợp trên JVM đang chạy; vẫn phải kiểm thử điều kiện hỗ trợ và hợp đồng mật mã.
- **Chỉ định provider:** hữu ích khi bắt buộc dùng HSM, provider đã qua kiểm định, chính sách/FIPS hoặc khi cần hành vi/khả năng được xác minh cụ thể; có thể giảm tính di động giữa môi trường.
- Thay đổi thứ tự Security provider, cấu hình JDK hoặc dependency provider trong khi hệ thống đang chạy có thể ảnh hưởng **các lần tạo engine sau đó**; engine hiện có không tự chuyển cài đặt một cách kỳ diệu.

Không nên sửa cấu hình provider theo request để “thử cho chạy”. Quyết định provider là cấu hình kiến trúc/triển khai và cần test rõ ràng.

### 10.3. Đừng phụ thuộc default

Phản ví dụ: **Cipher.getInstance("AES")** cho provider tự chọn mode/padding mặc định. Điều này vừa có nguy cơ không an toàn vừa làm kết quả không nhất quán giữa môi trường. **Cipher.getInstance("AES/GCM/NoPadding")** nêu yêu cầu rõ hơn, nhưng vẫn phải thống nhất IV, tag, AAD và format.

Tương tự, hãy ghi rõ tên thuật toán HMAC, thuật toán chữ ký và tham số liên quan; tránh cơ chế fallback “nếu ký chuẩn không được thì chuyển sang thuật toán cũ yếu hơn” mà không được thiết kế và kiểm soát.

## 11. Kiểm thử đúng: tách compatibility test khỏi concurrency test

| Nhóm kiểm thử | Cách thực hiện | Lỗi được phát hiện |
| --- | --- | --- |
| **Known-answer test** | Cùng input/key/params cho expected digest/HMAC/ciphertext khi thuật toán có vector chuẩn | Sai thuật toán, encoding, padding, profile, implementation. |
| **Cross-provider / cross-version** | Provider A tạo, provider B đọc/xác minh; đảo chiều khi phù hợp | Khác định dạng key/signature, mode, tham số, khả năng hỗ trợ. |
| **Tamper/negative test** | Đổi 1 bit ciphertext/tag/AAD, thay chữ ký/khóa, sai key ID | Không xác minh tag/chữ ký, xử lý lỗi/fallback không đúng. |
| **Concurrency/stress test** | Chạy hàng trăm/nghìn tác vụ độc lập với expected outputs và nhiều thread | Race khi dùng chung engine/buffer/counter, dữ liệu request bị trộn. |
| **Lifecycle test** | init → update → doFinal; dùng lại tuần tự; thử exception rồi khởi tạo lại | Hiểu sai reset, dùng sai mode, reuse với trạng thái lỗi. |
| **Nonce/key lifecycle test** | Chạy đồng thời trên nhiều node, restart/snapshot, rotation | IV trùng theo khóa, key ID cũ không giải mã được, khóa không nhất quán. |
| **Runtime matrix** | Kiểm tra môi trường JDK, provider, FIPS/HSM, policy, độ dài khóa | NoSuchAlgorithm/NoSuchPadding/InvalidKey/InvalidAlgorithmParameter trong production. |
| **Performance & liveness** | Đo throughput, contention, provider lock, HSM session pool, entropy wait | Tắc nghẽn, starvation, timeout và chi phí getInstance/init. |

Một bài stress test chạy xanh **không chứng minh không có data race**. Chứng minh thiết kế an toàn dựa trước hết vào ownership, API contract và invariant (như một IV cho mỗi lần mã hóa), sau đó dùng test để bắt lỗi cài đặt.

### Checklist review một dịch vụ đa luồng

- Có engine stateful nào là field/static của singleton hay bị share giữa request không?
- Mỗi tác vụ có sở hữu trọn chuỗi init → update → finalize không?
- Input buffer, key parameter, IV/AAD có bị thread khác sửa khi đang xử lý không?
- Với AES-GCM, có thể chứng minh hoặc đánh giá theo thiết kế **không lặp (key, IV)** khi scale/restart không?
- Có giao thức byte chuẩn: charset, trường dữ liệu, version, key ID, tag/padding, tham số và thứ tự không?
- Có negative test cho dữ liệu sai, khóa sai, replay khi giao thức yêu cầu không?
- Có test trên môi trường/provider thực tế và ghi lại các thay đổi provider/JDK không?
- Có giữ bí mật khỏi log, bảo vệ private/secret keys và giới hạn truy cập hợp lý không?

## 12. Phân biệt lỗi state, lỗi khả năng hỗ trợ và lỗi dữ liệu

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| **NoSuchAlgorithmException** hoặc **NoSuchPaddingException** | Provider có cung cấp thuật toán/transformation đúng tên không? JDK và chính sách có khác nhau không? |
| **InvalidKeyException** | Key size, key type, purpose và khả năng import/provider handle có hợp lệ không? |
| **InvalidAlgorithmParameterException** | IV, tag length, PSS/OAEP/GCM parameters có đúng contract/provider không? |
| **IllegalStateException** khi update/finalize | Đã init chưa? Mode đang là gì? Có thread khác re-init hoặc finalize cùng engine không? |
| **AEADBadTagException** | Sai key/IV/AAD, ciphertext/tag hỏng hoặc bị sửa; kiểm tra format, byte serialization và nonce. |
| **Signature.verify trả false** | Public key, byte input, algorithm/profile, encoding chữ ký và tham số có khớp không? |
| **Lỗi chỉ xuất hiện khi tải cao** | Engine/buffer singleton, ThreadLocal reuse, counter IV, provider/HSM contention, key rotation race. |

Không dùng thông báo lỗi chi tiết có chứa khóa, plaintext hoặc metadata nhạy cảm trong API phản hồi cho client. Hãy log nguyên nhân kỹ thuật ở mức đủ để chẩn đoán, kèm request ID/algorithm version đã được phê duyệt, không log secrets.

## 13. Một thiết kế ứng dụng Java thực tế

Giả sử có dịch vụ web xác thực webhook đồng thời:

1. Mỗi request có đúng **raw payload bytes**, chữ ký/MAC, key ID và timestamp theo giao thức đã thỏa thuận.
2. Server kiểm tra định dạng, giới hạn payload, thời hạn và replay/idempotency theo yêu cầu.
3. Thành phần tìm khóa nhận key ID và trả về đúng key/version đã được phép sử dụng; cấu hình provider đã cố định từ deployment.
4. Service tạo **Mac hoặc Signature instance mới trong method**; init đúng khóa, update trên raw bytes/canonical bytes đã định nghĩa, kiểm tra kết quả.
5. Chỉ khi xác thực thông điệp hợp lệ mới đi tiếp tới xử lý nghiệp vụ và kiểm soát quyền.
6. Tại lớp nghiệp vụ, xử lý idempotent để thông điệp hợp lệ bị gửi lặp không tạo giao dịch lặp.
7. Khi thay provider/JDK, chạy lại compatibility vectors, negative tests và concurrency tests trước khi triển khai.

Tương tự, với dịch vụ mã hóa dữ liệu, **mỗi thao tác mã hóa** cần một Cipher với khóa/IV/AAD đúng; bản ghi phải lưu metadata giải mã theo version, còn bộ quản lý IV và key lifecycle phải đủ an toàn dưới tải đồng thời, restart và nhiều instance.

## 14. Câu hỏi tự kiểm tra

**1. Mac.doFinal() reset về trạng thái sau init. Có thể dùng một Mac instance cho nhiều request song song không?**  
Không suy ra được. Reset hỗ trợ **tái sử dụng tuần tự**; các chuỗi update và doFinal ở các thread khác nhau vẫn có thể xen vào nhau. Nên tạo Mac riêng cho mỗi tác vụ.

**2. Vì sao cùng một chương trình AES-GCM chạy trên hai JVM có thể không tương thích?**  
Không chỉ cần cùng transformation. Hai bên phải thống nhất key, IV, tag length, AAD và byte format; provider của mỗi bên phải hỗ trợ cấu hình đó.

**3. Cipher.doFinal() reset state, vậy dùng lại Cipher GCM vừa mã hóa để mã hóa message khác có an toàn không?**  
Không nếu vẫn dùng cặp key/IV cũ. Phải thiết lập một IV mới hợp lệ, duy nhất với khóa đó; thường tạo Cipher mới cho thao tác tiếp theo.

**4. Có thể đặt một SecureRandom trong singleton để các thread dùng chung không?**  
Có, Java quy định SecureRandom thread-safe. Tuy nhiên vẫn cần xem throughput, hành vi block/reseed và provider thực tế. Không áp dụng kết luận tương tự cho Cipher, Signature, Mac hay MessageDigest.

**5. Signature.verify(false) chắc chắn chứng minh có race condition?**  
Không. Lỗi cũng có thể nằm ở public key, thuật toán/tham số, định dạng chữ ký hoặc byte input khác nhau. Kiểm tra compatibility contract trước, rồi mới phân tích concurrency.

**6. AtomicLong sinh nonce duy nhất trong một JVM có đủ cho cluster dùng cùng khóa không?**  
Không. Một node khác có thể dùng lại cùng dãy counter; restart/khôi phục trạng thái cũng vậy. Uniqueness cần được bảo đảm trong **toàn bộ phạm vi dùng chung khóa**.

**7. Vì sao không nên dựa vào getEncoded() cho mọi private key?**  
Các khóa thuộc HSM/PKCS#11 có thể là key handle không cho xuất. Khả năng chuyển khóa phụ thuộc provider, loại khóa và chính sách an toàn; getEncoded có thể trả null.

## 15. Ghi nhớ và tài liệu đối chiếu

Tính tương thích trong JCA là khả năng các phía thống nhất **thuật toán + tham số + bytes + khóa/định dạng + giao thức/version + chính sách provider**. Tính đúng đắn khi chạy đồng thời phụ thuộc **quyền sở hữu stateful engine**, thứ tự gọi phương thức và các invariant bảo mật như **mỗi lần mã hóa AES-GCM không lặp key/IV**. Thiết kế tốt thường chia sẻ cấu hình và quản lý khóa có kiểm soát, tạo engine riêng cho từng tác vụ và kiểm thử tính tương thích trên môi trường triển khai thật.

Tài liệu API chuẩn cho JDK 21:

- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)