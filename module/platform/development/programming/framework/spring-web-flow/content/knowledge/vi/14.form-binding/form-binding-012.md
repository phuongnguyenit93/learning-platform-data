# Nhận tệp qua multipart và giới hạn dữ liệu lưu trong flow

Trong một hành trình web nhiều bước, người dùng có thể tải lên hợp đồng, ảnh chứng từ hoặc tệp đính kèm ở một màn hình, rồi xem lại thông tin trước khi xác nhận. Spring Web Flow quản lý state và transition của hành trình; Spring MVC cùng Servlet container tiếp nhận phần dữ liệu multipart của request. Thiết kế cần phối hợp hai phần này để nhận đúng tệp, giới hạn kích thước và giữ flow execution nhẹ, có thể khôi phục.

Bài này thuộc chương **Liên kết biểu mẫu** của module **SPRING_WEB_FLOW**. Trọng tâm là liên kết trường file với biểu mẫu, cấu hình multipart resolver và giới hạn ở tầng Servlet, sau đó xử lý nội dung tệp ngay trong request tải lên. Flow chỉ nên giữ mã tham chiếu và metadata cần cho các bước tiếp theo, không giữ payload lớn trong trạng thái của hành trình.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích cách multipart request đi qua Servlet container, Spring MVC và Spring Web Flow.
- Cấu hình **StandardServletMultipartResolver** và giới hạn dung lượng tệp.
- Tạo biểu mẫu JSP có **enctype="multipart/form-data"** và liên kết trường file với **MultipartFile**.
- Xử lý tệp trong transition của flow và lưu metadata/tham chiếu thay vì giữ nội dung tệp.
- Phân biệt giới hạn của từng tệp, toàn bộ request và dung lượng dữ liệu lưu trong flow.
- Dọn dữ liệu tạm khi người dùng hủy, khi flow kết thúc hoặc khi quy trình hết hạn.
- Kiểm thử các trường hợp tệp hợp lệ, quá giới hạn, sai định dạng và gửi nhiều lần.

## 1. Multipart request đi qua những thành phần nào?

Một form HTML chỉ gửi file khi dùng phương thức POST và encoding **multipart/form-data**. Trình duyệt chia request thành nhiều part: các trường văn bản, trường file và metadata của từng part. Servlet container phân tích nội dung multipart theo cấu hình của servlet.

Với tích hợp Spring MVC, **MultipartResolver** được Spring tìm theo bean name mặc định **multipartResolver** trong web application context của DispatcherServlet. **StandardServletMultipartResolver** sử dụng cơ chế multipart của Servlet container. Sau khi request được phân tích, Spring Web Flow nhận request qua handler adapter và xử lý event trên flow execution tương ứng.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant C as Servlet container
    participant D as DispatcherServlet
    participant M as MultipartResolver
    participant H as FlowHandlerAdapter
    participant F as FlowExecutor
    participant S as DocumentService
    participant R as File storage

    B->>C: POST multipart/form-data
    C->>D: Chuyển request
    D->>M: Phân tích multipart
    M-->>D: Request có file part
    D->>H: Chuyển request của flow
    H->>F: Tiếp tục flow execution
    F->>F: Binding form và nhận event upload
    F->>S: Đọc MultipartFile trong request
    S->>R: Lưu tệp tạm theo luồng dữ liệu
    R-->>S: Storage key
    S-->>F: Metadata và tham chiếu
    F->>F: Giữ metadata trong flowScope
~~~

Multipart resolver không tự quyết định file được lưu nghiệp vụ ở đâu. Nó giúp Spring đọc các part của request. Việc kiểm tra nội dung, lưu vào vùng tạm, quét tệp và quyết định thời điểm xác nhận vẫn thuộc ứng dụng.

Nếu request không được nhận diện là multipart, trường file có thể không được binding như mong đợi. Nếu container từ chối request vì vượt giới hạn, request có thể thất bại trước khi transition của flow được thực thi. Vì vậy, cần cấu hình và kiểm tra cả tầng Servlet lẫn tầng flow.

## 2. Cấu hình multipart resolver và giới hạn dung lượng

Trong Spring MVC dùng Servlet 3.0 trở lên, có thể đăng ký resolver như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.multipart.support.StandardServletMultipartResolver;

@Configuration
public class MultipartConfig {

    @Bean(name = "multipartResolver")
    public StandardServletMultipartResolver multipartResolver() {
        return new StandardServletMultipartResolver();
    }
}
~~~

Bean phải nằm trong web application context phục vụ **DispatcherServlet**. Tên **multipartResolver** là quan trọng vì Spring MVC tra cứu resolver theo tên quy ước này.

**StandardServletMultipartResolver** dựa vào cấu hình multipart của Servlet. Trong ứng dụng dùng Java-based Servlet initializer, có thể đặt giới hạn trên servlet registration:

~~~java
import jakarta.servlet.MultipartConfigElement;
import jakarta.servlet.ServletRegistration;

import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;

public class WebAppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected void customizeRegistration(
            ServletRegistration.Dynamic registration) {

        registration.setMultipartConfig(
                new MultipartConfigElement(
                        System.getProperty("java.io.tmpdir"),
                        10L * 1024 * 1024,
                        12L * 1024 * 1024,
                        1024 * 1024
                )
        );
    }

    // Các phương thức cấu hình root context, servlet context
    // và servlet mapping được khai báo theo ứng dụng.
}
~~~

Ví dụ trên dùng namespace **jakarta.servlet**, phù hợp với ứng dụng trên nền Jakarta Servlet. Nếu dự án đang dùng Spring Framework và Servlet API thế hệ cũ, hãy dùng package **javax.servlet** tương ứng. Không trộn hai namespace trong cùng một ứng dụng.

Bốn tham số của **MultipartConfigElement** lần lượt là:

| Tham số | Giá trị ví dụ | Ý nghĩa |
|---|---:|---|
| Location | Thư mục tạm của hệ điều hành | Nơi container có thể ghi các part tạm. Nên chọn thư mục riêng, có quyền ghi và không nằm trong web root công khai. |
| Max file size | 10 MiB | Giới hạn kích thước của một file part. |
| Max request size | 12 MiB | Giới hạn tổng kích thước của toàn bộ multipart request, gồm các part và phần overhead. |
| File size threshold | 1 MiB | Ngưỡng để container quyết định giữ dữ liệu part trong bộ nhớ hay ghi ra vùng lưu tạm. Đây không phải giới hạn tối đa của file. |

Trong ứng dụng Spring Boot, có thể khai báo các giới hạn tương ứng bằng cấu hình:

~~~properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=12MB
spring.servlet.multipart.file-size-threshold=1MB
spring.servlet.multipart.location=/var/tmp/booking-uploads
~~~

Spring Boot tự cấu hình hạ tầng multipart theo các thuộc tính này trong trường hợp cấu hình mặc định. Không cần tạo thêm một resolver thủ công nếu ứng dụng đã dùng cấu hình tự động và không có yêu cầu tùy biến.

Hãy chọn giới hạn dựa trên loại tài liệu, lưu lượng đồng thời và dung lượng đĩa tạm. Ví dụ, nếu cho phép một file tối đa 10 MiB và form có thêm các trường văn bản, **max-request-size** phải lớn hơn giới hạn một file một khoảng hợp lý. Nếu form cho phép nhiều file, giới hạn request phải đủ cho tổng kích thước các file cùng những part khác.

Giới hạn ở Servlet container chưa phải toàn bộ hệ thống. Reverse proxy, API gateway, nền tảng hosting hoặc bộ cân bằng tải có thể có giới hạn request riêng. Hãy đồng bộ các giới hạn đó và kiểm tra dung lượng thư mục tạm để tránh lỗi khi nhiều người tải tệp đồng thời.

## 3. Liên kết trường file với form model

Tạo một đối tượng biểu mẫu có thuộc tính nhận tệp. Ví dụ:

~~~java
import org.springframework.web.multipart.MultipartFile;

public class DocumentUploadForm {

    private String description;
    private MultipartFile file;

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public MultipartFile getFile() {
        return file;
    }

    public void setFile(MultipartFile file) {
        this.file = file;
    }
}
~~~

**MultipartFile** đại diện cho nội dung file đã được Spring phân tích từ request. Nó cung cấp các thông tin như tên file gốc, content type, kích thước và luồng đọc nội dung. Đối tượng này phù hợp để xử lý trong request upload hiện tại.

View JSP có thể gửi file và event upload như sau:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<h1>Tải tài liệu lên</h1>

<form:form modelAttribute="uploadForm"
           action="${flowExecutionUrl}"
           method="post"
           enctype="multipart/form-data">

    <label for="description">Mô tả</label>
    <form:input id="description" path="description"/>

    <label for="file">Chọn tài liệu</label>
    <input id="file"
           type="file"
           name="file"
           accept=".pdf,.png,.jpg,.jpeg"/>

    <button type="submit"
            name="_eventId_upload"
            value="upload">Tải lên</button>
</form:form>
~~~

Các điểm cần chú ý:

- **enctype="multipart/form-data"** yêu cầu trình duyệt gửi nội dung file dưới dạng multipart.
- **name="file"** phải trùng với thuộc tính **file** của form model để data binding nhận đúng part.
- **action="${flowExecutionUrl}"** gửi request đến URL của flow execution hiện tại.
- **_eventId_upload** gửi event **upload** để transition trong state xử lý tệp.

Thuộc tính **accept** chỉ hỗ trợ giao diện chọn file của trình duyệt. Nó không phải cơ chế bảo vệ và không ngăn request gửi tệp có định dạng khác. Máy chủ vẫn phải xác minh nội dung thực tế.

Nếu ứng dụng bật Spring Security CSRF, biểu mẫu phải gửi CSRF token theo cấu hình bảo mật hiện hành. Việc upload cũng cần kiểm tra quyền của người dùng đối với quy trình và tài liệu đích.

## 4. Xử lý tệp ngay trong transition

Một flow có thể nhận file ở state **upload**, chuyển sang màn hình rà soát sau khi lưu tệp tạm. Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="uploadForm"
         class="com.example.documents.DocumentUploadForm"/>

    <view-state id="upload"
                view="documents/upload"
                model="uploadForm">

        <transition on="upload" to="review">
            <evaluate
                expression="documentService.stage(
                    flowScope.uploadForm.file,
                    flowScope.uploadForm.description)"
                result="flowScope.stagedDocument"/>

            <set name="flowScope.uploadForm.file" value="null"/>
        </transition>

        <transition on="cancel" to="cancelled">
            <evaluate expression="documentService.discard(
                flowScope.stagedDocument)"/>
        </transition>
    </view-state>

    <view-state id="review" view="documents/review">
        <transition on="confirm" to="completed">
            <evaluate expression="documentService.confirm(
                flowScope.stagedDocument)"/>
        </transition>

        <transition on="cancel" to="cancelled">
            <evaluate expression="documentService.discard(
                flowScope.stagedDocument)"/>
        </transition>
    </view-state>

    <end-state id="completed" view="documents/completed"/>
    <end-state id="cancelled" view="documents/cancelled"/>
</flow>
~~~

Trong ví dụ, **documentService.stage(...)** đọc nội dung **MultipartFile** ngay trong request gửi event upload và lưu tệp vào vùng lưu trữ tạm. Dịch vụ trả về một đối tượng mô tả tệp đã lưu, được giữ trong **flowScope.stagedDocument**. Sau khi lưu thành công, thuộc tính file trong form model được đặt lại thành null để flow không tiếp tục giữ tham chiếu đến đối tượng multipart của request.

Đối tượng **stagedDocument** chỉ nên chứa dữ liệu cần cho các bước sau, chẳng hạn:

- Mã tham chiếu hoặc storage key của tệp tạm.
- Tên file đã được chuẩn hóa để hiển thị.
- Kích thước và loại nội dung đã xác minh.
- Checksum hoặc mã phiên bản nếu cần đối chiếu.
- Trạng thái xử lý, ví dụ đang chờ xác nhận hoặc đã quét an toàn.

Khi người dùng xác nhận, **documentService.confirm(...)** chuyển tệp tạm sang trạng thái lưu trữ chính thức hoặc gắn nó với hồ sơ nghiệp vụ. Khi người dùng hủy, **documentService.discard(...)** xóa tệp tạm và metadata liên quan.

Trong ứng dụng thực tế, hãy xử lý cả trường hợp dịch vụ lưu tệp thất bại giữa chừng. Dịch vụ nên đóng stream trong mọi nhánh, xóa đối tượng lưu tạm nếu thao tác không hoàn tất và trả lỗi phù hợp cho flow. Nếu flow có thể kết thúc do timeout hoặc lỗi hệ thống mà không đi qua transition cancel, vùng lưu trữ tạm cần TTL hoặc cơ chế dọn dẹp định kỳ để thu hồi các tệp mồ côi.

## 5. Giới hạn dữ liệu được giữ trong flow

Điểm quan trọng nhất là phân biệt nội dung tệp với thông tin tham chiếu đến tệp.

**Không nên giữ các dữ liệu sau trong flow scope lâu dài:**

- Đối tượng **MultipartFile** sau khi request upload kết thúc.
- Mảng byte lớn như **byte[]** chứa toàn bộ tệp.
- Chuỗi Base64 của nội dung file.
- Stream đang mở, request object hoặc đối tượng phụ thuộc vào tài nguyên tạm của container.

Những dữ liệu này có thể làm flow execution phình to, tốn bộ nhớ và khiến việc lưu snapshot/khôi phục execution trở nên khó khăn. Một số đối tượng còn gắn với vòng đời của request, nên không thể dựa vào chúng ở request tiếp theo.

Thay vào đó, hãy lưu nội dung tệp trong vùng lưu trữ phù hợp và giữ một tham chiếu nhỏ trong flow:

~~~java
public class StagedDocument {

    private String storageKey;
    private String displayName;
    private String contentType;
    private long size;
    private String checksum;
    private String status;

    // Constructors, getters và setters
}
~~~

Dịch vụ lưu tệp nên đọc theo stream thay vì gọi **getBytes()** cho các file lớn:

~~~java
public StagedDocument stage(
        MultipartFile file,
        String description) throws IOException {

    if (file == null || file.isEmpty()) {
        throw new IllegalArgumentException("Vui lòng chọn tệp");
    }

    // Kiểm tra giới hạn nghiệp vụ trước khi lưu.
    // Tạo storage key ngẫu nhiên, không dùng tên file làm đường dẫn.
    // Sao chép file.getInputStream() vào vùng lưu trữ tạm theo stream.
    // Đóng stream và trả về metadata cùng storage key.
    return temporaryDocumentStorage.store(file, description);
}
~~~

Phần **temporaryDocumentStorage.store(...)** là dịch vụ hạ tầng của ứng dụng. Nó cần đảm bảo stream được đóng đúng cách, tệp được ghi hoàn chỉnh và đối tượng dở dang được dọn khi có lỗi. Ví dụ trên minh họa cấu trúc xử lý; phần lưu trữ cụ thể phụ thuộc việc ứng dụng dùng filesystem riêng, object storage hay dịch vụ tài liệu.

Giới hạn payload của flow repository là một vấn đề riêng với giới hạn multipart request. Một request có thể hợp lệ ở tầng upload nhưng vẫn làm flow state quá lớn nếu ứng dụng lưu cả nội dung file vào scope. Ngược lại, giữ một storage key ngắn trong flow không làm thay đổi kích thước file đã tải lên. Vì vậy, cần kiểm tra độc lập giới hạn upload và kích thước dữ liệu flow được lưu.

## 6. Kiểm tra kích thước và loại nội dung

Không nên chỉ dựa vào tên phần mở rộng hoặc content type do trình duyệt gửi. Các giá trị đó có thể bị giả mạo. Một quy trình kiểm tra thực tế thường gồm:

1. Kiểm tra part có tồn tại và không rỗng.
2. Kiểm tra kích thước theo giới hạn nghiệp vụ của loại tài liệu.
3. Chuẩn hóa tên file để hiển thị; không dùng trực tiếp tên gốc làm đường dẫn trên filesystem.
4. Xác định định dạng từ nội dung thực tế hoặc chữ ký file (magic bytes), kết hợp allowlist định dạng được hỗ trợ.
5. Quét mã độc hoặc kiểm tra an toàn nội dung theo yêu cầu của hệ thống.
6. Lưu vào vùng tạm riêng tư và chỉ cho phép người dùng có quyền truy cập đọc lại.
7. Chỉ chuyển sang lưu trữ chính thức sau khi flow hoàn tất bước xác nhận.

Ví dụ, hệ thống chỉ cho phép PDF và ảnh JPEG/PNG thì cần kiểm tra nội dung thực tế có thuộc các định dạng đó. Việc form có **accept=".pdf,.png,.jpg"** không thay thế bước kiểm tra trên máy chủ.

Ngoài giới hạn của container, dịch vụ có thể đặt giới hạn nghiệp vụ nhỏ hơn. Chẳng hạn, container chấp nhận file đến 10 MiB nhưng một loại chứng từ cụ thể chỉ được phép tối đa 5 MiB. Dịch vụ phải từ chối file vượt giới hạn nghiệp vụ và trả thông báo có thể hiển thị trong view.

Cũng cần tính đến giới hạn theo người dùng hoặc theo quy trình: tổng dung lượng tài liệu đã tải lên, số file được đính kèm, số request đồng thời và dung lượng còn trống của vùng lưu tạm. Các giới hạn này giúp ngăn một flow đơn lẻ chiếm quá nhiều tài nguyên.

## 7. Xử lý lỗi upload và dọn dẹp

Lỗi multipart có thể xảy ra ở nhiều thời điểm. Nếu file vượt **max-file-size** hoặc toàn request vượt **max-request-size**, Servlet container có thể từ chối request trong quá trình phân tích multipart. Khi đó, transition **upload** chưa chắc đã được thực thi. Ứng dụng cần có exception handling phù hợp ở tầng web để hiển thị thông báo dễ hiểu và cho phép người dùng thử lại.

Các lỗi thường gặp:

| Biểu hiện | Nơi cần kiểm tra |
|---|---|
| Thuộc tính file luôn null | Form thiếu multipart encoding, sai tên field, hoặc multipart resolver chưa được đăng ký đúng context. |
| Request bị từ chối trước khi vào flow | File/request vượt giới hạn của Servlet container, reverse proxy hoặc gateway. |
| Upload thành công nhưng bước sau không tìm thấy file | Chỉ giữ MultipartFile hoặc file tạm của request thay vì storage key bền vững. |
| Flow state tăng kích thước sau upload | Lưu byte array, Base64 hoặc đối tượng file vào flow scope. |
| Người dùng hủy nhưng tệp tạm còn lại | Transition hủy chưa gọi dịch vụ dọn dẹp hoặc luồng timeout không được thu hồi. |
| Nhiều file cùng ghi đè | Dùng tên file gốc làm tên lưu trữ thay vì storage key duy nhất. |
| Tệp có phần mở rộng hợp lệ nhưng nội dung nguy hiểm | Chỉ kiểm tra tên file hoặc content type do client gửi. |

Một vùng lưu tạm nên có thời hạn sống rõ ràng. Mỗi đối tượng tạm cần được gắn với flow hoặc hồ sơ sở hữu để chỉ đúng người có quyền mới có thể xác nhận, tải xuống hoặc xóa. Khi flow kết thúc thành công, dịch vụ đánh dấu tệp đã được gắn với nghiệp vụ. Khi hủy, dịch vụ xóa tệp tạm. Với flow bị bỏ dở hoặc session hết hạn, một tác vụ dọn dẹp dựa trên TTL sẽ thu hồi những tệp không còn được tham chiếu.

Không nên xóa một tệp chỉ dựa vào storage key do client gửi lên. Hãy lấy key từ dữ liệu flow đã được máy chủ quản lý, đồng thời xác minh quyền sở hữu trước khi xóa hoặc xác nhận.

## 8. Kiểm thử upload và giới hạn flow

Một bộ kiểm thử tốt cần xác nhận cả request multipart, binding, lưu trữ và trạng thái của flow execution.

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Tải file hợp lệ dưới giới hạn | Event upload được nhận, dịch vụ lưu tệp tạm được gọi và flow chỉ giữ metadata/tham chiếu. |
| File rỗng hoặc không chọn file | Người dùng nhận thông báo; không tạo đối tượng lưu trữ tạm. |
| File vượt giới hạn từng file | Request bị từ chối theo cấu hình và ứng dụng hiển thị lỗi phù hợp. |
| Tổng multipart vượt giới hạn request | Container từ chối request; không tạo trạng thái flow giả như upload thành công. |
| Định dạng không nằm trong allowlist | Dịch vụ từ chối file và xóa dữ liệu tạm đã tạo nếu có. |
| Người dùng xác nhận | Tệp tạm được gắn vào hồ sơ hoặc chuyển sang lưu trữ chính thức đúng một lần. |
| Người dùng hủy | Tệp tạm được xóa hoặc đánh dấu chờ dọn theo chính sách. |
| Flow hết hạn | Tác vụ dọn dẹp thu hồi tệp không còn được tham chiếu. |
| Hai flow upload đồng thời | Storage key và dữ liệu của mỗi flow độc lập, không ghi đè lẫn nhau. |

Trong kiểm thử Spring MVC, có thể dùng **MockMvc multipart request builder** để tạo request có file part. Cần giữ cùng session và URL execution khi mô phỏng các bước tiếp theo của flow. Ngoài kiểm thử trong ứng dụng, nên có kiểm thử tích hợp trên Servlet container thực tế để xác nhận giới hạn multipart được áp dụng đúng, vì giới hạn này do container thực thi.

Khi xác nhận flow không giữ payload lớn, hãy kiểm tra đối tượng lưu trong flow chỉ gồm metadata và storage key. Kiểm tra cả trường hợp lỗi giữa chừng để chắc chắn không còn file tạm bị bỏ quên và không có transition nào đánh dấu thành công khi tệp chưa được lưu đầy đủ.

## 9. Nguyên tắc thiết kế lâu dài

Hãy để Servlet container và multipart resolver chịu trách nhiệm phân tích request, để dịch vụ tài liệu chịu trách nhiệm kiểm tra và lưu nội dung, còn Spring Web Flow điều phối các bước upload, rà soát, xác nhận và hủy.

Xử lý **MultipartFile** trong request upload hiện tại, lưu nội dung vào vùng lưu trữ riêng và xóa tham chiếu file khỏi form model sau khi xử lý. Flow chỉ giữ storage key, metadata và trạng thái nghiệp vụ cần thiết. Đặt giới hạn ở cả cấp file, cấp request, cấp người dùng và cấp hạ tầng; có cơ chế dọn dẹp cho những quy trình bị bỏ dở.

Cách tổ chức này giữ cho flow execution gọn nhẹ và dễ khôi phục, trong khi nội dung tệp vẫn được quản lý theo vòng đời lưu trữ riêng. Khi hành trình cần thêm bước quét an toàn, phê duyệt hoặc thay thế tệp, bạn có thể bổ sung state và event tương ứng mà không phải đưa toàn bộ nội dung file vào trạng thái của flow.
