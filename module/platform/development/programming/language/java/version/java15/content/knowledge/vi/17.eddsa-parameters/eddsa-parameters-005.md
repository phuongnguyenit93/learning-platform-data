# Java 15 — Khác biệt giữa context vắng mặt và context rỗng trong `EdDSAParameterSpec`

## 1. Vì sao hai cách viết nhìn giống nhau có thể tạo chữ ký khác nhau?

Java 15 bổ sung hỗ trợ EdDSA (Ed25519/Ed448) theo RFC 8032 và lớp `java.security.spec.EdDSAParameterSpec`. Khi cấu hình chữ ký, **context không được truyền** và **context có truyền nhưng dài 0 byte** là hai trạng thái riêng biệt trong API:

~~~java
EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
EdDSAParameterSpec empty =
        new EdDSAParameterSpec(false, new byte[0]);
~~~

Hai biến ở trên đều có `isPrehash() == false`, nhưng không đồng nghĩa hoàn toàn:

- `absent.getContext()` trả **`Optional.empty()`**: không có context được cung cấp.
- `empty.getContext()` trả **`Optional.of(new byte[0])`** theo nghĩa giá trị hiện diện có độ dài bằng 0.
- **Ed25519, không prehash:** trạng thái không có context chọn chế độ **Ed25519 thuần**; khi context hiện diện dù rỗng, Java chọn **Ed25519ctx**. Hai chế độ có domain separation khác nhau, nên chữ ký trên cùng khóa và thông điệp **khác nhau**.
- **Ed448, không prehash:** cả context vắng mặt và context hiện diện rỗng có **giá trị context hiệu dụng rỗng** trong thuật toán Ed448 chuẩn; chữ ký **giống nhau** trên cùng khóa và thông điệp, dù hai `EdDSAParameterSpec` vẫn phân biệt được bằng `getContext()`.
- **Các biến thể prehash (`true`):** context vắng mặt và context rỗng cũng cho cùng giá trị context hiệu dụng rỗng trong các chế độ Ed25519ph/Ed448ph. Việc bật prehash lại là một quyết định thuật toán **khác** với việc truyền context.

**Ý chính cần nhớ:** `absent` và `empty` khác nhau **ở mô hình tham số Java trong mọi trường hợp**, nhưng **có tạo chữ ký khác nhau hay không phụ thuộc biến thể EdDSA**. Không thay đổi cách tạo `EdDSAParameterSpec` chỉ vì nghĩ một mảng byte độ dài 0 chẳng mang thông tin gì.

### Mục tiêu học tập

1. Phân biệt `null`, không truyền context, mảng rỗng và mảng không rỗng.
2. Hiểu hai constructor, `getContext()`, `isPrehash()`, quy tắc sao chép byte và giới hạn 255 **byte**.
3. Giải thích khác biệt Ed25519/Ed25519ctx, Ed448 và các biến thể `ph` mà không tự suy đoán từ chữ ký.
4. Viết mã Java chạy được dùng `Signature.setParameter(...)`, kiểm tra chữ ký cùng context và cố tình xác minh sai context.
5. Áp dụng hợp đồng giao thức rõ ràng giữa bên ký và bên xác minh; tránh nhầm lẫn có thể làm các hệ thống từ chối chữ ký hợp lệ.

**Phạm vi:** API EdDSA chuẩn hóa ở Java 15 và tiếp tục được hỗ trợ trong Java hiện đại. Ví dụ sử dụng API chuẩn, chạy được khi biên dịch với `javac --release 15` trên JDK có hỗ trợ release đó; không dùng preview hoặc cơ chế đã lỗi thời.

## 2. Hợp đồng API chính thức của `EdDSAParameterSpec`

`EdDSAParameterSpec` thuộc package `java.security.spec`, triển khai `AlgorithmParameterSpec`. Hai constructor được hỗ trợ:

~~~java
new EdDSAParameterSpec(boolean prehash)
new EdDSAParameterSpec(boolean prehash, byte[] context)
~~~

Đây là **chữ ký minh họa** của constructor, không phải đoạn mã có thể đặt trực tiếp vào một file Java ở top level.

| Cách tạo | `isPrehash()` | `getContext().isPresent()` | `getContext()` phản ánh |
| --- | --- | --- | --- |
| `new EdDSAParameterSpec(false)` | `false` | `false` | Context **vắng mặt** |
| `new EdDSAParameterSpec(false, new byte[0])` | `false` | `true` | Context **có mặt, dài 0** |
| `new EdDSAParameterSpec(false, new byte[]{1, 2})` | `false` | `true` | Context có 2 byte |
| `new EdDSAParameterSpec(true)` | `true` | `false` | Prehash, context vắng mặt |
| `new EdDSAParameterSpec(true, new byte[0])` | `true` | `true` | Prehash, context rỗng |
| `new EdDSAParameterSpec(true, new byte[]{1, 2})` | `true` | `true` | Prehash, context có 2 byte |

**Chi tiết bắt buộc của Javadoc:**

- Constructor **một tham số** biểu diễn *không có context* (ngữ nghĩa nội bộ là `null`).
- Constructor **hai tham số** **không chấp nhận `null`**. Muốn không có context, dùng constructor một tham số, **không** dùng `new EdDSAParameterSpec(false, null)`.
- Constructor hai tham số **cho phép mảng rỗng**. Giá trị rỗng là một **context được cung cấp**, khác với vắng mặt trong API.
- Độ dài context tối đa **255 octet (255 byte)**. Context 256 byte gây `InvalidParameterException`; `null` gây `NullPointerException`.
- Constructor **sao chép** mảng input; `getContext()` cũng cung cấp **bản sao**. Đổi mảng gốc sau khi tạo spec hoặc sửa mảng lấy từ accessor không thay đổi context đã gắn trong spec.
- `getContext()` trả `Optional<byte[]>`, **không** trả trực tiếp `byte[]` hoặc `null`.

### 2.1. Vì sao không dùng `orElse(new byte[0])` một cách vô thức?

Xét mã minh họa:

~~~java
byte[] context = spec.getContext().orElse(new byte[0]);
~~~

Dòng này cố ý **gộp** hai trạng thái “không có” và “có nhưng rỗng” thành cùng mảng 0 byte. Nếu sau đó tạo lại `new EdDSAParameterSpec(false, context)`, bạn đã đổi chế độ **Ed25519 thuần** thành **Ed25519ctx với context rỗng**.

Nếu ứng dụng cần giữ đúng ngữ nghĩa, nên kiểm tra `isPresent()` trước khi dựng lại spec, hoặc lưu một cờ **contextPresent** bên cạnh mảng byte trong schema. Chỉ dùng `orElse(new byte[0])` nếu giao thức của bạn **cố ý** coi hai trạng thái là tương đương, và điều đó đã được kiểm thử với thuật toán sử dụng.

## 3. Bảng lựa chọn chế độ EdDSA theo đường cong, prehash và context

Theo Javadoc `EdDSAParameterSpec` và RFC 8032, có thể đọc bảng sau:

| Đường cong | `prehash` | Context trong spec | Chế độ / ý nghĩa |
| --- | --- | --- | --- |
| Ed25519 | `false` | **Vắng mặt** | **Ed25519 thuần**, không dùng `dom2` |
| Ed25519 | `false` | Hiện diện, **rỗng** | **Ed25519ctx** với context rỗng, **khác** Ed25519 thuần |
| Ed25519 | `false` | Hiện diện, có byte | **Ed25519ctx** với context đó |
| Ed25519 | `true` | Vắng mặt | **Ed25519ph**, context hiệu dụng rỗng |
| Ed25519 | `true` | Hiện diện, rỗng | **Ed25519ph**, context hiệu dụng rỗng, cùng kết quả với hàng trước |
| Ed25519 | `true` | Hiện diện, có byte | **Ed25519ph** với context đó |
| Ed448 | `false` | Vắng mặt | **Ed448**, context hiệu dụng rỗng |
| Ed448 | `false` | Hiện diện, rỗng | **Ed448**, context hiệu dụng rỗng, cùng kết quả với hàng trước |
| Ed448 | `false` | Hiện diện, có byte | **Ed448** với context đó |
| Ed448 | `true` | Vắng mặt hoặc rỗng | **Ed448ph**, context hiệu dụng rỗng |
| Ed448 | `true` | Hiện diện, có byte | **Ed448ph** với context đó |

**Không nên suy luận “EdDSA có context” là một thuật toán mới tên `Ed448ctx`.** RFC 8032 gọi nó là **Ed448**, có hỗ trợ context; `Ed25519ctx` là biến thể được đặt tên riêng của Ed25519 khi không prehash.

### 3.1. Lưu ý riêng của RFC 8032 về Ed25519ctx rỗng

RFC 8032 quy định **context trong Ed25519ctx SHOULD NOT rỗng**. Java **cho phép** `new EdDSAParameterSpec(false, new byte[0])` để biểu diễn mode có context hiện diện và rỗng, nhưng điều đó không biến nó thành lựa chọn khuyến nghị cho giao thức mới.

Nếu sản phẩm cần **Ed25519 chuẩn, không context**, hãy chọn:

~~~java
new EdDSAParameterSpec(false)
~~~

hoặc dùng mode mặc định Ed25519 của provider được kiểm thử. **Đừng** thêm `new byte[0]` chỉ để “truyền tham số cho đầy đủ”.

Nếu sản phẩm có yêu cầu **domain separation bằng Ed25519ctx**, hãy dùng context **không rỗng** do giao thức định nghĩa (ví dụ nhãn cố định theo phiên bản), và bảo đảm các bên sử dụng **cùng byte context**. Không tự áp dụng context cho giao thức chữ ký hiện hữu nếu giao thức ấy không hỗ trợ.

## 4. Vì sao Ed25519 khác Ed448? Cơ chế domain separation

Context trong EdDSA là một đầu vào đặc biệt của phép tính chữ ký. Nó **không** phải metadata gắn thêm bên ngoài chữ ký sau khi ký, cũng không chỉ là chuỗi được nối vào message mà ứng dụng tự quy ước.

### 4.1. Ed25519 và `dom2`

RFC 8032 xác định cơ chế domain separation `dom2(F, C)` cho các biến thể Ed25519:

- **Ed25519 thuần:** không sử dụng prefix `dom2`.
- **Ed25519ctx:** dùng `dom2` với cờ prehash bằng 0 và context `C`. Kể cả khi `C` dài 0, prefix domain separation vẫn **hiện diện**.
- **Ed25519ph:** dùng cờ prehash bằng 1, hash thông điệp theo chế độ prehash và dùng `dom2`; context vắng mặt hay mảng rỗng có cùng giá trị hiệu dụng rỗng.

Vì vậy, cùng private key và cùng message nhưng:

~~~text
Ed25519 pure
    -> không có dom2 prefix
Ed25519ctx, context = byte[0]
    -> có dom2 prefix cho mode ctx, length(context)=0
~~~

hai chữ ký **khác nhau**. Một chữ ký Ed25519ctx không được chấp nhận khi verifier đang chạy Ed25519 thuần (và ngược lại) vì chúng tính challenge khác nhau.

**Lưu ý cách diễn đạt:** không chỉ vì “số byte context khác nhau” — cả hai đều có **0 byte context hiệu dụng**; cái làm khác là **có chọn biến thể dùng domain separation hay không**.

### 4.2. Ed448 và `dom4`

Ed448 dùng cơ chế domain separation `dom4(F, C)` **ngay trong chế độ Ed448 thông thường**. RFC 8032 quy định context mặc định là chuỗi byte rỗng. Vì vậy:

~~~text
Ed448, không cung cấp context
    -> dom4 với context hiệu dụng dài 0
Ed448, cung cấp byte[0]
    -> dom4 với context hiệu dụng dài 0
~~~

trên cùng khóa, message và cờ prehash, hai đường tạo cùng chữ ký. Nếu truyền context **không rỗng**, giá trị `dom4` đổi và chữ ký sẽ khác; verifier phải dùng đúng context.

### 4.3. Prehash là chiều cấu hình **độc lập**

`new EdDSAParameterSpec(true)` chuyển sang Ed25519ph hoặc Ed448ph. Đây là thay đổi **cách xử lý message trước khi ký**, không phải “context vắng mặt” hay “context rỗng”.

Không tự hash message bằng `MessageDigest` rồi bật `prehash=true` mà không hiểu giao thức: API EdDSA xử lý chế độ prehash theo thuật toán; hash ở tầng ứng dụng rồi bật prehash có thể tạo **double-hashing** và không tương thích với các bên khác.

Thông thường chỉ chọn biến thể prehash khi **giao thức yêu cầu rõ ràng** và bên ký/bên xác minh đều hỗ trợ. Với mục đích đơn giản, `Ed25519` thuần thường là lựa chọn dễ tương thích hơn; tránh đổi mode chỉ vì thấy `true` “an toàn hơn”.

## 5. Chương trình Java hoàn chỉnh: kiểm tra vắng mặt, rỗng và chữ ký

Lưu toàn bộ mã dưới đây thành **`EdDsaContextModesDemo.java`**. Mã tạo khóa ngẫu nhiên **cho mỗi đường cong một lần**, ký hai lần với cùng key/message nhưng spec khác nhau, rồi so sánh và xác minh chéo. Nó cũng kiểm tra giới hạn context, `Optional` và defensive copy. Không in private key hay signature bytes.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.InvalidParameterException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDsaContextModesDemo {
    private static final byte[] MESSAGE =
            "same-message".getBytes(StandardCharsets.UTF_8);

    private static byte[] sign(KeyPair keyPair, String algorithm,
                               EdDSAParameterSpec params) throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.setParameter(params);
        signer.initSign(keyPair.getPrivate());
        signer.update(MESSAGE);
        return signer.sign();
    }

    private static boolean verifies(KeyPair keyPair, String algorithm,
                                    EdDSAParameterSpec params, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.setParameter(params);
        verifier.initVerify(keyPair.getPublic());
        verifier.update(MESSAGE);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
        EdDSAParameterSpec empty =
                new EdDSAParameterSpec(false, new byte[0]);

        System.out.println("absentPresent=" +
                absent.getContext().isPresent());
        System.out.println("emptyPresent=" +
                empty.getContext().isPresent());
        System.out.println("emptyLength=" +
                empty.getContext().orElseThrow().length);

        byte[] contextInput = {1, 2, 3};
        EdDSAParameterSpec defensive =
                new EdDSAParameterSpec(false, contextInput);
        contextInput[0] = 9;
        System.out.println("constructorCopy=" +
                (defensive.getContext().orElseThrow()[0] == 1));

        byte[] exported = defensive.getContext().orElseThrow();
        exported[0] = 8;
        System.out.println("accessorCopy=" +
                (defensive.getContext().orElseThrow()[0] == 1));

        boolean nullRejected;
        try {
            new EdDSAParameterSpec(false, (byte[]) null);
            nullRejected = false;
        } catch (NullPointerException expected) {
            nullRejected = true;
        }

        boolean longRejected;
        try {
            new EdDSAParameterSpec(false, new byte[256]);
            longRejected = false;
        } catch (InvalidParameterException expected) {
            longRejected = true;
        }

        System.out.println("nullRejected=" + nullRejected);
        System.out.println("tooLongRejected=" + longRejected);
        System.out.println("max255Accepted=" +
                (new EdDSAParameterSpec(false, new byte[255])
                        .getContext().orElseThrow().length == 255));

        compare("Ed25519", absent, empty);
        compare("Ed448", absent, empty);

        EdDSAParameterSpec preAbsent = new EdDSAParameterSpec(true);
        EdDSAParameterSpec preEmpty =
                new EdDSAParameterSpec(true, new byte[0]);

        compare("Ed25519", preAbsent, preEmpty, "ph");
        compare("Ed448", preAbsent, preEmpty, "ph");
    }

    private static void compare(String algorithm,
                                EdDSAParameterSpec absent,
                                EdDSAParameterSpec empty) throws Exception {
        compare(algorithm, absent, empty, "pure");
    }

    private static void compare(String algorithm,
                                EdDSAParameterSpec absent,
                                EdDSAParameterSpec empty,
                                String mode) throws Exception {
        KeyPair pair =
                KeyPairGenerator.getInstance(algorithm).generateKeyPair();
        byte[] signatureAbsent = sign(pair, algorithm, absent);
        byte[] signatureEmpty = sign(pair, algorithm, empty);

        System.out.println(algorithm + "-" + mode +
                " signaturesEqual=" +
                Arrays.equals(signatureAbsent, signatureEmpty));
        System.out.println(algorithm + "-" + mode +
                " ownVerifies=" +
                verifies(pair, algorithm, absent, signatureAbsent) + "," +
                verifies(pair, algorithm, empty, signatureEmpty));
        System.out.println(algorithm + "-" + mode +
                " crossVerifies=" +
                verifies(pair, algorithm, empty, signatureAbsent) + "," +
                verifies(pair, algorithm, absent, signatureEmpty));
    }
}
~~~

Biên dịch và chạy với JDK hỗ trợ `--release 15`:

~~~bash
javac --release 15 -Xlint:all EdDsaContextModesDemo.java
java EdDsaContextModesDemo
~~~

**Stdout chính xác đã được kiểm chứng trên JDK với provider EdDSA tích hợp:**

~~~text
absentPresent=false
emptyPresent=true
emptyLength=0
constructorCopy=true
accessorCopy=true
nullRejected=true
tooLongRejected=true
max255Accepted=true
Ed25519-pure signaturesEqual=false
Ed25519-pure ownVerifies=true,true
Ed25519-pure crossVerifies=false,false
Ed448-pure signaturesEqual=true
Ed448-pure ownVerifies=true,true
Ed448-pure crossVerifies=true,true
Ed25519-ph signaturesEqual=true
Ed25519-ph ownVerifies=true,true
Ed25519-ph crossVerifies=true,true
Ed448-ph signaturesEqual=true
Ed448-ph ownVerifies=true,true
Ed448-ph crossVerifies=true,true
~~~

### 5.1. Giải thích `Optional` và việc sao chép mảng

Ba dòng đầu xác nhận **API phân biệt hai trạng thái**: vắng mặt là `Optional.empty()`; hiện diện rỗng là `Optional` có giá trị dài 0. Hai dòng `constructorCopy=true` và `accessorCopy=true` chứng minh Java **sao chép bytes** vào spec, đồng thời `getContext()` cung cấp một **bản sao khác**. Vì vậy việc tái sử dụng/mutate mảng input không làm thay đổi tham số chữ ký một cách bất ngờ.

`nullRejected=true` và `tooLongRejected=true` xác nhận hai lỗi API riêng biệt. `max255Accepted=true` cho thấy 255 byte là giới hạn **bao gồm**; mảng 256 byte bị từ chối ngay khi khởi tạo spec.

### 5.2. Vì sao `Ed25519-pure` có chữ ký khác nhau?

`Ed25519-pure signaturesEqual=false` nghĩa là hai chữ ký trên **cùng** message và key khác byte, vì mode Ed25519 thuần và Ed25519ctx context rỗng khác nhau. `ownVerifies=true,true` chứng minh mỗi chữ ký hợp lệ khi verifier dùng đúng spec. `crossVerifies=false,false` chứng minh dùng nhầm spec không xác minh được.

Lưu ý chữ **`pure` trong nhãn output** chỉ để phân biệt `prehash=false` với `prehash=true` trong code. Khi context hiện diện, trường hợp thứ hai vẫn là **Ed25519ctx**, không phải Ed25519 thuần; không suy diễn tên mode từ nhãn in log.

### 5.3. Vì sao `Ed448-pure` có chữ ký giống nhau?

Ed448 dùng context hiệu dụng rỗng khi không cung cấp; đưa mảng rỗng vào spec không làm thay đổi giá trị ấy. Vì vậy `signaturesEqual=true` và cả hai chiều xác minh chéo `true,true`. Kết luận này áp dụng khi **cùng key, message, prehash và các tham số khác** như trong chương trình, không phải khẳng định mọi chữ ký Ed448 với mọi context đều bằng nhau.

### 5.4. Vì sao hai nhãn `-ph` cũng có chữ ký giống nhau?

Các dòng `Ed25519-ph` và `Ed448-ph` dùng `prehash=true`. Ed25519ph/Ed448ph luôn dùng cơ chế domain separation tương ứng và context hiệu dụng rỗng khi không cung cấp; context được cung cấp nhưng dài 0 tạo cùng giá trị. Các chữ ký `-ph` **không** được tự động xem là tương thích với mode `prehash=false` chỉ vì chữ ký nội bộ của một cặp absent/empty bằng nhau.

### 5.5. Các giá trị output có ngẫu nhiên không?

Keypair được tạo ngẫu nhiên mỗi lần chạy, vì vậy bytes của chữ ký có thể khác giữa hai lượt chạy. Nhưng trong từng cặp so sánh, chương trình dùng **cùng keypair, cùng message và chỉ thay một điểm cấu hình**. EdDSA theo RFC 8032 là lược đồ chữ ký xác định với input như nhau; phép so sánh `signaturesEqual` kiểm tra tính tương thích mode, không yêu cầu cố định signature hex trong giáo trình.

## 6. Chương trình thực tế hơn: kiểm tra chế độ mặc định và context nghiệp vụ

Chương trình thứ hai cho thấy một lỗi thường gặp trong hệ thống phân tán: bên ký chuyển context thành một **chuỗi bytes gắn với mục đích nghiệp vụ**, trong khi bên xác minh dùng tên/phiên bản khác. Kết quả là verification thất bại dù public key và thông điệp đều đúng.

Lưu file độc lập **`EdDsaContextInteropDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.util.Arrays;

public class EdDsaContextInteropDemo {
    private static final byte[] MESSAGE =
            "invoice=42".getBytes(StandardCharsets.UTF_8);

    private static byte[] sign(KeyPair pair, String curve,
                               EdDSAParameterSpec parameters)
            throws Exception {
        Signature signer = Signature.getInstance(curve);
        if (parameters != null) {
            signer.setParameter(parameters);
        }
        signer.initSign(pair.getPrivate());
        signer.update(MESSAGE);
        return signer.sign();
    }

    private static boolean verify(KeyPair pair, String curve,
                                  EdDSAParameterSpec parameters,
                                  byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance(curve);
        if (parameters != null) {
            verifier.setParameter(parameters);
        }
        verifier.initVerify(pair.getPublic());
        verifier.update(MESSAGE);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair ed25519 = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        EdDSAParameterSpec absent = new EdDSAParameterSpec(false);
        EdDSAParameterSpec empty =
                new EdDSAParameterSpec(false, new byte[0]);

        EdDSAParameterSpec named = new EdDSAParameterSpec(
                false, "invoices:v1".getBytes(StandardCharsets.UTF_8));
        EdDSAParameterSpec other = new EdDSAParameterSpec(
                false, "contracts:v1".getBytes(StandardCharsets.UTF_8));

        byte[] defaultSignature = sign(ed25519, "Ed25519", null);
        byte[] absentSignature = sign(ed25519, "Ed25519", absent);
        byte[] emptySignature = sign(ed25519, "Ed25519", empty);
        byte[] namedSignature = sign(ed25519, "Ed25519", named);

        System.out.println("defaultEqualsAbsent=" +
                Arrays.equals(defaultSignature, absentSignature));
        System.out.println("emptyDiffers=" +
                !Arrays.equals(absentSignature, emptySignature));
        System.out.println("namedVerifies=" +
                verify(ed25519, "Ed25519", named, namedSignature));
        System.out.println("wrongContextRejects=" +
                !verify(ed25519, "Ed25519", other, namedSignature));

        KeyPair ed448 = KeyPairGenerator.getInstance("Ed448")
                .generateKeyPair();
        byte[] noContext448 = sign(ed448, "Ed448", absent);
        byte[] empty448 = sign(ed448, "Ed448", empty);
        byte[] named448 = sign(ed448, "Ed448", named);

        System.out.println("ed448AbsentEqualsEmpty=" +
                Arrays.equals(noContext448, empty448));
        System.out.println("ed448NamedDiffers=" +
                !Arrays.equals(empty448, named448));
        System.out.println("ed448WrongContextRejects=" +
                !verify(ed448, "Ed448", other, named448));
    }
}
~~~

~~~bash
javac --release 15 -Xlint:all EdDsaContextInteropDemo.java
java EdDsaContextInteropDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
defaultEqualsAbsent=true
emptyDiffers=true
namedVerifies=true
wrongContextRejects=true
ed448AbsentEqualsEmpty=true
ed448NamedDiffers=true
ed448WrongContextRejects=true
~~~

**Điểm học được:**

1. Với provider được kiểm thử, mode mặc định của `Signature.getInstance("Ed25519")` khi không `setParameter` tương thích `new EdDSAParameterSpec(false)`: kết quả `defaultEqualsAbsent=true`.
2. `new EdDSAParameterSpec(false, new byte[0])` không phải một cách viết thay thế mode mặc định Ed25519: `emptyDiffers=true`.
3. Context `"invoices:v1"` và `"contracts:v1"` khác nhau ở mức byte; dù cùng key và message, chữ ký được ký với `invoices:v1` không xác minh theo `contracts:v1`: `wrongContextRejects=true`.
4. Đối với Ed448, context vắng mặt và rỗng cho cùng chữ ký (`ed448AbsentEqualsEmpty=true`), nhưng một context có nội dung khác làm đổi chữ ký (`ed448NamedDiffers=true`) và không xác minh được với context khác (`ed448WrongContextRejects=true`).

**Lưu ý quan trọng cho người dùng API:** ở hàm `sign/verify` của ví dụ, giá trị Java `parameters == null` chỉ là **quy ước nội bộ của hàm ví dụ để không gọi `setParameter`**. Nó **không** có nghĩa bạn được truyền `null` làm tham số `context` cho constructor hai tham số; hai tình huống là hoàn toàn khác nhau.

## 7. Cách cấu hình `Signature` đúng trong JCA

Để ký với context rõ ràng, thực hiện những bước tương ứng:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(new EdDSAParameterSpec(
        false, "invoices:v1".getBytes(StandardCharsets.UTF_8)));
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Đây là **đoạn minh họa trong method**, có các `import` cần thiết; `privateKey` và `messageBytes` phải là giá trị có sẵn và đúng loại. Chương trình hoàn chỉnh ở phần 6 đã biên dịch/chạy, trong đó `Signature` được tạo mới cho từng phép ký và xác minh.

Phía xác minh:

~~~java
Signature verifier = Signature.getInstance("Ed25519");
verifier.setParameter(new EdDSAParameterSpec(
        false, "invoices:v1".getBytes(StandardCharsets.UTF_8)));
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
~~~

**Các bên phải khớp**: đường cong/thuật toán, chế độ prehash, ngữ nghĩa context (bao gồm absent vs present), chính xác từng byte context và chính xác bytes thông điệp. Một chuỗi tên protocol có thể trông giống nhau trên hai hệ thống nhưng khác encoding/canonicalization, dẫn đến không xác minh được.

### 7.1. Gọi `setParameter` khi nào?

API `Signature.setParameter(AlgorithmParameterSpec)` dùng để cung cấp `EdDSAParameterSpec` cho provider. Trong hai chương trình đã kiểm thử, chúng ta gọi **trước `initSign/initVerify` và trước `update(...)`**. Điều này làm cấu hình hiển thị rõ và tránh các vấn đề trạng thái khi cố đổi mode sau khi đã nhập một phần message.

Không đổi tham số giữa lúc `update` và `sign/verify`. Khi cần ký theo context khác, dễ kiểm toán nhất là tạo **một đối tượng `Signature` mới**, set spec rồi init/update/sign cho mode tương ứng.

### 7.2. `Signature.getInstance("Ed25519")` và `EdDSAParameterSpec` khác nhau

Tên `"Ed25519"` chỉ chọn thuật toán và khả năng provider; tham số có thể bổ sung mode (prehash/context) của EdDSA. Cụ thể, `"Ed25519"` **không buộc** ứng dụng phải dùng context vắng mặt trong mọi tình huống: provider EdDSA trong JDK hỗ trợ các biến thể RFC 8032 qua `EdDSAParameterSpec`.

Mã chọn algorithm và mã chọn spec cần được **đặt cạnh nhau** trong tài liệu giao thức. Chỉ lưu chuỗi `"Ed25519"` trong cấu hình chưa đủ khi sản phẩm dùng Ed25519ctx hay Ed25519ph. Đối với tiêu chuẩn giao thức bên ngoài, phải kiểm tra giao thức ấy **có chấp nhận context/mode này hay không**, không tự thay đổi signature profile chỉ vì JDK có khả năng ký được.

## 8. Context là **chuỗi byte**, không phải chuỗi ký tự tùy tiện

`EdDSAParameterSpec` nhận `byte[]`. Giới hạn 255 nói về số **byte**, không phải số ký tự Java hoặc số ký tự Unicode. Nếu hệ thống muốn context như `"invoices:v1"`, phải định nghĩa cách encoding:

~~~java
byte[] contextBytes =
        "invoices:v1".getBytes(StandardCharsets.UTF_8);
EdDSAParameterSpec params =
        new EdDSAParameterSpec(false, contextBytes);
~~~

Đây là đoạn minh họa trong method với `StandardCharsets` đã import. Context không tự được normalize Unicode, lowercase, trim hoặc giải mã Base64 bởi `EdDSAParameterSpec`. Những quy ước ấy, nếu cần, phải do protocol định nghĩa rõ trước khi chuyển thành bytes.

### 8.1. Những cặp context khác nhau

| Context | Quan hệ |
| --- | --- |
| Vắng mặt (constructor một tham số) | Không có context trong cấu hình Java |
| `new byte[0]` | Có context, độ dài 0 |
| UTF-8 của `"orders:v1"` | Có context, độ dài dương |
| UTF-8 của `"Orders:v1"` | Khác `"orders:v1"` vì bytes khác |
| UTF-8 của `"orders:v1 "` | Khác `"orders:v1"` vì space cuối được ký vào context |
| Hai chuỗi Unicode giống mặt chữ nhưng khác cách chuẩn hóa | Có thể có UTF-8 bytes khác nhau |
| 255 byte | Được constructor chấp nhận |
| 256 byte | Bị constructor từ chối |

Người thiết kế protocol nên dùng một **nhãn hằng, ngắn, chính xác bytes**, định nghĩa từ trước, và đưa nhãn/phiên bản này vào specification cả bên ký và bên xác minh. Không ghép ID request, timestamp, chữ ký hoặc nội dung message vào context nếu không có lý do protocol rõ ràng.

RFC 8032 `8.3 khuyến cáo context **nên là chuỗi hằng do giao thức quy định**, không nên chứa các thành phần biến thiên lấy từ chính message, và không được bật “tùy hứng” ở một vài phía. Context là cơ chế **domain separation có hợp đồng**, không phải trường metadata ngẫu nhiên.

### 8.2. Không nhầm `context` với `message` hay `salt`

- **Message** là dữ liệu đưa qua `Signature.update(...)` để ký.
- **Context** là byte string nằm trong cấu hình thuật toán, được đưa vào domain separation theo RFC 8032.
- **Salt/nonce** là khái niệm của những lược đồ mật mã khác; EdDSA không dùng `EdDSAParameterSpec.context` như một random salt nên không tự sinh context ngẫu nhiên mỗi lần ký.
- **Prehash flag** chọn biến thể ký prehashed; nó cũng không phải context.

Nếu hệ thống cần chứng minh chữ ký thuộc về một đơn hàng cụ thể, thường dữ liệu đơn hàng thuộc **message đã được canonicalize và ký**, trong khi context là **nhãn hằng của giao thức**.

## 9. Chuyển đổi cấu hình và lưu trữ mà không mất trạng thái absent

Một schema chỉ có trường:

~~~json
{"context": ""}
~~~

có thể khó phân biệt **context rỗng có chủ ý** và **context bị bỏ qua** nếu tầng serialize/deserialize thay `null`, missing field và chuỗi rỗng cho nhau. Đây là vấn đề tương thích chữ ký, không chỉ vấn đề thẩm mỹ dữ liệu.

Gợi ý mô hình dữ liệu rõ ràng:

~~~text
SignatureMode:
  curve: Ed25519 | Ed448
  prehash: true | false
  contextPresence: absent | present
  contextBytes: byte[] (chỉ khi present; có thể dài 0)
~~~

Đây là **sơ đồ cấu hình**, không phải cú pháp Java/JSON để import trực tiếp. Trước khi ký hay xác minh, kiểm tra:

1. Curve hợp lệ và đúng key algorithm.
2. Mode prehash được giao thức chấp nhận.
3. Context **absent hay present** rõ ràng.
4. Nếu present, bytes chính xác và dài không quá 255.
5. Với Ed25519ctx, context rỗng chỉ được dùng khi một protocol hiện hữu bắt buộc; thiết kế mới nên tránh theo RFC.
6. Bên ký/bên xác minh dùng cùng quy ước; không tự quy đổi absent thành empty trong tầng DTO.

### 9.1. Đoạn mã tái tạo đúng spec từ hai trạng thái

~~~java
static EdDSAParameterSpec makeSpec(
        boolean prehash, boolean contextPresent, byte[] context) {
    if (!contextPresent) {
        return new EdDSAParameterSpec(prehash);
    }
    if (context == null) {
        throw new IllegalArgumentException(
                "Present context must contain a byte array");
    }
    return new EdDSAParameterSpec(prehash, context);
}
~~~

Đây là **một method minh họa** nằm trong class có import `EdDSAParameterSpec`. Nó giữ rõ bất biến: khi absent, không dùng bytes; khi present, phải có mảng (có thể là mảng rỗng). Gắn thêm validation schema và authorization của hệ thống ở tầng gọi nếu config được cung cấp từ nguồn ngoài.

### 9.2. Bảo vệ ranh giới Ed25519 thuần khi interop

Trong một số protocol, thuật toán được cố định là **Ed25519 thuần**; parser của một phía trả context mặc định là `new byte[0]`. Nếu ứng dụng dựng spec bằng constructor hai tham số và ký theo Ed25519ctx rỗng, chữ ký sẽ không tương thích phía kia dù mã key/message chuẩn.

Hướng sửa: định nghĩa policy **Ed25519 thuần → context absent** và dùng `new EdDSAParameterSpec(false)`, không chỉ kiểm tra byte context rỗng. Nếu cần mode Ed25519ctx, phải cấu hình **cả hai phía** theo mode đó và dùng context không rỗng như giao thức yêu cầu.

Với Ed448, absent/empty có thể tạo cùng bytes chữ ký, nhưng **giữ nguyên hai trạng thái trong dữ liệu cấu hình** vẫn hữu ích để bảo toàn ý định protocol, phục vụ kiểm toán và tránh đổ quy tắc Ed448 sang Ed25519 về sau.

## 10. Tính bảo mật và tương thích của context

### 10.1. Context giúp tách miền, không thay chữ ký hay xác thực khóa

Domain separation giúp phân biệt các cách dùng chữ ký trong những giao thức khác nhau khi chúng được cấu hình đúng. Tuy nhiên:

- Context **không phải khóa bí mật**. Nó nên được xác định công khai và nhất quán theo protocol.
- Context **không thay thế** xác minh `Signature.verify`, kiểm tra public key thuộc danh tính nào, chứng chỉ/trust chain hoặc chính sách cấp quyền.
- Context **không mã hóa message**, không bảo mật thông tin và không ngăn replay một cách tự động.
- Context **không tự ngăn nhầm định dạng input**; phải có giao thức về message serialization, encoding và canonicalization.
- Context không nên là giá trị khách hàng tự chọn tùy ý nếu server cần ngăn các thao tác ký vượt quyền; quyền ký phải được kiểm soát độc lập.

### 10.2. Những trường hợp mismatch phổ biến

| Bên ký | Bên xác minh | Kết quả mong đợi |
| --- | --- | --- |
| Ed25519 thuần / context absent | Ed25519 thuần / absent | Hợp lệ với đúng key/message |
| Ed25519ctx / context empty | Ed25519 thuần / absent | **Không hợp lệ** |
| Ed25519ctx / `"invoices:v1"` | Ed25519ctx / `"contracts:v1"` | **Không hợp lệ** |
| Ed25519ctx / cùng bytes context | Ed25519ctx / cùng bytes context | Hợp lệ với đúng key/message |
| Ed448 / absent | Ed448 / empty | **Tương thích** theo context hiệu dụng rỗng |
| Ed448 / `"invoices:v1"` | Ed448 / `"contracts:v1"` | **Không hợp lệ** |
| Ed25519ph | Ed25519 không prehash | **Không cùng mode**, không tương thích |
| Ed448ph | Ed448 không prehash | **Không cùng mode**, không tương thích |

“Không hợp lệ” ở đây nghĩa là thao tác verify chữ ký không thành công **khi các yếu tố khác giữ nguyên** như ví dụ. Trong code production, provider có thể ném ngoại lệ khi cấu hình không được hỗ trợ hoặc key không phù hợp; cần phân biệt lỗi thiết lập API với một chữ ký sai thông thường.

### 10.3. Không dùng context để né kiểm tra thuật toán

Mã có chữ ký không tự chứng minh nguồn gốc hay quyền dùng public key. Khi nhận chữ ký từ bên ngoài, hệ thống phải quyết định **thuật toán được phép, key id đáng tin, message canonicalization và mode** trước khi verify. Không chạy một vòng thử nhiều mode/context bất kỳ cho đến khi “có mode verify được” nếu giao thức không cho phép điều đó: cách làm ấy làm suy yếu hợp đồng thuật toán và mở rộng bề mặt nhầm lẫn.

## 11. Các lỗi hay mắc và cách sửa

**Lỗi 1 — Coi `Optional.empty()` và `Optional.of(new byte[0])` như nhau.**  
Hai trạng thái khác trong Java. Với Ed25519 không prehash, chúng chọn **Ed25519** và **Ed25519ctx** khác nhau. Sửa: giữ cờ context-present hoặc lựa chọn constructor đúng theo mode.

**Lỗi 2 — Truyền `null` làm context cho constructor hai tham số.**  
`new EdDSAParameterSpec(false, null)` ném `NullPointerException`. Sửa: dùng constructor một tham số khi **không có context**.

**Lỗi 3 — Suy từ Ed448 rằng Ed25519 absent=empty.**  
Ed448 có context hiệu dụng rỗng trong cả hai trường hợp; Ed25519 thuần **không dùng `dom2`**, còn Ed25519ctx rỗng vẫn có prefix `dom2`. Sửa: kiểm thử/định nghĩa mode theo **đường cong**.

**Lỗi 4 — Dùng Ed25519ctx rỗng chỉ vì Java cho phép.**  
RFC 8032 nêu Ed25519ctx context **SHOULD NOT empty**. Với Ed25519 thuần, dùng constructor một tham số; với Ed25519ctx, định nghĩa context **không rỗng** theo protocol.

**Lỗi 5 — Giới hạn 255 **ký tự** thay vì 255 **byte**.**  
Constructor nhận `byte[]` và giới hạn 255 octet. Với Unicode UTF-8, một ký tự có thể chiếm nhiều byte. Sửa: encode bằng charset cố định rồi kiểm tra `contextBytes.length`.

**Lỗi 6 — Tạo context từ `String.getBytes()` không chỉ rõ encoding.**  
Charset mặc định hoặc các bước normalize có thể khác nhau giữa hệ thống. Sửa: dùng `StandardCharsets.UTF_8` và quy ước canonicalization của protocol.

**Lỗi 7 — Chỉnh sửa mảng context sau khi dựng spec và kỳ vọng chữ ký thay đổi.**  
Constructor sao chép context; `getContext()` cũng trả bản sao. Sửa: tạo spec mới khi cần đổi bytes, đừng dựa vào mutation của mảng cũ.

**Lỗi 8 — Nối context vào message rồi cho rằng bằng `EdDSAParameterSpec`.**  
Domain separation của EdDSA theo RFC 8032 không giống tùy tiện nối chuỗi. Sửa: dùng `EdDSAParameterSpec` khi giao thức yêu cầu, không tạo protocol ad-hoc.

**Lỗi 9 — Bật `prehash=true` mà không cập nhật phía verify.**  
Ed25519ph/Ed448ph khác mode không prehash. Sửa: ràng buộc mode trong giao thức; đừng bật prehash như một “tăng bảo mật” mặc định.

**Lỗi 10 — Hash message bằng SHA-512 rồi còn bật prehash trong Signature.**  
Có thể tạo quy trình khác chuẩn/phụ thuộc tầng gọi, không tương thích bên nhận. Sửa: để provider áp dụng chế độ prehash của RFC nếu thật sự được protocol quy định.

**Lỗi 11 — Một object `Signature` được chia sẻ nhiều thread và sửa parameter giữa các request.**  
`Signature` có trạng thái ký/xác minh; đổi mode hay dùng đồng thời có thể làm kết quả khó dự đoán. Sửa: tạo instance riêng cho từng phép toán hoặc quản lý vòng đời/synchronization theo hợp đồng provider.

**Lỗi 12 — Khi verify thất bại, tự thử tất cả context khác nhau.**  
Điều này che giấu cấu hình sai và có thể làm rối trust boundary. Sửa: xác định mode/context chính xác từ protocol trước khi xác minh.

**Lỗi 13 — Chỉ lưu tên `"Ed25519"` mà bỏ mất `prehash/contextPresent/contextBytes`.**  
Đối tác có thể hiểu là Ed25519 thuần, trong khi bên ký đang dùng Ed25519ctx. Sửa: schema cần lưu đủ **signature profile**.

**Lỗi 14 — Nghĩ `context` mã hóa message hoặc chống replay tự động.**  
Context là domain separator, không bảo vệ bí mật hay thay policy chống replay. Sửa: thiết kế nonce/timestamp/message ID và kiểm tra phù hợp trong protocol.

## 12. Bài tập tự kiểm tra

**Câu 1.** `new EdDSAParameterSpec(false)` và `new EdDSAParameterSpec(false, new byte[0])` có cùng trạng thái Java không?  
**Đáp án:** Không. `getContext()` của cái đầu là `Optional.empty()`, của cái sau có giá trị byte array độ dài 0.

**Câu 2.** Hai spec ấy có tạo chữ ký Ed25519 không prehash giống nhau trên cùng key/message không?  
**Đáp án:** Không. Chế độ tương ứng là Ed25519 thuần và Ed25519ctx rỗng, khác domain separation.

**Câu 3.** Với Ed448 không prehash, absent và empty có tạo khác chữ ký không?  
**Đáp án:** Không khi các yếu tố khác giữ nguyên: RFC Ed448 dùng context hiệu dụng rỗng cho cả hai. Trạng thái Optional vẫn khác.

**Câu 4.** Ed25519ctx với context rỗng được Java API cho phép không? Có nên dùng trong giao thức mới?  
**Đáp án:** Java cho phép; RFC 8032 nói context Ed25519ctx **SHOULD NOT rỗng**, nên không chọn làm cấu hình mới nếu không có yêu cầu tương thích đặc biệt.

**Câu 5.** `new EdDSAParameterSpec(true)` khác `new EdDSAParameterSpec(false)` chỗ nào?  
**Đáp án:** Cờ prehash; nó chọn Ed25519ph/Ed448ph thay vì mode không prehash, không chỉ thay đổi trạng thái context.

**Câu 6.** Tại sao `new EdDSAParameterSpec(false, (byte[]) null)` ném lỗi?  
**Đáp án:** Constructor hai tham số không cho phép `null`; “không context” phải được tạo bằng constructor một tham số.

**Câu 7.** Nếu context có 255 byte, constructor có chấp nhận không? Nếu 256 byte?  
**Đáp án:** 255 được chấp nhận, 256 ném `InvalidParameterException`.

**Câu 8.** Nếu sửa `contextInput[0]` sau khi tạo spec, context đã gắn có đổi không?  
**Đáp án:** Không, vì constructor sao chép mảng. Mảng trả từ `getContext()` cũng là bản sao.

**Câu 9.** Vì sao `"invoices:v1"` và `"contracts:v1"` không xác minh chéo được?  
**Đáp án:** Context bytes khác nhau, làm thay đổi domain separation. Bên ký và bên xác minh phải dùng **đúng cùng bytes**.

**Câu 10.** `Signature.getInstance("Ed25519")` không gọi `setParameter` có giống `new EdDSAParameterSpec(false)` trong chương trình kiểm thử không?  
**Đáp án:** Có, `defaultEqualsAbsent=true` trên provider tích hợp được kiểm thử. Khi interop với provider khác, xác nhận profile thuật toán cụ thể.

**Câu 11.** Để giữ absent trong một bản config, có thể luôn gọi `getContext().orElse(new byte[0])` rồi dựng constructor hai tham số không?  
**Đáp án:** Không nếu cần giữ đúng Ed25519 thuần; thao tác ấy biến absent thành present-empty và đổi mode.

**Câu 12.** Context nên lấy từ dữ liệu ngẫu nhiên mỗi lần ký hay nhãn hằng của giao thức?  
**Đáp án:** RFC 8032 khuyến nghị **nhãn hằng theo protocol**, không gắn thành phần biến thiên của message và không bật context tùy hứng.

## 13. Checklist triển khai và kiểm thử liên thông

- [ ] Đã chỉ rõ **Ed25519 hay Ed448**, không dựa vào duy nhất tên chung EdDSA khi protocol yêu cầu mode cụ thể.
- [ ] Đã ghi rõ `prehash`: `false` hay `true`, tránh mặc định không công bố.
- [ ] Đã ghi rõ `contextPresent`: absent hay present, **không** đánh đồng absent và present-empty.
- [ ] Với Ed25519 thuần, dùng context **absent**, không thay bằng mảng rỗng.
- [ ] Với Ed25519ctx, dùng context **không rỗng** theo khuyến nghị RFC 8032, nếu protocol cho phép.
- [ ] Với Ed448, hiểu absent và empty có cùng context hiệu dụng khi không có prehash, nhưng vẫn quản lý metadata chính xác.
- [ ] Context được quy định dạng **byte string**, encoding/canonicalization/độ dài 255 byte rõ ràng.
- [ ] Bên ký và verifier dùng cùng key algorithm, mode prehash, context bytes và message canonicalization.
- [ ] `Signature.setParameter` được gọi rõ ràng trước khi truyền message vào `update`.
- [ ] Test âm tính có mismatch absent/empty (Ed25519), context khác nhau, message bị sửa và public key sai.
- [ ] Test dương tính có Ed448 absent/empty tương đương và Ed25519ph absent/empty tương đương theo RFC.
- [ ] Lỗi API được phân biệt: `NullPointerException` cho context null, `InvalidParameterException` cho context trên 255 byte, lỗi key/provider riêng.
- [ ] Không tự nối context vào message hoặc tự prehash nếu protocol không quy định cách đó.
- [ ] Không ghi khóa bí mật, byte chữ ký nhạy cảm hoặc raw context chứa dữ liệu cá nhân vào log không kiểm soát.
- [ ] Không thay chữ ký số, xác minh key identity và authorization bằng việc “có context”.
- [ ] Kiểm tra cross-provider/cross-language với test vectors từ protocol đích nếu hệ thống thực sự liên thông.

## 14. Tài liệu chính thức và tiêu chuẩn còn áp dụng

1. [Java SE 25 — `EdDSAParameterSpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): hai constructor, ngữ nghĩa context null vs empty, `getContext()`, defensive copy, giới hạn 255 byte, `Since: 15`.
2. [Java SE 15 — `EdDSAParameterSpec`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): đối chiếu API gốc xuất hiện trong Java 15.
3. [Java SE 25 — `Signature.setParameter(AlgorithmParameterSpec)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): cách cấu hình tham số chữ ký trong JCA.
4. [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): `5.1` Ed25519/Ed25519ctx/Ed25519ph với `dom2`, `5.2` Ed448/Ed448ph với `dom4`, `8.3` khuyến nghị context cố định theo giao thức.
5. [Oracle JDK 26 Migration Guide — Security Updates](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html): hỗ trợ EdDSA đã có từ JDK 15 (JEP 339), tiếp tục có trong JDK hiện hành.
6. [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): đặc tả bổ sung EdDSA vào Java 15.
