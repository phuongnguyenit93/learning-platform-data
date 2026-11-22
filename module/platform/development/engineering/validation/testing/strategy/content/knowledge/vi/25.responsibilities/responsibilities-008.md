# Thống nhất quyền phê duyệt thay đổi chiến lược và chấp nhận ngoại lệ

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), chiến lược kiểm thử chỉ có giá trị khi mọi người hiểu ai được quyền thay đổi nó, ai chịu trách nhiệm đánh giá tác động và ai có thể chấp nhận rủi ro khi không đáp ứng một tiêu chí đã thống nhất. Nếu quyền quyết định không rõ, nhóm có thể tự ý bỏ test, thay đổi ngưỡng chất lượng, hoãn kiểm tra bảo mật hoặc xem một khoảng trống bằng chứng như thể đã được chấp nhận.

Cần thiết lập cơ chế quản trị để phân biệt hai loại quyết định: **thay đổi chiến lược** và **chấp nhận ngoại lệ**. Thay đổi chiến lược điều chỉnh cách tổ chức kiểm thử trong một phạm vi xác định, chẳng hạn chuyển một nhóm test từ UI sang API, thay đổi lịch hồi quy hoặc điều chỉnh ma trận môi trường. Chấp nhận ngoại lệ cho phép tiếp tục dù một yêu cầu, tiêu chí hoặc hoạt động kiểm thử cụ thể chưa được đáp ứng đầy đủ. Hai quyết định có thể liên quan nhưng không thay thế nhau: phê duyệt thay đổi cách kiểm tra không tự động chấp nhận rủi ro còn lại; waiver cho một lần phát hành cũng không tự động sửa chính sách lâu dài.

Bài học này hướng dẫn cách xác định quyền quyết định, phân loại thay đổi, đánh giá tác động, thiết lập luồng phê duyệt, quản lý waiver và tình huống khẩn cấp, lưu vết quyết định và xử lý bất đồng. Mục tiêu là bảo đảm mọi thay đổi và ngoại lệ đều có lý do, phạm vi, người chịu trách nhiệm, thời hạn và bằng chứng đủ để xem xét lại.

## 1. Vì sao cần thống nhất quyền phê duyệt?

### 1.1. Chiến lược kiểm thử ảnh hưởng đến quyết định chất lượng

Chiến lược kiểm thử quy định phạm vi, tầng kiểm thử, mức độ bao phủ, môi trường, dữ liệu, lịch chạy, ngưỡng chất lượng và cách xử lý kết quả. Thay đổi một yếu tố có thể làm thay đổi loại bằng chứng mà nhóm có được.

Ví dụ:

- Bỏ một nhóm E2E có thể làm giảm bằng chứng về hành trình người dùng.
- Chuyển xác minh từ UI sang API có thể không còn kiểm tra được hiển thị và tương tác.
- Giảm tần suất full regression có thể làm lỗi tích lũy lâu hơn trước khi được phát hiện.
- Nới ngưỡng hiệu năng có thể làm hệ thống không còn đáp ứng kỳ vọng người dùng.
- Bỏ kiểm tra phân quyền có thể làm tăng nguy cơ truy cập trái phép.
- Dùng mock thay cho dependency thật có thể để lại khoảng trống về tích hợp.

Những thay đổi này cần được đánh giá bởi người hiểu mục tiêu, rủi ro và hậu quả. Người trực tiếp thực hiện test không nhất thiết có quyền chấp nhận mọi rủi ro phát sinh từ việc giảm phạm vi.

### 1.2. Ngoại lệ là quyết định rủi ro, không phải thao tác hành chính

Ngoại lệ có thể cần thiết khi môi trường không sẵn sàng, phụ thuộc bên ngoài gặp sự cố, một test không thể chạy trước thời hạn hoặc một yêu cầu chưa thể đáp ứng. Nhưng cho phép tiếp tục không có nghĩa là rủi ro biến mất.

Một ngoại lệ cần trả lời:

- Điều kiện nào chưa được đáp ứng?
- Tài sản, người dùng hoặc hành trình nào có thể bị ảnh hưởng?
- Vì sao không thể đáp ứng trong thời điểm này?
- Có bằng chứng thay thế nào?
- Biện pháp giảm thiểu nào được áp dụng?
- Ai có quyền chấp nhận rủi ro?
- Ngoại lệ có hiệu lực đến khi nào và điều kiện nào làm nó hết hiệu lực?

Nếu thiếu những thông tin này, quyết định dễ trở thành một lời đồng ý miệng không thể kiểm tra lại.

### 1.3. Tránh xung đột lợi ích và quyết định vượt thẩm quyền

Người chịu áp lực giao hàng có thể muốn bỏ kiểm thử để giữ ngày phát hành. Người chịu trách nhiệm chất lượng có thể muốn giữ toàn bộ phạm vi. Người có quyền chấp nhận rủi ro cần xem xét cả giá trị kinh doanh, tác động, nghĩa vụ và biện pháp giảm thiểu.

Một người có thể đề xuất, đánh giá và thực hiện thay đổi, nhưng quyết định chấp nhận rủi ro quan trọng nên thuộc vai trò được tổ chức giao thẩm quyền. Với rủi ro bảo mật, quyền riêng tư, an toàn hoặc tuân thủ, cần có ý kiến của chuyên gia và người sở hữu nghĩa vụ tương ứng.

### 1.4. Quyền quyết định rõ giúp phản hồi nhanh hơn

Cơ chế phê duyệt không nên tạo ra nhiều tầng ký tên cho mọi thay đổi nhỏ. Khi đã phân loại mức ảnh hưởng và xác định ngưỡng quyền hạn, nhóm có thể tự xử lý thay đổi rủi ro thấp, đồng thời chuyển nhanh các quyết định quan trọng đến đúng người.

Điều cần chuẩn hóa là ai quyết định loại việc nào, thông tin tối thiểu cần có và thời gian phản hồi kỳ vọng.

## 2. Phân biệt thay đổi chiến lược, sai lệch và ngoại lệ

### 2.1. Thay đổi chiến lược kiểm thử

Thay đổi chiến lược là điều chỉnh có chủ đích đối với cách kiểm thử được tổ chức hoặc thực hiện. Ví dụ:

- Thay đổi tỷ trọng unit, API, integration và E2E.
- Thay đổi test suite bắt buộc chạy trên pull request.
- Điều chỉnh lịch nightly hoặc full regression.
- Thay đổi ma trận browser, thiết bị hoặc môi trường.
- Chuyển một nhóm kiểm tra từ thủ công sang tự động.
- Thay đổi cách chuẩn bị dữ liệu hoặc cấp phát môi trường.
- Điều chỉnh ngưỡng chất lượng hoặc tiêu chí hoàn tất.
- Thay đổi trách nhiệm giữa QA, developer, security và operations.

Thay đổi có thể áp dụng lâu dài, theo một release hoặc chỉ trong một phạm vi module. Phạm vi và thời hạn phải được nêu rõ.

### 2.2. Sai lệch so với kế hoạch

Sai lệch là việc thực tế không diễn ra như kế hoạch hoặc tiêu chí đã thống nhất. Ví dụ:

- Test bắt buộc không chạy vì môi trường lỗi.
- Một suite bị skip do runner thiếu tài nguyên.
- Môi trường dùng sai phiên bản artifact.
- Dữ liệu chuẩn bị không đúng trạng thái.
- Một test flaky không thể cho kết quả đáng tin.
- Một hoạt động kiểm thử bị trễ so với lịch.

Sai lệch cần được ghi nhận và đánh giá. Không nên âm thầm đổi kế hoạch sau khi kết quả đã có để biến sai lệch thành hoàn thành.

### 2.3. Ngoại lệ hoặc waiver

Ngoại lệ là quyết định có thẩm quyền cho phép tiếp tục trong khi một điều kiện cụ thể chưa được đáp ứng, với rủi ro còn lại được ghi nhận. Waiver có thể áp dụng cho:

- Một tiêu chí chất lượng chưa đạt.
- Một test bắt buộc chưa thể thực thi.
- Một nền tảng hoặc môi trường chưa được xác minh.
- Một lỗi còn mở được đề xuất chấp nhận có điều kiện.
- Một hoạt động kiểm tra bị trì hoãn đến mốc khác.

Waiver không thay đổi sự thật về kết quả kiểm thử. Nếu test thất bại, báo cáo vẫn phải ghi FAIL. Nếu test chưa chạy, trạng thái vẫn là NOT RUN hoặc BLOCKED. Waiver chỉ ghi nhận quyết định quản lý rủi ro cho phép tiếp tục trong phạm vi cụ thể.

### 2.4. Xử lý khẩn cấp

Thay đổi khẩn cấp có thể cần thực hiện trước quy trình phê duyệt thông thường, ví dụ khi phải khôi phục dịch vụ hoặc xử lý sự cố bảo mật. Tuy vậy, cần có người có thẩm quyền được chỉ định, giới hạn hành động, ghi nhận lý do và rà soát sau khi ổn định.

Khẩn cấp không đồng nghĩa với không cần lưu vết. Cần xác định trước ai được kích hoạt quy trình, hành động nào được phép và thời hạn hoàn tất đánh giá sau sự kiện.

### 2.5. Bảng phân biệt

| Loại quyết định | Câu hỏi cần trả lời | Ví dụ | Kết quả cần lưu |
|---|---|---|---|
| Thay đổi chiến lược | Cách kiểm thử có nên thay đổi không? | Chuyển một nhóm kiểm tra thường xuyên từ UI sang API và giữ E2E đại diện. | Phê duyệt thay đổi, phạm vi, ngày hiệu lực và kế hoạch triển khai. |
| Sai lệch | Điều gì đã không diễn ra theo kế hoạch? | Full suite không chạy vì database test bị lỗi. | Báo cáo sai lệch, tác động và hành động khắc phục. |
| Ngoại lệ/waiver | Có chấp nhận tiếp tục dù điều kiện chưa đạt không? | Một browser ít sử dụng chưa được kiểm tra trong release này. | Hồ sơ waiver, rủi ro còn lại, người chấp nhận và ngày hết hạn. |
| Khẩn cấp | Cần hành động ngay để hạn chế sự cố nào? | Tạm dừng rollout hoặc tắt feature flag để bảo vệ dữ liệu. | Nhật ký hành động, người chỉ huy và review sau sự cố. |

Một đề xuất có thể cần nhiều quyết định. Ví dụ, thay đổi lâu dài lịch full regression là thay đổi chiến lược; việc phát hành hiện tại khi suite chưa chạy lại là một ngoại lệ riêng.

## 3. Nguyên tắc quản trị quyền quyết định

### 3.1. Quyền hạn phải gắn với trách nhiệm và mức rủi ro

Người có quyền phê duyệt cần hiểu hoặc có khả năng tiếp nhận đánh giá chuyên môn về tác động của quyết định. Quyền hạn nên được xác định theo:

- Phạm vi sản phẩm hoặc module.
- Mức độ nghiêm trọng của rủi ro.
- Loại nghĩa vụ bị ảnh hưởng.
- Mức thay đổi đối với phạm vi và bằng chứng.
- Tác động đến người dùng, dữ liệu và vận hành.
- Phạm vi thời gian và số release bị ảnh hưởng.

Không nên cấp quyền phê duyệt vô hạn cho một vai trò chỉ vì vai trò đó sở hữu lịch phát hành.

### 3.2. Tách người đề xuất, người đánh giá và người chấp nhận

Có thể một người kiêm nhiều vai trò ở nhóm nhỏ, nhưng với quyết định rủi ro cao cần tránh tự đề xuất rồi tự chấp nhận mà không có review độc lập.

- **Người đề xuất:** mô tả thay đổi hoặc ngoại lệ và lý do.
- **Người đánh giá:** phân tích tác động kỹ thuật, kiểm thử, bảo mật, vận hành và nghiệp vụ.
- **Người phê duyệt:** quyết định trong phạm vi thẩm quyền.
- **Người thực hiện:** triển khai thay đổi hoặc biện pháp giảm thiểu.
- **Người xác minh:** kiểm tra thay đổi đã được thực hiện đúng và bằng chứng được cập nhật.

Người phê duyệt không nhất thiết trực tiếp chạy test, nhưng phải có đủ thông tin để hiểu điều gì đang được chấp nhận.

### 3.3. Quyết định phải có phạm vi cụ thể

Không chấp nhận mô tả rộng như “bỏ qua test cho release” hoặc “QA đồng ý”. Hồ sơ phải nêu rõ:

- Module, tính năng hoặc release.
- Test, tiêu chí hoặc môi trường bị ảnh hưởng.
- Phiên bản và khoảng thời gian.
- Người dùng hoặc tài sản có thể bị tác động.
- Điều kiện áp dụng và điều kiện dừng.
- Những phần vẫn phải được kiểm tra.

Một waiver cho một test trên một browser không tự động áp dụng cho các browser khác hoặc các release tiếp theo.

### 3.4. Không hạ thấp yêu cầu bắt buộc ngoài thẩm quyền

Yêu cầu pháp lý, hợp đồng, chính sách bảo mật, quyền riêng tư hoặc an toàn có thể không được miễn trừ bởi chủ sở hữu dự án thông thường. Khi có xung đột, cần chuyển đến vai trò hoặc cơ quan có thẩm quyền theo chính sách tổ chức.

Người phê duyệt chiến lược kiểm thử không mặc nhiên có quyền miễn trừ mọi nghĩa vụ. Nếu không xác định được thẩm quyền, trạng thái cần là chờ quyết định hoặc không được phép tiếp tục theo điều kiện đang áp dụng.

### 3.5. Quyết định phải có thể xem xét lại

Mọi thay đổi hoặc ngoại lệ cần có lý do, bằng chứng, người chịu trách nhiệm và thời hạn rà soát. Quyết định có thể hết hiệu lực khi:

- Release hoặc phiên bản kết thúc.
- Môi trường hoặc dependency thay đổi.
- Rủi ro tăng lên.
- Biện pháp giảm thiểu không còn hoạt động.
- Thời hạn waiver hết.
- Một sự cố mới làm thay đổi đánh giá.

Không nên để ngoại lệ tạm thời trở thành chính sách mặc định chỉ vì không ai quay lại xem xét.

## 4. Phân loại thay đổi theo mức ảnh hưởng

Một mô hình phân loại giúp xác định cấp phê duyệt tương ứng. Tổ chức có thể điều chỉnh các mức sau.

### 4.1. Thay đổi mức thấp

Đặc điểm:

- Không giảm phạm vi kiểm tra rủi ro quan trọng.
- Không thay đổi tiêu chí chất lượng hoặc gate phát hành.
- Không ảnh hưởng nghĩa vụ bảo mật, quyền riêng tư hoặc tuân thủ.
- Không làm thay đổi bằng chứng cần thiết cho quyết định phát hành.
- Có thể hoàn tác dễ dàng.

Ví dụ:

- Sắp xếp lại thứ tự chạy test độc lập.
- Bổ sung log chẩn đoán không chứa dữ liệu nhạy cảm.
- Điều chỉnh nhãn hoặc metadata của test.
- Tối ưu setup mà không thay đổi điều kiện và assertion.

Có thể giao test lead hoặc người sở hữu bộ test phê duyệt theo quy trình đã thống nhất.

### 4.2. Thay đổi mức trung bình

Đặc điểm:

- Thay đổi phạm vi hoặc cách thực hiện trong một module.
- Có tác động giới hạn và có bằng chứng thay thế.
- Không hạ một gate bắt buộc.
- Có thể cần phối hợp với một hoặc nhiều nhóm.

Ví dụ:

- Thay đổi một số test UI thành API test, đồng thời giữ kiểm tra hành trình đại diện.
- Thay đổi lịch chạy một suite ít rủi ro.
- Dùng môi trường sandbox mới đã được xác minh.
- Điều chỉnh fixture hoặc dữ liệu test mà không làm giảm phạm vi mục tiêu.

Thường cần review của test lead và technical owner; product owner hoặc service owner tham gia khi hành vi nghiệp vụ bị ảnh hưởng.

### 4.3. Thay đổi mức cao

Đặc điểm:

- Giảm hoặc thay đổi bằng chứng cho rủi ro cao.
- Thay đổi tiêu chí hoàn tất, ngưỡng hiệu năng hoặc gate phát hành.
- Ảnh hưởng nhiều module, tenant hoặc nhóm người dùng.
- Có liên quan đến bảo mật, dữ liệu, tiền hoặc tính sẵn sàng.
- Có thể tạo rủi ro khó đảo ngược.

Ví dụ:

- Loại bỏ kiểm tra phân quyền bắt buộc.
- Nới ngưỡng hiệu năng của một API cốt lõi.
- Bỏ full regression trước release lớn.
- Thay dependency thật bằng mock trong kiểm tra cần bằng chứng tích hợp.
- Chấp nhận lỗi có thể làm sai trạng thái giao dịch.

Cần đánh giá liên chức năng và phê duyệt bởi người có thẩm quyền về sản phẩm, kỹ thuật, chất lượng và chuyên môn liên quan. Với nghĩa vụ bảo mật hoặc tuân thủ, cần có phê duyệt của vai trò tương ứng.

### 4.4. Ma trận phân loại tham khảo

| Mức | Ví dụ tác động | Review tối thiểu | Quyết định |
|---|---|---|---|
| Thấp | Không giảm bằng chứng, không thay đổi gate. | Test owner. | Test lead hoặc owner được ủy quyền. |
| Trung bình | Thay đổi cục bộ, có bằng chứng thay thế. | Test lead và technical owner; thêm product owner nếu cần. | Người sở hữu phạm vi hoặc quản lý chất lượng được ủy quyền. |
| Cao | Ảnh hưởng rủi ro trọng yếu, gate hoặc nhiều hệ thống. | QA, engineering, product và chuyên gia liên quan. | Người sở hữu rủi ro/release có thẩm quyền cùng phê duyệt chuyên môn bắt buộc. |
| Bị cấm hoặc ngoài thẩm quyền | Vi phạm nghĩa vụ bắt buộc hoặc không có quyền thực hiện. | Chuyển đến cơ quan có thẩm quyền. | Không được tự phê duyệt trong nhóm dự án. |

Không nên phân loại chỉ theo số lượng test bị thay đổi. Bỏ một test phân quyền duy nhất có thể nghiêm trọng hơn bỏ hàng chục test giao diện ít rủi ro.

## 5. Xác định vai trò và quyền phê duyệt

### 5.1. Vai trò thường gặp

| Vai trò | Trách nhiệm trong quyết định |
|---|---|
| Test lead / QA lead | Đánh giá phạm vi, độ bao phủ, chất lượng bằng chứng và tác động đến test strategy. |
| Test owner | Giải thích mục tiêu của test, rủi ro được bảo vệ và phương án thay thế. |
| Engineering lead / architect | Đánh giá tác động kỹ thuật, kiến trúc, dependency và khả năng đảo ngược. |
| Product owner / business owner | Đánh giá tác động nghiệp vụ, người dùng và ưu tiên. |
| Security / privacy / compliance | Đánh giá nghĩa vụ và rủi ro thuộc chuyên môn; xác nhận yêu cầu bắt buộc. |
| Operations / SRE | Đánh giá readiness, giám sát, phục hồi và tác động vận hành. |
| Release owner / release manager | Điều phối quyết định phát hành trong phạm vi được giao và tổng hợp gate. |
| Risk owner | Chấp nhận rủi ro còn lại trong giới hạn thẩm quyền được tổ chức quy định. |
| Change authority / governance board | Quyết định thay đổi có phạm vi rộng hoặc vượt quyền của nhóm sản phẩm. |

Tên vai trò có thể khác nhau giữa các tổ chức. Điều quan trọng là trách nhiệm và quyền hạn phải được xác định rõ, không phụ thuộc vào tên chức danh.

### 5.2. Phân biệt tư vấn chuyên môn và quyền chấp nhận rủi ro

Chuyên gia bảo mật có thể kết luận một kiểm soát chưa đạt và đưa ra khuyến nghị. Product owner có thể đánh giá tác động kinh doanh. Release owner có thể tổng hợp trạng thái phát hành. Nhưng người có quyền chấp nhận rủi ro phải được chỉ định rõ.

Một quyết định có thể cần nhiều chữ ký cho các khía cạnh khác nhau. Ví dụ, việc chấp nhận một lỗ hổng có thể cần security owner xác nhận đánh giá kỹ thuật và risk owner có thẩm quyền chấp nhận tác động. Một bên không thay thế bên còn lại.

### 5.3. Ma trận quyền quyết định mẫu

| Quyết định | Đề xuất | Đánh giá | Phê duyệt cuối |
|---|---|---|---|
| Sắp xếp lại test không đổi phạm vi | Test owner | Test lead | Test lead được ủy quyền |
| Thay đổi cách kiểm tra trong một module | Test lead | Engineering owner, product owner nếu ảnh hưởng hành vi | Owner chiến lược của module |
| Giảm phạm vi hồi quy cho một release | Release/test lead | QA, engineering, product, operations | Release/risk owner theo chính sách |
| Thay đổi gate bảo mật hoặc quyền riêng tư | Security/test lead | Security, privacy/compliance và engineering | Vai trò có thẩm quyền về nghĩa vụ đó |
| Chấp nhận lỗi có rủi ro tài chính | Product/engineering | Finance/business, QA, security nếu liên quan | Risk owner có thẩm quyền |
| Thay đổi chiến lược áp dụng nhiều module | QA/engineering leadership | Các owner bị ảnh hưởng | Change authority hoặc governance board |
| Hành động khẩn cấp để hạn chế sự cố | Incident commander hoặc owner được chỉ định | Kỹ thuật, security, operations | Người chỉ huy theo quy trình sự cố; review sau sự kiện |

Bảng này là khung tham khảo. Nhóm cần ghi tên vai trò hoặc người thay thế thực tế, giới hạn thẩm quyền và quy trình khi người phê duyệt vắng mặt.

### 5.4. Dùng RACI để làm rõ trách nhiệm

RACI có thể được dùng để xác định ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai cần được thông báo:

- **R – Responsible:** trực tiếp thực hiện hoặc chuẩn bị hồ sơ.
- **A – Accountable:** chịu trách nhiệm cuối cùng cho quyết định hoặc đầu ra; nên có một vai trò A rõ ràng cho mỗi quyết định.
- **C – Consulted:** cung cấp ý kiến trước khi quyết định.
- **I – Informed:** được thông báo về quyết định và tác động.

Ví dụ:

| Hoạt động | QA lead | Engineering lead | Product owner | Security | Release owner |
|---|---|---|---|---|---|
| Đề xuất thay đổi test strategy | R | C | C | C nếu liên quan | I |
| Đánh giá tác động kỹ thuật | C | A/R | C | C nếu liên quan | I |
| Đánh giá khoảng trống bằng chứng | A/R | C | C | C nếu liên quan | I |
| Chấp nhận rủi ro nghiệp vụ | C | C | A/R theo thẩm quyền | C | C |
| Chấp nhận rủi ro bảo mật | C | C | C | R/C | A chỉ nếu có thẩm quyền; nếu không phải risk owner được chỉ định |
| Tổng hợp quyết định release | R/C | C | C | C | A/R theo chính sách |

Không dùng RACI để tạo ra quyền phê duyệt mà tổ chức chưa giao. Ma trận cần phản ánh quy định và phân quyền thực tế.

## 6. Quy trình đề xuất và phê duyệt thay đổi chiến lược

### 6.1. Bước 1: Mô tả thay đổi

Người đề xuất cần ghi:

- Điều gì đang được áp dụng?
- Muốn thay đổi điều gì?
- Phạm vi module, test suite, môi trường hoặc release.
- Lý do và vấn đề cần giải quyết.
- Thời điểm có hiệu lực.
- Thay đổi tạm thời hay lâu dài.

Mô tả cần cụ thể để người review hiểu khác biệt trước và sau.

### 6.2. Bước 2: Phân tích tác động và rủi ro

Đánh giá:

- Mục tiêu nào được hỗ trợ hoặc bị ảnh hưởng?
- Rủi ro nào không còn được kiểm tra như trước?
- Bằng chứng hiện tại nào bị mất hoặc thay đổi?
- Có bằng chứng thay thế nào?
- Tác động đến người dùng, dữ liệu, bảo mật và vận hành?
- Tác động đến thời gian pipeline, chi phí và nguồn lực?
- Có ảnh hưởng đến các nhóm hoặc consumer khác không?
- Có yêu cầu bắt buộc nào bị ảnh hưởng không?

Không chỉ nêu lợi ích như giảm thời gian chạy. Cần chỉ ra giá trị bằng chứng bị giảm và cách kiểm soát rủi ro đó.

### 6.3. Bước 3: Xác định phương án và khả năng đảo ngược

So sánh các phương án:

- Giữ nguyên chiến lược.
- Thay đổi một phần.
- Thử nghiệm giới hạn trong một module hoặc một chu kỳ.
- Áp dụng thay đổi có điều kiện.
- Hoãn thay đổi đến khi có thêm bằng chứng.

Ghi cách rollback nếu thay đổi làm giảm chất lượng hoặc tạo vấn đề. Với thay đổi lớn, có thể chạy song song cách cũ và mới trong một khoảng thời gian để so sánh kết quả.

### 6.4. Bước 4: Lấy review đúng chuyên môn

Gửi hồ sơ cho các owner liên quan. Ví dụ:

- QA xem xét độ bao phủ và bằng chứng.
- Engineering xem xét kiến trúc và tính khả thi.
- Product xem xét tác động nghiệp vụ.
- Security/privacy xem xét nghĩa vụ và rủi ro dữ liệu.
- Operations xem xét readiness, alert và phục hồi.

Ý kiến phản đối hoặc điều kiện cần được ghi lại, không chỉ lưu trạng thái “approved”.

### 6.5. Bước 5: Phê duyệt theo mức ảnh hưởng

Người phê duyệt xác nhận:

- Phạm vi và thời hạn.
- Rủi ro đã hiểu.
- Điều kiện bắt buộc và bằng chứng thay thế.
- Điều kiện triển khai.
- Kế hoạch theo dõi và rollback.
- Người chịu trách nhiệm.
- Ngày xem xét lại.

Nếu đề xuất vượt quyền hoặc ảnh hưởng nghĩa vụ bắt buộc, phải chuyển đến cấp có thẩm quyền. Không suy diễn sự im lặng thành phê duyệt.

### 6.6. Bước 6: Triển khai và xác minh thay đổi

Sau khi được duyệt:

- Cập nhật test plan, test suite, lịch hoặc cấu hình.
- Thông báo cho các nhóm bị ảnh hưởng.
- Xác minh thay đổi được thực hiện đúng phạm vi.
- Chạy kiểm tra xác nhận hoặc pilot nếu cần.
- Theo dõi chỉ số và lỗi phát sinh.
- Lưu bằng chứng và liên kết với quyết định phê duyệt.

Phê duyệt trên tài liệu không chứng minh cấu hình thực tế đã được cập nhật đúng.

### 6.7. Bước 7: Đánh giá sau thay đổi

Tại ngày hoặc mốc đã thống nhất, xem xét:

- Thay đổi có đạt lợi ích dự kiến không?
- Có lỗi hoặc khoảng trống mới không?
- Bằng chứng có còn đủ cho quyết định chất lượng không?
- Có cần tiếp tục, điều chỉnh hay rollback?
- Có cần cập nhật chính sách chung không?

Thay đổi thử nghiệm cần có điều kiện kết thúc. Nếu không đánh giá sau pilot, thay đổi tạm thời có thể tồn tại mà không có quyết định chính thức.

## 7. Quy trình đề xuất và chấp nhận ngoại lệ

### 7.1. Khi nào cần waiver?

Waiver có thể được xem xét khi:

- Một test bắt buộc không thể chạy vì dependency ngoài kiểm soát.
- Một môi trường hoặc nền tảng chưa sẵn sàng.
- Một lỗi đã biết chưa thể sửa trước release.
- Một ngưỡng chất lượng chưa đạt nhưng có biện pháp giảm thiểu.
- Một phần phạm vi được hoãn vì lý do đã đánh giá.
- Một hoạt động kiểm tra cần thời gian bổ sung và có bằng chứng thay thế giới hạn.

Không phải mọi lỗi hoặc thiếu sót đều nên được waiver. Nếu rủi ro không thể giảm xuống mức chấp nhận được hoặc không có người đủ thẩm quyền, cần giữ quyết định ở trạng thái không được phê duyệt.

### 7.2. Nội dung tối thiểu của hồ sơ waiver

Một hồ sơ nên có:

1. Mã định danh waiver.
2. Sản phẩm, module, release và phiên bản.
3. Tiêu chí hoặc hoạt động chưa đáp ứng.
4. Kết quả thực tế: FAIL, BLOCKED hoặc NOT RUN.
5. Lý do và nguyên nhân.
6. Tài sản, người dùng và quy trình bị ảnh hưởng.
7. Khả năng xảy ra, tác động và mức rủi ro.
8. Bằng chứng hiện có và phần còn thiếu.
9. Biện pháp giảm thiểu hoặc bằng chứng thay thế.
10. Điều kiện tiếp tục và điều kiện dừng.
11. Người đề xuất, reviewer và người chấp nhận.
12. Ngày hiệu lực, ngày hết hạn và người xử lý.
13. Kế hoạch khắc phục hoặc kiểm tra lại.

Một waiver không có ngày hết hạn hoặc người chịu trách nhiệm thường trở thành ngoại lệ vĩnh viễn.

### 7.3. Đánh giá bằng chứng thay thế

Bằng chứng thay thế có thể giảm rủi ro nhưng cần nêu giới hạn. Ví dụ:

- E2E test không chạy được, nhưng API và integration test đã xác minh một phần luồng.
- Browser phụ không sẵn sàng, nhưng browser chính đã được kiểm tra.
- Sandbox nhà cung cấp gặp sự cố, nhưng contract test và mock đã xác minh logic nội bộ.

Các bằng chứng này không tương đương hoàn toàn. Cần ghi rõ phần chưa được xác minh: rendering trên browser phụ, hành vi dependency thật hoặc toàn bộ hành trình người dùng.

Không dùng bằng chứng thay thế để tuyên bố tiêu chí gốc đã đạt nếu nó không kiểm tra cùng mục tiêu.

### 7.4. Điều kiện chấp nhận waiver

Người phê duyệt nên xem xét:

- Rủi ro còn lại có nằm trong giới hạn được phép không?
- Có biện pháp giảm thiểu khả thi không?
- Có thể giới hạn rollout, người dùng hoặc tính năng không?
- Có giám sát và phát hiện sự cố đủ nhanh không?
- Có kế hoạch rollback hoặc tắt tính năng không?
- Có thời hạn khắc phục rõ không?
- Các nghĩa vụ bắt buộc có cho phép ngoại lệ không?
- Người chấp nhận có đúng thẩm quyền không?

Nếu câu trả lời cho điều kiện bắt buộc là không, waiver không được dùng để hợp thức hóa việc tiếp tục.

### 7.5. Theo dõi và đóng waiver

Waiver cần được theo dõi như một công việc có owner:

- Nhắc trước ngày hết hạn.
- Theo dõi hành động khắc phục.
- Đánh giá lại khi có thay đổi hoặc sự cố.
- Gia hạn chỉ khi có đánh giá mới và phê duyệt lại.
- Đóng khi tiêu chí đã được đáp ứng hoặc rủi ro không còn.
- Lưu bằng chứng đóng và kết quả kiểm tra lại.

Không tự động gia hạn chỉ vì chưa hoàn thành công việc khắc phục.

## 8. Quy trình thay đổi khẩn cấp và quyết định trong sự cố

### 8.1. Khi nào dùng quy trình khẩn cấp?

Có thể dùng khi cần hành động nhanh để ngăn hoặc giảm tác động nghiêm trọng, chẳng hạn:

- Dừng rollout gây lỗi dữ liệu.
- Tắt feature flag gây ảnh hưởng người dùng.
- Thu hồi credential bị lộ.
- Cô lập service đang làm lộ dữ liệu.
- Tạm dừng job tạo giao dịch trùng.
- Áp dụng biện pháp phục hồi để khôi phục dịch vụ.

Quy trình khẩn cấp không phải cách rút ngắn thông thường cho thay đổi đã biết từ trước.

### 8.2. Quyền chỉ huy và phạm vi hành động

Tổ chức cần xác định trước người có quyền điều phối sự cố và vai trò thay thế. Người chỉ huy cần:

- Xác định mục tiêu hạn chế tác động.
- Giao người thực hiện và người review khi có thể.
- Giới hạn phạm vi và thời gian hành động.
- Ghi lại quyết định, thời điểm và bằng chứng.
- Thông báo cho các bên liên quan.
- Bảo đảm có kế hoạch xác minh và phục hồi.

Nếu phải thực hiện hành động một người phê duyệt duy nhất trong thời gian khẩn cấp, cần ghi lý do và yêu cầu review độc lập ngay sau khi tình huống ổn định.

### 8.3. Review sau sự cố

Sau khi xử lý:

1. Tập hợp timeline, hành động và người tham gia.
2. Xác định thay đổi nào được thực hiện ngoài quy trình thường.
3. Đánh giá tác động và rủi ro còn lại.
4. Xác minh trạng thái hệ thống sau phục hồi.
5. Hoàn tất phê duyệt hoặc ghi nhận quyết định sau sự kiện theo chính sách.
6. Cập nhật chiến lược, test và runbook.
7. Tạo hành động phòng ngừa tái diễn.

Review sau sự cố không nhằm hợp thức hóa hành động sai thẩm quyền; nó giúp xác định trách nhiệm, tác động và cải tiến quy trình.

## 9. Lưu vết, truyền thông và kiểm toán quyết định

### 9.1. Hồ sơ quyết định tập trung

Mỗi thay đổi hoặc waiver cần một định danh để truy vết từ đề xuất đến triển khai và kết quả. Có thể lưu trong change management system, issue tracker hoặc kho tài liệu được kiểm soát.

Thông tin nên gồm:

- ID và loại quyết định.
- Người đề xuất, reviewer, approver.
- Phạm vi và ngày hiệu lực.
- Phiên bản hoặc release liên quan.
- Mục tiêu, rủi ro và bằng chứng.
- Ý kiến chuyên môn và điều kiện phê duyệt.
- Trạng thái triển khai.
- Ngày xem xét lại và kết quả.
- Liên kết đến test run, bug và release record.

Không chỉ lưu ảnh chụp màn hình trạng thái approved. Cần giữ nội dung quyết định và căn cứ.

### 9.2. Truyền thông đến người bị ảnh hưởng

Sau phê duyệt, thông báo cho:

- Nhóm phát triển và QA.
- Chủ sở hữu service hoặc module.
- Security, privacy hoặc operations nếu liên quan.
- Người quản lý release.
- Các nhóm phụ thuộc hoặc consumer.
- Người cần xử lý hành động còn mở.

Thông báo phải nêu điều gì thay đổi, khi nào có hiệu lực, ai chịu trách nhiệm và rủi ro nào cần lưu ý. Người thực hiện test cần biết test nào vẫn bắt buộc và test nào bị giới hạn bởi waiver.

### 9.3. Bảo đảm tính toàn vẹn của kết quả test

Quyết định quản trị không được làm sai lệch kết quả thực thi:

- FAIL vẫn là FAIL.
- BLOCKED vẫn là BLOCKED.
- NOT RUN vẫn là NOT RUN.
- Waiver được lưu riêng và liên kết với kết quả.
- Test bị quarantine vẫn cần lý do, owner và thời hạn.
- Bằng chứng gốc cần được giữ theo chính sách.

Điều này giúp người review phân biệt chất lượng kỹ thuật thực tế với quyết định chấp nhận rủi ro.

### 9.4. Rà soát định kỳ quyền phê duyệt

Khi tổ chức thay đổi, người giữ vai trò hoặc phạm vi trách nhiệm có thể thay đổi. Cần rà soát:

- Ai hiện có quyền phê duyệt loại thay đổi nào?
- Quyền có vượt quá trách nhiệm không?
- Có người phê duyệt dự phòng không?
- Có quyết định nào được phê duyệt sai cấp không?
- Có waiver hết hạn nhưng chưa đóng không?
- Có thay đổi tạm thời đã trở thành mặc định không?

Quyền phê duyệt nên được cập nhật khi vai trò, cấu trúc tổ chức hoặc chính sách thay đổi.

## 10. Xử lý bất đồng và xung đột lợi ích

### 10.1. Làm rõ loại bất đồng

Bất đồng có thể liên quan đến:

- Sự kiện: test có thực sự chạy hay không?
- Kỹ thuật: bằng chứng thay thế có tương đương không?
- Rủi ro: hậu quả và khả năng xảy ra được đánh giá thế nào?
- Nghiệp vụ: lợi ích phát hành có đáng với rủi ro không?
- Thẩm quyền: ai có quyền quyết định?
- Nghĩa vụ: có thể miễn trừ yêu cầu này không?

Hãy tách các câu hỏi để tránh tranh luận chung chung.

### 10.2. Dùng bằng chứng và tiêu chí đã thống nhất

Khi có bất đồng, quay lại:

- Mục tiêu và tiêu chí hoàn tất.
- Rủi ro và tài sản bị ảnh hưởng.
- Kết quả test và giới hạn bằng chứng.
- Chính sách, hợp đồng hoặc nghĩa vụ liên quan.
- Phạm vi quyền được giao.

Nếu thông tin chưa đủ, yêu cầu bổ sung bằng chứng hoặc đánh giá chuyên môn. Không giải quyết bất đồng bằng cách đổi nhãn severity hoặc bỏ test khỏi báo cáo.

### 10.3. Escalation theo mức rủi ro

Nếu các owner không thống nhất, chuyển quyết định lên vai trò có thẩm quyền cao hơn theo ma trận. Với rủi ro bảo mật, quyền riêng tư, an toàn hoặc tuân thủ, cần escalation đến chuyên gia hoặc cơ quan tương ứng.

Trong khi chờ quyết định, giữ trạng thái chưa được phê duyệt. Không mặc định rằng deadline hoặc sự im lặng đồng nghĩa với chấp nhận.

### 10.4. Ghi nhận ý kiến thiểu số và điều kiện

Nếu một chuyên gia phản đối, ý kiến và cơ sở cần được ghi lại. Người quyết định có thể đưa ra kết luận khác trong phạm vi thẩm quyền, nhưng cần nêu lý do và biện pháp giảm thiểu. Điều này giúp tổ chức hiểu rủi ro đã được nhận diện và cân nhắc như thế nào.

## 11. Ví dụ: phê duyệt ngoại lệ trước release

Giả sử một release có thay đổi luồng đặt hàng. Full regression đã chạy, nhưng test trên một browser phụ bị BLOCKED do browser grid gặp sự cố. Các browser chính đã đạt; API, integration và E2E trên browser chính không phát hiện lỗi. Browser phụ vẫn nằm trong ma trận hỗ trợ của sản phẩm.

### 11.1. Đánh giá trước khi đề xuất

Nhóm cần xác định:

- Browser nào bị ảnh hưởng và phiên bản nào.
- Mức sử dụng của browser đó.
- Thay đổi có tác động đến CSS, JavaScript, storage hoặc API không.
- Test nào chưa chạy và rủi ro nào được bảo vệ.
- Bằng chứng từ browser khác có thể thay thế phần nào.
- Có thể dùng môi trường khác hoặc chạy lại trước release không.
- Có thể giới hạn rollout hoặc theo dõi lỗi sau triển khai không.

Không được kết luận browser phụ đạt chỉ vì browser chính đạt.

### 11.2. Hồ sơ waiver

Hồ sơ có thể ghi:

- Phạm vi: một ma trận browser cho release cụ thể.
- Trạng thái: test browser phụ BLOCKED do hạ tầng.
- Rủi ro: lỗi hiển thị hoặc tương tác chỉ xuất hiện trên browser đó.
- Bằng chứng hiện có: API/integration đạt và UI trên browser chính đạt.
- Giảm thiểu: kiểm tra thủ công trên thiết bị thay thế nếu được hỗ trợ, giám sát lỗi client và giới hạn rollout nếu cần.
- Hành động: khôi phục browser grid và chạy lại trước ngày hết hạn.
- Owner: QA automation owner.
- Approver: release/risk owner theo ma trận quyền.
- Hết hạn: ngày hoặc mốc phát hành tiếp theo đã định.

### 11.3. Quyết định và theo dõi

Nếu người có thẩm quyền chấp nhận rủi ro, release có thể tiếp tục trong phạm vi được ghi. Kết quả test browser phụ vẫn là BLOCKED; waiver được liên kết riêng. Khi browser grid hoạt động, nhóm phải chạy lại, cập nhật bằng chứng và đóng waiver.

Nếu đánh giá cho thấy thay đổi ảnh hưởng trực tiếp đến một hành vi quan trọng chỉ có trên browser phụ, biện pháp giảm thiểu có thể không đủ. Khi đó, người phê duyệt cần từ chối waiver hoặc yêu cầu hoãn release.

## 12. Mẫu hồ sơ thay đổi chiến lược và waiver

### 12.1. Mẫu đề xuất thay đổi chiến lược

~~~text
CHANGE ID:
Tên thay đổi:
Người đề xuất:
Ngày đề xuất:
Phạm vi module / release:
Chiến lược hiện tại:
Thay đổi đề xuất:
Lý do và lợi ích dự kiến:

Mục tiêu bị ảnh hưởng:
Rủi ro được giảm:
Rủi ro có thể tăng:
Test / bằng chứng bị thay đổi:
Bằng chứng thay thế:
Tác động đến môi trường, dữ liệu và nguồn lực:

Mức ảnh hưởng:
Ý kiến QA:
Ý kiến Engineering:
Ý kiến Product:
Ý kiến Security / Privacy / Operations:
Điều kiện phê duyệt:
Kế hoạch triển khai:
Kế hoạch rollback:
Người phê duyệt:
Ngày hiệu lực:
Ngày đánh giá lại:
Kết quả sau triển khai:
~~~

### 12.2. Mẫu hồ sơ waiver / chấp nhận ngoại lệ

~~~text
WAIVER ID:
Sản phẩm / module / release:
Người đề xuất:
Ngày đề xuất:

Tiêu chí hoặc hoạt động chưa đáp ứng:
Trạng thái thực tế (FAIL / BLOCKED / NOT RUN):
Lý do và nguyên nhân:
Tài sản / người dùng / quy trình bị ảnh hưởng:
Rủi ro và mức độ:
Bằng chứng hiện có:
Khoảng trống bằng chứng:
Biện pháp giảm thiểu:
Bằng chứng thay thế và giới hạn:

Điều kiện tiếp tục:
Điều kiện dừng / rollback:
Hành động khắc phục:
Owner:
Reviewer chuyên môn:
Risk owner / approver:
Ngày hiệu lực:
Ngày hết hạn:
Ngày xem xét lại:
Trạng thái waiver:
Bằng chứng đóng waiver:
~~~

### 12.3. Checklist trước khi phê duyệt

- [ ] Loại quyết định được phân biệt rõ: thay đổi, sai lệch, waiver hay khẩn cấp.
- [ ] Phạm vi, phiên bản và thời hạn được xác định.
- [ ] Mục tiêu và rủi ro bị ảnh hưởng được mô tả.
- [ ] Bằng chứng hiện có và phần còn thiếu được trình bày trung thực.
- [ ] Bằng chứng thay thế có giới hạn rõ.
- [ ] Mức ảnh hưởng và cấp phê duyệt phù hợp.
- [ ] Các chuyên gia cần thiết đã được tham vấn.
- [ ] Người phê duyệt có thẩm quyền thực tế.
- [ ] Biện pháp giảm thiểu và điều kiện dừng được xác định.
- [ ] Có owner, thời hạn và kế hoạch xem xét lại.
- [ ] Yêu cầu pháp lý, hợp đồng và chính sách bắt buộc được tôn trọng.
- [ ] Kết quả test gốc không bị thay đổi để phản ánh waiver.

## 13. Những sai lầm thường gặp

- **Để người đề xuất tự chấp nhận mọi rủi ro:** tạo xung đột lợi ích và vượt thẩm quyền.
- **Không phân biệt thay đổi chiến lược với waiver:** một quyết định lâu dài và một ngoại lệ tạm thời bị trộn lẫn.
- **Phê duyệt bằng lời nói hoặc tin nhắn không có phạm vi:** khó truy vết và dễ bị hiểu rộng.
- **Dùng chức danh thay cho quyền hạn được giao:** người có vai trò cao chưa chắc có quyền miễn trừ nghĩa vụ chuyên môn.
- **Không đánh giá bằng chứng bị mất:** lợi ích giảm thời gian được ghi nhận nhưng rủi ro mới không được xem xét.
- **Coi waiver là PASS:** làm sai lệch kết quả kiểm thử và báo cáo chất lượng.
- **Không có ngày hết hạn:** ngoại lệ tạm thời trở thành vĩnh viễn.
- **Chấp nhận ngoại lệ cho yêu cầu bắt buộc không đúng thẩm quyền:** có thể vi phạm nghĩa vụ hoặc chính sách.
- **Không ghi ý kiến phản đối:** mất thông tin quan trọng cho lần xem xét sau.
- **Không kiểm tra việc triển khai sau phê duyệt:** tài liệu được duyệt nhưng hệ thống thực tế không theo quyết định.
- **Không review sau thay đổi khẩn cấp:** biện pháp tạm thời có thể tồn tại ngoài kiểm soát.
- **Không thông báo cho nhóm bị ảnh hưởng:** test tiếp tục chạy theo chiến lược cũ hoặc hiểu sai phạm vi.

## 14. Danh sách rà soát quản trị quyền phê duyệt

- [ ] Có danh mục loại quyết định và mức ảnh hưởng.
- [ ] Quyền phê duyệt được gắn với phạm vi và trách nhiệm cụ thể.
- [ ] Người đề xuất, reviewer, approver và implementer được phân biệt.
- [ ] Có người thay thế khi approver vắng mặt.
- [ ] Rủi ro bảo mật, quyền riêng tư, an toàn và tuân thủ có đường review riêng.
- [ ] Thay đổi chiến lược có phân tích tác động, kế hoạch triển khai và rollback.
- [ ] Waiver có bằng chứng, rủi ro còn lại, biện pháp giảm thiểu, owner và ngày hết hạn.
- [ ] Test FAIL, BLOCKED và NOT RUN giữ nguyên trạng thái.
- [ ] Quyết định được lưu tập trung và truy vết đến release/test run.
- [ ] Các nhóm bị ảnh hưởng được thông báo.
- [ ] Quyết định được đánh giá lại khi hết hạn hoặc bối cảnh thay đổi.
- [ ] Quy trình khẩn cấp có người chỉ huy và review sau sự kiện.
- [ ] Quyền phê duyệt được rà soát định kỳ.
- [ ] Ngoại lệ đã đóng có bằng chứng và hành động khắc phục được theo dõi.

## Kết luận

Quyền phê duyệt thay đổi chiến lược và chấp nhận ngoại lệ cần được xác định theo loại quyết định, phạm vi và mức rủi ro. Thay đổi chiến lược điều chỉnh cách kiểm thử; waiver ghi nhận việc chấp nhận một khoảng trống hoặc điều kiện chưa đạt trong phạm vi cụ thể; cả hai đều cần đánh giá tác động, người có thẩm quyền, điều kiện và thời hạn rõ ràng. Khi vai trò đề xuất, review, phê duyệt và thực hiện được phân định; kết quả test được giữ nguyên; quyết định được lưu vết và xem xét lại, tổ chức có thể xử lý thay đổi linh hoạt mà vẫn giữ được tính minh bạch và trách nhiệm đối với rủi ro chất lượng.
