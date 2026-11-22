# InputStream.nullInputStream và nguồn luôn kết thúc trong Java 11

**Chủ đề cha:** Byte stream  
**Năng lực trọng tâm:** Hiểu và sử dụng `InputStream.nullInputStream()` như một nguồn byte rỗng, hợp lệ, lập tức ở trạng thái end-of-stream (EOF). Phân biệt EOF với tham chiếu `null`, thao tác đọc độ dài 0, nguồn chưa có dữ liệu, lỗi I/O và việc đóng stream.

`InputStream.nullInputStream()` là phương thức **static** của `java.io.InputStream`, được thêm trong **Java 11** và vẫn hữu ích trên Java hiện đại. Nó trả về **một đối tượng stream mới, đang mở, không chứa byte nào**. Những lệnh đọc dữ liệu thật sự từ đối tượng này lập tức gặp EOF; không phải chờ dữ liệu xuất hiện sau đó. Đây là lựa chọn rõ nghĩa cho nhánh xử lý được phép có **nguồn đầu vào rỗng**, đặc biệt trong test, pipeline và API vốn nhận `InputStream`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích EOF, `read() == -1` và cách phân biệt stream rỗng với byte có giá trị `0` hoặc một tham chiếu Java `null`.
2. Dự đoán kết quả của `read`, `readNBytes`, `readAllBytes`, `available`, `skip`, `transferTo`, `mark/reset` trên `nullInputStream`.
3. Hiểu việc gọi `close()` thay đổi khả năng sử dụng stream; viết mã `try-with-resources` và kiểm thử lỗi sau khi đóng.
4. Dùng nguồn EOF tức thì trong xử lý tùy chọn và kiểm thử, đồng thời giữ rõ ý nghĩa “không có nguồn”, “nguồn có mặt nhưng rỗng” và “không mở được nguồn”.
5. Viết vòng lặp đọc byte đúng hợp đồng của `InputStream`, không dùng `available() == 0` như điều kiện xác định EOF.
6. Chọn giữa `nullInputStream()`, `ByteArrayInputStream`, `Reader.nullReader()` và `OutputStream.nullOutputStream()` theo loại dữ liệu và hướng truyền.

## 2. EOF là gì và vì sao stream rỗng vẫn là một stream hợp lệ?

`InputStream` trừu tượng hóa **nguồn các byte**. Một phép gọi `read()` trả:

- Một số nguyên trong khoảng **0 đến 255**: đó là một byte được đọc (ví dụ byte `0x00` hợp lệ sẽ cho kết quả `0`).
- **`-1`**: không còn byte nào, tức **end-of-stream** (EOF).
- Ném `IOException`: thao tác đọc không thể hoàn thành do lỗi I/O hoặc trạng thái stream không cho phép.

Một stream rỗng ngay từ đầu hoàn toàn có thể là **nguồn dữ liệu hợp lệ**, miễn là hợp đồng ứng dụng chấp nhận “không có dữ liệu”. `InputStream.nullInputStream()` trả một đối tượng như vậy. Nó khác các trường hợp:

| Trường hợp | Ý nghĩa | Ví dụ hành vi |
|---|---|---|
| `InputStream.nullInputStream()` | Một stream tồn tại, đang mở nhưng không có byte nào | `read()` trả `-1` ngay |
| `InputStream` tham chiếu `null` | Không có đối tượng để gọi phương thức | `stream.read()` ném `NullPointerException` |
| `new ByteArrayInputStream(new byte[0])` | Stream từ mảng byte dài 0 | `read()` trả `-1` khi mở; cách hoạt động khi đóng khác |
| File có dung lượng 0 được mở thành công | Tệp tồn tại, nguồn đọc đã mở, không có nội dung | Đọc sẽ gặp EOF |
| File không tồn tại hoặc thiếu quyền | Không tạo được nguồn hợp lệ | Mở tệp có thể ném `IOException` hoặc lớp con như `NoSuchFileException` |
| Stream đang chờ mạng/pipe | Có thể chưa có byte **ngay lúc này**, nhưng nguồn chưa kết thúc | `read()` có thể chặn hoặc hành xử theo hợp đồng nguồn |
| Stream đã đóng | Vòng đời sử dụng đã kết thúc | Các thao tác đọc thông thường có thể ném `IOException` |

Tên `nullInputStream` đề cập đến **nguồn không có dữ liệu**, **không có nghĩa là Java `null`**. Đây là điểm quan trọng để tránh lạm dụng `null` trong API. Khi một thành phần nhận `InputStream`, nó có thể tiếp tục xử lý hợp đồng stream bình thường mà không cần thêm nhánh `if (in == null)`, **nếu** đầu vào rỗng là hợp lệ theo nghiệp vụ.

Một nguồn EOF tức thì cũng **không phải** nguồn “chưa sẵn sàng”. Khi đã biết không bao giờ có byte nào, lặp đọc mãi để chờ dữ liệu là sai về mô hình.

## 3. Hợp đồng của `InputStream.nullInputStream()`

Khai báo API:

```java
public static InputStream nullInputStream()
```

Phương thức nằm trên `java.io.InputStream` và dùng được từ Java 11 trở lên. Mỗi lần gọi tạo **một stream mới**, ban đầu ở trạng thái **open**; `close()` đóng nó và gọi `close()` lần nữa không gây tác dụng thêm.

Trong trạng thái **đang mở**, bảng sau mô tả hành vi tiêu biểu:

| Phép gọi | Giá trị/trạng thái | Giải thích |
|---|---|---|
| `in.read()` | `-1` | Không có byte đầu tiên |
| `in.read(buffer)`, `buffer.length > 0` | `-1` | EOF với yêu cầu đọc byte |
| `in.read(buffer, off, len)`, `len > 0` hợp lệ | `-1` | Không có byte nào để cấp |
| `in.read(new byte[0])` | `0` | Yêu cầu đọc **0 byte**, không phải phát hiện EOF |
| `in.readAllBytes()` | `new byte[0]` về nội dung | Trả mảng byte rỗng |
| `in.readNBytes(5)` | Mảng byte độ dài `0` | Yêu cầu tối đa 5 byte nhưng không còn dữ liệu |
| `in.readNBytes(buffer, off, len)` | `0` | Kiểu kết quả là **số byte thực sự đọc**, không dùng `-1` cho EOF |
| `in.available()` | `0` | Không có byte sẵn để đọc |
| `in.skip(10)` | `0L` | Không có byte nào để bỏ qua |
| `in.transferTo(out)` | `0L` | Không sao chép byte nào; `out` không nhận dữ liệu từ nguồn này |
| `in.markSupported()` | `false` | Không hỗ trợ đánh dấu/đặt lại vị trí |
| `in.mark(limit)` | Không tác dụng | Không lưu trạng thái |
| `in.reset()` | Ném `IOException` | Không hỗ trợ reset |
| `in.close()` | Đóng stream | Không tạo byte hay EOF event đặc biệt |

**Đừng trộn các quy tắc trả về:** `read()` và `read(buffer)` (với buffer không rỗng) dùng `-1` để báo EOF; `readNBytes(buffer,off,len)` trả **`0`** ở EOF; `readAllBytes()` và `readNBytes(int)` trả **mảng độ dài 0**. Ba hình thức này thể hiện cùng thực tế “không có byte nào”, nhưng có **kiểu trả về và quy ước khác nhau**.

### 3.1 Vì sao `read(new byte[0])` trả 0?

Một lệnh yêu cầu đọc 0 byte không cần nhận dữ liệu, vì thế `read(new byte[0])` có thể trả `0` dù luồng đã ở EOF. Đây là quy tắc quan trọng của `read(byte[])` và `read(byte[],off,len)` cho `len == 0`. Khi viết code kiểm tra EOF, hãy dùng **buffer có dung lượng dương** và điều kiện dừng `-1`.

Đặc biệt, không viết `if (in.read(new byte[0]) == 0)` rồi kết luận “stream rỗng” hay “stream đã kết thúc”: giá trị 0 tại đây xuất phát từ **yêu cầu đọc 0 byte**, không phải từ nội dung nguồn.

### 3.2 Sau khi đóng stream

Với phép đọc dữ liệu thực sự như `read()`, sau `close()`, `nullInputStream` không còn hoạt động như một nguồn mở và sẽ ném `IOException`. `available()` và các thao tác có yêu cầu xử lý dữ liệu cũng được tài liệu API mô tả là lỗi khi nguồn đã đóng. `close()` có thể gọi nhiều lần.

Một số overload với độ dài 0 có đường đi kiểm tra đối số trước khi truy cập trạng thái stream và có thể trả 0; **không dùng thao tác 0 byte để thử xem stream đã đóng hay chưa**. Khi cần kiểm thử vòng đời, chọn một lệnh đọc có yêu cầu dữ liệu, ví dụ `read()`.

`markSupported()` trả `false`; `mark()` không làm gì và `reset()` ném `IOException`. EOF không có nghĩa rằng có thể `reset()` để “đọc lại” nguồn. Một lời gọi **mới** đến `InputStream.nullInputStream()` tạo đối tượng khác, cũng rỗng và ban đầu đang mở.

## 4. Ví dụ 1 — quan sát đầy đủ một nguồn EOF tức thì

Lưu chương trình sau thành **`NullInputStreamDemo.java`**. Chương trình sử dụng API có trong Java 11 và in rõ kết quả của những cách đọc khác nhau.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class NullInputStreamDemo {
    public static void main(String[] args) throws IOException {
        InputStream in = InputStream.nullInputStream();
        byte[] buffer = new byte[4];
        Arrays.fill(buffer, (byte) 7);
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        System.out.println("read()=" + in.read());
        System.out.println("read(buffer)=" + in.read(buffer));
        System.out.println("read(buffer, 1, 2)=" + in.read(buffer, 1, 2));
        System.out.println("read(empty buffer)=" + in.read(new byte[0]));
        System.out.println("readNBytes(buffer)=" + in.readNBytes(buffer, 0, 4));
        System.out.println("readNBytes(4).length=" + in.readNBytes(4).length);
        System.out.println("readAllBytes().length=" + in.readAllBytes().length);
        System.out.println("available()=" + in.available());
        System.out.println("skip(10)=" + in.skip(10));
        System.out.println("markSupported()=" + in.markSupported());
        System.out.println("transferTo(out)=" + in.transferTo(out));
        System.out.println("out.size()=" + out.size());
        System.out.println("buffer unchanged=" +
                Arrays.equals(buffer, new byte[]{7, 7, 7, 7}));

        in.mark(16);
        try {
            in.reset();
            System.out.println("reset(): unexpected success");
        } catch (IOException expected) {
            System.out.println("reset(): IOException");
        }

        in.close();
        in.close();
        try {
            in.read();
            System.out.println("read() after close: unexpected success");
        } catch (IOException expected) {
            System.out.println("read() after close: IOException");
        }
    }
}
```

Biên dịch/chạy bằng JDK 11 hoặc JDK mới hỗ trợ target Java 11:

```bash
javac --release 11 -encoding UTF-8 NullInputStreamDemo.java
java NullInputStreamDemo
```

**Đầu ra chính xác đã kiểm tra:**

```text
read()=-1
read(buffer)=-1
read(buffer, 1, 2)=-1
read(empty buffer)=0
readNBytes(buffer)=0
readNBytes(4).length=0
readAllBytes().length=0
available()=0
skip(10)=0
markSupported()=false
transferTo(out)=0
out.size()=0
buffer unchanged=true
reset(): IOException
read() after close: IOException
```

Từ ví dụ này có năm kết luận:

1. Không có lần đọc nào cung cấp byte. Ba overload `read` có yêu cầu dữ liệu đều gặp EOF `-1`.
2. `read(new byte[0])` trả 0 do độ dài yêu cầu bằng 0; điều này **không phủ nhận** EOF.
3. `readNBytes`/`readAllBytes` biểu diễn đầu ra rỗng bằng độ dài hoặc số byte bằng 0. Buffer ban đầu chứa bốn số 7 vẫn giữ nguyên vì chưa ghi dữ liệu nào vào đó.
4. `transferTo(out)` không ghi byte và trả 0. Nó không tự đóng `out`.
5. `reset()` không hỗ trợ; sau khi đóng, `read()` ném `IOException` dù trước đó nguồn luôn chỉ có EOF.

Ở ứng dụng thật, hãy dùng `try-with-resources` khi stream thuộc quyền sở hữu của phương thức. Ví dụ dùng `close()` tường minh chỉ để minh họa sự thay đổi vòng đời.

## 5. Viết vòng lặp đọc byte đúng khi nguồn đã ở EOF

Mẫu đọc thông dụng của `InputStream`:

```java
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    // Xử lý buffer[0] tới buffer[count - 1].
}
```

Đây là **trích đoạn** bên trong phương thức khi biến `input` đã là một `InputStream` được mở và xử lý/khai báo `IOException`. Với `InputStream.nullInputStream()`, lần `read(buffer)` đầu tiên trả `-1`, nên thân vòng lặp **không chạy**.

Một phiên bản tự đóng nguồn:

```java
static long countBytes(InputStream source) throws IOException {
    long total = 0L;
    byte[] buffer = new byte[8192];
    try (InputStream in = source) {
        int read;
        while ((read = in.read(buffer)) != -1) {
            total = Math.addExact(total, read);
        }
    }
    return total;
}
```

Đây là phương thức minh họa cần đặt trong class, import `java.io.InputStream` và `java.io.IOException`. Hàm sở hữu/đóng `source`: chỉ chọn hợp đồng này nếu người gọi đã chuyển quyền sở hữu stream. `Math.addExact` giúp phát hiện tràn bộ đếm `long` (dù cực hiếm trong một ví dụ nhỏ).

**Điểm cần chú ý:**

- `read(byte[])` trả số byte mới nhận, **không nhất thiết đọc đầy buffer** cho nguồn bình thường. Khi có dữ liệu, xử lý đúng phạm vi `0..count-1`.
- `read()` trả `int` 0..255 khi có byte. Giá trị **0** có thể là một byte `0x00` thật, không phải EOF.
- Dùng buffer độ dài dương. Việc liên tục yêu cầu đọc 0 byte sẽ không giúp nguồn tiến tới EOF.
- Với stream đặc biệt có thể có hành vi khác, cần tôn trọng hợp đồng cụ thể của nó; đừng tự biến `0` thành `-1` hoặc ném lỗi chỉ vì “chưa đọc được byte nào”.

### 5.1 Không dùng `available()` làm điều kiện kết thúc

`available()` ước lượng số byte có thể đọc **mà không chặn**. `available() == 0` không chứng minh tất cả dữ liệu đã hết trên mọi `InputStream`. Một nguồn hợp lệ có thể trả 0 nhưng vẫn có byte khi gọi `read()` sau đó.

Trong `InputStream.nullInputStream()`, `available()` luôn là 0 khi mở, nhưng đó là hành vi đặc biệt của **nguồn rỗng**. Không suy rộng ra `SocketInputStream`, pipe hay các loại stream khác.

**Ví dụ sai:**

```java
while (input.available() > 0) {
    process(input.read());
}
```

Đoạn trên chỉ minh họa lỗi, **không phải chương trình chạy độc lập**: nó có thể bỏ sót dữ liệu của một nguồn mà `available() == 0` tại thời điểm kiểm tra. Sử dụng vòng lặp `read() != -1` hoặc cơ chế đọc theo giao thức tương ứng.

### 5.2 Demo khác biệt giữa “available bằng 0” và EOF

Lưu thành **`AvailableDoesNotMeanEof.java`**:

```java
import java.io.InputStream;

public class AvailableDoesNotMeanEof {
    public static void main(String[] args) throws Exception {
        try (InputStream source = new InputStream() {
            private boolean consumed = false;

            @Override
            public int read() {
                if (consumed) return -1;
                consumed = true;
                return 65; // byte của ký tự ASCII 'A'
            }
        }) {
            System.out.println("available=" + source.available());
            System.out.println("first=" + source.read());
            System.out.println("second=" + source.read());
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 AvailableDoesNotMeanEof.java
java AvailableDoesNotMeanEof
```

```text
available=0
first=65
second=-1
```

`InputStream` ẩn danh chỉ override `read()`, còn `available()` dùng implementation mặc định là 0. Tuy vậy, lần đọc đầu thực sự trả byte 65. Đây là minh họa gọn của lý do `available()` không phải API phát hiện EOF tổng quát.

## 6. Ứng dụng thực tế: nguồn mặc định không có dữ liệu

Một API đã nhận `InputStream` có thể không cần nhánh null nếu việc **không có payload** được quy định là trường hợp hợp lệ. Ví dụ:

- Một bước xử lý tệp **tùy chọn**: khi không có tệp được yêu cầu, phần xử lý phía sau được phép nhận nguồn rỗng và xử lý thành công.
- Kiểm thử parser hoặc consumer phải xử lý trường hợp nguồn vào 0 byte.
- Pipeline gửi dữ liệu cho hàm copy, tính dung lượng hoặc parse stream, khi muốn xác minh hành vi EOF tức thì.
- Sử dụng như đầu vào mặc định cho một thành phần luôn nhận `InputStream`, nhưng chỉ khi mô tả nghiệp vụ **không đòi phân biệt** nguyên nhân thiếu payload.

**Không dùng nguồn rỗng để che lỗi:** nếu người dùng yêu cầu đọc tệp bắt buộc, tệp không tồn tại hoặc quyền truy cập bị từ chối phải được báo lỗi đúng nghĩa. Tự thay mọi `IOException` thành `InputStream.nullInputStream()` sẽ tạo thành công giả và có thể làm mất dữ liệu hoặc khiến kết quả nghiệp vụ sai.

### 6.1 Ví dụ 2 — dùng stream rỗng cho payload được phép vắng mặt

Ví dụ sau cố ý chọn chính sách “payload vắng mặt có thể được tiêu thụ như 0 byte”. Nó giữ `Optional<byte[]>` ở **biên đầu vào** để diễn đạt rằng payload có thể vắng mặt; trong phương thức tạo stream, trạng thái `Optional.empty()` được chuyển thành nguồn EOF tức thì.

Lưu thành **`OptionalSourceDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

public class OptionalSourceDemo {
    static InputStream source(Optional<byte[]> payload) {
        return payload.<InputStream>map(ByteArrayInputStream::new)
                .orElseGet(InputStream::nullInputStream);
    }

    static String consume(Optional<byte[]> payload) throws IOException {
        try (InputStream in = source(payload);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            long bytes = in.transferTo(out);
            String text = new String(
                    out.toByteArray(), StandardCharsets.UTF_8);
            return "bytes=" + bytes + ", text=[" + text + "]";
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("missing: " + consume(Optional.empty()));
        System.out.println("present-empty: " + consume(Optional.of(new byte[0])));
        System.out.println("present-text: " + consume(
                Optional.of("Java".getBytes(StandardCharsets.UTF_8))));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 OptionalSourceDemo.java
java OptionalSourceDemo
```

**Kết quả chính xác:**

```text
missing: bytes=0, text=[]
present-empty: bytes=0, text=[]
present-text: bytes=4, text=[Java]
```

Vì sao hai dòng đầu giống nhau? Sau khi đã đưa vào tầng tiêu thụ `InputStream` và chỉ đo số byte, **không thể suy lại** payload ban đầu vắng mặt hay có mặt nhưng có mảng độ dài 0. Sự khác biệt vẫn tồn tại trong `Optional<byte[]>` trước khi chuyển đổi; nếu nghiệp vụ cần phân biệt, **giữ trạng thái đó trong kết quả hoặc metadata**, không chỉ trả về stream rỗng.

`transferTo(OutputStream)` là API có từ Java 9, vẫn dùng trong Java 11 và các bản sau. Trong ví dụ này, nó đọc hết nguồn rồi ghi sang `ByteArrayOutputStream`; với nguồn rỗng, trả 0 ngay. `ByteArrayOutputStream` phù hợp ví dụ nhỏ; với dữ liệu lớn, nên xử lý bằng streaming thật để không giữ toàn bộ nội dung trong bộ nhớ.

### 6.2 Phân biệt nguồn rỗng hợp lệ với lỗi mở nguồn

Giả sử người dùng cung cấp đường dẫn bắt buộc, cách xử lý phải để lộ lỗi mở file:

```java
try (InputStream in = Files.newInputStream(path)) {
    consumeRequiredFile(in);
}
```

Đây là **trích đoạn**, cần import `java.io.InputStream`, `java.nio.file.Files`, khai báo `path` kiểu `Path` và phương thức `consumeRequiredFile`. Nếu `path` không tồn tại, `Files.newInputStream` có thể ném `NoSuchFileException`. Không nên thay lỗi bằng nguồn rỗng nếu hệ thống cần thông báo “không tìm thấy tệp”.

Nếu luồng nghiệp vụ cho phép đầu vào tùy chọn, hãy chọn fallback tại điểm đã xác định **rằng vắng mặt là hợp lệ**:

```java
InputStream input = optionalPath.isPresent()
        ? Files.newInputStream(optionalPath.get())
        : InputStream.nullInputStream();
```

Đây cũng là **trích đoạn**, với `optionalPath` là `Optional<Path>`. Nhánh có path **vẫn giữ lỗi thật** khi mở tệp. Trong code dự án nên ưu tiên cơ chế điều phối/khai báo biến tránh dùng `get()` tùy tiện, hoặc xử lý `Optional` qua `map`/`orElseGet` khi không có checked exception; mục tiêu ở đây là mô tả ranh giới hành vi, không đưa ra một tiện ích API hoàn chỉnh.

## 7. Kiểm thử các consumer của `InputStream`

Nguồn luôn EOF rất hữu ích để chứng minh consumer xử lý được trường hợp không có byte, không gọi parser hoặc xử lý giả định rằng luôn có ít nhất một byte.

**Một bộ test hợp đồng nên bao gồm:**

| Ca kiểm thử | Đầu vào | Điều cần xác minh |
|---|---|---|
| EOF ngay | `InputStream.nullInputStream()` | Consumer trả kết quả cho dữ liệu rỗng, không lặp vô hạn |
| Byte 0 thật | `new ByteArrayInputStream(new byte[]{0})` | Không nhầm `0` thành `-1` |
| Có dữ liệu | `new ByteArrayInputStream(new byte[]{1, 2, 3})` | Đọc đủ ba byte theo hợp đồng |
| Source rỗng dạng mảng | `new ByteArrayInputStream(new byte[0])` | Dữ liệu rỗng có thể đến từ nguồn khác null stream |
| EOF sau dữ liệu | Mảng có byte rồi hết | Dừng chính xác ở `-1`, không đọc thêm |
| Chỉ yêu cầu 0 byte | `read(new byte[0])` | Phân biệt giá trị `0` với EOF `-1` |
| Đóng stream | `nullInputStream` sau `close()` | Thao tác đọc thực sự ném `IOException` |
| Lỗi I/O | Fake stream ném `IOException` khi `read` | Không lặng lẽ coi lỗi là EOF |
| Ngắn hơn mong đợi | Nguồn có ít byte hơn số byte ứng dụng yêu cầu | Tùy hợp đồng: báo thiếu dữ liệu hoặc xử lý phần đã có |

**Không dùng `nullInputStream()` để test mọi hành vi streaming**: nó không mô phỏng đọc từng phần, byte ngắt quãng, timeout, mạng gián đoạn, buffer nửa đầy hoặc lỗi giữa chừng. Với những trường hợp đó, dùng stream giả lập hành vi cụ thể, `ByteArrayInputStream` có nội dung hoặc nguồn kiểm thử phù hợp.

### 7.1 Tự kiểm tra nhanh các kết quả cần nhớ

Đoạn chương trình đầy đủ ở mục 4 đã kiểm tra nhiều phương thức trên cùng một đối tượng. Khi viết test tự động, nên tách từng hành vi thành ca độc lập và **tạo stream mới cho mỗi ca** khi việc đóng/đọc có thể làm thay đổi trạng thái.

Ví dụ JUnit Jupiter (**trích đoạn test**, cần JUnit trên test classpath; không thuộc Java standard library):

```java
@Test
void emptySourceImmediatelyReturnsEof() throws IOException {
    try (InputStream in = InputStream.nullInputStream()) {
        assertEquals(-1, in.read());
        assertEquals(0, in.readAllBytes().length);
    }
}
```

Cần import `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.assertEquals`, `java.io.InputStream` và `java.io.IOException`. Dùng phiên bản JUnit tương thích với runtime/build của dự án. Nếu không có framework test, ví dụ Java 11 độc lập ở mục 4 vẫn cung cấp kết quả kiểm chứng.

### 7.2 Phân biệt hợp đồng “rỗng” và “thất bại”

Một parser có thể chọn một trong những cách sau khi gặp EOF ngay:

1. Trả collection rỗng hoặc `Optional.empty()` nếu dữ liệu đầu vào là **tùy chọn**.
2. Trả một giá trị mặc định do nghiệp vụ chỉ định.
3. Ném lỗi validation/parse có ý nghĩa nếu input **bắt buộc có dữ liệu**.

`InputStream.nullInputStream()` **không quyết định** cách xử lý nghiệp vụ nào đúng. Nó chỉ làm đầu vào có **0 byte**, để consumer thực thi quy tắc của chính mình. Test nên kiểm tra kết quả đúng theo đặc tả, không mặc định “EOF tức thì nghĩa là xử lý thành công”.

## 8. So sánh với các API gần nghĩa vẫn được sử dụng

| API | Hướng / loại dữ liệu | Khi sử dụng | Khác biệt chính |
|---|---|---|---|
| `InputStream.nullInputStream()` | Đầu vào byte | Muốn nguồn luôn EOF | `read()` trả `-1` khi mở |
| `new ByteArrayInputStream(new byte[0])` | Đầu vào byte từ mảng | Muốn stream từ dữ liệu có sẵn, kể cả mảng rỗng | Có trạng thái vùng đệm; `close()` không có tác dụng như null stream |
| `new ByteArrayInputStream(bytes)` | Đầu vào byte từ mảng | Test vài byte thật, kể cả byte `0x00` | Đọc được nội dung rồi mới EOF |
| `Reader.nullReader()` | Đầu vào **ký tự** | API cần `Reader` luôn EOF | Đọc char thay vì byte; cũng có từ Java 11 |
| `OutputStream.nullOutputStream()` | **Đầu ra** byte | Muốn bỏ dữ liệu được ghi mà không lưu | `write(...)` chấp nhận rồi loại bỏ byte; không thể dùng như nguồn đọc |
| `Files.newInputStream(path)` | Đầu vào byte từ file | Đọc tệp thực | I/O thật, có thể lỗi mở/đọc và cần đóng |
| `InputStreamReader(in, charset)` | Cầu nối byte → ký tự | Cần giải mã stream theo charset cụ thể | Bản thân không tạo nguồn dữ liệu |

**Nguồn rỗng và đích bỏ dữ liệu là hai chiều khác nhau.** `InputStream.nullInputStream()` làm consumer **không nhận byte nào**; `OutputStream.nullOutputStream()` cho producer ghi byte nhưng không giữ lại. Có thể dùng cặp này để kiểm thử API chuyển byte, nhưng nó không đo lường nội dung file thực và không chứng minh một kết nối mạng sẽ hoạt động.

`ByteArrayInputStream` có thể đủ khi bạn cần test bằng mảng rỗng hoặc dữ liệu cụ thể. Tuy nhiên, `nullInputStream()` diễn đạt ý định rất rõ: “Đây là nguồn byte luôn kết thúc, không cần cấp mảng làm dữ liệu nền”.

### 8.1 Đọc ký tự từ nguồn byte rỗng

Ví dụ về cơ chế:

```java
try (var reader = new InputStreamReader(
        InputStream.nullInputStream(), StandardCharsets.UTF_8)) {
    System.out.println(reader.read()); // -1
}
```

Đây là **trích đoạn** trong phương thức có khai báo/xử lý `IOException`, cần import `InputStream`, `InputStreamReader` và `StandardCharsets`. Khi đã biết API nhận `Reader`, `Reader.nullReader()` có thể diễn đạt ý định trực tiếp hơn. Đối với chuỗi rỗng đã có sẵn, `new StringReader("")` cũng là một lựa chọn phù hợp.

## 9. Các hiểu nhầm và lỗi thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
|---|---|---|
| `nullInputStream()` trả Java `null` | Nó trả đối tượng `InputStream` mới | Có thể gọi phương thức của đối tượng khi đang mở |
| EOF là byte `0` | Byte `0x00` là dữ liệu hợp lệ | Với `read()`, EOF là **`-1`** |
| `read(buffer) == 0` lúc nào cũng có nghĩa EOF | Yêu cầu 0 byte có thể trả 0 | Dùng buffer dương, dừng khi `-1` |
| `readNBytes(buffer,off,len) == -1` khi EOF | API này trả **số byte đã đọc**, 0 ở EOF | Kiểm tra `count == 0` theo ngữ cảnh |
| `readAllBytes()` của null stream là `null` | Trả mảng byte rỗng | Kiểm tra `bytes.length == 0` |
| `available() == 0` nghĩa là EOF với mọi stream | Chỉ là ước lượng số byte đọc không chặn | Dựa vào kết quả `read`/giao thức |
| Stream rỗng chưa có byte thì “chờ thêm” | `nullInputStream()` luôn ở EOF | Dùng nguồn bất đồng bộ/stream thật nếu dữ liệu sẽ đến sau |
| `reset()` sẽ quay lại đầu | `markSupported() == false` | Không gọi reset; tạo nguồn mới nếu cần |
| Sau `close()` vẫn có thể đọc `-1` mãi | Nguồn đã đóng; thao tác đọc thật sự ném `IOException` | Quản lý vòng đời qua `try-with-resources` |
| Đổi mọi lỗi mở file thành null stream | Che mất lỗi tệp/permission, trả kết quả thành công giả | Chỉ fallback khi input vắng mặt được hợp đồng cho phép |
| Input stream và output stream rỗng tương đương | Một bên đọc EOF, bên kia bỏ dữ liệu ghi | Dùng đúng `nullInputStream`/`nullOutputStream` |
| Một lần đọc trả `-1` thì có thể dùng lại nguồn cho dữ liệu mới | EOF của null stream là vĩnh viễn | Tạo nguồn khác nếu có nội dung mới |
| `transferTo` trả 0 là lỗi | Với nguồn rỗng, truyền 0 byte là hợp lệ | Kết hợp hợp đồng và yêu cầu tối thiểu về kích thước nếu có |

## 10. Tình huống ra quyết định

**Tình huống A — một request HTTP có body tùy chọn.** Nếu thành phần nhận đầu vào byte và **body không có** là trạng thái được phép, có thể chuyển một nguồn EOF tức thì vào tầng xử lý. Nếu body là bắt buộc theo schema, bộ kiểm tra dữ liệu phải báo thiếu input; không được giả sử nguồn rỗng luôn hợp lệ.

**Tình huống B — test việc copy stream.** Truyền `InputStream.nullInputStream()` vào hàm copy rồi xác nhận số byte sao chép bằng 0 và output không đổi. Bổ sung test với nguồn có byte để biết hàm không chỉ “trả 0 cho mọi input”.

**Tình huống C — mở đường dẫn cấu hình bắt buộc.** `Files.newInputStream(path)` ném lỗi khi không tìm thấy; fallback thành EOF sẽ làm chương trình trông như có cấu hình rỗng. Cần ưu tiên thông báo lỗi và chính sách mặc định rõ ràng.

**Tình huống D — consumer xử lý byte stream qua mạng.** Khi `available()` trả 0, không kết luận kết nối đã đóng. Đọc theo hợp đồng mạng/timeout và phát hiện EOF qua `read() == -1` hoặc protocol framing; null stream chỉ mô phỏng **EOF tức thì**, không mô phỏng độ trễ hay kết nối mạng.

**Tình huống E — cần xử lý văn bản Unicode.** `InputStream` đưa ra byte thô, không phải ký tự; nếu logic cần ký tự, chọn `Reader` hoặc giải mã bằng charset tường minh. Nguồn byte rỗng vẫn có thể được giải mã thành nguồn ký tự rỗng, nhưng không có nghĩa một byte đơn lẻ tương ứng một ký tự Unicode trong mọi encoding.

## 11. Bài tập có đáp án

**Bài 1 — dự đoán giá trị.** Với `InputStream in = InputStream.nullInputStream();`, các lệnh `in.read()`, `in.read(new byte[8])`, `in.read(new byte[0])` và `in.readNBytes(new byte[8],0,8)` trả gì?  
**Đáp án:** lần lượt `-1`, `-1`, `0`, `0`. Lệnh cuối trả số byte đã đọc, không dùng `-1` làm sentinel.

**Bài 2 — byte 0 và EOF.** Với `new ByteArrayInputStream(new byte[]{0})`, hai lần `read()` đầu trả gì?  
**Đáp án:** `0` rồi `-1`. Đây là lý do không dùng `0` để báo EOF khi đọc từng byte.

**Bài 3 — vòng lặp.** Vì sao `while (in.available() > 0)` không phải cách đọc đến EOF?  
**Đáp án:** `available()` chỉ là ước lượng byte có thể đọc ngay, có thể bằng 0 dù còn dữ liệu; dùng `read() == -1` hoặc protocol framing để xác định kết thúc.

**Bài 4 — vòng đời.** Sau khi gọi `close()` trên null stream, `in.read()` trả `-1` hay ném lỗi?  
**Đáp án:** ném `IOException` khi yêu cầu đọc. Trạng thái đóng khác với trạng thái EOF của nguồn đang mở.

**Bài 5 — điều hướng lỗi.** Ứng dụng phải đọc file cấu hình bắt buộc, nhưng `Files.newInputStream` ném `NoSuchFileException`. Có nên trả `InputStream.nullInputStream()` để chạy tiếp không?  
**Đáp án:** không nếu thiếu cấu hình là lỗi. Chỉ làm vậy khi yêu cầu sản phẩm định nghĩa rõ “không có tệp” là hợp lệ và các tầng tiếp theo được thiết kế để xử lý nguồn rỗng.

**Bài 6 — mất thông tin.** Một hàm dùng `Optional<byte[]>`, trong nhánh vắng mặt tạo null stream. Tầng downstream chỉ đếm byte rồi trả `0`. Có thể kết luận payload “vắng mặt” không?  
**Đáp án:** không. Payload có mặt nhưng dài 0 cũng cho `0`. Muốn phân biệt phải bảo toàn trạng thái có/vắng mặt riêng trong kết quả hoặc hợp đồng API.

**Bài 7 — chiều dữ liệu.** Dùng phương thức nào để cung cấp “nguồn không có byte”, và phương thức nào để bỏ byte được ghi?  
**Đáp án:** `InputStream.nullInputStream()` cho nguồn đầu vào và `OutputStream.nullOutputStream()` cho đích đầu ra.

## 12. Tài liệu chính thức còn giá trị tra cứu

- [Java SE 11 — InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html): hợp đồng `nullInputStream`, `read`, `readAllBytes`, `readNBytes`, `available`, `skip`, `transferTo`, `mark/reset` và `close`.
- [Java SE 11 — ByteArrayInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/ByteArrayInputStream.html): nguồn dữ liệu trong mảng byte, bao gồm mảng rỗng.
- [Java SE 11 — OutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/OutputStream.html): `nullOutputStream` cho trường hợp bỏ dữ liệu được ghi.
- [Java SE 11 — Reader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/Reader.html): `nullReader` cho nguồn ký tự rỗng.
- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): mở nguồn file thực và các lỗi I/O cần xử lý.
- [Java SE 11 — Optional](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html): biểu diễn dữ liệu có thể vắng mặt mà không trộn với stream rỗng.

**Nguyên tắc áp dụng:** `InputStream.nullInputStream()` mô tả một **nguồn byte đang mở nhưng kết thúc ngay**. Hãy dùng nó khi 0 byte là kết quả hợp lệ và mong muốn. Đọc đến EOF bằng quy ước của từng API, giữ riêng trạng thái “vắng mặt” nếu nghiệp vụ cần, và tuyệt đối không dùng nguồn rỗng để che lỗi thật.