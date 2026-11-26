# Tích hợp thư viện thành phần, tải tệp và tài nguyên liên quan

Trong module **SPRING_WEB_FLOW**, JSF cung cấp vòng đời xử lý giao diện và hệ thống component để xây dựng biểu mẫu nhiều bước. Các thư viện như PrimeFaces hoặc OmniFaces bổ sung component nâng cao, AJAX, upload và tiện ích giao diện. Khi kết hợp chúng với Spring Web Flow, cần bảo đảm request của JSF đi qua đúng flow execution, tài nguyên của component được phục vụ đúng URL và dữ liệu upload được xử lý an toàn trong vòng đời của flow.

Một view JSF có thể được hiển thị trong `view-state`, phát event để chuyển sang state tiếp theo và giữ dữ liệu nháp trong scope của flow. Tuy nhiên, file upload, AJAX request và tài nguyên JavaScript/CSS có vòng đời riêng. Không nên coi file đã upload là một phần tự động được khôi phục cùng snapshot của flow; cần có chiến lược lưu tạm, xác nhận và dọn dẹp rõ ràng.

## 1. Các lớp tham gia khi tích hợp JSF với Spring Web Flow

Một ứng dụng kết hợp JSF và Web Flow thường có các thành phần sau:

| Thành phần | Trách nhiệm |
|---|---|
| JSF `FacesServlet` và JSF implementation | Nhận request JSF, chạy lifecycle, quản lý component tree và render response |
| Spring Faces / JSF integration của Web Flow | Kết nối lifecycle JSF với flow execution và điều hướng theo event |
| `FlowHandlerMapping` | Ánh xạ URL khởi tạo hoặc tiếp tục flow tới flow handler |
| `JsfFlowHandlerAdapter` | Chuyển request của flow sang cơ chế thực thi JSF được tích hợp với Web Flow |
| Flow registry và `FlowExecutor` | Tìm định nghĩa flow và quản lý execution, state, event, scope |
| Component library | Cung cấp component như upload, date picker, dialog, data table và AJAX |
| JSF resource handler | Phục vụ stylesheet, script, ảnh và tài nguyên do component library đăng ký |
| Multipart parser / servlet container | Đọc request `multipart/form-data` và cung cấp nội dung file cho component |

Các lớp này phải tương thích về phiên bản. Một stack JSF dùng namespace `javax.faces.*` và một stack Jakarta Faces dùng `jakarta.faces.*` không thể được ghép tùy ý với cùng một phiên bản Spring Faces. Hãy chọn bản Spring Web Flow/Spring Faces, JSF implementation và component library hỗ trợ cùng dòng API, sau đó xác nhận cấu hình thực tế của ứng dụng.

## 2. Nối flow handler với JSF lifecycle

Trong cấu hình Spring MVC Servlet phổ biến, flow URL được ánh xạ tới flow registry và request được xử lý bởi adapter dành cho JSF. Ví dụ cấu hình XML minh họa:

```xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
    <property name="order" value="0" />
</bean>

<bean class="org.springframework.faces.webflow.JsfFlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
```

JSF integration còn cần các hook phù hợp để Web Flow tham gia quá trình xử lý view. Với cấu hình dựa trên `faces-config.xml`, các thành phần thường gặp là `FlowViewHandler` và `FlowPhaseListener`:

```xml
<application>
    <el-resolver>org.springframework.web.jsf.el.SpringBeanFacesELResolver</el-resolver>
    <view-handler>org.springframework.faces.webflow.FlowViewHandler</view-handler>
</application>

<lifecycle>
    <phase-listener>org.springframework.faces.webflow.FlowPhaseListener</phase-listener>
</lifecycle>
```

`SpringBeanFacesELResolver` cho phép JSF EL tìm các bean do Spring quản lý; chỉ đăng ký khi ứng dụng dùng Spring-managed backing bean và theo đúng phiên bản Spring tương ứng. Nếu ứng dụng dùng CDI bean thuần, cấu hình CDI/EL resolver của JSF thay thế phù hợp.

Đây là hình thức cấu hình theo dòng Spring Faces/JSF tương ứng; tên lớp và cách đăng ký có thể thay đổi theo phiên bản. Nếu ứng dụng dùng Java configuration hoặc cấu hình tự động, hãy dùng cơ chế được phiên bản đó hỗ trợ và tránh đăng ký cùng một handler hai lần.

Flow definition vẫn mô tả state và event:

```xml
<view-state id="editBooking" view="booking/edit">
    <transition on="continue" to="uploadDocuments" />
    <transition on="cancel" to="cancelled" />
</view-state>

<view-state id="uploadDocuments" view="booking/upload-documents">
    <transition on="continue" to="reviewBooking" />
    <transition on="back" to="editBooking" />
</view-state>
```

View JSF phát event như `continue`, `back` hoặc `cancel`; integration chuyển event đó cho flow execution để chọn transition. Không tự điều hướng bằng URL tĩnh tới một file Facelets nếu màn hình đó thuộc flow và cần giữ execution key. Dùng URL do Web Flow render để request tiếp tục đúng execution.

## 3. Tạo view Facelets và phát event của flow

Một view Facelets có thể dùng component JSF chuẩn cùng component của thư viện bên ngoài. Ví dụ:

```xhtml
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:h="http://xmlns.jcp.org/jsf/html"
      xmlns:f="http://xmlns.jcp.org/jsf/core"
      xmlns:p="http://primefaces.org/ui">
<h:head>
    <title>Chỉnh sửa booking</title>
</h:head>
<h:body>
    <h:form id="bookingForm">
        <p:messages id="messages" showDetail="true" />

        <p:outputLabel for="note" value="Ghi chú" />
        <p:inputTextarea id="note" value="#{flowScope.bookingForm.note}"
                         maxlength="500" />

        <p:commandButton value="Tiếp tục" action="continue"
                         process="@form" update="messages" />
        <p:commandButton value="Hủy" action="cancel"
                         process="@this" immediate="true" />
    </h:form>
</h:body>
</html>
```

Ví dụ dùng namespace PrimeFaces minh họa; namespace Facelets, component và thuộc tính có thể khác theo JSF/PrimeFaces version. `flowScope.bookingForm` đại diện dữ liệu được Web Flow giữ qua các state. Với `process="@form"`, component form được xử lý theo lifecycle trước khi event `continue` được điều phối. Nút hủy dùng `immediate` trong một số trường hợp để tránh validation của field đang nhập chặn thao tác hủy; cần kiểm thử đúng hành vi mong muốn và không dùng `immediate` để bỏ qua kiểm tra bảo mật hoặc quy tắc nghiệp vụ.

Khi event `continue` được phát, flow chuyển sang state kế tiếp nếu quá trình JSF xử lý và validation thành công. Nếu validation thất bại, view hiện tại cần hiển thị message và giữ dữ liệu người dùng đã nhập để họ sửa. Event ID trong `action` phải khớp chính xác với thuộc tính `on` của transition.

## 4. Dùng thư viện component mà không phá vỡ flow

Thư viện component giúp giảm code giao diện nhưng cần tuân thủ lifecycle và cơ chế request của JSF:

- Dùng component library được hỗ trợ bởi JSF implementation và phiên bản Spring Faces đang chạy.
- Với component AJAX, bảo đảm partial request vẫn được định tuyến qua integration và mang thông tin execution cần thiết.
- Dùng `process`/`execute` để chỉ định component nào được decode, validate và cập nhật model; dùng `update`/`render` để chỉ định vùng giao diện được render lại.
- Không để một AJAX request đi thẳng tới URL view tĩnh làm mất ngữ cảnh flow.
- Không tự nạp lại JSF core script hoặc script của component library nếu JSF resource handler đã quản lý chúng.
- Với dialog, tab hoặc wizard component, kiểm tra event điều hướng vẫn đi qua flow state thay vì chỉ đổi tab ở phía trình duyệt.

Ví dụ PrimeFaces AJAX cập nhật vùng thông báo:

```xhtml
<p:commandButton value="Kiểm tra mã" actionListener="#{bookingView.checkCode}"
                 process="code" update="codeMessage" />
<p:inputText id="code" value="#{flowScope.bookingForm.code}" />
<p:message id="codeMessage" for="code" />
```

Ở ví dụ này, `checkCode` là listener phục vụ tương tác trong cùng view. Nếu cần chuyển state, hãy phát một event của flow thông qua command action tương ứng. Phân biệt rõ AJAX cập nhật một vùng giao diện với transition chuyển sang state khác.

## 5. Quản lý tài nguyên CSS, JavaScript và ảnh

JSF có resource handler để tạo URL và phục vụ tài nguyên theo library/name. Dùng component chuẩn để tham chiếu tài nguyên của ứng dụng:

```xhtml
<h:head>
    <h:outputStylesheet library="css" name="booking.css" />
    <h:outputScript library="js" name="booking.js" target="body" />
</h:head>
<h:body>
    <h:graphicImage library="images" name="booking-logo.svg"
                    alt="Booking" />
</h:body>
```

Tài nguyên của ứng dụng thường được đặt trong thư mục resources theo quy ước của JSF, ví dụ `resources/css`, `resources/js` và `resources/images` trong web application. Tài nguyên của component library được library đăng ký và render tự động khi component cần dùng. Không sao chép file script nội bộ của PrimeFaces vào thư mục ứng dụng chỉ để tự tham chiếu; việc đó dễ gây tải trùng hoặc lệch phiên bản.

Khi tích hợp Web Flow, cần kiểm tra request tới tài nguyên JSF được xử lý bởi JSF resource handler và không bị flow handler nhận nhầm như một yêu cầu khởi chạy flow. Tùy cách ánh xạ servlet, URL tài nguyên có thể chứa prefix như `javax.faces.resource` hoặc `jakarta.faces.resource`. Cấu hình mapping của `FacesServlet`, filter và security phải cho phép các request tài nguyên đi đúng đường.

Một số điểm cần kiểm tra:

- CSS và JavaScript trả về HTTP 200 với content type phù hợp.
- URL tài nguyên có context path đúng khi ứng dụng triển khai dưới context path khác `/`.
- Resource version/cache busting hoạt động sau khi cập nhật thư viện.
- Các script không bị nạp hai lần khi view render lại hoặc AJAX update.
- CSP, security filter và cache header không chặn tài nguyên cần thiết.
- Tài nguyên riêng tư không được đặt trong thư mục public chỉ vì view cần hiển thị chúng.

## 6. Upload file bằng component JSF chuẩn

JSF 2.2 trở lên cung cấp `<h:inputFile>` với kiểu dữ liệu Servlet `Part`. Form phải gửi `multipart/form-data`, và servlet/container cần được cấu hình multipart phù hợp. Ví dụ view:

```xhtml
<h:form id="attachmentForm" enctype="multipart/form-data">
    <h:outputLabel for="attachment" value="Tệp đính kèm" />
    <h:inputFile id="attachment" value="#{bookingUploadView.file}" />
    <h:message for="attachment" />

    <h:commandButton value="Tải lên" action="uploaded" />
</h:form>
```

Bean nhận file có thể dùng `Part`:

```java
import jakarta.servlet.http.Part;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component("bookingUploadView")
@RequestScoped
public class BookingUploadView {

    private Part file;

    @Autowired
    private AttachmentStagingService stagingService;

    public Part getFile() {
        return file;
    }

    public void setFile(Part file) {
        this.file = file;
    }

    public String uploaded() throws Exception {
        if (file == null || file.getSize() == 0) {
            return null;
        }

        try (var input = file.getInputStream()) {
            stagingService.stage(input, file.getSize(), file.getContentType(),
                    file.getSubmittedFileName());
        }
        return null;
    }
}
```

Đoạn Java minh họa một Spring-managed backing bean; `SpringBeanFacesELResolver` ở phần cấu hình giúp JSF EL tìm bean `bookingUploadView`. Với stack JSF cũ, thay `jakarta.servlet.http.Part` bằng `javax.servlet.http.Part` và dùng phiên bản Spring tương ứng. `AttachmentStagingService` là service của ứng dụng, chịu trách nhiệm kiểm tra và lưu file vào vùng staging. Phương thức upload trả `null` để JSF ở lại view hiện tại sau khi staging; nút `continue` riêng mới phát event để flow chuyển state. Nếu muốn action upload tự phát event, hãy trả một outcome có transition tương ứng trong flow.

Với Servlet 3.x, cấu hình multipart ở servlet nhận request, ví dụ:

```xml
<servlet>
    <servlet-name>Faces Servlet</servlet-name>
    <servlet-class>jakarta.faces.webapp.FacesServlet</servlet-class>
    <multipart-config>
        <max-file-size>5242880</max-file-size>
        <max-request-size>10485760</max-request-size>
        <file-size-threshold>0</file-size-threshold>
    </multipart-config>
</servlet>
```

Đây là cấu hình khái niệm cho trường hợp request được xử lý bởi servlet đó. Khi flow URL được nhận qua Spring MVC `DispatcherServlet` và `JsfFlowHandlerAdapter`, multipart parsing có thể cần được cấu hình tại `MultipartResolver` của `DispatcherServlet` hoặc `MultipartFilter`, tùy mapping và adapter. Xác định servlet/filter thực sự nhận request upload trước khi chọn cách cấu hình; không giả định multipart-config của một servlet khác tự áp dụng cho request flow.

## 7. Upload bằng component library như PrimeFaces

Các thư viện như PrimeFaces có component upload với chế độ đơn giản hoặc AJAX nâng cao. Ví dụ minh họa:

```xhtml
<h:form id="uploadForm" enctype="multipart/form-data">
    <p:fileUpload id="files"
                  mode="advanced"
                  auto="true"
                  multiple="true"
                  listener="#{bookingUploadView.handleUpload}"
                  sizeLimit="5242880"
                  allowTypes="/(\.|\/)(pdf|png|jpe?g)$/" />

    <p:messages id="uploadMessages" />

    <p:commandButton value="Tiếp tục" action="continue"
                     process="@this" update="uploadMessages" />
</h:form>
```

Tên package và chữ ký listener phụ thuộc phiên bản PrimeFaces. Một số phiên bản dùng `org.primefaces.event.FileUploadEvent` và `UploadedFile`; các bản mới có thể thay đổi API model. Hãy theo đúng tài liệu của phiên bản đang dùng. `sizeLimit` và `allowTypes` cải thiện trải nghiệm phía component nhưng không thay thế giới hạn và kiểm tra ở server.

Ví dụ PrimeFaces là phương án thay thế cho `<h:inputFile>` ở phần trước, không phải một listener bổ sung cho bean nhận `Part`. Bean `bookingUploadView` cần triển khai phương thức `handleUpload` với chữ ký event đúng phiên bản PrimeFaces; phương thức đó đọc stream từ `event.getFile()` và chuyển stream cùng metadata sang `AttachmentStagingService`. Dù dùng component nào, service staging và quy tắc xác thực phía server vẫn có thể dùng chung.

Với upload AJAX, request từng file có thể là một partial request riêng. Cần xác nhận:

- Request upload đi qua đúng flow execution và session.
- Multipart parser xử lý request trước khi JSF/component đọc nội dung.
- Component library được cấu hình đúng chế độ upload cho Servlet/container đang dùng.
- AJAX response có thể cập nhật message/progress mà không làm mất state hoặc execution key.
- Nút `continue` chỉ chuyển state sau khi các file bắt buộc đã được staging và xác thực.

Không dùng `allowTypes`, phần mở rộng hoặc MIME type do trình duyệt gửi như bằng chứng duy nhất về loại file. Những giá trị này đều có thể bị giả mạo.

## 8. Không giữ nội dung file thô trong flow scope

File upload thường có kích thước lớn và gắn với tài nguyên request như `Part`, `UploadedFile` hoặc stream. Không nên lưu trực tiếp các object này vào `flowScope` để chờ người dùng hoàn thành nhiều bước. Request upload có thể kết thúc, stream có thể bị đóng và object có thể không serialize được khi repository lưu execution.

Một thiết kế phù hợp là:

1. Component nhận multipart request và cung cấp stream.
2. Service kiểm tra giới hạn, đọc stream và lưu file vào vùng staging riêng.
3. Service trả về một mã tham chiếu ngẫu nhiên, không đoán được.
4. Flow chỉ lưu mã tham chiếu cùng metadata tối thiểu trong `flowScope`, chẳng hạn tên hiển thị đã làm sạch, kích thước và trạng thái kiểm tra.
5. Khi người dùng xác nhận, service kiểm tra quyền sở hữu mã tham chiếu, quét file và gắn file vào booking trong một transaction phù hợp.
6. Nếu flow bị hủy hoặc hết hạn, một cơ chế cleanup xóa file staging chưa được xác nhận.

Ví dụ cấu trúc dữ liệu flow có thể giữ:

```java
public class StagedAttachment {
    private String token;
    private String displayName;
    private long size;
    private String detectedType;
    private String status;
}
```

Không lưu đường dẫn file nội bộ có thể truy cập tùy ý hoặc tên file gốc làm đường dẫn trên server. Token phải được kiểm tra thuộc đúng flow/user/booking trước khi dùng. Tệp riêng tư nên được lưu ngoài web root và chỉ tải xuống qua endpoint kiểm tra quyền.

## 9. Kiểm tra file và giới hạn tài nguyên ở server

Một upload an toàn cần nhiều lớp kiểm tra:

- **Kích thước:** giới hạn mỗi file, tổng request, số lượng file và dung lượng staging theo người dùng/booking.
- **Phần mở rộng:** dùng allowlist như PDF, PNG hoặc JPEG theo yêu cầu nghiệp vụ; chuẩn hóa chữ hoa/thường trước khi kiểm tra.
- **Nội dung thực:** kiểm tra magic bytes hoặc parse bằng thư viện phù hợp; không tin `Content-Type` từ client.
- **Tên file:** tạo tên lưu trữ ngẫu nhiên; chỉ giữ tên hiển thị đã làm sạch và encode khi render.
- **Vùng lưu trữ:** đặt ngoài web root, phân quyền filesystem tối thiểu và tránh ghi đè file đã tồn tại.
- **Malware:** quét file hoặc chuyển qua hệ thống kiểm tra trước khi cho phép tải/xử lý.
- **Quyền:** xác nhận người dùng được phép gắn tệp vào đúng booking và không thể dùng token của flow khác.
- **Tài nguyên:** đặt timeout, giới hạn request body ở reverse proxy/container và bảo vệ khỏi upload quá nhiều hoặc request chậm.

Kiểm tra ở giao diện chỉ giúp người dùng chọn đúng file. Quyết định chấp nhận phải được thực hiện ở server trước khi file được dùng trong nghiệp vụ.

## 10. Kết hợp file staging với transaction và vòng đời flow

Upload file và ghi dữ liệu database không phải lúc nào cũng nằm trong cùng một transaction. File system hoặc object storage thường không tham gia transaction database thông thường. Vì vậy, hãy thiết kế các bước staging và finalize có thể phục hồi:

| Giai đoạn | Thao tác | Xử lý khi thất bại |
|---|---|---|
| Upload | Ghi file vào staging và tạo token | Xóa file dở dang, ghi log và trả message |
| Validate | Kiểm tra loại file, kích thước, malware và quyền | Đánh dấu rejected, không cho flow xác nhận |
| Confirm | Trong transaction, tạo metadata/quan hệ attachment với booking | Rollback metadata nếu database lỗi; giữ staging để retry có giới hạn hoặc đánh dấu chờ xử lý |
| Finalize | Chuyển file sang vùng lưu chính hoặc đánh dấu đã gắn | Dùng trạng thái trung gian và retry idempotent nếu storage không cùng transaction |
| Cancel/expire | Xóa file staging chưa được xác nhận | Cleanup job xử lý file mồ côi sau thời hạn |

Không giữ database transaction mở trong lúc truyền một file lớn hoặc chờ quét malware. Hãy staging trước, thực hiện kiểm tra ngoài transaction dài, sau đó mở transaction ngắn để ghi metadata và trạng thái nghiệp vụ. Nếu thao tác lưu metadata và chuyển file không thể nguyên tử, dùng trạng thái như `PENDING`, `READY`, `REJECTED` cùng retry/compensation rõ ràng.

Flow có thể điều phối các state `uploadDocuments`, `reviewBooking`, `confirmBooking` và `bookingSaved`, nhưng service phải sở hữu quy tắc gắn tệp, quyền truy cập và trạng thái lưu trữ. Khi flow kết thúc hoặc bị bỏ dở, cleanup không nên chỉ dựa vào một action `on-end`, vì process/session có thể mất đột ngột. Dùng TTL và tiến trình dọn file staging mồ côi độc lập.

## 11. AJAX, validation và thông báo lỗi

Với component AJAX, cần phân biệt lỗi component, lỗi JSF lifecycle và lỗi flow:

- **Lỗi component/upload:** file quá lớn, định dạng không được hỗ trợ hoặc upload bị gián đoạn. Hiển thị message tại vùng upload và cho phép thử lại.
- **Lỗi JSF validation/conversion:** field không hợp lệ; giữ view hiện tại và render message tương ứng.
- **Lỗi flow transition:** event không có transition phù hợp hoặc execution không còn hợp lệ; xử lý bằng cấu hình flow/exception handler.
- **Lỗi nghiệp vụ:** người dùng không có quyền, booking đã đóng hoặc tệp không còn thuộc flow; trả kết quả nghiệp vụ để flow hiển thị nhánh thích hợp.

Đối với AJAX partial response, response cần đúng định dạng mà JSF/component library mong đợi. Không trả một trang HTML lỗi đầy đủ vào request AJAX nếu client đang chờ XML/partial response. Ghi log server với correlation ID và thông tin cần thiết; không đưa đường dẫn lưu trữ, stack trace hoặc dữ liệu cá nhân vào message hiển thị.

## 12. Kiểm thử tích hợp JSF, component và upload

Kiểm thử cần bao phủ cả render, lifecycle, request multipart và flow transition:

1. **Render view:** JSF dựng được view-state và component library; các script/style cần thiết được render đúng URL.
2. **Resource request:** request tới CSS, JavaScript, ảnh và resource của component trả về thành công, không bị flow handler bắt nhầm.
3. **Flow event:** command action phát đúng event ID và flow chuyển tới state mong đợi.
4. **AJAX component:** partial request giữ đúng execution/session, cập nhật đúng vùng giao diện và không chạy action không liên quan.
5. **Upload hợp lệ:** gửi multipart file được chấp nhận, service staging được gọi và flow chỉ tiếp tục khi file sẵn sàng.
6. **Upload sai:** thử file quá lớn, phần mở rộng lạ, MIME giả mạo, nội dung không đúng định dạng và số lượng file vượt giới hạn.
7. **Request không có multipart:** xác nhận thông báo phù hợp và không làm hỏng flow execution.
8. **Hủy flow:** xác nhận file staging chưa gắn được đánh dấu để cleanup và không để lại attachment mồ côi lâu dài.
9. **Lỗi database sau upload:** xác nhận metadata không bị commit một phần và staging có thể retry hoặc được cleanup theo chính sách.
10. **Quyền truy cập:** thử dùng token upload từ user/booking khác và xác nhận bị từ chối.
11. **Refresh hoặc nhiều tab:** xác nhận cùng một file không bị gắn trùng và thao tác finalize có idempotency.
12. **Session hết hạn:** xác nhận flow phục hồi hoặc hiển thị thông báo hết hạn; file staging được dọn theo TTL.

Test unit cho `AttachmentStagingService` có thể kiểm tra validator, tên file, giới hạn và cleanup bằng storage giả. Test flow dùng test support của Spring Web Flow để kiểm tra state/event. Kiểm thử multipart, JSF lifecycle và AJAX cần chạy qua Servlet container hoặc môi trường tích hợp phù hợp vì mock request đơn giản có thể không mô phỏng đầy đủ resource handler và component decoder.

## 13. Lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Component hiển thị nhưng CSS/JS không tải | Resource mapping sai, servlet/filter chặn URL tài nguyên hoặc library version lệch | Kiểm tra URL resource, status HTTP, content type và FacesServlet mapping |
| AJAX hoạt động nhưng flow không chuyển state | Listener chỉ cập nhật component, chưa phát event của flow | Tách AJAX listener khỏi command action phát event |
| Upload luôn rỗng | Form thiếu `multipart/form-data` hoặc request chưa được multipart parser xử lý | Kiểm tra enctype và resolver/servlet nhận request |
| Upload thường hoạt động nhưng upload AJAX lỗi | Component upload mode không tương thích container hoặc partial request không đi qua đúng adapter | Kiểm tra phiên bản component library và route flow request |
| Sau upload, quay lại state thì file biến mất | Chỉ giữ `Part`, `UploadedFile` hoặc stream trong request | Staging file và giữ token trong flow scope |
| File được tải lên nhưng không gắn với booking | Chưa finalize metadata/quan hệ trong bước xác nhận | Kiểm tra state confirm và transaction của service |
| Hủy flow để lại file tạm | Cleanup chỉ phụ thuộc event kết thúc bình thường | Dùng TTL và job dọn file staging mồ côi |
| File nguy hiểm vượt qua kiểm tra | Chỉ tin extension hoặc MIME client gửi | Kiểm tra nội dung thực, scan và allowlist server-side |
| Nhiều lần submit tạo attachment trùng | Refresh/retry không có idempotency | Dùng token duy nhất, unique constraint và finalize idempotent |

## 14. Checklist triển khai

Trước khi đưa JSF component library và file upload vào một flow, hãy xác nhận:

1. JSF implementation, Spring Faces/Web Flow và component library tương thích phiên bản, namespace.
2. Flow handler và JSF lifecycle hook được đăng ký đúng, không trùng.
3. View-state render đúng Facelets view và command action phát event khớp transition.
4. AJAX request tiếp tục đúng flow execution; tài nguyên JSF được phục vụ qua resource handler.
5. Multipart parsing được cấu hình trên đúng servlet/filter/DispatcherServlet nhận upload.
6. Upload giới hạn kích thước, số lượng, loại nội dung, quyền và dung lượng lưu trữ ở server.
7. File được staging ngoài web root; flow chỉ giữ token và metadata cần thiết.
8. Finalize file và ghi metadata có retry/idempotency; transaction database ngắn.
9. Cancel, session timeout và flow expiration có cơ chế cleanup file mồ côi.
10. Test render, resource, AJAX, multipart, validation, quyền và phục hồi execution chạy trong môi trường tích hợp.

Khi tích hợp đúng, JSF chịu trách nhiệm vòng đời component và giao diện, component library cung cấp tương tác phong phú, còn Spring Web Flow điều phối hành trình qua state và event. File upload cần một vòng đời lưu trữ riêng gồm staging, xác thực, finalize và cleanup. Giữ rõ các ranh giới này giúp component AJAX không làm mất execution, tài nguyên được tải đúng và dữ liệu file không bị nhầm với snapshot hay transaction của flow.
