# Giới hạn dùng ngăn xếp làm hợp đồng nghiệp vụ

StackWalker được bổ sung trong Java 9 để đọc các stack frame của thread hiện tại một cách có kiểm soát. API này hữu ích cho logging, tracing, chẩn đoán và công cụ hỗ trợ phát triển. Tuy nhiên, stack trace mô tả đường đi thực thi tại một thời điểm; nó không phải hợp đồng ổn định của ứng dụng.

Không nên dùng tên class, tên method, vị trí frame hoặc độ sâu stack để quyết định quyền truy cập, tenant, giá nghiệp vụ, luồng xử lý, danh tính người dùng hay kết quả API. Những quyết định đó cần dựa trên dữ liệu và chính sách được truyền tường minh.

## 1. StackWalker dùng để làm gì?

StackWalker cung cấp cách duyệt stack frame của thread đang gọi. Mỗi frame mô tả một method đang hoạt động và có thể cung cấp thông tin như:

- Tên class khai báo method.
- Tên method.
- Tên file nguồn nếu có.
- Số dòng nếu runtime có thông tin.
- Trạng thái native method.
- Class object nếu walker được tạo với tùy chọn giữ tham chiếu class.

Ví dụ khởi tạo walker mặc định:

~~~java
StackWalker walker = StackWalker.getInstance();
~~~

Duyệt một số frame để ghi log:

~~~java
walker.forEach(frame ->
        System.out.println(
                frame.getClassName() + "#" + frame.getMethodName()
        )
);
~~~

StackWalker chỉ quan sát stack của thread hiện tại tại thời điểm gọi. Nó không phải API để đọc stack của một thread khác hoặc để dựng lại toàn bộ lịch sử thực thi của ứng dụng.

## 2. Vì sao stack không phải hợp đồng nghiệp vụ?

Stack frame là chi tiết triển khai. Cấu trúc stack có thể thay đổi khi code được refactor, tách method, gộp helper, thêm proxy, đổi framework, chuyển qua lambda hoặc thay đổi cách gọi nội bộ.

Ví dụ, một API ban đầu được gọi trực tiếp:

~~~java
reportService.export(report);
~~~

Sau đó ứng dụng thêm lớp điều phối:

~~~java
requestFacade.export(report);
~~~

Nếu logic nghiệp vụ kiểm tra tên caller hoặc vị trí frame để quyết định ai được export, chỉ một thay đổi kiến trúc cũng có thể làm hành vi thay đổi ngoài ý muốn.

Các yếu tố khác cũng khiến stack không ổn định:

- Framework có thể thêm proxy, interceptor, dispatcher hoặc wrapper.
- Reflection và method handle có thể tạo frame được lọc hoặc hiển thị tùy cấu hình.
- Lambda và các class ẩn có thể làm tên class hoặc hình dạng stack khác với code nguồn.
- Refactor thay đổi số lớp gọi và độ sâu stack.
- Tối ưu hóa runtime có thể thay đổi cách thực thi method; không nên dựa vào một hình dạng stack cụ thể để định nghĩa nghiệp vụ.

StackWalker phù hợp để trả lời câu hỏi chẩn đoán như “đường gọi nào dẫn tới log này?”. Nó không phù hợp để trả lời câu hỏi nghiệp vụ như “người dùng này có quyền quản trị không?” hoặc “request thuộc tenant nào?”.

## 3. Những quyết định không được suy ra từ stack

Không dùng stack frame làm nguồn xác thực hoặc phân quyền:

~~~java
// Không dùng tên caller để cấp quyền.
if (StackWalker.getInstance().getCallerClass().getName()
        .contains("Admin")) {
    allowSensitiveOperation();
}
~~~

Tên class không chứng minh danh tính hoặc quyền của người gọi. Class có thể được đổi tên, gọi thông qua proxy hoặc được sử dụng từ một đường đi khác.

Không dùng stack để chọn tenant:

~~~java
// Không suy luận tenant từ package hoặc tên class trong stack.
String tenant = inferTenantFromCaller();
~~~

Tenant phải đến từ context đã được xác thực và kiểm tra theo hợp đồng của request.

Không dùng stack để xác định giá, trạng thái giao dịch, giới hạn quota hoặc loại API. Những dữ liệu đó cần nằm trong tham số, context nghiệp vụ hoặc policy service có kiểm soát.

Một nguyên tắc hữu ích: nếu một quyết định phải đúng sau khi đổi tên class, di chuyển method, thêm interceptor hoặc đổi framework, thì quyết định đó không nên phụ thuộc vào stack.

## 4. Truyền hợp đồng nghiệp vụ bằng dữ liệu tường minh

Thay vì suy luận vai trò từ caller, hãy truyền thông tin đã được xác thực vào service:

~~~java
static void requireRole(Set<String> authenticatedRoles,
                        String requiredRole) {
    if (!authenticatedRoles.contains(requiredRole)) {
        throw new SecurityException("Required role is missing");
    }
}
~~~

Trong ứng dụng thực tế, tập role phải đến từ principal hoặc security context đã được xác thực. Không nhận một chuỗi role tùy ý từ client rồi coi nó là bằng chứng quyền.

Tương tự, truyền tenant hoặc request context bằng một đối tượng có cấu trúc:

~~~java
final class RequestContext {
    private final String tenantId;
    private final Set<String> roles;

    RequestContext(String tenantId, Set<String> roles) {
        this.tenantId = tenantId;
        this.roles = roles;
    }

    String tenantId() {
        return tenantId;
    }

    Set<String> roles() {
        return roles;
    }
}
~~~

Service có thể xác thực context ở ranh giới tin cậy rồi dùng nó trong suốt nghiệp vụ. StackWalker vẫn có thể ghi lại caller để chẩn đoán, nhưng không tham gia vào quyết định cho phép hay từ chối thao tác.

## 5. Dùng getCallerClass đúng mục đích

StackWalker có phương thức getCallerClass để lấy class của caller theo ngữ nghĩa API. Để sử dụng class object, phải tạo walker với RETAIN_CLASS_REFERENCE:

~~~java
private static final StackWalker WALKER =
        StackWalker.getInstance(
                StackWalker.Option.RETAIN_CLASS_REFERENCE
        );

static Class<?> diagnosticCaller() {
    return WALKER.getCallerClass();
}
~~~

Nếu không bật RETAIN_CLASS_REFERENCE, việc lấy declaring class từ StackFrame hoặc gọi getCallerClass không được hỗ trợ và có thể ném UnsupportedOperationException.

Dùng kết quả cho thông tin chẩn đoán:

~~~java
Class<?> caller = diagnosticCaller();
logger.debug("Diagnostic caller: {}", caller.getName());
~~~

Không dùng caller class để cấp quyền hoặc suy luận vai trò. Caller thực tế có thể là adapter, proxy, framework hoặc helper; class đó không nhất thiết là người dùng hay thành phần nghiệp vụ mà bạn muốn nhận diện.

Nếu cần định danh một thành phần theo hợp đồng, hãy dùng interface, dependency injection, capability object hoặc một mã định danh được khai báo rõ ràng.

## 6. Tùy chọn hiển thị frame

StackWalker có các tùy chọn điều khiển loại frame được quan sát:

| Option | Ý nghĩa |
|---|---|
| RETAIN_CLASS_REFERENCE | Giữ tham chiếu Class để có thể lấy declaring class |
| SHOW_REFLECT_FRAMES | Hiển thị các frame liên quan reflection vốn được lọc mặc định |
| SHOW_HIDDEN_FRAMES | Hiển thị cả hidden frame vốn được lọc mặc định |

Mặc định, các frame reflection và hidden frame không được hiển thị. Điều này giúp stack dễ đọc hơn cho nhiều mục đích chẩn đoán.

Khi cần điều tra một đường gọi có reflection hoặc cơ chế runtime tạo class ẩn, có thể bật tùy chọn tương ứng:

~~~java
Set<StackWalker.Option> options =
        EnumSet.of(
                StackWalker.Option.RETAIN_CLASS_REFERENCE,
                StackWalker.Option.SHOW_REFLECT_FRAMES,
                StackWalker.Option.SHOW_HIDDEN_FRAMES
        );

StackWalker detailedWalker = StackWalker.getInstance(options);
~~~

Bật thêm frame có thể làm kết quả dài và phụ thuộc implementation hơn. Hãy chọn option theo mục đích quan sát; không dùng số lượng frame hoặc vị trí frame làm điều kiện nghiệp vụ.

## 7. walk và thời hạn sử dụng Stream

Phương thức walk nhận một Function thao tác trên Stream các StackFrame:

~~~java
<T> T walk(
        Function<? super Stream<StackFrame>, ? extends T> function
)
~~~

Stream chỉ hợp lệ trong khi function được truyền vào walk đang thực thi. Khi function trả về, stream được đóng và không được giữ lại để xử lý về sau.

Đúng:

~~~java
List<String> frames = walker.walk(stream ->
        stream.limit(10)
                .map(frame ->
                        frame.getClassName() + "#" + frame.getMethodName()
                )
                .collect(Collectors.toList())
);
~~~

Không đúng:

~~~java
Stream<StackWalker.StackFrame> saved =
        walker.walk(stream -> stream);
~~~

Không trả stream ra ngoài walk để dùng sau đó. Hãy chuyển thông tin cần thiết thành list, string hoặc đối tượng bất biến ngay trong callback.

Cũng nên giới hạn số frame cần thu thập. Ghi toàn bộ stack cho mọi request có thể tạo log lớn, tốn CPU và làm lộ tên class hoặc cấu trúc nội bộ không cần thiết.

## 8. forEach và giới hạn độ sâu

Nếu chỉ cần duyệt frame để ghi log, có thể dùng forEach:

~~~java
walker.forEach(frame -> {
    logger.debug(
            "{}#{} at {}",
            frame.getClassName(),
            frame.getMethodName(),
            frame.getLineNumber()
    );
});
~~~

Nếu cần biến đổi, lọc hoặc giới hạn số frame, walk thường thuận tiện hơn vì cho phép dùng Stream:

~~~java
List<String> callers = walker.walk(stream ->
        stream.skip(1)
                .limit(5)
                .map(StackWalker.StackFrame::getMethodName)
                .collect(Collectors.toList())
);
~~~

skip chỉ có ý nghĩa cho mục tiêu quan sát cụ thể. Đừng giả định frame ở vị trí 0 hoặc 1 luôn là một method nghiệp vụ cố định; thêm wrapper hoặc interceptor có thể làm vị trí thay đổi.

StackWalker cũng có overload getInstance nhận maxDepth. Giới hạn này hữu ích khi công cụ chỉ cần một số frame đầu tiên, nhưng nó làm dữ liệu quan sát bị cắt ngắn. Không diễn giải việc không thấy một frame ở phần stack bị giới hạn là bằng chứng method đó không tham gia đường gọi.

## 9. Thông tin frame không phải lúc nào cũng đầy đủ

StackFrame cung cấp tên file và số dòng khi runtime có thể xác định. Các thông tin này có thể không có, ví dụ khi class không có debug line information hoặc frame là native method.

Không giả định:

- File nguồn luôn tồn tại.
- Số dòng luôn dương.
- Tên method trong stack luôn là tên API công khai.
- Một frame tương ứng một ranh giới nghiệp vụ.
- Hai lần chạy cùng một request luôn có stack giống nhau.

Nếu cần correlation giữa log, trace và request, dùng trace ID hoặc request ID được tạo và truyền theo context. Không dùng hash của stack hoặc tên method làm correlation ID.

## 10. Ví dụ chạy được với Java 17+

Tạo file **StackWalkerContractDemo.java**:

~~~java
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class StackWalkerContractDemo {
    private static final StackWalker WALKER =
            StackWalker.getInstance(
                    StackWalker.Option.RETAIN_CLASS_REFERENCE
            );

    static String diagnosticCaller() {
        return WALKER.getCallerClass().getSimpleName();
    }

    static List<String> diagnosticFrames() {
        return WALKER.walk(frames -> frames
                .limit(4)
                .map(frame ->
                        frame.getClassName() + "#" + frame.getMethodName()
                )
                .collect(Collectors.toList()));
    }

    static void requireRole(Set<String> roles, String requiredRole) {
        if (!roles.contains(requiredRole)) {
            throw new SecurityException("Required role is missing");
        }
    }

    static class RequestService {
        static void handleRequest() {
            System.out.println("diagnostic caller: "
                    + StackWalkerContractDemo.diagnosticCaller());
            System.out.println("trace captured: "
                    + !StackWalkerContractDemo.diagnosticFrames().isEmpty());
        }
    }

    public static void main(String[] args) {
        RequestService.handleRequest();

        Set<String> authenticatedRoles =
                Collections.singleton("REPORT_VIEWER");
        requireRole(authenticatedRoles, "REPORT_VIEWER");
        System.out.println("authorization: explicit role");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StackWalkerContractDemo.java
java StackWalkerContractDemo
~~~

Kết quả stdout:

~~~text
diagnostic caller: RequestService
trace captured: true
authorization: explicit role
~~~

Ví dụ dùng StackWalker để ghi caller và xác nhận có thể thu thập stack frame. Quyết định role được thực hiện bằng tập role truyền tường minh. Trong ứng dụng thật, tập role đó phải lấy từ principal hoặc security context đã được xác thực.

## 11. Khi nào nên dùng StackWalker?

StackWalker phù hợp cho:

- Ghi log caller khi debug hoặc điều tra lỗi.
- Bổ sung thông tin stack có giới hạn vào diagnostic event.
- Công cụ quan sát, profiler hoặc framework cần hiểu đường gọi hiện tại.
- Phát hiện một số ngữ cảnh gọi phục vụ cảnh báo hoặc tương thích nội bộ, miễn là kết quả không trở thành hợp đồng bảo mật/nghiệp vụ.
- Kiểm thử cấu trúc gọi trong một test chuyên biệt, khi test đó chủ đích kiểm tra implementation detail.

Không phù hợp cho:

- Xác thực danh tính người dùng.
- Phân quyền hoặc quyết định truy cập dữ liệu.
- Chọn tenant, giá, quota, workflow hoặc loại giao dịch.
- Xác định public API chỉ bằng tên caller.
- Thay thế request context, principal, capability hoặc audit event.
- Giữ Stream StackFrame sau khi walk kết thúc.

## 12. Lỗi thường gặp

**Dùng tên caller để phân quyền:** tên class là chi tiết triển khai, không chứng minh quyền. Dùng principal và policy đã xác thực.

**Dùng độ sâu stack làm điều kiện nghiệp vụ:** thêm wrapper hoặc interceptor có thể thay đổi độ sâu. Dùng tham số hoặc context rõ ràng.

**Quên RETAIN_CLASS_REFERENCE:** lấy Class từ StackFrame hoặc gọi getCallerClass cần option này.

**Giữ Stream sau walk:** stream chỉ dùng trong callback của walk. Thu thập dữ liệu cần thiết thành collection hoặc value trước khi trả về.

**Giả định stack chứa đủ mọi frame:** frame reflection và hidden bị lọc mặc định; native method và thông tin debug cũng có giới hạn.

**Đọc stack của thread khác:** StackWalker chỉ duyệt stack của thread đang gọi.

**Ghi toàn bộ stack trong mọi request:** có thể tạo log lớn và lộ cấu trúc nội bộ. Giới hạn depth và chỉ thu thập khi cần.

**Dùng StackWalker làm correlation ID:** stack thay đổi giữa các lần chạy. Dùng trace ID hoặc request ID được truyền theo context.

## 13. Checklist thiết kế

- Dùng StackWalker cho quan sát và chẩn đoán.
- Không dùng class, method, line number hoặc frame depth làm hợp đồng nghiệp vụ.
- Dùng principal đã xác thực cho danh tính và quyền.
- Dùng request context rõ ràng cho tenant và dữ liệu request.
- Bật RETAIN_CLASS_REFERENCE khi thực sự cần Class object.
- Bật SHOW_REFLECT_FRAMES hoặc SHOW_HIDDEN_FRAMES chỉ khi mục tiêu chẩn đoán yêu cầu.
- Tiêu thụ Stream bên trong walk và chỉ giữ dữ liệu đã trích xuất.
- Giới hạn số frame và tránh log stack quá mức.
- Không giả định stack giống nhau sau refactor, proxy hoặc thay đổi runtime.

StackWalker là công cụ quan sát stack hiện hành từ Java 9. Dùng nó để hiểu đường gọi khi chẩn đoán; giữ quyền truy cập, danh tính và quyết định nghiệp vụ trong các hợp đồng dữ liệu tường minh, ổn định và có thể kiểm thử độc lập với cấu trúc stack.
