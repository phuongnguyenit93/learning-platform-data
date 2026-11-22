# Ghi rõ phần ngoài phạm vi cùng lý do và tác động

## 1. Vì sao phải ghi rõ phần ngoài phạm vi?

Một kế hoạch kiểm thử có giá trị khi mọi người hiểu chính xác điều gì sẽ được xác nhận, điều gì không được xác nhận và rủi ro còn lại là gì. Danh sách các hạng mục nằm trong phạm vi thường chưa đủ. Nếu một luồng nghiệp vụ, nền tảng, tích hợp hoặc thuộc tính chất lượng bị loại khỏi đợt kiểm thử mà không có giải thích, người đọc có thể hiểu nhầm rằng hạng mục đó đã được kiểm tra hoặc không có rủi ro.

Trong **VALIDATION_TESTING_STRATEGY**, ghi rõ phần ngoài phạm vi giúp liên kết quyết định kiểm thử với mục tiêu chất lượng và mức chấp nhận rủi ro. Mỗi hạng mục bị loại cần có ranh giới, lý do, tác động, biện pháp kiểm soát thay thế và người có thẩm quyền chấp nhận rủi ro còn lại. Việc ghi nhận này hỗ trợ:

- Ngăn hiểu nhầm về mức độ bao phủ và bằng chứng kiểm thử.
- Làm rõ rủi ro nào chưa được xác nhận trước khi phát hành.
- Giúp nhóm sản phẩm, phát triển, kiểm thử, vận hành và nghiệp vụ thống nhất trách nhiệm.
- Giải thích các quyết định về thời gian, chi phí, môi trường, dữ liệu và ưu tiên.
- Xác định điều kiện khiến một hạng mục cần được đưa trở lại phạm vi.

Phần ngoài phạm vi không phải là danh sách để hợp thức hóa việc bỏ qua kiểm thử. Đó là một quyết định có chủ đích, cần có căn cứ và được xem xét theo tác động.

## 2. Phân biệt các loại hạng mục không được kiểm thử

Không phải mọi hạng mục chưa được kiểm thử đều có cùng trạng thái. Cần dùng cách diễn đạt chính xác để người đọc hiểu điều gì đã được quyết định và điều gì chỉ chưa thể thực hiện.

| Trạng thái | Ý nghĩa | Cách ghi nhận |
|---|---|---|
| Ngoài phạm vi (out of scope) | Đã quyết định không xác nhận hạng mục trong đợt hoặc phiên bản hiện tại | Ghi ranh giới, lý do, tác động, kiểm soát thay thế và người chấp thuận |
| Chưa kiểm thử (not tested) | Hạng mục thuộc phạm vi dự kiến nhưng chưa có hoạt động kiểm thử | Ghi nguyên nhân chưa thực hiện, mức độ ảnh hưởng, kế hoạch và người phụ trách |
| Bị chặn (blocked) | Không thể kiểm thử do thiếu môi trường, dữ liệu, quyền truy cập, dịch vụ phụ thuộc hoặc điều kiện cần thiết | Ghi điều kiện chặn, thời gian ảnh hưởng, phương án tháo gỡ và rủi ro trong lúc chờ |
| Hoãn (deferred) | Hạng mục được chuyển sang đợt hoặc thời điểm sau | Ghi thời điểm dự kiến, điều kiện thực hiện và rủi ro tạm thời được chấp nhận |
| Không áp dụng (not applicable) | Hạng mục không liên quan đến sản phẩm hoặc phạm vi đang đánh giá | Nêu căn cứ chứng minh vì sao không liên quan |
| Được xác nhận qua bằng chứng khác | Không chạy một loại kiểm thử cụ thể vì đã có bằng chứng phù hợp từ nguồn khác | Ghi nguồn, phạm vi, phiên bản, thời điểm và giới hạn của bằng chứng đó |

Ví dụ, kiểm thử trên một trình duyệt chưa có trong danh sách hỗ trợ có thể là “không áp dụng” nếu chính sách hỗ trợ được phê duyệt và sản phẩm thực sự không cam kết tương thích. Kiểm thử trên trình duyệt được hỗ trợ nhưng môi trường chưa sẵn sàng là “bị chặn” hoặc “chưa kiểm thử”, không nên đổi nhãn thành “ngoài phạm vi” để làm báo cáo trông đầy đủ.

Tương tự, nếu kiểm thử hiệu năng do một nhóm chuyên trách thực hiện trong pipeline khác, hạng mục này không nhất thiết nằm ngoài phạm vi xác nhận chất lượng. Cần liên kết báo cáo của nhóm đó và kiểm tra nó bao phủ đúng phiên bản, cấu hình, tải và tiêu chí đang được đánh giá.

## 3. Xác định ranh giới phần ngoài phạm vi

Một mục ngoài phạm vi cần được mô tả đủ cụ thể để không tạo ra khoảng trống diễn giải. Có thể xác định ranh giới theo các chiều sau:

| Chiều phạm vi | Câu hỏi làm rõ | Ví dụ |
|---|---|---|
| Chức năng và hành trình | Luồng, chức năng hoặc trường hợp nghiệp vụ nào bị loại? | Không kiểm thử chức năng xuất báo cáo tùy chỉnh trong bản phát hành này |
| Thành phần và tích hợp | Dịch vụ, API, nhà cung cấp hoặc giao diện nào không được kiểm tra? | Không kiểm thử nội bộ hệ thống đối soát của đối tác thanh toán |
| Nền tảng và cấu hình | Thiết bị, hệ điều hành, trình duyệt, phiên bản hoặc cấu hình nào không thuộc phạm vi? | Không xác nhận trên phiên bản hệ điều hành đã hết hỗ trợ |
| Dữ liệu | Loại dữ liệu, quy mô dữ liệu hoặc tình huống dữ liệu nào không được sử dụng? | Không sử dụng dữ liệu lịch sử đầy đủ trong môi trường kiểm thử |
| Thuộc tính chất lượng | Khía cạnh nào không được đánh giá trong đợt này? | Không thực hiện kiểm thử tải cực đại vượt quá tải đỉnh đã dự báo |
| Môi trường và vận hành | Môi trường, khu vực, quy trình triển khai hoặc tình huống vận hành nào bị loại? | Không diễn tập chuyển vùng thảm họa trong đợt kiểm thử chức năng |
| Vai trò và nhóm người dùng | Nhóm người dùng, quyền hoặc hành vi nào không được xác nhận? | Không đánh giá quy trình quản trị nội bộ của khách hàng doanh nghiệp |
| Thời gian và phiên bản | Khoảng thời gian, bản dựng hoặc đợt phát hành nào được áp dụng? | Không xác nhận dữ liệu được tạo bởi phiên bản trước thời điểm chuyển đổi đã thống nhất |

Tránh ghi những câu chung chung như “không kiểm thử các chức năng phụ”, “không kiểm thử tích hợp ngoài” hoặc “không kiểm thử trên thiết bị cũ”. Những cụm từ này không cho biết chức năng nào, tích hợp nào, thiết bị nào và căn cứ loại trừ là gì.

Nên nêu cả phần được bao gồm để tạo ranh giới đối chiếu. Ví dụ: “Đợt này xác nhận luồng thanh toán bằng thẻ trên ứng dụng web ở hai trình duyệt được hỗ trợ. Thanh toán qua ví điện tử và ứng dụng di động nằm ngoài phạm vi của đợt này; các giao diện liên quan vẫn được theo dõi theo hồ sơ tích hợp riêng.” Cách ghi này giúp tránh suy diễn rằng toàn bộ thanh toán hoặc mọi nền tảng đã được xác nhận.

## 4. Ghi lý do loại trừ có căn cứ

Lý do cần giải thích tại sao việc không kiểm thử là hợp lý trong bối cảnh hiện tại. Các nhóm lý do thường gặp gồm:

### 4.1. Không liên quan đến phạm vi hoặc phiên bản

Chức năng chưa được triển khai, không có trong sản phẩm, không được hỗ trợ hoặc không thuộc hành trình đang đánh giá. Cần dẫn đến tài liệu phạm vi, chính sách hỗ trợ hoặc quyết định sản phẩm làm căn cứ. Không suy luận rằng một chức năng “không quan trọng” chỉ vì ít người dùng.

### 4.2. Đã có bằng chứng xác nhận phù hợp

Một hoạt động xác nhận khác đã bao phủ cùng rủi ro, cùng phiên bản và điều kiện tương đương. Ví dụ, kiểm thử hợp đồng API được chạy độc lập trong pipeline của nhóm sở hữu dịch vụ. Cần ghi liên kết tới kết quả, thời điểm chạy, phiên bản và phạm vi thực tế. Việc có một báo cáo cũ hoặc báo cáo của môi trường khác không tự động chứng minh yêu cầu hiện tại đã được đáp ứng.

### 4.3. Rủi ro thấp trong bối cảnh đã xác định

Hạng mục có tác động nhỏ, ít được sử dụng hoặc được cô lập tốt. Lý do này phải đi kèm đánh giá rủi ro và bằng chứng, chẳng hạn dữ liệu sử dụng, phân tích ảnh hưởng hoặc lịch sử lỗi. “Chưa từng có lỗi” không đủ để kết luận rủi ro thấp nếu thiếu dữ liệu hoặc hệ thống vừa thay đổi đáng kể.

### 4.4. Giới hạn nguồn lực hoặc điều kiện thực hiện

Thiếu thời gian, môi trường, thiết bị, dữ liệu, giấy phép hoặc quyền truy cập. Đây thường là lý do để đánh dấu “chưa kiểm thử”, “bị chặn” hoặc “hoãn”. Nếu vẫn quyết định loại khỏi đợt phát hành, cần nêu rõ giới hạn, hậu quả, biện pháp giảm thiểu và người chấp nhận rủi ro. Giới hạn nguồn lực không làm rủi ro biến mất.

### 4.5. Có thể xác nhận ở giai đoạn khác

Một số kiểm tra phù hợp hơn với giai đoạn triển khai, diễn tập vận hành hoặc kiểm tra định kỳ. Ví dụ, diễn tập khôi phục thảm họa có thể được lên lịch trong đợt vận hành riêng. Cần ghi ngày hoặc điều kiện thực hiện, chủ sở hữu và biện pháp bảo vệ trong thời gian chưa có kết quả.

### 4.6. Bị giới hạn bởi bên thứ ba

Nhóm không có quyền truy cập hoặc không thể kiểm thử nội bộ dịch vụ của nhà cung cấp. Cần mô tả ranh giới trách nhiệm, bằng chứng thay thế như chứng nhận, báo cáo kiểm toán, cam kết dịch vụ hoặc kiểm thử sandbox, cùng các giới hạn còn lại. Không dùng tài liệu của nhà cung cấp để khẳng định những hành vi tích hợp mà nhóm chưa xác nhận.

Lý do loại trừ nên cụ thể, kiểm chứng được và gắn với thời điểm. Nếu lý do chỉ là “không đủ thời gian”, cần ghi rõ phần nào bị ảnh hưởng, tại sao không thể thu hẹp phạm vi kiểm thử theo rủi ro và ai phê duyệt quyết định phát hành trong điều kiện đó.

## 5. Phân tích và mô tả tác động

Tác động của một hạng mục ngoài phạm vi là phần thông tin quan trọng nhất đối với người ra quyết định. Cần trả lời: nếu hạng mục này có lỗi, ai hoặc điều gì bị ảnh hưởng, ảnh hưởng nghiêm trọng đến đâu, có thể phát hiện bằng cách nào và có thể khôi phục ra sao?

Nên xem xét ít nhất các khía cạnh sau:

- **Người dùng và nghiệp vụ:** nhóm người dùng, hành trình, doanh thu, năng suất hoặc khả năng hoàn thành công việc có thể bị ảnh hưởng.
- **Dữ liệu và bảo mật:** nguy cơ mất, sai lệch, lộ, truy cập trái phép hoặc không thể khôi phục dữ liệu.
- **Vận hành:** ảnh hưởng đến tính sẵn sàng, hiệu năng, giám sát, hỗ trợ, xử lý sự cố và khôi phục.
- **Tích hợp và tương thích:** hệ thống phụ thuộc, đối tác, phiên bản API hoặc nền tảng có thể gặp lỗi dây chuyền.
- **Tuân thủ và hợp đồng:** nghĩa vụ pháp lý, cam kết dịch vụ, yêu cầu kiểm toán hoặc điều khoản với khách hàng có thể không được đáp ứng.
- **Phạm vi chưa biết:** điều gì chưa thể kết luận vì chưa có bằng chứng và mức độ tin cậy của giả định hiện tại.

Có thể đánh giá rủi ro bằng tác động, khả năng xảy ra, khả năng phát hiện và khả năng khôi phục. Dùng thang định tính hoặc định lượng nhất quán trong nhóm, nhưng không để điểm tổng che khuất rủi ro nghiêm trọng. Một hạng mục có xác suất thấp nhưng có thể làm lộ dữ liệu cá nhân hoặc ghi nhận sai giao dịch vẫn cần được xử lý theo mức độ nghiêm trọng của hậu quả.

Tác động nên mô tả cả điều đã biết và điều chưa biết. Ví dụ: “Chưa kiểm thử trên phiên bản trình duyệt cũ không còn nằm trong chính sách hỗ trợ. Người dùng trên phiên bản này có thể gặp lỗi hiển thị; nhóm hỗ trợ không cam kết khắc phục riêng. Chưa có bằng chứng về khả năng truy cập trái phép hoặc sai lệch dữ liệu từ cấu hình này.” Cách viết này cụ thể hơn kết luận “tác động thấp”.

## 6. Biện pháp kiểm soát thay thế và rủi ro còn lại

Khi một hạng mục không được kiểm thử, cần xem xét biện pháp giảm thiểu phù hợp. Biện pháp có thể bao gồm:

- Dùng bằng chứng từ kiểm thử trước đó hoặc pipeline khác sau khi xác nhận đúng phiên bản và phạm vi.
- Giới hạn phát hành bằng feature flag, cấu hình, quyền truy cập hoặc nhóm người dùng.
- Triển khai theo từng đợt, canary hoặc nhóm khách hàng nhỏ và theo dõi chỉ số quan trọng.
- Tăng cường giám sát, cảnh báo, nhật ký và quy trình phản ứng trong thời gian chấp nhận rủi ro.
- Chuẩn bị rollback, tắt tính năng, khôi phục dữ liệu hoặc quy trình xử lý thủ công.
- Hạn chế loại dữ liệu, giao dịch hoặc môi trường có thể bị ảnh hưởng.
- Lập lịch kiểm thử bổ sung trước một mốc phát hành hoặc trước khi mở rộng phạm vi sử dụng.

Biện pháp thay thế không phải lúc nào cũng tương đương với kiểm thử bị thiếu. Giám sát sau phát hành có thể giúp phát hiện lỗi nhưng không ngăn người dùng đầu tiên chịu tác động. Rollback có thể phục hồi dịch vụ nhưng không đảo ngược được một giao dịch tài chính đã hoàn tất hoặc việc dữ liệu nhạy cảm bị tiết lộ. Hãy mô tả giới hạn của từng biện pháp và rủi ro còn lại sau khi áp dụng.

Nếu rủi ro vượt quá mức chấp nhận hoặc liên quan đến yêu cầu bắt buộc, cần dừng phát hành, giảm phạm vi, bổ sung kiểm thử hoặc chuyển quyết định lên cấp có thẩm quyền. Không được coi việc ghi một ngoại lệ trong tài liệu là đủ để hợp thức hóa rủi ro không thể chấp nhận.

## 7. Quy trình quyết định và quản lý phần ngoài phạm vi

### Bước 1: Liệt kê các hạng mục có khả năng bị loại

Rà soát yêu cầu, hành trình, kiến trúc, tích hợp, nền tảng, dữ liệu, thuộc tính chất lượng và môi trường. So sánh với mục tiêu chất lượng và rủi ro đã xác định. Mỗi hạng mục quan trọng cần có trạng thái rõ ràng: trong phạm vi, ngoài phạm vi, chưa kiểm thử, bị chặn, hoãn hoặc không áp dụng.

### Bước 2: Xác định ranh giới chính xác

Ghi tên chức năng, luồng, API, nền tảng, phiên bản, dữ liệu hoặc điều kiện bị loại. Chỉ rõ phần liên quan vẫn được kiểm tra để tránh hiểu nhầm. Nếu loại một phần của luồng, hãy xác định điểm bắt đầu và kết thúc của phần được xác nhận.

### Bước 3: Ghi lý do và bằng chứng

Nêu lý do cụ thể, nguồn dữ liệu hoặc quyết định hỗ trợ lý do đó. Nếu dựa trên báo cáo khác, kiểm tra phiên bản, cấu hình, ngày chạy, môi trường và giới hạn bao phủ. Nếu dựa trên mức sử dụng thấp, nêu nguồn và khoảng thời gian dữ liệu.

### Bước 4: Phân tích tác động và rủi ro còn lại

Xác định người dùng, nghiệp vụ, dữ liệu, bảo mật, vận hành, tích hợp và nghĩa vụ có thể bị ảnh hưởng. Nêu hậu quả nếu có lỗi, mức độ chưa chắc chắn và khả năng phát hiện hoặc khôi phục.

### Bước 5: Chọn biện pháp giảm thiểu hoặc kế hoạch bổ sung

Xác định kiểm soát thay thế, người phụ trách, thời hạn, điều kiện thực hiện và bằng chứng cần có. Nếu không có biện pháp giảm thiểu khả thi, nêu rõ điều đó để người ra quyết định đánh giá đúng mức rủi ro.

### Bước 6: Xin chấp thuận đúng thẩm quyền

Người chịu trách nhiệm sản phẩm hoặc phát hành cần chấp thuận rủi ro kinh doanh; chủ sở hữu kỹ thuật, bảo mật, dữ liệu hoặc tuân thủ cần tham gia khi quyết định ảnh hưởng đến lĩnh vực họ phụ trách. Người ghi nhận ngoại lệ không nên tự mặc định mình có quyền chấp nhận mọi rủi ro.

### Bước 7: Theo dõi và xem xét lại

Gắn hạng mục với phiên bản, đợt phát hành, thời hạn và điều kiện kích hoạt đánh giá lại. Khi có thay đổi yêu cầu, kiến trúc, nhà cung cấp, mức sử dụng, sự cố hoặc nghĩa vụ mới, phải xem xét hạng mục có cần đưa trở lại phạm vi hay không. Đóng ngoại lệ khi đã có bằng chứng phù hợp hoặc khi quyết định loại trừ không còn hiệu lực.

## 8. Ví dụ thực tế

### Ví dụ A: Không kiểm thử một trình duyệt đã hết hỗ trợ

**Ranh giới:** bản phát hành web chỉ cam kết hỗ trợ các phiên bản trình duyệt còn trong chính sách tương thích đã công bố. Các phiên bản đã hết hỗ trợ không nằm trong ma trận kiểm thử.

**Lý do:** nhà cung cấp trình duyệt đã kết thúc hỗ trợ bảo mật; sản phẩm đã thông báo thời điểm ngừng hỗ trợ và có dữ liệu cho thấy nhóm người dùng còn lại rất nhỏ.

**Tác động:** người dùng tiếp tục sử dụng phiên bản cũ có thể gặp lỗi hiển thị hoặc thao tác. Nhóm không có bằng chứng xác nhận trải nghiệm hoặc bảo mật trên cấu hình đó.

**Kiểm soát:** hiển thị thông tin về trình duyệt được hỗ trợ, theo dõi lỗi theo user-agent và hướng dẫn người dùng nâng cấp. Nếu có khách hàng hợp đồng đặc biệt cần phiên bản cũ, phải đánh giá riêng trước khi cam kết.

### Ví dụ B: Hoãn kiểm thử tải cực đại

**Ranh giới:** đợt xác nhận trước phát hành kiểm thử tải bình thường và tải đỉnh dự báo; chưa kiểm thử tình huống vượt xa dự báo trong thời gian dài.

**Lý do:** môi trường kiểm thử hiện tại chưa có năng lực tạo tải tương đương và thời gian chuẩn bị hạ tầng chưa đủ.

**Tác động:** chưa biết chính xác ngưỡng suy giảm khi tải vượt dự báo. Tăng trưởng đột biến có thể gây tăng độ trễ, từ chối yêu cầu hoặc làm cạn tài nguyên.

**Kiểm soát:** giới hạn tốc độ, đặt ngưỡng tự động mở rộng, theo dõi độ trễ và tỷ lệ lỗi, chuẩn bị phương án giảm tải. Lập lịch kiểm thử tải cực đại trước chiến dịch có dự báo lưu lượng lớn. Nếu không chứng minh được hệ thống đáp ứng tải bắt buộc, cần giới hạn quy mô phát hành hoặc hoãn phát hành.

### Ví dụ C: Không kiểm thử nội bộ hệ thống của nhà cung cấp thanh toán

**Ranh giới:** nhóm kiểm thử xác nhận hợp đồng API, xác thực, timeout, retry, chữ ký webhook và đối soát ở phía tích hợp; không truy cập hoặc kiểm thử mã nguồn và hạ tầng nội bộ của nhà cung cấp.

**Lý do:** hạ tầng thuộc quyền quản lý của bên thứ ba và không nằm trong quyền truy cập của nhóm.

**Tác động:** nhóm không thể tự xác nhận mọi lỗi nội bộ hoặc khả năng phục hồi của nhà cung cấp. Sự cố từ phía nhà cung cấp có thể ảnh hưởng đến việc hoàn tất thanh toán.

**Kiểm soát:** xem xét cam kết dịch vụ và báo cáo bảo đảm phù hợp, kiểm thử sandbox, mô phỏng lỗi tích hợp, giám sát tỷ lệ thành công, đối soát trạng thái và có phương án xử lý giao dịch chưa rõ kết quả. Ghi rõ các bằng chứng của nhà cung cấp không thay thế việc xác nhận luồng tích hợp đầu cuối.

### Ví dụ D: Hoãn diễn tập khôi phục thảm họa

**Ranh giới:** đợt kiểm thử chức năng không thực hiện diễn tập mất toàn bộ vùng triển khai; hoạt động này được lên lịch trong chương trình kiểm thử liên tục của vận hành.

**Lý do:** diễn tập cần cửa sổ bảo trì, phối hợp nhiều nhóm và phê duyệt vận hành riêng.

**Tác động:** khả năng đáp ứng RTO/RPO trong tình huống mất vùng chưa được chứng minh bởi đợt kiểm thử hiện tại.

**Kiểm soát:** xác minh bản sao lưu, kiểm tra cấu hình phục hồi và lịch diễn tập đã được phê duyệt. Nếu RTO/RPO là điều kiện bắt buộc trước phát hành, việc chưa diễn tập là rủi ro chặn phát hành cho đến khi có bằng chứng phù hợp.

## 9. Mẫu ghi nhận phần ngoài phạm vi

Mỗi hạng mục nên có một bản ghi riêng để dễ truy vết và xem xét lại.

| Trường | Nội dung cần ghi |
|---|---|
| ID | Mã định danh duy nhất của hạng mục hoặc ngoại lệ |
| Phiên bản/đợt | Bản dựng, phiên bản, môi trường và đợt phát hành áp dụng |
| Hạng mục bị loại | Chức năng, luồng, thành phần, tích hợp, nền tảng hoặc thuộc tính chất lượng cụ thể |
| Ranh giới | Phần nào bị loại, phần liên quan nào vẫn được xác nhận |
| Trạng thái | Ngoài phạm vi, chưa kiểm thử, bị chặn, hoãn, không áp dụng hoặc có bằng chứng thay thế |
| Lý do | Nguyên nhân và căn cứ, kèm liên kết hoặc nguồn bằng chứng |
| Tác động | Người dùng, nghiệp vụ, dữ liệu, bảo mật, vận hành, tích hợp và tuân thủ có thể bị ảnh hưởng |
| Rủi ro còn lại | Khả năng xảy ra, mức độ nghiêm trọng, điều chưa biết và giới hạn bằng chứng |
| Biện pháp kiểm soát | Giám sát, giới hạn phát hành, rollback, bằng chứng thay thế hoặc kiểm thử bổ sung |
| Điều kiện đưa lại vào phạm vi | Sự kiện, thay đổi, ngưỡng hoặc ngày cần đánh giá lại |
| Chủ sở hữu | Người chịu trách nhiệm thực hiện kiểm soát và theo dõi |
| Người chấp thuận | Người có thẩm quyền chấp nhận rủi ro còn lại |
| Thời hạn | Ngày hết hiệu lực hoặc mốc xem xét lại ngoại lệ |
| Quyết định | Chấp thuận, yêu cầu bổ sung kiểm thử, giới hạn phát hành hoặc không chấp thuận |

Ví dụ bản ghi ngắn:

```yaml
id: TS-EX-014
release: 2.4.0
item: "Kiểm thử tải vượt mức đỉnh dự báo trong 2 giờ"
boundary: "Đã kiểm thử tải bình thường và tải đỉnh dự báo; chưa kiểm thử tải vượt dự báo kéo dài"
status: deferred
reason: "Môi trường tạo tải chưa đáp ứng; cần bổ sung năng lực trước chiến dịch lớn"
impact: "Chưa xác định ngưỡng suy giảm khi lưu lượng vượt dự báo"
mitigation:
  - "Giới hạn tốc độ và theo dõi p95, tỷ lệ lỗi, tài nguyên"
  - "Giới hạn quy mô phát hành trước khi có kết quả tải cực đại"
revisit_when: "Trước chiến dịch có lưu lượng lớn tiếp theo"
owner: "Service owner"
approval: "Release owner"
```

Đây là ví dụ cấu trúc để minh họa nội dung cần ghi; nhóm có thể dùng biểu mẫu hoặc hệ thống quản lý ngoại lệ hiện có. Điều quan trọng là các trường phải được điền đầy đủ, có thể truy vết và cập nhật theo trạng thái thực tế.

## 10. Những sai lầm thường gặp

- **Chỉ liệt kê phần bị loại mà không ghi lý do:** người đọc không thể đánh giá quyết định có hợp lý hay không.
- **Dùng lý do nguồn lực như thể rủi ro đã biến mất:** thiếu thời gian hoặc môi trường chỉ giải thích vì sao chưa kiểm thử; cần mô tả tác động và người chấp nhận rủi ro.
- **Gộp “không áp dụng” với “chưa kiểm thử”:** làm sai lệch mức bao phủ và che giấu các hạng mục còn thiếu bằng chứng.
- **Mô tả ranh giới quá rộng:** cụm từ như “các tích hợp bên ngoài” có thể vô tình bao gồm tích hợp quan trọng vẫn cần xác nhận.
- **Dùng báo cáo cũ mà không kiểm tra tính phù hợp:** khác phiên bản, cấu hình hoặc điều kiện có thể khiến bằng chứng không còn giá trị.
- **Không nêu tác động đến người dùng và dữ liệu:** báo cáo chỉ nói về công việc của nhóm mà bỏ qua hậu quả kinh doanh.
- **Coi giám sát là thay thế hoàn toàn cho kiểm thử:** phát hiện sau phát hành không ngăn được mọi tổn thất và có thể đến quá muộn.
- **Không chỉ định người phê duyệt:** ngoại lệ tồn tại nhưng không ai chịu trách nhiệm chấp nhận rủi ro.
- **Không có thời hạn hoặc điều kiện xem xét lại:** hạng mục hoãn có thể bị quên và trở thành khoảng trống kéo dài.
- **Không cập nhật khi phạm vi thay đổi:** quyết định loại trừ cũ có thể không còn phù hợp với phiên bản hoặc kiến trúc mới.

## 11. Checklist trước khi chốt phạm vi kiểm thử

- [ ] Mỗi hạng mục bị loại được mô tả bằng tên và ranh giới cụ thể.
- [ ] Trạng thái được phân biệt rõ giữa ngoài phạm vi, chưa kiểm thử, bị chặn, hoãn, không áp dụng và có bằng chứng thay thế.
- [ ] Lý do có căn cứ và nguồn bằng chứng phù hợp với phiên bản, môi trường và thời điểm.
- [ ] Tác động đến người dùng, nghiệp vụ, dữ liệu, bảo mật, vận hành, tích hợp và tuân thủ đã được xem xét.
- [ ] Rủi ro còn lại và những điều chưa biết được nêu rõ.
- [ ] Biện pháp kiểm soát thay thế có chủ sở hữu và giới hạn được mô tả.
- [ ] Điều kiện đưa hạng mục trở lại phạm vi hoặc thời điểm kiểm thử bổ sung đã được xác định.
- [ ] Người có thẩm quyền đã chấp thuận rủi ro; yêu cầu bắt buộc không bị miễn trừ trái thẩm quyền.
- [ ] Báo cáo phạm vi không tạo ấn tượng rằng hạng mục ngoài phạm vi đã được kiểm thử.
- [ ] Các ngoại lệ được theo dõi và rà soát khi sản phẩm hoặc bối cảnh thay đổi.

## Kết luận

Ghi rõ phần ngoài phạm vi cùng lý do và tác động giúp báo cáo kiểm thử phản ánh trung thực mức độ xác nhận của sản phẩm. Mỗi quyết định loại trừ cần có ranh giới cụ thể, căn cứ, phân tích tác động, rủi ro còn lại, biện pháp kiểm soát, người chấp thuận và điều kiện xem xét lại. Nhờ đó, nhóm có thể đưa ra quyết định phát hành minh bạch, tập trung kiểm thử vào rủi ro quan trọng và tránh để khoảng trống chưa được xác nhận bị hiểu nhầm thành chất lượng đã được bảo đảm.
