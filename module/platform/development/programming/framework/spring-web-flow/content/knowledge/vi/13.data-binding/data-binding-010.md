# Kiểm tra quyền truy cập dữ liệu được chỉ định bởi input

Trong chương **Ánh xạ dữ liệu**, bài này hướng dẫn bảo vệ dữ liệu mà người dùng chỉ định qua flow input, URL parameter hoặc trường form trong Spring Web Flow. Một hành trình nhiều bước có thể giữ mã hồ sơ, đơn hàng hoặc tài liệu trong `flowScope`, bind dữ liệu vào form object rồi chuyển qua nhiều state và subflow. Tuy nhiên, việc một mã định danh đã được bind thành công không có nghĩa người gửi được phép đọc hoặc sửa bản ghi đó.

Mục tiêu của module **SPRING_WEB_FLOW** là mô hình hóa hành trình bằng state, event, transition và subflow, đồng thời quản lý form binding, validation, scope và phiên. Quyền truy cập phải được kiểm tra xuyên suốt các bước này, đặc biệt ở nơi dữ liệu được tải hoặc thay đổi.

## 1. Input là dữ liệu đầu vào, không phải bằng chứng về quyền

Giả sử URL mở màn hình chỉnh sửa có dạng `/document/edit?documentId=42`. Flow nhận `documentId`, tải tài liệu vào `flowScope` và hiển thị form. Người dùng có thể thay `42` thành `43`, sửa một hidden field, gửi request trực tiếp hoặc tiếp tục một flow cũ. Nếu ứng dụng chỉ kiểm tra rằng ID có định dạng hợp lệ và bản ghi tồn tại, người dùng có thể truy cập tài liệu thuộc về người khác.

Đây là dạng lỗi thường gọi là **Insecure Direct Object Reference (IDOR)** hoặc thiếu kiểm tra quyền ở cấp đối tượng. Mã định danh chỉ giúp ứng dụng tìm tài nguyên. Nó không chứng minh người đang đăng nhập là chủ sở hữu hoặc có quyền thực hiện hành động.

Phân biệt ba việc:

- **Authentication (xác thực):** xác định người dùng hiện tại là ai.
- **Authorization (phân quyền):** quyết định người dùng đó có được thực hiện hành động cụ thể trên tài nguyên cụ thể hay không.
- **Data binding (ánh xạ dữ liệu):** chuyển dữ liệu từ request vào model hoặc flow input theo quy tắc binding.

Binding thành công và validation dữ liệu hợp lệ không thay thế authorization. Một `documentId` có thể là số hợp lệ, một form có thể vượt qua `@NotBlank`, nhưng người gửi vẫn không có quyền đọc hoặc sửa tài liệu tương ứng.

## 2. Xác định ranh giới tin cậy của từng loại input

Trong một flow, dữ liệu có thể đến từ nhiều nơi:

| Nguồn input | Ví dụ | Cách xem xét |
|---|---|---|
| Flow input khi khởi chạy | `documentId`, `orderId`, `accountId` | Xem như định danh do client cung cấp; kiểm tra quyền trước khi tải dữ liệu. |
| Form field được bind | `title`, `description`, `quantity` | Chỉ bind thuộc tính người dùng được phép thay đổi; kiểm tra quy tắc nghiệp vụ ở server. |
| Hidden field hoặc query parameter | `ownerId`, `tenantId`, `status` | Không tin giá trị để quyết định quyền, chủ sở hữu hoặc trạng thái. |
| Input truyền vào subflow | `documentId`, `caseId` | Subflow vẫn phải kiểm tra quyền theo người dùng hiện tại. |
| Giá trị giữ trong flow scope | `flowScope.documentId` | Có thể được dùng qua nhiều state nhưng vẫn bắt nguồn từ input; không tự trở thành dữ liệu đáng tin cậy. |

Khi dữ liệu đã được lưu trong `flowScope`, nó có vòng đời dài hơn request ban đầu. Điều đó giúp flow tiếp tục qua nhiều bước, nhưng không làm dữ liệu trở nên đáng tin cậy hơn. Người dùng có thể mở nhiều flow, tiếp tục flow sau một khoảng thời gian hoặc gửi lại một request cũ. Mọi thao tác nhạy cảm vẫn cần kiểm tra quyền ở thời điểm thực hiện.

## 3. Khai báo flow input và kiểm tra quyền trước khi hiển thị

Flow có thể khai báo input để nhận mã tài nguyên khi được khởi chạy. Ví dụ dưới đây nhận `documentId`, sau đó gọi service để tải form chỉnh sửa. `currentActor.userId` đại diện cho ID người dùng lấy từ ngữ cảnh xác thực phía server; nó không đến từ request hoặc form.

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="documentId" type="java.lang.Long" required="true"/>

    <on-start>
        <evaluate expression="documentAccessService.loadForEdit(flowScope.documentId, currentActor.userId)"
                  result="flowScope.documentForm"/>
    </on-start>

    <view-state id="editDocument"
                view="document/edit"
                model="documentForm">
        <binder>
            <binding property="title" required="true"/>
            <binding property="description"/>
        </binder>
        <transition on="save" to="saved">
            <evaluate expression="documentAccessService.update(flowScope.documentId, currentActor.userId, flowScope.documentForm)"/>
        </transition>
    </view-state>

    <end-state id="saved" view="document/saved"/>
</flow>
```

`documentId` là flow input, được dùng để tìm tài liệu. Service `loadForEdit` phải xác minh người dùng hiện tại có quyền xem và chỉnh sửa trước khi trả về form. Nếu không có quyền, service từ chối truy cập và flow không hiển thị dữ liệu. `documentForm` chỉ chứa các trường được phép sửa.

Ví dụ dùng `on-start` để kiểm tra ngay khi flow bắt đầu. Nếu ứng dụng tải dữ liệu ở action-state hoặc transition khác, hãy đặt kiểm tra tại nơi tải dữ liệu đó. Điều quan trọng là không render thông tin nhạy cảm trước khi quyền xem đã được xác nhận.

Không dùng một giá trị `userId`, `ownerId` hoặc `tenantId` gửi từ trình duyệt làm danh tính của người đang đăng nhập. Lấy actor từ `SecurityContext` hoặc một bean chuyên cung cấp principal đã xác thực. Các biểu thức bean trong XML phải trỏ đến bean thật trong application context.

## 4. Giới hạn form binding bằng allow-list

View-state có thể dùng phần tử `<binder>` để chỉ rõ thuộc tính nào được phép nhận dữ liệu từ form. Đây là cách giảm nguy cơ mass assignment, trong đó người dùng tự thêm trường vào request để thay đổi các thuộc tính không xuất hiện trên giao diện.

Ví dụ form chỉnh sửa tài liệu chỉ cho phép bind `title` và `description`:

```xml
<view-state id="editDocument"
            view="document/edit"
            model="documentForm">
    <binder>
        <binding property="title" required="true"/>
        <binding property="description"/>
    </binder>
</view-state>
```

Không thêm các thuộc tính sau vào binder nếu người dùng không được quyền thay đổi chúng:

- `ownerId`, `createdBy` hoặc `tenantId` — xác định chủ sở hữu và phạm vi dữ liệu.
- `role`, `permission` hoặc `approvedBy` — xác định quyền và người phê duyệt.
- `status`, `paymentState` hoặc `verified` — biểu diễn trạng thái do quy trình server kiểm soát.
- `price`, `discount` hoặc `totalAmount` — giá trị phải được tính và xác minh ở server.

Binder là một hàng rào ở tầng ánh xạ form. Nó không chứng minh người dùng có quyền truy cập bản ghi, không thay thế kiểm tra quyền trong service và cũng không thay thế validation nghiệp vụ. Nếu model có các thuộc tính lồng nhau hoặc collection, cần rà soát cả đường dẫn property được phép bind và các phần tử có thể được thêm, xóa hoặc thay thế.

## 5. Kiểm tra quyền ở service theo người dùng đã xác thực

Service nên nhận định danh tài nguyên và actor đã xác thực, sau đó truy vấn tài nguyên trong đúng phạm vi quyền. Một cách tốt là kết hợp ID tài nguyên với điều kiện chủ sở hữu hoặc tenant ngay trong truy vấn.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service("documentAccessService")
public class DocumentAccessService {

    private final DocumentRepository documentRepository;
    private final DocumentMapper documentMapper;

    public DocumentAccessService(
            DocumentRepository documentRepository,
            DocumentMapper documentMapper) {
        this.documentRepository = documentRepository;
        this.documentMapper = documentMapper;
    }

    @Transactional(readOnly = true)
    public DocumentForm loadForEdit(Long documentId, String actorId) {
        Document document = documentRepository
                .findByIdAndOwnerId(documentId, actorId)
                .orElseThrow(() -> new AccessDeniedException("Access denied"));

        return documentMapper.toForm(document);
    }

    @Transactional
    public void update(Long documentId, String actorId, DocumentForm form) {
        Document document = documentRepository
                .findByIdAndOwnerId(documentId, actorId)
                .orElseThrow(() -> new AccessDeniedException("Access denied"));

        document.rename(form.getTitle());
        document.updateDescription(form.getDescription());
    }
}
```

`findByIdAndOwnerId` là truy vấn repository minh họa: nó chỉ trả về tài liệu có ID khớp và thuộc về actor hiện tại. Nếu hệ thống có vai trò biên tập viên, quản trị tenant hoặc chia sẻ tài liệu, thay điều kiện owner bằng một chính sách truy cập đầy đủ hơn. Không nên tải bản ghi theo ID rồi giả định rằng người dùng được quyền chỉ vì bản ghi tồn tại.

Kiểm tra lại quyền trong `update` dù `loadForEdit` đã kiểm tra. Quyền có thể thay đổi giữa hai request; flow có thể được tiếp tục sau khi quyền bị thu hồi; hoặc người dùng có thể gửi request save trực tiếp. Mỗi thao tác nhạy cảm phải tự bảo vệ tại ranh giới service/domain.

## 6. Dùng form object thay vì bind trực tiếp entity

Không nên bind request thẳng vào JPA entity hoặc đối tượng domain giàu hành vi. Entity thường chứa nhiều trường mà form không được phép sửa. Một form object nhỏ giúp xác định rõ dữ liệu được nhận và giới hạn bề mặt binding.

Ví dụ:

```java
public class DocumentForm {
    private String title;
    private String description;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }
}
```

Form object không có `ownerId`, `tenantId`, `status` hoặc quyền phê duyệt. Khi nhận dữ liệu, service chỉ chép những thuộc tính đã được cho phép vào domain object sau khi kiểm tra quyền. Với dữ liệu nhạy cảm, không dùng một mapper tự động chép tất cả thuộc tính giữa form và entity mà không có allow-list.

## 7. Xác thực quyền và validation giải quyết hai câu hỏi khác nhau

Validation kiểm tra dữ liệu có đáp ứng yêu cầu về định dạng và quy tắc hay không. Authorization kiểm tra actor có được thực hiện hành động trên tài nguyên hay không.

| Kiểm tra | Ví dụ | Nơi xử lý phù hợp |
|---|---|---|
| Định dạng | `documentId` có phải số hợp lệ? | Flow input conversion hoặc validation. |
| Bắt buộc | `title` không được để trống. | Binder và Bean Validation/validator. |
| Độ dài | `description` không vượt giới hạn. | Validator ở server. |
| Quyền đọc | Actor có thể xem tài liệu này? | Service/policy trước khi trả dữ liệu. |
| Quyền sửa | Actor có quyền sửa tài liệu ở trạng thái hiện tại? | Service/domain khi xử lý command. |
| Quyền chuyển trạng thái | Actor có được duyệt hoặc đóng hồ sơ? | Domain service/policy ở transition tương ứng. |

Không trả về thông tin chi tiết về tài nguyên cho người không có quyền. Tùy chính sách ứng dụng, có thể trả 403 hoặc 404 để tránh tiết lộ bản ghi có tồn tại hay không; cần dùng nhất quán trong API và giao diện.

## 8. Bảo vệ dữ liệu khi truyền vào subflow

Flow cha có thể truyền ID tài nguyên cho subflow qua input mapping:

```xml
<subflow-state id="editDocumentStep" subflow="document-edit">
    <input name="documentId" value="flowScope.documentId"/>
    <transition on="documentSaved" to="review"/>
</subflow-state>
```

Subflow nhận một định danh để thực hiện công việc. Việc flow cha đã kiểm tra quyền trước đó không có nghĩa subflow có thể bỏ qua kiểm tra. Subflow có thể được gọi từ một flow khác hoặc được dùng lại trong ngữ cảnh khác; vì vậy nơi tải hoặc thay đổi tài liệu vẫn phải kiểm tra actor và chính sách truy cập.

Chỉ truyền các input cần thiết cho subflow. Không truyền `ownerId` hoặc quyền từ form cha như một bằng chứng tin cậy. Nếu subflow cần actor hiện tại, lấy từ cùng nguồn xác thực phía server. Nếu dữ liệu được chia sẻ qua `conversationScope`, vẫn phải xem đó là dữ liệu theo vòng đời flow, không phải giấy phép truy cập.

## 9. Kiểm tra quyền ở mọi điểm có thể đọc hoặc thay đổi dữ liệu

Một flow có thể truy cập tài nguyên tại nhiều điểm khác nhau. Rà soát toàn bộ đường đi, không chỉ màn hình đầu tiên:

- Khi khởi chạy flow: kiểm tra quyền trước khi tải dữ liệu vào scope hoặc render view.
- Khi chuyển sang state khác: kiểm tra quyền cho hành động tương ứng, đặc biệt khi quyền phụ thuộc trạng thái tài nguyên.
- Khi gọi subflow: xác minh input và actor tại service của subflow.
- Khi lưu form: kiểm tra lại quyền và các bất biến trong transaction.
- Khi flow được tiếp tục sau một khoảng thời gian: không dựa vào kết quả phân quyền cũ nếu quyền hoặc trạng thái tài nguyên có thể đã thay đổi.
- Khi xử lý event lặp hoặc request trực tiếp: command service phải tự kiểm tra quyền và tính hợp lệ của trạng thái.

Bảo vệ URL flow bằng Spring Security là một lớp quan trọng để xác thực và giới hạn các nhóm người dùng có thể khởi chạy flow. Tuy nhiên, URL authorization thường chỉ kiểm soát quyền truy cập endpoint hoặc nhóm chức năng. Nó không thay thế object-level authorization cho từng `documentId`, `orderId` hoặc `accountId` được gửi vào.

## 10. Xử lý từ chối truy cập an toàn

Khi service xác định actor không có quyền, hãy từ chối thao tác và đưa ứng dụng về một phản hồi an toàn. Không tiếp tục flow với object rỗng hoặc dữ liệu mặc định vì các state sau có thể vô tình hiển thị hoặc ghi dữ liệu sai.

Có thể dùng `AccessDeniedException` hoặc ngoại lệ domain tương ứng để tích hợp với Spring Security. Ở tầng web, cấu hình `AccessDeniedHandler` hoặc exception handling phù hợp với cách ứng dụng điều hướng. Chỉ ánh xạ lỗi sang một view chung khi chính sách yêu cầu; không bắt mọi exception rồi coi như validation error.

Thông báo cho người dùng nên ngắn gọn, chẳng hạn “Bạn không có quyền thực hiện thao tác này” hoặc “Tài nguyên không khả dụng”. Log nội bộ có thể ghi actor ID, resource ID, action và correlation ID theo chính sách bảo mật, nhưng không ghi token, mật khẩu hoặc toàn bộ dữ liệu form. Tránh log các thông tin nhạy cảm mà người dùng không có quyền xem.

## 11. Kiểm thử quyền truy cập dữ liệu được chỉ định bởi input

Kiểm thử cần xác minh cả đường đi hợp lệ lẫn các trường hợp cố tình thay đổi input:

| Tình huống | Kết quả mong đợi |
|---|---|
| Người dùng sở hữu tài liệu mở flow | Flow tải form và hiển thị đúng tài liệu. |
| Người dùng khác thay `documentId` sang tài liệu riêng tư | Service từ chối; dữ liệu không được render. |
| Người dùng gửi thêm `ownerId` trong request | Giá trị không được bind hoặc không ảnh hưởng đến quyết định quyền. |
| Request thêm `status=APPROVED` | Trạng thái không thay đổi vì field không nằm trong allow-list và command không tin request. |
| Người dùng có quyền xem nhưng không có quyền sửa | Màn hình có thể chỉ đọc; event save bị từ chối ở service. |
| Quyền bị thu hồi sau khi flow đã mở | Request save tiếp theo bị kiểm tra lại và từ chối. |
| Subflow nhận ID tài liệu không thuộc actor | Subflow/service từ chối giống như flow chính. |
| Flow execution được tiếp tục sau session hoặc thời gian gián đoạn | Mỗi command nhạy cảm vẫn kiểm tra quyền hiện tại. |
| Gửi event save trực tiếp, bỏ qua giao diện | Service vẫn xác minh actor, tài nguyên và trạng thái. |

Có thể kết hợp các lớp kiểm thử:

1. Unit test cho policy/service với actor sở hữu, actor khác, vai trò quản trị và trường hợp không tìm thấy tài nguyên.
2. Test flow execution để xác nhận input được chuyển vào đúng scope và lỗi quyền không đi tiếp sang view-state.
3. MockMvc/integration test để thay đổi query parameter, hidden field, form field và event request.
4. Kiểm thử repository để bảo đảm truy vấn giới hạn theo tenant hoặc owner, tránh chỉ lọc ở giao diện.
5. Kiểm thử đồng thời hoặc trạng thái thay đổi nếu quyền phụ thuộc vào trạng thái tài nguyên trong transaction.

Không chỉ kiểm tra rằng giao diện ẩn nút Edit. Người dùng có thể tự tạo request; kiểm tra phải chứng minh service từ chối thao tác dù request được gửi trực tiếp.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Tin `documentId` vì nó nằm trong flow scope | ID có thể bắt nguồn từ input do client kiểm soát. | Xác minh actor và quyền ở service mỗi lần truy cập. |
| Dùng `ownerId` từ hidden field | Người dùng có thể giả mạo chủ sở hữu. | Lấy actor từ principal đã xác thực và xác định owner ở server. |
| Bind trực tiếp entity | Request có thể thay đổi field nội bộ hoặc quan hệ. | Dùng form DTO và binder allow-list. |
| Chỉ kiểm tra quyền lúc mở flow | Quyền hoặc trạng thái có thể thay đổi trước khi lưu. | Kiểm tra lại ở command/service khi thực hiện hành động. |
| Chỉ bảo vệ URL flow | Người dùng có thể truy cập ID của tài nguyên khác trong cùng endpoint. | Thêm object-level authorization. |
| Cho subflow tin kết quả kiểm tra của flow cha | Subflow có thể được gọi từ ngữ cảnh khác hoặc tái sử dụng. | Kiểm tra lại input tại service được subflow gọi. |
| Dùng validation thay authorization | Dữ liệu đúng định dạng vẫn có thể thuộc người khác. | Tách kiểm tra dữ liệu và kiểm tra quyền. |

## 13. Checklist bảo vệ input và data binding

- [ ] Xác định rõ input nào đến từ URL, request, form, flow cha hoặc subflow.
- [ ] Coi mọi ID và hidden field từ client là dữ liệu chưa đáng tin cậy.
- [ ] Lấy actor từ principal đã xác thực; không lấy danh tính từ form.
- [ ] Kiểm tra quyền đọc trước khi đưa dữ liệu nhạy cảm vào view hoặc scope.
- [ ] Dùng `<binder>` để chỉ cho phép các thuộc tính form được sửa.
- [ ] Dùng form object thay vì bind trực tiếp entity/domain object.
- [ ] Kiểm tra lại quyền và trạng thái ở mỗi command trong service/domain.
- [ ] Áp dụng chính sách tenant/owner nhất quán trong truy vấn dữ liệu.
- [ ] Subflow kiểm tra quyền độc lập tại ranh giới service.
- [ ] Từ chối truy cập an toàn, không để lộ dữ liệu hoặc chi tiết nội bộ.
- [ ] Kiểm thử thay đổi ID, giả mạo field, event trực tiếp, quyền bị thu hồi và request lặp.

## 14. Kết luận

Flow input và form binding chỉ chuyển dữ liệu vào flow model; chúng không cấp quyền truy cập tài nguyên. Hãy xem ID từ client là định danh cần kiểm tra, dùng binder allow-list để giới hạn field được bind, lấy actor từ principal đã xác thực và đặt object-level authorization trong service/domain cho cả thao tác đọc lẫn ghi. Kiểm tra lại quyền ở các transition, command và subflow giúp hành trình Spring Web Flow nhiều bước bảo vệ dữ liệu nhất quán ngay cả khi người dùng sửa input hoặc tiếp tục một flow cũ.
