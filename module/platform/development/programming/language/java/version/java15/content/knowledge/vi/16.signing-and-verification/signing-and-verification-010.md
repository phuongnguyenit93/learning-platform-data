# Trạng thái của Signature sau thao tác ký, xác minh trong Java 15

> **Mục tiêu:** Hiểu vòng đời và máy trạng thái của `java.security.Signature`: tạo object, `initSign`/`initVerify`, nhiều lần `update`, `sign`/`verify`, **tự reset về trạng thái đã khởi tạo sau khi hoàn tất thao tác**, tái sử dụng với cùng khóa và khởi tạo lại khi đổi khóa/vai trò. Các ví dụ dùng **Ed25519 và Ed448 chính thức từ Java 15** để minh họa trên **Java 17+**. Chỉ trình bày API và kiến thức **vẫn còn áp dụng trong Java hiện đại**, không dùng thuật toán hay cú pháp đã lỗi thời.

## 1. Kết luận quan trọng nhất

Theo hợp đồng của `java.security.Signature` trên Java hiện đại:

- Sau khi gọi **`sign()` thành công**, object `Signature` được **reset về trạng thái sau `initSign(privateKey)`**. Nó vẫn ở chế độ **SIGN**, với khóa ký đã khởi tạo, và có thể thực hiện `update(...)`/`sign()` tiếp theo.
- Sau khi gọi **`verify(signature)` thành công về mặt thực thi** (trả `true` **hoặc** `false`), object được **reset về trạng thái sau `initVerify(publicKey)`**. Nó vẫn ở chế độ **VERIFY**, với public key đã khởi tạo, và sẵn sàng cho dữ liệu/chữ ký tiếp theo.
- **Những bytes đã đưa vào `update` cho lượt trước không được cộng dồn sang lượt tiếp theo.** Lượt mới phải gọi `update` với **toàn bộ thông điệp mới**; nếu bỏ qua `update`, một số thuật toán/provider vẫn có thể xử lý **thông điệp rỗng**.
- `sign()` **không chuyển** object thành trạng thái VERIFY; `verify()` **không chuyển** object thành trạng thái SIGN. Muốn đổi vai trò phải gọi `initVerify(...)` hoặc `initSign(...)`.
- Tự reset sau hoàn tất **không đồng nghĩa dùng chung một `Signature` cho nhiều luồng hoặc nhiều request là an toàn**. `Signature` là một đối tượng có trạng thái thay đổi, cần quản lý vòng đời và đồng bộ hóa theo thiết kế.

Đây là **hợp đồng chung của `Signature`**, không phải chức năng lần đầu xuất hiện ở Java 15. Điểm liên hệ với **module Java 15** là **EdDSA/Ed25519/Ed448 được chuẩn hóa ở JDK 15 (JEP 339)** và là các thuật toán đang được dùng để kiểm nghiệm chính xác hợp đồng đó.

## 2. Ba trạng thái chính và ý nghĩa của chúng

API `Signature` có khái niệm ba trạng thái nội bộ:

| Trạng thái | Đạt được khi nào? | Được làm gì? | Không nên làm gì? |
| --- | --- | --- | --- |
| **UNINITIALIZED** | Sau `Signature.getInstance(...)`, trước lần khởi tạo thích hợp | `initSign` hoặc `initVerify` | Gọi `update`/`sign`/`verify` khi chưa khởi tạo |
| **SIGN** | Sau `initSign(PrivateKey)` | `update` với bytes cần ký, `sign` để sinh chữ ký; có thể ký tiếp sau hoàn tất | `verify` với object chưa chuyển sang VERIFY |
| **VERIFY** | Sau `initVerify(PublicKey)` | `update` với bytes cần kiểm tra, `verify` chữ ký; có thể xác minh tiếp sau hoàn tất | `sign` với object chưa chuyển sang SIGN |

Sơ đồ:

~~~text
Signature.getInstance("Ed25519")
           |
           v
      UNINITIALIZED
        /       \
 initSign(key)  initVerify(key)
      |               |
      v               v
     SIGN           VERIFY
      |               |
 update(bytes)    update(bytes)
      |               |
   sign()         verify(sig)
      |               |
      +-- reset --> SIGN
                      ^
                      |
                      +-- reset về VERIFY sau verify
~~~

Nhãn minh họa bên phải cần đọc như hai vòng lặp **độc lập**: `sign()` quay về **SIGN**; `verify()` quay về **VERIFY**. Không có cạnh chuyển tự động từ SIGN sang VERIFY hoặc ngược lại. Để tránh hiểu nhầm hình vẽ, có thể diễn đạt gọn hơn bằng bảng chuyển trạng thái:

| Trước thao tác | Gọi | Khi hoàn tất bình thường |
| --- | --- | --- |
| UNINITIALIZED | `initSign(privateKey)` | SIGN, dữ liệu đang chờ ký rỗng |
| UNINITIALIZED hoặc SIGN hoặc VERIFY | `initVerify(publicKey)` | VERIFY, dữ liệu đang chờ xác minh rỗng |
| UNINITIALIZED hoặc VERIFY hoặc SIGN | `initSign(privateKey)` | SIGN, dữ liệu đang chờ ký rỗng |
| SIGN | `update(bytes)` | Vẫn SIGN, thêm bytes vào **lượt hiện tại** |
| SIGN | `sign()` | Trả chữ ký, reset về SIGN sau khởi tạo |
| VERIFY | `update(bytes)` | Vẫn VERIFY, thêm bytes vào **lượt hiện tại** |
| VERIFY | `verify(signature)` trả true hoặc false | Trả kết quả, reset về VERIFY sau khởi tạo |
| UNINITIALIZED hoặc VERIFY | `sign()` | Không hợp lệ; ném `SignatureException` |
| UNINITIALIZED hoặc SIGN | `verify(signature)` | Không hợp lệ; ném `SignatureException` |

**Quan trọng:** `UNINITIALIZED`, `SIGN` và `VERIFY` là tên mô tả trạng thái API/Javadoc; người sử dụng không nên truy cập trường `protected state`, ép xuống lớp triển khai hoặc phân tích `toString()` để điều khiển logic. Cách đúng là quản lý trạng thái bằng luồng lời gọi `initSign`/`initVerify` trong code.

## 3. Luồng ký lần đầu: `initSign → update → sign`

Ví dụ dùng khóa Ed25519 đã tạo:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(keyPair.getPrivate());
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Đây là **đoạn code đặt trong method** đã có `keyPair` và `messageBytes`, với exceptions được khai báo hoặc xử lý. Chương trình chạy hoàn chỉnh có ở mục 7.

Cơ chế:

1. `getInstance("Ed25519")` tạo một **engine `Signature` chưa khởi tạo**; nó chưa nắm private key và chưa biết cần ký bytes nào.
2. `initSign(privateKey)` chọn khóa và đưa engine vào chế độ **SIGN**.
3. Một hoặc nhiều `update` đưa bytes của **thông điệp hiện tại** vào engine; thứ tự và nội dung bytes rất quan trọng.
4. `sign()` hoàn tất việc ký, trả bytes chữ ký và **reset engine về trạng thái như sau `initSign`**.
5. Có thể gọi `update(secondMessage)` và `sign()` ngay trên **cùng engine** để ký thông điệp thứ hai bằng cùng private key.

Điều này **không yêu cầu** khởi tạo lại khóa trước mỗi lượt ký **nếu** việc tái sử dụng cùng khóa và cùng tham số là chủ đích, mọi lời gọi hoàn tất thành công và không có truy cập cạnh tranh. Tuy vậy, một hàm ký nhận nhiều request từ các bên khác nhau thường nên tạo engine mới cho từng lượt để quản lý trạng thái dễ hơn.

### Nhiều lần `update` là nối bytes trong **cùng lượt**

~~~java
signer.initSign(privateKey);
signer.update(headerBytes);
signer.update(payloadBytes);
byte[] combined = signer.sign();
~~~

Đoạn code trên ký **sự nối tiếp** `headerBytes || payloadBytes` theo thứ tự gửi vào; không sinh hai chữ ký. Muốn ký hai thông điệp độc lập, phải có một lần `sign()` ở giữa:

~~~java
signer.update(firstMessage);
byte[] sigFirst = signer.sign(); // hoàn tất lượt 1 và reset

signer.update(secondMessage);
byte[] sigSecond = signer.sign(); // hoàn tất lượt 2 và reset
~~~

**Không được suy luận rằng `update` tự reset**. `update` chỉ thêm dữ liệu. **`sign` và `verify`** là các thao tác hoàn tất lượt và đưa engine về trạng thái đã khởi tạo theo hợp đồng.

## 4. Luồng xác minh: `initVerify → update → verify`

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(keyPair.getPublic());
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
~~~

`verify(signature)` kiểm tra chữ ký trên **tất cả bytes đã update trong lượt này**, dùng public key đã chọn.

Khi `verify` trả:

- **`true`:** chữ ký hợp lệ cho bytes, thuật toán/mode, tham số và public key đang sử dụng.
- **`false`:** chữ ký **không khớp** (ví dụ message bị sửa, sai public key, context không khớp); đây là kết quả xác minh không thành công, **không tự động là exception**.
- **`SignatureException`:** có lỗi thao tác, chữ ký sai format hoặc loại không hỗ trợ, engine không ở trạng thái hợp lệ, provider không xử lý được input... Không đồng nhất lỗi kỹ thuật với kết quả `false`.

**Sau lời gọi `verify` trả true hoặc false**, engine được reset về **VERIFY với public key cũ**; vì vậy có thể tiếp tục:

~~~java
verifier.update(secondMessage);
boolean secondValid = verifier.verify(secondSignature);
~~~

Không cần `initVerify` lần nữa nếu **chính public key đó** vẫn là key đúng, mode/params không thay đổi và không có lỗi làm trạng thái provider không rõ ràng. Nhưng **phải `update` lại bytes của message thứ hai**.

### Xác minh sai một lần có “làm hỏng” verifier không?

**Không**, nếu `verify` hoàn tất và trả `false` theo hợp đồng. Một verifier có thể xác minh sai ở lượt N và xác minh đúng ở lượt N+1:

~~~java
verifier.update(tamperedMessage);
boolean invalid = verifier.verify(expectedSignature); // false

verifier.update(originalMessage);
boolean valid = verifier.verify(expectedSignature);    // true
~~~

Đoạn code này giả định `expectedSignature` thực sự được ký cho `originalMessage` bằng private key tương ứng. Độ chính xác của kết quả cần dựa trên dữ liệu test cụ thể; chương trình mục 7 kiểm chứng trường hợp Ed25519 và Ed448.

**Ngoại lệ quan trọng:** Tuyên bố “reset” ở trên áp dụng cho lời gọi `sign`/`verify` **hoàn tất theo hợp đồng**. Khi lời gọi **ném exception**, không được mặc định mọi provider đã khôi phục y hệt trạng thái ban đầu. Cách an toàn sau lỗi provider/crypto là **bỏ engine đó và tạo/khởi tạo mới** trước khi xử lý một thông điệp khác.

## 5. Sai lầm nguy hiểm: lượt mới không có `update`

Sau `sign()`, trạng thái dữ liệu được reset. Nếu gọi tiếp:

~~~java
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] forMessage = signer.sign();

byte[] withoutUpdate = signer.sign();
~~~

thì lượt thứ hai **không ký lại `messageBytes`**. Với Ed25519/Ed448 trong môi trường đã kiểm thử, lời gọi `sign()` thứ hai ký **thông điệp rỗng** vì không có bytes mới được update.

Chương trình mục 7 xác minh:

~~~text
emptyMessageAfterSign=true
~~~

bằng cách so bytes chữ ký sau `sign()` lần thứ hai (không `update`) với kết quả từ **một engine mới ký `new byte[0]`** bằng cùng khóa và thuật toán.

**Tác động nghiệp vụ:** Nếu code thực hiện `update`/`sign` ở nhiều nhánh điều kiện và một nhánh quên `update`, hệ thống có thể tạo **chữ ký hợp lệ về toán học cho thông điệp sai** thay vì báo lỗi. Đừng dùng khả năng “ký rỗng” làm chỉ báo trạng thái hay kiểm tra rằng dữ liệu đã được gửi.

Hàm ký tốt nên luôn nhận `byte[]` hoặc một định dạng message rõ ràng, kiểm tra preconditions và thực hiện đủ `initSign → update → sign` trong một scope dễ audit.

## 6. Phân biệt reset tự động, khởi tạo lại và thay đổi khóa

| Tình huống | Cần `initSign`/`initVerify` lại? | Lý do |
| --- | --- | --- |
| Ký lần hai bằng cùng private key, không đổi mode/params, lượt trước hoàn tất | **Không bắt buộc** | `sign` đã reset về SIGN |
| Xác minh lần hai bằng cùng public key, lượt trước trả true | **Không bắt buộc** | `verify` đã reset về VERIFY |
| Xác minh lần hai sau `verify` trả false | **Không bắt buộc** nếu không có exception và vẫn cùng key | `verify` trả false cũng hoàn tất một lượt |
| Ký với **private key khác** | **Có: `initSign(newKey)`** | Phải chọn danh tính người ký mới |
| Xác minh với **public key khác** | **Có: `initVerify(newKey)`** | Phải đổi khóa đối tác |
| Muốn từ SIGN sang VERIFY | **Có: `initVerify(publicKey)`** | `sign` không tự đổi vai trò |
| Muốn từ VERIFY sang SIGN | **Có: `initSign(privateKey)`** | `verify` không tự đổi vai trò |
| Đổi algorithm | **Tạo engine với `getInstance(newAlgorithm)`** | `getAlgorithm()` là thuộc tính của engine; `initSign` không biến Ed25519 thành Ed448 |
| Đổi EdDSA mode/context | Thiết lập `EdDSAParameterSpec` phù hợp và khởi tạo lại theo provider | Mode/context phải khớp ở hai đầu |
| Lần trước ném exception bất thường | **Nên tạo engine mới/khởi tạo lại** | Không giả định trạng thái provider sau lỗi |

**Khởi tạo lại không “nhặt lại bytes còn chờ”.** Khi gọi `initSign` với khóa khác giữa chừng, các bytes đang được `update` cho lượt cũ không được ký như một phần của lượt mới. Ví dụ đã kiểm thử ở mục 9 xác nhận `initSign(secondKey)` đưa engine về trạng thái mới chỉ có key thứ hai, không đem message pending cũ qua.

**Đừng dùng `Signature.sign()` để “xả dữ liệu và đổi chế độ”.** Nó **tạo ra một chữ ký**, không phải API reset thủ công. Khi cần bỏ lượt dở dang hoặc đổi key/mode, thiết kế code nên tạo engine mới hoặc khởi tạo lại rõ ràng.

## 7. Chương trình Java 17+ đầy đủ: kiểm chứng mọi trạng thái với Ed25519 và Ed448

Tạo file **SignatureLifecycleDemo.java**; không cần thư viện ngoài JDK. Chương trình:

1. Kiểm tra `update` trước `initSign` gây `SignatureException`.
2. Ký hai thông điệp bằng **cùng `Signature` không `initSign` lại**.
3. So chữ ký với engine mới; xác minh không có dữ liệu lượt trước bị cộng dồn.
4. Gọi `sign()` khi không có `update`, xác định chữ ký của empty message.
5. Xác minh success, tampering failure, rồi tiếp tục verify success.
6. Dùng các overload `sign(outbuf, offset, len)` / `verify(sig, offset, len)`.
7. Dùng `update(ByteBuffer)` và kiểm tra vị trí buffer.
8. Chuyển một object từ SIGN sang VERIFY, kiểm tra gọi sai hướng, rồi chuyển lại.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;

public class SignatureLifecycleDemo {
    static byte[] message(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] freshSignature(PrivateKey key, String algorithm,
            byte[] data) throws Exception {
        Signature fresh = Signature.getInstance(algorithm);
        fresh.initSign(key);
        fresh.update(data);
        return fresh.sign();
    }

    static void run(NamedParameterSpec parameters) throws Exception {
        String algorithm = parameters.getName();
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(parameters);
        KeyPair pair = generator.generateKeyPair();
        byte[] first = message("invoice:001");
        byte[] second = message("invoice:002");
        byte[] tampered = message("invoice:999");

        Signature uninitialized = Signature.getInstance(algorithm);
        String uninitUpdate;
        try {
            uninitialized.update(first);
            uninitUpdate = "UNEXPECTED";
        } catch (SignatureException expected) {
            uninitUpdate = "SignatureException";
        }

        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(pair.getPrivate());
        signer.update(first);
        byte[] sigFirst = signer.sign();

        signer.update(second);
        byte[] sigSecond = signer.sign();

        boolean firstMatchesFresh = Arrays.equals(sigFirst,
                freshSignature(pair.getPrivate(), algorithm, first));
        boolean secondMatchesFresh = Arrays.equals(sigSecond,
                freshSignature(pair.getPrivate(), algorithm, second));
        byte[] sigEmpty = signer.sign();
        boolean emptyMatchesFresh = Arrays.equals(sigEmpty,
                freshSignature(pair.getPrivate(), algorithm, new byte[0]));

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(pair.getPublic());
        verifier.update(first);
        boolean verifiedFirst = verifier.verify(sigFirst);
        verifier.update(second);
        boolean verifiedSecond = verifier.verify(sigSecond);
        verifier.update(tampered);
        boolean tamperedRejected = !verifier.verify(sigSecond);
        verifier.update(second);
        boolean recoveredAfterFalse = verifier.verify(sigSecond);
        boolean emptyMessageRejected = !verifier.verify(sigFirst);

        byte[] out = new byte[algorithm.equals("Ed25519") ? 80 : 130];
        signer.update(first);
        int written = signer.sign(out, 7, out.length - 7);
        verifier.update(first);
        boolean sliceVerified = verifier.verify(out, 7, written);
        signer.update(second);
        boolean afterBufferedSign = Arrays.equals(signer.sign(), sigSecond);

        ByteBuffer slice = ByteBuffer.wrap(new byte[] {12, 13, 14, 15});
        slice.position(1);
        slice.limit(3);
        signer.update(slice);
        byte[] sliceSignature = signer.sign();
        verifier.update(new byte[] {13, 14});
        boolean byteBufferVerified = verifier.verify(sliceSignature);

        signer.initVerify(pair.getPublic());
        signer.update(first);
        boolean switchedToVerify = signer.verify(sigFirst);
        String signInVerifyMode;
        try {
            signer.sign();
            signInVerifyMode = "UNEXPECTED";
        } catch (SignatureException expected) {
            signInVerifyMode = "SignatureException";
        }
        signer.initSign(pair.getPrivate());
        signer.update(first);
        boolean switchedBackToSign = Arrays.equals(signer.sign(), sigFirst);

        System.out.println("algorithm=" + algorithm);
        System.out.println("uninitializedUpdate=" + uninitUpdate);
        System.out.println("firstMatchesFresh=" + firstMatchesFresh);
        System.out.println("secondMatchesFresh=" + secondMatchesFresh);
        System.out.println("oldMessageWasNotAppended="
                + !Arrays.equals(sigFirst, sigSecond));
        System.out.println("emptyMessageAfterSign=" + emptyMatchesFresh);
        System.out.println("verifyFirst=" + verifiedFirst);
        System.out.println("verifySecond=" + verifiedSecond);
        System.out.println("tamperedRejected=" + tamperedRejected);
        System.out.println("recoveredAfterFalse=" + recoveredAfterFalse);
        System.out.println("emptyMessageRejected=" + emptyMessageRejected);
        System.out.println("bufferedSignBytes=" + written);
        System.out.println("bufferedSignVerified=" + sliceVerified);
        System.out.println("afterBufferedSign=" + afterBufferedSign);
        System.out.println("byteBufferPositionAtLimit="
                + (slice.position() == slice.limit()));
        System.out.println("byteBufferVerified=" + byteBufferVerified);
        System.out.println("switchedToVerify=" + switchedToVerify);
        System.out.println("signInVerifyMode=" + signInVerifyMode);
        System.out.println("switchedBackToSign=" + switchedBackToSign);
    }

    public static void main(String[] args) throws Exception {
        run(NamedParameterSpec.ED25519);
        run(NamedParameterSpec.ED448);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
~~~

**Stdout đã kiểm thử thực tế với JDK hỗ trợ Ed25519/Ed448:**

~~~text
algorithm=Ed25519
uninitializedUpdate=SignatureException
firstMatchesFresh=true
secondMatchesFresh=true
oldMessageWasNotAppended=true
emptyMessageAfterSign=true
verifyFirst=true
verifySecond=true
tamperedRejected=true
recoveredAfterFalse=true
emptyMessageRejected=true
bufferedSignBytes=64
bufferedSignVerified=true
afterBufferedSign=true
byteBufferPositionAtLimit=true
byteBufferVerified=true
switchedToVerify=true
signInVerifyMode=SignatureException
switchedBackToSign=true
algorithm=Ed448
uninitializedUpdate=SignatureException
firstMatchesFresh=true
secondMatchesFresh=true
oldMessageWasNotAppended=true
emptyMessageAfterSign=true
verifyFirst=true
verifySecond=true
tamperedRejected=true
recoveredAfterFalse=true
emptyMessageRejected=true
bufferedSignBytes=114
bufferedSignVerified=true
afterBufferedSign=true
byteBufferPositionAtLimit=true
byteBufferVerified=true
switchedToVerify=true
signInVerifyMode=SignatureException
switchedBackToSign=true
~~~

### Phân tích cụ thể stdout

- **`uninitializedUpdate=SignatureException`:** `getInstance` chưa chọn private/public key; không thể `update`.
- **`firstMatchesFresh=true` và `secondMatchesFresh=true`:** chữ ký từng lượt từ **engine tái sử dụng** giống chữ ký từ **engine mới** dùng cùng key+message. Đây là phép kiểm chứng mạnh rằng bytes của lượt trước đã được reset.
- **`oldMessageWasNotAppended=true`:** hai thông điệp khác nhau cho chữ ký khác nhau. Để chứng minh **không cộng dồn**, nên nhìn cả `secondMatchesFresh=true`, không chỉ sự khác biệt của chữ ký.
- **`emptyMessageAfterSign=true`:** gọi `sign()` ngay sau một lần `sign()` mà không `update` đã ký **empty message** trong hai thuật toán được kiểm thử.
- **`verifyFirst` và `verifySecond` đều true:** verifier dùng cùng public key có thể tiếp tục xác minh nhiều chữ ký.
- **`tamperedRejected=true` rồi `recoveredAfterFalse=true`:** kết quả `verify=false` không “khóa” engine hay làm mất chế độ VERIFY.
- **`emptyMessageRejected=true`:** sau lượt verify, không `update` mà lại verify chữ ký của message khác thì không khớp; chứng minh dữ liệu cũ không tồn đọng.
- **`bufferedSignBytes=64/114`:** Ed25519 và Ed448 có signature sizes lần lượt 64 và 114 byte theo RFC 8032.
- **`bufferedSignVerified` và `afterBufferedSign` đều true:** `sign(outbuf,off,len)` cũng reset về SIGN, không chỉ `sign()` trả `byte[]`.
- **`byteBufferPositionAtLimit=true`:** `update(ByteBuffer)` đọc từ current position tới limit và **di chuyển position tới limit**. `byteBufferVerified=true` chứng minh đúng hai bytes được ký.
- **`switchedToVerify=true`:** `initVerify` chuyển signer đang dùng sang VERIFY và xác minh được.
- **`signInVerifyMode=SignatureException`:** sau khi chuyển sang VERIFY không thể gọi `sign` mà không `initSign`.
- **`switchedBackToSign=true`:** `initSign` chọn lại chế độ SIGN, ký được bằng khóa cũ.

**Bài học về test:** Chương trình dùng **EdDSA deterministic** nên so sánh hai chữ ký trên cùng khóa/message bằng `Arrays.equals` là phù hợp cho mode đã chọn. Với các signature schemes sử dụng randomness, không nên dùng “hai lần ký phải sinh bytes giống nhau” như một kiểm thử phổ quát; hãy **verify đúng message/key** để kiểm chứng trạng thái.

## 8. Overload có buffer: `sign(outbuf, offset, len)` và `verify(sig, offset, len)`

Ngoài `byte[] sign()` và `boolean verify(byte[])`, Java hỗ trợ các overload làm việc với **một đoạn trong array**:

~~~java
byte[] output = new byte[80]; // Ed25519 signature 64 bytes
signer.update(messageBytes);
int bytesWritten = signer.sign(output, 8, output.length - 8);

verifier.update(messageBytes);
boolean ok = verifier.verify(output, 8, bytesWritten);
~~~

Đây là đoạn code **trong method** với `signer` đã initSign và `verifier` đã initVerify bằng khóa tương ứng.

- Với `sign(outbuf, offset, len)`, `len` là **số byte dành ra cho chữ ký ở vị trí offset**, không nhất thiết bằng `outbuf.length`.
- Kết quả `bytesWritten` cho biết **số bytes thực sự đã ghi**, quan trọng nếu cùng buffer dùng cho nhiều trường.
- Với `verify(sig, offset, length)`, `length` là **độ dài bytes chữ ký cần đọc** từ `offset`.
- `sign(outbuf, offset, len)` hoàn tất lượt ký và **reset về SIGN** như `sign()`.
- `verify(sig, offset, length)` hoàn tất lượt xác minh và **reset về VERIFY** như `verify(sig)`.

**Lỗi và giới hạn:** Offset/len không hợp lệ hoặc vượt giới hạn array bị từ chối bằng `IllegalArgumentException`. Nếu vùng `outbuf` không đủ chứa chữ ký thực tế, `sign(outbuf, offset, len)` có thể ném `SignatureException`. Không giả định trạng thái sau **một ngoại lệ** là reset đúng như khi thao tác thành công; khởi tạo engine mới nếu phát hiện lỗi.

Với thuật toán/giao thức khác, signature length không phải luôn 64/114; ứng dụng nên lấy kích thước theo scheme hoặc dùng `sign()` trả về array nếu không cần điền vào một buffer đã cấp phát.

## 9. `update(ByteBuffer)` và hậu quả của vị trí buffer

Javadoc `Signature.update(ByteBuffer)` nói rõ nó xử lý **`data.remaining()` bytes từ `position()` đến `limit()`**, và sau khi hoàn tất **position bằng limit**, limit không đổi.

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {12, 13, 14, 15});
buffer.position(1);
buffer.limit(3);

signer.update(buffer);
// Hai bytes đã update: {13, 14}.
System.out.println(buffer.position() == buffer.limit()); // true
~~~

**Không nhầm:**

- `update(ByteBuffer)` không tự ký/xác minh; vẫn phải gọi `sign`/`verify`.
- Buffer đã được tiêu thụ phần `remaining`. Nếu định đưa chính bytes ấy vào một lượt mới, cần **chuẩn bị buffer ở vị trí phù hợp** hoặc dùng `duplicate()/slice()` khi muốn quản lý vị trí độc lập.
- Sau `sign`, dữ liệu nội bộ engine reset; **vị trí của `ByteBuffer` không tự rewind**. Đây là hai trạng thái của **hai object khác nhau**.
- Nếu buffer là mutable và được thread khác thay đổi khi đang ký, dữ liệu ký có thể không nhất quán; hãy quản lý ownership hoặc copy snapshot khi cần.

Ở chương trình mục 7, `byteBufferPositionAtLimit=true` và `byteBufferVerified=true` xác nhận provider ký chính xác phần bytes `{13,14}` khi buffer có position=1, limit=3.

## 10. State không đồng nghĩa key, mode và context được đổi tự động

Với EdDSA, có ít nhất ba chiều cấu hình khác nhau:

1. **Thuật toán/curve:** `Ed25519` hoặc `Ed448`; chọn qua `Signature.getInstance(...)` và key phù hợp.
2. **Khóa:** private key cho SIGN, public key cho VERIFY; chọn qua `initSign`/`initVerify`.
3. **Signature parameters:** có thể bao gồm **context và prehash** từ `EdDSAParameterSpec`, tùy mode/giao thức.

Lời gọi `sign`/`verify` **không tự đổi** các chiều này chỉ vì đã kết thúc một message. Nó reset về trạng thái đã khởi tạo cho **cùng vai trò và key**, với tham số thích hợp mà provider đã cấu hình.

Khi cần **đổi thông điệp** nhưng giữ cùng key/mode, việc tái sử dụng đúng hợp đồng là có thể. Khi cần **đổi khóa, đổi algorithm, đổi context/prehash hoặc đổi vai trò**, hãy **cấu hình/khởi tạo lại rõ ràng**; nhiều ứng dụng nên chọn một engine mới per operation.

### Context của EdDSA là gì?

Từ Java 15 có `java.security.spec.EdDSAParameterSpec`. Ví dụ:

~~~java
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;

Signature signer = Signature.getInstance("EdDSA");
byte[] context = "orders-v1".getBytes(StandardCharsets.US_ASCII);

signer.setParameter(new EdDSAParameterSpec(false, context));
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

Đây là code **trong method**; cần import `StandardCharsets`, có `privateKey`/`message`. `false` là **không sử dụng prehash mode**, và `context` ràng buộc signature với một miền sử dụng đã xác định. EdDSA có các biến thể **Ed25519ctx/Ed25519ph, Ed448/Ed448ph** theo RFC 8032. Bên xác minh phải dùng **đúng curve, key, message, context và mode**.

**Lưu ý:** `context` là **byte array** có độ dài tối đa 255 bytes, không phải 255 ký tự Unicode. Không tự hash message bên ngoài rồi gọi pure EdDSA và gọi đó là “ph”; muốn mode prehash, dùng tham số được provider hỗ trợ theo RFC.

## 11. Chương trình thứ hai: reuse khi có context và thay private key

Tạo file **SignatureContextStateDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;

public class SignatureContextStateDemo {
    static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] singleSign(KeyPair kp, byte[] message, byte[] context)
            throws Exception {
        Signature signer = Signature.getInstance("EdDSA");
        signer.setParameter(new EdDSAParameterSpec(false, context));
        signer.initSign(kp.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(KeyPair kp, byte[] message,
            byte[] signature, byte[] context) throws Exception {
        Signature v = Signature.getInstance("EdDSA");
        v.setParameter(new EdDSAParameterSpec(false, context));
        v.initVerify(kp.getPublic());
        v.update(message);
        return v.verify(signature);
    }

    static void run(NamedParameterSpec curve) throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("EdDSA");
        g.initialize(curve);
        KeyPair firstKey = g.generateKeyPair();
        KeyPair secondKey = g.generateKeyPair();
        byte[] one = bytes("order:1");
        byte[] two = bytes("order:2");
        byte[] context = bytes("orders-v1");
        byte[] otherContext = bytes("payments-v1");

        Signature sign = Signature.getInstance("EdDSA");
        sign.setParameter(new EdDSAParameterSpec(false, context));
        sign.initSign(firstKey.getPrivate());
        sign.update(one);
        byte[] sigOne = sign.sign();
        sign.update(two);
        byte[] sigTwo = sign.sign();

        Signature v = Signature.getInstance("EdDSA");
        v.setParameter(new EdDSAParameterSpec(false, context));
        v.initVerify(firstKey.getPublic());
        v.update(one);
        boolean firstValid = v.verify(sigOne);
        v.update(two);
        boolean secondValid = v.verify(sigTwo);

        sign.update(one);
        sign.initSign(secondKey.getPrivate()); // Bỏ dữ liệu đang chờ của key cũ
        sign.update(two);
        byte[] secondKeySig = sign.sign();

        System.out.println("curve=" + curve.getName());
        System.out.println("sameContextFirst=" + firstValid);
        System.out.println("sameContextSecond=" + secondValid);
        System.out.println("wrongContextRejected="
                + !verify(firstKey, one, sigOne, otherContext));
        System.out.println("sameAsIndependentWithContext="
                + Arrays.equals(sigTwo,
                    singleSign(firstKey, two, context)));
        System.out.println("secondKeyValidWithSecond="
                + verify(secondKey, two, secondKeySig, context));
        System.out.println("secondKeyInvalidWithFirst="
                + !verify(firstKey, two, secondKeySig, context));
        System.out.println("reinitDroppedPendingMessage="
                + Arrays.equals(secondKeySig,
                    singleSign(secondKey, two, context)));
    }

    public static void main(String[] args) throws Exception {
        run(NamedParameterSpec.ED25519);
        run(NamedParameterSpec.ED448);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 SignatureContextStateDemo.java
java SignatureContextStateDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
curve=Ed25519
sameContextFirst=true
sameContextSecond=true
wrongContextRejected=true
sameAsIndependentWithContext=true
secondKeyValidWithSecond=true
secondKeyInvalidWithFirst=true
reinitDroppedPendingMessage=true
curve=Ed448
sameContextFirst=true
sameContextSecond=true
wrongContextRejected=true
sameAsIndependentWithContext=true
secondKeyValidWithSecond=true
secondKeyInvalidWithFirst=true
reinitDroppedPendingMessage=true
~~~

### Ý nghĩa chính xác của kết quả

- `sameContextFirst=true` và `sameContextSecond=true`: cùng `Signature` với context `orders-v1` có thể ký hai thông điệp; cùng verifier với context tương ứng có thể kiểm tra cả hai.
- `wrongContextRejected=true`: chữ ký không hợp lệ khi verifier cố dùng context `payments-v1` cho cùng dữ liệu/khóa.
- `sameAsIndependentWithContext=true`: chữ ký lượt thứ hai từ engine tái sử dụng trùng chữ ký từ engine mới có **cùng private key, message và context** (mang tính xác định của EdDSA ở mode này).
- Sau `sign.update(one)`, lệnh `sign.initSign(secondKey.getPrivate())` **khởi tạo lại**; dữ liệu `one` đang chờ không bị gộp vào lượt ký `two` bằng khóa thứ hai.
- `secondKeyValidWithSecond=true` và `secondKeyInvalidWithFirst=true`: thay private key làm thay đổi danh tính signer, cần public key tương ứng khi verify.
- `reinitDroppedPendingMessage=true`: chữ ký sau khi đổi key giống chữ ký sinh độc lập trên **chỉ message `two`**, xác nhận `initSign` đã bỏ message pending cũ trong môi trường thử nghiệm.

**Giới hạn kết luận:** Thí nghiệm với provider cụ thể chứng minh việc đặt `EdDSAParameterSpec` trước `initSign`, giữ context qua các lượt `sign` bình thường và khởi tạo key mới là khả thi. Đừng suy diễn mọi provider/algorithm đều có cùng cách lưu parameters hoặc cùng signature bytes; phải kiểm thử provider thật và tuân theo Javadoc của thuật toán.

## 12. Trường hợp error: reset sau exception có được bảo đảm?

Cần phân biệt hai đường đi:

| Kết quả của thao tác | Điều có thể dựa vào | Điều không nên giả định |
| --- | --- | --- |
| `sign()` trả về byte[] | Engine reset về trạng thái sau `initSign` | Engine đã đổi sang VERIFY |
| `sign(outbuf,off,len)` trả về số bytes | Engine reset về trạng thái sau `initSign` | Bytes có thể tiếp tục nối vào lượt trước |
| `verify(signature)` trả `true` | Engine reset về trạng thái sau `initVerify` | Public key có thể tự đổi ở lượt sau |
| `verify(signature)` trả `false` | Engine reset về trạng thái sau `initVerify` | Sai một lần khiến engine mất khả năng verify |
| `sign/verify/update` ném `SignatureException` | Thao tác thất bại; cần xử lý lỗi cụ thể | Mọi bytes/params nội bộ chắc chắn đã được reset theo cách an toàn |

Khi **lỗi cấu hình** như thiếu provider, sai khóa, sai algorithm, phải xử lý theo type exception tương ứng: `NoSuchAlgorithmException`, `InvalidKeyException`, `InvalidAlgorithmParameterException` hoặc `SignatureException`.

**Khuyến nghị cho code production:** Sau một exception khiến trạng thái operation khó biết, **discard engine và tạo mới**, kiểm tra lỗi trước khi thực hiện lượt kế tiếp. Không cố `verify` hoặc `sign` lặp lại với cùng mutable object chỉ để xem lần thứ hai có tình cờ thành công không. Đặc biệt trong hệ thống đa tenant, một engine đang có pending data của request A không được dùng cho request B.

## 13. Tái sử dụng hợp lệ nhưng không đồng nghĩa thread-safe

`Signature` lưu trạng thái thay đổi qua `initSign`, `initVerify`, `update` và `sign/verify`. Nếu hai luồng dùng chung object:

~~~text
Thread A: initSign(keyA)
Thread A: update(messageA)
Thread B: initSign(keyB)
Thread B: update(messageB)
Thread A: sign()
~~~

thì thao tác bị trộn lẫn về key/message state; **không có cơ sở để kết luận chữ ký của messageA bằng keyA đã được sinh**. JVM/provider không cam kết `Signature` an toàn cho kiểu chia sẻ này.

**Hai phương án chính:**

- **Mỗi operation một `Signature` object**: rõ ràng nhất, hạn chế trạng thái sót và dễ audit. Dùng một engine signing riêng và một engine verifying riêng khi logic cần cả hai.
- **Tái sử dụng trong một scope tuần tự có ownership rõ**: sau mỗi `sign/verify` thành công, có thể `update` một message mới cùng key; nếu đổi key/mode hoặc có exception thì khởi tạo lại/đổi engine.

**Không chia sẻ engine qua thread mà không có thiết kế đồng bộ hóa.** Ngay cả khi có lock, vẫn phải bảo đảm **toàn chuỗi thao tác `init → update → sign/verify`** thuộc cùng transaction, chứ không chỉ khóa một lời gọi `update` riêng lẻ. Dùng object mới mỗi operation thường ít lỗi hơn.

### Template cho một API ký dễ kiểm toán

~~~java
static byte[] signEd25519(
        PrivateKey key, byte[] message) throws GeneralSecurityException {
    Signature s = Signature.getInstance("Ed25519");
    s.initSign(key);
    s.update(message);
    return s.sign();
}
~~~

Đây là **phương thức minh họa đặt trong class**, cần import `java.security.PrivateKey`, `java.security.Signature` và `java.security.GeneralSecurityException`. Mỗi lần gọi tạo engine mới, không lưu state pending giữa các requests.

Tương tự:

~~~java
static boolean verifyEd25519(PublicKey key,
        byte[] message, byte[] signature) throws GeneralSecurityException {
    Signature v = Signature.getInstance("Ed25519");
    v.initVerify(key);
    v.update(message);
    return v.verify(signature);
}
~~~

Với cả hai, cần **bảo vệ key material**, giới hạn kích thước đầu vào theo policy, xác định source của public key và phân biệt kết quả `false` với lỗi kỹ thuật. Việc tạo engine mới không giải quyết được chính sách tin cậy public key, message canonicalization hoặc replay protection.

## 14. Không nhầm trạng thái của Signature với trạng thái dữ liệu khác

Một ứng dụng ký thường có nhiều object mutable:

| Object | Trạng thái thay đổi | `sign/verify` có reset nó không? |
| --- | --- | --- |
| `Signature` | Key/role/mode và bytes đang update | **Có reset bytes của lượt ký/xác minh khi hoàn tất**; giữ vai trò/key đã chọn |
| `ByteBuffer` được đưa vào `update` | `position`, `limit`, content | **Không reset ByteBuffer**; `update` có thể đã tiến `position` tới `limit` |
| `byte[] messageBytes` của ứng dụng | Nội dung bytes trong array | `Signature` không tự xóa/sửa array dữ liệu caller |
| `byte[] signatureBytes` trả về | Chữ ký đã tạo | Là kết quả để lưu/truyền; không tự biến mất khi engine reset |
| `PrivateKey` / `PublicKey` | Key object do provider quản lý | `sign/verify` không tự đổi hoặc hủy key |
| Tham số `EdDSAParameterSpec` | Mode/context được cấu hình trong engine | `sign/verify` bình thường không tự chọn một context mới |
| Request/transaction object của ứng dụng | Metadata, idempotency, replay controls | `Signature` không quản lý những vấn đề nghiệp vụ này |

**Ví dụ thực tế:** Một API client có thể ký payload, rồi vô tình gọi `signer.sign()` một lần nữa mà không `update`, trong khi payload array vẫn còn nguyên. Engine sẽ ký empty message vì **nó không còn nhớ bytes đã update**, không phải vì payload array bị xóa.

Tương tự, với `ByteBuffer`, dù engine reset, buffer position vẫn có thể ở cuối. Nếu vô tình dùng lại `update(buffer)` với `remaining()==0`, bạn lại không đưa bytes mới vào engine.

## 15. Các sai lầm phổ biến và hậu quả

1. **“`sign()` xong thì `Signature` trở lại UNINITIALIZED.”** Sai: nó trở lại trạng thái sau `initSign`; có thể ký tiếp bằng cùng key.
2. **“`verify()` xong thì phải `initVerify` lại mọi lần.”** Không bắt buộc sau lời gọi hoàn tất bình thường với cùng public key; verifier đã reset.
3. **“`verify=false` làm hỏng verifier.”** Sai: lời gọi trả false cũng reset về VERIFY.
4. **“Sau `sign()`, `update` lượt cũ còn nguyên.”** Sai: dữ liệu lượt cũ không được nối vào lượt mới.
5. **“Nếu không `update`, `sign()` sẽ tự ký lại thông điệp trước.”** Sai: trong Ed25519/Ed448 ví dụ, nó ký empty message.
6. **“`sign()` làm object tự chuyển sang VERIFY.”** Sai: cần `initVerify(publicKey)`.
7. **“`verify()` làm object tự chuyển sang SIGN.”** Sai: cần `initSign(privateKey)`.
8. **“Có thể dùng cùng một `Signature` cho nhiều luồng vì object tự reset.”** Sai: tự reset sau operation không phải thread safety cho chuỗi calls có trạng thái.
9. **“Chỉ cần đặt lock quanh `sign()` thôi.”** Sai: key, params và mọi `update` phải thuộc cùng một chuỗi thao tác nguyên tử theo thiết kế.
10. **“`sign(outbuf,off,len)` không reset vì không trả byte[].”** Sai: overload này cũng reset sau khi hoàn tất.
11. **“`verify(sig,offset,length)` không reset.”** Sai: overload này cũng reset.
12. **“`update(ByteBuffer)` không làm đổi vị trí của buffer.”** Sai: khi hoàn tất, position tiến tới limit.
13. **“Chữ ký Ed25519 deterministic nên engine giữ message.”** Sai: tính deterministic đến từ thuật toán/khóa/message, không phải lưu message trước.
14. **“Chữ ký sai luôn khiến `verify` ném exception.”** Sai: thường `false` nếu signature hợp lệ về định dạng nhưng không khớp; lỗi format/engine có thể ném `SignatureException`.
15. **“Có exception rồi cứ gọi `sign()` lần nữa vì API bảo đảm reset.”** Không có bảo đảm chung như khi thao tác hoàn tất bình thường; cần khởi tạo lại/an toàn hơn là tạo engine mới.
16. **“Đổi key chỉ cần thay biến `PrivateKey key` trong code.”** Sai: engine phải nhận key mới bằng `initSign(key)`.
17. **“Ed25519 và Ed448 là cùng algorithm object vì đều EdDSA.”** Sai: phải giữ key/params/algorithm tương thích.
18. **“Một chữ ký verify đúng chứng minh người gửi tin cậy.”** Sai: phải xác thực provenance và quyền sử dụng public key trong protocol.
19. **“Dùng text input mà không xác định charset vẫn verify được mọi nơi.”** Sai: `update` xử lý bytes; cần thống nhất serialization/UTF-8.
20. **“`Signature` tự ngăn replay giữa các lượt.”** Sai: nó không lưu request IDs hoặc timestamps; replay defense là logic protocol.

## 16. Checklist triển khai hệ thống ký/xác minh thực tế

| Câu hỏi kiểm tra | Câu trả lời/việc cần làm |
| --- | --- |
| Đã chọn thuật toán và curve chưa? | `Ed25519` hoặc `Ed448` theo giao thức; kiểm tra provider hỗ trợ |
| Đã có đúng private/public key tương ứng chưa? | Chỉ định `initSign`/`initVerify` đúng key |
| Bytes đầu vào có được xác định chính xác không? | Dùng UTF-8/serialization canonical theo hợp đồng |
| Một request có quyền sở hữu engine riêng không? | Ưu tiên tạo `Signature` mới mỗi operation |
| Có nhiều `update` không? | Chúng nối bytes trong **cùng** operation; kiểm tra thứ tự |
| Khi sign/verify xong có update message mới chưa? | Engine đã reset, nhưng key/role vẫn còn |
| Có đổi key hoặc role không? | Gọi `initSign`/`initVerify` hoặc tạo engine mới |
| Dùng EdDSA context/prehash không? | Đồng bộ mode/context giữa bên ký và xác minh |
| Sau `verify=false` xử lý thế nào? | Xử lý chữ ký không hợp lệ; verifier có thể dùng cho lượt tiếp theo nếu không có exception |
| Sau exception xử lý thế nào? | Không dựa vào state còn lại; tạo/reinit engine phù hợp |
| Có dùng `ByteBuffer` không? | Theo dõi `position/limit`, snapshot/duplicate nếu cần |
| Đã xác minh public key đáng tin chưa? | Chữ ký hợp lệ chỉ gắn với key đã chọn; cần policy danh tính |
| Có chống replay chưa? | Ghi version, nonce/sequence, timestamp vào payload được ký và kiểm tra nghiệp vụ |
| Đã kiểm tra khả năng tương tác và provider chưa? | Test với JDK/provider/định dạng thực tế và thuật toán đã chọn |

## 17. Bài thực hành và tiêu chí đạt

**Bài 1 — Dự đoán máy trạng thái.** Xác định trạng thái sau `getInstance`, `initSign`, `update`, `sign`, `initVerify`, `verify`. **Đạt** khi biết `sign` quay về SIGN và `verify` quay về VERIFY, không về UNINITIALIZED.

**Bài 2 — Ký hai messages bằng một engine.** Dùng Ed25519 và Ed448, ký `invoice:001` rồi `invoice:002` không khởi tạo lại. **Đạt** khi hai chữ ký đều verify được và chữ ký thứ hai tương đương một engine độc lập ký `invoice:002`.

**Bài 3 — Không gọi `update`.** Gọi `sign()` ngay sau một lần `sign()` đã hoàn tất. **Đạt** khi giải thích vì sao lượt mới ký empty message trong demo EdDSA, không ký lại message cũ.

**Bài 4 — Verify sai rồi đúng.** Với cùng public key, verify một message sai để được false, sau đó update message đúng rồi verify lại. **Đạt** khi kết quả false → true và không gọi `initVerify` lại giữa hai lượt.

**Bài 5 — Sai hướng hoạt động.** Sau `initVerify`, gọi `sign()`; sau đó `initSign` rồi thử lại. **Đạt** khi xác định đúng lỗi `SignatureException` ở lời gọi sai hướng và hành vi hợp lệ khi đã đổi mode.

**Bài 6 — Buffered overload.** Dùng `sign(outbuf,off,len)`, verify chỉ slice chữ ký và ký tiếp. **Đạt** khi biết nó cũng reset sau completion và xử lý được offset/length.

**Bài 7 — `ByteBuffer`.** Ký một slice của buffer, kiểm tra `position()==limit()` và verify bằng đúng bytes. **Đạt** khi phân biệt state buffer với state của `Signature`.

**Bài 8 — Đổi private key.** Đưa một message vào `update`, rồi `initSign` bằng key khác và ký message khác. **Đạt** khi chữ ký sau đó chỉ hợp lệ cho key/message mới, pending bytes cũ không được ký.

**Bài 9 — Context.** Cấu hình EdDSA context `orders-v1`, ký hai lượt; verify bằng context đúng và context khác. **Đạt** khi bốn tham số curve/key/message/context được giữ nhất quán.

**Bài 10 — Thiết kế API concurrent.** Tạo API ký nhận nhiều requests đồng thời. **Đạt** khi mỗi operation quản lý engine của riêng mình hoặc khóa cả chuỗi init/update/sign như transaction, xử lý exception có chủ đích và tránh dùng static mutable signer chung.

**Bài 11 — Sự khác nhau giữa false và exception.** Nêu ba tình huống `verify=false`, `SignatureException` và `InvalidKeyException`. **Đạt** khi phân biệt chữ ký không khớp, lỗi thao tác/format/provider, và khóa không hợp lệ.

**Bài 12 — Ký đúng bytes.** Xây dựng payload có algorithm, version, request ID và nonce/timestamp được ký; xác minh bằng đúng serialization. **Đạt** khi giải thích được `Signature` chỉ xác nhận bytes + key, không tự chống replay hay xác thực nguồn public key.

## 18. Nguồn chuẩn và tài liệu hiện hành

- [Oracle Java SE 25 — Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): mô hình ba pha, `initSign`/`initVerify`, `update`, và **hợp đồng reset sau `sign`/`verify`**, bao gồm các overload buffer.
- [Oracle Java SE 25 — SignatureSpi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SignatureSpi.html): vai trò provider, các thao tác backend `engineSign`, `engineVerify` và `engineUpdate`.
- [Oracle Java SE 25 — EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): prehash và context, các mode EdDSA, giới hạn context.
- [Oracle Java SE 25 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519` và `ED448`.
- [Oracle Java SE 25 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html): tạo cặp khóa bằng bộ tham số rõ ràng.
- [JEP 339 — EdDSA (JDK 15)](https://openjdk.org/jeps/339): Ed25519/Ed448 được tích hợp vào JCA, là ngữ cảnh phiên bản Java 15 của bài.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): thông số thuật toán, chữ ký Ed25519/Ed448, context và prehash.

**Ghi nhớ:** `Signature` **không bị hủy** và **không trở về UNINITIALIZED** sau khi một lời gọi `sign`/`verify` hoàn tất bình thường. Nó trở lại **SIGN/VERIFY với khóa đã khởi tạo**, và dữ liệu của lượt vừa xử lý được reset. Tái sử dụng tuần tự đúng cách là hợp lệ, nhưng **luôn `update` message mới**, chủ động `initSign`/`initVerify` khi đổi key/vai trò, giữ mode/context thống nhất và **không chia sẻ mutable engine giữa các luồng hoặc request không có ownership rõ**.
