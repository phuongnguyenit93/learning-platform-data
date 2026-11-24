# Recovery completion guidance

## 1. Vì sao cần hướng dẫn sau khi khôi phục?

Recovery completion guidance là phần hướng dẫn giúp người dùng hiểu kết quả của luồng khôi phục tài khoản và biết hành động tiếp theo. Một màn hình có dấu tích xanh cùng câu “Thành công” thường chưa trả lời được các câu hỏi quan trọng: điều gì đã thay đổi, còn bước nào phải làm và thiết bị bị mất có tiếp tục truy cập được hay không?

Khôi phục có thể liên quan đến mật khẩu, MFA, passkey hoặc thiết bị xác thực. Những thao tác này có phạm vi khác nhau. Đặt lại mật khẩu không tự chứng minh rằng mọi passkey cũ đã bị thu hồi; đăng ký MFA mới cũng không tự chứng minh mọi phiên đăng nhập cũ đã kết thúc.

Phần hoàn tất cần trả lời bốn câu hỏi:

- Hệ thống đã xác nhận thay đổi nào?
- Người dùng có thể truy cập bằng cách nào từ thời điểm này?
- Những phiên và phương thức cũ đã được xử lý đến đâu?
- Nếu đây không phải thao tác của người dùng, họ cần làm gì?

Hướng dẫn phải dựa trên kết quả máy chủ. Một trang hoàn tất có thể trình bày kết quả, nhưng bản thân trang đó không tạo ra quyền đăng nhập hoặc quyền quản trị tài khoản.

## 2. Xác định đúng thời điểm được nói “hoàn tất”

Cần phân biệt hoàn thành một bước với hoàn thành toàn bộ hành trình.

| Trạng thái thực tế | Cách diễn đạt phù hợp | Điều chưa thể khẳng định |
| --- | --- | --- |
| Yêu cầu được tiếp nhận | “Yêu cầu của bạn đã được tiếp nhận.” | Đã xác minh danh tính |
| Một bằng chứng được chấp nhận | “Bạn có thể tiếp tục bước tiếp theo.” | Đã khôi phục đầy đủ quyền truy cập |
| Mật khẩu mới đã được lưu | “Mật khẩu đã được đặt lại.” | MFA, passkey và mọi phiên cũ đều đã bị thu hồi |
| Phương thức mới đã được đăng ký thành công | “Phương thức xác thực mới đã được thiết lập.” | Thiết bị cũ đã bị xóa dữ liệu |
| Những điều kiện bắt buộc của luồng đã đạt | “Khôi phục đã hoàn tất”, kèm phạm vi cụ thể | Mọi nguy cơ liên quan đến tài khoản đều đã biến mất |

Nếu chính sách yêu cầu đăng ký một phương thức mới trước khi kết thúc khôi phục MFA, bước đó phải được trình bày như phần bắt buộc của luồng. Không báo hoàn tất rồi mới tiết lộ người dùng vẫn chưa đủ điều kiện đăng nhập.

Một số việc có thể tiếp tục ở nền, như gửi thông báo. Điều này không nhất thiết làm mất hiệu lực thay đổi đã được xác nhận. Tuy nhiên, giao diện cần phân biệt việc đã hoàn thành với việc đang xử lý, đặc biệt khi phần còn lại ảnh hưởng trực tiếp đến an toàn truy cập.

Mất phản hồi sau khi gửi không đủ để kết luận thành công hoặc thất bại. Nếu chưa xác nhận được kết quả, hiển thị trạng thái chưa rõ và cung cấp lối đối chiếu phù hợp; không dựng màn hình thành công chỉ vì người dùng đã bấm nút cuối.

## 3. Bố cục một màn hình hoàn tất dễ hiểu

Một cấu trúc hữu ích gồm bốn phần, theo thứ tự người dùng cần biết:

1. **Kết quả chính:** nêu thay đổi đã được xác nhận.
2. **Ảnh hưởng đến truy cập:** nói phương thức nào dùng tiếp được và các phiên cũ đã được xử lý ra sao.
3. **Hành động chính:** một nút đưa đến bước tiếp theo.
4. **Trợ giúp và củng cố bảo vệ:** đường xử lý thao tác không nhận ra, cùng việc cần làm thêm khi phù hợp.

Ví dụ cho một luồng đặt lại mật khẩu có thu hồi các phiên đăng nhập khác:

```text
Mật khẩu đã được đặt lại

Hãy đăng nhập bằng mật khẩu mới.
Các phiên đăng nhập khác đã được thu hồi.

[Đến trang đăng nhập]

Bạn không thực hiện thay đổi này?
Mở hướng dẫn bảo vệ tài khoản và liên hệ hỗ trợ chính thức.
```

Chỉ dùng câu về thu hồi phiên khi máy chủ đã xác nhận đúng phạm vi đó. Nếu không có dữ liệu xác nhận, không thêm câu để làm người dùng yên tâm.

Hành động chính nên cụ thể, chẳng hạn “Đến trang đăng nhập”, “Thiết lập phương thức mới” hoặc “Xem cài đặt bảo mật”. Một nút chỉ ghi “Tiếp tục” có thể khiến người dùng không biết mình sắp đăng nhập, chuyển bước hay rời quy trình.

Không đặt quá nhiều lựa chọn ngang nhau trên màn hình cuối. Các việc bổ sung như xem lại thiết bị hoặc cập nhật kênh dự phòng có thể được hướng dẫn sau khi đăng nhập, trừ khi chúng là điều kiện bắt buộc của chính sách khôi phục.

## 4. Hướng dẫn theo từng loại thay đổi

Thông báo cần nói đúng phạm vi của thao tác thay vì dùng một câu chung cho mọi trường hợp.

### 4.1. Đặt lại mật khẩu

Nêu rõ mật khẩu mới đã có hiệu lực và người dùng cần đăng nhập theo luồng thông thường. Không hiển thị lại mật khẩu trên trang xác nhận hoặc gửi mật khẩu trong thông báo.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị thông báo việc đặt lại mật khẩu, không gửi mật khẩu trong email và để người dùng đăng nhập qua cơ chế thông thường thay vì tự động đăng nhập sau bước đặt lại.

Nếu sản phẩm còn yêu cầu MFA khi đăng nhập, hướng dẫn cần phản ánh điều đó. Người dùng mất cả mật khẩu và MFA có thể chưa hoàn thành toàn bộ hành trình chỉ bằng việc đặt mật khẩu mới.

### 4.2. Khôi phục MFA

Nêu phương thức mới đã được thiết lập hay người dùng vẫn cần đăng ký phương thức đó. Nếu phương thức trên thiết bị mất đã bị thu hồi, mô tả phạm vi thu hồi ở phía dịch vụ.

Ví dụ khi các điều kiện tương ứng đã được xác nhận:

```text
Phương thức xác thực mới đã được thiết lập.
Phương thức gắn với điện thoại đã báo mất không còn được
chấp nhận để đăng nhập vào dịch vụ này.

[Đến trang đăng nhập]
```

Không diễn đạt rằng hệ thống đã xóa ứng dụng hoặc dữ liệu trên điện thoại mất nếu nó chỉ thay đổi trạng thái xác thực của tài khoản.

### 4.3. Khôi phục passkey hoặc thiết bị

Phân biệt passkey mới được đăng ký với passkey cũ bị thu hồi. Việc thu hồi phía dịch vụ không đồng nghĩa xóa bản lưu passkey trên thiết bị hoặc trong dịch vụ đồng bộ của người dùng.

Nếu còn bước đăng ký passkey mới, giao diện cần giúp người dùng hoàn thành bước đó bằng ngữ cảnh và quyền được cho phép. Không chuyển họ đến một trang chỉ dành cho phiên đăng nhập đầy đủ khi phiên khôi phục hiện tại chưa có quyền tương ứng.

## 5. Giải thích session và đường truy cập tiếp theo

Người dùng thường nghĩ đổi mật khẩu sẽ tự đăng xuất mọi thiết bị. Hệ thống cần nói chính xác điều đã thực hiện thay vì dựa vào giả định đó.

Có thể phân biệt:

| Loại ngữ cảnh | Vai trò | Điều cần làm rõ khi hoàn tất |
| --- | --- | --- |
| Phiên khôi phục | Thực hiện các bước khôi phục được cho phép | Đã kết thúc hay chỉ còn quyền xem kết quả giới hạn |
| Phiên đăng nhập hiện tại | Truy cập ứng dụng sau xác thực | Có tiếp tục dùng được hay cần đăng nhập lại |
| Những phiên đăng nhập khác | Truy cập từ trình duyệt hoặc ứng dụng khác | Đã bị thu hồi trong phạm vi nào |
| Phiên của dịch vụ liên kết | Truy cập qua hệ thống khác | Có chịu tác động hay cần xử lý riêng |

Không hứa “đã đăng xuất khỏi mọi nơi” khi phạm vi chỉ gồm một ứng dụng. Nếu một tác vụ thu hồi còn đang chờ, dùng thông báo phù hợp với trạng thái đó và có lối tiếp tục được thiết kế trước. Nếu chính sách yêu cầu thu hồi xong mới hoàn tất khôi phục, không được bỏ qua điều kiện này để chuyển sang trang thành công.

Token khôi phục dùng một lần phải được tiêu thụ theo quy trình máy chủ. Nút Back, tải lại trang hoặc mở lại liên kết không được cho phép thực hiện lại thay đổi. Một thông tin xác nhận kết quả, nếu có, cần được giới hạn quyền và thời hạn; nó không trở thành bằng chứng thay thế cho đăng nhập.

Hướng dẫn truy cập tiếp theo cũng không nên yêu cầu người dùng cung cấp lại bí mật đã bị thu hồi. Sau khi báo mất thiết bị, bắt họ dùng chính thiết bị đó để đóng hành trình có thể tạo vòng lặp không thể hoàn thành.

## 6. Thông báo độc lập và tình huống “không phải tôi”

Màn hình hoàn tất chỉ được nhìn thấy bởi người đang thao tác. Nếu người đó là kẻ chiếm đoạt, chủ tài khoản có thể không nhìn thấy màn hình này. Vì vậy, hướng dẫn hoàn tất cần đi cùng cơ chế thông báo độc lập của sản phẩm.

[NIST SP 800-63B trong bộ Digital Identity Guidelines 800-63-4](https://pages.nist.gov/800-63-4/sp800-63b.html) quy định thông báo cho sự kiện khôi phục và yêu cầu chỉ dẫn rõ ràng khi người nhận không công nhận sự kiện. Đây là căn cứ để thiết kế thông báo giúp phát hiện khôi phục trái phép, theo phạm vi áp dụng của hệ thống.

Một thông báo hữu ích có thể chứa:

- Tên dịch vụ và loại thay đổi đã xảy ra.
- Thời gian sự kiện với cách hiển thị múi giờ rõ ràng.
- Thông tin tài khoản đã được giảm thiểu theo chính sách.
- Hướng dẫn nếu người nhận không thực hiện thay đổi.
- Đường đến kênh hỗ trợ chính thức.

Không gửi mật khẩu, OTP, token khôi phục hoặc mã dự phòng trong thông báo chỉ để chứng minh sự kiện có thật. Cũng không khẳng định người nhận chắc chắn đã đọc thông báo chỉ vì hệ thống đã tiếp nhận tác vụ gửi.

Địa chỉ mới vừa xuất hiện trong một yêu cầu chưa được xác minh không tự trở thành đích thông báo đáng tin cậy. Việc chọn kênh nhận cần tuân theo chính sách và nguồn liên hệ đã được thiết lập phù hợp.

Đường “Không phải tôi” cần dễ tìm nhưng không được biến một lần mở email thành lệnh hoàn tác nhạy cảm. Email có thể được quét tự động hoặc chuyển tiếp. Việc báo cáo, xác minh người báo và quyết định hạn chế truy cập là các bước cần thiết kế rõ; một GET từ liên kết không nên tự đổi mật khẩu hoặc khôi phục phương thức đã bị loại bỏ.

Hướng dẫn có thể khuyến khích người nhận mở ứng dụng hoặc truy cập dịch vụ theo cách họ đã biết để tìm trợ giúp. Nhân viên hỗ trợ không cần yêu cầu người dùng đọc lại mật khẩu, OTP hoặc token.

## 7. Giúp người dùng tránh bị mắc kẹt lần sau

Sau khi kết quả chính đã rõ, cung cấp một số việc bảo vệ phù hợp với tình huống. Tránh đặt một danh sách dài khiến người dùng không phân biệt được điều bắt buộc và điều có thể làm sau.

Ví dụ:

| Tình huống | Việc nên hướng dẫn | Điều cần giữ |
| --- | --- | --- |
| Đã dùng một mã dự phòng | Xem cách cấp hoặc lưu mã dự phòng thay thế theo chính sách | Không làm người dùng nghĩ mã đã dùng vẫn còn hiệu lực |
| Mất thiết bị xác thực | Đăng ký phương thức dự phòng phù hợp | Không yêu cầu thiết bị đã mất |
| Nghi ngờ bị chiếm đoạt | Xem lại phương thức xác thực, kênh liên hệ và phiên còn hiệu lực | Không coi đổi mật khẩu là xử lý xong mọi thay đổi trái phép |
| Chỉ quên mật khẩu | Lưu mật khẩu mới bằng công cụ quản lý phù hợp | Không yêu cầu lưu dưới dạng văn bản thiếu bảo vệ |

Nếu có mã dự phòng mới, phần hiển thị hoặc tải mã là thao tác xử lý bí mật riêng, cần được bảo vệ. Không nhúng mã vào URL trang hoàn tất hoặc nội dung thông báo sự kiện. Giải thích cách lưu giữ an toàn và điều kiện xem lại theo chính sách sản phẩm.

Các hành động tùy chọn có thể để sau khi đăng nhập. Những bước bắt buộc, như thiết lập phương thức đủ điều kiện trước khi cấp lại quyền truy cập, phải được đặt đúng trong hành trình và chưa được coi là hoàn tất khi còn thiếu.

## 8. Khả năng tiếp cận và quyền riêng tư của trang kết quả

[W3C WAI về phản hồi biểu mẫu](https://www.w3.org/WAI/tutorials/forms/notifications/) nhấn mạnh việc thông báo kết quả rõ ràng; tiêu đề trang và heading có thể giúp người dùng nhận biết kết quả sau khi gửi biểu mẫu.

Ở màn hình hoàn tất, nên:

- Có heading mô tả kết quả bằng chữ, không chỉ dùng màu xanh hoặc biểu tượng.
- Với SPA, cập nhật tiêu đề trang và quản lý focus khi chuyển sang bước kết quả.
- Giữ thông báo đủ lâu để người dùng đọc và thao tác bằng bàn phím.
- Dùng nhãn hành động nói rõ đích đến.
- Giữ ý nghĩa nhất quán giữa các bản dịch và các kênh thông báo.

Tránh tự chuyển trang quá nhanh khiến người dùng chưa đọc xong hướng dẫn. Nếu có chuyển tiếp tự động, cần có cách hiểu và kiểm soát phù hợp; hành động chủ động thường dễ dự đoán hơn ở bước này.

Trang kết quả không cần công bố toàn bộ hồ sơ tài khoản. Không đưa token hoặc mật khẩu vào URL, lịch sử trình duyệt hay mã phân tích. Chính sách cache và hiển thị dữ liệu cần phù hợp với tính nhạy cảm của trang, nhất là khi người dùng khôi phục trên máy mượn.

Nếu trang có thể được mở lại, kết quả hiển thị vẫn phải dựa trên quyền và trạng thái hiện tại. Một trang cũ còn trong lịch sử không được cấp lại quyền, mở lại token đã dùng hoặc làm xuất hiện bí mật đã kết thúc vòng đời.

## 9. Tình huống minh họa

Linh mất điện thoại chứa phương thức MFA và thực hiện khôi phục bằng bằng chứng dự phòng được chấp nhận. Sau xác minh, hệ thống yêu cầu thiết lập phương thức mới trước khi hoàn tất.

Khi Linh mới vượt qua bước bằng chứng, giao diện nói “Bạn có thể thiết lập phương thức mới”. Nó chưa dùng thông báo hoàn tất khôi phục.

Sau khi phương thức mới được đăng ký và các điều kiện bắt buộc đã đạt, trang cuối mô tả đúng kết quả: phương thức mới đã sẵn sàng, phương thức trên điện thoại báo mất đã bị thu hồi trong dịch vụ và Linh cần đăng nhập lại. Các phiên cũ chỉ được nói là đã thu hồi khi trạng thái máy chủ xác nhận.

Linh nhận thông báo độc lập với hướng dẫn “không phải tôi”. Trang cuối cung cấp một hành động chính rõ ràng là đến trang đăng nhập, còn hướng dẫn lưu phương thức dự phòng được đặt ở phần bổ sung thích hợp.

Nếu Linh quay lại trang khôi phục cũ, hệ thống không cho dùng lại token để thay đổi tiếp. Nếu phản hồi cuối bị mất, giao diện cung cấp lối xác định kết quả trong phạm vi quyền cho phép thay vì tự khẳng định thất bại rồi thực hiện lại.

Hướng dẫn hoàn tất giúp người dùng hiểu quyền truy cập đã được khôi phục đến đâu và cần làm gì tiếp theo. Sự rõ ràng đó phải đi cùng trạng thái đáng tin cậy, giới hạn phiên và thông báo độc lập để giảm nguy cơ chiếm đoạt tài khoản.
