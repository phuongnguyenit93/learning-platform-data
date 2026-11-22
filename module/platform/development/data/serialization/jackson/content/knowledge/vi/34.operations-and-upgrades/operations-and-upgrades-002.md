# Theo dõi tỷ lệ lỗi theo loại tài liệu và phiên bản hợp đồng

Một hệ thống dùng Jackson thường tiếp nhận nhiều loại tài liệu: invoice, payment event, user profile, batch import hoặc file cấu hình. Mỗi loại có thể tồn tại qua nhiều phiên bản hợp đồng dữ liệu. Khi producer phát hành phiên bản mới, consumer nâng Jackson hoặc thay đổi DTO, một nhóm tài liệu có thể bắt đầu lỗi trong khi các nhóm khác vẫn hoạt động bình thường.

Nếu chỉ theo dõi tổng số lỗi deserialize, đội vận hành khó xác định lỗi tập trung ở loại tài liệu nào, phiên bản nào, và xảy ra ở bước parse, binding hay validation. Theo dõi cần gắn mỗi lần xử lý với một **document type**, một **contract version**, một **processing stage** và một **error category** có quy ước ổn định. Những chiều này cho phép dashboard phát hiện regression theo phiên bản, hỗ trợ rollout có kiểm soát và đưa ra quyết định rollback dựa trên dữ liệu.

Bài này trình bày cách định nghĩa tỷ lệ lỗi, phân loại exception Jackson, thiết kế metric có cardinality thấp, ghi log và trace có cấu trúc, xây dashboard và alert, rồi dùng các số liệu đó để quản lý thay đổi contract. Mục tiêu là phân biệt lỗi đầu vào dự kiến với lỗi vận hành của hệ thống, để cảnh báo phản ánh đúng rủi ro.

## 1. Vì sao phải theo dõi theo document type và contract version?

Giả sử một dịch vụ xử lý ba loại tài liệu:

- `invoice`: hóa đơn do hệ thống bán hàng phát hành.
- `payment_event`: sự kiện thanh toán từ message broker.
- `customer_profile`: hồ sơ khách hàng được đồng bộ định kỳ.

Mỗi loại có contract version riêng. Ví dụ, invoice có v1 và v2 trong giai đoạn migration; payment_event đang dùng v3; customer_profile chỉ có v1.

Nếu tỷ lệ lỗi tổng thể tăng từ 0,2% lên 1,5%, chỉ số tổng không cho biết nguyên nhân. Có thể invoice v2 lỗi 20% nhưng traffic chỉ chiếm 2%; hoặc payment_event v3 lỗi 2% trên phần lớn traffic. Hai tình huống đòi hỏi cách xử lý khác nhau.

Theo dõi theo type và version trả lời được:

- Loại tài liệu nào bị ảnh hưởng?
- Phiên bản nào bắt đầu lỗi sau deploy?
- Consumer cũ có đang nhận contract mới ngoài dự kiến không?
- Lỗi là JSON/XML không hợp lệ, sai kiểu, unknown field hay lỗi nghiệp vụ?
- Tỷ lệ lỗi tăng do traffic thay đổi hay do chất lượng dữ liệu?
- Có nên rollback producer, rollback consumer hay tạm dừng rollout?

Không nên chỉ ghi nhận exception tổng. Cần một mô hình sự kiện xử lý tài liệu nhất quán ở mọi entry point dùng Jackson.

## 2. Phân biệt document type, contract version và application version

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

| Dimension | Ý nghĩa | Ví dụ |
|---|---|---|
| Document type | Nhóm tài liệu theo contract/nghiệp vụ | `invoice`, `payment_event` |
| Contract version | Phiên bản schema/wire contract của tài liệu | `v1`, `v2`, `2026-04` |
| Application version | Phiên bản ứng dụng đang chạy | `billing-service 4.8.1` |
| Jackson version | Phiên bản thư viện xử lý | `jackson-databind 2.x` |

Khi lỗi tăng sau khi nâng Jackson, application version và library version giúp xác định thay đổi runtime. Khi lỗi chỉ xuất hiện với invoice v2, contract version giúp xác định dữ liệu bị ảnh hưởng.

Không dùng application version thay cho contract version. Một ứng dụng có thể đọc nhiều contract version cùng lúc; một contract version cũng có thể được nhiều phiên bản ứng dụng hỗ trợ.

### 2.1. Định nghĩa document type bằng danh sách hữu hạn

Nên có registry hoặc enum cho các loại tài liệu đã biết:

~~~java
public enum DocumentType {
    INVOICE("invoice"),
    PAYMENT_EVENT("payment_event"),
    CUSTOMER_PROFILE("customer_profile"),
    UNKNOWN("unknown");

    private final String metricKey;

    DocumentType(String metricKey) {
        this.metricKey = metricKey;
    }

    public String metricKey() {
        return metricKey;
    }
}
~~~

Không lấy tên class bất kỳ hoặc tên file do người dùng gửi làm metric label. Tên class proxy, tên plugin hoặc giá trị do input điều khiển có thể tạo cardinality lớn.

### 2.2. Contract version phải có cách chuẩn hóa

Một contract version nên là định danh đã được công bố và có số lượng hữu hạn trong một thời điểm vận hành. Ví dụ:

~~~java
public enum ContractVersion {
    V1("v1"),
    V2("v2"),
    V3("v3"),
    UNKNOWN("unknown"),
    UNSUPPORTED("unsupported");

    private final String metricKey;

    ContractVersion(String metricKey) {
        this.metricKey = metricKey;
    }

    public String metricKey() {
        return metricKey;
    }
}
~~~

Nếu header chứa `v2-beta-20261112-build-93841`, không đưa nguyên chuỗi đó vào metric label. Chuẩn hóa thành một bucket có kiểm soát như `v2`, `pre_release` hoặc `unknown`; giữ chi tiết build ở log/trace nếu cần.

### 2.3. Version phải đến từ nguồn đáng tin cậy và dễ truy xuất

Ưu tiên xác định type/version từ routing metadata hoặc message headers đã được gateway/producer kiểm soát. Nếu version chỉ nằm trong body, có thể chưa đọc được khi JSON sai cú pháp.

Khi không thể xác định, ghi `unknown`. Không nên chạy một parser phụ tùy tiện chỉ để lấy version từ tài liệu lỗi vì nó có thể lặp lại chi phí parse hoặc tạo thêm bề mặt tấn công.

Nếu body chứa discriminator hoặc schema id, đọc nó trong quá trình parse bằng cơ chế đã thiết kế cho contract đó. Đừng suy ra version từ field tùy ý nếu chưa có quy ước.

## 3. Định nghĩa chính xác một lần xử lý và tỷ lệ lỗi

Trước khi viết metric, cần thống nhất đơn vị đếm.

Một **processing attempt** là một lần consumer thử xử lý một tài liệu. Nếu message bị retry ba lần, có thể có ba attempts cho một logical document. Một **logical document** là tài liệu nghiệp vụ duy nhất, có thể trải qua nhiều attempt.

Hai số liệu này trả lời câu hỏi khác nhau:

- Attempt rate phản ánh tải và hành vi retry.
- Logical document outcome phản ánh tỷ lệ tài liệu cuối cùng được chấp nhận hoặc bị từ chối.

Không cộng lẫn hai loại vào cùng một denominator.

### 3.1. Chọn outcome có ý nghĩa vận hành

Một mô hình đơn giản có ba outcome:

| Outcome | Ý nghĩa | Ví dụ |
|---|---|---|
| `accepted` | Tài liệu được parse, bind và chấp nhận theo contract | Deserialize và validation thành công |
| `rejected` | Tài liệu không hợp lệ theo input contract hoặc validation | Sai JSON, sai kiểu, unknown discriminator, thiếu field bắt buộc |
| `failed` | Hệ thống không thể xử lý do lỗi nội bộ/hạ tầng | Cấu hình mapper sai, lỗi storage, dependency unavailable |

Có thể có thêm `ignored`, `quarantined` hoặc `dead_lettered` nếu đó là outcome nghiệp vụ rõ ràng. Hãy giữ tập outcome nhỏ và ổn định.

Một payload không hợp lệ do client thường là rejection, không nhất thiết là sự cố availability của dịch vụ. Ngược lại, `InvalidDefinitionException` có thể chỉ ra DTO hoặc cấu hình Jackson ở server bị lỗi; không nên đếm nó như lỗi dữ liệu của client.

### 3.2. Công thức tỷ lệ rejection và internal failure

Với cùng một tập document type và contract version:

[
	ext{rejection rate} =
rac{	ext{rejected documents}}{	ext{processed documents}}
]

[
	ext{internal failure rate} =
rac{	ext{failed documents}}{	ext{processed documents}}
]

[
	ext{acceptance rate} =
rac{	ext{accepted documents}}{	ext{processed documents}}
]

Trong đó:

[
	ext{processed documents} =
	ext{accepted} + 	ext{rejected} + 	ext{failed}
]

Ba outcome phải loại trừ nhau ở cùng một ranh giới xử lý. Nếu một tài liệu vừa bị reject ở parser vừa được tính failed ở service handler, metric sẽ double-count.

### 3.3. Chọn denominator nhất quán

Một số đội dùng số message nhận vào làm denominator; đội khác dùng số attempt hoàn tất. Cả hai có thể hữu ích, nhưng không thể so sánh nếu định nghĩa khác nhau.

Ví dụ:

- `received_total`: số tài liệu được nhận.
- `processing_attempts_total`: số lần bắt đầu xử lý.
- `processing_outcomes_total`: số lần xử lý kết thúc với accepted/rejected/failed.
- `logical_documents_completed_total`: số document ID duy nhất đã có kết quả cuối cùng.

Nếu retry diễn ra bên trong consumer, hãy quyết định metric outcome đếm từng attempt hay chỉ kết quả cuối. Có thể theo dõi cả hai, nhưng tên metric và dashboard phải ghi rõ.

### 3.4. Không tính tài liệu đang xử lý vào mẫu số hoàn tất

Counter outcome chỉ tăng khi xử lý kết thúc. Để theo dõi backlog hoặc tài liệu đang chờ, dùng queue depth, in-flight gauge và age of oldest message riêng. Đừng trộn số liệu chưa hoàn tất vào tỷ lệ lỗi.

## 4. Phân loại lỗi Jackson theo nhóm ổn định

Jackson có nhiều exception class. Dashboard không nên tạo một metric series cho từng class hoặc message. Thay vào đó, map exception vào một tập category hữu hạn.

Một taxonomy thực tế:

| Category | Ví dụ | Outcome thường gặp |
|---|---|---|
| `syntax_error` | JSON/XML sai cú pháp, token bị hỏng | rejected |
| `type_mismatch` | Object nhận scalar, array nhận object | rejected |
| `invalid_format` | String không chuyển được sang số/ngày | rejected |
| `unknown_property` | Field không được model nhận diện | rejected hoặc accepted theo policy |
| `missing_required` | Thiếu discriminator/creator property bắt buộc | rejected |
| `unsupported_type` | Unknown polymorphic type id | rejected |
| `mapping_error` | Lỗi binding tổng quát | rejected hoặc cần phân tích |
| `definition_error` | DTO/serializer/deserializer cấu hình sai | failed |
| `constraint_violation` | Bean Validation/domain input constraint | rejected |
| `input_io` | Stream bị ngắt hoặc đọc lỗi | tùy nguồn, rejected hoặc failed |
| `timeout` | Timeout khi đọc/nhận tài liệu | failed hoặc retry |
| `dependency_error` | Database/broker/downstream không sẵn sàng | failed |
| `business_rejection` | Quy tắc nghiệp vụ từ chối dữ liệu | rejected |

Không phải mọi category đều đến từ Jackson. Mục đích là chuẩn hóa outcome của toàn bộ document pipeline, đồng thời giữ stage để phân biệt parser với business layer.

### 4.1. Các exception Jackson thường gặp

| Exception | Ý nghĩa thường gặp | Category gợi ý |
|---|---|---|
| `JsonParseException` | JSON syntax/token error | `syntax_error` |
| `InvalidTypeIdException` | Polymorphic type id không hợp lệ/không được biết | `unsupported_type` |
| `UnrecognizedPropertyException` | JSON có property không được nhận diện | `unknown_property` |
| `InvalidFormatException` | Giá trị không chuyển được sang kiểu đích | `invalid_format` |
| `MismatchedInputException` | Hình dạng/token không phù hợp kiểu đích | `type_mismatch` |
| `InvalidDefinitionException` | Model hoặc cấu hình serializer/deserializer không hợp lệ | `definition_error` |
| `JsonMappingException` | Lỗi databinding tổng quát | `mapping_error` |

Thứ tự phân loại rất quan trọng vì nhiều exception chuyên biệt kế thừa từ `JsonMappingException` hoặc từ một subtype khác. Kiểm tra exception cụ thể trước, superclass sau.

### 4.2. Unknown property không phải lúc nào cũng là lỗi

Nếu mapper tắt `FAIL_ON_UNKNOWN_PROPERTIES`, field lạ có thể bị bỏ qua. Nếu dùng `@JsonAnySetter`, field có thể được lưu lại. Vì vậy, metric `unknown_property` chỉ tăng khi chính sách ứng dụng thực sự xem đó là rejection.

Nên ghi nhận cấu hình contract/version nào đang strict và version nào tolerant. Không dùng một category chung để mô tả một field bị bỏ qua như thể deserialize thất bại.

## 5. Viết bộ phân loại exception có kiểm soát

Có thể gom mapping exception thành một enum nội bộ:

~~~java
public enum ErrorCategory {
    SYNTAX_ERROR("syntax_error"),
    UNSUPPORTED_TYPE("unsupported_type"),
    UNKNOWN_PROPERTY("unknown_property"),
    INVALID_FORMAT("invalid_format"),
    TYPE_MISMATCH("type_mismatch"),
    DEFINITION_ERROR("definition_error"),
    MAPPING_ERROR("mapping_error"),
    INPUT_IO("input_io"),
    CONSTRAINT_VIOLATION("constraint_violation"),
    BUSINESS_REJECTION("business_rejection"),
    DEPENDENCY_ERROR("dependency_error"),
    UNKNOWN("unknown");

    private final String metricKey;

    ErrorCategory(String metricKey) {
        this.metricKey = metricKey;
    }

    public String metricKey() {
        return metricKey;
    }
}
~~~

Bộ phân loại:

~~~java
public final class JacksonErrorClassifier {
    private JacksonErrorClassifier() {
    }

    public static ErrorCategory classify(JsonProcessingException ex) {
        if (ex instanceof InvalidDefinitionException) {
            return ErrorCategory.DEFINITION_ERROR;
        }
        if (ex instanceof InvalidTypeIdException) {
            return ErrorCategory.UNSUPPORTED_TYPE;
        }
        if (ex instanceof UnrecognizedPropertyException) {
            return ErrorCategory.UNKNOWN_PROPERTY;
        }
        if (ex instanceof InvalidFormatException) {
            return ErrorCategory.INVALID_FORMAT;
        }
        if (ex instanceof MismatchedInputException) {
            return ErrorCategory.TYPE_MISMATCH;
        }
        if (ex instanceof JsonParseException) {
            return ErrorCategory.SYNTAX_ERROR;
        }
        if (ex instanceof JsonMappingException) {
            return ErrorCategory.MAPPING_ERROR;
        }
        return ErrorCategory.UNKNOWN;
    }
}
~~~

Đây là phân loại ban đầu cho JSON Databind. Với XML, YAML hoặc CSV, bổ sung mapping theo exception của parser/provider tương ứng, nhưng vẫn quy về cùng tập category cấp ứng dụng khi semantics tương đương.

### 5.1. Không phân loại bằng cách tìm từ trong message

Không viết logic như:

~~~java
if (ex.getMessage().contains("not a valid Integer")) {
    // ...
}
~~~

Message text có thể thay đổi theo Jackson version, locale, parser hoặc kiểu target. Hãy dùng exception type và metadata công khai; nếu cần phân biệt sâu hơn, đặt logic ở adapter riêng cho từng dataformat.

### 5.2. Phân biệt lỗi input với lỗi cấu hình server

`InvalidDefinitionException` thường chỉ ra Jackson không thể xử lý model hoặc cấu hình. Ví dụ DTO thiếu creator phù hợp hoặc serializer được đăng ký sai. Trả lỗi này như một client validation error sẽ che giấu bug server.

Một policy hữu ích:

- Parse/binding error do payload: `rejected`.
- Bean/domain validation không đạt: `rejected`.
- Definition/configuration error: `failed`, phát cảnh báo vận hành.
- Dependency/timeout: `failed` hoặc retry state theo pipeline.

## 6. Chọn điểm đo trong document pipeline

Một document pipeline thường có nhiều bước:

~~~text
Receive
  |
  v
Resolve document type / contract version
  |
  v
Read bytes / enforce size limits
  |
  v
Parse + Jackson databind
  |
  v
Schema / Bean Validation
  |
  v
Business validation
  |
  v
Persist / publish / call dependency
  |
  v
Final outcome
~~~

Đo riêng các stage để tìm nguyên nhân:

| Stage | Chỉ số hữu ích |
|---|---|
| `ingress` | Số tài liệu nhận, kích thước, content type |
| `parse_bind` | Accepted/rejected theo exception category, thời gian deserialize |
| `schema_validation` | Lỗi schema hoặc contract constraint |
| `business_validation` | Rejection theo rule code |
| `persistence` | Lỗi database, conflict, timeout |
| `publish` | Lỗi broker/downstream |
| `end_to_end` | Outcome cuối cùng và tổng latency |

Không chỉ instrument riêng `ObjectMapper.readValue()` nếu câu hỏi vận hành là “tài liệu đã được xử lý thành công chưa?”. Một lần deserialize thành công vẫn có thể thất bại ở validation hoặc persistence.

Ngược lại, không nên gộp mọi stage vào một category duy nhất vì sẽ khó xác định phần nào cần rollback hoặc sửa.

## 7. Thiết kế metric có cardinality thấp

Metric labels phải có số giá trị hữu hạn và được kiểm soát. Các chiều thường hữu ích:

- `document_type`: invoice, payment_event, customer_profile.
- `contract_version`: v1, v2, v3, unknown.
- `stage`: parse_bind, validation, persistence.
- `outcome`: accepted, rejected, failed.
- `error_category`: tập category đã định nghĩa.

Ví dụ metric:

~~~text
document_processing_outcomes_total{
  document_type="invoice",
  contract_version="v2",
  stage="parse_bind",
  outcome="rejected",
  error_category="invalid_format"
}
~~~

Một metric khác đo thời gian:

~~~text
document_processing_duration_seconds{
  document_type="invoice",
  contract_version="v2",
  stage="parse_bind",
  outcome="accepted"
}
~~~

### 7.1. Không đưa dữ liệu động vào label

Không dùng các giá trị sau làm metric label:

- Document ID, invoice ID, customer ID.
- Request ID, correlation ID, trace ID.
- Raw filename hoặc URL.
- Raw exception message.
- JSON property path có thể chứa map key do input cung cấp.
- Raw class name hoặc type id tùy ý.
- Tenant ID nếu số tenant lớn hoặc thay đổi liên tục.
- Version string tự do do producer gửi.

Những giá trị này làm số time series tăng theo dữ liệu đầu vào, gây áp lực lên Prometheus/Metrics backend và có thể làm chi phí lưu trữ tăng mạnh.

Giữ chúng trong log hoặc trace theo chính sách bảo mật và retention phù hợp.

### 7.2. Chuẩn hóa unknown và unsupported

Nếu input gửi version không nhận diện được, không gắn raw value vào label. Dùng bucket `unknown` hoặc `unsupported`; nếu cần điều tra chính xác, ghi version raw đã sanitize trong log có quyền truy cập giới hạn.

Tương tự, type id polymorphic lạ nên map thành `unsupported_type` trong metric. Không tạo một series mới cho mỗi chuỗi attacker gửi.

### 7.3. Giới hạn số dimension kết hợp

Ngay cả từng label có cardinality thấp, tích của nhiều label vẫn có thể lớn. Ví dụ 20 document types × 8 versions × 7 stages × 3 outcomes × 12 categories đã tạo ra hàng chục nghìn tổ hợp tiềm năng.

Chỉ thêm dimension nếu dashboard hoặc alert thực sự dùng nó. Có thể tách metric tổng hợp khỏi metric chi tiết, hoặc chỉ gắn `error_category` cho counter lỗi thay vì cả success series.

## 8. Instrument bằng Micrometer

Micrometer cung cấp Counter, Timer, DistributionSummary và Gauge. Với Spring Boot, registry thường được cấu hình tự động; ứng dụng có thể nhận `MeterRegistry` qua dependency injection.

Một descriptor đã chuẩn hóa:

~~~java
public record DocumentDescriptor(
        String documentType,
        String contractVersion
) {
    public DocumentDescriptor {
        documentType = normalizeType(documentType);
        contractVersion = normalizeVersion(contractVersion);
    }

    private static String normalizeType(String value) {
        return switch (value == null ? "" : value) {
            case "invoice" -> "invoice";
            case "payment_event" -> "payment_event";
            case "customer_profile" -> "customer_profile";
            default -> "unknown";
        };
    }

    private static String normalizeVersion(String value) {
        return switch (value == null ? "" : value) {
            case "v1" -> "v1";
            case "v2" -> "v2";
            case "v3" -> "v3";
            default -> "unknown";
        };
    }
}
~~~

Chỉ đưa giá trị đã chuẩn hóa vào metric. Không truyền trực tiếp header hoặc body value chưa kiểm soát.

### 8.1. Counter cho processing outcomes

~~~java
public final class DocumentMetrics {
    private final MeterRegistry registry;

    public DocumentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordOutcome(
            DocumentDescriptor descriptor,
            String stage,
            String outcome,
            String errorCategory
    ) {
        Counter.builder("document_processing_outcomes")
                .description("Completed document processing outcomes")
                .tag("document_type", descriptor.documentType())
                .tag("contract_version", descriptor.contractVersion())
                .tag("stage", stage)
                .tag("outcome", outcome)
                .tag("error_category", errorCategory)
                .register(registry)
                .increment();
    }
}
~~~

Tên metric ở Micrometer thường được export theo naming convention của registry. Ví dụ Prometheus có thể hiển thị counter với hậu tố `_total`. Hãy kiểm tra tên thực tế trên endpoint metrics của ứng dụng.

### 8.2. Timer cho từng stage

~~~java
public <T> T measure(
        DocumentDescriptor descriptor,
        String stage,
        Callable<T> operation
) throws Exception {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "accepted";

    try {
        return operation.call();
    } catch (JsonProcessingException ex) {
        outcome = "rejected";
        throw ex;
    } catch (Exception ex) {
        outcome = "failed";
        throw ex;
    } finally {
        Timer timer = Timer.builder("document_processing_duration")
                .description("Time spent processing a document stage")
                .tag("document_type", descriptor.documentType())
                .tag("contract_version", descriptor.contractVersion())
                .tag("stage", stage)
                .tag("outcome", outcome)
                .register(registry);

        sample.stop(timer);
    }
}
~~~

Đoạn code trên phân loại lỗi Jackson thành rejection và các exception còn lại thành failure để minh họa Timer theo outcome. Trong pipeline thật, có thể truyền một bộ phân loại theo stage để tách lỗi validation, business rejection và dependency failure chính xác hơn.

### 8.3. Wrapper deserialize có outcome chính xác

Ví dụ dưới đây thể hiện một cách triển khai rõ ràng cho bước Jackson binding:

~~~java
public <T> T deserialize(
        byte[] payload,
        Class<T> targetType,
        DocumentDescriptor descriptor,
        ObjectMapper mapper,
        MeterRegistry registry
) throws IOException {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "accepted";
    String errorCategory = "none";

    try {
        return mapper.readValue(payload, targetType);
    } catch (JsonProcessingException ex) {
        outcome = "rejected";
        errorCategory = JacksonErrorClassifier
                .classify(ex)
                .metricKey();
        throw ex;
    } catch (IOException ex) {
        outcome = "failed";
        errorCategory = "input_io";
        throw ex;
    } finally {
        Timer timer = Timer.builder("document_deserialization_duration")
                .tag("document_type", descriptor.documentType())
                .tag("contract_version", descriptor.contractVersion())
                .tag("outcome", outcome)
                .register(registry);

        sample.stop(timer);

        Counter.builder("document_deserialization_outcomes")
                .tag("document_type", descriptor.documentType())
                .tag("contract_version", descriptor.contractVersion())
                .tag("outcome", outcome)
                .tag("error_category", errorCategory)
                .register(registry)
                .increment();
    }
}
~~~

Trong Java, `JsonProcessingException` là một loại IOException nên cần catch trước. Lỗi Jackson mapping được phân loại là rejection trong ví dụ; lỗi I/O stream được xem là failed. Hệ thống thực tế có thể phân biệt client disconnect, broker read error và file storage error theo nguồn.

Nếu có runtime exception do lỗi code hoặc validation, bắt và phân loại ở wrapper pipeline bên ngoài; không ép mọi RuntimeException thành lỗi JSON.

### 8.4. Ghi nhận stage validation riêng

Không gắn lỗi Bean Validation vào metric deserialize. Deserialize có thể thành công nhưng object không đạt constraint. Ghi một outcome riêng cho stage validation:

~~~java
Set<ConstraintViolation<Document>> violations =
        validator.validate(document);

if (violations.isEmpty()) {
    metrics.recordOutcome(descriptor, "validation", "accepted", "none");
} else {
    metrics.recordOutcome(
            descriptor,
            "validation",
            "rejected",
            "constraint_violation"
    );
    throw new DocumentValidationException(violations);
}
~~~

Đoạn code này minh họa policy. Nếu validator trả về Set<ConstraintViolation<T>> thay vì ném exception, hãy ghi outcome dựa trên tập vi phạm thực tế.

## 9. Đếm logical document và retry đúng cách

Retry có thể làm tỷ lệ lỗi bị hiểu sai nếu không định nghĩa metric.

Ví dụ một message lỗi database được thử 5 lần rồi thành công:

- Attempt-level: 4 failed attempts, 1 accepted attempt.
- Logical document: 1 document cuối cùng accepted.
- Retry metric: 4 retry attempts.

Nếu dashboard dùng attempt-level, failure ratio phản ánh mức độ khó xử lý và áp lực retry. Nếu dashboard dùng logical document, nó phản ánh kết quả cuối cùng với producer.

Nên có metric riêng nếu cả hai đều quan trọng:

~~~text
document_processing_attempts_total{outcome="failed"}
document_processing_final_outcomes_total{outcome="accepted"}
document_processing_retries_total{reason="dependency_error"}
~~~

Không dùng document ID làm label để deduplicate. Nếu cần tính logical outcome chính xác, dùng state store, event ledger hoặc metric tại nơi quyết định kết quả cuối cùng, với idempotency key ở tầng ứng dụng.

## 10. Structured logging để điều tra một lỗi cụ thể

Metrics cho biết xu hướng tổng hợp; logs giúp tìm một lần xử lý cụ thể.

Một log event có thể gồm:

~~~json
{
  "event": "document_processing_rejected",
  "document_type": "invoice",
  "contract_version": "v2",
  "stage": "parse_bind",
  "error_category": "invalid_format",
  "exception_type": "InvalidFormatException",
  "property_path": "items[2].quantity",
  "correlation_id": "req-7f31",
  "application_version": "4.8.1"
}
~~~

Các trường này nên được ghi dưới dạng structured fields để truy vấn được. Không cần nhét mọi thứ vào một message text.

### 10.1. Dùng path Jackson nhưng giới hạn nội dung

Với `JsonMappingException`, có thể lấy:

- `getOriginalMessage()`: thông báo lỗi gốc.
- `getPathReference()`: path của object graph.
- `getLocation()`: vị trí parser nếu có.

Path có thể chứa map key do input cung cấp. Trước khi log, giới hạn độ dài và escape ký tự điều khiển. Nếu field/key có thể chứa dữ liệu nhạy cảm, chỉ log field path đã chuẩn hóa hoặc bỏ segment động.

Không parse `getMessage()` để suy ra error category. Dùng exception type để phân loại, path chỉ hỗ trợ chẩn đoán.

### 10.2. Không log toàn bộ payload mặc định

Raw document có thể chứa token, thông tin cá nhân, payment data hoặc bí mật. Chỉ log payload khi có cơ chế redaction và quyền truy cập phù hợp. Thường chỉ cần:

- Correlation ID.
- Document type/version.
- Error category và exception class.
- Path đã sanitize.
- Parser line/column nếu có.
- Payload size.
- Producer/source đã chuẩn hóa.

Nếu cần tái hiện lỗi, có thể lưu payload vào quarantine storage có mã hóa, retention ngắn, access control và audit trail thay vì ghi vào log chung.

## 11. Distributed tracing theo document stage

Trong hệ thống có broker, API gateway và nhiều consumer, trace giúp nối một document từ producer tới nơi lỗi.

Một trace có thể có span:

~~~text
receive-document
    |
    +-- resolve-contract
    |
    +-- deserialize
    |
    +-- validate-schema
    |
    +-- validate-business
    |
    +-- persist
    |
    +-- publish-result
~~~

Các span attributes hữu ích:

- `document.type`
- `contract.version`
- `processing.stage`
- `processing.outcome`
- `error.category`
- `application.version`

Giữ attribute values có cardinality thấp. Correlation ID hoặc document ID có thể nằm trong trace/log context, nhưng không nên biến chúng thành metric labels.

Khi có exception, đánh dấu span error và ghi exception theo convention của tracing library. Không ghi payload nhạy cảm hoặc raw exception message chứa dữ liệu đầu vào.

## 12. Dashboard cần trả lời câu hỏi vận hành

Một dashboard tốt không chỉ hiển thị tổng số exception. Nó cần cho người trực ca xác định phạm vi và mức độ ảnh hưởng.

Các panel nên có:

1. **Traffic theo document type/version:** số tài liệu nhận và xử lý.
2. **Acceptance/rejection/failure rate:** outcome theo từng type/version.
3. **Error category breakdown:** syntax, type mismatch, unknown property, unsupported type, definition error, validation.
4. **Latency theo stage:** p50/p95/p99 parse, validation và end-to-end.
5. **Version comparison:** phiên bản mới so với phiên bản cũ.
6. **Unknown/unsupported version:** số tài liệu không xác định hoặc ngoài tập hỗ trợ.
7. **Retry/dead-letter volume:** số lần retry, số tài liệu chuyển DLQ.
8. **Payload size:** phân phối kích thước tài liệu và outlier.

### 12.1. Tổng quan outcome

<text>Panel đầu tiên cần cho thấy tổng số accepted, rejected và failed trong cùng khoảng thời gian. Nếu chỉ hiển thị error count, người xem không biết traffic tăng hay tỷ lệ lỗi thực sự tăng.</text>

### 12.2. Heatmap theo document type và contract version

Bảng hoặc heatmap:

| Document type | v1 | v2 | v3 |
|---|---:|---:|---:|
| invoice | 0,2% | 4,8% | — |
| payment_event | — | 0,1% | 0,3% |
| customer_profile | 0,4% | 0,2% | — |

Các giá trị trên chỉ là ví dụ. Dashboard thực tế cần hiển thị cả số mẫu bên cạnh tỷ lệ. Một tỷ lệ 50% từ 2 tài liệu không có cùng ý nghĩa với 5% từ 100.000 tài liệu.

### 12.3. Error category theo stage

Nếu `invalid_format` tăng ở parse_bind, có thể producer đang gửi sai kiểu hoặc format. Nếu `constraint_violation` tăng ở business_validation, JSON vẫn bind thành công nhưng dữ liệu không còn thỏa rule. Nếu `definition_error` tăng sau deploy, cần xem xét regression ở model/configuration.

Tách category và stage giúp đội vận hành chuyển đúng nhóm xử lý.

## 13. Prometheus query cho tỷ lệ lỗi

Giả sử metric counter được export thành:

`document_processing_outcomes_total`

với labels `document_type`, `contract_version`, `stage`, `outcome`, `error_category`.

### 13.1. Rejection rate theo type/version

~~~promql
sum by (document_type, contract_version) (
  rate(document_processing_outcomes_total{outcome="rejected"}[5m])
)
/
sum by (document_type, contract_version) (
  rate(document_processing_outcomes_total[5m])
)
~~~

Kết quả là tỷ lệ rejection trên các outcome được ghi nhận trong cửa sổ 5 phút. Với traffic thấp, nên dùng cửa sổ dài hơn và kiểm tra số lượng mẫu trước khi alert.

### 13.2. Internal failure rate

~~~promql
sum by (document_type, contract_version) (
  rate(document_processing_outcomes_total{outcome="failed"}[10m])
)
/
sum by (document_type, contract_version) (
  rate(document_processing_outcomes_total[10m])
)
~~~

Internal failure thường phù hợp hơn để cảnh báo đội vận hành. Rejection do producer gửi dữ liệu sai có thể cần cảnh báo cho đội tích hợp hoặc producer owner, không nhất thiết page on-call của consumer.

### 13.3. Tỷ lệ theo error category

~~~promql
sum by (document_type, contract_version, error_category) (
  rate(document_processing_outcomes_total{outcome="rejected"}[10m])
)
~~~

Panel này cho biết category nào tăng. Có thể dùng topk để hiển thị nhóm lỗi có volume cao nhất:

~~~promql
topk(
  10,
  sum by (document_type, contract_version, error_category) (
    rate(document_processing_outcomes_total{outcome="rejected"}[10m])
  )
)
~~~

### 13.4. P95 latency theo type/version

Với Timer histogram được export theo Prometheus:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, document_type, contract_version) (
    rate(document_processing_duration_seconds_bucket[5m])
  )
)
~~~

Nếu Timer được ghi cho nhiều stage, thêm label stage vào grouping hoặc filter stage cần xem. Không gộp parse latency với end-to-end latency nếu chúng đại diện cho phạm vi khác nhau.

### 13.5. Xử lý denominator bằng 0

Khi không có traffic trong cửa sổ, tỷ lệ không có ý nghĩa. Dashboard nên hiển thị no data hoặc bỏ điểm đó; không diễn giải thành 0% lỗi.

Có thể dùng `clamp_min` để tránh phép chia cho zero trong một số query, nhưng điều đó có thể tạo tỷ lệ giả. Tốt hơn là kiểm tra volume và hiển thị trạng thái no traffic riêng.

## 14. Alert theo ngưỡng và theo thay đổi bất thường

Không có một ngưỡng rejection rate chung phù hợp mọi document type. Một file import do người dùng tải lên có thể có rejection tự nhiên cao hơn payment event từ producer đã kiểm soát.

Alert nên dựa trên:

- SLO hoặc baseline riêng cho từng type.
- Số lượng mẫu tối thiểu.
- Thời gian duy trì ngưỡng.
- Mức độ ảnh hưởng và owner của contract.
- Outcome là rejected hay failed.
- Có đang rollout version mới hay không.

### 14.1. Alert internal failure

Ví dụ rule minh họa:

~~~yaml
groups:
  - name: document-processing
    rules:
      - alert: DocumentInternalFailureRateHigh
        expr: |
          (
            sum by (document_type, contract_version) (
              rate(document_processing_outcomes_total{outcome="failed"}[10m])
            )
            /
            sum by (document_type, contract_version) (
              rate(document_processing_outcomes_total[10m])
            )
          ) > 0.02
        for: 10m
        labels:
          severity: page
        annotations:
          summary: "Document processing internal failures increased"
          description: "Internal failure rate is above the configured threshold."
~~~

Ngưỡng 2% chỉ là ví dụ. Trong production, thêm điều kiện minimum traffic và cấu hình theo service/type; không copy nguyên ngưỡng này cho mọi workload.

### 14.2. Alert rejection rate

Rejection rate cao có thể là tín hiệu producer contract bị lệch. Có thể gửi cảnh báo tới team sở hữu producer hoặc integration thay vì page on-call ngay lập tức.

Một số rejection có thể là hành vi bình thường, ví dụ người dùng nhập form sai. Với loại tài liệu đó, nên theo dõi trend và top validation rule thay vì đặt threshold thấp.

### 14.3. Alert theo version mới

Trong rollout, theo dõi version mới riêng. Alert có thể kích hoạt khi:

- Rejection rate của v2 cao hơn baseline v1/v2 trước rollout.
- Unsupported version xuất hiện đột ngột.
- Consumer cũ nhận version chưa hỗ trợ.
- Definition error tăng ngay sau deploy.
- Latency hoặc timeout tăng theo version mới.

Không so sánh trực tiếp hai version nếu traffic, producer population hoặc loại dữ liệu khác nhau mà không điều chỉnh bối cảnh.

### 14.4. Alert cần chống nhiễu

Với traffic thấp, một lỗi duy nhất có thể tạo tỷ lệ 100%. Hãy kết hợp tỷ lệ và số lượng tuyệt đối, ví dụ “tỷ lệ trên 5% và ít nhất 50 documents trong 10 phút”, hoặc dùng burn-rate SLO cho dịch vụ có volume ổn định.

Dùng `for` để yêu cầu tín hiệu kéo dài trước khi alert. Thiết lập no-data alert riêng nếu việc mất metric cũng là rủi ro.

## 15. SLO: phân biệt chất lượng dữ liệu và độ tin cậy dịch vụ

Một lỗi input không hợp lệ và một lỗi nội bộ không có cùng ý nghĩa.

Có thể định nghĩa hai SLI:

**Contract acceptance SLI**

[
rac{	ext{valid documents accepted}}{	ext{documents submitted}}
]

Chỉ số này phản ánh chất lượng dữ liệu và mức tương thích giữa producer/consumer. Nó có thể thuộc trách nhiệm chung của integration owners.

**Processing availability SLI**

[
rac{	ext{documents processed without internal failure}}{	ext{eligible processing attempts}}
]

Chỉ số này phản ánh khả năng dịch vụ xử lý tài liệu hợp lệ mà không gặp lỗi nội bộ.

Nếu gộp mọi rejection vào error budget availability, producer gửi sai dữ liệu có thể làm cạn error budget của consumer dù consumer đang hoạt động đúng. Ngược lại, nếu bỏ qua toàn bộ rejection, contract regression có thể không được ai theo dõi. Giữ hai SLI riêng giúp phân công trách nhiệm rõ hơn.

### 15.1. Định nghĩa eligible documents

Nếu một số loại tài liệu được phép reject theo nghiệp vụ, hãy xác định rõ chúng có thuộc denominator của SLO hay không. Ví dụ:

- JSON sai cú pháp từ client: có thể không thuộc availability SLO.
- JSON hợp lệ nhưng bị business rule từ chối: có thể được tính vào acceptance SLI, không phải availability failure.
- DTO không thể deserialize do server definition bug: thuộc internal failure.
- Database timeout sau deserialize: thuộc internal failure.
- Version không hỗ trợ do rollout producer chưa phối hợp: contract rejection, cần theo dõi riêng.

Điều quan trọng là định nghĩa này phải được thống nhất trước khi dashboard dùng để đánh giá reliability.

## 16. Theo dõi contract version trong quá trình rollout

Một thay đổi contract nên được triển khai theo giai đoạn thay vì chuyển toàn bộ producer và consumer cùng lúc.

Một rollout thường có:

1. Consumer mở rộng khả năng đọc version mới.
2. Consumer vẫn đọc version cũ.
3. Test fixture và contract tests xác nhận cả hai.
4. Producer bắt đầu phát version mới cho một tỷ lệ nhỏ.
5. Dashboard theo dõi rejection/failed theo version.
6. Mở rộng rollout nếu số liệu ổn định.
7. Ngừng phát version cũ sau thời gian tương thích.
8. Gỡ reader cũ trong release riêng khi không còn producer gửi.

~~~text
Consumer supports v1 + v2
          |
          v
Producer emits v1
          |
          v
Canary emits v2 for small cohort
          |
          v
Observe v2 acceptance / rejection / latency
          |
       +--+--+
       |     |
    Healthy  Regression
       |     |
       v     v
  Expand v2  Pause / rollback producer
       |
       v
  Retire v1 after migration window
~~~

### 16.1. Theo dõi old và new version riêng

Không chỉ nhìn tổng rejection rate. Khi v2 bắt đầu phát, tỷ lệ tổng có thể vẫn thấp vì v1 chiếm phần lớn traffic.

Dashboard cần có:

- Volume theo version.
- Accepted/rejected/failed theo version.
- Error category theo version.
- Producer/source cohort đã chuẩn hóa nếu có ích.
- Application version của consumer.
- Thời điểm rollout bắt đầu.

### 16.2. Consumer-first rollout

Nếu producer phát v2 trước khi consumer hỗ trợ, lỗi `unsupported_version` hoặc `unknown_property` có thể tăng. Thông thường, consumer nên được triển khai hỗ trợ đọc cả v1 và v2 trước khi producer chuyển sang v2.

Nếu contract có breaking change, có thể dùng adapter/migration layer để map v1 và v2 về cùng internal model. Metric vẫn giữ version đầu vào để biết adapter nào đang được sử dụng và lỗi tập trung ở đâu.

### 16.3. Rollback dựa trên tín hiệu

Định nghĩa trước tiêu chí dừng rollout:

- Rejection rate v2 vượt ngưỡng trong thời gian đủ dài.
- Internal failure v2 tăng sau deploy consumer.
- P95 latency v2 vượt budget.
- DLQ tăng nhanh.
- Unsupported version xuất hiện ngoài cohort dự kiến.

Rollback producer có thể khôi phục v1; rollback consumer có thể cần thiết nếu release mới gây lỗi cho cả v1. Chọn hành động theo stage và category, không chỉ theo tổng lỗi.

## 17. Phân biệt lỗi do contract với lỗi do Jackson upgrade

Khi nâng Jackson, cùng một payload có thể được xử lý khác do thay đổi parser, coercion, polymorphic handling hoặc default feature.

Để xác định nguyên nhân:

- Giữ fixture đại diện cho từng contract version.
- Chạy compatibility suite trên Jackson version cũ và mới.
- So sánh exception category, outcome và latency.
- Ghi application version và Jackson dependency version trong deployment metadata.
- Xem lỗi có chỉ xảy ra ở một document type/version hay mọi type.
- Kiểm tra cấu hình mapper, module và custom serializer/deserializer.
- So sánh parser constraints và coercion policy giữa hai release.

Không gắn Jackson version vào từng metric label nếu số phiên bản triển khai tăng liên tục. Có thể dùng label application release có cardinality được kiểm soát trong thời gian rollout, hoặc giữ library version trong build/deployment metadata và log.

### 17.1. Phân biệt regression behavior với dữ liệu producer thay đổi

Nếu lỗi chỉ tăng ở v2 nhưng đồng thời producer vừa thay đổi nội dung field, chưa thể kết luận Jackson upgrade gây lỗi. Cần so sánh fixture trước/sau, producer release và consumer release. Trace/correlation ID giúp truy ra một số tài liệu đại diện mà không lưu toàn bộ payload trong metrics.

## 18. Dead-letter queue và quarantine

Nếu pipeline không thể xử lý một tài liệu sau số lần retry cho phép, có thể chuyển nó vào dead-letter queue (DLQ) hoặc quarantine storage.

Nên ghi nhận:

- Số tài liệu vào DLQ theo type/version/category.
- Số lần retry trước khi chuyển.
- Thời gian từ receive tới DLQ.
- Lý do cuối cùng.
- Consumer/application version.
- Correlation ID hoặc document ID trong log metadata.

Không dùng document ID làm metric label. DLQ là nơi giữ payload lỗi để điều tra/replay; cần mã hóa, quyền truy cập, retention và audit trail phù hợp.

### 18.1. Không retry lỗi không thể tự phục hồi

Một số lỗi như malformed JSON, unknown type id hoặc missing required field thường không tự sửa khi retry cùng payload. Retry liên tục chỉ làm tăng load và duplicate logs.

Có thể phân loại:

- Non-retryable input rejection: chuyển quarantine/DLQ hoặc trả lỗi producer.
- Transient dependency failure: retry có backoff/jitter.
- Internal configuration error: dừng hoặc giảm consumer, alert on-call.
- Unknown error: giới hạn retry và bảo đảm có đường điều tra.

### 18.2. Replay cần giữ contract metadata

Khi replay DLQ, giữ lại document type, contract version, producer metadata và original receive time. Nếu replay bằng mapper mới, ghi thêm application version và replay flag. Điều này giúp phân biệt lỗi ban đầu với lỗi phát sinh khi replay.

## 19. Error path và top failing fields

Metrics có thể theo dõi category tổng quát, còn logs hoặc analytics có thể tổng hợp field path.

Ví dụ:

- `items[].quantity`
- `customer.address.postalCode`
- `payment.type`

Không dùng raw `getPathReference()` trực tiếp làm metric label vì map key/index có thể tạo cardinality rất cao. Nếu muốn dashboard top failing field, cần chuẩn hóa path:

- Giữ property name đã biết trong schema.
- Thay index bằng `[]`.
- Thay map key động bằng `{key}`.
- Giới hạn độ sâu.
- Bỏ hoặc mask segment không nằm trong allowlist.
- Chỉ tạo metric cho tập field quan trọng đã định nghĩa.

Ví dụ path raw:

~~~text
orders[92381].metadata["customer-uuid-9381"].taxCode
~~~

Path chuẩn hóa:

~~~text
orders[].metadata{key}.taxCode
~~~

Metric field có thể hữu ích cho contract owner, nhưng nên giới hạn vào một tập path cố định. Path đầy đủ của từng tài liệu ở log/trace phù hợp hơn.

## 20. Bảo mật và quyền riêng tư trong telemetry

Document processing có thể xử lý thông tin cá nhân, tài chính hoặc dữ liệu bí mật. Telemetry cần hữu ích nhưng không được biến hệ thống quan sát thành nơi lưu bản sao payload.

Nguyên tắc:

- Không ghi raw payload mặc định.
- Không ghi token, password, secret hoặc payment data.
- Sanitize path và map key.
- Không dùng document ID, user ID hoặc tenant ID làm metric label có cardinality lớn.
- Hạn chế ai được truy cập log/trace có correlation ID và error detail.
- Thiết lập retention theo nhu cầu điều tra.
- Mã hóa quarantine/DLQ và audit việc đọc/replay.
- Mask dữ liệu trước khi lưu fixture test.
- Không trả exception message nội bộ cho API caller.

Nếu cần lưu một payload để debug, dùng quy trình quarantine riêng có consent/policy, access control, encryption và expiration; không tự động gửi toàn bộ payload sang observability backend.

## 21. Kiểm thử instrumentation

Không chỉ test parser. Cần xác nhận metric/log được ghi đúng khi outcome xảy ra.

Với Micrometer, có thể dùng `SimpleMeterRegistry`:

~~~java
@Test
void shouldCountRejectedInvoiceV2() throws Exception {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    DocumentMetrics metrics = new DocumentMetrics(registry);

    DocumentDescriptor descriptor =
            new DocumentDescriptor("invoice", "v2");

    metrics.recordOutcome(
            descriptor,
            "parse_bind",
            "rejected",
            "invalid_format"
    );

    Counter counter = registry.find("document_processing_outcomes")
            .tags(
                    "document_type", "invoice",
                    "contract_version", "v2",
                    "stage", "parse_bind",
                    "outcome", "rejected",
                    "error_category", "invalid_format"
            )
            .counter();

    assertNotNull(counter);
    assertEquals(1.0, counter.count());
}
~~~

Test này kiểm tra metric tagging. Cần thêm integration test chạy wrapper deserialize thực tế với payload lỗi để xác nhận classifier và counter cùng hoạt động.

### 21.1. Test classifier theo từng exception

Tạo fixture lỗi cho:

- JSON syntax error.
- Unknown type id.
- Unknown property.
- Invalid number/date format.
- Mismatched object/array shape.
- Invalid definition do cấu hình test.
- Bean Validation violation.

Assert category theo policy. Khi nâng Jackson, test này giúp phát hiện exception hierarchy hoặc behavior thay đổi.

### 21.2. Test outcome không bị double-count

Một document bị reject ở parse stage không nên tiếp tục được tính accepted ở final stage. Nếu pipeline có nhiều stage, chỉ ghi stage outcomes riêng và ghi final outcome đúng một lần.

Test retry cũng cần xác nhận attempt counter và logical final outcome được cập nhật đúng semantics.

### 21.3. Test cardinality normalization

Đưa vào các version/type string không biết như `v999999-build-abc` hoặc `tenant-unique-123`, rồi xác nhận metric chỉ có bucket `unknown`/ `unsupported`, không tạo label value tùy ý.

## 22. Kiểm thử contract version và compatibility

Mỗi contract version được hỗ trợ nên có fixture độc lập:

~~~text
src/test/resources/contracts/
  invoice/
    v1/
      valid-minimal.json
      valid-full.json
      invalid-amount.json
    v2/
      valid-minimal.json
      valid-full.json
      unknown-field.json
      invalid-amount.json
  payment-event/
    v1/
      valid-event.json
    v2/
      valid-event.json
~~~

Test matrix có thể gồm:

| Producer version | Consumer hỗ trợ | Kết quả mong đợi |
|---|---|---|
| invoice v1 | reader v1 + v2 | accepted |
| invoice v2 | reader v1 + v2 | accepted |
| invoice v3 | reader chưa hỗ trợ v3 | unsupported_version |
| payment_event v2 | reader v2 | accepted |
| malformed body | bất kỳ reader | syntax_error hoặc parse rejection |

Nếu consumer cố ý tolerant với unknown fields, fixture unknown-field phải xác nhận field được bỏ qua hoặc preserve theo contract. Nếu strict, phải xác nhận rejection và error category phù hợp.

### 22.1. Contract version không nên được đoán từ class name

Đừng suy ra v2 chỉ vì DTO class tên `InvoiceV2`. Wire version phải được xác định từ contract metadata, route hoặc schema registry. Class name là chi tiết implementation và có thể đổi.

### 22.2. Reader support và writer version là hai policy khác nhau

Một service có thể đọc v1 và v2 nhưng chỉ ghi v2. Theo dõi riêng:

- `input_contract_version`: version tài liệu nhận vào.
- `output_contract_version`: version tài liệu phát ra.

Nếu dùng chung label `contract_version` cho cả hai chiều, dashboard có thể gộp hai hành vi khác nhau. Metric name/stage nên cho biết direction hoặc dùng dimension `direction=read|write` có tập giá trị nhỏ.

## 23. Theo dõi tỷ lệ lỗi khi ghi tài liệu

Lỗi không chỉ xảy ra ở deserialize. Serializer có thể thất bại do:

- Getter ném exception.
- Custom serializer lỗi.
- Object graph có cycle không được xử lý.
- Type metadata không hợp lệ.
- Không thể truy cập member hoặc cấu hình module.
- Output stream bị đóng hoặc hết dung lượng.
- Schema CSV không phù hợp object.
- XML/YAML generator gặp lỗi encoding/format.

Theo dõi riêng stage `serialize` hoặc `write` và chiều `direction=outbound`. Đừng gộp serializer failure với input rejection.

Nếu producer tạo file theo contract version, metric output cũng cần ghi document type/version đã phát. Khi consumer đối tác báo lỗi, có thể đối chiếu version và application release.

## 24. Dashboard và alert cho version migration

Trong giai đoạn migration, nên có một dashboard chuyên biệt với:

- Tỷ lệ traffic từng version.
- Acceptance/rejection rate từng version.
- Error category theo version.
- Latency theo version.
- Tỷ lệ unknown/unsupported version.
- Producer release hoặc cohort nếu hữu ích.
- DLQ/retry theo version.
- Thời điểm bắt đầu rollout và deployment marker.

Một checklist rollout:

1. Consumer đã deploy reader hỗ trợ cả version cũ và mới.
2. Contract fixtures của cả hai version pass.
3. Producer canary gửi version mới.
4. Dashboard xác nhận traffic version mới xuất hiện đúng cohort.
5. Rejection và internal failure không vượt baseline/budget.
6. Latency và payload size nằm trong giới hạn.
7. DLQ không tăng bất thường.
8. Mở rộng cohort theo từng bước.
9. Duy trì thời gian tương thích cho consumer trễ.
10. Gỡ version cũ sau khi traffic và producer inventory xác nhận không còn sử dụng.

Không xóa metric version cũ ngay khi migration kết thúc; giữ lịch sử đủ lâu để điều tra replay hoặc batch cũ.

## 25. Runbook điều tra khi tỷ lệ lỗi tăng

Khi alert phát ra, người trực ca có thể đi theo trình tự:

1. Xem document type và contract version nào tăng.
2. Kiểm tra số lượng mẫu và traffic có thay đổi không.
3. Xem outcome là rejected hay failed.
4. Xem stage nào phát sinh lỗi.
5. Xem error category nào tăng mạnh nhất.
6. Đối chiếu thời điểm với deployment producer/consumer và Jackson upgrade.
7. Mở log theo correlation ID để xem path/location đã sanitize.
8. Kiểm tra fixture hoặc sample đã được quarantine có quyền truy cập.
9. Xác định lỗi có retry được không.
10. Nếu là contract regression, pause/rollback producer hoặc consumer theo rollout plan.
11. Nếu là server definition error, giảm traffic/consumer concurrency nếu cần và khắc phục release.
12. Sau khi sửa, replay có kiểm soát và theo dõi tỷ lệ phục hồi.

Runbook nên chỉ rõ owner của từng document type và producer. Một alert không có owner sẽ kéo dài thời gian điều tra.

## 26. Các lỗi thường gặp khi thiết kế monitoring

**Chỉ đếm tổng exception.** Không biết type/version nào bị ảnh hưởng. Thêm dimension contract đã chuẩn hóa.

**Dùng raw version hoặc document ID làm metric label.** Cardinality tăng không kiểm soát. Chuẩn hóa version, giữ ID trong logs/traces.

**Gộp rejected và failed.** Lỗi producer có thể bị hiểu nhầm là sự cố consumer. Tách outcome và SLI.

**Không định nghĩa denominator.** Retry có thể làm tỷ lệ sai. Ghi rõ attempt-level hay logical document-level.

**Đếm cùng một tài liệu ở nhiều stage như nhiều final outcome.** Double-count. Tách stage metrics và final outcome.

**Phân loại exception bằng message text.** Dễ vỡ khi nâng Jackson. Dùng exception type và taxonomy nội bộ.

**Coi InvalidDefinitionException là lỗi client.** Có thể che bug server. Phân loại definition/configuration thành internal failure.

**Alert theo tỷ lệ mà không xem volume.** Một mẫu nhỏ tạo cảnh báo nhiễu. Kết hợp tỷ lệ, số mẫu và thời gian duy trì.

**Không theo dõi version mới riêng khi rollout.** Lỗi bị che bởi traffic version cũ. Dùng dashboard/version-specific alert.

**Log toàn bộ payload để điều tra.** Có nguy cơ lộ dữ liệu nhạy cảm. Dùng metadata, path đã sanitize và quarantine có kiểm soát.

**Không test instrumentation.** Metric có thể thiếu label hoặc outcome sai dù parser test pass. Dùng SimpleMeterRegistry và integration test.

**Để metric không có owner.** Không ai hành động khi contract lỗi. Gắn ownership và runbook cho từng document type.

## 27. Quy trình triển khai end-to-end

Khi thêm monitoring cho một loại tài liệu Jackson:

1. Định nghĩa document type và contract version bằng registry hữu hạn.
2. Chọn nguồn metadata đáng tin cậy; nếu không xác định được, dùng bucket unknown.
3. Định nghĩa attempt, logical document, outcome và denominator.
4. Xây error taxonomy ổn định, phân biệt input rejection với internal failure.
5. Instrument parse/bind, validation, business và persistence theo stage.
6. Ghi Counter cho outcome và Timer cho latency; thêm payload size nếu cần.
7. Giới hạn metric labels để tránh cardinality cao.
8. Ghi structured logs/traces với correlation ID, error category và path đã sanitize.
9. Tạo dashboard theo type/version/outcome/category/stage.
10. Định nghĩa alert có minimum traffic, threshold và duration.
11. Xây SLI/SLO riêng cho contract acceptance và processing availability.
12. Giữ fixtures cho từng contract version và test classifier/instrumentation.
13. Theo dõi version mới trong canary, so sánh với baseline.
14. Dùng runbook để pause, rollback, quarantine hoặc replay.
15. Rà soát retention, quyền truy cập và privacy của logs/traces/DLQ.

## 28. Kết luận

Theo dõi tỷ lệ lỗi theo document type và contract version giúp đội vận hành phát hiện chính xác nhóm dữ liệu bị ảnh hưởng khi producer, consumer, DTO hoặc Jackson thay đổi. Nền tảng của việc theo dõi là một taxonomy ổn định: document type và version hữu hạn, stage rõ ràng, error category có ý nghĩa, và outcome phân biệt accepted, rejected với failed. Định nghĩa denominator ở cấp attempt hay logical document trước khi tính tỷ lệ để retry không làm sai số liệu.

Dùng Counter và Timer để theo dõi volume, outcome và latency; dùng logs/traces để điều tra một tài liệu cụ thể. Giữ metric cardinality thấp bằng cách chuẩn hóa type/version và không đưa ID, raw path hoặc exception message vào labels. Dashboard cần so sánh version, category và stage; alert cần xét cả tỷ lệ lẫn số mẫu. Trong rollout, triển khai consumer hỗ trợ version mới trước, canary producer và chỉ mở rộng khi rejection, failure, latency và DLQ ổn định.

Cuối cùng, tách contract acceptance khỏi service availability. Một payload sai có thể là rejection dự kiến; một DTO definition bug hoặc dependency outage là internal failure. Khi hai loại này được đo riêng, số liệu trở thành cơ sở đáng tin cậy để phối hợp producer/consumer, quyết định rollback và bảo vệ chất lượng dữ liệu trong quá trình nâng cấp.

## Tài liệu tham khảo

- [Jackson Databind — JsonMappingException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonMappingException.html)
- [Jackson Databind — InvalidFormatException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/InvalidFormatException.html)
- [Jackson Databind — UnrecognizedPropertyException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/UnrecognizedPropertyException.html)
- [Jackson Databind — InvalidTypeIdException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/InvalidTypeIdException.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Naming conventions](https://docs.micrometer.io/micrometer/reference/concepts/naming.html)
- [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)

