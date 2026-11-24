# Failure message wording — Cách viết thông báo thất bại trong khôi phục tài khoản

## 1. Một thông báo lỗi cũng là một phần của luồng bảo mật

Khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, người dùng thường không biết họ còn cách nào để lấy lại tài khoản. Một thông báo thất bại có thể giúp họ chọn bước tiếp theo, hoặc khiến họ thử lặp lại, gửi bí mật cho hỗ trợ và tìm đến những đường dẫn không đáng tin.

Thông báo cũng có thể cung cấp thông tin cho người không có quyền:

- Một email có đăng ký tài khoản hay không.
- Tài khoản đang dùng phương thức MFA nào.
- Kênh khôi phục đã thay đổi hay đang bị giữ.
- Hệ thống đã phát hiện tín hiệu rủi ro nào.
- Một token có tồn tại, còn hạn hay đã được dùng.

**Failure message wording** là cách diễn đạt tình huống không thể tiếp tục hoặc chưa thể xác nhận kết quả, sao cho người dùng hiểu điều cần làm trong phạm vi thông tin họ được phép biết.

Ba mục tiêu cần giữ cùng nhau:

1. Phản ánh đúng điều hệ thống đã xác nhận.
2. Không tiết lộ dữ liệu ngoài phạm vi của người nhận.
3. Đưa ra bước tiếp theo thực sự có thể thực hiện.

Một câu chung chung như “Có lỗi xảy ra” thường thiếu hướng dẫn. Một câu quá chi tiết như “Email này có tài khoản nhưng đang bị giữ vì vừa thay MFA” lại có thể trở thành công cụ dò thông tin.

## 2. Xác định người nhận được phép biết gì trước khi viết câu

Không nên chọn nội dung chỉ theo mã lỗi kỹ thuật. Cùng một nguyên nhân có thể cần cách diễn đạt khác nhau ở những giai đoạn khác nhau.

| Bối cảnh | Điều hệ thống có thể biết | Giới hạn thông báo |
| --- | --- | --- |
| Người chưa được xác minh nhập email để bắt đầu | Request có đúng định dạng không; hệ thống có tiếp nhận được không | Không xác nhận sự tồn tại hoặc cấu hình tài khoản |
| Người đang ở một thử thách được cấp có phạm vi | Giao dịch và thao tác hiện tại có điều kiện nào đã được xác minh | Chỉ nói chi tiết phù hợp với phạm vi đó |
| Chủ tài khoản đã xác thực đủ cho một thao tác | Người nhận có quyền biết trạng thái liên quan đến thao tác | Có thể cụ thể hơn nhưng vẫn không lộ bí mật hoặc luật rủi ro |
| Nhân viên hỗ trợ hoặc vận hành | Có quyền nội bộ theo nhiệm vụ | Xem reason code và dữ liệu tối thiểu cần thiết, không mặc định xem mọi nội dung |

### 2.1. Có một token không có nghĩa được biết toàn bộ tài khoản

Một token khôi phục có thể cho phép mở một bước cụ thể. Nó không tự cho quyền xem mọi email dự phòng, danh sách passkey hoặc lịch sử MFA.

Thông báo tại bước đó phải dựa vào quyền mà máy chủ đã xác định. Không dùng tham số `verified=true` do client gửi để quyết định hiển thị chi tiết.

### 2.2. Không cần che những lỗi không liên quan đến dữ liệu tài khoản

Một trường bắt buộc đang để trống có thể được mô tả trực tiếp:

> Nhập địa chỉ email để tiếp tục.

Một địa chỉ sai định dạng có thể nhận:

> Kiểm tra định dạng địa chỉ email.

Những câu này mô tả dữ liệu người dùng vừa nhập và không cần tra cứu xem tài khoản có tồn tại hay không. Gom cả lỗi nhập liệu vào “Không thể thực hiện” có thể làm giao diện khó sử dụng mà không bảo vệ thêm thông tin cần thiết.

Điều cần phân biệt là lỗi của biểu mẫu với kết quả tra cứu tài khoản hoặc quyết định an ninh.

## 3. Cấu trúc một thông báo có ích

Một mẫu tư duy đơn giản là:

```text
Điều đang xảy ra
+ Giới hạn hoặc hệ quả đã biết, nếu người nhận được phép biết
+ Bước tiếp theo có thể thực hiện
```

Ví dụ trong một giao dịch có phạm vi phù hợp:

> Không thể dùng liên kết này để tiếp tục. Hãy bắt đầu một yêu cầu khôi phục mới.

Câu đầu cho biết trạng thái. Câu sau cho biết hành động. Không cần liệt kê liên kết sai, hết hạn, bị thu hồi hay đã dùng nếu những chi tiết đó không cần cho quyết định của người dùng.

### 3.1. Dùng động từ phản ánh đúng thao tác

Những thao tác này không giống nhau:

- Gửi yêu cầu khôi phục.
- Gửi một hướng dẫn đến kênh khôi phục.
- Xác minh một mã.
- Đặt lại mật khẩu.
- Thay phương thức MFA.
- Hoàn tất khôi phục.

Nếu chỉ gửi yêu cầu thất bại, không nên viết “Không thể đăng nhập” hoặc “Không thể đổi mật khẩu” như thể hệ thống đã đi đến những bước đó.

Tương tự, “Mã không được chấp nhận” không có nghĩa toàn bộ tài khoản bị khóa. Thông báo nên nói về lần thử hoặc bước hiện tại khi đó là phạm vi thực tế.

### 3.2. Bước tiếp theo phải được phép và có sẵn

Những gợi ý như “Dùng một phương thức khác” hoặc “Liên hệ hỗ trợ” chỉ có ích khi hệ thống thực sự có đường đi tương ứng.

Không đưa ra một đường tắt trái chính sách, chẳng hạn yêu cầu người dùng gửi OTP qua chat hoặc gửi khóa bí mật để nhân viên kiểm tra.

Nếu không còn bằng chứng phù hợp, hệ thống có thể cần giữ hoặc từ chối yêu cầu. Thông báo vẫn nên diễn đạt rõ trạng thái và đường xử lý có thật, thay vì hứa chắc rằng hỗ trợ sẽ mở được tài khoản.

## 4. Viết thông báo ở bước khởi tạo mà không làm lộ tài khoản

### 4.1. Tránh câu trả lời phân biệt tài khoản có và không tồn tại

Ví dụ dễ làm lộ thông tin:

> Không tìm thấy tài khoản với email này.

Nếu một email có tài khoản lại nhận “Đã gửi hướng dẫn”, hai câu trả lời cho phép người bên ngoài phân biệt danh sách email đã đăng ký.

Một cách diễn đạt có điều kiện có thể là:

> Nếu thông tin bạn cung cấp phù hợp với một tài khoản đủ điều kiện khôi phục, hệ thống sẽ xử lý việc gửi hướng dẫn qua kênh đã đăng ký. Hãy kiểm tra cả thư rác.

Câu này không xác nhận tài khoản tồn tại. Cũng cần tránh hiển thị địa chỉ khôi phục được lấy từ hồ sơ trước khi người nhận có quyền biết; một địa chỉ đã che một phần vẫn có thể tiết lộ thông tin mới.

### 4.2. Không khẳng định đã gửi hoặc đã nhận khi chưa có cơ sở

Các trạng thái sau khác nhau:

1. Máy chủ nhận request.
2. Hệ thống tiếp nhận công việc gửi thông báo.
3. Dịch vụ gửi chấp nhận xử lý.
4. Thư hoặc tin nhắn được chuyển đến nơi nhận.
5. Người dùng thực sự nhìn thấy nội dung.

Không dùng “Bạn đã nhận được email” chỉ vì công việc đã được đưa vào hàng đợi.

Nếu máy chủ chưa thể tiếp nhận yêu cầu do một sự cố chung, có thể dùng:

> Hiện chưa thể xử lý yêu cầu khôi phục. Vui lòng thử lại sau.

Nếu yêu cầu đã được tiếp nhận theo đúng ngữ nghĩa của hệ thống, có thể xác nhận điều đó; không nên suy ra thêm rằng việc khôi phục đã thành công.

### 4.3. Đồng nhất câu chữ chưa đủ để ngăn dò tìm

Hai response có cùng thông báo nhưng khác status code, trường dữ liệu, header hoặc dạng chuyển trang vẫn có thể làm lộ kết quả tra cứu.

Ví dụ, tránh một trường `accountFound: false` đi kèm câu chữ trung lập. Tương tự, một thời gian chờ chi tiết chỉ xuất hiện cho tài khoản tồn tại có thể trở thành tín hiệu.

Độ trễ cũng cần được xem xét ở cấp thiết kế. Chỉ sửa câu văn không giải quyết được mọi khác biệt thời gian hoặc hành vi gửi thông báo.

Điểm cốt lõi là thông điệp hiển thị và hợp đồng phản hồi phải cùng tôn trọng ranh giới thông tin. Không coi một câu trung lập là bằng chứng rằng toàn bộ endpoint đã an toàn.

## 5. Bảng thông báo cho các nhóm thất bại

Các mẫu dưới đây cần được đặt trong đúng bối cảnh. Chúng không phải câu trả lời dùng chung cho mọi endpoint.

| Tình huống | Mẫu thông báo | Bước tiếp theo hoặc điều kiện |
| --- | --- | --- |
| Thiếu dữ liệu bắt buộc | “Nhập địa chỉ email để tiếp tục.” | Đưa người dùng đến trường cần sửa |
| Dữ liệu sai định dạng | “Kiểm tra định dạng địa chỉ email.” | Cho sửa dữ liệu mà không tiết lộ kết quả tra cứu |
| Liên kết không thể tiếp tục | “Không thể dùng liên kết này để tiếp tục. Hãy bắt đầu yêu cầu khôi phục mới.” | Chỉ đề xuất tạo mới khi luồng thực sự hỗ trợ |
| Mã không được chấp nhận | “Không thể xác minh bằng mã này. Kiểm tra mã hoặc chọn cách khôi phục khác.” | Chỉ hiện lựa chọn thay thế đủ điều kiện và được phép công bố |
| Gửi lại quá sớm trong giao dịch đã xác định | “Chưa thể gửi lại lúc này. Hãy chờ đến thời điểm hiển thị.” | Thời điểm phải đến từ chính sách máy chủ và được phép hiển thị |
| Không đủ căn cứ để tiếp tục | “Chưa thể hoàn tất khôi phục với cách xác minh này.” | Kèm đường xử lý tiếp theo có thật nếu còn |
| Sự cố tạm thời trước khi thực hiện thay đổi | “Hiện chưa thể xử lý bước này. Vui lòng thử lại sau.” | Không ngụ ý thông tin xác thực đã được đổi |
| Chưa xác định được kết quả sau gián đoạn | “Chưa thể xác nhận kết quả lúc này.” | Hướng tới cơ chế kiểm tra trạng thái có kiểm soát, nếu có |

### 5.1. “Sai”, “hết hạn” và “đã dùng” có nên tách riêng?

Có thể tách khi người nhận có quyền biết trạng thái và sự phân biệt giúp họ chọn bước khác nhau. Ví dụ, một giao dịch đã được xác định có thể cho biết cần xin mã mới thay vì nhập lại mã cũ.

Ở bề mặt công khai, thông báo gộp có thể phù hợp hơn để tránh xác nhận tính tồn tại hoặc vòng đời của token.

Quyết định không nên chỉ dựa vào việc backend có ba mã lỗi. Cần xét người nhận, phạm vi giao dịch và lợi ích thực tế của việc công bố chi tiết.

### 5.2. Không làm lộ phương thức chưa được phép biết

Câu “Hãy dùng passkey còn lại trên máy tính của bạn” có thể tiết lộ cấu hình tài khoản nếu hệ thống chưa xác minh người đang xem.

Một lựa chọn thay thế chỉ nên được đưa ra khi có căn cứ để hiển thị. Có thể dùng nhãn chung như “Xem cách khôi phục khác” để dẫn đến một bước kiểm soát quyền phù hợp, thay vì công khai ngay danh sách phương thức.

## 6. Thông báo về giới hạn thử và thời gian chờ

### 6.1. Nói về khả năng thao tác hiện tại, tránh đe dọa

Cách diễn đạt dễ gây hiểu nhầm:

> Bạn đã làm tài khoản bị khóa.

Nếu hệ thống chỉ giữ một giao dịch hoặc tạm dừng gửi mã, câu này mô tả sai hậu quả và có thể khiến người dùng hoảng sợ.

Một câu có phạm vi rõ hơn:

> Chưa thể thử lại trong yêu cầu này. Bạn có thể tiếp tục sau thời điểm hiển thị.

Chỉ hiển thị thời điểm khi người nhận được phép biết và máy chủ thực sự xác định được mốc đó. Nếu hệ thống không có mốc đáng tin, không tự bịa “thử lại sau 15 phút”.

### 6.2. Không biến nội dung thông báo thành mô tả bộ chống lạm dụng

Những chi tiết như số lần còn lại trên một tài khoản chưa được xác minh, loại tín hiệu vừa kích hoạt hoặc điểm rủi ro có thể giúp người ngoài thăm dò.

Bên trong hệ thống có thể cần những dữ liệu này để giải thích và vận hành. Người dùng thường chỉ cần biết thao tác có thể thực hiện khi nào và lựa chọn hợp lệ nào còn lại.

### 6.3. Bắt đầu lại không tự khôi phục mọi ngân sách thử

Nếu thông báo hướng dẫn tạo một yêu cầu mới, backend vẫn phải áp dụng chính sách chống lạm dụng phù hợp. Câu hướng dẫn không được biến thành lời hứa rằng tạo giao dịch mới sẽ bỏ qua mọi thời gian chờ hoặc giới hạn của tài khoản.

Tương tự, đếm ngược trên trình duyệt chỉ là cách hiển thị. Quyết định có cho thử lại hay không phải do máy chủ thực thi.

## 7. Phân biệt thất bại đã xác nhận với kết quả chưa rõ

Một timeout trên trình duyệt không tự chứng minh thao tác đã thất bại ở máy chủ.

Ví dụ:

```text
1. Máy chủ thay mật khẩu và tiêu thụ token thành công.
2. Phản hồi bị gián đoạn trên đường về trình duyệt.
3. Trình duyệt chỉ thấy hết thời gian chờ.
```

Nếu giao diện viết “Mật khẩu chưa được thay đổi”, hệ thống đang khẳng định điều chưa biết. Nếu người dùng gửi lại rồi nhận “Token không hợp lệ”, họ có thể hiểu nhầm rằng lần đầu không thành công.

### 7.1. Thông báo phải phản ánh mức chắc chắn của kết quả

Có thể phân biệt ba nhóm:

| Trạng thái đã biết | Nội dung có thể nói | Hành động phù hợp |
| --- | --- | --- |
| Chưa thực hiện thay đổi và đã xác nhận thất bại | Chưa thể thực hiện bước đang yêu cầu | Cho thử lại theo điều kiện của luồng |
| Thay đổi đã hoàn tất và người nhận có quyền xem | Xác nhận đúng thao tác đã hoàn tất | Chuyển đến bước tiếp theo được phép |
| Không thể xác nhận kết quả từ trạng thái hiện có | Chưa thể xác nhận kết quả | Kiểm tra trạng thái hoặc dùng đường xử lý an toàn đã thiết kế |

Nếu sản phẩm có trang trạng thái giao dịch được kiểm soát quyền, một thông báo có thể là:

> Chưa thể xác nhận kết quả lúc này. Hãy kiểm tra trạng thái yêu cầu trước khi thử lại.

Không tạo một endpoint tra cứu công khai bằng email chỉ để hỗ trợ câu này. Quyền xem trạng thái vẫn phải gắn với giao dịch và người được phép.

Nếu sản phẩm chưa có cơ chế kiểm tra trạng thái, nội dung phải dựa vào đường xử lý thực tế. Không hiển thị một nút không hoạt động hoặc hướng dẫn người dùng lặp lại vô hạn.

### 7.2. Khả năng xử lý gửi lại phải đi cùng câu chữ

Một giao diện hướng dẫn “Thử lại” cần biết việc gửi lại có an toàn và có làm lặp thay đổi nhạy cảm hay không.

Ở phía máy chủ, việc nhận biết cùng một thao tác và trả lại trạng thái phù hợp có thể giúp tránh tạo lại credential, tiêu thụ nhiều quyền hoặc phát sinh nhiều yêu cầu hỗ trợ. Câu thông báo không thể thay thế cơ chế nhất quán này.

Nếu thao tác đã hoàn tất, một lỗi gửi lại không nên khiến giao diện bỏ qua trạng thái hoàn tất đã được xác nhận và tiếp tục khẳng định thất bại.

## 8. Diễn đạt quyết định giữ hoặc từ chối khôi phục

### 8.1. Không kết tội người dùng bằng một tín hiệu rủi ro

Câu như:

> Bạn bị phát hiện gian lận vì dùng thiết bị lạ.

vừa có thể mô tả sai, vừa tiết lộ điều kiện của bộ đánh giá. Chủ tài khoản thật sau khi mất thiết bị rất có thể đang dùng một thiết bị mới.

Một cách nói theo trạng thái:

> Chưa thể hoàn tất khôi phục bằng cách xác minh này.

Nếu có bước tiếp theo phù hợp, thêm hành động đó. Nếu không có, cần mô tả giới hạn thực tế mà không hứa rằng chỉ cần gửi thêm thông tin là chắc chắn được chấp nhận.

### 8.2. Phân biệt chờ xem xét với bị từ chối

“Yêu cầu đang được xem xét” chỉ nên xuất hiện khi thật sự có một quy trình tiếp nhận và xử lý yêu cầu.

Không dùng câu này để che một quyết định đã kết thúc hoặc một sự cố chưa có công việc nào được tạo. Người dùng có thể chờ mãi vì tin rằng hồ sơ vẫn đang được xử lý.

Tương tự, không hứa “Chúng tôi sẽ phản hồi trong một giờ” nếu hệ thống không có cam kết tương ứng và cách thông báo khi không đáp ứng được.

Khi có mốc thời gian đáng tin, có thể hiển thị theo giờ địa phương phù hợp và giải thích mốc đó là lúc có thể thử lại hay dự kiến có cập nhật. Hai mốc này không có cùng ý nghĩa.

### 8.3. Giải thích vừa đủ cho người có quyền

Sau khi xác minh phù hợp, một số lý do tổng quát có thể giúp người dùng hiểu vì sao cần thêm bước, chẳng hạn phương thức đang chọn không còn đủ điều kiện cho thao tác này.

Nhưng không cần công khai điểm rủi ro, ngưỡng, danh sách tín hiệu hoặc cách tránh điều kiện chặn. Phân biệt giải thích trạng thái của luồng với mô tả chi tiết cách hệ thống phát hiện lạm dụng.

## 9. Ví dụ xuyên suốt: người dùng mất điện thoại và gặp nhiều lỗi

Giả sử Lan mất điện thoại có ứng dụng MFA. Sản phẩm có luồng khôi phục với một liên kết gửi qua kênh đủ điều kiện và, ở một số trường hợp, một phương thức bổ sung đã đăng ký từ trước.

### Bước 1: Nhập sai định dạng email

Thông báo:

> Kiểm tra định dạng địa chỉ email.

Giao diện đặt nội dung cạnh trường liên quan, cho phép sửa dữ liệu và không tra cứu tài khoản để quyết định lỗi định dạng.

### Bước 2: Gửi yêu cầu với địa chỉ có định dạng phù hợp

Bề mặt công khai dùng thông điệp có điều kiện. Nó không xác nhận tài khoản của địa chỉ đó có tồn tại và không tự hiển thị một số điện thoại được lấy từ hồ sơ.

Nếu hệ thống không tiếp nhận được request vì sự cố chung, thông báo nói chưa thể xử lý yêu cầu thay vì khẳng định đã gửi hướng dẫn.

### Bước 3: Mở liên kết không thể sử dụng

Thông báo:

> Không thể dùng liên kết này để tiếp tục. Hãy bắt đầu một yêu cầu khôi phục mới.

Câu này không phân biệt công khai mọi nguyên nhân của token. Việc tạo yêu cầu mới vẫn chịu giới hạn chống lạm dụng của hệ thống.

### Bước 4: Không hoàn thành được cách xác minh bổ sung

Thông báo trong phạm vi giao dịch:

> Không thể xác minh bằng cách này. Bạn có thể xem lựa chọn khôi phục khác.

Chỉ dùng câu thứ hai nếu sản phẩm có lựa chọn phù hợp và được phép hiển thị. Không tự gợi ý gửi OTP, khóa bí mật hay recovery code cho nhân viên hỗ trợ.

### Bước 5: Gián đoạn sau khi gửi thay đổi cuối cùng

Giao diện chưa có kết quả chắc chắn nên không viết “Khôi phục đã thất bại” như một kết luận cuối cùng. Nếu có cơ chế trạng thái được kiểm soát quyền, nó hướng Lan đến đó.

Sau khi máy chủ xác nhận thay đổi đã hoàn tất, giao diện hiển thị kết quả tương ứng và bước đăng nhập hoặc xác thực tiếp theo theo đúng thiết kế. Nó không tự cấp thêm quyền chỉ để làm thông báo trở nên thuận tiện.

Ví dụ cho thấy “an toàn” không đồng nghĩa mọi bước phải dùng cùng một câu. Mỗi thông báo phản ánh dữ liệu được phép công bố và mức chắc chắn của giai đoạn hiện tại.

## 10. Tách nguyên nhân nội bộ khỏi nội dung công khai

### 10.1. Một nguyên nhân có thể ánh xạ sang nhiều thông báo theo ngữ cảnh

Ví dụ mô tả nội bộ:

```text
internalReason: RECOVERY_CONTACT_RECENTLY_CHANGED
transactionState: ADDITIONAL_VERIFICATION_REQUIRED
allowedDisclosure: SCOPED_RECOVERY
publicMessageKey: RECOVERY_CANNOT_CONTINUE_WITH_THIS_METHOD
allowedActions:
  - VIEW_ELIGIBLE_ALTERNATIVES
```

Nguyên nhân nội bộ giúp bộ quyết định và người có quyền hiểu tình huống. Nội dung công khai chỉ nói điều người dùng cần để tiếp tục.

Tên khóa trong ví dụ là dữ liệu thiết kế nội bộ; không nên biến chính tên reason code thành câu hiển thị.

### 10.2. Máy chủ quyết định phạm vi, client diễn đạt đúng hợp đồng

Mã giả minh họa:

```text
buildRecoveryFailure(result, serverVerifiedContext):
    disclosure = determineAllowedDisclosure(serverVerifiedContext)

    messageKey = selectMessage(
        result.publicOutcomeClass,
        disclosure
    )

    actions = selectAllowedActions(
        result.transactionState,
        serverVerifiedContext
    )

    return {
        messageKey,
        safeParametersFor(messageKey, disclosure),
        actions
    }
```

Các tham số hiển thị cần có danh sách được phép. Không đưa nguyên exception, dữ liệu hồ sơ hoặc reason object vào response rồi trông chờ giao diện chỉ dùng một phần.

Một mã tham chiếu hỗ trợ có thể giúp truy vết mà không công khai nguyên nhân. Mã đó không nên là token có quyền khôi phục và không tự cho phép tra cứu hồ sơ qua một trang công khai.

### 10.3. Giao diện không tự suy ra nguyên nhân khi thiếu dữ liệu

Không nên ánh xạ mọi lỗi mạng sang “Mã đã hết hạn”. Một lỗi mạng chỉ cho biết giao diện chưa nhận được kết quả tương ứng.

Tương tự, không hiển thị “Tài khoản bị khóa” chỉ vì nhận một mã HTTP được dùng chung cho nhiều tình huống. Hợp đồng cần phân biệt những lớp kết quả công khai mà giao diện được phép diễn đạt.

Nhật ký nội bộ có thể giữ reason code, trạng thái và mã giao dịch theo quyền truy cập phù hợp. Không ghi token, OTP, recovery code hoặc thông tin xác thực nguyên văn để giải thích một thông báo thất bại.

## 11. Viết cho người đang căng thẳng và dùng nhiều loại thiết bị

### 11.1. Giữ giọng điệu bình tĩnh và không quy lỗi

Những câu như “Bạn nhập sai quá nhiều lần” hoặc “Bạn đã làm hệ thống nghi ngờ” thường nhấn vào sự trách móc hơn là hành động cần thiết.

Có thể tập trung vào trạng thái:

> Chưa thể xác minh mã này. Kiểm tra lại mã trước khi tiếp tục.

Hoặc, khi cần chờ:

> Chưa thể thử lại lúc này. Hãy chờ đến thời điểm hiển thị.

Không cần xin lỗi nhiều lần hoặc dùng lời trấn an không có cơ sở như “Tài khoản của bạn chắc chắn an toàn” khi hệ thống chưa xác định được điều đó.

### 11.2. Hỗ trợ việc đọc và thao tác

Một thông báo cần có thể hiểu bằng văn bản, không chỉ bằng màu đỏ hoặc một biểu tượng.

Một số yêu cầu thiết kế có ích:

- Liên kết lỗi với đúng trường nhập khi đó là lỗi của trường.
- Cho người dùng bàn phím và công nghệ hỗ trợ nhận biết thông báo mới ở thời điểm phù hợp.
- Giữ thông báo đủ lâu để đọc và thực hiện hành động.
- Dùng nhãn nút cụ thể như “Bắt đầu yêu cầu mới” thay vì chỉ “OK”.
- Tránh đọc lại đồng hồ đếm ngược mỗi giây theo cách gây gián đoạn.
- Không tự xóa mọi dữ liệu đã nhập khi chỉ một trường cần sửa.

Bí mật xác thực vẫn phải tuân theo cách xử lý riêng của luồng. Việc giữ dữ liệu nhập không có nghĩa lưu OTP, token hoặc mật khẩu vào log, analytics hay ghi chú hỗ trợ.

### 11.3. Bản dịch phải giữ nguyên ý nghĩa bảo mật

Bản dịch có thể vô tình chuyển câu có điều kiện thành khẳng định chắc chắn:

- Câu gốc: “Nếu yêu cầu đủ điều kiện, hướng dẫn sẽ được xử lý gửi.”
- Bản dịch sai ý: “Tài khoản tồn tại và email đã được gửi.”

Cần giữ ổn định các ý nghĩa: điều kiện, phạm vi, mức chắc chắn, trạng thái chờ và hành động được phép.

Thời điểm chờ nên được hiển thị theo định dạng dễ hiểu và múi giờ phù hợp. Thông báo “thử lại lúc 08:00” thiếu ngữ cảnh có thể khiến người dùng hiểu sai ngày hoặc giờ.

Các thuật ngữ “đăng nhập”, “đặt lại mật khẩu”, “thay MFA” và “khôi phục tài khoản” cũng cần dùng nhất quán; chúng không phải các cách gọi thay thế cho cùng một thao tác.

## 12. Giữ thông điệp nhất quán giữa các kênh

Một giao diện có câu trung lập nhưng email, SMS hoặc hội thoại hỗ trợ lại công khai thông tin khác vẫn có thể làm mất ranh giới riêng tư.

Cần xác định người nhận và mục đích của từng kênh:

- Phản hồi công khai cho người đang gửi yêu cầu.
- Hướng dẫn được gửi tới một kênh đã được chọn theo chính sách.
- Cảnh báo an ninh cho người có quyền nhận.
- Thông tin xử lý dành cho nhân viên được giao hồ sơ.

Những nội dung này không nhất thiết giống nhau, vì quyền biết có thể khác nhau. Nhưng chúng phải cùng phản ánh trạng thái thật.

Ví dụ, nếu giao dịch chỉ đang chờ xác minh, một kênh không nên nói “đã hoàn tất khôi phục”. Nếu chưa có quy trình xem xét nào được tạo, nhân viên hỗ trợ cũng không nên nói “hồ sơ đang được xử lý” chỉ vì giao diện dùng câu đó.

Đường dẫn hành động trong thông báo cần đi vào luồng chính thức của sản phẩm. Không hướng dẫn người dùng cung cấp bí mật qua một kênh khác để vượt qua lỗi của giao diện.

Khi thông báo vẫn khiến người dùng liên tục thử lại hoặc liên hệ sai nơi, có thể xem các chỉ số tổng hợp về bước dừng, lần gửi lặp và nhu cầu hỗ trợ để cải thiện cách diễn đạt. Việc theo dõi không cần thu toàn bộ mã người dùng nhập hoặc nội dung nhạy cảm của giao dịch.

## 13. Những lỗi diễn đạt thường gặp

| Lỗi | Hệ quả | Hướng diễn đạt hoặc thiết kế |
| --- | --- | --- |
| “Không có tài khoản với email này” ở bước công khai | Làm lộ sự tồn tại tài khoản | Dùng phản hồi có điều kiện phù hợp với trạng thái tiếp nhận |
| “Email đã được giao tới hộp thư” khi mới xếp hàng | Khẳng định vượt dữ liệu đã biết | Chỉ xác nhận trạng thái thực tế |
| “Tài khoản bị khóa” khi chỉ giao dịch bị giữ | Gây hiểu nhầm và hoảng sợ | Nêu đúng phạm vi thao tác đang bị giới hạn |
| Hiển thị exception hoặc reason code | Lộ thông tin nội bộ và khó hiểu | Ánh xạ sang lớp kết quả công khai |
| “Thử lại sau 15 phút” không dựa vào máy chủ | Tạo hướng dẫn không đáng tin | Dùng mốc thật được phép hiển thị hoặc hướng dẫn không bịa thời gian |
| “Bạn gian lận vì thiết bị lạ” | Kết tội sai và lộ tín hiệu rủi ro | Diễn đạt trạng thái của cách xác minh |
| Mọi timeout đều nói thao tác thất bại | Sai khi thay đổi đã hoàn tất | Phân biệt kết quả chưa rõ với thất bại đã xác nhận |
| “Liên hệ hỗ trợ để mở khóa ngay” khi không có khả năng đó | Tạo kỳ vọng và đường xử lý không thật | Chỉ mô tả hỗ trợ có sẵn cùng giới hạn thực tế |
| Câu trung lập nhưng payload có trạng thái tài khoản | Ranh giới bảo mật vẫn bị phá | Đồng bộ nội dung với hợp đồng phản hồi |
| Chỉ hiện màu hoặc toast biến mất nhanh | Người dùng khó nhận biết và sửa lỗi | Có văn bản, ngữ cảnh và hành động rõ ràng |

## 14. Điểm cần ghi nhớ

Một thông báo thất bại tốt cho biết điều hệ thống thực sự biết, ở mức người nhận được phép biết, rồi hướng họ đến bước hợp lệ tiếp theo. Nó không cần công khai nguyên nhân bảo mật chi tiết để trở nên hữu ích.

Hãy phân biệt lỗi nhập liệu, quyết định không cho tiếp tục, giới hạn tạm thời, sự cố hệ thống và kết quả chưa xác định. Câu chữ cần đi cùng phạm vi giao dịch, hợp đồng API và trạng thái máy chủ; nếu những phần này không thống nhất, một câu văn dễ hiểu vẫn có thể làm lộ thông tin hoặc dẫn người dùng đi sai đường.
