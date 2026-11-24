# Trusted origin display

Trong luồng khôi phục tài khoản, người dùng có thể phải đặt lại mật khẩu, thay MFA hoặc đăng ký passkey trên thiết bị mới. Họ thường thực hiện những thao tác này khi vừa mất một phương thức xác thực, đang lo lắng và dễ làm theo hướng dẫn khẩn cấp. Nếu giao diện không giúp họ nhận biết mình đang tương tác với dịch vụ nào, một trang giả có thể sao chép toàn bộ hình thức của trang khôi phục thật.

**Trusted origin display** là việc giúp người dùng nhận biết nguồn đang yêu cầu thao tác, dựa trên thông tin có ranh giới tin cậy rõ ràng. Mục tiêu là để người dùng hiểu “tôi đang giao tiếp với ai, cho tài khoản nào và để thực hiện việc gì” trước khi cung cấp bằng chứng hoặc chấp thuận thay đổi phương thức xác thực.

Hiển thị origin là một lớp hỗ trợ quyết định. Quyền khôi phục vẫn phải được máy chủ kiểm soát bằng trạng thái giao dịch và bằng chứng hợp lệ.

## 1. Origin là gì?

Với các URL HTTPS thông thường, origin được xác định bởi bộ ba **scheme, hostname và port hiệu lực**. Path, query và fragment không thuộc origin. Đây là mô hình origin được mô tả trong [HTML Standard của WHATWG](https://html.spec.whatwg.org/multipage/browsers.html#concept-origin).

Giả sử dịch vụ sử dụng origin chính thức:

~~~text
https://accounts.example:443
~~~

Port HTTPS mặc định có thể được lược bỏ khi trình bày thành `https://accounts.example`. Hai đường dẫn `/recover/start` và `/recover/confirm` trên cùng origin vẫn thuộc cùng một origin. Ngược lại, `https://accounts.example:8443` là origin khác.

Các hostname dưới đây dùng miền ví dụ để minh họa; chúng không phải địa chỉ triển khai thật.

| Thành phần | Ví dụ | Ý nghĩa khi khôi phục |
| --- | --- | --- |
| Origin | `https://accounts.example` | Nguồn web đang phục vụ trang |
| Hostname | `accounts.example` | Tên máy chủ trong URL |
| Path | `/recover/confirm` | Chức năng bên trong nguồn đó |
| Tên thương hiệu | “Example Accounts” | Nhãn có thể bị sao chép |
| Tên tài khoản | `a***@mail.example` | Ngữ cảnh tài khoản sau khi được phép hiển thị |
| Hành động | “Thay phương thức MFA” | Việc người dùng sắp chấp thuận |

Không gộp các thành phần này thành một nhãn mơ hồ như “Example đã xác minh”. Nhãn đó không cho biết ai xác minh điều gì và có thể khiến người dùng hiểu nhầm rằng một logo xác nhận được địa chỉ của trang.

## 2. Phân biệt thông tin trình duyệt và nội dung trang

Một trang có thể tự vẽ thanh địa chỉ, biểu tượng ổ khóa, huy hiệu “an toàn” hoặc dòng chữ “đây là website chính thức”. Kẻ tấn công cũng có thể vẽ những thành phần đó.

Trong thiết kế này, cần phân biệt ba nguồn thông tin:

| Nguồn hiển thị | Ranh giới tin cậy | Cách sử dụng |
| --- | --- | --- |
| Thanh địa chỉ và thông tin trang của trình duyệt thật | Do trình duyệt quản lý | Dùng để nhận biết địa chỉ đang mở |
| Hộp thoại xác thực do trình duyệt hoặc hệ điều hành quản lý | Phụ thuộc cơ chế nền tảng đang sử dụng | Cung cấp ngữ cảnh trong bước xác thực được nền tảng điều phối |
| Logo, URL và thông báo bên trong trang | Do trang web cung cấp | Giải thích thao tác; không tự chứng minh trang là chính chủ |

Thông tin về kết nối HTTPS giúp đánh giá kết nối tới hostname đang mở. Một trang giả có HTTPS vẫn có thể phục vụ nội dung lừa đảo trên hostname của nó. Vì vậy, thông điệp “có HTTPS nên đáng tin” là một hướng dẫn không đầy đủ.

Đưa một dòng `window.location.origin` lên trang cũng không giải quyết được vấn đề này: trang giả có thể thay dòng chữ bằng bất kỳ địa chỉ nào. JavaScript có thể hỗ trợ trải nghiệm trên trang thật, nhưng không được trở thành bằng chứng duy nhất cho quyết định bảo mật của máy chủ.

## 3. Những địa chỉ dễ gây nhầm lẫn

Với origin chính thức `https://accounts.example`, cần làm rõ cách đọc các URL sau:

| URL minh họa | Hostname thực tế | Điểm gây nhầm lẫn |
| --- | --- | --- |
| `https://accounts.example.attacker.example/recover` | `accounts.example.attacker.example` | Tên dịch vụ xuất hiện ở phần đầu hostname của nguồn khác |
| `https://accounts.example@attacker.example/recover` | `attacker.example` | Chuỗi trước dấu `@` là userinfo |
| `https://attacker.example/accounts.example/recover` | `attacker.example` | Tên dịch vụ chỉ xuất hiện trong path |
| `https://attacker.example/#https://accounts.example` | `attacker.example` | Địa chỉ thật được giấu bằng nội dung fragment |
| `https://accounts.example:8443/recover` | `accounts.example`, port `8443` | Cùng hostname nhưng khác origin |

Tên miền quốc tế còn có thể chứa ký tự nhìn gần giống nhau. Giao diện cần tránh việc cắt mất phần hostname quyết định danh tính nguồn, dùng ký tự điều hướng văn bản để đảo thứ tự hiển thị hoặc tự biến một hostname không quen thuộc thành tên thương hiệu đáng tin.

Việc xử lý tên miền quốc tế nên theo chính sách nhất quán của hệ thống và nền tảng. Không tự viết một phép thay ký tự đơn giản rồi coi mọi tên “trông giống nhau” là cùng một origin.

## 4. Lấy origin chính thức từ nguồn được quản trị

Origin dùng để tạo đường dẫn khôi phục cần đến từ cấu hình được kiểm soát. Không để người gửi yêu cầu tự quyết định địa chỉ mà hệ thống sẽ đưa vào email hoặc thông báo.

Ví dụ, nếu máy chủ ghép reset URL từ `Host` do request mang tới, một yêu cầu với hostname giả có thể khiến email hợp lệ của dịch vụ chứa đường dẫn tới trang do kẻ tấn công quản lý. OWASP khuyến nghị tạo reset URL từ địa chỉ cố định hoặc danh sách tên miền đáng tin, sử dụng HTTPS và hạn chế rò rỉ token qua referrer. Xem [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#url-tokens).

Một phương án cấu hình minh họa:

~~~text
Recovery policy:
  Public origin: https://accounts.example
  Start path: /recover/start
  Continue path: /recover/continue
  Completion path: /recover/complete
~~~

Trong phương án này:

- Backend dựng URL từ origin và các path cố định trong policy.
- Tham số do người dùng cung cấp không được thay scheme, hostname hoặc port.
- Header `Forwarded` và `X-Forwarded-Host` chỉ được xử lý trong mô hình proxy đã cấu hình; không mặc nhiên là dữ liệu tin cậy.
- Origin cho môi trường phát triển, thử nghiệm và sản xuất được tách biệt.
- Liên kết trở về sau khôi phục dùng đích cố định hoặc tập đích được duyệt, tránh biến trang thật thành điểm trung chuyển tới trang giả.

Nội dung origin hiển thị trên trang nên lấy từ cùng policy dùng để dựng liên kết. Cách làm này giảm sai lệch trên hệ thống thật; nó không ngăn một website khác sao chép dòng chữ đó.

## 5. Thiết kế màn hình khôi phục có ngữ cảnh rõ ràng

Màn hình cần giúp người dùng nhận ra dịch vụ và hành động, đồng thời hướng họ tới nguồn thông tin mà trình duyệt thực sự quản lý.

Ví dụ giao diện sau khi giao dịch khôi phục đã được xác nhận đủ để hiển thị ngữ cảnh tài khoản:

~~~text
Khôi phục tài khoản Example

Địa chỉ chính thức: https://accounts.example
Hãy kiểm tra địa chỉ này trong thanh địa chỉ của trình duyệt.

Tài khoản: a***@mail.example
Bạn đang thực hiện: thay phương thức MFA đã mất.

[Tiếp tục]  [Dừng khôi phục]

Nếu không nhận ra thao tác này, hãy đóng trang và mở dịch vụ
từ địa chỉ bạn đã lưu hoặc ứng dụng chính thức.
~~~

Đây là nội dung giải thích bên trong trang, không phải một thanh địa chỉ thay thế.

Một số lựa chọn thiết kế có ích:

- Đặt hostname ở nơi dễ thấy trước thao tác nhạy cảm, với kích thước đọc được trên điện thoại.
- Cho phép xem đầy đủ địa chỉ nếu không gian hẹp; không chỉ hiện phần đầu rồi thêm dấu ba chấm.
- Dùng văn bản thật để công cụ hỗ trợ tiếp cận có thể đọc được.
- Trình bày origin và hành động bằng các nhãn riêng.
- Mô tả đúng việc sắp xảy ra, chẳng hạn “đăng ký passkey mới” hoặc “thay MFA”, thay cho nút “xác minh” không có ngữ cảnh.
- Chỉ hiện thông tin tài khoản theo quyền và trạng thái giao dịch hiện tại; tránh làm lộ việc một email có tài khoản ngay ở bước bắt đầu công khai.

Tên thiết bị, tên người dùng và nhãn passkey có thể là dữ liệu do người dùng nhập. Khi đưa lên trang, cần hiển thị như văn bản thông thường, giới hạn độ dài hợp lý và không cho chúng đóng vai trò thông báo hệ thống. Một tên thiết bị như “Đã xác minh bởi bộ phận bảo mật” không phải bằng chứng thiết bị đáng tin.

## 6. Gắn hiển thị origin với từng bước của giao dịch

Hiển thị địa chỉ đúng ở trang đầu chưa đủ nếu các bước sau chuyển người dùng sang một nguồn khác mà không giải thích.

Luồng minh họa dưới đây là đề xuất thiết kế cho một dịch vụ khôi phục; nó không phải quy trình bắt buộc cho mọi sản phẩm:

~~~mermaid
flowchart TD
    A["Mở điểm bắt đầu chính thức"] --> B["Tạo giao dịch khôi phục"]
    B --> C["Nhận liên kết hoặc bằng chứng"]
    C --> D["Mở trang trên origin đã cấu hình"]
    D --> E["Máy chủ kiểm tra trạng thái và bằng chứng"]
    E --> F["Hiển thị tài khoản, hành động và nguồn"]
    F --> G["Người dùng xác nhận thay đổi"]
    G --> H["Máy chủ áp dụng chính sách khôi phục"]
    H --> I["Thông báo kết quả và hướng dẫn đăng nhập"]
~~~

Các bước mang ý nghĩa khác nhau:

**Điểm bắt đầu:** người dùng có thể tự mở địa chỉ đã biết hoặc ứng dụng chính thức. Trang công khai giải thích cách khôi phục mà chưa tiết lộ dữ liệu tài khoản.

**Tiếp nhận liên kết:** đường dẫn đi tới origin đã cấu hình. Việc tải trang bằng GET không nên tự thực hiện thay đổi tài khoản, vì phần mềm quét email hoặc trình xem trước liên kết cũng có thể mở URL.

**Xem hành động:** sau khi có ngữ cảnh hợp lệ, hệ thống hiển thị tài khoản được che phù hợp và thay đổi dự kiến. Nội dung phải lấy từ giao dịch phía máy chủ; không chỉ tin các tham số như `action=replace-mfa` do trình duyệt gửi.

**Xác nhận:** backend kiểm tra quyền của giao dịch, bằng chứng và trạng thái trước khi thay đổi. Một nút “tôi đã kiểm tra địa chỉ” chỉ ghi nhận lựa chọn của người dùng, không thay thế các kiểm tra này.

**Kết thúc:** trang nêu rõ thay đổi đã áp dụng và cách đăng nhập tiếp theo. Quyền hạn của session sau khôi phục vẫn phải tuân theo chính sách của hệ thống; nhãn “khôi phục thành công” không tự cấp quyền đầy đủ.

## 7. Khi có passkey hoặc WebAuthn

WebAuthn có cơ chế ràng buộc credential với RP ID và kiểm tra ngữ cảnh origin trong nghi thức xác thực. RP ID không đồng nghĩa với toàn bộ origin: nó không chứa scheme hoặc port. Backend vẫn cần kiểm tra origin được phép, challenge và các thành phần xác minh của phản hồi. Tên thương hiệu do ứng dụng gửi không thay thế được các kiểm tra đó. Tham khảo [Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/).

Trong khôi phục, cần đặt câu hỏi: **ai đã được phép bắt đầu bước đăng ký passkey mới?** Một passkey được đăng ký trên origin thật vẫn có thể thuộc thiết bị của kẻ tấn công nếu một giao dịch khôi phục yếu đã cấp quyền đăng ký cho người đó.

Vì vậy, thiết kế minh họa của bài này tách hai quyết định:

1. Giao dịch hiện tại có đủ quyền để thêm hoặc thay phương thức xác thực hay chưa?
2. Nghi thức đăng ký đang diễn ra trong đúng ngữ cảnh được dịch vụ chấp nhận hay chưa?

Cả hai đều cần đáp ứng chính sách. Màn hình nên nói rõ rằng người dùng đang thêm passkey mới cho tài khoản, thay vì chỉ yêu cầu chạm vào thiết bị mà không giải thích mục đích.

Không giả định hộp thoại của mọi trình duyệt đều hiển thị đầy đủ scheme, hostname và port theo cùng một cách. Giao diện ứng dụng phải bổ sung ngữ cảnh hành động mà không giả làm giao diện nền tảng.

Nếu người dùng đã mất toàn bộ passkey, việc hiển thị origin không tạo ra bằng chứng sở hữu thay thế. Dịch vụ phải dùng phương án khôi phục phù hợp với rủi ro và chính sách đã thiết kế.

## 8. Chuyển miền, nhiều tenant và ứng dụng di động

### Nhiều tenant

Một dịch vụ có thể hỗ trợ nhiều tổ chức hoặc miền tùy chỉnh. Không lấy `tenant` và `returnUrl` từ request rồi tự cho phép origin bất kỳ.

Một thiết kế có kiểm soát sẽ ánh xạ tenant đã xác định ở backend tới origin đã được duyệt trong cấu hình. Việc thêm miền cần có quy trình quản trị riêng. Không dùng wildcard rộng để xử lý nhanh mọi subdomain, vì các subdomain có thể thuộc những hệ thống có mức bảo vệ khác nhau.

Giao diện cần phân biệt tên tổ chức và địa chỉ đang xử lý khôi phục. Một tên tổ chức đúng không chứng minh URL hiện tại đúng.

### Chuyển qua nhà cung cấp danh tính

Nếu luồng phải chuyển sang một nhà cung cấp xác thực khác, hãy giải thích trước khi chuyển và nêu nguồn dự kiến. Sau khi trở về, backend vẫn phải xác nhận giao dịch liên quan và kết quả được chấp nhận.

Không tự động mở rộng danh sách origin chỉ vì một trang trung gian đã hiển thị logo của dịch vụ. Mỗi nguồn có vai trò cụ thể và cần được cấu hình tương ứng.

### Thiết bị di động

Webview không hiện địa chỉ hoặc cửa sổ có giao diện tùy biến có thể làm người dùng khó xác định nguồn đang mở. Với bước khôi phục nhạy cảm, cần lựa chọn bề mặt trình duyệt hoặc cơ chế nền tảng phù hợp, đồng thời cung cấp cách xem địa chỉ rõ ràng.

Với liên kết mở ứng dụng, việc hiển thị tên ứng dụng không đủ. Cần dùng cơ chế liên kết ứng dụng và website được nền tảng xác minh theo thiết kế của sản phẩm. Không giả định mọi trình xử lý một URL đều là ứng dụng chính thức.

## 9. Xử lý dấu hiệu không khớp

Khi phát hiện yêu cầu đi qua nguồn không được hỗ trợ, hệ thống nên dừng bước đó và đưa ra cách bắt đầu lại từ điểm chính thức. Không tự chuyển tiếp token sang một origin mới để “sửa hộ” đường dẫn.

Thông báo có thể là:

~~~text
Không thể tiếp tục khôi phục trong ngữ cảnh hiện tại.

Hãy đóng trang này, mở dịch vụ từ địa chỉ bạn đã lưu
và bắt đầu lại mục Khôi phục tài khoản.
~~~

Thông báo không cần lặp lại token, email đầy đủ hoặc mọi chi tiết của giao dịch.

Một số hành vi cần tránh trong thiết kế:

- Hiển thị cảnh báo rồi vẫn cho thao tác thay MFA tiếp tục bằng nút “bỏ qua”.
- Coi header `Origin` là bằng chứng duy nhất về danh tính người gọi; client ngoài trình duyệt có thể tự tạo request.
- Tự vô hiệu hóa mọi yêu cầu khôi phục hợp lệ chỉ vì có một request từ origin lạ; hành vi đó có thể tạo điều kiện gây từ chối dịch vụ.
- Yêu cầu người dùng đọc token hoặc mã dự phòng cho nhân viên hỗ trợ chỉ để “xác nhận đúng trang”.
- Ghi toàn bộ URL có token vào log, công cụ phân tích hoặc ảnh minh họa gửi hỗ trợ.

Có thể ghi sự kiện như loại điểm vào, policy origin áp dụng, mã giao dịch nội bộ và lý do từ chối đã phân loại. Dữ liệu phục vụ vận hành cần đủ để điều tra mà không biến nhật ký thành nơi chứa bí mật khôi phục.

## 10. Ví dụ áp dụng: thay MFA sau khi mất điện thoại

Lan mất điện thoại chứa ứng dụng tạo mã. Một email giả hướng dẫn cô mở “cổng xác minh”, trong đó có logo đúng và dòng `https://accounts.example` được vẽ trên trang.

Nếu Lan chỉ dựa vào dòng chữ trong nội dung, cô có thể cung cấp bằng chứng khôi phục cho nguồn khác. Trong thiết kế của bài này, hướng dẫn từ trước giúp cô mở dịch vụ bằng địa chỉ đã lưu và kiểm tra thanh địa chỉ thật.

Khi vào luồng chính thức, trang hiển thị tài khoản được che và hành động “thay phương thức MFA đã mất”. Nếu Lan đang được yêu cầu đăng ký một passkey trên thiết bị mà cô không nhận ra, ngữ cảnh hành động giúp cô dừng lại thay vì hiểu nhầm đây là bước kiểm tra vô hại.

Phía máy chủ chỉ cho thay MFA khi giao dịch có đủ bằng chứng và quyền theo chính sách. Sau thay đổi, hệ thống áp dụng quy tắc session và gửi thông báo phù hợp. Origin được hiển thị rõ giúp Lan nhận biết nguồn tương tác; trạng thái và kiểm tra phía máy chủ quyết định thao tác có được phép xảy ra hay không.

Bài học thiết kế là giữ liên hệ rõ ràng giữa **nguồn đang mở, tài khoản liên quan và hành động sắp thực hiện**. Tên miền dễ đọc, bề mặt trình duyệt đáng tin và kiểm tra giao dịch cần phối hợp trong cùng luồng khôi phục.
