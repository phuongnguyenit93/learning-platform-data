# WARN — Mức cảnh báo trong Java Logging

## 1. WARN có ý nghĩa gì?

**WARN (warning)** là mức log dùng cho một điều kiện **bất thường, có nguy cơ gây vấn đề hoặc làm suy giảm chất lượng hoạt động**, nhưng chưa đủ căn cứ để kết luận thao tác hiện tại đã thất bại hoàn toàn. Một WARN tốt giúp người vận hành nhận biết rủi ro, sự suy giảm hoặc tình trạng hệ thống đang phải khắc phục theo cơ chế dự phòng.

Ví dụ: service gọi cổng thanh toán chính bị timeout, nhưng còn tuyến dự phòng. Nếu hệ thống chuyển sang tuyến dự phòng và tiếp tục hoàn tất đơn hàng, thông điệp “cổng chính không đáp ứng, đã chuyển sang dự phòng” thường có giá trị ở mức WARN. Nếu cả hai tuyến đều thất bại khiến đơn hàng không hoàn tất, lỗi đó thường phù hợp với ERROR hơn.

**WARN mô tả mức độ nghiêm trọng và mức độ cần chú ý của sự kiện**, không phải một lệnh yêu cầu ứng dụng dừng, tự động retry, gửi thông báo hay rollback. Bản thân `logger.warn(...)` chỉ phát sự kiện vào logging pipeline theo cấu hình; nó không thay đổi luồng xử lý của Java.

Trong các thư viện Java phổ biến:

- **SLF4J, Logback, Log4j 2:** có mức tên `WARN`; lời gọi thường là `logger.warn(...)`.
- **java.util.logging (JUL) của JDK:** mức tương đương theo mục đích là `java.util.logging.Level.WARNING`; lời gọi là `logger.warning(...)` hoặc `logger.log(Level.WARNING, ...)`. JUL không khai báo hằng `Level.WARN`.
- **Thứ tự phổ biến** trong các backend dùng DEBUG/INFO/WARN/ERROR là `TRACE < DEBUG < INFO < WARN < ERROR`. Khi threshold là WARN, log ở WARN và các mức nghiêm trọng hơn thường được chấp nhận; mức INFO và DEBUG bị loại. JUL có bộ tên/cấp độ riêng, ví dụ `INFO < WARNING < SEVERE`.

Bởi vậy, “WARN” là khái niệm chung, còn **tên API, mức ưu tiên, filter và nơi xuất log cụ thể phụ thuộc framework/backend**.

## 2. Khi nào nên ghi WARN?

Hãy dùng WARN khi có **tín hiệu cụ thể, đáng chú ý và có thể hành động hoặc theo dõi**, chẳng hạn:

1. **Hệ thống đang hoạt động suy giảm:** một dependency chậm hơn ngưỡng cho phép, hệ thống sử dụng fallback hoặc dữ liệu dự phòng.
2. **Có nguy cơ sự cố nếu tình trạng tiếp diễn:** độ trễ tăng bất thường, hàng đợi gần đầy, kết nối sắp cạn, số lần retry tăng cao.
3. **Một hành vi ngoài kỳ vọng nhưng còn xử lý được:** cấu hình không tối ưu và hệ thống phải sử dụng giá trị dự phòng được phê duyệt.
4. **Điều kiện chưa gây hỏng nghiệp vụ nhưng cần xác minh:** dữ liệu phụ trợ thiếu và hệ thống áp dụng quy tắc dự phòng có thể ảnh hưởng chất lượng đầu ra.
5. **Chuyển trạng thái đáng kể:** chuyển sang degraded mode hoặc circuit breaker chuyển sang OPEN; những chuyển trạng thái này thường hữu ích hơn việc ghi lại cùng lỗi trên mọi request.

Ví dụ thông điệp có ngữ cảnh:

```text
WARN payment-service orderId=O-17 correlationId=req-21 dependency=primary-gateway outcome=FALLBACK_SELECTED reason=TIMEOUT
```

Đọc thông điệp này, người vận hành biết **dịch vụ nào, giao dịch nào, dependency nào gặp điều kiện gì và hệ thống đã phản ứng ra sao**. Nó chưa khẳng định đơn hàng cuối cùng thành công, vì fallback còn có thể thất bại. Nếu fallback thực sự thành công, cần sự kiện tiếp theo (thường INFO) cho biết kết quả cuối cùng.

Không có quy tắc “hễ xuất hiện `Exception` thì phải WARN” hoặc “hễ retry thì phải WARN”. Cần xét tác động thực tế, tần suất, kỳ vọng nghiệp vụ và khả năng hành động.

## 3. Phân biệt WARN với các mức gần nó

| Mức | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **DEBUG / TRACE / FINE** | Chi tiết kỹ thuật để điều tra, thường không cần trong vận hành bình thường. | Một lần cache miss bình thường trước khi đọc database. |
| **INFO** | Hoạt động hoặc trạng thái dự kiến đã xảy ra. | Đơn hàng được tiếp nhận hoặc đã hoàn tất thành công. |
| **WARN / WARNING** | Bất thường, rủi ro hoặc suy giảm cần chú ý; thao tác có thể vẫn hoàn tất. | Gateway chính timeout, đang chuyển sang fallback. |
| **ERROR / SEVERE** | Có lỗi đáng kể: một thao tác hoặc khả năng quan trọng không thực hiện được theo hợp đồng. | Thanh toán thất bại vì cả tuyến chính và dự phòng đều lỗi. |

Bảng này là quy ước thiết kế thường gặp, **không phải quy tắc cứng áp dụng cho mọi dự án**. Sự kiện tương tự có thể ở các mức khác nhau nếu kỳ vọng và mức tác động khác nhau. Một lần retry được thiết kế sẵn và xảy ra đều đặn có thể chỉ cần DEBUG; một đợt timeout kéo dài dẫn đến degraded mode thì nên WARN. Một request bị từ chối hợp lệ vì nhập sai dữ liệu thường không phải ERROR hệ thống.

Ba câu hỏi giúp lựa chọn mức:

- **Có khác thường so với hợp đồng vận hành không?** Nếu không, thường dùng INFO/DEBUG hoặc metric.
- **Hành động hiện tại đã thất bại đáng kể chưa?** Nếu có, cân nhắc ERROR; nếu chưa nhưng đã suy giảm hoặc có rủi ro, cân nhắc WARN.
- **Tín hiệu có ích cho việc ra quyết định không?** Nếu phát WARN mỗi giây mà không ai có thể phân biệt hay xử lý, cần thay đổi vị trí ghi, cấu trúc hoặc cơ chế tổng hợp.

**Một sự kiện WARN không đảm bảo toàn bộ request thành công**; và một ERROR không nhất thiết khiến cả process chết. Chúng chỉ thể hiện mức độ theo chính sách logging.

## 4. Đặt WARN đúng thời điểm trong luồng nghiệp vụ

Ví dụ luồng thanh toán có hai tuyến:

```text
Bắt đầu thanh toán
        |
        v
Gọi gateway chính
        |
    +---+---+
    |       |
 Thành công  Timeout/không khả dụng
    |       |
    v       v
 INFO     WARN: tuyến chính suy giảm,
success   đang chọn fallback
            |
            v
       Gọi gateway phụ
            |
        +---+---+
        |       |
     Thành công  Thất bại
        |       |
        v       v
      INFO     ERROR:
   completed   payment failed
```

Diễn giải:

- WARN được phát **khi phát hiện bất thường có ý nghĩa** (gateway chính không đáp ứng) và quyết định chuyển sang fallback.
- WARN không được phép mô tả sai thành “đã hoàn tất bằng fallback” trước khi fallback thực sự hoàn tất.
- Nếu fallback thành công, có log hoặc metric xác nhận thao tác hoàn tất.
- Nếu fallback thất bại, ghi lỗi ở ranh giới xử lý thích hợp. Tránh cùng stack trace bị ghi liên tiếp ở gateway adapter, service và controller nếu không thêm ngữ cảnh mới.
- Một retry không phải lúc nào cũng cần một WARN. Trong hệ thống retry hàng nghìn lần, tốt hơn là ghi khi **sự kiện chuyển trạng thái**, vượt ngưỡng hoặc phải thay đổi hành vi.

Đối với các công việc nền như job đồng bộ, “job chậm hơn lịch 2 phút” có thể là WARN nếu trễ này có ý nghĩa; “job không thể hoàn tất và đã hết các cơ chế xử lý” thường là ERROR. Ngưỡng 2 phút chỉ là ví dụ: dự án phải xác định ngưỡng theo SLO và nhu cầu nghiệp vụ thực.

## 5. Thông tin cần có trong một WARN hữu ích

Một thông điệp WARN nên trả lời đủ để tìm nguyên nhân và đánh giá tác động, nhưng tránh làm lộ dữ liệu.

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Thời điểm | Đặt sự kiện vào dòng thời gian; ưu tiên timestamp có offset/UTC. | `2026-11-09T08:00:00Z` |
| Service/component | Xác định nơi sự kiện xuất hiện. | `payment-service` |
| Mã hoạt động | Lọc và tổng hợp ổn định khi câu chữ thay đổi. | `PAYMENT_GATEWAY_TIMEOUT` |
| Mức | Cho biết đây là cảnh báo. | `WARN` |
| Đối tượng liên quan | Truy vết thao tác, hạn chế dữ liệu nhạy cảm. | `orderId=O-17` |
| Mã liên kết | Tìm các bước xử lý cùng giao dịch. | `correlationId=req-21` |
| Tác động/phản ứng | Biết mức độ suy giảm và hành động của hệ thống. | `fallback=selected` |
| Nguyên nhân hoặc ngưỡng | Giúp phân loại. | `reason=TIMEOUT`, `elapsedMs=3000` |

Một event có cấu trúc có thể có dạng:

```json
{
  "timestamp": "2026-11-09T08:00:00Z",
  "level": "WARN",
  "service": "payment-service",
  "event": "PAYMENT_GATEWAY_TIMEOUT",
  "orderId": "O-17",
  "correlationId": "req-21",
  "dependency": "primary-gateway",
  "elapsedMs": 3000,
  "action": "SELECT_FALLBACK"
}
```

Các giá trị trên là dữ liệu giả định để minh họa schema. Timestamp phải được lấy từ thời điểm xử lý thật khi triển khai; `correlationId` phải được gắn nhất quán từ request, không tạo ngẫu nhiên lại ở từng lớp.

**Không đưa vào WARN**: mật khẩu, OTP, cookie, access token, refresh token, private key, toàn bộ request/response chứa dữ liệu nhạy cảm, email/số điện thoại khi không cần, hoặc toàn bộ đối tượng domain chưa được lọc. Nếu cần lưu stack trace, chọn cấp độ và thời điểm phù hợp để không tạo hàng nghìn bản sao và không phát tán bí mật trong exception message.

## 6. WARN đi qua logging pipeline như thế nào?

Lời gọi `logger.warn(...)`/`logger.warning(...)` không trực tiếp đảm bảo rằng bản ghi xuất hiện tại nơi truy vấn. Một sơ đồ đơn giản:

```text
Code tạo WARN
    |
Logger và kiểm tra level
    |
Filter / enrichment / redaction
    |
Handler hoặc appender
    |
Formatter/encoder (text, JSON ...)
    |
stdout / file / network
    |
Collector / storage (nếu có)
    |
Truy vấn, dashboard, cảnh báo
```

Khi một WARN không hiển thị, cần kiểm tra:

1. **Logger threshold:** logger có cho phép WARNING/WARN không?
2. **Handler/appender threshold và filter:** một logger đã cho phép event nhưng sink cụ thể vẫn có thể loại.
3. **Parent/additivity:** có gửi lên logger cha hoặc nhiều appender, làm WARN trùng?
4. **Queue/sink:** nếu async, queue đã đầy hoặc chưa flush? Có sự cố I/O, rotate hoặc kết nối không?
5. **Collector/search:** dữ liệu đã tới collector và được parse/index đúng chưa? Có nhầm khoảng thời gian hoặc chính sách retention?

Ví dụ, nếu backend dùng ngưỡng ERROR, WARN thường không xuất hiện; nếu dùng ngưỡng INFO, WARN thường xuất hiện cùng INFO và ERROR. Tuy nhiên, **filter riêng của handler/appender** có thể thay đổi kết quả. Đừng chỉ nhìn một thiết lập level rồi kết luận pipeline đã hoạt động.

## 7. Ví dụ Java 17+ chạy độc lập với java.util.logging

JDK có sẵn `java.util.logging` (JUL), trong đó `Level.WARNING` tương đương với WARN về mục đích. Ví dụ sau minh họa **lúc nào nên ghi WARNING** khi hệ thống chuyển sang tuyến thanh toán dự phòng, và vì sao INFO vẫn thích hợp cho các mốc bình thường.

Tạo tệp **`WarnLevelDemo.java`** với nội dung:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class WarnLevelDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.warn");

        // Không dùng handler của logger cha để tránh in trùng bản ghi.
        logger.setUseParentHandlers(false);
        for (Handler handler : logger.getHandlers()) {
            logger.removeHandler(handler);
        }

        // INFO, WARNING và SEVERE đều được phép đi qua logger.
        // FINE bị loại ngay tại ngưỡng logger.
        logger.setLevel(Level.INFO);

        Formatter lineFormatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | "
                        + formatMessage(record)
                        + "\n";
            }
        };

        // Dùng stdout và flush từng bản ghi cho ví dụ dễ kiểm chứng.
        StreamHandler output = new StreamHandler(
                System.out, lineFormatter) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        String orderId = "O-17";
        boolean primaryAvailable = false;
        boolean backupAvailable = true;

        logger.fine("orderId=" + orderId + " internal route probe");
        logger.info("orderId=" + orderId + " payment started");

        if (primaryAvailable) {
            logger.info("orderId=" + orderId
                    + " payment completed through primary");
        } else {
            logger.warning("orderId=" + orderId
                    + " primary unavailable; trying backup");

            if (backupAvailable) {
                logger.info("orderId=" + orderId
                        + " payment completed through backup");
            } else {
                logger.severe("orderId=" + orderId
                        + " payment failed: no available route");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên, tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 WarnLevelDemo.java
java WarnLevelDemo
```

**Stdout chính xác** khi giữ các biến như trong ví dụ:

```text
INFO | orderId=O-17 payment started
WARNING | orderId=O-17 primary unavailable; trying backup
INFO | orderId=O-17 payment completed through backup
```

Giải thích từng dòng:

1. `logger.fine(...)` không xuất hiện vì `Logger.setLevel(Level.INFO)` chặn mức FINE.
2. `logger.info(...)` đầu tiên mô tả một mốc bình thường: bắt đầu thanh toán.
3. Vì `primaryAvailable = false`, chương trình ghi **WARNING**: tuyến chính gặp sự cố và hệ thống đang thử dự phòng. Chưa được kết luận giao dịch đã thành công.
4. Vì `backupAvailable = true`, chương trình ghi INFO xác nhận kết quả cuối: tuyến dự phòng hoàn tất.
5. Nhánh `logger.severe(...)` chỉ chạy nếu tuyến dự phòng cũng không khả dụng; trong lần chạy mặc định nó **không xuất hiện**. Bạn có thể đổi `backupAvailable` thành `false` để quan sát điều kiện thất bại, nhưng lúc đó stdout sẽ khác mẫu trên.

Đây là **mô phỏng điều kiện sẵn có của tuyến thanh toán**, không thực hiện HTTP request, thanh toán, retry hoặc giao dịch thật. Lựa chọn thông báo WARNING/SEVERE biểu diễn quyết định thiết kế; logging không tự sửa sự cố.

**Tại sao dùng `StreamHandler`?** JUL `ConsoleHandler` thường xuất ra `System.err`. Ví dụ chủ động dùng `StreamHandler(System.out, formatter)` và flush từng lần để bạn thấy chính xác trên stdout. Hàm `Formatter.format` cố ý bỏ timestamp nhằm đảm bảo output tất định cho bài học; production nên giữ timestamp, component và correlation ID.

**Nếu đổi ngưỡng handler** thành `Level.SEVERE`, ngay cả WARNING đã được logger cho qua cũng không xuất ra handler này. Điều đó minh họa rằng level gate có thể tồn tại ở nhiều chặng.

## 8. Dùng WARN trong ứng dụng với SLF4J

Nếu dự án dùng SLF4J cùng một backend được cấu hình như Logback hoặc Log4j 2, code thường gọi:

```java
// Đoạn minh họa bên trong service đã có logger SLF4J.
// Không phải chương trình Java SE chạy độc lập.
logger.warn(
        "Primary payment route unavailable: orderId={}, dependency={}, fallback={}",
        orderId, "primary-gateway", "selected");
```

Cách này sử dụng placeholder để logging backend xử lý tham số theo API. Nó có thể tránh chi phí nối chuỗi không cần thiết khi WARN bị vô hiệu hóa, và cho phép backend hỗ trợ thêm metadata có cấu trúc tùy công cụ. Tuy nhiên, **placeholder tự nó chưa biến message thành các trường JSON riêng**: cần logging API/backend hỗ trợ structured attributes hoặc cấu hình encoder/field mapping phù hợp. Chỉ nhìn thấy dấu `{}` không chứng minh log đã được chuẩn hóa.

Khi cần exception:

```java
// Minh họa trong lớp service có logger, orderId và caughtException.
// Quyết định ghi WARN một lần ở ranh giới xử lý có ý nghĩa.
logger.warn(
        "Primary gateway failed; fallback selected for orderId={}",
        orderId,
        caughtException);
```

Theo quy ước SLF4J phổ biến, `Throwable` cuối là nguyên nhân exception, được backend in stack trace khi cấu hình cho phép. Không nên đặt message lỗi chứa token hoặc dữ liệu cá nhân vào exception một cách vô ý. Với retry diễn ra thường xuyên, có thể log WARN một lần lúc chuyển trạng thái và dùng metric đếm số retry, thay vì in toàn bộ stack trace mỗi lần.

**Lưu ý về phụ thuộc:** Các đoạn SLF4J chỉ là mã minh họa trong ứng dụng đã có SLF4J và backend; muốn biên dịch độc lập cần dependency và khai báo logger thích hợp. Chương trình `WarnLevelDemo.java` ở trên dùng thuần JDK nên không cần thêm thư viện.

## 9. WARN, retry, fallback và circuit breaker

Đây là những nơi mức WARN hay bị dùng quá mức.

### 9.1. Retry có kiểm soát

Giả sử SDK tự retry tối đa ba lần khi gặp lỗi mạng tạm thời. Nếu mỗi request đều gặp retry đầu tiên nhưng phần lớn hoàn tất nhanh, in WARN ở mỗi lần có thể tạo lượng log rất lớn. Một chính sách thực tế:

- Ghi chi tiết từng lần thử ở DEBUG khi cần điều tra.
- Dùng metric `retry_total` hoặc histogram latency để đo tần suất và tác động.
- Ghi WARN khi vượt ngưỡng liên tiếp, chuyển sang fallback, độ trễ vượt SLO hoặc cần hành động vận hành.
- Nếu hết mọi cơ chế và thao tác thất bại, log lỗi một lần tại lớp chịu trách nhiệm kết quả.

Không có nghĩa **retry luôn là DEBUG**: retry của thao tác rủi ro cao hoặc cho thấy dependency đang suy giảm có thể xứng đáng WARN. Mục tiêu là tạo tín hiệu có ý nghĩa thay vì tiếng ồn.

### 9.2. Fallback

Fallback có thể giúp giữ hệ thống hoạt động, nhưng thường đi kèm đánh đổi: kết quả cũ hơn, độ chính xác thấp hơn, thời gian đáp ứng dài hơn hoặc mất tính năng phụ. WARN nên mô tả **tác động đó**, không chỉ nói “fallback invoked”.

Ví dụ: `WARN catalog-service event=CACHE_STALE_SERVED ageSeconds=120 impact=stale_read reason=upstream_timeout`. Nếu chính sách cho phép dùng dữ liệu cũ 120 giây và tình trạng phổ biến/không ảnh hưởng, có thể cần INFO hoặc metric thay vì WARN; mức đúng phụ thuộc hợp đồng dịch vụ.

### 9.3. Circuit breaker

Circuit breaker thường có các trạng thái CLOSED, OPEN, HALF_OPEN. WARN khi chuyển CLOSED → OPEN do lỗi vượt ngưỡng có thể cung cấp thông tin quan trọng. Việc log WARN trên **mọi request** bị từ chối lúc OPEN thường làm ngập log và giấu tín hiệu chuyển trạng thái. Tốt hơn là log thay đổi trạng thái có ngữ cảnh, theo dõi số request bị chặn bằng metric và ghi recovery khi circuit breaker quay lại trạng thái bình thường.

### 9.4. Giới hạn tài nguyên

Bộ nhớ, kết nối, thread pool hay queue tăng gần ngưỡng có thể được ghi WARN khi vượt ngưỡng trong một thời gian xác định. Cần tránh dao động liên tục quanh ngưỡng bằng hysteresis, thời gian xác nhận hoặc tổng hợp định kỳ. Nếu nguồn lực đã cạn khiến nghiệp vụ thất bại, mức log cho sự cố có thể là ERROR. Đối với sức khỏe hệ thống, **metric/alert** thường là kênh chính; WARN đóng vai trò bối cảnh bổ trợ.

## 10. Cảnh báo vận hành: không coi mỗi WARN là một incident

Log WARN **không tự động đồng nghĩa phải đánh thức người trực ca**. Một dòng WARN có thể biểu thị dấu hiệu dự báo, cơ chế tự phục hồi bình thường hoặc sự kiện đã được xử lý. Alert cần tính đến:

- **Tần suất và xu hướng:** tỷ lệ WARN so với throughput, không chỉ số lượng tuyệt đối.
- **Tác động người dùng:** độ trễ, tỷ lệ lỗi, khả năng cung cấp tính năng và các SLI/SLO đã định nghĩa.
- **Mức kéo dài:** cảnh báo lặp trong bao lâu, có phục hồi hay không.
- **Độ nghiêm trọng và khả năng hành động:** ai cần phản ứng, bước xác minh đầu tiên là gì?
- **Khử trùng lặp và nhóm:** nhiều WARN của cùng một dependency có thể là một vấn đề, không phải hàng nghìn incident độc lập.

Ví dụ, một lần fallback thành công có thể chỉ xuất WARN để quan sát. Nếu 30% thanh toán chuyển fallback trong 10 phút và độ trễ vượt mục tiêu, hệ thống có thể cần alert dựa trên metric. Các con số 30%/10 phút chỉ minh họa, phải được xác định theo tải thật và yêu cầu sản phẩm.

Nếu dùng sampling hoặc rate limiting để giảm lượng WARN, cần biết sự kiện nào có thể bỏ, cách đo số bị bỏ và nguy cơ che giấu sự kiện quan trọng. Với **audit/security event bắt buộc**, không nên dựa vào WARN vận hành có thể bị lọc hoặc drop làm bằng chứng duy nhất; thiết kế đường audit riêng với chính sách lưu giữ và tính toàn vẹn phù hợp.

## 11. Chất lượng thông điệp WARN và các lỗi thường gặp

So sánh một số cách viết:

| Thông điệp | Đánh giá |
| --- | --- |
| `WARN Something happened` | Quá chung; không có nguyên nhân, phạm vi, tác động. |
| `WARN Error processing request` | Mơ hồ về việc request đã thất bại hay còn cơ chế phục hồi. |
| `WARN orderId=O-17 dependency=primary-gateway reason=TIMEOUT action=TRY_BACKUP` | Có nguyên nhân, đối tượng và bước xử lý cụ thể; dễ truy vết. |
| `WARN userPassword=... token=...` | **Sai:** làm lộ dữ liệu nhạy cảm trong log. |
| `WARN Retry 1`, `WARN Retry 2`, `WARN Retry 3` cho mọi request | Dễ tạo noise; nên xem lại tần suất, metric và chính sách ghi. |

Các sai lầm phổ biến:

1. **WARN cho hoạt động bình thường:** ví dụ `cache miss` thông thường, request thiếu optional header hợp lệ. Điều này làm dashboard luôn báo vàng và mất giá trị phát hiện bất thường.
2. **WARN cho lỗi nghiệp vụ đã chắc chắn thất bại:** nếu không thể hoàn thành hợp đồng thao tác, cần xem xét ERROR và kết quả trả về đúng, thay vì chỉ giảm mức log.
3. **Ghi WARN trong `catch` rồi ném tiếp exception, để lớp trên ghi ERROR giống hệt:** tạo stack trace trùng. Hãy chọn một lớp chịu trách nhiệm ghi kết quả, các lớp khác bổ sung context qua cơ chế hợp lý.
4. **Nhầm logging với xử lý lỗi:** gọi `logger.warning(...)` không retry, rollback, circuit-break hay thông báo tới client; các hành động đó phải được code thực hiện rõ ràng.
5. **Không gắn service/operation/correlation ID:** khi nhiều instance ghi đồng thời, khó liên hệ cảnh báo với yêu cầu bị ảnh hưởng.
6. **In toàn bộ object hoặc thông điệp exception không được kiểm soát:** phát tán dữ liệu nhạy cảm và tăng kích thước bản ghi.
7. **Dùng string tự do không có mã sự kiện ổn định:** thay đổi câu chữ làm các truy vấn và biểu đồ theo chuỗi dễ hỏng.
8. **Không theo dõi số WARN bị drop hoặc độ trễ ingest:** nghĩ rằng không có WARN trong kho nghĩa là không có vấn đề.
9. **Chỉ nhìn log ERROR khi kiểm tra health:** bỏ qua WARN đang phản ánh degraded mode kéo dài; mặt khác không nên coi mọi WARN là sự cố nghiêm trọng.

## 12. Cách kiểm thử và kiểm tra cấu hình WARN

Các ca kiểm thử thiết thực:

| Tình huống | Kỳ vọng |
| --- | --- |
| Tuyến chính hoạt động bình thường | Không tạo WARN vô nghĩa; có INFO hoặc metric theo nhu cầu. |
| Tuyến chính lỗi, fallback thành công | Ghi WARN tại lúc phát hiện suy giảm; kết quả cuối phản ánh thành công. |
| Cả tuyến chính và fallback thất bại | Có dấu vết lỗi cuối đúng mức; không báo thành công sai. |
| Threshold = ERROR trong backend | WARN có thể bị loại theo ngưỡng; chỉ log mức nghiêm trọng hơn đi qua. |
| Threshold = INFO, handler cho phép WARN | WARN được xuất, trừ khi filter hoặc sink loại riêng. |
| WARN chứa dấu nháy hoặc newline từ input | Encoder escape đúng; không tạo dòng log giả và không để lộ bí mật. |
| Dependency lỗi hàng loạt | Số WARN hữu ích, có cơ chế tránh bão log, số event bị bỏ nếu có được đo. |
| Xử lý qua thread pool/async | `correlationId` đúng từng request; không rò context giữa các lần dùng thread. |
| Collector hoặc sink lỗi | Có cơ chế retry/metrics/alert phù hợp; biết giới hạn độ bền và mất log. |

Khi không thấy WARN dự kiến, thứ tự điều tra nên là: **code có chạy đến nhánh cảnh báo? → logger level → filter → handler/appender level → sink/queue → collector → kho/truy vấn**. Khi thấy WARN quá nhiều, kiểm tra điều kiện tạo event và tần suất trước, rồi mới xét rate limiting hoặc điều chỉnh mức.

## 13. Checklist trước khi sử dụng WARN trong production

1. **Có điều kiện bất thường thật:** cảnh báo chỉ phát khi có sai lệch, suy giảm hoặc rủi ro được định nghĩa rõ.
2. **Chọn mức theo tác động:** INFO cho tiến trình dự kiến, WARN cho bất thường cần chú ý còn khả năng xử lý, ERROR cho thất bại đáng kể.
3. **Ghi đúng thời điểm:** không báo fallback hoàn tất khi mới bắt đầu; không khẳng định request thành công trước khi xử lý thực sự thành công.
4. **Ghi đủ ngữ cảnh:** service, mã sự kiện, dependency, mã đối tượng được phép, correlation ID, tác động và phản ứng của hệ thống.
5. **Không lộ bí mật:** kiểm soát trường, định dạng, exception và quyền truy cập log.
6. **Kiểm soát noise:** tập trung vào chuyển trạng thái/triệu chứng có ý nghĩa, kết hợp metric và cảnh báo theo SLI/SLO.
7. **Kiểm tra toàn pipeline:** level/filter ở logger và appender, async buffer, collector, độ trễ lưu trữ, khả năng tìm kiếm.
8. **Kiểm thử có thể lặp lại:** chạy tình huống bình thường, degraded, fallback thành công và fallback thất bại; xác minh kết quả và log đúng theo từng nhánh.

**Ghi nhớ:** WARN là tín hiệu rằng “đã xuất hiện điều kiện đáng chú ý và có nguy cơ ảnh hưởng hệ thống”. Giá trị của WARN nằm ở **độ chính xác, ngữ cảnh và khả năng phản ứng**, chứ không nằm ở việc ghi thật nhiều dòng cảnh báo.