# Xử lý sự cố logging về bảo mật trong Java

## 1. Vì sao sự cố logging có thể là sự cố bảo mật?

Logging không chỉ phục vụ gỡ lỗi. Log thường ghi lại sự kiện đăng nhập, thay đổi quyền, lỗi xác thực, thao tác dữ liệu, dấu vết kiểm toán, trạng thái của dịch vụ và hoạt động bất thường. Vì vậy, khi pipeline logging xảy ra vấn đề, rủi ro không chỉ là “thiếu thông tin debug” mà còn có thể là **lộ dữ liệu, làm giả bằng chứng, che dấu hành vi xâm nhập hoặc không thể điều tra sự cố**.

Một số tình huống cụ thể:

- Một đoạn `logger.debug("headers={}", request.getHeaders())` ghi cả `Authorization` header vào file hoặc collector tập trung.
- Thông điệp lỗi database chứa connection string hoặc thông tin định danh rồi được in toàn bộ bằng stack trace.
- Người dùng đưa ký tự xuống dòng hoặc chuỗi điều khiển vào trường tên; logger ghép chuỗi thô khiến một sự kiện trông như hai dòng log khác nhau.
- Người không được phép truy cập dashboard log có thể xem session ID, email, IP, dữ liệu giao dịch hoặc bản ghi audit.
- Kẻ tấn công xóa/sửa log trên máy bị xâm nhập, làm lệch trình tự sự kiện và khiến quá trình điều tra gặp khó khăn.
- Collector hoặc log agent ngừng hoạt động trong lúc xảy ra tấn công; sự kiện quan trọng không tới được nơi lưu trữ.
- Một request tạo ra hàng chục nghìn bản ghi gây log flooding, lấp đầy ổ đĩa hoặc queue và làm lu mờ tín hiệu cảnh báo.

Trong bối cảnh **Bảo mật logging**, “xử lý sự cố logging” là quy trình **phát hiện → đánh giá phạm vi → bảo toàn bằng chứng → cô lập/ngăn chặn rủi ro → khắc phục → xác minh → phòng tái diễn**. Không nên chỉ sửa level logger rồi coi sự cố đã kết thúc.

### Ba mục tiêu bảo mật

| Mục tiêu | Câu hỏi quan trọng | Ví dụ sự cố |
| --- | --- | --- |
| **Confidentiality — bí mật** | Ai có thể đọc dữ liệu trong log? | Token/PII xuất hiện ở log tập trung hoặc bucket public |
| **Integrity — toàn vẹn** | Log có thể bị chèn, sửa, xóa hoặc giả mạo? | Log injection, sửa file audit, giả timestamp/severity |
| **Availability — sẵn sàng** | Có nhận đủ log quan trọng khi cần điều tra? | Collector offline, queue drop, disk full, log flooding |

Tính **xác thực nguồn sự kiện** và **khả năng truy vết** cũng quan trọng. Có một dòng văn bản `INFO login success` không đủ chứng minh một hành động đã xảy ra nếu nguồn log, event ID và quyền sửa/xóa không được kiểm soát.

## 2. Hiểu đường đi của một bản ghi log

Một ứng dụng Java có thể dùng SLF4J với Logback hoặc Log4j2; một ứng dụng khác có thể dùng `java.util.logging` (JUL). Bên ngoài Java còn có agent, file, stdout/stderr, transport và hệ thống thu thập.

```text
Request / job / message
          |
          v
Code ứng dụng
(logger + message + tham số + Throwable + MDC)
          |
          v
Logger level / TurboFilter / filter
          |
          v
Appender / encoder / async queue
          |
          +----------> file hoặc stdout/stderr
          |                 |
          |                 v
          |           log agent / driver
          |                 |
          v                 v
      network transport / collector
                    |
                    v
             storage / index
                    |
                    v
            dashboard / export / alert
```

Có thể rò rỉ hoặc mất dữ liệu ở **bất cứ điểm nào**. Ví dụ appender không ghi file chưa chắc do filter: có thể logger level loại event trước đó. Hoặc log đã ở stdout, nhưng agent không đưa đến collector; việc thiếu kết quả tìm kiếm trên dashboard chưa chứng minh Java logger không tạo sự kiện.

**Cần xác định mốc thành công**:

- Lời gọi `logger.info(...)` trả về: chỉ nói lời gọi logging đã kết thúc theo hành vi backend.
- Event được appender nhận: chưa chứng minh đã ghi bền vững.
- Collector nhận qua mạng: còn phụ thuộc cơ chế xác nhận và lưu trữ.
- Sự kiện nằm trong kho log có bảo vệ/retention: mới gần hơn tới mục tiêu điều tra và audit.

Khi ứng cứu, hãy vẽ đường đi từ source đến sink và hỏi **dữ liệu nào đi qua từng chặng, ai có quyền đọc, ai có quyền sửa, và dấu vết kiểm tra được ở đâu**.

## 3. Phân loại sự cố và dấu hiệu phát hiện

| Nhóm | Ví dụ | Dấu hiệu gợi ý | Ưu tiên kiểm tra |
| --- | --- | --- | --- |
| Rò bí mật | API key, bearer token, cookie, private key trong log | Secret scanner, tìm kiếm mẫu token giả, phát hiện truy cập bất thường | Chặn sinh log mới, thu hồi secret, giới hạn đọc |
| Lộ dữ liệu cá nhân | Email, số điện thoại, dữ liệu định danh hoặc nội dung request | Log debug quá chi tiết, export lớn, sai redaction | Phân loại dữ liệu, xác định phạm vi người nhận |
| Log injection/forging | Chèn CR/LF, escape sequence, cấu trúc giả | Một request tạo nhiều dòng đáng ngờ, parser lỗi, field bất thường | Kiểm tra dữ liệu đầu vào và encoder |
| Truy cập trái phép | Dashboard public, quyền đọc rộng, link export chia sẻ | IAM/ACL sai, download không bình thường | Thu hẹp quyền, vô hiệu hóa phiên truy cập |
| Thay đổi/xóa log | Bản ghi audit bị sửa, file đột ngột rỗng | Hash lệch, đứt sequence, retention thay đổi | Giữ bản sao có nguồn gốc, xem quyền ghi/xóa |
| Mất log quan trọng | Queue đầy, sink không khả dụng, agent offline | Drop count, backlog, gap theo event ID, collector 5xx | Xác minh chặng mất, bảo toàn dữ liệu còn lại |
| Log flooding | Số event/tốc độ tăng bất thường | Disk gần đầy, request latency tăng, log chiếm băng thông | Giới hạn tải, theo dõi tác động đến nghiệp vụ |
| Cấu hình nguy hiểm | DEBUG mở toàn production, in raw header/body | Thay đổi deployment, spike bytes/event | Kiểm tra effective config, nguồn override |

Không có một mức độ nghiêm trọng cố định cho tất cả các hàng trên. Ví dụ một token còn hiệu lực bị lộ cho bên thứ ba có thể nghiêm trọng hơn một dòng debug không chứa dữ liệu nhạy cảm; việc mất audit trong giai đoạn tấn công có thể cần xử lý khẩn cấp dù hệ thống nghiệp vụ vẫn chạy.

### Phân loại ưu tiên ban đầu

- **Khẩn cấp:** có bằng chứng secret còn hiệu lực đã bị phơi lộ, log bảo mật/audit có thể bị sửa/xóa, hoặc quyền đọc kho log bị mở ra cho người không được phép. Kích hoạt quy trình ứng cứu sự cố của tổ chức.
- **Cao:** log chứa PII ở nơi có quyền truy cập vượt phạm vi dự kiến, thiếu log bảo mật quan trọng trong sự cố đang diễn ra, hoặc injection ảnh hưởng tới điều tra/cảnh báo.
- **Thông thường:** log chẩn đoán bị thiếu nhưng không ảnh hưởng đến bằng chứng bắt buộc; cấu hình chưa tối ưu nhưng chưa có chỉ dấu dữ liệu bị truy cập trái phép.

Đây chỉ là cách **triage kỹ thuật**. Trách nhiệm thông báo cho khách hàng/cơ quan có thẩm quyền, thời hạn và yêu cầu lưu giữ bằng chứng phụ thuộc quy định, hợp đồng và chính sách áp dụng; cần phối hợp nhóm bảo mật/pháp chế thay vì tự đoán.

## 4. Runbook ứng cứu: từ phát hiện đến khôi phục

### Bước 1 — Xác nhận tín hiệu mà không lan truyền dữ liệu

Ghi nhận nơi phát hiện (alert, issue, kiểm thử, yêu cầu của khách hàng), thời điểm, hệ thống, môi trường và mức độ tin cậy. Kiểm tra một mẫu tối thiểu để biết là **rò secret, log bị sửa, mất event hay lỗi parser**.

Khi lập ticket hoặc gửi trao đổi nội bộ, **không copy nguyên token/PII** từ log vào kênh mới. Dùng loại dữ liệu, fingerprint, event ID, đường dẫn truy cập đã phân quyền và số lượng ước lượng. Nếu cần giữ bản đầy đủ cho điều tra, lưu ở nơi chỉ nhóm ứng cứu được phép xem, không chụp màn hình phát tán rộng.

### Bước 2 — Bảo toàn bằng chứng

Trước khi chỉnh sửa cấu hình hoặc xóa dữ liệu bị lộ, phối hợp người phụ trách ứng cứu để lưu giữ:

- Các event gốc, metadata, timestamp kèm timezone và nguồn tạo.
- Cấu hình logging có hiệu lực, phiên bản ứng dụng/image, profile và lịch sử thay đổi.
- Nhật ký truy cập dashboard, export, object storage, IAM và audit trail quản trị.
- Dữ liệu log từ nguồn độc lập (proxy, cloud control plane, log agent), nếu có.
- Bản sao hoặc snapshot được hạn chế truy cập, có hash/định danh và nhật ký ai thu thập, khi nào.

**Bảo toàn bằng chứng không có nghĩa phải để dữ liệu nhạy cảm tiếp tục public.** Có thể cô lập quyền đọc/ngắt export công khai, đồng thời giữ bản sao forensics an toàn. Không âm thầm sửa hoặc xóa log audit gốc để “làm sạch” trước khi nhóm phụ trách thống nhất cách xử lý; điều đó có thể phá hủy bằng chứng.

### Bước 3 — Khoanh vùng và hạn chế thiệt hại

Tùy sự cố:

- **Secret lộ:** vô hiệu hóa/rotate secret, kiểm tra những hệ thống phụ thuộc, giám sát sử dụng bất thường; chặn code đang log secret.
- **Kho log mở rộng quyền:** thu hồi quyền/public link, sửa chính sách bucket/dashboard/API, hủy phiên và token truy cập có nguy cơ.
- **Injection:** loại bỏ đường ghi raw input, bật encoding/canonical serialization đúng ở ứng dụng và ingestion pipeline.
- **Log flooding:** giới hạn tần suất, giảm logging lặp tại nguồn, đặt quota/buffer có kiểm soát; không bỏ sự kiện audit bắt buộc một cách tùy tiện.
- **Tampering:** khóa quyền sửa/xóa không cần thiết, giữ bản sao độc lập và nguồn sự kiện khác trước khi phục hồi.
- **Collector hỏng:** khôi phục luồng nhận, giữ spool/backlog, quan sát drop và vùng dữ liệu không thể xác minh.

### Bước 4 — Đánh giá phạm vi

Trả lời có căn cứ:

1. Những service/logger/host nào tạo hoặc nhận dữ liệu?
2. Từ khi nào đến khi nào? Có sai lệch đồng hồ, queue delay hoặc timezone?
3. Những trường nào bị lộ: token, email, IP, request body, SQL, stack trace, MDC?
4. Log đã đến đâu: stdout, local file, agent, collector, index, backup, export?
5. Ai **có quyền** đọc và có bằng chứng ai **đã thực sự đọc/tải**? Hai câu này khác nhau.
6. Có bằng chứng sự kiện bị xóa/sửa hoặc chỉ đơn giản chưa được ingest?
7. Đã rotate secret, ngắt kênh lộ và chặn ghi mới chưa?

Nếu không có audit truy cập hoặc ack cuối pipeline, hãy ghi **giới hạn điều tra**; không khẳng định “không ai đọc” chỉ vì không thấy truy cập.

### Bước 5 — Khắc phục nguyên nhân gốc

Sửa code/cấu hình thu thập dữ liệu, bổ sung allowlist/redaction, phân quyền theo least privilege, chỉnh retention, bảo vệ cấu hình logging, hạn chế export và xây dựng alert độc lập. Thay đổi phải được review và triển khai có kiểm soát.

Đặc biệt, không coi chỉ việc chuyển level từ `DEBUG` sang `INFO` là đủ: secret có thể vẫn xuất hiện trong message `INFO`, exception message, stack trace, MDC, third-party library hoặc appender khác.

### Bước 6 — Kiểm chứng và theo dõi

Tái hiện bằng **dữ liệu giả** trong môi trường kiểm thử. Xác nhận:

- Không còn dòng log mới chứa chuỗi nhạy cảm giả hoặc điều khiển CR/LF chưa encode.
- Người không được phép không còn đọc/export kho log.
- Các sự kiện bảo mật cần thiết vẫn được nhận, có event ID/correlation ID phù hợp.
- Queue, retry, error count, log-agent backlog và latency trở lại mức chấp nhận.
- Dữ liệu bị ảnh hưởng ở các bản sao/backups được xử lý theo chính sách và yêu cầu bảo toàn bằng chứng.

Lưu lại root cause, khoảng thời gian có thể bị tác động, dữ liệu chưa thể xác minh, quyết định khắc phục và người phê duyệt đóng sự cố.

## 5. Trường hợp 1: secret hoặc dữ liệu cá nhân xuất hiện trong log

### Nguồn rò phổ biến trong ứng dụng Java

```java
// Không nên: log nguyên toàn bộ header có thể chứa Authorization.
logger.debug("headers={}", request.getHeaderNames());

// Không nên: Object.toString() có thể chứa trường nhạy cảm.
logger.info("request={}", requestDto);

// Không nên: exception message có thể chứa chuỗi kết nối/URI có credentials.
logger.error("Connector failed", exception);

// Không nên: MDC có giá trị lấy từ bearer token hoặc session ID.
MDC.put("correlationId", bearerToken);
```

Đây là **mã minh họa trong ứng dụng web có biến và thư viện tương ứng**, không phải chương trình độc lập. Ở ví dụ đầu, `getHeaderNames()` chỉ trả về tên header trong Servlet API thông thường, không phải toàn bộ giá trị; điều nguy hiểm là khi code log toàn bộ **header/value map**, chẳng hạn `headers` chứa giá trị `Authorization`. Vì vậy, để biểu diễn chính xác một trường hợp rò, hãy tưởng tượng biến `headersWithValues` chứa đầy đủ tên-và-giá-trị và lời gọi `logger.debug("headers={}", headersWithValues)`. Không suy diễn rằng log **chỉ tên header** đã tiết lộ token.

Các nguồn khác bao gồm interceptor ghi request/response body, tracing baggage, HTTP client wire logs, ORM SQL logs, serializer và thư viện bên thứ ba tự ghi nội dung lỗi.

### Phản ứng đúng khi phát hiện token trong log

1. Xác định token đó có còn hiệu lực hay không, phạm vi quyền và tài nguyên mà nó truy cập được.
2. Nếu có nguy cơ thật, **revoke/rotate** theo quy trình credential; cập nhật nơi sử dụng token và kiểm tra khả năng gián đoạn ứng dụng do rotation.
3. Giới hạn quyền truy cập kho log và export, kể cả những bản sao và pipeline chuyển tiếp.
4. Đánh giá lịch sử truy cập token và log liên quan để phát hiện sử dụng bất thường.
5. Chặn việc phát sinh log chứa token: sửa call site, interceptor, formatter, cấu hình DEBUG hoặc thư viện.
6. Lưu bằng chứng theo quy trình, rồi xử lý bản sao không cần thiết theo chính sách retention, quyền riêng tư và yêu cầu pháp lý. Không xóa bừa bằng chứng điều tra.
7. Chạy kiểm thử với **secret giả duy nhất** để xác nhận không còn đi vào sink nào.

Đối với PII, cách giảm thiểu khác nhau theo mục đích thu thập và quy định. Các ví dụ an toàn hơn là mã định danh nội bộ đã được đánh giá, lý do lỗi dạng enum, correlation ID không bí mật hoặc giá trị được mask có chủ đích. **Hash không tự động biến PII thành dữ liệu công khai**: hash định danh có miền nhỏ hoặc sử dụng salt không phù hợp vẫn có nguy cơ tái nhận diện.

## 6. Trường hợp 2: log injection và giả mạo dòng log

**Log injection** xảy ra khi dữ liệu không đáng tin được đưa vào định dạng log mà không được encode/giới hạn thích hợp. Đối tượng gửi yêu cầu có thể chèn ký tự xuống dòng, escape sequence của terminal hoặc cú pháp giống phần đầu của một log entry để:

- Làm giả severity/timestamp hoặc nguồn sự kiện trong file văn bản.
- Gây nhầm lẫn cho người đọc log hoặc hệ thống parser/alert.
- Che khuất hành vi thực tế sau một loạt sự kiện giả.
- Làm lệch cấu trúc JSON/CSV nếu encoder hoặc công cụ ghép chuỗi không đảm bảo escaping.

Ví dụ không an toàn:

```java
String userId = inputFromHttp;
logger.warn("Access denied userId=" + userId);
```

Nếu `inputFromHttp` là `"u42\r\nERROR admin login succeeded"` và formatter xuất message thô vào file dạng từng dòng, một sự kiện có thể bị nhìn thành hai dòng. Vấn đề không phải tên biến `userId`, mà là **đưa dữ liệu chưa kiểm soát vào định dạng không có ranh giới an toàn**.

### Phòng vệ theo lớp

- **Ưu tiên structured logging/encoder chuẩn** để giữ trường dữ liệu tách biệt; đảm bảo codec escape control characters đúng cách.
- Nếu một trường theo hợp đồng chỉ được chứa ID ASCII, **validate allowlist và giới hạn chiều dài** trước khi đưa vào log. Đây là giải pháp theo kiểu dữ liệu cụ thể, không phải sanitizer tổng quát cho mọi chuỗi Unicode.
- Với text cần giữ nguyên nội dung (ví dụ mô tả nhập liệu), encode ký tự điều khiển và ký tự phân tách theo chuẩn của sink; tránh tự viết một phép replace sơ sài rồi cho rằng chống được mọi loại injection.
- Không tin tưởng ngay cả dữ liệu do upstream cung cấp. Header như `X-Request-ID` có thể do client tự đặt, cần validate trước khi đưa vào MDC.
- Thiết lập giới hạn độ dài message, batch và tần suất để tránh payload dài gây log flooding.
- Khi điều tra, xem log từ nguồn khác và metadata có kiểm soát để xác thực sự kiện; **không tin một dòng text do người dùng có thể tạo nội dung**.

## 7. Ví dụ Java 17 chạy độc lập: giới hạn ID không đáng tin

Ví dụ sau minh họa nguyên tắc **log trường cần thiết bằng giá trị đã validate**, không ghi token hoặc nguyên văn dữ liệu không đáng tin. Vì đầu vào ví dụ là **user ID theo hợp đồng chỉ được có `A-Z`, `a-z`, `0-9`, `_` và `-`**, việc thay ký tự ngoài allowlist bằng `_` là lựa chọn có chủ đích.

Tạo file `SafeSecurityLogDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeSecurityLogDemo {
    // Chỉ dùng cho ID theo hợp đồng ASCII. Không phải bộ redaction tổng quát.
    private static String safeId(String raw) {
        if (raw == null || raw.isEmpty()) {
            return "-";
        }
        String normalized = raw.replaceAll("[^A-Za-z0-9_-]", "_");
        return normalized.length() <= 32
                ? normalized
                : normalized.substring(0, 32);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.security.demo");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        List<String> captured = new ArrayList<>();
        Handler stdout = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    String line = record.getLevel().getName()
                            + " " + record.getMessage();
                    captured.add(line);
                    System.out.println(line);
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        stdout.setLevel(Level.INFO);
        logger.addHandler(stdout);

        try {
            String untrustedUserId = "u42\r\nERROR forged";
            String secret = "demo-token-never-log";

            logger.info("Access denied userId="
                    + safeId(untrustedUserId)
                    + " reason=INVALID_SCOPE");

            System.out.println("events=" + captured.size());
            System.out.println("secretLeaked=" + captured.stream()
                    .anyMatch(line -> line.contains(secret)));
            System.out.println("containsLineBreak=" + captured.stream()
                    .anyMatch(line -> line.contains("\r")
                            || line.contains("\n")));
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SafeSecurityLogDemo.java
java SafeSecurityLogDemo
```

**Stdout chính xác:**

```text
INFO Access denied userId=u42__ERROR_forged reason=INVALID_SCOPE
events=1
secretLeaked=false
containsLineBreak=false
```

Giải thích:

1. Hai ký tự `\r` và `\n` được thay bằng hai dấu `_` vì ID chỉ cho phép tập ký tự ASCII đã định nghĩa. Dấu cách cũng biến thành `_`; đầu vào `u42\r\nERROR forged` trở thành `u42__ERROR_forged`.
2. Trong sự kiện chỉ có một message với trường ID đã giới hạn và lý do `INVALID_SCOPE`. Giá trị `secret` không được truyền vào logger.
3. `captured` là các sự kiện mà handler trong bộ nhớ đã nhận; hai phép kiểm cuối là quan sát **trong ví dụ**, không khẳng định một ứng dụng thật có các appender khác cũng an toàn.
4. Handler hoạt động đồng bộ trên thread chính, không phát sinh timestamp hay I/O từ backend bên ngoài, nên các dòng stdout xác định. Đây chỉ là **demo kiểm thử**, không thay thế JSON encoder, secret scanner, access control hay hệ thống lưu log production.
5. Cách thay ký tự có thể làm **hai ID khác nhau thành cùng chuỗi đã chuẩn hóa**. Nếu định danh có ý nghĩa bảo mật, hãy validate/reject tại boundary, dùng ID nội bộ đáng tin hoặc ánh xạ sang surrogate ID không nhạy cảm; đừng dùng kết quả replace làm identity authority.

Với trường text Unicode cần hiển thị, chỉ dùng một quy tắc ASCII có thể làm mất thông tin. Hãy tách **kiểm tra hợp lệ của loại dữ liệu** khỏi **escaping theo format log**; tránh một hàm `sanitize(String)` mơ hồ được áp dụng cho mọi thứ.

## 8. Trường hợp 3: truy cập trái phép và xuất log

Sự cố không nhất thiết xuất phát từ mã Java. Có thể tất cả log đều được ghi đúng, nhưng người không phù hợp lại đọc được chúng vì:

- Role đọc dashboard được cấp quá rộng.
- Bucket/file export cấu hình public hoặc chia sẻ ngoài tổ chức.
- Log agent dùng credential có quyền đọc/ghi/xóa nhiều hơn cần thiết.
- Đường dẫn log cục bộ có quyền file cho user/process khác.
- API quản trị/log export không có xác thực hoặc thiếu giới hạn.
- Bản sao trong backup, máy phát triển, ticket, email hoặc data warehouse không có chính sách bảo vệ tương đương.
- Dữ liệu được gửi qua endpoint không xác thực đúng đích hoặc không bảo vệ đường truyền theo yêu cầu.

Khi phát hiện, phối hợp nhóm IAM/security để thu hẹp quyền, thu hồi phiên/token, rà soát export và kiểm tra lịch sử truy cập. **Khả năng truy cập** không đồng nghĩa **đã có truy cập**; tránh khẳng định mức độ lộ dữ liệu nếu thiếu bằng chứng.

### Nguyên tắc thiết kế quyền

- Least privilege: app chỉ cần ghi; nhân viên vận hành chỉ cần đọc đúng tập log; tài khoản quản trị retention/xóa phải được kiểm soát riêng.
- Phân tách môi trường: người có quyền debug dev không mặc nhiên được đọc log production.
- Mã hóa khi truyền và lưu theo khả năng/nền tảng, kết hợp kiểm soát khóa và quyền giải mã.
- Giới hạn export, audit mọi thao tác nhạy cảm và cảnh báo tải xuống bất thường.
- Có retention và xóa dữ liệu theo phân loại, yêu cầu hợp đồng/quy định và legal hold khi cần.
- Không chép nguyên secret vào dashboard, issue, chat hoặc email khi trao đổi xử lý sự cố.

## 9. Trường hợp 4: log bị chỉnh sửa, xóa hoặc mất khả năng kiểm toán

Một attacker có quyền ghi lên máy ứng dụng có thể sửa hoặc xóa file log nội bộ. Vì vậy, **file log cùng host không phải luôn là nguồn chứng cứ độc lập đáng tin**.

Cơ chế giảm thiểu:

1. Gửi event cần kiểm toán sang hệ thống tách biệt về quyền và miền lỗi, không chỉ lưu trên host đang được kiểm toán.
2. Dùng cơ chế append-only, immutable storage hoặc WORM nơi phù hợp với yêu cầu và hạ tầng; hiểu chính xác giới hạn của cơ chế đang dùng.
3. Bảo vệ quyền thay đổi retention, xóa index, sửa clock và cấu hình logging.
4. Dùng sequence/event ID, timestamp, nguồn phát, chữ ký/hash chain nếu threat model cần phát hiện can thiệp. Hash thuần trên một file mà attacker có quyền thay file **và thay luôn hash** không đủ chứng minh tính toàn vẹn.
5. Ghi audit trail của hành động quản trị: ai đổi level, xóa file, sửa chính sách, vô hiệu hóa agent, export dữ liệu.
6. Đối chiếu nguồn độc lập: API gateway, authentication provider, infrastructure logs, access log và hệ thống nghiệp vụ.

### Khi nghi ngờ tampering

- Không tự ý “sửa lại dòng log cho đúng” trên bản gốc.
- Thu thập bản sao có chain of custody, quyền truy cập giới hạn, hash và metadata.
- Kiểm tra khoảng trống sequence, thay đổi kích thước file, event đến muộn, timestamp bất thường và thay đổi quyền/config.
- Phân biệt **missing log** do filter/queue/drop với **tampering có chủ ý**; cần bằng chứng trước khi kết luận.
- Nếu log chính không đáng tin, dựa thêm vào các bản ghi độc lập để dựng timeline, ghi rõ độ bất định.

**Audit logging quan trọng không nên dựa duy nhất vào một cuộc gọi `logger.info` kiểu best-effort.** Nếu hợp đồng yêu cầu độ bền, cần thành phần lưu sự kiện có acknowledgment, cơ chế retry/dedup và ranh giới commit nghiệp vụ phù hợp.

## 10. Trường hợp 5: log flooding và gián đoạn pipeline

Một endpoint bị gọi lặp hoặc payload lỗi liên tục có thể khiến ứng dụng tạo rất nhiều log. Hậu quả:

- CPU tăng vì format exception/stack trace.
- Disk/volume đầy hoặc phí ingest tăng mạnh.
- Producer bị block khi appender đồng bộ/sink chậm; queue async đầy và có thể drop event.
- Alert noise làm nhân viên bỏ qua sự kiện đáng chú ý.
- Dữ liệu audit cần thiết bị trì hoãn hoặc mất.

Cách xử lý phải dựa vào mức độ quan trọng của event:

| Loại log | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Debug/trace lặp | request path, payload chẩn đoán | Có thể sampling, rate limit, giảm verbosity |
| Vận hành | retry, timeout, health check | Tổng hợp, giới hạn tần suất kèm số đếm |
| Bảo mật | login failed, deny access, escalation | Giữ khả năng điều tra, cẩn trọng khi drop/sampling |
| Audit bắt buộc | thay đổi quyền, hoạt động có ràng buộc | Xác định bảo đảm lưu trước khi báo thành công |

**Logback AsyncAppender** có các lựa chọn như `queueSize`, `discardingThreshold` và `neverBlock`. Với cấu hình có thể discard mức thấp khi gần đầy, việc thiếu log không tự động là dấu hiệu tampering. Đồng thời, `neverBlock=false` có thể khiến thread nghiệp vụ chờ khi queue đầy; thiết kế cần rõ ràng về tác động latency. Queue trong bộ nhớ không bảo vệ log sau crash.

Nếu log cần giữ lại trong outage dài, xem xét spool bền vững của agent/collector và giới hạn tài nguyên. Retry phải có timeout, backoff và chính sách khi đầy; không retry không giới hạn rồi gây sự cố thứ cấp.

### Không dùng chính logger đang hỏng để báo lỗi logger

Khi sink hỏng, log lỗi của appender nếu tiếp tục đi vào chính appender đó có thể gây đệ quy hoặc spam. Hãy dựa vào status listener, metric, health check hoặc kênh cảnh báo độc lập. Các metric như `log_dropped_events_total`, `log_last_delivery_age`, `log_export_requests_total` là **tên minh họa**, không phải mặc định có sẵn trong mọi thư viện.

## 11. Java logging: những vị trí dễ vô tình đưa dữ liệu nhạy cảm vào sink

### 11.1. Parameterized logging không tự redaction

```java
logger.info("User profile: {}", profileDto);
```

Định dạng `{}` của SLF4J có thể giúp tránh nối chuỗi khi level bị tắt, nhưng không tự nhận biết trường nào là bí mật. Nếu `profileDto.toString()` hiển thị email, address hoặc token, dữ liệu có thể xuất hiện khi level cho phép. Cần log allowlist trường an toàn, không truyền nguyên object hoặc raw HTTP body chỉ vì API nhận Object.

### 11.2. Exception và stack trace

```java
logger.error("Login provider failed", exception);
```

Dạng SLF4J này thường ghi stack trace của exception. Ngữ cảnh trong exception message/cause, URL/SQL và suppressed exception có thể chứa dữ liệu nhạy cảm. Đừng mặc định exception luôn an toàn. Một cách khác ở một số lớp là log mã lỗi và metadata đã đánh giá thay vì nguyên exception ở sink rộng quyền; tại kênh forensics có quyền phù hợp có thể cần bảo tồn trace để điều tra.

Đừng **nuốt hoàn toàn** lỗi bảo mật bằng việc xóa stack trace ở mọi nơi. Mục tiêu là đặt dữ liệu ở kênh phù hợp, bảo vệ truy cập và giữ đủ ngữ cảnh, không đơn thuần là giảm số dòng.

### 11.3. MDC và correlation ID

```java
// Minh họa code dùng SLF4J trong một tác vụ.
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", validatedRequestId);
    logger.info("Authorization denied, reason={}", reasonCode);
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đoạn này **không độc lập**: `MDC`, `logger`, `validatedRequestId`, `reasonCode` được cung cấp từ ứng dụng. `requestId` cần được validate hoặc tạo mới bằng cơ chế tin cậy; không dùng bearer token/session cookie làm correlation ID. Việc cleanup trong `finally` tránh giữ nhầm context giữa các request khi thread pool tái sử dụng thread.

Không giả định MDC tự truyền qua `ExecutorService`, `CompletableFuture` hoặc worker thread khác. Bài kiểm thử bảo mật nên xác minh request A không vô tình mang metadata của request B. Với async logging, event phải lấy đúng snapshot MDC phía producer; đọc `MDC.get(...)` ở worker không tự có context của producer.

### 11.4. Logging configuration có thể bị thay đổi ở runtime

Với Spring Boot/Logback, level có thể bị cấu hình qua file YAML/XML, environment variables, CLI hoặc endpoint quản trị được bật. Nếu `DEBUG` được mở trong production, lượng dữ liệu chẩn đoán có thể tăng; cần kiểm soát quyền đổi level và audit thay đổi. Một hệ thống dùng Log4j2/JUL có cơ chế khác, không nên gán các option Logback sang mọi backend.

Khi điều tra, xác nhận **effective level, filter, appender và encoder thật sự đang chạy**, không chỉ nhìn source config của một file. Một appender được cấu hình không có nghĩa tất cả event đều đến nơi; cần kiểm tra sink sau khi logger level/filter, queue và collector xử lý.

## 12. Thiết kế logging an toàn từ đầu

### Giảm thiểu dữ liệu

- Định nghĩa **schema sự kiện** thay vì log toàn bộ object: `eventType`, `outcome`, `reasonCode`, `requestId`, `service`, `timestamp`, và các ID đã được đánh giá.
- Chỉ lưu field thực sự phục vụ vận hành, bảo mật hoặc audit.
- Không log password, access token, refresh token, private key, cookie, raw Authorization header và các secret tương tự.
- Đối với thông tin cá nhân, dùng mask/pseudonymization theo mục đích và giới hạn truy cập/retention; không mặc định bất kỳ hash nào cũng an toàn.
- Đặt giới hạn độ dài và chính sách encoding rõ cho dữ liệu do người dùng cung cấp.
- Với structured logging, dùng JSON encoder đáng tin thay vì tự ghép chuỗi `"{\\"user\\":\\"" + userInput + "\\"}"`.

### Bảo vệ pipeline

- Thiết lập TLS/xác thực giữa agent và collector khi phù hợp.
- Tách quyền write/read/delete/export; kiểm tra quyền service account.
- Có audit trail khi thay đổi logging config, role và retention.
- Đặt quota, rotation và retention để không làm đầy storage vô hạn.
- Phân tách log nhạy cảm và log thông thường bằng quyền truy cập và mục đích sử dụng.
- Kiểm tra backup, các bản copy sang analytics và ticket attachments: đây cũng là nơi log có thể tồn tại.
- Duy trì đường cảnh báo độc lập khi logger/collector chính không khả dụng.

### Không đánh đồng redaction và authorization

Redaction giúp giảm dữ liệu rò qua message. Nhưng một kho log đã ẩn token vẫn có thể chứa pattern truy cập, IP, chi tiết hạ tầng hoặc metadata nội bộ cần bảo vệ. Access control, retention và audit là lớp phòng vệ **không thể thay thế** bởi regex redaction.

## 13. Kiểm thử bảo mật logging

### 13.1. Ma trận kiểm thử

| Tình huống | Input test | Kỳ vọng |
| --- | --- | --- |
| Token | Chuỗi secret giả có dấu hiệu riêng | Không xuất hiện ở mọi sink được kiểm tra |
| Log injection | ID có `\r`, `\n`, tab, control characters | Trường đã encode/validate; không tạo dòng log giả |
| Đầu vào dài | ID/message quá giới hạn | Được giới hạn theo schema, không làm collector quá tải |
| Dữ liệu thiếu/null | Không có request ID | Dùng giá trị mặc định an toàn, không gây exception trong logger |
| MDC giữa các task | Request A và B dùng chung executor | Không rò context từ A sang B |
| Exception nhạy cảm | Exception message chứa secret giả | Output tới sink rộng quyền không tiết lộ secret |
| Nhiều appender | Console, file, remote | Mỗi sink tuân thủ chính sách riêng, không bỏ sót kênh |
| Config runtime | Tăng level tạm thời | Không bypass redaction/least privilege |
| Collector offline | Ngắt kết nối, đầy queue | Có metric/alert và chính sách drop/retry rõ |
| Truy cập trái phép | Tài khoản không có quyền | Không đọc/export được log |
| Audit integrity | Giả lập chỉnh sửa/xóa ở nguồn kém tin cậy | Hệ thống kiểm tra phát hiện lệch hoặc vẫn còn bản độc lập |
| Sau khắc phục | Gửi probe có ID không nhạy cảm | Sự kiện quan trọng đi đến nơi cần thiết |

Không chạy test với token hoặc PII thật. Dùng marker giả, ví dụ `FAKE_SECRET_TEST_42`. Một test chỉ khẳng định token không có ở một `MemoryAppender` **không chứng minh** token đã bị loại khỏi file appender, agent, collector và bản sao khác. Cần kiểm chứng theo kiến trúc thực tế.

### 13.2. Kiểm tra output và chống flaky test

Với logging đồng bộ, có thể dùng appender test in-memory để chặn event rồi assert. Với `AsyncAppender`, cần `BlockingQueue` hoặc latch trong sink và `poll(timeout)` trước khi kiểm tra. **Không dùng `Thread.sleep(200)` làm bằng chứng chắc chắn rằng worker đã hoàn thành**.

Với trường hợp **không được có** một sự kiện, cần biết mọi event đứng trước nó trong queue đã được xử lý hoặc dùng barrier/sentinel phù hợp với hợp đồng FIFO của implementation; chờ một lúc ngắn rồi thấy rỗng không phải bằng chứng tuyệt đối. Test phải xét thêm filter, discard policy và timeout.

Với security test, nội dung log không nên được in ra test failure message nếu nó có thể chứa secret thật; sử dụng dữ liệu giả để assertion và report không làm tăng bề mặt rò rỉ.

### 13.3. Kiểm chứng code ví dụ phần 7

Một bài test độc lập có thể xác minh:

```java
// Minh họa assertion JUnit 5 trong test của dự án,
// không phải file Java độc lập.
assertEquals("u42__ERROR_forged", safeId("u42\r\nERROR forged"));
assertEquals("-", safeId(null));
assertEquals(32, safeId("x".repeat(100)).length());
```

Để gọi `safeId` từ test độc lập, cần đổi phạm vi phương thức khỏi `private` hoặc kiểm tra qua API công khai của thành phần ứng dụng. Với production, nên kiểm tra cả case Unicode, chuỗi toàn dấu cách, dữ liệu đã escape, encoded payload và correlation ID không đạt schema.

**Đừng chỉ test regex redaction đơn lẻ rồi kết luận hệ thống không thể rò dữ liệu.** Cần kiểm tra nguồn ghi khác, exception/MDC, config profile, appender và những kênh xuất dữ liệu khỏi hệ thống.

## 14. Quy trình chẩn đoán khi thiếu hoặc sai log bảo mật

Khi một cảnh báo “không tìm thấy log đăng nhập thất bại” xuất hiện, cần tách những khả năng:

1. **Sự kiện nghiệp vụ đã xảy ra chưa?** Đối chiếu nguồn xác thực, response và request ID.
2. **Code có phát log không?** Kiểm tra đường đi code, level, filter và điều kiện sampling.
3. **Appender có nhận event không?** Kiểm tra status, encoder exception, queue backlog, discard.
4. **Agent có thu dữ liệu không?** Đối chiếu stdout/file/timestamp và trạng thái collection.
5. **Collector có ingest không?** Kiểm tra transport, ack, retry, dead letter queue, parser.
6. **Dashboard có truy vấn đúng không?** Index, timezone, filter, retention, quyền xem.
7. **Có dấu hiệu can thiệp không?** Thay đổi config, role, xóa index, file bị sửa, gap event ID.
8. **Có mất bằng chứng thật không?** Chỉ khẳng định trong phạm vi có số đếm/ack đối chiếu.

Nếu phát hiện event không đến được sink, hãy tránh quy ngay cho attacker. Mất log do queue drop, sai profile hoặc collector outage là sự cố kỹ thuật; **tampering** là kết luận cần chứng cứ riêng.

### Ví dụ xử lý kết hợp: debug log lộ credential rồi bị export

Giả sử một bản triển khai vô tình bật debug request logging trong khoảng ngắn và phát hiện một export của collector chứa bearer token giả định còn hiệu lực.

Trình tự thích hợp:

1. Nhóm trực vận hành ghi nhận alert và liên hệ đầu mối an ninh.
2. Ngăn export/public access tiếp diễn, bảo toàn metadata export và quyền truy cập.
3. Phân loại token và phối hợp rotate/revoke; kiểm tra dấu hiệu sử dụng bất thường.
4. Tắt hoặc sửa đúng nguồn log header/value; không chỉ giảm level nếu event vẫn có thể lộ qua `INFO`.
5. Xác định các bản sao qua file, agent, collector, backup và export; ghi phạm vi có bằng chứng.
6. Dùng test với secret giả để xác nhận mọi sink dự kiến không còn lưu token.
7. Xử lý bản sao bị ảnh hưởng theo chính sách retention và bảo toàn chứng cứ.
8. Review cách config debug được bật, ai có quyền export, guardrail kiểm thử và alert cần bổ sung.

Không tự tuyên bố “không có rò rỉ” nếu audit quyền truy cập/export không đủ dữ liệu. Báo cáo sự cố cần phân biệt **đã xác nhận**, **có khả năng** và **chưa thể xác minh**.

## 15. Những sai lầm thường gặp khi xử lý sự cố bảo mật logging

| Sai lầm | Rủi ro | Cách xử lý phù hợp |
| --- | --- | --- |
| Copy nguyên token trong ticket/chat để báo lỗi | Tạo thêm nơi lộ secret | Dùng fingerprint, secret giả hoặc kênh chứng cứ hạn chế |
| Xóa toàn bộ log ngay khi thấy dữ liệu nhạy cảm | Có thể phá bằng chứng và audit bắt buộc | Cô lập quyền, bảo toàn bản gốc có kiểm soát rồi xử lý theo quy trình |
| Chỉ đổi `DEBUG` thành `INFO` | `INFO`/exception/MDC vẫn có thể lộ | Sửa nguồn ghi, schema, encoder, test sink cuối |
| Dùng replace regex cho mọi loại dữ liệu | Có thể bỏ sót, làm sai dữ liệu hoặc tạo collision | Validate theo kiểu trường + encoder đúng format |
| Nghĩ parameterized logging tự mask secret | SLF4J chỉ xử lý tham số/format | Dùng allowlist trường, redaction và review object.toString |
| Thấy log có dòng `ERROR admin login` là tin ngay | Dòng có thể do log injection | Xem event ID, nguồn độc lập và định dạng |
| Chỉ kiểm tra file local | Collector/export/backup vẫn có bản sao | Vẽ toàn pipeline, kiểm tra từng sink |
| Coi thiếu log là bằng chứng attacker xóa | Có thể do level/filter/queue/ingest | Phân biệt lỗi kỹ thuật và can thiệp có chủ ý |
| Mở quyền dashboard rộng để điều tra nhanh | Tăng phạm vi rò thông tin | Cấp quyền tạm có audit, tối thiểu cần thiết |
| Chỉ giám sát lỗi qua logger đang hỏng | Có thể mất luôn tín hiệu sự cố | Metric/status/health độc lập |
| Mở DEBUG toàn production để tìm nguyên nhân | Tăng chi phí và nguy cơ lộ dữ liệu | Chẩn đoán có phạm vi, thời hạn, review và hoàn nguyên |
| Kết luận exactly-once vì log đã qua queue | Async memory queue không đảm bảo durability | Xác định acknowledgment và khả năng replay/dedup |

## 16. Checklist sau khi đóng sự cố

Một sự cố logging liên quan bảo mật chỉ nên được coi là đã xử lý khi những câu hỏi sau có câu trả lời:

- [ ] Đã phân loại nguy cơ đối với **bí mật, toàn vẹn và sẵn sàng** của log.
- [ ] Đã bảo toàn bằng chứng cần thiết trong kho có giới hạn truy cập, có ghi nhận nguồn và thời gian.
- [ ] Đã ngăn event mới tiếp tục ghi dữ liệu nhạy cảm hoặc tạo log giả.
- [ ] Secret liên quan đã được đánh giá và rotate/revoke khi cần; không để credential cũ còn hiệu lực không kiểm soát.
- [ ] Đã rà soát quyền dashboard, file, bucket, agent, API, export và các bản sao.
- [ ] Đã đối chiếu log từ nhiều nguồn khi cần xác minh tính toàn vẹn.
- [ ] Đã xác định những khoảng mất log thực tế hoặc các giới hạn không thể xác minh.
- [ ] Đã kiểm thử bằng dữ liệu giả, bao gồm CR/LF, exception, MDC, async và từng sink.
- [ ] Đã đánh giá lại retention, audit, encryption, rate limit và các alert độc lập.
- [ ] Đã ghi nhận root cause, tác động, người phê duyệt khắc phục và biện pháp chống tái diễn.
- [ ] Đã phối hợp các nghĩa vụ thông báo/lưu giữ dữ liệu theo chính sách và quy định áp dụng nếu có.

**Ghi nhớ:** log vừa là công cụ phát hiện sự cố, vừa là nguồn dữ liệu nhạy cảm và có thể là bằng chứng. Khi logging gặp sự cố bảo mật, phải bảo vệ **nội dung**, **nguồn gốc**, **quyền truy cập**, **độ toàn vẹn** và **khả năng khôi phục**, thay vì chỉ cố làm cho một dòng log xuất hiện trở lại.
