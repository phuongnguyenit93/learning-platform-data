# Message có thể tìm kiếm — Thiết kế log message dễ tra cứu trong Java

## 1. “Message có thể tìm kiếm” là gì?

**Message có thể tìm kiếm** (*searchable log message*) là thông điệp log được viết và tổ chức sao cho người vận hành có thể **tìm đúng sự kiện cần điều tra, lọc theo tiêu chí và liên kết các sự kiện có liên quan** trong console, tệp log hoặc hệ thống tập trung. Một message tốt cần vừa dễ hiểu khi đọc trực tiếp, vừa có các dấu hiệu ổn định để công cụ tìm kiếm nhận diện.

Ví dụ, khi một khách hàng báo rằng thao tác thanh toán thất bại, câu log sau rất khó sử dụng:

~~~text
Có lỗi!
~~~

Thông điệp này không nói lỗi thuộc thao tác nào, cần tìm ở dịch vụ nào hoặc liên hệ với yêu cầu cụ thể ra sao. Một message có cấu trúc và ngữ cảnh rõ hơn:

~~~text
WARN service=order-api event=payment.retry requestId=req-42 orderId=ORD-7 attempt=2 reason=timeout
~~~

Nhờ các trường có tên và giá trị nhất quán, người đọc có thể tìm **event=payment.retry**, lọc **requestId=req-42**, hoặc tổng hợp những sự kiện có **reason=timeout**. Dòng trên là ví dụ về định dạng key=value, không phải cú pháp xuất log mặc định của Java.

**“Có thể tìm kiếm” không đồng nghĩa “cứ chứa nhiều chữ là tốt”.** Message hữu ích phải trả lời được một câu hỏi cụ thể: *đã xảy ra sự kiện gì, liên quan đến đối tượng/tác vụ nào, ở đâu và kết quả là gì?* Số lượng trường cần đủ dùng và không chứa dữ liệu không cần thiết.

## 2. Vì sao khả năng tìm kiếm lại quan trọng?

Một ứng dụng thực tế có thể phát nhiều log mỗi giây. Khi sự cố xảy ra, người vận hành thường không có thời gian đọc toàn bộ dòng theo thứ tự, mà cần thực hiện một số thao tác sau:

1. **Tìm sự kiện:** xem lần đăng nhập thất bại, lần retry, lần timeout hoặc lần kết thúc một tác vụ.
2. **Lọc phạm vi:** chỉ giữ log của một service, môi trường, logger, cấp log, route hoặc khoảng thời gian.
3. **Theo dõi một yêu cầu:** dùng request ID hoặc trace ID để đối chiếu các sự kiện cùng một luồng xử lý.
4. **Đếm và so sánh:** kiểm tra một loại sự kiện có xuất hiện nhiều hơn bình thường hay không; việc đo chính thức theo thời gian nên kết hợp metrics.
5. **Nhận diện nguyên nhân:** tìm mã lỗi, loại ngoại lệ, thành phần phụ thuộc hoặc bước thất bại.
6. **Đối chiếu sau khi sửa:** tìm cùng loại sự kiện trước/sau triển khai để xem vấn đề có còn xảy ra.

Nếu mỗi vị trí trong mã đặt tên sự kiện khác nhau, chẳng hạn “pay fail”, “Payment failed”, “Thanh toán bị lỗi”, công cụ phải tìm nhiều mẫu văn bản và dễ bỏ sót. **Sự ổn định của thông điệp và các trường tìm kiếm là một phần của khả năng bảo trì.**

## 3. Các thành phần của một log message có thể tìm kiếm

Một sự kiện hữu ích thường có một số trường sau, tùy tình huống:

| Thành phần | Ví dụ | Vai trò khi tra cứu |
| --- | --- | --- |
| Timestamp | 2026-11-09T10:15:00Z | Khoanh vùng thời điểm; nên có múi giờ rõ ràng |
| Level | INFO, WARN, ERROR | Phân loại mức độ cần chú ý |
| Service/component | order-api, payment-client | Xác định nơi phát sinh |
| Event name/code | payment.retry, ORDER_PAYMENT_TIMEOUT | Tìm cùng một loại sự kiện ổn định |
| Correlation ID | requestId=req-42, traceId=... | Liên kết nhiều bản ghi cùng một yêu cầu |
| Business ID | orderId=ORD-7 | Điều tra đối tượng nghiệp vụ nếu việc ghi ID được phép |
| Outcome/status | outcome=failure, status=503 | Lọc theo kết quả hoặc trạng thái |
| Error type/code | errorType=TimeoutException | Phân nhóm nguyên nhân kỹ thuật |
| Duration và đơn vị | durationMs=2500 | Nhận diện thao tác chậm |
| Message cho người đọc | “Thử lại sau timeout ở payment” | Giải thích ý nghĩa mà không cần biết mã nguồn |

Không phải tất cả trường đều cần có ở mọi dòng. Sự kiện khởi động ứng dụng không cần orderId, còn một lỗi thanh toán thường cần requestId và mã lỗi để điều tra.

### Message và metadata có thể nằm ở các vị trí khác nhau

Trong một số thư viện, **message** là phần mô tả sự kiện; timestamp, level, logger name, thread và exception được logging framework gắn vào **log event** rồi mới xuất ra tệp hoặc console. Trong structured logging, những thuộc tính này thường trở thành các trường JSON riêng. Vì thế “log message có thể tìm kiếm” bao gồm cả **cách đặt nội dung** lẫn **cách đóng gói và xuất dữ liệu log**.

Một cấu hình chỉ ghi message thô mà bỏ timestamp hoặc level có thể đủ cho bài tập nhỏ nhưng thiếu thông tin quan trọng khi vận hành. Nên thiết kế *toàn bộ bản ghi log* để tra cứu tốt.

## 4. Viết message với sự kiện ổn định

Các thông điệp tự do dễ đọc nhưng có thể thay đổi theo cách diễn đạt. Ví dụ:

~~~text
Không kết nối được payment lúc thử lần 2
Payment timeout, retrying
Lỗi gọi thanh toán: thử lại 2
~~~

Ba dòng có thể nói về cùng một loại sự kiện, nhưng việc tìm chính xác bằng một cụm từ sẽ bỏ sót các cách viết khác.

Giải pháp là chọn một **event name hoặc event code ổn định**, đồng thời giữ phần mô tả tự nhiên khi cần:

~~~text
event=payment.retry requestId=req-42 attempt=2 reason=timeout message="Retrying payment dependency"
~~~

Trong ví dụ này, **payment.retry** trở thành điểm tìm kiếm chính. Có thể điều chỉnh wording của message cho con người mà vẫn giữ event không đổi khi ý nghĩa nghiệp vụ chưa đổi.

Quy tắc đặt tên gợi ý:

- Dùng tên diễn tả **sự kiện cụ thể**, chẳng hạn **order.created**, **payment.retry**, **payment.failed**, **job.completed**.
- Chọn một quy ước chung cho chữ hoa/chữ thường và dấu phân tách; ví dụ chữ thường, dùng dấu chấm theo miền và hành động.
- Tránh tự tạo tên động như **payment.failed.order-874**. Đặt mã đơn hàng ở **trường riêng**.
- Không dùng một event cho nhiều ý nghĩa khác nhau. **payment.retry** và **payment.failed** khác nhau: một cái là thử lại, cái kia là kết quả thất bại.
- Nếu sự kiện có mã chính thức, giữ mã ổn định và tài liệu hóa ý nghĩa của nó để việc lọc/dashboard không phụ thuộc diễn đạt tự nhiên.

Event name được nhất quán giúp tìm kiếm dễ hơn; tự nó **không biến log thành metric** hoặc bảo đảm hệ thống thu thập sẽ lập chỉ mục theo trường đó.

## 5. Cấu trúc key=value và JSON

### 5.1. Dạng key=value dễ bắt đầu

Một định dạng đơn giản:

~~~text
INFO service=order-api event=order.created requestId=req-101 orderId=ORD-100 outcome=success durationMs=18
WARNING service=order-api event=payment.failed requestId=req-102 orderId=ORD-101 outcome=failure errorType=TimeoutException durationMs=2500
~~~

Ưu điểm: con người đọc nhanh, có các mẫu dễ tìm bằng công cụ tìm chuỗi, phù hợp demo và hệ thống nhỏ.

Hạn chế: nếu giá trị chứa dấu cách, dấu bằng, dấu nháy hoặc ký tự xuống dòng, việc phân tích cần **quy tắc escaping/quoting rõ ràng**. Chỉ ghép string theo cảm tính sẽ tạo dữ liệu khó parse. Các ví dụ ở bài này cố ý dùng giá trị token đơn giản.

### 5.2. JSON Lines cho structured logging

Khi công cụ thu thập hỗ trợ JSON, mỗi bản ghi có thể là một đối tượng JSON độc lập trên **một dòng**:

~~~json
{"timestamp":"2026-11-09T10:15:00Z","level":"WARN","service":"order-api","event":"payment.failed","requestId":"req-102","orderId":"ORD-101","outcome":"failure","errorType":"TimeoutException","durationMs":2500}
~~~

Ưu điểm:

- Các trường là dữ liệu có kiểu: ví dụ **durationMs** là số, giúp lọc **durationMs > 1000** chính xác hơn so với so khớp chuỗi.
- Công cụ thu thập có thể parse và truy vấn trực tiếp theo tên trường.
- Giá trị chứa dấu cách hoặc ký tự đặc biệt được biểu diễn theo cú pháp JSON chuẩn.
- Có thể tổ chức trường như **error.type**, **http.status_code**, **service.name** nếu dự án theo một schema đã chọn.

Điểm cần nhớ: **JSON phải được tạo bằng encoder/serializer phù hợp**, không chỉ ghép chuỗi thủ công mà bỏ qua escape. Khi xuất JSON Lines, một sự kiện nên tương ứng một đối tượng trên một dòng để việc xử lý đơn giản. Cách xuất stack trace cần nhất quán với bộ thu thập.

**Key=value và JSON đều có thể tìm kiếm**. JSON thuận tiện cho truy vấn trường có kiểu khi pipeline đã cấu hình parse/index; key=value vẫn hữu ích nếu công cụ có parser logfmt hoặc tìm kiếm chuỗi. Không có định dạng nào tự bảo đảm khả năng tìm kiếm khi bộ thu thập không đọc, không lưu hoặc không cho phép truy vấn dữ liệu.

## 6. Ví dụ Java 17+ chạy được với java.util.logging

JDK có **java.util.logging (JUL)**, đủ để minh họa message ổn định mà không cần dependency bên ngoài. Chương trình dưới đây ghi ba sự kiện theo quy ước **event, requestId, orderId, outcome** và một số trường tùy loại sự kiện.

Tạo tệp **SearchableMessageDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SearchableMessageDemo {
    private static final Logger LOGGER =
            Logger.getLogger(SearchableMessageDemo.class.getName());

    public static void main(String[] args) {
        // Cô lập handler để ví dụ không phát thêm log qua logger cha.
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        // Formatter gọn, không phụ thuộc thời điểm chạy.
        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        LOGGER.info("service=order-api event=order.created"
                + " requestId=req-101 orderId=ORD-100"
                + " outcome=success durationMs=18");

        LOGGER.warning("service=order-api event=payment.failed"
                + " requestId=req-102 orderId=ORD-101"
                + " outcome=failure errorType=TimeoutException"
                + " durationMs=2500");

        LOGGER.info("service=order-api event=order.created"
                + " requestId=req-103 orderId=ORD-102"
                + " outcome=success durationMs=21");

        // StreamHandler đệm bản ghi; flush để bảo đảm ví dụ in đủ.
        stdout.flush();
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên** trong terminal hiển thị UTF-8:

~~~bash
javac -encoding UTF-8 SearchableMessageDemo.java
java SearchableMessageDemo
~~~

**Stdout chính xác** khi chạy chương trình này:

~~~text
INFO service=order-api event=order.created requestId=req-101 orderId=ORD-100 outcome=success durationMs=18
WARNING service=order-api event=payment.failed requestId=req-102 orderId=ORD-101 outcome=failure errorType=TimeoutException durationMs=2500
INFO service=order-api event=order.created requestId=req-103 orderId=ORD-102 outcome=success durationMs=21
~~~

Cách hoạt động:

1. **LOGGER.info(...)** và **LOGGER.warning(...)** phát các bản ghi ở level tương ứng. Message chứa các trường có tên nhất quán.
2. **LOGGER.setLevel(Level.INFO)** và **stdout.setLevel(Level.INFO)** bảo đảm các sự kiện INFO/WARNING được nhận.
3. **setUseParentHandlers(false)** tránh cùng bản ghi bị xuất thêm qua handler của logger cha, giúp output xác định.
4. **StreamHandler(System.out, ...)** ghi ra stdout; **ConsoleHandler mặc định của JUL thường ghi stderr**, vì vậy không coi hai handler như nhau.
5. Formatter chỉ in level và message để dễ kiểm chứng; **bản production nên có timestamp, logger/service, môi trường và các trường ngữ cảnh phù hợp**.
6. **stdout.flush()** đẩy các bản ghi đang đệm trước khi chương trình kết thúc.

Để tìm kiếm trong file log trên Linux/macOS hoặc môi trường có **grep**, có thể chuyển stdout của chương trình thành tệp rồi tìm:

~~~bash
java SearchableMessageDemo > app.log
grep -F 'event=payment.failed' app.log
grep -F 'requestId=req-102' app.log
~~~

Hai lệnh grep trên đều chọn dòng WARNING thứ hai trong output đã nêu. Tùy yêu cầu, bạn có thể tìm tất cả **event=order.created** hoặc một **requestId** cụ thể. **grep -F** so khớp chuỗi con nguyên văn; nó không phải công cụ truy vấn trường có kiểu và không xác thực ranh giới trường. Ví dụ, tìm **requestId=req-1** có thể vô tình khớp **requestId=req-101**.

Trên **Windows PowerShell**, câu lệnh gần tương đương cho tệp log là:

~~~powershell
Select-String -Path app.log -SimpleMatch 'requestId=req-102'
~~~

Lệnh trả các dòng chứa chuỗi tìm kiếm, có thể kèm tên tệp và số dòng tùy môi trường hiển thị. Đây là thao tác tìm kiếm file text, không phải cấu hình của logger.

### Giới hạn của ví dụ

Chương trình minh họa khả năng tìm theo chuỗi. Nó **chưa có hệ thống thu thập tập trung, trường JSON được index, retention hoặc khả năng truy vấn phân tán**. Đầu ra cố ý không có timestamp để luôn giống nhau; logging thực tế cần thời gian rõ múi giờ để lọc theo sự cố.

Nếu dữ liệu đến từ người dùng có thể chứa khoảng trắng, dấu nháy hoặc ký tự xuống dòng, **không ghép trực tiếp vào key=value theo cách trên**. Dùng structured logging và encoder bảo đảm escaping chính xác, hoặc định nghĩa định dạng escaping rõ ràng.

## 7. Tìm theo chuỗi và tìm theo trường khác nhau thế nào?

Có hai kiểu truy vấn thường gặp.

### 7.1. Full-text hoặc substring search

Ví dụ tìm tất cả dòng chứa:

~~~text
payment.failed
~~~

Cách này dễ triển khai nhưng có thể trúng cả nội dung không phải event, ví dụ thông điệp “previous event was payment.failed”. Việc so khớp có thể phụ thuộc chữ hoa/thường, tách từ, tokenization hoặc cú pháp của công cụ.

### 7.2. Structured field filtering

Nếu dữ liệu đã được parse thành các trường riêng, có thể diễn đạt yêu cầu theo logic:

~~~text
service = "order-api"
AND event = "payment.failed"
AND outcome = "failure"
AND durationMs > 1000
~~~

Đây là **mô tả bộ lọc khái niệm**, không phải câu truy vấn có thể chạy nguyên văn trên mọi backend. Trong một hệ thống cụ thể, cú pháp của Elastic, Loki, Cloud Logging, OpenSearch hoặc công cụ khác có thể khác. Quan trọng là bộ thu thập nhận dạng được **event** và **durationMs** như các trường dữ liệu.

Khi cần một giá trị chính xác như requestId, truy vấn **bằng trường có kiểu/chuỗi chính xác** sẽ đáng tin hơn tìm chuỗi con. Chẳng hạn requestId=req-1 và requestId=req-101 là hai giá trị khác nhau, dù phép tìm substring có thể cho cùng kết quả.

## 8. Mẫu message tốt và chưa tốt

| Message khó tìm hoặc khó hiểu | Message được cải thiện | Vì sao tốt hơn |
| --- | --- | --- |
| “Có lỗi” | event=payment.failed errorType=TimeoutException | Có tên sự kiện và loại nguyên nhân |
| “Order OK” | event=order.created orderId=ORD-7 outcome=success | Có sự kiện rõ nghĩa, kết quả, ID để đối chiếu |
| “Retry lần 2” | event=payment.retry requestId=req-42 attempt=2 reason=timeout | Có thể lọc các lần retry và nguyên nhân |
| “Query chậm quá” | event=db.query.slow operation=loadOrders durationMs=1820 | Đo rõ thời lượng và tên tác vụ |
| “Sai input: [toàn bộ dữ liệu người dùng]” | event=validation.failed errorCode=INVALID_FORMAT field=postalCode | Có mã lỗi và tên trường, tránh đưa dữ liệu nhạy cảm |

Một message có thể chứa **phần mô tả dành cho con người** cùng các trường để máy lọc. Ví dụ:

~~~text
event=job.completed jobType=sync-catalog outcome=success durationMs=381 message="Catalog sync completed"
~~~

Hãy đặt trường **event** theo hành động thật, và giữ **outcome** tách riêng để phân biệt thành công/thất bại của cùng một loại tác vụ. Không tạo tên trường mới cho từng thông điệp khi nội dung chỉ khác giá trị.

## 9. Correlation ID giúp tìm toàn bộ câu chuyện của một request

Một vấn đề thường trải qua nhiều bước và có thể chạy trên nhiều thread hoặc dịch vụ:

~~~text
INFO service=checkout event=checkout.started requestId=req-42
INFO service=pricing event=price.calculated requestId=req-42 total=90
WARNING service=payment event=payment.retry requestId=req-42 attempt=2 reason=timeout
ERROR service=checkout event=checkout.failed requestId=req-42 errorCode=PAYMENT_UNAVAILABLE
~~~

Nếu tất cả bản ghi có cùng **requestId=req-42**, người điều tra có thể lọc để xem chuỗi sự kiện liên quan. Trong ứng dụng phân tán, **traceId/spanId** còn giúp liên hệ log với distributed trace khi đã thiết lập context propagation.

Cần lưu ý:

- **Request ID cần được tạo/quản lý có quy tắc và truyền qua các bước xử lý**; logger không tự thêm cùng một ID vào mọi message.
- Khi dùng thread pool, asynchronous task hoặc reactive flow, ngữ cảnh không nhất thiết tự chuyển sang thread khác; cần cơ chế propagation đúng của framework.
- Đừng mặc định **ThreadLocal/MDC** đi theo mọi asynchronous task. Với SLF4J/Logback, MDC thường được dùng để bổ sung ngữ cảnh; với JUL thuần không có một API MDC đồng nhất như vậy.
- Trong log tập trung của nhiều instance, thứ tự các dòng khi nhận **không nhất thiết là thứ tự toàn cục** của sự kiện; dùng thời điểm, trace và thông tin nguyên nhân để phân tích.

ID dùng để tìm kiếm nên được kiểm soát quyền truy cập phù hợp và không chứa dữ liệu nhạy cảm. Đừng đưa thông tin nhận diện người dùng trực tiếp vào request ID chỉ để tiện tìm log.

## 10. Java: placeholder, exception và structured logging

### 10.1. Thông điệp có tham số

Với **java.util.logging**, cú pháp định dạng tham số phổ biến là **{0}, {1}**:

~~~java
// Đoạn minh họa bên trong một lớp đã khai báo LOGGER và requestId.
LOGGER.log(java.util.logging.Level.INFO,
        "event=job.completed requestId={0} outcome=success",
        requestId);
~~~

Với **SLF4J**, cú pháp placeholder phổ biến là **{}**:

~~~java
// Đoạn minh họa: cần SLF4J API, provider và biến requestId.
LOG.info("event=job.completed requestId={} outcome=success",
        requestId);
~~~

Hai đoạn này là **minh họa trong ngữ cảnh**, chưa phải chương trình độc lập. Khi log nhiều sự kiện cùng loại, giữ **message template** ổn định và truyền giá trị dưới dạng tham số thường dễ bảo trì hơn việc tạo ra nhiều mẫu thông điệp khác nhau. Tuy nhiên, cách backend lập chỉ mục thông điệp gốc hoặc template không giống nhau ở mọi hệ thống.

**Không đồng nhất placeholder với structured field.** Một câu chứa **requestId={}** sau khi định dạng vẫn có thể chỉ là một chuỗi message; muốn truy vấn chính xác theo trường, pipeline cần parser hoặc dùng structured logging API/encoder tương ứng.

### 10.2. Ghi ngoại lệ để tìm nguyên nhân

Khi một thao tác thất bại, thông điệp nên mô tả **sự kiện** và **mã lỗi**, đồng thời giữ đối tượng ngoại lệ khi cần:

~~~java
try {
    callPaymentService();
} catch (java.io.IOException ex) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "event=payment.failed errorCode=PAYMENT_IO_ERROR",
            ex);
}
~~~

Đây là **đoạn minh họa**, vì callPaymentService() cần được định nghĩa ở chương trình thật. Phương thức **LOGGER.log(Level, String, Throwable)** giữ throwable trong LogRecord. **Formatter/handler phải hỗ trợ** mới hiển thị stack trace; formatter tối giản ở ví dụ mục 6 chỉ in level + message nên sẽ không hiển thị stack trace nếu dùng nguyên xi.

Không chỉ log **ex.getMessage()** rồi đánh mất chuỗi nguyên nhân. Đồng thời tránh ghi cùng một ngoại lệ ở mọi tầng xử lý khiến số dòng bị nhân lên, gây khó tìm sự kiện gốc.

### 10.3. Structured logging trong dự án

Trong ứng dụng lớn, nên cân nhắc một logging framework/encoder hỗ trợ **trường có cấu trúc** (chẳng hạn JSON), thay vì tự ghép toàn bộ message bằng Java string. Các thư viện như SLF4J với Logback hoặc Log4j 2 có khả năng cấu hình mạnh hơn, nhưng API, phiên bản và encoder cụ thể quyết định cách bổ sung key-value pairs, context và throwable. **JUL có thể tùy biến formatter**, song ví dụ ở đây tập trung vào bản ghi tìm kiếm được trên JDK thuần.

## 11. Bảo mật, dữ liệu nhạy cảm và giới hạn tìm kiếm

Càng nhiều log được tập trung và đánh chỉ mục, phạm vi người hoặc hệ thống có thể truy cập càng tăng. Vì thế:

- **Không ghi password, access token, API key, cookie, private key, số thẻ thanh toán hoặc nội dung nhạy cảm của request** dưới dạng thô.
- **Không mặc định log toàn bộ HTTP headers, request/response body hay object.toString()**; chúng có thể vô tình chứa bí mật và dữ liệu cá nhân.
- Nếu cần nhận diện một đối tượng nghiệp vụ, chỉ ghi **mã nội bộ không nhạy cảm** hoặc giá trị đã được làm mờ theo chính sách. Không mặc định mọi business ID đều an toàn.
- Với nội dung không tin cậy, cần xử lý **ký tự xuống dòng, dấu nháy và escape** để tránh log injection (giả mạo dòng hoặc trường log).
- Đặt quyền truy cập, thời gian lưu (*retention*) và chính sách xóa dữ liệu phù hợp. Một trường dữ liệu rất thuận tiện khi tìm kiếm vẫn có thể không nên được thu thập.
- **Không dùng dữ liệu riêng lẻ không giới hạn làm nhãn metric**. Request ID thích hợp để tương quan trong log/trace nhưng có thể tạo cardinality rất cao nếu dùng làm label trong hệ thống metrics.

Một message chuẩn còn cần tính đến chi phí. Mỗi bản ghi lớn, nhiều trường hoặc stack trace dài sẽ tăng lượng dữ liệu phải truyền và lưu. Log nhiều quá có thể làm sự kiện quan trọng bị chìm; các phép đo định lượng liên tục như số lỗi, throughput và latency percentile nên dùng metrics khi phù hợp.

## 12. Những lỗi thường gặp khi thiết kế message

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Message quá chung như “Có lỗi” | Không biết tìm theo thành phần hay nguyên nhân | Nêu event, outcome và errorCode/errorType phù hợp |
| Tên event thay đổi tùy chỗ gọi | Bỏ sót khi tìm cùng một loại sự kiện | Đặt quy ước tên/codes ổn định |
| Nhét ID vào tên event | Không thể lọc cùng một loại event đơn giản | Dùng event cố định và trường ID riêng |
| Tìm requestId bằng chuỗi con mơ hồ | Dễ khớp nhầm req-1 với req-101 | Query theo trường đã parse hoặc ranh giới chính xác |
| Đưa dữ liệu thô chứa newline vào message | Dòng log có thể bị chia/giả mạo | Escape đúng hoặc dùng structured encoder |
| Chỉ log ngoại lệ bằng message | Thiếu stack trace và nguyên nhân | Truyền Throwable khi cần và kiểm tra formatter |
| Thiếu timestamp hoặc múi giờ | Khó khoanh vùng sự cố theo thời gian | Xuất thời gian chuẩn, có timezone |
| Mỗi dòng dùng tên trường khác nhau | Truy vấn và tổng hợp phức tạp | Dùng schema/tên trường thống nhất |
| Ghi quá nhiều trường và payload lớn | Tốn lưu trữ, rủi ro dữ liệu nhạy cảm | Ghi trường tối thiểu phục vụ chẩn đoán |
| Mong thấy log dù level không được bật | Bỏ sót sự kiện ở đích xuất | Kiểm tra ngưỡng logger, handler/appender và filter |
| Coi thiếu log là bằng chứng thao tác không chạy | Kết luận sai khi log bị lọc/mất/trễ | Đối chiếu metric, trace và dữ liệu thực tế |

## 13. Cách kiểm tra một message có thật sự “tìm kiếm được” hay chưa

Trước khi đưa một mẫu log vào ứng dụng, có thể tự kiểm tra theo checklist:

1. **Đặt câu hỏi điều tra:** “Làm sao tìm mọi lần payment retry?”, “Làm sao tìm log của req-42?”, “Làm sao tìm request lỗi lâu hơn 2 giây?”.
2. **Xác định trường cần lọc:** event, service, requestId, outcome, errorCode, durationMs.
3. **Kiểm tra tính nhất quán:** cùng một ý nghĩa có dùng cùng tên event và cùng kiểu dữ liệu/trường không?
4. **Kiểm tra mẫu có dữ liệu đặc biệt:** giá trị chứa dấu cách, dấu bằng, dấu nháy, Unicode hoặc xuống dòng có được escape đúng không?
5. **Xác nhận đích ghi và cấu hình:** event có qua level, filter, handler/appender và bộ thu thập hay không?
6. **Thử tìm bằng công cụ thật:** tìm theo một event và một request ID xác định; xác minh không bỏ sót và không trúng các giá trị gần giống.
7. **Đánh giá bảo mật và chi phí:** không để lộ bí mật, không tạo payload quá lớn hoặc số lượng trường không kiểm soát.
8. **Kiểm tra khi có sự cố:** hệ thống nhận log có thể trễ, sampling hoặc rớt dữ liệu; log không phải bằng chứng tuyệt đối.

Thao tác xác nhận bằng công cụ thực tế rất quan trọng vì **khả năng truy vấn phụ thuộc cả định dạng và pipeline thu thập**, không chỉ phụ thuộc câu lệnh ghi log trong Java.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Vì sao event=payment.failed dễ tìm hơn dòng “Có lỗi thanh toán”?

**Đáp án:** Tên event ổn định có thể làm khóa tra cứu cùng một loại sự kiện qua nhiều lời gọi, tránh phụ thuộc ngôn ngữ và cách diễn đạt thay đổi.

**Câu 2.** Hai request có ID req-1 và req-101. Tìm substring **requestId=req-1** có chính xác không?

**Đáp án:** Không bảo đảm. Chuỗi đó cũng nằm trong **requestId=req-101**. Nên parse thành trường và truy vấn bằng giá trị chính xác, hoặc dùng quy tắc ranh giới rõ ràng khi chỉ có văn bản.

**Câu 3.** Message key=value có đủ để hệ thống hiểu durationMs là số không?

**Đáp án:** Không tự động. Bộ thu thập cần parser/schema và chuyển kiểu thích hợp. JSON có giá trị số giúp truyền biểu diễn có kiểu, nhưng backend vẫn phải parse đúng.

**Câu 4.** Có nên ghi toàn bộ request body để dễ tìm lỗi không?

**Đáp án:** Không mặc định. Body có thể rất lớn hoặc chứa thông tin nhạy cảm. Chọn trường tối thiểu có giá trị chẩn đoán và tuân thủ chính sách bảo mật.

**Câu 5.** Một chương trình gọi LOGGER.warning nhưng không tìm thấy log trong file. Điều đó có chứng minh mã không chạy qua lời gọi không?

**Đáp án:** Không. Còn phụ thuộc level, filter, handler, đích xuất, buffer, thu thập, thời gian lưu và có thể cả sự cố truyền log.

**Câu 6.** Cần tìm toàn bộ log của một request chạy qua nhiều dịch vụ. Trường nào hữu ích?

**Đáp án:** **requestId hoặc traceId** được truyền nhất quán qua các dịch vụ, cùng timestamp, service và event để dựng lại các bước xử lý.

**Ghi nhớ:** Một **log message có thể tìm kiếm** cần **event có ý nghĩa và ổn định, các trường nhất quán, ngữ cảnh tương quan, định dạng parse được và dữ liệu an toàn**. Viết message tốt là bước đầu; phải cấu hình logging và pipeline thu thập đúng thì việc tìm kiếm và phân tích trong thực tế mới đáng tin cậy.
