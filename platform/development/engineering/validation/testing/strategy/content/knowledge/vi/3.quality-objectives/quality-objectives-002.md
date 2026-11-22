# Phân biệt mục tiêu kiểm thử với mục tiêu sửa lỗi hoặc cải tiến sản phẩm

## Mục tiêu bài học

Trong chiến lược VALIDATION_TESTING_STRATEGY, một hoạt động có thể liên quan đến kiểm thử, sửa lỗi và cải tiến sản phẩm nhưng ba loại mục tiêu này trả lời ba câu hỏi khác nhau. Kiểm thử nhằm thu thập bằng chứng và cung cấp thông tin về chất lượng hoặc rủi ro. Sửa lỗi nhằm loại bỏ nguyên nhân khiến phần mềm không đáp ứng hành vi mong đợi. Cải tiến sản phẩm nhằm tăng giá trị hoặc khả năng sử dụng của sản phẩm theo nhu cầu đã xác định.

Nếu không phân biệt rõ, nhóm có thể dùng số lượng test case làm thước đo thành công của việc sửa lỗi, coi một yêu cầu tính năng mới là lỗi, hoặc kết thúc kiểm thử mà chưa có quyết định về rủi ro còn lại. Bài học này giúp nhóm xác định đúng mục tiêu, chọn tiêu chí đánh giá phù hợp và phối hợp ba hoạt động thành một quy trình có thể truy vết.

Sau bài học, người học có thể:

- Phân biệt mục tiêu kiểm thử, mục tiêu sửa lỗi và mục tiêu cải tiến sản phẩm.
- Chuyển một vấn đề hoặc yêu cầu thành mục tiêu có thể đánh giá.
- Chọn bằng chứng và chỉ số phù hợp cho từng loại mục tiêu.
- Phân loại kết quả kiểm thử thành lỗi, yêu cầu cải tiến hoặc rủi ro được chấp nhận.
- Xác định cách kiểm thử lại, kiểm thử hồi quy và xác nhận thay đổi sau khi sửa hoặc cải tiến.

## 1. Vì sao cần phân biệt ba loại mục tiêu?

Trong một dự án, các hoạt động thường nối tiếp nhau. Người kiểm thử thực hiện một kịch bản, phát hiện kết quả sai, ghi nhận lỗi; nhà phát triển sửa mã; nhóm sản phẩm đề xuất một thay đổi để trải nghiệm tốt hơn; người kiểm thử xác nhận bản sửa và đánh giá ảnh hưởng của thay đổi. Vì cùng xuất hiện trong một luồng công việc, các mục tiêu dễ bị gộp thành một câu chung như “nâng cao chất lượng”.

Mục tiêu chung như vậy chưa đủ để điều hành công việc. Nó không cho biết:

- Nhóm cần tìm hiểu điều gì và cần bằng chứng nào?
- Hành vi nào đang sai so với yêu cầu hoặc hợp đồng đã thống nhất?
- Người dùng cần giá trị mới nào ngoài hành vi hiện tại?
- Ai quyết định mức rủi ro có thể chấp nhận?
- Điều kiện nào cho phép đóng hoạt động hoặc đưa thay đổi đến người dùng?

Phân biệt mục tiêu giúp nhóm chọn đúng phương pháp và tiêu chí. Một kiểm thử có thể hoàn thành tốt mục tiêu cung cấp thông tin dù phát hiện nhiều lỗi. Một bản sửa có thể khắc phục đúng lỗi được báo cáo nhưng chưa chứng minh rằng chức năng không bị ảnh hưởng ở nơi khác. Một cải tiến có thể được triển khai thành công về kỹ thuật nhưng không tạo ra lợi ích mà người dùng cần. Vì vậy, mỗi loại mục tiêu cần được xác định và đánh giá riêng.

## 2. Mục tiêu kiểm thử là gì?

**Mục tiêu kiểm thử (testing objective)** mô tả điều nhóm muốn đạt được thông qua hoạt động kiểm thử: đánh giá một thuộc tính chất lượng, xác minh một yêu cầu, phát hiện rủi ro, cung cấp thông tin cho quyết định phát hành hoặc kiểm tra rằng các thành phần phối hợp đúng.

Kiểm thử tạo ra bằng chứng. Bằng chứng có thể là kết quả đạt/trượt, báo cáo lỗi, log, số liệu hiệu năng, kết quả phân tích bảo mật, ảnh chụp, bản ghi thao tác hoặc kết quả so sánh với tiêu chí chấp nhận. Nhóm dùng bằng chứng đó để hiểu trạng thái của sản phẩm và quyết định bước tiếp theo.

Một mục tiêu kiểm thử tốt thường có các thành phần:

1. **Đối tượng và phạm vi:** chức năng, thành phần, phiên bản, môi trường hoặc luồng nghiệp vụ cần kiểm tra.
2. **Khẳng định cần đánh giá:** yêu cầu, quy tắc nghiệp vụ, thuộc tính chất lượng hoặc giả định nào cần được xác minh.
3. **Rủi ro cần giảm:** điều gì có thể xảy ra nếu khẳng định đó không đúng.
4. **Bằng chứng cần thu thập:** kiểm tra, dữ liệu, quan sát hoặc kết quả nào sẽ hỗ trợ đánh giá.
5. **Tiêu chí hoàn thành:** mức độ bao phủ, điều kiện đạt/trượt hoặc ngưỡng chấp nhận để ra quyết định.

Ví dụ, thay vì ghi “kiểm thử chức năng thanh toán”, nhóm có thể đặt mục tiêu cụ thể: “Xác minh rằng tổng tiền, thuế và phí được tính đúng theo quy tắc đã thống nhất cho các loại đơn hàng chính, đồng thời giao dịch không bị ghi nhận hai lần khi người dùng gửi yêu cầu lặp.” Mục tiêu này chỉ rõ phạm vi, khẳng định cần kiểm tra và rủi ro cần giảm.

### 2.1. Các mục tiêu kiểm thử thường gặp

| Mục tiêu | Câu hỏi kiểm thử cần trả lời | Bằng chứng có thể dùng |
|---|---|---|
| Xác minh yêu cầu (verification) | Sản phẩm hoặc thành phần có đáp ứng đặc tả, thiết kế và quy tắc đã định không? | Kết quả kiểm thử đơn vị, tích hợp, hợp đồng API và truy vết yêu cầu. |
| Xác nhận nhu cầu sử dụng (validation) | Giải pháp có đáp ứng nhu cầu và cách sử dụng thực tế của người dùng không? | Nghiệm thu, thử nghiệm người dùng, đánh giá nghiệp vụ và phản hồi có cấu trúc. |
| Đánh giá chức năng | Các luồng và quy tắc nghiệp vụ có cho kết quả đúng không? | Kết quả theo dữ liệu đầu vào, đầu ra mong đợi và các trường hợp biên. |
| Đánh giá thuộc tính chất lượng | Hiệu năng, bảo mật, khả năng truy cập, độ tin cậy hoặc khả năng tương thích có đạt ngưỡng không? | Số đo, báo cáo chuyên biệt, kiểm tra trên môi trường và thiết bị đại diện. |
| Phát hiện lỗi và rủi ro | Có hành vi không mong muốn hoặc điều kiện có thể gây thất bại không? | Lỗi tái hiện được, log, kết quả kiểm tra khám phá và phân tích nguyên nhân ban đầu. |
| Kiểm tra thay đổi và hồi quy | Thay đổi mới có hoạt động đúng và có làm hỏng hành vi đã có không? | Kiểm thử lại lỗi, bộ kiểm thử hồi quy và so sánh kết quả trước/sau. |
| Hỗ trợ quyết định phát hành | Bằng chứng hiện có có đủ để người có thẩm quyền chấp nhận phát hành không? | Báo cáo trạng thái kiểm thử, lỗi còn mở, rủi ro tồn dư và ngoại lệ được phê duyệt. |

Những mục tiêu này có thể cùng tồn tại trong một kế hoạch kiểm thử. Tuy nhiên, cần ghi rõ mục tiêu chính của từng hoạt động để chọn mức kiểm tra và cách báo cáo phù hợp.

### 2.2. Kiểm thử không đồng nghĩa với sửa lỗi

Người kiểm thử có thể phát hiện và mô tả một lỗi, nhưng việc thực thi test case không tự sửa được nguyên nhân trong mã nguồn hoặc cấu hình. Kết quả kiểm thử thường cho biết một điều kiện không đạt, còn việc sửa lỗi cần phân tích vì sao điều kiện đó xảy ra và thay đổi thành phần phù hợp.

Kiểm thử cũng không chứng minh rằng phần mềm hoàn toàn không có lỗi. Kết quả đạt chỉ cho thấy các trường hợp đã kiểm tra đáp ứng tiêu chí trong phạm vi, dữ liệu và môi trường cụ thể. Nhóm cần kết hợp kiểm thử với phân tích rủi ro, rà soát, giám sát vận hành và phản hồi người dùng để có bức tranh đầy đủ hơn.

## 3. Mục tiêu sửa lỗi là gì?

**Mục tiêu sửa lỗi (defect-fixing objective)** mô tả kết quả cần đạt khi khắc phục một hành vi sai hoặc một nguyên nhân gây ra hành vi sai. Lỗi thường được xác định khi kết quả thực tế khác với yêu cầu, tiêu chí chấp nhận, hợp đồng giao tiếp, quy tắc nghiệp vụ hoặc hành vi đã được cam kết.

Một mục tiêu sửa lỗi cần làm rõ:

- Hành vi sai được quan sát là gì và xảy ra trong điều kiện nào?
- Hành vi đúng cần đạt là gì, dựa trên nguồn yêu cầu hoặc quyết định nào?
- Nguyên nhân gốc hoặc cơ chế gây lỗi đã được xác định đến mức nào?
- Thay đổi nào sẽ khắc phục lỗi và có thể ảnh hưởng đến thành phần nào?
- Bằng chứng nào xác nhận lỗi đã được khắc phục và không gây hồi quy nghiêm trọng?

Ví dụ: “Khi khách hàng áp dụng mã giảm giá cho đơn hàng có sản phẩm được miễn thuế, hệ thống đang tính thuế trên phần giá đã được giảm sai quy tắc. Sửa phép tính để tuân thủ quy tắc thuế đã phê duyệt, đồng thời bảo đảm tổng tiền, hóa đơn và dữ liệu giao dịch nhất quán.” Mục tiêu sửa lỗi tập trung vào việc khôi phục hành vi đúng.

### 3.1. Các bước cơ bản trong sửa lỗi

1. **Tiếp nhận và xác nhận:** kiểm tra báo cáo có đủ phiên bản, môi trường, dữ liệu, bước tái hiện, kết quả thực tế và kết quả mong đợi hay chưa.
2. **Phân loại và ưu tiên:** đánh giá mức độ nghiêm trọng, phạm vi ảnh hưởng, khả năng xảy ra, tác động đến người dùng và mức khẩn cấp.
3. **Điều tra nguyên nhân:** tái hiện lỗi, xem log, lần theo luồng dữ liệu, kiểm tra thay đổi liên quan và xác định điều kiện kích hoạt.
4. **Sửa nguyên nhân:** cập nhật mã, cấu hình, dữ liệu hoặc quy trình có liên quan; tránh chỉ che biểu hiện nếu nguyên nhân vẫn tồn tại.
5. **Kiểm thử lại (retesting):** chạy trường hợp đã thất bại trước đó để xác nhận hành vi sai không còn xảy ra trong điều kiện đã mô tả.
6. **Kiểm thử hồi quy (regression testing):** kiểm tra các luồng liên quan để phát hiện tác động ngoài ý muốn của bản sửa.
7. **Đóng lỗi có căn cứ:** lưu phiên bản đã sửa, kết quả kiểm thử, bằng chứng và quyết định đóng hoặc tiếp tục theo dõi.

Sửa lỗi có thể bao gồm biện pháp phòng ngừa để tránh tái diễn, chẳng hạn bổ sung kiểm tra đầu vào, cải thiện xử lý ngoại lệ, thêm test tự động hoặc sửa quy tắc thiết kế. Nếu cần thay đổi cách sản phẩm hoạt động vượt ra ngoài yêu cầu đã cam kết, nhóm nên ghi nhận phần đó như một mục tiêu cải tiến riêng.

### 3.2. Đo lường thành công của sửa lỗi

Thành công của sửa lỗi được đánh giá qua hành vi được khôi phục và rủi ro phát sinh sau bản sửa. Một số bằng chứng phù hợp gồm:

- Trường hợp tái hiện ban đầu hiện đạt theo kết quả mong đợi.
- Nguyên nhân đã xác định được xử lý và có kiểm tra bảo vệ chống tái diễn.
- Các luồng liên quan vượt qua kiểm thử hồi quy phù hợp.
- Không xuất hiện lỗi nghiêm trọng mới trong phạm vi ảnh hưởng.
- Tỷ lệ lỗi tái mở hoặc lỗi cùng nguyên nhân giảm theo thời gian.

Số lượng lỗi đóng trong một sprint không đủ để chứng minh chất lượng sửa lỗi. Một lỗi có thể được đóng do không tái hiện được, trùng lặp, không phải lỗi hoặc được chấp nhận như rủi ro; các trạng thái đó cần được phân biệt trong báo cáo.

## 4. Mục tiêu cải tiến sản phẩm là gì?

**Mục tiêu cải tiến sản phẩm (product-improvement objective)** mô tả giá trị mới hoặc sự thay đổi tích cực mà sản phẩm cần mang lại cho người dùng, khách hàng hoặc tổ chức. Cải tiến có thể liên quan đến chức năng, trải nghiệm, hiệu năng, khả năng truy cập, khả năng cấu hình, độ tin cậy, chi phí vận hành hoặc quy trình hỗ trợ.

Khác với sửa lỗi, cải tiến không nhất thiết bắt nguồn từ một hành vi đang vi phạm yêu cầu hiện có. Sản phẩm có thể hoạt động đúng theo đặc tả nhưng người dùng vẫn cần cách làm nhanh hơn, dễ hiểu hơn hoặc phù hợp hơn với công việc mới.

Ví dụ: “Giảm thời gian hoàn tất thanh toán cho khách hàng quay lại bằng cách cho phép lưu phương thức thanh toán an toàn và xác nhận đơn hàng trong ít bước hơn, đồng thời duy trì yêu cầu xác thực và bảo vệ dữ liệu.” Mục tiêu này hướng đến kết quả người dùng nhận được, kèm giới hạn chất lượng cần giữ.

### 4.1. Đặc điểm của mục tiêu cải tiến tốt

- **Xuất phát từ nhu cầu:** có phản hồi người dùng, dữ liệu sử dụng, mục tiêu kinh doanh hoặc vấn đề vận hành làm căn cứ.
- **Mô tả giá trị mong đợi:** nêu người dùng hoặc tổ chức sẽ làm được điều gì tốt hơn.
- **Có chỉ số đánh giá:** xác định chỉ số đầu ra hoặc kết quả, giá trị hiện tại nếu biết và mục tiêu cần đạt.
- **Nêu giới hạn chất lượng:** bảo mật, quyền riêng tư, khả năng truy cập, độ tin cậy và tương thích phải được duy trì.
- **Có phạm vi và đối tượng:** chỉ rõ người dùng, nền tảng, luồng nghiệp vụ và phiên bản liên quan.

Ví dụ về một mục tiêu đo được: “Trong nhóm người dùng thử nghiệm, giảm trung vị thời gian hoàn thành biểu mẫu từ 4 phút xuống dưới 3 phút mà không làm giảm tỷ lệ gửi thành công hoặc tăng lỗi xác thực.” Chỉ số cần được đo trong điều kiện tương đương và có đủ dữ liệu để tránh kết luận từ một mẫu quá nhỏ.

### 4.2. Kiểm thử một cải tiến

Một cải tiến vẫn cần được kiểm thử. Mục tiêu kiểm thử lúc này là cung cấp bằng chứng rằng chức năng mới đáp ứng yêu cầu, tạo ra kết quả mong đợi và không làm suy giảm chất lượng ở các phần liên quan.

Ví dụ, khi bổ sung tìm kiếm có gợi ý:

- Kiểm thử chức năng xác minh gợi ý phù hợp với từ khóa và dữ liệu được phép hiển thị.
- Kiểm thử hiệu năng đánh giá thời gian phản hồi khi dữ liệu lớn hoặc nhiều người dùng đồng thời.
- Kiểm thử bảo mật xác minh người dùng không nhìn thấy dữ liệu ngoài quyền truy cập.
- Thử nghiệm người dùng đánh giá liệu gợi ý có giúp tìm nội dung nhanh hơn hay gây nhiễu.
- Kiểm thử hồi quy xác nhận tìm kiếm hiện tại vẫn hoạt động đúng khi người dùng không bật hoặc không sử dụng gợi ý.

Kết quả kiểm thử cho biết cải tiến đáp ứng các điều kiện đã đặt ra hay chưa. Chỉ số sử dụng sau phát hành mới cho biết lợi ích thực tế có xuất hiện trong môi trường vận hành hay không. Hai loại bằng chứng bổ sung cho nhau.

## 5. So sánh ba loại mục tiêu

| Khía cạnh | Mục tiêu kiểm thử | Mục tiêu sửa lỗi | Mục tiêu cải tiến sản phẩm |
|---|---|---|---|
| Câu hỏi chính | Cần biết điều gì về chất lượng hoặc rủi ro? | Hành vi sai nào cần được khắc phục? | Giá trị hoặc trải nghiệm nào cần được nâng lên? |
| Điểm xuất phát | Yêu cầu, rủi ro, thay đổi, giả định hoặc quyết định cần bằng chứng. | Sai khác giữa hành vi thực tế và hành vi đã cam kết. | Nhu cầu mới, phản hồi, dữ liệu sử dụng hoặc cơ hội sản phẩm. |
| Kết quả trực tiếp | Bằng chứng và thông tin để ra quyết định. | Nguyên nhân được xử lý và hành vi đúng được khôi phục. | Khả năng hoặc trải nghiệm mới được cung cấp. |
| Tiêu chí đánh giá | Phạm vi kiểm tra, độ tin cậy bằng chứng, điều kiện đạt/trượt và rủi ro còn lại. | Lỗi tái hiện đã được khắc phục, hồi quy được kiểm soát. | Giá trị người dùng, chỉ số sản phẩm và các giới hạn chất lượng. |
| Vai trò kiểm thử | Thiết kế và thực hiện kiểm tra, phân tích kết quả, truyền đạt rủi ro. | Tái hiện, kiểm thử lại, hồi quy và cung cấp bằng chứng cho bản sửa. | Xác minh yêu cầu mới, đánh giá chất lượng và hỗ trợ đo lường tác động. |
| Ví dụ | Xác minh tổng tiền đơn hàng được tính đúng theo quy tắc. | Sửa lỗi áp dụng thuế sai cho một loại đơn hàng. | Rút ngắn quy trình thanh toán cho khách hàng quay lại. |

Ba loại mục tiêu có liên hệ nhưng không thay thế cho nhau. Mục tiêu kiểm thử có thể dẫn đến việc tạo lỗi cần sửa hoặc cung cấp bằng chứng rằng một cải tiến đã đạt. Mục tiêu sửa lỗi và cải tiến đều có thể cần nhiều hoạt động kiểm thử để xác nhận kết quả.

## 6. Phân biệt lỗi, yêu cầu cải tiến và rủi ro được chấp nhận

Không phải mọi phản hồi tiêu cực đều là lỗi phần mềm. Một yêu cầu có thể được phân loại khác nhau tùy theo hợp đồng, đặc tả, tiêu chí nghiệm thu và quyết định sản phẩm.

| Tình huống | Cách phân loại có thể phù hợp | Căn cứ cần kiểm tra |
|---|---|---|
| Chức năng trả kết quả khác với yêu cầu đã được phê duyệt. | Lỗi cần điều tra và sửa. | Yêu cầu, tiêu chí nghiệm thu, phiên bản và bước tái hiện. |
| Người dùng muốn thêm một bộ lọc chưa nằm trong phạm vi hiện tại. | Yêu cầu cải tiến hoặc chức năng mới. | Phạm vi sản phẩm, nhu cầu người dùng và ưu tiên roadmap. |
| Hệ thống hoạt động đúng đặc tả nhưng thời gian phản hồi không đạt ngưỡng hiệu năng đã cam kết. | Lỗi chất lượng hoặc vấn đề hiệu năng cần khắc phục. | SLO/SLA, ngưỡng đã thống nhất, môi trường đo và tải đại diện. |
| Hệ thống hoạt động đúng đặc tả nhưng người dùng thấy quy trình có quá nhiều bước. | Cơ hội cải tiến trải nghiệm. | Nghiên cứu người dùng, dữ liệu hành trình và mục tiêu trải nghiệm. |
| Một trường hợp biên có xác suất thấp, tác động hạn chế và chưa có giải pháp kinh tế. | Rủi ro tồn dư có thể được chấp nhận có điều kiện. | Đánh giá rủi ro, người phê duyệt, biện pháp giảm thiểu và thời hạn xem xét. |

Việc phân loại phải dựa trên bằng chứng và thỏa thuận, không dựa vào cách người báo cáo đặt tiêu đề. Nếu chưa rõ hành vi mong đợi, nhóm cần làm rõ yêu cầu với người có thẩm quyền trước khi kết luận đó là lỗi hay cải tiến.

### 6.1. Câu hỏi hỗ trợ phân loại

1. Có yêu cầu, tiêu chí chấp nhận hoặc hợp đồng nào mô tả hành vi mong đợi không?
2. Kết quả hiện tại có vi phạm điều đã cam kết không?
3. Nếu không vi phạm, đề xuất có tạo ra giá trị mới hoặc cải thiện kết quả cho người dùng không?
4. Có bằng chứng tái hiện, dữ liệu vận hành hoặc phản hồi người dùng nào hỗ trợ nhận định không?
5. Ai có thẩm quyền xác nhận phạm vi, ưu tiên và mức rủi ro được chấp nhận?

Nếu câu trả lời chưa đủ rõ, ghi nhận vấn đề ở trạng thái cần làm rõ. Không nên tự đổi một yêu cầu mới thành lỗi chỉ để tăng mức ưu tiên, cũng không nên đổi một lỗi đã vi phạm cam kết thành “cải tiến” để né trách nhiệm khắc phục.

## 7. Liên kết ba mục tiêu trong một quy trình

Một quy trình hiệu quả giúp bằng chứng kiểm thử dẫn đến quyết định phù hợp, rồi xác nhận kết quả của quyết định đó.

~~~mermaid
flowchart TD
    A[Đặt câu hỏi hoặc nhận phản hồi] --> B[Xác định yêu cầu và hành vi mong đợi]
    B --> C[Kiểm thử và thu thập bằng chứng]
    C --> D{Kết quả cho thấy điều gì?}
    D -->|Vi phạm yêu cầu| E[Ghi nhận và ưu tiên lỗi]
    D -->|Đáp ứng yêu cầu, có nhu cầu mới| F[Đánh giá yêu cầu cải tiến]
    D -->|Chưa đủ bằng chứng| G[Làm rõ hoặc kiểm thử bổ sung]
    E --> H[Điều tra và sửa nguyên nhân]
    H --> I[Kiểm thử lại và hồi quy]
    F --> J[Định nghĩa giá trị và tiêu chí cải tiến]
    J --> K[Phát triển thay đổi]
    K --> L[Kiểm thử chức năng và chất lượng]
    I --> M[Đánh giá bằng chứng và rủi ro còn lại]
    L --> M
    G --> C
    M --> N{Đủ điều kiện?}
    N -->|Có| O[Quyết định phát hành hoặc đóng việc]
    N -->|Chưa| P[Tiếp tục xử lý hoặc chấp nhận rủi ro có thẩm quyền]
~~~

Quy trình trên có thể được điều chỉnh theo mô hình phát triển. Trong quy trình Agile, việc phân loại, kiểm thử và phản hồi có thể diễn ra trong từng vòng lặp. Trong quy trình theo giai đoạn, các hoạt động có thể được gom theo mốc nhưng vẫn cần truy vết từ yêu cầu đến bằng chứng và quyết định.

### 7.1. Hồ sơ tối thiểu cần truy vết

Để tránh nhầm lẫn, mỗi hạng mục nên có liên kết đến các thông tin phù hợp:

- Yêu cầu hoặc nguồn phản hồi ban đầu.
- Loại hạng mục: mục tiêu kiểm thử, lỗi, cải tiến hoặc rủi ro cần quyết định.
- Phạm vi, phiên bản, môi trường và mức ưu tiên.
- Tiêu chí mong đợi và bằng chứng hiện có.
- Người chịu trách nhiệm và người ra quyết định khi cần.
- Thay đổi mã nguồn hoặc cấu hình liên quan.
- Kết quả kiểm thử lại, kiểm thử hồi quy hoặc xác nhận cải tiến.
- Trạng thái cuối cùng, rủi ro còn lại và lý do đóng.

Không phải mọi hạng mục đều cần cùng một bộ trường dữ liệu. Ví dụ, một mục tiêu kiểm thử có thể chưa gắn với thay đổi mã nguồn; một cải tiến có thể cần chỉ số sản phẩm sau phát hành; một lỗi cần bước tái hiện và phiên bản bị ảnh hưởng. Điều quan trọng là thông tin đủ để người khác hiểu quyết định và kiểm tra lại bằng chứng.

## 8. Viết mục tiêu rõ ràng và có thể đánh giá

Một mục tiêu nên diễn đạt kết quả cần đạt, phạm vi và cách xác nhận. Tránh câu quá rộng như “kiểm thử kỹ hơn”, “sửa cho ổn định” hoặc “làm sản phẩm tốt hơn”. Các câu này không xác định được điều kiện hoàn thành.

### 8.1. Mẫu mục tiêu kiểm thử

~~~text
[Mục tiêu kiểm thử]
Đối tượng/phạm vi: ...
Khẳng định hoặc thuộc tính cần đánh giá: ...
Rủi ro cần giảm: ...
Bằng chứng sẽ thu thập: ...
Tiêu chí hoàn thành/đạt: ...
Giới hạn và rủi ro còn lại: ...
~~~

Ví dụ: “Đánh giá khả năng xử lý 500 yêu cầu đồng thời của API tra cứu đơn hàng trong môi trường đại diện. Thu thập độ trễ p95, tỷ lệ lỗi và mức sử dụng tài nguyên. Mục tiêu đạt khi độ trễ p95 dưới 800 ms và tỷ lệ lỗi dưới 0,5% trong kịch bản tải đã thống nhất.” Các ngưỡng trong ví dụ chỉ là giả định minh họa; dự án cần đặt ngưỡng theo nhu cầu và cam kết thực tế.

### 8.2. Mẫu mục tiêu sửa lỗi

~~~text
[Mục tiêu sửa lỗi]
Hành vi sai và điều kiện tái hiện: ...
Hành vi đúng theo căn cứ: ...
Nguyên nhân hoặc giả thuyết nguyên nhân: ...
Thay đổi dự kiến: ...
Kiểm thử lại: ...
Phạm vi hồi quy: ...
Điều kiện đóng: ...
~~~

Ví dụ: “Khi người dùng gửi biểu mẫu hai lần do kết nối chậm, hệ thống tạo hai yêu cầu trùng. Bảo đảm cùng một mã yêu cầu chỉ tạo một bản ghi nghiệp vụ, kiểm thử lại kịch bản gửi lặp và kiểm tra hồi quy các luồng gửi biểu mẫu bình thường.”

### 8.3. Mẫu mục tiêu cải tiến

~~~text
[Mục tiêu cải tiến sản phẩm]
Người dùng/nhu cầu: ...
Giá trị mong đợi: ...
Phạm vi thay đổi: ...
Chỉ số hiện tại và mục tiêu: ...
Giới hạn chất lượng phải giữ: ...
Cách xác nhận trước phát hành: ...
Cách đánh giá sau phát hành: ...
~~~

Ví dụ: “Giúp nhân viên hỗ trợ tìm hồ sơ khách hàng nhanh hơn bằng bộ lọc theo trạng thái và ngày cập nhật. Mục tiêu là giảm thời gian tìm hồ sơ trung vị 20% trong thử nghiệm có kiểm soát, không làm lộ hồ sơ ngoài quyền truy cập và không làm tăng lỗi truy vấn.”

## 9. Chọn chỉ số phù hợp với từng mục tiêu

Chỉ số phải phản ánh điều mà mục tiêu muốn đạt. Không dùng một chỉ số cho cả ba loại mục tiêu nếu ý nghĩa của nó khác nhau.

| Loại mục tiêu | Chỉ số hoặc bằng chứng phù hợp | Chỉ số dễ bị hiểu sai nếu dùng riêng lẻ |
|---|---|---|
| Kiểm thử | Tỷ lệ yêu cầu/rủi ro có bằng chứng; kết quả đạt/trượt; độ ổn định của kiểm thử; thời gian phản hồi; lỗi phát hiện theo mức độ. | Tổng số test case hoặc tỷ lệ pass mà không xét phạm vi và chất lượng kiểm tra. |
| Sửa lỗi | Tỷ lệ lỗi tái mở; thời gian khắc phục theo mức độ; lỗi tái diễn cùng nguyên nhân; kết quả retest và regression. | Số lỗi đóng hoặc số dòng mã thay đổi. |
| Cải tiến sản phẩm | Tỷ lệ hoàn thành tác vụ; thời gian thực hiện; mức sử dụng; tỷ lệ chuyển đổi; phản hồi hài lòng; chi phí hoặc hiệu quả vận hành. | Số tính năng phát hành hoặc số người nhấp vào tính năng mà không đo giá trị thực tế. |

Một số lưu ý khi đo lường:

- Xác định cách tính, nguồn dữ liệu, khoảng thời gian và nhóm người dùng trước khi so sánh.
- Dùng đường cơ sở (baseline) khi cần đánh giá mức cải thiện.
- Theo dõi chỉ số bảo vệ (guardrail), chẳng hạn tỷ lệ lỗi, khi tối ưu tốc độ hoặc chuyển đổi.
- Phân tách số liệu theo phiên bản, nền tảng hoặc nhóm người dùng nếu tổng số che khuất vấn đề.
- Không khuyến khích hành vi chạy theo chỉ số. Ví dụ, mục tiêu giảm số lỗi báo cáo có thể khiến nhóm đóng lỗi quá sớm hoặc không ghi nhận lỗi khó tái hiện.

## 10. Ví dụ xuyên suốt: cải thiện quy trình thanh toán

Giả sử một cửa hàng trực tuyến nhận phản hồi rằng một số đơn hàng hiển thị tổng tiền không nhất quán sau khi áp dụng mã giảm giá.

**Giai đoạn 1 — Mục tiêu kiểm thử:** Nhóm kiểm thử xác minh cách hệ thống tính giá sản phẩm, giảm giá, thuế, phí vận chuyển và tổng thanh toán theo các quy tắc nghiệp vụ đã phê duyệt. Bộ dữ liệu bao gồm đơn hàng thường, đơn có sản phẩm miễn thuế, mã giảm giá theo phần trăm, mã giảm giá cố định và trường hợp giá trị đơn hàng bằng ngưỡng áp dụng. Mục tiêu là xác định điều kiện nào tạo ra sai khác và cung cấp bằng chứng có thể tái hiện.

**Giai đoạn 2 — Mục tiêu sửa lỗi:** Kết quả cho thấy hệ thống áp dụng thứ tự tính giảm giá và thuế không đúng với một loại đơn hàng. Nhóm sửa quy tắc tính, kiểm thử lại dữ liệu đã tái hiện lỗi và chạy hồi quy các trường hợp đơn hàng liên quan. Tiêu chí đóng là tổng tiền và dữ liệu hóa đơn nhất quán với quy tắc đã phê duyệt, không xuất hiện sai lệch ở các trường hợp hồi quy.

**Giai đoạn 3 — Mục tiêu cải tiến sản phẩm:** Qua phân tích hành trình, nhóm phát hiện người dùng thường phải quay lại trang giỏ hàng để kiểm tra tác động của mã giảm giá. Nhóm đề xuất cập nhật tổng tiền theo thời gian thực và giải thích rõ khoản giảm giá. Đây là cải tiến trải nghiệm nếu hành vi cũ vẫn đáp ứng yêu cầu đã cam kết. Mục tiêu cải tiến có thể là tăng tỷ lệ người dùng hiểu đúng tổng tiền trước khi xác nhận, đồng thời không làm tăng độ trễ hoặc giao dịch lỗi.

**Giai đoạn 4 — Kiểm thử cải tiến:** Nhóm kiểm tra tính đúng của số tiền cập nhật, trạng thái khi mã không hợp lệ, khả năng đồng bộ giữa giỏ hàng và bước thanh toán, hiệu năng khi cập nhật nhiều lần, khả năng truy cập và các luồng hồi quy. Sau phát hành, nhóm theo dõi tỷ lệ hoàn tất thanh toán, tỷ lệ bỏ giỏ và phản hồi hỗ trợ để đánh giá lợi ích.

Ví dụ này cho thấy một phát hiện có thể mở ra nhiều loại công việc, nhưng mỗi công việc vẫn cần mục tiêu và tiêu chí riêng. Việc sửa phép tính là khôi phục cam kết; việc hiển thị thông tin rõ hơn là tạo giá trị mới; kiểm thử là cung cấp bằng chứng cho cả hai.

## 11. Những nhầm lẫn thường gặp

- **Coi “tìm được nhiều lỗi” là mục tiêu duy nhất của kiểm thử:** kiểm thử còn đánh giá yêu cầu, thuộc tính chất lượng và rủi ro để hỗ trợ quyết định. Một vòng kiểm thử không phát hiện lỗi vẫn có thể cung cấp bằng chứng hữu ích nếu phạm vi và phương pháp phù hợp.
- **Cho rằng kiểm thử viên chịu trách nhiệm sửa mọi lỗi:** kiểm thử viên có trách nhiệm mô tả và cung cấp bằng chứng; việc điều tra, sửa và quyết định ưu tiên cần sự phối hợp của các vai trò liên quan.
- **Đóng lỗi ngay khi mã đã thay đổi:** cần kiểm thử lại và hồi quy phù hợp trước khi kết luận hành vi đã được khôi phục.
- **Gọi mọi mong muốn mới là lỗi:** phải so sánh với yêu cầu và phạm vi đã cam kết. Nhu cầu mới thường thuộc backlog cải tiến.
- **Đồng nhất cải tiến với thêm chức năng:** cải tiến cũng có thể là giảm độ trễ, tăng khả năng truy cập, giảm bước thao tác hoặc giảm chi phí vận hành.
- **Dùng tỷ lệ pass làm bằng chứng duy nhất:** tỷ lệ pass không cho biết trường hợp quan trọng nào chưa được kiểm tra, dữ liệu có đại diện không hoặc test có đáng tin cậy không.
- **Đo cải tiến bằng số tính năng phát hành:** cần xem người dùng có đạt kết quả tốt hơn và các chỉ số bảo vệ có được duy trì không.
- **Bỏ qua rủi ro tồn dư:** không phải mọi vấn đề đều được xử lý ngay; nếu chấp nhận rủi ro, cần người có thẩm quyền, căn cứ, biện pháp giảm thiểu và thời hạn xem xét.

## 12. Checklist rà soát mục tiêu

Trước khi bắt đầu công việc, hãy tự kiểm tra:

- [ ] Mục tiêu được xác định rõ là thu thập bằng chứng, khắc phục sai lệch hay tạo giá trị mới.
- [ ] Yêu cầu, hành vi mong đợi hoặc nhu cầu người dùng có nguồn căn cứ rõ ràng.
- [ ] Phạm vi, phiên bản, đối tượng và rủi ro liên quan đã được nêu.
- [ ] Tiêu chí hoàn thành phù hợp với loại mục tiêu.
- [ ] Bằng chứng và chỉ số cần thu thập đã được xác định trước.
- [ ] Có người chịu trách nhiệm và người có thẩm quyền quyết định khi cần.
- [ ] Với bản sửa, đã xác định trường hợp kiểm thử lại và phạm vi hồi quy.
- [ ] Với cải tiến, đã xác định giá trị mong đợi, đường cơ sở và chỉ số bảo vệ.
- [ ] Rủi ro còn lại và ngoại lệ được ghi nhận, phê duyệt và có kế hoạch xem xét.

## Kết luận

Mục tiêu kiểm thử là tạo bằng chứng để hiểu chất lượng và rủi ro; mục tiêu sửa lỗi là khôi phục hành vi đúng theo cam kết; mục tiêu cải tiến sản phẩm là tạo thêm giá trị cho người dùng hoặc tổ chức. Ba mục tiêu hỗ trợ lẫn nhau nhưng cần tiêu chí hoàn thành riêng. Khi xác định đúng loại mục tiêu, nhóm có thể chọn hoạt động, bằng chứng, chỉ số và quyết định phù hợp, đồng thời truy vết rõ từ vấn đề ban đầu đến kết quả cuối cùng.
