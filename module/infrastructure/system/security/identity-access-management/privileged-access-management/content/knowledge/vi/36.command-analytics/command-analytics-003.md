# Command denylist

## 1. Command denylist giải quyết vấn đề gì trong PAM?

Command denylist là tập quy tắc nhận diện những lệnh, nhóm tham số hoặc hành vi thực thi không được chấp nhận trong một ngữ cảnh truy cập đặc quyền. Khi có khả năng can thiệp trước thực thi, hệ thống từ chối yêu cầu khớp quy tắc. Khi chỉ thu thập nhật ký sau thực thi, cùng quy tắc đó chỉ tạo tín hiệu phát hiện; nó không ngăn tác động đã xảy ra.

Trong chương Command analytics của PAM, denylist giúp biến yêu cầu như “tài khoản hỗ trợ không được dừng dịch vụ kiểm toán” thành một chính sách có điều kiện, có điểm kiểm soát và có bằng chứng. Chính sách cần gắn với danh tính thực, tài khoản đặc quyền được sử dụng, máy đích, mục đích phiên và quyền đã được phê duyệt.

Ví dụ, một kỹ sư được cấp phiên JIT trong 30 phút để chẩn đoán lỗi ứng dụng:

- Được xem trạng thái ứng dụng và nhật ký đã lọc dữ liệu nhạy cảm.
- Không được thay đổi cấu hình PAM, tác động hệ thống kiểm toán hoặc truy cập kho khóa riêng.
- Tác vụ khôi phục dịch vụ có quyền thay đổi cần đi qua một quy trình khác.

Denylist bổ sung một hàng rào trong phiên đã được cấp quyền. Nó không tự quyết định ai được đăng nhập, không làm giảm quyền của tài khoản hệ điều hành và không thay thế least privilege, JIT/JEA, vault hay kiểm soát hệ điều hành.

Sau bài học, người học cần làm được bốn việc:

1. Diễn đạt một yêu cầu cấm thành quy tắc có ngữ nghĩa rõ ràng.
2. Phân biệt dữ liệu nhập ở terminal, chương trình thực thi và tác động lên tài nguyên.
3. Xác định khi nào hệ thống thực sự chặn được lệnh.
4. Thiết kế kiểm thử, ngoại lệ và bằng chứng để vận hành denylist an toàn.

## 2. Phân biệt denylist, allowlist và command analytics

| Cơ chế | Câu hỏi chính | Ý nghĩa khi không khớp |
| --- | --- | --- |
| Denylist | Yêu cầu có thuộc tập bị cấm trong phạm vi này không? | Chưa có bằng chứng phải cấm theo tập quy tắc này; vẫn phải kiểm tra quyền nền |
| Allowlist | Yêu cầu có thuộc tập được cho phép rõ ràng không? | Thường từ chối hoặc chuyển sang quy trình được phê duyệt |
| Command analytics | Yêu cầu hoặc chuỗi hành vi có đáng chú ý không? | Chưa phát hiện dấu hiệu theo mô hình đang sử dụng |
| Session recording | Có thể xem lại người dùng đã làm gì không? | Không có kết luận cho phép hay từ chối chỉ từ việc ghi hình |

Một cấu hình denylist có thể cho các yêu cầu không khớp đi tiếp trong phạm vi phiên đã được cấp quyền. Điều đó không đồng nghĩa mọi lệnh không nằm trong danh sách đều an toàn.

Cách diễn giải đúng là:

> Yêu cầu phải có quyền thực thi hợp lệ trước; trong tập đã có quyền đó, denylist loại thêm những trường hợp bị cấm.

Với tác vụ quản trị lặp lại, phạm vi hẹp và mô tả được đầy đủ, một tập thao tác cho phép cố định thường dễ kiểm chứng hơn danh sách vô hạn các cách làm sai. Với phiên xử lý sự cố cần linh hoạt, denylist vẫn hữu ích để bảo vệ một số ranh giới quan trọng, nhưng mức bảo đảm phụ thuộc vào quyền thật của phiên và độ phủ của điểm thực thi.

Cần ghi rõ chế độ của mỗi quy tắc:

- `OBSERVE`: ghi nhận kết quả khớp để đo ảnh hưởng, không chặn.
- `ENFORCE`: từ chối trước thực thi tại điểm kiểm soát có khả năng cưỡng chế.
- `ALERT`: gửi cảnh báo để điều tra; có thể phát sinh từ dữ liệu sau thực thi.

Một sự kiện “đã phát hiện lệnh bị cấm” không được báo cáo thành “đã ngăn lệnh” nếu không có bằng chứng cưỡng chế trước thực thi.

## 3. Xác định chính xác thứ đang bị kiểm soát

### 3.1. Dòng nhập terminal không phải là lời gọi thực thi

Một người dùng có thể nhập:

```text
service-helper status orders
```

Ở đây `service-helper` là tên tiện ích giả định trong bài. Từ dòng nhập đến hành động thực tế có thể có nhiều bước:

```text
Dòng nhập ở terminal
        |
        v
Shell phân tích cú pháp, mở rộng và chuyển hướng
        |
        v
Một hoặc nhiều yêu cầu thực thi
        |
        v
Chương trình xử lý tham số, gọi tiến trình con hoặc API
        |
        v
Đọc, sửa hoặc tác động tài nguyên đích
```

Một bộ lọc chuỗi ở terminal chỉ quan sát tầng đầu tiên. Một bộ kiểm soát thực thi có thể quan sát chương trình và danh sách tham số. Kiểm soát truy cập tài nguyên mới quyết định tiến trình có được mở tệp, thay đổi dịch vụ hoặc gọi API quản trị hay không.

Các tầng này không tương đương:

| Đối tượng quan sát | Có thể biết | Không tự chứng minh được |
| --- | --- | --- |
| Ký tự hiển thị trong terminal | Nội dung được nhập hoặc hiển thị | Toàn bộ hành vi của tiến trình và tác vụ không có terminal |
| Yêu cầu thực thi có cấu trúc | Chương trình, tham số và ngữ cảnh có thu thập | Mọi tác động sau đó của chương trình được phép chạy |
| Sự kiện truy cập tài nguyên | Tệp hoặc đối tượng được truy cập theo nguồn log | Ý định ban đầu và toàn bộ chuỗi nhân quả nếu thiếu liên kết |
| Sự kiện PAM | Người yêu cầu, phiên, phê duyệt và tài khoản đích | Mọi hoạt động đi ngoài đường truy cập PAM |

### 3.2. Không đồng nhất tên chương trình với năng lực của nó

Chặn một tên chương trình chỉ chặn được hành vi mà quy tắc thực sự bao phủ. Một tiện ích khác, thư viện hoặc chương trình có sẵn có thể thực hiện cùng một tác động.

Ngược lại, cấm toàn bộ một công cụ phổ biến có thể chặn cả chẩn đoán hợp lệ. Ví dụ, một công cụ quản lý dịch vụ có cả thao tác xem trạng thái và thao tác thay đổi trạng thái. Chỉ nhìn tên công cụ không đủ để phân biệt chúng.

Vì vậy, quy tắc nên xuất phát từ tài sản và hành vi cần bảo vệ:

```text
Tài sản: cấu hình và trạng thái dịch vụ kiểm toán.
Hành vi bị cấm trong phiên chẩn đoán: dừng, vô hiệu hóa hoặc sửa cấu hình.
Chủ thể: người vận hành qua tài khoản hỗ trợ được PAM cấp.
Phạm vi: máy production thuộc nhóm ứng dụng orders.
Điểm cưỡng chế: bộ thực thi tác vụ được quản lý và quyền hệ điều hành.
```

Sau đó mới ánh xạ yêu cầu này sang những biểu diễn kỹ thuật mà từng điểm kiểm soát có thể quan sát.

## 4. Viết hợp đồng cho một quy tắc denylist

Một quy tắc vận hành được cần có nhiều hơn một biểu thức khớp:

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Định danh | Rule ID ổn định và phiên bản chính sách |
| Mục đích | Tài sản, rủi ro hoặc ranh giới đang bảo vệ |
| Chủ thể | Người dùng thực, vai trò, tài khoản đặc quyền hiệu lực |
| Phạm vi | Môi trường, nhóm máy, loại phiên và thời gian áp dụng |
| Dữ liệu khớp | Chuỗi terminal, executable, argv, tác vụ hay tài nguyên |
| Điều kiện | Những giá trị và quan hệ cần thỏa mãn |
| Hành động | Quan sát, từ chối, cảnh báo hoặc chuyển quy trình |
| Ưu tiên | Cách xử lý khi nhiều quy tắc cùng khớp |
| Ngoại lệ | Ai được duyệt, hiệu lực bao lâu, có được ngoại lệ hay không |
| Bằng chứng | Sự kiện quyết định, kết quả cưỡng chế và dữ liệu liên kết |

Tên quy tắc như `block-dangerous-command` quá mơ hồ. Tên như `deny-audit-service-change-in-support-session` giúp người vận hành hiểu mục tiêu, nhưng mô tả và điều kiện vẫn phải cụ thể.

Một điều kiện kết hợp có thể được diễn đạt như sau:

```text
environment = production
AND session_profile = support-diagnostics
AND executable_identity = managed-service-helper
AND action thuộc {stop, disable, reconfigure}
AND target_service thuộc protected_audit_services
THEN DENY
```

Đây là quy tắc trên các trường có cấu trúc, không phải cú pháp của một sản phẩm PAM cụ thể. Nếu điểm kiểm soát chỉ có chuỗi terminal, không được giả định nó đã biết đáng tin cậy các trường `action` và `target_service`.

### 4.1. Quy tắc phải có phạm vi

Cùng một thao tác có thể bị cấm trong phiên hỗ trợ, nhưng hợp lệ trong quy trình bảo trì được phê duyệt. Để thể hiện điều đó, cần ràng buộc theo loại tác vụ, tài sản đích và cửa sổ thay đổi.

Không nên biến một điều kiện cấm có phạm vi hẹp thành lệnh cấm toàn hệ thống chỉ vì tên công cụ giống nhau. Cũng không được để một quy tắc chỉ dành cho production bị áp dụng nhầm sang toàn bộ môi trường mà không đánh giá ảnh hưởng.

### 4.2. Thứ tự ưu tiên phải rõ ràng

Ví dụ một hợp đồng quyết định:

1. Xác minh quyền nền và ngữ cảnh phiên.
2. Áp dụng quy tắc cấm tuyệt đối trong phạm vi đang xét.
3. Xem xét ngoại lệ được ký duyệt cho các quy tắc cho phép ngoại lệ.
4. Áp dụng denylist còn lại.
5. Chuyển yêu cầu không khớp về cơ chế phân quyền gốc.

Một ngoại lệ không được tự tạo ra quyền nền. Nó cũng không được vượt qua quy tắc được khai báo là không cho ngoại lệ. Nếu tổ chức chọn thứ tự khác, phải mô tả và kiểm thử thứ tự đó trước khi sử dụng.

## 5. Khớp lệnh: từ chuỗi đến ngữ nghĩa

### 5.1. Vì sao tìm chuỗi con thường không đủ?

Giả sử hệ thống dùng điều kiện:

```text
Nếu dòng nhập chứa "stop" thì chặn.
```

Cách này có thể chặn một thông điệp vô hại:

```text
echo "không stop dịch vụ trong phiên này"
```

Đồng thời, nó không chứng minh rằng mọi cách làm dừng dịch vụ đã được bao phủ. Tác vụ có thể đi qua một chương trình khác, một API hoặc một tiến trình con.

Biểu thức chính quy có ích khi đối tượng thật sự là văn bản theo một định dạng đã biết. Nó không tự trở thành bộ phân tích ngữ nghĩa cho mọi shell, mọi ngôn ngữ script và mọi giao thức quản trị.

Nếu dùng regex, cần giới hạn kích thước đầu vào, kiểm soát độ phức tạp và thử với dữ liệu không khớp. Một quy tắc gây tiêu tốn quá nhiều tài nguyên có thể làm chậm hoặc gián đoạn chính luồng quản trị.

### 5.2. Ưu tiên đối sánh theo trường khi nguồn dữ liệu cho phép

Một yêu cầu có cấu trúc có thể trông như sau:

```json
{
  "sessionId": "pam-session-demo-031",
  "environment": "production",
  "sessionProfile": "support-diagnostics",
  "effectiveIdentity": "svc-support-orders",
  "executable": {
    "path": "/opt/pam-tools/service-helper",
    "identity": "managed-service-helper"
  },
  "argv": ["stop", "audit-demo"],
  "requestedAction": "stop",
  "targetService": "audit-demo"
}
```

`requestedAction` và `targetService` chỉ đáng tin nếu được tạo bởi bộ thực thi có hợp đồng đầu vào rõ ràng hoặc bộ phân tích phù hợp. Không lấy những nhãn do người yêu cầu tự gửi lên làm bằng chứng duy nhất.

Đối với chương trình có giao diện tham số đã biết, bộ phân tích cần xử lý:

- Ranh giới giữa các tham số, không chỉ khoảng trắng nhìn thấy.
- Cú pháp tùy chọn hợp lệ và các dạng viết tương đương được hỗ trợ.
- Những tham số kết thúc việc đọc tùy chọn.
- Đối số lặp lại, thứ tự và giá trị mặc định theo đúng giao diện công cụ.
- Cách xử lý đầu vào không hợp lệ hoặc chưa hỗ trợ.

Đừng tự tạo ra quy tắc “tham số thứ hai luôn là đối tượng đích” nếu chương trình cho phép tùy chọn xuất hiện trước nó.

### 5.3. Chuẩn hóa có giới hạn và có thể giải thích

Chuẩn hóa có ích khi nó giữ nguyên ý nghĩa trong ngữ cảnh đang xét. Chuẩn hóa quá mức có thể làm bộ kiểm soát quyết định trên một yêu cầu khác với yêu cầu thực thi.

Những sai lầm cần tránh:

- Chuyển mọi ký tự về chữ thường dù hệ thống đích phân biệt hoa thường.
- Xóa dấu nháy, dấu thoát hoặc khoảng trắng rồi đối sánh chuỗi đã mất cấu trúc.
- Giải mã nhiều lần mà không biết thành phần thực thi sẽ giải mã bao nhiêu lần.
- Gộp đường dẫn theo cách xử lý khác với hệ điều hành đích.
- Coi tên tệp hiển thị giống nhau là cùng một đối tượng thực thi.

Nên giữ các dạng biểu diễn tách biệt:

```text
original_input        = dữ liệu gốc theo nguồn thu thập
parsed_representation = cấu trúc do parser tương ứng tạo ra
policy_fields         = các trường đã xác minh dùng để ra quyết định
```

Mỗi quyết định cần biết parser nào, phiên bản nào và trường nào đã dẫn đến kết quả. Dữ liệu gốc có thể chứa bí mật; việc giữ nó phải đi kèm kiểm soát truy cập, thời hạn lưu và cơ chế bảo vệ phù hợp.

### 5.4. Đường dẫn thực thi và ranh giới kiểm tra

Tên gọi ngắn của chương trình chưa xác định chắc chắn tệp nào sẽ chạy. Đường tìm kiếm chương trình, liên kết tệp, bản cập nhật và quyền ghi vào thư mục đều ảnh hưởng kết quả.

Nếu quy tắc tin cậy một executable cụ thể, cần xác minh danh tính thực thi tại điểm cưỡng chế, bảo vệ nơi chứa nó và tránh khoảng hở giữa lúc kiểm tra với lúc sử dụng. Kiểm tra một đường dẫn từ xa rồi cho một tiến trình khác tự phân giải lại đường dẫn không tạo ra cùng mức bảo đảm.

Ngay cả hash của tệp thực thi cũng chưa mô tả toàn bộ hành vi: chương trình có thể nạp cấu hình, thư viện, plugin hoặc chạy nội dung do người dùng cung cấp. Quy tắc phải phản ánh những phụ thuộc mà mô hình thực thi cho phép.

## 6. Những cấu trúc lệnh cần được xử lý đúng

### 6.1. Nhiều lệnh trong một yêu cầu

Một dòng có thể chứa nhiều công đoạn:

```text
Lệnh A  ->  Lệnh B  ->  Lệnh C
```

Với dữ liệu terminal, dấu nối lệnh, pipeline và chuyển hướng có thể tạo ra hành vi ngoài chương trình đầu tiên được nhìn thấy. Với dữ liệu exec, mỗi chương trình đã chạy chỉ là một phần của chuỗi.

Nếu điểm cưỡng chế có thể phân tích và kiểm soát toàn bộ kế hoạch trước thực thi, nó có thể từ chối cả yêu cầu trước khi có tác động. Nếu hệ thống chỉ kiểm tra từng lần thực thi, công đoạn đầu có thể đã chạy trước khi công đoạn sau bị chặn. Báo cáo phải thể hiện giới hạn này.

Chuyển hướng của shell cũng không nhất thiết xuất hiện như một tham số của chương trình con. Quy tắc chỉ nhìn `argv` của chương trình không tự biết toàn bộ tệp đích mà shell mở.

### 6.2. Shell và interpreter

Khi một shell hoặc interpreter được phép thực thi nội dung tùy ý với quyền cao, cấm tên một vài công cụ thường không đủ để hạn chế năng lực của phiên.

Bộ kiểm soát cần biết nó có đang cho phép:

- Thực thi chuỗi lệnh do người dùng cung cấp.
- Chạy một tệp script có nội dung thay đổi được.
- Nạp mã hoặc plugin từ nơi người dùng ghi được.
- Mở chức năng chạy lệnh từ một chương trình tương tác.

Phương án cho tác vụ hẹp là cung cấp thao tác có đầu vào kiểm tra được, thay vì một bộ thông dịch có quyền rộng. Nếu nghiệp vụ thật sự cần shell đầy đủ, phải ghi nhận đó là ranh giới còn mở và bổ sung kiểm soát tài nguyên, giám sát phiên, thời hạn quyền cùng khả năng thu hồi.

### 6.3. Wrapper và công cụ trung gian

Một chương trình được phép chạy có thể gọi một chương trình khác. Cấm chỉ tiến trình ngoài cùng sẽ bỏ sót tác động của tiến trình con; chỉ nhìn tên tiến trình con lại có thể mất mục đích nghiệp vụ và người khởi tạo.

Cần liên kết được:

```text
Người dùng thực
  -> phiên PAM
    -> tài khoản đặc quyền hiệu lực
      -> tác vụ được cấp
        -> tiến trình cha
          -> tiến trình con
            -> tài nguyên đích
```

Khả năng giữ liên kết phụ thuộc nguồn dữ liệu và nền tảng. Không được coi một PID đơn lẻ là định danh vĩnh viễn, vì PID có thể được sử dụng lại.

### 6.4. Lệnh nội bộ và hành vi không qua exec

Một số thao tác được thực hiện ngay trong shell hoặc trong tiến trình đã chạy. Chúng có thể không tạo ra một lần thực thi chương trình mới.

Do đó, quan sát các sự kiện tạo tiến trình không đồng nghĩa quan sát toàn bộ truy cập tài nguyên. Một editor đang chạy có quyền ghi tệp nhạy cảm vẫn cần được giới hạn bằng quyền tài nguyên phù hợp, dù không xuất hiện thêm một tên lệnh bị cấm.

## 7. Chọn điểm cưỡng chế và chứng minh độ phủ

### 7.1. Proxy hoặc cổng phiên

Cổng phiên có lợi thế gắn hành động với danh tính, phê duyệt và bản ghi PAM. Tuy nhiên, khả năng cưỡng chế phụ thuộc giao thức và thiết kế:

- Có nhìn thấy dữ liệu trước khi chuyển tới máy đích không?
- Có hiểu đúng cú pháp của yêu cầu không?
- Có kiểm soát phiên không tương tác, truyền tệp hoặc đường quản trị khác không?
- Người dùng có thể truy cập trực tiếp máy đích ngoài cổng không?

Một proxy ghi lại màn hình không tự trở thành một bộ phân quyền lệnh. Với giao thức chỉ mang luồng terminal, nội dung hiển thị chưa chắc phản ánh đầy đủ yêu cầu có cấu trúc mà máy đích thực hiện.

### 7.2. Kiểm soát trên máy đích

Điểm kiểm soát trên máy đích có thể tiếp cận danh tính thực thi, tiến trình và tài nguyên gần nơi tác động hơn. Cần xác định nó là cơ chế cưỡng chế trước hành động hay chỉ là cảm biến phát hiện sau hành động.

Nếu tài khoản được cấp có thể tắt, sửa hoặc bỏ qua điểm kiểm soát đó, mức bảo đảm của denylist bị giới hạn. Cần bảo vệ cấu hình, kênh cập nhật chính sách và thành phần giám sát bằng quyền quản trị thích hợp.

### 7.3. Bộ thực thi tác vụ giới hạn

Với một bộ thao tác như xem trạng thái, xem log đã lọc và khởi động lại một ứng dụng cụ thể, có thể thiết kế một bộ thực thi nhận yêu cầu có cấu trúc. Bộ thực thi xác minh quyền và chỉ ánh xạ sang các hành động đã định nghĩa.

Đây là nơi denylist có thể làm lớp bảo vệ bổ sung: ngay cả tác vụ thuộc danh mục đã được cấp cũng bị từ chối nếu chạm vào tài sản đang được bảo vệ hoặc nằm ngoài cửa sổ thay đổi.

| Điểm kiểm soát | Điều kiện để tin cậy quyết định chặn | Giới hạn cần công bố |
| --- | --- | --- |
| Bộ lọc đầu vào terminal | Quan sát đúng luồng, parser phù hợp và từ chối trước khi gửi | Khó bao phủ mọi cú pháp, chương trình tương tác và đường truy cập khác |
| Cơ chế cưỡng chế thực thi trên đích | Không thể bị chủ thể đang kiểm soát bỏ qua trong phạm vi đã công bố | Kiểm soát exec không đồng nghĩa kiểm soát mọi thao tác tài nguyên |
| Bộ thực thi tác vụ quản lý | Tập hành động cố định, đầu vào được kiểm tra, quyền nền hẹp | Chỉ bao phủ tác vụ đi qua nó |
| Bộ phân tích log | Dữ liệu đủ, thời gian và định danh liên kết được | Phát hiện sau sự kiện không ngăn tác động ban đầu |

Độ phủ nên được lập thành danh mục các đường truy cập thực tế, bao gồm con người và tài khoản dịch vụ. Một dashboard báo không có lệnh vi phạm không chứng minh an toàn nếu một phần hoạt động chưa được thu thập.

## 8. Ví dụ chính sách minh họa

Giả sử tổ chức có tiện ích nội bộ `service-helper` cho các thao tác trên dịch vụ. Phiên `support-diagnostics` chỉ phục vụ chẩn đoán. Dịch vụ `audit-demo` được bảo vệ.

Đoạn YAML dưới đây mô tả ý tưởng chính sách, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm:

```yaml
policyId: pam-command-guard
version: "demo-03"
scope:
  environment: production
  sessionProfile: support-diagnostics

inputContract:
  source: managed-task-executor
  parser: service-helper-contract-v1

rules:
  - id: deny-protected-audit-change
    mode: ENFORCE
    match:
      executableIdentity: managed-service-helper
      actionIn:
        - stop
        - disable
        - reconfigure
      targetServiceIn:
        - audit-demo
    effect: DENY
    exceptionAllowed: false
    reasonCode: PROTECTED_AUDIT_SERVICE

  - id: deny-application-restart-in-diagnostics
    mode: ENFORCE
    match:
      executableIdentity: managed-service-helper
      actionIn:
        - restart
      targetServiceIn:
        - orders-demo
    effect: DENY
    exceptionAllowed: true
    reasonCode: CHANGE_REQUIRES_APPROVAL

noMatch: DEFER_TO_BASE_AUTHORIZATION
unsupportedInput: DENY_IN_THIS_TASK_EXECUTOR
```

Các điểm cần chú ý:

- `scope` chỉ ra phạm vi. Chính sách này không tự cấp quyền trên các môi trường khác.
- `inputContract` yêu cầu nguồn hiểu chính xác cấu trúc thao tác.
- Quy tắc bảo vệ kiểm toán không cho ngoại lệ trong hợp đồng ví dụ.
- Ngoại lệ khởi động lại ứng dụng chỉ có ý nghĩa khi đã tồn tại quyền và quy trình thay đổi phù hợp.
- `noMatch` không có nghĩa cấp quyền toàn cục.
- `unsupportedInput` là quyết định cho bộ thực thi hẹp này, không phải mặc định bắt buộc cho mọi hệ thống PAM.

Nếu triển khai thực tế chỉ có văn bản terminal, phải thiết kế lại hợp đồng đầu vào và công bố mức bảo đảm tương ứng. Không thể gắn nhãn trường có cấu trúc vào văn bản rồi coi chúng đã được xác minh.

## 9. Luồng quyết định trước thực thi

Một luồng minh họa cho bộ thực thi tác vụ có thể viết dưới dạng giả mã:

```text
evaluate(request, context):
    verify_context_is_authentic_and_current(context)

    if not base_authorization_allows(request, context):
        return DENY("BASE_AUTHORIZATION_FAILED")

    policy = load_verified_policy_for(context)

    if policy is unavailable:
        return handle_policy_unavailable(context)

    parsed = parse_with_declared_contract(request)

    if parsed is unsupported:
        return policy.unsupported_input_decision

    matches = find_matching_rules(parsed, context, policy)

    if matches contains a non_exceptionable_enforced_deny:
        return DENY(rule_id, policy.version)

    for rule in matches:
        if rule.mode == OBSERVE:
            record_observation(rule, context)
            continue

        if rule.effect == DENY:
            exception = find_valid_scoped_exception(rule, parsed, context)
            if exception is absent:
                return DENY(rule.id, policy.version)

    return DEFER_TO_BASE_AUTHORIZATION
```

Giả mã chỉ minh họa quyết định. Để trở thành điểm cưỡng chế, nó còn cần một hợp đồng giữa kiểm tra và thực thi:

1. Quyết định gắn với đúng yêu cầu đã được kiểm tra.
2. Danh tính phiên, tài sản và quyền chưa hết hiệu lực tại thời điểm thực thi.
3. Tham số hoặc chương trình không bị thay thế sau khi kiểm tra.
4. Điểm thực thi tiếp nhận quyết định và thực sự từ chối khi cần.
5. Kết quả cưỡng chế được ghi nhận, kể cả khi điểm thực thi gặp lỗi.

Không cho yêu cầu tự đổi đường dẫn hoặc đối số sau khi nhận quyết định cho phép. Nếu điều đó xảy ra, cần đánh giá lại yêu cầu mới.

### 9.1. Khi parser không hiểu đầu vào

Không được tự diễn giải “không phân tích được” thành “không có lệnh nguy hiểm”. Đây là hai trạng thái khác nhau.

Với bộ thực thi tác vụ hẹp, từ chối đầu vào ngoài hợp đồng thường tạo ra ranh giới rõ ràng. Với phiên quản trị tổng quát, tổ chức phải xác định cách giảm quyền, yêu cầu giám sát bổ sung hoặc chuyển sang quy trình khác. Dù chọn cách nào, cần có quyết định rõ ràng và kiểm thử sự cố tương ứng.

### 9.2. Khi dịch vụ chính sách hoặc kênh log lỗi

Cần tách hai tình huống:

- Không thể đưa ra quyết định phân quyền đáng tin cậy.
- Đã có quyết định phân quyền nhưng kênh ghi bằng chứng bị gián đoạn.

Chính sách vận hành có thể khác nhau cho từng loại tài sản. Không nên để một lỗi ghi log âm thầm biến tất cả deny thành allow. Ngược lại, nếu việc từ chối mọi tác vụ có thể gây gián đoạn nghiêm trọng, phải chuẩn bị quy trình phục hồi và quyền khẩn cấp đã được kiểm thử trước.

Bản chính sách lưu cục bộ chỉ là phương án hợp lệ khi đã được xác minh, còn hiệu lực và hợp đồng cho phép sử dụng trong trạng thái đó.

## 10. Ngoại lệ, JIT và break-glass

Ngoại lệ của denylist là quyền vượt qua một quy tắc xác định trong điều kiện xác định. Nó cần hẹp hơn một “công tắc bỏ lọc”.

Một ngoại lệ minh họa:

```text
Rule: deny-application-restart-in-diagnostics
Người được cấp: kỹ sư đang xử lý sự cố INC-DEMO-018
Tài khoản đích: svc-support-orders
Tài sản: orders-prod-demo-02
Tác vụ: restart orders-demo qua managed-task-executor
Thời hạn: 15 phút, không gia hạn ngầm
Phê duyệt: người có thẩm quyền theo quy trình thay đổi
Giới hạn: không áp dụng cho protected audit service
```

Ngoại lệ phải được kiểm tra tại thời điểm dùng, bao gồm trạng thái thu hồi. Việc thấy một mã ticket trong chuỗi lệnh không chứng minh ticket đó hợp lệ hoặc cho phép đúng hành động.

JIT giới hạn thời gian quyền tồn tại; denylist giới hạn một số hành động trong thời gian đó. Hai cơ chế bổ sung nhau. Hết thời hạn hoặc bị thu hồi cần được xử lý ở hệ thống cấp quyền và phiên theo thiết kế; chỉ đổi trạng thái ngoại lệ trong dashboard chưa bảo đảm tiến trình đang chạy đã mất quyền.

Break-glass nên là một luồng có danh tính riêng, điều kiện kích hoạt, thời hạn, người giám sát và đối soát sau sử dụng. Không coi break-glass là lý do để âm thầm xóa quy tắc, tắt audit hoặc dùng chung một tài khoản không quy trách nhiệm được.

## 11. Kiểm thử chính sách bằng các tình huống có ý nghĩa

Kiểm thử phải xác minh cả quyết định và tác động tại điểm cưỡng chế. Với các hành động có thể gây ảnh hưởng, dùng môi trường thử nghiệm và đối tượng giả lập.

### 11.1. Ma trận quyết định

| Tình huống | Kết quả mong đợi trong ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Xem trạng thái `orders-demo`, quyền nền hợp lệ | Chuyển về quyền nền và được thực thi nếu quyền nền cho phép | Denylist không chặn tác vụ chẩn đoán hợp lệ |
| Dừng `audit-demo` trong phiên hỗ trợ | DENY | Tiện ích chưa được thực thi tác vụ dừng |
| Khởi động lại `orders-demo` khi chưa có ngoại lệ | DENY | Có đúng rule ID và lý do |
| Khởi động lại đúng ứng dụng với ngoại lệ còn hiệu lực | Chuyển về quyền nền | Ngoại lệ đúng người, máy, tác vụ và thời hạn |
| Dùng ngoại lệ khởi động lại cho `audit-demo` | DENY | Ngoại lệ không vượt quy tắc cấm tuyệt đối |
| Ngoại lệ đã hết hạn hoặc bị thu hồi | DENY với hành động bị quy tắc cấm | Kiểm tra tại thời điểm sử dụng |
| Yêu cầu ngoài hợp đồng parser | DENY trong bộ thực thi hẹp | Không coi parse lỗi là không khớp |
| Dòng văn bản chỉ nhắc đến từ “stop” | Không kết luận vi phạm chỉ từ từ khóa | Không tạo false positive do tìm chuỗi con |

Quyết định cuối cùng cho yêu cầu không bị deny vẫn phải tuân theo quyền nền. Một trường hợp “không khớp denylist” không đủ để kiểm thử quyền thành công.

### 11.2. Kiểm thử biểu diễn tương đương

Với một giao diện tham số được hỗ trợ, chuẩn bị nhiều cách viết có cùng ý nghĩa theo đúng hợp đồng của công cụ. Kiểm tra chúng dẫn đến cùng quyết định.

Nhóm kiểm thử cần có:

- Khoảng trắng, dấu nháy và ký tự Unicode liên quan đến đầu vào được hỗ trợ.
- Các dạng tùy chọn và thứ tự đối số hợp lệ.
- Tên chương trình ngắn so với danh tính chương trình đã được phân giải.
- Chuỗi lệnh có nhiều công đoạn và chuyển hướng nếu điểm kiểm soát tuyên bố hỗ trợ.
- Yêu cầu qua wrapper, tiến trình con và phiên không tương tác.
- Tệp script hoặc chương trình thay đổi sau lần kiểm tra.
- Dữ liệu quá dài hoặc parser không xử lý được.
- Thay đổi phạm vi máy đích, tài khoản hoặc thời hạn giữa kiểm tra và thực thi.

Mục tiêu là xác minh ranh giới đã công bố, không khẳng định một tập test hữu hạn chứng minh bao phủ mọi chương trình.

### 11.3. Kiểm thử lỗi và khôi phục

Cần thử riêng khi:

- Không tải được chính sách mới.
- Bản chính sách không hợp lệ hoặc hết thời hạn cho phép sử dụng.
- Điểm thực thi và bộ đánh giá mất kết nối.
- Đồng hồ giữa các thành phần lệch ngoài mức chấp nhận.
- Hàng đợi bằng chứng bị đầy.
- Người vận hành khôi phục về phiên bản chính sách trước.

Kết quả mong đợi phải được định nghĩa trước cho từng trường hợp. Một hệ thống chạy tốt khi mọi thành phần sẵn sàng chưa chứng minh được hành vi an toàn khi có sự cố.

## 12. Log quyết định và bằng chứng kiểm toán

Một bản ghi deny hữu ích cần trả lời được: ai yêu cầu, dùng quyền nào, trên đâu, yêu cầu gì, quy tắc nào quyết định và điều gì thực sự xảy ra.

Ví dụ sự kiện đã hạn chế dữ liệu nhạy cảm:

```json
{
  "eventType": "pam.command.decision",
  "requestId": "req-demo-073",
  "sessionId": "pam-session-demo-031",
  "actorId": "user-demo-17",
  "effectiveAccount": "svc-support-orders",
  "assetId": "orders-prod-demo-02",
  "sessionProfile": "support-diagnostics",
  "policyId": "pam-command-guard",
  "policyVersion": "demo-03",
  "ruleId": "deny-protected-audit-change",
  "mode": "ENFORCE",
  "decision": "DENY",
  "reasonCode": "PROTECTED_AUDIT_SERVICE",
  "parserId": "service-helper-contract-v1",
  "executionState": "REJECTED_BEFORE_DISPATCH",
  "argumentsView": ["stop", "audit-demo"]
}
```

Trong hệ thống thực, thời gian, nguồn sự kiện và định danh điểm cưỡng chế cũng cần có trong schema. Nên liên kết sự kiện đánh giá với xác nhận từ điểm thực thi bằng request ID. Nếu không có xác nhận, ghi rõ trạng thái chưa xác định thay vì tự kết luận đã chặn.

Nếu một cảm biến chỉ thấy hành vi sau thực thi, sự kiện nên thể hiện điều đó:

```text
mode = DETECT
executionState = OBSERVED_AFTER_EXECUTION
response = ALERTED
```

Không được đổi nhãn thành `REJECTED_BEFORE_DISPATCH` chỉ vì hệ thống đã gửi cảnh báo hoặc đóng phiên sau đó.

### 12.1. Giữ bằng chứng mà không làm lộ bí mật

Đối số và nội dung terminal có thể chứa credential, token, đường dẫn nhạy cảm hoặc dữ liệu nghiệp vụ. Thiết kế log cần phân biệt:

- Bản ghi quyết định dùng cho vận hành thường ngày.
- Dữ liệu đầy đủ chỉ dành cho điều tra khi có thẩm quyền.
- Dấu vết truy cập chính dữ liệu điều tra đó.

Có thể lưu bản xem đã che bí mật cùng tham chiếu đến bằng chứng được bảo vệ. Hàm băm giúp kiểm tra tính toàn vẹn theo cơ chế sử dụng, nhưng không thay thế nội dung cần điều tra và không bảo vệ đầy đủ một bí mật dễ đoán chỉ bằng việc băm.

Thời hạn lưu, quyền truy cập và cơ chế bảo vệ cần thống nhất với bản ghi phiên PAM. Nếu bản ghi quyết định còn nhưng liên kết phiên đã mất, khả năng quy trách nhiệm sẽ giảm.

## 13. Đưa denylist vào vận hành

### 13.1. Bắt đầu từ ranh giới có giá trị cao

Ưu tiên một số hành vi mà tổ chức xác định rõ là không được có trong loại phiên đang xét, chẳng hạn thay đổi cơ chế kiểm toán, sửa cấu hình PAM hoặc thực hiện thay đổi dịch vụ ngoài mục đích chẩn đoán.

Mỗi quy tắc cần có chủ sở hữu nghiệp vụ và chủ sở hữu kỹ thuật. Nếu không xác định được ai quyết định một trường hợp là hợp lệ, quy tắc dễ tích lũy ngoại lệ không kiểm soát.

### 13.2. Quan sát trước khi cưỡng chế theo phạm vi

Một lộ trình triển khai phù hợp có thể là:

1. Thu thập dữ liệu trong phạm vi đã được phê duyệt.
2. Chạy quy tắc ở chế độ quan sát và đối chiếu với tác vụ thực tế.
3. Sửa các điều kiện mơ hồ hoặc thiếu dữ liệu.
4. Cưỡng chế trên nhóm tài sản thử nghiệm.
5. Mở rộng theo từng phạm vi sau khi có bằng chứng vận hành.
6. Duy trì kiểm thử hồi quy khi đổi công cụ, parser hoặc chính sách.

Quan sát giúp đo ảnh hưởng, nhưng không chứng minh khả năng chặn. Trước khi mở rộng, vẫn phải thử cơ chế từ chối tại điểm thực thi.

### 13.3. Chỉ số nên theo dõi

| Chỉ số | Câu hỏi nó giúp trả lời |
| --- | --- |
| Tỷ lệ hành động hợp lệ bị chặn sau xác minh | Quy tắc có gây cản trở nghiệp vụ không? |
| Số tác vụ bị chặn với xác nhận cưỡng chế | Có bao nhiêu yêu cầu thực sự bị ngăn tại điểm đã công bố? |
| Tỷ lệ đầu vào không phân tích được | Hợp đồng parser có còn phù hợp với cách dùng không? |
| Độ phủ phiên và đường truy cập được quản lý | Còn hoạt động nào ngoài phạm vi quan sát hoặc cưỡng chế? |
| Độ trễ quyết định theo phân vị | Điểm kiểm soát có đáp ứng luồng quản trị không? |
| Ngoại lệ đang mở, hết hạn và bị thu hồi | Quyền vượt quy tắc có được quản lý đúng vòng đời không? |
| Sự kiện thiếu liên kết quyết định với thực thi | Bằng chứng có đủ để kết luận kết quả không? |

Tỷ lệ false positive phải dùng các trường hợp đã được phân loại, không lấy mọi lệnh bị chặn làm lỗi. Tương tự, không thể suy ra false negative bằng cách chỉ đếm số cảnh báo: cần kiểm thử có kiểm soát, đối chiếu điều tra và nguồn dữ liệu độc lập phù hợp.

### 13.4. Thay đổi chính sách như thay đổi kiểm soát truy cập

Một thay đổi denylist có thể làm gián đoạn hoạt động hoặc mở rộng năng lực của phiên. Vì vậy, cần quản lý phiên bản, review, bằng chứng kiểm thử, phạm vi phát hành và phương án khôi phục.

Khôi phục phiên bản cũ cũng cần xác minh rằng bản cũ vẫn phù hợp với chương trình và môi trường hiện tại. Không coi thao tác rollback thành công về mặt kỹ thuật là bằng chứng chính sách cũ an toàn về mặt nghiệp vụ.

## 14. Tình huống thực hành: chẩn đoán ứng dụng production

### Bối cảnh

Nhóm hỗ trợ được cấp tài khoản qua PAM để chẩn đoán ứng dụng `orders-demo`. Tổ chức muốn bảo vệ `audit-demo` và không cho tự thay đổi trạng thái ứng dụng trong phiên chẩn đoán.

Môi trường thử nghiệm cung cấp một bộ thực thi tác vụ giả lập. Nó nhận hành động và tên dịch vụ dưới dạng dữ liệu có cấu trúc, ghi nhận yêu cầu, nhưng không điều khiển dịch vụ production thật.

### Bước 1: Xác định ranh giới

Ghi lại:

```text
Ai: người dùng hỗ trợ đã xác thực, gắn với phiên PAM.
Quyền nền: các thao tác chẩn đoán đã được cấp.
Tài sản: nhóm máy ứng dụng được chọn.
Cấm: thay đổi audit-demo.
Có điều kiện: restart orders-demo phải có phê duyệt riêng.
Ngoài phạm vi: mọi đường truy cập không đi qua bộ thực thi giả lập.
```

Dòng “ngoài phạm vi” là khoảng trống cần được quản lý khi thiết kế hệ thống thật, không phải sự chấp thuận cho phép bỏ qua kiểm soát.

### Bước 2: Mô phỏng quyết định

Gửi lần lượt các yêu cầu vào bộ mô phỏng:

```text
status orders-demo
stop audit-demo
restart orders-demo
```

Kết quả kỳ vọng:

- `status orders-demo` không khớp denylist; quyền nền quyết định việc thực hiện.
- `stop audit-demo` bị từ chối trước khi dispatch.
- `restart orders-demo` bị từ chối khi chưa có ngoại lệ phù hợp.

Không cần chạy lệnh thay đổi dịch vụ thật để chứng minh logic chính sách.

### Bước 3: Thử ngoại lệ hẹp

Tạo dữ liệu ngoại lệ cho đúng người, máy và thao tác `restart orders-demo`, còn hiệu lực trong khoảng thử nghiệm. Xác minh yêu cầu khởi động lại chỉ đi tiếp nếu quyền nền cũng cho phép.

Sau đó thay đổi từng yếu tố: máy đích, người dùng, trạng thái thu hồi và thời hạn. Yêu cầu bị quy tắc cấm phải quay lại kết quả từ chối nếu ngoại lệ không còn khớp.

Yêu cầu thay đổi `audit-demo` vẫn bị cấm theo quy tắc không cho ngoại lệ.

### Bước 4: Đối chiếu bằng chứng

Với từng yêu cầu, kiểm tra có:

1. Request ID và session ID.
2. Phiên bản chính sách cùng rule ID khi khớp.
3. Kết quả phân quyền nền.
4. Quyết định denylist.
5. Xác nhận từ bộ thực thi là bị từ chối hay đã tiếp nhận.
6. Bản xem dữ liệu không làm lộ bí mật.

Nếu chỉ có dòng “rule matched”, bài thực hành chưa chứng minh được yêu cầu đã bị chặn trước thực thi.

### Bước 5: Đánh giá giới hạn

Trả lời các câu hỏi:

- Nếu người dùng có shell root ngoài bộ thực thi, chính sách này còn bảo đảm điều gì?
- Nếu một chương trình được phép tự sửa tài nguyên được bảo vệ, kiểm soát nào chịu trách nhiệm?
- Nếu parser không hiểu yêu cầu, hệ thống hành xử ra sao?
- Nếu bộ ghi log lỗi nhưng bộ cưỡng chế còn hoạt động, quyết định có đổi không?
- Khi hết quyền JIT, thành phần nào ngăn tác vụ mới và xử lý phiên còn tồn tại?

Kết quả thực hành cần chỉ ra cả những gì đã kiểm chứng và phần nằm ngoài phạm vi.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa trọng tâm |
| --- | --- | --- |
| Danh sách chỉ gồm vài tên chương trình | Không phản ánh tác động cần bảo vệ | Xuất phát từ tài sản, hành vi và điểm cưỡng chế |
| Dùng chuỗi con cho mọi loại đầu vào | Chặn sai và bỏ sót cấu trúc | Dùng parser hoặc hợp đồng tác vụ thích hợp |
| Chỉ kiểm tra chương trình ngoài cùng | Bỏ qua tiến trình con và tác động bên trong | Giới hạn năng lực và liên kết chuỗi thực thi |
| Cho phép interpreter quyền rộng nhưng kỳ vọng denylist hẹp là đủ | Năng lực thật vượt mô hình kiểm soát | Giảm quyền nền hoặc chuyển sang tác vụ có cấu trúc |
| Coi “không khớp” là “được cấp quyền” | Vượt qua kiểm tra phân quyền nền | Giữ quyết định quyền nền độc lập và bắt buộc |
| Coi cảnh báo sau thực thi là chặn | Báo cáo sai hiệu quả kiểm soát | Ghi rõ thời điểm quan sát và xác nhận cưỡng chế |
| Tạo ngoại lệ toàn phiên không thời hạn | Mở rộng quyền khó thu hồi | Ràng buộc ngoại lệ theo rule, chủ thể, đích và thời gian |
| Log nguyên văn mọi tham số | Có thể lộ bí mật trong hệ thống giám sát | Phân tách bản xem và bằng chứng được bảo vệ |
| Chỉ thử trường hợp khớp đơn giản | Không phát hiện khoảng trống parser và sự cố | Thử biểu diễn tương đương, chuỗi tác vụ và lỗi thành phần |
| Bỏ qua đường truy cập ngoài PAM | Dashboard tạo cảm giác bao phủ sai | Kiểm kê và quản lý các đường truy cập thực tế |

## 16. Câu hỏi tự kiểm tra

1. Một hệ thống nhìn thấy lệnh nguy hiểm trong session recording rồi đóng phiên có thể khẳng định đã ngăn lệnh đó không? Cần thêm bằng chứng gì?
2. Vì sao tên executable và danh sách tham số vẫn chưa mô tả toàn bộ tác động của một chương trình?
3. Một yêu cầu không khớp denylist nhưng không có quyền nền phải nhận kết quả nào?
4. Những trường nào làm một ngoại lệ chỉ áp dụng đúng người, đúng tác vụ và đúng thời hạn?
5. Nếu điểm kiểm soát không hỗ trợ cú pháp đầu vào, vì sao không được coi đó là trường hợp không khớp?
6. Quy tắc chặn thao tác dịch vụ cần thay đổi thế nào khi nguồn dữ liệu chỉ là terminal text?
7. Làm sao phân biệt số yêu cầu khớp quy tắc với số yêu cầu thực sự bị chặn?
8. Khi nào nên thay một phiên quản trị linh hoạt bằng bộ thao tác giới hạn?

Một thiết kế command denylist có thể kiểm chứng phải gắn yêu cầu cấm với ngữ cảnh quyền, dữ liệu đáng tin, điểm cưỡng chế và bằng chứng thực thi. Mức bảo đảm của nó chỉ nằm trong những đường truy cập và năng lực đã được kiểm soát; phần còn lại cần được xử lý bằng least privilege, JIT/JEA, kiểm soát tài nguyên và giám sát phù hợp.
