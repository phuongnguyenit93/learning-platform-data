# Thống nhất nguồn xác nhận kết quả mong đợi và người giải thích yêu cầu

Một trường hợp kiểm thử chỉ có thể kết luận đạt hay không đạt khi nhóm biết **kết quả nào được xem là đúng** và **ai có thẩm quyền giải thích ý nghĩa của yêu cầu**. Nếu hai điều này chưa rõ, người kiểm thử có thể viết test case rất chi tiết nhưng vẫn đưa ra kết luận sai: kết quả thực tế khác với điều người viết test nghĩ, trong khi quy tắc nghiệp vụ chưa từng được thống nhất.

Vì vậy, trước khi kiểm thử một yêu cầu quan trọng, nhóm cần thống nhất ba việc: tài liệu hoặc dữ liệu nào làm căn cứ, nguồn nào xác nhận kết quả mong đợi cho từng tình huống, và người nào có trách nhiệm giải thích hoặc phê duyệt khi có nhiều cách hiểu. Đây là một phần của chiến lược kiểm thử dựa trên rủi ro và là điều kiện để kết quả kiểm thử có thể truy vết, thảo luận và sử dụng trong quyết định phát hành.

## 1. Vì sao cần thống nhất nguồn xác nhận?

Yêu cầu phần mềm thường được diễn đạt bằng ngôn ngữ tự nhiên, quy tắc nghiệp vụ, sơ đồ, hợp đồng API, bảng dữ liệu hoặc tiêu chuẩn chất lượng. Một câu như "hoàn tiền nhanh chóng", "người dùng hợp lệ", "đơn hàng đủ điều kiện" hay "hệ thống phản hồi trong thời gian phù hợp" chưa cho biết chính xác điều kiện, giới hạn và kết quả cần kiểm tra.

Ngay cả khi yêu cầu có vẻ rõ, các vai trò khác nhau vẫn có thể hiểu khác nhau. Người làm nghiệp vụ có thể nói "trong vòng bảy ngày" theo ngày lịch; người phát triển có thể hiểu là bảy khoảng thời gian 24 giờ; bộ phận tài chính có thể tính từ thời điểm giao hàng được xác nhận. Nếu nhóm không thống nhất cách hiểu trước, mỗi bên sẽ đánh giá kết quả theo một chuẩn riêng.

Việc thống nhất nguồn xác nhận giúp:

- Người viết kiểm thử và người đánh giá kết quả dùng cùng một căn cứ.
- Phát hiện yêu cầu thiếu, mơ hồ hoặc mâu thuẫn trước khi chúng trở thành lỗi triển khai.
- Phân biệt lỗi sản phẩm với khác biệt trong cách hiểu yêu cầu.
- Tạo khả năng truy vết từ mục tiêu chất lượng đến yêu cầu, trường hợp kiểm thử và bằng chứng.
- Xác định đúng người cần tham gia khi phải giải thích hoặc thay đổi quy tắc.
- Tránh việc kết quả hiện tại của phần mềm vô tình trở thành chuẩn đúng duy nhất.

Thống nhất nguồn không có nghĩa là mọi yêu cầu phải nằm trong một tài liệu duy nhất. Một sản phẩm có thể có nhiều nguồn có thẩm quyền cho các chủ đề khác nhau. Điều cần thống nhất là nguồn nào có giá trị đối với từng yêu cầu, phiên bản nào đang áp dụng và ai có quyền xác nhận khi các nguồn không khớp nhau.

## 2. Phân biệt cơ sở kiểm thử, nguồn xác nhận và người giải thích yêu cầu

Ba khái niệm có liên quan nhưng không đồng nghĩa.

### 2.1. Cơ sở kiểm thử

**Cơ sở kiểm thử (test basis)** là tập hợp thông tin được dùng để phân tích, thiết kế và thực hiện kiểm thử. Cơ sở có thể bao gồm:

- Yêu cầu sản phẩm, câu chuyện người dùng và tiêu chí chấp nhận.
- Quy tắc nghiệp vụ, chính sách và quy trình đã được phê duyệt.
- Thiết kế giao diện, sơ đồ luồng, mô hình dữ liệu và kiến trúc.
- Đặc tả API, hợp đồng sự kiện và thỏa thuận tích hợp.
- Mục tiêu chất lượng, SLO, tiêu chuẩn kỹ thuật và yêu cầu bảo mật.
- Quy định pháp lý, điều khoản hợp đồng và tiêu chuẩn áp dụng.
- Lỗi đã xảy ra, phản hồi người dùng và dữ liệu vận hành có liên quan.

Cơ sở kiểm thử giúp xác định **cần kiểm tra điều gì** và phạm vi nào có liên quan. Một tài liệu chỉ là cơ sở phù hợp khi nhóm biết trạng thái phê duyệt, phạm vi áp dụng và phiên bản của nó.

### 2.2. Nguồn xác nhận kết quả mong đợi

**Nguồn xác nhận kết quả mong đợi (test oracle)** là nguồn thông tin hoặc phương pháp dùng để quyết định kết quả quan sát được có đúng với kết quả cần có hay không. Oracle có thể là một tài liệu được phê duyệt, một tập dữ liệu chuẩn, một công thức, một hợp đồng giao tiếp, một bất biến của hệ thống hoặc một cách so sánh có cơ sở.

Ví dụ:

- Bảng giá và quy tắc làm tròn đã được chủ nghiệp vụ phê duyệt dùng để xác nhận tổng tiền.
- Hợp đồng API đã công bố dùng để xác nhận cấu trúc phản hồi và mã lỗi.
- Tập dữ liệu tham chiếu đã được kiểm định dùng để đối chiếu kết quả nhập hoặc chuyển đổi dữ liệu.
- Quy tắc "một mã giao dịch chỉ được ghi nhận một lần" dùng làm bất biến để kiểm tra tính idempotent.
- SLO đã thống nhất dùng để đánh giá thời gian phản hồi dưới điều kiện tải được xác định.

Oracle không nhất thiết phải là một người hoặc một tài liệu đơn lẻ. Với một số bài toán, nhóm phải kết hợp nhiều nguồn hoặc dùng một thuộc tính có thể kiểm chứng thay cho một kết quả đầu ra cố định.

### 2.3. Người giải thích và người có quyền quyết định

**Người giải thích yêu cầu** là người có kiến thức phù hợp để làm rõ ý nghĩa, bối cảnh, quy tắc và ngoại lệ. **Người có quyền quyết định** là người hoặc vai trò chịu trách nhiệm phê duyệt cách hiểu cuối cùng khi có lựa chọn hoặc xung đột.

Hai trách nhiệm này có thể thuộc cùng một người, nhưng không phải lúc nào cũng vậy. Chuyên gia nghiệp vụ có thể giải thích quy trình đối soát; chủ sở hữu sản phẩm có thể quyết định hành vi sản phẩm được chấp nhận; bộ phận tuân thủ có thể xác nhận cách áp dụng một yêu cầu kiểm soát. Người kiểm thử cần biết ai tư vấn và ai phê duyệt.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Cơ sở kiểm thử | Dựa vào thông tin nào để thiết kế kiểm thử? | Yêu cầu, quy tắc, hợp đồng API |
| Nguồn xác nhận (oracle) | Dựa vào đâu để biết kết quả có đúng? | Công thức đã duyệt, dữ liệu chuẩn, bất biến |
| Người giải thích | Ai hiểu và làm rõ yêu cầu? | Chuyên gia nghiệp vụ, BA, kiến trúc sư |
| Người quyết định | Ai phê duyệt cách hiểu khi có bất đồng? | Chủ sở hữu nghiệp vụ hoặc sản phẩm, người có thẩm quyền |

Một người có thể giữ nhiều vai trò. Dù vậy, nhóm vẫn nên ghi rõ vai trò nào đang được thực hiện để tránh nhầm lẫn giữa tư vấn chuyên môn và quyền phê duyệt.

## 3. Các nguồn thường dùng để xác định kết quả mong đợi

Nguồn phù hợp phụ thuộc vào loại yêu cầu và rủi ro đang kiểm tra. Bảng dưới đây gợi ý những nguồn phổ biến và vai trò nên được hỏi khi cần làm rõ.

| Loại yêu cầu | Nguồn xác nhận thường dùng | Người giải thích hoặc phê duyệt phù hợp |
|---|---|---|
| Quy tắc nghiệp vụ và luồng chức năng | Quy trình đã duyệt, chính sách, tiêu chí chấp nhận, ví dụ nghiệp vụ được phê duyệt | Chủ nghiệp vụ, Product Owner, chuyên gia miền nghiệp vụ |
| Giao tiếp giữa dịch vụ | Đặc tả API, schema, hợp đồng consumer-provider, quy ước sự kiện | Chủ sở hữu API, kiến trúc sư, nhóm cung cấp và sử dụng dịch vụ |
| Dữ liệu và chuyển đổi | Data dictionary, schema, quy tắc mapping, ràng buộc, tập dữ liệu chuẩn | Chủ sở hữu dữ liệu, chuyên gia dữ liệu, chủ nghiệp vụ |
| Tính toán và định giá | Công thức, bảng tham số, quy tắc làm tròn, bộ ví dụ đã kiểm định | Chủ nghiệp vụ, tài chính, chuyên gia lĩnh vực |
| Hiệu năng và độ tin cậy | SLO/SLA, mô hình tải, mục tiêu phục hồi, yêu cầu vận hành | Chủ sản phẩm, kiến trúc sư, SRE hoặc vận hành |
| Bảo mật và quyền riêng tư | Chính sách bảo mật, mô hình phân quyền, yêu cầu kiểm soát, tiêu chuẩn áp dụng | Chủ sở hữu bảo mật, privacy, compliance hoặc người phụ trách kiểm soát |
| Trải nghiệm và khả năng tiếp cận | Luồng UX đã duyệt, nguyên tắc thiết kế, tiêu chí tiếp cận, nghiên cứu người dùng | UX, chuyên gia accessibility, chủ sản phẩm và đại diện người dùng |
| Tương thích và hành vi cũ | Ma trận nền tảng hỗ trợ, cam kết tương thích, phiên bản tham chiếu đã được chấp thuận | Chủ sản phẩm, kiến trúc sư, nhóm vận hành |

Một nguồn có thể hữu ích nhưng chưa đủ thẩm quyền. Chẳng hạn, ảnh chụp màn hình từ môi trường thật cho biết hệ thống đang hiển thị gì, nhưng không chứng minh rằng cách hiển thị đó đúng với chính sách hiện hành. Tương tự, mã nguồn hiện tại cho biết hệ thống đang được triển khai như thế nào, nhưng không tự động xác nhận đó là hành vi được yêu cầu.

Khi sử dụng nguồn tham chiếu, cần ghi nhận ít nhất tên nguồn, chủ sở hữu, phiên bản hoặc ngày hiệu lực, phạm vi áp dụng và trạng thái phê duyệt. Nếu có dữ liệu nhạy cảm, chỉ dùng tập dữ liệu được phép cho môi trường và mục đích kiểm thử.

## 4. Xác định đúng người giải thích yêu cầu

Không nên mặc định người viết yêu cầu, người phát triển hoặc người kiểm thử luôn là người có đủ thẩm quyền trả lời mọi câu hỏi. Hãy chọn người dựa trên nội dung cần làm rõ.

| Vai trò | Trách nhiệm thường gặp khi làm rõ yêu cầu |
|---|---|
| Product Owner hoặc chủ sở hữu sản phẩm | Làm rõ mục tiêu sản phẩm, ưu tiên, hành vi được chấp nhận và quyết định sản phẩm khi có nhiều lựa chọn. |
| Chủ sở hữu nghiệp vụ hoặc chuyên gia miền nghiệp vụ (SME) | Giải thích thuật ngữ, quy trình, quy tắc, ngoại lệ và tác động nghiệp vụ. |
| Business Analyst (BA) | Thu thập, phân tích, cấu trúc yêu cầu; kết nối các bên và ghi lại quyết định. BA thường hỗ trợ làm rõ nhưng quyền phê duyệt phụ thuộc mô hình quản trị. |
| Kiến trúc sư hoặc chủ sở hữu dịch vụ/API | Giải thích ranh giới thành phần, hợp đồng, phụ thuộc, trạng thái lỗi và giới hạn kỹ thuật. |
| Chủ sở hữu dữ liệu | Xác nhận định nghĩa trường, nguồn dữ liệu chuẩn, chất lượng, quyền truy cập và quy tắc chuyển đổi. |
| Bảo mật, quyền riêng tư và tuân thủ | Giải thích các kiểm soát chuyên môn, nghĩa vụ và bằng chứng cần thiết trong phạm vi được giao. |
| UX hoặc chuyên gia khả năng tiếp cận | Làm rõ hành vi giao diện, trạng thái tương tác, ngôn ngữ, khả năng tiếp cận và nhu cầu người dùng. |
| Vận hành hoặc SRE | Làm rõ mục tiêu vận hành, giám sát, phục hồi, ngưỡng cảnh báo và kịch bản sự cố. |
| Developer | Giải thích thiết kế và hành vi kỹ thuật hiện tại, nêu giới hạn triển khai và đề xuất phương án khả thi. |
| Tester hoặc QA | Phát hiện điểm chưa rõ, phân tích rủi ro, đề xuất tình huống và kiểm tra tính kiểm chứng được của yêu cầu. |

Người kiểm thử có trách nhiệm chủ động đặt câu hỏi và chỉ ra khi chưa thể xác định kết quả mong đợi. Họ có thể đề xuất cách diễn đạt hoặc ví dụ để các bên xem xét, nhưng không nên tự đặt ra quy tắc sản phẩm khi chưa có người có thẩm quyền xác nhận.

Với yêu cầu liên quan nhiều chuyên môn, cần chỉ định một người chịu trách nhiệm chốt quyết định và mời các chuyên gia liên quan cung cấp ý kiến. Điều này tránh tình trạng mỗi nhóm trả lời một phần nhưng không ai chịu trách nhiệm về cách hiểu cuối cùng.

## 5. Quy trình thống nhất nguồn và cách hiểu

Có thể áp dụng quy trình sau cho yêu cầu mới, thay đổi quan trọng hoặc vùng có nhiều lỗi và tranh chấp.

### Bước 1: Xác định yêu cầu và rủi ro cần làm rõ

Gắn yêu cầu với mục tiêu chất lượng, người dùng, luồng nghiệp vụ và hậu quả nếu kết quả sai. Chia yêu cầu lớn thành các quy tắc hoặc hành vi có thể kiểm tra. Ưu tiên những điểm có ảnh hưởng đến tiền, dữ liệu, quyền truy cập, an toàn, tuân thủ hoặc tính liên tục của dịch vụ.

### Bước 2: Tìm nguồn hiện hành và xác định thẩm quyền

Tìm tài liệu, hợp đồng, dữ liệu hoặc tiêu chuẩn đang có hiệu lực. Xác nhận chủ sở hữu, phiên bản, ngày hiệu lực và phạm vi. Nếu có nhiều nguồn, ghi rõ nguồn nào là căn cứ chính cho từng phần của yêu cầu.

Không dùng bản nháp, trao đổi miệng hoặc hành vi phần mềm hiện tại làm căn cứ cuối cùng nếu chưa được người có thẩm quyền xác nhận. Trao đổi miệng có thể giúp hiểu nhanh, nhưng quyết định có ảnh hưởng đến kiểm thử cần được ghi lại ở nơi nhóm có thể truy cập.

### Bước 3: Chỉ định người giải thích và người phê duyệt

Ghi tên vai trò chịu trách nhiệm trả lời câu hỏi, vai trò phê duyệt và người thay thế khi người chính vắng mặt. Với chủ đề chuyên môn, xác định chuyên gia tư vấn tương ứng. Nếu chưa có người chịu trách nhiệm, xem đó là khoảng trống cần giải quyết trước khi kết luận kiểm thử.

### Bước 4: Làm rõ bằng ví dụ và trường hợp biên

Đặt câu hỏi cụ thể thay vì chỉ hỏi "yêu cầu này có rõ không?". Có thể dùng ví dụ đầu vào, kết quả mong đợi và tình huống ngoại lệ để phát hiện cách hiểu khác nhau.

Các câu hỏi hữu ích gồm:

- Điều kiện nào làm cho hành vi bắt đầu hoặc không được phép xảy ra?
- Kết quả chính xác là gì, bao gồm trạng thái dữ liệu và tác động phụ?
- Giá trị biên, giá trị rỗng, dữ liệu không hợp lệ và trường hợp trùng lặp được xử lý ra sao?
- Quy tắc về thời gian dùng múi giờ nào, tính ngày lịch hay ngày làm việc, và thời điểm bắt đầu được tính là lúc nào?
- Nếu dịch vụ phụ thuộc không phản hồi hoặc phản hồi lặp, hệ thống phải làm gì?
- Người dùng có quyền nào trong từng trạng thái? Có ngoại lệ hoặc vai trò đặc biệt không?
- Quy tắc làm tròn, tiền tệ, đơn vị đo và độ chính xác được xác định ở đâu?
- Khi hai chính sách hoặc hai nguồn có vẻ mâu thuẫn, ai có quyền quyết định?

### Bước 5: Ghi kết quả mong đợi thành tiêu chí có thể kiểm chứng

Diễn đạt yêu cầu theo điều kiện và kết quả quan sát được. Tùy tình huống, kết quả có thể bao gồm:

- Giá trị trả về, nội dung hiển thị hoặc mã trạng thái.
- Trạng thái bản ghi trước và sau thao tác.
- Sự kiện được phát ra, thông báo được gửi hoặc tác động đến hệ thống phụ thuộc.
- Quyền truy cập được cho phép hoặc từ chối.
- Thời gian phản hồi, thông lượng, khả năng phục hồi hoặc giới hạn tài nguyên.
- Log, audit trail và bằng chứng cần lưu.

Tiêu chí chấp nhận nên mô tả cả hành vi bình thường và những trường hợp quan trọng khi dữ liệu hoặc phụ thuộc không như mong đợi. Nếu kết quả có thể được diễn đạt bằng bảng quyết định, sơ đồ trạng thái hoặc ví dụ dữ liệu, hãy dùng hình thức đó để giảm cách hiểu mơ hồ.

### Bước 6: Xác nhận oracle và lưu dấu vết

Liên kết từng yêu cầu hoặc tiêu chí với nguồn xác nhận, người chịu trách nhiệm và trường hợp kiểm thử. Đưa quyết định vào hệ thống quản lý yêu cầu hoặc tài liệu được nhóm thống nhất sử dụng. Ghi lại ngày, phiên bản, người phê duyệt và các giả định còn tồn tại.

### Bước 7: Cập nhật khi yêu cầu thay đổi

Khi chính sách, hợp đồng, dữ liệu hoặc thiết kế thay đổi, đánh giá lại test oracle và các trường hợp kiểm thử phụ thuộc. Thông báo thay đổi cho những vai trò cần biết; tránh để test case tiếp tục dùng kết quả mong đợi từ phiên bản cũ.

## 6. Xử lý yêu cầu mơ hồ hoặc nguồn mâu thuẫn

Khi các nguồn không thống nhất, không nên chọn nguồn thuận tiện nhất hoặc lấy hành vi hiện tại của phần mềm làm đáp án. Hãy ghi nhận vấn đề và tìm quyết định có thẩm quyền.

Một cách xử lý có kiểm soát:

1. Ghi nguyên văn các phát biểu mâu thuẫn, nguồn, phiên bản và phần yêu cầu bị ảnh hưởng.
2. Đánh giá rủi ro nếu tiếp tục kiểm thử hoặc phát hành theo từng cách hiểu.
3. Xác định chủ sở hữu của từng nguồn và người có quyền phê duyệt quy tắc cuối cùng.
4. Đưa ra các phương án cùng ví dụ cụ thể, chỉ rõ tác động của mỗi phương án.
5. Ghi quyết định, lý do, ngày hiệu lực và các tài liệu hoặc test case cần cập nhật.
6. Nếu chưa thể quyết định, ghi rõ giả định tạm thời, người chấp nhận rủi ro và điều kiện phải giải quyết trước mốc phát hành liên quan.

Ví dụ: tài liệu yêu cầu nói rằng phiên đăng nhập hết hạn sau 30 phút không hoạt động, trong khi cấu hình hiện tại đặt 60 phút. Đây có thể là lỗi cấu hình, thay đổi chính sách chưa cập nhật tài liệu hoặc khác biệt giữa môi trường. Tester cần ghi nhận xung đột, hỏi chủ sở hữu bảo mật hoặc sản phẩm và xác nhận giá trị được phê duyệt cho từng môi trường. Không nên tự sửa expected result thành 60 phút chỉ vì hệ thống đang hoạt động như vậy.

Nếu không tìm được một kết quả đầu ra duy nhất, vẫn có thể kiểm thử bằng một số phương pháp:

- **Bất biến (invariant):** xác minh thuộc tính luôn phải đúng, ví dụ tổng số tiền ghi nợ không vượt quá số tiền được phép hoặc một giao dịch chỉ được ghi nhận một lần.
- **Kiểm thử quan hệ hoặc biến hình (metamorphic testing):** xác minh quan hệ giữa nhiều lần chạy khi không có oracle cho từng kết quả riêng lẻ. Ví dụ, sắp xếp lại thứ tự bản ghi đầu vào không được làm thay đổi tổng hợp nếu nghiệp vụ quy định phép tổng hợp không phụ thuộc thứ tự.
- **So sánh vi sai (differential testing):** so sánh nhiều cách triển khai hoặc phiên bản tham chiếu đã được xác nhận, đồng thời điều tra mọi khác biệt thay vì mặc định một kết quả là đúng.
- **Bộ dữ liệu chuẩn (golden dataset):** đối chiếu với tập đầu vào và kết quả đã được chuyên gia kiểm định, có quản lý phiên bản.
- **Đánh giá chuyên gia hoặc kiểm thử thăm dò:** dùng nhận định chuyên môn để tìm vấn đề và thu thập bằng chứng, sau đó ghi lại giới hạn và mức độ tin cậy của kết luận.

Các phương pháp này hỗ trợ khi oracle không đầy đủ; chúng không thay thế quyết định nghiệp vụ hoặc phê duyệt bắt buộc. Với rủi ro cao, cần giải quyết khoảng trống về nguồn xác nhận trước khi đưa ra kết luận phát hành.

## 7. Ví dụ thực tế: xác nhận quy tắc hoàn tiền đơn hàng

Giả sử sản phẩm có yêu cầu: "Khách hàng được hoàn tiền trong vòng bảy ngày nếu đơn hàng đủ điều kiện." Câu này chưa đủ để viết expected result vì còn nhiều câu hỏi:

- Bảy ngày được tính từ lúc đặt hàng, giao hàng hay xác nhận nhận hàng?
- Đó là ngày lịch hay ngày làm việc? Tính theo múi giờ nào?
- Đơn hàng đã dùng một phần có được hoàn một phần không?
- Phí vận chuyển, mã giảm giá và điểm thưởng được xử lý thế nào?
- Yêu cầu hoàn tiền được chấp nhận ngay hay chỉ sau khi nhà cung cấp thanh toán xác nhận?
- Nếu khách gửi yêu cầu hai lần hoặc callback từ nhà cung cấp đến lặp, có tạo hai khoản hoàn không?
- Trạng thái đơn hàng và thông báo cho khách thay đổi ở thời điểm nào?

### 7.1. Xác định nguồn và người chịu trách nhiệm

| Nội dung cần xác nhận | Nguồn xác nhận | Người giải thích hoặc phê duyệt |
|---|---|---|
| Điều kiện đủ bảy ngày và thời điểm bắt đầu | Chính sách đổi trả đã phê duyệt | Chủ nghiệp vụ bán hàng hoặc chủ sở hữu sản phẩm |
| Số tiền được hoàn và cách xử lý ưu đãi | Quy tắc giá, chính sách khuyến mãi và hướng dẫn tài chính | Tài chính và chuyên gia nghiệp vụ |
| Trạng thái API hoàn tiền | Hợp đồng API của nhà cung cấp thanh toán | Chủ sở hữu tích hợp thanh toán |
| Quyền yêu cầu hoàn tiền | Ma trận phân quyền và chính sách bảo mật | Chủ sở hữu bảo mật và sản phẩm |
| Thông báo và trạng thái hiển thị | Luồng UX và tiêu chí chấp nhận | UX và chủ sở hữu sản phẩm |

Nhóm có thể mời nhiều chuyên gia cung cấp ý kiến, nhưng cần xác định rõ ai phê duyệt chính sách hoàn tiền và ai xác nhận hợp đồng tích hợp.

### 7.2. Chuyển cách hiểu thành kết quả kiểm thử

Sau khi các bên xác nhận quy tắc, nhóm có thể ghi lại ví dụ như sau:

| Tình huống | Điều kiện | Kết quả mong đợi | Nguồn xác nhận |
|---|---|---|---|
| Hoàn tiền trong hạn | Đơn hàng đủ điều kiện và yêu cầu nằm trong thời hạn đã duyệt | Tạo yêu cầu hoàn tiền với số tiền theo quy tắc; ghi nhận trạng thái chờ xử lý | Chính sách hoàn tiền và quy tắc tài chính |
| Ngoài thời hạn | Yêu cầu đến sau mốc hết hạn | Từ chối theo mã/lý do đã thống nhất; không tạo khoản hoàn | Chính sách đổi trả |
| Hoàn một phần | Chỉ một phần hàng hóa đủ điều kiện | Tính số tiền theo quy tắc phân bổ ưu đãi và phí đã duyệt | Quy tắc tài chính |
| Gửi yêu cầu lặp | Cùng một yêu cầu được gửi lại do timeout | Không tạo khoản hoàn trùng; trả về hoặc tham chiếu kết quả của yêu cầu ban đầu | Hợp đồng API và quy tắc idempotency |
| Nhà cung cấp từ chối | Nhà cung cấp trả trạng thái thất bại | Không đánh dấu đã hoàn thành; lưu lỗi và cho phép xử lý tiếp theo theo chính sách | Hợp đồng API và quy trình vận hành |

Bảng này chỉ có thể trở thành expected result chính thức sau khi giá trị cụ thể, cách tính, thời điểm và trạng thái đã được người có thẩm quyền xác nhận. Các ô còn thiếu phải được làm rõ trước khi kiểm thử được dùng làm bằng chứng chấp nhận.

### 7.3. Truy vết quyết định

Với mỗi trường hợp, nhóm liên kết mã yêu cầu, phiên bản chính sách, tiêu chí chấp nhận, nguồn oracle, người phê duyệt, dữ liệu kiểm thử và kết quả chạy. Khi chính sách hoàn tiền thay đổi, nhóm có thể xác định ngay trường hợp nào cần xem xét lại.

## 8. Ghi nhận thỏa thuận để nhóm có thể sử dụng

Một bản ghi ngắn nhưng đầy đủ giúp giảm việc hỏi lại và tránh tranh luận dựa trên trí nhớ. Có thể dùng mẫu sau trong hệ thống quản lý yêu cầu hoặc tài liệu dự án:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Mã yêu cầu / tiêu chí | Định danh ổn định để truy vết |
| Phát biểu yêu cầu | Hành vi hoặc thuộc tính chất lượng cần xác minh |
| Nguồn cơ sở | Tên tài liệu, liên kết nội bộ, phiên bản và ngày hiệu lực |
| Nguồn xác nhận (oracle) | Quy tắc, công thức, dữ liệu, hợp đồng hoặc phương pháp so sánh |
| Người giải thích | Vai trò hoặc người cung cấp chuyên môn |
| Người phê duyệt | Vai trò có quyền chốt cách hiểu |
| Kết quả mong đợi | Giá trị, trạng thái, tác động và ngoại lệ có thể quan sát |
| Trường hợp liên quan | Test case, test data, kiểm thử tự động hoặc bằng chứng |
| Giả định và giới hạn | Điều chưa xác nhận, phạm vi không bao phủ và rủi ro còn lại |
| Phiên bản quyết định | Ngày, người xác nhận và điều kiện thay đổi |

Không phải mọi yêu cầu đều cần một bản ghi riêng dài như bảng trên. Với yêu cầu đơn giản, các trường có thể nằm trong tiêu chí chấp nhận hoặc công cụ quản lý test. Với yêu cầu quan trọng, nhiều phụ thuộc hoặc có tác động tuân thủ, nên ghi đủ để kiểm toán và truy vết được.

## 9. Những sai lầm thường gặp

- **Dùng hành vi hiện tại làm chuẩn đúng:** phần mềm có thể đang chứa lỗi hoặc chưa cập nhật chính sách. Chỉ dùng triển khai làm oracle khi hành vi đã được xác nhận và phê duyệt làm chuẩn tham chiếu.
- **Cho rằng người viết yêu cầu luôn là người quyết định:** người viết có thể tổng hợp thông tin nhưng không có thẩm quyền chốt mọi quy tắc. Hãy xác định chủ sở hữu quyết định.
- **Chỉ hỏi khi test case đã thất bại:** khi đó việc sửa yêu cầu hoặc dữ liệu có thể làm trễ dự án. Hãy làm rõ các điểm mơ hồ trong lúc phân tích và thiết kế kiểm thử.
- **Chỉ ghi kết quả thành công:** bỏ qua ngoại lệ, quyền truy cập, giá trị biên, trạng thái lỗi và tác động phụ sẽ làm oracle không đủ dùng.
- **Không quản lý phiên bản nguồn:** test case có thể so sánh với chính sách cũ sau khi sản phẩm đã đổi. Ghi phiên bản và ngày hiệu lực của căn cứ.
- **Để nhiều người đưa ra quyết định không thống nhất:** cần một vai trò chịu trách nhiệm phê duyệt cuối cùng cho từng chủ đề.
- **Dùng trao đổi miệng làm quyết định lâu dài:** ghi lại kết luận ở nơi nhóm có thể tìm thấy và liên kết với yêu cầu, test case.
- **Tự suy diễn khi không có oracle:** nếu chưa có căn cứ, ghi nhận khoảng trống, giả định và người chịu trách nhiệm giải quyết; không âm thầm biến suy đoán thành expected result.

## 10. Checklist trước khi sử dụng kết quả kiểm thử

Trước khi kết luận một yêu cầu đã được xác minh, hãy kiểm tra:

- [ ] Yêu cầu và phạm vi kiểm thử đã rõ, có mã hoặc cách truy vết ổn định.
- [ ] Cơ sở kiểm thử là nguồn hiện hành, có chủ sở hữu và phiên bản.
- [ ] Nguồn xác nhận kết quả mong đợi được chỉ định cho các tình huống quan trọng.
- [ ] Người giải thích và người có quyền phê duyệt đã được xác định.
- [ ] Các thuật ngữ, điều kiện, giá trị biên, ngoại lệ và tác động phụ đã được làm rõ.
- [ ] Kết quả mong đợi có thể quan sát và kiểm chứng bằng dữ liệu hoặc bằng chứng cụ thể.
- [ ] Xung đột giữa các nguồn đã được giải quyết hoặc ghi nhận với người chịu trách nhiệm và hạn xử lý.
- [ ] Giả định, giới hạn và rủi ro còn lại được công khai.
- [ ] Test case và dữ liệu kiểm thử liên kết với đúng phiên bản yêu cầu và oracle.
- [ ] Có cơ chế cập nhật khi nguồn hoặc quy tắc thay đổi.

## 11. Mối liên hệ giữa yêu cầu, oracle và bằng chứng

Quy trình thống nhất nguồn xác nhận có thể được hình dung như sau:

~~~mermaid
flowchart TD
    A["Yêu cầu và mục tiêu chất lượng"]
    B["Cơ sở kiểm thử<br/>Tài liệu, quy tắc, hợp đồng, dữ liệu"]
    C["Người giải thích chuyên môn"]
    D["Người có quyền phê duyệt"]
    E["Nguồn xác nhận kết quả<br/>Oracle và tiêu chí chấp nhận"]
    F["Test case và dữ liệu kiểm thử"]
    G["Kết quả thực tế và bằng chứng"]
    H["Đánh giá đạt, không đạt hoặc cần làm rõ"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H -. "Phát hiện mơ hồ hoặc xung đột" .-> C
    H -. "Cập nhật tiêu chí và nguồn" .-> E
~~~

Kết quả kiểm thử có giá trị khi người khác có thể lần theo bằng chứng để biết nhóm đã kiểm tra yêu cầu nào, dựa trên nguồn nào, ai xác nhận cách hiểu và vì sao kết luận được đưa ra. Khi nguồn xác nhận và trách nhiệm giải thích được thống nhất từ sớm, nhóm giảm được tranh cãi không cần thiết, phát hiện khoảng trống yêu cầu nhanh hơn và đưa ra quyết định chất lượng có căn cứ.
