# Compromised actor assumptions — Giả định tác nhân bị chiếm quyền

Một request có token hợp lệ, chữ ký đúng và vai trò phù hợp chưa chứng minh người chủ tài khoản đang chủ động thực hiện nó. Người khác có thể đã lấy được phiên đăng nhập, kiểm soát thiết bị hoặc sử dụng thông tin xác thực của một dịch vụ.

**Compromised actor assumptions** là cách phát biểu rõ tác nhân nào có thể bị chiếm quyền, bên tấn công điều khiển được những gì và các quy tắc nghiệp vụ nào vẫn phải được giữ. Mục tiêu không phải giả định mọi thành phần đều hỏng cùng lúc, mà chọn các ranh giới có ý nghĩa để thiết kế và kiểm thử.

Trong chương **Actor Model**, bài học này nối mô hình tác nhân với việc bảo vệ phê duyệt, giá, quyền trên đối tượng, transaction, idempotency và tác vụ nền. Khi danh tính hợp lệ đã nằm trong tay người khác, các giới hạn nghiệp vụ còn lại quyết định phạm vi thiệt hại.

## 1. Danh tính hợp lệ và hành động có chủ đích là hai vấn đề khác nhau

Xác thực giúp hệ thống xác định chủ thể theo một cơ chế: phiên đăng nhập, token, chứng chỉ hoặc thông tin xác thực dịch vụ. Nếu cơ chế đó bị sử dụng bởi người chiếm quyền, hệ thống vẫn có thể nhận diện request là đến từ tài khoản hợp lệ.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tác nhân hợp lệ | Chủ thể được hệ thống nhận diện theo cơ chế xác thực | Tài khoản người mua có phiên đang hoạt động |
| Tác nhân bị chiếm quyền | Khả năng hành động của chủ thể bị bên khác điều khiển trong phạm vi nhất định | Người khác dùng được phiên người mua |
| Người dùng có ý đồ xấu | Chủ tài khoản thật sử dụng quyền được cấp để lạm dụng | Tự tạo nhiều hồ sơ để chiếm năng lực xử lý |
| Dịch vụ bị chiếm thông tin xác thực | Bên khác có thể giả danh dịch vụ ở những nơi chấp nhận credential đó | Có thể gọi API bằng danh tính worker |
| Runtime dịch vụ bị kiểm soát | Bên khác có thể điều khiển tiến trình và sử dụng tài nguyên mà tiến trình truy cập được | Đọc bí mật, thay nội dung message hoặc ghi dữ liệu theo quyền runtime |

Nhiều kiểm soát nghiệp vụ bảo vệ được cả tài khoản bị chiếm và người dùng có ý đồ xấu: giới hạn đối tượng, hạn mức, state machine và phê duyệt độc lập. Tuy nhiên, nguyên nhân, tín hiệu phát hiện và biện pháp khôi phục có thể khác nhau.

Một dòng audit gắn với `user-17` cho thấy hệ thống quy hành động cho tài khoản đó theo bằng chứng xác thực đang có. Nó không tự chứng minh người chủ thật đã đồng ý với tác động hoặc thiết bị của họ không bị kiểm soát.

## 2. Phải nói rõ bị chiếm quyền ở mức nào

Nếu chỉ ghi “giả sử tài khoản bị hack”, nhóm thiết kế dễ tưởng tượng những khả năng khác nhau. Cần mô tả mức điều khiển trước khi đánh giá biện pháp.

| Mức giả định | Bên tấn công có thể làm | Điều chưa tự được suy ra |
| --- | --- | --- |
| Có phiên người mua | Gọi API mà phiên được chấp nhận, đổi tham số, lặp và chạy đồng thời | Tự ký token quyền quản trị hoặc ghi trực tiếp cơ sở dữ liệu |
| Có tài khoản người duyệt | Thực hiện những quyết định mà tài khoản có quyền đưa ra | Kiểm soát tài khoản người duyệt khác hoặc thay mọi chính sách |
| Có credential dịch vụ | Gọi các đích chấp nhận credential với danh tính dịch vụ | Điều khiển mã của dịch vụ hoặc dùng mọi tài khoản hạ tầng của nó |
| Kiểm soát runtime worker | Thực hiện hành động trong phạm vi mạng, bí mật và quyền hạ tầng runtime có | Kiểm soát mọi dịch vụ hoặc mọi kho dữ liệu độc lập |
| Có quyền quản trị nghiệp vụ | Thay các cấu hình và quyền mà vai trò được phép quản lý | Mặc nhiên vượt các quyết định độc lập nằm ngoài phạm vi quản trị đó |
| Kiểm soát nhiều chủ thể độc lập | Phối hợp các vai trò tương ứng | Các bảo đảm dựa trên chính những chủ thể đó vẫn còn nguyên |

Không nên đánh giá “chống tài khoản người mua bị chiếm” bằng cách cho bên tấn công quyền tùy ý sửa bảng phê duyệt nếu khả năng đó không thuộc giả định. Ngược lại, khi runtime có thể ghi trực tiếp vào bảng, chỉ kiểm tra endpoint API sẽ không bao phủ được mức chiếm quyền đó.

Cũng cần ghi các giả định còn được tin cậy: nguồn danh tính, nơi quyết định quyền, dữ liệu giá, cơ chế lưu nội dung đã duyệt, cơ sở dữ liệu hoặc một dịch vụ kiểm soát độc lập. Biện pháp chỉ có ý nghĩa trong ranh giới tin cậy mà nó cần.

## 3. Viết một thẻ giả định có thể kiểm thử

Một giả định hữu ích cần trả lời bốn phần: tác nhân, khả năng điều khiển, tài sản và bảo đảm mong muốn.

Ví dụ cho tài khoản người mua:

```text
Tác nhân:
  Người mua user-17 thuộc organization-a.

Khả năng điều khiển:
  Sử dụng một phiên hợp lệ của tài khoản.
  Gọi API trực tiếp và bỏ qua giao diện.
  Thay trường trong request, mã đối tượng và thứ tự thao tác.
  Gửi lại, đổi khóa idempotency hoặc gửi đồng thời.

Ranh giới còn được tin cậy:
  Máy chủ xác minh danh tính và quyền đúng theo thiết kế.
  Giá có thẩm quyền và bản nội dung đã duyệt không bị sửa trực tiếp.
  Tài khoản người duyệt độc lập chưa bị chiếm.
  Cơ chế lưu trữ và transaction cung cấp bảo đảm đã chọn.

Bảo đảm cần giữ:
  Không đọc hoặc sửa đơn ngoài phạm vi.
  Không tự phê duyệt qua bất kỳ đường thực thi nào.
  Không dùng nội dung chưa được duyệt để thanh toán.
  Không tạo khoản thu trùng hoặc vượt hạn mức tổng hợp.
  Không tiêu thụ năng lực vượt giới hạn được cấp.
```

Phần ranh giới tin cậy không phải lý do bỏ qua các lỗi triển khai. Nó giúp biết cần kiểm thử những đường nào và khi nào phải bổ sung một kịch bản có mức chiếm quyền rộng hơn.

Nên viết thêm thẻ cho người duyệt, dịch vụ tích hợp hoặc quản trị viên nếu đó là tác nhân có quyền quan trọng. Không nên gộp mọi tác nhân vào một thẻ rồi đưa ra một kết luận chung rằng hệ thống “an toàn khi bị chiếm quyền”.

## 4. Từ quyền của tác nhân đến phạm vi thiệt hại

**Blast radius**, hay phạm vi thiệt hại, là tập tài sản và tác động mà một mức chiếm quyền có thể ảnh hưởng trong điều kiện đã xét.

Có thể phân tích theo các chiều:

- **Đối tượng:** một đơn, một khách hàng, một bộ phận hay toàn tổ chức?
- **Dữ liệu:** chỉ thông tin cần cho công việc hay cả giá vốn, hợp đồng và ghi chú nội bộ?
- **Hành động:** đọc, sửa nháp, duyệt, chuyển tiền hay cấp quyền?
- **Giá trị:** tối đa bao nhiêu tiền hoặc quyền lợi?
- **Thời gian:** trong bao lâu trước khi quyền hết hạn, bị thu hồi hoặc phải xác nhận lại?
- **Số lần:** một tác động duy nhất hay có thể lặp vô hạn?
- **Đường lan:** có thể dùng dịch vụ hoặc cấp quyền cho tác nhân khác không?

Quyền tối thiểu giúp giảm phạm vi này, nhưng phải áp dụng theo nghiệp vụ. Vai trò mang tên `USER` vẫn có thể gây thiệt hại lớn nếu được phép tạo vô hạn công việc có tính phí.

Một giới hạn mỗi giao dịch cũng không tự giới hạn tổng thiệt hại. Nếu mỗi lần được tối đa 4.900.000 đồng, nhiều lần liên tiếp vẫn có thể tạo tổng lớn. Muốn bảo vệ ngân sách tổng, cần một invariant tổng hợp theo chủ thể, người nhận, kỳ hoặc phạm vi phù hợp.

Đối với người dùng hợp lệ, các giới hạn cũng phải cho phép hoàn thành công việc. Mục tiêu là ràng buộc tác động theo hợp đồng, không phải làm mọi hành động trở nên không thể thực hiện.

## 5. Ví dụ: phiên người tạo đơn bị chiếm

Giả sử hệ thống bán hàng cho tổ chức có quy tắc:

1. Người mua chỉ được thao tác trên các đơn thuộc phạm vi được giao.
2. Giá và tổng tiền được xác định ở máy chủ.
3. Đơn phải được người có quyền khác với người tạo duyệt theo chính sách.
4. Phê duyệt gắn với nội dung, số tiền, tiền tệ và các điều kiện quyết định tác động.
5. Thay đổi nội dung quan trọng làm mất hiệu lực quyết định cũ hoặc bị từ chối.
6. Thanh toán tuân thủ hạn mức và không thu trùng cùng nghĩa vụ.

Bên tấn công kiểm soát phiên của người tạo đơn nhưng chưa kiểm soát người duyệt. Những chuỗi cần xét gồm:

```text
A. Tạo đơn → gọi thẳng API approve.
B. Sửa approvedBy trong request → yêu cầu duyệt.
C. Dùng mã đơn tổ chức khác → đọc hoặc sửa.
D. Đơn đã được duyệt → thay sản phẩm, số lượng hoặc người nhận → thanh toán.
E. Gửi lệnh cho worker → yêu cầu worker dùng quyền nội bộ để bỏ qua phê duyệt.
F. Gửi lại cùng thao tác hoặc đổi khóa → thử tạo thêm tác động.
G. Gửi nhiều thao tác đồng thời → tranh phần hạn mức còn lại.
```

Các chuỗi trên không đòi hỏi token giả hoặc dữ liệu sai kiểu. Một hệ thống chỉ dựa vào việc “đã đăng nhập” hoặc “giao diện không có nút đó” sẽ thiếu những giới hạn quan trọng.

### 5.1. Những invariant vẫn phải giữ

| Quy tắc | Điều cần thực thi dù phiên hợp lệ bị chiếm |
| --- | --- |
| Quyền theo đối tượng | Đối chiếu tổ chức, quan hệ sở hữu hoặc phân công ở máy chủ |
| Nguồn giá có thẩm quyền | Không lấy giá do client tự khai làm quyết định thanh toán |
| Tách quyết định | Không cho người tạo hoặc luồng chạy thay người tạo tự trở thành người duyệt độc lập |
| State machine | Không cho chuyển nháp hoặc chờ duyệt thẳng sang thanh toán |
| Nội dung được duyệt | Đối chiếu đúng phiên bản và các trường ảnh hưởng tác động |
| Hạn mức tổng hợp | Kiểm tra và cập nhật nguyên tử theo phạm vi ngân sách |
| Idempotency và tính duy nhất nghiệp vụ | Không tạo tác động thêm vì retry hoặc đổi khóa |
| Quota | Giới hạn tổng lượng công việc và số tác vụ đang chiếm năng lực |

Nếu bên tấn công vẫn chỉ làm những hành động mà người mua được phép làm trong các giới hạn đó, hệ thống có thể chưa phân biệt được ý định xấu bằng kiểm tra quyền. Tùy mức rủi ro, cần thêm xác nhận, giám sát hoặc quyết định độc lập cho các tác động nhạy cảm.

## 6. Tài khoản người duyệt bị chiếm: bảo vệ còn lại là gì?

Khi người duyệt bị chiếm quyền, một kiểm tra `hasRole(APPROVER)` có thể vẫn thành công. Phải nhìn vào những giới hạn còn độc lập với credential đó:

- Người duyệt chỉ được xử lý đúng tổ chức, bộ phận hoặc hồ sơ được giao.
- Quyết định chỉ áp dụng cho bản nội dung và số tiền được chỉ rõ.
- Không được duyệt vượt hạn mức của mình hoặc vượt ngân sách liên quan.
- Quy tắc không tự duyệt vẫn áp dụng theo danh tính có ý nghĩa của chính sách.
- Các quyết định giá trị cao có thể cần chủ thể thứ hai thật sự độc lập.
- Việc thêm người duyệt, đổi hạn mức hoặc thay chính sách không được trở thành đường tự nâng quyền ngoài quy trình.

Một người nắm hai tài khoản không nhất thiết là hai người phê duyệt độc lập. Nếu chính sách yêu cầu tách con người chịu trách nhiệm, cần mô hình quan hệ phù hợp và cơ chế quản lý tài khoản tương ứng; chỉ so sánh hai chuỗi `userId` khác nhau chưa chứng minh được điều đó.

Tương tự, người duyệt có thể có quyền sửa một phần dữ liệu. Chính sách phải nói rõ họ có được sửa rồi duyệt cùng nội dung không, hay sửa đổi cần đưa về quy trình khác.

### 6.1. Xác thực mạnh và xác nhận lại có phạm vi bảo vệ riêng

Xác thực nhiều yếu tố hoặc xác nhận lại có thể giảm khả năng sử dụng một thông tin xác thực bị lấy cắp trong những điều kiện tương ứng. Nhưng nếu bên tấn công đã điều khiển phiên đủ thẩm quyền hoặc thiết bị thực hiện xác nhận, không thể mặc định mọi quyết định tiếp theo là ý định đúng của người dùng.

Với hành động nhạy cảm, xác nhận nên gắn với tác động cụ thể: đối tượng, số tiền, tiền tệ, người nhận và phiên bản nội dung. Một cờ “đã xác nhận trong phiên” quá rộng có thể bị dùng cho hành động khác sau đó.

Bằng chứng xác nhận cũng cần thời hạn, phạm vi, khả năng dùng lại và cập nhật nguyên tử phù hợp. Nếu người dùng xác nhận 1.000.000 đồng cho đối tác A rồi request bị đổi thành người nhận B, hệ thống phải phát hiện không còn cùng tác động.

Các biện pháp này tăng lớp bảo vệ, nhưng vẫn dựa trên những giả định về kênh và chủ thể xác nhận. Cần mô tả đúng các giả định đó trong thẻ tác nhân.

## 7. Dịch vụ bị chiếm quyền và đường lan qua hệ thống

### 7.1. Có credential dịch vụ

Giả sử bên tấn công có thể gọi API bằng danh tính `payment-worker`. Dịch vụ đích vẫn phải kiểm tra năng lực, tổ chức, đối tượng, lệnh nguồn và trạng thái nghiệp vụ.

Credential hợp lệ không được cho phép:

```text
payment-worker tự tạo quyết định phê duyệt;
export-worker tự chọn tổ chức ngoài phạm vi lệnh;
notification-service đổi số tiền hoặc người nhận thanh toán;
một job thiếu ủy quyền tự biến thành công việc hệ thống toàn quyền.
```

Giới hạn dịch vụ theo chức năng giúp giảm đường lan. Nếu mọi workload dùng cùng một principal có toàn quyền, việc mất một credential có thể mở rộng tác động sang nhiều nghiệp vụ.

### 7.2. Kiểm soát runtime

Nếu bên tấn công điều khiển tiến trình, họ có thể bỏ qua các kiểm tra chỉ nằm trong chính tiến trình đó. Lúc này cần xem xét quyền truy cập dữ liệu, bí mật, mạng và những dịch vụ khác mà runtime có thể dùng.

Ví dụ, worker có quyền trực tiếp sửa mọi trạng thái đơn có thể không cần gọi API giữ guard. Mô hình “dịch vụ đích sẽ kiểm tra” không bao phủ đường ghi trực tiếp đó.

Các ranh giới độc lập có thể giữ được một phần bảo vệ: quyền cơ sở dữ liệu hẹp, dịch vụ sở hữu tài nguyên kiểm tra lệnh, ngân sách do thành phần khác thực thi hoặc nơi nhận tác động xác minh giới hạn. Mỗi biện pháp chỉ có tác dụng nếu bên bị chiếm không thể tự thay đổi hoặc bỏ qua ranh giới tương ứng.

Nếu chính thành phần có toàn quyền quyết định và sửa bằng chứng bị kiểm soát, không thể tiếp tục coi dữ liệu do riêng nó phát ra là bằng chứng độc lập. Cần ghi rõ sự thay đổi giả định, thay vì khẳng định audit trong tiến trình đó vẫn chứng minh mọi hành động đúng.

### 7.3. Không biến dịch vụ thành đường nâng quyền

Một người dùng có quyền thấp có thể không chiếm credential dịch vụ nhưng vẫn điều khiển tham số một job. Nếu worker tin dữ liệu đó rồi dùng đặc quyền của mình, người dùng đã tác động qua một thành phần có quyền rộng hơn.

Do đó, mô hình actor phải phân biệt người khởi xướng, dịch vụ thực thi và nguồn thẩm quyền của công việc. Quyền thực thi không được cộng tùy ý thành toàn bộ quyền của cả người dùng lẫn dịch vụ.

## 8. Giữ invariant dưới thứ tự thao tác do bên tấn công chọn

Một tác nhân bị chiếm có thể thử đúng thời điểm, gọi lại rất nhanh hoặc phối hợp nhiều phiên. Hệ thống phải giữ quy tắc qua chuỗi thao tác, không chỉ kiểm tra từng request riêng.

### 8.1. Phê duyệt phải gắn với nội dung

Một lần chuyển trạng thái hợp lệ nên kiểm tra đồng thời:

```text
Chủ thể còn đủ quyền theo chính sách áp dụng.
Đối tượng thuộc phạm vi.
Trạng thái nguồn cho phép hành động.
Phiên bản nội dung khớp quyết định.
Những trường quyết định tác động không bị tráo.
Các giới hạn dùng chung vẫn còn.
```

Giá trị phiên bản client gửi là dữ liệu kỳ vọng để đối chiếu, không phải bằng chứng nội dung đó đã được duyệt. Cần so với dữ liệu có thẩm quyền ở máy chủ.

### 8.2. Kiểm tra và cập nhật phải phối hợp

Hai request có thể cùng nhìn thấy còn 1.000.000 đồng ngân sách rồi mỗi request sử dụng 800.000 đồng. Kiểm tra giới hạn riêng lẻ đều có vẻ đúng nhưng tổng tác động vượt mức.

Transaction, cập nhật có điều kiện, khóa hoặc cơ chế phiên bản cần bảo vệ đúng phạm vi invariant. Khóa từng đơn riêng không tự bảo vệ hạn mức chung của tổ chức.

Một kịch bản đối kháng có thể được diễn đạt:

```text
Chuẩn bị: ngân sách còn 1.000.000 đồng.
Cho hai thao tác 800.000 đồng tranh cùng phạm vi.
Chờ các thay đổi liên quan kết thúc.
Xác minh: tổng được cam kết không vượt ngân sách.
Xác minh: thao tác không được cấp không tạo tác động bên ngoài trái phép.
```

### 8.3. Idempotency không thay thế quy tắc duy nhất nghiệp vụ

Cùng khóa và cùng nội dung phải được xử lý theo hợp đồng chống lặp. Nhưng bên tấn công có thể đổi khóa. Nghĩa vụ đã thanh toán vẫn cần trạng thái và ràng buộc phù hợp để không bị thực hiện lại.

Ngược lại, không nên coi mọi thao tác giống payload là cùng một nghĩa vụ. Định danh nghiệp vụ phải phản ánh việc nào được phép lặp và việc nào không.

Kết quả lưu để replay cũng phải được cách ly và phân quyền. Một tác nhân không được dùng khóa của chủ thể khác để đọc dữ liệu hoặc nhận kết quả nhạy cảm.

### 8.4. Lỗi và hủy không được phục hồi quyền lợi sai

Timeout không chứng minh tác động chưa xảy ra. Yêu cầu hủy không chứng minh worker đã dừng. Nếu mỗi lỗi đều được trả toàn bộ quota hoặc cho phép thực hiện lại, bên tấn công có thể cố tình khai thác sự bất định đó.

Cần giữ trạng thái chưa rõ, quyết toán phần đã dùng và đối soát tác động bên ngoài theo hợp đồng. Khả năng phục hồi là một phần của bảo vệ logic khi tác nhân chủ động chọn thời điểm ngắt hoặc gửi lại.

## 9. Phát hiện và thu hồi trong một khoảng thời gian có ý nghĩa

Các tín hiệu có thể hỗ trợ phát hiện gồm hành động khác thường, đổi người nhận, tăng lượng công việc, nhiều lần bị từ chối hoặc sử dụng ngoài phạm vi hoạt động quen thuộc. Chúng là tín hiệu đánh giá, không phải bằng chứng tuyệt đối về việc tài khoản bị chiếm.

Một tác nhân bị chiếm có thể hành động chậm và giống hành vi bình thường. Vì vậy, các invariant cốt lõi không nên chỉ bật khi hệ thống đánh dấu rủi ro.

Khi quyết định thu hồi, cần xem xét các lớp đang có hiệu lực:

| Lớp | Điều cần xác định |
| --- | --- |
| Tài khoản | Có chặn tạo phiên hoặc nhận công việc mới không? |
| Phiên, token | Các bằng chứng xác thực đang tồn tại còn được chấp nhận đến khi nào? |
| Cache quyền | Quyết định cũ được dùng lại trong bao lâu? |
| Grant và ủy quyền | Công việc đã được cấp có bị thu hồi hay có hiệu lực độc lập theo chính sách? |
| Hàng đợi | Job chưa chạy có được kiểm tra lại trước tác động không? |
| Job đang thực thi | Có thể dừng, chặn tác động tiếp theo hoặc phải đối soát phần đã xảy ra? |
| Liên kết tải và kết quả | Người mất quyền có tiếp tục lấy dữ liệu qua bản sao hoặc URL còn hiệu lực không? |

Đổi mật khẩu hoặc xoay một bí mật không tự chứng minh mọi phiên, token, grant và kết quả đã phát hành đều vô hiệu. Mỗi loại cần cơ chế và ranh giới hiệu lực được mô tả.

Nếu dùng token có thể được kiểm tra độc lập với máy chủ phát hành, khả năng thu hồi trước hạn phụ thuộc vào thiết kế kiểm tra trạng thái, thời hạn hoặc cơ chế liên quan. Không được giả định đặt một cờ trong cơ sở dữ liệu sẽ lập tức ảnh hưởng mọi nơi chấp nhận token.

Công việc đã gây tác động bên ngoài cần được xử lý theo trạng thái thực tế. Thu hồi quyền mới không tự hoàn lại tiền hoặc lấy lại dữ liệu đã được chuyển đi.

## 10. Audit và bằng chứng khi tác nhân không còn đáng tin

Nên phân biệt dữ liệu do tác nhân tự khai với dữ liệu được thành phần đáng tin quan sát hoặc xác định.

Ví dụ:

| Thông tin | Cách diễn giải |
| --- | --- |
| `reason=customer-approved` do client gửi | Lời khai về lý do; chưa phải bằng chứng khách hàng đã xác nhận |
| Danh tính từ ngữ cảnh xác thực | Tài khoản hoặc workload mà hệ thống nhận diện |
| Quyết định duyệt có tham chiếu nội dung | Bằng chứng hệ thống đã ghi nhận quyết định trên bản cụ thể |
| Xác nhận nhà cung cấp đã được kiểm tra | Bằng chứng về tác động theo giao thức và nguồn tương ứng |
| Dòng log từ runtime bị kiểm soát | Dữ liệu cần đánh giá lại trong mô hình chiếm quyền đó |

Audit nên giữ người khởi xướng, người thực thi, đối tượng, phiên bản, nguồn quyết định, thao tác logic và kết quả. Dữ liệu quan trọng cần được bảo vệ khỏi sửa xóa bởi chính tác nhân đang bị giới hạn.

Một nơi lưu độc lập có thể tăng khả năng bảo vệ lịch sử đã nhận. Nó không tự bảo đảm producer bị chiếm đã gửi mọi sự kiện hoặc khai đúng nội dung. Cần biết nguồn nào có thể quan sát độc lập thay đổi và khoảng trống nào còn tồn tại.

Không ghi nguyên credential để phục vụ điều tra. Có thể lưu định danh phiên hoặc tham chiếu phù hợp theo chính sách, với quyền đọc và thời hạn bảo vệ tương ứng.

Khi điều tra, cần tách ba kết luận: tài khoản nào được hệ thống nhận diện, tác động nào có bằng chứng đã xảy ra và ai thật sự điều khiển tài khoản ở thời điểm đó. Không nên khẳng định kết luận thứ ba chỉ từ hai loại dữ liệu đầu.

## 11. Kiểm thử bằng tài khoản hợp lệ có hành vi đối kháng

Một bộ test về giả định chiếm quyền nên sử dụng danh tính hợp lệ trong môi trường kiểm thử rồi thay đổi hành vi, thay vì chỉ gửi token hỏng.

| Giả định | Hành vi kiểm thử | Bảo đảm cần quan sát |
| --- | --- | --- |
| Phiên người mua bị chiếm | Gọi trực tiếp API duyệt với request đúng định dạng | Không có quyết định duyệt trái quyền |
| Cùng phiên hợp lệ | Gửi thêm `approvedBy` hoặc `role` tự khai | Không biến metadata client thành nguồn thẩm quyền |
| Người mua tổ chức A | Đổi mã đối tượng sang tổ chức B | Không đọc, sửa hoặc nhận kết quả ngoài phạm vi |
| Nội dung đã được duyệt | Sửa trường quyết định tác động rồi gọi thanh toán | Phát hiện phê duyệt không còn áp dụng |
| Credential người duyệt | Duyệt ngoài phân công hoặc vượt hạn mức | Quyền tổng quát không mở toàn bộ đối tượng |
| Có hai tài khoản cùng một chủ thể | Thử thỏa chính sách tách trách nhiệm | Kết quả phù hợp định nghĩa độc lập của chính sách |
| Credential dịch vụ | Gọi hành động không thuộc chức năng dịch vụ | Bị từ chối dù xác thực thành công |
| Worker theo ủy quyền | Bỏ hoặc đổi phạm vi người khởi xướng | Không được nâng thành thao tác hệ thống |
| Chủ động retry | Dùng cùng khóa rồi đổi khóa cho nghĩa vụ đã hoàn tất | Không tạo thêm tác động ngoài hợp đồng |
| Chủ động cạnh tranh | Hai thao tác tranh ngân sách còn ít | Tổng cam kết và tác động giữ được invariant |
| Tác nhân bị vô hiệu hóa | Truy cập lại qua API, consumer và đường replay | Hành vi đúng ranh giới thu hồi đã công bố |
| Job đang chờ khi quyền đổi | Chạy sau thời điểm thay đổi | Kiểm tra quyền hoặc grant theo đúng chính sách |
| Tác động ngoài chưa rõ | Timeout, hủy rồi yêu cầu lại | Không coi chưa biết là chưa thực hiện |
| Thử cấp quyền cho chính mình | Sửa role, hạn mức hoặc ngoại lệ | Không vượt quy trình quản trị và quyết định độc lập |
| Runtime có quyền hạ tầng | Đối chiếu khả năng ghi dữ liệu ngoài API trong môi trường thử nghiệm | Đánh giá đúng ranh giới còn bảo vệ, không suy luận từ test API đơn thuần |

Với mỗi test, kiểm tra cả response và tác động: trạng thái, bản phê duyệt, số tiền, dữ liệu bị trả, số lời gọi nhà cung cấp và mức sử dụng tài nguyên. Một lỗi HTTP sau tác động không chứng minh request không gây thiệt hại.

Có thể dùng kiểm thử theo state machine để sinh chuỗi thao tác và kiểm tra invariant sau mỗi bước hoặc mỗi commit. Với cạnh tranh và transaction, cần môi trường tích hợp tái hiện cơ chế lưu trữ tương ứng.

Những khả năng chưa thuộc giả định không nên âm thầm đưa vào test rồi kết luận sai về phạm vi bảo đảm. Khi muốn xét mức chiếm quyền rộng hơn, hãy thêm thẻ giả định và tiêu chí riêng.

## 12. Những kết luận dễ bị suy rộng

| Kết luận vội | Cách đánh giá chính xác hơn |
| --- | --- |
| “Token hợp lệ nên hành động là chủ ý của người dùng” | Token xác định quyền sử dụng bằng chứng xác thực, không tự chứng minh ý định |
| “Có MFA nên không cần giới hạn nghiệp vụ” | Xác thực mạnh và invariant bảo vệ các lớp khác nhau |
| “Hai tài khoản khác nhau nghĩa là hai quyết định độc lập” | Phải xem chính sách độc lập nói về tài khoản, con người hay đơn vị chịu trách nhiệm |
| “Dịch vụ nội bộ được phép bỏ qua guard” | Dịch vụ vẫn cần năng lực, phạm vi và nguồn thẩm quyền |
| “Một khoản nhỏ nên tổng thiệt hại nhỏ” | Cần xét số lần, cửa sổ thời gian và ngân sách tổng hợp |
| “Có idempotency nên không lặp được tác động” | Phải xét đổi khóa, định danh nghĩa vụ và các đường thực thi khác |
| “Khóa tài khoản là dừng mọi tác động ngay” | Phiên, cache, grant và job có cơ chế hiệu lực riêng |
| “Audit có tên người dùng nên đã biết ai thực hiện thật” | Cần phân biệt danh tính được nhận diện với người điều khiển credential |
| “Nếu runtime bị chiếm thì mọi thiết kế đều vô ích” | Cần xác định ranh giới độc lập nào còn giữ được giới hạn |
| “Hệ thống vẫn chặn khi mọi nguồn thẩm quyền cùng bị kiểm soát” | Bảo đảm phụ thuộc vào các thành phần còn tin cậy; cần nói rõ giới hạn đó |

Một tác nhân có toàn bộ quyền hợp lệ cho một tác động vẫn có thể quyết định thực hiện nó với ý đồ xấu. Khi hệ thống không có thêm bằng chứng hoặc giới hạn độc lập, không thể yêu cầu một kiểm tra quyền tự suy ra ý định thật.

Nếu nhiều người duyệt cùng bị chiếm hoặc thông đồng, bảo đảm dựa trên sự độc lập của họ cần được đánh giá lại. Có thể vẫn còn ngân sách, giới hạn đối tượng hoặc kiểm soát ở nơi nhận tác động, nhưng không nên tiếp tục khẳng định lớp phê duyệt đó còn nguyên sức bảo vệ.

## 13. Cách áp dụng vào một chức năng nhạy cảm

Với thao tác sửa giá, phê duyệt, xuất dữ liệu hoặc thanh toán, có thể đi theo trình tự:

1. **Chọn tác nhân và mức chiếm quyền:** phiên, credential, runtime hay quyền quản trị.
2. **Liệt kê khả năng điều khiển:** tham số, thứ tự, retry, đồng thời, danh tính phụ hoặc đường gọi dịch vụ.
3. **Xác định ranh giới còn đáng tin:** nơi giữ giá, quyền, nội dung duyệt, ngân sách và bằng chứng.
4. **Viết invariant cần sống sót:** đối tượng nào bị giới hạn, trạng thái nào phải giữ và mức tác động tối đa.
5. **Tìm đường mở rộng thẩm quyền:** ủy quyền, tác vụ nền, thay role, đổi chính sách hoặc tài khoản phụ.
6. **Thiết kế kiểm soát độc lập phù hợp:** guard ở nơi sở hữu tài nguyên, hạn mức, nội dung xác nhận và quyết định tách trách nhiệm.
7. **Định nghĩa phát hiện và thu hồi:** những gì bị chặn, thời điểm hiệu lực và cách xử lý công việc đang tồn tại.
8. **Kiểm thử bằng danh tính hợp lệ:** chứng minh invariant còn giữ dưới các chuỗi thao tác mà bên chiếm quyền có thể chọn.

Một phát biểu cụ thể có thể là:

> Khi phiên người mua bị chiếm nhưng người duyệt độc lập và máy chủ nghiệp vụ còn đáng tin, bên điều khiển phiên vẫn không được tự phê duyệt, dùng lại quyết định cho nội dung khác, thao tác ngoài tổ chức hoặc vượt ngân sách tổng hợp. Các tác vụ chạy nền thay người mua phải giữ những giới hạn tương ứng.

Giả định tác nhân bị chiếm quyền giúp chuyển niềm tin chung chung thành một phạm vi bảo đảm có thể kiểm tra. Hệ thống cần giữ quy tắc nghiệp vụ ngay cả khi một chủ thể hợp lệ hành động đối kháng, đồng thời nói rõ bảo đảm nào phụ thuộc vào những nguồn thẩm quyền còn độc lập.
