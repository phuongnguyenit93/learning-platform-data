# Cây quyết định cho hành trình khôi phục tài khoản

Trong chương **Recovery Journey** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **recovery journey decision tree** là cây quyết định giúp hệ thống chọn đường khôi phục dựa trên tình huống mất quyền truy cập, bằng chứng còn sử dụng được và chính sách áp dụng cho hành động cần thực hiện.

Người dùng có thể quên mật khẩu, mất điện thoại chứa TOTP, không còn truy cập passkey hoặc nghi thiết bị đã bị chiếm. Những tình huống này không nên cùng dẫn đến một nút “bỏ MFA và đặt mật khẩu mới”. Mỗi đường phải có điều kiện vào, bước xác minh, phạm vi quyền và kết quả kết thúc rõ ràng.

Một cây quyết định tốt giúp chủ tài khoản tìm được đường khả thi, đồng thời ngăn đối thủ chọn nhánh ít kiểm tra nhất để tạo quyền truy cập mới.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thông tin người dùng khai báo với bằng chứng đã được máy chủ xác minh.
- Thiết kế cây quyết định cho việc mất mật khẩu, MFA, passkey hoặc thiết bị.
- Tách nhánh đăng nhập bằng phương thức còn lại khỏi nhánh khôi phục khi không còn khả năng đăng nhập.
- Xác định điểm chuyển sang xử lý nghi bị chiếm, xem xét thủ công hoặc kết thúc chưa đủ bằng chứng.
- Gắn mỗi nhánh với quyền cụ thể thay vì cấp một phiên toàn quyền cho mọi trường hợp.
- Chuyển cây quyết định thành trạng thái giao dịch có thể tiếp tục, hết hạn, hủy và hoàn tất an toàn.

## 2. Cây quyết định giải quyết vấn đề gì?

Hãy xét ba người dùng:

- An quên mật khẩu nhưng vẫn dùng được email và TOTP.
- Bình mất điện thoại chứa TOTP nhưng còn passkey trên một khóa bảo mật khác.
- Chi mất toàn bộ authenticator và nghi email đã bị chiếm.

Nếu cả ba chỉ được đưa đến biểu mẫu “nhận mã email để tắt MFA”, hệ thống vừa gây phiền cho Bình, vừa có thể tạo đường chiếm tài khoản của Chi. Nếu cả ba bị yêu cầu cung cấp TOTP, An và Bình còn có thể tìm cách xử lý nhưng Chi sẽ bị đưa vào ngõ cụt.

Cây quyết định cần phân biệt hai câu hỏi:

1. **Người dùng muốn sửa vấn đề nào?** Đây là thông tin giúp định tuyến.
2. **Người yêu cầu chứng minh được quyền gì?** Đây là căn cứ để cấp quyền.

Câu trả lời “tôi mất điện thoại” chỉ hỗ trợ câu hỏi thứ nhất. Nó không tự chứng minh người yêu cầu là chủ tài khoản và không tự cho phép gỡ yếu tố thứ hai.

### Cây quyết định và máy trạng thái có vai trò khác nhau

| Thành phần | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Cây quyết định | Tiếp theo nên đi theo đường nào? | Còn authenticator sử dụng được thì thử xác minh theo đường đó |
| Máy trạng thái | Giao dịch hiện ở đâu và được chuyển sang đâu? | Đã gửi mã nhưng chưa xác minh thì không được đặt lại credential |
| Chính sách khôi phục | Bằng chứng nào đủ cho hành động nào? | Mã email có thể chỉ cho phép đổi mật khẩu, không cho phép gỡ MFA |
| Giao diện hành trình | Người dùng thấy và thực hiện điều gì? | Hướng dẫn dùng phương thức khác hoặc quay lại khi đã chuẩn bị bằng chứng |

Cây đẹp trên giao diện không thay thế được chính sách và trạng thái phía máy chủ. Một nhánh chỉ an toàn khi API cũng từ chối mọi đường tắt vượt qua điều kiện của nhánh đó.

## 3. Các đầu vào cần có trước khi phân nhánh

Không cần thu thập mọi thông tin ngay từ đầu. Chỉ lấy dữ liệu cần cho bước hiện tại và phân biệt rõ dữ liệu do người yêu cầu gửi với dữ liệu đã kiểm chứng.

| Đầu vào | Nguồn | Vai trò | Giới hạn |
| --- | --- | --- | --- |
| Vấn đề đang gặp | Người dùng lựa chọn | Chọn hướng giải thích và phương thức thử trước | Không phải bằng chứng sở hữu |
| Định danh tài khoản | Người dùng nhập hoặc phiên đã xác thực | Liên kết nội bộ giao dịch với tài khoản nếu có | Không được dùng để công khai xác nhận tài khoản tồn tại |
| Authenticator đang được thử | Lựa chọn của người dùng và dữ liệu đăng ký phía máy chủ | Xác định bước xác minh phù hợp | Chỉ được chấp nhận sau khi giao thức xác minh thành công |
| Kênh khôi phục có trước | Hồ sơ đã được xác minh của tài khoản | Chọn nơi gửi bằng chứng nếu chính sách cho phép | Kênh vừa được nhập vào không tự trở thành kênh đáng tin |
| Bối cảnh nghi bị chiếm | Khai báo và các tín hiệu được hệ thống thu thập hợp lệ | Điều chỉnh đường khôi phục và phạm vi xử lý | Khai báo không tự đủ để khóa hoặc thay đổi tài khoản của người khác |
| Loại tài khoản, hành động yêu cầu | Dữ liệu máy chủ và giao dịch | Áp dụng chính sách phù hợp | Không tin giá trị client tự nhận là tài khoản có quyền thấp |
| Bằng chứng đã xác minh | Kết quả kiểm tra phía máy chủ | Cho phép chuyển sang bước có quyền cao hơn | Phải còn hiệu lực, đúng tài khoản, giao dịch và phạm vi |

Ví dụ, người dùng chọn “tôi còn mã dự phòng” thì giao diện được phép mở bước nhập mã. Chỉ khi máy chủ xác minh mã hợp lệ, chưa dùng và đủ điều kiện cho hành động, giao dịch mới được chuyển tiếp.

## 4. Cây quyết định tổng quát

Sơ đồ dưới đây mô tả một thiết kế minh họa. Mỗi sản phẩm cần lựa chọn đường được phép theo chính sách và những phương thức thực sự hỗ trợ.

~~~mermaid
flowchart TD
    A[Bắt đầu từ điểm khôi phục chính thức] --> B[Xác định vấn đề và tạo ngữ cảnh giao dịch]
    B --> C{Có khai báo hoặc tín hiệu nghi bị chiếm?}
    C -- Có --> D[Đánh giá sự cố và tránh phụ thuộc duy nhất vào kênh bị nghi chiếm]
    C -- Chưa ghi nhận --> E{Còn đường đăng nhập được chính sách chấp nhận?}
    D --> E
    E -- Có --> F[Xác minh thực tế bằng phương thức còn lại]
    F --> G{Đủ quyền cho thay đổi cần làm?}
    G -- Có --> H[Cấp quyền giới hạn cho đúng thay đổi]
    G -- Chưa đủ --> I{Còn bằng chứng khôi phục phù hợp?}
    E -- Không --> I
    F -- Không xác minh được --> I
    I -- Có --> J[Xác minh bằng chứng trong giao dịch khôi phục]
    J --> K{Đạt điều kiện của đường khôi phục?}
    K -- Có --> H
    K -- Chưa đủ --> L{Có quy trình xem xét được hỗ trợ?}
    I -- Không --> L
    L -- Có --> M[Chờ xem xét theo quy trình có kiểm soát]
    M --> N{Yêu cầu được duyệt cho phạm vi cụ thể?}
    N -- Có --> H
    N -- Không --> O[Kết thúc hoặc bổ sung bằng chứng theo chính sách]
    L -- Không --> O
    H --> P[Thực hiện thay đổi và xử lý credential, session liên quan]
    P --> Q[Thông báo kết quả và hướng dẫn truy cập tiếp theo]
~~~

Sơ đồ không có cạnh “người dùng nói không còn gì nên cho phép bỏ kiểm tra”. Không có bằng chứng đủ điều kiện có thể dẫn đến xem xét, bổ sung bằng chứng hoặc kết thúc chưa khôi phục được.

Cạnh “còn đường đăng nhập” cũng không có nghĩa chỉ cần một lần nhập mật khẩu đúng. Đường đó phải đáp ứng những yêu cầu xác thực hiện đang áp dụng cho tài khoản. Nếu thiếu MFA bắt buộc, việc biết mật khẩu chưa hoàn thành đường đăng nhập đó.

## 5. Các nhánh mất quyền truy cập thường gặp

### 5.1. Quên mật khẩu nhưng vẫn còn yếu tố khác

Nếu dịch vụ hỗ trợ đặt lại mật khẩu, người dùng có thể đi qua kênh khôi phục được chính sách chấp nhận. Kết quả nên được mô tả đúng phạm vi: **được đặt lại mật khẩu**.

Nếu tài khoản vẫn yêu cầu TOTP sau khi đặt lại mật khẩu, hành trình cần nói rõ điều này. Không nên để người dùng hiểu rằng bước đặt lại đã giải quyết cả việc mất TOTP.

Một đường minh họa:

1. Người dùng chọn quên mật khẩu.
2. Hệ thống xử lý yêu cầu với phản hồi công khai không làm lộ tài khoản tồn tại.
3. Với tài khoản phù hợp, hệ thống gửi liên kết hoặc mã đến kênh đã xác minh theo chính sách.
4. Máy chủ xác minh bằng chứng và cho đặt mật khẩu mới.
5. Người dùng tiếp tục đăng nhập với các yêu cầu xác thực còn áp dụng.

Nếu người dùng báo cũng mất yếu tố thứ hai, cần chuyển sang đường phù hợp cho cả hai vấn đề. Không tự bỏ MFA chỉ vì mật khẩu đã đổi thành công.

### 5.2. Mất MFA nhưng còn phương thức đăng nhập khác

Người dùng có thể mất TOTP trên điện thoại nhưng vẫn giữ một phương thức khác mà chính sách cho phép đăng nhập. Hành trình nên ưu tiên cho họ thử phương thức còn lại trước khi đẩy sang quy trình mất toàn bộ yếu tố.

Sau xác thực, hành động thay MFA vẫn cần đáp ứng chính sách của thay đổi nhạy cảm. Một phiên đăng nhập cũ không nhất thiết đủ; hệ thống có thể cần xác minh lại và kiểm tra bối cảnh sự cố.

Quyền được cấp có thể là “thay TOTP bị mất”, thay vì “được đổi email, thêm passkey và gỡ mọi yếu tố”. Phần thu hồi phiên hoặc vô hiệu hóa phương thức bị mất phải được xác định rõ theo chính sách.

### 5.3. Không dùng được passkey trên thiết bị hiện tại

Không sử dụng được một passkey trên thiết bị hiện tại chưa chứng minh người dùng mất mọi passkey. Hành trình có thể cho người dùng thử:

- Authenticator khác đã đăng ký và còn sử dụng được.
- Khóa bảo mật hoặc thiết bị khác mà dịch vụ hỗ trợ sử dụng để xác thực.
- Passkey khả dụng qua cơ chế đồng bộ của hệ sinh thái, nếu người dùng vẫn truy cập được và dịch vụ hỗ trợ.

Dịch vụ chỉ nên chấp nhận kết quả xác thực đúng giao thức. Câu nói “tôi đã khôi phục tài khoản đồng bộ” không tự là bằng chứng cho ứng dụng; người dùng vẫn phải thực hiện xác thực bằng credential được ứng dụng chấp nhận.

Không hướng dẫn gửi khóa riêng của passkey qua email hoặc coi một tệp người dùng tải lên là bản thay thế mặc nhiên cho xác thực passkey.

Với tài khoản không dùng mật khẩu, hành trình không nên tự chuyển sang “đặt mật khẩu mới” nếu sản phẩm không có đường đó. Khôi phục có thể nhằm cho phép đăng ký authenticator mới sau khi đạt điều kiện, thay vì tạo thêm một phương thức ngoài thiết kế.

### 5.4. Mất thiết bị xác thực

Một thiết bị có thể chứa nhiều thành phần: passkey, TOTP, email đang đăng nhập, mã dự phòng và phiên ứng dụng. Vì vậy, nhãn “mất thiết bị” phải được phân tích thành những quyền và bằng chứng thực sự bị ảnh hưởng.

Cần giúp người dùng xác định:

- Có phương thức nào trên một môi trường khác còn sử dụng được không?
- Kênh nhận thông báo hoặc bằng chứng có nằm trên chính thiết bị đã mất không?
- Mã dự phòng có được lưu riêng hay cũng chỉ nằm trên thiết bị đó?
- Có cần xử lý những phiên còn hoạt động trên thiết bị bị mất không?

Không nên yêu cầu người dùng nhận mã trên một thiết bị họ vừa khai báo không còn kiểm soát, rồi không cung cấp lựa chọn khác.

Thiết bị mới là một tín hiệu bối cảnh cần đánh giá. Nó không tự chứng minh gian lận vì chủ tài khoản hợp lệ thường phải dùng thiết bị khác để khôi phục.

### 5.5. Còn mã dự phòng hoặc kênh khôi phục

Mã dự phòng, email hoặc số điện thoại có thể là các đường được chính sách hỗ trợ. Hành trình cần công bố điều kiện sử dụng theo cách dễ hiểu, nhưng máy chủ phải kiểm tra tính hợp lệ và phạm vi thật sự.

Đối với mã dự phòng, cần xử lý mã đã dùng, mã không hợp lệ, thử sai và việc hai yêu cầu cùng sử dụng một mã. Đối với liên kết khôi phục, cần kiểm tra hạn dùng, giao dịch, mục đích và trạng thái đã tiêu thụ.

Một email mới do người yêu cầu nhập có thể là nơi nhận thông tin liên lạc trong quy trình phù hợp, nhưng không tự chứng minh quyền với tài khoản cũ. Không được dùng quy trình vòng tròn: nhập email mới, nhận mã ở email đó, rồi coi mã là đủ để thay kênh khôi phục của tài khoản.

### 5.6. Không còn đường tự phục vụ đủ điều kiện

Khi không còn authenticator, mã dự phòng hoặc kênh được chính sách chấp nhận, cần nói rõ lựa chọn thực tế:

- Bổ sung bằng chứng theo một đường khác đã được thiết kế.
- Chuyển sang quy trình xem xét nếu sản phẩm có hỗ trợ.
- Kết thúc với thông báo chưa đủ căn cứ khôi phục nếu không có đường phù hợp.

Không nên hứa “hỗ trợ chắc chắn sẽ lấy lại tài khoản”. Một quy trình thủ công cũng cần bằng chứng và có thể không xác minh được người yêu cầu.

Đối với tài khoản không có căn cứ danh tính phù hợp để đối chiếu, việc yêu cầu giấy tờ có thể không giải quyết được quyền sở hữu. Sản phẩm cần xác định trước những đường được hỗ trợ thay vì thu thập thêm dữ liệu nhạy cảm mà không có mục đích xác minh rõ ràng.

## 6. Nhánh nghi tài khoản hoặc thiết bị bị chiếm

Nghi bị chiếm làm thay đổi mức tin cậy của bằng chứng. Nếu email bị chiếm, gửi mã đến email đó có thể tiếp tục trao quyền cho đối thủ. Nếu thiết bị bị xâm nhập, tạo bí mật mới trên thiết bị đó có thể khiến bí mật mới tiếp tục bị lộ.

Nhánh này nên xác định phạm vi sự cố và chọn bằng chứng không chỉ dựa vào môi trường bị nghi ảnh hưởng. Khi phù hợp, có thể hướng dẫn người dùng tiếp tục từ môi trường khác và dùng phương thức còn an toàn theo chính sách.

Tuy nhiên, dịch vụ thường không thể tự bảo đảm một thiết bị là sạch chỉ từ dữ liệu của một yêu cầu web. Cây quyết định cần làm việc với những gì có thể xác minh, không tạo một nhãn “thiết bị an toàn” chỉ vì người dùng bấm xác nhận.

Một nguyên tắc khác là tránh tạo công cụ gây từ chối dịch vụ. Người bất kỳ nhập email và chọn “tài khoản bị chiếm” không nên tự động có quyền khóa vĩnh viễn tài khoản hoặc thu hồi mọi credential của người khác.

Những hành động có tác động lớn cần bằng chứng, điều kiện hoặc cơ chế kiểm soát tương ứng. Hệ thống vẫn có thể ghi nhận báo cáo, áp dụng biện pháp chống lạm dụng và cung cấp hướng dẫn phù hợp trước khi cấp quyền thay đổi.

## 7. Thiết kế giao diện không làm lộ thông tin tài khoản

Cây quyết định thường bắt đầu khi người dùng chưa đăng nhập. Nếu nhập một email rồi giao diện hiển thị “tài khoản này có hai passkey, một TOTP và số điện thoại đuôi 1234”, hành trình có thể trở thành công cụ dò thông tin.

Ở phần công khai, có thể hỏi theo khả năng người dùng tự nhận biết, chẳng hạn:

- “Bạn có thể thử phương thức đăng nhập khác không?”
- “Bạn còn giữ mã khôi phục dự phòng không?”
- “Bạn có nghi một kênh hoặc thiết bị đã bị chiếm không?”

Không cần xác nhận phương thức đó thực sự có trong tài khoản trước khi người yêu cầu đạt điều kiện được phép xem thông tin tương ứng.

| Điểm trong hành trình | Cách diễn đạt hoặc xử lý minh họa |
| --- | --- |
| Sau khi gửi yêu cầu qua định danh | “Nếu thông tin phù hợp với một tài khoản có thể khôi phục theo cách này, hướng dẫn sẽ được gửi.” |
| Không dùng được phương thức hiện tại | Cho phép quay lại lựa chọn đường khác mà không xác nhận cấu hình riêng của tài khoản |
| Mã hoặc liên kết không được chấp nhận | Thông báo không thể tiếp tục bằng bằng chứng này; hướng dẫn yêu cầu mới hoặc thử đường phù hợp |
| Yêu cầu đang chờ xem xét | Hiển thị trạng thái qua cơ chế truy cập được phép, không qua mã hồ sơ dễ đoán công khai |
| Hoàn tất đặt lại mật khẩu | Nêu rõ mật khẩu đã đổi và những bước đăng nhập tiếp theo còn cần thực hiện |

Câu chữ chung không đủ nếu khác biệt mã phản hồi, thời gian xử lý, giới hạn thử hoặc các API phụ vẫn tiết lộ tài khoản tồn tại. Cần đánh giá toàn bộ hành vi quan sát được của phần công khai.

Chỉ hiển thị thông tin tài khoản theo quyền đã được xác minh và nhu cầu của bước hiện tại. Việc che một phần email hoặc số điện thoại không mặc nhiên làm cho thông tin đó an toàn để công khai.

## 8. Gắn cây quyết định với trạng thái giao dịch

Mỗi giao dịch khôi phục nên có tài khoản đích, hành động, thời điểm tạo, thời hạn, phiên bản chính sách và trạng thái do máy chủ quản lý. Các trạng thái dưới đây chỉ là mô hình minh họa cho ứng dụng.

| Trạng thái | Ý nghĩa | Chuyển tiếp hợp lệ minh họa |
| --- | --- | --- |
| Đã khởi tạo | Giao dịch có ngữ cảnh nhưng chưa có quyền thay credential | Chờ bằng chứng, hết hạn hoặc hủy theo quyền |
| Chờ bằng chứng | Đang chờ hoàn tất một bước xác minh | Chờ xem xét hoặc được cấp quyền nếu đạt điều kiện |
| Chờ xem xét | Đã chuyển tới quy trình được hỗ trợ | Bổ sung bằng chứng, được duyệt, bị từ chối hoặc hết hạn |
| Được cấp quyền giới hạn | Đủ điều kiện cho một hành động cụ thể trong thời hạn | Hoàn tất hành động, bị hủy, bị thu hồi quyền hoặc hết hạn |
| Đã hoàn tất | Thay đổi đã được ghi nhận theo phạm vi được cấp | Không thực hiện lại thay đổi bằng cùng quyền đã dùng |
| Đã hủy, hết hạn hoặc bị từ chối | Không còn được dùng giao dịch này để thay credential | Có thể khởi tạo yêu cầu khác theo chính sách |

Một số sự kiện phải được phân biệt:

- Gửi email thành công không đồng nghĩa xác minh email thành công.
- Nhập mã đúng không đồng nghĩa mã đủ để gỡ MFA.
- Được duyệt thay một yếu tố không đồng nghĩa được thay mọi kênh.
- Đổi credential thành công không đồng nghĩa mọi phiên cũ đã bị thu hồi.
- Đăng ký authenticator mới không chứng minh quyết định chấp nhận người đăng ký ban đầu là đúng.

### Các kiểm tra phải lặp lại ở thời điểm thực hiện thay đổi

Trước khi ghi thay đổi, máy chủ cần kiểm tra giao dịch vẫn còn hiệu lực, quyền chưa bị tiêu thụ hoặc thu hồi, hành động khớp phạm vi và các điều kiện cần thiết vẫn được đáp ứng.

Việc tiêu thụ quyền và thay đổi credential phải được xử lý nhất quán để hai yêu cầu đồng thời không cùng dùng một quyền một lần. Không chỉ đánh dấu “đã xác minh” trong trình duyệt rồi cho API thay đổi chạy mà không kiểm tra.

Các tác vụ liên quan như thu hồi phiên và gửi thông báo cần có trạng thái xử lý rõ ràng. Giao diện không nên tuyên bố “mọi thiết bị khác đã đăng xuất” nếu hệ thống chưa thực thi hoặc chưa có cơ chế bảo đảm điều đó.

## 9. Mã giả định tuyến phía máy chủ

Mã giả sau minh họa việc phân nhánh từ trạng thái đã kiểm chứng. Nó không quy định một chính sách dùng chung cho mọi sản phẩm.

~~~text
chooseRecoveryStep(transaction, verifiedState, policy):
    if transaction.isExpiredOrCancelled():
        return END_OR_START_NEW_REQUEST

    if transaction.isCompleted():
        return SHOW_EXISTING_RESULT

    require transaction.accountId is fixed
    require transaction.action is fixed

    incident = verifiedState.incidentContext

    if policy.requiresIncidentHandling(incident):
        applyAllowedIncidentControls(transaction, incident)

    if verifiedState.hasAcceptedAuthenticationFor(transaction.action):
        return AUTHORIZE_SPECIFIC_ACTION

    if policy.hasEligibleRecoveryRoute(
        transaction.action,
        verifiedState.evidence,
        incident
    ):
        return AUTHORIZE_SPECIFIC_ACTION

    if policy.hasAnotherPermittedEvidenceStep(
        transaction.action,
        verifiedState.evidence,
        incident
    ):
        return REQUEST_NEXT_EVIDENCE_WITHOUT_PUBLIC_DISCLOSURE

    if policy.supportsReview(transaction.accountClass, transaction.action):
        return ENTER_CONTROLLED_REVIEW

    return END_WITH_INSUFFICIENT_EVIDENCE
~~~

Ở đây, **verifiedState** là dữ liệu do máy chủ hình thành sau kiểm tra, không phải tập cờ do client gửi lên. Một giá trị như “hasBackupCode=true” từ trình duyệt chỉ có thể là lựa chọn giao diện, không phải bằng chứng đã được chấp nhận.

Khi người dùng muốn đổi từ “đặt lại mật khẩu” sang “thay email khôi phục”, phải tạo hoặc đánh giá lại phạm vi theo chính sách. Không tái sử dụng quyền của hành động trước một cách tự động.

Các nhánh có thể áp dụng giới hạn thử, thời gian chờ và thông báo. Các kiểm soát này giảm lạm dụng hoặc tạo cơ hội phát hiện; chúng không thay thế bằng chứng còn thiếu.

## 10. Xử lý các đoạn hành trình dễ gây vòng lặp

### 10.1. Người dùng không nhận được mã

Cần có lựa chọn kiểm tra hướng dẫn, gửi lại theo giới hạn hoặc thử đường khác nếu chính sách cho phép. Không yêu cầu người dùng xác nhận thông tin bí mật qua một kênh hỗ trợ tùy tiện.

Hệ thống cần quy tắc rõ cho mã cũ và mã mới: mã nào còn hiệu lực, thời hạn nào áp dụng và mã nào bị vô hiệu hóa. Hướng dẫn phải nhất quán với quy tắc thực tế để tránh người dùng thử một mã đã mất hiệu lực mà không biết.

Đường gửi lại cần chống quấy rối kênh liên hệ và không tự làm mất một giao dịch hợp lệ chỉ vì người ngoài liên tục gửi yêu cầu mới.

### 10.2. Người dùng mở liên kết trên thiết bị khác

Không nên coi trường hợp này mặc nhiên là gian lận; việc chuyển thiết bị có thể là chủ đích để tránh thiết bị bị mất hoặc bị nghi chiếm.

Tuy nhiên, phải tuân theo thiết kế ràng buộc của đường khôi phục. Nếu giao dịch yêu cầu một ngữ cảnh cụ thể, cần hướng dẫn cách tiếp tục hoặc khởi tạo lại theo chính sách. Không âm thầm bỏ ràng buộc chỉ để liên kết luôn hoạt động.

### 10.3. Người dùng mở nhiều tab hoặc bấm hoàn tất nhiều lần

Mọi tab phải dựa trên cùng trạng thái máy chủ. Khi một quyền đã được dùng, tab còn lại không được thay credential thêm lần nữa bằng quyền đó.

Một lần gửi lại cùng yêu cầu đã hoàn tất có thể trả về kết quả hiện có nếu thiết kế cho phép, nhưng không được lặp lại tác động. Việc nhận được phản hồi mạng chậm không có nghĩa thay đổi chưa xảy ra.

### 10.4. Người dùng quay lại sau một khoảng thời gian

Giao dịch có thể hết hạn, bằng chứng không còn đủ mới hoặc bối cảnh rủi ro đã thay đổi. Cần nói rõ bước nào phải làm lại và giữ đúng những gì vẫn được phép sử dụng.

Nếu cho phép tiếp tục giao dịch, thông tin tiếp tục phải được bảo vệ và có phạm vi phù hợp. Một mã hồ sơ dễ đoán không được trở thành quyền thay đổi tài khoản.

### 10.5. Người dùng muốn hủy

Hủy phải là một chuyển trạng thái được kiểm soát. Một thao tác công khai không có bằng chứng không nên có quyền hủy mọi giao dịch hợp lệ của một tài khoản khác.

Sau khi hủy, các quyền của giao dịch đó không còn được dùng. Nếu thay đổi đã hoàn tất, nút “hủy” không tự đảo ngược credential; cần xử lý theo đường sự cố hoặc thay đổi tiếp theo phù hợp.

## 11. Điểm chuyển sang hỗ trợ hoặc xem xét

“Liên hệ hỗ trợ” phải là một nhánh có quy trình, không phải lối thoát khỏi chính sách.

Một điểm chuyển giao rõ ràng cần xác định:

- Những loại tài khoản và tình huống được hỗ trợ.
- Bằng chứng nào cần bổ sung và mục đích của từng loại.
- Nhân viên được xem dữ liệu gì, được quyết định gì và hành động nào cần phê duyệt khác.
- Cách người dùng theo dõi trạng thái mà không làm lộ dữ liệu cho người khác.
- Điều kiện duyệt, từ chối, hết hạn hoặc yêu cầu bổ sung.
- Phạm vi quyền được cấp sau khi duyệt và cách ghi nhận quyết định.

Không yêu cầu người dùng gửi mật khẩu, OTP đang dùng hoặc mã khôi phục dự phòng cho nhân viên qua chat để “kiểm tra hộ”. Nếu một bằng chứng cần được sử dụng, nên sử dụng đúng bước xác minh được thiết kế cho nó.

Nhân viên biết nhiều thông tin hồ sơ của người yêu cầu cũng chưa tự chứng minh quyền sở hữu. Đối thủ có thể biết các thông tin đó từ dữ liệu bị lộ hoặc phiên đã bị chiếm.

Thời gian chờ và thông báo tới kênh cũ có thể hỗ trợ phát hiện, nhưng không có phản đối không đồng nghĩa yêu cầu hợp lệ. Chủ tài khoản bị mất quyền có thể không còn nhận được thông báo.

## 12. Bốn hành trình minh họa

### Trường hợp A: Quên mật khẩu, vẫn giữ TOTP

An chọn quên mật khẩu. Theo chính sách minh họa của dịch vụ, An nhận liên kết qua email đã xác minh, đặt mật khẩu mới và quay lại đăng nhập với TOTP.

**Điểm kết thúc:** mật khẩu được thay; yêu cầu TOTP vẫn còn. Nếu An không dùng được TOTP, hành trình tiếp tục sang đường mất MFA, không tự gỡ yếu tố đó.

### Trường hợp B: Mất điện thoại, còn khóa bảo mật

Bình không nhận được TOTP trên điện thoại đã mất nhưng còn passkey trên khóa bảo mật khác. Bình dùng phương thức đó để xác thực theo yêu cầu, rồi thực hiện giao dịch thay TOTP bị mất.

**Điểm kết thúc:** phương thức bị mất được xử lý theo chính sách; quyền thay email không được cấp kèm một cách tự động. Các phiên trên thiết bị mất được xử lý theo phạm vi sự cố.

### Trường hợp C: Tài khoản không dùng mật khẩu, mất mọi passkey

Chi không còn passkey nào sử dụng được và không có mã dự phòng. Chi chỉ còn email liên hệ.

Nếu chính sách không chấp nhận email đơn lẻ để đăng ký authenticator mới, giao dịch phải chuyển sang đường xem xét được hỗ trợ hoặc kết thúc chưa đủ bằng chứng. Không tự tạo đường đặt mật khẩu chỉ vì biểu mẫu quên mật khẩu đã có sẵn trong sản phẩm.

**Điểm kết thúc:** chưa có quyền truy cập mới cho tới khi đạt điều kiện. Hành trình mô tả đúng giới hạn thay vì hứa sẽ lấy lại tài khoản bằng mọi giá.

### Trường hợp D: Nghi email và thiết bị cùng bị chiếm

Dung báo trình duyệt có dấu hiệu bị kiểm soát, email cũng có thể bị truy cập trái phép. Dung còn một mã dự phòng được lưu riêng trước sự cố.

Hệ thống cho phép thử đường dùng mã dự phòng nếu chính sách hỗ trợ, kiểm tra mã trong giao dịch và cân nhắc những điều kiện liên quan. Nó không coi mã email gửi đến cùng môi trường bị nghi chiếm là lớp xác minh độc lập.

**Điểm kết thúc:** nếu đủ điều kiện, chỉ cấp quyền đã được duyệt và xử lý credential, session liên quan. Nếu chưa đủ, yêu cầu được giữ lại hoặc chuyển xem xét; việc Dung đã thử nhiều phương thức không tự nâng mức tin cậy.

## 13. Đánh giá chất lượng hành trình

Một hành trình có thể trông thuận tiện nhưng vẫn sai nếu một nhánh dự phòng cấp quyền quá rộng. Ngược lại, một hành trình có nhiều kiểm tra nhưng không có đường thực tế cho người mất thiết bị cũng có thể khiến chủ tài khoản bị mắc kẹt.

| Góc nhìn | Điều cần quan sát | Cách diễn giải |
| --- | --- | --- |
| Khả năng hoàn tất | Tỷ lệ hoàn tất theo từng đường và tình huống mất quyền | Giúp tìm các đường gây ngõ cụt hoặc hướng dẫn khó hiểu |
| Bỏ dở | Bước người dùng thường dừng lại | Có thể do không còn bằng chứng, lỗi gửi hoặc giao diện; cần phân biệt nguyên nhân |
| An toàn | Dấu hiệu khôi phục trái phép, thêm authenticator lạ hoặc yêu cầu vượt phạm vi | Giúp phát hiện nhánh dự phòng làm yếu chính sách |
| Hỗ trợ | Số lần chuyển xem xét, thời gian chờ và lý do từ chối | Phản ánh chất lượng đường tự phục vụ và quy trình xử lý |
| Vận hành | Lỗi gửi, bằng chứng hết hạn, xung đột trạng thái và tác vụ thu hồi chưa hoàn tất | Giúp phân biệt lỗi hệ thống với quyết định chính sách |
| Khả năng tiếp cận | Người dùng có thực hiện được bước cần thiết khi mất thiết bị hoặc có hạn chế thao tác không? | Cần lựa chọn khả thi mà vẫn giữ các điều kiện cấp quyền |

Việc đo lường phải tránh ghi token, OTP, mã dự phòng, cookie và tài liệu nhạy cảm vào log phân tích. Dữ liệu sự kiện nên đủ giải thích đường đi và quyết định, theo quyền truy cập và thời hạn lưu phù hợp.

Không tối ưu riêng số lần bấm hoặc tỷ lệ hoàn tất. Nếu tăng hoàn tất bằng cách cho mọi yêu cầu qua email đều gỡ được MFA, cây đã thay đổi mức bảo vệ của tài khoản.

## 14. Danh sách kiểm tra khi thiết kế cây

Một cây quyết định đủ rõ để triển khai cần trả lời được các câu hỏi sau:

- Tình huống người dùng chọn là dữ liệu định tuyến hay bằng chứng cấp quyền?
- Còn đường đăng nhập hợp lệ nào trước khi cần khôi phục đầy đủ không?
- Mỗi cạnh chuyển tiếp yêu cầu điều kiện nào được máy chủ xác minh?
- Bằng chứng có phụ thuộc vào chính thiết bị hoặc kênh đang bị nghi chiếm không?
- Phần công khai có làm lộ tài khoản, danh sách authenticator hoặc kênh liên hệ không?
- Mỗi đường cấp đúng hành động nào, trong thời hạn nào và tiêu thụ quyền ra sao?
- Có đường xử lý khi không nhận mã, hết hạn, mở nhiều tab, đổi thiết bị hoặc muốn hủy không?
- Khi không đủ bằng chứng, hệ thống chuyển xem xét hay kết thúc thế nào?
- Sau thay đổi, credential, session, thông báo và quyền còn lại được xử lý ra sao?
- Người dùng có hiểu rõ vấn đề nào đã giải quyết và bước đăng nhập nào vẫn còn không?

Giá trị của recovery journey decision tree nằm ở việc nối tình huống mất quyền với bằng chứng có thể xác minh và hành động được cho phép. Mỗi nhánh phải đưa người dùng đến một kết quả rõ ràng: tiếp tục với bằng chứng phù hợp, được thực hiện đúng thay đổi, chờ xử lý hoặc chưa đủ căn cứ để khôi phục.