Những đặc điểm nào của dữ liệu và mẫu truy vấn khiến bạn ưu tiên NoSQL hơn cơ sở dữ liệu quan hệ?
Bốn họ cơ sở dữ liệu NoSQL khóa–giá trị, tài liệu, cột rộng và đồ thị khác nhau như thế nào về mô hình lưu trữ và cách truy vấn?
Bạn thu thập những mẫu truy cập dữ liệu nào trước khi chọn loại cơ sở dữ liệu NoSQL cho một hệ thống mới?
Bạn cân nhắc thế nào giữa yêu cầu đọc nhanh, ghi nhiều, duyệt quan hệ và truy vấn phân tích khi lựa chọn mô hình NoSQL?
Những ràng buộc nghiệp vụ nào khiến bạn phải đánh giá hỗ trợ transaction và tính nhất quán trước khi dùng NoSQL?
Bạn đánh giá ưu điểm và chi phí của schema linh hoạt trong NoSQL đối với tiến hóa dữ liệu như thế nào?
Bạn phân biệt khả năng mở rộng theo chiều ngang với khả năng tăng tài nguyên trên một máy chủ trong hệ NoSQL như thế nào?
Bạn chọn cách tổ chức dữ liệu phục vụ truy vấn chủ đạo thay vì tái sử dụng mô hình chuẩn hóa quan hệ như thế nào?
Bạn xác định các thực thể cần đồng tồn tại trong một đơn vị đọc hoặc ghi dựa trên ranh giới nghiệp vụ ra sao?
Bạn nhận diện những trường hợp nên duy trì nhiều bản biểu diễn cùng một dữ liệu để phục vụ các truy vấn khác nhau như thế nào?
Bạn phân tích rủi ro mất đồng bộ khi denormalization khiến một thay đổi phải cập nhật nhiều bản ghi như thế nào?
Trong cơ sở dữ liệu khóa–giá trị, bạn thiết kế key để tránh va chạm và vẫn hỗ trợ tra cứu theo nghiệp vụ ra sao?
Bạn mô hình hóa dữ liệu phiên đăng nhập, giỏ hàng hoặc bộ đếm bằng kho khóa–giá trị như thế nào?
Bạn lựa chọn cấu trúc value và kích thước bản ghi trong kho khóa–giá trị dựa trên các thao tác đọc và cập nhật như thế nào?
Khi cần tìm kiếm theo một thuộc tính không nằm trong key, bạn đánh giá những giải pháp nào cho mô hình khóa–giá trị?
Bạn quyết định thời gian TTL và chính sách hết hạn của bản ghi khóa–giá trị để cân bằng tính mới và chi phí bộ nhớ ra sao?
Bạn phân biệt cache với nguồn dữ liệu chính khi sử dụng hệ thống khóa–giá trị bằng những yêu cầu nào về độ bền và phục hồi?
Bạn xử lý cache miss, cache stampede và dữ liệu cache cũ trong một dịch vụ có lưu lượng cao như thế nào?
Khi cập nhật bộ đếm hoặc trạng thái phiên đồng thời, bạn lựa chọn thao tác nguyên tử hay cơ chế đồng bộ nào?
Bạn phát hiện và xử lý hot key khiến một nhóm yêu cầu tập trung vào cùng một bản ghi như thế nào?
Bạn thiết kế quy ước version cho giá trị lưu trong kho khóa–giá trị để nâng cấp ứng dụng không gây lỗi đọc ra sao?
Trong cơ sở dữ liệu tài liệu, những tiêu chí nào giúp bạn quyết định nhúng dữ liệu vào document hay tham chiếu sang document khác?
Bạn tổ chức dữ liệu đơn hàng và các dòng hàng trong mô hình document để cân bằng thao tác đọc với cập nhật như thế nào?
Bạn quản lý sự khác biệt về cấu trúc giữa các document khi ứng dụng thay đổi schema theo thời gian ra sao?
Bạn thiết kế index cho truy vấn lọc theo nhiều trường, sắp xếp và phân trang trong kho tài liệu như thế nào?
Bạn cân nhắc tác động của document lớn hoặc mảng nhúng tăng liên tục đến hiệu năng cập nhật như thế nào?
Bạn xử lý truy vấn nhiều collection hoặc quan hệ chéo trong cơ sở dữ liệu tài liệu theo hướng nào?
Những yêu cầu nhất quán nào khiến bạn chọn transaction thay vì xử lý bất đồng bộ khi cập nhật nhiều document?
Bạn triển khai thao tác ghi lặp lại an toàn và kiểm soát xung đột cập nhật cùng một document ra sao?
Bạn xây dựng chiến lược di chuyển dữ liệu khi đổi định dạng document mà vẫn hỗ trợ phiên bản ứng dụng cũ như thế nào?
Bạn đánh giá index, bộ nhớ và chi phí ghi khi một collection tăng mạnh về số lượng document như thế nào?
Mô hình cột rộng tổ chức partition key, clustering key và các hàng dữ liệu như thế nào để phục vụ truy vấn?
Bạn thiết kế bảng cột rộng bắt đầu từ truy vấn cần hỗ trợ thay vì bắt đầu từ sơ đồ thực thể như thế nào?
Partition key trong cơ sở dữ liệu cột rộng tác động thế nào đến phân phối tải và số node phải tham gia một truy vấn?
Bạn lựa chọn clustering key để hỗ trợ truy vấn theo khoảng thời gian và thứ tự kết quả như thế nào?
Bạn nhận diện các truy vấn phải quét nhiều partition và xác định hướng thiết kế lại mô hình cột rộng ra sao?
Bạn xử lý hiện tượng partition quá lớn hoặc một partition nhận phần lớn lưu lượng ghi như thế nào?
Bạn thiết kế dữ liệu sự kiện theo thời gian với bucket hoặc phân vùng theo thời gian trong hệ cột rộng như thế nào?
Tombstone và cơ chế xóa dữ liệu có thể tác động thế nào đến truy vấn và công việc bảo trì của hệ cột rộng?
Bạn đánh giá đánh đổi giữa ghi nhanh, compaction và độ trễ đọc trong các hệ thống sử dụng cấu trúc LSM như thế nào?
Bạn chọn mức nhất quán đọc và ghi trong cơ sở dữ liệu cột rộng dựa trên SLA và số replica như thế nào?
Bạn so sánh mô hình đồ thị với tài liệu và cột rộng khi bài toán cần truy vấn quan hệ nhiều bước như thế nào?
Bạn xác định node, relationship và property từ các quy tắc nghiệp vụ như thế nào để mô hình hóa đồ thị?
Bạn thiết kế truy vấn tìm đường đi hoặc hàng xóm nhiều cấp sao cho tránh duyệt lan rộng không kiểm soát ra sao?
Bạn phát hiện và giảm ảnh hưởng của supernode khi một đỉnh đồ thị có số lượng quan hệ rất lớn như thế nào?
Bạn đánh giá chi phí phân vùng một đồ thị có nhiều cạnh nối xuyên shard so với phân vùng dữ liệu khóa–giá trị như thế nào?
Khi nghiệp vụ vừa cần truy vấn theo thuộc tính vừa cần duyệt quan hệ, bạn cân nhắc index và mô hình dữ liệu đồ thị ra sao?
Bạn lựa chọn giữa một cơ sở dữ liệu đồ thị chuyên dụng và mô hình quan hệ trong hệ khác dựa trên những phép đo nào?
Bạn xác định khóa phân vùng hoặc shard key dựa trên tính phân bố, độ biến động và mẫu truy cập như thế nào?
Bạn giải thích cách consistent hashing hoặc cơ chế định tuyến shard giúp phân phối dữ liệu và yêu cầu ra sao?
Bạn dự đoán các vấn đề phát sinh khi thêm node hoặc tái phân bố shard trên cụm đang chịu tải như thế nào?
Bạn thiết kế khóa và chiến lược phân vùng cho dữ liệu có tenant lớn nhỏ rất khác nhau như thế nào?
Bạn phân biệt replication và sharding về mục đích tăng khả năng sẵn sàng, dung lượng và thông lượng như thế nào?
Bạn xác định giới hạn của việc tăng replica nếu ứng dụng bị nghẽn bởi thao tác ghi hoặc khóa dữ liệu như thế nào?
Bạn giải thích CAP theorem trong bối cảnh phân vùng mạng thực tế mà hệ thống phải tiếp tục xử lý yêu cầu như thế nào?
Bạn dùng PACELC để cân nhắc độ trễ và tính nhất quán khi mạng hoạt động bình thường như thế nào?
Bạn phân biệt strong consistency, eventual consistency và các bảo đảm nhất quán theo phiên qua tình huống nghiệp vụ nào?
Khi thao tác ghi đã thành công nhưng lượt đọc tiếp theo chưa thấy dữ liệu mới, bạn chẩn đoán nguyên nhân và xử lý ra sao?
Bạn lựa chọn cơ chế quorum đọc và ghi theo mục tiêu nhất quán, độ trễ và khả năng chịu lỗi như thế nào?
Trong hệ multi-leader hoặc ghi đồng thời trên nhiều replica, bạn giải quyết xung đột dữ liệu theo quy tắc nghiệp vụ nào?
Bạn thiết kế phiên bản dữ liệu hoặc optimistic concurrency control để tránh ghi đè mất cập nhật như thế nào?
Bạn phân biệt tính nguyên tử trong một bản ghi, một partition và nhiều bản ghi phân tán khi thiết kế transaction như thế nào?
Bạn xây dựng quy trình bù trừ và idempotency khi một nghiệp vụ phải cập nhật nhiều nguồn dữ liệu không có transaction chung như thế nào?
Bạn phân loại những tình huống chấp nhận dữ liệu cũ tạm thời và những tình huống bắt buộc đọc được ghi mới nhất dựa trên tiêu chí nghiệp vụ nào?
Bạn lập kịch bản thử nghiệm phân vùng mạng, replica chậm hoặc node mất kết nối để xác nhận hành vi nhất quán ra sao?
Bạn xây dựng tiêu chí lựa chọn giữa kho khóa–giá trị, tài liệu, cột rộng và đồ thị cho hệ thống gợi ý, thương mại hoặc phân tích sự kiện như thế nào?
Bạn đánh giá tính phù hợp của một sản phẩm NoSQL dựa trên truy vấn, công cụ vận hành, SDK, backup và giới hạn dịch vụ như thế nào?
Bạn xác định khối lượng dữ liệu, tốc độ tăng trưởng và kích thước bản ghi đại diện trước khi thử nghiệm sản phẩm như thế nào?
Bạn thiết kế workload kiểm thử có tỷ lệ đọc/ghi, phân bố khóa và mức đồng thời giống production như thế nào?
Bạn chọn các chỉ số throughput, p95/p99 latency, tỷ lệ lỗi và mức dùng tài nguyên để đánh giá phương án NoSQL ra sao?
Bạn phân biệt giới hạn hiệu năng của ứng dụng khách, mạng và cơ sở dữ liệu trong kết quả benchmark như thế nào?
Bạn dùng dữ liệu lệch phân bố và hot partition trong benchmark để phát hiện giới hạn mà tải đồng đều che giấu ra sao?
Bạn so sánh độ trễ và thông lượng khi thay đổi consistency level hoặc số replica trong một bài kiểm thử như thế nào?
Bạn đo tác động của compaction, garbage collection, rebalance và backup lên hiệu năng khi hệ thống đang chịu tải ra sao?
Bạn lập kế hoạch sao lưu và khôi phục cho hệ phân tán để bảo đảm bản sao có thể phục hồi nhất quán như thế nào?
Bạn theo dõi replication lag, dung lượng shard, hot key, lỗi timeout và độ trễ truy vấn để phát hiện nghẽn NoSQL ra sao?
Bạn kiểm soát TTL, compaction, retention và tốc độ tăng dung lượng để tránh hệ thống cạn đĩa như thế nào?
Bạn tổ chức xác thực, phân quyền và mã hóa dữ liệu khi cơ sở dữ liệu NoSQL chạy trên nhiều node hoặc nhiều vùng như thế nào?
Bạn xác định rủi ro từ việc dùng nhiều hệ quản trị NoSQL trong cùng kiến trúc và cách giảm chi phí đồng bộ dữ liệu như thế nào?
Khi hệ thống gặp lỗi đọc hoặc ghi sau failover, bạn thu thập bằng chứng nào để phân biệt lỗi định tuyến, replica và client retry?
Bạn thiết kế phương án chuyển đổi từ cơ sở dữ liệu hiện tại sang NoSQL với backfill, dual-write và kiểm chứng dữ liệu như thế nào?
Bạn xây dựng tiêu chí chấp nhận cuối cùng nào để chứng minh một lựa chọn NoSQL đáp ứng tải thực tế, mức nhất quán và khả năng phục hồi?
