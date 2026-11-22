# Không coi module boundary là authorization nghiệp vụ

## 1. Mục tiêu

Java Platform Module System (JPMS) tạo ranh giới giữa các module để kiểm soát dependency, khả năng truy cập package và mức độ đóng gói của implementation. Ranh giới này giúp tổ chức code rõ ràng và ngăn module khác phụ thuộc tùy tiện vào package nội bộ.

Tuy nhiên, **module boundary không phải cơ chế phân quyền nghiệp vụ cho người dùng**. JPMS không biết người đang đăng nhập là ai, họ thuộc tenant nào, có vai trò gì hoặc được phép đọc/sửa tài nguyên nào.

Cần phân biệt hai câu hỏi:

- **Module access:** code thuộc module nào có thể đọc module khác, truy cập public type trong package nào, hoặc thực hiện deep reflection ở đâu?
- **Business authorization:** người dùng hoặc service đã được xác thực có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể hay không?

Hai lớp kiểm soát này bổ sung cho nhau. Module encapsulation giúp bảo vệ cấu trúc code và hạn chế truy cập kỹ thuật ngoài ý muốn. Authorization nghiệp vụ phải được thực hiện ở application/service layer dựa trên danh tính, quyền và tài nguyên thực tế.

## 2. JPMS kiểm soát điều gì?

Một named module có thể khai báo dependency và ranh giới package trong module-info.java:

~~~java
module com.acme.orders {
    requires com.acme.persistence;

    exports com.acme.orders.api;
}
~~~

Các directive có ý nghĩa ở cấp module:

- **requires**: khai báo module hiện tại cần đọc một module khác.
- **exports**: công khai package cho module khác truy cập các API theo quy tắc Java language.
- **exports ... to**: chỉ export package cho một danh sách named module.
- **opens**: mở package cho deep reflection ở runtime.
- **opens ... to**: chỉ mở package cho một danh sách module cụ thể.
- **uses / provides**: khai báo module sử dụng hoặc cung cấp service.

Ví dụ module triển khai có thể giữ package nội bộ không export:

~~~text
com.acme.orders
  com.acme.orders.api
  com.acme.orders.internal
~~~

Module descriptor chỉ export package API:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Module khác có thể dùng public API trong com.acme.orders.api nếu các điều kiện readability và access khác được đáp ứng. Code ở module khác không thể import tùy ý public class trong package com.acme.orders.internal qua cơ chế truy cập thông thường.

Đây là một ranh giới kỹ thuật hữu ích: implementation có thể được thay đổi mà không biến package nội bộ thành contract cho toàn hệ thống.

## 3. Vì sao module boundary không phải authorization nghiệp vụ?

JPMS không mô hình hóa danh tính của người dùng cuối. Một module không biết:

- Người dùng đã đăng nhập bằng tài khoản nào.
- Người dùng có vai trò ADMIN, MANAGER hay VIEWER không.
- Người dùng thuộc tổ chức hoặc tenant nào.
- Họ có quyền đọc invoice này nhưng không có quyền đọc invoice khác không.
- Họ có được phép hoàn tiền, phê duyệt hoặc xóa dữ liệu tại thời điểm hiện tại không.

Giả sử module com.acme.orders export API:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Một controller, batch job hoặc module khác có thể gọi API đó. Khi request đến từ người dùng Alice hay Bob, JVM vẫn thực thi code của module gọi theo cùng một module identity. JPMS không tự thay đổi quyền truy cập dựa trên tài khoản đang gửi HTTP request.

Nếu API không kiểm tra quyền nghiệp vụ, bất kỳ caller nào đã truy cập được API và có thể tạo request hợp lệ đều có thể thử thực hiện thao tác mà API cung cấp.

Ví dụ, việc module com.acme.admin được phép đọc package nội bộ không chứng minh người đang sử dụng màn hình admin có quyền quản trị. Tên module là danh tính của code trong module graph, không phải danh tính đã được xác thực của người dùng.

### Qualified exports vẫn không phải role-based access control

Có thể viết:

~~~java
module com.acme.orders {
    exports com.acme.orders.admin to com.acme.admin;
}
~~~

Khai báo này giới hạn module nào có thể truy cập package com.acme.orders.admin theo quy tắc module access. Nó không kiểm tra người dùng có role ADMIN hay không.

Tất cả code được chạy trong module com.acme.admin đều có cùng module identity khi xét quan hệ này. Module system không phân biệt Alice là admin còn Bob chỉ là nhân viên khi cả hai request đều đi qua cùng module.

Qualified exports có ích để giới hạn dependency giữa các thành phần code. Không dùng nó thay cho kiểm tra quyền của principal hoặc quyền trên từng resource.

## 4. Authentication, authorization và module encapsulation là ba khái niệm khác nhau

| Khái niệm | Câu hỏi cần trả lời | Ví dụ cơ chế |
|---|---|---|
| Authentication | Ai đang gọi? | Xác thực session, token, certificate, service identity |
| Authorization | Caller này được phép làm gì trên resource nào? | Role, permission, policy, tenant/resource ownership |
| Module encapsulation | Code của module nào được truy cập package/API nào? | requires, exports, opens, module-info.java |

Authentication tạo ra danh tính đã được xác minh. Authorization sử dụng danh tính đó cùng policy và thông tin tài nguyên để quyết định cho phép hay từ chối thao tác.

JPMS không thay thế hai bước này. Ngược lại, một hệ thống authorization tốt cũng không làm cho module descriptor trở nên thừa: module encapsulation vẫn giúp giảm coupling, bảo vệ implementation và ngăn code phụ thuộc vào API không được công khai.

Ví dụ một request có thể trải qua:

1. Server xác minh access token và lấy principal đáng tin cậy.
2. Application xác định hành động mà request muốn thực hiện.
3. Service tải resource cần thao tác.
4. Authorization policy kiểm tra principal có quyền thực hiện hành động trên resource đó không.
5. Chỉ khi policy cho phép, service mới thực hiện thay đổi.
6. Hệ thống ghi audit event phù hợp.

Module boundary hỗ trợ cấu trúc code ở các bước này; nó không tự quyết định bước 4.

## 5. Thực hiện authorization tại service layer

Giả sử hệ thống quản lý invoice. Người dùng chỉ được đọc invoice thuộc tenant của họ và có permission phù hợp.

Một cách tổ chức module:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Package com.acme.billing.internal chứa repository và implementation nội bộ. Package API cung cấp service cho các caller hợp lệ của ứng dụng.

Ví dụ minh họa:

~~~java
public final class InvoiceService {
    private final InvoiceRepository repository;
    private final AuthorizationService authorization;

    public InvoiceService(
            InvoiceRepository repository,
            AuthorizationService authorization) {
        this.repository = repository;
        this.authorization = authorization;
    }

    public Invoice findInvoice(
            AuthenticatedPrincipal actor,
            InvoiceId invoiceId) {

        Invoice invoice = repository.findById(invoiceId)
                .orElseThrow(InvoiceNotFoundException::new);

        authorization.requireAllowed(
                actor,
                Permission.INVOICE_READ,
                invoice.tenantId());

        return invoice;
    }
}
~~~

Ở đây:

- **AuthenticatedPrincipal** đại diện cho danh tính đã được server xác minh.
- **Permission.INVOICE_READ** là hành động nghiệp vụ.
- **invoice.tenantId()** xác định phạm vi resource.
- **requireAllowed** từ chối request nếu principal không có quyền.

Không lấy principal bằng cách tin một userId hoặc role tùy ý do client gửi lên. Principal phải đến từ authentication context đáng tin cậy, ví dụ token đã được xác minh hoặc session phía server.

Tương tự, các thao tác cập nhật, xóa, phê duyệt và hoàn tiền đều cần policy phù hợp. Việc người dùng nhìn thấy nút Edit trên giao diện không chứng minh họ được phép gọi API cập nhật.

## 6. Kiểm tra quyền trên từng resource, không chỉ trên chức năng

Một lỗi phổ biến là chỉ kiểm tra người dùng có quyền truy cập chức năng hay không:

~~~java
if (actor.hasPermission(Permission.INVOICE_READ)) {
    return repository.findById(invoiceId);
}
~~~

Đoạn code này chưa chắc an toàn. Nếu invoiceId thuộc tenant khác, người dùng có thể đọc dữ liệu ngoài phạm vi được phép.

Authorization cần xét ít nhất:

- **Subject:** ai đang thực hiện hành động?
- **Action:** họ muốn làm gì?
- **Resource:** đối tượng nào bị tác động?
- **Context:** tenant, trạng thái workflow, thời gian, mức rủi ro hoặc điều kiện nghiệp vụ liên quan.

Ví dụ:

~~~java
authorization.requireAllowed(
        actor,
        Permission.INVOICE_APPROVE,
        invoice.id(),
        invoice.tenantId(),
        invoice.status());
~~~

Policy có thể yêu cầu người phê duyệt thuộc cùng tenant, có quyền APPROVE và invoice đang ở trạng thái PENDING.

Cần kiểm tra authorization ở phía server cho mọi request có thể truy cập dữ liệu hoặc thay đổi trạng thái. Không dựa vào ID khó đoán, URL ẩn, menu giao diện hoặc module không export để ngăn truy cập trái phép.

## 7. Ranh giới module hỗ trợ security như thế nào?

Module encapsulation vẫn có giá trị bảo mật ở phạm vi phù hợp.

### Giảm API công khai

Chỉ export package cần cho caller. Giữ implementation, helper, repository nội bộ và class nhạy cảm trong package không export khi có thể.

~~~java
module com.acme.identity {
    exports com.acme.identity.api;
}
~~~

Các module khác phụ thuộc vào API ổn định thay vì truy cập trực tiếp vào package nội bộ. Điều này giảm bề mặt truy cập kỹ thuật và hạn chế việc code bên ngoài gọi nhầm implementation.

### Giới hạn deep reflection

Không mở package bằng opens nếu không có nhu cầu cụ thể. Framework cần reflection có thể được cấp quyền mở đúng package cho đúng module:

~~~java
module com.acme.identity {
    opens com.acme.identity.model to com.acme.json;
}
~~~

Tránh dùng open module nếu chỉ một vài package cần deep reflection. Mở quá rộng có thể khiến framework hoặc code trong module được chỉ định truy cập sâu vào nhiều implementation detail hơn cần thiết.

### Giảm dependency không cần thiết

Dùng requires để khai báo dependency thật sự cần. Không đưa module nhạy cảm vào graph chỉ vì tiện gọi một helper class. Tách API và implementation thành module phù hợp có thể làm dependency rõ ràng hơn.

### Bảo vệ tính toàn vẹn của kiến trúc

Các module không export package nội bộ giúp compiler và runtime phát hiện việc truy cập trái với thiết kế. Khi API thay đổi, code phụ thuộc vào implementation nội bộ ít có cơ hội âm thầm tiếp tục hoạt động.

Các lợi ích này hỗ trợ defense in depth và maintainability. Chúng không thay thế authorization cho từng user, action và resource.

## 8. Những giới hạn cần nhớ

### Module identity không phải user identity

Module name xác định một module trong module graph. Nó không đại diện cho tài khoản người dùng, role, tenant hoặc quyền được cấp trong database.

### Public API vẫn cần kiểm tra quyền

Một public method trong exported package có thể được nhiều thành phần gọi. Nếu method thực hiện thao tác nhạy cảm, chính application/service layer phải thực thi authorization policy.

### opens không cấp quyền nghiệp vụ

opens cho phép deep reflection theo module access rules. Nó không cấp quyền đọc dữ liệu invoice, chuyển tiền hoặc thay đổi tài khoản theo policy nghiệp vụ.

### requires không có nghĩa là được phép thực hiện mọi hành động

requires tạo readability relationship. Nó không trao role ADMIN, không cấp quyền trên dữ liệu và không chứng minh caller đã được xác thực.

### Classpath và unnamed module cần được chú ý

Code chạy trên classpath thuộc unnamed module. Unnamed module đọc mọi module. Điều đó không biến nó thành một security principal đáng tin cậy và cũng không tạo ra policy nghiệp vụ. Hãy hiểu rõ module nào thực sự được export cho unnamed module khi cấu hình ứng dụng.

### Reflection và tùy chọn runtime có thể thay đổi mức encapsulation

Các tùy chọn như **--add-exports** và **--add-opens** có thể mở rộng quyền truy cập module trong runtime configuration. Với package được mở cho **ALL-UNNAMED**, code trên classpath có thể nhận quyền truy cập tương ứng.

Một số API runtime cũng cho phép điều chỉnh quan hệ module trong các điều kiện caller nhất định. Vì vậy, cần kiểm soát command line, startup scripts, build configuration và quyền vận hành JVM.

Đừng coi việc package không export trong module-info.java là bằng chứng duy nhất rằng dữ liệu nghiệp vụ đã được bảo vệ.

### JPMS không phải sandbox cho code không đáng tin cậy

Các module cùng chạy trong một JVM không tự động có process isolation riêng. Code đã được nạp và thực thi trong process có thể sử dụng các API, thread, tài nguyên và quyền của process theo những giới hạn runtime hiện có.

Nếu phải chạy plugin hoặc extension không đáng tin cậy, không nên dựa vào module boundary để cách ly nó. Hãy cân nhắc process/container riêng, OS identity riêng, giới hạn filesystem/network, credential riêng và giao thức giao tiếp được kiểm soát. Thiết kế cách ly phải phù hợp với threat model thực tế.

## 9. Defense in depth cho ứng dụng modular

Một hệ thống an toàn thường phối hợp nhiều lớp:

1. **Authentication:** xác minh user hoặc service identity; kiểm tra chữ ký, issuer, audience, expiry và các claim cần thiết.
2. **Authorization:** kiểm tra action và resource ở server side; áp dụng least privilege và deny by default.
3. **Tenant isolation:** đảm bảo truy vấn và thao tác luôn giới hạn đúng tenant; không chỉ kiểm tra ở UI hoặc controller.
4. **Data layer:** dùng database account có quyền tối thiểu; cân nhắc row-level security hoặc constraint phù hợp để bảo vệ dữ liệu ở lớp lưu trữ.
5. **Module encapsulation:** chỉ export API cần thiết; hạn chế opens và dependency không cần.
6. **Runtime isolation:** tách process/container khi chạy code có mức độ tin cậy khác nhau; giới hạn network, filesystem và secrets.
7. **Audit và monitoring:** ghi nhận ai thực hiện hành động gì trên resource nào, kết quả cho phép/từ chối và correlation ID phù hợp.

Không phải hệ thống nào cũng cần tất cả kỹ thuật ở mức phức tạp như nhau. Chọn biện pháp theo dữ liệu, tác động của hành động và threat model. Nhưng mọi thao tác nhạy cảm phải có một quyết định authorization có thể giải thích và kiểm thử.

## 10. Ví dụ phân biệt module access với business authorization

Giả sử hai module:

~~~java
module com.acme.admin {
    requires com.acme.billing;
}
~~~

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Cả module admin và module web có thể phụ thuộc vào API billing nếu module graph và package access cho phép.

Điều này chỉ trả lời câu hỏi code có thể gọi API hay không. Nó không quyết định người dùng đang gửi request có được phép thực hiện thao tác quản trị hay không.

Ví dụ:

~~~java
public void refundInvoice(
        AuthenticatedPrincipal actor,
        InvoiceId invoiceId) {

    Invoice invoice = repository.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);

    authorization.requireAllowed(
            actor,
            Permission.INVOICE_REFUND,
            invoice.tenantId());

    paymentGateway.refund(invoice.paymentReference());
}
~~~

Nếu actor không có quyền refund trong tenant tương ứng, service phải từ chối dù caller nằm trong module admin, web hay batch.

Có thể bổ sung một module riêng chứa authorization policy và chỉ export API cần thiết. Tuy nhiên, mọi đường gọi đến thao tác nhạy cảm vẫn phải đi qua policy enforcement. Nếu có một public method khác bỏ qua kiểm tra, module structure tốt cũng không ngăn được lỗi đó.

## 11. Checklist thiết kế và review

Khi thiết kế module:

- Chỉ export package thực sự là API của module.
- Giữ implementation nội bộ trong package không export khi có thể.
- Chỉ dùng opens cho package và module framework thực sự cần reflection.
- Kiểm tra các tùy chọn --add-exports, --add-opens và ALL-UNNAMED trong cấu hình runtime.
- Không xem module name là user identity hoặc role.
- Không xem requires là quyền được thao tác trên dữ liệu.
- Không chạy code không đáng tin cậy trong cùng JVM chỉ dựa trên module encapsulation.

Khi thiết kế authorization:

- Principal có được tạo từ authentication context đã xác minh không?
- Mỗi hành động nhạy cảm có kiểm tra permission ở server side không?
- Policy có xét resource, tenant và trạng thái nghiệp vụ không?
- Các thao tác đọc, cập nhật, xóa, phê duyệt và hoàn tiền có kiểm tra riêng phù hợp không?
- Có ngăn truy cập chéo tenant khi client thay đổi ID trong request không?
- Quyền có mặc định bị từ chối khi thiếu policy hoặc thiếu context không?
- Có audit quyết định authorization và kiểm thử cả trường hợp bị từ chối không?
- Database và hạ tầng có quyền tối thiểu phù hợp không?

## 12. Bài tập tự kiểm tra và đáp án

### Bài 1 — Module admin có nghĩa là user admin?

Một request đi qua module com.acme.admin. Có thể kết luận người gửi request có role ADMIN không?

**Đáp án:** Không. Module identity xác định code/module trong runtime graph, không xác định danh tính người dùng đã đăng nhập. Phải lấy principal từ authentication context và kiểm tra role/permission.

### Bài 2 — Package không export có bảo vệ invoice khỏi truy cập trái phép không?

Một package chứa InvoiceRepository không được export. Điều đó có đủ để đảm bảo người dùng không thể đọc invoice của tenant khác không?

**Đáp án:** Không. Encapsulation hạn chế code module khác truy cập package nội bộ theo module rules. Authorization phải kiểm tra principal, hành động, invoice và tenant ở phía server; data layer có thể bổ sung isolation.

### Bài 3 — Qualified exports có phải RBAC không?

Module billing khai báo:

~~~java
exports com.acme.billing.admin to com.acme.admin;
~~~

Có thể dùng khai báo này để đảm bảo chỉ user có role ADMIN mới refund invoice không?

**Đáp án:** Không. Qualified exports giới hạn module caller, không phân biệt người dùng chạy qua module đó. Refund vẫn phải kiểm tra permission trên resource.

### Bài 4 — opens có cấp quyền đọc dữ liệu nghiệp vụ không?

Module model mở package cho module JSON bằng opens. Module JSON có tự động được phép đọc mọi customer record không?

**Đáp án:** Không. opens chỉ liên quan đến deep reflection trong package ở runtime. Quyền đọc customer record phải được xác định bởi application authorization và data access policy.

### Bài 5 — Có nên chạy plugin không đáng tin cậy trong module riêng?

Một plugin được đặt trong named module riêng và không được export package. Có thể coi plugin đã bị sandbox không?

**Đáp án:** Không. Các module cùng chạy trong một JVM không có process isolation tự động. Với code không đáng tin cậy, cần đánh giá process/container isolation và giới hạn OS, filesystem, network, credential.

### Bài 6 — Quyền ở UI đã đủ chưa?

UI chỉ hiển thị nút Delete cho user có permission. API có cần kiểm tra lại khi nhận DELETE request không?

**Đáp án:** Có. Client có thể tự tạo request mà không dùng UI. Server phải xác thực principal và kiểm tra permission trên resource trước khi thực hiện thao tác.

### Bài 7 — requires có trao quyền ADMIN không?

Module com.acme.admin khai báo requires com.acme.billing. Điều đó có trao quyền admin trên billing data không?

**Đáp án:** Không. requires tạo readability relationship giữa module. Role và quyền trên dữ liệu là policy nghiệp vụ riêng.

### Bài 8 — Kiểm tra tenant ở đâu?

Người dùng có permission INVOICE_READ nhưng invoiceId thuộc tenant khác. Chỉ kiểm tra permission chung có đủ không?

**Đáp án:** Không. Cần kiểm tra resource và tenant scope. Authorization phải đánh giá cả subject, action, resource và context.

**Ghi nhớ:** JPMS kiểm soát code có thể truy cập API và package nào. Authorization nghiệp vụ quyết định một principal đã được xác thực có được phép thực hiện hành động trên resource cụ thể hay không. Dùng module encapsulation để giữ kiến trúc rõ ràng; dùng policy enforcement ở server side để bảo vệ dữ liệu và nghiệp vụ.

## Tài liệu tham khảo

- Oracle Java SE 21 — Java Platform Module System, module declarations và access control: https://docs.oracle.com/en/java/javase/21/docs/specs/jls/jls-7.html
- Oracle Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Oracle Java SE 21 — javac options --add-exports và --add-reads: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — java launcher options --add-exports và --add-opens: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261
