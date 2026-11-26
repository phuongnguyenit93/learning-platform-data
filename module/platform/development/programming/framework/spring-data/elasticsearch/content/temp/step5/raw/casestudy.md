Một ứng dụng Spring Boot dùng Spring Data Elasticsearch để lưu sản phẩm nhưng @Document trỏ tới tên index cũ, khiến bản ghi mới không xuất hiện trên trang tìm kiếm sau đợt đổi tên index.
Nhóm phát triển ánh xạ @Id của ProductDocument bằng mã SKU có thể đổi, khiến cùng một sản phẩm tạo ra hai document khi hệ thống quản trị thay mã.
Một dịch vụ tìm khách theo số điện thoại nhưng trường này được mapping là text thay vì keyword, khiến tra cứu chính xác những số có dấu cộng và khoảng trắng cho kết quả không như mong đợi.
Đội vận hành bật dynamic mapping cho document đơn hàng từ nhiều đối tác, khiến cùng trường amount lúc được nhận dạng số và lúc là chuỗi làm bulk indexing thất bại.
Ứng dụng định nghĩa @Field cho ngày phát hành theo format của Java nhưng index Elasticsearch có định dạng khác, khiến các sản phẩm lịch sử không đọc được sau khi nâng cấp entity.
Nhóm gắn @Field(type=Text) vào thuộc tính mã bưu chính, khiến yêu cầu lọc theo mã đầy đủ không hoạt động giống điều kiện khớp nguyên giá trị.
Một bảng tìm kiếm khách chứa tên tiếng Việt có dấu nhưng index được tạo bằng analyzer mặc định, khiến người dùng gõ không dấu khó tìm được hồ sơ tương ứng.
Đội thêm thuộc tính danh sách biến thể màu sắc dưới dạng object array, nhưng bộ lọc màu và kích thước ghép điều kiện từ hai biến thể khác nhau vẫn trả sản phẩm.
Ứng dụng dự kiến dùng nested mapping cho danh sách mặt hàng trong đơn nhưng index cũ lưu object thông thường, khiến truy vấn nested bị lỗi trên dữ liệu đang có.
Nhóm thay đổi mapping của trường status từ keyword sang text trong entity mà không chuyển dữ liệu sang index mới, khiến kết quả filter khác giữa pod mới và pod cũ.
Một service Spring Data Elasticsearch dùng @Setting với cấu hình số shards riêng nhưng index đã được tạo tự động trước đó, khiến môi trường production không có cấu trúc như tài liệu triển khai.
Đội phát triển khai báo trường giá có nhiều chữ số thập phân nhưng mapping dùng kiểu số không phù hợp, khiến phép lọc khoảng giá có sai lệch ở các mặt hàng đắt tiền.
Ứng dụng dùng @Field với tên trường Java mới và tên field Elasticsearch cũ, nhưng custom converter bỏ qua alias đó khiến kết quả tìm kiếm trả null cho một thuộc tính quan trọng.
Nhóm lưu địa chỉ giao hàng trong document sản phẩm thử nghiệm rồi tái sử dụng entity cho public search, khiến thông tin cá nhân có nguy cơ xuất hiện trong response API.
Một dự án ánh xạ dữ liệu vị trí cửa hàng bằng chuỗi tọa độ thông thường, nhưng tính năng tìm cửa hàng trong bán kính cần một kiểu dữ liệu không được index hiện tại hỗ trợ.
Đội nhập ngày khuyến mãi từ các quốc gia với offset khác nhau, nhưng converter Java mất thông tin múi giờ khiến truy vấn ngày bắt đầu bán sai theo vùng.
Một service lưu lịch sử giá trong list embedded document, nhưng mỗi lần giá đổi phải index lại document sản phẩm lớn khiến chi phí cập nhật tăng theo số phiên bản.
Nhóm dùng @Document cho hai loại entity cùng tên index nhưng mapping của một trường trùng tên không tương thích, khiến một API đọc được document còn API kia lỗi chuyển đổi.
Ứng dụng tự sinh document ID mới ở mỗi lần chạy batch đồng bộ từ PostgreSQL, khiến một sản phẩm được lập chỉ mục nhiều lần sau khi job retry.
Đội đánh dấu một field chứa JSON động trong entity nhưng không giới hạn số khóa có thể xuất hiện, khiến index bị phình mappings khi đối tác gửi metadata tùy ý.
Một service tạo document khi không có trường category nhưng Java entity khai báo bắt buộc, khiến truy vấn dữ liệu cũ thất bại khi deserializer khởi tạo đối tượng.
Nhóm nâng thư viện Spring Data Elasticsearch và dùng converter cũ cho trường enum mới, khiến những document được ghi bởi phiên bản khác không thể chuyển sang giá trị Java hợp lệ.
Ứng dụng cần sắp xếp tên sản phẩm theo thứ tự chữ cái nhưng dùng trường text đã analyze, khiến yêu cầu sort báo lỗi hoặc cho thứ tự không phản ánh tên đầy đủ.
Đội lưu nhiều đơn vị đo độ dài trong cùng trường số và bỏ metadata đơn vị, khiến tính năng lọc theo khoảng không thể so sánh dữ liệu giữa các nguồn.
Nhóm lưu tags theo thứ tự ưu tiên do người bán sắp xếp, nhưng giao diện lấy danh sách tags qua terms aggregation nên không thể suy ra thứ tự ưu tiên từ kết quả thống kê.
Một công ty tạo index với field nested cho địa chỉ chi nhánh nhưng kết quả SearchHit chỉ lấy document cha, khiến UI không biết địa chỉ con nào thực sự khớp điều kiện.
Ứng dụng dùng ElasticsearchRepository để tìm sản phẩm theo thương hiệu, nhưng derived query được xây từ thuộc tính Java không trùng tên field thực trong index.
Nhóm thêm method repository tìm theo mô tả sản phẩm rồi kiểm tra bằng một cụm từ trùng nguyên, khiến lỗi analyzer không lộ ra cho truy vấn tự nhiên của người dùng.
Một API dùng ElasticsearchRepository.findAll để export hàng triệu document, khiến JVM phải giữ lượng kết quả lớn và ảnh hưởng các request tìm kiếm đồng thời.
Đội triển khai repository phân trang bằng Pageable với page number rất sâu, khiến truy vấn gặp giới hạn result window và người dùng không thể đến trang dữ liệu cũ.
Ứng dụng dùng method findByStatus để lọc đơn đang chờ nhưng field status được analyze, khiến filter chính xác không trả đúng số lượng theo dashboard.
Nhóm ghép nhiều repository methods cho các tùy chọn filter, nhưng một yêu cầu vừa có tên, vùng và khoảng giá không được biểu diễn đầy đủ bằng các phương thức hiện tại.
Một service gọi repository.save sau khi nhận DTO thiếu một số field đã lưu, khiến bản document mới ghi đè và mất thông tin từ lần nhập trước.
Đội dự định dùng repository.save để chỉ cập nhật một thuộc tính của document, nhưng API đọc trước đó quá cũ nên những thay đổi mới của luồng khác bị ghi đè.
Nhóm có hai ElasticsearchRepository cùng trỏ một alias nhưng Java entity mapping khác nhau, khiến bản ghi do job ghi không được API chuyển đổi chính xác.
Một service triển khai reactive Elasticsearch repository cho WebFlux nhưng controller gọi block trên publisher, khiến vài request tìm kiếm dài làm nghẽn event loop.
Đội tạo derived query theo mã khách trên một trường nested nhưng không dùng ngữ nghĩa truy vấn nested, khiến API tìm đơn theo khách trả các kết quả sai.
Ứng dụng dùng count từ repository để hiển thị tổng số mặt hàng sau mỗi lần nhập, nhưng bản ghi vừa ghi chưa refresh nên dashboard lệch so với kết quả từ database nguồn.
Nhóm chạy integration test chỉ với mock ElasticsearchRepository trả dữ liệu đúng thứ tự, khiến lỗi sort theo keyword thực tế không được phát hiện trước production.
Một dịch vụ cần trả điểm relevance cùng từng document, nhưng API hiện chỉ dùng repository trả entity nên không có metadata score cần cho phân tích xếp hạng.
Đội giới hạn quyền tìm kiếm ở tầng controller nhưng repository cũng được gọi từ consumer nền, khiến truy vấn của consumer bỏ qua điều kiện tenant bắt buộc.
Một ứng dụng tạo nhiều phương thức truy vấn repository dựa trên tên field động, nhưng khi refactor entity một phương thức không còn phù hợp với index mà test không phát hiện.
Nhóm muốn lấy những document khớp nhiều điều kiện và highlight phần trùng, nhưng thiết kế repository hiện tại chỉ trả danh sách entity nên giao diện thiếu thông tin match.
Ứng dụng xây tìm kiếm sản phẩm qua ElasticsearchOperations, nhưng NativeQuery không chứa filter tenant khiến người dùng có thể thấy document doanh nghiệp khác.
Đội phát triển dùng ElasticsearchOperations.search cho truy vấn match nhưng chỉ lấy content của SearchHit, khiến điểm relevance và sort values bị loại khỏi response.
Một service tạo NativeQuery để tìm các đơn trong khoảng ngày nhưng field time zone của dữ liệu không nhất quán, khiến những đơn gần nửa đêm bị lọc sai.
Nhóm dùng ElasticsearchOperations để thực hiện bulk operations theo sự kiện kho nhưng không xác định xử lý từng item lỗi, khiến một phần sản phẩm không được index dù batch báo kết thúc.
Một API tìm kiếm đặt minimumShouldMatch trong bool query nhưng các điều kiện must và should không được phân tích rõ, khiến số sản phẩm được trả nhiều hơn bộ lọc khách chọn.
Đội dùng ElasticsearchOperations để truy vấn qua alias nhiều index phiên bản, nhưng mapping field status giữa hai index khác nhau khiến truy vấn gặp kết quả không nhất quán.
Một chương trình import gọi ElasticsearchOperations.indexOps để tạo index mới nhưng cấu hình template khác production, khiến analyzer của index tự tạo không đúng như kỳ vọng.
Nhóm thêm dynamic criteria vào NativeQuery theo filter từ URL, nhưng giá trị null được đưa vào điều kiện truy vấn và làm một phân khúc dữ liệu không được hiển thị.
Ứng dụng cần cập nhật một field bằng ElasticsearchOperations nhưng hiện lấy document rồi ghi toàn bộ, khiến hai tác vụ đồng thời ghi đè field của nhau.
Đội chạy update by query để sửa metadata cho sản phẩm cũ nhưng không xác định cách xử lý version conflict, khiến chỉ một phần tập dữ liệu được thay đổi.
Một service dùng ElasticsearchOperations để lấy dữ liệu theo Scroll API cho export nhưng không đóng scroll context, khiến cluster giữ search context lâu sau khi job kết thúc.
Nhóm tìm kiếm dữ liệu lịch sử bằng Point in Time nhưng client giữ PIT quá lâu trong quá trình export, làm tài nguyên node tăng theo số job đồng thời.
Ứng dụng đặt refresh policy bắt buộc sau mọi lệnh save qua Operations, khiến thời gian index tăng cao khi có hàng nghìn sự kiện mỗi giây.
Đội dùng ElasticsearchOperations để đếm theo nhiều điều kiện nhưng áp kết quả count như số bản ghi chính xác từ SQL, khiến dashboard gây nhầm lẫn khi index chưa đồng bộ.
Một service đọc response ElasticsearchOperations từ một index có document sai mapping nhưng chuyển đổi exception thành danh sách rỗng, khiến người dùng tưởng không có dữ liệu.
Nhóm thử trực tiếp truy vấn DSL trong Kibana cho kết quả đúng, nhưng query được xây trong Java bỏ thiếu một nhánh filter khiến API trả khác công cụ quản trị.
Ứng dụng dùng ElasticsearchOperations tìm kiếm nhiều index bằng wildcard nhưng không kiểm tra index nào chứa dữ liệu nhạy cảm, khiến API nội bộ có thể trả document ngoài phạm vi.
Đội triển khai một analyzer riêng cho tên sản phẩm tiếng Việt nhưng index cũ được tạo trước khi analyzer được khai báo, khiến kết quả tìm kiếm khác nhau giữa dữ liệu mới và cũ.
Người dùng nhập tên thương hiệu không dấu vào full-text search, nhưng analyzer chỉ chuẩn hóa chữ hoa thường nên không khớp tên thương hiệu có dấu trong index.
Một dịch vụ tìm sản phẩm theo tên chứa dấu gạch nối và ký hiệu model, nhưng tokenizer tách mã như các từ tự nhiên khiến mã chính xác khó được tìm thấy.
Nhóm cấu hình stopwords cho tìm kiếm tiếng Việt nhưng từ quan trọng trong tên loại sản phẩm bị loại bỏ, khiến truy vấn ngắn trả tập kết quả quá rộng.
Ứng dụng hỗ trợ từ đồng nghĩa giữa các tên gọi sản phẩm nhưng synonym rules được cập nhật sau khi tạo index, khiến dữ liệu và truy vấn áp dụng quy tắc không đồng đều.
Đội dùng stemmer cho mô tả tiếng Anh nhưng sản phẩm có nội dung tiếng Việt và tiếng Nhật cùng index, khiến kết quả full-text không đồng nhất giữa ngôn ngữ.
Một website cần tìm cả mã SKU chính xác lẫn mô tả gần đúng trong cùng ô nhập, nhưng hai loại dữ liệu bị analyze chung và làm độ chính xác giảm.
Nhóm viết test tìm kiếm chỉ dùng chữ ASCII trong khi tên khách thực có dấu kết hợp Unicode, khiến lỗi normalization không được phát hiện trước deploy.
Một ứng dụng tìm thông tin sản phẩm theo phrase query nhưng người dùng nhập khoảng trắng và dấu câu khác trong tên, khiến tài liệu hợp lệ bị bỏ sót.
Đội dùng fuzzy matching mặc định cho mọi truy vấn, khiến mã thiết bị gần giống nhau bị trộn và khách mở nhầm hướng dẫn kỹ thuật.
Một cửa hàng muốn tự động gợi ý tên sản phẩm khi người dùng gõ từng ký tự, nhưng thiết kế index chỉ hỗ trợ match query thông thường khiến trải nghiệm autocomplete chậm.
Nhóm bật prefix query trên trường text dài để làm autocomplete, khiến chi phí truy vấn tăng mạnh khi hàng trăm người gõ đồng thời.
Ứng dụng xây search-as-you-type nhưng dữ liệu import qua một index thiếu multi-fields, khiến môi trường mới trả gợi ý khác dữ liệu trước migration.
Một API tìm kiếm nội dung PDF nhưng extractor đưa cả header và footer lặp lại vào text, khiến BM25 ưu tiên những tài liệu nhiều mẫu chân trang hơn nội dung chính.
Nhóm dùng cùng analyzer cho bước index và query nhưng việc nâng cấp plugin khiến chúng không còn xử lý ký tự tiếng Việt như trước, làm relevance thay đổi sau restart.
Một trang hỗ trợ khách hàng cần tìm cả dạng viết tắt và tên đầy đủ của sản phẩm, nhưng chỉ một số tài liệu có alias nên người dùng tìm bỏ sót hướng dẫn cũ.
Ứng dụng lưu title và description dưới một field tổng hợp để tìm nhanh, nhưng đội sản phẩm muốn title được trọng số cao hơn và không có tín hiệu tách nguồn match.
Đội thử tokenizer bằng các tên sản phẩm ngắn nhưng dữ liệu thật chứa tiếng Việt kèm mã kỹ thuật và số seri, khiến nhiều term bị tách ngoài kỳ vọng.
Một dịch vụ tìm địa chỉ theo tên đường có dấu nháy và dấu gạch, nhưng dữ liệu từ nhiều hệ thống được chuẩn hóa khác nhau nên các truy vấn giống nhau về nghĩa không khớp.
Nhóm thay analyzer của một text field trực tiếp trên index đang có dữ liệu nhưng bỏ qua việc index cũ vẫn giữ tokens đã được phân tích theo quy tắc trước.
Một website cho phép tìm bằng từ khóa rất phổ biến như 'máy', nhưng số document khớp quá lớn khiến relevance kém và thời gian truy vấn tăng đáng kể.
Đội dùng wildcard query ở đầu chuỗi cho tìm kiếm tên thương hiệu với hàng triệu term, khiến CPU tăng đột biến khi một người dùng gửi bộ lọc mở rộng.
Một ứng dụng có nội dung đa ngôn ngữ nhưng field language chỉ được gắn ở document, còn truy vấn luôn dùng analyzer của tiếng Anh khiến kết quả tiếng Việt xếp hạng thấp.
Nhóm đo chất lượng tìm kiếm bằng vài truy vấn do chính developer viết, nên lỗi tìm synonym, lỗi chính tả và tiếng địa phương của khách thật không được thấy.
Một service triển khai query string query với nội dung do người dùng nhập, khiến các ký tự mang nghĩa cú pháp truy vấn tạo lỗi parsing hoặc kết quả ngoài mong muốn.
Đội chuyển từ tìm kiếm match trên một field sang multi_match trên nhiều field, nhưng tài liệu chứa nhiều từ trong field phụ được xếp cao hơn kết quả khớp tên chính xác.
Một trang thương mại điện tử có hàng triệu sản phẩm nhưng sort theo giá được ưu tiên trước score, khiến người dùng gõ tên hàng cụ thể vẫn thấy nhiều hàng không liên quan.
Nhóm điều chỉnh boost cho title và brand nhưng không có bộ truy vấn đánh giá trước sau, khiến sản phẩm đúng thương hiệu nhưng sai loại thường xuất hiện đầu trang.
Ứng dụng dùng BM25 ranking mặc định cho mô tả dài ngắn khác nhau, khiến những trang tài liệu lặp lại từ khóa xuất hiện trên tài liệu giải quyết đúng vấn đề.
Đội thêm ưu tiên hàng đang có tồn kho vào score, nhưng trạng thái kho đồng bộ muộn nên sản phẩm đã hết hàng vẫn đứng đầu kết quả tìm kiếm.
Nhóm muốn kết hợp mức độ phổ biến và relevance, nhưng lượt xem lớn của sản phẩm không khớp từ khóa làm những kết quả đúng bị đẩy xuống nhiều trang.
Một hệ thống dùng function_score để ưu tiên sản phẩm mới nhưng công thức ranking làm hàng mới bất kể nội dung luôn vượt hàng cũ có độ khớp cao.
Đội áp điều kiện filter giá trong scoring query không phù hợp, khiến score thay đổi khi khách chỉ bật bộ lọc không liên quan tới mức độ khớp văn bản.
Ứng dụng cần xếp hạng tài liệu theo độ mới nhưng thời gian cập nhật đến từ hai hệ thống dùng timezone khác nhau, khiến một số tài liệu cũ được coi là mới.
Nhóm ghi log điểm score cuối cùng nhưng không lưu lý do match trên title, brand hay description, khiến nhóm sản phẩm không giải thích được vì sao kết quả sai đứng đầu.
Một website dùng rescoring trên top kết quả để tăng chất lượng nhưng giới hạn cửa sổ rescore thấp hơn số kết quả khách có thể xem, khiến thứ hạng thay đổi bất thường giữa các trang.
Đội dùng custom sort theo mức độ ưu tiên kinh doanh và dùng score để tie-break, khiến các tài liệu ít liên quan nhưng được gắn ưu tiên cao luôn lên đầu.
Một ứng dụng tìm tên người có nhiều cách viết nhưng tăng fuzziness quá cao, khiến khách có thể nhận thông tin của người khác có họ tên tương tự.
Nhóm muốn cá nhân hóa ranking theo địa bàn nhưng đặt tọa độ người dùng vào truy vấn không ràng buộc quyền, khiến dữ liệu vị trí nhạy cảm xuất hiện trong search logs.
Một API áp boost cho trường tags do người bán tự khai báo, khiến người bán thêm hàng trăm tag không liên quan để đẩy sản phẩm lên đầu kết quả.
Đội dùng should clauses để cộng điểm theo sở thích nhưng thiếu filter quyền bắt buộc, khiến document không được phép xem vẫn lọt vào danh sách khớp.
Ứng dụng thay đổi công thức ranking trước chiến dịch lớn nhưng chỉ đánh giá click-through rate, không kiểm tra trường hợp truy vấn chính xác mã sản phẩm bị xếp sau.
Nhóm định đo nDCG cho một bộ truy vấn có đánh giá người dùng nhưng nhãn mức độ liên quan chưa được gắn theo phiên bản index, khiến so sánh hai lần triển khai không tin cậy.
Một trang tìm kiếm tin tức ưu tiên document theo thời điểm xuất bản nhưng metadata của bài được cập nhật thường xuyên, khiến bài cũ liên tục nổi lên như tin mới.
Đội sắp xếp nhiều tiêu chí giữa score và timestamp mà không giữ tie-breaker ổn định, khiến người dùng lật trang thấy kết quả lặp hoặc bị bỏ qua.
Ứng dụng lọc sản phẩm theo danh mục bằng term query nhưng category đã được index bằng text analyzer, khiến bộ lọc danh mục có tên gồm nhiều từ bị lệch.
Một website cho phép lọc theo giá từ min đến max nhưng một phần document lưu giá bằng tiền tệ khác, khiến bộ lọc trả những sản phẩm ngoài ngân sách khách.
Nhóm xây bool query với nhiều filter vùng, tình trạng còn hàng và thương hiệu, nhưng một nhánh điều kiện dùng should làm dữ liệu ngoài vùng vẫn xuất hiện.
Một dịch vụ tìm đơn theo userId và status nhưng cùng index chứa dữ liệu nhiều tenant; query chỉ lọc userId nên trùng định danh giữa tenant gây lộ thông tin.
Đội dùng terms query với danh sách hàng chục nghìn ID từ hệ thống phân quyền, khiến truy vấn gặp giới hạn kích thước và tiêu tốn nhiều tài nguyên.
Ứng dụng tìm cửa hàng gần vị trí người dùng nhưng dữ liệu tọa độ được lưu đảo thứ tự kinh độ và vĩ độ, khiến một số cửa hàng bị đặt sai vùng địa lý.
Nhóm áp geo_distance filter trong API nhưng một số document thiếu geo_point, khiến báo cáo số cửa hàng hiển thị ít hơn danh mục gốc mà không có cảnh báo.
Một hệ thống hiển thị đơn đã giao bằng range query ngày giao, nhưng thời điểm ở index dùng UTC còn bộ lọc UI dùng múi giờ chi nhánh làm thiếu đơn ở ranh giới ngày.
Đội lọc tài liệu chỉ có field hợp đồng bằng exists query nhưng field đó chứa null hoặc giá trị rỗng khác nhau giữa nguồn, khiến cách tính document hợp lệ không nhất quán.
Ứng dụng cần tìm đơn có nhiều item thỏa đồng thời điều kiện màu và size, nhưng truy vấn thông thường khớp điều kiện trên hai item khác nhau trong cùng document.
Nhóm tạo filter khách có quyền xem sản phẩm cho từng region nhưng dùng cache kết quả query không bao gồm region, khiến người dùng thấy dữ liệu ngoài khu vực.
Một API dùng must_not để bỏ trạng thái đã xóa, nhưng các document lịch sử thiếu field trạng thái lại không được xử lý như quy tắc nghiệp vụ mong muốn.
Đội thêm nested filter theo biến thể sản phẩm nhưng aggregation đếm sản phẩm cha như số lượng biến thể, khiến bảng bộ lọc hiển thị số liệu không khớp.
Ứng dụng lọc theo brand keyword có phân biệt chữ hoa, nhưng dữ liệu nguồn viết hoa khác nhau và normalizer chưa thống nhất giữa các index.
Nhóm cần lọc sản phẩm theo khoảng kích thước có đơn vị cm và inch, nhưng index chỉ lưu một số đo mà không ghi đơn vị nên kết quả sai ở một phần danh mục.
Một hệ thống kiểm tra quyền tài liệu ở API gateway nhưng batch export truy vấn trực tiếp ElasticsearchOperations, khiến cùng index có hai con đường với chính sách lọc quyền khác nhau.
Đội áp filter theo chi nhánh trong truy vấn nhưng alias của môi trường production trỏ tới index cũ không chứa trường chi nhánh, khiến kết quả giảm mạnh sau phát hành.
Ứng dụng dùng negative filter cho trạng thái khuyến mãi nhưng dữ liệu từ đối tác mới có một giá trị enum ngoài danh sách cũ, khiến tài liệu không được phân loại chính xác.
Nhóm phát triển trang bộ lọc theo thương hiệu bằng terms aggregation nhưng số lượng brand lớn hơn size mặc định, khiến nhiều thương hiệu ít phổ biến không xuất hiện.
Một ứng dụng tính số mặt hàng theo category bằng terms aggregation trên text field, khiến truy vấn không hoạt động như thống kê theo giá trị danh mục đầy đủ.
Đội thống kê doanh số từng ngày bằng date_histogram nhưng không đặt timezone của thị trường, khiến doanh thu vào giờ giao ngày bị chuyển sang ngày khác.
Nhóm hiển thị biểu đồ giá trung bình qua avg aggregation nhưng dữ liệu giá chưa chuẩn hóa tiền tệ, khiến kết quả tổng hợp không có ý nghĩa kinh doanh.
Một hệ thống đếm số khách duy nhất bằng cardinality aggregation và dùng trực tiếp kết quả như số chính xác để tính thưởng, khiến báo cáo có sai lệch so với đối soát.
Đội tạo biểu đồ hàng tháng theo date_histogram nhưng một số tháng không có giao dịch và UI mặc định bỏ bucket rỗng, khiến đường biểu diễn bị đứt.
Ứng dụng chạy aggregation trên hàng triệu tags có độ phân biệt cao mà không đánh giá bộ nhớ, khiến request dashboard chạm giới hạn tài nguyên cluster.
Nhóm muốn phân trang toàn bộ giá trị nhóm thương hiệu nhưng chỉ dùng terms aggregation với size lớn, khiến những nhóm có thứ tự cuối khó truy xuất ổn định.
Một dịch vụ báo cáo theo category và country dùng multi-level aggregation nhưng số lượng bucket kết hợp quá lớn làm response tăng mạnh trong đợt cao điểm.
Đội xây thống kê lỗi theo nested items của hóa đơn nhưng quên ngữ nghĩa nested aggregation, khiến số hàng lỗi khác tổng số hóa đơn lỗi.
Ứng dụng dùng reverse_nested để đếm document đơn hàng chứa item lỗi, nhưng báo cáo vẫn cộng số item thay vì số đơn và kết quả vượt số đơn thực.
Nhóm dùng filter aggregation để so sánh đơn thành công và thất bại nhưng điều kiện không giống điều kiện query chính, khiến tổng các nhóm không khớp số dòng hiển thị.
Một dashboard dùng sum aggregation cho trường số tiền mà vài document chứa giá trị không hợp lệ từ dữ liệu nhập, khiến doanh số tổng thiếu một phần giao dịch.
Đội muốn tính tỷ lệ chuyển đổi qua pipeline aggregation nhưng nguồn dữ liệu có độ trễ index khác nhau, khiến tử số và mẫu số không cùng thời điểm.
Ứng dụng hiển thị top 10 sản phẩm bằng aggregation nhưng dữ liệu bán hàng được cập nhật trễ qua Kafka, khiến kết quả khác dashboard lấy từ database nguồn.
Nhóm cần phân nhóm địa điểm theo geotile grid để hiển thị bản đồ, nhưng nhiều tài liệu không có tọa độ chuẩn khiến vùng mật độ bị sai.
Một dịch vụ dùng bucket selector để loại nhóm quá ít sản phẩm, nhưng client vẫn lấy count tổng như chưa lọc nên số nhóm trên dashboard không khớp.
Đội chạy composite aggregation nhiều trang cho export facet nhưng không giữ after key đúng giữa các lần gọi, khiến báo cáo bị lặp hoặc thiếu một số bucket.
Ứng dụng đặt tên aggregation trùng giữa các nhánh truy vấn khác nhau, khiến mã Java đọc kết quả từ response sai nhánh và trả số liệu không tương ứng.
Nhóm lấy percentile latency từ dữ liệu log đã lấy mẫu mà không công bố phạm vi sample, khiến bảng SLO bị hiểu như phản ánh toàn bộ request.
Một hệ thống lọc dữ liệu theo tenant rồi tính global aggregation trên index chung mà không kiểm soát phạm vi, khiến số lượng tổng có thể tiết lộ dữ liệu tenant khác.
Đội cấu hình endpoint aggregation không giới hạn khoảng thời gian, khiến một truy vấn lịch sử nhiều năm tiêu tốn CPU và heap làm chậm tìm kiếm giao dịch tức thời.
Ứng dụng hiển thị thống kê kho theo nhiều warehouse nhưng cùng document chứa nested warehouses, khiến bucket count sai nếu chưa xét cấp nested tương ứng.
Một công ty import 2 triệu sản phẩm bằng repository.save từng bản ghi, khiến số HTTP requests và thời gian index quá lớn so với cửa sổ cập nhật dữ liệu.
Nhóm chuyển sang Bulk API nhưng chỉ kiểm tra HTTP response của toàn batch, khiến hàng nghìn document lỗi mapping bị bỏ qua khi job báo thành công.
Một batch bulk indexing gửi dữ liệu từ CSV với một document có kiểu giá sai, khiến những item còn lại thành công nhưng hệ thống không biết bản ghi nào cần sửa.
Đội chọn kích thước bulk batch rất lớn để tăng throughput, khiến payload và bộ nhớ worker tăng mạnh và cluster từ chối một số yêu cầu.
Ứng dụng chạy nhiều bulk workers đồng thời mà không giới hạn backpressure, khiến hàng đợi xử lý phía Elasticsearch tăng và ứng dụng gặp lỗi 429 trong giờ cao điểm.
Nhóm dùng retry cho toàn bộ bulk batch khi một số item thất bại, khiến các item thành công bị ghi lại và gây chi phí index không cần thiết.
Một pipeline nhập sự kiện dùng document ID ngẫu nhiên sau mỗi retry, khiến cùng một sản phẩm có nhiều phiên bản hiện diện trong index và kết quả tìm kiếm bị trùng.
Đội tạo document ID theo SKU mà không kèm tenant, khiến hai doanh nghiệp dùng cùng mã sản phẩm ghi đè tài liệu của nhau trong index chung.
Ứng dụng bulk indexing sau một lần timeout và không biết server đã xử lý bao nhiêu item, khiến dashboard tiến độ nhập dữ liệu khác số document thực.
Nhóm dùng bulk update với dữ liệu từ nhiều nguồn nhưng không giữ version của entity, khiến sự kiện đến trễ ghi đè thông tin mới hơn.
Một batch nhập dữ liệu chỉ chạy thành công với index không có refresh, nhưng người dùng kiểm tra kết quả ngay sau job lại thấy thiếu sản phẩm trong vài giây.
Đội cấu hình refresh cho từng item của bulk import để đáp ứng kiểm tra ngay, khiến throughput index sụt mạnh và tài nguyên cluster tăng bất thường.
Ứng dụng tạo ingest pipeline để chuẩn hóa tên sản phẩm nhưng một trường lạ trong JSON làm processor lỗi, khiến các item thất bại không được ghi vào nơi cách ly.
Nhóm bổ sung pipeline enrich metadata từ bộ dữ liệu khác, nhưng index lookup không được cập nhật theo thay đổi mới nên nhiều document nhận thuộc tính cũ.
Một service chạy update_by_query trên toàn index để sửa giá sau chiến dịch, khiến các request tìm kiếm trên cùng cluster gặp độ trễ lớn trong giờ làm việc.
Đội nhập dữ liệu theo các file lớn song song nhưng thiếu checkpoint sau từng chunk, khiến khi job crash nó không biết phần nào đã được index thành công.
Ứng dụng vừa xóa sản phẩm hết hàng vừa chạy bulk import, nhưng thứ tự sự kiện không được kiểm soát nên một sản phẩm đã xóa xuất hiện trở lại.
Nhóm dùng Bulk API để xóa nhiều document theo danh sách ID nhưng tên index alias thay đổi giữa lúc job chạy, khiến một phần thao tác nhắm vào index cũ.
Một doanh nghiệp có dữ liệu tăng nhanh nhưng dùng một index cho tất cả năm, khiến thao tác reindex phục vụ mapping mới mất nhiều giờ và ảnh hưởng các API.
Đội chuyển dữ liệu sản phẩm sang index phiên bản mới nhưng không kiểm chứng checksum và số document sau bulk import, khiến alias được đổi khi bản mới còn thiếu dữ liệu.
Ứng dụng cần tăng tốc bulk load bằng cách giảm replica tạm thời nhưng quy trình vận hành không ghi nhận khi nào phải khôi phục cấu hình độ bền cho index.
Nhóm định kỳ tải 20 GB tài liệu vào Elasticsearch từ job Spring Boot, nhưng việc giữ toàn bộ DTO trong bộ nhớ trước bulk làm JVM hết heap.
Một service dùng ingestion từ Kafka và bulk queue nội bộ, nhưng Kafka consumer commit offset trước khi bulk item báo thành công nên một số event bị mất khi Elasticsearch quá tải.
Đội tối ưu Bulk API dựa vào số document mỗi request nhưng không xét độ lớn byte khác nhau giữa văn bản và dữ liệu nhị phân, khiến một số batch quá lớn.
Ứng dụng lập chỉ mục từ database PostgreSQL mỗi đêm nhưng cập nhật của khách xảy ra ngay sau thời điểm snapshot, khiến trang tìm kiếm phản ánh giá cũ suốt ngày.
Nhóm dùng outbox events để cập nhật Elasticsearch sau khi database commit, nhưng worker crash sau khi index thành công và trước đánh dấu đã gửi nên một event được phát lại.
Một hệ thống đồng bộ từ MySQL CDC sang Elasticsearch nhưng không lưu vị trí nguồn và version ổn định, khiến khi connector restart một số document bị cập nhật ngược.
Đội ghi sản phẩm vào database và Elasticsearch trong một request HTTP rồi kỳ vọng cả hai cùng rollback khi một bên lỗi, khiến dữ liệu hai hệ thống lệch.
Ứng dụng dùng event ProductDeleted để xóa document khỏi index nhưng một số bản tin nằm trong DLQ, khiến sản phẩm đã xóa trong database vẫn còn kết quả tìm kiếm.
Nhóm nhận ProductUpdated sau ProductDeleted do xử lý bất đồng bộ, khiến document bị xóa được tạo lại trong index khi không có kiểm tra version.
Một service đồng bộ tên khách từ CRM sang Elasticsearch nhưng không có khóa định danh ổn định sau khi khách đổi email, khiến một người xuất hiện thành nhiều document.
Đội triển khai tìm kiếm sản phẩm near-real-time nhưng UI vẫn kỳ vọng read-after-write giống PostgreSQL, khiến khách sửa tên rồi tìm ngay tưởng việc lưu thất bại.
Ứng dụng cập nhật tồn kho trong PostgreSQL vài lần mỗi giây nhưng gửi mọi thay đổi sang Elasticsearch, khiến backlog indexing tăng dù khách chỉ cần trạng thái kho hiện tại.
Nhóm sử dụng bảng denormalized ở Elasticsearch chứa giá và thông tin nhà cung cấp, nhưng chỉ có event giá được phát nên địa chỉ nhà cung cấp thay đổi không cập nhật trong document.
Một dịch vụ đồng bộ dữ liệu khách hàng sang index chung nhưng sự kiện không có tenantId, khiến document bị đưa vào phạm vi truy vấn sai.
Đội cần backfill tài liệu lịch sử vào index đang nhận cập nhật mới nhưng job chạy dữ liệu snapshot cũ, khiến sản phẩm mới bị ghi đè bởi bản lịch sử.
Ứng dụng chạy backfill trên toàn bộ bảng nguồn trong lúc Debezium CDC cũng phát event, nhưng không có cách xác định thời điểm bắt đầu áp dụng stream sau snapshot.
Nhóm đánh dấu sync job hoàn tất dựa trên số event đã đọc từ queue mà không đối chiếu số item bulk thành công, khiến dashboard báo đồng bộ đủ dù index còn thiếu.
Một hệ thống có cơ chế retry event lỗi nhưng không giới hạn số lần và không lưu nguyên nhân, khiến một document có mapping sai làm consumer bận liên tục.
Đội quản trị sửa lỗi index bằng cách chạy reindex trực tiếp nhưng không khóa hay điều phối luồng cập nhật online, khiến trong quá trình chuyển đổi có tài liệu bị mất thay đổi.
Ứng dụng thay đổi category của sản phẩm nhưng chỉ cập nhật field ở document chính, trong khi index gợi ý autocomplete được đồng bộ riêng nên hai tính năng hiển thị khác nhau.
Nhóm nhận event từ Kafka theo nhiều partitions, nhưng các cập nhật cùng productId không được đưa về một key ổn định khiến thứ tự cuối trong index bị sai.
Một service xử lý xóa dữ liệu cá nhân từ database thành công nhưng quên xóa document tìm kiếm và snapshot index cũ, khiến yêu cầu xóa chưa được hoàn thành.
Đội vận hành đo độ trễ đồng bộ từ timestamp event tới thời điểm indexing, nhưng đồng hồ nguồn bị lệch và biểu đồ báo cả giá trị âm khó diễn giải.
Ứng dụng cần đối chiếu document tồn tại trong Elasticsearch và bản ghi nguồn, nhưng quy trình chỉ so sánh tổng count nên không phát hiện cặp thiếu và trùng có số lượng bù nhau.
Nhóm tạo job làm mới index khi nâng mapping nhưng dữ liệu mới từ API không được nhân đôi sang index đích trong lúc backfill, khiến alias chuyển xong thiếu sự kiện vừa phát sinh.
Một website dùng index alias products-current cho tìm kiếm nhưng một tác vụ viết nhầm vào alias chỉ đọc trong lúc chuyển index, khiến sản phẩm mới không được đồng bộ sau deployment.
Đội nâng mapping cho trường giá bằng cách tạo index mới, nhưng alias đọc được đổi trước khi ứng dụng ghi hỗ trợ cấu trúc mới nên một số bulk items bị lỗi.
Ứng dụng sử dụng alias nhiều index để tìm đơn lịch sử nhưng hai index có cùng field name với mapping khác nhau, khiến sort và aggregation theo field đó không nhất quán.
Nhóm tạo versioned index để rollback nhanh nhưng không giữ khả năng đọc document schema mới bằng Java entity cũ, khiến rollback code vẫn lỗi serialization.
Một service sử dụng tên index có ngày hiện tại để lưu logs nhưng môi trường chạy ở UTC còn công cụ báo cáo dùng giờ địa phương, khiến dữ liệu giờ giao ngày nằm ở index bất ngờ.
Đội đặt rollover cho index log nhưng consumer ghi theo tên index vật lý cũ, khiến index mới không nhận dữ liệu và shard cũ tiếp tục phình lớn.
Ứng dụng lưu lịch sử đơn hàng cần retention nhiều năm nhưng index lifecycle áp chính sách xóa giống log kỹ thuật, khiến dữ liệu đối soát bị mất quá sớm.
Nhóm chuyển index sang tier lưu trữ chậm theo ILM nhưng API vẫn hứa trả kết quả vài trăm mili giây cho mọi năm dữ liệu, khiến SLO không còn đạt.
Một hệ thống dùng data stream cho log thời gian nhưng document nhập ngược không có timestamp phù hợp, khiến pipeline từ chối dữ liệu hoặc tìm sai khoảng.
Đội phân bổ quá nhiều primary shards cho index nhỏ mới tạo, khiến cluster tăng chi phí metadata và heap khi hệ thống có hàng nghìn tenant.
Ứng dụng dùng một primary shard cho index tìm kiếm phát triển tới hàng trăm GB, khiến query và restore mất lâu khi load tăng đột ngột.
Nhóm tăng replica count để tăng tốc tìm kiếm nhưng cluster thiếu node và tài nguyên disk, khiến một số shards không được phân bổ trong rollout.
Một service ghi document dung lượng lớn vào index chung với sản phẩm nhỏ, khiến thao tác search trả nhiều dữ liệu không cần thiết và network tăng.
Đội muốn split index sản phẩm nhưng lựa chọn số primary shards ban đầu không phù hợp kế hoạch tăng quy mô, khiến việc mở rộng cần reindex phức tạp.
Ứng dụng chạy trên cluster nhiều availability zones nhưng shard allocation không phản ánh zone awareness, khiến một sự cố vùng ảnh hưởng nhiều bản sao dữ liệu hơn dự kiến.
Nhóm thêm shard routing theo tenant để giảm fan-out nhưng một tenant quá lớn dồn dữ liệu vào ít shard, khiến latency của tenant đó tăng.
Một doanh nghiệp dùng index riêng cho mỗi khách nhỏ với số shards mặc định cao, khiến cluster phải quản lý quá nhiều shards khi số tenant tăng nhanh.
Đội chuyển dữ liệu cũ từ hot tier sang warm tier nhưng dashboard vẫn gửi truy vấn toàn bộ lịch sử trên mọi request, khiến thời gian đáp ứng biến động theo dữ liệu cũ.
Ứng dụng mở một truy vấn wildcard trên hàng nghìn index logs cho mỗi thao tác hỗ trợ, khiến số shard được truy cập vượt ngân sách tìm kiếm.
Nhóm triển khai Snapshot Lifecycle Management nhưng không thử restore index và alias vào cluster thay thế, khiến khả năng phục hồi chỉ tồn tại trên báo cáo.
Một service chỉ kiểm tra cluster health màu xanh mà không đánh giá disk watermarks, khiến đến giờ cao điểm Elasticsearch chặn một số thao tác ghi dù API vẫn hoạt động.
Đội mở rộng disk volume cho Elasticsearch nodes nhưng không đo độ phân tán shards, khiến một số node còn gần ngưỡng watermark và vẫn gây lỗi indexing.
Một API dùng search_after để đọc danh sách sản phẩm rất sâu nhưng không giữ sort tie-breaker ổn định, khiến trang tiếp theo bỏ sót hoặc lặp document.
Nhóm dùng point-in-time cho export để giữ snapshot tìm kiếm, nhưng job không đóng PIT sau khi client hủy khiến search contexts tích lũy theo ngày.
Ứng dụng ghép search_after với việc thay đổi filter giữa các trang từ UI, khiến token phân trang trả kết quả không còn tương ứng với tiêu chí hiện tại.
Đội dùng from/size cho trang thứ một nghìn của nhật ký bảo mật, khiến API gặp giới hạn deep pagination dù các trang đầu hoạt động tốt.
Một service dùng sort trên trường thời gian mà nhiều document có cùng giá trị, khiến các trang kết quả thay đổi thứ tự khi refresh diễn ra giữa hai request.
Nhóm muốn xuất toàn bộ kết quả bằng Scroll API nhưng cố giữ scroll context nhiều giờ trong khi cluster còn phục vụ search trực tuyến, khiến tài nguyên giảm dần.
Ứng dụng đọc tài liệu sau khi index mới xong nhưng không tính đến refresh interval, khiến bài test thỉnh thoảng không thấy document vừa tạo.
Đội kiểm thử update theo thứ tự hai HTTP requests nhưng production có nhiều writers và thay đổi xảy ra đồng thời, khiến cùng document bị ghi đè ngoài dự kiến.
Một service cập nhật document dựa trên sequence number và primary term nhưng không xử lý xung đột, khiến API chỉ trả lỗi chung thay vì thể hiện trạng thái đồng thời.
Nhóm dùng retry_on_conflict rất cao cho hot document lượt xem, khiến một SKU nổi tiếng bị cập nhật lặp và tiêu tốn tài nguyên lớn dù nghiệp vụ chỉ cần số liệu gần đúng.
Ứng dụng cần bảo đảm người dùng thấy nội dung sửa mới nhất trong một phiên, nhưng yêu cầu tìm kiếm có thể đi đến replica chưa refresh như kỳ vọng của đội sản phẩm.
Đội trả tổng số kết quả của một truy vấn sâu mà không xét cách Elasticsearch giới hạn theo dõi hits, khiến UI hiển thị con số không chính xác cho tập rất lớn.
Một dịch vụ tìm sản phẩm theo phân vùng index thời gian nhưng user chọn khoảng lớn, khiến request fan-out nhiều shards và độ trễ tăng mạnh.
Nhóm gửi multi-search để giảm số HTTP calls nhưng mỗi subquery quá nặng, khiến một request tổng hợp làm search thread pool quá tải.
Ứng dụng dùng nested queries lồng nhiều mức với hàng nghìn nested objects mỗi document, khiến bộ lọc theo biến thể sản phẩm tiêu tốn CPU tăng cao.
Đội chạy query trên một trường có giá trị keyword rất dài và cardinality cao, khiến terms aggregation dùng nhiều bộ nhớ và chạm circuit breaker.
Một service dùng runtime field để tính giá đã giảm cho từng document rồi sort trên toàn tập, khiến query nhiều triệu sản phẩm mất vài giây thay vì phản hồi tức thời.
Nhóm cho phép wildcard query tự do theo input khách, khiến một mẫu ký tự bắt đầu bằng wildcard tạo truy vấn quá tốn tài nguyên trên index lớn.
Ứng dụng cấu hình search timeout nhưng vẫn gửi nhiều truy vấn tương tự đồng thời khi khách liên tục gõ, khiến search queue tăng dù client đã hủy request cũ.
Đội tối ưu tốc độ tìm kiếm bằng cache nhưng query có timestamp hiện tại trong điều kiện lọc, khiến tỷ lệ cache hit rất thấp dù khách dùng cùng bộ lọc.
Một service chạy aggregation nặng trên cluster đang bulk index nhưng không giới hạn song song, khiến cả dashboard và API chính bị chậm trong giờ cao điểm.
Nhóm áp index sorting cho dữ liệu theo thời gian nhưng ingest pipeline ghi timestamp sai, khiến tác động tối ưu không phản ánh truy vấn thực tế.
Ứng dụng lưu trường description dài trong source và trả nguyên _source cho mỗi hit dù UI chỉ cần tên và giá, khiến network egress và latency tăng mạnh.
Đội tắt lưu source cho index để tiết kiệm dung lượng nhưng ứng dụng cần dựng lại DTO đầy đủ cho API, khiến việc đọc document không còn đáp ứng chức năng.
Một cluster Elasticsearch có nhiều node nhưng request routing cố định vào một coordinator, khiến coordinator quá tải trong khi các data nodes còn tài nguyên.
Nhóm bật request cache cho aggregation nhưng dữ liệu được refresh liên tục từ hệ thống bán hàng, khiến cache ít hiệu quả và dashboard vẫn chậm.
Một service gọi nhiều queries giống nhau trong một request vì mỗi widget tự tra Elasticsearch, khiến tổng số query tăng tuyến tính theo số thành phần UI.
Đội deploy hai phiên bản Spring Data Elasticsearch với Java client khác nhau, khiến một bản phát hành gọi API không được Elasticsearch cluster hiện tại hỗ trợ.
Ứng dụng kết nối cluster Elasticsearch qua HTTPS nhưng JVM không tin CA nội bộ, khiến pod mới lỗi bắt tay TLS trong khi phiên cũ còn giữ kết nối.
Nhóm để Elasticsearch endpoint mở qua internet cho service tiện truy cập, nhưng không giới hạn danh tính client khiến dữ liệu tìm kiếm có nguy cơ bị xem hoặc sửa trái phép.
Một dịch vụ dùng tài khoản Elasticsearch có quyền quản trị index cho chức năng tìm kiếm chỉ đọc, khiến sự cố lộ credential có thể làm mất dữ liệu cả cluster.
Đội lưu mật khẩu Elasticsearch trong application.yml đóng gói vào artifact, khiến tài khoản production đi theo bản build được chia sẻ cho nhà thầu.
Ứng dụng hỗ trợ nhiều tenant trong cùng index nhưng chỉ kiểm tra tenantId ở endpoint tìm kiếm, trong khi endpoint export dùng ElasticsearchOperations trực tiếp và bỏ filter.
Nhóm dựa vào field-level security để ẩn số điện thoại nhưng API highlight vẫn trả fragment có thông tin nhạy cảm từ field không được kiểm soát.
Một hệ thống có nhiều role tìm kiếm nhưng chỉ lọc quyền tại Java service sau khi nhận hits, khiến tổng hit count và aggregation có thể tiết lộ quy mô dữ liệu không được phép xem.
Đội cho phép truy vấn Elasticsearch DSL tùy ý từ khách hàng bên ngoài, khiến người dùng có thể chạy những aggregation và script tốn tài nguyên ngoài phạm vi sản phẩm.
Ứng dụng lưu log chứa token và thông tin cá nhân trong Elasticsearch nhưng lifecycle policy dài hơn thời hạn lưu giữ được doanh nghiệp phê duyệt.
Nhóm triển khai API tìm kiếm tài liệu theo tenant nhưng kết quả từ index alias lọc không phù hợp với mọi đường đọc, khiến một client nội bộ thấy tài liệu của nhóm khác.
Một service ghi query text và toàn bộ _source vào slow log để điều tra relevance, khiến nội dung hợp đồng bí mật xuất hiện trong nơi nhiều nhân viên có quyền đọc.
Đội vận hành xoay Elasticsearch API key trong secret manager nhưng HTTP client vẫn giữ key cũ trong bean singleton, khiến các request sau thời điểm thu hồi nhận lỗi xác thực.
Ứng dụng truy cập Elasticsearch qua private endpoint nhưng network policy ở namespace mới chặn egress tới các node, khiến chỉ một phần pod lỗi kết nối.
Nhóm thay phiên bản Elasticsearch server cùng lúc nâng Spring Data library nhưng test chỉ mock repository, khiến vấn đề tương thích client chỉ xuất hiện ở production.
Một service dùng query string do người dùng nhập cho tìm kiếm log nội bộ nhưng không giới hạn thời gian và độ phức tạp, khiến một request có thể tiêu tốn CPU bất thường.
Đội triển khai field-level masking trong API nhưng document còn chứa các bản sao text tổng hợp đã index trước khi mask, khiến tìm kiếm vẫn làm lộ từ khóa nhạy cảm.
Ứng dụng báo health UP khi web server Spring Boot chạy nhưng cluster Elasticsearch không có shard phục vụ index chính, khiến người dùng chỉ thấy lỗi tìm kiếm sau đăng nhập.
Nhóm theo dõi CPU và heap Elasticsearch nhưng không đo indexing failures trong Bulk API, khiến dữ liệu tìm kiếm thiếu dần dù tài nguyên hệ thống còn bình thường.
Đội vận hành chỉ theo dõi tổng số document Elasticsearch mà không so với nguồn dữ liệu, khiến một đợt mất event và một đợt ghi trùng che lấp nhau.
Một service đo p95 latency search nhưng không tách thời gian Elasticsearch, chuyển đổi DTO và network, khiến nhóm tối ưu nhầm thành phần gây chậm.
Nhóm chỉ đo thời gian phản hồi truy vấn khớp một SKU, nhưng phần lớn người dùng tìm phrase tự nhiên nhiều từ nên benchmark không phản ánh tải thật.
Ứng dụng ghi metric theo từng query text của người dùng làm tag Prometheus, khiến cardinality và bộ nhớ hệ thống giám sát tăng rất nhanh.
Đội dùng Elasticsearch slow log để điều tra query tốn tài nguyên nhưng threshold quá cao nên những truy vấn medium chậm với tần suất lớn không được phát hiện.
Một cluster có unassigned shards sau khi mất node nhưng API chỉ kiểm tra HTTP 200 từ cluster, khiến cảnh báo phục hồi dữ liệu không đến đội trực.
Nhóm cấu hình alert theo average search latency trong khi một index giao dịch có p99 rất cao, khiến SLA của khách quan trọng bị vi phạm mà không có cảnh báo.
Ứng dụng log search request ID nhưng không chuyển correlation ID từ gateway đến Bulk API và job đồng bộ, khiến không thể truy vết một document bị thiếu.
Đội nhận cảnh báo search thread pool rejection nhưng không liên kết với dashboard aggregation đang chạy, khiến việc điều tra nguồn truy vấn tăng tải bị kéo dài.
Một hệ thống thấy chỉ số cache hit cao nhưng kết quả tìm kiếm vừa thay đổi mapping có relevance sai, khiến metric hiệu năng che khuất vấn đề chất lượng dữ liệu.
Nhóm muốn kiểm tra độ trễ đồng bộ sản phẩm bằng timestamp nguồn và timestamp index, nhưng timezone và clock skew của các hệ thống làm biểu đồ sai.
Ứng dụng đếm số tài liệu đã xóa bằng lệnh delete nhưng dashboard storage vẫn cao vì segment chưa được merge, khiến đội vận hành đánh giá sai tài nguyên cần thiết.
Đội chỉ theo dõi lượng request Elasticsearch tổng nhưng không phân loại tìm kiếm, aggregation, indexing và reindex, khiến workload nền bị nhầm với traffic khách hàng.
Một service dùng circuit breaker khi Elasticsearch chậm nhưng fallback trả danh sách sản phẩm từ cache quá cũ, khiến API thông báo dữ liệu còn hàng không đúng thực tế.
Nhóm bật retry tự động cho các search requests khi cluster quá tải mà không có backoff, khiến lượng truy vấn tăng và thời gian hồi phục kéo dài hơn.
Đội tích hợp Testcontainers Elasticsearch cho integration test nhưng container dùng mapping mặc định khác index template production, khiến các truy vấn keyword và nested không được kiểm thử đúng.
Ứng dụng kiểm thử ElasticsearchRepository bằng một mock trả entity nhưng không thử analyzer của index, khiến lỗi tìm kiếm tên tiếng Việt chỉ được phát hiện sau release.
Nhóm tạo test ElasticsearchOperations trên index có vài chục document, khiến deep pagination và giới hạn result window không được kiểm chứng trước khi dữ liệu tăng.
Một service thử bulk indexing bằng dữ liệu đều đúng schema, nhưng production có vài item sai kiểu khiến lỗi từng phần của bulk response không được kiểm tra.
Đội QA viết test để tìm một cụm từ chính xác duy nhất, nhưng không đánh giá độ chính xác top-k cho từ đồng nghĩa và lỗi gõ thường gặp của người dùng.
Ứng dụng cần bảo đảm query phân quyền theo tenant nhưng test chỉ dùng một tenant, khiến thiếu filter trong một nhánh aggregation vẫn PASS.
Nhóm tạo fixtures cho nested product variants nhưng chỉ một variant mỗi document, khiến truy vấn khớp chéo thuộc tính hai variant không được phát hiện.
Đội chạy test search-after với dữ liệu có timestamp khác nhau hoàn toàn, nên không phát hiện lỗi lặp kết quả khi nhiều document có cùng sort values.
Ứng dụng kiểm thử version migration bằng cách tạo index mới trống nhưng không thử reindex dữ liệu lịch sử, khiến một số document cũ lỗi conversion sau alias swap.
Nhóm dùng test profile chạy Elasticsearch không có TLS hoặc auth, nhưng production bắt buộc API key nên lỗi credential rotation không được mô phỏng.
Một service kiểm tra full-text ranking bằng assert rằng có kết quả mà không xác minh thứ tự quan trọng, khiến thay đổi boost làm sản phẩm liên quan tụt xuống mà CI vẫn xanh.
Đội test tìm sản phẩm sau index ngay lập tức không chờ refresh và đôi lúc bài test FAIL dù document đã được ghi thành công, khiến CI không ổn định.
Ứng dụng dựng dashboard aggregation từ vài sản phẩm nhưng không có test cardinality lớn hoặc bucket limit, khiến lỗi bộ nhớ chỉ xuất hiện trên dữ liệu thật.
Nhóm kiểm tra đồng bộ PostgreSQL sang Elasticsearch khi tất cả event đến đúng thứ tự, nhưng production có replay và event đến muộn khiến bản ghi cũ ghi đè.
Đội tích hợp test chỉ gọi repository.save rồi findById, khiến lỗi ingest pipeline, analyzer và alias mà production sử dụng không nằm trong phạm vi kiểm thử.
Một bộ test chạy song song dùng chung tên index products-test và mỗi test tự xóa index sau khi xong, khiến những test khác thỉnh thoảng gặp index missing.
Nhóm nâng Elasticsearch client Java nhưng chỉ chạy unit tests không khởi tạo cluster thật, khiến API tương thích với phiên bản cũ không còn hoạt động sau deploy.
Ứng dụng dùng tài liệu mẫu không có ký tự đặc biệt, khiến lỗi tokenizer với ký hiệu mã hàng, emoji và dấu tiếng Việt bị bỏ sót.
Đội chạy performance test chỉ đo throughput indexing mà không chạy search đồng thời, khiến cấu hình bulk tưởng tốt lại làm latency khách hàng vượt SLA.
Nhóm kiểm thử thao tác xóa dữ liệu cá nhân chỉ xác nhận document biến mất khỏi index hiện tại mà không đối soát alias, snapshot và bản index đang chờ thay thế.
Một service rollback sang phiên bản Java cũ sau khi đã đổi mapping Elasticsearch, nhưng kế hoạch rollback chưa được thử với document mới mang field và type của bản phát hành sau.
Đội QA mô phỏng node Elasticsearch dừng khi không có bulk job nào chạy, khiến không phát hiện các item đã nhận nhưng client timeout và quyết định retry sai.
Một API gợi ý từ khóa chạy tốt trên laptop với vài nghìn document, nhưng chưa có benchmark prefix search trên index hàng triệu sản phẩm và lượng truy cập cao.
Nhóm so sánh số hit trong test và production nhưng test không bật cùng refresh interval, khiến kết luận về lỗi đồng bộ không dựa trên hành vi thực.
Một hệ thống tìm kiếm toàn văn có cả dữ liệu nhạy cảm, nhưng bộ kiểm thử quyền chỉ gọi endpoint trả document mà không kiểm tra highlight và aggregation có rò thông tin.
Đội triển khai index sản phẩm theo từng quốc gia nhưng CI không chạy test qua alias đa vùng, khiến yêu cầu tìm sản phẩm quốc tế chỉ lỗi sau khi thêm một thị trường.
Một chương trình backfill hàng triệu document được thử trên một Elasticsearch node, nhưng chưa mô phỏng cluster nhiều shards và mất kết nối giữa bulk import nên khả năng khôi phục khó đoán.
Nhóm triển khai cập nhật synonyms ở search-time nhưng không kiểm tra phiên bản cấu hình analyzer được áp dụng giữa các nodes, khiến cùng truy vấn cho kết quả khác trong rollout.
Đội cần khôi phục tìm kiếm sau sự cố cluster nhưng chỉ thử restart Spring Boot, không kiểm tra restore snapshot, alias và khả năng tái đồng bộ event còn tồn.
Một tổ chức yêu cầu truy vết vì sao một hợp đồng được trả trong top 5 kết quả, nhưng phiên bản index, analyzer, query boost và dữ liệu quyền không được ghi cùng correlation ID.
