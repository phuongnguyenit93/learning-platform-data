# 4.3. Chu trình `update`, `digest`, `reset` và xử lý dữ liệu nhiều phần

## Mục tiêu

Bài này hướng dẫn sử dụng `java.security.MessageDigest` của Java Cryptography Architecture (JCA) để băm một thông điệp thành nhiều phần, tính digest cuối cùng, chủ động hủy state, và băm dữ liệu lớn mà không cần nạp toàn bộ file vào RAM.

Sau bài học, bạn có thể:

- Giải thích vòng đời **`update` → `digest` → reset tự động**, phân biệt với `reset()` do lập trình viên gọi.
- Nạp dữ liệu bằng `byte[]`, các đoạn có `offset/len` và `ByteBuffer` mà không tính thừa byte.
- Băm file hoặc `InputStream` theo từng chunk và chứng minh digest không phụ thuộc kích thước chunk khi byte đầu vào giống nhau.
- Hiểu rõ sự khác biệt giữa `digest()`, `digest(byte[] input)` và `digest(byte[] buf, int offset, int len)`.
- Tránh tái sử dụng state sai, nhầm ranh giới dữ liệu và các lỗi thường gặp liên quan encoding, concurrency, luồng đọc và tính bảo mật.

Ví dụ dùng **Java 17+** và **SHA-256**. `SHA-256` nhận byte input và cho output 256 bit (= 32 byte, thường hiển thị 64 ký tự hex). Các ví dụ tập trung vào API và state, không triển khai thuật toán SHA-256 từ đầu.

## 1. `MessageDigest` là engine có trạng thái

Gọi factory:

```java
MessageDigest md = MessageDigest.getInstance("SHA-256");
```

Snippet giả định đã `import java.security.MessageDigest;` và có xử lý `NoSuchAlgorithmException`. JCA chọn implementation của provider phù hợp đang đăng ký. Đối tượng mới chứa **state của thông điệp rỗng**.

Gọi `md.update(...)` để đưa thêm byte vào state, theo **thứ tự**. Gọi `md.digest()` khi đã nạp đủ để **hoàn tất băm**, nhận mảng digest, đồng thời engine **tự reset** về state ban đầu. Gọi `md.reset()` nếu muốn **hủy dữ liệu đã nạp** mà không lấy kết quả.

```text
MessageDigest mới (thông điệp rỗng)
              |
      update(part 1)
              |
      update(part 2)
              |
      update(part n)
              |
           digest()
              |
              +----> trả digest của (part1 || part2 || ... || partN)
              |
              v
      state rỗng trở lại
              |
      sẵn sàng cho thông điệp tiếp theo
```

Bất kỳ lúc nào trước `digest()`:

```text
update(part1) -> update(part2) -> reset()
                                    |
                                    v
                          bỏ phần dữ liệu đã nạp
                          state rỗng, không có digest
```

Do đó:

- `update("ab"); update("c"); digest()` băm **`abc`**.
- `update("ab"); digest("c")` cũng băm **`abc`**: `digest(byte[] input)` nạp thêm `input` rồi final.
- `update("ab"); reset(); digest("c")` băm **`c`**, vì đã bỏ `ab`.
- `digest(); digest()` trên cùng instance: lần đầu băm state hiện có, lần sau băm **thông điệp rỗng** do lần trước đã reset.
- `digest()` không trả về “state đã lưu”; nó **kết thúc thông điệp**. Nếu muốn tiếp tục cùng thông điệp, chưa được gọi `digest()`.

## 2. Các overload cần phân biệt

| Phương thức | Chức năng | Trạng thái sau lời gọi |
| --- | --- | --- |
| `update(byte b)` | Nạp đúng 1 byte. | Giữ state, có thêm byte. |
| `update(byte[] input)` | Nạp **toàn bộ mảng**. | Giữ state, có thêm mảng. |
| `update(byte[] input, int offset, int len)` | Nạp đúng `len` byte từ `input[offset]`. | Giữ state, có thêm đoạn byte. |
| `update(ByteBuffer input)` | Nạp từ `position` đến trước `limit`; position tiến đến limit. | Giữ state, buffer được tiêu thụ. |
| `digest()` | Final hóa state hiện tại. | **Tự reset**, trả digest byte[]. |
| `digest(byte[] input)` | Nạp **input** rồi final hóa. | **Tự reset**, trả digest byte[]. |
| `digest(byte[] buf, int offset, int len)` | Final hóa và ghi digest vào **buffer đích** tại `offset`, có tối đa `len` byte. | **Tự reset**, trả số byte ghi (có thể ném `DigestException`). |
| `reset()` | Bỏ toàn bộ state đang nạp, không băm. | State rỗng. |
| `getDigestLength()` | Hỏi độ dài digest theo byte. | Không nạp byte; có thể trả 0 nếu provider không xác định được. |

**Rất dễ nhầm overload:** tham số `byte[]` của `digest(byte[] input)` là **đầu vào**; còn `byte[] buf` của `digest(byte[] buf, offset, len)` là **đầu ra**. Muốn băm một đoạn mảng, dùng `update(input, offset, len)`, sau đó `digest()`.

Mỗi lời gọi `update` nối thêm bytes vào cùng một thông điệp. Ranh giới giữa các lời gọi không được mã hóa trong digest; chỉ **chuỗi byte cuối cùng** quan trọng. Vì vậy, chia `abc` thành `a + bc` hay `ab + c` vẫn cho cùng SHA-256 nếu không có `digest` hoặc `reset` xen giữa.

## 3. Chương trình hoàn chỉnh: update, digest và reset

Lưu file **`DigestLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class DigestLifecycleDemo {
    private DigestLifecycleDemo() {}

    private static byte[] utf8(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    private static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");

        md.update(utf8("a"));
        md.update(utf8("b"));
        System.out.println("chunks-abc = " + hex(md.digest(utf8("c"))));

        System.out.println("after-digest-empty = " + hex(md.digest()));

        md.update(utf8("discard"));
        md.reset();
        System.out.println("after-reset-abc = " + hex(md.digest(utf8("abc"))));

        byte[] src = utf8("abc");
        md.update(src, 0, 1);
        md.update(src, 1, 2);
        System.out.println("slices-abc = " + hex(md.digest()));

        ByteBuffer buffer = ByteBuffer.wrap(utf8("__abc__"));
        buffer.position(2);
        buffer.limit(5);
        md.update(buffer);
        System.out.println("buffer-remaining = " + buffer.remaining());
        System.out.println("bytebuffer-abc = " + hex(md.digest()));

        md.update(utf8("abc"));
        byte[] destination = new byte[40];
        int written = md.digest(destination, 4, 32);
        System.out.println("written-bytes = " + written);
        System.out.println("destination-abc = " +
                HexFormat.of().formatHex(destination, 4, 4 + written));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DigestLifecycleDemo.java
java DigestLifecycleDemo
```

**Stdout chính xác:**

```text
chunks-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
after-digest-empty = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
after-reset-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
slices-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
buffer-remaining = 0
bytebuffer-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
written-bytes = 32
destination-abc = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Cách đọc từng kết quả:

1. `md.update("a")` và `md.update("b")` tích lũy `ab`; `md.digest("c")` **nạp tiếp `c`**, trả SHA-256(`abc`) rồi reset.
2. `md.digest()` ngay sau đó cho SHA-256 của **0 byte** (thông điệp rỗng): một bằng chứng rằng state sau `digest` đã được reset.
3. `md.update("discard"); md.reset(); md.digest("abc")` bỏ phần đã nạp dở; chỉ tính trên `abc`.
4. `md.update(src,0,1)` và `md.update(src,1,2)` băm hai đoạn `a` và `bc` chính xác, cũng là `abc`.
5. `ByteBuffer.wrap("__abc__")` chứa hai byte `_` ở đầu và cuối; đặt position=2, limit=5 để lấy đúng `abc`. `md.update(buffer)` tiêu thụ `remaining()` và làm position bằng limit.
6. `md.digest(destination,4,32)` ghi **32 byte OUTPUT** kể từ index 4 của mảng 40 byte. `written = 32` và hàm `HexFormat.of().formatHex(destination,4,4+written)` chỉ in vùng đã ghi.

Lưu ý: `HexFormat` có trong **Java 17+**. Có thể dùng `String.format` hoặc tự định dạng hex ở Java cũ, nhưng ví dụ này chủ đích yêu cầu Java 17+.

## 4. Nạp dữ liệu từ `InputStream` vào một digest duy nhất

`MessageDigest` không quan tâm dữ liệu đến từ mảng byte, file hay mạng: điều kiện để kết quả đúng là mọi byte được truyền vào `update` **đúng một lần, đúng thứ tự**, rồi mới gọi `digest()`. Phần này minh họa cách dùng luồng để chứng minh quy tắc state; cách thiết kế, benchmark và kiểm thử file nhiều GiB, `FileChannel` và `ByteBuffer` được triển khai riêng trong bài **4.4 Băm file lớn bằng luồng hoặc ByteBuffer**.

Phương thức minh họa dưới đây nhận `InputStream` đã mở; cần đặt trong class có import `java.io.InputStream` và `java.security.MessageDigest`, xử lý ngoại lệ theo chữ ký. Đây là **đoạn phương thức**, còn `DigestLifecycleDemo` ở mục 3 là chương trình độc lập của bài này:

```java
static byte[] sha256(InputStream source) throws Exception {
    MessageDigest md = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[8192];
    int n;
    while ((n = source.read(buffer)) != -1) {
        if (n > 0) {
            md.update(buffer, 0, n);
        }
    }
    return md.digest();
}
```

Một lần `read` có thể trả ít hơn 8192 byte, đặc biệt ở chunk cuối; `update(buffer, 0, n)` vì thế chỉ nhận những byte thực đã đọc. Nếu thay bằng `update(buffer)`, các byte còn sót trong buffer cũng bị nạp, làm sai digest. Nếu gọi `digest()` bên trong vòng lặp, state bị reset giữa các chunk và kết quả không còn là digest của toàn luồng.

Hàm này **không đóng** nguồn mà caller sở hữu: nên gọi bằng `try-with-resources`, chỉ dùng kết quả nếu đọc đến EOF thành công. Với `ByteArrayInputStream` chứa đúng byte UTF-8 của `abc`, kết quả hex là `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`. Đổi cách chia chunk không đổi digest nếu giữ nguyên chuỗi byte. Với nguồn không có EOF (stream kéo dài vô hạn), ứng dụng phải xác định điểm kết thúc thông điệp trước khi final.

## 5. Dùng `DigestInputStream` làm lựa chọn thay thế

JDK có `java.security.DigestInputStream`: các byte **đọc qua wrapper** được tự động nạp vào `MessageDigest` gắn với nó. Snippet dưới đây dùng trong một phương thức đã khai báo biến `Path path` và xử lý checked exceptions:

```java
MessageDigest md = MessageDigest.getInstance("SHA-256");
try (DigestInputStream input =
             new DigestInputStream(Files.newInputStream(path), md)) {
    input.transferTo(OutputStream.nullOutputStream());
}
byte[] result = md.digest();
```

Import cần thiết: `java.security.MessageDigest`, `java.security.DigestInputStream`, `java.nio.file.Files`, `java.nio.file.Path` và `java.io.OutputStream`.

`transferTo(OutputStream.nullOutputStream())` đọc hết file thông qua wrapper, không giữ toàn bộ file trong RAM. `DigestInputStream` nạp bytes **khi chúng được đọc**, chứ không tự hoàn tất hash lúc constructor hay `close()`; do đó phải gọi `md.digest()` sau khi đã đọc đủ. Nếu chỉ đọc prefix rồi dừng, digest chỉ tính prefix; đọc trực tiếp từ stream gốc (bỏ wrapper) cũng làm mất những byte ấy khỏi digest wrapper. Có thể dùng wrapper để tiết kiệm code, còn vòng lặp `update` thủ công cho quyền kiểm soát rõ ràng hơn về số byte/ranh giới dữ liệu.

## 6. Các chi tiết của `ByteBuffer` và ranh giới dữ liệu

### `position`, `limit` và `remaining`

`MessageDigest.update(ByteBuffer)` băm bytes trong vùng `[position, limit)` hiện hành của buffer; sau đó position chuyển đến limit, không băm capacity chưa chứa dữ liệu hợp lệ. Với NIO, thường phải gọi `flip()` sau khi ghi vào buffer để chuyển từ mode ghi sang mode đọc. Nếu quên `flip()` hoặc đặt limit sai, có thể băm sai byte.

Khi muốn giữ position của buffer ban đầu, có thể truyền **duplicate**:

```java
ByteBuffer view = original.duplicate();
md.update(view);        // Thay đổi position của view; original giữ position.
```

Đây là snippet có sẵn `original` kiểu `ByteBuffer` và `md` kiểu `MessageDigest`. `duplicate()` tạo view độc lập về position/limit nhưng **vẫn chia sẻ bộ nhớ chứa byte**, không sao chép dữ liệu nền; đừng để thread khác sửa nội dung đồng thời. Với `ByteBuffer` trực tiếp hoặc read-only, ý nghĩa position/limit và `update` vẫn vậy.

### Ranh giới chunk không được mã hóa

Nếu hai chương trình nạp cùng byte stream `abc`, một chương trình `update("a"); update("bc")` và chương trình kia `update("ab"); update("c")`, digest giống nhau. Đừng tưởng số lần gọi `update` lưu được ranh giới trường.

Ví dụ băm một record bằng cách nối trực tiếp UTF-8: hai cặp (`"ab"`, `"c"`) và (`"a"`, `"bc"`) đều cho byte sequence `abc`. Muốn phân biệt, phải dùng **format mã hóa record có cấu trúc**, chẳng hạn nạp trước độ dài của từng trường bằng số byte cố định rồi nạp chính bytes của trường. Khi dùng độ dài, phải đếm **byte đã encode**, không đếm `String.length()` (đơn vị UTF-16).

**Khi hash nhiều thông điệp độc lập**, mỗi thông điệp cần một lần finalize riêng. `update(A1); update(A2); digest()` là hash message A; sau đó `update(B1); digest()` là hash message B. Nếu muốn tách hai nhánh có prefix chung, có thể cân nhắc `clone()` **chỉ khi provider hỗ trợ** hoặc xây hai instance và nạp lại prefix, chứ `reset()` không lưu checkpoint.

## 7. Văn bản, encoding và tính tái lập

`MessageDigest` chỉ xử lý **byte**. Các biểu diễn khác nhau của cùng văn bản nhìn thấy được có thể tạo byte khác nhau:

- Encoding khác nhau, ví dụ UTF-8 và UTF-16.
- Unicode normalization khác nhau.
- Line endings `\n` (LF) và `\r\n` (CRLF).
- Dấu cách, BOM, ký tự ẩn, thứ tự byte hay việc truyền dữ liệu qua một lớp text decoder/encoder.

Luôn chọn encoding rõ ràng khi chuyển chuỗi:

```java
byte[] data = text.getBytes(StandardCharsets.UTF_8);
md.update(data);
```

Snippet giả định `text` là `String` và `md` đã tạo. Tránh dùng `String.getBytes()` không có charset khi cần kết quả byte ổn định trên nhiều runtime. Đặc biệt, để xác minh hash một **file nhị phân**, hãy hash trực tiếp bytes của file, đừng biến nó thành `String` rồi encode lại. Để so khớp digest giữa hai hệ thống, phải thống nhất **exact byte representation** trước khi xem xét provider hay mã hash.

## 8. Tái sử dụng và lỗi trong thực tế

### Khi nào cần gọi `reset()`?

- **Không cần** giữa hai phép băm đã hoàn thành bằng `digest()`: JCA đã reset tự động.
- **Cần** nếu muốn hủy state đã nạp dở và bắt đầu một thông điệp mới trên cùng instance.
- **Không dùng** để chốt digest, tạm lưu state, hoặc cố xóa an toàn dữ liệu nhạy cảm khỏi heap; `reset()` không đảm bảo xóa sạch bộ nhớ.

### Concurrency và ownership

`MessageDigest` là đối tượng **mutable**. Không mặc định nó an toàn khi nhiều thread gọi `update`/`digest` đồng thời; state có thể bị trộn giữa các thông điệp, gây kết quả không kiểm soát. Cách đơn giản là **một instance riêng cho mỗi hoạt động băm**, hoặc duy trì ownership đồng bộ nghiêm ngặt. Với workload cần tối ưu, đo chi phí tạo instance và thiết kế vòng đời rõ ràng trước khi cân nhắc pooling. Không dùng `clone()` nếu provider chưa được kiểm chứng hỗ trợ.

### Đọc lỗi hoặc nguồn thay đổi đồng thời

Nếu `InputStream` đọc dở rồi lỗi, không thể coi kết quả băm của phần đã nhận là hash toàn bộ. Nên báo lỗi và bỏ instance; nếu tái sử dụng instance thì reset trước lần mới. Nếu file bị sửa trong lúc đọc, phép hash có thể bao phủ một trạng thái không nhất quán dù `read` không ném exception. Với bài toán cần tính nhất quán, phải kiểm soát nguồn hoặc cách chụp dữ liệu đầu vào.

### Digest không phải xác thực

`SHA-256` thuần cho dấu vân tay byte, không chứng minh dữ liệu đến từ ai: ai có thể sửa payload cũng có thể tính lại hash. Với yêu cầu toàn vẹn **có khóa bí mật**, xem xét `Mac`/HMAC; với password lưu trữ, dùng cơ chế password hashing có salt và chi phí thích hợp thay vì SHA-256 trực tiếp. Đây là khác biệt về mục tiêu bảo mật, không làm thay đổi quy tắc `update/digest/reset`.

## 9. Bảng lỗi thường gặp

| Nhầm lẫn/lỗi | Triệu chứng | Sửa đúng |
| --- | --- | --- |
| Gọi `digest()` trong mỗi lượt `read` | Cho nhiều hash của từng phần, state reset liên tục. | `update` cho mọi block, `digest` một lần sau khi đọc xong. |
| Dùng `update(block)` với mảng tái sử dụng | Block cuối có byte cũ, hash sai. | Dùng `update(block,0,n)` chính xác. |
| Gọi `reset()` giữa hai phần của một thông điệp | Phần đầu bị loại. | Chỉ reset khi chủ động hủy thao tác dở. |
| Gọi `digest()` rồi tiếp tục `update` | Phần sau trở thành một thông điệp mới. | Chỉ finalize khi có đầy đủ mọi phần. |
| Cho rằng `digest(bytes)` bỏ dữ liệu đã nạp | Hash vô tình gồm cả pending state và `bytes`. | Tạo instance mới/reset nếu cần hash chỉ `bytes`. |
| Nhầm `digest(out,off,len)` là update input | Không đưa input mong muốn vào state. | Dùng `update(input,off,len)`; overload digest đó ghi output. |
| Quên `ByteBuffer.flip()` hoặc giới hạn position/limit | Băm vùng dữ liệu không dự kiến. | Kiểm tra vùng `remaining()` trước `update`. |
| Lấy `String.length()` làm độ dài byte của trường UTF-8 | Tiền tố độ dài sai, encoding record nhập nhằng. | Mã hóa ra byte trước, dùng `byte[].length`. |
| Không cố định charset/chuẩn hóa line ending | Digest khác nhau giữa môi trường. | Thống nhất exact bytes/encoding/protocol. |
| Chia sẻ instance giữa thread | State bị race/trộn. | Instance riêng cho từng phép băm. |
| Stream thất bại vẫn xuất hash như đã hoàn tất | Hash chỉ tính prefix. | Bỏ kết quả, báo lỗi và khởi tạo lại có kiểm soát. |
| Coi hash thuần là xác thực nguồn gửi | Không ngăn được giả mạo nếu attacker sửa cả dữ liệu và hash. | Sử dụng HMAC/chữ ký theo yêu cầu bảo mật. |

## 10. Kiểm tra hiểu bài

1. Tạo hai instance SHA-256 độc lập. Instance A gọi `update("a")`, `update("bc")`, `digest()`; instance B gọi `digest("abc")`. Tại sao output giống nhau? Điều kiện nào làm chúng khác?
2. Nạp `a`, gọi `reset()`, nạp `bc` rồi `digest()`. So với SHA-256(`abc`) và SHA-256(`bc`) để xác nhận prefix đã bị bỏ.
3. Viết một `main` gọi phương thức `sha256(InputStream)` ở mục 4 trên cùng một dữ liệu với buffer dài 1, 7, 8192 rồi 65536 byte; giải thích vì sao digest phải giữ nguyên và tìm lỗi trong `read`/`update` nếu khác.
4. Dùng một ByteBuffer chứa `__abc__`, đặt position=2 và limit=5, xác nhận kết quả bằng `digest("abc")` trên instance khác. Kiểm tra position sau update.
5. Tạo mảng output 40 byte, nạp `abc` rồi gọi `digest(output,4,32)`. Giải thích giá trị trả về 32 và vùng nào chứa digest. Thử output nhỏ để xem exception.
6. Giải thích vì sao hai cặp chuỗi (`ab`, `c`) và (`a`, `bc`) có cùng hash khi nối byte trực tiếp. Đề xuất encoding có tiền tố độ dài giúp tách ranh giới.
7. Băm một file ở dạng binary stream, so sánh kết quả với công cụ SHA-256 độc lập trên máy. Nếu mismatch, kiểm tra source file đang thay đổi, byte count, encoding, BOM và line ending.

Đạt yêu cầu khi bạn giải thích được **`update` tích lũy**, **`digest` chốt và tự reset**, **`reset` bỏ dữ liệu chưa chốt**, và dùng chunk đúng **số byte thực đọc**, giữ digest không đổi khi chỉ đổi kích thước chunk.

## Tài liệu Java 17 chính thức

- [`MessageDigest`: `update`, `digest`, `reset`, `getDigestLength`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [`DigestInputStream`: cập nhật digest khi đọc qua wrapper](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/DigestInputStream.html)
- [`InputStream`: `read`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`ByteBuffer`: `position`, `limit`, `remaining`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
