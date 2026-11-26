# Thẻ bảo mật Facelets và kiểm tra quyền ở phía máy chủ

Trong chương **Tích hợp JSF**, bài này trình bày cách dùng thẻ bảo mật trong Facelets để điều khiển nội dung được render, đồng thời bảo vệ thao tác thật ở phía máy chủ khi JSF gửi action event vào Spring Web Flow. Một nút “Sửa” có thể được ẩn khỏi người không có quyền, nhưng người dùng vẫn có thể tự gửi postback hoặc gọi URL trực tiếp. Vì vậy, lớp giao diện và lớp nghiệp vụ phải cùng áp dụng chính sách truy cập.

Module **SPRING_WEB_FLOW** mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow, kết hợp JSF/Facelets để hiển thị component và nhận thao tác. Spring Security cung cấp xác thực, authority và các điểm kiểm tra quyền. Bài này dùng ví dụ chỉnh sửa một tài liệu: Facelets chỉ hiển thị nút lưu cho người có authority phù hợp; flow kiểm tra quyền vào state/transition; service kiểm tra lại quyền trên đúng tài liệu trước khi đọc hoặc cập nhật.

## 1. Ba lớp bảo vệ có nhiệm vụ khác nhau

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Facelets/UI | Ẩn hoặc hiển thị component theo quyền để giao diện dễ hiểu. | Chỉ render nút “Lưu” cho `ROLE_DOCUMENT_EDITOR`. |
| Flow/URL | Chặn truy cập flow, state hoặc transition không dành cho actor hiện tại. | Bảo vệ flow chỉnh sửa và event `save`. |
| Service/domain | Quyết định actor có được đọc hoặc thay đổi đúng tài nguyên hay không. | Kiểm tra người dùng có quyền sửa tài liệu có ID cụ thể trong tenant hiện tại. |

Không lớp nào thay thế hoàn toàn hai lớp còn lại. Facelets tag không phải hàng rào bảo mật cho endpoint. Quy tắc bảo vệ URL không nhất thiết biết người dùng có quyền với một `documentId` cụ thể. Service/domain là nơi cuối cùng bảo vệ dữ liệu và bất biến nghiệp vụ.

## 2. Spring Security Facelets Tag Library

Spring Web Flow có thư viện Facelets tag riêng để tích hợp Spring Security với JSF. Trong dòng Spring Web Flow 2.x, tag handler thường dùng là `org.springframework.faces.security.FaceletsAuthorizeTagHandler`, được cung cấp bởi module `spring-faces` tương ứng với phiên bản Web Flow.

Thư viện này khác cách khai báo JSP taglib. Một trang Facelets `.xhtml` cần namespace XML và một file Facelet tag library được đăng ký với JSF. Chỉ thêm `spring-security-taglibs` dành cho JSP không tự động làm cho tag `<sec:authorize>` hoạt động trong Facelets.

### 2.1. Đồng bộ dependency

Với ứng dụng dùng Spring Web Flow 2.x và JSF theo hệ `javax`, dependency JSF integration cần cùng dòng phiên bản với các module Spring Web Flow khác:

```xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-faces</artifactId>
    <version>${spring-webflow.version}</version>
</dependency>
```

`${spring-webflow.version}` phải trùng phiên bản với `spring-webflow` và các module Web Flow liên quan. Kiểm tra release notes để chọn phiên bản JSF tương thích. Tài liệu Spring Web Flow 2.5 mô tả tích hợp JSF 2.2 trở lên và các ví dụ Facelets sử dụng namespace `javax`; không coi cấu hình cũ là cấu hình dùng trực tiếp cho Jakarta Faces 3/4.

### 2.2. Đăng ký Facelets tag library

Tạo file `/WEB-INF/springsecurity.taglib.xml`. Ví dụ tối thiểu đăng ký tag `authorize` và hai EL function thường dùng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE facelet-taglib PUBLIC
    "-//Sun Microsystems, Inc.//DTD Facelet Taglib 1.0//EN"
    "http://java.sun.com/dtd/facelet-taglib_1_0.dtd">
<facelet-taglib>
    <namespace>http://www.springframework.org/security/tags</namespace>

    <tag>
        <tag-name>authorize</tag-name>
        <handler-class>
            org.springframework.faces.security.FaceletsAuthorizeTagHandler
        </handler-class>
    </tag>

    <function>
        <function-name>areAnyGranted</function-name>
        <function-class>
            org.springframework.faces.security.FaceletsAuthorizeTagUtils
        </function-class>
        <function-signature>
            boolean areAnyGranted(java.lang.String)
        </function-signature>
    </function>

    <function>
        <function-name>areAllGranted</function-name>
        <function-class>
            org.springframework.faces.security.FaceletsAuthorizeTagUtils
        </function-class>
        <function-signature>
            boolean areAllGranted(java.lang.String)
        </function-signature>
    </function>
</facelet-taglib>
```

Đăng ký file trên trong `web.xml` bằng context parameter:

```xml
<context-param>
    <param-name>javax.faces.FACELETS_LIBRARIES</param-name>
    <param-value>/WEB-INF/springsecurity.taglib.xml</param-value>
</context-param>
```

Trong template Facelets, khai báo namespace:

```xml
<ui:composition
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:ui="http://java.sun.com/jsf/facelets"
    xmlns:h="http://java.sun.com/jsf/html"
    xmlns:sec="http://www.springframework.org/security/tags">
    <!-- Nội dung view -->
</ui:composition>
```

Các tên `javax.faces.*`, DTD và class `org.springframework.faces.*` ở trên thuộc cách tích hợp JSF cũ. Nếu ứng dụng dùng Jakarta Faces hoặc phiên bản Web Flow khác, hãy kiểm tra module/tag handler tương thích trước khi cấu hình. Nếu class không tồn tại trong dependency thực tế, lỗi nằm ở sự không khớp phiên bản hoặc thiếu module, không phải ở namespace của trang.

## 3. Dùng thẻ `authorize` để điều khiển nội dung Facelets

`authorize` bao quanh một vùng component và chỉ đưa nội dung đó vào giao diện khi điều kiện authority được đáp ứng. Với tag handler trong ví dụ trên, có thể dùng các thuộc tính legacy sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| `ifAnyGranted` | Hiển thị khi actor có ít nhất một authority trong danh sách. |
| `ifAllGranted` | Hiển thị khi actor có tất cả authority trong danh sách. |
| `ifNotGranted` | Hiển thị khi actor không có authority nào trong danh sách. |

Ví dụ chỉ hiển thị nút lưu cho biên tập viên:

```xml
<h:form id="documentForm">
    <h:messages />

    <h:outputLabel for="title" value="Tiêu đề" />
    <h:inputText id="title" value="#{documentForm.title}" />

    <sec:authorize ifAnyGranted="ROLE_DOCUMENT_EDITOR">
        <h:commandButton id="save"
                         value="Lưu"
                         action="save" />
    </sec:authorize>

    <sec:authorize ifNotGranted="ROLE_DOCUMENT_EDITOR">
        <h:outputText value="Bạn chỉ có quyền xem tài liệu này." />
    </sec:authorize>
</h:form>
```

`action="save"` phát action event tên `save` để Spring Web Flow xử lý bằng transition tương ứng. Tag chỉ quyết định nút có xuất hiện trong view hay không. Người dùng vẫn có thể tự tạo request postback với event `save`, vì vậy transition và service vẫn phải kiểm tra quyền.

### 3.1. Dùng EL function trong thuộc tính `rendered`

Khi chỉ cần điều khiển một component, có thể dùng function thay vì bọc cả vùng bằng tag:

```xml
<h:commandButton id="save"
                 value="Lưu"
                 action="save"
                 rendered="#{sec:areAnyGranted('ROLE_DOCUMENT_EDITOR')}"/>
```

`areAnyGranted` trả về boolean để JSF dùng trong thuộc tính `rendered`. `areAllGranted` phù hợp khi phải có đủ nhiều authority. Một số phiên bản tag library còn cung cấp `areNotGranted` và `isAllowed`; hãy kiểm tra đúng `.taglib.xml` và API đang cài trước khi sử dụng.

`isAllowed(url, method)` kiểm tra quyền đối với cặp URL/phương thức HTTP theo cấu hình Spring Security. Nó không thay thế kiểm tra quyền trên một đối tượng domain cụ thể, ví dụ tài liệu số 42 thuộc tenant nào.

## 4. Vai trò, authority và quy ước đặt tên

Spring Security lưu quyền dưới dạng `GrantedAuthority`. Ứng dụng có thể dùng authority như `DOCUMENT_EDIT`, hoặc quy ước role có tiền tố `ROLE_` như `ROLE_DOCUMENT_EDITOR`. Cần thống nhất quy ước giữa:

- UserDetails hoặc authentication provider tạo ra authority.
- Quy tắc URL và method security của Spring Security.
- Thuộc tính `ifAnyGranted`/`ifAllGranted` trong Facelets tag library.
- Phần tử `<secured>` trong flow definition.

Không nhầm `hasRole("DOCUMENT_EDITOR")` với `hasAuthority("ROLE_DOCUMENT_EDITOR")`: `hasRole` thường tự thêm tiền tố `ROLE_`, còn `hasAuthority` so khớp chuỗi authority chính xác. Với tag Facelets cũ dùng `ifAnyGranted`, truyền tên authority đầy đủ theo đúng cấu hình, ví dụ `ROLE_DOCUMENT_EDITOR`.

Tránh tạo quá nhiều role chỉ để điều khiển từng nút. Role thường mô tả nhóm quyền; authority có thể mô tả hành động như `DOCUMENT_READ` hoặc `DOCUMENT_EDIT`. Dù dùng mô hình nào, quyền trên từng tài nguyên vẫn phải được kiểm tra theo owner, tenant, trạng thái và quy tắc domain.

## 5. Bảo vệ flow, state và transition

Spring Web Flow hỗ trợ phần tử `<secured>` ở cấp flow, state và transition. Phần tử này mô tả các authority cần có trước khi đi vào vùng được bảo vệ. Để những khai báo này có hiệu lực, `FlowExecutor` phải đăng ký `SecurityFlowExecutionListener`.

Ví dụ cấu hình XML:

```xml
<webflow:flow-executor id="flowExecutor" flow-registry="flowRegistry">
    <webflow:flow-execution-listeners>
        <webflow:listener ref="securityFlowExecutionListener" />
    </webflow:flow-execution-listeners>
</webflow:flow-executor>

<bean id="securityFlowExecutionListener"
      class="org.springframework.webflow.security.SecurityFlowExecutionListener" />
```

Ví dụ bảo vệ state và transition:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="editDocument" view="document/edit.xhtml">
        <secured attributes="ROLE_USER" />

        <transition on="save" to="saved">
            <secured attributes="ROLE_DOCUMENT_EDITOR" />
            <evaluate expression="documentService.update(flowScope.documentId, flowScope.documentForm)" />
        </transition>
    </view-state>

    <end-state id="saved" view="document/saved.xhtml" />
</flow>
```

`ROLE_USER` cho phép vào màn hình; `ROLE_DOCUMENT_EDITOR` cho phép phát triển transition `save`. Có thể đặt `<secured>` trực tiếp trong flow nếu toàn bộ flow yêu cầu authority đó. Thuộc tính `match="any"` hoặc `match="all"` điều khiển việc cần có một hay tất cả authority; mặc định của cấu hình role-based là `any`.

Ba bước phải đi cùng nhau: cấu hình Spring Security, khai báo `<secured>` trong flow và gắn `SecurityFlowExecutionListener` vào executor. Chỉ viết `<secured>` trong XML mà quên listener sẽ không bảo vệ execution. Listener cũng không tự biết người dùng có quyền sửa đúng bản ghi được truyền trong `flowScope.documentId`; đó là việc của service/domain.

## 6. Kiểm tra quyền cấp đối tượng trong service

Quyền `ROLE_DOCUMENT_EDITOR` có thể cho phép người dùng chỉnh sửa một số loại tài liệu, nhưng không có nghĩa họ được sửa mọi tài liệu trong hệ thống. Service phải kiểm tra actor hiện tại có quyền trên đúng đối tượng, đúng tenant và đúng trạng thái nghiệp vụ.

Có thể bật method security trong cấu hình Spring Security hiện đại:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Với dòng Spring Security cũ, cấu hình tương ứng thường dùng `@EnableGlobalMethodSecurity(prePostEnabled = true)`. Chọn annotation theo phiên bản đang sử dụng.

Service minh họa:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

@Service
public class DocumentService {

    private final DocumentRepository documentRepository;
    private final DocumentAccessPolicy accessPolicy;

    public DocumentService(
            DocumentRepository documentRepository,
            DocumentAccessPolicy accessPolicy) {
        this.documentRepository = documentRepository;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize("hasAuthority('ROLE_DOCUMENT_EDITOR')")
    @Transactional
    public void update(UUID documentId, DocumentForm form) {
        Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();

        Document document = documentRepository.findByIdForUpdate(documentId)
                .orElseThrow(DocumentNotFoundException::new);

        if (!accessPolicy.canEdit(authentication, document)) {
            throw new AccessDeniedException("Không có quyền sửa tài liệu");
        }

        document.updateEditableFields(form.getTitle(), form.getSummary());
    }
}
```

`findByIdForUpdate` là phương thức repository minh họa, có thể được triển khai bằng truy vấn khóa bản ghi hoặc cơ chế concurrency phù hợp. `DocumentAccessPolicy` kiểm tra owner, tenant, quan hệ chia sẻ và trạng thái tài liệu. Việc kiểm tra đối tượng sau khi tải trong transaction giúp tránh dựa vào một ID hoặc owner do client gửi lên.

`DocumentForm` chỉ nên chứa các trường được phép sửa. Không bind `ownerId`, `tenantId`, `approved`, `status` hoặc authority vào form rồi chép toàn bộ vào entity. Service phải tự xác định actor từ `SecurityContext`, không nhận danh tính người dùng từ hidden field.

Method security dựa vào Spring proxy. Hãy gọi service qua bean Spring được inject; lời gọi nội bộ kiểu `this.update(...)` có thể bỏ qua proxy và không kích hoạt interceptor method security. Đồng thời giữ kiểm tra quyền bên trong domain/service cho các quy tắc phụ thuộc đối tượng và trạng thái.

## 7. Kết hợp Facelets, flow transition và service

Ví dụ hoàn chỉnh hơn cho hành trình sửa tài liệu:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="documentId" type="java.util.UUID" required="true" />

    <on-start>
        <evaluate expression="documentService.loadForEdit(flowScope.documentId)"
                  result="flowScope.documentForm" />
    </on-start>

    <view-state id="editDocument"
                view="document/edit.xhtml"
                model="documentForm">
        <secured attributes="ROLE_USER" />
        <transition on="save" to="saved">
            <secured attributes="ROLE_DOCUMENT_EDITOR" />
            <evaluate expression="documentService.update(flowScope.documentId, flowScope.documentForm)" />
        </transition>
    </view-state>

    <end-state id="saved" view="document/saved.xhtml" />
</flow>
```

View `document/edit.xhtml` chỉ render nút lưu khi có authority:

```xml
<ui:composition
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:ui="http://java.sun.com/jsf/facelets"
    xmlns:h="http://java.sun.com/jsf/html"
    xmlns:sec="http://www.springframework.org/security/tags">

    <h:form id="documentForm">
        <h:messages />
        <h:outputLabel for="title" value="Tiêu đề" />
        <h:inputText id="title" value="#{documentForm.title}" />

        <sec:authorize ifAnyGranted="ROLE_DOCUMENT_EDITOR">
            <h:commandButton value="Lưu" action="save" />
        </sec:authorize>
    </h:form>
</ui:composition>
```

Khi người dùng bấm nút, JSF gửi action event `save`; Spring Web Flow ánh xạ event đó tới transition cùng tên. Transition có thể yêu cầu role biên tập viên, sau đó gọi service. Service tiếp tục kiểm tra quyền trên đúng tài liệu. Nếu người dùng giả mạo postback và gửi event `save` dù nút đã bị ẩn, các kiểm tra phía flow/service vẫn phải từ chối thao tác.

Đối với thao tác đọc, `loadForEdit` cũng phải kiểm tra quyền xem trước khi trả form. Không tải dữ liệu nhạy cảm vào model rồi chỉ ẩn component sau khi render.

## 8. Kiểm soát truy cập theo URL và CSRF

Spring Security filter chain nên bảo vệ đường dẫn dùng để khởi chạy và tiếp tục flow. Đây là lớp xác thực và phân quyền thô theo URL/method. Nếu dùng Spring Web Flow với JSF, request thường đi qua Spring MVC `DispatcherServlet` và `JsfFlowHandlerAdapter`; hãy bảo đảm Spring Security filter áp dụng cho các đường dẫn đó.

Không nhầm URL security với object-level authorization. Quy tắc “người dùng có thể POST tới `/spring/document/**`” không chứng minh người đó có quyền sửa `documentId` cụ thể. Cũng không bỏ CSRF protection chỉ vì form là JSF; postback thay đổi dữ liệu vẫn phải tuân thủ cơ chế CSRF của ứng dụng và cấu hình view state.

Không đặt execution key, token xác thực hoặc dữ liệu nhạy cảm vào query string. Không coi một link ẩn hoặc một button không render là cơ chế bảo vệ request.

## 9. Xử lý AccessDeniedException đúng cách

Khi kiểm tra quyền thất bại, service nên ném `AccessDeniedException` hoặc ngoại lệ bảo mật tương ứng. Để ngoại lệ đi lên security filter/exception handling phù hợp; không bắt rồi chuyển thành thông báo validation bình thường hoặc tiếp tục flow như thể thao tác thành công.

Có thể trả 403 cho request đã xác thực nhưng không đủ quyền, hoặc chuyển đến trang đăng nhập khi actor chưa xác thực, tùy cấu hình. Thông báo trên giao diện nên ngắn gọn và không tiết lộ tài liệu có tồn tại hay không nếu chính sách yêu cầu che giấu. Log nội bộ có thể ghi actor, resource, action và correlation ID, nhưng không ghi token hoặc toàn bộ nội dung tài liệu.

## 10. Kiểm thử quyền ở cả giao diện và phía máy chủ

Kiểm thử cần chứng minh cả việc hiển thị đúng component và việc request trái phép bị chặn:

| Tình huống | Kết quả mong đợi |
|---|---|
| Actor có `ROLE_DOCUMENT_EDITOR` | Nút lưu được render; transition và service cho phép nếu actor có quyền trên tài liệu. |
| Actor chỉ có `ROLE_USER` | Có thể xem nếu được phép; nút lưu không render và transition `save` bị từ chối. |
| Actor không có quyền đọc | Flow/service từ chối trước khi dữ liệu tài liệu được đưa vào view model. |
| Gửi postback giả mạo event `save` | Service từ chối; database không thay đổi. |
| Đổi `documentId` sang tài liệu của người khác | Object-level policy từ chối đọc hoặc cập nhật. |
| Người dùng cùng role nhưng khác tenant | Service từ chối nếu tài liệu không thuộc phạm vi tenant. |
| Tài liệu đã khóa hoặc chuyển trạng thái | Command bị từ chối dù actor có role biên tập. |
| Gửi request thiếu CSRF token | Bị Spring Security từ chối theo cấu hình. |
| Gọi service từ controller/job khác | Method security và domain policy vẫn được áp dụng. |
| Quyền bị thu hồi khi flow đang mở | Request save tiếp theo bị kiểm tra lại và từ chối. |

Có thể chia test thành:

1. **Facelets/view test:** kiểm tra button và nội dung chỉ xuất hiện cho authority tương ứng.
2. **Flow test:** kiểm tra secured flow/state/transition với principal có và không có authority.
3. **Service integration test:** gọi service dưới các `Authentication` khác nhau, kiểm tra object ownership, tenant và trạng thái.
4. **HTTP integration test:** gửi trực tiếp postback/event `save`, thay đổi ID, bỏ CSRF token và xác minh không có thay đổi dữ liệu trái phép.

Không dừng ở test “nút không xuất hiện”. Một người dùng có thể tự tạo request mà không cần nhìn thấy nút. Test quan trọng nhất là request trái phép bị từ chối ở phía máy chủ và dữ liệu không thay đổi.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng JSP taglib như thể đó là Facelets taglib | Facelets không nhận ra tag hoặc báo lỗi namespace. | Đăng ký Facelet `.taglib.xml` và handler tương thích. |
| Thiếu `spring-faces` hoặc lệch phiên bản | Không tìm thấy `FaceletsAuthorizeTagHandler` khi khởi động/render. | Dùng module cùng phiên bản Spring Web Flow và JSF tương thích. |
| Dùng cấu hình `javax.faces.*` trên Jakarta Faces | Tag library không được nạp hoặc class không tương thích. | Dùng bản tích hợp Jakarta phù hợp hoặc giải pháp authorization bean/`rendered`. |
| Chỉ ẩn nút bằng `sec:authorize` | Request giả mạo vẫn có thể gọi transition. | Bảo vệ flow và service/domain. |
| Chỉ bảo vệ URL | Actor có thể truy cập ID tài nguyên ngoài quyền. | Kiểm tra object-level theo owner/tenant/trạng thái. |
| Khai báo `<secured>` nhưng quên listener | Flow rule không được thực thi. | Đăng ký `SecurityFlowExecutionListener` với `FlowExecutor`. |
| Không thống nhất role/authority | Tag, flow và method security cho kết quả khác nhau. | Chuẩn hóa tên và tiền tố authority. |
| Bắt `AccessDeniedException` như lỗi form | Request trái phép có thể tiếp tục hoặc bị che giấu. | Để security exception được xử lý ở tầng bảo mật. |

## 12. Checklist triển khai

- [ ] Phiên bản `spring-faces`, `spring-webflow`, Spring Security và JSF tương thích.
- [ ] Facelets tag library được đăng ký đúng với JSF runtime.
- [ ] Trang `.xhtml` khai báo đúng namespace `sec`.
- [ ] `authorize` chỉ dùng để điều khiển nội dung giao diện.
- [ ] Tên role/authority nhất quán giữa authentication, Facelets, flow và service.
- [ ] URL khởi chạy/tiếp tục flow được Spring Security bảo vệ.
- [ ] Flow có `<secured>` ở cấp phù hợp và executor đã đăng ký `SecurityFlowExecutionListener`.
- [ ] Service kiểm tra quyền đọc và ghi trên đúng tài nguyên, tenant và trạng thái.
- [ ] Actor lấy từ `SecurityContext`, không lấy từ form hoặc hidden field.
- [ ] Form binding chỉ cho phép các trường người dùng được sửa.
- [ ] CSRF protection vẫn hoạt động với JSF postback.
- [ ] Có test giả mạo event, thay đổi resource ID và gọi service trực tiếp.

## 13. Kết luận

Thẻ `authorize` của Facelets giúp giao diện chỉ hiển thị component phù hợp với authority; `<secured>` cùng `SecurityFlowExecutionListener` bảo vệ flow, state và transition; service/domain kiểm tra quyền trên đúng tài nguyên trước khi đọc hoặc ghi. Ba lớp này cần phối hợp để request trực tiếp, postback giả mạo hoặc việc thay đổi ID không vượt qua được chính sách bảo mật. Khi tích hợp, hãy đồng bộ phiên bản `spring-faces` với Spring Web Flow và kiểm tra riêng khác biệt giữa JSF dùng `javax` và Jakarta Faces.

## Tài liệu tham khảo

- [Spring Web Flow 2.5 — JSF Integration và Spring Security Facelets Tag Library](https://docs.spring.io/spring-webflow/docs/2.5.x/reference/html/spring-faces.html)
- [Spring Web Flow 2.4 — Securing Flows](https://docs.spring.io/spring-webflow/docs/2.4.x/reference/htmlsingle/)
