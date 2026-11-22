# Chọn mức tài liệu phù hợp với nhóm, rủi ro và yêu cầu chứng minh

Tài liệu kiểm thử giúp nhóm thống nhất mục tiêu, phạm vi, cách thực hiện, trách nhiệm và bằng chứng về chất lượng. Tuy nhiên, không phải dự án nào cũng cần cùng một bộ tài liệu hoặc cùng mức chi tiết. Một nhóm nhỏ phát triển sản phẩm nội bộ có thể phối hợp hiệu quả bằng tiêu chí chấp nhận, ghi chú kiểm thử trong ticket và báo cáo ngắn. Một hệ thống xử lý thanh toán, dữ liệu nhạy cảm hoặc hoạt động trong lĩnh vực có yêu cầu kiểm toán có thể cần chiến lược kiểm thử chính thức, truy vết yêu cầu, hồ sơ thực thi, phê duyệt và bằng chứng được lưu giữ theo quy định.

Chọn mức tài liệu phù hợp là quyết định cân bằng giữa nhu cầu phối hợp, rủi ro, độ phức tạp, khả năng thay đổi và yêu cầu chứng minh. Tài liệu quá ít khiến nhóm phải dựa vào trí nhớ, khó bàn giao và không thể giải thích quyết định. Tài liệu quá nhiều tạo gánh nặng cập nhật, làm chậm thay đổi và dễ trở thành hình thức nếu nội dung không phản ánh công việc thực tế.

Một cách tiếp cận tốt bắt đầu từ câu hỏi: ai cần biết điều gì, cần biết vào thời điểm nào, cần bằng chứng nào để ra quyết định và hậu quả ra sao nếu thông tin bị thiếu? Từ đó, nhóm chọn đúng loại tài liệu, mức chi tiết, nơi lưu trữ và cách duy trì. Tài liệu cần đủ để người khác hiểu và tái hiện công việc, đồng thời đủ gọn để luôn được cập nhật.

## 1. Mục đích của tài liệu trong chiến lược kiểm thử

Tài liệu không chỉ là bản ghi sau khi công việc hoàn tất. Nó hỗ trợ các hoạt động trong suốt vòng đời sản phẩm.

### Tạo sự thống nhất

Tài liệu giúp các vai trò hiểu cùng một mục tiêu, phạm vi, thuật ngữ, giả định và tiêu chí. Điều này đặc biệt quan trọng khi phát triển, kiểm thử, nghiệp vụ và vận hành cùng tham gia.

### Hướng dẫn thực hiện

Kế hoạch, checklist, hướng dẫn môi trường và runbook cho biết cần chuẩn bị gì, chạy ở đâu, theo thứ tự nào và xử lý ra sao khi có vấn đề.

### Hỗ trợ quyết định

Báo cáo kiểm thử, danh sách lỗi, ma trận rủi ro và bản ghi quyết định giúp người có thẩm quyền hiểu trạng thái chất lượng, khoảng trống bằng chứng và rủi ro còn lại.

### Bảo toàn tri thức

Tài liệu giúp người mới tiếp nhận công việc, người khác thay thế khi cần và nhóm giữ được kiến thức sau khi thành viên chuyển vai trò hoặc rời dự án.

### Chứng minh và truy vết

Trong những bối cảnh cần kiểm toán hoặc xác nhận chính thức, tài liệu cung cấp dấu vết cho biết yêu cầu nào đã được kiểm tra, bằng phiên bản nào, ai thực hiện, kết quả gì và quyết định dựa trên bằng chứng nào.

### Hỗ trợ vận hành và cải tiến

Runbook, hướng dẫn khôi phục, bài học sau sự cố và lịch sử thay đổi giúp nhóm vận hành hệ thống, xử lý lỗi và cải tiến chiến lược theo dữ liệu thực tế.

Tài liệu chỉ có giá trị khi phục vụ một mục đích cụ thể. Nếu không xác định được người dùng, quyết định hoặc công việc mà tài liệu hỗ trợ, cần xem xét có nên tạo tài liệu đó hay không.

## 2. Nguyên tắc chọn mức tài liệu

Có thể áp dụng một số nguyên tắc chung trước khi quyết định loại và độ chi tiết.

### Tài liệu theo nhu cầu, không theo số lượng

Không cần tạo đủ mọi loại tài liệu chỉ vì một mẫu quy trình đề xuất. Chọn những tài liệu giúp giải quyết nhu cầu phối hợp, kiểm soát rủi ro hoặc chứng minh cụ thể.

### Mức chi tiết tỷ lệ với rủi ro

Thay đổi có tác động thấp, dễ đảo ngược và có phạm vi nhỏ thường cần ít hồ sơ hơn thay đổi ảnh hưởng đến dữ liệu quan trọng, giao dịch, bảo mật hoặc nhiều hệ thống.

### Tài liệu gần với công việc

Thông tin nên nằm ở nơi người thực hiện tìm thấy và cập nhật được: ticket, kho mã, hệ thống quản lý test, trang hướng dẫn hoặc hồ sơ phát hành. Tránh sao chép cùng một thông tin ở nhiều nơi mà không có nguồn chính.

### Ưu tiên bằng chứng có thể xác minh

Một ghi chú “đã kiểm thử” ít hữu ích hơn thông tin cho biết phiên bản, môi trường, dữ liệu, phạm vi, kết quả và liên kết đến log hoặc báo cáo. Mức chứng minh cần phù hợp với quyết định mà tài liệu hỗ trợ.

### Tài liệu là một phần của sản phẩm

Khi hành vi, API, schema, môi trường hoặc quy trình thay đổi, tài liệu liên quan cần được xem xét cùng thay đổi đó. Tài liệu lỗi thời có thể nguy hiểm hơn việc không có tài liệu vì người dùng tin vào thông tin sai.

### Tạo đủ cấu trúc để tìm kiếm và tái sử dụng

Dùng tiêu đề, metadata, định danh và quy ước đặt tên nhất quán. Không cần áp dụng biểu mẫu dài cho mọi việc, nhưng cần khả năng tìm lại thông tin quan trọng.

## 3. Những yếu tố quyết định mức tài liệu cần thiết

Không nên chọn mức tài liệu chỉ dựa vào quy mô dự án hoặc yêu cầu của một cá nhân. Cần đánh giá nhiều yếu tố.

### Quy mô và cách tổ chức nhóm

Nhóm nhỏ, ổn định, làm việc gần nhau có thể phối hợp bằng trao đổi trực tiếp và tài liệu ngắn. Khi nhóm phân tán, nhiều múi giờ, nhiều nhà cung cấp hoặc thay đổi nhân sự thường xuyên, thông tin cần được ghi rõ hơn để giảm phụ thuộc vào trao đổi miệng.

### Rủi ro sản phẩm

Cần xem hậu quả nếu lỗi xảy ra: mất dữ liệu, sai giao dịch, gián đoạn dịch vụ, ảnh hưởng an toàn, lộ thông tin, vi phạm nghĩa vụ hoặc mất khả năng phục hồi. Rủi ro cao thường cần phạm vi, tiêu chí, bằng chứng và phê duyệt rõ ràng hơn.

### Độ phức tạp kỹ thuật

Hệ thống nhiều dịch vụ, tích hợp bất đồng bộ, nhiều phiên bản ứng dụng, migration dữ liệu hoặc phụ thuộc bên ngoài thường cần tài liệu về hợp đồng, luồng dữ liệu, tương thích, môi trường và phục hồi.

### Tốc độ thay đổi

Nếu yêu cầu và thiết kế thay đổi thường xuyên, tài liệu dài và sao chép thủ công nhanh lỗi thời. Nên dùng tài liệu ngắn, liên kết đến nguồn chính và đặt việc cập nhật vào quy trình thay đổi.

### Yêu cầu chứng minh

Một số sản phẩm cần lưu bằng chứng để phục vụ kiểm toán, khách hàng, hợp đồng, cơ quan quản lý hoặc quy trình nội bộ. Khi đó cần xác định hồ sơ nào phải lưu, ai phê duyệt, thời hạn lưu và cách chứng minh tính toàn vẹn.

### Khả năng khắc phục

Thay đổi dễ rollback, dữ liệu có thể tái tạo và tác động giới hạn thường cần ít hồ sơ hơn thay đổi khó đảo ngược, ảnh hưởng dữ liệu lịch sử hoặc cần phối hợp nhiều bên để phục hồi.

### Vòng đời và mức độ quan trọng

Một thử nghiệm ngắn hạn có thể chỉ cần ghi chú mục tiêu và kết quả. Một dịch vụ cốt lõi tồn tại nhiều năm cần tài liệu kiến trúc, vận hành, dữ liệu, kiểm thử, phụ thuộc và chuyển giao được duy trì lâu dài.

## 4. Phân loại mức rủi ro để định hướng tài liệu

Có thể phân loại rủi ro thành các mức định tính để chọn mức tài liệu. Đây là công cụ định hướng, không thay thế phân tích rủi ro chuyên môn.

| Mức rủi ro | Đặc điểm tham khảo | Mức tài liệu gợi ý |
|---|---|---|
| Thấp | Phạm vi nhỏ, ít người dùng, dễ đảo ngược, không xử lý dữ liệu nhạy cảm | Ghi chú trong ticket, tiêu chí chấp nhận và kết quả ngắn |
| Trung bình | Ảnh hưởng một luồng nghiệp vụ, có phụ thuộc hoặc dữ liệu cần quản lý | Kế hoạch kiểm thử gọn, ma trận phạm vi, báo cáo và hướng dẫn liên quan |
| Cao | Ảnh hưởng chức năng cốt lõi, nhiều dịch vụ, giao dịch hoặc dữ liệu quan trọng | Chiến lược/plan rõ, truy vết, bằng chứng thực thi, phê duyệt và kế hoạch phục hồi |
| Rất cao hoặc chịu quản lý | Có rủi ro an toàn, bảo mật, pháp lý, tài chính hoặc yêu cầu kiểm toán chính thức | Hồ sơ được kiểm soát, truy vết đầy đủ, phê duyệt theo thẩm quyền và lưu giữ theo chính sách |

Một lỗi ở chức năng nhỏ vẫn có thể có rủi ro cao nếu ảnh hưởng đến quyền truy cập hoặc dữ liệu nhạy cảm. Ngược lại, một hệ thống lớn có thể có thay đổi nhỏ, cô lập và dễ phục hồi. Cần đánh giá theo thay đổi và bối cảnh cụ thể.

### Không dùng nhãn rủi ro thay cho lý do

Khi chọn mức tài liệu, ghi ngắn lý do: số người dùng bị ảnh hưởng, loại dữ liệu, khả năng rollback, phụ thuộc và yêu cầu chứng minh. Điều này giúp người khác hiểu tại sao nhóm chọn cách làm đó.

## 5. Chọn tài liệu theo đối tượng sử dụng

Mỗi tài liệu cần có người đọc chính. Nếu một tài liệu cố phục vụ tất cả mọi người, nó dễ quá dài hoặc thiếu chi tiết cho từng nhu cầu.

| Đối tượng | Câu hỏi họ cần trả lời | Tài liệu hữu ích |
|---|---|---|
| Chủ sản phẩm/nghiệp vụ | Phạm vi nào được xác minh, rủi ro nào còn lại? | Tóm tắt chiến lược, tiêu chí chấp nhận, báo cáo chất lượng |
| Developer | Cần kiểm tra gì, dữ liệu nào, thay đổi ảnh hưởng ở đâu? | Tiêu chí, test design, hợp đồng, hướng dẫn chạy |
| QA/test engineer | Cách chuẩn bị, thực thi, ghi nhận và đánh giá kết quả? | Test plan, checklist, test case, charter, dữ liệu |
| Vận hành/SRE | Cách triển khai, giám sát, xử lý và khôi phục? | Runbook, kế hoạch rollout, dashboard, hướng dẫn phục hồi |
| Quản lý/phê duyệt | Có đủ bằng chứng để ra quyết định không? | Báo cáo, rủi ro, ngoại lệ và quyết định |
| Kiểm toán/đánh giá độc lập | Có thể xác minh hoạt động đã thực hiện và người phê duyệt không? | Hồ sơ truy vết, lịch sử thay đổi, kết quả có định danh |
| Thành viên mới/nhóm tiếp nhận | Cần hiểu hệ thống và bắt đầu công việc ở đâu? | Tổng quan, kiến trúc, hướng dẫn môi trường, quy trình |

Có thể có nhiều tài liệu liên kết với nhau thay vì gom mọi nội dung vào một tệp lớn.

## 6. Các loại tài liệu kiểm thử và mục đích của chúng

Không phải dự án nào cũng cần tất cả loại tài liệu dưới đây. Hãy chọn theo mục tiêu.

### Chiến lược kiểm thử (test strategy)

Mô tả cách tiếp cận dài hạn hoặc ở cấp sản phẩm: mục tiêu chất lượng, nguyên tắc, tầng kiểm thử, phân bổ trách nhiệm, công cụ, rủi ro và tiêu chí chung.

Chiến lược thường ổn định hơn kế hoạch của một lần phát hành. Nó trả lời nhóm sẽ bảo vệ chất lượng theo cách nào và vì sao.

### Kế hoạch kiểm thử (test plan)

Mô tả cách áp dụng chiến lược cho một phạm vi cụ thể: mục tiêu, phạm vi trong/ngoài, môi trường, dữ liệu, nguồn lực, lịch, phụ thuộc, tiêu chí bắt đầu/kết thúc và rủi ro.

Một thay đổi nhỏ có thể không cần tài liệu plan riêng nếu thông tin đã có trong ticket và pipeline.

### Thiết kế kiểm thử (test design)

Mô tả điều kiện, dữ liệu, trạng thái, trường hợp và cách kiểm tra. Có thể thể hiện bằng bảng quyết định, ma trận, sơ đồ trạng thái, charter hoặc danh sách test.

### Test case hoặc checklist

Ghi các bước, dữ liệu, kết quả mong đợi hoặc các điểm cần xác minh. Test case chi tiết phù hợp với quy trình lặp lại, yêu cầu bằng chứng hoặc người thực hiện khác nhau. Checklist ngắn phù hợp với công việc đơn giản và có thể quan sát trực tiếp.

### Charter kiểm thử thăm dò

Nêu mục tiêu khám phá, phạm vi, rủi ro, thời lượng và ghi chú phát hiện. Không cần viết trước mọi bước vì hoạt động khám phá điều chỉnh theo kết quả quan sát.

### Báo cáo kiểm thử

Tóm tắt phiên bản, môi trường, phạm vi đã chạy, kết quả, lỗi còn mở, test bị chặn, giới hạn và khuyến nghị. Báo cáo cần phân biệt điều đã kiểm tra với điều chưa có bằng chứng.

### Hồ sơ thực thi và bằng chứng

Gồm kết quả test, log, trace, ảnh, dữ liệu đầu vào/đầu ra, build ID, thời gian, người thực hiện và liên kết đến lỗi. Đây là phần quan trọng khi cần tái hiện hoặc chứng minh.

### Tài liệu môi trường và dữ liệu

Mô tả cách tạo môi trường, phiên bản schema, cấu hình, dữ liệu seed, quyền, phụ thuộc và cách reset/cleanup. Không ghi bí mật trực tiếp vào tài liệu.

### Runbook và hướng dẫn vận hành

Hướng dẫn triển khai, smoke test, giám sát, xử lý sự cố, rollback và phục hồi. Nội dung cần đủ cụ thể để người trực có thể hành động trong điều kiện áp lực.

### Bản ghi quyết định

Ghi quyết định quan trọng, bối cảnh, phương án đã cân nhắc, lý do, người quyết định và hệ quả. Có thể dùng cho quyết định kiến trúc, mức bao phủ, ngoại lệ phát hành hoặc chấp nhận rủi ro.

### Bằng chứng phê duyệt và truy vết

Liên kết yêu cầu, rủi ro, kiểm thử, kết quả, lỗi và quyết định. Mức chi tiết phụ thuộc yêu cầu quản trị, hợp đồng và kiểm toán.

## 7. Chọn bộ tài liệu tối thiểu cho từng tình huống

Có thể bắt đầu từ bộ tài liệu tối thiểu, sau đó bổ sung khi rủi ro hoặc nhu cầu chứng minh tăng.

### Thay đổi nhỏ, rủi ro thấp

Ví dụ: sửa nhãn, thay đổi bố cục nhỏ hoặc cải thiện thông báo không ảnh hưởng dữ liệu.

Bộ tài liệu có thể gồm:

- Ticket có mục tiêu và tiêu chí chấp nhận.
- Ghi chú phạm vi kiểm tra hoặc checklist ngắn.
- Kết quả CI hoặc xác nhận thủ công.
- Liên kết lỗi nếu phát hiện vấn đề.

Không cần tạo test plan dài nếu thông tin đã rõ và có thể truy vết từ ticket.

### Thay đổi chức năng thông thường

Ví dụ: thêm bộ lọc, quy tắc tìm kiếm hoặc một trạng thái nghiệp vụ mới.

Bộ tài liệu có thể gồm:

- Yêu cầu và tiêu chí chấp nhận.
- Phân tích rủi ro ngắn.
- Test design hoặc checklist theo luồng.
- Kế hoạch dữ liệu và môi trường nếu có phụ thuộc.
- Kết quả kiểm thử và lỗi còn mở.
- Ghi chú phát hành nếu có thay đổi vận hành.

### Thay đổi tích hợp hoặc dữ liệu

Ví dụ: thêm dịch vụ, thay API, migration schema hoặc xử lý message.

Bộ tài liệu nên xem xét:

- Chiến lược hoặc plan theo phạm vi.
- Sơ đồ luồng và danh sách phụ thuộc.
- Hợp đồng API/sự kiện và ma trận tương thích.
- Kế hoạch migration, backfill và rollback.
- Test design theo trạng thái, lỗi và retry.
- Bằng chứng tích hợp, đối soát và kiểm thử hồi quy.
- Runbook và giám sát sau triển khai.

### Thay đổi rủi ro cao hoặc cần chứng minh chính thức

Bộ tài liệu thường cần:

- Chiến lược và kế hoạch được phê duyệt.
- Yêu cầu và tiêu chí có định danh.
- Phân tích rủi ro và biện pháp kiểm soát.
- Ma trận truy vết yêu cầu – test – kết quả.
- Quy trình review và phê duyệt.
- Hồ sơ thực thi có phiên bản, thời gian và người thực hiện.
- Quản lý lỗi, ngoại lệ và quyết định chấp nhận rủi ro.
- Bằng chứng triển khai, giám sát, phục hồi và lưu giữ.
- Lịch sử thay đổi và kiểm soát quyền truy cập.

Các yêu cầu chính thức cần được xác định từ chính sách và quy định áp dụng. Không nên tự suy diễn rằng một mẫu tài liệu cụ thể đáp ứng mọi chuẩn hoặc nghĩa vụ pháp lý.

## 8. Dùng mức tài liệu theo quy mô và cấu trúc nhóm

Quy mô nhóm ảnh hưởng đến cách phối hợp và chuyển giao, nhưng không phải yếu tố duy nhất.

### Nhóm nhỏ, ổn định

Có thể dùng:

- README hoặc trang tổng quan ngắn.
- Ticket chứa mục tiêu và tiêu chí.
- Checklist kiểm thử.
- Báo cáo pipeline và ghi chú lỗi.
- Runbook tối thiểu cho triển khai và khôi phục.

Thông tin cần dễ tìm và không phụ thuộc vào trí nhớ của một cá nhân. Dù nhóm chỉ có ba người, các thao tác có rủi ro cao vẫn cần ghi lại.

### Nhóm nhiều vai trò hoặc nhiều nhóm

Cần bổ sung:

- Chiến lược chung và quy ước.
- Phân công trách nhiệm.
- Quy tắc bàn giao và review.
- Ma trận phụ thuộc và hợp đồng.
- Kế hoạch theo phạm vi phát hành.
- Dashboard và báo cáo có cấu trúc.
- Quy trình triage và leo thang.

Tài liệu giúp các nhóm hiểu điểm giao nhau và tránh mỗi nhóm dùng thuật ngữ hoặc tiêu chí khác nhau.

### Nhóm phân tán hoặc có nhà cung cấp

Cần ghi rõ:

- Đầu mối và trách nhiệm.
- Kênh giao tiếp và thời gian phản hồi.
- Phiên bản hợp đồng và phụ thuộc.
- Quyền truy cập và cách trao đổi bằng chứng.
- Quy trình thay đổi, phê duyệt và bàn giao.
- Điều kiện hỗ trợ, sự cố và phục hồi.

Trao đổi trực tiếp vẫn hữu ích, nhưng quyết định và thông tin cần thiết phải được ghi ở nơi các bên có thể truy cập.

## 9. Chọn mức tài liệu theo vòng đời sản phẩm

Tài liệu cần phù hợp với độ trưởng thành và vòng đời.

### Khám phá và thử nghiệm ý tưởng

Mục tiêu là học nhanh và giảm giả định. Có thể dùng:

- Mục tiêu giả thuyết.
- Kịch bản thử nghiệm.
- Tiêu chí thành công hoặc dừng.
- Kết quả quan sát.
- Quyết định tiếp tục, thay đổi hoặc dừng.

Không nên đầu tư quá sớm vào bộ tài liệu vận hành dài hạn khi sản phẩm chưa được xác nhận.

### MVP hoặc sản phẩm mới

Cần đủ tài liệu để nhóm phát triển và vận hành hiểu cách hoạt động:

- Yêu cầu và tiêu chí.
- Tổng quan kiến trúc.
- Chiến lược kiểm thử cơ bản.
- Hướng dẫn môi trường và dữ liệu.
- Quy trình triển khai và rollback.
- Kết quả kiểm thử và lỗi đã biết.

### Sản phẩm đang mở rộng

Khi số người dùng, nhóm và phụ thuộc tăng, cần bổ sung:

- Chiến lược kiểm thử cấp sản phẩm.
- Quy ước API và hợp đồng.
- Ma trận trách nhiệm.
- Báo cáo chất lượng và rủi ro.
- Runbook, SLO và quy trình sự cố.
- Quản lý phiên bản dữ liệu và schema.
- Lịch sử quyết định quan trọng.

### Sản phẩm trưởng thành hoặc quan trọng

Cần chú trọng:

- Tài liệu có chủ sở hữu và lịch review.
- Truy vết thay đổi và bằng chứng.
- Quy trình phê duyệt.
- Quản lý ngoại lệ và rủi ro.
- Kế hoạch phục hồi và diễn tập.
- Lưu giữ hồ sơ theo chính sách.
- Chuyển giao và tính liên tục tri thức.

## 10. Xác định yêu cầu chứng minh trước khi chọn biểu mẫu

Một số dự án cần chứng minh rằng hoạt động đã được thực hiện và kết quả đủ tin cậy. Hãy xác định chính xác loại bằng chứng cần có.

Các câu hỏi:

- Ai sẽ xem xét hoặc kiểm toán?
- Họ cần xác nhận quyết định nào?
- Cần chứng minh yêu cầu nào đã được kiểm thử?
- Có cần biết ai thực hiện, ai review và ai phê duyệt không?
- Cần lưu phiên bản ứng dụng, schema, dữ liệu và môi trường không?
- Cần lưu kết quả từng test hay chỉ báo cáo tổng hợp?
- Có yêu cầu chữ ký, dấu thời gian hoặc lịch sử thay đổi không?
- Hồ sơ phải được lưu trong bao lâu?
- Ai được phép xem, sửa hoặc xóa?
- Cần bảo vệ tính toàn vẹn của hồ sơ như thế nào?

### Bằng chứng tối thiểu cho một lần chạy

Tùy bối cảnh, một bản ghi có thể gồm:

- Định danh lần chạy.
- Build hoặc phiên bản ứng dụng.
- Phiên bản test và cấu hình.
- Môi trường và schema.
- Bộ dữ liệu hoặc fixture version.
- Thời điểm bắt đầu và kết thúc.
- Người hoặc hệ thống khởi chạy.
- Danh sách test và trạng thái.
- Log, artifact và liên kết lỗi.
- Ghi chú về test bị bỏ qua hoặc bị chặn.

Nếu cần chứng minh chi tiết hơn, có thể lưu từng lần thực thi, người review, phê duyệt và checksum hoặc cơ chế toàn vẹn theo quy trình tổ chức.

### Phân biệt bằng chứng và kết luận

Log là bằng chứng về sự kiện được ghi nhận. Báo cáo là phần tổng hợp và diễn giải. Kết luận “đạt” là quyết định dựa trên tiêu chí. Không nên gộp ba lớp này thành một câu không có nguồn hỗ trợ.

## 11. Thiết kế truy vết ở mức cần thiết

Truy vết giúp nối nhu cầu với hoạt động xác minh và kết quả. Mức truy vết nên tỷ lệ với rủi ro và yêu cầu chứng minh.

Một chuỗi truy vết tham khảo:

**Yêu cầu → Rủi ro → Tiêu chí chấp nhận → Test design/test case → Lần thực thi → Kết quả/bằng chứng → Lỗi hoặc quyết định.**

### Truy vết nhẹ

Với thay đổi nhỏ, liên kết ticket với test tự động, pull request và kết quả CI có thể đủ.

### Truy vết có cấu trúc

Với thay đổi nhiều luồng hoặc nhiều nhóm, dùng bảng hoặc hệ thống quản lý để liên kết yêu cầu, rủi ro, test, kết quả và lỗi.

### Truy vết đầy đủ

Với yêu cầu chứng minh cao, cần định danh ổn định, lịch sử thay đổi, trạng thái review, phê duyệt, phiên bản và hồ sơ thực thi được lưu giữ.

Không nên tạo liên kết chỉ để có một bảng đẹp. Mỗi liên kết cần giúp trả lời câu hỏi: yêu cầu này được kiểm tra ở đâu, bằng chứng nào hỗ trợ kết luận và điều gì còn thiếu?

## 12. Chọn tài liệu tĩnh, tài liệu sống và tài liệu được sinh tự động

Mỗi loại thông tin có nhịp thay đổi khác nhau.

### Tài liệu tĩnh có kiểm soát

Phù hợp với chính sách, chiến lược, quy trình phê duyệt hoặc quyết định ít thay đổi. Cần người sở hữu, phiên bản và lịch review.

### Tài liệu sống

Phù hợp với hướng dẫn phát triển, cách chạy test, kiến trúc đang thay đổi, checklist và runbook. Nên đặt gần mã hoặc công cụ mà người dùng thao tác.

### Tài liệu sinh tự động

Phù hợp với báo cáo CI, coverage, API reference, danh sách test, kết quả thực thi và metric. Cần xác định nguồn dữ liệu, thời điểm sinh, phiên bản và cách kiểm tra độ chính xác.

### Kết hợp các loại

Ví dụ, chiến lược kiểm thử có thể là tài liệu được review định kỳ; danh sách test và kết quả được sinh từ pipeline; hướng dẫn chạy test nằm trong README; quyết định ngoại lệ được lưu trong hệ thống quản lý công việc.

Không nên sao chép báo cáo tự động vào tài liệu thủ công nếu có thể liên kết trực tiếp đến nguồn có định danh ổn định.

## 13. Quản lý tài liệu như mã nguồn khi phù hợp

Tài liệu lưu trong kho mã có thể được review, version control và cập nhật cùng thay đổi sản phẩm. Cách này hữu ích với hướng dẫn kỹ thuật, cấu hình, test strategy ở cấp repository và runbook gắn với triển khai.

Lợi ích:

- Thay đổi có lịch sử và người review.
- Có thể liên kết tài liệu với pull request.
- Dễ phát hiện tài liệu chưa được cập nhật.
- Có thể kiểm tra liên kết hoặc sinh tài liệu tự động.
- Người phát triển tìm tài liệu gần mã nguồn.

Tuy nhiên, không phải tài liệu nào cũng nên lưu trong repository. Hồ sơ phê duyệt, dữ liệu kiểm toán hoặc thông tin có quyền truy cập riêng có thể cần hệ thống chuyên dụng.

### Quy tắc cập nhật tài liệu cùng mã

Khi thay đổi API, schema, cấu hình, test framework hoặc quy trình triển khai, pull request nên nêu tài liệu liên quan đã được cập nhật hoặc giải thích vì sao không cần. Review cần xem nội dung tài liệu có khớp hành vi mới không.

### Tránh tài liệu sinh ra nhưng không ai đọc

Tự động hóa có thể tạo hàng trăm trang API hoặc báo cáo. Cần xác định người dùng, cách tìm kiếm và quy trình xử lý nội dung lỗi thời. Khối lượng tài liệu không đồng nghĩa với khả năng tiếp cận thông tin.

## 14. Xác định chủ sở hữu và quy trình review tài liệu

Mỗi tài liệu quan trọng cần có người hoặc nhóm chịu trách nhiệm duy trì.

Thông tin quản lý có thể gồm:

- Tên tài liệu và mục đích.
- Đối tượng sử dụng.
- Chủ sở hữu.
- Người review hoặc phê duyệt.
- Phiên bản hoặc ngày cập nhật.
- Nguồn thông tin chính.
- Phạm vi và giới hạn.
- Ngày review tiếp theo.
- Chính sách lưu giữ và quyền truy cập nếu cần.

### Ai nên sở hữu?

- Chiến lược kiểm thử: QA lead, test manager hoặc vai trò được giao.
- Test plan theo thay đổi: người điều phối kiểm thử hoặc chủ sở hữu phạm vi.
- Hướng dẫn chạy test: nhóm sở hữu repository hoặc framework.
- API và schema: nhóm sở hữu dịch vụ.
- Runbook: chủ sở hữu dịch vụ hoặc vận hành.
- Tiêu chí nghiệp vụ: chủ sản phẩm hoặc đại diện nghiệp vụ.
- Hồ sơ phát hành: vai trò quản lý phát hành hoặc chủ sở hữu quy trình.

Một người có thể viết và người khác phê duyệt. Cần tránh để người viết tự xác nhận mọi nội dung quan trọng nếu quy trình yêu cầu review độc lập.

### Lịch review theo rủi ro

Tài liệu chiến lược có thể được review theo quý hoặc khi có thay đổi lớn. Runbook cần được kiểm tra sau thay đổi vận hành và diễn tập. Hướng dẫn chạy test cần được xem xét khi công cụ hoặc cấu trúc repository thay đổi. Hồ sơ phát hành cần được kiểm tra trong từng lần phát hành.

Không nên đặt lịch review máy móc mà không gắn với thay đổi. Một tài liệu có thể cần cập nhật ngay sau khi kiến trúc đổi, dù ngày review định kỳ còn xa.

## 15. Kiểm soát phiên bản, thay đổi và lịch sử

Khi tài liệu ảnh hưởng đến quyết định hoặc vận hành, cần biết phiên bản nào được áp dụng tại thời điểm thực hiện.

Có thể dùng:

- Version control của repository.
- Revision history của hệ thống tài liệu.
- Version hoặc ID trong metadata.
- Liên kết đến release, commit hoặc ticket.
- Lịch sử review và phê duyệt.
- Snapshot của hồ sơ tại thời điểm phát hành khi cần.

### Thay đổi nội dung quan trọng

Với thay đổi ảnh hưởng đến tiêu chí, phạm vi hoặc trách nhiệm, cần ghi:

- Nội dung thay đổi.
- Lý do.
- Tác động đến công việc hoặc bằng chứng.
- Người đề xuất.
- Người review/phê duyệt.
- Ngày hiệu lực.
- Tài liệu và test liên quan cần cập nhật.

### Không sửa hồ sơ lịch sử để làm đẹp kết quả

Nếu phát hiện báo cáo cũ sai, cần tạo bản sửa hoặc ghi chú bổ sung theo cơ chế có lịch sử. Không nên thay thế âm thầm hồ sơ đã dùng cho quyết định trước đó, đặc biệt khi cần kiểm toán.

## 16. Bảo vệ tài liệu và bằng chứng

Tài liệu kiểm thử có thể chứa dữ liệu nhạy cảm, thông tin cấu hình hoặc chi tiết bảo mật. Quyền truy cập cần phù hợp với nội dung.

Cần xem xét:

- Phân loại tài liệu theo mức độ nhạy cảm.
- Giới hạn quyền đọc, sửa, xóa và phê duyệt.
- Không lưu mật khẩu, token hoặc private key trực tiếp.
- Dùng liên kết đến secret manager hoặc kho được bảo vệ.
- Ẩn danh dữ liệu trong ảnh chụp, log và ví dụ.
- Đặt thời hạn lưu cho artifact và hồ sơ.
- Có bản sao lưu hoặc cơ chế khôi phục tài liệu quan trọng.
- Ghi nhận thay đổi và truy cập khi chính sách yêu cầu.

Không phải mọi tài liệu đều cần kiểm soát nghiêm ngặt như hồ sơ kiểm toán. Nhưng mọi tài liệu cần có cách xử lý phù hợp với loại thông tin chứa trong đó.

## 17. Giữ tài liệu ngắn gọn nhưng đủ dùng

Độ dài không phải tiêu chí chất lượng. Một tài liệu tốt giúp người đọc tìm câu trả lời nhanh và hiểu giới hạn của thông tin.

### Cấu trúc dễ dùng

- Mục đích và đối tượng.
- Phạm vi và điều không bao gồm.
- Vai trò và trách nhiệm.
- Các bước hoặc quy tắc chính.
- Điều kiện và ngoại lệ.
- Ví dụ hoặc minh họa.
- Liên kết đến nguồn chi tiết.
- Chủ sở hữu và ngày review.

### Dùng liên kết thay cho sao chép

Nếu quy tắc API đã được mô tả trong tài liệu hợp đồng, test plan nên liên kết thay vì chép lại toàn bộ. Nếu cách chạy test đã có trong README, ticket có thể dẫn đến hướng dẫn đó.

Cần bảo đảm liên kết ổn định và có quyền truy cập phù hợp. Một tài liệu chỉ có liên kết đến nơi người đọc không thể mở không thực sự giải quyết nhu cầu.

### Dùng bảng và sơ đồ khi chúng làm rõ quan hệ

Bảng phù hợp với vai trò, ma trận bao phủ, trạng thái và tiêu chí. Sơ đồ phù hợp với luồng, phụ thuộc và chuyển giao. Không cần thêm hình thức nếu vài câu rõ ràng đã đủ.

## 18. Tránh tài liệu quá mức và tài liệu thiếu mức

### Dấu hiệu tài liệu quá mức

- Nhiều tài liệu lặp cùng nội dung.
- Mọi thay đổi nhỏ đều cần biểu mẫu dài.
- Người viết dành nhiều thời gian cập nhật trạng thái hơn thực hiện kiểm thử.
- Tài liệu chi tiết nhưng không được sử dụng trong quyết định.
- Nội dung lỗi thời vì phải đồng bộ thủ công ở nhiều nơi.
- Không ai biết đâu là nguồn chính.

Cách cải thiện là loại bỏ bản sao, liên kết nguồn chính, tự động hóa dữ liệu có thể sinh và giảm trường không phục vụ quyết định.

### Dấu hiệu tài liệu thiếu mức

- Không ai biết phạm vi kiểm thử.
- Không rõ phiên bản hoặc dữ liệu đã dùng.
- Không thể tái hiện kết quả.
- Quyết định phát hành không có bằng chứng.
- Người mới không thể thiết lập môi trường.
- Không biết ai phê duyệt ngoại lệ.
- Sự cố không có runbook hoặc đầu mối.
- Không thể chứng minh yêu cầu quan trọng đã được xác minh.

Cách cải thiện là bổ sung đúng thông tin còn thiếu, bắt đầu từ rủi ro và câu hỏi cần trả lời thay vì tạo thêm tài liệu theo mẫu chung.

## 19. Quy trình chọn mức tài liệu cho một thay đổi

Có thể dùng quy trình ngắn sau khi bắt đầu một tính năng hoặc thay đổi.

### Bước 1: Xác định quyết định và người đọc

Tài liệu sẽ hỗ trợ ai? Họ cần quyết định về phạm vi, chất lượng, phát hành, vận hành hay tuân thủ?

### Bước 2: Đánh giá rủi ro và độ phức tạp

Xem người dùng, dữ liệu, giao dịch, bảo mật, phụ thuộc, khả năng rollback và phạm vi lan truyền.

### Bước 3: Xác định yêu cầu chứng minh

Cần ghi lại những gì để giải thích kết quả? Có cần truy vết, phê duyệt, lịch sử và lưu giữ chính thức không?

### Bước 4: Chọn tài liệu tối thiểu

Chọn các loại tài liệu cần thiết: ticket, checklist, test plan, test design, báo cáo, runbook, ma trận truy vết hoặc hồ sơ phê duyệt.

### Bước 5: Xác định chủ sở hữu và nguồn chính

Ai viết, ai review, ai phê duyệt, lưu ở đâu và tài liệu nào là nguồn chính?

### Bước 6: Gắn cập nhật vào quy trình

Xác định sự kiện làm tài liệu cần cập nhật: thay đổi yêu cầu, API, schema, môi trường, quy trình hoặc kết quả kiểm thử.

### Bước 7: Kiểm tra khả năng sử dụng

Đưa tài liệu cho một người khác trong nhóm đọc và thực hiện công việc. Nếu họ không thể tìm thông tin hoặc hiểu điều kiện, cần cải thiện cấu trúc hoặc nội dung.

## 20. Ví dụ: chọn tài liệu cho ba thay đổi khác nhau

### Thay đổi A: sửa nhãn và khoảng cách giao diện

Rủi ro thấp, không ảnh hưởng dữ liệu hoặc logic nghiệp vụ.

Tài liệu phù hợp:

- Ticket có mô tả và tiêu chí.
- Ảnh hoặc ghi chú giao diện mong đợi nếu cần.
- Checklist kiểm tra màn hình và nền tảng liên quan.
- Kết quả CI hoặc ghi chú xác nhận.

Không cần chiến lược riêng hoặc báo cáo dài.

### Thay đổi B: thêm quy tắc tính phí vận chuyển

Thay đổi ảnh hưởng nghiệp vụ, giá trị tiền và nhiều trường hợp dữ liệu.

Tài liệu phù hợp:

- Yêu cầu và bảng quyết định quy tắc.
- Phân tích rủi ro và tiêu chí chấp nhận.
- Test design cho vùng giá trị, địa chỉ, loại hàng và ngoại lệ.
- Dữ liệu kiểm thử đại diện.
- Kết quả kiểm thử và báo cáo lỗi.
- Ghi chú triển khai nếu có thay đổi cấu hình.

Nghiệp vụ cần xác nhận quy tắc tính phí; QA thiết kế kiểm thử; developer xác minh logic; vận hành xác nhận cấu hình và quan sát nếu cần.

### Thay đổi C: chuyển dịch vụ thanh toán sang nhà cung cấp mới

Thay đổi có nhiều phụ thuộc, dữ liệu giao dịch và rủi ro vận hành.

Tài liệu phù hợp:

- Chiến lược và kế hoạch kiểm thử theo giai đoạn.
- Sơ đồ luồng và ma trận phụ thuộc.
- Hợp đồng API và webhook.
- Ma trận tương thích và kế hoạch chuyển đổi.
- Kiểm thử thành công, từ chối, timeout, retry và idempotency.
- Kế hoạch đối soát dữ liệu và giao dịch.
- Phương án rollback hoặc chuyển tiếp.
- Runbook, dashboard, cảnh báo và đầu mối hỗ trợ.
- Báo cáo kiểm thử, lỗi còn mở và quyết định phát hành.
- Hồ sơ phê duyệt theo thẩm quyền.

Cùng một module sản phẩm có thể cần nhiều mức tài liệu tùy phạm vi thay đổi. Không nên áp dụng một bộ biểu mẫu cố định cho mọi ticket.

## 21. Ví dụ: chọn mức tài liệu theo quy mô nhóm

Giả sử một nhóm gồm bốn người duy trì một ứng dụng nội bộ. Nhóm làm việc cùng nhau, triển khai hàng tuần và có thể rollback nhanh. Bộ tài liệu có thể gồm README, tiêu chí trong ticket, test tự động trong repository, checklist phát hành và runbook ngắn.

Khi ứng dụng tăng lên ba nhóm, có nhiều dịch vụ và một nhóm vận hành riêng, nhóm cần bổ sung chiến lược kiểm thử chung, hợp đồng API, trách nhiệm, hướng dẫn môi trường, ma trận phụ thuộc, quy trình triage và báo cáo theo phạm vi.

Khi sản phẩm xử lý giao dịch quan trọng hoặc chịu yêu cầu kiểm toán, cần thêm truy vết, phê duyệt, lịch sử phiên bản, hồ sơ thực thi và quy tắc lưu giữ. Mức tài liệu tăng vì nhu cầu chứng minh và hậu quả của lỗi tăng, không đơn thuần vì số lượng nhân sự.

## 22. Ví dụ: xây dựng bộ tài liệu tối thiểu cho một nhóm Agile

Một nhóm Agile có thể duy trì tài liệu bằng cách phân bổ thông tin vào các nơi làm việc hiện có:

| Nhu cầu | Nơi lưu phù hợp | Nội dung tối thiểu |
|---|---|---|
| Mục tiêu và quy tắc | Story/ticket | Mục tiêu, phạm vi, tiêu chí chấp nhận |
| Rủi ro | Ticket hoặc trang tính năng | Rủi ro chính và cách xác minh |
| Cách kiểm thử | Test file, checklist hoặc charter | Điều kiện, dữ liệu và kết quả mong đợi |
| Cách chạy | README hoặc hướng dẫn repository | Lệnh, cấu hình và phụ thuộc |
| Kết quả | CI và ticket | Phiên bản, trạng thái, log và lỗi |
| Quyết định | Decision record hoặc ticket | Lựa chọn, lý do và người quyết định |
| Vận hành | Runbook | Giám sát, xử lý và phục hồi |

Trong refinement, nhóm xác định thông tin còn thiếu. Trong review, nhóm xem thay đổi và tài liệu liên quan. Trong retrospective, nhóm xem tài liệu nào khó dùng hoặc đã lỗi thời. Cách này giúp tài liệu phát triển cùng công việc mà không cần tạo một giai đoạn viết hồ sơ riêng ở cuối sprint.

## 23. Đo lường chất lượng và mức sử dụng tài liệu

Không nên đánh giá tài liệu bằng số trang hoặc số tệp. Hãy xem tài liệu có giúp người dùng thực hiện công việc và ra quyết định tốt hơn không.

Các tín hiệu hữu ích:

- Người mới có thể thiết lập môi trường trong thời gian hợp lý không?
- Người trực có thể xử lý tình huống theo runbook không?
- Có thể truy vết yêu cầu quan trọng đến kết quả kiểm thử không?
- Người phê duyệt có thể hiểu rủi ro còn lại không?
- Tài liệu có được cập nhật cùng thay đổi liên quan không?
- Có nhiều câu hỏi lặp lại vì hướng dẫn thiếu hoặc khó tìm không?
- Có tài liệu quan trọng nào không có chủ sở hữu không?
- Tỷ lệ liên kết hỏng hoặc nội dung lỗi thời là bao nhiêu?
- Thời gian tìm bằng chứng cho một quyết định có giảm không?

### Tránh chỉ số gây hành vi sai

Không nên đặt mục tiêu tăng số trang, số checklist hoặc tỷ lệ tài liệu được tạo. Những mục tiêu này có thể khiến nhóm tạo hồ sơ không cần thiết.

Tốt hơn là đo khả năng tìm kiếm, tính đúng đắn, độ đầy đủ theo nhu cầu và mức độ sử dụng trong công việc.

## 24. Checklist rà soát mức tài liệu

### Mục đích và người dùng

- [ ] Đã xác định quyết định hoặc công việc mà tài liệu hỗ trợ.
- [ ] Đã xác định đối tượng đọc chính.
- [ ] Nội dung trả lời được câu hỏi mà người đọc cần.
- [ ] Phạm vi và giới hạn được nêu rõ.

### Rủi ro và bằng chứng

- [ ] Mức tài liệu phù hợp với tác động và khả năng khắc phục.
- [ ] Đã xem xét dữ liệu, bảo mật, vận hành và phụ thuộc.
- [ ] Yêu cầu chứng minh và lưu giữ đã được xác định.
- [ ] Bằng chứng có phiên bản, thời điểm và nguồn phù hợp.

### Cấu trúc và nguồn chính

- [ ] Chọn đúng loại tài liệu.
- [ ] Tránh sao chép nội dung đã có nguồn chính.
- [ ] Có liên kết ổn định và quyền truy cập phù hợp.
- [ ] Người dùng có thể tìm thông tin cần thiết.

### Sở hữu và vòng đời

- [ ] Có người sở hữu và người review khi cần.
- [ ] Có quy tắc cập nhật theo thay đổi.
- [ ] Phiên bản và lịch sử được quản lý phù hợp.
- [ ] Quyền truy cập và thời hạn lưu được xác định.
- [ ] Có cách phát hiện tài liệu lỗi thời.

### Khả năng sử dụng

- [ ] Nội dung đủ rõ để người khác thực hiện công việc.
- [ ] Ví dụ, bảng hoặc sơ đồ giúp làm rõ vấn đề.
- [ ] Không chứa bí mật hoặc dữ liệu nhạy cảm không phù hợp.
- [ ] Có thể kiểm tra hoặc xác minh thông tin quan trọng.

## 25. Mẫu quyết định mức tài liệu cho một thay đổi

~~~text
TÊN THAY ĐỔI:
SẢN PHẨM / THÀNH PHẦN:
NGƯỜI SỞ HỮU:

MỤC TIÊU:
ĐỐI TƯỢNG CẦN ĐỌC:
QUYẾT ĐỊNH CẦN HỖ TRỢ:

RỦI RO:
- Người dùng / nghiệp vụ:
- Dữ liệu / giao dịch:
- Bảo mật / tuân thủ / an toàn:
- Phụ thuộc / tích hợp:
- Khả năng khắc phục:
- Phạm vi lan truyền:

YÊU CẦU CHỨNG MINH:
- Truy vết:
- Người thực hiện / review:
- Phiên bản / môi trường:
- Kết quả / bằng chứng:
- Phê duyệt:
- Thời hạn lưu:

TÀI LIỆU ĐƯỢC CHỌN:
- Ticket / tiêu chí:
- Test strategy / test plan:
- Test design / checklist:
- Báo cáo:
- Runbook:
- Quyết định / phê duyệt:
- Hồ sơ truy vết:

NGUỒN CHÍNH:
CHỦ SỞ HỮU TÀI LIỆU:
NGƯỜI REVIEW:
SỰ KIỆN CẦN CẬP NHẬT:
NGÀY REVIEW:
LÝ DO CHỌN MỨC TÀI LIỆU:
~~~

## 26. Mẫu cấu trúc tài liệu kiểm thử gọn

~~~text
TÊN PHẠM VI / THAY ĐỔI:
MỤC TIÊU:
PHIÊN BẢN:
CHỦ SỞ HỮU:
NGÀY CẬP NHẬT:

1. PHẠM VI
- Trong phạm vi:
- Ngoài phạm vi:
- Giả định:

2. RỦI RO
- Rủi ro chính:
- Tác động:
- Biện pháp kiểm soát:

3. CÁCH KIỂM THỬ
- Tầng kiểm thử:
- Kịch bản / checklist:
- Dữ liệu:
- Môi trường:
- Phụ thuộc:

4. TIÊU CHÍ
- Điều kiện bắt đầu:
- Điều kiện hoàn tất:
- Điều kiện chặn:

5. KẾT QUẢ
- Phiên bản đã kiểm tra:
- Phạm vi đã chạy:
- Passed / Failed / Blocked / Skipped:
- Lỗi còn mở:
- Giới hạn bằng chứng:

6. QUYẾT ĐỊNH
- Khuyến nghị:
- Rủi ro còn lại:
- Người quyết định:
- Phê duyệt:

7. LIÊN KẾT
- Yêu cầu:
- Test:
- Báo cáo:
- Lỗi:
- Runbook:
~~~

## 27. Mẫu danh mục và quản trị tài liệu

~~~text
TÊN TÀI LIỆU:
LOẠI:
MỤC ĐÍCH:
ĐỐI TƯỢNG SỬ DỤNG:
PHẠM VI:

CHỦ SỞ HỮU:
NGƯỜI REVIEW:
NGƯỜI PHÊ DUYỆT:
NGUỒN CHÍNH:
VỊ TRÍ:

PHIÊN BẢN:
NGÀY CẬP NHẬT:
NGÀY REVIEW TIẾP THEO:
SỰ KIỆN KÍCH HOẠT CẬP NHẬT:

MỨC ĐỘ RỦI RO LIÊN QUAN:
YÊU CẦU BẰNG CHỨNG:
QUYỀN TRUY CẬP:
THỜI HẠN LƯU:
TRẠNG THÁI:
GHI CHÚ:
~~~

## 28. Những sai lầm thường gặp

- **Dùng cùng một bộ tài liệu cho mọi thay đổi:** tạo gánh nặng với thay đổi nhỏ và thiếu kiểm soát ở thay đổi lớn.
- **Chọn mức tài liệu theo quy mô nhóm:** bỏ qua tác động, khả năng khắc phục và yêu cầu chứng minh.
- **Đồng nhất tài liệu với biểu mẫu:** điền đủ trường không có nghĩa nội dung hữu ích.
- **Viết tài liệu chỉ để đáp ứng kiểm toán:** hồ sơ không phản ánh hoạt động thực tế.
- **Ghi kết quả mà thiếu phiên bản và môi trường:** không thể tái hiện hoặc giải thích.
- **Sao chép cùng nội dung ở nhiều nơi:** các bản nhanh chóng mâu thuẫn.
- **Không có người sở hữu:** tài liệu lỗi thời nhưng không ai cập nhật.
- **Không phân biệt nguồn chính và bản tham khảo:** người đọc không biết thông tin nào có hiệu lực.
- **Lưu mọi thứ vô thời hạn:** tăng chi phí và rủi ro dữ liệu.
- **Tự động sinh báo cáo nhưng không kiểm tra nguồn:** thông tin sai được phát tán nhanh hơn.
- **Quá tập trung vào số trang:** tài liệu dài nhưng khó tìm câu trả lời.
- **Không xem xét tài liệu trong pull request:** hành vi sản phẩm thay đổi nhưng hướng dẫn vẫn cũ.

## Kết luận

Mức tài liệu phù hợp được quyết định bởi người sử dụng, mục tiêu phối hợp, rủi ro, độ phức tạp, khả năng khắc phục và yêu cầu chứng minh. Thay đổi nhỏ có thể chỉ cần ticket, tiêu chí và kết quả kiểm tra; thay đổi tích hợp cần hợp đồng, dữ liệu, môi trường và kế hoạch phục hồi; hệ thống rủi ro cao hoặc chịu kiểm toán cần truy vết, hồ sơ thực thi, review và phê duyệt có kiểm soát.

Nhóm nên bắt đầu với bộ tài liệu tối thiểu có ích, chỉ bổ sung cấu trúc khi có nhu cầu rõ và gắn việc cập nhật với thay đổi sản phẩm. Mỗi tài liệu quan trọng cần có đối tượng sử dụng, nguồn chính, chủ sở hữu và vòng đời. Khi tài liệu giúp người khác thực hiện công việc, tái hiện kết quả và đưa ra quyết định dựa trên bằng chứng, nó đang phục vụ đúng mục đích của chiến lược kiểm thử.
