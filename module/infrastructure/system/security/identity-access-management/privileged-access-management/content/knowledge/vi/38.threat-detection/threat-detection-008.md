# Insider misuse: phát hiện và xử lý lạm dụng đặc quyền từ bên trong

## 1. Insider misuse trong PAM là gì?

**Insider misuse** là việc một người có quan hệ nội bộ với tổ chức sử dụng quyền truy cập được cấp để thực hiện hành vi trái mục đích, phạm vi hoặc điều kiện đã được cho phép. Người đó có thể là quản trị viên, nhân viên vận hành, kỹ sư phát triển, người phê duyệt, nhân sự hỗ trợ hoặc nhà thầu được cấp quyền.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), rủi ro đặc biệt lớn vì một phiên quản trị hợp lệ có thể đọc dữ liệu nhạy cảm, thay đổi cấu hình bảo mật, cấp quyền cho người khác hoặc can thiệp vào bằng chứng. Đăng nhập thành công qua MFA và đi qua vault chỉ chứng minh một số điều kiện truy cập đã được đáp ứng; chúng không chứng minh mọi hành động trong phiên đều phù hợp.

Ví dụ, một quản trị viên được cấp quyền sửa lỗi kết nối cơ sở dữ liệu trong 30 phút nhưng dùng chính phiên đó để xuất danh sách khách hàng. Tài khoản và phiên có thể hợp lệ về mặt kỹ thuật, trong khi mục đích sử dụng quyền đã bị vượt quá.

Bài học này xem xét cách phát hiện, xác minh và xử lý hành vi như vậy trong hạ tầng quản trị, tài khoản dịch vụ và hệ thống nhạy cảm. Trọng tâm là kết nối **con người — quyền được cấp — hành động thực tế — đối tượng bị tác động — bằng chứng**, thay vì chỉ tìm một lệnh đáng ngờ.

### Không đồng nhất mọi bất thường với người nội bộ có ác ý

Cần phân biệt các khả năng sau khi một hành động bất thường xuất hiện:

| Khả năng | Ví dụ | Cách tiếp cận ban đầu |
|---|---|---|
| Lạm dụng có chủ ý | Dùng quyền bảo trì để lấy dữ liệu ngoài phạm vi công việc | Xác minh hành động, phạm vi cho phép và dấu hiệu che giấu |
| Sai sót trong vận hành | Chạy công cụ sao lưu trên nhầm máy | Kiểm tra ngữ cảnh, thiệt hại và khả năng phục hồi |
| Tài khoản bị chiếm đoạt | Kẻ khác sử dụng phiên hoặc credential của quản trị viên | Điều tra thiết bị, phiên đăng nhập và đường đi của credential |
| Nhu cầu hợp lệ nhưng hồ sơ thiếu | Xử lý sự cố khẩn cấp trước khi hoàn tất ticket | Kiểm tra quy trình break-glass và xác nhận độc lập |
| Quan sát hoặc ánh xạ sai | Tài khoản dùng chung bị gán nhầm cho một người | Sửa việc liên kết danh tính trước khi kết luận |

Các khả năng có thể đan xen. Một người nội bộ cũng có thể bị lừa thực hiện hành động, hoặc một tài khoản dịch vụ có thể bị dùng ngoài mục đích đã thiết kế. Cảnh báo nên mô tả hành vi quan sát được, chẳng hạn “xuất dữ liệu ngoài phạm vi yêu cầu”, thay vì mặc định gắn nhãn “nhân viên đánh cắp dữ liệu”.

## 2. Quyền kỹ thuật khác với quyền sử dụng theo nhiệm vụ

Một tài khoản có thể được phép chạy một câu lệnh nhưng người sử dụng chưa chắc được phép chạy câu lệnh đó trong mọi hoàn cảnh.

Phạm vi được cho phép cần có các chiều cụ thể:

- **Chủ thể:** ai được dùng quyền; ai chịu trách nhiệm cho tài khoản dịch vụ.
- **Mục đích:** sửa sự cố, triển khai, sao lưu hay kiểm toán.
- **Tài nguyên:** máy, cơ sở dữ liệu, tenant, namespace hoặc nhóm đối tượng nào.
- **Thao tác:** đọc cấu hình, khởi động dịch vụ, thay đổi quyền hay xuất dữ liệu.
- **Thời gian:** thời điểm bắt đầu, thời lượng và điều kiện gia hạn.
- **Điều kiện bổ sung:** ticket hợp lệ, người phê duyệt độc lập, thiết bị được quản lý hoặc phiên có giám sát.

Có thể biểu diễn một yêu cầu hợp lệ bằng ví dụ giả định:

```yaml
request_id: PAM-REQ-4102
requester: user-u17
purpose: repair_connection_pool
target_scope:
  - db-orders-prod
allowed_actions:
  - inspect_connection_metrics
  - update_connection_pool_config
validity:
  start: "2026-11-27T02:00:00Z"
  end: "2026-11-27T02:30:00Z"
approval:
  approved_by: user-u42
  independent_approver: true
data_export_allowed: false
```

Đây là mô hình minh họa, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm PAM. Khi triển khai thực tế, cần ánh xạ các hành động nghiệp vụ sang quyền, tài nguyên và sự kiện mà hệ thống có thể kiểm tra.

Trong ví dụ này, việc xuất bảng khách hàng không trở nên hợp lệ chỉ vì tài khoản quản trị có quyền đọc bảng. Ngược lại, một lệnh đọc thông tin kết nối có thể hoàn toàn phù hợp dù chưa từng xuất hiện trong lịch sử của người đó.

**JIT** giới hạn thời gian có quyền; **JEA** giới hạn thao tác hoặc bề mặt quản trị được phép. Hai biện pháp làm giảm cơ hội lạm dụng, nhưng hiệu quả còn phụ thuộc vào cách cấp quyền và các đường truy cập khác. Một vai trò JIT quá rộng vẫn cho phép thực hiện hành động ngoài nhiệm vụ trong khoảng thời gian ngắn.

## 3. Những dạng lạm dụng cần đưa vào mô hình đe dọa

### 3.1. Truy cập hoặc lấy dữ liệu ngoài mục đích

Người có quyền vận hành có thể đọc dữ liệu mà nhiệm vụ không cần đến, chạy truy vấn diện rộng, tạo bản xuất hoặc chuyển dữ liệu đến một nơi khác.

Ví dụ: kỹ sư chỉ cần kiểm tra độ trễ truy vấn nhưng tạo bản dump toàn bộ cơ sở dữ liệu. Muốn đánh giá tình huống, cần biết phạm vi dữ liệu, quy mô truy cập, đích đến và yêu cầu bảo trì có cho phép thao tác đó không.

Số byte đọc lớn chỉ là một dấu hiệu. Một bản sao lưu theo lịch có thể tạo nhiều lưu lượng hơn một lần lấy dữ liệu có chủ ý. Ngược lại, dữ liệu rất nhạy cảm có thể được lấy với khối lượng nhỏ.

### 3.2. Mở rộng hoặc duy trì quyền ngoài yêu cầu

Các hành vi cần quan sát gồm tạo tài khoản quản trị mới, thêm thành viên vào nhóm đặc quyền, tạo khóa truy cập, cấp vai trò quá rộng, tăng thời hạn quyền hoặc tạo đường truy cập không đi qua PAM.

Một thay đổi đơn lẻ có thể phục vụ xử lý sự cố. Rủi ro tăng khi thay đổi không gắn với yêu cầu được duyệt, người hưởng quyền không nằm trong phạm vi, hoặc quyền vẫn tồn tại sau khi nhiệm vụ kết thúc.

### 3.3. Can thiệp vào giám sát và bằng chứng

Ví dụ: thay đổi cấu hình audit, làm giảm mức ghi log, thay đổi đường chuyển log, làm gián đoạn ghi phiên hoặc sửa chính sách lưu giữ.

Không được chỉ dựa vào việc “không còn log” để kết luận có che giấu. Cần kiểm tra lỗi collector, sự cố mạng, thay đổi cấu hình hợp lệ và độ trễ truyền dữ liệu. Tuy vậy, mất khả năng quan sát ngay sau một thay đổi bảo mật nhạy cảm là điều cần điều tra khẩn trương.

### 3.4. Lạm dụng luồng phê duyệt và ngoại lệ

Người dùng có thể tách một thay đổi lớn thành nhiều yêu cầu nhỏ, dùng lý do chung chung để xin quyền rộng, dùng quyền phê duyệt không độc lập hoặc lặp lại break-glass như một cách truy cập thường xuyên.

Sự thông đồng giữa nhiều người không thể được loại trừ chỉ nhờ quy tắc “hai người phê duyệt”. Cần quan sát quan hệ giữa người yêu cầu, người duyệt, phạm vi quyền, kết quả thay đổi và các ngoại lệ lặp lại. Một mối quan hệ phê duyệt thường xuyên tự nó chưa phải bằng chứng sai phạm, vì cơ cấu trực vận hành có thể tạo ra mẫu hình đó.

### 3.5. Lạm dụng credential và tài khoản phi con người

Một người có thể lấy credential của tài khoản dịch vụ rồi sử dụng từ máy cá nhân, mở phiên tương tác bằng tài khoản vốn chỉ chạy theo lịch, hoặc thay đổi ứng dụng để thực hiện thao tác vượt mục đích được duyệt.

Ở đây phải tách ba danh tính: người khởi tạo hoặc sửa tác vụ, workload thực thi và tài khoản mà hệ thống đích nhìn thấy. Nếu chỉ ghi nhận tên tài khoản dịch vụ thì rất khó xác định ai đã điều khiển hành động.

### 3.6. Thay đổi gây thiệt hại cho vận hành

Lạm dụng không chỉ là lấy dữ liệu. Một thay đổi có thể làm ngừng dịch vụ, phá khả năng phục hồi, sửa bản sao lưu hoặc hạ mức kiểm soát truy cập.

Phát hiện cần kết hợp sự kiện quản trị với ảnh hưởng vận hành: cấu hình nào thay đổi, dịch vụ nào suy giảm, bản sao lưu nào bị tác động và có quy trình khôi phục được kiểm chứng hay không.

## 4. Dữ liệu cần có để quan sát hành vi

Một hệ thống PAM không nhìn thấy mọi hoạt động trên tài nguyên đích. Phiên được ghi hình cũng không tự giải thích được ý nghĩa của một thay đổi. Cần kết hợp nhiều nguồn theo khả năng thực tế của môi trường.

| Nguồn | Câu hỏi có thể hỗ trợ trả lời | Giới hạn thường gặp |
|---|---|---|
| Kho danh tính và nhân sự | Người đó đang có vai trò, trạng thái và đơn vị nào? | Dữ liệu chậm cập nhật; không phản ánh đầy đủ nhiệm vụ tạm thời |
| Yêu cầu và phê duyệt PAM | Quyền được cấp vì mục đích nào, trên tài nguyên nào? | Nội dung ticket có thể mơ hồ hoặc chỉ được duyệt sau sự kiện |
| Vault và cấp credential | Ai checkout, lấy secret hoặc được cấp lease? | Checkout không chứng minh credential đã được dùng; credential có thể bị dùng ngoài luồng |
| Broker và ghi phiên | Phiên nào tới tài nguyên nào, có đi qua đường kiểm soát không? | Ghi hình thiếu dữ liệu có cấu trúc; broker có thể không bao phủ mọi đường truy cập |
| Audit hệ điều hành, cơ sở dữ liệu, nền tảng | Thao tác cụ thể nào được hệ thống đích chấp nhận? | Có thể thiếu chi tiết hoặc bị gián đoạn thu thập |
| Thiết bị và workload | Tiến trình, thiết bị hoặc tác vụ nào thực hiện hoạt động? | Không phải mọi thiết bị đều được quản lý hoặc quan sát ngang nhau |
| Mạng và đích lưu trữ | Dữ liệu đi đâu, qua đường nào, với khối lượng nào? | Mã hóa và dịch vụ trung gian có thể hạn chế việc hiểu nội dung |
| Quản lý thay đổi và triển khai | Hành động có thuộc một thay đổi được duyệt không? | Yêu cầu hợp lệ không đồng nghĩa mọi hành động đều hợp lệ |

### 4.1. Chuẩn hóa định danh và thời gian

Một bản ghi phục vụ tương quan nên có tối thiểu các trường phù hợp với sự kiện:

```json
{
  "event_id": "evt-781",
  "event_time": "2026-11-27T02:08:14Z",
  "ingest_time": "2026-11-27T02:08:19Z",
  "source": "database_audit",
  "actor_id": "user-u17",
  "effective_account": "db-admin-temporary",
  "request_id": "PAM-REQ-4102",
  "session_id": "pam-sess-205",
  "target_id": "db-orders-prod",
  "action": "data_export",
  "object_classification": "restricted",
  "result": "success",
  "export_bytes": 482000000,
  "destination_id": "storage-unregistered",
  "identity_resolution": "confirmed"
}
```

Các giá trị trên là dữ liệu giả lập. Không đưa mật khẩu, token, private key hoặc nội dung dữ liệu khách hàng vào sự kiện chỉ để thuận tiện phân tích. Nếu thông tin truy vấn hay tham số có thể chứa dữ liệu nhạy cảm, cần cơ chế hạn chế, che dữ liệu và kiểm soát người xem.

Không được tự điền `actor_id` khi chưa liên kết được người sử dụng với tài khoản hiệu lực. Có thể để trống kèm trạng thái chưa xác định. “Không xác định được người thao tác” là vấn đề về khả năng truy vết, không phải lý do gán hành vi cho người checkout gần nhất.

Nên lưu cả thời điểm xảy ra và thời điểm tiếp nhận. Các nguồn có độ trễ hoặc lệch đồng hồ có thể khiến chuỗi sự kiện nhìn như đảo ngược. Dùng định danh phiên và yêu cầu nếu có, rồi mới bổ sung tương quan theo khoảng thời gian có kiểm soát.

### 4.2. Giữ cả dữ liệu gốc và diễn giải

Bản ghi chuẩn hóa giúp tìm kiếm, nhưng có thể mất chi tiết hoặc sai khi bộ phân tích thay đổi. Bằng chứng cần có tham chiếu đến nguồn gốc, thời điểm thu thập, cách truy xuất và phiên bản logic phân tích.

Nếu một trường được suy ra, hãy ghi rõ đó là giá trị suy ra và cơ sở của nó. Ví dụ, suy ra người sử dụng từ ánh xạ phiên broker có độ tin cậy khác với đoán người sử dụng theo địa chỉ IP.

## 5. Thiết kế phát hiện từ hành vi và phạm vi được phép

Một phát hiện hữu ích nên trả lời được sáu câu hỏi:

1. Hành vi nào cần phát hiện?
2. Vì sao hành vi đó có thể gây hại trong phạm vi tài sản này?
3. Cần những sự kiện nào để nhận diện?
4. Điều kiện nào làm tăng hoặc giảm mức nghi ngờ?
5. Bằng chứng nào còn thiếu trước khi kết luận?
6. Người nhận cảnh báo có thể thực hiện bước tiếp theo nào?

### 5.1. Bắt đầu từ một giả thuyết cụ thể

Thay vì “phát hiện người nội bộ xấu”, hãy viết:

> Một người được cấp quyền sửa cấu hình nhưng thực hiện xuất dữ liệu nhạy cảm ngoài phạm vi phê duyệt; cần xác định việc xuất có thực sự xảy ra, ai điều khiển phiên và dữ liệu đi đâu.

Giả thuyết này gắn được với yêu cầu PAM, audit tại tài nguyên đích và thông tin đích lưu trữ. Nó cũng chỉ rõ bằng chứng cần thêm khi chỉ quan sát được một phần.

### 5.2. Dùng ba lớp điều kiện

**Lớp thứ nhất: quy tắc theo chính sách.** Một hành động bị cấm rõ ràng trong phạm vi yêu cầu có thể tạo cảnh báo ngay cả khi từng xảy ra nhiều lần.

**Lớp thứ hai: bất thường theo ngữ cảnh.** Ví dụ, người dùng chuyển sang nhóm máy chưa từng quản trị, dùng thiết bị mới hoặc lấy nhiều credential trong một khoảng ngắn. Những điểm này giúp ưu tiên nhưng chưa chứng minh lạm dụng.

**Lớp thứ ba: chuỗi hành vi và ảnh hưởng.** Tổ hợp cấp thêm quyền, xuất dữ liệu và thay đổi audit thường đáng chú ý hơn mỗi sự kiện riêng lẻ.

Không có một thứ tự cố định buộc mọi phát hiện phải qua đủ ba lớp. Một hành động có ảnh hưởng nghiêm trọng và trái chính sách rõ ràng không cần chờ thêm hành vi để được xử lý.

### 5.3. Baseline phải có bối cảnh

Baseline có thể được xây theo vai trò, nhóm trực, tài sản, nhiệm vụ và thời điểm vận hành. So sánh một quản trị viên cơ sở dữ liệu với toàn bộ nhân viên thường tạo ra rất nhiều bất thường giả.

Các yếu tố cần đưa vào diễn giải gồm:

- Ca trực, múi giờ và lịch bảo trì.
- Thay đổi vai trò hoặc nhiệm vụ mới.
- Tác vụ di chuyển dữ liệu, sao lưu và phục hồi đã được duyệt.
- Sự cố lớn khiến tần suất truy cập thay đổi.
- Người mới chưa có lịch sử đủ dài.
- Chất lượng và độ bao phủ của dữ liệu quan sát.

Baseline phản ánh điều thường xảy ra, không xác định điều được phép. Một hành vi trái chính sách diễn ra lâu ngày không trở thành hợp lệ vì được mô hình coi là bình thường.

### 5.4. Ví dụ danh mục phát hiện

| Hành vi | Tín hiệu chính | Ngữ cảnh cần đối chiếu | Điều cần thận trọng |
|---|---|---|---|
| Xuất dữ liệu ngoài yêu cầu | Audit ghi nhận xuất thành công | Phạm vi ticket, phân loại dữ liệu, đích xuất | Sao lưu và di chuyển dữ liệu có thể hợp lệ |
| Cấp quyền vượt nhiệm vụ | Thay đổi nhóm hoặc vai trò đặc quyền | Người hưởng quyền, thời hạn, người duyệt | Tên vai trò không luôn mô tả đúng quyền hiệu lực |
| Dùng credential dịch vụ tương tác | Phiên tương tác bằng tài khoản workload | Chủ sở hữu, kiểu xác thực và quy trình hỗ trợ | Một số tác vụ hỗ trợ có ngoại lệ đã được duyệt |
| Can thiệp audit gần hành vi nhạy cảm | Thay đổi audit và hoạt động quản trị liên quan | Thay đổi hệ thống, sức khỏe collector | Gián đoạn mạng có thể làm mất log tương tự |
| Lặp lại break-glass | Nhiều phiên ngoại lệ trên tài sản nhạy cảm | Sự cố, kết quả rà soát sau truy cập | Không dùng một ngưỡng chung cho mọi nhóm trực |
| Giữ quyền sau khi hết nhiệm vụ | Quyền vẫn hiệu lực sau thời hạn | Gia hạn, độ trễ thu hồi, tài khoản liên quan | Phân biệt lỗi cơ chế thu hồi với hành vi cố ý |
| Vượt đường truy cập PAM | Hoạt động đặc quyền tại đích thiếu phiên tương ứng | Độ bao phủ broker và chất lượng ánh xạ | Thiếu tương quan chưa đủ chứng minh cố tình né PAM |

## 6. Một phát hiện minh họa: xuất dữ liệu ngoài phạm vi

Giả sử mọi hoạt động xuất dữ liệu trong phạm vi quan sát đều được chuẩn hóa thành `data_export`, và hệ thống lưu trạng thái yêu cầu tại thời điểm cấp quyền. Logic dưới đây minh họa tư duy phát hiện, không phải mã truy vấn cho một sản phẩm cụ thể:

```text
FOR each successful data_export event:
    request = find_request_by_verified_session(event.session_id)

    IF request is missing:
        emit("EXPORT_WITH_UNRESOLVED_AUTHORIZATION",
             observed_event=event,
             next_action="resolve session and authorization")
        CONTINUE

    IF event.target_id is outside request.target_scope:
        emit("EXPORT_OUTSIDE_TARGET_SCOPE", event, request)
        CONTINUE

    IF request.data_export_allowed is explicitly false:
        emit("EXPORT_NOT_ALLOWED_BY_REQUEST", event, request)
        CONTINUE

    IF request.data_export_allowed is unknown:
        emit("EXPORT_REQUIRES_AUTHORIZATION_REVIEW", event, request)
        CONTINUE

    IF event.destination_id is outside approved_destinations(request):
        emit("EXPORT_TO_UNAPPROVED_DESTINATION", event, request)
```

Có một khác biệt quan trọng giữa **bị cấm rõ ràng** và **không có thông tin**. Trường phê duyệt bị thiếu không nên bị diễn giải tự động thành “đã chứng minh vi phạm”. Ngược lại, ticket có nội dung chung chung cũng không nên được diễn giải thành quyền xuất mọi dữ liệu.

Khi triển khai, cần kiểm tra thêm:

- Yêu cầu có hiệu lực tại thời điểm hành động, thay vì dùng trạng thái hiện tại đã được sửa sau đó.
- Định danh tài nguyên có được chuẩn hóa qua alias và endpoint hay không.
- Có nhiều phiên hoặc nhiều yêu cầu cùng tồn tại cho một người hay không.
- Hoạt động thất bại có được phân biệt với hoạt động thành công hay không.
- Một tác vụ xuất được chia thành nhiều sự kiện có bị đếm lặp không.
- Đích lưu trữ có xác định được hay chỉ đang thiếu dữ liệu quan sát.
- Dữ liệu đến chậm có làm phát hiện chạy trước khi bản ghi phê duyệt được tiếp nhận không.

Một truy vấn có thể chính xác về cú pháp nhưng vẫn tạo kết luận sai nếu xử lý các điểm này không đúng.

### 6.1. Không biến điểm rủi ro thành kết luận về con người

Có thể dùng điểm rủi ro để xếp thứ tự điều tra. Các yếu tố như mức nhạy cảm tài sản, quyền hiệu lực, bằng chứng trái phạm vi và hành vi làm giảm khả năng quan sát có thể ảnh hưởng đến độ ưu tiên.

Không nên cộng điểm cơ học từ nhiều cảnh báo trùng nguồn. Chẳng hạn, “xuất nhiều dữ liệu”, “đọc nhiều dữ liệu” và “lưu lượng lớn” có thể cùng mô tả một tác vụ xuất, không phải ba bằng chứng độc lập.

Nên thể hiện riêng:

- **Mức ảnh hưởng tiềm tàng hoặc đã quan sát.**
- **Độ tin cậy của bằng chứng.**
- **Tính cấp bách vì hành vi còn đang tiếp diễn.**
- **Phần ngữ cảnh còn thiếu.**

Một hành động có ảnh hưởng lớn nhưng ánh xạ người dùng chưa rõ vẫn có thể cần chặn để bảo vệ hệ thống. Việc chặn không đồng nghĩa đã kết luận cá nhân nào có lỗi.

## 7. Từ cảnh báo đến xác minh có căn cứ

### 7.1. Triage theo câu hỏi

Khi nhận cảnh báo, người phân tích nên lần lượt làm rõ:

1. **Điều gì thực sự được quan sát?** Có bản ghi thao tác thành công hay chỉ có ý định gọi lệnh?
2. **Tài nguyên và dữ liệu nào bị tác động?** Mức nhạy cảm và phạm vi thực tế là gì?
3. **Quyền nào đã được cấp?** Có yêu cầu, phê duyệt, ngoại lệ hoặc gia hạn hợp lệ không?
4. **Ai hoặc workload nào điều khiển hành động?** Mức chắc chắn của liên kết danh tính đến đâu?
5. **Hoạt động còn tiếp diễn không?** Có cần giới hạn thiệt hại ngay không?
6. **Có lời giải thích thay thế phù hợp với bằng chứng không?**
7. **Cần bổ sung nguồn nào để xác nhận hoặc bác bỏ giả thuyết?**

Nếu cần xác minh với người yêu cầu hoặc người phê duyệt, nên đi theo quy trình xử lý sự cố đã thống nhất. Khi có dấu hiệu che giấu hoặc ảnh hưởng nghiêm trọng, người phân tích không nên tự ý thông báo rộng hoặc chất vấn trực tiếp đối tượng trước khi phối hợp với đầu mối được giao.

### 7.2. Dòng thời gian minh họa

| Thời điểm | Sự kiện | Diễn giải ban đầu |
|---|---|---|
| 02:00 UTC | Cấp quyền sửa connection pool cho `db-orders-prod` | Quyền bảo trì có thời hạn |
| 02:04 UTC | Phiên broker bắt đầu từ thiết bị quản lý | Liên kết phiên với người yêu cầu được xác nhận |
| 02:08 UTC | Audit tại cơ sở dữ liệu ghi nhận xuất dữ liệu thành công | Hành vi cần đối chiếu với mục đích |
| 02:09 UTC | Ghi dữ liệu vào đích chưa nằm trong danh sách được duyệt | Chưa xác định chủ sở hữu và lý do sử dụng đích |
| 02:10 UTC | Có thay đổi cấu hình audit | Cần xác minh phạm vi và kết quả thay đổi |
| 02:11 UTC | Hệ thống tạo cảnh báo tương quan | Cần triage và quyết định giới hạn thiệt hại |

Đây là tình huống giả định, không phải bằng chứng cho một vụ việc thực tế. Ngay trong tình huống này, vẫn cần kiểm tra liệu tác vụ xuất có thuộc một yêu cầu khác, thay đổi audit có thành công và đích lưu trữ có được phê duyệt qua quy trình khác hay không.

Việc xác minh không được trì hoãn vô thời hạn nếu dữ liệu nhạy cảm đang tiếp tục bị chuyển ra ngoài phạm vi kiểm soát. Có thể thực hiện biện pháp hạn chế tạm thời theo thẩm quyền đã quy định, đồng thời tiếp tục điều tra nguyên nhân.

### 7.3. Phân loại kết quả rõ ràng

Một cảnh báo có thể được đóng theo các kết quả khác nhau:

- Hoạt động hợp lệ, cảnh báo phát sinh do logic hoặc dữ liệu ngữ cảnh chưa đủ.
- Hành vi vượt quy trình nhưng chưa xác định động cơ.
- Sai sót vận hành có ảnh hưởng thực tế.
- Tài khoản hoặc phiên bị chiếm đoạt.
- Lạm dụng có chủ ý được xác nhận theo quy trình của tổ chức.
- Chưa đủ bằng chứng để kết luận.

Không nên ép mọi vụ việc vào hai nhãn “insider có lỗi” và “false positive”. Việc thiếu audit hoặc không thể liên kết danh tính cần được ghi nhận như một kết quả và một khoảng trống kiểm soát.

## 8. Giới hạn thiệt hại mà vẫn giữ khả năng điều tra

Lựa chọn phản ứng dựa trên hành động đang xảy ra, mức ảnh hưởng và độ chắc chắn, không chỉ dựa trên tên quy tắc hoặc một điểm rủi ro.

| Tình huống | Biện pháp có thể cân nhắc theo thẩm quyền | Điều phải kiểm tra |
|---|---|---|
| Bất thường đơn lẻ, chưa rõ mục đích | Yêu cầu xác minh bổ sung, giám sát có mục tiêu | Không mở rộng thu thập quá mức cần thiết |
| Hoạt động ngoài phạm vi đang tiếp diễn | Tạm dừng phiên hoặc hạn chế quyền liên quan | Phiên nền và kết nối tại tài nguyên có còn tiếp tục không |
| Credential có thể đã lộ | Thu hồi lease, khóa hoặc đổi credential có phối hợp | Ứng dụng phụ thuộc, token dẫn xuất và khả năng khôi phục |
| Thay đổi quyền không được duyệt | Thu hồi quyền phát sinh và kiểm tra tài khoản liên quan | Quyền hiệu lực, phiên đã tồn tại, đường truy cập thay thế |
| Can thiệp audit | Bảo vệ bản log tập trung và khôi phục quan sát | Bản ghi nào còn nguyên; khoảng thời gian thiếu dữ liệu |
| Nguy cơ gián đoạn dịch vụ | Phối hợp chủ hệ thống để cô lập có kiểm soát | Tài khoản khẩn cấp, phụ thuộc hệ thống và đường phục hồi |

Khóa tài khoản không bảo đảm mọi phiên hiện có bị chấm dứt. Đổi mật khẩu cũng không bảo đảm token, chứng thư hoặc khóa khác hết hiệu lực. Phản ứng cần kiểm tra kết quả thực tế tại từng hệ thống liên quan.

Với tài khoản dịch vụ, thu hồi vội vàng có thể làm dừng nhiều ứng dụng. Điều đó không có nghĩa phải giữ nguyên quyền nguy hiểm; cần xác định biện pháp hẹp nhất có hiệu quả, chẳng hạn giới hạn đích truy cập hoặc thu hồi đúng credential bị nghi ngờ, rồi phối hợp thay thế an toàn.

Nếu bắt buộc hành động ngay để ngăn thiệt hại, hãy ghi lại người quyết định, căn cứ, thời điểm, phạm vi và kết quả. Không trì hoãn việc ngăn thiệt hại chỉ để thu thập một bộ bằng chứng hoàn hảo.

## 9. Bằng chứng, quyền riêng tư và phân tách trách nhiệm

### 9.1. Thu thập đủ để giải thích quyết định

Một hồ sơ điều tra nên liên kết được:

- Sự kiện gốc và các bản ghi chuẩn hóa liên quan.
- Yêu cầu, phiên bản phê duyệt và chính sách có hiệu lực khi hành động xảy ra.
- Quyền trước và sau thay đổi, nếu quan sát được.
- Cơ sở liên kết tài khoản, phiên và chủ thể thực hiện.
- Đích dữ liệu, kết quả thao tác và ảnh hưởng đã xác nhận.
- Biện pháp phản ứng, người thực hiện và bằng chứng kết quả.
- Những dữ kiện mâu thuẫn hoặc chưa xác minh.

Cần quản lý quyền truy cập bằng chứng, lưu dấu việc truy xuất và bảo vệ tính toàn vẹn. Giá trị băm giúp phát hiện bản sao bị thay đổi so với lúc tính băm; nó không tự chứng minh dữ liệu gốc đúng hoặc quá trình thu thập đáng tin cậy.

Không giữ credential đang hoạt động trong hồ sơ điều tra. Nếu log vô tình chứa secret, cần xử lý theo quy trình của tổ chức, hạn chế người xem và đánh giá việc thu hồi hoặc luân chuyển secret đó.

### 9.2. Giám sát người có quyền giám sát

Nhóm vận hành PAM hoặc hệ thống log cũng có đặc quyền. Nếu một người vừa sử dụng quyền, vừa chỉnh quy tắc phát hiện, vừa xóa bằng chứng, toàn bộ cơ chế kiểm soát có thể bị vô hiệu hóa.

Nên phân tách hợp lý các quyền quản trị vault, quản trị log, phê duyệt truy cập và xem lại phiên. Các thay đổi đối với cấu hình audit, quyền người điều tra hoặc chính sách lưu giữ cũng cần được ghi nhận và rà soát.

Độc lập không nhất thiết có nghĩa mọi thao tác đều cần nhiều lớp phê duyệt. Mục tiêu là tránh một chủ thể có thể âm thầm kiểm soát toàn bộ hành động và bằng chứng về hành động đó.

### 9.3. Giới hạn mục đích sử dụng dữ liệu

Dữ liệu phục vụ phát hiện lạm dụng đặc quyền có thể chứa thông tin nhạy cảm về người lao động, khách hàng và hệ thống. Thiết kế thu thập nên tập trung vào hoạt động có liên quan đến quyền và tài sản cần bảo vệ.

Cần xác định người được xem bản ghi phiên, phạm vi tìm kiếm, thời hạn lưu giữ theo chính sách áp dụng và cơ chế phê duyệt khi phải xem nội dung nhạy cảm. Không dùng thông tin cá nhân không liên quan làm dấu hiệu suy đoán động cơ.

Đánh giá kỹ thuật về hành vi và quyết định liên quan đến nhân sự cần có trách nhiệm rõ ràng. Người phân tích cảnh báo nên báo cáo điều quan sát được và mức chắc chắn, không tự đưa ra quyết định kỷ luật.

## 10. Kiểm chứng phát hiện trong môi trường được phép

Không cần tạo một hành vi lạm dụng thực sự để kiểm chứng quy tắc. Có thể dùng sự kiện tổng hợp, phát lại dữ liệu đã khử nhạy cảm hoặc thực hiện kịch bản trên tài sản thử nghiệm và dữ liệu giả.

Một kế hoạch kiểm chứng nên có cả trường hợp cần cảnh báo và trường hợp không nên kết luận vi phạm:

| Ca kiểm chứng | Dữ liệu đầu vào | Kết quả mong đợi |
|---|---|---|
| Xuất dữ liệu bị cấm rõ trong yêu cầu | Phiên liên kết chắc chắn, export thành công | Cảnh báo hành động trái phạm vi với bằng chứng |
| Sao lưu hợp lệ | Có phê duyệt đúng tài nguyên, thời gian và đích | Không bị kết luận lạm dụng vì khối lượng lớn |
| Thiếu yêu cầu do dữ liệu đến chậm | Audit đến trước bản ghi phê duyệt | Trạng thái chờ bổ sung hoặc rà soát; có cơ chế cập nhật |
| Không xác định được người dùng | Tài khoản đích có hoạt động, thiếu liên kết phiên | Cảnh báo khoảng trống truy vết, không gán tên tùy ý |
| Thao tác xuất thất bại | Audit trả kết quả bị từ chối | Phân biệt hành vi thử với dữ liệu đã xuất |
| Đổi vai trò hợp lệ | Người dùng nhận nhiệm vụ mới và quyền phù hợp | Baseline không tự kết luận sai do lịch sử cũ |
| Collector mất kết nối | Thiếu log nhưng không có sự kiện sửa audit | Phát hiện suy giảm quan sát, tránh khẳng định che giấu |
| Tác vụ nền tiếp tục sau khi khóa tài khoản | Phiên hoặc token cũ còn hiệu lực | Chứng minh biện pháp phản ứng có cần bổ sung không |

Trước khi đưa quy tắc vào hoạt động, cần xác định người nhận, thời hạn phản hồi theo mức ưu tiên, bước xác minh và thẩm quyền giới hạn thiệt hại. Một cảnh báo không có người xử lý hoặc không có hành động tiếp theo rõ ràng sẽ ít giá trị dù logic phát hiện tốt.

Các ngưỡng như số lần checkout, dung lượng xuất hoặc độ dài cửa sổ tương quan phải được hiệu chỉnh bằng dữ liệu và bối cảnh của tổ chức. Không coi một con số minh họa là ngưỡng phù hợp cho mọi hệ thống.

## 11. Đo hiệu quả và cải tiến sau vụ việc

Số lượng cảnh báo không phải thước đo đủ tốt. Nhiều cảnh báo hơn có thể chỉ phản ánh quy tắc trùng lặp hoặc chất lượng dữ liệu giảm.

Các chỉ số hữu ích gồm:

- Tỷ lệ hoạt động đặc quyền liên kết được với chủ thể và yêu cầu hợp lệ.
- Độ bao phủ audit trên các tài sản nhạy cảm thuộc phạm vi.
- Thời gian từ sự kiện đến lúc có thể điều tra, bao gồm độ trễ dữ liệu.
- Thời gian xác minh và thời gian giới hạn hoạt động gây hại.
- Tỷ lệ cảnh báo có đủ bằng chứng cho bước xử lý tiếp theo.
- Tỷ lệ kết quả chưa thể kết luận vì thiếu dữ liệu.
- Mức phát hiện được các kịch bản đã kiểm chứng.
- Tỷ lệ quyền hoặc phiên liên quan được thu hồi và xác nhận hiệu quả sau phản ứng.

Khi tính tỷ lệ cảnh báo đúng, phải nói rõ “đúng” nghĩa là hành động trái phạm vi được xác nhận, hay chỉ là bất thường có thật. Một hoạt động bất thường có thật vẫn có thể hoàn toàn hợp lệ.

Sau mỗi vụ việc, hãy phân biệt ba loại cải tiến: giảm quyền không cần thiết, tăng khả năng quan sát và sửa logic phát hiện. Không giải quyết mọi vấn đề bằng cách tăng điểm rủi ro hoặc hạ ngưỡng. Nếu nguyên nhân là vai trò quá rộng, kiểm soát phòng ngừa thường cần thay đổi ở cách cấp quyền.

## 12. Bài tập vận dụng

### Tình huống

Một kỹ sư được cấp quyền JIT trong 20 phút để kiểm tra lỗi ứng dụng trên hệ thống thanh toán. Trong phiên, audit ghi nhận đọc nhiều bản ghi giao dịch và tạo tệp xuất. Sau đó collector bị gián đoạn trong ba phút. Ticket chưa ghi rõ có được xuất dữ liệu hay không.

Hãy xác định:

1. Những gì đã biết chắc từ tình huống và những gì mới chỉ là giả thuyết.
2. Nguồn nào có thể xác nhận phạm vi dữ liệu, đích xuất và danh tính điều khiển phiên.
3. Vì sao chưa thể kết luận sự gián đoạn collector là hành vi che giấu.
4. Điều kiện nào khiến cần giới hạn phiên ngay trước khi hoàn tất điều tra.
5. Cần thay đổi gì trong yêu cầu cấp quyền để lần sau xác minh được rõ ràng hơn.

### Gợi ý tiếp cận

Đã quan sát có thao tác đọc và xuất theo dữ liệu audit được mô tả, nhưng chưa đủ thông tin về phạm vi được phép, đích đến và nguyên nhân mất log. Ticket mơ hồ tạo ra khoảng trống về xác minh quyền sử dụng; nó không tự chứng minh có phê duyệt và cũng không tự chứng minh ý định xấu.

Nên đối chiếu audit tại tài nguyên, ánh xạ phiên PAM, yêu cầu thay đổi, dữ liệu đích lưu trữ và sức khỏe collector. Nếu hoạt động đang tiếp tục trên dữ liệu nhạy cảm ngoài phạm vi kiểm soát, có thể cần hạn chế theo thẩm quyền xử lý sự cố. Quyết định đó cần dựa vào hành động và nguy cơ quan sát được, đồng thời lưu căn cứ cho việc rà soát sau này.

Yêu cầu cấp quyền có thể được cải tiến bằng cách mô tả thao tác được phép, phạm vi dữ liệu, điều kiện xuất, đích được duyệt và người phê duyệt độc lập. Việc thu hồi phải được kiểm tra đến quyền hiệu lực và phiên thực tế, không chỉ đến thời điểm hết hạn ghi trên ticket.

## 13. Những điểm cần ghi nhớ

Insider misuse là vấn đề **sử dụng đặc quyền trái phạm vi hoặc mục đích**, không đồng nghĩa với mọi hoạt động lạ. Quyền đăng nhập hợp lệ và quyền thực hiện nhiệm vụ là hai điều cần kiểm tra riêng.

Một cơ chế phát hiện tốt kết nối yêu cầu PAM, danh tính, phiên, audit tại tài nguyên và ảnh hưởng. Nó giữ rõ ranh giới giữa dữ kiện, suy luận và thông tin còn thiếu, đồng thời có bước phản ứng cụ thể.

Least privilege, JIT/JEA, quản lý credential và phân tách trách nhiệm giảm cơ hội lạm dụng. Phát hiện theo ngữ cảnh, bảo vệ bằng chứng và xác minh kết quả thu hồi giúp tổ chức xử lý phần rủi ro vẫn còn lại.

