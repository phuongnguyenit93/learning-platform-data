# Sử dụng testing quadrants để nhìn các mục tiêu và hoạt động bổ sung

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, nhóm cần phân bổ hoạt động sao cho vừa hỗ trợ phát triển đúng hướng, vừa đánh giá sản phẩm từ góc nhìn người dùng và các thuộc tính kỹ thuật. **Testing quadrants** (mô hình bốn góc phần tư kiểm thử), thường được gọi là *Agile Testing Quadrants*, là một bản đồ tư duy giúp nhóm nhìn các mục tiêu và nhóm hoạt động kiểm thử theo hai chiều: kiểm thử hướng nghiệp vụ hay hướng công nghệ, và kiểm thử nhằm hỗ trợ nhóm phát triển hay nhằm đánh giá, phản biện sản phẩm.

Mô hình này giúp nhận ra những khoảng trống thường gặp. Một nhóm có thể có rất nhiều test đơn vị và kiểm thử API nhưng ít khi quan sát người dùng thực hiện công việc. Nhóm khác có thể tổ chức nhiều buổi UAT nhưng thiếu kiểm tra hiệu năng, bảo mật hoặc khả năng phục hồi. Testing quadrants giúp đặt các hoạt động cạnh nhau để thảo luận xem bằng chứng nào còn thiếu và cần đầu tư vào đâu.

## 1. Testing quadrants là gì?

Testing quadrants chia hoạt động kiểm thử thành bốn nhóm theo hai trục:

- **Trục hướng nghiệp vụ — hướng công nghệ:** hoạt động tập trung vào quy tắc, mục tiêu và công việc nghiệp vụ hay tập trung vào cấu trúc, hành vi và thuộc tính kỹ thuật của hệ thống.
- **Trục hỗ trợ nhóm — đánh giá sản phẩm:** hoạt động giúp nhóm phát triển hiểu yêu cầu, phản hồi nhanh và xây dựng đúng hướng hay hoạt động tìm hiểu, đánh giá sản phẩm để phát hiện vấn đề và xác định mức phù hợp.

Có thể hình dung bản đồ như sau:

```text
                         HƯỚNG NGHIỆP VỤ
                                ^
                                |
          Q2                    |                    Q3
   Ví dụ, tiêu chí chấp nhận,   |       Khám phá, khả năng sử dụng,
   kiểm thử chức năng hỗ trợ    |       UAT, đánh giá trải nghiệm
   nhóm phát triển              |       và kịch bản thực tế
                                |
 HỖ TRỢ NHÓM  ------------------+------------------> ĐÁNH GIÁ SẢN PHẨM
                                |
          Q1                    |                    Q4
   Đơn vị, component,           |       Hiệu năng, tải, bảo mật,
   kiểm tra kỹ thuật sớm        |       độ tin cậy và khả năng phục hồi
                                |
                                v
                         HƯỚNG CÔNG NGHỆ
```

Tên gọi Q1, Q2, Q3, Q4 là nhãn để trao đổi, không phải thứ tự bắt buộc phải thực hiện. Các góc phần tư cũng không đại diện cho bốn cấp độ kiểm thử hoặc bốn giai đoạn tuần tự. Một dự án có thể thực hiện hoạt động ở cả bốn nhóm song song và lặp lại theo từng thay đổi.

## 2. Bốn góc phần tư và mục tiêu của từng nhóm

### Q1 — Hướng công nghệ, hỗ trợ nhóm phát triển

Q1 tập trung vào các kiểm tra kỹ thuật ở mức gần với mã nguồn và thành phần, giúp nhóm nhận phản hồi nhanh khi xây dựng phần mềm. Mục tiêu là phát hiện sớm lỗi logic, lỗi cấu trúc và sai lệch trong các thành phần nhỏ.

Hoạt động thường gặp:

- Kiểm thử đơn vị cho hàm, lớp và quy tắc nghiệp vụ cô lập.
- Kiểm thử component hoặc module với các phụ thuộc được kiểm soát.
- Kiểm thử cấu trúc dữ liệu, thuật toán và xử lý trạng thái.
- Kiểm tra kỹ thuật tự động trong quá trình phát triển, chẳng hạn phân tích tĩnh, kiểm tra kiểu và một số kiểm tra cấu hình.
- Phát triển hướng kiểm thử (TDD), trong đó test giúp làm rõ hành vi cần xây dựng.

Ví dụ, hàm tính tổng đơn hàng cần xử lý giá sản phẩm, mã giảm giá, thuế và làm tròn. Test đơn vị kiểm tra từng quy tắc, giá trị biên và tổ hợp dữ liệu để lập trình viên nhận biết lỗi ngay khi thay đổi logic.

Q1 đặc biệt hữu ích khi nhóm cần phản hồi nhanh và muốn cô lập nguyên nhân lỗi. Tuy nhiên, kết quả Q1 không chứng minh các thành phần tích hợp đúng, quy trình người dùng phù hợp hoặc hệ thống hoạt động tốt dưới tải thực tế.

### Q2 — Hướng nghiệp vụ, hỗ trợ nhóm phát triển

Q2 tập trung vào ví dụ, quy tắc và tiêu chí nghiệp vụ giúp nhóm hiểu chính xác điều cần xây dựng. Những hoạt động này kết nối yêu cầu với hành vi mong đợi, thường được thực hiện trước hoặc trong khi phát triển để giảm hiểu nhầm.

Hoạt động thường gặp:

- Ví dụ nghiệp vụ và kiểm thử theo ví dụ (example-based testing).
- Kiểm thử chức năng dựa trên user story và tiêu chí chấp nhận.
- Kiểm thử chấp nhận ở mức câu chuyện hoặc tính năng để làm rõ điều kiện hoàn thành.
- Prototype, mô phỏng và ví dụ dữ liệu để thảo luận với người dùng hoặc chuyên gia nghiệp vụ.
- Kiểm tra quy tắc, bảng quyết định và các tình huống nghiệp vụ điển hình.

Ví dụ, một user story yêu cầu khách hàng được miễn phí giao hàng khi tổng tiền hàng sau giảm giá đạt một ngưỡng đã định. Nhóm cùng chủ sản phẩm làm rõ các ví dụ: đúng ngưỡng, thấp hơn một đơn vị tiền, cao hơn ngưỡng, mã giảm giá làm tổng tiền giảm xuống dưới ngưỡng và địa chỉ không được hỗ trợ. Các ví dụ này trở thành tiêu chí cụ thể để phát triển và kiểm tra.

Q2 giúp nhóm xây dựng đúng điều nghiệp vụ mong đợi. Nhưng việc một chức năng đáp ứng các ví dụ đã thống nhất chưa đảm bảo người dùng có thể hoàn thành công việc thuận tiện, hoặc hệ thống đáp ứng hiệu năng và bảo mật.

### Q3 — Hướng nghiệp vụ, đánh giá sản phẩm

Q3 xem xét sản phẩm từ góc nhìn người dùng, khách hàng và bối cảnh vận hành. Mục tiêu là tìm hiểu sản phẩm có thực sự hỗ trợ công việc, dễ hiểu và phù hợp với kỳ vọng hay không; đồng thời phát hiện những vấn đề mà kịch bản định trước có thể bỏ sót.

Hoạt động thường gặp:

- Kiểm thử khám phá (exploratory testing) theo mục tiêu và phiên làm việc.
- Kiểm thử khả năng sử dụng (usability testing) với người dùng đại diện.
- Kiểm thử chấp nhận người dùng (UAT) trong quy trình gần thực tế.
- Đánh giá luồng nghiệp vụ xuyên suốt và các tình huống sử dụng bất thường.
- Thử nghiệm alpha, beta hoặc pilot với nhóm người dùng phù hợp.
- Quan sát tác vụ, phỏng vấn và phân tích phản hồi sau khi sử dụng.

Ví dụ, người mua có thể hoàn tất thanh toán theo đúng các bước đã đặc tả, nhưng trong buổi thử nghiệm họ không nhận ra phí giao hàng chỉ xuất hiện ở bước cuối. Quan sát này cho thấy trải nghiệm chưa minh bạch dù các test chức năng vẫn đạt. Nhóm cần xem lại cách trình bày và có thể cả yêu cầu nghiệp vụ.

Q3 thường cung cấp bằng chứng có ngữ cảnh về tính phù hợp và trải nghiệm. Chất lượng của bằng chứng phụ thuộc vào việc chọn đúng người tham gia, tác vụ đại diện và điều kiện thử nghiệm; một vài nhận xét rời rạc không đủ để đại diện cho mọi nhóm người dùng.

### Q4 — Hướng công nghệ, đánh giá sản phẩm

Q4 đánh giá các thuộc tính kỹ thuật và khả năng vận hành của sản phẩm trong điều kiện sử dụng dự kiến hoặc điều kiện bất lợi. Mục tiêu là xác định hệ thống có đủ năng lực, an toàn và ổn định khi đối diện với tải, lỗi, môi trường và các mối đe dọa hay không.

Hoạt động thường gặp:

- Kiểm thử hiệu năng, tải, sức chịu đựng (stress) và tăng đột biến (spike).
- Kiểm thử bảo mật, phân quyền, cấu hình và khả năng chống tấn công.
- Kiểm thử độ tin cậy, khả năng chịu lỗi, phục hồi và tính sẵn sàng.
- Kiểm thử tương thích với hệ điều hành, trình duyệt, thiết bị hoặc phiên bản tích hợp.
- Kiểm thử khả năng mở rộng, dung lượng, sử dụng tài nguyên và khả năng vận hành.
- Kiểm tra cài đặt, nâng cấp, sao lưu, khôi phục và các kịch bản vận hành quan trọng.

Ví dụ, API đặt hàng có thể trả kết quả đúng trong kiểm thử chức năng nhưng bị tăng độ trễ hoặc tạo lỗi khi có hàng nghìn yêu cầu đồng thời. Kiểm thử tải và theo dõi tài nguyên giúp xác định giới hạn của hệ thống, điểm nghẽn và cách nó suy giảm khi vượt tải.

Q4 thường cần môi trường, công cụ và chuyên môn phù hợp. Kết quả phải gắn với điều kiện đo cụ thể; một lần chạy tải trong môi trường nhỏ không thể tự động đại diện cho production.

## 3. Bảng tổng hợp bốn góc phần tư

| Góc phần tư | Hướng chính | Mục tiêu | Ví dụ hoạt động | Bằng chứng điển hình |
|---|---|---|---|---|
| Q1 | Công nghệ, hỗ trợ nhóm | Phản hồi kỹ thuật sớm, kiểm tra thành phần và logic | Unit test, component test, TDD, phân tích tĩnh | Kết quả test, báo cáo phân tích, độ bao phủ phù hợp |
| Q2 | Nghiệp vụ, hỗ trợ nhóm | Làm rõ yêu cầu và ví dụ hành vi mong đợi | Story test, ví dụ chấp nhận, kiểm thử chức năng, prototype | Tiêu chí chấp nhận, ví dụ nghiệp vụ, kết quả kiểm tra chức năng |
| Q3 | Nghiệp vụ, đánh giá sản phẩm | Đánh giá trải nghiệm và tính phù hợp trong sử dụng | Exploratory, usability, UAT, alpha/beta, pilot | Quan sát tác vụ, phản hồi, tỷ lệ hoàn thành và phát hiện khám phá |
| Q4 | Công nghệ, đánh giá sản phẩm | Đánh giá thuộc tính kỹ thuật và rủi ro vận hành | Performance, load, security, reliability, recovery, compatibility | Độ trễ, thông lượng, lỗi, báo cáo bảo mật và kết quả phục hồi |

Các ví dụ trong bảng là điển hình, không phải quy tắc phân loại tuyệt đối. Một hoạt động có thể phục vụ nhiều mục tiêu. Ví dụ, UAT có thể kiểm tra tiêu chí chấp nhận đã ghi (Q2) đồng thời đánh giá khả năng hoàn thành công việc thực tế (Q3). Kiểm thử API có thể hỗ trợ nhóm phát triển (Q1 hoặc Q2 tùy mục tiêu) hoặc đánh giá khả năng chịu tải của hệ thống (Q4). Hãy phân loại theo mục đích, góc nhìn và cách sử dụng kết quả.

## 4. Cách sử dụng mô hình để phân bổ hoạt động kiểm thử

Testing quadrants hữu ích nhất khi được dùng để thảo luận và cân bằng bằng chứng. Không nên đặt chỉ tiêu phải có cùng số lượng test ở mỗi góc phần tư. Một sản phẩm nhúng, một website thương mại điện tử và một ứng dụng quản lý nội bộ có hồ sơ rủi ro khác nhau; phân bổ phù hợp cũng khác nhau.

### Bước 1: Xác định mục tiêu và quyết định cần hỗ trợ

Làm rõ nhóm cần chứng minh điều gì: logic có đúng không, yêu cầu nghiệp vụ có rõ không, người dùng có hoàn thành tác vụ không, hay hệ thống có chịu được tải và lỗi không. Ghi nhận ai sẽ dùng bằng chứng để quyết định tiếp tục phát triển, nghiệm thu hoặc phát hành.

### Bước 2: Liệt kê yêu cầu và rủi ro quan trọng

Thu thập yêu cầu chức năng, mục tiêu chất lượng, quy định, lịch sử lỗi và các giả định về người dùng. Đánh giá khả năng xảy ra và mức độ tác động của từng rủi ro. Những rủi ro nghiêm trọng như giao dịch sai, lộ dữ liệu hoặc mất dữ liệu cần có bằng chứng tương ứng, thường ở nhiều góc phần tư.

### Bước 3: Đặt hoạt động vào góc phần tư phù hợp

Với từng yêu cầu hoặc rủi ro, hỏi:

- Cần phản hồi cho nhóm phát triển để xây dựng đúng hơn, hay cần đánh giá sản phẩm đã hình thành?
- Bằng chứng tập trung vào quy tắc và công việc nghiệp vụ, hay thuộc tính và hành vi kỹ thuật?
- Có cần cả góc nhìn của nhóm phát triển và người dùng/vận hành không?

Một yêu cầu quan trọng có thể liên kết với nhiều hoạt động. Ví dụ, yêu cầu “một yêu cầu thanh toán chỉ được ghi nhận một lần” có thể cần test đơn vị cho logic idempotency (Q1), ví dụ chấp nhận cho retry và timeout (Q2), thử nghiệm luồng khi mạng chập chờn với người dùng (Q3) và kiểm tra đồng thời, độ tin cậy của dịch vụ (Q4).

### Bước 4: Tìm khoảng trống và trùng lặp

Quan sát xem có góc phần tư nào hầu như không có bằng chứng. Nếu nhóm chỉ có test tự động Q1 và Q2, cần hỏi liệu trải nghiệm người dùng và thuộc tính vận hành đã được đánh giá chưa. Nếu có nhiều kịch bản UAT nhưng thiếu test đơn vị cho logic quan trọng, lỗi có thể được phát hiện muộn và khó xác định nguyên nhân.

Đồng thời, kiểm tra các test trùng lặp mà không tăng thêm bằng chứng. Nhiều test đầu cuối có thể cùng kiểm tra một quy tắc đơn giản, làm tăng thời gian chạy và chi phí bảo trì. Có thể chuyển kiểm tra logic xuống Q1 và giữ một số luồng đầu cuối đại diện cho rủi ro xuyên hệ thống.

### Bước 5: Phân bổ nguồn lực theo rủi ro và giá trị thông tin

Ưu tiên các hoạt động giúp phát hiện sớm hoặc làm rõ rủi ro có tác động lớn. Cân nhắc thời gian, kỹ năng, môi trường, dữ liệu và công cụ. Q1 thường phù hợp với tự động hóa phản hồi nhanh; Q2 cần sự phối hợp giữa kỹ thuật và nghiệp vụ; Q3 cần người dùng đại diện hoặc tester có kỹ năng khám phá; Q4 có thể cần môi trường tải, công cụ chuyên biệt và chuyên gia bảo mật/vận hành.

Nếu chưa thể thực hiện một hoạt động, ghi rõ giới hạn, rủi ro còn lại, biện pháp thay thế và người có thẩm quyền chấp nhận. Không được xem một góc phần tư không có hoạt động là bằng chứng rằng rủi ro tương ứng không tồn tại.

### Bước 6: Lặp lại khi sản phẩm và rủi ro thay đổi

Mỗi thay đổi lớn, sự cố, phản hồi người dùng hoặc thay đổi tải có thể làm thay đổi phân bổ. Cập nhật bản đồ quadrants khi có thông tin mới. Một tính năng mới có thể cần tăng Q2 và Q3 để làm rõ trải nghiệm; một sự cố hiệu năng có thể làm tăng Q4; lỗi logic lặp lại có thể khiến nhóm đầu tư thêm vào Q1.

## 5. Ví dụ xuyên suốt: quy trình đặt hàng trực tuyến

Giả sử nhóm xây dựng quy trình cho khách hàng chọn sản phẩm, áp dụng mã giảm giá, thanh toán qua cổng bên ngoài và nhận xác nhận đơn hàng. Các rủi ro chính gồm tính tiền sai, tạo đơn trùng, người mua không hiểu trạng thái thanh toán và hệ thống chậm khi có chiến dịch lớn.

### Phân bổ hoạt động theo quadrants

| Góc phần tư | Hoạt động cụ thể | Câu hỏi cần trả lời |
|---|---|---|
| Q1 | Test đơn vị cho tính giá, thuế, giảm giá, làm tròn và khóa idempotency | Logic từng thành phần có xử lý đúng quy tắc và trường hợp biên không? |
| Q2 | Ví dụ chấp nhận cho mã giảm giá, phí giao hàng, thanh toán thành công/thất bại và retry | Nhóm có hiểu thống nhất các quy tắc và kết quả nghiệp vụ mong đợi không? |
| Q3 | Cho người mua đại diện thực hiện luồng mua hàng; khám phá khi thanh toán chậm, quay lại trang hoặc mất mạng | Người mua có hiểu tổng tiền, trạng thái và cách tiếp tục hoặc xử lý sự cố không? |
| Q4 | Kiểm thử tải trong chiến dịch, kiểm tra bảo mật thanh toán, webhook lặp, lỗi phụ thuộc và phục hồi | Hệ thống có an toàn, ổn định và đáp ứng tải cũng như tình huống lỗi dự kiến không? |

### Theo dõi một yêu cầu qua bốn góc phần tư

Xét yêu cầu: “Khi cổng thanh toán gửi lại cùng một thông báo giao dịch, hệ thống không được ghi nhận thanh toán hoặc tạo đơn hàng lần thứ hai.”

1. **Q1:** kiểm tra hàm xử lý khóa giao dịch và logic loại bỏ sự kiện trùng với nhiều dữ liệu đầu vào.
2. **Q2:** thống nhất ví dụ về webhook đến một lần, đến lặp, đến sai thứ tự, đến sau timeout và đến khi đơn đã bị hủy.
3. **Q3:** mô phỏng cho người mua tình huống trang chờ lâu hoặc tải lại; quan sát họ có hiểu trạng thái đơn và tránh thao tác gây nhầm lẫn không.
4. **Q4:** gửi nhiều webhook đồng thời, mô phỏng mất kết nối cơ sở dữ liệu, kiểm tra tính nhất quán và xác minh hệ thống phục hồi đúng.

Các hoạt động trên bổ sung cho nhau. Test đơn vị có thể chứng minh logic loại bỏ sự kiện trùng trong điều kiện cô lập, nhưng không chứng minh được toàn bộ hệ thống xử lý đúng khi hai webhook đến đồng thời hoặc khi cơ sở dữ liệu gặp sự cố. Thử nghiệm với người mua giúp đánh giá cách hiển thị trạng thái, nhưng không thay thế kiểm tra tính toàn vẹn giao dịch.

## 6. Quan hệ giữa quadrants với các loại và mức kiểm thử

Không nên đồng nhất quadrants với các cấp độ như unit, integration, system và acceptance. Các cấp độ mô tả phạm vi thành phần được kiểm tra và mức tích hợp; quadrants mô tả mục tiêu, góc nhìn và cách sử dụng hoạt động kiểm thử.

Ví dụ:

- Kiểm thử đơn vị thường thuộc Q1 khi nó hỗ trợ lập trình viên kiểm tra logic kỹ thuật.
- Kiểm thử chức năng có thể thuộc Q2 khi dùng ví dụ nghiệp vụ để hỗ trợ nhóm xây dựng tính năng.
- Kiểm thử hệ thống có thể thuộc Q3 nếu tập trung quan sát người dùng hoàn thành hành trình thực tế.
- Kiểm thử hệ thống cũng có thể thuộc Q4 nếu đo tải, độ tin cậy hoặc bảo mật.
- Kiểm thử chấp nhận có thể nằm ở Q2 hoặc Q3 tùy nó được dùng để làm rõ tiêu chí với nhóm hay đánh giá mức phù hợp của sản phẩm với người dùng.

Tương tự, không thể kết luận Q1 và Q2 luôn tự động hóa, còn Q3 và Q4 luôn thủ công. Q4 thường được tự động hóa bằng công cụ tải, quét bảo mật và kiểm tra phục hồi. Một số hoạt động Q3 có thể dùng công cụ ghi nhận hoặc tự động hóa tác vụ, nhưng đánh giá trải nghiệm vẫn cần con người diễn giải trong ngữ cảnh.

## 7. Dùng quadrants để xem xét mức độ bao phủ

Một bản đồ quadrants tốt không chỉ ghi tên hoạt động mà cần liên kết với yêu cầu, rủi ro, bằng chứng và người chịu trách nhiệm. Có thể sử dụng bảng sau trong buổi lập kế hoạch:

| Yêu cầu / rủi ro | Q1 — hỗ trợ kỹ thuật | Q2 — làm rõ nghiệp vụ | Q3 — đánh giá sử dụng | Q4 — đánh giá kỹ thuật |
|---|---|---|---|---|
| Tính tổng đơn hàng chính xác | Test đơn vị công thức và biên | Ví dụ giá, giảm giá, thuế và phí | Quan sát người mua hiểu phần phân rã tổng tiền | Kiểm tra sai lệch khi xử lý nhiều giao dịch đồng thời nếu có liên quan |
| Không tạo đơn trùng | Test logic idempotency | Ví dụ retry, timeout và webhook lặp | Thử luồng mạng chập chờn và cách hiển thị trạng thái | Test đồng thời, lỗi cơ sở dữ liệu và phục hồi |
| Bảo vệ thông tin thanh toán | Test kiểm tra quyền ở thành phần | Làm rõ vai trò và dữ liệu được phép hiển thị | Đánh giá người dùng có vô tình để lộ thông tin trên màn hình/chia sẻ hay không | Kiểm thử bảo mật, cấu hình, mã hóa và nhật ký |
| Hoàn tất mua hàng thuận tiện | Test logic trạng thái và validation đầu vào | Ví dụ tiêu chí chấp nhận cho từng bước | Usability, exploratory và UAT | Đo độ trễ, khả năng sẵn sàng và hành vi khi phụ thuộc chậm |

Không phải ô nào cũng bắt buộc có test riêng. Nếu một ô không phù hợp, có thể ghi “không áp dụng” kèm lý do. Nếu ô trống vì thiếu thời gian hoặc công cụ, hãy ghi thành khoảng trống và đánh giá rủi ro còn lại.

### Những câu hỏi giúp kiểm tra sự cân bằng

- Q1: Logic quan trọng có được kiểm tra sớm và đủ cô lập để dễ chẩn đoán không?
- Q2: Các bên có cùng hiểu yêu cầu, ví dụ và tiêu chí chấp nhận không?
- Q3: Có bằng chứng từ người dùng hoặc hoạt động khám phá về tính phù hợp của sản phẩm không?
- Q4: Các thuộc tính kỹ thuật và tình huống vận hành có rủi ro cao đã được kiểm tra trong điều kiện đại diện chưa?

Không nên đánh giá sự cân bằng bằng số lượng test mỗi góc phần tư. Hãy xem rủi ro nào được bao phủ, bằng chứng có đủ tin cậy không và kết quả có hỗ trợ được quyết định cần thiết không.

## 8. Những hiểu lầm thường gặp

**Coi bốn góc phần tư là bốn giai đoạn.** Mô hình không quy định phải hoàn thành Q1 rồi mới đến Q2, Q3 và Q4. Các hoạt động có thể diễn ra song song và lặp lại theo thay đổi.

**Coi quadrants là các cấp độ kiểm thử.** Q1 không đồng nghĩa unit test, Q2 không đồng nghĩa integration, Q3 không đồng nghĩa system và Q4 không đồng nghĩa acceptance. Cấp độ và góc phần tư trả lời hai câu hỏi khác nhau.

**Cho rằng mỗi test chỉ thuộc một góc phần tư.** Một bài UAT có thể vừa xác nhận tiêu chí nghiệp vụ vừa đánh giá trải nghiệm. Hãy phân loại theo mục đích chính và ghi nhận các mục tiêu phụ khi cần.

**Chỉ đầu tư vào Q1 vì test chạy nhanh.** Q1 giúp phát hiện lỗi sớm nhưng không đủ để đánh giá trải nghiệm, tích hợp thực tế, bảo mật hoặc hiệu năng toàn hệ thống.

**Chỉ đầu tư vào Q3 vì người dùng là người quyết định.** Phản hồi người dùng không thể chứng minh logic tính toán, tính toàn vẹn dữ liệu, an toàn hoặc khả năng chịu tải. Cần kết hợp với kiểm tra kỹ thuật.

**Bỏ Q4 vì môi trường kiểm thử hạn chế.** Nếu chưa thể thực hiện kiểm thử hiệu năng hoặc bảo mật chuyên sâu, phải ghi rõ giới hạn, biện pháp thay thế và rủi ro còn lại. Không nên suy ra hệ thống an toàn hoặc chịu tải tốt khi chưa có bằng chứng.

**Coi mọi hoạt động Q3 là thủ công và mọi hoạt động Q1/Q2 là tự động.** Mức tự động hóa phụ thuộc vào tính lặp lại, độ ổn định, dữ liệu và mục tiêu của hoạt động, không phụ thuộc riêng vào vị trí trên bản đồ.

**Dùng số lượng test để tuyên bố cân bằng.** Nhiều test ở một góc phần tư có thể vẫn bỏ sót rủi ro quan trọng ở góc khác. Cần đánh giá độ bao phủ và giá trị của bằng chứng.

## 9. Checklist áp dụng testing quadrants

Khi lập kế hoạch:

- [ ] Mục tiêu kiểm thử và quyết định cần hỗ trợ đã được xác định.
- [ ] Yêu cầu, rủi ro và bối cảnh sử dụng đã được xem xét.
- [ ] Các hoạt động hiện có được đặt vào Q1, Q2, Q3 hoặc Q4 theo mục tiêu chính.
- [ ] Các yêu cầu và rủi ro quan trọng có hoạt động bổ sung phù hợp ở nhiều góc phần tư khi cần.

Khi phân bổ nguồn lực:

- [ ] Q1 có kiểm tra kỹ thuật sớm cho logic và thành phần quan trọng.
- [ ] Q2 có ví dụ và tiêu chí nghiệp vụ đủ rõ để hỗ trợ phát triển.
- [ ] Q3 có cách thu thập phản hồi hoặc quan sát sử dụng trong bối cảnh đại diện.
- [ ] Q4 có bằng chứng về thuộc tính kỹ thuật và rủi ro vận hành quan trọng.
- [ ] Nguồn lực, công cụ, môi trường, dữ liệu và kỹ năng phù hợp với hoạt động đã chọn.
- [ ] Khoảng trống hoặc hoạt động chưa thể thực hiện được ghi nhận cùng rủi ro tồn dư.

Khi đánh giá kết quả:

- [ ] Bằng chứng được liên kết với yêu cầu, rủi ro và người chịu trách nhiệm.
- [ ] Kết quả được đánh giá theo chất lượng và mức tin cậy, không chỉ số lượng test.
- [ ] Các phát hiện từ một góc phần tư được dùng để cập nhật hoạt động ở góc phần tư khác khi phù hợp.
- [ ] Bản đồ được xem xét lại khi sản phẩm, kiến trúc, người dùng hoặc rủi ro thay đổi.

## 10. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Nhóm viết test đơn vị cho công thức tính phí giao hàng để lập trình viên nhận phản hồi khi thay đổi logic. Đây là hoạt động Q1 vì tập trung vào kiểm tra kỹ thuật để hỗ trợ nhóm phát triển.

**Tình huống 2:** Chủ sản phẩm và tester thống nhất các ví dụ về đơn hàng được miễn phí vận chuyển, bao gồm đúng ngưỡng và thấp hơn ngưỡng. Đây là Q2 vì ví dụ nghiệp vụ giúp nhóm hiểu và xây dựng đúng hành vi mong đợi.

**Tình huống 3:** Người mua đại diện được mời hoàn thành quy trình thanh toán trong khi tester quan sát điểm họ do dự hoặc hiểu nhầm trạng thái. Đây là Q3 vì hoạt động đánh giá sản phẩm từ góc nhìn sử dụng thực tế.

**Tình huống 4:** Nhóm tạo tải lớn, đo p95, thông lượng và tỷ lệ lỗi của API thanh toán. Đây là Q4 vì mục tiêu là đánh giá thuộc tính kỹ thuật của sản phẩm trong điều kiện tải.

**Tình huống 5:** UAT xác nhận nhân viên có thể hoàn tất quy trình nhập kho theo tiêu chí đã thống nhất, đồng thời quan sát thấy cách chọn kho gây nhầm lẫn. Phần đối chiếu tiêu chí có mục tiêu Q2; phần đánh giá trải nghiệm và phát hiện trở ngại là Q3. Một hoạt động có thể tạo ra bằng chứng cho cả hai mục tiêu.

Khi phân loại một hoạt động, hãy tự hỏi: **hoạt động này hướng đến nghiệp vụ hay công nghệ, và nó hỗ trợ nhóm phát triển hay đánh giá sản phẩm?** Sau đó xác định bằng chứng nó tạo ra, rủi ro nó giúp kiểm soát và những góc nhìn còn thiếu.

## Kết luận

Testing quadrants là bản đồ giúp nhóm nhìn các hoạt động kiểm thử theo hai chiều: nghiệp vụ hay công nghệ, hỗ trợ nhóm phát triển hay đánh giá sản phẩm. Q1 hỗ trợ phản hồi kỹ thuật sớm; Q2 làm rõ ví dụ và yêu cầu nghiệp vụ; Q3 đánh giá trải nghiệm và tính phù hợp; Q4 đánh giá thuộc tính kỹ thuật và rủi ro vận hành. Sử dụng cả bốn góc phần tư như các nguồn bằng chứng bổ sung giúp nhóm phát hiện khoảng trống, phân bổ nguồn lực theo rủi ro và đưa ra quyết định chất lượng có cơ sở.
