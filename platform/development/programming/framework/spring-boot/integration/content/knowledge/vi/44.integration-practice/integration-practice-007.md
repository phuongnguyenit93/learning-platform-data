# Xây dựng IntegrationFlow nhận tệp, kiểm tra, biến đổi và định tuyến

## 1. Bối cảnh thực hành

Một ứng dụng **Spring Boot Integration** cần nhận tệp CSV do đối tác gửi đến thư mục dùng chung, kiểm tra nội dung, chuẩn hóa thành đối tượng Java và chuyển sang dịch vụ xử lý **đơn hàng** hoặc **biến động tồn kho**. Bài này kết hợp HTTP/DB/broker adapter ở tầng nghiệp vụ với các **Enterprise Integration Patterns (EIP)** trong Spring Integration: file inbound adapter, polling consumer, transformer, filter, content-based router, service activator và error channel.

### Đề bài và hợp đồng dữ liệu

Để tập trung vào cách ghép `IntegrationFlow`, ví dụ quy ước **mỗi tệp có một bản ghi** với mã hóa UTF-8, đúng hai dòng: header cố định và một dòng dữ liệu.

~~~csv
type,requestId,sku,quantity
ORDER,req-1001,SKU-42,3
~~~

Ví dụ yêu cầu nhập/xuất tồn kho:

~~~csv
type,requestId,sku,quantity
STOCK,req-1002,SKU-42,-3
~~~

| Trường | Quy tắc trong bài | Ý nghĩa |
| --- | --- | --- |
| `type` | `ORDER` hoặc `STOCK` | Khóa định tuyến |
| `requestId` | 1–64 ký tự chữ, số, `_` hoặc `-` | Khóa idempotency xuyên hệ thống |
| `sku` | 1–64 ký tự theo bộ ký tự trên | Mã sản phẩm |
| `quantity` | Số nguyên 32-bit; `ORDER > 0`; `STOCK != 0` | Lượng đặt hàng hoặc chênh lệch tồn |

Đối tác ghi vào tệp tạm `.writing`, đóng file, rồi đổi tên thành `*.ready.csv` sau khi hoàn tất. Ứng dụng **chỉ đọc `*.ready.csv`**. Quy tắc này giảm nguy cơ consumer nhìn thấy dữ liệu mới ghi dở.

~~~mermaid
flowchart TD
    A[Đối tác ghi .writing] --> B[Đổi tên .ready.csv]
    B --> C[File inbound adapter và poller]
    C --> D[Payload: java.io.File]
    D --> E[Parser tạo ImportCandidate]
    E --> F{Dữ liệu hợp lệ?}
    F -- Không --> Q[rejectedImports]
    Q --> R[Quarantine, lưu nguyên nhân]
    F -- Có --> G[Transformer tạo NormalizedImport]
    G --> H{Route theo type}
    H -- ORDER --> I[orderImports]
    H -- STOCK --> J[stockImports]
    I --> K[Order handler]
    J --> L[Stock handler]
    K --> M[DB hoặc HTTP + archive]
    L --> M
    E -. Exception .-> X[fileImportErrors]
    G -. Exception .-> X
    K -. Exception .-> X
    L -. Exception .-> X
    X --> Y[Incident và redrive có kiểm soát]
~~~

**Phân loại lỗi ngay từ thiết kế:** thiếu cột hoặc `quantity=abc` là **lỗi dữ liệu** để từ chối có giải thích; mất kết nối DB, lỗi đọc file hoặc HTTP timeout là **lỗi kỹ thuật** để đưa vào kênh lỗi và quy trình retry/redrive. Hai nhóm không nên cùng âm thầm rơi khỏi flow.

## 2. Chuẩn bị ứng dụng

Với Spring Boot 3.x và Java 17+, khai báo các dependency Maven sau; phiên bản được Spring Boot BOM quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-file</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Java DSL đã được tích hợp trong các module Spring Integration hiện đại; không cần dependency `spring-integration-java-dsl` cũ. Nếu dùng Spring Boot 4.x, đối chiếu lại dependency và API theo phiên bản tương ứng.

~~~yaml
# application.yml
app:
  import:
    inbox: ./data/inbox
    processed: ./data/processed
    rejected: ./data/rejected
spring:
  application:
    name: file-integration-practice
logging:
  level:
    org.springframework.integration: INFO
~~~

~~~text
data/
├── inbox/       # Chỉ file *.ready.csv mới được xử lý
├── processed/   # File đã xử lý thành công
└── rejected/    # File sai và lý do từ chối
~~~

Trong container, nên cấu hình các thư mục bằng volume và biến môi trường, kiểm tra quyền đọc/ghi, dung lượng đĩa và tránh để nhiều instance quét cùng một nguồn khi chưa có cơ chế claim.

## 3. Mô hình thông điệp trung gian

Sau khi nhận, message có payload là `File`. Parser chuyển thành `ImportCandidate` vẫn giữ quantity dưới dạng chuỗi và tập lỗi. Filter quyết định cho đi tiếp. Sau đó transformer mới tạo `NormalizedImport` có giá trị đã chuẩn hóa.

~~~java
import java.io.File;
import java.util.List;

public record ImportCandidate(
        File file,
        String type,
        String requestId,
        String sku,
        String quantityText,
        List<String> errors) {

    public boolean valid() {
        return errors.isEmpty();
    }
}

public enum ImportType {
    ORDER, STOCK
}

public record NormalizedImport(
        File source,
        ImportType type,
        String requestId,
        String sku,
        int quantity) {
}
~~~

Đặt ba kiểu `public` trong ba file Java cùng package; bài gộp lại cho dễ đọc. Ranh giới này giữ đường dẫn file gốc để archive/quarantine, giúp handler nghiệp vụ chỉ nhìn dữ liệu đã hợp lệ và hỗ trợ thay parser CSV bằng JSON/XML mà không phải viết lại nhánh xử lý.

## 4. Parser kiểm tra cấu trúc và quy tắc cơ bản

Parser sau minh họa trường hợp **một bản ghi CSV không chứa dấu phẩy trong ô**. Với CSV thực tế có quote/escape hoặc nhiều dòng, dùng Apache Commons CSV/Jackson CSV và cơ chế streaming; không dùng `String.split(",")` để xử lý CSV tổng quát.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;

@Component
public class CsvImportParser {

    private static final String HEADER = "type,requestId,sku,quantity";
    private static final long MAX_SIZE = 64 * 1024;

    public ImportCandidate parse(File file) {
        List<String> lines;
        try {
            if (java.nio.file.Files.size(file.toPath()) > MAX_SIZE) {
                return invalid(file, "File vượt quá 64 KiB");
            }
            lines = java.nio.file.Files.readAllLines(
                    file.toPath(), StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException("Không đọc được " + file.getName(), ex);
        }

        if (lines.size() != 2 || !HEADER.equals(lines.get(0))) {
            return invalid(file, "Cần đúng header và một dòng dữ liệu");
        }
        String[] fields = lines.get(1).split(",", -1);
        if (fields.length != 4) {
            return invalid(file, "Dòng dữ liệu phải có đúng 4 trường");
        }

        String type = fields[0].trim().toUpperCase(Locale.ROOT);
        String requestId = fields[1].trim();
        String sku = fields[2].trim();
        String quantityText = fields[3].trim();
        List<String> errors = new ArrayList<>();

        if (!type.equals("ORDER") && !type.equals("STOCK")) {
            errors.add("type phải là ORDER hoặc STOCK");
        }
        if (!requestId.matches("[A-Za-z0-9_-]{1,64}")) {
            errors.add("requestId không đúng định dạng");
        }
        if (!sku.matches("[A-Za-z0-9_-]{1,64}")) {
            errors.add("sku không đúng định dạng");
        }

        try {
            int quantity = Integer.parseInt(quantityText);
            if ("ORDER".equals(type) && quantity <= 0) {
                errors.add("ORDER phải có quantity > 0");
            }
            if ("STOCK".equals(type) && quantity == 0) {
                errors.add("STOCK phải có quantity khác 0");
            }
        } catch (NumberFormatException ex) {
            errors.add("quantity phải là số nguyên 32-bit");
        }

        return new ImportCandidate(
                file, type, requestId, sku, quantityText, List.copyOf(errors));
    }

    private ImportCandidate invalid(File file, String message) {
        return new ImportCandidate(file, "", "", "", "", List.of(message));
    }
}
~~~

Lỗi dữ liệu sinh một `ImportCandidate` chứa `errors` để được giải thích trong `rejectedImports`. Lỗi đọc tệp ném `UncheckedIOException` để vào `fileImportErrors`. Việc kiểm tra kích thước trước `readAllLines` phù hợp cho sandbox có producer tuân thủ giao thức đổi tên, chưa phải phương án ingest file không tin cậy hoặc file rất lớn. Trong production cần giới hạn đọc thực tế, kiểm tra encoding, phòng đọc đồng thời với writer và ràng buộc kích thước khi tải lên.

## 5. Transformer chuẩn hóa

Sau khi filter bảo đảm candidate hợp lệ, transformer đổi `type` thành enum và `quantity` thành số nguyên. Đây là ranh giới hợp đồng dữ liệu giữa hệ thống đối tác và model nội bộ.

~~~java
import org.springframework.stereotype.Component;

@Component
public class ImportNormalizer {

    public NormalizedImport normalize(ImportCandidate candidate) {
        if (!candidate.valid()) {
            throw new IllegalArgumentException("Candidate chưa hợp lệ");
        }
        return new NormalizedImport(
                candidate.file(),
                ImportType.valueOf(candidate.type()),
                candidate.requestId(),
                candidate.sku(),
                Integer.parseInt(candidate.quantityText()));
    }
}
~~~

Parser đã kiểm tra các điều kiện để `valueOf` và `parseInt` thành công. Nếu thay đổi hợp đồng ngoài, có thể thay parser/validator mà giữ nguyên API `NormalizedImport` cho handler nghiệp vụ.

## 6. Ghép IntegrationFlow: nhận → kiểm tra → biến đổi → định tuyến

Đoạn cấu hình sau là phần trung tâm. `Files.inboundAdapter` tạo một `FileReadingMessageSource`; poller cứ 5 giây lấy tối đa 10 tệp phù hợp trong một lượt. Flow tiếp theo là chuỗi handler đồng bộ, và router gửi thông điệp sang channel ứng với `type`.

~~~java
import java.io.File;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;

@Configuration
public class FileImportFlowConfig {

    @Bean
    IntegrationFlow fileImportFlow(
            @Value("${app.import.inbox}") File inbox,
            CsvImportParser parser,
            ImportNormalizer normalizer) {

        return IntegrationFlow
                .from(Files.inboundAdapter(inbox)
                                .autoCreateDirectory(true)
                                .patternFilter("*.ready.csv")
                                .preventDuplicates(true),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(5))
                                        .maxMessagesPerPoll(10)
                                        .errorChannel("fileImportErrors")))
                .transform(File.class, parser::parse)
                .filter(ImportCandidate.class,
                        ImportCandidate::valid,
                        spec -> spec.discardChannel("rejectedImports"))
                .transform(ImportCandidate.class, normalizer::normalize)
                .route(NormalizedImport.class,
                        value -> value.type().name(),
                        spec -> spec
                                .channelMapping("ORDER", "orderImports")
                                .channelMapping("STOCK", "stockImports")
                                .defaultOutputChannel("unsupportedImports"))
                .get();
    }

    @Bean
    IntegrationFlow orderImportFlow(ImportHandlers handlers) {
        return IntegrationFlow.from("orderImports")
                .handle(handlers, "handleOrder")
                .get();
    }

    @Bean
    IntegrationFlow stockImportFlow(ImportHandlers handlers) {
        return IntegrationFlow.from("stockImports")
                .handle(handlers, "handleStock")
                .get();
    }

    @Bean
    IntegrationFlow rejectedImportFlow(RejectedImportHandler handler) {
        return IntegrationFlow.from("rejectedImports")
                .handle(handler, "handle")
                .get();
    }

    @Bean
    IntegrationFlow unsupportedImportFlow(UnsupportedImportHandler handler) {
        return IntegrationFlow.from("unsupportedImports")
                .handle(handler, "handle")
                .get();
    }

    @Bean
    IntegrationFlow fileImportErrorFlow(FileImportErrorHandler handler) {
        return IntegrationFlow.from("fileImportErrors")
                .handle(handler, "handle")
                .get();
    }
}
~~~

### Vai trò và kiểu payload của từng bước

| Bước | Payload vào → ra | Vai trò |
| --- | --- | --- |
| `Files.inboundAdapter` | File trên đĩa → `java.io.File` | Phát hiện file theo pattern |
| `Pollers.fixedDelay(5s)` | Lịch polling | Kích hoạt nguồn, tối đa 10 message/lượt; không đồng nghĩa 10 luồng song song |
| `transform(File.class, parser::parse)` | `File → ImportCandidate` | Đọc và kiểm tra cú pháp |
| `filter(...valid...)` | `ImportCandidate` hoặc discard | Lỗi hợp đồng đi `rejectedImports` |
| `transform(...normalize...)` | `ImportCandidate → NormalizedImport` | Chuẩn hóa kiểu dữ liệu |
| `route(...type...)` | `NormalizedImport → channel` | Chọn ORDER/STOCK theo nội dung message |
| `handle(...)` | Message → side effect | Gọi dịch vụ tích hợp, archive hoặc quarantine |
| `errorChannel(...)` | Exception → `ErrorMessage` | Ghi incident của xử lý bất thường trong tác vụ poll |

`filter` không tự phát lỗi khi predicate trả false; `discardChannel` là cách chủ động giữ lại tệp bị từ chối. Khi khai báo router, nên có `defaultOutputChannel` để tránh rơi message im lặng trong trường hợp xuất hiện loại mới. Kênh `unsupportedImports` ở ví dụ này nhận **`NormalizedImport`**, khác với `rejectedImports` nhận **`ImportCandidate`**; hai nhánh phải có handler đúng loại payload.

Các channel trên là điểm nối đồng bộ theo cấu hình mặc định. Vì vậy exception của một handler `DirectChannel` có thể lan về poller rồi chuyển thành `ErrorMessage` tại `fileImportErrors`. Nếu sau này dùng `ExecutorChannel`, `QueueChannel` hoặc reactive adapter, hãy thiết kế lại error channel, correlation, transaction và bảo đảm phản hồi của nhánh bất đồng bộ: error channel của poller không mặc nhiên bao quát mọi exception sau khi bàn giao.

## 7. Handler ở các nhánh định tuyến

Phần Spring Integration chịu trách nhiệm **điều phối message**; nghiệp vụ đặt sau một interface có thể được triển khai bằng Spring Data JDBC/JPA, HTTP client, broker hoặc adapter Spring Integration khác. Ví dụ khai báo hai cổng tích hợp:

~~~java
public interface ImportApplicationService {
    void applyOrder(String requestId, String sku, int quantity);
    void applyStockDelta(String requestId, String sku, int delta);
}

public interface FileImportArchive {
    void markProcessed(java.io.File source);
    void reject(java.io.File source, java.util.List<String> errors);
}
~~~

Để chạy ứng dụng, cần tạo bean triển khai hai interface này phù hợp với môi trường thử nghiệm. Ví dụ trên cố ý giữ phần kết nối DB/API/broker thành cổng riêng để không trộn thao tác hạ tầng với định nghĩa flow. Trong production, service phải có idempotency bền vững và kiểm soát transaction theo đúng hợp đồng downstream.

~~~java
import org.springframework.stereotype.Component;

@Component
public class ImportHandlers {
    private final ImportApplicationService service;
    private final FileImportArchive archive;

    public ImportHandlers(
            ImportApplicationService service, FileImportArchive archive) {
        this.service = service;
        this.archive = archive;
    }

    public void handleOrder(NormalizedImport message) {
        service.applyOrder(
                message.requestId(), message.sku(), message.quantity());
        archive.markProcessed(message.source());
    }

    public void handleStock(NormalizedImport message) {
        service.applyStockDelta(
                message.requestId(), message.sku(), message.quantity());
        archive.markProcessed(message.source());
    }
}
~~~

**Thứ tự có ý nghĩa:** handler chỉ gọi `markProcessed` sau khi dịch vụ xác nhận thành công. Nếu HTTP đã xử lý nhưng ứng dụng chết trước khi archive, việc chạy lại có thể phát cùng yêu cầu thêm lần nữa. `requestId` phải là idempotency key ở lớp dữ liệu hoặc phía đối tác; chỉ lọc tên tệp không tạo được exactly-once.

### Nhánh từ chối vì dữ liệu sai

~~~java
import org.springframework.stereotype.Component;

@Component
public class RejectedImportHandler {
    private final FileImportArchive archive;

    public RejectedImportHandler(FileImportArchive archive) {
        this.archive = archive;
    }

    public void handle(ImportCandidate rejected) {
        archive.reject(rejected.file(), rejected.errors());
    }
}

@Component
public class UnsupportedImportHandler {
    private final FileImportArchive archive;

    public UnsupportedImportHandler(FileImportArchive archive) {
        this.archive = archive;
    }

    public void handle(NormalizedImport unsupported) {
        archive.reject(
                unsupported.source(),
                java.util.List.of("Chưa có nhánh xử lý: " + unsupported.type()));
    }
}
~~~

Hai lớp `public` đặt trong hai file Java riêng. Với hợp đồng hiện tại, validator đã loại `type` khác `ORDER`/`STOCK`; nhánh `unsupportedImports` phòng khi sau này enum có giá trị mới nhưng router chưa có mapping.

`FileImportArchive` có thể triển khai bằng cách tạo thư mục đích với `java.nio.file.Files.createDirectories`, ghi lý do `.reason.txt`, rồi chuyển file bằng `Files.move`. Không cho ghi đè file đã xử lý trùng tên; đường dẫn đích phải được tạo từ tên file an toàn, thuộc thư mục đã cấu hình. Quarantine nên giữ raw input, timestamp, version schema và các lỗi để truy vết. Nếu việc ghi lý do hoặc chuyển file thất bại thì ném exception, không giả vờ đã reject thành công.

### Nhánh lỗi kỹ thuật từ poller

Trong chuỗi đồng bộ, các exception không được bắt riêng ở handler có thể đi về `fileImportErrors`. Handler bên dưới chỉ minh họa ghi lỗi; thực tế cần logger, lưu incident, metric, cảnh báo và quy trình khôi phục.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class FileImportErrorHandler {
    private static final Logger log =
            LoggerFactory.getLogger(FileImportErrorHandler.class);

    public void handle(ErrorMessage message) {
        Throwable failure = message.getPayload();
        Object failedPayload = null;

        if (failure instanceof MessagingException messagingFailure) {
            Message<?> failedMessage = messagingFailure.getFailedMessage();
            if (failedMessage != null) {
                failedPayload = failedMessage.getPayload();
            }
        }

        String source = "unknown";
        if (failedPayload instanceof java.io.File file) {
            source = file.getAbsolutePath();
        } else if (failedPayload instanceof ImportCandidate candidate) {
            source = candidate.file().getAbsolutePath();
        } else if (failedPayload instanceof NormalizedImport item) {
            source = item.source().getAbsolutePath();
        }

        log.error("fileImport error, source={}", source, failure);
        // TODO: lưu incident theo correlation/requestId và kích hoạt redrive.
    }
}
~~~

Không nên in nội dung tệp hoặc dữ liệu định danh nhạy cảm vào log. `ErrorMessage` cho phép kiểm tra exception và message thất bại, nhưng khả năng tìm được failed message phụ thuộc nơi exception phát sinh. Thực hành tốt là gắn `sourcePath` và correlation ID ổn định vào header ngay đầu flow hoặc duy trì trạng thái xử lý trong repository.

## 8. Độ tin cậy: file filter, idempotency và giao dịch

### 8.1. `preventDuplicates(true)` có giới hạn

`preventDuplicates(true)` sử dụng bộ lọc tiếp nhận file kiểu `AcceptOnceFileListFilter` trong bộ nhớ. Nó giảm khả năng một file bị poll lại trong một phiên chạy nhưng **không** là bảo đảm exactly-once:

- Sau khi ứng dụng restart, trạng thái accept-once trong RAM mất. File còn ở `inbox` có thể được đọc lại.
- Khi file được adapter đánh dấu *accepted* nhưng handler sau đó lỗi, file thường **không được chọn lại trong cùng phiên chạy** chỉ vì đã có kỳ poll mới. Cần chính sách bỏ dấu đã đọc, chuyển file sang khu vực retry hoặc redrive có kiểm soát.
- Hai instance có bộ lọc RAM riêng đều có thể lấy cùng một file trên filesystem dùng chung.
- Việc nhận file một lần không bảo đảm side effect một lần, vì DB commit, HTTP request và chuyển file không cùng một giao dịch nguyên tử.

Với yêu cầu tồn tại trạng thái qua restart, xem xét `FileSystemPersistentAcceptOnceFileListFilter` cùng `ConcurrentMetadataStore` có khả năng lưu bền. Với nhiều node, dùng metadata store chung (ví dụ Redis) và cơ chế claim/lock tương thích filesystem, đồng thời bảo đảm khóa idempotency ở downstream. Nếu metadata bị đánh dấu trước khi xử lý xong, phải có quy trình recovery rõ ràng để không mất tệp.

### 8.2. Quy trình xử lý an toàn hơn

Một hệ thống thực tế có thể tổ chức như sau:

1. **Bàn giao file:** producer ghi `name.writing`, flush/close và rename sang `name.ready.csv`. Đừng chỉ kiểm tra mtime rồi đoán file đã ghi xong.
2. **Claim:** consumer tạo trạng thái `RECEIVED/PROCESSING` với unique key của file (hoặc request ID) ở kho dữ liệu bền vững. Khi có nhiều node, chỉ một node claim thành công.
3. **Kiểm tra và định tuyến:** dữ liệu sai → `REJECTED` và quarantine; dữ liệu đúng → chuyển về model nội bộ rồi gửi sang adapter.
4. **Side effect idempotent:** DB ghi bằng unique constraint theo `(sourceSystem, requestId)`; API downstream dùng idempotency key ổn định; broker consumer cũng phải chống duplicate.
5. **Kết thúc:** ghi trạng thái `COMPLETED` sau khi xác nhận nghiệp vụ, rồi archive. Nếu archive thất bại, lần sau nhận diện `COMPLETED` và có thể chỉ lặp lại bước archive.
6. **Khôi phục:** lỗi có thể thử lại thì retry giới hạn số lần, có backoff và trạng thái `RETRY_PENDING`; lỗi dữ liệu được quarantine; lỗi không thể khôi phục có cảnh báo và thao tác redrive được ghi audit.

### 8.3. Phân loại các trường hợp thất bại

| Tình huống | Xử lý đề xuất | Điều cần tránh |
| --- | --- | --- |
| Sai header, thiếu trường, số lượng không hợp lệ | `rejectedImports`; lưu reason và raw file | Im lặng bỏ message |
| Không đọc được file, quyền truy cập sai | `fileImportErrors`; ghi incident; redrive sau khi sửa quyền | Retry liên tục không giới hạn |
| HTTP timeout, đối tác có thể đã xử lý | Retry với cùng idempotency key và kiểm tra trạng thái phía đối tác | Tạo request ID mới mỗi lần retry |
| DB commit thành công, move file lỗi | Đánh dấu completed bền vững, lần sau chỉ archive | Ghi dữ liệu nghiệp vụ thêm lần nữa |
| Trạng thái filter lưu bền nhưng consumer chết | Recovery/reset metadata có kiểm soát, đối chiếu processing state | Coi accepted đồng nghĩa completed |
| Hai pod cùng đọc file | Claim chung/lock + idempotency ở downstream | Dựa vào `preventDuplicates(true)` riêng từng pod |
| Tệp chứa 10.000 dòng | Streaming/batching, cân nhắc `split()` và `aggregate()`, có chính sách partial success | Đọc hết vào RAM rồi gọi một transaction dài |

Nói cách khác, **file lock, file filter và idempotency giải quyết các vấn đề khác nhau**. File lock có thể hạn chế hai tiến trình cùng mở file; accept-once hạn chế phát lại từ nguồn; idempotency bảo vệ tác dụng phụ nghiệp vụ khi message bị phát lại bất cứ lý do gì.

## 9. Chạy thử theo từng đường đi của flow

Trước khi thử, phải có bean cài đặt `ImportApplicationService` và `FileImportArchive`. Trong môi trường sandbox, các adapter này có thể ghi kết quả vào database test hoặc file output được đặt tên theo `requestId`; bài không giả định một endpoint đối tác thật. Đối chiếu output và log với từng tình huống sau.

**Kịch bản A — tệp ORDER hợp lệ**

1. Chạy ứng dụng; tạo `data/inbox/order-001.writing` chứa mẫu `ORDER` ở đầu bài.
2. Đóng file, đổi tên thành `order-001.ready.csv`.
3. Adapter phát `File`; parser sinh `ImportCandidate(valid=true)`; normalizer tạo `NormalizedImport(ORDER, req-1001, SKU-42, 3)`.
4. Router chuyển sang `orderImports`; handler gọi `applyOrder` và sau đó `markProcessed`.
5. Kiểm tra đúng request ID, đúng quantity, tệp được archive và không bị poll tiếp.

**Kịch bản B — tệp STOCK hợp lệ:** tạo `stock-001.ready.csv` có dòng `STOCK,req-1002,SKU-42,-3`. Chỉ `applyStockDelta` được gọi với `-3`; handler ORDER không được kích hoạt.

**Kịch bản C — lỗi hợp đồng:** tạo `bad-001.ready.csv` chứa `ORDER,req-1003,SKU-42,abc`. Parser tạo candidate có lỗi `quantity phải là số nguyên 32-bit`; filter gửi sang `rejectedImports`, không gọi adapter nghiệp vụ. Xác nhận raw file và reason có mặt trong quarantine.

**Kịch bản D — lỗi kỹ thuật:** cho service ném exception ở `applyOrder`. Xác nhận `fileImportErrors` ghi sự cố và file chưa được đánh dấu processed. Sau khi sửa lỗi, thực hiện redrive theo cơ chế của ứng dụng; nếu request đã thành công ở downstream, adapter phải nhận diện duplicate và không tạo thêm side effect.

**Kịch bản E — file chưa hoàn tất:** chỉ tạo `order-002.writing`. Kiểm tra adapter không nhận trong nhiều kỳ poll; chỉ sau rename sang `.ready.csv` mới bắt đầu xử lý.

### Kiểm thử tự động nên chia ba lớp

| Lớp | Ví dụ kiểm tra | Phạm vi |
| --- | --- | --- |
| Unit test parser | Đúng hai dòng; thiếu header; mã dài > 64; số nguyên overflow; số lượng âm của ORDER | Cú pháp + quy tắc dữ liệu |
| Unit test transformer/handler | Candidate hợp lệ → enum/int đúng; service được gọi trước archive | Mapping + phối hợp nghiệp vụ |
| Integration test | Ghi file vào `@TempDir`, đợi poll có timeout, assert output/quarantine/error, thử restart/redrive | Nối các endpoint và tác dụng phụ thực |

Ví dụ unit test độc lập cho parser:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CsvImportParserTest {
    @TempDir Path tempDir;

    @Test
    void rejectsNonNumericQuantity() throws Exception {
        Path file = tempDir.resolve("bad.ready.csv");
        Files.writeString(file,
                "type,requestId,sku,quantity\n" +
                "ORDER,req-9,SKU-1,abc\n",
                StandardCharsets.UTF_8);

        ImportCandidate result = new CsvImportParser().parse(file.toFile());

        assertFalse(result.valid());
        assertTrue(result.errors().stream()
                .anyMatch(e -> e.contains("số nguyên")));
    }
}
~~~

Với `@SpringBootTest`, có thể dùng `@DynamicPropertySource` cấu hình `app.import.inbox` trỏ đến thư mục tạm và mock/stub các adapter đích. Vì polling bất đồng bộ theo thời gian, cần công cụ chờ có timeout hoặc kiểm tra trạng thái đến khi đạt điều kiện; tránh `Thread.sleep` cố định khiến test vừa chậm vừa dễ chập chờn. Đừng chạy test file intake với đường dẫn của môi trường production.

### Ma trận kết quả mong đợi

| Đầu vào | Kết quả |
| --- | --- |
| `ORDER,req-1,SKU-1,2` | Order handler được gọi, archive thành công |
| `STOCK,req-2,SKU-1,-2` | Stock handler được gọi với delta âm |
| `ORDER,req-3,SKU-1,0` | Reject: quantity ORDER không hợp lệ |
| `STOCK,req-4,SKU-1,0` | Reject: quantity STOCK không hợp lệ |
| `REFUND,req-5,SKU-1,1` | Reject: loại chưa hỗ trợ |
| Dữ liệu ba dòng hoặc header sai | Reject: hợp đồng tệp sai |
| `quantity=2147483648` | Reject: ngoài miền số nguyên 32-bit |
| Chỉ có tệp `.writing` | Không phát message |
| Handler ném lỗi | Error channel nhận incident, không archive |
| Cùng `requestId` phát lại | Nghiệp vụ không có side effect lần hai |

## 10. Quan sát, tải và tiêu chí nghiệm thu

Ở hệ thống tích hợp, log cần có `requestId`, tên file, định danh nhánh, thời gian bắt đầu/kết thúc và kết quả. Metric có thể gồm `files_discovered_total`, `files_rejected_total{reason}`, `files_processed_total{type}`, `file_processing_duration_seconds`, `file_import_errors_total{stage}` và tuổi tệp đang chờ lâu nhất. Không đặt request ID hoặc filename làm label metric vì cardinality tăng không giới hạn.

`fixedDelay` và `maxMessagesPerPoll` chỉ điều tiết cách lấy message từ nguồn. Với `DirectChannel`, handler đồng bộ chậm sẽ chiếm thời gian poll. Nếu thêm executor/queue để tăng throughput, cần giới hạn dung lượng hàng đợi, timeout, circuit breaker, cơ chế claim, thứ tự xử lý cùng SKU và nơi nhận lỗi ở luồng bất đồng bộ. Với DB/broker, cân nhắc ranh giới transaction và outbox/inbox để tránh mất sự kiện khi hai hệ thống commit khác nhau.

**Tiêu chí hoàn thành bài thực hành:**

- File đã hoàn tất được nhận đúng một lần trong kịch bản bình thường; file `.writing` không được đọc.
- Đầu vào sai được giải thích rõ và cách ly; không chạy adapter nghiệp vụ.
- Dữ liệu đúng được chuẩn hóa và route đến đúng ORDER hoặc STOCK handler.
- Lỗi downstream được ghi nhận, có quy trình retry/redrive; tệp không bị archive khi nghiệp vụ chưa thành công.
- Restart, replay cùng `requestId` và lỗi archive không gây tác dụng phụ trùng ở downstream.
- Có kiểm thử parser, định tuyến, nhánh từ chối, nhánh lỗi và luồng file đầu-cuối.

Khi mở rộng bài này sang các luồng HTTP, JDBC, cache, RabbitMQ/Kafka hoặc Spring Integration adapter khác, phần nhận/kiểm tra/biến đổi/định tuyến vẫn là cấu trúc EIP có thể tái sử dụng. Thứ cần thiết kế cẩn thận nhất là **hợp đồng message, idempotency, giao dịch, ranh giới lỗi và khả năng quan sát**.

## Tài liệu tham khảo

- [Spring Integration Reference — File Reading](https://docs.spring.io/spring-integration/reference/file/reading.html)
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html)
- [Spring Integration Reference — Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html)
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
