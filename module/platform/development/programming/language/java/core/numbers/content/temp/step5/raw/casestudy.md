Một hệ thống bán vé dùng int để cộng số lượng lượt xem trong năm; khi chiến dịch quảng bá đạt hàng tỷ lượt, tổng số trở thành giá trị âm và báo cáo quản trị hiển thị lưu lượng không hợp lý.
Một cổng thương mại tính tổng tiền bằng cách nhân hai biến int rồi mới gán vào long; đơn hàng có số lượng lớn ghi nhận tổng âm dù cột cơ sở dữ liệu cho phép số nguyên 64-bit.
Một dịch vụ kế toán cộng số tiền kiểu long từ nhiều giao dịch có giá trị rất lớn; sau đợt nhập dữ liệu lịch sử, tổng số dư vượt phạm vi biểu diễn nhưng ứng dụng vẫn trả một số hợp lệ về mặt kiểu dữ liệu.
Một hệ thống xử lý ảnh dùng Math.abs để lấy độ lớn của độ lệch kiểu int; với một giá trị đầu vào ở biên âm, kết quả vẫn âm và thuật toán tính khoảng cách gặp lỗi.
Một bộ phân tích thống kê tính số đối của giá trị long nhỏ nhất để chuẩn hóa tín hiệu; cùng biểu thức cho kết quả bất thường dù không có exception số học nào được báo.
Một dịch vụ đo thời gian dùng phép trừ trên hai bộ đếm int tích lũy qua nhiều ngày; khi bộ đếm đi qua giới hạn số nguyên, thời lượng một tác vụ được ghi thành giá trị âm.
Một nền tảng xuất hóa đơn chia tổng số tiền nguyên cho số lượng đơn trước khi áp dụng chính sách làm tròn; phần lẻ bị mất khiến tổng giá trị phân bổ khác số ban đầu.
Một hệ thống chấm công dùng toán tử chia số nguyên để đổi phút sang giờ; các ca làm chưa đủ một giờ bị ghi nhận bằng không dù hợp đồng yêu cầu tính tỷ lệ thời gian.
Một ứng dụng lập lịch dùng toán tử phần dư với chỉ số có thể âm để xác định ngày trong chu kỳ; dữ liệu điều chỉnh từ các kỳ trước làm chương trình truy cập phần tử tại vị trí âm.
Một dịch vụ đánh số gói hàng dùng phép chia trên giá trị nguyên âm để phân trang nhật ký lùi thời gian; các mốc trang gần số không rơi vào nhóm khác với dự kiến của đội vận hành.
Một bộ xử lý thanh toán tính phép chia nguyên với mẫu số lấy từ dữ liệu cấu hình; khi cấu hình bị đặt bằng không, tác vụ kết thúc bằng ArithmeticException thay vì thông báo nghiệp vụ.
Một nhóm phân tích mã sự kiện dùng số nguyên có số không ở đầu trong literal Java; một mã được hiểu theo cơ số khác nên kết quả so khớp không giống mã hiển thị trong tài liệu.
Một ứng dụng dùng byte để lưu số lượng hàng trả trong ngày; khi một cửa hàng vượt ngưỡng 127 món, dữ liệu được ép kiểu và giá trị trong báo cáo biến thành số âm.
Một hệ thống cảm biến nhận giá trị không dấu 16-bit qua thiết bị, nhưng ứng dụng chuyển trực tiếp sang short; khi bit cao được bật, nhiệt độ hoặc mã trạng thái bị đọc thành số âm.
Một dịch vụ tích hợp tệp nhị phân lấy một byte có bit cao bằng một rồi mở rộng thành int; bước so khớp mã thiết bị thất bại vì giá trị âm được tạo ra không giống giá trị không dấu từ tài liệu giao thức.
Một ứng dụng lưu số lần tải tệp trong char vì mỗi ký tự được xem là 16-bit; kết quả vượt phạm vi và báo cáo hiển thị mã ký tự thay vì con số nghiệp vụ được mong đợi.
Một nền tảng phân tích sử dụng phép dịch phải có dấu để giải mã trường bit của một số âm; những bit cao được lặp lại làm mã trạng thái sau giải mã không phù hợp với cấu trúc gói tin.
Một dịch vụ phân quyền sinh bit mask bằng phép dịch trên int; khi số quyền cần biểu diễn tăng vượt một từ máy, nhiều quyền trùng vị trí bit và hệ thống cấp nhầm quyền.
Một công cụ xây mã định danh từ hai phần 32-bit bằng phép dịch và phép hoặc; khi phần cao có bit dấu, giá trị long tạo ra không giống mã 64-bit mà hệ thống đối tác xuất ra.
Một dịch vụ xử lý mã cơ số 16 nhận các giá trị không dấu 64-bit từ thiết bị; một số mã hợp lệ vượt giới hạn Long có dấu và thao tác chuyển chuỗi sang long thất bại.
Một nền tảng đặt hàng dùng Integer.parseInt cho số lượng do đối tác cung cấp; chuỗi có dấu cộng, khoảng trắng hoặc chữ số vượt phạm vi được xử lý không thống nhất giữa các đường nhập.
Một ứng dụng phân tích dữ liệu đọc số lượng từ JSON dưới dạng long nhưng chuyển sang int khi tính chỉ số; với bộ dữ liệu lớn, kết quả ép hẹp bị thay đổi và chương trình trỏ sai bản ghi.
Một cổng thanh toán dùng phép chuyển từ double sang int để tính số điểm thưởng; khi số đầu vào lớn hơn phạm vi int, giá trị sau chuyển kiểu không phản ánh lượng điểm thực tế.
Một dịch vụ định vị chuyển giá trị tọa độ kiểu double sang float để giảm dung lượng truyền; sai số đủ lớn làm điểm giao hàng lệch khỏi vị trí trên bản đồ ở mức phóng đại cao.
Một bộ tính lương trộn int, long và double trong một biểu thức rồi tạo BigDecimal từ kết quả đã tính; báo cáo cuối có sai lệch nhỏ nhưng lặp lại trên hàng triệu bản ghi.
Một hệ thống định giá nhập số nguyên 64-bit rất lớn vào biến double để tính toán; khi chuyển ngược về long, hai mã giao dịch gần nhau có thể không còn phân biệt được.
Một ứng dụng thương mại nhận mã đơn hàng dạng số nguyên lớn hơn hai mũ 53 từ dịch vụ Java và trả về giao diện JavaScript dưới dạng JSON number; hai mã khác nhau có thể bị làm tròn thành cùng một số.
Một dịch vụ đo tốc độ tính trung bình bằng phép chia hai số nguyên rồi gán kết quả vào double; dữ liệu chỉ thay đổi ở phần thập phân vẫn hiển thị cùng một kết quả.
Một ứng dụng mua sắm dùng biến float cho giá có hai chữ số thập phân; sau khi cộng nhiều sản phẩm, tổng hiển thị sai ở chữ số lẻ dù từng giá riêng lẻ đều đúng.
Một hệ thống hoàn tiền kiểm tra trực tiếp kết quả của phép cộng 0,1 và 0,2 với 0,3 bằng toán tử bằng; các giao dịch hợp lệ bị đánh dấu không cân đối.
Một bộ tính điểm dùng so sánh double với một ngưỡng tuyệt đối rất nhỏ để đánh giá bằng nhau; khi giá trị tăng từ vài phần triệu lên hàng tỷ, kết quả so sánh trở nên không phù hợp với sai số tương đối.
Một mô hình dự báo dùng vòng lặp cộng dồn các bước float rất nhỏ; cùng khối lượng dữ liệu cho tổng khác nhau khi thay thứ tự xử lý hoặc chia việc sang nhiều thread.
Một hệ thống tính độ chênh lệch nhiệt độ bằng cách trừ hai giá trị double gần bằng nhau nhưng rất lớn; chữ số có ý nghĩa trong kết quả bị mất khiến cảnh báo vượt ngưỡng hoạt động sai.
Một dịch vụ thống kê tính phương sai bằng hiệu của hai tổng bình phương số thực; trên dữ liệu có giá trị gần nhau, phương sai đôi khi âm dù đại lượng được mong đợi không âm.
Một bộ mô phỏng dùng Math.pow với số mũ lớn; kết quả double trở thành Infinity và tiếp tục đi qua các phép tính mà không có ArithmeticException.
Một hệ thống cảnh báo đo tỷ lệ bằng phép chia hai số double mà mẫu số có thể bằng không; kết quả Infinity hoặc NaN đi vào báo cáo mà không bị xử lý như lỗi dữ liệu.
Một ứng dụng đánh giá rủi ro sắp xếp danh sách số thực có chứa NaN từ phép tính không xác định; thứ tự trả về khác quy tắc so sánh bằng các toán tử mà nhóm nghiệp vụ đang sử dụng.
Một nền tảng phân tích dùng điều kiện lớn hơn và nhỏ hơn để phân loại điểm double; các bản ghi có NaN không đi vào nhánh nào dù giao diện vẫn đòi hỏi một loại kết quả.
Một hệ thống đo tín hiệu nhận cả dương không và âm không dưới dạng double; phép so sánh bằng cho thấy chúng tương đương nhưng các thao tác chia và sắp xếp có thể biểu hiện khác nhau.
Một thư viện cache dùng Double làm khóa và nhận số thực có NaN từ nhiều phép tính; nhóm phát triển giả định hợp đồng equals giống toán tử so sánh nguyên thủy nên kết quả tra cứu gây ngạc nhiên.
Một dịch vụ nhập số thập phân rất nhỏ vào float; các số gần ngưỡng biểu diễn bị làm tròn về không khiến cảnh báo dựa trên mức tối thiểu không kích hoạt.
Một hệ thống phân tích xuất số double sang chuỗi rồi đọc lại bằng hệ thống khác; quy tắc hiển thị số chữ số và dạng ký pháp khoa học làm các báo cáo văn bản khác với dữ liệu kỳ vọng.
Một cổng thanh toán dùng Math.round cho số tiền âm và số tiền dương tại điểm giữa; kết quả hoàn tiền không đối xứng với kết quả thu tiền theo chính sách làm tròn được mô tả.
Một ứng dụng tính thuế lưu hai trường phần trăm dưới dạng double rồi làm tròn từng bước; khi tính lại ở cuối kỳ, tổng thuế khác so với cách tính trực tiếp trên tổng doanh số.
Một dịch vụ đo đạc áp dụng phép tính với float cho sai số dung sai của thiết bị; khi dùng cùng phép tính trên double, kết quả vượt hoặc không vượt ngưỡng kiểm định ở các giá trị biên.
Một nhóm xây công cụ so sánh kết quả mô phỏng yêu cầu các phép toán số thực cho cùng kết quả bất kể phần cứng và thứ tự cộng; bản triển khai song song gây khác biệt ở chữ số cuối của báo cáo.
Một ứng dụng bán lẻ tạo BigDecimal trực tiếp từ literal double của giá 0,1; dữ liệu lưu xuất hiện nhiều chữ số thập phân không có trong giá niêm yết.
Một cổng hóa đơn tạo BigDecimal từ chuỗi do khách hàng gửi; chuỗi tiền có dấu phẩy thập phân theo locale khác làm thao tác phân tích giá trị thất bại.
Một hệ thống kế toán lưu BigDecimal cho các khoản thu nhưng dùng equals để kiểm tra hai số có cùng giá trị; số 10,0 và 10,00 được xem là khác nhau trong bước đối chiếu.
Một ứng dụng quản lý sản phẩm đặt BigDecimal làm khóa HashMap; hai biểu diễn giá có scale khác nhau không tra cứu được cùng mục dù bộ phận nghiệp vụ coi chúng bằng nhau.
Một dịch vụ báo giá dùng compareTo trên BigDecimal để xác định giá trùng nhưng HashSet ở module khác dựa vào equals; kết quả loại trùng khác nhau khi dữ liệu có nhiều mức scale.
Một nền tảng thanh toán thực hiện BigDecimal.divide trên một khoản tiền chia thành ba phần; với kết quả thập phân vô hạn, tác vụ phát sinh ArithmeticException ở một số đơn hàng.
Một hệ thống phân bổ ngân sách chia tổng giá trị BigDecimal theo tỷ lệ nhưng không thống nhất MathContext; kết quả giữa các bước có độ chính xác khác nhau và tổng phân bổ không khớp.
Một công ty bảo hiểm dùng setScale để giảm số chữ số thập phân của khoản phí; những số nằm đúng giữa hai mức làm tròn trở thành trường hợp khiếu nại vì quy tắc đang dùng chưa được xác định.
Một dịch vụ quản lý thuế sử dụng RoundingMode.HALF_EVEN cho nghiệp vụ yêu cầu quy tắc khác; các giao dịch có chữ số cuối đúng điểm giữa cho kết quả không khớp tài liệu kế toán.
Một ứng dụng hoàn tiền xử lý giá trị BigDecimal âm bằng cách làm tròn rồi lấy giá trị tuyệt đối; cách tính tạo ra khác biệt so với quy tắc làm tròn tiền hoàn của đối tác.
Một hệ thống ngân hàng dùng BigDecimal để tính lãi qua nhiều kỳ nhưng đặt precision thấp cho các phép tính trung gian; tổng lãi cuối kỳ chênh với kết quả kiểm toán độc lập.
Một dịch vụ nhập giá từ file CSV giữ scale nguyên gốc trong BigDecimal; khi sinh JSON, cùng một khoản tiền đôi khi hiển thị số lượng chữ số lẻ khác nhau giữa các nhà cung cấp.
Một ứng dụng tạo tệp đối soát gọi stripTrailingZeros trên BigDecimal rồi chuyển thành chuỗi; số tiền nguyên lớn xuất hiện ở dạng ký pháp khoa học mà đối tác không chấp nhận.
Một cổng bảo hiểm so sánh BigDecimal có giá trị bằng không với BigDecimal.ZERO bằng equals; các kết quả tính toán có scale khác nhau làm kiểm tra số dư bằng không không ổn định.
Một ứng dụng lưu giá trị BigDecimal vào cơ sở dữ liệu với cột decimal có precision và scale cố định; khoản phí tính được có nhiều chữ số hơn nên bị làm tròn hoặc bị từ chối khi ghi.
Một nhóm tích hợp Java và hệ thống kế toán khác ngôn ngữ chuyển BigDecimal thành double trước khi gửi JSON; tổng tiền nhận ở đối tác khác bản ghi trong hệ thống Java.
Một dịch vụ sinh mã xác thực dùng BigInteger để biểu diễn số nguyên dương rất lớn; khi chuyển thành mảng byte, một số mã có thêm byte dấu khiến hệ thống bên ngoài từ chối.
Một nền tảng chữ ký số chuyển dãy byte không dấu thành BigInteger theo constructor thông thường; những giá trị có bit cao được diễn giải thành số âm và phép toán xác thực không thành công.
Một dịch vụ phân tích dữ liệu dùng BigInteger để lưu bộ đếm không giới hạn; các vòng lặp liên tục tạo đối tượng mới làm chi phí cấp phát tăng rõ khi lượng sự kiện tăng.
Một công cụ đánh giá mật mã gọi phép lũy thừa BigInteger với số mũ lấy từ dữ liệu nhập không giới hạn; một yêu cầu bất thường tiêu thụ nhiều CPU và bộ nhớ hơn dự kiến.
Một ứng dụng thống kê so sánh BigInteger với long bằng cách chuyển về kiểu nguyên thủy; giá trị rất lớn bị cắt mất bit và thứ tự các kết quả trở nên sai.
Một hệ thống xử lý ID nhận số nguyên rất dài dưới dạng chuỗi; bộ kiểm tra chỉ xét số ký tự chứ không kiểm tra dấu và cơ số nên một nhóm giá trị gây lỗi khi tạo BigInteger.
Một dịch vụ quản lý phiên dùng Integer làm bộ đếm cho phép null khi chưa có dữ liệu; thao tác tự động unboxing trong phép cộng phát sinh NullPointerException chỉ với tài khoản mới.
Một ứng dụng tối ưu bộ nhớ so sánh hai đối tượng Integer bằng toán tử ==; kiểm thử với giá trị nhỏ thường đạt nhưng dữ liệu sản xuất có giá trị lớn lại cho kết quả không như mong đợi.
Một hệ thống lưu kết quả kiểm tra trong Map<Integer, String>; một thành phần gửi khóa là Long có cùng giá trị số khiến thao tác tìm kiếm không nhận ra mục đã lưu.
Một dịch vụ thu thập chỉ số có nhiều overload nhận long, Object và Number; sau khi bổ sung overload mới, lời gọi với đối số Integer từ plugin được xử lý ở phương thức khác với nhóm phát triển dự kiến.
Một bộ tính điểm dùng biểu thức điều kiện có một nhánh int và nhánh kia double; kết quả được nâng kiểu ngoài dự đoán nên bước kiểm tra equality với một số nguyên không còn phù hợp.
Một công cụ tổng hợp nhận Collection<Number> gồm Integer, Long và BigDecimal; bộ xử lý giả định tất cả đều chuyển sang double mà không mất độ chính xác và báo cáo tổng có sai số.
Một ứng dụng kế toán lưu phần trăm dưới dạng BigDecimal rồi dùng intValue để phân loại; phần lẻ bị loại bỏ khiến hai mức thuế khác nhau đi vào cùng một nhóm.
Một dịch vụ ngân hàng dùng longValue trên BigInteger đọc từ đối tác; giá trị vượt phạm vi long bị đổi thành mã khác mà không báo ngoại lệ khi chuyển.
Một hệ thống thanh toán dùng BigDecimal.longValue cho số tiền sau khi nhân tỷ lệ; phần thập phân bị cắt nhưng API chỉ kiểm tra xem phép chuyển đổi có hoàn thành hay không.
Một nền tảng thương mại xuất cùng một số lượng dưới dạng int ở service cũ và BigDecimal ở service mới; hệ thống downstream ghép dữ liệu bằng so sánh kiểu chặt nên nhận diện hai bản ghi là khác nhau.
Một nhóm QA kiểm thử tràn số chỉ với giá trị lớn nhất của int mà không kiểm tra nhân trước khi nâng kiểu, ép hẹp hay các giá trị âm tại giới hạn; lỗi vẫn xuất hiện ở production.
Một bộ kiểm thử giao dịch so sánh số thực bằng sai số cố định duy nhất; các ca dữ liệu rất nhỏ, rất lớn, NaN và Infinity chưa được kiểm chứng trước khi phát hành.
Một hệ thống tài chính vừa đổi từ double sang BigDecimal cho số tiền; bộ kiểm thử chỉ đối chiếu tổng cuối, chưa tái hiện vấn đề scale, rounding, phép chia không hữu hạn và định dạng khi tích hợp.
