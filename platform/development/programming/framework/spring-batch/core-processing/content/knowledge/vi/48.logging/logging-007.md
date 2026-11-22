# Gắn chunk hoặc item key vào log trong Spring Batch

Khi một batch job chạy qua hàng triệu bản ghi, dòng log như `Processing failed` gần như không đủ để điều tra sự cố. Người vận hành cần biết lỗi xảy ra ở **job execution nào**, **step nào**, **lượt xử lý chunk nào** và **item nào**. Nhưng nếu ghi toàn bộ object vào log để có thêm ngữ cảnh, hệ thống có thể vô tình tiết lộ dữ liệu khách hàng, thông tin giao dịch hoặc nội dung file nguồn.

Bài học thuộc **Spring Batch Core Processing → Logging**, tập trung vào hai loại khóa dùng để liên kết sự kiện:

- **Chunk key / chunk reference**: nhận diện một *lượt xử lý chunk* để nhóm những log đọc, xử lý, ghi và rollback gần nhau.
- **Item key / item reference**: nhận diện *một bản ghi logic* qua các lần retry, chunk hoặc restart, nếu nguồn dữ liệu có khóa ổn định.

Ta sẽ dùng Spring Batch 5.x, Spring Boot 3.x, Java 17, SLF4J/Logback và JUnit 5 để thiết kế khóa, gắn ngữ cảnh bằng MDC, tạo `ChunkListener`, bọc `ItemProcessor`, log retry/skip an toàn và kiểm tra việc không rò rỉ dữ liệu.

## 1. Vì sao cần cả chunk key và item key?

Một chunk-oriented step thường đọc nhiều item, xử lý từng item, rồi ghi cả nhóm trong một transaction:

```text
JobExecution #850
  └── StepExecution #1260 (importOrdersStep)
       ├── Chunk attempt C1
       │    ├── item A ── process ──┐
       │    ├── item B ── process ──┼── writer ── COMMIT
       │    └── item C ── process ──┘
       │
       ├── Chunk attempt C2
       │    ├── item D ── process ──┐
       │    ├── item E ── process ──┼── writer ── exception
       │    └── item F ── process ──┘              │
       │                                          └── ROLLBACK
       │
       └── Chunk attempt C3 / retry
            ├── item D
            ├── item E
            └── item F ── ...
```

Nếu chỉ có `JobExecutionId`, các dòng log của hàng nghìn chunk bị trộn lẫn. Nếu chỉ có `chunk_ref`, không dễ biết một item xuất hiện lại sau retry/rollback. Nếu chỉ có `item_ref`, khó phân biệt lần xử lý nào bị rollback hay writer đã nhận nhóm nào.

Ví dụ log có cấu trúc:

```text
event=chunk_started job=importOrdersJob step=importOrdersStep
job_execution_id=850 step_execution_id=1260 chunk_ref=je850-se1260-c17

event=item_attempt_failed stage=process
chunk_ref=je850-se1260-c17 item_ref=3d9f840e63776c49
error_code=REMOTE_TIMEOUT

event=chunk_rolled_back
chunk_ref=je850-se1260-c17

event=item_skipped stage=process
chunk_ref=je850-se1260-c18 item_ref=3d9f840e63776c49
error_code=INVALID_ORDER
```

Các mã `chunk_ref` và `item_ref` là **ví dụ minh họa**. Khi phân tích, có thể lọc theo một chunk để xem tiến trình của lượt xử lý hoặc lọc theo item để xem lịch sử qua các lần thử. Hai khóa phục vụ mục đích khác nhau, vì vậy không nên dùng lẫn.

## 2. Hiểu chính xác đơn vị mà khóa nhận diện

| Khóa / metadata | Phạm vi | Ổn định khi retry? | Ổn định khi restart? | Mục đích |
| --- | --- | --- | --- | --- |
| `jobName` | Định nghĩa job | Có | Có | Nhóm các job cùng loại |
| `JobInstance` | Job name + identifying `JobParameters` | Có trong cùng instance | Có nếu restart đúng instance | Nhận diện một công việc logic |
| `jobExecutionId` | Một lần thực thi job | Có trong execution | **Không**; restart tạo execution khác | Truy vết một lần chạy |
| `stepExecutionId` | Một lần thực thi step | Có trong step execution | Thường khác khi step chạy lại | Truy vết step cụ thể |
| `chunk_ref` tự tạo | Một lượt chunk attempt | Có trong lượt xử lý đó | Không bảo đảm | Nhóm log trong một chunk attempt |
| `item_ref` ổn định | Một item logic | Có nếu dùng cùng nguồn khóa | Có nếu định danh nguồn không đổi | Ghép lịch sử một item |
| Trace/span ID | Phạm vi do tracing định nghĩa | Phụ thuộc instrument | Phụ thuộc thiết kế tracing | Tương quan log và lời gọi dịch vụ |

**Spring Batch không cung cấp một `chunkId` bền vững, duy nhất trên mọi restart như một khóa nghiệp vụ.** `StepExecution.getCommitCount()` chỉ là số lần commit được ghi nhận, không phải định danh an toàn cho mọi chunk attempt. Khi transaction rollback, các count, callback và lượt retry có thể thay đổi; không nên coi `commitCount + 1` là ID bất biến của dữ liệu.

Một cách thực dụng là tạo `chunk_ref` cho **mỗi lần bắt đầu chunk** bằng `jobExecutionId + stepExecutionId + sequence` tăng dần. Reference này tốt cho chẩn đoán log trong một lần thực thi; không dùng làm primary key của item, khóa idempotency hay checkpoint.

Ngược lại, `item_ref` cần dựa vào một định danh ổn định: `orderId` của bản ghi, mã thông điệp nguồn hoặc `sourceVersion + rowNumber` khi file **bất biến**. Số thứ tự `readCount` và vị trí item trong chunk thường không phải định danh ổn định sau rollback, partitioning, thay đổi input hoặc restart.

## 3. Thiết kế item key đúng với nguồn dữ liệu

Ví dụ job xử lý đơn hàng có model:

```java
package com.example.batch;

import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        String customerEmail,
        BigDecimal amount) {}
```

Ở đây `orderId` có thể là ứng viên để xây dựng item key, nhưng **không có nghĩa được phép log nguyên văn ID**. ID có thể là dữ liệu cá nhân gián tiếp, có thể liên kết với khách hàng qua hệ thống khác, hoặc bị xem là nhạy cảm theo chính sách nội bộ.

Một số lựa chọn:

| Nguồn item | Định danh nội bộ nên xem xét | Lưu ý |
| --- | --- | --- |
| Database | Primary key hoặc business key đã chuẩn hóa | Có thể thay đổi theo lần import; tránh in trực tiếp key nhạy cảm |
| Kafka/message queue | Topic + partition + offset, hoặc event ID | Offset chỉ định danh bản tin trong nguồn cụ thể; không nhất thiết là cùng entity nghiệp vụ |
| CSV/file bất biến | File version/checksum + record number | Không dùng mỗi số dòng nếu nội dung file có thể thay đổi |
| API có ID ổn định | Provider + external ID | External ID có thể lộ danh tính, cần chính sách token hóa |
| Record chưa parse được | Có thể chưa có ID | Log stage, nguồn đã được phép và vị trí kỹ thuật; dùng `item_ref=unavailable` nếu cần |

Khi một entity xuất hiện trong nhiều nguồn, cần có *namespace*: ví dụ kết hợp `sourceSystem`, `tenantId` hoặc `sourceVersion` trong **dữ liệu đầu vào trước khi tạo token**. Một ID trùng chuỗi trong hai tenant không nên bị coi là cùng một item. Nếu item key được dùng để đối chiếu nghiệp vụ hoặc chống ghi trùng, hãy quản lý khóa nghiệp vụ đó tại tầng dữ liệu; token trong log chỉ là tham chiếu chẩn đoán.

### 3.1. Vì sao tránh hash thường?

Ví dụ `SHA-256(email)` hoặc `SHA-256(orderId)` không có khóa vẫn có thể bị dò bằng từ điển nếu giá trị đầu vào dễ đoán. `String.hashCode()` càng không phù hợp vì vừa không có tính bảo mật, vừa dễ va chạm.

Nếu cần **token ổn định để đối chiếu log** nhưng không được ghi ID gốc, một giải pháp là dùng `HMAC-SHA-256` với khóa bí mật đủ mạnh. HMAC không làm dữ liệu trở nên vô hại: token vẫn cho phép liên kết các log và phải được quản lý quyền truy cập, retention và rotation. Nếu nghiệp vụ không cần liên kết item, bỏ item key khỏi log có thể đơn giản và an toàn hơn.

## 4. Sinh item reference bằng HMAC

Class dưới đây tạo token từ namespace và stable ID, không đưa ID gốc vào output. Mỗi lần gọi tạo một `Mac` mới vì đối tượng `Mac` không bảo đảm thread-safe.

```java
package com.example.batch.logging;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ItemRefFactory {

    private final SecretKeySpec key;

    public ItemRefFactory(byte[] secret) {
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC secret must have at least 32 bytes");
        }
        this.key = new SecretKeySpec(
                secret.clone(), "HmacSHA256");
    }

    public String fromOrderId(String orderId) {
        Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            return "unavailable";
        }

        // Namespace cố định để tránh ghép ID từ domain khác.
        String canonical = "orders:v1:" + orderId;

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));

            // 12 byte đầu (96 bit), biểu diễn bằng 24 ký tự hex.
            return HexFormat.of().formatHex(digest, 0, 12);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Cannot calculate safe item reference");
        }
    }
}
```

Trong hệ thống thật, khóa HMAC cần được lấy từ secret manager hoặc cấu hình bí mật, **không hardcode trong source, log hoặc script triển khai**. Khóa phải được tạo ngẫu nhiên đủ mạnh; kiểm tra độ dài 32 byte trong ví dụ là ràng buộc cấu hình, không phải bằng chứng khóa có entropy tốt.

Cần tính đến hai lựa chọn vận hành:

- **Rotation:** đổi khóa sẽ đổi token của cùng một item. Nếu phải tìm log qua nhiều phiên bản khóa, có thể ghi một `key_version` không nhạy cảm và dùng công cụ truy vết được cấp quyền.
- **Giới hạn liên kết:** cùng khóa và cùng ID tạo cùng token. Nếu không muốn liên kết giữa tenant, job hoặc môi trường, dùng namespace/khóa tách biệt. Không để người dùng tự do chèn chuỗi không kiểm soát vào tên field log.

Token HMAC không thể giải mã trực tiếp thành `orderId`. Muốn tra cứu item từ token, cần một công cụ được cấp quyền đối chiếu với ID từ nguồn dữ liệu hoặc một mapping store được bảo vệ. Đừng coi token là authorization token.

## 5. Gắn chunk key bằng `ChunkListener` và MDC

SLF4J cung cấp **Mapped Diagnostic Context (MDC)**: một tập khóa–giá trị gắn với thread thực thi, được logger/encoder đọc khi phát log. Khi chunk bắt đầu, có thể tạo reference và gắn nó vào MDC; các dòng log trong cùng thread sẽ mang khóa đó.

Ví dụ `ChunkTraceListener.java`:

```java
package com.example.batch.logging;

import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkTraceListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkTraceListener.class);

    private static final String CHUNK_REF = "batch_chunk_ref";
    private static final String STEP_EXECUTION_ID =
            "batch_step_execution_id";

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void beforeChunk(ChunkContext context) {
        StepExecution step =
                context.getStepContext().getStepExecution();

        long attempt = sequence.incrementAndGet();
        String reference = "je" + step.getJobExecutionId()
                + "-se" + step.getId()
                + "-c" + attempt;

        MDC.put(CHUNK_REF, reference);
        MDC.put(STEP_EXECUTION_ID,
                String.valueOf(step.getId()));

        log.debug(
                "event=batch_chunk_started chunk_ref={} step_execution_id={}",
                reference, step.getId());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        try {
            log.debug("event=batch_chunk_committed chunk_ref={}",
                    MDC.get(CHUNK_REF));
        } finally {
            cleanup();
        }
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        try {
            log.warn(
                    "event=batch_chunk_failed chunk_ref={} error_code={}",
                    MDC.get(CHUNK_REF), "CHUNK_ROLLBACK");
        } finally {
            cleanup();
        }
    }

    private void cleanup() {
        // Xóa đúng các khóa listener sở hữu.
        MDC.remove(CHUNK_REF);
        MDC.remove(STEP_EXECUTION_ID);
    }
}
```

Điểm quan trọng:

1. `StepExecution.getJobExecutionId()` và `getId()` liên kết lượt chunk với metadata của job/step. Dãy `AtomicLong` chỉ giúp phân biệt các **lượt callback** trong cùng instance listener.
2. `chunk_ref` trong ví dụ **không phải ID được Spring Batch lưu bền vững**; sau khi restart job, `jobExecutionId`/`stepExecutionId` và counter có thể khác.
3. `afterChunk` và `afterChunkError` dọn các khóa đã gắn, kể cả khi code log gặp lỗi. Không gọi `MDC.clear()` một cách tùy tiện vì như vậy có thể xóa trace context do thành phần khác thiết lập.
4. Đừng dùng `Throwable` hoặc nội dung toàn bộ `Chunk` làm tham số logger. Event rollback trong ví dụ chỉ ghi mã trạng thái đã cho phép.
5. Ví dụ giả định callback cùng lượt chunk dùng cùng thread. Nếu xử lý bất đồng bộ hoặc có custom executor thay đổi thread giữa các công đoạn, MDC cần được truyền và dọn đúng trong từng task; một listener không tự bảo đảm propagation qua mọi thread.

### 5.1. Vì sao dùng bean theo step scope?

Nếu một singleton listener dùng chung cho nhiều step execution, biến `sequence` có thể tăng chung giữa các job đang chạy. Giá trị này vẫn có thể giúp tạo reference nếu đã có execution ID, nhưng gây khó hiểu về phạm vi và quản lý state. Với chunk trace listener chứa counter, nên tạo **mỗi step execution một instance**:

```java
@Bean
@StepScope
public ChunkTraceListener chunkTraceListener() {
    return new ChunkTraceListener();
}
```

`@StepScope` tạo scoped proxy để bean chỉ thực sự được tạo khi step chạy. Trong cấu hình Java, import `org.springframework.context.annotation.Bean` và `org.springframework.batch.core.configuration.annotation.StepScope`.

Với step nhiều thread hoặc partitioned step, counter nguyên tử giúp phân biệt sequence trong cùng instance, nhưng thứ tự `c1`, `c2` không hứa hẹn tương ứng với thứ tự nguồn dữ liệu hay thứ tự commit. Muốn phân tích partition, có thể thêm `partition_ref` cố định đã được kiểm duyệt vào log; item key vẫn phải dựa trên định danh của item, không dựa vào thứ tự thread.

## 6. Gắn item key đúng phạm vi bằng `ItemProcessor`

MDC là context theo thread. Không nên đặt `batch_item_ref` tại `ItemReader` rồi để nguyên cho đến cuối chunk: một chunk có nhiều item, nên khi writer chạy, MDC có thể chỉ còn ID của item cuối cùng và làm người điều tra tưởng writer đang xử lý riêng item đó.

Cách rõ ràng là dùng **một phạm vi MDC cho đúng một lời gọi xử lý item**, rồi gỡ nó trong `finally`. SLF4J 2 hỗ trợ `MDC.putCloseable(...)` giúp làm việc này với `try-with-resources`.

Ví dụ `ItemTraceProcessor.java`:

```java
package com.example.batch.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.item.ItemProcessor;

import com.example.batch.OrderRow;

public class ItemTraceProcessor
        implements ItemProcessor<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ItemTraceProcessor.class);

    private final ItemProcessor<OrderRow, OrderRow> delegate;
    private final ItemRefFactory refs;

    public ItemTraceProcessor(
            ItemProcessor<OrderRow, OrderRow> delegate,
            ItemRefFactory refs) {
        this.delegate = delegate;
        this.refs = refs;
    }

    @Override
    public OrderRow process(OrderRow item) throws Exception {
        String reference = refs.fromOrderId(item.orderId());

        try (MDC.MDCCloseable scope =
                MDC.putCloseable("batch_item_ref", reference)) {

            try {
                // Logger trong delegate có thể lấy item_ref từ MDC.
                return delegate.process(item);
            } catch (Exception ex) {
                log.warn(
                        "event=batch_item_attempt_failed "
                        + "stage=process chunk_ref={} item_ref={} "
                        + "error_code={}",
                        MDC.get("batch_chunk_ref"),
                        reference,
                        safeErrorCode(ex));
                throw ex;
            }
        }
    }

    private String safeErrorCode(Exception ex) {
        if (ex instanceof IllegalArgumentException) {
            return "INVALID_INPUT";
        }
        if (ex instanceof java.net.SocketTimeoutException) {
            return "REMOTE_TIMEOUT";
        }
        return "PROCESSING_FAILED";
    }
}
```

`delegate` là processor nghiệp vụ thật. Nó có thể biến đổi dữ liệu, trả `null` để lọc item hoặc ném exception. Lớp bọc giữ nguyên kết quả và exception, chỉ thêm tham chiếu vào log. Để code trên chạy, record `OrderRow` đã khai báo ở phần 3 cần được đặt ở package `com.example.batch` như ví dụ.

Trong log, chỉ truyền mã lỗi từ danh sách cho phép. **Không đưa `ex.getMessage()`, `ex`, `item`, `item.toString()` hoặc payload HTTP/SQL vào logger thông thường**: chúng có thể chứa dữ liệu nhạy cảm. Nếu cần stack trace để chẩn đoán, phải dùng kênh restricted được thiết kế riêng và xử lý dữ liệu phù hợp.

Với `MDC.putCloseable`, khóa `batch_item_ref` bị gỡ khi thoát phạm vi, kể cả exception. Đoạn mẫu giả định không có một giá trị `batch_item_ref` khác đang được thiết lập bởi component bên ngoài. Nếu có nested scope sử dụng cùng key, hãy lưu giá trị trước đó rồi khôi phục trong `finally`, thay vì xóa mất context của caller.

**Log `batch_item_attempt_failed` chưa có nghĩa item bị skip hoặc job bị FAILED.** Một exception có thể được retry rồi thành công, hoặc bị skip khi đạt điều kiện lỗi. Muốn biết kết quả cuối, sử dụng listener tương ứng và metadata của Spring Batch.

## 7. Writer và SkipListener: tránh gắn nhầm item

### 7.1. Một writer có thể xử lý nhiều item

Trong chunk-oriented step, `ItemWriter.write(Chunk<? extends T>)` nhận một **chunk**, không nhất thiết là một item:

```java
@Override
public void write(Chunk<? extends OrderRow> chunk) throws Exception {
    log.debug(
            "event=batch_write_requested chunk_ref={} item_count={}",
            MDC.get("batch_chunk_ref"),
            chunk.size());

    // Ghi dữ liệu theo quy tắc transaction của writer.
    delegate.write(chunk);
}
```

Ở đây `delegate` là writer nghiệp vụ, `log` là logger của lớp writer và `Chunk` là `org.springframework.batch.item.Chunk`. Nếu writer thất bại ở mức cả chunk mà chưa xác định chính xác bản ghi gây lỗi, **không gán lỗi cho item cuối cùng đã được processor xử lý**. Dùng `chunk_ref` và số lượng item để khoanh vùng; chỉ ghi `item_ref` khi writer hoặc cơ chế skip thực sự xác định được item liên quan.

Khi writer gửi request tới dịch vụ ngoài và cần idempotency, hãy dùng business key được thiết kế riêng cho giao dịch hoặc event. `chunk_ref` là khóa log tạm thời nên không thích hợp làm idempotency key; retry có thể tạo một chunk reference khác.

### 7.2. SkipListener nhận diện item bị bỏ qua

Spring Batch có `SkipListener<I, O>` để thông báo khi framework đã quyết định skip. Ví dụ này giả định cùng kiểu `OrderRow` cho đầu vào và đầu ra:

```java
package com.example.batch.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.SkipListener;

import com.example.batch.OrderRow;

public class SafeOrderSkipListener
        implements SkipListener<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeOrderSkipListener.class);

    private final ItemRefFactory refs;

    public SafeOrderSkipListener(ItemRefFactory refs) {
        this.refs = refs;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=read "
                + "chunk_ref={} item_ref={} error_code={}",
                MDC.get("batch_chunk_ref"),
                "unavailable",
                "READ_FAILED");
    }

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        logSkip("process", item, "INVALID_INPUT");
    }

    @Override
    public void onSkipInWrite(OrderRow item, Throwable error) {
        logSkip("write", item, "WRITE_REJECTED");
    }

    private void logSkip(
            String stage, OrderRow item, String safeCode) {
        log.warn(
                "event=batch_item_skipped stage={} "
                + "chunk_ref={} item_ref={} error_code={}",
                stage,
                MDC.get("batch_chunk_ref"),
                refs.fromOrderId(item.orderId()),
                safeCode);
    }
}
```

Ở `onSkipInRead`, callback không cung cấp item đã đọc thành công, vì vậy không thể suy ra ID an toàn của bản ghi từ một `OrderRow` chưa được tạo. Không dump dòng CSV, buffer hoặc response body để lấy ID. Có thể bổ sung một `source_ref` đã được thẩm định nếu reader cung cấp định danh nguồn và vị trí an toàn.

Trong code mẫu, các mã `READ_FAILED`, `INVALID_INPUT` và `WRITE_REJECTED` đại diện cho kịch bản minh họa. Ứng dụng thật nên ánh xạ `Throwable` sang **error code cố định dựa trên loại lỗi**, thay vì luôn quy mọi lỗi process thành `INVALID_INPUT`; tuyệt đối tránh chuyển thẳng exception message thành log field.

`SkipListener` phù hợp để log item **bị bỏ qua thực sự**, còn `ItemProcessListener.onProcessError` hay wrapper processor phù hợp cho **một attempt lỗi**. Có retry, một item có thể bị ghi log lỗi attempt nhiều lần mà cuối cùng không bị skip. Vì log không tham gia transaction dữ liệu, không lấy số dòng log làm nguồn duy nhất để đếm item chính xác trong những yêu cầu audit.

## 8. Cấu hình step tích hợp các listener

Giả sử ứng dụng đã có `ItemReader<OrderRow>`, `ItemProcessor<OrderRow, OrderRow>` nghiệp vụ và `ItemWriter<OrderRow>`. Có thể tạo các bean:

```java
package com.example.batch.logging;

import java.util.Base64;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

import com.example.batch.OrderRow;

@Configuration
public class ImportOrdersStepConfig {

    @Bean
    ItemRefFactory itemRefFactory(
            @Value("${batch.logging.hmac-key-base64}") String keyBase64) {
        return new ItemRefFactory(
                Base64.getDecoder().decode(keyBase64));
    }

    @Bean
    @StepScope
    ChunkTraceListener chunkTraceListener() {
        return new ChunkTraceListener();
    }

    @Bean
    SafeOrderSkipListener safeOrderSkipListener(ItemRefFactory refs) {
        return new SafeOrderSkipListener(refs);
    }

    @Bean
    ItemTraceProcessor itemTraceProcessor(
            @Qualifier("businessOrderProcessor")
            ItemProcessor<OrderRow, OrderRow> businessProcessor,
            ItemRefFactory refs) {
        return new ItemTraceProcessor(businessProcessor, refs);
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderRow> reader,
            ItemTraceProcessor processor,
            ItemWriter<OrderRow> writer,
            ChunkTraceListener chunkListener,
            SafeOrderSkipListener skipListener) {

        return new StepBuilder("importOrdersStep", repository)
                .<OrderRow, OrderRow>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(java.net.SocketTimeoutException.class)
                .retryLimit(3)
                .skip(IllegalArgumentException.class)
                .skipLimit(20)
                .listener(chunkListener)
                .listener(skipListener)
                .build();
    }
}
```

`businessOrderProcessor`, reader và writer là các bean nghiệp vụ **giả định tồn tại**; ví dụ tập trung vào việc gắn ngữ cảnh log. Trong dự án thật phải điều chỉnh loại exception retry/skip cho đúng exception phát ra tại ranh giới step và đúng chính sách xử lý dữ liệu.

Cấu hình tham chiếu khóa:

```properties
batch.logging.hmac-key-base64=${BATCH_LOG_REF_KEY_B64}
```

`BATCH_LOG_REF_KEY_B64` cần được cấp từ secret manager hoặc cơ chế quản lý secret được bảo vệ; không ghi giá trị thật vào repository, container image hoặc log. Bean chứa `ChunkTraceListener` ở `@StepScope` để sequence của listener gắn với một step execution, và cần đảm bảo hạ tầng Spring Batch step scope đã được cấu hình.

Khi dùng log pattern của Logback, có thể hiển thị MDC bên cạnh thông điệp:

```xml
<pattern>
  %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
  chunk=%X{batch_chunk_ref:-none}
  item=%X{batch_item_ref:-none}
  %logger{30} - %msg%n
</pattern>
```

Đây là **fragment pattern** cần đặt vào appender Logback thích hợp trong cấu hình `logback-spring.xml`; bản thân đoạn XML không phải file cấu hình hoàn chỉnh. Không bật in toàn bộ MDC (`%X`) nếu trong MDC có key khác mang dữ liệu nhạy cảm. Cũng không nên log **cả** giá trị từ pattern và các field lặp trong message khi log volume lớn; hệ thống JSON logging có thể đưa từng field vào cấu trúc thay cho chuỗi văn bản.

## 9. Tác động của retry, rollback, restart và concurrency

### 9.1. Retry và rollback

Nếu processor của item B lỗi rồi retry thành công:

```text
chunk_ref=je850-se1260-c17 item_ref=ref-B attempt_failed
chunk_ref=je850-se1260-c17 item_ref=ref-B processed
chunk_ref=je850-se1260-c17 chunk_committed
```

Nhưng nếu writer lỗi làm rollback chunk, framework có thể phát sinh lượt xử lý lại, tùy cấu hình transaction, buffering và retry:

```text
chunk_ref=je850-se1260-c17 writer_failed
chunk_ref=je850-se1260-c17 chunk_rolled_back
chunk_ref=je850-se1260-c18 item_ref=ref-B processed_again
```

`chunk_ref` khác, còn `item_ref` giống nhau. Chính quan hệ đó giúp hiểu một item được thực hiện lại ở đâu. Không nên suy ra số attempt chỉ bằng đếm `chunk_ref`: một chunk có thể thực hiện nhiều retry nội bộ, và callback/transaction behavior phụ thuộc reader, processor, writer và policy.

### 9.2. Restart job

Khi restart một `JobInstance` `FAILED` với cùng identifying `JobParameters`, Spring Batch tạo **`JobExecution` mới**. Nếu step cần chạy lại, nó thường có `StepExecution` mới. `chunk_ref` vì thế sẽ khác, nhưng item reference ổn định có thể liên kết log qua hai lần chạy:

```text
JobExecution 850:
  chunk_ref=je850-se1260-c17 item_ref=ref-B error

JobExecution 851 (restart cùng JobInstance):
  chunk_ref=je851-se1302-c01 item_ref=ref-B success
```

Không dùng `jobExecutionId` hay số thứ tự chunk làm một phần của **item key cần ổn định qua restart**. Mặt khác, nếu item key chỉ dựa vào ngày nghiệp vụ mà thiếu ID item, nhiều bản ghi trong cùng ngày sẽ bị gộp nhầm.

### 9.3. Multi-threaded step và partitioning

MDC thông thường gắn với **thread hiện tại**. Khi dùng `TaskExecutor`, partitioning hoặc gọi API bất đồng bộ, log có thể chạy ở thread khác mà không tự động nhận được context. Muốn truyền MDC qua task, có thể dùng wrapper hoặc `TaskDecorator` sao chép context map ở thời điểm dispatch và **khôi phục/clear trong `finally`** sau khi task kết thúc.

Không chia sẻ một `Map<String,String>` mutable giữa các thread rồi thay đổi trực tiếp. Mỗi task nên nhận snapshot context riêng. Nếu listener chạy trên nhiều thread, sequence `AtomicLong` giúp tránh trùng `chunk_ref` trong step execution, nhưng không cam kết thứ tự chunk theo file, offset hoặc commit.

Nếu hệ thống có tracing với OpenTelemetry/Micrometer, có thể liên kết `traceId`/`spanId` từ tracing vào log. **Trace ID và item key có vòng đời khác nhau**: một trace có thể chứa nhiều item, một item có thể xuất hiện ở nhiều trace qua restart. Không thay thế item identity bằng trace identity.

## 10. Kiểm thử khóa log và việc dọn MDC

Một lớp logging có thể hoạt động tốt về mặt nghiệp vụ nhưng vẫn làm rò rỉ ngữ cảnh khi thread được tái sử dụng. Test cần kiểm tra ba điều: **khóa xuất hiện khi cần**, **dữ liệu gốc không xuất hiện**, và **MDC đã được dọn khi kết thúc lời gọi**.

Ví dụ test với JUnit 5, AssertJ và Logback `ListAppender`. Đây là test của wrapper processor, không cần chạy toàn bộ job:

```java
package com.example.batch.logging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.Arrays;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.item.ItemProcessor;

import com.example.batch.OrderRow;

class ItemTraceProcessorTest {

    @Test
    void addsSafeItemRefAndRestoresThreadContext() {
        byte[] testKey = new byte[32];
        Arrays.fill(testKey, (byte) 7);
        ItemRefFactory refs = new ItemRefFactory(testKey);

        String rawId = "order-private-007";
        String privateEmail = "person@example.test";
        OrderRow item = new OrderRow(
                rawId, privateEmail, new BigDecimal("123.45"));

        ItemProcessor<OrderRow, OrderRow> failingBusinessProcessor =
                row -> {
                    throw new IllegalArgumentException(
                            "Invalid customer: " + row.customerEmail());
                };

        ItemTraceProcessor processor =
                new ItemTraceProcessor(failingBusinessProcessor, refs);

        Logger logger = (Logger) LoggerFactory.getLogger(
                ItemTraceProcessor.class);
        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            assertThatThrownBy(() -> processor.process(item))
                    .isInstanceOf(IllegalArgumentException.class);

            assertThat(capture.list).hasSize(1);
            ILoggingEvent event = capture.list.get(0);
            String message = event.getFormattedMessage();

            assertThat(message)
                    .contains("event=batch_item_attempt_failed")
                    .contains("error_code=INVALID_INPUT")
                    .contains("item_ref=" + refs.fromOrderId(rawId));

            assertThat(event.getMDCPropertyMap())
                    .containsEntry(
                            "batch_item_ref", refs.fromOrderId(rawId));

            assertThat(message)
                    .doesNotContain(rawId)
                    .doesNotContain(privateEmail)
                    .doesNotContain("123.45")
                    .doesNotContain("Invalid customer:");

            assertThat(MDC.get("batch_item_ref")).isNull();
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            MDC.remove("batch_item_ref");
        }
    }
}
```

Trong test, ta dùng một khóa giả có giá trị biết trước. Production phải dùng khóa có entropy thực sự từ secret manager. `ListAppender` thu event do wrapper phát ra; test này **chưa chứng minh** các thư viện khác, HTTP client, SQL logger hay tracing agent không log dữ liệu nhạy cảm. Với integration test, nên đưa một marker dữ liệu nhạy cảm giả qua toàn pipeline, thu log sau encoder rồi tìm marker đó.

### 10.1. Kiểm tra chunk listener

Với `ChunkTraceListener`, có thể dùng integration test chạy một step nhỏ gồm 2–3 chunk và kiểm tra:

1. Mỗi `beforeChunk` tạo `chunk_ref` gồm job/step execution ID và sequence.
2. Dòng log processor trong cùng thread mang đúng `chunk_ref`.
3. Sau commit, MDC không còn `batch_chunk_ref`.
4. Khi writer làm rollback, event `batch_chunk_failed` có reference và MDC vẫn được dọn.
5. Nếu chạy lại cùng item qua retry hoặc restart, `item_ref` vẫn ổn định, trong khi `chunk_ref` có thể khác.
6. Khi chạy test ở nhiều thread, không có chunk reference của một task xuất hiện trong log task khác.

Để test chunk listener đầy đủ cần cấu hình `JobRepository`/transaction và step test phù hợp; không nên giả lập một cách quá đơn giản rồi kết luận chính xác về chu kỳ rollback của Spring Batch.

## 11. Quy tắc vận hành cho chunk/item keys

| Trường hợp | Nên làm | Tránh |
| --- | --- | --- |
| Chẩn đoán chunk rollback | Dùng `jobExecutionId`, `stepExecutionId`, `chunk_ref` | Coi `commitCount` là chunk ID ổn định mãi |
| Theo dõi item qua retry/restart | Dùng item ref từ identity nguồn ổn định | Dùng vị trí trong chunk hoặc thread ID |
| Item chứa PII | HMAC/token có chính sách, hoặc bỏ ref | Log nguyên email/order ID |
| Lỗi reader chưa tạo item | `item_ref=unavailable` và mã lỗi | Log nguyên dòng CSV/body để lấy ID |
| Writer xử lý cả chunk | Log chunk ref, số lượng, kết quả | Gắn nhầm lỗi cho item cuối cùng |
| Log attempt rồi skip | Tách `attempt_failed`, `item_skipped`, `chunk_failed` | Gọi mọi lỗi là “item failed cuối cùng” |
| Logging multi-thread | Scope MDC theo task, cleanup trong `finally` | Để MDC rò sang task kế tiếp |
| Metrics | Label theo job, step, stage, error code | Đưa item key/chunk key làm metric label |
| Idempotency/restart | Dùng business key/checkpoint được thiết kế riêng | Dùng chunk ref làm transaction key |
| Log aggregation | Mask dữ liệu ở nguồn, giới hạn quyền và retention | Tin rằng log text an toàn thì toàn pipeline an toàn |

**Cardinality:** item key và chunk key thường có số lượng giá trị rất lớn. Chúng phù hợp làm **field tìm kiếm trong log** khi cần điều tra, nhưng không nên đưa thành label của metric time series (Prometheus/Micrometer), vì dễ làm bùng nổ số lượng chuỗi và chi phí lưu trữ. Metric nên tổng hợp theo các chiều có số giá trị hữu hạn như `job_name`, `step_name`, `stage` và `error_code`.

**Tính chính xác:** log là kênh quan sát, không phải transaction log của Spring Batch. Khi có rollback, retry, network hoặc lỗi hệ thống thu log, một event có thể được ghi nhiều lần hoặc bị mất. Nếu yêu cầu audit “mỗi item chỉ có đúng một kết quả cuối”, cần bảng audit hoặc transactional outbox có idempotency key và quy tắc commit phù hợp.

**Bảo mật:** giới hạn quyền đọc log, thời hạn lưu, truy cập token mapping và khóa HMAC. Không ghi tất cả `JobParameters` hoặc `ExecutionContext` vào log để lấy ngữ cảnh vì hai object này có thể chứa dữ liệu ngoài allowlist.

## 12. Bài thực hành

Hãy tạo một `importOrdersJob` có chunk size 3 và đầu vào ít nhất 7 bản ghi, trong đó một item có lỗi validation và một item gây lỗi dịch vụ tạm thời:

1. Tạo `OrderRow` với `orderId`, `customerEmail`, `amount`. Tạo `ItemRefFactory` dùng HMAC với khóa test riêng; kiểm tra cùng order ID tạo cùng item ref, còn hai ID khác nhau cho kết quả khác nhau.
2. Gắn `ChunkTraceListener` vào step. Chạy một lượt thành công và quan sát các event chunk với `jobExecutionId`, `stepExecutionId` và sequence.
3. Bọc processor thật bằng `ItemTraceProcessor`. Ở lỗi validation, kiểm tra `item_ref` xuất hiện nhưng email, ID gốc và amount không xuất hiện trong log.
4. Cấu hình `retry` cho lỗi tạm thời trong processor. Tạo lỗi hai lần rồi thành công; so sánh event attempt với kết quả item cuối.
5. Cấu hình `skip` cho lỗi validation. Dùng `SkipListener` để ghi **event item bị skip**, phân biệt nó với lần processor gặp exception.
6. Cho writer ném lỗi trước commit, quan sát `chunk_ref` khi rollback và khi thử lại. Xác nhận không suy ra item gây lỗi chỉ từ `chunk_ref` nếu writer xử lý nhiều bản ghi.
7. Thực hiện restart sau job `FAILED` trên repository bền vững. Kiểm tra item đã xử lý lại vẫn dùng cùng `item_ref`, còn execution/chunk reference thay đổi.
8. Chạy một step multi-threaded hoặc partitioned, rồi kiểm tra MDC của mỗi task không bị trộn. Nếu có task bất đồng bộ, bổ sung propagation wrapper và cleanup.
9. Thu toàn bộ log bằng Logback test appender, bảo đảm dữ liệu nhạy cảm giả không xuất hiện. Đồng thời kiểm tra JSON encoder, exception layout và tracing nếu hệ thống sử dụng.
10. Định nghĩa dashboard: đếm số item skip và chunk rollback theo error code, job và step; không đưa item/chunk reference vào metric labels.

Khi gắn chunk hoặc item key vào logging của Spring Batch, cần chọn **đúng phạm vi và vòng đời của khóa**. `chunk_ref` giúp nhóm log của một lượt xử lý, `item_ref` giúp theo dõi cùng dữ liệu qua retry/restart, còn `JobExecution`/`StepExecution` liên kết log với metadata của framework. Dùng khóa có nguồn gốc ổn định, token hóa những ID nhạy cảm, giới hạn thời gian tồn tại của MDC và phân biệt event kỹ thuật với kết quả nghiệp vụ sẽ giúp log hữu ích mà không làm tăng rủi ro lộ dữ liệu.
