# Phân biệt thời gian thực thi trong cơ sở dữ liệu với thời gian chờ tại ứng dụng

Khi một API mất nhiều thời gian để trả lời, nguyên nhân không nhất thiết nằm trong câu lệnh SQL. Ứng dụng có thể đang đợi một kết nối rảnh trong connection pool, xếp hàng trên executor, chờ mạng, đọc một tập kết quả lớn hoặc chuyển đổi dữ liệu. Ở phía cơ sở dữ liệu, câu lệnh cũng có thể dành phần lớn thời gian chờ khóa, chờ I/O hoặc chờ tài nguyên dùng chung thay vì sử dụng CPU.

Trong chương **Khối lượng công việc** của module **DATABASE_PERFORMANCE**, việc phân biệt các khoảng thời gian này giúp bạn hiểu đúng đặc điểm của workload và xác định nơi cần tối ưu. Module rèn phương pháp dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy, mỗi kết luận cần được gắn với số liệu và điều kiện đo cụ thể. Bài học này tập trung vào cách tách thời gian mà người dùng cảm nhận khỏi thời gian xử lý ở máy chủ cơ sở dữ liệu, cách thu thập số liệu ở cả hai phía và cách diễn giải chúng mà không nhầm lẫn.

## 1. Một yêu cầu đi qua nhiều chặng

Một yêu cầu đọc dữ liệu thường đi qua nhiều thành phần trước khi kết quả đến được người dùng:

1. Máy chủ ứng dụng nhận request và đưa công việc vào hàng đợi xử lý.
2. Một thread hoặc tác vụ được thực thi; ứng dụng lấy kết nối từ connection pool.
3. Ứng dụng chuẩn bị câu lệnh, bind tham số và gửi yêu cầu qua driver.
4. Cơ sở dữ liệu nhận yêu cầu, phân tích hoặc tìm kế hoạch phù hợp, rồi thực hiện câu lệnh.
5. Cơ sở dữ liệu trả metadata và các hàng kết quả qua mạng.
6. Driver tiếp tục lấy dữ liệu theo từng đợt; ứng dụng đọc, chuyển đổi và xử lý các hàng.
7. Ứng dụng hoàn tất giao dịch, giải phóng kết nối, tạo response và gửi về phía gọi.

Mỗi chặng có thể tạo ra độ trễ. Nếu chỉ đo thời gian từ lúc nhận request đến lúc gửi response, bạn biết người dùng phải đợi bao lâu nhưng chưa biết thời gian bị tiêu thụ ở đâu. Nếu chỉ xem thời gian truy vấn trong cơ sở dữ liệu, bạn biết một phần hoạt động phía máy chủ nhưng có thể bỏ sót thời gian chờ trước và sau câu lệnh.

Có thể mô tả gần đúng độ trễ của một đường xử lý tuần tự như sau:

~~~text
Độ trễ request
  = thời gian xếp hàng tại ứng dụng
  + thời gian chờ lấy kết nối
  + thời gian chuẩn bị và gửi câu lệnh
  + thời gian xử lý và chờ bên trong cơ sở dữ liệu
  + thời gian truyền và đọc kết quả
  + thời gian xử lý dữ liệu tại ứng dụng
  + thời gian tạo và gửi response
~~~

Đây là mô hình để phân tích, không phải phép cộng máy móc cho mọi hệ thống. Một số hoạt động có thể diễn ra song song hoặc nằm lồng bên trong một span lớn hơn. Khi đọc distributed trace, cần tránh cộng thời gian của các span cha và span con hai lần. Với một request tuần tự, các khoảng không chồng lấp có thể được cộng để giải thích tổng thời gian; với xử lý song song, độ trễ đầu cuối phụ thuộc đường găng (critical path), không phải tổng thời lượng CPU của mọi nhánh.

## 2. Phân biệt ba góc nhìn về thời gian

Cùng một thao tác có thể được đo bằng những đồng hồ khác nhau. Cần biết mỗi số đo bắt đầu ở đâu, kết thúc ở đâu và bao gồm những công việc nào.

### 2.1. Độ trễ đầu cuối tại ứng dụng

Đây là khoảng thời gian từ một mốc được chọn ở ứng dụng, chẳng hạn lúc nhận request, đến lúc hoàn thành một mốc khác, chẳng hạn lúc response sẵn sàng hoặc đã được gửi. Nó gần với trải nghiệm của người gọi API nhất.

Độ trễ này có thể bao gồm:

- Hàng đợi của web server, executor hoặc scheduler.
- Thời gian lấy kết nối từ pool.
- Xử lý nghiệp vụ trước và sau truy vấn.
- Thời gian gọi driver và trao đổi dữ liệu qua mạng.
- Thời gian đọc toàn bộ ResultSet và chuyển đổi từng hàng.
- Chờ các dịch vụ khác, retry, serialization và gửi response.

Cần định nghĩa rõ điểm kết thúc. “Response đã được tạo”, “đã ghi vào socket” và “client đã nhận đủ response” là các mốc khác nhau. Chúng không thể thay thế nhau khi phân tích độ trễ đầu cuối.

### 2.2. Thời gian câu lệnh ở phía cơ sở dữ liệu

Hệ quản trị có thể ghi nhận thời gian của một câu lệnh, thời gian thực thi một kế hoạch, thời gian phục vụ request hoặc các bộ đếm thời gian theo từng loại sự kiện chờ. Ý nghĩa chính xác phụ thuộc hệ quản trị và công cụ quan sát.

Một số số liệu phía cơ sở dữ liệu có thể bao gồm thời gian chờ khóa, chờ đọc trang, chờ ghi log hoặc chờ tài nguyên dùng chung. Vì vậy, “thời gian ở cơ sở dữ liệu” không đồng nghĩa với “thời gian CPU thực hiện câu lệnh”.

Khi dùng log truy vấn chậm hoặc thống kê theo mẫu truy vấn, hãy đọc định nghĩa của trường thời gian. Có hệ thống ghi thời gian trôi qua (elapsed time), có hệ thống cung cấp thêm CPU time, wait time hoặc số lần truy cập. Một số thống kê tổng hợp thời gian qua nhiều lần thực thi; một số công cụ ghi từng lần. Không so sánh hai con số khi chưa hiểu đơn vị, phạm vi và cách tổng hợp.

### 2.3. Thời gian chờ tài nguyên bên trong cơ sở dữ liệu

Một câu lệnh có thể đã đến máy chủ nhưng chưa được xử lý ngay vì phải chờ một tài nguyên:

- Chờ khóa do giao dịch khác đang giữ.
- Chờ đọc trang dữ liệu từ thiết bị lưu trữ.
- Chờ ghi log giao dịch hoặc hoàn tất thao tác ghi.
- Chờ latch, mutex hoặc cấu trúc đồng bộ nội bộ.
- Chờ CPU khi máy chủ quá tải hoặc có nhiều tác vụ cạnh tranh.
- Chờ tài nguyên cho phép nối, sắp xếp hoặc thao tác trung gian.

Các khoảng chờ này thường nằm trong thời gian trôi qua mà máy chủ ghi nhận cho câu lệnh. Chúng cần được phân loại riêng nếu muốn biết nút thắt là CPU, I/O, khóa hay một tài nguyên khác.

## 3. Những khoảng chờ thường phát sinh ở ứng dụng

### 3.1. Chờ lấy kết nối từ connection pool

Ứng dụng thường dùng connection pool để tái sử dụng kết nối và giới hạn số phiên đồng thời đến cơ sở dữ liệu. Khi không còn kết nối rảnh, request phải chờ đến khi một kết nối được trả về hoặc hết thời gian chờ.

Khoảng chờ này xảy ra trước khi câu lệnh được gửi đến cơ sở dữ liệu. Do đó, truy vấn có thể rất nhanh ở phía máy chủ nhưng API vẫn chậm vì pool không cấp kết nối kịp thời.

Các dấu hiệu cần quan sát:

- Thời gian trung bình và phân vị p95, p99 khi lấy kết nối.
- Số kết nối đang hoạt động, rảnh và đang chờ.
- Số lần chờ, timeout khi lấy kết nối và thời gian giữ kết nối.
- Tỷ lệ request giữ kết nối trong khi không thực hiện truy vấn.
- Sự khác biệt giữa thời gian lấy kết nối và thời gian thực thi SQL.

Pool cạn có thể xuất phát từ số lượng kết nối cấu hình thấp so với tải, truy vấn chậm, giao dịch mở lâu, ứng dụng quên đóng tài nguyên hoặc giữ kết nối trong lúc làm việc không liên quan đến cơ sở dữ liệu. Tăng kích thước pool ngay lập tức có thể làm số phiên đồng thời tăng quá cao, khiến cơ sở dữ liệu tranh chấp CPU, bộ nhớ và I/O nhiều hơn.

### 3.2. Xếp hàng ở thread pool hoặc executor

Request có thể đã đến máy chủ ứng dụng nhưng chưa có thread hoặc worker để xử lý. Khi đó, thời gian chờ nằm trước cả thao tác lấy kết nối.

Nếu chỉ đo từ lúc bắt đầu xử lý controller, bạn có thể bỏ sót khoảng chờ trước đó. Cần phân biệt thời điểm request được nhận, được đưa vào hàng đợi và thực sự bắt đầu chạy.

Khi tải tăng, hàng đợi ứng dụng có thể dài lên dù cơ sở dữ liệu vẫn còn khả năng xử lý. Ngược lại, cơ sở dữ liệu quá chậm có thể khiến các thread giữ kết nối lâu, làm executor bị chiếm dụng và tạo ra hàng đợi ở ứng dụng. Hai hiện tượng có thể khuếch đại lẫn nhau.

### 3.3. Chờ mạng và các lượt trao đổi dữ liệu

Driver gửi câu lệnh qua mạng và chờ phản hồi. Độ trễ mạng, số lượt round trip, kích thước dữ liệu và cách driver lấy kết quả đều có thể ảnh hưởng thời gian.

Một truy vấn có thể thực hiện nhanh ở máy chủ nhưng cần nhiều lượt trao đổi để lấy dữ liệu hoặc thực hiện nhiều câu lệnh tuần tự. Ứng dụng gọi cơ sở dữ liệu qua mạng có độ trễ cao sẽ nhạy cảm với số round trip hơn môi trường có mạng nội bộ độ trễ thấp.

Ví dụ, một vòng lặp phát sinh một truy vấn cho từng phần tử có thể tạo hàng trăm lượt trao đổi. Mỗi truy vấn riêng lẻ nhanh nhưng tổng thời gian vẫn lớn. Đây là một dạng vấn đề N+1 thường gặp khi tải dữ liệu liên quan.

### 3.4. Đọc và chuyển đổi tập kết quả

Thời gian gọi executeQuery không nhất thiết bao gồm việc ứng dụng tiêu thụ hết kết quả. Tùy driver và cấu hình fetch, lần gọi có thể nhận metadata và một phần hàng đầu tiên; các hàng còn lại được lấy theo từng đợt khi ứng dụng duyệt ResultSet.

Vì vậy, nếu ứng dụng chỉ đo quanh executeQuery rồi kết luận truy vấn đã hoàn tất, kết quả có thể thiếu phần thời gian đọc dữ liệu. Một tập kết quả lớn có thể làm tăng:

- Số lượt fetch qua mạng.
- Thời gian giải mã dữ liệu của driver.
- Thời gian chuyển kiểu và ánh xạ sang object.
- Lượng bộ nhớ giữ các hàng trong ứng dụng.
- Thời gian garbage collection hoặc áp lực bộ nhớ.
- Thời gian serialization trước khi gửi response.

Cần đo riêng thời gian nhận kết quả ban đầu và thời gian duyệt hết kết quả. Nếu chỉ cần 20 hàng, việc truy vấn và chuyển hàng trăm nghìn bản ghi có thể là lãng phí dù thời gian thực thi phía máy chủ không quá cao.

### 3.5. Công việc nằm trong một giao dịch

Một giao dịch có thể gồm nhiều câu lệnh và cả công việc ở ứng dụng. Ví dụ, ứng dụng mở giao dịch, đọc dữ liệu, gọi dịch vụ bên ngoài, xử lý nghiệp vụ rồi mới cập nhật và commit. Trong thời gian chờ dịch vụ bên ngoài, giao dịch vẫn có thể giữ kết nối hoặc khóa.

Hãy phân biệt:

- Thời gian giữ kết nối: từ lúc lấy kết nối đến lúc trả lại pool.
- Thời gian giao dịch: từ lúc bắt đầu đến lúc commit hoặc rollback.
- Thời gian từng câu lệnh: từng lần SQL được thực thi.
- Thời gian chờ khóa: phần thời gian câu lệnh hoặc giao dịch bị chặn bởi khóa.

Một giao dịch kéo dài không nhất thiết có một câu SQL chậm. Nó có thể chứa nhiều khoảng chờ hoặc nhiều thao tác ứng dụng. Giao dịch mở lâu còn có thể giữ khóa, giữ phiên bản dữ liệu hoặc làm chậm các giao dịch khác, tùy cơ chế của hệ quản trị.

## 4. Những khoảng thời gian ở phía cơ sở dữ liệu

### 4.1. Phân tích, lập kế hoạch và thực thi

Trước khi thực hiện, hệ quản trị có thể cần phân tích cú pháp, kiểm tra đối tượng, tối ưu truy vấn và chọn kế hoạch. Một số hệ quản trị có thể tái sử dụng kế hoạch đã biên dịch; một số tình huống vẫn phát sinh công việc lập kế hoạch hoặc biên dịch lại.

Khi phân tích một câu lệnh chậm, cần biết số đo đang bao gồm giai đoạn nào. Nếu thời gian lập kế hoạch đáng kể, nguyên nhân có thể liên quan đến câu lệnh động, số lượng câu lệnh khác nhau, invalidation hoặc hành vi tái sử dụng kế hoạch. Nếu thời gian thực thi chiếm phần lớn, hãy xem kế hoạch, số hàng, phép nối, sắp xếp và truy cập dữ liệu.

Không mặc định rằng thời gian lập kế hoạch luôn bằng không hoặc luôn đáng kể. Hãy dùng số liệu của hệ quản trị đang vận hành.

### 4.2. CPU time và elapsed time

CPU time là thời gian CPU thực sự được dùng cho một công việc theo định nghĩa của hệ điều hành hoặc hệ quản trị. Elapsed time là thời gian trôi qua trên đồng hồ từ lúc bắt đầu đến lúc kết thúc một khoảng đo.

Một truy vấn có elapsed time 900 ms nhưng CPU time chỉ 80 ms có thể đã dành phần lớn thời gian để chờ khóa, I/O, scheduler hoặc tài nguyên khác. Ngược lại, elapsed time và CPU time đều cao có thể cho thấy câu lệnh đang xử lý nhiều dữ liệu hoặc thực hiện phép tính tốn kém.

CPU time có thể được cộng dồn qua nhiều worker hoặc core trong truy vấn song song; do đó, trong một số hệ thống, CPU time lớn hơn elapsed time là điều có thể xảy ra. Hãy xem cách hệ quản trị định nghĩa chỉ số và có tính đến xử lý song song hay không.

### 4.3. Wait events và thời gian chờ

Wait event là thông tin mô tả loại tài nguyên mà một tác vụ đang chờ. Tên sự kiện, cách nhóm và độ chi tiết tùy hệ quản trị. Khi xem số liệu chờ, hãy đặt câu hỏi:

- Tác vụ đang chờ loại tài nguyên nào?
- Sự kiện xảy ra bao lâu và bao nhiêu lần?
- Có tập trung vào một truy vấn, một bảng, một hàng hoặc một nhóm phiên không?
- Sự kiện xuất hiện khi tải thấp hay chỉ khi tải cao?
- Sau khi chờ kết thúc, tác vụ tiếp tục làm gì?

Ví dụ, thời gian chờ khóa tăng có thể liên quan đến giao dịch giữ khóa lâu hoặc nhiều giao dịch cập nhật cùng dữ liệu. Chờ đọc vật lý tăng có thể liên quan đến working set lớn, cache miss hoặc quét dữ liệu rộng. Chờ ghi log có thể phản ánh tải ghi và cách commit được thực hiện.

Không kết luận từ tên một wait event đơn lẻ. Hãy kết hợp sự kiện chờ với session, truy vấn, kế hoạch thực thi, mức đồng thời và thời điểm xảy ra.

### 4.4. Thời gian chờ không đồng nghĩa với thời gian lãng phí

Một số thao tác chờ là hệ quả cần thiết của việc bảo vệ tính đúng đắn hoặc phục vụ dữ liệu từ thiết bị lưu trữ. Mục tiêu tối ưu là giảm phần chờ không cần thiết và loại bỏ nguyên nhân gây tranh chấp, chứ không phải xóa mọi wait event.

Ví dụ, khóa bảo đảm các giao dịch không ghi đè dữ liệu của nhau. Bỏ cơ chế khóa có thể làm thời gian chờ giảm nhưng gây sai lệch dữ liệu. Tương tự, đọc đĩa là cần thiết khi dữ liệu không nằm trong bộ nhớ; tăng cache có thể giúp nếu working set phù hợp nhưng không giải quyết mọi loại I/O.

## 5. Thiết kế phép đo ở cả hai phía

Một phép đo tốt phải có mốc bắt đầu và kết thúc rõ ràng, đơn vị thống nhất, phạm vi quan sát đủ hẹp và khả năng liên kết dữ liệu giữa ứng dụng với cơ sở dữ liệu.

### 5.1. Đo theo từng span

Ở ứng dụng, nên tách ít nhất các khoảng sau nếu kiến trúc cho phép:

| Khoảng đo | Bắt đầu | Kết thúc |
|---|---|---|
| Hàng đợi ứng dụng | Request được nhận hoặc enqueue | Worker bắt đầu xử lý |
| Lấy kết nối | Bắt đầu gọi pool | Nhận được kết nối |
| Chuẩn bị câu lệnh | Bắt đầu chuẩn bị/bind | Sẵn sàng gửi |
| Gọi câu lệnh | Bắt đầu gọi driver | Nhận kết quả ban đầu |
| Duyệt kết quả | Bắt đầu đọc hàng | Đọc xong hoặc dừng đọc |
| Giao dịch | Begin | Commit hoặc rollback |
| Xử lý ứng dụng | Bắt đầu logic liên quan | Hoàn tất logic |
| Request | Nhận request | Response hoàn tất theo mốc đã chọn |

Không phải ứng dụng nào cũng cần tạo tất cả span. Hãy bắt đầu từ các khoảng có khả năng giải thích độ trễ lớn và thêm chi tiết khi cần.

### 5.2. Dùng đồng hồ đơn điệu để đo thời lượng

Trong Java, System.nanoTime() phù hợp để đo khoảng thời gian trong cùng một tiến trình vì nó là đồng hồ đơn điệu, không bị điều chỉnh theo giờ hệ thống như đồng hồ lịch. Không dùng hai giá trị thời gian lịch ở hai máy khác nhau để trừ trực tiếp rồi kết luận chính xác về duration.

Ví dụ sau đo thời gian lấy kết nối, thời gian gọi executeQuery và thời gian tiêu thụ toàn bộ ResultSet:

~~~java
long requestStart = System.nanoTime();

try (Connection connection = dataSource.getConnection()) {
    long connectionReady = System.nanoTime();

    try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT id, status FROM orders WHERE tenant_id = ?")) {

        statement.setLong(1, tenantId);

        long executeStart = System.nanoTime();

        try (ResultSet resultSet = statement.executeQuery()) {
            long firstResultReady = System.nanoTime();

            int rowCount = 0;
            while (resultSet.next()) {
                long id = resultSet.getLong("id");
                String status = resultSet.getString("status");
                processOrder(id, status);
                rowCount++;
            }

            long resultConsumed = System.nanoTime();

            long poolWaitNanos = connectionReady - requestStart;
            long executeCallNanos = firstResultReady - executeStart;
            long consumeNanos = resultConsumed - firstResultReady;

            recordDatabaseCallMetrics(
                poolWaitNanos,
                executeCallNanos,
                consumeNanos,
                rowCount
            );
        }
    }
}
long requestElapsedNanos = System.nanoTime() - requestStart;
recordRequestElapsed(requestElapsedNanos);
~~~

Đây là ví dụ minh họa cách đặt mốc đo. Trong ứng dụng thực tế, mốc requestStart cần được đặt tại ranh giới phù hợp; nếu muốn đo riêng hàng đợi executor, phải ghi thêm thời điểm enqueue và thời điểm worker bắt đầu. Việc gọi processOrder có thể bao gồm logic ứng dụng nên consumeNanos không chỉ là thời gian mạng hoặc driver lấy hàng.

Đặc biệt, executeCallNanos không phải thời gian thực thi thuần ở cơ sở dữ liệu. Nó có thể bao gồm thời gian gửi yêu cầu, chờ máy chủ, nhận phản hồi ban đầu và hành vi buffer của driver. consumeNanos có thể bao gồm các lượt fetch bổ sung, giải mã dữ liệu, chuyển đổi kiểu và xử lý từng hàng. Cần dùng số liệu phía máy chủ để phân tách phần xử lý tại cơ sở dữ liệu.

Không ghi giá trị nhạy cảm của tham số truy vấn vào metric hoặc log chỉ để liên kết các khoảng thời gian. Hãy ưu tiên query fingerprint, mã tương quan và thông tin đã được làm sạch.

### 5.3. Liên kết số liệu ứng dụng với số liệu cơ sở dữ liệu

Để so sánh hai phía, cần một cách nhận diện lần gọi hoặc nhóm truy vấn. Các lựa chọn thường gặp:

- Request ID hoặc trace ID đi từ ứng dụng qua các lớp xử lý.
- Query fingerprint hoặc normalized SQL để gom các câu lệnh có cùng cấu trúc.
- Tên thao tác nghiệp vụ hoặc tên repository method.
- Session ID hoặc connection ID nếu hệ quản trị và công cụ quan sát cho phép.
- Thời điểm bắt đầu/kết thúc, kết hợp với đồng bộ đồng hồ và sai số đã biết.

Không phải hệ quản trị nào cũng hỗ trợ truyền trace ID theo cùng cách. Có thể dùng application name, session context, comment có kiểm soát hoặc thuộc tính tracing do driver hỗ trợ. Tránh thêm comment ngẫu nhiên vào mọi câu SQL nếu việc đó làm mất khả năng gom nhóm fingerprint hoặc tạo ra quá nhiều dạng câu lệnh.

Đồng hồ giữa ứng dụng và cơ sở dữ liệu có thể lệch. Hãy dùng timestamp để tìm khoảng thời gian gần đúng, nhưng dùng trace/span hoặc mã tương quan để liên kết chính xác hơn. Duration nên được đo bằng đồng hồ đơn điệu trong từng tiến trình. Nếu cần so sánh timestamp giữa máy, cần hiểu mức đồng bộ và sai số của đồng hồ.

## 6. Đọc số liệu mà không nhầm lẫn phạm vi

Một số nhầm lẫn thường gặp khi điều tra độ trễ:

| Nhầm lẫn | Vì sao sai | Cách kiểm tra |
|---|---|---|
| Thời gian executeQuery là thời gian SQL trên máy chủ | Lệnh gọi driver có thể bao gồm mạng, chờ phản hồi và buffer | So sánh span ứng dụng với elapsed/CPU/wait phía máy chủ |
| Query log ghi 100 ms nên API chỉ nên mất 100 ms | API còn chờ pool, xử lý dữ liệu, mạng và công việc khác | Đo từng span từ request đến response |
| Cơ sở dữ liệu CPU thấp nghĩa là không có vấn đề | Phiên có thể đang chờ khóa, I/O hoặc tài nguyên | Kiểm tra wait events, session state và elapsed time |
| Một câu lệnh nhanh nghĩa là giao dịch nhanh | Giao dịch có thể gồm nhiều câu lệnh và khoảng chờ ở ứng dụng | Đo thời gian từ begin đến commit, cùng thời gian giữ kết nối |
| Chỉ cần đo lần đầu tiên của truy vấn | Cache, pool, kế hoạch đã chuẩn bị và tải có thể khác nhau | Đo nhiều lần ở điều kiện đại diện, phân biệt warm/cold |
| Thời gian đọc ResultSet bằng không vì executeQuery nhanh | Driver có thể lấy phần còn lại khi ứng dụng duyệt kết quả | Đo riêng vòng lặp đọc và số hàng thực tế |
| Tổng thời gian các span luôn bằng thời gian request | Span có thể lồng nhau hoặc chạy song song | Xem quan hệ cha/con và đường găng của trace |

Một ví dụ quan trọng: nếu executeQuery mất 30 ms nhưng duyệt ResultSet mất 700 ms, đừng vội tối ưu kế hoạch SQL. Hãy kiểm tra số hàng trả về, kích thước từng hàng, fetch size, số lượt round trip, tốc độ mạng và công việc ánh xạ dữ liệu ở ứng dụng. Ngược lại, nếu thời gian lấy kết nối chỉ 2 ms, thời gian duyệt kết quả 10 ms nhưng span gọi câu lệnh mất 900 ms và máy chủ ghi nhận lock wait 850 ms, cần điều tra giao dịch đang giữ khóa.

## 7. Phân vị và thống kê theo workload

Thời gian trung bình có thể che giấu những request rất chậm. Ví dụ, phần lớn truy vấn hoàn tất trong 20 ms nhưng một số ít request chờ pool hoặc khóa trong vài giây. Trung bình có thể vẫn trông chấp nhận được trong khi người dùng gặp độ trễ lớn.

Nên theo dõi:

- p50: mốc giữa của phân bố, mô tả trải nghiệm phổ biến.
- p90 hoặc p95: cho thấy nhóm request chậm hơn phần lớn.
- p99: giúp quan sát phần đuôi chậm, nơi timeout và tranh chấp thường dễ lộ ra.
- Tần suất: số lần gọi trong một khoảng thời gian.
- Tổng thời gian tiêu thụ: giúp tìm mẫu truy vấn gây tác động tích lũy lớn.
- Tỷ lệ timeout và lỗi: cho biết request không hoàn tất đúng hạn.
- Phân bố theo endpoint, query fingerprint, tenant hoặc loại thao tác phù hợp.

Không gộp mọi câu lệnh vào một phân bố duy nhất. Một truy vấn đọc hồ sơ người dùng và một truy vấn báo cáo lớn có đặc điểm khác nhau. Hãy phân nhóm theo mẫu truy vấn hoặc nghiệp vụ để so sánh các đối tượng tương đồng.

Cần chú ý cách tính phân vị. p99 của từng instance rồi lấy trung bình không nhất thiết bằng p99 của toàn bộ request. Nếu có nhiều instance, hãy dùng histogram hoặc dữ liệu phân phối có thể tổng hợp đúng theo phương pháp của hệ thống giám sát.

## 8. Quy trình điều tra một API chậm

Khi một API chậm, hãy đi theo các bước có thể kiểm chứng:

**Bước 1: Xác nhận triệu chứng.** Xác định endpoint, khoảng thời gian, tỷ lệ request bị ảnh hưởng, p50/p95/p99 và lỗi. Kiểm tra có phải mọi request đều chậm hay chỉ một nhóm tham số, tenant hoặc thời điểm.

**Bước 2: Xem trace đầu cuối.** Tìm span chiếm phần lớn thời gian. Phân biệt thời gian chờ hàng đợi, lấy kết nối, gọi cơ sở dữ liệu, đọc kết quả, dịch vụ ngoài và xử lý response.

**Bước 3: Nếu pool wait lớn, kiểm tra pool.** Xem active/idle/pending, thời gian giữ kết nối, timeout và giao dịch mở lâu. Tìm đường xử lý không đóng ResultSet, Statement hoặc Connection đúng cách. Xem có đoạn code giữ kết nối trong lúc gọi dịch vụ khác hay không.

**Bước 4: Nếu thời gian gọi cơ sở dữ liệu lớn, đối chiếu phía máy chủ.** Tìm câu lệnh bằng fingerprint hoặc mã tương quan. So sánh elapsed time, CPU time, wait events, số hàng đọc và trả về. Nếu máy chủ ghi nhận thời gian ngắn hơn nhiều, xem xét mạng, driver, round trip hoặc điểm đo ở ứng dụng.

**Bước 5: Nếu đọc kết quả lâu, kiểm tra kích thước và cách fetch.** Xem số hàng, số cột, kích thước dữ liệu lớn, fetch size, số lượt lấy dữ liệu và thời gian mapping. Xác định ứng dụng có thật sự cần toàn bộ kết quả không.

**Bước 6: Nếu thời gian chờ trong cơ sở dữ liệu cao, phân loại wait.** Với lock wait, tìm phiên giữ khóa và giao dịch liên quan. Với I/O wait, kiểm tra số trang đọc, working set và kế hoạch. Với CPU cao, xem truy vấn xử lý bao nhiêu hàng và các bước tốn CPU.

**Bước 7: Đưa ra giả thuyết và thử một thay đổi.** Mỗi thay đổi cần nêu rõ khoảng thời gian dự kiến giảm, chỉ số phụ cần theo dõi và điều kiện tải dùng để kiểm chứng.

**Bước 8: Đo lại toàn bộ đường đi.** Một cải thiện trong thời gian SQL chưa chắc cải thiện request nếu pool wait hoặc mapping vẫn chiếm phần lớn. So sánh cùng loại workload và cùng điều kiện tải trước/sau.

## 9. Ví dụ thực tế: API chậm nhưng truy vấn phía máy chủ nhanh

Giả sử một API lấy danh sách đơn hàng có độ trễ p95 khoảng 780 ms. Nhóm vận hành xem log truy vấn và thấy câu SQL hoàn tất nhanh, nên ban đầu nghi ngờ vấn đề nằm ngoài cơ sở dữ liệu.

Một trace đại diện cho request chậm cho thấy:

| Khoảng đo | Thời gian |
|---|---:|
| Chờ lấy kết nối từ pool | 220 ms |
| Gọi executeQuery đến khi có kết quả ban đầu | 180 ms |
| Duyệt ResultSet và xử lý từng hàng | 240 ms |
| Logic ứng dụng sau khi đọc dữ liệu | 80 ms |
| Các phần còn lại của request | 60 ms |
| **Tổng độ trễ** | **780 ms** |

Phía cơ sở dữ liệu ghi nhận câu lệnh có elapsed time khoảng 70 ms, trong đó lock wait chiếm 45 ms, CPU time 15 ms và I/O wait 10 ms. Các số liệu phía máy chủ là thông tin chi tiết nằm trong khoảng gọi cơ sở dữ liệu ở trace; không cộng thêm 70 ms lần nữa vào tổng 780 ms.

Từ bằng chứng này có thể rút ra một số nhận định:

1. Pool wait 220 ms là một phần lớn của độ trễ. Cần tìm lý do kết nối bị giữ lâu hoặc số kết nối rảnh không đủ trong thời điểm đó.
2. Thời gian máy chủ ghi nhận chỉ là một phần của khoảng executeQuery 180 ms. Phần còn lại có thể liên quan đến truyền yêu cầu, mạng, driver và nhận phản hồi.
3. Duyệt kết quả mất 240 ms. Cần xem số hàng, fetch size, dữ liệu trả về và thời gian xử lý từng hàng.
4. Lock wait 45 ms cho thấy có tranh chấp ở cơ sở dữ liệu. Cần xác định giao dịch giữ khóa và mức ảnh hưởng theo tải.
5. Chỉ tối ưu SQL để giảm vài mili giây có thể không cải thiện đáng kể p95 nếu pool wait và đọc kết quả vẫn chiếm phần lớn.

Giả sử nhóm phát hiện một số request giữ kết nối trong lúc gọi dịch vụ ngoài. Sau khi thay đổi để hoàn tất công việc ngoài cơ sở dữ liệu trước khi mở giao dịch, thời gian giữ kết nối giảm và pool wait giảm. Nhóm đo lại dưới cùng mức tải, đồng thời xác nhận thời gian chờ khóa, lỗi và tính đúng đắn dữ liệu không xấu đi. Đây là một thay đổi có cơ sở vì nó xử lý đúng khoảng chờ đã được đo.

Ví dụ trên chỉ minh họa cách đọc số liệu. Trong hệ thống thực tế, các khoảng đo có thể chồng lấp và các giá trị sẽ thay đổi theo driver, hệ quản trị, cấu hình pool, kích thước dữ liệu và tải.

## 10. Chọn hướng tối ưu theo vị trí phát sinh độ trễ

Sau khi tách thời gian, hãy chọn biện pháp phù hợp với nguyên nhân được đo:

| Vị trí chậm | Hướng điều tra hoặc cải thiện |
|---|---|
| Hàng đợi ứng dụng | Xem giới hạn executor, mức đồng thời, backpressure và công việc giữ worker |
| Chờ connection pool | Tìm kết nối bị giữ lâu, giao dịch mở lâu, rò rỉ tài nguyên và cấu hình pool |
| Chuẩn bị câu lệnh | Kiểm tra số lượng SQL khác nhau, bind parameter, tái sử dụng statement và kế hoạch |
| Elapsed time phía máy chủ cao, CPU cao | Đọc kế hoạch, số hàng, phép nối, sắp xếp, biểu thức và truy cập dữ liệu |
| Elapsed time cao, CPU thấp | Kiểm tra wait events, khóa, I/O, scheduler và tài nguyên dùng chung |
| Lock wait cao | Tìm giao dịch giữ khóa, rút ngắn giao dịch, giảm xung đột và chuẩn hóa thứ tự truy cập |
| I/O wait cao | Kiểm tra working set, lượng dữ liệu đọc, chỉ mục, cache và thiết bị lưu trữ |
| Fetch/result consumption cao | Giảm số hàng/cột không cần thiết, phân trang phù hợp, kiểm tra fetch size và mapping |
| Nhiều round trip | Điều tra N+1, gom thao tác theo lô hoặc giảm số lượt gọi tuần tự |
| Serialization/response cao | Giảm payload, tránh chuyển đổi lặp và kiểm tra định dạng dữ liệu |

Các hướng trên là nơi bắt đầu điều tra. Ví dụ, tăng fetch size có thể giảm round trip nhưng cũng làm driver lấy nhiều dữ liệu hơn trong mỗi đợt, tăng bộ nhớ và có thể gây lãng phí nếu ứng dụng dừng đọc sớm. Tăng pool size có thể giảm chờ cấp kết nối nhưng làm tăng mức đồng thời lên cơ sở dữ liệu. Mọi thay đổi phải được đo lại ở cả ứng dụng và máy chủ.

## 11. Những sai lầm khi đo và tối ưu

**Chỉ đo một lần.** Một lần chạy có thể chịu ảnh hưởng của cache, kế hoạch vừa được tạo, tải nền hoặc kết nối mới. Hãy đo nhiều lần và ghi lại điều kiện.

**Chỉ nhìn thời gian trung bình.** Độ trễ đuôi có thể bị che khuất. Theo dõi phân vị và phân bố theo workload.

**Đo quanh executeQuery rồi bỏ qua ResultSet.** Driver có thể fetch theo từng đợt. Hãy đo đến khi ứng dụng đọc xong dữ liệu cần thiết.

**Dùng timestamp lịch để đo duration.** Đồng hồ hệ thống có thể được điều chỉnh. Dùng đồng hồ đơn điệu trong mỗi tiến trình để đo thời lượng.

**So sánh timestamp giữa các máy mà không xét sai số.** Đồng hồ ứng dụng và cơ sở dữ liệu có thể lệch. Dùng trace và mã tương quan, đồng thời hiểu độ chính xác của đồng bộ thời gian.

**Cộng các span lồng nhau.** Span truy vấn có thể nằm bên trong span repository, transaction và request. Cộng tất cả sẽ đếm trùng thời gian.

**Tăng pool hoặc timeout mà không tìm nguyên nhân.** Timeout dài hơn chỉ khiến request chờ lâu hơn; pool lớn hơn có thể đẩy quá nhiều phiên đến cơ sở dữ liệu. Hãy xác định nơi hàng đợi hình thành và khả năng xử lý thực tế.

**Đưa toàn bộ SQL và tham số nhạy cảm vào log.** Điều này có thể làm lộ dữ liệu và tạo lượng log lớn. Ưu tiên fingerprint, mã tương quan và trường đã được làm sạch.

**Tối ưu SQL khi điểm nghẽn ở ứng dụng.** Nếu phần lớn thời gian nằm ở pool wait, fetch hoặc xử lý kết quả, thay đổi kế hoạch SQL có thể ít tác dụng. Hãy xử lý phần thời gian lớn và có bằng chứng trước.

## 12. Checklist kiểm tra một request chậm

- [ ] Đã định nghĩa mốc bắt đầu và kết thúc của độ trễ request.
- [ ] Đã tách thời gian hàng đợi ứng dụng và thời gian chờ lấy kết nối.
- [ ] Đã đo riêng khoảng gọi driver và khoảng tiêu thụ ResultSet.
- [ ] Đã biết số hàng và kích thước dữ liệu được trả về.
- [ ] Đã liên kết truy vấn ứng dụng với query fingerprint hoặc trace tương ứng.
- [ ] Đã phân biệt elapsed time, CPU time và thời gian chờ phía cơ sở dữ liệu.
- [ ] Đã kiểm tra lock wait, I/O wait và các wait event có liên quan.
- [ ] Đã xem thời gian giữ kết nối và thời gian giao dịch.
- [ ] Đã theo dõi p50, p95, p99, thông lượng và tỷ lệ lỗi theo workload.
- [ ] Đã kiểm tra khả năng chồng lấp giữa các span để tránh cộng trùng.
- [ ] Đã thử một thay đổi có giả thuyết và đo lại toàn bộ đường đi.
- [ ] Đã xác nhận tính đúng đắn dữ liệu và tác động đến các thao tác khác.

## 13. Nguyên tắc cần ghi nhớ

Độ trễ mà ứng dụng quan sát được là kết quả của toàn bộ đường đi từ lúc nhận request đến lúc hoàn tất response. Thời gian câu lệnh phía cơ sở dữ liệu chỉ là một phần của đường đi đó. Ngay cả bên trong cơ sở dữ liệu, elapsed time cũng có thể bao gồm CPU, khóa, I/O và các loại chờ tài nguyên khác.

Muốn tìm đúng nguyên nhân, hãy đo ở cả ứng dụng và cơ sở dữ liệu, xác định phạm vi từng đồng hồ, liên kết các số liệu bằng trace hoặc query fingerprint và phân tích phân vị theo workload. Khi đã biết phần thời gian nào chiếm ưu thế, hãy hình thành giả thuyết, thay đổi có kiểm soát và đo lại cả độ trễ đầu cuối lẫn tác động lên cơ sở dữ liệu. Cách làm này giúp tránh tối ưu nhầm một câu SQL trong khi người dùng vẫn phải chờ ở một thành phần khác.
