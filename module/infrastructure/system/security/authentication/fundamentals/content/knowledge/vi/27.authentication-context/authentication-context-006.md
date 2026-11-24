# Tín hiệu rủi ro

> **Chương:** Authentication context  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thu thập và đánh giá tín hiệu rủi ro trong lúc xác thực, hiểu giới hạn của IP, thiết bị, vị trí và hành vi, rồi chọn phản ứng phù hợp như cho phép, step-up, trì hoãn hoặc từ chối.

## 1. Tín hiệu rủi ro trong authentication context là gì?

**Tín hiệu rủi ro (risk signal)** là dữ liệu hoặc sự kiện giúp hệ thống ước lượng một yêu cầu xác thực có bất thường hay có khả năng bị lạm dụng hay không. Tín hiệu có thể đến từ request hiện tại, thiết bị, mạng, lịch sử tài khoản, hành vi đăng nhập hoặc thông tin tình báo về mối đe dọa.

Ví dụ, một nhân viên thường đăng nhập từ laptop công ty tại thành phố nơi họ làm việc. Một lần đăng nhập mới xuất hiện từ thiết bị chưa từng thấy, mạng ẩn danh và ngay sau đó thử nhiều mật khẩu sai. Các dấu hiệu này có thể khiến hệ thống yêu cầu passkey hoặc MFA bổ sung, giới hạn hành động nhạy cảm hoặc chuyển sang kiểm tra thủ công.

Tín hiệu rủi ro không phải bằng chứng chắc chắn rằng người dùng là kẻ tấn công. IP mới có thể do người dùng đi công tác; thiết bị mới có thể là máy vừa thay; vị trí suy ra từ mạng có thể sai. Một tín hiệu đơn lẻ thường chỉ là một phần ngữ cảnh để đánh giá.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, tín hiệu rủi ro giúp người học hiểu cách hệ thống điều chỉnh quy trình xác thực theo ngữ cảnh, bảo vệ credential và phiên, đồng thời tránh biến dữ liệu suy đoán thành kết luận về danh tính.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân loại tín hiệu mạng, thiết bị, vị trí, hành vi, tài khoản và credential.
- Đánh giá nguồn gốc, độ tin cậy, độ mới và giới hạn của từng tín hiệu.
- Phân biệt risk signal với bằng chứng xác thực và quyết định authorization.
- Thiết kế chính sách risk-based authentication và step-up.
- Xử lý false positive, false negative, tín hiệu thiếu và tín hiệu mâu thuẫn.
- Bảo vệ quyền riêng tư, giảm thiên lệch và kiểm thử khả năng chống né tránh.

## 2. Tín hiệu rủi ro nằm ở đâu trong luồng xác thực?

Hệ thống thường thu thập tín hiệu trước, trong và sau khi người dùng trình credential. Tín hiệu có thể ảnh hưởng đến quyết định xác thực, nhưng không được bỏ qua việc xác minh credential.

~~~mermaid
flowchart TD
    R["Request đăng nhập"] --> S["Thu thập tín hiệu"]
    S --> Q["Đánh giá chất lượng và độ mới"]
    Q --> E["Đánh giá rủi ro theo chính sách"]
    E --> D{"Mức rủi ro / yêu cầu"}
    D -->|"Thấp, đủ điều kiện"| A["Tiếp tục xác minh credential"]
    D -->|"Trung bình"| U["Step-up / xác thực bổ sung"]
    D -->|"Cao hoặc dấu hiệu rõ"| B["Giới hạn / từ chối / kiểm tra"]
    A --> V["Xác minh credential"]
    U --> V
    V --> C{"Xác thực thành công?"}
    C -->|"Không"| X["Từ chối và ghi nhận"]
    C -->|"Có"| Z["Authorization theo tài nguyên"]
~~~

Quy trình thực tế có thể đánh giá rủi ro trước khi chọn phương thức xác thực, rồi đánh giá lại sau khi nhận kết quả MFA/passkey. Ví dụ, một thiết bị mới có thể kích hoạt step-up; một passkey hợp lệ với user verification có thể giảm một số rủi ro, nhưng không làm mất các kiểm tra tài khoản và phân quyền.

### Tách ba loại quyết định

1. **Risk evaluation:** request có bất thường hoặc nguy cơ bị lạm dụng đến mức nào?
2. **Authentication:** chủ thể có chứng minh được quyền kiểm soát credential theo chính sách không?
3. **Authorization:** chủ thể đã xác thực có quyền làm gì trên tài nguyên cụ thể?

Không dùng risk score thay chữ ký WebAuthn, mật khẩu, MFA hoặc kiểm tra token. Cũng không dùng kết quả authentication thành công để mặc nhiên cho phép mọi hành động.

## 3. Nhóm tín hiệu thường gặp

### Tín hiệu mạng và nguồn truy cập

- Địa chỉ IP và ASN.
- Mạng doanh nghiệp, mạng di động, Wi-Fi công cộng hoặc hosting provider.
- VPN, proxy, Tor exit node hoặc dịch vụ ẩn danh.
- Quốc gia/khu vực suy ra từ IP.
- Danh tiếng IP và thông tin tình báo về botnet, scanner hoặc nguồn tấn công.
- Tốc độ request, tần suất thử đăng nhập và số tài khoản bị nhắm đến từ cùng nguồn.

IP có thể dùng chung qua NAT, thay đổi nhanh trên mạng di động hoặc bị định vị sai. VPN và proxy có thể hợp pháp; việc dùng chúng không tự chứng minh hành vi xấu. Reputation feed cũng có thể cũ, thiếu ngữ cảnh hoặc gán nhầm một dải địa chỉ.

### Tín hiệu thiết bị và client

- Thiết bị hoặc browser đã từng được đăng ký/ghi nhận.
- Hệ điều hành, phiên bản ứng dụng và phiên bản browser.
- Trạng thái cập nhật hoặc cấu hình bảo mật nếu nền tảng cung cấp bằng chứng đáng tin.
- Cookie hoặc mã thiết bị do ứng dụng quản lý.
- Kết quả attestation khi có cơ chế phù hợp và được tin cậy.
- Dấu hiệu client tự động, emulator hoặc môi trường bất thường.

User-agent và fingerprint có thể bị giả mạo, thay đổi sau cập nhật và gây nhận diện nhầm. Không coi một fingerprint là định danh bền vững hoặc bằng chứng một người cụ thể đang sử dụng thiết bị. Nếu dùng device binding/attestation, cần xác định chính xác bên phát hành và phạm vi bảo đảm.

### Tín hiệu vị trí và thời gian

- Vị trí gần đúng từ IP.
- Múi giờ hoặc thời điểm hoạt động.
- Khoảng cách và thời gian giữa hai lần đăng nhập.
- Mẫu di chuyển bất khả thi theo mô hình dữ liệu đã chọn.
- Đăng nhập vào thời điểm khác thường so với lịch sử tài khoản.

Vị trí IP chỉ là ước lượng, không phải tọa độ của người dùng. Mạng VPN, roaming, gateway tập trung và dữ liệu định vị lỗi có thể tạo impossible travel giả. Không yêu cầu người dùng cung cấp vị trí chính xác nếu không có nhu cầu rõ ràng.

### Tín hiệu hành vi

- Tần suất và nhịp nhập credential.
- Số lần thất bại, cách thử nhiều tên tài khoản hoặc mật khẩu.
- Mẫu điều hướng và thao tác bất thường.
- Thời gian từ đăng nhập đến hành động nhạy cảm.
- Thay đổi đột ngột về hành vi sử dụng hoặc quy mô giao dịch.
- Dấu hiệu automation hoặc thao tác lặp có tốc độ không tự nhiên.

Hành vi con người đa dạng. Người dùng có thể dùng công nghệ hỗ trợ, bàn phím khác, làm việc theo ca hoặc thay đổi thói quen. Không đánh đồng thao tác nhanh, chậm hoặc khác biệt với gian lận.

### Tín hiệu tài khoản và credential

- Tuổi tài khoản và lịch sử đăng nhập.
- Mật khẩu vừa được reset hoặc có dấu hiệu credential stuffing.
- MFA vừa bị thay đổi, thêm passkey mới hoặc xóa yếu tố dự phòng.
- Nhiều lần khôi phục tài khoản trong thời gian ngắn.
- Session/token mới được tạo từ ngữ cảnh khác thường.
- Credential bị báo mất, thu hồi hoặc xuất hiện trong nguồn rò rỉ đã được xác minh.
- Thay đổi email/điện thoại khôi phục, phương thức thanh toán hoặc quyền.

Tín hiệu thay đổi yếu tố xác thực đặc biệt quan trọng vì kẻ tấn công có thể tìm cách thay credential hoặc recovery method sau khi chiếm một phiên yếu.

## 4. Đánh giá chất lượng tín hiệu

Không phải mọi tín hiệu đều đáng tin như nhau. Trước khi đưa vào quyết định, hãy đánh giá ít nhất các chiều sau:

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| **Provenance (nguồn gốc)** | Ai tạo ra tín hiệu và qua kênh nào? | IP từ proxy tin cậy hay header do client tự gửi? |
| **Integrity (toàn vẹn)** | Tín hiệu có thể bị client sửa hoặc giả mạo không? | User-agent dễ giả; kết quả attestation cần xác minh nguồn |
| **Freshness (độ mới)** | Dữ liệu được tạo lúc nào? | Threat feed cập nhật vài phút hay vài tháng trước? |
| **Confidence (độ tin cậy)** | Mức chắc chắn của phép đo là bao nhiêu? | Vị trí IP gần đúng hay thiết bị đã được xác minh? |
| **Relevance (liên quan)** | Tín hiệu có liên quan tới rủi ro đang xét không? | VPN có thể không liên quan với nhân viên đi công tác |
| **Coverage (độ bao phủ)** | Tín hiệu có sẵn cho mọi nhóm người dùng không? | Một số thiết bị không cung cấp attestation |
| **Manipulability (khả năng bị thao túng)** | Kẻ tấn công có dễ thay đổi tín hiệu không? | IP có thể đổi qua proxy; cookie thiết bị có thể bị sao chép |

### Dữ liệu thiếu không có nghĩa là rủi ro cao

Một browser không gửi thông tin thiết bị có thể do quyền riêng tư hoặc chính sách nền tảng. Một nguồn threat intelligence không phản hồi có thể là sự cố dịch vụ. Không nên mặc định không biết đồng nghĩa đáng ngờ.

Hãy phân biệt:

- **Known benign:** có bằng chứng đáng tin cho thấy tín hiệu bình thường.
- **Known risky:** có bằng chứng phù hợp cho thấy nguy cơ tăng.
- **Unknown/unavailable:** không đủ dữ liệu để kết luận.
- **Conflicting:** nhiều nguồn đưa ra tín hiệu trái ngược.

Chính sách cần có cách xử lý từng trạng thái. Không biến sự cố của nhà cung cấp tín hiệu thành việc khóa hàng loạt người dùng.

### Không tin header do client tự khai

Header như X-Forwarded-For, X-Device-Trust hoặc trường trusted=true chỉ có thể được tin khi được tạo bởi proxy/gateway thuộc hạ tầng tin cậy và đường truyền được kiểm soát. Nếu client Internet có thể gửi trực tiếp header đó, attacker có thể tự khai IP hoặc thiết bị đáng tin.

Chuỗi proxy cần cấu hình rõ hop được tin; không lấy phần tử đầu tiên của header forwarding mà không xác minh nguồn. Tương tự, tín hiệu attestation phải được xác minh theo giao thức và trust store, không chỉ đọc kết quả do app gửi.

## 5. Từ tín hiệu đến risk score

Hệ thống có thể dùng luật, mô hình thống kê hoặc mô hình machine learning để kết hợp tín hiệu thành đánh giá rủi ro. Điểm số là một cách hỗ trợ chính sách, không phải chân lý về người dùng.

### Mô hình luật đơn giản

Ví dụ:

- Nhiều lần đăng nhập thất bại trong thời gian ngắn: tăng rủi ro.
- Thiết bị mới cộng với thay đổi recovery method gần đây: tăng rủi ro đáng kể.
- Passkey hợp lệ với user verification: có thể giảm rủi ro liên quan đến phishing/credential theft.
- IP từ VPN doanh nghiệp đã xác minh: không tự động tăng rủi ro.
- Nguồn tín hiệu không khả dụng: đánh dấu unknown và áp dụng fallback.

Không nên cộng điểm máy móc nếu các tín hiệu có tương quan. Ví dụ IP quốc gia lạ, ASN lạ và VPN đều có thể bắt nguồn từ cùng một đặc điểm mạng; cộng cả ba như ba bằng chứng độc lập sẽ phóng đại rủi ro.

### Ví dụ risk score minh họa

~~~text
risk_score = evaluate(
    network_context,
    device_context,
    account_history,
    credential_events,
    request_behavior
)

if risk_score >= HIGH_THRESHOLD:
    decision = "deny_or_manual_review"
elif risk_score >= STEP_UP_THRESHOLD:
    decision = "step_up"
else:
    decision = "continue"
~~~

Đây là mô hình khái niệm, không phải thuật toán chấm điểm có thể dùng trực tiếp. Ngưỡng phải được hiệu chỉnh bằng dữ liệu phù hợp, kiểm tra false positive/false negative, giám sát drift và phê duyệt bởi chủ sở hữu chính sách.

### Mô hình phải giải thích được

Khi một request bị yêu cầu step-up hoặc bị chặn, đội vận hành cần biết nhóm tín hiệu nào góp phần vào quyết định. Không cần phơi bày quy tắc chi tiết cho attacker, nhưng phải có audit đủ để điều tra, hỗ trợ người dùng và phát hiện lỗi.

Không lưu toàn bộ dữ liệu thô chỉ để giải thích mô hình. Có thể ghi mã lý do, phiên bản chính sách, mức confidence, thời điểm và nguồn đã dùng ở mức tối thiểu.

## 6. Risk-based authentication và adaptive authentication

**Risk-based authentication (RBA)** điều chỉnh mức kiểm tra dựa trên rủi ro của request. **Adaptive authentication** thường chỉ cách hệ thống thay đổi phương thức hoặc bước xác thực theo ngữ cảnh.

Ví dụ:

| Ngữ cảnh | Phản ứng có thể phù hợp |
|---|---|
| Thiết bị quen thuộc, credential hợp lệ, không có tín hiệu bất thường | Tiếp tục luồng xác thực thông thường |
| Thiết bị mới nhưng tài khoản và request không có dấu hiệu khác | Yêu cầu passkey hoặc MFA theo chính sách |
| Nhiều lần thử sai và dấu hiệu automation | Rate limit, challenge phù hợp hoặc tạm chặn nguồn |
| Thay đổi recovery method rồi yêu cầu hành động giá trị cao | Step-up bằng yếu tố đã đăng ký trước đó hoặc review |
| Tín hiệu mạnh về session/token theft | Thu hồi session/token và yêu cầu xác minh lại |
| Dữ liệu vị trí không khả dụng | Dùng tín hiệu khác hoặc fallback; không tự động từ chối |

RBA có thể giảm ma sát cho người dùng hợp lệ và tăng kiểm soát khi có dấu hiệu bất thường. Nhưng hệ thống phải đảm bảo mọi request vẫn đáp ứng mức xác thực tối thiểu bắt buộc; risk score thấp không cho phép bỏ qua yêu cầu MFA hoặc xác thực mạnh do chính sách quy định.

## 7. Step-up authentication

**Step-up authentication** yêu cầu người dùng chứng minh lại hoặc dùng phương thức mạnh hơn trước một request có rủi ro cao.

Ví dụ:

- Người dùng đăng nhập bằng session còn hiệu lực nhưng muốn thay email khôi phục.
- Nhân viên đã đăng nhập nhưng cần xuất toàn bộ dữ liệu.
- Tài khoản vừa đăng nhập từ thiết bị mới và muốn tạo API key.
- Người dùng thực hiện giao dịch vượt ngưỡng giá trị.

### Chọn yếu tố step-up

Ưu tiên yếu tố có mức bảo đảm phù hợp và độc lập với yếu tố có thể đã bị chiếm. Nếu rủi ro là phishing, yêu cầu thêm một OTP qua cùng kênh dễ bị phishing có thể không giải quyết gốc rủi ro. Passkey/WebAuthn gắn với RP ID/origin có khả năng chống phishing tốt hơn mật khẩu và OTP nhập tay.

### Ràng buộc step-up với hành động

Không chỉ hỏi người dùng vừa xác thực lại chưa. Cần gắn kết quả với:

- Chủ thể và session đang thực hiện hành động.
- Phương thức và mức xác thực đã hoàn tất.
- Thời điểm xác thực và thời hạn freshness.
- Tài nguyên/hành động cụ thể nếu quy trình yêu cầu.
- Nonce/challenge hoặc transaction context để tránh dùng lại kết quả cho hành động khác.

Một step-up thành công để xem hồ sơ không nhất thiết đủ cho việc đổi chủ sở hữu tài khoản hoặc chuyển tiền. Các hành động có giá trị cao có thể cần xác nhận giao dịch riêng hoặc phê duyệt độc lập.

## 8. Tín hiệu và credential/session

Risk engine nên hiểu các sự kiện trong vòng đời credential:

- Credential mới được đăng ký.
- Passkey hoặc khóa bảo mật bị thu hồi.
- MFA bị reset hoặc phương thức dự phòng được thay đổi.
- Mật khẩu bị đổi sau sự kiện nghi ngờ.
- Refresh token reuse hoặc session xuất hiện đồng thời ở ngữ cảnh bất thường.
- Người dùng yêu cầu recovery hoặc support override.

### Không dùng thiết bị quen thuộc làm yếu tố duy nhất

Cookie remember-this-device có thể bị sao chép cùng session hoặc bị malware lấy cắp. Device fingerprint cũng có thể thay đổi sau cập nhật hoặc bị giả mạo. Một thiết bị quen thuộc chỉ là tín hiệu phụ; nó không thay thế credential và không tự chứng minh người dùng hiện tại là chủ tài khoản.

### Thay đổi yếu tố xác thực cần kiểm soát

Khi thêm passkey mới, reset MFA hoặc đổi số điện thoại khôi phục:

1. Xác thực lại bằng phương thức đã đăng ký phù hợp.
2. Đánh giá risk context và lịch sử sự kiện.
3. Thông báo qua kênh liên hệ đã xác minh.
4. Có thời gian chờ hoặc giới hạn hành động nhạy cảm khi phù hợp.
5. Ghi audit và cho phép thu hồi nếu người dùng không nhận ra thay đổi.

Không để một phiên yếu có thể vừa thay toàn bộ phương thức xác thực, vừa tắt cảnh báo và thực hiện giao dịch giá trị cao.

## 9. False positive, false negative và phản ứng có tỷ lệ

**False positive** xảy ra khi request hợp lệ bị đánh giá là rủi ro. **False negative** xảy ra khi request độc hại được đánh giá là bình thường.

| Sai lệch | Tác động | Cách giảm |
|---|---|---|
| False positive | Khóa nhầm, gây gián đoạn, người dùng mất khả năng truy cập | Step-up thay vì từ chối khi phù hợp; fallback và khiếu nại |
| False negative | Attacker vượt qua kiểm soát | Kết hợp tín hiệu độc lập, giám sát sau đăng nhập, giới hạn hành động |
| Thiếu tín hiệu | Không đủ dữ liệu để đánh giá | Chính sách unknown rõ ràng và phương thức xác thực tối thiểu |
| Tín hiệu lỗi thời | Đánh giá sai do dữ liệu cũ | TTL, freshness và nguồn cập nhật |
| Model drift | Mô hình giảm chính xác theo thời gian | Theo dõi chất lượng, hiệu chỉnh và rollback |

### Phản ứng theo mức độ

Không phải request bất thường nào cũng cần khóa tài khoản. Có thể lựa chọn:

- **Allow:** tiếp tục nếu mọi yêu cầu xác thực và chính sách đạt.
- **Observe:** cho phép nhưng tăng giám sát với dữ liệu tối thiểu.
- **Rate limit:** giảm tốc độ thử đăng nhập hoặc hành động lặp.
- **Step-up:** yêu cầu passkey/MFA hoặc xác thực lại.
- **Restrict:** giới hạn một số hành động nhạy cảm.
- **Hold/manual review:** tạm giữ giao dịch hoặc chuyển người có thẩm quyền.
- **Deny/revoke:** từ chối và thu hồi phiên khi có bằng chứng đủ mạnh.

Phản ứng cần tỷ lệ với rủi ro và hậu quả. Một request bị chặn nên có quy trình khôi phục hợp pháp, nhưng thông báo không nên tiết lộ toàn bộ logic phát hiện cho attacker.

## 10. Kẻ tấn công có thể né tín hiệu như thế nào?

Risk signal thường quan sát những gì client và môi trường thể hiện. Attacker có thể thay đổi các đặc điểm dễ thao túng:

- Dùng VPN/proxy hoặc thiết bị đã bị xâm nhập để thay IP.
- Sao chép cookie hoặc token để tái sử dụng session.
- Giả user-agent và một số thuộc tính browser.
- Làm chậm hành vi automation để giống người dùng.
- Dùng residential proxy hoặc hạ tầng phân tán.
- Chiếm thiết bị quen thuộc hoặc lấy cookie trusted-device.
- Tấn công nguồn dữ liệu/tích hợp để tạo tín hiệu giả.

Do đó, không xây dựng chính sách chỉ dựa trên một đặc điểm như quốc gia, ASN, browser fingerprint hoặc tốc độ gõ. Kết hợp tín hiệu có nguồn độc lập, bảo vệ credential, giới hạn request và dùng step-up mạnh khi hành động nhạy cảm.

### Tín hiệu sau đăng nhập

Đánh giá rủi ro không kết thúc khi user đăng nhập thành công. Hệ thống có thể tiếp tục phát hiện:

- Thay đổi thiết bị hoặc mạng trong một phiên.
- Request truy cập dữ liệu vượt xa vai trò thông thường.
- Thêm credential hoặc token mới.
- Hành vi export hàng loạt.
- Refresh token reuse.
- Session đồng thời ở nhiều ngữ cảnh không phù hợp.

Khi phát hiện rủi ro sau đăng nhập, có thể yêu cầu step-up, giới hạn session hoặc thu hồi. Cần tránh kết luận từ một thay đổi IP đơn lẻ.

## 11. Quyền riêng tư và công bằng

Risk engine có thể xử lý dữ liệu cá nhân hoặc dữ liệu nhạy cảm như vị trí gần đúng, lịch sử hoạt động, thông tin thiết bị và thói quen sử dụng. Cần có mục đích rõ ràng, giới hạn thu thập và kiểm soát truy cập.

### Nguyên tắc dữ liệu

- Thu thập tín hiệu tối thiểu cần cho mục tiêu bảo vệ tài khoản.
- Xác định thời hạn lưu và xóa dữ liệu khi không còn cần.
- Không lưu raw fingerprint, vị trí chính xác hoặc hành vi chi tiết nếu không có căn cứ.
- Tách dữ liệu audit cần thiết khỏi dữ liệu thô có thể nhận diện người dùng.
- Giới hạn nhân sự và dịch vụ có thể truy cập risk profile.
- Bảo vệ dữ liệu khi truyền, lưu và chia sẻ với nhà cung cấp.
- Thông báo minh bạch về loại dữ liệu và mục đích sử dụng theo chính sách áp dụng.

### Tránh thiên lệch

Một mô hình có thể đánh giá bất lợi cho người dùng:

- Thường dùng VPN vì lý do an toàn hoặc chính sách doanh nghiệp.
- Sử dụng mạng di động có IP thay đổi thường xuyên.
- Dùng công nghệ hỗ trợ hoặc thiết bị cũ.
- Làm việc theo ca hoặc ở múi giờ khác.
- Đi lại thường xuyên hoặc sống tại khu vực có dữ liệu định vị kém.

Đo false positive và tỷ lệ step-up/từ chối giữa các nhóm và điều kiện sử dụng phù hợp, trong phạm vi pháp lý cho phép. Nếu có chênh lệch, điều tra nguyên nhân và cung cấp fallback công bằng. Không suy ra thuộc tính nhạy cảm từ vị trí hoặc hành vi để áp dụng chính sách phân biệt đối xử.

## 12. Kiến trúc risk engine và nguồn tín hiệu

Một kiến trúc khái niệm có thể gồm:

~~~mermaid
flowchart LR
    REQ["Authentication request"] --> COL["Signal collector"]
    NET["Network / IP intelligence"] --> COL
    DEV["Device / client context"] --> COL
    ACC["Account / credential events"] --> COL
    BEH["Behavior / session events"] --> COL
    COL --> NORM["Normalize, provenance, freshness"]
    NORM --> RISK["Policy / risk engine"]
    RISK --> DEC["Decision + reason codes"]
    DEC --> AUTH["Authentication service"]
    AUTH --> AUD["Audit / monitoring"]
~~~

### Tách collector khỏi policy engine

Signal collector thu thập và chuẩn hóa dữ liệu. Policy engine đánh giá dữ liệu theo quy tắc và phiên bản chính sách. Tách hai phần giúp thay nguồn tín hiệu mà không thay đổi mọi luồng đăng nhập và giúp kiểm thử chính sách độc lập.

### Chuẩn hóa tín hiệu

Mỗi tín hiệu có thể mang metadata:

| Trường | Ý nghĩa |
|---|---|
| signal_type | Nhóm tín hiệu, ví dụ network.reputation |
| value | Giá trị đã chuẩn hóa hoặc phân loại |
| source | Nguồn tạo tín hiệu |
| observed_at | Thời điểm quan sát |
| expires_at / ttl | Thời điểm hoặc khoảng dữ liệu hết giá trị |
| confidence | Mức tin cậy do nguồn/đánh giá cung cấp |
| integrity | Trạng thái xác minh tính toàn vẹn |
| reason_code | Mã giải thích có kiểm soát |

Không nhất thiết lưu mọi trường cho mọi loại tín hiệu. Schema phải giới hạn dữ liệu cá nhân và không đưa secret, cookie, access token hoặc raw credential vào risk event.

## 13. Ví dụ chính sách đánh giá rủi ro

**Bối cảnh:** Một nhân viên đăng nhập vào hệ thống quản lý dữ liệu. Chính sách yêu cầu MFA chống phishing cho mọi tài khoản có quyền xuất dữ liệu.

### Luật minh họa

| Điều kiện | Phản ứng |
|---|---|
| Mật khẩu sai nhiều lần từ cùng nguồn | Rate limit và theo dõi credential stuffing |
| Thiết bị mới, nhưng passkey hợp lệ và UV đạt | Tiếp tục nếu chính sách thiết bị cho phép; ghi nhận thiết bị mới |
| Thiết bị mới cộng thay đổi MFA gần đây | Step-up bằng yếu tố đã đăng ký trước hoặc manual review |
| Tín hiệu impossible travel nhưng IP định vị có confidence thấp | Không từ chối tự động; kiểm tra tín hiệu khác |
| Refresh token reuse được xác nhận | Thu hồi token family và đánh giá session liên quan |
| Yêu cầu export dữ liệu lớn | Yêu cầu freshness/step-up và kiểm tra quyền trên dữ liệu |

### Pseudocode

~~~typescript
async function evaluateAuthenticationContext(request, account) {
  const signals = await collectSignals(request, account);
  const usableSignals = signals.filter((signal) =>
    signal.integrity === "verified" &&
    !isExpired(signal, serverNow())
  );

  const assessment = riskPolicy.evaluate({
    accountState: account.securityState,
    signals: usableSignals,
    unknownSignalTypes: findUnavailableSignals(signals),
    policyVersion: CURRENT_POLICY_VERSION,
  });

  if (assessment.confirmedCompromise) {
    return { action: "deny_and_revoke", reasons: assessment.reasonCodes };
  }
  if (assessment.requiresStepUp) {
    return { action: "step_up", methods: assessment.allowedMethods };
  }
  if (assessment.requiresRestriction) {
    return { action: "restrict", limits: assessment.limits };
  }
  return { action: "continue", reasons: assessment.reasonCodes };
}
~~~

Đây là pseudocode minh họa. collectSignals phải xác minh nguồn và không tin header tùy ý; riskPolicy phải được hiệu chỉnh, kiểm thử và version hóa. Không lọc bỏ mọi tín hiệu unknown rồi mặc định rủi ro thấp; policy cần đánh giá rõ mức thiếu dữ liệu và các yêu cầu bảo đảm bắt buộc.

### Sau khi xác thực thành công

Hệ thống có thể ghi nhận kết quả credential, phương thức, mức xác thực, thiết bị và quyết định risk context vào session metadata. Chỉ lưu thông tin cần thiết; không lưu mẫu sinh trắc học hoặc secret xác thực. Các quyết định sau đó phải dùng dữ liệu có thời hạn và cập nhật, không coi risk assessment cũ là bảo đảm vô thời hạn.

## 14. Tình huống thực hành: đăng nhập từ thiết bị mới

**Bối cảnh:** Một nhân viên thường truy cập hệ thống từ laptop công ty. Hôm nay họ đăng nhập bằng laptop cá nhân khi đi công tác. IP thuộc mạng di động và vị trí suy ra khác thành phố thường dùng.

### Đánh giá

1. IP và vị trí khác thường là tín hiệu, nhưng có confidence giới hạn.
2. Thiết bị mới là tín hiệu cần xem xét, không chứng minh tài khoản bị chiếm.
3. Tài khoản không có lịch sử reset mật khẩu hoặc thay đổi MFA gần đây.
4. Người dùng có passkey đã đăng ký và xác thực với user verification.
5. Hành động hiện tại chỉ là xem dashboard, chưa phải export dữ liệu.

Theo chính sách phù hợp, hệ thống có thể cho phép sau khi xác minh passkey, đánh dấu thiết bị mới và tăng giám sát trong phiên. Khi người dùng yêu cầu export dữ liệu, hệ thống có thể yêu cầu step-up/fresh authentication và kiểm tra quyền riêng.

### Kịch bản khác: dấu hiệu chiếm tài khoản

Nếu cùng request có nhiều lần thử mật khẩu sai, recovery method vừa bị đổi, rồi xuất hiện yêu cầu tạo API key, mức rủi ro tăng rõ. Hệ thống có thể tạm chặn tạo key, yêu cầu xác thực bằng credential đã đăng ký trước khi thay đổi, thông báo cho chủ tài khoản và chuyển review nếu có thêm bằng chứng.

### Bài học

- IP lạ không tự động có nghĩa là tấn công.
- Passkey hợp lệ làm giảm một số rủi ro phishing nhưng không giải quyết mọi rủi ro tài khoản.
- Thay đổi recovery/MFA cần được xem là sự kiện bảo mật quan trọng.
- Hành động nhạy cảm cần authorization và freshness riêng.

## 15. Kiểm thử tín hiệu rủi ro

Kiểm thử trong môi trường được phép, dùng tài khoản và dữ liệu giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| IP mới nhưng credential hợp lệ | Không tự động kết luận gian lận |
| IP reputation feed lỗi hoặc cũ | Đánh dấu unknown/stale và áp dụng fallback |
| Client tự gửi header trusted=true | Không được coi là tín hiệu tin cậy |
| Forwarded IP từ proxy không nằm trong trust chain | Bị bỏ qua hoặc đánh dấu không xác minh |
| Device fingerprint thay đổi sau browser update | Không tự động khóa tài khoản |
| Nhiều lần thử sai tốc độ cao | Rate limit/challenge theo chính sách |
| Tín hiệu vị trí có confidence thấp | Không dùng làm căn cứ từ chối duy nhất |
| Tín hiệu thiết bị và mạng mâu thuẫn | Áp dụng quy tắc xử lý conflicting signals |
| Dữ liệu thiếu | Không mặc định là rủi ro thấp hoặc cao |
| Thay đổi MFA rồi tạo API key | Step-up hoặc giới hạn theo chính sách |
| Refresh token reuse | Thu hồi token family và audit |
| Mô hình được cập nhật | Có version, kiểm thử hồi quy và rollback |
| Người dùng hợp lệ bị step-up nhầm | Có fallback và quy trình hỗ trợ |
| Một nhóm người dùng bị false positive cao | Phát hiện qua metric và điều tra thiên lệch |
| Risk engine timeout | Có fallback an toàn, không bỏ qua xác thực bắt buộc |
| Request sau đăng nhập có hành vi bất thường | Đánh giá lại session/action theo chính sách |

### Chỉ số vận hành

- Tỷ lệ step-up, deny và manual review theo ứng dụng/nhóm tín hiệu.
- False positive và false negative được xác nhận qua điều tra.
- Tỷ lệ người dùng hoàn tất step-up và tỷ lệ bỏ dở.
- Độ trễ, availability và freshness của từng nguồn tín hiệu.
- Tỷ lệ tín hiệu unknown/conflicting.
- Số sự cố credential stuffing, session theft và recovery abuse.
- Chênh lệch kết quả theo điều kiện thiết bị/mạng và nhóm người dùng phù hợp.
- Số lần override chính sách và lý do.

Không tối ưu chỉ theo tỷ lệ từ chối hoặc số vụ tấn công phát hiện. Cần cân bằng an toàn, trải nghiệm, khả năng tiếp cận và quyền riêng tư.

## 16. Checklist thiết kế tín hiệu rủi ro

- [ ] Tách risk evaluation khỏi authentication và authorization.
- [ ] Mỗi tín hiệu có nguồn gốc, độ mới, confidence và giới hạn rõ ràng.
- [ ] Không tin header hoặc thuộc tính thiết bị do client tự khai nếu chưa xác minh nguồn.
- [ ] IP, VPN, vị trí và fingerprint được xem là tín hiệu có thể sai hoặc bị thao túng.
- [ ] Tín hiệu thiếu, lỗi thời và mâu thuẫn có trạng thái xử lý riêng.
- [ ] Không cộng nhiều tín hiệu tương quan như bằng chứng độc lập.
- [ ] Risk score/policy có phiên bản, ngưỡng được hiệu chỉnh và lý do kiểm toán.
- [ ] Rủi ro thấp không bỏ qua yêu cầu authentication tối thiểu bắt buộc.
- [ ] Step-up dùng phương thức phù hợp với loại tấn công và mức bảo đảm cần thiết.
- [ ] Kết quả step-up gắn với subject, session, thời gian và hành động phù hợp.
- [ ] Thay đổi credential/recovery method được đánh giá và thông báo.
- [ ] Có giới hạn hành động, rate limit, revocation và manual review khi cần.
- [ ] Có fallback an toàn khi nguồn tín hiệu hoặc risk engine không khả dụng.
- [ ] Dữ liệu thu thập tối thiểu, có retention, access control và redaction.
- [ ] Đo false positive/false negative, fairness và model drift.
- [ ] Kiểm thử né tránh tín hiệu, replay, session theft và request đồng thời.

## Ghi nhớ

Tín hiệu rủi ro cung cấp ngữ cảnh để hệ thống đánh giá một request xác thực có bất thường hay không. IP, thiết bị, vị trí, hành vi, lịch sử tài khoản và sự kiện credential đều có thể hữu ích, nhưng mỗi tín hiệu có nguồn gốc, độ mới, confidence và khả năng bị thao túng khác nhau.

Hãy kết hợp tín hiệu theo chính sách có thể giải thích, xử lý unknown và false positive công bằng, rồi chọn phản ứng tương xứng như quan sát, rate limit, step-up, giới hạn hoặc từ chối. Tín hiệu rủi ro không chứng minh danh tính, không thay thế credential và không tự cấp quyền truy cập; authentication và authorization vẫn phải được kiểm tra độc lập.
