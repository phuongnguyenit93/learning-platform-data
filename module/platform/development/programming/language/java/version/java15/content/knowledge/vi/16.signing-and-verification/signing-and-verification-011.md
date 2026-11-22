# Tránh chia sẻ `Signature` khả biến giữa nhiều luồng trong Java

## 1. Vì sao đây là vấn đề bảo mật, không chỉ là tối ưu hiệu năng?

`java.security.Signature` là API của Java Cryptography Architecture (JCA) dùng **ký số** bằng khóa riêng và **xác minh chữ ký** bằng khóa công khai. Đây là một đối tượng **có trạng thái thay đổi được** (*mutable, stateful*), vì các lệnh `initSign`, `initVerify`, `update`, `setParameter`, `sign` và `verify` tác động đến cùng một phiên tính toán.

Khi ứng dụng web hoặc service xử lý đồng thời nhiều yêu cầu, một lỗi nguy hiểm là **tái sử dụng cùng một instance `Signature` cho các request chạy song song**. Kết quả có thể là:

- Byte của request này bị ghép vào luồng dữ liệu đang ký của request khác.
- Một luồng khởi tạo lại key hoặc chuyển từ SIGN sang VERIFY trong lúc luồng khác đang thao tác.
- Chữ ký phát hành cho **thông điệp khác** với thông điệp mà business logic dự định xác nhận.
- Xác minh thất bại, phát sinh `SignatureException`/lỗi provider, hoặc xuất hiện lỗi không ổn định khó tái hiện.
- Trong trường hợp có nhiều tenant, **trộn dữ liệu giữa các giao dịch/định danh**, dẫn tới hậu quả bảo mật và tính đúng đắn của nghiệp vụ.

**Quy tắc mặc định:** **mỗi thao tác ký hoặc xác minh độc lập nên dùng một `Signature` instance riêng**, được tạo/khởi tạo/cập nhật/kết thúc hoàn toàn trong phạm vi thao tác. Một cặp khóa có thể được quản lý tập trung theo chính sách/provider, nhưng **không chia sẻ phiên `Signature` khả biến** giữa các tác vụ.

Bài dùng **Ed25519 và Ed448**, được Java hỗ trợ chính thức từ Java 15 theo **JEP 339**, và các quy tắc quản lý trạng thái `Signature` vẫn đúng cho Java hiện hành. API `Signature` tồn tại từ trước Java 15; **EdDSA** mới là phần liên hệ đến module Java 15. Nguyên tắc áp dụng tương tự cho các chữ ký JCA hiện đại khác nếu ứng dụng cần dùng chúng.

## 2. `Signature` thực sự lưu những trạng thái gì?

Theo tài liệu Java SE, mỗi phiên `Signature` có ba trạng thái khái niệm:

| Trạng thái | Cách đi vào | Phép xử lý dự kiến |
| --- | --- | --- |
| **UNINITIALIZED** | Mới `Signature.getInstance(...)` | Chưa thể `update` để ký/xác minh đúng quy trình |
| **SIGN** | `initSign(PrivateKey)` | `update(...)` rồi `sign()` |
| **VERIFY** | `initVerify(PublicKey)` | `update(...)` rồi `verify(signatureBytes)` |

Pipeline ký:

~~~text
Signature.getInstance("Ed25519")
       │
       ▼
initSign(privateKey)     chọn khóa riêng và chế độ SIGN
       │
       ▼
update(bytes1)
update(bytes2)          đưa dữ liệu vào CÙNG MỘT phiên ký
       │
       ▼
sign()                  trả byte chữ ký trên toàn bộ dữ liệu đã update
       │
       ▼
trở về trạng thái sau initSign (có thể dùng tiếp tuần tự)
~~~

Pipeline xác minh:

~~~text
Signature.getInstance("Ed25519")
       │
       ▼
initVerify(publicKey)   chọn khóa công khai và chế độ VERIFY
       │
       ▼
update(messageBytes)    đưa chính byte thông điệp cần kiểm chứng
       │
       ▼
verify(signatureBytes)  true/false hoặc exception theo trường hợp
       │
       ▼
trở về trạng thái sau initVerify (có thể dùng tiếp tuần tự)
~~~

**Hai chi tiết quan trọng:**

1. `update` **tích lũy byte** cho lần ký/xác minh hiện tại. Nhiều lời gọi `update` trong cùng phiên là hợp lệ **nếu chúng là các phần liên tiếp của một thông điệp duy nhất**. Nó trở thành lỗi khi các lời gọi ấy đến từ những request khác nhau mà không có cơ chế cô lập.
2. `sign()` và `verify(...)` được đặc tả **reset phiên về trạng thái sau lần khởi tạo tương ứng**, cho phép tái sử dụng **tuần tự** với cùng key. **Reset sau khi hoàn thành không bảo đảm thread safety trong khi hai luồng cùng thao tác.**

Đây là khác biệt giữa **tái sử dụng lần lượt** và **chia sẻ cùng lúc**: cái đầu được API hỗ trợ trong một số điều kiện, cái sau không nên được giả định là an toàn.

## 3. Race condition: byte của hai request bị trộn

Giả sử service có một `Signature shared`:

~~~java
// ĐOẠN MÃ MINH HỌA KIỂU THIẾT KẾ SAI, không phải chương trình độc lập.
class BadSigner {
    private final Signature shared;

    BadSigner() throws GeneralSecurityException {
        shared = Signature.getInstance("Ed25519");
    }

    byte[] sign(PrivateKey key, byte[] data) throws GeneralSecurityException {
        shared.initSign(key);
        shared.update(data);
        return shared.sign();
    }
}
~~~

Nếu một instance `BadSigner` được singleton service chia sẻ cho Thread A và Thread B, ba lời gọi trong `sign(...)` **không phải một giao dịch nguyên tử**.

Lịch thực thi có thể xảy ra:

~~~text
Thread A                           Thread B
--------                           --------
shared.initSign(privateKey)
shared.update("message-A")
                                    shared.update("message-B")
shared.sign()
       │
       ▼
Signature chứa "message-Amessage-B"
thay vì chỉ "message-A"
~~~

Ví dụ cụ thể ở mục 8 mô phỏng chính xác thứ tự này bằng **một thread** để dễ kiểm tra. Đây không phải benchmark hay thử nghiệm dựa vào xác suất; nó chứng minh **về mặt logic**, chỉ cần hai chuỗi `update` của hai tác vụ xen vào nhau là phiên ký đã mang **dữ liệu ghép ngoài ý muốn**.

Cùng vấn đề xảy ra khi một task gọi `initSign(keyB)` hoặc `initVerify(pubB)` trong lúc task khác đang xử lý. Chúng đang tác động đến **cùng trạng thái**; khóa, chế độ và dữ liệu tích lũy có thể không còn tương ứng với request.

**Không nên viết test “chạy nhiều luồng rồi chờ có lỗi” làm bằng chứng duy nhất:** race có thể không lộ ra trên một máy hoặc trong một lần chạy, và hành vi cụ thể tùy lịch thực thi/provider. **Sự vắng mặt của lỗi không chứng minh thiết kế chia sẻ đúng.**

## 4. Thread safety của API khác với tính nguyên tử của cả thao tác

Java SE mô tả các trạng thái của `Signature`, cách reset sau `sign/verify` và hợp đồng của từng phương thức. **Không có bảo đảm tổng quát** rằng một instance `Signature` có thể được gọi đồng thời tùy ý bởi nhiều thread để ký nhiều message độc lập.

Ngay cả khi một provider nào đó có khóa nội bộ khiến **mỗi lời gọi phương thức đơn lẻ** không phá cấu trúc dữ liệu, bài toán vẫn chưa được giải quyết:

~~~text
initSign → update → [update thêm nhiều lần] → sign
~~~

Toàn bộ chuỗi ở trên phải thuộc **cùng một request**. Thread-safety ở mức phương thức **không tự làm toàn bộ chuỗi trở thành atomic transaction**.

Có thể phân biệt:

- **`Signature` instance:** mang state phiên tính toán, tránh chia sẻ đồng thời.
- **`KeyPair` / `PublicKey` / `PrivateKey`:** đại diện vật liệu hoặc handle tới khóa; nhiều thao tác có thể dùng cùng khóa khi provider, chính sách bảo mật và môi trường cho phép. Đây **không phải** lý do để dùng chung `Signature`.
- **Byte array của message:** `byte[]` **cũng mutable**. Không cho thread khác sửa mảng trong lúc đang `update`/ký/xác minh; tạo snapshot bất biến theo cách quản lý dữ liệu của ứng dụng khi cần.
- **Đối tượng provider/HSM:** có thể có quota phiên, quy tắc đồng thời và giới hạn khác. Hãy tuân theo tài liệu của provider; việc tạo mỗi `Signature` riêng không thay thế kiểm soát concurrency của thiết bị phần cứng.

**Chia sẻ public/private key có chính sách phù hợp không đồng nghĩa chia sẻ một phiên ký.** Đây là hai trục thiết kế khác nhau.

## 5. Mẫu đúng: mỗi thao tác một `Signature`

### 5.1. Hàm ký Ed25519

~~~java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.Signature;

static byte[] signEd25519(PrivateKey privateKey, byte[] message)
        throws GeneralSecurityException {
    Signature signer = Signature.getInstance("Ed25519");
    signer.initSign(privateKey);
    signer.update(message);
    return signer.sign();
}
~~~

Đây là **đoạn minh họa hàm thành viên**, cần đặt trong class phù hợp. Mỗi lần gọi tạo instance riêng; caller chỉ nhận **mảng byte chữ ký**, không nhận đối tượng có trạng thái bên trong.

### 5.2. Hàm xác minh Ed25519

~~~java
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.Signature;

static boolean verifyEd25519(
        PublicKey publicKey, byte[] message, byte[] signatureBytes)
        throws GeneralSecurityException {
    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(publicKey);
    verifier.update(message);
    return verifier.verify(signatureBytes);
}
~~~

Cả hai hàm giữ trọn *lifecycle* của phiên bên trong một lời gọi, tránh lộ đối tượng `Signature` ra nơi có thể dùng đồng thời.

**Chú ý:** `verify(...)` trả `false` khi chữ ký không khớp, nhưng cũng **có thể ném `SignatureException`** nếu chữ ký có cấu trúc sai hoặc provider không xử lý được đầu vào. Đừng gom mọi lỗi vận hành của provider thành “signature sai” mà không phân biệt và ghi nhận.

### 5.3. Cô lập theo yêu cầu, không chỉ theo thread

Trong server nhận request, nên giữ một cách tổ chức như:

~~~text
Request A ─→ sign(privateKey, bytesA) ─→ Signature riêng A ─→ sigA
Request B ─→ sign(privateKey, bytesB) ─→ Signature riêng B ─→ sigB
Request C ─→ verify(pubKey, bytesC, sigC) ─→ Signature riêng C ─→ true/false
~~~

Các tác vụ có thể được chạy trên cùng hoặc khác thread; quyền sở hữu ở đây là **một thao tác**, không phụ thuộc việc thread pool tái sử dụng thread sau đó.

Trong mã bất đồng bộ/`CompletableFuture`/reactive pipeline, **đừng giữ một `Signature` chung làm field rồi rải các lệnh `update` ở nhiều callback**. Hoặc biến thao tác ký thành một hàm hoàn chỉnh, hoặc sở hữu state riêng theo request với điều phối rõ ràng, không cho cập nhật đan xen.

## 6. Tái sử dụng tuần tự: hợp lệ nhưng khác chia sẻ nhiều luồng

Tài liệu `Signature.sign()` quy định đối tượng được reset về trạng thái sau `initSign` khi kết thúc ký. Tương tự `verify(...)` reset về trạng thái sau `initVerify`. Ví dụ một thread làm lần lượt:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);

signer.update(messageA);
byte[] signatureA = signer.sign(); // kết thúc phiên A

signer.update(messageB);
byte[] signatureB = signer.sign(); // kết thúc phiên B
~~~

Đây là **mã minh họa**, `privateKey`, `messageA` và `messageB` là đầu vào đã biết. Hoàn toàn khác cách một thread cập nhật `messageB` **trước** khi phiên A gọi `sign()`.

Tương tự:

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);

verifier.update(messageA);
boolean aOK = verifier.verify(signatureA);

verifier.update(messageB);
boolean bOK = verifier.verify(signatureB);
~~~

Đây cũng chỉ nên là quy trình **tuần tự có một chủ sở hữu**; không truyền `verifier` cho thread khác giữa các bước. Nếu cần đổi khóa, đổi thuật toán hoặc context, **khởi tạo/configure theo đúng thao tác**, tránh dựa vào state còn lại.

### Vì sao vẫn nên ưu tiên instance mới theo request?

- Dễ chứng minh dữ liệu không bị trộn giữa các request/tenant.
- Giảm lỗi logic do quên `initSign/initVerify`, cấu hình context và các bước `update`.
- Dễ ghi unit test và thay provider.
- Hành vi rõ ràng khi code sau này chuyển từ tuần tự sang song song.

Việc tạo instance mới có chi phí khởi tạo provider nhưng **không phải nguyên nhân đủ để hy sinh đúng đắn của chữ ký**. Nếu cần tối ưu, đo hiệu năng thực tế, theo dõi áp lực provider/HSM và lựa chọn giải pháp có kiểm soát sau khi đã chứng minh an toàn.

## 7. Các phương án thiết kế và rủi ro

| Cách làm | Đánh giá | Lưu ý |
| --- | --- | --- |
| **Tạo `Signature` mới trong mỗi thao tác** | **Khuyến nghị mặc định** | Đơn giản, cô lập state, dễ audit |
| **Một instance theo request** | Tốt nếu request là chủ sở hữu duy nhất | Không chuyển state đó qua luồng song song bất kiểm soát |
| **Một instance theo thread bằng `ThreadLocal`** | Có thể dùng khi đo hiệu năng và quản lý chặt | Thread pool tái sử dụng thread; phải reset/reinit đúng key/params và `remove` theo vòng đời |
| **Một singleton chung với `synchronized`** | Chỉ có thể an toàn nếu khóa trọn *init → update → sign/verify* | Tạo nút cổ chai, khó tránh sơ suất, dễ lộ state |
| **Chỉ `synchronized(update)`** | **Không đủ** | Các thao tác của hai request vẫn có thể xen kẽ giữa các lần update |
| **Chỉ `synchronized(sign)`** | **Không đủ** | Dữ liệu/khóa có thể bị thay trước lúc sign |
| **Clone `Signature` rồi phát cho từng thread** | Không phải giải pháp chung | `clone()` phụ thuộc provider, có thể không được hỗ trợ; vẫn phải cấu hình riêng |
| **Dùng một instance cho mọi thread vì EdDSA deterministic** | **Sai** | Deterministic chỉ nói về đầu ra cùng khóa/message/mode, không nói về thread safety |

### 7.1. Nếu buộc phải dùng synchronized

Cần khóa bao trùm **toàn bộ** phiên:

~~~java
// Minh họa lựa chọn bất đắc dĩ, KHÔNG phải mẫu mặc định.
synchronized (sharedSignature) {
    sharedSignature.initSign(privateKey);
    sharedSignature.update(message);
    return sharedSignature.sign();
}
~~~

Đây là đoạn code **trong một phương thức trả `byte[]`**, không phải chương trình đầy đủ. Mọi đường đi sử dụng `sharedSignature` phải nhất quán với cùng khóa đồng bộ. Nếu có code khác gọi `setParameter`, `initVerify`, `update` hay `sign` **ngoài cùng khóa**, vẫn có race. Ngoài ra, ký tuần tự dưới khóa làm mất tính song song của worker pool.

**Không dùng khóa đồng bộ trên từng phương thức riêng lẻ** rồi cho rằng phiên ký đã an toàn: bản thân chuỗi thao tác mới là đơn vị cần bảo vệ.

### 7.2. `ThreadLocal` không luôn là câu trả lời tốt

`ThreadLocal<Signature>` tạo một phiên riêng cho mỗi thread, nhưng thread pool có thể giữ phiên lâu hơn request. Các trường hợp dễ sai:

- Lần trước dùng private key A, lần sau dùng private key B nhưng quên `initSign(keyB)`.
- Lần trước dùng context Ed25519ctx, lần sau cần pure mode nhưng quên cấu hình đúng.
- Thread pool bị tái sử dụng giữa tenant với thông tin cấu hình cũ.
- Không gọi `ThreadLocal.remove()` ở điểm kết thúc thích hợp gây giữ reference không cần thiết.
- Ứng dụng async chuyển một request qua **nhiều thread**; thread-local không đồng nhất với request-local.

Vì thế `ThreadLocal` chỉ nên xem như **tối ưu sau benchmark**, đi kèm chính sách reset/reinit/cleanup chặt chẽ và kiểm thử với provider cụ thể.

## 8. Java 15+: EdDSA có context/prehash càng cần tách state

Java 15 mang `EdDSAParameterSpec` để chọn chế độ ký theo RFC 8032, ví dụ pure Ed25519, Ed25519ctx hoặc Ed25519ph. Những tham số này là **cấu hình của `Signature`**, cũng không nên bị trộn giữa các request.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;

byte[] context = "invoice:v1".getBytes(StandardCharsets.UTF_8);
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(false, context));
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

Đây là **đoạn minh họa**, giả định `privateKey` và `message` hợp lệ. Bên verify phải cấu hình **đúng cùng mode và byte context** trên một `Signature` **khác**:

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.setParameter(new EdDSAParameterSpec(false, context));
verifier.initVerify(publicKey);
verifier.update(message);
boolean valid = verifier.verify(signed);
~~~

**Không đồng bộ cấu hình bằng cách thay `setParameter` trên một singleton** khi các request cần nhiều context; lời gọi từ tác vụ khác có thể thay đổi state của phiên đang chạy.

Lưu ý liên quan bảo mật:

- `Ed25519` dùng khóa chữ ký; `Ed448` cũng là EdDSA, với kích thước chữ ký khác. Chọn thuật toán cụ thể theo protocol.
- Chế độ **pure**, **ctx**, **ph** phải được thống nhất ở bên ký và bên verify. Prehash không được tự mô phỏng bằng cách băm ngoài rồi ký pure.
- **EdDSA deterministic** không có nghĩa một `Signature` có thể được chia sẻ cho nhiều luồng.
- Message và context đều được xử lý theo **byte**; dùng encoding/canonicalization nhất quán, không suy luận từ cách hiển thị `String`.
- Không ghi private key, private seed hoặc payload nhạy cảm vào log để “debug race”.

## 9. Chương trình Java đầy đủ, có test đồng thời và đối chứng lỗi

Ví dụ này cố ý **không phát sinh race bất định** để chứng minh sai: nó dựng một lịch thực thi xác định trong một thread, cho thấy một `Signature` nếu bị hai tác vụ `update` xen vào sẽ ký sai mục tiêu. Sau đó tạo **24 task trên pool bốn thread**, mỗi thao tác tạo `Signature` mới, cùng dùng cặp khóa Ed25519 để ký/xác minh. Cuối cùng minh họa Ed448.

Lưu thành file **`SignatureThreadSafetyDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

public class SignatureThreadSafetyDemo {
    static byte[] sign(String algorithm, PrivateKey privateKey, byte[] data)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateKey);
        signer.update(data);
        return signer.sign();
    }

    static boolean verify(String algorithm, PublicKey publicKey,
                          byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        byte[] first = "message-A".getBytes(StandardCharsets.UTF_8);
        byte[] second = "message-B".getBytes(StandardCharsets.UTF_8);

        // Mô phỏng SAI: request B update cùng Signature trước khi A gọi sign().
        Signature shared = Signature.getInstance("Ed25519");
        shared.initSign(pair.getPrivate());
        shared.update(first);   // Request A has started.
        shared.update(second);  // Request B interleaves before A signs.
        byte[] mixedSignature = shared.sign();

        byte[] combined = new byte[first.length + second.length];
        System.arraycopy(first, 0, combined, 0, first.length);
        System.arraycopy(second, 0, combined, first.length, second.length);

        System.out.println("mixedVerifiesFirst=" +
                verify("Ed25519", pair.getPublic(), first, mixedSignature));
        System.out.println("mixedVerifiesSecond=" +
                verify("Ed25519", pair.getPublic(), second, mixedSignature));
        System.out.println("mixedVerifiesConcatenation=" +
                verify("Ed25519", pair.getPublic(), combined, mixedSignature));

        // ĐÚNG: có thể dùng tuần tự, không xen kẽ, với cùng key.
        Signature sequentialSigner = Signature.getInstance("Ed25519");
        sequentialSigner.initSign(pair.getPrivate());
        sequentialSigner.update(first);
        byte[] firstSignature = sequentialSigner.sign();
        sequentialSigner.update(second);
        byte[] secondSignature = sequentialSigner.sign();
        System.out.println("sequentialSignaturesValid=" +
                (verify("Ed25519", pair.getPublic(), first, firstSignature)
                 && verify("Ed25519", pair.getPublic(), second, secondSignature)));

        Signature sequentialVerifier = Signature.getInstance("Ed25519");
        sequentialVerifier.initVerify(pair.getPublic());
        sequentialVerifier.update(first);
        boolean firstValid = sequentialVerifier.verify(firstSignature);
        sequentialVerifier.update(second);
        boolean secondValid = sequentialVerifier.verify(secondSignature);
        System.out.println("sequentialVerifyReusable=" + (firstValid && secondValid));

        // ĐÚNG: các tác vụ song song tạo Signature riêng theo thao tác.
        final int taskCount = 24;
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<Boolean>> futures = new ArrayList<>();
        try {
            for (int id = 0; id < taskCount; id++) {
                final int requestId = id;
                futures.add(pool.submit(() -> {
                    byte[] request = ("request-" + requestId)
                            .getBytes(StandardCharsets.UTF_8);
                    byte[] signature = sign("Ed25519", pair.getPrivate(), request);
                    boolean valid = verify(
                            "Ed25519", pair.getPublic(), request, signature);
                    request[0] ^= 1;
                    boolean tamperedValid = verify(
                            "Ed25519", pair.getPublic(), request, signature);
                    return valid && !tamperedValid && signature.length == 64;
                }));
            }
            int passed = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) passed++;
            }
            System.out.println("concurrentTasks=" + taskCount);
            System.out.println("concurrentPassed=" + passed);
        } finally {
            pool.shutdown();
        }

        KeyPair ed448 = KeyPairGenerator.getInstance("Ed448").generateKeyPair();
        byte[] ed448Signature = sign("Ed448", ed448.getPrivate(), first);
        System.out.println("ed448SignatureBytes=" + ed448Signature.length);
        System.out.println("ed448Valid=" +
                verify("Ed448", ed448.getPublic(), first, ed448Signature));

        System.out.println("checks=" +
                (!verify("Ed25519", pair.getPublic(), first, mixedSignature)
                 && verify("Ed25519", pair.getPublic(), combined, mixedSignature)
                 && firstValid && secondValid
                 && verify("Ed25519", pair.getPublic(), first, firstSignature)
                 && verify("Ed25519", pair.getPublic(), second, secondSignature)
                 && ed448Signature.length == 114
                 && verify("Ed448", ed448.getPublic(), first, ed448Signature)));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 SignatureThreadSafetyDemo.java
java SignatureThreadSafetyDemo
~~~

Chương trình dùng API có sẵn từ Java 15, nên cũng biên dịch được với `javac --release 15`. Đã kiểm chứng bằng `--release 15` và `--release 17`, thực thi trên JDK 24 với provider EdDSA của JDK. **Đầu ra thực tế:**

~~~text
mixedVerifiesFirst=false
mixedVerifiesSecond=false
mixedVerifiesConcatenation=true
sequentialSignaturesValid=true
sequentialVerifyReusable=true
concurrentTasks=24
concurrentPassed=24
ed448SignatureBytes=114
ed448Valid=true
checks=true
~~~

### Phân tích đầu ra quan trọng

- `mixedVerifiesFirst=false`: chữ ký “A” đã bị lẫn dữ liệu của B, nên không còn khớp thông điệp A.
- `mixedVerifiesSecond=false`: chữ ký đó cũng không khớp riêng B.
- `mixedVerifiesConcatenation=true`: chữ ký thật sự khớp **A nối B**. Đây là bằng chứng rõ nhất về lỗi trộn `update`, không phụ thuộc scheduling của JVM.
- `sequentialSignaturesValid=true`: tái sử dụng **tuần tự** với cùng private key vẫn hợp lệ sau khi `sign()` reset phiên.
- `sequentialVerifyReusable=true`: tương tự, `verify(...)` có thể được dùng tuần tự trên một đối tượng verifier đã khởi tạo.
- `concurrentTasks=24` và `concurrentPassed=24`: các thao tác đồng thời độc lập thành công; từng task tạo một `Signature` signer và một `Signature` verifier riêng.
- `ed448SignatureBytes=114`, `ed448Valid=true`: cùng mẫu thiết kế áp dụng cho Ed448. Ed25519 có chữ ký raw 64 byte.
- `checks=true`: chương trình đối chiếu các điều kiện ký/xác minh chính.

Ví dụ này **không sử dụng private key cố định**; cặp khóa được tạo mới khi chạy. Byte của chữ ký sẽ thay đổi theo cặp khóa, vì vậy output chỉ in những thuộc tính ổn định và kết quả boolean. Trong ví dụ, request data là mảng riêng của từng task, không có thread khác cùng chỉnh sửa.

**Giới hạn kiểm chứng:** test 24 task chứng tỏ *cách cài đặt minh họa* chạy đúng trên provider/JDK đã nêu; nó không chứng minh tất cả provider/HSM hỗ trợ số lượng phiên đồng thời không giới hạn. Thiết kế ứng dụng phải tách state và tôn trọng tài liệu provider.

## 10. Trường hợp xử lý dữ liệu lớn: nhiều `update` là đúng nếu cùng một request

Không nên nhầm lệnh `Signature.update(...)` nhiều lần là lỗi. Với một file lớn, có thể stream từng chunk **trong cùng một thao tác riêng**:

~~~java
// Đoạn minh họa, path/privateKey đã được xác định theo ứng dụng.
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
try (var in = java.nio.file.Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) signer.update(buffer, 0, n);
    }
}
byte[] signature = signer.sign();
~~~

Vẫn là cùng một phiên, nên hợp lệ: byte của các chunk giữ đúng thứ tự của **một file**. Cái cần tránh là request khác đồng thời gọi `update` vào `signer`.

Khi xử lý streaming asynchronous, hai lựa chọn đáng tin:

1. Đảm bảo **một tác vụ điều khiển toàn bộ trình tự update** và không expose `Signature` ra nhiều callback chạy song song.
2. Hoặc thiết kế bộ gom/luồng byte có thứ tự rõ ràng, đưa đến **một signer riêng cho một message**.

Không lấy các chunk của hai file khác nhau rồi cập nhật xen kẽ vào cùng `Signature` trừ khi **định dạng message thực sự quy định một payload ghép và bên xác minh ký đúng các byte ấy**.

## 11. Lỗi thường gặp khi triển khai production

### 11.1. Singleton `Signature` trong dependency injection container

~~~java
// Sai ở service đồng thời: field mutable được mọi request dùng chung.
private final Signature signature = Signature.getInstance("Ed25519");
~~~

Đây là **mã minh họa bên trong class**; ngoài vấn đề checked exception khi khởi tạo field trong ứng dụng thực tế, điều sai chủ yếu là **phạm vi sống của `Signature` trùng service singleton**, không trùng thao tác.

**Nên làm:** singleton service chỉ giữ configuration, identifier, provider policy và quyền truy cập key; trong mỗi lời gọi method tạo/khởi tạo `Signature` mới.

### 11.2. Chỉ khóa phương thức `sign`, quên `update` và `initSign`

Ngay cả nếu `sign()` được gọi trong `synchronized`, dữ liệu `update` vẫn có thể xen kẽ trước đó. Cần bảo vệ **trọn pipeline** nếu quyết định dùng một instance chung.

### 11.3. Chuyển một `Signature` giữa các task của thread pool

Một `Future` hoặc callback có thể chạy trên thread khác. Nếu toàn bộ `Signature` được share giữa nhiều callback mà không có owner duy nhất, request dễ mất kiểm soát. **Đừng dùng thread name làm định danh của giao dịch ký.**

### 11.4. Tái sử dụng verifier khi đổi public key

Một verifier đã `initVerify(keyA)` sẽ tiếp tục được cấu hình cho key A sau `verify(...)`. Nếu request sau phải dùng key B, không được chỉ gọi `update` và `verify` với chữ ký B. Việc tạo instance mới và `initVerify(keyB)` cho request B tránh lỗi.

### 11.5. Bỏ qua `EdDSAParameterSpec`

Ngay cả khi hai request có cùng private key Ed25519, context khác nhau có thể tạo chữ ký khác nhau. Nếu dùng chung instance và thay `setParameter` đan xen, chữ ký có thể gắn sai domain. **Mỗi phiên nên chứa trọn bộ thuật toán, key, mode, context và message bytes thuộc request đó.**

### 11.6. Trộn `String` với byte mà không quy định encoding

Chữ ký kiểm tra **byte**. Nếu request A encode UTF-8, request B lại thay đổi normalization/canonical JSON, signature có thể không khớp dù nội dung nhìn giống nhau. Định rõ encoding, định dạng dữ liệu được ký và phiên bản canonicalization; đây là lỗi độc lập với race và cũng cần được kiểm thử.

### 11.7. Dùng `Signature` cùng lúc vì Ed25519 “deterministic”

EdDSA deterministic nghĩa là **cùng key + cùng message bytes + cùng biến thể/context → cùng signature**; không nghĩa instance `Signature` trở thành bất biến hoặc tự hỗ trợ concurrency. Chỉ sử dụng deterministic property cho kiểm chứng/troubleshooting phù hợp.

### 11.8. Xem mọi lần `verify=false` là lỗi race

`verify=false` có thể do message bị sửa, sai public key, sai context, sai encoding, không khớp thuật toán hoặc đơn giản là chữ ký không hợp lệ. **Không kết luận race chỉ từ `false`**. Cần xác nhận sự cô lập phiên, kiểm tra byte đầu vào và các thành phần giao thức. Đồng thời không in khóa riêng hoặc dữ liệu bí mật ra log để debug.

## 12. Kiểm thử thiết kế nhiều luồng và khả năng quan sát

**Bộ kiểm thử nên có:**

| Nhóm test | Kỳ vọng |
| --- | --- |
| Ký/xác minh một request | Kết quả `true` với public key đúng |
| Sửa một byte message | `verify` trả `false` (hoặc xử lý lỗi định dạng theo provider) |
| Dùng sai public key | Không xác minh thành công |
| Ký nhiều request **song song** | Mỗi chữ ký chỉ xác minh đối với đúng dữ liệu của request đó |
| Mô phỏng xen kẽ `update` trên **instance chung** | Chứng minh dữ liệu ghép có thể tạo chữ ký sai mục tiêu |
| Ký rồi ký tiếp **tuần tự** | Hợp lệ nếu dùng đúng reset/reinit |
| Verify rồi verify tiếp **tuần tự** | Hợp lệ với cùng key và mỗi message được update riêng |
| Đổi thuật toán, key, mode, context | Không có state cũ ảnh hưởng thao tác mới |
| HSM/provider giới hạn phiên | Có chính sách queue, backpressure, timeout và error handling |
| Message đa byte Unicode | Encoding và các byte được ký phải xác định |

**Dấu hiệu quan sát** hữu ích: mã yêu cầu không nhạy cảm, key ID *không chứa khóa bí mật*, thuật toán, mode/context ID, số byte message, loại lỗi/latency, provider name. Không lưu private seed, nội dung nhạy cảm hoặc toàn bộ signature theo mặc định nếu không có chính sách thích hợp.

Nếu nghi có race, có thể thêm test interleaving **có điều khiển** ở layer nghiệp vụ (latch/barrier chỉ để xác định thứ tự), nhưng **không** thiết kế test dựa vào provider phải phát sinh kết quả hỏng trong một lần race: kết quả không được Java SE bảo đảm và có thể khác trên các máy.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Hai task dùng cùng `Signature`, mỗi task gọi tuần tự `initSign → update → sign`. Có an toàn nếu các task thực thi đồng thời?  
**Đáp án:** **không thể giả định**. Các lệnh của hai task có thể xen kẽ; cả chuỗi không atomic.

**Câu 2.** Có thể dùng một `Signature` để ký nhiều message không?  
**Đáp án:** **có, theo thứ tự tuần tự và đúng trạng thái**. `sign()` reset phiên về trạng thái sau `initSign`, sau đó có thể `update` message mới. Điều này **không cấp quyền dùng chung đồng thời**.

**Câu 3.** Chỉ thêm `synchronized` quanh `sign()` có đủ không?  
**Đáp án:** **không**. Phải bảo vệ `initSign`, mọi `update`, cấu hình và `sign` như **một giao dịch duy nhất**, nếu vẫn dùng instance chung.

**Câu 4.** `ThreadLocal<Signature>` có tự bảo đảm không lẫn context giữa hai request không?  
**Đáp án:** **không**. Thread pool có thể tái sử dụng thread; cần reinit/reset và xử lý mọi tham số/cleanup đúng cách.

**Câu 5.** Có thể chia sẻ cặp khóa Ed25519 giữa nhiều thao tác song song nhưng tạo `Signature` riêng cho mỗi thao tác không?  
**Đáp án:** **có trong môi trường/provider hỗ trợ việc đó**, và đó là mẫu được ví dụ áp dụng. Với HSM/provider đặc thù, phải tuân thủ chính sách concurrency của chúng.

**Câu 6.** Vì sao ví dụ in `mixedVerifiesConcatenation=true` trong khi riêng A và B đều `false`?  
**Đáp án:** cả hai lượt `update` đã tích lũy vào **cùng một `Signature` trước khi gọi `sign`**, nên chữ ký thuộc byte `A||B`, không thuộc A hay B.

## Tài liệu chính thức còn áp dụng

- **Oracle Java SE 26 — `java.security.Signature`**: trạng thái UNINITIALIZED/SIGN/VERIFY; `initSign`, `initVerify`, `update`, `sign`, `verify` và reset sau sign/verify. https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html
- **Oracle Java SE 25 — Security Developer's Guide**, cơ chế trạng thái của đối tượng `Signature` và quy trình ký/xác minh: https://docs.oracle.com/en/java/javase/25/security/security-developer-guide.pdf
- **OpenJDK JEP 339 — EdDSA**, hỗ trợ `Ed25519`/`Ed448` được đưa vào Java 15: https://openjdk.org/jeps/339
- **Oracle Java SE 26 — `EdDSAParameterSpec`**, cấu hình prehash/context theo RFC 8032: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- **Oracle Java SE 26 — `ExecutorService`**, các mẫu thực thi tác vụ song song: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **RFC 8032**, chuẩn Ed25519/Ed448, chữ ký deterministic và các biến thể context/prehash: https://www.rfc-editor.org/rfc/rfc8032