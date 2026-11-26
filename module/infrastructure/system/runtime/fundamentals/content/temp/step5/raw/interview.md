Theo bạn, runtime của một chương trình bao gồm những gì, và ranh giới của nó với mã nguồn, bản dựng và hệ điều hành nằm ở đâu?
Bạn sẽ mô tả vòng đời của một chương trình từ thao tác khởi chạy đến khi kết thúc như thế nào?
Hệ điều hành, bộ xử lý và các thư viện hệ thống phối hợp ra sao để một chương trình thực thi?
Vì sao cùng một bản chương trình có thể chạy ổn định trên môi trường này nhưng gặp lỗi trên môi trường khác?
Bạn phân biệt thời điểm xây dựng, thời điểm nạp chương trình và thời điểm thực thi như thế nào?
Các mô hình thực thi trực tiếp mã máy, qua máy ảo phần mềm và qua bộ thông dịch khác nhau ra sao về yêu cầu runtime?
Trong những trường hợp nào việc biên dịch tại thời điểm chạy đem lại lợi ích hoặc phát sinh chi phí?
Bộ phận nạp chương trình cần thực hiện những việc gì trước khi ứng dụng bắt đầu xử lý công việc?
Thư viện dùng chung và liên kết động ảnh hưởng thế nào đến quá trình khởi động và vận hành chương trình?
Bạn sẽ điều tra thế nào nếu chương trình chỉ báo thiếu thư viện sau khi chuyển sang môi trường triển khai?
Một tiến trình sở hữu những loại tài nguyên nào, và nó khác một luồng thực thi ở những điểm gì?
Khi nào nên tách các thành phần phần mềm thành nhiều tiến trình, và cách tổ chức đó tạo ra những chi phí nào?
Bộ lập lịch CPU của hệ điều hành ảnh hưởng thế nào đến thời gian phản hồi của một chương trình?
Chuyển ngữ cảnh xảy ra trong những tình huống nào và tác động gì đến hiệu năng?
Bạn phân biệt xử lý đồng thời và xử lý song song như thế nào qua một ví dụ phần mềm thực tế?
Những yếu tố nào giúp bạn lựa chọn giữa đa luồng, đa tiến trình và vòng lặp sự kiện cho một khối lượng công việc?
Vì sao một chương trình có thể phải chờ I/O kéo dài trong khi CPU vẫn còn nhiều thời gian rảnh?
Khi một luồng bị chặn, hệ quả đối với các công việc khác phụ thuộc thế nào vào mô hình thực thi?
Tranh chấp dữ liệu có thể xảy ra như thế nào khi nhiều tác vụ cùng thay đổi trạng thái dùng chung?
Bạn sẽ đánh giá và lựa chọn cơ chế đồng bộ nào khi nhiều tác vụ cùng truy cập một tài nguyên?
Những điều kiện nào có thể dẫn đến deadlock, và bạn sẽ nhận diện nó trong chương trình đang chạy ra sao?
Livelock và starvation biểu hiện như thế nào, và chúng khác deadlock ở điểm nào?
Khi hàng đợi công việc liên tục tăng, bạn sẽ tìm nguyên nhân và quyết định cách xử lý như thế nào?
Bạn kiểm soát áp lực ngược ra sao khi tốc độ tạo công việc vượt quá khả năng xử lý của chương trình?
Không gian địa chỉ của một tiến trình thường gồm những vùng nào và mỗi vùng phục vụ mục đích gì?
Bộ nhớ stack và heap khác nhau thế nào về vòng đời dữ liệu, cách sử dụng và những lỗi có thể xảy ra?
Bộ nhớ ảo giúp tiến trình hoạt động như thế nào, và một page fault có thể ảnh hưởng gì đến thời gian thực thi?
Vì sao lượng bộ nhớ mà tiến trình sử dụng tăng dần chưa đủ để kết luận có rò rỉ bộ nhớ?
Bạn sẽ phân biệt rò rỉ bộ nhớ, bộ nhớ dành cho cache và phân mảnh bộ nhớ bằng những dấu hiệu nào?
Quản lý bộ nhớ thủ công, quản lý theo vùng và thu hồi tự động có những đánh đổi nào trong quá trình thực thi?
Trong chương trình sử dụng bộ thu gom rác, các đợt thu gom có thể ảnh hưởng đến độ trễ như thế nào?
Bạn sẽ chẩn đoán sự cố thiếu bộ nhớ ra sao khi chỉ có biểu đồ RAM và nhật ký hệ thống?
Một chương trình có thể cạn kiệt những tài nguyên nào ngoài CPU và RAM, và dấu hiệu nhận biết là gì?
Vòng đời của tệp, socket và các handle cần được quản lý thế nào để tránh cạn tài nguyên?
Lời gọi hệ thống hoạt động như thế nào qua ranh giới giữa mã ứng dụng và nhân hệ điều hành?
Bộ đệm trong thao tác đọc ghi ảnh hưởng ra sao đến thông lượng, độ trễ và độ bền dữ liệu?
Thao tác đọc hoặc ghi chỉ hoàn thành một phần có thể xảy ra khi nào, và chương trình cần ứng xử ra sao?
Khi kết nối mạng gián đoạn giữa một thao tác, runtime và phần mềm cần phối hợp xử lý những tình huống nào?
Bạn sẽ thiết kế timeout và retry thế nào để không làm tình trạng quá tải nghiêm trọng hơn khi có lỗi?
Thứ tự khởi tạo tài nguyên và các thành phần phụ thuộc có thể ảnh hưởng ra sao đến khả năng khởi động thành công?
Bạn dựa vào những dấu hiệu nào để xác định một tiến trình đã chạy nhưng dịch vụ vẫn chưa sẵn sàng phục vụ?
Khi chương trình nhận yêu cầu dừng, một quy trình kết thúc an toàn cần bảo đảm những điều gì?
Những hậu quả nào có thể xảy ra khi tiến trình bị kết thúc đột ngột trong lúc đang ghi dữ liệu?
Lỗi ứng dụng, tín hiệu từ hệ điều hành và lỗi phần cứng khác nhau thế nào về cách phát hiện và xử lý khi đang chạy?
Bạn sẽ điều tra một chương trình tự thoát chỉ vài giây sau khi khởi động bằng cách nào?
Trong những trường hợp nào nên tự động khởi động lại tiến trình và khi nào cần giữ nguyên trạng thái để phân tích?
Cấu hình được cung cấp lúc chạy khác thông tin đã đóng gói trong bản dựng ở những điểm nào?
Bạn sẽ xác định giá trị cấu hình thực tế thế nào khi nhiều nguồn cấu hình cùng tác động lên một tiến trình?
Việc thay đổi biến môi trường, quyền truy cập, múi giờ hoặc locale có thể làm hành vi phần mềm thay đổi ra sao?
Những rủi ro nào xuất hiện khi thông tin bí mật được đưa qua cấu hình hoặc ghi vào nhật ký trong lúc chạy?
Quyền hệ điều hành và nguyên tắc đặc quyền tối thiểu giúp giảm tác động của lỗi runtime như thế nào?
Tiến trình riêng, container và máy ảo hệ thống cung cấp những mức cách ly tài nguyên và sự cố khác nhau ra sao?
Trong môi trường container, những phần nào của runtime vẫn phụ thuộc vào nhân hệ điều hành của máy chủ?
Bạn sẽ kiểm tra khả năng tương thích khi thay đổi kiến trúc CPU, hệ điều hành hoặc phiên bản thư viện hệ thống như thế nào?
Vì sao hai môi trường có cùng mã chương trình và cấu hình vẫn có thể tạo ra hành vi khác nhau khi chạy?
Những nguyên nhân nào khiến một lỗi chỉ xuất hiện khi tải cao hoặc sau nhiều ngày chương trình hoạt động?
Khi mức sử dụng CPU luôn cao, bạn cần thu thập những bằng chứng gì trước khi quyết định tối ưu?
Bạn sẽ phân biệt chương trình chậm do CPU, I/O, chờ khóa đồng bộ hay áp lực bộ nhớ bằng cách nào?
Profiling theo mẫu và ghi vết chi tiết có lợi ích và chi phí gì khi áp dụng cho một tiến trình đang phục vụ người dùng?
Độ trễ trung bình, các phân vị độ trễ cao và thông lượng phản ánh những khía cạnh nào khác nhau của runtime?
Vì sao hiệu năng ở lần chạy đầu tiên và sau một thời gian hoạt động có thể khác nhau đáng kể?
Bạn sẽ dùng những dữ liệu quan sát nào để tìm điểm nghẽn trong một chương trình gồm nhiều bước xử lý?
Log, metric và trace bổ sung cho nhau như thế nào khi điều tra lỗi phát sinh trong lúc chương trình chạy?
Bạn sẽ liên kết dấu vết của nhiều tác vụ chạy đồng thời bằng cách nào mà vẫn bảo vệ dữ liệu nhạy cảm?
Bạn sẽ tiếp cận một lỗi runtime chỉ xuất hiện trong môi trường sản xuất và chưa thể tái hiện ở nơi khác ra sao?
Core dump, stack trace và thông tin trạng thái các luồng giúp bạn hiểu nguyên nhân sự cố như thế nào?
Bạn sẽ đo lường tác động của việc bật giám sát hoặc debug lên hiệu năng của chương trình đang chạy ra sao?
Độ chính xác đồng hồ và chênh lệch thời gian giữa các máy có thể làm sai lệch timeout hoặc lịch tác vụ như thế nào?
Khi một dịch vụ phụ thuộc không sẵn sàng, chương trình nên ứng xử thế nào ở thời điểm khởi động và trong lúc vận hành?
Các giới hạn CPU, bộ nhớ và số lượng handle do môi trường chạy áp đặt có thể làm phần mềm thất bại theo những cách nào?
Bạn sẽ thiết kế thử nghiệm gì để phát hiện tranh chấp tài nguyên mà các kiểm thử tuần tự khó nhận ra?
Với phần mềm có yêu cầu thời gian thực, bạn cần đánh giá thêm những gì ngoài thời gian thực thi trung bình?
Bạn sẽ kiểm tra khả năng phục hồi của chương trình sau mất điện hoặc bị buộc kết thúc giữa một thao tác như thế nào?
Những thông tin nào cần ghi lại để tái hiện điều kiện runtime gây lỗi trên một máy khác?
Bạn sẽ quyết định thay đổi cấu hình lúc chạy hay triển khai lại chương trình dựa trên những tiêu chí và rủi ro nào?
Khi nâng cấp hệ điều hành, thư viện nền hoặc môi trường thực thi, bạn sẽ xác minh những hành vi nào để tránh sự cố?
Nếu cùng đầu vào nhưng hai lần chạy cho kết quả khác nhau, bạn sẽ điều tra những nguồn bất định nào trong runtime?
Bạn sẽ tổ chức việc dọn dẹp tài nguyên như thế nào khi một bước xử lý thất bại giữa chừng?
