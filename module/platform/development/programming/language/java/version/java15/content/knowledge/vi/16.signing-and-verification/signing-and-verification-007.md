# Ký và xác minh EdDSA: cập nhật dữ liệu theo từng phần hoặc ByteBuffer trong Java

> **Ngữ cảnh Java 15:** JEP 339 đưa EdDSA (Ed25519/Ed448) vào Java. Khi ký hoặc xác minh, ứng dụng có thể chuyển **một mảng byte**, **nhiều đoạn của mảng byte**, hoặc **các byte còn lại trong một ByteBuffer** vào `java.security.Signature.update(...)`. Dù chia thành bao nhiêu lần cập nhật, thuật toán xử lý **một thông điệp logic gồm các byte nối tiếp nhau theo đúng thứ tự**. Bài học dùng API chính thức còn áp dụng trên JDK hiện đại; ví dụ thực hành chạy được trên JDK 17+.

## 1. Vì sao không phải lúc nào cũng gọi một lần update?

Một payload nhỏ có thể được ký đơn giản:

~~~java
// Mảnh mã: signer đã được initSign(privateKey).
signer.update(messageBytes);
byte[] signatureBytes = signer.sign();
~~~

Nhưng thông điệp có thể đến từ:

- File lớn được đọc bằng `InputStream` hoặc `FileChannel`.
- Một luồng mạng, mỗi lần `read(...)` trả số bytes khác nhau.
- Dữ liệu đã nằm trong `ByteBuffer`, ví dụ buffer của Java NIO.
- Nhiều thành phần có định dạng rõ: header, metadata, payload.
- Một mảng lớn mà ứng dụng chỉ muốn ký đoạn `[offset, offset + length)`.

Nếu ép mọi trường hợp thành `Files.readAllBytes(path)` rồi mới ký, ứng dụng có thể phải cấp phát một mảng lớn trên heap. API `Signature.update` cho phép gửi lần lượt từng đoạn **và không bắt buộc caller ghép chúng thành một mảng mới trước**.

**Ranh giới cần hiểu:** khả năng gọi `update` nhiều lần **không có nghĩa mọi provider Ed25519/Ed448 đều dùng lượng RAM hằng số**. Mức sử dụng bộ nhớ nội bộ phụ thuộc vào thuật toán và provider, sẽ phân tích ở phần sau.

## 2. Ba giai đoạn của Signature: khởi tạo, cập nhật, kết thúc

Java Cryptography Architecture (JCA) quy định vòng đời `Signature`:

~~~text
KÝ:
Signature.getInstance("Ed25519")
        |
        v
initSign(privateKey)
        |
        +--> update(chunk1)
        +--> update(chunk2)
        +--> update(chunk3)
        |
        v
sign() -> byte[] chữ ký của chunk1 || chunk2 || chunk3

XÁC MINH:
Signature.getInstance("Ed25519")
        |
        v
initVerify(trustedPublicKey)
        |
        +--> update(đoạn 1)
        +--> update(đoạn 2)
        +--> update(đoạn 3)
        |
        v
verify(signatureBytes) -> true / false / lỗi
~~~

Ký hiệu `||` là **nối bytes không thêm dấu phân cách**. Nếu phía ký đưa vào:

~~~text
update([A, B])
update([C])
update([D, E])
~~~

thì nội dung logic được ký là `[A, B, C, D, E]`. Nó **không** tự động bao gồm kích thước chunk, số lần gọi `update` hay tên file/buffer.

Vì vậy, các cách sau **tương đương về message bytes**:

~~~java
// Mảnh minh họa: mỗi nhóm được chạy với một Signature riêng
// đã initSign bằng cùng private key.
signature1.update(new byte[] {1, 2, 3, 4, 5});

signature2.update(new byte[] {1, 2});
signature2.update(new byte[] {3});
signature2.update(new byte[] {4, 5});
~~~

Nếu cùng dùng **Ed25519 thuần**, cùng private key và cùng chuỗi byte, chữ ký tạo ra sẽ giống nhau vì Ed25519 có tính xác định. Với thuật toán chữ ký khác, có thể chữ ký byte-for-byte khác nhau vì dùng randomness, **nhưng vẫn cùng biểu diễn một thông điệp để kiểm tra**.

**Không ký từng chunk thành từng chữ ký riêng** trừ khi giao thức định nghĩa rõ một bộ chữ ký cho nhiều messages độc lập. `update(chunk1); update(chunk2); sign()` là **một chữ ký cho toàn bộ nội dung nối lại**, khác hoàn toàn với `sign(chunk1)` và `sign(chunk2)`.

## 3. Các overload của `Signature.update` cần biết

`java.security.Signature` cung cấp bốn cách cập nhật thông điệp:

| Phương thức | Phạm vi bytes được xử lý | Tình huống điển hình |
| --- | --- | --- |
| `update(byte b)` | Một byte | Định dạng protocol đặc biệt, dữ liệu rất nhỏ |
| `update(byte[] data)` | Toàn mảng | Payload đã ở dạng byte array |
| `update(byte[] data, int off, int len)` | `data[off]` tới `data[off + len - 1]` | Đọc file/network vào buffer dùng lại |
| `update(ByteBuffer data)` | `data.remaining()` bytes từ `position()` tới trước `limit()` | Java NIO; heap, direct hoặc read-only buffers |

Các lệnh này chỉ có ý nghĩa sau khi `Signature` đã được khởi tạo bằng **`initSign` hoặc `initVerify`**. Nếu chưa khởi tạo, có thể nhận `SignatureException`.

Với overload mảng có `off` và `len`, các tham số không hợp lệ (mảng null, offset/length âm, phạm vi vượt quá độ dài mảng) được API báo bằng `IllegalArgumentException`. Đây là lỗi kiểm soát chỉ số của ứng dụng, không phải chữ ký “không hợp lệ”.

**Quy tắc:** hiểu `len` là **số byte của đoạn**, không phải chỉ số cuối.

~~~java
byte[] bytes = {10, 20, 30, 40, 50};
// Mảnh mã: signer đã initSign.
signer.update(bytes, 1, 3);  // Ký [20, 30, 40].
// signer.update(bytes, 1, 4); sẽ ký [20, 30, 40, 50].
~~~

Hai lời gọi trên ký **thông điệp khác nhau**. Chỉ có thể verify thành công khi bên nhận dùng đúng đoạn đã ký.

## 4. Cập nhật nhiều lần qua byte[]: đúng offset và số bytes đọc được

Ví dụ ký từ một mảng mà không phải tạo array cho từng chunk:

~~~java
// Mảnh mã nằm trong phương thức có xử lý SignatureException.
// signer đã initSign(privateKey), data đã có.
final int chunkSize = 4096;
for (int offset = 0; offset < data.length; offset += chunkSize) {
    int count = Math.min(chunkSize, data.length - offset);
    signer.update(data, offset, count);
}
byte[] signatureBytes = signer.sign();
~~~

Giải thích:

1. `offset` trỏ tới byte bắt đầu của đoạn hiện tại.
2. `count` là số byte thực sự còn lại, tối đa `chunkSize`.
3. Vòng lặp giữ **đúng thứ tự** và không bỏ/trùng byte.
4. `sign()` được gọi **một lần** sau khi cung cấp hết dữ liệu.

Nếu mảng trống, vòng lặp không gọi `update`, và `sign()` ký **thông điệp rỗng** (nếu thuật toán/provider chấp nhận như đặc tả Ed25519). Điều đó khác lỗi “chưa initSign”; một empty message có thể là dữ liệu có chủ đích.

### Lỗi thường gặp khi dùng mảng đã cấp phát sẵn

~~~java
byte[] buffer = new byte[8192];
int n = input.read(buffer);

// SAI: có thể ký cả các byte không được read lần này.
signer.update(buffer);

// ĐÚNG khi n > 0:
signer.update(buffer, 0, n);
~~~

Lệnh `InputStream.read(buffer)` có thể trả **ít hơn `buffer.length`**. Phần buffer còn lại có thể chứa bytes từ lần đọc trước hoặc giá trị khởi tạo. Nếu đưa toàn mảng vào `update`, người ký vô tình thêm dữ liệu không thuộc input hiện tại.

Khi `n == -1` là hết luồng, **không** gọi `update(buffer, 0, -1)`. Nếu `n == 0`, không có bytes mới để ký. Vòng đọc hoàn chỉnh nằm ở phần sau.

## 5. `InputStream`: luồng dữ liệu từng phần, không gọi readAllBytes

Một pattern còn được sử dụng trong Java hiện đại:

~~~java
// Mảnh mã trong phương thức có IOException và SignatureException.
// input là InputStream đang mở, signer đã initSign(privateKey).
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > 0) {
        signer.update(buffer, 0, count);
    }
}
byte[] signatureBytes = signer.sign();
~~~

Điểm quan trọng:

- `InputStream.read(byte[])` báo **số bytes thật được đọc**, không báo “số bytes còn lại của toàn file”.
- Chỉ gọi `update(buffer, 0, count)` với phần đã đọc.
- Giữ nguyên thứ tự đọc; không bỏ chunk và không thêm separators.
- Đóng stream bằng `try-with-resources` ở nơi chịu trách nhiệm sở hữu nó.
- Với file/network, phải kiểm tra **giới hạn dung lượng, timeout và xử lý lỗi** theo yêu cầu sản phẩm.
- Nếu đọc gặp `IOException` giữa chừng, **không** tiếp tục `sign()` rồi coi chữ ký cho partial content là chữ ký thành công của file đầy đủ.

Ví dụ khi ký file:

~~~java
// Mảnh minh họa trong phương thức:
// Path path; PrivateKey privateKey; imports từ java.nio.file,
// java.security và java.io.
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);

try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        if (count > 0) {
            signer.update(buffer, 0, count);
        }
    }
}

byte[] signatureBytes = signer.sign();
~~~

Trong production, cần cân nhắc file bị thay khi đang đọc, quyền truy cập, kích thước tối đa và cách gắn chữ ký với **đúng phiên bản file**. Ký bytes vừa đọc không bảo vệ các bytes khác hoặc phiên bản file đã bị thay sau đó.

## 6. ByteBuffer: `position`, `limit`, `capacity`, `remaining`

`ByteBuffer` là abstraction quan trọng của Java NIO. Để biết chính xác bytes được ký, phải hiểu con trỏ trạng thái:

- **`capacity()`:** dung lượng tối đa của buffer.
- **`position()`:** vị trí byte kế tiếp được đọc/ghi.
- **`limit()`:** ranh giới trên của các bytes hiện tại được phép đọc/ghi; **không bao gồm** byte tại index limit.
- **`remaining()`:** `limit() - position()`.

Giả sử buffer chứa:

~~~text
Chỉ số:       0    1    2    3    4
Byte:        10   20   30   40   50
                 ^              ^
               position=1     limit=4 (exclusive)

`remaining()` = 4 - 1 = 3
Bytes được Signature.update(buffer) xử lý: [20, 30, 40]
~~~

Với:

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {10, 20, 30, 40, 50});
buffer.position(1);
buffer.limit(4);

// Mảnh minh họa; signer đã initSign(privateKey).
signer.update(buffer);
System.out.println(buffer.position()); // 4
System.out.println(buffer.limit());    // 4
~~~

Theo Javadoc `Signature.update(ByteBuffer)`:

1. Chỉ xử lý **`data.remaining()` bytes bắt đầu tại `data.position()`**.
2. Khi phương thức **trả về bình thường**, `position` của buffer bằng `limit`.
3. **`limit` không thay đổi**.
4. Không tự thêm prefix/suffix, bytes đã bỏ qua ở trước `position` hoặc bytes nằm sau `limit`.

Với trường hợp `position == limit`, `remaining() == 0`: một lời gọi `update(buffer)` sẽ **không đóng góp byte mới**. Nếu quên `flip()` trước khi ký, đây là lỗi đặc biệt dễ gặp.

### Quy tắc trạng thái sau lần gọi

~~~text
TRƯỚC: [prefix | bytes còn lại để ký | dữ liệu ngoài phạm vi]
               ^ position         ^ limit

SAU:   [prefix | bytes vừa được xử lý | dữ liệu ngoài phạm vi]
                                  ^ position == limit
~~~

Nếu muốn ký **lại từ đầu cùng phạm vi**, phải tự điều chỉnh vị trí hoặc tạo một **`duplicate()`**, không đưa lại nguyên buffer đã bị consume rồi mong nó cập nhật đủ dữ liệu lần nữa.

## 7. Buffer vừa được ghi cần `flip()` trước khi ký

Với `ByteBuffer`, sau khi ghi bằng `put`, `position` nằm ở **cuối các bytes vừa ghi**, còn `limit` thường bằng capacity. Nếu ký ngay lúc đó, `update` có thể đọc vùng **chưa phải dữ liệu cần ký**.

Pattern đúng:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
buffer.put("Hello".getBytes(StandardCharsets.UTF_8));

buffer.flip();            // limit = 5, position = 0
signer.update(buffer);   // xử lý 5 bytes "Hello"
~~~

Đây là **mảnh mã minh họa**: cần `StandardCharsets` và `signer` đã được khởi tạo.

- `flip()` chuyển từ chế độ ghi sang đọc: `limit = position` cũ, `position = 0`.
- `clear()` chuyển buffer về chế độ **có thể ghi lại**: `position=0`, `limit=capacity`; **không xóa dữ liệu vật lý**.
- `rewind()` đưa `position=0` để đọc lại trong phạm vi limit hiện hành.
- `compact()` giữ dữ liệu còn lại và tạo không gian ghi tiếp; có thể cần cho network protocols nhiều frame.

**Lỗi nghiêm trọng:** gọi `clear()` trước `Signature.update` rồi nghĩ buffer đã “được làm sạch”. `clear()` **chỉ thay đổi con trỏ**, có thể khiến signature cập nhật cả vùng chưa ghi mới hoặc còn bytes cũ. Nếu muốn ký bytes vừa ghi, dùng `flip()`.

## 8. Direct, heap và read-only ByteBuffer

`Signature.update(ByteBuffer)` nhận một `ByteBuffer`. Tùy cách tạo, buffer có thể:

| Loại buffer | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| Heap buffer | `ByteBuffer.wrap(byte[])`, `ByteBuffer.allocate(n)` | Thường backed by heap array; `position/limit` vẫn quyết định phạm vi ký |
| Direct buffer | `ByteBuffer.allocateDirect(n)` | Có thể thuận lợi cho I/O NIO; **không bảo đảm** JCA dùng zero-copy |
| Read-only buffer | `ByteBuffer.wrap(bytes).asReadOnlyBuffer()` | Có thể **đọc** để verify/sign; không thể `put` vào buffer |
| Slice | `buffer.slice()` | Tạo view bắt đầu tại vị trí hiện tại, với con trỏ riêng; nội dung chia sẻ |
| Duplicate | `buffer.duplicate()` | Chia sẻ nội dung nhưng có **position/limit độc lập** |

Tất cả các loại có thể được đưa vào `Signature.update(ByteBuffer)` theo hợp đồng API khi được khởi tạo và có dữ liệu phù hợp. **Không** cần gọi `buffer.array()` để lấy dữ liệu trước: direct hoặc read-only buffer có thể không cho truy cập array bên dưới, dù API `update(ByteBuffer)` xử lý được.

### Muốn giữ nguyên con trỏ của caller? Dùng duplicate

~~~java
// Mảnh minh họa: callerBuffer có position và limit đúng.
ByteBuffer view = callerBuffer.duplicate();
signer.update(view);

// view.position() == view.limit(), nếu update thành công.
// callerBuffer.position() vẫn như trước.
~~~

`duplicate()` có **con trỏ độc lập** nhưng **nội dung bytes chia sẻ**. Nếu một thread khác ghi đè content trong lúc ký, kết quả có thể không ổn định; duplicate không tạo bản sao bất biến của dữ liệu.

### Phạm vi được định nghĩa bằng slice

~~~java
// Mảnh minh họa: original có phần prefix và suffix.
ByteBuffer original = ByteBuffer.wrap(
        new byte[] {99, 1, 2, 3, 4, 88});

original.position(1);
original.limit(5);

ByteBuffer onlyPayload = original.slice();  // [1,2,3,4]
signer.update(onlyPayload);                 // chỉ bốn byte payload
~~~

`slice()` tạo view của **remaining bytes** tại thời điểm gọi. Position của slice bắt đầu từ 0 và limit bằng độ dài vùng đó. Không suy ra rằng view tạo copy: nội dung vẫn có thể chia sẻ với parent.

## 9. Chương trình Java đầy đủ: so sánh toàn mảng, từng phần, InputStream và ByteBuffer

Ví dụ này dùng **Ed25519** (Java 15+, không preview) và một cặp khóa mới cho lần chạy. Cùng thông điệp byte được ký theo **bốn đường cập nhật**; vì Ed25519 thuần có tính xác định, cả bốn chữ ký đều bằng nhau.

Lưu chính xác thành **`EdDsaChunkedUpdateDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Arrays;

public class EdDsaChunkedUpdateDemo {
    private static Signature signer(PrivateKey privateKey)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(privateKey);
        return s;
    }

    private static Signature verifier(PublicKey publicKey)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(publicKey);
        return s;
    }

    private static byte[] signWhole(PrivateKey key, byte[] data)
            throws GeneralSecurityException {
        Signature s = signer(key);
        s.update(data);
        return s.sign();
    }

    private static byte[] signPieces(
            PrivateKey key, byte[] data, int step)
            throws GeneralSecurityException {
        Signature s = signer(key);
        for (int pos = 0; pos < data.length; pos += step) {
            int length = Math.min(step, data.length - pos);
            s.update(data, pos, length);
        }
        return s.sign();
    }

    private static byte[] signStream(PrivateKey key, byte[] data)
            throws Exception {
        Signature s = signer(key);
        try (InputStream input = new ByteArrayInputStream(data)) {
            byte[] buffer = new byte[7];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (n > 0) {
                    s.update(buffer, 0, n);
                }
            }
        }
        return s.sign();
    }

    private static boolean verifyPieces(
            PublicKey key, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature s = verifier(key);
        for (int pos = 0; pos < data.length; pos += 3) {
            int length = Math.min(3, data.length - pos);
            s.update(data, pos, length);
        }
        return s.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();

        byte[] message = "Hóa đơn #42: amount=100 VND\n"
                .getBytes(StandardCharsets.UTF_8);

        byte[] whole = signWhole(pair.getPrivate(), message);
        byte[] pieces = signPieces(pair.getPrivate(), message, 5);
        byte[] streamed = signStream(pair.getPrivate(), message);

        // ByteBuffer direct có hai byte prefix và hai byte suffix.
        // Chỉ ký bytes của message ở vùng position..limit.
        ByteBuffer direct = ByteBuffer.allocateDirect(message.length + 4);
        direct.put((byte) 11);
        direct.put((byte) 22);
        direct.put(message);
        direct.put((byte) 33);
        direct.put((byte) 44);
        direct.flip();
        direct.position(2);
        direct.limit(2 + message.length);

        int originalLimit = direct.limit();
        Signature directSigner = signer(pair.getPrivate());
        directSigner.update(direct);
        byte[] viaBuffer = directSigner.sign();

        Signature readOnlyVerifier = verifier(pair.getPublic());
        ByteBuffer readOnly = ByteBuffer.wrap(message)
                .asReadOnlyBuffer();
        readOnlyVerifier.update(readOnly);
        boolean verified = readOnlyVerifier.verify(whole);

        byte[] tampered = message.clone();
        tampered[tampered.length - 2] ^= 1;

        System.out.println("signature bytes: " + whole.length);
        System.out.println("parts equal whole: "
                + Arrays.equals(whole, pieces));
        System.out.println("stream equals whole: "
                + Arrays.equals(whole, streamed));
        System.out.println("buffer equals whole: "
                + Arrays.equals(whole, viaBuffer));
        System.out.println("buffer consumed: "
                + (direct.position() == direct.limit()));
        System.out.println("limit unchanged: "
                + (direct.limit() == originalLimit));
        System.out.println("read-only verified: " + verified);
        System.out.println("chunked verified: "
                + verifyPieces(pair.getPublic(), message, whole));
        System.out.println("tamper rejected: "
                + !verifyPieces(pair.getPublic(), tampered, whole));
    }
}
~~~

### Biên dịch và chạy

Trên **JDK 17+** có JCA provider hỗ trợ Ed25519:

~~~bash
javac EdDsaChunkedUpdateDemo.java
java EdDsaChunkedUpdateDemo
~~~

**Stdout xác định về logic** (cặp khóa sinh ngẫu nhiên mỗi lần chạy, nhưng các điều kiện boolean được kiểm chứng theo hợp đồng và Ed25519 deterministic):

~~~text
signature bytes: 64
parts equal whole: true
stream equals whole: true
buffer equals whole: true
buffer consumed: true
limit unchanged: true
read-only verified: true
chunked verified: true
tamper rejected: true
~~~

### Vì sao chương trình cho các kết quả đó?

1. **Ed25519** tạo signature raw dài 64 byte.
2. `signWhole` đưa toàn bộ `message` vào engine trong **một lần**.
3. `signPieces` đưa cùng bytes vào theo từng đoạn dài tối đa 5 byte, đúng thứ tự, không thêm/thiếu. Vì cùng private key, chữ ký bằng `whole`.
4. `signStream` dùng `ByteArrayInputStream` để mô phỏng I/O và buffer 7 byte. Mỗi lần đọc, nó dùng **`n`**, không ký toàn bộ buffer, nên signature vẫn bằng `whole`.
5. Buffer direct có **hai byte prefix 11,22** và **hai byte suffix 33,44**, nhưng `position=2` và `limit=2+message.length` khiến `update` chỉ lấy message. Nếu ký cả prefix/suffix thì chữ ký không thể bằng `whole`.
6. Sau update thành công, `position == limit`, còn `limit` không đổi.
7. ByteBuffer read-only vẫn dùng được để verify; không cần truy cập mảng bên dưới hoặc sửa bytes.
8. Bên verify chia input thành các phần **3 byte**, khác kích thước từng đoạn phía ký (**5 byte**). Việc chia khác nhau **không làm thay đổi** thông điệp logic.
9. `tampered` khác `message` đúng một bit, vì vậy chữ ký ban đầu không hợp lệ đối với nội dung đã thay.

Để xác nhận code/API tương thích Java 15 (với compiler còn hỗ trợ mức `--release 15`):

~~~bash
javac --release 15 EdDsaChunkedUpdateDemo.java
~~~

Không dùng tính năng preview hay API đã legacy. Ví dụ đặt mọi thành phần trong một file, không phụ thuộc dữ liệu bên ngoài và không đưa private-key material ra log.

## 10. Nếu cần verify một file lớn, cũng update từng phần

Quy trình verify tương tự ký, nhưng thay private key bằng **public key đáng tin cậy**:

~~~java
// Mảnh minh họa trong phương thức có xử lý IOException,
// GeneralSecurityException; Path path, byte[] signatureBytes,
// PublicKey trustedKey đã có.
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedKey);

try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > 0) {
            verifier.update(buffer, 0, n);
        }
    }
}

boolean valid = verifier.verify(signatureBytes);
~~~

**Phải kiểm tra toàn bộ file** theo đúng thứ tự, trên **cùng bytes** mà bên ký đã xử lý. Một chữ ký hợp lệ trên prefix của file **không** chứng minh toàn bộ file; nếu code vô tình dừng vòng đọc trước EOF, nó đang kiểm tra một **message khác**.

Nếu verify trả `false` hoặc phát sinh ngoại lệ bảo mật, **không chấp nhận file như nội dung đã xác thực**. Chỉ xử lý nghiệp vụ đáng tin sau khi hoàn tất toàn bộ verification, tránh sử dụng nội dung chưa xác thực theo một cách gây tác động không thể đảo ngược.

### ByteBuffer từ FileChannel

`FileChannel` thường đọc vào `ByteBuffer`. Một pattern được áp dụng:

~~~java
// Mảnh minh họa; Signature s đã initSign(privateKey),
// Path file đã có; cần import FileChannel, ByteBuffer, Files.
try (FileChannel channel = FileChannel.open(file)) {
    ByteBuffer buf = ByteBuffer.allocateDirect(8192);
    while (channel.read(buf) != -1) {
        buf.flip();              // Giới hạn đến bytes đã đọc.
        if (buf.hasRemaining()) {
            s.update(buf);       // Consumes vị trí đến limit.
        }
        buf.clear();             // Chuẩn bị nhận khối dữ liệu mới.
    }
}
byte[] signature = s.sign();
~~~

Giải thích:

- `FileChannel.read(buf)` ghi dữ liệu vào buffer, làm tăng `position`.
- `flip()` đặt `limit` ở vị trí cuối dữ liệu vừa ghi và `position=0` để đọc.
- `Signature.update(buf)` đọc các bytes còn lại; **sau khi thành công**, `position == limit`.
- `clear()` đặt buffer ở trạng thái ghi mới. Nó **không** xóa bytes trong vùng nhớ; chính `position/limit` và giá trị trả về từ `read` mới quyết định dữ liệu hợp lệ.
- Đừng ký khi buffer chưa `flip()` hoặc reset con trỏ sai.

**Chú ý:** ví dụ dùng file channel thông thường trong trạng thái đọc tuần tự. Với channel không blocking hoặc mô hình network phức tạp, phải xử lý trường hợp `read()==0`, cancellation, timeout và frame boundaries theo hợp đồng I/O. Không giả định mọi channel luôn trả đúng kích thước block.

## 11. Tác động bộ nhớ: update từng đoạn ≠ luôn streaming O(1) memory

Đây là điểm quan trọng khi bài học liên quan đến **EdDSA**, không chỉ API `Signature` nói chung.

### 11.1. Caller không cần tạo mảng kích thước toàn bộ file

Khi dùng `InputStream` hoặc `FileChannel` với buffer 8 KiB, ứng dụng **không tự cấp phát `byte[]` bằng toàn bộ kích thước file** chỉ để gọi `update`. Điều đó giảm áp lực tạo một mảng lớn **ở tầng application**.

### 11.2. Nhưng provider có thể giữ lại toàn bộ message

RFC 8032 mô tả **PureEdDSA** (như Ed25519 thuần): quy trình ký cần tính hai hàm băm tuần tự có phụ thuộc thông điệp. Nhiều implementation cần **lưu lại message** hoặc đọc lại nó để hoàn tất chữ ký. Một provider có thể đệm dữ liệu được truyền bằng `Signature.update` ở tầng nội bộ.

Hệ quả:

- Gọi `update(buffer,0,n)` nhiều lần **không bảo đảm** heap/native memory của provider luôn không đổi theo kích thước message.
- `ByteBuffer.allocateDirect` **không** bảo đảm zero-copy khi đi qua JCA; provider có thể copy bytes.
- Việc dùng `update(ByteBuffer)` thay vì `update(byte[])` không tự động khiến thuật toán mật mã xử lý một tệp nhiều GB với RAM hằng số.
- Muốn kiểm soát memory footprint của quá trình ký file rất lớn, cần **đo provider thật**, xem tài liệu của nó và thiết kế giao thức/kiến trúc phù hợp thay vì dựa vào tên overload.

### 11.3. Không tự biến Ed25519 thành “ký SHA-256 của file”

Mẫu sau không tương đương ký file gốc:

~~~java
// Mảnh minh họa về một thiết kế khác, KHÔNG thay thế
// message gốc nếu giao thức yêu cầu ký nguyên message.
byte[] sha256 = MessageDigest.getInstance("SHA-256")
        .digest(fileBytes);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(sha256);
byte[] signature = signer.sign();
~~~

Đoạn trên ký **32 bytes digest**, không ký trực tiếp `fileBytes`. Bên verify ký trên file gốc sẽ không thể xác minh chữ ký này theo cùng thông điệp. Nếu giao thức chủ động định nghĩa “ký digest”, phải công bố rõ **domain separation, thuật toán digest, định dạng payload, cách chống tráo đổi**, và kiểm tra cả hai phía; không ngầm coi đó là Ed25519ph.

**Ed25519ph** là một biến thể được định nghĩa riêng trong RFC 8032, không đồng nghĩa với `SHA256(message)` rồi gọi `Signature.getInstance("Ed25519")`. Với bài toán thông thường, dùng Ed25519 chuẩn cùng bytes thông điệp do giao thức quy định.

## 12. Những lỗi thường gặp và hệ quả

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `signer.update(buffer)` sau `input.read(buffer)` | Ký cả dữ liệu cũ/chưa đọc khi số bytes đọc ít hơn capacity | Dùng `update(buffer, 0, count)` |
| Truyền `len` là end index thay vì số byte | Ký nhiều hoặc ít bytes hơn dự định | `len = endExclusive - offset` |
| Không xử lý `read()==-1` | Có thể gửi length âm hoặc xử lý EOF sai | Kết thúc vòng đọc trước update |
| Quên `ByteBuffer.flip()` | Ký các byte khác, hoặc ký dữ liệu rỗng | Sau ghi dùng `flip()` để xác lập vùng đọc |
| Dùng `ByteBuffer.clear()` như xóa nội dung | `clear` chỉ reset cursor; có thể ký dữ liệu cũ | Dùng `flip/clear` đúng thời điểm, không hiểu clear là wipe |
| Ký `buffer.capacity()` bytes thay vì `remaining()` | Gộp bytes ngoài phạm vi hợp lệ | Tin vào `position..limit` |
| Gọi `update(buffer)` hai lần cùng buffer, không reset | Lần thứ hai không thêm byte nào nếu buffer đã hết remaining | Dùng `duplicate()` hoặc reset phạm vi rõ ràng |
| Tạo `ByteBuffer.wrap(bytes,off,len)` rồi cho rằng position=0 | Dễ ký sai do hiểu nhầm API wrap có offset | Kiểm tra position/limit hoặc dùng `slice()` |
| Gọi `array()` trên direct/read-only buffer | `UnsupportedOperationException` hoặc `ReadOnlyBufferException` | Gọi `Signature.update(ByteBuffer)` trực tiếp |
| Ký các chunk sai thứ tự | Thông điệp được ký bị đảo/thiếu bytes | Duy trì thứ tự và kiểm tra tổng số bytes |
| Ký từng chunk riêng bằng `sign()` rồi gửi một chữ ký | Không có chữ ký duy nhất của toàn file | Update tất cả chunks trước một lần `sign()` |
| Giả định kích thước chunk phải giống giữa signer/verifier | Gây phụ thuộc giao thức không cần thiết | Chỉ cần **concatenated bytes** giống nhau |
| Gửi String thay vì UTF-8 bytes cố định | Charset/newline/Unicode khác có thể làm verify fail | Thống nhất encoding và serialization |
| Giả định Ed25519 buffer nội bộ không tăng | Có thể OOME với payload lớn tùy provider | Đo memory, kiểm tra provider và thiết kế |
| Dùng một `Signature` object ở nhiều thread cùng lúc | Trộn dữ liệu/state của nhiều thông điệp | Mỗi operation có engine riêng |
| Kết luận verify=true chứng minh đúng đối tác | Public key có thể do attacker cung cấp | Xác thực public key qua policy tin cậy |
| Cho phép file đã ký nhưng hết hạn hoặc bị replay | Chữ ký không tự bảo vệ freshness | Kiểm tra requestId/expiry/audience riêng |

### Sai lầm cụ thể: `ByteBuffer.wrap(array, offset, length)`

API `wrap(array, offset, length)` tạo buffer view mà **position bắt đầu tại offset** và **limit tại offset + length**, thay vì nhất thiết position=0. Vì thế:

~~~java
byte[] framed = {99, 11, 22, 33, 88};
ByteBuffer view = ByteBuffer.wrap(framed, 1, 3);

// Mảnh minh họa:
System.out.println(view.position());  // 1
System.out.println(view.limit());     // 4
System.out.println(view.remaining()); // 3
~~~

Khi truyền vào `update(view)`, nó sẽ xử lý đúng `11,22,33`. Nhưng nếu code lại gọi `rewind()` trước, position có thể quay về 0 và làm **prefix 99** lọt vào thông điệp. Hãy hiểu rõ cursor của view mình tạo.

## 13. Thứ tự, framing và toàn vẹn ở cấp giao thức

Giả sử bên phát hành ký:

~~~text
update(header)
update(body)
~~~

Về mặt toán học, đó là chữ ký trên `header || body`. Nếu giao thức không có framing rành mạch, hai cặp `header/body` khác nhau đôi khi có thể cho **cùng chuỗi bytes nối lại**, ví dụ:

~~~text
("ab", "c")  -> "abc"
("a", "bc")  -> "abc"
~~~

**Chữ ký không ghi nhớ ranh giới từng lời gọi `update`.** Nếu ranh giới các fields có ý nghĩa bảo mật, ứng dụng phải đưa chúng vào **encoded message** một cách không nhập nhằng:

- Độ dài từng field theo định dạng đã chuẩn hóa.
- Kiểu thông điệp, phiên bản và domain separator nằm trong bytes được ký.
- Các trường tenant, recipient, amount, currency, timestamp, requestId nếu ảnh hưởng quyết định.
- Charset, canonicalization (nếu cần) và quy tắc newline chính xác.
- Giới hạn kích thước, chống replay và chính sách sử dụng khóa.

Ví dụ một khung protocol **mang tính khái niệm**:

~~~text
magic/version | headerLength | headerBytes | bodyLength | bodyBytes
~~~

Trong implementation thật, hãy quy định chính xác endianness, số byte mỗi length, trường bắt buộc, thứ tự và quy tắc overflow. Đừng chỉ ghép chuỗi bằng dấu `|` nếu các fields có thể tự chứa dấu đó.

### Không coi Base64 là một phần dữ liệu đã ký trừ khi protocol yêu cầu

Bên ký có thể gửi:

~~~text
payloadBytes + Base64(signatureBytes)
~~~

Bên nhận cần decode Base64 để lấy đúng signature bytes, và `update` bằng chính payload bytes. Nếu bên nhận đem ký/xác minh **chuỗi Base64 của payload** trong khi bên gửi ký raw payload bytes, hai bên đang dùng messages khác nhau.

## 14. Bắt lỗi và xử lý trạng thái API

Các lỗi quan trọng:

| Lỗi | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Signature.getInstance("Ed25519")` | Không có provider hỗ trợ thuật toán |
| `InvalidKeyException` | `initSign` / `initVerify` | Key không phù hợp thuật toán hoặc provider |
| `SignatureException` | `update` / `sign` / `verify` | State hoặc xử lý ký/verify không hợp lệ |
| `IllegalArgumentException` | `update(byte[],off,len)` | Phạm vi mảng không hợp lệ |
| `IOException` | `InputStream/FileChannel.read` | Dữ liệu chưa được đọc đầy đủ; không coi signature partial là thành công |
| `BufferOverflowException` | Ghi vào `ByteBuffer` | Không đủ remaining space để `put` toàn bộ dữ liệu |
| `ReadOnlyBufferException` | Thử ghi vào read-only buffer | Không được chỉnh bytes; chỉ đọc hoặc dùng buffer khác |

Khi `Signature.sign()` hoặc `verify()` hoàn tất thành công, Javadoc mô tả engine được đưa về trạng thái sau khởi tạo tương ứng và có thể dùng lại với các lần `update` mới. Nhưng **đừng vô tình nối dữ liệu của hai operation**, đặc biệt khi có exception giữa chừng. Cách an toàn, dễ audit là **mỗi request dùng một `Signature` mới** hoặc chủ động khởi tạo lại và quản lý state rõ ràng.

Không bắt mọi exception rồi trả `verify=true`. Với dữ liệu quan trọng về bảo mật, lỗi xử lý phải được coi như **không xác minh thành công** và được báo cáo có kiểm soát.

## 15. Checklist thực tế trước khi đưa vào sản phẩm

1. **Chọn thuật toán cụ thể:** `Ed25519` hoặc `Ed448`; bảo đảm provider hỗ trợ và key đúng loại.
2. **Bảo vệ private key:** không trích xuất raw bytes chỉ để gọi `update`; sử dụng `PrivateKey` với `initSign`.
3. **Ràng buộc public key tin cậy:** bên verify phải biết khóa tương ứng người có quyền phát hành.
4. **Xác định đúng message bytes:** bytes của file, canonical representation hay một protocol frame đã thỏa thuận.
5. **Không ký dữ liệu chưa đọc:** với InputStream luôn dùng `count` trả về.
6. **Đảm bảo chunk order:** mỗi byte xuất hiện **đúng một lần** theo thứ tự.
7. **Xác định phạm vi ByteBuffer:** `position..limit`; `flip()` sau write; không nhầm `clear()`.
8. **Không chia sẻ engine state qua threads:** mỗi operation có `Signature` độc lập.
9. **Kiểm soát lỗi I/O và data size:** file/network có thể bị hủy giữa chừng hoặc vượt giới hạn.
10. **Đo bộ nhớ của provider:** nhất là Ed25519 với message lớn; `update` nhiều lần không tự bảo đảm O(1) RAM.
11. **Tách chữ ký và chống replay:** nonce/requestId/expiry/authorization là kiểm tra nghiệp vụ riêng.
12. **Test các buffer types:** heap, direct, read-only, slice, duplicate, position/limit không mặc định.
13. **Test negative cases:** tampered bytes, sai key, thiếu/trùng chunk, sai offset/length và dữ liệu bị cắt cụt.
14. **Không thay đổi dữ liệu sau khi verify:** dữ liệu được xử lý phải là đúng phiên bản đã xác minh, tránh TOCTOU.
15. **Test liên thông:** với nhiều provider/runtime, dùng dữ liệu byte cụ thể và test vectors của RFC 8032.

## 16. Bài tập kèm đáp án

**Bài 1.** Bên ký gọi `update({1,2})` rồi `update({3,4,5})`. Bên xác minh gọi `update({1,2,3})` rồi `update({4,5})`. Họ có đang xử lý cùng thông điệp không?

**Đáp án:** Có. Cả hai bên xử lý dãy bytes `[1,2,3,4,5]`. Ranh giới chunk không phải một phần của message.

**Bài 2.** `input.read(buffer)` trả về `42` nhưng buffer có capacity `8192`. Phải truyền `len` bao nhiêu cho `update(buffer,0,len)`?

**Đáp án:** `42`, vì chỉ 42 bytes đầu của buffer thuộc lần đọc hiện tại.

**Bài 3.** `ByteBuffer` có `position=5` và `limit=12`. Có bao nhiêu byte được update và vị trí sau khi hoàn thành bình thường?

**Đáp án:** `remaining=12-5=7` bytes; sau `update(ByteBuffer)`, `position=12`, `limit` vẫn `12`.

**Bài 4.** Vì sao gọi `buffer.clear()` trước `update(buffer)` có thể tạo chữ ký sai?

**Đáp án:** `clear()` không xóa bytes, chỉ đặt `position=0`, `limit=capacity`. Vùng được update lúc đó có thể bao gồm dữ liệu cũ/chưa hợp lệ.

**Bài 5.** Làm sao ký một `ByteBuffer` mà không thay đổi `position` của biến do caller sở hữu?

**Đáp án:** Dùng `ByteBuffer copyView=caller.duplicate()` rồi `signer.update(copyView)`. Con trỏ độc lập, nhưng nội dung được chia sẻ; phải tránh mutation đồng thời.

**Bài 6.** Một file có prefix 100 byte và payload 1000 byte; chỉ cần ký payload. Với `update(byte[], off, len)`, truyền `off=100` và `len=1000` đúng hay sai?

**Đáp án:** Đúng, nếu array có ít nhất 1100 bytes và payload thực sự nằm tại dải đó. `len` là số bytes, không phải end index.

**Bài 7.** Một file 2 GB được ký qua `InputStream` với buffer 8 KiB. Có thể kết luận RAM do provider Ed25519 sử dụng tối đa 8 KiB không?

**Đáp án:** Không. Chỉ biết caller dùng buffer đầu vào 8 KiB. PureEdDSA có nhu cầu xử lý message nhiều lượt và provider có thể giữ/đệm dữ liệu nội bộ; phải đo implementation thực tế.

**Bài 8.** Một signature Ed25519 có được ký từng đoạn riêng nếu bên nhận chỉ có một chữ ký cuối cùng không?

**Đáp án:** Nếu mục tiêu là một chữ ký cho toàn message, phải gọi `update` cho toàn bộ các đoạn rồi **`sign()` một lần**. Ký từng đoạn riêng sẽ tạo các chữ ký cho những messages độc lập.

**Bài 9.** Sửa một byte của payload đã ký rồi đặt lại `ByteBuffer.position` về 0. Có làm signature cũ hợp lệ không?

**Đáp án:** Không. Con trỏ chỉ quyết định byte nào được đưa vào verify; nó không làm dữ liệu đã bị sửa trở lại như ban đầu.

**Bài 10.** Vì sao phải kiểm tra key trust, expiry và requestId ngay cả khi `verify(signature)==true`?

**Đáp án:** Signature chỉ xác minh dữ liệu và nguồn gốc **theo public key**. Việc public key có thuộc đúng chủ thể, message còn hiệu lực và có bị replay hay không là những kiểm tra bổ sung.

## 17. Nguồn chính thức và API còn được sử dụng

- **JEP 339 — Edwards-Curve Digital Signature Algorithm, Java 15:** https://openjdk.org/jeps/339
- **Java SE 17 — `java.security.Signature`, `update(byte[])`, `update(byte[],off,len)`, `update(ByteBuffer)`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- **Java SE 17 — `java.nio.ByteBuffer` (position, limit, flip, clear, duplicate, slice):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- **Java SE 17 — `java.io.InputStream`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- **Java SE 17 — `java.nio.channels.FileChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- **RFC 8032 — Ed25519, Ed448 và nhu cầu xử lý message của PureEdDSA:** https://www.rfc-editor.org/rfc/rfc8032
- **Oracle Java Security Standard Algorithm Names:** https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html

**Kết luận:** `Signature.update` có thể nhận **nhiều đoạn `byte[]` hoặc một `ByteBuffer`**, và tất cả được nối theo thứ tự để hình thành **chính xác thông điệp được ký/xác minh**. Với mảng, phải dùng đúng `off/len` và số byte thực tế được đọc. Với `ByteBuffer`, phải kiểm soát `position/limit`, `flip()` và trạng thái sau update. Dù API cho phép đưa dữ liệu vào từng phần, **mức dùng bộ nhớ bên trong EdDSA provider không được bảo đảm cố định**; hãy kiểm tra môi trường thực tế và tuyệt đối không đánh đồng chunked input với một giao thức ký khác.
