# Command allowlist (bổ sung 2)

## 1. Mục tiêu và bối cảnh

Trong Privileged Access Management (PAM), command allowlist là tập quy tắc xác định những thao tác được phép thực hiện trong một phạm vi quyền đặc biệt. Chính sách này giúp biến yêu cầu “chỉ cấp quyền cần thiết” thành các hành động cụ thể mà quản trị viên hoặc tài khoản tự động hóa có thể sử dụng.

Một allowlist hữu ích không chỉ trả lời “có cho chạy chương trình này không?”. Nó còn phải trả lời:

- Ai được chạy, với danh tính đặc quyền nào?
- Chạy trên tài sản và môi trường nào?
- Chạy đúng chương trình, thao tác và tập tham số nào?
- Những đối tượng, đường dẫn hoặc dịch vụ nào được phép tác động?
- Quyền có hiệu lực trong bao lâu, gắn với yêu cầu thay đổi nào?
- Hệ thống có chặn được hành động hay chỉ ghi nhận để phân tích sau đó?
- Khi thao tác bị từ chối hoặc lớp thực thi gặp lỗi, phiên truy cập sẽ tiếp tục như thế nào?

Bài học này trình bày cách xây dựng allowlist có ràng buộc ngữ nghĩa, kết hợp với JIT/JEA, vault, giám sát phiên và command analytics. Trọng tâm là thiết kế quyền vận hành hẹp nhưng đủ dùng, thay vì chỉ lập danh sách tên lệnh.

Sau bài học, người học có thể mô tả một thao tác đặc quyền thành hợp đồng kiểm soát, nhận diện các trường hợp cho phép quá rộng, thiết kế bộ kiểm thử và đọc bằng chứng để giải thích quyết định cho phép hoặc từ chối.

## 2. Phân biệt ba lớp kiểm soát

### 2.1. Cho phép vào phiên chưa có nghĩa là cho phép mọi thao tác

Ví dụ, kỹ sư được cấp một phiên JIT tới máy chủ ứng dụng trong 15 phút. Việc PAM cho phép tạo phiên chỉ xác nhận người đó được truy cập trong khoảng thời gian đã duyệt. Nó chưa tự xác định người đó có được sửa cấu hình hệ điều hành, đọc credential hay dừng mọi dịch vụ trên máy chủ hay không.

Cần phân biệt ba lớp:

| Lớp | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Quyền truy cập | Ai được vào đâu và vào lúc nào? | Nhóm vận hành được tạo phiên tới máy chủ ứng dụng trong cửa sổ bảo trì |
| Quyền thao tác | Trong phiên đó được làm gì? | Chỉ xem trạng thái và khởi động lại một dịch vụ được chỉ định |
| Phân tích hành vi | Chuỗi thao tác có bất thường hoặc sai mục đích không? | Liên tiếp yêu cầu những thao tác ngoài phạm vi ticket |

JIT giới hạn thời gian tồn tại của quyền; JEA giới hạn phạm vi thao tác. Command allowlist có thể là một phần của cơ chế thực hiện JEA, nhưng hiệu lực phụ thuộc vào nơi chính sách được thực thi và những đường truy cập còn tồn tại.

### 2.2. Allowlist thực thi và allowlist phân tích khác nhau

Một bộ phân tích log có thể gán nhãn “ngoài allowlist” cho một lệnh đã chạy. Đó là quyết định phân tích, không phải bằng chứng rằng lệnh đã bị chặn.

Trong bài học này, dùng hai khái niệm rõ ràng:

- **Allowlist thực thi:** được kiểm tra trước khi cấp khả năng thực hiện thao tác; quyết định có thể ngăn hành động.
- **Allowlist phân tích:** dùng để phân loại các sự kiện quan sát được; giúp phát hiện, điều tra hoặc đề xuất điều chỉnh.

Một gateway chỉ quan sát dòng nhập ở terminal có thể không nhìn thấy đầy đủ lời gọi API, tác vụ chạy nền hoặc đường truy cập trực tiếp tới máy chủ. Vì vậy, không suy ra rằng “không thấy lệnh cấm trong log” đồng nghĩa “không thể thực hiện hành động cấm”.

### 2.3. Denylist bổ sung không thay thế allowlist

Denylist liệt kê các hành động bị cấm. Allowlist bắt đầu từ tập hành động được phép và từ chối những trường hợp còn lại trong phạm vi mà nó kiểm soát.

Một denylist có thể chặn vài chuỗi lệnh dễ nhận biết nhưng bỏ sót những cách biểu diễn tương đương. Ngược lại, allowlist quá rộng, chẳng hạn cho phép một shell hoặc một trình thông dịch với tham số tùy ý, có thể trao khả năng thực thi tổng quát dù chỉ có một dòng quy tắc.

Đơn vị đánh giá phù hợp là **khả năng thực hiện hành động**, không phải số lượng tên lệnh xuất hiện trong chính sách.

## 3. Mô hình một yêu cầu thực thi có thể kiểm soát

Có thể mô tả yêu cầu đặc quyền bằng bộ thông tin:

```text
Yêu cầu =
  người gọi
  + danh tính thực thi
  + tài sản đích
  + thao tác
  + đối tượng tác động
  + tham số
  + môi trường thực thi
  + phiên cấp quyền
  + thời điểm
```

Ví dụ, “khởi động lại dịch vụ” còn quá rộng. Một yêu cầu cụ thể hơn là:

> Kỹ sư thuộc nhóm vận hành ứng dụng, đã xác thực và có grant JIT còn hiệu lực, được yêu cầu thao tác restart đối với dịch vụ payment-api trên đúng máy chủ đã được phê duyệt trong môi trường staging.

Không được xem tên nhóm, mã ticket hoặc tên môi trường do người gọi gửi lên là dữ liệu đã đáng tin. Lớp thực thi phải lấy hoặc xác minh các giá trị đó từ nguồn quản lý danh tính, inventory và hệ thống phê duyệt phù hợp.

Một mô hình quyết định ở mức thiết kế:

```text
Cho phép khi:
  danh tính hợp lệ
  VÀ grant còn hiệu lực
  VÀ tài sản nằm trong phạm vi grant
  VÀ thao tác nằm trong policy
  VÀ đối tượng tác động được phép
  VÀ tham số đáp ứng ràng buộc
  VÀ lớp thực thi đang hoạt động đúng hợp đồng

Các trường hợp còn lại: từ chối yêu cầu.
```

Đây là logic khái niệm, không phải cú pháp cấu hình của một sản phẩm PAM cụ thể.

## 4. Từ tên lệnh sang hợp đồng thao tác

### 4.1. Vì sao tên executable chưa đủ?

Giả sử policy cho phép một công cụ quản lý dịch vụ. Nếu mọi tham số đều được chấp nhận, người dùng có thể tác động tới các dịch vụ không thuộc nhiệm vụ, hoặc sử dụng những chức năng khác của cùng công cụ.

Một chương trình còn có thể:

- Đọc cấu hình hoặc plugin từ vị trí người dùng kiểm soát.
- Tải thư viện hoặc gọi chương trình con.
- Mở editor, pager hoặc shell tương tác.
- Nhận đường dẫn đầu ra và ghi vào vị trí nhạy cảm.
- Kết nối mạng tới đích không thuộc phạm vi công việc.
- Đọc dữ liệu từ file có nội dung thay đổi giữa lúc kiểm tra và lúc sử dụng.

Vì vậy, “đã cho phép chương trình A” không tự chứng minh rằng “chỉ hành động B có thể xảy ra”.

### 4.2. Mẫu hợp đồng tối thiểu

| Thành phần | Ràng buộc cần mô tả | Lý do |
| --- | --- | --- |
| Người gọi | Nhóm, vai trò, điều kiện xác thực | Không trao thao tác cho mọi người có phiên |
| Danh tính thực thi | Tài khoản đích có quyền tối thiểu | Giảm phạm vi ảnh hưởng nếu công cụ bị lạm dụng |
| Tài sản | Định danh máy chủ hoặc tập tài sản có kiểm soát | Tránh mở rộng sang máy chủ khác cùng tên dịch vụ |
| Thao tác | Giá trị hữu hạn như status, restart | Tránh biến thao tác thành chuỗi tùy ý |
| Đối tượng | Dịch vụ hoặc tài nguyên đã phê duyệt | Giới hạn phạm vi nghiệp vụ |
| Tham số | Kiểu dữ liệu, tập giá trị, giới hạn | Không để cờ tùy chọn mở thêm khả năng |
| Môi trường | Cấu hình, thư mục làm việc, đường dẫn tin cậy | Giảm ảnh hưởng của môi trường người gọi |
| Thời hạn | Grant JIT và cửa sổ thay đổi | Không để quyền tồn tại vô hạn |
| Bằng chứng | Mã policy, phiên bản, quyết định, kết quả | Giải thích được hành động sau này |

Tùy mô hình triển khai, lớp thực thi có thể là agent trên máy đích, endpoint giới hạn thao tác, wrapper đặc quyền hoặc dịch vụ điều phối. Cần đánh giá chính cơ chế đó, không mặc định mọi gateway đều có khả năng kiểm soát giống nhau.

### 4.3. Ưu tiên thao tác có cấu trúc khi nhiệm vụ cho phép

Thay vì nhận một chuỗi lệnh tự do:

```text
execute(command_text)
```

có thể thiết kế giao diện hẹp:

```text
restart_application_service(asset_id, service_id, grant_id)
```

Dịch vụ thực thi tự ánh xạ `service_id` tới dịch vụ hợp lệ và tự dựng lời gọi hệ thống từ dữ liệu đã kiểm tra. Người gọi không được cung cấp tên executable, cờ tùy ý hoặc danh tính chạy thay.

Cách này không làm mất nhu cầu bảo vệ mã nguồn, cấu hình và quyền của dịch vụ thực thi. Nó giảm số cách biểu diễn đầu vào và làm ranh giới kiểm soát dễ kiểm thử hơn.

## 5. Chuỗi lệnh, argv và ngữ nghĩa thực thi

### 5.1. Không đồng nhất chuỗi hiển thị với yêu cầu thực tế

Một dòng chữ trong log có thể là:

- Dữ liệu người dùng nhập.
- Dòng do shell xử lý.
- Biểu diễn lại của executable và các đối số.
- Thông tin được suy từ một sự kiện tiến trình.
- Chuỗi đã được cắt ngắn hoặc che dữ liệu nhạy cảm.

Những dữ liệu này có giá trị khác nhau. Không nên dùng một trường `command_text` duy nhất để vừa thực thi policy, vừa điều tra và khẳng định chính xác chương trình đã làm gì.

Nếu nền tảng cung cấp được dữ liệu có cấu trúc, nên tách các trường như executable, danh sách đối số, người gọi, tài khoản thực thi, tài sản, thư mục làm việc và nguồn quan sát. Đồng thời ghi rõ giới hạn: thiếu đối số, log bị cắt, thiếu sự kiện kết thúc hoặc không thấy tiến trình con.

### 5.2. Shell tạo thêm một lớp diễn giải

Chuỗi lệnh đưa qua shell có thể chứa cơ chế nối nhiều thao tác, chuyển hướng dữ liệu, mở rộng biến hoặc gọi lồng. Bộ kiểm tra chuỗi và shell có thể hiểu cùng đầu vào theo hai cách khác nhau.

Với một tác vụ đặc quyền hữu hạn, thiết kế thường dễ kiểm soát hơn khi:

1. Nhận một yêu cầu có cấu trúc.
2. Kiểm tra từng trường theo kiểu dữ liệu và tập giá trị.
3. Dựng danh sách đối số nội bộ.
4. Gọi trực tiếp chương trình đích mà không yêu cầu shell diễn giải đầu vào của người dùng.

Điều này chỉ loại bỏ một lớp diễn giải; chương trình đích vẫn có cú pháp tham số riêng và có thể gọi thêm thành phần khác. Vì vậy vẫn phải đánh giá hành vi của executable và những file nó sử dụng.

### 5.3. Tránh kiểm tra theo tiền tố

Quy tắc “chuỗi bắt đầu bằng tên lệnh được phép” thường không đủ. Tiền tố không nói lên những tham số phía sau, đối tượng bị tác động hoặc việc có thêm một thao tác khác trong cùng chuỗi.

Tương tự, wildcard quá rộng có thể cho phép những giá trị ngoài dự kiến. Regex chỉ hữu ích khi người thiết kế biết rõ ngữ pháp, quy tắc mã hóa, ranh giới toàn chuỗi và cách executor diễn giải dữ liệu.

Đối với một thao tác chỉ chấp nhận hai hành động và một dịch vụ cố định, enum cùng ánh xạ tài nguyên thường dễ kiểm chứng hơn một biểu thức tổng quát.

### 5.4. Chuẩn hóa phải theo loại dữ liệu

Chuẩn hóa không phải là chuyển toàn bộ đầu vào thành chữ thường rồi so sánh. Việc thay đổi chữ hoa, khoảng trắng, dấu phân cách hoặc ký tự có thể làm thay đổi ý nghĩa trên một số nền tảng.

Một quy trình phù hợp là:

- Xác định trường nào là enum, số, định danh inventory hoặc đường dẫn.
- Dùng quy tắc chuẩn hóa tương ứng với nền tảng và loại dữ liệu.
- Từ chối đầu vào mơ hồ hoặc ngoài ngữ pháp được hỗ trợ.
- Kiểm tra chính dữ liệu mà executor sẽ sử dụng.
- Không sửa lại chuỗi sau khi đã phê duyệt theo cách có thể đổi nghĩa.

Nếu bộ phân tích không xác định được yêu cầu thuộc trường hợp nào, không tự nới policy để “đoán đúng ý người dùng”.

## 6. Đường dẫn và các đầu vào gián tiếp

### 6.1. Đường dẫn tuyệt đối có ích nhưng chưa đủ

Chỉ định executable bằng đường dẫn tuyệt đối giúp giảm phụ thuộc vào cơ chế tìm chương trình. Tuy nhiên, cần kiểm tra thêm:

- Người gọi có quyền thay thế executable không?
- Những thư mục cha có thể bị sửa hay thay liên kết không?
- File cấu hình, thư viện hoặc plugin được nạp từ đâu?
- Thư mục làm việc có ảnh hưởng tới việc nạp tài nguyên không?
- Chính chương trình được phép có thể chạy thêm mã tùy ý không?

Kiểm soát đường dẫn không thay thế việc bảo vệ chuỗi phụ thuộc thực thi.

### 6.2. File đầu vào có thể mang quyền hành động

Ví dụ, một wrapper chỉ chấp nhận đường dẫn file dưới thư mục được duyệt. Nếu nội dung file có thể điều khiển thêm thao tác, việc xác nhận đường dẫn chưa kiểm soát hết hành vi.

Cần phân biệt:

- **File dữ liệu:** được xử lý theo schema hẹp, không mang khả năng thực thi.
- **File cấu hình:** có thể thay đổi đích, chức năng hoặc hành vi của công cụ.
- **File mã hoặc plugin:** trực tiếp mở rộng khả năng chạy mã.

Cho phép người dùng đưa một file cấu hình tùy ý vào công cụ đặc quyền có thể tạo phạm vi quyền rộng hơn nhiều so với thao tác ban đầu.

### 6.3. Khoảng cách kiểm tra và sử dụng

Nếu hệ thống kiểm tra một file rồi sau đó mở lại theo đường dẫn, tài nguyên có thể thay đổi trong khoảng thời gian giữa hai bước. Đây là vấn đề kiểm tra rồi mới sử dụng, thường gọi là TOCTOU.

Biện pháp cụ thể phụ thuộc hệ điều hành và giao diện lập trình, nhưng mục tiêu thiết kế nhất quán:

- Giảm khả năng người gọi sửa tài nguyên đã kiểm tra.
- Gắn việc xác minh với đúng đối tượng mà thao tác thực sự sử dụng.
- Giới hạn quyền ghi vào đường dẫn và các thư mục liên quan.
- Tránh xem việc lấy đường dẫn chuẩn một lần là bảo đảm vĩnh viễn.
- Đánh giá cả thay đổi nội dung lẫn thay đổi đối tượng phía sau đường dẫn.

Nếu không chứng minh được ràng buộc đường dẫn an toàn cho một tác vụ, hãy xem xét giao diện dùng định danh tài nguyên đã quản lý thay vì nhận đường dẫn tự do.

## 7. Thiết kế một policy minh họa

### 7.1. Tình huống

Nhóm AppOps cần xem trạng thái và khởi động lại dịch vụ payment-api trên một máy staging trong cửa sổ thay đổi. Họ không cần quyền quản trị tổng quát, không cần xem credential và không cần tác động tới dịch vụ khác.

Policy sau là **schema minh họa phục vụ thiết kế**, không phải cấu hình có thể nạp trực tiếp vào sản phẩm:

```yaml
policy_id: pam-appops-payment-service
version: 4
default_decision: deny

subject:
  approved_group: appops
  authentication_required: true

target:
  asset_ids:
    - staging-app-17
  environment: staging

grant:
  jit_required: true
  approved_change_required: true
  maximum_duration_minutes: 15
  validate_at_each_request: true

operations:
  - action: service_status
    service_id: payment-api
  - action: service_restart
    service_id: payment-api

execution:
  entrypoint: managed-service-operations
  raw_command_input: false
  caller_selected_executable: false
  caller_selected_run_as: false
  caller_supplied_environment: false
  caller_supplied_config: false

failure:
  policy_unavailable: deny
  invalid_or_expired_grant: deny
  unrecognized_operation: deny
```

Các cờ trong ví dụ diễn tả yêu cầu cần hiện thực, không tự tạo ra ràng buộc an toàn. Đội triển khai phải xác định cơ chế thực thi tương ứng và bằng chứng kiểm thử cho từng ràng buộc.

### 7.2. Nguồn dữ liệu và phân quyền của executor

Executor cần ánh xạ `staging-app-17` và `payment-api` từ dữ liệu do tổ chức quản lý. Không sử dụng giá trị hiển thị do client tự khai để quyết định môi trường hoặc đích thực thi.

Danh tính thực thi chỉ nên có quyền cần cho hai thao tác đã thiết kế. Nếu quyền hẹp cần một cơ chế trung gian, cơ chế đó phải bảo vệ được đầu vào, mã nguồn, cấu hình và đường gọi. Trường hợp nền tảng bắt buộc dùng danh tính có quyền rộng hơn, phải ghi nhận đó là rủi ro còn lại và kiểm soát chặt điểm thực thi.

Vault có thể giữ credential của danh tính đặc quyền, nhưng việc lưu trong vault không tự giới hạn hành động sau khi credential được sử dụng. Nếu người dùng nhận được credential có thể dùng trực tiếp ngoài executor, khả năng đi vòng allowlist phải được đánh giá riêng.

### 7.3. Luồng thực thi khái niệm

```text
Người dùng yêu cầu restart payment-api
        |
        v
Xác thực danh tính + lấy grant đã duyệt
        |
        v
Kiểm tra tài sản, thao tác, đối tượng, thời hạn
        |
        +-- không hợp lệ --> từ chối + ghi quyết định
        |
        v
Executor tạo lời gọi nội bộ đã ràng buộc
        |
        v
Thực thi bằng danh tính được quản lý
        |
        v
Ghi kết quả + liên kết session/grant/policy
```

Không chuyển sang một đường chạy rộng hơn chỉ vì executor không nhận diện thao tác. Yêu cầu mới phải đi qua quy trình bổ sung hoặc ngoại lệ có phê duyệt.

### 7.4. Thu hồi có hai phạm vi khác nhau

Grant hết hạn có thể chặn yêu cầu mới, nhưng chưa chắc dừng được công việc đã được khởi tạo trước đó. Nếu một thao tác tạo tiến trình hoặc tác vụ dài, cần quy định:

- Thời điểm kiểm tra quyền: khi nhận yêu cầu, khi bắt đầu, và tại những điểm nào khác.
- Tác vụ có được tiếp tục sau khi grant hết hạn không.
- Cơ chế hủy hoặc kết thúc tác vụ có được hỗ trợ không.
- Hành động nào cần dừng mềm để tránh gây lỗi dịch vụ.
- Ai được quyết định tiếp tục một tác vụ đang ảnh hưởng tới vận hành.

Không tuyên bố “thu hồi quyền tức thì” nếu hệ thống chỉ ngăn phiên hoặc yêu cầu mới.

## 8. Kiểm thử chính sách bằng tình huống có kết quả mong đợi

Bộ kiểm thử cần gồm trường hợp hợp lệ, trường hợp bị từ chối và lỗi của chính lớp thực thi. Mục tiêu là kiểm chứng ranh giới quyền; không cần chạy thử trên tài sản sản xuất để chứng minh thiết kế ban đầu.

### 8.1. Ma trận kiểm thử cho tình huống AppOps

| Mã | Điều kiện hoặc yêu cầu | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- |
| A01 | Đúng người, grant còn hạn, xem trạng thái đúng dịch vụ | Cho phép | Policy v4, grant, sự kiện bắt đầu và kết quả |
| A02 | Đúng người, grant còn hạn, restart đúng dịch vụ | Cho phép | Đúng tài sản, đúng thao tác, kết quả thực thi |
| D01 | Cùng người nhưng yêu cầu dịch vụ khác | Từ chối trước thực thi | Lý do đối tượng ngoài phạm vi |
| D02 | Đúng dịch vụ nhưng tài sản production | Từ chối trước thực thi | Tài sản ngoài grant hoặc policy |
| D03 | Grant hết hạn trước lúc bắt đầu thao tác | Từ chối | Thời điểm kiểm tra và thời điểm hết hạn |
| D04 | Gửi thêm tham số không có trong hợp đồng | Từ chối | Lỗi schema hoặc tham số ngoài phạm vi |
| D05 | Cung cấp executable hoặc tài khoản chạy thay | Từ chối | Trường đầu vào không được hỗ trợ |
| D06 | Gửi chuỗi raw command thay cho thao tác có cấu trúc | Từ chối | Yêu cầu không thuộc giao diện được cấp |
| D07 | Người dùng không thuộc nhóm được phê duyệt | Từ chối | Kết quả xác minh danh tính hoặc grant |
| F01 | Không đọc được policy có hiệu lực | Từ chối theo hợp đồng | Sự kiện lỗi policy, không có hành động đích |
| F02 | Kênh thực thi bị đứt sau khi bắt đầu | Trạng thái không xác định cho tới khi đối soát | Liên kết yêu cầu và bằng chứng từ đích |
| F03 | Đường truy cập trực tiếp tồn tại ngoài executor | Ghi nhận lỗ hổng phạm vi kiểm soát | Kết quả kiểm tra đường truy cập và quyền thực tế |

Dòng F03 không thể được giải quyết chỉ bằng cách thêm một regex. Nó đòi hỏi xử lý đường truy cập hoặc quyền có thể vượt qua điểm thực thi.

### 8.2. Kiểm thử biến thể đầu vào

Với những trường hợp có tham số, cần xem xét:

- Giá trị rỗng, quá dài hoặc sai kiểu.
- Giá trị gần giống định danh được phép.
- Trường trùng lặp trong giao thức đầu vào.
- Ký tự điều khiển hoặc ký tự không thuộc schema.
- Mã hóa hoặc cách biểu diễn khiến bộ kiểm tra và executor hiểu khác nhau.
- Tham số hợp lệ riêng lẻ nhưng không hợp lệ khi kết hợp.
- Mất dữ liệu do log cắt ngắn hoặc do bước chuẩn hóa.
- Thay đổi tài nguyên sau khi yêu cầu đã được kiểm tra.

Kết quả mong đợi phải rõ. “Không thấy lỗi” chưa đủ; một trường hợp bị từ chối cần có bằng chứng rằng thao tác không được gửi tới đích trong phạm vi có thể quan sát.

### 8.3. Kiểm thử quyền của các thành phần

Ngoài request, cần kiểm tra các giả định triển khai:

- Người dùng có sửa được wrapper hoặc policy không?
- Executor có nạp cấu hình từ thư mục người gọi ghi được không?
- Danh tính thực thi có quyền không liên quan tới nhiệm vụ không?
- Có tài khoản dùng chung làm mất khả năng truy vết người thực sự thao tác không?
- Phiên không đi qua PAM còn hoạt động không?
- Thu hồi grant có chặn được yêu cầu mới như thiết kế không?
- Cập nhật policy có làm các node thực thi dùng phiên bản khác nhau không?

Một policy được viết hẹp nhưng có thể bị người gọi sửa lại không tạo ra ranh giới quyền đáng tin.

## 9. Command analytics hỗ trợ vận hành allowlist

### 9.1. Quan sát để tìm nhu cầu, không tự động hợp thức hóa hành vi

Ở giai đoạn thiết kế, command analytics giúp tìm các thao tác thường dùng, tham số biến thiên và những bước thực sự cần quyền đặc biệt.

Tuy nhiên:

- Thao tác xuất hiện thường xuyên có thể là thói quen cấp quyền quá rộng.
- Thao tác hiếm gặp có thể là nhiệm vụ phục hồi hợp lệ.
- Một hành động thành công không đồng nghĩa đã được phê duyệt.
- Một hành động bị từ chối không đồng nghĩa người dùng có ý đồ xấu.

Vì vậy, dữ liệu quan sát là đầu vào để chủ dịch vụ và chủ quyền phê duyệt, không phải căn cứ tự động thêm lệnh vào allowlist.

### 9.2. Chuyển log thành ứng viên thao tác

Một quy trình xây dựng ứng viên:

1. Chọn tập phiên có nguồn gốc và mục đích công việc rõ.
2. Nhóm theo loại công việc, tài sản và danh tính thực thi.
3. Tách thao tác thực sự cần quyền cao khỏi các bước có thể chạy bằng quyền thường.
4. Nhận diện executable, đối số và tài nguyên có liên quan nếu dữ liệu quan sát cho phép.
5. Đề xuất giao diện thao tác hẹp cùng điều kiện JIT.
6. Nhờ chủ dịch vụ xác nhận nhu cầu và tác động.
7. Kiểm thử trước khi chuyển từ quan sát sang thực thi.

Không rút gọn mọi khác biệt tham số thành wildcard. Một tham số thay đổi có thể đại diện cho tài nguyên ngoài phạm vi, đường dẫn cấu hình khác hoặc hành vi hoàn toàn khác.

### 9.3. Các chỉ số có ý nghĩa

| Chỉ số | Cách đọc | Điểm cần tránh |
| --- | --- | --- |
| Tỷ lệ từ chối trên yêu cầu đã đánh giá | Cho biết mức ma sát và nhu cầu xem xét | Không tự kết luận tỷ lệ cao là tấn công |
| Yêu cầu hợp lệ bị từ chối đã xác minh | Cho thấy policy hoặc dữ liệu cấp quyền chưa đủ | Không mở rộng quyền chỉ từ phàn nàn chưa đối soát |
| Số yêu cầu dùng ngoại lệ | Cho thấy phần việc chưa được chuẩn hóa | Không để ngoại lệ trở thành quyền thường trực |
| Thời gian xử lý ngoại lệ | Đo khả năng hỗ trợ vận hành | Không giảm thời gian bằng cách bỏ phê duyệt cần thiết |
| Độ phủ sự kiện | Cho biết bao nhiêu yêu cầu có quyết định và kết quả liên kết được | Không coi thiếu log là không có hành động |
| Tỷ lệ phiên bản policy không khớp | Phát hiện node chưa đồng bộ | Không gộp mọi node thành một phiên bản giả định |

Mẫu số phải được định nghĩa. Ví dụ, “tỷ lệ từ chối 5%” cần nói rõ tính trên yêu cầu đã vào executor hay trên tất cả hoạt động đặc quyền quan sát được. Hai con số này phản ánh hai phạm vi khác nhau.

### 9.4. Phân biệt vi phạm policy và tín hiệu bất thường

Một thao tác đúng allowlist vẫn có thể bất thường: lặp lại quá nhiều lần, xảy ra trên tập tài sản khác thường hoặc không phù hợp với diễn biến ticket.

Ngược lại, một thao tác ngoài allowlist có thể là nhu cầu vận hành mới. Quyết định cho phép và điểm bất thường không nên bị trộn thành một trường duy nhất.

Có thể giữ riêng:

```text
policy_decision = ALLOW | DENY | ERROR
execution_state = NOT_STARTED | STARTED | SUCCEEDED | FAILED | UNKNOWN
analytics_assessment = thông tin đánh giá hành vi theo ngữ cảnh
```

Một trạng thái thực thi thành công chỉ cho biết executor báo hoàn thành theo tiêu chí của nó. Nếu nghiệp vụ yêu cầu dịch vụ phải hồi phục, cần kiểm tra sức khỏe dịch vụ bằng cơ chế phù hợp; không suy ra điều đó chỉ từ việc chương trình trả mã thành công.

## 10. Bằng chứng audit và bảo vệ dữ liệu

### 10.1. Ghi đủ để giải thích quyết định

Mẫu sự kiện quyết định dưới đây dùng dữ liệu giả:

```json
{
  "event_type": "pam.operation.decision",
  "request_id": "req-example-2048",
  "session_id": "session-example-73",
  "subject_id": "user-example-12",
  "execution_identity_id": "managed-identity-example-3",
  "asset_id": "staging-app-17",
  "action": "service_restart",
  "resource_id": "payment-api",
  "grant_id": "grant-example-901",
  "change_id": "change-example-210",
  "policy_id": "pam-appops-payment-service",
  "policy_version": 4,
  "decision": "ALLOW",
  "reason_code": "ALL_CONDITIONS_MATCHED",
  "executor_id": "executor-example-2",
  "event_time": "2026-01-15T09:30:00Z"
}
```

Sự kiện kết quả nên liên kết bằng `request_id`, bổ sung thời điểm bắt đầu/kết thúc và trạng thái thực thi. Đối với hành động bị từ chối, trạng thái tương ứng là chưa bắt đầu trong đường thực thi được kiểm soát.

Nếu có mất kết nối, không ghi thành công hoặc thất bại dựa trên suy đoán. Dùng trạng thái chưa xác định và đối soát với nguồn đích trước khi quyết định retry; thao tác có thể đã thực hiện dù client không nhận được phản hồi.

### 10.2. Không đưa secret vào đối số và log

Đối số, đầu ra phiên và nội dung lỗi có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm. Một allowlist không khiến dữ liệu đó an toàn để ghi log.

Cần thiết kế kênh cung cấp credential phù hợp với nền tảng và công cụ, tránh đưa bí mật vào command line khi có lựa chọn được hỗ trợ tốt hơn. Vault và danh tính được quản lý giúp giảm việc con người trực tiếp nhìn thấy credential, nhưng vẫn cần kiểm soát cách executor sử dụng và ghi nhận chúng.

Nên ghi định danh tham chiếu thay cho secret. Chỉ ghi đối số cần cho mục đích điều tra; bảo vệ log và bản ghi phiên bằng quyền truy cập, thời hạn lưu và cơ chế phát hiện sửa đổi phù hợp với yêu cầu tổ chức.

Việc che dữ liệu phải được đánh giá trên cả luồng sự kiện, bản ghi phiên, đầu ra và thông báo lỗi. Không coi che một trường duy nhất là đã loại bỏ toàn bộ nguy cơ lộ bí mật.

### 10.3. Liên kết mà vẫn ghi rõ giới hạn

Bằng chứng tốt cho phép trả lời:

- Ai yêu cầu thao tác và ai phê duyệt quyền?
- Quyền áp dụng cho tài sản, tài nguyên và thời gian nào?
- Node thực thi đã dùng phiên bản policy nào?
- Vì sao yêu cầu được phép hoặc bị từ chối?
- Thao tác có bắt đầu không và kết quả quan sát được là gì?
- Có mất dữ liệu hoặc đường truy cập không nằm trong phạm vi quan sát không?

Bản ghi terminal, sự kiện tiến trình và log của executor có thể bổ sung cho nhau. Không cần giả định một nguồn duy nhất luôn phản ánh đầy đủ mọi hành động.

## 11. Vòng đời thay đổi policy

### 11.1. Từ nhu cầu đến policy có hiệu lực

Một thay đổi allowlist nên có:

1. Mục đích nghiệp vụ và người sở hữu.
2. Đối tượng được cấp quyền và danh tính thực thi.
3. Tập tài sản, thao tác, tài nguyên và tham số.
4. Ràng buộc JIT, điều kiện phê duyệt và thời hạn.
5. Các giả định về điểm thực thi và những đường truy cập khác.
6. Bộ kiểm thử cho phép, từ chối và lỗi.
7. Kế hoạch triển khai, quan sát và hoàn tác.
8. Thời điểm rà soát hoặc hết hiệu lực nếu là quyền tạm thời.

Khi cập nhật, cần biết node nào đã nhận phiên bản mới. Việc sửa một policy trung tâm không chứng minh mọi executor đã áp dụng ngay lập tức.

### 11.2. Triển khai có phạm vi

Có thể bắt đầu với một nhóm người dùng và một tập tài sản thử nghiệm có đại diện. Chế độ chỉ quan sát giúp thu thập dữ liệu nhưng không cung cấp cùng mức ngăn chặn như chế độ thực thi.

Trước khi mở rộng, đánh giá yêu cầu hợp lệ bị từ chối, độ phủ log, khả năng hỗ trợ vận hành và tính nhất quán của policy trên các node. Không đặt mục tiêu số lượng quy tắc lớn; ưu tiên ranh giới quyền rõ và có bằng chứng.

### 11.3. Hoàn tác cũng phải có phạm vi quyền

Hoàn tác về phiên bản cũ có thể khôi phục cả quyền rộng đã bị loại bỏ. Vì vậy, cần xác định phiên bản được phép hoàn tác và người chịu trách nhiệm cho quyết định đó.

Khi policy mới gây sự cố, hướng xử lý có thể là dừng mở rộng, thu hẹp phạm vi thí điểm hoặc dùng ngoại lệ đã phê duyệt cho tác vụ cụ thể. Không mặc định đổi toàn bộ hệ thống sang cho phép mọi lệnh.

### 11.4. Ngoại lệ và break-glass

Ngoại lệ cần chỉ rõ chủ thể, tài sản, tác vụ, lý do, người phê duyệt và thời điểm kết thúc. Tùy mức độ khẩn cấp, tổ chức có thể dùng quy trình break-glass riêng với điều kiện xác thực, giám sát và rà soát sau sự kiện.

Break-glass là một tuyến quyền được quản lý, không phải lỗi thực thi khiến hệ thống tự mở quyền. Sau khi sử dụng, cần thu hồi quyền tạm, kiểm tra credential liên quan theo chính sách và xem xét nhu cầu có nên trở thành một thao tác chuẩn hay không.

## 12. Những sai lầm thiết kế thường gặp

| Sai lầm | Hệ quả | Hướng điều chỉnh |
| --- | --- | --- |
| Cho phép tên executable cùng mọi đối số | Quyền thực tế rộng hơn nhiệm vụ | Giới hạn thao tác, tham số và tài nguyên |
| Coi chuỗi terminal là toàn bộ sự thật | Bỏ sót hành động ngoài terminal hoặc thiếu dữ liệu | Kết hợp nguồn quan sát, ghi rõ độ phủ |
| Nhận raw command rồi kiểm tra tiền tố | Bộ kiểm tra không nắm ngữ nghĩa thực thi | Dùng giao diện có cấu trúc khi phù hợp |
| Cho phép trình thông dịch tổng quát để xử lý một việc nhỏ | Mở khả năng chạy hành động tùy ý | Cung cấp thao tác hẹp bằng executor được quản lý |
| Đường dẫn đúng nhưng file hoặc thư mục cha sửa được | Đối tượng được thực thi có thể bị thay đổi | Bảo vệ chuỗi phụ thuộc và ràng buộc đối tượng |
| Chỉ kiểm tra grant khi tạo phiên | Yêu cầu mới có thể tiếp tục sau khi quyền thay đổi | Xác định điểm kiểm tra và cơ chế thu hồi |
| Tự thêm mọi lệnh thường thấy vào allowlist | Hợp thức hóa quyền hoặc hành vi không cần thiết | Đối chiếu nhu cầu và chủ sở hữu |
| Xem thiếu log là không có hoạt động | Tạo cảm giác kiểm soát sai | Theo dõi độ phủ và trạng thái chưa xác định |
| Ghi toàn bộ đối số để phục vụ audit | Có thể làm lộ secret | Giảm dữ liệu nhạy cảm và bảo vệ bằng chứng |
| Cho phép mọi thao tác khi policy lỗi | Sự cố kiểm soát biến thành cấp quyền rộng | Định nghĩa xử lý lỗi và tuyến khẩn cấp riêng |

## 13. Bài tập thực hành

### Đề bài

Một nhóm vận hành có quyền dùng công cụ quản lý dịch vụ với tham số tùy ý. Trong tháng vừa qua, log chủ yếu ghi nhận xem trạng thái và restart hai dịch vụ ứng dụng. Nhóm đề xuất allowlist toàn bộ công cụ để “không ảnh hưởng vận hành”.

Hãy thiết kế lại phạm vi quyền với các điều kiện:

- Môi trường staging và production có phê duyệt riêng.
- Chỉ hai dịch vụ ứng dụng nằm trong phạm vi.
- Quyền được cấp theo thời gian và nhiệm vụ cụ thể.
- Người dùng không nhận credential của danh tính thực thi.
- Log phải phân biệt quyết định cấp quyền và kết quả thao tác.
- Nhu cầu ngoài policy đi qua ngoại lệ có thời hạn.

### Sản phẩm cần tạo

1. Một bảng hợp đồng thao tác gồm người gọi, tài sản, hành động, tài nguyên và điều kiện.
2. Một policy khái niệm không dùng wildcard cho tài nguyên hoặc tham số.
3. Ít nhất ba trường hợp cho phép, năm trường hợp từ chối và hai trường hợp lỗi.
4. Một mẫu sự kiện quyết định và một mẫu sự kiện kết quả đã loại bỏ secret.
5. Một giải thích về đường truy cập nào có thể vượt điểm thực thi và cách kiểm chứng.

### Gợi ý tự đánh giá

Thiết kế đạt mục tiêu khi có thể giải thích vì sao một yêu cầu cụ thể được phép, vì sao yêu cầu gần giống bị từ chối và bằng chứng nào cho thấy điều đó. Nếu câu trả lời vẫn chỉ là “vì tên công cụ nằm trong danh sách”, phạm vi kiểm soát chưa được mô tả đủ.

Đặc biệt, hãy kiểm tra ba tình huống: cùng dịch vụ nhưng sai môi trường; cùng người dùng nhưng grant hết hạn; và công cụ đúng nhưng nhận file cấu hình do người dùng tự cung cấp. Mỗi tình huống phải có quyết định rõ ràng cùng cơ chế thực thi tương ứng.

## 14. Kết luận

Command allowlist có giá trị khi chuyển quyền đặc biệt thành những thao tác cụ thể, có ngữ cảnh và có thể giải thích bằng bằng chứng. Tên lệnh chỉ là một phần của yêu cầu; tham số, tài nguyên, danh tính thực thi, môi trường và thời hạn cùng quyết định phạm vi quyền thực tế.

Trong PAM, kết hợp allowlist với JIT/JEA, quản lý credential, bảo vệ executor và giám sát giúp thu hẹp khả năng thao tác ngoài nhiệm vụ. Command analytics hỗ trợ nhận diện nhu cầu và sai lệch, còn điểm thực thi chịu trách nhiệm ngăn hành động ngoài phạm vi đã cấp.
