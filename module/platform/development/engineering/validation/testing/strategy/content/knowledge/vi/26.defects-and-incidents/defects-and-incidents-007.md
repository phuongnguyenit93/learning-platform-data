# Xử lý lỗi không ổn định hoặc chỉ xuất hiện trong môi trường thực tế

Một số lỗi xuất hiện không đều: cùng một thao tác có lúc thành công, có lúc thất bại; kiểm thử chạy lại có thể đạt mà không có thay đổi mã; hoặc lỗi chỉ xuất hiện trên production dù các môi trường phát triển và staging đều hoạt động bình thường. Đây là nhóm lỗi khó điều tra vì điều kiện gây lỗi có thể phụ thuộc vào thời điểm, tải, dữ liệu, thứ tự sự kiện, cấu hình, phiên bản, quyền truy cập hoặc tương tác giữa nhiều dịch vụ.

Lỗi không ổn định thường được gọi là *intermittent defect* hoặc *flaky behavior*. Lỗi chỉ xuất hiện trong môi trường thực tế có thể là lỗi production-only. Hai nhóm có thể giao nhau: một race condition chỉ xảy ra khi tải production tăng, hoặc một lỗi cấu hình chỉ ảnh hưởng một vùng triển khai.

Xử lý hiệu quả đòi hỏi nhóm phải bảo toàn bằng chứng trước khi trạng thái thay đổi, xác định phạm vi và điều kiện xuất hiện, so sánh môi trường, xây dựng giả thuyết có thể kiểm chứng, giảm thiểu tác động an toàn và chuyển điều kiện thực tế thành kiểm thử hồi quy. Chạy lại nhiều lần hoặc thêm retry có thể giúp thu thập thêm dữ liệu, nhưng không tự giải thích nguyên nhân và có thể che giấu lỗi.

Bài học này trình bày cách phối hợp giữa phát triển, kiểm thử, nghiệp vụ và vận hành để điều tra những lỗi khó tái hiện, xử lý sự cố đang ảnh hưởng người dùng và giảm khả năng lỗi tái diễn.

## 1. Phân biệt lỗi không ổn định và lỗi chỉ xuất hiện trong production

Hai loại lỗi cần cách tiếp cận khác nhau, dù đôi khi cùng một nguyên nhân.

### Lỗi không ổn định

Lỗi không ổn định xuất hiện trong những lần thực thi có vẻ tương đương nhưng kết quả khác nhau. Ví dụ:

- Một test API đạt ở lần đầu nhưng timeout ở lần sau.
- Một thao tác lưu đôi khi tạo hai bản ghi.
- Một test giao diện thỉnh thoảng không tìm thấy nút dù trang đã tải.
- Một worker xử lý sự kiện trễ hoặc sai thứ tự trong một số lần chạy.
- Một job chạy thành công khi thực hiện riêng nhưng thất bại khi chạy song song.

Nguyên nhân thường liên quan đến thời gian, đồng thời, dữ liệu dùng chung, thứ tự thực thi, phụ thuộc bên ngoài hoặc trạng thái không được khởi tạo và dọn dẹp nhất quán.

### Lỗi chỉ xuất hiện trong môi trường thực tế

Lỗi production-only xuất hiện khi hệ thống hoạt động với dữ liệu, tải, cấu hình, người dùng hoặc phụ thuộc thực tế. Ví dụ:

- Một truy vấn chậm chỉ khi bảng có hàng triệu bản ghi.
- Người dùng ở một khu vực không thể đăng nhập do cấu hình định tuyến hoặc danh tính khác biệt.
- Một giao dịch lỗi khi nhà cung cấp bên ngoài trả về mã phản hồi chưa từng có trong sandbox.
- Lỗi phân quyền chỉ xuất hiện với tổ hợp vai trò và tài nguyên hiếm gặp.
- Một tiến trình nền xử lý backlog lớn bị hết bộ nhớ.

Lỗi này có thể ổn định trong một điều kiện production cụ thể, nhưng không xuất hiện trong môi trường thử nghiệm vì dữ liệu, tải, quyền, cấu hình hoặc hành vi phụ thuộc khác nhau.

### So sánh nhanh

| Đặc điểm | Lỗi không ổn định | Lỗi chỉ xuất hiện trong production |
|---|---|---|
| Dấu hiệu | Kết quả thay đổi giữa các lần chạy | Môi trường thử nghiệm không tái hiện được |
| Điều kiện thường gặp | Thời gian, đồng thời, thứ tự, trạng thái dùng chung | Dữ liệu, tải, cấu hình, quyền, topology, phụ thuộc thật |
| Bằng chứng hữu ích | Lịch sử lần chạy, timestamp, trace, thứ tự sự kiện | Log production, metric, dữ liệu đã bảo vệ, cấu hình và phiên bản |
| Hướng điều tra | Tìm biến số gây khác biệt giữa các lần chạy | Tìm khác biệt có ý nghĩa giữa production và môi trường khác |
| Cạm bẫy | Retry đến khi đạt rồi kết luận không có lỗi | Cho rằng không tái hiện ở staging nghĩa là lỗi không tồn tại |

Không nên mặc định lỗi production-only là lỗi hạ tầng hoặc lỗi không ổn định là lỗi kiểm thử. Cả hai đều cần xác minh bằng chứng trước khi kết luận.

## 2. Ưu tiên giảm tác động trước khi điều tra sâu

Khi lỗi đang ảnh hưởng người dùng, giao dịch hoặc dữ liệu, nhóm cần đánh giá mức độ khẩn cấp và ngăn hậu quả tiếp tục tăng. Điều tra nguyên nhân gốc không phải lúc nào cũng là hành động đầu tiên.

### Đánh giá nhanh tác động

Xác định:

- Chức năng hoặc hành trình nào bị ảnh hưởng.
- Người dùng, khách hàng, khu vực hoặc tenant nào gặp lỗi.
- Lỗi có gây mất dữ liệu, sai giao dịch, lộ thông tin hoặc vượt quyền không.
- Tần suất và xu hướng lỗi đang tăng hay giảm.
- Có thể ngăn lỗi bằng feature flag, giới hạn lưu lượng hoặc dừng job không.
- Có dữ liệu hoặc trạng thái nào cần bảo toàn trước khi khôi phục.
- Ai có quyền quyết định rollback, tắt chức năng hoặc áp dụng biện pháp giảm thiểu.

### Chọn biện pháp giảm thiểu phù hợp

Tùy nguyên nhân và mức rủi ro, có thể:

- Tắt tạm tính năng bằng feature flag.
- Dừng hoặc giảm tốc độ một worker gây lỗi.
- Giới hạn lưu lượng hoặc phạm vi người dùng.
- Quay lui ứng dụng nếu phiên bản trước tương thích với schema và dữ liệu hiện tại.
- Chuyển sang chế độ chỉ đọc hoặc quy trình thủ công đã được phê duyệt.
- Tạm ngừng một loại giao dịch để tránh ghi sai dữ liệu.
- Chuyển phụ thuộc sang phương án dự phòng đã được xác minh.

Không nên tự ý xóa dữ liệu, reset môi trường, vô hiệu hóa kiểm tra bảo mật hoặc chuyển endpoint chưa được phê duyệt. Một biện pháp giảm thiểu cần có người sở hữu, điều kiện kích hoạt, phạm vi và cách xác minh.

### Giữ nguyên bằng chứng

Trước khi restart, rollback hoặc xóa trạng thái, hãy thu thập log, trace, metric, thông tin phiên bản và dữ liệu chẩn đoán cần thiết. Một số lỗi chỉ có thể điều tra khi trạng thái bất thường vẫn còn. Việc bảo toàn bằng chứng phải tuân thủ quy định bảo mật và quyền riêng tư.

## 3. Bảo toàn bằng chứng ngay khi lỗi xuất hiện

Lỗi không ổn định thường biến mất sau khi request tiếp theo thành công hoặc tiến trình được khởi động lại. Nếu chỉ ghi lại thông báo “đã xảy ra lỗi”, nhóm có thể không đủ dữ liệu để tìm nguyên nhân.

Một bản ghi sự cố hữu ích nên có:

- Thời điểm chính xác và múi giờ.
- Mã tương quan của request, trace hoặc giao dịch.
- Phiên bản ứng dụng, commit, image hoặc build.
- Môi trường, vùng triển khai, instance, pod hoặc worker.
- Người dùng hoặc tenant ở dạng định danh đã bảo vệ.
- Loại thao tác và trạng thái trước/sau.
- Request và response đã loại bỏ dữ liệu nhạy cảm.
- Mã lỗi, exception và stack trace.
- Thời gian xử lý từng bước.
- Tình trạng phụ thuộc tại thời điểm lỗi.
- Cấu hình và feature flag liên quan.
- Dấu hiệu tải, tài nguyên và độ trễ.
- Những thao tác đã thực hiện để giảm thiểu.

### Ghi nhận timestamp có ý nghĩa

Trong hệ thống phân tán, các máy có thể có độ lệch đồng hồ. Cần ghi timestamp theo định dạng thống nhất, thường là UTC, đồng thời giữ thông tin múi giờ khi cần. Với một luồng có nhiều dịch vụ, trace ID và span ID thường hữu ích hơn việc chỉ so sánh thời gian log.

Không nên giả định hai dòng log có thứ tự ghi là thứ tự sự kiện thực tế. Cần xem thời gian sự kiện, thời gian nhận, độ trễ mạng và cơ chế đồng bộ.

### Gắn định danh xuyên suốt luồng

Một request có thể đi qua gateway, dịch vụ đơn hàng, thanh toán, broker và worker nền. Nếu mỗi thành phần tạo một mã riêng không liên kết, nhóm khó nối các dấu vết.

Dùng correlation ID hoặc trace context để liên kết các bước. Với thông điệp bất đồng bộ, đưa định danh tương quan vào metadata của message và giữ nó qua retry hoặc dead-letter queue khi phù hợp.

### Không ghi bí mật vào log

Trước khi thu thập hoặc chia sẻ bằng chứng, cần loại bỏ token, mật khẩu, khóa, dữ liệu thanh toán và thông tin cá nhân không cần thiết. Dùng định danh giả hoặc đã băm khi phù hợp. Chỉ người có quyền mới được truy cập dữ liệu chẩn đoán nhạy cảm.

## 4. Xác định phạm vi và mẫu hình xuất hiện

Thay vì bắt đầu bằng một giả thuyết kỹ thuật, hãy mô tả chính xác mẫu hình lỗi.

Các chiều nên khảo sát:

- **Thời gian:** bắt đầu từ lúc nào, theo giờ cao điểm hay sau một tác vụ định kỳ?
- **Tần suất:** bao nhiêu lần lỗi trên tổng số lần thực hiện?
- **Phạm vi:** tất cả người dùng hay một nhóm, tenant, vùng hoặc thiết bị?
- **Phiên bản:** chỉ xảy ra sau một lần triển khai hoặc trên một phiên bản cụ thể?
- **Dữ liệu:** liên quan đến kích thước, trạng thái, tuổi hoặc hình dạng dữ liệu nào?
- **Tải:** xảy ra khi đồng thời cao, backlog lớn hoặc tài nguyên gần giới hạn?
- **Thao tác:** chỉ xuất hiện khi người dùng nhấn lặp, refresh hoặc thực hiện hai hành động gần nhau?
- **Phụ thuộc:** có liên quan đến API ngoài, broker, database hoặc DNS?
- **Kết quả:** lỗi hoàn toàn, timeout, dữ liệu sai, trạng thái không nhất quán hay chỉ hiển thị sai?

### Dùng mẫu số khi mô tả tỷ lệ lỗi

Câu “lỗi xảy ra thường xuyên” không đủ để so sánh. Nên ghi số lần thất bại trên tổng số cơ hội, theo một khoảng thời gian và nhóm điều kiện cụ thể.

Ví dụ: “Trong 30 phút, 18 trên 2.400 request tạo đơn thất bại; 16 request thuộc vùng triển khai B và đều gọi dịch vụ tồn kho phiên bản 7.” Thông tin này tạo hướng điều tra rõ hơn so với “đôi khi không tạo được đơn”.

Tỷ lệ cần được phân nhóm theo endpoint, vùng, phiên bản hoặc tenant để tránh số trung bình toàn hệ thống che khuất một nhóm bị ảnh hưởng nghiêm trọng.

### Tìm thay đổi gần thời điểm bắt đầu

Đối chiếu thời điểm lỗi bắt đầu với:

- Triển khai ứng dụng hoặc cấu hình.
- Migration schema và backfill dữ liệu.
- Thay đổi feature flag.
- Cập nhật chứng thư, secret hoặc quyền.
- Thay đổi DNS, network policy hoặc load balancer.
- Thay đổi ở nhà cung cấp.
- Lịch chạy batch, backup hoặc tác vụ định kỳ.
- Tăng tải hoặc thay đổi hành vi người dùng.

Sự trùng khớp thời gian là manh mối, chưa phải bằng chứng nguyên nhân. Cần kiểm tra liệu thay đổi đó có tạo ra điều kiện dẫn đến lỗi hay không.

## 5. So sánh môi trường có hệ thống

Khi lỗi chỉ xuất hiện ở production, cần so sánh những khác biệt có thể ảnh hưởng đến hành vi. Không nên chỉ so sánh tên môi trường hoặc phiên bản ứng dụng.

### Những khác biệt cần xem xét

| Nhóm | Điều cần so sánh |
|---|---|
| Ứng dụng | Build, commit, dependency, runtime và feature flag |
| Cấu hình | Biến môi trường, timeout, pool size, cache, giới hạn |
| Hạ tầng | CPU, bộ nhớ, số instance, topology và loại máy |
| Dữ liệu | Kích thước, phân bố, trạng thái, tuổi và tính đa dạng |
| Cơ sở dữ liệu | Phiên bản, schema, index, query plan, transaction |
| Mạng | DNS, TLS, proxy, latency, packet loss và routing |
| Quyền | Vai trò, policy, token scope, tenant và service account |
| Phụ thuộc | Phiên bản API, quota, giới hạn tốc độ và sandbox/production |
| Tải | Đồng thời, throughput, backlog và mẫu lưu lượng |
| Vận hành | Scheduler, autoscaling, restart, backup và quy trình triển khai |

### So sánh cấu hình theo cách có thể kiểm tra

Nên xuất cấu hình đã loại bỏ bí mật và so sánh có cấu trúc. Không sao chép toàn bộ secret production sang staging để thử. Với mỗi khác biệt, ghi:

- Giá trị ở môi trường bị lỗi.
- Giá trị ở môi trường không bị lỗi.
- Lý do khác biệt.
- Khả năng ảnh hưởng đến đường đi gây lỗi.
- Cách kiểm tra giả thuyết an toàn.

### Không làm thay đổi nhiều biến cùng lúc

Nếu đồng thời thay timeout, số worker, phiên bản database và cấu hình cache, rồi lỗi biến mất, nhóm không biết thay đổi nào có tác dụng. Ưu tiên thử nghiệm có kiểm soát, thay một yếu tố hoặc một nhóm yếu tố có liên quan, ghi lại kết quả và có cách hoàn nguyên.

## 6. Tạo điều kiện tái hiện gần với thực tế

Không phải lúc nào cũng có thể tái hiện production nguyên trạng. Mục tiêu là tái tạo các yếu tố có liên quan đến lỗi trong một môi trường an toàn.

### Dùng dữ liệu đại diện

Dữ liệu kiểm thử cần phản ánh các đặc điểm có thể kích hoạt lỗi:

- Bản ghi lớn hoặc có nhiều quan hệ.
- Dữ liệu lịch sử từ nhiều phiên bản.
- Trường null, thiếu hoặc không chuẩn hóa.
- Giá trị biên, chuỗi Unicode hoặc định dạng thời gian.
- Phân bố lệch, nhóm dữ liệu hiếm.
- Trạng thái chuyển tiếp hoặc bản ghi đang được cập nhật.
- Dữ liệu tạo đồng thời bởi nhiều tiến trình.

Không nên sao chép dữ liệu production nguyên trạng nếu chưa được phép và bảo vệ. Hãy dùng dữ liệu tổng hợp, dữ liệu đã ẩn danh hoặc trích xuất tối thiểu theo quy trình được phê duyệt.

### Tạo tải phù hợp

Nếu lỗi chỉ xuất hiện khi tải cao, cần tái tạo concurrency, throughput, kích thước request và tỷ lệ lỗi phụ thuộc. Tải thử nghiệm nên tăng có kiểm soát, có giới hạn tài nguyên và không làm ảnh hưởng dịch vụ thật.

### Mô phỏng điều kiện phụ thuộc

Có thể dùng service virtualization hoặc fault injection để mô phỏng:

- Phản hồi chậm.
- Timeout và kết nối bị ngắt.
- Phản hồi 429 hoặc 5xx.
- Message lặp hoặc đến sai thứ tự.
- Phụ thuộc trả dữ liệu không đầy đủ.
- Broker tạm ngừng hoặc tăng backlog.
- Database từ chối kết nối hoặc khóa lâu.

Mô phỏng giúp cô lập logic ứng dụng. Khi cần xác minh hành vi thật của nhà cung cấp hoặc hạ tầng, vẫn phải có kiểm thử tích hợp trên môi trường phù hợp.

### Tạo lại đúng phiên bản và cấu hình

Nếu lỗi chỉ xuất hiện sau một bản phát hành, cần xác định chính xác image, commit, migration và cấu hình liên quan. Không nên dùng “bản mới nhất” thay cho định danh phiên bản vì nội dung có thể thay đổi giữa các lần chạy.

## 7. Điều tra lỗi phụ thuộc vào thời gian

Thời gian là nguyên nhân phổ biến của lỗi chỉ xuất hiện ở một số lần chạy.

Các vấn đề thường gặp:

- Hết hạn token hoặc session.
- Job chạy đúng thời điểm đổi ngày hoặc tháng.
- Múi giờ khác nhau giữa ứng dụng và database.
- Đồng hồ giữa các máy lệch nhau.
- Timeout quá ngắn hoặc không nhất quán.
- Cache hết hạn đúng lúc request đến.
- Race condition giữa tác vụ định kỳ và request.
- Kiểm thử giả định thời gian xử lý cố định.

### Kiểm tra thời gian và múi giờ

Xác minh ứng dụng, database, worker và dịch vụ ngoài dùng quy ước thời gian nhất quán. Lưu thời điểm theo UTC khi phù hợp và chuyển sang múi giờ người dùng ở lớp hiển thị.

Chú ý các thời điểm ranh giới như nửa đêm, cuối tháng, năm nhuận, thời điểm chuyển giờ mùa hè ở khu vực có áp dụng và thời gian hết hạn chính xác.

### Tiêm nguồn thời gian có thể điều khiển

Trong mã ứng dụng, nên sử dụng abstraction như Clock thay vì gọi trực tiếp đồng hồ hệ thống ở nhiều nơi. Điều này giúp kiểm thử các trường hợp hết hạn và ranh giới thời gian một cách xác định.

Ví dụ Java:

~~~java
class SessionPolicy {
    private final Clock clock;

    SessionPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Kiểm thử có thể dùng thời gian cố định:

~~~java
@Test
void expiresSessionAtTheConfiguredInstant() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-11-16T08:00:00Z"),
        ZoneOffset.UTC
    );
    SessionPolicy policy = new SessionPolicy(clock);

    assertTrue(policy.isExpired(
        Instant.parse("2026-11-16T08:00:00Z")
    ));
}
~~~

Cần kiểm tra cả trước, đúng thời điểm và sau thời điểm hết hạn để xác định quy tắc biên.

### Phân biệt timeout từng bước và deadline toàn luồng

Một request có thể đi qua nhiều dịch vụ. Nếu mỗi dịch vụ tự đặt timeout dài hơn phần thời gian còn lại, tổng thời gian có thể vượt deadline của người dùng. Nên truyền deadline hoặc ngân sách thời gian còn lại theo luồng khi kiến trúc hỗ trợ.

## 8. Điều tra race condition và lỗi đồng thời

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các thao tác đồng thời. Những lỗi này thường khó tái hiện bằng cách chạy một test đơn lẻ.

Ví dụ:

- Hai request cùng đọc số lượng tồn kho trước khi cả hai trừ hàng.
- Hai worker cùng xử lý một message.
- Một tiến trình xóa cache trong khi tiến trình khác đang ghi.
- Một request đọc trạng thái cũ trong lúc transaction khác cập nhật.
- Hai test cùng sửa một tài khoản hoặc bản ghi dùng chung.

### Dấu hiệu nhận biết

- Lỗi tăng khi số worker hoặc request đồng thời tăng.
- Thứ tự log thay đổi giữa các lần chạy.
- Có bản ghi trùng, thiếu hoặc trạng thái chuyển sai.
- Chạy riêng thì đạt nhưng chạy song song thì lỗi.
- Lỗi giảm khi thêm delay hoặc chạy chậm hơn.
- Có deadlock, lock timeout hoặc optimistic locking conflict.

### Cách điều tra

1. Xác định tài nguyên hoặc trạng thái được nhiều tiến trình truy cập.
2. Thu thập trace và timestamp cho từng thao tác.
3. Ghi nhận khóa, transaction, version hoặc sequence liên quan.
4. Tạo test có rào đồng bộ để kích hoạt cạnh tranh có kiểm soát.
5. Tăng dần mức đồng thời và giữ dữ liệu riêng cho mỗi lần chạy.
6. Kiểm tra invariant sau khi tất cả thao tác hoàn tất.
7. Lặp lại với thứ tự khác nhau và lưu seed hoặc lịch thực thi nếu công cụ hỗ trợ.

Không nên thêm sleep để “sửa” race condition. Delay có thể làm lỗi ít xuất hiện hơn nhưng không bảo đảm thứ tự hoặc tính nguyên tử.

### Kiểm tra tính nguyên tử và idempotency

Với thao tác có thể được gửi lại, cần xác định một request lặp có tạo ra tác dụng phụ lần thứ hai không. Dùng idempotency key, ràng buộc duy nhất hoặc cơ chế giao dịch phù hợp. Kiểm thử cần gửi request đồng thời và lặp lại, sau đó xác minh chỉ có kết quả nghiệp vụ hợp lệ.

## 9. Điều tra lỗi bất đồng bộ và eventual consistency

Trong hệ thống dùng message broker hoặc event-driven architecture, dữ liệu có thể chưa nhất quán ngay sau khi request hoàn tất. Một test kiểm tra quá sớm có thể báo lỗi dù hệ thống đang hoạt động đúng theo thiết kế; ngược lại, một độ trễ bất thường có thể che giấu vấn đề thực sự.

Cần phân biệt:

- Độ trễ bình thường theo hợp đồng.
- Message bị trễ hoặc backlog tăng.
- Message bị gửi lặp.
- Message đến sai thứ tự.
- Consumer lỗi hoặc bị restart.
- Message vào dead-letter queue.
- Trạng thái được cập nhật một phần giữa nhiều dịch vụ.

### Dùng chờ có điều kiện thay vì sleep cố định

Thay vì đợi một số giây tùy ý rồi đọc trạng thái, kiểm thử nên chờ điều kiện mong đợi với deadline và polling interval hợp lý.

Ví dụ Java:

~~~java
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() -> {
        Order order = orderRepository.findById(orderId).orElseThrow();
        assertEquals(OrderStatus.CONFIRMED, order.status());
    });
~~~

Ví dụ dùng thư viện chờ điều kiện. Trong thực tế, cần cấu hình timeout dựa trên hợp đồng hệ thống và giữ lại thông tin khi hết thời gian chờ. Không nên tăng timeout quá lớn để che giấu backlog hoặc lỗi consumer.

### Kiểm tra tính đúng đắn cuối cùng

Khi luồng hoàn tất, xác minh các bất biến: không có xử lý trùng, trạng thái cuối hợp lệ, dữ liệu liên quan nhất quán và message lỗi được xử lý theo chính sách. Nếu chỉ kiểm tra rằng message đã được gửi, chưa đủ để chứng minh consumer đã xử lý thành công.

## 10. Điều tra lỗi phụ thuộc dữ liệu

Lỗi production-only thường xuất hiện khi dữ liệu thực tế có quy mô hoặc hình dạng khác fixture trong test.

Các nguyên nhân thường gặp:

- Dữ liệu lớn hơn nhiều so với môi trường thử nghiệm.
- Phân bố dữ liệu lệch khiến một truy vấn chậm.
- Có bản ghi null hoặc giá trị cũ ngoài dự kiến.
- Quan hệ dữ liệu bị thiếu hoặc trùng.
- Dữ liệu lịch sử không tuân theo quy tắc mới.
- Một tenant có số lượng bản ghi vượt xa mức trung bình.
- Ký tự đặc biệt hoặc Unicode gây lỗi xử lý.
- Trạng thái dữ liệu chuyển tiếp chưa được xử lý.

### Thu thập đặc điểm thay vì sao chép toàn bộ dữ liệu

Ghi nhận kích thước, phân bố, số lượng quan hệ, tỷ lệ null, giá trị biên và trạng thái. Tạo bộ dữ liệu tổng hợp có cùng đặc điểm cần thiết để tái hiện.

Nếu cần lấy mẫu từ production, phải áp dụng quyền truy cập, ẩn danh, giảm thiểu dữ liệu và thời hạn lưu theo chính sách. Không đưa dữ liệu nhạy cảm vào ticket, chat hoặc log không được bảo vệ.

### Kiểm tra truy vấn và kế hoạch thực thi

Với lỗi hiệu năng, so sánh query plan, index, cardinality, lock và số lượng bản ghi được đọc. Truy vấn chạy nhanh trên vài trăm bản ghi trong staging không chứng minh hiệu năng trên dữ liệu production.

### Kiểm tra dữ liệu lịch sử

Sau migration hoặc thay đổi quy tắc, dữ liệu cũ có thể chưa được chuẩn hóa. Cần xác định ứng dụng mới có thể đọc cả dữ liệu cũ và mới không, và có bước backfill hoặc xử lý ngoại lệ nào còn thiếu.

## 11. Điều tra lỗi cấu hình, quyền và topology

Cấu hình production có thể khác staging vì yêu cầu bảo mật, quy mô, vùng triển khai hoặc nhà cung cấp. Một giá trị sai hoặc quyền thiếu có thể chỉ ảnh hưởng một số request.

### Cấu hình

So sánh:

- Timeout và retry.
- Pool kết nối và số worker.
- Cache TTL và giới hạn bộ nhớ.
- Feature flag.
- Endpoint và region.
- Mức logging.
- Giới hạn payload.
- Cấu hình serializer và parser.
- Tùy chọn runtime và phiên bản thư viện.

Cần kiểm tra cấu hình thực tế mà tiến trình đã nạp, không chỉ file cấu hình được lưu trong repository. Secret có thể được xoay vòng hoặc inject trong lúc triển khai.

### Quyền và danh tính

Xem xét:

- Role và permission của người dùng.
- Scope và audience của token.
- Service account.
- Policy theo tenant hoặc khu vực.
- Quyền trên database, bucket, queue hoặc secret.
- Hết hạn chứng thư và quá trình xoay vòng khóa.

Không nên mở quyền rộng để xác nhận giả thuyết. Thử nghiệm cần dùng tài khoản kiểm thử với quyền tối thiểu và môi trường phù hợp.

### Topology và định tuyến

Kiểm tra số instance, load balancer, sticky session, DNS, proxy, network policy, TLS termination và vùng triển khai. Một lỗi chỉ xuất hiện trên một instance có thể liên quan đến cấu hình không đồng nhất hoặc cache cục bộ.

## 12. Điều tra lỗi phụ thuộc dịch vụ bên ngoài

Sandbox thường không phản ánh đầy đủ hành vi production. Nhà cung cấp có thể dùng cấu hình, dữ liệu, quota, phiên bản API hoặc cơ chế bảo vệ khác nhau.

Cần thu thập:

- Endpoint và phiên bản API.
- Request ID do nhà cung cấp trả về.
- Mã trạng thái và response đã làm sạch.
- Thời gian gọi và độ trễ.
- Tình trạng quota hoặc rate limit.
- Cấu hình xác thực và chứng thư.
- Thay đổi gần đây từ nhà cung cấp.
- Hành vi retry và callback.
- Thời gian xảy ra sự cố ở phía nhà cung cấp.

### Phân biệt lỗi phía mình và lỗi phía nhà cung cấp

Một mã 5xx không tự động chứng minh nhà cung cấp là nguyên nhân. Request có thể không hợp lệ hoặc vi phạm giới hạn. Cần kiểm tra request đã gửi, response, request ID và hợp đồng. Khi liên hệ nhà cung cấp, chỉ chia sẻ dữ liệu tối thiểu đã được phép.

### Không retry mù quáng

Retry một thao tác không idempotent sau timeout có thể tạo giao dịch trùng nếu nhà cung cấp đã xử lý request nhưng response bị mất. Trước khi retry, cần biết hợp đồng idempotency và cách tra cứu trạng thái giao dịch. Với kết quả không chắc chắn, có thể cần đối soát trước khi gửi lại.

## 13. Phân tích log, metric và distributed trace

Ba loại dữ liệu quan sát bổ sung cho nhau.

- **Log:** mô tả sự kiện, lỗi và ngữ cảnh tại một thời điểm.
- **Metric:** cho thấy xu hướng và phân bố theo thời gian, ví dụ tỷ lệ lỗi, độ trễ, backlog và mức sử dụng tài nguyên.
- **Trace:** nối các bước của một request xuyên qua nhiều dịch vụ.

### Bắt đầu từ triệu chứng có thể đo

Ví dụ, nếu người dùng báo thao tác lưu đơn đôi khi thất bại, hãy tìm metric về tỷ lệ lỗi của endpoint, phân nhóm theo phiên bản và vùng, sau đó chọn một trace thất bại để xem span nào có độ trễ hoặc lỗi bất thường.

### Tìm tương quan, không chỉ tìm từ khóa

Một thông báo exception có thể xuất hiện ở nhiều nguyên nhân. Hãy kết hợp:

- Trace ID.
- Request ID.
- User/tenant ID đã bảo vệ.
- Phiên bản và instance.
- Timestamp.
- Loại thao tác.
- Mã lỗi.
- Trạng thái phụ thuộc.

### Kiểm tra chất lượng observability

Nếu log thiếu định danh, metric không phân nhóm theo vùng hoặc trace bị đứt ở message broker, đó là một khoảng trống cần sửa. Điều tra khó khăn có thể là dấu hiệu hệ thống chưa được thiết kế để quan sát đầy đủ.

Không nên tăng logging vô hạn trong production. Log quá nhiều có thể tăng chi phí, làm lộ dữ liệu và gây tải. Hãy thêm trường có cấu trúc, lấy mẫu có kiểm soát và giới hạn thời gian bật log chi tiết.

## 14. Xây dựng giả thuyết và kiểm tra có kiểm soát

Một quy trình điều tra tốt không bắt đầu bằng việc thay đổi ngẫu nhiên. Hãy chuyển triệu chứng thành giả thuyết có thể kiểm chứng.

Ví dụ:

- Giả thuyết: lỗi chỉ xảy ra trên một instance do cấu hình cache khác.
- Bằng chứng cần: tỷ lệ lỗi theo instance, hash cấu hình không chứa secret, trace và trạng thái cache.
- Phép kiểm tra: so sánh instance bị lỗi với instance hoạt động tốt trong cùng khoảng thời gian.
- Kết quả dự kiến nếu giả thuyết đúng: lỗi tập trung ở instance có cấu hình khác.
- Kết quả làm giả thuyết yếu đi: lỗi xuất hiện đồng đều trên mọi instance.

### Dùng bảng giả thuyết

| Giả thuyết | Bằng chứng ủng hộ | Bằng chứng phản bác | Phép kiểm tra tiếp theo |
|---|---|---|---|
| Pool kết nối cạn | Timeout tăng khi tải cao | Pool vẫn còn kết nối rảnh | Đối chiếu wait time và số kết nối |
| Race condition | Lỗi tăng khi request đồng thời | Không có thao tác ghi cạnh tranh | Tạo test đồng thời có kiểm soát |
| Dữ liệu lịch sử bất thường | Chỉ một nhóm bản ghi lỗi | Bản ghi mới cũng lỗi | Tạo fixture có cùng đặc điểm |
| Phụ thuộc ngoài chậm | Span gọi ngoài chiếm phần lớn latency | Request lỗi không gọi dịch vụ đó | So sánh trace và request ID |
| Cấu hình instance lệch | Lỗi tập trung trên một instance | Các instance có cấu hình giống nhau | So sánh cấu hình đã nạp |

Ghi lại cả kết quả không ủng hộ giả thuyết. Điều đó giúp nhóm tránh quay lại cùng một hướng điều tra và hạn chế thiên kiến xác nhận.

### Thay đổi một yếu tố có kiểm soát

Nếu có thể tái hiện, hãy giữ cố định dữ liệu, phiên bản và tải, sau đó thay một biến số liên quan. Với hệ thống phân tán, có thể cần thử nghiệm theo từng nhóm yếu tố như cấu hình mạng hoặc lịch thực thi, nhưng phải ghi rõ mọi thay đổi.

Không thử nghiệm trực tiếp trên production nếu chưa có phạm vi, quyền, giám sát và phương án dừng được phê duyệt.

## 15. Sử dụng canary, feature flag và replay an toàn

Một số lỗi chỉ có thể quan sát trong production. Có thể cần xác minh bản sửa bằng rollout giới hạn, nhưng phải kiểm soát rủi ro.

### Canary hoặc rollout theo tỷ lệ

Triển khai cho một nhóm instance hoặc tỷ lệ lưu lượng nhỏ. So sánh metric trước và sau theo cùng nhóm điều kiện. Cần có ngưỡng dừng, người theo dõi và khả năng quay lui.

Không nên so sánh hai nhóm có dữ liệu hoặc lưu lượng khác biệt lớn mà không điều chỉnh. Một canary không có đủ mẫu hoặc thời gian quan sát có thể tạo kết luận sai.

### Feature flag

Dùng flag để giới hạn người dùng hoặc tắt hành vi mới. Cần kiểm tra flag được áp dụng nhất quán trên backend, worker và các đường truy cập khác. Flag không nên trở thành cơ chế che giấu lỗi vĩnh viễn; cần có người sở hữu và ngày loại bỏ.

### Replay request hoặc event

Replay có thể giúp tái hiện lỗi từ request hoặc message đã xảy ra. Trước khi thực hiện:

- Loại bỏ hoặc thay thế dữ liệu nhạy cảm.
- Xác định thao tác có side effect hay không.
- Dùng môi trường cô lập hoặc chế độ chỉ đọc khi phù hợp.
- Bảo đảm idempotency hoặc dùng bản sao dữ liệu.
- Giới hạn tốc độ và phạm vi.
- Ghi nhận nguồn, thời điểm và phiên bản.
- Không phát lại giao dịch tài chính hoặc thông báo thật ngoài quy trình được phê duyệt.

Replay không kiểm soát có thể tạo giao dịch trùng, gửi email thật hoặc làm sai dữ liệu.

## 16. Xử lý flaky test và phân biệt với lỗi sản phẩm

Một test không ổn định có thể phản ánh lỗi thật trong hệ thống hoặc lỗi trong chính test. Cần phân loại thay vì mặc định là flaky test rồi tắt.

### Nguyên nhân thuộc kiểm thử

- Dữ liệu dùng chung giữa các test.
- Không cleanup trạng thái.
- Chờ bằng sleep cố định.
- Bộ định vị giao diện không ổn định.
- Phụ thuộc vào thứ tự chạy.
- Mock hoặc stub không xác định.
- Test dùng đồng hồ hoặc số ngẫu nhiên thật.
- Assertion kiểm tra quá sớm.
- Tài nguyên dùng chung bị tranh chấp.

### Nguyên nhân thuộc sản phẩm hoặc môi trường

- Race condition trong mã.
- Timeout do hiệu năng suy giảm.
- Deadlock hoặc lock contention.
- Phụ thuộc ngoài không ổn định.
- Cấu hình instance không đồng nhất.
- Lỗi xử lý retry hoặc message lặp.
- Giới hạn tài nguyên hoặc quota.
- Dữ liệu không nhất quán.

### Quy trình xử lý

1. Giữ lại lần thất bại đầu tiên và toàn bộ thông tin môi trường.
2. Chạy lại có kiểm soát để xác định tần suất, không xóa kết quả ban đầu.
3. Chạy test riêng và chạy song song để so sánh.
4. Kiểm tra dữ liệu, thời gian, thứ tự và phụ thuộc.
5. Xác định test có đang phơi bày một lỗi sản phẩm thật hay không.
6. Sửa nguyên nhân gốc.
7. Chạy lặp lại trong điều kiện đại diện và xác nhận tính ổn định.
8. Gỡ trạng thái cách ly và cập nhật báo cáo.

Nếu phải quarantine test, cần người sở hữu, lý do, thời hạn và kế hoạch khôi phục. Không nên bỏ qua một test chỉ vì nó gây phiền cho pipeline.

## 17. Tái hiện lỗi bằng kiểm thử có mục tiêu

Khi đã có giả thuyết, hãy thiết kế một kiểm thử nhỏ nhất có thể tái hiện điều kiện gây lỗi. Kiểm thử này có thể là unit, integration, contract, load, concurrency hoặc E2E tùy nguyên nhân.

### Tạo test hồi quy từ điều kiện đã tìm ra

Một test hồi quy tốt nên:

- Tái hiện điều kiện thực sự liên quan.
- Kiểm tra hành vi quan sát được hoặc bất biến quan trọng.
- Có dữ liệu độc lập và có thể tái tạo.
- Không phụ thuộc thời gian thực nếu có thể điều khiển.
- Có timeout hợp lý và thông báo lỗi hữu ích.
- Chạy ổn định trong pipeline phù hợp.
- Không chỉ kiểm tra một chi tiết triển khai mong manh.

### Chọn đúng tầng kiểm thử

Nếu lỗi là race condition trong logic cập nhật số lượng, có thể cần unit hoặc integration test đồng thời. Nếu lỗi do cấu hình DNS ở production, unit test không đủ; cần kiểm thử hạ tầng hoặc smoke test trong môi trường tương đương. Nếu lỗi do hợp đồng nhà cung cấp, cần contract test và kiểm thử tích hợp thật.

Không cần tạo một E2E cho mọi lỗi. Hãy chọn tầng có thể tái hiện nguyên nhân với chi phí và độ ổn định phù hợp.

### Ghi rõ giới hạn

Nếu không thể tái hiện đầy đủ production, ghi rõ điều kiện nào đã được mô phỏng và điều kiện nào chưa. Một test gần đúng vẫn có giá trị nhưng không nên được mô tả như bằng chứng đã tái hiện toàn bộ sự cố.

## 18. Ví dụ: lỗi chỉ xuất hiện khi tải cao

Giả sử API tạo đơn hoạt động bình thường trong staging nhưng production thỉnh thoảng ghi nhận số lượng tồn kho âm vào giờ cao điểm.

### Bằng chứng ban đầu

- Lỗi tập trung ở một số SKU có lượng đặt hàng cao.
- Tỷ lệ lỗi tăng khi số request đồng thời tăng.
- Log cho thấy hai request đọc cùng số lượng tồn kho trước khi ghi.
- Chạy tuần tự trong staging không tái hiện được.

### Giả thuyết

Hai request cùng đọc giá trị tồn kho cũ và cùng trừ số lượng mà không có cơ chế đồng bộ hoặc cập nhật có điều kiện.

### Cách kiểm tra

- Tạo dữ liệu với số lượng tồn kho nhỏ.
- Dùng barrier để hai request đọc trạng thái trước khi cập nhật.
- Gửi hai request đồng thời.
- Xác minh tồn kho không âm và không tạo hai đơn vượt số lượng.
- Lặp lại với nhiều lịch thực thi và mức đồng thời.

### Khắc phục và hồi quy

Có thể dùng cập nhật nguyên tử, optimistic locking, transaction hoặc cơ chế reservation phù hợp với nghiệp vụ. Sau sửa, kiểm thử đồng thời cần xác minh invariant và kết quả nghiệp vụ, đồng thời chạy kiểm thử tích hợp với database thực tế.

Trong production, nhóm cần xác định các bản ghi đã bị ảnh hưởng và đối soát trước khi chỉ kết luận rằng bản sửa đã ngăn lỗi mới.

## 19. Ví dụ: lỗi chỉ xuất hiện với dữ liệu khách hàng lịch sử

Giả sử một phiên bản mới thêm trường normalized_email. Hầu hết khách hàng mới hoạt động bình thường, nhưng một số tài khoản cũ không thể đăng nhập.

### Bằng chứng

- Lỗi tập trung ở tài khoản được tạo từ nhiều năm trước.
- Bản ghi mới có normalized_email, một số bản ghi cũ có giá trị null.
- Log cho thấy truy vấn đăng nhập dùng trường mới nhưng migration chưa backfill toàn bộ.
- Staging chỉ có dữ liệu seed mới nên không tái hiện.

### Điều tra

- Phân nhóm bản ghi theo thời điểm tạo và trạng thái migration.
- Tạo fixture tổng hợp có cùng cấu trúc cũ.
- Kiểm tra ứng dụng mới có xử lý null hoặc fallback đúng không.
- Kiểm tra tiến độ backfill và các bản ghi bị bỏ sót.
- Xác minh dữ liệu sau chuyển đổi bằng đối soát.

### Khắc phục

Có thể triển khai logic đọc tương thích trong thời gian chuyển tiếp, tiếp tục backfill theo lô và theo dõi số bản ghi chưa chuyển. Sau đó bổ sung test cho dữ liệu lịch sử và migration để bảo vệ các lần thay đổi schema tiếp theo.

Không nên chỉ cập nhật fixture để mọi bản ghi đều có trường mới; cách đó có thể che khuất lỗi tương thích với dữ liệu cũ.

## 20. Ví dụ: lỗi gián đoạn do nhà cung cấp bên ngoài

Giả sử một số giao dịch thanh toán bị timeout. Người dùng thử lại và đôi khi bị ghi nhận hai giao dịch.

### Điều cần xác định

- Nhà cung cấp đã nhận và xử lý request trước khi timeout chưa?
- Request có idempotency key không?
- Retry có dùng cùng khóa và payload không?
- Có thể tra cứu trạng thái giao dịch bằng mã tham chiếu không?
- Webhook có đến trễ hoặc lặp không?
- Hệ thống có phân biệt trạng thái thất bại với trạng thái chưa xác định không?

### Phương án xử lý

Không gửi lại giao dịch mù quáng. Nếu trạng thái chưa xác định, tra cứu với nhà cung cấp hoặc chờ callback theo hợp đồng. Dùng idempotency key nhất quán và đối soát các giao dịch có khả năng trùng.

### Kiểm thử hồi quy

Mô phỏng tình huống nhà cung cấp xử lý giao dịch nhưng response bị mất, sau đó ứng dụng retry. Xác minh chỉ có một giao dịch nghiệp vụ và trạng thái cuối cùng được đồng bộ. Kiểm thử tích hợp thật cần xác nhận hợp đồng idempotency và webhook của nhà cung cấp.

## 21. Quản lý dữ liệu và quyền riêng tư khi điều tra production

Điều tra lỗi production có thể cần dữ liệu thật, nhưng không có nghĩa mọi thành viên đều cần truy cập trực tiếp vào dữ liệu đó.

Nguyên tắc:

- Chỉ thu thập dữ liệu cần thiết để kiểm tra giả thuyết.
- Dùng dữ liệu tổng hợp hoặc ẩn danh khi có thể.
- Giới hạn quyền và thời gian truy cập.
- Không đưa thông tin nhạy cảm vào ticket hoặc kênh trao đổi không phù hợp.
- Ghi nhận nguồn và cách xử lý dữ liệu trích xuất.
- Xóa dữ liệu tạm khi hết mục đích sử dụng.
- Tuân thủ quy trình ứng phó bảo mật nếu nghi ngờ lộ dữ liệu.

Nếu lỗi liên quan đến truy cập trái phép, không nên tự điều tra bằng cách mở rộng quyền hoặc sao chép thêm dữ liệu. Cần phối hợp với nhóm bảo mật và người sở hữu dữ liệu.

## 22. Phối hợp giữa phát triển, kiểm thử, nghiệp vụ và vận hành

Lỗi không ổn định hoặc production-only thường vượt qua ranh giới một nhóm. Cần xác định rõ ai cung cấp bằng chứng, ai điều tra, ai giảm thiểu và ai quyết định.

| Vai trò | Đóng góp chính |
|---|---|
| Vận hành/SRE | Phát hiện sự cố, metric, log, trace, trạng thái hạ tầng, điều phối và phục hồi |
| Phát triển | Phân tích mã, thiết kế, concurrency, cấu hình ứng dụng, sửa lỗi và cung cấp bản vá |
| Kiểm thử | Tái hiện có kiểm soát, phân loại test flaky, thiết kế kiểm thử hồi quy và xác minh bản sửa |
| Nghiệp vụ/chủ sản phẩm | Đánh giá tác động người dùng, ưu tiên, quy trình thay thế và chấp nhận rủi ro theo thẩm quyền |
| Bảo mật/dữ liệu/chuyên gia liên quan | Đánh giá rủi ro chuyên môn và hướng dẫn xử lý khi dữ liệu hoặc quyền bị ảnh hưởng |

### Một đầu mối điều phối

Với sự cố đang ảnh hưởng production, cần một incident commander hoặc người điều phối được chỉ định. Người này giữ nhịp cập nhật, phân công hành động và bảo đảm quyết định được ghi lại. Người điều phối không nhất thiết là người hiểu sâu nhất về mọi thành phần.

### Phân biệt điều tra kỹ thuật và quyết định nghiệp vụ

Developer có thể kết luận nguyên nhân kỹ thuật; QA có thể kết luận bằng chứng kiểm thử; vận hành có thể kết luận trạng thái dịch vụ. Nhưng quyết định chấp nhận rủi ro đối với người dùng hoặc giao dịch cần người có thẩm quyền nghiệp vụ và các vai trò chuyên môn tương ứng.

## 23. Quản lý lỗi khó tái hiện trong backlog

Một lỗi khó tái hiện không nên bị đóng chỉ vì nhóm không thể làm nó xuất hiện trong môi trường phát triển.

Ticket cần ghi:

- Triệu chứng và tác động.
- Tần suất hoặc số lần quan sát.
- Phiên bản, vùng và điều kiện.
- Request/trace ID đã bảo vệ.
- Log, metric và bằng chứng.
- Các giả thuyết đã thử.
- Kết quả ủng hộ hoặc phản bác.
- Biện pháp giảm thiểu hiện tại.
- Rủi ro còn lại.
- Người sở hữu điều tra.
- Điều kiện để đóng hoặc hạ mức ưu tiên.

### Trạng thái phù hợp

Có thể dùng các trạng thái như:

- Mới ghi nhận.
- Đang xác minh.
- Đang điều tra.
- Đã xác định nguyên nhân.
- Đang khắc phục.
- Chờ xác minh.
- Đã giảm thiểu, còn rủi ro.
- Đã đóng.
- Không tái hiện được, tiếp tục theo dõi.

“Không tái hiện được” là kết quả điều tra tại thời điểm đó, không phải bằng chứng lỗi không tồn tại. Nếu tác động cao, cần tiếp tục quan sát và có điều kiện mở lại rõ.

## 24. Xác minh bản sửa và tránh tái phát

Sau khi có bản sửa, cần kiểm tra cả trường hợp tái hiện ban đầu và các đường đi có thể bị ảnh hưởng.

### Xác minh bản sửa

- Tái hiện lỗi trên phiên bản cũ hoặc bằng điều kiện đã lưu khi phù hợp.
- Chạy test mới chứng minh lỗi đã được ngăn.
- Chạy hồi quy cho luồng liên quan.
- Kiểm tra dữ liệu và trạng thái đã bị ảnh hưởng.
- Kiểm tra hiệu năng và tài nguyên nếu bản sửa thay đổi cơ chế đồng bộ hoặc truy vấn.
- Kiểm tra log, metric và cảnh báo.
- Xác minh rollout và rollback nếu thay đổi có rủi ro.

### Tránh test quá mong manh

Test hồi quy nên tập trung vào bất biến và hành vi quan sát được. Không nên khóa cứng thứ tự log hoặc thời gian xử lý chính xác nếu hợp đồng không yêu cầu. Với test đồng thời, dùng cơ chế đồng bộ rõ ràng thay vì dựa vào sleep.

### Theo dõi sau triển khai

Một test đạt trong môi trường thử nghiệm chưa đủ để kết luận lỗi production đã biến mất. Theo dõi metric và sự kiện thực tế trong khoảng thời gian phù hợp, so sánh tỷ lệ trước và sau, kiểm tra các nhóm người dùng bị ảnh hưởng và xác nhận không có tác động phụ.

## 25. Đánh giá sau sự cố và chia sẻ bài học

Sau khi lỗi được khống chế và khắc phục, nhóm nên tổ chức review tập trung vào hệ thống và quy trình.

Các câu hỏi:

- Điều gì đã xảy ra và ảnh hưởng đến ai?
- Điều kiện kích hoạt chính xác là gì?
- Vì sao lỗi không xuất hiện trong môi trường kiểm thử?
- Bằng chứng nào giúp tìm ra nguyên nhân?
- Bằng chứng nào bị thiếu?
- Biện pháp giảm thiểu có hiệu quả không?
- Có dữ liệu hoặc giao dịch cần đối soát không?
- Test nào cần bổ sung hoặc thay đổi?
- Có cần cải thiện cấu hình, dữ liệu, quan sát hoặc quy trình triển khai?
- Ai sở hữu hành động và thời hạn?

### Không biến postmortem thành tìm người chịu lỗi

Mục tiêu là hiểu các điều kiện và quyết định đã dẫn đến sự cố. Nếu thành viên sợ bị quy trách nhiệm khi báo lỗi hoặc nêu giả thuyết sai, nhóm sẽ mất thông tin quan trọng.

Hành động sau sự cố nên cụ thể, có người sở hữu, thời hạn và bằng chứng hoàn tất. Tránh danh sách chung chung như “cải thiện monitoring” mà không xác định metric, cảnh báo hoặc luồng cần bổ sung.

## 26. Các sai lầm thường gặp

- **Chỉ chạy lại cho đến khi đạt:** che giấu lỗi không ổn định và làm mất lần thất bại ban đầu.
- **Kết luận do môi trường khi chưa có bằng chứng:** có thể bỏ qua lỗi sản phẩm.
- **Thay nhiều cấu hình cùng lúc:** không xác định được yếu tố gây lỗi.
- **Không giữ trace và định danh tương quan:** khó nối các bước trong hệ thống phân tán.
- **Dùng sleep để giải quyết race condition:** làm lỗi ít xuất hiện nhưng không bảo đảm tính đúng.
- **Tăng timeout vô hạn:** che giấu backlog và suy giảm hiệu năng.
- **Chỉ dùng dữ liệu mới trong staging:** bỏ sót lỗi với dữ liệu lịch sử.
- **Sao chép dữ liệu production thiếu kiểm soát:** tạo rủi ro quyền riêng tư và bảo mật.
- **Retry thao tác không idempotent:** có thể tạo giao dịch hoặc tác dụng phụ trùng.
- **Tắt test flaky không thời hạn:** làm giảm độ tin cậy của bộ kiểm thử.
- **Đóng lỗi vì không tái hiện được:** nhầm lẫn giữa thiếu bằng chứng và lỗi không tồn tại.
- **Sửa mã nhưng không đối soát dữ liệu:** hậu quả cũ vẫn còn sau khi lỗi mới được ngăn.
- **Không theo dõi sau phát hành:** chưa xác minh được bản sửa trong điều kiện thật.
- **Không có người điều phối:** điều tra trùng lặp và quyết định bị chậm.

## 27. Checklist điều tra lỗi không ổn định hoặc production-only

### Khi tiếp nhận

- [ ] Mô tả triệu chứng và tác động người dùng.
- [ ] Ghi thời điểm, phiên bản, vùng và định danh tương quan.
- [ ] Lưu log, metric, trace và bằng chứng đã bảo vệ.
- [ ] Xác định phạm vi, tần suất và xu hướng.
- [ ] Kiểm tra có nguy cơ dữ liệu, tài chính, bảo mật hoặc an toàn không.
- [ ] Chỉ định người điều phối và chủ sở hữu điều tra.

### Khi điều tra

- [ ] So sánh môi trường, cấu hình và phiên bản.
- [ ] Kiểm tra dữ liệu, tải, thời gian và quyền.
- [ ] Kiểm tra concurrency, retry và thứ tự sự kiện.
- [ ] Kiểm tra phụ thuộc bên ngoài và tình trạng dịch vụ.
- [ ] Viết giả thuyết và phép kiểm tra có thể bác bỏ.
- [ ] Thử nghiệm trong môi trường an toàn, có kiểm soát.
- [ ] Ghi lại kết quả không ủng hộ giả thuyết.

### Khi khắc phục

- [ ] Có biện pháp giảm thiểu với người sở hữu rõ.
- [ ] Xác định dữ liệu hoặc giao dịch đã bị ảnh hưởng.
- [ ] Có test hồi quy tái hiện điều kiện lỗi.
- [ ] Chạy kiểm thử liên quan và kiểm tra tác động phụ.
- [ ] Có kế hoạch rollout, rollback hoặc roll-forward.
- [ ] Có metric và cảnh báo để xác minh sau phát hành.

### Khi đóng

- [ ] Nguyên nhân hoặc giới hạn điều tra được ghi rõ.
- [ ] Bản sửa đã được xác minh.
- [ ] Dữ liệu và trạng thái bị ảnh hưởng đã được xử lý.
- [ ] Theo dõi sau triển khai đạt tiêu chí.
- [ ] Hành động phòng ngừa có người sở hữu và thời hạn.
- [ ] Bài học được chia sẻ và test/tài liệu được cập nhật.

## 28. Mẫu báo cáo điều tra lỗi khó tái hiện

~~~text
MÃ LỖI / SỰ CỐ:
TIÊU ĐỀ:
MỨC ĐỘ ẢNH HƯỞNG:
TRẠNG THÁI:

TRIỆU CHỨNG:
KẾT QUẢ MONG ĐỢI:
KẾT QUẢ THỰC TẾ:
THỜI ĐIỂM / MÚI GIỜ:
TẦN SUẤT / MẪU SỐ:
PHẠM VI NGƯỜI DÙNG / TENANT / VÙNG:

PHIÊN BẢN ỨNG DỤNG:
SCHEMA / DỮ LIỆU:
CẤU HÌNH LIÊN QUAN:
INSTANCE / WORKER:
PHỤ THUỘC:
TRACE ID / REQUEST ID:

BẰNG CHỨNG:
- Log:
- Metric:
- Trace:
- Dữ liệu đã bảo vệ:
- Thay đổi gần thời điểm xảy ra:

GIẢ THUYẾT:
1. Giả thuyết:
   Bằng chứng ủng hộ:
   Bằng chứng phản bác:
   Phép kiểm tra tiếp theo:

2. Giả thuyết:
   Bằng chứng ủng hộ:
   Bằng chứng phản bác:
   Phép kiểm tra tiếp theo:

BIỆN PHÁP GIẢM THIỂU:
NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:
BẢN SỬA:
KIỂM THỬ HỒI QUY:
KẾT QUẢ SAU TRIỂN KHAI:
DỮ LIỆU CẦN ĐỐI SOÁT:
NGƯỜI SỞ HỮU:
HÀNH ĐỘNG PHÒNG NGỪA:
THỜI HẠN:
~~~

## 29. Mẫu kế hoạch tái hiện và kiểm chứng giả thuyết

~~~text
MỤC TIÊU:
ĐIỀU KIỆN LỖI ĐÃ QUAN SÁT:
PHẠM VI MÔI TRƯỜNG AN TOÀN:

PHIÊN BẢN CẦN DÙNG:
DỮ LIỆU ĐẠI DIỆN:
CẤU HÌNH:
TẢI / MỨC ĐỒNG THỜI:
THỜI GIAN / THỨ TỰ:
PHỤ THUỘC ĐƯỢC MÔ PHỎNG:

GIẢ THUYẾT:
KẾT QUẢ DỰ KIẾN NẾU ĐÚNG:
KẾT QUẢ BÁC BỎ:
BIẾN SỐ SẼ THAY ĐỔI:
BIẾN SỐ GIỮ CỐ ĐỊNH:

CÁCH THỰC HIỆN:
SỐ LẦN / ĐIỀU KIỆN DỪNG:
LOG / METRIC / TRACE:
KẾT QUẢ:
KẾT LUẬN:
GIỚI HẠN:
BƯỚC TIẾP THEO:
~~~

## Kết luận

Lỗi không ổn định và lỗi chỉ xuất hiện trong môi trường thực tế cần được điều tra dựa trên bằng chứng, điều kiện và khác biệt có thể kiểm chứng. Nhóm cần ưu tiên giảm tác động, bảo toàn log và trace, xác định phạm vi, so sánh môi trường, kiểm tra thời gian, đồng thời, dữ liệu, cấu hình và phụ thuộc, rồi xây dựng giả thuyết có kiểm soát.

Sau khi xác định nguyên nhân, cần khắc phục cả hành vi và dữ liệu bị ảnh hưởng, tạo kiểm thử hồi quy ở tầng phù hợp, theo dõi bản sửa trong điều kiện thực tế và ghi nhận hành động phòng ngừa. Khi phát hiện lỗi không đồng nghĩa với tái hiện được lỗi, và không tái hiện được cũng không chứng minh lỗi đã biến mất. Chỉ đóng điều tra khi bằng chứng, giới hạn còn lại, trách nhiệm và kế hoạch theo dõi đều được ghi nhận rõ ràng.
