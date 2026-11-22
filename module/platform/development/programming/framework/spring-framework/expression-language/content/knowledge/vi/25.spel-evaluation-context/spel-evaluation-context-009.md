# Kiểm tra quyền truy cập trước khi đưa expression vào runtime

SpEL có thể đánh giá biểu thức để kiểm tra một điều kiện nghiệp vụ hoặc chính sách truy cập. Tuy nhiên, parse được một expression không có nghĩa người gọi được phép sử dụng expression đó, cũng không có nghĩa expression an toàn để chạy trong mọi EvaluationContext.

Trước khi đưa expression vào runtime, ứng dụng cần xác thực người gọi, kiểm tra quyền sử dụng chính sách, xác nhận expression đến từ nguồn được phê duyệt và tạo EvaluationContext chỉ chứa dữ liệu cùng capability cần thiết. Khi expression được dùng để quyết định cho phép một hành động, kết quả phải được kiểm tra theo nguyên tắc fail-closed: thiếu dữ liệu, lỗi đánh giá hoặc kết quả không phải Boolean đều không được coi là cho phép.

Bài học này trình bày cách đặt authorization gate trước khi evaluate, cách tách quyền sử dụng expression khỏi kết quả của policy, cách giới hạn EvaluationContext và cách tích hợp với Spring Security.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt parse expression, authorize việc sử dụng expression và evaluate expression.
- Kiểm tra người gọi có quyền truy cập policy hoặc tài nguyên trước khi chạy biểu thức.
- Chỉ đưa expression đã được đăng ký, xác thực và phê duyệt vào runtime.
- Tạo EvaluationContext riêng cho mỗi lần đánh giá với dữ liệu đã được phép truy cập.
- Giới hạn root object, variable, PropertyAccessor, MethodResolver, TypeLocator và BeanResolver.
- Yêu cầu kết quả Boolean rõ ràng và từ chối khi evaluate lỗi hoặc trả null.
- Kết hợp policy expression với Spring Security method authorization.
- Tránh cache nhầm quyết định truy cập giữa người dùng, tenant hoặc tài nguyên.
- Kiểm thử cả đường được phép, đường bị từ chối và trường hợp lỗi.

Bạn nên biết SpelExpressionParser, Expression, EvaluationContext, bean reference, method invocation và các khái niệm xác thực/ủy quyền trong ứng dụng Spring.

## 2. Ba bước khác nhau: parse, authorize và evaluate

Một luồng SpEL thường có ba bước:

1. **Parse:** phân tích chuỗi và tạo Expression. Bước này kiểm tra cú pháp và xây dựng cấu trúc biểu thức.
2. **Authorize:** xác định người gọi có quyền sử dụng expression/policy đó trên phạm vi dữ liệu hoặc tài nguyên đang yêu cầu hay không.
3. **Evaluate:** thực thi cấu trúc expression với root object, biến và resolver trong EvaluationContext.

Ba bước này giải quyết ba câu hỏi khác nhau:

| Bước | Câu hỏi |
|---|---|
| Parse | Chuỗi có phải cú pháp SpEL hợp lệ không? |
| Authorize | Người gọi có quyền sử dụng policy này trong ngữ cảnh hiện tại không? |
| Evaluate | Với dữ liệu được cung cấp, điều kiện của policy trả về kết quả gì? |

Parse thành công không chứng minh expression an toàn. Evaluate trả về true cũng không tự chứng minh người gọi có quyền truy cập policy hoặc tài nguyên. Ứng dụng phải kiểm tra quyền ở tầng phù hợp trước khi cho phép expression chạy.

Ví dụ, một người dùng có thể có quyền đọc đơn hàng nhưng không có quyền sửa policy kiểm soát việc đọc đơn hàng. Quyền sử dụng policy và quyền thực hiện hành động nghiệp vụ cần được xác định riêng.

## 3. Xác thực người gọi trước khi xử lý expression

Trước tiên, ứng dụng cần biết ai đang gửi yêu cầu. Authentication xác định principal; authorization xác định principal có được phép thực hiện hành động hay không.

Một luồng điển hình:

~~~text
HTTP request
    |
    v
Xác thực principal
    |
    v
Kiểm tra quyền truy cập policy
    |
    v
Kiểm tra tenant và phạm vi tài nguyên
    |
    v
Lấy phiên bản expression đã phê duyệt
    |
    v
Tạo EvaluationContext giới hạn
    |
    v
Evaluate policy
    |
    v
Kiểm tra kết quả Boolean
    |
    v
Cho phép hoặc từ chối hành động
~~~

Không nên lấy expression do client gửi rồi evaluate trước để xem người dùng có được phép hay không. Cách đó đảo ngược ranh giới tin cậy: chính expression chưa được cho phép lại được chạy trước khi authorization hoàn tất.

Nếu người dùng được phép tạo hoặc chỉnh sửa policy, quyền đó cũng phải được kiểm tra riêng tại thời điểm lưu/publish. Một người có quyền thực thi policy đã được phê duyệt không nhất thiết có quyền thay đổi nội dung policy.

## 4. Kiểm tra quyền sử dụng policy trước khi evaluate

Nếu ứng dụng lưu nhiều expression trong database hoặc cấu hình, hãy quản lý chúng như policy có định danh và trạng thái rõ ràng.

Một policy nên có tối thiểu:

- ID ổn định.
- Tenant hoặc phạm vi sở hữu.
- Mục đích sử dụng, ví dụ ORDER_READ hoặc DISCOUNT_ELIGIBILITY.
- Nội dung expression.
- Trạng thái draft, approved, disabled hoặc revoked.
- Phiên bản hoặc thời điểm phát hành.
- Người tạo và người phê duyệt theo quy trình ứng dụng.

Trước khi lấy nội dung để evaluate, kiểm tra:

1. Người gọi có quyền yêu cầu loại hành động này không?
2. Người gọi có quyền dùng policy thuộc tenant/phạm vi hiện tại không?
3. Policy có đang active và đã được phê duyệt không?
4. Policy có đúng loại use case mà endpoint đang thực hiện không?
5. Phiên bản policy có còn hiệu lực không?
6. Tài nguyên đang xét có thuộc phạm vi mà người gọi được phép truy cập không?

Không chỉ dựa vào policy ID do client gửi. Backend phải xác định tenant, principal và tài nguyên từ nguồn tin cậy, sau đó kiểm tra quan hệ sở hữu/ủy quyền ở phía server.

## 5. Chỉ dùng expression đã được phê duyệt

Có ba nguồn expression thường gặp:

| Nguồn | Cách xử lý phù hợp |
|---|---|
| Expression cố định trong source code | Review cùng code và quản lý phiên bản như logic ứng dụng |
| Expression do quản trị viên cấu hình | Có quy trình validate, review, approve và publish trước khi runtime sử dụng |
| Expression do người dùng cuối gửi | Không evaluate như SpEL tổng quát; dùng DSL giới hạn hoặc bộ lọc có schema |

Nếu người dùng cuối chỉ cần chọn field, operator và value, hãy định nghĩa một cấu trúc dữ liệu có giới hạn. Ví dụ:

~~~json
{
  "field": "status",
  "operator": "EQ",
  "value": "ACTIVE"
}
~~~

Backend xác thực field nằm trong allowlist, operator thuộc tập hỗ trợ và value có kiểu đúng. Sau đó ứng dụng tự tạo điều kiện nội bộ từ cấu trúc đã xác thực. Cách này cho phép người dùng tùy chỉnh bộ lọc mà không cấp quyền viết cú pháp SpEL tùy ý.

Nếu quản trị viên được phép viết SpEL, hãy lưu bản draft riêng, parse và kiểm tra theo chính sách, chạy test trên dữ liệu mẫu, yêu cầu phê duyệt rồi mới publish một phiên bản bất biến cho runtime.

Parse chỉ xác nhận cú pháp. Không dùng việc parse thành công làm tiêu chí duy nhất để publish.

## 6. Tạo EvaluationContext sau khi authorization thành công

Sau khi đã xác thực người gọi và policy, tạo context từ dữ liệu mà người gọi được phép sử dụng.

Ví dụ một DTO chỉ chứa dữ liệu phục vụ quyết định:

~~~java
public record OrderPolicyInput(
    String status,
    BigDecimal total,
    boolean customerVerified
) {}
~~~

Biểu thức:

~~~text
#input.status == 'PAID'
    and #input.total >= #minimum
    and #input.customerVerified
~~~

Context được tạo cho lần đánh giá:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();

context.setVariable("input", authorizedInput);
context.setVariable("minimum", minimum);
~~~

Ví dụ này minh họa cách đưa DTO và biến đã được kiểm tra vào context chỉ đọc. Hãy xác nhận các tính năng SpEL cần dùng tương thích với SimpleEvaluationContext. Nếu cần một capability khác, chỉ bổ sung capability đó một cách có chủ đích.

Không đưa toàn bộ entity graph, ApplicationContext, BeanFactory, repository hoặc service quản trị vào root object. Một DTO nhỏ giúp expression chỉ nhìn thấy các trường cần thiết và giảm nguy cơ đọc dữ liệu ngoài phạm vi.

## 7. Giới hạn capability của EvaluationContext

EvaluationContext không chỉ chứa biến. Nó còn quyết định cách expression truy cập property, gọi method, tìm kiểu, tạo object và tham chiếu bean.

| Capability | Cần quyết định |
|---|---|
| PropertyAccessor | Property nào được đọc hoặc ghi? |
| MethodResolver | Method nào được phép gọi? |
| TypeLocator | Có cần T(...) không và những class nào được tham chiếu? |
| ConstructorResolver | Có cần cú pháp new không? |
| BeanResolver | Có cần @beanName không và bean nào được expose? |
| Variables/functions | Dữ liệu và function nào được đưa vào context? |
| Parser configuration | Có bật assignment/auto-grow hoặc các tính năng làm thay đổi object không? |

Với policy chỉ đọc, ưu tiên:

- Root DTO nhỏ hoặc variable có kiểu rõ ràng.
- Property access chỉ đọc.
- Không cấp bean reference nếu không cần.
- Không cấp type reference hoặc constructor invocation nếu không cần.
- Không expose method có side effect.
- Chỉ đăng ký function thuần và được kiểm soát nếu use case thực sự cần.
- Tắt auto-grow nếu expression chỉ dùng để đọc/kiểm tra.
- Không đưa object mutable dùng chung vào context nếu expression có thể sửa nó.

SimpleEvaluationContext thường phù hợp với use case data binding giới hạn. StandardEvaluationContext linh hoạt hơn và cần được cấu hình cẩn thận khi dùng cho policy runtime. Không coi riêng việc chọn một loại context là bảo đảm an toàn; object và capability được đăng ký vẫn quyết định phạm vi truy cập.

## 8. Kiểm tra kết quả theo nguyên tắc fail-closed

Nếu expression quyết định cho phép một hành động, chỉ Boolean true mới được coi là policy pass.

Ví dụ:

~~~java
Object result = expression.getValue(context);

if (!(result instanceof Boolean allowed)) {
    throw new AccessDeniedException(
        "Policy did not return a Boolean result"
    );
}

if (!allowed) {
    throw new AccessDeniedException("Policy denied the action");
}
~~~

Cách xử lý này từ chối các trường hợp:

- Kết quả là false.
- Kết quả là null.
- Kết quả là String, Number hoặc object khác.
- Evaluate phát sinh exception.
- Biến hoặc property bắt buộc không tồn tại.
- Conversion hoặc method invocation thất bại.

Không chuyển một giá trị bất kỳ sang Boolean chỉ để expression có vẻ hoạt động. Policy cần có hợp đồng kết quả rõ ràng.

Fail-closed có nghĩa lỗi hoặc dữ liệu không đủ không được diễn giải thành cho phép. Nếu policy không thể đánh giá, ứng dụng nên từ chối hoặc trả lỗi vận hành phù hợp, đồng thời ghi nhận nguyên nhân ở phía server.

## 9. Ví dụ về luồng kiểm tra trước runtime

Đoạn mã sau minh họa cấu trúc xử lý. Các repository và authorization service là thành phần do ứng dụng định nghĩa:

~~~java
public boolean evaluatePolicy(
        Authentication caller,
        String policyId,
        OrderPolicyInput input) {

    PolicyDefinition policy =
        policyRepository.findActive(policyId)
            .orElseThrow(() ->
                new AccessDeniedException("Policy unavailable"));

    authorizationService.requireCanExecute(
        caller, policy.getTenantId(), policy.getPurpose());

    if (!policy.isApproved()) {
        throw new AccessDeniedException("Policy is not approved");
    }

    if (!"ORDER_READ".equals(policy.getPurpose())) {
        throw new AccessDeniedException("Policy purpose mismatch");
    }

    Expression expression =
        parser.parseExpression(policy.getExpression());

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("input", input);

    Object result = expression.getValue(context);

    if (!(result instanceof Boolean allowed)) {
        throw new AccessDeniedException("Invalid policy result");
    }

    return allowed;
}
~~~

Điểm chính của ví dụ:

1. Backend lấy policy từ nguồn quản lý của ứng dụng.
2. Authorization kiểm tra principal, tenant và purpose trước khi evaluate.
3. Chỉ policy đã được phê duyệt mới được chạy.
4. Context được tạo riêng và chỉ chứa input cần thiết.
5. Kết quả phải là Boolean.
6. Caller tiếp tục thực hiện hành động chỉ khi policy cho phép và các kiểm tra quyền khác cũng thành công.

Trong production, nên parse/validate policy khi publish và lưu phiên bản đã được phê duyệt. Runtime vẫn phải kiểm tra quyền của caller ở mỗi request; không được bỏ qua authorization chỉ vì expression đã parse hoặc đã được cache.

## 10. Kết hợp với Spring Security method authorization

Spring Security cung cấp các annotation method security như @PreAuthorize. Chúng kiểm tra điều kiện trước khi method được gọi thông qua method security interceptor.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ') and @orderAccessPolicy.canRead(#orderId)")
public Order readOrder(Long orderId) {
    return orderService.findById(orderId);
}
~~~

Trong ví dụ:

- hasAuthority kiểm tra authority của caller.
- @orderAccessPolicy tham chiếu bean policy do Spring quản lý.
- canRead kiểm tra caller có quyền đọc order cụ thể hay không.
- Method readOrder chỉ được gọi khi biểu thức cho phép.

Method security phải được bật và expression context của Spring Security phải được cấu hình đúng. Bean policy nên thực hiện kiểm tra chỉ đọc, có đầu vào rõ ràng và không tự thay đổi trạng thái.

Không nhầm @PreAuthorize với @PostAuthorize. @PreAuthorize kiểm tra trước khi method thực thi; @PostAuthorize kiểm tra sau khi method đã chạy và thường dùng để quyết định có trả kết quả hay không. Nếu yêu cầu là ngăn hành động xảy ra trước khi có quyền, hãy đặt kiểm tra ở trước method hoặc service operation.

Một biểu thức SpEL tự tạo bằng StandardEvaluationContext không tự có các hàm hasAuthority hoặc security root object của Spring Security. Những hàm đó chỉ có trong context tích hợp tương ứng.

## 11. Phân biệt quyền truy cập policy với kết quả policy

Giả sử policy có nội dung:

~~~text
#input.total < 500
~~~

Kết quả true chỉ nói rằng điều kiện total nhỏ hơn 500 đúng với input hiện tại. Nó không chứng minh caller được phép đọc policy, được phép truy cập order hoặc được phép thực hiện hành động khác.

Cần tách các lớp:

- **Permission to use policy:** caller có quyền dùng policy này không?
- **Permission to access data:** caller có quyền xem dữ liệu được đưa vào context không?
- **Policy result:** dữ liệu có thỏa điều kiện trong expression không?
- **Permission to perform action:** caller có đủ quyền thực hiện hành động cuối cùng không?

Tùy use case, policy result có thể là một điều kiện bổ sung cho authorization, nhưng không thay thế quyền truy cập được xác định ở tầng bảo mật.

Ví dụ một caller có authority ORDER_READ nhưng không thuộc tenant của order thì vẫn phải bị từ chối, dù expression trả true. Dữ liệu đầu vào cũng không được tải hoặc đưa vào context trước khi phạm vi truy cập được xác nhận.

## 12. Ngăn truy cập chéo tenant và tài nguyên

Trong ứng dụng multi-tenant, mọi bước lấy policy và dữ liệu đều phải ràng buộc tenant từ nguồn tin cậy.

Các nguyên tắc:

1. Lấy tenant hiện tại từ authentication hoặc security context đã xác thực.
2. Kiểm tra policy thuộc tenant đó trước khi đọc nội dung expression.
3. Kiểm tra tài nguyên thuộc tenant/phạm vi được caller truy cập.
4. Chỉ đưa các trường đã được phép vào DTO của expression.
5. Không chấp nhận tenantId trong request làm bằng chứng quyền truy cập.
6. Không tái sử dụng context hoặc kết quả authorization giữa các tenant.
7. Ghi nhận policy ID, version, tenant và decision code trong audit log theo chính sách dữ liệu.

Nếu một policy được chia sẻ toàn hệ thống, hãy thể hiện rõ phạm vi global trong model và authorization. Không suy luận policy global chỉ vì không có tenantId.

## 13. Tránh TOCTOU giữa kiểm tra và hành động

TOCTOU là tình huống trạng thái tài nguyên thay đổi sau khi kiểm tra quyền nhưng trước khi hành động được thực hiện.

Ví dụ:

1. Ứng dụng kiểm tra caller có quyền sửa order.
2. Một tiến trình khác thay đổi owner hoặc trạng thái order.
3. Ứng dụng tiếp tục ghi dựa trên quyết định cũ.

Đối với thao tác nhạy cảm, hãy gắn kiểm tra với thao tác thực tế:

- Đọc lại hoặc khóa tài nguyên trong transaction phù hợp.
- Kiểm tra quyền trên trạng thái hiện tại.
- Thực hiện cập nhật trong cùng transaction khi có thể.
- Dùng optimistic locking hoặc version check nếu dữ liệu có thể thay đổi đồng thời.
- Không coi kết quả expression được tính từ dữ liệu cũ là quyền vĩnh viễn.

Expression nên đánh giá snapshot dữ liệu đã được xác thực cho một lần xử lý. Nếu trạng thái quan trọng thay đổi trước khi ghi, cần kiểm tra lại theo chính sách của nghiệp vụ.

## 14. Cache expression và cache quyết định truy cập

Có thể cache Expression đã parse để tránh parse lại cùng một nội dung. Tuy nhiên, cache expression và cache authorization decision là hai vấn đề khác nhau.

**Cache parsed Expression:**

- Có thể dùng key gồm policy ID, version và parser configuration.
- Chỉ cache phiên bản policy đã được phê duyệt.
- Khi policy bị revoke hoặc thay version, vô hiệu hóa cache phù hợp.
- Mỗi lần evaluate vẫn tạo context với dữ liệu và quyền của caller hiện tại.

**Cache kết quả authorization:**

- Có thể trở nên sai nếu principal, role, tenant, resource owner hoặc trạng thái policy thay đổi.
- Nếu thật sự cần cache, key phải phản ánh mọi yếu tố bảo mật liên quan và có chính sách hết hạn/invalidation rõ ràng.
- Không dùng kết quả true của một người dùng để quyết định cho người dùng khác.
- Không dùng kết quả của một tài nguyên để quyết định cho tài nguyên khác.

Mặc định an toàn là cache cấu trúc expression đã parse, còn authorization và policy evaluation thực hiện lại trong ngữ cảnh hiện tại.

## 15. Xử lý exception và ghi audit

Các lỗi có thể xảy ra trước hoặc trong evaluate:

- Caller không có authority.
- Policy không tồn tại, bị disable hoặc chưa approve.
- Policy thuộc tenant khác.
- Expression không parse được.
- Biến hoặc property bắt buộc không tồn tại.
- Method hoặc type không được phép truy cập.
- Type conversion thất bại.
- Expression trả null hoặc kiểu không phải Boolean.
- Method trong expression ném exception.

Ứng dụng nên phân loại lỗi:

| Loại lỗi | Xử lý |
|---|---|
| Không có quyền | Từ chối truy cập |
| Policy không hợp lệ hoặc chưa phê duyệt | Không evaluate |
| Lỗi cú pháp policy đã publish | Dừng xử lý, báo lỗi cấu hình |
| Lỗi runtime khi evaluate | Fail closed và ghi nhận lỗi |
| Kết quả false | Từ chối theo policy |
| Kết quả không phải Boolean | Từ chối do vi phạm hợp đồng policy |

Audit log nên ghi các metadata cần thiết như caller ID, tenant, action, resource ID, policy ID/version, decision và mã lỗi. Không ghi token, secret, toàn bộ object hoặc expression có thể chứa dữ liệu nhạy cảm nếu không có lý do và chính sách lưu trữ phù hợp.

Thông tin trả cho client nên đủ để hiểu bị từ chối nhưng không tiết lộ cấu trúc nội bộ, expression riêng tư hoặc chi tiết stack trace.

## 16. Kiểm thử authorization gate

Bộ test nên xác nhận quyền được kiểm tra trước khi evaluate:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Caller có quyền, policy approved, expression true | Cho phép theo policy |
| Caller không có quyền dùng policy | Từ chối trước khi evaluate |
| Policy thuộc tenant khác | Từ chối, không tải dữ liệu ngoài phạm vi |
| Policy draft hoặc disabled | Không evaluate |
| Policy sai purpose | Từ chối |
| Expression parse lỗi | Không thực hiện hành động |
| Expression trả false | Từ chối |
| Expression trả null | Từ chối |
| Expression trả String hoặc Number | Từ chối vì sai hợp đồng |
| Evaluate ném exception | Fail closed |
| Biến bắt buộc thiếu | Từ chối hoặc báo lỗi dữ liệu |
| Policy version bị revoke | Không dùng bản cache cũ |
| Hai caller khác nhau | Không dùng chung context hoặc quyết định |
| Hai tenant khác nhau | Không lẫn dữ liệu hoặc kết quả |
| Tài nguyên thay đổi trước khi ghi | Kiểm tra lại theo transaction/version |

Một test quan trọng là xác nhận expression evaluator không được gọi khi authorization service từ chối. Có thể dùng mock hoặc spy trong test để đếm số lần evaluate. Khi caller không có quyền, số lần evaluate phải bằng 0.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Parse thành công nhưng caller vẫn không nên chạy expression | Nhầm cú pháp hợp lệ với quyền sử dụng | Đặt authorization gate trước evaluate |
| Người dùng có thể gửi expression tùy ý | Tin input client là policy đã được duyệt | Dùng policy registry hoặc DSL giới hạn |
| Policy true nhưng truy cập tài nguyên vẫn trái phép | Dùng policy result thay cho authorization | Kiểm tra quyền principal, tenant và resource độc lập |
| Caller không có quyền nhưng expression vẫn chạy | Evaluate trước khi kiểm tra quyền | Đổi thứ tự luồng xử lý và test evaluate count |
| Expression đọc dữ liệu ngoài phạm vi | Root object hoặc bean quá rộng | Dùng DTO nhỏ và context giới hạn |
| Kết quả null được hiểu thành cho phép | Không kiểm tra kiểu Boolean tường minh | Fail closed với null và kiểu khác Boolean |
| Policy cũ vẫn được sử dụng | Cache không gắn version hoặc chưa invalidate | Cache theo version và kiểm tra trạng thái active |
| Dữ liệu giữa request bị lẫn | Chia sẻ EvaluationContext mutable | Tạo context riêng cho mỗi lần evaluate |
| Quyền thay đổi giữa check và write | TOCTOU | Kiểm tra lại trong transaction hoặc dùng versioning |

## 18. Bài tập thực hành

1. Tạo một policy cố định #input.total >= #minimum và đánh giá bằng DTO cùng context chỉ đọc.
2. Tạo service kiểm tra caller có quyền dùng policy ID trước khi gọi Expression.getValue().
3. Viết test xác nhận khi authorization thất bại thì evaluator không được gọi.
4. Thử policy ở trạng thái draft, approved, disabled và revoked.
5. Tạo hai tenant với hai policy cùng tên hiển thị nhưng ID/phạm vi khác nhau; xác nhận không truy cập chéo.
6. Thử expression trả false, null, String và Boolean để kiểm tra fail-closed.
7. Tích hợp @PreAuthorize cho một service method và kiểm tra method không chạy khi bị từ chối.
8. Cache parsed Expression theo policy version nhưng tạo EvaluationContext mới cho mỗi request.
9. Thử thay đổi trạng thái resource giữa authorization check và cập nhật; xác định cách transaction/version check bảo vệ.
10. Ghi audit metadata cho decision allow/deny mà không log secret.

## 19. Checklist trước khi đưa expression vào runtime

- [ ] Caller đã được xác thực chưa?
- [ ] Quyền sử dụng policy đã được kiểm tra trước evaluate chưa?
- [ ] Policy có đúng tenant, purpose và resource scope không?
- [ ] Expression có nguồn tin cậy và đã được phê duyệt không?
- [ ] Policy có version và trạng thái active rõ ràng không?
- [ ] Dữ liệu đưa vào context đã được caller quyền truy cập chưa?
- [ ] Root object/variables có chỉ chứa dữ liệu cần thiết không?
- [ ] EvaluationContext có giới hạn property, method, type, constructor và bean access không?
- [ ] Có tránh expression tùy ý do người dùng cuối gửi không?
- [ ] Kết quả có bắt buộc là Boolean true mới cho phép không?
- [ ] Null, exception và kiểu kết quả sai có bị từ chối không?
- [ ] Authorization có được thực hiện lại khi trạng thái resource thay đổi không?
- [ ] Cache có tách parsed expression khỏi authorization decision không?
- [ ] Có test xác nhận evaluator không chạy khi caller bị từ chối không?
- [ ] Audit log có đủ metadata mà không lộ dữ liệu nhạy cảm không?

## 20. Kết luận

Trước khi đưa expression vào runtime, ứng dụng phải xác thực caller, kiểm tra quyền sử dụng policy và phạm vi tài nguyên, rồi mới tạo context giới hạn để evaluate. Parse thành công không phải authorization; kết quả expression true cũng không thay thế quyền truy cập ở tầng ứng dụng. Chỉ chạy policy đã được phê duyệt, cung cấp DTO và biến cần thiết, giới hạn resolver/accessor, yêu cầu kết quả Boolean và fail closed khi có lỗi. Với hành động nhạy cảm, gắn kiểm tra quyền với thao tác thực tế để tránh TOCTOU, đồng thời cache cấu trúc expression riêng với quyết định authorization.