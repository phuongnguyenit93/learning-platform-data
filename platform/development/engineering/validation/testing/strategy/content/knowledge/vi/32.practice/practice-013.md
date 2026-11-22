# Trình bày quyết định phát hành khi bằng chứng hoặc nguồn lực chưa đầy đủ

## 1. Mục tiêu thực hành

Trong thực tế, nhóm có thể phải đưa ra quyết định phát hành khi thời gian kiểm thử bị rút ngắn, môi trường chưa sẵn sàng, một số kết quả chưa thể tái lập, chuyên gia nghiệp vụ chưa xác nhận, hoặc nguồn lực để hoàn tất kiểm tra không còn đủ. Đây là tình huống cần trình bày rõ ràng vì người ra quyết định phải hiểu điều gì đã được xác nhận, điều gì còn chưa biết, rủi ro nào có thể phát sinh và lựa chọn nào đang được đề xuất.

Mục tiêu của bài thực hành là xây dựng một bản trình bày quyết định phát hành trung thực, có cấu trúc và có thể kiểm tra. Bản trình bày phải giúp người có thẩm quyền lựa chọn giữa tiếp tục phát hành, phát hành giới hạn hoặc có điều kiện, trì hoãn, hay dừng để xử lý. Người trình bày không được biến việc thiếu bằng chứng thành kết luận đạt, cũng không được che giấu hạn chế nguồn lực hoặc giả định chưa xác minh.

Một quyết định tốt không nhất thiết phải có mọi thông tin hoàn hảo. Nó cần phân biệt rõ dữ kiện và giả định, chỉ ra khoảng trống ảnh hưởng đến quyết định, nêu phương án khả thi và điều kiện kiểm soát, đồng thời xác định ai có thẩm quyền chấp thuận rủi ro còn lại. Một số yêu cầu bắt buộc theo chính sách, hợp đồng, pháp luật hoặc an toàn có thể không được phép miễn trừ; khi đó phải dừng hoặc thu hẹp phạm vi cho đến khi có bằng chứng đáp ứng.

## 2. Nhận diện loại thiếu hụt trước khi đề xuất quyết định

Không phải mọi khoảng trống đều giống nhau. Trước tiên hãy phân loại nguyên nhân và ảnh hưởng của nó.

| Loại thiếu hụt | Ví dụ | Câu hỏi cần làm rõ |
|---|---|---|
| Thiếu bằng chứng kiểm thử | Chưa chạy kiểm thử tải, chưa có kết quả hồi quy cho một luồng quan trọng | Điều gì chưa được kiểm tra, vì sao, và có thể thu thập bằng chứng thay thế đáng tin cậy không? |
| Bằng chứng không đủ tin cậy | Test chập chờn, log thiếu phiên bản, môi trường khác cấu hình phát hành | Kết quả có thể đại diện cho bản phát hành hiện tại không? Có thể tái lập không? |
| Thiếu xác nhận nghiệp vụ | Chủ sở hữu nghiệp vụ chưa duyệt kết quả hoặc dữ liệu biên | Ai có quyền xác nhận, và điều gì có thể xảy ra nếu giả định hiện tại sai? |
| Thiếu kiểm tra vận hành | Chưa diễn tập rollback, cảnh báo chưa được kiểm chứng, runbook chưa cập nhật | Nhóm có thể phát hiện và khôi phục khi sự cố xảy ra không? |
| Thiếu nguồn lực | Thiếu người kiểm thử, môi trường, thiết bị, dữ liệu hoặc thời gian | Phần nào có thể ưu tiên, giảm phạm vi hoặc bổ sung nguồn lực? |
| Thiếu phụ thuộc bên ngoài | Đối tác chưa cấp sandbox, dịch vụ ngoài chưa sẵn sàng | Có contract test, mô phỏng, xác nhận có kiểm soát hoặc phương án thay thế nào? |
| Thiếu thông tin về rủi ro | Chưa rõ phạm vi ảnh hưởng, dữ liệu bị tác động hoặc mức độ nghiêm trọng | Cần khảo sát thêm trước khi ra quyết định hay có thể giới hạn tác động? |

Phân biệt “chưa chạy”, “đã chạy nhưng thất bại”, “không thể kết luận” và “đạt”. Đây là những trạng thái khác nhau. Ví dụ, không có kết quả kiểm thử tải không chứng minh hiệu năng kém, nhưng cũng không chứng minh hiệu năng đạt. Một test thất bại do môi trường có thể chưa nói gì về chức năng, song vẫn cho thấy bằng chứng hiện tại chưa đủ để kết luận.

## 3. Xác định phạm vi quyết định và mức độ quan trọng

Trước khi trình bày, ghi rõ quyết định đang được yêu cầu cho phiên bản, bản dựng, môi trường, nhóm người dùng và phạm vi chức năng nào. Không trình bày chung chung “có nên phát hành hay không” nếu có thể tách thành các phần có mức rủi ro khác nhau.

Hãy phân loại phạm vi theo các khía cạnh:

- **Thành phần thay đổi:** dịch vụ, API, giao diện, schema, tác vụ nền, cấu hình hoặc tích hợp bị tác động.
- **Luồng nghiệp vụ:** hành trình nào thay đổi và hành trình nào phụ thuộc vào thành phần đó.
- **Dữ liệu:** loại dữ liệu được đọc, ghi, chuyển đổi hoặc gửi ra bên ngoài; khả năng khôi phục dữ liệu.
- **Đối tượng chịu ảnh hưởng:** người dùng nội bộ, khách hàng, nhóm vận hành, đối tác hoặc hệ thống phụ thuộc.
- **Mức triển khai:** toàn bộ người dùng, một nhóm nhỏ, một khu vực, một tenant, một phần lưu lượng hoặc môi trường thử nghiệm.
- **Thời hạn và phụ thuộc:** mốc phát hành, cam kết, điều kiện kỹ thuật và nguồn lực còn lại.

Một thiếu hụt có thể chấp nhận được trong một phạm vi thử nghiệm nội bộ nhưng không phù hợp với phát hành rộng. Ngược lại, nếu có thể tắt riêng tính năng mới và giữ nguyên phần ổn định, nhóm có thể đề xuất phát hành phần không bị ảnh hưởng trong khi tiếp tục xác minh phần còn lại. Mọi giới hạn phải có cách thực thi và kiểm chứng rõ ràng.

## 4. Lập bảng bằng chứng: điều đã biết và điều chưa biết

Đây là phần trọng tâm của bản trình bày. Với từng mục tiêu chất lượng hoặc tiêu chí phát hành, ghi trạng thái bằng chứng, nguồn, phạm vi và mức độ tin cậy.

| Tiêu chí / mục tiêu | Trạng thái | Bằng chứng hiện có | Khoảng trống | Ảnh hưởng đến quyết định |
|---|---|---|---|---|
| Luồng nghiệp vụ chính | Đạt / Không đạt / Chưa đủ bằng chứng | Mã lần chạy, phiên bản, dữ liệu và kết quả | Trường hợp biên hoặc vai trò chưa được kiểm tra | Có thể ảnh hưởng trực tiếp tới khả năng sử dụng |
| Hồi quy thành phần liên quan | Chưa đủ bằng chứng | Một số test mục tiêu đã chạy | Chưa có bộ hồi quy đầy đủ | Không biết chắc tác động lan sang phần phụ thuộc |
| Hiệu năng | Chưa chạy | Số liệu môi trường trước đó | Thiếu tải đại diện cho phiên bản mới | Chưa thể xác nhận mục tiêu hiệu năng |
| Bảo mật | Đang xử lý / Chưa đủ bằng chứng | Kết quả quét và hồ sơ phát hiện | Một phát hiện chưa được phân loại hoặc xác minh | Có thể là điều kiện chặn theo chính sách |
| Khả năng khôi phục | Chưa đủ bằng chứng | Runbook và bản sao lưu hiện có | Chưa diễn tập phục hồi với thay đổi dữ liệu này | Rủi ro khôi phục có thể cao |

Các trạng thái trong bảng cần theo quy ước đã thống nhất của tổ chức. Không dùng màu sắc hoặc biểu tượng thay cho giải thích. Mỗi kết quả quan trọng nên liên kết đến báo cáo, log, bản dựng, cấu hình và thời điểm thực hiện. Nếu kết quả dựa trên môi trường khác, phải nêu rõ khác biệt và đánh giá khả năng đại diện.

Đối với bằng chứng chưa có, ghi nguyên nhân: thiếu thời gian, môi trường, dữ liệu, người thực hiện, công cụ hoặc phụ thuộc bên ngoài. Sau đó xác định khả năng khắc phục và thời gian cần thiết. Việc nêu nguyên nhân giúp phân biệt khoảng trống có thể đóng nhanh với rủi ro cấu trúc cần kế hoạch dài hơn.

## 5. Đánh giá rủi ro còn lại và mức độ không chắc chắn

Rủi ro còn lại là phần rủi ro vẫn tồn tại sau các biện pháp kiểm soát đã thực hiện. Khi bằng chứng chưa đầy đủ, mức độ không chắc chắn thường tăng. Không nên trình bày một điểm rủi ro duy nhất nếu chưa có căn cứ; hãy giải thích các chiều đánh giá và giả định.

Với từng khoảng trống, xem xét:

1. **Tác động:** nếu giả định sai hoặc lỗi xảy ra, hậu quả đối với người dùng, dữ liệu, an toàn, bảo mật, tài chính và vận hành là gì?
2. **Khả năng xảy ra:** lịch sử lỗi, độ phức tạp thay đổi, số phụ thuộc và mức độ mới của công nghệ cho biết điều gì?
3. **Khả năng phát hiện:** log, metric, cảnh báo, hỗ trợ khách hàng hoặc kiểm tra sau triển khai có thể nhận biết lỗi nhanh không?
4. **Khả năng khôi phục:** có thể tắt tính năng, quay lui mã, khôi phục dữ liệu hoặc xử lý bù không?
5. **Phạm vi lan truyền:** lỗi có ảnh hưởng một nhóm nhỏ hay có thể lan sang nhiều hệ thống và người dùng?
6. **Độ tin cậy của nhận định:** kết luận dựa trên dữ liệu thực, kinh nghiệm, giả định hay suy đoán?

Hãy phân biệt rủi ro có thể giảm bằng biện pháp vận hành với rủi ro cần bằng chứng kỹ thuật. Ví dụ, giám sát tăng cường có thể giúp phát hiện lỗi hiệu năng sau triển khai nhưng không thay thế việc chứng minh một yêu cầu bảo mật bắt buộc. Tương tự, kế hoạch rollback không thay thế kiểm thử migration nếu dữ liệu đã chuyển đổi không thể khôi phục an toàn.

Nếu rủi ro liên quan đến nghĩa vụ pháp lý, an toàn, quyền riêng tư, bảo mật hoặc hợp đồng, cần kiểm tra chính sách và thẩm quyền áp dụng. Không mặc định rằng người quản lý dự án hoặc chủ sản phẩm có quyền miễn trừ mọi điều kiện. Nếu không có cơ chế chấp thuận hợp lệ, phải coi điều kiện đó là chưa được đáp ứng.

## 6. Xây dựng các phương án quyết định

Không nên chỉ đưa ra một lựa chọn duy nhất. Trình bày các phương án thực tế, hệ quả và điều kiện đi kèm để người có thẩm quyền có thể cân nhắc.

| Phương án | Khi phù hợp | Điều kiện và hệ quả cần nêu |
|---|---|---|
| Phát hành theo kế hoạch | Các điều kiện bắt buộc đã đạt và khoảng trống còn lại nằm trong mức chấp nhận được theo quy trình | Bằng chứng đạt, rủi ro còn lại và chủ sở hữu theo dõi |
| Phát hành giới hạn hoặc theo giai đoạn | Có thể giới hạn người dùng, lưu lượng, khu vực hoặc tính năng; tác động có thể quan sát và dừng | Cơ chế giới hạn, tiêu chí mở rộng, điều kiện dừng và người giám sát |
| Phát hành có điều kiện | Quy trình cho phép chấp nhận một số rủi ro cụ thể và có biện pháp kiểm soát hữu hiệu | Người phê duyệt, ngoại lệ hợp lệ, thời hạn, kiểm soát bù và kế hoạch khắc phục |
| Trì hoãn để hoàn tất bằng chứng | Khoảng trống ảnh hưởng lớn hoặc có thể đóng trong thời gian hợp lý | Công việc còn lại, nguồn lực, thời hạn mới và bằng chứng cần đạt |
| Dừng hoặc quay lại phương án ổn định | Có lỗi nghiêm trọng, điều kiện bắt buộc chưa đạt hoặc không thể kiểm soát tác động | Cách bảo vệ dữ liệu, thông báo, khôi phục và điều kiện đánh giá lại |

Phương án phát hành giới hạn chỉ có ý nghĩa nếu giới hạn có thể thực thi và kiểm tra. Ví dụ, cờ tính năng phải được xác nhận hoạt động, phân đoạn người dùng phải chính xác, giới hạn lưu lượng phải được giám sát và nhóm vận hành phải biết cách dừng. Một lời hứa “sẽ theo dõi kỹ” mà không có người, công cụ và điều kiện hành động không phải là biện pháp kiểm soát đầy đủ.

## 7. Chọn phương án và trình bày lý do

Đề xuất cần gắn trực tiếp với bằng chứng và rủi ro. Trình bày vì sao phương án được chọn phù hợp với phạm vi và mục tiêu, đồng thời nêu rõ đánh đổi. Nếu đề xuất trì hoãn, chỉ ra bằng chứng nào cần hoàn tất và tại sao việc chờ sẽ giảm rủi ro. Nếu đề xuất phát hành giới hạn, giải thích cách giới hạn làm giảm phạm vi tác động và cách nhóm biết khi nào cần dừng.

Một cấu trúc lập luận ngắn gọn gồm:

- **Dữ kiện:** điều đã được xác nhận bằng nguồn có thể truy xuất.
- **Khoảng trống:** điều chưa được xác nhận, nguyên nhân và phạm vi ảnh hưởng.
- **Rủi ro:** hậu quả có thể xảy ra, mức độ không chắc chắn và khả năng phát hiện/khôi phục.
- **Phương án:** lựa chọn được đề xuất và các lựa chọn thay thế.
- **Điều kiện:** biện pháp kiểm soát, người chịu trách nhiệm, thời hạn và tiêu chí dừng/mở rộng.
- **Quyết định cần phê duyệt:** câu hỏi cụ thể dành cho đúng người có thẩm quyền.

Tránh dùng ngôn ngữ làm nhẹ vấn đề như “chỉ còn vài test”, “rủi ro thấp” hoặc “không có vấn đề lớn” nếu không có số liệu và phạm vi rõ ràng. Không biến một dự báo thành kết quả thực tế. Nếu nhóm không biết xác suất xảy ra, hãy nói rõ chưa đủ dữ liệu để ước lượng và mô tả căn cứ định tính.

## 8. Điều kiện cho một quyết định phát hành có điều kiện

Phát hành có điều kiện chỉ phù hợp khi quy trình của tổ chức cho phép và người có thẩm quyền chấp thuận rõ ràng. Một hồ sơ có thể cần các nội dung sau:

1. **Rủi ro cụ thể được chấp nhận:** mô tả tiêu chí chưa đạt hoặc chưa đủ bằng chứng, phiên bản và phạm vi ảnh hưởng.
2. **Cơ sở chấp thuận:** lý do kinh doanh hoặc vận hành, dữ liệu hiện có và các lựa chọn đã cân nhắc.
3. **Thẩm quyền:** người hoặc vai trò có quyền chấp nhận rủi ro, bằng chứng phê duyệt và thời điểm.
4. **Giới hạn:** tính năng, nhóm người dùng, lưu lượng, môi trường hoặc thời gian áp dụng.
5. **Kiểm soát bù:** giám sát, cảnh báo, kiểm tra thủ công, hỗ trợ trực, giới hạn thao tác hoặc phương án giảm tác động.
6. **Điều kiện dừng:** sự kiện hoặc ngưỡng đã thống nhất khiến nhóm ngừng mở rộng, tắt tính năng hoặc quay lui.
7. **Kế hoạch khắc phục:** công việc, người phụ trách, nguồn lực, mốc hoàn thành và bằng chứng đóng rủi ro.
8. **Thời hạn và xem xét lại:** ngày hết hiệu lực hoặc sự kiện bắt buộc đánh giá lại.

Một ngoại lệ phải bao phủ chính xác phiên bản, thành phần, môi trường và tình huống được đề xuất. Phê duyệt cũ không tự động áp dụng cho bản dựng hoặc phạm vi mới. Nếu điều kiện kiểm soát không còn được đáp ứng, ngoại lệ có thể mất cơ sở sử dụng và cần trình lại theo quy trình.

Không dùng phát hành có điều kiện để lách một yêu cầu bắt buộc không cho phép miễn trừ. Nếu chưa rõ điều kiện có thể được miễn hay không, phải xác minh chính sách và thẩm quyền trước khi đề xuất. Nếu không thể xác minh trong thời gian quyết định, trình bày trạng thái là chưa đủ căn cứ và đề xuất phương án an toàn phù hợp.

## 9. Phân bổ nguồn lực còn lại theo ưu tiên

Khi thiếu người hoặc thời gian, lập danh sách công việc còn lại và chọn phần có giá trị giảm rủi ro cao nhất. Không phân bổ chỉ dựa trên việc test nào dễ hoàn tất trước.

Với mỗi công việc, ghi:

- Rủi ro mà công việc giúp giảm.
- Phạm vi được xác nhận và bằng chứng dự kiến.
- Thời lượng, kỹ năng và môi trường cần thiết.
- Phụ thuộc có thể làm chậm hoặc khiến kết quả không đáng tin cậy.
- Người thực hiện và người xem xét kết quả.
- Công việc khác bị trì hoãn nếu nguồn lực được chuyển sang đây.

Có thể ưu tiên theo thứ tự: điều kiện bắt buộc và rủi ro an toàn/bảo mật; luồng nghiệp vụ có tác động cao; dữ liệu và khả năng khôi phục; ranh giới tích hợp quan trọng; rồi mới đến cải thiện ít ảnh hưởng hơn. Thứ tự cụ thể phải dựa trên chính sách, mức độ nghiêm trọng và bối cảnh sản phẩm.

Nếu nguồn lực hiện có không đủ để tạo bằng chứng cho một rủi ro quan trọng, hãy trình bày đó là quyết định về nguồn lực và mức chấp nhận rủi ro, không che nó bằng cách giảm phạm vi kiểm thử trên giấy. Có thể đề xuất bổ sung người có chuyên môn, mượn môi trường, chia đợt phát hành hoặc điều chỉnh mốc thời gian.

## 10. Mẫu bản trình bày quyết định phát hành

Mẫu dưới đây có thể dùng làm tài liệu ngắn trong cuộc họp phát hành hoặc làm phần tóm tắt của hồ sơ quyết định. Thay nội dung trong ngoặc bằng dữ liệu của bản phát hành cụ thể.

```markdown
# Quyết định phát hành: [Tên phiên bản / bản dựng]

## 1. Quyết định cần đưa ra
- Phạm vi và thời điểm:
- Người có thẩm quyền:
- Các lựa chọn cần xem xét:

## 2. Tóm tắt tình trạng
- Điều kiện đã đạt:
- Điều kiện không đạt:
- Điều kiện chưa đủ bằng chứng:
- Điều kiện bắt buộc còn mở:

## 3. Bằng chứng và khoảng trống
| Tiêu chí | Trạng thái | Bằng chứng | Khoảng trống / ảnh hưởng |
|---|---|---|---|
| ... | ... | ... | ... |

## 4. Rủi ro còn lại
- Tác động:
- Khả năng xảy ra / độ không chắc chắn:
- Khả năng phát hiện:
- Khả năng khôi phục:

## 5. Phương án
- Phát hành theo kế hoạch:
- Phát hành giới hạn / có điều kiện:
- Trì hoãn:
- Dừng / quay lại phiên bản ổn định:

## 6. Đề xuất và lý do
[Nêu lựa chọn, bằng chứng hỗ trợ và đánh đổi.]

## 7. Điều kiện kiểm soát
- Giới hạn phạm vi:
- Giám sát và cảnh báo:
- Điều kiện dừng / rollback:
- Người chịu trách nhiệm:
- Thời hạn khắc phục:

## 8. Phê duyệt và theo dõi
- Người phê duyệt và thời điểm:
- Rủi ro được chấp nhận:
- Việc còn lại, chủ sở hữu và hạn hoàn thành:
- Mốc / sự kiện xem xét lại:
```

Nếu cuộc họp cần một trang tóm tắt, giữ lại quyết định cần đưa ra, các khoảng trống trọng yếu, rủi ro, đề xuất và điều kiện dừng. Đặt bảng bằng chứng chi tiết và báo cáo kỹ thuật ở phần phụ lục hoặc liên kết để người cần có thể kiểm tra.

## 11. Ví dụ thực hành: phát hành tính năng báo cáo khi thiếu kiểm thử tải

### 11.1. Bối cảnh giả định

Một phiên bản bổ sung chức năng báo cáo tổng hợp. Kiểm thử chức năng trên dữ liệu mẫu đã đạt và kiểm thử tích hợp với kho dữ liệu đã hoàn tất. Tuy nhiên, môi trường kiểm thử tải chưa được cấp kịp thời nên chưa có kết quả về hiệu năng khi nhiều người dùng truy cập đồng thời. Nhóm vận hành có dashboard cơ bản nhưng chưa diễn tập xử lý khi hàng đợi báo cáo tăng nhanh.

### 11.2. Bằng chứng và khoảng trống

| Mục tiêu | Trạng thái | Bằng chứng hiện có | Khoảng trống |
|---|---|---|---|
| Tạo báo cáo đúng dữ liệu | Đạt trong phạm vi đã chạy | Kết quả so sánh với dữ liệu mẫu và log truy vấn | Chưa kiểm tra mọi biến thể dữ liệu lịch sử |
| Phân quyền báo cáo | Đạt trong các vai trò được kiểm tra | Kết quả kiểm thử API theo vai trò | Cần xác nhận thêm vai trò đặc thù nếu nằm trong phạm vi phát hành |
| Hiệu năng khi truy cập đồng thời | Chưa đủ bằng chứng | Số đo đơn lẻ trong môi trường phát triển | Chưa có tải đại diện và chưa xác định hành vi ở mức tải cao |
| Khả năng vận hành | Chưa đủ bằng chứng | Dashboard cơ bản và runbook hiện có | Chưa diễn tập hàng đợi tăng và xử lý backlog |

### 11.3. Phương án được cân nhắc

- Phát hành rộng ngay: đáp ứng mốc kế hoạch nhưng rủi ro hiệu năng và vận hành chưa được định lượng.
- Trì hoãn toàn bộ phiên bản: cho phép hoàn tất kiểm thử tải và diễn tập nhưng ảnh hưởng mốc cung cấp các thay đổi đã được xác nhận.
- Phát hành giới hạn: bật tính năng cho một nhóm người dùng hoặc phạm vi báo cáo nhỏ, giới hạn mức sử dụng theo khả năng kỹ thuật, theo dõi hàng đợi và có cơ chế tắt tính năng; hoàn tất kiểm thử tải trước khi mở rộng.

### 11.4. Đề xuất minh họa

Giả sử chính sách phát hành cho phép triển khai theo giai đoạn và không có yêu cầu bắt buộc nào đang bị vi phạm. Nhóm có thể đề xuất phát hành giới hạn nếu cơ chế phân đoạn người dùng, giới hạn sử dụng, dashboard, cảnh báo và thao tác tắt tính năng đã được kiểm chứng. Bản trình bày phải ghi rõ hiệu năng ở tải đại diện vẫn chưa được xác nhận, ai theo dõi hàng đợi, điều kiện dừng đã được phê duyệt và khi nào nhóm chạy kiểm thử tải.

Nếu không thể giới hạn người dùng hoặc không thể phát hiện và dừng khi hệ thống quá tải, phương án phát hành giới hạn không có cơ sở kiểm soát đủ tin cậy. Khi đó, trì hoãn là lựa chọn cần được trình bày. Ví dụ này minh họa cách đánh giá phương án dựa trên biện pháp thực thi, không phải khuyến nghị mặc định cho mọi chức năng báo cáo.

## 12. Cách trình bày trong cuộc họp và xử lý câu hỏi

Mở đầu bằng quyết định cụ thể cần được đưa ra và thời điểm cần quyết định. Sau đó trình bày ngắn gọn trạng thái bằng chứng, khoảng trống quan trọng nhất, rủi ro còn lại, phương án được đề xuất và điều kiện kiểm soát. Không bắt đầu bằng lịch sử dài của dự án nếu thông tin đó không ảnh hưởng đến lựa chọn.

Khi người tham dự hỏi “Có an toàn để phát hành không?”, hãy trả lời theo phạm vi và điều kiện: phần nào đã được xác nhận, phần nào chưa, điều kiện bắt buộc có đáp ứng không, và lựa chọn nào có thể kiểm soát rủi ro. Tránh câu trả lời tuyệt đối khi bằng chứng không hỗ trợ.

Khi được hỏi “Tại sao chưa kiểm tra?”, nêu nguyên nhân cụ thể, tác động của thiếu hụt và kế hoạch đóng khoảng trống. Không đổ lỗi cá nhân; tập trung vào điều kiện nguồn lực, phụ thuộc và cách giải quyết.

Khi được yêu cầu “cứ phát hành rồi kiểm tra sau”, làm rõ điều gì có thể phát hiện sau triển khai, điều gì có thể gây tác động không thể đảo ngược và biện pháp dừng/khôi phục nào đã được kiểm chứng. Kiểm tra sau triển khai chỉ phù hợp với rủi ro có thể quan sát và kiểm soát trong thực tế.

Khi người có thẩm quyền chọn một phương án khác đề xuất, ghi lại quyết định, lý do, rủi ro được chấp nhận, điều kiện và người chịu trách nhiệm. Không tự ghi một đề xuất của nhóm thành quyết định đã được phê duyệt.

## 13. Theo dõi sau quyết định

Sau cuộc họp, cập nhật hồ sơ phát hành và liên kết với bằng chứng nguồn. Mỗi hành động còn lại phải có chủ sở hữu, hạn hoàn thành, đầu ra cần cung cấp và người xác nhận. Nếu có ngoại lệ, ghi phạm vi, ngày hết hiệu lực, người phê duyệt và điều kiện đóng.

Trong quá trình phát hành giới hạn hoặc có điều kiện, theo dõi các chỉ số liên quan trực tiếp đến khoảng trống: tỷ lệ lỗi, độ trễ, hàng đợi, lỗi tích hợp, giao dịch bất thường, cảnh báo bảo mật hoặc phản hồi người dùng. Ghi lại thời điểm, phiên bản và phạm vi người dùng để có thể liên hệ dấu hiệu với thay đổi.

Khi điều kiện dừng xảy ra, người được giao trách nhiệm thực hiện hành động đã phê duyệt, chẳng hạn ngừng mở rộng, tắt tính năng, giảm lưu lượng, quay lui hoặc kích hoạt xử lý sự cố. Khi bằng chứng còn thiếu đã được bổ sung, tổ chức đánh giá lại và quyết định có mở rộng, giữ nguyên giới hạn hay kết thúc ngoại lệ.

## 14. Những lỗi thường gặp khi trình bày quyết định

- **Đồng nhất chưa kiểm tra với đạt:** làm người phê duyệt hiểu sai trạng thái chất lượng. Dùng trạng thái “chưa đủ bằng chứng” và nêu rõ phạm vi.
- **Chỉ nêu thiếu nguồn lực mà không nêu tác động:** người ra quyết định không biết khoảng trống có ý nghĩa gì. Liên kết từng thiếu hụt với rủi ro cụ thể.
- **Chỉ đưa một phương án:** không thể hiện đánh đổi và lựa chọn thay thế. Chuẩn bị các phương án khả thi cùng điều kiện của chúng.
- **Dùng phát hành giới hạn nhưng không có giới hạn thực:** không thể kiểm soát phạm vi ảnh hưởng. Xác minh cờ tính năng, phân đoạn, hạn mức và cách dừng.
- **Dựa vào giám sát để thay thế mọi kiểm thử:** một số lỗi chỉ được phát hiện sau khi gây tác động hoặc không thể quan sát trực tiếp. Xác định loại rủi ro có thể quản lý sau triển khai.
- **Không xác định thẩm quyền:** người không có quyền chấp thuận lại đưa ra quyết định thay tổ chức. Xác nhận vai trò và lưu bằng chứng phê duyệt.
- **Không có hạn hoàn thành cho việc còn lại:** ngoại lệ tạm thời trở thành vĩnh viễn. Giao chủ sở hữu, thời hạn và điều kiện đóng.
- **Trình bày điểm số không có căn cứ:** tạo cảm giác chính xác giả. Nêu dữ liệu, giả định và giới hạn của ước lượng.
- **Không ghi nhận quyết định thực tế sau cuộc họp:** đề xuất và quyết định bị nhầm lẫn. Cập nhật trạng thái, người quyết định và lý do đã thống nhất.

## 15. Checklist trước khi trình quyết định phát hành

1. Phiên bản, bản dựng, môi trường và phạm vi người dùng được xác định rõ.
2. Các tiêu chí bắt buộc và người có thẩm quyền được xác định.
3. Bằng chứng được phân loại rõ: đạt, không đạt, chưa đủ bằng chứng hoặc không áp dụng.
4. Mỗi khoảng trống có nguyên nhân, phạm vi ảnh hưởng và kế hoạch đóng.
5. Rủi ro còn lại được mô tả theo tác động, khả năng xảy ra, phát hiện, khôi phục và độ không chắc chắn.
6. Có nhiều phương án thực tế và đánh đổi của từng phương án.
7. Đề xuất có liên kết với bằng chứng và không che giấu giới hạn.
8. Nếu phát hành có điều kiện, ngoại lệ và thẩm quyền chấp thuận hợp lệ.
9. Giới hạn, giám sát, điều kiện dừng, rollback và người chịu trách nhiệm đã được xác định.
10. Công việc còn lại có chủ sở hữu, thời hạn và bằng chứng hoàn thành.
11. Quyết định, lý do, phê duyệt và mốc xem xét lại sẽ được lưu vết.

## 16. Kết luận

Khi bằng chứng hoặc nguồn lực chưa đầy đủ, bản trình bày quyết định phát hành phải làm rõ điều đã biết, điều chưa biết, ảnh hưởng của khoảng trống và lựa chọn khả thi. Người trình bày cần đưa ra phương án có căn cứ, chỉ rõ rủi ro còn lại, giới hạn và điều kiện dừng, đồng thời bảo đảm người phê duyệt có đúng thẩm quyền.

Quyết định phát hành có thể là tiếp tục, giới hạn, có điều kiện, trì hoãn hoặc dừng. Không có lựa chọn nào phù hợp trong mọi tình huống. Chất lượng quyết định phụ thuộc vào tính trung thực của bằng chứng, sự phù hợp của biện pháp kiểm soát và khả năng truy xuất trách nhiệm sau cuộc họp. Khi có dữ liệu mới hoặc điều kiện thay đổi, nhóm phải xem xét lại theo quy trình đã thống nhất.
