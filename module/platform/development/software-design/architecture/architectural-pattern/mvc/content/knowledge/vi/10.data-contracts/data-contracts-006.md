# Giới hạn trường được phép nhận từ người dùng

Trong ứng dụng MVC, dữ liệu từ trình duyệt hoặc API client là dữ liệu không đáng tin cậy, kể cả khi giao diện chỉ hiển thị một số trường nhất định. Người dùng có thể sửa HTML, gọi endpoint trực tiếp hoặc gửi thêm thuộc tính mà biểu mẫu không cung cấp. Vì vậy, Controller cần xác định rõ **trường nào endpoint được phép nhận**, sau đó chuyển dữ liệu đó thành command có phạm vi phù hợp để application service và Model xử lý.

Việc giới hạn trường đầu vào giúp tránh lỗi *mass assignment* (còn gọi là over-posting): client gửi thêm thuộc tính nhạy cảm để cố thay đổi dữ liệu mà chức năng không định cho phép, chẳng hạn `ownerId`, `role`, `approved`, `balance` hoặc `status`. Nguyên tắc cơ bản là chỉ nhận những trường cần thiết cho hành động cụ thể; các giá trị do hệ thống quản lý phải được lấy từ ngữ cảnh đã xác thực hoặc được xác định bởi nghiệp vụ phía máy chủ.

## Vì sao không nên bind toàn bộ request vào Model?

Giả sử trang sửa công việc chỉ hiển thị hai trường `title` và `description`. Entity trong ứng dụng còn có các thuộc tính `ownerId`, `status`, `approved` và `createdAt`. Nếu Controller bind trực tiếp request vào entity, client có thể gửi thêm các trường này dù chúng không xuất hiện trong biểu mẫu.

Ví dụ request hợp lệ theo giao diện:

```http
POST /tasks/42
Content-Type: application/x-www-form-urlencoded

title=Hoan+thanh+tai+lieu&description=Cap+nhat+noi+dung
```

Nhưng client có thể tự gửi request mở rộng:

```http
POST /tasks/42
Content-Type: application/x-www-form-urlencoded

title=Hoan+thanh+tai+lieu&description=Cap+nhat+noi+dung&ownerId=1&approved=true&status=COMPLETED
```

Nếu cơ chế binding hoặc sao chép thuộc tính chấp nhận mọi trường tương ứng, dữ liệu nhạy cảm có thể bị ghi đè. Việc ẩn trường trên HTML không ngăn được request giả mạo; trường `hidden` cũng do client kiểm soát và không phải bằng chứng đáng tin cậy.

### Mass assignment xảy ra như thế nào?

Mass assignment xuất hiện khi ứng dụng ánh xạ một tập thuộc tính do client kiểm soát vào đối tượng có nhiều thuộc tính hơn phạm vi mà endpoint định cho phép. Rủi ro thường đến từ:

- bind trực tiếp request vào entity hoặc đối tượng persistence;
- dùng setter công khai cho các thuộc tính nhạy cảm;
- sao chép tất cả thuộc tính bằng reflection hoặc tiện ích như `BeanUtils.copyProperties` mà không có allowlist;
- nhận `Map<String, Object>` hoặc JSON tùy ý rồi cập nhật đối tượng theo tên thuộc tính;
- cho phép đường dẫn thuộc tính lồng nhau hoặc chỉ số collection mà không giới hạn;
- dùng chung một DTO cho nhiều thao tác có quyền cập nhật khác nhau.

Hậu quả có thể là người dùng tự đổi chủ sở hữu, trạng thái phê duyệt, vai trò hoặc dữ liệu tài chính. Đây là vấn đề kiểm soát dữ liệu đầu vào và quyền ghi; nó có thể dẫn đến leo thang đặc quyền hoặc sửa dữ liệu trái phép.

## Nguyên tắc allowlist: khai báo rõ trường được nhận

Với mỗi endpoint, hãy xác định một danh sách cho phép (allowlist) gồm những trường cần thiết cho hành động. Các trường không có trong danh sách không được dùng để cập nhật trạng thái.

Ví dụ, chức năng sửa thông tin công việc có thể nhận:

| Trường | Được nhận? | Nguồn giá trị đáng tin cậy / xử lý |
|---|---|---|
| `title` | Có | Request; kiểm tra độ dài và nội dung |
| `description` | Có | Request; giới hạn kích thước và mã hóa khi hiển thị |
| `dueDate` | Có, nếu chức năng hỗ trợ | Request; parse và kiểm tra quy tắc ngày |
| `ownerId` | Không trong form sửa thông thường | Xác định từ nghiệp vụ hoặc một use case chuyển giao riêng |
| `status` | Không trong form sửa thông thường | Thay đổi qua hành động nghiệp vụ riêng như hoàn thành hoặc hủy |
| `approved` | Không | Quy trình phê duyệt có quyền riêng |
| `createdAt` | Không | Máy chủ và hệ thống lưu trữ quản lý |
| `role` | Không | Quản trị người dùng với kiểm tra quyền riêng |

Allowlist cần được xác định theo từng use case, không chỉ theo entity. Cùng một đối tượng có thể có nhiều hành động: người dùng được sửa tiêu đề, quản lý được giao việc, còn người phê duyệt được thay đổi trạng thái duyệt. Không nên tạo một DTO “cập nhật tất cả” rồi dùng cho mọi endpoint.

## Dùng Request DTO hoặc Form Object riêng

Cách dễ kiểm soát nhất trong MVC là tạo DTO đầu vào chỉ chứa các trường mà endpoint được phép nhận. DTO là hợp đồng giao tiếp ở ranh giới web; nó không phải entity miền và không nên chứa mọi thuộc tính của đối tượng lưu trữ.

Ví dụ với Java:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateTaskRequest(
        @NotBlank @Size(max = 120) String title,
        @Size(max = 2000) String description) {
}
```

Controller chuyển DTO thành command có phạm vi rõ ràng:

```java
@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final UpdateTaskUseCase updateTask;

    public TaskController(UpdateTaskUseCase updateTask) {
        this.updateTask = updateTask;
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable long id,
            @Valid @RequestBody UpdateTaskRequest request,
            Principal principal) {

        updateTask.handle(new UpdateTaskCommand(
                new TaskId(id),
                request.title(),
                request.description(),
                principal.getName()));

        return ResponseEntity.noContent().build();
    }
}
```

`UpdateTaskRequest` không có `ownerId`, `status`, `approved` hay `createdAt`, nên các thuộc tính đó không thể được ánh xạ từ JSON qua DTO này. Controller lấy danh tính từ `Principal`; use case kiểm tra người đó có quyền sửa công việc và áp dụng quy tắc miền trước khi lưu.

Tách `UpdateTaskRequest`, `UpdateTaskCommand` và `Task` giúp phân biệt ba hợp đồng: dữ liệu client gửi, yêu cầu ứng dụng cần thực hiện và trạng thái miền. Trong ứng dụng nhỏ, DTO và command có thể có cấu trúc giống nhau, nhưng vẫn nên giữ ranh giới nếu nó bảo vệ quyền ghi hoặc ngăn phụ thuộc framework.

### Không dùng response DTO làm request DTO

Response thường chứa nhiều trường hơn request, ví dụ `id`, `ownerName`, `statusLabel`, `createdAt` hoặc `canEdit`. Nếu dùng lại response DTO cho thao tác cập nhật, client có thể gửi lại các trường chỉ có ý nghĩa hiển thị hoặc do máy chủ quản lý.

Hãy thiết kế hai chiều riêng:

```java
public record TaskResponse(
        long id,
        String title,
        String description,
        String status,
        String ownerName,
        Instant createdAt) {
}

public record UpdateTaskRequest(
        @NotBlank @Size(max = 120) String title,
        @Size(max = 2000) String description) {
}
```

Response có thể cung cấp dữ liệu để hiển thị; request chỉ chứa dữ liệu người dùng được phép thay đổi qua endpoint đó. Không nên dựa vào annotation ẩn trường trên giao diện để thay thế việc tách DTO.

## Giới hạn binding trong Spring MVC

Khi dùng `@ModelAttribute`, Spring MVC có thể bind request parameter vào thuộc tính của đối tượng. Nếu một form object có nhiều thuộc tính có setter, hãy giới hạn trường được phép bind. `WebDataBinder#setAllowedFields` hỗ trợ khai báo allowlist cho binding.

```java
@Controller
@RequestMapping("/tasks")
public class TaskFormController {

    @InitBinder("form")
    void configureFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("title", "description", "dueDate");
    }

    @PostMapping("/{id}/edit")
    public String update(
            @PathVariable long id,
            @Valid @ModelAttribute("form") UpdateTaskForm form,
            BindingResult errors,
            Principal principal) {

        if (errors.hasErrors()) {
            return "tasks/edit";
        }

        taskService.update(
                new TaskId(id), form.getTitle(), form.getDescription(),
                form.getDueDate(), principal.getName());
        return "redirect:/tasks/" + id;
    }
}
```

Tên trong `@InitBinder("form")` phải khớp với tên model attribute. Các trường không nằm trong allowlist sẽ bị chặn khỏi quá trình binding. Đây là lớp bảo vệ bổ sung cho form object; DTO riêng với ít trường được phép vẫn là thiết kế quan trọng.

Nếu cần phát hiện client đã gửi trường bị chặn, `BindingResult` cung cấp `getSuppressedFields()`. Ứng dụng có thể ghi log sự kiện phù hợp hoặc trả lỗi theo chính sách API. Không ghi giá trị nhạy cảm của trường vào log. Việc trường bị suppressed không tự động chứng minh có hành vi tấn công, vì client có thể gửi dữ liệu thừa do lỗi tích hợp.

```java
String[] suppressed = errors.getSuppressedFields();
if (suppressed.length > 0) {
    // Ghi nhận tên trường bị chặn theo chính sách logging của ứng dụng.
}
```

Với form phức tạp, hãy kiểm soát cả đường dẫn lồng nhau và collection. Không cho phép binding tùy ý như `user.roles[0].name` hoặc `task.owner.permissions` nếu endpoint không có use case cụ thể cho những thay đổi đó. Danh sách cho phép nên nêu đúng đường dẫn cần thiết, tránh wildcard rộng.

## Giới hạn trường khi nhận JSON

Với `@RequestBody`, framework thường dùng Jackson hoặc message converter tương ứng để giải mã JSON thành DTO. DTO chỉ chứa thuộc tính được phép là biện pháp chính:

```java
public record ChangeTaskTitleRequest(
        @NotBlank @Size(max = 120) String title) {
}
```

Endpoint đổi tiêu đề chỉ nhận `title`:

```java
@PatchMapping("/{id}/title")
public ResponseEntity<Void> changeTitle(
        @PathVariable long id,
        @Valid @RequestBody ChangeTaskTitleRequest request,
        Principal principal) {

    taskService.changeTitle(
            new TaskId(id), request.title(), principal.getName());
    return ResponseEntity.noContent().build();
}
```

Nếu client gửi thêm `ownerId` hoặc `approved`, những thuộc tính này không thuộc request DTO. Tùy cấu hình JSON, thư viện có thể bỏ qua hoặc báo lỗi với thuộc tính không được khai báo. Hãy chọn và kiểm thử chính sách nhất quán: báo lỗi cho trường không biết giúp phát hiện client gửi sai hợp đồng; bỏ qua có thể hữu ích cho tương thích phiên bản nhưng cần tránh tạo cảm giác rằng trường đó đã được áp dụng. Dù chọn cách nào, không được sao chép các trường lạ vào entity.

Một số annotation Jackson có thể điều chỉnh quyền đọc/ghi thuộc tính, chẳng hạn `@JsonProperty(access = READ_ONLY)`. Chúng hữu ích cho serialization contract trong trường hợp phù hợp, nhưng không nên dùng entity làm request object rồi trông chờ annotation bảo vệ mọi endpoint. DTO đầu vào riêng vẫn dễ review và ít phụ thuộc vào cấu hình serializer hơn.

## Các trường do máy chủ quản lý

Một số trường phải được xác định từ nguồn tin cậy phía máy chủ thay vì lấy từ request:

| Trường | Nguồn phù hợp |
|---|---|
| `ownerId` hoặc `createdBy` | Danh tính đã xác thực hoặc quy tắc chuyển giao được phép |
| `createdAt`, `updatedAt` | Đồng hồ và cơ chế lưu trữ phía máy chủ |
| `role`, `permissions` | Quy trình quản trị và chính sách phân quyền |
| `approvedBy`, `approvedAt` | Người phê duyệt đã xác thực và thời điểm máy chủ |
| `balance`, `totalPrice` | Quy tắc tính toán và giao dịch phía máy chủ |
| `status` | Hành động nghiệp vụ cụ thể, không phải setter tùy ý từ form |

Ví dụ, khi tạo công việc, service có thể nhận người tạo từ danh tính đã xác thực:

```java
public TaskId create(CreateTaskCommand command, UserId actorId) {
    User actor = userRepository.findById(actorId)
            .orElseThrow(UserNotFoundException::new);

    Task task = Task.create(taskIdGenerator.nextId(), command.title(), actor.id());
    taskRepository.save(task);
    return task.id();
}
```

Client không gửi `createdBy` trong `CreateTaskRequest`. Controller hoặc lớp xác thực lấy `actorId` từ principal đã được xác minh rồi truyền vào use case. Service vẫn kiểm tra actor có quyền tạo công việc trong phạm vi tương ứng.

## Allowlist không thay thế phân quyền

Giới hạn trường chỉ trả lời câu hỏi “endpoint này nhận những thuộc tính nào?”. Nó không trả lời “người dùng này có được thay đổi tài nguyên này không?”. Một request chỉ chứa `title` vẫn có thể cố sửa công việc thuộc người khác bằng cách thay `id` trong URL.

Vì vậy, cần kiểm tra riêng:

- **Quyền trên endpoint:** người dùng có được gọi chức năng này không?
- **Quyền trên đối tượng:** người dùng có được xem hoặc sửa đúng công việc có ID trong URL không?
- **Quyền trên trường:** người dùng có được thay đổi trường cụ thể trong ngữ cảnh này không?
- **Quy tắc trạng thái:** đối tượng có đang ở trạng thái cho phép hành động không?

Ví dụ, người dùng thường có thể sửa `title` và `description`, trưởng nhóm có thể thay đổi `assigneeId` qua một use case giao việc riêng, còn người có quyền phê duyệt mới được gọi endpoint phê duyệt. Không nên thêm tất cả các trường vào một DTO chung rồi chỉ ẩn nút trên View.

## PUT, PATCH và ý nghĩa của trường bị thiếu

Giới hạn trường cần đi cùng hợp đồng cập nhật rõ ràng:

- **PUT:** thường biểu diễn thay thế toàn bộ biểu diễn của tài nguyên theo hợp đồng endpoint. Nếu một trường bắt buộc bị thiếu, server cần xử lý theo quy ước thay thế đã công bố.
- **PATCH:** biểu diễn thay đổi một phần. Cần định nghĩa trường bị thiếu nghĩa là giữ nguyên, còn trường có `null` nghĩa là xóa giá trị hay bị từ chối.

Với PATCH, không nên dùng một DTO mà mọi trường `null` đều bị hiểu là “không thay đổi” nếu client cần khả năng chủ động đặt một trường thành `null`. Cần một kiểu biểu diễn có trạng thái hiện diện (present/absent), wrapper phù hợp hoặc một định dạng patch được quy định rõ. Hãy chỉ cho phép các đường dẫn thuộc tính nằm trong allowlist và từ chối thao tác vào trường nhạy cảm.

Ví dụ, endpoint `PATCH /tasks/42/title` chỉ nhận một trường `title`, có hợp đồng đơn giản hơn một endpoint patch JSON tổng quát cho mọi thuộc tính của entity. Endpoint hẹp giúp dễ kiểm tra quyền, validation và kiểm thử.

## Kiểm soát collection và đối tượng lồng nhau

Các request lồng nhau có thể mở rộng phạm vi ghi ngoài dự kiến. Ví dụ:

```json
{
  "title": "Cập nhật tài liệu",
  "assignee": {
    "id": 7,
    "roles": ["ADMIN"]
  },
  "comments": [
    { "id": 91, "approved": true }
  ]
}
```

Nếu endpoint chỉ nhằm đổi tiêu đề, không nên nhận toàn bộ graph này. Nếu chức năng thực sự cần thay đổi người phụ trách, hãy định nghĩa request riêng chỉ nhận `assigneeId`, kiểm tra quyền giao việc và tải người nhận từ hệ thống. Nếu chức năng thêm bình luận, hãy dùng endpoint và DTO riêng; quyền duyệt bình luận cần một use case khác.

Đối với collection, hãy giới hạn số phần tử, kiểm tra từng phần tử và xác định thao tác được phép: thêm, xóa, sắp xếp hay thay thế toàn bộ. Không tin ID con trong payload chứng minh rằng đối tượng con thuộc về đối tượng cha. Repository hoặc dịch vụ cần xác minh quan hệ đó trước khi thay đổi.

## Những cách làm cần tránh

- **Bind trực tiếp entity:** tạo điều kiện để request ghi vào trường không dành cho người dùng.
- **Dùng DTO quá rộng:** DTO có tất cả thuộc tính của entity làm mờ phạm vi quyền ghi.
- **Dùng chung request và response:** trường chỉ đọc trong response vô tình trở thành đầu vào cập nhật.
- **Sao chép tất cả thuộc tính:** `copyProperties` hoặc reflection không có allowlist có thể ghi đè trường nhạy cảm.
- **Nhận map tùy ý:** key do client kiểm soát có thể trở thành tên thuộc tính để cập nhật.
- **Dựa vào hidden input hoặc disabled field:** client có thể sửa hoặc gửi lại các giá trị đó.
- **Dựa vào annotation ở View:** ẩn trường không phải kiểm soát ở phía máy chủ.
- **Coi allowlist là authorization:** trường hợp lệ vẫn có thể được gửi bởi người không có quyền trên tài nguyên.
- **Cho phép patch đường dẫn tùy ý:** JSON Patch hoặc cơ chế cập nhật tương tự cần giới hạn operation và path, đặc biệt với thuộc tính lồng nhau.

## Kiểm thử allowlist và chống mass assignment

Kiểm thử cần chứng minh cả trường được phép hoạt động và trường không được phép không làm thay đổi trạng thái. Với chức năng cập nhật công việc, có thể dùng ma trận sau:

| Request | Kết quả mong đợi |
|---|---|
| Gửi `title` và `description` hợp lệ | Hai trường được cập nhật |
| Gửi thêm `ownerId` | Trường không được cập nhật; request bị từ chối hoặc trường thừa bị bỏ qua theo hợp đồng |
| Gửi `status=COMPLETED` qua endpoint sửa mô tả | Trạng thái không thay đổi |
| Gửi `approved=true` | Không thể tự phê duyệt |
| Thay ID URL sang công việc của người khác | Bị từ chối theo kiểm tra quyền đối tượng |
| Gửi đường dẫn lồng nhau như `owner.roles[0]` | Không được bind nếu không thuộc allowlist |
| Gửi collection vượt giới hạn | Request bị từ chối trước khi xử lý nghiệp vụ |

Ví dụ kiểm thử tích hợp nên đọc lại đối tượng sau request để xác minh `ownerId`, `status` và `approved` không thay đổi. Chỉ kiểm tra response 200 hoặc 400 là chưa đủ; cần kiểm tra trạng thái lưu trữ để phát hiện trường hợp server trả thành công nhưng đã ghi nhầm dữ liệu.

Với Spring MVC, có thể dùng MockMvc để gửi form chứa cả trường được phép và trường bị chặn, sau đó xác minh `BindingResult`, lời gọi service và trạng thái đối tượng. Với JSON endpoint, gửi payload có thuộc tính thừa rồi xác minh chính sách unknown-property và kết quả use case. Bổ sung kiểm thử phân quyền đối tượng để chắc chắn ID trong URL không cho phép truy cập chéo.

## Quy trình xác định trường được phép cho một endpoint

Khi thiết kế hợp đồng đầu vào, hãy thực hiện theo trình tự:

1. **Xác định hành động:** endpoint tạo mới, sửa mô tả, giao việc, phê duyệt hay đổi trạng thái?
2. **Liệt kê trường thực sự cần:** chỉ đưa vào DTO những trường cần để thực hiện hành động đó.
3. **Phân loại nguồn dữ liệu:** trường nào do client cung cấp, trường nào do máy chủ suy ra, trường nào chỉ đọc?
4. **Định nghĩa validation:** kiểu, độ dài, khoảng giá trị, số phần tử và quan hệ giữa các trường.
5. **Định nghĩa quyền:** ai được gọi endpoint, ai được sửa đối tượng và ai được thay đổi từng trường nhạy cảm?
6. **Chuyển thành command:** ánh xạ rõ ràng từ request DTO sang command; tránh sao chép hàng loạt thuộc tính.
7. **Bảo vệ ở Model/service:** quy tắc trạng thái và quyền nghiệp vụ phải được kiểm tra dù use case được gọi từ kênh nào.
8. **Kiểm thử trường thừa:** gửi các thuộc tính nhạy cảm và xác minh chúng không làm thay đổi dữ liệu.

Một hợp đồng dữ liệu an toàn mô tả chính xác những gì người dùng được gửi cho một hành động. Khi DTO có phạm vi hẹp, binding được giới hạn, giá trị do máy chủ quản lý được tạo từ nguồn tin cậy và quyền được kiểm tra độc lập, Controller có thể chuyển request thành command rõ ràng mà không mở rộng ngoài ý muốn quyền ghi của người dùng.
