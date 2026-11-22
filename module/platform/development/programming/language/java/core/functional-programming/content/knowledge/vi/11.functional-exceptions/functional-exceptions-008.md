# Giữ phần đọc ghi và tác dụng phụ ở ranh giới dễ kiểm soát

Trong lập trình hàm với Java, một nguyên tắc quan trọng là **đưa các thao tác đọc/ghi (I/O) và tác dụng phụ ra ranh giới của chương trình**, còn phần xử lý quy tắc nghiệp vụ ở giữa nhận dữ liệu đầu vào và trả kết quả rõ ràng. Nguyên tắc này đặc biệt hữu ích khi xử lý **ngoại lệ**: mã đọc file, gọi mạng hoặc ghi cơ sở dữ liệu có thể thất bại vì môi trường, trong khi phép tính thuần túy có thể được kiểm thử bằng dữ liệu cho trước.

Mục tiêu không phải loại bỏ mọi tác dụng phụ. Ứng dụng vẫn cần đọc, ghi, gửi thông báo, lưu dữ liệu và ghi log. Mục tiêu là **biết chúng xảy ra ở đâu, phụ thuộc vào điều gì, và lỗi được xử lý tại ranh giới nào**.

## 1. Nhận diện tác dụng phụ và ranh giới

Một hàm có *tác dụng phụ quan sát được* khi nó làm thay đổi hoặc phụ thuộc vào trạng thái ngoài kết quả trả về, ví dụ:

- Đọc/ghi file, socket, HTTP, cơ sở dữ liệu, hàng đợi hoặc console.
- Ghi log, gửi email, phát sự kiện hay cập nhật cache dùng chung.
- Sửa một đối tượng/collection mà mã gọi còn quan sát được; thay đổi biến toàn cục hoặc thuộc tính chia sẻ.
- Tự lấy thời gian hiện tại bằng `Instant.now()`, lấy giá trị ngẫu nhiên hoặc đọc biến môi trường. Đây là các **đầu vào ẩn**, khiến cùng tham số có thể cho kết quả khác nhau.

Ngược lại, một hàm xử lý thuần túy nhận đầy đủ đầu vào qua tham số, trả kết quả bằng giá trị trả về và không tạo tác dụng phụ quan sát được. Ví dụ:

```java
static long total(int quantity, long unitPrice) {
    if (quantity <= 0 || unitPrice < 0) {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }
    return Math.multiplyExact((long) quantity, unitPrice);
}
```

Đây là **đoạn minh họa đặt trong một class**. Với cùng `quantity` và `unitPrice`, kết quả hoặc ngoại lệ luôn có cùng nguyên nhân. Việc ném `IllegalArgumentException` xác định lỗi đầu vào và không tự gây I/O. Java không buộc mọi ngoại lệ phải là tác dụng phụ; điều quan trọng ở đây là **khả năng dự đoán, không có phụ thuộc môi trường ẩn và không thay đổi trạng thái bên ngoài**.

> Phân biệt: cập nhật biến cục bộ trong một hàm không nhất thiết là tác dụng phụ quan sát được, miễn trạng thái đó không bị rò ra ngoài. Trong khi đó, `list.sort(...)` trên list do bên gọi truyền vào làm thay đổi dữ liệu có thể quan sát được.

## 2. Mô hình “lõi xử lý – vỏ tương tác”

Một dòng xử lý thường nên đi theo hướng:

```text
Biên vào (I/O)           Lõi xử lý dữ liệu             Biên ra (I/O)
Đọc file / HTTP   --->   Parse -> Validate -> Compute   --->   Ghi file / DB / HTTP
   IOException             Lỗi dữ liệu rõ nghĩa                 IOException
```

**Biên vào** chuyển dữ liệu của hệ thống bên ngoài thành tham số Java, ví dụ `List<String>`, `Order` hoặc `byte[]`. **Lõi xử lý** thực hiện các phép biến đổi bằng cách tạo giá trị mới. **Biên ra** nhận kết quả hoàn chỉnh và chịu trách nhiệm thực hiện tác động đến thế giới bên ngoài.

Từ đó có ba quy tắc:

1. Không giấu việc đọc file, gọi mạng hoặc ghi log trong `map`, `filter`, `reduce` chỉ vì có thể viết bằng lambda.
2. Lõi xử lý không cần biết file nằm ở đâu, logger nào được dùng hoặc HTTP client nào được khởi tạo. Truyền vào dữ liệu đã đọc, hoặc đưa nguồn/đích I/O qua interface tại lớp điều phối.
3. Bắt, chuyển nghĩa và báo cáo lỗi ở nơi hiểu **ngữ cảnh xử lý**: lỗi dữ liệu có thể đến từ lõi; `IOException` do adapter đọc/ghi phát sinh; quyết định retry, dừng hay trả lỗi cho người dùng nằm ở lớp biên.

Lõi xử lý có thể dùng `Stream`, vòng `for`, `Optional` hoặc record; dùng cú pháp hàm không tự động làm mã trở nên thuần túy.

## 3. Ví dụ hoàn chỉnh Java 17+: tách đọc, tính toán và ghi

Bài toán: nguồn cung cấp mỗi dòng dưới dạng `mã,số_lượng`. Chương trình kiểm tra đầu vào, nhân số lượng với đơn giá cố định `100`, rồi xuất `mã,thành_tiền`. Cùng một lõi xử lý có thể chạy với dữ liệu giả trong bộ nhớ hoặc file thật.

Lưu toàn bộ thành `SideEffectBoundaryDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class SideEffectBoundaryDemo {

    @FunctionalInterface
    interface Source {
        List<String> read() throws IOException;
    }

    @FunctionalInterface
    interface Sink {
        void write(List<String> rows) throws IOException;
    }

    record Order(String code, int quantity) {}

    // Lõi: kiểm tra và phân tích một dòng, không đọc file hay in log.
    static Order parse(String raw) {
        String[] parts = raw.split(",", -1);
        if (parts.length != 2 || parts[0].isBlank()) {
            throw new IllegalArgumentException("Sai cấu trúc: " + raw);
        }

        int quantity;
        try {
            quantity = Integer.parseInt(parts[1].trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Sai số lượng: " + raw, e);
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương: " + raw);
        }
        return new Order(parts[0].trim(), quantity);
    }

    // Lõi: tạo giá trị mới, không ghi vào Order hay hệ thống bên ngoài.
    static String calculate(Order order) {
        long amount = order.quantity() * 100L;
        return order.code() + "," + amount;
    }

    static List<String> transform(List<String> rawLines) {
        return rawLines.stream()
                .map(SideEffectBoundaryDemo::parse)
                .map(SideEffectBoundaryDemo::calculate)
                .toList();
    }

    // Vỏ điều phối: đọc một lần, tính toán, sau đó mới ghi một lần.
    static void run(Source source, Sink sink) throws IOException {
        List<String> input = source.read();
        List<String> output = transform(input);
        sink.write(output);
    }

    public static void main(String[] args) {
        if (args.length != 0 && args.length != 2) {
            System.err.println(
                    "Cách dùng: java SideEffectBoundaryDemo [input.csv output.csv]"
            );
            return;
        }

        try {
            if (args.length == 0) {
                // Adapter trong bộ nhớ: không cần file thật để thử lõi.
                run(
                        () -> List.of("A01,2", "B02,3"),
                        lines -> lines.forEach(System.out::println)
                );
                return;
            }

            Path input = Path.of(args[0]);
            Path output = Path.of(args[1]);

            // Adapter thật: I/O được đặt tại hai điểm rõ ràng.
            run(
                    () -> Files.readAllLines(input, StandardCharsets.UTF_8),
                    lines -> {
                        Files.write(output, lines, StandardCharsets.UTF_8);
                    }
            );
            System.out.println("Đã ghi " + output.getFileName());

        } catch (IOException | IllegalArgumentException e) {
            // Biên chương trình quyết định cách báo lỗi ra bên ngoài.
            System.err.println("Không xử lý được: " + e.getMessage());
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 SideEffectBoundaryDemo.java
java SideEffectBoundaryDemo
```

Kết quả stdout chính xác khi không truyền tham số:

```text
A01,200
B02,300
```

Để dùng I/O thật, tạo file `input.csv` UTF-8 với nội dung:

```text
A01,2
B02,3
```

Sau đó chạy:

```bash
java SideEffectBoundaryDemo input.csv output.csv
```

Khi đọc và ghi thành công, console hiển thị `Đã ghi output.csv`; file `output.csv` có hai dòng `A01,200` và `B02,300`. Nếu đường dẫn hoặc quyền truy cập không hợp lệ, adapter có thể ném `IOException` và phần `catch` tại `main` báo lỗi bằng stderr. Thông báo cụ thể từ hệ điều hành có thể khác nhau.

**Vì sao ví dụ này đặt ranh giới đúng chỗ?**

- `Source.read()` là nơi duy nhất nhận dữ liệu từ môi trường. `Sink.write(...)` là nơi thực hiện hành động ra ngoài, như in hay ghi file.
- `parse`, `calculate` và `transform` không gọi I/O. Ta có thể truyền `List.of("A01,2")` cho `transform` và kiểm tra kết quả mà không cần file hoặc mock HTTP.
- `Order` là `record`, giúp thể hiện một giá trị dữ liệu rõ ràng; kết quả `calculate` là chuỗi mới, không sửa đối tượng đầu vào.
- `run` nhận hai hành vi thông qua interface riêng. Các interface **cho phép `throws IOException`**, nên lambda đọc/ghi file hợp lệ mà không cần chôn `try/catch` vào mỗi phần tử của stream.
- `transform` chạy xong rồi mới gọi `sink.write`. Nếu dòng thứ hai sai cú pháp, phần ghi **chưa được gọi trong lần chạy đó**. Đây là một bảo đảm về thứ tự điều phối, không đồng nghĩa thao tác `Files.write` tự động có transaction.

`Stream.toList()` (Java 16+) cho ra list kết quả không thể sửa. Trong ví dụ, sink chỉ cần đọc các dòng để xuất nên không cần list có thể thay đổi.

## 4. Ngoại lệ cần đi qua ranh giới nào?

Có hai nhóm lỗi đáng phân biệt:

| Nguồn lỗi | Ví dụ | Nơi thường xử lý |
| --- | --- | --- |
| Dữ liệu/quy tắc nghiệp vụ | Dòng không đúng `mã,số_lượng`, số lượng không dương | Hàm parse/validate phát hiện; lớp điều phối hoặc API boundary quyết định báo lỗi, bỏ dòng theo chính sách hay yêu cầu nhập lại |
| Môi trường/I/O | File không tồn tại, mất kết nối, hết dung lượng, lỗi quyền ghi | Adapter ném lỗi đúng ngữ cảnh; tầng biên quyết định retry, phản hồi, hủy thao tác hoặc ghi nhận sự cố |

`IOException` là **checked exception**: phương thức có thể ném nó phải khai báo `throws` hoặc xử lý. Trong khi đó, `IllegalArgumentException` là **unchecked exception** (`RuntimeException`). Việc lựa chọn loại ngoại lệ tùy vào hợp đồng API, chứ không phải cứ lỗi I/O là phải nuốt tại chỗ.

Trong ví dụ, `parse` chuyển `NumberFormatException` thành `IllegalArgumentException` kèm **nguyên nhân gốc** `e`. Việc này cho người gọi biết lỗi thuộc cấu trúc dữ liệu đầu vào, đồng thời vẫn giữ thông tin nguyên nhân để chẩn đoán. `main` chỉ bắt ở điểm có khả năng đưa thông báo phù hợp cho người chạy.

**Đừng bắt ngoại lệ rồi trả kết quả giả để pipeline “chạy tiếp”:**

```java
// Không nên: lỗi đọc dữ liệu bị biến thành danh sách trống.
try {
    return Files.readAllLines(path);
} catch (IOException e) {
    return List.of();
}
```

Đây là đoạn minh họa trong một phương thức có biến `path`; không phải chương trình độc lập. Kết quả rỗng lúc này không phân biệt “file hợp lệ nhưng không có dòng” với “không đọc được file”. Nếu nghiệp vụ **thực sự quy định** lỗi nguồn được hiểu là không có dữ liệu, phải ghi chính sách đó trong hợp đồng và kiểm thử rõ ràng; không áp dụng như mặc định.

## 5. Vì sao không nên đưa I/O thẳng vào `Stream.map()`?

Dễ viết một lambda như sau:

```java
List<String> contents = paths.stream()
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
```

Đây là đoạn minh họa cần các import `java.io.IOException`, `java.io.UncheckedIOException`, `java.nio.file.Files`, `java.util.List`; `paths` có kiểu `List<Path>`. Mã có thể hợp lệ, nhưng kéo theo các hệ quả:

- `map` giờ phụ thuộc vào file system và có thể thất bại ngoài phép biến đổi dữ liệu; khó kiểm thử độc lập.
- Trong stream, các phép trung gian như `map` là **lazy**. Lệnh đọc file trong lambda chỉ được gọi khi terminal operation như `toList()` tiêu thụ phần tử.
- Nếu thao tác lỗi giữa chừng, một số file có thể đã được đọc; dùng stream song song còn làm việc kiểm soát thứ tự và tác dụng phụ phức tạp hơn.
- Việc đổi sang `UncheckedIOException` là một chính sách chuyển ngoại lệ, **không làm I/O trở thành thuần túy**. Nếu phải dùng kiểu này, hãy chuyển có chủ đích ở adapter và giữ `cause`, rồi xử lý ở ranh giới thích hợp.

Khi API yêu cầu `Function<T,R>`, `Predicate<T>` hoặc `Consumer<T>`, các interface chuẩn này không khai báo checked exception. **Đừng ép mọi thao tác I/O vào chúng**. Có thể đọc dữ liệu trước khi chạy stream, tạo một interface `throws IOException` riêng như ví dụ, hoặc chọn API bất đồng bộ hỗ trợ trạng thái thành công/thất bại khi bài toán cần.

Tương tự, gọi `forEach(x -> repository.save(x))` có thể hữu ích ở tầng orchestration nếu thật sự muốn phát lệnh ghi cho từng phần tử, nhưng hãy xác định rõ cách xử lý lỗi, retry, thứ tự và khả năng đã ghi một phần. Cú pháp `forEach` không làm các lệnh ghi có tính nguyên tử.

## 6. Kiểm thử lõi và kiểm thử ranh giới

Với thiết kế ở ví dụ, kiểm thử đơn vị của lõi rất đơn giản:

```java
List<String> actual = SideEffectBoundaryDemo.transform(
        List.of("X1,2", "Y2,1")
);
if (!actual.equals(List.of("X1,200", "Y2,100"))) {
    throw new AssertionError(actual);
}
```

Đây là đoạn kiểm thử minh họa đặt trong mã Java cùng package và có `import java.util.List;`. `transform` không cần môi trường thật.

Để kiểm thử `run`, có thể thay adapter bằng một sink giả lưu kết quả vào bộ nhớ:

```java
List<String> saved = new java.util.ArrayList<>();
SideEffectBoundaryDemo.run(
        () -> List.of("X1,2"),
        rows -> saved.addAll(rows)
);
if (!saved.equals(List.of("X1,200"))) {
    throw new AssertionError(saved);
}
```

Đoạn kiểm thử thứ hai cần đặt trong phương thức có `throws IOException` hoặc xử lý ngoại lệ; dùng `java.util.List` và `java.io.IOException` phù hợp. Đây là kiểm thử hành vi tại ranh giới: `saved` là trạng thái **của adapter giả**, không phải tác dụng phụ bên trong `transform`.

Cũng nên kiểm tra:

1. **Lỗi dữ liệu:** truyền `"X1,abc"` vào `transform`, xác nhận `IllegalArgumentException`; đảm bảo sink chưa được gọi nếu việc biến đổi chưa hoàn tất.
2. **Lỗi nguồn:** triển khai `Source` giả ném `IOException`; xác nhận `run` lan truyền lỗi và sink không chạy.
3. **Lỗi đích:** triển khai `Sink` giả ném `IOException`; xác nhận lỗi tới caller. Lúc này lõi có thể đã tính xong, nhưng kết quả chưa được lưu thành công.
4. **I/O thật:** kiểm thử tích hợp bằng file tạm và charset UTF-8, xác nhận dữ liệu ghi đúng và tài nguyên được quản lý đúng cách.

Các ca kiểm thử này tập trung vào **hợp đồng và khả năng quan sát lỗi**, không đòi hỏi mock mọi hàm tính toán thuần túy.

## 7. Quản lý tài nguyên và nhất quán dữ liệu ở biên

Giữ I/O ở biên còn giúp nhìn thấy vòng đời tài nguyên:

```java
try (var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
    // Đọc từ reader và chuyển dữ liệu đã đọc tới lõi xử lý.
}
```

Đây là đoạn minh họa cần import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`; biến `input` là `Path`. `try-with-resources` đảm bảo tài nguyên được đóng khi thoát khối, cả khi xảy ra ngoại lệ. Nếu thao tác trong khối và thao tác đóng cùng ném lỗi, Java có thể lưu lỗi đóng dưới dạng *suppressed exception*; đừng làm mất nguyên nhân khi báo cáo.

Đọc toàn bộ file bằng `Files.readAllLines` phù hợp dữ liệu nhỏ/vừa; với file lớn, streaming/lặp qua `BufferedReader` giúp kiểm soát bộ nhớ. Ngay cả khi xử lý theo luồng từng dòng, vẫn cần xác định rõ ranh giới mở/đóng tài nguyên và xem xét xử lý lỗi giữa chừng.

**Thứ tự “tính xong rồi mới ghi” giúp giảm ghi dở do lỗi biến đổi**, nhưng không đảm bảo hệ thống ngoài chỉ nhận thay đổi một lần hoặc thay đổi tất cả cùng lúc. Ví dụ:

- `Files.write` có thể thất bại khi đang ghi, để lại file chưa hoàn chỉnh. Nếu cần cập nhật file theo cách “thay thế toàn bộ”, cân nhắc ghi sang file tạm cùng thư mục và đổi tên bằng `Files.move` với `ATOMIC_MOVE` khi hệ thống file hỗ trợ; vẫn phải xử lý lỗi và dọn file tạm.
- Ghi nhiều bản ghi DB có thể cần transaction; việc bọc các lời gọi `save` trong stream không thay transaction.
- Gọi HTTP có thể thành công ở server rồi thất bại ở thời điểm client nhận phản hồi; retry mù quáng có nguy cơ tạo thao tác lặp. Cần chính sách idempotency hoặc nhận diện kết quả.
- Log/chỉ số lỗi đặt gần adapter hoặc tầng điều phối giúp chẩn đoán mà không làm mỗi hàm parse phải biết hệ thống observability.

## 8. Truyền các phụ thuộc thay vì tự truy cập môi trường

Nếu một phép tính cần “thời điểm hiện tại”, đừng ẩn lệnh đọc đồng hồ trong hàm:

```java
// Đầu vào ẩn, không ổn định qua thời gian:
boolean expired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
```

Thay vào đó, tầng biên đọc thời gian một lần và truyền vào:

```java
// Cùng hai tham số luôn cho cùng kết quả:
static boolean expired(java.time.Instant deadline,
                       java.time.Instant now) {
    return now.isAfter(deadline);
}
```

Hai đoạn minh họa cần đặt trong class Java, import `java.time.Instant` nếu không dùng tên đầy đủ. Tương tự với ngẫu nhiên, locale, cấu hình hoặc dữ liệu từ bên thứ ba: khi có thể, chuyển chúng thành **giá trị đầu vào tường minh** cho lõi xử lý. Nếu nhiều nơi cần truy cập đồng hồ, có thể tiêm `Clock` ở adapter và lấy `Instant` tại điểm điều phối.

## 9. Những lỗi thiết kế dễ gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `Files.readString` hoặc `client.send` trực tiếp từ một phép `map` xử lý nghiệp vụ | Hàm phụ thuộc môi trường; checked exception khó quản lý | Adapter đọc trước, chuyển dữ liệu vào `map`; hoặc dùng interface chuyên cho I/O |
| `catch (Exception e) { return null; }` ở mọi lớp | Mất nguyên nhân, `null` lan sâu, khó xác định lỗi | Chỉ xử lý ở nơi có chính sách phục hồi; giữ cause khi chuyển nghĩa |
| Ghi dữ liệu ngay khi đang xác thực từng phần tử | Dòng lỗi cuối có thể xuất hiện sau khi đã ghi nhiều dòng đầu | Xác thực/biến đổi trước khi ghi nếu yêu cầu all-or-nothing; khi cần streaming phải định nghĩa phục hồi |
| Log, gửi email, cập nhật counter trong hàm tính toán | Test phụ thuộc hệ thống ngoài; gọi lại hàm gây hiệu ứng lặp | Trả kết quả/sự kiện dữ liệu rồi để lớp biên quyết định phát hành |
| Catch `IOException` và biến thành `List.of()` | Lỗi đọc bị hiểu là “không có dữ liệu” | Phân biệt kết quả rỗng hợp lệ và lỗi bằng ngoại lệ hoặc kiểu kết quả |
| Giả định `forEach` hoặc parallel stream an toàn cho mọi tác dụng phụ | Race condition, thứ tự không rõ, ghi một phần | Điều phối tác dụng phụ có kiểm soát; cân nhắc transaction và idempotency |
| Dùng `finally` thủ công nhưng quên đóng tài nguyên | Rò rỉ file descriptor/connection | Ưu tiên `try-with-resources` tại điểm sở hữu tài nguyên |

Một trường hợp đặc biệt là `InterruptedException` khi tác vụ chờ bị ngắt: nếu bắt để chuyển thành exception khác trong worker thread, thông thường cần gọi `Thread.currentThread().interrupt()` để khôi phục cờ ngắt trước khi lan truyền chính sách dừng; tránh nuốt tín hiệu hủy tác vụ.

## 10. Tự đánh giá trước khi kết thúc một luồng xử lý

Hãy thử trả lời những câu sau khi nhìn vào mã:

1. Những câu lệnh nào thật sự đọc/ghi bên ngoài, và chúng có nằm tại lớp adapter hoặc biên điều phối có thể nhìn thấy không?
2. Có thể chạy lại hàm xử lý bằng cùng dữ liệu và nhận cùng kết quả, không cần file, đồng hồ, mạng hoặc DB không?
3. Lỗi dữ liệu và lỗi môi trường có bị trộn thành một giá trị giả (`null`, chuỗi rỗng, danh sách rỗng) không?
4. Nếu lỗi xảy ra ở giữa, phần dữ liệu ngoài nào đã có thể thay đổi? Có cần transaction, file tạm, retry idempotent hoặc cơ chế bù trừ không?
5. Ai sở hữu việc đóng tài nguyên, ghi log, chuyển exception thành thông báo API/CLI và quyết định retry?

**Ghi nhớ:** Đưa I/O và tác dụng phụ vào những ranh giới dễ thấy; giữ phần parse/validate/compute trên giá trị dữ liệu; để ngoại lệ đi tới nơi có đủ ngữ cảnh để xử lý. Cách này làm mã Java dùng lambda/stream dễ đọc, dễ kiểm thử và dễ kiểm soát lỗi hơn.
