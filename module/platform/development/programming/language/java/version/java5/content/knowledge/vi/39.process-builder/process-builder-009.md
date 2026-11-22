# redirectErrorStream và hợp nhất luồng lỗi

## 1. Vì sao một tiến trình có hai luồng đầu ra?

Một chương trình con thường có:

- **stdout:** đầu ra chuẩn, có thể là kết quả hoặc thông tin tiến độ.
- **stderr:** đầu ra lỗi/chẩn đoán, có thể chứa cảnh báo và thông tin phục vụ điều tra.

Khi dùng cấu hình mặc định của `ProcessBuilder`, cha đọc hai luồng này qua hai pipe khác nhau. Nếu mục tiêu là thu một bản nhật ký chung, việc quản lý hai nguồn có thể không cần thiết. Khi đó có thể cấu hình:

```java
builder.redirectErrorStream(true);
```

Tùy chọn này đưa stderr của con đến cùng đích với stdout của con. Nó là cấu hình đầu ra khi khởi chạy tiến trình, không phải thao tác bắt ngoại lệ Java hay chuyển mọi lỗi thành kết quả thành công.

## 2. Đường đi của dữ liệu trước và sau khi gộp

Mặc định, `redirectErrorStream` là `false`:

```text
Con stdout → pipe stdout → cha đọc Process.getInputStream()
Con stderr → pipe stderr → cha đọc Process.getErrorStream()
```

Khi bật `true` và giữ stdout ở dạng pipe:

```text
Con stdout ─┐
            ├→ một pipe chung → cha đọc Process.getInputStream()
Con stderr ─┘

Process.getErrorStream() không còn dữ liệu stderr riêng.
```

Luồng do `getErrorStream()` trả về trong trường hợp này là một **null input stream** theo hợp đồng API: gọi `read()` trả `-1`, tức hết dữ liệu. Nó không phải một tham chiếu Java `null`.

Đích chung được quyết định bởi cấu hình `redirectOutput`. Nếu đã đặt `redirectError`, cấu hình chuyển hướng stderr riêng đó bị bỏ qua khi bật gộp. Các quy tắc này nằm trong [API ProcessBuilder.redirectErrorStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html#redirectErrorStream(boolean)).

Cấu hình phải có trước `start()`. Sửa builder sau khi một tiến trình đã chạy không nối lại các pipe của tiến trình đó.

## 3. Kết hợp với các đích stdout khác nhau

| Cấu hình | Dữ liệu stdout và stderr đi đâu? | Cha đọc bằng gì? |
|---|---|---|
| Không gộp, cả hai là `PIPE` | Hai pipe riêng | `getInputStream()` và `getErrorStream()` |
| Gộp, stdout là `PIPE` | Một pipe chung | `getInputStream()` |
| Gộp, stdout chuyển ra tệp | Cùng tệp đầu ra | Đọc tệp theo thiết kế; không có pipe đầu ra để lấy nội dung |
| Gộp, stdout là `INHERIT` | Cùng đích stdout được kế thừa từ cha | Không thu nội dung qua pipe của `Process` |
| Gộp, stdout là `DISCARD` | Cả hai bị loại bỏ | Không còn nội dung để đọc |

Ví dụ minh họa, đặt trong phương thức có sẵn một builder:

```java
builder.redirectErrorStream(true);
builder.redirectOutput(ProcessBuilder.Redirect.INHERIT);
```

Với cấu hình này, thông báo stderr của con cũng đi đến đích stdout mà con kế thừa, thay vì được cha thu riêng qua `getErrorStream()`.

Nếu muốn ghi nhật ký ra tệp, chọn rõ ghi mới hay nối thêm bằng cấu hình đầu ra phù hợp. Không nghĩ rằng `redirectErrorStream(true)` tự tạo tệp nhật ký hoặc tự in ra màn hình: nó chỉ gộp đường đi, còn đích cụ thể do cấu hình khác quyết định.

## 4. Khi nào nên gộp, khi nào cần giữ riêng?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Hiển thị nhật ký chung của công cụ | Gộp có thể giúp đơn giản hóa việc tiêu thụ dữ liệu |
| Lưu toàn bộ thông báo vào một tệp | Gộp rồi chuyển stdout ra tệp |
| stdout chứa JSON/CSV hoặc dữ liệu nhị phân để phân tích | Thường cần giữ stderr riêng |
| Cần biết chắc byte/dòng nào đến từ stderr | Giữ riêng hoặc dùng giao thức có thông tin nguồn do bên phát cung cấp |
| Không cần lưu đầu ra nhưng phải xác nhận kết quả | Có thể chuyển hướng/loại bỏ theo yêu cầu, vẫn kiểm tra mã thoát |

Ví dụ, một công cụ in JSON hợp lệ ra stdout nhưng in cảnh báo ra stderr. Nếu gộp, bộ phân tích JSON của cha sẽ nhận cả cảnh báo và có thể không đọc được kết quả nữa. Gộp tiện cho nhật ký không có nghĩa phù hợp với mọi giao thức dữ liệu.

Sau khi đã gộp, pipe chung không gắn thêm nhãn “stdout” hay “stderr” cho từng byte. Cha không thể tái tạo nguồn chỉ bằng cách gọi getter khác. Nếu ví dụ hoặc công cụ dùng tiền tố như `OUT:`/`ERR:`, đó là nội dung do bên phát tự viết, không phải nhãn tự động của `ProcessBuilder`.

## 5. Gộp không tự giải quyết việc tắc bộ đệm

Pipe có dung lượng hữu hạn. Nếu con ghi nhiều mà cha không đọc, con có thể bị chặn khi bộ đệm đầy. Nếu cha lúc đó chỉ chờ con kết thúc, hai bên có thể chờ nhau.

Bật gộp giúp chỉ còn một nguồn cần đọc, nhưng nguồn ấy **vẫn phải được tiêu thụ**. Một cấu trúc hữu ích là:

```text
Luồng đọc: đọc liên tục pipe chung trong lúc con đang chạy
Luồng điều phối: chờ tiến trình có thời hạn và kiểm tra kết quả
Sau khi con kết thúc: chờ phần đọc hoàn thành trong giới hạn phù hợp
```

Không gộp thì hai luồng phải được tiêu thụ theo cách tránh chặn lẫn nhau, thường là đọc đồng thời. Đọc hết stdout trước rồi mới đọc stderr có thể bỏ mặc một pipe đang đầy.

Tài liệu [Process](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html) mô tả nguy cơ chặn hoặc bế tắc nếu không xử lý kịp dữ liệu đầu vào/đầu ra.

Đọc qua `readLine()` cũng có đặc tính riêng: lời gọi có thể chờ đến dấu kết thúc dòng hoặc hết dữ liệu, và chuỗi trả về không chứa dấu kết thúc dòng. Không dùng cách đọc dòng nếu cần bảo toàn nguyên byte hoặc nội dung không phải văn bản. Xem [API BufferedReader.readLine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html#readLine()).

## 6. Ví dụ đầy đủ: một tác vụ đọc luồng gộp trong lúc cha chờ

Lưu mã sau vào `MergedErrorStreamDemo.java`. Chương trình con phát đúng ba dòng nhỏ; ví dụ thu chúng vào danh sách để kiểm tra. Đây không phải thiết kế lưu toàn bộ nhật ký không giới hạn trong bộ nhớ.

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MergedErrorStreamDemo {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--child")) {
            System.out.println("OUT: start");
            System.out.flush();
            System.err.println("ERR: diagnostic");
            System.err.flush();
            System.out.println("OUT: done");
            System.out.flush();
            return;
        }

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        Path javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable.toString(),
                "-cp", System.getProperty("java.class.path"),
                MergedErrorStreamDemo.class.getName(),
                "--child");
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.PIPE);

        Process child = builder.start();
        ExecutorService readerExecutor = Executors.newSingleThreadExecutor();
        try {
            child.getOutputStream().close();
            Future<List<String>> captured = readerExecutor.submit(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(
                                child.getInputStream(),
                                StandardCharsets.UTF_8))) {
                    List<String> lines = new ArrayList<>();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        lines.add(line);
                    }
                    return lines;
                }
            });

            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child process timed out");
            }
            List<String> lines = captured.get(2, TimeUnit.SECONDS);
            boolean hasStdout = lines.contains("OUT: start")
                    && lines.contains("OUT: done");
            boolean hasStderr = lines.contains("ERR: diagnostic");
            boolean errorStreamEof = child.getErrorStream().read() == -1;
            int exitCode = child.exitValue();

            if (lines.size() != 3 || !hasStdout || !hasStderr
                    || !errorStreamEof || exitCode != 0) {
                throw new AssertionError("Unexpected captured result");
            }
            System.out.println("merged lines=" + lines.size());
            System.out.println("has stdout=" + hasStdout);
            System.out.println("has stderr=" + hasStderr);
            System.out.println("error stream EOF=" + errorStreamEof);
            System.out.println("exit=" + exitCode);
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(5, TimeUnit.SECONDS);
            }
            readerExecutor.shutdownNow();
            child.getInputStream().close();
            child.getErrorStream().close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 MergedErrorStreamDemo.java
java MergedErrorStreamDemo
```

Stdout khi chương trình con khởi chạy và hoàn thành trong thời hạn:

```text
merged lines=3
has stdout=true
has stderr=true
error stream EOF=true
exit=0
```

### Vì sao kết quả không in nguyên thứ tự ba dòng?

Mục tiêu của bài kiểm tra là xác nhận luồng chung chứa đủ nội dung của cả hai nguồn và luồng stderr riêng đã hết dữ liệu. Nó không dựa vào một lời hứa tổng quát rằng thông báo từ hai luồng luôn có thứ tự thời gian chính xác.

Chương trình con có các lệnh `flush` tường minh và dữ liệu nhỏ, nhưng chương trình thực tế có thể dùng nhiều luồng, nhiều lớp bộ đệm hoặc thư viện ghi khác nhau. Thứ tự mà cha nhận được không nhất thiết phản ánh đúng thứ tự sự kiện nghiệp vụ. Các phần ghi còn có thể xen kẽ, nên không giả định mọi dòng luôn giữ nguyên như một đơn vị nguyên tử.

Nếu thứ tự sự kiện hoặc nguồn là điều kiện của giao thức, hãy thiết kế một đầu ra có cấu trúc và thông tin cần thiết ngay từ phía phát. Chỉ gộp hai đích dữ liệu không tự cung cấp các bảo đảm đó.

### Vì sao đọc ở một tác vụ riêng?

Tác vụ gửi vào `ExecutorService` bắt đầu đọc `child.getInputStream()` trong lúc luồng chính chờ tiến trình kết thúc. Nhờ vậy việc chờ không bỏ mặc pipe chung.

Sau khi con kết thúc, `captured.get(2, TimeUnit.SECONDS)` chờ kết quả đọc có thời hạn. Thời hạn đọc này khác thời hạn chờ tiến trình. Với các công cụ sinh tiến trình hậu duệ, việc tiến trình đang theo dõi đã thoát không phải lúc nào cũng đủ để mọi đầu ghi được đóng ngay; cần quản lý vòng đời tương ứng.

`finally` yêu cầu dừng nếu con còn sống, ngừng executor và đóng các stream. Ví dụ chỉ có một JVM con do chính nó kiểm soát, không sinh hậu duệ. Hệ thống chạy công cụ bất kỳ cần chính sách dọn dẹp đầy đủ cho cây tiến trình và các trường hợp ngắt.

### Vì sao có stderr mà exit vẫn bằng 0?

JVM con in `ERR: diagnostic` rồi trở về bình thường. Nó đã dùng stderr để ghi thông tin chẩn đoán nhưng không báo thất bại qua mã thoát.

Từ đó có hai kết luận cần giữ riêng:

- Có nội dung trên stderr không tự chứng minh tác vụ thất bại.
- Không có nội dung trên stderr không tự chứng minh tác vụ thành công.

Mã thoát, đầu ra và điều kiện kết quả phải được diễn giải theo hợp đồng của chương trình đích. Bật gộp không thay đổi quy ước mã thoát.

### Vì sao chọn UTF-8?

Cha cần biết cách biến byte thành ký tự. Ví dụ chỉ phát các ký tự ASCII, cũng hợp lệ dưới UTF-8, nên kết quả không phụ thuộc chữ có dấu của môi trường console.

Với công cụ thật, chọn charset theo đầu ra mà công cụ cam kết. `redirectErrorStream` không chuyển đổi mã hóa. Nếu stdout và stderr dùng các mã hóa không tương thích, việc gộp byte rồi dùng một bộ giải mã duy nhất còn có thể làm dữ liệu khó đọc.

## 7. Giới hạn tài nguyên khi áp dụng

Ví dụ gom ba dòng vào `ArrayList` để giữ chương trình dễ kiểm chứng. Với nhật ký lớn, cần chọn một trong các cách phù hợp:

- Ghi liên tục ra tệp có chính sách dung lượng.
- Chuyển tiếp đến nơi tiêu thụ theo tốc độ phù hợp.
- Chỉ giữ một lượng cuối hữu hạn để chẩn đoán.
- Giới hạn số byte/ký tự hoặc dòng, đồng thời quyết định việc đọc tiếp hay dừng tiến trình khi vượt giới hạn.

Không chỉ ngừng đọc khi danh sách đầy mà vẫn để con chạy và chờ nó thoát: pipe có thể lại đầy. Chính sách bộ nhớ phải đi cùng chính sách tiêu thụ hoặc dừng công việc.

Nếu nơi nhận đầu ra rất chậm, tác vụ đọc cũng có thể bị chặn ở nơi ghi tiếp theo. Việc có một luồng đọc riêng không xóa bỏ mọi khả năng chờ; cần xem toàn bộ đường đi dữ liệu.

stdin không bị thay đổi bởi `redirectErrorStream`. Nếu công cụ chờ đầu vào, cha vẫn phải gửi dữ liệu hoặc đóng đầu vào theo giao thức. Trong ví dụ, `child.getOutputStream().close()` báo rằng cha không gửi thêm dữ liệu.

## 8. Lỗi thường gặp

| Lỗi | Cách sửa cách hiểu |
|---|---|
| Bật gộp nhưng vẫn chờ đọc stderr riêng để lấy lỗi | Đọc pipe stdout chung nếu đích vẫn là `PIPE` |
| So `getErrorStream() == null` | Hợp đồng trả một luồng hết dữ liệu, không phải tham chiếu `null` |
| Bật gộp rồi chờ con mà không đọc đầu ra | Vẫn cần tiêu thụ hoặc chuyển hướng luồng chung |
| Đặt `redirectError(file)` và nghĩ nó thắng cấu hình gộp | Khi gộp bật, chuyển hướng stderr riêng bị bỏ qua |
| Gộp cảnh báo vào dữ liệu JSON rồi phân tích như JSON thuần | Giữ dữ liệu và chẩn đoán riêng hoặc đổi giao thức |
| Tìm chữ “error” để quyết định tác vụ thành công/thất bại | Dùng hợp đồng kết quả, gồm mã thoát và nội dung cần kiểm tra |
| Coi gộp luồng là sắp xếp sự kiện theo thời gian | Muốn thứ tự chắc chắn phải có giao thức phát phù hợp |

## 9. Bài thực hành

1. Đổi sang không gộp và dự đoán vì sao phép kiểm tra `has stderr` trên stdout chung sẽ không đạt. Sau đó thiết kế việc đọc hai luồng riêng đồng thời.
2. Đổi đích stdout thành một tệp, bật gộp và xác nhận tệp có cả ba dòng. Không tiếp tục kỳ vọng `getInputStream()` chứa cùng dữ liệu.
3. Cho con in một cảnh báo nhưng thoát với mã 0, rồi một lần khác không in cảnh báo nhưng thoát với mã khác 0. Viết quy tắc diễn giải hai kết quả.
4. Thiết kế cách chỉ giữ phần cuối của nhật ký mà vẫn đọc hết pipe khi công cụ chạy lâu.

Trước khi dùng tùy chọn gộp, hãy xác định đầu ra dùng cho người đọc hay cho bộ phân tích, có cần phân biệt nguồn không và ai sẽ tiêu thụ luồng chung trong suốt thời gian tiến trình chạy.
