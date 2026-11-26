Transaction là gì, và bạn sẽ giải thích vai trò của ranh giới giao dịch trong một nghiệp vụ như thế nào?
Bạn sẽ minh họa tính nguyên tử của ACID bằng một nghiệp vụ chuyển tiền giữa hai tài khoản ra sao?
Bạn sẽ xác định các bất biến dữ liệu mà tính nhất quán của transaction cần bảo vệ trong hệ thống đặt hàng như thế nào?
Bạn sẽ giải thích tính cô lập giúp các giao dịch đồng thời tránh ảnh hưởng không mong muốn đến nhau ra sao?
Bạn sẽ phân tích tính bền vững của giao dịch sau COMMIT khi máy chủ bất ngờ mất điện như thế nào?
Bạn sẽ phân biệt bảo đảm ACID của cơ sở dữ liệu với tính đúng đắn của quy tắc nghiệp vụ ở tầng ứng dụng ra sao?
Bạn sẽ mô tả vòng đời transaction từ BEGIN đến COMMIT hoặc ROLLBACK và những trạng thái cần theo dõi như thế nào?
Bạn sẽ chọn phạm vi transaction cho một yêu cầu cần đọc, tính toán và cập nhật nhiều bản ghi dựa trên tiêu chí nào?
Bạn sẽ đánh giá ảnh hưởng của auto-commit đến tính nguyên tử của chuỗi lệnh SQL như thế nào?
Bạn sẽ sử dụng SAVEPOINT khi xử lý nhiều bước có thể khôi phục từng phần trong một transaction ra sao?
Bạn sẽ phân biệt ROLLBACK toàn bộ với ROLLBACK TO SAVEPOINT về trạng thái dữ liệu và khóa như thế nào?
Bạn sẽ quyết định bên nào chịu trách nhiệm COMMIT và ROLLBACK khi nhiều tầng service cùng tham gia một nghiệp vụ ra sao?
Bạn sẽ xử lý ngoại lệ giữa các bước cập nhật để transaction không bị bỏ lại trong trạng thái chưa hoàn tất như thế nào?
Bạn sẽ mô tả vai trò của transaction log hoặc write-ahead log trong việc khôi phục sau sự cố như thế nào?
Bạn sẽ kiểm tra những giả định nào về độ bền khi hệ thống dùng commit bất đồng bộ hoặc cấu hình ghi log khác nhau?
Bạn sẽ phân biệt giao dịch ngắn và dài theo mức giữ tài nguyên, khả năng cạnh tranh và rủi ro vận hành như thế nào?
Bạn sẽ điều chỉnh thiết kế nếu một transaction đang giữ khóa phải chờ phản hồi từ dịch vụ bên ngoài ra sao?
Việc giữ transaction mở khi người dùng vẫn đang nhập liệu có thể gây những tác động nào đến hiệu năng và truy cập đồng thời?
Bạn sẽ thiết kế giới hạn thời gian và cơ chế hủy transaction khi request vượt quá thời gian cho phép ra sao?
Bạn sẽ bảo đảm một connection được trả lại pool trong mọi nhánh xử lý thành công, thất bại hoặc timeout như thế nào?
Bạn sẽ mô tả một lịch thực thi đồng thời của hai transaction theo thứ tự đọc và ghi dữ liệu như thế nào?
Bạn sẽ đánh giá một lịch thực thi có thể tương đương với thứ tự tuần tự các transaction dựa trên những tiêu chí nào?
Bạn sẽ sử dụng đồ thị phụ thuộc giữa các transaction để nhận diện xung đột và chu trình như thế nào?
Bạn sẽ phân biệt serial execution với serializable isolation trong hệ thống phục vụ nhiều yêu cầu đồng thời ra sao?
Bạn sẽ xây dựng một lịch thực thi minh họa dirty read và chỉ ra dữ liệu nào đã được đọc trước khi commit ra sao?
Bạn sẽ mô tả hiện tượng non-repeatable read khi cùng transaction đọc một hàng hai lần ra sao?
Bạn sẽ minh họa phantom read khi hai truy vấn cùng điều kiện lọc trả về tập hàng khác nhau như thế nào?
Bạn sẽ phân biệt lost update với non-repeatable read trong tình huống nhiều người cùng sửa một số dư như thế nào?
Bạn sẽ xây dựng một lịch thực thi thể hiện write skew khi hai giao dịch cùng kiểm tra một điều kiện tổng thể ra sao?
Bạn sẽ giải thích read skew hoặc inconsistent analysis ảnh hưởng đến báo cáo đọc nhiều bản ghi như thế nào?
Bạn sẽ phân biệt những bất thường quan sát được ở mức hàng với vi phạm bất biến liên quan nhiều hàng ra sao?
Bạn sẽ phân tích cách một transaction đọc dữ liệu được commit ở những thời điểm khác nhau và gây kết quả thiếu nhất quán như thế nào?
Bạn sẽ nhận diện trường hợp hai request đều đọc thấy tồn kho còn đủ nhưng cùng lúc trừ số lượng như thế nào?
Bạn sẽ thiết kế cập nhật tồn kho có điều kiện để ngăn số lượng âm mà không cần khóa cả bảng ra sao?
Bạn sẽ sử dụng cột version hoặc điều kiện WHERE để ngăn lost update trong mô hình optimistic concurrency như thế nào?
Bạn sẽ xác định cách xử lý khi cập nhật lạc quan trả về không có hàng nào được thay đổi ra sao?
Bạn sẽ lựa chọn một chiến lược kiểm thử hai phiên đồng thời để tái hiện lost update một cách có kiểm soát như thế nào?
Bạn sẽ tìm những điểm xen kẽ đọc và ghi nào khiến bài kiểm thử concurrency cho kết quả thiếu ổn định?
Bạn sẽ dùng barrier hoặc đồng bộ tiến trình trong kiểm thử để chủ động tạo tình huống tranh chấp như thế nào?
Bạn sẽ ghi nhận thứ tự sự kiện, mã giao dịch và trạng thái dữ liệu để đối chiếu lỗi đồng thời sau kiểm thử ra sao?
Bạn sẽ so sánh ý nghĩa của READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ và SERIALIZABLE ở mức khái niệm như thế nào?
Bạn sẽ giải thích vì sao tên cùng một mức isolation có thể không bảo đảm cùng hành vi giữa các hệ quản trị cơ sở dữ liệu ra sao?
Bạn sẽ chọn mức cô lập cho thao tác cập nhật số dư khi hệ thống không được phép vi phạm bất biến tài chính như thế nào?
Bạn sẽ lựa chọn isolation cho một báo cáo đọc nhiều bảng nhưng chấp nhận độ mới dữ liệu có giới hạn ra sao?
Bạn sẽ phân tích sự đánh đổi giữa mức cô lập cao, thông lượng, độ trễ và xác suất giao dịch phải chạy lại như thế nào?
Bạn sẽ kiểm chứng READ COMMITTED có ngăn được lost update trong một luồng đọc rồi ghi cụ thể hay không bằng cách nào?
Bạn sẽ xác minh mức REPEATABLE READ của hệ quản trị đang dùng xử lý phantom và write skew ra sao?
Bạn sẽ mô tả cơ chế ngăn lịch thực thi không tuần tự hóa được ở mức SERIALIZABLE như thế nào?
Bạn sẽ kiểm tra tác động của SERIALIZABLE đối với thời gian chờ khóa hoặc lỗi cần retry khi tăng số request ra sao?
Bạn sẽ xác định nhu cầu dùng snapshot ổn định cho một truy vấn phân tích kéo dài theo những tiêu chí nào?
Bạn sẽ giải thích sự khác biệt giữa snapshot isolation và serializable isolation bằng một ví dụ write skew như thế nào?
Bạn sẽ chỉ ra những thông tin cần đọc trong tài liệu hệ quản trị trước khi dựa vào cam kết của một isolation level ra sao?
Bạn sẽ chọn cách kiểm chứng hành vi isolation bằng thực nghiệm trên phiên bản cơ sở dữ liệu đang triển khai như thế nào?
Bạn sẽ phân biệt shared lock và exclusive lock theo khả năng đọc hoặc ghi đồng thời như thế nào?
Bạn sẽ mô tả các mức khóa hàng, trang, bảng và tác động của độ hạt khóa đến mức tranh chấp ra sao?
Bạn sẽ giải thích cơ chế lock compatibility quyết định session nào được phép tiếp tục và session nào phải chờ như thế nào?
Bạn sẽ phân biệt khóa được lấy khi đọc, khi cập nhật và khi xác nhận giao dịch trong một hệ quản trị cụ thể ra sao?
Bạn sẽ sử dụng SELECT FOR UPDATE hoặc cơ chế tương đương khi cần đọc trước rồi cập nhật một bản ghi như thế nào?
Bạn sẽ cân nhắc NOWAIT hoặc SKIP LOCKED khi xây dựng hàng đợi tác vụ dựa trên cơ sở dữ liệu ra sao?
Bạn sẽ phân biệt khóa bi quan với khóa lạc quan dựa trên tần suất xung đột và chi phí thử lại như thế nào?
Bạn sẽ phân tích hiện tượng lock escalation có thể làm tăng phạm vi chặn các transaction khác ra sao?
Bạn sẽ mô tả vai trò của gap lock hoặc predicate lock trong việc bảo vệ tập hàng khớp điều kiện ra sao?
Bạn sẽ điều tra vì sao một lệnh UPDATE chỉ sửa ít hàng nhưng vẫn chờ khóa lâu do kế hoạch truy vấn hoặc index ra sao?
Bạn sẽ xác định thứ tự truy cập bảng và bản ghi để giảm tranh chấp và nguy cơ deadlock ra sao?
Bạn sẽ giải thích quy tắc hai pha khóa ảnh hưởng đến khả năng tuần tự hóa và thời điểm giải phóng khóa như thế nào?
Bạn sẽ phân biệt lock wait timeout với deadlock detection dựa trên dấu hiệu và cơ chế xử lý như thế nào?
Bạn sẽ lập sơ đồ wait-for graph của ba transaction để phát hiện chu trình chờ khóa ra sao?
Bạn sẽ phân tích một tình huống hai giao dịch cập nhật các bảng theo thứ tự ngược nhau và dẫn tới deadlock như thế nào?
Bạn sẽ xác định transaction nào bị chọn làm nạn nhân deadlock và trạng thái công việc cần khôi phục ra sao?
Bạn sẽ dùng log, lock monitoring và thông tin session để tìm câu lệnh giữ khóa gây nghẽn như thế nào?
Bạn sẽ thay đổi thứ tự cập nhật, kích thước giao dịch hoặc cấu trúc index để giảm deadlock lặp lại ra sao?
Bạn sẽ phân biệt một transaction bị deadlock với việc chờ lâu do transaction khác chưa commit như thế nào?
Bạn sẽ xử lý giao dịch thất bại vì deadlock bằng cách thử lại toàn bộ đơn vị công việc như thế nào?
Bạn sẽ đặt thời gian chờ khóa và timeout của request theo thứ tự nào để hệ thống trả lỗi có thể kiểm soát?
Bạn sẽ đánh giá khi nào nên chủ động hủy transaction giữ khóa quá lâu và các ảnh hưởng tới dữ liệu ra sao?
Bạn sẽ giải thích MVCC cho phép nhiều phiên đọc các phiên bản dữ liệu khác nhau mà không chặn mọi thao tác ghi như thế nào?
Bạn sẽ mô tả cách phiên bản hàng và timestamp hoặc transaction ID được dùng để quyết định dữ liệu hiển thị ra sao?
Bạn sẽ phân biệt snapshot tại thời điểm bắt đầu câu lệnh với snapshot tại thời điểm bắt đầu transaction như thế nào?
Bạn sẽ phân tích điều gì xảy ra khi một transaction đọc phiên bản cũ trong lúc transaction khác đã cập nhật cùng hàng ra sao?
Bạn sẽ mô tả cách MVCC xử lý hai transaction đồng thời muốn cập nhật một bản ghi như thế nào?
Bạn sẽ xây dựng ví dụ nào để chứng minh MVCC không tự động ngăn mọi hiện tượng lost update hoặc write skew?
Bạn sẽ đánh giá tác động của transaction đọc kéo dài đối với việc thu hồi phiên bản dữ liệu cũ như thế nào?
Bạn sẽ phân tích sự tăng trưởng của undo hoặc phiên bản hàng cũ khi hệ thống có nhiều transaction lâu ra sao?
Bạn sẽ lựa chọn phương pháp quan sát vacuum, garbage collection hoặc version cleanup phù hợp hệ quản trị đang dùng như thế nào?
Bạn sẽ giải thích sự khác biệt giữa đọc phiên bản nhất quán và đọc có khóa trước khi cập nhật như thế nào?
Bạn sẽ kiểm thử sự khác nhau về hành vi MVCC giữa truy vấn SELECT thông thường và SELECT FOR UPDATE ra sao?
Bạn sẽ xác định các giới hạn của snapshot khi cập nhật đồng thời một tập bản ghi có quan hệ logic như thế nào?
Bạn sẽ thiết kế transaction bảo vệ ràng buộc toàn cục khi dữ liệu liên quan được lưu trên nhiều hàng ra sao?
Bạn sẽ quyết định dùng unique constraint, conditional update hay isolation cao hơn để bảo vệ bất biến theo loại xung đột như thế nào?
Bạn sẽ phân biệt retry khi xảy ra lỗi có thể khôi phục với retry khi có lỗi dữ liệu hoặc vi phạm ràng buộc như thế nào?
Bạn sẽ phân loại mã lỗi deadlock, serialization failure, lock timeout và lỗi kết nối theo chính sách xử lý như thế nào?
Bạn sẽ thiết kế retry có giới hạn số lần, backoff và jitter để giảm dồn tải lên các hàng đang tranh chấp ra sao?
Bạn sẽ ngăn thao tác bị thực thi hai lần khi ứng dụng không nhận được phản hồi COMMIT nhưng database có thể đã ghi thành công như thế nào?
Bạn sẽ xây dựng idempotency key hoặc ràng buộc duy nhất để bảo vệ nghiệp vụ nhận thanh toán qua API như thế nào?
Bạn sẽ xác định khi nào cần đọc lại trạng thái dữ liệu trước khi chạy lại một transaction bị xung đột ra sao?
Bạn sẽ đảm bảo một transaction được chạy lại từ đầu không tái sử dụng kết quả đọc cũ gây sai dữ liệu như thế nào?
Bạn sẽ bố trí việc gửi email, gọi API bên ngoài hoặc phát sự kiện ngoài transaction để tránh tác dụng phụ bị lặp khi retry ra sao?
Bạn sẽ dùng transactional outbox hoặc cơ chế tương đương để đồng bộ ghi dữ liệu và phát sự kiện như thế nào?
Bạn sẽ xử lý việc timeout ở phía ứng dụng khi trạng thái commit của cơ sở dữ liệu chưa xác định ra sao?
Bạn sẽ quyết định lúc nào nên trả lỗi bận, xếp hàng hoặc giới hạn đồng thời thay vì tiếp tục retry như thế nào?
Bạn sẽ theo dõi tỷ lệ retry thành công, số lần serialization failure và độ trễ cộng dồn để điều chỉnh chính sách ra sao?
Bạn sẽ thiết kế đường xử lý an toàn khi transaction liên quan nhiều dịch vụ không thể bao trong một giao dịch cơ sở dữ liệu như thế nào?
Bạn sẽ giải thích hiện tượng hot row hoặc hot key khi nhiều request cùng cập nhật một bản ghi như thế nào?
Bạn sẽ đánh giá cách tách bộ đếm, phân bổ khóa hoặc xử lý theo hàng đợi giúp giảm tranh chấp ghi ra sao?
Bạn sẽ chọn kích thước batch và số thao tác trong transaction để giảm thời gian giữ khóa mà vẫn bảo đảm tính đúng đắn như thế nào?
Bạn sẽ cân nhắc sắp xếp thứ tự cập nhật và dùng index phù hợp để tránh mở rộng phạm vi khóa ra sao?
Bạn sẽ xác định nguyên nhân lock contention tăng đột biến từ các chỉ số thời gian chờ, blocked sessions và số transaction hoạt động như thế nào?
Bạn sẽ liên kết trace của request với transaction ID và câu SQL để tìm nơi xảy ra chờ khóa ra sao?
Bạn sẽ phân biệt pool connection bị cạn do truy vấn chậm, lock wait và connection leak bằng những phép đo nào?
Bạn sẽ chọn cách tối ưu khi CPU cơ sở dữ liệu thấp nhưng độ trễ transaction tăng và số phiên chờ khóa cao như thế nào?
Bạn sẽ đánh giá ảnh hưởng của tăng số worker hoặc pool connection lên mức tranh chấp cùng một hàng ra sao?
Bạn sẽ xác định ngưỡng cảnh báo khi deadlock, serialization failure hoặc lock wait vượt mức bình thường ra sao?
Bạn sẽ thiết kế thử nghiệm tải hỗn hợp đọc và ghi để đo thông lượng, độ trễ và tỷ lệ giao dịch bị hủy như thế nào?
Bạn sẽ mô phỏng cạnh tranh cập nhật cùng một bản ghi để so sánh cách tiếp cận optimistic và pessimistic locking ra sao?
Bạn sẽ kiểm tra kết quả cuối của các transaction đồng thời bằng bất biến nghiệp vụ và lịch sử thực thi như thế nào?
Bạn sẽ phân tích trường hợp chỉ số tổng hợp cuối cùng đúng nhưng một số giao dịch riêng lẻ vẫn bị mất cập nhật ra sao?
Bạn sẽ tổ chức điều tra một sự cố số dư sai gồm tái hiện lịch thực thi, xác định isolation và rà soát retry như thế nào?
Bạn sẽ quyết định thay đổi isolation, bổ sung constraint hay sửa thiết kế nghiệp vụ dựa trên bằng chứng nào?
Bạn sẽ đặt các tiêu chí nghiệm thu nào về tính đúng đắn, deadlock, độ trễ và khả năng phục hồi trước khi đưa xử lý đồng thời vào sản xuất?
