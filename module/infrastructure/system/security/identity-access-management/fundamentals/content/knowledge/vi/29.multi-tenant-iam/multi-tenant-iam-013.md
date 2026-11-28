# Kiểm thử cross-tenant access

## 1. Mục tiêu kiểm thử: chứng minh ranh giới tenant được thực thi

**Cross-tenant access** là việc một chủ thể thao tác với dữ liệu hoặc chức năng thuộc tenant khác. Việc đó trở thành lỗi bảo mật khi không có quyền hoặc cơ chế chia sẻ hợp lệ cho phép.

Trong nền tảng quản lý dự án phục vụ nhiều công ty, người dùng của công ty A không được đọc dự án riêng của công ty B chỉ bằng cách đổi ID trên URL. Tương tự, quyền quản trị ở A không được tự động có hiệu lực tại B.

Kiểm thử cross-tenant access cần trả lời ba câu hỏi:

1. Chủ thể được phép làm gì trong từng tenant?
2. Hệ thống có chặn thao tác vượt phạm vi trên mọi đường vào liên quan không?
3. Khi từ chối, hệ thống có thực sự không làm lộ dữ liệu và không tạo tác động ngoài phạm vi không?

Một phản hồi `403` hoặc `404` chỉ là một phần bằng chứng. Request vẫn có thể đã tạo job, thay đổi dữ liệu hoặc sinh file trước khi trả lỗi. Vì vậy cần kiểm tra cả phản hồi lẫn trạng thái sau thao tác.

Bài này sử dụng tenant, tài khoản và tài nguyên thử nghiệm trong môi trường được phép kiểm thử. Không sử dụng dữ liệu khách hàng thật để làm fixture.

## 2. Xác định hợp đồng truy cập trước khi viết ca kiểm thử

Không thể kết luận một request là đúng hay sai nếu chưa có policy làm chuẩn.

Với ứng dụng thông thường, một hành động trên tài nguyên tenant thường đòi hỏi:

```text
Danh tính được xác thực
  + quyền truy cập tenant đích
  + quyền thực hiện hành động
  + tài nguyên thuộc phạm vi được phép
  + điều kiện policy hiện hành.
```

Ví dụ hợp đồng:

- Người dùng chỉ thuộc A không được đọc tài nguyên riêng của B.
- Người quản trị A nhưng chỉ là người xem B không được sửa tài nguyên B.
- Token chỉ dành cho A không được dùng trên endpoint B.
- Workload được cấp quyền cho A không được tự chọn B.
- Một tài nguyên được chia sẻ hợp lệ từ A sang B chỉ cho phép đúng người nhận và hành động đã cấp.

Điểm cuối rất quan trọng: **khác tenant không tự động đồng nghĩa với bị cấm**. Sản phẩm có thể hỗ trợ chia sẻ tài nguyên, đối tác hoặc quyền hỗ trợ khách hàng. Các ngoại lệ này cần có grant rõ ràng và có ca kiểm thử riêng, thay vì được ngầm hiểu từ một vai trò toàn cục.

Hợp đồng cũng cần xác định phản hồi khi bị từ chối. API có thể dùng `403` hoặc che giấu sự tồn tại bằng `404` theo thiết kế. Credential không hợp lệ thuộc lớp xác thực và thường có cách xử lý khác. Một lỗi máy chủ hoặc phản hồi rỗng do exception không phải bằng chứng đạt yêu cầu phân quyền.

## 3. Thiết kế fixture phân biệt được các loại lỗi

### 3.1. Hai tenant và nhiều quan hệ quyền

Một bộ dữ liệu tối thiểu:

| Định danh thử nghiệm | Tenant A: Sao Mai | Tenant B: Đại Dương |
| --- | --- | --- |
| `user_a` | Thành viên, được đọc một số dự án | Không là thành viên |
| `user_b` | Không là thành viên | Thành viên, được đọc một số dự án |
| `user_ab` | Quản trị dự án | Người xem |
| `service_a` | Workload có quyền đọc báo cáo | Không có grant |
| `project_a1` | Dự án riêng của A | Không thuộc B |
| `project_b1` | Không thuộc A | Dự án riêng của B |

Gắn dữ liệu nhận diện dễ kiểm tra:

```text
project_a1.name = FIXTURE_A_ONLY_7F1
project_b1.name = FIXTURE_B_ONLY_8C2
```

Các dấu hiệu này giúp phát hiện dữ liệu sai tenant trong response, file export, log ứng dụng phục vụ người dùng hoặc kết quả tìm kiếm. Chúng không thay thế kiểm tra cấu trúc và quyền; một dữ liệu bị biến đổi có thể không còn giữ nguyên chuỗi đánh dấu.

Nếu thiết kế cho phép ID chỉ duy nhất trong mỗi tenant, nên tạo tài nguyên có cùng ID cục bộ:

```text
(A, project_id=42)
(B, project_id=42)
```

Cách này dễ phát hiện cache hoặc truy vấn chỉ dùng `project_id` mà bỏ quên tenant. Nếu sản phẩm dùng ID duy nhất toàn cục, hãy tôn trọng mô hình đó và sử dụng các ID khác nhau; không phá ràng buộc dữ liệu chỉ để tạo fixture.

### 3.2. Tách danh tính, membership và token

Bộ kiểm thử cần biết mỗi credential đại diện cho ai và phạm vi nào:

```text
token_a       → user_a,  tenant A
token_b       → user_b,  tenant B
token_ab_a    → user_ab, tenant A, quyền quản trị dự án
token_ab_b    → user_ab, tenant B, quyền xem
token_service → service_a, tenant A, quyền đọc báo cáo
```

Đây là mô hình khi sản phẩm sử dụng token gắn với một tenant. Với phiên hoặc token danh tính chung, fixture cần mô tả tenant được chọn và cách kiểm tra membership trên từng request theo đúng kiến trúc thực tế.

Token phải được cấp qua cơ chế thử nghiệm hợp lệ hoặc bên cấp quyền được cấu hình cho môi trường test. Không chỉ sửa claim tenant trong một JWT rồi kiểm tra hệ thống trả lỗi: trường hợp đó có thể chỉ kiểm chứng chữ ký, chưa kiểm chứng phân quyền giữa hai tenant với token hợp lệ.

Không ghi credential thật vào mã nguồn, báo cáo hoặc log kiểm thử.

## 4. Ma trận kiểm thử cốt lõi

Bắt đầu bằng ca thành công để chứng minh fixture và endpoint hoạt động, rồi chỉ thay một chiều ngữ cảnh để tạo ca vượt quyền.

| Chủ thể và ngữ cảnh | Tài nguyên hoặc hành động | Kỳ vọng |
| --- | --- | --- |
| `user_a`, tenant A | Đọc `project_a1` được cấp quyền | Thành công |
| `user_b`, tenant B | Đọc `project_b1` được cấp quyền | Thành công |
| `user_a`, tenant A | Đọc trực tiếp `project_b1` | Không trả dữ liệu B |
| Token chỉ dành cho A | Gọi đường dẫn tenant B | Bị từ chối theo hợp đồng tenant |
| `user_ab`, tenant B | Đọc dự án B được phép | Thành công |
| `user_ab`, tenant B | Sửa hoặc xóa dự án B | Bị từ chối dù là quản trị viên ở A |
| `user_a`, tenant A | Tạo task tham chiếu project B | Bị từ chối, không tạo quan hệ chéo tenant |
| `service_a`, tenant A | Xuất báo cáo B | Bị từ chối, không tạo job cho B |
| Chủ thể có grant chia sẻ cụ thể | Đọc tài nguyên được chia sẻ | Chỉ thành công trong giới hạn grant |

Ca `user_ab` đặc biệt hữu ích vì phát hiện lỗi làm mất phạm vi của role. Nếu chỉ dùng hai người dùng hoàn toàn khác nhau, hệ thống có thể vượt qua kiểm thử membership nhưng vẫn áp quyền quản trị A sang B cho cùng một người.

Nên kiểm tra hai hướng A sang B và B sang A. Các tenant có thể dùng cấu hình, kho dữ liệu hoặc kết nối danh tính khác nhau nên hành vi không chắc đối xứng.

## 5. Thay đổi ngữ cảnh tenant ở từng đường vào

### 5.1. Path, query, header và body

Ví dụ request hợp lệ:

```http
GET /tenants/tenant_a/projects/project_a1
Authorization: Bearer <test-token-a>
```

Các biến thể cần kiểm tra trong môi trường thử nghiệm:

```text
1. Giữ token A, đổi path sang tenant B.
2. Giữ path A, đổi project ID thành project_b1.
3. Giữ path A, gửi header tenant B nếu API có đọc header tenant.
4. Giữ path A, gửi body tenant_id=B trên endpoint tạo hoặc sửa.
5. Gửi tenant không tồn tại, thiếu tenant hoặc định dạng không hợp lệ.
6. Gửi nhiều nguồn tenant mâu thuẫn theo các vị trí API hỗ trợ.
```

Mục tiêu là chứng minh mọi tầng dùng cùng ngữ cảnh tenant đã được xác minh. Không để tầng phân quyền dùng path A trong khi repository lấy tenant B từ body.

Với endpoint tạo tài nguyên, cần kiểm tra client không thể gán tài nguyên sang tenant khác qua cơ chế tự động bind field. Với endpoint cập nhật, cần kiểm tra không thể chuyển `tenant_id` của bản ghi hiện có nếu sản phẩm không có quy trình chuyển tenant được cấp quyền riêng.

Trường hợp thiếu tenant không được âm thầm trở thành một tenant mặc định có dữ liệu thật. Cách từ chối hoặc định tuyến phải đúng hợp đồng endpoint.

### 5.2. Hostname, slug và phiên

Nếu ứng dụng chọn tenant qua subdomain hoặc slug:

```text
sao-mai.example.test
dai-duong.example.test
```

Cần kiểm tra ánh xạ hostname hoặc slug về tenant chuẩn, đồng thời kiểm tra principal có quyền trong tenant đó. Việc định tuyến đến giao diện đăng nhập tenant B chưa đồng nghĩa được đọc dữ liệu riêng của B.

Nếu phiên phía máy chủ lưu tenant đang chọn, hãy thử:

1. Mở tab A ở tenant A.
2. Mở tab B và chuyển sang tenant B.
3. Từ tab A, gửi lại một thao tác vẫn hiển thị tenant A.
4. Xác minh thao tác không âm thầm áp dụng cho B.
5. Kiểm tra kết quả trả về không bị hiển thị dưới tenant sai.

### 5.3. Nguồn danh tính và thẩm quyền issuer

Trong mô hình liên kết nhiều IdP, cần kiểm tra token hoặc assertion hợp lệ từ nguồn của A không tự cấp quyền tại B ngoài ánh xạ tin cậy.

Có thể có token đúng chữ ký nhưng issuer không có thẩm quyền khẳng định membership của tenant đích. Đây là lỗi khác với token bị sửa chữ ký.

Cũng nên kiểm tra hai danh tính có cùng email ở hai nguồn độc lập không bị tự gộp và thừa hưởng quyền chéo tenant trái với policy liên kết danh tính của hệ thống.

## 6. Kiểm thử đọc dữ liệu: không chỉ endpoint lấy theo ID

Một API lấy chi tiết có thể an toàn trong khi những đường đọc khác vẫn làm lộ dữ liệu.

| Đường đọc | Điều cần xác minh |
| --- | --- |
| Danh sách và phân trang | Mọi phần tử và tổng số đều thuộc phạm vi được phép |
| Tìm kiếm, gợi ý, autocomplete | Không lộ tên, ID hoặc nội dung tenant khác |
| Bộ lọc và thống kê | Không trả số lượng hoặc giá trị tổng hợp ngoài phạm vi |
| Quan hệ lồng nhau | Child và parent đều giữ ràng buộc tenant |
| Batch hoặc truy vấn nhiều ID | Mỗi phần tử được kiểm tra; không coi kiểm tra phần tử đầu là đủ |
| Lịch sử, audit cho người dùng tenant | Không lộ hoạt động hoặc chủ thể của tenant khác |
| Export và báo cáo | File, hàng dữ liệu và metadata đều đúng tenant |
| Tải file hoặc preview | Quyền được kiểm tra trên tài nguyên và phạm vi sở hữu |
| Luồng realtime | Subscription và sự kiện đều được giới hạn tenant |

Ví dụ, request danh sách chỉ trả dự án A nhưng trường `totalCount` tính trên cả A và B vẫn có thể làm lộ thông tin.

Với batch, chuẩn bị một tập có cả tài nguyên được phép và không được phép:

```json
{
  "project_ids": ["project_a1", "project_b1"]
}
```

Sản phẩm có thể từ chối toàn bộ hoặc trả một phần theo hợp đồng. Dù chọn cách nào, không được trả dữ liệu B cho người chỉ có quyền A, và không được làm lộ chi tiết nhạy cảm trong thông báo lỗi từng phần.

Nếu API hỗ trợ truy vấn quan hệ sâu, hãy đi qua các nhánh như project → task → attachment. Chỉ kiểm tra tenant ở node gốc chưa bảo đảm mọi resolver hoặc truy vấn con đều giữ phạm vi.

## 7. Kiểm thử ghi và các tác động phụ

### 7.1. Chứng minh trạng thái không đổi khi bị từ chối

Đối với thao tác sửa, xóa hoặc cấp quyền, hãy lưu trạng thái trước và kiểm tra sau bằng một nguồn quan sát được phép.

Ví dụ ca `user_a` cố cập nhật `project_b1`:

```text
Trước request:
  project_b1.name = FIXTURE_B_ONLY_8C2
  project_b1.version = 5

Request:
  user_a yêu cầu đổi tên project_b1.

Sau request bị từ chối:
  name và version vẫn như cũ;
  không tạo event cập nhật dự án B;
  không tạo job hoặc thông báo nghiệp vụ cho B.
```

Có thể có audit về lần thử bị từ chối. Audit đó là kết quả dự kiến, không phải tác động nghiệp vụ trái phép. Bộ kiểm thử cần phân biệt hai loại.

Cần quan sát đủ lâu hoặc dùng điểm đồng bộ của hệ thống để phát hiện tác động bất đồng bộ. Không kết luận ngay rằng không có job chỉ vì kiểm tra hàng đợi trước khi producer hoàn tất.

### 7.2. Quan hệ chéo tenant

Các ca cần có:

- Tạo task ở A với project ID thuộc B.
- Gán chủ sở hữu tài nguyên A cho một principal không được phép trong A.
- Thêm thành viên A vào nhóm quyền của B bằng cách thay group ID.
- Gắn role assignment của A vào membership B.
- Tải attachment B qua đường dẫn parent thuộc A.

Mục tiêu là kiểm tra cả tenant của bản ghi chính và tenant của đối tượng được tham chiếu. Một field `tenant_id=A` trên task không đủ nếu task vẫn tham chiếu project B.

### 7.3. Bulk và transaction

Với thao tác hàng loạt chứa cả A và B, hợp đồng phải nêu rõ tính nguyên tử:

- Nếu toàn bộ thao tác phải thành công hoặc thất bại cùng nhau, request bị từ chối không được để lại phần thay đổi nào.
- Nếu cho phép thành công từng phần, từng phần tử phải được cấp quyền độc lập và báo kết quả đúng phạm vi.

Không mặc định mọi bulk API đều có transaction chung. Bộ kiểm thử cần đối chiếu đúng cam kết của endpoint.

## 8. Kiểm thử cache, tác vụ nền và truyền ngữ cảnh

### 8.1. Cache và thứ tự request

Một lỗi thường gặp là cache dùng khóa `project:42` dù ID chỉ duy nhất trong tenant.

Chuỗi kiểm thử:

```text
1. User A đọc project 42 của A để làm nóng cache.
2. User B đọc project 42 của B.
3. Xác minh B nhận đúng dữ liệu B.
4. Đảo thứ tự B rồi A và kiểm tra lại.
5. Thực hiện xen kẽ các request có quyền khác nhau trong cùng tenant.
```

Bước 5 giúp phát hiện cache có tenant nhưng bỏ qua điều kiện quyền theo principal hoặc policy.

Cần kiểm tra cả cache dữ liệu, cache quyết định cấp quyền và cache ở client hoặc lớp trung gian có liên quan. Việc đặt tenant trong cache key hỗ trợ phân vùng, nhưng vẫn cần kiểm tra quyền trước khi trả dữ liệu.

### 8.2. Job nền, retry và kết quả export

Với job xuất báo cáo:

1. Người dùng A yêu cầu export dữ liệu A.
2. Xác minh job mang tenant A từ nguồn đã được kiểm tra.
3. Consumer thực thi đúng phạm vi A.
4. Kết quả chỉ chứa dữ liệu A.
5. Chỉ principal được phép mới lấy được trạng thái và file kết quả.
6. Người dùng B không thể tải file bằng cách thay job ID hoặc file ID.
7. Retry không làm đổi tenant hoặc dùng ngữ cảnh còn sót từ job trước.

Nếu dùng link tải có chữ ký hoặc credential dạng capability, phải kiểm tra hành vi theo hợp đồng chia sẻ của link: thời hạn, phạm vi object, đối tượng được phép nếu cơ chế có ràng buộc đó, và cách thu hồi khi cần.

Không mặc định một link đã cấp sẽ luôn kiểm tra lại membership mỗi lần tải. Điều này phụ thuộc cơ chế phục vụ file và cần được xác định trong yêu cầu sản phẩm.

### 8.3. Dùng lại thread và connection

Tenant context có thể rò rỉ khi dùng lại thread, connection hoặc session làm việc với cơ sở dữ liệu.

Các chuỗi có giá trị:

```text
Request A thành công → request B.
Request A ném exception → request B.
Job A bị hủy → job B.
Transaction A rollback → transaction B.
A và B chạy xen kẽ qua nhiều tác vụ bất đồng bộ.
```

Sau mỗi chuỗi, dữ liệu và quyền của B phải chỉ phụ thuộc ngữ cảnh B. Kiểm tra cả nhánh lỗi vì cleanup có thể chỉ chạy khi request thành công.

Nếu cơ chế tenant isolation dựa vào trạng thái trên connection, hãy xác minh trạng thái được thiết lập và xóa theo đúng vòng đời transaction hoặc connection pool. Không chỉ kiểm tra một request đơn lẻ trên connection mới.

## 9. Quyền thay đổi và ngoại lệ có kiểm soát

### 9.1. Membership, role và tenant bị khóa

Một ca vòng đời:

```text
T0: User A có quyền đọc và nhận token.
T1: Thu hồi membership hoặc quyền đọc.
T2: Gửi request bằng token cũ.
T3: Thử làm mới token hoặc cấp token mới.
```

Kỳ vọng tại T2 phụ thuộc mục tiêu thu hồi quyền. Nếu hệ thống chấp nhận token tự chứa cho đến hết hạn, cần ghi rõ giới hạn đó; không đặt một assertion thu hồi tức thì mà thiết kế không cam kết.

Nếu hệ thống cam kết thu hồi trong một khoảng thời gian nhất định, kiểm thử phải đo theo mốc thay đổi quyền và giới hạn đã quy định. Nên chờ có điều kiện với thời hạn tối đa, thay vì chèn một khoảng sleep tùy ý rồi coi là bằng chứng.

Kiểm tra thêm:

- Tenant bị khóa trong khi access token còn hạn.
- Refresh token cũ được dùng sau khi membership bị gỡ.
- Cache quyền được làm nóng trước khi role thay đổi.
- Gỡ người dùng khỏi A nhưng vẫn giữ quyền hợp lệ tại B.
- Vô hiệu hóa danh tính toàn cục khi người dùng thuộc nhiều tenant.

### 9.2. Chia sẻ hợp lệ và quyền hỗ trợ

Nếu A chia sẻ một tài liệu cho một nhóm của B, cần kiểm tra cả ca cho phép và giới hạn:

| Trạng thái | Kỳ vọng |
| --- | --- |
| Grant chỉ cho đọc | Không được sửa hoặc chia sẻ tiếp nếu chưa được cấp |
| Grant dành cho nhóm B1 | Người khác trong B không tự được truy cập |
| Grant bị thu hồi | Mất quyền theo mục tiêu hiệu lực đã quy định |
| Grant hết hạn | Không tiếp tục được chấp nhận ngoài thời hạn |
| Request tới tài liệu khác của A | Không được thừa hưởng quyền chỉ vì cùng chủ sở hữu tenant |

Với nhân viên hỗ trợ, cần thử quyền trước, trong và sau khoảng được phê duyệt. Audit phải thể hiện được người thực hiện, tenant bị tác động và căn cứ của quyền đặc biệt.

Không dùng ca hỗ trợ được phép để biện minh cho việc mọi tài khoản quản trị nền tảng đều bỏ qua kiểm tra tenant.

## 10. Ví dụ tổ chức một ca kiểm thử tự động

Pseudocode theo phong cách Java và JUnit:

```java
@Test
void readerOfTenantACannotModifyProjectOfTenantB() {
    Fixture fixture = fixtures.createIsolatedTwoTenantFixture();

    ProjectSnapshot before =
        fixture.observer().readProjectB();

    ApiResponse response = api.updateProject(
        fixture.tokenForUserA(),
        fixture.tenantB(),
        fixture.projectB(),
        new UpdateProject("UNAUTHORIZED_CHANGE")
    );

    fixture.contract().assertAccessDenied(response);
    fixture.contract().assertNoSensitiveData(response);

    fixture.events().awaitRequestProcessingCompleted(
        response.correlationId()
    );

    ProjectSnapshot after =
        fixture.observer().readProjectB();

    assertEquals(before, after);

    fixture.events().assertNoBusinessMutationFor(
        response.correlationId(),
        fixture.tenantB(),
        fixture.projectB()
    );
}
```

Đây là ví dụ tổ chức kiểm thử, không phải mã hoàn chỉnh để chạy trực tiếp. Fixture, API client, observer và event probe phải được triển khai theo hệ thống thực tế.

Một số điểm cần giữ khi hiện thực hóa:

- Observer là cơ chế được phép nhìn trạng thái để đánh giá kết quả, không phải quyền được cấp cho người dùng A.
- Correlation ID phải gắn được request với tác động cần quan sát; không lưu token vào bằng chứng.
- Điểm `awaitRequestProcessingCompleted` chỉ có ý nghĩa nếu hệ thống thử nghiệm thật sự cung cấp tín hiệu hoàn tất đáng tin cậy.
- Assertion về response phải khớp hợp đồng endpoint, không chỉ kiểm tra mã khác `200`.
- Snapshot phải bao gồm các field hoặc quan hệ có thể bị sửa bởi thao tác, tránh bỏ sót tác động.
- Dữ liệu test cần được cô lập và dọn theo quyền của bộ kiểm thử, không xóa dữ liệu ngoài fixture.

Nên tái sử dụng cấu trúc này theo từng hành động thay vì chỉ viết một ca đọc tài nguyên. Một ca cập nhật không chứng minh endpoint export, tìm kiếm hoặc cấp role đã an toàn.

## 11. Bằng chứng và điều kiện đạt

Báo cáo kiểm thử nên ghi:

```text
Test case: XTA-UPDATE-001
Actor: user_a
Credential scope: tenant A
Requested tenant: tenant B
Resource owner tenant: tenant B
Action: project.update
Expected decision: DENY
Observed response: đúng hợp đồng từ chối
Observed state: không thay đổi dữ liệu hoặc quan hệ nghiệp vụ
Observed async effects: không có tác động nghiệp vụ trái phép
Audit: ghi nhận lần thử theo policy
Result: PASS
```

Các dấu hiệu cần điều tra gồm dữ liệu tenant khác xuất hiện trong payload, số lượng thống kê không đúng phạm vi, file export sai tenant, role của tenant A được áp dụng tại B, hoặc request bị từ chối nhưng vẫn gây thay đổi.

Một bộ kiểm thử đạt cần chứng minh cả **khả năng sử dụng đúng quyền** và **khả năng chặn vượt quyền**. Nếu mọi request đều bị lỗi vì fixture hỏng, hệ thống chưa được chứng minh có tenant isolation đúng.

Khi thêm endpoint, resolver, consumer hoặc cơ chế cache mới, hãy xác định điểm nào nhận tenant context và điểm nào thực thi quyền. Các kiểm thử cross-tenant tương ứng cần đi cùng đường xử lý đó để phát hiện hồi quy tại chính nơi ranh giới tenant có thể bị mất.
