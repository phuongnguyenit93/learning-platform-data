Một ứng dụng chạy bình thường trên máy phát triển nhưng khi chép tệp thực thi sang máy chủ mới thì hệ điều hành báo không thể thực thi tệp; hai máy có kiến trúc bộ xử lý và định dạng tệp thực thi khác nhau.
Một chương trình đã đóng gói thành tệp thực thi chạy trên máy chủ đời mới nhưng dừng ngay với lỗi lệnh máy không hợp lệ khi triển khai lên máy đời cũ dù cùng họ kiến trúc CPU.
Một dịch vụ khởi động thành công ở môi trường thử nghiệm nhưng thất bại trước khi in log ở môi trường sản xuất; bản phát hành mới phụ thuộc vào một thư viện dùng chung không tồn tại trên máy đích.
Hai máy có cùng thư viện dùng chung nhưng phiên bản giao diện nhị phân khác nhau; chương trình chỉ lỗi lúc gọi một chức năng cụ thể sau vài phút chạy.
Một tệp thực thi tải đúng thư viện khi chạy trực tiếp nhưng tải nhầm bản thư viện đặt trong thư mục của công cụ khác khi khởi chạy từ một quy trình tự động.
Ứng dụng đọc được tệp cấu hình khi mở từ thư mục cài đặt nhưng báo thiếu cấu hình khi khởi chạy bởi trình quản lý dịch vụ với thư mục làm việc khác.
Nhân viên đặt biến môi trường trong cửa sổ terminal rồi mở ứng dụng qua giao diện đồ họa; ứng dụng vẫn báo thiếu giá trị cấu hình dù lệnh kiểm tra trong terminal hiển thị đúng.
Một chương trình gọi tiến trình con để xử lý ảnh; tiến trình cha hiển thị thành công nhưng một số ảnh không được tạo vì tiến trình con kết thúc với mã lỗi riêng.
Sau khi tiến trình cha bị dừng đột ngột, các tiến trình con vẫn chạy và tiếp tục giữ CPU, bộ nhớ và cổng mạng; người vận hành khó xác định ai còn chịu trách nhiệm thu hồi chúng.
Một công cụ dòng lệnh nhận được vài nghìn đường dẫn tệp nhưng không thể khởi chạy khi người dùng truyền tất cả đường dẫn trong cùng một lần gọi; chạy theo từng nhóm nhỏ lại thành công.
Ứng dụng nền chạy bình thường khi mở từ terminal nhưng dừng ngay sau khi người vận hành đóng terminal dù họ không gửi yêu cầu thoát ứng dụng.
Một dịch vụ báo trạng thái tiến trình là đang chạy ngay sau khi khởi động, trong khi yêu cầu đầu tiên vẫn thất bại vì các tài nguyên cần thiết chưa sẵn sàng.
Một tính năng ít dùng chỉ gây lỗi khi được truy cập lần đầu; chương trình khởi động ổn định hàng giờ trước đó vì tài nguyên thực thi liên quan được nạp muộn.
Sau khi thay tệp thực thi bằng phiên bản mới, người vận hành thấy tiến trình đang chạy vẫn có hành vi của phiên bản cũ, còn tiến trình khởi động sau mới có hành vi mới.
Cùng một dịch vụ chạy được dưới tài khoản quản trị nhưng không khởi động dưới tài khoản dịch vụ bị giới hạn quyền; log chỉ cho thấy lỗi truy cập vào tài nguyên hệ thống.
Một ứng dụng đóng ngay khi được khởi chạy bởi lịch tác vụ và không ghi thông báo nào; đầu ra chuẩn, lỗi chuẩn và môi trường tương tác của nó khác lúc chạy thủ công.
Một tiến trình cha chờ tiến trình con hoàn thành, nhưng cả hệ thống đứng im khi tiến trình con ghi lượng lớn dữ liệu vào đầu ra được chuyển qua một đường ống mà bên cha chưa đọc.
Khi nhận tín hiệu yêu cầu dừng, dịch vụ vẫn giữ các kết nối hiện tại quá lâu và bị hệ thống triển khai buộc kết thúc trước khi hoàn tất các tác vụ đang xử lý.
Một tiến trình bị yêu cầu thoát nhưng vẫn hiện trong danh sách tiến trình với trạng thái chờ I/O; các lần gửi tín hiệu dừng tiếp theo không khiến nó rời trạng thái đó.
Một chương trình chạy được từ ổ cục bộ nhưng báo không đủ quyền thực thi khi được đặt trên một vùng lưu trữ đã gắn kết có chính sách hạn chế chạy tệp.
Bộ nhớ sử dụng của một dịch vụ tăng đều qua nhiều ngày dù lượng yêu cầu mỗi giờ gần như không đổi; sau mỗi lần khởi động lại, bộ nhớ trở về mức thấp rồi tăng tiếp.
Sau đợt tải cao, lượng bộ nhớ cư trú của tiến trình không giảm về mức ban đầu dù các yêu cầu lớn đã hoàn tất; nhóm vận hành chưa rõ bộ nhớ còn được dùng hay chỉ đang được giữ để tái sử dụng.
Một chương trình xử lý dữ liệu theo cấu trúc lồng nhau chạy tốt với đầu vào nhỏ nhưng dừng vì tràn ngăn xếp khi gặp một đầu vào có độ sâu lớn bất thường.
Ứng dụng 32 bit không thể cấp phát thêm bộ nhớ trong khi máy 64 bit còn rất nhiều RAM trống; lỗi chỉ xuất hiện khi dữ liệu vượt một kích thước nhất định.
Một tiến trình bên trong container bị hệ điều hành kết thúc do vượt giới hạn bộ nhớ trong khi dashboard của máy chủ vật lý vẫn hiển thị nhiều RAM còn trống.
Khi số người dùng đồng thời tăng, hệ thống đọc ghi trang nhớ liên tục và phản hồi chậm hàng chục lần dù CPU thực hiện tính toán nghiệp vụ không cao.
Một chương trình ánh xạ tệp dữ liệu rất lớn vào không gian địa chỉ nên công cụ giám sát hiển thị bộ nhớ ảo khổng lồ, nhưng bộ nhớ cư trú thực tế ban đầu rất nhỏ.
Ứng dụng đang đọc một vùng tệp được ánh xạ vào bộ nhớ thì một tiến trình khác cắt ngắn tệp; lần truy cập kế tiếp gây lỗi truy cập bộ nhớ bất ngờ.
Sau nhiều chu kỳ cấp phát và giải phóng các khối kích thước khác nhau, tiến trình không cấp phát được một khối lớn dù tổng bộ nhớ còn trống trên giấy tờ vẫn đáng kể.
Chương trình truy vấn lượng dữ liệu lớn thường nhanh nhưng đôi lúc tạm ngừng rõ rệt khi bộ phận quản lý bộ nhớ tự động thu hồi đối tượng; người dùng nhìn thấy các đợt tăng độ trễ ngắn.
Một thiết bị nhúng có bộ nhớ hạn chế chạy ổn trong vài giờ nhưng sau nhiều lần bật tắt tính năng thì không tạo được vùng đệm mới; khởi động lại thiết bị tạm thời làm hết lỗi.
Ứng dụng xử lý ảnh thỉnh thoảng bị hỏng dữ liệu sau khi một vùng nhớ được tái sử dụng; lỗi xuất hiện nhiều hơn khi tăng số công việc song song và thay đổi lịch chạy.
Khi chuyển dịch vụ sang máy có nhiều nút bộ nhớ NUMA, số lõi CPU tăng nhưng một số tác vụ truy cập dữ liệu dùng chung lại chậm hơn trên máy ít lõi.
Một công việc xử lý tập dữ liệu lớn có độ trễ thất thường giữa lần chạy đầu tiên và các lần chạy sau trên cùng máy; lượng lỗi trang nhớ và hoạt động bộ đệm của hệ điều hành cũng khác nhau.
Hệ thống chạy nhiều tiến trình song song có tổng nhu cầu bộ nhớ vượt RAM; có thời điểm một dịch vụ quan trọng bị chậm nặng dù bản thân nó không tăng tải.
Hai luồng cùng cập nhật số lượng đơn hàng đã xử lý; sau một ngày, số tổng kết nhỏ hơn số sự kiện thực tế dù từng lần tăng đều có vẻ đúng trong log.
Hai tác vụ chạy đồng thời có lúc đứng chờ nhau vô thời hạn khi mỗi tác vụ đang giữ một khóa và đợi khóa còn lại để hoàn tất.
Một tác vụ nền giữ khóa chung trong thời gian dài khiến nhiều yêu cầu ngắn phải xếp hàng; CPU thấp nhưng thời gian phản hồi của toàn dịch vụ tăng mạnh.
Dịch vụ tăng số luồng làm việc từ vài chục lên vài nghìn để xử lý thêm yêu cầu, nhưng thông lượng lại giảm và số lần chuyển ngữ cảnh tăng vọt.
Trong hệ thống có nhóm luồng cố định, thời gian xử lý từng tác vụ không thay đổi nhiều nhưng hàng chờ lớn dần và yêu cầu mới hết hạn trước khi được thực thi.
Một công việc ưu tiên cao phải đợi tài nguyên mà một luồng ưu tiên thấp đang nắm giữ, trong khi các luồng ưu tiên trung bình liên tục được chạy; thời gian chờ trở nên khó dự đoán.
Ứng dụng vẫn nhận kết nối nhưng các tác vụ hẹn giờ và phản hồi bất đồng bộ bị trì hoãn mỗi khi có một công việc tính toán lớn chạy trên cùng vòng lặp xử lý sự kiện.
Một dịch vụ có hàng đợi tác vụ nền báo đã tắt thành công, nhưng sau mỗi lần triển khai lại có một số tác vụ đã nhận mà chưa kịp hoàn thành.
Một luồng liên tục kiểm tra trạng thái công việc và tiêu thụ gần hết một lõi CPU mà tiến độ xử lý không tăng; các luồng khác chỉ chạy chậm đi.
Trên máy một lõi, chương trình gần như không bộc lộ lỗi nhưng trên máy nhiều lõi đôi khi đọc giá trị trạng thái cũ dù luồng khác vừa cập nhật.
Một dịch vụ dùng luồng làm việc được tái sử dụng giữa các yêu cầu; thông tin ngữ cảnh của yêu cầu trước thỉnh thoảng xuất hiện trong log của yêu cầu sau.
Khi nhiều tác vụ cùng ghi vào một tệp nhật ký, các dòng bị xen kẽ hoặc thiếu đoạn, còn chạy từng tác vụ riêng lẻ thì nhật ký hoàn chỉnh.
Một ứng dụng chỉ bị treo khi tải cao đúng lúc đang thay đổi kích thước nhóm luồng xử lý; trong các lần chạy ít tải, thao tác này không gây triệu chứng.
Trên máy có nhiều lõi, một tiến trình thường chỉ dùng tối đa một lõi mặc dù hàng đợi công việc tăng; chỉ số CPU tổng thể không cao nên cảnh báo tải hệ thống không kích hoạt.
Một ứng dụng mở kết nối tới tệp, socket và thiết bị theo mỗi yêu cầu; sau nhiều giờ xuất hiện lỗi không thể mở thêm tài nguyên dù CPU và RAM vẫn còn.
Một phân vùng còn nhiều dung lượng tính theo byte nhưng chương trình không tạo được tệp nhật ký mới sau khi đã sinh hàng triệu tệp nhỏ.
Tiến trình ghi log liên tục nhưng sau khi mất điện, vài dòng cuối không có trên đĩa dù người vận hành đã nhìn thấy thông báo ghi thành công trước đó.
Một dịch vụ ghi được dữ liệu vào tệp lúc chạy thủ công nhưng thất bại khi được triển khai trên hệ thống có thư mục cài đặt chỉ cho phép đọc.
Một chương trình yêu cầu đọc một khối dữ liệu từ luồng mạng hoặc đường ống nhưng mỗi lần chỉ nhận được một phần; vấn đề chỉ xảy ra với gói tin lớn hoặc kết nối chậm.
Hai tiến trình sử dụng chung một mô tả tệp, rồi đọc và di chuyển vị trí hiện tại xen kẽ; kết quả xử lý đôi lúc bỏ qua hoặc đọc lại các đoạn dữ liệu.
Một ứng dụng trên Windows không thể đổi tên tệp log đang được tiến trình khác mở, trong khi quy trình tương tự trên hệ thống Unix có hành vi khác.
Tệp cấu hình có tên chứa ký tự Unicode được mở bình thường trên một máy nhưng bị báo không tồn tại sau khi chuyển sang máy có cấu hình mã hóa hoặc hệ thống tệp khác.
Ứng dụng xử lý tệp rất lớn bằng các lần ghi nhỏ liên tục và có thông lượng thấp; công cụ đo cho thấy số lần gọi I/O hệ thống tăng mạnh theo kích thước đầu vào.
Một dịch vụ thao tác với thiết bị ngoại vi chờ đọc vô hạn sau khi thiết bị mất kết nối; thao tác dừng tiến trình từ giao diện quản trị cũng không trả về ngay.
Sau khi dịch vụ khởi động lại nhanh, nó không thể lắng nghe cổng cũ vì hệ điều hành vẫn báo địa chỉ đang được sử dụng dù giao diện quản trị không còn thấy tiến trình cũ.
Một máy chủ phản hồi tốt khi truy cập qua địa chỉ loopback nhưng không thể kết nối từ máy khác trong cùng mạng; tiến trình vẫn báo đã mở cổng lắng nghe thành công.
Một máy chủ nhận đủ số byte cần thiết trên kết nối TCP nhưng xử lý sai ranh giới thông điệp khi các lần chạy trả về số đoạn dữ liệu khác nhau.
Kết nối TCP đã được thiết lập thành công nhưng yêu cầu nghiệp vụ vẫn đứng chờ tới khi hết thời gian; số kết nối mở cao và hàng đợi xử lý phía máy chủ tăng.
Sau khi đổi địa chỉ IP của một dịch vụ nội bộ, một số tiến trình tiếp tục kết nối đến địa chỉ cũ trong khi các tiến trình khởi động sau sử dụng địa chỉ mới.
Một chương trình tạo hàng chục nghìn kết nối ngắn tới cùng máy chủ; sau một đợt cao điểm, các kết nối mới bắt đầu thất bại dù máy đích vẫn có khả năng phục vụ.
Ứng dụng dùng socket không chặn gặp các lần đọc chưa có dữ liệu ở thời điểm kiểm tra; dưới tải cao, nó đôi khi báo lỗi kết nối dù phiên làm việc vẫn còn tồn tại.
Một máy chủ truyền dữ liệu nhanh hơn tốc độ thiết bị của khách hàng có thể nhận; bộ đệm chờ gửi tăng liên tục kéo theo lượng bộ nhớ tiến trình tăng bất thường.
Trên một số máy có đồng hồ hệ thống sai lệch, ứng dụng không bắt tay được kết nối mã hóa với máy chủ dù cùng chứng chỉ vẫn hợp lệ trên máy khác.
Khi kết nối mạng mất ngay sau thao tác gửi, ứng dụng không biết phía nhận đã xử lý thông điệp hay chưa; người dùng gửi lại và đôi khi thấy tác vụ được thực hiện hai lần.
Một chương trình tự động thử lại ngay sau mỗi lỗi kết nối; khi dịch vụ phụ thuộc bị chậm, lượng kết nối mới tăng đột biến và cả hai bên gần như ngừng đáp ứng.
Trong đợt cập nhật phiên bản, một số kết nối tồn tại lâu bị cắt giữa chừng và khách hàng nhận dữ liệu dở dang dù các yêu cầu mới đã chuyển sang tiến trình mới.
Một dịch vụ vẫn giữ cổng mạng sau khi tiến trình chủ được dừng; kiểm tra cho thấy tiến trình con còn giữ một mô tả socket được kế thừa từ lúc khởi tạo.
Một quy trình đặt thời hạn xử lý theo đồng hồ hệ thống bị hết hạn bất thường sau khi hệ điều hành đồng bộ lại thời gian, dù lượng công việc thực tế không thay đổi.
Một tác vụ được lên lịch theo giờ địa phương chạy hai lần trong đêm chuyển giờ mùa hè ở một địa điểm, trong khi cùng lịch biểu ở nơi khác chỉ chạy một lần.
Cùng một đầu vào chứa dấu thập phân và ngày tháng, một chương trình cho kết quả khác nhau khi chạy trên các máy có thiết lập vùng và ngôn ngữ hệ thống khác nhau.
Một cụm dịch vụ ghi thời điểm sự kiện từ nhiều máy; đồng hồ giữa các máy lệch nhau khiến nhật ký có thứ tự khó hiểu và việc đối chiếu thời hạn phiên truy cập bị sai.
Một tiến trình tạo nhiều công việc con ngay sau khi khởi động; các công việc sinh giá trị ngẫu nhiên lặp lại bất thường dù mong đợi các chuỗi khác nhau.
Một ứng dụng khởi động trong môi trường cô lập có múi giờ mặc định khác máy chủ; dữ liệu báo cáo theo ngày đôi khi bị chuyển sang ngày trước hoặc ngày sau.
Một dịch vụ tạo tệp đầu ra với quyền truy cập khác nhau giữa lúc chạy trực tiếp và qua trình quản lý dịch vụ; các tiến trình dùng chung tệp đôi khi không thể mở dù thư mục cha không đổi.
Một ứng dụng bị từ chối mở tệp hoặc tạo kết nối mạng trong môi trường sandbox dù quyền người dùng trên tệp và mạng có vẻ đã được cấp phù hợp.
Một tiến trình khởi chạy công cụ bên ngoài và vô tình cho công cụ đó thừa hưởng các biến môi trường chứa thông tin nhạy cảm; nhật ký lỗi của công cụ phụ xuất hiện dữ liệu không nên được ghi lại.
Một ứng dụng hoạt động khi chạy trên máy trực tiếp nhưng bị hệ thống cô lập từ chối một số lời gọi hệ thống khi triển khai trong môi trường container với chính sách hạn chế.
Một dịch vụ chạy ổn định suốt nhiều tuần rồi bị thoát bất thường; hệ thống có ghi nhận sự cố nhưng không tìm thấy dữ liệu chẩn đoán hoặc dấu vết ngăn xếp sau sự kiện.
Biểu đồ CPU của một dịch vụ luôn thấp, nhưng nhiều yêu cầu vẫn có độ trễ cao; thông tin giám sát cho thấy đa số thời gian tiến trình đang chờ các hoạt động bên ngoài hoàn tất.
Một dịch vụ chạy trong container chỉ được phân bổ một phần thời gian CPU dù máy chủ vật lý còn rảnh; khi cao điểm, tác vụ hết hạn nhưng dashboard CPU toàn máy không xuất hiện mức tải cao.
Một chương trình cần đặt chỗ cho vùng địa chỉ bộ nhớ rất lớn rồi chỉ sử dụng từng phần nhỏ; máy này báo lỗi ngay khi đặt chỗ, còn máy khác khởi chạy được nhưng gặp lỗi khi thực sự sử dụng vùng nhớ.
Một dịch vụ phát sinh lỗi gián đoạn nhưng log chỉ có thông báo chung; lỗi xuất hiện tại ranh giới giữa tiến trình cha, tiến trình con và hệ điều hành nên khó xác định nơi sự cố xảy ra.
