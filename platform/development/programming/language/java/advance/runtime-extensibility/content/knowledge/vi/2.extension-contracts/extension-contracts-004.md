# Quy định đầu vào, đầu ra, giá trị null và ngoại lệ qua ranh giới mở rộng trong Java

## 1. Hợp đồng mở rộng là gì?

Trong ứng dụng có khả năng mở rộng lúc chạy (runtime extensibility), **host** gọi mã của **extension/plugin/provider** thông qua một API hoặc SPI dùng chung. Ví dụ: host tìm implementation bằng ServiceLoader, chọn một processor trong registry, hoặc gọi adapter được nạp bằng class loader riêng. Host và plugin có thể do hai nhóm phát triển, nâng cấp độc lập; compiler chỉ kiểm tra một phần của thỏa thuận.

Xét chữ ký:

~~~java
Result process(Request request) throws ExtensionFailure;
~~~

Chữ ký chưa trả lời: Request có được null không? Trường nào bắt buộc? Plugin có quyền sửa danh sách đầu vào không? Result có bao giờ null không? Khi không tìm thấy dữ liệu, plugin trả gì? Exception nào báo lỗi nghiệp vụ, exception nào báo lỗi hợp đồng? Nếu mỗi bên hiểu khác nhau, lỗi của một plugin có thể gây NullPointerException ở tầng khác hoặc bị che thành một kết quả "thành công".

**Hợp đồng mở rộng** xác định tiền điều kiện, hậu điều kiện, nullability, loại thất bại, quyền sở hữu dữ liệu, vòng đời và yêu cầu tương thích. Đây là một phần của API ổn định, không phải chi tiết ngẫu nhiên của implementation.

## 2. Vai trò và trách nhiệm ở ranh giới

| Vai trò | Cam kết |
| --- | --- |
| Caller/host | Chuẩn bị input đúng tiền điều kiện; kiểm tra lỗi sử dụng API trước khi gọi plugin |
| Extension | Không phá vỡ các bất biến đã hứa; trả output đúng hậu điều kiện hoặc ném lỗi được công bố |
| Boundary adapter | Kiểm tra kết quả plugin, phân loại lỗi, giữ cause và áp dụng chính sách lỗi của host |
| Bên tiêu thụ | Dựa trên API công khai và mã lỗi ổn định, không phụ thuộc class nội bộ hay nội dung message của plugin |

Một hợp đồng đủ dùng cần nêu rõ: kiểu và miền giá trị đầu vào; trường bắt buộc/tùy chọn; trạng thái "không có dữ liệu"; bất biến kết quả; exception được phép xuất hiện; timeout, hủy, tài nguyên, concurrency nếu có; chính sách xử lý khi plugin không tuân thủ.

**Tiền điều kiện** là điều caller phải bảo đảm trước lời gọi; **hậu điều kiện** là điều provider phải bảo đảm khi trả về bình thường. **Thất bại dự kiến** phải tách khỏi **vi phạm hợp đồng hoặc bug**.

## 3. Đầu vào: xác thực sớm và ranh giới sở hữu

### 3.1. Kiểm tra hơn cả kiểu Java

Reference type trong Java có thể chứa null. String đúng kiểu vẫn có thể rỗng hoặc chỉ có dấu cách; List đúng kiểu vẫn có thể chứa null, phần tử không hợp lệ hay object mutable. Chọn trước quy tắc cho từng trường: ví dụ operation phải non-null và non-blank; items phải non-null, không chứa null; kích thước phải trong giới hạn hợp đồng.

Áp dụng validation ở **host trước khi đi qua ranh giới** để lỗi do caller tạo không bị nhầm thành lỗi plugin. Những bất biến phụ thuộc logic của provider vẫn có thể được kiểm tra bên trong provider, nhưng không thể thay thế validation tại biên. Khi cần normalize dữ liệu (trim, chuyển case, chuẩn hóa đường dẫn), phải công bố quy tắc để không âm thầm đổi nghĩa yêu cầu.

Objects.requireNonNull(value, "name") là biện pháp fail fast; kiểm tra rỗng, miền số hay tính nhất quán giữa trường cần điều kiện riêng. Một request không hợp lệ không nên được gửi xuống plugin rồi mới ném ngoại lệ mơ hồ từ một tầng sâu.

### 3.2. Không vô tình đưa quyền sửa dữ liệu cho plugin

Nếu host truyền trực tiếp ArrayList, plugin có thể sửa danh sách mà host còn giữ. Với List<String>, List.copyOf tạo một bản sao không thể sửa qua API List và từ chối phần tử null. Record và DTO bất biến giúp giữ tiền điều kiện sau khi đã validate.

Tuy nhiên, List.copyOf chỉ bảo vệ **container**, không sao chép sâu phần tử mutable. Với List<MutableItem>, phần tử vẫn có thể đổi. Chọn immutable DTO, defensive copy sâu hoặc một view có quyền hạn hạn chế theo đúng hợp đồng.

Cũng phải quy định plugin có được giữ Request/callback sau khi phương thức trả về không; ai sở hữu transaction, connection, buffer và dữ liệu request-scoped. Không đưa state nội bộ hay tài nguyên của host vào API mở rộng nếu không có lý do thiết kế cụ thể.

## 4. Đầu ra: trạng thái thành công, vắng mặt và thất bại

Ba trường hợp cần được phân biệt:

| Tình huống | Biểu diễn thích hợp | Ý nghĩa |
| --- | --- | --- |
| Thành công có dữ liệu | Result non-null, thỏa mãn bất biến | Caller có thể sử dụng an toàn |
| Thành công nhưng không có dữ liệu | Optional.empty(), collection rỗng hoặc mã NOT_FOUND được công bố | Kết quả hợp lệ, không phải plugin crash |
| Không hoàn thành tác vụ | Exception đã khai báo hoặc một kiểu kết quả lỗi rõ ràng | Caller áp dụng chính sách lỗi/retry |

Mỗi API chỉ nên có **một cách biểu diễn** cho một ý nghĩa. Không để "không tìm thấy" lúc là null, lúc là exception, lúc là danh sách rỗng. Không trả list rỗng để che lỗi đọc nguồn dữ liệu.

Một Result cần nêu bất biến của từng trường: description non-null và có nội dung, count không âm, mã trạng thái phù hợp payload, v.v. Việc trả về bình thường chính là cam kết các bất biến đã đúng. Host nên kiểm tra hậu điều kiện quan trọng ngay sau khi nhận output từ plugin, trước khi chuyển dữ liệu đó cho phần còn lại của hệ thống.

Nếu output là Stream, InputStream, AutoCloseable hoặc callback, quy định rõ **ai đóng, khi nào đóng và dữ liệu còn hợp lệ bao lâu**. Nếu Result chứa object mutable của plugin, việc giữ tham chiếu có thể gây lỗi khi plugin bị dỡ hoặc state của nó thay đổi; ưu tiên DTO độc lập ở API chung.

## 5. Quy định null cho từng vị trí

Java 17 không tự xem String, Request hay List là non-null. Cần viết và kiểm tra nullability tại từng ranh giới.

| Vị trí | Hợp đồng khuyến nghị | Nếu bị vi phạm |
| --- | --- | --- |
| Extension instance | Không null | Host từ chối trước lời gọi |
| Request gốc | Không null | Host từ chối trước lời gọi |
| Trường bắt buộc | Non-null và đúng miền giá trị | Constructor/validator báo sai đầu vào |
| Trường tùy chọn | Mô tả rõ null hoặc dùng một representation khác | Caller/provider không tự suy diễn |
| Giá trị process trả về | Non-null khi hoàn thành bình thường | Adapter đánh dấu vi phạm hợp đồng |
| Giá trị tra cứu có thể vắng mặt | Optional<Result> non-null hoặc trạng thái rõ ràng | Optional.empty() nghĩa là vắng mặt |
| Phần tử List/Map | Non-null trừ khi API công bố khác | Validate khi tạo và khi nhận |

Null khác chuỗi rỗng, số 0, false, collection rỗng và trạng thái NOT_FOUND. Những giá trị đó không được tự động thay thế nhau.

Optional phù hợp cho **giá trị trả về có thể vắng mặt**, không phải mặc định cho mọi tham số hay mọi field của DTO. Phương thức trả Optional vẫn **không được trả null thay vì Optional.empty()**.

Annotation @Nullable/@NonNull có thể giúp IDE và công cụ phân tích khi dự án thống nhất annotation và checker. Compiler Java thông thường không kiểm tra đầy đủ hợp đồng nullability chỉ vì có annotation; validation runtime tại boundary vẫn có ý nghĩa.

## 6. Ngoại lệ: phân loại lỗi trước khi quyết định cách xử lý

| Trường hợp | Cách biểu diễn ví dụ | Trách nhiệm/ứng xử |
| --- | --- | --- |
| Caller truyền tham số không hợp lệ | IllegalArgumentException hoặc NullPointerException trước lời gọi | Caller sửa input |
| Plugin thất bại theo nghiệp vụ đã công bố | ExtensionFailure (checked, hoặc error result có kiểu) | Host có thể retry/fallback nếu an toàn |
| Plugin trả null trái cam kết | ContractViolation | Host báo plugin vi phạm hậu điều kiện |
| Plugin ném RuntimeException ngoài hợp đồng | ContractViolation với cause gốc | Host phân loại lỗi plugin và chẩn đoán |
| Không tìm hoặc khởi tạo được provider | Lỗi discovery riêng; ServiceConfigurationError khi dùng ServiceLoader | Loader/registration xử lý |
| JVM gặp lỗi nghiêm trọng | Error (ví dụ OutOfMemoryError) | Không che thành lỗi nghiệp vụ |

**Checked exception** phù hợp khi caller có hành động cụ thể cho một loại thất bại dự kiến. **Unchecked exception** thường diễn đạt lỗi lập trình hoặc tiền điều kiện sai. Có thể chọn kiểu kết quả Success/Failure thay exception, nhưng phải nhất quán; không diễn giải ngẫu nhiên mọi RuntimeException là "không có dữ liệu".

Khi wrap exception, luôn giữ nguyên **cause**:

~~~java
throw new ContractViolation("extension failed unexpectedly", original);
~~~

Không so khớp chuỗi exception message để quyết định retry; nếu cần máy xử lý ổn định, công bố error code. Log tên plugin, operation, correlation ID và error code, nhưng tránh phát tán secret, request nhạy cảm hoặc stack trace đến caller.

Không bắt Throwable tràn lan chỉ để tiếp tục chạy: Error có thể là lỗi nghiêm trọng của VM. Đối với InterruptedException, nếu phương thức có thể khai báo thì chuyển tiếp; nếu bắt mà không ném lại, khôi phục cờ interrupt bằng Thread.currentThread().interrupt() và xử lý cancellation. Không nuốt interrupt để giả vờ xử lý thành công.

Khi đóng resource bị lỗi trong lúc một lỗi khác đang xảy ra, try-with-resources giữ lỗi đóng dưới dạng **suppressed exception**. Cần đọc exception gốc, cause và suppressed để chẩn đoán đúng.

Riêng ServiceLoader, việc load/dò provider có tính lazy; ServiceConfigurationError có thể xuất hiện khi duyệt hoặc tạo provider. Chính sách bỏ qua một provider hỏng hay fail toàn bộ startup phải nằm trong phần **discovery contract**; bắt lỗi tại vị trí đó khác với bắt toàn bộ Error khi thực thi plugin.

## 7. Ví dụ Java 17 hoàn chỉnh: hợp đồng kiểm tra hai chiều

Chương trình dưới đây minh họa một extension point đơn giản. Request và Result không được null; items không chứa null; count không âm. Lỗi xử lý dự kiến đi qua ExtensionFailure, còn kết quả null hoặc lỗi runtime không dự kiến được adapter biến thành ContractViolation.

Tạo tệp **ExtensionContractDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;

public final class ExtensionContractDemo {
    public record Request(String operation, List<String> items) {
        public Request {
            operation = Objects.requireNonNull(operation, "operation");
            if (operation.isBlank()) {
                throw new IllegalArgumentException("operation is blank");
            }
            items = List.copyOf(Objects.requireNonNull(items, "items"));
        }
    }

    public record Result(String description, int count) {
        public Result {
            description = Objects.requireNonNull(description, "description");
            if (description.isBlank()) {
                throw new IllegalArgumentException("description is blank");
            }
            if (count < 0) {
                throw new IllegalArgumentException("count is negative");
            }
        }
    }

    public interface Extension {
        Result run(Request request) throws ExtensionFailure;
    }

    public static final class ExtensionFailure extends Exception {
        public ExtensionFailure(String message) {
            super(message);
        }
    }

    public static final class ContractViolation extends RuntimeException {
        public ContractViolation(String message) {
            super(message);
        }

        public ContractViolation(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static Result call(Extension extension, Request request)
            throws ExtensionFailure {
        Objects.requireNonNull(extension, "extension");
        Objects.requireNonNull(request, "request");

        try {
            Result result = extension.run(request);
            if (result == null) {
                throw new ContractViolation("extension returned null");
            }
            return result;
        } catch (ExtensionFailure expected) {
            throw expected;
        } catch (ContractViolation violation) {
            throw violation;
        } catch (RuntimeException unexpected) {
            throw new ContractViolation(
                    "extension threw an unexpected exception", unexpected);
        }
    }

    public static void main(String[] args) throws ExtensionFailure {
        Request input = new Request("count", List.of("a", "b"));

        Extension good = request -> new Result(
                request.operation() + ":" + request.items().size(),
                request.items().size());
        System.out.println(call(good, input));

        Extension nullResult = request -> null;
        try {
            call(nullResult, input);
        } catch (ContractViolation ex) {
            System.out.println(ex.getMessage());
        }

        Extension unavailable = request -> {
            throw new ExtensionFailure("data source unavailable");
        };
        try {
            call(unavailable, input);
        } catch (ExtensionFailure ex) {
            System.out.println("failed: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ExtensionContractDemo.java
java ExtensionContractDemo
~~~

Standard output chính xác:

~~~text
Result[description=count:2, count=2]
extension returned null
failed: data source unavailable
~~~

Giải thích:

1. Record Request kiểm tra operation, sau đó copy items; List.copyOf từ chối danh sách có phần tử null. Sai input bị chặn trước khi plugin xử lý.
2. Record Result kiểm tra description và count khi khởi tạo. Provider bình thường trả một output thỏa mãn hậu điều kiện.
3. Provider trả null làm adapter ném ContractViolation đúng tại ranh giới; không chờ NullPointerException xảy ra xa hơn.
4. Provider ném ExtensionFailure thể hiện lỗi tác vụ dự kiến. Host nhận đúng loại đó.
5. Một RuntimeException bất ngờ sẽ được wrap với cause; Error không bị bắt. Đối với cancellation hay interruption, nếu API hỗ trợ thì bổ sung quy ước cụ thể thay vì mặc định coi chúng là lỗi runtime thông thường.

Đây là chương trình độc lập chạy được, còn cơ chế ServiceLoader, lifecycle và sandbox cần thiết kế riêng theo hệ thống. Không nên coi việc bắt exception như khả năng hoàn tác side effect đã xảy ra trong plugin.

## 8. Luồng kiểm soát tại boundary adapter

~~~text
Caller tạo Request
    |
    v
Host kiểm tra tiền điều kiện
    |-- sai -> lỗi caller, không gọi plugin
    v
Extension.run(request)
    |-- ExtensionFailure được công bố -> lỗi tác vụ dự kiến
    |-- RuntimeException không dự kiến -> plugin failure, giữ cause
    v
Return bình thường
    |
    v
Host kiểm tra non-null và hậu điều kiện
    |-- sai -> ContractViolation
    v
Trả Result đã xác thực cho caller
~~~

Validate đầu vào chưa đủ vì plugin có thể viết sai hợp đồng. Validate đầu ra không thể tự khôi phục side effect mà plugin đã gây ra trước khi thất bại. Nếu operation có side effect, cần thêm giao ước atomicity, idempotency, transaction hoặc compensation cho từng loại tác vụ.

Với API bất đồng bộ, cần mô tả riêng CompletionStage/Future có thể null không, giá trị khi hoàn tất có thể null không, cancellation được biểu diễn thế nào và cause nằm trong CompletionException/ExecutionException ra sao. Timeout của Future chỉ giới hạn thời gian đợi; không bảo đảm một plugin phớt lờ interrupt đã thực sự dừng.

## 9. API chung, class loader và tiến hóa hợp đồng

Trong JVM, định danh lớp phụ thuộc vào **tên lớp và class loader định nghĩa lớp đó**. Hai bản của cùng một interface có tên giống nhau nhưng do hai loader khác nhau định nghĩa không nhất thiết ép kiểu cho nhau được. Host và plugin cần có cách chia sẻ API contract thống nhất; đừng cho mỗi plugin nhúng riêng một bản interface không tương thích rồi trông chờ cast sẽ thành công.

Khi thay đổi phiên bản API:

- Không tự đổi ý nghĩa của null, Optional.empty(), danh sách rỗng hoặc exception. Đây có thể là breaking change về hành vi dù chữ ký Java không thay đổi.
- Đặt interface, DTO và exception công khai ở API chung. Tránh trả object thuộc thư viện riêng của plugin hoặc lộ lớp chỉ được load trong plugin.
- Công bố quy tắc trường bắt buộc/tùy chọn và fallback cho các version; kiểm tra tương thích nhị phân lẫn tương thích hành vi.
- Không biến chuỗi message của exception thành protocol. Nếu host tích hợp nhiều plugin, dùng error code hoặc contract type ổn định.
- Chính sách fallback/retry thuộc host; chỉ retry tác vụ có idempotency hoặc chống lặp phù hợp.

## 10. Các cam kết đi kèm dữ liệu và lỗi

**Concurrency:** API phải nêu một extension instance có bị gọi đồng thời không, có reentrant không và ai sở hữu mutable state. Interface không tự làm implementation thread-safe.

**Lifecycle/tài nguyên:** API phải nêu ai đóng Closeable, bao giờ callback được gọi, thread nào có thể gọi và Request/Result được giữ tham chiếu bao lâu. Dùng try-with-resources ở phía có trách nhiệm đóng.

**Cô lập lỗi:** Chuyển đổi exception giúp host thống nhất cách báo lỗi, nhưng không tạo sandbox. Plugin chạy cùng JVM vẫn có thể ảnh hưởng tài nguyên chung. Với mã không đáng tin, cân nhắc cách ly process/JVM và giao thức qua IPC thay vì chỉ dùng catch.

**Observability:** Log có cấu trúc gồm provider ID, operation, correlation ID, phân loại lỗi và cause; tránh log dữ liệu nhạy cảm. Tách thông điệp an toàn cho caller khỏi chẩn đoán kỹ thuật dành cho vận hành.

## 11. Ma trận kiểm thử hợp đồng

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Extension hoặc Request là null | Host từ chối trước lời gọi |
| Trường bắt buộc null, blank hoặc vượt miền giá trị | Fail fast với lỗi input có chủ ý |
| List chứa phần tử null | Bị từ chối nếu hợp đồng non-null |
| Plugin sửa collection nhận được | Không làm thay đổi snapshot của host nếu API hứa bất biến |
| Plugin trả kết quả hợp lệ | Host nhận Result và các bất biến còn đúng |
| Không tìm thấy dữ liệu | Dùng chính xác representation vắng mặt được định nghĩa |
| Plugin trả null trái hợp đồng | Adapter báo ContractViolation |
| Plugin ném ExtensionFailure | Host nhận đúng loại thất bại dự kiến |
| Plugin ném RuntimeException không dự kiến | Adapter giữ cause và phân loại plugin failure |
| Provider không load hoặc instantiate được | Discovery trả đúng lỗi/sự kiện riêng |
| Interruption, timeout, cancellation | Không nuốt interrupt và không giả định tác vụ đã dừng |
| Gọi đồng thời hoặc khác phiên bản API | Tuân thủ chính sách thread-safety và tương thích |

Dùng **contract tests** chung cho từng provider; bổ sung fake provider cố tình trả null, output sai, ném checked/unchecked exception. Với runtime loading, chạy integration test qua class loader và version API thật vì unit test trên cùng classpath có thể bỏ sót lỗi type identity.

## 12. Checklist thiết kế extension point

- Đã mô tả rõ nullability, miền giá trị và quyền sửa/giữ tham chiếu của từng input.
- Đã phân biệt thành công có dữ liệu, thành công vắng dữ liệu và thất bại; hậu điều kiện được kiểm tra.
- Đã phân loại caller error, lỗi tác vụ được công bố, vi phạm hợp đồng plugin và lỗi discovery.
- Khi wrap exception có giữ cause; chính sách logging, interruption, cancellation và retry được xác định.
- DTO/interface/exception công khai có nguồn class loader và quy tắc versioning nhất quán.
- Đã định nghĩa quyền sở hữu tài nguyên, lifecycle, concurrency và hợp đồng kiểm thử cho từng provider.

**Nguyên tắc:** mọi giá trị và lỗi đi qua ranh giới extension phải có nghĩa đã thống nhất. Host bảo đảm input hợp lệ, plugin bảo đảm output hợp lệ hoặc thất bại được định nghĩa, và boundary adapter xác minh cả hai chiều.
