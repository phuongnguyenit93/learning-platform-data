# Kết hợp đặc tả sẵn với khám phá trong quá trình thực thi

Trong chiến lược kiểm thử xác thực (validation testing strategy), nhóm cần vừa kiểm tra có hệ thống những điều đã biết, vừa tìm hiểu những hành vi và rủi ro chưa được dự đoán đầy đủ. Hai cách tiếp cận thường dùng là **kiểm thử dựa trên đặc tả sẵn (scripted testing)** và **kiểm thử thăm dò (exploratory testing)**. Kết hợp chúng giúp nhóm duy trì khả năng lặp lại và truy vết, đồng thời tận dụng quan sát, suy luận và khả năng thích ứng của người kiểm thử.

Kiểm thử dựa trên đặc tả sẵn chuẩn bị trước mục tiêu, điều kiện, dữ liệu, các bước thực hiện và kết quả mong đợi. Người kiểm thử thực hiện theo kịch bản đã thiết kế và ghi nhận kết quả. Kiểm thử thăm dò kết hợp việc học hỏi sản phẩm, thiết kế thử nghiệm và thực thi trong cùng một hoạt động. Người kiểm thử sử dụng thông tin thu được từ mỗi thao tác để quyết định bước tiếp theo, kiểm tra giả thuyết và tìm vấn đề mới.

Hai cách tiếp cận có thể dùng trong cùng một giai đoạn, cùng một chức năng hoặc thậm chí trong một phiên làm việc. Nhóm nên chọn tỷ trọng theo mục tiêu, rủi ro, mức độ ổn định của yêu cầu, độ phức tạp của sản phẩm và bằng chứng cần có. Không có một tỷ lệ cố định phù hợp với mọi dự án.

## 1. Kiểm thử dựa trên đặc tả sẵn

Kiểm thử dựa trên đặc tả sẵn bắt đầu từ yêu cầu, tiêu chí chấp nhận, quy tắc nghiệp vụ hoặc thiết kế kiểm thử đã được thống nhất. Trước khi thực thi, người kiểm thử xác định những điều kiện cần chuẩn bị và hành vi được kỳ vọng.

Một ca kiểm thử thường có các thành phần:

- **Mục đích:** Yêu cầu, quy tắc hoặc rủi ro cần kiểm tra.
- **Điều kiện tiên quyết:** Trạng thái hệ thống, quyền người dùng, cấu hình hoặc dữ liệu cần có.
- **Dữ liệu đầu vào:** Giá trị, tài khoản, bản ghi hoặc tệp dùng trong ca kiểm thử.
- **Các bước thực hiện:** Hành động theo thứ tự có thể lặp lại.
- **Kết quả mong đợi:** Trạng thái, dữ liệu, thông báo hoặc phản hồi cần quan sát.
- **Kết quả thực tế và bằng chứng:** Điều xảy ra khi chạy, trạng thái đạt/không đạt/bị chặn và thông tin giúp kiểm tra lại.

Ví dụ, ca kiểm thử áp dụng mã giảm giá có thể yêu cầu một giỏ hàng đủ điều kiện, một mã còn hiệu lực và tài khoản khách hàng hợp lệ. Các bước thêm sản phẩm, nhập mã và xác nhận tổng tiền được mô tả trước. Kết quả mong đợi nêu rõ mức giảm, thuế, phí vận chuyển và tổng tiền sau cùng.

Ưu điểm của cách tiếp cận này:

- **Tính lặp lại:** Người khác có thể thực hiện lại cùng điều kiện để xác nhận lỗi hoặc kiểm tra bản sửa.
- **Khả năng truy vết:** Có thể liên kết ca kiểm thử với yêu cầu, tiêu chí chấp nhận và rủi ro.
- **Khả năng lập kế hoạch:** Nhóm có thể ước lượng công sức, chuẩn bị dữ liệu và phân công công việc.
- **Khả năng so sánh:** Kết quả giữa các phiên bản hoặc môi trường có thể được đối chiếu nếu điều kiện thực thi tương đương.
- **Tiềm năng tự động hóa:** Các ca ổn định, lặp lại thường xuyên và có kết quả xác định có thể được tự động hóa.

Hạn chế xuất hiện khi đặc tả thiếu, lỗi thời hoặc chỉ mô tả luồng thông thường. Một bộ ca kiểm thử có thể chạy đúng như kế hoạch nhưng bỏ qua hành vi bất ngờ, cách người dùng thao tác khác dự kiến, tương tác giữa nhiều tính năng hoặc lỗi chỉ xuất hiện trong một chuỗi điều kiện đặc biệt. Nếu người kiểm thử chỉ tập trung hoàn thành danh sách, họ có thể bỏ qua tín hiệu bất thường phát hiện trong lúc chạy.

## 2. Kiểm thử thăm dò

Kiểm thử thăm dò là cách tiếp cận trong đó người kiểm thử chủ động tìm hiểu sản phẩm, thiết kế thử nghiệm, thực hiện thao tác và đánh giá kết quả trong một chu trình liên tục. Thông tin thu được ở bước trước ảnh hưởng đến lựa chọn thử nghiệm tiếp theo.

Ví dụ, khi khám phá luồng thanh toán, người kiểm thử bắt đầu bằng một giao dịch thông thường. Sau khi quan sát hệ thống tạo đơn hàng trước khi nhận phản hồi cuối cùng từ cổng thanh toán, họ đặt giả thuyết rằng việc mất kết nối ở thời điểm đó có thể để lại đơn hàng ở trạng thái không nhất quán. Họ tiếp tục thử ngắt kết nối, tải lại trang, gửi lại yêu cầu và kiểm tra trạng thái giao dịch. Chuỗi thử nghiệm mới xuất phát từ hiểu biết vừa thu được.

Kiểm thử thăm dò có ba hoạt động diễn ra đan xen:

1. **Học hỏi:** Tìm hiểu chức năng, quy tắc, kiến trúc có thể quan sát, dữ liệu và hành vi của hệ thống.
2. **Thiết kế:** Hình thành câu hỏi, giả thuyết và lựa chọn thử nghiệm tiếp theo dựa trên rủi ro hoặc tín hiệu vừa phát hiện.
3. **Thực thi và đánh giá:** Thao tác, quan sát kết quả, ghi lại bằng chứng và điều chỉnh hướng khám phá.

Thăm dò không có nghĩa là thao tác ngẫu nhiên hoặc bỏ qua kế hoạch. Một phiên thăm dò tốt có mục tiêu, phạm vi, thời lượng và ghi chép đủ để người khác hiểu đã điều tra điều gì. Người kiểm thử cần duy trì tư duy phản biện: kết quả nào là bất thường, điều kiện nào có thể giải thích nó, giả thuyết nào cần kiểm tra thêm và rủi ro nào vẫn chưa được khảo sát.

Ưu điểm của cách tiếp cận này:

- Phát hiện vấn đề chưa được mô tả trong yêu cầu hoặc ca kiểm thử.
- Thích ứng nhanh khi yêu cầu thay đổi, sản phẩm mới hoặc hành vi thực tế khác dự đoán.
- Khai thác kinh nghiệm, trực giác và hiểu biết nghiệp vụ của người kiểm thử.
- Tìm ra tương tác giữa các tính năng, chuỗi thao tác bất thường và tình huống biên khó liệt kê trước.
- Tạo hiểu biết mới để cải thiện đặc tả, bộ ca kiểm thử và ưu tiên kiểm thử.

Hạn chế của thăm dò là kết quả phụ thuộc vào kỹ năng, kiến thức và cách ghi nhận của người thực hiện. Nếu không có mục tiêu hoặc bằng chứng, phiên thăm dò khó lặp lại và khó chứng minh phần nào đã được kiểm tra. Một phiên làm việc thú vị nhưng không ghi lại dữ liệu, bước tái hiện và kết luận có thể tạo ra rất ít giá trị cho nhóm.

## 3. So sánh hai cách tiếp cận

| Khía cạnh | Dựa trên đặc tả sẵn | Thăm dò |
|---|---|---|
| Thời điểm thiết kế | Phần lớn thiết kế trước khi thực thi | Thiết kế liên tục trong khi thực thi |
| Đầu vào | Yêu cầu, tiêu chí chấp nhận, quy tắc và ca kiểm thử | Mục tiêu khám phá, hiểu biết hiện có, giả thuyết và tín hiệu quan sát |
| Cách thực hiện | Theo các bước và dữ liệu đã chuẩn bị | Điều chỉnh thử nghiệm theo thông tin mới |
| Kết quả mong đợi | Được xác định trước cho từng bước | Có thể được làm rõ khi hiểu thêm hành vi, nhưng vẫn cần một quy tắc đánh giá |
| Điểm mạnh | Lặp lại, truy vết, lập kế hoạch và tự động hóa | Thích ứng, học hỏi và phát hiện điều chưa dự đoán |
| Rủi ro nếu dùng riêng | Bỏ sót tình huống ngoài đặc tả hoặc đặc tả sai | Khó lặp lại, khó đánh giá độ bao phủ nếu thiếu ghi chép |
| Bằng chứng | Ca kiểm thử, dữ liệu, kết quả mong đợi và thực tế | Mục tiêu phiên, ghi chú, thao tác, dữ liệu, quan sát và phát hiện |
| Phù hợp khi | Quy tắc ổn định, yêu cầu truy vết cao, hồi quy thường xuyên | Sản phẩm mới, yêu cầu chưa rõ, rủi ro chưa biết hoặc cần điều tra sâu |

Sự khác biệt chủ yếu nằm ở cách thiết kế và điều chỉnh thử nghiệm, không nằm ở việc có hay không có tài liệu. Một phiên thăm dò vẫn có thể được ghi chép chi tiết; một ca kiểm thử đặc tả sẵn vẫn có thể được người kiểm thử thực hiện thủ công. Cả hai đều cần mục tiêu và bằng chứng.

## 4. Khi nào nên ưu tiên từng cách tiếp cận?

Hãy chọn cách tiếp cận dựa trên loại quyết định cần hỗ trợ và mức độ hiểu biết hiện có.

**Ưu tiên đặc tả sẵn khi:**

- Quy tắc nghiệp vụ và tiêu chí chấp nhận đã rõ, ổn định.
- Chức năng có tác động lớn và cần bằng chứng truy vết đến từng yêu cầu.
- Cần kiểm tra lại bản sửa hoặc chạy hồi quy qua nhiều phiên bản.
- Quy trình có yêu cầu kiểm toán, phê duyệt hoặc lưu hồ sơ cụ thể.
- Kết quả có thể xác định trước và điều kiện thực thi có thể chuẩn hóa.

**Ưu tiên thăm dò khi:**

- Chức năng mới, yêu cầu chưa đầy đủ hoặc đang thay đổi nhanh.
- Nhóm chưa hiểu rõ hành vi thực tế hoặc có nhiều tương tác giữa các thành phần.
- Có dấu hiệu bất thường nhưng chưa xác định được nguyên nhân.
- Cần đánh giá trải nghiệm, khả năng sử dụng hoặc các luồng người dùng linh hoạt.
- Rủi ro có thể xuất hiện trong các tổ hợp điều kiện khó liệt kê đầy đủ.

**Kết hợp ngay từ đầu khi:**

- Luồng nghiệp vụ quan trọng có cả quy tắc ổn định lẫn nhiều tình huống lỗi.
- Một lỗi có thể gây tổn thất lớn, trong khi đặc tả chưa bao phủ mọi tình huống.
- Cần kiểm tra yêu cầu đã biết và tìm thêm rủi ro mới trước quyết định phát hành.
- Kết quả thăm dò có thể làm thay đổi cách hiểu yêu cầu hoặc ưu tiên kiểm thử.

Không nên dùng mức độ ổn định của yêu cầu làm tiêu chí duy nhất. Một chức năng ổn định vẫn có thể có rủi ro thăm dò cao do tích hợp phức tạp; một chức năng mới vẫn cần ca kiểm thử đặc tả sẵn cho các quy tắc bắt buộc đã rõ.

## 5. Tổ chức một chu trình kết hợp

Một chu trình thực tế có thể gồm các bước sau:

1. **Xác định mục tiêu và rủi ro:** Nêu kết quả cần xác nhận, người dùng liên quan, hậu quả nếu sai và các giả định quan trọng.
2. **Rà soát đặc tả:** Thu thập yêu cầu, quy tắc, tiêu chí chấp nhận, thiết kế hiện có và ca kiểm thử trước đó. Ghi nhận điểm chưa rõ hoặc mâu thuẫn.
3. **Chuẩn bị kiểm thử đặc tả sẵn:** Chọn các kịch bản quan trọng, dữ liệu, điều kiện tiên quyết, kết quả mong đợi và bằng chứng cần lưu.
4. **Thực hiện các kiểm tra đã định:** Xác nhận hành vi đã biết và phát hiện sai lệch so với yêu cầu.
5. **Dành thời gian thăm dò có mục tiêu:** Dựa trên rủi ro, hiểu biết sản phẩm và tín hiệu từ các lần chạy để điều tra các nhánh chưa được bao phủ.
6. **Ghi nhận và đánh giá phát hiện:** Lưu bước tái hiện, dữ liệu, trạng thái hệ thống, bằng chứng và tác động. Phân biệt lỗi thực tế với câu hỏi hoặc hành vi cần làm rõ.
7. **Chuyển hiểu biết mới thành kiểm thử có thể lặp lại:** Khi phát hiện một tình huống có giá trị, tạo hoặc cập nhật ca kiểm thử, bổ sung yêu cầu hoặc ghi nhận rủi ro.
8. **Kiểm thử xác nhận và hồi quy:** Sau khi sửa lỗi, chạy lại kịch bản liên quan và các kiểm tra hồi quy có nguy cơ bị ảnh hưởng.
9. **Đánh giá độ bao phủ và rủi ro còn lại:** Xác định mục tiêu đã có bằng chứng, vùng chưa kiểm tra, giới hạn của môi trường và quyết định tiếp theo.

Chu trình này có thể lặp lại nhiều lần. Một phát hiện từ thăm dò có thể làm thay đổi đặc tả hoặc sinh thêm ca kiểm thử; kết quả của ca kiểm thử mới lại gợi ý hướng khám phá tiếp theo.

## 6. Thiết kế phiên thăm dò có mục tiêu

Để thăm dò có thể phối hợp với hoạt động kiểm thử chung, nhóm có thể sử dụng **test charter** (đề cương phiên thăm dò). Charter không cần liệt kê trước mọi thao tác; nó xác định khu vực và câu hỏi cần điều tra.

Một charter nên nêu:

- **Mục tiêu:** Điều cần tìm hiểu hoặc rủi ro cần khảo sát.
- **Phạm vi:** Chức năng, vai trò, nền tảng hoặc tích hợp được xem xét.
- **Thời lượng:** Khoảng thời gian tập trung, thường được giới hạn để giữ trọng tâm.
- **Dữ liệu và điều kiện:** Tài khoản, trạng thái ban đầu, thiết bị và môi trường cần có.
- **Ý tưởng khám phá:** Các hướng thử nghiệm hoặc câu hỏi khởi đầu, không phải danh sách bước bắt buộc.
- **Bằng chứng cần ghi:** Thao tác đáng chú ý, dữ liệu, kết quả, ảnh hoặc log và phát hiện.
- **Điều kiện dừng hoặc mở rộng:** Khi nào kết thúc, khi nào cần báo ngay hoặc tạo phiên điều tra tiếp theo.

Ví dụ charter:

```text
Mục tiêu: Tìm lỗi có thể tạo giao dịch thanh toán trùng.
Phạm vi: Luồng thanh toán thẻ trên môi trường sandbox.
Thời lượng: 45 phút.
Điều kiện: Có đơn hàng thử, tài khoản hợp lệ và log giao dịch.
Hướng khám phá:
  - Gửi lại yêu cầu sau timeout.
  - Tải lại trang khi đang chờ phản hồi.
  - Mở cùng đơn hàng trên hai cửa sổ.
  - Thử thao tác khi phản hồi từ cổng thanh toán đến muộn.
Bằng chứng: Mã yêu cầu, mã giao dịch, trạng thái đơn hàng,
            thời điểm thao tác và log liên quan.
Kết quả: Ghi lỗi, câu hỏi chưa giải đáp và tình huống cần
         chuyển thành ca kiểm thử hồi quy.
```

Các hướng khám phá trong charter là điểm xuất phát. Nếu trong phiên xuất hiện một tín hiệu quan trọng khác, người kiểm thử có thể điều chỉnh hướng đi và ghi lại lý do. Khi phát hiện lỗi nghiêm trọng hoặc rủi ro bảo mật, cần thực hiện quy trình báo cáo và xử lý sự cố của nhóm ngay, không chờ hết thời lượng phiên.

## 7. Ghi chép để kết quả thăm dò có thể sử dụng lại

Ghi chép không cần biến phiên thăm dò thành một kịch bản dài. Mục tiêu là lưu đủ thông tin để nhóm hiểu điều đã kiểm tra, tái hiện phát hiện và quyết định bước tiếp theo.

Nên ghi lại:

| Nội dung | Ví dụ |
|---|---|
| Phiên và người thực hiện | Mã phiên, người kiểm thử, thời điểm |
| Mục tiêu và phạm vi | Khảo sát xử lý timeout của thanh toán |
| Phiên bản và môi trường | Bản dựng, trình duyệt, cấu hình sandbox |
| Dữ liệu ban đầu | Mã đơn hàng thử, vai trò tài khoản, trạng thái trước khi thử |
| Hoạt động đã thực hiện | Gửi yêu cầu, ngắt kết nối, tải lại trang, kiểm tra trạng thái |
| Quan sát | Đơn hàng vẫn ở trạng thái chờ nhưng giao dịch đã được ghi nhận |
| Bằng chứng | Log, mã giao dịch, ảnh chụp hoặc bản ghi thời gian |
| Phát hiện và tác động | Có nguy cơ khách hàng gửi lại và bị tạo giao dịch trùng |
| Việc cần làm tiếp | Tạo lỗi, kiểm tra idempotency, bổ sung ca hồi quy |

Khi báo lỗi, mô tả bước tái hiện ngắn gọn và có thứ tự; nêu kết quả mong đợi, kết quả thực tế, điều kiện môi trường, dữ liệu và mức độ ảnh hưởng. Nếu chưa chắc đó là lỗi, ghi rõ câu hỏi cần xác minh và trao đổi với người phụ trách quy tắc nghiệp vụ. Điều này tránh biến mọi khác biệt chưa hiểu thành defect.

Cuối phiên, có thể tóm tắt theo ba nhóm: **đã kiểm tra**, **đã phát hiện hoặc học được**, và **chưa kiểm tra/đề xuất tiếp tục**. Cách ghi này giúp người khác hiểu giới hạn của phiên và tránh suy diễn rằng khu vực chưa nhắc đến đã được xác nhận.

## 8. Chuyển phát hiện thành tài sản kiểm thử

Một giá trị quan trọng của thăm dò là giúp cải thiện hệ thống kiểm thử về lâu dài. Không phải mọi thao tác trong phiên đều cần trở thành ca kiểm thử cố định. Hãy chọn những tình huống có giá trị lặp lại, gắn với rủi ro đáng kể hoặc có khả năng tái phát.

Sau một phát hiện, nhóm có thể:

- Bổ sung hoặc làm rõ yêu cầu và tiêu chí chấp nhận nếu hành vi mong đợi chưa được xác định.
- Tạo ca kiểm thử đặc tả sẵn cho tình huống có thể tái hiện và cần kiểm tra thường xuyên.
- Tự động hóa ca hồi quy nếu điều kiện ổn định, kết quả xác định và chi phí bảo trì hợp lý.
- Cập nhật dữ liệu kiểm thử, điều kiện môi trường hoặc ma trận nền tảng.
- Bổ sung rủi ro mới hoặc điều chỉnh mức ưu tiên của rủi ro hiện tại.
- Tạo charter mới nếu còn câu hỏi cần điều tra sâu.

Ví dụ, phiên thăm dò phát hiện rằng gửi lại yêu cầu thanh toán sau timeout có thể tạo giao dịch trùng. Nhóm xác minh quy tắc idempotency với chủ sản phẩm và lập trình viên, tạo ca kiểm thử có dữ liệu và kết quả mong đợi rõ ràng, sau đó cân nhắc tự động hóa ca này trong bộ hồi quy tích hợp. Phiên thăm dò tiếp theo có thể khảo sát thêm các trạng thái như giao dịch đang xử lý, bị hủy hoặc phản hồi đến muộn.

Việc chuyển đổi cần có chọn lọc. Tự động hóa mọi thao tác khám phá có thể tạo ra bộ kiểm thử mong manh và tốn chi phí bảo trì. Chỉ nên chuẩn hóa những tình huống có quy tắc đủ rõ, có giá trị kiểm tra lặp lại và có cách xác định kết quả đáng tin cậy.

## 9. Phối hợp với kiểm thử hồi quy và tự động hóa

Kiểm thử dựa trên đặc tả sẵn thường phù hợp với hồi quy vì cùng một điều kiện có thể được chạy lại sau thay đổi. Tuy nhiên, tự động hóa là lựa chọn triển khai, không phải bản chất của kiểm thử đặc tả sẵn. Một ca đặc tả có thể chạy thủ công; một hoạt động thăm dò có thể dùng công cụ tự động để tạo tải, sinh dữ liệu hoặc quan sát log.

Một cách tổ chức hợp lý là:

- Dùng kiểm tra tự động nhanh để phát hiện lỗi cơ bản sau khi tích hợp hoặc triển khai bản dựng.
- Chạy các ca hồi quy đã ổn định cho luồng nghiệp vụ quan trọng.
- Dùng kiểm thử thủ công và thăm dò để điều tra vùng mới thay đổi, hành vi bất thường và các tổ hợp khó tự động hóa.
- Khi tìm được tình huống quan trọng, chuyển nó thành ca hồi quy phù hợp và quyết định có tự động hóa hay không.
- Định kỳ rà soát ca tự động thất bại không ổn định, kết quả dương tính giả và ca không còn phản ánh yêu cầu hiện tại.

Không nên đánh giá hiệu quả chỉ bằng tỷ lệ tự động hóa hoặc số lượng ca chạy. Cần xem xét khả năng phát hiện lỗi quan trọng, độ tin cậy của kết quả, thời gian phản hồi, chi phí bảo trì và phần rủi ro vẫn chưa được khảo sát.

## 10. Đo lường mức độ bao phủ và hiệu quả

Hai cách tiếp cận tạo ra các loại bằng chứng khác nhau, vì vậy nhóm nên kết hợp nhiều góc nhìn khi đánh giá kết quả.

Với kiểm thử dựa trên đặc tả sẵn, có thể theo dõi:

- Tỷ lệ yêu cầu hoặc tiêu chí chấp nhận quan trọng đã có ca kiểm thử.
- Kết quả đạt, không đạt, bị chặn và chưa thực hiện theo mức ưu tiên.
- Tỷ lệ ca hồi quy được chạy trong phạm vi đã thống nhất.
- Số lỗi được phát hiện và thời gian từ khi phát hiện đến khi xử lý.

Với kiểm thử thăm dò, có thể theo dõi:

- Các charter và khu vực rủi ro đã được khảo sát.
- Số phát hiện có thể tái hiện và mức độ ảnh hưởng của chúng.
- Những câu hỏi hoặc giả thuyết đã được giải đáp và còn bỏ ngỏ.
- Số phát hiện được chuyển thành yêu cầu rõ hơn, ca kiểm thử hoặc hành động giảm rủi ro.
- Phần rủi ro chưa thể khảo sát do giới hạn thời gian, dữ liệu hoặc môi trường.

Các số liệu này cần được diễn giải theo bối cảnh. Một phiên thăm dò không phát hiện lỗi không chứng minh khu vực đó không có lỗi. Số lượng phát hiện cao cũng không tự động có nghĩa người kiểm thử làm tốt hơn; kết quả có thể phụ thuộc vào độ trưởng thành của sản phẩm, thời gian và phạm vi. Mục đích của số liệu là giúp nhóm hiểu độ bao phủ, chất lượng bằng chứng và quyết định tiếp theo, không tạo động lực chạy theo số lượng.

## 11. Ví dụ kết hợp: kiểm thử luồng đặt hàng và thanh toán

Giả sử nhóm chuẩn bị xác nhận một luồng đặt hàng mới. Một phần yêu cầu đã rõ: khách hàng có thể thêm sản phẩm, áp dụng mã giảm giá, chọn phương thức thanh toán và nhận xác nhận đơn hàng. Tuy nhiên, cách hệ thống xử lý timeout, thao tác đồng thời và phản hồi đến muộn từ cổng thanh toán chưa được hiểu đầy đủ.

**Phần đặc tả sẵn** có thể bao gồm:

1. Khách hàng có thể thêm sản phẩm còn hàng vào giỏ.
2. Mã giảm giá hợp lệ được áp dụng theo quy tắc đã công bố.
3. Tổng tiền hiển thị bằng tổng tiền được gửi sang cổng thanh toán.
4. Giao dịch thành công làm đơn hàng chuyển sang trạng thái đã thanh toán.
5. Giao dịch thất bại không làm đơn hàng được đánh dấu đã thanh toán.

Mỗi ca có dữ liệu và kết quả mong đợi cụ thể. Các ca ổn định có thể được chạy trong hồi quy.

**Phần thăm dò** có thể điều tra:

- Người dùng nhấn nút thanh toán liên tục hoặc mở cùng giỏ hàng ở hai cửa sổ.
- Kết nối bị ngắt sau khi cổng thanh toán nhận yêu cầu nhưng trước khi trình duyệt nhận phản hồi.
- Người dùng tải lại trang khi trạng thái giao dịch đang chờ.
- Phản hồi từ cổng thanh toán đến muộn hoặc đến theo thứ tự khác dự kiến.
- Hàng trong kho thay đổi giữa thời điểm thêm vào giỏ và thời điểm thanh toán.
- Mã giảm giá hết hạn trong lúc phiên mua hàng vẫn đang mở.

Nếu thăm dò phát hiện đơn hàng ở trạng thái chờ nhưng giao dịch đã thành công, nhóm ghi lại mã giao dịch, thời điểm, log và bước tái hiện. Sau khi xác nhận quy tắc đúng, nhóm tạo ca kiểm thử cho tình huống phản hồi đến muộn và bổ sung kiểm tra hồi quy. Nếu nguyên nhân chưa rõ, nhóm mở thêm phiên thăm dò tập trung vào đồng bộ trạng thái và cơ chế thử lại.

Trước khi kết luận, nhóm đối chiếu các yêu cầu bắt buộc với kết quả đặc tả, xem xét phát hiện và giới hạn từ thăm dò, xác định rủi ro còn lại và ghi rõ phần chưa kiểm tra. Như vậy, kết quả thể hiện cả mức độ đáp ứng yêu cầu đã biết lẫn hiểu biết mới thu được trong quá trình kiểm thử.

## 12. Những sai lầm thường gặp khi kết hợp

- **Xem thăm dò là kiểm thử tùy hứng:** Không có mục tiêu, phạm vi hoặc ghi chép khiến kết quả khó đánh giá và chia sẻ.
- **Xem đặc tả là danh sách bất biến:** Không điều chỉnh ca kiểm thử khi yêu cầu hoặc hiểu biết sản phẩm thay đổi sẽ làm bộ kiểm thử nhanh chóng lỗi thời.
- **Chỉ thăm dò sau khi hoàn thành mọi ca:** Có thể bỏ lỡ cơ hội dùng phát hiện sớm để điều chỉnh phạm vi và ưu tiên.
- **Không phân biệt phát hiện với giả thuyết:** Một hành vi đáng ngờ cần được xác minh trước khi kết luận là lỗi.
- **Ghi nhận quá ít bằng chứng:** Không có phiên bản, dữ liệu, bước tái hiện hoặc kết quả mong đợi khiến nhóm khó sửa và kiểm tra lại.
- **Tự động hóa mọi thứ tìm thấy:** Một thao tác thăm dò không nhất thiết có giá trị trở thành ca hồi quy lâu dài.
- **Đánh đồng số lượng ca đạt với độ bao phủ:** Ca đạt chỉ chứng minh hành vi trong điều kiện đã kiểm tra.
- **Không cập nhật tài liệu sau khám phá:** Hiểu biết mới không được đưa vào yêu cầu, rủi ro hoặc bộ kiểm thử sẽ dễ bị mất sau khi phiên kết thúc.
- **Không xem xét giới hạn:** Báo cáo cần nói rõ khu vực chưa được khảo sát, môi trường không đại diện hoặc dữ liệu còn thiếu.

Kết hợp đặc tả sẵn với khám phá giúp chiến lược kiểm thử cân bằng giữa tính nhất quán và khả năng thích ứng. Đặc tả cung cấp nền tảng để xác nhận các yêu cầu đã biết; thăm dò mở rộng hiểu biết và phát hiện những tình huống chưa được dự đoán. Khi phát hiện được ghi nhận, xác minh và chuyển thành tài sản kiểm thử phù hợp, nhóm vừa cải thiện bằng chứng hiện tại vừa nâng cao khả năng kiểm tra các thay đổi trong tương lai.
