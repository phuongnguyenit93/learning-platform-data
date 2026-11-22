# Level ở môi trường phát triển — Java Core Logging

## Mục tiêu và phạm vi

Khi phát triển ứng dụng Java, log cần cho biết luồng xử lý đã đi qua đâu, quyết định nào được chọn, lỗi xảy ra tại bước nào và kết quả cuối cùng của thao tác. Level cho phép điều khiển độ chi tiết của những bản ghi này mà không sửa từng câu lệnh log mỗi khi điều tra lỗi.

Sau bài học, bạn có thể chọn level hợp lý trong môi trường phát triển; hiểu vì sao logger và handler đều ảnh hưởng đến việc hiển thị log; bật thông tin debug cho đúng package hoặc lớp; chạy chương trình Java 17+ để so sánh INFO với FINE; và kiểm soát bảo mật, hiệu năng khi tăng độ chi tiết.

Bài thuộc nhóm **Log level**, tập trung vào **level ở môi trường phát triển**. Ví dụ chính sử dụng API có sẵn trong JDK là **java.util.logging (JUL)**. Các framework khác như SLF4J cùng Logback hoặc Log4j 2 được nhắc đến để tránh nhầm cách đặt level.

## 1. Level phát huy tác dụng gì khi đang phát triển?

Một luồng xử lý đơn hàng có thể gồm nhiều bước: nhận request, kiểm tra giỏ hàng, kiểm tra cache, chọn quy tắc giảm giá, gọi dependency, retry rồi trả kết quả. Khi chỉ cần xác nhận nghiệp vụ hoàn thành, bạn thường không cần nhìn từng bước. Khi có lỗi tính giá, chính những bước trung gian đó lại quan trọng.

Ví dụ tình huống:

~~~text
INFO    event=checkout.started requestId=req-17
FINE    event=cart.checked requestId=req-17 items=3
FINE    event=discount.rule_selected requestId=req-17 rule=WELCOME
FINEST  event=discount.expression_step requestId=req-17 index=4
WARNING event=inventory.retry requestId=req-17 attempt=2
INFO    event=checkout.completed requestId=req-17 status=200
~~~

Đây là chuỗi minh họa, không phải đầu ra của chương trình thực hành bên dưới. Ở ngưỡng INFO, lập trình viên thấy yêu cầu bắt đầu, một lần retry và kết quả cuối. Ở FINE, hai dòng giải thích quyết định nội bộ được hiển thị thêm. Ở FINEST, hệ thống có thể phát rất nhiều thông tin chi tiết theo từng bước, chỉ hữu ích khi đang tái hiện một lỗi hẹp.

**Level không thay đổi nghiệp vụ của ứng dụng.** Thay đổi ngưỡng chỉ thay đổi record được chấp nhận và xuất ra. Một WARNING có thể là lần retry đã phục hồi; request trong ví dụ vẫn thành công với status=200. Ngược lại, một lời gọi log ở INFO không nhất thiết cho thấy hệ thống khỏe mạnh; phải xem nội dung và kết quả thực tế.

Với development, câu hỏi tốt không phải “làm sao in mọi thứ?” mà là “cần những record nào để phân biệt hai giả thuyết?”. Tăng độ chi tiết cho đúng điểm giúp đỡ tốn thời gian tìm kiếm và không ngập console.

## 2. Thứ tự log level trong JUL

Trong **java.util.logging**, thứ tự mức nghiêm trọng/chi tiết thường nhìn từ trên xuống như sau:

| Level JUL | Ý nghĩa điển hình | Sử dụng khi phát triển |
| --- | --- | --- |
| SEVERE | Lỗi nặng khiến thao tác hoặc thành phần không thể hoàn thành đúng | Lỗi mất chức năng, kèm exception và ngữ cảnh có thể điều tra |
| WARNING | Bất thường đáng quan tâm; có thể vẫn phục hồi | Retry bất thường, fallback, đầu vào không mong đợi tùy tác động |
| INFO | Mốc nghiệp vụ hoặc vận hành hữu ích | Bắt đầu/kết thúc thao tác, kết quả request, job completed |
| CONFIG | Chi tiết cấu hình vận hành | Kiểm tra profile hoặc tùy chọn không nhạy cảm |
| FINE | Thông tin debug cơ bản | Cache hit/miss, rule được chọn, nhánh xử lý |
| FINER | Chi tiết sâu hơn | Thay đổi trạng thái trung gian khi đang chẩn đoán |
| FINEST | Rất chi tiết, thường tần suất cao | Từng bước bên trong thuật toán hoặc parser trong thời gian ngắn |

JUL còn có **OFF** để tắt logging theo ngưỡng và **ALL** để cho phép mọi level qua ngưỡng tương ứng. Hai giá trị này không phải loại sự kiện nghiệp vụ. Một level có giá trị số; một record bị loại bởi phép kiểm tra ngưỡng nếu level thấp hơn ngưỡng đang có hiệu lực. Không nên tự so sánh level dựa trên thứ tự chữ cái trong tên.

Ví dụ với một logger đơn lẻ, **ngưỡng INFO** cho phép INFO, WARNING, SEVERE nhưng loại CONFIG, FINE, FINER, FINEST. **Ngưỡng FINE** cho phép thêm CONFIG và FINE; FINER và FINEST vẫn bị loại. **Ngưỡng FINEST** cho phép cả các mức chi tiết nhất. Còn filter, handler hoặc tuyến xuất log vẫn có thể quyết định không xuất một record đã qua ngưỡng logger.

Ở các framework khác, bạn thường gặp ERROR, WARN, INFO, DEBUG, TRACE. Về mục tiêu sử dụng, JUL FINE thường gần với DEBUG, FINER/FINEST thường gần với TRACE. Đó chỉ là cách **đối chiếu ý nghĩa**, không phải ánh xạ API, giá trị số hoặc hành vi đảm bảo tương đương. Muốn chỉnh đúng level phải biết ứng dụng thực sự đang phát qua JUL hay backend nào.

## 3. Chọn level cho từng loại tình huống development

| Tình huống | Ví dụ record | Level gợi ý |
| --- | --- | --- |
| Ứng dụng đã sẵn sàng xử lý request | event=app.ready port=8080 | INFO |
| Một batch chạy xong | event=batch.completed processed=120 durationMs=85 | INFO |
| Một request kết thúc với kết quả đo được | event=request.completed requestId=req-17 status=200 | INFO |
| Chọn rule tính giá | event=pricing.rule_selected rule=WELCOME requestId=req-17 | FINE |
| Kiểm tra cache để giải thích quyết định | event=cache.lookup result=miss requestId=req-17 | FINE |
| Theo từng bước parser khó chẩn đoán | event=parser.transition state=HEADER index=12 | FINER hoặc FINEST |
| Retry sau timeout có tác động đáng chú ý | event=payment.retry attempt=2 reason=timeout | WARNING hoặc FINE tùy kỳ vọng |
| Dependency không thể phục vụ request | event=inventory.unavailable requestId=req-17 | SEVERE khi tác động thực sự nghiêm trọng |
| Người dùng nhập dữ liệu sai theo nhánh dự kiến | event=validation.rejected field=quantity | FINE/INFO hoặc không log nếu quá thường xuyên |

Các giá trị level trong bảng là ví dụ theo **tác động và kỳ vọng vận hành**. Không có quy tắc “hễ catch exception là SEVERE”. Ngoại lệ đã được xử lý như một tình huống nghiệp vụ thông thường có thể không cần cảnh báo. Ngược lại, lỗi cấu hình làm ứng dụng không khởi động phải được báo rõ ở mức đủ cao.

Thông điệp tốt nên có **hành động + kết quả + định danh + ngữ cảnh đủ dùng**. Dùng event name ổn định, requestId/traceId phù hợp, mã nguyên nhân an toàn và số đo có đơn vị như durationMs. Tránh các dòng “step1”, “here”, “debug” vì khó đọc khi có nhiều request chạy đồng thời.

## 4. Chiến lược bật level trong development

**Mặc định bắt đầu từ INFO.** Những record quan trọng giúp kiểm tra ứng dụng đang hoạt động, hiểu kết quả cuối và nhận biết bất thường có thể được giữ ở INFO/WARNING/SEVERE. Không ghi mọi phép gán, mọi vòng lặp, mọi dữ liệu đầu vào ở mức INFO.

**Khi phát hiện một vấn đề, bật FINE cho phạm vi nhỏ.** Nếu đang debug phần pricing, tăng mức chi tiết của logger/package pricing và những dependency trực tiếp liên quan. Chọn vài điểm log giúp phân biệt các nhánh logic: giá trị cache, rule đã chọn, kết quả xử lý. Tiếp tục lọc bằng requestId để đọc một luồng xử lý.

**Chỉ dùng FINER/FINEST khi FINE chưa đủ.** Các mức này có thể sinh rất nhiều record. Bật theo package/lớp có vấn đề, tái hiện một ca có kiểm soát và dừng ngay khi có bằng chứng. Việc bật FINEST cho toàn bộ thư viện mạng, database và JDK thường khiến các dòng quan trọng bị chìm.

**Sau khi khắc phục, trả cấu hình về baseline.** Nếu một thông điệp giúp bảo trì lâu dài thì giữ nó ở level thích hợp; nếu chỉ là thông tin thử nghiệm quá chi tiết thì loại bỏ. Không để cấu hình debug toàn hệ thống vô thời hạn. Đừng giả định mọi log local là riêng tư: output terminal, IDE, CI hoặc issue đính kèm vẫn có thể được lưu và chia sẻ.

Trong phát triển nhiều service, bật log có chọn lọc trên **service/package có liên quan** và tìm theo traceId/requestId thường hữu ích hơn thay đổi toàn bộ hệ thống. Những dòng có timestamp gần nhau trên nhiều máy không nhất thiết thuộc cùng một request hoặc theo đúng thứ tự nhân quả.

## 5. Hai lớp lọc: Logger và Handler

Với JUL, một lời gọi log có thể bị loại ngay ở **Logger**, hoặc được logger chấp nhận nhưng bị **Handler** loại trước khi hiển thị.

- **Logger level:** Nếu logger được đặt FINE, bản ghi FINE có thể được chấp nhận. Nếu logger đặt INFO, FINE bị loại trước khi tới handler. Logger có thể kế thừa ngưỡng từ parent khi level của nó là null.
- **Handler level:** ConsoleHandler, FileHandler hoặc handler tùy chỉnh có ngưỡng riêng. Một handler ở INFO không xuất FINE dù logger ở FINE.
- **Filter:** Logger hoặc handler có thể áp bộ lọc bổ sung. Level phù hợp chưa bảo đảm record được xuất.
- **Parent handlers:** JUL có thể chuyển record tới handler của parent logger. Nếu nhiều handler cùng nhận, một record có thể xuất nhiều lần; nếu xem nhầm đích xuất, ta lại tưởng thiếu record.
- **Formatter:** Quyết định các trường và dạng văn bản được hiển thị; một record có thể chứa thông tin nhưng formatter không xuất trường đó.
- **Destination:** ConsoleHandler thông thường ghi stderr. IDE, test runner hoặc môi trường container có thể hiển thị stderr và stdout khác nhau.

| Effective level của Logger | Level của Handler | Dòng FINE tới handler này? |
| --- | --- | --- |
| INFO | FINE | Không, logger loại |
| FINE | INFO | Không, handler loại |
| FINE | FINE | Có nếu không bị filter hoặc lỗi xuất |
| FINEST | FINE | Có |
| OFF | ALL | Không, logger đã tắt |

Điểm quan trọng khi debug: **cấu hình logger FINE không đồng nghĩa console cũng đang hiển thị FINE**. Đặc biệt, ConsoleHandler có thể vẫn đang sử dụng ngưỡng INFO. Khi cần quan sát chi tiết, kiểm tra ngưỡng thực tế ở cả hai nơi và xem có framework nào thay thế handler hay cấu hình JUL không.

Một câu lệnh minh họa (đòi hỏi biến logger đã có sẵn) là:

~~~java
logger.fine("event=pricing.rule_selected rule=WELCOME");
~~~

Nếu logger ở FINE nhưng ConsoleHandler ở INFO, dòng này vẫn bị loại tại handler. Nếu đặt handler FINE nhưng logger kế thừa INFO, dòng cũng bị loại ngay khi gọi logger.

## 6. Chương trình Java 17+ so sánh hai mức quan sát

Ví dụ sử dụng **java.util.logging**, không cần dependency bên ngoài JDK. Cùng một luồng xử lý mô phỏng, ứng dụng phát năm lời gọi log. Một system property tự định nghĩa là **app.env** quyết định dùng INFO hay FINE.

Tạo tệp **DevLogLevelDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DevLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(DevLogLevelDemo.class.getName());

    public static void main(String[] args) {
        boolean development = "dev".equals(System.getProperty("app.env"));
        Level selected = development ? Level.FINE : Level.INFO;

        // Dùng một handler trong demo để tránh output trùng.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(selected);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(selected);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.info("event=request.started requestId=req-17");
            LOG.fine("event=cache.lookup requestId=req-17 result=miss");
            LOG.log(Level.FINE, () ->
                    "event=route.selected requestId=req-17 branch=fallback");
            LOG.warning("event=dependency.retry requestId=req-17 attempt=2");
            LOG.info("event=request.completed requestId=req-17 status=200");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

### Lần chạy 1: mặc định INFO

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac DevLogLevelDemo.java
java DevLogLevelDemo
~~~

**Output chính xác do ConsoleHandler ghi vào stderr** là:

~~~text
INFO | event=request.started requestId=req-17
WARNING | event=dependency.retry requestId=req-17 attempt=2
INFO | event=request.completed requestId=req-17 status=200
~~~

Các dòng FINE không xuất ra vì cả logger và handler được đặt ngưỡng INFO. Chúng vẫn là những lời gọi logging được thực hiện trong code; thông tin chi tiết của chúng chỉ không được đưa ra đích.

### Lần chạy 2: bật mức FINE cho development

Chạy:

~~~bash
java -Dapp.env=dev DevLogLevelDemo
~~~

**Output chính xác trên stderr**:

~~~text
INFO | event=request.started requestId=req-17
FINE | event=cache.lookup requestId=req-17 result=miss
FINE | event=route.selected requestId=req-17 branch=fallback
WARNING | event=dependency.retry requestId=req-17 attempt=2
INFO | event=request.completed requestId=req-17 status=200
~~~

Ngưỡng FINE làm hiện thêm thông tin cache miss và chọn nhánh fallback. Hai lần chạy vẫn cùng kết quả nghiệp vụ: request kết thúc status=200. Một WARNING xuất hiện ở cả hai chế độ và chỉ nói về một lần retry, không chứng minh yêu cầu đã thất bại.

### Giải thích từng thành phần

1. **System.getProperty("app.env")** đọc một property JVM do bài thực hành tự đặt. Tùy chọn -Dapp.env=dev nằm trước tên lớp trong lệnh java. Đây không phải property cấu hình logging mặc định của JUL.
2. **LOG.setLevel(selected)** đặt ngưỡng tại logger để cho phép INFO hoặc FINE.
3. **handler.setLevel(selected)** đặt ngưỡng tại ConsoleHandler. Nếu chỉ thay logger mà handler vẫn INFO, hai dòng FINE không hiện.
4. **LOG.setUseParentHandlers(false)** tránh bản ghi được chuyển tới handler của root logger và có khả năng hiển thị trùng trong demo.
5. **Formatter** ở đây chỉ in level và message, bỏ timestamp/logger name/stack trace để kết quả được xác định chính xác. Formatter thật cần cân nhắc những metadata đó khi điều tra lỗi.
6. **LOG.log(Level.FINE, () -> ...)** dùng Supplier<String> để trì hoãn tạo message; nếu logger lọc FINE, Supplier có thể không được gọi. Không đặt tác dụng phụ nghiệp vụ trong Supplier.
7. **LOG.removeHandler(handler)** và **handler.close()** giải phóng handler sau khi kết thúc demo. Ứng dụng thực thường khởi tạo và quản lý handler theo vòng đời ứng dụng, không tạo handler mới cho từng request.

JUL ConsoleHandler ghi **stderr**, trong khi System.out.println ghi stdout. Việc terminal trộn hai luồng không làm chúng trở thành một. Nếu môi trường làm việc chỉ thu stdout, cần kiểm tra cách cấu hình hoặc thu stderr.

## 7. Cấu hình mức chi tiết bên ngoài code

Trong dự án thực, phát log qua logger nhưng thường nên cấu hình level theo **environment/profile** để đổi mức quan sát mà không sửa logic. Đoạn code thực hành trực tiếp gọi setLevel chỉ để minh họa; các cấu hình bên ngoài bên dưới áp dụng cho ứng dụng sử dụng cơ chế tương ứng và không lập tức ghi đè cấu hình bằng code.

### Ví dụ file JUL logging-dev.properties

~~~properties
# Root logger ở INFO.
.level = INFO

# Chỉ định handler cho root; handler nhận được FINE.
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Tăng độ chi tiết cho package cần điều tra.
com.example.checkout.level = FINE
~~~

Khi ứng dụng phù hợp có lớp chính com.example.Main và classpath được đặt trong thư mục out, có thể chạy:

~~~bash
java -Djava.util.logging.config.file=logging-dev.properties -cp out com.example.Main
~~~

File phải tồn tại ở đường dẫn mà JVM truy cập được. Trong ví dụ, root ở INFO; package checkout được đặt FINE; handler root phải đủ chi tiết để không loại dòng FINE từ logger checkout. Các logger khác vẫn có thể chịu ảnh hưởng ngưỡng INFO của root nếu không có cấu hình riêng.

**Đây không phải lệnh chạy DevLogLevelDemo ở mục 6.** Chương trình đó tự tạo ConsoleHandler và setLevel trong code, nên không dùng để minh họa việc cấu hình ngoài hoạt động một cách độc lập. Khi dùng SimpleFormatter mặc định của JUL, định dạng và timestamp cũng sẽ khác output custom formatter phía trên.

### Ví dụ framework như Spring Boot

Với hệ logging do Spring Boot cấu hình, một đoạn YAML minh họa là:

~~~yaml
logging:
  level:
    root: INFO
    com.example.checkout: DEBUG
~~~

Ý nghĩa là giữ root ở INFO nhưng mở DEBUG cho package checkout. Đó là **cú pháp của Spring Boot**, không phải của JUL logging.properties. Tên level trong SLF4J/Logback/Log4j 2 có thể khác JUL. Khi ứng dụng dùng facade và backend riêng, việc chỉnh ConsoleHandler JUL có thể không tác động đến logger đang phát qua backend ấy.

Các yếu tố thường cần kiểm tra: profile development đang bật, file cấu hình đang được tải, tên package có khớp logger name, level bị ghi đè từ môi trường hoặc tham số dòng lệnh, và có code gọi setLevel sau khi hệ thống đọc cấu hình hay không.

### Quy ước cấu hình theo môi trường

Trong local, bạn có thể bật FINE/DEBUG cho một thành phần cụ thể để tái hiện lỗi. Trong môi trường test, chọn độ chi tiết phù hợp để tìm lỗi khi test fail, nhưng tránh tạo log dài vô ích. Môi trường staging và production thường cần baseline vận hành nhất quán, quan sát bằng INFO/WARNING/SEVERE và cơ chế chủ động bật debug có kiểm soát khi cần. Cụ thể chọn level nào phải dựa trên tải, dung lượng, bảo mật và quy ước của sản phẩm.

## 8. Khi không thấy FINE hoặc DEBUG: kiểm tra theo thứ tự

**Bước 1 — Xác minh đường code.** Đặt breakpoint hoặc kiểm tra điều kiện gọi để chắc nhánh đang xét thực sự chạy. Không thấy log không đủ chứng minh code chưa chạy.

**Bước 2 — Xác nhận logger name.** Kiểm tra tên lớp/package hoặc tên logger đặt thủ công. Ngưỡng FINE trên một logger khác không ảnh hưởng mọi logger trong JVM.

**Bước 3 — Kiểm tra effective level.** Logger có level FINE hay đang kế thừa INFO từ parent? Trong JUL, level null nghĩa là kế thừa; đừng nhầm với ALL.

**Bước 4 — Kiểm tra handler/appender.** ConsoleHandler/FileHandler có thể đang INFO hoặc có filter riêng. Một handler khác có thể nhận FINE vào file trong khi console không hiển thị.

**Bước 5 — Kiểm tra propagation.** Các handler của parent có thể xuất trùng hoặc xuất theo format khác nếu useParentHandlers được bật. Đừng sửa cấu hình toàn bộ root chỉ vì thấy một dòng bị trùng.

**Bước 6 — Kiểm tra backend thực tế.** SLF4J facade + Logback không được điều khiển đơn giản bởi JUL ConsoleHandler; cần tìm ứng dụng đang dùng adapter/backend nào.

**Bước 7 — Kiểm tra cấu hình có hiệu lực.** Profile đúng chưa, file có được load không, system property đặt đúng vị trí chưa, có override sau khi khởi động không?

**Bước 8 — Kiểm tra nơi xuất và người đọc.** ConsoleHandler thường ở stderr. CI, container, test runner, IDE, backend thu thập có thể tách luồng hoặc áp parser/filter khác.

**Bước 9 — Kiểm tra độ trễ và dữ liệu thiếu.** Với log qua collector, có thể có batching, sampling, ingest delay, retention hoặc record bị loại. Không suy ra event không xảy ra chỉ vì chưa tìm thấy record.

Khi chẩn đoán, xác định chính xác **record bị loại ở tầng nào** rồi mới tăng mức log ở tầng đó. Nếu tăng ALL cho toàn bộ ứng dụng, log có thể đầy lên nhưng vẫn không giải quyết vấn đề xem sai service, sai class, sai file hoặc sai requestId.

## 9. Chi phí và bảo mật khi bật log chi tiết

**Không ghi dữ liệu nhạy cảm dù là FINEST trên máy phát triển.** Tránh mật khẩu, session cookie, access token, refresh token, API key, mã OTP, thông tin thanh toán, payload chứa dữ liệu cá nhân hoặc cấu hình có credentials. Dữ liệu được in trong exception message, URL hoặc toString() cũng có thể lộ thông tin. Khi cần liên kết, dùng định danh được phép theo chính sách; không mặc định mọi ID đều an toàn để xuất log.

**Đầu vào không tin cậy có thể gây log injection.** Chuỗi nhận từ người dùng có newline và ký tự điều khiển có thể giả mạo một record mới khi ghép thẳng vào text log. Sử dụng escaping, structured logging, giới hạn kích thước và lọc dữ liệu phù hợp.

**Không dựng message đắt đỏ khi level đang bị loại.** Với JUL, Supplier giúp trì hoãn công việc tạo message:

~~~java
// Đoạn mã minh họa; đã khai báo logger và hàm expensiveSummary().
logger.log(java.util.logging.Level.FINE,
        () -> "event=state.snapshot details=" + expensiveSummary());
~~~

Bạn cũng có thể dùng kiểm tra isLoggable khi chuẩn bị dữ liệu tốn chi phí. Supplier không được gọi khi logger đã loại level, nhưng **handler/filter vẫn có thể loại record về sau**; không dựa vào logging để thực thi side effect nghiệp vụ.

Không ghi toàn bộ object hoặc giá trị ở mỗi vòng lặp trong đường xử lý nóng. Khi record thực sự được xuất, serialization, format, disk I/O, buffering và shipping đều có thể làm ứng dụng chậm đi. Với lỗi liên quan timing, bật nhiều log thậm chí có thể thay đổi hành vi race condition. Dùng metrics để theo dõi số đếm/latency tổng hợp và traces để theo đường đi request; logs nên giữ thông tin diễn giải sự kiện hoặc quyết định.

## 10. Các lỗi phổ biến và hướng khắc phục

| Lỗi thường gặp | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Bật ALL/FINEST toàn JVM trong nhiều ngày | Log nhiễu và tăng I/O | Bật FINE/DEBUG cho package liên quan trong thời gian cần thiết |
| Đặt logger FINE, handler INFO | Không thấy dòng FINE | Kiểm tra cả logger và handler |
| Coi WARNING là request thất bại | Kết luận sai khi retry phục hồi | Xem outcome cuối và requestId |
| Log “here1”, “here2” | Không biết sự kiện và luồng nào | Dùng tên event, branch, requestId và kết quả |
| Ghi INFO cho mọi phép gán | Khó tìm mốc quan trọng | Đưa debug nội bộ về FINE/FINER |
| Nhầm Logback DEBUG với JUL FINE | Chỉnh sai cấu hình | Xác định facade, backend và profile |
| Chỉ nối ex.getMessage() | Mất loại Throwable/cause/stack trace | Ghi Throwable bằng overload phù hợp khi cần |
| Log cùng exception ở nhiều tầng | Thống kê lỗi bị phóng đại | Đặt điểm log chịu trách nhiệm với ngữ cảnh đủ dùng |
| Log thành công trước commit | Bản ghi không phản ánh kết quả cuối | Ghi sau khi xác nhận kết quả hoặc đặt tên event chính xác |
| Dùng System.out.println mọi nơi | Thiếu level, logger và cơ chế quản lý | Dùng logging API thống nhất trong dự án |
| Ghi raw request hoặc secret để debug nhanh | Rủi ro lộ dữ liệu | Ghi field tối thiểu, an toàn, đã che |
| Quên hạ level sau điều tra | Log tiếp tục phình và gây nhiễu | Khôi phục cấu hình development trước khi kết thúc |

Khi dùng Throwable, hãy phân biệt ngoại lệ đã được bắt và xử lý hợp lệ với lỗi làm gián đoạn chức năng. Một stack trace nói về vị trí ném lỗi; message có ngữ cảnh giúp hiểu **thao tác nào thất bại và thực thể nào bị ảnh hưởng**. Không tự gán level chỉ dựa trên tên exception.

## 11. Quy trình thực hành khi debug một chức năng

Ví dụ cần điều tra sai giá vì có thể chọn nhầm nhánh fallback:

1. **Tạo ca tái hiện** với dữ liệu giả hoặc đã xử lý bảo mật, ghi nhận đầu vào và requestId.
2. **Đặt giả thuyết**: giá sai do cache miss hay do rule lựa chọn? Cần log ở cả hai quyết định.
3. **Giữ mốc INFO** cho bắt đầu và kết quả cuối của request; dùng FINE ở các chỗ cache.lookup và pricing.rule_selected.
4. **Bật FINE đúng package** ở cả logger và handler/backend đang xuất log; tránh tăng chi tiết của mọi thư viện.
5. **Chạy lại và lọc requestId**, sắp xếp timeline. Quan sát hai nhánh đối chiếu thay vì tìm từ khóa ERROR chung chung.
6. **So log với debugger/test/metric/trace**. Nếu log chỉ ghi một sự kiện trước khi transaction hoàn tất, kiểm tra kết quả cuối thực tế.
7. **Sửa lỗi và xác nhận lại hành vi nghiệp vụ** bằng test phù hợp, không chỉ dựa vào việc log có xuất.
8. **Hạ level, xóa debug tạm**, giữ lại các record có giá trị bảo trì lâu dài ở mức hợp lý.

Log là bằng chứng về những gì code và pipeline logging đã ghi nhận. Nó không thay cho assertion, kiểm chứng trạng thái nghiệp vụ hoặc một phép đo độc lập, và cũng không đảm bảo mọi sự kiện đã được ghi đầy đủ khi có filtering, sampling hoặc lỗi I/O.

## 12. Tự kiểm tra

**Câu 1:** Logger FINE và ConsoleHandler INFO. Một dòng FINE có hiện trên console của handler đó không?  
**Đáp án:** Không. Logger nhận record nhưng handler lọc ở INFO. Cần đặt cả hai ngưỡng phù hợp.

**Câu 2:** Nếu ngưỡng JUL là FINE, FINER có tự động hiển thị không?  
**Đáp án:** Không. FINER thấp hơn FINE về ngưỡng; cần dùng mức đủ chi tiết như FINER hoặc FINEST tại những tầng liên quan.

**Câu 3:** Tại sao lệnh chạy ví dụ với -Dapp.env=dev có thêm hai dòng FINE?  
**Đáp án:** Chương trình chọn FINE cho cả Logger và ConsoleHandler, trong khi lần chạy mặc định chọn INFO. Code nghiệp vụ vẫn đi qua những bước như nhau.

**Câu 4:** WARNING ở sự kiện retry đồng nghĩa request lỗi?  
**Đáp án:** Không. Retry có thể đã thành công; cần kiểm tra event kết thúc của cùng requestId.

**Câu 5:** Vì sao tránh bật FINEST cho mọi thư viện?  
**Đáp án:** Chi phí lớn, tạo nhiễu, có thể làm lộ dữ liệu và khiến khó tìm record quan trọng. Nên tăng mức chi tiết ở phạm vi liên quan đến giả thuyết.

**Câu 6:** Có thể dùng cấu hình logging.properties của JUL để điều khiển trực tiếp một logger SLF4J/Logback không?  
**Đáp án:** Không được mặc định như vậy. Phải biết facade/backend và cầu nối logging, sau đó dùng cấu hình đúng cơ chế.

**Câu 7:** Log ở máy cá nhân có được phép ghi raw token vì chỉ để debug không?  
**Đáp án:** Không. Log có thể đi vào IDE, terminal history, CI hoặc bug report; phải bảo vệ dữ liệu ở mọi môi trường.

## Ghi nhớ

Ở môi trường phát triển, **mục tiêu là tạo đủ bằng chứng để giải thích hành vi**, không phải in mọi thứ. Giữ baseline dễ đọc, mở FINE/DEBUG cho đúng đoạn cần điều tra, nhớ hai ngưỡng logger/handler, gắn ngữ cảnh để đọc theo request, và hạ mức chi tiết sau khi xong. Việc bật log không được thay đổi logic nghiệp vụ hay làm rò dữ liệu nhạy cảm.
