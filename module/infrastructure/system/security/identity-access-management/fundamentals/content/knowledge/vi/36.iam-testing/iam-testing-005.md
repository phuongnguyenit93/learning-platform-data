# Object-level authorization test

## 1. Kiểm thử quyền trên từng đối tượng nhằm phát hiện điều gì?

**Object-level authorization test** kiểm tra rằng một chủ thể chỉ được thực hiện những hành động được phép đối với đúng đối tượng tài nguyên trong đúng ngữ cảnh. Đối tượng có thể là tài liệu, đơn hàng, khóa học, bản ghi thanh toán hoặc một tệp đính kèm cụ thể.

Authentication cho biết request có danh tính được kiểm chứng hay không. Quyền gọi một chức năng cho biết chủ thể có được sử dụng loại thao tác đó hay không. Cả hai vẫn chưa trả lời đầy đủ câu hỏi: **người này có được thực hiện thao tác này trên bản ghi này không?**

Ví dụ, Alice và Bob đều có role `member` và đều được gọi chức năng đọc tài liệu. Alice có thể đọc tài liệu riêng của mình, nhưng không được đọc tài liệu riêng của Bob nếu không có quan hệ chia sẻ hoặc quyền khác theo chính sách.

Một lỗi ở lớp này có thể khiến người đã đăng nhập truy cập hoặc sửa đối tượng ngoài phạm vi của mình. ID khó đoán, giao diện ẩn nút hoặc gateway đã kiểm tra token không thay thế được việc thực thi quyền trên đối tượng tại backend.

Mục tiêu kiểm thử không phải từ chối mọi đối tượng “không phải của tôi”. Hệ thống có thể có chia sẻ, phân công, quản trị có phạm vi hoặc tài nguyên công khai. Kết quả phải dựa trên chính sách đã xác định, không dựa vào một giả định sở hữu quá đơn giản.

## 2. Xác định chính sách làm nguồn kỳ vọng độc lập

Một quyết định authorization có thể phụ thuộc:

```text
chủ thể đã được kiểm chứng
+ hành động được yêu cầu
+ đối tượng tài nguyên thực tế
+ quan hệ chủ thể - đối tượng
+ tenant và ngữ cảnh liên quan
+ policy và trạng thái đủ mới
-> cho phép / từ chối theo hợp đồng
```

Trước khi viết test, cần mô tả những quy tắc đó bằng ví dụ nghiệp vụ rõ ràng. Nếu kỳ vọng của test chỉ gọi lại chính hàm authorization đang được kiểm thử, hai bên có thể cùng sai và test vẫn pass.

Một policy minh họa cho tài liệu riêng trong bài này:

- Chủ sở hữu được đọc, sửa nội dung và xóa tài liệu của mình trong tenant tương ứng.
- Người được chia sẻ quyền đọc chỉ được đọc đúng tài liệu đã chia sẻ.
- Người có role `auditor` được đọc tài liệu trong tenant của mình theo phạm vi đã cấp, không được sửa hoặc xóa.
- Thành viên thông thường không có quyền trên tài liệu riêng của người khác khi không có quan hệ phù hợp.
- Không có quyền truy cập chéo tenant trong mô hình minh họa này.

Đây là chính sách phục vụ bài học. Một hệ thống thực tế cần thay bằng hợp đồng quyền của nó, bao gồm các ngoại lệ hợp lệ nếu có.

Kiểm thử field-level authorization, chẳng hạn ai được sửa trường `ownerId`, có liên quan nhưng không đồng nghĩa object-level authorization. Cần biết lỗi đang nằm ở quyền trên đối tượng hay ở quyền trên từng trường của một đối tượng được phép truy cập.

## 3. Dựng fixture đủ để phân biệt các ranh giới

Dùng dữ liệu tổng hợp trong môi trường kiểm thử được phép, với những chủ thể và tài nguyên có quan hệ rõ ràng.

| Chủ thể | Tenant | Vai trò và quan hệ trong fixture |
|---|---|---|
| Alice | A | Thành viên; sở hữu tài liệu A1 |
| Bob | A | Thành viên; sở hữu tài liệu A2 |
| Reader-A | A | Được chia sẻ quyền đọc A1, không được chia sẻ A2 |
| Auditor-A | A | Có quyền audit đọc tài liệu trong A theo policy minh họa |
| Carol | B | Thành viên; sở hữu tài liệu B1 |

| Đối tượng | Tenant | Chủ sở hữu | Quan hệ bổ sung |
|---|---|---|---|
| A1 | A | Alice | Reader-A được đọc |
| A2 | A | Bob | Không có quyền chia sẻ cho Alice hoặc Reader-A |
| B1 | B | Carol | Không có quyền chia sẻ sang A |
| Attachment-A1 | A | Thuộc tài liệu A1 | Quyền theo hợp đồng của tài liệu cha |

Từ policy có thể lập một phần ma trận kỳ vọng:

| Chủ thể | Đối tượng | Đọc | Sửa nội dung | Xóa |
|---|---|---|---|---|
| Alice | A1 | Cho phép | Cho phép | Cho phép |
| Alice | A2 | Từ chối | Từ chối | Từ chối |
| Reader-A | A1 | Cho phép | Từ chối | Từ chối |
| Reader-A | A2 | Từ chối | Từ chối | Từ chối |
| Auditor-A | A2 | Cho phép | Từ chối | Từ chối |
| Auditor-A | B1 | Từ chối | Từ chối | Từ chối |

Một tài khoản duy nhất có role quản trị toàn cục thường không đủ để phát hiện lỗi phân tách quyền. Cần những chủ thể có cùng loại quyền chức năng nhưng khác quan hệ đối tượng, đồng thời có chủ thể khác tenant.

Credential của các chủ thể phải hợp lệ cho ứng dụng được kiểm thử. Nếu token của Alice vốn hết hạn, test “Alice không được đọc A2” có thể bị từ chối ở authentication và chưa hề kiểm tra object-level authorization.

## 4. Dùng positive control để tránh pass vì sai nguyên nhân

Trước một ca từ chối, cần có bằng chứng đường gọi đang hoạt động và chủ thể có thể thực hiện một thao tác hợp lệ tương đương.

Ví dụ:

```text
Positive control:
    Alice dùng credential hợp lệ đọc A1 -> nhận đúng dữ liệu A1

Negative case:
    Alice dùng cùng ngữ cảnh xác thực đọc A2 -> không nhận dữ liệu A2
```

Nếu cả hai request đều thất bại vì endpoint không tồn tại, mock không được cấu hình hoặc môi trường không có dữ liệu, bộ test chưa chứng minh ranh giới quyền.

Với thao tác ghi, tạo fixture độc lập hoặc khôi phục đúng dữ liệu thử nghiệm thuộc ca test trước khi chạy trường hợp tiếp theo. Không để ca xóa tài liệu làm những test về sau bị từ chối chỉ vì đối tượng không còn tồn tại.

Positive control cần xác nhận cả nội dung và danh tính đang được sử dụng. Một session cũ của tài khoản quản trị còn trong client có thể khiến request không chạy dưới principal mà người viết test nghĩ tới.

## 5. Các ca truy cập chéo cần có

### 5.1. Chéo chủ thể trong cùng tenant

Giữ nguyên credential của Alice, thay đối tượng từ A1 sang A2. Kiểm tra riêng từng hành động đọc, sửa và xóa theo ma trận.

Không chỉ kiểm tra chức năng đọc. Backend có thể kiểm tra owner ở `GET` nhưng quên ở một đường cập nhật, tải file hoặc tạo bản export.

### 5.2. Chéo tenant

Dùng chủ thể thuộc A truy cập B1 bằng một định danh hợp lệ đã biết trong fixture. Kiểm tra cả trường hợp có cùng tên role ở hai tenant.

Không dựa trên việc B1 khó đoán ID để coi ranh giới đã an toàn. Test cần cung cấp ID thật trong môi trường thử nghiệm để đi tới đúng điều kiện authorization.

Những trường tenant do client gửi ở path, query, body hoặc header không được tự thay thế tenant của principal và tenant thực tế của đối tượng. Ca test cần kiểm tra sự bất nhất đó theo hợp đồng API.

### 5.3. Cùng đối tượng nhưng khác hành động

Reader-A được đọc A1 nhưng không được sửa hoặc xóa. Auditor-A đọc được A2 nhưng không có quyền thay nội dung. Các ca này phát hiện việc backend dùng một cờ chung “có thể truy cập” cho mọi hành động.

Quyền gọi chức năng quản trị và quyền quản trị một đối tượng cụ thể cũng cần tách biệt. Nếu hệ thống có admin theo dự án hoặc tenant, phải có ca chứng minh role đó không vượt phạm vi được cấp.

## 6. Kiểm tra mọi nơi đối tượng được tham chiếu

Đối tượng không chỉ xuất hiện trong một path dạng `/documents/{id}`.

| Đường tham chiếu | Ví dụ minh họa | Điều cần kiểm thử |
|---|---|---|
| Path parameter | Đọc một tài liệu theo ID | Quyền trên chính tài liệu đó |
| Query parameter | Lọc theo project hoặc owner | Bộ lọc không mở rộng tập được phép xem |
| Request body | Gửi `documentId` để sửa hoặc xử lý | Không bỏ kiểm tra vì ID nằm trong body |
| Danh sách ID | Batch tải hoặc cập nhật nhiều tài liệu | Quyền được áp dụng cho từng phần tử theo hợp đồng |
| Quan hệ cha-con | Project, document và attachment | Tài nguyên con thực sự thuộc cha đã chỉ định và được phép truy cập |
| Job bất đồng bộ | Tạo export rồi tải kết quả | Quyền tạo, xem trạng thái và lấy kết quả đều được kiểm soát |
| Kênh sự kiện | Subscribe cập nhật của tài liệu | Subscription và dữ liệu phát ra đúng phạm vi |
| Link tải hoặc chuyển hướng | Tải tệp đính kèm | Không tạo hoặc trả capability ngoài quyền được phép |

Các ví dụ là hình dạng API minh họa, không phải các endpoint có sẵn trong một hệ thống cụ thể.

Nếu có nhiều giao diện như REST, truy vấn dạng graph, WebSocket hoặc API nội bộ, cần kiểm tra những điểm thực thi tương ứng trong phạm vi tích hợp. Việc một route đã an toàn không tự bảo đảm route khác gọi cùng dữ liệu cũng áp dụng quyền.

Thay `ownerId` hoặc `tenantId` trong payload còn có thể là vấn đề field-level hoặc mass assignment. Cần thêm test cho quy tắc cập nhật các trường này, đồng thời không làm mất test quyền trên đối tượng ban đầu.

## 7. Đối tượng lồng nhau, collection và batch

### 7.1. Không chỉ kiểm tra quyền trên đối tượng cha

Giả sử endpoint nhận cả project ID và attachment ID. Một ca cần kiểm tra trường hợp project thuộc phạm vi được phép nhưng attachment thực tế thuộc một project hoặc tài liệu khác.

```text
Principal có quyền trên project A
+ request khai project A
+ attachment thực tế thuộc một tài liệu không được phép
-> không được đọc attachment chỉ vì kiểm tra project đã pass
```

Backend cần xác minh quan hệ thực tế giữa các đối tượng, không chỉ kiểm tra độc lập rằng từng ID tồn tại hoặc tin quan hệ do client tự khai.

### 7.2. Collection và tìm kiếm

Test danh sách phải kiểm tra tập dữ liệu thực tế, không chỉ status code hoặc số phần tử đầu tiên. Pagination có thể vô tình áp dụng lọc quyền ở một trang nhưng không ở trang tiếp theo.

Cần xét cả tổng số, facet, dữ liệu gợi ý, kết quả tìm kiếm và metadata nếu chính sách giới hạn việc tiết lộ sự tồn tại của đối tượng. Không nhất thiết mọi số liệu tổng hợp đều phải bị ẩn, nhưng hành vi phải đúng hợp đồng đã xác định.

Một ca hữu ích là dựng dữ liệu đủ để đối tượng không được phép nằm ở những vị trí khác nhau trong tập kết quả, rồi kiểm tra qua các trang mà không phụ thuộc thứ tự ngẫu nhiên.

### 7.3. Batch chứa cả đối tượng được phép và không được phép

Gửi một batch gồm A1 và A2 dưới danh tính Alice. Trước khi test, phải biết API dùng hợp đồng nào:

- Từ chối toàn bộ batch và không thực hiện thay đổi nghiệp vụ nào.
- Xử lý riêng từng phần tử, chỉ thực hiện các phần được phép và trả kết quả từng phần phù hợp.

Không tự giả định một trong hai là đúng cho mọi API. Trong cả hai trường hợp, phần tử không được phép không được bị đọc hoặc thay đổi ngoài hợp đồng.

Với batch ghi, chỉ một mã lỗi tổng chưa chứng minh không có cập nhật một phần trái phép. Cần kiểm tra trạng thái từng đối tượng sau xử lý.

## 8. Oracle của test phải gồm dữ liệu và tác động nghiệp vụ

Oracle là cơ sở dùng để kết luận kết quả đúng hay sai. Trong kiểm thử quyền, chỉ nhìn HTTP status thường chưa đủ.

Một request bị từ chối có thể dùng `403`, hoặc có thể trả `404` để không công bố sự tồn tại theo hợp đồng. Request thiếu credential hợp lệ lại thuộc lớp authentication. Không viết test chấp nhận mọi mã `4xx` như thể chúng đều chứng minh kiểm tra quyền đã chạy đúng.

Ngoài status và cấu trúc lỗi, cần kiểm tra:

- Không có nội dung hoặc thuộc tính tài nguyên bị cấm trong response.
- Không có link tải, redirect hoặc artifact giúp lấy dữ liệu ngoài quyền.
- Trạng thái nghiệp vụ không bị thay đổi trái phép.
- Không có job, message hoặc tác vụ ngoài hệ thống được tạo trái phép.
- Audit phản ánh đúng một nỗ lực bị từ chối nếu hợp đồng yêu cầu ghi nhận.

Ví dụ, một endpoint cập nhật A2 rồi mới trả `403` cho Alice là lỗi nghiêm trọng dù test status đơn giản sẽ pass.

Khi đối chiếu trạng thái, cần chọn đúng dữ liệu nghiệp vụ của fixture. Một bản ghi audit về request bị từ chối có thể là tác động được mong đợi; không nên coi mọi thay đổi trong toàn database đều là vi phạm.

Các kiểm tra response cũng cần theo chính sách tiết lộ của hệ thống. Không yêu cầu giấu mọi dấu hiệu tồn tại nếu nghiệp vụ chủ ý cho phép thấy metadata, nhưng phải kiểm tra đúng ranh giới giữa metadata được thấy và nội dung không được thấy.

## 9. Ví dụ test tham số hóa

Pseudocode sau minh họa cách tách kỳ vọng, danh tính và bằng chứng. Nó không phụ thuộc một framework hoặc thư viện cụ thể:

```text
cases = [
    {actor: Alice,     object: A1, action: READ,   expected: ALLOW},
    {actor: Alice,     object: A2, action: READ,   expected: DENY},
    {actor: ReaderA,   object: A1, action: UPDATE, expected: DENY},
    {actor: AuditorA,  object: A2, action: READ,   expected: ALLOW},
    {actor: AuditorA,  object: B1, action: READ,   expected: DENY}
]

for case in cases:
    fixture = createIsolatedFixtureFor(case)
    credential = obtainValidTestCredential(case.actor)
    before = snapshotRelevantBusinessState(fixture)

    response = callRealApplicationBoundary(
        credential,
        case.action,
        fixture.objectFor(case.object)
    )

    if case.expected == ALLOW:
        assertAllowedResultMatchesContract(response, fixture)
    else:
        assertDenialMatchesContract(response)
        assertNoForbiddenDataOrArtifact(response, fixture)
        assertNoUnauthorizedBusinessEffect(before, fixture)

    assertExpectedSecurityEvidence(case, fixture)
    cleanupOnlyThisFixture(fixture)
```

`obtainValidTestCredential` cần tạo danh tính thử nghiệm đúng actor, issuer, tenant và audience của ứng dụng. Không dùng một token không hợp lệ để đại diện cho mọi ca từ chối object-level.

`callRealApplicationBoundary` phải đi qua điểm thực thi quyền mà ca test muốn đánh giá. Một test gọi thẳng repository hoặc mock thành phần authorization trả `DENY` chưa chứng minh HTTP handler thực sự áp dụng quyết định đó.

Snapshot và cleanup chỉ thao tác dữ liệu thuộc fixture tương ứng. Ca lỗi cũng cần được xử lý dọn dẹp theo cơ chế của môi trường test, tránh để trạng thái cũ làm thay đổi kết quả lần chạy sau.

## 10. Kết hợp các lớp kiểm thử

| Lớp kiểm thử | Chứng minh được gì? | Phần còn cần lớp khác |
|---|---|---|
| Unit test policy | Quy tắc cho tổ hợp chủ thể, hành động và quan hệ | Không tự chứng minh handler gọi policy hoặc truyền dữ liệu đúng |
| Integration test backend | Principal, truy vấn tài nguyên và enforcement phối hợp đúng | Có thể chưa bao phủ gateway, proxy hoặc cấu hình triển khai |
| API hoặc end-to-end test | Đường request thực tế giữ đúng ranh giới | Thường chậm hơn và cần fixture, credential ổn định |
| Kiểm thử job và sự kiện | Worker, subscription và artifact giữ đúng quyền | Cần xét thời điểm đánh giá và trạng thái thay đổi |

Ở unit test, có thể dùng các tổ hợp policy rõ ràng và dữ liệu giả lập. Ở integration test, cần kiểm tra rằng tenant hoặc owner được lấy từ nguồn đáng tin và quan hệ tài nguyên đúng, không chỉ từ request body.

Với backend dựa trên context từ gateway, kiểm thử hợp đồng tin cậy giữa hai thành phần. Nếu triển khai có đường gọi backend trực tiếp, cần xác nhận đường đó không nhận header danh tính tự khai như bằng chứng hợp lệ. Nếu backend chỉ nhận kết nối từ thành phần trung gian được xác thực, test cần phản ánh đúng bảo đảm đó.

Không mock hết điểm thực thi rồi coi đó là coverage đầy đủ. Mỗi mock cần có giới hạn được hiểu rõ, và ít nhất những ranh giới quan trọng phải có bằng chứng qua đường thực tế tương ứng.

## 11. Thay đổi quyền, cache và thời điểm thực thi

Quyền trên đối tượng có thể thay đổi sau khi một phiên hoặc token đã được tạo.

Một kịch bản kiểm thử cần thiết:

1. Reader-A có quyền đọc A1 và đọc thành công.
2. Thu hồi quan hệ chia sẻ bằng cơ chế thuộc phạm vi thử nghiệm.
3. Thử lại bằng phiên hoặc token cũ theo các thời điểm đã xác định.
4. Kiểm tra thời điểm mất quyền theo hợp đồng và giới hạn propagation của hệ thống.
5. Xác nhận trạng thái đã thu hồi không bị một cache hoặc sự kiện cũ khôi phục sai.

Không chỉ lấy token mới rồi kết luận các phiên cũ đã mất quyền. Đồng thời, không đòi hệ thống phải có thu hồi tức thời nếu hợp đồng đã xác định một khoảng trễ khác; điều cần kiểm chứng là mục tiêu và giới hạn thực tế được thực thi đúng.

Cache quyết định phải có ngữ cảnh phù hợp. Test cần chứng minh cache cho Alice đọc A1 không được dùng cho Bob, cho A2, cho tenant B hoặc cho hành động sửa.

Với thao tác nhạy cảm có khoảng cách giữa kiểm tra quyền và commit, cần xác định hợp đồng khi quyền hoặc owner thay đổi trong khoảng đó. Có thể dùng các điểm đồng bộ có kiểm soát trong test để tạo đúng thứ tự sự kiện, thay vì dựa vào một race ngẫu nhiên khó lặp lại.

Với export hoặc job bất đồng bộ, cũng cần xác định quyền được đánh giá tại lúc yêu cầu, lúc xử lý và lúc tải kết quả như thế nào. Nếu hợp đồng yêu cầu kiểm tra lại, phải có test cho việc quyền bị thu hồi giữa các thời điểm đó.

## 12. Các đường trả dữ liệu cần kiểm tra riêng

### 12.1. Export và artifact

Người không được đọc A2 không nên được tạo hoặc tải một bản export chứa A2 qua một endpoint khác, trừ khi chính sách có một quyền riêng được cấp rõ ràng cho chức năng đó.

Cần kiểm tra quyền xem trạng thái job, tải file kết quả, liệt kê các export và thời hạn truy cập artifact. Một job ID khó đoán vẫn không thay thế hợp đồng quyền truy cập kết quả.

### 12.2. Link tải có quyền theo thời hạn

Một link tải được ký có thể là capability cho phép người cầm link dùng trong điều kiện nhất định. Kiểm thử phải bám đúng hợp đồng: ai được phát hành link, nó áp dụng cho đối tượng nào, thời hạn ra sao và có ràng buộc bổ sung nào không.

Không mặc định mọi link phải mất hiệu lực ngay khi logout nếu cơ chế không hỗ trợ điều đó. Tuy nhiên, phải xác nhận hành vi thực tế không vượt các giới hạn đã công bố, và người không có quyền không được tự xin link cho đối tượng bị cấm.

### 12.3. Subscription và cache nội dung

Nếu Alice được subscribe vào cập nhật A1, việc thử đổi tham chiếu sang A2 phải đi qua kiểm tra quyền phù hợp. Khi quyền bị thay đổi, kiểm tra cách hệ thống xử lý subscription còn mở theo hợp đồng.

Cache response hoặc nội dung cũng cần giữ đúng phạm vi người dùng và tenant. Một response A1 trả đúng cho Alice nhưng bị tái sử dụng cho chủ thể không được phép vẫn là vi phạm, dù logic policy ban đầu không sai.

## 13. Làm test lặp lại được và bảo vệ dữ liệu thử nghiệm

Mỗi ca cần có fixture, principal và policy version rõ ràng. Tài nguyên dùng chung giữa nhiều test song song dễ gây kết quả không ổn định khi một ca thay owner, chia sẻ hoặc xóa dữ liệu của ca khác.

Nên dùng không gian dữ liệu thử nghiệm được tách biệt, định danh duy nhất trong phạm vi lần chạy và cách dọn đúng các tài nguyên đã tạo. Không dùng hồ sơ, token hoặc đối tượng production để kiểm tra quyền ngoài phạm vi được phép.

Khi test thời hạn hoặc propagation, có thể dùng clock điều khiển được ở lớp thích hợp và cơ chế chờ có giới hạn cho integration test. Không dùng một khoảng sleep dài tùy ý rồi coi việc cuối cùng bị từ chối là bằng chứng đáp ứng mục tiêu thời gian.

Báo cáo cần giúp xác định actor, tenant, nhóm hành động, fixture và kết quả mà không ghi credential. Dữ liệu response trong bằng chứng lỗi cũng cần được giới hạn, kể cả khi fixture thường là tổng hợp.

Trong CI, tách các ca nhanh kiểm tra policy khỏi những ca tích hợp cần IdP hoặc hệ thống bất đồng bộ, nhưng vẫn giữ khả năng truy vết tới cùng yêu cầu nghiệp vụ. Không bỏ ca chéo tenant chỉ vì nó khó dựng dữ liệu hơn một ca owner đơn giản.

## 14. Đánh giá coverage và xử lý ca thất bại

Coverage nên phản ánh các ranh giới đã kiểm chứng, không chỉ số test hoặc phần trăm dòng mã chạy qua.

Một bảng truy vết có thể ghi:

| Ranh giới | Bằng chứng cần có |
|---|---|
| Owner và người không có quan hệ | Cùng chức năng, khác đối tượng, positive và negative control |
| Quan hệ chia sẻ chỉ đọc | Đọc được nhưng không sửa, xóa hoặc mở sang đối tượng khác |
| Quyền đặc biệt có phạm vi | Được phép trong tenant hoặc dự án đúng, bị từ chối ngoài phạm vi |
| Tách tenant | Credential hợp lệ không vượt sang tài nguyên tenant khác |
| Quan hệ cha-con | Không truy cập tài nguyên con ngoài quan hệ thực tế được phép |
| Collection và batch | Không rò dữ liệu hoặc tạo tác động trái phép trên phần tử bị cấm |
| Vòng đời quyền | Thu hồi và thay đổi quan hệ có hiệu lực theo giới hạn đã định |
| Kênh phụ | Export, link tải, subscription và cache giữ cùng hợp đồng quyền |
| Tác động nghiệp vụ | Từ chối không đi kèm thay đổi trái phép phía sau |

Khi một ca thất bại, trước hết xác nhận fixture, actor và nguyên nhân thực sự. Một lỗi authentication, một đối tượng không tồn tại hoặc môi trường chưa đồng bộ có thể làm kết quả khác kỳ vọng mà chưa chỉ ra lỗi object-level.

Nếu kiểm tra quyền thực sự thiếu hoặc sai, cần tìm điểm thực thi và những đường gọi có cùng rủi ro. Ví dụ, bổ sung kiểm tra ở một handler chưa đủ nếu batch, export hoặc worker vẫn truy cập cùng đối tượng mà không áp dụng policy.

Một bộ test pass chỉ chứng minh những trường hợp, phiên bản và ngữ cảnh đã được chạy. Khi thêm hành động, quan hệ chia sẻ, tenant hoặc đường trả dữ liệu mới, cần cập nhật ma trận kỳ vọng và những ca kiểm chứng tương ứng.

Object-level authorization test có giá trị khi nó chứng minh cả quyền hợp lệ lẫn ranh giới phải từ chối trên tài nguyên thật của fixture. Kết hợp principal hợp lệ, kỳ vọng nghiệp vụ độc lập, kiểm tra dữ liệu và tác động phía sau giúp phát hiện những lỗi mà một kiểm tra “đã đăng nhập” hoặc một assertion status code đơn lẻ không nhìn thấy.
