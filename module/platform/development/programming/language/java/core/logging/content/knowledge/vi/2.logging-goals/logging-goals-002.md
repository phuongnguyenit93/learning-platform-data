# Điều tra lỗi bằng logging trong Java

**Điều tra lỗi (troubleshooting/debugging)** là một mục tiêu cốt lõi của logging: khi chương trình chạy sai, log giúp tái dựng những sự kiện đã diễn ra, khoanh vùng nơi thất bại và kiểm chứng nguyên nhân. Điều này đặc biệt cần thiết với lỗi chỉ xuất hiện ở môi trường chạy thật, lỗi không tái hiện được ngay trên máy lập trình hoặc lỗi đi qua nhiều lớp xử lý.

Logging không tự sửa lỗi và một dòng `ERROR` cũng chưa chứng minh nguyên nhân gốc. Giá trị của log nằm ở **bằng chứng có ngữ cảnh, theo đúng thứ tự thời gian**, để người điều tra phân biệt biểu hiện, tác động và nguyên nhân.

## 1. Log trả lời những câu hỏi nào?

Khi tiếp nhận một lỗi, cần tìm bằng chứng để trả lời:

1. **Chuyện gì xảy ra?** Thao tác nào thất bại; lỗi trả về cho người dùng, tác vụ nền hay giai đoạn khởi động?
2. **Xảy ra khi nào và ở đâu?** Mốc thời gian, thành phần, phương thức, bước xử lý và phiên bản triển khai liên quan.
3. **Ảnh hưởng đến ai hoặc việc gì?** Một yêu cầu, một job, một tài nguyên hay toàn bộ dịch vụ? Chỉ ghi định danh nội bộ đã được phép lưu.
4. **Điều gì xảy ra ngay trước khi lỗi xuất hiện?** Bước cuối thành công, dữ liệu đã được kiểm tra, thao tác gọi ra ngoài và thay đổi trạng thái.
5. **Ngoại lệ bắt nguồn từ đâu?** Loại exception, stack trace và chuỗi `Caused by` cho thấy luồng gọi và nguyên nhân gần nhất.
6. **Lỗi có lặp lại không?** Có cùng dấu hiệu ở nhiều request, sau một lần triển khai hay khi hệ thống chịu tải?

Ví dụ, chỉ có `Payment failed` gần như không đủ để điều tra. Cùng sự kiện nhưng có `requestId`, `operation`, `stage`, `outcome`, loại exception và thời điểm sẽ giúp xác định yêu cầu nào thất bại và tại bước nào.

## 2. Ghi log như thế nào để có thể điều tra?

Một sự kiện quan trọng nên mang các trường có ý nghĩa ổn định:

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| `timestamp` | Sắp xếp các sự kiện, so với thời điểm báo lỗi | `2026-01-15T08:30:12.345Z` |
| `level` | Phân biệt diễn tiến bình thường, cảnh báo, thất bại | `INFO`, `WARNING`, `SEVERE` |
| `service` / `component` | Xác định nơi phát sinh sự kiện | `order-service`, `ConfigLoader` |
| `requestId` / `jobId` / `runId` | Nối các dòng thuộc cùng một đơn vị công việc | `req-42` |
| `operation` và `stage` | Biết đang làm gì, đã đi đến bước nào | `createOrder`, `validate` |
| `outcome` và mã lỗi ổn định | Phân biệt thành công/thất bại, nhóm lỗi | `failed`, `INVALID_TIMEOUT` |
| `durationMs` hoặc thông tin phụ thuộc | Tìm dấu hiệu chậm, timeout, retry | `durationMs=1200` |
| `exception` kèm cause | Truy vị trí và nguyên nhân kỹ thuật | `NumberFormatException` |

Một log dễ lọc có thể là:

```text
2026-01-15T08:30:12.345Z INFO service=order-service requestId=req-42 operation=createOrder stage=validate outcome=started
2026-01-15T08:30:12.349Z WARNING service=order-service requestId=req-42 operation=createOrder stage=validate outcome=failed errorCode=INVALID_QUANTITY
```

Hai dòng trên là **dữ liệu giả định để minh họa cấu trúc**, không phải kết quả chạy chương trình ở phần sau.

**Nguyên tắc thực hành:**

- Ghi sự kiện tại các ranh giới quan trọng: bắt đầu xử lý, kiểm tra dữ liệu, gọi hệ thống phụ thuộc, retry và kết thúc. Không ghi mọi dòng lệnh.
- Dùng cùng một correlation ID xuyên suốt luồng; qua HTTP/message queue phải truyền ID theo cơ chế của ứng dụng, không kỳ vọng `ThreadLocal` tự đi qua luồng hoặc tiến trình khác.
- Ghi sự kiện tại nơi có **ngữ cảnh nghiệp vụ đầy đủ**; lưu cả exception dưới dạng `Throwable` để không mất stack trace.
- Dùng tên trường và mã lỗi ổn định để lọc bằng công cụ tìm kiếm. Phân biệt chuỗi thông báo dành cho con người với mã lỗi dùng cho máy.
- Timestamp nên có múi giờ rõ ràng, thường dùng UTC/ISO 8601, nhất là khi nhiều dịch vụ chạy ở các múi giờ khác nhau.
- Chỉ log những gì cần cho vận hành. Không ghi mật khẩu, access token, cookie phiên, khóa bí mật hay dữ liệu cá nhân nhạy cảm; xử lý đầu vào có thể chứa xuống dòng để tránh làm giả cấu trúc log.

### Chọn mức log phù hợp trong Java

Trong `java.util.logging` (JUL), một số mức thường gặp là:

| Mức JUL | Khi nào nên dùng |
| --- | --- |
| `FINE`, `FINER`, `FINEST` | Chi tiết để chẩn đoán, thường chỉ bật có kiểm soát khi cần |
| `INFO` | Mốc vận hành bình thường, sự kiện đáng chú ý |
| `WARNING` | Tình huống bất thường nhưng hệ thống còn tiếp tục, lỗi đầu vào dự kiến hoặc retry |
| `SEVERE` | Thất bại nghiêm trọng của thao tác hoặc thành phần cần xử lý |

Mức log phụ thuộc **tác động và chính sách vận hành**, không chỉ tên lớp exception. Chẳng hạn, dữ liệu không hợp lệ do người dùng nhập thường không cần `SEVERE`; cấu hình khởi động sai khiến dịch vụ không thể hoạt động có thể cần `SEVERE`. JUL cũng có các mức khác như `CONFIG` và `OFF`.

## 3. Quy trình điều tra lỗi từ log

1. **Xác định biểu hiện.** Ghi nhận thời gian, môi trường, thao tác, request/job ID nếu có, kết quả thực tế và kết quả mong đợi.
2. **Khoanh vùng thời gian và thành phần.** Tìm sự kiện thất bại gần thời điểm báo lỗi; kiểm tra độ lệch đồng hồ trước khi suy ra thứ tự giữa nhiều máy.
3. **Lọc theo correlation ID.** Gom các dòng cùng `requestId`, `jobId` hoặc `runId`, rồi sắp xếp theo thời gian. Nếu luồng chạy song song, cần dùng thêm ID và thứ tự sự kiện, tránh coi mọi dòng xen kẽ là một request.
4. **Tìm điểm chuyển từ bình thường sang bất thường.** Xác định bước cuối thành công và bước đầu thất bại; xem timeout, retry, trạng thái của phụ thuộc và mã lỗi.
5. **Đọc ngoại lệ đầy đủ.** Kiểm tra loại exception, stack trace, `Caused by` và những frame thuộc mã nguồn ứng dụng. Dòng đầu của stack trace là nơi ngoại lệ được tạo/ném, chưa chắc là nguyên nhân nghiệp vụ cuối cùng.
6. **Đưa ra giả thuyết có thể kiểm chứng.** Ví dụ: giá trị cấu hình không phải số, kết nối bị từ chối, thiếu quyền truy cập hoặc dữ liệu chưa đáp ứng điều kiện tiền đề. Đối chiếu cấu hình, input đã được phép kiểm tra, chỉ số vận hành và lần chạy thành công.
7. **Kiểm chứng sau khi sửa.** Tái hiện có kiểm soát, thử ca lỗi và ca thành công, xác nhận log chỉ ra đúng điểm xử lý và lỗi không tái phát. Nếu dữ liệu log còn thiếu, bổ sung sự kiện có ý nghĩa cho lần sau.

**Không suy luận nguyên nhân chỉ từ log cuối cùng.** Một `NullPointerException` ở lớp hiển thị có thể là hậu quả của giá trị rỗng trả từ một bước trước đó; `Connection timed out` cũng có thể là biểu hiện của tải cao hoặc sự cố mạng. Cần thêm dữ kiện để xác nhận giả thuyết.

## 4. Ví dụ Java 17+: điều tra cấu hình sai bằng `java.util.logging`

Ví dụ sau chạy độc lập bằng JDK 17+, không cần thư viện bên ngoài. Một lần khởi động có `runId=boot-42`; chương trình thử đọc thời gian chờ từ chuỗi `five-seconds` và phát hiện giá trị không hợp lệ. Log cho thấy bước đã bắt đầu, bước thất bại, exception và nguyên nhân được giữ lại qua chuỗi `cause`.

Lưu nội dung thành `InvestigateFailureDemo.java`:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class InvestigateFailureDemo {
    private static final Logger LOGGER =
            Logger.getLogger(InvestigateFailureDemo.class.getName());

    public static void main(String[] args) {
        configureLogging();

        String runId = "boot-42";
        LOGGER.info("runId=" + runId
                + " operation=startupConfig stage=readTimeout outcome=started");

        try {
            int timeoutMillis = parseTimeoutMillis("five-seconds");
            LOGGER.info("runId=" + runId
                    + " operation=startupConfig stage=readTimeout outcome=completed"
                    + " timeoutMillis=" + timeoutMillis);
        } catch (IllegalArgumentException e) {
            LOGGER.log(Level.SEVERE,
                    "runId=" + runId
                            + " operation=startupConfig stage=readTimeout outcome=failed",
                    e);
        }
    }

    private static int parseTimeoutMillis(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "timeoutMillis must be positive");
            }
            return value;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "timeoutMillis must be an integer", e);
        }
    }

    private static void configureLogging() {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder message = new StringBuilder();
                message.append(record.getLevel())
                        .append(' ')
                        .append(formatMessage(record))
                        .append(System.lineSeparator());

                if (record.getThrown() != null) {
                    StringWriter buffer = new StringWriter();
                    record.getThrown().printStackTrace(new PrintWriter(buffer));
                    message.append(buffer);
                }
                return message.toString();
            }
        });

        LOGGER.addHandler(console);
    }
}
```

Biên dịch và chạy:

```bash
javac InvestigateFailureDemo.java
java InvestigateFailureDemo
```

**Trích đoạn đầu ra minh họa (ghi vào stderr)**, với dòng stack trace được lược bớt vì số dòng của tệp và chi tiết JDK có thể khác:

```text
INFO runId=boot-42 operation=startupConfig stage=readTimeout outcome=started
SEVERE runId=boot-42 operation=startupConfig stage=readTimeout outcome=failed
java.lang.IllegalArgumentException: timeoutMillis must be an integer
    at InvestigateFailureDemo.parseTimeoutMillis(InvestigateFailureDemo.java:...)
    at InvestigateFailureDemo.main(InvestigateFailureDemo.java:...)
Caused by: java.lang.NumberFormatException: For input string: "five-seconds"
    ...
```

**Phân tích bằng chứng:**

- Dòng `INFO` chứng tỏ chương trình đã vào bước đọc cấu hình; không có dòng `outcome=completed`.
- Dòng `SEVERE` gắn sự cố với `runId=boot-42` và `stage=readTimeout`, nên có thể tìm tất cả sự kiện của lần chạy này.
- `IllegalArgumentException` diễn đạt quy tắc cấu hình ở lớp ứng dụng; `Caused by: NumberFormatException` chỉ ra việc chuyển chuỗi thành số thất bại.
- Thay `"five-seconds"` bằng `"5000"` sẽ đi qua nhánh thành công và ghi `timeoutMillis=5000`. Trường hợp giá trị `"0"` vẫn bị từ chối vì timeout phải dương.

Formatter ở đây cố tình rút gọn log để dễ học. Trong môi trường thật, bổ sung timestamp có timezone, tên dịch vụ và định dạng log nhất quán; có thể dùng formatter JSON nếu hệ thống thu thập log yêu cầu. `ConsoleHandler` mặc định ghi vào **stderr**, không phải stdout.

Chương trình mẫu bắt exception ở `main` để hiển thị đầy đủ bằng chứng. Nó **không tự kết thúc với mã lỗi khác 0** chỉ vì đã gọi `LOGGER.log(Level.SEVERE, ...)`. Ứng dụng thật phải quyết định dừng khởi động, trả lỗi hoặc chuyển trạng thái không sẵn sàng theo chính sách của mình; logging không thay thế xử lý lỗi.

## 5. Ghi exception đúng cách để không mất nguyên nhân

Chỉ ghi thông điệp exception thường khiến việc điều tra bị cụt:

```java
catch (Exception e) {
    LOGGER.severe("Startup failed: " + e.getMessage());
}
```

Cách này làm mất stack trace và chuỗi `cause` trong bản ghi. Khi thực sự xử lý hoặc báo lỗi tại ranh giới phù hợp, truyền cả đối tượng ngoại lệ:

```java
catch (Exception e) {
    LOGGER.log(Level.SEVERE,
            "runId=" + runId + " operation=startupConfig outcome=failed",
            e);
}
```

Đoạn thứ hai giả định `LOGGER` và `runId` đã có trong phạm vi phương thức, nên là **mẫu minh họa trong một khối `catch`**, không phải chương trình độc lập.

Khi chuyển ngoại lệ giữa các lớp, giữ nguyên nguyên nhân bằng constructor nhận `cause` (ví dụ `new IllegalArgumentException("Invalid config", e)`). Không log cùng một stack trace ở mọi tầng rồi lại ném tiếp nếu không có thêm ngữ cảnh: nó tạo nhiều bản ghi trùng, dễ khiến một lỗi bị đếm thành nhiều sự cố. Quy ước phổ biến là thêm ngữ cảnh khi chuyển tầng và log đầy đủ một lần ở ranh giới xử lý cuối.

Một ngoại lệ đã được dự đoán và xử lý thành công, chẳng hạn retry rồi khôi phục, có thể chỉ cần `WARNING` kèm số lần thử và kết quả. Không dùng `SEVERE` cho mọi ngoại lệ.

## 6. Ghép dấu vết trong nhiều luồng hoặc nhiều dịch vụ

Đối với một request đi qua controller, service, repository hoặc các dịch vụ khác nhau, **correlation ID** giúp gom đúng sự kiện:

```text
INFO  requestId=req-42 component=OrderController stage=received
INFO  requestId=req-42 component=OrderService stage=validated
WARNING requestId=req-42 component=InventoryClient stage=reserve outcome=retry attempt=1
SEVERE requestId=req-42 component=OrderService stage=reserve outcome=failed errorCode=UPSTREAM_TIMEOUT
```

Đây là một tình huống minh họa. Từ chuỗi này ta biết lỗi xuất hiện sau bước validate, ở bước giữ hàng tồn kho; cần xem log của thành phần phụ thuộc và nguyên nhân timeout trước khi kết luận lỗi nằm trong mã nghiệp vụ.

`java.util.logging` không cung cấp sẵn cơ chế tự động truyền `requestId` qua tất cả thread và service. Ứng dụng phải đưa ID vào ngữ cảnh tác vụ rồi truyền tiếp khi tạo task, gửi thông điệp hoặc gọi HTTP. Trong các thư viện logging khác, MDC/thread context có thể hỗ trợ nhưng vẫn cần xử lý khi chuyển luồng và dọn ngữ cảnh để tránh gán nhầm ID.

Khi số lượng log quá lớn, nên ưu tiên tìm theo khoảng thời gian + `service` + correlation ID + `errorCode`, thay vì dò thủ công toàn bộ file.

## 7. Những lỗi logging làm việc điều tra khó hơn

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ ghi `"error"` hoặc `e.getMessage()` | Không biết bước nào, stack trace bị mất | Ghi operation, stage, ID và `Throwable` |
| Không có ID liên kết | Log các request đồng thời bị trộn | Truyền ID cho từng request/job |
| Chỉ ghi lúc lỗi, không có dấu mốc trước đó | Không thấy bước cuối thành công | Ghi mốc bắt đầu/kết thúc và ranh giới quan trọng |
| Log cùng exception tại mọi lớp | Nhiều stack trace trùng, nhiễu cảnh báo | Chọn ranh giới log chính; giữ cause khi ném tiếp |
| Ghi input thô hoặc thông tin bí mật | Rò rỉ dữ liệu, nguy cơ giả mạo dòng log | Che/xóa dữ liệu nhạy cảm, chuẩn hóa đầu vào không tin cậy |
| Bật debug tràn lan | Tốn tài nguyên, khó tìm tín hiệu | Điều chỉnh level, thời gian bật và chính sách lưu trữ |
| Không có timestamp/múi giờ nhất quán | Khó tái dựng trình tự giữa hệ thống | Dùng mốc thời gian chuẩn, kiểm tra đồng bộ đồng hồ |
| Coi mọi lỗi là `SEVERE` | Cảnh báo sai mức độ, khó ưu tiên | Phân loại theo tác động thực tế và khả năng phục hồi |

Cần phân biệt **log**, **metric** và **trace**: log diễn giải từng sự kiện; metric cho biết xu hướng/tỷ lệ/độ trễ; distributed trace thể hiện đường đi và thời gian các bước của một request. Khi điều tra hệ thống phân tán, kết hợp cả ba sẽ đáng tin cậy hơn chỉ dựa vào một dòng exception.

## 8. Checklist trước khi coi một lỗi đã được giải thích

- Có bằng chứng về thời gian, môi trường, thành phần và phạm vi ảnh hưởng.
- Tìm được các log liên quan đến cùng request/job/run và điểm bắt đầu thất bại.
- Đọc đủ stack trace, chuỗi `Caused by`, trạng thái phụ thuộc và ngữ cảnh phù hợp.
- Tách rõ **triệu chứng**, **giả thuyết** và **nguyên nhân đã kiểm chứng**.
- Có cách tái hiện hoặc phép kiểm chứng đáng tin cậy, cùng kết quả sau khi sửa.
- Log bổ sung đủ giá trị điều tra mà không làm lộ dữ liệu nhạy cảm hoặc tạo nhiễu.

**Kết quả mong đợi của logging phục vụ điều tra lỗi** là trả lời được *điều gì hỏng, hỏng ở bước nào, liên quan đến công việc nào, vì sao có khả năng xảy ra và bằng chứng nào xác nhận điều đó*. Log tốt giúp giảm thời gian tìm nguyên nhân và giúp lần điều tra tiếp theo dễ hơn, nhưng kết luận vẫn phải dựa trên kiểm chứng thực tế.
