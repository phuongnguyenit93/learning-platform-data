# User agent trong logging của ứng dụng web Java

## 1. User-Agent là gì?

Trong HTTP, **User-Agent** là một request header mà client có thể gửi để tự mô tả phần mềm tạo request: browser, công cụ dòng lệnh, SDK, crawler, mobile app hoặc client tùy chỉnh. Khi được lưu trong web access log, trường này giúp phân nhóm lưu lượng và hỗ trợ chẩn đoán sự cố liên quan khả năng tương thích client.

Một request HTTP minh họa:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.test
User-Agent: LearningClient/1.0
Accept: application/json
```

Một số dạng User-Agent có thể gặp:

```text
Mozilla/5.0 (...) Chrome/...
Mozilla/5.0 (...) Firefox/...
curl/8.5.0
PostmanRuntime/...
ExampleBot/1.0
MyCompanyApp/2.4
```

Các dòng trên chỉ minh họa **hình dạng**. Chuỗi browser thường chứa nhiều token vì lý do tương thích lịch sử; không thể suy ra browser chính từ token đầu tiên `Mozilla/5.0`.

Quan trọng nhất: **User-Agent do client tự khai, không phải danh tính được xác thực**. Người gửi request có thể tự tạo chuỗi trông giống Chrome, bot đã biết hoặc ứng dụng khác. Do đó không dùng User-Agent làm bằng chứng xác thực, điều kiện cấp quyền, kết luận chắc chắn về thiết bị hay chứng minh ai thực sự đã truy cập.

### 1.1. Vì sao ghi vào log?

Trong logging của ứng dụng web, câu hỏi thường gặp:

- Lỗi 500 hoặc timeout có tập trung ở nhóm client/browser nào?
- Endpoint này có bị một công cụ automation tự khai gửi nhiều request không?
- Sau bản cập nhật SDK, có tăng tỷ lệ lỗi ở client tự khai version mới?
- Request xuất phát từ browser, CLI hoặc mobile app theo **tín hiệu tự khai** nào?
- Có giá trị bất thường, quá dài hoặc chứa ký tự điều khiển gây lỗi parser log không?

UA có giá trị phân tích khi đi kèm **request ID/trace ID, endpoint dạng route template, HTTP method, status, thời gian xử lý và kết quả thực tế**. Một dòng chỉ ghi `User-Agent: ...` thường không đủ để tái dựng sự cố.

### 1.2. Phân biệt các khái niệm

| Dữ liệu | Trả lời gì? | Có xác thực danh tính không? |
| --- | --- | --- |
| `User-Agent` | Client **tự nhận** dùng phần mềm nào | Không |
| Principal / session đã xác thực | Hệ thống đã kiểm chứng tác nhân nào | Tùy cơ chế xác thực |
| Request ID | Log nào thuộc cùng request | Không |
| Trace ID | Span/event nào thuộc cùng trace | Không |
| IP từ kết nối | Kết nối đến từ đâu hoặc proxy nào | Không đủ xác định người dùng |
| `http.route` | Server xử lý route logic nào | Phục vụ quan sát endpoint |
| `Sec-CH-UA` và các client hints | Gợi ý bổ sung do client/browser gửi | Không |

Trường UA không thay thế authentication, authorization, bot verification hay hệ thống phát hiện gian lận.

## 2. Cách đọc User-Agent trong Java web

Trong Servlet API:

```java
// Đoạn mã tích hợp khi request là HttpServletRequest:
String rawUserAgent = request.getHeader("User-Agent");
```

`getHeader` trả giá trị header hoặc `null` nếu không tồn tại. Tên HTTP header không phân biệt chữ hoa/chữ thường; `User-Agent` và `user-agent` là cùng tên về mặt ngữ nghĩa HTTP.

Lưu ý sự khác biệt phiên bản:

- Java Servlet cũ và nhiều ứng dụng Spring Boot 2.x dùng `javax.servlet.http.HttpServletRequest`.
- Các ứng dụng Spring Boot 3.x trên Servlet stack dùng hệ sinh thái `jakarta.servlet.http.HttpServletRequest`.
- WebFlux/reactive stack không dùng cơ chế Servlet filter đồng nhất với Spring MVC; cần đọc request và ghi context theo API reactive tương ứng.

Không được giả định UA luôn có dữ liệu. HTTP client có thể bỏ header, proxy có thể sửa/loại bỏ, và một request có thể chứa nhiều header cùng tên theo hành vi container/gateway. Nếu cần kiểm soát nhiều giá trị, xem `request.getHeaders("User-Agent")` và đặt policy rõ ràng; không nối mù nhiều chuỗi không giới hạn.

### 2.1. Khác biệt giữa UA nhìn thấy ở từng tầng

```text
Browser / curl / SDK
         |
   CDN / WAF / gateway
         |
   reverse proxy
         |
   Servlet container / Spring MVC
         |
       Controller
         |
   application logger
         |
     collector / sink
```

Gateway có thể thay header trước khi chuyển đến Java app. Request bị WAF chặn có thể **không tới ứng dụng Java**, nên application log không thể tự cung cấp bằng chứng về mọi request bên ngoài. Access log ở gateway, container và application có phạm vi quan sát khác nhau. Nếu giữ nhiều bản ghi ở các tầng, cần định danh tầng phát log và request correlation để tránh đếm đôi.

## 3. Dữ liệu nào nên lưu?

Một mẫu **structured access event** minh họa:

```json
{
  "event": "HTTP_REQUEST_COMPLETED",
  "timestamp": "2026-11-10T02:00:00Z",
  "service": "orders-api",
  "requestId": "req-2001",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "durationMs": 27,
  "userAgentFamily": "BROWSER",
  "userAgentPresent": true
}
```

Đây là dữ liệu giả lập, không phải JSON tự sinh bởi mọi backend. Các field giúp trả lời “một request nào, vào route nào, trạng thái gì, client tự khai loại nào?”. Timestamp ở đây là một thời điểm minh họa.

Có ba mức thu thập:

| Biểu diễn | Ví dụ | Khi nào có ích |
| --- | --- | --- |
| Raw UA | `Mozilla/5.0 (...) Chrome/...` | Điều tra tương thích chi tiết trong phạm vi được phép |
| UA đã sanitize và giới hạn | Chuỗi bị cắt/bỏ ký tự điều khiển | Debug text log có kiểm soát |
| Coarse family | `BROWSER`, `CLI`, `SDK`, `OTHER`, `UNKNOWN` | Dashboard, aggregation và metric labels |

**Ưu tiên thu thập tối thiểu.** Nếu mục tiêu chỉ là so sánh tỷ lệ lỗi giữa browser và CLI, một nhóm `ua.family` thường phù hợp hơn raw UA chi tiết trên mọi dòng. Nếu cần raw UA phục vụ điều tra, cần quy định riêng quyền truy cập, lưu trữ và retention.

Nên phân biệt các trường:

- `ua.present`: có header hay không; không suy luận luôn có client nhận diện được.
- `ua.family`: phân loại thô, có thể sai hoặc bị giả mạo.
- `ua.original`: dữ liệu gốc; chỉ lưu khi có lý do và chính sách.
- `ua.truncated`: ghi nhận việc giới hạn độ dài nếu cần phân tích dữ liệu thiếu.
- `requestId`/route/status/duration: thông tin quan sát ứng dụng, không phải thành phần tự thân của UA.

## 4. Java 17: ví dụ độc lập đọc, làm sạch và phân loại UA

Chương trình dưới mô phỏng bốn UA khác nhau, không cần HTTP server hoặc thư viện bên ngoài:

1. `curl/8.5.0` tự khai là CLI.
2. Một chuỗi có token `Chrome/` được phân vào nhóm browser.
3. Một chuỗi có ký tự xuống dòng mô phỏng nguy cơ tạo dòng log giả.
4. Thiếu User-Agent được gán `UNKNOWN`.

Mã chỉ phục vụ **minh họa về logging và phân loại**, không phải parser User-Agent đầy đủ hay cơ chế nhận diện bot đáng tin cậy.

Lưu file **`UserAgentLogDemo.java`**:

```java
import java.util.Locale;

public class UserAgentLogDemo {
    private static final int MAX_CODE_POINTS = 80;

    private static String sanitizeForTextLog(String raw) {
        if (raw == null || raw.isBlank()) {
            return "(missing)";
        }

        StringBuilder out = new StringBuilder();
        int count = 0;

        for (int offset = 0;
                offset < raw.length() && count < MAX_CODE_POINTS;
                count++) {
            int cp = raw.codePointAt(offset);
            offset += Character.charCount(cp);

            boolean unsafe = Character.isISOControl(cp)
                    || Character.getType(cp) == Character.FORMAT
                    || (cp >= 0xD800 && cp <= 0xDFFF)
                    || cp == 34   // double quote
                    || cp == 92   // backslash
                    || cp == 0x2028
                    || cp == 0x2029;

            out.append(unsafe ? "_" : new String(Character.toChars(cp)));
        }

        return out.toString();
    }

    private static String family(String safe) {
        if ("(missing)".equals(safe)) {
            return "UNKNOWN";
        }

        String s = safe.toLowerCase(Locale.ROOT);
        if (s.startsWith("curl/")) {
            return "CLI";
        }
        if (s.contains("chrome/")
                || s.contains("firefox/")
                || s.contains("safari/")) {
            return "BROWSER";
        }
        if (s.contains("bot")) {
            return "BOT_CLAIM";
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        String[] samples = {
                "curl/8.5.0",
                "Mozilla/5.0 (Linux) Chrome/120.0",
                "demo" + (char) 10 + "WARN forged",
                null
        };

        for (int i = 0; i < samples.length; i++) {
            String safe = sanitizeForTextLog(samples[i]);
            System.out.println("req=" + (i + 1)
                    + " family=" + family(safe)
                    + " ua=" + safe);
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac UserAgentLogDemo.java
java UserAgentLogDemo
```

Kết quả **`stdout`**:

```text
req=1 family=CLI ua=curl/8.5.0
req=2 family=BROWSER ua=Mozilla/5.0 (Linux) Chrome/120.0
req=3 family=OTHER ua=demo_WARN forged
req=4 family=UNKNOWN ua=(missing)
```

### 4.1. Vì sao chương trình có kết quả đó?

- `raw == null || raw.isBlank()` giúp xử lý header bị thiếu hoặc rỗng, không gây `NullPointerException`.
- Giới hạn `80` là **số Unicode code point** được xem xét cho output; nó **không phải byte-size limit cho HTTP header**.
- `codePointAt` + `Character.charCount` tránh cắt đôi một cặp UTF-16 surrogate hợp lệ; code point không hợp lệ được thay bằng `_`.
- Ký tự điều khiển, dấu nháy kép, backslash và một số ký tự format được thay bằng `_`; vì vậy chuỗi `demo` + newline + `WARN forged` thành `demo_WARN forged`, không tạo dòng log khác.
- Phân loại bằng cách tìm token chỉ là **heuristic**. Một `curl` có thể gửi chuỗi có `Chrome/` và bị gán `BROWSER`.
- Dùng `Locale.ROOT` để lower-case không bị ảnh hưởng bởi locale của server.

**Giới hạn:** sanitizer ví dụ không thay thế JSON encoder, chuẩn escaping của logging pipeline, phân tích browser chuẩn hoặc quy định privacy. Không dùng kết quả `BROWSER`/ `BOT_CLAIM` cho authorization. Trong production nên đặt **max header size tại gateway/container trước khi lập trình parser**, vì việc cắt output không làm input cực dài trở nên vô hại từ đầu.

### 4.2. Vì sao không dùng `User-Agent` gốc để tạo tên file?

Một UA có thể rất dài hoặc chứa ký tự đặc biệt. Nếu lấy UA làm tên file, index, Kafka topic, queue hay cache key không giới hạn, client có thể khiến hệ thống tạo số lượng tài nguyên không kiểm soát, gây path injection hoặc cạn bộ nhớ/dung lượng. Hãy gán vào **nhóm hữu hạn do server định nghĩa**, và kiểm tra allowlist cho mọi đích động.

## 5. Spring Boot 3+ Servlet stack: logging nhóm User-Agent

Trong Spring MVC có thể dùng `OncePerRequestFilter` để lấy UA và ghi một event đã chuẩn hóa. Đoạn dưới **không chạy độc lập với JDK**: cần Spring Boot 3+ (Servlet stack), Spring Web, SLF4J và provider/backend tương thích.

File **`UserAgentLoggingFilter.java`** trong một ứng dụng Spring Boot phù hợp:

```java
package com.example.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class UserAgentLoggingFilter extends OncePerRequestFilter {
    private static final Logger LOG =
            LoggerFactory.getLogger(UserAgentLoggingFilter.class);

    private static String family(String raw) {
        if (raw == null || raw.isBlank()) {
            return "UNKNOWN";
        }

        String s = raw.toLowerCase(Locale.ROOT);
        if (s.startsWith("curl/")) {
            return "CLI";
        }
        if (s.contains("chrome/")
                || s.contains("firefox/")
                || s.contains("safari/")) {
            return "BROWSER";
        }
        return "OTHER";
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String uaFamily = family(request.getHeader("User-Agent"));
        long start = System.nanoTime();

        try {
            filterChain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

            String route = mapped instanceof String
                    ? (String) mapped
                    : "UNMATCHED";

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start);

            LOG.info(
                    "method={} route={} uaFamily={} durationMs={}",
                    request.getMethod(), route, uaFamily, durationMs);
        }
    }
}
```

### 5.1. Phân tích và giới hạn của đoạn tích hợp

1. Filter lấy đúng request header `User-Agent`, nhưng **chỉ ghi nhóm** thay vì raw UA.
2. Tên route lấy từ `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` khi Spring MVC đã phân giải mapping. Giá trị có thể là `/api/orders/{id}` thay vì raw path chứa ID riêng lẻ.
3. Với request chưa match (404), lỗi sớm hoặc dispatch đặc biệt, attribute này có thể không tồn tại và route thành `UNMATCHED`.
4. `finally` chạy khi `filterChain.doFilter` trở lại hoặc ném exception, nhưng không bảo đảm một event được lưu ở sink cuối cùng.
5. `durationMs` đo thời gian từ lúc filter vào đến khi nó thoát. Với **async request/streaming**, thời điểm này có thể chưa phải lúc response hoàn tất.
6. Đoạn minh họa không ghi `response.getStatus()` vì exception có thể được xử lý ở tầng khác sau khi filter đã thoát; lúc đó status quan sát chưa chắc là kết quả cuối.
7. Nếu cần access log chính xác về status, request completion và async lifecycle, chọn instrumentation/hook tương ứng ở thời điểm phản hồi hoàn thành thực sự.
8. Nếu hệ thống đã có canonical access log tại gateway/container, tránh ghi trùng ở filter và ở server mà không có nhu cầu rõ ràng.

`@Component` cần package được Spring scan; import phụ thuộc dự án. Ở hệ thống WebFlux, phải dùng API reactive tương ứng, không copy Servlet filter này nguyên xi.

## 6. Log một lần hay gắn vào từng event?

Thông thường có hai phương pháp:

**Phương pháp A — một access event mỗi request:** ghi `method`, `route`, `status`, `duration`, `requestId`, `uaFamily`; các log khác tương quan qua request ID. Đây thường là cách dễ kiểm soát dung lượng và quyền riêng tư hơn.

**Phương pháp B — gắn UA vào context:** với SLF4J + provider hỗ trợ MDC, có thể gắn `ua.family` để encoder đưa vào một số log liên quan.

```java
import org.slf4j.MDC;

// Mã tích hợp: uaFamily là giá trị phân loại đã kiểm tra.
MDC.put("ua.family", uaFamily);
try {
    processRequest();
} finally {
    MDC.remove("ua.family");
}
```

Đây là **mảnh mã**, không phải chương trình JDK độc lập; giả định phương thức `processRequest()` và các biến đã được khai báo. Trong Logback, một pattern có `%X{ua.family}` có thể hiển thị MDC nếu được cấu hình ở encoder tương ứng.

Lưu ý:

- MDC không tự tạo audit/access event; ứng dụng vẫn phải thực hiện lời gọi logger.
- Thread pool tái dùng worker thread. **Phải dọn MDC** ở `finally` để tránh thông tin request trước lọt vào request sau.
- `CompletableFuture`, thread executor, callback và WebFlux có thể chuyển sang thread khác; context không mặc nhiên đi theo, cần cơ chế propagation của framework.
- Gắn raw UA vào MDC rồi sao chép vào mọi log có thể làm tăng khối lượng dữ liệu và mở rộng phạm vi lộ thông tin.
- SLF4J API, Logback và Log4j 2 có những cấu hình khác nhau; không trộn class XML backend.

## 7. Bảo mật: coi User-Agent là input không đáng tin

### 7.1. Spoofing: chuỗi tự khai không xác minh client

Ví dụ người dùng có thể tự đặt UA:

```bash
curl -A "Mozilla/5.0 Chrome/120.0" https://example.test/
```

Đây là lệnh minh họa cách đặt User-Agent bằng `curl`, **không khẳng định URL là môi trường đang chạy**. Request do curl thực hiện vẫn có thể tự nhận là Chrome. Tương tự, một bot tự nhận `ExampleBot/1.0` không chứng minh là crawler đã được xác minh.

Không xây logic như:

```java
// Sai về bảo mật: rawUserAgent không phải chứng cứ xác thực.
if (rawUserAgent.contains("TrustedBot")) {
    skipSecurityCheck();
}
```

Đây là đoạn minh họa hành vi **cần tránh**, không phải chương trình đầy đủ. Dùng authentication/authorization, token, WAF policy, network controls hoặc cơ chế xác minh bot phù hợp cho những quyết định an ninh. User-Agent có thể là tín hiệu phụ, không phải giấy thông hành.

### 7.2. Log injection và log forging

Một input chứa newline, carriage return hoặc ký tự điều khiển có thể tạo nội dung khiến người đọc tưởng có nhiều log event:

```text
User-Agent: demo
ERROR Payment accepted for another user
```

Các container HTTP hiện đại có thể từ chối CR/LF không hợp lệ ở tầng giao thức, nhưng chính sách phòng thủ vẫn cần **không tin tưởng dữ liệu HTTP header**: hệ thống có nhiều proxy/parser/collector, và log có thể lấy từ nguồn khác.

Cách xử lý:

1. Giới hạn kích thước request/header ở server/gateway.
2. Chỉ ghi trường thật sự cần; ưu tiên nhóm đã phân loại.
3. Dùng structured log với encoder/serializer escape JSON đúng chuẩn.
4. Nếu bắt buộc ghi raw UA vào text log, sanitize ký tự điều khiển, quote, newline và áp giới hạn độ dài.
5. Không cho header tự chọn nơi ghi file/topic/index hoặc tên dynamic appender.
6. Test cả payload có newline, Unicode control, quote/backslash và input quá lớn.

**SLF4J `{}` chỉ là placeholder để định dạng**, không tự làm sạch input, không làm JSON escaping và không che secret. Sanitization cho an toàn hiển thị cũng **không làm UA trở thành đáng tin để cấp quyền**.

### 7.3. Privacy và fingerprinting

UA có thể tiết lộ hoặc góp phần suy luận browser, platform, phiên bản và đặc điểm ứng dụng. Kết hợp với IP, cookies, tài khoản, path và timestamp, dữ liệu có thể hỗ trợ **fingerprinting** người dùng/thiết bị.

Nguyên tắc:

- Hạn chế raw UA nếu chỉ cần coarse category.
- Không lưu UA cùng dữ liệu nhận diện cá nhân không cần thiết.
- Xác định quyền đọc log, retention, mục đích thu thập và đối tượng được truy cập.
- Nếu cần giữ raw để chẩn đoán, giới hạn thời gian và nơi lưu riêng.
- Tránh sao chép UA vào mọi log, message broker, trace baggage hoặc hệ thống metrics.
- Không giả định UA luôn không chứa secret: client tự viết có thể đưa thông tin không được phép vào chuỗi.

Một chuỗi đã bị cắt và escape vẫn có thể mang dữ liệu nhạy cảm. **Data minimization** là chính sách riêng, không thể thay bằng sanitizer đơn giản.

## 8. User-Agent Client Hints và sự thiếu nhất quán giữa client

Một số browser cung cấp những Client Hints:

```text
Sec-CH-UA
Sec-CH-UA-Mobile
Sec-CH-UA-Platform
```

Browser có thể giảm độ chi tiết của UA truyền thống; khả năng có/không có client hints thay đổi theo browser, policy, origin và phiên bản. Vì thế:

- Không yêu cầu tất cả request đều phải chứa `Sec-CH-UA`.
- Không coi Client Hints là bằng chứng xác thực.
- Không ghi quá nhiều tín hiệu thiết bị khi không có mục đích cụ thể.
- Đặt fallback cho giá trị thiếu và phân loại `UNKNOWN`.
- Nếu ứng dụng cần kiểm tra tương thích, kiểm thử các browser/SDK thật thay vì suy đoán hoàn toàn từ chuỗi.

Không nên dựa vào một regex tự viết để khẳng định chính xác hệ điều hành và phiên bản browser. Khi thật sự cần phân tích User-Agent chi tiết, dùng parser đã được đánh giá và kiểm soát tài nguyên, phiên bản và false positives; kết quả vẫn là **suy luận từ dữ liệu tự khai**.

## 9. Hiệu năng và cardinality

Raw User-Agent tạo ra rất nhiều chuỗi riêng biệt: trình duyệt có version khác nhau, bot tự khai, SDK, custom client... Đưa raw UA thành **metric label** sẽ làm tăng cardinality:

```text
http_requests_total{user_agent="Chrome/120 ..."}
http_requests_total{user_agent="Chrome/121 ..."}
http_requests_total{user_agent="CustomClient/xyz"}
```

Thay bằng nhãn hữu hạn:

```text
http_requests_total{ua_family="BROWSER"}
http_requests_total{ua_family="CLI"}
http_requests_total{ua_family="OTHER"}
http_requests_total{ua_family="UNKNOWN"}
```

Các tên metric trên là **ví dụ**, không phải metric tự có ở mọi framework. Nếu cần phân tích browser major version, cân nhắc tập nhóm có giới hạn hoặc báo cáo offline, không tăng nhãn động tùy ý.

Một số nguyên tắc hiệu năng khác:

- Không parse UA bằng regex tốn kém trên input không giới hạn.
- Không cache vô hạn từng giá trị raw UA; client có thể gửi chuỗi mới liên tục.
- Không lặp raw UA trong hàng chục dòng log cho cùng request.
- Kiểm soát kích thước đầu vào từ HTTP server, không chỉ cắt output sau khi xử lý.
- Đo CPU, allocation, GC và latency khi bật parser trên đường request nóng.
- Không lưu raw UA thành resource name, file name hoặc queue name sinh động theo mỗi request.

Nếu log được đưa qua async queue, log volume lớn có thể làm đầy queue; khi đó policy chặn/bỏ log còn ảnh hưởng latency và độ tin cậy. Giảm lượng dữ liệu UA có thể giúp nhưng không thay thế việc thiết kế pipeline log đúng mức tải.

## 10. User-Agent cùng request ID, route và status

Để điều tra lỗi, một access event có cấu trúc có thể như sau:

```json
{
  "event": "HTTP_REQUEST_COMPLETED",
  "requestId": "req-1007",
  "httpMethod": "GET",
  "route": "/api/orders/{id}",
  "status": 404,
  "durationMs": 18,
  "userAgentFamily": "CLI"
}
```

Nếu log ở nhiều service, request ID/trace ID giúp tìm các sự kiện cùng chuỗi xử lý. Nhưng nếu `requestId` đến từ HTTP header do client gửi thì nó cũng **không tự đáng tin**; hệ thống cần validate hoặc tạo ID chuẩn tại gateway theo policy. Request ID không thay thế principal đã xác thực.

Ưu tiên **route template** `/api/orders/{id}` thay vì raw path `/api/orders/123` để giảm cardinality và khả năng lộ thông tin. Raw query string có thể chứa token hoặc PII; không dump vào log chỉ vì đang quan sát User-Agent.

Status và duration cũng cần tính ở đúng thời điểm. Một Servlet filter ghi trong `finally` có thể không thấy status cuối sau exception handling hoặc async completion. Với yêu cầu access log chuẩn, dùng instrumentation ở điểm request thực sự hoàn thành.

## 11. Ví dụ lệnh HTTP để kiểm thử

Nếu có một server thử nghiệm trên máy bạn với endpoint tương ứng, có thể gửi các request với UA tùy chỉnh:

```bash
curl -A "LearningClient/1.0" http://localhost:8080/health
curl -A "curl/8.5.0" http://localhost:8080/health
```

Chúng chỉ minh họa cách đặt header, **không khẳng định server đang chạy ở port 8080 hoặc có endpoint `/health`**. Theo heuristic của ví dụ Java, `LearningClient/1.0` vào `OTHER` còn `curl/8.5.0` vào `CLI`. Những nhãn này không chứng minh client thật.

Khi test ứng dụng thật, nên capture sự kiện tại appender/test collector, kiểm tra đúng trường và số event; đừng chỉ tìm một chuỗi bất kỳ trong terminal.

## 12. Kiểm thử hệ thống: các ca bắt buộc

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| User-Agent thiếu / null | Không NPE; ghi `UNKNOWN` hoặc `MISSING` nhất quán |
| UA rỗng hoặc chỉ khoảng trắng | Không thành trường nhận diện giả |
| UA `curl/...` | Phân loại CLI theo rule đã định nghĩa |
| UA có nhiều token browser | Không lấy `Mozilla/5.0` làm browser chính |
| UA tự nhận là Chrome từ curl | Không tăng đặc quyền hoặc bỏ kiểm soát bảo mật |
| UA có newline/control | Không tạo dòng log giả, JSON vẫn hợp lệ |
| UA rất dài | Có limit và policy; không ngốn RAM quá mức |
| Chuỗi Unicode bất thường | Không phá encoder/collector hoặc hiển thị sai |
| Header bị proxy sửa | Biết giá trị tại từng tầng và request correlation |
| Request 404 hoặc exception | Route/status phản ánh được giới hạn quan sát |
| Request async/streaming | Duration theo đúng lifecycle yêu cầu |
| 10.000 UA khác nhau | Không tạo hàng nghìn nhãn metric/cache key không giới hạn |
| Thông tin chi tiết về thiết bị | Không vượt mục đích, quyền đọc và retention |
| Nhiều lớp cùng ghi access log | Không đếm đôi một request |
| Collector bị chậm hoặc lỗi | Có policy rõ về drop/block và giám sát backlog |

Cần kiểm tra cả **unit test** cho sanitizer/classifier và **integration test** cho Filter/Servlet lifecycle; với pipeline quan trọng, thêm end-to-end test từ gateway qua collector. Tài liệu hóa false positive/negative của heuristic, vì browser/SDK có thể thay đổi UA theo thời gian.

## 13. Những lỗi thường gặp

### “User-Agent cho biết ai đang sử dụng hệ thống”

Sai. Nó là thông tin client tự khai, thường dùng chung và dễ giả mạo. Danh tính thực cần cơ chế xác thực.

### “UA chứa chữ bot là bot được xác minh”

Sai. `BOT_CLAIM` chỉ biểu diễn chuỗi tự nhận là bot. Quyết định truy cập phải dựa trên quy trình xác minh phù hợp.

### “SLF4J placeholder đã chống được log injection”

Sai. Placeholder không thực hiện mọi escaping, giới hạn kích thước hay redaction. Dùng encoder/serializer đúng chuẩn và policy dữ liệu đầu vào.

### “Ghi nguyên UA trong MDC và mọi service log là tốt nhất”

Dễ lặp dữ liệu, tăng chi phí và rủi ro privacy. Thường chỉ cần một access event và request ID.

### “Filter luôn biết status và duration cuối cùng”

Sai nếu exception/async processing chưa hoàn tất khi filter thoát. Cần instrumentation ở đúng lifecycle.

### “Dùng raw UA làm metric label rất tiện”

Raw UA có cardinality lớn; nên dùng `ua.family` hoặc nhóm hữu hạn.

### “Chuỗi UA không thể chứa dữ liệu nhạy cảm”

Client tùy chỉnh có thể đưa vào bất cứ nội dung nào; kết hợp với thông tin khác còn tạo nguy cơ fingerprinting.

### “Sanitize xong có thể dùng UA cho authorization”

Sanitize chỉ bảo vệ đường ghi/hiển thị ở một mức, không chứng minh tính trung thực của header.

### “Không cần giới hạn header vì đã cắt text log”

Cắt output không bảo đảm input rất lớn được xử lý an toàn ở gateway, parser hoặc cache. Cần limit ở tầng HTTP trước.

## 14. Checklist triển khai

- [ ] Xác định mục đích thu thập User-Agent và nơi ghi canonical access log.
- [ ] Đọc từ `HttpServletRequest.getHeader("User-Agent")` hoặc API tương ứng đúng web stack.
- [ ] Xử lý `null`, rỗng, quá dài, nhiều header và input khó parse.
- [ ] Không dùng UA để xác thực, cấp quyền hoặc xác minh bot.
- [ ] Giới hạn header/input, sanitize/escape, structured logging và kiểm soát log injection.
- [ ] Ưu tiên `ua.family` cho metrics; không dùng raw UA làm nhãn động.
- [ ] Không lặp raw UA vào mọi event hoặc MDC không cần thiết.
- [ ] Tương quan qua request ID/trace ID và route template an toàn.
- [ ] Đảm bảo đo status/duration ở thời điểm request hoàn thành phù hợp, nhất là khi async.
- [ ] Kiểm tra log ở gateway/container/app có bị trùng hoặc khác giá trị không.
- [ ] Bảo đảm quyền đọc, retention, data minimization và privacy.
- [ ] Test từ Java unit code tới collector, gồm spoofing, dài, newline, async và overload.

**Kết luận:** User-Agent là trường **hữu ích cho quan sát và chẩn đoán web request**, nhưng chỉ phản ánh **lời khai của client**, không phải bằng chứng về danh tính hay phần mềm thật. Ghi log chất lượng cần **chuẩn hóa đủ dùng, giới hạn và bảo vệ đầu vào, tránh high cardinality, liên kết request context và tôn trọng privacy**.
