# Recent credential change signal — Tín hiệu thay đổi thông tin xác thực gần đây

## 1. Vì sao một thay đổi gần đây lại đáng chú ý?

Trong khôi phục tài khoản, người yêu cầu có thể đang cố lấy lại quyền truy cập sau khi mất mật khẩu, MFA, passkey hoặc thiết bị. Nhưng kẻ đã chiếm được một phần quyền truy cập cũng có thể lợi dụng luồng này để củng cố quyền kiểm soát: đổi mật khẩu, thay kênh khôi phục, xóa MFA rồi đăng ký phương thức xác thực của mình.

**Recent credential change signal** là tín hiệu cho biết các yếu tố ảnh hưởng đến việc xác thực hoặc khôi phục tài khoản vừa thay đổi trong một khoảng thời gian được chính sách xác định.

Ví dụ:

> Một tài khoản vừa thay email khôi phục, sau đó yêu cầu gỡ MFA từ thiết bị chưa từng thấy. Việc người yêu cầu mở được đường dẫn gửi đến email mới không đủ để kết luận rằng họ là chủ tài khoản hợp lệ.

Tín hiệu này giúp hệ thống đặt câu hỏi: bằng chứng đang được dùng để khôi phục có còn độc lập và đáng tin, hay chính bằng chứng đó vừa được tạo ra trong một chuỗi chiếm đoạt?

Tuy nhiên, thay đổi gần đây **không đồng nghĩa với gian lận**. Người dùng thật cũng đổi mật khẩu sau cảnh báo rò rỉ, chuyển điện thoại hoặc bổ sung passkey. Hệ thống cần đánh giá loại thay đổi, nguồn gốc, thứ tự sự kiện và thao tác đang được yêu cầu.

## 2. Những sự kiện nào thuộc tín hiệu này?

### 2.1. Thay đổi thành công và có hiệu lực

Nguồn chính của tín hiệu nên là sự kiện được máy chủ xác nhận sau khi một thay đổi thực sự có hiệu lực.

| Nhóm sự kiện | Ví dụ | Ý nghĩa đối với khôi phục |
| --- | --- | --- |
| Mật khẩu | Đổi mật khẩu, hoàn tất đặt lại mật khẩu | Một người vừa thiết lập lại bí mật đăng nhập |
| MFA | Thêm phương thức, xóa phương thức, thay khóa TOTP | Cấu hình bảo vệ bổ sung đã thay đổi |
| Passkey | Đăng ký hoặc xóa một passkey | Tập thông tin xác thực được chấp nhận đã thay đổi |
| Recovery code | Tạo bộ code mới, vô hiệu bộ cũ | Bằng chứng dự phòng và vòng đời của nó đã thay đổi |
| Kênh khôi phục | Thay email hoặc số điện thoại khôi phục | Nơi nhận bằng chứng khôi phục có thể đã đổi chủ kiểm soát |
| Can thiệp quản trị | Nhân viên hỗ trợ thay phương thức hoặc đặt lại cấu hình | Có thay đổi qua luồng đặc quyền cần xác định nguồn gốc |

Email hoặc số điện thoại không phải lúc nào cũng là một thông tin xác thực đăng nhập. Chúng vẫn cần được xét nếu có thể nhận token, mã khôi phục hoặc phê duyệt thay đổi thông tin xác thực.

Đăng ký thêm một passkey trên tài khoản là một sự kiện có thể ghi nhận. Việc một nhà cung cấp đồng bộ passkey sang thiết bị khác không mặc nhiên tạo ra cùng một sự kiện đăng ký mới mà ứng dụng có thể quan sát. Tín hiệu chỉ nên dựa vào dữ liệu thực sự có, tránh suy diễn mọi biến động thiết bị thành một thay đổi credential đã được xác nhận.

### 2.2. Phân biệt yêu cầu, thử không thành công và thay đổi đã hoàn tất

Các sự kiện sau có giá trị khác nhau:

- Một người bấm “quên mật khẩu”.
- Hệ thống phát hành token khôi phục.
- Một lần đặt lại mật khẩu bị từ chối.
- Mật khẩu mới được ghi thành công.
- MFA cũ bị vô hiệu và phương thức mới được kích hoạt.

Nếu chỉ có yêu cầu quên mật khẩu mà đã gắn nhãn “mật khẩu vừa đổi”, kẻ tấn công có thể tạo tín hiệu giả cho tài khoản của nạn nhân mà không cần kiểm soát tài khoản.

Nên giữ các nhóm sự kiện riêng:

- **Yêu cầu hoặc lần thử:** phục vụ phát hiện lạm dụng và giới hạn tốc độ.
- **Thay đổi đã có hiệu lực:** phục vụ tín hiệu thay đổi credential gần đây.
- **Thay đổi đang chờ:** thể hiện trạng thái chưa hoàn tất và có thể cần kiểm soát riêng.
- **Thay đổi đã bị thu hồi hoặc sửa lại:** giữ lịch sử để hiểu chuỗi sự kiện, đồng thời phản ánh trạng thái hiện tại.

Một thay đổi bị đảo ngược không làm sự kiện ban đầu biến mất khỏi lịch sử an ninh. Ngược lại, lịch sử có sự kiện không có nghĩa phương thức đó vẫn còn hiệu lực.

## 3. Dữ liệu tối thiểu để tín hiệu có ý nghĩa

Một mốc thời gian kiểu `credentialsUpdatedAt` có thể là điểm khởi đầu, nhưng thường không đủ để giải thích một chuỗi khôi phục.

Ví dụ mô tả một sự kiện nội bộ:

```text
eventId: event-123
accountRef: mã tài khoản nội bộ
changeType: RECOVERY_EMAIL_REPLACED
state: APPLIED
effectiveAt: thời điểm thay đổi có hiệu lực trên máy chủ
observedAt: thời điểm hệ thống phân tích nhận được sự kiện
credentialVersion: 42
sourceFlow: AUTHENTICATED_SETTINGS
recoveryTransactionRef: NONE
actorClass: ACCOUNT_SESSION
authenticationContextRef: auth-context-456
```

Các trường chỉ mang tính minh họa. Cần chú ý những điểm sau:

1. **Loại thay đổi:** thêm một phương thức và xóa phương thức cuối cùng không có cùng ý nghĩa.
2. **Thời điểm có hiệu lực:** dùng để xác định sự kiện thuộc cửa sổ gần đây hay không.
3. **Thời điểm nhận sự kiện:** giúp nhận biết dữ liệu đến chậm, không thay thế thời điểm có hiệu lực.
4. **Nguồn thay đổi:** cài đặt tài khoản, luồng khôi phục, quản trị hoặc quy trình hệ thống.
5. **Bối cảnh xác thực:** phương thức nào đã cho phép thao tác, kết quả còn truy vết được không.
6. **Phiên bản trạng thái:** hỗ trợ phát hiện credential đã đổi sau lần đánh giá trước.
7. **Liên kết giao dịch:** phân biệt thay đổi thuộc chính giao dịch đang xử lý với thay đổi từ một giao dịch khác.

Máy chủ phải xác định các trường có tính quyết định. Không tin một request tự khai rằng thay đổi là “do chủ tài khoản thực hiện” hoặc “đã được MFA mạnh bảo vệ”.

Một phiên đã xác thực vẫn có thể bị chiếm quyền. Bối cảnh xác thực mạnh làm thay đổi cách đánh giá sự kiện, nhưng không tự chứng minh mọi hành động tiếp theo đều hợp lệ.

Không đưa mật khẩu, khóa TOTP, recovery code, token khôi phục hoặc dữ liệu bí mật của passkey vào bản ghi tín hiệu. Các định danh dùng để liên kết sự kiện nên là tham chiếu nội bộ được phân quyền và có thời hạn lưu phù hợp.

## 4. Định nghĩa “gần đây” bằng cửa sổ thời gian

### 4.1. Xác định đúng mốc tính

Giả sử:

- `t` là thời điểm máy chủ đang đánh giá yêu cầu.
- `w` là độ dài cửa sổ do chính sách chọn.
- `event.effectiveAt` là lúc thay đổi có hiệu lực.

Một quy ước minh họa:

```text
recent(event, t, w) =
    event.state == APPLIED
    and t - w <= event.effectiveAt
    and event.effectiveAt <= t
```

Cần quy định rõ sự kiện ở đúng ranh giới có được tính hay không. Ví dụ trên tính cả hai đầu mút.

Không dùng thời gian do trình duyệt gửi để quyết định tính gần đây. Nếu sự kiện mang thời gian tương lai so với mốc đánh giá, hệ thống cần xử lý bất thường đồng hồ hoặc dữ liệu; không biến nó thành “không có thay đổi gần đây”.

Độ mới của sự kiện và độ mới của kết quả đánh giá là hai vấn đề khác nhau. Một kết quả vừa được tính có thể dựa trên nguồn sự kiện đã bị chậm nhiều phút.

### 4.2. Một cửa sổ không phù hợp cho mọi thay đổi

Có thể cần những cửa sổ khác nhau cho:

- Đổi mật khẩu.
- Thêm một phương thức xác thực.
- Xóa MFA.
- Thay kênh khôi phục.
- Chuỗi nhiều thay đổi ảnh hưởng đến cùng một tài khoản.

Ví dụ một chính sách giả định có thể quan sát 30 phút cho chuỗi thay đổi dồn dập và 24 giờ cho thay đổi kênh khôi phục. Các con số này chỉ để minh họa cách thiết kế, không phải ngưỡng chuẩn để sao chép vào vận hành.

Việc chọn cửa sổ cần cân bằng giữa khả năng phát hiện chuỗi chiếm đoạt và mức cản trở người dùng thật. Tín hiệu cũng có thể mang tuổi của sự kiện thay vì chỉ một giá trị đúng hoặc sai.

### 4.3. Hết cửa sổ không có nghĩa tài khoản đã an toàn

Một kẻ tấn công vẫn có thể kiểm soát email hoặc phương thức xác thực sau khi cửa sổ “gần đây” kết thúc.

Vì vậy, phải tách riêng:

- **Tín hiệu theo thời gian:** thay đổi xảy ra gần đây đến mức nào.
- **Trạng thái hiệu lực:** phương thức nào đang được chấp nhận.
- **Trạng thái sự cố:** có cảnh báo chiếm quyền hoặc lệnh giữ đang hoạt động không.
- **Yêu cầu xác minh:** cần bằng chứng gì để thực hiện thao tác tiếp theo.

Không dùng việc hết thời gian chờ để tự phục hồi độ tin cậy của một phương thức đã bị xác định là bị chiếm quyền.

## 5. Đọc chuỗi thay đổi thay vì chỉ đếm sự kiện

### 5.1. Chuỗi cần tăng mức thận trọng

Một chuỗi có thể gồm:

```text
t0: đổi email khôi phục
t1: hoàn tất đặt lại mật khẩu qua email mới
t2: yêu cầu xóa MFA
t3: đăng ký passkey mới
```

Điểm đáng chú ý là email vừa thay được dùng ngay để mở đường cho các thay đổi tiếp theo. Nếu bước nào cũng chỉ kiểm tra phương thức “hiện đang đăng ký”, hệ thống có thể bỏ qua việc phương thức đó vừa được thiết lập trong cùng một chuỗi đáng ngờ.

Để hiểu chuỗi này, cần xem thứ tự, khoảng cách giữa các sự kiện và quan hệ phụ thuộc của bằng chứng. Ba sự kiện cùng được chuyển tới hệ thống phân tích không nhất thiết có cùng thời điểm xảy ra.

### 5.2. Chuỗi có thể hoàn toàn hợp lệ

Một người dùng chuyển sang điện thoại mới có thể:

1. Đăng nhập bằng passkey còn dùng được trên máy tính.
2. Thêm MFA cho điện thoại mới.
3. Xác minh phương thức mới.
4. Xóa MFA của điện thoại cũ.

Đây cũng là nhiều thay đổi trong một khoảng ngắn. Nhưng trình tự bổ sung rồi xác minh trước khi loại bỏ phương thức cũ và bối cảnh xác thực là những yếu tố khác với việc mất toàn bộ bằng chứng rồi liên tục thay kênh khôi phục.

Hệ thống vẫn cần đánh giá rủi ro; không nên gắn nhãn gian lận chỉ vì số sự kiện vượt một con số đơn giản.

### 5.3. Không cộng lặp cùng một sự kiện hoặc cùng một nguồn

Một thay đổi mật khẩu có thể tạo bản ghi trong dịch vụ xác thực, nhật ký bảo mật và kho sự kiện phân tích. Đếm cả ba như ba lần đổi mật khẩu sẽ làm tín hiệu sai lệch.

Cần định danh sự kiện để nhận biết bản sao. Đồng thời, các tín hiệu “credential vừa đổi”, “mật khẩu vừa đổi” và “password reset vừa hoàn tất” có thể cùng bắt nguồn từ một thay đổi duy nhất.

Nếu một bộ đánh giá sử dụng cả ba, cần xử lý quan hệ phụ thuộc thay vì mặc định chúng là ba bằng chứng độc lập.

## 6. Ví dụ: email mới không tự chứng minh quyền gỡ MFA

Giả sử tài khoản của Minh có email khôi phục và MFA. Lúc 09:00, một phiên đang đăng nhập thay email khôi phục. Lúc 09:08, một yêu cầu từ thiết bị mới muốn đặt lại mật khẩu và gỡ MFA.

### 6.1. Những điều hệ thống thực sự biết

- Email khôi phục mới đã có hiệu lực.
- Người gửi yêu cầu có thể nhận một token được gửi đến email mới nếu họ hoàn tất bước tương ứng.
- MFA cũ vẫn tồn tại hoặc đang ở một trạng thái xác định trong hệ thống.
- Chưa biết chắc phiên đổi email lúc 09:00 thuộc chủ tài khoản hay đã bị chiếm.

Hệ thống không được suy từ “mở được email hiện tại” thành “đã chứng minh độc lập quyền gỡ MFA”.

### 6.2. Cách dùng tín hiệu trong quyết định

Chính sách có thể chuyển yêu cầu sang xác minh bổ sung bằng một phương thức đã đăng ký trước thay đổi và vẫn đủ điều kiện sử dụng, hoặc sang quy trình xem xét có căn cứ nếu không còn bằng chứng phù hợp.

Việc chọn phương thức phải xét trạng thái thực tế. Nếu email cũ được thay vì đã bị chiếm quyền, tự gửi một liên kết phê duyệt toàn quyền về email cũ có thể tạo thêm rủi ro. “Có từ trước” là thuộc tính lịch sử, không tự bảo đảm phương thức còn an toàn.

Thông báo đến kênh phù hợp có thể giúp chủ tài khoản phát hiện thay đổi. Nhưng việc không phản hồi thông báo không phải bằng chứng chấp thuận; việc bấm liên kết báo cáo cũng cần có phạm vi và cơ chế xác minh phù hợp, tránh cho phép một thao tác đảo ngược tùy tiện.

### 6.3. Không khóa nhầm toàn bộ tài khoản chỉ vì có yêu cầu

Nếu một người lạ chỉ có thể khởi tạo yêu cầu khôi phục, họ không nên dễ dàng làm tài khoản của Minh bị khóa vĩnh viễn. Quyết định giữ hoặc từ chối giao dịch, giới hạn tốc độ và trạng thái tài khoản cần được thiết kế riêng.

Tín hiệu thay đổi đã có hiệu lực và tín hiệu nhiều yêu cầu chưa xác minh có thể cùng hỗ trợ phát hiện lạm dụng, nhưng chúng không phải cùng một sự kiện.

## 7. Phân biệt không có tín hiệu với không đủ dữ liệu

Một truy vấn không trả sự kiện có thể mang nhiều ý nghĩa:

- Tài khoản thực sự không có thay đổi trong cửa sổ đang xét.
- Dịch vụ sự kiện đang lỗi.
- Dữ liệu mới chưa đến kho phân tích.
- Lịch sử được giữ ngắn hơn cửa sổ của chính sách.
- Một luồng quản trị thay đổi credential nhưng chưa phát sự kiện.
- Việc đọc đang dùng một bản sao chưa đồng bộ.

Vì vậy, đầu ra không nên chỉ là `recentChange = false`.

| Trạng thái | Điều kiện diễn giải | Cách sử dụng |
| --- | --- | --- |
| `PRESENT` | Có thay đổi phù hợp đã được xác nhận trong cửa sổ | Cung cấp loại, tuổi và nguồn của thay đổi cho bộ quyết định |
| `ABSENT` | Nguồn đủ đầy và đủ mới cho phạm vi cần xét, không có sự kiện phù hợp | Chỉ kết luận không thấy thay đổi gần đây trong phạm vi đó |
| `UNKNOWN` | Chưa đủ cơ sở để kết luận có hay không | Áp dụng nhánh dữ liệu thiếu của chính sách |

Một kết quả `PRESENT` vẫn có thể đi kèm cờ lịch sử chưa đầy đủ. Biết chắc có một thay đổi không có nghĩa đã biết hết các thay đổi.

Để diễn giải `ABSENT`, hệ thống cần biết phạm vi dữ liệu đã được bao phủ, độ trễ nguồn và các luồng thay đổi có nằm trong cơ chế ghi nhận hay không. Nếu chỉ có lịch sử 2 giờ, không thể kết luận không có thay đổi trong 24 giờ.

Khi phiên bản credential hiện tại đã tăng nhưng nguồn sự kiện chưa phản ánh thay đổi tương ứng, nên coi đó là khoảng trống cần xử lý. Không lấy sự im lặng của kho phân tích làm bằng chứng tài khoản không đổi.

## 8. Chuyển tín hiệu thành hành động có phạm vi

Tín hiệu mô tả tình huống; chính sách quyết định hành động. Không nên để một bộ thu thập sự kiện tự cấp quyền hoặc xóa MFA.

Một số hướng xử lý theo ngữ cảnh:

| Tình huống | Hướng xử lý có thể được chính sách lựa chọn |
| --- | --- |
| Mật khẩu vừa đổi qua luồng có bằng chứng phù hợp, đang yêu cầu một thao tác ít nhạy cảm hơn | Tiếp tục đánh giá cùng các tín hiệu khác |
| Kênh khôi phục vừa thay, sau đó dùng chính kênh đó để yêu cầu gỡ MFA | Yêu cầu bằng chứng bổ sung đủ độc lập hoặc giữ giao dịch |
| Xóa phương thức cũ và thêm phương thức mới từ một bối cảnh đáng ngờ | Tăng mức thận trọng; chưa thực hiện thêm thay đổi nhạy cảm |
| Không thể xác định lịch sử thay đổi trong cửa sổ bắt buộc | Chuyển nhánh chưa biết; không mặc định cho phép |
| Có sự cố chiếm quyền đang hoạt động | Tuân theo điều kiện chặn hoặc quy trình sự cố, độc lập với tuổi sự kiện |

Các hành động cụ thể phải phù hợp với khả năng khôi phục đã được thiết kế. Nếu người dùng không còn phương thức xác minh bổ sung, không được tự thay nó bằng một câu hỏi dễ đoán chỉ để giảm tỷ lệ bỏ cuộc.

### 8.1. Không coi chờ đủ lâu là xác minh

Một khoảng trì hoãn có thể tạo thời gian để phát hiện hoặc xử lý thay đổi đáng ngờ. Nó không chứng minh ai đang kiểm soát tài khoản.

Nếu có thời gian chờ, cần xác định điều kiện để giao dịch được tiếp tục sau đó: bằng chứng nào còn hiệu lực, cảnh báo nào đã được xử lý và có phải đánh giá lại không. Không tự cho phép chỉ vì tín hiệu “recent” đã hết cửa sổ.

### 8.2. Không bỏ qua toàn bộ thay đổi thuộc giao dịch hiện tại

Một luồng khôi phục hợp lệ có thể tạo ra chính sự kiện mà bộ phát hiện đang quan sát, chẳng hạn đăng ký phương thức thay thế sau khi đã được xác minh.

Nếu mọi thay đổi của cùng giao dịch đều làm giao dịch đó bị chặn lại, hệ thống có thể tự tạo vòng lặp. Nhưng bỏ qua tất cả sự kiện có cùng `transactionId` cũng không an toàn.

Cần phân biệt thay đổi dự kiến với thay đổi ngoài phạm vi bằng các ràng buộc phía máy chủ:

- Giao dịch và mục đích được tạo, lưu và kiểm soát trên máy chủ.
- Thay đổi nằm trong phạm vi đã phê duyệt ở đúng bước của luồng.
- Bằng chứng cần thiết đã có trước khi cho phép bước đó.
- Sự kiện được liên kết bằng dữ liệu đáng tin, không dựa vào nhãn client tự gửi.
- Thay đổi từ phiên hoặc giao dịch khác vẫn được xét bình thường.

Không xóa sự kiện dự kiến khỏi lịch sử. Bộ quyết định có thể diễn giải nó theo bối cảnh; các giao dịch khôi phục mới sau đó vẫn cần nhìn thấy lịch sử phù hợp.

## 9. Ví dụ logic tạo tín hiệu

Mã giả dưới mô tả cách phân biệt có tín hiệu, không có tín hiệu và chưa biết. Đây không phải một dịch vụ hoàn chỉnh:

```text
evaluateRecentCredentialChange(account, evaluationTime, policy):
    snapshot = readCredentialSnapshot(account)
    history = readChangeHistory(account, policy.requiredWindow)

    matchingEvents = history.availableEvents
        .deduplicateBy(eventId)
        .filter(eventIsTrustedAndRelevant)
        .filter(eventHasAppliedChange)
        .filter(eventFallsInsideConfiguredWindow)

    gaps = detectCoverageFreshnessAndVersionGaps(snapshot, history)

    if matchingEvents is not empty:
        return signal(
            state = PRESENT,
            changes = summarizeWithoutSecrets(matchingEvents),
            dataGaps = gaps,
            credentialVersion = snapshot.version,
            evaluatedAt = evaluationTime
        )

    if gaps is not empty:
        return signal(
            state = UNKNOWN,
            dataGaps = gaps,
            credentialVersion = snapshot.version,
            evaluatedAt = evaluationTime
        )

    return signal(
        state = ABSENT,
        credentialVersion = snapshot.version,
        evaluatedAt = evaluationTime
    )
```

Một vài điểm quan trọng trong logic:

- Loại bỏ bản sao theo định danh đáng tin, không chỉ theo thời gian gần giống nhau.
- Áp dụng đúng cửa sổ cho từng loại thay đổi.
- Bản ghi không hợp lệ hoặc thời gian bất thường cần được đưa vào xử lý chất lượng dữ liệu, không âm thầm coi là không có thay đổi.
- Đầu ra giữ lại phiên bản trạng thái để bên quyết định có thể phát hiện thay đổi về sau.
- Tín hiệu `ABSENT` không phải bằng chứng danh tính và không tự cho phép khôi phục.

Nếu bằng chứng bắt buộc không hợp lệ, hệ thống vẫn phải từ chối hoặc giữ thao tác theo chính sách dù tín hiệu gần đây là `ABSENT`.

## 10. Duy trì tính nhất quán đến lúc hoàn tất khôi phục

Một rủi ro thường gặp là đánh giá đúng nhưng sử dụng kết quả quá muộn.

Ví dụ:

```text
10:00:00  Đánh giá giao dịch A tại credentialVersion = 42
10:00:02  Giao dịch B thay kênh khôi phục, phiên bản tăng thành 43
10:00:04  Giao dịch A dùng kết quả cũ để cho phép gỡ MFA
```

Nếu không đối chiếu trạng thái mới, giao dịch A có thể bỏ qua một thay đổi quan trọng xảy ra sau lúc đánh giá.

Thiết kế cần có cơ chế nhất quán phù hợp:

1. Gắn kết quả đánh giá với phiên bản hoặc mốc trạng thái mà nó đã đọc.
2. Trước khi thực hiện thao tác nhạy cảm, kiểm tra các thay đổi làm mất hiệu lực quyết định.
3. Nếu trạng thái đã đổi theo cách liên quan, đánh giá lại hoặc dừng giao dịch theo chính sách.
4. Thực hiện thay đổi và tiêu thụ quyền khôi phục dùng một lần bằng cơ chế giao dịch, điều kiện phiên bản hoặc cơ chế nhất quán tương đương.
5. Xử lý yêu cầu gửi lại mà không lặp lại thay đổi hoặc tạo thêm quyền mới.

Không nhất thiết mọi cập nhật hồ sơ đều làm credential version tăng. Cơ chế phiên bản cần có ngữ nghĩa rõ: những thay đổi ảnh hưởng đến xác thực và khôi phục nào sẽ làm quyết định cũ không còn dùng được.

Trong hệ thống nhiều dịch vụ, một số phiên bản ở các kho khác nhau chưa chắc tạo thành một snapshot nhất quán. Cần xác định nguồn chuẩn và giao thức kiểm tra, thay vì chỉ so sánh hai con số không cùng ý nghĩa.

Việc thu hồi credential hoặc session là một kiểm soát riêng. Một tín hiệu “vừa đổi mật khẩu” không thay thế việc thực thi chính sách thu hồi; ngược lại, token hoặc session đã bị thu hồi không được chấp nhận chỉ vì rủi ro tổng thể thấp.

## 11. Chống lạm dụng và bảo vệ dữ liệu của tín hiệu

### 11.1. Tránh biến tín hiệu thành công cụ gây khóa tài khoản

Một người chưa được xác minh thường có thể gửi yêu cầu quên mật khẩu cho tài khoản khác. Nếu mỗi yêu cầu tự tạo “credential vừa đổi” và kéo dài thời gian giữ, kẻ tấn công có thể liên tục cản trở nạn nhân.

Biện pháp thiết kế gồm:

- Tách sự kiện yêu cầu khỏi thay đổi đã có hiệu lực.
- Quản lý ngân sách thử và tốc độ yêu cầu theo nhiều phạm vi phù hợp.
- Phân biệt quyết định cho một lần thử, một giao dịch và toàn bộ tài khoản.
- Tránh cơ chế gia hạn thời gian giữ vô hạn chỉ bằng lưu lượng chưa được xác minh.
- Có đường xử lý cho chủ tài khoản còn bằng chứng đủ tin cậy theo chính sách.

Các trường hợp có bằng chứng sự cố thực sự vẫn có thể cần giữ tài khoản hoặc giao dịch. Điểm cần bảo toàn là quyết định đó có căn cứ phù hợp, không chỉ dựa vào số lượt bấm từ bên ngoài.

### 11.2. Không tiết lộ lịch sử nhạy cảm qua phản hồi công khai

Trước khi xác minh phù hợp, thông báo như “tài khoản vừa đổi email lúc 09:00” có thể làm lộ sự tồn tại và hoạt động của tài khoản.

Phản hồi công khai nên hướng dẫn bước tiếp theo mà không tiết lộ lịch sử, điểm rủi ro hoặc chi tiết điều kiện chặn. Nội dung dành cho chủ tài khoản sau khi xác minh và nội dung dành cho nhân viên xử lý cần được phân quyền riêng.

Bản ghi nội bộ có thể lưu các thông tin cần giải thích quyết định, chẳng hạn:

- Mã giao dịch và phiên bản credential.
- Loại thay đổi được xét và tuổi sự kiện.
- Trạng thái tín hiệu, khoảng trống dữ liệu.
- Phiên bản chính sách và quyết định cuối cùng.

Không cần đưa toàn bộ địa chỉ email cũ, số điện thoại đầy đủ hoặc bí mật xác thực vào từng bản ghi đánh giá. Phạm vi lưu, quyền đọc và thời hạn lưu cần phù hợp với mục đích xử lý.

### 11.3. Theo dõi chất lượng nguồn trước khi kết luận về người dùng

Tỷ lệ `UNKNOWN` tăng có thể do độ trễ sự kiện hoặc một luồng thay credential mới chưa được ghi nhận, thay vì do gian lận gia tăng.

Các đại lượng có thể giúp vận hành hiểu tín hiệu gồm độ trễ từ lúc thay đổi đến lúc quan sát, tỷ lệ thiếu phiên bản, số sự kiện trùng, tỷ lệ giao dịch bị yêu cầu xác minh thêm và các sự cố đã được xác nhận sau khôi phục.

Cần định nghĩa rõ mẫu số, khoảng thời gian và độ trễ của kết quả. Chưa có khiếu nại không đồng nghĩa với một yêu cầu đã được chứng minh là hợp lệ.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao gây vấn đề | Hướng xử lý |
| --- | --- | --- |
| Coi phát hành token là đổi mật khẩu thành công | Người ngoài có thể tạo tín hiệu giả | Dựa vào sự kiện thay đổi có hiệu lực |
| Chỉ lưu một mốc cập nhật chung | Không biết loại thay đổi và nguồn gốc | Giữ loại sự kiện và bối cảnh cần thiết |
| Mặc định không có tín hiệu khi kho sự kiện lỗi | Nhầm thiếu dữ liệu với không có thay đổi | Có trạng thái chưa biết riêng |
| Dùng email vừa thay để xác minh toàn bộ chuỗi thay đổi tiếp theo | Bằng chứng phụ thuộc vào chính thay đổi đang bị nghi ngờ | Xét quan hệ phụ thuộc và yêu cầu bằng chứng phù hợp |
| Cộng lặp các bản sao của một sự kiện | Phóng đại số lần thay đổi | Định danh và loại bỏ bản sao |
| Mọi thay đổi gần đây đều bị coi là gian lận | Cản trở người dùng chuyển thiết bị hợp lệ | Xét trình tự, nguồn và thao tác |
| Hết cửa sổ là tự chấp nhận khôi phục | Thời gian không chứng minh quyền sở hữu | Đánh giá lại bằng chứng và trạng thái sự cố |
| Bỏ qua mọi sự kiện cùng transaction ID | Có thể che thay đổi ngoài phạm vi | Chỉ diễn giải thay đổi dự kiến dựa vào trạng thái máy chủ |
| Không kiểm tra lại trước khi ghi | Dùng quyết định từ trạng thái credential cũ | Ràng buộc phiên bản và bước hoàn tất |

## 13. Điểm cần ghi nhớ

Tín hiệu thay đổi thông tin xác thực gần đây giúp phát hiện thời điểm mà các bằng chứng đăng nhập hoặc khôi phục có thể vừa bị thay đổi trong một chuỗi chiếm đoạt. Giá trị của nó nằm ở loại thay đổi, nguồn gốc, tuổi sự kiện, trình tự và quan hệ với bằng chứng đang được dùng.

Một thiết kế đáng tin cần phân biệt yêu cầu với thay đổi thành công, không có sự kiện với thiếu dữ liệu, và sự kiện lịch sử với trạng thái đang có hiệu lực. Kết quả phải hỗ trợ một quyết định có phạm vi, được đánh giá lại khi trạng thái liên quan thay đổi, đồng thời vẫn giữ đường khôi phục phù hợp cho chủ tài khoản thật.
