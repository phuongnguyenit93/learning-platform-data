# Xây bộ smoke, hồi quy cốt lõi và hồi quy mở rộng

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kiểm thử hồi quy (regression testing) giúp xác nhận rằng một thay đổi mới không làm hỏng hành vi đã hoạt động trước đó. Khi sản phẩm phát triển, số lượng chức năng, luồng nghiệp vụ, tích hợp và cấu hình tăng lên. Chạy toàn bộ kiểm thử sau mọi thay đổi có thể tốn nhiều thời gian và tài nguyên; chỉ chạy một vài test gần với phần code vừa sửa lại có thể bỏ sót tác động lan truyền. Vì vậy, nhóm cần tổ chức bộ kiểm thử thành các lớp có mục tiêu và phạm vi khác nhau: **smoke**, **hồi quy cốt lõi** và **hồi quy mở rộng**.

Ba lớp này tạo thành một chiến lược phản hồi theo mức độ ưu tiên. Smoke kiểm tra nhanh xem bản build hoặc môi trường có đủ điều kiện để tiếp tục kiểm thử hay không. Hồi quy cốt lõi kiểm tra các hành trình và quy tắc có rủi ro hoặc giá trị nghiệp vụ cao. Hồi quy mở rộng bao phủ rộng hơn các chức năng, biến thể, tích hợp và thuộc tính chất lượng để tăng độ tin cậy trước những mốc phát hành quan trọng. Việc phân lớp giúp nhóm chọn đúng tập test theo thay đổi, rủi ro và thời gian phản hồi cần thiết.

## 1. Kiểm thử hồi quy và lý do cần phân tầng

Kiểm thử hồi quy là hoạt động chạy lại các kiểm tra đã có sau khi phần mềm thay đổi để phát hiện hành vi cũ bị ảnh hưởng ngoài dự kiến. Thay đổi có thể là sửa lỗi, bổ sung tính năng, tái cấu trúc, nâng cấp thư viện, thay đổi cấu hình, schema dữ liệu, hạ tầng hoặc dịch vụ phụ thuộc.

Hồi quy cần thiết vì phần mềm có nhiều quan hệ phụ thuộc. Một thay đổi trong tính giá có thể ảnh hưởng giỏ hàng, thanh toán, hóa đơn và báo cáo. Một thay đổi trong xác thực có thể ảnh hưởng đăng nhập, API, quyền quản trị và tác vụ nền. Lỗi có thể xuất hiện ở thành phần không nằm trong phạm vi code vừa sửa.

Nếu chỉ chạy một bộ test rất nhỏ, nhóm có thể bỏ sót lỗi lan truyền. Nếu luôn chạy toàn bộ bộ test lớn, thời gian phản hồi tăng, pipeline chậm và nhóm có thể trì hoãn việc nhận biết lỗi. Phân tầng giúp cân bằng:

- **Tốc độ phản hồi:** phát hiện lỗi nghiêm trọng sớm sau build hoặc deploy.
- **Mức độ bao phủ:** kiểm tra hành vi quan trọng trước, sau đó mở rộng đến các biến thể và rủi ro ít thường xuyên hơn.
- **Chi phí thực thi:** dành tài nguyên dài hơn cho các mốc cần bằng chứng sâu.
- **Khả năng chẩn đoán:** mỗi lớp có mục tiêu rõ, giúp hiểu loại rủi ro nào đã được kiểm tra.
- **Quản trị phát hành:** có thể đặt cổng chất lượng khác nhau cho commit, pull request, nightly build, release candidate và production rollout.

Phân tầng không phải là chia test theo số lượng hoặc theo tên thư mục. Mỗi test cần được xếp vào lớp dựa trên mục đích, mức độ quan trọng, thời gian chạy, độ ổn định và điều kiện cần thiết.

## 2. Phân biệt smoke, hồi quy cốt lõi và hồi quy mở rộng

### Smoke test — xác nhận bản build đủ điều kiện

Smoke test là tập kiểm tra nhỏ, chạy nhanh để xác nhận những chức năng hoặc thành phần thiết yếu không bị hỏng nghiêm trọng. Mục tiêu là phát hiện sớm các lỗi khiến việc kiểm thử sâu hơn không có ý nghĩa, ví dụ ứng dụng không khởi động, không đăng nhập được, API trọng yếu không phản hồi hoặc kết nối dữ liệu chính bị lỗi.

Smoke thường chạy sau build, sau deploy lên môi trường test/staging hoặc sau khi thay đổi hạ tầng quan trọng. Kết quả smoke trả lời câu hỏi: “Bản này có đủ khỏe để tiếp tục kiểm thử không?”

Đặc điểm thường gặp:

- Phạm vi nhỏ, tập trung vào luồng khởi động và chức năng sống còn.
- Thời gian chạy ngắn và kết quả dễ diễn giải.
- Ưu tiên tính ổn định, ít phụ thuộc và khả năng phát hiện lỗi chặn.
- Có thể chạy tự động trong CI/CD và sau deploy.
- Khi smoke thất bại nghiêm trọng, dừng các suite dài hơn để tiết kiệm tài nguyên và tránh báo lỗi dây chuyền.

Smoke không chứng minh toàn bộ chức năng đúng. Một luồng đăng nhập thành công không chứng minh phân quyền mọi vai trò, xử lý dữ liệu biên hoặc tích hợp thanh toán đều hoạt động.

### Hồi quy cốt lõi (core regression)

Hồi quy cốt lõi là tập kiểm tra các hành vi, luồng nghiệp vụ và hợp đồng có giá trị cao hoặc hậu quả lớn nếu bị hỏng. Nó thường bao gồm các đường đi chính của người dùng, quy tắc nghiệp vụ quan trọng, quyền truy cập, tính toàn vẹn dữ liệu và những tích hợp thiết yếu.

Core regression trả lời câu hỏi: “Các năng lực quan trọng nhất của sản phẩm còn hoạt động đúng sau thay đổi không?”

Đặc điểm thường gặp:

- Bao phủ hành trình nghiệp vụ chính từ đầu đến cuối ở mức cần thiết.
- Ưu tiên chức năng có tần suất sử dụng cao hoặc tác động lớn.
- Bao gồm các test hồi quy cho lỗi nghiêm trọng đã từng xảy ra.
- Có thể chạy trên mỗi pull request hoặc mỗi build tích hợp, tùy thời gian.
- Có thể lâu hơn smoke nhưng vẫn phải đủ nhanh để cung cấp phản hồi trong chu kỳ phát triển.

Core regression không nhất thiết chỉ có end-to-end test. Một test đơn vị, component, API, contract hoặc integration có thể thuộc core nếu nó bảo vệ rủi ro cốt lõi và cho phản hồi đáng tin cậy. Thường nên đặt kiểm tra ở mức thấp nhất có thể nhưng vẫn xác nhận đúng ranh giới và hành vi cần bảo vệ.

### Hồi quy mở rộng (extended regression)

Hồi quy mở rộng là tập kiểm tra có phạm vi rộng hơn, bao gồm biến thể, trường hợp biên, vai trò ít phổ biến, cấu hình, trình duyệt/thiết bị, tích hợp bổ sung và những rủi ro không cần kiểm tra trong mọi lần build.

Extended regression trả lời câu hỏi: “Ngoài các hành vi cốt lõi, những phần nào khác có thể bị ảnh hưởng và có cần thêm bằng chứng trước phát hành không?”

Đặc điểm thường gặp:

- Bao phủ rộng chức năng, tổ hợp dữ liệu, trạng thái và cấu hình.
- Có thể gồm kiểm thử giao diện trên nhiều browser, kiểm thử tương thích, migration, báo cáo, xử lý ngoại lệ và tích hợp ít dùng.
- Có thể chạy theo lịch nightly, trước release candidate, trước mốc bàn giao hoặc khi thay đổi có phạm vi ảnh hưởng lớn.
- Có thể cần môi trường chuyên biệt, dữ liệu lớn hoặc dịch vụ sandbox.
- Thời gian thực thi dài hơn; cần quản lý song song, dữ liệu và độ ổn định.

Hồi quy mở rộng không phải “mọi test còn lại” được gom tùy tiện. Tập này vẫn cần có mục tiêu, chủ sở hữu, tiêu chí chọn và bằng chứng cho thấy nó bao phủ các rủi ro đã xác định.

### Bảng so sánh tổng hợp

| Khía cạnh | Smoke | Core regression | Extended regression |
|---|---|---|---|
| Câu hỏi chính | Bản build/môi trường có đủ điều kiện để tiếp tục? | Các hành vi quan trọng nhất còn đúng? | Các biến thể và rủi ro rộng hơn có còn được kiểm soát? |
| Phạm vi | Rất nhỏ, luồng sống còn | Luồng và quy tắc có giá trị/rủi ro cao | Rộng, nhiều biến thể và tích hợp |
| Thời gian | Rất ngắn | Ngắn đến trung bình | Trung bình đến dài |
| Thời điểm | Sau build/deploy, trước suite khác | PR/build tích hợp, trước deploy hoặc theo nhịp chính | Nightly, release candidate, thay đổi lớn |
| Kết quả thất bại | Thường chặn kiểm thử tiếp theo hoặc rollout | Chặn merge/release theo mức độ | Tạo quyết định điều tra, sửa lỗi hoặc đánh giá rủi ro trước mốc phát hành |
| Ví dụ | App khởi động, health, đăng nhập cơ bản, API trọng yếu | Tạo đơn, tính tiền, thanh toán, phân quyền quan trọng | Browser matrix, dữ liệu biên, báo cáo, migration, tích hợp ít dùng |

Các thời lượng và thời điểm trong bảng là định hướng, không phải chuẩn cứng. Một sản phẩm có thể có smoke vài phút, core regression vài chục phút và extended regression vài giờ; sản phẩm khác có thể có quy mô khác. Hãy đo thời gian thực tế và thiết kế theo nhu cầu.

## 3. Nguyên tắc phân loại test vào từng lớp

Một test có thể có giá trị ở nhiều giai đoạn. Để tránh trùng lặp hoặc bỏ sót, nhóm nên thống nhất tiêu chí phân loại.

### Mức độ quan trọng của hành vi

Ưu tiên smoke hoặc core cho hành vi mà nếu hỏng sẽ làm hệ thống không thể sử dụng, gây mất dữ liệu, sai giao dịch, vi phạm quyền hoặc ảnh hưởng lớn đến khách hàng. Các biến thể ít thường xuyên hơn có thể thuộc extended, trừ khi hậu quả của chúng đủ nghiêm trọng để cần kiểm tra sớm.

### Khả năng phát hiện lỗi chặn

Smoke nên phát hiện lỗi nghiêm trọng với ít bước và ít phụ thuộc. Một test dài, cần nhiều dịch vụ bên ngoài và dữ liệu phức tạp thường không phù hợp làm smoke, dù nó kiểm tra chức năng quan trọng. Có thể tách một kiểm tra đơn giản cho smoke và giữ kịch bản đầy đủ ở core.

### Thời gian và độ ổn định

Test chạy nhanh, đáng tin và dễ chẩn đoán phù hợp với các cổng phản hồi thường xuyên. Test chậm, cần môi trường đặc biệt hoặc dễ biến động có thể được chạy ở extended, sau khi đã đầu tư làm cho nó ổn định. Không nên đẩy một test quan trọng xuống extended chỉ vì nó đang flaky; cần xử lý độ không ổn định hoặc thiết kế phép kiểm tra phù hợp hơn.

### Mức độ thay đổi và quan hệ phụ thuộc

Test gần với code vừa thay đổi nên được chạy sớm, nhưng không chỉ giới hạn ở đó. Phân tích tác động cần xác định các module, API, dữ liệu và luồng phụ thuộc có thể bị ảnh hưởng. Một thay đổi ở thư viện xác thực có thể yêu cầu core regression cho đăng nhập và phân quyền, cùng extended regression cho các tích hợp SSO hoặc browser ít dùng.

### Lịch sử lỗi và rủi ro

Test tái hiện lỗi nghiêm trọng từng xảy ra nên được đưa vào suite phù hợp để ngăn tái diễn. Nếu lỗi dễ phát hiện, thời gian ngắn và tác động cao, ưu tiên core. Nếu cần dữ liệu hoặc môi trường chuyên biệt, có thể ở extended nhưng phải có lịch và cổng kiểm tra rõ ràng.

## 4. Xây dựng bộ smoke test

Smoke test cần nhỏ, có khả năng xác nhận ứng dụng và các luồng thiết yếu hoạt động ở mức cơ bản.

### Chọn các kiểm tra thiết yếu

Tùy hệ thống, smoke có thể gồm:

- Artifact đúng phiên bản và ứng dụng khởi động thành công.
- Health/readiness của thành phần bắt buộc ở trạng thái sẵn sàng.
- Ứng dụng kết nối được database hoặc phụ thuộc thiết yếu.
- Người dùng kiểm tra có thể đăng nhập và truy cập chức năng chính.
- API trọng yếu trả phản hồi hợp lệ với dữ liệu kiểm tra.
- Một luồng nghiệp vụ ngắn hoàn tất mà không tạo tác dụng phụ nguy hiểm.
- Giao diện hoặc endpoint chính có thể truy cập sau deploy.

Không cần đưa mọi chức năng vào smoke. Chọn một số kiểm tra có khả năng phát hiện lỗi chặn cao và đại diện cho khả năng sử dụng cơ bản của bản build.

### Giữ smoke ngắn và đáng tin

Để smoke có giá trị:

- Dùng dữ liệu ổn định, dễ chuẩn bị và dọn dẹp.
- Tránh phụ thuộc vào dịch vụ bên ngoài không cần thiết; nếu cần, kiểm tra kết nối tối thiểu hoặc dùng sandbox ổn định.
- Hạn chế thao tác tạo dữ liệu lớn hoặc quy trình nhiều bước.
- Không dùng sleep cố định nếu có thể chờ readiness hoặc điều kiện rõ ràng.
- Đảm bảo lỗi có thông báo và log đủ để xác định nguyên nhân.
- Có timeout tổng thể và timeout từng bước để suite không treo.

Smoke test quá đơn giản có thể pass trong khi chức năng nghiệp vụ vẫn lỗi; smoke quá rộng lại chậm và dễ thất bại vì phụ thuộc. Cần cân bằng bằng cách xác định rõ điều kiện “đủ khỏe” cho bản build.

### Smoke sau build và smoke sau deploy

Smoke sau build có thể kiểm tra artifact, cấu hình cơ bản, test khởi động và các thành phần đóng gói. Smoke sau deploy kiểm tra ứng dụng trong môi trường đã triển khai, gồm readiness, kết nối phụ thuộc và luồng đại diện.

Hai lần smoke có thể khác nhau vì mục tiêu khác nhau. Smoke sau build không chứng minh cấu hình staging đúng; smoke sau deploy không thay thế việc kiểm tra nguồn gốc artifact và build pipeline.

### Ví dụ smoke cho ứng dụng đặt hàng

1. Xác nhận version endpoint trả đúng release identifier.
2. Health/readiness của Order Service và Payment Adapter đạt.
3. Tài khoản kiểm tra đăng nhập được.
4. API danh sách sản phẩm trả ít nhất một kết quả hợp lệ.
5. Tạo một đơn thử ở trạng thái phù hợp và xác nhận mã đơn được sinh.

Nếu smoke thất bại ở readiness, không nên chạy hàng trăm test giao diện phía sau vì phần lớn sẽ thất bại do cùng một nguyên nhân môi trường. Nếu tạo đơn thử có tác dụng phụ, cần dùng sandbox hoặc dữ liệu có thể nhận diện và dọn dẹp.

## 5. Xây dựng bộ hồi quy cốt lõi

Core regression bảo vệ các hành vi có giá trị cao nhất. Nhóm cần chọn theo rủi ro, hành trình người dùng và các hợp đồng quan trọng.

### Bao phủ hành trình nghiệp vụ chính

Xác định các hành trình mà người dùng hoặc hệ thống phải hoàn thành để sản phẩm tạo ra giá trị. Ví dụ:

- Đăng nhập, xác thực và truy cập đúng chức năng theo vai trò.
- Tạo, xem, cập nhật và hoàn tất một giao dịch quan trọng.
- Tính toán giá trị, phí, thuế hoặc hạn mức chính xác.
- Thanh toán, hoàn tiền hoặc ghi nhận trạng thái giao dịch.
- Lưu và truy xuất dữ liệu quan trọng mà không mất hoặc nhân đôi.
- Đồng bộ thông tin với hệ thống thiết yếu.

Một hành trình có thể được chia thành nhiều test ở các mức khác nhau. Không nhất thiết mọi quy tắc đều phải kiểm tra qua UI end-to-end; unit/API/integration test thường cho phản hồi nhanh và chẩn đoán tốt hơn.

### Bao phủ quy tắc và ràng buộc cốt lõi

Chọn các quy tắc có hậu quả lớn nếu sai, như:

- Tính tổng tiền, giảm giá, thuế và đơn vị tiền tệ.
- Kiểm soát quyền và quyền sở hữu dữ liệu.
- Không xử lý trùng giao dịch hoặc message.
- Trạng thái chỉ chuyển theo quy tắc hợp lệ.
- Dữ liệu được lưu nhất quán sau thao tác quan trọng.
- Hạn mức, ngưỡng và điều kiện chấp nhận không bị phá vỡ.

Những quy tắc này thường có thể được kiểm tra ở unit hoặc component level, rồi bổ sung một số luồng tích hợp để xác nhận ranh giới.

### Đưa lỗi nghiêm trọng đã sửa vào core

Khi một lỗi production hoặc lỗi phát hành được sửa, cần đánh giá cách ngăn tái diễn. Nếu lỗi có thể tái hiện bằng test nhanh, ổn định, hãy đưa test vào core hoặc tầng thấp phù hợp để chạy thường xuyên. Nếu lỗi phụ thuộc môi trường hoặc tình huống hiếm, đưa vào extended nhưng bảo đảm có lịch chạy và chủ sở hữu.

Không nên thêm một test trùng lặp chỉ vì lỗi đã xảy ra. Hãy xác định test nào đang thiếu, mức nào phát hiện lỗi sớm nhất và liệu một test hiện có có thể được mở rộng để bảo vệ cùng quy tắc hay không.

### Giữ core đủ nhỏ để phản hồi thường xuyên

Core có thể phát triển theo thời gian. Cần review định kỳ để loại bỏ test trùng lặp, chuyển test xuống mức nhanh hơn, tách test chậm hoặc cải thiện dữ liệu. Không nên để core trở thành một bộ hồi quy mở rộng thu nhỏ mà mất khả năng phản hồi nhanh.

## 6. Xây dựng bộ hồi quy mở rộng

Extended regression tăng độ rộng và chiều sâu của bằng chứng trước những mốc quan trọng hoặc khi thay đổi có phạm vi ảnh hưởng lớn.

### Bao phủ biến thể và trường hợp biên

Ví dụ:

- Giá trị tối thiểu/tối đa, dữ liệu rỗng, dữ liệu rất lớn hoặc định dạng bất thường.
- Nhiều trạng thái nghiệp vụ, chuyển trạng thái không hợp lệ và thao tác lặp.
- Người dùng thuộc vai trò ít phổ biến hoặc cấu hình đặc biệt.
- Ngôn ngữ, locale, timezone, tiền tệ và định dạng khác nhau.
- Tương thích browser, hệ điều hành, thiết bị và độ phân giải.
- Tải cao, cạnh tranh tài nguyên, timeout, retry và phục hồi.
- Migration, nâng cấp và tương thích giữa phiên bản cũ/mới.

### Bao phủ chức năng và tích hợp ít thường xuyên

Các chức năng báo cáo, xuất dữ liệu, cấu hình quản trị, tác vụ theo lịch, tích hợp đối tác hoặc quy trình xử lý ngoại lệ có thể không chạy trong mọi lần build nhưng vẫn cần được kiểm tra định kỳ hoặc trước phát hành.

### Bao phủ thuộc tính phi chức năng

Extended có thể chứa kiểm tra hiệu năng, bảo mật, khả năng phục hồi, tương thích, accessibility hoặc khả năng vận hành. Những test này có thể cần môi trường riêng, dữ liệu lớn hoặc chuyên gia. Nếu rủi ro cao, không nên mặc định chúng chỉ chạy trong extended; một số kiểm tra bảo mật hoặc hiệu năng quan trọng có thể cần cổng riêng trước phát hành.

### Chọn lịch chạy phù hợp

- Nightly: chạy các test ổn định, cần thời gian dài hơn hoặc nhiều dữ liệu.
- Theo lịch tuần: kiểm tra ma trận browser/OS, tích hợp đối tác hoặc các kịch bản ít thay đổi.
- Release candidate: chạy bộ mở rộng đại diện trước khi phát hành.
- Khi thay đổi lớn: kích hoạt suite liên quan theo phân tích tác động.
- Trước migration hoặc nâng cấp: chạy bộ kiểm tra tương thích và khôi phục chuyên biệt.

Lịch chạy cần được xác định theo rủi ro và thời hạn phản hồi. Một test quan trọng nhưng chỉ chạy mỗi tháng có thể không đủ nếu sản phẩm phát hành hàng ngày.

## 7. Ánh xạ test vào các lớp và tránh trùng lặp

Phân lớp smoke/core/extended không thay thế việc phân loại theo test level hoặc test type. Một test đơn vị có thể thuộc core; một test UI có thể là smoke; một test hiệu năng có thể là extended hoặc cổng bắt buộc trước release.

### Phân loại theo mục tiêu và cách chạy

Khi quyết định test thuộc lớp nào, xem xét:

1. **Rủi ro được bảo vệ:** test phát hiện hậu quả nào và mức độ nghiêm trọng ra sao?
2. **Giá trị phát hiện sớm:** test có thể phát hiện lỗi ngay sau thay đổi không?
3. **Thời gian và độ ổn định:** test chạy bao lâu, có flaky hay phụ thuộc bên ngoài không?
4. **Phạm vi ảnh hưởng:** test xác nhận thành phần, API, tích hợp hay hành trình xuyên hệ thống?
5. **Tần suất cần thiết:** rủi ro có cần kiểm tra mỗi commit, mỗi ngày hay trước release?
6. **Khả năng chẩn đoán:** khi fail, nhóm có nhanh chóng xác định nguyên nhân không?

### Tránh kiểm tra cùng một quy tắc ở quá nhiều tầng

Một quy tắc tính giảm giá có thể được kiểm tra chi tiết bằng unit test, được xác nhận qua API test và xuất hiện trong một số end-to-end test đại diện. Không cần nhân bản hàng chục luồng UI chỉ để kiểm tra mọi tổ hợp công thức. Hãy đặt kiểm tra chi tiết ở tầng thấp, giữ số lượng luồng đầu cuối vừa đủ để xác nhận các phần phối hợp.

### Duy trì liên kết yêu cầu — rủi ro — test

Mỗi test nên có thể truy về yêu cầu, rủi ro, lỗi lịch sử hoặc mục tiêu chất lượng mà nó bảo vệ. Metadata có thể gồm:

- Test ID và mô tả hành vi.
- Requirement/risk ID hoặc nhóm tính năng.
- Test level và test type.
- Suite membership: smoke, core, extended hoặc nhiều lớp nếu có lý do.
- Thời gian chạy, môi trường và dữ liệu cần thiết.
- Chủ sở hữu và tần suất thực thi.
- Điều kiện skip, quarantine hoặc giới hạn đã biết.

Việc gắn một test vào nhiều suite cần có lý do rõ. Ví dụ, một test API quan trọng có thể chạy trong core mỗi pull request và được chạy lại trong extended với nhiều bộ dữ liệu hoặc phiên bản phụ thuộc.

## 8. Điều phối các suite trong CI/CD

Phân tầng chỉ có giá trị khi được tích hợp vào quy trình phát triển và phát hành.

### Một luồng pipeline tham khảo

```text
Commit / Pull Request
        |
        v
 Build + static checks + unit tests
        |
        v
 Smoke (artifact / test environment)
        |
        v
 Core regression
        |
        v
 Deploy to staging / release candidate
        |
        v
 Extended regression + non-functional checks
        |
        v
 Release decision
        |
        v
 Production rollout + post-deployment smoke
```

Đây là một luồng mẫu. Unit test có thể chạy song song với build checks; một số core API test có thể chạy trước smoke; extended có thể chạy nightly hoặc song song trên nhiều worker. Điều quan trọng là các cổng chặn và điều kiện tiếp tục được xác định rõ.

### Pull request và commit

Chạy các kiểm tra nhanh để người phát triển nhận phản hồi trước khi merge. Tùy dự án, có thể gồm static checks, unit tests, smoke ở mức component và một phần core regression. Nếu thời gian core quá dài, phân tích rủi ro và chạy các test liên quan thay đổi trước, nhưng vẫn cần một cổng hồi quy cốt lõi định kỳ.

### Build tích hợp và môi trường staging

Sau khi merge, chạy smoke để xác nhận artifact và môi trường. Khi smoke đạt, chạy core regression với dữ liệu và phụ thuộc phù hợp. Trước release candidate, chạy extended theo phạm vi thay đổi và lịch phát hành.

### Nightly và lịch định kỳ

Nightly phù hợp cho các suite dài hơn, ma trận cấu hình và test cần dữ liệu lớn. Cần theo dõi kết quả, phân loại lỗi môi trường và đảm bảo có người xem báo cáo vào ngày làm việc tiếp theo. Một nightly suite thất bại liên tục mà không ai xử lý sẽ mất giá trị như một tín hiệu chất lượng.

### Sau triển khai production

Chạy post-deployment smoke an toàn để xác nhận version, health, readiness và một số luồng đại diện. Tiếp tục theo dõi metric và cảnh báo. Không chạy toàn bộ hồi quy mở rộng trên production nếu test có thể tạo giao dịch, thay đổi dữ liệu hoặc gây tải ngoài dự kiến.

## 9. Cổng chất lượng và quyết định khi test thất bại

Mỗi lớp cần có quy tắc xử lý kết quả rõ ràng.

### Smoke thất bại

Smoke thường là cổng chặn. Nếu ứng dụng không khởi động, database không sẵn sàng hoặc luồng thiết yếu không hoạt động, dừng suite phía sau và xử lý nguyên nhân. Không nên bỏ qua smoke chỉ để pipeline có màu xanh.

### Core regression thất bại

Core fail cần được đánh giá ngay vì có thể ảnh hưởng hành vi quan trọng. Xác định đây là defect, test lỗi, môi trường lỗi hay dữ liệu không hợp lệ. Nếu là lỗi sản phẩm, chặn merge/release theo chính sách. Nếu test flaky, cần có quy trình điều tra và không tự động bỏ qua mãi mãi.

### Extended regression thất bại

Extended fail cần được phân loại theo mức độ và phạm vi. Một lỗi bảo mật hoặc mất dữ liệu có thể là điều kiện chặn dù test nằm trong extended. Một lỗi giao diện ít ảnh hưởng ở browser ngoài phạm vi hỗ trợ có thể được xử lý theo chính sách khác. Vị trí trong suite không tự quyết định mức nghiêm trọng.

### Quản lý test flaky và quarantine

Test flaky cho kết quả không ổn định khi không có thay đổi sản phẩm tương ứng. Nguyên nhân có thể là timing, dữ liệu dùng chung, phụ thuộc mạng, thứ tự test, môi trường hoặc assertion không phù hợp.

Khi cần quarantine một test:

- Ghi rõ test ID, lý do, người phụ trách và ngày xem xét lại.
- Đánh giá rủi ro mà test đó đang bảo vệ.
- Có test thay thế hoặc biện pháp kiểm tra tạm thời nếu rủi ro cao.
- Không loại test khỏi mọi suite mà không có quyết định.
- Theo dõi đến khi sửa và đưa lại vào suite.

Quarantine không nên trở thành nơi lưu các test khó chịu vô thời hạn. Tỷ lệ test bị quarantine là một tín hiệu sức khỏe của bộ kiểm thử.

## 10. Dữ liệu, môi trường và tính độc lập giữa các suite

Smoke, core và extended có thể chạy trên cùng một môi trường hoặc môi trường riêng. Dù lựa chọn nào, cần bảo đảm suite không gây nhiễu cho nhau.

### Dữ liệu có thể tái lập

- Tạo dữ liệu theo fixture hoặc API chuẩn bị có version.
- Dùng định danh duy nhất để tránh xung đột khi chạy song song.
- Xác định trạng thái đầu vào và kết quả cần dọn dẹp.
- Không phụ thuộc vào dữ liệu do một test khác tạo nếu không có quan hệ được quản lý.
- Dùng dữ liệu tổng hợp hoặc đã được xử lý phù hợp; tránh dữ liệu nhạy cảm không cần thiết.

### Cô lập môi trường

Test chạy song song có thể cạnh tranh database, tài khoản, hàng đợi hoặc file. Có thể dùng namespace, tenant, schema hoặc container riêng. Với test cần trạng thái toàn cục, đánh dấu và tuần tự hóa nếu không thể cô lập an toàn.

### Kiểm soát phụ thuộc bên ngoài

Smoke và core nên giảm phụ thuộc vào dịch vụ không ổn định nếu mục tiêu không phải kiểm tra chính dịch vụ đó. Dùng fake hoặc simulator cho test logic; dùng contract/integration test định kỳ để xác nhận giao tiếp thật. Extended có thể chứa thêm kiểm tra sandbox hoặc môi trường tích hợp đối tác.

### Tương thích môi trường

Ghi nhận phiên bản ứng dụng, runtime, database, browser, service và cấu hình. Nếu extended chạy trên ma trận phiên bản, cần biết test nào chạy ở tổ hợp nào và tổ hợp nào chưa được bao phủ.

## 11. Chọn test theo phạm vi thay đổi

Không phải thay đổi nào cũng cần cùng một tập test. Phân tích tác động giúp bổ sung các test liên quan mà không làm mất lớp bảo vệ cơ bản.

### Thay đổi ở giao diện

Chạy smoke giao diện cho trang và luồng thiết yếu; core regression cho hành trình người dùng chính; extended cho browser, độ phân giải, accessibility và các trạng thái ít phổ biến có liên quan.

### Thay đổi ở logic tính toán

Chạy unit tests cho giá trị biên và quy tắc; core cho API hoặc luồng sử dụng kết quả; extended cho dữ liệu lớn, tiền tệ, làm tròn, locale và tích hợp báo cáo nếu có ảnh hưởng.

### Thay đổi ở xác thực/phân quyền

Smoke xác nhận đăng nhập cơ bản; core kiểm tra vai trò quan trọng và truy cập dữ liệu; extended kiểm tra token hết hạn, SSO, phiên đồng thời, quyền ít phổ biến và các tổ hợp endpoint.

### Thay đổi schema hoặc database

Chạy migration test, core cho đọc/ghi và luồng nghiệp vụ trọng yếu; extended cho dữ liệu lớn, tương thích phiên bản cũ/mới, rollback/restore và đối soát.

### Nâng cấp thư viện hoặc runtime

Chạy smoke để xác nhận khởi động, core cho luồng chính, extended cho compatibility matrix, security scan và các chức năng phụ thuộc vào hành vi thư viện.

### Sửa lỗi production

Tạo test tái hiện lỗi ở tầng phù hợp. Nếu lỗi nghiêm trọng và test nhanh, đưa vào core. Nếu cần môi trường chuyên biệt, đưa vào extended với lịch chạy rõ ràng. Chạy thêm các test lân cận để kiểm tra tác động của thay đổi sửa lỗi.

## 12. Ví dụ xuyên suốt: phân tầng hồi quy cho thương mại điện tử

Giả sử một nền tảng bán hàng có các luồng đăng nhập, tìm kiếm, giỏ hàng, đặt hàng, thanh toán, kho, vận chuyển và thông báo. Nhóm chuẩn bị phát hành thay đổi về mã giảm giá và tích hợp thanh toán.

### Bộ smoke

| Test | Mục tiêu |
|---|---|
| Version/health check | Xác nhận đúng build và service sẵn sàng |
| Login cơ bản | Xác nhận người dùng kiểm tra có thể đăng nhập |
| Product API | Xác nhận danh sách sản phẩm truy cập được |
| Cart API | Xác nhận có thể tạo giỏ hàng thử |
| Checkout cơ bản | Xác nhận một luồng đơn giản tạo được đơn thử trong sandbox |

### Bộ core regression

| Test | Rủi ro được bảo vệ |
|---|---|
| Tính tổng tiền với mã giảm giá hợp lệ | Sai giá trị thanh toán hoặc hóa đơn |
| Mã giảm giá hết hạn/không đủ điều kiện | Áp dụng ưu đãi sai |
| Tạo đơn và giữ tồn kho | Đơn không nhất quán với tồn kho |
| Thanh toán thành công/thất bại | Sai trạng thái giao dịch |
| Retry sau timeout với cùng idempotency key | Tạo giao dịch hoặc đơn trùng |
| Phân quyền xem và sửa đơn | Lộ hoặc sửa dữ liệu trái phép |
| Ghi nhận đơn và phát event | Mất hoặc phát trùng sự kiện quan trọng |

### Bộ extended regression

| Nhóm | Ví dụ kiểm tra |
|---|---|
| Giá trị biên | Mã giảm giá đúng ngưỡng, thấp hơn ngưỡng, đơn giá bằng 0, số lượng tối đa |
| Trạng thái | Hủy đơn trong khi thanh toán đang chờ, webhook đến trễ hoặc sai thứ tự |
| Tương thích | Browser, thiết bị và phiên bản ứng dụng di động được hỗ trợ |
| Tích hợp | WMS, vận chuyển, thông báo và đối soát thanh toán |
| Dữ liệu | Migration, báo cáo doanh thu, dữ liệu lịch sử lớn |
| Phi chức năng | Tải cao ở checkout, timeout phụ thuộc và kiểm tra bảo mật phù hợp |

### Lựa chọn theo thay đổi cụ thể

Vì thay đổi liên quan mã giảm giá và thanh toán, nhóm chạy smoke sau build/deploy, core regression cho tính giá, checkout, thanh toán, retry và trạng thái đơn. Extended bổ sung tổ hợp mã giảm giá, locale/tiền tệ, webhook sai thứ tự, đối soát và các browser được hỗ trợ. Nếu thay đổi không chạm đến báo cáo hoặc vận chuyển, nhóm vẫn cân nhắc chạy extended định kỳ trước release nhưng có thể không cần đưa mọi test đó vào cổng PR.

## 13. Đo lường sức khỏe của các suite

Không chỉ đo số test pass. Cần biết suite có nhanh, ổn định, có khả năng phát hiện lỗi và tạo thông tin hữu ích hay không.

### Chỉ số về tốc độ

- Thời gian trung vị và phân vị cao của smoke, core và extended.
- Thời gian chờ trong pipeline và thời gian thực thi thực tế.
- Tỷ lệ test chạy song song và mức sử dụng tài nguyên.
- Thời gian từ commit đến phản hồi đầu tiên có ý nghĩa.

### Chỉ số về độ ổn định

- Tỷ lệ flaky và số lần retry do test không ổn định.
- Tỷ lệ test bị quarantine và tuổi của test trong quarantine.
- Tỷ lệ lỗi môi trường hoặc phụ thuộc bên ngoài.
- Tỷ lệ test cần can thiệp thủ công hoặc dữ liệu sửa tay.

### Chỉ số về giá trị phát hiện

- Số lỗi được phát hiện theo suite và mức độ nghiêm trọng.
- Tỷ lệ lỗi production có test hồi quy ngăn tái diễn.
- Thời gian phát hiện lỗi sau thay đổi.
- Tỷ lệ lỗi được phát hiện trước khi merge, trước release candidate hoặc sau production.
- Các khu vực rủi ro quan trọng chưa có test hoặc chỉ có test ở tầng muộn.

Không nên đánh giá hiệu quả suite chỉ bằng số lỗi nó phát hiện. Một suite có ít defect có thể là dấu hiệu sản phẩm ổn định, hoặc test yếu và không tìm được lỗi. Cần xem lịch sử lỗi, thay đổi, mức rủi ro, chất lượng test và kết quả production cùng nhau.

### Review suite định kỳ

Mỗi chu kỳ phát hành hoặc theo lịch, nhóm nên xem:

- Test nào không còn phù hợp vì chức năng đã bị loại bỏ?
- Test nào trùng lặp và có thể hợp nhất?
- Test nào quá chậm so với giá trị phát hiện?
- Test nào thường flaky và cần sửa nguyên nhân?
- Rủi ro mới nào chưa được đưa vào suite?
- Test nào cần chuyển giữa smoke, core và extended?
- Có suite nào không có người chịu trách nhiệm hoặc không ai xem kết quả?

Phân tầng cần được cập nhật theo sản phẩm. Một test từng thuộc extended có thể trở thành core khi chức năng trở nên thiết yếu hoặc có lỗi nghiêm trọng; một test có thể được chuyển xuống tầng thấp hơn khi logic được tách ra và có cách kiểm tra nhanh hơn.

## 14. Những sai lầm thường gặp

**Coi smoke là bộ hồi quy rút gọn tùy ý.** Smoke cần xác nhận điều kiện thiết yếu để tiếp tục, không phải chọn ngẫu nhiên vài test. Xác định tiêu chí “đủ khỏe” và giữ phạm vi ngắn.

**Đưa mọi test quan trọng vào smoke.** Nếu smoke quá dài và phụ thuộc nhiều dịch vụ, nó mất khả năng phản hồi nhanh. Tách kiểm tra tối thiểu vào smoke, phần hành vi sâu vào core.

**Chỉ chạy core sau khi phát hành.** Core cần cung cấp phản hồi trước các quyết định merge hoặc release quan trọng. Chọn lịch phù hợp với tốc độ thay đổi và rủi ro.

**Để extended trở thành nơi chứa test không được quản lý.** Mỗi test cần có mục tiêu, chủ sở hữu, lịch chạy và tiêu chí kết quả. Extended fail vẫn có thể là lỗi nghiêm trọng cần chặn phát hành.

**Phân lớp theo test level một cách máy móc.** Không phải unit luôn là core hay UI luôn là extended. Xếp theo rủi ro, giá trị phản hồi và phạm vi cần xác nhận.

**Chỉ chạy test gần với code thay đổi.** Tác động có thể lan qua API, dữ liệu và luồng khác. Phân tích phụ thuộc và duy trì một lớp core ổn định.

**Nhân bản cùng một kịch bản ở nhiều suite.** Trùng lặp làm tăng chi phí và tạo nhiều kết quả khó hiểu. Đặt test ở tầng phù hợp, chỉ chạy lại ở suite khác khi có mục tiêu hoặc điều kiện khác.

**Bỏ qua test flaky.** Retry đến khi pass hoặc quarantine vô thời hạn làm giảm niềm tin vào pipeline. Ghi nhận nguyên nhân, người phụ trách và hạn xử lý; đánh giá rủi ro test bị bỏ.

**Không kiểm soát dữ liệu giữa các suite.** Smoke tạo dữ liệu khiến core thất bại hoặc test song song sửa cùng bản ghi. Dùng fixture, namespace và dọn dẹp độc lập.

**Chỉ dùng pass rate làm thước đo.** Pass rate cao có thể do test không đủ nhạy. Kết hợp tốc độ, độ ổn định, lịch sử lỗi, rủi ro và lỗi production.

## 15. Checklist xây dựng và duy trì các bộ hồi quy

### Thiết kế phân tầng

- [ ] Đã xác định mục tiêu riêng của smoke, core và extended.
- [ ] Mỗi test được xếp lớp theo rủi ro, giá trị phát hiện, thời gian và độ ổn định.
- [ ] Các luồng nghiệp vụ và quy tắc quan trọng có test bảo vệ.
- [ ] Lỗi nghiêm trọng đã sửa được đánh giá để bổ sung hồi quy.
- [ ] Test được liên kết với yêu cầu, rủi ro hoặc lịch sử lỗi.
- [ ] Các test trùng lặp và giới hạn bao phủ được nhận diện.

### Smoke

- [ ] Xác nhận đúng artifact/build và ứng dụng sẵn sàng.
- [ ] Bao phủ một số chức năng sống còn và luồng đại diện.
- [ ] Chạy nhanh, ổn định, có timeout và thông báo lỗi rõ.
- [ ] Dữ liệu an toàn, dễ tạo và dọn dẹp.
- [ ] Có quy tắc dừng suite sau lỗi chặn.

### Core regression

- [ ] Bao phủ hành trình và quy tắc có giá trị/rủi ro cao.
- [ ] Có kiểm tra quyền, tính toàn vẹn dữ liệu và tích hợp thiết yếu.
- [ ] Test đặt ở mức phù hợp để phản hồi nhanh và dễ chẩn đoán.
- [ ] Được chạy ở các cổng phát triển/phát hành đã xác định.
- [ ] Có chủ sở hữu và tiêu chí xử lý khi thất bại.

### Extended regression

- [ ] Bao phủ biến thể, giá trị biên, trạng thái và cấu hình bổ sung.
- [ ] Có test tương thích, tích hợp, migration và phi chức năng theo rủi ro.
- [ ] Có lịch nightly/release candidate hoặc trigger theo thay đổi.
- [ ] Môi trường và dữ liệu đủ ổn định để kết quả có ý nghĩa.
- [ ] Lỗi nghiêm trọng được đánh giá như cổng chặn dù test nằm trong extended.

### Vận hành và cải tiến

- [ ] Pipeline thể hiện rõ thứ tự, điều kiện và kết quả từng suite.
- [ ] Test flaky/quarantine có người phụ trách và hạn xem xét.
- [ ] Thời gian chạy, độ ổn định và giá trị phát hiện được theo dõi.
- [ ] Suite được review định kỳ và cập nhật theo rủi ro mới.
- [ ] Báo cáo ghi rõ suite đã chạy, suite bị bỏ qua và lý do.

## 16. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Sau deploy, ứng dụng không khởi động vì thiếu biến cấu hình. Nhóm nên phát hiện qua smoke hoặc health/readiness check và dừng các suite phía sau. Chạy hồi quy mở rộng lúc này không giúp ích vì môi trường chưa đủ điều kiện.

**Tình huống 2:** Thay đổi công thức giảm giá có thể ảnh hưởng giá thanh toán. Unit test cho các ngưỡng và core regression cho checkout nên chạy sớm. Extended có thể bổ sung nhiều loại tiền tệ, locale và các tổ hợp chương trình khuyến mãi.

**Tình huống 3:** Một lỗi production từng tạo giao dịch trùng sau timeout. Test tái hiện retry với idempotency key nên được đưa vào core nếu chạy nhanh và ổn định; các biến thể webhook trễ, sai thứ tự hoặc lỗi broker có thể thuộc extended hoặc một cổng chuyên biệt tùy rủi ro.

**Tình huống 4:** Một test hiệu năng kéo dài 40 phút nằm trong extended và phát hiện độ trễ tăng mạnh. Dù nằm trong extended, lỗi này có thể chặn release nếu vi phạm SLO hoặc gây tác động lớn. Suite membership không quyết định mức độ nghiêm trọng.

**Tình huống 5:** Core regression ngày càng mất 90 phút vì có nhiều test UI trùng nhau. Nhóm nên xem lại tầng kiểm thử, chuyển quy tắc chi tiết xuống unit/API, giữ các luồng UI đại diện và đo lại thời gian. Không nên loại bỏ kiểm tra rủi ro mà không có bằng chứng thay thế.

**Tình huống 6:** Nightly extended thường fail do một sandbox đối tác không ổn định. Cần phân loại lỗi môi trường với lỗi sản phẩm, ghi nhận độ tin cậy của phụ thuộc và có test contract/simulator để phản hồi thường xuyên; vẫn duy trì kiểm tra tích hợp thật theo lịch và rủi ro.

Khi xây dựng các suite, hãy tự hỏi: **điều gì cần biết ngay sau build, hành vi nào tuyệt đối không được hỏng và những biến thể nào cần bằng chứng rộng hơn trước phát hành?** Câu trả lời giúp phân bổ test vào smoke, core và extended với mục tiêu rõ ràng.

## Kết luận

Smoke, hồi quy cốt lõi và hồi quy mở rộng là ba lớp bổ sung nhau trong chiến lược hồi quy. Smoke xác nhận bản build và môi trường đủ điều kiện để tiếp tục; core bảo vệ các hành vi và rủi ro quan trọng bằng phản hồi thường xuyên; extended mở rộng độ bao phủ cho biến thể, tích hợp, cấu hình và thuộc tính chất lượng trước những mốc cần bằng chứng sâu. Khi phân loại theo rủi ro, duy trì dữ liệu và môi trường ổn định, tích hợp suite vào CI/CD, quản lý test flaky và review định kỳ, nhóm có thể phát hiện hồi quy sớm mà vẫn kiểm soát thời gian và chi phí kiểm thử.
