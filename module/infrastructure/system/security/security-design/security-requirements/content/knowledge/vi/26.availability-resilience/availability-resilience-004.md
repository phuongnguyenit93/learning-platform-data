# Rate limiting

## 1. Từ rủi ro quá tải đến yêu cầu bảo mật

Trong chương **Availability và resilience**, rate limiting là cơ chế giới hạn lượng công việc mà một chủ thể hoặc một nhóm chủ thể được phép đưa vào hệ thống trong một khoảng thời gian. Chủ thể có thể là tài khoản, tenant, ứng dụng tích hợp, địa chỉ mạng hoặc toàn bộ lưu lượng tới một chức năng.

Một API có thể xác thực và phân quyền chính xác nhưng vẫn mất khả năng phục vụ nếu một client tạo quá nhiều yêu cầu hợp lệ. Rate limiting giúp bảo vệ năng lực xử lý, giữ tài nguyên cho người dùng khác, hạn chế tự động hóa gây hại và kiểm soát chi phí. Khi đặc tả yêu cầu bảo mật, điều quan trọng là chuyển câu “cần chống spam” thành một chính sách có phạm vi, ngưỡng, cách xử lý và bằng chứng kiểm thử rõ ràng.

Sau bài học, người học cần có khả năng:

- Liên kết rủi ro lạm dụng tài nguyên với yêu cầu rate limiting cụ thể.
- Chọn đơn vị giới hạn, khóa định danh và thuật toán phù hợp với luồng nghiệp vụ.
- Đặc tả hành vi khi vượt ngưỡng, khi thành phần giới hạn gặp lỗi và khi triển khai nhiều replica.
- Xây dựng tiêu chí kiểm thử, log và chỉ số để chứng minh chính sách hoạt động đúng.

Các con số trong bài là **ví dụ thiết kế cho một hệ thống giả định**, cần hiệu chỉnh bằng mô hình đe dọa, đo tải và mục tiêu chất lượng dịch vụ của hệ thống thực tế.

## 2. Rate limiting bảo vệ điều gì?

Xét một dịch vụ xuất báo cáo có 10 worker. Nếu mỗi job chiếm một worker trong 20 giây thì năng lực xử lý lý tưởng chỉ khoảng 0,5 job/giây, trước khi tính thêm chi phí phối hợp và lỗi. Một client gửi 100 yêu cầu/giây có thể làm hàng đợi tăng rất nhanh dù client đó có quyền xuất báo cáo.

Rủi ro không chỉ nằm ở số lượng request:

| Luồng nghiệp vụ | Hành vi gây hại hoặc sự cố | Tài nguyên bị ảnh hưởng | Hướng đặc tả yêu cầu |
|---|---|---|---|
| Đăng nhập | Đoán mật khẩu tự động hoặc gửi dồn yêu cầu | CPU xác minh mật khẩu, dịch vụ danh tính | Hạn chế nhịp thử theo nhiều tín hiệu; có cơ chế phục hồi phù hợp |
| Gửi OTP | Gửi lặp lại để quấy rối hoặc làm tăng hóa đơn | Ngân sách SMS/email, trải nghiệm người nhận | Giới hạn theo nơi nhận, chủ thể gọi và ngân sách chung |
| Tìm kiếm | Truy vấn nặng liên tục | CPU, bộ nhớ, cơ sở dữ liệu | Giới hạn theo người gọi và chi phí truy vấn |
| Xuất báo cáo | Tạo nhiều job hơn tốc độ xử lý | Worker, hàng đợi, dung lượng lưu trữ | Kết hợp tốc độ nhận job, số job đang chạy và độ dài hàng đợi |
| Tích hợp đối tác | Client retry đồng loạt khi có lỗi | Connection pool, dịch vụ phụ thuộc | Kiểm soát burst, hướng dẫn retry và áp dụng backpressure |

Một yêu cầu hữu ích phải chỉ ra mối quan hệ giữa **hành vi đe dọa → tài nguyên cần bảo vệ → chính sách kiểm soát → tiêu chí kiểm chứng**. Chỉ ghi “API phải có rate limit” chưa cho biết cần bảo vệ tài nguyên nào hoặc thế nào được xem là đạt.

### 2.1. Phân biệt các cơ chế liên quan

| Cơ chế | Đại lượng kiểm soát | Ví dụ |
|---|---|---|
| Rate limit | Số lần hoặc số đơn vị công việc theo thời gian | Tối đa 5 job/phút/tenant theo sliding window |
| Concurrency limit | Số công việc đang thực hiện cùng lúc | Tối đa 2 job báo cáo đang chạy/tenant |
| Quota | Tổng mức sử dụng trong một kỳ | Tối đa 10.000 báo cáo/tháng/tenant |
| Timeout | Thời gian tối đa một thao tác được chiếm tài nguyên | Dừng job sau 60 giây theo chính sách hủy tác vụ |
| Queue bound | Số lượng hoặc tổng chi phí công việc chờ | Hàng đợi tối đa 100 job |
| Load shedding | Lượng công việc bị từ chối khi hệ thống chịu áp lực | Từ chối thêm job khi hàng đợi đã đầy |

Rate limit không tự giới hạn số request đang xử lý. Nếu cho nhận 10 request/giây và mỗi request kéo dài 30 giây, số request đồng thời có thể xấp xỉ 300 ở trạng thái ổn định. Đây là ước lượng khi tốc độ và thời gian xử lý tương đối ổn định, không phải một cận an toàn trong mọi tình huống.

Tương tự, một request tải lên tệp rất lớn hoặc chạy truy vấn cực nặng vẫn có thể gây quá tải dù số request nhỏ. Yêu cầu cần kết hợp giới hạn kích thước, độ phức tạp, thời gian, đồng thời và dung lượng hàng đợi theo đúng loại tài nguyên.

Rate limiting cũng không thay thế xác thực, phân quyền hay phòng thủ tấn công làm nghẽn đường truyền. Nếu lưu lượng đã bão hòa kết nối mạng trước khi tới ứng dụng, bộ giới hạn trong ứng dụng không bảo vệ được đoạn đường đó.

## 3. Bắt đầu từ luồng nghiệp vụ và mô hình đe dọa

Trước khi chọn thuật toán, hãy mô tả các trường hợp sử dụng và lạm dụng:

1. **Tác nhân:** người dùng hợp lệ nhưng có lỗi ở client, bot chưa đăng nhập, tài khoản bị chiếm quyền hoặc đối tác tích hợp.
2. **Năng lực:** một IP hay nhiều IP, một tài khoản hay nhiều tài khoản, có thể thay API key hoặc chạy song song bao nhiêu kết nối.
3. **Tài nguyên:** CPU, cơ sở dữ liệu, dịch vụ OTP, connection pool, worker hoặc ngân sách bên thứ ba.
4. **Tác động:** giảm chất lượng phục vụ, tăng chi phí, làm cạn hàng đợi hoặc ngăn người dùng khác truy cập.
5. **Yêu cầu phục vụ hợp lệ:** burst bình thường, nhóm người dùng chung NAT, tenant lớn, batch và nhu cầu truy cập khi sự cố.

Ví dụ, giới hạn theo IP có thể hữu ích với request chưa xác thực, nhưng một mạng văn phòng có nhiều người dùng chung IP. Ngược lại, kẻ tấn công có nhiều IP có thể vượt qua giới hạn đó. Chính sách cần dựa trên giả định cụ thể, không lấy IP làm đồng nghĩa với một người.

Với đăng nhập, giới hạn theo tài khoản đích giúp hạn chế đoán mật khẩu phân tán nhưng cũng có thể bị lợi dụng để khiến chủ tài khoản bị từ chối đăng nhập. Đặc tả phải cân bằng phòng thủ với khả năng phục hồi: kết hợp tín hiệu nguồn gọi, nhịp thử, phản hồi ít tiết lộ thông tin và luồng xác minh bổ sung khi phù hợp. Không mặc định khóa vĩnh viễn tài khoản chỉ vì có nhiều yêu cầu từ bên ngoài.

## 4. Một chính sách rate limiting phải có những thành phần nào?

Có thể dùng mẫu dưới đây khi viết yêu cầu:

> Đối với **luồng X**, hệ thống phải giới hạn **đại lượng Y** theo **chủ thể K**, tại **điểm thực thi E**, bằng **thuật toán A và tham số P**. Khi không được phép tiếp nhận, hệ thống phải **thực hiện H**, trong **điều kiện lỗi F**, và chứng minh bằng **phép đo hoặc ca kiểm thử V**.

Một bản đặc tả đầy đủ cần trả lời các câu hỏi sau:

| Thành phần | Câu hỏi cần chốt |
|---|---|
| Phạm vi | Endpoint, nhóm endpoint hay toàn bộ tenant? Có nhiều đường truy cập cùng một nghiệp vụ không? |
| Chủ thể | Theo user, tenant, ứng dụng, API credential, đích nhận OTP, IP hay tổ hợp nào? |
| Đơn vị | Đếm request, số bản ghi, dung lượng, điểm chi phí hay job được tiếp nhận? |
| Ngân sách | Ngưỡng, tốc độ nạp lại, burst, chu kỳ và cách xử lý biên thời gian? |
| Cách đếm | Tính mọi lần thử, chỉ lần tiếp nhận hay chỉ khi thành công? Có hoàn trả ngân sách không? |
| Thời điểm | Kiểm tra trước bước nào, đặc biệt trước thao tác tốn tài nguyên hoặc tạo tác dụng phụ? |
| Kết hợp | Request phải vượt qua những ngân sách độc lập nào? Thứ tự kiểm tra và ghi nhận ra sao? |
| Phạm vi phân tán | Trong một process, một vùng hay toàn bộ triển khai? Sai số cho phép bao nhiêu? |
| Từ chối | Mã trạng thái, thông báo, thời gian thử lại và hành vi phía client? |
| Sự cố | Cho qua, từ chối hay chuyển sang một chính sách dự phòng có giới hạn? |
| Ngoại lệ | Ai được cấp ngoại lệ, phạm vi, thời hạn và dấu vết kiểm toán? |
| Kiểm chứng | Ca kiểm thử, chỉ số và bằng chứng nào xác nhận yêu cầu? |

Không nên để các câu hỏi này thành quyết định ngầm trong mã nguồn. Hai triển khai cùng ghi “100 request/phút” có thể tạo hành vi rất khác nhau nếu một bên dùng fixed window, bên kia dùng token bucket.

## 5. Chọn khóa định danh và đơn vị công việc

### 5.1. Khóa phải phản ánh đúng chủ thể cần bảo vệ

Một khóa logic có thể biểu diễn như sau:

```text
(policy_version, policy_id, tenant_id, actor_id, operation_group)
```

Đây là mô hình dữ liệu, không phải yêu cầu lưu nguyên văn mọi thành phần trong kho đếm. Các định danh phải lấy từ nguồn đã được xác minh và được chuẩn hóa trước khi tạo khóa.

Những điểm cần đặc tả:

- `tenant_id` phải được xác định từ ngữ cảnh truy cập đã kiểm tra quyền, không tin trực tiếp một header do client tùy ý gửi.
- Request chưa xác thực không được dùng một `user_id` tự khai để tránh bộ giới hạn trước xác thực.
- Nếu dùng địa chỉ IP, phải định nghĩa danh sách proxy đáng tin và quy tắc lấy IP. Header chuyển tiếp từ nguồn không đáng tin không được dùng để đổi danh tính người gọi.
- Nếu giới hạn theo API credential, đổi credential không được vô tình làm mất giới hạn chung của tài khoản hoặc tenant khi yêu cầu bảo vệ ở cấp đó.
- Chuẩn hóa nơi nhận OTP trước khi tính khóa; không để biến thể biểu diễn của cùng một nơi nhận tạo các ngân sách khác nhau.
- Không đưa password, OTP, bearer token hay API secret vào khóa, log hoặc nhãn metric.

Nếu dùng giá trị băm cho thông tin cá nhân, cần cân nhắc khả năng dò ngược. Băm trực tiếp số điện thoại hoặc email không tự bảo đảm tính bí mật. Có thể dùng HMAC với khóa được quản lý riêng khi cần tạo định danh nội bộ khó suy đoán, kèm chính sách phân quyền và thời hạn lưu.

Kho đếm cũng là tài nguyên có giới hạn. Kẻ tấn công gửi vô số định danh ngẫu nhiên có thể tạo hàng triệu khóa. Cần giới hạn kích thước đầu vào, đặt TTL phù hợp, có cơ chế chặn sớm và theo dõi số lượng khóa hoạt động.

### 5.2. Chọn đơn vị phù hợp với chi phí

Đếm request phù hợp khi chi phí giữa các request tương đối gần nhau. Khi chi phí chênh lệch lớn, có thể dùng điểm công việc:

```text
tra cứu đơn giản: 1 điểm
truy vấn tổng hợp đã được giới hạn: 5 điểm
khởi tạo báo cáo lớn: 20 điểm
```

Điểm chi phí phải được xác định bằng quy tắc phía server. Không cho client tự khai chi phí mà không kiểm chứng. Nếu chi phí chỉ biết sau khi thực hiện, cần mô tả cách đặt trước ngân sách, điều chỉnh hoặc kết hợp với hạn mức thực thi khác.

Với tải lên tệp, một giới hạn theo request vẫn cần giới hạn byte và thời gian đọc. Với xử lý batch, phải chốt rõ một batch tính là một đơn vị hay tính theo số phần tử.

## 6. Thuật toán và hệ quả đối với yêu cầu

### 6.1. Fixed window counter

Chia thời gian thành các cửa sổ cố định và đếm số lần trong từng cửa sổ. Ví dụ: tối đa 100 request trong mỗi phút theo mốc phút của bộ giới hạn.

Ưu điểm là đơn giản và ít trạng thái. Hạn chế nằm ở biên: client có thể gửi 100 request ngay cuối phút và 100 request ngay đầu phút sau. Mỗi cửa sổ vẫn hợp lệ nhưng gần 200 request xuất hiện trong một khoảng thời gian ngắn.

Vì vậy, yêu cầu “không quá 100 request trong bất kỳ khoảng 60 giây liên tiếp nào” không thể được đáp ứng chỉ bằng một fixed window 60 giây thông thường.

### 6.2. Sliding window log và sliding window counter

**Sliding window log** lưu thời điểm các lần được tính, bỏ những lần nằm ngoài cửa sổ và kiểm tra số còn lại. Cách này có thể kiểm soát chính xác số lần trong cửa sổ trượt đã định nghĩa, nhưng tốn bộ nhớ và thao tác hơn khi lưu lượng lớn.

**Sliding window counter** thường kết hợp số đếm ở các cửa sổ lân cận để ước lượng lưu lượng trong khoảng trượt. Nó giảm trạng thái nhưng có sai số phụ thuộc thuật toán và phân bố request. Nếu chọn cách ước lượng, yêu cầu phải nêu được sai số tối đa chấp nhận hoặc giới hạn hành vi được kiểm chứng; tên thuật toán không đủ để suy ra độ chính xác.

Ví dụ một quy ước biên rõ ràng: tại thời điểm `t`, chỉ tính các lần tiếp nhận có thời điểm thuộc `(t - 60 giây, t]`. Lần tiếp nhận đúng tại `t - 60 giây` đã hết hiệu lực.

### 6.3. Token bucket

Token bucket có dung lượng tối đa `B`, nạp lại token với tốc độ `r` token/giây. Request có chi phí `c` chỉ được tiếp nhận khi có đủ `c` token, sau đó tiêu thụ lượng tương ứng.

Ví dụ `B = 20`, `r = 5` và mọi request tốn 1 token:

- Khi bucket đầy, có thể tiếp nhận burst tức thời tối đa 20 request.
- Sau khi hết token, hệ thống chỉ có thể tiếp nhận thêm theo tốc độ nạp lại.
- Khi không có lưu lượng, bucket hồi phục tới 20 token, không tích lũy vô hạn.

Với mô hình nạp liên tục và cập nhật nguyên tử, tổng chi phí được tiếp nhận trong khoảng thời gian dài `Δt` bị chặn trên bởi `B + r × Δt`. Đây là giới hạn về tổng công việc có tính cả burst, không có nghĩa là mọi cửa sổ một giây đều chỉ nhận đúng `r` request.

Đặc tả phải chốt trạng thái ban đầu, độ phân giải thời gian, cách làm tròn và hành vi khi request có `c > B`. Trường hợp chi phí lớn hơn dung lượng bucket cần được từ chối hoặc đi theo một luồng có ngân sách phù hợp; chờ nạp lại sẽ không bao giờ giải quyết được.

### 6.4. Leaky bucket và cơ chế làm đều nhịp

Tên leaky bucket được dùng cho nhiều biến thể. Một biến thể xếp công việc vào hàng đợi hữu hạn rồi đưa ra xử lý theo nhịp cố định; biến thể khác đo mức tích lũy để quyết định từ chối. Cần mô tả hành vi cụ thể thay vì chỉ ghi tên.

Nếu có hàng đợi, yêu cầu phải nêu dung lượng, thời gian chờ tối đa, hủy công việc khi hết hạn và công bằng giữa các chủ thể. Hàng đợi vô hạn chỉ chuyển quá tải thành tăng độ trễ và cạn bộ nhớ.

### 6.5. Chọn theo mục tiêu

| Mục tiêu | Hướng lựa chọn | Điều phải kiểm chứng |
|---|---|---|
| Chấp nhận burst nhỏ và khống chế tốc độ dài hạn | Token bucket | Dung lượng burst, nạp lại, cập nhật nguyên tử |
| Chặn chính xác số lần trong cửa sổ trượt | Sliding window log | Quy ước biên và chi phí trạng thái |
| Lưu lượng lớn, chấp nhận xấp xỉ | Sliding window counter hoặc bộ đếm phân tán có sai số | Cận sai số, điều kiện phân tải và hành vi vượt cận |
| Cần làm đều tốc độ gửi xuống phụ thuộc | Cơ chế pacing với hàng đợi hữu hạn | Tốc độ phát, độ trễ, dung lượng và cơ chế hủy |
| Hạn mức thô theo kỳ, không nhạy burst | Fixed window | Burst ở biên và các kiểm soát bổ sung |

## 7. Kiến trúc thực thi và chính sách nhiều tầng

Một luồng điển hình có thể được tổ chức như sau:

```text
Client
  -> Edge: giới hạn thô theo nguồn mạng và kiểm tra kích thước cơ bản
  -> Gateway: xác thực credential, giới hạn theo ứng dụng hoặc tenant
  -> Service: kiểm tra quyền và chính sách theo nghiệp vụ
  -> Admission control: giới hạn đồng thời, hàng đợi và nhận job
  -> Worker / Cơ sở dữ liệu / Dịch vụ phụ thuộc
```

Đặt giới hạn sớm giúp giảm chi phí xử lý request bị từ chối. Tuy nhiên, ở lớp edge thường chưa biết đủ user, tenant hoặc chi phí nghiệp vụ. Vì vậy cần phân tầng kiểm soát và xác định rõ trách nhiệm từng tầng.

Request có thể phải đáp ứng đồng thời:

```text
ngân sách theo user
AND ngân sách theo tenant
AND ngân sách cho nhóm thao tác
AND ngân sách toàn hệ thống
AND giới hạn công việc đang chạy hoặc đang chờ
```

Giới hạn theo user giúp công bằng giữa người dùng. Giới hạn tenant ngăn việc tạo nhiều user để tăng tổng mức sử dụng. Ngân sách toàn hệ thống bảo vệ năng lực chung khi số tenant tăng hoặc khi cùng chịu một đợt tấn công.

Tổng các mức trần theo tenant có thể vượt năng lực toàn hệ thống. Mức trần là lượng tối đa được phép dùng khi có tài nguyên, không tự động là năng lực được dành sẵn. Nếu hợp đồng yêu cầu đảm bảo tối thiểu cho từng tenant, cần chính sách phân bổ và ưu tiên riêng.

Mọi đường đi tới cùng nghiệp vụ cần được xem xét: API phiên bản cũ, endpoint thay thế, giao diện quản trị, webhook và luồng nội bộ. Một giới hạn ở endpoint công khai có thể bị vô hiệu nếu một đường gọi khác tạo cùng loại công việc mà không chịu kiểm soát tương đương.

## 8. Hệ thống phân tán: tính nguyên tử, sai số và khởi động lại

### 8.1. Kiểm tra và cập nhật phải cùng một quyết định

Mã giả dưới đây mô tả một thao tác logic token bucket. Toàn bộ phần đọc trạng thái, nạp lại, quyết định và tiêu thụ cần được thực thi nguyên tử tại nơi giữ trạng thái:

```text
consume(key, cost, now):
    require cost > 0
    atomically:
        state = load_or_initialize(key, tokens=B, last_refill=now)
        elapsed = max(0, now - state.last_refill)
        available = min(B, state.tokens + r * elapsed)

        if cost > B:
            return DENIED_IMPOSSIBLE_COST

        if available < cost:
            save(tokens=available, last_refill=now)
            return DENIED, retry_after=(cost - available) / r

        save(tokens=available - cost, last_refill=now)
        return ALLOWED
```

Mã giả giả định `r > 0`, nguồn thời gian không lùi, không có tranh chấp cho lần thử tiếp theo và chưa biểu diễn TTL, độ chính xác số học, timeout hoặc nhiều ngân sách. Thời gian chờ tính được là thời điểm sớm nhất có thể đủ token nếu không có yêu cầu khác tiêu thụ trước đó, không phải cam kết chắc chắn sẽ được tiếp nhận.

Nếu hai instance cùng đọc “còn 1 token” rồi đều cho qua, chính sách có thể bị vượt. Yêu cầu phải chỉ rõ thao tác nguyên tử tương ứng với kho trạng thái được chọn; một giao dịch ở cơ sở dữ liệu nghiệp vụ không mặc nhiên bảo vệ bộ đếm ở kho khác.

### 8.2. Giới hạn cục bộ khác giới hạn toàn cục

Nếu mỗi replica tự cho phép 100 request/phút và có 5 replica, tổng mức tiếp nhận có thể lên tới 500 request/phút. Autoscaling làm thay đổi hành vi này nếu không có cơ chế phối hợp.

Có ba hướng thường gặp:

- **Trạng thái dùng chung:** dễ diễn đạt ngân sách chung hơn nhưng phụ thuộc vào độ trễ và khả năng phục vụ của kho đếm.
- **Phân bổ ngân sách cho replica:** giảm lượt truy cập kho chung nhưng phải xác định vòng đời phần được cấp, tái phân bổ, mất replica và cận sai số.
- **Chính sách cục bộ có chủ đích:** phù hợp với một số lớp bảo vệ thô, với điều kiện tài liệu ghi đúng phạm vi và có ngân sách chung ở nơi cần thiết.

Với nhiều vùng, lựa chọn đồng bộ mạnh hay ngân sách phân vùng ảnh hưởng độ trễ và hành vi khi mất kết nối. Cụm từ “giới hạn toàn cầu” phải đi kèm cơ chế thực thi và cận vượt ngưỡng khi có phân vùng mạng.

### 8.3. Thời gian và vòng đời trạng thái

Trong một process, nên dùng nguồn thời gian đơn điệu để tính khoảng trôi qua khi nền tảng hỗ trợ. Với trạng thái dùng chung, các instance cần dùng nguồn thời gian hoặc quy tắc thời gian thống nhất; không trộn tùy tiện đồng hồ đơn điệu của các máy khác nhau. Nếu đồng hồ có thể lùi, phải có quy tắc giữ mốc thời gian đã quan sát và tránh nạp lại token hai lần cho cùng khoảng thời gian.

TTL phải tương thích với thuật toán. Xóa sớm một bucket đang thiếu token rồi tạo lại bucket đầy sẽ cấp thêm ngân sách ngoài thiết kế. Khởi động lại, eviction, thay khóa định danh và đổi phiên bản policy đều có thể tạo hiệu ứng tương tự nếu không được đặc tả.

### 8.4. Nhiều ngân sách và kết quả không xác định

Một request có thể tiêu thụ token ở bộ đếm user rồi bị từ chối ở bộ đếm tenant. Cần chốt có giữ phần đã tiêu thụ hay hoàn lại. Giữ lại có thể là lựa chọn hợp lệ khi đếm mọi lần thử, nhưng phải được nêu rõ. Hoàn lại cần tránh trả dư token khi có retry hoặc lỗi cạnh tranh.

Timeout khi gọi bộ đếm có thể xảy ra sau khi token đã được trừ nhưng trước khi service nhận được kết quả. Lặp lại thao tác một cách mù quáng có thể trừ hai lần. Yêu cầu cần xác định cách xử lý kết quả không chắc chắn, chẳng hạn mã định danh lần quyết định có hiệu lực ngắn hoặc chính sách dự phòng bảo thủ.

Idempotency của nghiệp vụ không tự làm thao tác tiêu thụ token trở thành idempotent. Cần phân biệt ngân sách chống lạm dụng theo lần thử với ngân sách theo job thực sự được tạo.

## 9. Phản hồi khi vượt giới hạn và hành vi retry

Đối với HTTP, mã `429 Too Many Requests` phù hợp khi một yêu cầu bị từ chối do chính sách giới hạn tốc độ. Nếu dịch vụ không thể tiếp nhận do sự cố năng lực chung hoặc phụ thuộc bị lỗi, phản hồi như `503 Service Unavailable` có thể phản ánh nguyên nhân tốt hơn. Hợp đồng API cần phân biệt hai tình huống này.

Ví dụ phản hồi cho giới hạn theo tenant:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 12

{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Bạn đã đạt giới hạn tạo báo cáo. Vui lòng thử lại sau.",
  "retryAfterSeconds": 12,
  "requestId": "req-example-001"
}
```

`Retry-After: 12` biểu thị khoảng chờ 12 giây trong ví dụ này. Server phải định nghĩa cách làm tròn để client không thử lại sớm chỉ vì số giây bị cắt xuống. Khi không thể xác định thời gian phục hồi, không nên đưa ra một mốc chính xác thiếu cơ sở.

Nếu có nhiều giới hạn đồng thời, thời gian thử lại được công bố cần phản ánh các giới hạn đã biết đang chặn request. Kể cả vậy, lưu lượng cạnh tranh hoặc sự thay đổi năng lực vẫn có thể khiến lần thử lại tiếp tục bị từ chối.

Yêu cầu cho client nên bao gồm:

- Tôn trọng thời gian chờ do server công bố khi có.
- Áp dụng backoff và jitter để tránh nhiều client gửi lại cùng lúc.
- Có số lần thử hoặc thời gian retry tối đa, cùng hạn chót cho toàn bộ thao tác.
- Chỉ tự động retry thao tác tạo tác dụng phụ khi hợp đồng idempotency cho phép.
- Không mở thêm nhiều kết nối song song để bù cho một request bị giới hạn.

Thông báo không nên tiết lộ tài khoản hoặc nơi nhận OTP có tồn tại hay không. Các trường đếm còn lại, tên policy nội bộ và phạm vi giới hạn phải được đánh giá theo nhu cầu của client và mô hình đe dọa trước khi công bố.

## 10. Khi thành phần giới hạn gặp lỗi

Không có lựa chọn fail-open hoặc fail-closed phù hợp cho mọi luồng:

| Chính sách lỗi | Lợi ích | Rủi ro | Điều cần đặc tả |
|---|---|---|---|
| Fail-open | Giữ khả năng phục vụ khi kho đếm lỗi | Có thể làm quá tải tài nguyên phía sau | Phạm vi, thời hạn và giới hạn dự phòng |
| Fail-closed | Không tiếp nhận công việc khi thiếu quyết định cho phép | Bộ giới hạn trở thành điểm làm gián đoạn dịch vụ | Luồng phục hồi và mức ảnh hưởng chấp nhận được |
| Chế độ suy giảm có giới hạn | Vẫn phục vụ một phần bằng ngân sách dự phòng | Sai số và độ công bằng thay đổi | Cận tổng, cách chia ngân sách và điều kiện quay lại |

Ví dụ, luồng gửi SMS có chi phí trực tiếp có thể từ chối gửi mới khi không xác định được ngân sách. Một API đọc dữ liệu ít tốn tài nguyên có thể được phép dùng giới hạn cục bộ dự phòng trong thời gian ngắn. Quyết định phải xuất phát từ rủi ro và mục tiêu phục vụ đã thống nhất.

Đối với chế độ dự phòng, không chỉ ghi “100 request/giây/instance”. Nếu số instance tăng gấp đôi, tổng ngân sách cũng tăng gấp đôi. Cần giới hạn số instance có thể sử dụng ngân sách đó hoặc cấp trước tổng ngân sách có ràng buộc. Nếu không chứng minh được cận vượt ngưỡng, đặc tả phải thừa nhận giới hạn đó.

Các yêu cầu vận hành cần xác định timeout cho thao tác quyết định, ngưỡng chuyển chế độ, cảnh báo, điều kiện phục hồi và cách xử lý trạng thái sau khi kết nối lại. Không được âm thầm bỏ qua lỗi limiter rồi ghi nhận như một lần cho phép bình thường.

## 11. Ví dụ đặc tả có thể kiểm chứng: tạo báo cáo

### 11.1. Bối cảnh và mục tiêu

Hệ thống giả định cung cấp `POST /reports` cho nhiều tenant. Mỗi báo cáo là một job đắt tài nguyên. Rủi ro `R-AV-04` là một tenant hoặc client lỗi tạo quá nhiều job, làm cạn worker và kéo dài thời gian chờ của tenant khác.

Mục tiêu là giới hạn số job mới được tiếp nhận, giữ hàng đợi có cận và trả phản hồi rõ ràng. Bước xác thực, phân quyền truy cập dữ liệu và kiểm tra định dạng đầu vào vẫn là các điều kiện độc lập.

### 11.2. Tập yêu cầu minh họa

| ID | Yêu cầu |
|---|---|
| SEC-RL-01 | Mỗi tenant được tiếp nhận tối đa 5 job mới trong cửa sổ trượt `(t - 60 giây, t]`, dùng thời điểm tiếp nhận do server xác định. |
| SEC-RL-02 | Request không có tenant hợp lệ hoặc không đủ quyền tạo báo cáo không được tạo job và không được khởi chạy tác vụ báo cáo. |
| SEC-RL-03 | Một job mới chỉ được tiếp nhận sau khi đã vượt qua kiểm tra ngân sách tenant và giới hạn hàng đợi. Tại một thời điểm, toàn hệ thống có tối đa 100 job chờ; mỗi tenant có tối đa 2 job đang chạy. |
| SEC-RL-04 | Khi vượt giới hạn tần suất theo tenant, API trả `429`, mã lỗi ổn định và thời gian thử lại tính theo cửa sổ. Request bị từ chối không tạo job. |
| SEC-RL-05 | Khi hàng đợi chung đã đầy hoặc hệ thống không thể đưa ra quyết định an toàn, API không tiếp nhận job mới; lỗi năng lực hoặc phụ thuộc được phản ánh bằng `503`, có hướng dẫn thử lại khi xác định được. |
| SEC-RL-06 | Chính sách áp dụng trên toàn bộ replica trong phạm vi triển khai; request đồng thời không được làm vượt ngưỡng SEC-RL-01 hoặc giới hạn hàng đợi. |
| SEC-RL-07 | Khi kho quyết định rate limit không hoạt động, luồng tạo báo cáo chuyển sang từ chối tiếp nhận job mới; hạn chót cho bước quyết định là 100 ms. Không thực hiện xuất báo cáo trước quyết định. |
| SEC-RL-08 | Trong thời hạn bảo vệ idempotency 24 giờ kể từ lúc tiếp nhận, retry của job đã được tiếp nhận với cùng khóa hợp lệ trả lại cùng job, không tạo thêm job và không tiêu thụ thêm ngân sách job mới. Mọi lần thử vẫn chịu giới hạn chống lạm dụng ở gateway. |
| SEC-RL-09 | Đo riêng số quyết định cho phép, từ chối và lỗi theo policy; khi thử tải trong phạm vi thiết kế, độ trễ p99 của quyết định limiter không vượt 20 ms. |
| SEC-RL-10 | Đổi ngưỡng hoặc cấp ngoại lệ phải có người thực hiện, phạm vi, lý do, thời điểm, hạn hết hiệu lực nếu là ngoại lệ và dấu vết kiểm toán. |

Mốc 20 ms là ngân sách độ trễ trong điều kiện vận hành bình thường của ví dụ. Mốc 100 ms là hạn chót cho bước quyết định khi thành phần phụ thuộc không trả lời, không bao gồm thời gian truyền qua mạng tới client. Hai mốc phục vụ hai điều kiện khác nhau và cần đo riêng.

Cụm “toàn bộ replica” ở đây bao gồm mọi đường tạo job trong phạm vi triển khai được đặc tả. Nếu sản phẩm hoạt động ở nhiều vùng, phải bổ sung rõ tenant có bị giới hạn xuyên vùng hay được phân bổ ngân sách theo vùng.

### 11.3. Quy tắc đếm và nhận job

Để các yêu cầu trên không mâu thuẫn nhau, thiết kế phải chốt thêm:

1. Một job mới được tính khi quyền tiếp nhận và bản ghi job được xác lập bền vững theo thiết kế.
2. Job xử lý thất bại về sau vẫn được tính là một job đã tiếp nhận trong cửa sổ; không tự động hoàn ngân sách theo kết quả xử lý.
3. Request bị từ chối trước khi tiếp nhận không tiêu thụ ngân sách 5 job, nhưng vẫn được tính ở lớp giới hạn số lần thử tại gateway.
4. Retry cùng khóa idempotency phải được xác minh đúng tenant và đúng nội dung thao tác trước khi trả job cũ. Cùng khóa nhưng khác nội dung bị từ chối theo hợp đồng API.
5. Khi kết quả tiếp nhận không chắc chắn do lỗi mạng, hệ thống phải có cách đối soát theo khóa idempotency, không tạo job mới chỉ vì client chưa nhận phản hồi.
6. Sau thời hạn bảo vệ idempotency, client không được mặc định một khóa cũ vẫn ngăn tạo job mới; hợp đồng API phải nêu rõ cách đối soát và retry ngoài thời hạn.

Nếu bộ đếm và kho job ở hai hệ thống khác nhau, cần một thiết kế phối hợp bảo toàn các bất biến trên, chẳng hạn đặt trước suất tiếp nhận, xác nhận và phục hồi các suất bị treo. Việc gọi bộ đếm rồi đẩy job vào queue bằng hai bước rời rạc chưa tự chứng minh được tính đúng khi có lỗi.

Cũng cần ngăn đường gọi trực tiếp vào worker hoặc queue bỏ qua admission control. Quyền ghi vào hàng đợi và quyền thay đổi policy là một phần của yêu cầu bảo mật cho cơ chế này.

## 12. Tiêu chí kiểm thử và bằng chứng

### 12.1. Ma trận kiểm chứng ví dụ

| Ca kiểm thử | Thiết lập và kích thích | Kết quả cần quan sát |
|---|---|---|
| T01 — Đủ ngưỡng | Tenant A tạo 5 job trong 10 giây; hàng đợi còn chỗ | Cả 5 job được tiếp nhận; không bị từ chối do tần suất |
| T02 — Vượt ngưỡng | Sau T01, gửi yêu cầu tạo job thứ 6 trước khi lần tiếp nhận đầu hết cửa sổ | Trả `429`; tổng job mới của A vẫn là 5; không có tác dụng phụ tạo job |
| T03 — Biên cửa sổ | Job cũ nhất tại giây 0; thử một lần tại 59,999 giây và một lần tại 60,000 giây bằng đồng hồ kiểm thử | Trước biên vẫn bị chặn; tại biên, job ở giây 0 không còn được tính theo `(t - 60, t]`, nếu không có giới hạn khác đang chặn |
| T04 — Đồng thời | 50 yêu cầu hợp lệ tạo job khác nhau của A đồng thời qua nhiều replica; lịch sử rỗng, queue còn chỗ, các phụ thuộc hoạt động bình thường | Đúng 5 job được tiếp nhận trong cửa sổ; các lần còn lại bị từ chối do tần suất |
| T05 — Cô lập tenant | A đã cạn ngân sách, B gửi yêu cầu khi năng lực chung còn đủ | B không bị từ chối chỉ vì A đã hết ngân sách |
| T06 — Giới hạn đồng thời | A có nhiều job được tiếp nhận, worker hoạt động bình thường | Không lúc nào có hơn 2 job của A đang chạy |
| T07 — Hàng đợi đầy | Tạo trạng thái có 100 job đang chờ rồi gửi thêm yêu cầu | Không nhận job mới; phản hồi theo lỗi năng lực đã đặc tả |
| T08 — Kho đếm lỗi | Làm thao tác ra quyết định bị timeout | Không tạo job mới; bước quyết định kết thúc trong hạn chót; metric ghi nhận lỗi và chế độ xử lý |
| T09 — Khởi động lại | A đã dùng đủ ngân sách; restart một replica rồi gửi tiếp | Không có bucket hoặc cửa sổ mới cho A chỉ vì replica vừa restart |
| T10 — Idempotency | Trong 24 giờ, retry cùng khóa và cùng nội dung cho một job đã tiếp nhận | Trả cùng job; không tăng số job mới hoặc trừ thêm ngân sách job |
| T11 — Giả mạo nguồn | Đổi header tenant hoặc header IP không đáng tin | Không chuyển ngân sách sang một chủ thể tùy ý do client lựa chọn |
| T12 — Độ trễ | Đo limiter tại mức tải và phân bố khóa đã định nghĩa | p99 không vượt ngân sách; số liệu tách biệt quyết định bình thường, từ chối và lỗi |

Để kiểm thử tái lập được, phải ghi số replica, mức tải, phân bố tenant, trạng thái ban đầu, nguồn thời gian và thời gian đo. Một kiểm thử chỉ gửi request tuần tự tới một replica không chứng minh được yêu cầu toàn hệ thống.

Với T03, tạo lịch sử có đủ 5 job còn hiệu lực trước lần thử đầu và kiểm soát đồng hồ để không phụ thuộc lịch chạy của máy kiểm thử. Với T04, cần đồng bộ thời điểm phát tải và tránh để cửa sổ trôi sang thời điểm hết hiệu lực của job cũ trong lúc kiểm tra.

Việc quan sát response phải đi kèm đối chiếu bản ghi job hoặc sự kiện tiếp nhận bền vững; chỉ đếm mã `429` không đủ chứng minh không có job ngoài ý muốn.

### 12.2. Kiểm thử lỗi và vòng đời

Ngoài luồng thông thường, cần kiểm chứng:

- Hai request đồng thời tranh token cuối hoặc suất cuối trong hàng đợi.
- Timeout xảy ra sau khi cập nhật ngân sách nhưng trước khi caller nhận kết quả.
- Eviction hoặc TTL hết hạn, thay đổi policy và chuyển phiên bản khóa.
- Mất một phần kết nối, thêm hoặc giảm replica, khôi phục kho đếm.
- Burst của lưu lượng hợp lệ, nhiều user cùng NAT và phân phối tải lệch giữa replica.
- Tạo nhiều định danh ngẫu nhiên nhằm làm tăng số khóa, kích thước kho đếm và cardinality metric.
- Retry đồng loạt từ client khi dịch vụ vừa phục hồi.

Mỗi ca phải có kết quả mong đợi gắn với lựa chọn kiến trúc thực tế. Nếu chấp nhận sai số phân tán, cần kiểm tra sai số nằm trong cận đã cam kết, không thay tiêu chí bằng “đa số request đã bị chặn”.

## 13. Logging, metric và vận hành

Log quyết định nên có đủ dữ kiện để điều tra nhưng tránh trở thành nguồn quá tải hoặc rò rỉ dữ liệu:

```text
request_id
policy_id, policy_version
operation_group
decision = allowed | denied | error
reason = budget_exhausted | dependency_timeout | invalid_identity | ...
subject_ref = định danh nội bộ được kiểm soát
retry_after_seconds nếu có cơ sở xác định
limiter_latency_ms
mode = normal | fallback
```

Không cần ghi đầy đủ mọi request được phép nếu lưu lượng quá lớn. Có thể dùng metric tổng hợp và sampling cho log thường, nhưng log thay đổi cấu hình và sự kiện quan trọng phải tuân theo yêu cầu kiểm toán đã chốt. Request bị chặn hàng triệu lần cũng không được làm đầy ổ đĩa vì log vô hạn.

Các metric thường hữu ích gồm:

- Tốc độ request được phép, bị từ chối và lỗi theo nhóm policy.
- Độ trễ p50, p95, p99 của thao tác quyết định.
- Số lần chuyển chế độ dự phòng và thời gian ở chế độ đó.
- Số khóa hoạt động, bộ nhớ kho trạng thái và số lần eviction.
- Số job chờ, số job chạy, tuổi của job lâu nhất và mức sử dụng dịch vụ phụ thuộc.

Tránh gắn user ID, IP hoặc API key làm nhãn metric không giới hạn. Dữ liệu chi tiết theo chủ thể có thể đưa vào hệ thống log hoặc phân tích được kiểm soát phù hợp hơn.

Tỷ lệ `429` tăng có thể do tấn công, client lỗi, policy quá chặt hoặc nhu cầu hợp lệ tăng. Cảnh báo cần liên kết với độ trễ, tỷ lệ lỗi, hàng đợi và tình trạng phụ thuộc. Không tự nâng ngưỡng chỉ để giảm số phản hồi bị giới hạn khi chưa hiểu nguyên nhân.

Quy trình vận hành nên có quyền truy cập cấu hình tối thiểu cần thiết, theo dõi phiên bản, kiểm tra trước khi áp dụng, khả năng rollback và giới hạn thời hạn cho ngoại lệ. Khi cập nhật policy, cần nêu rõ giữ hay chuyển đổi trạng thái hiện tại; việc vô tình làm đầy lại mọi bucket có thể tạo burst lớn.

## 14. Liên kết yêu cầu với rủi ro, kiến trúc và vòng đời phát triển

Một chuỗi truy vết tối giản cho ví dụ báo cáo:

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng kiểm chứng |
|---|---|---|---|
| R-AV-04: Một tenant chiếm năng lực tiếp nhận job | SEC-RL-01, 03, 06 | Sliding window dùng chung; admission control | T02, T04, T05, T07 và số job thực được tạo |
| Mất kiểm soát khi kho đếm lỗi | SEC-RL-05, 07 | Từ chối job mới sau thời hạn quyết định | T08 và kiểm thử lỗi sau khi ghi trạng thái |
| Retry tạo thêm job hoặc trừ ngân sách lặp | SEC-RL-08 | Idempotency gắn tenant và nội dung; đối soát kết quả | T10 và kiểm thử mất phản hồi |
| Limiter làm tăng độ trễ ngoài ngân sách | SEC-RL-09 | Điểm thực thi và kho trạng thái phù hợp tải | T12, phân vị độ trễ và đo chi phí |
| Thay đổi ngưỡng làm mất hiệu lực kiểm soát | SEC-RL-10 | Cấu hình có phân quyền, phiên bản và audit | Thử quyền thay đổi, hết hạn ngoại lệ và rollback |

Trong giai đoạn thiết kế, tập trung chốt tài nguyên cần bảo vệ và các bất biến. Khi triển khai, chuyển chúng thành quyết định nguyên tử, khóa chuẩn hóa và xử lý lỗi. Khi kiểm thử, kiểm tra cả phản hồi lẫn tác dụng phụ. Khi vận hành, so sánh mức sử dụng thực tế với giả định ban đầu và cập nhật chính sách có kiểm soát.

Không chỉ lưu tên một công cụ trong tài liệu yêu cầu. Công cụ là lựa chọn triển khai; yêu cầu cần giữ được ý nghĩa khi thay gateway, kho đếm hoặc cách phân bổ worker.

## 15. Các lỗi đặc tả thường gặp và cách sửa

| Đặc tả thiếu rõ ràng | Vấn đề | Cách viết tốt hơn |
|---|---|---|
| “Mỗi API tối đa 100 request/phút” | Chưa có chủ thể, cửa sổ và phạm vi phân tán | Nêu nhóm API, khóa, thuật toán, tham số, phạm vi và tiêu chí vượt ngưỡng |
| “Giới hạn theo IP là đủ” | Có NAT, proxy và bot phân tán | Chọn tín hiệu theo mô hình đe dọa; kết hợp ngân sách sau xác thực |
| “Hết ngưỡng thì chờ” | Có thể tạo hàng đợi vô hạn | Chốt có từ chối hay xếp hàng; nếu xếp hàng, nêu cận và thời gian chờ |
| “Lỗi kho đếm thì cho qua” | Không có cận tài nguyên trong lúc sự cố | Định nghĩa rõ phạm vi fail-open hoặc ngân sách dự phòng |
| “Đã có token bucket nên không quá tải” | Request nặng và tác vụ kéo dài vẫn chiếm tài nguyên | Kết hợp giới hạn đồng thời, chi phí, timeout và queue bound |
| “429 nghĩa là không có tác dụng phụ” | Có thể đã tạo job trước khi kiểm tra | Đặt quyết định tiếp nhận trước tác dụng phụ và kiểm chứng bằng dữ liệu thực |
| “Giới hạn toàn hệ thống” | Trạng thái có thể chỉ nằm trong mỗi process | Nêu cơ chế phối hợp và cận sai số khi nhiều replica hoặc vùng |
| “Retry cùng idempotency key luôn miễn phí” | Có thể bị lạm dụng để tạo tải tra cứu vô hạn | Tách ngân sách job mới khỏi giới hạn mọi lần thử |
| “Bật log tất cả để điều tra” | Log thành điểm cạn tài nguyên và chứa dữ liệu nhạy cảm | Chốt trường dữ liệu, sampling, retention và quyền truy cập |

## 16. Bài tập áp dụng

Giả sử bạn thiết kế API gửi OTP cho một ứng dụng có nhiều tenant. Hãy viết một tập yêu cầu gồm:

1. Tài nguyên cần bảo vệ, tác nhân và ít nhất hai cách lạm dụng, trong đó có một cách dùng nhiều IP.
2. Các ngân sách theo nơi nhận, nguồn gọi, tenant và toàn hệ thống; giải thích vì sao cần từng cấp.
3. Cách chuẩn hóa và bảo vệ định danh, tránh tiết lộ nơi nhận có tồn tại hay không.
4. Thuật toán, tham số minh họa và quy tắc đếm với lần thử gửi thất bại hoặc kết quả gửi chưa xác định.
5. Phản hồi khi hết ngân sách, hành vi khi nhà cung cấp OTP lỗi và khả năng chống retry tạo gửi trùng.
6. Ba ca kiểm thử biên, một ca đồng thời, một ca sự cố và bằng chứng không phát sinh tin nhắn ngoài ý muốn.

Tự đánh giá bản đặc tả bằng câu hỏi: **Một nhóm triển khai độc lập có thể dựa vào tài liệu này để xây cùng một hành vi, và một nhóm kiểm thử độc lập có thể kết luận đạt hay không?** Nếu vẫn phải đoán khóa, cách đếm, cửa sổ hoặc hành vi khi lỗi, yêu cầu cần được làm rõ thêm.
