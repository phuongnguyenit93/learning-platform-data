# Mã sự kiện chuẩn trong Structured Logging của Java

## 1. Mã sự kiện chuẩn là gì?

**Mã sự kiện chuẩn** (*standard event code*) là một định danh **ổn định, có kiểm soát và có ý nghĩa đã được định nghĩa trước** cho một loại sự kiện mà ứng dụng ghi log. Mục tiêu của nó là cho phép con người và hệ thống xử lý nhận ra **điều gì đã xảy ra** mà không phụ thuộc vào câu message cụ thể, ngôn ngữ hiển thị, tên thread hoặc đường dẫn source code.

Ví dụ một nhóm sự kiện của quy trình checkout:

| eventCode | eventName | Ý nghĩa |
| --- | --- | --- |
| `ORD-1001` | `order.checkout.started` | Bắt đầu xử lý checkout |
| `ORD-1002` | `order.checkout.succeeded` | Checkout hoàn tất thành công |
| `ORD-1500` | `order.checkout.failed` | Checkout thất bại và không thể hoàn tất |
| `PAY-2001` | `payment.authorization.declined` | Đơn vị xử lý thanh toán từ chối ủy quyền |
| `INF-9001` | `infrastructure.dependency.unavailable` | Một dependency cần thiết không sẵn sàng |

Các giá trị trên là **quy ước minh họa do dự án đặt**, không phải danh mục mã bắt buộc của JDK, SLF4J, Logback, Log4j2 hay OpenTelemetry.

Một log dạng text có thể là:

~~~text
ERROR eventCode=ORD-1500 eventName=order.checkout.failed requestId=req-17 orderId=O-42 outcome=failed
~~~

Một log **có cấu trúc thực sự** có thể là:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "ERROR",
  "service": "order-service",
  "eventCode": "ORD-1500",
  "eventName": "order.checkout.failed",
  "message": "Cannot complete checkout",
  "requestId": "req-17",
  "orderId": "O-42",
  "outcome": "failed",
  "errorType": "InventoryUnavailableException"
}
~~~

Đây là **hai bản ghi minh họa**, không phải output mặc định được mọi logging framework tạo ra. Trong JSON, `eventCode` và `eventName` là các field có thể truy vấn; trong text, chúng chỉ là một phần message nếu pipeline không parse thành field.

**Nguyên tắc trọng tâm:** mã thuộc về **loại sự kiện**, còn ID của request, order, người dùng hoặc exception thuộc về **lần phát sinh cụ thể**. Không tạo mã động như `ORD-1500-O-42`; hãy giữ `ORD-1500` cố định và lưu `orderId=O-42` ở field riêng.

## 2. Vì sao hệ thống cần mã sự kiện chuẩn?

Hãy so sánh hai kiểu log lỗi:

~~~text
Không có mã:
ERROR Checkout could not be completed
ERROR Checkout failed
ERROR Không thể hoàn tất thanh toán đơn hàng

Có mã:
ERROR eventCode=ORD-1500 message="Checkout could not be completed"
ERROR eventCode=ORD-1500 message="Checkout failed"
ERROR eventCode=ORD-1500 message="Không thể hoàn tất thanh toán đơn hàng"
~~~

Ba thông điệp có thể khác nhau do phiên bản, bản dịch hoặc cách viết, nhưng nếu chúng thực sự biểu diễn **cùng một loại failure**, hệ thống vẫn có thể nhóm theo `ORD-1500`.

Những lợi ích cụ thể:

1. **Tìm kiếm nhất quán:** truy vấn theo `eventCode` thay vì regex một câu message có thể đổi.
2. **Cảnh báo chính xác hơn:** theo dõi số lần phát sinh mã lỗi quan trọng trong khoảng thời gian và theo service.
3. **Dashboard ổn định:** thống kê checkout thành công/thất bại theo loại sự kiện thay vì đếm từ khóa.
4. **Hỗ trợ xử lý sự cố:** một mã dẫn đến tài liệu runbook, owner, nguyên nhân thường gặp và hành động khuyến nghị.
5. **Phân tích qua nhiều phiên bản:** message có thể được cải thiện mà truy vấn theo mã vẫn hoạt động.
6. **Tích hợp giữa các đội:** service, collector và hệ thống hỗ trợ có chung danh mục định nghĩa loại sự kiện.
7. **Giảm cardinality của khóa phân nhóm:** danh mục eventCode được quản lý thường nhỏ và ổn định hơn tập request ID, path động hoặc exception message.

**Không phải mọi dòng log đều cần mã.** Những log DEBUG ngắn phục vụ khảo sát tạm thời có thể không cần hợp đồng sự kiện lâu dài. Ưu tiên định nghĩa mã cho các **mốc vận hành, chuyển trạng thái, kết quả quan trọng, lỗi cần điều tra hoặc sự kiện tích hợp** có giá trị tìm kiếm/báo cáo rõ ràng.

## 3. Phân biệt eventCode với các trường dễ nhầm

| Trường | Trả lời câu hỏi | Thường thay đổi thế nào? |
| --- | --- | --- |
| `eventCode` | Đây là **loại sự kiện nào** theo danh mục của hệ thống? | Ổn định cho cùng một loại; không nhét ID động |
| `eventName` | Tên ngữ nghĩa, dễ đọc của loại sự kiện? | Ổn định theo hợp đồng, ví dụ `order.checkout.failed` |
| `level` / `severity` | Sự kiện nghiêm trọng đến đâu trong ngữ cảnh này? | Có thể đổi theo chính sách/tác động |
| `message` | Mô tả bằng ngôn ngữ con người ở lần ghi này? | Có thể thay câu chữ, ngôn ngữ, ngữ cảnh |
| `errorCode` | Mã lỗi nghiệp vụ/API trả cho bên gọi? | Có thể trùng hoặc khác eventCode, cần mapping rõ |
| `requestId` | Sự kiện thuộc request nào? | Khác nhau theo request, cardinality rất cao |
| `traceId` / `spanId` | Sự kiện liên quan trace/span nào? | Khác nhau theo lần thực thi |
| `orderId` / `jobId` | Đối tượng nghiệp vụ của sự kiện? | Khác nhau theo đơn hàng/job |
| `exception.type` | Exception kỹ thuật thuộc loại gì? | Phụ thuộc sự cố và tầng phát sinh |
| `schemaVersion` | Bản hợp đồng cấu trúc log đang dùng? | Đổi khi schema phát triển có chủ đích |

### 3.1. Event code không phải log level

Một sự kiện `ORD-1500` thường được ghi ở ERROR khi checkout thật sự thất bại. Nhưng trong một flow có xử lý được lỗi bằng retry, đội có thể ghi một event kỹ thuật khác ở WARN, rồi ghi `ORD-1002` khi checkout hoàn tất. Không nên nhồi severity vào mã rồi giả định một mức log luôn đúng trong mọi tình huống.

Mã nói **điều gì**; mức nói **tác động/độ ưu tiên quan sát** của lần phát sinh. Nếu một sự kiện có nhiều mức tùy tình huống, danh mục phải nêu quy tắc cụ thể hoặc tách thành các loại sự kiện khác nhau nếu ý nghĩa thực sự khác.

### 3.2. Event code không phải mã phản hồi HTTP

Một request checkout có thể trả HTTP 503, nhưng `ORD-1500` không tự động đồng nghĩa HTTP 503. Một mã sự kiện của hệ thống nội bộ có thể liên quan nhiều API/status, hoặc nhiều mã sự kiện có thể dẫn tới cùng một HTTP status.

Ví dụ:

~~~text
Internal log:
  eventCode=ORD-1500, outcome=failed, dependency=inventory

Public HTTP response:
  status=503, errorCode=ORDER_TEMPORARILY_UNAVAILABLE, requestId=req-17
~~~

Việc ánh xạ giữa `eventCode` và `errorCode` cần được định nghĩa; **không gửi stack trace, mã hạ tầng nội bộ hoặc thông tin bí mật ra public response** chỉ để người dùng thấy cùng một định danh.

### 3.3. Mã sự kiện không thay thế context

Chỉ ghi `eventCode=ORD-1500` chưa đủ để tìm request nào thất bại. Một bản ghi hữu ích cần thêm `requestId`, service, operation, outcome và các trường đã được cho phép. Ngược lại, chỉ có `requestId` mà không có eventCode thì rất khó tổng hợp theo loại sự kiện.

## 4. Thiết kế quy ước đặt mã

Một quy ước nội bộ dễ quản lý:

~~~text
<DOMAIN>-<NUMBER>

ORD-1001
ORD-1002
ORD-1500
PAY-2001
INF-9001
~~~

Đây là **một lựa chọn thiết kế**, không phải chuẩn công nghiệp bắt buộc. Có thể chọn mã thuần số, mnemonic string hoặc UUID do hệ thống quản lý; nhưng trong tài liệu học này ta dùng tiền tố miền và số bốn chữ số để dễ xem log.

### Quy tắc nên có

1. **Ổn định:** khi ý nghĩa loại sự kiện không đổi, mã không đổi dù message hay tên class thay đổi.
2. **Duy nhất trong phạm vi danh mục:** không tái sử dụng cùng một mã cho hai sự kiện khác nghĩa.
3. **Không chứa dữ liệu của từng lần phát sinh:** không nhúng userId, email, orderId, thời gian hoặc tham số request vào mã.
4. **Có tên ngữ nghĩa đi kèm:** mã ngắn như `ORD-1500` có thể kết hợp `eventName=order.checkout.failed` để người đọc hiểu ngay.
5. **Quy định owner:** mỗi nhóm mã có người/nhóm chịu trách nhiệm định nghĩa, review và bảo trì.
6. **Không gắn mã với dòng source code:** refactor không nên phá dashboard và cảnh báo.
7. **Rõ ranh giới sự kiện:** chỉ định lúc nào mã được phát; nếu “checkout failed” có nghĩa là thất bại cuối cùng, không ghi mã đó mỗi lần retry tạm thời.
8. **Có hướng dẫn bảo mật:** mô tả field nào bắt buộc, field nào chứa dữ liệu nhạy cảm, có thể log ở mức nào và lưu giữ bao lâu.
9. **Có chính sách ngừng sử dụng:** mã đã deprecate không được âm thầm cấp lại cho ý nghĩa mới.
10. **Có quy tắc tương thích:** giữ cùng code cho cùng nghĩa; thay code hoặc tạo schemaVersion mới khi ý nghĩa/hợp đồng dữ liệu thay đổi không tương thích.

Một cách kiểm tra định dạng minh họa:

~~~regex
^(ORD|PAY|INF)-[0-9]{4}$
~~~

Regex chỉ kiểm tra **cú pháp**, không bảo đảm mã đã được đăng ký hoặc hợp lệ về ngữ nghĩa. Một registry/enum và CI test cần thực thi việc không trùng mã, đúng tên và đủ mô tả.

### 4.1. Nên dùng mã tự mô tả hay số?

- **Mã số có tiền tố:** gọn, dễ xử lý, ổn định, ví dụ `ORD-1500`. Nhược điểm là cần registry để biết ý nghĩa.
- **Tên ngữ nghĩa:** dễ đọc, ví dụ `order.checkout.failed`. Nếu dùng làm khóa duy nhất, đổi tên để “đẹp hơn” có thể gây breaking change.
- **Dùng cả hai:** một mã bất biến cho machine và một tên ngữ nghĩa rõ ràng cho người; nên bảo đảm cả hai tham chiếu cùng một định nghĩa trong registry.

Không có quy định Java nào bắt buộc phải dùng cả hai. Quan trọng là **hợp đồng mà ứng dụng và bên thu thập cùng hiểu và có kiểm thử**.

## 5. Danh mục mã sự kiện (event catalog) là nguồn sự thật

Đừng để mỗi lập trình viên tự tạo mã bằng cách nối chuỗi tại nơi ghi log. Nên duy trì một **event catalog** được quản lý cùng phiên bản sản phẩm hoặc một registry chung.

Ví dụ:

| eventCode | eventName | Khi nào phát | Mức mặc định | Field bắt buộc | Owner |
| --- | --- | --- | --- | --- | --- |
| `ORD-1001` | `order.checkout.started` | Khi checkout chính thức bắt đầu | INFO | `requestId`, `orderId` | Order |
| `ORD-1002` | `order.checkout.succeeded` | Khi checkout hoàn tất thành công | INFO | `requestId`, `orderId`, `durationMs` | Order |
| `ORD-1500` | `order.checkout.failed` | Khi checkout kết thúc bằng thất bại | ERROR | `requestId`, `orderId`, `error.type` | Order |
| `PAY-2001` | `payment.authorization.declined` | Khi nhận quyết định declined từ processor | WARN hoặc INFO theo tác động | `requestId`, `paymentAttemptId` an toàn | Payments |
| `INF-9001` | `infrastructure.dependency.unavailable` | Khi dependency cần thiết không dùng được | ERROR | `dependency`, `requestId` nếu có | Platform |

**Danh mục trên chỉ để thực hành.** Trước khi đưa vào hệ thống thật, người thiết kế cần xác định rõ trigger, ngữ nghĩa, trường dữ liệu, quy tắc chống trùng, cách log retry và runbook.

Một mục registry hoàn chỉnh có thể gồm:

~~~yaml
eventCode: ORD-1500
eventName: order.checkout.failed
description: Checkout kết thúc bằng thất bại sau khi các chính sách retry/fallback đã được áp dụng.
owner: order-platform
defaultLevel: ERROR
requiredAttributes:
  - requestId
  - orderId
  - outcome
  - error.type
optionalAttributes:
  - durationMs
  - dependency
  - traceId
outcome: failed
piiPolicy: Chỉ ghi định danh nội bộ được phép; không ghi token hay payload thanh toán.
runbook: docs/runbooks/order-checkout-failure.md
status: active
~~~

Đây là **schema YAML minh họa**, không phải file triển khai bắt buộc. Trường `runbook` là đường dẫn ví dụ trong một repository tưởng tượng, không khẳng định tệp đó tồn tại. Nếu tổ chức có hệ thống catalog riêng, dùng định dạng registry thực tế của tổ chức.

### Vì sao registry cần “khi nào phát”?

Giả sử checkout thử gọi inventory ba lần, hai lần đầu timeout và lần ba thành công. Nếu code phát `ORD-1500` cho **mỗi retry**, dashboard có thể đếm ba thất bại cuối cùng dù request đã thành công. Có thể dùng event riêng như `inventory.read.retry_scheduled` cho một lần thử tạm thời và chỉ dùng `ORD-1500` khi toàn bộ checkout thật sự thất bại.

Thống nhất **ý nghĩa của event** quan trọng hơn việc mã trông đẹp. Một mã ổn định nhưng phát sai thời điểm sẽ khiến số liệu giám sát sai lệch.

## 6. Schema log có cấu trúc và quy tắc field

Một event thường có nhóm trường sau:

| Trường | Kiểu gợi ý | Quy tắc |
| --- | --- | --- |
| `timestamp` | ISO-8601 UTC string / native timestamp | Thời điểm xảy ra sự kiện, timezone rõ |
| `level` | enum/string | Theo logging framework hoặc chuẩn ingest đã chọn |
| `service` | string | Tên service ổn định |
| `eventCode` | string | Giá trị từ catalog, cardinality thấp |
| `eventName` | string | Tên loại sự kiện đã đăng ký |
| `message` | string | Mô tả cho người, có thể thay đổi |
| `requestId` | string | ID an toàn để tương quan request |
| `traceId` / `spanId` | string | Nếu tracing được cấu hình |
| `operation` | string | Thao tác, giá trị từ tập có kiểm soát |
| `outcome` | string | `started`, `succeeded`, `failed` hoặc quy ước khác |
| `durationMs` | number | Đơn vị millisecond, không nhét “ms” vào số |
| `error.type` | string | Loại lỗi khi có failure |
| `error.message` / `stack_trace` | string | Chỉ khi cần và theo chính sách bí mật |
| `schemaVersion` | integer/string | Phiên bản hợp đồng cấu trúc |

Ví dụ log JSON có field riêng:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventCode": "ORD-1002",
  "eventName": "order.checkout.succeeded",
  "message": "Checkout completed",
  "requestId": "req-17",
  "traceId": "5dbf59d442a240a18cc82d48c2eb7e44",
  "operation": "checkout",
  "orderId": "O-42",
  "outcome": "succeeded",
  "durationMs": 42,
  "schemaVersion": 1
}
~~~

Đây là bản ghi mô tả **định dạng đích** chứ không phải output mặc định của `Logger.info(...)`. Nếu một layout chỉ tạo text chứa `eventCode=...`, pipeline cần parser để biến nó thành field. Với structured logging thực sự, ưu tiên encoder tạo JSON/NDJSON hoặc một format có cấu trúc được hệ thống thu thập hỗ trợ.

### 6.1. Tách schema version khỏi event code

Một trường mới `region` được thêm dưới dạng optional có thể giữ nguyên `eventCode` nếu loại sự kiện không đổi. Khi thay đổi một field từ số `durationMs` sang chuỗi `"42ms"`, bên đọc có thể bị phá; hãy dùng quy tắc schema evolution, version hoặc một field mới để tránh breaking change.

Không tạo mã `ORD-1500-v2` chỉ vì đổi tên trường hiển thị, trừ khi tổ chức quyết định đó là loại sự kiện mới có ý nghĩa khác.

### 6.2. Tên field phải nhất quán

`eventCode`, `event.code` và `event_code` không được tự coi là một field. Chọn một convention rồi áp dụng nhất quán qua service, indexer, dashboard và alert. Nếu collector yêu cầu mapping khác, hãy quy định rõ lớp chuyển đổi; không để mỗi service viết một tên tùy ý.

Ví dụ ở bài này dùng `eventCode`/`eventName` trong JSON minh họa. Các dự án dùng chuẩn bên ngoài có thể chọn những tên khác sau khi đã xác định mapping.

## 7. Java 17 chạy độc lập: catalog enum và JSON lines có eventCode

Trong JDK có `java.util.logging` (JUL), nhưng JUL **không cung cấp sẵn một tiêu chuẩn event code**. Ta có thể đặt danh mục bằng `enum` và viết `Formatter` tạo JSON Lines để minh họa cách một bản ghi có mã, tên, outcome, correlation ID và error type.

Ví dụ này chỉ dùng JDK 17; **không cần Maven hay thư viện bên ngoài**. Formatter tự viết chủ yếu để học cơ chế; hệ thống production nên dùng structured encoder/backend đã được kiểm chứng để xử lý timestamp, exception đầy đủ, Unicode, throughput và dữ liệu nhạy cảm.

Tạo tệp **StandardEventCodeDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class StandardEventCodeDemo {
    private static final Logger LOG =
            Logger.getLogger(StandardEventCodeDemo.class.getName());

    private StandardEventCodeDemo() {
    }

    private enum EventCode {
        CHECKOUT_STARTED(
                "ORD-1001", "order.checkout.started",
                "Checkout started", Level.INFO),
        CHECKOUT_SUCCEEDED(
                "ORD-1002", "order.checkout.succeeded",
                "Checkout succeeded", Level.INFO),
        CHECKOUT_FAILED(
                "ORD-1500", "order.checkout.failed",
                "Checkout failed", Level.SEVERE);

        final String code;
        final String name;
        final String message;
        final Level level;

        EventCode(String code, String name, String message, Level level) {
            this.code = code;
            this.name = name;
            this.message = message;
            this.level = level;
        }
    }

    private static String jsonString(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u");
                        for (int n = hex.length(); n < 4; n++) {
                            out.append('0');
                        }
                        out.append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class EventJsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] p = record.getParameters();
            EventCode event = (EventCode) p[0];
            String requestId = (String) p[1];
            String orderId = (String) p[2];
            String outcome = (String) p[3];

            StringBuilder out = new StringBuilder("{\"level\":");
            out.append(jsonString(record.getLevel().getName()));
            out.append(",\"eventCode\":").append(jsonString(event.code));
            out.append(",\"eventName\":").append(jsonString(event.name));
            out.append(",\"message\":").append(jsonString(record.getMessage()));
            out.append(",\"requestId\":").append(jsonString(requestId));
            out.append(",\"orderId\":").append(jsonString(orderId));
            out.append(",\"outcome\":").append(jsonString(outcome));

            if (record.getThrown() != null) {
                out.append(",\"errorType\":")
                   .append(jsonString(
                           record.getThrown().getClass().getSimpleName()));
            }
            return out.append("}\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new StreamHandler(
                System.out, new EventJsonFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    private static void emit(
            EventCode event, String requestId,
            String orderId, String outcome, Throwable cause) {
        LogRecord record = new LogRecord(event.level, event.message);
        record.setLoggerName(LOG.getName());
        record.setParameters(
                new Object[] {event, requestId, orderId, outcome});
        record.setThrown(cause);
        LOG.log(record);
    }

    public static void main(String[] args) {
        configureLogger();

        emit(EventCode.CHECKOUT_STARTED,
                "req-17", "O-42", "started", null);

        emit(EventCode.CHECKOUT_SUCCEEDED,
                "req-17", "O-42", "succeeded", null);

        emit(EventCode.CHECKOUT_FAILED,
                "req-18", "O-43", "failed",
                new IOException("store timeout"));
    }
}
~~~

### 7.1. Biên dịch và chạy

Trong thư mục chứa tệp trên:

~~~bash
javac -encoding UTF-8 StandardEventCodeDemo.java
java StandardEventCodeDemo
~~~

**Stdout chính xác từ formatter của ví dụ:**

~~~json
{"level":"INFO","eventCode":"ORD-1001","eventName":"order.checkout.started","message":"Checkout started","requestId":"req-17","orderId":"O-42","outcome":"started"}
{"level":"INFO","eventCode":"ORD-1002","eventName":"order.checkout.succeeded","message":"Checkout succeeded","requestId":"req-17","orderId":"O-42","outcome":"succeeded"}
{"level":"SEVERE","eventCode":"ORD-1500","eventName":"order.checkout.failed","message":"Checkout failed","requestId":"req-18","orderId":"O-43","outcome":"failed","errorType":"IOException"}
~~~

Đây là **ba JSON object riêng, mỗi object một dòng** (NDJSON/JSON Lines), không phải một JSON array chứa ba phần tử. `SEVERE` là tên mức nghiêm trọng của JUL; một hệ thống Logback/Log4j2 có thể gọi mức tương ứng là `ERROR`. Không đồng nhất tên level của các backend nếu chưa định nghĩa mapping.

Vì sao output dự đoán được?

1. `EventCode` là `enum`: ba mã, ba tên và ba message cố định, không được dựng từ các ID động.
2. `emit(...)` tạo `LogRecord` chứa message của event, level, parameters và Throwable tùy trường hợp.
3. `EventJsonFormatter` đọc `EventCode` từ `record.getParameters()` và xuất các key JSON theo thứ tự cố định.
4. Logger tắt parent handlers và chỉ thêm một `StreamHandler` đẩy tới stdout; handler `flush()` sau mỗi event.
5. Không có timestamp trong ví dụ để bảo đảm expected stdout ổn định; production nên có timestamp, logger/service, tracing context và nhiều thông tin chẩn đoán khác.
6. Sự kiện thất bại có `IOException` thật trong `record.getThrown()`, nhưng formatter minh họa chỉ in `errorType`, **không in stack trace hay cause**. Production cần layout/encoder giữ và bảo vệ các dữ liệu lỗi phù hợp.

**Hạn chế thực tế:** `jsonString(...)` là helper tối thiểu cho các chuỗi đầu vào hợp lệ trong demo; không thay thế một thư viện JSON production xử lý mọi trường hợp Unicode/surrogate không hợp lệ, format số/boolean và schema validation. Không tự viết serializer lớn chỉ để phục vụ logging ứng dụng nếu backend có encoder chuẩn.

### 7.2. Vì sao lưu eventCode trong enum?

So với:

~~~java
// Sai về quản trị mã: mỗi nơi tự ghép ra mã động.
LOG.info("eventCode=ORD-" + orderId + " checkout failed");
~~~

`enum EventCode` giúp mã được khai báo tập trung, liên kết `code` với `name`, `message` và mức mặc định, giảm lỗi gõ chữ và hạn chế tình trạng nhiều nơi cùng tên nhưng khác ý nghĩa.

Trong hệ thống có nhiều module/service, danh mục có thể được đưa thành thư viện chung, file registry hoặc cơ chế code generation. Tuy nhiên **không bắt mọi service phải deploy cùng một thư viện để đổi một câu message**; versioning và backward compatibility cần có chiến lược rõ.

## 8. SLF4J 2.x: truyền eventCode qua key/value

Ở một dự án dùng **SLF4J 2.x** và logging provider/backend phù hợp, fluent API có `addKeyValue(...)`:

~~~java
// Snippet trong một service có SLF4J Logger LOG và các biến tương ứng.
LOG.atInfo()
   .addKeyValue("eventCode", "ORD-1002")
   .addKeyValue("eventName", "order.checkout.succeeded")
   .addKeyValue("requestId", requestId)
   .addKeyValue("orderId", orderId)
   .addKeyValue("outcome", "succeeded")
   .log("Checkout succeeded");
~~~

Cách viết này có lợi hơn việc nhét toàn bộ metadata vào một chuỗi `"eventCode=... orderId=..."`, vì event builder truyền các cặp key/value ở tầng API.

**Nhưng `addKeyValue(...)` không tự tạo JSON.** Provider và encoder/layout phải thật sự đưa các field đó ra đích và giữ đúng kiểu. Nếu cấu hình chỉ in `%msg`, nhiều field key/value có thể không xuất ra. Các backend có khả năng structured logging/JSON encoder khác nhau; phải kiểm tra output thật và version hỗ trợ.

Một ví dụ thất bại:

~~~java
// Đoạn minh họa trong catch có Throwable e.
LOG.atError()
   .addKeyValue("eventCode", "ORD-1500")
   .addKeyValue("eventName", "order.checkout.failed")
   .addKeyValue("requestId", requestId)
   .setCause(e)
   .log("Checkout failed");
~~~

`setCause(e)` giữ đối tượng Throwable để backend có thể in stack trace/cause. Không thay bằng chỉ `e.getMessage()` nếu cần chẩn đoán lỗi. Khi có retry/fallback, chọn loại sự kiện đúng với **kết quả cuối** của thao tác thay vì phát mã failure cuối cùng cho mọi lần thử.

Một quy tắc code hữu ích: tách các eventCode thành enum/constants hoặc từ registry; **không copy literal** ở hàng trăm call site mà không có kiểm tra trùng/typo. Hai ví dụ trên dùng string trực tiếp để làm rõ API, nhưng thiết kế production nên liên kết với catalog.

## 9. Logback và Log4j2: làm sao giữ field thành dữ liệu có cấu trúc?

### 9.1. Logback

Logback Classic thường được dùng làm backend của SLF4J. Nó có encoder/layout và các công cụ mở rộng để xuất JSON; việc giữ các key/value từ SLF4J 2.x phụ thuộc phiên bản và encoder.

Nếu cấu hình text, có thể đưa mã sự kiện vào thông điệp có cấu trúc dễ đọc:

~~~text
INFO eventCode=ORD-1002 eventName=order.checkout.succeeded orderId=O-42 outcome=succeeded
~~~

Nhưng **text giống JSON chưa phải JSON**. Nếu cần truy vấn chính xác theo `eventCode`, dùng encoder hỗ trợ structured data hoặc có một parser đáng tin cậy ở collector. Không tuyên bố Logback mặc định tự tạo `eventCode` chỉ vì đã gọi `LOG.info(...)`.

Nếu dùng MDC để chèn mã vào pattern như `%X{eventCode}`, phải quản lý scope cẩn thận. **MDC là ngữ cảnh liên quan tới thread**, còn eventCode là thuộc tính của từng sự kiện; gán mã vào MDC rồi quên xóa có thể làm mã của event trước dính sang event sau. Với SLF4J 2.x, key/value gắn trực tiếp vào event thường rõ nghĩa hơn cho eventCode.

### 9.2. Log4j2

Log4j2 hỗ trợ các layout structured, trong đó **JSON Template Layout** cho phép định nghĩa schema và ánh xạ field. Đây là một khả năng của backend/encoder, không phải đặc tính tự phát sinh của `eventCode`.

Một snippet mô tả việc phát mã khi dùng Log4j API:

~~~java
// Đoạn minh họa trong lớp có Log4j2 Logger LOG, requestId và orderId.
LOG.info("eventCode={} eventName={} requestId={} orderId={}",
        "ORD-1002", "order.checkout.succeeded",
        requestId, orderId);
~~~

Đoạn này là **parameterized text message**, không tự tạo field `eventCode` trong JSON output. Để ra structured fields, dùng message/context API phù hợp rồi cấu hình JSON Template Layout với resolver/template đúng; tính năng cụ thể phụ thuộc thư viện/module và bản phát hành.

Có thể dùng template của `JsonTemplateLayout` để tạo field theo convention chung, nhưng cần kiểm tra rằng:

- Mọi service tạo eventCode hợp lệ.
- Encoder có thật sự xuất eventCode/eventName thành field độc lập.
- Collector không đổi tên/đánh kiểu field sai.
- Throwable, traceId và timestamp được encode đúng.
- Thứ tự các trường không được dùng như một hợp đồng nghiệp vụ; JSON object không đảm bảo thứ tự có ý nghĩa.

**Không đưa nguyên một ví dụ layout của Logback sang Log4j2** rồi kỳ vọng tên class/placeholder tương thích. API, dependency và cách cấu hình layout khác nhau.

## 10. Kết hợp với OpenTelemetry event semantics

OpenTelemetry mô tả **event** như một sự kiện được đặt tên, xảy ra tại một thời điểm có ý nghĩa, đi kèm attributes. Hướng dẫn semantic conventions nhấn mạnh **tên event ổn định, không chứa dữ liệu động**. Trong thiết kế nội bộ này, `eventName=order.checkout.failed` thể hiện loại event, còn `requestId` và `orderId` là attributes của lần phát sinh.

Cần phân biệt:

- `eventCode` trong bài này là **mã nội bộ** do tổ chức định nghĩa. Không được khẳng định OpenTelemetry hoặc SLF4J bắt buộc có field `eventCode`.
- `eventName` có thể ánh xạ sang cơ chế tên event của một SDK/tracing/logging system, nhưng cần kiểm tra đúng data model và mapping mà hệ thống dùng.
- Một **event** mô tả checkpoint/state change; một **span** phù hợp khi cần đo một operation có thời lượng và ranh giới. Không phải mọi log line đều là một OpenTelemetry event chính thức.
- `traceId` và `spanId` chỉ có ý nghĩa nếu thực sự có cơ chế tracing/context propagation; phát một chuỗi ngẫu nhiên không tự tạo distributed trace hợp lệ.

Các semantic conventions của OpenTelemetry có thể phát triển theo phiên bản. Khi tích hợp production, xem tài liệu hiện hành và chuẩn hóa tên field ở collector, thay vì tự đồng nhất tên nội bộ với tên bắt buộc của chuẩn bên ngoài.

## 11. Dùng mã sự kiện để tìm kiếm, đo lường và cảnh báo

### 11.1. Truy vấn theo mã

Giả sử collector lưu JSON có field `eventCode`. Một truy vấn **pseudocode**:

~~~text
WHERE service = "order-service"
  AND eventCode = "ORD-1500"
  AND timestamp >= now() - 15 minutes
GROUP BY environment, errorType
~~~

Đây không phải cú pháp chung cho mọi sản phẩm log analytics. Mỗi backend có query language, field indexing và hàm thời gian riêng. Ưu điểm là cùng một mã có thể được nhóm dù message thay đổi.

### 11.2. Alert nên xét tần suất và tác động

Không nên đặt alert paging chỉ vì một event `PAY-2001` xuất hiện nếu đó có thể là trường hợp declined bình thường. Cần định nghĩa rõ tín hiệu:

- Số sự kiện `ORD-1500` trên phút tăng vượt ngưỡng.
- Tỷ lệ `ORD-1500` / số checkout kết thúc tăng, thay vì chỉ đếm số lượng tuyệt đối khi traffic thay đổi.
- `INF-9001` liên tục vượt ngưỡng và ảnh hưởng nhiều request.
- Một mã quan trọng **không xuất hiện** khi đáng ra phải có (ví dụ thiếu event completion), nhưng phải hiểu tác động sampling và lọc log.

**Quan trọng:** nếu log có thể bị drop trong async queue, sampling hoặc mất trên đường collector, đếm log không phải số giao dịch tuyệt đối. Với SLO/kinh doanh, kết hợp metrics/traces và nguồn dữ liệu đáng tin cậy. Event code giúp truy vấn chính xác hơn nhưng không tự bảo đảm delivery.

### 11.3. Cardinality phải kiểm soát

`eventCode` nên là trường có tập giá trị hữu hạn được quản lý, thích hợp để group. Nhưng `requestId`, `orderId`, `exceptionMessage` hoặc giá trị URL động có cardinality cao; không đưa trực tiếp vào **eventCode**, cũng không mặc định biến chúng thành nhãn metrics nếu gây bùng nổ series.

Một enum cố định gồm vài trăm event code khác với việc tạo code từ mỗi user ID. Việc định nghĩa mã quá chi tiết theo từng tham số có thể làm catalog phình to và khiến dashboard khó dùng.

## 12. Quy trình quản trị và phát triển danh mục mã

### Đăng ký một sự kiện mới

1. **Xác định mục tiêu:** sự kiện được dùng để debug, audit, alert hay đo hành trình nghiệp vụ?
2. **Kiểm tra catalog:** đã có mã nào biểu diễn cùng ngữ nghĩa chưa? Không tạo hai mã chỉ vì hai nhóm thích đặt tên khác.
3. **Chọn domain và code chưa dùng:** ví dụ `ORD-1501`, không tái sử dụng mã cũ.
4. **Đặt tên ngữ nghĩa:** ví dụ `order.checkout.rejected_by_policy`; không chứa ID động.
5. **Viết trigger rõ:** khi nào được phát, trước/sau commit, trước/sau retry, chỉ một lần hay mỗi attempt?
6. **Định nghĩa field:** kiểu dữ liệu, required/optional, đơn vị, giới hạn kích thước và chính sách bảo mật.
7. **Chọn level mặc định:** dựa trên tác động, không chỉ vì tên có chữ “error”.
8. **Gắn owner và runbook:** ai xử lý khi mã tăng đột biến, cách xác minh/khôi phục.
9. **Thêm test:** unique code, pattern hợp lệ, schema, mapping lên JSON, sự kiện được phát đúng giai đoạn.
10. **Cập nhật dashboard/alert có kiểm soát:** bảo đảm mã mới được index và người trực có thông tin cần thiết.

### Thay đổi một mã đã được sử dụng

- **Đổi message/format trình bày:** thường có thể giữ code nếu ý nghĩa sự kiện không đổi.
- **Thêm field optional:** thường tương thích nếu consumer có thể bỏ qua field chưa biết.
- **Đổi field required, kiểu hoặc nghĩa:** đánh giá schemaVersion, migration và consumer.
- **Đổi ngữ nghĩa của event:** tạo mã mới; deprecate mã cũ với thời điểm/chính sách rõ ràng.
- **Gộp hoặc tách event:** cập nhật catalog và các truy vấn dùng mã cũ; tránh silent break.
- **Ngừng phát mã:** đánh dấu deprecated/retired; không cấp lại cho một sự kiện mới.

Một thay đổi **mã sự kiện đã tồn tại** có thể là breaking change với dashboard, alert, data pipeline và runbook. Cần review kỹ như đổi public API hoặc contract dữ liệu.

## 13. Bảo mật và quyền riêng tư

Event code không được chứa secret; nhưng event **có nhiều field khác** có thể chứa thông tin nhạy cảm. Các quy tắc:

1. Không đưa password, access token, cookie, API key hoặc nội dung thanh toán vào `message`/`attributes`.
2. Không lấy email, số điện thoại, số thẻ hoặc tên người dùng làm một phần của `eventCode`. Nếu cần tương quan, sử dụng ID nội bộ an toàn theo chính sách dữ liệu.
3. Tránh log toàn bộ request/response body và đối tượng Java lớn; chỉ chọn field cần điều tra.
4. Dùng JSON encoder có escaping đúng cho newline và ký tự điều khiển, tránh log forging.
5. Với Throwable, giữ nguyên nhân khi cần chẩn đoán nhưng hạn chế lộ stack trace và endpoint/SQL/private path ra response công khai.
6. Đặt quyền truy cập, retention và bảo vệ dữ liệu cho cả console, file, archive, collector và backup.
7. Định nghĩa danh sách field có thể ghi cho mỗi mã; đừng để một schema mở tự động serialize mọi thuộc tính của object.

Một sự kiện `ORD-1500` được đặt mã “đúng chuẩn” vẫn có thể là một log nguy hiểm nếu `message` chứa session token. **Mã chuẩn giúp định danh, không tự thực hiện masking/redaction.**

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghép mã với orderId/requestId | Mỗi event sinh mã mới, mất khả năng group | Đặt ID động trong field riêng |
| Dùng message làm khóa cảnh báo | Đổi câu chữ làm gãy rule | Group theo eventCode/eventName ổn định |
| Tự copy literal mã khắp nơi | Typo và mã trùng nghĩa | Dùng catalog, enum/constants, CI |
| Ghi `ORD-1500` cho mọi retry | Dashboard hiểu nhầm số lần thất bại cuối cùng | Xác định rõ trigger và event cho attempt |
| Đổi ý nghĩa nhưng giữ mã | Consumer cũ hiểu sai dữ liệu | Tạo mã mới và version/migrate |
| Tái sử dụng mã đã deprecated | Log lịch sử và log mới lẫn nhau | Không tái sử dụng mã |
| Nhầm eventCode với HTTP errorCode | Trả dữ liệu nội bộ hoặc mapping sai | Tách contract API và log, định nghĩa ánh xạ |
| Chỉ thêm `eventCode=...` vào text | Collector không tự có field structured | Dùng encoder/schema hoặc parser được kiểm thử |
| `LOG.atInfo().addKeyValue(...)` nhưng không `log(...)` | Không phát sự kiện | Kết thúc fluent chain bằng `log()` |
| Formatter bỏ Throwable | Mất stack trace/cause trên output | Dùng encoder hỗ trợ error attributes theo policy |
| Thiếu requestId/traceId | Không nối được sự kiện về request | Thêm correlation field an toàn, propagate context |
| Dùng mã code làm metric label nhưng lại gắn ID động | Bùng nổ cardinality | Dùng tập mã cố định/đã đăng ký |
| Log cùng một sự kiện ở nhiều tầng | Đếm trùng và nhiễu | Chọn ranh giới phát event rõ |
| Gán eventCode vào MDC không dọn | Sự kiện sau mang mã cũ | Gắn field per-event hoặc dọn scope ở `finally` |
| Quên schemaVersion khi breaking change | Parser/dashboard sai hoặc mất field | Quản trị schema evolution và migration |

## 15. Checklist kiểm tra một hệ thống event code

Trước khi đưa vào production, hãy xác minh:

- **Catalog:** mỗi mã có một ý nghĩa, không trùng, không chứa dữ liệu động, có owner và trigger rõ.
- **Naming:** eventName dễ hiểu, nhất quán theo domain và hành động/điểm chuyển trạng thái.
- **Schema:** eventCode, eventName, level, timestamp, service, outcome và field bắt buộc có đúng kiểu.
- **Emission:** code phát đúng lúc, không bị log nhầm cho retry tạm thời hoặc bị phát hai lần cùng một kết quả.
- **Error handling:** Throwable được giữ theo policy; API response không lộ dữ liệu nội bộ.
- **Structured encoder:** collector thật sự nhận eventCode là field, không phải chuỗi không được parse.
- **Correlation:** requestId/traceId được truyền đúng qua thread/async và được dọn sau xử lý.
- **Privacy:** không có secret/PII không cần thiết; dữ liệu được escape và có retention.
- **Monitoring:** dashboard/alert truy vấn theo mã, nhưng hiểu giới hạn do sampling/drop.
- **Backward compatibility:** có test cho mã, field bắt buộc, deprecation và thay đổi version.
- **Hiệu năng:** đo log events/s, bytes/s, allocations/GC và latency ở workload thực.
- **Runbook:** mã có đường dẫn tra cứu cách xử lý; khi alert nổ, người trực hiểu hành động tiếp theo.

## 16. Bài tập thực hành

1. **Phân biệt:** cho `ORD-1500`, `order.checkout.failed`, `ERROR`, `requestId=req-17` và `HTTP 503`; xác định cái nào là eventCode, eventName, severity, correlation ID và API status.
2. **Thiết kế catalog:** tạo ít nhất bốn mã cho vòng đời của một job nhập dữ liệu: started, progress checkpoint quan trọng, succeeded và failed. Mỗi mã phải có trigger và required fields.
3. **Chạy JDK 17:** tạo `StandardEventCodeDemo.java`; đối chiếu ba dòng NDJSON theo expected stdout. Vì sao mã `ORD-1500` không chứa `O-43`?
4. **Thêm sự kiện:** bổ sung một enum `CHECKOUT_CANCELLED` với mã mới, tên riêng và outcome phù hợp. Kiểm tra nó không trùng code và không thay nghĩa mã cũ.
5. **SLF4J 2.x:** chuyển một log text `"Checkout succeeded"` sang fluent API có `eventCode`, `eventName`, `requestId` và `outcome`. Giải thích vì sao backend/encoder vẫn cần hỗ trợ key/value.
6. **Kiểm thử schema:** viết assertion cho trường `eventCode` đúng pattern, `durationMs` là number và `requestId` không rỗng. Kiểm tra consumer khi xuất hiện field optional mới.
7. **Retry:** một checkout có hai lần timeout rồi lần ba thành công. Sự kiện `ORD-1500` nên có được phát không nếu nó được định nghĩa là thất bại cuối cùng?
8. **Dashboard:** tính tỷ lệ checkout thất bại từ các sự kiện outcome cuối cùng; chỉ ra điều gì sai nếu vừa đếm retry vừa đếm failure cuối.
9. **Cardinality:** nếu tạo eventCode bằng cách nối mã với một triệu requestId, group-by eventCode sẽ có bao nhiêu khóa? Vì sao không phù hợp cho alert?
10. **Bảo mật:** một eventCode chuẩn nhưng message chứa token. Đề xuất thay đổi ở nguồn phát, encoder và quyền truy cập để giảm rủi ro.
11. **Versioning:** một đội đổi `durationMs` thành `duration` với kiểu chuỗi. Nêu cách migration mà không phá dashboard và cách giữ eventCode nếu ý nghĩa không đổi.

## 17. Tài liệu tham khảo

- SLF4J Manual — Fluent Logging API: https://slf4j.org/manual.html
- Apache Log4j 2 — Layouts và structured logging: https://logging.apache.org/log4j/2.x/manual/layouts.html
- Apache Log4j 2 — JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- OpenTelemetry — Semantic conventions for events: https://opentelemetry.io/docs/specs/semconv/general/events/
- Java SE 17 — `java.util.logging`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html

**Ghi nhớ:** mã sự kiện chuẩn là **định danh bất biến của một loại event đã được mô tả trong catalog**, không phải log level, message, errorCode công khai hay request ID. Muốn structured logging thực sự, hãy xuất mã vào **field có cấu trúc**, giữ schema và ý nghĩa ổn định, định nghĩa trigger/owner/required attributes, kiểm soát bảo mật và kiểm thử cả đường ingest. Mã tốt khiến hệ thống dễ truy vấn, cảnh báo và điều tra **ngay cả khi câu message hoặc cách triển khai Java thay đổi**.