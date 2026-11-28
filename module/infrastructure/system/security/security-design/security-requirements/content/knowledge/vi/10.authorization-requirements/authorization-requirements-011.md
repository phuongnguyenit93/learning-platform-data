# Field-level authorization

## 1. Quyền trên đối tượng chưa đủ để bảo vệ từng trường

**Field-level authorization** là kiểm soát quyền theo từng trường hoặc thuộc tính của dữ liệu. Một chủ thể có thể được truy cập một hồ sơ nhưng chỉ được đọc một phần nội dung, xem một trường ở dạng che, hoặc sửa một tập trường xác định.

Ví dụ, giảng viên được xem hồ sơ đăng ký học của lớp đang phụ trách, nhưng chỉ thấy số điện thoại đã che. Học viên được sửa số điện thoại của mình, nhưng không được sửa điểm cuối kỳ. Quyền đọc hồ sơ không tự kéo theo quyền đọc đầy đủ mọi trường; quyền đọc một trường cũng không tự kéo theo quyền sửa trường đó.

Trong chương **Yêu cầu authorization**, mục tiêu là biến các điều kiện như vậy thành đặc tả đo được: trường nào, thao tác nào, ai được thực hiện, trong bối cảnh nào, tại đâu thực thi và kiểm chứng bằng bằng chứng gì.

Phân biệt các cơ chế liên quan:

| Cơ chế | Câu hỏi được giải quyết | Giới hạn cần nhớ |
| --- | --- | --- |
| Quyền theo đối tượng hoặc hàng | Chủ thể có được truy cập hồ sơ này không? | Không tự quyết định quyền trên từng trường |
| Quyền theo trường | Chủ thể được đọc, che, sửa hoặc sử dụng thuộc tính nào? | Vẫn phải kết hợp quyền trên đối tượng |
| Ẩn thành phần giao diện | Người dùng nhìn thấy ô nào trên màn hình? | Không bảo vệ dữ liệu đã nằm trong response hoặc DOM |
| Mã hóa dữ liệu | Dữ liệu có được bảo vệ trên đường truyền hoặc khi lưu không? | Dịch vụ có thể giải mã rồi vẫn trả sai người |
| Masking — che dữ liệu | Phiên bản nào của giá trị được hiển thị? | Là một cách thực hiện quyết định, không thay thế chính sách cấp quyền |

Một API trả số điện thoại nguyên vẹn rồi dùng JavaScript thay bằng dấu sao chưa thực hiện bảo vệ theo trường tại ranh giới API. Bí mật đã đến trình duyệt trước bước che.

## 2. Xác định tài sản, đường truy cập và mô hình đe dọa

Xét nền tảng học tập phục vụ nhiều tenant. Một hồ sơ đăng ký học gắn với học viên, học phần và đơn vị đào tạo. Dữ liệu được dùng qua API chi tiết, danh sách, báo cáo và tác vụ hỗ trợ.

Các nhóm chủ thể trong ví dụ:

- Học viên đang hoạt động, truy cập đúng hồ sơ của mình.
- Giảng viên còn được phân công phụ trách học phần.
- Nhân viên hỗ trợ có hồ sơ hỗ trợ được giao, đúng mục đích và còn hiệu lực.
- Dịch vụ nghiệp vụ thực hiện một tác vụ đã được cấp phạm vi.

Quản trị hạ tầng hoặc quản trị thành viên không mặc nhiên được đọc mọi dữ liệu học tập. Nếu cần quyền đặc biệt, phải đặc tả riêng thay vì coi nhãn “admin” là lý do bỏ qua tất cả kiểm tra.

### 2.1. Danh mục trường và quyền mẫu

| Trường logic | Đọc | Ghi | Điều kiện đáng chú ý |
| --- | --- | --- | --- |
| displayName | Học viên, giảng viên phụ trách, hỗ trợ đúng phạm vi | Học viên qua luồng cập nhật thông tin | Không dùng tên hiển thị làm định danh quyền |
| contact.phone | Học viên thấy đầy đủ; giảng viên thấy bản che; hỗ trợ chỉ thấy đầy đủ khi được cấp | Học viên qua lệnh đổi liên hệ | Quyền xem che khác quyền xem đầy đủ |
| contact.email | Học viên và hỗ trợ được cấp phạm vi phù hợp | Qua luồng đổi email có xác minh riêng | Không mở quyền sửa trực tiếp chỉ vì đọc được |
| learning.progress | Học viên và giảng viên phụ trách | Chỉ dịch vụ tính tiến độ | Không nhận giá trị tự khai để thay kết quả hệ thống |
| assessment.finalScore | Giảng viên phụ trách; học viên chỉ khi đã công bố | Giảng viên đủ điều kiện khi còn ở trạng thái cho phép sửa | Không cho chủ thể tự sửa điểm của chính mình |
| internalNote | Cán bộ được cấp quyền nghiệp vụ cụ thể | Cán bộ được phép theo học phần và trạng thái | Không đưa vào response học viên |
| tenantId, learnerId, courseId | Theo hợp đồng định danh của API | Do máy chủ hoặc lệnh chuyển có quyền riêng quản lý | Không sửa bằng một PATCH hồ sơ thông thường |

Đây là chính sách minh họa. Mỗi hệ thống phải xác nhận lại các chủ thể, luồng nghiệp vụ và mức nhạy cảm. Tên trường logic không bắt buộc trùng cột cơ sở dữ liệu; một trường API có thể tổng hợp từ nhiều nguồn.

### 2.2. Các rủi ro cần liên kết

| Mã | Tình huống | Tác động | Nhóm yêu cầu |
| --- | --- | --- | --- |
| R-FL-01 | API trả cả entity rồi giao diện tự ẩn trường | Lộ dữ liệu riêng tư | Chiếu trường tại máy chủ |
| R-FL-02 | Client thêm trường ngoài giao diện vào request | Sửa điểm, đổi chủ sở hữu hoặc tenant | Danh sách trường ghi được phép |
| R-FL-03 | Đổi tên, alias, đường dẫn lồng nhau hoặc endpoint | Đi vòng qua bộ lọc trường | Hợp đồng tên trường và mọi điểm thực thi |
| R-FL-04 | Lọc, sắp xếp hoặc tổng hợp theo trường bị giấu | Suy ra giá trị nhạy cảm | Quyền sử dụng trường trong truy vấn |
| R-FL-05 | Cache dùng chung một response cho nhiều người | Trả view có quyền rộng cho người quyền hẹp | Phạm vi cache và thu hồi |
| R-FL-06 | Export, job nền hoặc log lấy dữ liệu đầy đủ | Rò rỉ ngoài API chính | Phạm vi theo trường xuyên suốt luồng dữ liệu |
| R-FL-07 | Trạng thái hoặc quyền đổi giữa kiểm tra và ghi | Ghi vào trường đã hết quyền | Kiểm tra phiên bản và giao dịch |
| R-FL-08 | Thêm một trường mới mà serializer tự xuất | Mở quyền ngoài ý muốn | Mặc định không công bố trường mới |

Danh mục đường truy cập phải bao gồm cả REST, GraphQL nếu có, thông điệp, file, thông báo, trang quản trị và công cụ hỗ trợ. Chỉ kiểm tra màn hình chính không bao phủ mô hình đe dọa.

## 3. Viết hợp đồng quyền theo thao tác, trường và ngữ cảnh

Có thể biểu diễn quyết định theo trường như sau:

~~~text
fieldDecision = evaluate(
    subject,
    actor,
    resource,
    operation,
    fieldPath,
    context,
    policyVersion
)
~~~

Quyền theo đối tượng là điều kiện nền. Sau đó mới xét từng trường trong phạm vi được truy cập. Chủ thể không có quyền với hồ sơ không được nhận một phần dữ liệu chỉ vì có quyền đọc cùng tên trường trên hồ sơ khác.

### 3.1. Tách các khả năng sử dụng trường

| Khả năng | Ví dụ | Vì sao cần phân biệt |
| --- | --- | --- |
| Đọc đầy đủ | Xem số điện thoại của mình | Cho phép nhận giá trị nguyên vẹn |
| Đọc bản che | Giảng viên thấy bốn số cuối | Chỉ cho nhận một biểu diễn giới hạn |
| Ghi | Đổi số điện thoại | Tạo tác động khác với đọc |
| Xóa giá trị | Đặt trường về null | Có thể làm mất dữ liệu hoặc vô hiệu kiểm soát |
| Dùng để lọc | Tìm hồ sơ theo số điện thoại | Có thể kiểm tra một giá trị có tồn tại hay không |
| Dùng để sắp xếp | Xếp theo điểm chưa công bố | Có thể làm lộ thứ tự dù không trả điểm |
| Tổng hợp | Tính thống kê trên điểm | Phạm vi và nguy cơ suy luận khác đọc chi tiết |
| Export | Đưa trường vào file tải về | Dữ liệu có thể tồn tại lâu và được chia sẻ tiếp |

Không nhất thiết phải xây dựng một quyền rời cho mọi ô trong bảng nếu sản phẩm không có nhu cầu. Nhưng đặc tả phải nói rõ quyền nào bao gồm khả năng nào; không suy ra rằng đọc bản che đồng nghĩa được tìm kiếm theo giá trị đầy đủ.

### 3.2. Thuộc tính dùng quyết định phải có nguồn đáng tin

Các điều kiện như đúng chủ sở hữu, cùng tenant, được phân công học phần và có vụ việc hỗ trợ đang hoạt động phải lấy từ nguồn có thẩm quyền. Client có thể gửi ID để yêu cầu thao tác, nhưng không được tự khai quyền sở hữu hay trạng thái công bố.

Với ghi dữ liệu, chính sách có thể cần cả giá trị cũ và thay đổi đề xuất. Ví dụ, quyền sửa điểm chỉ hiệu lực khi hồ sơ đang DRAFT và người sửa không phải học viên sở hữu kết quả. Kiểm tra vai trò “giảng viên” đơn lẻ chưa diễn đạt được yêu cầu đó.

Kiểu dữ liệu, enum, thời hạn và độ mới của thuộc tính cần được xác định. Nếu không đọc được trạng thái hồ sơ, không được mặc định rằng nó còn cho sửa. Nếu không xác nhận được vụ việc hỗ trợ, không cấp quyền xem liên hệ đầy đủ.

### 3.3. Kết quả phải đủ rõ để thực thi

Đối với đọc, hệ thống có thể giải quyết chính sách thành một kế hoạch hiển thị:

~~~yaml
viewPlan:
  policyVersion: field-policy-demo-v1
  resourceRef: enrollment-demo-01
  fields:
    displayName:
      mode: FULL
    contact.phone:
      mode: MASK
      transform: PHONE_LAST4
    assessment.finalScore:
      mode: OMIT
    internalNote:
      mode: OMIT
~~~

FULL, MASK và OMIT lần lượt là trả đầy đủ, trả bản che đã xác định và không phát hành trường. Đây là định dạng minh họa, không phải cú pháp của một thư viện cụ thể.

Quy tắc cấm bắt buộc phải có ưu tiên rõ ràng. Nếu nhiều quy tắc tạo ra kết quả xung đột mà hợp đồng chưa định nghĩa cách giải quyết, không được tự chọn kết quả rộng nhất. Thuộc tính thiếu hoặc lỗi đánh giá không trở thành FULL.

Đối với ghi, máy chủ cần một tập đường dẫn và hành động được phép, cùng các điều kiện trên trạng thái. Kế hoạch đọc không được dùng lại như danh sách cho phép ghi.

## 4. Đặc tả hành vi đọc và che dữ liệu

### 4.1. Lựa chọn cách phản hồi

Có nhiều hợp đồng hợp lệ, nhưng cần chọn có chủ đích:

| Cách phản hồi | Khi phù hợp | Điều phải làm rõ |
| --- | --- | --- |
| Bỏ trường | View theo quyền không hứa có mọi thuộc tính | Trường bị cấm luôn vắng mặt, không phụ thuộc giá trị thật có tồn tại |
| Trả biểu diễn che | Chủ thể được phép biết một phần thông tin | Thuật toán che và lượng thông tin được phép lộ |
| Trả null | Schema có ngữ nghĩa rõ cho dữ liệu không hiển thị | Không gây nhầm với giá trị nghiệp vụ thật là null |
| Từ chối yêu cầu | Client yêu cầu rõ một trường không được phép hoặc dữ liệu không thể tách an toàn | Không đưa giá trị thật vào lỗi |

Trong tình huống mẫu, response chi tiết hoặc danh sách mặc định bỏ trường không được phép. Nếu API có tham số chọn trường rõ ràng và client yêu cầu một trường bị cấm, từ chối toàn bộ yêu cầu theo hợp đồng đã công bố. Không lúc bỏ, lúc báo lỗi tùy việc giá trị thật đang có hay chưa.

Với GraphQL hoặc schema có ràng buộc hiện diện khác, cần chọn hành vi tương thích với schema và giao thức. Không ép một quy tắc bỏ trường của REST vào mọi giao thức mà không xác định cấu trúc dữ liệu và lỗi.

### 4.2. Masking phải chạy trước khi dữ liệu ra khỏi ranh giới được phép

Một quy tắc PHONE_LAST4 có thể được đặc tả:

> Chỉ trả tiền tố che cố định và tối đa bốn chữ số cuối của giá trị điện thoại hợp lệ đã chuẩn hóa. Với giá trị có không quá bốn chữ số, trả ký hiệu che chung thay vì trả nguyên giá trị. Quy tắc không phát hành giá trị gốc trong trường phụ, tooltip, thuộc tính HTML, metadata hoặc lỗi.

Bốn chữ số cuối cũng là dữ liệu được phát hành có chủ đích. Nhóm nghiệp vụ cần xác nhận nó có đủ cơ sở sử dụng và có thể làm tăng khả năng suy luận đến mức nào. Không coi chuỗi có dấu sao là dữ liệu vô điều kiện công khai.

Mã hóa trong cơ sở dữ liệu hoặc TLS không thay đổi nghĩa vụ này. Nếu máy chủ giải mã, tạo JSON đầy đủ rồi client mới che, ranh giới đã bị vượt.

### 4.3. Giá trị suy dẫn có thể mang cùng bí mật

Một trường không xuất hiện trực tiếp vẫn có thể lộ qua:

- Thông báo mô tả lại giá trị.
- Đường dẫn hoặc tên file chứa giá trị.
- Một nhãn được tính trực tiếp từ dữ liệu bị giấu.
- Thuộc tính HTML, dữ liệu hydration hoặc nội dung analytics.
- Lỗi validation hoặc trace ghi giá trị thật.

Trường tính toán cần được phân loại theo thông tin nó tiết lộ. Ví dụ, cho phép biết nhóm tuổi nhưng không biết ngày sinh có thể là một quyết định nghiệp vụ hợp lệ; phải đặc tả phép biến đổi và quyền đọc kết quả đó. Không tự công bố mọi trường suy dẫn chỉ vì chúng không trùng cột dữ liệu gốc.

## 5. Đặc tả quyền ghi và chống mass assignment

**Mass assignment** là tình huống dữ liệu client được gắn vào đối tượng nghiệp vụ quá rộng, khiến các thuộc tính ngoài ý định cũng bị cập nhật. Giao diện chỉ gửi contact.phone không ngăn người gọi API thêm tenantId hoặc assessment.finalScore.

Yêu cầu ghi cần bao phủ cả tạo mới và cập nhật. Một lệnh tạo hồ sơ cũng không được cho phép client tự cấp quyền, chọn tenant ngoài phạm vi hoặc thiết lập trạng thái đã phê duyệt.

### 5.1. Trình tự xử lý mẫu

~~~text
handle_update(request):
    xac_thuc_chu_the_va_actor()
    parse_request_theo_schema_khong_mo_ho()
    load_resource_va_context_dang_tin()
    kiem_tra_quyen_voi_doi_tuong()

    changedPaths = xac_dinh_duong_dan_va_loai_thay_doi(request)
    kiem_tra_quyen_ghi_cho_moi_changedPath()
    kiem_tra_dieu_kien_trang_thai_va_gia_tri_de_xuat()
    validate_du_lieu_nghiep_vu_duoc_phep()

    ghi_co_dieu_kien_theo_version()
    tao_response_tu_ke_hoach_doc_hien_tai()
~~~

Đây là mã giả mô tả các nghĩa vụ. Kiểm tra định dạng và giới hạn đầu vào cơ bản vẫn cần trước khi xử lý sâu; ví dụ không có nghĩa là bỏ qua bảo vệ parser.

Khi request chứa một trường bị cấm, tình huống mẫu từ chối toàn bộ cập nhật và không tạo tác động nghiệp vụ. Không âm thầm áp dụng những trường còn lại, trừ khi API đã có một hợp đồng cập nhật từng phần riêng và các bên sử dụng hiểu rõ kết quả.

### 5.2. Trường vắng mặt khác trường có null

| Dữ liệu gửi | Nghĩa cần đặc tả |
| --- | --- |
| Không gửi trường | Giữ nguyên hoặc xử lý theo hợp đồng của loại lệnh |
| Gửi null | Xin xóa hoặc đặt rỗng theo schema; cần quyền tương ứng |
| Gửi chuỗi rỗng | Một giá trị cụ thể, không tự đồng nghĩa thiếu trường |
| Gửi lại giá trị cũ | Vẫn phải qua quyền đối với trường được đề nghị ghi |
| Gửi giá trị che từ màn hình | Không được ghi chuỗi che đè lên dữ liệu thật |

Một form chỉ nhìn thấy một phần đối tượng không nên được phép gửi lại cả entity để thay thế dữ liệu mà nó không biết. Với PUT hoặc một API thay thế toàn bộ, phải định nghĩa chính xác cách giữ các trường do máy chủ quản lý; không xóa chúng chỉ vì client không nhận được khi đọc.

Nếu dùng chuỗi che làm placeholder, cần tách nó khỏi dữ liệu nhập. Phương án rõ ràng hơn là chỉ gửi lệnh đổi trường khi người dùng thực sự cung cấp giá trị mới, không dùng quy ước mơ hồ “dấu sao nghĩa là giữ nguyên” cho mọi giá trị.

### 5.3. Quyền ghi không thay thế quy trình nghiệp vụ

Quyền đọc email không bao gồm quyền đổi email tức thời. Luồng đổi có thể yêu cầu xác thực lại và xác minh địa chỉ mới. Tương tự, sửa điểm nháp không đồng nghĩa được công bố điểm hoặc bỏ qua người duyệt.

Các trường như owner, tenant, role, trạng thái phê duyệt và dữ liệu do hệ thống tính nên được quản lý qua lệnh có mục đích rõ. Nếu có một luồng chuyển chủ sở hữu hợp lệ, nó cần quyền và tiêu chí riêng; không mở trường đó trong mọi PATCH.

Validation kiểm tra giá trị có hợp lệ, còn authorization kiểm tra chủ thể có quyền thực hiện thay đổi. Một giá trị điểm nằm trong khoảng hợp lệ vẫn không được chấp nhận từ học viên tự sửa kết quả của mình.

## 6. Trường lồng nhau, alias và các đường ghi tương đương

Một trường logic có thể xuất hiện dưới nhiều biểu diễn: contact.phone, đường dẫn /contact/phone, alias trong truy vấn hoặc tên do serializer ánh xạ. Chính sách cần dùng danh mục trường chuẩn và ánh xạ có kiểm soát, không suy đoán bằng cách so chuỗi tùy ý.

Yêu cầu cần xác định:

- Tên và đường dẫn chuẩn của từng trường bảo mật.
- Cách ánh xạ tên API, tên miền nghiệp vụ và cột lưu trữ.
- Hành vi với tên không biết, khóa trùng lặp hoặc biểu diễn không hợp lệ.
- Quyền khi thay cả đối tượng cha so với sửa một trường con.
- Cách kiểm tra phần tử mảng và danh tính đối tượng con.

Cho phép sửa /contact không được tự động mở mọi trường con hiện tại và tương lai. Khi thay đối tượng cha, phải tính tập thay đổi ở các trường con được kiểm soát; không chỉ kiểm tra tiền tố.

Nếu API hỗ trợ thao tác patch như copy hoặc move, cần kiểm tra cả quyền đọc nguồn và quyền ghi đích, cùng điều kiện của thao tác. Không chỉ kiểm tra đường dẫn đích rồi sao chép một trường bí mật sang nơi người dùng đọc được.

Vị trí phần tử mảng không phải định danh ổn định. Nếu client đổi thứ tự hoặc phần tử đã thay đổi giữa hai lần đọc, kiểm tra theo index đơn lẻ có thể tác động nhầm đối tượng. Cần gắn quyền với phần tử thật hoặc danh tính nghiệp vụ, cùng điều kiện phiên bản phù hợp.

Alias và fragment của truy vấn không được tạo quyền mới. Quyền phải được đánh giá trên trường logic đích và tài nguyên thực, không dựa vào tên client chọn để hiển thị kết quả.

## 7. Chống lộ qua lọc, sắp xếp, tổng hợp và metadata

Không trả một cột chưa đủ nếu người dùng có thể đặt câu hỏi về chính cột đó. Ví dụ, điểm chưa công bố bị bỏ khỏi JSON nhưng người dùng lọc finalScore > 8 vẫn có thể suy ra thông tin.

| Bề mặt | Ví dụ rò rỉ | Yêu cầu cần xét |
| --- | --- | --- |
| Bộ lọc | Thử số điện thoại đầy đủ để xem có kết quả không | Quyền dùng trường làm điều kiện tìm |
| Sắp xếp | Xếp theo điểm chưa công bố | Quyền dùng trường và độ chi tiết thứ tự |
| Count hoặc thống kê | Đếm một nhóm rất nhỏ theo thuộc tính nhạy cảm | Phạm vi tổng hợp và rủi ro suy luận |
| Thông báo lỗi | “Giá trị hiện tại là ...” | Không nhúng giá trị bị cấm |
| Metadata phiên bản | Biết một trường ẩn vừa thay đổi | Đánh giá tín hiệu từ version, ETag và thời gian sửa |
| Báo cáo hoặc biểu đồ | Dùng cùng dữ liệu qua đường trình bày khác | Áp chính sách tương ứng cho kết quả suy dẫn |

Cần phân biệt việc **hệ thống nội bộ** dùng một thuộc tính để giới hạn đúng dữ liệu với việc **client được quyền truy vấn** thuộc tính đó. Máy chủ có thể cần dùng tenantId hoặc trạng thái công bố để lọc an toàn dù các trường đó không được đưa ra response. Điều này không mở quyền cho client tự tìm trên mọi trường nội bộ.

Một API thống kê có thể cho phép kết quả tổng hợp mà không cho phép xem từng dòng. Đó phải là một chính sách riêng có phạm vi và đánh giá suy luận; không mặc định rằng aggregate luôn vô hại. Việc giảm độ chi tiết hoặc đặt ngưỡng nhóm là quyết định thiết kế cần kiểm chứng, không phải một con số áp dụng chung.

Hợp đồng phản hồi nên mô tả quyền trên count, phân trang và kết quả tìm kiếm. Không lấy tổng số từ tập dữ liệu rộng hơn tập mà người gọi được phép biết.

## 8. Kiến trúc thực thi: từ chính sách đến dữ liệu phát hành

Một thiết kế có thể tách các trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Điểm quyết định chính sách | Xác định quyền theo đối tượng, trường, thao tác và ngữ cảnh |
| Nguồn thuộc tính | Cung cấp quyền sở hữu, tenant, phân công, trạng thái và bằng chứng hỗ trợ |
| Điểm thực thi nghiệp vụ | Chặn thao tác và gắn quyết định với tài nguyên thật |
| Lớp truy xuất | Giới hạn hàng, cột và điều kiện ghi cần thiết |
| Lớp tạo response | Thực hiện chiếu trường, che và loại bỏ dữ liệu không được phép |
| Điểm phát hành | Trả API, tạo file, gửi thông báo hoặc truyền dữ liệu sang bên nhận |

Các trách nhiệm có thể cùng nằm trong một ứng dụng. Không bắt buộc thêm dịch vụ riêng chỉ để có một sơ đồ nhiều tầng.

~~~mermaid
flowchart LR
    C["Client"] --> E["API / lệnh nghiệp vụ"]
    E --> P["Quyết định quyền đối tượng và trường"]
    P --> A["Nguồn thuộc tính có thẩm quyền"]
    E --> Q["Truy xuất / ghi có điều kiện"]
    Q --> D["Kho dữ liệu"]
    P --> V["Kế hoạch view hoặc tập trường ghi"]
    Q --> S["DTO và serializer"]
    V --> S
    S --> O["Response / file trong phạm vi quyền"]
    E --> L["Audit không chứa giá trị bí mật"]
~~~

DTO là hợp đồng dữ liệu được trả hoặc nhận tại một ranh giới, không phải một bản sao tự động của toàn bộ entity. Hệ thống nên có ánh xạ rõ ràng cho từng loại lệnh và view. Một trường thêm vào entity không được tự xuất hiện trong DTO công khai.

Chiếu cột từ kho dữ liệu giúp giảm lượng dữ liệu nhạy cảm đi qua ứng dụng. Lớp tạo response vẫn cần cưỡng chế đúng view để tránh join, resolver hoặc serializer đưa dữ liệu trở lại. Nhiều lớp bảo vệ phải dùng cùng ngữ nghĩa quyền, không tự diễn giải khác nhau.

Nếu quyết định được truyền giữa các dịch vụ, bằng chứng phải gắn với subject, actor, resource, thao tác, các trường, phiên bản và thời hạn. Một header “đã kiểm tra quyền” không đủ nếu bên nhận không xác minh nguồn và phạm vi.

Khi thiếu thuộc tính, bộ quyết định timeout hoặc kế hoạch view không hợp lệ, tình huống mẫu không phát hành dữ liệu theo một view mặc định rộng. Cần trả lỗi có kiểm soát hoặc từ chối theo hợp đồng. Nếu phép che bắt buộc không chạy được, không dùng giá trị gốc làm phương án dự phòng.

## 9. Cache và thu hồi quyền đối với từng trường

### 9.1. Một tài nguyên có nhiều view bảo mật

Cùng một hồ sơ có thể tạo ra response khác nhau cho học viên, giảng viên và hỗ trợ. Nếu cache chỉ dùng resource ID, response dành cho hỗ trợ có thể bị trả cho giảng viên hoặc học viên.

Một cache view phải gắn với đủ phạm vi tạo ra kết quả: tenant, chủ thể hoặc nhóm quyền được chứng minh tương đương, actor nếu có, loại view, policy version, resource version và các điều kiện còn hiệu lực. Nếu không biểu diễn được biến thể an toàn, không dùng chung cache response đó.

Cần phân biệt:

- Cache dữ liệu gốc trong vùng nội bộ được phép: vẫn phải tạo view theo quyền khi phát hành.
- Cache quyết định hoặc kế hoạch view: phải xét thời hạn quyền và thuộc tính.
- Cache response đã lọc: không được dùng cho ngữ cảnh có quyền khác.
- Cache trình duyệt hoặc trung gian: phải có hợp đồng phù hợp với dữ liệu riêng tư.

Đặt header cache đúng chỉ là một phần; cần kiểm tra cấu hình thực tế của CDN, reverse proxy và client. Không để một tuyến nhạy cảm được cache công khai vì kế thừa cấu hình chung.

### 9.2. Độ trễ thu hồi phải đo từ nguồn

Tình huống mẫu yêu cầu: sau khi quyền xem liên hệ đầy đủ bị thu hồi và commit tại nguồn, mọi lần phát hành mới phải ngừng trả giá trị đầy đủ trong tối đa 60 giây. Đây là mục tiêu minh họa, không phải thời hạn mặc định của field-level authorization.

Để đạt được, phải tính tổng ảnh hưởng của cache thuộc tính, cache quyết định, cache response và dịch vụ phát hành. Dữ liệu lấy lại từ cache không được tự nhận thời điểm mới để kéo dài hiệu lực. Thời hạn gốc của bằng chứng hỗ trợ hoặc quyền được cấp vẫn phải được giữ.

Thông báo xóa cache có thể giúp phản ứng nhanh nhưng cần xử lý mất thông báo. Nếu không xác nhận được view còn hiệu lực sau giới hạn, không phát hành bản đầy đủ cũ.

Một phản hồi 304 hoặc cơ chế tái sử dụng nội dung cũ cũng cần đánh giá quyền hiện tại theo hợp đồng. Không chỉ kiểm tra rằng bản ghi chưa thay đổi rồi cho tiếp tục dùng một view đã hết quyền.

Nếu ETag hoặc updatedAt được tạo từ toàn bộ entity, chúng có thể làm lộ việc một trường ẩn thay đổi. Cần xác định tín hiệu đó có được phép hay tạo metadata từ view được cấp; trường hợp không cần thì không công bố metadata gây tiết lộ.

Quyền đã thu hồi không xóa được dữ liệu người dùng từng tải hợp lệ. Cam kết cần nói rõ đang bảo vệ lần phát hành mới, tác vụ đang chạy hay file còn có thể tải, thay vì hứa thu hồi mọi bản sao.

## 10. Cập nhật đồng thời, bulk và tác vụ nền

### 10.1. Kiểm tra quyền phải gắn với trạng thái thực thi

Giả sử giảng viên được sửa finalScore khi hồ sơ còn DRAFT ở version 7. Một giao dịch khác công bố hồ sơ ở version 8 trước khi lệnh sửa ghi dữ liệu. Nếu chỉ kiểm tra quyền lúc đầu, thay đổi có thể xảy ra trên trạng thái đã không còn cho phép.

Một điều kiện cập nhật minh họa:

~~~sql
UPDATE enrollment_assessment
SET final_score = :score,
    version = version + 1
WHERE enrollment_id = :authorizedEnrollment
  AND tenant_id = :authorizedTenant
  AND state = 'DRAFT'
  AND version = :authorizedVersion;
~~~

Điều kiện SQL không thay thế việc kiểm tra chủ thể và trường. Nó liên kết thao tác ghi với trạng thái và phiên bản được đánh giá. Khi không cập nhật được hàng nào, không tự thử lại bằng cách bỏ điều kiện; cần đánh giá lại hoặc trả xung đột.

Các điều kiện trên nhiều trường cũng cần giữ tính nhất quán. Không cho thay một trường phụ để làm điều kiện của trường nhạy cảm trở thành hợp lệ rồi ghi trong cùng request nếu chính sách không cho phép chuyển trạng thái đó.

Với thuộc tính quyền ở dịch vụ khác, phải nêu mô hình độ mới và thu hồi. Giao dịch trong cơ sở dữ liệu hồ sơ không tự bảo đảm rằng mọi nguồn quyền bên ngoài đã được đồng bộ tức thời.

### 10.2. Bulk cần xác định đơn vị thành công

Một yêu cầu chứa nhiều hồ sơ và nhiều trường phải được kiểm tra theo từng tài nguyên và tập thay đổi tương ứng. Tình huống mẫu chọn **tất cả hoặc không có gì** cho lệnh ghi bulk: nếu một thay đổi không được phép, không áp dụng bất kỳ thay đổi nghiệp vụ nào trong lệnh.

Nếu sản phẩm chọn kết quả từng phần, phải định nghĩa phần tử thành công, lỗi, tác động đã commit và cách thử lại. Không vừa trả lỗi chung vừa âm thầm ghi một số trường.

Export không tự kế thừa toàn bộ quyền của endpoint đọc chi tiết. Nó cần tập hàng và trường được cấp cho hành động xuất, cùng quyền của bên nhận. Tính đúng phải giữ cả trong file CSV, bảng tính, PDF, metadata và các cột ẩn nếu định dạng có chúng.

### 10.3. Job nền phải giữ và đánh giá đúng ngữ cảnh

Một job xuất báo cáo hoặc gửi thông báo cần biết ai yêu cầu, actor thực hiện, tenant, mục đích, phạm vi trường và nguồn phê duyệt. Quyền kỹ thuật đọc cơ sở dữ liệu của worker không tự trở thành quyền phát hành mọi trường.

Quyền cần được xét ở các điểm có ý nghĩa: lúc nhận job, lúc thực thi và lúc người dùng nhận hoặc tải kết quả. Nếu có thu hồi trong khoảng đó, xử lý theo cam kết đã định nghĩa; không giữ quyền vô hạn bằng bản chụp “đã được cho phép” từ lúc tạo job.

Email, webhook và thông báo phải có view theo bên nhận. Một trường không được phép trong API vẫn có thể rò rỉ qua nội dung thư hoặc tên tệp đính kèm nếu dùng template đầy đủ.

Liên kết tải có thời hạn cần được đánh giá theo khả năng thu hồi thực tế. Nếu cơ chế phát hành không kiểm tra lại quyền, thời hạn liên kết phải nằm trong cam kết hoặc phải chọn cơ chế phù hợp hơn.

## 11. Audit, lỗi và thay đổi schema

### 11.1. Ghi đủ bằng chứng, không sao chép dữ liệu nhạy cảm

Một sự kiện minh họa:

~~~json
{
  "eventType": "FIELD_UPDATE_REJECTED",
  "requestId": "server-demo-request",
  "subjectRef": "subject-demo",
  "actorRef": "actor-demo",
  "resourceRef": "enrollment-demo-01",
  "operation": "ENROLLMENT_PATCH",
  "fieldPaths": ["assessment.finalScore"],
  "policyVersion": "field-policy-demo-v1",
  "reasonCode": "FIELD_NOT_WRITABLE"
}
~~~

Ví dụ dùng dữ liệu giả. Audit cần cho biết ai yêu cầu, đối tượng, thao tác, nhóm trường, kết quả và phiên bản chính sách. Không ghi mật khẩu, token, số điện thoại đầy đủ, ghi chú nội bộ hoặc body nguyên vẹn chỉ để giải thích quyết định.

Tên trường cũng có thể nhạy cảm trong một số miền nghiệp vụ. Khi cần, dùng mã trường hoặc mã nhóm được quản lý và giới hạn quyền đọc audit. Nếu phải lưu lịch sử giá trị nghiệp vụ, đó là một kho có chính sách bảo vệ riêng, không phải lý do đưa mọi giá trị vào log chung.

Đường lỗi, debug, APM và bản ghi hỗ trợ phải cùng tuân thủ. Một response đúng nhưng trace chứa entity đầy đủ vẫn là rò rỉ.

### 11.2. Phản hồi lỗi không được mang giá trị bị cấm

Lỗi có thể thông báo loại vi phạm hoặc yêu cầu không hợp lệ mà không trả giá trị hiện tại của trường. Nếu schema công khai cho phép biết tên trường, việc chỉ ra đường dẫn lỗi có thể phù hợp; nếu tên hoặc sự tồn tại là nhạy cảm, phải giảm chi tiết theo hợp đồng.

Trình tự kiểm tra cần tránh xác nhận dữ liệu bí mật cho người không có quyền. Ví dụ, không báo “số điện thoại giống số đang lưu” trước khi xác định chủ thể có quyền đổi liên hệ đó. Không trả entity đầy đủ trong thông báo xung đột hoặc validation.

### 11.3. Trường mới phải có quyết định công bố rõ ràng

Thêm một cột, thuộc tính entity hoặc resolver mới là thay đổi bề mặt dữ liệu. Yêu cầu quản trị cần xác định chủ sở hữu phân loại, quyền đọc/ghi, phép che, quyền truy vấn và các bên nhận.

Trường chưa có trong danh mục được duyệt không được tự động đọc, ghi hoặc export. Mặc định này cần giữ trong serializer, mapper, schema, query builder và mẫu báo cáo.

Policy và schema phải được phát hành tương thích. Khi rollback, phải xét cache view và các client cũ; khôi phục một file chính sách nhưng giữ response quyền rộng trong cache chưa tạo ra trạng thái bảo vệ đúng.

Có thể dùng đánh giá song song để quan sát khác biệt của policy ứng viên. Quyết định thử không được phát hành thêm dữ liệu cho người dùng thật.

## 12. Viết yêu cầu có ID, chủ sở hữu và bằng chứng

Một yêu cầu hoàn chỉnh nên chỉ ra trường logic, hành động, chủ thể, điều kiện, điểm cưỡng chế, hành vi lỗi và tiêu chí nghiệm thu.

| Trường đặc tả | Ví dụ |
| --- | --- |
| ID | SR-FIELD-02 |
| Mục tiêu | Ngăn giảng viên nhận số điện thoại đầy đủ ngoài quyền |
| Rủi ro | R-FL-01, R-FL-03, R-FL-06 |
| Phạm vi | Chi tiết, danh sách, truy vấn lồng nhau và báo cáo cho giảng viên |
| Nghĩa vụ | Khi có quyền với hồ sơ, contact.phone chỉ được phát hành qua PHONE_LAST4; không kèm giá trị gốc ở trường phụ hoặc metadata |
| Điều kiện | Cùng tenant, phân công học phần còn hiệu lực, không có quyền riêng cho đọc đầy đủ |
| Điểm thực thi | Kế hoạch view, serializer và điểm phát hành báo cáo |
| Hành vi lỗi | Không tạo được bản che hợp lệ thì không phát hành giá trị gốc |
| Chủ sở hữu | Nhóm nghiệp vụ duyệt phạm vi; nhóm API thực thi; nhóm báo cáo áp dụng cùng hợp đồng |
| Bằng chứng | So sánh payload, file, lỗi, DOM và telemetry bằng dữ liệu tổng hợp |
| Giới hạn | Bốn số cuối là phần thông tin được cấp có chủ đích; dữ liệu đã tải không thể tự thu hồi |
| Ngoại lệ | Có phạm vi, căn cứ, người chịu trách nhiệm và thời hạn được duyệt |

Ma trận yêu cầu mẫu:

| ID | Nghĩa vụ | Liên kết kiến trúc và bằng chứng |
| --- | --- | --- |
| SR-FIELD-01 | Quyền theo đối tượng và tenant là điều kiện nền | Kiểm tra tài nguyên thật trước quyền trường; ca đổi ID/tenant |
| SR-FIELD-02 | Đọc đầy đủ, che và bỏ trường có nghĩa rõ ràng | View plan và serializer; payload không chứa giá trị ngoài quyền |
| SR-FIELD-03 | Ghi chỉ trên tập trường và thao tác được cấp | DTO lệnh và điểm ghi; ca mass assignment, null và trường hệ thống |
| SR-FIELD-04 | Đường dẫn, alias, trường lồng nhau và patch dùng cùng danh mục | Mapper, resolver và parser; ca thay đối tượng cha/copy/move |
| SR-FIELD-05 | Lọc, sắp xếp và tổng hợp không đi vòng quyền | Query planner và API thống kê; ca suy luận qua tập kết quả |
| SR-FIELD-06 | Mọi điểm phát hành dùng view phù hợp bên nhận | API, job, file, email; kiểm kê tuyến và kiểm tra nội dung |
| SR-FIELD-07 | Cache và thu hồi giữ giới hạn phát hành mới 60 giây của tình huống | Các tầng cache; đo từ commit thu hồi đến response cuối |
| SR-FIELD-08 | Ghi gắn với trạng thái và phiên bản được đánh giá | Giao dịch hoặc điều kiện cập nhật; ca cạnh tranh |
| SR-FIELD-09 | Audit và lỗi không chứa giá trị ngoài quyền | Log, trace, lỗi và công cụ hỗ trợ; dữ liệu đánh dấu tổng hợp |
| SR-FIELD-10 | Trường mới mặc định chưa được công bố hoặc ghi | Schema, serializer, export; thêm thuộc tính giả để kiểm tra |

Các ngưỡng, ID và hợp đồng trong bài là cấu trúc minh họa cho một bộ yêu cầu. Việc viện dẫn một nguyên tắc như đặc quyền tối thiểu vẫn cần được chuyển thành các trường, thao tác và bằng chứng cụ thể của sản phẩm.

## 13. Kế hoạch nghiệm thu theo bề mặt dữ liệu

Các ca sau là kế hoạch kiểm thử, không phải kết quả đã chạy.

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| AT-FL-01 | Học viên đọc hồ sơ của mình | Chỉ các trường được cấp; điểm chưa công bố và ghi chú nội bộ không xuất hiện |
| AT-FL-02 | Giảng viên phụ trách đọc liên hệ | Chỉ có bản che đã quy định; không có giá trị gốc trong trường phụ |
| AT-FL-03 | Đổi ID hồ sơ hoặc tenant nhưng giữ tên trường hợp lệ | Không nhận dữ liệu của đối tượng ngoài quyền |
| AT-FL-04 | Hỗ trợ không có vụ việc hoặc phạm vi phù hợp yêu cầu liên hệ đầy đủ | Không được cấp FULL |
| AT-FL-05 | Thêm finalScore, owner hoặc tenant vào lệnh sửa liên hệ | Từ chối toàn bộ lệnh; không có thay đổi nghiệp vụ |
| AT-FL-06 | Gửi null, chuỗi rỗng và trường vắng mặt | Đúng từng ngữ nghĩa; không xóa ngầm dữ liệu |
| AT-FL-07 | Gửi chuỗi che từ form trong khi không có lệnh đổi liên hệ | Không ghi đè giá trị thật bằng chuỗi hiển thị |
| AT-FL-08 | PUT từ client chỉ nhìn thấy một phần đối tượng | Không làm mất hoặc thay đổi trường ngoài quyền |
| AT-FL-09 | Thay contact ở cấp cha, dùng alias và trường lồng nhau | Mỗi thay đổi quy về trường logic đúng và chịu quyền tương ứng |
| AT-FL-10 | Copy/move từ trường không được đọc hoặc vào trường không được ghi | Bị từ chối, không có bản sao rò rỉ |
| AT-FL-11 | Dùng lọc hoặc sắp xếp theo điểm chưa công bố | Không có kênh truy vấn ngoài quyền đã định nghĩa |
| AT-FL-12 | Lấy count, phân trang hoặc thống kê nhóm nhỏ | Chỉ trả thông tin trong chính sách của loại kết quả |
| AT-FL-13 | Mở payload, DOM, dữ liệu hydration, lỗi và trace | Không có giá trị ngoài view được cấp |
| AT-FL-14 | Prime cache bằng view hỗ trợ rồi đọc với tài khoản giảng viên | Không nhận view có quyền rộng hơn |
| AT-FL-15 | Thu hồi quyền khi cache đang nóng, làm mất thông báo vô hiệu hóa | Sau tối đa 60 giây không phát hành mới giá trị đầy đủ dựa trên quyền cũ |
| AT-FL-16 | Dùng revalidation hoặc 304 sau khi quyền thay đổi | Không giữ khả năng sử dụng view cũ ngoài hợp đồng |
| AT-FL-17 | Chuyển hồ sơ khỏi DRAFT giữa kiểm tra và cập nhật điểm | Không ghi bằng quyết định gắn với trạng thái cũ |
| AT-FL-18 | Một phần tử bulk chứa trường cấm | Không ghi phần tử nào theo hợp đồng tất cả hoặc không có gì |
| AT-FL-19 | Export, gửi email hoặc chạy job sau thu hồi quyền | Giữ đúng scope trường và các điểm kiểm tra đã cam kết |
| AT-FL-20 | Thêm thuộc tính mới vào entity hoặc schema | Không tự xuất hiện trong response, request ghi hoặc file |
| AT-FL-21 | Bộ quyết định timeout hoặc phép che lỗi | Không có nhánh trả entity đầy đủ để dự phòng |
| AT-FL-22 | Dùng dữ liệu tổng hợp đánh dấu trên đường thành công và lỗi | Không có giá trị nhạy cảm ngoài quyền trong telemetry và công cụ hỗ trợ |

Mỗi ca cần kiểm tra cả dữ liệu trả về lẫn tác động lưu trữ. Một mã 403 không chứng minh an toàn nếu cơ sở dữ liệu đã bị cập nhật trước khi trả lỗi. Tương tự, một mã 200 không chứng minh sai nếu hợp đồng cho phép view một phần và dữ liệu trả đúng phạm vi.

Các ca bị từ chối cần đi cùng ca được phép để chứng minh hệ thống vẫn hỗ trợ nghiệp vụ hợp lệ. Với masking, kiểm tra cả giá trị ngắn, giá trị thiếu và dữ liệu không hợp lệ theo hợp đồng để tránh rơi về nguyên văn.

Với thu hồi và cạnh tranh cập nhật, cần điều khiển thời điểm và đo qua từng tầng liên quan. Không chỉ thực hiện hai thao tác tuần tự rồi kết luận cửa sổ cạnh tranh đã được xử lý.

## 14. Duy trì yêu cầu theo vòng đời dữ liệu và phát triển

Ở giai đoạn phân tích, lập danh mục trường và các bên sử dụng; gắn mỗi quyền với mục tiêu nghiệp vụ và rủi ro. Ở giai đoạn thiết kế, xác định ngữ nghĩa đọc/che/ghi, nguồn thuộc tính và mọi điểm phát hành.

Khi triển khai, tách hợp đồng lệnh khỏi view đọc và tránh ánh xạ toàn bộ entity ra ngoài. Khi nghiệm thu, nối từng yêu cầu với payload, tác động dữ liệu và kịch bản lỗi. Trong vận hành, theo dõi quyết định bị từ chối bất thường, lỗi tạo view, độ trễ thu hồi và tuyến phát hành mới.

Những thay đổi cần đánh giá lại gồm thêm trường, đổi tên hoặc cấu trúc lồng nhau, mở truy vấn linh hoạt, thêm export, thay template thông báo, dùng cache mới hoặc cho dịch vụ xử lý thay người dùng. Một cột được thêm chỉ để vận hành vẫn có thể thành rò rỉ nếu serializer hoặc báo cáo tự xuất mọi thuộc tính.

Field-level authorization hoàn chỉnh là hợp đồng xuyên suốt: chủ thể chỉ nhận đúng biểu diễn được cấp, chỉ sửa đúng trường được phép, và không vượt chính sách bằng một đường truy vấn hay phát hành khác. Bằng chứng phải nối được quyền theo trường với tài nguyên thật, điểm thực thi, hành vi khi lỗi và dữ liệu thực sự đi qua ranh giới hệ thống.
