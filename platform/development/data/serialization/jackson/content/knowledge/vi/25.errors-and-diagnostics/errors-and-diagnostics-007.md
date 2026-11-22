# Giữ nguyên nguyên nhân gốc khi chuyển lỗi sang lớp ứng dụng

Trong một ứng dụng Java, lỗi thường đi qua nhiều tầng: Jackson đọc JSON, adapter chuyển dữ liệu sang kiểu domain, application service thực hiện use case, repository truy cập database và controller chuyển kết quả thành HTTP response. Mỗi tầng có thể cần một loại exception phù hợp với trách nhiệm của mình. Controller không nhất thiết phải biết chi tiết JsonMappingException, còn application service có thể cần một lỗi ổn định như InvalidImportRequestException.

Khi chuyển một exception kỹ thuật thành exception của ứng dụng, điều quan trọng là **giữ nguyên nguyên nhân gốc (cause)**. Exception mới giúp tầng gọi hiểu ngữ cảnh và phân loại lỗi; exception cũ vẫn giữ thông tin kỹ thuật để điều tra. Nếu chỉ tạo exception mới từ message, stack trace ban đầu và kiểu lỗi cụ thể sẽ bị mất khỏi chuỗi nguyên nhân.

Bài học này trình bày cách bọc exception đúng cách, phân biệt lỗi kỹ thuật với lỗi nghiệp vụ, xử lý lỗi Jackson ở ranh giới phù hợp, ghi log mà không làm mất thông tin, và kiểm thử rằng cause chain được bảo toàn.

## 1. Vì sao cần chuyển lỗi sang lớp ứng dụng?

Một thư viện thường ném exception theo ngôn ngữ kỹ thuật của chính nó. Jackson có thể ném JsonParseException khi cú pháp JSON sai hoặc JsonMappingException khi dữ liệu không khớp kiểu Java. JDBC driver có thể ném SQLException; thư viện HTTP có thể ném lỗi kết nối hoặc timeout.

Nếu những exception này đi thẳng qua mọi tầng, code nghiệp vụ sẽ phụ thuộc vào chi tiết của thư viện. Ví dụ:

~~~java
public void importOrders(String json) throws JsonProcessingException {
    List<OrderRequest> requests = mapper.readValue(
        json,
        new TypeReference<List<OrderRequest>>() {}
    );

    // Xử lý nghiệp vụ.
}
~~~

Một service công khai như trên buộc caller biết Jackson và JsonProcessingException, dù nhiệm vụ của service là import đơn hàng. Nếu sau này thay Jackson hoặc thay cách nhận dữ liệu, chữ ký và các caller có thể phải thay đổi theo.

Có thể chuyển lỗi tại adapter thành exception của ứng dụng:

~~~java
public List<OrderRequest> parseOrders(String json) {
    try {
        return mapper.readValue(
            json,
            new TypeReference<List<OrderRequest>>() {}
        );
    } catch (JsonProcessingException exception) {
        throw new InvalidImportRequestException(
            "Import request contains invalid JSON",
            exception
        );
    }
}
~~~

Caller chỉ cần hiểu InvalidImportRequestException. Khi cần chẩn đoán, kỹ thuật viên vẫn có thể xem cause là JsonProcessingException hoặc một lớp con cụ thể của Jackson.

## 2. Cause là gì?

Trong Java, một exception có thể giữ một exception khác làm nguyên nhân. Exception được truyền vào constructor có tham số cause hoặc được gắn qua initCause() sẽ nằm trong chuỗi nguyên nhân.

~~~java
try {
    readConfiguration();
} catch (IOException exception) {
    throw new ConfigurationLoadException(
        "Cannot load application configuration",
        exception
    );
}
~~~

Ở đây:

- ConfigurationLoadException là exception ở mức ứng dụng.
- IOException là nguyên nhân kỹ thuật trực tiếp.
- Stack trace của exception gốc vẫn có thể được truy cập qua getCause().
- printStackTrace() của exception bọc thường hiển thị cả chuỗi nguyên nhân.

Một cause chain có thể dài nhiều tầng:

~~~text
ImportFailedException
  caused by InvalidImportRequestException
    caused by JsonMappingException
      caused by NumberFormatException
~~~

Mỗi tầng bổ sung ngữ cảnh phù hợp với trách nhiệm của mình, nhưng không được xóa mất lỗi trước đó.

### 2.1. Khác nhau giữa message và cause

Message trả lời câu hỏi “điều gì xảy ra ở tầng này?”. Cause trả lời “lỗi nào thực sự dẫn tới tình trạng đó?”.

~~~java
throw new ImportFailedException(
    "Could not import partner batch",
    originalException
);
~~~

Message có thể bổ sung batch ID, tên nguồn hoặc use case. Cause giữ exception thực tế như lỗi parse, lỗi kết nối hoặc lỗi lưu dữ liệu.

Không nên thay cause bằng cách chỉ sao chép message:

~~~java
// Sai: chỉ giữ chuỗi mô tả, làm mất cause.
throw new ImportFailedException(originalException.getMessage());
~~~

Cũng không nên chỉ nối message của exception gốc vào message mới rồi bỏ cause. Việc đó không bảo toàn kiểu exception, stack trace và các thông tin có cấu trúc của lỗi ban đầu.

## 3. Tạo exception ứng dụng có constructor nhận cause

Một exception tùy chỉnh nên cung cấp các constructor phù hợp để người gọi có thể tạo lỗi có hoặc không có nguyên nhân.

~~~java
public class InvalidImportRequestException extends RuntimeException {
    public InvalidImportRequestException(String message) {
        super(message);
    }

    public InvalidImportRequestException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Với lỗi có thể phục hồi hoặc cần được khai báo trong chữ ký phương thức, có thể kế thừa Exception:

~~~java
public class ImportFailedException extends Exception {
    public ImportFailedException(String message) {
        super(message);
    }

    public ImportFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Chọn checked hay unchecked exception theo hợp đồng của tầng ứng dụng:

- Checked exception buộc caller xử lý hoặc khai báo tiếp.
- Unchecked exception phù hợp với nhiều lỗi ứng dụng cần được xử lý ở boundary chung như controller advice hoặc message consumer.
- Không chọn loại chỉ vì muốn tránh khai báo throws; hãy xem lỗi có phải một phần dự kiến trong hợp đồng use case và caller có thể xử lý có ý nghĩa hay không.

Không cần tạo hàng chục lớp exception chỉ để đổi tên lỗi thư viện. Tạo loại riêng khi tầng gọi cần phân biệt một tình huống có ý nghĩa, chẳng hạn payload không hợp lệ, nguồn dữ liệu không khả dụng hoặc thao tác bị từ chối theo quy tắc nghiệp vụ.

## 4. Bọc exception đúng cách

Mẫu cơ bản là bắt loại lỗi mà tầng hiện tại hiểu được, sau đó ném exception mới với cause:

~~~java
try {
    return mapper.readValue(input, OrderRequest.class);
} catch (JsonProcessingException exception) {
    throw new InvalidImportRequestException(
        "The order request cannot be parsed",
        exception
    );
}
~~~

Đây là exception translation: adapter chuyển lỗi của Jackson thành khái niệm lỗi thuộc ứng dụng. Cause vẫn là exception Jackson ban đầu.

Có thể thêm ngữ cảnh vào message:

~~~java
try {
    return mapper.readValue(input, OrderRequest.class);
} catch (JsonProcessingException exception) {
    throw new InvalidImportRequestException(
        "Cannot parse order payload for partner " + partnerCode,
        exception
    );
}
~~~

Ngữ cảnh nên giúp xác định use case hoặc nguồn dữ liệu. Tránh đưa toàn bộ JSON, token, mật khẩu, access token hoặc dữ liệu cá nhân vào message.

### 4.1. Bắt đúng loại exception

Chỉ bắt loại exception mà tầng đó có thể chuyển đổi có ý nghĩa. Ví dụ, adapter JSON có thể bắt JsonProcessingException. Nó không nên bắt mọi Exception chỉ để đổi thành InvalidImportRequestException:

~~~java
// Quá rộng: có thể biến lỗi lập trình hoặc lỗi hệ thống thành lỗi payload.
try {
    return mapper.readValue(input, OrderRequest.class);
} catch (Exception exception) {
    throw new InvalidImportRequestException("Invalid payload", exception);
}
~~~

Đoạn code quá rộng có thể bắt cả lỗi không liên quan đến JSON, chẳng hạn lỗi trong logic xử lý tiếp theo, và phân loại sai thành lỗi đầu vào. Hãy thu hẹp try block chỉ bao quanh thao tác parse và bắt đúng loại exception mà thao tác đó có thể ném.

~~~java
OrderRequest request;
try {
    request = mapper.readValue(input, OrderRequest.class);
} catch (JsonProcessingException exception) {
    throw new InvalidImportRequestException(
        "Order payload is not valid",
        exception
    );
}

validateBusinessRules(request);
return orderService.create(request);
~~~

Như vậy, lỗi validation hoặc service không bị gắn nhầm nhãn “JSON không hợp lệ”.

## 5. Không làm mất nguyên nhân khi rethrow

Nếu không cần đổi loại exception, có thể ném lại chính instance đã bắt:

~~~java
try {
    performOperation();
} catch (IOException exception) {
    log.debug("I/O operation failed; propagating", exception);
    throw exception;
}
~~~

Làm như vậy giữ nguyên loại exception, stack trace và cause hiện có. Không tạo wrapper mới nếu tầng hiện tại không bổ sung ngữ cảnh hay thay đổi hợp đồng.

Nếu cần bổ sung ngữ cảnh, bọc exception và truyền nó làm cause:

~~~java
try {
    performOperation();
} catch (IOException exception) {
    throw new ReportGenerationException(
        "Could not generate monthly report",
        exception
    );
}
~~~

Không ném exception mới mà không truyền cause:

~~~java
catch (IOException exception) {
    throw new ReportGenerationException("Could not generate monthly report");
}
~~~

Cách viết cuối làm mất đường dẫn đến lỗi I/O gốc. Nếu message gốc không còn được giữ ở nơi khác, việc điều tra sẽ khó hơn đáng kể.

## 6. Bọc lỗi tại đúng ranh giới

Không phải lúc nào cũng nên để exception kỹ thuật đi xuyên qua toàn bộ hệ thống. Nếu adapter là ranh giới giữa Jackson và ứng dụng, caller không nên phải hiểu chi tiết JsonMappingException.

~~~text
JSON bytes
   |
   v
Jackson adapter
   |  JsonMappingException
   v
InvalidImportRequestException
   |
   v
Application service
   |  ImportFailedException
   v
HTTP / message boundary
   |  400 / rejected message
   v
Client or broker
~~~

Mỗi tầng chỉ bọc khi có thêm ý nghĩa. Nếu ImportFailedException chỉ lặp lại message mà không thêm ngữ cảnh hoặc hợp đồng mới, wrapper đó không có ích.

Không nên tạo chuỗi wrapper dày đặc như:

~~~text
ServiceException
  -> UseCaseException
    -> BusinessServiceException
      -> AdapterException
        -> JsonException
~~~

Một exception cho mỗi method khiến stack trace dài nhưng không giúp phân loại lỗi. Tốt hơn là đặt exception translation tại ranh giới thư viện/hệ thống và tại ranh giới use case khi thực sự cần.

## 7. Giữ lại thông tin đường dẫn của Jackson

JsonMappingException có thể chứa reference path chỉ ra property hoặc index nơi ánh xạ thất bại. Ví dụ payload có:

~~~json
{
  "orders": [
    {
      "id": 101,
      "quantity": "many"
    }
  ]
}
~~~

Nếu quantity yêu cầu số nguyên, Jackson có thể chỉ ra lỗi ở đường dẫn orders[0].quantity.

Khi bọc exception, truyền nguyên exception làm cause:

~~~java
catch (JsonMappingException exception) {
    throw new InvalidImportRequestException(
        "Order payload does not match the expected structure",
        exception
    );
}
~~~

Không chỉ lấy exception.getOriginalMessage() rồi bỏ object exception. Khi cần chẩn đoán, có thể xem path của lỗi gốc:

~~~java
Throwable cause = applicationException.getCause();

if (cause instanceof JsonMappingException mappingException) {
    String path = mappingException.getPathReference();
    // Ghi nhận path đã được kiểm soát trong diagnostic log.
}
~~~

getPathReference() có thể chứa tên property và index. Đây là thông tin hữu ích để chỉ ra vị trí sai mà không cần ghi toàn bộ payload. Tùy phiên bản Jackson, API path có thể cung cấp danh sách JsonMappingException.Reference; hãy dùng API tương ứng với dependency của dự án.

JsonParseException thường phản ánh lỗi cú pháp hoặc token ở cấp parser, còn JsonMappingException thường phản ánh lỗi khi ánh xạ cấu trúc JSON sang kiểu Java. Có thể phân loại chúng riêng nếu ứng dụng có cách phản hồi khác nhau; dù vậy, cả hai vẫn có thể được giữ làm cause của một exception ứng dụng chung.

## 8. Phân biệt lỗi parse, lỗi validation và lỗi nghiệp vụ

Một payload có thể vượt qua cú pháp JSON nhưng vẫn không hợp lệ với hợp đồng hoặc nghiệp vụ.

~~~json
{
  "orderId": "ORD-1001",
  "quantity": -3
}
~~~

Đây là JSON hợp lệ. Jackson có thể ánh xạ thành DTO thành công. Nhưng quantity âm có thể vi phạm quy tắc nghiệp vụ.

Nên phân biệt:

| Loại lỗi | Ví dụ | Tầng phát hiện | Loại lỗi ứng dụng có thể dùng |
|---|---|---|---|
| Cú pháp JSON | Thiếu dấu ngoặc hoặc dấu phẩy | Jackson parser | InvalidImportRequestException |
| Lỗi mapping | Chuỗi không chuyển được sang số | Jackson Databind | InvalidImportRequestException |
| Lỗi cấu trúc/validation | Thiếu order ID, trường bắt buộc rỗng | Validator/application boundary | RequestValidationException |
| Lỗi nghiệp vụ | Đơn hàng đã đóng, tồn kho không đủ | Domain/application service | OrderRejectedException |
| Lỗi hạ tầng | Database không kết nối | Repository/adapter | PersistenceUnavailableException |
| Lỗi lập trình | Null ngoài dự kiến hoặc invariant bị phá | Code nội bộ | Thường để lỗi được phát hiện và sửa, không đổi thành lỗi client |

Không nên bắt mọi lỗi rồi trả về “Invalid JSON”. Làm vậy khiến client nhận sai mã lỗi và đội vận hành khó biết lỗi thực sự nằm ở đâu.

## 9. Giữ nguyên cause qua nhiều tầng

Một use case có thể cần bổ sung ngữ cảnh ở nhiều ranh giới:

~~~java
public ImportResult importPartnerBatch(String partner, String json) {
    try {
        List<OrderRequest> orders = jsonAdapter.parseOrders(json);
        return importService.importOrders(partner, orders);
    } catch (InvalidImportRequestException exception) {
        throw new PartnerBatchImportException(
            "Could not import batch from partner " + partner,
            exception
        );
    }
}
~~~

Ở đây, PartnerBatchImportException giữ InvalidImportRequestException làm cause; exception đó lại giữ JsonProcessingException. Chuỗi nguyên nhân vẫn truy ngược được tới Jackson.

Nếu lỗi xảy ra ở importService và đã là exception nghiệp vụ, không nên vô tình bọc nó thành lỗi parse. Có thể bắt riêng loại exception mà tầng hiện tại muốn thêm ngữ cảnh, hoặc để nó đi qua.

Một quy tắc hữu ích: **chỉ bọc exception khi tầng hiện tại có thể đặt tên tình huống rõ hơn hoặc cần thay đổi hợp đồng lỗi cho caller**.

## 10. Ghi log mà không làm mất stack trace

Log exception object, không chỉ log message:

~~~java
try {
    importService.importBatch(batch);
} catch (ImportFailedException exception) {
    logger.error("Partner batch import failed", exception);
    throw exception;
}
~~~

Logger nhận exception sẽ ghi stack trace và cause chain. Nếu chỉ ghi:

~~~java
logger.error("Partner batch import failed: {}", exception.getMessage());
~~~

thì log thường chỉ có message, không có stack trace hay cause chain.

Tuy nhiên, không nên log cùng một exception ở mọi tầng rồi tiếp tục ném lên. Điều đó tạo nhiều bản stack trace giống nhau, làm nhiễu log và tăng chi phí lưu trữ. Thường nên log một lần ở boundary chịu trách nhiệm ghi nhận lỗi cuối cùng, còn các tầng dưới chỉ bọc và truyền lỗi.

Nếu cần log ở tầng thấp để thêm context, hãy cân nhắc log ở mức phù hợp và tránh log lại toàn bộ stack trace ở tầng trên. Cần giữ correlation ID, batch ID hoặc request ID để liên kết các bản ghi.

## 11. Không trả cause hoặc stack trace thô cho client

Cause chain dành cho chẩn đoán nội bộ. Không nên trả trực tiếp stack trace, tên class nội bộ, câu SQL, đường dẫn file, thông tin máy chủ hoặc message chi tiết của thư viện cho client.

Ví dụ không an toàn:

~~~java
catch (Exception exception) {
    return ResponseEntity.internalServerError()
        .body(exception.toString());
}
~~~

Response công khai nên dùng mã lỗi và message ổn định:

~~~json
{
  "code": "INVALID_IMPORT_REQUEST",
  "message": "The import request is invalid",
  "requestId": "req-8f21"
}
~~~

Chi tiết kỹ thuật được ghi trong log có kiểm soát, gắn cùng request ID. Client có thể dùng request ID để yêu cầu hỗ trợ mà không nhìn thấy stack trace hoặc dữ liệu nội bộ.

Với Spring MVC, có thể dùng @RestControllerAdvice để chuyển exception ứng dụng thành response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(InvalidImportRequestException.class)
    ResponseEntity<ApiError> handleInvalidImport(
            InvalidImportRequestException exception) {

        ApiError body = new ApiError(
            "INVALID_IMPORT_REQUEST",
            "The import request is invalid"
        );

        return ResponseEntity.badRequest().body(body);
    }
}

public record ApiError(String code, String message) {
}
~~~

Nếu cần chẩn đoán, log exception tại handler hoặc một boundary logging thống nhất; không đưa exception.getCause() hay stack trace vào ApiError.

Với Spring Framework hỗ trợ ProblemDetail, có thể biểu diễn lỗi theo Problem Details format. Dù dùng DTO riêng hay ProblemDetail, nguyên tắc vẫn giống nhau: response ổn định và không chứa nội dung nội bộ của cause.

## 12. Xử lý lỗi khi đọc JSON trong adapter

Một adapter JSON nên chịu trách nhiệm chuyển exception Jackson thành lỗi ứng dụng có ngữ nghĩa phù hợp:

~~~java
public final class JacksonOrderRequestReader {
    private final ObjectReader reader;

    public JacksonOrderRequestReader(ObjectMapper mapper) {
        this.reader = mapper.readerFor(OrderRequest.class);
    }

    public OrderRequest read(String json) {
        try {
            return reader.readValue(json);
        } catch (JsonProcessingException exception) {
            throw new InvalidImportRequestException(
                "Order request JSON is invalid",
                exception
            );
        }
    }
}
~~~

Lợi ích:

- Application service không phụ thuộc Jackson.
- Adapter tập trung xử lý lỗi của thư viện.
- Cause chain vẫn giữ thông tin mapping/path.
- Unit test adapter có thể kiểm tra loại exception và cause.
- Có thể thay cách parse hoặc thư viện mà ít ảnh hưởng đến use case.

Nếu adapter nhận InputStream, chữ ký của readValue() có thể ném IOException. Hãy xác định lỗi I/O có cùng ý nghĩa với payload sai hay là lỗi nguồn dữ liệu không khả dụng. Không nên gộp lỗi file/network bị gián đoạn vào InvalidImportRequestException nếu client gửi payload đúng nhưng hệ thống không đọc được nguồn.

Ví dụ tách lỗi:

~~~java
public OrderRequest read(InputStream input) {
    try {
        return reader.readValue(input);
    } catch (JsonProcessingException exception) {
        throw new InvalidImportRequestException(
            "Order payload is malformed",
            exception
        );
    } catch (IOException exception) {
        throw new ImportSourceReadException(
            "Could not read the import source",
            exception
        );
    }
}
~~~

Vì JsonProcessingException là một loại IOException trong các dòng Jackson 2.x phổ biến, cần đặt catch cụ thể trước catch tổng quát hơn. Kiểm tra chữ ký và hierarchy theo phiên bản Jackson của dự án.

## 13. Khi chuyển lỗi trong try-with-resources

Java try-with-resources có thể tạo suppressed exception khi cả phần thân và thao tác đóng tài nguyên đều thất bại.

~~~java
try (InputStream input = Files.newInputStream(path)) {
    parse(input);
}
~~~

Nếu parse(input) ném exception và input.close() cũng ném exception, lỗi parse thường là exception chính; lỗi đóng stream được gắn vào danh sách suppressed exceptions qua getSuppressed().

Khi bọc exception chính, hãy truyền nguyên object làm cause:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    parse(input);
} catch (IOException exception) {
    throw new ImportSourceReadException(
        "Could not read import file " + safeFileName,
        exception
    );
}
~~~

Cause vẫn giữ suppressed exceptions của nó. Không tạo exception mới chỉ từ message, vì điều đó có thể làm mất cả cause chain và các lỗi suppressed gắn với exception ban đầu.

Có thể kiểm tra suppressed exception khi chẩn đoán:

~~~java
for (Throwable suppressed : exception.getSuppressed()) {
    logger.warn("A resource close operation also failed", suppressed);
}
~~~

Thông thường logger đã hiển thị suppressed exceptions khi ghi stack trace đầy đủ. Chỉ cần xử lý riêng khi ứng dụng có yêu cầu quan sát đặc biệt.

## 14. Xử lý InterruptedException đúng cách

Một trường hợp đặc biệt là InterruptedException. Nếu bắt nó rồi chuyển thành exception ứng dụng mà không khôi phục trạng thái interrupt, ứng dụng có thể làm mất tín hiệu hủy từ thread quản lý.

Ví dụ:

~~~java
try {
    queue.put(item);
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();

    throw new ImportCancelledException(
        "Import was interrupted",
        exception
    );
}
~~~

Thread.currentThread().interrupt() khôi phục interrupt flag trước khi chuyển lỗi. Cause vẫn giữ InterruptedException.

Nếu phương thức có thể khai báo throws InterruptedException và caller có trách nhiệm xử lý, có thể ném lại trực tiếp. Chỉ chuyển thành exception ứng dụng khi use case cần một hợp đồng riêng, nhưng vẫn phải giữ trạng thái interrupt.

Không bắt InterruptedException rồi tiếp tục xử lý như không có gì xảy ra. Điều đó có thể khiến shutdown hoặc cancellation không hoạt động đúng.

## 15. Không nuốt lỗi và tiếp tục với dữ liệu giả

Một lỗi phổ biến là bắt exception rồi trả giá trị mặc định:

~~~java
public OrderRequest parse(String json) {
    try {
        return mapper.readValue(json, OrderRequest.class);
    } catch (JsonProcessingException exception) {
        logger.warn("Invalid order JSON");
        return new OrderRequest();
    }
}
~~~

Caller không thể phân biệt payload hợp lệ nhưng rỗng với payload không parse được. Lỗi ban đầu cũng không còn trong kết quả hoặc cause chain.

Nếu nghiệp vụ cho phép bỏ qua một record lỗi, hãy biểu diễn rõ kết quả:

~~~java
public sealed interface ParseResult<T> {
    record Success<T>(T value) implements ParseResult<T> {}
    record Failure<T>(String code, Throwable cause)
        implements ParseResult<T> {}
}
~~~

Hoặc ném exception ứng dụng để boundary quyết định dừng job, từ chối record hay tiếp tục. Không dùng object rỗng hoặc null làm tín hiệu lỗi nếu hợp đồng không quy định rõ.

## 16. Phân biệt exception với Error

Java có Exception và Error dưới Throwable. Exception thường biểu diễn tình huống ứng dụng có thể xử lý; Error thường biểu diễn tình trạng nghiêm trọng của JVM hoặc môi trường thực thi, chẳng hạn OutOfMemoryError hoặc StackOverflowError.

Không nên bắt Throwable hoặc Error rồi bọc thành lỗi nghiệp vụ chung:

~~~java
// Không nên.
try {
    runImport();
} catch (Throwable throwable) {
    throw new ImportFailedException("Import failed", throwable);
}
~~~

Việc này có thể bắt cả lỗi nghiêm trọng mà ứng dụng không thể phục hồi. Hãy bắt những exception dự kiến và có cách xử lý. Với Error, thường để nó lan truyền sau khi các tài nguyên được giải phóng bởi cơ chế phù hợp.

Không phải mọi RuntimeException đều là lỗi lập trình; một số exception ứng dụng unchecked là cách biểu diễn lỗi nghiệp vụ dự kiến. Điều quan trọng là phân loại theo hợp đồng và trách nhiệm của tầng, không chỉ theo checked/unchecked.

## 17. Thiết kế cause chain có ý nghĩa

Một cause chain tốt nên trả lời được:

1. Use case nào thất bại?
2. Tầng nào phát hiện hoặc chuyển đổi lỗi?
3. Lỗi kỹ thuật ban đầu là gì?
4. Vị trí dữ liệu hoặc tài nguyên nào liên quan?
5. Có lỗi phụ nào xảy ra khi dọn dẹp tài nguyên?

Ví dụ:

~~~text
PartnerBatchImportException
  message: Could not import batch B-2026-001 from partner A
  caused by InvalidImportRequestException
    message: Order request JSON is invalid
    caused by JsonMappingException
      path: orders[3].quantity
      caused by NumberFormatException
~~~

Message ở mỗi tầng bổ sung ngữ cảnh. Cause chain bảo toàn chi tiết gốc. Diagnostic metadata như request ID, batch ID hoặc source name nên được lưu ở context có cấu trúc/log field, không nhất thiết phải nhồi mọi thứ vào message.

Không lặp lại cùng một thông tin ở mọi wrapper. Nếu batch ID đã được log có cấu trúc ở boundary, wrapper dưới không cần đưa lại toàn bộ payload hoặc metadata nhạy cảm.

## 18. Kiểm thử cause chain

Một test cần xác nhận không chỉ exception ngoài cùng mà cả cause trực tiếp và nguyên nhân sâu hơn.

~~~java
@Test
void wrapsJacksonFailureAndPreservesOriginalCause() {
    String invalidJson = """
        {
          "orderId": "ORD-1",
          "quantity": "not-a-number"
        }
        """;

    InvalidImportRequestException exception = assertThrows(
        InvalidImportRequestException.class,
        () -> reader.read(invalidJson)
    );

    assertNotNull(exception.getCause());
    assertInstanceOf(
        JsonProcessingException.class,
        exception.getCause()
    );
}
~~~

Nếu cần xác nhận Jackson path:

~~~java
Throwable cause = exception.getCause();

assertInstanceOf(JsonMappingException.class, cause);

JsonMappingException mappingException =
    (JsonMappingException) cause;

assertFalse(mappingException.getPath().isEmpty());
~~~

Dữ liệu cụ thể trong test phải thật sự làm Jackson thất bại khi ánh xạ OrderRequest. Nếu quantity là String trong DTO thì ví dụ không gây lỗi; hãy dùng kiểu đích phù hợp như int hoặc một field có deserializer/validation tương ứng.

Có thể kiểm thử chuỗi nguyên nhân nhiều tầng:

~~~java
assertInstanceOf(
    JsonMappingException.class,
    exception.getCause()
);

assertNotNull(exception.getCause().getStackTrace());
~~~

Không nên assert toàn bộ stack trace theo số dòng hoặc tên file vì chúng có thể thay đổi giữa phiên bản compiler, dependency và môi trường. Hãy kiểm tra loại exception, cause và path cần thiết.

### 18.1. Test lỗi bị bọc ở tầng use case

~~~java
@Test
void addsBatchContextWithoutDiscardingAdapterCause() {
    PartnerBatchImportException exception = assertThrows(
        PartnerBatchImportException.class,
        () -> importService.importBatch("partner-a", invalidPayload)
    );

    assertInstanceOf(
        InvalidImportRequestException.class,
        exception.getCause()
    );

    assertInstanceOf(
        JsonProcessingException.class,
        exception.getCause().getCause()
    );
}
~~~

Test này xác nhận mỗi tầng bổ sung ngữ cảnh mà vẫn giữ cause từ tầng dưới. Dùng test như vậy khi cause chain là một phần quan trọng của khả năng chẩn đoán hệ thống.

## 19. Kiểm tra exception ở ranh giới HTTP

Ngoài unit test service, có thể kiểm tra controller advice trả mã lỗi ổn định mà không lộ thông tin cause:

~~~java
@Test
void mapsInvalidImportToClientErrorWithoutExposingCause() throws Exception {
    mockMvc.perform(post("/imports")
            .contentType(MediaType.APPLICATION_JSON)
            .content(invalidPayload))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code")
            .value("INVALID_IMPORT_REQUEST"))
        .andExpect(jsonPath("$.message")
            .value("The import request is invalid"))
        .andExpect(jsonPath("$.stackTrace").doesNotExist());
}
~~~

Test này kiểm tra hai ranh giới riêng:

- Nội bộ: exception ứng dụng giữ cause để điều tra.
- Bên ngoài: HTTP response chỉ trả mã và message đã được công bố.

Không cần đưa exception object hoặc cause vào JSON response để chứng minh lỗi đã được giữ.

## 20. Những lỗi thường gặp

### Chỉ truyền message của exception gốc

~~~java
throw new ApplicationException(exception.getMessage());
~~~

Cách này làm mất cause. Dùng constructor nhận cause.

### Bắt Exception quá rộng

Có thể phân loại sai lỗi lập trình, lỗi hạ tầng hoặc lỗi nghiệp vụ thành lỗi payload. Thu hẹp try block và bắt đúng loại.

### Bọc cùng một lỗi ở mọi method

Cause chain dài nhưng không có ngữ cảnh mới. Chỉ chuyển đổi tại boundary có trách nhiệm rõ ràng.

### Log message thay vì exception object

Stack trace và cause chain không được ghi. Truyền exception vào logger khi cần log lỗi.

### Log cùng lỗi nhiều lần

Nhiều stack trace trùng nhau gây nhiễu. Chọn một boundary chịu trách nhiệm ghi log đầy đủ.

### Trả stack trace cho client

Có thể lộ class nội bộ, đường dẫn, SQL hoặc thông tin hệ thống. Dùng error code/message ổn định và request ID.

### Nuốt exception rồi trả object rỗng

Caller không phân biệt dữ liệu rỗng hợp lệ với lỗi parse. Hãy ném exception hoặc trả kiểu kết quả có trạng thái rõ ràng.

### Bắt InterruptedException nhưng không khôi phục interrupt

Tín hiệu hủy bị mất. Khôi phục flag trước khi chuyển lỗi hoặc truyền exception lên caller.

### Bắt Throwable để bọc mọi lỗi

Có thể nuốt Error nghiêm trọng. Chỉ bắt các exception dự kiến có thể xử lý.

### Tạo cause chain nhưng làm mất metadata Jackson

Chỉ lưu message khiến path của JsonMappingException biến mất. Truyền exception gốc làm cause và truy cập path khi cần.

## 21. Quy trình chuyển lỗi sang lớp ứng dụng

Khi tích hợp thư viện hoặc adapter, hãy áp dụng trình tự:

1. Xác định exception kỹ thuật có thể phát sinh từ thao tác cụ thể.
2. Phân biệt lỗi cú pháp, mapping, validation, nghiệp vụ và hạ tầng.
3. Chọn exception ứng dụng mà caller có thể xử lý có ý nghĩa.
4. Chỉ bọc tại boundary nơi có thêm ngữ cảnh hoặc thay đổi hợp đồng.
5. Dùng constructor nhận message và cause để giữ nguyên nguyên nhân.
6. Thu hẹp try block để không phân loại nhầm lỗi ở bước tiếp theo.
7. Giữ metadata hữu ích như Jackson path, request ID và batch ID trong log/context có cấu trúc.
8. Không ghi toàn bộ payload hoặc secret vào message/log.
9. Ghi log stack trace tại boundary phù hợp; tránh log lặp ở mọi tầng.
10. Trả error code/message ổn định cho client, không trả cause hoặc stack trace.
11. Khôi phục interrupt nếu chuyển InterruptedException.
12. Không bắt Error hoặc nuốt lỗi rồi tiếp tục với dữ liệu giả.
13. Viết test xác nhận exception ngoài cùng, cause chain và response HTTP.
14. Kiểm tra các lỗi suppressed khi thao tác đóng tài nguyên cũng thất bại.

## 22. Bảng ghi nhớ

| Tình huống | Cách làm |
|---|---|
| Chuyển lỗi thư viện thành lỗi ứng dụng | new AppException(message, cause) |
| Không cần đổi loại exception | Ném lại chính exception đã bắt |
| Cần thêm ngữ cảnh use case | Bọc một lần tại application boundary |
| Giữ path của Jackson | Truyền JsonMappingException làm cause |
| Phân loại lỗi parse | Bắt JsonProcessingException trong adapter |
| Phân loại lỗi I/O nguồn | Dùng exception ứng dụng riêng nếu khác ý nghĩa với payload sai |
| Ghi stack trace | Truyền exception object vào logger |
| Trả lỗi HTTP | Error code/message ổn định, không trả cause |
| Giữ tín hiệu hủy thread | Khôi phục interrupt flag khi chuyển InterruptedException |
| Dọn dẹp tài nguyên lỗi | Giữ exception chính và suppressed exceptions |
| Kiểm tra nguyên nhân | Assert getCause() và loại/path của cause |
| Lỗi JVM nghiêm trọng | Không bắt Error để bọc thành lỗi nghiệp vụ |

## 23. Kết luận

Chuyển một lỗi kỹ thuật thành exception của ứng dụng là cách giữ ranh giới giữa adapter và logic nghiệp vụ. Exception mới cung cấp tên gọi và ngữ cảnh phù hợp với tầng gọi; cause phải giữ exception ban đầu để stack trace, loại lỗi, reference path của Jackson và thông tin chẩn đoán không bị mất.

Hãy bọc lỗi bằng constructor nhận cause, bắt đúng loại exception trong try block hẹp và chỉ tạo wrapper khi có thêm ý nghĩa cho caller. Ghi log exception object tại boundary phù hợp, giữ metadata chẩn đoán có kiểm soát và chỉ trả error code/message ổn định ra bên ngoài. Kiểm thử cause chain cùng response HTTP giúp bảo đảm ứng dụng vừa dễ vận hành vừa không để chi tiết nội bộ rò rỉ sang client.
