# Bài toán logging giải quyết

## 1. Vì sao ứng dụng cần logging?

Giả sử dịch vụ đặt hàng hoạt động bình thường trên máy lập trình, nhưng thỉnh thoảng trả lỗi khi chạy trên server. Người dùng chỉ thấy thông báo “Đặt hàng thất bại”; lập trình viên không đứng cạnh server để quan sát từng câu lệnh. Nếu chương trình không ghi lại các sự kiện có ý nghĩa, nhóm vận hành khó biết yêu cầu nào bị ảnh hưởng, lỗi xảy ra lúc nào, đã đi qua bước nào và nguyên nhân kỹ thuật nào được phát hiện.

**Logging** là việc ứng dụng ghi lại các **sự kiện trong quá trình chạy** thành các bản ghi (log record) để con người hoặc hệ thống khác có thể tra cứu, lọc và phân tích. Mục tiêu chính là **tạo dấu vết có ngữ cảnh về những gì ứng dụng đã quan sát được tại thời điểm chạy**.

Logging hữu ích ngay cả khi chương trình không lỗi: nó cho biết ứng dụng đã khởi động, nhận yêu cầu, thực hiện tác vụ quan trọng hay hoàn tất một thao tác. Khi sự cố xuất hiện, các sự kiện bình thường trước đó giúp xác định điểm bắt đầu bất thường.

Ví dụ hai thông điệp sau mang lượng thông tin rất khác nhau:

```text
Lỗi!
```

```text
level=SEVERE service=order-api requestId=req-42 orderId=ord-17
event=inventory_reservation_failed cause=InventoryServiceUnavailable
```

Bản ghi thứ hai cho phép tìm đúng yêu cầu, nhận diện bước thất bại và khoanh vùng thành phần cần điều tra. Nó **không tự chứng minh nguyên nhân gốc**; nhóm phát triển vẫn phải đối chiếu mã nguồn, hệ thống phụ thuộc và bằng chứng khác.

## 2. Những bài toán logging giúp giải quyết

### 2.1. Quan sát một chương trình đang chạy ngoài môi trường phát triển

Trong ứng dụng server, tác vụ nền, job theo lịch hoặc hệ thống nhiều luồng, không thể luôn dừng chương trình bằng debugger. Log ghi lại các dấu mốc như “ứng dụng sẵn sàng”, “bắt đầu xử lý”, “gọi dịch vụ phụ thuộc”, “thử lại” và “hoàn tất”.

Nhờ vậy, người vận hành có thể trả lời: **Ứng dụng đã thực sự nhận công việc chưa? Nó dừng ở bước nào?** Đây là năng lực quan sát hoạt động, không có nghĩa là mọi câu lệnh đều phải được ghi log.

### 2.2. Dựng lại diễn biến trước và sau một lỗi

Một exception thường cho biết *điều gì thất bại* tại một vị trí mã. Log ở các mốc liên quan cho biết *diễn biến dẫn đến lỗi*:

```text
10:15:03.100 INFO  requestId=req-42 event=order_received
10:15:03.120 INFO  requestId=req-42 event=inventory_reservation_started
10:15:03.310 WARN  requestId=req-42 event=inventory_retry attempt=2
10:15:03.620 ERROR requestId=req-42 event=inventory_reservation_failed
```

Đây là chuỗi minh họa; mốc thời gian, mức log và tên sự kiện phụ thuộc ứng dụng. Các mốc giúp khoanh vùng khoảng thời gian xảy ra sự cố và phân biệt “chưa nhận yêu cầu”, “đã bắt đầu nhưng phụ thuộc chậm” và “đã kết thúc với lỗi”.

**Giới hạn:** không thể khẳng định một bước không diễn ra chỉ vì không tìm thấy log của bước đó. Log có thể bị lọc, bị rơi, ghi trễ hoặc không được lập trình tại nhánh tương ứng.

### 2.3. Chẩn đoán lỗi và giảm thời gian tìm nguyên nhân

Khi bắt được lỗi ngoài dự kiến tại một ranh giới xử lý thích hợp, log nên chứa **thao tác**, **ngữ cảnh liên quan** và **exception gốc**. Với Java, lời gọi `logger.log(Level.SEVERE, "Thông điệp", exception)` giữ đối tượng `Throwable` để formatter/handler có thể ghi thông tin lỗi và stack trace.

Ví dụ, thay vì chỉ ghi “Không lưu được”, nên biết đó là thao tác lưu đơn hàng nào, xảy ra trong request nào và exception thuộc loại gì. Stack trace cho biết đường gọi dẫn đến lỗi; mã lỗi hoặc phản hồi của dịch vụ phụ thuộc có thể giúp điều tra sâu hơn.

Không nên bắt exception rồi chỉ ghi thông báo và bỏ qua nếu lời gọi phía trên vẫn cần biết thao tác thất bại. Cũng không nên ghi **cùng một exception ở mọi tầng** khiến một lỗi thành hàng chục bản ghi trùng lặp. Hãy xác định tầng chịu trách nhiệm ghi và cách truyền hoặc xử lý lỗi.

### 2.4. Liên kết các sự kiện của cùng một yêu cầu

Server có nhiều request chạy xen kẽ; chỉ sắp log theo thời gian có thể trộn lẫn các luồng xử lý. Đưa một **requestId** hoặc **correlationId** nhất quán vào các bản ghi giúp lọc những sự kiện thuộc cùng một giao dịch.

Ví dụ, khi `req-42` đi qua API → dịch vụ đặt hàng → dịch vụ kho, mỗi thành phần cần truyền hoặc ghi một định danh tương quan phù hợp. Tên thread một mình không đủ vì thread pool có thể tái sử dụng luồng cho các request khác nhau. Trong hệ thống phân tán, `traceId` và `spanId` thường giúp liên kết log với distributed tracing; chúng phải được truyền đúng qua ranh giới dịch vụ.

### 2.5. Hỗ trợ vận hành, cảnh báo và hỗ trợ người dùng

Log giúp nhân viên hỗ trợ tìm một sự kiện theo mã yêu cầu, thời gian hoặc thao tác; giúp người trực vận hành đối chiếu thay đổi triển khai với thời điểm lỗi tăng; và cung cấp dữ liệu cho hệ thống cảnh báo khi được thu thập, phân tích đúng cách.

Các thông điệp có cấu trúc ổn định, mức độ rõ ràng và ngữ cảnh nhất quán thường dễ tìm kiếm hơn câu tự do như “Vào hàm A” hoặc “Đã tới đây”. Tuy nhiên, **log không thay thế metrics** cho số lượng, tỉ lệ lỗi, độ trễ hay SLO; metrics thường phù hợp hơn với việc đo xu hướng, còn logs giúp xem chi tiết sự kiện cụ thể.

### 2.6. Cung cấp dấu vết phục vụ kiểm tra nghiệp vụ

Một số hành động quan trọng (ví dụ thay đổi trạng thái đơn hàng hoặc cập nhật cấu hình) cần dấu vết “hành động nào, lúc nào, kết quả gì”. Diagnostic log có thể hỗ trợ tra cứu, nhưng **audit trail có yêu cầu riêng** về độ đầy đủ, quyền truy cập, chống sửa đổi, thời hạn lưu trữ và bảo vệ dữ liệu. Không được mặc định rằng vài dòng log thông thường đã đáp ứng yêu cầu audit hay pháp lý.

## 3. Một log record hữu ích cần những thông tin gì?

Không nhất thiết mỗi bản ghi phải có mọi trường, nhưng cần đủ ngữ cảnh để trả lời câu hỏi điều tra mà không làm lộ dữ liệu nhạy cảm.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Thời điểm và múi giờ | Xác định lúc sự kiện xảy ra, đối chiếu giữa hệ thống | `2026-11-09T03:15:03.620Z` |
| Mức độ (level) | Phân biệt hoạt động bình thường, dấu hiệu bất thường và lỗi | `INFO`, `WARNING`, `SEVERE` |
| Nguồn phát sinh | Xác định service, component hoặc logger | `order-api`, `InventoryClient` |
| Sự kiện/thao tác | Cho biết hành động và trạng thái, nên có tên ổn định | `event=reserve_failed` |
| Mã tương quan | Gom các log của cùng request/job/giao dịch | `requestId=req-42` |
| Ngữ cảnh nghiệp vụ an toàn | Hỗ trợ truy vết mà không lộ bí mật | `orderId=ord-17` |
| Chi tiết lỗi khi có | Cung cấp loại exception, thông điệp và stack trace phù hợp | `IllegalStateException` |

Thời điểm và nơi ghi log có thể do logger/handler bổ sung; không cần tự ghép mọi trường vào từng chuỗi. Với ứng dụng thực tế, log dạng JSON hoặc key–value cùng schema nhất quán thường thuận lợi cho hệ thống tập trung. Không ghi token, mật khẩu, khóa API, dữ liệu thẻ, nội dung nhạy cảm hoặc toàn bộ request/response một cách tùy tiện; mã định danh cũng cần được xem xét theo chính sách bảo mật.

### Chọn mức log theo ý nghĩa

Trong `java.util.logging` (JUL) của JDK:

- **`SEVERE`:** lỗi nghiêm trọng hoặc thao tác thất bại ngoài dự kiến cần chú ý.
- **`WARNING`:** điều kiện bất thường nhưng có thể xử lý/phục hồi, ví dụ retry hoặc dữ liệu đầu vào không hợp lệ cần theo dõi.
- **`INFO`:** những mốc hoạt động chính, ví dụ bắt đầu và hoàn tất một tác vụ có ý nghĩa.
- **`FINE` / `FINER` / `FINEST`:** chi tiết phục vụ chẩn đoán, thường chỉ bật có chọn lọc.

Các framework khác có thể dùng tên `ERROR`, `WARN`, `DEBUG`, `TRACE`. **Level phản ánh mức độ của sự kiện**, không phản ánh độ dài thông điệp. Ví dụ hết hàng theo quy tắc nghiệp vụ thông thường không nhất thiết là `SEVERE`, trong khi kho dữ liệu phụ thuộc ngừng hoạt động có thể là lỗi vận hành nghiêm trọng.

## 4. Ví dụ Java 17+: nhìn thấy hành trình của một yêu cầu

Chương trình sau mô phỏng hai yêu cầu đặt hàng. Yêu cầu thứ nhất thất bại vì dịch vụ kho không khả dụng; yêu cầu thứ hai thành công. Ví dụ dùng logger có sẵn của JDK, **không cần dependency bên ngoài**.

Lưu toàn bộ vào tệp `LoggingProblemDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingProblemDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingProblemDemo.class.getName());

    public static void main(String[] args) {
        configureLogging();
        processOrder("req-42", "ord-17", false);
        processOrder("req-43", "ord-18", true);
    }

    private static void configureLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = "";
                if (record.getThrown() != null) {
                    Throwable error = record.getThrown();
                    cause = " cause=" + error.getClass().getSimpleName()
                            + ":" + error.getMessage();
                }
                return record.getLevel().getName() + " "
                        + record.getMessage() + cause
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    private static void processOrder(
            String requestId, String orderId, boolean inventoryAvailable) {
        String context = "requestId=" + requestId + " orderId=" + orderId;
        LOG.info(context + " event=order_received");

        try {
            reserveInventory(inventoryAvailable);
            LOG.info(context + " event=inventory_reserved");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE,
                    context + " event=inventory_reservation_failed", error);
        }
    }

    private static void reserveInventory(boolean available) {
        if (!available) {
            throw new IllegalStateException("inventory service unavailable");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LoggingProblemDemo.java
java LoggingProblemDemo
```

Kết quả trên console (handler dùng luồng lỗi chuẩn, `stderr`):

```text
INFO requestId=req-42 orderId=ord-17 event=order_received
SEVERE requestId=req-42 orderId=ord-17 event=inventory_reservation_failed cause=IllegalStateException:inventory service unavailable
INFO requestId=req-43 orderId=ord-18 event=order_received
INFO requestId=req-43 orderId=ord-18 event=inventory_reserved
```

**Đọc kết quả:** lọc `requestId=req-42` thấy yêu cầu đã được nhận, sau đó bước đặt giữ hàng thất bại; `requestId=req-43` có sự kiện hoàn tất bình thường. Ngoại lệ được truyền vào `LOG.log(..., error)` nên logger có thể cung cấp thông tin chẩn đoán. Formatter tự viết ở đây chỉ in loại lỗi và thông điệp để output **ổn định, dễ kiểm chứng**; trong ứng dụng thực tế nên dùng formatter/handler bảo toàn stack trace và timestamp, đồng thời cấu hình đích ghi, thời hạn lưu trữ và cơ chế thu thập thích hợp.

Ví dụ chỉ minh họa hai tình huống mô phỏng. Sự kiện `inventory service unavailable` là lỗi được chương trình chủ động tạo ra khi cờ `inventoryAvailable` bằng `false`; nó không chứng minh đã có một dịch vụ mạng hoặc cơ sở dữ liệu thật bị lỗi.

## 5. Logging khác gì so với `System.out.println`?

| Khía cạnh | `System.out.println` | Logging qua API/framework |
|---|---|---|
| Mục đích | In chuỗi ra stdout | Ghi sự kiện có ngữ nghĩa phục vụ theo dõi và chẩn đoán |
| Phân mức | Không có level mặc định | Có level để điều chỉnh độ chi tiết |
| Ngữ cảnh/metadata | Phải tự ghép nếu cần | Có thể cấu hình timestamp, logger name, thread, correlation ID |
| Đích ghi | Stdout | Console, file, collector hoặc handler/appender tùy cấu hình |
| Xử lý exception | Thường tự in hoặc gọi `printStackTrace` | Có API ghi kèm `Throwable` |
| Quản lý khi vận hành | Khó điều chỉnh đồng bộ khi dùng rải rác | Thường hỗ trợ lọc, format, cấu hình, thu thập tập trung |

`println` vẫn hữu ích khi học ngôn ngữ hoặc viết chương trình nhỏ. Trong ứng dụng dài hạn, logging giúp tổ chức thông tin theo sự kiện, điều chỉnh mức độ ghi và tích hợp với vận hành. Tuy nhiên, dùng logging API **không tự bảo đảm** log được lưu bền vững hay được tập trung; điều đó còn phụ thuộc cấu hình và hạ tầng.

## 6. Các sai lầm phổ biến và giới hạn của logging

1. **Ghi quá ít hoặc thiếu ngữ cảnh:** “Lỗi xử lý” không cho biết request và thao tác nào thất bại. Hãy ghi mã tương quan, tên sự kiện và ngoại lệ ở tầng thích hợp.
2. **Ghi quá nhiều:** in mọi vòng lặp hoặc toàn bộ payload có thể tăng chi phí I/O, tốn lưu trữ, làm chìm tín hiệu có ích và ảnh hưởng hiệu năng. Chọn dấu mốc quan trọng, điều chỉnh level hoặc lấy mẫu có chủ đích.
3. **Ghi dữ liệu nhạy cảm:** không đưa password, access token, secret, dữ liệu cá nhân không cần thiết vào log. Chú ý cả thông điệp exception, URL query và dữ liệu nhập từ người dùng; kiểm soát việc xuống dòng hoặc ký tự điều khiển gây giả mạo bản ghi.
4. **Mất nguyên nhân lỗi:** chỉ ghi `error.getMessage()` có thể bỏ mất stack trace và chuỗi nguyên nhân. Truyền `Throwable` cho logger tại nơi ghi lỗi, nhưng tránh lặp lại cùng lỗi ở nhiều tầng.
5. **Sai level:** tình huống nghiệp vụ mong đợi bị ghi `SEVERE` sẽ tạo cảnh báo giả; lỗi thật chỉ ghi `FINE` có thể bị lọc mất.
6. **Không có định danh liên kết:** những dòng log từ nhiều request xen nhau khó dùng để dựng lại luồng xử lý.
7. **Hiểu log là nguồn sự thật tuyệt đối:** log có thể bị lọc, buffer chưa flush, mất khi crash, thiếu đồng bộ đồng hồ hoặc hết thời gian lưu. Không dùng “không có log” làm bằng chứng chắc chắn rằng sự kiện không xảy ra.

Ba nguồn tín hiệu thường bổ trợ nhau trong vận hành là **logs** (sự kiện chi tiết), **metrics** (số đo tổng hợp theo thời gian) và **traces** (đường đi và thời lượng của một yêu cầu qua các thành phần). Logging giải quyết tốt bài toán tạo dấu vết sự kiện; không thay thế kiểm thử, giám sát định lượng hay distributed tracing.

## 7. Cách đánh giá log có thực sự giải quyết được bài toán

Với một sự cố giả định, hãy thử trả lời các câu sau chỉ từ những bản ghi cần thiết: **(1)** yêu cầu hoặc job nào chịu ảnh hưởng; **(2)** lúc nào bắt đầu và kết thúc; **(3)** bước cuối cùng được ghi nhận thành công; **(4)** sự kiện lỗi và exception là gì; **(5)** có thể liên kết những sự kiện cùng ngữ cảnh mà không lộ dữ liệu nhạy cảm không?

Nếu còn thiếu câu trả lời, bổ sung **đúng sự kiện và trường ngữ cảnh còn thiếu**, thay vì tăng số lượng câu `println` một cách ngẫu nhiên. Một hệ thống log hữu ích giúp nhóm phát triển và vận hành thu hẹp phạm vi điều tra, giải thích điều ứng dụng đã quan sát được và xử lý sự cố nhanh hơn, trong giới hạn của bằng chứng mà log thực sự ghi lại.
