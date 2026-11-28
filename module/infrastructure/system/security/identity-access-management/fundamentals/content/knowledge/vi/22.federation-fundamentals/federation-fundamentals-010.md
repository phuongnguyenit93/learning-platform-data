# Single Logout

## 1. Single Logout giải quyết vấn đề gì?

**Single Logout (SLO)** là cơ chế phối hợp kết thúc các phiên đăng nhập liên quan trong một môi trường federation. Thay vì chỉ đăng xuất khỏi ứng dụng đang mở, một bên khởi tạo quy trình để các bên tham gia khác cũng xử lý phiên thuộc phạm vi cần kết thúc.

Ví dụ, nhân viên đăng nhập qua IdP công ty rồi sử dụng cổng nhân sự, ứng dụng chi phí và hệ thống báo cáo. Mỗi ứng dụng có thể giữ một phiên riêng. Khi nhân viên bấm “đăng xuất” ở cổng nhân sự, việc xóa phiên cổng đó không tự làm phiên ở hai ứng dụng còn lại biến mất.

SLO cố gắng nối các hành động này thành một quy trình phối hợp. Tuy nhiên, “single” không có nghĩa mọi phiên trên mọi thiết bị đều chắc chắn bị xóa tức thì. Kết quả phụ thuộc phạm vi giao thức, những bên có tham gia, khả năng tìm đúng phiên và kết quả xử lý tại từng bên.

Cần phân biệt ba khẳng định:

- Người dùng đã đăng xuất khỏi ứng dụng hiện tại.
- Phiên SSO tại IdP và các phiên liên quan đã được xử lý trong phạm vi phối hợp.
- Mọi phương thức truy cập, token và tài khoản của người dùng đã bị thu hồi.

Ba khẳng định này không tương đương nhau.

## 2. Những trạng thái cần được phân biệt

Trong một hệ thống liên kết danh tính, người dùng có thể đồng thời có nhiều loại trạng thái.

| Loại trạng thái | Nơi quản lý | Việc kết thúc một phiên web có tự xử lý không? |
|---|---|---|
| Phiên IdP/OP | Hệ thống cung cấp danh tính | Chỉ khi luồng có xử lý phiên đó |
| Phiên SP/RP | Từng ứng dụng | Cần ứng dụng vô hiệu hóa đúng phiên |
| Cookie trên trình duyệt | Theo miền và phạm vi cookie | Một ứng dụng không thể tùy ý xóa cookie của mọi miền |
| Access token | Client và cơ chế bảo vệ API | Phụ thuộc cơ chế hiệu lực, thu hồi và kiểm tra token |
| Refresh token | Client và authorization server | Cần chính sách cùng cơ chế xử lý riêng hoặc phối hợp |
| Khóa API và tài khoản cục bộ | Ứng dụng hoặc hệ thống quản trị | Thường nằm ngoài việc kết thúc phiên SSO |
| Kết nối đang mở | Ứng dụng, gateway hoặc dịch vụ | Cần xử lý nếu trạng thái xác thực đã được giữ trên kết nối |
| Tài khoản và quyền được cấp | Nguồn IAM và ứng dụng | Cần quy trình vòng đời hoặc thay đổi quyền |

Cookie thường chỉ là vật mang định danh hoặc dữ liệu phiên. Xóa cookie trong một trình duyệt không luôn chứng minh phiên phía máy chủ đã bị vô hiệu hóa. Ngược lại, vô hiệu hóa phiên phía máy chủ có thể khiến cookie còn tồn tại nhưng không còn sử dụng được.

Với cookie tự chứa được ký và không có kiểm tra trạng thái thu hồi, ứng dụng cần hiểu cách kết thúc hiệu lực trước hạn. Chỉ hiển thị trang “đã đăng xuất” không làm một bản cookie đã bị sao chép tự mất giá trị.

### Phiên hiện tại và mọi thiết bị

Một người có thể có phiên trên máy tính, điện thoại và một trình duyệt khác. Một thao tác logout có thể chỉ nhắm vào phiên SSO hiện tại, hoặc theo chính sách có thể yêu cầu phạm vi rộng hơn.

“Đăng xuất khỏi phiên này” và “đăng xuất mọi thiết bị” cần được thiết kế, ghi nhận và giải thích riêng. Không suy ra phạm vi toàn bộ thiết bị từ tên nút “Single Logout”.

## 3. Ai khởi tạo và ai truyền thông báo?

Có hai trục cần phân biệt.

**Trục khởi tạo** trả lời: người dùng hoặc hệ thống bắt đầu từ đâu? Có thể là ứng dụng, cổng IdP, hết hạn phiên hoặc một hành động quản trị được hỗ trợ.

**Trục truyền thông báo** trả lời: những bên khác được yêu cầu kết thúc phiên qua kênh nào? Có thể qua trình duyệt hoặc qua kết nối trực tiếp giữa các máy chủ.

| Góc nhìn | Ví dụ | Điều chưa tự xác định |
|---|---|---|
| SP/RP khởi tạo | Người dùng bấm logout ở ứng dụng | Thông báo đến các ứng dụng khác bằng kênh nào |
| IdP/OP khởi tạo | Đăng xuất tại cổng danh tính | Mọi ứng dụng có hỗ trợ nhận và xử lý thông báo hay không |
| Front-channel | Trình duyệt mang yêu cầu đến bên nhận | Máy chủ đã vô hiệu hóa đúng phiên hay chưa |
| Back-channel | Bên điều phối gọi trực tiếp endpoint bên nhận | Bên nhận tìm phiên bằng cách nào và xử lý ra sao |

Một luồng do RP khởi tạo có thể kết hợp cơ chế truyền thông báo khác. Không nên coi “RP-initiated”, “front-channel” và “back-channel” là ba lựa chọn luôn loại trừ nhau.

## 4. Single Logout trong SAML

SAML có cơ chế trao đổi `LogoutRequest` và `LogoutResponse`. Trong một luồng điển hình, SP khởi tạo yêu cầu; IdP phối hợp với các SP khác thuộc phiên liên quan rồi trả kết quả. Định danh chủ thể và thông tin phiên giúp bên nhận xác định phạm vi xử lý. [OASIS — SAML Technical Overview, Single Logout](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html).

```text
Người dùng → SP A: yêu cầu đăng xuất
SP A → IdP: LogoutRequest
IdP → SP B, SP C: yêu cầu kết thúc phiên liên quan
SP B, SP C → IdP: kết quả
IdP → SP A: kết quả phối hợp
```

Đây là sơ đồ khái niệm. Binding và cách trao đổi có thể khác giữa các chặng. Luồng phụ thuộc trình duyệt có thể bị gián đoạn; không nên coi việc bắt đầu SLO là bảo đảm hoàn tất ở mọi bên.

Khi triển khai, cần theo profile, binding và quy tắc xác minh tương ứng, thay vì tự xử lý XML bằng cách chỉ đọc tên tài khoản.

## 5. Các cơ chế logout trong OpenID Connect

Phía cung cấp danh tính trong OIDC là OpenID Provider (OP), còn ứng dụng là Relying Party (RP). Các cơ chế dưới đây bổ sung những phần khác nhau của quá trình logout.

### RP-Initiated Logout

RP yêu cầu OP đăng xuất người dùng thông qua logout endpoint. Luồng có thể dùng `id_token_hint` để cung cấp ngữ cảnh. Nếu dùng `post_logout_redirect_uri`, địa chỉ quay lại phải thuộc cấu hình đã đăng ký phù hợp; không chấp nhận một URL tùy ý từ đầu vào. [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html).

Cơ chế này xác định cách yêu cầu OP logout; nó không tự chứng minh mọi RP đã kết thúc phiên. Trang quay lại cũng không nên tự động khởi tạo đăng nhập ngay, khiến người dùng vừa logout đã có phiên mới.

### Front-Channel Logout

OP dùng trình duyệt để thông báo đến endpoint logout của RP. Khả năng truy cập nội dung hoặc trạng thái của bên thứ ba có thể ảnh hưởng việc xử lý, đặc biệt khi luồng sử dụng iframe. [OpenID Connect Front-Channel Logout](https://openid.net/specs/openid-connect-frontchannel-1_0.html).

Vì trình duyệt tham gia, cần kiểm chứng trên môi trường thực tế. Đóng tab, điều hướng hoặc mất mạng có thể khiến chuỗi chưa hoàn tất.

### Back-Channel Logout

OP gửi thông báo trực tiếp đến RP bằng Logout Token được ký. RP xác minh token theo quy tắc chuyên biệt rồi tìm và kết thúc phiên liên quan. Cơ chế không dựa vào việc đọc cookie trình duyệt, nên cần lưu liên kết phiên phù hợp ở phía ứng dụng. [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html).

Logout Token không phải ID Token để đăng nhập. Các token có mục đích khác nhau cần được phân biệt khi xác minh.

Back-channel giảm phụ thuộc trình duyệt, nhưng vẫn chịu lỗi mạng, endpoint và lưu trữ phiên. Nó không tạo ra bảo đảm thành công nếu ứng dụng chỉ nhận thông báo mà chưa xử lý trạng thái của mình.

## 6. Tìm đúng phiên trước khi kết thúc phiên

Phần khó của SLO thường là liên kết giữa phiên bên cung cấp danh tính và phiên cục bộ.

Một ứng dụng có thể cần lưu quan hệ khái niệm:

```text
Quan hệ tin cậy/issuer
    + tài khoản ngoài ứng dụng
    + định danh phiên liên kết nếu có
    + tenant hoặc phạm vi ứng dụng
        → một hoặc nhiều phiên cục bộ
```

Các định danh phiên phải được diễn giải đúng ngữ cảnh bên phát hành. Không lấy một chuỗi session ID rời khỏi issuer rồi tìm trên toàn bộ dữ liệu của mọi tổ chức.

### Không dùng email làm cơ sở duy nhất

Email có thể thay đổi hoặc tái sử dụng. Dùng email để vô hiệu hóa phiên có thể xử lý sai tài khoản hoặc không tìm được những phiên đã tạo trước khi email thay đổi.

Nên dựa trên liên kết danh tính được quản lý và các định danh mà giao thức cùng ứng dụng đã thống nhất.

### Phiên cụ thể và phạm vi theo chủ thể

Một thông báo có thể xác định phiên cụ thể hoặc phạm vi theo chủ thể, tùy cơ chế được sử dụng. Ứng dụng cần xử lý đúng ý nghĩa đó; không tự biến một yêu cầu hẹp thành xóa mọi phiên của mọi tài khoản có cùng tên.

Cũng không nên chỉ xóa phiên mà worker xử lý hiện đang nhìn thấy. Nếu người dùng có nhiều phiên cục bộ thuộc đúng phạm vi yêu cầu, cần tìm và xử lý đủ các phiên ấy.

### Nhiều instance và bộ nhớ đệm

Nếu ứng dụng chạy nhiều instance nhưng chỉ xóa phiên trong bộ nhớ của một instance, instance khác có thể vẫn chấp nhận truy cập.

Cần có nguồn trạng thái phiên có thẩm quyền hoặc cơ chế truyền trạng thái vô hiệu hóa nhất quán. Nếu các lớp cache có độ trễ, phải biết khoảng trễ đó và tác động của nó đến quyền truy cập.

Với kết nối dài hạn như WebSocket, việc chỉ kiểm tra phiên khi mở kết nối có thể không đáp ứng yêu cầu kết thúc truy cập đang tồn tại. Ứng dụng cần cơ chế kiểm tra lại hoặc ngắt kết nối khi chính sách yêu cầu.

### Cookie còn trong trình duyệt

Back-channel có thể vô hiệu hóa phiên tại máy chủ mà không trực tiếp xóa cookie đang nằm ở trình duyệt người dùng.

Điều quan trọng là lần dùng cookie tiếp theo không được phục hồi phiên đã bị vô hiệu hóa. Ứng dụng có thể dọn cookie khi người dùng tương tác lại, nhưng việc bảo vệ truy cập không được phụ thuộc hoàn toàn vào bước dọn đó.

## 7. Trình tự logout tại ứng dụng

Một thiết kế thường cần bảo đảm ứng dụng hiện tại có thể kết thúc phiên của mình ngay cả khi việc phối hợp bên ngoài gặp lỗi.

Luồng khái niệm:

```text
1. Xác định yêu cầu logout và phạm vi hợp lệ.
2. Ghi nhận những liên kết cần cho quy trình phối hợp.
3. Vô hiệu hóa phiên cục bộ theo chính sách.
4. Dọn trạng thái phía client trong phạm vi ứng dụng kiểm soát.
5. Khởi tạo hoặc tiếp tục logout liên kết nếu được hỗ trợ.
6. Theo dõi kết quả từng bên và giới hạn thời gian chờ.
7. Hiển thị kết quả đúng với mức đã xác nhận.
```

Đây là cách tổ chức trách nhiệm, không phải thứ tự bắt buộc cho mọi giao thức. Thư viện và nền tảng có thể cần giữ một số thông tin giao dịch đến khi xử lý phản hồi hoàn tất.

### Không phục hồi phiên vì bên khác lỗi

Nếu SP A đã kết thúc phiên nhưng không liên hệ được IdP, không nên khôi phục phiên SP A chỉ để trở lại trạng thái “đồng bộ”.

Kết quả cần thể hiện: phiên A đã đóng, phần logout liên kết chưa hoàn tất. Điều này khác với việc báo toàn bộ quá trình thất bại rồi để người dùng không biết phiên nào còn tồn tại.

### Không tự đăng nhập lại từ trang kết quả

Một vòng lặp thường gặp là logout xong điều hướng đến trang yêu cầu xác thực, trang đó tự chuyển sang IdP; nếu một phiên xác thực phù hợp còn tồn tại, người dùng lại được đăng nhập.

Cần thiết kế trang sau logout phù hợp mục đích: hiển thị trạng thái và cho người dùng chủ động đăng nhập lại. Tránh tạo cảm giác nút logout không hoạt động hoặc hiểu nhầm rằng phiên cũ vẫn còn trong khi thực tế hệ thống vừa tạo phiên mới.

### Trang đã tải không phải trạng thái xác thực

Sau logout, trình duyệt có thể vẫn hiển thị dữ liệu đã tải hoặc trang trong lịch sử. Logout không thể thu hồi thông tin người dùng đã nhìn thấy hay sao chép.

Ứng dụng cần bảo vệ các yêu cầu mới, quản lý cache phù hợp với độ nhạy cảm và dọn giao diện trong khả năng của mình. Chỉ việc màn hình cũ còn hiển thị chưa đủ chứng minh phiên còn hiệu lực; cần kiểm tra truy cập thực tế có được tiếp tục chấp nhận hay không.

## 8. Single Logout không đồng nghĩa thu hồi mọi token

Đây là một trong những nhầm lẫn quan trọng nhất.

Một access token có thể được API xác minh theo cơ chế riêng. Nếu token còn hiệu lực và API không nhận biết trạng thái thu hồi, việc kết thúc phiên web không tự làm API từ chối token đó.

Tương tự, refresh token có vòng đời và điều kiện sử dụng riêng. Chính sách cần xác định loại token nào gắn với phiên cần kết thúc và loại quyền truy cập nào được phép tiếp tục ngoài phiên tương tác.

| Mục tiêu | Các phần cần được xem xét |
|---|---|
| Đăng xuất khỏi một ứng dụng | Phiên ứng dụng và trạng thái client liên quan |
| Kết thúc phiên SSO liên kết | Phiên IdP cùng các phiên SP/RP thuộc phạm vi |
| Dừng truy cập API đã cấp | Access token, refresh token và cơ chế thực thi tại API |
| Xử lý tài khoản bị xâm phạm | Phiên, token, khóa, phương thức xác thực và hành vi liên quan theo phạm vi sự cố |
| Thu hồi người nghỉ việc | Trạng thái tài khoản, quyền, các đường đăng nhập và phương thức truy cập còn tồn tại |

Một ID Token đã hết hạn cũng không tự chứng minh phiên ứng dụng đã kết thúc. Token dùng làm kết quả xác thực và phiên được ứng dụng tạo sau đó là hai đối tượng có vòng đời khác nhau.

Không nên dùng một nút SLO làm toàn bộ quy trình thu hồi khẩn cấp hoặc deprovisioning. Các quy trình đó có thể sử dụng logout như một bước, nhưng còn cần xử lý quyền và phương thức truy cập khác theo kiến trúc thực tế.

## 9. Logout một phần là trạng thái vận hành cần quản lý

SLO đi qua nhiều hệ thống độc lập, nên có thể xuất hiện các kết quả khác nhau.

```text
Phiên ứng dụng A: đã vô hiệu hóa
Phiên IdP: đã kết thúc
Phiên ứng dụng B: bên nhận xác nhận xử lý
Phiên ứng dụng C: chưa nhận được kết quả
Token API ngoài phạm vi SLO: chưa đánh giá
```

Đây là kết quả rõ hơn một cờ `logoutSuccess=true`.

### Phân biệt bằng chứng

Cần tách các mức:

1. Đã tạo yêu cầu logout.
2. Đã gửi thông báo.
3. Đã nhận phản hồi từ bên nhận.
4. Trạng thái phiên tại bên nhận đã được xử lý theo hợp đồng giao thức.
5. Khả năng truy cập trong phạm vi cần kiểm tra đã được xác minh.

Một phản hồi thành công là bằng chứng mà bên nhận cung cấp theo giao thức. Nó không tự chứng minh những lớp ngoài phạm vi đó, chẳng hạn khóa API độc lập hoặc một ứng dụng không tham gia federation.

Nếu bên nhận chỉ ghi nhận yêu cầu vào hàng đợi, cần tránh mô tả kết quả trung gian là “mọi phiên đã bị vô hiệu hóa”. Hành vi phản hồi phải phù hợp với giao thức và mô hình xử lý được triển khai.

### Retry và tính lặp an toàn

Lỗi mạng có thể khiến một thông báo được xử lý nhưng phản hồi bị mất. Thử lại cần theo quy tắc giao thức và kiểm soát tải.

Thao tác kết thúc một phiên đã kết thúc nên không tạo thêm tác dụng phụ không mong muốn. Tuy nhiên, tính lặp an toàn không có nghĩa bỏ xác minh nguồn hoặc chấp nhận token không hợp lệ.

Một yêu cầu cũ không nên tùy tiện ảnh hưởng đến một phiên xác thực mới ngoài phạm vi của nó. Cần phân biệt định danh phiên, phiên bản trạng thái và ý nghĩa của yêu cầu theo chủ thể khi áp dụng.

### Giới hạn thời gian và chuyển cấp

Không để trình duyệt chờ vô hạn vì một bên không phản hồi. Cần có thời hạn, thông tin lỗi phù hợp và hành động tiếp theo.

Với ứng dụng nhạy cảm, phần chưa được xác nhận có thể cần chủ ứng dụng hoặc đội IAM xử lý. Với sự cố bảo mật, có thể cần các biện pháp vô hiệu hóa bổ sung được cho phép. Mức xử lý phải gắn với rủi ro và thẩm quyền, không tự mở rộng logout thành xóa tài khoản.

## 10. Bảo vệ endpoint và luồng logout

Logout làm thay đổi trạng thái bảo mật, nên cần được bảo vệ như một phần của giao thức.

### Xác minh bên phát và mục đích thông điệp

Đối với thông điệp đã được bảo vệ theo giao thức, bên nhận phải xác minh nguồn tin cậy, tính hợp lệ và đối tượng nhận theo cơ chế áp dụng.

Không chấp nhận một yêu cầu chỉ vì nó chứa subject hoặc session ID có vẻ đúng. Không dùng bộ xử lý ID Token làm bộ xử lý mọi JWT khác mà không kiểm tra mục đích.

Logout Token, phản hồi đăng nhập và access token có thể cùng có một số trường tương tự nhưng không được dùng thay thế nhau.

### Tương quan yêu cầu và điều hướng

Những bước cần tương quan phải gắn phản hồi với đúng giao dịch đang chờ. Địa chỉ quay lại cần được kiểm tra theo quy tắc đăng ký và cấu hình tin cậy.

Không sử dụng một tham số URL tự do làm lệnh điều hướng sau logout. Việc người dùng muốn rời ứng dụng không phải lý do cho phép chuyển hướng đến một địa chỉ không được kiểm soát.

### CSRF và endpoint giao thức

Luồng logout cục bộ cần bảo vệ khỏi những yêu cầu thay đổi trạng thái không mong muốn theo thiết kế ứng dụng.

Endpoint nhận thông điệp liên kết có thể dùng cách xác minh khác endpoint tương tác thông thường, đặc biệt khi bên gọi là máy chủ IdP chứ không phải trình duyệt có phiên. Không áp máy móc một cơ chế rồi vô hiệu hóa toàn bộ bảo vệ khi giao thức không hoạt động.

Mỗi endpoint cần biết ai được gọi, bằng chứng gì chứng minh lời gọi hợp lệ và phạm vi nào có thể bị ảnh hưởng.

### Tránh rò rỉ dữ liệu

Không ghi cookie, token hay toàn bộ assertion vào log. Nếu giao thức truyền một giá trị nhạy cảm qua trình duyệt, cần xét logging tại ứng dụng, proxy, công cụ theo dõi và trang đích để tránh sao chép giá trị đó ngoài mục đích cần thiết.

Báo lỗi cho người dùng cũng không nên tiết lộ danh sách tài khoản hoặc phiên của người khác.

## 11. Ví dụ: một IdP, ba ứng dụng

Mai đang sử dụng:

```text
IdP công ty
    ├── Ứng dụng A: chi phí
    ├── Ứng dụng B: nhân sự
    └── Ứng dụng C: báo cáo
```

Mai bấm đăng xuất liên kết tại A.

| Bước | Kết quả | Cách diễn giải |
|---|---|---|
| A vô hiệu hóa phiên cục bộ | Thành công | Không tiếp tục truy cập A bằng phiên đó |
| IdP xử lý phiên liên quan | Thành công | Phiên IdP trong phạm vi đã kết thúc |
| B nhận thông báo và kết thúc phiên | Thành công | B báo xử lý xong phiên tương ứng |
| C không truy cập được do lỗi mạng | Chưa xác định | Chưa có bằng chứng C đã kết thúc phiên |
| Mai mở trang kết quả tại A | Hiển thị trạng thái | Không tự khởi tạo lại luồng đăng nhập |

Thông báo phù hợp có thể là:

> Bạn đã đăng xuất khỏi ứng dụng này. Việc đăng xuất liên kết chưa được xác nhận đầy đủ ở một số dịch vụ.

Nếu phạm vi nghiệp vụ yêu cầu xử lý C, hệ thống tiếp tục theo dõi và chuyển chủ sở hữu. Không khẳng định “đã đăng xuất tất cả dịch vụ” chỉ vì A và IdP thành công.

Nếu Mai đồng thời đăng nhập trên điện thoại với một phiên khác, cần kiểm tra hành động vừa rồi có bao gồm phiên đó hay không. Nếu không, giao diện và báo cáo cần giữ đúng phạm vi.

Nếu đây là sự cố mất thiết bị, SLO có thể chưa đủ. Cần quy trình xử lý thiết bị, phiên, token và các phương thức truy cập liên quan theo chính sách.

## 12. Kiểm chứng thiết kế và theo dõi vận hành

Một ca logout thành công trên một trình duyệt chỉ chứng minh được một phần nhỏ.

Các tình huống cần được đưa vào kế hoạch kiểm chứng của hệ thống gồm:

| Tình huống | Câu hỏi cần trả lời |
|---|---|
| Đăng xuất cục bộ | Phiên máy chủ có bị vô hiệu hóa hay chỉ xóa cookie? |
| IdP không phản hồi | Phiên ứng dụng hiện tại có được đóng và kết quả có rõ không? |
| Một RP không nhận được thông báo | Có ghi nhận phần chưa hoàn tất và hành động tiếp theo không? |
| Trình duyệt gián đoạn luồng | Phần nào đã thực hiện, phần nào chưa được biết? |
| Thông báo sai issuer hoặc sai bên nhận | Có bị từ chối mà không ảnh hưởng nhầm phiên không? |
| Thông báo lặp | Có xử lý an toàn theo quy tắc giao thức không? |
| Nhiều instance ứng dụng | Phiên có bị từ chối trên mọi nơi cần thực thi không? |
| Nhiều tenant hoặc IdP | Có giữ đúng phạm vi danh tính và phiên không? |
| Nhiều thiết bị | Phạm vi kết thúc phiên có đúng với yêu cầu không? |
| Access token còn hạn | API xử lý ra sao, có nằm trong mục tiêu logout không? |
| Phiên mới sau logout | Có phân biệt phiên mới hợp lệ với trạng thái cũ không? |

Bằng chứng vận hành nên có định danh giao dịch, quan hệ tin cậy, phạm vi phiên, thời gian, bên nhận, kết quả và phần chưa xác minh. Các định danh nhạy cảm cần được bảo vệ; chỉ lưu mức chi tiết phục vụ điều tra.

Chỉ số hữu ích gồm thời gian xử lý, số bên không phản hồi, số lỗi ánh xạ phiên, độ trễ truyền trạng thái vô hiệu hóa và số trường hợp báo thành công nhưng truy cập bằng phiên cũ vẫn được chấp nhận.

Không gộp mọi kết quả vào một tỷ lệ thành công mà không biết mẫu số: một ứng dụng, một phiên liên kết, mọi bên tham gia hay toàn bộ thiết bị.

## 13. Những nhầm lẫn cần tránh

**Đóng tab là logout:** tab đóng không tự xóa phiên IdP hoặc phiên ứng dụng.

**Xóa cookie là hủy phiên máy chủ:** một bản định danh phiên khác có thể vẫn còn được chấp nhận nếu trạng thái máy chủ chưa bị vô hiệu hóa.

**Đăng xuất IdP là hết mọi phiên ứng dụng:** mỗi ứng dụng có trạng thái riêng và cần cơ chế phối hợp phù hợp.

**Back-channel luôn thành công:** nó giảm phụ thuộc trình duyệt nhưng vẫn phụ thuộc mạng, endpoint và quản lý trạng thái tại bên nhận.

**Một JWT hợp lệ có thể dùng cho mọi mục đích:** thông điệp logout phải được xác minh đúng loại, nguồn và phạm vi.

**SLO là deprovisioning:** logout không tự xóa tài khoản, thu hồi vai trò hoặc vô hiệu hóa khóa API.

**Một lần logout bao phủ mọi thiết bị:** phạm vi phải được xác định theo phiên và chính sách thực tế.

**Một bên lỗi thì mở lại phiên đã đóng:** hành động này làm mất tác dụng đã đạt được. Cần giữ phiên cục bộ đã kết thúc và theo dõi phần chưa hoàn tất.

**Hiển thị thành công là đủ:** kết luận phải gắn với trạng thái đã được xử lý và bằng chứng, không chỉ với trang giao diện.

Single Logout là một quy trình phối hợp kết thúc phiên trong phạm vi đã xác định. Để vận hành an toàn, cần tìm đúng phiên, kiểm tra thông điệp, xử lý trạng thái ở từng bên và phản ánh trung thực phần đã hoàn tất cùng phần còn chưa biết.
