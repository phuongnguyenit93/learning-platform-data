# Avoiding channel disclosure: Tránh tiết lộ kênh khôi phục

Trong chương **Recovery Discovery** của `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, **channel disclosure** là việc luồng tìm phương án khôi phục làm lộ thông tin về những kênh hoặc phương tiện đã gắn với một tài khoản. Thông tin bị lộ có thể là email đầy đủ, vài chữ số điện thoại, tên miền hộp thư, loại MFA, tên thiết bị hoặc việc tài khoản có một đường dự phòng cụ thể.

Người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực cần được hướng dẫn tìm đường trở lại tài khoản. Nhưng người chỉ biết tên đăng nhập cũng có thể dùng chính giao diện đó để thu thập thông tin phục vụ lừa đảo, chiếm kênh hoặc dò tài khoản. Thiết kế tốt phải xác định thông tin nào được công khai, thông tin nào chỉ được tiết lộ sau bằng chứng phù hợp và việc tiết lộ đó có phạm vi gì.

Bài học tập trung vào ranh giới tiết lộ thông tin trong giai đoạn khám phá phương án khôi phục. Quyền biết một phần kênh không đồng nghĩa quyền thay kênh, nhận token ở địa chỉ mới hoặc vô hiệu hóa MFA.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện thông tin về kênh có thể bị lộ qua giao diện, API, lỗi, thời gian phản hồi và luồng hỗ trợ.
- Giải thích vì sao che một phần địa chỉ hoặc số điện thoại chưa chắc ngăn được tiết lộ.
- Thiết kế phản hồi công khai hạn chế dò tìm tài khoản và gợi ý theo từng mức quyền.
- Giữ nguyên ranh giới giữa kiểm soát một kênh, khám phá phương án và quyền khôi phục tài khoản.
- Cung cấp đường hỗ trợ cho người mất kênh mà không cho phép tự chọn một kênh mới làm bằng chứng sở hữu.
- Đặt tiêu chí kiểm tra cho dữ liệu trả về, tác vụ gửi mã, log và các nhánh lỗi.

## 2. Cần bảo vệ những thông tin nào?

Tiết lộ kênh không chỉ là trả về địa chỉ đầy đủ. Một giá trị nhỏ cũng có thể hữu ích khi kết hợp với dữ liệu từ nơi khác.

| Thông tin quan sát được | Điều người ngoài có thể suy ra | Rủi ro có thể phát sinh |
|---|---|---|
| Email khôi phục đầy đủ | Địa chỉ đang liên kết với tài khoản | Nhắm vào hộp thư hoặc giả danh dịch vụ |
| Một phần email và tên miền | Thu hẹp các địa chỉ có khả năng đúng | Đối chiếu với danh bạ, hồ sơ công khai hoặc dữ liệu bị lộ |
| Vài số cuối điện thoại | Liên kết tài khoản với một số đã biết | Bổ sung dữ liệu để thao túng hỗ trợ hoặc nhắm vào thuê bao |
| Có nút SMS nhưng không có email | Tài khoản có một loại kênh và thiếu loại khác | Chọn cách tiếp cận phù hợp với cấu hình của nạn nhân |
| Tên thiết bị hoặc khóa bảo mật | Loại thiết bị hoặc cách tổ chức bảo vệ tài khoản | Tạo thông điệp lừa đảo có vẻ đúng ngữ cảnh |
| Số lượng passkey hoặc mã dự phòng | Mức chuẩn bị dự phòng của tài khoản | Xác định mục tiêu hoặc đường gây gián đoạn |
| Chuyển sang một nhà cung cấp SSO cụ thể | Quan hệ với tổ chức hoặc cơ chế đăng nhập | Nhắm vào hạ tầng danh tính liên quan |
| Chỉ tài khoản đặc quyền được chuyển hỗ trợ riêng | Tầng bảo vệ hoặc vai trò của tài khoản | Ưu tiên mục tiêu có tác động cao |

Không phải mọi thông tin trong bảng đều phải được giấu tuyệt đối trong mọi sản phẩm. Một tổ chức có thể công khai nhà cung cấp đăng nhập của mình. Điều cần thiết là quyết định có chủ đích về mức lộ chấp nhận được, thay vì vô tình tiết lộ cấu hình riêng qua endpoint khôi phục.

### Phân biệt tiết lộ tài khoản và tiết lộ kênh

**Account enumeration** là khả năng suy ra định danh nào có tài khoản. **Channel disclosure** là khả năng biết thêm phương tiện liên kết với tài khoản đó. Hai vấn đề có thể xuất hiện cùng nhau nhưng không giống hệt nhau.

Một phản hồi không nói trực tiếp tài khoản tồn tại vẫn có thể làm lộ qua câu “mã đã gửi tới số kết thúc bằng 48”. Ngược lại, dù tài khoản đã được biết là tồn tại từ nguồn công khai, dịch vụ vẫn cần bảo vệ các kênh riêng của tài khoản.

## 3. Mô hình đối phương trong giai đoạn khám phá

Mô hình cơ sở có thể là đối phương biết email hoặc tên đăng nhập của nạn nhân, có khả năng gửi yêu cầu công khai và quan sát phản hồi, nhưng chưa kiểm soát authenticator hay kênh khôi phục.

Đối phương có thể so sánh nhiều định danh, thay đổi lựa chọn trên giao diện, đọc payload API hoặc đi qua các nhánh “không còn điện thoại”, “thử cách khác” và “liên hệ hỗ trợ”. Họ có thể kết hợp mẩu thông tin trả về với dữ liệu đã biết để dựng câu chuyện có vẻ đáng tin.

Các biến thể cần xét riêng gồm:

- Đối phương có mật khẩu nhưng chưa vượt MFA; không nên mặc định họ được biết toàn bộ phương tiện bảo mật.
- Đối phương có session cũ hoặc quyền hạn chế; cần kiểm tra quyền xem thông tin nhạy cảm của session đó.
- Đối phương kiểm soát hộp thư; bằng chứng email lúc này không loại trừ được họ.
- Tài khoản hỗ trợ bị chiếm hoặc nhân viên tra cứu ngoài nhiệm vụ; giao diện nội bộ cũng có thể làm lộ kênh.

Threat model phải nói rõ trường hợp nào đang được bảo vệ. Một phản hồi công khai kín đáo không giải quyết được việc đối phương đã kiểm soát mọi kênh, nhưng vẫn giảm cơ hội thu thập dữ liệu trước khi chiếm quyền.

## 4. Quyết định mức tiết lộ theo quyền và mục đích

Thông tin trả về nên phụ thuộc vào quyền đã được xác lập và mục đích cụ thể, không chỉ việc client gửi đúng tên tài khoản.

| Ngữ cảnh | Cách cung cấp thông tin phù hợp |
|---|---|
| Chưa xác minh, chỉ nhập định danh | Hướng dẫn chung và danh mục phương án không phản ánh cấu hình riêng của tài khoản |
| Có một phần bằng chứng, như mật khẩu nhưng còn thiếu MFA | Chỉ thông tin được chính sách cho phép ở mức đó; không tự trả toàn bộ kênh |
| Có ngữ cảnh được phép khám phá phương án khôi phục | Gợi ý tối thiểu cần thiết, có thể che dữ liệu theo chính sách |
| Có grant cho một thao tác khôi phục | Chỉ dữ liệu cần cho thao tác và hồ sơ đó; không tự có quyền thay kênh khác |
| Người dùng quản lý thiết lập bảo mật | Kiểm tra quyền và yêu cầu xác thực phù hợp trước khi hiển thị chi tiết nhạy cảm |
| Nhân viên hỗ trợ | Quyền theo vai trò, tenant và hồ sơ đang xử lý; giới hạn trường dữ liệu và ghi nhận tra cứu |

Đây là các mức ngữ cảnh để thiết kế, không phải quy định rằng cứ vượt một bước là được xem mọi thông tin ở mức tiếp theo. Phải xác định loại bằng chứng nào đủ cho loại dữ liệu nào.

### Tiết lộ dần có kiểm soát

Progressive disclosure trong bài này là chỉ đưa thêm thông tin khi đã có quyền cần thiết và thông tin đó phục vụ bước hiện tại. Ví dụ, sau kiểm tra được chính sách chấp nhận, người dùng có thể được chọn giữa những phương án được phép dùng; địa chỉ đầy đủ vẫn không cần xuất hiện nếu một nhãn tối thiểu đã đủ.

Việc kiểm soát một email chỉ chứng minh quyền kiểm soát email theo kiểm tra đã thực hiện. Nó không tự cho phép biết mọi số điện thoại của tài khoản hoặc thay MFA. Nếu chính sách cần bằng chứng mạnh hơn, phải giữ ranh giới đó.

## 5. Thiết kế phản hồi công khai hạn chế dò tìm

Ở bước chưa có quyền xem cấu hình riêng, có thể dùng thông báo như:

> Nếu thông tin khớp và yêu cầu đủ điều kiện, hướng dẫn sẽ được gửi qua phương thức đã thiết lập.

Câu này diễn đạt điều kiện tiếp nhận, không khẳng định có tài khoản, có một loại kênh cụ thể hoặc đã gửi thành công. Tránh dùng thông báo chung nhưng lại kèm payload, mã lỗi hay chuyển hướng tiết lộ câu trả lời thật.

| Dấu hiệu dễ làm lộ | Hướng xử lý |
|---|---|
| “Không tìm thấy email này” chỉ ở định danh chưa đăng ký | Dùng phản hồi công khai không xác nhận sự tồn tại trong phạm vi đã chọn |
| Tài khoản thật nhận `available_methods`, tài khoản khác nhận danh sách rỗng | Không trả danh mục riêng khi chưa đủ quyền |
| Chỉ hiện nút “Gửi SMS” nếu tài khoản có số điện thoại | Dùng lựa chọn chung hoặc chờ tới ngữ cảnh được phép tiết lộ |
| Lỗi “Không có email dự phòng” | Không cho nhánh lỗi xác nhận cấu hình riêng |
| Receipt hoặc endpoint theo dõi trả trạng thái gửi riêng theo tài khoản | Giới hạn trạng thái công khai về việc tiếp nhận, không công bố kết quả tra cứu |
| Header hoặc URL chuyển hướng chứa loại kênh | Kiểm tra cả lớp HTTP và điều hướng, không chỉ nội dung hiển thị |

Thông báo chung không được đi kèm lời hứa sai. Nếu chưa biết có gửi được hay không, không hiển thị “SMS đã gửi thành công”. Người có quyền phù hợp có thể được nhận trạng thái chi tiết hơn theo chính sách; điều đó là một quyết định tiết lộ riêng.

## 6. Che dữ liệu không thay thế kiểm soát quyền

Địa chỉ dạng `m***@example.test` hoặc số kết thúc bằng `48` có thể giúp người dùng nhớ lại một kênh. Nhưng chúng vẫn là dữ liệu được tiết lộ và có thể đủ để đối phương phân biệt giữa vài địa chỉ hoặc số đã biết.

Cần trả lời ba câu hỏi trước khi dùng gợi ý đã che:

1. Bên đang xem đã có quyền biết loại thông tin này chưa?
2. Phần giữ lại có thật sự cần cho bước hiện tại không?
3. Khi kết hợp với gợi ý ở nơi khác, có thể khôi phục nhiều hơn dự kiến không?

Ví dụ, một trang giữ tên miền, trang khác giữ chữ đầu hộp thư và hỗ trợ đọc thêm vài ký tự có thể làm lộ nhiều hơn từng phần riêng lẻ. Cần có chính sách tiết lộ nhất quán giữa các bề mặt của sản phẩm, không coi từng màn hình là độc lập.

### Chỉ gửi xuống dữ liệu được phép hiển thị

Nếu API gửi email đầy đủ rồi JavaScript tự che trên màn hình, địa chỉ vẫn có thể được đọc từ response hoặc bộ nhớ trình duyệt. Tương tự, dữ liệu đặt trong hidden field, thuộc tính HTML, tên truy cập hỗ trợ hoặc nút bị ẩn bằng CSS vẫn đã được gửi tới client.

Việc che phải được thực hiện trước khi dữ liệu vượt ranh giới được phép, theo mức quyền của ngữ cảnh. Cần kiểm tra cả ứng dụng di động, công cụ hỗ trợ khả năng tiếp cận, bản địa hóa và các endpoint thay thế.

Không có một cách che phù hợp với mọi kênh. Nếu không cần phân biệt các đích cụ thể, một nhãn như “phương thức dự phòng đã đăng ký” có thể đủ. Nếu cần gợi ý, chỉ giữ phần tối thiểu và chấp nhận rằng nó vẫn mang giá trị nhận diện.

## 7. Giảm tín hiệu qua HTTP, thời gian và bộ nhớ đệm

### Tính nhất quán của phản hồi

Người ngoài có thể quan sát mã HTTP, cấu trúc JSON, số phần tử, độ dài dữ liệu, header, URL tiếp theo và nhánh lỗi. Dùng cùng một câu thông báo không đủ nếu những thành phần còn lại khác nhau tùy việc tài khoản có kênh hay không.

Nên thiết kế một hợp đồng phản hồi công khai theo lớp đầu vào và trạng thái được phép biết. Có thể báo lỗi định dạng email sai vì đó là thông tin về dữ liệu người dùng vừa nhập, không phải về sự tồn tại của tài khoản. Những khác biệt dựa trên kết quả tra cứu riêng cần được đánh giá và giới hạn.

Cần kiểm tra cả endpoint gửi lại, xác nhận mã, đổi phương án và xem tiến trình. Một bước đầu kín đáo không có ích nếu bước tiếp theo trả “tài khoản này chỉ có SMS”.

### Thời gian phản hồi

Nếu tài khoản tồn tại phải gọi nhà cung cấp gửi tin còn tài khoản không tồn tại trả ngay, thời gian có thể trở thành tín hiệu. Có thể tách việc tiếp nhận công khai khỏi xử lý tra cứu và gửi thông báo bằng cơ chế bất đồng bộ, với phản hồi tiếp nhận có cấu trúc và đường xử lý tương đương phù hợp.

Không nên gọi đây là bảo đảm thời gian HTTP hoàn toàn cố định. Độ trễ mạng, tải hệ thống và nhiều nhánh xử lý vẫn có thể khác nhau. Thêm một khoảng ngủ cố định hoặc nhiễu ngẫu nhiên không tự loại bỏ tín hiệu nếu có thể quan sát và so sánh nhiều mẫu.

Đánh giá cần dựa trên hành vi thực tế, gồm cả nhánh lỗi và timeout. Tránh để kết quả gửi email hoặc SMS được phản ánh trực tiếp vào thời gian hay trạng thái của endpoint chưa xác minh.

### Giới hạn tần suất cũng có thể làm lộ

Nếu tài khoản thật có bộ đếm gửi SMS còn định danh khác không có, số lần thử tới lúc bị chặn hoặc giá trị chờ có thể cho biết kết quả tra cứu. Cần tách giới hạn công khai theo nguồn và đầu vào khỏi các quyết định nội bộ dựa trên tài khoản.

Một phản hồi giới hạn do nguồn gửi quá nhiều yêu cầu có thể được công khai nếu nó không xác nhận tài khoản đích. Với giới hạn nội bộ theo kênh hoặc tài khoản, phản hồi vẫn phải tuân theo chính sách tiết lộ. Nếu dùng bộ đếm theo định danh đã nhập, có thể áp dụng nhất quán cho cả định danh chưa khớp, đồng thời kiểm soát chi phí và thời hạn lưu.

Không chỉ dựa vào IP vì có thể có nhiều người dùng chung mạng và đối phương có thể đổi nguồn. Cũng không để một người lạ dùng yêu cầu gửi lại để làm khóa tài khoản hoặc thu hồi mọi session của chủ tài khoản.

### Bộ nhớ đệm và dữ liệu quan sát

Phản hồi có thông tin riêng của kênh không nên bị bộ nhớ đệm dùng chung trả cho người khác. Chính sách cache, chẳng hạn `Cache-Control: no-store` ở các phản hồi nhạy cảm, cần được thực thi phù hợp tại ứng dụng và các lớp trung gian.

Không đưa địa chỉ khôi phục, số điện thoại hoặc token vào URL điều hướng để tiện theo dõi. Query string, referrer, lịch sử trình duyệt, telemetry và log có thể giữ chúng lâu hơn dự kiến. Dùng body của request cũng không tự bảo vệ dữ liệu nếu gateway hoặc công cụ giám sát vẫn ghi nguyên văn.

## 8. Cho người dùng chọn phương án mà không công bố cấu hình riêng

### Danh mục chung

Ở bước công khai, giao diện có thể đưa ra các lựa chọn như “Tôi còn dùng được một authenticator”, “Tôi có mã dự phòng” hoặc “Tôi không còn các phương thức này”. Các lựa chọn là danh mục hướng dẫn chung, không phải xác nhận tài khoản đã đăng ký từng phương thức.

Sau khi người dùng chọn, máy chủ xử lý theo chính sách và ngữ cảnh. Không để một tùy chọn không áp dụng lập tức trả chi tiết cấu hình cho bên chưa có quyền biết. Phản hồi thất bại của bằng chứng không hợp lệ và của hồ sơ không khớp cần tuân theo cùng chính sách tiết lộ.

### Yêu cầu người dùng cung cấp kênh họ biết

Một thiết kế có thể yêu cầu người dùng nhập đầy đủ một kênh dự phòng mà họ tin đã đăng ký, rồi đối chiếu phía máy chủ. Cách này giảm nhu cầu hiển thị gợi ý sẵn nhưng vẫn cần giới hạn thử và phản hồi không xác nhận từng phần đúng sai.

Không trả “đúng tên miền nhưng sai hộp thư” hay “đúng vài số cuối” trong quá trình đối chiếu công khai. Việc chuẩn hóa và so khớp phải nhất quán với mô hình định danh của dịch vụ; không tự gộp các địa chỉ khác nhau chỉ vì một số nhà cung cấp có quy tắc riêng.

Nếu được phép gửi challenge, đích gửi phải là kênh đã được hệ thống chấp nhận trong hồ sơ tài khoản, theo quyền và chính sách hiện tại. Một địa chỉ hoặc số mới do người yêu cầu nhập không tự trở thành kênh tin cậy chỉ vì họ nhận được mã ở đó.

Nếu cần địa chỉ mới để trao đổi với hỗ trợ, phải ghi rõ vai trò liên hệ của nó. Quyền trả lời ở địa chỉ đó không được dùng thay bằng chứng cho phép chuyển tài khoản sang kênh mới.

### Người dùng mất cả kênh cũ

Không thể giải quyết việc mất kênh bằng cách tiết lộ dần mọi địa chỉ và số của tài khoản cho bất kỳ ai tự khai gặp sự cố. Cần có đường dùng authenticator còn lại, recovery code hoặc quy trình xác minh được thiết kế cho loại tài khoản đó.

Quy trình hỗ trợ phải có khả năng tiếp nhận người không còn email hoặc thiết bị cũ, nhưng chỉ cung cấp dữ liệu và cấp quyền khi đạt điều kiện tương ứng. Biết tên, ngày sinh hoặc mã khách hàng có thể giúp tìm hồ sơ, không mặc nhiên tạo quyền xem kênh riêng.

## 9. Mô hình xử lý phía máy chủ

Đoạn dưới minh họa việc tách tiếp nhận công khai khỏi kết quả tra cứu. Nó không phải mã triển khai hoàn chỉnh.

```text
public_start_discovery(input, request_context):
    validate_public_input_format(input)
    enforce_public_abuse_limits(input, request_context)

    receipt = persist_minimal_intake(
        identifier = input.identifier,
        selected_route = allowed_route(input.route),
        namespace = trusted_namespace(request_context)
    )
    schedule_internal_processing(receipt)

    return generic_intake_response(receipt.public_reference)

process_discovery_intake(receipt):
    account = resolve_account_in_namespace(receipt)

    if account does not match:
        record_internal_outcome_without_public_disclosure()
        return

    if initiation_policy_or_internal_limits_do_not_allow(account, receipt):
        record_internal_outcome_without_public_disclosure()
        return

    route = select_registered_route_allowed_by_policy(account, receipt)
    if no route is allowed:
        record_internal_outcome_without_public_disclosure()
        return

    create_scoped_challenge_and_deliver_to_registered_destination(route)
```

Receipt công khai chỉ chứng minh hệ thống đã tiếp nhận yêu cầu ở mức được nêu. Nó không chứng minh có tài khoản, đã gửi tin hay có quyền khôi phục. Định danh receipt không được trở thành khóa đọc cấu hình kênh qua một endpoint khác.

Xử lý bất đồng bộ không tự giải quyết mọi rò rỉ. Endpoint theo dõi, tác vụ gửi lại và nhánh lỗi vẫn phải giữ hợp đồng tiết lộ. Cũng cần bảo vệ dữ liệu đầu vào được lưu để xử lý, tránh lưu dài hơn nhu cầu.

### Sau khi có bằng chứng phù hợp

```text
get_permitted_recovery_hints(context, case):
    require context may discover channels for this case
    require context.subject == case.subject
    require context.tenant == case.tenant
    require evidence and policy remain valid

    hints = policy.select_minimum_hints_for_current_step(case, context)
    return server_redacted_hints(hints)
```

Máy chủ chọn trường dữ liệu và mức che trước khi trả về. Không trả một đối tượng tài khoản đầy đủ rồi trông chờ client tự bỏ những trường nhạy cảm.

Token dùng để xác lập ngữ cảnh khám phá cần có mục đích, phạm vi và thời hạn; nếu được thiết kế dùng một lần thì phải kiểm soát tiêu thụ và phát lại. Token ngẫu nhiên cần nguồn ngẫu nhiên mật mã và cách lưu phù hợp. Request đọc trang không nên tự đổi credential hoặc tiêu thụ quyền có tác động bảo mật chỉ vì trình quét email mở liên kết.

Ngay cả sau khi kiểm tra thành công, grant khám phá kênh không được endpoint thay MFA hoặc đổi email chấp nhận như quyền tương đương. Kiểm soát mục đích phải nằm phía máy chủ.

## 10. Kiểm soát thông báo và luồng hỗ trợ

### Thông báo cũng là một điểm tiết lộ

Việc gửi email hoặc SMS có thể cho người nhận biết một mối liên hệ với dịch vụ. Nếu hộp thư dùng chung, số điện thoại đã được chuyển cho người khác hoặc kênh đã bị chiếm, nội dung thông báo có thể đến không đúng người mong muốn.

Chỉ gửi tới kênh được chính sách chấp nhận và có quản lý vòng đời phù hợp. Nội dung nên tối thiểu cho mục đích hiện tại, không liệt kê thêm các email, số điện thoại hoặc thiết bị khác của tài khoản. Nếu thông báo cần mang token, token phải có phạm vi, thời hạn và điều kiện sử dụng tương xứng.

Không sao chép mọi thông báo bảo mật sang địa chỉ mới do người yêu cầu cung cấp trước khi có quyền thay kênh. Một email liên hệ hỗ trợ mới không được tự trở thành nơi nhận quyền khôi phục.

Cần giới hạn tần suất và tránh gửi trùng không cần thiết để đối phương không dùng khám phá kênh làm công cụ quấy rối. Việc chưa gửi được thông báo cũng không phải lý do trả dữ liệu kênh riêng cho caller chưa xác minh.

### Nhân viên hỗ trợ không đọc kênh để tự tạo bằng chứng

Một cách xử lý có vấn đề là nhân viên đọc vài số cuối rồi hỏi người gọi có nhận ra không. Đối phương vừa nhận thêm thông tin và có thể xác nhận dựa trên chính gợi ý đó. Việc đồng ý với thông tin do nhân viên vừa cung cấp không tạo ra bằng chứng độc lập.

Nên hướng dẫn người dùng đi qua giao diện chính thức và nộp bằng chứng được chấp nhận. Nếu cần đối chiếu thông tin họ biết, quy trình phải xác định giá trị xác minh của dữ liệu đó; việc họ kể đúng thông tin cá nhân không tự đủ để xem hoặc đổi kênh.

Giao diện hỗ trợ chỉ nên hiển thị trường cần thiết cho nhiệm vụ, với quyền theo vai trò và tenant. Tra cứu kênh đầy đủ, xuất dữ liệu hoặc vượt mức che phải có thẩm quyền rõ ràng và được audit. Một nhân viên đã đăng nhập không tự có quyền xem mọi tài khoản.

Không yêu cầu người dùng đọc mật khẩu, OTP, recovery code hay liên kết chứa token nguyên văn cho nhân viên. Biết mã hồ sơ chỉ giúp tìm vụ việc trong phạm vi được phép, không chứng minh quyền sở hữu của người đang liên hệ.

## 11. Kiểm tra lại kênh trước khi dùng

Một gợi ý được hiển thị hợp lệ ở bước trước không chứng minh kênh vẫn được phép dùng ở bước sau. Trong lúc hồ sơ đang chờ, người dùng có thể đổi email, báo mất thiết bị hoặc phát hiện một kênh đã bị chiếm.

Khi gửi challenge hoặc cấp quyền tiếp tục, cần kiểm tra lại trạng thái tài khoản, phiên bản kênh và chính sách liên quan. Nếu client chọn một định danh kênh, máy chủ phải tra định danh đó trong phạm vi đúng tài khoản và tenant; không chấp nhận kênh của tài khoản khác hoặc một đích gửi tùy ý trong payload.

Việc chọn một kênh từ giao diện không được tự thay đổi kênh đã đăng ký. Nếu cần đổi, đó là thao tác bảo mật riêng với bằng chứng, phê duyệt và token có mục đích tương ứng.

Discovery cũng không nên làm thay đổi mật khẩu, thu hồi session hoặc vô hiệu hóa MFA chỉ vì có yêu cầu chưa xác minh. Giữ ranh giới này giúp tránh biến chức năng bảo vệ thông tin thành một đường gây mất quyền truy cập.

## 12. Tình huống thực tế: Tìm đường khôi phục khi mất điện thoại

Phương quên mật khẩu và mất điện thoại chứa MFA, nhưng còn truy cập được hộp thư đăng nhập trên máy tính và giữ recovery code ở nơi dự phòng. Một người khác biết email đăng nhập của Phương nhưng chưa có quyền kiểm soát hộp thư hoặc mã dự phòng.

### Thiết kế dễ làm lộ

Sau khi nhập email, trang trả về email dự phòng đã che, số điện thoại kết thúc bằng `48` và thông báo tài khoản không có passkey khác. API còn chứa địa chỉ đầy đủ để client tự che. Khi chọn “không còn điện thoại”, trang xác nhận rằng đường duy nhất còn lại là bộ phận hỗ trợ đặc quyền.

Người ngoài chưa vượt bước xác minh nào nhưng đã biết thêm cấu hình và cách tiếp cận hỗ trợ. Gộp những dữ kiện này với thông tin từ nguồn khác có thể giúp họ giả danh Phương có vẻ đáng tin hơn.

### Thiết kế có ranh giới tiết lộ

1. Bước đầu nhận email và hiển thị phản hồi có điều kiện, không nêu số điện thoại hoặc danh sách phương thức riêng. Các lựa chọn công khai là danh mục hướng dẫn chung.
2. Máy chủ xử lý việc tra cứu và gửi challenge qua kênh đã đăng ký nếu chính sách cho phép. Client không nhận kết quả tra cứu hoặc địa chỉ nội bộ từ tác vụ này.
3. Phương hoàn tất kiểm tra quyền kiểm soát hộp thư qua giao diện chính thức. Theo chính sách của ví dụ, ngữ cảnh đó chỉ được xem một số gợi ý tối thiểu phục vụ bước tiếp theo.
4. Giao diện không trả email hoặc số điện thoại đầy đủ nếu không cần. Các trường gợi ý được chọn và che ở máy chủ.
5. Để thay MFA, Phương vẫn phải đáp ứng đường khôi phục tương ứng, chẳng hạn dùng recovery code và những điều kiện khác của loại tài khoản. Kiểm tra email trước đó không tự cho quyền xóa MFA hoặc đổi cả kênh.
6. Khi bước thay đổi được phép, hệ thống cấp quyền hẹp, có thời hạn và giới hạn dùng; các session và phương tiện truy cập liên quan được xử lý theo chính sách sau khôi phục.

Đối phương chỉ biết email sẽ không nhận được gợi ý riêng qua phản hồi công khai. Nếu họ chiếm được hộp thư, họ có thể vượt kiểm tra email và biết những thông tin mà chính sách cho phép ở mức đó. Vì vậy, mức tiết lộ sau email phải được lựa chọn phù hợp, và các thay đổi có tác động lớn vẫn cần điều kiện riêng.

Nếu Phương mất cả hộp thư và mã dự phòng, hệ thống phải đưa tới đường xác minh hoặc hỗ trợ đã thiết kế. Không tự gửi quyền tới email mới chỉ để giải quyết bế tắc. Có trường hợp không còn đủ bằng chứng để cấp quyền; trải nghiệm cần giải thích đường xử lý và giới hạn thực tế.

## 13. Quan sát vận hành mà không sao chép dữ liệu kênh khắp hệ thống

Nhóm vận hành cần biết lý do không gửi được challenge, số lần bị giới hạn và lỗi nhà cung cấp, nhưng các chi tiết này không nhất thiết phải xuất hiện trong phản hồi công khai.

Có thể tách mã kết quả nội bộ khỏi thông báo bên ngoài. Ví dụ, nội bộ phân biệt không khớp hồ sơ, không có đường được phép hoặc bị giới hạn theo chính sách, trong khi bên chưa xác minh chỉ nhận trạng thái tiếp nhận được phép biết.

Dữ liệu quan sát nên dùng định danh hồ sơ, loại sự kiện và tham chiếu kênh cần thiết thay vì sao chép email, số điện thoại và token nguyên văn. Một giá trị băm email không khóa vẫn có thể bị đối chiếu bằng cách thử danh sách địa chỉ; mã hóa hoặc dùng định danh giả có khóa có thể giảm một số rủi ro nhưng không tự làm dữ liệu thành vô danh.

Cần quy định quyền truy cập, thời hạn lưu và mục đích sử dụng đối với cả log, hàng đợi, dữ liệu nhà cung cấp và công cụ hỗ trợ. Tham chiếu kênh cũng có thể liên kết được với người dùng nếu có bảng tra cứu, nên vẫn cần bảo vệ.

Khi điều tra, cần biết ai đã được xem trường nào, theo hồ sơ nào và quyền gì. Không nên chỉ ghi “recovery viewed” mà không phân biệt xem hướng dẫn chung với truy cập dữ liệu kênh đầy đủ.

## 14. Các tình huống kiểm tra thiết kế

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Nhập định danh có tài khoản và chưa khớp tài khoản | Phản hồi công khai tuân theo cùng hợp đồng tiết lộ đã chọn |
| Tài khoản có SMS, chỉ có email hoặc không có kênh dự phòng | Chưa có quyền thì không suy ra cấu hình từ danh sách nút, payload hoặc lỗi |
| API gửi địa chỉ đầy đủ nhưng UI che | Được nhận diện là tiết lộ; dữ liệu phải được giới hạn trước khi trả client |
| Mở nhánh “thử cách khác” hoặc “không còn thiết bị” | Không được dùng nhánh thay thế để lấy cấu hình đã bị giấu ở bước đầu |
| So sánh status, header, độ dài, redirect và lỗi nhà cung cấp | Không vô tình có tín hiệu riêng vượt mức tiết lộ được chấp nhận |
| Gửi nhiều yêu cầu và quan sát thời gian hoặc giới hạn | Đánh giá tín hiệu thực tế; không coi câu thông báo chung hoặc delay là đủ |
| Biết receipt rồi gọi endpoint theo dõi | Không đọc được kết quả tra cứu hoặc danh sách kênh nếu chưa có quyền |
| Có token chỉ cho khám phá kênh rồi gọi API thay MFA | Bị từ chối vì sai mục đích hoặc thiếu quyền |
| Nhập một email hoặc số điện thoại mới do mình kiểm soát | Không tự được dùng làm kênh khôi phục đã đăng ký |
| Client chọn định danh kênh thuộc tài khoản hoặc tenant khác | Máy chủ từ chối theo phạm vi đối tượng |
| Kênh vừa bị thu hồi hoặc báo chiếm sau khi hiện gợi ý | Kiểm tra lại trước khi gửi challenge hoặc cấp quyền |
| Nhân viên không có nhiệm vụ với hồ sơ tìm kênh đầy đủ | Bị giới hạn truy cập và có dấu vết audit phù hợp |
| Một người lạ liên tục yêu cầu khám phá hoặc gửi lại | Chống lạm dụng không tự khóa tài khoản hoặc hủy mọi session hợp lệ |

Bảng này mô tả hành vi cần xác minh khi triển khai. Phải kiểm tra dữ liệu thực sự được gửi và các nhánh thay thế, không chỉ chụp màn hình xem chuỗi đã được che hay chưa.

## 15. Bài tập áp dụng

**Đề bài:** Endpoint khám phá khôi phục luôn trả thông báo “Nếu tài khoản tồn tại, bạn sẽ nhận được hướng dẫn”. Tuy nhiên, tài khoản thật trả `methods` với email đầy đủ và số điện thoại đã che; tài khoản không khớp trả danh sách rỗng. Nếu nhà cung cấp SMS lỗi, endpoint trả lỗi riêng. Trang gửi lại cho biết chính xác số lần chờ theo số điện thoại, và nhân viên hỗ trợ có thể đọc toàn bộ kênh sau khi hỏi tên người dùng.

**Yêu cầu phân tích:**

1. Chỉ ra các đường tiết lộ còn lại dù câu thông báo đã chung.
2. Xác định thông tin nào nên là danh mục công khai và thông tin nào cần quyền riêng.
3. Thiết kế việc tiếp nhận, gửi challenge và xem tiến trình mà không trả kết quả tra cứu cho bên chưa xác minh.
4. Nêu cách hỗ trợ người đã mất kênh cũ mà không coi email mới là bằng chứng sở hữu tài khoản.
5. Đặt quyền và audit cho nhân viên hỗ trợ cùng dữ liệu quan sát nội bộ.

**Gợi ý:** Hợp đồng tiết lộ phải bao phủ payload, HTTP, nhánh lỗi, thời gian và trạng thái gửi lại. Che trên client không bảo vệ dữ liệu đã trả về. Cần kiểm soát quyền trước khi cung cấp gợi ý riêng, chỉ dùng đích đã được chấp nhận và giữ tách biệt quyền khám phá, xác minh kênh, thay kênh và khôi phục phương thức xác thực.

## 16. Điều cần ghi nhớ

Tránh tiết lộ kênh là kiểm soát **ai được biết thông tin nào, vào giai đoạn nào và để làm gì**. Một chuỗi đã che hoặc một câu phản hồi chung không đủ nếu API, lỗi, thời gian hay bộ phận hỗ trợ vẫn công bố dữ liệu phía sau.

Thiết kế phù hợp cung cấp hướng dẫn chung ở bước công khai, tiết lộ tối thiểu sau bằng chứng được chấp nhận và kiểm tra quyền ở máy chủ. Quyền biết một kênh hay kiểm soát một địa chỉ mới không tự trở thành quyền thay MFA, đổi đường khôi phục hoặc tạo session đầy đủ.