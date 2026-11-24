# Thời hạn thuê và khoảng cách giữa các nhịp báo sống

## 1. Heartbeat và lease giải quyết vấn đề gì?

Trong Spring Cloud Service Discovery, Eureka cần biết instance nào còn có thể nhận request. Khi một ứng dụng khởi động, Eureka Client đăng ký instance với Eureka Server. Sau đó client gửi heartbeat định kỳ để báo rằng instance vẫn đang hoạt động. Mỗi lần heartbeat thành công, server gia hạn thời hạn thuê (lease) của instance trong registry.

Hai khái niệm này liên quan chặt chẽ nhưng không giống nhau:

- **Heartbeat (nhịp báo sống):** thông điệp định kỳ từ Eureka Client đến Eureka Server để gia hạn đăng ký.
- **Lease (thời hạn thuê):** khoảng thời gian server chấp nhận giữ một instance nếu chưa nhận được lần gia hạn tiếp theo.

Heartbeat là tín hiệu được gửi đi; lease là giới hạn thời gian mà registry dùng để đánh giá một đăng ký có còn hiệu lực hay không. Nếu client dừng đột ngột hoặc mất kết nối, server sẽ không nhận được heartbeat và lease có thể hết hạn.

Ví dụ, một instance thanh toán đăng ký với Eureka. Nếu instance vẫn chạy bình thường, nó liên tục gia hạn lease. Nếu tiến trình bị kill hoặc máy chủ mất mạng, heartbeat dừng lại. Sau thời gian chờ được cấu hình, Eureka có thể loại instance đó khỏi registry để các client khác không tiếp tục chọn nó.

## 2. Vòng đời của heartbeat và lease

Một instance thường trải qua các bước sau:

1. **Register:** Eureka Client gửi thông tin instance như application name, hostname, IP, port và trạng thái đến Eureka Server.
2. **Renew:** client gửi heartbeat theo chu kỳ để gia hạn lease.
3. **Expire:** nếu server không nhận heartbeat trong thời hạn lease, đăng ký được xem là hết hạn.
4. **Evict:** tác vụ eviction của Eureka Server kiểm tra các lease hết hạn và loại instance khỏi registry, nếu cơ chế self-preservation không ngăn việc eviction.
5. **Cancel:** nếu ứng dụng dừng có trật tự và gửi yêu cầu hủy đăng ký, server có thể xóa instance mà không cần chờ lease hết hạn.

~~~mermaid
stateDiagram-v2
    [*] --> Registered: Register
    Registered --> Registered: Heartbeat / Renew
    Registered --> Expired: Không nhận renew trước hạn lease
    Expired --> Evicted: Eviction task cho phép xóa
    Registered --> Cancelled: Cancel khi shutdown có trật tự
    Evicted --> [*]
    Cancelled --> [*]
~~~

Điểm quan trọng là **lease hết hạn không đồng nghĩa instance biến mất khỏi registry ngay tại đúng giây đó**. Server còn phải chạy tác vụ eviction, và self-preservation có thể tạm dừng việc xóa instance. Ngoài ra, các Eureka Client đang dùng registry cache có thể cần thời gian để nhận được danh sách đã cập nhật.

## 3. Các khoảng thời gian mặc định thường gặp

Với cấu hình Eureka phổ biến trong Spring Cloud Netflix, hai giá trị mặc định thường được sử dụng là:

| Thuộc tính | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---:|---|
| **eureka.instance.lease-renewal-interval-in-seconds** | 30 giây | Khoảng cách giữa hai lần client gửi heartbeat |
| **eureka.instance.lease-expiration-duration-in-seconds** | 90 giây | Thời gian server chờ kể từ lần gia hạn cuối trước khi lease hết hạn |

Với heartbeat 30 giây và lease 90 giây, server cho phép instance bỏ lỡ một vài nhịp heartbeat trước khi xem lease là hết hạn. Cách đặt này giúp tránh loại instance chỉ vì một heartbeat bị trễ trong thời gian ngắn.

Hai giá trị trên là mặc định thường gặp, không phải hằng số bắt buộc. Chúng có thể được thay đổi theo phiên bản thư viện và cấu hình triển khai. Khi vận hành, hãy kiểm tra cấu hình hiệu lực của ứng dụng và Eureka Server thay vì chỉ dựa vào giá trị mặc định được nhớ từ một phiên bản khác.

### 3.1. Ví dụ tính thời điểm lease hết hạn

Giả sử server nhận heartbeat gần nhất tại thời điểm 10:00:00 và lease duration là 90 giây:

| Thời điểm | Diễn biến |
|---|---|
| 10:00:00 | Server nhận heartbeat và gia hạn lease |
| 10:00:30 | Client dự kiến gửi heartbeat tiếp theo |
| 10:01:00 | Client dự kiến gửi heartbeat tiếp theo |
| 10:01:30 | Đã đủ 90 giây kể từ lần renew cuối; lease có thể được xem là hết hạn |
| Sau 10:01:30 | Tác vụ eviction kiểm tra và có thể xóa instance |

Đây là ví dụ minh họa với các mốc lý tưởng. Thời điểm thực tế phụ thuộc vào thời gian gửi/nhận request, độ trễ mạng, lịch thực thi tác vụ và trạng thái self-preservation.

## 4. Phân biệt thời điểm hết hạn và thời điểm bị xóa

Eureka Server không nhất thiết xóa instance ngay khi đồng hồ vừa vượt qua lease duration. Server có tác vụ định kỳ để kiểm tra và eviction các lease hết hạn. Thuộc tính thường dùng để điều chỉnh chu kỳ tác vụ này là:

| Thuộc tính | Giá trị mặc định thường gặp | Vai trò |
|---|---:|---|
| **eureka.server.eviction-interval-timer-in-ms** | 60000 ms | Khoảng thời gian giữa các lần chạy tác vụ eviction |

Ví dụ, nếu lease hết hạn lúc 10:01:30 và tác vụ eviction chạy mỗi 60 giây, instance có thể được loại ở lần kiểm tra kế tiếp. Do đó, thời gian từ lần heartbeat cuối đến khi instance bị xóa có thể dài hơn 90 giây.

Có thể hình dung tổng thời gian như sau:

~~~text
Lần renew cuối
    |
    |<------ lease duration ------>|
    |                              |
    v                              v
 10:00:00                      10:01:30
                                  |
                                  | Chờ lần eviction kế tiếp
                                  v
                             Instance bị xóa
~~~

Không nên dùng riêng lease duration để cam kết thời gian phát hiện lỗi cho nghiệp vụ. Nếu hệ thống cần ngừng gửi request đến instance lỗi nhanh hơn, hãy kết hợp health check, timeout và chính sách retry ở phía gọi dịch vụ.

## 5. Cấu hình heartbeat và lease trong Spring Cloud

Các thuộc tính dưới đây thường được đặt trong file cấu hình của từng ứng dụng đăng ký với Eureka:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
~~~

Trong cấu hình này:

- **lease-renewal-interval-in-seconds** quy định chu kỳ gửi heartbeat của instance.
- **lease-expiration-duration-in-seconds** quy định thời hạn lease mà instance quảng bá cho Eureka.
- **service-url.defaultZone** xác định endpoint Eureka Server mà client sử dụng.

Để điều chỉnh eviction, cấu hình thuộc tính ở Eureka Server:

~~~yaml
eureka:
  server:
    eviction-interval-timer-in-ms: 60000
~~~

Nếu có nhiều Eureka Server, hãy bảo đảm cấu hình và khả năng kết nối giữa các peer phù hợp. Một node xóa instance khỏi registry cục bộ nhưng việc cập nhật các peer hoặc cache ở client vẫn cần thời gian để hoàn tất.

### 5.1. Chọn khoảng heartbeat và lease

Khi điều chỉnh, cần cân bằng giữa tốc độ phát hiện instance lỗi và khả năng chịu được trễ mạng:

- Heartbeat quá dày làm tăng số request định kỳ đến Eureka Server, nhất là khi có nhiều instance.
- Heartbeat quá thưa làm registry nhận tín hiệu liveness chậm hơn.
- Lease quá ngắn có thể khiến instance khỏe mạnh bị xem là hết hạn khi JVM tạm dừng lâu, CPU quá tải hoặc mạng chập chờn.
- Lease quá dài khiến instance đã chết có thể còn xuất hiện trong registry lâu hơn.

Một quy tắc thực hành là lease duration nên lớn hơn nhiều lần heartbeat interval để có khoảng đệm cho các lần heartbeat trễ hoặc thất bại tạm thời. Cấu hình mặc định thường gặp 90 giây và 30 giây thể hiện tỷ lệ 3:1. Đây là điểm khởi đầu, không phải tỷ lệ phù hợp cho mọi hệ thống.

Ví dụ, với ứng dụng có thời gian dừng GC dài hoặc chạy qua mạng có độ trễ biến động, lease 90 giây có thể quá ngắn. Ngược lại, một hệ thống yêu cầu loại instance lỗi nhanh cần đánh giá cẩn thận việc giảm lease, vì việc giảm quá mức có thể tạo ra false eviction.

## 6. Self-preservation ảnh hưởng đến eviction như thế nào?

Eureka Server có cơ chế **self-preservation** để hạn chế xóa instance hàng loạt khi số heartbeat nhận được thấp bất thường. Một đợt mất mạng có thể khiến nhiều instance khỏe mạnh đồng thời không gửi được heartbeat. Nếu server xóa tất cả các lease hết hạn ngay lúc đó, registry có thể mất hàng loạt instance vẫn đang chạy.

Khi self-preservation được kích hoạt, Eureka có thể tạm ngừng eviction để bảo toàn registry. Điều này giúp giảm nguy cơ xóa nhầm instance trong sự cố mạng, nhưng cũng có mặt trái: instance thực sự đã chết có thể tiếp tục xuất hiện trong registry lâu hơn.

Một thuộc tính thường gặp để bật/tắt cơ chế này ở server là:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
~~~

Giá trị **true** thường là mặc định trong Eureka Server. Không nên tắt self-preservation chỉ để dashboard loại instance nhanh hơn. Trước khi thay đổi, cần hiểu tỷ lệ heartbeat thực tế, chất lượng mạng, số lượng instance và cách ứng dụng xử lý instance stale.

### 6.1. Ví dụ khi nhiều heartbeat cùng bị mất

Giả sử có 100 instance và mỗi instance gửi heartbeat mỗi 30 giây. Trong điều kiện bình thường, server kỳ vọng nhận xấp xỉ 200 heartbeat mỗi phút. Nếu một sự cố mạng khiến server chỉ nhận được một phần nhỏ số heartbeat đó, server có thể nhận định lượng renewals thấp bất thường và kích hoạt self-preservation.

Trong tình huống này:

- Một số instance có thể thực sự đã dừng.
- Một số instance khác vẫn khỏe nhưng heartbeat không tới được server.
- Nếu xóa tất cả instance quá hạn, server có thể loại nhầm các instance còn sống.
- Self-preservation ưu tiên giữ registry trong giai đoạn bất thường; vì vậy registry có thể chứa dữ liệu cũ.

Con số 200 heartbeat mỗi phút chỉ là phép tính minh họa từ 100 instance nhân với 2 lần mỗi phút. Tỷ lệ renewal thực tế còn phụ thuộc vào số instance đã đăng ký, cấu hình hiệu lực và thời gian quan sát.

## 7. Điều gì xảy ra trong các tình huống vận hành?

### 7.1. Instance dừng có trật tự

Khi ứng dụng shutdown đúng quy trình, Eureka Client có thể gửi yêu cầu cancel để hủy đăng ký. Server nhận cancel sẽ xóa instance khỏi registry và nhân bản thay đổi theo cơ chế của cụm. Cách này giúp tránh phải chờ hết lease.

Tuy nhiên, nếu tiến trình bị kill cưỡng bức, máy ảo bị tắt đột ngột hoặc container mất kết nối trước khi gửi cancel, server không nhận được thông báo shutdown. Khi đó việc phát hiện phụ thuộc vào heartbeat, lease expiration và eviction.

### 7.2. Instance vẫn chạy nhưng mất kết nối đến Eureka

Giả sử payment-service vẫn xử lý request nội bộ nhưng không thể kết nối đến Eureka Server. Client không gia hạn được lease. Khi lease hết hạn và server thực hiện eviction, instance có thể bị xóa khỏi registry dù tiến trình vẫn đang chạy.

Đây là một ví dụ về false eviction: registry đánh giá instance không còn khả dụng vì thiếu heartbeat, trong khi tiến trình nghiệp vụ vẫn sống. Khi kết nối được khôi phục, Eureka Client có thể đăng ký lại instance; thời gian để các peer và client khác nhìn thấy instance phụ thuộc vào quá trình cập nhật registry.

### 7.3. Eureka Server bị gián đoạn

Nếu Eureka Server tạm thời dừng, các client không thể gửi heartbeat đến node đó. Trong cụm nhiều node, client có thể tiếp tục giao tiếp với peer khác nếu được cấu hình nhiều endpoint và mạng vẫn cho phép kết nối. Registry giữa các node có thể tạm thời khác nhau.

Khi server khôi phục, cần theo dõi quá trình kết nối peer, đăng ký lại và cập nhật registry. Không nên giả định rằng mọi cache của client được cập nhật ngay khi server vừa khởi động xong.

### 7.4. JVM pause hoặc máy chủ quá tải

Một JVM pause dài, stop-the-world GC, thiếu CPU hoặc thread pool bị nghẽn có thể làm heartbeat gửi trễ. Nếu lease được cấu hình quá sát heartbeat interval, server có thể xem instance là hết hạn dù tiến trình sẽ tiếp tục hoạt động sau khi pause kết thúc.

Vì vậy, khi điều tra instance bị eviction bất thường, cần xem cả log GC, CPU, thread, network và log Eureka. Chỉ tăng lease mà không tìm nguyên nhân nghẽn có thể che khuất vấn đề hiệu năng thật.

## 8. Theo dõi heartbeat và chẩn đoán lease hết hạn

Khi instance biến mất khỏi registry, hãy xác định nó bị cancel có chủ đích hay bị eviction do thiếu heartbeat. Một quy trình kiểm tra thực tế có thể gồm:

1. Kiểm tra log của ứng dụng để tìm lỗi kết nối Eureka, timeout hoặc lỗi gửi heartbeat.
2. Kiểm tra log Eureka Server để tìm thông tin renew, lease expiration, eviction và self-preservation.
3. So sánh thời điểm heartbeat cuối cùng với lease duration hiệu lực.
4. Kiểm tra chu kỳ eviction và xem self-preservation có đang ngăn eviction hay không.
5. Kiểm tra GC pause, CPU, thread pool, DNS, firewall và độ trễ mạng ở cả client lẫn server.
6. Đối chiếu registry trên các Eureka Server và cache phía client để phân biệt lỗi đăng ký với độ trễ cập nhật.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Instance biến mất khi ứng dụng vẫn chạy | Heartbeat bị trễ hoặc mất kết nối | Log client, mạng, GC, lease duration |
| Instance chết nhưng vẫn xuất hiện lâu | Lease dài, eviction chạy chậm hoặc self-preservation | Log server, eviction interval, renewal rate |
| Nhiều instance cùng bị stale | Sự cố mạng hoặc Eureka Server quá tải | Kết nối peer, heartbeat tổng thể, CPU và thread |
| Instance xuất hiện lại sau một thời gian | Client kết nối lại và đăng ký lại | Log register/renew và thời điểm phục hồi mạng |
| Các node hiển thị số instance khác nhau | Replication hoặc cache chưa hội tụ | Log peer, registry từng node, thời gian fetch cache |

Dashboard hữu ích để quan sát registry nhưng không thay thế log và metric. Hãy kiểm tra từ nhiều node và từ phía client để xác định trạng thái mà ứng dụng thực sự sử dụng.

## 9. Các lỗi cấu hình thường gặp

### 9.1. Đặt lease nhỏ hơn hoặc quá sát heartbeat interval

Nếu lease chỉ vừa bằng heartbeat interval, một request trễ có thể khiến lease hết hạn trước khi lần renew tiếp theo đến server. Hãy dành khoảng đệm đủ lớn cho độ trễ mạng, lịch chạy thread và thời gian pause của JVM.

### 9.2. Chỉ tăng lease để che lỗi heartbeat

Lease dài giúp giảm false eviction nhưng cũng kéo dài thời gian instance chết còn nằm trong registry. Nếu heartbeat thất bại do DNS, firewall hoặc server quá tải, cần sửa nguyên nhân gốc thay vì chỉ tăng thời hạn.

### 9.3. Nhầm eviction interval với lease duration

Lease duration là thời gian chờ kể từ lần renew cuối. Eviction interval là chu kỳ server kiểm tra các lease hết hạn. Hai thông số điều khiển hai bước khác nhau; thay đổi một thông số không thay thế được thông số còn lại.

### 9.4. Tắt self-preservation trong môi trường thật

Tắt self-preservation có thể khiến server xóa instance nhanh hơn khi heartbeat giảm, nhưng trong network partition có thể xóa nhầm nhiều instance còn hoạt động. Chỉ thay đổi cơ chế này khi đã đánh giá rõ rủi ro và có hệ thống health check, quan sát cùng chính sách phục hồi phù hợp.

### 9.5. Cho rằng instance bị xóa là mọi client lập tức biết

Eureka Client có thể giữ registry cache và làm mới theo chu kỳ. Sau khi server eviction, một client khác vẫn có thể thấy instance cũ trong một khoảng thời gian. Ứng dụng gọi dịch vụ vẫn cần timeout, retry có giới hạn và xử lý lỗi kết nối.

## 10. Ví dụ lựa chọn cấu hình theo mục tiêu

Không có một bộ giá trị phù hợp cho mọi hệ thống. Bảng sau mô tả cách suy nghĩ khi điều chỉnh:

| Mục tiêu | Hướng điều chỉnh | Đánh đổi cần chấp nhận |
|---|---|---|
| Giảm tải heartbeat khi có rất nhiều instance | Tăng heartbeat interval | Phát hiện instance lỗi chậm hơn |
| Phát hiện lỗi nhanh hơn | Giảm lease duration và đánh giá lại eviction interval | Dễ false eviction khi mạng hoặc JVM bị trễ |
| Chịu được mạng không ổn định | Tăng khoảng đệm lease và giữ self-preservation | Instance chết có thể tồn tại trong registry lâu hơn |
| Tránh stale registry sau khi mất mạng | Theo dõi peer, cache, renewal và health check | Cần thêm metric và quy trình vận hành |

Ví dụ, một hệ thống nội bộ có mạng ổn định và số instance vừa phải có thể bắt đầu với heartbeat 30 giây và lease 90 giây. Một hệ thống chạy qua nhiều vùng mạng cần đo độ trễ thực tế, thời gian pause của JVM và tỷ lệ heartbeat bị trễ trước khi chọn lease. Sau khi thay đổi, hãy thử nghiệm bằng cách dừng một instance, chặn kết nối đến Eureka trong thời gian ngắn và khôi phục mạng để quan sát toàn bộ vòng đời.

## 11. Tổng kết

Heartbeat là nhịp báo sống mà Eureka Client gửi để gia hạn lease. Lease xác định thời gian server chờ sau lần gia hạn cuối trước khi đăng ký có thể hết hạn. Với cấu hình phổ biến, heartbeat mặc định thường là 30 giây và lease duration thường là 90 giây.

Lease expiration, eviction và việc các client nhìn thấy registry mới là những mốc khác nhau. Tác vụ eviction chạy định kỳ, self-preservation có thể trì hoãn việc xóa và cache phía client có thể cập nhật sau đó. Khi điều chỉnh heartbeat hoặc lease, cần cân bằng giữa tốc độ phát hiện lỗi, tải lên Eureka và khả năng chịu được trễ mạng hoặc JVM pause. Theo dõi renewals, log expiration, eviction và self-preservation giúp phân biệt instance đã chết với instance khỏe mạnh nhưng tạm thời không gửi được heartbeat.
