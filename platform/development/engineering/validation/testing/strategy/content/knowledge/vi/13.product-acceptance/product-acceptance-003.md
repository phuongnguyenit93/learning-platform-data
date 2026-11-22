# Liên kết ví dụ nghiệp vụ với hành vi có thể quan sát

Trong module VALIDATION_TESTING_STRATEGY, việc chấp nhận sản phẩm cần dựa trên bằng chứng cho thấy sản phẩm giải quyết đúng công việc nghiệp vụ. Một yêu cầu như “khách hàng có thể đặt lịch” hoặc “nhân viên có thể hoàn tiền” thường chưa đủ để xác định chính xác hệ thống phải làm gì trong từng tình huống. Những ví dụ cụ thể từ hoạt động thực tế giúp các bên hiểu cùng một quy tắc, nhận ra ngoại lệ và chuyển kỳ vọng thành hành vi có thể kiểm tra.

**Ví dụ nghiệp vụ** mô tả một tình huống có ý nghĩa trong công việc của người dùng hoặc tổ chức. **Hành vi có thể quan sát** là kết quả mà người dùng, hệ thống liên quan hoặc người kiểm thử có thể nhận biết và xác minh khi tình huống đó xảy ra. Liên kết hai yếu tố này giúp nhóm tránh kiểm thử theo suy đoán hoặc chỉ xác nhận một thao tác giao diện mà không biết kết quả nghiệp vụ đã đạt hay chưa.

Bài học này trình bày cách thu thập ví dụ nghiệp vụ, tìm quy tắc nằm sau ví dụ, chuyển chúng thành kịch bản có điều kiện và kết quả rõ ràng, chọn bằng chứng quan sát phù hợp và duy trì liên kết giữa ví dụ, tiêu chí chấp nhận và kiểm thử. Mục tiêu là để mỗi kết luận chấp nhận sản phẩm có thể giải thích được bằng một tình huống thực tế và bằng chứng cụ thể.

## 1. Vì sao ví dụ nghiệp vụ cần được liên kết với hành vi quan sát được?

### 1.1. Yêu cầu chung thường che giấu nhiều cách hiểu

Một câu yêu cầu ngắn có thể được hiểu khác nhau bởi người dùng, chuyên gia nghiệp vụ, nhà phát triển và người kiểm thử.

Ví dụ: “Khách hàng có thể hủy lịch hẹn.”

Câu này chưa cho biết:

- Khách có thể hủy trước thời điểm hẹn bao lâu?
- Có được hủy khi nhân viên đã bắt đầu phục vụ không?
- Khi hủy, chỗ trống có được mở lại ngay không?
- Có cần gửi thông báo cho nhân viên hoặc khách hàng không?
- Nếu lịch đã thanh toán trước, tiền được hoàn tự động hay cần xử lý riêng?
- Hai yêu cầu hủy đồng thời được giải quyết thế nào?

Nếu mỗi người tự điền phần còn thiếu theo kinh nghiệm, sản phẩm có thể được triển khai theo một cách và kiểm thử theo cách khác. Một ví dụ thực tế giúp làm rõ điều kiện và hậu quả: “Khách hủy lịch trước giờ hẹn 24 giờ; lịch được chuyển sang trạng thái đã hủy, chỗ được mở lại và khách nhận xác nhận hủy.”

Tình huống cụ thể chưa tự động trở thành đặc tả đầy đủ, nhưng nó tạo điểm bắt đầu để hỏi đúng câu hỏi và thống nhất hành vi.

### 1.2. Từ ví dụ đến bằng chứng chấp nhận

Chuỗi liên kết cơ bản:

~~~text
Mục tiêu nghiệp vụ
    -> Ví dụ thực tế
        -> Quy tắc nghiệp vụ
            -> Hành vi mong đợi
                -> Bằng chứng quan sát
                    -> Kết luận chấp nhận
~~~

Ví dụ:

- Mục tiêu: khách có thể hủy lịch khi chính sách cho phép.
- Ví dụ: khách hủy trước giờ hẹn 24 giờ.
- Quy tắc: chỉ lịch chưa bắt đầu và còn trong thời hạn được phép hủy mới được hủy trực tuyến.
- Hành vi mong đợi: lịch chuyển sang trạng thái đã hủy; chỗ được giải phóng; thông báo được gửi.
- Bằng chứng: trạng thái lịch, số chỗ khả dụng và bản ghi gửi thông báo.
- Kết luận: tình huống đáp ứng chính sách nếu cả các kết quả cần thiết đều được xác nhận.

Nếu chỉ quan sát thấy nút Hủy biến mất, nhóm chưa có bằng chứng rằng lịch đã được hủy đúng, chỗ đã được giải phóng hoặc thông báo đã được gửi.

### 1.3. Ví dụ nghiệp vụ không chỉ là dữ liệu mẫu

Một ví dụ nghiệp vụ có giá trị thường mô tả cả bối cảnh, tác nhân, điều kiện, hành động và hậu quả. Chẳng hạn, “đơn hàng trị giá 500.000” chỉ là dữ liệu. “Khách đã thanh toán 500.000, sau đó hủy một mặt hàng trị giá 100.000 trước khi giao; hệ thống phải hoàn đúng số tiền đủ điều kiện và cập nhật tổng đơn” là một tình huống có thể dùng để khám phá quy tắc và thiết kế kiểm thử.

Dữ liệu mẫu chỉ trở thành ví dụ hữu ích khi nó minh họa một quy tắc hoặc một quyết định nghiệp vụ.

## 2. Thu thập ví dụ từ công việc thực tế

### 2.1. Bắt đầu từ mục tiêu của tác nhân

Xác định ai thực hiện công việc và họ muốn đạt kết quả gì. Tác nhân có thể là khách hàng, nhân viên vận hành, quản trị viên, đối tác hoặc một hệ thống khác.

Với mỗi tác nhân, hãy hỏi:

- Họ bắt đầu công việc trong hoàn cảnh nào?
- Họ cần thông tin hoặc quyền gì?
- Hành động nào họ thực hiện?
- Họ kỳ vọng nhận được kết quả gì?
- Ai hoặc hệ thống nào tiếp tục xử lý sau đó?
- Điều gì khiến công việc được xem là hoàn tất?

Ví dụ với quy trình hoàn tiền:

| Tác nhân | Mục tiêu | Ví dụ cần tìm |
|---|---|---|
| Khách hàng | Nhận lại khoản tiền đủ điều kiện | Hủy đơn đã thanh toán và yêu cầu hoàn tiền |
| Nhân viên hỗ trợ | Giải quyết yêu cầu hợp lệ | Kiểm tra lý do, trạng thái đơn và quyền xử lý |
| Bộ phận tài chính | Đối soát khoản tiền đã hoàn | So sánh giao dịch gốc, giao dịch hoàn và báo cáo |
| Cổng thanh toán | Xử lý yêu cầu hoàn | Chấp nhận, từ chối hoặc phản hồi chậm |

### 2.2. Tìm ví dụ ở nhiều nguồn

Không nên chỉ dựa vào tài liệu yêu cầu. Ví dụ thực tế có thể đến từ:

- Phỏng vấn người dùng hoặc nhân viên vận hành.
- Quan sát quy trình làm việc.
- Ticket hỗ trợ và khiếu nại đã được xử lý.
- Báo cáo sự cố và các tình huống ngoại lệ.
- Quy định, chính sách và hợp đồng.
- Bản ghi nghiệp vụ hoặc báo cáo vận hành được phép sử dụng.
- Workshop giữa Product Owner, chuyên gia nghiệp vụ, developer và tester.

Khi sử dụng dữ liệu hoặc tình huống thật, hãy bảo vệ thông tin cá nhân và bí mật. Có thể thay định danh, số tiền hoặc ngày tháng bằng dữ liệu tổng hợp nếu việc thay thế không làm mất ý nghĩa của quy tắc cần minh họa.

### 2.3. Hỏi về trường hợp bình thường và trường hợp bất thường

Người dùng thường mô tả luồng thành công trước tiên. Người kiểm thử cần hỏi thêm về các trường hợp khác:

- Trường hợp nào xảy ra thường xuyên?
- Có ngoại lệ nào cần nhân viên can thiệp không?
- Điều gì xảy ra khi dữ liệu thiếu hoặc sai?
- Có trường hợp nào chính sách thay đổi theo vai trò, thời gian hoặc loại khách hàng không?
- Khi hai người cùng thao tác, kết quả nào được xem là hợp lệ?
- Có sự cố nào từng xảy ra mà quy trình hiện tại chưa xử lý tốt không?

Ví dụ, khi tìm hiểu đặt lịch, ngoài việc đặt thành công, cần hỏi về lịch hết chỗ, khách đến muộn, khách hủy sát giờ, nhân viên đổi lịch, dịch vụ ngừng hoạt động và hai khách cùng chọn chỗ cuối cùng.

### 2.4. Ghi ví dụ theo cấu trúc nhất quán

Một mẫu đơn giản:

| Trường | Nội dung cần ghi |
|---|---|
| Mã ví dụ | Định danh duy nhất để truy vết |
| Tác nhân | Ai thực hiện hoặc chịu ảnh hưởng |
| Mục tiêu | Công việc cần hoàn tất |
| Bối cảnh | Trạng thái và điều kiện ban đầu |
| Hành động | Điều tác nhân hoặc hệ thống thực hiện |
| Kết quả mong đợi | Điều cần xảy ra trong nghiệp vụ |
| Ngoại lệ | Điều kiện có thể làm kết quả khác đi |
| Nguồn | Người, tài liệu hoặc dữ liệu xác nhận |
| Câu hỏi còn mở | Quy tắc chưa rõ hoặc chưa thống nhất |

Ví dụ:

| Trường | Ví dụ đặt lịch |
|---|---|
| Mã ví dụ | EX-BOOK-01 |
| Tác nhân | Khách hàng đã đăng nhập |
| Mục tiêu | Đặt một khung giờ còn chỗ |
| Bối cảnh | Khung giờ có một chỗ khả dụng |
| Hành động | Khách xác nhận đặt lịch |
| Kết quả mong đợi | Một lịch được tạo, số chỗ giảm một và khách nhận xác nhận |
| Ngoại lệ | Một khách khác có thể đặt cùng thời điểm |
| Nguồn | Quy trình đặt lịch và xác nhận của chủ sở hữu nghiệp vụ |
| Câu hỏi còn mở | Thời gian giữ chỗ trước khi thanh toán là bao lâu? |

Ví dụ này giúp nhóm nhận ra câu hỏi về đặt đồng thời và giữ chỗ trước khi biến nó thành tiêu chí chính thức.

## 3. Tìm quy tắc nghiệp vụ nằm sau ví dụ

### 3.1. Không suy ra quy tắc từ một ví dụ duy nhất

Một ví dụ cho thấy một trường hợp cụ thể được xử lý ra sao. Nó không luôn cho biết ranh giới của quy tắc.

Ví dụ: khách hủy lịch trước 24 giờ và được hoàn tiền. Chưa thể kết luận mọi lịch hủy trước 24 giờ đều được hoàn toàn bộ tiền. Có thể có loại dịch vụ không hoàn phí, khoản đặt cọc không hoàn hoặc điều kiện khác theo kênh đặt.

Hãy tìm các ví dụ đối chiếu:

- Trường hợp ngay trước ngưỡng thời gian.
- Trường hợp đúng tại ngưỡng.
- Trường hợp ngay sau ngưỡng.
- Trường hợp có khoản thanh toán khác nhau.
- Trường hợp do nhân viên thực hiện.
- Trường hợp lịch đã bắt đầu hoặc đã hoàn tất.

Các ví dụ đối chiếu giúp xác định ranh giới và ngoại lệ của quy tắc.

### 3.2. Phân biệt sự kiện, quy tắc và quyết định

Khi thảo luận một tình huống, tách ba lớp:

- **Sự kiện:** điều đã xảy ra hoặc điều kiện thực tế.
- **Quy tắc:** chính sách hoặc điều kiện quyết định cách xử lý.
- **Quyết định:** kết quả hệ thống phải đưa ra trong tình huống đó.

Ví dụ:

| Lớp | Nội dung |
|---|---|
| Sự kiện | Khách gửi yêu cầu hủy 10 giờ trước giờ hẹn |
| Quy tắc | Hủy trực tuyến chỉ được phép trước giờ hẹn ít nhất 12 giờ |
| Quyết định | Yêu cầu hủy trực tuyến bị từ chối |
| Hành vi mong đợi | Lịch vẫn giữ trạng thái đã xác nhận; khách nhận lý do từ chối và hướng dẫn liên hệ hỗ trợ nếu chính sách có quy định |

Phân biệt như vậy giúp tránh nhầm một hành vi hiện tại của phần mềm với quy tắc nghiệp vụ đã được phê duyệt.

### 3.3. Dùng ví dụ để tìm điều kiện và ngoại lệ

Một quy tắc có thể phụ thuộc vào nhiều yếu tố:

- Vai trò hoặc nhóm khách hàng.
- Thời gian và múi giờ.
- Trạng thái hiện tại.
- Giá trị giao dịch hoặc giới hạn số lượng.
- Khu vực, loại dịch vụ hoặc phương thức thanh toán.
- Quyền sở hữu dữ liệu.
- Kết quả từ hệ thống bên ngoài.

Dùng bảng quyết định khi nhiều điều kiện kết hợp:

| Điều kiện | Trường hợp A | Trường hợp B | Trường hợp C |
|---|---|---|---|
| Còn ít nhất 12 giờ | Có | Có | Không |
| Lịch đã bắt đầu | Không | Không | Không |
| Vai trò là khách sở hữu lịch | Có | Không | Có |
| Hủy trực tuyến được phép | Có | Không | Không |
| Kết quả | Cho phép hủy | Từ chối do không có quyền | Từ chối do quá hạn |

Bảng trên minh họa cách tách điều kiện. Quy tắc thật phải được chủ sở hữu nghiệp vụ xác nhận, đặc biệt khi có ưu tiên hoặc ngoại lệ giữa các điều kiện.

### 3.4. Làm rõ quy tắc khi các ví dụ mâu thuẫn

Nếu hai người đưa ra ví dụ có kết quả khác nhau, đừng vội chọn một ví dụ làm chuẩn. Có thể:

- Hai ví dụ thuộc hai phiên bản chính sách khác nhau.
- Vai trò hoặc loại khách hàng khác nhau.
- Một ví dụ là trường hợp ngoại lệ được phê duyệt.
- Quy trình thực tế đang khác tài liệu.
- Hệ thống hiện tại có lỗi và không phản ánh quy tắc mong muốn.

Ghi lại nguồn, thời điểm và bối cảnh của từng ví dụ. Nhờ người có thẩm quyền xác nhận quy tắc có hiệu lực. Nếu chưa thể thống nhất, đánh dấu câu hỏi còn mở và không biến một cách hiểu cá nhân thành tiêu chí chấp nhận.

## 4. Chuyển ví dụ thành hành vi có thể quan sát

### 4.1. Hành vi quan sát được là gì?

Hành vi quan sát được là thay đổi hoặc phản hồi có thể nhận biết từ bên ngoài hệ thống hoặc qua một nguồn bằng chứng được phép truy cập. Nó có thể gồm:

- Phản hồi hiển thị cho người dùng.
- Mã trạng thái và payload của API.
- Trạng thái đối tượng nghiệp vụ.
- Dữ liệu được tạo, cập nhật hoặc không thay đổi.
- Sự kiện được phát hoặc tiêu thụ.
- Thông báo được gửi.
- Báo cáo hoặc kết quả đối soát.
- Quyền truy cập được cấp hoặc từ chối.
- Thời gian hoàn tất hoặc giới hạn được đo.

Không phải mọi hành vi đều cần hiển thị trên giao diện. Ví dụ, khi khách hủy lịch, việc chỗ trống được mở lại có thể chỉ quan sát được qua dữ liệu lịch hoặc API quản lý khung giờ. Đây vẫn là hành vi nghiệp vụ quan trọng.

### 4.2. Mô tả kết quả bằng trạng thái và tác động

Một mô tả như “hệ thống xử lý thành công” quá chung. Hãy cụ thể hóa:

- Đối tượng nào được tạo hoặc thay đổi?
- Trạng thái trước và sau là gì?
- Dữ liệu nào cần được cập nhật?
- Có tác động phụ nào cần xảy ra hoặc không được xảy ra?
- Tác nhân nhận được phản hồi nào?
- Hệ thống liên quan nào cần nhận sự kiện hoặc thông tin?
- Kết quả phải xuất hiện trong thời hạn nào?

Ví dụ:

| Mô tả chung | Hành vi có thể quan sát |
|---|---|
| Hủy lịch thành công | Lịch chuyển từ CONFIRMED sang CANCELLED; không còn được tính vào lịch đang hoạt động |
| Giải phóng chỗ | Số chỗ khả dụng tăng đúng một theo quy tắc |
| Gửi xác nhận | Một thông báo hủy được ghi nhận cho đúng người nhận |
| Từ chối người không có quyền | API trả lỗi theo hợp đồng; lịch và dữ liệu liên quan không thay đổi |
| Hoàn tiền | Giao dịch hoàn được ghi nhận với số tiền và tham chiếu giao dịch gốc đúng |

### 4.3. Xác định nguồn quan sát có thẩm quyền

Mỗi kết quả cần có nguồn xác minh phù hợp. Không nên dùng một dấu hiệu thuận tiện nếu nó không chứng minh điều cần kiểm tra.

| Hành vi cần xác nhận | Nguồn quan sát phù hợp |
|---|---|
| Người dùng nhận được thông báo | Giao diện hoặc kênh nhận thử; trạng thái gửi thông báo |
| Đơn hàng đã được tạo | API hoặc bản ghi đơn hàng có mã định danh |
| Thanh toán đã được ghi nhận | Giao dịch từ hệ thống thanh toán và đối soát |
| Tồn kho đã thay đổi | Dữ liệu tồn kho hoặc API có thẩm quyền |
| Quyền truy cập bị từ chối | Response API và xác nhận dữ liệu không bị trả về |
| Sự kiện đã được xử lý | Event ID, trạng thái consumer hoặc bản ghi kết quả |
| Báo cáo đã cập nhật | Báo cáo hoặc dữ liệu tổng hợp theo thời hạn đã định |

Nguồn quan sát cần được lựa chọn theo kiến trúc và quyền truy cập của môi trường. Khi dữ liệu được xử lý bất đồng bộ, hãy xác định trạng thái trung gian hợp lệ và thời hạn chờ trước khi kết luận thất bại.

### 4.4. Phân biệt hành vi bên ngoài với chi tiết triển khai

Tiêu chí chấp nhận thường nên mô tả kết quả nghiệp vụ, không khóa vào một cách triển khai nội bộ.

Ví dụ:

- Hành vi: “Khách nhận được xác nhận đặt lịch sau khi lịch được tạo.”
- Chi tiết triển khai: “Dịch vụ A gọi hàm B, ghi bảng C rồi gửi message vào queue D.”

Chi tiết triển khai có thể hữu ích cho kiểm thử kỹ thuật, nhưng tiêu chí chấp nhận nên giữ ổn định khi kiến trúc thay đổi mà kết quả nghiệp vụ không đổi. Nếu một chi tiết kỹ thuật là yêu cầu bắt buộc, chẳng hạn phải ghi audit trail theo quy định, hãy mô tả rõ lý do và bằng chứng cần có.

## 5. Viết kịch bản từ ví dụ bằng Given–When–Then

Given–When–Then giúp chuyển tình huống thành kịch bản dễ đọc và có kết quả mong đợi rõ ràng.

### 5.1. Cấu trúc cơ bản

- **Given (Cho trước):** bối cảnh, trạng thái ban đầu và dữ liệu liên quan.
- **When (Khi):** hành động hoặc sự kiện kích hoạt.
- **Then (Thì):** hành vi có thể quan sát và kết quả mong đợi.

Ví dụ:

~~~gherkin
Feature: Hủy lịch hẹn

  Scenario: Khách hủy lịch trước thời hạn cho phép
    Given khách sở hữu một lịch đã xác nhận
      And thời điểm hiện tại còn ít nhất 12 giờ trước giờ hẹn
    When khách gửi yêu cầu hủy lịch
    Then lịch chuyển sang trạng thái CANCELLED
      And chỗ được mở lại theo chính sách
      And khách nhận được xác nhận hủy
~~~

Kịch bản này cho biết điều kiện, hành động và kết quả. Để hoàn chỉnh, nhóm cần xác nhận ngưỡng 12 giờ, cách giải phóng chỗ và kênh thông báo theo quy tắc thực tế.

### 5.2. Viết kịch bản từ chối

Ví dụ:

~~~gherkin
Scenario: Khách hủy lịch quá sát giờ
  Given khách sở hữu một lịch đã xác nhận
    And thời điểm hiện tại còn 10 giờ trước giờ hẹn
  When khách gửi yêu cầu hủy trực tuyến
  Then hệ thống từ chối yêu cầu theo chính sách
    And lịch vẫn ở trạng thái CONFIRMED
    And khách nhận được hướng dẫn xử lý tiếp theo
~~~

Kịch bản âm cần xác nhận cả điều không xảy ra. Ví dụ, lịch không được chuyển trạng thái và chỗ không được mở lại khi yêu cầu bị từ chối.

### 5.3. Giữ kịch bản tập trung vào một quy tắc

Một kịch bản quá nhiều hành động và kết quả có thể khó chẩn đoán. Hãy tách khi:

- Các kết quả có thể thất bại độc lập.
- Các điều kiện đại diện cho quy tắc khác nhau.
- Một kịch bản cần nhiều vai trò hoặc nhiều hành trình không liên quan.
- Dữ liệu hoặc trạng thái ban đầu quá phức tạp.

Có thể giữ nhiều kiểm tra trong cùng kịch bản khi chúng là các tác động bắt buộc của cùng một hành động nghiệp vụ, chẳng hạn hủy lịch đồng thời cập nhật trạng thái và giải phóng chỗ.

### 5.4. Sử dụng bảng ví dụ cho nhiều biến thể

Khi cùng một quy tắc có nhiều dữ liệu đại diện, dùng bảng ví dụ để tránh lặp nội dung:

~~~gherkin
Scenario Outline: Kiểm tra thời hạn hủy lịch
  Given khách sở hữu lịch đã xác nhận
    And còn <hours_before> giờ trước giờ hẹn
  When khách gửi yêu cầu hủy trực tuyến
  Then kết quả là <decision>

Examples:
  | hours_before | decision |
  | 48           | ALLOWED  |
  | 12           | ALLOWED  |
  | 10           | REJECTED |
  | 1            | REJECTED |
~~~

Bảng này chỉ đúng nếu chính sách bao gồm trường hợp đúng 12 giờ. Nếu ngưỡng là lớn hơn 12 giờ, kết quả tại ngưỡng phải được thay đổi. Giá trị biên cần được xác nhận thay vì suy ra từ cách viết ví dụ.

## 6. Chọn loại ví dụ để bao phủ quy tắc

Một ví dụ thành công thường chỉ bao phủ một phần hành vi. Hãy chọn các loại ví dụ phù hợp với rủi ro.

### 6.1. Luồng thành công

Minh họa người dùng đạt mục tiêu khi mọi điều kiện hợp lệ.

Ví dụ: khách có quyền, khung giờ còn chỗ, dữ liệu hợp lệ và xác nhận đặt lịch. Hành vi quan sát gồm lịch được tạo, số chỗ cập nhật và xác nhận được gửi.

### 6.2. Luồng thay thế

Minh họa một cách hợp lệ khác để đạt cùng mục tiêu.

Ví dụ: khách thanh toán bằng thẻ hoặc ví điện tử; khách đặt lịch qua nhân viên thay vì tự đặt trên ứng dụng. Hai luồng có thể khác bước nhưng phải đạt kết quả nghiệp vụ tương đương theo chính sách.

### 6.3. Luồng từ chối và lỗi

Minh họa khi điều kiện không đạt hoặc hệ thống không thể hoàn tất.

Ví dụ: khung giờ hết chỗ, người dùng thiếu quyền, phương thức thanh toán bị từ chối hoặc dịch vụ phụ thuộc timeout. Cần xác định phản hồi, trạng thái dữ liệu và cách phục hồi.

### 6.4. Giá trị biên

Minh họa các trường hợp tại ranh giới của quy tắc:

- Đúng thời hạn hủy.
- Số lượng bằng giới hạn tối đa.
- Số tiền bằng ngưỡng miễn phí.
- Thời điểm ngay trước hoặc sau khi phiên hết hạn.
- Đơn hàng có đúng một sản phẩm hoặc số lượng tối thiểu.

Giá trị biên giúp phân biệt các điều kiện như lớn hơn, lớn hơn hoặc bằng, nhỏ hơn hoặc bằng. Hãy ghi rõ đơn vị, múi giờ và cách làm tròn nếu có.

### 6.5. Đồng thời và lặp lại

Minh họa khi nhiều tác nhân hoặc yêu cầu tác động đến cùng một tài nguyên:

- Hai khách cùng đặt chỗ cuối cùng.
- Khách gửi lại yêu cầu sau khi không nhận được phản hồi.
- Nhân viên và khách cùng cập nhật lịch.
- Webhook thanh toán được gửi lặp.

Hành vi cần quan sát gồm số bản ghi cuối, trạng thái, tác dụng phụ và tính nhất quán giữa các hệ thống.

### 6.6. Quy trình phục hồi

Minh họa cách hệ thống trở lại trạng thái hợp lệ sau lỗi:

- Thanh toán timeout nhưng nhà cung cấp đã xử lý.
- Thông báo chưa gửi được và cần thử lại.
- Một bước cập nhật thất bại sau khi bước trước đã thành công.
- Người vận hành thực hiện đối soát hoặc can thiệp thủ công.

Các ví dụ này đặc biệt quan trọng với hệ thống bất đồng bộ và tích hợp nhiều dịch vụ.

## 7. Ví dụ tổng hợp: đặt lịch và xử lý chỗ cuối cùng

Giả sử một nền tảng cho phép khách đặt lịch dịch vụ. Mỗi khung giờ có số chỗ giới hạn. Khách có thể tự đặt, hủy hoặc yêu cầu nhân viên hỗ trợ.

### 7.1. Tập hợp ví dụ nghiệp vụ

| Mã | Tình huống | Quy tắc cần làm rõ |
|---|---|---|
| EX-01 | Khách đặt khung giờ còn nhiều chỗ | Đặt thành công khi khách đủ điều kiện |
| EX-02 | Khách đặt chỗ cuối cùng | Không vượt số lượng chỗ khả dụng |
| EX-03 | Hai khách cùng đặt chỗ cuối | Chỉ một yêu cầu được xác nhận |
| EX-04 | Khách hủy trước thời hạn | Lịch hủy và chỗ được giải phóng |
| EX-05 | Khách hủy sau thời hạn | Từ chối hoặc chuyển sang quy trình hỗ trợ |
| EX-06 | Nhân viên hủy lịch thay khách | Quyền và dấu vết thao tác phải đúng |
| EX-07 | Dịch vụ thông báo tạm thời lỗi | Lịch vẫn có trạng thái rõ; thông báo được xử lý theo chính sách retry |

### 7.2. Chuyển ví dụ thành hành vi quan sát

| Ví dụ | Hành vi cần quan sát | Nguồn bằng chứng |
|---|---|---|
| EX-01 | Một lịch mới được tạo và số chỗ giảm đúng một | Bản ghi lịch và dữ liệu khung giờ |
| EX-02 | Lịch được xác nhận nếu chỗ cuối còn hợp lệ tại thời điểm xử lý | Trạng thái lịch và số chỗ |
| EX-03 | Không có hai lịch được xác nhận cho cùng chỗ cuối | Bản ghi lịch và lịch sử cập nhật tài nguyên |
| EX-04 | Lịch chuyển sang CANCELLED; chỗ được mở lại theo chính sách | Trạng thái lịch và số chỗ |
| EX-05 | Lịch không thay đổi; khách nhận lý do từ chối | Response và bản ghi lịch |
| EX-06 | Thao tác được ghi nhận đúng nhân viên; quyền và lịch sử được lưu | Audit trail và trạng thái lịch |
| EX-07 | Lịch không bị tạo lại; thông báo được thử lại hoặc ghi nhận lỗi để xử lý | Event ID, trạng thái notification và bản ghi lịch |

### 7.3. Kịch bản đồng thời

Một ví dụ cần được diễn đạt rõ hơn:

~~~gherkin
Scenario: Hai khách cùng đặt chỗ cuối cùng
  Given khung giờ chỉ còn một chỗ
    And khách A và khách B đều đủ điều kiện đặt
  When hai khách gửi yêu cầu đặt gần như đồng thời
  Then chỉ một yêu cầu được xác nhận
    And số chỗ khả dụng không âm
    And yêu cầu còn lại nhận kết quả hết chỗ hoặc xung đột theo hợp đồng
~~~

Không nên chỉ kiểm tra response của hai request. Cần kiểm tra trạng thái cuối trong dữ liệu có thẩm quyền để bảo đảm không có hai lịch xác nhận cùng chiếm một chỗ.

### 7.4. Tiêu chí chấp nhận tổng hợp

Từ các ví dụ, nhóm có thể thống nhất một số tiêu chí:

- Một khung giờ không thể có số lịch xác nhận vượt quá sức chứa.
- Yêu cầu đặt lịch chỉ thành công khi khách đủ điều kiện và còn chỗ tại thời điểm xác nhận.
- Hủy lịch chỉ được thực hiện theo trạng thái, thời hạn và quyền được quy định.
- Mọi thay đổi trạng thái quan trọng có thể truy vết tác nhân và thời điểm.
- Lỗi thông báo không làm mất hoặc tạo trùng lịch.
- Kết quả trả về cho khách phản ánh đúng trạng thái nghiệp vụ đã được xác nhận.

Các tiêu chí cần được chủ sở hữu sản phẩm xác nhận trước khi dùng làm chuẩn chấp nhận.

## 8. Liên kết ví dụ, tiêu chí, kiểm thử và bằng chứng

### 8.1. Ma trận truy vết

Một ví dụ cần có liên kết đến quy tắc, tiêu chí chấp nhận, trường hợp kiểm thử và nguồn bằng chứng.

| Trường | Ý nghĩa |
|---|---|
| Example ID | Mã ví dụ nghiệp vụ |
| Nguồn | Người, tài liệu hoặc dữ liệu xác nhận |
| Business rule ID | Quy tắc được rút ra từ ví dụ |
| Acceptance criteria ID | Điều kiện chấp nhận tương ứng |
| Test case ID | Trường hợp kiểm thử |
| Observable behavior | Hành vi có thể quan sát |
| Evidence source | API, dữ liệu, event, log hoặc giao diện |
| Status | Chưa làm rõ, đã xác nhận, đã thiết kế, đã chạy |
| Open question | Điểm còn thiếu hoặc chưa thống nhất |

Ví dụ:

| Example ID | Rule ID | Acceptance Criteria | Test Case | Hành vi / bằng chứng |
|---|---|---|---|---|
| EX-01 | BR-BOOK-01 | AC-01 | TC-BOOK-01 | Lịch được tạo; số chỗ giảm một |
| EX-03 | BR-BOOK-02 | AC-02 | TC-BOOK-03 | Chỉ một lịch được xác nhận; số chỗ không âm |
| EX-05 | BR-CANCEL-01 | AC-03 | TC-CANCEL-02 | Yêu cầu bị từ chối; lịch không đổi |
| EX-07 | BR-NOTIFY-01 | AC-04 | TC-NOTIFY-02 | Trạng thái thông báo có thể truy vết và xử lý lại |

### 8.2. Truy vết hai chiều

- Từ ví dụ đến kiểm thử: bảo đảm tình huống nghiệp vụ quan trọng được chuyển thành hành vi và bằng chứng.
- Từ kiểm thử về ví dụ: giúp phát hiện kiểm thử không có căn cứ nghiệp vụ hoặc đang kiểm tra một giả định chưa được xác nhận.
- Từ lỗi về ví dụ: khi sự cố xảy ra, tìm ví dụ và quy tắc liên quan để đánh giá thiếu sót trong tiêu chí hoặc phạm vi.
- Từ thay đổi yêu cầu về kiểm thử: xác định những ví dụ và kết quả mong đợi cần cập nhật.

Một ví dụ có thể dẫn đến nhiều trường hợp kiểm thử; một trường hợp kiểm thử có thể xác minh nhiều hành vi liên quan nếu mục tiêu được ghi rõ.

### 8.3. Ghi bằng chứng đủ để người khác đánh giá

Bằng chứng nên cho biết:

- Tình huống và dữ liệu đã dùng.
- Phiên bản và môi trường.
- Hành động hoặc sự kiện được thực hiện.
- Kết quả thực tế.
- Nguồn quan sát và mã tương quan nếu có.
- Kết quả mong đợi và sai lệch.
- Giới hạn hoặc phụ thuộc được mô phỏng.

Không cần lưu mọi dữ liệu thô nếu chúng không cần thiết. Bằng chứng phải đủ để tái hiện hoặc đánh giá kết luận, đồng thời tuân thủ quy định về dữ liệu và quyền truy cập.

## 9. Tổ chức buổi làm rõ bằng ví dụ

Một buổi làm rõ yêu cầu có thể dùng kỹ thuật Example Mapping để cấu trúc cuộc thảo luận quanh một câu chuyện hoặc một mục tiêu nghiệp vụ.

### 9.1. Bốn nhóm nội dung

- **Câu chuyện hoặc mục tiêu:** công việc người dùng cần hoàn tất.
- **Quy tắc:** các điều kiện chi phối hành vi.
- **Ví dụ:** tình huống cụ thể minh họa từng quy tắc.
- **Câu hỏi:** điều chưa rõ, mâu thuẫn hoặc cần quyết định.

Ví dụ với câu chuyện “Khách có thể hủy lịch”:

| Nhóm | Nội dung |
|---|---|
| Mục tiêu | Khách hủy lịch đã đặt khi chính sách cho phép |
| Quy tắc 1 | Chỉ lịch chưa bắt đầu mới có thể hủy trực tuyến |
| Ví dụ | Khách hủy trước giờ hẹn; lịch chuyển sang CANCELLED |
| Quy tắc 2 | Hủy sát giờ cần xử lý theo chính sách riêng |
| Ví dụ | Khách gửi yêu cầu 2 giờ trước giờ hẹn |
| Câu hỏi | Ngưỡng hủy là bao lâu? Ai được phép ngoại lệ? |
| Quy tắc 3 | Chỗ được giải phóng sau khi hủy hợp lệ |
| Ví dụ | Khung giờ có một chỗ trống trở lại |
| Câu hỏi | Nếu dịch vụ lịch cập nhật thành công nhưng thông báo thất bại thì xử lý ra sao? |

### 9.2. Cách điều phối

1. Chọn một mục tiêu hoặc câu chuyện có phạm vi đủ nhỏ.
2. Mời người hiểu quy trình, người quyết định và người xây dựng hoặc kiểm thử sản phẩm.
3. Đọc mục tiêu và hỏi kết quả nào được xem là thành công.
4. Thu thập ví dụ bình thường, ngoại lệ và giá trị biên.
5. Nhóm các ví dụ theo quy tắc.
6. Ghi câu hỏi chưa có lời giải thay vì tranh luận theo suy đoán.
7. Xác định người có thẩm quyền và thời điểm cần trả lời.
8. Chuyển các quy tắc đã thống nhất thành tiêu chí và kiểm thử.

Không cần cố giải quyết mọi câu hỏi trong một buổi. Hãy ưu tiên câu hỏi có thể làm thay đổi hành vi, rủi ro hoặc quyết định chấp nhận.

### 9.3. Khi nào nên dừng việc thu thập ví dụ?

Có thể chuyển sang thiết kế kiểm thử khi:

- Mục tiêu và tác nhân đã rõ.
- Quy tắc chính có ví dụ đại diện.
- Các ngoại lệ có hậu quả lớn đã được làm rõ.
- Kết quả có thể quan sát và có nguồn bằng chứng.
- Các câu hỏi còn lại đã có người phụ trách và mức ưu tiên.
- Các bên hiểu và thống nhất phạm vi chấp nhận.

Nếu tiếp tục thu thập thêm ví dụ nhưng chúng không làm thay đổi quy tắc hoặc phạm vi rủi ro, có thể đưa chúng vào backlog để xử lý sau.

## 10. Những sai lầm thường gặp

1. **Chỉ dùng ví dụ thành công:** không tìm trường hợp từ chối, biên, lỗi và phục hồi.
2. **Coi một ví dụ là toàn bộ quy tắc:** suy rộng từ một tình huống mà không kiểm tra trường hợp đối chiếu.
3. **Nhầm hành vi hiện tại với hành vi mong muốn:** hệ thống đang làm gì không nhất thiết là điều nghiệp vụ yêu cầu.
4. **Mô tả kết quả quá chung:** dùng từ “thành công”, “đúng” hoặc “xử lý xong” mà không xác định trạng thái và bằng chứng.
5. **Chỉ kiểm tra giao diện:** không xác minh dữ liệu, sự kiện hoặc tác động liên quan.
6. **Gắn tiêu chí với chi tiết triển khai:** làm tiêu chí mất ổn định khi kiến trúc thay đổi dù kết quả nghiệp vụ không đổi.
7. **Không xác định nguồn bằng chứng:** dựa vào log hoặc màn hình không có thẩm quyền cho kết luận.
8. **Bỏ qua ngoại lệ và mâu thuẫn:** tự chọn một cách hiểu mà không có xác nhận.
9. **Không quản lý câu hỏi còn mở:** để giả định chưa xác minh trở thành quy tắc ngầm.
10. **Không truy vết:** không biết ví dụ nào được kiểm tra và kiểm thử nào không có căn cứ.
11. **Dùng dữ liệu thật không phù hợp:** đưa thông tin cá nhân hoặc bí mật vào ví dụ và bằng chứng.
12. **Tạo quá nhiều kịch bản trùng lặp:** tăng số lượng nhưng không tăng mức độ bao phủ quy tắc.

## 11. Checklist liên kết ví dụ nghiệp vụ với hành vi có thể quan sát

- [ ] Đã xác định tác nhân và mục tiêu nghiệp vụ của hành trình.
- [ ] Đã thu thập ví dụ từ nguồn phù hợp và ghi lại bối cảnh.
- [ ] Đã phân biệt dữ liệu mẫu, sự kiện, quy tắc và quyết định.
- [ ] Đã tìm ví dụ đối chiếu để làm rõ điều kiện và ranh giới.
- [ ] Đã ghi nhận ngoại lệ, giá trị biên, đồng thời và phục hồi theo rủi ro.
- [ ] Các quy tắc quan trọng được người có thẩm quyền xác nhận.
- [ ] Mỗi ví dụ quan trọng được chuyển thành hành vi mong đợi cụ thể.
- [ ] Hành vi được mô tả bằng trạng thái, dữ liệu, phản hồi hoặc tác động quan sát được.
- [ ] Mỗi kết quả có nguồn bằng chứng phù hợp và có thẩm quyền.
- [ ] Kịch bản có tiền điều kiện, hành động và kết quả mong đợi rõ ràng.
- [ ] Các câu hỏi còn mở có người phụ trách và thời điểm xử lý.
- [ ] Ví dụ, quy tắc, tiêu chí, trường hợp kiểm thử và bằng chứng có thể truy vết.
- [ ] Dữ liệu minh họa và bằng chứng tuân thủ yêu cầu bảo vệ thông tin.
- [ ] Kết luận chấp nhận chỉ giới hạn trong hành vi và môi trường đã được xác minh.

Khi ví dụ nghiệp vụ được chuyển thành hành vi có thể quan sát, các bên có cùng căn cứ để hiểu yêu cầu, thiết kế kiểm thử và đánh giá sản phẩm. Một kết luận chấp nhận đáng tin cậy cần chỉ ra tình huống nào đã được kiểm tra, kết quả nào đã được xác nhận và bằng chứng đến từ đâu.
