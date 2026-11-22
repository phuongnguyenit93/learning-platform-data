# Java 11+ — Ứng dụng Byte Stream trong kiểm thử, adapter và xử lý dữ liệu tùy chọn

## 1. Bối cảnh: byte stream và tình huống cần “nguồn rỗng” hoặc “đích bỏ qua”

Java dùng `InputStream` để đọc **byte** từ một nguồn, và `OutputStream` để ghi **byte** đến một đích. API làm việc với byte, không tự biết dữ liệu đó là văn bản UTF-8, ảnh, tệp nén hay dữ liệu nhị phân.

Trong ứng dụng thực tế có ba tình huống phổ biến:

- **Kiểm thử:** cần cấp dữ liệu vào một hàm hoặc quan sát byte mà hàm tạo ra, không phụ thuộc tệp, mạng hay dịch vụ ngoài.
- **Adapter:** thành phần xử lý cần một `InputStream`/`OutputStream` không `null`, nhưng một số cấu hình có thể không cung cấp nguồn hoặc không cần lưu đầu ra.
- **Dữ liệu tùy chọn:** vắng dữ liệu **được đặc tả là hợp lệ** và có thể được diễn giải thành luồng 0 byte; hoặc đầu ra được chủ ý vô hiệu hóa và có thể bỏ qua.

Từ **Java 11**, hai phương thức trong JDK giải quyết trực tiếp hai trường hợp sau:

```java
InputStream empty = InputStream.nullInputStream();
OutputStream discard = OutputStream.nullOutputStream();
```

Tên chứa từ “null” nhưng cả hai lệnh đều trả về **đối tượng stream thật**, không phải tham chiếu Java `null`. Chúng vẫn có hợp đồng về đọc/ghi, trạng thái mở/đóng và ngoại lệ. Các phương thức này tiếp tục có trong Java hiện đại.

## 2. Phân biệt hai loại no-op stream

| API | Hành vi khi đang mở | Ứng dụng đúng |
| --- | --- | --- |
| `InputStream.nullInputStream()` | Nguồn không có byte; `read()` trả `-1` (EOF), `readAllBytes()` trả mảng byte rỗng, `transferTo(out)` trả `0`. | Nguồn mặc định cho trường hợp “không có dữ liệu đầu vào”. |
| `OutputStream.nullOutputStream()` | Các lệnh `write(...)` nhận byte nhưng **bỏ toàn bộ**, không lưu vào đĩa hoặc bộ nhớ đích; `flush()` không làm gì. | Đích mặc định khi tác vụ được chủ ý chạy ở chế độ bỏ kết quả. |

Mỗi lần gọi phương thức factory tạo **stream mới** và ban đầu đang mở. `close()` có thể được gọi nhiều lần; với null input, các thao tác đọc sau khi đóng ném `IOException`; với null output, các thao tác ghi sau khi đóng cũng ném `IOException`. Không dùng lại một stream đã đóng như thể nó là nguồn/đích bất biến.

Ví dụ nhỏ (cần `java.io.*` và xử lý `IOException`):

```java
try (InputStream input = InputStream.nullInputStream()) {
    System.out.println(input.read());           // -1: không còn byte
    System.out.println(input.readAllBytes().length); // 0
}

try (OutputStream output = OutputStream.nullOutputStream()) {
    output.write(new byte[] {10, 20, 30});  // ghi thành công, 3 byte bị bỏ
}
```

Chú ý: `read(new byte[0])` trả `0` vì bộ đệm yêu cầu độ dài 0; đừng diễn giải mệnh đề “đọc trên luồng rỗng trả EOF” thành “mọi lệnh `read` đều phải trả `-1`” khi yêu cầu đọc 0 byte.

**Không dùng `available() == 0` làm dấu hiệu chắc chắn hết dữ liệu** đối với một `InputStream` bất kỳ: nhiều nguồn có thể chưa có byte sẵn để đọc ngay nhưng vẫn còn dữ liệu về sau. `InputStream.nullInputStream()` thì thực sự EOF ngay từ đầu theo hợp đồng của chính factory đó.

## 3. Kiểm thử byte stream: rỗng, ghi nhận byte và bỏ qua byte

Trong test, nên chọn stream theo thứ cần khẳng định:

| Câu hỏi kiểm thử | Công cụ phù hợp | Điều có thể xác minh |
| --- | --- | --- |
| Hàm hoạt động ra sao khi **không có byte đầu vào**? | `InputStream.nullInputStream()` | Kết thúc ở EOF, không phát sinh bản ghi/byte đầu ra. |
| Hàm xử lý **đúng nội dung đầu vào xác định trước**? | `ByteArrayInputStream(expectedBytes)` | Truyền các byte có thể lặp lại, không cần tệp hay mạng. |
| Hàm tạo ra **đúng byte theo đúng thứ tự**? | `ByteArrayOutputStream` | Đọc `toByteArray()` và so sánh byte thực tế với byte mong đợi. |
| Muốn chạy nhánh xử lý byte nhưng **không giữ kết quả**? | `OutputStream.nullOutputStream()` | Đảm bảo code xử lý và gửi dữ liệu đến sink có thể chạy; không thể kiểm tra dữ liệu sink đã lưu. |

`ByteArrayInputStream` và `ByteArrayOutputStream` là những công cụ vẫn phù hợp cho kiểm thử hiện nay: chạy trong bộ nhớ, dễ tái tạo dữ liệu và không cần thiết lập hệ thống bên ngoài. `nullOutputStream()` **không thay thế** `ByteArrayOutputStream` trong test cần kiểm chứng nội dung: toàn bộ byte được gửi đến null output đã bị bỏ.

Với API `InputStream.transferTo(OutputStream)`, giá trị trả về là **số byte được chuyển từ nguồn sang đích**, kể cả khi đích là `nullOutputStream()`. Ví dụ:

```java
byte[] data = "HELLO".getBytes(StandardCharsets.UTF_8);

try (InputStream src = new ByteArrayInputStream(data);
     OutputStream dst = OutputStream.nullOutputStream()) {
    long count = src.transferTo(dst); // 5 byte đã được chuyển cho sink
    // Không có tệp hoặc buffer đầu ra nào chứa "HELLO" ở đây.
}
```

Vì vậy `count == 5` **không chứng minh dữ liệu đã được lưu** hoặc truyền đến hệ thống bên ngoài. Trong test khẳng định nội dung, hãy so sánh `ByteArrayOutputStream.toByteArray()`. Trong test hiệu năng, null output chỉ loại trừ chi phí lưu đầu ra, không mô phỏng trung thực độ trễ tệp hay mạng.

## 4. Adapter: thay thế luồng tùy chọn bằng một stream hợp lệ

Giả sử tầng xử lý có hợp đồng:

```java
long process(InputStream source, OutputStream destination) throws IOException
```

Tầng đó luôn yêu cầu hai tham số **không null**. Trong khi đó, tầng tích hợp có thể tìm được hoặc không tìm được một nguồn byte.

Khi hợp đồng nghiệp vụ quy định **“không có nguồn” tương đương “nguồn rỗng”**, adapter có thể chọn:

```java
// Giả sử mayHaveInput là Optional<InputStream>.
InputStream source = mayHaveInput.orElseGet(InputStream::nullInputStream);
```

Sử dụng `orElseGet` cho phép tạo stream dự phòng **chỉ khi Optional rỗng**. `orElse(InputStream.nullInputStream())` cũng cho kết quả đúng trong ví dụ đơn giản nhưng sẽ gọi factory tạo stream không dùng đến ngay cả khi đã có dữ liệu. Với tài nguyên thực tế, việc tạo dự phòng sớm có thể gây tác dụng phụ không cần thiết.

Không nên biến mọi dữ liệu vắng mặt thành chuỗi byte rỗng. Các trạng thái sau có ý nghĩa khác nhau:

- **Nguồn tùy chọn vắng mặt:** là kết quả hợp lệ nếu API quy định vậy; có thể dùng `nullInputStream()`.
- **Nguồn được cung cấp nhưng tệp thực tế có 0 byte:** cũng có thể trả EOF ngay, nhưng trạng thái *có nguồn* vẫn khác *vắng nguồn* về nghiệp vụ.
- **Nguồn bắt buộc bị thiếu, lỗi mở tệp, lỗi mạng hoặc lỗi quyền truy cập:** phải báo lỗi tương ứng; không được âm thầm thay bằng `nullInputStream()` vì sẽ che giấu lỗi.
- **Không có đầu ra vì tính năng được chủ ý vô hiệu hóa:** có thể chọn `nullOutputStream()`, nhưng không được dùng để nuốt lỗi từ đầu ra bắt buộc.

Nếu cần phân biệt “không được gửi dữ liệu” với “đã gửi một payload rỗng”, hãy **giữ riêng thông tin presence** (ví dụ `Optional` hoặc cờ nghiệp vụ). Sau khi cả hai đã biến thành cùng một stream 0 byte, code xử lý thuần byte không thể tự khôi phục ý nghĩa đó.

## 5. Quyền sở hữu stream và tác dụng của `transferTo`

Các stream là tài nguyên có vòng đời, nhất là khi bọc tệp, socket hay kết nối từ nơi khác. `InputStream.transferTo(out)` **không tự đóng** nguồn hay đích; chính người thiết kế API phải định rõ ai đóng.

Có hai hợp đồng hợp lệ, tùy ứng dụng:

1. **Adapter nhận quyền sở hữu nguồn:** adapter có thể dùng `try (InputStream in = ...)`, đóng nguồn sau khi chuyển dữ liệu, kể cả khi có lỗi. Đích vẫn do caller quản lý.
2. **Caller giữ quyền sở hữu nguồn:** adapter chỉ sử dụng stream và **không đóng nó**; caller đóng ở ranh giới ngoài. Không nên áp dụng `try-with-resources` bên trong adapter nếu caller còn cần dùng stream đó.

Ví dụ ở mục 7 chọn hợp đồng thứ nhất và đặt tên `forwardOwned` để thể hiện rõ. Dù dùng `nullInputStream()` thì nên đối xử với stream như tài nguyên có vòng đời. Đừng giữ một singleton `nullInputStream()` đã bị đóng để chia sẻ cho nhiều lời gọi.

Nếu xảy ra `IOException` giữa chừng khi chuyển dữ liệu, một phần byte có thể đã tới đích. Việc bắt ngoại lệ rồi chuyển sang null stream giữa tác vụ sẽ làm kết quả không nhất quán. Hãy báo lỗi và đóng tài nguyên theo hợp đồng của ứng dụng.

## 6. Tùy chọn đầu ra: khi nào dùng `nullOutputStream()`

Khi một luồng xử lý luôn ghi byte nhưng việc **lưu đầu ra** là tùy chọn (ví dụ xuất bản debug được bật/tắt), tầng cấu hình có thể cấp một đích thực hoặc đích bỏ dữ liệu:

```java
// Minh họa trong phương thức có throws IOException.
// enabled và targetPath được xác định từ cấu hình ứng dụng.
try (OutputStream destination = enabled
        ? Files.newOutputStream(targetPath)
        : OutputStream.nullOutputStream()) {
    input.transferTo(destination);
}
```

Đoạn trên yêu cầu import `java.io.InputStream`, `java.io.OutputStream`, `java.io.IOException` và `java.nio.file.Files`. `input` là nguồn được quản lý riêng, không bị đóng bởi `transferTo`. Khi `enabled == false`, không mở `targetPath` và byte đầu ra sẽ bị bỏ theo chủ ý; khi `enabled == true`, lỗi mở/ghi tệp vẫn được báo.

Hãy đặt tên cấu hình và phương thức rõ ý định (ví dụ `discardOutput` hoặc `outputEnabled`) thay vì đặt mặc định “ghi đi đâu đó” rồi âm thầm bỏ dữ liệu. `nullOutputStream()` phù hợp với debug tùy chọn, đo đường đi của xử lý hoặc chạy dry run mà đặc tả cho phép không lưu; không phù hợp với lưu bản ghi giao dịch, ghi audit bắt buộc hay kết quả cần bảo toàn.

**Không phụ thuộc vào `flush()` để biết dữ liệu đã lưu:** đối với `nullOutputStream()`, `flush()` đơn giản là no-op. Chỉ kiểm chứng việc xuất dữ liệu thực bằng một đích có thể quan sát và bằng điều kiện thành công do API đích cung cấp.

## 7. Ví dụ Java 11+ hoàn chỉnh: kiểm thử, adapter, nguồn vắng và đích bỏ dữ liệu

Lưu chính xác vào tệp **`ByteStreamOptionalDemo.java`**. Ví dụ không mở tệp/mạng, dùng dữ liệu xác định trước và in stdout ổn định:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.Optional;

public final class ByteStreamOptionalDemo {
    /**
     * Consumes and closes the supplied input when present.
     * The destination is owned by the caller and is not closed here.
     */
    static long forwardOwned(Optional<InputStream> maybeInput, OutputStream destination)
            throws IOException {
        Objects.requireNonNull(maybeInput, "maybeInput");
        Objects.requireNonNull(destination, "destination");
        try (InputStream input = maybeInput.orElseGet(InputStream::nullInputStream)) {
            return input.transferTo(destination);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] payload = "HELLO".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream captured = new ByteArrayOutputStream();
        long copied = forwardOwned(
                Optional.of(new ByteArrayInputStream(payload)), captured);
        System.out.println("present-count=" + copied);
        System.out.println("present-data=" +
                new String(captured.toByteArray(), StandardCharsets.UTF_8));

        ByteArrayOutputStream noDataCapture = new ByteArrayOutputStream();
        long missing = forwardOwned(Optional.empty(), noDataCapture);
        System.out.println("absent-count=" + missing);
        System.out.println("absent-size=" + noDataCapture.size());

        try (OutputStream sink = OutputStream.nullOutputStream()) {
            long accepted = forwardOwned(
                    Optional.of(new ByteArrayInputStream(payload)), sink);
            System.out.println("discard-count=" + accepted);
        }

        try (InputStream empty = InputStream.nullInputStream()) {
            System.out.println("empty-first-read=" + empty.read());
            System.out.println("empty-all-bytes=" + empty.readAllBytes().length);
        }

        InputStream closedInput = InputStream.nullInputStream();
        closedInput.close();
        try {
            closedInput.read();
            System.out.println("closed-input=unexpected-success");
        } catch (IOException ex) {
            System.out.println("closed-input=IOException");
        }

        OutputStream closedOutput = OutputStream.nullOutputStream();
        closedOutput.close();
        try {
            closedOutput.write(1);
            System.out.println("closed-output=unexpected-success");
        } catch (IOException ex) {
            System.out.println("closed-output=IOException");
        }
    }
}
```

Biên dịch và chạy trên **JDK 11 trở lên**:

```bash
javac -encoding UTF-8 --release 11 ByteStreamOptionalDemo.java
java ByteStreamOptionalDemo
```

Kết quả chuẩn:

```text
present-count=5
present-data=HELLO
absent-count=0
absent-size=0
discard-count=5
empty-first-read=-1
empty-all-bytes=0
closed-input=IOException
closed-output=IOException
```

Giải thích từng nhóm:

- `present-count=5` và `present-data=HELLO`: dữ liệu có mặt đi qua adapter; `ByteArrayOutputStream` giữ lại chính xác năm byte để kiểm tra.
- `absent-count=0` và `absent-size=0`: `Optional.empty()` được chuyển thành stream rỗng; không ghi byte nào, không cần kiểm tra `null` trong bộ xử lý byte.
- `discard-count=5`: nguồn có năm byte, `transferTo` vẫn đếm năm byte đã chuyển cho null sink, dù đích **không lưu** chúng.
- `empty-first-read=-1` và `empty-all-bytes=0`: stream rỗng phát EOF và mảng byte rỗng.
- `closed-input=IOException` và `closed-output=IOException`: stream kiểu no-op vẫn tuân thủ vòng đời; đọc/ghi sau khi đóng là lỗi.

Ví dụ chỉ chuyển **byte**. Việc dùng `StandardCharsets.UTF_8` nhằm tạo dữ liệu byte từ `"HELLO"` và giải mã byte đã ghi để in kết quả kiểm thử; bản thân `InputStream`/`OutputStream` không tự gắn encoding.

## 8. Bổ sung phép khẳng định thực tế cho unit test

Khi viết bài kiểm thử tự động, so sánh **dữ liệu thực**, không chỉ nhìn stdout:

```java
// Đoạn kiểm tra nằm trong phương thức test có throws IOException;
// class ByteStreamOptionalDemo phải truy cập được từ test cùng package.
byte[] expected = {1, 2, 3, (byte) 255};

ByteArrayOutputStream result = new ByteArrayOutputStream();
long bytesTransferred = ByteStreamOptionalDemo.forwardOwned(
        Optional.of(new ByteArrayInputStream(expected)), result);

if (bytesTransferred != expected.length ||
        !java.util.Arrays.equals(expected, result.toByteArray())) {
    throw new AssertionError("wrong bytes transferred");
}

ByteArrayOutputStream emptyResult = new ByteArrayOutputStream();
long emptyCount = ByteStreamOptionalDemo.forwardOwned(
        Optional.empty(), emptyResult);

if (emptyCount != 0 || emptyResult.size() != 0) {
    throw new AssertionError("missing source should emit no bytes");
}
```

Đây là đoạn minh họa nằm trong method test, nên cần import `java.io.*` và `java.util.Optional` theo ngữ cảnh. Nếu dùng JUnit, có thể thay `if/throw AssertionError` bằng assertion tương đương; cách kiểm tra dữ liệu không phụ thuộc framework. Sử dụng cả **số byte** và **nội dung byte** vì đếm đúng byte chưa chắc đã giữ đúng thứ tự hoặc giá trị.

Với adapter có quản lý tài nguyên, cũng nên kiểm thử phương thức có đóng stream đầu vào khi thành công hoặc thất bại hay không, bằng một stream test ghi nhận việc `close()` được gọi. Khi kiểm thử lỗi đọc/ghi, dùng fake stream ném `IOException` và xác nhận lỗi **được truyền ra**, thay vì bị thay bằng EOF hoặc null sink.

## 9. Dữ liệu tùy chọn: tránh lẫn “vắng”, “rỗng” và “lỗi”

Ví dụ một tích hợp có thể trả `Optional<InputStream>` nếu nguồn không bắt buộc:

```java
// Đoạn minh họa nằm trong phương thức có throws IOException.
// path là Path đã được xác định, enabled là cấu hình rõ ràng.
Optional<InputStream> maybeSource = enabled
        ? Optional.of(Files.newInputStream(path))
        : Optional.empty();
```

Nếu `enabled` là `true` mà tệp không mở được, `Files.newInputStream(path)` sẽ báo `IOException`. Đây là điều đúng: một nguồn **được yêu cầu** nhưng không truy cập được là **lỗi**, không phải “vắng theo thiết kế”. Khi `enabled` là `false` thì không mở tệp và có thể truyền `Optional.empty()` cho adapter áp dụng chính sách rỗng. Stream được mở khi `enabled` là `true` cần được đóng một lần bởi bên sở hữu.

Trong thiết kế API mới, không phải lúc nào cũng cần truyền `Optional<InputStream>` làm tham số. Nếu caller có thể chọn trực tiếp nguồn rỗng và API chỉ làm việc với `InputStream`, bạn có thể để adapter xử lý `Optional` ở **ranh giới**, rồi truyền một stream không null vào phần lõi. Điều này giữ phần xử lý byte đơn giản. Nếu cần mở nguồn lại nhiều lần, hãy biểu diễn **nhà cung cấp tạo stream mới** (ví dụ `Supplier<InputStream>` hoặc interface factory có `throws IOException`) thay vì tái sử dụng một `InputStream` đã đọc hết/đã đóng.

**Trường hợp không nên biến thành stream rỗng:** đầu vào thiết yếu cho xác thực, dữ liệu cần kiểm toán, request body bắt buộc, tài liệu có mặt nhưng giải mã bị lỗi, hoặc bất kỳ lỗi I/O nào cần báo về caller. Chỉ áp dụng no-op stream khi hợp đồng xác định rõ vắng dữ liệu là kết quả bình thường.

## 10. Lỗi thường gặp và cách sửa

| Lỗi / ngộ nhận | Cách làm đúng |
| --- | --- |
| “`nullInputStream()` trả `null`.” | Nó trả đối tượng `InputStream` hợp lệ, có EOF ngay khi mở. |
| “`nullOutputStream()` lưu dữ liệu nhưng không có tên tệp.” | Nó **bỏ** dữ liệu, không có bộ đệm/tệp đầu ra để truy xuất. |
| “`transferTo` trả 5 nghĩa là 5 byte đã nằm trong file.” | Số byte đã **chuyển cho output stream**; output có thể cố ý loại bỏ tất cả. |
| “Dùng null sink để test nội dung mong đợi.” | Dùng `ByteArrayOutputStream`, so sánh `toByteArray()` với byte kỳ vọng. |
| “`Optional.empty()` và lỗi mở tệp đều là không có dữ liệu.” | Trạng thái tùy chọn vắng hợp lệ phải phân biệt với `IOException`. |
| “`available() == 0` là EOF với mọi `InputStream`.” | Sai; số byte đọc ngay không chặn không phản ánh chắc chắn EOF. |
| “`transferTo` tự đóng hai stream.” | Không; bên sở hữu đóng bằng try-with-resources hoặc cơ chế thích hợp. |
| “No-op stream đã đóng vẫn dùng được vì không có tài nguyên thật.” | Đọc/ghi sau `close()` vẫn ném `IOException` theo hợp đồng. |
| “`InputStream` tự giải mã UTF-8.” | Byte stream không mang charset; khi chuyển byte sang `String` phải chỉ định charset. |
| “Dùng `orElse(...)` không có tác dụng phụ.” | Đối số `orElse(...)` được tạo/đánh giá ngay; dùng `orElseGet` khi fallback được tạo theo nhu cầu. |
| “Tắt output bằng null sink luôn an toàn.” | Chỉ khi bỏ kết quả là hành vi **được cho phép và có chủ đích**. |
| “Giữ một no-op stream toàn cục cho mọi lần gọi.” | Dùng factory mới để tránh tái sử dụng đối tượng đã đóng; mỗi lời gọi có vòng đời rõ ràng. |

## 11. Checklist chọn stream trong ba tình huống

1. **Kiểm thử dữ liệu có thật:** `ByteArrayInputStream` cấp byte và `ByteArrayOutputStream` nhận byte; so sánh mảng byte cùng số lượng.
2. **Kiểm thử nhánh thiếu đầu vào hợp lệ:** `InputStream.nullInputStream()` mô phỏng nguồn EOF; xác nhận phần lõi không tạo dữ liệu sai.
3. **Chạy pipeline nhưng chủ ý bỏ đầu ra:** `OutputStream.nullOutputStream()`; đo/kiểm tra điều khiển, không dùng nó để khẳng định byte đã được lưu.
4. **Adapter có đầu vào tùy chọn:** chọn nguồn thay thế ở ranh giới với `Optional.orElseGet(InputStream::nullInputStream)`, giữ nguyên lỗi I/O khi input bắt buộc.
5. **Tài nguyên:** quy định ai đóng nguồn, ai đóng đích; nhớ `transferTo` không tự đóng.
6. **Ngữ nghĩa nghiệp vụ:** quyết định khi nào “vắng” đồng nghĩa “rỗng” và khi nào cần giữ riêng cờ presence; tuyệt đối tránh nuốt lỗi bằng stream rỗng/đích bỏ qua.
7. **Đúng dữ liệu byte:** xác định charset nếu cần chuyển sang `String`; các API no-op byte stream không xử lý Unicode thay cho ứng dụng.

### Tài liệu chính thức

- [Java SE 11 — `InputStream.nullInputStream()` và `InputStream.transferTo`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html)
- [Java SE 11 — `OutputStream.nullOutputStream()`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/OutputStream.html)
- [Java SE 26 — `InputStream` (hợp đồng hiện hành)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html)
- [Java SE 26 — `OutputStream` (hợp đồng hiện hành)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStream.html)
