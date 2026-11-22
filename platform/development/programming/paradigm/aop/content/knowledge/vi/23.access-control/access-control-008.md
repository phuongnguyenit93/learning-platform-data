# Ngăn aspect bảo mật bị vô hiệu hóa ngoài ý muốn trong AOP

## 1. Vì sao đây là một yêu cầu bảo mật cốt lõi?

Lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) cho phép đặt chính sách bảo mật tại những điểm cắt (*join point*) mà không cần lặp toàn bộ logic kiểm tra quyền trong từng phương thức nghiệp vụ. Một advice có thể chặn lời gọi, kiểm tra danh tính, quyền hạn, đối tượng dữ liệu hoặc trạng thái phiên, rồi chỉ cho phương thức đích thực thi khi được phép.

Nhưng một chính sách bảo mật chỉ có ý nghĩa nếu **mọi đường thực thi cần bảo vệ đều bắt buộc đi qua điểm kiểm tra có hiệu lực**. Nếu phương thức có thể bị gọi bằng một đường khác không qua advice, cấu hình pointcut vô tình bỏ sót, thứ tự aspect khiến cache trả sớm, hoặc lỗi trong cơ chế áp advice làm phép kiểm tra bị bỏ qua, hệ thống có thể hoạt động như thể không có bảo vệ.

Có hai khái niệm cần phân biệt:

- **Aspect được viết đúng:** đoạn mã kiểm tra quyền có thể từ chối các lời gọi không hợp lệ khi chính nó được chạy.
- **Chính sách được thực thi đầy đủ:** tất cả các cách đi tới thao tác nhạy cảm đều buộc phải qua một điểm kiểm tra đủ thẩm quyền, đồng thời không có đường vòng cho caller thiếu quyền.

Chỉ chứng minh điều thứ nhất là chưa đủ. Mục tiêu của bài là thiết kế ranh giới bảo mật theo nguyên tắc **không cho phép đường đi không được bảo vệ** (*fail closed*), phân tích các trường hợp AOP bị vô hiệu hóa ngoài ý muốn và kiểm chứng rằng lời gọi nhạy cảm không thể chạy khi thiếu authorization.

## 2. Bản chất của một security aspect

Trong AOP tổng quát:

| Thành phần | Vai trò trong bảo mật | Rủi ro nếu dùng sai |
| --- | --- | --- |
| **Join point** | Nơi lời gọi/thực thi có thể được kiểm soát | Có đường truy cập không phát sinh join point được instrument |
| **Pointcut** | Chọn những vị trí cần áp advice | Điểm cắt quá hẹp, sai tên hoặc không khớp overload |
| **Before advice** | Kiểm tra điều kiện trước thực thi | Không nhất thiết kiểm soát kết quả/đường tiếp tục |
| **Around advice** | Có thể chặn `proceed()`, từ chối hoặc cho chạy target | Nhánh sớm gọi `proceed()` trước khi kiểm tra |
| **Proxy/decorator** | Bắt những lời gọi đi qua wrapper | Caller giữ tham chiếu target gốc rồi gọi trực tiếp |
| **Weaving/instrumentation** | Chèn advice tại join point do công cụ hỗ trợ | Mất cấu hình weaving, class không được instrument |
| **Security policy** | Quyết định ai được làm gì trên tài nguyên nào | Kiểm tra quyền không đầy đủ hoặc phụ thuộc metadata sai |
| **Trusted context** | Mang principal, tenant, scope và thuộc tính request | Caller giả mạo hoặc context bị lẫn giữa các luồng |

Security advice có thể được diễn tả bằng luồng:

~~~text
Caller
   |
   v
[Trusted entry point]
   |
   v
[Security advice / policy enforcement point]
   |
   +--> Không xác thực / thiếu quyền / lỗi chính sách
   |       |
   |       +----> DENY; target không được chạy
   |
   +--> Được phép theo policy hiện hành
           |
           +----> proceed() ---> Target / resource
~~~

**Không cho qua vì thiếu thông tin** khác với “cứ thử chạy target để xem sao”. Với một thao tác nhạy cảm, nếu không thể xác định principal, không đọc được policy bắt buộc hoặc không chứng minh được quyền, phương án mặc định phải từ chối hoặc dùng cơ chế dự phòng đã được thiết kế rõ, không bỏ qua kiểm tra.

Một security aspect chỉ là một **điểm thực thi chính sách**. Nó không tự bảo vệ những entry point, ngôn ngữ gọi native, direct database access hoặc đường thực thi khác mà công cụ AOP không chặn được.

## 3. Các kiểu “vô hiệu hóa” không chủ ý

Một aspect bảo mật có thể tồn tại trong source code nhưng không chạy ở một số đường đi.

### 3.1. Gọi thẳng đối tượng đích, bỏ qua proxy

Nếu caller được trao cả `secureProxy` lẫn `rawTarget`, họ có thể gọi `rawTarget.delete(...)` mà không qua invocation handler. Proxy chỉ bảo vệ những lời gọi đi qua nó.

~~~text
Caller ---> SecureProxy ---> Authorization ---> Target
   |
   +-------------------- trực tiếp ------------> Target
                           (BYPASS)
~~~

Cách phòng tránh: ràng buộc kiến trúc để target nhạy cảm chỉ được tạo và giữ trong phạm vi tin cậy; xuất ra interface đã bảo vệ. Không coi wrapper là ranh giới bảo mật nếu code thiếu tin cậy vẫn có tham chiếu trực tiếp hoặc có quyền gọi resource dưới nó.

### 3.2. *Self-invocation* trong lớp đích

Một phương thức đã được gọi qua proxy có thể gọi phương thức khác của chính đối tượng bằng `this.otherMethod()`. Nếu cơ chế AOP chỉ intercept qua proxy, lời gọi nội bộ không qua proxy đó.

~~~java
class DocumentService {
    void listDocuments() {
        deleteDocument("doc-7"); // gọi trực tiếp trên this
    }

    void deleteDocument(String id) {
        // Thao tác cần quyền xóa
    }
}
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. Nếu chỉ phương thức `deleteDocument` được áp advice qua proxy, gọi nó từ `listDocuments` theo đường nội bộ có thể bỏ kiểm tra quyền xóa. Nếu weaving tại execution join point được áp đúng, kết quả có thể khác; phải dựa trên hành vi thật của nền tảng.

Giải pháp thiết kế không nên dựa vào việc “tự gọi lại proxy bằng mẹo”. Với thao tác nhạy cảm, có thể tách ra một dịch vụ chỉ có entry point đã bảo vệ, hoặc đặt kiểm tra tại lớp nghiệp vụ/resource không thể bị đường gọi nội bộ bỏ qua.

### 3.3. Pointcut không bao trùm đầy đủ

Ví dụ pointcut chỉ chọn các phương thức mang metadata `@RequiresRole`. Một method nhạy cảm mới được thêm nhưng người viết quên gắn marker; method đó không được advice chọn. Tương tự, đổi tên package, thêm overload, thay visibility hoặc refactor interface có thể thay tập join point mà không làm code advice bị lỗi biên dịch.

Biện pháp:

- Định nghĩa rõ **tập thao tác nhạy cảm cần bảo vệ** từ mô hình quyền nghiệp vụ.
- Dùng **allowlist**: method nhạy cảm không có policy phải bị từ chối hoặc làm ứng dụng không khởi động, thay vì tự do chạy.
- Có kiểm tra cấu hình/coverage lúc bootstrap hoặc kiểm thử; không chỉ test method đã được gắn annotation.
- Kiểm tra overload, inherited method, bridge method, generic type erasure, thay đổi package/signature và pointcut precedence.
- Không xem “advice được phát hiện trong metadata” là bằng chứng đủ; phải chứng minh advice chạy trên **lời gọi thật**.

### 3.4. Nền tảng không thể intercept join point đó

Các kỹ thuật AOP khác nhau có giới hạn:

| Kỹ thuật | Phạm vi thông dụng | Nguy cơ |
| --- | --- | --- |
| Decorator thủ công | Lời gọi qua wrapper | Có thể gọi thẳng object gốc |
| Dynamic proxy theo interface | Method gọi qua interface proxy | Method ngoài interface hoặc gọi thẳng target không được chặn |
| Subclass proxy | Method có thể override và đi qua proxy | `final`, `private`, constructor, static hoặc visibility có thể cản intercept |
| Compile/load-time weaving | Các join point được weaver hỗ trợ và đã cấu hình | Build/load thiếu weaving, thứ tự class loading hoặc classloader khác |
| Runtime instrumentation | Các điểm có hook/bytecode transformation hợp lệ | Module access, agent không nạp, lớp không được biến đổi, lỗi retransform |

Các giới hạn thực tế phụ thuộc bộ máy AOP và ngôn ngữ, không có luật “cứ có aspect là chặn mọi method”. Reflection gọi vào **đối tượng gốc** vẫn có thể đi vòng qua proxy. Việc reflection được kiểm soát ở runtime cũng không khiến proxy tự xuất hiện trên đường gọi đó.

## 4. Bảo mật là một bất biến trên đồ thị lời gọi

Thay vì hỏi “advice có được viết chưa?”, hãy xét đường đi từ các *entry point* tới hành động nhạy cảm:

~~~text
HTTP/CLI/Message/Job/Plugin entry
             |
             v
     Identity/context validated
             |
             v
      Authorization check
             |
             v
       Protected operation
             |
             v
       Data/resource write
~~~

Một yêu cầu đúng có dạng: **với mọi đường đi có thể tới protected operation, policy check hợp lệ phải đã được thực hiện cho đúng principal, action và resource trước khi side effect xảy ra**, trừ đường phục vụ nội bộ được ủy quyền tường minh và ràng buộc bằng quyền hạn riêng.

Có thể coi điều này như *complete mediation*: mỗi lần truy cập tài nguyên cần được kiểm soát tại một điểm có hiệu lực. Chỉ chèn một aspect ở một số service method chưa chứng minh được bất biến nếu còn API khác, job nền, callback, công cụ bảo trì hoặc direct resource access.

Ví dụ những đường thường bị bỏ sót:

- Endpoint mới hoặc command-line command đi thẳng tới repository/resource.
- Scheduled job chạy bằng identity hệ thống nhưng không có phân quyền thích hợp.
- Message consumer gọi implementation trực tiếp.
- Unit test/bootstrap tạo object bằng `new` và không dùng proxy như production.
- Callback sau khi lời gọi ban đầu đã kết thúc nhưng vẫn truy cập resource.
- Batch processor thực hiện thao tác tương tự qua API khác.
- Plugin/module được nạp động giữ tham chiếu tới raw service.

Đối với thao tác nhạy cảm, kiểm tra tại **nơi dữ liệu/tài nguyên được chạm thật** hoặc một boundary đáng tin cậy mà mọi đường đều đi qua sẽ chắc chắn hơn so với chỉ dựa vào hình dạng phương thức.

## 5. Thiết kế *fail closed* và policy allowlist

Một thiết kế nguy hiểm:

~~~text
if policyExistsFor(method):
    checkPolicy(method)
return proceed()
~~~

Khi ai đó thêm method mới và quên policy, lời gọi được cho phép mặc định. Với API nhạy cảm, hãy thay bằng mô hình:

~~~text
policy = resolvePolicy(method, resource, action)

if policy missing:
    deny("Unmapped protected operation")

identity = readTrustedIdentity()
if identity missing:
    deny("Unauthenticated")

decision = authorize(identity, action, resource, policy)
if decision != ALLOW:
    deny("Forbidden")

return proceed()
~~~

Đây là pseudocode, không phải API Java độc lập. Ba nguyên tắc:

1. **Default deny:** method mới hoặc metadata không khớp không mặc nhiên có quyền.
2. **Không thực thi rồi mới kiểm tra:** authorization phải hoàn tất **trước side effect**. Advice dạng after returning không phù hợp để ngăn hành động trái phép.
3. **Không biến lỗi kiểm tra thành allow:** thiếu principal, exception khi resolve policy, timeout policy source hoặc không thể chứng minh quyền không nên rơi vào nhánh `proceed()`.

Nếu tài nguyên là dữ liệu của một tenant hoặc object cụ thể, role chung có thể chưa đủ. Policy phải nhận diện **action** (read/update/delete), **resource ID**, **owner/tenant**, phạm vi dữ liệu và thuộc tính request theo contract.

Với authorization dựa trên thuộc tính (*attribute-based access control*), nên đánh giá trên ngữ cảnh đáng tin từ cơ chế xác thực; đừng nhận `isAdmin=true` từ một tham số mà caller không tin cậy tự gửi rồi coi nó là quyết định quyền cuối cùng.

## 6. Ví dụ Java 17 chạy độc lập: proxy mặc định từ chối

Ví dụ dùng `java.lang.reflect.Proxy` để thực hiện security advice trên một interface. Với phương thức không có policy trong bảng lựa chọn, handler ném `SecurityException`. Method `erase` đòi role ADMIN; `view` đòi READER. Đây là mô hình giáo dục: principal được cung cấp bằng `AtomicReference` để mô phỏng thay đổi người gọi trong chương trình một luồng, **không phải** cơ chế xác thực an toàn cho ứng dụng production.

Tạo tệp **`SecureAspectBoundaryDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

public class SecureAspectBoundaryDemo {
    enum Role { READER, ADMIN }

    record Caller(String name, Set<Role> roles) {
        Caller {
            roles = Set.copyOf(roles);
        }
    }

    interface DocumentApi {
        String view(String id);
        String erase(String id);
    }

    private static final class DocumentStore implements DocumentApi {
        @Override
        public String view(String id) {
            System.out.println("[target] view " + id);
            return "document:" + id;
        }

        @Override
        public String erase(String id) {
            System.out.println("[target] erase " + id);
            return "erased:" + id;
        }
    }

    static DocumentApi secure(Supplier<Caller> currentCaller) {
        DocumentApi target = new DocumentStore();

        return (DocumentApi) Proxy.newProxyInstance(
                DocumentApi.class.getClassLoader(),
                new Class<?>[] { DocumentApi.class },
                (proxy, method, args) -> {
                    Role required = switch (method.getName()) {
                        case "view" -> Role.READER;
                        case "erase" -> Role.ADMIN;
                        default -> throw new SecurityException(
                                "Unmapped protected operation");
                    };

                    Caller caller = currentCaller.get();
                    if (caller == null || !caller.roles().contains(required)) {
                        System.out.println("[guard] deny " + method.getName());
                        throw new SecurityException("Access denied");
                    }

                    System.out.println("[guard] allow " + method.getName());
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        AtomicReference<Caller> identity =
                new AtomicReference<>(new Caller(
                        "alice", Set.of(Role.READER)));

        DocumentApi api = secure(identity::get);
        System.out.println("view=" + api.view("doc-7"));

        try {
            api.erase("doc-7");
        } catch (SecurityException error) {
            System.out.println("blocked=" + error.getMessage());
        }

        identity.set(new Caller(
                "root", Set.of(Role.READER, Role.ADMIN)));
        System.out.println("erase=" + api.erase("doc-7"));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac SecureAspectBoundaryDemo.java
java SecureAspectBoundaryDemo
~~~

Đầu ra:

~~~text
[guard] allow view
[target] view doc-7
view=document:doc-7
[guard] deny erase
blocked=Access denied
[guard] allow erase
[target] erase doc-7
erase=erased:doc-7
~~~

**Điều ví dụ chứng minh:**

- Khi principal chỉ có READER, `view` được proceed tới `DocumentStore`, còn `erase` bị từ chối **trước khi target chạy**. Không xuất hiện dòng `[target] erase` sau lượt bị từ chối.
- Khi principal có ADMIN, `erase` được phép chạy và target mới in `[target] erase`.
- Nếu method được thêm vào interface nhưng quên thêm quy tắc trong switch, handler ném lỗi “Unmapped protected operation”, tức chính sách **default deny** tại proxy.
- `DocumentStore` là lớp `private` và được tạo bên trong `secure(...)`; caller của ví dụ chỉ nhận proxy `DocumentApi`. Mẫu kiến trúc này hạn chế lộ raw target cho code bên ngoài.
- Handler unwrap `InvocationTargetException` để exception nghiệp vụ không bị che bởi lớp reflection wrapper; đây không phải lý do để bắt rồi cho phép truy cập khi xảy ra lỗi kiểm tra quyền.

**Giới hạn bảo đảm:** ví dụ chứng minh việc kiểm tra ở những lời gọi **đi qua proxy**. Nó không biến dynamic proxy thành sandbox an toàn chống mã không đáng tin trong cùng JVM, không chứng minh dữ liệu lưu trữ được bảo vệ trước mọi đường trực tiếp, không thực thi per-document ownership/tenant policy và không có bước xác thực danh tính thật. Production cần policy đầy đủ (principal + action + resource), boundary tin cậy và kiểm thử tất cả entry path.

## 7. Vì sao không được chỉ dựa vào annotation?

Marker, annotation hay metadata là cách khai báo chính sách, không phải cơ chế enforcement. Một annotation như `@Restricted` chỉ có hiệu lực khi:

1. Metadata tồn tại ở nơi interceptor có thể đọc.
2. Pointcut xác định đúng method/join point mang metadata.
3. Nền tảng AOP đã cài aspect vào đúng đường gọi.
4. Advice thật sự chạy trước thao tác nguy hiểm.
5. Advice có dữ liệu danh tính và policy đúng để quyết định.
6. Nhánh deny không gọi `proceed()`.
7. Không tồn tại đường thực thi nhạy cảm đi vòng qua toàn bộ cơ chế đó.

Cần xác định rõ metadata đặt trên interface hay implementation, cách inheritance/override hoạt động, visibility runtime của annotation, bridge methods và overload. Không nên mặc định runtime proxy sẽ đọc annotation từ implementation nếu handler nhận một `Method` của interface.

**Quy tắc kiểm chứng tốt:** một method nhạy cảm không được bảo vệ phải là lỗi rõ ràng lúc khởi động/kiểm thử, thay vì mặc nhiên “không thấy annotation tức là public”. Với phương thức công khai thật sự, hãy khai báo policy `PUBLIC` tường minh ở cấu hình tin cậy, tránh nhầm “chưa gắn nhãn” với “ai cũng được gọi”.

## 8. Thứ tự các aspect có thể làm mất lớp bảo vệ

Giả sử một lời gọi đồng thời có security aspect và caching aspect.

~~~text
A. Security ở ngoài cache:

security {
    cache {
        target
    }
}

B. Cache ở ngoài security:

cache {
    security {
        target
    }
}
~~~

Trong cách A, bất kể hit hay miss, mọi lượt gọi phải đi qua `security`. Trong cách B, một cache hit ở lớp ngoài có thể trả dữ liệu ngay mà không gọi tiếp advice phía trong, nghĩa là **security không chạy**. Khi nội dung cache phụ thuộc quyền người gọi hoặc quyền thay đổi, đây có thể là lỗ hổng nghiêm trọng.

Tương tự, cần xét thứ tự với:

- **Retry:** mỗi attempt có cần đánh giá lại quyền hoặc có thể dùng quyết định quyền đã được xác lập tại boundary? Quy tắc phải rõ.
- **Fallback/circuit breaker:** một fallback trả dữ liệu từ nguồn khác vẫn phải chịu đúng policy nếu dữ liệu nhạy cảm.
- **Transaction:** authorization nên hoàn tất trước side effect. Nếu data authorization phụ thuộc trạng thái DB có thể biến đổi, cần thiết kế nhất quán và chống race.
- **Rate limit/quota:** nếu đặt chỉ ở trong cache thì hit có thể không tiêu thụ quota dù chính sách yêu cầu mọi request đều bị giới hạn.
- **Audit:** logging một lần mỗi caller truy cập phải được bảo đảm cả khi cache hit hoặc fallback.
- **Exception handler:** không biến `SecurityException` thành giá trị “thành công” hoặc lỗi chung khiến caller được tiếp tục qua một nhánh khác.

Tối ưu hiệu năng không được thay đổi vị trí của security boundary khi chưa phân tích an toàn. Chỉ chọn thứ tự bằng tiêu chí “nhanh hơn” là thiếu.

## 9. Danh tính, tenant và bối cảnh lời gọi

Một security aspect thường phụ thuộc **ai đang gọi**, **được phép làm gì**, **trên tài nguyên nào** và **trong bối cảnh nào**:

~~~text
AuthorizationDecision =
    policy(principal, action, resource, tenant, context)
~~~

Principal cần đến từ nguồn đã được xác thực, không lấy trực tiếp từ một tham số tự khai báo của caller thiếu tin cậy. Nếu dùng role-based access control (RBAC), role ADMIN không luôn đồng nghĩa có quyền trên mọi tenant hay mọi đối tượng; cần thêm ownership/tenant rules phù hợp.

Khi dùng context gắn theo luồng như `ThreadLocal`:

- Executor/callback có thể chạy trên luồng khác và **không tự có** context của caller.
- Pool có thể tái sử dụng luồng; context không cleanup đúng sẽ làm request sau nhận identity cũ.
- Một callback tiếp tục sau request có thể dùng identity đã hết hạn hoặc quyền đã thay đổi.
- Khi security context thiếu, không tự gán role đặc quyền để “cho công việc chạy”.
- Việc truyền ngữ cảnh phải do thành phần tin cậy thực hiện, với lifetime và phạm vi ủy quyền rõ ràng.

Đối với tác vụ chạy nền hợp lệ, nên dùng identity hệ thống có quyền **tối thiểu** cho công việc đó và được cấp có chủ đích. Không bê nguyên quyền của caller sang worker vô thời hạn mà không xét expiry, scope hoặc khả năng thu hồi.

## 10. Kiểm tra quyền theo dữ liệu: chống *time-of-check to time-of-use*

Giả sử advice xác minh caller có quyền sửa tài liệu rồi target tiếp tục công việc dài trước khi sửa dữ liệu. Trong lúc đó, ownership/permission có thể đổi. Đây là vấn đề *time-of-check to time-of-use* (TOCTOU).

~~~text
T0: advice kiểm tra caller có quyền trên document X
T1: quyền/owner của X thay đổi
T2: target ghi X dựa trên quyết định cũ
~~~

Không có một cách sửa chung cho mọi hệ thống. Với dữ liệu có yêu cầu nhất quán cao, cần đánh giá quyền trong cùng boundary dữ liệu có khả năng bảo vệ, dùng version check, transaction hoặc cơ chế cập nhật có điều kiện phù hợp. Cần xác định policy có cho dùng **quyền tại lúc bắt đầu request** hay bắt buộc **quyền tại lúc commit**.

Vì vậy một advice chỉ kiểm tra role ở đầu method thường **không đủ** nếu authorization phụ thuộc trạng thái resource có thể bị thay đổi đồng thời. AOP giúp tập trung policy, nhưng nơi ra quyết định phải ăn khớp với semantics dữ liệu.

## 11. Lỗi xử lý bảo mật và quy tắc fail closed

Một lỗi triển khai nguy hiểm:

~~~java
try {
    verifyPermission();
} catch (Exception error) {
    log(error);
}
return proceed(); // Vẫn chạy target khi phép kiểm tra lỗi.
~~~

Đây là mã minh họa, không phải chương trình độc lập. Nếu `verifyPermission()` lỗi do không lấy được policy hoặc identity, nhánh `proceed()` vẫn được chạy, dẫn tới *fail open* ngoài ý muốn.

Một thiết kế an toàn hơn:

~~~text
try:
    decision = evaluatePermission(trustedIdentity, action, resource)
catch policyFailure:
    recordFailureSafely()
    deny()

if decision != ALLOW:
    deny()

return proceed()
~~~

Đây cũng là pseudocode. Trong những hệ thống có mô hình quyết định phong phú (`PERMIT`, `DENY`, `INDETERMINATE`, `NOT_APPLICABLE`), chỉ `PERMIT` hợp lệ mới được proceed theo policy. Không đồng nhất `NOT_APPLICABLE` hay `INDETERMINATE` với quyền truy cập công khai.

Nếu không đọc được policy bắt buộc, cần có hành vi từ chối rõ ràng, ghi nhận sự cố và xử lý theo mức độ nghiêm trọng. Với lỗi hệ thống, có thể báo lỗi phù hợp mà không tiết lộ chi tiết policy, danh tính khác hoặc cấu trúc nội bộ cho caller.

### Lỗi ném trong target khác lỗi authorization

Nếu authorization đã cho phép rồi target ném lỗi nghiệp vụ, advice không nên nuốt lỗi đó rồi trả dữ liệu tùy ý. Bảo toàn cause và đường lỗi giúp người gọi không hiểu nhầm hoạt động đã thành công. Ngược lại, nếu caller thiếu quyền thì **không gọi target để tạo lỗi rồi dùng lỗi đó làm authorization**.

Cần phân biệt audit của “yêu cầu bị từ chối” với “phương thức chạy rồi thất bại”; chúng là sự kiện khác nhau về bảo mật.

## 12. Bất đồng bộ, callback và những lối đi sau return

Một method trả `CompletionStage<T>` có thể chỉ lên lịch công việc rồi trả ngay. Nếu advice kiểm tra quyền trước return, công việc thực tế có thể chạy sau trên executor khác.

Các câu hỏi bắt buộc:

1. Authorization ở T0 có đủ theo hợp đồng, hay worker phải kiểm tra lại quyền lúc truy cập resource?
2. Worker có nhận identity/tenant scope bằng cơ chế được tin cậy không?
3. Quyền có thể bị thu hồi trước lúc worker chạy không?
4. Kết quả/callback có gửi dữ liệu nhạy cảm cho subscriber khác không?
5. Nếu future bị cancel, side effect đã phát ra có được xử lý đúng không?
6. Nếu stage hoàn tất bất thường, nhánh fallback có phát dữ liệu ngoài quyền không?

Một advice đặt ở ranh giới method return **không tự trở thành interceptor của mọi continuation**. Với `Flow.Publisher<T>` hoặc luồng lazy, thao tác thực tế có thể chỉ bắt đầu khi subscriber đăng ký, và cùng publisher có thể có nhiều subscription. Cần chọn authorization boundary phù hợp tại subscription/resource access và quản lý quyền/tenant trên mỗi thực thi theo contract.

Tránh cache một `CompletionStage` hoặc publisher chứa dữ liệu theo tenant rồi chia sẻ với tenant khác chỉ vì tham số nghiệp vụ giống nhau. Không coi việc future được trả về bình thường là tín hiệu tác vụ đã an toàn hoặc thành công.

## 13. Đường vòng ngoài AOP: resource boundary và nguyên tắc đặc quyền tối thiểu

Ngay cả khi mọi method trong một interface đều có security advice, một thành phần có quyền trực tiếp với database, filesystem, network client hoặc bộ nhớ tiến trình vẫn có thể tác động resource mà không qua interface đó. Vì thế:

- Hạn chế việc lộ reference target và resource handle.
- Cấp quyền cho component/resource theo **least privilege**; code đọc dữ liệu không mặc định có quyền xóa.
- Đặt chính sách ở boundary có thể bao phủ mọi entry path, không chỉ ở UI/transport.
- Dùng kiểm soát quyền của chính resource khi có thể, nhất là đối với dữ liệu nhiều tenant hoặc hành động nguy hiểm.
- Tách public API và internal API; explicit authorization cho những lối đi nội bộ có quyền đặc biệt.
- Không dựa vào việc đổi tên method/package hay che annotation như một hàng rào an ninh.

Mã Java chạy trong cùng process và được cấp quyền đầy đủ có thể có nhiều đường truy cập khác; một dynamic proxy không phải ranh giới cô lập dành cho mã độc tùy ý. AOP bảo mật có giá trị lớn trong thực thi chính sách ứng dụng và hạn chế lỗi lập trình, nhưng cần kết hợp kiến trúc và quyền ở tài nguyên để có độ bảo đảm tương ứng.

## 14. Kiểm chứng rằng security aspect không thể bị bỏ qua

Kiểm thử security không chỉ là “advice đã được gọi” hoặc “một request thiếu quyền bị chặn”. Phải kiểm chứng **đường đi không có coverage**, **phương thức mới**, **cache hit**, **self-invocation** và **failure của policy engine**.

| Trường hợp kiểm thử | Kết quả cần chứng minh |
| --- | --- |
| Caller có quyền, gọi qua proxy | Advice cho phép và target thực thi đúng |
| Caller thiếu quyền, gọi qua proxy | Deny **trước** side effect; target execution count không tăng |
| Không có identity | Deny, không tự chọn principal đặc quyền |
| Role không đủ trên resource/tenant | Deny, kể cả khi cùng method/input đã cache |
| Method nhạy cảm mới nhưng thiếu policy | Startup fail hoặc default deny, không chạy trống policy |
| Self-invocation từ method ít quyền sang method nhạy cảm | Không có đường bypass; dùng boundary hoặc weaving thật được kiểm chứng |
| Gọi trực tiếp implementation/raw target | Không thể tiếp cận từ code không tin cậy hoặc resource vẫn kiểm tra quyền |
| Cache hit / fallback | Vẫn kiểm tra những policy bắt buộc |
| Có nhiều advice | Thứ tự bảo đảm kiểm tra quyền trước mọi đường short-circuit |
| Policy source lỗi/timeout | Fail closed, không proceed |
| Proxy/weaving không được kích hoạt | Health/startup check thất bại hoặc kiểm thử phát hiện ngay |
| Callback / executor / scheduled job | Identity và quyền đúng tại nơi thao tác thật |
| Quyền bị thu hồi trong lúc xử lý | Hành vi phù hợp consistency policy |
| Exception từ target | Không biến lỗi nghiệp vụ thành authorization success giả |
| Gọi overload/inherited/bridge method | Coverage đúng theo danh sách protected operations |

Tốt nhất nên có một **ma trận quyền** trên từng action/resource và những testcase negative tương ứng; sử dụng counter hoặc kiểm chứng dữ liệu thật để đảm bảo target không chạy khi bị deny. Với resource có side effect, chỉ log deny không đủ nếu side effect đã xảy ra trước khi ghi log.

### Kiểm tra lúc build/khởi động

Nếu một hệ thống có registry các protected operations, có thể dùng bài kiểm tra fail-fast:

~~~text
for each exposed operation:
    if operation requires protection:
        assert interceptable(operation)
        assert policyMapped(operation)
        assert targetNotExposedThroughUncheckedPath(operation)

assert securityAdviceRegistered()
assert aspectOrderSatisfiesPolicy()
assert policyRepositoryReachableOrFailClosed()
~~~

Đây là pseudocode diễn tả điều kiện kiểm tra. Việc xác định “đường unchecked” toàn cục có thể cần kiểm thử tích hợp, phân tích kiến trúc và rà soát mã; một vòng lặp reflection đơn giản không tự chứng minh được toàn bộ call graph. Dù vậy, kiểm tra fail-fast vẫn hữu ích để ngăn lỗi cấu hình phổ biến trước khi production nhận request.

### Quan sát khi chạy

Nên ghi nhận số lượt permit/deny và nhóm lỗi policy bằng dữ liệu audit phù hợp, nhưng tránh log token, secret hoặc chi tiết nhạy cảm. Có thể giám sát bất thường: thao tác nhạy cảm thành công mà không có dấu vết authorization tương ứng. Tuy nhiên, telemetry là tín hiệu phát hiện; **không thay thế enforcement**. Nếu audit thất bại, policy phải quy định rõ đó là lỗi chặn thực thi hay chỉ lỗi quan sát, dựa trên yêu cầu nghiệp vụ và tuân thủ.

## 15. Những sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao nguy hiểm | Cách thiết kế đúng |
| --- | --- | --- |
| Coi annotation là bằng chứng đã được bảo vệ | Annotation không tự intercept | Kiểm tra proxy/weaving và protected call path |
| Tạo target rồi phát cả raw target và proxy | Caller có đường trực tiếp | Chỉ cấp protected interface, kiểm soát resource |
| Quên self-invocation | Lời gọi `this.method()` có thể bỏ proxy | Chuyển enforcement tới boundary chắc chắn hoặc dùng weaving hỗ trợ |
| Pointcut chỉ chọn vài tên method | Method mới/đổi tên không được kiểm tra | Allowlist/fail-fast coverage |
| Lỗi policy thì ghi log rồi `proceed()` | Fail open | Deny khi không chứng minh được quyền |
| Cache nằm ngoài security | Hit bỏ security advice phía trong | Bảo đảm authorization ở đường luôn chạy |
| Chỉ kiểm tra role, bỏ tenant/resource | Có thể đọc/sửa tài nguyên của người khác | Policy theo principal/action/resource/context |
| Truyền identity qua biến toàn cục | Context lẫn giữa requests | Scoped trusted context và cleanup |
| Tin `ThreadLocal` tự theo callback | Worker có thể không nhận hoặc nhận context cũ | Truyền context có kiểm soát, xác thực tại resource khi cần |
| Kiểm tra sau khi gọi target | Side effect đã xảy ra | Authorization trước thực thi |
| Test chỉ thấy “deny log” | Target có thể vẫn chạy | Kiểm chứng side effect và execution count |
| Cho default “public” khi policy thiếu | Thiếu metadata thành bypass | Default deny hoặc khai báo PUBLIC tường minh |
| Dùng proxy như sandbox an ninh tuyệt đối | Cùng JVM có thể còn đường truy cập khác | Least privilege và resource-level enforcement |
| Không xét TOCTOU | Quyền đổi giữa check và write | Policy nhất quán tại boundary tài nguyên |
| Chỉ thử đường HTTP | Job/consumer/CLI có thể bypass | Kiểm thử toàn bộ entry path |

## 16. Checklist áp dụng

Trước khi tin rằng một security aspect bảo vệ thao tác nhạy cảm, hãy trả lời:

1. Những **action/resource nào cần bảo vệ**, kể cả tác vụ nền và entry point nội bộ?
2. Tất cả đường thực thi đến action có đi qua policy enforcement point không? Nếu không, còn chốt kiểm tra nào ở resource?
3. Pointcut có khớp đúng method/interface/overload và kỹ thuật proxy/weaving đang dùng không?
4. Có method bị `final`/`private` hoặc đường self-invocation khiến advice không chạy không?
5. Target/raw resource có bị lộ cho code không được ủy quyền không?
6. Khi policy/identity vắng mặt, lỗi hoặc unknown, hệ thống có **deny mặc định** không?
7. Chỉ `ALLOW` có thẩm quyền mới đi tới `proceed()`, trước side effect?
8. Quyền có gắn đúng principal, tenant, action, resource và dữ liệu phiên bản không?
9. Cache/fallback/retry và thứ tự aspect có làm skip security không?
10. Với callback/async/publisher, policy có được kiểm tra ở thời điểm và luồng truy cập thật không?
11. Có kiểm tra fail-fast khi thêm method nhạy cảm hoặc thay đổi cấu hình interception không?
12. Kiểm thử negative đã chứng minh **target không chạy** và dữ liệu không thay đổi khi bị deny chưa?
13. Audit/metrics có giúp phát hiện lối đi không qua authorization mà không lộ dữ liệu nhạy cảm không?
14. Quyền tại resource có được giới hạn để giảm hậu quả nếu AOP coverage mắc lỗi không?

## 17. Kết luận

Aspect bảo mật có thể tập trung hóa chính sách kiểm soát truy cập, nhưng hiệu lực của nó phụ thuộc **đường gọi thật sự được intercept**, **pointcut đầy đủ**, **thứ tự advice**, **ngữ cảnh danh tính tin cậy** và **khả năng từ chối mặc định khi thiếu chính sách hoặc dữ liệu**. Một lời gọi không đi qua proxy, một method mới thiếu metadata hoặc một cache hit xảy ra trước security check đều có thể khiến aspect bị vô hiệu hóa ngoài ý muốn.

Cách thiết kế bền vững là đặt authorization tại một boundary mà mọi thao tác nhạy cảm phải đi qua, không lộ đường trực tiếp tới target/resource, kiểm tra fail-fast và kiểm thử negative trên mọi entry path, đồng thời giữ kiểm soát quyền tại tầng tài nguyên phù hợp. **Một security aspect chỉ bảo vệ được những lời gọi mà nó thực sự kiểm soát**, nên bảo đảm coverage và nguyên tắc fail closed quan trọng ngang với việc viết đúng logic kiểm tra quyền.