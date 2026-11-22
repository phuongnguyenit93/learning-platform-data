# Phân tích log theo trace

## 1. Mục tiêu và bài toán

Trong ứng dụng Java gồm nhiều thành phần, một yêu cầu có thể đi qua API, dịch vụ nghiệp vụ, cơ sở dữ liệu, hàng đợi và dịch vụ bên ngoài. Khi yêu cầu thất bại, mỗi thành phần thường ghi log riêng. Đọc từng file log theo thứ tự xuất hiện dễ bỏ sót nguyên nhân vì các yêu cầu khác đang chạy xen kẽ.

**Phân tích log theo trace** là tìm các bản ghi thuộc cùng một luồng xử lý, ghép chúng với thông tin span và thời gian, rồi đối chiếu với distributed tracing để trả lời:

- Yêu cầu bắt đầu tại đâu, đi qua dịch vụ nào và kết thúc thế nào?
- Lỗi được ghi nhận lần đầu ở thao tác nào? Lỗi nào chỉ là hậu quả của lỗi trước?
- Có retry, timeout, xử lý bất đồng bộ hoặc nhánh song song nào?
- Chứng cứ nào từ log, span, metric và mã nguồn đủ để kết luận nguyên nhân?

Mục tiêu không phải chỉ gom mọi dòng có cùng mã định danh: một trace có thể chứa nhiều span, nhiều nhánh và nhiều lỗi thứ cấp. Cần phân biệt **tương quan** (cùng luồng xử lý) với **quan hệ nhân quả** (thao tác nào thực sự dẫn tới lỗi).

## 2. Trace, span và bản ghi log liên hệ thế nào?

- **Trace** biểu diễn toàn bộ hoặc một phần hành trình của một thao tác xuyên các thành phần. `trace_id` định danh trace, thường là 16 byte / 32 ký tự hex trong ngữ cảnh W3C Trace Context.
- **Span** biểu diễn một đơn vị công việc có điểm bắt đầu/kết thúc, thuộc tính, trạng thái và có thể có quan hệ cha–con. `span_id` thường là 8 byte / 16 ký tự hex. Nhiều span cùng chia sẻ một `trace_id`.
- **Log event** là ghi nhận tại một thời điểm về trạng thái/sự kiện. Nếu được gắn `trace_id` và `span_id` từ ngữ cảnh đang hoạt động, log có thể nối với trace/span tương ứng.
- **Parent span** xác định quan hệ cha–con trong dữ liệu trace. `parent_span_id` trong log là thuộc tính bổ sung nếu hệ thống tự ghi; không phải mọi định dạng log đều có sẵn trường đó.
- **Request ID** thường do ứng dụng/gateway tự phát sinh; nó có thể tương quan với một request nhưng không thay thế được `trace_id` khi công việc đi qua nhiều dịch vụ hoặc message.

Ví dụ, HTTP `POST /checkout` có một span phía `checkout-api` và một span phía `payment-service`. Hai span có `span_id` khác nhau, cùng `trace_id`. Log của hai dịch vụ có thể được tìm chung bằng `trace_id`; muốn hiểu thao tác nào gọi thao tác nào, tiếp tục đối chiếu span cha–con và mốc thời gian.

Một trace được lấy mẫu để xuất sang tracing backend **không đồng nghĩa** mọi log của nó đều đã được lưu; ngược lại, thiếu trace trong tracing backend **không chứng minh** log có `trace_id` là sai. Sampling, retention, cấu hình thu thập và độ trễ xuất dữ liệu là các cơ chế riêng.

## 3. Các trường cần có để phân tích hiệu quả

| Trường | Ý nghĩa khi điều tra | Điểm cần kiểm tra |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện theo đồng hồ nguồn | Có múi giờ, độ chính xác và đồng bộ đồng hồ hay không |
| `service.name` / `service` | Dịch vụ phát log | Tên ổn định giữa các bản triển khai |
| `trace_id` | Ghép bản ghi xuyên dịch vụ | Đúng định dạng, được truyền qua ranh giới dịch vụ |
| `span_id` | Nối log với thao tác cụ thể | Phải lấy từ span đang hoạt động, không tự gán ngẫu nhiên |
| `severity` / `level` | Lọc lỗi, cảnh báo, thông tin | Không dùng `ERROR` đơn lẻ để kết luận nguyên nhân |
| `message` / `event.name` | Diễn biến và điểm thất bại | Nên có sự kiện rõ nghĩa, dễ tìm |
| `error.type`, `exception.type` | Phân loại lỗi | Giữ nguyên loại lỗi; stack trace có thể nằm ở trường riêng |
| `duration_ms`, `http.response.status_code` | Đối chiếu độ trễ và kết quả | Phân biệt thời gian tác vụ với khoảng cách giữa hai dòng log |
| `parent_span_id`, `operation` | Bổ sung quan hệ và chức năng | Tùy hệ thống có ghi hay không |
| `deployment.environment`, `service.version` | Khoanh vùng môi trường và phiên bản | Rất hữu ích khi lỗi chỉ xảy ra sau triển khai |

Dùng **log có cấu trúc** (ví dụ JSONL, mỗi dòng là một JSON object) để truy vấn ổn định. Thống nhất tên trường giữa ứng dụng, collector và công cụ tìm kiếm. Trong OpenTelemetry, `trace_id`/`span_id` có vị trí trong mô hình LogRecord; tên trường hiển thị trong công cụ lưu trữ có thể được ánh xạ khác đi. Không giả định mọi log framework Java tự động đính kèm trace context.

## 4. Ví dụ: dựng lại một yêu cầu bị lỗi

Giả sử các dịch vụ xuất các sự kiện sau; mọi mốc thời gian đều ở UTC. Cột `parent_span_id` thể hiện quan hệ được cung cấp từ hệ thống quan sát, không phải quan hệ suy ra chỉ bằng việc sắp xếp dòng.

| UTC | Service | Span | Parent span | Sự kiện |
| --- | --- | --- | --- | --- |
| 02:00:00.010 | `checkout-api` | `00f067aa0ba902b7` | — | Nhận `POST /checkout` |
| 02:00:00.030 | `payment-service` | `b7ad6b7169203331` | `00f067aa0ba902b7` | Bắt đầu yêu cầu thanh toán |
| 02:00:02.032 | `payment-service` | `b7ad6b7169203331` | `00f067aa0ba902b7` | Lỗi timeout từ payment gateway |
| 02:00:02.044 | `checkout-api` | `00f067aa0ba902b7` | — | Checkout thất bại |

Tất cả cùng có:

```text
trace_id = 4bf92f3577b34da6a3ce929d0e0e4736
```

Cách đọc có cơ sở:

1. Span phía `checkout-api` nhận yêu cầu; sau đó span phía `payment-service` được gọi.
2. `payment-service` ghi nhận timeout trước khi `checkout-api` ghi lỗi cuối cùng. Log ở checkout **có thể là hậu quả** của lỗi thanh toán.
3. Khoảng hơn 2 giây giữa log bắt đầu thanh toán và log timeout **không tự động là thời lượng span chính xác**. Muốn kết luận thời gian thực thi, kiểm tra span start/end, đồng hồ giữa dịch vụ và các lần retry.
4. Nguyên nhân gần nhất có chứng cứ là **timeout quan sát tại `payment-service`**. Cần kiểm tra thêm span gọi gateway, retry, trạng thái kết nối, timeout configuration và log/metric của gateway trước khi kết luận vì sao gateway chậm.

Ví dụ cho thấy thứ tự log giúp đặt giả thuyết, còn quan hệ span và chứng cứ bổ sung giúp kiểm tra giả thuyết đó.

## 5. Quy trình điều tra một trace từ đầu đến cuối

### Bước 1 — Lấy dấu vết từ sự kiện đầu vào

Bắt đầu từ mã lỗi, cảnh báo, phản hồi API, thời điểm, môi trường và `trace_id` trong log hoặc response header (nếu hệ thống chủ động trả về). Đừng tìm theo mỗi thông điệp chung chung như “request failed”: điều đó thường trộn nhiều yêu cầu.

Kiểm tra `trace_id` có dạng hợp lệ, có bị cắt chuỗi, thay ký tự, đổi tên trường hoặc sinh mới giữa các dịch vụ hay không. Theo W3C Trace Context, trace-id 16 byte và parent-id 8 byte không được toàn số 0. Một trace ID nhìn hợp lệ vẫn chưa đảm bảo luồng propagation đúng.

### Bước 2 — Truy vấn toàn bộ dịch vụ trong khoảng thời gian hợp lý

Tìm **đúng `trace_id`** trên tập log có cùng môi trường và khoảng thời gian quanh sự cố. Tùy nền tảng (Loki, Elasticsearch/OpenSearch, Cloud Logging, v.v.), cú pháp khác nhau; ví dụ dưới đây là *truy vấn minh họa*, không phải cú pháp dùng chung cho mọi công cụ:

```text
trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
sort timestamp ascending
show timestamp, service, span_id, severity, message
```

Kiểm tra các dịch vụ được kỳ vọng tham gia có xuất hiện hay không. Nếu thiếu một dịch vụ, xem lại propagation, collector, bộ lọc severity, retention và logging khi xử lý bất đồng bộ; đừng vội kết luận dịch vụ đó không được gọi.

### Bước 3 — Dựng dòng thời gian và phân nhóm span

- Sắp xếp bằng **event timestamp**, đồng thời để ý **ingest timestamp** nếu pipeline nhận log muộn hoặc không theo thứ tự.
- Nhóm theo `service` rồi `span_id`; đối chiếu tên thao tác, start/end, trạng thái và quan hệ parent/child trên tracing backend.
- Đánh dấu thời điểm nhận request, gọi dependency, retry, timeout, exception được ném, exception được bắt và phản hồi cuối.
- Nếu có nhánh song song, vẽ riêng từng nhánh; hai dòng log đứng liền nhau không mặc nhiên là quan hệ gọi–trả.
- Với luồng Kafka/message queue, tìm trace context trong **message headers** tại producer và consumer, cùng thông tin message ID để hiểu quá trình enqueue, delay, redelivery và xử lý.

### Bước 4 — Phân biệt lỗi gốc với lỗi lan truyền

Ví dụ: `payment-service` ghi `SocketTimeoutException`; `checkout-api` sau đó ghi `PaymentFailedException`. Lỗi checkout có thể chỉ là biểu hiện của timeout phía dưới. Ngược lại, nếu checkout gửi tham số sai, lỗi validation ở payment mới có thể là hậu quả của lỗi từ checkout. Kiểm tra stack trace, mã lỗi trả về, các span liên quan và mã nguồn.

Không quy mọi `ERROR` về “root cause”. Có những log lỗi dự kiến của nhánh retry, circuit breaker hoặc nghiệp vụ; cũng có vấn đề nghiêm trọng chỉ được ghi `WARN`/metric.

### Bước 5 — Kiểm tra giả thuyết và phạm vi ảnh hưởng

So khớp trace lỗi với trace thành công cùng endpoint/phiên bản, so sánh độ trễ mỗi span, tần suất retry và sự thay đổi sau deploy. Dùng metric cho câu hỏi tổng thể như tỷ lệ lỗi, p95/p99 hoặc saturation; trace/log cho chi tiết của một yêu cầu. Lưu kết luận gồm **chứng cứ**, **điểm chưa chắc chắn**, **thao tác khắc phục** và cách xác minh sau khắc phục.

## 6. Truy vấn log JSONL thực tế

Giả sử các file `app-*.jsonl` chứa mỗi dòng một object với các khóa `timestamp`, `service`, `trace_id`, `span_id`, `severity`, `message`. Nếu máy có `jq` và các timestamp ISO 8601 đều chuẩn hóa về UTC, có thể lọc và sắp xếp:

```bash
TRACE_ID='4bf92f3577b34da6a3ce929d0e0e4736'
jq -r --arg trace "$TRACE_ID" \
  'select(.trace_id == $trace) |
   [.timestamp, .service, .severity, .span_id, .message] |
   @tsv' app-*.jsonl | sort
```

`jq` xử lý log JSON, còn `sort` ở đây dùng được vì cột đầu là timestamp UTC cùng định dạng. Nếu timestamp khác timezone/format, phải parse và chuẩn hóa trước khi sắp xếp. Log nhiều dòng như stack trace nên được collector đóng gói thành **một sự kiện có cấu trúc**; dùng `grep` trần có thể tách rời các dòng thuộc một exception.

Ví dụ tìm lỗi trong cùng trace có thể thêm điều kiện:

```text
trace_id = "<trace cần điều tra>" AND severity IN ("ERROR", "FATAL")
```

Đừng chỉ xem ERROR: các log INFO/WARN trước lỗi, nhánh retry và trạng thái downstream thường giải thích vì sao lỗi xảy ra.

## 7. Ví dụ Java 17: lọc và sắp xếp log của một trace

Chương trình dưới đây tự chạy bằng JDK 17+, không yêu cầu thư viện ngoài. Dữ liệu log được mô phỏng trong bộ nhớ để tập trung vào thao tác lọc `trace_id` và sắp xếp theo sự kiện. Dữ liệu thực tế có thể được lấy từ JSONL, hệ thống tìm kiếm hoặc collector.

Lưu thành **`TraceLogAnalyzer.java`**:

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public class TraceLogAnalyzer {
    record Event(
            Instant timestamp,
            String service,
            String traceId,
            String spanId,
            String level,
            String message) {
    }

    public static void main(String[] args) {
        String target = "4bf92f3577b34da6a3ce929d0e0e4736";
        String other = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

        // Cố ý để các sự kiện không theo thứ tự thời gian.
        List<Event> events = List.of(
            new Event(Instant.parse("2026-11-10T02:00:02.032Z"),
                "payment-service", target, "b7ad6b7169203331",
                "ERROR", "Gateway timeout"),
            new Event(Instant.parse("2026-11-10T02:00:00.010Z"),
                "checkout-api", target, "00f067aa0ba902b7",
                "INFO", "POST /checkout accepted"),
            new Event(Instant.parse("2026-11-10T02:00:00.015Z"),
                "checkout-api", other, "1111111111111111",
                "INFO", "Unrelated request"),
            new Event(Instant.parse("2026-11-10T02:00:00.030Z"),
                "payment-service", target, "b7ad6b7169203331",
                "INFO", "Charge requested"),
            new Event(Instant.parse("2026-11-10T02:00:02.044Z"),
                "checkout-api", target, "00f067aa0ba902b7",
                "ERROR", "Checkout failed")
        );

        events.stream()
            .filter(event -> target.equals(event.traceId()))
            .sorted(Comparator.comparing(Event::timestamp)
                .thenComparing(Event::service))
            .forEach(event -> System.out.println(
                event.timestamp() + " | " + event.service()
                + " | " + event.level()
                + " | span=" + event.spanId()
                + " | " + event.message()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TraceLogAnalyzer.java
java TraceLogAnalyzer
```

Kết quả chuẩn:

```text
2026-11-10T02:00:00.010Z | checkout-api | INFO | span=00f067aa0ba902b7 | POST /checkout accepted
2026-11-10T02:00:00.030Z | payment-service | INFO | span=b7ad6b7169203331 | Charge requested
2026-11-10T02:00:02.032Z | payment-service | ERROR | span=b7ad6b7169203331 | Gateway timeout
2026-11-10T02:00:02.044Z | checkout-api | ERROR | span=00f067aa0ba902b7 | Checkout failed
```

Cần hiểu đúng giới hạn ví dụ: lọc và sắp xếp log **chưa dựng được cây span** vì record `Event` không chứa đầy đủ thông tin parent–child hoặc start/end. Trong hệ thống thực, ghép với trace backend bằng cặp `trace_id` + `span_id`, thay vì đoán quan hệ chỉ từ thứ tự timestamp.

## 8. Liên kết log Java với OpenTelemetry

Trong ứng dụng Java có OpenTelemetry, instrument HTTP server/client, JDBC và messaging phù hợp để tạo/nhận context, sau đó cấu hình bridge để chuyển trace/span ID vào log. Ví dụ với SLF4J/Logback, bridge có thể chèn `trace_id` và `span_id` vào MDC hoặc xuất trực tiếp các trường tương quan theo OTLP; **cấu hình cụ thể phụ thuộc phiên bản và cách triển khai instrumentation**.

Luồng thông thường:

```text
HTTP/gRPC/message nhận context
          ↓
Trích xuất trace context → span hiện hành
          ↓
Business code ghi log có trace_id/span_id
          ↓
Logger / collector chuẩn hóa log
          ↓
Log backend truy vấn theo trace_id
          ↕
Tracing backend mở chi tiết span cùng trace_id
```

W3C `traceparent` có dạng:

```text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Các phần tương ứng gồm phiên bản, trace-id, parent-id và trace-flags. Giá trị `01` đặt cờ sampled trong ví dụ; **không** có nghĩa mọi log chắc chắn được lưu hoặc mọi span chắc chắn xuất thành công. Khi outbound request tạo span con, `parent-id` trong header truyền đi thường là ID của span outbound hiện tại.

Nếu phải gắn MDC thủ công, cần lấy ID từ **span context đang hoạt động**, kiểm tra context hợp lệ, và bảo đảm cleanup/restore bằng `try/finally` hoặc cơ chế đóng scope. MDC thường gắn với thread; truyền request sang `Executor`, `CompletableFuture` hoặc reactive pipeline mà không truyền context đúng cách sẽ gây **mất ID hoặc gắn nhầm trace giữa hai request**. Nên ưu tiên integration/instrumentation được hỗ trợ và kiểm tra log thực tế, thay vì tự tạo một `trace_id` cho từng dòng.

Không đưa secret, Authorization header, cookie, token thanh toán hoặc nội dung cá nhân nhạy cảm vào log chỉ để dễ ghép trace. `trace_id` là khóa điều tra có tính phân biệt cao; áp dụng quyền truy cập, retention và quy tắc dữ liệu phù hợp.

## 9. Các tình huống dễ chẩn đoán sai

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Chỉ thấy log của API, thiếu service downstream | Không propagate context, đổi tên trường, collector lọc log | Kiểm tra inbound/outbound context và log ngay sát ranh giới |
| Một request chứa nhiều `trace_id` | Tạo trace mới sai chỗ, context bị mất trong async/message | Đối chiếu traceparent và instrumentation mỗi hop |
| Log của hai request bị lẫn ID | MDC không cleanup, tái sử dụng thread | Kiểm tra restore/clear MDC, test concurrency |
| Có log với `trace_id` nhưng không mở được trace | Sampling, exporter lỗi, backend chưa nhận hoặc retention khác nhau | Kiểm tra sampling/export pipeline và khoảng thời gian |
| Timestamp log ngược với quan hệ gọi–trả | Lệch đồng hồ, log buffering, ingestion chậm | So thời gian của span và event/ingest timestamp |
| Có nhiều ERROR trong một trace | Lỗi bị wrap/propagate hoặc retry nhiều lần | Tìm lỗi sớm nhất *có quan hệ nhân quả*, không chỉ dòng ERROR đầu |
| Span không có log nhưng được đánh dấu lỗi | Level filter, instrumentation không phát log, không giữ dữ liệu | Mở event/status của span, không mặc định có log tương ứng |
| Message consumer có trace khác producer | Context không được ghi/đọc từ message headers | Kiểm tra encode/decode context, retry, dead-letter queue |
| Trace quá dài, tìm kiếm chậm | Nhiều span/log hoặc truy vấn không giới hạn | Khoanh thời gian, service, event rồi mở rộng có chủ đích |

**Đặc biệt với xử lý bất đồng bộ:** một trace có thể có quan hệ theo span links thay vì cây cha–con trực tiếp. Có thể một message được xử lý theo trace mới nhưng vẫn mang liên kết tới context nguồn; việc kết luận “mất liên kết” phải dựa trên dữ liệu spans/links thực tế.

## 10. Cách viết kết luận điều tra có thể kiểm chứng

Một báo cáo điều tra nên trả lời rõ:

1. **Phạm vi:** môi trường, phiên bản, endpoint/consumer, khoảng thời gian, một hoặc vài `trace_id` tiêu biểu.
2. **Dòng thời gian:** mốc nhận request, span/downstream liên quan, mốc lỗi và response cuối, kèm timezone.
3. **Chứng cứ:** đoạn log ngắn có `trace_id`/`span_id`, exception gốc, span status/duration và metric cho mức độ ảnh hưởng.
4. **Giả thuyết và mức độ chắc chắn:** yếu tố nào đã chứng minh, yếu tố nào vẫn cần log/trace từ dependency khác.
5. **Hành động:** sửa propagation/instrumentation nếu thiếu dữ liệu; sửa logic hoặc cấu hình dependency nếu có chứng cứ; xác minh bằng request tái hiện và so sánh trace trước–sau.

Ví dụ kết luận hợp lý: “Trong trace `4bf92f…`, `payment-service` ghi `Gateway timeout` lúc 02:00:02.032Z; `checkout-api` ghi `Checkout failed` lúc 02:00:02.044Z. Span thanh toán là nhánh đáng điều tra đầu tiên. Chưa đủ dữ liệu để khẳng định gateway lỗi hay timeout phía client quá thấp; cần đối chiếu thời lượng span HTTP client, số lần retry và metric của gateway.”

Đó là kết luận tốt hơn việc chỉ ghi “checkout lỗi vì payment”: nó chỉ ra được chứng cứ, ranh giới hiểu biết và phép kiểm tra tiếp theo.

## 11. Checklist trước khi coi phân tích là hoàn tất

- Có đúng `trace_id` và khoảng thời gian, đã tìm qua các dịch vụ thực sự tham gia.
- Đã phân biệt `span_id`, request ID, message ID; kiểm tra context qua HTTP và messaging nếu có.
- Đã sắp xếp sự kiện theo timestamp chuẩn hóa và tính đến lệch đồng hồ/log đến muộn.
- Đã đối chiếu span parent/child hoặc links; không suy quan hệ nhân quả chỉ từ thứ tự log.
- Đã phân biệt lỗi khởi phát với lỗi được wrap, propagate hoặc ghi lặp khi retry.
- Đã kiểm tra sampling, retention, exporter và collector trước khi kết luận thiếu log/trace.
- Đã kiểm chứng bằng metric/traces hoặc chạy tái hiện khi cần; không diễn giải quá mức từ một trace.
- Đã hạn chế dữ liệu nhạy cảm và tránh dùng `trace_id` làm nhãn metric có độ phân biệt quá cao.

**Ghi nhớ:** `trace_id` giúp *tìm đúng các sự kiện*, `span_id` và span relationships giúp *hiểu nhánh xử lý*, còn log + tracing + metric + mã nguồn giúp *kiểm chứng nguyên nhân*. Một phân tích tốt ghi cả điều đã quan sát và điều chưa thể kết luận.