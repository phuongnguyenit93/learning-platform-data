# Kiểm tra giao tiếp với cơ sở dữ liệu, bộ nhớ đệm và hàng đợi

Một ứng dụng thường dựa vào nhiều thành phần để lưu trữ, truy xuất và truyền dữ liệu. Cơ sở dữ liệu giữ trạng thái có tính bền vững; bộ nhớ đệm giúp truy cập dữ liệu nhanh hơn; hàng đợi và hệ thống nhắn tin cho phép các thành phần xử lý công việc bất đồng bộ. Những thành phần này có thể hoạt động tốt khi kiểm thử riêng lẻ nhưng vẫn gây lỗi khi kết nối với ứng dụng: dữ liệu được ghi không đầy đủ, cache trả về giá trị cũ, thông điệp bị xử lý lặp hoặc công việc biến mất sau khi consumer gặp sự cố.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, kiểm tra giao tiếp với cơ sở dữ liệu, bộ nhớ đệm và hàng đợi tập trung vào hợp đồng dữ liệu, trạng thái, tính nhất quán, xử lý lỗi và khả năng phục hồi tại ranh giới tích hợp. Mục tiêu là chứng minh các thành phần phối hợp đúng trong điều kiện bình thường và khi có lỗi, đồng thời bảo đảm người dùng nhận được kết quả chính xác và có thể giải thích.

## 1. Xác định ranh giới giao tiếp và mục tiêu kiểm thử

### Nhận diện thành phần và luồng dữ liệu

Trước khi viết kịch bản, hãy xác định thành phần nào gửi yêu cầu, thành phần nào nhận, dữ liệu đi theo chiều nào và nơi nào giữ trạng thái có thẩm quyền.

| Thành phần | Vai trò thường gặp | Câu hỏi cần xác thực |
|---|---|---|
| Cơ sở dữ liệu | Lưu trạng thái bền vững, quan hệ, giao dịch và lịch sử | Ghi/đọc có đúng schema, ràng buộc, transaction và quyền không? |
| Bộ nhớ đệm | Giữ bản sao dữ liệu để giảm độ trễ hoặc tải truy vấn | Dữ liệu có được lấy đúng khóa, hết hạn và làm mới đúng lúc không? |
| Hàng đợi | Lưu công việc hoặc thông điệp chờ xử lý | Thông điệp có được phát, nhận, xác nhận, thử lại và xử lý đúng không? |
| Broker hoặc nền tảng nhắn tin | Định tuyến, lưu giữ và phân phối thông điệp | Topic, partition, subscription, quyền và chính sách lưu giữ có đúng không? |
| Ứng dụng hoặc worker | Tạo yêu cầu, xử lý dữ liệu và cập nhật trạng thái | Có xử lý đúng phản hồi, lỗi, timeout và thông điệp lặp không? |

Một luồng thực tế có thể đi qua nhiều thành phần. Ví dụ, người dùng tạo đơn hàng; ứng dụng ghi đơn vào cơ sở dữ liệu; một sự kiện được đưa vào hàng đợi; worker trừ tồn kho; cache được làm mới; dịch vụ thông báo gửi xác nhận. Kiểm thử từng thành phần độc lập không đủ để chứng minh trạng thái cuối nhất quán.

Hãy lập sơ đồ luồng dữ liệu, xác định điểm đồng bộ và bất đồng bộ, nơi phát sinh tác dụng phụ, nơi có thể retry và nơi lưu trạng thái có thẩm quyền. Sơ đồ cần thể hiện các nhánh lỗi và bước phục hồi quan trọng.

~~~mermaid
flowchart LR
    U["Yêu cầu từ người dùng"] --> API["Ứng dụng / API"]
    API --> DB[("Cơ sở dữ liệu")]
    API --> Q[["Hàng đợi / Broker"]]
    Q --> W["Worker xử lý"]
    W --> DB
    API --> C[("Bộ nhớ đệm")]
    W --> C
    W --> N["Dịch vụ thông báo"]
~~~

Sơ đồ chỉ là ví dụ. Trong hệ thống thật, cache có thể được cập nhật theo sự kiện, worker có thể gọi dịch vụ khác và hàng đợi có thể được chia theo partition. Hãy xác minh kiến trúc và luồng thực tế với chủ sở hữu thành phần.

### Xác định mục tiêu cần kiểm chứng

Các mục tiêu phổ biến gồm:

- Dữ liệu được ghi và đọc đúng, không mất hoặc nhân đôi ngoài quy tắc nghiệp vụ.
- Ràng buộc, transaction và mức cô lập bảo vệ trạng thái trước cập nhật đồng thời.
- Cache trả về dữ liệu đúng phạm vi, không vượt quá thời hạn hoặc mức cũ được chấp nhận.
- Thông điệp được phát và tiêu thụ đúng schema, routing key, thứ tự và chính sách lưu giữ.
- Lỗi tạm thời được retry có giới hạn; lỗi không thể xử lý được đưa vào luồng điều tra phù hợp.
- Consumer có thể phục hồi sau khi dừng giữa chừng mà không làm mất hoặc nhân đôi tác dụng phụ.
- Quyền truy cập và dữ liệu nhạy cảm được bảo vệ ở mọi ranh giới.
- Log, metric và trace đủ để theo dõi một giao dịch qua nhiều thành phần.

Mỗi mục tiêu cần gắn với hành trình và hậu quả cụ thể. Ví dụ, với thao tác thanh toán, ưu tiên tính đúng đắn và tính lặp an toàn. Với dữ liệu hiển thị gần thời gian thực, độ trễ đồng bộ và độ cũ của cache có thể quan trọng hơn.

### Phân biệt kiểm thử đơn vị với kiểm thử tích hợp

Kiểm thử đơn vị có thể mock database, cache hoặc broker để xác minh logic cục bộ, chẳng hạn ứng dụng tạo đúng câu lệnh hoặc xử lý phản hồi lỗi. Tuy nhiên, mock không chứng minh câu lệnh chạy được trên database thật, cấu hình serializer tương thích với broker hay chính sách TTL của cache hoạt động như dự kiến.

Kiểm thử tích hợp cần kết nối với thành phần thật hoặc môi trường đại diện để xác minh hợp đồng tại ranh giới. Một chiến lược cân bằng thường dùng:

- Unit test cho quy tắc và nhánh xử lý cục bộ.
- Contract hoặc component integration test cho schema, API, query, serializer và cấu hình.
- Integration test với database, cache hoặc broker thật trong môi trường cô lập.
- System test cho hành trình đi qua nhiều thành phần.
- Kiểm thử phục hồi và vận hành cho lỗi, retry, backlog và khôi phục.

Không phải mọi lần chạy đều cần toàn bộ hạ tầng thật. Hãy chọn phương pháp nhỏ nhất có thể tạo bằng chứng đáng tin cậy cho rủi ro đang xét.

## 2. Kiểm tra giao tiếp với cơ sở dữ liệu

### Xác minh schema, kiểu dữ liệu và ánh xạ

Ứng dụng và database phải thống nhất về cấu trúc và ý nghĩa dữ liệu. Kiểm thử cần xác minh:

- Tên bảng, cột, kiểu dữ liệu, độ dài và khả năng nhận giá trị null.
- Khóa chính, khóa ngoại, unique constraint và check constraint.
- Giá trị mặc định, sequence hoặc cơ chế sinh định danh.
- Quy tắc mã hóa, collation, phân biệt hoa thường và chuẩn hóa.
- Độ chính xác số thập phân, tiền tệ, múi giờ và kiểu ngày giờ.
- Ánh xạ giữa kiểu dữ liệu trong ứng dụng và kiểu dữ liệu lưu trữ.
- Hành vi khi schema thay đổi hoặc migration được áp dụng.

Ví dụ, nếu ứng dụng dùng kiểu số dấu phẩy động để lưu tiền, sai số biểu diễn có thể làm tổng tiền lệch. Với dữ liệu tài chính, cần chọn kiểu thập phân và quy tắc làm tròn phù hợp, sau đó kiểm tra cả dữ liệu lưu và dữ liệu trả về.

Cũng cần kiểm tra trường hợp schema thay đổi nhưng một phiên bản ứng dụng cũ vẫn đang chạy. Trong triển khai cuốn chiếu, hai phiên bản có thể cùng truy cập database. Migration cần tương thích trong giai đoạn chuyển tiếp, hoặc có quy trình phát hành đảm bảo không có phiên bản cũ sử dụng schema mới theo cách không hỗ trợ.

### Kiểm tra CRUD và truy vấn

Với các thao tác tạo, đọc, cập nhật và xóa, hãy xác minh kết quả ở cả phía ứng dụng và database:

- Tạo bản ghi hợp lệ và nhận được định danh hoặc trạng thái đúng.
- Đọc theo khóa, bộ lọc, phân trang và sắp xếp cho kết quả mong đợi.
- Cập nhật chỉ thay đổi các trường được phép.
- Xóa tuân thủ quy tắc xóa mềm, xóa cứng và quan hệ phụ thuộc.
- Truy vấn không trả về dữ liệu của tenant hoặc người dùng khác.
- Truy vấn xử lý đúng dữ liệu thiếu, trùng, biên và ký tự đặc biệt.
- Dữ liệu được ghi có thể đọc lại theo quy tắc nhất quán đã cam kết.

Không chỉ xác minh số dòng trả về. Cần kiểm tra nội dung, trạng thái, quan hệ và tác dụng phụ. Ví dụ, xóa một khách hàng có thể cần giữ lịch sử hóa đơn hoặc chuyển trạng thái tham chiếu thay vì xóa toàn bộ dữ liệu liên quan.

### Xác minh transaction và tính nguyên tử

Transaction giúp nhóm thao tác nhiều thay đổi như một đơn vị logic. Nếu một bước thất bại, các thay đổi thuộc transaction cần được rollback theo quy tắc. Kiểm thử cần xác minh:

- Tất cả thao tác thành công thì trạng thái cuối được commit.
- Một bước thất bại thì các thay đổi trong transaction được rollback.
- Ngoại lệ giữa chừng không để lại dữ liệu dở dang.
- Transaction được mở và đóng đúng cách, không giữ khóa lâu ngoài dự kiến.
- Nested transaction hoặc savepoint được sử dụng theo đúng semantics của database.
- Lỗi kết nối khi commit được xử lý thận trọng vì kết quả có thể chưa rõ với phía gọi.

Một tình huống quan trọng là client mất kết nối ngay sau khi gửi commit. Ứng dụng có thể không biết transaction đã commit hay chưa. Với thao tác có tác dụng phụ, không nên tự động chạy lại toàn bộ chỉ dựa trên timeout; cần cơ chế truy vấn trạng thái hoặc idempotency phù hợp.

### Kiểm tra ràng buộc và tính toàn vẹn dữ liệu

Ràng buộc database là lớp bảo vệ cuối cùng cho nhiều quy tắc. Hãy kiểm tra:

- Khóa ngoại từ chối tham chiếu không tồn tại.
- Unique constraint ngăn dữ liệu trùng trong điều kiện đồng thời.
- Check constraint từ chối giá trị ngoài miền hợp lệ.
- Not-null constraint bảo vệ trường bắt buộc.
- Quy tắc cascade hoặc restrict khi xóa bản ghi cha.
- Quy tắc optimistic locking hoặc version column ngăn ghi đè cập nhật mới hơn.

Kiểm thử nên xác minh cả phản hồi từ ứng dụng. Lỗi constraint cần được chuyển thành thông báo hoặc mã lỗi phù hợp, không làm lộ câu lệnh SQL hay chi tiết nội bộ cho người dùng.

### Kiểm tra giao dịch đồng thời và mức cô lập

Nhiều lỗi database chỉ xuất hiện khi hai hoặc nhiều yêu cầu thao tác cùng một dữ liệu. Ví dụ, hai người cùng mua sản phẩm cuối cùng trong kho; nếu kiểm tra tồn kho và trừ kho không nguyên tử, cả hai có thể được xác nhận.

Các tình huống cần cân nhắc:

- Hai transaction cùng cập nhật một bản ghi.
- Hai yêu cầu cùng tạo bản ghi có khóa nghiệp vụ duy nhất.
- Đọc dữ liệu rồi cập nhật dựa trên giá trị cũ.
- Deadlock khi hai transaction khóa tài nguyên theo thứ tự khác nhau.
- Lost update, dirty read, non-repeatable read hoặc phantom read tùy mức cô lập.
- Optimistic locking phát hiện xung đột và yêu cầu thử lại.
- Isolation level cấu hình khác nhau giữa các môi trường.

Kiểm thử đồng thời cần điều khiển được thời điểm thực hiện, số worker và dữ liệu dùng chung. Hãy xác minh trạng thái cuối, số bản ghi và các invariant nghiệp vụ, không chỉ dựa vào việc cả hai request nhận phản hồi thành công.

### Kiểm tra connection pool và timeout

Connection pool giúp tái sử dụng kết nối, nhưng cấu hình sai có thể gây cạn kết nối hoặc giữ tài nguyên quá lâu. Cần kiểm tra:

- Giới hạn kết nối và hành vi khi pool đầy.
- Connection timeout, query timeout và transaction timeout.
- Kết nối bị ngắt hoặc database khởi động lại.
- Kết nối stale được phát hiện và loại bỏ.
- Kết nối được trả về pool sau cả thành công và exception.
- Tải đồng thời không làm cạn pool hoặc gây hàng đợi không kiểm soát.

Theo dõi số kết nối đang dùng, số kết nối chờ, thời gian chờ lấy kết nối, thời gian truy vấn và tỷ lệ lỗi. Một ứng dụng có query nhanh vẫn có thể chậm nếu mọi request phải chờ pool cấp kết nối.

### Kiểm tra migration và khả năng tương thích schema

Migration là thay đổi cấu trúc hoặc dữ liệu database theo phiên bản. Cần xác minh:

- Migration chạy trên schema hiện tại và kết thúc đúng.
- Dữ liệu cũ được chuyển đổi và giữ nguyên ý nghĩa.
- Migration có thể chạy lại hoặc có cơ chế đánh dấu trạng thái rõ ràng.
- Khối lượng dữ liệu lớn không làm thời gian khóa vượt ngưỡng cho phép.
- Phiên bản ứng dụng cũ và mới tương thích trong thời gian chuyển tiếp.
- Rollback hoặc phương án khôi phục được xác định và thử nghiệm khi phù hợp.

Không giả định mọi migration đều có thể rollback an toàn. Một thao tác xóa cột hoặc biến đổi dữ liệu mất thông tin có thể không đảo ngược. Cần backup, kế hoạch khôi phục và tiêu chí dừng trước khi thực hiện trên dữ liệu quan trọng.

## 3. Kiểm tra giao tiếp với bộ nhớ đệm

### Hiểu vai trò và mô hình cache

Cache lưu bản sao dữ liệu để giảm độ trễ hoặc tải lên nguồn dữ liệu chính. Nó có thể nằm trong tiến trình ứng dụng, trên một máy riêng hoặc trong dịch vụ phân tán. Mô hình thường gặp gồm:

- Cache-aside: ứng dụng đọc cache trước; nếu không có thì đọc nguồn chính rồi lưu vào cache.
- Read-through: lớp cache tự tải dữ liệu từ nguồn khi cache miss.
- Write-through: ghi dữ liệu qua cache và cập nhật nguồn theo cơ chế đồng bộ.
- Write-behind: ghi vào cache trước rồi cập nhật nguồn bất đồng bộ.
- Refresh-ahead: làm mới dữ liệu trước khi hết hạn theo chính sách.

Mỗi mô hình có đặc tính nhất quán, độ trễ và rủi ro khác nhau. Nhóm cần hiểu mô hình đang dùng trước khi chọn oracle và kịch bản.

~~~mermaid
flowchart TD
    A["Ứng dụng đọc dữ liệu"] --> B{"Cache hit?"}
    B -->|Có| C["Trả dữ liệu từ cache"]
    B -->|Không| D["Đọc nguồn chính"]
    D --> E["Lưu vào cache theo TTL"]
    E --> C
~~~

### Kiểm tra cache hit, cache miss và key

Với mỗi đường đọc, hãy kiểm tra:

- Cache hit trả đúng dữ liệu và đúng tenant hoặc người dùng.
- Cache miss truy vấn nguồn chính và lưu dữ liệu theo đúng key.
- Key chứa đủ thành phần phân biệt dữ liệu, chẳng hạn tenant, locale, quyền hoặc phiên bản.
- Key không vô tình chứa dữ liệu nhạy cảm hoặc thông tin có thể gây lộ qua log.
- Cache miss đồng thời không tạo quá nhiều truy vấn trùng.
- Dữ liệu không tồn tại được xử lý đúng, tránh negative cache giữ trạng thái sai quá lâu.

Key thiếu tenant hoặc vai trò có thể khiến một người dùng nhận dữ liệu đã cache cho người khác. Đây là lỗi phân tách dữ liệu nghiêm trọng dù từng truy vấn database riêng lẻ đều đúng.

### Kiểm tra TTL và hết hạn

TTL xác định thời gian một mục cache được xem là còn hiệu lực. Hãy kiểm tra:

- Mục cache tồn tại trước khi hết hạn và bị loại bỏ hoặc làm mới sau TTL.
- TTL đúng theo loại dữ liệu và chính sách nghiệp vụ.
- TTL bằng 0, giá trị âm hoặc không được cấu hình có hành vi xác định.
- Cache không tiếp tục trả dữ liệu đã hết hạn do đồng hồ hoặc chính sách eviction sai.
- Việc refresh không tạo khoảng trống gây lỗi cho người dùng nếu hệ thống yêu cầu stale-while-revalidate.
- TTL được áp dụng nhất quán giữa các instance và môi trường.

TTL không tự đảm bảo dữ liệu luôn mới. Một dữ liệu có thể thay đổi ngay sau khi được cache. Nếu nghiệp vụ yêu cầu cập nhật tức thời, cần cơ chế invalidation hoặc đồng bộ phù hợp.

### Kiểm tra invalidation và cập nhật dữ liệu

Cache invalidation là nguồn lỗi khó phát hiện vì dữ liệu cũ vẫn có vẻ hợp lệ. Các kịch bản quan trọng:

- Cập nhật nguồn chính rồi đọc lại dữ liệu qua cache.
- Xóa bản ghi và xác minh cache không tiếp tục trả bản ghi đó.
- Thay đổi quyền hoặc trạng thái tenant và xác minh cache cũ không làm lộ dữ liệu.
- Cập nhật một phần dữ liệu trong khi cache chứa bản sao toàn bộ.
- Nhiều instance cùng giữ cache cục bộ và nhận tín hiệu invalidation.
- Sự kiện invalidation bị mất, đến trễ hoặc được xử lý trùng.

Xác định thứ tự thao tác rõ ràng. Nếu ứng dụng cập nhật database rồi xóa cache, có thể có khoảng thời gian ngắn mà request khác đọc cache cũ. Nếu xóa cache trước khi commit database, request có thể tải dữ liệu cũ trở lại cache. Cần chọn thứ tự và cơ chế đồng bộ theo yêu cầu nhất quán của sản phẩm.

### Kiểm tra dữ liệu cũ và mức nhất quán cho phép

Không phải mọi loại dữ liệu đều cần consistency giống nhau. Danh sách bài viết có thể chấp nhận trễ vài giây; số dư tài khoản, quyền truy cập hoặc trạng thái thanh toán có thể yêu cầu chặt chẽ hơn.

Với mỗi loại dữ liệu, hãy xác định:

- Nguồn dữ liệu có thẩm quyền.
- Mức trễ tối đa được chấp nhận.
- Trạng thái nào không được phép dùng dữ liệu cũ.
- Hành vi khi cache không sẵn sàng.
- Cách phát hiện và sửa cache lệch với nguồn chính.

Một chiến lược có thể bỏ qua cache cho dữ liệu nhạy cảm hoặc đọc lại nguồn chính khi cần xác nhận trước thao tác quan trọng. Điều này phải dựa trên yêu cầu nghiệp vụ và kiến trúc thực tế.

### Kiểm tra cache stampede, eviction và giới hạn dung lượng

Khi một key phổ biến hết hạn, nhiều request có thể đồng thời truy vấn nguồn chính và cùng tái tạo cache. Hiện tượng này có thể làm tăng tải đột biến. Hãy kiểm tra:

- Nhiều request cùng cache miss có được gộp hoặc điều tiết không?
- TTL có được phân tán bằng jitter để tránh hết hạn đồng loạt không?
- Có cơ chế khóa hoặc single-flight phù hợp không?
- Cache eviction có ảnh hưởng đến tính đúng đắn hay chỉ làm tăng truy vấn?
- Cache đầy hoặc bộ nhớ bị giới hạn có hành vi dự kiến không?
- Một key lớn hoặc nhiều key biến thiên có thể gây tăng bộ nhớ bất thường không?

Cache phải được xem là tối ưu hiệu năng. Nếu cache mất dữ liệu, sản phẩm vẫn cần duy trì tính đúng đắn thông qua nguồn dữ liệu chính, dù có thể chậm hơn.

### Kiểm tra cache không khả dụng

Mô phỏng cache timeout, từ chối kết nối, khởi động lại hoặc mất mạng. Xác minh:

- Ứng dụng có fallback về nguồn chính nếu phù hợp không?
- Fallback có được giới hạn để tránh tạo tải database quá mức không?
- Cache lỗi có làm hỏng thao tác ghi nguồn chính không?
- Sau khi cache phục hồi, dữ liệu được làm mới hoặc invalidation đúng không?
- Người dùng không nhận trạng thái thành công giả khi thao tác quan trọng thất bại?

Không nên luôn bỏ qua cache khi lỗi. Với dữ liệu quyền hoặc dữ liệu nhạy cảm, fallback phải tuân theo chính sách bảo mật; không được dùng dữ liệu cũ hoặc mặc định quyền rộng chỉ để giữ tính sẵn sàng.

## 4. Kiểm tra giao tiếp với hàng đợi và hệ thống nhắn tin

### Phân biệt queue, topic và consumer

Hàng đợi thường giữ công việc chờ được consumer xử lý. Hệ thống pub/sub có thể phát một sự kiện cho nhiều subscriber. Một broker có thể cung cấp cả queue, topic, partition và subscription với semantics riêng.

Trước khi kiểm thử, hãy xác định:

- Producer nào phát thông điệp?
- Queue, topic, exchange hoặc subscription nào nhận?
- Routing key hoặc partition key được dùng ra sao?
- Consumer group nào xử lý thông điệp?
- Thông điệp được lưu bao lâu và khi nào bị xóa?
- Cơ chế ack, retry, visibility timeout hoặc offset commit hoạt động thế nào?
- Có dead-letter queue (DLQ) hoặc luồng xử lý lỗi không?

Không suy luận semantics chỉ từ tên công nghệ. Các broker khác nhau có thể xử lý xác nhận, thứ tự, retry và lưu giữ theo cách khác nhau.

### Kiểm tra schema và nội dung thông điệp

Producer và consumer phải hiểu cùng một hợp đồng. Cần xác minh:

- Tên sự kiện, phiên bản schema và loại nội dung.
- Trường bắt buộc, kiểu dữ liệu, đơn vị và giá trị mặc định.
- Event ID, correlation ID, aggregate ID hoặc partition key.
- Timestamp, múi giờ và thứ tự phiên bản.
- Dữ liệu nhạy cảm có được tối thiểu hóa hoặc che giấu không.
- Consumer xử lý trường không biết, trường thiếu hoặc phiên bản mới ra sao.
- Schema evolution có tương thích với consumer cũ đang chạy không.

Một thông điệp hợp lệ về cú pháp vẫn có thể sai ngữ nghĩa. Ví dụ, trường amount có kiểu số nhưng không nói rõ đơn vị tiền tệ; consumer có thể hiểu khác producer. Hợp đồng phải định nghĩa cả ý nghĩa dữ liệu.

### Xác minh phát và nhận thông điệp

Ở phía producer, kiểm tra:

- Thông điệp được gửi đến đúng queue/topic.
- Routing key hoặc partition key đúng.
- Producer nhận được xác nhận theo semantics của broker.
- Lỗi publish, timeout và broker không khả dụng được xử lý.
- Một thao tác nghiệp vụ không tạo thông điệp trùng ngoài ý muốn.
- Thông điệp quan trọng không bị mất khi ứng dụng dừng giữa lúc ghi dữ liệu và publish.

Ở phía consumer, kiểm tra:

- Consumer nhận đúng subscription và quyền.
- Thông điệp hợp lệ được xử lý và xác nhận đúng lúc.
- Thông điệp lỗi không bị ack trước khi xử lý hoàn tất.
- Consumer có thể tiếp tục sau khi khởi động lại.
- Thông điệp trùng được xử lý an toàn.
- Consumer không xử lý vượt quá năng lực khiến backlog tăng không kiểm soát.

### Hiểu at-most-once, at-least-once và exactly-once

Các thuật ngữ delivery semantics mô tả cách hệ thống phân phối thông điệp:

- **At-most-once:** thông điệp được giao không quá một lần; có thể bị mất nếu lỗi xảy ra ở thời điểm không thuận lợi.
- **At-least-once:** thông điệp được giao lại cho đến khi được xác nhận theo cơ chế của broker; consumer có thể nhận nhiều lần.
- **Exactly-once:** một số nền tảng cung cấp bảo đảm xử lý trong phạm vi và điều kiện cụ thể, nhưng không nên hiểu là mọi tác dụng phụ bên ngoài được thực hiện đúng một lần trên toàn hệ thống.

Trong nhiều hệ thống, consumer cần được thiết kế idempotent ngay cả khi broker có cơ chế chống trùng. Nếu consumer cập nhật database rồi bị dừng trước khi ack, broker có thể giao lại cùng thông điệp. Lần xử lý tiếp theo phải nhận ra sự kiện đã được áp dụng hoặc bảo đảm thao tác không tạo kết quả lặp.

Ví dụ, dùng event ID duy nhất và bảng inbox/processed-events để ghi nhận thông điệp đã xử lý trong cùng transaction với thay đổi nghiệp vụ. Cơ chế cụ thể cần phù hợp với broker, database và yêu cầu độ trễ.

### Kiểm tra acknowledgment và thời điểm xác nhận

Ack quá sớm có thể làm mất công việc nếu consumer dừng trước khi hoàn tất. Ack quá muộn có thể khiến broker giao lại thông điệp dù tác dụng phụ đã xảy ra.

Kiểm thử các thời điểm:

1. Consumer nhận thông điệp nhưng chưa bắt đầu xử lý.
2. Consumer đang xử lý và bị dừng.
3. Database commit thành công nhưng ack chưa gửi.
4. Ack gửi đi nhưng phản hồi bị mất.
5. Consumer xử lý lỗi tạm thời hoặc lỗi không thể phục hồi.
6. Consumer khởi động lại khi thông điệp vẫn đang bị khóa hoặc visibility timeout sắp hết.

Xác minh kết quả cuối, số lần tác dụng phụ và trạng thái thông điệp. Không chỉ kiểm tra log cho biết handler đã được gọi.

### Kiểm tra retry, backoff và dead-letter queue

Retry phù hợp với lỗi tạm thời như timeout hoặc dịch vụ phụ thuộc không khả dụng trong thời gian ngắn. Lỗi dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường cần xử lý khác.

Cần kiểm tra:

- Phân loại lỗi có thể retry và không thể retry.
- Số lần retry tối đa và khoảng chờ.
- Exponential backoff và jitter nếu cần tránh dồn tải.
- Thông điệp có giữ nguyên ID và correlation ID qua lần retry không?
- Khi hết số lần thử, thông điệp được chuyển đến DLQ đúng không?
- DLQ có giữ thông tin lỗi, số lần thử và dữ liệu cần điều tra không?
- Quy trình sửa dữ liệu và phát lại thông điệp có kiểm soát không?
- Phát lại có thể tạo tác dụng phụ trùng hay không?

DLQ không phải nơi để bỏ quên thông điệp. Cần cảnh báo khi có thông điệp mới, xác định người chịu trách nhiệm, quy trình phân tích và tiêu chí phát lại hoặc loại bỏ.

### Kiểm tra thứ tự và xử lý đồng thời

Một số nghiệp vụ yêu cầu thứ tự sự kiện theo một thực thể, ví dụ tạo đơn hàng trước khi cập nhật trạng thái giao hàng. Broker có thể chỉ bảo đảm thứ tự trong một partition hoặc một queue, không phải toàn hệ thống.

Hãy kiểm tra:

- Partition key hoặc routing key giữ các sự kiện liên quan cùng thứ tự cần thiết.
- Consumer có thể xử lý song song mà không phá vỡ quy tắc nghiệp vụ.
- Sự kiện đến muộn không làm trạng thái lùi về phiên bản cũ.
- Sự kiện trùng không tạo tác dụng phụ.
- Một thông điệp lỗi không chặn toàn bộ queue ngoài chủ đích.
- Consumer scale up/down không làm mất hoặc xử lý sai thông điệp đang chờ.

Nếu thứ tự toàn cục không được bảo đảm, ứng dụng có thể cần sequence number, version check hoặc quy tắc từ chối cập nhật cũ.

### Kiểm tra backlog, lưu giữ và sức chịu tải

Backlog tăng có thể khiến người dùng chờ lâu dù API ban đầu đã trả thành công. Kiểm thử cần xem xét:

- Tốc độ producer và consumer trong điều kiện tải đại diện.
- Độ dài queue và tuổi của thông điệp cũ nhất.
- Thời gian xử lý trung bình và phân vị cao.
- Hành vi khi consumer chậm hoặc dừng.
- Giới hạn bộ nhớ, dung lượng lưu giữ và quota broker.
- Chính sách retention, TTL, compaction hoặc xóa thông điệp.
- Khả năng tăng số consumer mà vẫn giữ thứ tự và tính đúng đắn.
- Cơ chế cảnh báo khi backlog hoặc tuổi thông điệp vượt ngưỡng.

Không chỉ đo số thông điệp mỗi giây. Cần đo thời gian từ lúc sự kiện được phát đến khi tác dụng nghiệp vụ hoàn tất, vì đây mới là độ trễ mà người dùng hoặc quy trình kinh doanh chịu ảnh hưởng.

## 5. Kiểm tra tính nhất quán giữa database, cache và queue

### Tránh trạng thái ghi thành công nhưng sự kiện bị mất

Một lỗi phổ biến là ứng dụng ghi database thành công rồi publish thông điệp thất bại. Trạng thái nghiệp vụ đã đổi nhưng worker không biết cần xử lý tiếp.

Một cách giải quyết thường dùng là transactional outbox: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database; một tiến trình riêng đọc outbox và publish sự kiện. Cần kiểm thử:

- Thay đổi nghiệp vụ và outbox cùng commit hoặc cùng rollback.
- Publisher có thể publish lại sau timeout mà không tạo tác dụng phụ trùng.
- Bản ghi outbox được đánh dấu đã gửi theo quy tắc an toàn.
- Worker khôi phục sau khi dừng giữa publish và cập nhật trạng thái.
- Outbox backlog được theo dõi và có quy trình xử lý.

~~~mermaid
flowchart LR
    A["Yêu cầu nghiệp vụ"] --> T["Một transaction"]
    T --> DB[("Bảng nghiệp vụ")]
    T --> O[("Bảng outbox")]
    O --> P["Outbox publisher"]
    P --> Q[["Broker / Queue"]]
    Q --> C["Consumer"]
    C --> D[("Database đích")]
~~~

Outbox giúp gắn thay đổi nghiệp vụ với ý định phát sự kiện, nhưng publisher vẫn có thể gửi lặp. Consumer vẫn cần xử lý idempotent.

### Tránh tác dụng phụ trùng khi consumer retry

Một consumer có thể thực hiện tác dụng phụ rồi gặp lỗi trước khi xác nhận thông điệp. Lần giao lại sẽ chạy lại handler. Hãy kiểm tra cách consumer ghi nhận event ID, trạng thái xử lý và kết quả nghiệp vụ.

Nếu cần cập nhật database và đánh dấu event đã xử lý, hai thao tác nên được thực hiện trong cùng transaction khi cùng một database. Nếu tác dụng phụ xảy ra ở dịch vụ bên ngoài, cần cơ chế idempotency hoặc quy trình đối soát phù hợp với dịch vụ đó.

### Kiểm tra thứ tự cập nhật database và cache

Nếu database là nguồn có thẩm quyền, cache cần phản ánh thay đổi theo một quy tắc đã định. Hãy thử các tình huống:

- Database commit nhưng cache invalidation thất bại.
- Cache bị xóa trước khi database commit.
- Event cập nhật cache đến trễ hoặc sai thứ tự.
- Hai cập nhật đồng thời cho cùng một key.
- Cache được làm mới từ một replica database có độ trễ.
- Cache còn giữ dữ liệu sau khi quyền truy cập đã bị thu hồi.

Xác định thời gian nhất quán được chấp nhận và cách phục hồi khi invalidation bị mất. Với dữ liệu nhạy cảm, có thể cần bỏ qua cache hoặc kiểm tra quyền từ nguồn có thẩm quyền.

### Kiểm tra hành trình đầu cuối

Một bài kiểm thử hệ thống đại diện nên theo dõi một giao dịch qua tất cả thành phần. Ví dụ, khi người dùng tạo đơn:

1. API xác thực yêu cầu và ghi đơn vào database.
2. Transaction ghi sự kiện vào outbox.
3. Publisher gửi sự kiện đến queue.
4. Consumer xử lý tồn kho và cập nhật trạng thái.
5. Cache được invalidation hoặc làm mới.
6. Dịch vụ thông báo gửi kết quả cho người dùng.

Kiểm tra trạng thái cuối tại database, cache, queue và giao diện. Xác minh không có sự kiện tồn đọng ngoài dự kiến, không có bản ghi trùng và thông báo phản ánh trạng thái có thẩm quyền.

## 6. Thiết kế môi trường và dữ liệu kiểm thử

### Dùng thành phần thật hoặc môi trường đại diện

Đối với database, cache và broker, nên dùng container, instance kiểm thử hoặc dịch vụ sandbox được quản lý để kiểm tra hành vi thực. Mock vẫn hữu ích cho unit test nhưng không thay thế bằng chứng tích hợp.

Môi trường cần ghi nhận:

- Phiên bản database, cache server và broker.
- Cấu hình schema, index, isolation level và connection pool.
- Chính sách eviction, TTL và replication của cache.
- Queue/topic, partition, retention, ack và retry policy.
- Quyền truy cập, secret, chứng thư và network policy.
- Cấu hình worker, số consumer và concurrency.
- Khác biệt so với production có thể ảnh hưởng kết quả.

Nếu dùng container dùng chung hoặc môi trường chia sẻ, cần cô lập tên database, schema, key prefix, queue/topic và consumer group để các lần chạy không can thiệp lẫn nhau.

### Tạo dữ liệu có thể lặp lại

Dữ liệu kiểm thử cần được tạo và dọn dẹp theo cách xác định. Một bộ dữ liệu nên bao gồm:

- Bản ghi hợp lệ và quan hệ đầy đủ.
- Dữ liệu thiếu, trùng và giá trị biên.
- Trạng thái trước và sau chuyển đổi.
- Nhiều tenant hoặc vai trò để kiểm tra cách ly dữ liệu.
- Dữ liệu đủ lớn để kiểm tra truy vấn, index hoặc phân trang khi cần.
- Thông điệp hợp lệ, sai schema, trùng, đến muộn và không thể xử lý.

Tránh dùng dữ liệu production hoặc bí mật thật nếu chưa có căn cứ và quy trình được phép. Dùng dữ liệu tổng hợp hoặc đã khử định danh, và xác định thời hạn lưu cùng cách xóa.

### Cô lập trạng thái giữa các lần chạy

Database, cache và queue đều có thể giữ trạng thái sau khi test kết thúc. Nếu không dọn dẹp, lần chạy sau có thể đọc cache cũ, nhận thông điệp tồn đọng hoặc va vào unique key.

Có thể dùng:

- Database/schema riêng cho mỗi suite hoặc run ID.
- Key prefix riêng cho cache.
- Queue/topic hoặc subscription riêng trong phạm vi môi trường cho phép.
- Event ID và correlation ID riêng cho từng lần chạy.
- Setup và teardown có kiểm tra, có thể chạy lại an toàn.
- Thời hạn dọn dẹp rõ ràng cho dữ liệu còn sót.

Không xóa dữ liệu hoặc queue dùng chung nếu không có quyền và phạm vi được thống nhất. Với hệ thống có dữ liệu quan trọng, cần xác định chủ sở hữu và phương án khôi phục trước khi chạy kịch bản phá hủy.

## 7. Xác minh lỗi và khả năng phục hồi

### Lập ma trận lỗi theo thành phần

Kiểm thử lỗi cần có chủ đích. Một ma trận đơn giản có thể định hướng phạm vi:

| Thành phần | Tình huống lỗi | Hành vi cần xác minh |
|---|---|---|
| Database | Mất kết nối trước query | Timeout rõ ràng, không giữ tài nguyên vô hạn |
| Database | Lỗi giữa transaction | Rollback hoặc trạng thái cuối được xác định |
| Database | Deadlock hoặc conflict | Retry có giới hạn hoặc trả lỗi có thể xử lý |
| Database | Pool cạn | Backpressure, timeout và cảnh báo phù hợp |
| Cache | Cache miss hoặc key hết hạn | Đọc nguồn chính và làm mới đúng |
| Cache | Cache không khả dụng | Fallback có kiểm soát, không làm lộ dữ liệu |
| Cache | Invalidation bị mất | Phát hiện dữ liệu cũ và có cách đồng bộ lại |
| Queue | Broker không khả dụng khi publish | Lỗi được giữ lại hoặc outbox chờ phát |
| Queue | Consumer dừng trước ack | Thông điệp được giao lại và xử lý an toàn |
| Queue | Payload không hợp lệ | Đưa vào luồng lỗi/DLQ theo chính sách |
| Queue | Backlog tăng | Cảnh báo, điều tiết và khả năng phục hồi |

### Kiểm thử timeout và retry có kiểm soát

Mô phỏng độ trễ, mất kết nối hoặc lỗi tạm thời ở đúng ranh giới. Kiểm tra số lần retry, khoảng chờ, tổng thời gian và tác dụng phụ. Retry không giới hạn có thể làm sự cố nặng hơn bằng cách tạo thêm tải cho thành phần đang suy giảm.

Với thao tác không idempotent, phải kiểm tra kết quả trước khi gửi lại hoặc dùng khóa idempotency. Với queue, cần biết retry do broker hay do ứng dụng điều khiển để tránh hai lớp retry nhân số lần thử.

### Kiểm thử khởi động lại và phục hồi sau gián đoạn

Thử dừng database connection, cache node, broker hoặc worker ở các thời điểm khác nhau. Sau khi thành phần phục hồi, xác minh:

- Kết nối được thiết lập lại và tài nguyên cũ được giải phóng.
- Transaction hoặc tác vụ dang dở có trạng thái rõ.
- Thông điệp chưa ack được giao lại theo semantics.
- Outbox hoặc backlog được xử lý tiếp.
- Cache được làm mới hoặc invalidation lại.
- Không mất dữ liệu, không nhân đôi tác dụng phụ ngoài quy tắc.
- Hệ thống phát cảnh báo và ghi lại sự kiện đủ để điều tra.

Không nên tiêm lỗi vào môi trường production hoặc dịch vụ dùng chung khi chưa có quy trình, phạm vi và quyền phù hợp.

## 8. Bảo mật và quyền riêng tư tại ranh giới dữ liệu

Database, cache và queue đều có thể lưu hoặc truyền dữ liệu nhạy cảm. Kiểm thử cần xác minh:

- Tài khoản dịch vụ chỉ có quyền tối thiểu cần thiết.
- Tenant hoặc người dùng không thể đọc dữ liệu của nhau.
- Dữ liệu nhạy cảm được mã hóa hoặc che giấu theo yêu cầu.
- Secret không xuất hiện trong cấu hình công khai, log hoặc payload không cần thiết.
- Cache key và queue routing không làm lộ thông tin nhạy cảm.
- Message broker xác minh producer và consumer theo chính sách.
- Dữ liệu trong DLQ được kiểm soát quyền truy cập và thời gian lưu.
- Dữ liệu kiểm thử được quản lý và xóa theo quy định.

Kiểm thử phân tách tenant cần bao gồm cả cache và queue. Một truy vấn database có filter tenant đúng nhưng cache key thiếu tenant vẫn có thể làm lộ dữ liệu. Tương tự, consumer dùng quyền quá rộng có thể đọc thông điệp ngoài phạm vi cần thiết.

## 9. Quan sát và chẩn đoán

### Dùng tín hiệu phù hợp cho từng thành phần

Các chỉ số có thể theo dõi:

| Thành phần | Metric hoặc tín hiệu | Ý nghĩa |
|---|---|---|
| Database | Query latency, error rate, connection pool usage, lock wait, deadlock | Phát hiện truy vấn chậm, cạn kết nối và tranh chấp |
| Cache | Hit ratio, miss ratio, eviction, memory usage, latency, timeout | Đánh giá hiệu quả cache và nguy cơ suy giảm |
| Queue | Queue depth, oldest message age, publish/consume rate, retry, DLQ count | Phát hiện backlog, consumer chậm và thông điệp lỗi |
| Worker | Processing duration, failure rate, retry count, concurrency | Xác định năng lực xử lý và điểm nghẽn |
| Hành trình | Thời gian từ yêu cầu đến trạng thái nghiệp vụ hoàn tất | Đo trải nghiệm đầu cuối thay vì chỉ đo một thành phần |

Không nên tối ưu một metric riêng lẻ. Ví dụ, cache hit ratio cao chưa chắc tốt nếu cache đang trả dữ liệu cũ; queue depth thấp chưa chắc tốt nếu thông điệp bị xóa trước khi xử lý. Cần kết hợp metric với kiểm tra trạng thái nghiệp vụ.

### Truy vết xuyên thành phần

Dùng correlation ID hoặc trace ID để nối yêu cầu từ API đến database, publisher, broker, consumer và dịch vụ tiếp theo. Ghi nhận các mốc thời gian quan trọng như lúc ghi outbox, publish, consume, commit và ack.

Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân không cần thiết. Log nên có đủ ngữ cảnh để điều tra nhưng phải tuân theo chính sách bảo mật và quyền riêng tư.

### Xác minh cảnh báo và runbook

Kiểm thử không chỉ xác nhận metric được phát ra mà còn xác minh cảnh báo kích hoạt đúng khi vượt ngưỡng. Ví dụ:

- Connection pool chờ lâu hoặc database error tăng.
- Cache timeout hoặc eviction tăng bất thường.
- Queue backlog và tuổi thông điệp vượt ngưỡng.
- DLQ xuất hiện thông điệp mới.
- Outbox backlog tăng hoặc publisher không tiến triển.
- Worker retry liên tục hoặc không có consumer hoạt động.

Runbook cần nêu người chịu trách nhiệm, cách xác định phạm vi, bước chẩn đoán, điều kiện phát lại và cách xác minh trạng thái cuối. Một cảnh báo không có người nhận hoặc không có hành động rõ ràng không tạo ra khả năng phục hồi thực tế.

## 10. Ví dụ: kiểm thử hành trình tạo đơn hàng bất đồng bộ

Giả sử ứng dụng thương mại cho phép người dùng tạo đơn hàng. API ghi đơn vào database và tạo bản ghi outbox trong cùng transaction. Publisher gửi sự kiện order-created đến broker. Consumer kiểm tra tồn kho, cập nhật trạng thái và phát sự kiện tiếp theo. Cache giữ bản sao trạng thái đơn để giao diện đọc nhanh.

### Mục tiêu và rủi ro

| Mục tiêu | Rủi ro | Bằng chứng cần thu thập |
|---|---|---|
| Đơn hàng được ghi bền vững | Transaction rollback không đầy đủ | Bản ghi đơn và outbox sau lỗi |
| Sự kiện không bị mất | Publish thất bại sau commit | Outbox backlog, số sự kiện đã phát |
| Consumer không xử lý trùng | Broker giao lại sau khi worker dừng | Event ID, số tác dụng phụ, trạng thái đơn |
| Cache phản ánh trạng thái mới | Invalidation bị mất hoặc đến trễ | Giá trị database và cache theo thời gian |
| Hành trình phục hồi được | Broker hoặc database tạm ngừng | Trạng thái cuối sau khôi phục và đối soát |

### Kịch bản đại diện

1. Gửi yêu cầu tạo đơn hợp lệ; xác minh đơn và outbox cùng được commit.
2. Gây lỗi trước commit; xác minh cả đơn và outbox đều không tồn tại.
3. Tạm dừng broker sau khi database commit; xác minh outbox còn chờ và publisher gửi lại sau phục hồi.
4. Cho consumer xử lý sự kiện rồi dừng trước ack; xác minh sự kiện được giao lại nhưng đơn không bị xử lý trùng.
5. Gửi cùng event ID nhiều lần; xác minh consumer idempotent.
6. Làm cache mất kết nối; xác minh ứng dụng fallback theo chính sách và không trả dữ liệu sai.
7. Làm invalidation đến trễ; xác minh giới hạn dữ liệu cũ và cơ chế đồng bộ lại.
8. Tăng tốc độ producer cao hơn consumer trong thời gian kiểm thử; theo dõi backlog, tuổi thông điệp và khả năng bắt kịp.
9. Gửi payload sai schema; xác minh thông điệp được xử lý theo chính sách lỗi và có thể điều tra.

Kết quả cần đối chiếu ở nhiều nơi: database, outbox, broker, trạng thái xử lý, cache và giao diện. Không dùng riêng log của API để kết luận đơn hàng đã hoàn tất.

## 11. Những sai lầm thường gặp

- **Chỉ dùng mock để kiểm tra tích hợp:** mock không chứng minh hành vi database, cache hoặc broker thật.
- **Chỉ kiểm tra phản hồi API:** phản hồi thành công chưa chứng minh dữ liệu đã commit hoặc thông điệp đã xử lý.
- **Bỏ qua xử lý đồng thời:** lỗi race condition, lost update hoặc overselling chỉ xuất hiện khi nhiều request cùng thao tác.
- **Xem cache như nguồn dữ liệu có thẩm quyền:** cache có thể hết hạn, bị eviction hoặc lệch với nguồn chính.
- **Cho rằng queue bảo đảm xử lý đúng một lần:** delivery semantics và tác dụng phụ phải được kiểm tra riêng.
- **Ack trước khi xử lý hoàn tất:** worker dừng giữa chừng có thể làm mất công việc.
- **Retry không giới hạn:** có thể tạo tải dây chuyền hoặc tác dụng phụ lặp.
- **Không kiểm tra DLQ:** thông điệp lỗi bị giữ lại nhưng không ai điều tra hoặc phát lại.
- **Không cô lập dữ liệu test:** cache key, queue và database dùng chung làm kết quả giữa các lần chạy ảnh hưởng lẫn nhau.
- **Chỉ đo thông lượng:** bỏ qua tuổi thông điệp, độ trễ đầu cuối và trạng thái nghiệp vụ.
- **Không kiểm tra quyền xuyên thành phần:** dữ liệu có thể bị lộ qua cache hoặc queue dù truy vấn database đúng.
- **Không xác minh phục hồi:** hệ thống hoạt động bình thường nhưng mất dữ liệu hoặc lệch trạng thái sau sự cố.

## 12. Đầu ra cần có trước khi chốt kiểm thử tích hợp

Một kế hoạch kiểm thử giao tiếp với database, cache và queue nên có:

1. **Sơ đồ phụ thuộc và luồng dữ liệu:** producer, consumer, nguồn dữ liệu có thẩm quyền, điểm đồng bộ và bất đồng bộ.
2. **Hợp đồng giao tiếp:** schema, kiểu dữ liệu, key, routing, quyền, timeout, retry, TTL, ack và retention.
3. **Mục tiêu và rủi ro:** tính toàn vẹn, nhất quán, hiệu năng, bảo mật, khả năng phục hồi và hậu quả người dùng.
4. **Ma trận kịch bản:** thành công, lỗi, biên, đồng thời, trùng, đến muộn, mất kết nối và khôi phục.
5. **Môi trường và dữ liệu:** phiên bản, cấu hình, dữ liệu tổng hợp, cách cô lập và dọn dẹp.
6. **Oracle và tiêu chí đạt:** trạng thái database, cache, queue, tác dụng phụ và kết quả đầu cuối cần xác minh.
7. **Kế hoạch quan sát:** metric, log, trace, cảnh báo và cách truy vết giao dịch.
8. **Trách nhiệm:** chủ sở hữu từng thành phần, người chạy kiểm thử, người điều tra và người phê duyệt.
9. **Giới hạn và rủi ro còn lại:** hành vi chưa được mô phỏng, khác biệt môi trường và điều kiện cần xác minh thêm.

Trước khi thực thi, hãy rà soát:

- Đã xác định nguồn dữ liệu có thẩm quyền và semantics nhất quán chưa?
- Schema và hợp đồng giữa producer, consumer và database có được xác minh không?
- Transaction có bảo đảm trạng thái nghiệp vụ và outbox phù hợp không?
- Cache key, TTL, invalidation và fallback có đáp ứng yêu cầu không?
- Queue có kiểm tra ack, retry, DLQ, thứ tự và idempotency không?
- Các tình huống đồng thời, timeout, dừng tiến trình và phục hồi đã được bao phủ chưa?
- Dữ liệu kiểm thử và môi trường có được cô lập, bảo vệ và dọn dẹp không?
- Có thể truy vết một giao dịch qua các thành phần không?
- Trạng thái cuối có được xác minh bằng nguồn dữ liệu có thẩm quyền không?

Kiểm tra giao tiếp với database, cache và queue có giá trị khi nó chứng minh được trạng thái và tác dụng phụ xuyên ranh giới, kể cả trong điều kiện lỗi. Hãy cập nhật kịch bản khi schema, chính sách cache, semantics của broker, tải hoặc luồng nghiệp vụ thay đổi. Nhờ đó, nhóm có bằng chứng đáng tin cậy rằng các thành phần không chỉ hoạt động riêng lẻ mà còn phối hợp đúng để hoàn thành mục tiêu của sản phẩm.

