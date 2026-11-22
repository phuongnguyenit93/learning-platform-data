# Ghi quyết định, phương án bị loại và điều kiện xem xét lại

## 1. Mục đích của việc ghi quyết định

Trong VALIDATION_TESTING_STRATEGY, nhiều lựa chọn về phạm vi kiểm thử, mức tự động hóa, môi trường xác nhận, cách quản lý rủi ro và điều kiện phát hành có ảnh hưởng lâu dài đến chất lượng sản phẩm. Nếu chỉ lưu kết luận cuối cùng, người đọc sau này sẽ khó biết quyết định được đưa ra để giải quyết vấn đề nào, dựa trên dữ liệu nào, những phương án nào đã được cân nhắc và vì sao một phương án bị loại.

Ghi quyết định giúp duy trì bối cảnh và lý do của một lựa chọn tại thời điểm lựa chọn được thông qua. Một hồ sơ tốt trả lời được năm câu hỏi: vấn đề hoặc nhu cầu nào cần giải quyết; những ràng buộc nào chi phối; các phương án khả thi là gì; vì sao chọn một phương án và loại các phương án còn lại; điều kiện nào có thể khiến tổ chức cần xem xét lại.

Hồ sơ quyết định phục vụ cả người thực hiện hiện tại lẫn người tiếp nhận sau này. Nó giúp tránh việc lặp lại tranh luận đã có kết luận, hạn chế thay đổi chiến lược mà không hiểu hệ quả, đồng thời tạo dấu vết để đánh giá quyết định khi dữ liệu, hệ thống hoặc mục tiêu thay đổi. Ghi quyết định không bảo đảm lựa chọn ban đầu luôn đúng; nó giúp tổ chức hiểu lựa chọn đó dựa trên giả định nào và biết khi nào cần kiểm tra lại.

## 2. Phân biệt quyết định với biên bản và tài liệu thiết kế

Một cuộc họp có thể tạo ra nhiều loại tài liệu. Biên bản họp ghi lại diễn biến, người tham dự, ý kiến và công việc tiếp theo. Tài liệu thiết kế mô tả cấu trúc hoặc cách triển khai một giải pháp. Hồ sơ quyết định tập trung vào lựa chọn đã được chấp thuận, lý do lựa chọn và các hệ quả cần chấp nhận.

Ba loại tài liệu có thể liên kết với nhau nhưng không thay thế nhau. Nếu một cuộc họp quyết định sử dụng một chiến lược kiểm thử mới, biên bản có thể lưu trao đổi chi tiết; tài liệu chiến lược mô tả quy trình vận hành; hồ sơ quyết định giải thích vì sao chiến lược đó được chọn và vì sao các phương án khác không được chọn. Khi một tài liệu khác đã chứa bằng chứng hoặc chi tiết triển khai, hồ sơ quyết định nên dẫn liên kết và phiên bản thay vì sao chép toàn bộ nội dung.

Hồ sơ quyết định thường được gọi là Decision Record hoặc Architecture Decision Record (ADR) khi áp dụng cho lựa chọn kiến trúc. Có thể sử dụng cùng nguyên tắc cho quyết định về chiến lược kiểm thử, miễn là cấu trúc phù hợp với mức độ ảnh hưởng. Không nhất thiết mọi thay đổi nhỏ đều cần một ADR riêng. Nên ghi thành hồ sơ có thể truy xuất khi quyết định ảnh hưởng nhiều nhóm, kéo dài qua nhiều phiên bản, tạo ràng buộc khó đảo ngược, chấp nhận rủi ro đáng kể hoặc có khả năng bị xem xét lại trong tương lai.

## 3. Khi nào cần lập hồ sơ quyết định

Hãy lập hồ sơ khi có ít nhất một trong các đặc điểm sau:

- Quyết định làm thay đổi nguyên tắc hoặc hướng đi của chiến lược kiểm thử.
- Có nhiều phương án hợp lý với đánh đổi khác nhau về chất lượng, thời gian, chi phí, độ phức tạp hoặc khả năng vận hành.
- Một phương án bị loại có thể được đề xuất lại nếu điều kiện thay đổi.
- Quyết định tạo phụ thuộc giữa các nhóm, công cụ, môi trường hoặc quy trình.
- Quyết định chấp nhận rủi ro, giới hạn phạm vi xác nhận hoặc đặt ra điều kiện phát hành.
- Người thực hiện trong tương lai cần biết lý do của một quy tắc hiện hành để tránh vô tình đảo ngược nó.

Ví dụ về các chủ đề đáng ghi lại trong một chiến lược kiểm thử gồm: lựa chọn giữa kiểm thử thủ công và tự động; cách phân tầng bộ kiểm thử; tiêu chí chọn môi trường; mức kiểm thử hồi quy; chính sách dữ liệu kiểm thử; cách xử lý kiểm thử không ổn định; cách tích hợp kiểm tra bảo mật; hoặc cách phân bổ kiểm thử theo mức rủi ro.

Với quyết định nhỏ, dễ đảo ngược và chỉ ảnh hưởng một tác vụ, một mục trong nhật ký thay đổi hoặc công việc theo dõi có thể đủ. Điều quan trọng là mức độ ghi chép tương xứng với tác động và nhu cầu truy xuất, tránh tạo tài liệu nặng nề mà không cải thiện chất lượng quyết định.

## 4. Nội dung tối thiểu của một hồ sơ quyết định

Một hồ sơ có thể dùng cấu trúc dưới đây. Tổ chức có thể điều chỉnh tên trường hoặc bổ sung quy định riêng, nhưng nên giữ đủ thông tin để người đọc hiểu bối cảnh, kết luận và điều kiện thay đổi.

| Thành phần | Nội dung cần ghi | Mục đích |
|---|---|---|
| Mã và tiêu đề | Mã duy nhất, tiêu đề mô tả lựa chọn | Dễ tham chiếu từ tài liệu và công việc khác |
| Trạng thái | Đề xuất, đã chấp thuận, bị thay thế, đã rút lại hoặc trạng thái theo quy ước của nhóm | Cho biết quyết định đang ở giai đoạn nào |
| Ngày và người chịu trách nhiệm | Ngày lập, người soạn, người có thẩm quyền quyết định và các bên cần tham vấn | Xác định trách nhiệm và thời điểm |
| Bối cảnh | Vấn đề, mục tiêu, phạm vi, nguyên nhân và điều gì cần được quyết định | Giải thích vì sao quyết định tồn tại |
| Ràng buộc và giả định | Yêu cầu bắt buộc, nguồn lực, thời gian, hệ thống phụ thuộc và giả định chưa được xác nhận | Làm rõ giới hạn của phân tích |
| Tiêu chí đánh giá | Các tiêu chí dùng để so sánh phương án và mức ưu tiên tương đối | Giúp đánh giá có nhất quán |
| Các phương án | Những lựa chọn khả thi, gồm cả phương án giữ nguyên hiện trạng nếu phù hợp | Cho thấy phạm vi đã cân nhắc |
| Quyết định | Phương án được chọn và phạm vi áp dụng | Nêu rõ kết luận |
| Lý do và đánh đổi | Bằng chứng, lợi ích, chi phí, rủi ro và hạn chế của phương án được chọn | Giải thích vì sao lựa chọn phù hợp |
| Phương án bị loại | Lý do loại từng phương án và điều kiện có thể khiến phương án đó đáng cân nhắc lại | Giữ lại kiến thức từ quá trình đánh giá |
| Hệ quả và hành động | Việc cần làm, phụ thuộc, chủ sở hữu, rủi ro còn lại và tài liệu liên quan | Chuyển quyết định thành hành động |
| Điều kiện xem xét lại | Sự kiện kích hoạt, ngưỡng hoặc dấu hiệu cần theo dõi, người đánh giá và cách mở lại quyết định | Xác định khi nào kết luận cần được kiểm tra |

Không phải trường nào cũng cần nhiều văn bản. Với một quyết định đơn giản, có thể ghi ngắn gọn. Với quyết định có rủi ro cao hoặc nhiều bên liên quan, cần giải thích sâu hơn và liên kết bằng chứng chi tiết.

## 5. Ghi bối cảnh, ràng buộc và tiêu chí đánh giá

### 5.1. Bối cảnh phải mô tả vấn đề cần giải quyết

Bối cảnh nên bắt đầu bằng tình huống cụ thể và tác động của nó. Chẳng hạn, bộ kiểm thử hồi quy hiện tại mất nhiều thời gian để hoàn tất, khiến phản hồi cho thay đổi chậm; hoặc một số luồng nghiệp vụ có rủi ro cao nhưng chưa được xác nhận tự động. Tránh mở đầu bằng tên công cụ hoặc giải pháp đã định sẵn vì cách viết đó có thể khiến người đọc tưởng rằng lựa chọn đã được quyết định trước khi so sánh.

Mô tả rõ phạm vi: sản phẩm hoặc thành phần nào bị ảnh hưởng, nhóm nào sử dụng kết quả, loại thay đổi nào thuộc phạm vi và quyết định cần đưa ra vào thời điểm nào. Nếu quyết định chỉ áp dụng cho một giai đoạn hoặc một nhóm dịch vụ, ghi giới hạn đó để tránh mở rộng kết luận ngoài dự kiến.

### 5.2. Tách ràng buộc khỏi giả định

Ràng buộc là điều kiện phải tuân thủ, ví dụ yêu cầu hợp đồng, nền tảng được hỗ trợ, giới hạn bảo mật hoặc nguồn lực đã cam kết. Giả định là điều được tạm coi là đúng để phân tích tiếp, nhưng vẫn có thể cần xác minh, ví dụ dự báo lưu lượng, khả năng tích hợp của công cụ hoặc mức độ ổn định của môi trường.

Ghi rõ nguồn và mức độ chắc chắn của mỗi thông tin. Nếu một giả định quan trọng bị sai, quyết định có thể không còn phù hợp. Vì vậy, các giả định có ảnh hưởng lớn nên có người xác minh, thời hạn xác minh và liên kết tới điều kiện xem xét lại.

### 5.3. Chọn tiêu chí so sánh trước khi chọn phương án

Tiêu chí có thể gồm mức bao phủ rủi ro, tốc độ phản hồi, độ tin cậy của kết quả, chi phí thiết lập và duy trì, khả năng mở rộng, mức phù hợp với kỹ năng của nhóm, yêu cầu bảo mật, khả năng tích hợp và mức khó đảo ngược. Không phải tiêu chí nào cũng quan trọng như nhau. Hãy chỉ ra tiêu chí bắt buộc, tiêu chí ưu tiên và những đánh đổi có thể chấp nhận.

Nếu dùng điểm số hoặc ma trận trọng số, ghi cách chấm, nguồn dữ liệu và lý do chọn trọng số. Điểm số hỗ trợ so sánh; nó không thay thế giải thích chuyên môn hoặc phê duyệt của người có thẩm quyền. Không tạo độ chính xác giả bằng những con số không có dữ liệu nền.

## 6. Cách ghi các phương án bị loại

Một phương án bị loại vẫn là thông tin có giá trị. Ghi lại nó giúp người đọc sau này hiểu rằng lựa chọn đó từng được xem xét và lý do khiến nó không phù hợp trong bối cảnh lúc ấy. Điều này đặc biệt hữu ích khi người mới tham gia đề xuất lại một cách tiếp cận cũ mà không biết lịch sử đánh giá.

Với mỗi phương án, ghi tối thiểu:

1. Mô tả ngắn gọn phương án và phạm vi có thể áp dụng.
2. Lợi ích dự kiến nếu lựa chọn phương án.
3. Hạn chế, chi phí, rủi ro hoặc ràng buộc khiến phương án không được chọn.
4. Bằng chứng hoặc giả định hỗ trợ nhận định, bao gồm cả điểm chưa chắc chắn.
5. Lý do quyết định cuối cùng ưu tiên phương án khác.
6. Điều kiện thay đổi có thể khiến phương án này được đánh giá lại.

Tránh ghi nhận xét chung chung như “quá phức tạp”, “không phù hợp” hoặc “đã thống nhất không dùng”. Hãy nêu cụ thể độ phức tạp nằm ở đâu, nhóm nào phải vận hành, chi phí nào phát sinh hoặc yêu cầu nào chưa được đáp ứng. Nếu phương án bị loại vì chưa đủ dữ liệu, ghi đó là thiếu bằng chứng thay vì kết luận phương án vốn không tốt.

Phân biệt ba tình huống: phương án không đáp ứng một ràng buộc bắt buộc; phương án đáp ứng nhưng có đánh đổi kém hơn trong bối cảnh hiện tại; và phương án chưa thể đánh giá do thiếu thông tin. Ba tình huống này dẫn tới cách xem xét lại khác nhau. Một phương án vi phạm yêu cầu bắt buộc chỉ nên được mở lại khi yêu cầu đó thay đổi hoặc có cách chứng minh sự tuân thủ. Một phương án có đánh đổi kém hơn có thể trở nên phù hợp khi chi phí, năng lực hoặc ưu tiên thay đổi. Một phương án thiếu dữ liệu cần được đánh giá lại khi có bằng chứng mới.

## 7. Xác định điều kiện xem xét lại

Điều kiện xem xét lại là những thay đổi có ý nghĩa đủ để kiểm tra xem quyết định còn phù hợp hay không. Chúng phải cụ thể, quan sát được và gắn với người chịu trách nhiệm. Cụm từ như “khi cần thiết” hoặc “định kỳ xem xét” không đủ nếu không nêu ai xem xét, xem xét điều gì và căn cứ nào kích hoạt.

Có thể chia điều kiện xem xét lại thành các nhóm:

- **Thay đổi mục tiêu hoặc phạm vi:** sản phẩm mở rộng sang nhóm người dùng mới, xuất hiện luồng nghiệp vụ quan trọng hoặc thay đổi mức rủi ro.
- **Thay đổi kỹ thuật:** kiến trúc, nền tảng, công cụ, dữ liệu, tích hợp hoặc môi trường kiểm thử thay đổi đáng kể.
- **Bằng chứng vận hành mới:** sự cố lọt qua kiểm thử, tỷ lệ lỗi tăng, kết quả kiểm thử không ổn định hoặc thời gian phản hồi vượt giới hạn đã xác định.
- **Thay đổi nguồn lực và chi phí:** năng lực nhóm, ngân sách, giấy phép, hạ tầng hoặc chi phí duy trì thay đổi.
- **Thay đổi yêu cầu bên ngoài:** tiêu chuẩn, hợp đồng, quy định hoặc cam kết với khách hàng được cập nhật.
- **Đến mốc rà soát:** quyết định được xác định là tạm thời hoặc có ngày đánh giá lại đã thống nhất.

Mỗi điều kiện nên có bốn yếu tố: sự kiện hoặc ngưỡng kích hoạt; nguồn dữ liệu để nhận biết; người chịu trách nhiệm kiểm tra; hành động tiếp theo khi điều kiện xảy ra. Với ngưỡng định lượng, dùng ngưỡng đã được nhóm có thẩm quyền thống nhất và ghi rõ cách đo. Không tự tạo một con số áp dụng chung nếu chưa có dữ liệu hoặc chính sách.

Ví dụ, thay vì ghi “xem lại khi bộ kiểm thử chậm”, có thể ghi “nhóm phụ trách nền tảng kiểm tra thời gian chạy của bộ kiểm thử hồi quy theo báo cáo pipeline; khi xu hướng vượt giới hạn vận hành đã phê duyệt trong các lần chạy liên tiếp theo quy ước của nhóm, mở đánh giá về cách phân tầng bộ kiểm thử”. Cách ghi này xác định được nguồn dữ liệu, chủ sở hữu và hành động mà không áp đặt một ngưỡng không có căn cứ.

Điều kiện xem xét lại không đồng nghĩa tự động hủy quyết định. Khi điều kiện xảy ra, chủ sở hữu thu thập bằng chứng, đánh giá tác động và đề xuất giữ nguyên, sửa đổi, thay thế hoặc rút lại quyết định. Chỉ người hoặc vai trò có thẩm quyền theo quy trình mới phê duyệt thay đổi.

## 8. Vòng đời và quản lý liên kết giữa các quyết định

Một quyết định thường trải qua các trạng thái như đề xuất, đang xem xét, đã chấp thuận, bị thay thế hoặc đã rút lại. Tên trạng thái cụ thể cần thống nhất trong kho tài liệu của nhóm. Trạng thái phải phản ánh tình hình thực tế; không để một đề xuất chưa được phê duyệt xuất hiện như quy tắc đang có hiệu lực.

Khi quyết định mới thay thế quyết định cũ, không xóa hồ sơ cũ. Cập nhật trạng thái của hồ sơ cũ, ghi mã quyết định thay thế, ngày có hiệu lực và lý do thay đổi. Hồ sơ mới nên liên kết ngược tới quyết định trước đó và nêu rõ phần nào được giữ, phần nào thay đổi. Cách này tạo lịch sử liên tục và giúp người đọc biết tài liệu nào đang chi phối hoạt động hiện tại.

Nếu quyết định phụ thuộc vào một quyết định khác, ghi rõ quan hệ đó. Ví dụ, lựa chọn môi trường kiểm thử có thể phụ thuộc vào chính sách dữ liệu; lựa chọn phạm vi hồi quy có thể phụ thuộc vào phân loại rủi ro; kế hoạch tự động hóa có thể phụ thuộc vào nền tảng CI. Khi một quyết định nền tảng thay đổi, cần rà soát các quyết định phụ thuộc thay vì giả định chúng vẫn còn phù hợp.

Mỗi hồ sơ nên có một chủ sở hữu duy trì liên kết và trạng thái. Chủ sở hữu không nhất thiết là người có quyền tự thay đổi quyết định; trách nhiệm của họ là bảo đảm hồ sơ có thể tìm thấy, thông tin còn chính xác và yêu cầu xem xét lại được chuyển đến đúng người.

## 9. Ví dụ: lựa chọn cách phân tầng kiểm thử hồi quy

### 9.1. Bối cảnh giả định

Một nhóm phát triển có bộ kiểm thử hồi quy ngày càng lớn. Chạy toàn bộ bộ kiểm thử trong mọi lần thay đổi làm tăng thời gian chờ phản hồi. Tuy nhiên, chỉ chạy một nhóm kiểm tra rất nhỏ có thể bỏ sót lỗi ở các luồng ít được thực hiện nhưng có ảnh hưởng lớn. Nhóm cần quyết định cách phân bổ kiểm thử giữa các lần thay đổi, lịch chạy định kỳ và mốc phát hành.

### 9.2. Các phương án được cân nhắc

| Phương án | Lợi ích | Hạn chế và lý do đánh giá |
|---|---|---|
| Chạy toàn bộ hồi quy ở mọi lần thay đổi | Phạm vi xác nhận rộng, quy trình đơn giản | Thời gian phản hồi và tài nguyên có thể tăng; cần đánh giá khả năng duy trì khi bộ kiểm thử tiếp tục mở rộng |
| Chỉ chạy kiểm tra khói ở mọi lần thay đổi | Phản hồi nhanh, chi phí mỗi lần chạy thấp | Không đủ bằng chứng về nhiều luồng nghiệp vụ và rủi ro hồi quy |
| Phân tầng kiểm thử theo mục đích và rủi ro | Cân bằng phản hồi sớm với xác nhận rộng ở các mốc phù hợp | Cần phân loại kiểm thử, duy trì quy tắc chọn tập chạy và bảo đảm các lần chạy rộng vẫn được thực hiện |

### 9.3. Quyết định minh họa

Giả sử nhóm chọn phương án phân tầng: chạy kiểm tra khói và các kiểm thử mục tiêu liên quan đến thay đổi trong vòng phản hồi nhanh; chạy bộ hồi quy rộng theo lịch hoặc tại mốc phát hành phù hợp; bổ sung kiểm thử chuyên sâu theo mức rủi ro. Quyết định này không loại bỏ hồi quy rộng mà quy định thời điểm và lý do thực hiện từng lớp kiểm thử.

Phương án chạy toàn bộ ở mọi lần thay đổi được giữ lại trong hồ sơ vì có thể phù hợp khi bộ kiểm thử được tối ưu đáng kể hoặc hạ tầng có khả năng đáp ứng. Phương án chỉ chạy kiểm tra khói bị loại vì không cung cấp đủ bằng chứng cho các luồng quan trọng. Cả hai kết luận đều gắn với bối cảnh, dữ liệu và năng lực tại thời điểm quyết định.

### 9.4. Điều kiện xem xét lại

Nhóm có thể mở lại quyết định khi có một trong các sự kiện sau: lỗi hồi quy nghiêm trọng lọt qua các lớp kiểm thử hiện tại; phạm vi sản phẩm hoặc mức rủi ro thay đổi; thời gian chạy và độ ổn định của bộ kiểm thử thay đổi đáng kể; năng lực hạ tầng được mở rộng; hoặc dữ liệu cho thấy lịch chạy rộng không còn phát hiện được rủi ro tương ứng với chi phí bỏ ra. Chủ sở hữu chiến lược thu thập báo cáo pipeline, sự cố và dữ liệu vận hành, sau đó trình đánh giá lại theo quy trình phê duyệt.

Đây là ví dụ giả định về cách ghi quyết định, không phải quy định mặc định cho mọi dự án. Tập kiểm thử, lịch chạy và điều kiện phát hành thực tế phải được xác định từ rủi ro, dữ liệu và yêu cầu của sản phẩm.

## 10. Mẫu hồ sơ quyết định có thể tái sử dụng

Mẫu dưới đây có thể sao chép cho một quyết định mới. Xóa hoặc điều chỉnh các trường không phù hợp, đồng thời giữ lại liên kết tới bằng chứng và người có thẩm quyền.

```markdown
# [Mã] — [Tiêu đề quyết định]

- Trạng thái:
- Ngày tạo / ngày quyết định:
- Chủ sở hữu hồ sơ:
- Người hoặc vai trò phê duyệt:
- Quyết định liên quan:

## Bối cảnh và vấn đề
[Mô tả nhu cầu, phạm vi, tác động và quyết định cần đưa ra.]

## Ràng buộc và giả định
- Ràng buộc:
- Giả định cần xác minh:

## Tiêu chí đánh giá
- Tiêu chí bắt buộc:
- Tiêu chí ưu tiên:
- Đánh đổi có thể chấp nhận:

## Các phương án
### Phương án A
- Mô tả:
- Lợi ích:
- Hạn chế / rủi ro:
- Bằng chứng:

### Phương án B
- Mô tả:
- Lợi ích:
- Hạn chế / rủi ro:
- Bằng chứng:

## Quyết định
[Phương án được chọn, phạm vi và thời điểm có hiệu lực.]

## Lý do và hệ quả
[Lý do lựa chọn, đánh đổi được chấp nhận, rủi ro còn lại và hành động cần thực hiện.]

## Phương án bị loại
- [Phương án]: [Lý do loại và điều kiện có thể xem xét lại.]

## Điều kiện xem xét lại
- Sự kiện / ngưỡng kích hoạt:
- Nguồn dữ liệu:
- Người chịu trách nhiệm:
- Hành động khi kích hoạt:
- Mốc rà soát (nếu có):

## Liên kết
- Yêu cầu / tiêu chí:
- Bằng chứng / báo cáo:
- Công việc triển khai:
- Quyết định thay thế hoặc phụ thuộc:
```

## 11. Rà soát chất lượng hồ sơ quyết định

Trước khi công bố hoặc sử dụng hồ sơ làm căn cứ triển khai, hãy kiểm tra các điểm sau:

- Vấn đề và phạm vi được mô tả đủ rõ để người không tham gia thảo luận vẫn hiểu lý do cần quyết định.
- Ràng buộc được phân biệt với giả định; giả định quan trọng có cách xác minh.
- Các phương án được mô tả công bằng, có lợi ích, hạn chế và bằng chứng tương ứng.
- Tiêu chí đánh giá phù hợp với mục tiêu và rủi ro; mọi điểm số hoặc ngưỡng đều có căn cứ.
- Phương án được chọn, phạm vi áp dụng và người có thẩm quyền được nêu rõ.
- Các phương án bị loại có lý do cụ thể và điều kiện xem xét lại khi thích hợp.
- Hệ quả, rủi ro còn lại, công việc tiếp theo và chủ sở hữu đã được xác định.
- Điều kiện xem xét lại có thể quan sát, có nguồn dữ liệu, người chịu trách nhiệm và hành động tiếp theo.
- Trạng thái, ngày hiệu lực và liên kết tới quyết định cũ hoặc mới phản ánh đúng vòng đời.
- Hồ sơ không chứa dữ liệu nhạy cảm không cần thiết; bằng chứng được tham chiếu theo quyền truy cập phù hợp.

## 12. Những lỗi thường gặp

**Chỉ ghi kết luận:** người đọc biết phương án được chọn nhưng không biết vì sao. Hãy lưu bối cảnh, tiêu chí, các lựa chọn và đánh đổi quan trọng.

**Chỉ ghi phương án thắng:** các lựa chọn bị loại dễ được đề xuất lại vì lý do loại chưa được lưu. Ghi lý do cụ thể và điều kiện có thể làm thay đổi đánh giá.

**Biến giả định thành sự thật:** một dự báo hoặc nhận định chưa xác minh được dùng như dữ liệu chắc chắn. Đánh dấu giả định, người xác minh và tác động nếu giả định sai.

**Dùng điểm số thiếu căn cứ:** ma trận đánh giá tạo cảm giác khách quan dù trọng số hoặc dữ liệu tùy ý. Ghi cách chấm và giới hạn của dữ liệu; giải thích phần đánh đổi không thể biểu diễn bằng điểm.

**Điều kiện xem xét lại quá mơ hồ:** không ai biết lúc nào cần mở lại quyết định. Xác định sự kiện, nguồn dữ liệu, người theo dõi và quy trình đánh giá.

**Sửa hồ sơ cũ mà không lưu lịch sử:** người đọc không thể biết quyết định đã thay đổi khi nào và vì sao. Tạo hồ sơ thay thế hoặc lưu phiên bản theo quy ước, liên kết hai chiều và cập nhật trạng thái.

**Nhầm xem xét lại với tự động đảo ngược:** một chỉ số chạm ngưỡng không nhất thiết làm quyết định hết hiệu lực ngay. Điều kiện kích hoạt mở quy trình đánh giá; việc thay đổi vẫn cần đúng thẩm quyền.

**Không duy trì chủ sở hữu:** hồ sơ dần mất liên kết, trạng thái và điều kiện rà soát. Giao trách nhiệm duy trì rõ ràng và đưa các mốc xem xét vào hoạt động quản trị phù hợp.

## 13. Kết luận áp dụng

Một hồ sơ quyết định có giá trị khi người đọc có thể lần theo mạch từ vấn đề đến tiêu chí, từ tiêu chí đến các phương án, từ phương án đến lựa chọn và từ lựa chọn đến điều kiện xem xét lại. Phương án bị loại cần được ghi đủ rõ để tránh lặp lại đánh giá cũ, nhưng cũng cần giữ điều kiện để đánh giá mới khi hoàn cảnh thay đổi.

Trong quản lý chiến lược kiểm thử, quyết định nên được liên kết với yêu cầu, bằng chứng kiểm thử, rủi ro, kế hoạch triển khai và các quyết định phụ thuộc. Khi có thay đổi đáng kể, chủ sở hữu dùng các điều kiện đã ghi để mở đánh giá, cập nhật hoặc thay thế quyết định theo đúng thẩm quyền. Nhờ vậy, chiến lược có thể tiến hóa theo bằng chứng mà vẫn giữ được lịch sử và trách nhiệm giải trình.
