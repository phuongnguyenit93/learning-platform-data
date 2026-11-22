# Level ở production trong Java Logging

## 1. Vì sao cần chọn log level khác khi chạy production?

**Production** là môi trường ứng dụng phục vụ người dùng hoặc nghiệp vụ thực tế. Ở môi trường này, log phải giúp vận hành và chẩn đoán sự cố, đồng thời không làm hệ thống chậm đi, tốn quá nhiều dung lượng hoặc lộ dữ liệu nhạy cảm.

Trong quá trình phát triển, lập trình viên có thể bật **DEBUG/TRACE** hoặc **FINE/FINER/FINEST** để quan sát chi tiết từng nhánh xử lý. Khi chạy production, nếu giữ nguyên độ chi tiết đó cho mọi thành phần, hệ thống dễ gặp những vấn đề sau:

- **Nhiễu thông tin:** Hàng nghìn dòng debug che khuất lỗi thực sự cần điều tra.
- **Chi phí:** Log tiêu tốn CPU để tạo thông điệp, bộ nhớ đệm, I/O, băng thông, lưu trữ, lập chỉ mục và chi phí truy vấn.
- **Độ trễ:** Cấu hình ghi log đồng bộ hoặc quá nhiều sự kiện có thể kéo dài thời gian xử lý yêu cầu.
- **Rủi ro dữ liệu:** Ghi nhầm token, mật khẩu, nội dung yêu cầu, thông tin cá nhân hoặc dữ liệu thanh toán.
- **Khó vận hành:** Dòng log không nhất quán khiến dashboard, truy vấn tìm lỗi và cảnh báo hoạt động kém hiệu quả.

Một chính sách log level tốt có hai mục tiêu: **giữ tín hiệu vận hành thiết yếu luôn sẵn có** và **cho phép bật thông tin chẩn đoán có kiểm soát khi cần**.

**Mức log chỉ cho biết ưu tiên của từng bản ghi**. Việc một sự kiện có cần gọi người trực, mở incident hoặc gửi cảnh báo còn phụ thuộc tác động nghiệp vụ, mức khẩn cấp và quy tắc quan sát. Không nên mặc định mỗi dòng ERROR/SEVERE tương đương một sự cố phải đánh thức đội vận hành.

## 2. Chọn mức mặc định cho production

Trong nhiều ứng dụng Java, ngưỡng **INFO** là điểm khởi đầu phổ biến ở production: giữ lại các sự kiện vận hành quan trọng và loại bỏ phần lớn thông tin debug chi tiết. Tuy nhiên, **INFO không phải giá trị bắt buộc cho mọi hệ thống**. Dịch vụ lưu lượng cực cao, thư viện bên thứ ba quá nhiều log hoặc yêu cầu tuân thủ riêng có thể cần cấu hình theo package, class và loại sự kiện.

### So sánh JUL với hệ sinh thái SLF4J

Java có sẵn **java.util.logging (JUL)**; các hệ thống dùng SLF4J có thể kết nối với backend như Logback hoặc Log4j 2. Hai nhóm sử dụng tên mức khác nhau:

| Ý nghĩa thông thường | JUL | SLF4J/Logback thường dùng | Cách sử dụng ở production |
| --- | --- | --- | --- |
| Lỗi nghiêm trọng | **SEVERE** | **ERROR** | Ghi thất bại thực sự cần điều tra, ưu tiên giữ đầy đủ bằng chứng phù hợp |
| Bất thường hoặc rủi ro | **WARNING** | **WARN** | Ghi dependency chậm, fallback, retry đáng chú ý, nguy cơ suy giảm |
| Sự kiện hoạt động quan trọng | **INFO** | **INFO** | Startup, shutdown, kết quả job, cột mốc nghiệp vụ có ích |
| Cấu hình | **CONFIG** | Không có mức riêng tương ứng | Ghi thông tin cấu hình an toàn khi cần xác định cách ứng dụng khởi chạy |
| Chẩn đoán | **FINE** | **DEBUG** (gần đúng) | Thường tắt ở phần lớn class trong production; bật chọn lọc khi điều tra |
| Truy vết chi tiết | **FINER, FINEST** | **TRACE** (gần đúng) | Chỉ bật trong phạm vi rất hẹp và thời gian ngắn |
| Điều khiển lọc | **OFF, ALL** | Tùy API/backend | Không phải mức sự kiện nghiệp vụ thông thường |

Bảng chỉ đối chiếu **ý nghĩa sử dụng**, không phải mapping kỹ thuật chính xác của mọi bridge. JUL còn có thứ tự ưu tiên theo số: **SEVERE(1000) > WARNING(900) > INFO(800) > CONFIG(700) > FINE(500) > FINER(400) > FINEST(300)**. Khi đặt Logger ở **Level.INFO**, các mức chuẩn **INFO, WARNING, SEVERE** vượt qua ngưỡng của Logger; các mức thấp hơn bị loại. Các bộ lọc tại Handler vẫn có thể quyết định kết quả cuối cùng.

### Một cấu hình khởi điểm thường gặp

| Đối tượng | Ngưỡng minh họa | Lý do |
| --- | --- | --- |
| Logger gốc của ứng dụng | **INFO** | Nhìn thấy sự kiện chính, lỗi và cảnh báo |
| Một dependency ghi quá nhiều log không hữu ích | **WARNING** | Giảm nhiễu, nhưng giữ bất thường đáng quan tâm |
| Class đang có lỗi khó tái hiện | **FINE/DEBUG** tạm thời | Mở rộng bằng chứng đúng chỗ |
| Thư viện/framework cấp thấp | **WARNING/INFO** tùy thư viện | Tránh đẩy chi tiết nội bộ vào log nghiệp vụ |
| Thành phần xử lý bí mật, dữ liệu nhạy cảm | Mức phù hợp **kèm redaction** | Chỉ đổi level không tự bảo vệ dữ liệu |
| Audit hoặc log bảo mật bắt buộc | Luồng/chính sách riêng | Không dựa hoàn toàn vào ngưỡng logger gốc để quyết định giữ hay bỏ |

**Đừng tắt toàn bộ INFO chỉ để giảm chi phí** nếu INFO chứa những sự kiện vận hành hoặc audit thiết yếu. Trước tiên nên giảm những log ít giá trị, thay đổi chính xác từng logger, dùng metric cho số liệu lặp lại và thiết kế retention phù hợp.

## 3. Ghi gì ở từng mức trong production?

### SEVERE / ERROR: thất bại có ảnh hưởng rõ ràng

Ví dụ: giao dịch không thể hoàn tất, không thể ghi dữ liệu bắt buộc, một chức năng thiết yếu ngừng hoạt động, một job quan trọng thất bại sau các bước khôi phục.

Một log lỗi nên cho biết **thao tác nào thất bại, ở đâu, vì sao, có tác động gì** và đính kèm exception khi cần. Tránh ghi cùng một exception ở nhiều tầng nếu nó chỉ đại diện cho một sự cố.

**Không phải mọi exception đều là ERROR**. Một lỗi nhập liệu từ người dùng hoặc kết quả “không tìm thấy” hợp lệ có thể là tình huống nghiệp vụ bình thường. Ngược lại, mất dữ liệu cần được chú ý ngay cả khi chỉ xảy ra một lần.

### WARNING / WARN: bất thường nhưng hệ thống vẫn có thể tiếp tục

Ví dụ: retry thành công sau timeout, dependency phản hồi chậm, cache fallback, cấu hình không tối ưu nhưng có đường chạy an toàn.

Nếu một cảnh báo lặp lại cho mỗi request ở tốc độ cao, nó có thể làm ngập log. Hãy điều chỉnh vị trí phát sự kiện, giới hạn tần suất hoặc dùng metric/cảnh báo tổng hợp; không nên âm thầm hạ mức mọi cảnh báo có ý nghĩa chỉ để giảm dung lượng.

### INFO: cột mốc cần quan sát thường xuyên

Ví dụ: phiên bản dịch vụ đã khởi động, batch hoàn thành, cấu hình vận hành quan trọng được chọn, giao dịch quan trọng đổi trạng thái sau khi được xử lý.

**Tránh biến INFO thành bản sao của toàn bộ luồng thực thi.** Với endpoint có lưu lượng lớn, ghi “bắt đầu xử lý” và “kết thúc xử lý” cho mọi request có thể tạo khối lượng rất lớn. Thường nên dùng access log, tracing hoặc metric chuyên biệt theo chuẩn của hệ thống.

### FINE / DEBUG: chi tiết phục vụ điều tra

Ví dụ: một nhánh nghiệp vụ được chọn, số lần retry, cache hit/miss, kết quả lựa chọn chiến lược, thời gian của bước nội bộ.

Đây là mức hữu ích khi tái hiện vấn đề khó, nhưng thường nên **tắt theo mặc định ở những class không cần theo dõi**, đặc biệt trong production có traffic lớn. Thông điệp DEBUG vẫn phải tuân thủ quy tắc bảo vệ dữ liệu; “không bật thường xuyên” không phải lý do để ghi secret.

### FINER/FINEST / TRACE: dấu vết rất sâu

Ví dụ: từng vòng lặp, từng bước parse, nhiều giá trị trung gian hoặc tương tác nội bộ rất nhỏ. Những thông điệp này có thể tạo ra lượng log lớn hơn cấp INFO nhiều bậc và làm biến đổi đặc tính hiệu năng khi bật.

Ưu tiên bật **TRACE/FINEST** trong môi trường thử nghiệm hoặc một instance, một package, một phiên chẩn đoán được kiểm soát. Nếu cần bật ở production, phải xác định phạm vi, thời hạn, người chịu trách nhiệm, giới hạn lưu lượng và cách phục hồi cấu hình.

## 4. Cơ chế lọc: vì sao bật DEBUG vẫn có thể không thấy dòng log?

Log level thường có nhiều tầng lọc. Với JUL:

1. **Logger** có mức hiệu lực (effective level). Bản ghi dưới ngưỡng này thường bị chặn ngay tại Logger.
2. **Filter** của Logger có thể từ chối bản ghi dù mức log đã đạt ngưỡng.
3. **Handler** nhận bản ghi theo tuyến cấu hình và có **ngưỡng/Filter riêng**.
4. **Formatter** quyết định hình thức dòng log; **nơi nhận** có thể là console, file hoặc collector.

Một ví dụ sai lầm điển hình:

~~~java
logger.setLevel(Level.FINE);
// ConsoleHandler van co level INFO.
logger.fine("Chi tiet dieu tra");
~~~

Dòng FINE có thể không xuất hiện vì Handler ở INFO. Muốn FINE qua được, **cả Logger và Handler nhận nó đều phải cho phép**. Trong JUL, logger con có thể truyền bản ghi tới Handler của logger cha (mặc định thường là có); riêng mức của logger cha không nhất thiết lọc lại bản ghi đã được logger con chấp nhận, nhưng Handler của cha vẫn có mức/filter của nó. Do đó phải kiểm tra cả tuyến Handler và thuộc tính **useParentHandlers**.

Một số điểm cần nhớ:

- **Level.INFO** chấp nhận INFO, WARNING và SEVERE ở JUL, trừ khi có Filter/Handler loại bỏ sau đó.
- **Level.WARNING** chấp nhận WARNING và SEVERE.
- **Level.FINE** mở rộng xuống FINE; không tự cho phép FINER/FINEST.
- **Level.ALL** cho phép các mức chuẩn tại ngưỡng đang xét; **Level.OFF** chặn chúng.
- Khi một Logger có **setLevel(null)**, nó kế thừa ngưỡng hiệu lực từ logger cha trong phân cấp logger JUL.
- Để nhìn thấy tên class/package, Formatter hoặc layout phải được cấu hình xuất **logger name**; chỉ khai báo logger theo class chưa đủ.

Trong SLF4J, API gọi **logger.debug(...)** hoặc **logger.trace(...)**; backend thực tế và appender/filter quyết định có xuất bản ghi hay không. Vì vậy không nên áp dụng tên **Level.FINE** trực tiếp cho code SLF4J.

## 5. Ví dụ Java 17 chạy độc lập: INFO mặc định, FINE theo class khi điều tra

Ví dụ này minh họa một chiến lược production phổ biến:

- Hai Logger có tên theo lớp: **app.orders.OrderService** và **app.payment.PaymentClient**.
- Ban đầu cả hai ở mức **INFO**.
- Khi điều tra sự cố thanh toán, tạm tăng riêng Logger của **PaymentClient** lên **FINE**.
- Sau khi điều tra, đưa Logger đó trở lại **INFO**; Logger đặt hàng vẫn không phát FINE.
- Một Handler tự định dạng ra **stdout** để kết quả chạy có thể kiểm chứng chính xác. Đây là mô phỏng trong một JVM, không phải hệ thống thay đổi level tập trung cho toàn bộ production.

Tạo tệp **ProductionLogLevelDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ProductionLogLevelDemo {
    private static final Logger ORDER =
            Logger.getLogger("app.orders.OrderService");

    private static final Logger PAYMENT =
            Logger.getLogger("app.payment.PaymentClient");

    public static void main(String[] args) {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                System.out.println(
                        record.getLoggerName()
                        + " | " + record.getLevel().getName()
                        + " | " + record.getMessage());
            }

            @Override
            public void flush() {
                // Demo in truc tiep, khong co buffer can flush.
            }

            @Override
            public void close() {
                // Demo khong so huu tai nguyen can dong.
            }
        };
        output.setLevel(Level.ALL);

        configure(ORDER, Level.INFO, output);
        configure(PAYMENT, Level.INFO, output);

        ORDER.info("Order request accepted");
        PAYMENT.fine("Initial payment details");
        PAYMENT.warning("Gateway response slow");

        System.out.println("--- Scoped diagnostics ---");
        PAYMENT.setLevel(Level.FINE);
        PAYMENT.fine("Gateway retries=2");
        ORDER.fine("Order internal validation");

        System.out.println("--- Restore baseline ---");
        PAYMENT.setLevel(Level.INFO);
        PAYMENT.fine("Hidden after restore");
        PAYMENT.info("Payment recovered");

        ORDER.removeHandler(output);
        PAYMENT.removeHandler(output);
        output.close();
    }

    private static void configure(Logger logger, Level level, Handler output) {
        logger.setUseParentHandlers(false);
        logger.setLevel(level);
        logger.addHandler(output);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ProductionLogLevelDemo.java
java ProductionLogLevelDemo
~~~

**Stdout chính xác:**

~~~text
app.orders.OrderService | INFO | Order request accepted
app.payment.PaymentClient | WARNING | Gateway response slow
--- Scoped diagnostics ---
app.payment.PaymentClient | FINE | Gateway retries=2
--- Restore baseline ---
app.payment.PaymentClient | INFO | Payment recovered
~~~

Giải thích:

1. Ở mức **INFO**, lời gọi **PAYMENT.fine("Initial payment details")** bị bỏ qua; bản ghi **WARNING** vẫn được xuất.
2. Khi đặt **PAYMENT.setLevel(Level.FINE)**, dòng FINE của PaymentClient xuất hiện.
3. **ORDER.fine("Order internal validation")** vẫn bị chặn vì ORDER giữ ngưỡng INFO.
4. Sau khi khôi phục PAYMENT về INFO, dòng FINE mới của PAYMENT lại bị chặn.
5. Handler của demo ở **Level.ALL** để không loại bản ghi mà Logger đã chấp nhận; **setUseParentHandlers(false)** tránh ghi trùng từ Handler của Logger cha.
6. Đầu ra dùng **System.out** có chủ đích; **ConsoleHandler** JUL mặc định xuất ra **stderr**. Khi triển khai thật, nên để cấu hình logging đảm trách Handler, định dạng và đích thu thập.

**Đây là ví dụ thay đổi level trong bộ nhớ của một tiến trình.** Nếu một dịch vụ có nhiều JVM hoặc pod, **setLevel(...)** tại một JVM không tự động áp dụng cho các JVM khác, cũng không tự tồn tại sau khi tiến trình khởi động lại. Cơ chế thay đổi mức động trong production phải có kiểm soát truy cập, phạm vi, thời hạn và cách đưa cấu hình về baseline.

## 6. Cấu hình JUL production bằng logging.properties

Trong hệ thống dùng **java.util.logging**, có thể cấu hình ngưỡng logger và Handler từ tệp properties. Ví dụ:

~~~properties
# logging.properties
handlers = java.util.logging.ConsoleHandler

# Muc mac dinh cua Logger goc
.level = INFO

# Handler phai chap nhan FINE neu muon mo FINE theo class
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Chi tiet cho class dang dieu tra
com.example.payment.PaymentClient.level = FINE

# Thu vien qua on: chi giu canh bao va loi
com.vendor.chatty.level = WARNING
~~~

Cấu hình này minh họa một ứng dụng mà Logger PaymentClient có tên **com.example.payment.PaymentClient**. Logger gốc ở INFO, nhưng Logger cụ thể được đặt FINE và ConsoleHandler cho phép FINE qua. Như vậy, log chi tiết có thể xuất hiện riêng ở logger đó. Cần dùng tên logger thực tế; một framework có thể đặt tên khác với package Java.

Có thể yêu cầu JVM nạp cấu hình JUL từ tệp khi khởi động:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Lệnh trên là **mẫu chạy ứng dụng đã biên dịch** có main class **com.example.Main**, không phải lệnh chạy demo **ProductionLogLevelDemo** ở phần 5. Khi dùng file cấu hình, ứng dụng cũng cần tránh chủ động ghi đè level/Handler trong mã ở các điểm khác, nếu không hành vi thực tế có thể khác dự kiến.

Trong dự án thực tế, không nên giữ FINE lâu dài chỉ vì một lần cần điều tra. Khi kết thúc, đổi lại:

~~~properties
com.example.payment.PaymentClient.level = INFO
~~~

Hoặc bỏ cấu hình riêng để lớp thừa kế ngưỡng từ Logger cha, khi thiết kế phân cấp tên logger đã được kiểm chứng. **Chỉ sửa tệp trên đĩa chưa chắc làm mức log trong JVM đang chạy đổi theo**; việc áp dụng động cần cơ chế reload hoặc hệ thống quản lý cấu hình có hỗ trợ rõ ràng. Nếu không có, thay đổi có thể chỉ có hiệu lực sau một lần khởi động lại theo quy trình vận hành.

## 7. Dùng Spring Boot/SLF4J trong production

Trong dự án dùng **Spring Boot** với cơ chế logging tương thích, có thể cấu hình mức theo package hoặc class bằng thuộc tính **logging.level**. Ví dụ **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=INFO
logging.level.com.example.payment.PaymentClient=DEBUG
logging.level.com.vendor.chatty=WARN
~~~

Trong trường hợp này:

- **root=INFO:** Baseline chung.
- **com.example.orders=INFO:** Giữ ngưỡng vận hành cho package đặt hàng.
- **PaymentClient=DEBUG:** Bật riêng phần chẩn đoán của client thanh toán.
- **com.vendor.chatty=WARN:** Giảm những dòng INFO không cần thiết của dependency cụ thể.

Đây là **mẫu cấu hình Spring Boot**, không phải cấu hình JUL thuần, và tên level **DEBUG/WARN** phù hợp với hệ logging được Spring Boot quản lý. Các library ghi JUL có thể cần bridge hoặc cấu hình thích hợp để hội tụ vào backend chung. Không nên trộn công thức cấu hình của JUL và backend khác mà không xác định rõ pipeline.

Trong một số phiên bản/cấu hình Spring Boot, **Actuator loggers endpoint** có thể hỗ trợ xem hoặc thay đổi level lúc runtime. Nếu dùng, phải chủ động bật và bảo vệ endpoint bằng xác thực, phân quyền, giới hạn mạng và audit; **không mặc định endpoint tồn tại hay được phép truy cập ở production**. Chi tiết kích hoạt phụ thuộc phiên bản ứng dụng và chính sách triển khai.

Cấu hình file phù hợp cho baseline lâu dài; cơ chế thay đổi runtime phù hợp với điều tra ngắn hạn có quản lý. Nếu level runtime bị thay đổi, cần có người chịu trách nhiệm, thời hạn hết hiệu lực, cách đồng bộ nhiều instance và cách trả về mức chuẩn.

## 8. Quy trình bật log chi tiết an toàn khi có sự cố production

Một tình huống: PaymentClient thỉnh thoảng báo timeout nhưng không tái hiện được ở staging. Việc cần làm không nhất thiết là bật DEBUG cho mọi dịch vụ.

**Bước 1 — Xác định câu hỏi điều tra.**

Ví dụ: timeout xảy ra trước khi gửi request, trong quá trình chờ kết nối hay sau lần retry thứ ba? Xác định những trường/sự kiện nào cần thêm để trả lời câu hỏi.

**Bước 2 — Xác định đúng logger.**

Tìm tên logger **com.example.payment.PaymentClient** hoặc một nhóm package thật sự liên quan. Nếu có nhiều JVM hoặc instance, xác định trường hợp đang lỗi và phạm vi thay đổi.

**Bước 3 — Đánh giá chi phí và dữ liệu có thể xuất.**

Ước tính số sự kiện/giây, kích thước log và độ nhạy cảm của payload. Đừng bật DEBUG nếu code có thể in toàn bộ authorization header, token hoặc dữ liệu thanh toán. Thay đổi logger để loại bỏ dữ liệu nhạy cảm phải được ưu tiên trước khi mở rộng mức ghi.

**Bước 4 — Bật mức đủ dùng trong thời gian giới hạn.**

Bắt đầu với **DEBUG/FINE**, chỉ chuyển sang **TRACE/FINER/FINEST** nếu cần. Ghi lại người thay đổi, thời điểm bắt đầu, logger cụ thể và thời hạn kết thúc. Với nhiều instance, bảo đảm cách điều chỉnh phù hợp với kiến trúc triển khai; tránh trạng thái chỉ một phần hệ thống được đổi mức mà nhóm điều tra không biết.

**Bước 5 — Quan sát tín hiệu và tác động.**

Theo dõi tỷ lệ lỗi, p95/p99 latency, CPU, I/O, khối lượng log/giây, độ trễ pipeline và dấu hiệu mất log. Nếu việc bật debug làm hệ thống suy giảm, dừng hoặc thu hẹp phạm vi.

**Bước 6 — Thu thập đủ bằng chứng, rồi phục hồi baseline.**

Tắt mức chi tiết khi đã trả lời câu hỏi hoặc hết thời hạn cho phép, ngay cả khi incident chưa kết thúc nếu logging gây tốn kém. Kiểm tra các instance đã trở về mức kỳ vọng.

**Bước 7 — Hoàn thiện khả năng quan sát lâu dài.**

Nếu sự cố lặp lại, cải thiện **sự kiện có cấu trúc**, metric, trace, kiểm thử và runbook. Không giữ DEBUG toàn hệ thống mãi mãi để bù cho hệ thống quan sát chưa đủ tốt.

## 9. Hiệu năng và chi phí liên quan tới level

### Chi phí không chỉ nằm ở số dòng được ghi

Khi một lời gọi log bị chặn theo level, hệ thống có thể tránh được nhiều bước xử lý bản ghi. Tuy nhiên, **biểu thức truyền vào lời gọi Java vẫn được đánh giá trước khi phương thức được gọi**, nếu chính lập trình viên đã tạo chuỗi hoặc gọi hàm tốn kém trước đó.

Ví dụ dễ gây lãng phí dù FINE đang tắt:

~~~java
logger.fine("Expensive state: " + generateLargeDebugReport());
~~~

Đoạn trên là **minh họa trong một class có logger và phương thức generateLargeDebugReport()**. Hàm tạo báo cáo được đánh giá trước khi lời gọi logger diễn ra.

Với JUL, có thể dùng **Supplier**:

~~~java
logger.log(
        Level.FINE,
        () -> "Expensive state: " + generateLargeDebugReport()
);
~~~

Hoặc kiểm tra trước khi thực hiện tính toán:

~~~java
if (logger.isLoggable(Level.FINE)) {
    String report = generateLargeDebugReport();
    logger.fine("Expensive state: " + report);
}
~~~

Các API trên giúp tránh tạo nội dung tốn kém khi Logger chặn mức FINE. Tuy nhiên, một Handler hoặc Filter vẫn có thể loại bản ghi về sau; thao tác kiểm tra **isLoggable** ở Logger không cam kết bản ghi cuối cùng sẽ được ghi ra đĩa.

Trong SLF4J, dùng placeholder **{}** thay cho việc nối chuỗi chủ động khi phù hợp:

~~~java
log.debug("Payment attempt={}, state={}", attempt, state);
~~~

Đoạn mã yêu cầu Logger SLF4J đã khai báo trong class. Truyền tham số theo API như vậy thường tránh tạo chuỗi định dạng khi mức DEBUG không bật. Nếu tự gọi hàm đắt tiền để tính tham số, hàm đó vẫn được đánh giá trước lời gọi, nên cần guard hoặc API lazy tương ứng.

### Ví dụ ước tính khối lượng

Giả sử có **1.000 yêu cầu/giây**. Việc bật thêm DEBUG tạo **3 dòng cho mỗi yêu cầu**, trung bình **500 byte mỗi dòng**:

~~~text
1.000 request/s × 3 log/request × 500 byte/log
= 1.500.000 byte/s
≈ 129,6 GB/ngày (đơn vị GB thập phân)
~~~

Đây mới là **dung lượng dữ liệu thô được tạo thêm** với giả định ổn định 24 giờ; chưa tính metadata, chỉ mục, sao chép, lưu trữ nhiều tầng hoặc chi phí truy vấn. Số liệu thực tế phụ thuộc traffic, kích thước bản ghi, nén, sampling và cách thu thập. Bởi vậy, bật debug trong vài phút cho một lớp khác rất nhiều so với bật trên mọi request trong nhiều ngày.

### Ghi log đồng bộ và bất đồng bộ

Một số backend hỗ trợ ghi bất đồng bộ để giảm thời gian chờ I/O trên luồng xử lý nghiệp vụ. Tuy nhiên, queue có thể đầy hoặc bị mất bản ghi khi JVM chết; chính sách xử lý backpressure và độ tin cậy phải được lựa chọn theo loại log.

Log vận hành chi tiết có thể áp dụng sampling hoặc giới hạn tốc độ, nhưng phải đánh giá riêng **log lỗi, bảo mật và audit**, bởi việc lấy mẫu sai có thể làm mất bằng chứng hoặc khiến thống kê tỷ lệ lỗi bị lệch. Thông tin số lượng phục vụ SLO thường nên lấy từ **metrics**, thay vì giả định log luôn đầy đủ.

## 10. Thiết kế log production dễ tìm và dễ vận hành

Ngoài level, một bản ghi production nên có ngữ cảnh nhất quán. Tùy hệ thống, những trường thường hữu ích gồm:

| Trường | Tác dụng |
| --- | --- |
| **timestamp** | Thời điểm xảy ra sự kiện, nên bao gồm múi giờ rõ ràng, thường dùng UTC |
| **level** | INFO/WARN/ERROR hoặc mức JUL tương ứng |
| **service / environment** | Xác định dịch vụ, production/staging |
| **logger_name** | Tên class/package phát sinh sự kiện |
| **event_code** | Mã sự kiện ổn định, không phụ thuộc câu chữ |
| **trace_id / request_id** | Liên kết sự kiện trong một yêu cầu |
| **operation / outcome** | Xác định thao tác và kết quả |
| **exception type / stack trace** | Chẩn đoán lỗi khi cần |
| **release / instance** | So sánh theo phiên bản và instance |

Ví dụ log có cấu trúc mang tính minh họa:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "production",
  "logger_name": "com.example.payment.PaymentClient",
  "event_code": "PAYMENT_PROVIDER_TIMEOUT",
  "trace_id": "trace-123",
  "operation": "authorize",
  "outcome": "failed",
  "message": "Payment provider timeout after retry"
}
~~~

Đây là **ví dụ JSON**, không phải định dạng mặc định của JUL. Để phát JSON, cần Formatter/encoder và cấu hình phù hợp. Các trường như trace_id nên được tạo và truyền theo cơ chế tracing/bối cảnh của dự án; chỉ bật thêm level không tự sinh ra chúng.

**Nguyên tắc dữ liệu:** chỉ thu thập thông tin cần thiết, hạn chế mã định danh có tính cá nhân, che hoặc loại bỏ bí mật trước khi ghi, đặt thời gian lưu và quyền truy cập phù hợp. Tránh ghi full request/response cho mọi yêu cầu ngay cả ở DEBUG. Một khi bí mật đã đi vào pipeline log, việc xóa sạch tất cả bản sao có thể khó hơn sửa mã ứng dụng.

## 11. Level và monitoring/alerting có quan hệ gì?

**Log level là một cơ chế lọc; alert là một quyết định vận hành.** Không nên thiết kế cơ chế trực pager chỉ dựa trên việc “cứ thấy ERROR là gửi thông báo”.

Một dịch vụ có thể phát nhiều WARN trong lúc retry thành công, nhưng không có ảnh hưởng tới người dùng. Ngược lại, số lượng INFO đột nhiên biến mất có thể phản ánh job không còn chạy. Để cảnh báo đáng tin cậy, nên dựa vào tác động rõ ràng như **tỷ lệ lỗi, độ trễ, tỉ lệ tác vụ thành công, heartbeat hoặc sự kiện nghiệp vụ xác thực**, kết hợp log để tìm nguyên nhân.

Ví dụ cách phân loại:

| Tình huống | Cách log | Cách phát hiện sự cố phù hợp |
| --- | --- | --- |
| Gọi dependency thất bại sau tất cả retry | ERROR/SEVERE và exception liên quan | Tỷ lệ request thất bại, SLO, circuit breaker |
| Retry lần đầu nhưng lần kế thành công | WARN hoặc DEBUG theo quy ước | Metric retry và latency tăng |
| Job ban đêm không chạy | Có thể không có bản ghi lỗi | Job heartbeat, lịch chạy, giới hạn thời gian |
| Đăng nhập bị từ chối do sai mật khẩu | Log an toàn theo chính sách bảo mật | Phân tích tần suất, mẫu hành vi và bảo vệ tài khoản |
| Bật DEBUG một class để điều tra | DEBUG/FINE tạm thời | Theo dõi chi phí và thời hạn bật diagnostic |

Nếu thay đổi ngưỡng từ INFO lên WARNING, những event INFO từng được dùng trong dashboard hoặc cảnh báo có thể biến mất. Trước khi giảm level, cần rà soát **những truy vấn, alert và audit thực sự phụ thuộc vào log đó**. Cách tốt hơn có thể là giữ event quan trọng, loại các log ít giá trị và tạo metric chuyên trách.

## 12. Những lỗi thường gặp

1. **Bật DEBUG/TRACE cho toàn bộ production lâu dài.** Tạo nhiễu, tăng chi phí và có thể làm lộ nhiều dữ liệu hơn cần thiết.
2. **Hạ tất cả logger thành ERROR vì tiết kiệm.** Mất sự kiện vận hành hữu ích, đôi khi làm dashboard hoặc cảnh báo không còn dữ liệu.
3. **Nhầm ngưỡng Logger với ngưỡng Handler/appender.** Logger đã ở FINE nhưng đích xuất vẫn có thể chặn FINE.
4. **Không đặt thời hạn cho thay đổi runtime.** Một lần điều tra tạm thời trở thành cấu hình tốn kém kéo dài nhiều tuần.
5. **Chỉ đổi một instance mà không biết hệ thống có nhiều instance.** Dữ liệu trở nên không nhất quán và nhóm điều tra có thể kết luận sai.
6. **Không kiểm soát dữ liệu nhạy cảm ở DEBUG.** Log tạm thời cũng có thể bị tập trung và lưu lâu.
7. **Nối chuỗi hoặc tạo payload đắt tiền trước lời gọi log.** Dù level tắt, CPU vẫn có thể phải xử lý dữ liệu.
8. **Ghi cùng ngoại lệ ở mọi tầng.** Gây lặp bản ghi và phóng đại số sự kiện lỗi.
9. **Đồng nhất ERROR với paging.** Tạo quá nhiều cảnh báo giả; cần đánh giá tác động thực tế.
10. **Đổi tên logger khi refactor mà quên cấu hình.** Các quy tắc theo class/package cũ có thể mất hiệu lực.
11. **Chỉ dựa vào không có log lỗi để kết luận hệ thống khỏe.** Một tiến trình chết hoặc pipeline log hỏng có thể không phát thêm sự kiện.
12. **Dùng log thay cho metric hoặc trace.** Các loại dữ liệu quan sát bổ sung cho nhau và có chức năng khác nhau.

## 13. Checklist khi áp dụng log level ở production

Trước khi triển khai:

- Xác định **API và backend logging** đang dùng: JUL, SLF4J + Logback, Log4j 2 hoặc bridge.
- Chọn baseline theo ứng dụng, thường bắt đầu từ **INFO**, rồi điều chỉnh theo quan sát thực tế.
- Dùng **logger name** nhất quán theo class/package để điều chỉnh phạm vi nhỏ.
- Đảm bảo **Logger, Handler/appender, Filter và collector** có cấu hình nhất quán.
- Phân biệt **sự kiện nghiệp vụ quan trọng**, lỗi thực sự, bất thường có phục hồi và dấu vết chẩn đoán.
- Bảo vệ **secret/PII**, có retention và phân quyền truy cập.
- Thiết lập **metric/alert** phù hợp để không lệ thuộc vào số dòng log.
- Có quy trình **bật mức chi tiết tạm thời**, thời hạn, người phê duyệt theo chính sách, và cách khôi phục.
- Theo dõi **log volume, chi phí, throughput, latency** khi thay đổi level.
- Kiểm tra dashboard và quy tắc cảnh báo sau khi thay đổi mức log.

## 14. Câu hỏi tự kiểm tra

1. **Production có bắt buộc phải đặt mức WARN không?** Không. INFO là điểm khởi đầu phổ biến; mức cuối cùng phụ thuộc nhu cầu quan sát, độ nhiễu, chi phí và cấu hình cụ thể.
2. **Bật FINE cho PaymentClient có đồng nghĩa mọi FINE đều xuất hiện không?** Không. Handler, Filter và tuyến truyền bản ghi vẫn có thể loại chúng.
3. **DEBUG có tự động an toàn vì chỉ bật trong vài phút không?** Không. Dữ liệu nhạy cảm có thể được thu thập và lưu lại.
4. **setLevel(Level.FINE) trên một JVM có thay đổi các JVM khác không?** Không; cần cơ chế quản lý cấu hình tập trung hoặc thao tác riêng theo thiết kế triển khai.
5. **Một hệ thống có 1.000 request/giây bật thêm 3 log × 500 byte mỗi request sẽ tạo bao nhiêu dữ liệu?** Khoảng 1,5 MB/giây, tương đương 129,6 GB/ngày dữ liệu thô nếu tải giữ nguyên.
6. **Khi DEBUG được tắt, hàm generateLargeDebugReport() trong phép nối chuỗi trước lời gọi logger có chạy không?** Có; hãy dùng Supplier hoặc kiểm tra isLoggable trong JUL.
7. **Một ERROR có nhất thiết là một alert khẩn cấp không?** Không. Alert phải dựa trên tác động, mức độ khẩn và khả năng hành động.

**Ghi nhớ:** Quản lý level ở production không chỉ là chọn INFO hay WARN. Cần giữ những sự kiện có giá trị vận hành, tránh ghi dữ liệu thừa hoặc nhạy cảm, hiểu tất cả tầng lọc, và có cơ chế bật log chi tiết theo đúng class trong khoảng thời gian giới hạn. Khi kết thúc điều tra, hãy đưa ngưỡng về cấu hình chuẩn và tiếp tục dùng metric, trace cùng log để quan sát hệ thống.
