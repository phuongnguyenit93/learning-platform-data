# Kiểm tra điều kiện nghiệp vụ trước khi cập nhật

Trong ứng dụng MVC, cập nhật dữ liệu là một thao tác làm thay đổi trạng thái của Model. Trước khi lưu thay đổi, ứng dụng cần xác nhận rằng yêu cầu hợp lệ trong ngữ cảnh nghiệp vụ hiện tại: người thực hiện có quyền hay không, đối tượng có đang ở trạng thái cho phép hay không, dữ liệu liên quan có đáp ứng điều kiện hay không và thay đổi mới có giữ được các bất biến của hệ thống hay không.

Việc kiểm tra này bảo vệ tính nhất quán của dữ liệu và giúp ứng dụng phản hồi rõ ràng khi một thao tác không thể thực hiện. Nó cần được đặt ở phía máy chủ, trong luồng nghiệp vụ phù hợp, vì dữ liệu gửi từ trình duyệt có thể bị sửa đổi và trạng thái trong cơ sở dữ liệu có thể đã thay đổi kể từ lúc người dùng mở màn hình.

## 1. Điều kiện nghiệp vụ là gì?

Điều kiện nghiệp vụ là những quy tắc phải đúng tại thời điểm thực hiện một thao tác. Chúng xuất phát từ cách tổ chức hoạt động của hệ thống, chẳng hạn:

- Đơn hàng chỉ được xác nhận khi đang ở trạng thái chờ xác nhận.
- Người quản lý chỉ được duyệt yêu cầu thuộc phạm vi mình phụ trách.
- Số lượng đặt mua không được vượt quá lượng hàng có thể cung cấp.
- Tài khoản chỉ được rút tiền khi số dư khả dụng đủ đáp ứng giao dịch.
- Một mã đăng ký chỉ được sử dụng một lần.
- Hồ sơ đã khóa không được chỉnh sửa bằng luồng cập nhật thông thường.

Không phải mọi kiểm tra đều cùng một loại. Cần phân biệt chúng để đặt đúng trách nhiệm.

| Loại kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kiểm tra định dạng và dữ liệu đầu vào | Dữ liệu gửi lên có đúng kiểu, đủ trường và nằm trong giới hạn cho phép không? | Tên không rỗng, số lượng là số nguyên dương |
| Điều kiện nghiệp vụ trước thao tác | Với trạng thái hiện tại, thao tác này có được phép không? | Chỉ duyệt yêu cầu đang chờ duyệt |
| Bất biến của Model | Sau khi thay đổi, đối tượng có còn ở trạng thái hợp lệ không? | Số dư không âm, ngày kết thúc không trước ngày bắt đầu |
| Kiểm tra quyền | Người dùng hiện tại có được phép thực hiện thao tác trên đối tượng này không? | Người duyệt thuộc nhóm quản lý hồ sơ |
| Ràng buộc dữ liệu | Cơ sở dữ liệu có thể bảo đảm điều kiện toàn vẹn nào? | Khóa ngoại, giá trị duy nhất, cột bắt buộc |

Kiểm tra định dạng thường bắt đầu ở tầng tiếp nhận request. Điều kiện nghiệp vụ và bất biến cần được bảo vệ trong phần xử lý nghiệp vụ hoặc Model. Kiểm tra quyền phải dựa trên danh tính đã xác thực và dữ liệu phía máy chủ. Ràng buộc cơ sở dữ liệu là lớp bảo vệ cuối cùng cho những điều kiện có thể biểu diễn bằng cấu trúc dữ liệu.

## 2. Đặt việc kiểm tra ở đâu trong MVC?

Một luồng cập nhật thường đi qua các thành phần như sau:

```text
Người dùng gửi yêu cầu cập nhật
              |
              v
Controller nhận request
              |
              v
Kiểm tra dữ liệu đầu vào cơ bản
              |
              v
Service tải Model và dữ liệu liên quan
              |
              v
Kiểm tra quyền và điều kiện nghiệp vụ
              |
              v
Model thực hiện thay đổi hợp lệ
              |
              v
Lưu thay đổi trong transaction
              |
              v
Controller chọn phản hồi
              |
              v
View hiển thị kết quả hoặc lỗi
```

Mỗi thành phần có trách nhiệm riêng:

- **Controller** đọc tham số, nhận dữ liệu biểu mẫu hoặc request body, kiểm tra định dạng cơ bản, lấy danh tính người dùng từ ngữ cảnh xác thực và gọi ca sử dụng phù hợp. Controller không nên tự chứa toàn bộ quy tắc như “đơn hàng nào được hoàn tiền”.
- **Service hoặc lớp xử lý ca sử dụng** điều phối thao tác. Nó tải đối tượng và dữ liệu liên quan, kiểm tra quyền theo ngữ cảnh, gọi quy tắc nghiệp vụ, quản lý transaction và trả kết quả.
- **Model/domain object** bảo vệ các bất biến gắn với chính đối tượng. Thay vì để nhiều nơi tự gán `status = APPROVED`, có thể cung cấp phương thức `approve()` để đối tượng tự xác nhận trạng thái cho phép.
- **Repository hoặc lớp truy cập dữ liệu** tải và lưu đối tượng. Nó không nên trở thành nơi duy nhất chứa mọi quy tắc nghiệp vụ.
- **Cơ sở dữ liệu** bảo vệ các ràng buộc toàn vẹn như khóa ngoại, unique constraint và not-null constraint.

Một số framework MVC cho phép khai báo kiểm tra dữ liệu ngay trên DTO hoặc tham số của Controller. Cách đó hữu ích cho định dạng và giới hạn đầu vào, nhưng không thay thế việc kiểm tra nghiệp vụ bằng dữ liệu mới nhất ở phía máy chủ.

## 3. Quy trình kiểm tra trước khi cập nhật

### 3.1. Xác định chính xác đối tượng cần thay đổi

Tải đối tượng theo mã định danh từ request, đồng thời bảo đảm đối tượng thuộc đúng phạm vi mà người dùng có thể truy cập. Không nên tin các trường như `ownerId`, `createdBy`, `status` hoặc `approved` do trình duyệt gửi lên để quyết định quyền hay trạng thái hiện tại.

Ví dụ, khi cập nhật hồ sơ nghỉ phép, máy chủ cần đọc hồ sơ từ kho dữ liệu và xác định người gửi yêu cầu hiện tại. Nếu hồ sơ không tồn tại, trả kết quả không tìm thấy theo quy ước của ứng dụng. Nếu việc tiết lộ sự tồn tại của hồ sơ là nhạy cảm, có thể dùng truy vấn giới hạn theo phạm vi truy cập để không phân biệt hồ sơ không tồn tại với hồ sơ người dùng không được xem.

### 3.2. Kiểm tra danh tính và quyền thực hiện

Xác thực trả lời câu hỏi “người dùng là ai”; phân quyền trả lời “người dùng này có được thực hiện thao tác này trên đối tượng này không”.

Không suy ra quyền từ một giá trị gửi trong biểu mẫu. Hãy dùng danh tính và vai trò do máy chủ xác thực, sau đó kiểm tra quan hệ với đối tượng, ví dụ người dùng có phải quản lý được phân công hay không.

Ẩn nút “Duyệt” trên View chỉ giúp giao diện dễ sử dụng. Request vẫn có thể được gửi thủ công, vì vậy Controller hoặc service phải kiểm tra quyền ở phía máy chủ trong mọi lần thực hiện thao tác.

### 3.3. Kiểm tra trạng thái hiện tại và chuyển trạng thái được phép

Nhiều thao tác chỉ hợp lệ ở một số trạng thái. Hãy mô tả các chuyển trạng thái được phép thay vì cho phép cập nhật tùy ý một trường trạng thái.

Ví dụ, vòng đời đơn hàng có thể có các chuyển đổi:

| Trạng thái hiện tại | Thao tác | Trạng thái tiếp theo |
|---|---|---|
| `DRAFT` | Gửi đơn | `SUBMITTED` |
| `SUBMITTED` | Xác nhận | `CONFIRMED` |
| `CONFIRMED` | Giao hàng | `SHIPPED` |
| `SHIPPED` | Xác nhận nhận hàng | `COMPLETED` |
| `DRAFT` | Hủy | `CANCELLED` |
| `SUBMITTED` | Hủy | `CANCELLED` |

Một đơn hàng đã hoàn tất không nên quay về trạng thái nháp qua cùng thao tác gửi đơn. Nếu nghiệp vụ cần sửa hoặc hoàn tác, hãy thiết kế một thao tác riêng với điều kiện và quyền tương ứng.

### 3.4. Kiểm tra dữ liệu liên quan và giới hạn

Một đối tượng có thể hợp lệ riêng lẻ nhưng không hợp lệ khi kết hợp với dữ liệu khác. Ví dụ:

- Số lượng đặt hàng phải phù hợp với lượng hàng có thể phân bổ.
- Ngày đặt lịch phải nằm trong khung giờ còn chỗ.
- Một nhân viên chỉ được đăng ký số ngày nghỉ còn lại.
- Một tài khoản không thể thêm thành viên vượt giới hạn gói dịch vụ.

Các dữ liệu liên quan cần được đọc từ nguồn đáng tin cậy và kiểm tra trong cùng phạm vi transaction hoặc cơ chế đồng bộ thích hợp. Nếu quy tắc phụ thuộc vào tổng số bản ghi hoặc tài nguyên có thể bị thay đổi đồng thời, chỉ đọc một giá trị rồi lưu sau đó có thể không đủ an toàn; cần dùng khóa, cập nhật có điều kiện hoặc ràng buộc ở cơ sở dữ liệu.

### 3.5. Bảo vệ bất biến và ràng buộc duy nhất

Bất biến là điều kiện phải luôn đúng đối với Model hợp lệ. Ví dụ, một dòng hóa đơn không được có số lượng âm; khoảng thời gian không được có ngày kết thúc trước ngày bắt đầu; một yêu cầu đã được duyệt không thể được duyệt lần thứ hai.

Với dữ liệu cần duy nhất, chẳng hạn mã nhân viên hoặc tên đăng nhập, kiểm tra trước bằng truy vấn giúp trả thông báo thân thiện. Tuy nhiên, hai request có thể cùng kiểm tra thấy mã chưa tồn tại rồi cùng cố gắng tạo mới. Vì vậy, cơ sở dữ liệu vẫn cần unique constraint và ứng dụng cần xử lý trường hợp vi phạm ràng buộc.

### 3.6. Xem xét dữ liệu có thể đã thay đổi đồng thời

Giả sử hai nhân viên cùng mở một yêu cầu đang ở trạng thái `PENDING`. Người thứ nhất duyệt và lưu thành công. Người thứ hai vẫn có thể đang nhìn thấy màn hình cũ và gửi yêu cầu duyệt. Nếu ứng dụng chỉ dựa vào trạng thái mà người dùng đã tải trước đó, thao tác thứ hai có thể ghi đè kết quả mới.

Một số cách xử lý thường dùng:

- **Optimistic locking:** lưu thêm phiên bản của bản ghi. Khi cập nhật, chỉ thành công nếu phiên bản vẫn là phiên bản đã đọc. Nếu có người cập nhật trước, ứng dụng nhận biết xung đột và yêu cầu tải lại.
- **Pessimistic locking:** khóa bản ghi trong transaction khi cần tuần tự hóa các thao tác cạnh tranh. Cách này có chi phí chờ và cần cân nhắc nguy cơ deadlock.
- **Cập nhật có điều kiện:** thực hiện câu lệnh cập nhật chỉ khi trạng thái vẫn là trạng thái dự kiến, sau đó kiểm tra số bản ghi thực sự được cập nhật.

Ví dụ SQL minh họa cập nhật có điều kiện:

```sql
UPDATE leave_request
SET status = 'APPROVED',
    approved_by = :actorId
WHERE id = :requestId
  AND status = 'PENDING';
```

Nếu số dòng được cập nhật bằng 0, yêu cầu có thể không tồn tại, không còn ở trạng thái chờ hoặc đã được một request khác xử lý. Ứng dụng cần xác định phản hồi phù hợp theo ngữ cảnh và không giả định thao tác đã thành công.

### 3.7. Thực hiện kiểm tra và ghi dữ liệu trong transaction phù hợp

Khi nhiều bước phải cùng thành công, hãy đặt chúng trong một transaction. Ví dụ, xác nhận đơn hàng có thể cần cập nhật trạng thái đơn, ghi nhận thanh toán và tạo dữ liệu giao hàng. Nếu một bước thất bại, các thay đổi trong transaction cần được rollback để tránh trạng thái dở dang.

Transaction không tự giải quyết mọi xung đột đồng thời. Mức cô lập, khóa, optimistic version và ràng buộc dữ liệu vẫn cần được lựa chọn theo quy tắc nghiệp vụ. Với tác vụ gọi dịch vụ bên ngoài, không nên giữ transaction cơ sở dữ liệu mở trong thời gian mạng kéo dài; cần thiết kế cơ chế phối hợp phù hợp như trạng thái chờ, outbox hoặc quy trình bù trừ khi cần.

## 4. Ví dụ: duyệt một yêu cầu nghỉ phép

Giả sử hệ thống nhân sự cho phép quản lý duyệt yêu cầu nghỉ phép. Một yêu cầu chỉ được duyệt khi:

1. Yêu cầu tồn tại và đang ở trạng thái `PENDING`.
2. Người thực hiện đã đăng nhập và có quyền duyệt.
3. Người thực hiện được phân công quản lý nhân viên gửi yêu cầu.
4. Khoảng thời gian nghỉ vẫn hợp lệ theo quy định hiện tại.
5. Yêu cầu chưa bị một người khác xử lý đồng thời.

Luồng xử lý có thể đặt trong service như sau. Đây là mã Java minh họa, tên lớp và API transaction phụ thuộc framework của dự án:

```java
@Transactional
public void approveLeaveRequest(
        UUID requestId,
        UserId currentUserId) {

    LeaveRequest request = repository.findById(requestId)
        .orElseThrow(LeaveRequestNotFoundException::new);

    authorization.requireCanApprove(
        currentUserId,
        request.getEmployeeId()
    );

    leavePolicy.requireApprovalAllowed(request);

    request.approve(currentUserId, clock.instant());

    repository.save(request);
}
```

Phương thức của Model chịu trách nhiệm bảo vệ chuyển trạng thái:

```java
public void approve(UserId approverId, Instant approvedAt) {
    if (status != LeaveStatus.PENDING) {
        throw new InvalidLeaveTransitionException(
            "Only pending requests can be approved"
        );
    }

    if (approverId == null || approvedAt == null) {
        throw new IllegalArgumentException(
            "Approver and approval time are required"
        );
    }

    this.status = LeaveStatus.APPROVED;
    this.approvedBy = approverId;
    this.approvedAt = approvedAt;
}
```

Trong ví dụ này:

- Controller nhận request và gọi service với mã yêu cầu cùng danh tính đã xác thực.
- Service tải dữ liệu mới nhất, kiểm tra quyền và chính sách nghỉ phép.
- Model chỉ cho phép chuyển từ `PENDING` sang `APPROVED`.
- Transaction bao quanh thao tác đọc và ghi để giữ tính nhất quán giữa các bước.

Nếu hệ thống cho phép hai quản lý cùng thao tác, cần bổ sung optimistic locking hoặc khóa phù hợp. Chỉ dùng `@Transactional` mà không có chiến lược xử lý cạnh tranh không bảo đảm rằng hai request không cùng đọc một trạng thái cũ. Với optimistic locking, entity có thể có trường phiên bản:

```java
@Version
private long version;
```

Khi một request lưu phiên bản cũ sau khi request khác đã cập nhật, thao tác lưu sẽ thất bại do xung đột phiên bản. Ứng dụng cần chuyển lỗi này thành phản hồi phù hợp và hướng người dùng tải lại dữ liệu.

## 5. Phản hồi khi điều kiện không thỏa mãn

Khi từ chối cập nhật, ứng dụng nên cho biết thao tác không thành công vì lý do nào ở mức người dùng có thể hiểu và xử lý. Không nên trả stack trace, câu lệnh SQL hoặc chi tiết nội bộ.

Một số cách ánh xạ thường gặp trong ứng dụng web:

| Tình huống | Phản hồi HTTP thường dùng | Cách View có thể trình bày |
|---|---|---|
| Dữ liệu đầu vào sai định dạng | `400 Bad Request` hoặc `422 Unprocessable Content` | Hiển thị lỗi cạnh trường nhập |
| Chưa đăng nhập | `401 Unauthorized` hoặc chuyển đến đăng nhập theo ứng dụng | Yêu cầu đăng nhập |
| Đã đăng nhập nhưng không có quyền | `403 Forbidden`, hoặc `404` khi cần che giấu tài nguyên | Thông báo không thể thực hiện thao tác |
| Đối tượng không tồn tại | `404 Not Found` | Thông báo không tìm thấy |
| Trạng thái hiện tại không cho phép thao tác | Thường là `409 Conflict` | Nêu trạng thái đã thay đổi và yêu cầu tải lại |
| Xung đột phiên bản hoặc cập nhật đồng thời | Thường là `409 Conflict` | Thông báo dữ liệu vừa được người khác cập nhật |
| Vi phạm quy tắc nghiệp vụ đã xác định | `409` hoặc `422` tùy hợp đồng API | Nêu điều kiện cần đáp ứng |

Mã HTTP cụ thể cần nhất quán với hợp đồng API của ứng dụng. Với giao diện biểu mẫu server-rendered, ứng dụng có thể trả lại trang cùng dữ liệu đã nhập và thông báo lỗi. Với API JSON, có thể trả mã lỗi ổn định, thông điệp và thông tin trường liên quan để frontend xử lý.

Cần phân biệt lỗi nghiệp vụ dự kiến với lỗi hệ thống bất ngờ. Điều kiện không thỏa mãn là kết quả có thể dự đoán và nên được biểu diễn bằng lỗi miền nghiệp vụ hoặc kiểu kết quả rõ ràng. Lỗi cơ sở dữ liệu, mất kết nối hoặc lỗi lập trình cần được ghi log và xử lý ở lớp phù hợp.

## 6. Kiểm thử các điều kiện trước cập nhật

Kiểm thử nên xác nhận cả trường hợp được phép và trường hợp bị từ chối. Với thao tác duyệt yêu cầu nghỉ phép, có thể kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Yêu cầu đang chờ, người dùng có quyền và được phân công | Trạng thái chuyển sang `APPROVED` |
| Yêu cầu đã bị hủy | Từ chối chuyển trạng thái |
| Người dùng không có quyền duyệt | Từ chối thao tác, dữ liệu không đổi |
| Người duyệt không phụ trách nhân viên đó | Từ chối thao tác, dữ liệu không đổi |
| Chính sách nghỉ phép không còn thỏa mãn | Từ chối thao tác, dữ liệu không đổi |
| Hai request cùng duyệt một yêu cầu | Chỉ một cập nhật thành công; request còn lại nhận xung đột |
| Lưu một bước liên quan thất bại | Transaction rollback theo thiết kế |

Có thể chia kiểm thử thành ba mức:

- **Unit test cho Model:** xác nhận phương thức của đối tượng cho phép hoặc từ chối chuyển trạng thái và luôn giữ bất biến.
- **Unit hoặc service test:** xác nhận service kiểm tra quyền, chính sách và điều phối repository đúng thứ tự.
- **Integration test:** xác nhận transaction, ràng buộc cơ sở dữ liệu, optimistic locking và phản hồi HTTP hoạt động đúng khi có xung đột.

Một bài kiểm thử quan trọng là xác nhận dữ liệu không bị thay đổi khi điều kiện thất bại. Chỉ kiểm tra rằng phương thức ném exception là chưa đủ nếu một phần dữ liệu đã được ghi trước đó.

## 7. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra trên giao diện

Frontend có thể giúp người dùng nhập đúng, nhưng không thể là nơi duy nhất bảo vệ quy tắc. Request có thể được gửi bằng công cụ khác hoặc dữ liệu có thể đã thay đổi trên máy chủ.

### Để Controller tự quyết định mọi quy tắc

Khi nhiều Controller cùng thực hiện một thao tác, chúng dễ kiểm tra khác nhau hoặc bỏ sót điều kiện. Hãy đặt quy tắc dùng chung trong service hoặc Model để mọi luồng gọi đều được bảo vệ.

### Tin trạng thái hoặc quyền do client gửi lên

Các trường như `status`, `approvedBy`, `ownerId`, `price` và `role` có thể bị sửa. Máy chủ cần tải trạng thái có thẩm quyền và xác định danh tính từ ngữ cảnh bảo mật.

### Kiểm tra xong rồi cập nhật ngoài cơ chế đồng bộ

Giữa thời điểm kiểm tra và thời điểm ghi, request khác có thể thay đổi dữ liệu. Transaction cùng chiến lược khóa, version hoặc cập nhật có điều kiện giúp xử lý khoảng thời gian này.

### Dùng cơ sở dữ liệu thay cho toàn bộ quy tắc nghiệp vụ

Ràng buộc dữ liệu rất quan trọng, nhưng nhiều quy tắc cần ngữ cảnh như người thực hiện, trạng thái quy trình hoặc chính sách hiện hành. Hãy kiểm tra trong service/Model và dùng constraint làm lớp bảo vệ bổ sung.

### Trả thông báo lỗi quá chung chung hoặc quá chi tiết

Thông báo “Có lỗi xảy ra” không giúp người dùng biết phải làm gì; ngược lại, trả chi tiết truy vấn hoặc stack trace có thể làm lộ thông tin nội bộ. Hãy cung cấp lý do nghiệp vụ vừa đủ, đồng thời ghi log kỹ thuật ở phía máy chủ.

## 8. Checklist trước khi lưu một thay đổi

Trước khi thực hiện thao tác cập nhật quan trọng, hãy xác nhận:

1. Đối tượng được tải từ nguồn dữ liệu phía máy chủ và thuộc phạm vi truy cập phù hợp.
2. Danh tính và quyền của người thực hiện đã được xác minh.
3. Trạng thái hiện tại cho phép thao tác và chuyển trạng thái mới là hợp lệ.
4. Dữ liệu liên quan, giới hạn và các bất biến đều được kiểm tra.
5. Các trường do client gửi không được dùng làm nguồn sự thật cho quyền hoặc trạng thái.
6. Transaction và chiến lược xử lý cập nhật đồng thời phù hợp với mức độ rủi ro.
7. Ràng buộc cơ sở dữ liệu bảo vệ những điều kiện toàn vẹn cần được bảo đảm.
8. Khi điều kiện không thỏa mãn, dữ liệu không bị cập nhật một phần và phản hồi đủ rõ ràng.
9. Có kiểm thử cho cả trường hợp thành công, thất bại và xung đột đồng thời.

## Kết luận

Kiểm tra điều kiện nghiệp vụ trước khi cập nhật là bước bảo vệ trạng thái hợp lệ của Model. Controller tiếp nhận và kiểm tra dữ liệu đầu vào, service điều phối quyền và quy tắc của ca sử dụng, Model bảo vệ bất biến, còn transaction và cơ sở dữ liệu giúp duy trì tính toàn vẹn khi lưu. Khi các trách nhiệm này được đặt đúng chỗ, ứng dụng MVC xử lý được những thay đổi hợp lệ, từ chối thao tác không phù hợp và phản hồi nhất quán ngay cả khi nhiều người dùng cùng làm việc trên một dữ liệu.

