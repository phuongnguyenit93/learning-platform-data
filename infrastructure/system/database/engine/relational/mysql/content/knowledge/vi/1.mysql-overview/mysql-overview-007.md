# Vai trò và ranh giới công việc của lập trình viên, DBA và người vận hành

MySQL thường nằm giữa ứng dụng và hạ tầng: ứng dụng gửi câu lệnh SQL, máy chủ cơ sở dữ liệu xử lý dữ liệu, còn hệ thống bên dưới cung cấp CPU, bộ nhớ, lưu trữ và mạng. Vì vậy, một thay đổi nhỏ ở ứng dụng có thể ảnh hưởng đến tải của MySQL; một thay đổi cấu hình máy chủ có thể ảnh hưởng đến độ trễ của ứng dụng; và một thao tác bảo trì cơ sở dữ liệu có thể tác động đến cả hai.

Để hệ thống an toàn và dễ vận hành, nhóm cần phân biệt ba vai trò: **lập trình viên (developer)** chịu trách nhiệm về cách ứng dụng sử dụng dữ liệu; **quản trị viên cơ sở dữ liệu (DBA)** chịu trách nhiệm về thiết kế, tính toàn vẹn, hiệu năng và độ tin cậy của hệ quản trị cơ sở dữ liệu; **người vận hành (operations)** chịu trách nhiệm giữ cho nền tảng chạy ổn định, có thể quan sát, khôi phục và mở rộng. Ranh giới cụ thể tùy quy mô tổ chức, nhưng trách nhiệm cuối cùng của mỗi công việc phải được xác định rõ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt trách nhiệm của developer, DBA và operations trong vòng đời một ứng dụng dùng MySQL.
- Xác định ai chuẩn bị, ai rà soát, ai thực thi và ai xác nhận một thay đổi dữ liệu hoặc hạ tầng.
- Phối hợp xử lý thay đổi schema, truy vấn chậm, sự cố kết nối và khôi phục dữ liệu.
- Thiết kế quy trình bàn giao có quyền hạn tối thiểu, dấu vết kiểm toán và bước xác minh sau thay đổi.

## 1. Lập trình viên: bảo đảm ứng dụng sử dụng dữ liệu đúng

Developer hiểu yêu cầu nghiệp vụ và luồng xử lý của ứng dụng. Họ quyết định dữ liệu nào cần được đọc hoặc ghi, thời điểm nào một thao tác phải nằm trong transaction, và ứng dụng phản ứng ra sao khi truy vấn lỗi hoặc dữ liệu không tồn tại.

Các trách nhiệm thường thuộc developer:

- Chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu và đề xuất bảng, cột, kiểu dữ liệu, quan hệ, khóa chính, khóa ngoại và ràng buộc phù hợp.
- Viết SQL và mã truy cập dữ liệu; dùng tham số hóa để tránh SQL injection; xử lý lỗi, timeout và deadlock theo cách có thể thử lại an toàn.
- Xác định ranh giới transaction để một nhóm thao tác nghiệp vụ được thực hiện nhất quán; tránh giữ transaction mở lâu hoặc khóa hàng không cần thiết.
- Đề xuất index dựa trên các truy vấn thực tế, kiểm tra kế hoạch thực thi bằng `EXPLAIN`, đo lường trước và sau khi thay đổi.
- Quản lý migration cùng phiên bản ứng dụng, bảo đảm thay đổi schema tương thích với quá trình triển khai và dữ liệu đang tồn tại.
- Theo dõi chỉ số ở tầng ứng dụng như thời gian truy vấn, số kết nối, tỷ lệ lỗi và lượng truy vấn phát sinh theo từng chức năng.

Developer **chịu trách nhiệm về ý nghĩa nghiệp vụ và hành vi truy cập dữ liệu của ứng dụng**. Chẳng hạn, nếu một giao dịch đặt hàng phải cập nhật đơn hàng và trừ tồn kho cùng nhau, developer phải xác định các thao tác cần nằm trong cùng transaction và cách xử lý khi một thao tác thất bại.

Developer không nên tự ý dùng tài khoản quản trị để thay đổi dữ liệu hoặc cấu trúc trên production. Họ cũng không nên coi việc thêm index là giải pháp mặc định: index có chi phí lưu trữ và làm tăng công việc ghi, nên cần có bằng chứng từ truy vấn và dữ liệu thực tế. Với thay đổi có ảnh hưởng lớn, developer chuẩn bị migration và thông tin tác động để DBA cùng operations rà soát.

## 2. DBA: bảo đảm cơ sở dữ liệu đúng, nhanh và có thể phục hồi

DBA (Database Administrator) hiểu sâu về MySQL, cấu trúc lưu trữ, bộ tối ưu truy vấn, cơ chế khóa, transaction, replication, sao lưu và phục hồi. DBA nhìn hệ thống ở góc độ dữ liệu và máy chủ cơ sở dữ liệu, đồng thời kết nối yêu cầu của ứng dụng với giới hạn kỹ thuật của MySQL.

Các trách nhiệm thường thuộc DBA:

- Thiết lập tiêu chuẩn thiết kế schema: kiểu dữ liệu, quy ước đặt tên, khóa, ràng buộc, chuẩn hóa và chiến lược lưu trữ.
- Rà soát thiết kế bảng, migration, index và truy vấn có rủi ro về khóa, dung lượng, thời gian chạy hoặc ảnh hưởng đến replication.
- Phân tích kế hoạch thực thi, thống kê, cardinality, index và truy vấn để tìm nguyên nhân hiệu năng; hướng dẫn nhóm ứng dụng tối ưu dựa trên bằng chứng.
- Quản lý cấu hình ở tầng MySQL, kết nối, giới hạn tài nguyên, cơ chế đồng bộ và các tính năng sẵn sàng cao trong phạm vi được giao.
- Thiết kế chính sách sao lưu, phục hồi và lưu giữ dữ liệu; xác định mục tiêu RPO/RTO cùng chủ hệ thống và kiểm tra khả năng khôi phục định kỳ.
- Thiết kế quyền truy cập database theo nguyên tắc đặc quyền tối thiểu; rà soát tài khoản, quyền và hoạt động nhạy cảm.
- Lập kế hoạch nâng cấp phiên bản MySQL, thay đổi cấu hình quan trọng và xử lý sự cố liên quan đến tính toàn vẹn hoặc hiệu năng của database.

DBA **chịu trách nhiệm về sức khỏe và các quy tắc vận hành của MySQL**. Ví dụ, khi một truy vấn bắt đầu quét toàn bộ bảng lớn, DBA có thể đọc kế hoạch thực thi, kiểm tra index và thống kê, đánh giá tác động của phương án sửa rồi phối hợp với developer để điều chỉnh câu SQL hoặc mô hình dữ liệu.

DBA không tự quyết định ý nghĩa nghiệp vụ của dữ liệu thay cho nhóm sản phẩm và developer. DBA có thể chỉ ra rằng một cột cần ràng buộc `NOT NULL` hoặc một thao tác cần transaction, nhưng chủ nghiệp vụ phải xác nhận quy tắc đó có đúng với sản phẩm hay không. DBA cũng không mặc nhiên chịu trách nhiệm cho toàn bộ hệ điều hành, mạng, nền tảng triển khai hoặc mã nguồn ứng dụng; các phần này cần phối hợp với operations và developer.

## 3. Người vận hành: bảo đảm nền tảng sẵn sàng và có thể khôi phục

Người vận hành (operations, system administrator hoặc SRE tùy tổ chức) quản lý môi trường nơi MySQL và ứng dụng chạy. Họ tập trung vào tính sẵn sàng của dịch vụ, tài nguyên máy chủ, mạng, lưu trữ, triển khai, giám sát và quy trình phản ứng sự cố.

Các trách nhiệm thường thuộc operations:

- Cấp phát và quản lý máy chủ, máy ảo, container, ổ đĩa, mạng, DNS, chứng thư và các thành phần nền tảng cần thiết.
- Quản lý cấu hình môi trường, secrets, quyền truy cập hệ thống, bản vá hệ điều hành và quy trình triển khai có kiểm soát.
- Theo dõi CPU, bộ nhớ, dung lượng đĩa, I/O, mạng, tiến trình, tình trạng máy chủ và cảnh báo về tính sẵn sàng.
- Vận hành lịch sao lưu, kho lưu trữ bản sao, chính sách lưu giữ và quy trình khôi phục ở tầng hạ tầng theo thiết kế đã thống nhất với DBA.
- Chuẩn bị năng lực dự phòng, kế hoạch khôi phục thảm họa, quy trình trực ca và runbook cho các tình huống phổ biến.
- Thu thập log và số liệu hệ thống, điều phối xử lý sự cố, ghi nhận mốc thời gian và xác nhận nền tảng đã ổn định sau khắc phục.

Operations **chịu trách nhiệm về nền tảng và quy trình vận hành**. Ví dụ, khi máy chủ MySQL hết dung lượng đĩa, operations kiểm tra filesystem, volume, log và cảnh báo hạ tầng; DBA đánh giá file dữ liệu, binlog, lịch sử sao lưu và tác động đến MySQL; developer kiểm tra xem ứng dụng có tạo dữ liệu bất thường hoặc truy vấn gây tăng trưởng đột biến hay không.

Người vận hành không nên tự suy đoán ý nghĩa dữ liệu rồi chạy các câu `UPDATE` hoặc `DELETE` để sửa lỗi nghiệp vụ. Họ cũng không nên thực thi migration SQL chưa được rà soát. Nếu cần thao tác dữ liệu khẩn cấp, phải có người chịu trách nhiệm về nội dung SQL, phạm vi bản ghi, phê duyệt và xác minh kết quả.

## 4. Ranh giới trách nhiệm trong các công việc thường gặp

Ba vai trò có vùng giao nhau. Bảng dưới đây mô tả cách phân công tham khảo; tổ chức có thể gộp vai trò hoặc thay đổi người thực hiện, nhưng vẫn cần chỉ định một người/nhóm chịu trách nhiệm cuối cùng cho mỗi quyết định.

| Công việc | Developer | DBA | Operations |
|---|---|---|---|
| Quy tắc nghiệp vụ và ý nghĩa dữ liệu | Chịu trách nhiệm chính | Tư vấn tính toàn vẹn | Được thông báo khi ảnh hưởng vận hành |
| Thiết kế schema và migration | Đề xuất, viết và duy trì cùng mã ứng dụng | Rà soát chuẩn dữ liệu, khóa, index và tác động MySQL | Chuẩn bị pipeline, cửa sổ thay đổi và điều kiện nền tảng |
| SQL trong ứng dụng | Chịu trách nhiệm chính về tính đúng và cách gọi | Tư vấn, phân tích hiệu năng | Theo dõi ảnh hưởng tài nguyên ở môi trường chạy |
| Index và kế hoạch thực thi | Cung cấp truy vấn và ngữ cảnh tải | Dẫn dắt đánh giá ở tầng database | Cung cấp số liệu CPU, I/O và tài nguyên |
| Quyền truy cập database | Nêu nhu cầu tối thiểu của ứng dụng | Thiết kế và cấp quyền database theo chính sách | Quản lý secrets và quyền truy cập hạ tầng |
| Sao lưu và phục hồi | Xác nhận tính đúng của dữ liệu sau phục hồi | Thiết kế chiến lược và kiểm tra tính nhất quán | Vận hành lưu trữ, lịch chạy và quy trình khôi phục hạ tầng |
| Giám sát và cảnh báo | Chỉ số nghiệp vụ, lỗi và độ trễ ứng dụng | Chỉ số truy vấn, kết nối, khóa và replication | Máy chủ, mạng, lưu trữ và điều phối cảnh báo |
| Nâng cấp MySQL | Kiểm tra tương thích ứng dụng và driver | Đánh giá thay đổi database và kế hoạch nâng cấp | Chuẩn bị máy chủ, triển khai và phương án khôi phục nền tảng |
| Sự cố production | Khoanh vùng lỗi ứng dụng và hành vi truy cập | Khoanh vùng lỗi dữ liệu và MySQL | Điều phối sự cố và kiểm tra nền tảng |

Không nên hiểu bảng này là quy định cứng rằng chỉ một vai trò được chạm vào một công việc. Ví dụ, developer có thể chạy migration qua pipeline tự động; DBA có thể viết truy vấn kiểm tra; operations có thể khởi động quy trình phục hồi. Điều quan trọng là quyền thực thi, quyền phê duyệt và trách nhiệm xác nhận phải được phân định trước.

## 5. Ví dụ phối hợp: thêm cột và index cho chức năng mới

Giả sử ứng dụng cần lưu trạng thái giao hàng và thường xuyên tìm các đơn hàng theo `status` cùng `created_at`. Nhóm dự kiến thêm cột `delivery_status` và một index phục vụ truy vấn.

1. **Developer làm rõ yêu cầu.** Xác định các trạng thái hợp lệ, giá trị mặc định, quy tắc cập nhật và các phiên bản ứng dụng cùng tồn tại trong lúc triển khai. Developer viết migration, câu truy vấn sử dụng cột mới và kiểm thử với dữ liệu mẫu.
2. **DBA đánh giá tác động MySQL.** Rà soát kiểu dữ liệu, khả năng `NULL`, index, thứ tự cột trong index theo điều kiện truy vấn, kích thước bảng, khóa và thời gian thực hiện DDL. DBA kiểm tra phiên bản MySQL và khả năng hỗ trợ thuật toán thay đổi schema của thao tác cụ thể; không giả định mọi DDL đều chạy online hoặc có thể rollback bằng transaction.
3. **Operations chuẩn bị môi trường.** Kiểm tra dung lượng trống, tải hiện tại, trạng thái sao lưu, cảnh báo, quyền triển khai và cửa sổ thay đổi. Nếu chạy trên nền tảng có replica hoặc nhiều node, nhóm xác nhận quy trình triển khai phù hợp với kiến trúc đang dùng.
4. **Nhóm triển khai có kiểm soát.** Chạy migration qua quy trình đã phê duyệt, theo dõi thời gian, khóa, lỗi và độ trễ replica. Tách việc thay đổi schema khỏi việc bật hoàn toàn chức năng nếu cần hỗ trợ triển khai theo nhiều bước.
5. **Cùng xác minh.** Developer kiểm tra luồng nghiệp vụ và dữ liệu; DBA kiểm tra schema, index và kế hoạch thực thi; operations xác nhận tài nguyên và dịch vụ ổn định. Nếu có vấn đề, nhóm dùng phương án đã chuẩn bị: tắt tính năng, sửa tiến về phía trước hoặc khôi phục theo kế hoạch phù hợp.

Với MySQL, cần đặc biệt thận trọng khi lập kế hoạch rollback. Nhiều thao tác DDL có thể gây implicit commit; tính năng atomic DDL cũng phụ thuộc phiên bản và loại thao tác. Vì vậy, không thể mặc định bọc lệnh `ALTER TABLE` trong transaction rồi `ROLLBACK` là hoàn tác được thay đổi. Phương án an toàn phải dựa trên thao tác cụ thể, phiên bản MySQL, kích thước dữ liệu và khả năng khôi phục đã được thử nghiệm.

## 6. Ví dụ phối hợp: truy vấn đột ngột chậm

Một trang danh sách đơn hàng vốn phản hồi nhanh nhưng nay mất vài giây. Không nên kết luận ngay rằng database cần thêm CPU hoặc developer viết SQL sai. Nhóm cần lần lượt ghép bằng chứng từ ba tầng:

- **Developer** xác định thời điểm bắt đầu, phiên bản ứng dụng vừa triển khai, tham số truy vấn, tần suất gọi, kích thước trang và liệu một chức năng có phát sinh nhiều truy vấn hơn trước hay không.
- **DBA** kiểm tra truy vấn thực tế, `EXPLAIN`, index, thống kê, số hàng ước lượng, lock wait, transaction kéo dài và tình trạng kết nối. Khi cân nhắc `EXPLAIN ANALYZE`, cần nhớ lệnh này thực thi câu truy vấn; phải đánh giá tải và chọn môi trường phù hợp trước khi chạy trên production.
- **Operations** kiểm tra CPU, bộ nhớ, I/O, dung lượng đĩa, mạng, giới hạn container/VM và các sự kiện hạ tầng trùng thời điểm.

Sau khi xác định nguyên nhân, nhóm thống nhất một thay đổi có thể đo lường: sửa cách phân trang, giảm số lần gọi, thêm hoặc điều chỉnh index, xử lý transaction bị giữ lâu, hoặc khắc phục thiếu tài nguyên. Người đề xuất thay đổi cung cấp tiêu chí thành công; người thực thi theo đúng quyền; cả ba vai trò cùng xác minh tác động ở tầng mình phụ trách.

## 7. Nguyên tắc phối hợp và kiểm soát quyền

Một quy trình phân công tốt thường tuân theo các nguyên tắc sau:

**Một quyết định có một chủ sở hữu rõ ràng.** Với quy tắc nghiệp vụ, chủ sở hữu thường là nhóm sản phẩm hoặc developer được giao. Với tiêu chuẩn MySQL, DBA dẫn dắt. Với nền tảng và lịch trực, operations dẫn dắt. Các nhóm còn lại tham gia rà soát khi quyết định ảnh hưởng đến phần việc của họ.

**Tách quyền chạy ứng dụng và quyền thay đổi schema.** Tài khoản runtime của ứng dụng chỉ nên có các quyền dữ liệu thật sự cần, chẳng hạn một tập hợp `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE` giới hạn theo schema và bảng. Tài khoản migration là danh tính riêng, được sử dụng trong quy trình triển khai có kiểm soát. Không cấp quyền quản trị rộng cho ứng dụng chỉ để tránh lỗi quyền.

**Thay đổi production phải có dấu vết.** Migration, câu lệnh vận hành hoặc thao tác sửa dữ liệu cần ghi rõ mục đích, phạm vi, người chịu trách nhiệm, thời điểm, kết quả và cách xác minh. Với thao tác có rủi ro cao, cần có phê duyệt và người thứ hai rà soát.

**Sao lưu chỉ có giá trị khi phục hồi được.** DBA xác định dữ liệu cần bảo vệ, tính nhất quán và mục tiêu RPO/RTO; operations bảo đảm bản sao được tạo, lưu giữ và truy cập được; developer hoặc chủ nghiệp vụ xác nhận ứng dụng hoạt động đúng sau khi khôi phục. Cần diễn tập phục hồi định kỳ thay vì chỉ kiểm tra trạng thái tác vụ sao lưu.

**Sự cố là trách nhiệm phối hợp.** Người phát hiện sự cố không cần tự xử lý mọi tầng. Họ cần cung cấp thời điểm, dấu hiệu, thay đổi gần nhất và mức độ ảnh hưởng; đầu mối sự cố điều phối các nhóm, giữ một dòng thông tin thống nhất và ghi lại quyết định.

## 8. Những cách phân công dễ gây sự cố

- Developer dùng tài khoản có quyền cao để sửa trực tiếp dữ liệu production, khiến thay đổi không được kiểm tra hoặc không có dấu vết.
- DBA tự thay đổi quy tắc dữ liệu mà chưa xác nhận yêu cầu nghiệp vụ, dẫn đến schema đúng về kỹ thuật nhưng sai về sản phẩm.
- Operations chạy một file SQL chỉ vì có yêu cầu khẩn cấp mà chưa biết phạm vi, tác động khóa hoặc cách xác minh.
- Nhóm cho rằng sao lưu thành công đồng nghĩa có thể khôi phục, nhưng chưa từng thử phục hồi trên môi trường độc lập.
- Mỗi nhóm chỉ theo dõi chỉ số của mình, khiến không ai nối được lỗi ứng dụng với truy vấn MySQL và tình trạng hạ tầng.
- Không có người chịu trách nhiệm cuối cùng, dẫn đến thay đổi bị bỏ sót hoặc nhiều nhóm cùng giả định nhóm khác đã kiểm tra.

## 9. Checklist bàn giao một thay đổi MySQL

Trước khi thay đổi schema, truy vấn, quyền hoặc cấu hình trên môi trường quan trọng, nhóm nên trả lời được các câu hỏi sau:

- Mục tiêu nghiệp vụ và hệ thống của thay đổi là gì? Ai chịu trách nhiệm cuối cùng?
- Những bảng, truy vấn, dịch vụ và phiên bản ứng dụng nào bị ảnh hưởng?
- Migration hoặc câu lệnh đã được rà soát trên dữ liệu có quy mô gần thực tế chưa?
- Tác động đến khóa, thời gian chạy, dung lượng, replication và tải hệ thống đã được đánh giá chưa?
- Quyền thực thi có giới hạn đúng phạm vi không? Có lưu lại người thực thi và kết quả không?
- Bản sao lưu gần nhất có đáp ứng yêu cầu không, và phương án phục hồi đã được kiểm chứng chưa?
- Có tiêu chí theo dõi, điều kiện dừng, phương án xử lý khi thất bại và bước xác minh sau thay đổi không?
- Developer, DBA và operations đã biết rõ phần việc cũng như đầu mối điều phối chưa?

Khi các câu hỏi này được trả lời rõ ràng, nhóm có thể phối hợp mà không bỏ sót trách nhiệm. Developer bảo đảm dữ liệu được ứng dụng sử dụng đúng; DBA bảo đảm MySQL lưu trữ và phục vụ dữ liệu đáng tin cậy; operations bảo đảm nền tảng luôn có thể quan sát, duy trì và khôi phục. Ba vai trò cùng chịu trách nhiệm về chất lượng dịch vụ cơ sở dữ liệu, với quyền hạn và quyết định được phân công minh bạch.
