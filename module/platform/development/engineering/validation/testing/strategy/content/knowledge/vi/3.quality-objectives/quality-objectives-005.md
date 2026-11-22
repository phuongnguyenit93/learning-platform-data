# Phân biệt mức chất lượng mong muốn với ngưỡng chấp nhận tối thiểu

Khi xây dựng chiến lược kiểm thử trong phạm vi `VALIDATION_TESTING_STRATEGY`, nhóm cần thống nhất hai mức cho mỗi thuộc tính chất lượng quan trọng: **mức chất lượng mong muốn** (quality target) và **ngưỡng chấp nhận tối thiểu** (minimum acceptable threshold). Hai mức này giúp trả lời hai câu hỏi khác nhau: sản phẩm nên đạt chất lượng đến đâu để đáp ứng kỳ vọng, và chất lượng thấp đến mức nào thì không thể chấp nhận để phát hành hoặc tiếp tục vận hành.

Nếu chỉ đặt một con số mà không phân biệt hai ý nghĩa, nhóm dễ nhầm giữa mục tiêu cải thiện và điều kiện bắt buộc. Khi đó, một kết quả chưa đạt kỳ vọng có thể bị coi là thất bại nghiêm trọng dù vẫn nằm trong giới hạn chấp nhận; ngược lại, một kết quả vừa đủ qua ngưỡng có thể bị tuyên bố là thành công dù còn xa mức chất lượng người dùng cần.

## 1. Hai mức chất lượng có ý nghĩa gì?

### Mức chất lượng mong muốn — quality target

Mức chất lượng mong muốn mô tả trạng thái mà sản phẩm hoặc dịch vụ hướng tới trong điều kiện vận hành đã xác định. Đây là căn cứ để thiết kế giải pháp, lập kế hoạch nguồn lực, lựa chọn phương pháp kiểm thử và đánh giá mức độ đạt được kỳ vọng.

Ví dụ, nhóm đặt mục tiêu 95% yêu cầu tìm kiếm có thời gian phản hồi không quá 300 ms ở tải dự kiến. Mục tiêu này định hướng thiết kế chỉ mục, bộ nhớ đệm, truy vấn và kiểm thử hiệu năng. Nó cũng tạo cơ sở để nhóm theo dõi xem các lần cải tiến có đưa hệ thống gần hơn đến trải nghiệm mong muốn hay không.

Quality target phải có thể đo lường hoặc đánh giá bằng tiêu chí rõ ràng. Những phát biểu như “nhanh”, “dễ dùng”, “ổn định” hoặc “bảo mật cao” chưa phải mục tiêu chất lượng đầy đủ nếu chưa nêu cách xác định chúng đạt hay chưa đạt.

Trong một số dự án, target cũng là cam kết hợp đồng hoặc điều kiện phát hành bắt buộc. Trong trường hợp đó, tài liệu phải ghi rõ target là release gate. Không nên mặc định rằng mọi target chỉ mang tính khuyến khích; ý nghĩa bắt buộc hay định hướng cần được các bên liên quan thống nhất.

### Ngưỡng chấp nhận tối thiểu — minimum acceptable threshold

Ngưỡng chấp nhận tối thiểu xác định ranh giới chất lượng thấp nhất mà tổ chức, khách hàng hoặc người dùng vẫn có thể chấp nhận trong một phạm vi và điều kiện cụ thể. Nếu kết quả vượt qua ranh giới theo hướng xấu, sản phẩm không đáp ứng điều kiện chấp nhận đã thống nhất.

Ví dụ, thời gian phản hồi p95 không được vượt quá 500 ms ở tải dự kiến. Nếu kết quả đo là 650 ms, hệ thống đã vi phạm ngưỡng tối thiểu, dù phần lớn yêu cầu có thể vẫn phản hồi nhanh hơn.

“Tối thiểu” ở đây nói đến mức chất lượng thấp nhất có thể chấp nhận, không có nghĩa mọi chỉ số đều dùng dấu nhỏ hơn. Với chỉ số càng cao càng tốt như tỷ lệ sẵn sàng, ngưỡng tối thiểu là một giới hạn dưới. Với chỉ số càng thấp càng tốt như độ trễ hoặc tỷ lệ lỗi, ngưỡng chấp nhận là một giới hạn trên. Với chỉ số có khoảng giá trị hợp lệ, cần xác định cả hai biên.

Ngưỡng này thường gắn với rủi ro đối với người dùng, nghĩa vụ hợp đồng, quy định, an toàn, bảo mật hoặc khả năng duy trì hoạt động. Một số rủi ro không cho phép thỏa hiệp; khi đó target và ngưỡng tối thiểu có thể trùng nhau, chẳng hạn không chấp nhận lỗ hổng bảo mật mức nghiêm trọng theo chính sách đã thống nhất.

## 2. So sánh target và ngưỡng tối thiểu

| Khía cạnh | Mức chất lượng mong muốn | Ngưỡng chấp nhận tối thiểu |
|---|---|---|
| Câu hỏi | Chúng ta muốn sản phẩm đạt mức nào? | Mức thấp nhất nào vẫn có thể chấp nhận? |
| Vai trò | Định hướng thiết kế, đầu tư và cải tiến | Đặt ranh giới đạt/không đạt và kiểm soát rủi ro |
| Cơ sở xác định | Kỳ vọng người dùng, mục tiêu sản phẩm, năng lực kỹ thuật, định hướng cạnh tranh | Tác động nếu chất lượng suy giảm, hợp đồng, quy định, an toàn và mức chịu đựng rủi ro |
| Cách sử dụng | Lập kế hoạch, đặt ưu tiên, đánh giá khoảng cách và xu hướng | Tiêu chí chấp nhận, cổng phát hành, cảnh báo và quy trình ứng phó |
| Khi chưa đạt | Xác định khoảng cách, nguyên nhân và kế hoạch cải thiện; xử lý theo chính sách nếu target là điều kiện bắt buộc | Không chấp nhận kết quả theo quy tắc đã thống nhất; cần khắc phục hoặc có quyết định ngoại lệ đúng thẩm quyền |
| Quan hệ | Thường tốt hơn ngưỡng tối thiểu theo chiều chất lượng mong muốn | Là ranh giới dưới hoặc trên tùy hướng đo của chỉ số |

Ví dụ với độ trễ, target 300 ms và ngưỡng tối đa chấp nhận 500 ms có nghĩa là nhóm mong muốn đạt 300 ms hoặc thấp hơn, đồng thời không được để kết quả vượt quá 500 ms. Với độ sẵn sàng, target 99,95% và ngưỡng tối thiểu 99,9% có nghĩa là nhóm hướng đến 99,95% hoặc cao hơn, còn mức dưới 99,9% là không thể chấp nhận.

Khoảng giữa target và ngưỡng là vùng chất lượng có thể chấp nhận nhưng chưa đạt mức mong muốn. Đây là vùng cần được nhìn nhận minh bạch: sản phẩm có thể đáp ứng điều kiện tối thiểu, nhưng nhóm vẫn còn khoảng cách cần theo dõi hoặc cải thiện.

## 3. Biểu diễn đúng chiều của ngưỡng

Không nên viết một cặp số mà không giải thích chiều tốt/xấu. Cùng một con số có thể mang ý nghĩa hoàn toàn khác tùy chỉ số.

| Thuộc tính | Chiều chất lượng tốt hơn | Target minh họa | Ngưỡng tối thiểu minh họa |
|---|---|---:|---:|
| Độ trễ p95 | Thấp hơn | ≤ 300 ms | ≤ 500 ms |
| Tỷ lệ sẵn sàng theo tháng | Cao hơn | ≥ 99,95% | ≥ 99,9% |
| Tỷ lệ giao dịch lỗi | Thấp hơn | ≤ 0,1% | ≤ 0,5% |
| Tỷ lệ hoàn thành tác vụ chính | Cao hơn | ≥ 95% | ≥ 90% |
| Thời gian khôi phục dịch vụ (MTTR) | Thấp hơn | ≤ 30 phút | ≤ 60 phút |
| Thời gian mất dữ liệu tối đa có thể chấp nhận (RPO) | Thấp hơn | 0 phút | ≤ 5 phút |

Các con số trong bảng chỉ minh họa cách diễn đạt, không phải chuẩn áp dụng chung cho mọi hệ thống. Mức phù hợp phải được xác định theo người dùng, kiến trúc, tải, mức độ quan trọng, nghĩa vụ và rủi ro của sản phẩm.

Một số chỉ số cần một khoảng thay vì một giới hạn đơn. Ví dụ, mức sử dụng bộ nhớ có thể phải nằm trong khoảng đủ thấp để tránh thiếu bộ nhớ nhưng cũng đủ cao để không gây lãng phí tài nguyên. Khi đó cần ghi rõ khoảng mục tiêu, khoảng chấp nhận và cách xử lý khi vượt từng biên.

## 4. Ví dụ xuyên suốt: chất lượng của API đặt hàng

Giả sử một nền tảng thương mại điện tử cung cấp API tạo đơn hàng cho ứng dụng web và ứng dụng di động. Người dùng cần gửi đơn nhanh, không bị mất yêu cầu và không tạo đơn trùng khi mạng chập chờn. Nhóm xác định một số thuộc tính chất lượng và thống nhất target cùng ngưỡng chấp nhận như sau:

| Thuộc tính | Target | Ngưỡng chấp nhận tối thiểu | Ý nghĩa |
|---|---|---|---|
| Độ trễ p95 ở tải dự kiến | ≤ 300 ms | ≤ 500 ms | Mong muốn phần lớn yêu cầu nhanh; trên 500 ms là vượt giới hạn |
| Độ sẵn sàng hàng tháng | ≥ 99,95% | ≥ 99,9% | Hướng tới thời gian hoạt động cao hơn mức thấp nhất cam kết |
| Tỷ lệ tạo đơn lỗi do hệ thống | ≤ 0,1% | ≤ 0,5% | Giảm giao dịch thất bại; vượt 0,5% cần xử lý |
| Tạo đơn trùng do gửi lại cùng yêu cầu | 0 trường hợp | 0 trường hợp | Không cho phép sai lệch vì có thể gây thu tiền hoặc xử lý đơn nhiều lần |

Giả sử bài kiểm thử tải cho thấy p95 là 420 ms, độ sẵn sàng trong kỳ đo là 99,93%, tỷ lệ tạo đơn lỗi là 0,2% và không phát hiện đơn trùng.

- Độ trễ đã đạt ngưỡng chấp nhận 500 ms nhưng chưa đạt target 300 ms. Đây là khoảng cách hiệu năng cần phân tích và có kế hoạch cải thiện.
- Độ sẵn sàng 99,93% đạt ngưỡng tối thiểu 99,9% nhưng chưa đạt target 99,95%. Nhóm cần xem xét xu hướng sự cố và biên dự phòng.
- Tỷ lệ tạo đơn lỗi 0,2% nằm trong giới hạn tối thiểu 0,5% nhưng vẫn cao hơn mức mong muốn 0,1%.
- Tạo đơn trùng có ngưỡng bằng 0; nếu xuất hiện dù chỉ một trường hợp hợp lệ trong phạm vi đo, kết quả không đạt tiêu chí này.

Không thể chỉ dựa vào việc “đa số chỉ số nằm trong ngưỡng” để kết luận phát hành. Nhóm phải xét các tiêu chí bắt buộc, mức độ nghiêm trọng, độ tin cậy của phép đo, phạm vi thử nghiệm và chính sách release gate. Nếu tạo đơn trùng là rủi ro không thể chấp nhận, các chỉ số hiệu năng tốt không bù được lỗi đó.

## 5. Cách xác định hai mức chất lượng

### Bắt đầu từ nhu cầu và hậu quả

Với mỗi thuộc tính chất lượng, hãy xác định ai bị ảnh hưởng nếu chất lượng giảm và họ sẽ gặp hậu quả gì. Ví dụ, độ trễ cao có thể chỉ gây khó chịu ở màn hình tra cứu nội bộ, nhưng có thể làm hỏng trải nghiệm thanh toán nếu người dùng không biết giao dịch đã được ghi nhận hay chưa. Cùng một chỉ số vì thế có thể cần ngưỡng khác nhau ở các bối cảnh khác nhau.

Nên xem xét:

- Công việc chính mà người dùng cần hoàn thành và mức gián đoạn có thể chấp nhận.
- Tác động tài chính, dữ liệu, an toàn, bảo mật, tuân thủ và uy tín nếu xảy ra lỗi.
- Cam kết với khách hàng, đối tác, nhà cung cấp và các nhóm vận hành.
- Điều kiện môi trường: lưu lượng, dữ liệu, thiết bị, mạng, khu vực địa lý và thời điểm cao điểm.
- Khả năng phát hiện, khôi phục và giảm thiểu tác động khi chất lượng suy giảm.

### Xác định ngưỡng tối thiểu từ rủi ro

Ngưỡng tối thiểu nên phản ánh mức rủi ro mà tổ chức sẵn sàng chấp nhận. Có thể sử dụng yêu cầu pháp lý, hợp đồng, chính sách nội bộ, phân tích tác động nghiệp vụ, dữ liệu sự cố và ý kiến của người chịu trách nhiệm về rủi ro.

Với thuộc tính có hậu quả nghiêm trọng, ngưỡng cần chặt chẽ và có thể không có vùng thỏa hiệp. Ví dụ, nếu chính sách yêu cầu không có lỗ hổng mức nghiêm trọng đã biết trước khi phát hành, ngưỡng chấp nhận là không có lỗ hổng thuộc phạm vi đó. Không được tự nới ngưỡng chỉ vì việc khắc phục khó hoặc tốn kém.

### Xác định target từ kỳ vọng và khả năng thực hiện

Target nên thể hiện trải nghiệm hoặc năng lực mà sản phẩm muốn cung cấp, đồng thời phải được hỗ trợ bởi kế hoạch kỹ thuật và nguồn lực thực tế. Có thể dùng dữ liệu baseline, nghiên cứu người dùng, hệ thống tham chiếu, thử nghiệm prototype, mô hình tải và các vòng đo thử để chọn mục tiêu.

Target cần đủ tham vọng để tạo hướng cải tiến, nhưng cũng cần có cơ sở. Nếu target không thể đạt với kiến trúc, ngân sách hoặc thời hạn hiện tại, hãy ghi nhận khoảng cách và quyết định đầu tư, điều chỉnh phạm vi hoặc điều chỉnh mục tiêu qua quy trình phê duyệt. Không nên âm thầm hạ target hay thay đổi ngưỡng tối thiểu sau khi thấy kết quả kiểm thử.

### Kiểm tra tính nhất quán

Với chỉ số càng cao càng tốt, target thông thường phải lớn hơn hoặc bằng ngưỡng tối thiểu. Với chỉ số càng thấp càng tốt, target thông thường phải nhỏ hơn hoặc bằng giới hạn tối đa chấp nhận. Nếu các giá trị không theo quan hệ này, cần kiểm tra lại định nghĩa, đơn vị, chiều đo hoặc giả định.

Có trường hợp target trùng với ngưỡng tối thiểu vì không có mức suy giảm nào được phép. Cũng có trường hợp một target là mục tiêu dài hạn, còn ngưỡng tối thiểu là điều kiện ngắn hạn để vận hành an toàn. Cần ghi rõ thời hạn và phạm vi áp dụng để tránh so sánh sai.

## 6. Viết mục tiêu chất lượng sao cho kiểm thử được

Một mục tiêu chất lượng có thể được mô tả bằng các thành phần sau:

1. **Thuộc tính chất lượng:** hiệu năng, độ tin cậy, khả năng sử dụng, bảo mật, khả năng tiếp cận, tương thích, khả năng phục hồi hoặc tính toàn vẹn dữ liệu.
2. **Chỉ số:** đại lượng quan sát được, cách tính và đơn vị.
3. **Điều kiện đo:** môi trường, tải, dữ liệu, thiết bị, khu vực, vai trò người dùng và cấu hình.
4. **Cửa sổ đo và phạm vi mẫu:** đo trong bao lâu, trên bao nhiêu yêu cầu hoặc phiên sử dụng, loại trừ những trường hợp nào.
5. **Target:** mức mong muốn cùng chiều so sánh.
6. **Ngưỡng chấp nhận:** ranh giới đạt/không đạt và cách xử lý khi vi phạm.
7. **Nguồn bằng chứng:** công cụ đo, log, dashboard, kết quả test, khảo sát hoặc biên bản xác nhận.
8. **Chủ sở hữu và thời điểm xem xét:** người chịu trách nhiệm, thời điểm đánh giá và quy trình phê duyệt thay đổi.

Ví dụ một yêu cầu hiệu năng được viết rõ:

> Trong môi trường staging có cấu hình tương đương production, với 1.000 phiên hoạt động đồng thời và tập dữ liệu đại diện, p95 của thời gian phản hồi API tra cứu sản phẩm trong cửa sổ đo 30 phút có target không quá 300 ms và ngưỡng chấp nhận không quá 500 ms. Kết quả được lấy từ bộ đo tải đã thống nhất; các lỗi hệ thống được tính riêng vào tỷ lệ lỗi và không bị loại khỏi mẫu độ trễ nếu chính sách đo quy định chúng là yêu cầu thất bại.

Ví dụ này xác định được chỉ số, môi trường, tải, dữ liệu, thời gian, target và ngưỡng. Nhóm vẫn cần thống nhất cách tạo tải, số lần lặp, cách xử lý warm-up và cách lưu bằng chứng để kết quả có thể tái lập.

### Tránh các mô tả mơ hồ

| Mô tả chưa đủ | Cần làm rõ |
|---|---|
| Hệ thống phải nhanh | Chỉ số độ trễ nào, phân vị nào, ở tải và môi trường nào, target và giới hạn bao nhiêu? |
| Dịch vụ phải luôn sẵn sàng | Tỷ lệ sẵn sàng tính theo kỳ nào, thành phần nào, cách tính downtime và bảo trì ra sao? |
| Giao diện phải dễ sử dụng | Ai thực hiện tác vụ nào, tỷ lệ hoàn thành và thời gian mục tiêu là bao nhiêu, có cần hỗ trợ không? |
| Không được mất dữ liệu | Loại dữ liệu nào, mức mất tối đa (RPO), thời gian khôi phục (RTO), tình huống lỗi nào được kiểm tra? |
| Phải an toàn | Mô hình đe dọa, phạm vi kiểm tra, mức độ lỗ hổng và tiêu chí chấp nhận nào được áp dụng? |

## 7. Dùng target và ngưỡng trong chiến lược kiểm thử

### Thiết kế kiểm thử để đánh giá cả hai mức

Kế hoạch kiểm thử cần chỉ ra cách chứng minh target và cách phát hiện việc vi phạm ngưỡng. Với hiệu năng, có thể kiểm tra tải thông thường, tải cao điểm, tải kéo dài và tình huống suy giảm tài nguyên. Với độ tin cậy, cần kiểm tra lỗi phụ thuộc, mất kết nối, khởi động lại và phục hồi. Với khả năng sử dụng, cần thử nghiệm tác vụ trên nhóm người dùng đại diện và đo kết quả theo tiêu chí đã định nghĩa.

Không nên chỉ kiểm tra một điểm tải hoặc một lần chạy. Kết quả có thể dao động theo môi trường, dữ liệu và thời điểm. Hãy quy định số lần lặp, độ dài phép đo, phân vị, khoảng tin cậy hoặc quy tắc tổng hợp phù hợp với rủi ro. Một phép đo ngắn không đại diện cho mục tiêu độ sẵn sàng hàng tháng.

### Phân biệt ba trạng thái kết quả

| Kết quả | Diễn giải | Hành động điển hình |
|---|---|---|
| Đạt target | Đạt mức mong muốn và đồng thời nằm trong ngưỡng chấp nhận | Ghi nhận bằng chứng, tiếp tục theo dõi và xác nhận các thuộc tính khác |
| Đạt ngưỡng nhưng chưa đạt target | Chất lượng vẫn nằm trong vùng chấp nhận nhưng còn khoảng cách so với kỳ vọng | Phân tích nguyên nhân, đánh giá rủi ro, lập kế hoạch cải thiện và quyết định theo chính sách phát hành |
| Vi phạm ngưỡng | Chất lượng đã vượt ranh giới chấp nhận theo hướng xấu | Khắc phục, kiểm thử lại hoặc dừng phát hành; chỉ xem xét ngoại lệ khi quy trình và thẩm quyền cho phép |

Nếu không đủ dữ liệu hoặc phép đo không hợp lệ, kết quả phải được xem là chưa xác định. Không được tự coi thiếu bằng chứng là đạt ngưỡng.

### Đưa kết quả vào quyết định phát hành

Trước khi phát hành, nhóm cần phân loại rõ tiêu chí nào là release gate, tiêu chí nào là mục tiêu theo dõi hoặc cải thiện. Một chính sách có thể quy định mọi ngưỡng tối thiểu là điều kiện bắt buộc, còn target là mục tiêu cần đạt hoặc là điều kiện bắt buộc đối với một số thuộc tính quan trọng. Quy tắc này phải được thống nhất trước khi đánh giá kết quả.

Khi một thuộc tính vi phạm ngưỡng, cần ghi nhận mức ảnh hưởng, nguyên nhân, biện pháp giảm thiểu, người chấp thuận ngoại lệ và thời hạn xử lý nếu chính sách cho phép chấp nhận rủi ro. Ngoại lệ không tự động biến kết quả không đạt thành đạt; đó là một quyết định rủi ro có chủ đích và phải truy vết được.

Khi đạt ngưỡng nhưng chưa đạt target, quyết định phát hành cần dựa trên mức độ quan trọng của target, xu hướng đo, biên dự phòng, tác động người dùng và kế hoạch cải thiện. Không nên che giấu khoảng cách bằng cách chỉ báo cáo trạng thái “pass”.

## 8. Theo dõi sau phát hành và quản lý thay đổi

Kết quả kiểm thử trước phát hành chỉ phản ánh điều kiện đã đo. Khi tải, dữ liệu, hành vi người dùng hoặc phụ thuộc bên ngoài thay đổi, chất lượng thực tế có thể khác. Vì vậy, target và ngưỡng cần được đưa vào giám sát vận hành bằng metric, log, trace, báo cáo hỗ trợ hoặc khảo sát phù hợp.

Nên thiết lập cảnh báo theo hai mức nếu có ích:

- Cảnh báo sớm khi kết quả rời xa target hoặc xu hướng đang xấu đi, để nhóm chủ động điều tra trước khi vi phạm ngưỡng.
- Cảnh báo nghiêm trọng khi chạm hoặc vi phạm ngưỡng tối thiểu, kích hoạt quy trình ứng phó, giảm tải, khôi phục hoặc thông báo theo chính sách.

Không phải mọi chỉ số đều phù hợp với cùng một kiểu cảnh báo. Ví dụ, độ trễ có thể cảnh báo theo cửa sổ ngắn và phân vị; độ sẵn sàng cần cửa sổ đo đủ dài; lỗ hổng bảo mật nghiêm trọng có thể cần xử lý ngay khi được xác nhận.

Khi thay đổi target hoặc ngưỡng, cần ghi lại lý do, dữ liệu hỗ trợ, tác động đến người dùng, phạm vi áp dụng, ngày hiệu lực và người phê duyệt. Nếu thay đổi làm giảm mức bảo vệ, phải đánh giá lại rủi ro và các cam kết liên quan. Không được sửa định nghĩa hoặc cửa sổ đo chỉ để làm cho báo cáo trông đạt yêu cầu.

## 9. Những sai lầm thường gặp

**Dùng một con số cho cả target và ngưỡng mà không nêu ý nghĩa.** Người đọc không biết đó là mức kỳ vọng hay ranh giới bắt buộc. Hãy ghi riêng hai trường và nêu rõ chính sách release gate.

**Coi mọi target là tùy chọn.** Một số target là cam kết hợp đồng hoặc điều kiện phát hành. Cần đánh dấu rõ mức bắt buộc thay vì dựa vào cách hiểu của từng nhóm.

**Coi chỉ cần đạt ngưỡng là hoàn thành mục tiêu chất lượng.** Đạt ngưỡng có nghĩa là chưa vượt giới hạn không thể chấp nhận; điều đó không chứng minh sản phẩm đã đạt trải nghiệm mong muốn. Vẫn cần theo dõi khoảng cách đến target.

**Đặt ngưỡng theo khả năng hiện tại của hệ thống.** Nếu lấy điểm yếu hiện tại làm chuẩn, nhóm có thể hợp thức hóa chất lượng thấp. Ngưỡng phải xuất phát từ rủi ro và nhu cầu chấp nhận được, còn năng lực hiện tại được dùng để lập kế hoạch khắc phục.

**Chọn con số không có điều kiện đo.** Một chỉ số không nêu tải, môi trường, cửa sổ đo hoặc cách tính sẽ khó tái lập và dễ bị diễn giải khác nhau. Hãy mô tả điều kiện đo cùng với giá trị.

**Chỉ nhìn giá trị trung bình.** Trung bình có thể che giấu một nhóm nhỏ người dùng chịu độ trễ rất cao hoặc lỗi nghiêm trọng. Chọn phân vị, tỷ lệ, phân nhóm và cỡ mẫu phù hợp với trải nghiệm cần bảo vệ.

**Nới ngưỡng sau khi test thất bại mà không đánh giá rủi ro.** Việc thay đổi có thể làm mất ý nghĩa của tiêu chí và vi phạm cam kết. Mọi điều chỉnh phải có bằng chứng và phê duyệt đúng thẩm quyền.

**Bỏ qua các thuộc tính có ngưỡng không thỏa hiệp.** Với an toàn, bảo mật, tính toàn vẹn dữ liệu hoặc nghĩa vụ tuân thủ, một vi phạm nghiêm trọng có thể là điều kiện dừng phát hành dù các chỉ số khác đều tốt.

## 10. Checklist xây dựng và sử dụng mục tiêu chất lượng

Khi xác định mục tiêu:

- [ ] Đã xác định thuộc tính chất lượng và người dùng hoặc hoạt động chịu ảnh hưởng.
- [ ] Đã phân tích hậu quả nếu chất lượng giảm và cơ sở đặt ngưỡng tối thiểu.
- [ ] Đã xác định target dựa trên kỳ vọng, baseline và khả năng thực hiện.
- [ ] Đã làm rõ chiều tốt/xấu, đơn vị, cách tính và quan hệ giữa target với ngưỡng.
- [ ] Đã ghi rõ target nào là cam kết hoặc release gate.

Khi viết yêu cầu và kiểm thử:

- [ ] Điều kiện môi trường, tải, dữ liệu, thiết bị và vai trò người dùng đã được nêu.
- [ ] Cửa sổ đo, cỡ mẫu, phân vị và quy tắc tổng hợp đủ rõ để tái lập.
- [ ] Có phương pháp thu thập bằng chứng cho cả target và ngưỡng tối thiểu.
- [ ] Có tiêu chí xử lý khi đạt target, chỉ đạt ngưỡng, vi phạm ngưỡng hoặc thiếu dữ liệu.
- [ ] Các tiêu chí không thỏa hiệp được nhận diện riêng.

Khi phát hành và vận hành:

- [ ] Kết quả được báo cáo cùng điều kiện đo và giới hạn của bằng chứng.
- [ ] Khoảng cách đến target được ghi nhận dù ngưỡng tối thiểu đã đạt.
- [ ] Vi phạm ngưỡng có người chịu trách nhiệm, hành động khắc phục và quyết định phù hợp.
- [ ] Có giám sát và cảnh báo theo mức độ rủi ro.
- [ ] Mọi thay đổi target hoặc ngưỡng đều có lý do, phạm vi và phê duyệt.

## 11. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một dịch vụ đặt target độ trễ p95 không quá 250 ms và ngưỡng chấp nhận không quá 400 ms. Kết quả là 320 ms. Kết luận đúng là dịch vụ đạt ngưỡng nhưng chưa đạt target. Nhóm cần xem xét khoảng cách hiệu năng và chính sách phát hành; không nên báo cáo rằng đã đạt target.

**Tình huống 2:** Một ứng dụng đặt target tỷ lệ hoàn thành tác vụ là ít nhất 96% và ngưỡng tối thiểu là 90%. Kết quả thử nghiệm là 88%. Vì tỷ lệ càng cao càng tốt, kết quả thấp hơn ngưỡng 90% nên không đạt điều kiện tối thiểu.

**Tình huống 3:** Chính sách bảo mật yêu cầu không có lỗ hổng mức nghiêm trọng đã biết trước khi phát hành. Target và ngưỡng tối thiểu đều bằng không. Nhóm phát hiện một lỗ hổng thuộc phạm vi này. Đây là vi phạm tiêu chí không thỏa hiệp; hiệu năng tốt hoặc trải nghiệm thuận tiện không thể bù trừ cho kết quả đó.

**Tình huống 4:** Dashboard báo độ sẵn sàng 99,97%, cao hơn target 99,95%, nhưng chỉ được đo trong một giờ. Không thể dùng kết quả ngắn này để kết luận đã đạt mục tiêu độ sẵn sàng theo tháng. Cần đo đúng cửa sổ thời gian, định nghĩa downtime và phạm vi dịch vụ đã thống nhất.

Khi đọc một yêu cầu chất lượng, hãy tự hỏi: **đâu là mức nhóm muốn đạt, đâu là ranh giới thấp nhất có thể chấp nhận, và bằng chứng được đo trong điều kiện nào?** Nếu chưa trả lời được cả ba câu hỏi, mục tiêu chưa đủ rõ để làm căn cứ kiểm thử và quyết định phát hành.

## Kết luận

Mức chất lượng mong muốn định hướng sản phẩm cần đạt đến đâu; ngưỡng chấp nhận tối thiểu bảo vệ ranh giới mà sản phẩm không được vượt qua theo hướng suy giảm. Chiến lược kiểm thử cần xác định riêng hai mức, mô tả điều kiện đo, thu thập bằng chứng phù hợp và quy định cách ra quyết định khi đạt target, chỉ đạt ngưỡng hoặc vi phạm ngưỡng. Nhờ vậy, nhóm vừa kiểm soát được rủi ro tối thiểu, vừa có cơ sở rõ ràng để cải thiện chất lượng theo kỳ vọng của người dùng.
