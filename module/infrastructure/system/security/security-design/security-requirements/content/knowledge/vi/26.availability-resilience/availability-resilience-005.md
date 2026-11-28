# Concurrency limit

## 1. Vì sao giới hạn đồng thời là yêu cầu bảo mật?

**Concurrency limit** là giới hạn số đơn vị công việc được phép đồng thời chiếm dụng một tài nguyên hoặc thực thi trong một phạm vi đã xác định. Mục tiêu là ngăn một nhóm công việc làm cạn tài nguyên dùng chung, gây suy giảm hoặc từ chối dịch vụ cho các nhóm còn lại.

Ví dụ, một dịch vụ có thể chỉ cho phép tối đa 24 truy vấn tìm kiếm nặng đang chạy trên toàn cụm, trong đó mỗi tenant được dùng không quá 6 vị trí. Khi hết vị trí, công việc mới phải được từ chối hoặc đưa vào hàng đợi có giới hạn theo hợp đồng đã định nghĩa.

Trong chương **Availability và resilience** của module yêu cầu bảo mật, concurrency limit cần được xem như một biện pháp bảo vệ tính sẵn sàng. Người đặc tả phải chuyển rủi ro cạn tài nguyên thành yêu cầu cụ thể về phạm vi giới hạn, thời điểm cấp và thu hồi quyền chạy, hành vi khi quá tải, cách ly người dùng và bằng chứng kiểm thử.

Giới hạn đồng thời có thể giảm tác động của hành vi lạm dụng và tải đột biến hợp lệ. Tuy nhiên, nó không tự bảo vệ được mọi tầng. Nếu hệ thống chỉ kiểm tra giới hạn sau khi đã đọc một payload khổng lồ vào bộ nhớ hoặc sau khi đã mở kết nối đến dịch vụ phụ thuộc, tài nguyên có thể đã bị chiếm trước khi biện pháp bảo vệ có hiệu lực.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt giới hạn đồng thời với giới hạn tốc độ, hàng đợi và connection pool.
2. Xác định đúng đơn vị công việc, tài nguyên được bảo vệ và phạm vi áp dụng.
3. Viết yêu cầu cho vòng đời permit, hủy tác vụ và xử lý lỗi.
4. Đặc tả giới hạn nhiều tầng, tính công bằng và hành vi trong hệ thống phân tán.
5. Xây dựng tiêu chí kiểm thử đo được, bao gồm các tình huống race condition và mất kết nối.

## 2. Xuất phát từ tài sản và kịch bản đe dọa

Không nên bắt đầu bằng câu “mỗi người dùng được chạy 10 request”. Trước tiên cần xác định tài nguyên nào có thể cạn, công việc nào chiếm tài nguyên đó và đối tượng nào có khả năng gây tải.

| Tài nguyên cần bảo vệ | Kịch bản rủi ro | Phạm vi giới hạn có thể cần |
|---|---|---|
| CPU và worker xử lý | Nhiều yêu cầu tính toán nặng chạy cùng lúc | Theo loại tác vụ, instance và toàn cụm |
| Bộ nhớ | Nhiều báo cáo lớn cùng dựng dữ liệu trong RAM | Theo tác vụ xuất, tenant và ngân sách bộ nhớ |
| Kết nối cơ sở dữ liệu | Truy vấn chậm chiếm hết pool | Theo workload, dịch vụ và khả năng chịu tải của DB |
| Dịch vụ phụ thuộc | Hệ thống gọi quá nhiều tác vụ đồng thời sang dịch vụ khác | Theo dependency và loại thao tác |
| Dung lượng lưu tạm | Nhiều tác vụ upload hoặc tạo file cùng chạy | Theo người dùng, tenant và dung lượng đang chiếm |
| Luồng xử lý quan trọng | Workload ưu tiên thấp chiếm hết năng lực đăng nhập hoặc phục hồi | Theo lớp công việc, có phần năng lực dành riêng |

Các kịch bản cần xem xét gồm cả người chưa xác thực, tài khoản hợp lệ bị chiếm đoạt, tenant tạo tải lớn, client bị lỗi lặp yêu cầu và các tác vụ nền tự sinh tải. Giới hạn chỉ áp dụng cho người dùng ở giao diện có thể bị vượt qua nếu API nội bộ hoặc luồng chạy lại không sử dụng cùng cơ chế admission.

Yêu cầu tốt phải liên kết được:

```text
Tài nguyên → Kịch bản gây cạn → Chính sách giới hạn
           → Điểm thực thi → Hành vi quá tải → Kiểm thử
```

## 3. Định nghĩa chính xác thứ đang được đếm

### 3.1. Đơn vị công việc

“Request đang hoạt động” có thể mang nhiều nghĩa:

- Request đã vào gateway nhưng đang chờ backend.
- Request đã được nhận vào hàng đợi nhưng chưa bắt đầu chạy.
- Tác vụ đang thực thi và chiếm worker hoặc kết nối.
- Tác vụ đã trả phản hồi chấp nhận nhưng còn chạy nền.
- Phản hồi streaming đang mở và tiếp tục chiếm tài nguyên.

Phải chọn định nghĩa phù hợp với tài nguyên cần bảo vệ. Một tác vụ xuất dữ liệu được API chấp nhận và chạy nền trong 10 phút không được coi là kết thúc chỉ vì phản hồi tạo job đã gửi xong.

Tương tự, giới hạn số phiên đăng nhập đồng thời là một chính sách khác. Một phiên có thể phát sinh nhiều request, trong khi một tác vụ nền có thể tiếp tục chạy sau khi phiên hết hạn. Không dùng số phiên thay cho số công việc đang thực thi nếu mục tiêu là bảo vệ năng lực xử lý.

### 3.2. Permit và bất biến

**Permit** là quyền chiếm một đơn vị năng lực theo chính sách. Với giới hạn cố định và công việc có cùng trọng số, bất biến cơ bản là:

```text
0 ≤ active_work(scope, workload, t) ≤ limit(scope, workload)
```

Trong đó `active_work` phải đếm đúng công việc còn chiếm tài nguyên tại thời điểm `t`, không chỉ đếm các bản ghi chưa hết TTL trong kho điều phối.

Nếu mỗi công việc có trọng số khác nhau, có thể dùng ngân sách:

```text
sum(weight(job) với mọi job đang chiếm tài nguyên) ≤ resource_budget
```

Trọng số phải được tính hoặc xác minh phía máy chủ. Không tin trực tiếp giá trị “chi phí thấp” do client khai báo để cho phép vượt ngân sách.

Hai dạng giới hạn này có thể cùng tồn tại. Chẳng hạn, tối đa 4 tác vụ xuất và tổng phần bộ nhớ được đặt trước không vượt quá ngân sách dành cho workload xuất dữ liệu.

### 3.3. Hợp đồng phạm vi

Một giới hạn cần trả lời đầy đủ:

| Thuộc tính | Ví dụ cần làm rõ |
|---|---|
| Đơn vị | Truy vấn đang chạy, job đang xử lý hay stream còn mở |
| Tài nguyên | Worker tìm kiếm, DB connection hoặc bộ nhớ dựng báo cáo |
| Chủ thể | Tenant, tài khoản, danh tính dịch vụ hoặc lớp chưa xác thực |
| Phạm vi triển khai | Một tiến trình, một instance, một vùng hay toàn cụm |
| Điểm bắt đầu | Khi bắt đầu chiếm tài nguyên được bảo vệ |
| Điểm kết thúc | Khi tài nguyên đã được giải phóng thực sự |
| Đường đi bao phủ | API công khai, API nội bộ, retry và tác vụ nền |
| Ngoại lệ | Công việc đặc biệt, người phê duyệt và thời hạn ngoại lệ |

Một câu như “limit = 24” không đủ để xác minh nếu chưa có những thuộc tính này.

## 4. Phân biệt với các cơ chế liên quan

| Cơ chế | Đại lượng được kiểm soát | Giới hạn của cơ chế |
|---|---|---|
| Rate limit | Số lần bắt đầu hoặc gửi yêu cầu trong một khoảng thời gian | Yêu cầu kéo dài có thể tích lũy thành nhiều công việc đồng thời |
| Concurrency limit | Số công việc đồng thời chiếm năng lực trong phạm vi | Không tự giới hạn tổng số lần gọi trong ngày |
| Hàng đợi có giới hạn | Số hoặc dung lượng công việc được giữ để chờ chạy | Không tự xác định số công việc được thực thi |
| Connection pool | Số kết nối của một loại tài nguyên | Không bao phủ toàn bộ công việc, bộ nhớ và CPU ở tầng khác |
| Timeout hoặc deadline | Thời gian được phép chờ hoặc thực thi | Chỉ có tác dụng giải phóng tài nguyên nếu việc dừng thực sự được thực thi |
| Bulkhead | Phân chia năng lực thành các vùng cách ly | Cần chính sách phân bổ để tránh một vùng bị bỏ đói hoặc một vùng chiếm hết tài nguyên chung |

Giả sử client được khởi tạo 2 tác vụ mỗi giây và mỗi tác vụ chạy khoảng 30 giây. Trong trạng thái ổn định đơn giản, số tác vụ đang chạy có thể xấp xỉ 60. Đây là ước lượng giúp thấy rằng tốc độ đầu vào thấp vẫn có thể tạo mức đồng thời cao; nó không phải bằng chứng về ngưỡng an toàn khi thời gian xử lý hoặc tải biến động.

Giới hạn kết nối TCP cũng không tương đương giới hạn request. Một kết nối có thể mang nhiều request hoặc stream đồng thời tùy giao thức, trong khi một request có thể sinh nhiều lời gọi nội bộ. Phải đặt giới hạn tại nơi hiểu đúng công việc cần kiểm soát.

## 5. Chọn giới hạn từ ngân sách tài nguyên

### 5.1. Xác định giả định và khoảng dự phòng

Ngưỡng phải xuất phát từ phép đo hoặc một mô hình năng lực có giả định rõ ràng. Cần xét thời gian xử lý, bộ nhớ cực đại, kết nối, dung lượng tạm, giới hạn của dependency và năng lực cần giữ cho các chức năng quan trọng.

Ví dụ giả định một cụm dành riêng 1.024 MiB cho phần bộ nhớ của hai workload được kiểm soát:

| Workload | Bộ nhớ đặt trước cho mỗi công việc | Giới hạn toàn cụm |
|---|---|---|
| Tìm kiếm nặng | 16 MiB | 24 |
| Xuất báo cáo | 128 MiB | 4 |

Ngân sách đặt trước ở mức tối đa là:

```text
24 × 16 + 4 × 128 = 896 MiB
Phần còn lại trong ngân sách: 1.024 - 896 = 128 MiB
```

Ví dụ chỉ chứng minh phép phân bổ trong mô hình giả định. Nó chưa chứng minh toàn hệ thống đủ bộ nhớ: runtime, buffer mạng, cache và workload khác cũng cần ngân sách riêng. Nếu 16 MiB hoặc 128 MiB chỉ là giá trị trung bình thay vì giới hạn có thể kiểm soát, phép tính không tạo ra bảo đảm cứng về mức sử dụng cực đại.

Một workload cũng có thể cạn CPU hoặc DB trước khi chạm ngưỡng bộ nhớ. Ngưỡng cuối cùng phải thỏa các ràng buộc tài nguyên có liên quan, thay vì chỉ chọn theo một biểu đồ thuận tiện.

### 5.2. Áp dụng nhiều tầng

Một yêu cầu có thể phải thỏa đồng thời:

```text
Giới hạn toàn cụm
AND giới hạn workload
AND giới hạn tenant
AND giới hạn chủ thể, nếu có
AND ngân sách tài nguyên tại instance được chọn
```

Ví dụ:

- Tìm kiếm nặng: tối đa 24 tác vụ toàn cụm và 6 tác vụ mỗi tenant.
- Xuất báo cáo: tối đa 4 tác vụ toàn cụm và 1 tác vụ mỗi tenant.
- Workload phục hồi quan trọng có phần năng lực riêng; không được mặc nhiên tiêu thụ bằng tác vụ xuất thông thường.

Giới hạn tenant là trần tiêu thụ, không tự tạo quyền được phục vụ ngay. Khi nhiều tenant cùng chờ, cần thêm quy tắc lập lịch và mức bảo đảm phù hợp.

Nếu một công việc cần nhiều permit, việc cấp phải tránh trạng thái giữ permit ở tầng này rồi chờ vô hạn ở tầng khác. Có thể dùng thao tác cấp đồng thời hoặc thứ tự cấp xác định kèm giải phóng khi thất bại. Cách triển khai được lựa chọn phải có bằng chứng không làm rò permit hoặc gây deadlock trong các trường hợp đã nêu.

## 6. Vòng đời permit: nhận việc chưa phải là chạy việc

Một mô hình trạng thái khái quát:

```text
RECEIVED → kiểm tra đầu vào và quyền → WAITING hoặc REJECTED
WAITING  → được cấp đủ năng lực → RUNNING
RUNNING  → hoàn tất hoặc dừng thực sự → FINISHED
```

Với công việc được chạy ngay, có thể không có trạng thái `WAITING`. Hàng đợi, nếu có, cần ngân sách riêng. Không coi toàn bộ công việc chờ là đang thực thi, nhưng cũng không được để hàng đợi chiếm bộ nhớ hoặc dung lượng vô hạn.

### 6.1. Cấp permit nguyên tử

Thao tác “đọc bộ đếm, thấy còn chỗ, rồi tăng bộ đếm” tách rời có thể cho nhiều request cùng vượt trần. Yêu cầu cần bảo đảm việc kiểm tra và cấp năng lực là nguyên tử trong phạm vi mà chính sách cam kết.

Pseudocode dưới đây mô tả trách nhiệm, không phải mã triển khai hoàn chỉnh:

```text
handle(request):
    identity = authenticate_and_authorize(request)
    cost = validate_and_estimate_cost(request)
    ticket = admission.try_acquire(identity, workload, cost)

    if ticket was not granted:
        return overload_response(reason)

    try:
        execute_with_deadline(request)
        wait_until_protected_work_has_stopped()
    finally:
        release_after_confirmed_resource_cleanup(ticket)
```

`finally` chỉ là một công cụ quản lý luồng điều khiển. Nếu `execute_with_deadline` đã khởi tạo tác vụ nền hoặc lời gọi từ xa còn chạy sau khi hàm thoát, giải phóng permit ngay tại đó có thể làm sai bất biến. Triển khai phải gắn quyền sở hữu permit với vòng đời thực của công việc được bảo vệ.

### 6.2. Giải phóng đúng một lần

Mỗi permit cần định danh và chủ sở hữu đủ rõ để không bị một request khác thu hồi nhầm. Thao tác giải phóng lặp lại phải không làm bộ đếm tăng năng lực giả tạo. Việc giải phóng ticket đã kết thúc không được vô tình giải phóng ticket mới dùng lại cùng vị trí.

Các đường kết thúc cần được đặc tả gồm thành công, lỗi nghiệp vụ, exception, lỗi dependency, quá deadline, hủy từ client và worker bị dừng. Với tiến trình chết, cơ chế thu hồi phải phù hợp với khả năng xác nhận công việc cũ đã dừng; không chỉ dựa vào việc mất liên lạc.

### 6.3. Timeout và hủy request

Phải tách ba sự kiện:

1. Client không còn chờ phản hồi.
2. Hệ thống đã gửi tín hiệu hủy công việc.
3. Công việc đã ngừng chiếm tài nguyên được bảo vệ.

Chỉ sự kiện thứ ba mới là cơ sở giải phóng permit nếu mục tiêu là giới hạn công việc đang chiếm tài nguyên đó. Một DB query hoặc job từ xa có thể tiếp tục chạy dù request ở gateway đã timeout.

Nếu hệ thống không thể dừng công việc ngay, cần giữ việc hạch toán năng lực cho đến khi công việc kết thúc hoặc được cô lập theo cơ chế đã xác minh. Đồng thời, phải có thời hạn và cơ chế xử lý công việc không thể kết thúc bình thường để tránh giữ năng lực vĩnh viễn.

### 6.4. Retry và idempotency

Mỗi lần thử lại tạo ra công việc thực sự đều phải đi qua admission. Tránh đặt concurrency limit bên ngoài một khối tự tạo nhiều retry song song mà không tính chúng.

Với API tạo job, khóa idempotency có thể giúp yêu cầu gửi lại tham chiếu cùng một công việc. Tuy nhiên, cơ chế này phải được đặc tả về phạm vi tenant, thời hạn, xung đột payload và tính nguyên tử khi tạo job. Chỉ thêm một header không bảo đảm rằng backend không chạy hai công việc.

## 7. Hàng đợi, backpressure và phản hồi quá tải

### 7.1. Quyết định chờ hay từ chối

Khi hết permit, có hai lựa chọn thường gặp:

- **Từ chối ngay:** phù hợp với công việc không cần giữ lại hoặc có deadline ngắn. Client nhận kết quả quá tải theo hợp đồng.
- **Chờ có giới hạn:** phù hợp với công việc có thể trì hoãn và có ngân sách lưu chờ. Cần giới hạn độ dài, dung lượng và thời gian chờ.

Không nên biến concurrency limit thành hàng đợi vô hạn. Khi tốc độ đến lớn hơn năng lực hoàn tất trong thời gian dài, hàng đợi sẽ tiếp tục tăng và có thể trở thành điểm cạn tài nguyên mới.

Một hợp đồng minh họa cho tác vụ xuất báo cáo có thể quy định:

```text
Toàn cụm: tối đa 4 tác vụ đang thực thi.
Mỗi tenant: tối đa 1 tác vụ đang thực thi, tối đa 2 tác vụ đang chờ.
Toàn cụm: tối đa 40 tác vụ đang chờ.
Thời gian chờ tối đa: 60 giây tính từ lúc được nhận vào hàng đợi.
Tác vụ hết hạn chờ: không được bắt đầu thực thi.
```

Các số trên là ví dụ của dự án giả định. Ngoài số lượng, cần giới hạn dung lượng metadata hoặc payload được giữ. Bốn mươi mục chờ vẫn có thể quá lớn nếu mỗi mục chứa toàn bộ file tải lên.

Khi một công việc hết hạn hoặc bị hủy trong hàng đợi, cần loại nó khỏi ngân sách chờ. Trường hợp hủy xảy ra đồng thời với việc được cấp permit phải có một kết quả nhất quán: công việc không chạy thì hoàn trả permit; công việc đã chạy thì chuyển sang quy trình hủy công việc đang chạy và chỉ hoàn trả sau khi giải phóng tài nguyên.

### 7.2. Phản hồi cho client

Đặc tả cần phân biệt lý do bị từ chối: vượt giới hạn tenant, hết năng lực toàn hệ thống, hết thời gian chờ hoặc bộ điều phối không khả dụng. Phản hồi nên có mã lỗi ổn định để client biết có thể thử lại hay cần giảm tải.

Với API HTTP, một hợp đồng có thể dùng `429` cho việc chủ thể vượt chính sách tiêu thụ, và `503` cho tình trạng dịch vụ thiếu năng lực tạm thời hoặc không thể cấp phép an toàn. Việc ánh xạ cần thống nhất với hợp đồng API của dự án; mã trạng thái đơn lẻ không diễn đạt đầy đủ chính sách retry.

Nếu trả hướng dẫn chờ, thời gian đó phải có ý nghĩa theo chính sách và không được hiểu là cam kết chắc chắn sẽ có permit khi hết thời gian. Client cần tránh thử lại dồn dập hoặc đồng bộ thành từng đợt; chính sách retry phải có ngân sách số lần thử và khoảng lùi phù hợp.

Thông báo không nên tiết lộ danh tính tenant khác, hoạt động nội bộ nhạy cảm hoặc toàn bộ cấu hình năng lực. Người dùng cần biết yêu cầu của mình bị hạn chế và nên xử lý thế nào; đội vận hành có thể xem thông tin chi tiết bằng quyền riêng.

### 7.3. Backpressure phải đến đúng tầng

Khi dịch vụ phụ thuộc đã bão hòa, việc thêm nhiều tác vụ chờ ở tầng trên có thể chỉ kéo dài thời gian phản hồi. Cần đặc tả giới hạn riêng cho lời gọi tới dependency và cách truyền trạng thái thiếu năng lực trở lại tầng tiếp nhận.

Đường xử lý từ chối cũng phải nhẹ và có giới hạn. Nếu từ chối một request lại thực hiện nhiều truy vấn hoặc ghi log không giới hạn, đối tượng gây tải có thể làm cạn tài nguyên ngay trên đường từ chối.

## 8. Cách ly tenant và tính công bằng

### 8.1. Chọn danh tính đáng tin cậy

Giới hạn theo tenant hoặc tài khoản phải dựa trên danh tính đã xác minh. Không dùng một header tùy ý do client cung cấp làm khóa quota. Với API nội bộ, danh tính dịch vụ và quyền đại diện tenant cũng phải được kiểm tra.

Địa chỉ IP có thể hữu ích cho một số giới hạn trước xác thực, nhưng không phải khóa duy nhất phù hợp cho mọi trường hợp: nhiều người có thể dùng chung một địa chỉ, còn một đối tượng có thể gửi yêu cầu từ nhiều địa chỉ. Cần phối hợp giới hạn ở tầng biên, lớp chưa xác thực và tầng chủ thể sau xác thực theo mô hình đe dọa.

Chi phí xác thực cũng có thể bị lạm dụng. Nếu kiểm tra mật khẩu hoặc token đã đủ nặng để gây cạn worker, cần có giới hạn bảo vệ trước hoặc ngay tại bước đó; không chờ đến khi xác thực xong mới bảo vệ toàn bộ tài nguyên.

### 8.2. Trần tiêu thụ chưa bảo đảm công bằng

Giả sử mỗi tenant được dùng tối đa 6 vị trí trên tổng 24 vị trí. Bốn tenant có thể chiếm hết năng lực, khiến tenant thứ năm phải chờ. Chính sách này thỏa trần tenant nhưng chưa cam kết độ trễ phục vụ cho mọi tenant.

Nếu cần chống bỏ đói, yêu cầu phải xác định cách lập lịch, ví dụ luân phiên giữa các hàng đợi tenant hoặc dành trước năng lực cho lớp công việc quan trọng. Cần ghi rõ điều kiện đo: số tenant cùng hoạt động, mức tải, deadline và giả định công việc cuối cùng sẽ kết thúc.

Hàng đợi FIFO chung có thể gây chặn đầu hàng nếu công việc đầu tiên cần nhiều tài nguyên mà hiện chưa đủ. Cho phép vượt qua công việc đó có thể tăng hiệu suất nhưng cũng tạo nguy cơ công việc lớn chờ mãi. Đây là đánh đổi cần được quyết định trong yêu cầu lập lịch, không để thành hành vi ngẫu nhiên của thư viện.

### 8.3. Đường ưu tiên không được trở thành đường vượt giới hạn

Workload phục hồi hoặc vận hành khẩn cấp có thể có năng lực riêng. Cần xác định ai được sử dụng, thao tác nào được phép, trần tài nguyên và dấu vết audit. Gắn cờ `priority=high` từ client không được tự động cấp quyền vào vùng ưu tiên.

Ngoại lệ tenant cũng phải có người phê duyệt, phạm vi, thời hạn và cách thu hồi. Tăng trần cho một tenant không được làm tổng ngân sách vượt năng lực đã phân bổ.

## 9. Hệ thống phân tán: giới hạn ở đâu thì bảo đảm ở đó

### 9.1. Giới hạn local và global

Một semaphore trong một tiến trình chỉ kiểm soát các công việc đi qua tiến trình đó. Nếu mỗi instance cho chạy 8 công việc và có 3 instance, tổng có thể đạt 24. Khi tăng lên 5 instance, tổng có thể đạt 40 nếu không có chính sách điều chỉnh.

Các phương án phổ biến có đánh đổi khác nhau:

| Phương án | Phạm vi bảo đảm | Điều phải đặc tả |
|---|---|---|
| Giới hạn cục bộ | Một tiến trình hoặc instance | Số instance tối đa, đường gọi được bao phủ và tổng năng lực có thể phát sinh |
| Phân bổ ngân sách thành các phần | Tổng các phần được cấp không vượt ngân sách chung | Cấp phát, thu hồi và chuyển phần ngân sách an toàn |
| Điều phối permit dùng chung | Phạm vi do bộ điều phối quản lý | Tính nguyên tử, quyền sở hữu, khả dụng và xử lý phân vùng mạng |
| Kiểm soát tại tài nguyên đích | Công việc thật sự được tài nguyên nhận thực thi | Tài nguyên có thực thi được giới hạn và loại bỏ công việc cũ hay không |

Nếu dùng các phần ngân sách cố định, phải tính cả instance cũ và mới cùng tồn tại trong rolling deployment, kể cả phần đã cấp nhưng chưa được thu hồi an toàn. Không chỉ dựa vào số replica mục tiêu trong cấu hình.

### 9.2. Mất bộ điều phối

Khi không xác minh được quyền cấp mới, cần một chính sách rõ ràng. Ví dụ, workload xuất dữ liệu ngừng nhận việc chạy mới, giữ công việc đã được cấp hợp lệ và trả lỗi tạm thời cho yêu cầu mới. Ngừng cấp mới không đồng nghĩa tự động hủy mọi công việc đang chạy.

Nếu cho phép chế độ dự phòng cục bộ, phải chứng minh tổng phần ngân sách cũ và phần dự phòng không vượt ngân sách an toàn. Việc mỗi instance tự đặt lại một bộ đếm đầy đủ khi kho dùng chung mất kết nối có thể nhân số công việc đang chạy.

Một giới hạn được chấp nhận có sai số trong thời gian sự cố phải công bố phạm vi và điều kiện sai số. Không mô tả cơ chế đó như một giới hạn toàn cụm tuyệt đối nếu chưa bảo đảm được trong những tình huống lỗi đã cam kết.

### 9.3. Lease hết hạn không chứng minh công việc đã dừng

Trong cơ chế lease, worker có thể phải gia hạn quyền định kỳ. Nếu lease hết hạn do mất mạng nhưng worker cũ vẫn chạy, cấp lại permit cho worker mới có thể làm cả hai cùng chiếm tài nguyên.

Để cam kết trần cứng, cần cơ chế bảo đảm công việc cũ không còn tiêu thụ tài nguyên trước khi tái sử dụng năng lực, hoặc tài nguyên đích có thể thực thi việc thu hồi quyền một cách đáng tin cậy. Một số hệ thống dùng fencing token để tài nguyên đích từ chối chủ sở hữu cũ. Cơ chế này chỉ hữu ích với các thao tác mà tài nguyên đích thực sự kiểm tra và cưỡng chế được; một token mới không tự dừng CPU, truy vấn hay job cũ đang chạy.

Nếu chưa thể xác nhận công việc cũ đã dừng, hệ thống có thể phải giữ phần ngân sách đó ở trạng thái chưa thu hồi và giảm khả năng nhận việc mới. Đặc tả cần nêu cách đối soát, cảnh báo và xử lý thủ công hoặc tự động. Đây là đánh đổi trực tiếp giữa tiếp tục phục vụ và giữ đúng bảo đảm tài nguyên khi có lỗi.

### 9.4. Đối soát trạng thái

Nên phân biệt số permit đã cấp, số công việc worker báo đang chạy và số công việc tài nguyên đích xác nhận. Ba nguồn có thể lệch nhau sau lỗi. Cơ chế đối soát phải có quy tắc xử lý ticket mồ côi, worker quay lại sau mất kết nối và phản hồi giải phóng đến muộn.

Không “sửa bộ đếm về 0” chỉ vì không nhận heartbeat, nếu vẫn có khả năng công việc cũ đang chạy. Hành vi này có thể làm dashboard trông bình thường nhưng phá vỡ giới hạn thực tế.

## 10. Cấu hình, quan sát và kiểm toán

### 10.1. Quản trị cấu hình

Mỗi chính sách nên có mã định danh, phiên bản, chủ sở hữu, phạm vi, ngưỡng, thời điểm hiệu lực và lý do thay đổi. Việc sửa chính sách cần được phân quyền và ghi audit.

Thay đổi giảm trần cần có ngữ nghĩa riêng. Ví dụ, khi đang có 20 công việc và trần giảm từ 24 xuống 12, hệ thống có thể chọn giữ công việc đang chạy và ngừng cấp mới cho đến khi số hoạt động xuống dưới 12. Trong khoảng chuyển tiếp, tổng hoạt động có thể vẫn lớn hơn trần mới; yêu cầu phải công bố trạng thái đang giảm tải và thời hạn hội tụ, thay vì tuyên bố bất biến trần mới có hiệu lực tức thì.

Nếu yêu cầu phải dừng bớt công việc ngay, cần quy định việc chọn công việc, bảo toàn dữ liệu và hoàn tác nghiệp vụ. Không mặc nhiên hủy tác vụ đang ghi dữ liệu chỉ để làm đẹp bộ đếm.

### 10.2. Chỉ số vận hành

Các chỉ số hữu ích gồm:

- Số công việc đang chiếm tài nguyên so với trần, theo workload và phạm vi.
- Số và dung lượng công việc chờ; thời gian chờ và số hết hạn.
- Số yêu cầu bị từ chối theo lý do, gồm vượt quota, quá tải chung và lỗi điều phối.
- Thời gian giữ permit; số công việc quá deadline nhưng chưa dừng.
- Chênh lệch giữa permit và công việc thực; số ticket chưa thu hồi được.
- Độ trễ cấp permit, lỗi gia hạn và phiên bản chính sách đang áp dụng.

Định nghĩa phải làm rõ số lượng tích lũy, giá trị tại một thời điểm và cửa sổ thời gian. Không dùng tổng số request bị từ chối để kết luận tất cả đều là tấn công; cần đối chiếu danh tính, workload và trạng thái năng lực.

Nhãn metric phải được kiểm soát để không tạo số chuỗi đo vô hạn. Không đưa token, payload hoặc định danh tùy ý từ request vào nhãn. Khi cần điều tra chi tiết theo tenant, sử dụng kênh được phân quyền và chính sách lưu giữ phù hợp.

### 10.3. Audit và cảnh báo

Audit nên bao phủ thay đổi ngưỡng, cấp ngoại lệ, thu hồi ngoại lệ và thao tác can thiệp thu hồi permit. Bản ghi cần có người thực hiện, phạm vi, giá trị trước và sau, lý do, phiên bản và kết quả.

Cảnh báo không chỉ dựa trên việc chạm trần. Một hệ thống có thể thường xuyên chạy ở gần trần theo thiết kế. Cần liên kết tín hiệu với tác động: thời gian chờ vượt mục tiêu, lớp công việc quan trọng không được phục vụ, rò permit hoặc lỗi điều phối kéo dài.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây dùng workload xuất báo cáo giả định. Chúng là ví dụ về mức cụ thể cần đạt, không phải ngưỡng mặc định cho mọi dịch vụ.

| Mã | Yêu cầu | Liên kết rủi ro và điểm thực thi |
|---|---|---|
| CL-01 | Trong chế độ chính sách ổn định, tối đa 4 job xuất đang chiếm tài nguyên thực thi trên toàn cụm và tối đa 1 job mỗi tenant | Cạn tài nguyên; admission của mọi đường chạy job |
| CL-02 | Tenant phải lấy từ danh tính được xác minh; không cho phép tham số client thay đổi phạm vi quota trái quyền | Vượt quota bằng giả mạo tenant; lớp danh tính và admission |
| CL-03 | Cấp đủ các permit cần thiết phải tránh race vượt trần; thất bại cấp một phần không được làm rò năng lực hoặc chờ vô hạn | Vượt trần và deadlock; cơ chế cấp permit |
| CL-04 | Hàng đợi tối đa 40 job toàn cụm, 2 job mỗi tenant; job chờ quá 60 giây không được bắt đầu chạy | Cạn tài nguyên chờ; queue và scheduler |
| CL-05 | Permit chỉ được trả khi công việc đã ngừng chiếm tài nguyên được bảo vệ; giải phóng lặp lại hoặc đến muộn không làm tăng năng lực sai | Tác vụ mồ côi và đếm sai; worker, ticket và cleanup |
| CL-06 | Retry, gọi nội bộ và job nền phải chịu chính sách tương ứng; một lần thử tạo công việc mới phải được hạch toán | Lách giới hạn qua đường phụ; các điểm gọi và worker |
| CL-07 | Khi không thể cấp permit an toàn, hệ thống không khởi chạy job mới ngoài phần ngân sách còn được bảo đảm | Quá tải do lỗi điều phối; admission và chế độ dự phòng |
| CL-08 | Không tái sử dụng năng lực chỉ dựa vào lease hết hạn nếu công việc cũ có thể vẫn chạy; phải có bằng chứng dừng hoặc cơ chế cưỡng chế tại tài nguyên | Vượt trần khi phân vùng mạng; điều phối và tài nguyên đích |
| CL-09 | Thay đổi trần và ngoại lệ phải có quyền, phiên bản, audit và chính sách chuyển tiếp khi giảm trần | Bỏ kiểm soát qua cấu hình; quản trị chính sách |
| CL-10 | Phản hồi quá tải phải có mã lỗi ổn định, hành vi retry được công bố và không tiết lộ dữ liệu tenant khác | Retry dồn dập và lộ thông tin; API và client |
| CL-11 | Hệ thống phải cung cấp chỉ số active, waiting, rejected, thời gian giữ permit và ticket chưa đối soát; dữ liệu chi tiết phải được phân quyền | Không phát hiện cạn năng lực hoặc rò permit; telemetry và dashboard |

Với yêu cầu công bằng, cần bổ sung một mục tiêu riêng gắn với scheduler. Ví dụ, trong một bài thử có số tenant và thời gian xử lý được chặn trên rõ ràng, tenant liên tục có công việc hợp lệ không bị bỏ qua vô hạn. Nếu cần một giới hạn thời gian cụ thể, phải chọn nó từ năng lực và tải giả định, sau đó đo trong điều kiện tương ứng.

## 12. Tiêu chí nghiệm thu và kiểm thử lỗi

### 12.1. Kiểm tra ngưỡng với công việc được giữ chủ động

Để đo concurrency, dùng các công việc thử nghiệm có điểm đồng bộ giữ chúng ở trạng thái đang chiếm tài nguyên. Không chỉ gửi nhiều request rồi kiểm tra số phản hồi thành công, vì các công việc ngắn có thể chạy nối tiếp mà không vi phạm trần.

```gherkin
Given chính sách ổn định cho phép 4 job toàn cụm và 1 job mỗi tenant
And 4 tenant khác nhau đang có mỗi tenant 1 job chiếm tài nguyên
And các job thử nghiệm được giữ tại điểm đồng bộ trước cleanup
When tenant thứ năm gửi một job hợp lệ
Then job mới không bắt đầu thực thi
And kết quả chờ hoặc từ chối tuân theo chính sách hàng đợi
And số job thực sự chiếm tài nguyên không vượt quá 4

When một job kết thúc và hoàn tất cleanup
Then scheduler có thể cấp năng lực vừa được giải phóng
And mọi giới hạn tenant và toàn cụm vẫn được thỏa mãn
```

Cần quan sát trạng thái công việc tại worker hoặc tài nguyên được bảo vệ, không chỉ tin vào chính bộ đếm của bộ giới hạn. Với các cam kết cứng, dữ liệu lấy mẫu thưa có thể bỏ sót vượt trần ngắn; nên dùng dấu vết bắt đầu và kết thúc hoặc cơ chế quan sát phù hợp để dựng lại mức đồng thời.

### 12.2. Kiểm tra cấp permit đồng thời

Tại trạng thái chỉ còn một vị trí, cho nhiều luồng cùng thử cấp permit qua một điểm đồng bộ. Chỉ một công việc được phép nhận vị trí đó. Thực hiện trên nhiều instance nếu yêu cầu là toàn cụm.

Lặp kịch bản với cấp nhiều tầng, lỗi sau khi cấp một phần và giải phóng cùng lúc. Bằng chứng cần cho thấy không vượt trần, không rò permit và không giải phóng nhầm ticket.

### 12.3. Client timeout nhưng công việc chưa dừng

```gherkin
Given một job đang giữ permit và thực hiện lời gọi phụ thuộc chậm
When client ngắt kết nối hoặc hết thời gian chờ
And lời gọi phụ thuộc chưa dừng
Then permit vẫn được hạch toán cho phần công việc đang chạy
And yêu cầu mới không sử dụng được năng lực đó trái chính sách

When công việc được xác nhận đã dừng và cleanup hoàn tất
Then permit được giải phóng đúng một lần
```

Thêm biến thể tín hiệu hủy đến cùng lúc với hoàn tất bình thường và biến thể phản hồi giải phóng bị gửi lại. Kiểm tra cả tính đúng của bộ đếm lẫn tài nguyên thật.

### 12.4. Hàng đợi và cách ly tenant

Kiểm tra tenant đã có 1 job chạy và 2 job chờ. Job tiếp theo không được làm tenant vượt ngân sách chờ. Đồng thời, tenant khác còn quota vẫn có thể được tiếp nhận nếu ngân sách chung cho phép.

Tạo một job chờ quá 60 giây rồi giải phóng vị trí chạy. Job hết hạn không được khởi chạy sau đó. Kiểm tra race giữa hết hạn, hủy và cấp permit để bảo đảm chỉ một trạng thái cuối có hiệu lực.

Kiểm thử giả mạo header tenant, tạo nhiều khóa idempotency và gọi trực tiếp worker API trong phạm vi thử nghiệm được cấp quyền. Kết quả phải phản ánh đúng ranh giới danh tính và các đường admission đã đặc tả.

### 12.5. Mất điều phối, phân vùng và worker quay lại

Các bài thử lỗi nên gồm:

1. Worker đang chạy mất kết nối tới bộ điều phối nhưng vẫn tiếp cận được tài nguyên đích.
2. Lease hết hạn trong khi công việc cũ chưa dừng.
3. Instance mới được thêm vào khi ngân sách cũ chưa được thu hồi.
4. Bộ điều phối phục hồi và nhận phản hồi giải phóng đến muộn.
5. Worker khởi động lại nhưng còn job từ xa do nó đã tạo trước đó.

Kết quả mong đợi phải phù hợp với bảo đảm đã chọn: giữ trần cứng và hạn chế cấp mới, hoặc báo rõ trạng thái suy giảm trong phạm vi sai số được phê duyệt. Không dùng việc bộ điều phối hoạt động trở lại làm bằng chứng rằng mọi job cũ đã biến mất.

### 12.6. Thay đổi cấu hình và kiểm thử tải

Giảm trần khi còn nhiều job đang chạy và xác minh chính sách chuyển tiếp. Kiểm tra người không có quyền sửa ngưỡng, ngoại lệ hết hạn và cấu hình không hợp lệ.

Kiểm thử tải cần kết hợp nhiều loại công việc, thời gian chạy, tenant và tốc độ đến. Đo mức dùng tài nguyên, độ trễ chờ, tỷ lệ từ chối và mức phục vụ workload quan trọng. Tiêu chí “không vượt trần” là cần thiết nhưng chưa đủ nếu các công việc hợp lệ vẫn bị bỏ đói hoặc hệ thống cạn tài nguyên ở tầng trước admission.

## 13. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Hậu quả | Cách làm rõ |
|---|---|---|
| “Tối đa 10 request” | Không rõ đang chờ, đang chạy hay mỗi giây | Ghi đơn vị, vòng đời, tài nguyên và phạm vi |
| Chỉ có giới hạn mỗi instance nhưng gọi là toàn cụm | Autoscaling hoặc rolling deployment làm tăng tổng | Kiểm soát ngân sách chung hoặc công bố đúng giới hạn cục bộ |
| Trả permit khi gửi phản hồi xong | Job nền hoặc lời gọi từ xa vẫn chạy | Gắn permit với thời gian chiếm tài nguyên thật |
| Lease hết hạn thì xem công việc đã chết | Công việc cũ và mới cùng chạy | Xác minh dừng hoặc dùng cơ chế cưỡng chế phù hợp tại tài nguyên |
| Thêm hàng đợi không giới hạn | Chuyển sự cố sang bộ nhớ, dung lượng và độ trễ | Giới hạn số lượng, dung lượng và tuổi công việc chờ |
| Dùng tenant do client tự khai | Dễ đổi khóa để vượt quota | Lấy phạm vi từ danh tính và quyền được xác minh |
| Admin được bỏ mọi giới hạn | Một thao tác có đặc quyền vẫn làm cạn tài nguyên chung | Tách quyền nghiệp vụ khỏi ngân sách tài nguyên và ngoại lệ có kiểm soát |
| Timeout được coi là đã hủy | Bộ đếm thấp hơn công việc thực tế | Đặc tả tín hiệu hủy, xác nhận dừng và cleanup |
| Chỉ kiểm tra bộ đếm của limiter | Có thể bỏ sót đường gọi không được hạch toán | Đối chiếu với công việc và tài nguyên thực |
| Giảm trần rồi yêu cầu ngay lập tức thỏa trần mới | Mâu thuẫn với việc giữ job cũ chạy | Định nghĩa giai đoạn hội tụ hoặc quy tắc dừng an toàn |

## 14. Đưa yêu cầu vào vòng đời phát triển

Ở bước phân tích, liên kết rủi ro từ chối dịch vụ với tài nguyên và workload cụ thể. Ghi rõ mục tiêu sẵn sàng, lớp công việc cần bảo vệ và hệ quả chấp nhận được khi từ chối yêu cầu mới.

Ở bước thiết kế, xác định admission nằm ở đâu, danh tính nào được dùng, ngân sách được phân bổ ra sao và các đường thực thi nào phải đi qua kiểm soát. Hoàn thiện vòng đời permit cùng mô hình lỗi, đặc biệt với job nền và dependency.

Ở bước triển khai và nghiệm thu, gắn mã yêu cầu với các điểm thực thi, cấu hình và bài kiểm thử. Dùng dữ liệu quan sát độc lập để chứng minh công việc thực tế không vượt các giới hạn đã cam kết trong điều kiện bình thường và các tình huống lỗi thuộc phạm vi.

Ở bước vận hành, theo dõi rò permit, tuổi job, hàng đợi và tác động đến người dùng. Khi đổi số replica, loại workload, timeout, chiến lược retry hoặc giới hạn dependency, đánh giá lại ngân sách và tiêu chí nghiệm thu. Những thay đổi này có thể làm cam kết cũ không còn đúng dù giá trị cấu hình concurrency chưa đổi.

## 15. Bài tập tự kiểm tra

Một dịch vụ xuất dữ liệu có 3 instance. Mỗi instance giới hạn 4 job. Tài liệu sản phẩm ghi “toàn hệ thống tối đa 4 job đồng thời”. Mỗi request tạo job trả phản hồi ngay; permit được trả khi phản hồi được gửi. Job thật tiếp tục chạy ở worker và có thể kéo dài 5 phút. Khi bộ điều phối mất kết nối, mỗi instance chuyển sang semaphore local mới với đủ 4 permit.

Hãy thực hiện các việc sau:

1. Chỉ ra những điểm mà yêu cầu và triển khai đang mâu thuẫn.
2. Định nghĩa lại đơn vị công việc, điểm bắt đầu và điểm kết thúc giữ permit.
3. Viết yêu cầu cho giới hạn toàn cụm, tenant, hàng đợi và retry.
4. Chọn hành vi khi mất bộ điều phối và giải thích phần ngân sách nào vẫn an toàn để sử dụng.
5. Viết bài kiểm thử cho request đã trả phản hồi nhưng job còn chạy, lease hết hạn và worker quay lại.
6. Xác định bằng chứng cần có trước khi kết luận đã thu hồi an toàn một permit.

Một lời giải đầy đủ cần chỉ ra rằng semaphore theo instance, thời điểm trả phản hồi và lease đều không tự chứng minh số job thực sự đang chiếm tài nguyên trên toàn hệ thống. Yêu cầu bảo mật phải xác định đúng bất biến cần giữ, điều kiện bảo đảm bất biến đó và cách kiểm chứng bằng trạng thái công việc thực tế.
