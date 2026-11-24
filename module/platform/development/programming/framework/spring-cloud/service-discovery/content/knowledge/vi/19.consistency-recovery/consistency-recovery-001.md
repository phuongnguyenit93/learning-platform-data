# Đánh đổi giữa độ mới danh sách, tính sẵn sàng và chi phí đồng bộ

Service discovery giúp consumer tìm địa chỉ instance theo service ID, nhưng danh sách instance không phải lúc nào cũng phản ánh tức thời trạng thái mới nhất. Khi một instance vừa đăng ký, bị lỗi, chuyển trạng thái hoặc bị hủy đăng ký, thay đổi phải đi qua registry, response cache, client cache và có thể cả cache của LoadBalancer trước khi mọi consumer nhìn thấy kết quả.

Thiết kế discovery vì vậy phải cân bằng ba mục tiêu: độ mới của danh sách (freshness), khả năng tiếp tục tra cứu khi registry hoặc mạng gặp sự cố (availability) và chi phí để đồng bộ thay đổi (synchronization cost). Tối ưu một mục tiêu thường làm thay đổi hai mục tiêu còn lại. Bài này phân tích cách Eureka và Consul xử lý sự cân bằng đó, cách chọn chính sách theo loại request và cách đo độ trễ cập nhật trong hệ thống Spring Cloud.

## 1. Ba mục tiêu cần cân bằng

**Độ mới của danh sách** cho biết dữ liệu mà consumer đang dùng gần với trạng thái registry hiện tại đến đâu. Nếu một instance vừa bị loại khỏi pool nhưng consumer vẫn thấy bản ghi cũ, danh sách đó đã stale. Nếu instance mới đã đăng ký nhưng consumer chưa thấy, danh sách cũng chưa phản ánh topology mới.

**Tính sẵn sàng của discovery** cho biết consumer có thể tiếp tục lấy danh sách instance khi registry, leader hoặc đường mạng tới registry gặp sự cố hay không. Một client có cache cục bộ có thể tiếp tục tra cứu từ dữ liệu cũ trong lúc registry tạm thời không truy cập được. Điều này giữ khả năng phục vụ nhưng chấp nhận rủi ro chọn instance đã thay đổi trạng thái.

**Chi phí đồng bộ** gồm request polling, heartbeat, replication, blocking query, serialize/deserialize, cập nhật cache, network bandwidth và CPU. Cập nhật càng thường xuyên hoặc yêu cầu xác nhận mạnh hơn thì hệ thống càng phải xử lý nhiều hoạt động đồng bộ.

| Mục tiêu | Tăng cường bằng cách | Đánh đổi thường gặp |
|---|---|---|
| Freshness cao | Fetch/watch thường xuyên, cache ngắn, đọc nhất quán mạnh | Tăng request, CPU, network và độ trễ khi phải chờ quorum |
| Availability cao | Dùng cache cục bộ, cho phép stale read, tiếp tục phục vụ khi registry gián đoạn | Consumer có thể nhận địa chỉ cũ |
| Chi phí thấp | Poll ít hơn, cache lâu hơn, gom thay đổi, dùng delta/blocking query | Thay đổi lan truyền chậm hơn hoặc consumer nhìn thấy dữ liệu cũ lâu hơn |

Không có một cấu hình tối ưu cho mọi service. API thanh toán, service tra cứu danh mục, worker nền và gateway có thể cần ngân sách độ mới khác nhau.

## 2. Độ mới không đồng nghĩa với tính nhất quán

Cần phân biệt một số khái niệm:

- **Freshness:** dữ liệu có mới so với thay đổi gần nhất hay không.
- **Consistency:** các lần đọc ở những node hoặc consumer khác nhau có quan sát trạng thái tương thích với nhau hay không.
- **Availability:** yêu cầu tra cứu có nhận được phản hồi trong điều kiện lỗi hay không.
- **Propagation delay:** thời gian từ khi thay đổi được chấp nhận tại registry tới khi consumer nhìn thấy thay đổi.
- **Cache age:** thời gian kể từ lần cache được cập nhật gần nhất.

Một consumer có thể nhận được response nhanh và nhất quán với cache cục bộ của nó, nhưng cache đó đã cũ so với registry. Ngược lại, một truy vấn tới leader có thể đọc trạng thái mới nhất nhưng phải chờ thêm một round-trip hoặc không trả lời được khi không có quorum.

Đối với service discovery, consistency không phải lúc nào cũng có nghĩa mọi consumer phải nhìn thấy cùng một danh sách ở cùng một thời điểm. Nhiều hệ thống chấp nhận eventual consistency: thay đổi được lan truyền dần và các bản sao cuối cùng hội tụ nếu hệ thống ổn định.

## 3. CAP và service discovery trong thực tế

CAP mô tả đánh đổi khi xảy ra network partition: một hệ thống phân tán phải lựa chọn giữa việc tiếp tục trả lời yêu cầu ở mọi phía và bảo đảm các lần đọc không trả dữ liệu mâu thuẫn. Trong vận hành, điều quan trọng là hiểu hành vi cụ thể của registry và client thay vì gắn nhãn toàn bộ sản phẩm là CP hoặc AP.

Service discovery có một đặc điểm riêng: consumer thường có thể dùng cache để tiếp tục gửi request trong lúc registry không truy cập được. Khả năng phục vụ đó đến từ dữ liệu đã được lấy trước, không chứng minh registry đang có trạng thái mới nhất.

Ví dụ khi mạng giữa consumer và registry bị đứt:

1. Consumer đã cache hai instance của inventory-service.
2. Một instance thực tế bị dừng trong thời gian phân vùng.
3. Consumer không thể refresh danh sách nhưng vẫn có cache cũ.
4. Nếu consumer tiếp tục dùng cache, request có thể vẫn được gửi tới instance đã dừng.
5. Nếu consumer từ chối dùng cache và yêu cầu tra cứu mới, request có thể thất bại ngay vì registry không truy cập được.

Đây là quyết định chính sách ở tầng ứng dụng: tiếp tục phục vụ với danh sách có thể cũ hay dừng tra cứu để tránh dùng dữ liệu chưa được xác nhận.

## 4. Eventual consistency và vòng đời của một thay đổi

Một thay đổi registration thường đi qua nhiều bước:

    Instance
       |
       | register / status change / deregister
       v
    Registry leader hoặc local agent
       |
       | replicate / catalog update
       v
    Registry response hoặc query result
       |
       | fetch / watch / DNS query
       v
    DiscoveryClient cache
       |
       | refresh / list supplier
       v
    Spring Cloud LoadBalancer
       |
       v
    Consumer chọn instance

Mỗi bước có thể thêm độ trễ. Ví dụ, instance đã deregister tại registry nhưng Eureka client của consumer chưa fetch delta mới; hoặc Consul Catalog đã cập nhật nhưng consumer đang dùng kết quả cache cũ.

Vì vậy, khi đo propagation delay, hãy ghi nhận ít nhất hai mốc: thời điểm registry chấp nhận thay đổi và thời điểm consumer đầu tiên quan sát thấy thay đổi. Nếu cần đánh giá định tuyến thực tế, ghi thêm thời điểm LoadBalancer ngừng chọn instance cũ.

## 5. Eureka: cache cục bộ và delta fetch

Eureka Client tải registry từ Eureka Server rồi giữ bản cache cục bộ. Các lần tra cứu dịch vụ thường sử dụng cache này thay vì gọi server cho từng request nghiệp vụ.

Các thuộc tính phổ biến:

    eureka:
      client:
        registry-fetch-interval-seconds: 30
        disable-delta: false
        fetch-registry: true

registry-fetch-interval-seconds điều khiển chu kỳ fetch. Giá trị mặc định thường là 30 giây. disable-delta=false cho phép client lấy các thay đổi kể từ lần fetch trước thay vì tải toàn bộ registry ở mỗi lần cập nhật.

Delta giúp giảm lượng dữ liệu truyền khi số thay đổi thấp hơn nhiều so với số lần fetch. Client đối chiếu delta và có thể tải lại toàn bộ registry nếu phát hiện sai lệch khi reconcile.

Điều này tạo ra một đánh đổi:

- Fetch interval ngắn hơn có thể giúp consumer thấy thay đổi sớm hơn.
- Fetch interval dài hơn giảm số request tới Eureka Server nhưng kéo dài thời gian cache có thể cũ.
- Tắt delta làm client tải nhiều dữ liệu hơn, đặc biệt khi registry lớn.
- Cache cục bộ cho phép consumer tiếp tục tra cứu khi Eureka Server tạm thời không truy cập được, nhưng dữ liệu có thể stale.

Tài liệu Netflix mô tả client fetch delta định kỳ và lưu registry cục bộ; thời gian lan truyền có thể kéo dài tới khoảng hai phút trong cấu hình và tình huống được mô tả. Đây không phải SLA cố định cho mọi phiên bản hoặc mọi topology. Hãy đo hệ thống đang triển khai.

## 6. Eureka và khả năng phục vụ khi registry lỗi

Nếu Eureka Server tạm thời không truy cập được sau khi client đã tải registry, ứng dụng thường vẫn có dữ liệu cache để tra cứu. Điều này tăng khả năng tiếp tục gọi service trong sự cố ngắn, nhưng consumer có thể không biết instance nào vừa bị dừng hoặc mới được thêm.

Nếu client khởi động lần đầu khi không thể tải registry, nó chưa có cache đầy đủ. Một số cấu hình có thể dùng backup registry cho lần khởi động đầu tiên; không nên giả định mọi ứng dụng đều có dữ liệu dự phòng.

Eureka Server còn có self-preservation để hạn chế eviction hàng loạt khi heartbeat thấp hơn kỳ vọng. Trong network partition, server có thể giữ lại instance đã hết lease thay vì xóa chúng ngay. Cơ chế này ưu tiên bảo vệ registry khỏi việc xóa nhầm hàng loạt khi nguyên nhân có thể là lỗi mạng.

Khi vận hành, theo dõi:

- Registry fetch success/failure và thời gian fetch.
- Số lần delta fetch và full reconciliation.
- Tuổi cache gần nhất.
- Heartbeat renewal và trạng thái self-preservation.
- Số instance trong registry so với số instance thực tế đang chạy.
- Request lỗi do consumer chọn instance không còn hoạt động.

Không tắt self-preservation chỉ để loại instance stale nhanh hơn. Cần cân nhắc rủi ro xóa nhầm nhiều instance khi mạng bị phân vùng.

## 7. Consul: consistency mode của HTTP API

Consul lưu trạng thái registration và health trên các server, dùng consensus để ghi nhận thay đổi. Các follower có thể cần thời gian để nhận trạng thái mới từ leader. Vì vậy, cách một read request được xử lý ảnh hưởng tới độ mới và chi phí đọc.

Consul cung cấp ba consistency mode chính cho các HTTP API read có hỗ trợ:

| Mode | Hành vi | Đánh đổi |
|---|---|---|
| default | Dùng cơ chế mặc định; HTTP API thường đọc mạnh nhất trong hầu hết trường hợp | Nhanh trong điều kiện bình thường, vẫn có cửa sổ hiếm khi leader đang thay đổi |
| stale | Cho phép follower phục vụ read | Có thể mở rộng tải đọc và trả lời khi không có leader, nhưng dữ liệu có thể cũ |
| consistent | Leader xác minh còn là leader với quorum trước khi trả lời | Độ tin cậy đọc cao hơn nhưng thêm round-trip và latency |

HTTP API của Consul dùng default consistency mode nếu request không chỉ định mode khác. Consul DNS sử dụng stale mode mặc định cho các truy vấn discovery bên dưới. Không nên hiểu rằng mọi đường truy vấn Consul có cùng hành vi mặc định.

Consistency mode áp dụng cho read request. Các thao tác ghi không chọn mode theo query parameter; Consul xử lý write theo cơ chế consistent của cluster.

Nếu một thao tác cần dữ liệu mới nhất, một số endpoint hỗ trợ query parameter consistent. Nếu chấp nhận dữ liệu có thể stale để tăng khả năng đọc và phân tải, endpoint có thể hỗ trợ stale. Chỉ dùng mode được endpoint đó hỗ trợ và kiểm tra tài liệu phiên bản đang chạy.

Ví dụ truy vấn Health API yêu cầu consistency mạnh:

    curl "http://consul:8500/v1/health/service/inventory-service?consistent"

Ví dụ cho phép stale read:

    curl "http://consul:8500/v1/health/service/inventory-service?stale"

Đọc consistent cần leader xác minh quorum, vì vậy có thể tăng latency và phụ thuộc quorum. Không nên bật cho mọi request chỉ vì muốn danh sách luôn mới; hãy dành cho thao tác thực sự không chịu được stale read.

Ở stale mode, dữ liệu thường gần với leader trong điều kiện bình thường nhưng không có giới hạn trên tuyệt đối cho độ cũ. Nếu consumer không thể chịu được stale result, hãy chọn consistency mode phù hợp thay vì giả định follower luôn chỉ chậm một khoảng cố định.

## 8. Consul DNS và HTTP API không giống nhau

Consul DNS dùng stale consistency mode mặc định khi truy vấn các API service discovery bên dưới. Mục tiêu là cho phép nhiều server phục vụ read và có thể tiếp tục trả kết quả khi cluster không có leader, với rủi ro dữ liệu cũ hơn.

Consul HTTP API mặc định dùng default mode, mạnh trong hầu hết trường hợp. Một client gọi HTTP API có thể chọn consistency mode cho từng request nếu endpoint hỗ trợ.

Vì vậy, hai consumer cùng hỏi một service nhưng dùng DNS và HTTP API có thể nhận kết quả khác nhau trong một khoảng thời gian. Điều này không nhất thiết là lỗi đăng ký; có thể là hệ quả của consistency mode, follower replication hoặc cache.

Khi cần giới hạn stale DNS result, Consul có cấu hình nâng cao như dns_config.allow_stale và dns_config.max_stale. Việc giới hạn stale có thể chuyển thêm truy vấn về leader khi follower quá cũ, làm tăng tải trong lúc cluster đang quá tải. Chỉ áp dụng sau khi đánh giá tác động và xác định rằng stale result nguy hiểm hơn việc truy vấn có thể chậm hoặc thất bại.

## 9. Consul blocking query và long polling

Blocking query giúp consumer chờ thay đổi thay vì liên tục polling theo một khoảng thời gian cố định. Nhiều Consul API trả header X-Consul-Index biểu diễn trạng thái tài nguyên. Client gửi index đã nhận ở request trước cùng wait để yêu cầu Consul giữ request cho tới khi có thay đổi hoặc hết thời gian chờ.

Ví dụ lần đầu truy vấn:

    curl -i "http://consul:8500/v1/health/service/inventory-service"

Response có thể chứa:

    X-Consul-Index: 12345

Lần tiếp theo:

    curl -i "http://consul:8500/v1/health/service/inventory-service?index=12345&wait=5m"

Request có thể được giữ mở tới khi trạng thái liên quan thay đổi hoặc thời gian wait kết thúc. Hết thời gian chờ không có nghĩa dữ liệu đã thay đổi; client cần đọc lại header index và tiếp tục vòng lặp.

Blocking query giảm polling vô ích khi registry không đổi. Khi có thay đổi, response có thể được trả sớm hơn chu kỳ polling cố định. Tuy vậy, nó vẫn có timeout, cần xử lý reconnect và không bảo đảm mọi consumer nhận thay đổi cùng một thời điểm.

Không phải mọi Consul endpoint đều hỗ trợ blocking query. Kiểm tra tài liệu của endpoint cụ thể trước khi xây dựng watcher.

## 10. Spring Cloud Consul Catalog Watch

Spring Cloud Consul có Catalog Watch sử dụng blocking Consul HTTP API để theo dõi thay đổi service catalog. Khi có dữ liệu service mới, watch có thể phát Heartbeat Event để thành phần discovery liên quan cập nhật.

Một số thuộc tính cấu hình hiện hành:

    spring:
      cloud:
        consul:
          discovery:
            catalog-services-watch-delay: 1000
            catalog-services-watch-timeout: 2

catalog-services-watch-delay là khoảng delay giữa các lần gọi watch, tính bằng millisecond; tài liệu hiện hành công bố mặc định 1000. catalog-services-watch-timeout là số giây chờ blocking query; mặc định được công bố là 2 giây trong bảng cấu hình hiện hành.

Đây là cấu hình cho watch của Spring Cloud Consul, không phải cam kết mọi thay đổi sẽ tới mọi consumer trong đúng một giây. Độ trễ còn phụ thuộc thời gian Consul xử lý, mạng, event dispatch, cache và LoadBalancer.

Khi thay đổi các giá trị này:

- Delay thấp hơn có thể làm watcher bắt đầu vòng tiếp theo sớm hơn nhưng tăng hoạt động điều phối.
- Timeout dài hơn cho phép blocking query chờ lâu hơn và giảm polling khi catalog ít thay đổi.
- Timeout phải tương thích với HTTP client timeout và chính sách reconnect.
- Không nên tạo quá nhiều watcher cho cùng một service nếu một watcher hoặc cache dùng chung đã đủ.

Kiểm tra đúng tên property và behavior của Spring Cloud Consul version đang dùng; không nhầm Catalog Watch với Consul Config Watch.

## 11. Cache: giảm chi phí nhưng tăng tuổi dữ liệu

Cache giúp tránh truy vấn registry cho từng request. Tuy nhiên, cache tạo ra một khoảng thời gian mà dữ liệu consumer sử dụng có thể khác registry hiện tại.

Các lớp cache thường gặp:

- Response cache phía Eureka Server.
- Registry cache cục bộ của Eureka Client.
- Agent/query cache của Consul nếu được cấu hình.
- Cache của DiscoveryClient hoặc adapter.
- ServiceInstanceListSupplier cache của Spring Cloud LoadBalancer.
- DNS cache trong JVM, operating system hoặc resolver.

Nếu nhiều lớp cache cùng tồn tại, độ trễ có thể cộng dồn. Ví dụ Eureka client refresh registry mỗi 30 giây, sau đó LoadBalancer giữ danh sách thêm một khoảng TTL. Thời điểm request ngừng chọn instance cũ có thể muộn hơn thời điểm Eureka Server đã xóa instance.

Không phải mọi DiscoveryClient đều có cùng cache. Hãy xác định chính xác implementation, cache layer và refresh mechanism đang hoạt động trước khi thay đổi TTL.

## 12. Đặt freshness budget theo nghiệp vụ

Freshness budget là khoảng thời gian tối đa mà hệ thống chấp nhận consumer dùng dữ liệu discovery cũ cho một loại request. Đây là SLO thiết kế của hệ thống, không phải giá trị mặc định do Eureka hay Consul cam kết.

Ví dụ minh họa:

| Loại workload | Freshness budget tham khảo | Lý do |
|---|---:|---|
| Tra cứu catalog nội bộ | 30–60 giây | Một instance cũ có thể được xử lý bằng retry |
| API đọc có nhiều replica | 5–15 giây | Muốn chuyển traffic khỏi instance lỗi tương đối nhanh |
| Điều phối job mới | 5–10 giây | Tránh giao job tới worker vừa rời pool |
| Thay đổi trạng thái bảo trì | 1–5 giây nếu có thể | Cần hạn chế request mới tới instance đang drain |
| Luồng yêu cầu dữ liệu nhất quán nghiêm ngặt | Theo cơ chế kiểm soát riêng | Discovery không thay thế transaction hoặc source of truth |

Các số trên chỉ là ví dụ để bắt đầu thảo luận. Cần đo propagation delay, request failure rate và năng lực registry để đặt ngưỡng phù hợp.

Freshness budget phải tính từ lúc thay đổi được chấp nhận tại registry tới lúc consumer và LoadBalancer thực sự ngừng dùng dữ liệu cũ. Chỉ đo thời gian registry cập nhật là chưa đủ.

## 13. Chọn fail-open hay fail-closed khi registry không truy cập được

Khi registry tạm thời không thể truy cập, consumer phải quyết định có tiếp tục dùng cache hay không.

**Fail-open với cache**

- Tiếp tục dùng danh sách instance gần nhất.
- Tăng khả năng phục vụ trong sự cố registry ngắn.
- Chấp nhận rủi ro cache chứa instance đã chết hoặc đã bị rút khỏi traffic.
- Phù hợp hơn với API đọc có retry, timeout và nhiều replica.

**Fail-closed**

- Không chọn instance nếu không thể xác minh danh sách theo yêu cầu.
- Giảm nguy cơ dùng địa chỉ cũ trong những thao tác nhạy cảm.
- Có thể làm request thất bại dù service đích vẫn đang hoạt động.
- Phù hợp với các thao tác mà chọn nhầm instance có hậu quả lớn và có phương án xử lý lỗi rõ ràng.

Không nên áp dụng một chính sách cho mọi service. Một consumer gọi API đọc có thể tiếp tục dùng cache trong thời gian ngắn; một thành phần điều phối thao tác nhạy cảm có thể yêu cầu trạng thái registry mới hơn hoặc xác minh thêm ở tầng ứng dụng.

Dù fail-open hay fail-closed, request vẫn cần timeout, retry có giới hạn, circuit breaker và xử lý trường hợp instance biến mất sau khi được chọn.

## 14. Chi phí của đồng bộ thường xuyên

Giảm chu kỳ fetch hoặc tăng mức consistency có thể làm dữ liệu mới hơn, nhưng tạo chi phí:

| Cách đồng bộ | Chi phí tăng | Lợi ích |
|---|---|---|
| Polling thường xuyên | Nhiều HTTP request, CPU và response parsing | Giới hạn thời gian chờ tới lần poll tiếp theo |
| Full registry fetch | Payload lớn, deserialize nhiều instance | Tái đồng bộ toàn bộ trạng thái |
| Delta fetch | Xử lý và reconcile delta; cần xử lý sai lệch | Truyền ít dữ liệu khi số thay đổi thấp |
| Blocking query | Giữ connection, quản lý timeout/reconnect | Giảm polling khi không có thay đổi |
| Consistent read | Leader round-trip/quorum verification | Giảm rủi ro đọc stale ở endpoint hỗ trợ |
| Cache TTL ngắn | Refresh và lookup nhiều hơn | Giảm tuổi dữ liệu cũ |
| Cache TTL dài | Ít truy vấn hơn | Tăng thời gian có thể dùng dữ liệu cũ |

Với nhiều nghìn consumer, giảm fetch interval từ 30 giây xuống 5 giây có thể làm tần suất fetch tăng khoảng sáu lần. Đây là phép tính tần suất đơn giản; tải thực tế còn phụ thuộc delta size, số instance, compression, số server và cách phân phối client.

Không giảm mọi interval đồng thời. Hãy đo từng lớp và thay đổi một tham số mỗi lần.

## 15. Bảng quyết định theo tình huống

| Tình huống | Ưu tiên | Cách tiếp cận |
|---|---|---|
| Consumer cần tiếp tục hoạt động khi registry lỗi ngắn hạn | Availability | Dùng cache gần nhất, timeout và retry có giới hạn |
| Instance đang bảo trì cần ngừng nhận request mới | Freshness và an toàn routing | Đánh dấu out-of-service/maintenance, chờ propagation và drain |
| Cluster Consul nhiều read, cần scale query | Read scalability | Cân nhắc stale mode hoặc cache theo endpoint phù hợp |
| Consumer không chịu được stale read của một truy vấn quan trọng | Consistency | Dùng consistent mode nếu endpoint hỗ trợ, chấp nhận latency |
| Registry thay đổi ít nhưng nhiều consumer polling | Chi phí đồng bộ | Delta fetch, blocking query hoặc watch |
| Instance thay đổi liên tục do autoscaling dao động | Ổn định topology | Stabilization window, rollout theo batch và giảm health flapping |
| Consumer vẫn dùng instance cũ sau registry update | Cache freshness | Kiểm tra từng cache và LoadBalancer supplier |

## 16. Cấu hình và ví dụ thực hành với Eureka

Ví dụ cấu hình client giữ fetch interval mặc định và delta:

    eureka:
      client:
        fetch-registry: true
        registry-fetch-interval-seconds: 30
        disable-delta: false
        g-zip-content: true
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90

Cấu hình trên ưu tiên cách vận hành phổ biến: cache cục bộ, fetch định kỳ và delta. Chỉ giảm registry-fetch-interval-seconds khi đã đo độ trễ propagation và tải server.

Khi kiểm thử:

1. Đăng ký hai instance của inventory-service.
2. Khởi động consumer và xác nhận cache có cả hai instance.
3. Đưa một instance sang OUT_OF_SERVICE hoặc deregister.
4. Ghi thời điểm Eureka Server nhận thay đổi.
5. Ghi thời điểm consumer nhìn thấy danh sách mới.
6. Ghi thời điểm LoadBalancer ngừng chọn instance đó.
7. Lặp lại khi Eureka Server tạm thời không truy cập được.
8. So sánh số request lỗi khi consumer dùng cache với thời gian registry phục hồi.

Không dùng một lần thử làm kết luận. Lặp lại với số consumer và instance khác nhau để thấy ảnh hưởng tải.

## 17. Cấu hình và ví dụ thực hành với Consul

Ví dụ Spring Cloud Consul:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true
            consistency-mode: default
            catalog-services-watch-delay: 1000
            catalog-services-watch-timeout: 2

query-passing=true yêu cầu truy vấn health service chỉ trả instance passing. consistency-mode điều khiển consistency mode cho health service request theo implementation và phiên bản Spring Cloud Consul đang sử dụng. Catalog watch dùng blocking query để theo dõi thay đổi catalog.

Với raw Consul HTTP API, có thể so sánh các mode:

    curl "http://consul:8500/v1/health/service/inventory-service"
    curl "http://consul:8500/v1/health/service/inventory-service?stale"
    curl "http://consul:8500/v1/health/service/inventory-service?consistent"

Khi kiểm thử, ghi response header X-Consul-Effective-Consistency nếu endpoint trả header này để xác định mode thực tế được dùng.

Không đặt consistent mode cho mọi truy vấn chỉ vì muốn dữ liệu mới. Đọc mạnh có thêm chi phí và phụ thuộc quorum. Cũng không bật stale mode ở mọi nơi nếu consumer không thể xử lý instance cũ.

## 18. Đo propagation delay và chi phí

Một benchmark nên ghi nhận các mốc sau:

- T0: ứng dụng gọi register, deregister hoặc đổi status.
- T1: registry xác nhận thay đổi.
- T2: response cache hoặc follower phản ánh thay đổi.
- T3: consumer DiscoveryClient nhìn thấy thay đổi.
- T4: LoadBalancer ngừng chọn instance cũ hoặc bắt đầu chọn instance mới.
- T5: request thực tế đầu tiên đi theo topology mới.

Các chỉ số:

    registry_write_latency = T1 - T0
    registry_replication_delay = T2 - T1
    consumer_discovery_delay = T3 - T1
    load_balancer_propagation_delay = T4 - T1
    end_to_end_topology_delay = T5 - T0

Đây là metric do hệ thống benchmark tự instrument; không phải tên metric mặc định có sẵn trong Eureka hoặc Consul.

Đồng thời đo:

- Request rate tới registry.
- Response size trung bình và p95.
- CPU, heap, GC và network của registry.
- Số lần fetch, delta fetch, full reconciliation.
- Số blocking query đang mở và tỷ lệ timeout.
- Lookup latency/error phía consumer.
- Tỷ lệ request tới instance đã bị rút khỏi pool.
- Số instance được trả về theo từng truy vấn.

Thử nghiệm với polling interval khác nhau, cache TTL khác nhau và consistency mode khác nhau. Giữ nguyên topology, số consumer và workload để so sánh công bằng.

## 19. Xử lý khi dữ liệu cũ kéo dài

Khi consumer vẫn thấy instance cũ, kiểm tra theo thứ tự:

1. Registry đã chấp nhận deregister hoặc status change chưa?
2. Với Consul, leader/follower có đang hội tụ và query dùng consistency mode nào?
3. Với Eureka, client fetch delta có thành công hay đang dùng cache cũ?
4. Response cache phía registry có đang chờ refresh không?
5. DiscoveryClient hoặc adapter có giữ cache riêng không?
6. LoadBalancer có ServiceInstanceListSupplier cache không?
7. Consumer có DNS cache hoặc connection pool giữ địa chỉ cũ không?
8. Instance có được agent, orchestrator hoặc process khác đăng ký lại không?

Nếu registry đã đúng nhưng consumer stale, không nên xóa registration lặp lại. Tập trung vào cache và refresh path. Nếu registry vẫn sai, kiểm tra replication, quorum, heartbeat, self-preservation hoặc nguồn sở hữu registration.

Khi registry không có quorum, cần hiểu mỗi mode phản hồi ra sao. Consul consistent read có thể không trả lời nếu không thể xác minh quorum; stale read có thể vẫn trả lời từ server có dữ liệu cũ. Quyết định phụ thuộc vào việc consumer có thể chấp nhận stale data hay phải từ chối request.

## 20. Nguyên tắc thiết kế

- Đặt freshness budget theo tác động nghiệp vụ của từng service.
- Dùng cache để tăng khả năng phục vụ khi registry lỗi ngắn hạn, nhưng theo dõi cache age.
- Dùng delta hoặc blocking query để giảm chi phí polling khi phù hợp.
- Chỉ yêu cầu consistent read cho truy vấn thật sự không chịu được stale result.
- Phân biệt hành vi DNS và HTTP API của Consul.
- Theo dõi Eureka self-preservation và full reconciliation.
- Kiểm tra cả DiscoveryClient cache và LoadBalancer cache.
- Dùng timeout, retry có giới hạn và circuit breaker khi instance biến mất sau khi được chọn.
- Drain instance có kế hoạch trước khi deregister và chờ propagation.
- Không coi registry là source of truth cho giao dịch hoặc phân quyền nghiệp vụ.
- Đo độ trễ end-to-end từ thay đổi registration tới request thực tế.
- Kiểm thử network partition, registry outage, leader election và cache stale trước khi triển khai.

## 21. Kết luận

Độ mới danh sách, tính sẵn sàng và chi phí đồng bộ là ba mục tiêu liên quan nhưng khác nhau. Eureka dùng registry cache cục bộ và delta fetch để giảm chi phí tra cứu, đồng thời có thể tiếp tục phục vụ từ cache khi server gián đoạn. Consul cung cấp consistency mode cho HTTP API, stale read để tăng khả năng đọc và consistent read với chi phí quorum; blocking query giúp giảm polling không cần thiết.

Không nên chọn một cấu hình chỉ dựa trên mong muốn danh sách luôn mới. Hãy xác định freshness budget, quyết định fail-open hay fail-closed khi registry lỗi, đo cache và propagation delay ở mọi tầng, rồi cân bằng polling, delta, blocking query và consistency mode theo nhu cầu từng service. Discovery chỉ cung cấp thông tin định tuyến; ứng dụng vẫn cần chịu được instance stale bằng timeout, retry, circuit breaker và xử lý lỗi phù hợp.

## Tài liệu tham khảo

- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [HashiCorp Consul — Consistency Modes](https://developer.hashicorp.com/consul/api-docs/features/consistency)
- [HashiCorp Consul — Blocking Queries](https://developer.hashicorp.com/consul/api-docs/features/blocking)
- [HashiCorp Consul — Agent Caching](https://developer.hashicorp.com/consul/api-docs/features/caching)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Service Discovery and Catalog Watch](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud LoadBalancer — Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

