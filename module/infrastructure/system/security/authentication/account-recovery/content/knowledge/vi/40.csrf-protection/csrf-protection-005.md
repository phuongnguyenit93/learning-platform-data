# Referer validation — Kiểm tra Referer trong luồng khôi phục tài khoản

## 1. Referer cho biết ngữ cảnh xuất phát, không chứng minh danh tính

**Referer validation** là việc máy chủ kiểm tra thông tin nguồn của request thông qua header `Referer`, thường để bổ sung khả năng chống CSRF. Trong luồng khôi phục, mục tiêu là hạn chế một website khác lợi dụng trình duyệt đang có cookie hoặc ngữ cảnh khôi phục của người dùng để gửi hành động ngoài ý muốn.

Ví dụ một request hoàn tất đặt lại mật khẩu:

```http
POST /recovery/password HTTP/1.1
Host: accounts.example.com
Origin: https://accounts.example.com
Referer: https://accounts.example.com/recovery/new-password
Cookie: recovery_session=<opaque-value>
Content-Type: application/x-www-form-urlencoded

csrf_token=<secret>&new_password=<secret>
```

Cookie cho phép máy chủ tìm phiên khôi phục. Header nguồn giúp đánh giá request được phát sinh từ ngữ cảnh nào. CSRF token là một bằng chứng riêng gắn với tương tác mà máy chủ chấp nhận. Không nên coi ba loại dữ liệu này là một.

Tên header HTTP được viết là **`Referer`**, còn chính sách điều khiển việc gửi nó là **`Referrer-Policy`**. Cách viết khác nhau mang tính lịch sử; ứng dụng cần dùng đúng tên header. Ý nghĩa của `Referer` được mô tả trong [RFC 9110, mục 10.1.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.1.3).

Một `Referer` phù hợp không chứng minh người gửi là chủ tài khoản, không xác minh OTP và không cấp quyền gỡ MFA hoặc đăng ký passkey mới. Nó chỉ cung cấp thêm dữ liệu cho một quyết định bảo vệ request.

## 2. Áp dụng vào các thao tác thay đổi trạng thái

Trong thiết kế tham khảo của bài học, bảo vệ nguồn được áp dụng cho những request thay đổi trạng thái qua trình duyệt, chẳng hạn:

- Xác nhận bằng chứng để chuyển sang bước phục hồi có quyền cao hơn.
- Đặt lại mật khẩu.
- Xác nhận thay thế phương thức MFA hoặc passkey.
- Thay thông tin khôi phục sau khi đã xác minh.
- Hoàn tất hoặc hủy một hành động có tác động đến quyền truy cập.

Một phiên khôi phục có thể tồn tại trước khi người dùng đăng nhập bình thường. Vì vậy, không thể mặc định “chưa có session đăng nhập thì không có CSRF”. Cookie của một phiên khôi phục giới hạn cũng là ngữ cảnh mà trình duyệt có thể tự gửi.

Ngược lại, không nên yêu cầu mọi lượt mở link khôi phục đều có `Referer` từ chính miền tài khoản. Người dùng có thể mở link từ email, ứng dụng nhắn tin hoặc thanh địa chỉ.

Ví dụ:

```text
GET trang tiếp nhận link → có thể xuất phát ngoài website
POST thay credential → phải qua các bảo vệ của hành động
```

Trong ví dụ này, lượt GET không tự đổi mật khẩu, tiêu thụ grant hoàn tất hay gỡ yếu tố xác thực. Việc cho mở một trang không đồng nghĩa cho phép thực hiện hành động nhạy cảm.

## 3. Ưu tiên Origin, dùng Referer làm nguồn thay thế khi phù hợp

`Origin` biểu diễn nguồn theo scheme, host và port, không mang đường dẫn như một URL đầy đủ. `Referer` có thể cung cấp URL nguồn hoặc chỉ phần origin, tùy chính sách của trình duyệt. Xem [MDN: Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin) và [MDN: Referer](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer).

OWASP mô tả cách kiểm tra `Origin` trước và dùng `Referer` khi `Origin` không có. Nếu thông tin nguồn không xác lập được mức tin cậy, request cần bị từ chối hoặc phải đáp ứng một cơ chế chống CSRF khác đã được cấu hình. Tham khảo [CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#using-standard-headers-to-verify-origin).

Bài học đề xuất phân loại kết quả thay vì trả một boolean quá sớm:

| Kết quả | Ý nghĩa trong thiết kế tham khảo |
| --- | --- |
| `TRUSTED_SOURCE` | Header được chọn xác lập một origin nằm trong tập cho phép |
| `UNTRUSTED_SOURCE` | Header được chọn xác lập một origin ngoài tập cho phép |
| `SOURCE_UNAVAILABLE` | Không xác lập được origin, ví dụ thiếu cả hai header hoặc `Origin: null` |
| `REJECTED_HEADER` | Dữ liệu không đáp ứng cú pháp hoặc quy tắc tiếp nhận của endpoint |

Quy tắc lựa chọn của ví dụ:

1. Nếu có `Origin` hợp lệ, đối chiếu nó với tập nguồn được phép.
2. Nếu `Origin` không có, thử lấy origin từ `Referer`.
3. Nếu `Origin` hiện diện nhưng không khớp, không dùng một `Referer` khác để biến kết quả thành khớp.
4. Nếu `Origin` là `null`, không coi đó là cùng origin và không tự chuyển sang nhánh tin cậy.
5. Header trùng lặp, rỗng bất thường hoặc không phân tích được không được âm thầm biến thành một origin đã cấu hình.

Đây là chính sách xử lý cụ thể của ví dụ. Quan trọng là phân biệt **nguồn không tin cậy** với **không có đủ thông tin nguồn**; hai tình huống không tự động có cùng cách xử lý.

## 4. So sánh origin bằng cấu trúc, không tìm chuỗi con

Giả sử nguồn được phép là:

```text
https://accounts.example.com
```

Origin cần đối chiếu gồm:

```text
scheme + host + effective port
```

Ví dụ HTTPS không ghi port và HTTPS ghi port mặc định 443 có thể quy về cùng origin. Quy tắc origin và xử lý URL được định nghĩa trong [URL Standard](https://url.spec.whatwg.org/#concept-url-origin).

Không dùng các phép kiểm tra như:

```text
referer contains "accounts.example.com"
referer startsWith "https://accounts.example.com"
host endsWith "example.com"
```

Những chuỗi nhìn quen thuộc có thể xuất hiện trong host khác, userinfo, đường dẫn hoặc query.

| Giá trị Referer minh họa | Kết quả đối chiếu trong ví dụ |
| --- | --- |
| `https://accounts.example.com/recovery/form` | Khớp origin |
| `https://accounts.example.com/` | Khớp origin dù không có path của form |
| `https://accounts.example.com:443/recovery/form` | Khớp sau chuẩn hóa port mặc định |
| `http://accounts.example.com/recovery/form` | Không khớp scheme |
| `https://accounts.example.com:8443/recovery/form` | Không khớp port |
| `https://accounts.example.com.attacker.example/` | Không khớp host |
| `https://accounts.example.com@attacker.example/` | Không phải nguồn tài khoản được phép |
| `https://attacker.example/?next=https://accounts.example.com` | Không khớp; query không quyết định origin |

Bộ phân tích cần hiểu URL và authority. Trong ví dụ, endpoint chỉ nhận `Referer` là URL HTTP(S) tuyệt đối có cấu trúc phù hợp; không tự ghép một giá trị tương đối với origin đích để tạo ra kết quả “cùng nguồn”.

Đây là hạn chế tiếp nhận của endpoint, không phải tuyên bố rằng mọi dạng URI khác đều bị HTTP cấm.

Cũng không dùng một regex tự chế để thay toàn bộ quy tắc URL, IDN, port và ký tự phân cách. Thư viện phân tích phải có hành vi được hiểu rõ, còn tập origin được phép cần dùng cùng cách biểu diễn chuẩn hóa.

## 5. Không dùng path của Referer để cấp quyền

Một yêu cầu có thể chỉ gửi:

```http
Referer: https://accounts.example.com/
```

Ứng dụng không nên đòi phải có đúng `/recovery/new-password` rồi xem đó như bằng chứng người dùng đã đi qua bước trước. Chính sách referrer có thể loại bỏ path và query.

Ngay cả khi path có mặt, nó không thay thế trạng thái workflow được lưu ở máy chủ. Ví dụ, chuỗi `/recovery/verified` xuất hiện trong header không chứng minh OTP đã được xác minh.

Trong thiết kế của bài học:

- Header nguồn quyết định một phần điều kiện chống CSRF.
- Hồ sơ khôi phục quyết định tài khoản và trạng thái.
- Grant quyết định mục đích và phạm vi quyền.
- Chính sách bằng chứng quyết định còn cần xác minh gì.
- Trạng thái tiêu thụ quyết định một quyền dùng một lần còn hiệu lực hay không.

Một request có nguồn phù hợp nhưng hồ sơ chưa được phép thay MFA vẫn phải bị chặn ở lớp nghiệp vụ.

## 6. Xử lý thiếu Referer và Origin: chọn chính sách trước

`Referer` có thể vắng mặt vì chính sách riêng tư hoặc cách request được tạo. Không thể suy rằng request thiếu header là an toàn, cũng không thể kết luận mọi trường hợp thiếu đều là tấn công.

Hai chính sách tham khảo:

| Chính sách | Cách xử lý khi không xác lập được nguồn |
| --- | --- |
| Bắt buộc xác lập nguồn | Từ chối request nhạy cảm, kể cả khi người dùng có thể gặp giới hạn tương thích |
| Cho phép cơ chế thay thế đã cấu hình | Chỉ tiếp tục khi cơ chế chống CSRF độc lập, hợp lệ đáp ứng điều kiện của endpoint |

Ở chính sách thứ hai, “cơ chế thay thế” không phải chỉ có cookie, một cờ `isMobile=true`, hay giá trị User-Agent. Ví dụ của bài học dùng synchronizer token bí mật được máy chủ gắn với phiên khôi phục.

Việc cho phép thiếu nguồn phải do cấu hình đáng tin cậy quyết định. Client không được tự bật ngoại lệ bằng query, header tùy ý hoặc một field trong request body.

`Origin: null` có thể xuất hiện trong các ngữ cảnh trình duyệt không cung cấp tuple origin thông thường. Nó không phải tên của một origin cần đưa vào allowlist. Đặc điểm này được giải thích trong [MDN: Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin#description).

Trong chính sách tham khảo:

- Nguồn rõ ràng nằm ngoài tập cho phép bị từ chối.
- Header bị từ chối theo quy tắc cú pháp không đi qua nhánh ngoại lệ.
- Nguồn không khả dụng chỉ có thể qua cơ chế thay thế đã xác định.
- CSRF token vẫn được yêu cầu cho các request trình duyệt nhạy cảm của ví dụ, kể cả khi nguồn khớp.

Không tự biến một nhánh xử lý tương thích thành quy tắc “thiếu header thì cho qua”.

## 7. Phối hợp với Referrer-Policy để tránh lộ token

Trang khôi phục thường bắt đầu từ URL chứa bí mật. Nếu toàn bộ URL xuất hiện trong `Referer` của request khác, bí mật có thể đi qua những nơi không cần biết nó.

`Referrer-Policy: no-referrer` yêu cầu không gửi thông tin referrer. `strict-origin` chỉ gửi thông tin origin trong các điều kiện phù hợp và loại bỏ path, query. Các hành vi được mô tả trong [W3C Referrer Policy](https://www.w3.org/TR/referrer-policy/).

Ví dụ:

```http
Referrer-Policy: no-referrer
```

Chính sách này có thể phù hợp để giảm rò rỉ URL nhạy cảm, nhưng một bộ lọc bắt buộc `Referer` ở mọi POST có thể không tương thích với nó.

Cũng không nên khẳng định rằng bật `no-referrer` thì `Origin` luôn còn đầy đủ. Trong một số request không ở chế độ CORS, thuật toán Fetch có thể đặt giá trị `Origin` thành `null` theo referrer policy. Xem [Fetch Standard: append a request Origin header](https://fetch.spec.whatwg.org/#append-a-request-origin-header).

Từ đó, thiết kế cần nhất quán:

1. Xác định thông tin nào được phép rời trang khôi phục.
2. Chọn referrer policy phù hợp với dữ liệu nhạy cảm.
3. Chọn đường chống CSRF vẫn hoạt động với chính sách đó.
4. Không nới việc gửi URL đầy đủ chỉ để bộ lọc có thêm một header.

Nếu dùng chính sách giảm thông tin nguồn, ví dụ có thể tiếp tục dựa vào CSRF token hợp lệ theo nhánh đã cấu hình. Nếu bắt buộc xác lập nguồn, trải nghiệm và chính sách của trang phải đáp ứng điều kiện đó một cách rõ ràng.

Việc làm sạch URL sau bước tiếp nhận có thể giảm các lần lộ tiếp theo, nhưng không thay cho xác minh grant và không thu hồi một URL đã bị sao chép.

## 8. Origin đích và tập nguồn phải đến từ cấu hình đáng tin cậy

Trong một triển khai đơn giản, trang và endpoint cùng ở:

```text
https://accounts.example.com
```

Nhưng phía sau reverse proxy, ứng dụng có thể nhìn thấy:

```text
http://recovery-service.internal:8080
```

Không nên dùng địa chỉ nội bộ đó để kết luận nguồn trình duyệt bên ngoài là không hợp lệ. Ngược lại, cũng không được tin mọi giá trị `Host` hoặc `X-Forwarded-Host` từ request để dựng lại origin đích.

OWASP nêu lựa chọn cấu hình origin đích tại máy chủ và yêu cầu chỉ tin forwarding header từ proxy đã được tin cậy. Xem [Identifying the Target Origin](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#identifying-the-target-origin).

Ví dụ cấu hình của bài học:

```text
PUBLIC_RECOVERY_ORIGIN = https://accounts.example.com
ALLOWED_RECOVERY_FORM_ORIGINS = {
    https://accounts.example.com
}
```

Cấu hình cần gắn đúng môi trường và endpoint. Không dùng chung một danh sách quá rộng gồm mọi host phát triển, staging, đối tác và production.

Nếu frontend và API cố ý khác origin, sản phẩm cần quy định cặp nguồn–đích được phép. Cấu hình CORS là một phần tích hợp, nhưng không tự thay quyền khôi phục hoặc kiểm tra CSRF.

Ngoài ra, `https://support.example.com` và `https://accounts.example.com` là hai origin khác nhau. Việc cùng thuộc một tổ chức hoặc cùng site không tự cấp quyền cho cổng hỗ trợ phát sinh mọi hành động nhạy cảm của tài khoản.

## 9. Mã giả cho bộ bảo vệ có phân loại rõ ràng

Đây là mã giả cho **chính sách do bài học đề xuất**, không phải code thư viện có thể sao chép nguyên trạng:

```text
classifySource(request, allowedOrigins):
    reject duplicate or structurally invalid selected source headers

    if Origin header is present:
        if Origin is exactly "null":
            return SOURCE_UNAVAILABLE

        source = parseSingleSerializedHttpOriginStrictly(Origin)
        if parsing fails:
            return REJECTED_HEADER

        return TRUSTED_SOURCE if source in allowedOrigins
                              else UNTRUSTED_SOURCE

    if Referer header is present:
        sourceUrl = parseAbsoluteHttpUrlStrictly(Referer)
        if parsing fails or URL violates accepted-header rules:
            return REJECTED_HEADER

        source = normalizedOrigin(sourceUrl)
        return TRUSTED_SOURCE if source in allowedOrigins
                              else UNTRUSTED_SOURCE

    return SOURCE_UNAVAILABLE


protectRecoveryWrite(request, recoverySession, endpointPolicy):
    sourceDecision = classifySource(request, endpointPolicy.allowedOrigins)

    if sourceDecision in {UNTRUSTED_SOURCE, REJECTED_HEADER}:
        deny without changing recovery state

    requireValidSynchronizerToken(request, recoverySession)

    if sourceDecision == SOURCE_UNAVAILABLE:
        require endpointPolicy.allowUnavailableSourceWithValidCsrfToken

    require recoverySession is active
    require requested action is permitted
    require required recovery evidence is satisfied

    perform protected action with single-use and session controls
```

Các hàm phân tích trong ví dụ cần một hợp đồng chặt chẽ: không nhận danh sách origin tùy ý, không giải mã nhiều lần để “sửa” dữ liệu và không tự suy host bị thiếu.

Synchronizer token trong ví dụ là bí mật gắn với phiên khôi phục. Token chỉ được gửi theo kênh mà ứng dụng quy định và không xuất hiện trong URL để hỗ trợ kiểm tra nguồn.

Token khôi phục nhận qua email cũng không tự trở thành CSRF token cho mọi hành động. Muốn một bằng chứng đảm nhiệm một vai trò bảo vệ request, thiết kế phải chứng minh ràng buộc với phiên, mục đích và hành động tương ứng.

## 10. Phân biệt trình duyệt, API client và redirect hợp lệ

Kiểm tra header nguồn dựa vào hành vi của trình duyệt. Một chương trình HTTP độc lập có thể tự đặt `Referer` và `Origin`; các header này không phải chữ ký của người gửi.

Do đó:

- Không dùng `Referer` để xác thực ứng dụng mobile hoặc dịch vụ backend.
- Không coi một request đã đặt đúng header là bằng chứng sở hữu tài khoản.
- Không miễn bảo vệ request dùng cookie chỉ vì User-Agent trông giống SDK.
- Nếu cung cấp API cho client khác trình duyệt, cần xác định cơ chế xác thực và quyền phù hợp với API đó.

Với redirect từ nhà cung cấp danh tính, callback cần các bảo vệ của giao thức và trạng thái tương tác tương ứng. Không đưa toàn bộ miền của nhà cung cấp vào tập được phép gọi mọi endpoint đặt lại mật khẩu chỉ để xử lý một callback.

Tương tự, `Referer` từ webmail không được coi là bằng chứng rằng link do đúng chủ hộp thư mở. Trang tiếp nhận vẫn phải xác minh bí mật và chính sách khôi phục theo thiết kế.

## 11. Phản hồi và ghi nhận lỗi không làm lộ dữ liệu

Khi request bị từ chối, ví dụ sử dụng phản hồi công khai nhất quán như `403 Forbidden`, kèm hướng dẫn mở lại luồng từ trang chính thức nếu phù hợp.

Không cần trả về toàn bộ tập origin được phép hoặc nội dung header đã nhận để người dùng hiểu lỗi. Những chi tiết đó còn có thể chứa URL nhạy cảm.

Thông tin vận hành nên được phân loại:

```text
csrf_source_rejected
  request_id
  endpoint
  source_decision
  selected_header_type
  csrf_token_result
```

Không ghi nguyên `Referer` khi nó có thể chứa recovery token trong query. Nếu cần phân tích nguồn, chỉ giữ phần origin đã chuẩn hóa hoặc nhãn phân loại phù hợp chính sách dữ liệu.

Một request bị bộ bảo vệ từ chối không nên tiêu thụ recovery grant, thay credential hoặc thu hồi session của chính chủ. Tuy nhiên, hệ thống vẫn có thể ghi nhận sự kiện và áp dụng giới hạn chống lạm dụng theo chính sách riêng.

## 12. Ba tình huống áp dụng

### Origin không khớp nhưng Referer có chuỗi miền đúng

Không dùng phép tìm chuỗi để cho qua. Trong chính sách của bài học, `Origin` hiện diện và xác lập nguồn ngoài tập cho phép dẫn đến từ chối; `Referer` không được dùng để đảo kết quả.

### Người dùng hợp lệ có no-referrer và không xác lập được nguồn

Không tự gọi đó là tấn công. Nếu endpoint đã cấu hình cơ chế thay thế, request phải đáp ứng cơ chế đó. Nếu endpoint bắt buộc xác lập nguồn, request bị từ chối theo chính sách và cần đường tiếp tục phù hợp.

### Referer đúng nhưng hồ sơ chưa được phép thay MFA

Bảo vệ nguồn có thể đạt, nhưng yêu cầu nghiệp vụ vẫn không đạt. Máy chủ giữ nguyên yêu cầu bằng chứng và không biến quyền đặt lại mật khẩu thành quyền thay thế authenticator.

Kiểm tra Referer hữu ích khi được thực hiện bằng origin có cấu trúc, chính sách thiếu header rõ ràng và cấu hình nguồn đáng tin cậy. Nó bổ sung cho bảo vệ CSRF; quyền khôi phục vẫn phụ thuộc vào bằng chứng, phạm vi hành động và trạng thái được máy chủ xác minh.
