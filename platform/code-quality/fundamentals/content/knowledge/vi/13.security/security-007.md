# Xử lý thất bại của kiểm tra an toàn theo hợp đồng

Giả sử một API chỉ cho phép chủ tài liệu đọc nội dung riêng tư. Khi dịch vụ kiểm tra quyền trả lời **không đủ quyền**, API phải từ chối. Nhưng nếu dịch vụ kiểm tra quyền **bị timeout**, hệ thống phải làm gì? Trả nội dung để giữ trải nghiệm thông suốt, trả “không có quyền”, hay thông báo chưa thể xác minh quyền?

Một câu trả lời sai có thể làm lộ dữ liệu; một câu trả lời mơ hồ có thể khiến phía gọi xử lý sai loại lỗi. Vì thế, **khả năng xử lý thất bại của một kiểm tra an toàn phải được xác định ngay trong hợp đồng**, chứ không được quyết định tình cờ bằng một khối catch hoặc giá trị mặc định.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã gắn với tính đáng tin cậy, dễ hiểu và dễ thay đổi. Ở chương **Bảo mật**, xử lý thất bại đúng nghĩa là giữ được **bất biến bảo mật** ngay cả khi đầu vào sai, dữ liệu thiếu, dịch vụ phụ thuộc gặp lỗi hoặc chương trình không nhận được kết quả kiểm tra rõ ràng.

## 1. Kiểm tra an toàn có thể thất bại theo nhiều cách

Các kiểm tra an toàn thường gặp trong ứng dụng Java:

- **Xác thực (authentication):** Có đủ bằng chứng rằng danh tính yêu cầu là hợp lệ không?
- **Phân quyền (authorization):** Danh tính đã xác thực có quyền thực hiện hành động trên tài nguyên cụ thể không?
- **Kiểm tra dữ liệu đầu vào:** Dữ liệu có đáp ứng hợp đồng, giới hạn và định dạng an toàn không?
- **Kiểm tra bất biến nghiệp vụ nhạy cảm:** Một lệnh chi tiền có vượt hạn mức hoặc bị thực hiện lặp không?
- **Kiểm tra ràng buộc tài nguyên:** Người dùng có thuộc đúng tenant, nhóm, vai trò hoặc phạm vi truy cập không?
- **Kiểm tra giới hạn lạm dụng:** Yêu cầu có vượt giới hạn được áp dụng cho tài khoản hoặc thao tác không?

Các kiểm tra này không cùng một nghĩa, nên cũng không nên có cùng một phản hồi khi thất bại.

| Kết quả quan sát | Ý nghĩa | Hành vi an toàn thường phù hợp |
| --- | --- | --- |
| **Được phép (PERMIT)** | Có bằng chứng hợp lệ đáp ứng chính sách ở thời điểm đánh giá. | Tiếp tục thao tác trong phạm vi được cấp. |
| **Bị từ chối (DENY)** | Đánh giá thành công nhưng chính sách không cho phép. | Không thực hiện thao tác được bảo vệ; phản hồi theo hợp đồng quyền. |
| **Không xác định (INDETERMINATE)** | Chưa đủ bằng chứng đáng tin cậy để quyết định cho phép hay từ chối. | Không thực hiện thao tác được bảo vệ; báo trạng thái chưa xác minh được. |
| **Yêu cầu không hợp lệ** | Không thể đánh giá đúng vì dữ liệu đầu vào sai hợp đồng. | Từ chối đầu vào; không gây tác dụng phụ. |
| **Lỗi lập trình/vi phạm hợp đồng nội bộ** | Kiểm tra trả null ngoài hợp đồng, ném lỗi không dự kiến hoặc dữ liệu chính sách bất nhất. | Không mặc định cho phép; ghi nhận và xử lý sự cố. |

Điểm cốt lõi: **DENY và INDETERMINATE đều không cấp quyền**, nhưng chúng **không có cùng nguyên nhân**. Gộp cả hai thành “người dùng không có quyền” có thể che giấu sự cố hạ tầng; gộp cả hai thành “lỗi server” làm phát sinh cảnh báo không cần thiết cho những lượt từ chối bình thường.

## 2. Hợp đồng phải nói rõ điều gì?

Một hợp đồng kiểm tra an toàn tốt cần xác định tối thiểu:

1. **Đầu vào đáng tin cậy:** Danh tính và quyền hạn được lấy từ đâu? Có tin dữ liệu do client tự khai hay không?
2. **Đối tượng được bảo vệ:** Tài nguyên, hành động, tenant hoặc phạm vi truy cập nào đang được đánh giá?
3. **Bằng chứng cho phép:** Điều kiện nào phải đúng mới trả PERMIT?
4. **Bằng chứng từ chối:** Trạng thái nào dẫn tới DENY?
5. **Trường hợp không xác định:** Timeout, thiếu chính sách, cache cũ hoặc lỗi phụ thuộc được biểu diễn thế nào?
6. **Tác động của quyết định:** PERMIT cho phép thao tác nào, trong thời gian và phạm vi nào?
7. **Đường thất bại:** Điều gì phải **không xảy ra** khi kiểm tra chưa xác nhận được quyền?
8. **Quan sát và phản hồi:** API trả mã gì; log và metric cần ghi gì mà không làm lộ dữ liệu nhạy cảm?

Ví dụ hợp đồng kiểm tra quyền đọc tài liệu:

> Để đọc nội dung tài liệu, hệ thống phải nhận được quyết định **PERMIT** từ chính sách truy cập đáng tin cậy cho đúng **actorId, documentId và phạm vi tenant**. Nếu quyết định là DENY, không trả nội dung. Nếu kết quả chưa xác định, không trả nội dung và báo lỗi kiểm tra quyền chưa sẵn sàng. Mọi trường hợp thiếu đầu vào bắt buộc phải dừng trước khi đọc tài liệu.

Đây là **hợp đồng của ca sử dụng giả định**. Mô hình bảo mật thật có thể có thêm quy tắc chia sẻ, phân cấp quyền, hiệu lực quyền theo thời gian hoặc kiểm soát theo thuộc tính.

## 3. Fail-closed, fail-open và sự đánh đổi

**Fail-closed (mặc định không cho phép khi không xác minh được)** là nguyên tắc thường dùng ở các thao tác có rủi ro bảo mật cao: nếu không có bằng chứng hợp lệ để cho phép, hệ thống **không tiến hành hành động được bảo vệ**.

**Fail-open (vẫn cho phép khi cơ chế kiểm tra gặp lỗi)** nghĩa là hệ thống cho phép hành động trong một số tình huống chưa có kết quả kiểm tra xác nhận. Điều này có thể tăng khả năng sẵn sàng, nhưng đồng thời có thể tạo lỗ hổng nếu được áp dụng không đúng ngữ cảnh.

| Tình huống | Cách xử lý nên cân nhắc | Vì sao |
| --- | --- | --- |
| Đọc hồ sơ riêng tư, không xác định được quyền | **Không trả nội dung**; báo chưa thể xác minh quyền. | Tránh tiết lộ thông tin không được phép. |
| Chuyển tiền, không xác nhận được hạn mức | **Không thực hiện lệnh chuyển mới** cho đến khi có bằng chứng phù hợp. | Hạn chế tác dụng phụ không thể hoàn tác dễ dàng. |
| Gửi email marketing, bộ chọn cá nhân hóa lỗi | Có thể **bỏ cá nhân hóa** nếu chính sách cho phép và vẫn có quyền gửi. | Giảm chức năng không thiết yếu mà vẫn giữ yêu cầu bảo mật. |
| Hiển thị trang nội dung công khai, thành phần gợi ý lỗi | Có thể hiển thị nội dung công khai mà không có gợi ý. | Nội dung không cần quyền riêng và phương án thay thế đã được phép. |
| Kiểm tra giới hạn lạm dụng không sẵn sàng | Cần chính sách rõ theo rủi ro, có thể thắt chặt hoặc hạn chế tải. | Không nên tự mặc định vô hiệu hóa kiểm soát. |

**Fail-closed không đồng nghĩa mọi lỗi đều phải trả 403.** Nếu hệ thống chưa thể đánh giá quyền vì lỗi phụ thuộc, nó vẫn phải chặn hành động, nhưng phản hồi bên ngoài có thể là **503 Service Unavailable**, không phải khẳng định người dùng chắc chắn bị cấm.

Cũng không nên biến fail-closed thành “mất khả năng truy cập vĩnh viễn”. Hệ thống cần khả năng phục hồi, giới hạn lỗi, giám sát và cách thử lại an toàn khi điều kiện đã được khôi phục.

## 4. Một lỗi nguy hiểm: bắt mọi ngoại lệ rồi mặc định cho phép

Đoạn mã sau vi phạm nguyên tắc bảo vệ khi kiểm tra quyền gặp lỗi:

~~~java
boolean canReadDocument(String actorId, long documentId) {
    try {
        return authorizationService.isAllowed(actorId, documentId);
    } catch (RuntimeException failure) {
        // SAI: chỉ vì hệ thống kiểm tra quyền lỗi mà cho phép đọc.
        return true;
    }
}
~~~

Nếu dịch vụ phân quyền timeout hoặc ném ngoại lệ, phương thức trả true. Trong tình huống xấu, sự cố hạ tầng tạo ra **cửa sổ truy cập trái phép**.

Một cách viết khác nhìn có vẻ an toàn hơn nhưng vẫn có vấn đề:

~~~java
boolean canReadDocument(String actorId, long documentId) {
    try {
        return authorizationService.isAllowed(actorId, documentId);
    } catch (RuntimeException failure) {
        return false;
    }
}
~~~

Cách này không cho phép truy cập khi lỗi, nhưng **che mất nguyên nhân**: false có thể nghĩa là chính sách từ chối hoặc chưa thể kiểm tra vì dịch vụ hỏng. Nếu tầng API luôn trả 403, đội vận hành có thể không nhận ra lỗi phụ thuộc; client cũng không biết lúc nào nên thử lại.

Cần tách **quyết định chính sách** khỏi **khả năng thu được quyết định**.

## 5. Biểu diễn ba trạng thái quyết định một cách tường minh

Khi một kiểm tra có thể trả về ba nhóm kết quả, một boolean đôi khi quá nghèo thông tin.

~~~java
enum AccessDecision {
    PERMIT,
    DENY,
    INDETERMINATE
}
~~~

Ý nghĩa trong hợp đồng:

- **PERMIT:** chính sách đã xác nhận được quyền cho đúng yêu cầu.
- **DENY:** chính sách đã đánh giá và từ chối.
- **INDETERMINATE:** không có quyết định đáng tin cậy; không được suy ra PERMIT.
 
Ngoài enum, lỗi giao tiếp với nhà cung cấp chính sách có thể được biểu diễn bằng **ngoại lệ có kiểu riêng** hoặc một kiểu kết quả chứa nguyên nhân. Thiết kế nào được chọn cũng cần bảo đảm không nhầm **lỗi mạng** với **quyết định từ chối**.

Sơ đồ luồng quyết định:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đọc tài liệu"] --> B{"Đầu vào và ngữ cảnh xác thực hợp lệ?"}
    B -- "Không" --> C["Dừng trước khi truy cập tài liệu"]
    B -- "Có" --> D["Đánh giá quyền cho actor + resource + tenant"]
    D --> E{"Có quyết định đáng tin cậy?"}
    E -- "Không" --> F["INDETERMINATE: chặn đọc, báo sự cố"]
    E -- "Có" --> G{"PERMIT?"}
    G -- "Không" --> H["DENY: chặn đọc"]
    G -- "Có" --> I["Đọc tài liệu trong phạm vi quyền"]
    I --> J["Trả nội dung được phép"]
~~~

**Không có đường đi** từ DENY hoặc INDETERMINATE tới bước đọc tài liệu. Đây là một tính chất có thể viết thành assertion trong kiểm thử.

## 6. Ví dụ Java 17: kiểm tra quyền trước khi đọc dữ liệu

Ví dụ dưới đây tập trung vào **hợp đồng kiểm soát truy cập**, không phụ thuộc framework HTTP. Để chạy trong dự án thật, dịch vụ phải nhận **actorId từ ngữ cảnh xác thực đã được máy chủ kiểm chứng**, không lấy trực tiếp từ trường tùy ý do client gửi.

~~~java
import java.util.Objects;

public final class SecureDocumentService {
    public enum Decision {
        PERMIT,
        DENY,
        INDETERMINATE
    }

    @FunctionalInterface
    public interface AccessPolicy {
        Decision evaluate(String actorId, long documentId);
    }

    @FunctionalInterface
    public interface DocumentReader {
        String readBody(long documentId);
    }

    public static class PolicyProviderUnavailableException
            extends RuntimeException {
        public PolicyProviderUnavailableException(String message) {
            super(message);
        }
    }

    public static class InvalidRequestException extends RuntimeException {
        public InvalidRequestException(String message) {
            super(message);
        }
    }

    public static class AccessDeniedException extends RuntimeException {
        public AccessDeniedException() {
            super("Access denied");
        }
    }

    public static class AccessIndeterminateException extends RuntimeException {
        public AccessIndeterminateException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final AccessPolicy policy;
    private final DocumentReader documents;

    public SecureDocumentService(
            AccessPolicy policy, DocumentReader documents) {
        this.policy = Objects.requireNonNull(policy);
        this.documents = Objects.requireNonNull(documents);
    }

    public String read(String actorId, long documentId) {
        if (actorId == null || actorId.isBlank() || documentId <= 0) {
            throw new InvalidRequestException("Invalid document request");
        }

        Decision decision;
        try {
            decision = policy.evaluate(actorId, documentId);
        } catch (PolicyProviderUnavailableException cause) {
            throw new AccessIndeterminateException(
                    "Authorization check unavailable", cause);
        }

        // Không coi kết quả null hoặc chưa xác định là được phép.
        if (decision == null || decision == Decision.INDETERMINATE) {
            throw new AccessIndeterminateException(
                    "Authorization not established", null);
        }

        if (decision == Decision.DENY) {
            throw new AccessDeniedException();
        }

        // Chỉ PERMIT mới được tới điểm đọc dữ liệu.
        return documents.readBody(documentId);
    }
}
~~~

### Hợp đồng của các thành phần

**AccessPolicy** phải thực thi chính sách cho đúng người gọi và đúng tài nguyên. Nó trả một trong ba giá trị Decision; nếu không giao tiếp được với nhà cung cấp chính sách, nó có thể ném PolicyProviderUnavailableException. Đoạn ví dụ coi **null là vi phạm hợp đồng** và xử lý theo hướng không cấp quyền.

**DocumentReader** là ranh giới truy xuất dữ liệu. Nó chỉ được gọi **sau khi có PERMIT**. Trong hệ thống thật, nó còn phải tuân thủ tenant isolation và chính sách lọc dữ liệu; tránh để thông tin tài nguyên bị lộ qua truy vấn không phù hợp.

**SecureDocumentService** không tự định nghĩa mọi quy tắc phân quyền. Nó đảm bảo điều kiện quan trọng của luồng gọi: **không có PERMIT thì không đọc tài liệu**.

### Vì sao không bắt mọi RuntimeException?

Khối catch chỉ xử lý **PolicyProviderUnavailableException** được xác định trong hợp đồng. Nếu AccessPolicy ném một NullPointerException do lỗi lập trình, nó không bị âm thầm chuyển thành “người dùng không có quyền”. Lỗi vẫn làm lời gọi thất bại trước bước đọc và có thể được xử lý ở tầng biên bằng phản hồi lỗi hệ thống.

Dịch vụ trong ví dụ chưa ghi log để tránh ràng buộc vào logging framework. Trong sản phẩm thật, log phải chứa **loại lỗi, request ID và vị trí phụ thuộc**, nhưng không đưa stack trace hoặc thông tin tài liệu bí mật vào phản hồi công khai.

## 7. Kiểm thử không chỉ xem exception mà còn xem tác dụng phụ

Mục tiêu quan trọng nhất của các ca từ chối là **DocumentReader không được gọi**. Nếu kiểm thử chỉ xác nhận ném AccessDeniedException mà không kiểm tra lời gọi đọc, một bản triển khai sai vẫn có thể đọc dữ liệu rồi mới ném ngoại lệ.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class SecureDocumentServiceTest {
    @Test
    void permitAllowsExactlyOneRead() {
        AtomicInteger reads = new AtomicInteger();
        var service = new SecureDocumentService(
                (actorId, documentId) -> SecureDocumentService.Decision.PERMIT,
                documentId -> {
                    reads.incrementAndGet();
                    return "authorized content";
                });

        assertEquals("authorized content", service.read("user-7", 42L));
        assertEquals(1, reads.get());
    }

    @Test
    void denyNeverReadsDocument() {
        AtomicInteger reads = new AtomicInteger();
        var service = new SecureDocumentService(
                (actorId, documentId) -> SecureDocumentService.Decision.DENY,
                documentId -> {
                    reads.incrementAndGet();
                    return "secret";
                });

        assertThrows(SecureDocumentService.AccessDeniedException.class,
                () -> service.read("user-7", 42L));
        assertEquals(0, reads.get());
    }

    @Test
    void indeterminateNeverReadsDocument() {
        AtomicInteger reads = new AtomicInteger();
        var service = new SecureDocumentService(
                (actorId, documentId) ->
                        SecureDocumentService.Decision.INDETERMINATE,
                documentId -> {
                    reads.incrementAndGet();
                    return "secret";
                });

        assertThrows(
                SecureDocumentService.AccessIndeterminateException.class,
                () -> service.read("user-7", 42L));
        assertEquals(0, reads.get());
    }

    @Test
    void missingPolicyResultNeverGrantsAccess() {
        var service = new SecureDocumentService(
                (actorId, documentId) -> null,
                documentId -> {
                    fail("Reader must not be called");
                    return "secret";
                });

        assertThrows(
                SecureDocumentService.AccessIndeterminateException.class,
                () -> service.read("user-7", 42L));
    }

    @Test
    void providerFailureIsNotMistakenForDeny() {
        var service = new SecureDocumentService(
                (actorId, documentId) -> {
                    throw new SecureDocumentService
                            .PolicyProviderUnavailableException("timeout");
                },
                documentId -> {
                    fail("Reader must not be called");
                    return "secret";
                });

        var error = assertThrows(
                SecureDocumentService.AccessIndeterminateException.class,
                () -> service.read("user-7", 42L));

        assertInstanceOf(
                SecureDocumentService.PolicyProviderUnavailableException.class,
                error.getCause());
    }

    @Test
    void invalidInputStopsBeforePolicyEvaluation() {
        var service = new SecureDocumentService(
                (actorId, documentId) -> {
                    fail("Policy must not be called");
                    return SecureDocumentService.Decision.PERMIT;
                },
                documentId -> {
                    fail("Reader must not be called");
                    return "secret";
                });

        assertThrows(SecureDocumentService.InvalidRequestException.class,
                () -> service.read("", 42L));
    }
}
~~~

Các ca trên minh họa **đường cho phép, từ chối, không xác định, trả null ngoài hợp đồng, lỗi phụ thuộc và đầu vào không hợp lệ**. Chúng chứng minh thuộc tính của **luồng service trong ví dụ**, chưa phải bằng chứng đầy đủ về phân quyền ngoài thực tế. Cần kiểm thử chính sách với dữ liệu quyền thật, cấu hình xác thực, tenant isolation và cách ánh xạ lỗi HTTP trong môi trường tích hợp.

### Ma trận kiểm thử bổ sung

| Tình huống | Kết quả kỳ vọng | Điều phải không xảy ra |
| --- | --- | --- |
| Actor không có quyền | DENY, không trả nội dung. | Không đọc hoặc tiết lộ tài liệu. |
| Actor có quyền trên tài liệu khác | DENY cho tài liệu hiện tại. | Không dùng quyết định quyền của tài liệu khác. |
| Provider timeout | INDETERMINATE/lỗi phụ thuộc. | Không tự PERMIT hoặc trả nội dung. |
| Provider trả null ngoài hợp đồng | Thất bại an toàn và ghi nhận sự cố. | Không coi null là mặc định cho phép. |
| Tenant khác | Từ chối theo chính sách. | Không đọc dữ liệu xuyên tenant. |
| Token hết hạn hoặc chữ ký không hợp lệ | Không chấp nhận danh tính. | Không thực hiện hành động được bảo vệ. |
| Tài liệu bị đổi chủ trong lúc xử lý | Áp dụng cơ chế nhất quán phù hợp. | Không dùng quyền cũ để tiết lộ trái chính sách. |
| Yêu cầu thiếu định danh | Từ chối đầu vào. | Không truy cập dữ liệu hoặc gọi phụ thuộc không cần thiết. |

## 8. Phản hồi API: từ chối quyền khác với lỗi kiểm tra quyền

Trong HTTP API, nên phân biệt **quyết định chính sách** với **lỗi không thể đánh giá chính sách**:

| Trường hợp | HTTP status thường phù hợp | Nội dung công khai |
| --- | --- | --- |
| Thiếu token hoặc token xác thực không hợp lệ | **401 Unauthorized** | Yêu cầu xác thực theo hợp đồng; tránh nêu thông tin nhạy cảm. |
| Danh tính đã xác thực nhưng không đủ quyền | **403 Forbidden** | Thông báo không được phép, theo chính sách hiển thị. |
| Cần tránh tiết lộ tài nguyên có tồn tại hay không | **404 Not Found** có thể phù hợp | Không khẳng định quyền hoặc sự tồn tại của tài nguyên với người không được biết. |
| Request thiếu/sai định danh bắt buộc | **400 Bad Request** | Chỉ ra dữ liệu cần sửa khi an toàn. |
| Nhà cung cấp phân quyền không khả dụng | **503 Service Unavailable** thường phù hợp | Tạm thời không thể kiểm tra quyền; request ID; không nêu cấu trúc hệ thống. |
| Lỗi lập trình không dự kiến | **500 Internal Server Error** | Thông báo chung và khả năng tra cứu qua request ID. |

Đây là **gợi ý ánh xạ**, không phải quy định duy nhất cho mọi giao thức. Một policy engine có thể được triển khai cùng tiến trình, qua mạng hoặc qua cơ chế khác; mã lỗi phải phù hợp với hợp đồng API thực tế.

Ví dụ phản hồi khi chưa thể xác minh quyền:

~~~json
{
  "code": "AUTHORIZATION_UNAVAILABLE",
  "message": "Chưa thể xác minh quyền truy cập. Vui lòng thử lại sau.",
  "requestId": "req-2a9c"
}
~~~

Ví dụ phản hồi cho người không đủ quyền:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không được phép thực hiện thao tác này.",
  "requestId": "req-2a9c"
}
~~~

Không trả cho client dữ liệu như **câu truy vấn nội bộ, cấu trúc tài nguyên, stack trace, khóa API, điều kiện quyền chi tiết của người khác hoặc danh tính chủ tài liệu**. Đôi khi ngay cả việc phân biệt “tài liệu không tồn tại” và “tài liệu thuộc người khác” cũng làm rò rỉ thông tin. Cần thiết kế phản hồi theo **chính sách tiết lộ thông tin**.

## 9. Không tin vào giá trị do client tự khai

Một lớp bảo vệ có thể được viết đúng về mặt điều kiện nhưng vẫn sai vì **nguồn dữ liệu được tin tưởng**.

Ví dụ không an toàn:

~~~java
// SAI: actorId được lấy từ request body do client toàn quyền sửa.
String actorId = request.actorId();
return secureDocumentService.read(actorId, request.documentId());
~~~

Nếu client tự gửi actorId của một người khác, mọi quy tắc kiểm tra quyền dựa trên ID đó có thể bị áp dụng sai.

Cách tổ chức phù hợp hơn:

~~~java
// Ví dụ cấu trúc: principalId đến từ thành phần xác thực server.
String actorId = authenticatedPrincipal.getId();
long documentId = request.documentId();

return secureDocumentService.read(actorId, documentId);
~~~

Các kiểu **request** và **authenticatedPrincipal** là thành phần giả định, chỉ minh họa **nguồn gốc tin cậy**. Hệ thống thật phải kiểm tra chữ ký hoặc phiên xác thực, thời hạn, đối tượng phát hành, phạm vi/claim cần thiết và cơ chế thu hồi theo mô hình xác thực đang dùng.

Quy tắc bảo mật phải gắn với **ngữ cảnh chính xác**: danh tính, tài nguyên, tenant, hành động và điều kiện liên quan. Chỉ xác minh “người này đã đăng nhập” không chứng minh họ có quyền đọc bất kỳ tài liệu nào.

## 10. Cẩn trọng với cache, fallback và quyết định quyền cũ

Để tăng tốc, hệ thống có thể cache quyết định phân quyền. Nhưng **cache cũ có thể khiến quyền đã bị thu hồi vẫn được sử dụng** nếu thời hạn, khóa cache hoặc quy tắc vô hiệu hóa không phù hợp.

Một quyết định cache tối thiểu cần liên hệ với đúng:

- **Danh tính** đã được xác thực.
- **Tài nguyên** đang được truy cập.
- **Hành động** cần thực hiện (đọc, sửa, xóa, chuyển tiền...).
- **Tenant/phạm vi** áp dụng.
- **Phiên bản chính sách** hoặc thời gian hiệu lực nếu mô hình đòi hỏi.

Nếu khóa cache chỉ dựa trên actorId, một kết quả PERMIT cho tài liệu A có thể bị tái sử dụng sai với tài liệu B.

Khi chính sách từ xa không khả dụng, không nên âm thầm sử dụng một PERMIT cũ **chỉ vì nó có sẵn**. Có những hệ thống cho phép kiểm tra bằng dữ liệu cục bộ hoặc cache được xác thực còn hiệu lực; đó phải là **chiến lược được thiết kế và giới hạn rõ**. Khi không có bằng chứng đáp ứng hợp đồng, thao tác được bảo vệ phải dừng.

**Fallback an toàn** không nhất thiết là mở quyền. Ví dụ, nếu không xác minh được quyền xem số dư, UI có thể hiển thị “Chưa thể tải số dư” thay vì hiển thị dữ liệu nhạy cảm từ một nguồn không được phép.

## 11. Kiểm tra an toàn và lỗi giữa các bước: TOCTOU

**Time-of-check to time-of-use (TOCTOU)** là vấn đề khi điều kiện đã được kiểm tra nhưng **trạng thái thay đổi trước khi hành động được thực hiện**.

Ví dụ:

~~~text
1. Kiểm tra user A có quyền sửa tài liệu X -> PERMIT.
2. Chính sách chia sẻ của tài liệu X bị thay đổi; user A mất quyền.
3. Yêu cầu cũ vẫn tiếp tục ghi dữ liệu vào X.
~~~

Một check đúng ở bước 1 chưa đủ chứng minh bước 3 hợp lệ theo hợp đồng nếu quyền có thể thay đổi giữa hai bước và hệ thống yêu cầu quyết định có hiệu lực đến lúc cập nhật.

Các biện pháp cần xem xét theo hệ thống:

- **Gắn quyết định với tài nguyên và phiên bản trạng thái** phù hợp.
- **Kiểm tra và ghi trong cùng ranh giới nhất quán** khi cơ sở dữ liệu hỗ trợ.
- **Thực thi điều kiện quyền ngay tại thao tác cập nhật** thay vì chỉ dựa vào kiểm tra từ trước.
- **Dùng optimistic locking/version** nếu yêu cầu phụ thuộc trạng thái vừa đọc.
- **Giới hạn tuổi của bằng chứng quyền** nếu phải sử dụng token hoặc cache.

Không phải mọi thay đổi quyền đều cần transaction phân tán; phải chọn cơ chế theo mô hình nhất quán và rủi ro thật. Điều quan trọng là không hiểu “đã check một lần” thành “an toàn trong mọi thời điểm tiếp theo”.

## 12. Phân biệt lỗi đầu vào, nghiệp vụ, hạ tầng và lỗi bảo mật

Có những tình huống cùng trả về “không thực hiện được”, nhưng cách khắc phục rất khác:

| Tình huống | Nhóm nguyên nhân | Cách phản hồi |
| --- | --- | --- |
| documentId là 0 hoặc âm | Sai hợp đồng đầu vào. | Báo dữ liệu không hợp lệ. |
| Người dùng không có quyền trên tài liệu | Quyết định bảo mật DENY. | Chặn truy cập, phản hồi theo chính sách. |
| Quyền không xác minh được vì policy service timeout | Lỗi phụ thuộc, quyết định INDETERMINATE. | Chặn truy cập và báo sự cố kiểm tra quyền. |
| Đơn đã hủy nên không thể giao hàng | Từ chối nghiệp vụ. | Không biến thành lỗi phân quyền. |
| CSDL không đọc được nội dung tài liệu sau PERMIT | Lỗi truy xuất dữ liệu. | Không trả dữ liệu giả; phản hồi lỗi hệ thống phù hợp. |
| Policy component ném exception lập trình không dự kiến | Lỗi nội bộ cần điều tra. | Không tiếp tục như có PERMIT, ghi nhận lỗi. |

Một nguyên tắc hữu ích: **chính sách quyết định ai được phép làm gì; hạ tầng quyết định hệ thống có thực thi và xác minh được hay không**. Đừng để timeout trở thành PERMIT, cũng đừng che timeout thành DENY rồi mất khả năng giám sát.

## 13. Ghi log và giám sát mà không làm lộ dữ liệu

Khả năng quan sát giúp trả lời **lỗi do chính sách, do phụ thuộc hay do dữ liệu**. Tuy nhiên, log bảo mật cũng phải được bảo vệ khỏi lộ dữ liệu.

Những tín hiệu cần tách riêng:

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Số lượt PERMIT/DENY theo luồng và hành động | Theo dõi xu hướng sử dụng và phát hiện bất thường, không mặc nhiên coi DENY là lỗi máy chủ. |
| Tỷ lệ INDETERMINATE hoặc timeout của policy | Cho biết khả năng kiểm tra quyền đang suy giảm. |
| Số lỗi hợp đồng của policy (null, trạng thái không hợp lệ) | Có thể cho thấy lỗi tích hợp hoặc lập trình. |
| Số yêu cầu bị chặn trước khi gọi phụ thuộc | Hỗ trợ chứng minh guard hoạt động đúng. |
| Số thay đổi cấu hình/chính sách | Hỗ trợ điều tra nguyên nhân khi hành vi quyền thay đổi. |

Ví dụ log nội bộ có cấu trúc:

~~~text
level=ERROR
event=authorization_evaluation_unavailable
requestId=req-2a9c
action=READ_DOCUMENT
dependency=access-policy
decision=INDETERMINATE
elapsedMs=1200
~~~

Không ghi token, secret, nội dung tài liệu, thông tin cá nhân không cần thiết hoặc toàn bộ payload vào log. Nếu cần phân tích theo chủ thể, sử dụng định danh theo chính sách logging và retention, tránh đặt thông tin nhạy cảm vào nhãn metric có cardinality lớn.

Đối với phản hồi bên ngoài, chỉ cung cấp **mã lỗi ổn định, thông báo an toàn và request ID**. Thông tin chi tiết để điều tra được lưu trong hệ thống quan sát có kiểm soát truy cập.

## 14. Khả năng sẵn sàng và bảo mật cần được thiết kế cùng nhau

Fail-closed bảo vệ tài nguyên khi không có bằng chứng, nhưng một policy service không ổn định có thể làm giảm tính sẵn sàng. Để tránh lựa chọn giữa “an toàn nhưng thường xuyên lỗi” và “hoạt động nhưng mất kiểm soát”, có thể:

1. **Giảm phụ thuộc không cần thiết** trong đường kiểm tra quyền, nhưng không bỏ các điều kiện bắt buộc.
2. **Thiết kế timeout và deadline** phù hợp với thời gian phản hồi API.
3. **Dùng cơ chế phục hồi an toàn**, như retry giới hạn cho phép kiểm tra chỉ đọc, circuit breaker và giám sát phụ thuộc.
4. **Cân nhắc bằng chứng quyền cục bộ đã được xác minh** khi hợp đồng cho phép, có hiệu lực và khả năng thu hồi rõ.
5. **Tách chức năng công khai khỏi thao tác nhạy cảm** để một sự cố phân quyền không nhất thiết làm toàn bộ trang công khai ngừng hoạt động.
6. **Chuẩn bị quy trình sự cố**: cách xác định policy outage, khôi phục, đánh giá lượt truy cập thất bại và xử lý cảnh báo.

Việc retry kiểm tra quyền có thể phù hợp hơn retry **thao tác có tác dụng phụ**. Ví dụ nếu lỗi xảy ra sau khi một lệnh chuyển tiền đã được gửi đi, timeout không cho biết giao dịch có thực hiện hay chưa. Cần thiết kế đối soát và idempotency riêng; không suy ra “chưa chuyển” chỉ từ việc thiếu phản hồi.

## 15. Những anti-pattern cần nhận diện

| Anti-pattern | Vì sao nguy hiểm | Hướng cải thiện |
| --- | --- | --- |
| **catch(Exception) → return true** | Lỗi kiểm tra quyền biến thành cho phép truy cập. | Chỉ PERMIT đáng tin cậy mới cấp quyền. |
| **catch(Exception) → return false** cho mọi tình huống | Trộn DENY với outage, làm mờ nguyên nhân. | Tách quyết định và lỗi đánh giá; giữ nguyên nhân. |
| **null được hiểu là PERMIT mặc định** | Vi phạm hợp đồng không gây dừng an toàn. | Xem null là INDETERMINATE hoặc lỗi nội bộ. |
| **Dùng actorId từ body** | Client có thể mạo danh bằng cách thay trường tự khai. | Lấy danh tính từ cơ chế xác thực của server. |
| **Kiểm tra role chung, không kiểm tra object** | Người có vai trò đọc tài liệu có thể đọc tài liệu của tenant khác. | Ràng buộc quyền vào đúng tài nguyên/hành động/phạm vi. |
| **Dùng PERMIT cache không xét hiệu lực** | Quyền cũ có thể tiếp tục được dùng sau thu hồi. | Thiết kế khóa, TTL, phiên bản và invalidation phù hợp. |
| **Kiểm tra sau khi đọc/ghi nhạy cảm** | Tác dụng phụ đã xảy ra trước khi từ chối. | Chặn tại ranh giới cần thiết; bảo vệ TOCTOU. |
| **Trả lỗi chi tiết nội bộ cho client** | Có thể làm lộ cấu trúc quyền hoặc dữ liệu tài nguyên. | Tách lỗi công khai và log nội bộ. |

Không áp dụng các quy tắc này một cách máy móc cho mọi tính năng. Ví dụ nội dung hoàn toàn công khai không cần được “phân quyền” bằng một dịch vụ trung tâm. Nhưng nếu **hợp đồng nói cần kiểm tra quyền**, việc bỏ qua kiểm tra khi lỗi phải được xem là **thay đổi chính sách bảo mật**, không phải mẹo cải thiện trải nghiệm.

## 16. Quy trình review một luồng kiểm tra an toàn

Khi review mã truy cập dữ liệu hoặc thực hiện thao tác nhạy cảm, có thể đi theo trình tự:

1. **Xác định tài nguyên và hành động.** Đang bảo vệ đọc, sửa, xóa, xuất dữ liệu hay giao dịch nào?
2. **Viết hợp đồng PERMIT.** Điều kiện nào phải được chứng minh trước khi cho phép?
3. **Tách DENY với INDETERMINATE.** Đường lỗi phụ thuộc có được biểu diễn riêng không?
4. **Kiểm tra nguồn tin cậy.** Danh tính, quyền, tenant, phiên bản tài nguyên đến từ đâu?
5. **Theo dõi điểm có tác dụng phụ.** Đọc dữ liệu, ghi CSDL, gửi sự kiện hoặc gọi thanh toán ở bước nào?
6. **Chứng minh đường thất bại không chạm điểm bảo vệ.** Test DENY, timeout, null, exception và đầu vào sai; assert cả **không gọi dependency**.
7. **Xem tính nhất quán theo thời gian.** Quyền có thể thay đổi giữa check và use không?
8. **Đánh giá phản hồi/log.** Mã lỗi đủ rõ cho client/ops mà không tiết lộ thông tin nhạy cảm không?
9. **Kiểm chứng tích hợp.** Với framework thật, cấu hình xác thực, policy và interceptor có hoạt động ở đúng ranh giới không?

Một câu hỏi mạnh trong review: **“Nếu thành phần kiểm tra quyền bị tắt ngay lúc này, dữ liệu hoặc hành động được bảo vệ có còn có đường đi nào tới người dùng không?”**. Nếu có, phải hiểu rõ liệu đó là **đường đi công khai có chủ đích** hay một đường bỏ qua kiểm soát.

## 17. Bài tập tự kiểm tra

### Tình huống A — Provider timeout

Một API hồ sơ sức khỏe gọi policy service. Nếu sau 1 giây chưa nhận được câu trả lời, phương thức kiểm tra quyền trả true để người dùng không phải chờ.

**Câu hỏi:** Lỗi nằm ở đâu?

**Gợi ý:** Timeout không cung cấp bằng chứng được phép. Với dữ liệu riêng tư, không nên trả nội dung khi không có PERMIT. Phải giữ riêng tín hiệu lỗi phụ thuộc và có thông báo tạm thời phù hợp.

### Tình huống B — DENY và outage cùng trả 403

Một service trả false khi người dùng không đủ quyền, đồng thời cũng trả false khi policy service bị lỗi. Controller chuyển mọi false thành 403.

**Câu hỏi:** Về mặt bảo vệ dữ liệu có thể chưa bị mở quyền, nhưng vấn đề chất lượng nào còn tồn tại?

**Gợi ý:** Nguyên nhân từ chối và lỗi khả dụng bị trộn, khó giám sát và có thể dẫn phía gọi tới hành động không phù hợp. Cần phản hồi nội bộ phân biệt hai loại, đồng thời vẫn không cấp quyền.

### Tình huống C — Kết quả cache không đúng phạm vi

Hệ thống cache PERMIT bằng khóa chỉ gồm actorId. Người dùng có quyền trên tài liệu X và sau đó yêu cầu xem tài liệu Y.

**Câu hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** Quyết định quyền cho X bị dùng sai cho Y. Khóa và hiệu lực cache phải gắn với đầy đủ tài nguyên, hành động và ngữ cảnh liên quan.

### Tình huống D — Kiểm tra sau thao tác

Một API xuất dữ liệu người dùng gọi database để lấy toàn bộ bản ghi, rồi mới kiểm tra quyền và ném AccessDeniedException.

**Câu hỏi:** Việc ném ngoại lệ đã đủ chứng minh an toàn chưa?

**Gợi ý:** Chưa. Dữ liệu có thể đã đi qua log, bộ đệm, bộ nhớ dùng chung hoặc tác dụng phụ khác trước khi kiểm tra. Cần kiểm tra quyền tại ranh giới thích hợp và xác minh dữ liệu không được đọc hoặc tiết lộ trái phép.

### Tình huống E — Lỗi ngẫu nhiên ở policy

Một test chỉ assertThrows(AccessDeniedException.class) khi policy trả DENY. Không có test timeout và không kiểm tra DocumentReader có được gọi hay không.

**Câu hỏi:** Nên bổ sung loại bằng chứng nào?

**Gợi ý:** Ca INDETERMINATE, null ngoài hợp đồng, lỗi provider, đầu vào sai; kết quả mong đợi là **không có đường đọc tài liệu**. Kiểm thử tích hợp cho xác thực và policy thật cũng cần được cân nhắc.

---

**Ghi nhớ:** Khi kiểm tra an toàn thất bại, **không có bằng chứng cho phép thì không được coi như đã được cấp quyền**. Hãy xác định hợp đồng rõ cho PERMIT, DENY và INDETERMINATE; chặn tác dụng phụ trước khi kiểm tra thành công; phân biệt lỗi hạ tầng với quyết định chính sách; và dùng kiểm thử để chứng minh **đường thất bại không thể vượt qua ranh giới bảo vệ**.
