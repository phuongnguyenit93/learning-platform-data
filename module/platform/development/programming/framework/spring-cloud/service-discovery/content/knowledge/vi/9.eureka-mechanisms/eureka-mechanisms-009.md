# Điều chỉnh chu kỳ cập nhật trong thử nghiệm và đánh đổi vận hành

Eureka trao đổi thông tin đăng ký và danh sách instance theo nhiều chu kỳ độc lập. Client gửi heartbeat để gia hạn lease, client định kỳ tải registry về cache cục bộ, server cập nhật response cache và chạy tác vụ loại bỏ lease hết hạn. Vì vậy, thay đổi một chu kỳ không làm toàn bộ hệ thống cập nhật ngay lập tức.

Trong môi trường thử nghiệm, có thể rút ngắn một số chu kỳ để quan sát đăng ký, phát hiện instance mất kết nối và cập nhật danh sách dịch vụ nhanh hơn. Trong production, chu kỳ quá ngắn làm tăng request, tải xử lý, lưu lượng mạng và nguy cơ loại nhầm instance khi mạng chập chờn. Cần hiểu mỗi bộ định thời làm nhiệm vụ gì trước khi điều chỉnh.

## 1. Những chu kỳ chính trong Eureka

Một Eureka Client vừa đăng ký chính nó, vừa tải registry của các service khác. Hai luồng này có nhịp cập nhật khác nhau.

| Cơ chế | Thuộc tính Spring Cloud | Mặc định thường dùng | Ý nghĩa |
|---|---|---:|---|
| Heartbeat/lease renewal | eureka.instance.lease-renewal-interval-in-seconds | 30 giây | Client gửi heartbeat để báo instance vẫn hoạt động |
| Lease expiration | eureka.instance.lease-expiration-duration-in-seconds | 90 giây | Khoảng thời gian server chờ heartbeat trước khi lease có thể hết hạn |
| Registry fetch | eureka.client.registry-fetch-interval-seconds | 30 giây | Client tải delta registry và cập nhật cache cục bộ |
| Instance info replication | eureka.client.instance-info-replication-interval-seconds | 30 giây | Nhịp gửi thay đổi metadata/trạng thái instance lên server |
| Initial instance info replication | eureka.client.initial-instance-info-replication-interval-seconds | 40 giây | Độ trễ ban đầu trước khi lặp gửi thông tin instance |
| Server response cache update | eureka.server.response-cache-update-interval-ms | 30.000 ms | Nhịp làm mới response cache phía server |
| Expected client renewal | eureka.server.expected-client-renewal-interval-seconds | 30 giây | Chu kỳ heartbeat server giả định khi tính ngưỡng renewal |
| Eviction scan | eureka.server.eviction-interval-timer-in-ms | Do server cấu hình | Nhịp server quét lease hết hạn để xem xét eviction |

Các giá trị trên là mặc định được công bố trong tài liệu cấu hình Spring Cloud Netflix hiện hành, trừ eviction scan không có giá trị mặc định được khai báo trong bảng thuộc tính. Hãy kiểm tra đúng phiên bản Spring Cloud Netflix của dự án vì tên, giá trị mặc định hoặc khả năng thay đổi runtime có thể khác nhau giữa các phiên bản.

Không nhầm eureka.client.eureka-service-url-poll-interval-seconds với registry fetch. Thuộc tính này mặc định là 300 giây và dùng để poll thay đổi danh sách URL Eureka Server, ví dụ khi danh sách server được lấy từ DNS. Nó không phải chu kỳ tải danh sách service instance.

## 2. Heartbeat và lease renewal

Khi instance đăng ký với Eureka, client định kỳ gửi heartbeat đến server. Mặc định, client gửi heartbeat khoảng mỗi 30 giây. Server gia hạn lease khi nhận được heartbeat hợp lệ.

Thuộc tính phía client:

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 30

Heartbeat trả lời câu hỏi: server có còn nhận được tín hiệu sống từ instance hay không? Nó không chứng minh mọi dependency nghiệp vụ đều khỏe. Nếu cần trạng thái ứng dụng ảnh hưởng Eureka, phải cấu hình health check integration riêng.

Lease renewal interval quá dài làm server phát hiện instance mất kết nối chậm hơn. Interval quá ngắn làm tăng số heartbeat và tải xử lý ở server, đồng thời làm tăng số lần giao tiếp trong cụm. Spring Cloud Netflix khuyến nghị giữ mặc định trong production vì các phép tính nội bộ phía server giả định chu kỳ renewal tiêu chuẩn.

## 3. Lease expiration và phát hiện instance mất kết nối

Lease expiration xác định server chờ bao lâu kể từ heartbeat cuối cùng trước khi lease có thể hết hạn. Mặc định thường là 90 giây:

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90

Expiration duration phải lớn hơn renewal interval. Nếu expiration quá gần renewal interval, một lần trễ mạng, pause JVM hoặc tải CPU tăng đột biến có thể khiến instance khỏe bị coi là mất kết nối.

Ví dụ, nếu heartbeat được gửi mỗi 5 giây nhưng lease hết hạn sau 6 giây, chỉ một heartbeat đến chậm hơn dự kiến cũng có thể làm lease hết hạn. Một khoảng dự phòng rộng hơn giúp hệ thống chịu được jitter và sự cố mạng ngắn.

Cần phân biệt lease expiration với eviction scan. Lease có thể đã hết hạn theo thời gian, nhưng server chỉ xử lý loại bỏ khi tác vụ eviction chạy và khi chính sách self-preservation cho phép. Vì vậy, thời gian một instance biến mất khỏi registry không chỉ bằng expiration duration.

## 4. Registry fetch và cache phía client

Eureka Client không gọi server để tra cứu từng request nghiệp vụ. Client tải registry và lưu cache cục bộ; các lần tra cứu sau đó sử dụng dữ liệu đã cache.

Chu kỳ fetch được điều khiển bởi:

    eureka:
      client:
        registry-fetch-interval-seconds: 30

Mặc định, client làm mới registry khoảng mỗi 30 giây. Eureka thường dùng delta để chỉ tải các thay đổi kể từ lần fetch trước, giúp giảm lưu lượng so với tải toàn bộ registry mỗi lần. Client đối chiếu kết quả delta và có thể tải lại toàn bộ registry nếu phát hiện sai lệch.

Giảm registry-fetch-interval-seconds có thể giúp consumer nhìn thấy instance mới hoặc thay đổi trạng thái sớm hơn. Đổi lại, mỗi client sẽ tạo request thường xuyên hơn tới Eureka Server. Với số lượng client lớn, interval quá nhỏ có thể tạo tải đáng kể, đặc biệt nếu tắt delta và liên tục tải toàn bộ registry.

Cần nhớ rằng cache của Eureka Client và cache của Spring Cloud LoadBalancer là hai lớp khác nhau. Ngay cả khi Eureka Client đã có registry mới, cache ở tầng gọi dịch vụ có thể vẫn giữ danh sách instance trong một khoảng thời gian tùy cấu hình. Nếu muốn kiểm soát độ trễ đầu cuối, cần quan sát cả hai lớp.

## 5. Response cache và tác vụ eviction phía server

Eureka Server sử dụng response cache để phục vụ các request registry. Thuộc tính response-cache-update-interval-ms điều khiển nhịp cập nhật response cache; mặc định thường là 30.000 ms:

    eureka:
      server:
        response-cache-update-interval-ms: 30000

Khi server nhận đăng ký mới hoặc thay đổi trạng thái, response mà client đọc có thể chưa phản ánh ngay nếu còn phụ thuộc cache. Client lại chỉ đọc registry theo chu kỳ fetch của chính nó. Do đó, thời điểm một consumer nhìn thấy thay đổi có thể chịu ảnh hưởng của cả server response cache lẫn client fetch interval.

Tác vụ eviction được điều khiển bằng:

    eureka:
      server:
        eviction-interval-timer-in-ms: 60000

Đây là ví dụ đặt chu kỳ quét 60 giây, không khẳng định mọi phiên bản có cùng mặc định. Tác vụ này kiểm tra các lease hết hạn và loại bỏ instance khi được phép. Nếu giảm chu kỳ quét trong thử nghiệm, instance hết hạn có thể được xử lý sớm hơn; đổi lại server thực hiện công việc định kỳ thường xuyên hơn.

## 6. Self-preservation và ngưỡng renewal

Eureka có cơ chế self-preservation để tránh xóa hàng loạt instance khi server nhận ít heartbeat hơn dự kiến. Tình trạng thiếu heartbeat có thể do nhiều instance thực sự chết, nhưng cũng có thể do một sự cố mạng diện rộng khiến server tạm thời không nhận được heartbeat.

Self-preservation được bật mặc định trong cấu hình Spring Cloud Netflix. Ngưỡng renewal mặc định thường là 0,85 (85%). Server dùng số heartbeat nhận được so với số dự kiến để quyết định có nên tạm dừng eviction hay không.

Một số thuộc tính liên quan:

    eureka:
      server:
        enable-self-preservation: true
        renewal-percent-threshold: 0.85
        expected-client-renewal-interval-seconds: 30

Khi giảm lease-renewal-interval-in-seconds ở client, phải điều chỉnh expected-client-renewal-interval-seconds ở server cho khớp với nhịp heartbeat thực tế. Nếu client gửi mỗi 5 giây nhưng server vẫn tính ngưỡng theo 30 giây, số heartbeat dự kiến và số thực tế có thể lệch nhau, làm self-preservation hoạt động ngoài dự kiến.

Không nên tắt self-preservation chỉ để ép registry xóa instance trong production. Khi server nghi ngờ có sự cố mạng, self-preservation bảo vệ dữ liệu registry khỏi bị xóa hàng loạt. Trong bài thử nghiệm cô lập, có thể khảo sát hành vi này có kiểm soát, nhưng cần ghi rõ cấu hình thử nghiệm và khôi phục chính sách phù hợp trước khi triển khai thật.

## 7. Cấu hình rút ngắn chu kỳ cho môi trường thử nghiệm

Ví dụ sau rút ngắn các chu kỳ để dễ quan sát vòng đời instance trong một môi trường local hoặc integration test. Cần đặt cấu hình client và server ở đúng ứng dụng tương ứng.

**Trên Eureka Client**

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 5
        lease-expiration-duration-in-seconds: 15
      client:
        registry-fetch-interval-seconds: 5
        instance-info-replication-interval-seconds: 5

**Trên Eureka Server**

    eureka:
      server:
        expected-client-renewal-interval-seconds: 5
        response-cache-update-interval-ms: 5000
        eviction-interval-timer-in-ms: 5000
        enable-self-preservation: true

Trong ví dụ:

- Client gửi heartbeat mỗi 5 giây.
- Lease expiration là 15 giây, lớn hơn renewal interval và có khoảng dự phòng.
- Consumer fetch registry mỗi 5 giây.
- Server giả định heartbeat client mỗi 5 giây khi tính renewal threshold.
- Response cache và eviction scan được đặt ở mức 5 giây để dễ quan sát trong bài thực hành.

Đây là cấu hình minh họa cho thử nghiệm, không phải khuyến nghị production. Nếu có nhiều client chạy đồng thời, cần đánh giá tải server và số request phát sinh. Self-preservation vẫn được bật; nếu số client quá ít hoặc heartbeat không ổn định, cần đọc log và trạng thái self-preservation trước khi kết luận eviction bị lỗi.

## 8. Đánh đổi giữa tốc độ cập nhật và tải hệ thống

Giảm chu kỳ có lợi cho tốc độ quan sát nhưng làm tăng hoạt động định kỳ của toàn hệ thống.

| Điều chỉnh | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Giảm heartbeat interval | Server nhận tín hiệu sống thường xuyên hơn | Tăng heartbeat traffic; server tính renewal threshold phải được đồng bộ |
| Giảm lease expiration | Phát hiện instance mất kết nối nhanh hơn | Dễ loại nhầm instance khi mạng chập chờn hoặc JVM pause |
| Giảm registry fetch interval | Consumer cập nhật cache sớm hơn | Tăng request và xử lý registry ở server |
| Giảm response cache update interval | Thay đổi registry có thể xuất hiện trong response sớm hơn | Tăng công việc cập nhật cache |
| Giảm eviction interval | Xử lý lease hết hạn sớm hơn sau khi đủ điều kiện | Tăng số lần quét registry |
| Tắt delta fetch | Dễ quan sát full registry trong một số bài test | Tăng tải và lưu lượng so với delta |

Nếu có N client và mỗi client gửi heartbeat mỗi T giây, lượng heartbeat trung bình xấp xỉ N/T request mỗi giây, chưa tính retry, replication và request registry fetch. Ví dụ 300 client gửi mỗi 30 giây tạo khoảng 10 heartbeat/giây; nếu giảm xuống 5 giây, con số tăng lên khoảng 60 heartbeat/giây. Đây chỉ là ước lượng trung bình để thấy tác động của chu kỳ, không phải dự báo tải hoàn chỉnh.

Đối với registry fetch, mỗi client cũng tạo request định kỳ. Khi có hàng nghìn client, giảm interval từ 30 giây xuống 5 giây làm tần suất fetch tăng khoảng sáu lần. Delta giúp giảm lượng dữ liệu truyền trong mỗi lần fetch nhưng không loại bỏ chi phí request, xác thực, xử lý và cập nhật cache.

## 9. Ước lượng độ trễ cập nhật đầu cuối

Không có một con số duy nhất cho thời gian từ lúc instance thay đổi đến khi mọi consumer nhìn thấy thay đổi. Độ trễ phụ thuộc vào:

1. Thời điểm heartbeat hoặc thay đổi registration được server nhận.
2. Thời điểm response cache của server được cập nhật.
3. Chu kỳ fetch tiếp theo của từng client.
4. Cache bổ sung ở DiscoveryClient hoặc LoadBalancer.
5. Peer replication nếu triển khai nhiều Eureka Server.
6. Tác vụ eviction và trạng thái self-preservation nếu instance cần bị loại do lease hết hạn.

Tài liệu Spring Cloud Netflix lưu ý service có thể cần tới khoảng ba heartbeat để instance, server và client đồng bộ metadata trong cache ở kịch bản đăng ký. Đây là mô tả thực tế của quá trình đồng bộ, không phải cam kết thời gian cố định cho mọi cấu hình.

Sơ đồ khái quát:

    Instance
       |
       | heartbeat / registration update
       v
    Eureka Server registry
       |
       | response cache refresh
       v
    Eureka Client fetch
       |
       | local registry cache
       v
    DiscoveryClient / LoadBalancer
       |
       v
    Request tới instance được chọn

Để đo độ trễ thực tế, ghi timestamp ở thời điểm instance khởi động hoặc đổi trạng thái, thời điểm Dashboard hiển thị thay đổi và thời điểm consumer lần đầu nhận danh sách mới. Lặp lại nhiều lần trong điều kiện tải khác nhau để thấy phân bố độ trễ thay vì dựa vào một lần chạy.

## 10. Quy trình thử nghiệm có kiểm soát

Có thể dùng quy trình sau để so sánh cấu hình mặc định và cấu hình rút ngắn:

1. Khởi động Eureka Server và hai instance của một service.
2. Khởi động một consumer và ghi nhận thời điểm consumer nhìn thấy cả hai instance.
3. Giữ nguyên cấu hình mặc định, dừng một instance theo cách graceful và quan sát thời gian registry cập nhật.
4. Chạy lại thử nghiệm với client heartbeat, lease expiration, registry fetch và server cache được rút ngắn đồng bộ.
5. Thử ngắt mạng đột ngột thay vì graceful shutdown để quan sát lease expiration và self-preservation.
6. Khởi động lại instance, đo thời gian đăng ký và thời điểm consumer nhìn thấy instance.
7. Tăng số client để quan sát ảnh hưởng của chu kỳ tới CPU, request rate và log của Eureka Server.
8. Khôi phục cấu hình mặc định hoặc cấu hình production đã được đánh giá sau khi hoàn tất thử nghiệm.

Nên giữ mỗi lần thử chỉ thay đổi một nhóm chu kỳ. Nếu đồng thời thay đổi heartbeat, lease expiration, registry fetch và server cache mà không ghi lại cấu hình, sẽ khó xác định yếu tố nào tạo ra khác biệt.

## 11. Chẩn đoán khi chu kỳ không tạo ra kết quả mong đợi

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Client gửi heartbeat nhanh nhưng instance vẫn mất khỏi registry | Lease expiration quá ngắn, server không nhận được heartbeat hoặc server/client lệch cấu hình |
| Instance đã đăng ký nhưng consumer thấy chậm | Response cache, registry fetch interval, peer replication hoặc LoadBalancer cache |
| Instance đã dừng nhưng vẫn còn trong Dashboard | Lease chưa hết hạn, eviction chưa chạy hoặc self-preservation đang tạm dừng eviction |
| Consumer không cập nhật dù server đã có trạng thái mới | Registry fetch chưa tới chu kỳ tiếp theo hoặc cache ở tầng LoadBalancer |
| Server bật self-preservation thường xuyên | Expected renewal interval không khớp, thiếu heartbeat, mạng lỗi hoặc số client thay đổi mạnh |
| Tải Eureka Server tăng sau khi tinh chỉnh | Heartbeat/fetch/cache/eviction interval quá ngắn hoặc delta bị tắt |

Các bước kiểm tra:

- Đọc log Eureka Client để xác nhận heartbeat và registry fetch có chạy theo chu kỳ mong muốn.
- Đọc log Eureka Server để xác nhận heartbeat nhận được, lease expiration và eviction.
- Kiểm tra các giá trị cấu hình hiệu lực ở đúng tiến trình client hoặc server; không chỉ kiểm tra file YAML trên đĩa.
- Kiểm tra trạng thái self-preservation và renewal threshold khi instance hết hạn nhưng chưa bị xóa.
- Kiểm tra cache của consumer và LoadBalancer nếu Dashboard đã cập nhật nhưng request vẫn tới instance cũ.
- Kiểm tra cấu hình có thực sự được áp dụng runtime hay cần khởi động lại ứng dụng. Không phải mọi thuộc tính Eureka đều tự động có hiệu lực ngay khi thay đổi file cấu hình.

## 12. Khuyến nghị khi triển khai production

Trong production, ưu tiên tính ổn định và khả năng chịu lỗi mạng hơn tốc độ cập nhật ngắn nhất:

- Giữ heartbeat renewal mặc định 30 giây trừ khi có số liệu và lý do vận hành rõ ràng.
- Giữ lease expiration đủ lớn so với heartbeat interval để chịu được jitter, GC pause và sự cố mạng ngắn.
- Không giảm registry fetch interval đồng loạt cho hàng nghìn client nếu chưa đo tải server.
- Giữ self-preservation và theo dõi renewal threshold; không dùng việc tắt self-preservation như giải pháp chữa cháy mặc định.
- Dùng graceful shutdown để client deregister đúng cách khi instance kết thúc bình thường.
- Đo cache và propagation delay ở cả server, client và LoadBalancer.
- Kiểm thử tình huống mạng phân vùng, server restart, client restart và scale-out/scale-in trước khi chốt thông số.

Điều chỉnh chu kỳ chỉ cải thiện một phần độ trễ phát hiện và đồng bộ. Nó không thay thế retry có giới hạn, timeout request, circuit breaker, graceful shutdown hoặc khả năng xử lý dữ liệu registry cũ ở consumer.

## 13. Kết luận

Eureka có nhiều chu kỳ độc lập: heartbeat và lease, registry fetch, instance info replication, response cache và eviction. Trong thử nghiệm, có thể giảm các chu kỳ liên quan một cách đồng bộ để quan sát nhanh hơn, nhưng phải giữ lease expiration lớn hơn heartbeat interval và đồng bộ expected-client-renewal-interval-seconds ở server.

Trong production, chu kỳ ngắn làm tăng tải và có thể khiến instance khỏe bị loại nhầm khi mạng hoặc JVM bị gián đoạn. Hãy bắt đầu từ mặc định, đo độ trễ cập nhật đầu cuối, kiểm tra self-preservation và cache ở mọi tầng, sau đó chỉ thay đổi tham số có tác động đã được xác định.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Why Is It so Slow to Register a Service?](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Understanding Eureka Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka — Server Self Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)

