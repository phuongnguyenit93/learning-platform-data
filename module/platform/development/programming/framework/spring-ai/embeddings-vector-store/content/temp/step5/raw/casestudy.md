Một hệ thống tìm kiếm quy định nội bộ dùng Spring AI EmbeddingModel để lập chỉ mục hàng nghìn tài liệu, nhưng truy vấn tiếng Việt có dấu thường trả kết quả kém hơn truy vấn tiếng Anh cùng ý nghĩa.
Ứng dụng hỗ trợ khách hàng đã tạo vector bằng một embedding model, sau khi đổi nhà cung cấp lại dùng model mới cho câu hỏi nhưng tiếp tục tìm trong kho vector cũ và thứ hạng kết quả giảm mạnh.
Nhóm phát triển cập nhật phiên bản embedding model của dịch vụ Java mà không tái tạo dữ liệu lịch sử, khiến cùng một câu hỏi có kết quả rất khác giữa tài liệu mới và cũ.
Một nền tảng tuyển dụng dùng embedding cho mô tả công việc, nhưng các truy vấn ngắn như tên vị trí chuyên môn bị ghép nhầm với những hồ sơ có từ khóa gần giống mà khác trách nhiệm.
Ứng dụng tra cứu hồ sơ y tế dùng EmbeddingModel để biểu diễn câu mô tả triệu chứng; các từ viết tắt chuyên ngành ở bệnh viện khác nhau làm kết quả tìm tương đồng bị sai ngữ cảnh.
Dịch vụ nhận phản hồi khách hàng bằng nhiều ngôn ngữ nhưng embedding model hiện tại chỉ được đánh giá với một ngôn ngữ, khiến phản hồi tiếng Việt và tiếng Nhật khó tìm trong cùng kho dữ liệu.
Hệ thống tìm thiết bị công nghiệp sử dụng embedding trên mã linh kiện ngắn, nhưng hai mã chỉ khác một ký tự bị xem là tương tự và nhân viên chọn sai phụ tùng.
Một hệ thống hỗ trợ pháp lý tìm điều khoản hợp đồng bằng mức tương đồng ngữ nghĩa, nhưng từ phủ định trong câu truy vấn bị xem nhẹ và các điều khoản mang nghĩa ngược vẫn được xếp hạng cao.
Nhóm dùng cùng một bộ embedding cho tiêu đề và toàn văn tài liệu, nhưng tiêu đề được viết bằng từ ngữ tiếp thị còn nội dung là thuật ngữ kỹ thuật làm kết quả khớp không ổn định.
Một ứng dụng tra cứu chính sách dùng cả embedding của ảnh và embedding của văn bản từ hai hệ thống khác nhau, dẫn đến không thể so sánh điểm tương đồng trong một truy vấn thống nhất.
Hệ thống gửi toàn bộ tài liệu dài hàng trăm trang vào EmbeddingModel mỗi lần cập nhật, khiến yêu cầu vượt giới hạn đầu vào và một số tài liệu hoàn toàn không được lập chỉ mục.
Ứng dụng tạo embedding cho từng câu quá ngắn trong bản mô tả sản phẩm, làm mất ngữ cảnh điều kiện bảo hành và trả về các đoạn câu không đủ thông tin cho người dùng.
Nhóm tích hợp thêm bộ tiền xử lý xóa dấu câu và chữ hoa trước khi embedding; các ký hiệu phiên bản phần mềm và số hiệu hợp đồng bị biến đổi khiến việc truy xuất trở nên không chính xác.
Một kho tài liệu hỗn hợp có các đoạn tiếng Việt dùng Unicode ở nhiều dạng chuẩn hóa khác nhau; hệ thống tạo vector trùng lặp cho cùng nội dung từ các nguồn nhập liệu.
Ứng dụng hỗ trợ bán hàng gửi cả thông tin tên khách hàng và nội dung câu hỏi vào embedding chung; khi tra cứu, kết quả bị ảnh hưởng bởi thông tin định danh thay vì chủ đề cần tìm.
Nhóm xây hệ thống tìm kiếm bài viết dùng chung EmbeddingModel cho dữ liệu và truy vấn nhưng không theo dõi phiên bản model; sau nhiều lần deploy, không thể giải thích sự thay đổi độ liên quan.
Một công ty chuyển kho vector sang hạ tầng khác và quên cấu hình số chiều embedding tương ứng, khiến các bản ghi mới bị từ chối trong khi dữ liệu cũ vẫn tìm kiếm được.
Dịch vụ đánh giá chất lượng sử dụng điểm cosine similarity nhưng so sánh trực tiếp với một ngưỡng từng hiệu chỉnh cho embedding model khác; số câu hỏi bị từ chối tăng đột biến.
Một trung tâm hỗ trợ dùng cùng mô hình embedding cho bảng thuật ngữ và các đoạn hội thoại dài, nhưng truy vấn chỉ chứa mã lỗi dạng số thường bị những đoạn văn không liên quan vượt lên.
Nhóm vận hành đổi mô hình embedding có chi phí thấp hơn cho 10% tài liệu mới để thử nghiệm, khiến một kho VectorStore chứa các vector không còn đồng nhất về cách biểu diễn.
Dữ liệu danh mục sản phẩm được làm giàu bằng mô tả do AI sinh trước khi embedding, nhưng các mô tả thêm thuộc tính không tồn tại và ảnh hưởng tới kết quả tìm hàng.
Một nhà xuất bản cần tìm các bài viết tương tự nhưng không muốn bài trích dẫn lại chính nó; top kết quả chủ yếu là các bản sao nội dung được đăng trên nhiều miền khác nhau.
Ứng dụng Spring AI tiếp nhận file PDF quét từ năm trước, nhưng bước trích xuất chỉ đọc lớp văn bản nên một số tài liệu không có nội dung để tạo embedding.
Quy trình nhập liệu đọc PDF có bố cục hai cột theo thứ tự sai; các đoạn chunk trộn nội dung của hai mục và tạo kết quả truy xuất thiếu mạch lạc.
Một hợp đồng chứa nhiều bảng giá và chú thích cuối trang, nhưng pipeline trích xuất mất quan hệ giữa ô trong bảng và tiêu đề cột khi lưu thành văn bản.
Nhóm xây kho kiến thức từ tài liệu Word có header và footer lặp trên mọi trang; hàng nghìn chunk gần giống nhau lấn át nội dung quan trọng trong các truy vấn.
Ứng dụng lấy dữ liệu từ HTML nội bộ nhưng lưu cả thanh điều hướng và thông báo cookie vào text trước khi embedding; kết quả tìm kiếm thường trỏ tới những đoạn không chứa câu trả lời.
Một tài liệu hướng dẫn kỹ thuật có nhiều khối mã và chú giải bằng văn bản, nhưng cách tách đoạn đưa tên hàm vào chunk khác với giải thích khiến truy xuất câu hỏi lập trình thiếu chính xác.
Đội dữ liệu đặt kích thước chunk quá nhỏ cho tài liệu chính sách, làm điều kiện ngoại lệ nằm ở đoạn tiếp theo và nhân viên chỉ đọc được quy định chung.
Một doanh nghiệp chia tài liệu thành chunk quá lớn để giảm số lượng vector, khiến nhiều chủ đề khác nhau nằm chung một vector và kết quả tìm theo vấn đề cụ thể giảm độ chính xác.
Pipeline chunking cắt ở số ký tự cố định mà không giữ ranh giới câu; các mệnh đề phủ định hoặc câu điều kiện bị chia đôi khiến truy vấn tìm sai quy trình.
Ứng dụng cập nhật chính sách theo từng điều khoản nhưng chunking theo trang giấy; sửa một câu giữa tài liệu tạo lại nhiều vector không liên quan và phát sinh chi phí cao.
Nhóm điều chỉnh overlap giữa các chunk lên rất lớn để bảo toàn ngữ cảnh; một câu hỏi trả về nhiều kết quả trùng nội dung và làm bộ ngữ cảnh cho câu trả lời bị lãng phí.
Một hệ thống hỏi đáp dùng chunk overlap bằng không với tài liệu kỹ thuật có hình minh họa, khiến phần hướng dẫn tham chiếu hình nằm tách khỏi mô tả thao tác.
Tài liệu đào tạo được chia theo tiêu đề Markdown, nhưng những mục ngắn chỉ chứa một dòng bị gộp nhầm với mục kế tiếp thuộc chủ đề khác.
Đội triển khai thay đổi chiến lược chunking sau sáu tháng, nhưng chỉ dữ liệu nhập mới dùng chiến lược mới; độ liên quan khác biệt đáng kể giữa tài liệu trước và sau đợt nâng cấp.
Ứng dụng đưa đoạn text rỗng hoặc chỉ có khoảng trắng từ file lỗi vào quy trình embedding; batch nhập liệu bị gián đoạn và nhóm vận hành khó xác định tài liệu nguồn.
Một bộ tài liệu pháp lý chứa phần phụ lục rất dài không có dấu câu; bộ tách chunk dựa theo câu tạo một đoạn vượt giới hạn đầu vào EmbeddingModel.
Hệ thống ingest nhiều bản PDF của cùng một biểu mẫu ở các thư mục khác nhau; không có định danh ổn định cho nội dung khiến các kết quả tương tự xuất hiện trùng lặp.
Nhà vận hành nhập lại toàn bộ tài liệu sau khi một job gặp timeout, nhưng không biết chunk nào đã được ghi vào VectorStore và số bản ghi tăng gấp đôi.
Một hệ thống dùng đường dẫn file làm ID tài liệu; khi đổi tên thư mục lưu trữ, cùng nội dung được thêm như tài liệu mới và lịch sử truy xuất trở nên phân mảnh.
Dịch vụ đồng bộ tài liệu phát hiện tệp được sửa nhưng không xóa các vector sinh từ phiên bản trước; người dùng thấy cả quy trình cũ lẫn quy trình vừa cập nhật.
Một cơ sở tri thức xóa tài liệu theo yêu cầu quản trị nhưng các chunk vector tương ứng vẫn tồn tại trong VectorStore và tiếp tục được trả về khi tìm kiếm.
Quy trình đồng bộ cập nhật một tài liệu 100 chunk nhưng thất bại ở chunk thứ 62; hệ thống truy xuất đang phục vụ đồng thời các chunk thuộc hai phiên bản.
Ứng dụng nhập nội dung từ nhiều hệ thống CMS nhưng mỗi nguồn đặt tên metadata khác nhau, khiến bộ lọc theo loại tài liệu chỉ trả về một phần kho dữ liệu.
Nhóm ingest thêm metadata về số trang mà chỉ ghi giá trị dưới dạng chuỗi; bộ phận vận hành không thể lọc đúng các trang theo khoảng số thứ tự.
Đội dữ liệu lưu thời điểm ban hành tài liệu bằng nhiều múi giờ và định dạng khác nhau; các truy vấn lấy quy định có hiệu lực sau một ngày cụ thể cho kết quả sai.
Ứng dụng tìm kiếm chỉ giữ text chunk mà không lưu ID tài liệu và vị trí nguồn; khi người dùng yêu cầu mở trang gốc, hệ thống không có dữ liệu để dẫn nguồn chính xác.
Một bản ghi vector chỉ có metadata tiêu đề tài liệu, thiếu phiên bản và phòng ban chịu trách nhiệm; kết quả truy xuất đúng nội dung nhưng không xác định được ai xác nhận tính hiệu lực.
Hệ thống tìm kiếm tài liệu hai ngôn ngữ lưu metadata ngôn ngữ không nhất quán, khiến người dùng lọc tiếng Việt nhưng vẫn nhận những đoạn chỉ có tiếng Anh.
Nhóm triển khai VectorStore nhận metadata lồng nhau từ CMS, nhưng truy vấn filter mong đợi trường phẳng; chỉ một số tài liệu qua được điều kiện lọc.
Một nền tảng học trực tuyến dùng Spring AI VectorStore cho cả bài giảng công khai và đề thi nội bộ; bộ lọc theo mức độ truy cập bị bỏ quên trên một nhánh tìm kiếm.
Hệ thống đa tenant lưu các vector của nhiều doanh nghiệp trong cùng PGvector, nhưng query tìm kiếm của một tenant thiếu điều kiện tenantId và trả về trích đoạn thuộc khách hàng khác.
Ứng dụng bổ sung metadata tenantId ngay trước khi gọi VectorStore nhưng một số job xử lý nền không truyền ngữ cảnh tenant; dữ liệu mới thiếu thuộc tính phân tách.
Nhóm tích hợp cho phép người dùng nhập biểu thức filter trực tiếp; một chuỗi điều kiện không được kiểm soát khiến truy vấn trả về tài liệu ngoài nhóm được phép.
Một hệ thống quản lý quyền theo nhóm lưu metadata allowedGroups tại thời điểm index; sau khi nhân viên chuyển phòng, kết quả vẫn dựa vào quyền cũ trên bản ghi vector.
Kho hồ sơ nhân sự lưu cả thông tin lương và đánh giá hiệu suất; truy vấn từ chatbot công ty lọc theo chủ đề nhưng không xét quyền người hỏi với từng tài liệu.
Ứng dụng tìm nội dung hợp đồng theo metadata của dự án, nhưng các chunk của bản phụ lục bị thiếu projectId và biến mất khỏi kết quả dù nội dung có liên quan.
Hệ thống dùng metadata loại sản phẩm để lọc trước truy xuất, nhưng giá trị nhập từ hai nguồn có dạng khác nhau như chữ thường và chữ hoa khiến recall giảm.
Nhóm vận hành đánh dấu tài liệu đã hết hiệu lực trong CMS nhưng metadata trong VectorStore cập nhật chậm; chatbot tiếp tục trích quy định vừa bị thu hồi.
Ứng dụng áp bộ lọc năm xuất bản sau khi đã lấy top kết quả tương đồng; người dùng thường nhận dưới số lượng kết quả mong muốn dù kho còn nhiều tài liệu hợp lệ.
Một trang thương mại điện tử tìm sản phẩm bằng mô tả tự nhiên nhưng filter tồn kho chỉ được áp ở tầng giao diện; các sản phẩm hết hàng vẫn chiếm vị trí topK.
Đội phát triển dùng filter rất hẹp cho tài liệu kỹ thuật, nhưng truy vấn tìm quá ít chunk và không có tín hiệu phân biệt thiếu dữ liệu với độ tương đồng thấp.
Một nền tảng nghiên cứu lưu trạng thái bản nháp, bản duyệt và bản công bố trong metadata; endpoint công khai không phân biệt trạng thái và trả tài liệu chưa phát hành.
Hệ thống index báo cáo từ nhiều chi nhánh với cùng tên tài liệu; thiếu metadata về địa điểm khiến kết quả trích dẫn đúng chủ đề nhưng sai đơn vị áp dụng.
Ứng dụng chuyển từ lưu metadata dạng số sang chuỗi trong quá trình nâng cấp và không di trú bản ghi cũ; các điều kiện lọc dựa trên khoảng giá trị hoạt động không đồng đều.
Đội triển khai Spring AI VectorStore trên PostgreSQL nhưng môi trường mới chưa kích hoạt extension pgvector; ứng dụng khởi động nhưng thao tác lưu vector đầu tiên thất bại.
Một kho PGvector đã được tạo cột vector với số chiều của model cũ, còn EmbeddingModel mới trả vector số chiều khác khiến batch ghi dữ liệu bị từ chối.
Nhóm lập trình thêm một thuộc tính metadata vào dữ liệu tài liệu nhưng schema PostgreSQL và cấu hình ánh xạ không tương thích, khiến một số thuộc tính bị bỏ qua khi truy vấn.
Hệ thống lưu hàng triệu embedding vào PGvector nhưng chưa có chiến lược index tìm hàng xóm gần; truy vấn toàn kho tăng độ trễ khi số tài liệu tăng nhanh.
Đội thử nghiệm tạo chỉ mục ANN để tăng tốc PGvector nhưng dùng tập dữ liệu nhỏ và không so sánh chất lượng với tìm kiếm chính xác; sau triển khai một số kết quả phù hợp không còn trong topK.
Một hệ thống dùng chỉ số cosine similarity để đánh giá độ liên quan, nhưng cấu hình khoảng cách và cách sắp xếp kết quả giữa hai môi trường PGvector khác nhau.
Nhóm vận hành tạo chỉ mục dựa trên số lượng vector hiện có, nhưng sau khi dữ liệu tăng gấp mười lần, độ trễ tìm kiếm và mức sử dụng bộ nhớ vượt ngân sách.
Ứng dụng dùng PGvector chung với database giao dịch quan trọng; tác vụ nhập hàng loạt embedding làm tăng I/O và ảnh hưởng thời gian phản hồi đơn hàng.
Một đợt tạo lại chỉ mục vector trên PostgreSQL kéo dài nhiều giờ trong khi ứng dụng tìm kiếm vẫn phục vụ người dùng; số truy vấn chờ và độ trễ tăng rõ rệt.
Truy vấn PGvector lọc theo tenantId rồi sắp xếp độ tương đồng, nhưng nhóm phát triển chỉ kiểm thử trên một tenant nhỏ; tenant lớn nhận kết quả chậm bất thường.
Nhóm dữ liệu xây chỉ mục vector gần đúng cho toàn bộ bảng nhưng các truy vấn luôn kèm filter theo phòng ban; sau khi giới hạn kết quả, nhiều phòng ban không còn đủ chunk phù hợp.
Một dịch vụ dùng PGvector có bảng chứa hàng chục triệu chunk, nhưng xóa tài liệu nhiều lần mà không theo dõi lưu trữ và thống kê; dung lượng disk tiếp tục tăng nhanh.
Ứng dụng lưu vector cùng metadata ở PostgreSQL nhưng bảng không có cơ chế ánh xạ ổn định đến documentId nguồn; khi cần xóa toàn bộ chunk của một hợp đồng, các bản ghi còn sót lại.
Nhóm triển khai replication cho PostgreSQL nhưng app đọc VectorStore từ replica có độ trễ; người dùng vừa cập nhật tài liệu không thể tìm thấy nội dung mới trong vài phút.
Một job nhập tài liệu dùng nhiều kết nối đến PGvector theo số chunk thay vì batch; khi hàng trăm file vào cùng lúc, connection pool PostgreSQL bị bão hòa.
Đội triển khai Java ghi embedding theo từng chunk trong transaction dài; lúc một document thất bại giữa chừng, tài nguyên DB bị giữ và việc cập nhật của những người khác chậm đi.
Ứng dụng đồng bộ giữa lưu file nguồn và lưu vector trong hai hệ thống tách biệt; một lần mất kết nối khiến file đã có nhưng dữ liệu tìm kiếm vẫn không tồn tại.
Một sự cố PostgreSQL buộc đội khôi phục bản backup tuần trước; nhiều file mới vẫn hiện trong CMS nhưng không có vector tương ứng trong kho tìm kiếm.
Nhóm đổi embedding model cho PGvector bằng cách thêm cột mới nhưng rollout chưa đồng bộ; một số pod Java truy vấn vector cũ trong khi pod khác truy vấn vector mới.
Một index PGvector được tạo với lựa chọn tham số phục vụ tốc độ cao, nhưng nhóm kỹ thuật không kiểm tra recall trên bộ truy vấn thực tế và hệ thống bỏ sót tài liệu quan trọng.
Đội dùng chỉ mục HNSW trong PGvector cho nhiều truy vấn đồng thời, nhưng cấu hình bộ nhớ và tài nguyên khi xây dựng chỉ mục vượt ngưỡng cho phép của môi trường triển khai.
Nhóm dữ liệu thử chỉ mục IVFFlat trên tập vector quá nhỏ trước khi đổ dữ liệu thật; sau khi dữ liệu thay đổi phân bố, chất lượng tìm gần nhất không còn như kết quả thử nghiệm.
Ứng dụng dùng metadata về ngày hết hạn để lọc trong PostgreSQL nhưng không cập nhật thống kê và chiến lược thực thi truy vấn; thời gian tìm tương đồng biến động mạnh giữa các ngày.
Một công ty cần tách dữ liệu khách hàng theo vùng địa lý nhưng PGvector đang lưu tất cả trên cùng cụm, khiến yêu cầu lưu trú dữ liệu và truy xuất theo khu vực khó được kiểm chứng.
Nhóm vận hành thay đổi chính sách lưu giữ từ ba năm xuống một năm, nhưng việc xóa tài liệu gốc và dữ liệu embedding trong PGvector diễn ra theo hai lịch khác nhau.
Hệ thống phát hành phiên bản quy trình mới mỗi tuần và lưu song song embedding cũ/mới trong một bảng; truy vấn không có ràng buộc version trả cả hướng dẫn đã lỗi thời.
Ứng dụng tra cứu hàng hóa qua VectorStore với topK nhỏ; câu hỏi chi tiết chỉ xuất hiện ở chunk hạng thấp hơn nên trợ lý không tìm thấy thông tin dù tài liệu đã được index.
Một chatbot chính sách trả rất nhiều chunk có nội dung gần như trùng nhau; các phần quan trọng về trường hợp ngoại lệ bị đẩy khỏi giới hạn ngữ cảnh của bước trả lời.
Đội phát triển hạ similarity threshold để tăng số kết quả trong VectorStore, nhưng câu hỏi ngoài phạm vi vẫn nhận các tài liệu ít liên quan và người dùng mất niềm tin.
Ứng dụng tăng similarity threshold theo một chỉ số đo ở môi trường thử nghiệm, nhưng câu hỏi đa ngôn ngữ trong production thường không đạt ngưỡng dù có tài liệu phù hợp.
Nhóm chọn topK dựa vào số chunk tối đa mà hệ thống sinh câu trả lời nhận được; khi người dùng hỏi nhiều chủ đề trong một câu, kết quả không cân bằng giữa các chủ đề.
Người dùng tìm quy trình bằng đúng mã số tài liệu, nhưng VectorStore chỉ sử dụng embedding nên kết quả ngữ nghĩa gần giống xếp cao hơn tài liệu có mã trùng chính xác.
Một hệ thống tra cứu sản phẩm cần kết hợp mô tả ngữ nghĩa với mã SKU và trạng thái kho, nhưng truy vấn chỉ dựa trên điểm vector khiến kết quả sản phẩm sai mã xuất hiện.
Ứng dụng dùng phép tìm tương đồng cho tài liệu có nhiều phiên bản; kết quả hạng cao nhất là đoạn từ phiên bản cũ vì cách diễn đạt gần câu hỏi hơn bản mới.
Một đội hỗ trợ đánh giá kết quả truy xuất chỉ bằng vài câu hỏi do chính người xây hệ thống tạo ra; phản hồi khách hàng thật chứa cách diễn đạt khác và tỉ lệ tìm đúng thấp.
Nhóm tối ưu thời gian tìm kiếm PGvector nhưng không đo recall@K; chỉ số độ trễ cải thiện trong khi số đoạn tài liệu đúng xuất hiện trong top kết quả giảm.
Một dự án đo precision@K chỉ với các câu hỏi đơn giản có một tài liệu liên quan; khi câu hỏi cần kết hợp nhiều nguồn, cách đánh giá hiện tại không phản ánh chất lượng.
Đội xây bộ kiểm thử truy xuất không đánh dấu tài liệu liên quan theo từng câu hỏi; sau thay đổi chunking, nhóm chỉ so sánh điểm similarity mà không biết kết quả hữu ích có tăng hay không.
Ứng dụng đánh giá truy xuất trên một tập câu hỏi mà tài liệu câu trả lời đã bị xóa; phép đo liên tục báo lỗi tìm kiếm dù hệ thống không thể cung cấp nguồn hợp lệ.
Một trường đại học có nhiều bài giảng tương tự theo các năm học; người dùng yêu cầu tài liệu học kỳ hiện tại nhưng điểm vector ưu tiên giáo trình của khóa trước.
Hệ thống hỏi đáp báo giá dùng trích đoạn từ VectorStore nhưng không kiểm tra sự hiện diện của số liệu đơn giá trong chunk; trợ lý trình bày giá không có nguồn đối soát.
Nhóm triển khai RAG bằng Spring AI lấy năm chunk phù hợp nhất, nhưng thứ tự chunk được đưa sang bước sinh câu trả lời khiến model thiên về nội dung của chunk đầu.
Một bộ truy vấn đánh giá có các câu chứa phủ định hoặc điều kiện kép; top kết quả của VectorStore phù hợp chủ đề nhưng bỏ qua điều kiện quan trọng trong câu hỏi.
Ứng dụng tìm quy định an toàn trả về chunk có nội dung rất gần câu hỏi nhưng phần cảnh báo nằm ở chunk liền kề không được lấy; nhân viên nhận được hướng dẫn thiếu bối cảnh.
Đội thử kỹ thuật reranking để sắp xếp lại kết quả VectorStore, nhưng số lượng ứng viên trước rerank quá ít khiến các tài liệu liên quan không bao giờ được xét.
Nhóm tìm kiếm tích hợp hybrid retrieval giữa từ khóa và embedding nhưng chưa đo tác động trên truy vấn tên sản phẩm so với truy vấn diễn đạt tự nhiên; trải nghiệm không ổn định giữa hai nhóm.
Ứng dụng giảm số chiều embedding bằng một bước chuyển đổi ngoài pipeline nhưng không đánh giá tác động lên khả năng phân biệt các khái niệm gần nhau trong tài liệu pháp lý.
Một nền tảng tra cứu dùng score trả về từ hai VectorStore khác loại để hợp nhất bảng xếp hạng, nhưng thang đo và hướng tốt/xấu của điểm không tương thích.
Nhóm áp Maximal Marginal Relevance để đa dạng hóa kết quả, nhưng người dùng tìm một điều khoản cụ thể lại nhận nhiều đoạn khác chủ đề do mức ưu tiên đa dạng quá cao.
Hệ thống tìm tài liệu đa tenant dùng bước rerank sau khi truy xuất, nhưng tập ứng viên chưa được lọc quyền đầy đủ và log reranker chứa nội dung của tenant khác.
Một ứng dụng tự động tạo embedding cho tệp do người dùng tải lên, nhưng bộ lọc chống dữ liệu nhạy cảm chỉ chạy ở giao diện và không áp dụng cho job ingest nền.
Dịch vụ hỗ trợ pháp lý cho phép tài liệu có thông tin cá nhân vào VectorStore mà không theo dõi thời hạn lưu trữ; dữ liệu đã quá hạn vẫn có thể xuất hiện trong truy vấn.
Nhóm kiểm toán phát hiện log của bước tạo embedding ghi toàn bộ text chunk, bao gồm số tài khoản và địa chỉ khách hàng; nhiều nhân sự không phụ trách dữ liệu vẫn xem được.
Ứng dụng dùng embedding API của bên thứ ba nhưng phòng bảo mật chưa xác minh dữ liệu nào được truyền ra ngoài và có chứa thông tin nội bộ thuộc diện hạn chế.
Một kẻ tấn công chèn chỉ dẫn giả mạo vào tài liệu được index; hệ thống tra cứu lấy đoạn đó làm ngữ cảnh cho trợ lý và ranh giới giữa nội dung nguồn với lệnh điều khiển trở nên mơ hồ.
Kho tri thức của công ty chứa thông báo hết hiệu lực và quy định hiện hành ở hai chunk riêng; chatbot trả lời theo đoạn cũ vì chỉ xét điểm tương đồng mà không đối chiếu tính hiệu lực.
Một cổng tìm kiếm lưu vector của tài liệu mật trong cùng bảng với tài liệu công khai, nhưng bộ lọc phân quyền được áp sau khi có topK; truy vấn của khách nhận số kết quả khác thường.
Nhóm ứng dụng lưu toàn bộ metadata nguồn vào phản hồi tìm kiếm công khai, khiến đường dẫn file nội bộ và thông tin chủ sở hữu nhạy cảm bị lộ dù nội dung chunk đã được lọc.
Nhà cung cấp tăng giá tính embedding theo số token, trong khi hệ thống mỗi đêm tạo lại vector của toàn bộ tài liệu không thay đổi; hóa đơn dịch vụ tăng nhanh theo kích thước kho.
Ứng dụng có luồng đồng bộ theo sự kiện và một luồng chạy lại hằng ngày; cùng tài liệu bị tạo embedding hai lần do không có dấu hiệu nhận biết phiên bản nội dung.
Một nhà bán lẻ tạo embedding theo từng bản ghi sản phẩm riêng lẻ, nhưng mỗi đợt cập nhật giá rất nhỏ lại tái embedding toàn bộ mô tả dài dù nội dung tìm kiếm không đổi.
Dịch vụ lập chỉ mục đẩy hàng nghìn chunk vào EmbeddingModel đồng thời; nhà cung cấp áp hạn mức request và một số batch bị từ chối rồi không được đưa lại vào hàng đợi.
Nhóm triển khai batch embedding kích thước rất lớn để giảm overhead, nhưng một chunk lỗi làm toàn bộ lô phải thử lại và chi phí xử lý tăng bất thường.
Ứng dụng xử lý tệp mới ngay trong request HTTP tải lên và đợi hoàn tất embedding, khiến thời gian phản hồi của người dùng tăng tới hàng phút khi mô hình ở xa.
Nhóm tách bước ingest khỏi request HTTP nhưng không giám sát hàng đợi xử lý; người dùng tải tài liệu lên thành công mà nhiều giờ sau vẫn không tìm thấy nội dung.
Một hệ thống phục vụ chatbot gọi EmbeddingModel cho mọi câu hỏi mà không có cache các truy vấn lặp; trong ngày chạy chiến dịch, số token và độ trễ tăng nhanh.
Ứng dụng tái sử dụng embedding của câu hỏi có vẻ giống nhau bằng khóa cache quá thô; các câu chỉ khác mã đơn hàng hoặc phủ định lại dùng cùng vector và trả sai nguồn.
Nhóm quan sát chỉ lưu thời gian tìm vector mà bỏ qua thời gian tạo query embedding; báo cáo latency thấp hơn đáng kể so với trải nghiệm hỏi đáp thực tế.
Một ứng dụng dùng model embedding nhỏ để tiết kiệm chi phí nhưng không chạy kiểm thử trên bộ câu hỏi chuyên ngành; sau khi triển khai, số ticket phải chuyển cho nhân viên tăng.
Nhóm thay chunk size và topK cùng lúc để tối ưu throughput rồi so sánh chất lượng với bản trước; kết quả tốt hơn nhưng không biết thay đổi nào tạo ra cải thiện.
Đội QA thử truy xuất chỉ trên bộ tài liệu sạch bằng tiếng Anh; khi production có PDF tiếng Việt, bảng biểu và văn bản OCR lỗi, chất lượng tìm kiếm giảm ngoài dự đoán.
Một hệ thống tìm kiếm đạt tỷ lệ câu trả lời đúng cao trong ngày phát hành nhưng không theo dõi dữ liệu mới và sửa đổi hàng tuần; sau vài tháng, câu trả lời dẫn tới tài liệu lỗi thời.
Ứng dụng lưu VectorStore trong cụm PGvector duy nhất và không có kế hoạch phục hồi khi PostgreSQL tạm thời mất kết nối; toàn bộ tính năng tìm kiếm trở nên không khả dụng.
Nhóm vận hành chỉ giám sát CPU và bộ nhớ của PGvector mà không đo tốc độ index, lag đồng bộ, truy vấn rỗng và tỷ lệ kết quả sai; lỗi dữ liệu tồn tại nhiều ngày không được phát hiện.
Đội triển khai hai phiên bản pipeline tạo embedding chạy song song khi nâng cấp Spring AI, nhưng metadata không ghi pipelineVersion; kết quả không thể phân tích theo đợt nhập dữ liệu.
Trong đợt kiểm thử hồi quy, nhóm chạy lại bộ câu hỏi giống nhau và nhận kết quả thay đổi khi ANN index được cập nhật; chưa có quy tắc đánh giá độ ổn định thứ hạng theo thời gian.
Một tổ chức lưu dữ liệu đã chuyển đổi sang vector nhưng chưa lưu bản hash và lịch sử nhập liệu; khi cần chứng minh nguồn gốc một trích đoạn, đội vận hành không xác định được tài liệu ban đầu.
Ứng dụng hỗ trợ tìm chuyên gia nội bộ dựa trên mô tả hồ sơ, nhưng sau khi một nhân viên nghỉ việc vector hồ sơ vẫn tồn tại và liên hệ cũ tiếp tục được gợi ý.
Nhóm phát triển dùng Spring AI VectorStore cho cả lịch sử hội thoại và tài liệu hướng dẫn mà không phân biệt loại nguồn; truy vấn về chính sách thường trả lời dựa trên hội thoại chưa được xác minh.
Một hệ thống tìm kiếm tài liệu mới được index gửi kết quả tới dịch vụ trả lời nhưng không giữ metadata nguồn và score trong trace; khi người dùng phản ánh trả lời sai, không tái hiện được lý do lựa chọn.
Đội chuyển từ kho vector tạm thời sang PGvector để triển khai production, nhưng chưa đo dung lượng lưu trữ, thời gian phục hồi và độ trễ khi đạt hàng triệu chunk; hệ thống không đáp ứng SLA sau vài tháng.
