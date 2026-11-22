# Đích ghi log trong kiến trúc logging của Java

## 1. Đích ghi log là gì và nằm ở đâu trong kiến trúc?

Khi ứng dụng thực thi một câu lệnh ghi log, thông điệp được tạo ra chưa chắc đã được lưu ở đâu đó. Hệ thống logging còn phải quyết định **có nhận sự kiện không, định dạng thế nào và chuyển nó tới đâu**. Nơi tiếp nhận bản ghi ở cuối một nhánh xuất log được gọi là **đích ghi log** (*log destination* hoặc *sink*).

Các đích thường gặp gồm **console** (luồng chuẩn của tiến trình), **tệp log**, dịch vụ ghi nhật ký của hệ điều hành, một đầu nhận qua mạng và hệ thống tập trung để tìm kiếm, cảnh báo, lưu trữ. Một sự kiện có thể được gửi tới **nhiều đích**: chẳng hạn ứng dụng vừa in ra console để lập trình viên quan sát, vừa ghi vào tệp để tra cứu trong thời gian dài hơn.

Hình dung một nhánh xử lý:

```text
Mã Java gọi logger.info(...)
             |
             v
 Logger: kiểm tra mức log / quy tắc
             |
             v
 Handler / Appender: lọc riêng từng đích
             |
             v
 Formatter / Encoder: chuyển sự kiện thành văn bản hoặc cấu trúc
             |
      +------+-------+
      |              |
      v              v
   Console          File
  stdout/err     application.log
      |              |
      v              v
Bộ thu container  Agent đọc file
      |              |
      +------+-------+
             v
     Nền tảng log tập trung
             |
        Tìm kiếm / cảnh báo /
        lưu trữ theo chính sách
```

Đây là **một mô hình khả dĩ**, không phải mọi ứng dụng đều cần tất cả các khâu. Trong Java:

- `java.util.logging` (JUL) dùng `Logger`, `Handler`, `Formatter` và `Filter`; `ConsoleHandler` và `FileHandler` là hai triển khai có sẵn.
- Logback và Log4j 2 dùng khái niệm `Appender` tương ứng với vai trò đưa bản ghi tới đích; cách cấu hình, hỗ trợ bộ mã hóa và khả năng bất đồng bộ phụ thuộc framework.
- Các API như SLF4J thường là **lớp giao diện** để mã nghiệp vụ gọi logging; triển khai logging phía sau mới thực sự chọn đích, định dạng và cơ chế xuất. Chỉ gọi `log.info` không nói được log sẽ đến đâu.

Cần phân biệt ba khái niệm: **đích ghi của tiến trình** (ví dụ `stderr`), **đường vận chuyển** (ví dụ agent đọc console/file rồi gửi qua mạng), và **nơi lưu trữ/tra cứu cuối** (ví dụ hệ thống phân tích log). Nhìn thấy log trong màn hình tìm kiếm không có nghĩa ứng dụng đã tự gửi trực tiếp tới hệ thống đó.

## 2. Chọn đích ghi theo nhu cầu thực tế

| Đích | Phù hợp khi | Ưu điểm | Rủi ro / giới hạn |
| --- | --- | --- | --- |
| **Console** (`stdout`/`stderr`) | Ứng dụng CLI, phát triển cục bộ, dịch vụ chạy trong container | Dễ xem trực tiếp; nền tảng chạy thường có sẵn cơ chế thu thập | Không mặc nhiên lưu bền vững; khi tiến trình/container kết thúc, log có thể không còn nếu chưa được thu thập |
| **Tệp cục bộ** | Dịch vụ trên máy ảo/máy chủ cần lưu lịch sử tại máy | Dễ phân quyền, kiểm tra và chuyển cho agent đọc file | Chiếm đĩa; cần xoay vòng, lưu giữ, giám sát dung lượng và quyền truy cập |
| **Nhật ký hệ điều hành** | Hệ thống đã vận hành theo chuẩn ghi log của OS | Có công cụ quản trị, thu thập, lưu giữ theo nền tảng | Cần adapter/agent tương thích; không phải JUL mặc định ghi trực tiếp vào mọi hệ thống OS |
| **Đầu nhận qua mạng** | Muốn vận chuyển log tới dịch vụ hoặc bộ thu bên ngoài | Có thể tránh phải quản lý tệp dài hạn tại mỗi máy | Phụ thuộc mạng, xác thực, độ trễ, hàng đợi và hành vi khi đầu nhận không sẵn sàng |
| **Hệ thống log tập trung** | Nhiều instance/microservice cần tra cứu chung, dashboard và cảnh báo | Lọc theo `service`, `trace_id`, `correlation_id` và các trường khác; tìm sự kiện xuyên dịch vụ | Có độ trễ nhận log, chi phí lưu trữ/chỉ mục, quyền truy cập và thời gian lưu giữ |

Tên sản phẩm không quyết định kiến trúc. Cùng một hệ thống tập trung có thể tiếp nhận log do ứng dụng gửi trực tiếp, do agent thu thập từ tệp, hoặc do nền tảng container chuyển từ console.

**Nguyên tắc thiết kế:** chọn đích theo môi trường chạy, nhu cầu vận hành, mức độ bền vững mong muốn và chi phí chấp nhận được. Đích ghi log là quyết định của hạ tầng và cấu hình triển khai; code nghiệp vụ nên chỉ mô tả **sự kiện cần ghi**.

## 3. Console: stdout và stderr

Console là lựa chọn đơn giản nhất. Ứng dụng ghi vào luồng chuẩn của tiến trình; terminal, IDE hoặc bộ chạy dịch vụ sẽ quyết định cách hiển thị và thu thập. Hai luồng thường được nhắc đến:

- **`stdout`**: luồng đầu ra tiêu chuẩn; một số nền tảng dùng để thu log ứng dụng.
- **`stderr`**: luồng lỗi tiêu chuẩn; thường được dùng cho chẩn đoán và các thông điệp log.

Không nên suy luận rằng log ở mức `INFO` luôn xuất hiện ở `stdout` còn `ERROR` luôn ở `stderr`. Việc phân luồng **phụ thuộc vào handler/appender và cấu hình**.

Trong `java.util.logging`, `ConsoleHandler` mặc định ghi vào **`System.err`**, kể cả khi thông điệp ở mức `INFO`. Nó không tự chia mức log sang hai luồng. Vì vậy khi chạy:

```bash
java LogDestinationsDemo
```

log có thể hiện trong terminal nhưng **stdout vẫn rỗng**, do terminal thường hiển thị cả stdout và stderr. Nếu chuyển hướng riêng hai luồng, kết quả sẽ khác nhau. Với logback hoặc các framework khác, cần kiểm tra cấu hình ConsoleAppender để biết nó dùng luồng nào.

Khi triển khai container, nhiều nền tảng có thể thu `stdout`/`stderr` của từng container rồi chuyển tiếp tới dịch vụ tổng hợp. Cách này thường thuận tiện hơn việc ứng dụng tự mở tệp nằm trong filesystem tạm thời của container. Tuy vậy, việc **thu thập, lưu giữ và tra cứu** phụ thuộc cấu hình runtime, agent và nền tảng log; xuất ra console tự nó không bảo đảm log được lưu.

**Lưu ý riêng cho ứng dụng CLI:** nếu stdout là kênh xuất dữ liệu để chương trình khác đọc (JSON, CSV hoặc một giao thức dòng lệnh), đẩy log lẫn vào stdout có thể làm hỏng dữ liệu. Khi đó gửi log chẩn đoán ra stderr là lựa chọn hợp lý, hoặc sử dụng kênh log riêng theo hợp đồng của ứng dụng.

## 4. Tệp: lưu tại máy và xoay vòng

Ghi log vào tệp thích hợp khi ứng dụng chạy lâu dài trên máy có đĩa/volume được quản lý. Tệp tạo điều kiện để tra cứu các bản ghi cũ tại máy, sao lưu hoặc dùng agent đọc và gửi đi.

Trong JUL, `FileHandler` có thể cấu hình:

- **`pattern`**: tên/đường dẫn tệp, ví dụ `logs/application-%g.log`.
- **`limit`**: giới hạn kích thước xấp xỉ theo byte của mỗi tệp trước khi xoay vòng (giới hạn không phải ranh giới chính xác từng thông điệp).
- **`count`**: số thế hệ tệp được quản lý trong vòng quay.
- **`append`**: có tiếp tục ghi vào tệp hiện có khi mở hay bắt đầu lại theo chế độ không nối thêm.

Trong pattern của JUL, `%g` biểu thị **chỉ số thế hệ** của tệp khi có xoay vòng; `%u` biểu thị **số duy nhất để xử lý một số tình huống xung đột tên/khóa tệp**. Nếu môi trường có nhiều tiến trình, không được mặc nhiên cho rằng nhiều tiến trình có thể ghi an toàn vào **cùng một tệp** theo một quy ước tên chung.

**Rotation không phải retention vô hạn.** Khi file đạt ngưỡng, handler sẽ chuyển sang tệp thế hệ khác và có thể ghi đè tệp cũ khi hết số lượng được giữ. Vì thế cần quyết định mức lưu giữ phù hợp, thời điểm xóa, dung lượng đĩa và cách bàn giao cho agent đọc tệp đang xoay vòng.

Các vấn đề vận hành cần tính trước:

1. **Đường dẫn làm việc**: `logs/app.log` là đường dẫn tương đối theo thư mục làm việc khi tiến trình khởi chạy; chạy từ IDE, service manager hay container có thể cho kết quả khác.
2. **Quyền và dung lượng**: ứng dụng cần quyền tạo/ghi thư mục; đĩa đầy hoặc quyền sai có thể khiến log không ghi được.
3. **Thời gian lưu trữ**: log có thể chứa thông tin quan trọng, nên cần thời hạn lưu và chính sách xóa/sao lưu phù hợp.
4. **Định dạng**: `FileHandler` mặc định của JUL không nhất thiết dùng định dạng dòng văn bản mà người đọc mong đợi; cấu hình `Formatter` khi cần.
5. **Thu thập tiếp**: agent đọc file cần xử lý tệp bị đổi tên/xoay vòng và lưu vị trí đã đọc; sai cấu hình có thể gây mất hoặc trùng bản ghi.
6. **Dữ liệu nhạy cảm**: phân quyền truy cập tệp và mã hóa khi cần; không để mật khẩu, token hoặc dữ liệu khách hàng nhạy cảm đi vào log từ đầu.

## 5. Ví dụ Java 17+: cùng một sự kiện đến console và tệp

Ví dụ sau dùng **JUL có sẵn trong JDK**, tạo hai handler cho cùng một logger:

- `ConsoleHandler` xuất ra **stderr**.
- `FileHandler` ghi vào tệp thế hệ tại `logs/application-0.log`, cho phép tối đa ba thế hệ với ngưỡng khoảng 1.000.000 byte mỗi tệp.
- Một `Formatter` dùng chung tạo dòng văn bản đơn giản để có đầu ra dễ kiểm chứng.
- Chương trình không tạo hệ thống log tập trung; nó chỉ minh họa **hai đích cục bộ độc lập**.

Tạo file **`LogDestinationsDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogDestinationsDemo {
    private LogDestinationsDemo() {
    }

    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        Logger logger = Logger.getLogger("demo.log.destinations");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(formatter);

        FileHandler file = new FileHandler(
                "logs/application-%g.log", 1_000_000, 3, false);
        file.setLevel(Level.INFO);
        file.setEncoding("UTF-8");
        file.setFormatter(formatter);

        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.info("event=order_received order_id=ORD-101");
            logger.warning(
                    "event=payment_retry_scheduled order_id=ORD-101"
                    + " reason_code=GATEWAY_TIMEOUT");
        } finally {
            logger.removeHandler(file);
            logger.removeHandler(console);
            file.close();
            console.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên trong thư mục chứa file:

```bash
javac -encoding UTF-8 LogDestinationsDemo.java
java LogDestinationsDemo
```

**Đầu ra stderr** của lần chạy được cấu hình như trên:

```text
INFO event=order_received order_id=ORD-101
WARNING event=payment_retry_scheduled order_id=ORD-101 reason_code=GATEWAY_TIMEOUT
```

**Đầu ra stdout:** rỗng. Nếu chỉ nhìn terminal, hai dòng stderr thường vẫn hiện như thông điệp bình thường.

**Nội dung tệp `logs/application-0.log`** ngay sau lần chạy thành công (giả sử không có tiến trình khác can thiệp vào cùng đường dẫn):

```text
INFO event=order_received order_id=ORD-101
WARNING event=payment_retry_scheduled order_id=ORD-101 reason_code=GATEWAY_TIMEOUT
```

Dùng `false` ở tham số `append` để ví dụ cho kết quả ổn định giữa các lần chạy: tệp của thế hệ đang mở không được nối thêm vào nội dung cũ theo lựa chọn này. Trong dịch vụ thật, cần chọn chính sách append/rotation theo nhu cầu vận hành và cân nhắc việc ghi đồng thời.

### Giải thích các quyết định trong code

**`logger.setUseParentHandlers(false)`** ngăn sự kiện tự truyền thêm tới các handler của logger cha. Nếu logger cha đã có ConsoleHandler và logger con lại gắn một ConsoleHandler, cùng một sự kiện có thể xuất hiện hai lần trên màn hình. Đây là nguyên nhân phổ biến của log bị nhân đôi.

**`logger.setLevel(Level.INFO)`** và `handler.setLevel(Level.INFO)` kiểm soát **hai tầng**. Logger phải cho phép sự kiện đi qua; từng handler cũng phải chấp nhận mức đó. Ví dụ, nếu đổi `console.setLevel(Level.WARNING)` nhưng giữ file ở `INFO`, sự kiện `INFO` chỉ tới tệp, còn `WARNING` tới cả hai đích.

**`Formatter`** chỉ định cách biến `LogRecord` thành chuỗi. Ví dụ cố tình lược timestamp để đầu ra dự đoán chính xác; **trong production cần thời gian, nguồn phát và mã tương quan** khi phù hợp. Với log dạng JSON, dùng công cụ encoder/formatter có khả năng escape chính xác, tránh tự ghép JSON bằng chuỗi không an toàn.

**`FileHandler`** xoay vòng các thế hệ tệp khi đủ ngưỡng. `%g` trong tên tạo ra dạng `application-0.log` ở thế hệ ban đầu. `Files.createDirectories` tạo thư mục nếu chưa có; nếu không có quyền, chương trình có thể ném `IOException`. `file.close()` cho phép đóng và flush các tài nguyên của file handler sau khi ghi.

**`Logger` không đồng nghĩa với một đích.** Hai handler cùng nhận sự kiện ở đây, nhưng nếu một handler lọc ở mức khác hoặc lỗi ghi, bản ghi có thể xuất hiện ở một đích mà không có ở đích còn lại. Không lấy số dòng trên tất cả các đích cộng lại thành số sự kiện nghiệp vụ.

Ví dụ đặt cấu hình bằng code để dễ học. Ứng dụng thật thường tách cấu hình cấp log, formatter, file pattern và đích ghi khỏi mã nghiệp vụ (chẳng hạn `logging.properties` của JUL hoặc cấu hình của Logback/Log4j 2), giúp thay đổi theo môi trường mà không sửa logic của từng lớp.

## 6. Đích tập trung: ứng dụng gửi thẳng hay dùng bộ thu trung gian?

Khi một dịch vụ chạy ở nhiều máy hoặc nhiều container, đọc từng tệp riêng lẻ gây khó khăn cho việc tìm một yêu cầu xuyên dịch vụ. Có hai hướng triển khai phổ biến.

### Mô hình A: ứng dụng ghi ra stdout/stderr, nền tảng thu thập

```text
Java application
    |
    v
ConsoleHandler / ConsoleAppender
    |
    v
stdout/stderr của container
    |
    v
Container runtime / node collector
    |
    v
Pipeline xử lý, gắn metadata
    |
    v
Log storage + search/alerting
```

Ứng dụng chỉ biết đích gần nhất là console. Bộ thu có thể bổ sung `service`, `environment`, `instance_id`, timestamp, nhãn triển khai hoặc thông tin truy vết. Phù hợp với môi trường container được quản lý, miễn là pipeline thu thập và lưu giữ đã được thiết lập.

### Mô hình B: ứng dụng ghi tệp, agent theo dõi tệp

```text
Java application
    |
    v
Rolling file
    |
    v
File collector / shipper
    |
    v
Log storage + search/alerting
```

Ứng dụng quản lý tệp và cơ chế rotation; agent phải nhớ đã đọc đến đâu, theo dõi đổi tên tệp, xử lý retry và chuyển tiếp qua mạng. Mô hình này phù hợp với môi trường máy chủ truyền thống hoặc khi cần bản ghi cục bộ, nhưng tăng trách nhiệm về đĩa và file lifecycle.

### Mô hình C: appender/handler gửi qua mạng

Một framework hoặc một handler tùy biến có thể phát bản ghi trực tiếp tới đầu nhận qua mạng. Cách này có thể giảm khâu đọc file, nhưng phụ thuộc vào khả năng của thư viện, định dạng truyền, xác thực và hành vi khi mạng gián đoạn. **JUL mặc định không cung cấp mọi kiểu đích từ xa**; không nên tự giả định rằng chỉ cần thay tên file bằng URL là có thể gửi log.

Khi đích ở xa bị chậm hoặc mất kết nối, hệ thống có thể: chặn luồng gọi log, đưa sự kiện vào hàng đợi, thử lại, lưu dự phòng hoặc loại bỏ một số bản ghi theo chính sách. Phải hiểu rõ lựa chọn của ứng dụng và collector; không có cơ chế nào tự bảo đảm “không mất, không trùng, đúng thứ tự” trong mọi sự cố.

## 7. Định dạng và metadata phải phù hợp với đích

Đích ghi và định dạng là hai cấu hình liên quan nhưng không giống nhau. Cùng một sự kiện có thể thành:

**Dòng văn bản đọc nhanh tại console:**

```text
2026-11-09T12:00:00Z INFO order-service event=order_received order_id=ORD-101 correlation_id=req-7
```

**Bản ghi có cấu trúc để tìm kiếm tập trung:**

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "environment": "production",
  "event": "order_received",
  "order_id": "ORD-101",
  "correlation_id": "req-7"
}
```

Hai ví dụ chỉ minh họa định dạng; không phải đầu ra của chương trình Java ở phần trước.

Để dùng log xuyên dịch vụ, nên có **thời gian rõ múi giờ** (thường UTC), mức log, tên ứng dụng/dịch vụ, môi trường và mã tương quan theo yêu cầu. Khi có tracing phân tán, `trace_id`/`span_id` có thể giúp kết nối log với từng nhịp xử lý. Trong tập trung hóa, nên giữ **tên trường và kiểu dữ liệu nhất quán** để truy vấn và cảnh báo hoạt động ổn định.

Một số lưu ý tùy đích:

- **Console/file dạng dòng:** dữ liệu đầu vào chứa ký tự xuống dòng hoặc dấu phân cách cần được escape/chuẩn hóa để tránh tạo log giả hoặc phá một bản ghi thành nhiều dòng.
- **JSON:** sử dụng encoder JSON hợp lệ; có chính sách xử lý exception/stack trace để bộ thu không tách sai bản ghi.
- **Hệ thống tập trung:** phân biệt trường nên được lập chỉ mục với trường chỉ để hiển thị; giá trị có số lượng biến thể rất lớn như `request_id` không nên mặc nhiên biến thành nhãn lập chỉ mục chi phí cao trên mọi nền tảng.
- **Bảo mật:** không gửi token, mật khẩu, khóa API, dữ liệu thẻ hoặc thông tin cá nhân nhạy cảm tới bất kỳ đích nào. Việc dữ liệu đã ra khỏi ứng dụng khiến việc thu hồi và xóa đồng bộ khó hơn.
- **Độ tin cậy:** timestamp của sự kiện và thời điểm collector nhận được có thể khác nhau; nên biết đang sắp xếp theo trường nào khi xem thứ tự.

## 8. Độ tin cậy, hiệu năng và lưu giữ

Lời gọi `logger.info` không đồng nghĩa bản ghi đã được ghi thành công xuống đĩa hoặc đã xuất hiện trong kho tìm kiếm. Mỗi đích có điểm thất bại riêng:

| Tình huống | Có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Console được ghi nhưng collector chưa chạy | Bản ghi hiển thị tại máy, không tìm được trên dashboard | Kiểm tra cấu hình thu `stdout`/`stderr`, thời gian gửi và điểm nhận |
| Đĩa gần đầy | File handler không ghi tiếp hoặc quá trình phục hồi gặp lỗi | Giới hạn rotation, giám sát dung lượng, chính sách lưu giữ |
| Đầu nhận từ xa mất kết nối | Log đến chậm, bị loại, lặp khi retry hoặc gây tăng độ trễ | Hiểu rõ buffering, retry, backpressure và giới hạn hàng đợi |
| Queue bất đồng bộ đầy | Có thể bỏ bản ghi, chặn luồng hoặc áp dụng chính sách khác | Đo lượng backlog/dropped logs và đặt quy tắc ưu tiên |
| Ứng dụng dừng đột ngột | Bộ đệm chưa flush có thể mất | Đóng handler có kiểm soát khi tắt bình thường; không dựa vào close khi tiến trình crash |
| Cấu hình cấp độ không khớp | Sự kiện bị lọc trước khi đến đích | Kiểm tra cấp ở cả logger và handler/appender, kể cả logger cha |
| Sai khoảng thời gian tìm kiếm | Sự kiện đã lưu nhưng truy vấn không hiển thị | Kiểm tra múi giờ, timestamp, thời gian lập chỉ mục và retention |

**Logging bất đồng bộ** giúp giảm thời gian xử lý trực tiếp của luồng nghiệp vụ ở một số hệ thống, nhưng thêm hàng đợi, giới hạn bộ nhớ và rủi ro mất sự kiện chưa được ghi bền vững khi tiến trình dừng đột ngột. Khi độ tin cậy quan trọng, phải đo được bản ghi bị rơi hoặc trễ. Không tự tạo hàng đợi vô hạn để “tránh mất log”: hàng đợi có thể dùng hết bộ nhớ ứng dụng.

**Chính sách lưu giữ (retention)** phải xuất phát từ mục đích: điều tra sự cố, phân tích vận hành, yêu cầu pháp lý và bảo vệ dữ liệu. Giữ log lâu hơn làm tăng chi phí và rủi ro rò rỉ. Xóa log quá sớm làm mất khả năng đối chiếu sự cố. Quyết định retention có thể khác nhau giữa log truy cập, log lỗi, log nghiệp vụ và nhật ký kiểm toán.

**Log không thay thế cơ chế nghiệp vụ bền vững.** Nếu cần bằng chứng có yêu cầu toàn vẹn, khả năng kiểm toán hoặc không được mất khi giao dịch hoàn tất, phải thiết kế kho dữ liệu/cơ chế audit/event chuyên dụng. File handler hay appender gửi mạng không tự cung cấp bảo đảm giao dịch của cơ sở dữ liệu.

## 9. Chọn đích theo môi trường triển khai

**Ứng dụng chạy cục bộ hoặc bài tập Java:** dùng console để thấy kết quả ngay. Chỉ thêm FileHandler nếu bài tập thật sự cần minh họa lưu tệp hoặc truy vết nhiều lần chạy. Tránh cấu hình quá phức tạp khi đang học ý nghĩa của sự kiện.

**Ứng dụng CLI xuất dữ liệu cho chương trình khác:** ưu tiên bảo toàn stdout như kênh dữ liệu; tách log sang stderr hoặc cấu hình đích riêng để pipeline xử lý dữ liệu không bị nhiễu.

**Dịch vụ Java trên máy ảo:** console hoặc tệp đều có thể phù hợp. Nếu dùng tệp, cần đường dẫn ổn định, quyền truy cập, rotation, đo dung lượng và agent chuyển tiếp khi cần tìm kiếm tập trung.

**Dịch vụ Java trong container:** thường bắt đầu từ stdout/stderr và cơ chế thu log của runtime/orchestrator. Tránh phụ thuộc vào một tệp cục bộ trong filesystem tạm của container nếu chưa có volume và agent quản lý.

**Nhiều dịch vụ, nhiều instance:** bố trí pipeline tập trung, phân quyền, retention và dữ liệu tương quan. Mỗi instance có thể ghi tại chỗ bằng cùng một quy ước; hệ thống thu thập thêm nhận dạng instance để người vận hành phân biệt các bản ghi.

**Hệ thống có yêu cầu audit:** thiết kế audit trail riêng với quy tắc kiểm soát truy cập, toàn vẹn, thời gian lưu và đối chiếu. Log quan sát vẫn hữu ích, nhưng không là nguồn xác nhận duy nhất cho thay đổi quan trọng.

## 10. Khi không thấy log ở đích mong đợi

Điều tra từ **gần nguồn phát nhất** để xác định chính xác bước nào mất bản ghi:

1. **Xác định sự kiện có được gọi không.** Kiểm tra nhánh code thực thi và mức log đang bật; việc không thấy log chưa đủ chứng minh code không chạy.
2. **Kiểm tra Logger và Handler/Appender.** Logger có bật mức `INFO` không? Handler có nhận `INFO` không? Có filter, điều kiện phân môi trường hay inheritance làm mất/trùng sự kiện không?
3. **Kiểm tra định dạng.** Parser có nhận được bản ghi không, nhất là khi exception/stack trace chứa nhiều dòng hoặc thông điệp bị ghép thủ công?
4. **Kiểm tra đích gần nhất.** Console ghi vào stdout hay stderr? Tệp nằm ở thư mục làm việc nào? Quyền ghi và dung lượng thế nào? Có đang xem nhầm file thế hệ sau rotation không?
5. **Kiểm tra đường chuyển tiếp.** Collector có chạy, đọc đúng stream/path và có lỗi gửi, backpressure, retry hoặc mất quyền truy cập không?
6. **Kiểm tra kho tập trung.** Bộ lọc thời gian, `service`/`environment`, độ trễ lập chỉ mục, retention và chính sách truy cập có loại bản ghi khỏi kết quả không?

Ví dụ: code gọi `logger.info` nhưng chỉ ghi vào file, trong khi người vận hành đang lọc theo stderr của container. Không thấy log trên dashboard có thể đơn giản là do **collector không đọc nguồn mà ứng dụng đang dùng**. Cách sửa nằm ở routing của pipeline, không nhất thiết là thêm câu lệnh log.

Nếu log xuất hiện **hai lần**, trước tiên tìm nhiều handler cùng đích, logger cha truyền xuống, hoặc collector đọc đồng thời cả tệp và console chứa bản ghi giống nhau. Nếu log bị trùng **sau khi chuyển tiếp**, kiểm tra retry và cơ chế nhận diện bản ghi khi nhập kho. Không kết luận ứng dụng đã xử lý nghiệp vụ hai lần chỉ dựa trên số dòng.

## 11. Những lỗi thiết kế cần tránh

- **Nhầm mức log với đích:** `INFO` không bảo đảm đi stdout; `WARNING`/`ERROR` không bảo đảm đến một file riêng.
- **Gắn handler trùng:** một logger con và logger cha đều đẩy sự kiện tới console, tạo hai dòng cho cùng sự kiện.
- **Ghi tất cả vào tệp không giới hạn:** làm đầy đĩa, gây sự cố cho chính ứng dụng và hạ tầng.
- **Để mã nghiệp vụ quyết định file path:** gây khó khi chuyển môi trường; nên tách routing/định dạng/retention thành cấu hình triển khai.
- **Chia sẻ một file giữa nhiều tiến trình mà không có cơ chế phù hợp:** có thể xung đột khóa, ghi xen kẽ hoặc khác tên tệp so với dự tính.
- **Gửi log đồng bộ qua mạng mà không quan tâm lỗi:** làm sự cố ở nền tảng quan sát lan sang thời gian phản hồi nghiệp vụ.
- **Coi console là nơi lưu trữ chính thức:** chỉ có ý nghĩa khi hạ tầng thật sự thu và lưu các luồng đó.
- **Ghi bí mật và dữ liệu nhạy cảm:** một bản ghi có thể đi qua nhiều agent và kho lưu trữ; hạn chế tại điểm tạo sự kiện.
- **Cộng số dòng từ nhiều đích thành số sự kiện:** một sự kiện có thể được fan-out ra nhiều sink, hoặc bị thử gửi lại.
- **Bỏ qua xác minh sau triển khai:** cấu hình chạy cục bộ có thể khác runtime thật; cần một sự kiện kiểm tra an toàn, có mã nhận diện để xác nhận đường đi của log.

## 12. Câu hỏi tự kiểm tra

1. Một câu lệnh `logger.info("started")` trong JUL được xử lý bởi `ConsoleHandler` mặc định. Vì sao người đọc thấy trên terminal nhưng stdout có thể rỗng? **Vì ConsoleHandler ghi ra stderr theo mặc định; terminal thường hiển thị cả hai luồng.**
2. Một logger ở mức `INFO` có hai handler: console mức `WARNING` và file mức `INFO`. Sự kiện `INFO` xuất hiện ở đâu? **Ở file; console lọc sự kiện này.**
3. Vì sao không nên viết tất cả log vào một file mãi mãi? **Có nguy cơ đầy đĩa, khó lưu giữ an toàn và phải có chính sách xoay vòng/xóa.**
4. Một dịch vụ container ghi log ra stderr nhưng dashboard không có bản ghi. Hai nơi cần kiểm tra là gì? **Đích gần nhất (stderr của container) và cấu hình collector/pipeline đang thu luồng đó.**
5. Một bản ghi giống nhau hiện trong console và file. Có thể kết luận ứng dụng chạy hai lần không? **Không. Một sự kiện có thể được đưa tới hai handler.**
6. Dịch vụ gửi log từ xa bị nghẽn. Điều quan trọng cần biết ở appender/agent là gì? **Hành vi khi đầy hàng đợi hoặc mất mạng: chặn, lưu đệm, thử lại, loại bỏ và cách quan sát tình trạng ấy.**
7. Trong sản xuất, những thông tin nào giúp một log tìm được xuyên nhiều instance? **Timestamp có múi giờ, service, environment, instance, mã yêu cầu/correlation hoặc trace id và các trường nghiệp vụ an toàn, theo nhu cầu tra cứu.**

**Điểm ghi nhớ:** đích ghi log quyết định **sự kiện đi đâu**; logger, bộ lọc, handler/appender và formatter quyết định **sự kiện nào được đi và được biểu diễn ra sao**. Kiến trúc tốt chọn được nơi phát gần ứng dụng, đường vận chuyển và kho lưu trữ thích hợp, đồng thời có chính sách rõ ràng cho lưu giữ, bảo mật, lỗi và chi phí.
