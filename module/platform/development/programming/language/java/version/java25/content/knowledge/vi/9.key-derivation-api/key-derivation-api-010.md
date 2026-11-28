# Kiểm thử bằng vector chuẩn và xác minh khả năng tương tác giữa các thành phần

> **Chương:** API dẫn xuất khóa
>
> **Phiên bản:** Java 25 — **JEP 510: Key Derivation Function API** là API chính thức, không cần bật preview. Bài thực hành dùng HKDF-SHA256 theo RFC 5869, kiểm tra PRK và OKM bằng vector chuẩn, sau đó đối chiếu đầu ra với một thành phần độc lập và dùng khóa đã dẫn xuất ở tầng mã hóa.

## 1. Bài toán: hai thành phần phải tạo đúng cùng một khóa

Một hệ thống có hai thành phần cần sử dụng cùng khóa phiên:

- **Producer** nhận shared secret từ một quy trình key agreement đã xác thực, cùng salt và thông tin ngữ cảnh của giao thức.
- **Consumer** có cùng đầu vào theo hợp đồng giao thức và tự dẫn xuất khóa để giải mã dữ liệu.

Nếu hai bên chỉ thống nhất “dùng HKDF-SHA256” nhưng khác một byte của IKM, salt, info, thứ tự ghép dữ liệu hoặc độ dài đầu ra, khóa tạo ra sẽ khác hoàn toàn. Cả hai đoạn code có thể chạy thành công nhưng không thể trao đổi dữ liệu.

Vì vậy, kiểm thử KDF cần hai lớp bằng chứng:

1. **Đúng thuật toán:** đầu ra trùng vector chuẩn độc lập, ví dụ RFC 5869 Appendix A.
2. **Đúng hợp đồng liên tác:** các thành phần thống nhất byte đầu vào, thuật toán, độ dài và cách sử dụng khóa; ít nhất một phép thử end-to-end chứng minh dữ liệu do bên này tạo có thể được bên kia xác minh hoặc giải mã.

### Kết quả cần đạt

Sau bài này, bạn có thể:

- Dùng `javax.crypto.KDF` và `HKDFParameterSpec` của Java 25.
- Phân biệt `Extract`, `Expand` và `Extract-then-Expand`.
- Kiểm tra PRK và OKM với vector HKDF-SHA256 chuẩn.
- So sánh đầu ra Java với OpenSSL 3 hoặc một triển khai độc lập khác.
- Dùng `deriveKey` để nhận `SecretKey`; dùng `deriveData` trong test vector khi cần so sánh raw bytes.
- Thiết kế hợp đồng IKM/salt/info/L nhất quán giữa producer, consumer và hệ thống khác.
- Nhận diện sai lệch encoding, provider, key length, domain separation và các lỗi bảo mật thường gặp.

## 2. API KDF của Java 25 và phạm vi sử dụng

JEP 510 đưa API KDF thành tính năng chính thức trong Java 25. API cung cấp một giao diện chung để dẫn xuất khóa từ **input keying material (IKM)** và các tham số phụ thuộc thuật toán. Với Oracle JDK 25, SunJCE cung cấp các biến thể HKDF chuẩn:

| Tên thuật toán | HMAC hash | Độ dài HashLen |
| --- | --- | ---: |
| `HKDF-SHA256` | HMAC-SHA-256 | 32 byte |
| `HKDF-SHA384` | HMAC-SHA-384 | 48 byte |
| `HKDF-SHA512` | HMAC-SHA-512 | 64 byte |

Các tên trên được Java Security Standard Algorithm Names định nghĩa; HKDF tuân theo RFC 5869. Provider khác có thể hỗ trợ thêm thuật toán hoặc có phạm vi hỗ trợ riêng. Hãy kiểm tra JDK distribution và provider thực tế của môi trường triển khai.

### Hai API đầu ra

| API | Kết quả | Dùng khi |
| --- | --- | --- |
| `deriveKey(String alg, AlgorithmParameterSpec spec)` | Một `SecretKey` mang tên thuật toán đích, ví dụ `AES` | Mã ứng dụng chuẩn bị dùng khóa với `Cipher`, `Mac` hoặc API nhận `SecretKey`. |
| `deriveData(AlgorithmParameterSpec spec)` | Mảng byte raw của keying material | Kiểm thử vector chuẩn, so sánh với triển khai khác hoặc khi giao thức thật sự yêu cầu raw bytes. |

Trong production, ưu tiên `deriveKey` để giữ khóa dưới dạng `SecretKey` và tránh lấy raw bytes không cần thiết. `deriveData` có thể ném `UnsupportedOperationException` nếu provider giữ đầu ra ở dạng không thể export.

### Phân biệt hai loại tham số

- `HKDFParameterSpec` là `AlgorithmParameterSpec` mô tả **một phép dẫn xuất cụ thể**: IKM, salt, info, mode và độ dài.
- `KDFParameters` là tham số khởi tạo tùy chọn truyền vào một số overload của `KDF.getInstance(...)`; nó không thay thế `HKDFParameterSpec` ở lời gọi `deriveKey`/`deriveData`.

Không cần dùng `KDFParameters` cho ví dụ HKDF cơ bản trong bài.

## 3. Hiểu đúng Extract, Expand và Extract-then-Expand

HKDF gồm hai giai đoạn:

~~~text
                    Extract
          salt + IKM  ---------->  PRK
                                      |
                                      | info + L
                                      v
                                   Expand
                                      |
                                      v
                                     OKM
~~~

| Thành phần | Ý nghĩa | Quy tắc liên tác |
| --- | --- | --- |
| **IKM** | Input keying material, thường là shared secret từ key agreement hoặc material có entropy phù hợp | Hai bên phải dùng đúng cùng bytes và thứ tự ghép. |
| **salt** | Đầu vào không nhất thiết bí mật; giúp quá trình extract và các lần dùng khóa độc lập hơn | Nếu không cung cấp, RFC 5869 quy định salt mặc định là chuỗi 0 có độ dài HashLen. Giao thức nên xác định rõ có salt hay không. |
| **PRK** | Pseudorandom key do Extract tạo ra, có độ dài HashLen | Không dùng trực tiếp làm khóa cho mục đích tùy ý; thường đưa vào Expand. |
| **info** | Dữ liệu gắn đầu ra với ứng dụng/ngữ cảnh cụ thể | Dùng domain separation; hai bên phải thống nhất chính xác bytes. |
| **L** | Độ dài OKM, tính bằng **byte** | Phải giống nhau ở cả hai bên và phù hợp thuật toán đích. |
| **OKM** | Output keying material từ Expand | Có thể dùng làm khóa sau khi xác định đúng thuật toán và độ dài. |

### Chọn chế độ theo mục đích

| Chế độ | Java API | Kết quả |
| --- | --- | --- |
| Extract | `HKDFParameterSpec.ofExtract().addIKM(...).addSalt(...).extractOnly()` | PRK |
| Expand | `HKDFParameterSpec.expandOnly(prk, info, length)` | OKM từ một PRK đã có |
| Extract-then-Expand | `HKDFParameterSpec.ofExtract().addIKM(...).addSalt(...).thenExpand(info, length)` | OKM hoàn chỉnh |

Trong đa số luồng mới, dùng **Extract-then-Expand**. Tách hai giai đoạn khi giao thức yêu cầu lưu/chuyển PRK hoặc các thành phần được xử lý ở những thời điểm khác nhau. Không tự chia giai đoạn chỉ để code trông chi tiết hơn.

Với HKDF, giới hạn độ dài đầu ra là:

\[
L \leq 255 \times \mathrm{HashLen}
\]

Ví dụ HKDF-SHA256 có HashLen = 32 byte, nên giới hạn lý thuyết của OKM là 8.160 byte. Hệ thống thực tế thường chỉ dẫn xuất độ dài cần thiết cho khóa AES hoặc material đã được giao thức quy định; không lấy giới hạn tối đa làm khuyến nghị.

## 4. Cấu trúc API Java 25

Các kiểu quan trọng:

| Kiểu | Vai trò |
| --- | --- |
| `javax.crypto.KDF` | Chọn thuật toán và thực hiện dẫn xuất. |
| `javax.crypto.spec.HKDFParameterSpec` | Khai báo tham số HKDF. |
| `HKDFParameterSpec.Builder` | Ghép các phần IKM/salt và chọn `extractOnly()` hoặc `thenExpand(...)`. |
| `SecretKey` | Đại diện khóa đầu ra hoặc key material được provider quản lý. |
| `AlgorithmParameterSpec` | Kiểu tham số chung mà phương thức derive nhận. |

Ví dụ tối thiểu:

~~~java
import java.security.spec.AlgorithmParameterSpec;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

KDF hkdf = KDF.getInstance("HKDF-SHA256");

AlgorithmParameterSpec params = HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .thenExpand(info, 32);

SecretKey aesKey = hkdf.deriveKey("AES", params);
~~~

`32` ở ví dụ trên là 32 **byte**, tương ứng khóa AES-256. Tên `AES` chỉ định loại `SecretKey` trả về; độ dài thực tế vẫn do `HKDFParameterSpec` quyết định. Khi chọn độ dài khác với kích thước được thuật toán đích chấp nhận, thao tác sử dụng khóa có thể thất bại.

### Builder có thể nhận nhiều phần IKM và salt

Java 25 cho phép gọi `addIKM(...)` và `addSalt(...)` nhiều lần, với `byte[]` hoặc `SecretKey`. Các phần được đưa vào theo thứ tự gọi. Điều này hữu ích khi:

- IKM được ghép từ label, nonce hoặc nhiều thành phần đã định nghĩa trong protocol.
- Một phần key material nằm trong `SecretKey` không export được từ HSM/token.
- Ứng dụng muốn giữ key material trong provider thay vì gọi `getEncoded()` để lấy bytes.

Builder không thread-safe; hãy tạo builder riêng cho từng phép dẫn xuất.

## 5. Vector chuẩn RFC 5869 — Test Case 1 (SHA-256)

RFC 5869 Appendix A.1 cung cấp một vector độc lập để kiểm tra HKDF-SHA256.

**Đầu vào**

| Trường | Giá trị hex | Độ dài |
| --- | --- | ---: |
| Hash | SHA-256 | — |
| IKM | `0b` lặp 22 lần | 22 byte |
| Salt | `000102030405060708090a0b0c` | 13 byte |
| Info | `f0f1f2f3f4f5f6f7f8f9` | 10 byte |
| L | `42` | 42 byte |

**Đầu ra kỳ vọng**

PRK — kết quả Extract (32 byte):

~~~text
077709362c2e32df0ddc3f0dc47bba63
90b6c73bb50f9c3122ec844ad7c2b3e5
~~~

OKM — kết quả Expand (42 byte):

~~~text
3cb25f25faacd57a90434f64d0362f2a
2d2d0a90cf1a5a4c5db02d56ecc4c5bf
34007208d5b887185865
~~~

Test này kiểm tra được:

1. Đầu vào IKM/salt/info đã được chuyển thành đúng bytes.
2. Giai đoạn Extract tạo đúng PRK.
3. Giai đoạn Expand tạo đúng 42 byte OKM.
4. Java implementation tương thích với vector độc lập trong RFC.

Không dùng một output do chính implementation đang kiểm thử tạo ra làm expected value. Expected phải lấy từ đặc tả/vector chuẩn hoặc một implementation độc lập đã được xác minh.

## 6. Viết test Java 25 cho PRK và OKM

Ví dụ dưới đây dùng JUnit 5. Đây là **test vector công khai**, không phải secret production.

~~~java
// File: HkdfRfc5869Test.java
package com.example.crypto;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.HexFormat;
import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;
import org.junit.jupiter.api.Test;

class HkdfRfc5869Test {

    private static final HexFormat HEX = HexFormat.of();

    @Test
    void matchesRfc5869Sha256TestCase1() throws Exception {
        byte[] ikm = HEX.parseHex("0b".repeat(22));
        byte[] salt = HEX.parseHex("000102030405060708090a0b0c");
        byte[] info = HEX.parseHex("f0f1f2f3f4f5f6f7f8f9");

        byte[] expectedPrk = HEX.parseHex(
                "077709362c2e32df0ddc3f0dc47bba63" +
                "90b6c73bb50f9c3122ec844ad7c2b3e5");

        byte[] expectedOkm = HEX.parseHex(
                "3cb25f25faacd57a90434f64d0362f2a" +
                "2d2d0a90cf1a5a4c5db02d56ecc4c5bf" +
                "34007208d5b887185865");

        // Test riêng Extract để đối chiếu PRK.
        KDF extractKdf = KDF.getInstance("HKDF-SHA256");
        byte[] actualPrk = extractKdf.deriveData(
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .extractOnly());

        assertArrayEquals(expectedPrk, actualPrk);

        // Test Extract-then-Expand để đối chiếu OKM.
        KDF expandKdf = KDF.getInstance("HKDF-SHA256");
        byte[] actualOkm = expandKdf.deriveData(
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .thenExpand(info, 42));

        assertArrayEquals(expectedOkm, actualOkm);

        // Provider chỉ được truy vấn sau phép derive.
        assertNotNull(extractKdf.getProviderName());
        assertNotNull(expandKdf.getProviderName());
    }
}
~~~

### Vì sao test cả Extract và Extract-then-Expand?

- Test `extractOnly()` giúp khoanh vùng lỗi ở IKM/salt hoặc bước Extract.
- Test `thenExpand()` xác nhận đường dẫn thường dùng trong ứng dụng tạo đúng OKM.
- Nếu PRK đúng nhưng OKM sai, kiểm tra `info`, `L`, mode và bước Expand.
- Nếu PRK sai, kiểm tra byte đầu vào, thứ tự các phần IKM/salt, digest và provider.

`KDF` không được đảm bảo thread-safe nếu implementation không công bố điều ngược lại. Test trên dùng từng instance riêng cho từng phép dẫn xuất; không chia sẻ một instance cho nhiều test/thread chạy đồng thời.

## 7. Kiểm tra thêm vector rỗng salt/info

RFC 5869 Appendix A.3 kiểm tra trường hợp salt và info có độ dài bằng 0. Trường hợp này hữu ích để phát hiện khác biệt giữa:

- Không cung cấp salt và cung cấp salt rỗng.
- Không cung cấp info và cung cấp info rỗng.
- Chuỗi rỗng được mã hóa thành 0 byte hay nhầm thành hai ký tự `0x22`.

Với Java 25:

~~~java
byte[] ikm = HexFormat.of().parseHex("0b".repeat(22));
byte[] empty = new byte[0];

byte[] okm = KDF.getInstance("HKDF-SHA256").deriveData(
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(empty)
                .thenExpand(empty, 42));
~~~

Expected OKM của Test Case 3:

~~~text
8da4e775a563c18f715f802a063c5a31
b8a11f5c5ee1879ec3454e5f3c738d2d
9d201395faa4b61a96c8
~~~

Javadoc Java 25 quy định byte array rỗng được bỏ qua khi thêm IKM/salt; `info` rỗng tương ứng chuỗi byte rỗng. Hãy dùng `byte[0]` để thể hiện rõ trường hợp này trong test.

## 8. Kiểm tra liên tác với OpenSSL 3

Vector RFC không phụ thuộc Java. Có thể chạy cùng bộ input bằng OpenSSL 3 để xác nhận hai implementation độc lập cho cùng kết quả.

~~~bash
openssl version

openssl kdf -keylen 42 \
  -kdfopt digest:SHA256 \
  -kdfopt hexkey:0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b \
  -kdfopt hexsalt:000102030405060708090a0b0c \
  -kdfopt hexinfo:f0f1f2f3f4f5f6f7f8f9 \
  HKDF
~~~

OpenSSL CLI mặc định xuất kết quả dưới dạng hex text nếu không chỉ định `-binary`. Kết quả phải khớp chính xác 42 byte OKM ở mục 5:

~~~text
3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865
~~~

Đây là phép kiểm tra liên tác ở **mức thuật toán và encoding**. Nó chứng minh Java và OpenSSL cùng hiểu một bộ IKM/salt/info/L theo RFC 5869. Trong hệ thống thực, hãy lặp lại với protocol parameters thật trong môi trường test, không dùng khóa production để đưa vào command line hoặc shell history.

### Bảng đối chiếu khi hai bên cho kết quả khác

| Hạng mục | Java 25 | OpenSSL 3 | Cần thống nhất |
| --- | --- | --- | --- |
| KDF | `HKDF-SHA256` | `HKDF` với `digest:SHA256` | Cùng HMAC-SHA-256 |
| IKM | `addIKM(byte[])` | `hexkey:` | Cùng bytes, cùng thứ tự ghép |
| Salt | `addSalt(byte[])` | `hexsalt:` | Cùng bytes; xác định rõ trường hợp thiếu/rỗng |
| Info | `thenExpand(info, L)` | `hexinfo:` | Cùng bytes và cùng domain label |
| Mode | `thenExpand` | `EXTRACT_AND_EXPAND` mặc định | Cùng Extract rồi Expand |
| Độ dài | `L` trong `thenExpand` | `-keylen L` | Cùng số byte, không phải số ký tự hex |
| Output | `deriveData` | hex text hoặc `-binary` | So sánh raw bytes, không so chuỗi đã format khác nhau |

Nếu các byte đầu vào đã giống nhau mà kết quả vẫn khác, kiểm tra implementation/provider, phiên bản thư viện và mode của KDF. Không “sửa” bằng cách đổi salt hoặc info tùy tiện cho đến khi hai bên trùng; phải tìm nguyên nhân của sai lệch.

## 9. Xác minh deriveKey và thành phần tiêu thụ khóa

Vector test thường cần raw bytes để so sánh. Trong ứng dụng thật, nên lấy `SecretKey` trực tiếp:

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

static SecretKey deriveAesKey(
        byte[] sharedSecret,
        byte[] salt,
        String direction) throws Exception {

    byte[] info = (
            "com.example.checkout/v1/aes-256-gcm/" + direction)
            .getBytes(StandardCharsets.UTF_8);

    return KDF.getInstance("HKDF-SHA256").deriveKey(
            "AES",
            HKDFParameterSpec.ofExtract()
                    .addIKM(sharedSecret)
                    .addSalt(salt)
                    .thenExpand(info, 32));
}
~~~

Producer và consumer phải thống nhất:

- Cùng shared secret từ key agreement hoặc nguồn khóa được bảo vệ.
- Cùng salt bytes.
- Cùng `info`, gồm phiên bản protocol, mục đích và chiều truyền.
- Cùng HKDF hash và độ dài đầu ra.
- Cùng thuật toán sử dụng khóa, ví dụ AES-256-GCM.

Ví dụ, hai bên có thể dùng `direction = "client-to-server"` để dẫn xuất khóa cho một chiều; chiều ngược lại dùng label khác. Điều này tạo **domain separation**: cùng IKM/salt nhưng mục đích khác sẽ tạo khóa khác.

### Kiểm tra ở tầng Cipher

Một integration test có thể:

1. Thành phần A gọi `deriveAesKey(...)`, mã hóa plaintext bằng AES-GCM.
2. Thành phần B gọi cùng hợp đồng dẫn xuất độc lập, nhận `SecretKey` tương ứng.
3. B giải mã ciphertext bằng cùng nonce và AAD theo protocol.
4. Kiểm tra plaintext khôi phục giống hoàn toàn dữ liệu ban đầu.

~~~java
// Mã minh họa cho phần kiểm thử producer/consumer.
SecretKey producerKey = deriveAesKey(sharedSecret, salt, "client-to-server");
SecretKey consumerKey = deriveAesKey(sharedSecret, salt, "client-to-server");

byte[] nonce = new byte[12]; // Mỗi lần mã hóa phải dùng nonce duy nhất với key đó.
new java.security.SecureRandom().nextBytes(nonce);

var encryption = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
encryption.init(
        javax.crypto.Cipher.ENCRYPT_MODE,
        producerKey,
        new javax.crypto.spec.GCMParameterSpec(128, nonce));
byte[] ciphertext = encryption.doFinal(plaintext);

var decryption = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
decryption.init(
        javax.crypto.Cipher.DECRYPT_MODE,
        consumerKey,
        new javax.crypto.spec.GCMParameterSpec(128, nonce));
byte[] recovered = decryption.doFinal(ciphertext);

if (!java.util.Arrays.equals(plaintext, recovered)) {
    throw new AssertionError("Producer/consumer interoperability failed");
}
~~~

Đây là skeleton test; cần đóng gói trong method và cung cấp `sharedSecret`, `salt`, `plaintext` từ fixture test. Trong protocol thực, nonce phải duy nhất với mỗi khóa AES-GCM; nếu có AAD, cả hai phía phải dùng cùng bytes AAD. KDF không tạo nonce, không tự trao đổi shared secret và không thay thế authentication của protocol.

## 10. Dùng SecretKey không export được và provider selection

Một lợi ích đáng chú ý của API Java 25 là `HKDFParameterSpec.Builder` có overload nhận `SecretKey`:

~~~java
var params = HKDFParameterSpec.ofExtract()
        .addIKM(protocolLabel)
        .addIKM(nonExportableSharedSecret)
        .addSalt(salt)
        .thenExpand(info, 32);

SecretKey aesKey = KDF.getInstance("HKDF-SHA256")
        .deriveKey("AES", params);
~~~

`nonExportableSharedSecret` có thể đến từ HSM/token. Builder cho phép ghép nhiều phần IKM mà không buộc ứng dụng gọi `getEncoded()` trên từng `SecretKey`. Tuy nhiên, **provider được chọn phải hỗ trợ loại key material và thiết bị đó**.

### Provider selection có độ trễ

Khi gọi `KDF.getInstance("HKDF-SHA256")` mà không chỉ định provider, Java có thể trì hoãn chọn provider cho tới lần `deriveKey`/`deriveData` đầu tiên. Mục đích là chọn provider thực sự hỗ trợ algorithm, parameters và key material được đưa vào.

- Ứng dụng phổ thông nên ưu tiên `KDF.getInstance("HKDF-SHA256")`, không khóa cứng `"SunJCE"` nếu không có yêu cầu triển khai rõ ràng.
- Gọi `getProviderName()` hoặc `getParameters()` **trước** phép derive có thể làm provider bị chọn sớm; provider đó có thể không xử lý được key material HSM ở bước sau.
- Nếu cần policy provider cụ thể (ví dụ môi trường FIPS), cấu hình và kiểm tra provider theo yêu cầu compliance của hệ thống; tên provider đơn lẻ không tự chứng minh hệ thống đạt chứng nhận.
- Oracle JDK 25 ghi nhận SunJCE hỗ trợ `HKDF-SHA256`, `HKDF-SHA384` và `HKDF-SHA512`. Bản phân phối JDK/provider khác phải được kiểm tra bằng integration test tại đúng môi trường triển khai.

Sau khi phép derive đầu tiên hoàn tất, có thể ghi nhận provider được chọn để phục vụ kiểm kê và chẩn đoán:

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
byte[] output = kdf.deriveData(spec);
String providerName = kdf.getProviderName();
~~~

`KDF` và `HKDFParameterSpec.Builder` không được bảo đảm thread-safe. Không dùng chung một instance/builder cho nhiều phép derive đồng thời nếu provider không công bố bảo đảm riêng; tạo object theo operation hoặc đồng bộ hóa đúng cách.

## 11. Thiết kế hợp đồng liên tác cho nhiều thành phần

Một đặc tả KDF cần đủ thông tin để hai đội triển khai độc lập vẫn cho cùng kết quả:

| Trường hợp đồng | Ví dụ | Ghi chú |
| --- | --- | --- |
| KDF | `HKDF-SHA256` | Ghi đúng tên/hash, không chỉ ghi “HKDF”. |
| IKM source | Shared secret từ một key agreement đã xác thực | Không chuyển secret qua log hoặc config plaintext. |
| IKM composition | `componentA || componentB` theo thứ tự được quy định | Nêu rõ thứ tự và cách phân định ranh giới; tránh nối chuỗi mơ hồ. |
| Salt | 32 byte từ protocol handshake | Nêu rõ nguồn, kích thước, có thể lặp hay phải mới theo protocol. |
| Info | UTF-8 của `example/protocol/v1/client-to-server/aes-256-gcm` | Nêu encoding và chính tả chính xác; nên có version và purpose. |
| Output length | 32 byte | Không nhầm bit, byte hoặc số ký tự hex. |
| Output use | AES-256 | Cùng algorithm và mode ở tầng sử dụng. |
| Test vector | RFC 5869 A.1 + vector protocol riêng | Cùng fixture để CI của mọi thành phần dùng. |

### Byte encoding là nguồn lỗi phổ biến

Nếu `info` là chuỗi, hai bên phải thống nhất:

- Charset (ví dụ UTF-8).
- Chuẩn hóa Unicode nếu protocol cho phép ký tự Unicode.
- Cách phân tách các trường (length-prefix, encoding có cấu trúc hoặc định dạng đã chuẩn hóa).
- Chữ hoa/chữ thường và phiên bản label.

Không nối trực tiếp các chuỗi tùy ý như `"ab" + "c"` và `"a" + "bc"` nếu không có quy tắc phân định, vì cả hai đều thành cùng bytes `abc`. Với giao thức quan trọng, định nghĩa cấu trúc `info` bằng định dạng nhị phân/canonical rõ ràng.

### Domain separation

Không tái sử dụng cùng bộ IKM/salt/info cho các mục đích khác nhau. Ví dụ:

| Mục đích | `info` minh họa |
| --- | --- |
| Mã hóa client → server | `checkout/v1/client-to-server/aes-256-gcm` |
| Mã hóa server → client | `checkout/v1/server-to-client/aes-256-gcm` |
| Khóa MAC riêng | `checkout/v1/client-to-server/hmac-sha256` |

Các label chỉ là ví dụ; nếu protocol đã định nghĩa label thì phải dùng đúng chuẩn của protocol. Không tự đổi label trong một phiên bản đang hoạt động vì sẽ làm hai bên dẫn xuất ra khóa khác.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchAlgorithmException` tại `getInstance` | Provider/JDK không hỗ trợ tên KDF | Kiểm tra JDK distribution, provider list và tên `HKDF-SHA256/384/512`. |
| `InvalidAlgorithmParameterException` | `info`, PRK, độ dài hoặc combination tham số không hợp lệ | Kiểm tra mode, PRK length và `L <= 255 * HashLen`. |
| Java và OpenSSL cho output khác nhau | IKM/salt/info khác bytes, digest/mode/L khác | Chạy lại cùng RFC vector; so sánh từng đầu vào ở dạng hex. |
| PRK giống nhưng OKM khác | Khác `info`, độ dài hoặc Expand implementation | Kiểm tra `info`, `L` theo byte và test Expand riêng. |
| Kết quả đổi giữa các request | Dùng IKM/salt khác nhau ngoài ý muốn hoặc trộn fixture test với dữ liệu runtime | Ghi metadata không nhạy cảm: algorithm, version, lengths, provider; không ghi key bytes. |
| `deriveData` ném `UnsupportedOperationException` | Provider giữ key material ở dạng không export được | Dùng `deriveKey` và chuyển `SecretKey` trực tiếp tới consumer nếu API hỗ trợ. |
| Provider chọn được nhưng không dùng được HSM key | Provider bị chốt trước khi đưa key material vào | Tránh gọi `getProviderName()`/`getParameters()` trước derive; kiểm tra provider hỗ trợ key object. |
| Producer/consumer cùng tạo khóa nhưng AES-GCM fail | Nonce, AAD, ciphertext framing hoặc tag handling không đồng nhất | Kiểm tra tầng AEAD độc lập sau khi vector KDF đã pass. |
| Kết quả sai khi IKM ghép nhiều phần | Thứ tự `addIKM`/`addSalt` khác nhau hoặc encoding không giống | Chuẩn hóa thứ tự, độ dài và byte representation trong protocol contract. |
| Test pass trên máy dev nhưng fail production | JDK/provider/FIPS policy hoặc HSM khác | Chạy cùng vector trong image/runtime production và kiểm tra provider thực tế. |

## 13. Ranh giới bảo mật: HKDF không phải password hashing

HKDF là KDF dựa trên HMAC, phù hợp để **extract/expand key material có entropy phù hợp**, ví dụ shared secret từ key agreement hoặc root key được quản lý an toàn. HKDF không làm một mật khẩu yếu trở thành secret mạnh.

Không dùng `HKDF-SHA256` để lưu password người dùng. Password hashing cần thuật toán chuyên dụng, có salt riêng và chi phí tính toán/bộ nhớ được thiết kế để chống đoán mật khẩu. Chọn giải pháp password-hashing theo chính sách bảo mật của hệ thống; đừng nhầm “KDF” nói chung với “password-based KDF”.

Các nguyên tắc cần giữ:

- **Không hardcode IKM production** trong source, test fixture dùng chung hoặc repository.
- **Không log IKM, PRK, OKM, `SecretKey.getEncoded()` hoặc password.**
- Salt thường không cần bí mật; nhưng phải tạo/chọn theo yêu cầu protocol và không dùng thay cho IKM.
- `info` không cần bí mật nhưng rất quan trọng để ràng buộc khóa với mục đích.
- Không dùng lại nonce AES-GCM với cùng khóa.
- Không tự chế HKDF hoặc tự ghép HMAC bằng `Mac` trong code production nếu API/provider chuẩn đã hỗ trợ.
- Nếu có yêu cầu FIPS/compliance, xác minh thuật toán, provider, module, phiên bản và cấu hình được phê duyệt trong môi trường thực tế.

## 14. Bài tập thực hành

### Bài A — Kiểm thử RFC 5869 Test Case 1

Tạo test JUnit cho IKM 22 byte `0b`, salt và info đúng như mục 5. Kiểm tra cả PRK từ `extractOnly()` và OKM từ `thenExpand(...)`.

**Điều kiện đạt:** byte arrays phải khớp chính xác expected values, không chỉ so độ dài hoặc prefix.

### Bài B — Kiểm tra vector rỗng

Chạy RFC 5869 Test Case 3 với salt và info rỗng.

**Điều kiện đạt:** giải thích được sự khác nhau giữa byte array rỗng và chuỗi hex `"00"`; kết quả trùng vector chuẩn.

### Bài C — Đối chiếu OpenSSL

Chạy lệnh OpenSSL 3 ở mục 8 bằng cùng bộ input.

**Điều kiện đạt:** output 42 byte khớp Java và RFC. Ghi lại phiên bản JDK, provider, OpenSSL version và cách biểu diễn output.

### Bài D — Hai thành phần dùng chung hợp đồng

Tạo `KeyProducer` và `KeyConsumer`, mỗi thành phần gọi hàm derive riêng nhưng dùng cùng protocol contract. Producer mã hóa test payload; consumer dẫn xuất khóa độc lập và giải mã.

**Điều kiện đạt:** ciphertext chỉ giải mã thành công khi algorithm, IKM, salt, info, output length, nonce và AAD đồng nhất.

### Bài E — Tách khóa theo mục đích

Dẫn xuất hai khóa từ cùng IKM và salt nhưng dùng `info` khác nhau: một khóa cho AES-GCM, một khóa cho mục đích khác theo protocol.

**Điều kiện đạt:** chứng minh output khác nhau, giải thích domain separation và không dùng cùng khóa cho nhiều mục đích.

## 15. Checklist nghiệm thu

- [ ] Dùng JDK 25+ và API KDF final; không bật `--enable-preview`.
- [ ] Chọn đúng tên thuật toán chuẩn (`HKDF-SHA256`, `HKDF-SHA384` hoặc `HKDF-SHA512`).
- [ ] Test vector RFC độc lập cho cả PRK/OKM.
- [ ] Test thêm vector edge case khi giao thức có thể dùng salt/info rỗng.
- [ ] So sánh ít nhất một vector với implementation khác (ví dụ OpenSSL 3).
- [ ] Thống nhất chính xác byte encoding, thứ tự ghép IKM/salt, `info`, mode và `L`.
- [ ] Dùng `deriveKey` cho production khi consumer nhận `SecretKey`; giới hạn `deriveData` raw bytes cho test/protocol cần thiết.
- [ ] Không dùng `getEncoded()` với key không cần export; xác minh provider/HSM.
- [ ] Không dùng chung `KDF`/builder đồng thời nếu implementation không bảo đảm thread-safe.
- [ ] Dùng domain separation và label có version/purpose.
- [ ] Không dùng HKDF để hash password; không log key material.
- [ ] Có integration test từ producer đến consumer, bao gồm nonce/AAD nếu dùng AEAD.
- [ ] Chạy vector test trên đúng JDK vendor/provider/runtime sẽ triển khai.

## 16. Tài liệu tham khảo chính thức

1. [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510): API KDF chính thức trong Java 25.
2. [Java SE 25 — javax.crypto.KDF](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `getInstance`, `deriveKey`, `deriveData`, delayed provider selection và lưu ý thread safety.
3. [Java SE 25 — HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html): Extract, Expand, Extract-then-Expand và giới hạn output.
4. [Java SE 25 — HKDFParameterSpec.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html): thêm nhiều phần IKM/salt bằng bytes hoặc `SecretKey`.
5. [Java SE 25 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): các tên `HKDF-SHA256`, `HKDF-SHA384`, `HKDF-SHA512`.
6. [Oracle JDK 25 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): danh sách thuật toán của SunJCE, bao gồm các HKDF variants.
7. [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869.html): định nghĩa HKDF, salt/info và Appendix A test vectors.
8. [OpenSSL 3 — EVP_KDF-HKDF](https://docs.openssl.org/3.0/man7/EVP_KDF-HKDF/): chế độ Extract, Expand và Extract-and-Expand.
9. [OpenSSL 3 — openssl-kdf](https://docs.openssl.org/3.0/man1/openssl-kdf/): CLI để đối chiếu đầu ra KDF với thành phần Java.

**Ghi nhớ:** Một phép dẫn xuất khóa chỉ được xem là liên tác khi các bên cùng thống nhất **thuật toán, bytes đầu vào, salt, info, độ dài và cách dùng khóa**. Hãy dùng vector chuẩn để xác minh implementation, dùng một thành phần độc lập để đối chiếu, rồi mới kiểm tra producer/consumer end-to-end. Với Java 25, `KDF` và `HKDFParameterSpec` cung cấp API chuẩn cho HKDF; trách nhiệm thiết kế protocol, quản lý secret và kiểm soát provider vẫn thuộc về hệ thống sử dụng.
