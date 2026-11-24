# User visible audit context — Ngữ cảnh kiểm toán hiển thị cho người dùng

## 1. Người dùng cần hiểu lịch sử nghiệp vụ như thế nào?

Một dòng lịch sử như “Đã cập nhật” thường không đủ để giải thích điều gì vừa xảy ra. Người dùng có thể cần biết ai đã phê duyệt, số tiền nào đã thay đổi, thao tác được thực hiện trực tiếp hay qua đại diện và kết quả đã hoàn tất hay còn chờ xử lý.

**User visible audit context** là tập thông tin kiểm toán được chọn lọc và trình bày cho một người xem có quyền, giúp họ hiểu nguồn gốc và diễn biến của một hành động nghiệp vụ.

Trong bảo mật logic nghiệp vụ, ngữ cảnh này hỗ trợ:

- Nhận ra thay đổi giá, quyền hoặc trạng thái mà người dùng không thực hiện.
- Kiểm tra một phê duyệt có đến từ người phù hợp hay không.
- Phân biệt lệnh đã gửi, tác động đã commit và bước còn đang xử lý.
- Tránh gửi lại một thao tác chỉ vì chưa nhìn thấy kết quả.
- Cung cấp thông tin để yêu cầu hỗ trợ hoặc báo cáo bất thường.

Một lịch sử dành cho người dùng không phải bản sao nguyên vẹn của log nội bộ. Nó là một **khung nhìn được kiểm soát quyền**, giữ đúng sự thật nghiệp vụ và loại bỏ các chi tiết người xem không được phép biết.

Việc hiển thị lịch sử không thay thế kiểm tra quyền, business invariants, transaction hoặc idempotency. Một hệ thống vẫn phải chặn thao tác sai dù người dùng có đọc lịch sử hay không.

## 2. Tình huống xuyên suốt: lịch sử một yêu cầu hoàn tiền

Giả sử hoàn tiền R-420 thuộc tenant t-a, trị giá 750.000 VND. Quy trình yêu cầu người phê duyệt độc lập với người tạo và chỉ thanh toán sau khi có phê duyệt hợp lệ.

Một lịch sử có thể được trình bày như sau, nếu người xem có quyền thấy các thông tin tương ứng:

~~~text
Yêu cầu hoàn tiền R-420
Trạng thái hiện tại: Đang xử lý thanh toán

09:00 — Lan tạo yêu cầu hoàn tiền
Số tiền: 750.000 VND

09:05 — Minh phê duyệt yêu cầu
Số tiền được phê duyệt: 750.000 VND

09:05 — Hệ thống chuyển yêu cầu sang bước xử lý thanh toán
Kết quả thanh toán chưa được xác nhận
~~~

Lịch sử này trả lời được những câu hỏi cơ bản:

- Lan là người tạo, Minh là người phê duyệt.
- Phê duyệt áp dụng cho số tiền nào.
- Phê duyệt đã xảy ra nhưng thanh toán chưa chắc hoàn tất.
- Bước tự động không bị gán nhầm thành thao tác của người dùng.

Nếu lệnh thanh toán được retry do timeout, giao diện không nên thêm nhiều dòng “Đã hoàn tiền” như thể có nhiều tác động thành công. Nếu đối tác sau đó xác nhận lệnh, thông điệp cần phản ánh đúng nội dung xác nhận, không tự hứa thời điểm tiền có thể sử dụng trong tài khoản người nhận.

Một lần tự phê duyệt bị chặn cũng có thể tồn tại trong audit nội bộ. Việc người tạo, khách hàng hay nhân viên khác được thấy lần thử đó là quyết định về quyền và mục đích hiển thị, không phải mặc định mọi người đều thấy toàn bộ.

## 3. Tách trạng thái hiện tại, lịch sử và bằng chứng nội bộ

Ba nguồn thông tin thường bị trộn lẫn:

| Thành phần | Câu hỏi chính | Yêu cầu quan trọng |
|---|---|---|
| Trạng thái nghiệp vụ hiện tại | Đối tượng hiện đang ở bước nào? | Lấy từ nguồn có thẩm quyền cho trạng thái |
| Lịch sử người dùng được xem | Những hoạt động nào được phép hiển thị cho người này? | Lọc theo quyền, trình bày đúng ý nghĩa và nguồn gốc |
| Audit nội bộ | Quyết định và tác động đã xảy ra như thế nào? | Có bằng chứng chi tiết, tính toàn vẹn và quyền điều tra phù hợp |

### 3.1. Không suy ra trạng thái hiện tại chỉ từ dòng cuối

Lịch sử có thể được xây dựng bất đồng bộ. Database đã chuyển trạng thái nhưng projector chưa cập nhật dòng hoạt động mới.

Nếu giao diện lấy dòng cuối của timeline làm trạng thái duy nhất, người dùng có thể thấy “Chờ phê duyệt” dù thao tác đã commit. Ngược lại, một dòng “đã gửi” không chứng minh đã phê duyệt.

Nên có hợp đồng rõ ràng giữa trạng thái hiện tại và lịch sử. Khi hai phần có độ mới khác nhau, giao diện cần thể hiện sự khác biệt thay vì tự suy đoán.

### 3.2. Không gọi khung nhìn giới hạn là toàn bộ audit

Người dùng có thể chỉ được xem một số loại sự kiện, một khoảng thời gian hoặc một phần thông tin tác nhân.

Tiêu đề như “Các hoạt động bạn được phép xem” chính xác hơn “Toàn bộ bằng chứng hệ thống” khi phạm vi không đầy đủ.

Không cần thông báo rằng có một sự kiện điều tra bí mật đang bị ẩn. Cần mô tả phạm vi hợp lệ mà không làm lộ sự tồn tại của dữ liệu nhạy cảm.

### 3.3. Lịch sử không tự chứng minh ý chí của người thật

Một bản ghi cho biết hệ thống đã xử lý hành động dưới danh tính đã xác thực. Nó không tự chứng minh chủ tài khoản thực sự ngồi trước thiết bị hoặc đồng ý với hành động nếu tài khoản đã bị chiếm đoạt.

Không thêm nhãn “Không thể chối bỏ” hay “Chắc chắn do bạn thực hiện” chỉ vì có user ID. Người dùng cần có cách báo cáo hoạt động không nhận ra.

## 4. Một mục hoạt động nên có những gì?

| Nhóm thông tin | Nội dung hữu ích | Giới hạn cần xét |
|---|---|---|
| Hành động | Tạo yêu cầu, thay đổi giá, phê duyệt, hủy | Tên nghiệp vụ, không phải câu SQL hoặc tên hàm |
| Đối tượng | Yêu cầu hoặc đơn hàng liên quan | Chỉ định danh và liên kết trong phạm vi được xem |
| Người thực hiện | Người dùng, nhân viên đại diện hoặc hệ thống | Hiển thị theo quyền, không gán nhầm chủ thể |
| Thời gian | Thời điểm hoạt động xảy ra | Phân biệt với thời điểm nhận hoặc dựng trang |
| Kết quả | Đã commit, bị từ chối, đang xử lý, chưa xác định | Không khẳng định thành công quá sớm |
| Nội dung thay đổi | Giá trị trước/sau cần thiết | Chỉ các trường và giá trị được phép công khai |
| Ngữ cảnh | Thực hiện qua đại diện, luồng phê duyệt phù hợp | Không lộ grant, token hoặc tín hiệu nhạy cảm |
| Lý do | Lý do do người thao tác nhập hoặc mã lý do công khai | Phân biệt lời khai với dữ kiện đã xác minh |
| Tra cứu | Mã hoạt động hoặc đường hỗ trợ | Không biến mã thành quyền truy cập |
| Liên kết | Hoạt động gốc, đính chính hoặc kết quả liên quan | Mỗi lần mở vẫn kiểm tra quyền |

Không phải mọi mục đều cần đủ mọi trường. Một mục “Hệ thống đã chuyển sang xử lý thanh toán” không cần hiển thị tên workload nội bộ, host hoặc trace ID.

### 4.1. Dùng từ ngữ nghiệp vụ ổn định

Nên hiển thị “Minh phê duyệt yêu cầu hoàn tiền” thay vì “UPDATE refund status=2”.

Mã trạng thái có thể thay đổi khi triển khai. Ý nghĩa lịch sử cần được giữ, hoặc được chuyển đổi bằng bộ đọc có phiên bản phù hợp.

Một sự kiện PAYMENT_SUBMITTED không được đổi thành “Đã hoàn tiền” chỉ để giao diện ngắn hơn. Cách viết phải giữ đúng mức độ hoàn tất.

### 4.2. Thay đổi số tiền phải có đơn vị

Ví dụ:

~~~text
Số tiền hoàn đã thay đổi
Trước: 700.000 VND
Sau:   750.000 VND
~~~

Giao diện cần dùng currency và quy ước đơn vị của dữ liệu nguồn. Không tính toán lại từ chuỗi đã định dạng hoặc bỏ đơn vị khiến người dùng nhầm tiền tệ.

Nếu người xem không có quyền thấy số tiền cũ, không gửi nó ra trình duyệt rồi chỉ che bằng giao diện.

## 5. Trình bày đúng tác nhân và quan hệ đại diện

### 5.1. Thao tác trực tiếp

Ví dụ:

~~~text
Minh đã phê duyệt yêu cầu.
~~~

Thông điệp chỉ phù hợp khi audit xác định Minh là người thực hiện theo mô hình danh tính của hệ thống và người xem được phép thấy tên đó.

Không lấy tên từ trường actorName do client tự gửi. Danh tính phải gắn với chủ thể đã được xác minh ở phía máy chủ.

### 5.2. Thao tác qua nhân viên hỗ trợ

Giả sử support-9 thao tác thay mặt customer-42 trong một phiên hỗ trợ hợp lệ.

Nếu chỉ hiển thị “Khách hàng đã thay đổi yêu cầu”, lịch sử sẽ quy sai hành động cho khách hàng.

Một cách trình bày phù hợp khi được phép:

~~~text
Nhân viên hỗ trợ Hà đã cập nhật thông tin thay mặt khách hàng.
Thực hiện trong phiên hỗ trợ được cấp quyền.
~~~

Nếu tên nhân viên không được công khai cho nhóm người xem này:

~~~text
Nhân viên hỗ trợ đã cập nhật thông tin thay mặt khách hàng.
~~~

Việc giới hạn danh tính không được làm sai bản chất tác nhân. Không biến nhân viên thành khách hàng, cũng không biến người dùng thành “Hệ thống” chỉ vì không muốn hiển thị tên.

Các thông tin như grant ID, phạm vi quyền chi tiết hoặc thông tin xác thực của phiên hỗ trợ thường không cần xuất hiện trên timeline người dùng.

### 5.3. Hoạt động tự động

Một scheduler hoặc worker không nên bị gán cho tài khoản admin mặc định.

Có thể hiển thị:

~~~text
Hệ thống tự động chuyển yêu cầu sang bước đối chiếu.
~~~

Tên thành phần nên phục vụ sự hiểu biết của người dùng. Không cần lộ service account, địa chỉ máy hoặc cấu trúc triển khai nếu không có mục đích được phép.

Nếu hoạt động tự động bắt nguồn từ một yêu cầu của người dùng, có thể liên kết tới yêu cầu gốc trong phạm vi quyền thay vì nói người đó trực tiếp thực hiện mọi bước kỹ thuật.

### 5.4. Tài khoản đổi tên hoặc không còn hiển thị

Không nên phân giải lịch sử chỉ bằng email hoặc tên hiện tại. Một email có thể được tái sử dụng cho người khác.

Audit cần gắn với định danh ổn định. Khung nhìn có thể dùng tên tại thời điểm hành động, tên hiện tại hoặc nhãn đã giảm nhận dạng theo chính sách. Cách lựa chọn cần nhất quán và không đánh đồng hai người.

Nếu danh tính không còn được phép hiển thị, dùng nhãn phù hợp như “Danh tính không còn hiển thị”. Không bịa tên, không đổi actor cũ thành một tài khoản mới có cùng email.

## 6. Quyền xem lịch sử là quyền theo đối tượng và dữ liệu

Có quyền đọc một đơn hàng chưa chắc đồng nghĩa có quyền đọc mọi thông tin audit liên quan đến nó.

Ví dụ, khách hàng có thể xem trạng thái và số tiền, nhưng không được thấy ghi chú điều tra hoặc thông tin phân công nhân sự nội bộ.

Cần xét nhiều lớp quyền:

~~~text
Người xem đã xác thực
    -> đúng tenant hoặc phạm vi truy cập
    -> được xem đối tượng
    -> được xem loại hoạt động
    -> được xem từng nhóm trường
    -> được mở tài nguyên hoặc bản xuất liên quan
~~~

### 6.1. Kiểm tra ở phía máy chủ

Endpoint lịch sử phải xác minh quyền trên đối tượng được yêu cầu. Đổi refund ID trong URL không được làm lộ lịch sử của tenant khác.

Việc dùng UUID, mã khó đoán hoặc ID công khai riêng không thay thế kiểm tra quyền. Mã hoạt động cũng không phải bearer token cấp quyền xem.

Không tải toàn bộ audit xuống client rồi lọc theo role bằng JavaScript. Dữ liệu đã gửi vẫn có thể bị đọc qua công cụ mạng.

### 6.2. Kiểm tra lại ở trang tiếp theo và phần chi tiết

Cursor, nút “Xem thêm” hoặc liên kết một hoạt động không được cấp quyền vĩnh viễn.

Khi người dùng đổi tenant, bị thu hồi quyền hoặc chuyển chế độ đại diện, các lần truy vấn tiếp theo cần áp dụng ngữ cảnh mới theo mô hình quyền của hệ thống.

Cursor nên được kiểm soát tính toàn vẹn và gắn với phạm vi truy vấn thích hợp. Không nhận một cursor của đối tượng khác rồi tin rằng nó đã được cấp quyền từ trước.

### 6.3. Lọc cả sự tồn tại của sự kiện

Che nội dung một ghi chú điều tra nhưng vẫn hiển thị “Một ghi chú điều tra đã được tạo” có thể làm lộ thông tin nhạy cảm.

Đối với mỗi loại sự kiện, phải quyết định:

- Có được tiết lộ sự tồn tại của hoạt động không?
- Nếu có, trường nào được hiển thị?
- Tác nhân và lý do được chi tiết đến mức nào?
- Liên kết nào được cung cấp?

Không suy ra rằng xóa vài trường khỏi JSON là đủ cho mọi trường hợp.

### 6.4. Tổng số và khoảng trống cũng có thể làm lộ thông tin

Nếu người dùng được thấy 3 sự kiện nhưng API trả totalCount bằng 10, họ có thể biết có thêm hoạt động bị ẩn.

Tương tự, sequence nội bộ hoặc danh sách ID liên tiếp có thể làm lộ cấu trúc lịch sử không cần thiết.

Pagination và tổng số nên được định nghĩa theo khung nhìn được phép, hoặc không công khai tổng nếu không cần. Không gửi thống kê nội bộ rồi trông cậy giao diện bỏ qua.

## 7. Thiết kế một khung nhìn công khai từ audit

Một kiến trúc minh họa:

~~~mermaid
flowchart TD
    A["Thay đổi nghiệp vụ và sự kiện cùng transaction"] --> B["Outbox hoặc nguồn sự kiện đã commit"]
    B --> C["Audit nội bộ và dữ liệu hoạt động"]
    C --> D["Khung nhìn ứng viên có liên kết nguồn"]
    D --> E["Kiểm tra quyền hiện tại của người xem"]
    E --> F["Lọc sự kiện và trường theo đối tượng, vai trò"]
    F --> G["Ánh xạ tên hành động, tác nhân và dữ liệu an toàn"]
    G --> H["API lịch sử dành cho người dùng"]
    H --> I["Timeline hoặc trang chi tiết hoạt động"]
~~~

Sơ đồ tập trung vào sự kiện thành công. Các lần từ chối hoặc lỗi có thể cần đường ghi riêng để không mất theo rollback; chỉ được đưa vào khung nhìn khi chính sách cho phép.

### 7.1. Khung nhìn là dữ liệu dẫn xuất

Có thể lưu một read model để tìm kiếm và phân trang nhanh. Tuy nhiên, nó không nên trở thành nguồn độc lập tự tuyên bố một tác động đã xảy ra mà không có liên kết với dữ liệu có thẩm quyền.

Nên giữ được quan hệ nội bộ từ mục hoạt động đến sự kiện nguồn hoặc tác động nghiệp vụ. Quan hệ này hỗ trợ đối chiếu khi projector xử lý sai hoặc cần dựng lại khung nhìn.

Không cần gửi định danh trace, offset broker hoặc vị trí lưu log cho người dùng.

### 7.2. Tránh tạo nhiều mục cho cùng một sự kiện

Publisher và consumer có thể giao nhận lặp. Một sự kiện đã commit được nhận lại không được tạo thêm dòng phê duyệt thành công.

Read model cần định danh và ràng buộc chống lặp phù hợp, chẳng hạn trên sự kiện nguồn và kiểu mục được tạo. Nếu một tác động có nhiều sự kiện kỹ thuật, phải xác định sự kiện nào tạo hoạt động nghiệp vụ.

Không gom mọi sự kiện cùng command thành một dòng nếu command thực sự có nhiều bước cần phân biệt, như phê duyệt và xác nhận thanh toán.

### 7.3. Không đóng băng quyền lúc tạo khung nhìn

Nếu projector từng cho phép một vai trò thấy dữ liệu, điều đó không có nghĩa mọi người thuộc vai trò đó luôn được xem về sau.

Có thể tiền xử lý dữ liệu, nhưng việc phục vụ kết quả phải áp dụng quyền hiện hành và mô hình thu hồi đã thiết kế. Một blob JSON đã dựng cho người quản trị không được dùng lại cho khách hàng.

Cache cũng phải xét phạm vi người xem và các điều kiện quyền liên quan. Cache theo mỗi refund ID là không đủ nếu các nhóm người xem được thấy những trường khác nhau.

## 8. Hợp đồng API hiển thị hoạt động

Một response minh họa cho người được phép xem tên người phê duyệt và số tiền:

~~~json
{
  "resource": {
    "reference": "R-420",
    "currentStatus": "PROCESSING_PAYMENT"
  },
  "view": {
    "titleKey": "refund.activity.visible_history",
    "generatedAt": "2026-11-22T02:10:00Z",
    "historyStatus": "AVAILABLE"
  },
  "items": [
    {
      "activityId": "activity-7d42",
      "type": "REFUND_APPROVED",
      "occurredAt": "2026-11-22T02:05:00Z",
      "actor": {
        "kind": "PERSON",
        "displayName": "Minh",
        "actingMode": "DIRECT"
      },
      "result": "APPLIED",
      "details": {
        "approvedAmountMinor": 750000,
        "currency": "VND"
      }
    },
    {
      "activityId": "activity-8a16",
      "type": "PAYMENT_PROCESSING_STARTED",
      "occurredAt": "2026-11-22T02:05:10Z",
      "actor": {
        "kind": "SYSTEM",
        "displayName": "Hệ thống",
        "actingMode": "AUTOMATED"
      },
      "result": "PENDING",
      "details": {}
    }
  ],
  "nextCursor": null
}
~~~

Các trường và tập giá trị do ứng dụng tự định nghĩa.

### 8.1. generatedAt không chứng minh lịch sử đã đầy đủ

generatedAt là thời điểm dựng response. Nó không tự nói rằng mọi sự kiện trước thời điểm đó đã được nhận hoặc đã xử lý.

AVAILABLE chỉ cho biết khung nhìn có thể phục vụ theo hợp đồng đã định nghĩa. Không nên diễn giải thành “toàn bộ audit đã được đối chiếu và không thiếu”.

Nếu cần cam kết độ mới mạnh hơn, phải có cơ chế theo dõi tiến độ nguồn phù hợp. Lấy timestamp lớn nhất của một sự kiện không chứng minh không còn khoảng trống trước nó.

### 8.2. Type ổn định, nội dung được bản địa hóa

Client có thể ánh xạ REFUND_APPROVED sang câu tiếng Việt. Không phân tích chuỗi “đã duyệt” để quyết định trạng thái hoặc cho phép hành động.

Dữ liệu động như displayName phải được hiển thị an toàn. Không coi chuỗi từ API là HTML tin cậy.

### 8.3. Activity ID hỗ trợ truy vấn, không cấp quyền

ID có thể giúp liên kết tới trang chi tiết hoặc yêu cầu hỗ trợ. Endpoint nhận ID đó vẫn cần tìm phạm vi và kiểm tra quyền.

Không tạo một đường “xem chi tiết audit” bỏ qua kiểm tra tài nguyên chỉ vì link đã được phát từ trang lịch sử.

## 9. Ví dụ tổ chức tầng Java phục vụ lịch sử

Mã dưới đây là mã giả theo phong cách Java. Các lớp và phương thức là hợp đồng minh họa, không phải API thư viện có sẵn.

~~~java
ActivityPage listActivities(
        VerifiedViewer viewer,
        String refundId,
        String cursorValue) {

    Refund refund = refunds.findWithinViewerScope(
        refundId, viewer);

    access.requireCanViewActivityHistory(viewer, refund);

    VisibilityPlan visibility =
        activityPolicy.resolveVisibility(viewer, refund);

    PageCursor cursor = cursors.validateForRequest(
        cursorValue,
        refund.id(),
        viewer.accessScope());

    // Hợp đồng: chọn cửa sổ theo khung nhìn được phép;
    // không công khai tổng hoặc cursor của audit thô.
    VisibleWindow window = history.loadVisibleWindow(
        refund.id(), cursor, visibility);

    List<PublicActivity> items = window.entries().stream()
        .map(entry -> activityPresenter.toPublicActivity(
            entry, viewer, visibility))
        .toList();

    return pages.create(
        refund.currentStatus(),
        items,
        window.publicNextCursor(),
        clock.instant());
}
~~~

Các điều kiện cần giữ:

- VerifiedViewer được tạo từ xác thực và ngữ cảnh tenant, đại diện đã xác minh.
- Quyền xem lịch sử được kiểm tra riêng theo mô hình ứng dụng.
- VisibilityPlan quyết định cả sự kiện được thấy và trường được phép xuất.
- Presenter không serialize nguyên entity audit hoặc exception nội bộ.
- Cursor được kiểm tra cho phạm vi đang yêu cầu, không thay thế quyền.
- Trạng thái hiện tại không được suy ra tùy ý từ mục cuối của window.
- Lỗi truy vấn không được biến thành danh sách rỗng rồi gọi là “không có hoạt động”.

Trong triển khai thực tế, việc lọc và phân trang phải phối hợp. Chỉ lấy một trang audit thô rồi loại các mục ẩn có thể tạo trang rỗng, làm lộ tổng số hoặc bỏ sót dữ liệu khi chuyển cursor.

Cần xác định thứ tự ổn định, ranh giới cửa sổ và cách xử lý khi quyền hoặc dữ liệu thay đổi giữa các trang. Một snapshot truy vấn có thể hỗ trợ tính nhất quán nhưng vẫn không được dùng để vượt mô hình thu hồi quyền.

## 10. Thời gian, thứ tự và độ trễ hiển thị

### 10.1. Phân biệt lúc xảy ra và lúc hiển thị

Một worker có thể xử lý lệnh lúc 09:05 nhưng projector nhận sự kiện lúc 09:07.

Nếu có dữ liệu đáng tin cậy, timeline nên dùng thời điểm hoạt động xảy ra và thể hiện độ trễ khi cần. Không đổi thời điểm hành động thành lúc projector nhận chỉ để trông như cập nhật tức thì.

Ngược lại, nếu chỉ biết thời điểm tiếp nhận, không bịa một occurredAt chính xác hơn. Cần xác định ý nghĩa trường và cách ghi nhãn phù hợp.

### 10.2. Timestamp không luôn đủ để sắp thứ tự

Đồng hồ giữa các dịch vụ có thể lệch. Hai sự kiện có cùng timestamp cũng có thể có thứ tự nghiệp vụ rõ ràng.

Có thể cần phiên bản đối tượng, thứ tự sự kiện theo đối tượng hoặc liên kết nhân quả ở tầng xử lý. Không cần hiển thị toàn bộ thông tin kỹ thuật đó cho người dùng, nhưng cách sắp xếp phải có căn cứ.

Không ghép các sự kiện từ nhiều nguồn thành một chuỗi chắc chắn chỉ vì thời gian hiển thị gần nhau.

### 10.3. Múi giờ phải rõ ràng

Nếu giao diện hiển thị giờ địa phương, cần biết đang dùng múi giờ nào. Khi người dùng đổi múi giờ, cùng một hoạt động vẫn phải trỏ tới cùng thời điểm.

Định dạng ngày mơ hồ hoặc chỉ ghi “hôm qua” có thể gây khó đối chiếu. Có thể dùng nhãn tương đối để đọc nhanh và cung cấp ngày giờ đầy đủ khi cần.

### 10.4. Trạng thái mới nhưng lịch sử còn cập nhật

Nếu hệ thống biết lịch sử đang chậm, có thể hiển thị:

~~~text
Trạng thái hiện tại: Đã phê duyệt

Lịch sử hoạt động đang được cập nhật.
Bạn không cần gửi lại lệnh phê duyệt.
~~~

Câu cuối chỉ phù hợp khi hệ thống đã biết lệnh được phê duyệt. Nếu chưa biết kết quả, phải nói đúng mức độ chưa xác định và hướng người dùng tra cứu.

Một danh sách trống do lỗi hoặc độ trễ không được trình bày như bằng chứng rằng chưa từng có hoạt động.

## 11. Lý do, thay đổi dữ liệu và đính chính

### 11.1. Lý do do người thao tác nhập là lời khai

Ví dụ:

~~~text
Lý do người thao tác cung cấp:
“Điều chỉnh theo đề nghị của khách hàng.”
~~~

Đây là nội dung do một chủ thể khai báo. Nó không tự chứng minh khách hàng đã đồng ý hoặc dữ kiện được nêu là đúng.

Không chuyển nó thành câu khẳng định của hệ thống như “Khách hàng đã xác nhận điều chỉnh” nếu không có bằng chứng riêng.

Ghi chú có thể chứa dữ liệu cá nhân, nội dung không phù hợp hoặc ký tự đặc biệt. Cần giới hạn độ dài, xử lý hiển thị an toàn và áp dụng quyền xem.

### 11.2. Before/after phải lọc theo từng trường

Không gửi toàn bộ object cũ và mới để frontend tự tạo diff. Một object có thể chứa dữ liệu người xem không được biết.

Cần xác định:

- Người xem có được biết trường đó đã thay đổi không?
- Có được xem giá trị trước và sau không?
- Có cần giảm độ chi tiết hoặc che một phần không?
- Việc kết hợp nhiều trường có làm lộ dữ liệu khác không?

Nếu sự tồn tại của thay đổi là nhạy cảm, việc hiển thị “Một trường bí mật đã đổi” vẫn có thể vượt phạm vi.

### 11.3. Đính chính không được âm thầm viết lại lịch sử

Nếu một mục hiển thị sai do dữ liệu nguồn cần đính chính, nên có cơ chế ghi nhận chỉnh sửa có thẩm quyền và liên kết với thông tin trước đó theo chính sách.

Ví dụ:

~~~text
Thông tin hoạt động trước đã được đính chính.
Nội dung cập nhật: số tiền được phê duyệt là 750.000 VND.
~~~

Ai được thấy bản trước và lý do đính chính phụ thuộc quyền và chính sách dữ liệu. Nhưng không nên sửa một phê duyệt cũ thành tên người khác mà không có dấu vết nội bộ.

Cần phân biệt lỗi trình bày có thể dựng lại từ nguồn đúng với thay đổi chính dữ kiện nghiệp vụ. Không dùng thao tác sửa khung nhìn để hợp thức hóa một quyết định chưa từng xảy ra.

### 11.4. Lưu giữ và phạm vi hiển thị

Lịch sử người dùng có thể chỉ hiển thị một khoảng thời gian. Khi phù hợp, cần nói rõ khoảng hiển thị hoặc phạm vi tìm kiếm.

Không tìm thấy mục không tự chứng minh hành động chưa xảy ra: dữ liệu có thể ngoài cửa sổ, chưa được cập nhật hoặc không nằm trong quyền người xem.

Việc audit còn được giữ nội bộ không mặc nhiên cho mọi người quyền xem. Ngược lại, không thấy trên giao diện cũng không đồng nghĩa dữ liệu đã bị hủy.

## 12. Chi tiết, bản xuất và luồng báo cáo bất thường

### 12.1. Liên kết mở rộng vẫn cần kiểm tra quyền

Một mục hoạt động có thể liên kết tới yêu cầu gốc, hóa đơn hoặc quyết định phê duyệt. Mỗi tài nguyên đích có thể có quyền riêng.

Không vì người dùng xem được câu “Yêu cầu đã phê duyệt” mà cho phép tải toàn bộ tài liệu nội bộ của quy trình.

### 12.2. Export là một luồng truy cập dữ liệu riêng

Bản xuất có thể gom nhiều dữ liệu hơn một trang, tồn tại lâu hơn và được tạo bất đồng bộ. Cần kiểm soát:

- Phạm vi đối tượng, thời gian và trường dữ liệu.
- Quyền lúc yêu cầu và lúc cung cấp bản xuất theo mô hình thu hồi.
- Quyền của worker tạo file.
- Thời hạn truy cập, nơi lưu và vòng đời file.
- Việc tải xuống và các lần truy cập liên quan.

Không cho worker export quyền lấy mọi audit chỉ vì tác vụ chạy ở nền. Không cache một bản xuất của người quản trị rồi đưa cho khách hàng.

Link khó đoán hoặc có chữ ký không tự giải quyết mọi yêu cầu thu hồi. Nếu file đã được tải xuống, hệ thống không thể hứa thu hồi mọi bản sao bên ngoài chỉ bằng việc xóa link.

### 12.3. Giúp người dùng báo cáo hoạt động không nhận ra

Có thể cung cấp một luồng như “Tôi không nhận ra hoạt động này” hoặc “Yêu cầu kiểm tra”, nếu sản phẩm hỗ trợ.

Luồng nên dùng activity ID và ngữ cảnh đã có, không buộc người dùng sao chép token, header hoặc dữ liệu xác thực để chứng minh vấn đề.

Việc gửi báo cáo không mặc nhiên đảo ngược giao dịch. Cần giải thích rõ hệ thống đã tiếp nhận báo cáo, có tạo hồ sơ hay không và người dùng có thể theo dõi ở đâu.

Không tự kết luận tài khoản bị chiếm đoạt chỉ vì người dùng không nhận ra một dòng lịch sử. Đó là tín hiệu cần được xác minh theo quy trình.

## 13. Tình huống kiểm thử khi triển khai

Các tình huống dưới đây dùng để thiết kế kiểm thử cho một hệ thống thực tế; mã minh họa trong bài chưa phải triển khai đã được chạy.

| Tình huống | Điều cần xác minh |
|---|---|
| Đổi resource ID sang tenant khác | Không lộ hoạt động, actor, tổng số hoặc liên kết trái quyền |
| Có quyền xem tài nguyên nhưng không xem ghi chú nội bộ | Lọc đúng cả sự kiện và từng trường |
| Tái sử dụng cursor cho đối tượng khác | Bị chặn hoặc xử lý theo hợp đồng an toàn |
| Quyền bị thu hồi giữa hai trang | Trang tiếp theo áp dụng mô hình quyền hiện hành |
| Dùng cache sau khi đổi tenant hoặc chế độ đại diện | Không phục vụ khung nhìn của ngữ cảnh cũ |
| Nhân viên thao tác thay khách hàng | Không quy sai hành động cho khách hàng |
| Actor đổi tên, bị xóa hoặc email được tái sử dụng | Không gán lịch sử cho người mới |
| Cùng sự kiện được giao lại | Không tạo thêm phê duyệt hoặc tác động hiển thị giả |
| Transaction rollback | Không có mục tuyên bố tác động thành công đã commit |
| Trạng thái đã đổi nhưng projector chậm | Không khuyên gửi lại chỉ vì timeline chưa cập nhật |
| Query lịch sử lỗi | Không trả danh sách rỗng như một kết luận không có hoạt động |
| Ghi chú chứa HTML hoặc dữ liệu nhạy cảm | Hiển thị an toàn và lọc đúng quyền |
| Before/after có trường ngoài quyền | Không gửi giá trị hoặc dấu hiệu nhạy cảm không được phép |
| Có sự kiện nội bộ bị ẩn | Tổng số, cursor và giao diện không làm lộ ngoài hợp đồng |
| Đồng hồ lệch hoặc sự kiện đến sai thứ tự | Thứ tự hiển thị có căn cứ, không bịa chuỗi nhân quả |
| Dữ liệu cần đính chính | Giữ liên kết và dấu vết phù hợp, không âm thầm đổi actor |
| Export chạy sau khi quyền thay đổi | Không dùng quyền cũ để phát dữ liệu trái mô hình |
| Hoạt động ngoài cửa sổ lưu hoặc hiển thị | Không diễn giải vắng mặt thành chưa từng xảy ra |
| Khách hàng mở activity ID của người khác | Mã tham chiếu không vượt được quyền theo đối tượng |
| Người dùng gửi báo cáo bất thường | Thông báo đúng trạng thái tiếp nhận, không hứa đảo ngược giao dịch |

Cần đối chiếu nội dung hiển thị với audit nguồn và trạng thái nghiệp vụ. Chỉ kiểm tra “timeline có một dòng mới” không phát hiện được sai actor, sai số tiền hoặc một thành công được hiển thị trước commit.

### 13.1. Kiểm tra khả năng hiểu

Có thể yêu cầu người dùng trả lời từ màn hình:

- Ai thực hiện hoạt động và có đang đại diện cho ai không?
- Số tiền nào đã được phê duyệt?
- Thanh toán đã được xác nhận hay còn chờ?
- Họ có cần gửi lại lệnh không?
- Nếu không nhận ra hoạt động, bước tiếp theo là gì?

Nếu nhiều người hiểu “đang xử lý” thành “đã nhận được tiền”, cần sửa cách diễn đạt và bố cục, không chỉ thêm một biểu tượng.

### 13.2. Giám sát chất lượng khung nhìn

Có thể theo dõi độ trễ projection, lỗi ánh xạ loại sự kiện, số lần giao nhận lặp được loại và lỗi kiểm tra quyền.

Metric dùng loại hoạt động hoặc nhóm lỗi hữu hạn. User ID, resource ID và activity ID nằm ở sự kiện điều tra có quyền truy cập, không trở thành nhãn metric không giới hạn.

Một khung nhìn ngừng cập nhật cần có tín hiệu vận hành. Việc không có thêm dòng mới không đủ để kết luận hệ thống không có hoạt động.

## 14. Checklist thiết kế lịch sử người dùng được xem

Trước khi đưa audit context vào luồng sửa giá, phê duyệt, thanh toán hoặc thay đổi quyền, hãy xác định:

1. Người xem cần hiểu hành động, tác nhân, đối tượng và kết quả nào?
2. Nguồn nào chứng minh tác động đã commit, đang chờ hoặc chưa xác định?
3. Trạng thái hiện tại và lịch sử có độ mới khác nhau được trình bày ra sao?
4. Actor trực tiếp, người đại diện và hoạt động tự động có được phân biệt đúng không?
5. Quyền xem có áp dụng cho đối tượng, sự kiện, từng trường, trang tiếp theo và export không?
6. Before/after, ghi chú và dữ liệu danh tính có được lọc trước khi gửi xuống client không?
7. Retry và giao nhận lặp có tạo dòng thành công hoặc nguồn gốc sai không?
8. Thời gian, đơn vị tiền tệ và thứ tự hoạt động có được giải thích nhất quán không?
9. Đính chính, mất quyền, giới hạn thời gian hiển thị và danh tính không còn công khai được xử lý thế nào?
10. Người dùng có đường hợp lệ để hỏi hoặc báo cáo một hoạt động mà không cần cung cấp bí mật xác thực không?

Một khung nhìn audit có ích giúp người dùng hiểu điều đã xảy ra mà không cấp thêm quyền hoặc bóp méo bằng chứng. Nó cần giữ chính xác nguồn gốc tác nhân, kết quả thực tế và phạm vi người xem được biết, đồng thời phối hợp với state machine, transaction và idempotency ở phía máy chủ.
