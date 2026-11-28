# Token replay

## 1. Token replay là gì?

**Token replay** là việc một bên phát lại token hoặc bằng chứng bảo mật đã thu được để khiến hệ thống chấp nhận một yêu cầu không được phép. Kẻ tấn công có thể dùng nguyên giá trị đã lấy được mà không cần sửa claim, tạo chữ ký mới hoặc biết mật khẩu của người dùng.

Với bearer token, khả năng trình bày token là căn cứ quan trọng để sử dụng quyền của nó. Nếu token bị đánh cắp, chữ ký vẫn có thể hợp lệ và thời hạn vẫn còn. RFC 6750 mô tả token replay là tình huống kẻ tấn công thử sử dụng lại token đã được dùng trước đó tại resource server. [RFC 6750, mục 5.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-5.1)

Ví dụ, access token của nhân viên bị ghi vào log request. Một người đọc được log gửi chính token đó tới API hóa đơn trước khi token hết hạn. API có thể thấy cùng subject, issuer và scope như request hợp pháp; chỉ kiểm tra chữ ký sẽ không giúp nhận ra người gọi đã thay đổi.

Không phải mọi lần dùng lại token đều là tấn công. Một access token thường được thiết kế để sử dụng cho nhiều request trong thời gian hiệu lực. Vấn đề cần kiểm soát là ai có thể dùng credential, trong ngữ cảnh nào và bằng chứng nào phải mới cho từng lần sử dụng.

## 2. Một cuộc phát lại có thể diễn ra như thế nào?

Xét chuỗi sự kiện minh họa:

```text
09:00:00  Client nhận access token được phép đọc hóa đơn
09:00:05  Client gọi API; token vô tình xuất hiện trong log
09:01:00  Kẻ tấn công có quyền đọc log lấy được bản sao token
09:01:10  Kẻ tấn công gửi request mới kèm token đó
09:01:11  API kiểm tra chữ ký, issuer, audience và thời gian đều đạt
09:01:12  Nếu không có ràng buộc bổ sung, request có thể được chấp nhận
```

Những mốc trên cho thấy một token có thể bị dùng sai mà nội dung không bị thay đổi. Người tấn công đang lợi dụng quyền mà hệ thống đã cấp, nên việc phát hiện không thể chỉ dựa vào dấu hiệu token “bị sửa”.

Token có thể bị lộ qua mã độc hoặc XSS, kho lưu trữ không được bảo vệ, log và trace, công cụ hỗ trợ, URL, bản sao lưu hoặc một dịch vụ nhận nhầm credential. Mỗi đường rò rỉ cần được đánh giá ở điểm token được tạo, lưu, truyền và sử dụng.

Nếu kẻ tấn công dùng token bị đánh cắp trước cả client hợp pháp, hệ thống vẫn chịu nguy cơ sử dụng trái phép credential. Một cơ chế chỉ phát hiện “đã thấy token trước đây” không đủ để chứng minh lần sử dụng đầu tiên là hợp pháp.

## 3. Phân biệt các loại dùng lại

| Tình huống | Ý nghĩa đối với cơ chế bảo vệ |
| --- | --- |
| Client dùng cùng access token để đọc nhiều trang dữ liệu | Có thể hoàn toàn hợp lệ theo thiết kế |
| Kẻ tấn công lấy bearer token rồi gọi API | Sử dụng credential trái phép; cần ngăn rò rỉ và giới hạn khả năng sử dụng |
| Cùng một proof vốn phải mới cho từng request bị gửi lại | Cần kiểm tra độ mới và cơ chế phát hiện proof trùng |
| Refresh token đã bị thay thế trong một cơ chế rotation xuất hiện lại | Có thể là dấu hiệu lộ credential hoặc lỗi đồng thời cần được xử lý |
| Client thử lại yêu cầu thanh toán vì mất phản hồi | Cần cơ chế chống thực hiện nghiệp vụ hai lần, không chỉ xác minh token |

Trước khi xây replay cache, phải xác định đối tượng nào thực sự được phép dùng một lần. Nếu đánh dấu mọi access token là “đã dùng” ngay sau request đầu tiên, ứng dụng có thể hỏng khi tải tài nguyên thứ hai bằng cùng token.

Ngược lại, nếu một token khôi phục mật khẩu được thiết kế dùng một lần mà hệ thống chỉ kiểm tra ngày hết hạn, cùng credential có thể bị tiêu thụ nhiều lần trong khoảng còn hiệu lực.

## 4. Vì sao các kiểm tra thông thường chưa giải quyết hết replay?

| Biện pháp | Tác dụng | Giới hạn cần hiểu |
| --- | --- | --- |
| Xác minh chữ ký | Kiểm tra tính toàn vẹn và nguồn phát hành theo cấu hình | Bản sao token nguyên vẹn vẫn có chữ ký hợp lệ |
| Kiểm tra thời hạn | Giới hạn khoảng token có thể được chấp nhận | Kẻ tấn công vẫn có thể dùng trong khoảng còn hạn |
| Kiểm tra issuer và audience | Giới hạn nguồn tin cậy và bên nhận | Không tự phân biệt hai bên cùng trình bày một bearer token |
| TLS | Bảo vệ kênh truyền khi triển khai đúng | Không ngăn token bị lấy từ log hoặc thiết bị đã bị xâm nhập |
| Claim `jti` | Cung cấp định danh cho một JWT | Chỉ có ID không tự tạo ra trạng thái “đã sử dụng” |
| Mã hóa token | Hạn chế khả năng đọc nội dung | Một bản sao credential có thể vẫn được gửi nguyên vẹn để sử dụng |

Ví dụ, thêm một UUID vào `jti` không làm JWT trở thành token dùng một lần. Bên nhận phải biết chính sách của loại token và thực thi kiểm tra trạng thái thích hợp. Với access token được phép tái sử dụng, `jti` có thể hỗ trợ tra cứu thu hồi hoặc đối chiếu sự kiện mà không bị tiêu thụ sau mỗi request.

Giới hạn audience và scope vẫn có giá trị: chúng làm giảm những nơi và hành động mà bản sao token có thể được chấp nhận. Tuy nhiên, đó là giới hạn tác động, không phải bằng chứng rằng bên trình bày token là client hợp pháp.

## 5. Bảo vệ theo nhiều lớp

Một thiết kế IAM nên phối hợp các lớp sau thay vì chọn duy nhất một thuộc tính của JWT:

1. **Giảm cơ hội lấy được token.** Bảo vệ kênh truyền, kho lưu, máy client và hạ tầng xử lý log; không chuyển credential tới dịch vụ không cần nó.
2. **Giới hạn giá trị của token bị lộ.** Chọn quyền, audience và thời hạn phù hợp; tránh credential có phạm vi rộng và sống lâu không cần thiết.
3. **Ràng buộc việc sử dụng khi phù hợp.** Yêu cầu bằng chứng giữ khóa của bên gửi bằng một giao thức đã được hỗ trợ đầy đủ.
4. **Phát hiện dùng lại các bằng chứng phải mới.** Áp dụng trạng thái và thao tác nguyên tử cho proof hoặc token có chính sách dùng một lần.
5. **Có khả năng dừng quyền và điều tra.** Thiết kế thu hồi, cập nhật trạng thái, audit và xử lý sự cố phù hợp với độ trễ cho phép.

Ví dụ, access token có thời hạn ngắn nhưng refresh token bị lộ vẫn có thể cho phép lấy access token mới. Kế hoạch bảo vệ phải xem cả chuỗi credential, không chỉ token được gửi tới API nghiệp vụ.

Không có một thời hạn token cố định phù hợp với mọi ứng dụng. Giá trị cần được chọn dựa trên loại client, dữ liệu được truy cập, cơ chế thu hồi và khả năng bảo vệ credential.

## 6. Ràng buộc token với bên gửi

### 6.1. DPoP

DPoP ràng buộc token với khóa và yêu cầu client gửi proof cho request. Khi truy cập tài nguyên, API kiểm tra proof, liên kết khóa, method, URI và hash của access token. Proof có `jti`, thời điểm tạo và có thể cần nonce do máy chủ cung cấp. Một proof bị sao chép vẫn cần được kiểm soát replay trong cửa sổ nó được chấp nhận. [RFC 9449, mục 4, 7 và 11.1](https://www.rfc-editor.org/rfc/rfc9449.html#section-4)

Ý nghĩa trong ví dụ hóa đơn là: chỉ lấy được chuỗi access token chưa đủ nếu kẻ tấn công không có khả năng sử dụng khóa tương ứng. Nhưng nếu mã độc có thể ra lệnh cho client ký request, kể cả khi khóa không xuất được, nguy cơ vẫn cần được đánh giá.

DPoP không phải chữ ký toàn bộ nội dung nghiệp vụ của HTTP request. Không nên suy diễn rằng số tiền, query hoặc body đã được ràng buộc đầy đủ chỉ vì request có proof hợp lệ. Yêu cầu bảo vệ nội dung và chống xử lý giao dịch hai lần cần được thiết kế riêng.

### 6.2. mTLS và certificate-bound token

Với access token ràng buộc chứng thư mTLS, resource server xác minh bên gọi chứng minh quyền giữ khóa tương ứng với chứng thư mà token được ràng buộc. Chỉ xác thực client bằng mTLS khi xin token không tự đồng nghĩa mọi access token đã được certificate-bound. [RFC 8705, mục 3](https://www.rfc-editor.org/rfc/rfc8705.html#section-3)

Nếu TLS kết thúc tại reverse proxy, ứng dụng cần nhận thông tin chứng thư qua một đường tin cậy đã được thiết kế. Không tin một header do Internet tự gửi chỉ vì header có tên giống thông tin chứng thư client.

Cả DPoP lẫn mTLS đều cần được hỗ trợ nhất quán ở điểm phát hành và điểm sử dụng. API không được âm thầm nhận token đã ràng buộc như một bearer token thông thường khi thiếu bằng chứng cần thiết.

## 7. Replay cache phải theo đúng loại bằng chứng

Trước tiên, phân biệt các ID có thể cùng mang tên `jti`:

| Đối tượng | Chính sách minh họa |
| --- | --- |
| Access token được dùng nhiều lần | Không tiêu thụ ID sau request đầu tiên chỉ vì token có `jti` |
| Proof được yêu cầu mới cho từng request | Theo dõi ID proof trong cửa sổ áp dụng để phát hiện phát lại |
| Token khôi phục dùng một lần | Tiêu thụ token bằng thao tác nguyên tử theo giao dịch khôi phục |
| Refresh token có rotation | Theo dõi trạng thái và quan hệ token theo cơ chế rotation |

Với một bằng chứng dùng một lần, thao tác kiểu “kiểm tra chưa tồn tại rồi ghi vào cache” có thể có race condition:

```text
Request A kiểm tra: chưa thấy ID
Request B kiểm tra: chưa thấy ID
Request A ghi ID và được chấp nhận
Request B ghi ID và cũng được chấp nhận
```

Thiết kế cần thao tác nguyên tử có ý nghĩa “chỉ người đầu tiên ghi được”. Khóa cache phải có phạm vi phù hợp với giao thức, khóa mật mã, issuer hoặc endpoint liên quan, tránh nhập nhằng giữa những bên độc lập.

Trong một cụm nhiều node, trạng thái chống replay phải nhất quán trên toàn phạm vi mà cùng bằng chứng có thể được chấp nhận. Cache chỉ có ở một node có thể bỏ lọt request chuyển sang node khác.

Thời gian giữ bản ghi cần bao phủ đến khi bằng chứng không còn được chấp nhận, bao gồm dung sai đồng hồ thực tế. Nếu bản ghi hết hạn trước cửa sổ chấp nhận, proof cũ có thể được coi là mới sau khi cache quên nó.

Trước khi lưu trạng thái, xác minh cấu trúc, giới hạn kích thước và các kiểm tra bảo mật liên quan. Không để dữ liệu tùy ý chưa được tin cậy tạo ra vô số khóa hoặc TTL rất dài. Nếu kho chống replay lỗi, hệ thống phải có chính sách rõ ràng; một endpoint yêu cầu chống phát lại nghiêm ngặt không nên âm thầm bỏ kiểm tra rồi cấp quyền.

## 8. Refresh token rotation và phát hiện tái sử dụng

OAuth Security BCP yêu cầu authorization server dùng sender-constrained refresh token hoặc refresh token rotation để phát hiện refresh token replay đối với public client. Với rotation, mỗi lần refresh thành công nhận refresh token mới, token trước bị vô hiệu hóa và quan hệ giữa các token được giữ lại. Việc token đã bị vô hiệu hóa xuất hiện lại giúp phát hiện khả năng credential bị lộ. [RFC 9700, mục 4.14.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2)

Một chuỗi minh họa:

```text
RT-A --refresh thành công--> RT-B
RT-B --refresh thành công--> RT-C

RT-A xuất hiện lại:
  authorization server nhận ra token cũ đã được thay thế
  xử lý sự kiện theo cơ chế phát hiện reuse và thu hồi liên quan
```

Rotation không ngăn kẻ tấn công là người sử dụng credential bị đánh cắp đầu tiên. Giá trị của cơ chế còn nằm ở việc phát hiện khi một bên tiếp tục sử dụng nhánh cũ và dừng khả năng cấp token tiếp theo.

Client phải phối hợp các request refresh đồng thời. Ví dụ, nhiều tab hoặc nhiều request cùng thấy access token hết hạn không nên đồng loạt dùng cùng một refresh token rồi ghi đè token mới của nhau. Cần quản lý trạng thái refresh nhất quán và xử lý lỗi theo hợp đồng của nhà cung cấp.

Không tự thêm một khoảng cho phép token cũ dùng lại vô hạn để che lỗi đồng thời. Bất kỳ cơ chế retry hoặc dung sai nào cũng phải có giới hạn, được thiết kế trong mô hình phát hiện reuse và không làm mất khả năng nhận ra credential bị đánh cắp.

Thu hồi refresh token cũng không mặc nhiên làm mọi access token đã phát hành mất hiệu lực ngay. Khả năng dừng quyền ở resource server phụ thuộc cơ chế xác minh và thu hồi access token của hệ thống.

## 9. Replay credential và lặp giao dịch nghiệp vụ

Một client hợp pháp có thể gửi hai lần cùng yêu cầu do mất kết nối sau khi máy chủ đã xử lý. Ngay cả khi mỗi request có proof mới và token hợp lệ, giao dịch vẫn có thể bị thực hiện hai lần.

Với thao tác như thanh toán hoặc tạo lệnh chuyển tiền, có thể cần idempotency key hoặc một mã giao dịch được quản lý phía máy chủ. Thiết kế phải ràng buộc khóa đó với principal, hành động và nội dung yêu cầu cần thiết, đồng thời ghi nhận kết quả một cách nguyên tử.

Hai lớp kiểm tra giải quyết các câu hỏi khác nhau:

```text
Xác minh token và proof:
  Request này có credential được chấp nhận và quyền cần thiết không?

Kiểm soát tính lặp nghiệp vụ:
  Thao tác này đã được thực hiện hoặc đang được thực hiện chưa?
```

Idempotency key không thay thế kiểm soát truy cập. Người có token bị đánh cắp có thể thử tạo một yêu cầu mới với khóa khác; vì thế vẫn cần giới hạn credential và quyền. Ngược lại, DPoP không tự bảo đảm một thanh toán chỉ được ghi nợ một lần.

## 10. Quan sát và xử lý sự cố

Khi nghi ngờ token bị phát lại, cần thu thập đủ ngữ cảnh mà không tiếp tục làm lộ credential. Dữ liệu hữu ích có thể gồm issuer đã xác minh, principal, client, API đích, thời điểm, kết quả kiểm tra proof và mã sự kiện nội bộ.

Không ghi nguyên access token, refresh token hoặc proof vào log điều tra. Nếu cần đối chiếu credential, dùng một định danh hoặc dấu vết đã được thiết kế cho mục đích đó và được bảo vệ thích hợp.

Thay đổi IP, vị trí hoặc user agent có thể là tín hiệu bổ sung, nhưng không phải bằng chứng mật mã về bên gọi. Người dùng hợp pháp có thể chuyển mạng; kẻ tấn công cũng có thể hoạt động từ hạ tầng tương tự. Không thay sender constraint bằng một phép so sánh IP đơn giản.

Trong ví dụ token bị lộ qua log, việc xử lý cần bao gồm dừng quyền liên quan theo khả năng của hệ thống, loại bỏ nguồn ghi credential, giới hạn truy cập dữ liệu log đã lộ và xác định tác động nghiệp vụ. Chỉ cấp token mới mà giữ nguyên đường rò rỉ sẽ khiến sự cố lặp lại.

## 11. Các tình huống cần kiểm chứng

| Tình huống | Kỳ vọng của thiết kế |
| --- | --- |
| Client dùng access token nhiều lần theo đúng hợp đồng | Không bị chặn chỉ vì token đã xuất hiện trước đó |
| Bearer token bị sao chép nhưng còn hạn | Nhận diện đây là giới hạn cần giải quyết của mô hình bearer |
| Access token hết hạn hoặc sai audience | Không được chấp nhận chỉ vì từng hợp lệ trước đó |
| Token đã ràng buộc thiếu proof hoặc sai khóa | Không cấp quyền |
| Proof cũ được gửi lại trong cửa sổ chấp nhận | Cơ chế chống replay áp dụng phát hiện được theo chính sách |
| Hai node nhận cùng bằng chứng dùng một lần đồng thời | Không cùng tiêu thụ thành công |
| Bản ghi cache gần hết TTL trong khi còn clock skew | Không tạo khoảng trống cho proof cũ |
| Refresh token cũ xuất hiện sau rotation | Thực hiện đúng xử lý reuse và vòng đời credential liên quan |
| Client retry một giao dịch với proof mới | Kiểm soát nghiệp vụ ngăn thực hiện trùng theo thiết kế |
| Kho chống replay gặp lỗi | Thực thi chính sách lỗi đã định, có khả năng quan sát |

Thiết kế chống token replay bắt đầu từ việc xác định credential nào được tái sử dụng, bằng chứng nào phải mới và bên nhận dựa vào điều gì để tin người trình bày. Từ đó mới phối hợp bảo vệ token, thời hạn và phạm vi quyền, ràng buộc bên gửi, trạng thái chống phát lại và kiểm soát giao dịch phù hợp với hệ thống IAM.
