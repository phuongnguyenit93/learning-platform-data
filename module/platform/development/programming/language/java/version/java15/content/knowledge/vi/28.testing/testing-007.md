# Kiểm thử EdDSA bằng vector chuẩn, sai khóa, sai context và chữ ký hỏng

**Ngữ cảnh:** Java 15 → Kiểm thử. Nội dung sử dụng các API EdDSA thuộc Java SE từ JDK 15, ví dụ viết cho **Java 17+** để tận dụng `HexFormat` và `record`. Các thuật toán, API, chuẩn RFC và nguyên tắc kiểm thử trình bày ở đây vẫn phù hợp cho ứng dụng hiện nay.

## 1. Mục tiêu của bài

Sau khi hoàn thành, bạn có thể:

- Dùng **test vector độc lập của RFC 8032** để xác minh kết quả ký và xác minh EdDSA trên một JDK thực tế.
- Phân biệt **Ed25519, Ed25519ctx, Ed25519ph, Ed448**; đặc biệt hiểu **context** và chế độ **prehash** là một phần của phép ký/xác minh, không phải nhãn trang trí.
- Kiểm thử các ca âm quan trọng: **sai khóa công khai, sai thông điệp, sai context, thiếu context, chữ ký bị thay đổi/cắt ngắn, sai chế độ prehash**.
- Phân biệt `Signature.verify(...) == false` với `SignatureException` khi dữ liệu chữ ký sai định dạng; trong cả hai tình huống, hệ thống **không được chấp nhận chữ ký**.
- Tạo bộ test có khả năng chạy lại trong CI/container trên đúng JDK/provider được triển khai.

**Phạm vi:** Kiểm thử chữ ký số bằng Java Cryptography Architecture (JCA), không tự triển khai toán học đường cong elliptic, không dùng private key vector vào production. Không nhầm EdDSA dùng để **ký** với X25519/X448 dùng cho **thỏa thuận khóa**.

## 2. Hiểu các chế độ EdDSA trước khi viết test

EdDSA là họ thuật toán chữ ký số trên đường cong Edwards. RFC 8032 định nghĩa các chế độ dùng Ed25519/Ed448. Trong Java, sử dụng `Signature` cùng `KeyFactory`, `EdECPrivateKeySpec` và `EdDSAParameterSpec`.

| Chế độ RFC 8032 | Thuật toán trong `Signature.getInstance` | Cấu hình `EdDSAParameterSpec` | Ý nghĩa trong test |
| --- | --- | --- | --- |
| **Ed25519** (pure) | `Ed25519` | Không đặt tham số | Chữ ký gắn với đúng byte của thông điệp và cặp khóa. |
| **Ed25519ctx** | `Ed25519` | `new EdDSAParameterSpec(false, contextBytes)` | Context có mặt; signer/verifier phải dùng **cùng dãy byte context**. |
| **Ed25519ph** | `Ed25519` | `new EdDSAParameterSpec(true)` | Provider thực hiện quy trình prehash theo RFC 8032. |
| **Ed448** | `Ed448` | Mặc định hoặc `new EdDSAParameterSpec(false, contextBytes)` | Ed448 cho phép context tùy chọn; chữ ký dài hơn Ed25519. |
| **Ed448ph** | `Ed448` | `new EdDSAParameterSpec(true, contextBytes)` khi có context | Chế độ prehash Ed448; phải thống nhất cả cờ prehash và context. |

**Các tính chất cần nhớ:**

- **Ed25519** và **Ed25519ctx** khác chế độ về mặt mật mã. Không thể ký theo Ed25519ctx rồi xác minh như Ed25519 pure. Tên Java `Ed25519` vẫn được dùng, nhưng có thêm `EdDSAParameterSpec` khi cần context.
- Context là **byte array**, không phải tên biến hay nhãn ngoài protocol. Trong RFC 8032, context dài tối đa **255 octet (byte)**. Ví dụ `"foo"` ở UTF-8 có byte hex `66 6f 6f`. Trong ví dụ vector, dùng hex để tránh lỗi charset.
- Với **Ed25519ph**, đưa **thông điệp gốc** cho `Signature.update(...)` và đặt `prehash=true`. Đừng tự `SHA-512` thông điệp rồi lại bật prehash: như vậy sẽ thử một phép toán khác.
- **Ed25519** có seed/public key 32 byte, chữ ký 64 byte. **Ed448** có seed/public key 57 byte, chữ ký 114 byte. Đây là độ dài biểu diễn raw của **RFC 8032**; tệp khóa PKCS#8 hay public key X.509/SPKI dài hơn do có metadata.
- Với dữ liệu, khóa, context và chế độ cố định, EdDSA theo RFC 8032 cho chữ ký có thể so sánh **chính xác từng byte** với vector. Không cần tự cấp nonce ngẫu nhiên cho mỗi chữ ký như một số cách dùng ECDSA khác.

**Không lẫn việc xác thực định dạng với tính hợp lệ mật mã:** cùng một chữ ký có thể sai vì key, message, context, prehash mode hoặc byte chữ ký. Bộ test tốt phải thay đổi **một điều kiện tại một thời điểm**.

## 3. Vector chuẩn cần lấy từ đâu?

Sử dụng **[RFC 8032, Section 7: Test Vectors](https://www.rfc-editor.org/rfc/rfc8032.html#section-7)**. Các giá trị trong RFC ở dạng **hex của byte thực**, không phải text chứa ký tự hex.

| Ca dương tính | Mục trong RFC | Thông điệp | Context | Kiểm tra kỳ vọng |
| --- | --- | --- | --- | --- |
| Ed25519 TEST 1 | `7.1` | Rỗng, độ dài 0 byte | Không có | Chữ ký 64 byte **bằng chính xác** vector RFC, verify `true`. |
| Ed25519 TEST 2 | `7.1` | 1 byte `72` | Không có | Chữ ký khớp vector thứ hai, verify `true`. |
| Ed25519ctx “foo” | `7.2` | 16 byte `f726...76a8` | `666f6f`, tức “foo” | Ký với context “foo” khớp vector, verify cùng context `true`. |
| Ed25519ph “abc” | `7.3` | 3 byte `616263` | Không có | `prehash=true` cho chữ ký khớp vector, verify `true`. |
| Ed448 “Blank” | `7.4` | Rỗng | Không đặt context | Chữ ký 114 byte khớp vector, verify `true`. |

Ví dụ Ed25519 TEST 1 theo RFC:

```text
Seed (32 bytes):
9d61b19deffd5a60ba844af492ec2cc4
4449c5697b326919703bac031cae7f60

Public key raw (32 bytes):
d75a980182b10ab7d54bfed3c964073a
0ee172f3daa62325af021a68f707511a

Message: <empty, 0 bytes>

Signature (64 bytes):
e5564300c360ac729086e2cc806e828a
84877f1eb8e5d974d873e06522490155
5fb8821590a33bacc61e39701cf9b46b
d25bf5f0595bbe24655141438e7a100b
```

**Điểm quan trọng:** vector đã cung cấp **seed khóa bí mật**, **public key**, **message**, **signature** mong đợi; đây là nguồn tham chiếu độc lập. Chỉ kiểm tra `verify(sign(message))` bằng hai lời gọi của cùng một implementation **không đủ** chứng minh implementation tương thích chuẩn: hai thao tác có thể cùng sai mà vẫn chấp nhận nhau. Vì vậy bài kiểm tra bên dưới kết hợp **so sánh chữ ký với RFC** và **verify bằng chính chữ ký RFC**.

## 4. Ma trận kiểm thử âm tính

Mọi ca âm đều bắt đầu từ một vector hợp lệ rồi thay **đúng biến cần thử**, không thay tất cả cùng lúc.

| Ca âm | Thay đổi so với vector hợp lệ | Kết quả chấp nhận được | Chứng minh |
| --- | --- | --- | --- |
| **Sai public key** | Verify chữ ký TEST 1 bằng public key của TEST 2 | `false` | Chữ ký không thể xác thực bằng khóa khác. |
| **Sai message** | Với TEST 2, đổi byte message `72` thành `73` | `false` | Chữ ký ràng buộc dữ liệu đã ký. |
| **Sai context** | Ed25519ctx “foo”: verify với context “bar” (`626172`) | `false` | Context là thành phần của scheme/domain separation. |
| **Thiếu context** | Chữ ký Ed25519ctx nhưng verify không đặt context | `false` | Không được nhầm Ed25519ctx với Ed25519 pure. |
| **Chữ ký bị sửa một byte** | Đảo một bit trong chữ ký Ed25519 TEST 1 | `false` hoặc `SignatureException` do encoding hỏng | Chữ ký bị thay đổi bị từ chối. |
| **Chữ ký bị cắt ngắn** | Giữ 63/64 byte của chữ ký Ed25519 | `false` hoặc `SignatureException` | Chữ ký có độ dài/encoding sai không được chấp nhận. |
| **Sai prehash mode** | Ed25519ph “abc”: verify như Ed25519 pure | `false` | Hai chế độ ký không hoán đổi cho nhau. |

Trong chương trình test, **PASS** ở ca âm có nghĩa là **đã từ chối chữ ký sai thành công**; không có nghĩa là API trả về `true`.

## 5. Một chương trình Java 17+ chạy được đầy đủ

Tạo tệp tên chính xác **`EdDsaVectorTest.java`**. Chương trình dùng thư viện chuẩn `java.base`; không cần thêm JAR bên ngoài.

```java
import java.security.*;
import java.security.spec.*;
import java.util.*;

public class EdDsaVectorTest {
    static final HexFormat H = HexFormat.of();

    record V(String name, String alg, String seed, String pub,
             String msg, String sig, boolean ph, String ctx) {}

    static byte[] b(String hex) {
        return H.parseHex(hex);
    }

    static PublicKey publicKey(V v) throws GeneralSecurityException {
        String prefix = v.alg.equals("Ed25519")
                ? "302a300506032b6570032100"
                : "3043300506032b6571033a00";
        return KeyFactory.getInstance(v.alg).generatePublic(
                new X509EncodedKeySpec(b(prefix + v.pub)));
    }

    static PrivateKey privateKey(V v) throws GeneralSecurityException {
        NamedParameterSpec params = v.alg.equals("Ed25519")
                ? NamedParameterSpec.ED25519 : NamedParameterSpec.ED448;
        return KeyFactory.getInstance(v.alg).generatePrivate(
                new EdECPrivateKeySpec(params, b(v.seed)));
    }

    static Signature initEngine(String alg, boolean ph, byte[] ctx)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance(alg);
        if (ph || ctx != null) {
            s.setParameter(ctx != null
                    ? new EdDSAParameterSpec(ph, ctx)
                    : new EdDSAParameterSpec(true));
        }
        return s;
    }

    static boolean verify(V v, PublicKey pub, byte[] msg, byte[] sig,
                          boolean ph, byte[] ctx)
            throws GeneralSecurityException {
        Signature s = initEngine(v.alg, ph, ctx);
        s.initVerify(pub);
        s.update(msg);
        return s.verify(sig);
    }

    static void ok(String name, boolean pass) {
        if (!pass) throw new AssertionError(name);
        System.out.println(name + ": PASS");
    }

    static void positive(V v) throws GeneralSecurityException {
        Signature s = initEngine(v.alg, v.ph,
                v.ctx == null ? null : b(v.ctx));
        s.initSign(privateKey(v));
        s.update(b(v.msg));
        ok(v.name + " sign", Arrays.equals(s.sign(), b(v.sig)));
        ok(v.name + " verify",
                verify(v, publicKey(v), b(v.msg), b(v.sig), v.ph,
                        v.ctx == null ? null : b(v.ctx)));
    }

    static void negative(String label, V v, PublicKey pub, byte[] msg,
                         byte[] sig, boolean ph, byte[] ctx)
            throws GeneralSecurityException {
        boolean accepted = false;
        try {
            accepted = verify(v, pub, msg, sig, ph, ctx);
        } catch (SignatureException malformed) {
            // Malformed encoding may raise SignatureException instead of false.
        }
        ok(label, !accepted);
    }

    public static void main(String[] args) throws Exception {
        V empty = new V("RFC Ed25519 #1", "Ed25519",
                "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
                "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
                "",
                "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
              + "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
                false, null);

        V one = new V("RFC Ed25519 #2", "Ed25519",
                "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
                "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
                "72",
                "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
              + "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
                false, null);

        V ctx = new V("RFC Ed25519ctx foo", "Ed25519",
                "0305334e381af78f141cb666f6199f57bc3495335a256a95bd2a55bf546663f6",
                "dfc9425e4f968f7f0c29f0259cf5f9aed6851c2bb4ad8bfb860cfee0ab248292",
                "f726936d19c800494e3fdaff20b276a8",
                "55a4cc2f70a54e04288c5f4cd1e45a7bb520b36292911876cada7323198dd87a"
              + "8b36950b95130022907a7fb7c4e9b2d5f6cca685a587b4b21f4b888e4e7edb0d",
                false, "666f6f");

        V ph = new V("RFC Ed25519ph abc", "Ed25519",
                "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
                "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
                "616263",
                "98a70222f0b8121aa9d30f813d683f809e462b469c7ff87639499bb94e6dae41"
              + "31f85042463c2a355a2003d062adf5aaa10b8c61e636062aaad11c2a26083406",
                true, null);

        V ed448 = new V("RFC Ed448 blank", "Ed448",
                "6c82a562cb808d10d632be89c8513ebf6c929f34ddfa8c9f63c9960ef6e348a3"
              + "528c8a3fcc2f044e39a3fc5b94492f8f032e7549a20098f95b",
                "5fd7449b59b461fd2ce787ec616ad46a1da1342485a70e1f8a0ea75d80e96778"
              + "edf124769b46c7061bd6783df1e50f6cd1fa1abeafe8256180",
                "",
                "533a37f6bbe457251f023c0d88f976ae2dfb504a843e34d2074fd823d41a591f"
              + "2b233f034f628281f2fd7a22ddd47d7828c59bd0a21bfd3980ff0d2028d4b18a"
              + "9df63e006c5d1c2d345b925d8dc00b4104852db99ac5c7cdda8530a113a0f4db"
              + "b61149f05a7363268c71d95808ff2e652600",
                false, null);

        for (V v : new V[] {empty, one, ctx, ph, ed448}) {
            positive(v);
        }

        negative("Wrong public key", empty, publicKey(one),
                b(empty.msg), b(empty.sig), false, null);
        negative("Wrong message", one, publicKey(one),
                b("73"), b(one.sig), false, null);
        negative("Wrong context", ctx, publicKey(ctx),
                b(ctx.msg), b(ctx.sig), false, b("626172"));
        negative("Missing context", ctx, publicKey(ctx),
                b(ctx.msg), b(ctx.sig), false, null);

        byte[] damaged = b(empty.sig).clone();
        damaged[10] ^= 1;
        negative("Damaged signature", empty, publicKey(empty),
                b(empty.msg), damaged, false, null);
        negative("Truncated signature", empty, publicKey(empty),
                b(empty.msg), Arrays.copyOf(b(empty.sig), 63), false, null);

        negative("Wrong prehash mode", ph, publicKey(ph),
                b(ph.msg), b(ph.sig), false, null);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 EdDsaVectorTest.java
java EdDsaVectorTest
```

**Stdout kỳ vọng khi runtime/provider hỗ trợ đầy đủ các mode được dùng:**

```text
RFC Ed25519 #1 sign: PASS
RFC Ed25519 #1 verify: PASS
RFC Ed25519 #2 sign: PASS
RFC Ed25519 #2 verify: PASS
RFC Ed25519ctx foo sign: PASS
RFC Ed25519ctx foo verify: PASS
RFC Ed25519ph abc sign: PASS
RFC Ed25519ph abc verify: PASS
RFC Ed448 blank sign: PASS
RFC Ed448 blank verify: PASS
Wrong public key: PASS
Wrong message: PASS
Wrong context: PASS
Missing context: PASS
Damaged signature: PASS
Truncated signature: PASS
Wrong prehash mode: PASS
```

Nếu một dòng `ok(...)` nhận `false`, chương trình ném `AssertionError` và quá trình Java thoát với mã lỗi. Vì vậy có thể chạy trong CI: **toàn bộ 17 dòng PASS** là dấu hiệu bộ test đã đi qua đầy đủ; lỗi chưa được xử lý sẽ khiến job thất bại.

### Vì sao chương trình chuyển đổi khóa như vậy?

RFC 8032 biểu diễn private key trong vector dưới dạng **seed raw** dài 32 hoặc 57 byte. `EdECPrivateKeySpec` nhận seed cùng `NamedParameterSpec.ED25519` hoặc `ED448` để tạo `PrivateKey` theo JCA.

RFC 8032 biểu diễn public key dưới dạng **điểm Edwards đã nén (raw)**. `X509EncodedKeySpec` của JCA đòi public key trong cấu trúc **SubjectPublicKeyInfo (SPKI, DER)**. Hai tiền tố hex:

- Ed25519: `302a300506032b6570032100`.
- Ed448: `3043300506032b6571033a00`.

được ghép với **raw public-key bytes** để tạo SPKI tương thích với kiểu khóa mô tả trong **RFC 8410**. Chương trình dùng hai tiền tố chỉ để đóng gói **test vector có thuật toán đã biết**; không coi việc ghép tùy tiện là cách validate khóa đầu vào chưa tin cậy. Trong production, dùng khóa X.509/SPKI, PKCS#8, `KeyStore` hoặc cơ chế quản lý khóa đã được thiết kế phù hợp; không nhúng seed ví dụ vào ứng dụng.

### Vì sao gọi `setParameter` trước `initSign`/`initVerify`?

Hàm `initEngine` tạo một đối tượng `Signature` mới và đặt `EdDSAParameterSpec` theo vector **trước** khi cấp khóa. Điều này làm rõ chế độ đã chọn:

- `ph=false, ctx=null` → pure Ed25519 hoặc Ed448 theo tên thuật toán.
- `ph=false, ctx=666f6f` → Ed25519ctx, domain “foo”.
- `ph=true, ctx=null` → Ed25519ph; provider prehash message theo RFC.
- Khi verifier dùng context khác, digest nội bộ/đầu vào miền khác nên signature hợp lệ với “foo” **không hợp lệ** với “bar”.

Lưu ý: một số provider có chính sách hỗ trợ thuật toán/mode khác nhau. Nếu `getInstance`, `setParameter` hoặc `initSign` thất bại vì runtime không hỗ trợ, đó là **lỗi tương thích cần giải quyết**, không thể chuyển thành `PASS` bằng cách bỏ qua test.

## 6. Cách đọc kết quả và xử lý ngoại lệ

Trong JCA, đường xác minh thường là:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Đoạn trên là **mã minh họa**, cần có biến `publicKey`, `messageBytes`, `signatureBytes` thích hợp. Với Ed25519ctx/ph, phải đặt `EdDSAParameterSpec` trước khi verify, giống signer.

**Quy tắc fail-closed:**

- `verify(...)` trả về `true` → chữ ký hợp lệ **theo khóa, message, mode và context được cung cấp cho verifier**. Chưa tự động chứng minh người ký được phép thực hiện nghiệp vụ; ứng dụng còn phải kiểm tra quyền, danh tính, chính sách và nội dung đã ký.
- `verify(...)` trả về `false` → chữ ký không hợp lệ; **từ chối**.
- `SignatureException` khi nhận signature sai định dạng/độ dài hoặc lỗi verify → **từ chối**; với hệ thống thật cần ghi nhận và phân loại nguyên nhân.
- `InvalidKeyException`, `InvalidAlgorithmParameterException`, `NoSuchAlgorithmException` hoặc lỗi provider khi khởi tạo → **lỗi cấu hình/khả năng thực thi**, không được biến thành một test âm `PASS` rồi bỏ qua.
- `IllegalArgumentException` khi `HexFormat.parseHex` đọc chuỗi hex sai độ dài/ký tự → **lỗi fixture/test data**; sửa vector hoặc cách parse, không diễn giải là chữ ký đã bị từ chối bởi mật mã.

Trong `negative(...)`, chương trình chỉ cho phép `SignatureException` đại diện cho việc từ chối chữ ký sai định dạng. Các exception khởi tạo, parse key/fixture hoặc thiếu thuật toán vẫn nổi lên để làm **toàn bộ test thất bại**, giúp phân biệt negative case hợp lệ với môi trường bị lỗi.

### Cần kiểm tra độ dài và định dạng ở đâu?

- Chữ ký raw Ed25519/Ed25519ctx/Ed25519ph: **64 byte**. Ed448/Ed448ph: **114 byte**. Thêm ca chữ ký thừa byte, cắt ngắn và thay đổi `R`/`S`.
- Raw public key Ed25519: **32 byte**, Ed448: **57 byte**. Kiểm thử dữ liệu không hợp lệ ở bước tạo `PublicKey`; `InvalidKeySpecException` không phải kết quả `verify`.
- Context phải được truyền **đúng byte** và đúng mode. Các chuỗi nhìn giống nhau nhưng khác charset/normalization có thể tạo byte khác nhau. Hãy thống nhất mã hóa, chẳng hạn UTF-8 cho context xuất phát từ text.
- Bản thân `Signature` là đối tượng **có trạng thái**. Tạo instance mới cho từng thao tác kiểm thử; không chia sẻ nó qua các luồng mà không quản lý trạng thái.

## 7. Những lỗi kiểm thử EdDSA dễ mắc

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Chỉ test `sign` rồi `verify` bằng cùng provider | Hai đường đi có thể cùng lỗi nhưng vẫn khớp | So byte signature với vector RFC **và** verify chữ ký RFC. |
| Đọc chuỗi hex của RFC bằng `getBytes()` | Message/key/signature bị đổi thành byte ký tự ASCII | Dùng `HexFormat.parseHex(...)`. |
| Dùng raw public key như `X509EncodedKeySpec` trực tiếp | KeyFactory nhận dữ liệu sai cấu trúc | Dùng SPKI DER phù hợp hoặc `EdECPublicKeySpec`. |
| Quên `EdDSAParameterSpec` khi verify Ed25519ctx | Chuyển nhầm sang Ed25519 pure | Signer/verifier đặt cùng context và prehash mode. |
| Tự hash message khi đã bật `prehash=true` | Không khớp Ed25519ph/Ed448ph chuẩn | Đưa message gốc cho `update`. |
| Chỉ đổi signature nhưng cũng đổi message và key | Ca âm mơ hồ, khó biết ràng buộc nào được kiểm thử | Mỗi ca âm thay một tham số. |
| Coi exception bất kỳ là “rejected = PASS” | Che mất lỗi cấu hình, key spec và provider | Chỉ xử lý `SignatureException` có lý do phù hợp; lỗi khác làm test thất bại. |
| Dùng sai public key **không hợp lệ về encoding** | Test dừng ở bước parse key | Dùng một public key **hợp lệ nhưng khác** từ vector độc lập. |
| Dùng seed/vector RFC ở production | Tiết lộ khóa và mọi người biết private key | Vector chỉ là dữ liệu test công khai; production sinh/lưu khóa riêng. |
| Nghĩ verify `true` là đủ để ủy quyền | Cho phép signature hợp lệ trên nội dung/ứng dụng không đúng | Ràng buộc protocol, payload, danh tính và quyền ở tầng nghiệp vụ. |

**Đặc biệt với context:** Context là công cụ domain separation khi hệ thống thiết kế nhất quán. Nó không thay thế việc ký đầy đủ thông điệp có định dạng xác định, không thay thế kiểm tra danh tính/quyền, và không tự chống phát lại. Nếu một giao thức cần chống replay, hãy đưa nonce/timestamp/sequence hoặc thông tin miền giao thức thích hợp **vào payload được ký** và xác minh chúng ở phía nhận.

## 8. Đưa bài kiểm thử vào CI và kiểm tra tương thích JDK

1. Giữ các **RFC vectors bất biến** trong test source hoặc test resources; không cập nhật expected signature theo output của implementation đang test.
2. Chạy `javac --release 17` bằng JDK hỗ trợ mức phát hành đó, rồi chạy bằng các **JDK/vendor/container image** mà ứng dụng tuyên bố hỗ trợ.
3. Yêu cầu tất cả **positive vectors** PASS cả so sánh chữ ký và xác minh; yêu cầu tất cả **negative cases** từ chối theo quy tắc fail-closed.
4. Với provider bổ sung/HSM, kiểm tra hỗ trợ `Ed25519`, `Ed448`, context và prehash riêng biệt. Không mặc định “hỗ trợ Ed25519” nghĩa là có đủ mọi biến thể RFC 8032.
5. Khi kết quả khác nhau giữa môi trường, ghi nhận `java -version`, tên provider từ `Signature.getInstance(...).getProvider().getName()` ở thời điểm thích hợp và lỗi cụ thể. Với provider chọn trễ, không nên ép gọi `getProvider` trước khi gắn key/chọn chế độ chỉ để log.
6. Không log private key, seed, token HSM, payload nhạy cảm hoặc chữ ký thực tế từ production. Test vectors công khai của RFC có thể ghi trong fixture, nhưng chúng không đại diện khóa thật.
7. Khi đổi JDK, crypto provider, security policy hoặc hình thức phân phối khóa, chạy lại matrix này. Nếu ứng dụng có yêu cầu chứng nhận/tuân thủ, kiểm tra cấu hình provider/thuật toán theo yêu cầu riêng của môi trường.

Ví dụ cách trình bày kết quả theo nhóm:

| Nhóm kiểm thử | Điều kiện chấp nhận |
| --- | --- |
| **Reference conformance** | 5 vector RFC: ký ra đúng chữ ký mẫu và xác minh mẫu thành công. |
| **Binding to key/message** | Sai public key hoặc message luôn bị từ chối. |
| **Domain separation** | Sai hoặc thiếu Ed25519ctx context bị từ chối. |
| **Signature integrity** | Một bit bị sửa hoặc chữ ký cắt ngắn bị từ chối. |
| **Mode separation** | Chữ ký Ed25519ph không được xác minh như Ed25519 pure. |
| **Runtime compatibility** | Các engine, chế độ và key factory thật hoạt động trên môi trường hỗ trợ được công bố. |

## 9. Bài tập mở rộng

1. Thêm ca **Ed25519ctx “bar”** độc lập từ RFC 8032 `7.2. Kiểm tra chữ ký “foo” và “bar” khác nhau dù seed/message giống nhau; cả hai chỉ verify với đúng context.
2. Thêm test **Ed448 có context** và **Ed448ph** bằng vector tương ứng của RFC, phân biệt context rỗng, không có context và context cụ thể theo semantics của API.
3. Thử ký message bằng nhiều lời gọi `Signature.update(...)` theo từng đoạn, so chữ ký với khi gọi một lần toàn bộ message; chứng minh cách chia chunk không đổi các byte đã ký.
4. Bổ sung signature length **thừa một byte**, signature toàn byte 0 hoặc public-key encoding hỏng. Chỉ rõ ca nào thất bại ngay ở bước parse và ca nào thất bại ở `verify`.
5. Lập matrix chạy trên hai bản phân phối JDK khác nhau và giải thích vì sao thuật toán có thể được cung cấp bởi provider khác, nhưng **vector chuẩn phải giữ nguyên**.

## Tài liệu chính thức để đối chiếu

- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032.html), đặc biệt `7.1` (Ed25519), `7.2` (Ed25519ctx), `7.3` (Ed25519ph), `7.4` (Ed448), `7.5` (Ed448ph).
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339) — EdDSA trong Java SE.
- [EdDSAParameterSpec API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html) — tham số context và prehash.
- [EdECPrivateKeySpec API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html) — sinh đối tượng khóa bí mật từ seed.
- [Signature API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html) — `initSign`, `initVerify`, `update`, `sign`, `verify`.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, and X448](https://www.rfc-editor.org/rfc/rfc8410.html) — định dạng mã hóa khóa theo X.509/PKCS#8.

**Tiêu chí hoàn thành:** bộ test chứng minh bằng vector độc lập rằng thuật toán ký/xác minh khớp RFC; kiểm chứng mọi sai lệch **key, message, context, prehash, signature bytes/length** đều bị từ chối; và chạy lại ổn định trên Java runtime thực tế.
