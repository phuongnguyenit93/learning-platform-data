# Xác định mô hình phát triển và nhịp phát hành

## Mục tiêu

Trong phạm vi `VALIDATION_TESTING_STRATEGY`, việc chọn mô hình phát triển và nhịp phát hành là quyết định nền tảng để thiết kế hoạt động kiểm thử, xác nhận và đưa thay đổi đến người dùng. Hai quyết định này cần được xem xét cùng nhau: mô hình phát triển quy định cách nhóm biến yêu cầu thành phần mềm đã được kiểm chứng; nhịp phát hành quy định thời điểm và cách phần mềm đó được cung cấp cho người dùng.

Một quy trình phù hợp giúp nhóm nhận phản hồi sớm, phát hiện lỗi khi chi phí sửa còn thấp và kiểm soát rủi ro theo mức ảnh hưởng của thay đổi. Không có một mô hình hay tần suất phát hành tối ưu cho mọi sản phẩm. Lựa chọn tốt phải phù hợp với mức độ rủi ro, cách hệ thống được xây dựng, yêu cầu vận hành và khả năng kiểm chứng của nhóm.

Sau bài học, người học có thể phân biệt mô hình phát triển với nhịp phát hành, đánh giá các yếu tố ảnh hưởng, chọn cách làm phù hợp và xác định những bằng chứng kiểm thử cần có trước, trong và sau khi phát hành.

## 1. Phân biệt mô hình phát triển, nhịp phát hành và triển khai

**Mô hình phát triển** mô tả cách công việc đi từ ý tưởng đến một thay đổi có thể sử dụng. Nó bao gồm cách phân rã yêu cầu, lập kế hoạch, thiết kế, lập trình, tích hợp, kiểm thử, đánh giá và phản hồi. Mô hình cũng ảnh hưởng đến thời điểm các vai trò phối hợp và thời điểm nhóm có bằng chứng về chất lượng.

**Nhịp phát hành** mô tả tần suất và quy tắc cung cấp chức năng cho người dùng. Nhóm có thể phát hành theo lịch cố định, theo từng đợt đã lên kế hoạch hoặc ngay khi một thay đổi đáp ứng đủ điều kiện. Nhịp phát hành có thể khác với nhịp tích hợp mã nguồn.

Ba hoạt động sau cần được phân biệt:

- **Tích hợp (integration):** kết hợp thay đổi vào nhánh hoặc phiên bản chung để kiểm tra chúng hoạt động cùng nhau.
- **Triển khai (deployment):** đưa một bản dựng đến môi trường đích, chẳng hạn môi trường kiểm thử hoặc môi trường sản xuất.
- **Phát hành (release):** làm cho một chức năng hoặc phiên bản sẵn sàng sử dụng đối với một nhóm người dùng.

Ví dụ, một nhóm có thể tích hợp mã nguồn nhiều lần mỗi ngày, triển khai bản dựng lên môi trường sản xuất mỗi ngày, nhưng chỉ bật tính năng cho người dùng vào thứ Sáu. Feature flag cho phép mã đã triển khai tồn tại trong hệ thống mà chức năng vẫn chưa được công bố. Triển khai thường xuyên vì vậy không bắt buộc phải đồng nghĩa với việc thay đổi trải nghiệm người dùng thường xuyên.

**Chiến lược kiểm thử và xác nhận** kết nối ba hoạt động trên bằng cách xác định rủi ro cần kiểm soát, loại kiểm tra cần thực hiện, thời điểm thực hiện và bằng chứng cần lưu. Nhóm nên thiết kế chiến lược này ngay khi chọn mô hình và nhịp phát hành, thay vì đợi đến cuối dự án mới quyết định cách kiểm thử.

## 2. Các yếu tố cần đánh giá trước khi lựa chọn

Không nên chọn mô hình chỉ vì nhóm khác đang sử dụng hoặc vì một phương pháp đang phổ biến. Hãy đánh giá bối cảnh sản phẩm theo các yếu tố sau.

| Yếu tố | Câu hỏi cần trả lời | Tác động đến mô hình và phát hành |
|---|---|---|
| Mức độ ổn định của yêu cầu | Yêu cầu đã rõ và ít thay đổi hay cần khám phá qua phản hồi? | Yêu cầu ổn định có thể phù hợp với kế hoạch theo giai đoạn; yêu cầu biến động cần vòng lặp ngắn và thường xuyên đánh giá lại. |
| Mức ảnh hưởng của lỗi | Lỗi có thể gây mất dữ liệu, gián đoạn dịch vụ, thiệt hại tài chính hoặc ảnh hưởng an toàn không? | Rủi ro cao cần bằng chứng kiểm thử sâu hơn, phê duyệt rõ ràng và triển khai có kiểm soát. |
| Kiến trúc và phụ thuộc | Các thành phần có thể phát hành độc lập hay phải phối hợp thành một phiên bản? | Thành phần tách biệt hỗ trợ phát hành nhỏ; phụ thuộc chặt có thể cần phiên bản đồng bộ hoặc cửa sổ phát hành chung. |
| Ràng buộc bên ngoài | Có yêu cầu pháp lý, kiểm toán, chứng nhận, hợp đồng hoặc lịch bảo trì không? | Có thể cần cổng phê duyệt, hồ sơ truy vết, bằng chứng tái lập và lịch phát hành được kiểm soát. |
| Khả năng tự động hóa | Nhóm có môi trường ổn định, dữ liệu kiểm thử tin cậy và pipeline đủ nhanh không? | Tự động hóa tốt hỗ trợ tích hợp và phát hành thường xuyên; kiểm tra thủ công hoặc môi trường không ổn định có thể giới hạn tần suất. |
| Năng lực vận hành | Có giám sát, cảnh báo, sao lưu, rollback hoặc roll-forward và người trực xử lý sự cố không? | Phát hành nhanh cần khả năng quan sát và phục hồi tương xứng. |
| Nhu cầu phản hồi | Người dùng hoặc bên liên quan có thể đánh giá từng phần chức năng sớm không? | Phản hồi nhanh có lợi cho phát triển lặp và phát hành theo từng lát giá trị nhỏ. |

Đánh giá rủi ro nên xét ít nhất ba chiều: khả năng xảy ra lỗi, mức độ nghiêm trọng nếu lỗi xảy ra và khả năng phát hiện lỗi trước khi người dùng bị ảnh hưởng. Một thay đổi ít dòng mã vẫn có thể có rủi ro cao nếu nó chạm đến xác thực, thanh toán, phân quyền hoặc cấu trúc dữ liệu dùng chung. Ngược lại, thay đổi giao diện cô lập có thể có phạm vi ảnh hưởng nhỏ nhưng vẫn cần kiểm tra khả năng truy cập và các luồng sử dụng chính.

Khi chưa có dữ liệu đầy đủ, nhóm nên ghi rõ giả định, chọn một phạm vi thử nghiệm nhỏ và thu thập số liệu trước khi tăng tốc độ phát hành. Không nên dùng cảm nhận chung như “thay đổi này có vẻ đơn giản” làm căn cứ duy nhất để giảm kiểm thử.

## 3. Những mô hình phát triển thường gặp

### 3.1. Phát triển tuần tự theo giai đoạn

Trong mô hình tuần tự, nhóm thường hoàn thành một giai đoạn như phân tích yêu cầu, thiết kế, triển khai, kiểm thử và nghiệm thu trước khi chuyển sang giai đoạn tiếp theo. Mô hình này hữu ích khi phạm vi tương đối ổn định, các phụ thuộc cần được xác định sớm hoặc có yêu cầu phê duyệt và tài liệu hóa chính thức.

Ưu điểm là các mốc và trách nhiệm dễ nhận biết; hồ sơ quyết định và kết quả kiểm thử có thể được tổ chức theo từng cổng. Hạn chế là phản hồi từ phần mềm chạy thật thường đến muộn. Nếu giả định ban đầu sai, thay đổi có thể ảnh hưởng nhiều tài liệu, thành phần và kế hoạch đã hoàn tất.

Với mô hình này, chiến lược xác nhận nên bắt đầu từ giai đoạn yêu cầu và thiết kế. Nhóm cần rà soát yêu cầu có thể kiểm thử, tiêu chí nghiệm thu, rủi ro, kế hoạch tích hợp và điều kiện phát hành. Kiểm thử không nên chỉ xuất hiện ở giai đoạn cuối; kiểm thử đơn vị, phân tích tĩnh và kiểm thử thành phần vẫn có thể được thực hiện trong quá trình xây dựng.

### 3.2. Phát triển lặp và tăng dần

Trong mô hình lặp và tăng dần, nhóm chia sản phẩm thành những phần nhỏ có thể đánh giá. Mỗi vòng lặp tạo ra phản hồi để điều chỉnh yêu cầu, thiết kế hoặc thứ tự ưu tiên. Phần mềm được hoàn thiện dần qua các phiên bản tăng dần.

Mô hình này phù hợp khi nhóm cần khám phá nhu cầu, có thể chia giá trị thành các lát nhỏ và muốn kiểm tra giả định thường xuyên. Các vòng lặp có thể được tổ chức theo sprint hoặc theo luồng công việc liên tục. Scrum, Kanban và các cách làm Agile là những phương thức tổ chức công việc; chúng không tự động quy định sản phẩm phải phát hành vào một tần suất cố định.

Chiến lược kiểm thử cần tạo phản hồi trong từng vòng lặp: kiểm tra yêu cầu và tiêu chí nghiệm thu trước khi phát triển, kiểm thử tự động khi lập trình, kiểm thử tích hợp khi kết hợp thành phần và đánh giá chức năng với bên liên quan. Mỗi phần tăng thêm phải giữ cho các chức năng đã có tiếp tục hoạt động thông qua kiểm thử hồi quy phù hợp.

### 3.3. Tích hợp liên tục và phân phối liên tục

Tích hợp liên tục (Continuous Integration, CI) khuyến khích nhóm tích hợp thay đổi thường xuyên vào nhánh chung và chạy các kiểm tra tự động để phát hiện xung đột, lỗi biên dịch hoặc lỗi chức năng sớm.

Phân phối liên tục (Continuous Delivery, CD) mở rộng quy trình để tạo ra bản dựng có thể phát hành bất cứ lúc nào khi các cổng chất lượng được đáp ứng. Việc đưa bản dựng đến người dùng vẫn có thể cần một quyết định hoặc thao tác phát hành. Triển khai liên tục (Continuous Deployment) tự động đưa mọi thay đổi vượt qua các điều kiện đã định vào môi trường sản xuất.

Những cách làm này phù hợp với sản phẩm có thể chia thay đổi nhỏ, pipeline đáng tin cậy, kiểm thử tự động đủ độ bao phủ theo rủi ro và năng lực vận hành tốt. Chúng đòi hỏi nhóm quản lý cấu hình, dữ liệu kiểm thử, bí mật truy cập, chất lượng môi trường, cảnh báo và khả năng phục hồi. Tăng số lần triển khai mà không tăng khả năng kiểm chứng chỉ làm tăng số cơ hội đưa lỗi đến người dùng.

### 3.4. Mô hình kết hợp

Nhiều sản phẩm cần kết hợp các cách làm. Nhóm có thể phát triển theo vòng lặp ngắn, tích hợp mã nguồn liên tục, nhưng vẫn cần đánh giá kiến trúc, kiểm thử an toàn, phê duyệt nghiệp vụ hoặc chứng nhận theo các mốc chính thức. Đây là lựa chọn thực tế khi sản phẩm vừa cần phản hồi nhanh vừa chịu ràng buộc về rủi ro hoặc tuân thủ.

Điều quan trọng là xác định rõ cổng nào áp dụng cho mọi thay đổi, cổng nào chỉ áp dụng cho một loại rủi ro, ai chịu trách nhiệm phê duyệt và bằng chứng nào cần lưu. “Kết hợp” không nên trở thành tên gọi cho quy trình thiếu nhất quán.

## 4. Các kiểu nhịp phát hành

| Kiểu phát hành | Cách hoạt động | Khi phù hợp | Điều cần kiểm soát |
|---|---|---|---|
| Theo yêu cầu (on-demand) | Phát hành khi thay đổi đã sẵn sàng và đáp ứng điều kiện. | Sản phẩm có pipeline tự động, thành phần phát hành độc lập và vận hành trưởng thành. | Tính ổn định của cổng chất lượng, giám sát sau phát hành và khả năng phục hồi. |
| Theo lịch cố định | Phát hành vào ngày hoặc chu kỳ đã công bố, ví dụ hàng tuần hoặc hàng tháng. | Cần phối hợp truyền thông, hỗ trợ, đào tạo hoặc lịch bảo trì. | Quản lý phạm vi phiên bản, đóng băng thay đổi khi cần và kiểm thử toàn bộ nội dung của đợt. |
| Release train | Các thay đổi sẵn sàng được đưa lên chuyến phát hành kế tiếp; thay đổi chưa đạt điều kiện sẽ chờ chuyến sau. | Nhiều nhóm hoặc hệ thống cần phối hợp theo mốc chung. | Quy tắc đưa thay đổi vào hoặc rút khỏi phiên bản, tương thích và quản lý phụ thuộc. |
| Theo sự kiện hoặc mốc nghiệp vụ | Phát hành gắn với sự kiện như mùa bán hàng, kỳ học, hợp đồng hoặc chiến dịch. | Giá trị của chức năng phụ thuộc vào một thời điểm cụ thể. | Diễn tập trước sự kiện, tải dự kiến, phương án dự phòng và người ra quyết định. |
| Theo từng nhóm người dùng | Bật chức năng cho nội bộ, nhóm thử nghiệm hoặc một tỷ lệ người dùng trước khi mở rộng. | Cần giảm phạm vi ảnh hưởng và thu thập phản hồi trong môi trường thực tế. | Tiêu chí mở rộng/dừng, bảo vệ dữ liệu, khả năng tắt tính năng và truyền thông. |

Phát hành theo từng nhóm người dùng thường được gọi là progressive delivery. Các kỹ thuật như canary release và blue-green deployment hỗ trợ kiểm soát quá trình đưa phiên bản mới vào hoạt động. Canary bắt đầu với một phần nhỏ lưu lượng hoặc người dùng rồi mở rộng nếu các chỉ số ổn định. Blue-green duy trì hai môi trường tương đương để chuyển lưu lượng giữa phiên bản cũ và mới. Cả hai đều cần kiểm tra khả năng tương thích dữ liệu và đường quay lại.

Không có tần suất “hàng ngày”, “hàng tuần” hay “hàng tháng” nào tự thân chứng minh chất lượng. Một lịch phát hành tốt là lịch mà nhóm có thể duy trì với chất lượng ổn định, phản hồi đủ nhanh và mức rủi ro chấp nhận được.

## 5. Ghép mô hình phát triển với nhịp phát hành và kiểm thử

Mô hình phát triển và nhịp phát hành không cần giống nhau giữa các sản phẩm. Bảng sau minh họa cách kết hợp thường gặp; đây là điểm bắt đầu để thảo luận, không phải công thức bắt buộc.

| Bối cảnh | Mô hình có thể chọn | Nhịp phát hành có thể chọn | Trọng tâm xác nhận |
|---|---|---|---|
| Sản phẩm số có yêu cầu thay đổi thường xuyên, chức năng tách rời | Lặp/tăng dần, CI và CD | Theo yêu cầu hoặc nhiều đợt nhỏ trong tuần | Kiểm thử đơn vị, hợp đồng API, tích hợp, luồng chính, kiểm tra bảo mật tự động, smoke test và giám sát sau phát hành. |
| Hệ thống doanh nghiệp có nhiều nhóm và phụ thuộc phiên bản | Lặp theo nhóm kết hợp mốc đồng bộ | Release train hàng tháng hoặc theo quý | Kiểm thử hợp đồng giữa hệ thống, hồi quy liên hệ thống, kiểm tra di trú dữ liệu, nghiệm thu và điều phối triển khai. |
| Sản phẩm chịu yêu cầu tuân thủ hoặc rủi ro cao | Kết hợp vòng lặp phát triển với cổng kiểm soát chính thức | Theo lịch hoặc theo mốc được phê duyệt | Truy vết yêu cầu, rà soát độc lập, kiểm thử an toàn/bảo mật, bằng chứng có thể tái lập, phê duyệt và kế hoạch ứng phó. |
| Sản phẩm phần cứng hoặc thay đổi khó đảo ngược | Tuần tự hoặc kết hợp theo giai đoạn | Theo phiên bản, lô sản xuất hoặc cửa sổ bảo trì | Kiểm thử tích hợp hệ thống, tương thích, độ bền, điều kiện biên, xác nhận tại môi trường đại diện và phương án xử lý lỗi sau triển khai. |

Khi ghép hai quyết định, hãy kiểm tra ba điểm. Thứ nhất, mỗi đơn vị công việc có đủ nhỏ để kiểm chứng và đưa ra quyết định độc lập không? Thứ hai, các thành phần có thể tương thích khi được triển khai ở thời điểm khác nhau không? Thứ ba, nếu một thay đổi gây lỗi, nhóm có thể xác định phạm vi ảnh hưởng và phục hồi trong thời gian chấp nhận được không?

Nếu câu trả lời cho các câu hỏi này chưa rõ, nhóm nên giảm phạm vi của lần phát hành thử, bổ sung kiểm thử hợp đồng hoặc kiểm tra tương thích, và làm rõ phương án phục hồi trước khi tăng tần suất.

## 6. Quy trình lựa chọn có thể áp dụng

### Bước 1: Xác định lát giá trị và ranh giới hệ thống

Mô tả chức năng cần cung cấp, người dùng nhận được giá trị gì và thành phần nào bị ảnh hưởng. Tách công việc thành các lát nhỏ có thể đánh giá độc lập. Ghi lại các hệ thống, API, dịch vụ bên ngoài, cơ sở dữ liệu và nhóm cần phối hợp.

### Bước 2: Phân loại rủi ro của thay đổi

Đánh giá xác suất lỗi, hậu quả, khả năng phát hiện và khả năng phục hồi. Ghi nhận các luồng quan trọng như đăng nhập, phân quyền, thanh toán, xử lý dữ liệu cá nhân, sao lưu và khôi phục. Xác định thay đổi nào cần rà soát chuyên môn hoặc phê duyệt bổ sung.

### Bước 3: Chọn vòng phản hồi trong phát triển

Nếu yêu cầu ổn định và có cổng nghiệm thu bắt buộc, có thể dùng các giai đoạn rõ ràng. Nếu cần học từ người dùng, ưu tiên vòng lặp ngắn và bản tăng dần. Nếu nhiều thay đổi nhỏ có thể tích hợp an toàn, xây dựng CI và quy tắc làm việc trên nhánh chung. Có thể kết hợp các lựa chọn khi từng phần của sản phẩm có đặc điểm khác nhau.

### Bước 4: Chọn nhịp phát hành theo khả năng kiểm chứng

Xác định nhóm cần phát hành khi nào, ai cần phối hợp, thời điểm nào người dùng chịu tác động và có thể triển khai độc lập hay không. Chọn phát hành theo yêu cầu khi pipeline, kiểm thử và vận hành đã đủ tin cậy. Chọn lịch cố định hoặc release train khi cần phối hợp. Dùng triển khai theo giai đoạn khi muốn giới hạn phạm vi ảnh hưởng.

### Bước 5: Định nghĩa cổng chất lượng theo rủi ro

Với mỗi loại thay đổi, chỉ rõ kiểm tra nào bắt buộc, ai xem kết quả, điều kiện nào làm dừng phát hành và bằng chứng nào được lưu. Cổng chất lượng nên tự động hóa các kiểm tra lặp lại, đồng thời quy định rõ trường hợp cần đánh giá thủ công. Không nên áp dụng cùng một bộ kiểm tra nặng cho mọi thay đổi nếu rủi ro khác nhau.

### Bước 6: Chuẩn bị triển khai và phục hồi

Xác định cách phát hành, cách quan sát hành vi sau phát hành, ngưỡng dừng hoặc rollback, người chịu trách nhiệm và cách thông báo. Với thay đổi cơ sở dữ liệu, cần xem xét tương thích ngược, thứ tự triển khai và khả năng chạy đồng thời phiên bản cũ/mới. Rollback ứng dụng không tự động đảo ngược được dữ liệu đã biến đổi.

### Bước 7: Thử nghiệm, đo lường và điều chỉnh

Bắt đầu với một nhóm hoặc một phạm vi nhỏ. Theo dõi thời gian phản hồi kiểm thử, lỗi lọt ra ngoài, sự cố sau phát hành, thời gian phục hồi và phản hồi người dùng. Dựa trên kết quả để điều chỉnh độ dài vòng lặp, tần suất phát hành, bộ kiểm thử và quy tắc phê duyệt.

## 7. Thiết kế hoạt động kiểm thử theo nhịp phát hành

Một pipeline có thể chia kiểm tra thành nhiều lớp. Các lớp dưới đây là gợi ý; nhóm cần chọn chúng theo rủi ro và đặc điểm kỹ thuật của sản phẩm.

| Thời điểm | Kiểm tra thường dùng | Mục đích và điều kiện tiếp tục |
|---|---|---|
| Khi tạo pull request | Format/lint, phân tích tĩnh, kiểm thử đơn vị, kiểm thử thành phần, rà soát mã nguồn | Phát hiện lỗi nhanh; yêu cầu các kiểm tra bắt buộc đạt trước khi hợp nhất. |
| Sau khi hợp nhất | Build có thể tái lập, kiểm thử tích hợp, kiểm thử hợp đồng API, kiểm tra migration và dependency | Xác nhận các thành phần hoạt động cùng nhau và tạo được hiện vật phát hành xác định. |
| Trước khi phát hành | Kiểm thử đầu cuối cho luồng quan trọng, hồi quy theo phạm vi ảnh hưởng, bảo mật, hiệu năng, khả năng chịu lỗi và nghiệm thu khi cần | Xác nhận phiên bản đáp ứng tiêu chí chấp nhận và rủi ro còn lại được người có thẩm quyền chấp nhận. |
| Trong khi triển khai | Smoke test, health check, kiểm tra cấu hình, xác nhận kết nối và dữ liệu | Phát hiện lỗi triển khai hoặc cấu hình trước khi mở rộng lưu lượng. |
| Sau khi phát hành | Theo dõi lỗi, độ trễ, tỷ lệ giao dịch thành công, log, cảnh báo và phản hồi hỗ trợ | Xác nhận hệ thống hoạt động đúng trong điều kiện thực tế; kích hoạt dừng, rollback hoặc roll-forward nếu vượt ngưỡng. |

Nguyên tắc kiểm thử theo tầng giúp phản hồi nhanh ở nơi có chi phí thấp. Kiểm thử đơn vị thường nhanh và cô lập; kiểm thử tích hợp xác nhận ranh giới giữa các thành phần; kiểm thử đầu cuối xác nhận một số luồng quan trọng từ góc nhìn người dùng. Không cần nhân bản mọi trường hợp kiểm thử ở tất cả các tầng. Hãy đặt mỗi kiểm tra ở tầng có thể phát hiện lỗi hiệu quả nhất.

Với nhịp phát hành nhanh, kiểm thử tự động cần đáng tin cậy và cho kết quả đủ sớm để không tạo hàng đợi. Kiểm thử không ổn định (flaky test) làm giảm niềm tin vào pipeline; nhóm cần theo dõi, sửa hoặc cách ly có thời hạn các kiểm thử này. Mọi trường hợp bỏ qua cổng chất lượng phải có lý do, người chịu trách nhiệm, phạm vi ảnh hưởng và thời hạn xử lý rõ ràng.

Với nhịp phát hành theo lịch, cần kiểm soát việc thay đổi phạm vi khi gần ngày phát hành. Mỗi thay đổi được thêm vào phiên bản phải có kết quả kiểm thử và đánh giá ảnh hưởng. Nếu một thay đổi chưa đạt điều kiện, quy trình cần cho phép rút nó khỏi phiên bản mà không làm mất khả năng phát hành các phần đã sẵn sàng.

## 8. Ví dụ thực tế

### Ví dụ A: Nền tảng SaaS cộng tác

Một nền tảng cộng tác web thường xuyên bổ sung chức năng nhỏ và có thể tách dịch vụ theo miền nghiệp vụ. Nhóm chọn phát triển lặp, tích hợp mã nguồn nhiều lần mỗi ngày và tạo bản dựng sau mỗi lần hợp nhất. Các kiểm tra lint, đơn vị, hợp đồng API và tích hợp chạy tự động trong pipeline. Luồng đăng nhập, tạo dự án và chia sẻ tài liệu được kiểm thử đầu cuối trước các đợt phát hành có ảnh hưởng lớn.

Nhóm triển khai phiên bản đến môi trường sản xuất khi các cổng chất lượng đạt, nhưng bật chức năng bằng feature flag cho nhân viên trước. Sau khi smoke test và theo dõi chỉ số ổn định, nhóm mở cho một tỷ lệ nhỏ khách hàng rồi tăng dần. Nếu tỷ lệ lỗi hoặc độ trễ vượt ngưỡng đã thống nhất, nhóm dừng mở rộng và tắt flag hoặc chuyển về phiên bản ổn định. Cách làm này cho phép tích hợp thường xuyên và kiểm soát thời điểm người dùng tiếp cận chức năng.

### Ví dụ B: Hệ thống xử lý giao dịch có yêu cầu kiểm soát cao

Một hệ thống xử lý giao dịch có nhiều phụ thuộc và cần lưu vết quyết định. Nhóm vẫn có thể phát triển theo vòng lặp ngắn, nhưng mỗi phiên bản phát hành đi qua cổng rà soát bảo mật, kiểm thử tải, kiểm thử phục hồi, kiểm tra tương thích dữ liệu và phê duyệt nghiệp vụ. Phiên bản được phát hành theo cửa sổ đã thống nhất, kèm hiện vật build được định danh và kết quả kiểm thử có thể truy vết.

Trước khi mở rộng lưu lượng, nhóm kiểm tra các giao dịch đại diện và đối chiếu số liệu. Kế hoạch phục hồi cần mô tả rõ trường hợp có thể rollback ứng dụng, trường hợp phải roll-forward và cách xử lý giao dịch đang dở. Tần suất phát hành có thể thấp hơn nền tảng SaaS, nhưng các thay đổi nhỏ vẫn nên được tích hợp và kiểm tra sớm để tránh dồn rủi ro vào cuối chu kỳ.

## 9. Đo lường để cải thiện quyết định

Các chỉ số vận hành và chất lượng giúp kiểm tra xem mô hình đã chọn có phù hợp không:

- **Deployment frequency:** tần suất triển khai thành công đến môi trường đích.
- **Lead time for changes:** thời gian từ khi thay đổi được đưa vào quy trình đến khi triển khai.
- **Change failure rate:** tỷ lệ triển khai gây ra sự cố, rollback hoặc cần sửa nóng.
- **Time to restore service:** thời gian khôi phục dịch vụ sau sự cố liên quan đến thay đổi.
- **Escaped defects:** lỗi được phát hiện sau khi phiên bản đã đến người dùng hoặc môi trường vận hành.
- **Thời gian phản hồi pipeline:** thời gian từ lúc gửi thay đổi đến khi có kết quả kiểm tra đủ để ra quyết định.
- **Tỷ lệ kiểm thử không ổn định:** tỷ lệ lần chạy cho kết quả không nhất quán khi mã nguồn không thay đổi.

Không nên tối ưu một chỉ số riêng lẻ. Tăng tần suất triển khai nhưng đồng thời tăng lỗi lọt ra ngoài và thời gian phục hồi là dấu hiệu quy trình chưa cân bằng. Tỷ lệ kiểm thử đạt cao cũng không đảm bảo chất lượng nếu bộ kiểm thử bỏ sót rủi ro quan trọng. Hãy đọc các chỉ số cùng bối cảnh, phân tích xu hướng và dùng chúng để tìm điểm nghẽn.

## 10. Những sai lầm thường gặp

- **Đồng nhất Agile với phát hành liên tục:** nhóm có thể làm việc theo sprint nhưng phát hành theo tháng; cũng có thể làm theo luồng liên tục và phát hành theo lịch. Cần quyết định riêng hai vấn đề.
- **Đợi đến cuối mới kiểm thử:** lỗi yêu cầu, thiết kế và tích hợp thường khó sửa hơn khi đã tích lũy qua nhiều giai đoạn. Hãy đưa kiểm chứng vào từng bước.
- **Tăng tốc trước khi có khả năng phục hồi:** phát hành thường xuyên mà thiếu giám sát, rollback hoặc người chịu trách nhiệm sẽ làm tăng tác động của sự cố.
- **Áp dụng một cổng kiểm thử cho mọi thay đổi:** kiểm tra cần tương xứng với rủi ro và phạm vi ảnh hưởng.
- **Dùng độ bao phủ mã nguồn làm thước đo duy nhất:** coverage cho biết mã nào đã được thực thi, nhưng không chứng minh các khẳng định quan trọng đã được kiểm tra đúng.
- **Để phiên bản phát hành quá lớn:** lô thay đổi lớn làm khó xác định nguyên nhân khi lỗi xuất hiện và làm tăng phạm vi hồi quy.
- **Bỏ qua chất lượng môi trường và dữ liệu kiểm thử:** kết quả không đáng tin cậy nếu môi trường khác biệt đáng kể so với sản xuất hoặc dữ liệu không đại diện.
- **Không có tiêu chí dừng rõ ràng:** trước khi phát hành theo giai đoạn, cần định nghĩa ngưỡng lỗi, độ trễ, tỷ lệ thành công và người có quyền dừng mở rộng.

## 11. Checklist trước khi chốt mô hình và nhịp phát hành

- [ ] Mục tiêu sản phẩm, lát giá trị và các thành phần bị ảnh hưởng đã được xác định.
- [ ] Rủi ro về người dùng, dữ liệu, bảo mật, vận hành và tuân thủ đã được đánh giá.
- [ ] Nhóm đã phân biệt nhịp tích hợp, triển khai và phát hành.
- [ ] Mô hình phát triển phù hợp với độ ổn định của yêu cầu và nhu cầu phản hồi.
- [ ] Nhịp phát hành phù hợp với mức độ phụ thuộc, năng lực tự động hóa và lịch vận hành.
- [ ] Các cổng kiểm thử có tiêu chí đạt/trượt, người chịu trách nhiệm và bằng chứng cần lưu.
- [ ] Có cách quản lý thay đổi chưa sẵn sàng mà không chặn toàn bộ phiên bản.
- [ ] Có giám sát sau phát hành, tiêu chí dừng, phương án rollback/roll-forward và người xử lý.
- [ ] Nhóm có chỉ số để đánh giá chất lượng và điều chỉnh quy trình sau mỗi chu kỳ.

## Kết luận

Hãy chọn mô hình phát triển theo cách nhóm cần học hỏi, phối hợp và kiểm chứng công việc; chọn nhịp phát hành theo khả năng cung cấp giá trị an toàn cho người dùng. Thiết kế kiểm thử, cổng chất lượng, giám sát và phục hồi cùng với hai quyết định đó. Khi rủi ro hoặc năng lực của sản phẩm thay đổi, nhóm cần đánh giá lại lựa chọn dựa trên bằng chứng vận hành và chất lượng thực tế.
