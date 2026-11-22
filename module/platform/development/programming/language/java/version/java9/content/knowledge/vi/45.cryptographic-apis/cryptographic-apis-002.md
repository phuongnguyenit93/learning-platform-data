# Các hàm băm SHA3-224, SHA3-256, SHA3-384 và SHA3-512 trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích SHA-3 là gì và vì sao bốn thuật toán SHA3-224, SHA3-256, SHA3-384, SHA3-512 có đầu ra khác nhau; lựa chọn biến thể thích hợp; sử dụng API `java.security.MessageDigest` có sẵn trong JDK để băm văn bản hoặc luồng dữ liệu; kiểm tra kết quả với test vector; và nhận biết những chỗ một giá trị hash **không thay thế được** mã xác thực, chữ ký số hay cơ chế lưu mật khẩu.

SHA-3 là họ hàm băm mật mã được chuẩn hóa trong **NIST FIPS 202**, dựa trên thiết kế **Keccak**. Bốn thuật toán được hỏi đều sinh bản băm (**digest**) có độ dài cố định từ đầu vào có độ dài biến đổi. Chúng có mặt trong Java Cryptography Architecture (JCA) từ **Java 9** và vẫn là các thuật toán chuẩn trong những JDK hiện đại. Ví dụ chạy độc lập bên dưới dùng **Java 17+** để tận dụng `HexFormat`; bản thân `MessageDigest` với SHA-3 không đòi Java 17.

## 1. Một hàm băm mật mã làm gì?

Có thể hình dung hàm băm nhận một chuỗi **byte** bất kỳ và trả lại một dãy byte ngắn, có độ dài xác định bởi thuật toán:

```text
Dữ liệu gốc -- UTF-8 / bytes --> SHA3-256 --> 32 byte digest --> 64 ký tự hex
       "abc"               3a985da74fe225b2045c172d6bd390bd...
```

Ba đặc tính cần hiểu:

- **Xác định (deterministic):** cùng thuật toán và cùng byte đầu vào luôn cho cùng byte đầu ra, bất kể máy nào triển khai đúng chuẩn.
- **Một chiều theo mục đích mật mã:** không có phép “giải mã hash” để lấy lại thông điệp. Tuy nhiên, đầu vào đoán được (mật khẩu yếu, mã PIN ngắn) vẫn có thể bị thử hết các khả năng.
- **Chống va chạm và tìm tiền ảnh:** khó tìm hai thông điệp khác nhau có cùng digest (collision) hoặc dựng một thông điệp cho digest đã cho (preimage). Đây là độ khó tính toán, **không có nghĩa là không bao giờ tồn tại va chạm**.

Hiệu ứng thay đổi mạnh của đầu ra khi đổi một phần nhỏ đầu vào thường gọi là *avalanche effect*. Có thể quan sát trên ví dụ, nhưng một vài ví dụ không chứng minh được độ an toàn của toàn bộ thuật toán.

**SHA-3 không mã hóa và cũng không giải mã.** Giá trị digest không giữ bí mật dữ liệu gốc, không mang khóa, không tự xác nhận ai tạo thông điệp. Bản băm phù hợp để đối chiếu tính toàn vẹn khi giá trị hash tham chiếu được cung cấp qua một kênh đáng tin cậy.

## 2. So sánh bốn thuật toán SHA-3

Trong FIPS 202, bốn biến thể dùng cấu trúc sponge với trạng thái Keccak 1.600 bit; chúng khác nhau ở tham số **rate** (phần hấp thụ dữ liệu trong mỗi lượt), **capacity** và số bit digest.

| Tên thuật toán JCA | Độ dài digest | Byte | Chuỗi hex | Rate `r` (bit/byte) | Capacity `c` (bit) | Mức chống collision xấp xỉ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `SHA3-224` | 224 bit | 28 | 56 ký tự | 1152 / 144 | 448 | 112 bit |
| `SHA3-256` | 256 bit | 32 | 64 ký tự | 1088 / 136 | 512 | 128 bit |
| `SHA3-384` | 384 bit | 48 | 96 ký tự | 832 / 104 | 768 | 192 bit |
| `SHA3-512` | 512 bit | 64 | 128 ký tự | 576 / 72 | 1024 | 256 bit |

Với bốn biến thể này, `r + c = 1600` và `c = 2 × số bit digest`. Theo mô hình tấn công tổng quát và bảng độ mạnh của FIPS 202, độ khó tìm collision khoảng `2^(n/2)` phép thử cho digest `n` bit, còn tiền ảnh khoảng `2^n` (không phải luôn đạt được mức bảo đảm đó nếu cách dùng, giao thức hoặc hệ thống có điểm yếu).

**Ý nghĩa của từng biến thể:**

- **SHA3-224:** digest 28 byte, chống collision khoảng 112 bit; hữu ích khi giao thức đã quy định rõ 224 bit. Với thiết kế mới yêu cầu mức chống collision 128 bit, không nên tự chọn 224 chỉ để tiết kiệm bốn byte so với SHA3-256.
- **SHA3-256:** digest 32 byte, mức chống collision khoảng 128 bit. Đây là lựa chọn cân bằng phổ biến cho một giao thức mới **khi đã quyết định sử dụng họ SHA-3**.
- **SHA3-384:** digest 48 byte, phù hợp khi giao thức hoặc mục tiêu an toàn yêu cầu đầu ra dài hơn.
- **SHA3-512:** digest 64 byte, mức chống collision khoảng 256 bit; dùng khi giao thức yêu cầu hoặc độ dài digest/mức an toàn cao hơn là cần thiết. Kích thước và tốc độ có thể bất lợi hơn trên một số nền tảng, cần đo trên dữ liệu thực tế.

Độ dài 512 bit **không có nghĩa mọi ứng dụng đều cần SHA3-512**. Lựa chọn phải dựa vào giao thức, yêu cầu bảo mật, tương thích, kích thước dữ liệu và khả năng của các bên giao tiếp. Không tự đổi tên hoặc thay thế thuật toán đang được quy định sẵn: digest khác thuật toán sẽ không khớp, cho dù cùng độ dài.

## 3. Cơ chế sponge của SHA-3: hiểu đủ để dùng đúng

SHA-3 dựa trên cấu trúc *sponge* (bọt biển):

```text
Thông điệp dạng byte
      |
      v
[Domain separation + padding theo chuẩn SHA-3]
      |
      v
[Absorb]  -- nạp từng khối tối đa r bit vào trạng thái Keccak 1600 bit
      |
      v
[Keccak-f[1600]] -- hoán vị trạng thái qua nhiều vòng
      |
      v
[Squeeze] -- lấy số bit đầu ra cố định: 224 / 256 / 384 / 512
      |
      v
Digest
```

Với bốn biến thể, phần **capacity** càng lớn thì **rate** càng nhỏ: từ 144 byte cho SHA3-224 xuống 72 byte cho SHA3-512. Điều này ảnh hưởng lượng dữ liệu được hấp thụ mỗi lần hoán vị, nhưng không cho phép khẳng định tốc độ trên tất cả CPU/JVM nếu chưa benchmark.

Điểm then chốt: `SHA3-256` và `SHA3-512` **không phải cùng một phép băm chỉ khác độ dài cắt**. Mỗi biến thể có cấu hình sponge riêng. Cắt 32 byte đầu của `SHA3-512(input)` sẽ **không** tạo ra `SHA3-256(input)`.

**Phân biệt tên thuật toán dễ nhầm:**

1. `SHA3-256` khác `SHA-256`: SHA-256 thuộc **SHA-2/FIPS 180**, SHA3-256 thuộc **SHA-3/FIPS 202**. Chúng đều trả 256 bit nhưng không tương thích.
2. `SHA3-256` cũng khác **Keccak-256** theo quy ước được dùng trong một số hệ sinh thái blockchain, vì chuẩn SHA-3 áp dụng quy tắc domain separation/padding khác. Khi dịch vụ ghi “Keccak-256”, không thể dùng `MessageDigest.getInstance("SHA3-256")` và mong kết quả trùng.
3. `SHA3-256` khác `SHAKE256`. SHAKE là họ hàm XOF (*extendable-output function*) cũng thuộc FIPS 202, với ngữ nghĩa độ dài đầu ra và miền phân tách khác. Không thay hai thuật toán lẫn nhau chỉ vì có chữ “256”.

Đối với lập trình Java, **không cần tự triển khai permutation, padding hoặc bit ordering**. Để tránh lỗi mật mã khó kiểm chứng, dùng thuật toán do JCA provider đáng tin cậy cung cấp và xác nhận bằng test vector.

## 4. API Java hiện đại: `MessageDigest`

Java cung cấp cả bốn tên thuật toán qua `java.security.MessageDigest`:

```java
MessageDigest digest = MessageDigest.getInstance("SHA3-256");
byte[] output = digest.digest("abc".getBytes(StandardCharsets.UTF_8));
String hex = HexFormat.of().formatHex(output);
```

Đây là **đoạn trích**: trong tệp Java cần import `java.security.MessageDigest`, `java.nio.charset.StandardCharsets` và `java.util.HexFormat`; lệnh `getInstance` có thể ném `NoSuchAlgorithmException`. `HexFormat` là API từ Java 17.

Các thao tác chính:

| API | Công dụng và điểm cần nhớ |
| --- | --- |
| `MessageDigest.getInstance("SHA3-224")` | Lấy implementation từ provider đã đăng ký. Không cần hard-code tên provider nếu không có yêu cầu cụ thể. |
| `digest(byte[])` | Băm toàn bộ byte đầu vào một lần và hoàn tất. Đầu ra là `byte[]`, **không phải chuỗi hex**. |
| `update(byte[])` hoặc `update(byte[], offset, length)` | Nạp dần byte theo đúng thứ tự, hữu ích khi dữ liệu lớn hoặc được chia gói. |
| `digest()` | Hoàn tất sau các `update(...)`, lấy digest và tự đưa đối tượng trở về trạng thái khởi tạo. |
| `reset()` | Bỏ dữ liệu đã nạp khi cần hủy thao tác hiện tại và băm lại từ đầu. |
| `getDigestLength()` | Độ dài theo byte từ provider; trong một số implementation có thể trả 0, nên kiểm tra cả chiều dài mảng digest thực tế. |
| `MessageDigest.isEqual(byte[], byte[])` | So sánh mảng digest theo API chuyên dụng. Khi so sánh giá trị xác thực bí mật, sử dụng API này thay cho so sánh chuỗi hex thông thường. |

**Đầu vào của SHA-3 là byte, không phải “ký tự” hay “tên tệp”.** Vì vậy, hai chương trình băm cùng văn bản phải thống nhất mã hóa. Với Unicode, hãy gọi `getBytes(StandardCharsets.UTF_8)` (hoặc quy ước byte đã xác định trong giao thức), không phụ thuộc `Charset.defaultCharset()`. Ví dụ `"abc"` trong UTF-8 là ba byte `61 62 63` (hex).

Hãy coi mỗi đối tượng `MessageDigest` là **trạng thái xử lý của một lượt băm**. Không chia sẻ cùng một instance để hai luồng `update` đồng thời; tạo instance riêng cho mỗi phép tính hoặc mỗi luồng với vòng đời rõ ràng. Khi gọi `digest()`, trạng thái đã được reset: nếu muốn băm tiếp phần dữ liệu **nối vào thông điệp trước**, phải nạp lại toàn bộ dữ liệu hoặc duy trì instance chưa hoàn tất.

## 5. Ví dụ Java 17+ độc lập: cả bốn SHA-3, test vector và băm luồng

Ví dụ tạo digest của chuỗi ASCII `"abc"` bằng đủ bốn thuật toán, kiểm tra chiều dài, đối chiếu vector chuẩn SHA3-256, so sánh `update` theo phần với `digest(byte[])`, chứng minh trạng thái reset, kiểm tra đầu vào thay đổi và băm một tệp qua luồng 8 KiB.

Lưu dưới tên **`Sha3DigestDemo.java`**:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class Sha3DigestDemo {
    private static final String[] ALGORITHMS = {
            "SHA3-224", "SHA3-256", "SHA3-384", "SHA3-512"
    };
    private static final int[] EXPECTED_BYTES = {28, 32, 48, 64};
    private static final String SHA3_256_ABC =
            "3a985da74fe225b2045c172d6bd390bd"
            + "855f086e3e9d525b46bfe24511431532";

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static byte[] hashFile(Path path, String algorithm) throws Exception {
        MessageDigest digest = MessageDigest.getInstance(algorithm);
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) {
                digest.update(buffer, 0, length);
            }
        }
        return digest.digest();
    }

    public static void main(String[] args) throws Exception {
        byte[] message = "abc".getBytes(StandardCharsets.UTF_8);

        for (int i = 0; i < ALGORITHMS.length; i++) {
            MessageDigest digest = MessageDigest.getInstance(ALGORITHMS[i]);
            byte[] result = digest.digest(message);
            check(result.length == EXPECTED_BYTES[i], "Wrong digest length");
            System.out.println(ALGORITHMS[i] + " (" + result.length
                    + " bytes): " + HexFormat.of().formatHex(result));
        }

        byte[] expected = HexFormat.of().parseHex(SHA3_256_ABC);
        byte[] oneShot = MessageDigest.getInstance("SHA3-256").digest(message);
        check(MessageDigest.isEqual(expected, oneShot), "SHA3-256 test vector");
        System.out.println("PASS published SHA3-256 abc vector");

        MessageDigest incremental = MessageDigest.getInstance("SHA3-256");
        incremental.update((byte) 'a');
        incremental.update("bc".getBytes(StandardCharsets.UTF_8));
        check(MessageDigest.isEqual(oneShot, incremental.digest()),
                "Incremental hashing differs from one-shot");
        System.out.println("PASS incremental equals one-shot");

        MessageDigest reusable = MessageDigest.getInstance("SHA3-256");
        check(MessageDigest.isEqual(reusable.digest(message),
                reusable.digest(message)), "digest() must reset state");
        System.out.println("PASS digest automatically resets state");

        byte[] altered = "abd".getBytes(StandardCharsets.UTF_8);
        check(!MessageDigest.isEqual(oneShot,
                MessageDigest.getInstance("SHA3-256").digest(altered)),
                "Different sample messages unexpectedly equal");
        System.out.println("PASS changed input changes sample digest");

        Path temp = Files.createTempFile("sha3-demo-", ".txt");
        try {
            Files.write(temp, message);
            check(MessageDigest.isEqual(oneShot,
                    hashFile(temp, "SHA3-256")), "File hash mismatch");
            System.out.println("PASS streamed file equals in-memory digest");
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 Sha3DigestDemo.java
java Sha3DigestDemo
```

Stdout (toàn bộ chuỗi hex, không viết tắt):

```text
SHA3-224 (28 bytes): e642824c3f8cf24ad09234ee7d3c766fc9a3a5168d0c94ad73b46fdf
SHA3-256 (32 bytes): 3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532
SHA3-384 (48 bytes): ec01498288516fc926459f58e2c6ad8df9b473cb0fc08c2596da7cf0e49be4b298d88cea927ac7f539f1edf228376d25
SHA3-512 (64 bytes): b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0
PASS published SHA3-256 abc vector
PASS incremental equals one-shot
PASS digest automatically resets state
PASS changed input changes sample digest
PASS streamed file equals in-memory digest
```

**Giải thích kết quả:**

1. Bốn tên chuẩn đi qua cùng API `getInstance` nhưng cho digest lần lượt 28, 32, 48 và 64 byte. `HexFormat.of()` tạo chuỗi hex chữ thường, mỗi byte trở thành hai ký tự.
2. Test vector `SHA3-256("abc")` được so với chuỗi hex đã biết độc lập với lần băm hiện tại. Đây là phép thử đúng thuật toán; nếu chỉ so hai lần gọi cùng một provider, một implementation sai theo cùng cách vẫn có thể vượt qua.
3. `update('a')` rồi `update("bc")` phải bằng băm một lần `"abc"`. Chia thông điệp thành nhiều mảnh **không** được thay đổi digest nếu thứ tự byte không đổi.
4. Hai lệnh `reusable.digest(message)` liên tiếp trả cùng kết quả vì `digest` hoàn tất và reset trạng thái. Nếu muốn băm `"abcabc"`, không thể giả định lần gọi thứ hai tự nối với lần trước.
5. Test `"abd"` có digest khác `"abc"` chỉ là negative test minh họa, không phải chứng minh toán học rằng collision bất khả thi.
6. Fixture file được tạo và xóa ở thư mục tạm. Dữ liệu được đọc bằng `InputStream` theo từng mảng byte nên không phải nạp cả file vào RAM. Trong ứng dụng, có thể dùng `hashFile(path, "SHA3-256")` với đường dẫn file đã được xác thực.

**Những giá trị mẫu này đều là đầu ra SHA-3 chuẩn của ba byte `0x61 0x62 0x63`; chúng không phải SHA-2 và không phải Keccak-256.** Nếu kết quả ở công cụ khác không khớp, hãy kiểm tra tên thuật toán và byte đầu vào trước khi nghi ngờ provider.

## 6. Áp dụng vào kiểm tra toàn vẹn tệp và dữ liệu

Giả sử bạn nhận tệp `release.zip` cùng digest do bên phát hành công bố qua **kênh đáng tin cậy**. Luồng kiểm tra gồm:

```text
Nguồn tin đáng tin
   └─ thuật toán "SHA3-256", digest chuẩn ở dạng hex
                     |
Tệp release.zip ─ đọc byte qua stream ─ SHA3-256
                     |
              So sánh 32 byte digest
                     |
             Khớp / không khớp
```

Giá trị băm nên được lưu cùng **tên thuật toán**. Một thiết kế manifest nội bộ có thể quy định:

```text
algorithm: SHA3-256
encoding: lowercase-hex
file: release.zip
sha3: <64 ký tự hex lấy từ digest của chính tệp đó>
```

Dòng bắt đầu bằng dấu `<` chỉ mô tả trường dữ liệu cần điền trong **ví dụ định dạng**, không phải digest thực của một file nào. Trong triển khai thực tế, schema phải yêu cầu đúng 64 ký tự hex cho SHA3-256, đúng kiểu chữ khi chuẩn giao tiếp yêu cầu, không chấp nhận thay thuật toán chỉ dựa trên việc chuỗi tình cờ có cùng chiều dài.

Khi so sánh:

- Chuyển digest hex **được tin cậy** về `byte[]` bằng `HexFormat.of().parseHex(...)` và kiểm tra chiều dài, rồi so với digest vừa tính bằng `MessageDigest.isEqual(...)`.
- Tính trên byte nguyên trạng; không đọc file nhị phân thành `String` hay tự chuẩn hóa xuống dòng.
- Cùng một đường dẫn có thể bị thay đổi giữa lúc đọc và lúc sử dụng; trong hệ thống quan trọng, cần xác định một snapshot/descriptor đáng tin cậy hoặc bảo đảm file không bị thay giữa hai thời điểm.
- Ghi nhận tên thuật toán, phiên bản schema, nguồn digest và sai lệch một cách có cấu trúc; không log dữ liệu nhạy cảm không cần thiết.

**Hash không bảo đảm nguồn gốc.** Nếu kẻ tấn công sửa cả file và digest đặt cạnh file, phép so sánh vẫn có thể “khớp”. Để chống sửa đổi có chủ đích, dùng **chữ ký số** từ nhà phát hành hoặc **MAC/HMAC** với khóa bí mật (theo hợp đồng thuật toán và quản lý khóa), rồi xác minh trước khi tin dữ liệu. Chữ ký số không tương đương chỉ băm và dán digest công khai.

## 7. Chọn thuật toán và bảo mật trong ứng dụng mới

### Khi SHA3-256 là lựa chọn hợp lý

Chọn `SHA3-256` khi giao thức, hệ thống của bạn hoặc yêu cầu đa dạng thuật toán quy định SHA-3 với digest 256 bit và cần mức chống collision khoảng 128 bit. Ví dụ: fingerprint của đối tượng bất biến, đối chiếu toàn vẹn khi digest đã được xác thực, một thành phần trong quy trình ký hoặc nhận dạng nội dung có thiết kế giao thức cẩn thận.

**Không mặc định SHA-3 là bản nâng cấp bắt buộc của SHA-2.** Cả SHA-2 và SHA-3 vẫn được dùng trong hệ thống hiện đại; SHA-3 có cấu trúc mật mã khác. Khi làm việc với API đã yêu cầu `SHA-256`, chuyển sang `SHA3-256` sẽ làm hỏng tương thích. Kể cả khi cùng xuất 256 bit, tên thuật toán là một phần **bắt buộc** của hợp đồng giao tiếp.

### Những trường hợp không dùng trực tiếp digest SHA-3

- **Mật khẩu:** không lưu `SHA3-256(password)` hoặc `SHA3-512(password)` đơn thuần. Hàm băm mật mã nhanh không có cơ chế salt và work factor theo từng tài khoản. Với thiết kế hiện đại, dùng bộ xử lý mật khẩu chuyên dụng như **Argon2id**, hoặc lựa chọn phù hợp với nền tảng/chính sách như **scrypt/PBKDF2** với salt ngẫu nhiên riêng và thông số chi phí được quản lý; giữ định dạng lưu có tham số để nâng cấp về sau.
- **Xác thực thông điệp:** digest trần `SHA3-256(data)` không cho biết ai gửi. Dùng HMAC hoặc MAC theo một thuật toán đã thống nhất; không tự ghép kiểu `hash(secret + message)` để thay thế giao thức MAC. Một số provider hỗ trợ `HmacSHA3-256`, nhưng luôn kiểm tra tên thuật toán chuẩn/provider và yêu cầu liên thông thực tế trước khi chọn.
- **Mã hóa dữ liệu:** SHA-3 không trả lại plaintext. Nếu cần bí mật và tính toàn vẹn, chọn cơ chế mã hóa xác thực phù hợp như **AES-GCM** và quản lý nonce/khóa đúng chuẩn; hash chỉ là thành phần khi giao thức yêu cầu.
- **Ngẫu nhiên hoặc token bí mật:** băm giá trị dễ đoán không biến nó thành nguồn entropy tốt. Sinh giá trị ngẫu nhiên bằng `SecureRandom` phù hợp rồi dùng khóa/tạo token theo chính sách.
- **Chống sao chép hoặc quyền truy cập:** hash giống nhau không chứng minh người gọi được cấp quyền. Quyền truy cập cần kiểm tra ở lớp xác thực/ủy quyền riêng.

### Quy ước byte và tương tác giữa nhiều hệ thống

Một văn bản nhìn giống nhau có thể có byte khác nhau do UTF-8/UTF-16, Unicode normalization (NFC/NFD), ký tự xuống dòng `LF`/`CRLF`, khoảng trắng đầu/cuối hoặc thứ tự serialize JSON. Điều kiện để hash trùng là **dãy byte đầu vào phải trùng hoàn toàn**. Khi thiết kế chữ ký/giao thức cho văn bản có cấu trúc, định nghĩa canonicalization (nếu cần) **trước bước băm**, và áp dụng nhất quán ở mọi bên. Không được trim, lowercase hoặc sửa dữ liệu tùy tiện chỉ nhằm “làm cho hash khớp”.

Ví dụ, băm chuỗi `"abc\n"` khác băm `"abc"`. Nếu một tệp được tải xuống khác một byte vì xử lý xuống dòng, SHA-3 sẽ cho digest khác mặc dù trình soạn thảo hiển thị gần như giống nhau.

## 8. Kiểm thử SHA-3 theo từng cấp

Bộ kiểm thử nên xác nhận **thuật toán chuẩn**, **dữ liệu đầu vào**, **biên luồng** và **giao thức**. Một ma trận tham khảo:

| Trường hợp | Dữ liệu/thiết lập | Assertion phù hợp |
| --- | --- | --- |
| Known-answer test (KAT) | Ba byte UTF-8 `"abc"` | Cả bốn digest phải trùng test vector ở stdout trên, không chỉ cùng độ dài. |
| Thông điệp rỗng | Mảng byte `new byte[0]` | Kết quả bằng vector chuẩn cho chuỗi rỗng; không giả định hash rỗng là toàn byte 0. |
| Độ dài digest | Bốn tên chuẩn | Lần lượt 28/32/48/64 byte; chuỗi lowercase hex 56/64/96/128 ký tự. |
| Streaming | Cùng byte được `update` một lần và từng mảnh | Digest bằng nhau trong mọi cách phân mảnh, miễn thứ tự byte giữ nguyên. |
| Biên rate | Kích thước dữ liệu quanh `r - 1`, `r` và `r + 1` byte; ví dụ SHA3-256: 135/136/137 | Kết quả băm chunked bằng one-shot; quan sát lỗi đệm/padding qua test vector đối chiếu độc lập. |
| Tài liệu Unicode | Dấu tiếng Việt, emoji, dạng tổ hợp Unicode | Hash tính trên encoding/normalization đã quy định và giống byte chuẩn tham chiếu. |
| Trạng thái digest | `update`, `digest`, `reset`, tính liên tiếp | Không rò trạng thái giữa thông điệp khi lần băm đã hoàn tất; không nhầm băm nối. |
| Đầu vào thay đổi | `"abc"` và `"abd"` | Digest khác với hai mẫu kiểm thử, đồng thời hiểu đây không phải chứng minh chống collision. |
| Không tương thích | `SHA-256`/`SHA3-256`/`Keccak-256`/`SHAKE` | Kết quả không được dùng thay thế qua hợp đồng thuật toán khác. |
| Provider/triển khai | Các JDK được hỗ trợ, môi trường provider khác nhau | `MessageDigest.getInstance` tạo được algorithm yêu cầu; KAT vẫn đúng hoặc báo thiếu thuật toán rõ ràng. |
| Kịch bản file thực | Tệp nhị phân lớn, tệp 0 byte, file bị sửa | Băm đúng byte stream; mismatch được xử lý; lỗi I/O không bị coi là hash sai. |

Với test tự động, đừng hard-code giả định rằng nhà cung cấp sẽ luôn là provider tên `SUN` trên mọi runtime. Có thể ghi nhận `digest.getProvider().getName()` để chẩn đoán, nhưng điều kiện PASS quan trọng là **kết quả trùng vector chuẩn và đúng giao thức**.

**Known-answer test tốt hơn chỉ kiểm tra hai lần ra giống nhau.** Một implementation có lỗi xử lý endian, padding hoặc tên thuật toán vẫn có thể trả kết quả nhất quán nhưng sai chuẩn. Với dữ liệu lớn, nên so với vector độc lập hoặc implementation đã được kiểm chứng thay vì chỉ lấy chính cùng một provider làm oracle.

## 9. Lỗi hay gặp và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `"SHA-256"` nhưng gọi là SHA-3 | SHA-2 là hàm khác dù cùng 256 bit. | Dùng chính xác `"SHA3-256"` khi hợp đồng yêu cầu SHA-3. |
| Dùng Keccak-256 để đối chiếu SHA3-256 | Khác miền phân tách/padding. | Phân biệt định danh thuật toán trong giao thức và test vector của từng biến thể. |
| Cắt đầu ra SHA3-512 thành 32 byte | Không tạo SHA3-256. | Gọi trực tiếp `MessageDigest.getInstance("SHA3-256")`. |
| Băm `String.getBytes()` mà không chỉ định charset | Byte đầu vào có thể thay đổi theo môi trường. | Dùng `StandardCharsets.UTF_8` hoặc encoding được quy ước. |
| Băm file bằng `Files.readString(...)` | Giải mã, sửa line endings hoặc lỗi với dữ liệu nhị phân. | Dùng `InputStream`, cập nhật `MessageDigest` trực tiếp từ byte. |
| Gọi `update` trên nhiều thread với một digest | Mất ranh giới và thứ tự message. | Mỗi phép băm có instance riêng, bảo đảm chuỗi cập nhật tuần tự. |
| Xem hash cùng file là chữ ký số | Kẻ tấn công có thể thay cả hai. | Digest đáng tin / MAC / chữ ký theo yêu cầu xác thực. |
| Lưu mật khẩu bằng SHA3-512 thuần | Băm quá nhanh cho mật khẩu, không có salt/cost theo tài khoản. | Dùng bộ xử lý mật khẩu chuyên dụng có salt và work factor. |
| Chỉ test `result != null` | Bỏ sót sai thuật toán, byte order, padding và đầu vào. | Test vector chuẩn, độ dài, streaming, encoding và lỗi I/O. |
| Nuốt mọi `NoSuchAlgorithmException`/`IOException` | Dẫn tới đánh dấu thành công dù không băm được. | Báo lỗi có ngữ cảnh, dừng thao tác xác minh và xử lý theo chính sách. |

## 10. Bài tập tự luyện

1. Sửa `Sha3DigestDemo` để kiểm tra cả bốn vector `"abc"` bằng các chuỗi hex tương ứng trong stdout và `HexFormat.of().parseHex(...)`. Test nên thất bại ngay nếu bất kỳ byte nào sai.
2. Tạo dữ liệu đúng 135, 136, 137 byte cho SHA3-256; băm cùng dữ liệu theo ba cách: một lần, `update` từng byte và `InputStream`. Vì sao kết quả phải bằng nhau?
3. Băm hai chuỗi `"xin chào"` và `"xin chào\n"` bằng UTF-8; so sánh digest. Giải thích vai trò của newline và chuẩn hóa dữ liệu.
4. Giả sử file `archive.zip` cùng tệp `archive.zip.sha3` được tải từ một máy chủ không đáng tin. Nếu cả hai được thay đổi đồng thời, vì sao khớp digest chưa đủ để xác thực tác giả file? Đề xuất cơ chế phù hợp.
5. Một đối tác yêu cầu `SHA-256`, còn nhóm bạn đề xuất `SHA3-256` vì “cùng 256 bit”. Điều gì sẽ xảy ra nếu tự đổi thuật toán mà không cập nhật giao thức và hai phía?

## Ghi nhớ

- **Bốn tên chuẩn trên Java:** `SHA3-224`, `SHA3-256`, `SHA3-384`, `SHA3-512`, cho **28, 32, 48, 64 byte**.
- SHA-3 dùng Keccak *sponge*, là một họ thiết kế khác SHA-2; các biến thể SHA-3 không phải phép cắt đầu ra của nhau.
- `MessageDigest` của JCA xử lý byte, hỗ trợ `update` streaming và `digest`; `HexFormat` giúp hiển thị hex trên Java 17+.
- Test phải so với **vector chuẩn độc lập**, kiểm tra byte đầu vào/encoding và cách chia dữ liệu.
- Hash không phải encryption, không phải phương pháp lưu mật khẩu, cũng không tự cung cấp tính xác thực thông điệp.

### Tài liệu chuẩn đang áp dụng

- [NIST FIPS 202 — SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions](https://doi.org/10.6028/NIST.FIPS.202) — định nghĩa bốn SHA-3, sponge, rate/capacity và mức an toàn; xem mục 6 và phụ lục A.
- [Java SE 21 — Standard Algorithm Names, MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) — tên thuật toán JCA và độ dài digest.
- [Java SE 21 — `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html) — vòng đời `update`, `digest`, `reset` và `isEqual`.
- [Java SE 21 — `java.util.HexFormat`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html) — chuyển đổi giữa `byte[]` và hex trên Java hiện đại.