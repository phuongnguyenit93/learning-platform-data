# InputStream.readNBytes(int) và giới hạn lượng dữ liệu cần đọc (Java 11)

Khi đọc dữ liệu từ tệp, kết nối mạng hoặc một nguồn nhị phân bất kỳ, đôi khi ứng dụng chỉ cần **một số byte hữu hạn**. Từ **Java 11**, `java.io.InputStream` cung cấp:

```java
public byte[] readNBytes(int len) throws IOException
```

Phương thức đọc **tối đa `len` byte còn lại** từ stream và trả về một mảng `byte[]` chứa **đúng số byte thực sự đọc được**. Nó hữu ích khi đọc phần đầu tệp, một thông điệp nhị phân nhỏ, hoặc giới hạn lượng dữ liệu cần đưa vào bộ nhớ. Tuy nhiên, **giới hạn số byte đọc** và **xác minh nguồn không vượt quá giới hạn** là hai yêu cầu khác nhau; cần viết logic phù hợp cho từng tình huống.

Bài thuộc nhóm **Byte stream** của Java 11. Mọi API được hướng dẫn ở đây vẫn có giá trị trên JDK hiện đại. Bạn có thể dùng một **JDK đang được hỗ trợ và cập nhật** để thực hành, chẳng hạn JDK 25 LTS; khi compiler cho phép, dùng `javac --release 11` để xác nhận ví dụ không phụ thuộc API được bổ sung sau Java 11.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Hiểu hợp đồng của `InputStream.readNBytes(int)`: số byte tối đa, điểm kết thúc stream, khả năng chặn chờ và ngoại lệ.
2. Phân biệt `readNBytes(int)` với `read(byte[])`, `readNBytes(byte[], int, int)` và `readAllBytes()`.
3. Viết chương trình đọc một phần hữu hạn từ `InputStream` và xử lý trường hợp dữ liệu ngắn.
4. Phân biệt **đọc một bản xem trước có giới hạn** với **từ chối dữ liệu dài quá giới hạn** bằng kỹ thuật đọc `limit + 1` byte.
5. Áp dụng mức trần bộ nhớ, `try-with-resources`, xử lý `IOException` và các yêu cầu timeout khi nguồn chậm.
6. Nhận biết **byte** khác **ký tự**: giới hạn kích thước UTF-8 cần dựa trên byte thực tế.
7. Biết khi nào cần duyệt stream theo từng khối thay vì gom toàn bộ dữ liệu vào một mảng.

## 2. Mô hình tư duy: stream là chuỗi byte được tiêu thụ dần

`InputStream` đại diện cho một **luồng byte theo thứ tự**. Mỗi lần đọc thành công, một phần dữ liệu được tiêu thụ và vị trí đọc tiến về phía trước. Nguồn có thể là tệp, bộ nhớ, kết nối socket hoặc kết quả giải nén.

Giả sử stream chứa năm byte ASCII:

```text
Nguồn ban đầu: A B C D E
               ^
               vị trí đọc

readNBytes(2)  -> [A, B]
Còn lại:           C D E
                   ^

readNBytes(10) -> [C, D, E]
Còn lại:             (EOF)

readNBytes(1)  -> [] (mảng rỗng)
```

Trong tình huống này:

- Lần đầu yêu cầu 2 byte và nhận đúng 2 byte.
- Lần hai yêu cầu 10 byte nhưng chỉ còn 3 byte trước **end of stream (EOF)**, nên nhận mảng dài 3.
- Lần ba ở EOF nhận mảng rỗng; **không** có byte giả hoặc dấu `-1` được chèn vào mảng.

Một stream chưa chắc cho biết trước tổng số byte hoặc còn bao lâu mới kết thúc. Không được dùng giả định rằng “một lần gọi `read` sẽ trả toàn bộ dữ liệu yêu cầu” khi làm việc với stream nói chung.

### Hợp đồng chính xác của `readNBytes(int len)`

| Điều kiện | Kết quả |
| --- | --- |
| `len > 0` và có đủ dữ liệu | Cố đọc cho tới `len` byte, rồi trả mảng có `len` phần tử |
| `len > 0` nhưng EOF xuất hiện sớm | Trả mảng chứa **ít hơn `len` byte** |
| `len == 0` | Trả `new byte[0]` về mặt giá trị, **không tiêu thụ byte** |
| Stream đã ở EOF | Trả mảng rỗng khi yêu cầu đọc tiếp |
| `len < 0` | Ném `IllegalArgumentException` |
| Lỗi I/O trong quá trình đọc | Ném `IOException`; stream có thể đã bị tiêu thụ một phần |
| Không đủ bộ nhớ để cấp phát | Có thể ném `OutOfMemoryError` |
| Nguồn chưa có đủ dữ liệu, chưa báo EOF | Có thể **chặn chờ** cho đến khi đủ byte, EOF hoặc lỗi |

**Lưu ý:** `readNBytes(int)` **không đóng stream**. Code tạo hoặc sở hữu stream thường cần `try-with-resources` để đóng nó. Nếu truyền một stream do caller quản lý vào hàm tiện ích, phải thống nhất rõ bên nào chịu trách nhiệm `close()`.

## 3. Ví dụ 1 — đọc từng phần, nhận biết EOF và độ dài 0

Tạo tệp **`ReadNBytesDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadNBytesDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        try (InputStream in = new ByteArrayInputStream(source)) {
            byte[] first = in.readNBytes(2);
            byte[] second = in.readNBytes(10);
            byte[] atEnd = in.readNBytes(1);
            byte[] zero = in.readNBytes(0);

            System.out.println("First: " +
                    new String(first, StandardCharsets.US_ASCII));
            System.out.println("Second: " +
                    new String(second, StandardCharsets.US_ASCII));
            System.out.println("At EOF length: " + atEnd.length);
            System.out.println("Zero request length: " + zero.length);
        }

        try (InputStream in = new ByteArrayInputStream(source)) {
            try {
                in.readNBytes(-1);
            } catch (IllegalArgumentException expected) {
                System.out.println("Negative length rejected");
            }
        }
    }
}
```

Mở terminal ở thư mục chứa tệp. Sử dụng JDK có hỗ trợ biên dịch mục tiêu Java 11:

```sh
javac --release 11 -encoding UTF-8 ReadNBytesDemo.java
java ReadNBytesDemo
```

**Stdout dự kiến chính xác:**

```text
First: AB
Second: CDE
At EOF length: 0
Zero request length: 0
Negative length rejected
```

**Điểm cần hiểu:**

1. `"ABCDE"` được chuyển thành **5 byte ASCII**, không phụ thuộc mã hóa mặc định của máy.
2. `first.length == 2` vì đã đọc đủ yêu cầu.
3. `second.length == 3` vì sau lần đọc đầu chỉ còn ba byte trước EOF.
4. `readNBytes(1)` tại EOF trả mảng rỗng.
5. `readNBytes(0)` cũng trả mảng rỗng nhưng **không đọc bất kỳ byte nào**; chỉ nhìn vào mảng rỗng của lời gọi `len == 0` thì không thể suy ra stream đã hết dữ liệu.
6. Gọi với độ dài âm gây `IllegalArgumentException`. Điều này khác ngoại lệ `IOException` do nguồn đọc thất bại.
7. `try-with-resources` đóng stream sau khối lệnh, kể cả khi xảy ra ngoại lệ.

Trong ví dụ, `ByteArrayInputStream` cho dữ liệu cố định để có thể kiểm tra chính xác đầu ra; trên file hoặc socket, nguyên tắc API vẫn giống nhau nhưng thời điểm đọc và lỗi I/O phụ thuộc nguồn.

## 4. So sánh các API đọc byte đang được sử dụng

| API | Giá trị trả về | Điểm cần nhớ | Sử dụng khi |
| --- | --- | --- | --- |
| `read()` | `int`: byte `0..255` hoặc `-1` khi EOF | Chỉ đọc một byte mỗi lần | Đọc marker hoặc giao thức đơn giản |
| `read(byte[])` | `int`: số byte đọc hoặc `-1` khi EOF | Có thể trả ít hơn kích thước buffer dù chưa EOF | Đọc theo chunk, ghi dần ra nơi khác |
| `read(byte[], off, len)` | `int`: số byte đọc hoặc `-1` khi EOF | Kiểm soát offset và phần buffer sử dụng | Vòng lặp đọc có buffer tái sử dụng |
| **`readNBytes(int len)`** | **`byte[]`**, dài `0..len` | Cố đọc đến `len` byte hoặc EOF; **có từ Java 11** | Muốn nhận tối đa N byte trong mảng mới |
| `readNBytes(byte[], off, len)` | `int`: số byte đọc `0..len` | Ghi vào buffer của caller, cố đủ `len` byte hoặc EOF; có từ Java 9 | Đọc bản ghi cố định mà muốn tái sử dụng buffer |
| `readAllBytes()` | `byte[]` chứa toàn bộ phần còn lại | Không có mức trần ứng dụng; cần thận trọng với nguồn lớn/không tin cậy | Nguồn nhỏ và kích thước đã biết, được kiểm soát |
| `transferTo(OutputStream)` | `long`: số byte đã chuyển | Chuyển toàn bộ dữ liệu đến output; không tự áp giới hạn | Sao chép stream khi nguồn/đích đã được kiểm soát |

`readNBytes(int)` được đưa vào Java 11; phương thức `readNBytes(byte[], int, int)` và `readAllBytes()` đã xuất hiện ở Java 9 nhưng **vẫn là API hiện hành**. Việc biết từ phiên bản nào giúp đặt `--release 11` đúng, đồng thời tránh nghĩ chúng là phương thức mới thay thế mọi cách đọc.

### Vì sao `read(byte[])` có thể trả ít hơn số byte yêu cầu?

`read(byte[])` thường chỉ bảo đảm có một số dữ liệu được đọc (hoặc EOF/lỗi), không bảo đảm buffer đầy. Một nguồn mạng có thể cung cấp từng khối nhỏ. Ngược lại, `readNBytes(len)` cố đọc đủ `len` byte hoặc đợi đến EOF. Do đó, **mảng trả về ngắn hơn `len`** sau khi `readNBytes(len)` hoàn tất bình thường cho biết **đã gặp EOF trước khi đọc đủ**, còn một lần `read(byte[])` trả ngắn chưa chứng minh EOF.

Đổi lại, `readNBytes(len)` có thể **chờ lâu hơn** trên socket còn mở nhưng dữ liệu đến chậm. Giới hạn số byte không đồng nghĩa giới hạn thời gian chờ.

### Overload dùng buffer của caller

Ví dụ chương trình độc lập **`BufferReadDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class BufferReadDemo {
    public static void main(String[] args) throws IOException {
        byte[] destination = new byte[5];

        try (InputStream in = new ByteArrayInputStream(
                new byte[] {10, 20})) {
            int count = in.readNBytes(destination, 1, 3);

            System.out.println("Count: " + count);
            System.out.println("Buffer: " +
                    Arrays.toString(destination));
            System.out.println("At EOF count: " +
                    in.readNBytes(destination, 0, 1));
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 BufferReadDemo.java
java BufferReadDemo
```

**Stdout chính xác:**

```text
Count: 2
Buffer: [0, 10, 20, 0, 0]
At EOF count: 0
```

Ở đây `readNBytes(destination, 1, 3)` chỉ sửa vùng buffer bắt đầu tại **offset 1**. Nó cố đọc tối đa 3 byte nhưng nguồn chỉ có 2, nên trả `2`. Hai phần tử đã được ghi là `destination[1]` và `destination[2]`, các ô chưa sử dụng giữ giá trị ban đầu là `0`.

**Khác biệt quan trọng:** overload nhận `byte[]` trả **số byte đã đọc** (`int`), còn `readNBytes(int)` trả trực tiếp **mảng byte mới**.

## 5. Hai yêu cầu khác nhau: xem trước N byte và từ chối nguồn vượt N byte

Đây là phần dễ gây nhầm nhất khi xây API nhận payload, tải file hoặc xử lý dữ liệu do người dùng gửi đến.

### Yêu cầu A: chỉ cần N byte đầu tiên

```java
byte[] preview = input.readNBytes(4096);
```

Đây là **đoạn minh họa bên trong phương thức** đã có biến `InputStream input` và xử lý `IOException`. Nó trả tối đa 4096 byte còn lại, phù hợp để lấy phần đầu dữ liệu.

Nếu `preview.length == 4096`, ta **không biết** stream đã kết thúc đúng tại byte 4096 hay còn hàng triệu byte phía sau. API chỉ dừng khi đã đọc đủ yêu cầu, chưa tự kiểm tra có byte tiếp theo hay không.

**Không** kết luận rằng “tệp hợp lệ vì `readNBytes(4096)` trả đúng 4096 byte”; đây mới là giới hạn phần được lấy, chưa phải kiểm tra kích thước nguồn.

### Yêu cầu B: chỉ chấp nhận toàn bộ payload tối đa N byte

Hãy đọc **N + 1 byte**. Khi `readNBytes(N + 1)`:

- Trả mảng **dài tối đa N**: luồng đã gặp EOF trong phạm vi cho phép, có thể chấp nhận toàn bộ nội dung.
- Trả mảng **dài N + 1**: chắc chắn nguồn có ít nhất một byte vượt mức trần, phải từ chối.

```text
maxBytes = 4

Input: A B C D       -> readNBytes(5) trả 4 byte -> chấp nhận
Input: A B           -> readNBytes(5) trả 2 byte -> chấp nhận
Input: A B C D E     -> readNBytes(5) trả 5 byte -> từ chối
Input: A B C D E F G -> readNBytes(5) trả 5 byte -> từ chối
```

**Tại sao cộng thêm đúng 1?** Nếu chỉ đọc N byte, việc nhận đủ N chưa chứng minh stream đã hết. Một byte vượt ngưỡng là bằng chứng đủ để từ chối; không cần tải hết phần còn lại.

Khi dùng `N + 1`, phải bảo đảm không tràn số nguyên: `N` không thể là `Integer.MAX_VALUE`. Trong hệ thống thực tế, nên đặt **mức trần cấu hình hữu hạn và hợp lý**, thường nhỏ hơn rất nhiều giới hạn đó, đồng thời kiểm soát bộ nhớ.

## 6. Ví dụ 2 — hàm kiểm tra payload không vượt giới hạn

Đây là chương trình độc lập, minh họa thuật toán thường dùng với đầu vào có kích thước nhỏ, ví dụ một thông điệp tối đa 1 MiB. Mức 1 MiB **chỉ là chính sách mẫu của bài**, không phải giới hạn chung của Java.

Tạo tệp **`BoundedReadDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class BoundedReadDemo {
    private static final int HARD_LIMIT = 1024 * 1024;

    static byte[] readAtMost(InputStream in, int maxBytes)
            throws IOException {
        Objects.requireNonNull(in, "in");

        if (maxBytes < 0 || maxBytes > HARD_LIMIT) {
            throw new IllegalArgumentException(
                    "maxBytes outside permitted range");
        }

        byte[] data = in.readNBytes(maxBytes + 1);

        if (data.length > maxBytes) {
            throw new IllegalArgumentException(
                    "Input exceeds maxBytes");
        }

        return data;
    }

    private static void check(String label, byte[] source,
                              int maxBytes) throws IOException {
        try (InputStream in = new ByteArrayInputStream(source)) {
            try {
                byte[] data = readAtMost(in, maxBytes);
                System.out.println(label + ": accepted "
                        + data.length + " bytes");
            } catch (IllegalArgumentException rejected) {
                System.out.println(label + ": rejected");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        check("Exactly four",
                "ABCD".getBytes(StandardCharsets.US_ASCII), 4);
        check("Two",
                "AB".getBytes(StandardCharsets.US_ASCII), 4);
        check("Oversized",
                "ABCDE".getBytes(StandardCharsets.US_ASCII), 4);
        check("Empty", new byte[0], 0);
        check("UTF-8 accent",
                "é".getBytes(StandardCharsets.UTF_8), 1);
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 BoundedReadDemo.java
java BoundedReadDemo
```

**Stdout chính xác:**

```text
Exactly four: accepted 4 bytes
Two: accepted 2 bytes
Oversized: rejected
Empty: accepted 0 bytes
UTF-8 accent: rejected
```

**Giải thích:**

1. `HARD_LIMIT` giới hạn mức được phép cấp phát theo **chính sách ứng dụng**; code từ chối `maxBytes` âm hoặc lớn hơn 1 MiB **trước khi đọc**.
2. `readNBytes(maxBytes + 1)` đảm bảo mảng nhận được có **không quá N + 1 byte**. Nếu N hợp lệ, biểu thức `N + 1` cũng không tràn `int`.
3. Khi mảng trả về dài hơn `maxBytes`, đầu vào đã vượt giới hạn; code ném ngoại lệ có thể chuyển thành phản hồi lỗi cho người gửi.
4. Khi mảng có không quá `maxBytes` byte, lệnh gọi đã gặp EOF và trả **đầy đủ phần còn lại** trong phạm vi cho phép.
5. `maxBytes == 0` là giá trị có nghĩa: chỉ chấp nhận stream rỗng. Phương thức đọc **một byte để kiểm chứng**, khác hoàn toàn với `readNBytes(0)`.
6. Ký tự `é` trong UTF-8 gồm **2 byte**, vì vậy bị từ chối khi giới hạn là **1 byte**. Đây là kiểm tra kích thước byte, không phải số ký tự.
7. Hàm `readAtMost` **không tự đóng `in`**; nơi sở hữu stream dùng `try-with-resources` để đóng sau khi hoàn thành.

**Giới hạn của giải pháp:** nếu nguồn do bên khác kiểm soát liên tục giữ kết nối mở và chỉ gửi ít hơn `maxBytes + 1` byte, lệnh đọc có thể đợi EOF hoặc dữ liệu tiếp theo. Để bảo vệ endpoint mạng, cần thêm **read timeout, thời hạn tổng thể hoặc cơ chế hủy phù hợp với thư viện kết nối**. Giới hạn kích thước **không tự cung cấp timeout**.

### Kiểm tra không vượt giới hạn khác với cắt bớt dữ liệu

Có hai chính sách nghiệp vụ khác nhau:

- **Preview/truncate:** chỉ lấy N byte đầu; việc nguồn dài hơn N có thể chấp nhận được.
- **Reject oversize:** toàn bộ dữ liệu phải không vượt N; dùng `N + 1` để phát hiện ít nhất một byte vượt quá.

Không thay thế chính sách “reject” bằng “truncate” mà không được phép: nếu dữ liệu là tệp cấu hình, JSON, payload chữ ký, bản ghi tài chính hoặc nội dung có ý nghĩa toàn vẹn, âm thầm bỏ phần cuối có thể biến dữ liệu ban đầu thành dữ liệu khác.

## 7. Ví dụ 3 — đọc một số byte đầu từ file thật

`InputStream` có thể lấy từ `Files.newInputStream(Path)`. Sau khi đọc N byte, các byte còn lại vẫn có thể được đọc tiếp từ **cùng stream**.

Tạo tệp **`FilePrefixDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FilePrefixDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("read-nbytes-", ".bin");

        try {
            Files.write(file, new byte[] {10, 20, 30, 40});

            try (InputStream in = Files.newInputStream(file)) {
                byte[] firstThree = in.readNBytes(3);

                System.out.println("Prefix: " +
                        Arrays.toString(firstThree));
                System.out.println("Next byte: " + in.read());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 FilePrefixDemo.java
java FilePrefixDemo
```

**Stdout chính xác:**

```text
Prefix: [10, 20, 30]
Next byte: 40
```

Ví dụ này cho thấy:

- `Files.write` tạo file nhị phân có 4 byte để việc kiểm tra không phụ thuộc tệp do người học chuẩn bị trước.
- `in.readNBytes(3)` chỉ đọc ba byte đầu.
- `in.read()` ngay sau đó đọc byte thứ tư với giá trị nguyên `40` (trong khoảng `0..255`); nếu đã EOF thì `read()` trả `-1`.
- `try-with-resources` đóng luồng đọc, còn `finally` xóa file tạm kể cả khi có lỗi.
- Nếu file thực tế có thể do người khác sửa đồng thời, kích thước hoặc nội dung có thể thay đổi giữa các lần kiểm tra; kiểm tra `Files.size(file)` trước khi đọc chỉ là một **tín hiệu**, không thay thế kiểm tra thực tế trong lúc đọc.

Trong dự án thật, đầu vào thường là `Path` được chọn theo quyền truy cập và yêu cầu nghiệp vụ; việc kiểm soát đường dẫn là trách nhiệm riêng của ứng dụng.

## 8. Byte khác với ký tự: đừng cắt giữa chuỗi mã hóa

`InputStream` làm việc với **byte**, không tự hiểu Unicode hoặc UTF-8. Với dữ liệu văn bản:

```java
byte[] raw = "é".getBytes(StandardCharsets.UTF_8);
System.out.println(raw.length); // 2
```

Đây là một **đoạn minh họa bên trong phương thức**, cần `import java.nio.charset.StandardCharsets;`.

Một ký tự Unicode có thể cần nhiều byte trong UTF-8. Nếu dùng `readNBytes(1)` trên hai byte UTF-8 biểu diễn `é`, bạn chỉ nhận **một nửa chuỗi mã hóa**, và kết quả không đủ để giải mã thành ký tự gốc. Dùng `new String(truncated, StandardCharsets.UTF_8)` cũng không phải cách xác nhận văn bản hợp lệ: decoder mặc định có thể **thay thế byte lỗi bằng ký tự thay thế**.

**Cách đúng phụ thuộc mục đích:**

- Nếu mục tiêu là **giới hạn kích thước payload**, kiểm tra số byte trên stream bằng mức trần rồi mới giải mã văn bản.
- Nếu mục tiêu là **đọc đúng N ký tự**, dùng API xử lý ký tự và quy tắc Unicode phù hợp; số ký tự không đồng nghĩa số byte, code point cũng không đồng nghĩa grapheme cluster.
- Nếu mục tiêu là **xem trước N byte**, ghi rõ rằng preview có thể kết thúc giữa một ký tự UTF-8. Không xem preview này là văn bản hoàn chỉnh.
- Nếu cần xác thực UTF-8 nghiêm ngặt, có thể dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT` sau khi đã nhận đầy đủ byte, thay vì mặc định thay thế dữ liệu sai.

Ví dụ đoạn mã **trong phương thức có `byte[] bytes`** để báo lỗi khi dữ liệu UTF-8 không hợp lệ:

```java
String text = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
```

Đoạn này cần imports `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets` và `java.nio.charset.CodingErrorAction`, đồng thời xử lý hoặc khai báo `CharacterCodingException`. Đây là **mẫu minh họa**, không phải một chương trình độc lập. Phải phân biệt hai bước **kiểm tra lượng byte** và **kiểm tra tính hợp lệ của mã hóa văn bản**.

## 9. An toàn bộ nhớ, I/O và tài nguyên

### Giới hạn đọc không đồng nghĩa nguồn đã “an toàn tuyệt đối”

`readNBytes(len)` trả về tối đa `len` byte, nhưng vẫn phải **cấp phát bộ nhớ tương ứng với dữ liệu đọc**. Nếu code cho người dùng tự đặt `len` quá lớn, một request có thể sử dụng lượng bộ nhớ vượt ngân sách, thậm chí gây `OutOfMemoryError`. Đừng truyền `Integer.MAX_VALUE` hoặc một giá trị cực lớn mà không có chính sách tài nguyên. Chọn mức trần phù hợp với endpoint và ngân sách bộ nhớ thực tế.

Khi dùng `readNBytes(limit + 1)` để từ chối nguồn lớn, công cụ dừng đọc **ngay khi thấy byte vượt ngưỡng**; nó không cần đọc hết nguồn để quyết định. Nhưng ứng dụng phải **đóng hoặc xử lý phần stream còn lại theo quy định của giao thức**; đừng giả sử mọi socket/HTTP body có thể giữ nguyên để tái sử dụng kết nối sau khi chủ động bỏ dở đọc.

### Không dùng `available()` làm kích thước toàn bộ nội dung

`InputStream.available()` chỉ cung cấp **ước lượng số byte có thể đọc ngay mà không chặn**, không bảo đảm đó là tổng byte còn lại hoặc kích thước dữ liệu hoàn chỉnh. Với network stream, `available() == 0` có thể xảy ra dù kết nối còn mở và dữ liệu sẽ đến sau.

Vì thế, các lối viết như:

```java
byte[] data = new byte[in.available()];
in.read(data);
```

là **ví dụ cách làm sai** nếu mục tiêu là đọc toàn bộ một stream tùy ý: buffer có thể thiếu hoặc nhiều hơn dự kiến, và một lần `read` có thể không lấp đầy buffer. Hãy dùng API theo hợp đồng: `readNBytes` cho giới hạn hữu hạn, hoặc vòng lặp có buffer khi streaming.

### Timeout và lỗi I/O

`readNBytes(len)` **có thể chặn chờ** cho tới khi nhận đủ byte, gặp EOF hoặc lỗi. Với socket/request, hãy đặt **read timeout hoặc tổng deadline** ở lớp kết nối/giao thức phù hợp, tùy môi trường server và thư viện. Việc truyền `len = 1024` không có nghĩa phương thức sẽ hoàn thành trong một thời gian cố định.

Nếu xảy ra `IOException` sau khi đã đọc một số byte, trạng thái của stream có thể đã thay đổi. Không tự giả định có thể gọi lại với cùng tham số và nhận phần dữ liệu cũ. API khuyến nghị đóng stream sớm sau lỗi I/O trừ khi giao thức và implementation quy định cách hồi phục rõ ràng.

### Trường hợp dữ liệu sau giải nén

Một payload nén nhỏ vẫn có thể giải nén thành lượng dữ liệu rất lớn. Khi giới hạn kích thước **nội dung sau giải nén**, cần áp trần **trên luồng byte đã giải nén**, không chỉ lên file nén ban đầu. Cũng cần giới hạn thêm tỷ lệ nén, thời gian CPU và số tài nguyên tạo ra nếu bài toán có nguy cơ giải nén không kiểm soát.

## 10. Khi dữ liệu lớn: đọc theo khối và kiểm tra tổng số byte

Nếu payload không nhỏ, **không nhất thiết phải gom toàn bộ thành một mảng `byte[]`**. Thay vào đó, dùng `read(byte[])` nhiều lần và kiểm soát số byte tích lũy. Ví dụ dưới đây là **phương thức minh họa** chép dữ liệu từ `InputStream in` sang `OutputStream out`, với giới hạn kích thước đầu vào:

```java
static long copyWithLimit(InputStream in, OutputStream out,
                          long maxBytes) throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes < 0");
    }

    byte[] buffer = new byte[8192];
    long total = 0;

    int count;
    while ((count = in.read(buffer)) != -1) {
        if (count > maxBytes - total) {
            throw new IOException("Input too large");
        }
        out.write(buffer, 0, count);
        total += count;
    }
    return total;
}
```

Phương thức cần imports `java.io.InputStream`, `java.io.OutputStream` và `java.io.IOException`; nó được gọi từ code quản lý vòng đời của hai stream. **Đây không phải lớp độc lập** vì không có `main`.

Ý nghĩa:

1. Buffer cố định 8192 byte, nên bộ nhớ dùng cho buffer không tăng theo tổng kích thước dữ liệu.
2. Mỗi lần `read(buffer)` trả số byte thực nhận hoặc `-1` ở EOF. Chỉ ghi đúng `count` byte bằng `out.write(buffer, 0, count)`.
3. Kiểm tra `count > maxBytes - total` trước khi tăng bộ đếm giúp tránh tổng vượt mức trần. Trong trường hợp `total` luôn nằm trong `0..maxBytes`, hiệu `maxBytes - total` không âm.
4. Khi phát hiện nguồn dài quá giới hạn, phương thức có thể đã ghi **một phần dữ liệu trước đó** vào `out`. Nếu đích là một file hoặc giao dịch cần **all-or-nothing**, phải dùng vùng tạm/staging rồi chỉ xác nhận sau khi kiểm tra xong toàn bộ.
5. Với dữ liệu khổng lồ, cần thêm timeout, kiểm tra tài nguyên đích, xử lý I/O error và chính sách loại bỏ dữ liệu tạm.

`readNBytes(int)` phù hợp khi muốn **một mảng byte nhỏ có giới hạn rõ ràng**. Vòng lặp chunk phù hợp khi muốn **xử lý hoặc sao chép nhiều byte mà không giữ toàn bộ trong RAM**. Đây là hai kỹ thuật bổ sung cho nhau.

## 11. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `readAllBytes()` cho đầu vào không tin cậy | Có thể dùng quá nhiều bộ nhớ hoặc chờ tới EOF không xác định | Áp giới hạn chính sách; cân nhắc `readNBytes(limit + 1)` hoặc xử lý theo chunk |
| Tin rằng `readNBytes(limit)` xác nhận file không vượt limit | Đọc đúng limit chưa chứng minh EOF | Đọc thêm một byte bằng `limit + 1` nếu mục đích là từ chối nguồn quá lớn |
| Không kiểm tra `data.length` | Nhầm dữ liệu đã đủ khi gặp EOF sớm | Với giao thức cần đúng N byte, xác thực `data.length == N` |
| Nhầm `read(byte[])` với `readNBytes(int)` | Một lần `read` có thể đọc ngắn dù chưa EOF | Dùng `readNBytes` hoặc lặp đến đủ lượng cần thiết |
| Coi `readNBytes(0)` trả mảng rỗng là chứng minh EOF | Không đọc byte nào nên không thể kết luận EOF | Kiểm tra bằng yêu cầu đọc dương khi cần xác định dữ liệu còn lại |
| Dùng `available()` để cấp phát toàn bộ buffer | Ước lượng này không phải kích thước toàn stream | Dựa trên mức trần do ứng dụng đặt và kết quả đọc thật |
| Không giới hạn tham số `len` | Có thể bị yêu cầu cấp phát mảng lớn ngoài ngân sách RAM | Xác thực giá trị trước khi đọc; cân nhắc số request đồng thời |
| Cắt byte rồi giải mã UTF-8 ngay | Có thể cắt giữa ký tự hoặc tạo văn bản thay thế | Xác thực kích thước payload và decode sau khi có nội dung hoàn chỉnh |
| Quên `close()` | Rò rỉ file handle/kết nối/tài nguyên | Dùng `try-with-resources` tại nơi sở hữu stream |
| Chỉ áp giới hạn byte nhưng không đặt timeout | Kết nối chậm có thể giữ tác vụ chờ lâu | Đặt timeout/deadline ở lớp network phù hợp |
| Tự retry cùng stream sau `IOException` | Có thể lặp/thiếu byte vì stream đã tiêu thụ một phần | Đóng và xử lý lỗi theo chính sách I/O, chỉ retry khi có cơ chế mở lại nguồn |
| Dùng `limit + 1` khi `limit == Integer.MAX_VALUE` | Tràn số nguyên, khiến tham số âm | Đặt HARD_LIMIT nhỏ và hợp lý trước khi cộng |
| Dùng giới hạn file nén cho dữ liệu đã giải nén | Bỏ sót khả năng phình to sau giải nén | Giới hạn trên stream dữ liệu sau giải nén |

## 12. Bài tập tự kiểm tra

**Bài 1 — Dự đoán số byte.** Với stream chứa `"HELLO"`, lần lượt gọi `readNBytes(2)`, `readNBytes(2)`, `readNBytes(2)`, `readNBytes(2)`. Kết quả là `"HE"`, `"LL"`, `"O"`, mảng rỗng. Giải thích khi nào EOF được phát hiện.

**Bài 2 — Đọc bản ghi có độ dài cố định.** Viết hàm cần đúng 4 byte đầu của một bản ghi. Dùng `byte[] magic = in.readNBytes(4)` và kiểm tra `magic.length == 4`. Nếu thiếu, ném `EOFException` với thông báo có ý nghĩa; không tiếp tục xử lý bản ghi bị cắt ngắn.

**Bài 3 — Chính sách max size.** Chạy `BoundedReadDemo.java`. Thay giới hạn `4` bằng `3` và dự đoán đầu vào nào bị từ chối. Thử trường hợp giới hạn `0` với stream không rỗng. Giải thích vì sao phải đọc `N + 1`.

**Bài 4 — Phân biệt byte và ký tự.** Dùng `"é"` và emoji trong UTF-8. In `text.length()`, `text.codePointCount(0, text.length())` và `text.getBytes(StandardCharsets.UTF_8).length`; giải thích vì sao ba số có thể khác nhau.

**Bài 5 — Mô tả một endpoint tải nội dung.** Nêu cách giới hạn kích thước payload, đặt timeout, đóng stream, xử lý lỗi vượt giới hạn, giới hạn sau giải nén (nếu có), và kiểm tra dữ liệu trước khi xác nhận ghi file. Phân biệt “xem trước” với “chấp nhận toàn bộ”.

### Checklist hoàn thành

- [ ] Biết `InputStream.readNBytes(int)` có từ Java 11 và **trả mảng `byte[]` dài không quá `len`**.
- [ ] Dự đoán đúng hành vi khi `len == 0`, `len < 0` và EOF đến sớm.
- [ ] Phân biệt `read(byte[])` với `readNBytes`, và overload nhận buffer.
- [ ] Hiểu `readNBytes(N)` **không** chứng minh nguồn dài tối đa N byte.
- [ ] Viết được phép kiểm tra quá kích thước bằng `readNBytes(N + 1)` với mức N hữu hạn, an toàn.
- [ ] Không dùng `available()` làm kích thước nội dung và không mặc định `readAllBytes()` an toàn.
- [ ] Dùng `try-with-resources`, xử lý `IOException` và áp timeout phù hợp nguồn dữ liệu.
- [ ] Chọn xử lý theo chunk nếu bài toán không cần lưu toàn bộ payload trong bộ nhớ.

## 13. Tài liệu tham khảo chính thức

1. [Java SE 11 — InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html): hợp đồng của `readNBytes(int)` (Since 11), `readNBytes(byte[], int, int)`, `readAllBytes()`, `read(byte[])`, `available()` và `transferTo`.
2. [Java SE 25 — InputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html): kiểm chứng các API byte stream vẫn hiện diện trong JDK LTS mới hơn.
3. [Java SE 11 — ByteArrayInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/ByteArrayInputStream.html): stream in-memory dùng để kiểm thử không phụ thuộc môi trường.
4. [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `Files.newInputStream` và thao tác tạo/ghi/xóa file mẫu.
5. [Java SE 11 — StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html): các bộ mã hóa ASCII và UTF-8 dùng trong ví dụ.

**Nguyên tắc áp dụng:** `readNBytes(int)` là cách rõ ràng để **đọc tối đa N byte vào một mảng**. Muốn **từ chối toàn bộ nguồn vượt N byte**, hãy kiểm tra **N + 1** trong phạm vi tài nguyên cho phép. Kết hợp giới hạn bộ nhớ với timeout, quản lý stream và kiểm tra byte/encoding để tránh nhầm “đọc có giới hạn” với “đã xác thực dữ liệu an toàn”.