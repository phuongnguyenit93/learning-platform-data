# Phân loại dữ liệu không hợp lệ, xung đột, từ chối nghiệp vụ và lỗi hạ tầng

Một hệ thống phân tầng cần phân biệt rõ các nguyên nhân khiến một yêu cầu không hoàn thành. Request có thể sai định dạng, dữ liệu có thể xung đột với trạng thái hiện tại, một chính sách nghiệp vụ có thể từ chối hành động, hoặc một thành phần kỹ thuật có thể không hoạt động. Những tình huống này khác nhau về trách nhiệm xử lý, cách phản hồi cho người gọi, khả năng thử lại và cách theo dõi vận hành.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — việc phân loại lỗi là một mối quan tâm xuyên tầng. Tầng trình bày nhận diện lỗi của hợp đồng giao tiếp và chuyển kết quả thành phản hồi theo giao thức. Tầng ứng dụng điều phối ca sử dụng và ngữ cảnh. Domain xác định hành động có được phép theo quy tắc nghiệp vụ hay không. Adapter hạ tầng nhận diện lỗi từ cơ sở dữ liệu, mạng và dịch vụ bên ngoài. Cách phân loại nhất quán giúp các tầng giữ đúng trách nhiệm và giúp người vận hành biết cần sửa dữ liệu, xử lý xung đột, giải thích quyết định nghiệp vụ hay khôi phục một thành phần kỹ thuật.

## 1. Bốn nhóm tình huống cần phân biệt

Hãy xét API đặt hàng. Một yêu cầu có thể thất bại theo nhiều cách:

- JSON gửi lên bị hỏng hoặc số lượng không phải số nguyên dương theo hợp đồng API.
- Khách hàng gửi phiên bản đơn hàng cũ trong khi một nhân viên khác vừa cập nhật đơn.
- Đơn hàng hợp lệ về cấu trúc nhưng khách hàng đã vượt hạn mức mua chịu theo chính sách.
- Cơ sở dữ liệu không khả dụng trong lúc ứng dụng lưu đơn.

Nếu gom tất cả thành một lỗi chung như “request failed”, người gọi không biết nên sửa nội dung, tải lại dữ liệu, chấp nhận quyết định nghiệp vụ hay thử lại sau. Bảng sau tóm tắt sự khác nhau:

| Nhóm | Ý nghĩa | Ví dụ | Xử lý thường gặp |
|---|---|---|---|
| Dữ liệu không hợp lệ (invalid data) | Dữ liệu không đáp ứng cú pháp, kiểu hoặc hợp đồng đầu vào. | JSON sai, thiếu trường bắt buộc, UUID không phân tích được, quantity âm khi API yêu cầu số dương. | Trả lỗi đầu vào có thông tin theo trường; yêu cầu người gọi sửa dữ liệu. |
| Xung đột (conflict) | Yêu cầu hợp lệ riêng lẻ nhưng không thể áp dụng an toàn lên trạng thái hiện tại hoặc phiên bản hiện tại. | Cập nhật bằng version cũ, mã định danh đã được dùng, chuyển trạng thái bị một thao tác đồng thời thay đổi trước đó. | Trả thông tin xung đột; tải lại trạng thái hoặc giải quyết tranh chấp rồi thử lại khi phù hợp. |
| Từ chối nghiệp vụ (business rejection) | Hệ thống hiểu yêu cầu nhưng chính sách hoặc quy tắc nghiệp vụ không cho phép thực hiện. | Khách hàng không đủ điều kiện mua chịu, vượt hạn mức, sản phẩm không được bán cho nhóm khách hàng này. | Giải thích quyết định ở mức người dùng được phép biết; có thể đề xuất hành động hợp lệ khác. |
| Lỗi hạ tầng (infrastructure failure) | Thành phần kỹ thuật không thể hoàn thành thao tác do sự cố vận hành hoặc phụ thuộc bên ngoài. | Database mất kết nối, dịch vụ thanh toán timeout, broker không sẵn sàng, lỗi cấu hình. | Ghi nhận để vận hành xử lý; retry có kiểm soát nếu lỗi tạm thời và thao tác an toàn. |

Các nhóm này không nhất thiết tương ứng một-một với mã HTTP hoặc một lớp exception. Mã HTTP là cách REST adapter biểu diễn kết quả theo hợp đồng API. CLI, message consumer hoặc giao diện web có thể dùng cách trình bày khác cho cùng một nguyên nhân.

## 2. Dữ liệu không hợp lệ: lỗi ở hợp đồng đầu vào

Dữ liệu không hợp lệ xuất hiện khi đầu vào không thể được hiểu hoặc không đáp ứng cấu trúc mà kênh giao tiếp công bố. Ví dụ:

- JSON thiếu dấu ngoặc hoặc sai kiểu dữ liệu.
- Trường bắt buộc bị thiếu.
- Chuỗi ngày không theo định dạng được chấp nhận.
- Mã định danh không thể phân tích thành UUID.
- Số lượng nằm ngoài miền giá trị được request contract cho phép.

Đối với REST API, tầng trình bày thường phát hiện các lỗi này khi parse request hoặc chạy Bean Validation. Một request DTO có thể dùng các annotation như @NotNull, @Positive, @Size và @Email để từ chối dữ liệu sai trước khi gọi ca sử dụng.

~~~java
public record CreateOrderRequest(
    @NotNull UUID customerId,
    @NotEmpty List<@Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
    @NotNull UUID productId,
    @Positive int quantity
) {}
~~~

Nếu JSON sai cú pháp hoặc không thể chuyển đổi sang kiểu đích, Spring MVC thường phát sinh lỗi binding/conversion. Nếu dữ liệu đã bind được nhưng vi phạm annotation validation, ứng dụng có thể nhận MethodArgumentNotValidException. Cả hai đều thuộc hợp đồng đầu vào HTTP và có thể được ánh xạ thành HTTP 400 theo quy ước API.

Cần phân biệt lỗi cấu trúc với quy tắc nghiệp vụ. Quantity là số nguyên dương có thể là một phần hợp đồng đầu vào và được kiểm tra sớm ở request DTO. Nhưng nếu “một đơn phải có ít nhất một dòng hàng” là bất biến của domain, mô hình Order vẫn cần bảo vệ điều kiện đó khi command được gọi từ CLI hoặc message consumer. Kiểm tra ở controller không thể thay thế quy tắc có thẩm quyền ở domain.

Thông báo lỗi nên chỉ ra trường hoặc vị trí cần sửa, ví dụ:

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "Dữ liệu đầu vào không hợp lệ",
  "fieldErrors": [
    {
      "field": "lines[0].quantity",
      "code": "must_be_positive",
      "message": "Số lượng phải lớn hơn 0"
    }
  ]
}
~~~

Không nên trả lại toàn bộ request nếu request có thể chứa mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân. Cũng không nên đưa stack trace hoặc chi tiết parser nội bộ vào response công khai.

## 3. Xung đột: yêu cầu không còn phù hợp với trạng thái hiện tại

Xung đột thường xảy ra khi trạng thái đã thay đổi giữa thời điểm người gọi đọc dữ liệu và thời điểm họ gửi cập nhật, hoặc khi một ràng buộc duy nhất đã bị một thao tác khác chiếm trước.

Ví dụ, màn hình quản trị tải đơn hàng với version 4. Trong lúc nhân viên chỉnh sửa, một tiến trình khác đã cập nhật đơn lên version 5. Nếu request cũ tiếp tục ghi mà không phát hiện xung đột, thay đổi mới có thể bị ghi đè.

Optimistic locking trong JPA có thể dùng trường @Version:

~~~java
@Entity
class OrderJpaEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    private String deliveryNote;
}
~~~

Khi một transaction cập nhật dựa trên version cũ, JPA provider có thể phát sinh OptimisticLockException hoặc ngoại lệ Spring tương ứng. Adapter/application nhận biết đây là xung đột trạng thái và chuyển thành một lỗi ứng dụng ổn định, chẳng hạn OrderVersionConflictException. REST adapter có thể trả HTTP 409 Conflict để client tải lại dữ liệu và quyết định cách hợp nhất thay đổi.

~~~java
@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderVersionConflictException.class)
    ResponseEntity<ApiError> handleVersionConflict(
            OrderVersionConflictException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "ORDER_VERSION_CONFLICT",
                "Đơn hàng đã được cập nhật. Hãy tải lại trước khi tiếp tục."
            ));
    }
}

record ApiError(String code, String message) {}
~~~

Một số xung đột khác gồm:

- Tạo tài khoản với email đã tồn tại và database có unique constraint.
- Hủy một đơn đã được giao bởi một thao tác khác.
- Đặt chỗ một suất cuối cùng trong khi người khác vừa giữ suất đó.
- Cập nhật một tài nguyên bằng ETag hoặc version không còn mới.

Không phải mọi conflict đều có thể retry ngay. Với optimistic locking, client thường cần tải lại dữ liệu và xem xét lại ý định. Với thao tác đặt chỗ, có thể cần thông báo suất không còn. Với unique constraint, người dùng có thể chọn một giá trị khác. Retry tự động chỉ phù hợp khi ứng dụng biết cách lặp lại an toàn và có thể đánh giá lại điều kiện.

## 4. Từ chối nghiệp vụ: yêu cầu được hiểu nhưng không được phép thực hiện

Business rejection là kết quả của một quyết định nghiệp vụ. Dữ liệu có thể hoàn toàn đúng cú pháp, tài nguyên có thể tồn tại và hệ thống kỹ thuật có thể hoạt động bình thường, nhưng chính sách không cho phép hành động.

Ví dụ:

- Khách hàng chưa đủ điều kiện mua chịu.
- Đơn vượt hạn mức tín dụng.
- Sản phẩm không được bán cho khu vực giao hàng đã chọn.
- Nhân viên không có quyền phê duyệt khoản hoàn tiền theo cấp hạn mức.
- Đơn đã ở trạng thái không cho phép hủy theo chính sách hiện tại.

Những điều kiện này cần được kiểm tra trong tầng ứng dụng hoặc domain policy/model tùy nơi sở hữu kiến thức. Domain có thể phát sinh một lỗi nghiệp vụ có tên rõ ràng:

~~~java
public void approve(CreditLimit limit, Money requestedAmount) {
    if (!limit.allows(requestedAmount)) {
        throw new CreditLimitExceededException();
    }

    this.status = ApplicationStatus.APPROVED;
}
~~~

Tuy nhiên, từ chối nghiệp vụ không nhất thiết phải được biểu diễn bằng exception. Nếu đây là kết quả dự kiến thường xuyên của ca sử dụng, application có thể trả một kiểu kết quả tường minh:

~~~java
public sealed interface CreditDecision {
    record Approved(CreditId creditId) implements CreditDecision {}
    record Rejected(String reasonCode) implements CreditDecision {}
}
~~~

Cách biểu diễn này giúp người gọi phân biệt kết quả nghiệp vụ bình thường với lỗi kỹ thuật bất ngờ. Ví dụ, việc một hồ sơ vay không đủ điều kiện có thể là một quyết định hợp lệ của hệ thống, không phải sự cố khiến request bị lỗi.

REST adapter chọn cách biểu diễn phù hợp với hợp đồng API. Tùy ngữ nghĩa, một business rejection có thể được ánh xạ thành HTTP 403 nếu người gọi không được phép thực hiện hành động, HTTP 422 nếu nội dung hợp lệ về cú pháp nhưng không thể xử lý theo chính sách, hoặc HTTP 409 nếu yêu cầu xung đột với trạng thái hiện tại. Không có một mã duy nhất bắt buộc cho mọi quyết định nghiệp vụ; API cần nhất quán và tài liệu hóa mã lỗi cùng ý nghĩa của nó.

Cũng cần phân biệt xác thực danh tính và quyền nghiệp vụ. Không đăng nhập hoặc token không hợp lệ thường được xử lý ở biên bảo mật với 401. Người gọi đã xác thực nhưng không có quyền truy cập tài nguyên có thể nhận 403. Một chính sách nghiệp vụ như vượt hạn mức không nhất thiết là lỗi phân quyền; nó có thể là một quyết định riêng của ca sử dụng.

## 5. Lỗi hạ tầng: sự cố kỹ thuật và khả năng phục hồi

Lỗi hạ tầng phát sinh khi ứng dụng không thể sử dụng một phụ thuộc kỹ thuật. Ví dụ:

- Database không thể kết nối hoặc transaction bị mất kết nối.
- HTTP client gọi dịch vụ thanh toán nhưng hết thời gian chờ.
- Message broker từ chối kết nối hoặc consumer không thể commit offset.
- File storage hoặc hệ thống gửi email không sẵn sàng.
- Cấu hình thiếu credential hoặc chứng thư TLS không hợp lệ.

Adapter hạ tầng thường là nơi tiếp xúc trực tiếp với thư viện và ngoại lệ kỹ thuật. Nó có thể chuyển ngoại lệ cụ thể thành kiểu lỗi ổn định mà tầng ứng dụng hiểu, ví dụ PaymentGatewayUnavailableException. Tầng ứng dụng quyết định ca sử dụng có thể tiếp tục, retry hoặc đánh dấu trạng thái chờ xử lý. REST adapter chuyển kết quả thành phản hồi HTTP thích hợp.

Cần phân biệt lỗi tạm thời và lỗi không thể tự phục hồi:

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Tạm thời (transient) | Timeout ngắn, kết nối database bị ngắt trong chốc lát, broker tạm mất khả dụng. | Retry có giới hạn, backoff và jitter nếu thao tác an toàn. |
| Không tạm thời (permanent) | Sai credential, thiếu cấu hình bắt buộc, schema không tương thích, dữ liệu không thể giải mã. | Không retry liên tục; ghi nhận, cảnh báo và sửa cấu hình hoặc dữ liệu. |
| Không rõ kết quả (ambiguous outcome) | Client timeout sau khi gửi lệnh thanh toán; dịch vụ có thể đã xử lý nhưng phản hồi không tới. | Tra cứu bằng idempotency key hoặc mã giao dịch; không gửi lặp mù quáng. |

HTTP API có thể dùng 500 cho lỗi nội bộ không dự kiến, 502 khi gateway nhận phản hồi không hợp lệ từ upstream, 503 khi dịch vụ tạm thời không sẵn sàng, hoặc 504 khi upstream timeout. Cách ánh xạ cụ thể phụ thuộc vai trò của ứng dụng và hợp đồng API. Không nên trả 500 cho một lỗi validation mà người dùng có thể sửa, cũng không nên trả 400 cho việc database bị ngắt kết nối.

Khi retry, cần xem thao tác có idempotent hay không. Một lệnh tạo đơn được gửi lại có thể tạo hai đơn nếu không có khóa idempotency hoặc cơ chế chống trùng. Timeout không chứng minh thao tác đã thất bại; nó chỉ cho biết bên gọi không nhận được kết quả đúng hạn. Với thanh toán, cần dùng mã yêu cầu ổn định và khả năng tra cứu trạng thái trước khi gửi lại.

## 6. Luồng phân loại lỗi qua các tầng

Một luồng xử lý có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A[Request từ REST, CLI hoặc message] --> B[Presentation adapter]
    B --> C{Cú pháp và hợp đồng hợp lệ?}
    C -- Không --> D[Lỗi dữ liệu đầu vào]
    C -- Có --> E[Application use case]
    E --> F[Domain model hoặc policy]
    F --> G{Hành động được phép?}
    G -- Không --> H[Từ chối nghiệp vụ]
    G -- Xung đột trạng thái --> I[Lỗi conflict]
    G -- Có --> J[Infrastructure adapter]
    J --> K{Phụ thuộc kỹ thuật thành công?}
    K -- Không --> L[Lỗi hạ tầng]
    K -- Có --> M[Kết quả thành công]
    D --> N[Adapter ánh xạ phản hồi]
    H --> N
    I --> N
    L --> N
    M --> N
~~~

Các tầng không cần biết chi tiết trình bày lỗi của mọi kênh:

- **Presentation adapter** nhận lỗi parse/validation và chuyển thành lỗi của giao thức; REST có thể trả JSON, CLI có thể in thông báo và exit code.
- **Application** điều phối ca sử dụng, cung cấp ngữ cảnh, phân biệt kết quả nghiệp vụ dự kiến với lỗi cần rollback hoặc chuyển trạng thái.
- **Domain** bảo vệ bất biến và biểu diễn lý do hành động không hợp lệ theo ngôn ngữ nghiệp vụ.
- **Infrastructure adapter** chuyển ngoại lệ từ JDBC, ORM, HTTP client hoặc broker thành lỗi kỹ thuật ổn định, không để thư viện cụ thể lan khắp ứng dụng.

Có thể dùng một lớp xử lý lỗi tập trung ở tầng trình bày như @RestControllerAdvice để ánh xạ ngoại lệ sang HTTP response. Nhưng việc tập trung ánh xạ không có nghĩa mọi tầng phải ném một loại exception chung. Tên và kiểu lỗi bên trong nên giữ được nguyên nhân đủ rõ để application, log và kiểm thử xử lý chính xác.

## 7. Thiết kế mã lỗi và thông điệp ổn định

Một API có thể dùng một cấu trúc lỗi chung:

~~~json
{
  "code": "ORDER_VERSION_CONFLICT",
  "message": "Đơn hàng đã được cập nhật. Hãy tải lại trước khi tiếp tục.",
  "traceId": "9b8f7d1a",
  "details": {
    "resource": "order"
  }
}
~~~

Các trường thường hữu ích:

- **code:** mã máy đọc được, ổn định qua các phiên bản nếu ý nghĩa không đổi.
- **message:** thông điệp ngắn, an toàn và phù hợp với người gọi.
- **fieldErrors:** danh sách lỗi theo trường khi dữ liệu đầu vào không hợp lệ.
- **traceId/correlationId:** mã để liên hệ phản hồi với log và trace vận hành.
- **details:** thông tin bổ sung đã được chọn lọc, không chứa bí mật hoặc dữ liệu nhạy cảm.

Không dùng nội dung exception kỹ thuật làm mã lỗi công khai. Ví dụ, thông báo JDBC có thể chứa tên máy chủ, tên bảng, câu SQL hoặc thông tin cấu hình. Hãy ghi chi tiết đó vào log nội bộ có kiểm soát và trả về mã ổn định như DATABASE_UNAVAILABLE.

Thông điệp cũng cần phân biệt điều người dùng có thể làm tiếp theo. Với invalid data, chỉ ra trường cần sửa. Với conflict, hướng dẫn tải lại hoặc làm mới trạng thái. Với business rejection, giải thích chính sách ở mức được phép công bố. Với infrastructure failure, cho biết thao tác chưa thể hoàn thành và có thể thử lại sau nếu hệ thống xác định retry là an toàn.

## 8. Logging, metrics và tracing cho lỗi xuyên tầng

Phân loại lỗi chỉ hữu ích khi hệ thống có thể quan sát được chúng. Một số nguyên tắc:

- Ghi log lỗi hạ tầng với exception gốc, tên dependency, operation, thời gian và trace/correlation ID. Không ghi token, mật khẩu, dữ liệu thanh toán hoặc toàn bộ payload nhạy cảm.
- Không nhất thiết log mọi lỗi đầu vào do người dùng gửi là ERROR. Validation sai thường là kết quả dự kiến; có thể ghi ở mức INFO hoặc chỉ đếm metric để tránh làm nhiễu log.
- Ghi nhận business rejection bằng mã lý do có kiểm soát để phân tích xu hướng, nhưng không biến mỗi lần khách hàng không đủ điều kiện thành sự cố hệ thống.
- Theo dõi conflict và optimistic lock failure để nhận biết mức độ tranh chấp. Tỷ lệ tăng cao có thể cho thấy cần điều chỉnh luồng cập nhật hoặc trải nghiệm người dùng.
- Dùng metric cho số lượng lỗi theo nhóm, dependency, operation và thời gian. Tránh đưa customerId, email hoặc giá trị tùy ý vào label có cardinality cao.
- Tracing giúp nối các bước giữa controller, application, repository và dịch vụ ngoài. Truyền correlation ID qua message hoặc HTTP call khi có thể.

Một lỗi có thể xuất hiện ở nhiều tầng nhưng chỉ nên có một nơi ghi log với stack trace đầy đủ để tránh ghi trùng. Các tầng khác có thể bổ sung ngữ cảnh bằng cách ném lại lỗi có nguyên nhân gốc hoặc gắn mã nghiệp vụ phù hợp. Khi bắt exception để xử lý, cần giữ cause và không nuốt lỗi khiến transaction commit ngoài ý muốn.

## 9. Kiểm thử phân loại và ánh xạ lỗi

Nên kiểm thử riêng việc phát hiện nguyên nhân và việc biểu diễn nguyên nhân theo kênh:

| Phạm vi | Kịch bản | Điều cần xác minh |
|---|---|---|
| Presentation test | JSON sai, thiếu trường, UUID không hợp lệ. | Adapter trả lỗi đầu vào đúng hợp đồng và không gọi ca sử dụng. |
| Domain test | Đơn rỗng, vượt hạn mức hoặc chuyển trạng thái không hợp lệ. | Domain từ chối theo quy tắc và không phụ thuộc HTTP/Spring Web. |
| Application test | Version cũ, tài nguyên không tồn tại, quyền không phù hợp. | Ca sử dụng phân biệt conflict, rejection và kết quả dự kiến. |
| Infrastructure integration test | Database timeout, unique constraint, optimistic lock. | Adapter chuyển lỗi kỹ thuật đúng loại và transaction có hành vi mong đợi. |
| API contract test | Các nhóm lỗi được trả qua REST. | HTTP status, error code, fieldErrors và message nhất quán. |
| Message adapter test | Broker lỗi hoặc consumer nhận message lặp. | Retry, dead-letter và idempotency được thực hiện theo chính sách. |

Ví dụ, test cho một API có thể xác minh lỗi validation:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "not-a-uuid",
              "lines": []
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
~~~

Một domain test riêng nên gọi trực tiếp hành vi domain với trạng thái không hợp lệ và xác minh exception hoặc kết quả rejection phù hợp. Test không cần tạo HTTP request để chứng minh domain bảo vệ bất biến.

## 10. Quy trình phân loại khi một ca sử dụng thất bại

Khi một yêu cầu không hoàn thành, hãy lần lượt xác định:

1. **Có thể phân tích và chuyển đổi đầu vào không?** Nếu không, phân loại là invalid data và chỉ ra phần hợp đồng bị vi phạm.
2. **Yêu cầu có dựa trên trạng thái đã cũ hoặc xung đột với thay đổi đồng thời không?** Nếu có, trả conflict và xác định người gọi cần tải lại, hợp nhất hay chọn thao tác khác.
3. **Trạng thái hiện tại có hợp lệ nhưng chính sách nghiệp vụ từ chối hành động không?** Nếu có, trả kết quả rejection có mã lý do rõ ràng.
4. **Một phụ thuộc kỹ thuật có thất bại không?** Nếu có, xác định lỗi tạm thời, lỗi cấu hình hay kết quả chưa rõ; chọn retry, cảnh báo hoặc đối soát tương ứng.
5. **Kênh giao tiếp cần biểu diễn kết quả thế nào?** Ánh xạ mã nội bộ thành HTTP status, CLI exit code hoặc chính sách ack/retry của message.
6. **Có đủ dấu vết để vận hành không?** Gắn trace ID, log nguyên nhân kỹ thuật ở nơi phù hợp và theo dõi metric theo nhóm lỗi.

Một thiết kế phân tầng tốt không xem mọi yêu cầu thất bại là cùng một loại sự cố. Dữ liệu không hợp lệ cần được sửa; conflict cần được giải quyết theo trạng thái mới; business rejection phản ánh quyết định của chính sách; lỗi hạ tầng cần được phục hồi hoặc xử lý vận hành. Khi mỗi tầng nhận diện và chuyển giao đúng loại lỗi, hệ thống có thể phản hồi rõ ràng, retry an toàn và quan sát được nguyên nhân mà không làm rò rỉ chi tiết nội bộ.

