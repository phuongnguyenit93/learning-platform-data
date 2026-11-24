# Security warning wording: viết cảnh báo bảo mật trong luồng khôi phục tài khoản

## 1. Cảnh báo phải giúp người dùng quyết định

Khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, người dùng thường đang thiếu thông tin và khó kiểm tra điều gì đã xảy ra. Một cảnh báo tốt cần giúp họ hiểu sự kiện, biết ảnh hưởng hiện tại và chọn hành động phù hợp.

Trong chương User Messaging của module khôi phục tài khoản, **security warning wording** là cách diễn đạt cảnh báo bảo mật dựa trên sự kiện và trạng thái mà hệ thống thực sự biết. Nội dung không chỉ là câu chữ trên giao diện: nó phải khớp với quyền hạn, vòng đời recovery và cơ chế xử lý phía máy chủ.

So sánh:

> Nguy hiểm! Tài khoản của bạn đã bị hack. Nhấn ngay để cứu tài khoản!

với:

> Chúng tôi ghi nhận một yêu cầu thay phương thức xác thực lúc 15:20 ngày 23/11/2026, giờ Việt Nam. Yêu cầu này chưa được phê duyệt. Nếu bạn không thực hiện, hãy mở ứng dụng và vào Trung tâm bảo mật để kiểm tra.

Câu thứ hai phân biệt được yêu cầu với thay đổi đã hoàn tất và đưa ra đường xử lý cụ thể. Nó chỉ phù hợp nếu trạng thái chưa phê duyệt và đường dẫn thao tác ấy có thật.

Các tên như “Trung tâm bảo mật”, “Hoạt động bảo mật” và “Trợ giúp khôi phục” trong bài là thành phần giao diện giả định để minh họa. Khi áp dụng, phải thay bằng tính năng và đường điều hướng thực tế của sản phẩm.

## 2. Phân biệt sự kiện, suy đoán và kết luận

### 2.1. Nói điều đã được quan sát

Hệ thống có thể biết:

- Một yêu cầu khôi phục đã được tạo.
- Một mã đã được cấp hoặc một tác vụ gửi đã được ghi nhận.
- Có lần nhập mã không hợp lệ.
- Một passkey mới đã được đăng ký.
- Một thay đổi mật khẩu đã hoàn tất.
- Một yêu cầu đang chờ xác minh hoặc đã hết hiệu lực.

Những sự kiện này không đồng nghĩa hệ thống đã biết ai là người thực hiện.

Ví dụ, “Có yêu cầu từ mạng chưa từng được ghi nhận” không chứng minh có kẻ tấn công. “Có mã nhập sai” không chứng minh mật khẩu đã bị lộ.

| Điều hệ thống biết | Cách diễn đạt phù hợp | Cách diễn đạt vượt quá bằng chứng |
| --- | --- | --- |
| Có yêu cầu recovery | “Một yêu cầu khôi phục đã được tạo” | “Có người đã chiếm tài khoản” |
| IP chưa có trong lịch sử đủ điều kiện | “Yêu cầu đến từ một mạng chưa được ghi nhận trước đây” | “Tin tặc đang ở vị trí này” |
| Mật khẩu đã thay đổi | “Mật khẩu của bạn đã được thay đổi” | “Tài khoản đã hoàn toàn an toàn” |
| Đang xử lý thu hồi một số quyền truy cập | “Chúng tôi đang xử lý việc kết thúc các phiên liên quan” | “Mọi thiết bị đã bị đăng xuất” |
| Kết quả xác minh chưa đủ điều kiện | “Chưa thể hoàn tất bằng chứng đã cung cấp” | “Bạn đang giả mạo chủ tài khoản” |

### 2.2. Mức độ cảnh báo phải theo tác động

Có thể phân biệt:

- **Thông tin**: một yêu cầu đã được tiếp nhận hoặc đang chờ.
- **Cần chú ý**: có thay đổi cần người dùng nhận diện.
- **Cần xử lý**: một thay đổi nhạy cảm đã xảy ra hoặc có căn cứ cần bảo vệ tài khoản.

Nhãn và màu chỉ bổ trợ. Nội dung phải nói rõ sự kiện và hành động bằng chữ, để người dùng không phải suy ra mức độ từ màu đỏ hoặc biểu tượng.

Không làm mọi thông báo đều mang giọng khẩn cấp. Nếu yêu cầu gửi mã và thay toàn bộ MFA đều có cùng mức cảnh báo, người dùng khó nhận ra tình huống cần ưu tiên.

## 3. Phân loại người nhận và ngữ cảnh hiển thị

Một thông điệp phù hợp trong email đã đăng ký có thể không phù hợp trên endpoint công khai.

| Ngữ cảnh | Nội dung có thể cung cấp theo quyền tương ứng | Rủi ro cần tránh |
| --- | --- | --- |
| Form recovery công khai | Hướng dẫn chung, phản hồi nhất quán | Tiết lộ tài khoản tồn tại hoặc cấu hình xác thực |
| Màn hình của một yêu cầu đã có quyền truy cập phù hợp | Trạng thái và hành động trong phạm vi yêu cầu | Dùng quyền recovery để đọc hồ sơ ngoài phạm vi |
| Phiên đăng nhập đã được xác thực phù hợp | Chi tiết hoạt động theo quyền người dùng | Coi mọi phiên cũ đều đáng tin cậy |
| Email, SMS hoặc push thông báo | Sự kiện cần nhận diện và đường báo hoạt động không được phép | Lộ dữ liệu trên màn hình khóa hoặc kênh bị xâm phạm |
| Nhân viên hỗ trợ | Thông tin cần cho tác vụ được giao | Đọc bí mật xác thực hoặc chi tiết không cần thiết cho người gọi |

OWASP khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại trong bước yêu cầu đặt lại mật khẩu, đồng thời tránh chênh lệch thời gian phản hồi làm lộ thông tin. [Nguồn: OWASP — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Ví dụ trên form công khai:

> Nếu thông tin bạn cung cấp phù hợp với một phương thức khôi phục được hỗ trợ, bạn sẽ nhận được hướng dẫn qua kênh đã đăng ký. Hãy kiểm tra hộp thư và thư rác.

Câu này không xác nhận tài khoản tồn tại và không khẳng định hệ thống đã giao thư thành công. Nó cần được dùng nhất quán, cùng hành vi API và cách hiển thị phù hợp.

Không thêm bên dưới một thông báo khác như “Tài khoản này chưa đăng ký MFA” hoặc “Chúng tôi đã gửi tới a***@example.com” nếu người xem chưa có quyền biết các thông tin đó. Một dòng phản hồi chung không bù được phần rò rỉ ở nơi khác.

## 4. Cấu trúc của một cảnh báo có thể hành động

Một cảnh báo về sự kiện tài khoản có thể được thiết kế thành năm phần:

1. **Sự kiện**: hành động gì đã được yêu cầu hoặc đã xảy ra.
2. **Thời điểm**: thời gian có múi giờ rõ ràng khi cần đối chiếu.
3. **Ảnh hưởng**: điều gì đã thay đổi, điều gì còn đang chờ.
4. **Nhánh nhận diện**: người nhận có thực hiện hay không.
5. **Hành động**: bước tiếp theo cụ thể trong sản phẩm hoặc kênh hỗ trợ chính thức.

Mẫu:

```text
Tiêu đề:
[Sự kiện có thể nhận diện]

Nội dung:
[Sự kiện] được ghi nhận lúc [thời điểm và múi giờ].
[Ảnh hưởng hoặc trạng thái được xác nhận].

Nếu bạn thực hiện:
[Hành động phù hợp, hoặc cho biết không cần làm thêm].

Nếu bạn không thực hiện:
[Đường xử lý thực tế].
[Hướng dẫn bảo vệ mã hoặc bí mật, nếu liên quan].
```

Không phải thông điệp nào cũng cần đủ năm phần. SMS có thể cần ngắn hơn; một màn hình xác nhận có thể đã hiển thị thời gian ở phần khác. Tuy vậy, việc rút gọn không được làm mất phân biệt giữa yêu cầu đang chờ và thay đổi đã hoàn tất.

NIST SP 800-63B-4 xem thông báo tài khoản là cách giúp người dùng phát hiện gian lận và yêu cầu hướng dẫn rõ ràng, gồm thông tin liên hệ, khi người nhận phủ nhận sự kiện. [Nguồn: NIST — Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications).

Thông báo cho biết “nếu không phải bạn” nhưng không có đường xử lý dùng được sẽ không hoàn thành mục tiêu này.

## 5. Mẫu câu cho yêu cầu và mã khôi phục

### 5.1. Yêu cầu đã được tạo nhưng chưa thay đổi tài khoản

Trong một kênh có quyền nhận thông tin sự kiện:

> Một yêu cầu khôi phục tài khoản được tạo lúc 15:20 ngày 23/11/2026, giờ Việt Nam. Yêu cầu này chưa làm thay đổi mật khẩu hoặc phương thức xác thực của bạn. Nếu bạn không thực hiện, hãy mở ứng dụng và kiểm tra Hoạt động bảo mật.

Câu “chưa làm thay đổi” chỉ dùng khi hệ thống đã xác định đúng phạm vi và trạng thái tại thời điểm thông báo. Không dùng một mẫu chung nếu cùng loại sự kiện có thể được phát ra sau khi thay đổi đã hoàn tất.

Nếu sản phẩm không có trang hoạt động bảo mật cho người đang bị khóa ngoài, phải đưa đường hỗ trợ khôi phục có thể tiếp cận mà không đòi phương thức họ đã mất.

### 5.2. Mã chỉ dành cho thao tác do người dùng chủ động

Ví dụ thông điệp chứa mã:

```text
Mã xác minh cho yêu cầu khôi phục của bạn: [mã].

Chỉ nhập mã trong luồng khôi phục chính thức mà bạn đã chủ động mở.
Không đọc hoặc gửi mã cho người khác, kể cả người tự xưng là hỗ trợ.
Mã có hiệu lực đến [thời điểm, múi giờ].
```

Không viết “không bao giờ nhập mã ở bất kỳ đâu”, vì người dùng cần nhập mã vào giao diện hợp lệ. Cần phân biệt nhập trong luồng chính thức với gửi cho một người đang liên lạc.

Hạn dùng phải được lấy từ dữ liệu máy chủ. Không viết cố định “10 phút” trong mẫu nếu chính sách hoặc thời điểm gửi khiến thông tin đó không còn đúng.

Mã xuất hiện trên thông điệp là bí mật của bước tương ứng. Phần hướng dẫn không được yêu cầu người dùng chụp ảnh mã gửi cho hỗ trợ để xác nhận.

### 5.3. Khi người nhận không yêu cầu mã

Có thể dùng:

> Nếu bạn không yêu cầu mã này, đừng nhập hoặc chia sẻ mã. Việc nhận mã không đồng nghĩa tài khoản đã được khôi phục. Nếu các yêu cầu tiếp tục xuất hiện hoặc bạn thấy thay đổi không nhận ra, hãy dùng mục Trợ giúp khôi phục trên ứng dụng hoặc website chính thức.

Câu này chỉ phù hợp khi việc cấp mã thực sự chưa tự hoàn tất recovery. Nó không tuyên bố không có rủi ro khác và không thay thế thông báo cho một thay đổi đã xảy ra.

“Bạn có thể bỏ qua mã” có thể phù hợp trong một ngữ cảnh hẹp. Nhưng không dùng “cứ bỏ qua” cho mọi loại cảnh báo, đặc biệt khi mật khẩu hoặc MFA đã bị thay.

## 6. Mẫu câu cho thay đổi đã hoàn tất

### 6.1. Mật khẩu đã thay đổi

Ví dụ:

> Mật khẩu tài khoản của bạn đã được thay đổi lúc 15:28 ngày 23/11/2026, giờ Việt Nam. Nếu bạn thực hiện, hãy đăng nhập bằng mật khẩu mới qua ứng dụng hoặc website chính thức. Nếu bạn không thực hiện, hãy mở Trợ giúp khôi phục và chọn “Tôi không thực hiện thay đổi này”.

Chỉ thêm thông tin như “các phiên trước đã kết thúc” khi backend xác nhận điều đó theo đúng phạm vi. Thay mật khẩu không tự chứng minh mọi refresh token, API key hoặc quyền ủy quyền đã mất hiệu lực.

Nếu hệ thống còn đang thực hiện bước bảo vệ liên quan, nội dung cần phản ánh đúng việc đang xử lý và các hạn chế hiện tại. Không gửi thông báo “đã hoàn tất mọi biện pháp” chỉ vì tác vụ đã được đưa vào hàng đợi.

### 6.2. Phương thức xác thực đã thay đổi

Ví dụ:

> Một phương thức xác thực mới đã được thêm vào tài khoản của bạn lúc 15:31 ngày 23/11/2026, giờ Việt Nam. Nếu bạn không thêm phương thức này, hãy kiểm tra trong Trung tâm bảo mật hoặc dùng Trợ giúp khôi phục nếu không đăng nhập được.

Nếu hệ thống biết authenticator cụ thể bị thay thế, có thể mô tả bằng nhãn được kiểm soát và không chứa bí mật. Không đưa khóa riêng, seed TOTP, mã dự phòng hoặc dữ liệu cần giữ kín vào thông báo.

Không khẳng định “mọi passkey cũ đã bị xóa” nếu chỉ một credential đã bị thu hồi. Phân biệt passkey, thiết bị và phiên đăng nhập cũng cần được giữ đúng theo dữ liệu sản phẩm.

### 6.3. Không hướng dẫn hủy một sự kiện đã hoàn tất

Một nút “Hủy yêu cầu” chỉ có ý nghĩa khi còn một yêu cầu có thể hủy. Sau khi thay đổi đã hoàn tất, hành động phù hợp có thể là báo sự kiện không được phép hoặc bắt đầu quy trình bảo vệ.

Nội dung nên gọi đúng hành động:

| Trạng thái | Nhãn có thể phù hợp |
| --- | --- |
| Yêu cầu còn chờ và có quyền hủy | “Hủy yêu cầu khôi phục” |
| Thay đổi đã hoàn tất | “Báo thay đổi không phải của tôi” |
| Người dùng cần xem thêm chi tiết | “Xem hoạt động bảo mật” |
| Không đăng nhập được | “Mở trợ giúp khôi phục” |

Báo thay đổi không được phép không đồng nghĩa hệ thống lập tức hoàn tác mọi thứ. Nếu còn cần xác minh, thông báo sau thao tác phải nói rõ điều đó.

## 7. Thời gian chờ, hết hạn và giới hạn thử lại

### 7.1. Đang chờ không đồng nghĩa chắc chắn được duyệt

Một thông điệp phù hợp:

> Yêu cầu của bạn đang chờ đánh giá. Bạn chưa thể thay phương thức xác thực ở bước này. Hãy xem trạng thái trong Trợ giúp khôi phục. Chúng tôi sẽ thông báo khi có kết quả hoặc cần thêm thông tin.

Chỉ hứa “sẽ thông báo” nếu sản phẩm có quy trình thông báo bền vững tương ứng. Nếu có thời điểm dự kiến, cần phân biệt ước lượng với thời điểm chắc chắn.

Không viết:

> Đợi đủ 24 giờ là tài khoản sẽ được mở.

nếu hết thời gian chỉ làm yêu cầu đủ điều kiện được đánh giá lại. Chờ lâu không tự tạo thêm bằng chứng quyền sở hữu.

Có thể viết theo đúng cơ chế:

> Bạn có thể kiểm tra bước tiếp theo từ 09:00 ngày 24/11/2026, giờ Việt Nam. Chúng tôi vẫn cần kiểm tra các điều kiện trước khi phê duyệt.

Đây là ví dụ về diễn đạt, không phải quy định rằng mọi sản phẩm phải chờ đến mốc đó.

### 7.2. Mã không còn dùng được

Ví dụ trên màn hình đã có quyền xử lý yêu cầu:

> Mã này không còn dùng được. Hãy yêu cầu mã mới từ luồng khôi phục chính thức và làm theo hướng dẫn hiện tại.

Tùy quyền người xem và chính sách tiết lộ, hệ thống có thể cho biết rõ “đã hết hạn” hoặc “đã được sử dụng”. Không cần công khai mọi nguyên nhân nội bộ cho người chưa chứng minh được quyền đối với yêu cầu.

Không viết “Mã của bạn sai” nếu hệ thống chỉ biết mã không còn hợp lệ vì đã hết thời gian. Câu chữ sai nguyên nhân có thể khiến người dùng thử đi thử lại không cần thiết.

### 7.3. Đạt giới hạn thử lại

Ví dụ:

> Bạn đã thử nhiều lần. Hãy thử lại sau thời điểm được hiển thị hoặc dùng phương án khôi phục khác được hỗ trợ.

Nếu hiển thị thời điểm thử lại, giá trị phải khớp với quyết định của máy chủ. Không dùng bộ đếm chạy cục bộ rồi mở nút khi backend vẫn từ chối.

Thông báo cũng không nên tuyên bố “tài khoản đã bị khóa” nếu chỉ một phương thức hoặc một yêu cầu bị hạn chế. Phạm vi hạn chế cần được diễn đạt đúng để người dùng không hiểu rằng mọi đường truy cập đều mất.

## 8. Nhánh “không phải tôi” phải có hành động thực tế

Một cảnh báo không chỉ để người dùng đọc. Nó cần nối với quy trình nhận báo cáo và bảo vệ tài khoản.

### 8.1. Đưa ra đường có thể đi được khi người dùng mất quyền truy cập

Ví dụ:

> Nếu bạn không thực hiện thay đổi này, hãy tự mở ứng dụng hoặc website chính thức và vào Trợ giúp khôi phục. Nếu còn đăng nhập được, bạn có thể kiểm tra Hoạt động bảo mật trong phần cài đặt tài khoản.

Cách diễn đạt này có hai đường: còn phiên dùng được và không còn đăng nhập được. Nếu chỉ nói “đăng nhập rồi đổi mật khẩu” khi chính mật khẩu đã bị đổi trái phép, người dùng có thể không làm theo được.

Thông tin hỗ trợ cần là kênh do sản phẩm kiểm soát và được duy trì. Không viết “liên hệ ngay với chúng tôi” mà không cho biết liên hệ bằng cách nào.

### 8.2. Nói rõ kết quả của nút báo cáo

Nếu nhấn nút mới chỉ gửi một báo cáo:

> Chúng tôi đã nhận báo cáo. Báo cáo này chưa hoàn tất việc xác minh quyền sở hữu tài khoản. Hãy làm theo bước tiếp theo trong Trợ giúp khôi phục.

Nếu hệ thống đã áp dụng biện pháp bảo vệ cụ thể, có thể nêu đúng biện pháp ấy. Không biến “đã nhận báo cáo” thành “đã chặn toàn bộ người lạ”.

Tên nút không nên hứa điều hệ thống không thực hiện:

| Tên gây hiểu nhầm | Lựa chọn theo hành vi thực tế |
| --- | --- |
| “Cứu tài khoản ngay” | “Báo hoạt động không được phép” |
| “Đăng xuất tin tặc” khi chưa xác minh được actor | “Xem và kết thúc các phiên đăng nhập” nếu tính năng có thật |
| “Hoàn tác tất cả” khi chỉ hủy được yêu cầu đang chờ | “Hủy yêu cầu đang chờ” |
| “Xác nhận an toàn” khi chỉ đánh dấu đã đọc | “Tôi nhận ra hoạt động này” |

### 8.3. Câu chữ không được thay thế kiểm soát backend

Một liên kết trong thông báo không được dùng để thực hiện thay đổi nhạy cảm bằng GET chỉ vì nút có chữ “Bảo vệ tài khoản”. Công cụ xem trước hoặc quét liên kết có thể truy cập trước người dùng.

Luồng báo cáo và hủy yêu cầu cần kiểm tra quyền, mục đích và trạng thái tương ứng. Một liên kết báo cáo có phạm vi hẹp không được tự trở thành quyền thay toàn bộ thông tin xác thực.

Cũng cần cân nhắc lạm dụng: một người chỉ biết địa chỉ email của nạn nhân không nên dễ dàng dùng chức năng báo cáo để gây khóa tài khoản tùy ý. Quy trình bảo vệ phải dựa trên căn cứ và chính sách phù hợp với tác động.

## 9. Viết cảnh báo không giống lời dụ dỗ lừa đảo

### 9.1. Hướng dẫn người dùng tự tìm đến kênh chính thức

Một thông báo an toàn có thể cho người dùng lựa chọn tự mở ứng dụng hoặc gõ địa chỉ website đã biết. Người dùng không nên phải tin mọi liên kết trong tin nhắn mới thực hiện được bước bảo vệ.

Nếu dùng liên kết, tên miền đích và cách trình bày phải được kiểm soát. Không khuyến khích người dùng tin một tin nhắn chỉ vì có logo, tên người gửi hoặc câu “đã xác minh”. Những dấu hiệu ấy có thể bị sao chép.

Không dùng URL rút gọn cho hành động nhạy cảm nếu nó làm người nhận không nhận ra nơi đến. Không đưa một địa chỉ lấy từ dữ liệu người dùng vào nút hỗ trợ mà không kiểm soát.

### 9.2. Không tạo áp lực sai sự thật

Tránh các mẫu:

- “Bạn sẽ mất tài khoản vĩnh viễn trong 5 phút” khi không có quy tắc đó.
- “Phải chuyển tiền để xác minh chủ sở hữu.”
- “Gửi OTP để chúng tôi ngăn tin tặc.”
- “Cài công cụ điều khiển máy để xử lý ngay.”
- “Đừng liên hệ kênh khác, chỉ làm theo tin nhắn này.”

Nội dung chính thức nên xác định chính xác hành động được hỗ trợ và không yêu cầu người dùng giao bí mật cho người đang liên lạc. Các cảnh báo về hậu quả cần có căn cứ, không dùng để thúc ép bấm nút.

### 9.3. Không đổ lỗi cho người dùng

Thay:

> Bạn đã bất cẩn làm mất MFA.

bằng:

> Nếu bạn không còn dùng được phương thức xác thực này, hãy chọn một phương án khôi phục được hỗ trợ.

Thay:

> Bạn nhập sai quá nhiều nên chúng tôi nghi ngờ bạn.

bằng:

> Phương thức này đang được giới hạn sau nhiều lần thử. Hãy xem thời điểm thử lại hoặc chọn phương án khác được hỗ trợ.

Giọng bình tĩnh giúp người dùng tập trung vào hành động. Nó không yêu cầu hệ thống tiết lộ điểm rủi ro, ngưỡng chặn hoặc quy tắc phát hiện nội bộ.

## 10. Bảo vệ dữ liệu trong chính thông báo

### 10.1. Chỉ đưa chi tiết giúp nhận diện sự kiện

Có thể cần thời điểm, loại hành động và thông tin thiết bị ở mức phù hợp. Không cần đưa mọi chi tiết từ log.

Những dữ liệu thường không nên xuất hiện trong cảnh báo thông thường gồm:

- Mật khẩu hoặc mật khẩu mới.
- TOTP seed, khóa riêng hoặc mã dự phòng.
- Token phiên hoặc refresh token.
- Toàn bộ số giấy tờ, địa chỉ hoặc hồ sơ xác minh.
- Ghi chú điều tra nội bộ hoặc điểm rủi ro chi tiết.

Một thông báo chứa mã hoặc liên kết recovery có mục đích giao bí mật riêng. Không tái sử dụng mẫu đó làm cảnh báo chung rồi để token lan sang các kênh không cần nhận.

### 10.2. Vị trí mạng không phải vị trí vật lý đã được chứng minh

Nếu hiển thị vị trí suy ra từ IP, cần mô tả là vị trí ước lượng. Tránh viết “người này đang ở địa chỉ...” khi hệ thống chỉ có dữ liệu định vị mạng.

Tên thiết bị cũng có thể được người dùng hoặc máy khách đặt. Không cho một nhãn như “Hỗ trợ: gửi OTP tới số...” trở thành hướng dẫn đáng tin cậy trong thông báo.

Dữ liệu động cần được escape hoặc mã hóa phù hợp với ngữ cảnh HTML, URL và văn bản. Việc dịch mẫu không loại bỏ nguy cơ chèn nội dung từ biến đầu vào.

### 10.3. Màn hình khóa cần ít chi tiết hơn màn hình trong ứng dụng

Một push có thể chỉ viết:

> Có cập nhật về bảo mật tài khoản. Mở ứng dụng để xem chi tiết.

Sau khi người dùng vào đúng ngữ cảnh được phép, giao diện mới hiển thị sự kiện cụ thể. Mức rút gọn phụ thuộc thiết kế sản phẩm và nhu cầu cảnh báo, nhưng không nên mặc định mọi người cầm thiết bị đều được đọc chi tiết recovery.

Kênh nhận cảnh báo cũng cần được chọn theo chính sách tài khoản và tình trạng sự cố. Nội dung hay không khắc phục được việc chỉ gửi tới một địa chỉ vừa bị kẻ tấn công thay.

## 11. Thời gian, ngôn ngữ và khả năng tiếp cận

### 11.1. Giữ thời điểm rõ ràng

“Vừa rồi” hoặc “hôm nay” dễ gây nhầm khi email đến trễ hoặc người dùng đổi múi giờ. Với sự kiện nhạy cảm, có thể dùng ngày, giờ và múi giờ cụ thể.

Ví dụ:

```text
15:20 ngày 23/11/2026, giờ Việt Nam (UTC+7)
```

Nếu hiển thị giờ địa phương theo người dùng, cần có quy tắc chuyển đổi thống nhất và giữ timestamp chuẩn trong dữ liệu sự kiện. Không lấy đồng hồ trình duyệt làm nguồn xác định lúc thay đổi mật khẩu đã xảy ra.

### 11.2. Dịch nghĩa nhưng giữ nguyên ngữ nghĩa bảo mật

Các từ sau không thể hoán đổi tùy ý:

| Ý nghĩa | Cần giữ khi dịch |
| --- | --- |
| Requested | Đã có yêu cầu, chưa khẳng định được duyệt |
| Pending | Còn điều kiện hoặc bước xử lý chưa hoàn tất |
| Approved | Đã phê duyệt trong một phạm vi, chưa nhất thiết đã áp dụng |
| Completed | Hành động tương ứng đã hoàn tất |
| Revoked | Quyền hoặc phương thức trong phạm vi đã bị thu hồi |
| Reported | Đã nhận báo cáo, chưa khẳng định sự cố đã được xác minh |

Không dịch “yêu cầu đã được tiếp nhận” thành “tài khoản đã được khôi phục”. Không đổi “có thể cần thêm xác minh” thành “bạn chắc chắn sẽ được duyệt”.

Mã xác minh, mã tham chiếu và liên kết không được tự biến đổi qua bản dịch. Với màn hình nhập mã, hướng dẫn cần thống nhất về ký tự được chấp nhận và định dạng hiển thị.

### 11.3. Để người dùng đọc được hành động

Nên dùng câu ngắn, một hành động chính và tên nút rõ nghĩa. Không chỉ dựa vào chữ in hoa, màu sắc, âm thanh hoặc biểu tượng.

Màn hình cảnh báo cần có thứ tự đọc hợp lý và thông báo trạng thái mà công nghệ hỗ trợ có thể nhận biết. Không làm người dùng mất hướng khi lỗi xuất hiện ở nơi khác với trường đang thao tác.

Nếu có giới hạn thời gian, người dùng cần được biết cách yêu cầu bước mới hoặc chuyển sang phương án được hỗ trợ. Đếm ngược gây áp lực mà không có đường tiếp tục sẽ làm tăng lỗi thao tác.

## 12. Giữ nội dung đồng bộ với trạng thái backend

Một mẫu câu đúng vẫn có thể trở nên sai khi chọn nhầm sự kiện hoặc gửi quá muộn.

### 12.1. Tách loại sự kiện khỏi đoạn văn tự do

Có thể xây dựng hợp đồng thông điệp như sau:

```json
{
  "eventId": "sec_evt_804",
  "eventType": "RECOVERY_REQUEST_CREATED",
  "occurredAt": "2026-11-23T08:20:00Z",
  "requestRef": "rr_48a",
  "audience": "REGISTERED_NOTIFICATION_CHANNEL",
  "templateKey": "recovery.request.created.vi",
  "templateVersion": 3,
  "allowedActions": [
    "VIEW_CURRENT_STATUS",
    "REPORT_UNRECOGNIZED_REQUEST"
  ]
}
```

Đây là schema minh họa. Các trường phải do máy chủ tạo và kiểm soát; máy khách không được tự chọn audience có quyền cao hơn hoặc template khẳng định thành công.

Nên chọn mẫu theo sự kiện, trạng thái và quyền người nhận. Không để một chuỗi lỗi kỹ thuật hoặc ghi chú tự do đi thẳng ra thông báo người dùng.

### 12.2. Phân biệt lịch sử sự kiện với trạng thái hiện tại

Giả sử yêu cầu được tạo lúc 15:20, bị hủy lúc 15:22, nhưng email tạo yêu cầu đến lúc 15:25.

Câu:

> Yêu cầu của bạn hiện đang chờ phê duyệt.

có thể đã sai.

Câu mô tả lịch sử:

> Một yêu cầu khôi phục được tạo lúc 15:20 ngày 23/11/2026, giờ Việt Nam. Hãy mở Trợ giúp khôi phục để xem trạng thái hiện tại.

giữ được ý nghĩa của sự kiện. Nếu mẫu cần nêu trạng thái hiện tại, hệ thống phải có cách lấy lại trạng thái phù hợp trước khi gửi và xử lý trường hợp thông điệp đã lỗi thời.

Không thể bảo đảm một thông báo sẽ luôn mô tả hiện tại sau khi tới thiết bị. Vì vậy, nội dung nên xác định thời điểm sự kiện và dẫn người dùng đến nơi xem trạng thái mới nhất.

### 12.3. Không dùng trạng thái giao tin làm trạng thái recovery

`QUEUED`, `SENT` hoặc `DELIVERED` của thông báo khác với `APPROVED` hoặc `COMPLETED` của recovery.

- Đưa thư vào hàng đợi chưa có nghĩa người dùng đã nhận.
- Provider nhận tác vụ chưa chứng minh đã giao thành công.
- Giao thành công chưa chứng minh chủ tài khoản đã đọc.
- Người dùng đọc cảnh báo chưa chứng minh họ chấp thuận thay đổi.

Các thông điệp “đã gửi”, “đã xác minh” và “đã hoàn tất” cần nguồn sự thật riêng. Không đổi trạng thái nghiệp vụ chỉ để phù hợp với câu chữ đã viết trước.

## 13. Ví dụ xuyên suốt: yêu cầu thay MFA không được nhận ra

Hà mất điện thoại nhưng còn một phương án recovery. Trong lúc cô đang xử lý, hệ thống ghi nhận một yêu cầu khác thay phương thức xác thực.

### Giai đoạn 1: Yêu cầu mới

Thông báo tới kênh được phép:

> Một yêu cầu thay phương thức xác thực được tạo lúc 15:20 ngày 23/11/2026, giờ Việt Nam. Nếu bạn không nhận ra yêu cầu này, hãy tự mở ứng dụng hoặc website chính thức và vào Trợ giúp khôi phục để kiểm tra.

Không kết luận có tin tặc, không tiết lộ điểm rủi ro và không yêu cầu Hà gửi OTP cho nhân viên.

### Giai đoạn 2: Hà báo không thực hiện

Nếu hệ thống mới nhận báo cáo:

> Chúng tôi đã nhận báo cáo về yêu cầu bạn không nhận ra. Hãy tiếp tục theo hướng dẫn trong Trợ giúp khôi phục. Chúng tôi sẽ chỉ xác nhận biện pháp bảo vệ khi bước tương ứng đã được thực hiện.

Trong sản phẩm thật, phần hứa thông báo hoặc bước tiếp theo phải khớp quy trình đang có. Không dùng câu này như vật thay thế cho một quy trình chưa tồn tại.

### Giai đoạn 3: Yêu cầu đã bị hủy

Khi hủy thành công:

> Yêu cầu khôi phục lúc 15:20 đã bị hủy. Yêu cầu đó không thể được tiếp tục. Hãy kiểm tra các hoạt động khác nếu bạn vẫn thấy thay đổi không nhận ra.

Chỉ khẳng định phạm vi của yêu cầu đã hủy, không tuyên bố toàn bộ tài khoản chắc chắn an toàn.

### Giai đoạn 4: Nếu thay đổi đã hoàn tất trước khi báo cáo

Hệ thống phải dùng mẫu khác:

> Thay đổi phương thức xác thực đã hoàn tất trước khi chúng tôi nhận báo cáo. Hãy tiếp tục quy trình bảo vệ tài khoản trong Trợ giúp khôi phục. Việc gửi báo cáo không tự hoàn tác thay đổi.

Hai tình huống không thể dùng chung thông báo “đã hủy yêu cầu”. Cách diễn đạt phải đi theo trạng thái thực tế và quyền xử lý còn khả dụng.

## 14. Các lỗi diễn đạt thường gặp

| Lỗi | Hậu quả | Cách sửa theo nguyên tắc |
| --- | --- | --- |
| Gọi một yêu cầu mới là “tài khoản bị chiếm” | Gây hoảng và nói quá bằng chứng | Mô tả sự kiện, tách khỏi suy đoán actor |
| Nói “bỏ qua” cho thay đổi đã hoàn tất | Người dùng bỏ lỡ bước bảo vệ cần thiết | Cung cấp nhánh báo hoạt động không được phép |
| Hứa “đã đăng xuất tất cả” khi mới đưa tác vụ vào hàng đợi | Tạo cảm giác an toàn sai | Chỉ xác nhận hiệu lực đã được kiểm chứng |
| Nút “hoàn tác” chỉ gửi báo cáo | Người dùng tưởng thay đổi đã bị đảo ngược | Đặt tên đúng hành động và giải thích kết quả |
| Hiển thị địa chỉ khôi phục trên form công khai | Tiết lộ sự tồn tại hoặc cấu hình tài khoản | Phản hồi chung ở ngữ cảnh chưa có quyền |
| Yêu cầu liên hệ hỗ trợ nhưng không có đường dùng được | Người mất quyền truy cập bị kẹt | Chỉ dẫn kênh chính thức có thể tiếp cận |
| Đưa IP thành vị trí vật lý chính xác | Người dùng hiểu sai mức chắc chắn | Ghi rõ vị trí ước lượng và giới hạn |
| Dùng tên thiết bị làm hướng dẫn | Dữ liệu do người dùng đặt có thể chèn nội dung | Hiển thị như nhãn đã xử lý, không như chỉ thị |
| Đếm ngược không khớp backend | Người dùng thử lại vẫn bị chặn | Lấy mốc thời gian từ trạng thái máy chủ |
| Dịch “đã tiếp nhận” thành “đã hoàn tất” | Thay đổi ngữ nghĩa bảo mật | Giữ phân biệt trạng thái trong mọi ngôn ngữ |
| Email trễ vẫn nói “hiện đang chờ” | Thông tin lỗi thời dẫn sai hành động | Ghi thời điểm sự kiện và đường xem trạng thái hiện tại |
| Cảnh báo chỉ bằng màu hoặc biểu tượng | Người dùng khó nhận biết mức độ | Viết rõ sự kiện và hành động bằng chữ |

## 15. Câu hỏi tự suy luận

1. Hệ thống ghi nhận một yêu cầu từ mạng mới. Vì sao chưa thể viết “kẻ tấn công đang đăng nhập”?
2. Thông báo công khai và thông báo tới một kênh tài khoản được phép cần khác nhau ở điểm nào?
3. Khi nào câu “nếu không phải bạn, có thể bỏ qua” phù hợp, và khi nào nó gây nguy hiểm?
4. Nút “Hủy yêu cầu” có ý nghĩa gì khi thay đổi đã hoàn tất?
5. Vì sao trạng thái giao email không thể dùng làm trạng thái phê duyệt recovery?
6. Nếu cảnh báo đến trễ sau khi yêu cầu đã hủy, nội dung nào vẫn đúng?
7. Một người không còn đăng nhập được cần đường nào để báo thay đổi không được phép?
8. Những dữ liệu động nào có thể làm một cảnh báo hợp lệ trông giống hướng dẫn lừa đảo?

Một cảnh báo bảo mật đáng tin cậy cần nói đúng điều hệ thống biết, mô tả đúng phạm vi tác động và hướng người dùng tới hành động thực hiện được. Câu chữ, trạng thái máy chủ và đường xử lý phải cùng diễn đạt một sự thật.