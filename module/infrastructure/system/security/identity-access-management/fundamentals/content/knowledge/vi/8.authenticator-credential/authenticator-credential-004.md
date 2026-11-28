# Possession factor

Khi hệ thống yêu cầu người dùng xác nhận bằng khóa bảo mật, ứng dụng tạo mã hoặc thiết bị chứa khóa riêng, nó đang tìm bằng chứng cho possession factor: yếu tố dựa trên thứ người dùng đang kiểm soát. Ý tưởng quen thuộc là “thứ bạn có”, nhưng trong hệ thống số, máy chủ thường không nhìn thấy vật thể. Máy chủ kiểm tra một bằng chứng được tạo ra từ bí mật hoặc khóa gắn với authenticator đã đăng ký.

Hiểu đúng yếu tố này giúp phân biệt một thiết bị được khai báo với một authenticator thực sự, đánh giá MFA và thiết kế vòng đời credential. Có thêm điện thoại hoặc thêm một mã xác nhận không tự động làm mọi quy trình đăng nhập an toàn như nhau.

## 1. Possession factor chứng minh điều gì?

Possession factor dựa trên khả năng sử dụng một authenticator mà chủ thể đang nắm quyền kiểm soát. Authenticator có thể là thiết bị chuyên dụng, phần mềm trên điện thoại, thẻ chứa khóa hoặc một cơ chế giữ khóa mật mã trong thiết bị.

Ví dụ, người dùng đã đăng ký khóa công khai với dịch vụ. Khi đăng nhập, dịch vụ đưa ra một thử thách mới. Authenticator dùng khóa riêng tương ứng để tạo phản hồi mật mã mà dịch vụ có thể kiểm tra. Biết username hoặc khóa công khai không đủ để tạo phản hồi đó.

Bằng chứng này cho biết bên thực hiện có khả năng dùng khóa hoặc bí mật được chấp nhận tại thời điểm xác thực. Nó không tự chứng minh:

- Người thực hiện là chủ sở hữu hợp pháp của thiết bị.
- Thiết bị chưa bị đánh cắp, điều khiển từ xa hoặc nhiễm mã độc.
- Khóa hoặc bí mật chưa từng bị sao chép.
- Người thực hiện có quyền đọc dữ liệu hay thực hiện thao tác quản trị.
- Mọi yêu cầu sau đăng nhập đều do chính người đó trực tiếp thực hiện.

Vì vậy, possession là một phần của xác thực, không phải kết luận đầy đủ về danh tính, trạng thái thiết bị hoặc quyền truy cập. Sau khi xác thực, ứng dụng vẫn cần kiểm tra session, role, scope và điều kiện của từng hành động.

## 2. Phân biệt vật thể, authenticator và credential

Điện thoại là một vật thể. Ứng dụng hoặc bộ phận giữ khóa trên điện thoại có thể đóng vai trò authenticator. Dữ liệu được đăng ký để liên kết authenticator với tài khoản thuộc về credential hoặc hồ sơ credential của cơ chế tương ứng.

Ba lớp này không luôn có quan hệ một–một. Một điện thoại có thể chứa credential của nhiều dịch vụ; một tài khoản có thể đăng ký nhiều authenticator. Nếu bí mật của ứng dụng tạo mã được sao chép sang máy khác, cùng một credential có thể được sử dụng từ nhiều nơi.

| Thành phần | Ví dụ | Có đủ làm bằng chứng possession không? |
|---|---|---|
| Tên thiết bị | “Điện thoại cá nhân của An” | Không; đây là nhãn do người dùng đặt |
| Device ID gửi trong request | Chuỗi nhận diện cài đặt ứng dụng | Không nếu chỉ là giá trị có thể sao chép hoặc giả mạo |
| Credential ID | Định danh giúp máy chủ tìm khóa đã đăng ký | Không; nó không phải khóa bí mật |
| Khóa công khai | Dữ liệu để kiểm tra chữ ký | Không; chủ đích là có thể công khai |
| Mã OTP hợp lệ | Phản hồi được tạo từ bí mật hoặc nhận qua kênh đã liên kết | Là bằng chứng theo cơ chế đó, với giới hạn tương ứng |
| Phản hồi mật mã hợp lệ | Chữ ký trên dữ liệu của một lần xác thực | Là bằng chứng kiểm soát khóa khi được kiểm tra đầy đủ |

Không được chuyển trực tiếp từ “request có device ID đã biết” sang “người dùng đã chứng minh possession”. Device ID có thể giúp tra cứu hoặc đánh giá rủi ro, nhưng phải có cơ chế xác minh việc kiểm soát authenticator tương ứng.

## 3. Đặt possession trong mô hình các yếu tố xác thực

Ba nhóm quen thuộc là knowledge, possession và inherence:

| Nhóm | Câu hỏi khái niệm | Ví dụ |
|---|---|---|
| Knowledge | Chủ thể biết bí mật gì? | Mật khẩu hoặc PIN được kiểm tra theo cơ chế xác thực |
| Possession | Chủ thể kiểm soát authenticator nào? | Khóa bảo mật, ứng dụng giữ bí mật OTP, thiết bị chứa khóa riêng |
| Inherence | Có đặc điểm sinh trắc nào được xác minh? | Vân tay hoặc khuôn mặt trong một cơ chế hỗ trợ |

Mật khẩu cộng một câu hỏi bí mật vẫn thuộc cùng nhóm knowledge. Hai mã OTP từ hai ứng dụng không mặc nhiên tạo ra hai nhóm yếu tố khác nhau. Ngược lại, một authenticator có thể yêu cầu PIN hoặc sinh trắc để cho phép sử dụng khóa, kết hợp kiểm soát authenticator với xác minh người dùng tại thiết bị.

Muốn kết luận một luồng có nhiều yếu tố, phải xem yếu tố nào thực sự được cơ chế bắt buộc kiểm tra, và máy chủ dựa vào bằng chứng nào để chấp nhận kết quả. Không thể chỉ đếm số màn hình, số ứng dụng hoặc số lần bấm nút.

Ví dụ, chạm vào khóa có thể chỉ xác nhận có người hiện diện và đồng ý tương tác. Điều đó khác với authenticator đã kiểm tra PIN hoặc sinh trắc của người dùng. Giao diện hiển thị hình dấu vân tay cũng chưa đủ; dịch vụ phải xác minh kết quả theo khả năng và chính sách của cơ chế sử dụng.

## 4. Các cơ chế possession thường gặp

Các cơ chế sau có điểm chung là dựa vào quyền kiểm soát một thứ đã được liên kết với tài khoản, nhưng cách tạo bằng chứng và rủi ro khác nhau:

| Cơ chế | Bằng chứng máy chủ nhận | Điểm cần hiểu |
|---|---|---|
| Token OTP phần cứng | Mã dùng một lần theo bộ đếm hoặc thời gian | Thiết bị giữ bí mật; mã vẫn có thể bị người dùng nhập vào trang giả |
| Ứng dụng OTP | Mã tạo từ bí mật trong ứng dụng | Sao chép seed có thể tạo một bản sao cũng sinh được mã hợp lệ |
| Mã qua SMS | Mã gửi tới số điện thoại đã liên kết | Chứng minh khả năng nhận mã qua kênh đó, không trực tiếp chứng minh đang cầm đúng máy vật lý |
| Phê duyệt qua ứng dụng | Phản hồi cho một yêu cầu xác thực | Cần chống nhầm yêu cầu, phát lại và phê duyệt do bị thúc ép |
| Thẻ hoặc khóa mật mã | Phản hồi dùng khóa riêng | Cần kiểm tra toàn bộ giao thức và cách bảo vệ khóa |
| Credential kiểu passkey | Phản hồi mật mã từ authenticator | Có thể gắn một thiết bị hoặc được đồng bộ; thuộc tính bảo vệ phụ thuộc cách triển khai |

Không phải mọi chữ ký bằng khóa riêng đều tự động chống phishing. Khả năng đó còn phụ thuộc việc bằng chứng được ràng buộc với dịch vụ và ngữ cảnh xác thực như thế nào, cùng cách máy chủ kiểm tra ràng buộc ấy.

Tương tự, không phải mọi khóa riêng đều nằm trong phần cứng không xuất được. Khóa lưu trong file có thể được sao chép; khóa được bảo vệ trong phần cứng có đặc tính khác; khóa được đồng bộ có thêm ranh giới tin cậy ở hệ thống đồng bộ và khôi phục. Khi đánh giá, cần nêu đúng cơ chế thay vì chỉ ghi “dùng thiết bị”.

## 5. OTP chứng minh quyền kiểm soát bí mật ra sao?

Với OTP dựa trên bí mật chung, authenticator và bên xác minh có dữ liệu cần thiết để tạo hoặc kiểm tra mã. Hai cách phổ biến dùng bộ đếm hoặc thời gian làm đầu vào thay đổi.

Mô hình khái niệm:

```text
Authenticator: mã = hàm_mật_mã(bí_mật, đầu_vào_thay_đổi)
Máy chủ:      kiểm tra mã theo bí mật và trạng thái tương ứng
```

Với OTP theo thời gian, đầu vào thay đổi được xác định từ một khoảng thời gian. Máy chủ có thể cho phép độ lệch đồng hồ trong giới hạn. Với OTP theo bộ đếm, máy chủ cần quản lý trạng thái bộ đếm và việc đồng bộ theo thiết kế.

Các điều kiện vận hành quan trọng gồm:

- Bí mật ban đầu phải được sinh bằng nguồn ngẫu nhiên phù hợp và cấp phát qua luồng được bảo vệ.
- Bí mật và dữ liệu đăng ký như mã QR không được xuất hiện trong log, ảnh hỗ trợ hoặc công cụ phân tích.
- Máy chủ phải giới hạn số lần thử, kiểm tra thời hạn và xử lý việc dùng lại mã theo cơ chế.
- Việc ghi nhận mã đã sử dụng cần chịu được yêu cầu đồng thời; hai request không được cùng vượt qua kiểm tra một lần sử dụng do cập nhật trạng thái quá muộn.
- Cửa sổ thời gian được chấp nhận không nên mở rộng tùy tiện để che lỗi đồng hồ hoặc lỗi triển khai.

Một mã ngắn có không gian đoán hạn chế. Giới hạn tốc độ, theo dõi thất bại và liên kết mã với đúng tài khoản hoặc giao dịch là thành phần cần thiết, không phải phần bổ sung chỉ dành cho hệ thống lớn.

Bí mật OTP có thể cần được dùng lại để tính giá trị kỳ vọng, nên không thể mặc định lưu giống một hash mật khẩu rồi cho rằng việc xác minh sẽ hoạt động tương tự. Cần cơ chế bảo vệ bí mật tại nơi lưu trữ và nơi sử dụng, giới hạn quyền truy cập, cùng kế hoạch xử lý khi dữ liệu xác minh bị lộ.

Nếu seed được sao chép, người có bản sao có thể tạo mã hợp lệ mà không cần điện thoại ban đầu. Vì vậy bằng chứng là quyền kiểm soát bí mật theo cơ chế, không phải chứng minh duy nhất rằng một vật thể cụ thể đang ở trong tay người dùng.

## 6. Challenge–response bằng khóa bất đối xứng

Với cơ chế dùng khóa bất đối xứng, authenticator giữ khóa riêng và dịch vụ lưu dữ liệu xác minh, thường bao gồm khóa công khai. Dịch vụ tạo một challenge mới; authenticator tạo phản hồi mật mã; dịch vụ xác minh bằng khóa đã đăng ký.

Luồng khái niệm:

```text
1. Dịch vụ tạo challenge mới và gắn với giao dịch xác thực.
2. Authenticator nhận yêu cầu trong ngữ cảnh của dịch vụ.
3. Authenticator thực hiện tương tác hoặc xác minh người dùng nếu chính sách yêu cầu.
4. Authenticator tạo phản hồi mật mã trên dữ liệu của giao thức.
5. Dịch vụ kiểm tra phản hồi và tiêu thụ challenge đúng một lần.
```

Không nên mô tả mọi triển khai như chỉ “ký một chuỗi ngẫu nhiên”. Dữ liệu được ký và được kiểm tra có thể bao gồm thông tin về dịch vụ, nguồn yêu cầu, trạng thái authenticator hoặc các trường khác của giao thức. Bỏ qua một trường bắt buộc có thể làm mất đặc tính bảo mật mà người thiết kế đang dựa vào.

Ở mức kiến trúc, máy chủ cần kiểm tra:

- Credential đang hoạt động và thuộc tài khoản hoặc ngữ cảnh định danh phù hợp.
- Challenge khớp với lần xác thực đang chờ, còn hạn và chưa được dùng thành công.
- Chữ ký và dữ liệu phản hồi hợp lệ theo giao thức, thuật toán và khóa được chấp nhận.
- Thông tin ràng buộc dịch vụ hoặc nguồn yêu cầu khớp cấu hình tin cậy khi cơ chế có các ràng buộc đó.
- Các điều kiện về hiện diện hoặc xác minh người dùng thỏa mãn chính sách.
- Không có thay đổi trạng thái thu hồi hoặc khóa tài khoản làm lần xác thực không còn được phép.

Không lấy địa chỉ dịch vụ kỳ vọng từ một giá trị tùy ý do client gửi rồi dùng chính giá trị đó để xác minh. Giá trị kỳ vọng phải đến từ cấu hình và ngữ cảnh server tin cậy.

Việc tiêu thụ challenge cần được thực hiện nguyên tử để ngăn hai request đồng thời dùng cùng một phản hồi thành công. Đồng thời, không nên để một phản hồi không hợp lệ tùy ý hủy mọi challenge hợp lệ của người khác; trạng thái phải gắn với đúng giao dịch và có kiểm soát chống lạm dụng.

Lợi ích của mô hình bất đối xứng là cơ sở dữ liệu chứa khóa công khai không cung cấp trực tiếp khả năng ký như khóa riêng. Tuy vậy, nếu kẻ tấn công có thể sửa việc liên kết tài khoản với khóa hoặc chiếm luồng đăng ký, họ có thể thêm khóa của mình. Bảo vệ đăng ký credential vẫn là yêu cầu cốt lõi.

## 7. Vì sao mã hợp lệ vẫn có thể bị phishing?

Giả sử người dùng mở một trang đăng nhập giả. Trang đó lấy mật khẩu và yêu cầu mã từ ứng dụng OTP. Khi người dùng nhập mã, kẻ tấn công chuyển ngay thông tin sang dịch vụ thật trong lúc mã còn hiệu lực.

Máy chủ nhận được mã hợp lệ, nhưng người dùng đã tương tác với sai nơi. OTP có thời hạn ngắn giúp hạn chế thời gian sử dụng; nó không tự gắn mã với đúng website mà người dùng đang nhìn thấy. Đây là lý do cần phân biệt khả năng chống phát lại với khả năng chống chuyển tiếp trong thời gian thực.

Các cơ chế mật mã có ràng buộc dịch vụ được kiểm tra đầy đủ có thể bảo vệ tốt hơn trước lớp tấn công này. Tuy nhiên, cần xem cả chuỗi đăng ký, đăng nhập, khôi phục và quản lý phiên. Một hệ thống dùng authenticator mạnh nhưng cho phép thay thế nó qua một luồng khôi phục yếu vẫn có đường vòng để chiếm tài khoản.

Với SMS, còn có rủi ro người khác kiểm soát việc nhận tin nhắn do thay SIM, chuyển số, thiết bị bị truy cập hoặc hạ tầng chuyển tiếp. Số điện thoại cũng có thể được cấp lại. Bởi vậy thay đổi số điện thoại cần được coi là thay đổi liên kết authenticator, không chỉ là sửa một trường hồ sơ liên lạc.

## 8. Push approval và sự đồng ý có ngữ cảnh

Một thông báo “Có phải bạn đang đăng nhập?” có thể khiến người dùng bấm đồng ý theo thói quen. Nếu liên tục nhận yêu cầu, họ có thể chấp nhận để ngừng bị làm phiền. Nếu hiển thị thiếu ngữ cảnh, người dùng cũng có thể nhầm yêu cầu của kẻ tấn công với thao tác mình đang làm.

Thiết kế cần liên kết phê duyệt với một giao dịch cụ thể, có thời hạn và chỉ dùng một lần. Có thể bổ sung bước so khớp thông tin hiển thị giữa hai phía, cùng chi tiết đủ để người dùng nhận biết yêu cầu. Các biện pháp này giúp giảm nhầm lẫn; không nên tự tuyên bố mọi luồng push đã trở thành chống phishing.

Backend phải xác minh phản hồi từ authenticator hoặc kênh được đăng ký, kiểm tra trạng thái giao dịch và từ chối phản hồi sai tài khoản. Không chấp nhận một request kiểu sau như bằng chứng xác thực:

```json
{
  "userId": "user-42",
  "deviceId": "known-device",
  "approved": true
}
```

Nếu chỉ cần gửi ba trường trên qua một API không có cơ chế chứng minh phù hợp, bất kỳ client nào biết định danh cũng có thể giả mạo phê duyệt. Việc request đến từ “ứng dụng chính thức” không thay thế kiểm tra mật mã và ngữ cảnh phía server.

## 9. User presence và user verification

User presence thể hiện có một tương tác theo cơ chế của authenticator, chẳng hạn chạm vào thiết bị. User verification thể hiện authenticator đã thực hiện một bước kiểm tra người dùng, chẳng hạn PIN hoặc sinh trắc, theo khả năng của nó.

Một người nhặt được khóa và chạm vào nó có thể tạo ra sự hiện diện; điều này không giống chứng minh họ biết PIN đã bảo vệ khóa. Vì vậy hai khái niệm cần được phân biệt trong chính sách và trong dữ liệu xác minh.

Với một số cơ chế, PIN hoặc sinh trắc được kiểm tra tại authenticator để mở quyền sử dụng khóa, thay vì gửi nguyên bí mật hoặc mẫu sinh trắc tới dịch vụ. Dịch vụ dựa vào kết quả được bảo vệ của giao thức. Không được suy từ mô hình này rằng mọi ứng dụng dùng màn hình khóa đều cung cấp cùng mức bằng chứng cho máy chủ.

Đối với thao tác nhạy cảm, dịch vụ cần xác định rõ có yêu cầu xác minh người dùng hay không, kết quả nào phải được kiểm tra và khi nào cần xác thực lại. Không tin một trường `userVerified=true` do phần mềm client tùy ý tự khai báo.

## 10. Thiết bị bị mất, bí mật bị sao chép và khóa được đồng bộ

Mất thiết bị không phải rủi ro duy nhất của possession factor. Ba tình huống khác nhau dẫn đến cách xử lý khác nhau:

| Tình huống | Vấn đề chính | Hướng xử lý ở cấp IAM |
|---|---|---|
| Mất authenticator vật lý | Người khác có thể thử sử dụng thiết bị; chủ tài khoản mất khả năng đăng nhập | Xác minh qua đường dự phòng, thu hồi credential liên quan, đăng ký thay thế an toàn |
| Bí mật hoặc khóa bị sao chép | Nhiều bên có thể tạo bằng chứng được chấp nhận | Thu hồi liên kết cũ và cấp credential mới theo quy trình phù hợp |
| Credential được đồng bộ hợp lệ | Có nhiều bản sao trong mô hình đã thiết kế | Hiểu ranh giới đồng bộ, khôi phục và phạm vi của thao tác thu hồi |

Credential được đồng bộ không đồng nghĩa một kẻ tấn công đã sao chép trái phép, nhưng nó làm thay đổi ý nghĩa của “gắn với thiết bị”. Không nên dùng một sự kiện xác thực để khẳng định người dùng đang sử dụng đúng một máy vật lý nếu cơ chế cho phép nhiều bản sao.

Đối với dữ liệu giữ trong phần cứng, tính không xuất khóa và cơ chế chống sử dụng trái phép cần được đánh giá riêng. Sự hiện diện của một chip không tự chứng minh toàn bộ đường đăng ký, ứng dụng, hệ điều hành và khôi phục đều đáng tin cậy.

Khi thu hồi, dịch vụ cần làm mất hiệu lực credential trong hồ sơ xác minh của mình. Việc xóa một bản sao trên một thiết bị không chứng minh rằng mọi bản sao khác đã biến mất. Ngược lại, thu hồi credential tại dịch vụ không đồng nghĩa đã xóa bí mật từ mọi thiết bị; nó chặn việc dịch vụ tiếp tục chấp nhận credential đó theo chính sách.

## 11. Vòng đời đăng ký và thay thế authenticator

Một thiết kế possession factor chỉ hoàn chỉnh khi có quy trình quản lý credential từ lúc đăng ký đến lúc thu hồi.

Luồng đăng ký cơ bản gồm:

1. Xác định đúng tài khoản và yêu cầu mức xác thực phù hợp trước khi cho thêm authenticator.
2. Tạo giao dịch đăng ký có thời hạn, gắn với tài khoản và phiên hiện tại.
3. Thiết lập hoặc nhận dữ liệu credential theo cơ chế.
4. Xác minh bằng chứng hoàn tất đăng ký, không kích hoạt chỉ vì client đã gửi một nhãn thiết bị.
5. Lưu liên kết, trạng thái, thời điểm và thông tin cần thiết cho quản lý.
6. Thông báo thay đổi qua kênh đã thiết lập phù hợp để người dùng có thể phát hiện việc thêm trái phép.

Một hồ sơ credential khái niệm có thể gồm:

```text
CredentialRecord
  credentialId
  subjectId
  type
  verificationMaterialReference
  status
  createdAt
  lastUsedAt
  revokedAt
  userProvidedLabel
```

`verificationMaterialReference` chỉ là ký hiệu thiết kế. Với khóa bất đối xứng, dữ liệu xác minh có thể là khóa công khai và metadata phù hợp; với OTP bí mật chung, cần cơ chế bảo vệ bí mật khác. Không dùng một schema này để kết luận mọi loại credential có cùng yêu cầu lưu trữ.

Đối với tài khoản có giá trị cao, cần cơ chế dự phòng tránh việc mất một thiết bị khiến người dùng phải đi qua đường khôi phục yếu. Authenticator dự phòng vẫn phải được đăng ký, quản lý và thu hồi theo cùng trách nhiệm, không phải một bí mật bị bỏ quên trong hồ sơ.

Thêm authenticator, đổi số nhận mã hoặc thay credential đều có thể tạo một đường đăng nhập mới. Các thao tác này thường cần kiểm soát mạnh hơn sửa tên hiển thị, cùng khả năng phát hiện phiên bị chiếm dụng đang cố gắn authenticator của kẻ tấn công.

## 12. Khôi phục không được trở thành đường vòng

Nếu đăng nhập yêu cầu authenticator mạnh nhưng tổng đài có thể gỡ nó chỉ từ ngày sinh và địa chỉ email, kẻ tấn công sẽ chọn tổng đài thay vì tấn công authenticator.

Chính sách khôi phục cần làm rõ bằng chứng nào được chấp nhận, ai có quyền hỗ trợ, thời gian chờ nếu có và hành động nào phải bị hạn chế trong quá trình khôi phục. Không để một người vận hành tự ý bỏ qua mọi điều kiện chỉ vì người gọi nói đang gặp việc gấp.

Mã khôi phục được lưu để dùng khi mất authenticator cũng là bí mật cần bảo vệ. Phải xác định khả năng dùng một lần, cách lưu an toàn, cách vô hiệu hóa bộ cũ và điều gì xảy ra khi mã bị lộ. Không mặc định rằng mã khôi phục có tất cả đặc tính bảo mật của authenticator chính.

Sau khôi phục, cần xem xét credential cũ, phiên đang hoạt động và thông báo cho chủ tài khoản. Chỉ thêm credential mới mà để authenticator được báo mất tiếp tục hoạt động có thể duy trì khả năng truy cập của người không còn được phép.

## 13. Sử dụng kết quả possession trong phiên và phân quyền

Kết quả xác thực nên ghi nhận phương thức đã thực hiện, thời điểm và các thuộc tính cần cho chính sách. Ứng dụng có thể dùng thông tin này để yêu cầu xác thực lại trước hành động nhạy cảm, nhưng không được tự nâng mức tin cậy chỉ từ tên thiết bị.

Ví dụ một quản trị viên đã đăng nhập bằng mật khẩu từ nhiều giờ trước. Khi chuẩn bị đổi role cho người khác, hệ thống yêu cầu xác thực lại bằng authenticator đã đăng ký và kiểm tra quyền quản trị hiện tại. Cả hai kiểm tra đều cần thiết: possession gần đây và permission hợp lệ.

Thông tin phương thức xác thực phải đến từ thành phần xác thực đáng tin cậy và được truyền theo cơ chế bảo vệ phù hợp. Một header tùy ý như `X-MFA-Done: true` từ trình duyệt không phải bằng chứng đã hoàn tất MFA.

Sau đăng nhập, cookie phiên hoặc bearer token có thể trở thành mục tiêu chiếm đoạt. Nếu kẻ tấn công lấy được một phiên được chấp nhận, họ có thể gửi request mà không cần tạo lại bằng chứng possession trong từng request. Vì vậy bảo vệ phiên, thu hồi, giới hạn thời gian và xác thực lại vẫn có vai trò riêng.

Thu hồi authenticator cũng cần chính sách đối với các phiên đã được tạo trước đó. Hệ thống có thể cần chấm dứt hoặc đánh giá lại các phiên liên quan; không được mặc định thu hồi credential sẽ tự động làm mọi token đang tồn tại mất hiệu lực.

Danh tính workload cũng có thể chứng minh quyền kiểm soát khóa riêng hoặc secret, nhưng điều đó không tự biến xác thực workload thành MFA của một con người. Phải giữ rõ chủ thể nào đang được xác thực và chính sách nào áp dụng cho chủ thể đó.

## 14. Tình huống áp dụng và tự kiểm tra

Giả sử An quản trị tài khoản của một tenant. An có mật khẩu, ứng dụng OTP và một khóa mật mã đã đăng ký. Hãy phân tích các tình huống sau:

| Tình huống | Nhận định cần rút ra |
|---|---|
| An gửi đúng device ID nhưng không có phản hồi xác thực | Chưa chứng minh possession |
| Người khác có seed OTP được sao chép | Có thể tạo mã hợp lệ dù không có điện thoại của An |
| An nhập OTP vào website giả và mã được chuyển tiếp ngay | Mã có thời hạn không tự ngăn phishing thời gian thực |
| Một người chạm vào khóa không yêu cầu PIN | Có thể có user presence, chưa đủ kết luận đã user verification |
| Khóa đã bị thu hồi nhưng phiên cũ vẫn dùng được | Cần xử lý vòng đời phiên, không chỉ hồ sơ credential |
| Credential được đồng bộ sang thiết bị thứ hai | Không suy rằng credential chỉ tồn tại trên máy ban đầu |
| An xác thực mạnh nhưng không có quyền của tenant B | Vẫn phải từ chối truy cập tenant B |
| An mất thiết bị và yêu cầu hỗ trợ | Dùng quy trình khôi phục đã định nghĩa, có xác minh và quản lý credential cũ |

Để đánh giá một thiết kế, người học cần trả lời được: authenticator giữ thứ gì, máy chủ kiểm tra bằng chứng nào, credential được gắn với tài khoản ra sao, bằng chứng có chống phát lại hay chuyển tiếp không, và chuyện gì xảy ra khi thiết bị mất hoặc bí mật bị sao chép.

Possession factor có giá trị khi quyền kiểm soát authenticator được chứng minh bằng cơ chế phù hợp và được quản lý suốt vòng đời. Cách nhìn đó giúp tránh đồng nhất “có một thiết bị”, “có một mã” và “có một bằng chứng xác thực đủ mạnh cho hành động đang thực hiện”.
