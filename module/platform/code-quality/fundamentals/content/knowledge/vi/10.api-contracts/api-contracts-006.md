# Tác dụng phụ, quyền sở hữu và trách nhiệm đóng tài nguyên

## 1. Mục tiêu bài học

Trong chương **Hợp đồng API** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu một phần thường bị bỏ sót khi thiết kế phương thức và lớp: **ngoài giá trị trả về, lời gọi còn làm thay đổi điều gì, ai chịu trách nhiệm với đối tượng hoặc tài nguyên được truyền qua ranh giới, và ai phải đóng tài nguyên đó?**

Module hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Làm rõ tác dụng phụ và quyền sở hữu giúp người đọc dự đoán hành vi, ngăn lỗi rò rỉ tài nguyên hoặc đóng tài nguyên quá sớm, đồng thời cho phép thay đổi triển khai mà vẫn giữ đúng hợp đồng.

Sau bài học, bạn có thể:

- Phân biệt kết quả trả về với **tác dụng phụ (side effect)** của một API.
- Xác định ai **sở hữu (owns)**, ai chỉ **mượn (borrows)** và khi nào quyền sở hữu được **chuyển giao (transfers)**.
- Giải thích quy tắc đóng `AutoCloseable`, phạm vi `try-with-resources` và việc truyền lỗi khi ghi/đóng thất bại.
- Thiết kế API Java cho phép ghi vào `Writer` do caller cung cấp và một API khác tự mở/đóng file.
- Nhận biết lỗi khi trả về stream đã đóng, đóng phụ thuộc dùng chung hoặc thực hiện bất đồng bộ ngoài vòng đời tài nguyên.
- Viết kiểm thử xác minh quyền sở hữu, đường lỗi và trạng thái tài nguyên ở ranh giới API.

## 2. Hợp đồng API bao gồm nhiều hơn chữ ký phương thức

Một chữ ký như sau mô tả tên, kiểu đầu vào và kiểu trả về, nhưng **chưa cho biết đầy đủ hành vi**:

```java
void exportReport(List<ReportRow> rows, Writer destination)
        throws IOException;
```

Người gọi cần biết: phương thức có ghi vào `destination` không? Có đóng nó khi xong không? Có gọi `flush` không? Nếu ghi một nửa rồi gặp lỗi, dữ liệu đã ghi có bị hoàn tác không? Phương thức có được giữ lại `destination` để dùng sau khi trả về không?

Những câu trả lời này thuộc **hợp đồng hành vi** của API, dù không được Java biểu diễn hết qua kiểu dữ liệu.

| Thành phần hợp đồng | Ví dụ câu hỏi |
| --- | --- |
| Ý nghĩa nghiệp vụ | API đang xuất báo cáo, thực hiện giao dịch hay chỉ tính toán? |
| Đầu vào/đầu ra | Loại dữ liệu nào hợp lệ; trả lại hoặc ném lỗi gì? |
| Tác dụng phụ | Có ghi file, cập nhật trạng thái, gửi mạng, ghi log, tiêu thụ dữ liệu không? |
| Quyền sở hữu | Caller có còn được sử dụng đối tượng sau lời gọi không? |
| Vòng đời | Ai mở, ai đóng, ai chịu trách nhiệm khi thao tác thất bại? |
| Thời điểm hoàn tất | Tác dụng phụ hoàn thành khi phương thức trả về hay sau một tác vụ bất đồng bộ? |
| Tính an toàn khi lặp lại | Có thể gọi lại sau timeout mà không tạo thao tác trùng không? |

Một API được coi là **dễ hiểu** khi các quyết định này có thể suy ra hợp lý từ tên, kiểu và tài liệu ngắn gọn; **đáng tin cậy** khi hiện thực tuân thủ cam kết; **dễ thay đổi** khi chi tiết nội bộ được sửa mà caller không phải học lại những quy tắc vòng đời ngầm.

## 3. Tác dụng phụ: điều gì xảy ra ngoài giá trị trả về?

**Tác dụng phụ** là sự thay đổi hoặc tương tác quan sát được vượt ra ngoài kết quả tính toán trả về. Ví dụ:

- Sửa một đối tượng hoặc collection mà caller vẫn giữ tham chiếu.
- Ghi file, ghi cơ sở dữ liệu hoặc phát thông điệp.
- Gửi HTTP request, gọi cổng thanh toán, gửi email.
- Tiêu thụ một `InputStream` làm vị trí đọc tiến lên.
- Đóng, flush hoặc giải phóng tài nguyên do thành phần khác sở hữu.
- Ghi log, tăng metric, hoặc đọc thời gian/hệ thống ngẫu nhiên khiến kết quả phụ thuộc vào môi trường.

Ví dụ hai API cùng trả `long` nhưng có đặc tính rất khác:

```java
long calculateTotal(long subtotalVnd, long feeVnd);

long chargeCustomer(String orderId, long amountVnd);
```

`calculateTotal` có thể là phép tính thuần: cùng đầu vào cho cùng kết quả và không sửa trạng thái bên ngoài. `chargeCustomer` có thể tạo giao dịch thực tế. Dù đều trả `long`, không thể đối xử với chúng như những phép tính tương đương khi retry hoặc kiểm thử.

**Tác dụng phụ không mặc nhiên là mã xấu.** Một chương trình hữu ích thường phải ghi dữ liệu và giao tiếp với bên ngoài. Vấn đề phát sinh khi tác dụng phụ **bị ẩn, không có ranh giới rõ hoặc không được kiểm soát**.

### Mức độ ảnh hưởng khi gọi lặp lại

| Kiểu thao tác | Khi gọi lại với cùng đầu vào | Điều cần làm rõ |
| --- | --- | --- |
| Tính thuần | Không tạo thêm thay đổi bên ngoài | Kiểu dữ liệu, trường hợp biên, lỗi |
| Đọc stream | Có thể đọc từ vị trí tiếp theo thay vì dữ liệu ban đầu | Stream có thể đọc lại không, ai quản lý vị trí và đóng? |
| Ghi báo cáo vào `Writer` | Có thể ghi thêm cùng nội dung lần nữa | Ghi nối tiếp hay ghi đè? Có thể xuất lại không? |
| Gửi một thông báo | Có thể gửi hai lần | Có khóa chống trùng hoặc kết quả lần đầu không? |
| Ghi giao dịch | Có thể trùng tác động dù lần trước bị timeout | Idempotency, đối soát và trạng thái giao dịch |

**Idempotent** nghĩa là lặp lại thao tác theo hợp đồng không tạo thêm ảnh hưởng quan sát được ngoài lần áp dụng đầu tiên. Một lời gọi HTTP dùng phương thức nhất định không tự bảo đảm hiện thực có tính idempotent; phải xem quy tắc của chính API, lưu trữ và tác dụng phụ thực tế.

## 4. Quyền sở hữu tài nguyên: ba quan hệ thường gặp

Với một đối tượng có vòng đời (file, kết nối, stream, socket, transaction), cần xác định **ai có quyền quyết định khi nào nó hết sử dụng**.

### 4.1. Caller sở hữu, callee chỉ mượn

Caller tạo hoặc nhận trách nhiệm quản lý tài nguyên và truyền vào phương thức khác. Callee chỉ sử dụng trong thời gian lời gọi được phép; **không tự đóng hoặc giữ lại** nếu hợp đồng không cho phép.

Ví dụ:

```java
void writeRows(List<ReportRow> rows, Writer destination)
        throws IOException;
```

`destination` thuộc caller. `writeRows` được phép ghi trong lời gọi đồng bộ, nhưng không được đóng/flush hoặc giữ tham chiếu để ghi về sau nếu hợp đồng không nói vậy. Caller có thể cần viết nhiều phần vào cùng một file.

### 4.2. Callee tạo và sở hữu

Nếu phương thức tự mở tài nguyên để hoàn thành toàn bộ công việc đồng bộ, chính phương thức đó thường **đóng tài nguyên trên cả đường thành công và thất bại**.

Ví dụ `writeFile(Path path, ...)` tự mở `Writer`; phần triển khai dùng `try-with-resources` và trả về sau khi thao tác ghi/đóng kết thúc. Caller chỉ cần xử lý kết quả hoặc ngoại lệ.

### 4.3. Chuyển giao quyền sở hữu cho caller

Một số API **trả về tài nguyên đang mở** để caller sử dụng sau khi phương thức kết thúc. Khi đó caller phải đóng theo hợp đồng.

```java
Stream<String> openLines(Path path) throws IOException;
```

Nếu phương thức dùng `Files.lines(path)` và trả stream, stream còn gắn với file. Caller phải đặt nó trong `try-with-resources`; callee **không được đóng trước khi trả về**.

### Các mô hình khác cần ghi rõ

| Mô hình | Ai quyết định đóng? | Lưu ý |
| --- | --- | --- |
| **Sở hữu riêng** | Thành phần tạo và giữ tài nguyên trong vòng đời của mình | Đóng khi xong, kể cả có ngoại lệ. |
| **Mượn tạm thời** | Bên sở hữu ban đầu | Không đóng và không giữ tham chiếu quá thời hạn cho phép. |
| **Chuyển giao** | Bên nhận sau khi chuyển giao | Tài liệu phải nêu rõ trách nhiệm mới và thời điểm hiệu lực. |
| **Dùng chung** | Một chủ sở hữu vòng đời cấp cao, như container hoặc application | Không để từng request tự đóng phụ thuộc dùng chung. |
| **Mượn từ pool** | Theo hợp đồng pool: thường `close` là trả tài nguyên về pool | Không mặc định rằng `close` luôn phá hủy kết nối vật lý. |

**Quy tắc thực hành:** người tạo thường sở hữu tài nguyên, **trừ khi hợp đồng chuyển giao hoặc hạ tầng quản lý vòng đời có quy định khác**. “Ai tạo thì người đó đóng” là điểm xuất phát hữu ích nhưng chưa đủ cho factory trả stream mở, pool kết nối hoặc dependency được injection.

## 5. Ví dụ Java 17: xuất CSV với hợp đồng quyền sở hữu rõ ràng

Giả sử module báo cáo xuất một danh sách số lượng hàng theo SKU. Yêu cầu được xác định:

1. `sku` không rỗng, `quantity` là số nguyên không âm.
2. `writeRows` ghi CSV **đồng bộ** vào `Writer` do caller cung cấp; **không đóng, không flush, không giữ tham chiếu**.
3. `writeFile` tự mở file UTF-8; **tự đóng tài nguyên nó đã mở**, kể cả khi ghi thất bại.
4. Nếu `IOException` xảy ra, lỗi được truyền lên caller; nội dung ở đích có thể **đã được ghi một phần**.
5. Ví dụ minh họa quản lý tài nguyên và không bảo đảm việc ghi file có tính nguyên tử hoặc an toàn giao dịch.

### 5.1. Kiểu dữ liệu và phương thức ghi vào tài nguyên mượn

```java
// CsvReportExporter.java
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public final class CsvReportExporter {
    private CsvReportExporter() {}

    public record ReportRow(String sku, long quantity) {
        public ReportRow {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException(
                        "quantity must not be negative");
            }
        }
    }

    /**
     * Ghi các dòng CSV đồng bộ. destination do caller sở hữu;
     * phương thức không close, flush hoặc giữ tham chiếu này.
     * Nếu có IOException, dữ liệu đã ghi có thể là một phần.
     */
    public static void writeRows(
            List<ReportRow> rows, Writer destination) throws IOException {
        Objects.requireNonNull(rows, "rows");
        Objects.requireNonNull(destination, "destination");
        // Chụp danh sách tham chiếu; record ReportRow có thành phần bất biến.
        List<ReportRow> snapshot = List.copyOf(rows);

        destination.write("sku,quantity\n");
        for (ReportRow row : snapshot) {
            destination.write(quoteCsv(row.sku()));
            destination.write(",");
            destination.write(Long.toString(row.quantity()));
            destination.write("\n");
        }
    }

    private static String quoteCsv(String value) {
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    /**
     * Tự tạo và đóng Writer của file này.
     * Nếu lỗi, file có thể đang chứa dữ liệu chưa hoàn chỉnh.
     */
    public static void writeFile(
            Path file, List<ReportRow> rows) throws IOException {
        Objects.requireNonNull(file, "file");
        List<ReportRow> snapshot =
                List.copyOf(Objects.requireNonNull(rows, "rows"));

        try (Writer writer = Files.newBufferedWriter(
                file, StandardCharsets.UTF_8)) {
            writeRows(snapshot, writer);
        }
    }
}
```

Hợp đồng được thể hiện ở hai cấp:

- `writeRows` nhận **tài nguyên mượn**. Nó không gọi `close` hay `flush`, nên caller có thể tiếp tục ghi hoặc tự quyết định khi đưa dữ liệu từ bộ đệm ra đích. `IOException` không bị nuốt.
- `writeFile` **sở hữu** `Writer` do nó tạo ra. `try-with-resources` sẽ đóng tài nguyên khi rời khối, dù có ngoại lệ trong quá trình ghi.
- `List.copyOf` tạo snapshot danh sách trước khi viết, tránh thay đổi cấu trúc danh sách đầu vào trong lúc duyệt từ cùng một tham chiếu; ví dụ dùng `record` chứa `String` và `long` nên các dòng cũng không bị sửa nội dung sau khởi tạo. Với báo cáo rất lớn, sao chép toàn danh sách có thể không phù hợp và cần một giao thức streaming riêng.
- `quoteCsv` là chi tiết định dạng, không phải ví dụ về quản lý tài nguyên. Việc CSV được escape theo cú pháp vẫn **không** tự giải quyết các rủi ro riêng khi mở dữ liệu không tin cậy bằng phần mềm bảng tính; sản phẩm thực phải có chính sách đầu ra tương ứng.

### 5.2. Caller sử dụng đúng hợp đồng

Khi caller đã sở hữu `Writer` và muốn ghi nhiều thành phần vào cùng file:

```java
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReportJob {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("inventory.csv");
        var rows = List.of(
                new CsvReportExporter.ReportRow("SKU-A", 2),
                new CsvReportExporter.ReportRow("SKU-B", 0));

        try (Writer writer = Files.newBufferedWriter(
                output, StandardCharsets.UTF_8)) {
            CsvReportExporter.writeRows(rows, writer);
            // Caller vẫn sở hữu writer và có thể ghi thêm nếu
            // định dạng báo cáo quy định một phần tiếp theo.
        }
    }
}
```

Caller là bên mở `Writer` nên tự đặt nó trong `try-with-resources`. Nếu thay vào đó gọi `CsvReportExporter.writeFile(output, rows)`, caller không nhận một `Writer` đang mở để quản lý; chính phương thức xuất file đóng tài nguyên.

Việc **flush** và **close** cần phân biệt. `flush` yêu cầu đẩy dữ liệu đang đệm ở những lớp liên quan nhưng không kết thúc vòng đời; `close` kết thúc sử dụng tài nguyên và thường thực hiện flush phần đệm còn lại. Một API mượn `Writer` không nên tự flush nếu hợp đồng dành quyền quyết định thời điểm flush cho caller. Ngược lại, API sở hữu `Writer` phải bảo đảm đóng khi xong. Cả hai thao tác đều có thể ném `IOException`.

### 5.3. Ngoại lệ trong lúc đóng không được bỏ quên

`try-with-resources` đóng tài nguyên theo thứ tự ngược với thứ tự khai báo, kể cả khi phần thân khối ném ngoại lệ. Nếu **cả thao tác chính và `close` cùng ném lỗi**, ngoại lệ từ thao tác chính được giữ làm ngoại lệ chính, còn lỗi đóng được gắn dưới dạng **suppressed exception**.

```java
try (Writer writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    CsvReportExporter.writeRows(rows, writer);
} catch (IOException e) {
    // Ghi nhận/ngữ cảnh ở ranh giới xử lý lỗi phù hợp.
    // e.getSuppressed() có thể chứa lỗi phát sinh lúc close.
    throw e;
}
```

Đừng tự đóng trong `finally` rồi vô tình làm mất ngoại lệ ban đầu. Nếu chọn tự quản lý tài nguyên ngoài `try-with-resources` vì một hợp đồng đặc biệt, cần xác định cách giữ đầy đủ lỗi chính và lỗi khi giải phóng.

## 6. Kiểm thử quyền sở hữu và đường thất bại

Ngoài kiểm tra CSV đúng nội dung, cần kiểm tra rằng **API không đóng tài nguyên mượn** và **không che giấu lỗi ghi**. Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.io.Writer;
import java.util.List;
import org.junit.jupiter.api.Test;

class CsvReportExporterTest {
    private static final class TrackingWriter extends Writer {
        final StringBuilder content = new StringBuilder();
        boolean closed;
        int flushCount;

        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            if (closed) {
                throw new IOException("writer is closed");
            }
            content.append(chars, offset, length);
        }

        @Override
        public void flush() throws IOException {
            if (closed) {
                throw new IOException("writer is closed");
            }
            flushCount++;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    @Test
    void writingToBorrowedWriterDoesNotCloseOrFlushIt()
            throws IOException {
        var writer = new TrackingWriter();
        var rows = List.of(
                new CsvReportExporter.ReportRow("SKU-A", 2));

        CsvReportExporter.writeRows(rows, writer);

        assertEquals("sku,quantity\n\"SKU-A\",2\n",
                writer.content.toString());
        assertFalse(writer.closed);
        assertEquals(0, writer.flushCount);

        // Caller vẫn sử dụng được tài nguyên sau lời gọi.
        writer.write("next section");
    }

    @Test
    void writeFailureIsPropagated() {
        Writer brokenWriter = new Writer() {
            @Override
            public void write(char[] chars, int off, int len)
                    throws IOException {
                throw new IOException("write failed");
            }
            @Override
            public void flush() {}
            @Override
            public void close() {}
        };

        IOException failure = assertThrows(IOException.class,
                () -> CsvReportExporter.writeRows(
                        List.of(new CsvReportExporter.ReportRow("A", 1)),
                        brokenWriter));
        assertEquals("write failed", failure.getMessage());
    }
}
```

Các kiểm thử này xác minh hợp đồng ở phía tài nguyên mượn. Với `writeFile`, cần bổ sung kiểm thử đường thành công sử dụng file tạm, kiểm thử lỗi I/O khi hệ thống tệp có sự cố và xác nhận đường xử lý không coi file ghi một phần là báo cáo hoàn chỉnh. Trong thực tế, **việc file ghi xong và stream đã đóng không đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ**; nếu có yêu cầu chống mất dữ liệu khi mất điện, cần hợp đồng độ bền và cơ chế lưu trữ phù hợp.

## 7. Ba lỗi vòng đời điển hình

### 7.1. Đóng tài nguyên trước khi caller có thể sử dụng

Ví dụ sai:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static Stream<String> brokenLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines; // Đã đóng khi rời khối try.
    }
}
```

Phương thức trả một `Stream` nhưng đóng nó trước khi caller xử lý. Với stream gắn với file, caller có thể gặp lỗi khi đọc dữ liệu.

Một hợp đồng đúng khi **chuyển quyền sở hữu**:

```java
static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path); // Caller chịu trách nhiệm close.
}

static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines = openLines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

Nếu chỉ cần một danh sách đã nạp hoàn toàn, có thể dùng API trả `List<String>` bằng cách đọc hết và đóng file bên trong. Nhưng lựa chọn đó có chi phí bộ nhớ khác so với stream lười.

### 7.2. Đóng tài nguyên dùng chung từ một thành phần con

Giả sử ứng dụng tạo một HTTP client dùng chung và truyền nó cho nhiều service. Một service gọi `close()` của client sau mỗi request có thể làm hỏng các lời gọi khác. Hợp đồng phải nêu rõ **ai quản lý vòng đời client**: ví dụ container/application tạo và đóng khi ứng dụng dừng, các service chỉ mượn để thực hiện yêu cầu.

Không nên suy diễn từ tên `close` rằng mọi thư viện làm cùng một việc. Với kết nối từ pool, `close` thường trả kết nối về pool; với tài nguyên dùng chung, đóng có thể ảnh hưởng tất cả người dùng. Cần tuân theo vòng đời được tài liệu thư viện và thiết kế ứng dụng xác định.

### 7.3. Tác vụ bất đồng bộ sống lâu hơn phạm vi tài nguyên

Ví dụ về lỗi thiết kế: mở `InputStream` trong `try-with-resources`, khởi động một tác vụ đọc stream trên luồng khác rồi trả `CompletableFuture` ngay. Khi hàm trả về, stream đã bị đóng trong khi tác vụ chưa đọc xong.

Với API bất đồng bộ, cần quy định **tài nguyên thuộc ai cho đến lúc future/stream hoàn thành**, ai đóng khi thành công, thất bại hoặc hủy, và ai chịu trách nhiệm khi caller không chờ kết quả. Một lựa chọn là tạo và đóng tài nguyên **bên trong công việc bất đồng bộ**; lựa chọn khác là chuyển quyền sở hữu rõ cho một đối tượng kết quả có vòng đời. Chỉ chuyển `Writer` hoặc `InputStream` sang thread khác mà không xác định hợp đồng đồng thời thường gây lỗi khó tái hiện.

## 8. Tác dụng phụ ảnh hưởng đến kiểm thử và khả năng thay đổi

Khi tác dụng phụ được gom tại ranh giới rõ, logic nghiệp vụ có thể được kiểm thử bằng đối tượng giả phù hợp:

```java
interface NotificationSender {
    void send(Notification notification) throws DeliveryException;
}

record Notification(String recipientId, String text) {}

class DeliveryException extends Exception {
    DeliveryException(String message) {
        super(message);
    }
}
```

Nếu một service chỉ cần gửi thông báo, nó có thể phụ thuộc vào `NotificationSender` thay vì tự mở socket hoặc gọi API cụ thể. Một fake sender ghi lại thông báo được yêu cầu cho phép test logic lựa chọn nội dung. Tuy nhiên, test với fake **không xác nhận** adapter thật dùng đúng xác thực, timeout, retry hay hành vi lỗi của bên thứ ba: các phần đó cần kiểm thử tại ranh giới tích hợp.

Cần tránh **giấu tác dụng phụ sau tên gây hiểu nhầm**. Ví dụ `calculateInvoice()` nghe như chỉ tính toán nhưng âm thầm lưu hóa đơn và gửi email khiến caller dễ gọi lặp hoặc gọi trong luồng chỉ xem trước. Nên tách `calculateInvoice` khỏi `saveInvoice` và `sendInvoiceNotification` nếu các trách nhiệm thực sự độc lập và cần vòng đời khác nhau.

Mặt khác, không cần tạo interface cho mọi phép ghi hoặc mọi đối tượng tài nguyên. Chỉ thêm ranh giới khi nó giúp diễn đạt trách nhiệm, kiểm thử hành vi hoặc cô lập một phụ thuộc có lý do thay đổi rõ ràng.

## 9. Khi lỗi xảy ra giữa chừng: trách nhiệm và tính nguyên tử

Một hợp đồng có ghi dữ liệu phải trả lời cả câu hỏi **“đã ghi được bao nhiêu khi xảy ra lỗi?”**.

Trong ví dụ CSV, `writeRows` có thể đã xuất header và vài dòng trước khi ném `IOException`. Vì `Writer` thuộc caller, phương thức không thể tự biết có nên xóa toàn bộ file, quay lại vị trí cũ hay giữ dữ liệu đã viết. Do đó hợp đồng nêu rõ **có thể có kết quả một phần**.

Nếu nghiệp vụ yêu cầu báo cáo chỉ xuất hiện khi hoàn chỉnh, có thể thiết kế ở tầng cao hơn:

1. Ghi nội dung vào một **file tạm** trong cùng vùng lưu trữ phù hợp.
2. Hoàn thành ghi, đóng tài nguyên và kiểm tra lỗi.
3. Thay thế đích bằng thao tác di chuyển phù hợp với khả năng của hệ thống tệp.
4. Xác định cách xử lý khi di chuyển hoặc dọn file tạm thất bại.

Lưu ý: **atomic move** chỉ có thể dùng khi hệ thống tệp hỗ trợ và phải xử lý trường hợp không hỗ trợ; nguyên tử ở mức thay tên không tự bảo đảm tính bền vững khi mất điện. Vì vậy không nên tuyên bố `writeFile` trong ví dụ tự bảo đảm “hoặc toàn bộ hoặc không gì cả”.

Với database, việc ghi một phần được xử lý theo transaction và phạm vi commit; với hệ thống gửi thông điệp hay thanh toán, có thể phải dùng idempotency/outbox hoặc cơ chế đối soát. Quy tắc chung là **không làm lộ thành công giả khi tác dụng phụ đã thất bại hoặc chỉ hoàn thành một phần**.

## 10. Cách ghi hợp đồng rõ ràng trong Java

Một tài liệu API tốt nên diễn đạt các điều caller **cần biết để sử dụng đúng**, thay vì giải thích từng dòng cài đặt. Chẳng hạn:

```java
/**
 * Ghi các dòng báo cáo vào Writer do caller cung cấp.
 *
 * <p>Ghi đồng bộ, không đóng, không flush và không giữ Writer.
 * Caller quản lý vòng đời Writer. Nếu IOException xảy ra,
 * một phần đầu ra có thể đã được ghi.</p>
 *
 * @param rows danh sách các dòng hợp lệ, không chứa null
 * @param destination Writer còn mở do caller sở hữu
 * @throws NullPointerException nếu tham số hoặc phần tử null
 * @throws IOException nếu thao tác ghi thất bại
 */
static void writeRows(
        List<ReportRow> rows, Writer destination) throws IOException {
    // ... phần hiện thực đã trình bày ở trên
}
```

Đây là **minh họa cách ghi Javadoc**, không phải một định nghĩa thứ hai cần chép vào cùng lớp. Tài liệu nói về nghĩa và trách nhiệm, còn phần mã hiện thực phải tuân thủ đúng nội dung đó. Nếu một ngày chuyển từ ghi đồng bộ sang bất đồng bộ, sự thay đổi về **thời điểm hoàn tất và quyền sở hữu Writer** là thay đổi hợp đồng, dù tên phương thức vẫn giữ nguyên.

Không nên diễn giải `throws IOException` là lời hứa rằng **chỉ** có `IOException` có thể xảy ra: Java vẫn có unchecked exceptions, chẳng hạn do đầu vào null hoặc lỗi lập trình. Hợp đồng nên xác định rõ lỗi đầu vào và phản ứng với tình huống mà caller cần xử lý.

## 11. Checklist khi review API có tài nguyên

Trước khi chấp nhận một API nhận hoặc tạo tài nguyên, có thể lần lượt hỏi:

1. **API có tác dụng phụ nào?** Ghi dữ liệu, tiêu thụ input, gọi mạng, mutate collection, ghi log, thay trạng thái hay khởi động tác vụ nền?
2. **Ai sở hữu từng tài nguyên?** Được mượn, tạo cục bộ, chuyển giao hay cấp bởi pool/container?
3. **Ai đóng và khi nào?** Có `try-with-resources` hoặc ranh giới đóng rõ ràng trên cả đường thành công, lỗi và hủy không?
4. **Có flush hoặc giữ lại tham chiếu không?** Caller có được báo trước nếu phương thức ghi sau khi trả về hay không?
5. **Nếu thao tác thất bại một phần thì sao?** Có thể tiếp tục, thử lại, ghi đè, phục hồi hoặc phải loại bỏ kết quả?
6. **Gọi lại có an toàn không?** Có nguy cơ gửi trùng thông báo, tính tiền hai lần hoặc xuất thêm dòng không?
7. **Tài nguyên có dùng chung hoặc có nhiều luồng sử dụng không?** Hợp đồng của thư viện và thiết kế có hỗ trợ kiểu sử dụng ấy không?
8. **Kiểm thử có xác minh hợp đồng không?** Có thử đường I/O lỗi, caller còn sử dụng được tài nguyên mượn, tài nguyên sở hữu được đóng và trạng thái lỗi truyền đúng không?

Khi reviewer viết “phương thức này không nên đóng `Writer`”, nên kèm lý do: **caller sở hữu và còn cần ghi tiếp**. Khi reviewer đề nghị “hãy đóng stream tại đây”, cũng cần kiểm tra phương thức **có phải bên sở hữu stream hay đã chuyển quyền cho caller**. Như vậy review dựa trên hợp đồng thay vì một quy tắc máy móc.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hàm `render(Writer writer)` được caller truyền một `Writer` để ghép nhiều phần báo cáo. Nếu hàm tự gọi `writer.close()`, vấn đề nào xuất hiện?

**Câu 2.** Một factory trả `Stream<String>` lấy từ `Files.lines`. Ai phải đóng stream, và lỗi gì xảy ra nếu factory dùng `try-with-resources` trước khi trả về?

**Câu 3.** `writeFile` đã ghi 90% dữ liệu rồi gặp `IOException`. Có thể kết luận file hoàn chỉnh chỉ vì `try-with-resources` đã chạy không?

**Câu 4.** Một hàm gửi thanh toán có thể bị retry sau timeout. Những thông tin/hợp đồng nào cần làm rõ trước khi gọi lại?

**Câu 5.** Một service nhận HTTP client dùng chung do ứng dụng tạo. Service có nên đóng client sau mỗi request không?

**Gợi ý trả lời:** (1) Nó vi phạm quyền sở hữu, khiến caller không thể ghi tiếp và có thể gây lỗi hoặc kết thúc đầu ra sớm. (2) Caller nhận quyền sở hữu phải đóng; nếu factory đóng trước khi trả, stream không còn dùng đúng được. (3) Không: đóng không hoàn tác phần ghi trước đó; cần chính sách dữ liệu một phần hoặc cơ chế thay thế nguyên tử phù hợp. (4) Phải biết thao tác cũ có thể đã thành công, có idempotency key hay cơ chế truy vấn/đối soát không, và hậu quả khi lặp lại. (5) Không, trừ khi hợp đồng vòng đời giao trách nhiệm đó; tài nguyên dùng chung nên được chủ sở hữu ở tầng thích hợp đóng.

## 13. Ghi nhớ

**Một hợp đồng API đáng tin cậy phải nêu được cả kết quả, tác dụng phụ và trách nhiệm với tài nguyên.** Caller cần biết liệu lời gọi chỉ mượn tài nguyên, có chuyển giao quyền sở hữu hay tự tạo/đóng tài nguyên nội bộ; đồng thời biết điều gì xảy ra khi ghi thất bại hoặc thao tác chưa hoàn tất. Trong Java, `try-with-resources` là công cụ quan trọng để đóng tài nguyên đúng phạm vi, nhưng nó không thể thay thế một hợp đồng vòng đời rõ ràng. Khi quyền sở hữu và tác dụng phụ được thể hiện minh bạch, mã nguồn trở nên **dễ hiểu hơn, dễ kiểm chứng hơn và an toàn hơn khi thay đổi**.
