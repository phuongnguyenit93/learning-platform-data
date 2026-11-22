# Điều khiển `flush()` của bộ nén khi truyền dữ liệu liên tục

Trong `java.util.zip`, lệnh `write()` đưa dữ liệu vào bộ nén nhưng **không bảo đảm ngay lúc đó đã có đủ byte nén ở luồng đích**. Bộ nén DEFLATE có thể giữ dữ liệu để mã hóa hiệu quả hơn. Khi truyền sự kiện, bản ghi hoặc các phần phản hồi qua một kết nối còn mở, phía nhận đôi khi cần giải nén được những gì đã gửi **trước khi kết thúc toàn bộ luồng**.

Từ Java 7, `DeflaterOutputStream` và `GZIPOutputStream` hỗ trợ tùy chọn `syncFlush` ngay trong constructor. Cơ chế này vẫn có trong Java hiện đại: nếu khởi tạo với `syncFlush = true`, gọi `flush()` sẽ yêu cầu bộ nén thực hiện `Deflater.SYNC_FLUSH` rồi flush luồng đích. Đây là công cụ phù hợp khi phải cân bằng độ trễ và hiệu quả nén.

## 1. Vì sao `flush()` thông thường có thể chưa đủ?

Một đường đi dữ liệu thường có nhiều tầng:

```text
Dữ liệu ứng dụng -> bộ nén DEFLATE -> luồng đích/đệm I/O -> socket/HTTP -> phía nhận
                           ^                    ^
                     có bộ đệm nén        có thể có bộ đệm khác
```

- `write(bytes)`: cung cấp dữ liệu cho bộ nén. Một số byte nén có thể đã được ghi ra, nhưng không có cam kết rằng mỗi lần `write()` tạo thành một phần dữ liệu giải nén được độc lập.
- `flush()` khi `syncFlush = false` (giá trị mặc định): chỉ flush luồng đích; dữ liệu còn đang chờ **bên trong bộ nén** có thể chưa được đẩy ra.
- `flush()` khi `syncFlush = true`: yêu cầu bộ nén đưa hết dữ liệu đang chờ ra theo chế độ `SYNC_FLUSH`, sau đó flush luồng đích. Phía nhận có thể tiếp tục giải nén đến điểm đó mà **không cần kết thúc luồng nén**.
- `finish()`: kết thúc luồng nén và phát những byte cuối cùng của định dạng, nhưng không đóng luồng đích. Không gọi sau từng sự kiện nếu còn muốn ghi tiếp vào cùng luồng nén.
- `close()`: hoàn tất luồng nén và đóng luồng đích. Dùng khi kết thúc phiên truyền hoặc qua `try-with-resources`.

**Phân biệt:** flush ở bộ nén làm dữ liệu nén sẵn sàng cho tầng I/O kế tiếp; nó không tự bảo đảm mạng, HTTP server, proxy hoặc phía nhận sẽ chuyển/đọc ngay từng gói. Độ trễ thực tế còn phụ thuộc các tầng này.

## 2. API hiện hành và cách bật đồng bộ flush

| Lớp/constructor | Dữ liệu đầu ra | Khi nào sử dụng |
| --- | --- | --- |
| `new DeflaterOutputStream(out, true)` | Luồng DEFLATE với lớp bọc zlib mặc định, **không phải tệp .zip** | Truyền dữ liệu nén liên tục giữa hai bên thống nhất định dạng zlib |
| `new DeflaterOutputStream(out, deflater, bufferSize, true)` | DEFLATE/zlib theo cấu hình `Deflater` | Cần tùy chỉnh mức nén hoặc cấu hình nén, đồng thời chủ động quản lý vòng đời `Deflater` |
| `new GZIPOutputStream(out, true)` | Luồng GZIP (`.gz`) | Khi giao thức/phía nhận hỗ trợ GZIP và cần truyền tăng dần |
| `new GZIPOutputStream(out, bufferSize, true)` | GZIP với kích thước bộ đệm chỉ định | Khi cần điều chỉnh bộ đệm nén cho tải thực tế |
| `new ZipOutputStream(out)` | Kho lưu trữ ZIP gồm các `ZipEntry` | Khi cần tệp ZIP nhiều mục; **không có constructor `syncFlush` công khai** |

Các constructor tương ứng không truyền `true` dùng hành vi `syncFlush = false`. Cờ này được đặt lúc tạo stream, không phải thuộc tính có thể bật/tắt bằng một lời gọi `flush()` sau đó.

Ở mức thấp, `Deflater.deflate(output, offset, length, Deflater.SYNC_FLUSH)` cũng cho phép tự điều khiển chế độ xả khi trực tiếp sử dụng `Deflater`. Các chế độ cần phân biệt:

- `NO_FLUSH`: thông thường hiệu quả nén tốt hơn, phù hợp khi chưa cần phía nhận xử lý ngay.
- `SYNC_FLUSH`: đẩy dữ liệu còn chờ để phía nhận có thể tiếp tục giải nén, vẫn giữ trạng thái/từ điển nén cho phần tiếp theo.
- `FULL_FLUSH`: ngoài việc xả dữ liệu, còn đặt lại trạng thái nén để hỗ trợ điểm khởi động lại trong một số giao thức; không tương đương `SYNC_FLUSH` và có thể làm tỷ lệ nén giảm mạnh.

Khi chỉ cần xả dữ liệu trong `DeflaterOutputStream` hoặc `GZIPOutputStream`, thông thường **chọn constructor `syncFlush = true` rồi gọi `flush()`** thay vì tự viết vòng lặp với `Deflater`.

## 3. Ví dụ chạy được: giải nén dữ liệu ngay sau `flush()`

Ví dụ này sử dụng `ByteArrayOutputStream` để mô phỏng những byte đã được đưa tới tầng truyền tải. Chương trình tạo bộ nén zlib, ghi phần đầu, gọi `flush()` và kiểm tra: phần đầu có thể giải nén ngay, dù dòng nén **chưa kết thúc**. Sau khi đóng bộ nén, toàn bộ thông điệp được giải nén đầy đủ.

Tạo tệp `SyncFlushDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.DataFormatException;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;

public class SyncFlushDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream wire = new ByteArrayOutputStream();

        try (DeflaterOutputStream compressed =
                     new DeflaterOutputStream(wire, true)) {
            compressed.write("part-1|".getBytes(StandardCharsets.UTF_8));
            compressed.flush(); // SYNC_FLUSH, chưa kết thúc luồng nén

            byte[] firstSnapshot = wire.toByteArray();
            inspect(firstSnapshot, "After flush: ");

            compressed.write("part-2".getBytes(StandardCharsets.UTF_8));
        } // close(): ghi phần cuối và đóng luồng nén

        inspect(wire.toByteArray(), "After close: ");
    }

    private static void inspect(byte[] compressed, String label)
            throws DataFormatException {
        Inflater inflater = new Inflater();
        try {
            inflater.setInput(compressed);
            byte[] decoded = new byte[128];
            int length = inflater.inflate(decoded);

            System.out.println(label + new String(
                    decoded, 0, length, StandardCharsets.UTF_8));
            System.out.println("Finished: " + inflater.finished());
        } finally {
            inflater.end();
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac SyncFlushDemo.java
java SyncFlushDemo
```

Kết quả:

```text
After flush: part-1|
Finished: false
After close: part-1|part-2
Finished: true
```

Giải thích:

1. Sau `flush()`, bộ giải nén có thể lấy ra `part-1|` từ các byte đã có; `Inflater.finished()` vẫn là `false` vì trailer/kết thúc luồng zlib chưa xuất hiện.
2. Sau `close()`, bộ nén đã hoàn tất luồng; giải nén nhận `part-1|part-2` và `finished()` là `true`.
3. Hàm `inspect()` cố ý chỉ gọi `inflate()` một lần vì dữ liệu mẫu rất nhỏ; đó là phép kiểm tra minh họa, **không phải bộ giải nén production**. Với luồng thực tế, dùng một `Inflater` xuyên suốt các phần đến, đọc lặp theo trạng thái `needsInput()`/`finished()` và xử lý kết quả giải nén theo các ranh giới thông điệp của giao thức. Không tạo `Inflater` mới cho từng mảnh byte tùy ý.

Đừng dựa vào số byte nén của ví dụ: kích thước có thể phụ thuộc dữ liệu và phiên bản thư viện nén. Điều quan trọng là **nội dung giải nén được và trạng thái chưa/đã kết thúc**.

## 4. Áp dụng với GZIP cho truyền sự kiện hoặc phản hồi dài

Nếu hai bên đã thống nhất nhận luồng **GZIP**, có thể giữ một `GZIPOutputStream` sống trong suốt phiên, ghi từng bản ghi, rồi flush tại các điểm cần người nhận xử lý. Đoạn sau là **mã tích hợp minh họa**, giả định `networkOut` là `OutputStream` đã mở và `events` là tập các chuỗi sự kiện do ứng dụng cung cấp:

```java
try (GZIPOutputStream gzip =
         new GZIPOutputStream(networkOut, 8192, true)) {
    for (String event : events) {
        byte[] record = (event + "\n").getBytes(StandardCharsets.UTF_8);
        gzip.write(record);
        gzip.flush(); // đẩy phần GZIP đang chờ, luồng vẫn còn mở
    }
} // kết thúc GZIP member và đóng networkOut
```

Trong đoạn mã tích hợp cần import `java.util.zip.GZIPOutputStream` và `java.nio.charset.StandardCharsets`. Nếu `networkOut` là socket hoặc response body do framework quản lý, hãy tuân theo hợp đồng sở hữu/đóng stream của framework: không tự đóng sớm một tài nguyên dùng chung.

**Lưu ý về phía nhận:** một luồng GZIP đang truyền dở chưa có trailer hoàn tất; phía nhận có thể giải nén tăng dần những dữ liệu đã flush, nhưng chỉ kiểm tra được toàn vẹn GZIP cuối cùng khi nhận đủ phần kết thúc. Không coi một snapshot GZIP giữa chừng là tệp `.gz` hoàn chỉnh, và không dùng `readAllBytes()` khi mục tiêu là xử lý tăng dần trên kết nối chưa đóng.

Khi sử dụng HTTP, còn cần thống nhất `Content-Encoding: gzip`/khả năng của client, loại phản hồi và cơ chế stream của máy chủ. Việc bật `syncFlush` **không thay thế** cơ chế flush response, framing sự kiện hoặc chính sách buffer của proxy.

## 5. Phân biệt rõ luồng DEFLATE/GZIP với kho lưu trữ ZIP

Dù cùng nằm trong `java.util.zip`, `ZipOutputStream` ghi **định dạng tệp ZIP có các entry và central directory**, khác với `DeflaterOutputStream` hay `GZIPOutputStream` ghi một luồng dữ liệu nén.

`ZipOutputStream` kế thừa `flush()` nhưng không cung cấp constructor `syncFlush = true`. Vì thế, **không giả định `zip.flush()` sẽ buộc bộ nén của entry hiện tại đẩy hết dữ liệu chưa nén ra**. Cấu trúc thường dùng để tạo ZIP là:

```java
try (ZipOutputStream zip = new ZipOutputStream(destination)) {
    zip.putNextEntry(new ZipEntry("events.txt"));
    zip.write(content);
    zip.closeEntry(); // hoàn tất entry hiện tại
    zip.finish();     // ghi cấu trúc kết thúc ZIP
}
```

Đây là **đoạn tích hợp**, cần import `ZipOutputStream`/`ZipEntry`; `destination` là luồng đầu ra, `content` là mảng byte của ứng dụng. `closeEntry()` hoàn tất entry hiện tại, còn `finish()` hoàn thiện tệp ZIP (bao gồm central directory). Không dùng `finish()` để đánh dấu kết thúc từng mảnh của cùng một luồng còn mở. Một số trình đọc ZIP hỗ trợ đọc tuần tự theo entry, nhưng nhiều công cụ cần tệp ZIP hoàn chỉnh; vì vậy ZIP archive không phải lựa chọn mặc định cho dữ liệu sự kiện cần giải nén ngay từng phần.

Chọn theo mục tiêu:

| Yêu cầu | Lựa chọn phù hợp |
| --- | --- |
| Dữ liệu truyền liên tục, hai bên thống nhất zlib | `DeflaterOutputStream(..., true)` và `Inflater` tương ứng |
| Truyền liên tục với định dạng GZIP được client hỗ trợ | `GZIPOutputStream(..., true)` và bộ giải nén GZIP dạng streaming |
| Đóng gói nhiều tệp hoặc entry để tải về | `ZipOutputStream` với `putNextEntry()`, `closeEntry()` và `finish()` |
| Chỉ lưu tệp sau khi ghi xong, không cần đọc giữa chừng | Thường không cần bật `syncFlush` |

## 6. Lưu ý khi vận hành

### Độ trễ, băng thông và tần suất xả

`SYNC_FLUSH` phải tạo ranh giới để bộ giải nén tiêu thụ dữ liệu hiện có. Mỗi lần flush có thể phát sinh thêm byte điều khiển, giảm cơ hội gộp dữ liệu để nén tốt và tăng số lần ghi I/O. Nếu gọi sau từng ký tự hoặc từng byte, chi phí có thể lớn hơn lợi ích.

Hãy chọn mốc flush theo nhu cầu thực tế: sau mỗi **thông điệp cần hiển thị ngay**, theo một khoảng thời gian có mục tiêu độ trễ rõ ràng, hoặc khi đã gom đủ một nhóm bản ghi. So sánh trên tải thật bằng các chỉ số: độ trễ từ lúc tạo sự kiện đến lúc client giải nén được, tỷ lệ nén, số byte gửi và số lần flush/ghi mạng. Nếu truyền file lớn mà chỉ đọc sau khi hoàn tất, không cần xả liên tục.

### Ranh giới thông điệp và vòng đời

- `SYNC_FLUSH` chỉ tạo điểm có thể tiếp tục **giải nén**, **không** tạo ranh giới thông điệp nghiệp vụ. Nếu một bản ghi có thể chứa dấu xuống dòng hoặc dữ liệu nhị phân, cần giao thức framing rõ ràng (ví dụ tiền tố độ dài, bản ghi phân cách có quy ước escape, hoặc một định dạng sự kiện phù hợp).
- Đặt bộ đệm và các bộ chuyển mã đúng thứ tự. Ví dụ với `Writer` bọc phía ngoài `GZIPOutputStream`, phải flush `Writer` để đẩy ký tự còn chờ xuống bộ nén; chỉ flush trực tiếp bộ nén có thể bỏ sót dữ liệu đang đệm trong `Writer`.
- `flush()` **không** đồng nghĩa xác nhận phía nhận đã nhận/xử lý bản ghi. Với mạng hoặc client chậm, cần chính sách backpressure, timeout, hủy và xử lý lỗi I/O thích hợp.
- `finish()` và `close()` cần xảy ra khi kết thúc bình thường để ghi phần kết của định dạng nén. Mất kết nối trước thời điểm này có thể khiến phần cuối không hợp lệ; phía nhận phải phân biệt luồng đang chờ thêm dữ liệu với luồng bị cắt cụt.
- Với `Deflater` tự truyền vào constructor `DeflaterOutputStream`, bên tạo `Deflater` chịu trách nhiệm giải phóng nó sau khi kết thúc stream. Với compressor do constructor mặc định tự tạo, stream quản lý compressor đó.

### Lỗi thường gặp

1. **Dùng constructor mặc định rồi chỉ gọi `flush()`:** chỉ xả đệm phía sau bộ nén; thông điệp nhỏ có thể còn nằm trong DEFLATE.
2. **Gọi `close()`/`finish()` sau từng bản ghi:** kết thúc luồng nén quá sớm và làm mất lợi ích của một phiên nén liên tục.
3. **Nhầm `ZipOutputStream` với GZIP/zlib:** API ZIP không có công tắc `syncFlush` tương ứng, còn cấu trúc ZIP khác về entry và metadata.
4. **Dựa vào một lần `read()` là đủ toàn bộ thông điệp:** mạng và luồng giải nén không bảo đảm ranh giới `read()` trùng ranh giới `write()`; phải có framing và vòng lặp đọc.
5. **Bật flush quá dày:** tăng overhead và có thể làm tệ tỷ lệ nén; cần đo đạc trước khi chọn tần suất.
6. **Chỉ kiểm tra đã có byte trên socket:** byte có thể là header hoặc phần nén chưa đủ để giải mã; hãy kiểm tra khả năng giải nén tăng dần bằng bài test có nhiều phần và kiểm tra tính hoàn chỉnh sau khi kết thúc.

## 7. Kiểm thử nên có

Với pipeline nén truyền liên tục, tối thiểu kiểm tra ba tình huống: (1) sau `write` + `flush` với `syncFlush=true`, phía nhận giải nén được bản ghi đầu và biết luồng chưa kết thúc; (2) sau các bản ghi tiếp theo và `finish`/`close`, giải nén ra đúng toàn bộ dữ liệu và xác nhận kết thúc; (3) khi mất kết nối hoặc nhận dữ liệu bị cắt, phía nhận không coi dữ liệu dở dang là thành công. Có thể so sánh tần suất flush khác nhau bằng benchmark để chọn điểm cân bằng giữa độ trễ và kích thước dữ liệu.

**Ghi nhớ:** Với luồng nén DEFLATE/GZIP phải đọc tăng dần, hãy bật `syncFlush` ngay từ constructor và gọi `flush()` đúng **điểm cần công bố dữ liệu**. Sau cùng vẫn phải `finish()`/`close()` để hoàn thành định dạng; nếu yêu cầu là một tệp ZIP hoàn chỉnh, dùng vòng đời các `ZipEntry` thay vì dựa vào `flush()`.

## Tài liệu tham khảo chính thức

- [DeflaterOutputStream — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/DeflaterOutputStream.html): constructor `syncFlush`, `flush()`, `finish()` và trách nhiệm đóng compressor.
- [GZIPOutputStream — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/GZIPOutputStream.html): ghi GZIP với tùy chọn `syncFlush`.
- [Deflater — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/Deflater.html): `NO_FLUSH`, `SYNC_FLUSH`, `FULL_FLUSH`.
- [ZipOutputStream — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/ZipOutputStream.html): ZIP entry, `closeEntry()`, `finish()` và constructor.
