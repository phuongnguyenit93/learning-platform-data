# EdECPrivateKey.getBytes(): Optional và khóa riêng không xuất được trong Java

> **Bối cảnh Java 15:** JEP 339 bổ sung hỗ trợ EdDSA và các kiểu khóa EdEC, trong đó có interface `java.security.interfaces.EdECPrivateKey`. Phương thức `getBytes()` trả về **`Optional<byte[]>`**, không phải luôn có một mảng byte. Với một số nhà cung cấp khóa (provider), đặc biệt khi private key được giữ trong một hệ thống bảo vệ hoặc được đánh dấu **non-exportable**, giá trị có thể **vắng mặt**. Đây là một trạng thái hợp lệ của API: **không xuất được khóa ≠ khóa hỏng, và không xuất được khóa ≠ không thể ký**.

Bài này trình bày hợp đồng API hiện hành, cách xử lý `Optional` an toàn, sự khác nhau giữa **raw private-key bytes** và **PKCS#8 encoding**, cách sử dụng private key qua JCA `Signature` mà không trích xuất bí mật, cùng các rủi ro bảo mật khi xử lý khóa.

## 1. Khóa EdEC được dùng vào việc gì?

EdEC là tên nhóm kiểu khóa dùng cho các thuật toán Edwards-curve trong RFC 8032, chủ yếu **Ed25519** và **Ed448**. Trong Java 15+, EdDSA có thể thực hiện qua JCA:

~~~java
// Mảnh mã nằm trong phương thức có xử lý GeneralSecurityException.
KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
        .generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(messageBytes);
byte[] signatureBytes = signer.sign();
~~~

Private key được đưa **trực tiếp** vào `Signature.initSign(PrivateKey)`. Ứng dụng không cần biết raw key bytes để ký. Đây là nguyên tắc nền tảng khi làm việc với các khóa được quản lý bởi provider, HSM hoặc hệ thống key management.

EdEC **không** phải cùng loại với `ECPrivateKey` dùng cho các thuật toán elliptic-curve truyền thống như ECDSA. Các interface và cấu trúc tham số khác nhau; đừng ép kiểu hoặc tái dùng key spec cho sai thuật toán.

## 2. Hợp đồng chính xác của `EdECPrivateKey.getBytes()`

Interface:

~~~java
package java.security.interfaces;

public interface EdECPrivateKey extends EdECKey, java.security.PrivateKey {
    java.util.Optional<byte[]> getBytes();
}
~~~

Đây là **chữ ký API rút gọn để giải thích**, không phải đoạn cần tự định nghĩa lại trong dự án. Interface đã có trong `java.base` từ Java 15.

Javadoc của `getBytes()` mô tả:

- Trả về **một bản sao của byte array** chứa giá trị private key khi implementation sẵn lòng cung cấp giá trị đó.
- Kiểu trả về là **`Optional<byte[]>`**.
- Nếu implementation **không sẵn lòng cung cấp private-key value**, có thể trả **`Optional.empty()`**.
- `Optional.empty()` là **kết quả bình thường theo hợp đồng**, không phải lỗi giải mã hoặc bằng chứng private key đã mất.
- Nếu có mảng bytes, **đó là bí mật mật mã**; tuyệt đối không coi nó là dữ liệu log/telemetry vô hại.

Nói ngắn gọn:

~~~text
EdECPrivateKey.getBytes()
           |
           +--- Optional.of(byte[])  -> Có bản sao giá trị khóa riêng
           |
           +--- Optional.empty()     -> Giá trị khóa riêng không được cung cấp
~~~

Không được gọi:

~~~java
byte[] secret = edecPrivateKey.getBytes().get();
~~~

mà không kiểm tra trước. Nếu `Optional` rỗng, `get()` ném **`NoSuchElementException`**. Nếu bắt exception này rồi gán một mảng 32 byte toàn số 0 để “bù thiếu”, ứng dụng đã biến trạng thái khóa không xuất được thành **một khóa giả** và tạo ra lỗ hổng nghiêm trọng.

### Từ “Optional” nói về **khả năng xuất vật liệu khóa**, không phải “khóa tùy chọn”

Một private key có thể vẫn được cung cấp cho API ký ở dạng một đối tượng đại diện/handle. `Optional` chỉ thông báo liệu **bytes của private key** có thể được tiết lộ cho caller qua **method này** hay không.

Bởi vậy, thiết kế đúng là:

- Mục tiêu **ký**: dùng private key object với `Signature.initSign`.
- Mục tiêu **xuất khóa**: phải có chính sách cho phép rõ ràng, kiểm tra `Optional`, kiểm tra định dạng và bảo vệ bytes.
- Mục tiêu **xác minh chữ ký**: dùng public key với `Signature.initVerify`, **không cần xuất private-key bytes**.

## 3. Ba khái niệm cần tách biệt: key object, raw bytes và encoded form

Đối với một private key Ed25519:

1. **`PrivateKey` / `EdECPrivateKey` object**: đối tượng Java đại diện cho khóa; có thể chứa vật liệu khóa trong bộ nhớ hoặc chỉ là handle tới khóa do provider khác quản lý.
2. **`EdECPrivateKey.getBytes()`**: yêu cầu **giá trị byte của private key ở dạng raw/bit-string theo EdEC**, có thể bị từ chối bằng `Optional.empty()`. Không được nhầm bytes này với một file PKCS#8 hoàn chỉnh.
3. **`Key.getEncoded()`**: yêu cầu **biểu diễn khóa theo format do provider công bố**; với khóa private có thể là PKCS#8, nhưng API `Key` cho phép trả về **`null` nếu khóa không hỗ trợ encoding**.

Bảng so sánh:

| API / biểu diễn | Kiểu trả về | Nếu không có giá trị | Dùng để làm gì? |
| --- | --- | --- | --- |
| `EdECPrivateKey.getBytes()` | `Optional<byte[]>` | `Optional.empty()` | Giá trị raw của private key EdEC, khi được phép xuất |
| `Key.getEncoded()` | `byte[]` | `null` nếu key không hỗ trợ encoding | Biểu diễn có format như PKCS#8, nếu provider hỗ trợ |
| `Key.getFormat()` | `String` | `null` nếu không có format được hỗ trợ | Tên format tương ứng với `getEncoded()` |
| `EdECPrivateKey.getParams()` | `NamedParameterSpec` | Tham số curve theo hợp đồng phiên bản API | Biết bộ tham số Ed25519/Ed448, **không lộ raw private bytes** |
| `Signature.initSign(privateKey)` | Không xuất khóa | `InvalidKeyException` nếu provider không dùng được key | Khởi tạo ký trực tiếp từ đối tượng/handle private key |
| `EdECPrivateKeySpec.getBytes()` | `byte[]` | Không dùng `Optional` | Truy xuất bytes của **key specification minh bạch** đã có vật liệu khóa |

Một khóa **non-exportable** có thể không cung cấp raw bytes và cũng không hỗ trợ PKCS#8 encoding. Nhưng **đừng suy ra theo chiều ngược**: chỉ vì `getBytes()` rỗng **không được khẳng định** `getEncoded()` chắc chắn `null` trong mọi provider, hoặc ngược lại. Hai API có hợp đồng riêng; kết quả thực tế do provider/chính sách khóa quyết định.

### Raw Ed25519 private bytes không phải mảng `byte[]` PKCS#8

Một raw Ed25519 private seed theo RFC 8032 thường dài **32 byte**; Ed448 có private seed **57 byte**. Những bytes này là **vật liệu khóa bí mật**. Một `PKCS8EncodedKeySpec` thì chứa dữ liệu đã được đóng gói theo cấu trúc **PKCS#8**, gồm metadata thuật toán và các trường tương ứng, không phải đơn thuần mảng raw seed.

Không thể thay tùy tiện:

~~~java
// Sai về hợp đồng: KHÔNG coi raw EdEC bytes là PKCS#8.
new PKCS8EncodedKeySpec(rawPrivateKeyBytes);
~~~

và mong `KeyFactory` nhập khóa đúng. Để dựng từ raw bits khi chính sách cho phép, dùng **`EdECPrivateKeySpec` với `NamedParameterSpec` đúng**; để nhập PKCS#8 thì sử dụng **`PKCS8EncodedKeySpec`** với **bytes đúng định dạng PKCS#8**.

## 4. Vì sao một provider không cho lấy raw key?

Nhà cung cấp triển khai khóa có thể **cố ý từ chối export** nhằm bảo vệ private key:

- **HSM (Hardware Security Module):** private key được tạo/lưu bên trong thiết bị và không được phép rời khỏi ranh giới bảo vệ theo chính sách.
- **Token hoặc smart card:** ứng dụng cầm key handle, còn việc ký được thực thi trong provider/thiết bị.
- **Cloud KMS hoặc dịch vụ ký chuyên dụng:** ứng dụng gửi yêu cầu ký theo cơ chế được hỗ trợ, không nắm bytes khóa; mức độ tích hợp với JCA phụ thuộc dịch vụ/provider.
- **Security provider với policy non-extractable:** private key object có thể mang danh tính/handle nhưng không tiết lộ vật liệu.
- **Hạn chế theo quyền hoặc trạng thái:** policy/provider có thể không cho export trong ngữ cảnh ứng dụng hiện tại.

Không phải **mọi HSM/KMS** đều tích hợp thành `EdECPrivateKey` hoặc hỗ trợ `Signature.getInstance("Ed25519")` bằng cách giống nhau. Chỉ khi **provider tương ứng hỗ trợ EdDSA và chấp nhận đúng đối tượng khóa**, ứng dụng mới dùng được ký trực tiếp theo JCA.

**Điểm cần nhớ:** `Optional.empty()` có thể là **tín hiệu bảo vệ khóa đúng thiết kế**, không phải trạng thái cần phá vỡ bằng reflection, truy cập trường nội bộ, parse implementation-specific buffer hay chuyển provider để cố export. Những thủ thuật ấy vừa làm mất security boundary vừa phụ thuộc chi tiết runtime.

### Không phải khóa bị mất

Nên phân biệt:

| Tình huống | Ý nghĩa |
| --- | --- |
| `getBytes().isEmpty() == true` | Provider **không cung cấp raw bytes qua method này** |
| `getEncoded() == null` | Key **không hỗ trợ encoded form qua method này** |
| `Signature.initSign(key)` thành công | Provider/signature engine **chấp nhận khóa để ký** |
| `Signature.initSign(key)` ném `InvalidKeyException` | Engine hiện tại **không chấp nhận khóa hoặc tham số**, không suy ra raw bytes đã mất |
| Key handle hết hạn/thiết bị không sẵn sàng | Vấn đề vận hành/provider, có thể không liên quan đến contract của `getBytes()` |
| Private key bị thu hồi/hủy hoặc không còn accessible | Cần key lifecycle/recovery theo policy; `Optional.empty()` đơn lẻ không chứng minh điều này |

## 5. Xử lý `Optional<byte[]>` an toàn trong Java

### 5.1. Trường hợp chỉ cần biết khóa có xuất được hay không

Nếu một chức năng **được phép** kiểm tra trạng thái mà không cần dùng bytes:

~~~java
// Mảnh mã minh họa trong một phương thức.
EdECPrivateKey key = ...;

boolean exposed = key.getBytes().isPresent();
if (!exposed) {
    // Nhà cung cấp không cung cấp raw key bytes qua API này.
}
~~~

Cách này đúng về mặt API, nhưng **đã gọi phương thức có thể xuất bí mật**. Nếu không cần raw key, **đừng gọi `getBytes()` chỉ để quan sát**: xuất một bản sao private bytes không cần thiết có thể mở rộng bề mặt rủi ro. Hãy lấy thông tin policy từ cơ chế quản trị khóa nếu có.

### 5.2. Xử lý đủ hai nhánh

~~~java
// Mảnh minh họa, chỉ thực hiện trong luồng được cho phép export.
Optional<byte[]> maybeRaw = key.getBytes();

if (maybeRaw.isPresent()) {
    byte[] raw = maybeRaw.get();
    try {
        // Xử lý raw bytes theo chính sách an toàn đã cho phép.
        // Không log, không Base64-in-ra-stdout, không lưu plaintext.
    } finally {
        Arrays.fill(raw, (byte) 0); // Xóa bản sao có thể kiểm soát.
    }
} else {
    // Không export được: dùng API ký/khóa provider hoặc báo unsupported.
}
~~~

**Import** `java.util.Optional` và `java.util.Arrays` nếu đặt trong class.

Cần hiểu đúng `Arrays.fill(raw, (byte) 0)`:

- Chỉ ghi đè **mảng raw mà ứng dụng đang cầm**, không xóa chắc chắn mọi bản sao trong memory, private key nội bộ, backup, pagefile, crash dump hoặc JVM tối ưu hóa.
- **Không** gọi `destroy()` rồi tuyên bố xóa khóa thành công: giao diện `Destroyable` có quy tắc/provider support riêng.
- Nếu mã không cần raw bytes, **tránh trích xuất** có tác dụng bảo vệ tốt hơn trích xuất rồi cố “lau sạch”.

### 5.3. `ifPresent` dùng được nhưng không tự giải quyết lỗi nghiệp vụ

~~~java
// Mảnh minh họa.
key.getBytes().ifPresent(raw -> {
    try {
        // Chỉ khi đã được cho phép xử lý bí mật.
    } finally {
        Arrays.fill(raw, (byte) 0);
    }
});
~~~

Đoạn trên chạy yên lặng khi `Optional.empty()`. Với chức năng **backup/export bắt buộc**, im lặng có thể là lỗi. Hãy xử lý nhánh empty **có chủ đích**: hiển thị “khóa không cho phép xuất” hoặc trả về kết quả lỗi nghiệp vụ; không tiếp tục báo backup thành công.

### 5.4. Không dùng `orElse(new byte[...])` để tạo bí mật giả

Mẫu sai:

~~~java
// Sai: khi key không xuất được, đây là dãy zero, không phải private key.
byte[] raw = key.getBytes().orElse(new byte[32]);
~~~

Với private key, một fallback như vậy có thể dẫn tới:

- ký hoặc lưu bằng **một giá trị không phải key dự định**;
- xuất một backup có vẻ thành công nhưng thực ra vô giá trị;
- gây mất dữ liệu hoặc phá vỡ ràng buộc định danh của khóa.

**Không tự tạo private-key material thay thế để lấp khoảng trống `Optional`**. Nếu không có raw bytes, sử dụng capability ký do provider quản lý, hoặc từ chối export một cách minh bạch.

## 6. Khi chỉ cần ký: đừng gọi `getBytes()`

Đây là kiểu code **ưu tiên** trong ứng dụng:

~~~java
// Mảnh mã trong phương thức có xử lý GeneralSecurityException.
PrivateKey signingKey = keyStoreOrProviderKey;

Signature s = Signature.getInstance("Ed25519");
s.initSign(signingKey);
s.update(messageBytes);
byte[] signature = s.sign();
~~~

Bản thân API `Signature` nhận **`PrivateKey`**, không yêu cầu caller bóc vật liệu bí mật thành bytes. Bên xác minh dùng public key:

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedPublicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
~~~

Trong thực tế, `KeyStore`, provider hoặc KMS/HSM adapter phải hỗ trợ chính xác Ed25519 và có quyền sử dụng khóa. Những trường hợp provider không hỗ trợ có thể dẫn tới `NoSuchAlgorithmException` hoặc `InvalidKeyException`; không sửa bằng cách cố trích xuất private key.

**Lưu ý:** một `PrivateKey` opaque có thể **không implement** `EdECPrivateKey`. Vì vậy, code tổng quát dùng khóa provider nên chấp nhận `PrivateKey` theo API, và chỉ `instanceof EdECPrivateKey` khi chức năng thật sự cần thao tác với interface đó. Đừng ép kiểu mù:

~~~java
// Không an toàn với mọi provider:
EdECPrivateKey ed = (EdECPrivateKey) arbitraryPrivateKey;
~~~

Nếu provider cung cấp key object opaque có implementation khác, dòng trên có thể ném `ClassCastException` dù khóa vẫn có thể ký được qua engine tương ứng.

## 7. Ví dụ chạy được: khóa thật để ký, mock để minh họa Optional.empty()

Để có **stdout ổn định** mà không giả định một máy có HSM, ví dụ tách hai khái niệm:

1. Sinh **cặp khóa Ed25519 thật** bằng provider JDK và dùng private key **trực tiếp để ký**, không export.
2. Tạo một **đối tượng mô phỏng** `EdECPrivateKey` không cung cấp bytes nhằm minh họa đúng contract `Optional.empty()` và `getEncoded() == null`.

**Cảnh báo:** mock chỉ phục vụ minh họa API, **không chứa private key thực** và **không thể dùng làm khóa ký**. Nó **không giả lập được bảo mật của HSM**. Chương trình không in hoặc lưu vật liệu private key.

### File `EdECOptionalDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.EdECPrivateKey;
import java.security.spec.NamedParameterSpec;
import java.util.Optional;

public class EdECOptionalDemo {
    // Chỉ là test double về hợp đồng getBytes(); KHÔNG PHẢI
    // khóa mật mã có thể dùng để ký.
    private static final class NonExportableView
            implements EdECPrivateKey {

        private static final long serialVersionUID = 1L;

        @Override
        public Optional<byte[]> getBytes() {
            return Optional.empty();
        }

        @Override
        public NamedParameterSpec getParams() {
            return NamedParameterSpec.ED25519;
        }

        @Override
        public String getAlgorithm() {
            return "Ed25519";
        }

        @Override
        public String getFormat() {
            return null;
        }

        @Override
        public byte[] getEncoded() {
            return null;
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        byte[] message =
                "EdEC optional demo".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        System.out.println("Ed25519 signature bytes: "
                + signature.length);
        System.out.println("Signature verified: "
                + verifier.verify(signature));

        EdECPrivateKey view = new NonExportableView();
        System.out.println("Mock getBytes empty: "
                + view.getBytes().isEmpty());
        System.out.println("Mock getEncoded null: "
                + (view.getEncoded() == null));
        System.out.println("Mock getFormat null: "
                + (view.getFormat() == null));

        // Không dùng view để gọi initSign:
        // nó chỉ chứng minh API cho phép Optional.empty().
    }
}
~~~

Biên dịch/chạy với **JDK 17+ có Ed25519 provider**:

~~~bash
javac EdECOptionalDemo.java
java EdECOptionalDemo
~~~

**Stdout:**

~~~text
Ed25519 signature bytes: 64
Signature verified: true
Mock getBytes empty: true
Mock getEncoded null: true
Mock getFormat null: true
~~~

Giải thích:

- Chữ ký Ed25519 có độ dài cố định **64 byte** theo RFC 8032.
- `Signature.initSign(pair.getPrivate())` ký dữ liệu **mà không gọi `getBytes()` hay `getEncoded()`**.
- `Signature.verify(...)` dùng public key tương ứng xác minh thành công.
- `NonExportableView` chứng minh một implementation **có thể** trả `Optional.empty()` từ `getBytes()` và `null` từ các phương thức encoding theo hợp đồng. Việc code biên dịch/chạy **không** có nghĩa mock đại diện cho một private key thực hay tự ký được.
- Không in trạng thái export của private key do provider cụ thể sinh ra, tránh tạo giả định sai rằng **mọi provider Java** trả cùng một kết quả về khả năng export.

Chương trình dùng API từ Java 15 trở đi, không sử dụng preview. Nếu JDK compiler hiện tại còn hỗ trợ target 15:

~~~bash
javac --release 15 EdECOptionalDemo.java
~~~

## 8. Cách kiểm tra khóa thực do provider cung cấp (không tiết lộ bí mật)

Khi **chức năng chuyên biệt đã được phép** kiểm tra EdEC raw export, có thể xử lý một cách không phụ thuộc provider:

~~~java
import java.security.PrivateKey;
import java.security.interfaces.EdECPrivateKey;
import java.util.Arrays;
import java.util.Optional;

public class PrivateKeyAvailability {
    public static String classify(PrivateKey privateKey) {
        if (!(privateKey instanceof EdECPrivateKey)) {
            return "NOT_EDEC_INTERFACE";
        }

        EdECPrivateKey ed = (EdECPrivateKey) privateKey;
        Optional<byte[]> possibleRaw = ed.getBytes();

        if (possibleRaw.isEmpty()) {
            return "RAW_UNAVAILABLE";
        }

        byte[] raw = possibleRaw.get();
        try {
            return raw.length > 0
                    ? "RAW_AVAILABLE"
                    : "EMPTY_RAW_VALUE";
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }
}
~~~

Đây là **một class helper biên dịch độc lập**, nhưng không có `main`. Các nhãn trạng thái chỉ mô tả **kết quả hỏi API**, không tuyên bố key hợp lệ hoặc HSM đang ở trạng thái nào.

Cách dùng trong một service: nếu `classify(key)` trả `RAW_UNAVAILABLE`, thao tác export chuyên biệt phải **dừng với thông báo phù hợp**. Nếu chỉ cần ký, không nên gọi helper này — tiếp tục chuyển `PrivateKey` trực tiếp vào `Signature.initSign`.

**Không log** tên file/secret, dump bytes, private key `toString()` hay nội dung backup raw. Bản thân việc gọi `getBytes()` có thể đưa raw bytes vào Java heap, do đó chỉ dùng chức năng này khi có nhu cầu và được cho phép.

## 9. `EdECPrivateKeySpec` là lớp khác: vì sao nó không trả Optional?

Ngoài interface `EdECPrivateKey`, Java còn cung cấp **`java.security.spec.EdECPrivateKeySpec`**. Đây là **key specification mang raw bits** kèm tham số:

~~~java
// Mảnh mã: rawPrivateKeyBits chỉ hợp lệ khi được phép có vật liệu đó.
EdECPrivateKeySpec spec =
        new EdECPrivateKeySpec(
                NamedParameterSpec.ED25519,
                rawPrivateKeyBits
        );

byte[] copy = spec.getBytes();
NamedParameterSpec params = spec.getParams();
~~~

**Không phải mã chạy độc lập**; cần import `EdECPrivateKeySpec` và `NamedParameterSpec`, và biến raw bits thực sự hợp lệ.

Những khác biệt:

| `EdECPrivateKey` | `EdECPrivateKeySpec` |
| --- | --- |
| Là **interface của private key object** | Là **transparent key specification** |
| `getBytes()` trả **`Optional<byte[]>`** | `getBytes()` trả **`byte[]`**, một bản sao |
| Có thể không cung cấp private bytes | Key spec đã chứa raw private bytes |
| Có thể được provider dùng làm key handle/opaque object | Được dùng khi **đã có** private material |
| Có thể được đưa vào `Signature.initSign` nếu provider hỗ trợ | Không phải `PrivateKey` để đưa trực tiếp vào `initSign` |
| Cho biết tham số qua `getParams()` | Chứa tham số đã chỉ định khi tạo spec |

Javadoc của `EdECPrivateKeySpec` cho biết constructor **copy mảng input** và `getBytes()` **trả bản sao mới**. Vì vậy, dùng spec không loại bỏ nguy cơ xuất hiện nhiều bản sao dữ liệu bí mật trong heap.

### Chuyển key spec thành private key khi được cho phép

~~~java
// Mảnh minh họa: chỉ khi đã sở hữu raw key đúng curve,
// được phép import và provider hỗ trợ KeyFactory.
KeyFactory factory = KeyFactory.getInstance("Ed25519");
PrivateKey privateKey = factory.generatePrivate(
        new EdECPrivateKeySpec(
                NamedParameterSpec.ED25519,
                rawPrivateKeyBits
        )
);
~~~

Cần các import `java.security.KeyFactory`, `java.security.PrivateKey` và các key spec. Nếu bytes sai hoặc provider không hỗ trợ, có thể nhận `InvalidKeySpecException`.

**Không thể** tự động biến một khóa non-exportable thành `EdECPrivateKeySpec` nếu không có raw private bytes. Cố `KeyFactory.getKeySpec(opaqueKey, EdECPrivateKeySpec.class)` cũng **không được bảo đảm thành công**; provider có thể không hỗ trợ và/hoặc từ chối tiết lộ vật liệu khóa.

### `NamedParameterSpec` là thông tin công khai

`NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` mô tả tham số thuật toán. Thông tin **curve** không phải private key. Biết curve và public key **không đủ** để suy ra raw private key.

Không lẫn `EdECPrivateKeySpec` với `XECPrivateKeySpec`: XEC liên quan nhóm thuật toán như X25519 (key agreement), không thay thế EdDSA signature keys.

## 10. PKCS#8: khi nào `getEncoded()` có ý nghĩa?

`Key.getEncoded()` có thể trả key encoding theo **format chính** được provider công bố. Với một private key có thể export, format phổ biến là **PKCS#8**. Khi `getFormat()` trả `"PKCS#8"` và `getEncoded()` khác `null`, dữ liệu có thể được xử lý theo cấu trúc PKCS#8.

~~~java
// Mảnh minh họa: KHÔNG tự log hoặc lưu plaintext.
PrivateKey privateKey = ...;

String format = privateKey.getFormat();
byte[] encoded = privateKey.getEncoded();

if ("PKCS#8".equals(format) && encoded != null) {
    // Chỉ đưa vào luồng export được cấp quyền và bảo vệ bí mật.
} else {
    // Encoding không sẵn có/không đúng format mong muốn.
}
~~~

**Không tự suy luận** từ `getAlgorithm() == "Ed25519"` rằng `getEncoded()` phải trả raw 32 bytes; đó là sự nhầm lẫn giữa tên thuật toán và encoding.

Nếu một ứng dụng **được phép** nhập private key đã có ở định dạng PKCS#8 chuẩn:

~~~java
// Mảnh minh họa, pkcs8Bytes được lấy từ nguồn an toàn.
KeyFactory factory = KeyFactory.getInstance("Ed25519");
PrivateKey imported =
        factory.generatePrivate(new PKCS8EncodedKeySpec(pkcs8Bytes));
~~~

Sử dụng `PKCS8EncodedKeySpec` (cần import) với **bytes đúng PKCS#8**. Không đưa raw seed vào constructor đó, không convert PKCS#8 về base64 rồi lưu trong source code và không tự giải mã ASN.1 bằng cách cắt một offset cố định.

Với khóa không export được, **sao lưu nên diễn ra theo cơ chế quản lý khóa chính thức của HSM/KMS**, nếu hệ thống có hỗ trợ. Không thực hiện “backup” bằng cách cố lấy raw bytes từ Java provider trái policy.

## 11. Phân biệt ba tình huống vận hành

### Tình huống A — khóa thử nghiệm trong bộ nhớ

Ứng dụng sinh cặp khóa Ed25519 bằng provider phần mềm của JDK để test. Một implementation có thể cho phép gọi `getBytes()` và `getEncoded()`.

**Cách làm tốt:** nếu mục tiêu là ký, **không gọi export**. Chỉ lưu public key/signature và test verify. Khi cần xuất cho migration/test có kiểm soát, dùng format chuẩn và xóa bản sao raw có thể kiểm soát.

### Tình huống B — khóa do HSM/provider quản lý

Ứng dụng lấy một `PrivateKey` handle từ KeyStore/provider. Khả năng export bị policy từ chối, còn provider hỗ trợ ký Ed25519.

**Cách làm tốt:** gọi `Signature.initSign(key)` với **đúng provider/engine tương thích**. Việc `getBytes()` rỗng hoặc `getEncoded()` trả null **không phải yêu cầu phải tái tạo khóa**. Đừng in key material để debug.

### Tình huống C — provider không hỗ trợ Ed25519 cho key handle

Key handle tồn tại, nhưng `Signature.getInstance("Ed25519")` trả engine không chấp nhận handle đó hoặc provider không triển khai EdDSA.

**Cách làm tốt:** kiểm tra provider configuration, key algorithm, slot, quyền, phiên bản token/firmware và danh sách thuật toán hỗ trợ. Không mặc định rằng việc export key ra heap là cách duy nhất để chạy được.

## 12. Ngoại lệ và lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getBytes().get()` ném `NoSuchElementException` | `Optional.empty()` | Kiểm tra `isPresent()/isEmpty()` hoặc dùng nhánh Optional an toàn |
| `getBytes()` rỗng trên khóa provider | Policy/implementation không muốn tiết lộ vật liệu | Dùng provider ký, hoặc báo export unsupported |
| `getEncoded() == null` | Key không hỗ trợ external encoding | Không truyền null vào `PKCS8EncodedKeySpec` |
| `getFormat() == null` | Không có định dạng encoding được công bố | Không đoán format và không ép giải mã |
| `ClassCastException` khi cast sang `EdECPrivateKey` | Provider trả `PrivateKey` implementation khác | Dùng `instanceof`, thiết kế theo `PrivateKey` khi chỉ cần ký |
| `InvalidKeyException` tại `initSign` | Sai loại khóa, provider không nhận key hoặc key/slot unavailable | Kiểm tra algorithm/provider/key capability |
| `NoSuchAlgorithmException` tại `getInstance` | Provider/JDK thiếu dịch vụ `Ed25519` | Dùng JDK/provider hỗ trợ thuật toán chuẩn |
| `InvalidKeySpecException` tại `generatePrivate` | Bytes/curve/spec sai hoặc provider không hỗ trợ spec | Kiểm tra raw EdEC vs PKCS#8 và curve |
| Chữ ký không xác minh được | Message bytes khác, sai public key hoặc thuật toán | Dùng đúng bytes, trusted public key và algorithm |
| `EdECPrivateKeySpec.getBytes()` luôn có bytes nhưng `EdECPrivateKey.getBytes()` đôi khi rỗng | Hai lớp có hợp đồng API khác nhau | Phân biệt transparent spec và provider-managed key |
| Đã gọi `Arrays.fill` nhưng nghĩ đã xóa khóa trong HSM | Chỉ xóa bản sao array caller nắm giữ | Quản lý lifecycle bằng provider/HSM policy |
| Thấy khóa không export được và tạo raw key ngẫu nhiên thay thế | Mất định danh và tạo chữ ký dưới key khác | Không thay khóa một cách âm thầm; dùng quy trình rotation/migration |
| In `Base64(raw)` để debug | Bí mật bị lộ vào log và hệ thống quan sát | Không xuất raw bytes nếu không cần; bảo vệ logging |
| Dùng `Optional.orElse(new byte[32])` | Chèn secret giả | Báo unavailable hoặc dùng direct `Signature` |

### Lỗi từ API ký không hoàn toàn đồng nghĩa lỗi từ API xuất

Một số lỗi có thể đến từ các giai đoạn khác nhau:

~~~text
Lấy PrivateKey handle từ provider
       |
       +-- getBytes() = Optional.empty()  -> raw không được cung cấp
       |
       +-- getEncoded() = null             -> không có external encoding
       |
       +-- initSign(key)                    -> provider có nhận key để ký?
             |
             +-- thành công -> sign(...)
             |
             +-- InvalidKeyException / provider error
                 -> kiểm tra key/algorithm/quyền/slot/cấu hình
~~~

Không dùng một cờ boolean `exportable` suy ra tất cả điều kiện ở trên. Ký, lấy raw bytes và lấy encoding có những hợp đồng khác nhau.

## 13. Quy tắc quản trị khóa non-exportable

Nếu hệ thống có nhu cầu bảo vệ private key:

1. **Sinh khóa ở nơi tin cậy** và chọn policy non-exportable ngay từ đầu khi khả thi. Một khi private key đã xuất ra plaintext ở nhiều nơi, việc “chuyển sang không xuất được” không hoàn tác được các bản sao cũ.
2. **Không xuất raw bytes theo mặc định.** Các thao tác ký/xác minh không cần biết seed.
3. **Sử dụng provider chính thức** và kiểm tra Ed25519 support. Nếu công cụ dùng KMS/HSM API riêng, tuân theo API đó thay vì ép tất cả về một giả định JCA.
4. **Phân quyền ký:** chỉ những dịch vụ/identity được ủy quyền mới có quyền gọi private-key operation.
5. **Phân phối public key có xác thực:** `Signature.verify` xác minh nội dung theo khóa, nhưng việc ai sở hữu public key phải do trust policy giải quyết.
6. **Quản lý rotation và thu hồi:** lưu key ID, trạng thái và quy tắc xác minh chữ ký cũ, tránh thay key im lặng.
7. **Phân biệt backup hợp lệ và export:** HSM/KMS có thể cung cấp backup/replication theo cơ chế bảo vệ riêng mà không tiết lộ raw bytes cho application.
8. **Log metadata không nhạy cảm:** algorithm, key ID đã được phép ghi, provider name và mã lỗi; không log raw private key, PKCS#8, password hoặc dữ liệu bí mật.
9. **Giới hạn vòng đời raw copies:** nếu bắt buộc export, dùng vùng xử lý được kiểm soát, không lưu plaintext vào cache/String bất biến, xóa byte arrays mình kiểm soát khi xong.
10. **Kiểm thử chính sách:** test trường hợp raw available, raw unavailable, encoded null, wrong provider và signer fail. Không đặt giả định rằng tất cả khóa sinh từ API đều export được.
11. **Tôn trọng ranh giới thiết bị:** provider từ chối export có thể là mục tiêu bảo mật, không phải lỗi cần lách.
12. **Không dùng exception để thử các cách xâm nhập:** không reflection vào internal fields hoặc parse memory dump để lấy seed.

### Vì sao không nên chuyển secret sang `String`?

`String` bất biến, ứng dụng không kiểm soát chính xác khi bộ nhớ chứa nội dung bị thu hồi hoặc ghi đè. Chuyển raw bytes thành `new String(...)`, hex hay Base64 có thể tạo thêm bản sao bí mật trong heap và log. Nếu nhu cầu export là hợp pháp, hãy bảo vệ **dạng bytes** trong phạm vi tối thiểu, theo đúng format và phương thức lưu trữ được phê duyệt.

## 14. Bài tập thực hành có đáp án

**Câu 1.** Tại sao `EdECPrivateKey.getBytes()` trả `Optional<byte[]>` thay vì luôn trả `byte[]`?

**Đáp án:** Provider có thể **không sẵn lòng tiết lộ private-key material** dù vẫn quản lý khóa để thực hiện các thao tác được phép. `Optional.empty()` biểu diễn trạng thái không có raw bytes mà không cần đánh đồng với khóa hỏng.

**Câu 2.** `getBytes().isEmpty()` có chứng minh khóa đã mất, bị revoke hoặc không còn ký được không?

**Đáp án:** **Không.** Nó chỉ cho biết method không cung cấp raw bytes. Khả năng ký phải được kiểm tra riêng qua provider và `Signature.initSign`, cùng các trạng thái/quyền vận hành.

**Câu 3.** `EdECPrivateKey.getBytes()` trả Optional chứa 32 bytes; có nên đưa trực tiếp vào `PKCS8EncodedKeySpec` không?

**Đáp án:** **Không.** Đó là raw private-key bytes/bit-string, không phải một PKCS#8-encoded key hoàn chỉnh. Nếu có quyền xử lý raw material, dùng đúng `EdECPrivateKeySpec`/`NamedParameterSpec` hoặc cơ chế export format chuẩn do provider cung cấp.

**Câu 4.** Một khóa `getEncoded() == null` có thể vẫn ký qua `Signature.initSign(key)` không?

**Đáp án:** Có thể, nếu provider giữ khóa và hỗ trợ signature operation bằng handle đó. `getEncoded()==null` chỉ mô tả việc không hỗ trợ external encoding qua API `Key`.

**Câu 5.** Nếu provider trả một object `PrivateKey` mà không implement `EdECPrivateKey`, ứng dụng còn có thể ký Ed25519 không?

**Đáp án:** Có thể, nếu provider `Signature` tương thích chấp nhận object `PrivateKey` đó. Không ép kiểu; dùng đúng thuật toán/provider, và chỉ xử lý EdEC-specific interface khi implementation có hỗ trợ.

**Câu 6.** Vì sao không nên viết `key.getBytes().orElse(new byte[32])`?

**Đáp án:** Khi raw không có, fallback tạo một giá trị khác không phải private key thực, gây lỗi định danh, export giả hoặc lỗ hổng bảo mật. Hãy xử lý không sẵn có như một nhánh nghiệp vụ riêng.

**Câu 7.** `EdECPrivateKeySpec.getBytes()` và `EdECPrivateKey.getBytes()` có cùng kiểu trả về không?

**Đáp án:** Không. Key spec trả **`byte[]`**, còn interface private key trả **`Optional<byte[]>`**. Key spec là biểu diễn minh bạch đã có bytes; private key object có thể opaque.

**Câu 8.** Sau `Arrays.fill(raw, 0)` có chắc toàn bộ private key đã biến mất khỏi RAM và provider không còn khóa không?

**Đáp án:** **Không.** Chỉ mảng `raw` mà caller có được ghi đè. Provider/HSM có bản thể/handle riêng; JVM có thể có copies/optimized allocations và memory dump khác.

**Câu 9.** Nếu mục tiêu duy nhất là tạo chữ ký cho một thông điệp, có cần gọi `getBytes()` trước `initSign` không?

**Đáp án:** **Không.** `Signature.initSign(PrivateKey)` nhận key object. Đây là cách ưu tiên để tránh xuất vật liệu khóa.

**Câu 10.** Có phải mọi khóa non-exportable trong Java đều implement `EdECPrivateKey` và trả `Optional.empty()`?

**Đáp án:** **Không.** Một số provider có key classes/handles opaque khác, hoặc không hỗ trợ Ed25519. Chỉ áp dụng hợp đồng `getBytes()` khi object thật sự implement `EdECPrivateKey`.

## 15. Checklist thiết kế và kiểm thử

Trước khi phát triển chức năng EdEC key handling, tự kiểm tra:

- **Chức năng chính có thực sự cần raw bytes?** Nếu chỉ ký/verify thì bỏ mọi bước trích xuất.
- **Kiểu khóa có đúng không?** `PrivateKey` để ký, `PublicKey` để verify, `EdECPrivateKey` chỉ khi cần thông tin EdEC cụ thể.
- **Có kiểm tra `instanceof` trước khi cast không?** Không giả định key objects từ mọi provider giống nhau.
- **`Optional` rỗng đã được xử lý đúng chưa?** Không `get()` mù, không dùng mảng zero làm fallback.
- **`getEncoded() == null` và `getFormat() == null` đã được xử lý riêng chưa?** Không nhập nhằng với `Optional.empty()`.
- **Có phân biệt raw EdEC bytes và PKCS#8 không?** Không import nhầm format.
- **Bản sao private bytes có bị log, serialize, đưa vào String hoặc cache không?** Mọi luồng xuất phải được cấp quyền.
- **Provider có ký được bằng key handle không?** Test với thiết bị/provider và policy thật, không chỉ key software.
- **Có test provider không implement `EdECPrivateKey` không?** Giữ code dùng được qua `PrivateKey` ở trường hợp ký thông thường.
- **Có đảm bảo `Signature.verify` dùng public key được tin cậy không?** Không tin public key bất kỳ do bên gửi cung cấp.
- **Có quản lý rotation, revoke, backup theo cơ chế chính thức không?** Không cố lách non-export policy.
- **Có hạn chế logging/memory copy khi buộc phải export không?** `Arrays.fill` chỉ là biện pháp giảm rủi ro có giới hạn.

## 16. Nguồn tiêu chuẩn và API còn được sử dụng

- **JEP 339 — Edwards-Curve Digital Signature Algorithm (Java 15):** https://openjdk.org/jeps/339
- **Oracle Java SE 17 — `EdECPrivateKey`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html
- **Oracle Java SE 17 — `EdECKey`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/EdECKey.html
- **Oracle Java SE 17 — `Key` (`getEncoded`, `getFormat`):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Key.html
- **Oracle Java SE 17 — `EdECPrivateKeySpec`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html
- **Oracle Java SE 17 — `PKCS8EncodedKeySpec`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html
- **Oracle Java SE 17 — `Signature`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- **RFC 8032 — EdDSA và private/public key representations:** https://www.rfc-editor.org/rfc/rfc8032

**Kết luận:** `EdECPrivateKey.getBytes()` trả **`Optional<byte[]>`** vì provider có quyền **không cung cấp raw private-key bytes**. Đó là trạng thái hợp lệ, không phải lỗi khóa. `Key.getEncoded()` là một API khác và có thể trả `null` nếu không hỗ trợ encoded form. Khi chỉ muốn ký, **giữ private key trong provider và truyền đối tượng `PrivateKey` vào `Signature.initSign`**, không trích xuất bí mật. Nếu thực sự cần export, phải được cấp quyền, xử lý cả nhánh `Optional.empty()`, chọn đúng raw/PKCS#8 format và bảo vệ vòng đời của mọi bản sao bí mật.
