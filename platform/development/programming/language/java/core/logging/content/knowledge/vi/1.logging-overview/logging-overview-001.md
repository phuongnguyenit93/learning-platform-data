# Logging là gì? — Tổng quan Java Logging

## 1. Khái niệm

**Logging** là việc chương trình tạo và ghi lại các sự kiện xảy ra khi chạy, dưới dạng thông điệp có ngữ cảnh để con người hoặc hệ thống quan sát có thể tra cứu sau này. Một sự kiện có thể là ứng dụng khởi động, yêu cầu được xử lý, cấu hình thiếu, kết nối chậm hoặc một ngoại lệ phát sinh.

Một bản ghi log thường mang những thông tin sau:

- **Thời điểm** xảy ra sự kiện, có múi giờ rõ ràng.
- **Mức độ nghiêm trọng (level)**: INFO, WARN, ERROR… tùy hệ thống logging.
- **Nguồn phát sinh**: tên ứng dụng, lớp hoặc logger, đôi khi kèm luồng (thread).
- **Thông điệp và ngữ cảnh**: hành động, mã yêu cầu/đơn hàng, thời gian xử lý, kết quả.
- **Nguyên nhân lỗi**: loại ngoại lệ và stack trace khi cần chẩn đoán.

Ví dụ minh họa (định dạng thực tế phụ thuộc cấu hình):

~~~text
2026-11-09T10:00:00Z INFO  order-service orderId=ORD-42 Đã tạo đơn hàng
2026-11-09T10:00:02Z WARN  order-service orderId=ORD-42 Dịch vụ tồn kho phản hồi chậm
~~~

Logging trả lời những câu hỏi như “chuyện gì đã xảy ra?”, “xảy ra lúc nào?”, “ở bước nào?” và “vì sao thất bại?”. Log là dữ liệu quan sát vận hành, không phải chức năng nghiệp vụ chính.

## 2. Logging giúp ích gì?

1. **Chẩn đoán lỗi:** lần theo các sự kiện dẫn tới lỗi, lưu ngoại lệ và ngữ cảnh cần thiết để tái hiện vấn đề.
2. **Theo dõi vận hành:** biết ứng dụng đã khởi động, gọi dịch vụ nào, tác vụ nào hoàn thành hoặc thất bại.
3. **Tìm vấn đề hiệu năng:** ghi thời lượng bước xử lý và dấu hiệu timeout/chậm bất thường; muốn phân tích định lượng liên tục vẫn cần metrics.
4. **Điều tra sự cố phân tán:** đối chiếu các log liên quan bằng request ID, trace ID hoặc correlation ID.
5. **Hỗ trợ kiểm tra hành vi:** xác minh một nhánh xử lý thực sự đã chạy trong môi trường khó gắn debugger.

Logging khác với một số công cụ liên quan:

| Công cụ | Dùng chủ yếu để | Điểm cần nhớ |
| --- | --- | --- |
| Logging | Lưu các **sự kiện rời rạc** cùng ngữ cảnh | Cần cấu hình mức log, đích xuất và thời gian lưu |
| Debugger | Dừng chương trình, xem biến và từng bước thực thi | Thích hợp khi phát triển, khó dùng trực tiếp trên mọi sự cố production |
| Metrics | Đo số lượng, tỷ lệ và phân bố theo thời gian | Ví dụ: số request/giây, tỷ lệ lỗi, latency p95 |
| Tracing | Theo dõi đường đi của một request qua nhiều thành phần | Span/trace ID giúp liên kết với log |
| Audit trail | Ghi bằng chứng về hành động quan trọng cần truy vết | Có thể cần bảo đảm toàn vẹn, phân quyền và thời hạn lưu nghiêm ngặt hơn log kỹ thuật |

Một dòng in bằng **System.out.println** có thể giúp quan sát nhanh, nhưng thường thiếu level, nguồn phát sinh và khả năng lọc/cấu hình tập trung. Trong ứng dụng thực tế nên dùng logging API.

## 3. Logging hoạt động như thế nào?

Luồng xử lý phổ biến trong Java:

~~~text
Mã ứng dụng
   → Logger (tạo sự kiện, xét level/filter)
   → LogRecord hoặc logging event
   → Handler/Appender (xét level/filter, chọn đích)
   → Formatter/Encoder (biểu diễn thành text hoặc JSON)
   → Console, tệp, dịch vụ thu thập log…
~~~

- **Logger** là đối tượng mã nguồn dùng để phát sự kiện; thường đặt theo tên lớp hoặc thành phần.
- **Level** quyết định thông điệp nào đủ quan trọng để xử lý. Sự kiện có thể bị chặn ở logger và cả handler/appender.
- **Handler** (thuật ngữ của java.util.logging, viết tắt **JUL**) hoặc **appender** (thuật ngữ thường thấy ở Logback/Log4j) quyết định gửi log đi đâu.
- **Formatter/encoder** quyết định biểu diễn log, ví dụ thời gian + level + thông điệp hoặc JSON.
- **Đích ghi** có thể là console, tệp, hệ thống tập trung. Một sự kiện chỉ thực sự được lưu ở nơi đích khi quá trình ghi/chuyển tiếp thành công; logging không tự bảo đảm lưu bền vững.

Trong ứng dụng nhiều luồng, các sự kiện có thể xen kẽ nhau. Thứ tự dòng log ở một nơi thu thập không phải lúc nào cũng là thứ tự toàn cục của mọi thao tác. Vì thế timestamp, thread và correlation ID rất hữu ích.

## 4. Các mức log và cách chọn

Java cung cấp sẵn **java.util.logging** trong JDK. Các level thông dụng của JUL, theo mức nghiêm trọng giảm dần, gồm:

| JUL level | Ý nghĩa thường dùng |
| --- | --- |
| SEVERE | Lỗi nghiêm trọng, thao tác hoặc thành phần bị thất bại |
| WARNING | Bất thường, có rủi ro, nhưng có thể tiếp tục hoặc phục hồi |
| INFO | Cột mốc vận hành đáng quan tâm |
| CONFIG | Thông tin cấu hình phục vụ chẩn đoán |
| FINE | Chi tiết debug thông thường |
| FINER, FINEST | Chi tiết ngày càng sâu để phân tích luồng thực thi |

**OFF** và **ALL** chủ yếu dùng để cấu hình ngưỡng lọc, không phải tên mức sự kiện nghiệp vụ cần phát thường xuyên. Ở nhiều thư viện khác, tên phổ biến là **ERROR → WARN → INFO → DEBUG → TRACE**. Có thể liên hệ gần đúng ERROR với SEVERE, WARN với WARNING, DEBUG với FINE; chúng không phải một hệ thống level đồng nhất giữa mọi thư viện.

Ví dụ chọn mức:

- **INFO:** “Ứng dụng sẵn sàng nhận yêu cầu”; “Đã hoàn tất đồng bộ 120 bản ghi”.
- **WARNING:** “Dịch vụ ngoài phản hồi chậm, đang thử lại”.
- **SEVERE:** “Không thể kết nối cơ sở dữ liệu, chức năng khởi tạo thất bại”.
- **FINE:** “Đã chọn nhánh xử lý dự phòng với trạng thái X”.

Ngưỡng INFO thông thường cho phép INFO, WARNING và SEVERE, đồng thời chặn FINE/FINER/FINEST. **Level mô tả mức độ quan trọng của sự kiện; nó không tự sửa lỗi hay quyết định luồng điều khiển.**

## 5. Ví dụ Java 17+ chạy được: java.util.logging

JUL có sẵn trong JDK, không cần cài thư viện ngoài. Ví dụ dưới đây chủ động cấu hình một handler để kết quả dễ kiểm chứng.

Tạo tệp **LoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingDemo {
    private static final Logger LOGGER =
            Logger.getLogger(LoggingDemo.class.getName());

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        LOGGER.addHandler(output);

        LOGGER.info("Ứng dụng đã khởi động");
        LOGGER.log(Level.INFO, "Đã xử lý {0} bản ghi", 3);
        LOGGER.warning("Thiếu cấu hình tùy chọn");
        LOGGER.fine("Chi tiết chỉ dành cho debug");

        output.flush();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên, trong terminal hỗ trợ UTF-8:

~~~bash
javac -encoding UTF-8 LoggingDemo.java
java LoggingDemo
~~~

Kết quả **stdout** chính xác của chương trình này (mỗi dòng kết thúc bằng newline):

~~~text
INFO | Ứng dụng đã khởi động
INFO | Đã xử lý 3 bản ghi
WARNING | Thiếu cấu hình tùy chọn
~~~

Giải thích:

1. **Logger.getLogger(...)** lấy logger mang tên lớp. **setUseParentHandlers(false)** tránh phát thêm qua handler của logger cha, nhờ vậy không bị log hai lần trong ví dụ.
2. **LOGGER.setLevel(Level.INFO)** và **output.setLevel(Level.INFO)** đặt ngưỡng ở cả logger và handler. Vì thế dòng **fine(...)** không được xuất.
3. **StreamHandler(System.out, ...)** gửi log ra stdout. **Formatter** được tùy biến để chỉ in level và message; trong production nên có timestamp, nguồn và ngữ cảnh.
4. **LOGGER.log(Level.INFO, "Đã xử lý {0} bản ghi", 3)** dùng placeholder **{0}** theo kiểu định dạng của JUL. Dấu **{}** là kiểu phổ biến trong SLF4J, không được thay thế tương đương trong lời gọi JUL này.
5. **output.flush()** đẩy dữ liệu đang được StreamHandler đệm ra stdout. ConsoleHandler mặc định của JUL thường ghi ra stderr; hai handler có đặc điểm khác nhau.

Trong ứng dụng thực, cấu hình thường đặt tập trung (tệp cấu hình, biến môi trường hoặc cấu hình framework) thay vì tạo handler mỗi khi xử lý một yêu cầu.

## 6. Ghi log ngoại lệ đúng cách

Khi cần biết **tại sao** thao tác thất bại, hãy ghi đối tượng ngoại lệ để hệ thống logging giữ được stack trace và chuỗi nguyên nhân. Ví dụ đoạn mã sau có thể đặt trong một phương thức sử dụng logger ở trên:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (NumberFormatException ex) {
    LOGGER.log(Level.WARNING, "Giá trị số đầu vào không hợp lệ", ex);
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập; thông tin stack trace và vị trí dòng phụ thuộc nơi bạn đặt nó. Chỉ ghi message của ngoại lệ thường làm mất ngữ cảnh cần để chẩn đoán.

Một nguyên tắc hữu ích là **ghi lỗi ở nơi có đủ ngữ cảnh để quyết định cách xử lý**. Nếu một tầng đã log ngoại lệ rồi ném tiếp lên tầng trên và tầng trên cũng log cùng lỗi, bạn có thể nhận nhiều bản ghi lặp cho một sự cố. Tránh bắt ngoại lệ, log rồi im lặng nếu logic nghiệp vụ cần biết thao tác đã thất bại.

## 7. Chọn nội dung log có giá trị

Một log tốt thường trả lời được: **sự kiện gì, liên quan đối tượng nào, kết quả ra sao và mất bao lâu**. Khi có request/trace ID, hãy ghi nó nhất quán để liên kết các bước, ví dụ:

~~~text
INFO order-service requestId=req-17 orderId=ORD-42 action=create result=success durationMs=28
~~~

Các trường cụ thể tùy ứng dụng; minh họa trên không phải output của chương trình Java ở mục 5. Với hệ thống nhiều dịch vụ, định dạng log có cấu trúc (ví dụ JSON) giúp tìm kiếm/lọc theo trường chính xác hơn so với ghép văn bản tự do.

Chỉ đưa vào log thông tin thực sự phục vụ chẩn đoán. **Không ghi mật khẩu, access token, API key, số thẻ, cookie phiên, hoặc dữ liệu cá nhân nhạy cảm ở dạng thô.** Nếu bắt buộc dùng một định danh, ưu tiên mã nội bộ, rút gọn hoặc che phần nhạy cảm theo quy định hệ thống. Không mặc định log toàn bộ HTTP request/response body.

## 8. Hiệu năng và vận hành

- **Không log quá dày trong vòng lặp:** hàng triệu dòng INFO có thể gây chi phí I/O, lưu trữ và khó tìm sự kiện quan trọng. Dùng counters/metrics để đếm tần suất lớn.
- **Tránh tạo thông điệp tốn kém khi level bị tắt:** JUL hỗ trợ supplier, chẳng hạn **LOGGER.log(Level.FINE, () -> "Đang xử lý: " + soBanGhi)** nếu biến **soBanGhi** tồn tại và effectively final. Supplier không được đánh giá khi logger loại bỏ level đó.
- **Đặt ngưỡng phù hợp môi trường:** thường INFO cho hoạt động thông thường; bật FINE/DEBUG trong phạm vi hẹp và thời gian có kiểm soát khi điều tra sự cố.
- **Quản lý dung lượng và thời hạn lưu:** cần rotation, giới hạn dung lượng, chính sách retention và quyền truy cập. Container thường ghi stdout/stderr để hạ tầng thu thập log.
- **Tính đến mất log:** buffer, quá tải hoặc sự cố ở hệ thống nhận có thể khiến log không đến đích. Không dùng một dòng log thông thường làm bằng chứng duy nhất cho giao dịch quan trọng.
- **Giữ định dạng nhất quán:** dùng timestamp có múi giờ rõ ràng (thường UTC), level, service, correlation ID và mã sự kiện ổn định khi thích hợp.

## 9. JUL, SLF4J, Logback và Log4j 2 khác nhau ra sao?

| Thành phần | Vai trò |
| --- | --- |
| **java.util.logging (JUL)** | API và triển khai logging tích hợp trong JDK; dùng trực tiếp không cần dependency |
| **SLF4J** | Facade/API thống nhất để mã ứng dụng gọi logging; cần provider/backend thích hợp để thực sự xuất log |
| **Logback** | Một backend logging thường được dùng với SLF4J, hỗ trợ appender, encoder và cấu hình phong phú |
| **Log4j 2** | Framework logging có API, core và hệ sinh thái cấu hình riêng; có thể tích hợp với SLF4J theo cấu hình phù hợp |

Đối với người mới học Java Core, bắt đầu với JUL là đủ để hiểu logger, level, handler và formatter. Trong dự án dùng framework, hãy theo lựa chọn logging đã thống nhất của dự án, tránh cài nhiều backend/bridge chồng chéo gây ghi trùng hoặc vòng lặp chuyển tiếp.

## 10. Lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng System.out.println khắp nơi | Không phân cấp, khó lọc và quản lý | Dùng logger và level |
| Phát mọi sự kiện ở INFO/SEVERE | Nhiễu cảnh báo, tốn tài nguyên | Chọn mức theo ý nghĩa thật của sự kiện |
| Chỉ log “Có lỗi” | Không đủ thông tin truy vết | Ghi hành động, ID liên quan và throwable khi cần |
| Log dữ liệu bí mật | Rò rỉ thông tin qua console, file và hệ thống thu thập | Không ghi bí mật; lọc/che dữ liệu nhạy cảm |
| Log rồi ném tiếp qua nhiều tầng | Nhiều dòng lỗi cho một nguyên nhân | Quy định tầng chịu trách nhiệm log |
| Chỉ cấu hình logger mà quên handler | Log mong đợi có thể không xuất hiện | Kiểm tra cả ngưỡng logger và handler/appender |
| Giả định log luôn đúng thứ tự và được lưu mãi | Sai khi có nhiều luồng, buffer hoặc rotation | Dùng timestamp/correlation ID và chính sách lưu phù hợp |

## 11. Tự kiểm tra kiến thức

**Tình huống A:** Chương trình đặt logger và handler đều ở INFO, rồi gọi fine(...). Có xuất log không? **Không**, vì FINE thấp hơn ngưỡng INFO.

**Tình huống B:** Bạn muốn hiểu request thất bại vì đâu, nhưng chỉ có dòng “Xử lý lỗi”. Cần cải thiện gì? **Thêm** thao tác đang thực hiện, ID để tương quan và đối tượng ngoại lệ (khi phù hợp), đồng thời tránh dữ liệu nhạy cảm.

**Tình huống C:** Ứng dụng cần biểu đồ tỷ lệ lỗi theo phút và xem mỗi request đi qua nhiều dịch vụ như thế nào. Chỉ log có đủ không? **Không tối ưu**: kết hợp logging với **metrics** để đo tỷ lệ và **tracing** để theo dõi đường đi request.

**Ghi nhớ:** Logging là cơ chế ghi lại sự kiện có ngữ cảnh để quan sát và chẩn đoán ứng dụng. Nắm vững **logger → level/filter → handler/appender → formatter → đích ghi**, chọn mức phù hợp và bảo vệ dữ liệu nhạy cảm là nền tảng để dùng logging đúng trong Java.
