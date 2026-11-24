# Bộ đệm phía máy chủ, bộ đệm phía client và đường truyền thay đổi

## 1. Vì sao registry cần nhiều lớp bộ đệm?

Trong Spring Cloud Service Discovery, Eureka lưu thông tin các application và instance để client có thể tìm dịch vụ theo tên. Registry thay đổi liên tục khi instance khởi động, gửi heartbeat, đổi trạng thái hoặc dừng hoạt động. Nếu mỗi request đọc registry đều phải dựng lại toàn bộ dữ liệu, Eureka Server và các client sẽ chịu tải không cần thiết.

Eureka vì vậy sử dụng bộ đệm ở nhiều vị trí. Khi điều tra một instance vừa đăng ký nhưng chưa xuất hiện ở một client, cần biết dữ liệu đang nằm ở lớp nào và thay đổi phải đi qua những bước nào.

Trong một ứng dụng dùng Eureka, có thể phân biệt ba lớp:

1. **Server response cache:** Eureka Server tạo và lưu nội dung phản hồi registry để phục vụ REST API.
2. **Eureka Client registry cache:** Eureka Client tải registry về và giữ bản sao cục bộ để tra cứu.
3. **LoadBalancer cache:** nếu ứng dụng dùng Spring Cloud LoadBalancer với caching được bật, bộ cân bằng tải có thể giữ thêm danh sách instance đã chọn từ DiscoveryClient.

Ba lớp này có mục đích khác nhau. Registry trong Eureka Server là dữ liệu đăng ký mà server quản lý; response cache giúp trả lời truy vấn nhanh; client registry cache giúp ứng dụng tra cứu cục bộ; LoadBalancer cache tối ưu việc lấy danh sách instance để chọn đích gọi.

## 2. Nhìn tổng thể đường đi của một thay đổi

Giả sử instance mới của payment-service đăng ký với Eureka A. Thay đổi được ghi vào registry tại A, được nhân bản sang peer nếu có cấu hình cụm, sau đó được đưa vào response cache mà REST API sử dụng. Eureka Client định kỳ gọi API để tải delta hoặc toàn bộ registry. DiscoveryClient đọc dữ liệu từ registry cục bộ của Eureka Client; LoadBalancer có thể cache danh sách instance thêm một lớp nữa.

~~~mermaid
flowchart LR
    APP[Instance đăng ký] --> REG[Eureka Server Registry]
    REG --> PEER[Nhân bản sang peer]
    REG --> RWC[Server Read-Write Cache]
    RWC --> ROC[Server Read-Only Cache]
    ROC --> API[Eureka REST API]
    API --> FETCH[Eureka Client Fetch]
    FETCH --> CRC[Client Registry Cache]
    CRC --> DISC[DiscoveryClient]
    DISC --> LBC[LoadBalancer Cache nếu bật]
    LBC --> CALL[Chọn instance cho request]
~~~

Đây là mô hình khái quát. Chi tiết cập nhật cache và replication có thể khác theo phiên bản Eureka, cấu hình và provider. Không phải mọi thay đổi đều đi qua mọi lớp cache trong mọi request, nhưng sơ đồ giúp xác định các điểm có thể tạo độ trễ quan sát.

## 3. Bộ đệm phía máy chủ Eureka

### 3.1. Registry và response cache là hai thứ khác nhau

Eureka Server quản lý registry chứa thông tin instance. Khi client yêu cầu danh sách application qua REST API, server cần tạo phản hồi từ dữ liệu registry. Để giảm chi phí xử lý và serialization, Eureka có response cache.

Response cache không phải nguồn dữ liệu đăng ký độc lập. Nó là bản biểu diễn được lưu để phục vụ các truy vấn đọc. Khi instance được đăng ký, gia hạn, hủy đăng ký hoặc thay đổi trạng thái, registry được cập nhật theo thao tác tương ứng; response cache cần được làm mới hoặc vô hiệu hóa để phản hồi sau đó phản ánh dữ liệu mới.

Vì vậy, nếu registry đã nhận một thay đổi nhưng REST API vẫn trả dữ liệu cũ, cần kiểm tra cơ chế response cache và thời điểm cache được làm mới.

### 3.2. Read-write cache và read-only cache

Trong triển khai Eureka Server phổ biến, response cache có hai lớp thường được gọi là:

- **Read-write cache:** lưu các response đã được tạo và có thể bị vô hiệu hóa khi registry thay đổi hoặc cache hết hạn.
- **Read-only cache:** giữ bản response dùng cho truy vấn đọc nhanh. Một tác vụ nền định kỳ cập nhật dữ liệu từ read-write cache; cấu hình có thể cho phép tắt lớp read-only này.

Luồng đọc khái quát:

1. REST request cần dữ liệu registry cho một cache key, chẳng hạn toàn bộ applications hoặc một application cụ thể.
2. Server kiểm tra read-only cache nếu cơ chế này đang bật.
3. Nếu không có dữ liệu phù hợp trong read-only cache, server có thể lấy hoặc tạo response qua read-write cache.
4. Kết quả được trả về cho client và được cache theo cơ chế tương ứng.

Khi registry thay đổi, Eureka thường vô hiệu hóa các cache key response liên quan; request đọc tiếp theo có thể tạo lại response từ registry mới. Tác vụ nền định kỳ cũng làm mới read-only cache từ read-write cache. Vì vậy, không nên mặc định mọi thay đổi đều phải chờ hết response-cache-update-interval-ms mới nhìn thấy được: invalidation có thể khiến một key được tạo lại sớm hơn, còn chu kỳ nền là cơ chế cập nhật bổ sung.

### 3.3. Cấu hình response cache

Một số thuộc tính Eureka Server thường dùng để điều chỉnh response cache:

| Thuộc tính | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---:|---|
| eureka.server.use-read-only-response-cache | true | Bật lớp read-only response cache |
| eureka.server.response-cache-update-interval-ms | 30000 ms | Chu kỳ tác vụ nền cập nhật read-only cache |

Ví dụ:

~~~yaml
eureka:
  server:
    use-read-only-response-cache: true
    response-cache-update-interval-ms: 30000
~~~

Các giá trị trên là mặc định thường gặp của Eureka Server, có thể khác theo phiên bản và cấu hình. Không nên chỉnh chu kỳ cache chỉ dựa trên mong muốn thấy thay đổi nhanh hơn; cần đo tải REST API, số lượng instance và độ trễ chấp nhận được.

Tắt read-only cache có thể làm response được lấy trực tiếp qua read-write cache trong một số tình huống, nhưng server phải xử lý nhiều công việc đọc hơn. Với registry lớn hoặc tần suất truy vấn cao, điều này có thể làm tăng CPU và chi phí tạo response. Hãy thử nghiệm tải trước khi thay đổi.

## 4. Bộ đệm phía Eureka Client

### 4.1. Client giữ registry cục bộ

Eureka Client không gửi một request REST mới đến server cho mỗi lần ứng dụng gọi DiscoveryClient. Thay vào đó, client tải registry về và giữ một bản sao cục bộ. Các thành phần như DiscoveryClient sử dụng bản registry này để tra cứu service ID và danh sách instance.

Lợi ích:

- Tra cứu instance nhanh mà không phải gọi Eureka Server theo từng request nghiệp vụ.
- Giảm lưu lượng đọc đến server.
- Ứng dụng vẫn có thể tra cứu dữ liệu gần nhất mà nó đã tải nếu server tạm thời không truy cập được.

Đánh đổi là dữ liệu cục bộ có thể cũ hơn registry ở server. Khi một instance vừa đăng ký hoặc vừa bị xóa, client cần chờ chu kỳ fetch tiếp theo hoặc một lần đồng bộ phù hợp trước khi thấy thay đổi.

### 4.2. Fetch toàn bộ và fetch delta

Khi khởi tạo hoặc khi cần đồng bộ lại, Eureka Client có thể tải toàn bộ registry. Trong những lần cập nhật tiếp theo, client thường dùng delta để lấy phần thay đổi kể từ lần fetch trước, nhờ đó giảm lượng dữ liệu truyền qua mạng.

Hai endpoint REST tương ứng thường gặp:

| Endpoint | Nội dung |
|---|---|
| GET /eureka/apps | Toàn bộ registry mà server cung cấp |
| GET /eureka/apps/delta | Những thay đổi registry theo cơ chế delta |

Delta có thể chứa instance mới, instance bị xóa hoặc thay đổi trạng thái. Client áp dụng các thay đổi đó lên bản registry cục bộ.

Nếu dữ liệu delta không thể áp dụng nhất quán, chẳng hạn hash registry không khớp với trạng thái client mong đợi, Eureka Client có thể yêu cầu đồng bộ toàn bộ để phục hồi. Cơ chế này giúp client sửa lại bản sao cục bộ khi phát hiện sai lệch.

### 4.3. Chu kỳ fetch registry

Thuộc tính thường dùng để cấu hình chu kỳ cập nhật registry ở Eureka Client:

| Thuộc tính | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---:|---|
| eureka.client.registry-fetch-interval-seconds | 30 giây | Khoảng cách giữa các lần fetch registry |
| eureka.client.disable-delta | false | Cho phép client dùng delta khi giá trị là false |

Ví dụ:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
    disable-delta: false
~~~

Nếu tăng chu kỳ fetch, client tạo ít request hơn nhưng có thể giữ registry cũ lâu hơn. Nếu giảm chu kỳ, client cập nhật thường xuyên hơn nhưng tăng tải REST API, lưu lượng mạng và công việc xử lý delta. Hãy cân nhắc số lượng client và instance trong toàn hệ thống.

## 5. Cache của Spring Cloud LoadBalancer

Eureka Client registry cache và LoadBalancer cache là hai lớp khác nhau. DiscoveryClient lấy danh sách instance từ registry cục bộ của Eureka Client. Spring Cloud LoadBalancer có thể cache danh sách instance mà ServiceInstanceListSupplier cung cấp để tránh phải lấy và xử lý danh sách quá thường xuyên.

Luồng tra cứu khi dùng LoadBalancer:

1. Ứng dụng gửi request đến tên dịch vụ, ví dụ payment-service.
2. LoadBalancer lấy danh sách instance từ ServiceInstanceListSupplier.
3. Supplier có thể lấy dữ liệu qua DiscoveryClient.
4. Nếu caching được bật, LoadBalancer có thể trả danh sách từ cache của chính nó.
5. LoadBalancer chọn một instance và chuyển request đến host/port đã chọn.

Như vậy, một thay đổi mới trong Eureka Server có thể đã được Eureka Client fetch về nhưng chưa xuất hiện ngay trong danh sách mà LoadBalancer đang cache.

Spring Cloud LoadBalancer có thể sử dụng cache theo cấu hình và implementation trên classpath. Các thuộc tính cache thường gặp gồm:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

TTL và capacity ở trên là ví dụ cấu hình thường gặp, không phải cam kết mặc định cho mọi phiên bản. Hãy kiểm tra tài liệu Spring Cloud release train đang dùng và loại cache provider được chọn. Nếu danh sách instance đã được cache ở một tầng khác, cần tránh bật thêm cache không cần thiết khiến độ trễ cập nhật khó dự đoán.

Không phải mọi ứng dụng Eureka đều sử dụng Spring Cloud LoadBalancer. Nếu ứng dụng chỉ gọi DiscoveryClient trực tiếp, có thể không có lớp LoadBalancer cache này.

## 6. Đường truyền thay đổi giữa các thành phần

### 6.1. Instance đăng ký mới

Khi instance mới khởi động:

1. Eureka Client gửi thao tác register đến Eureka Server.
2. Server cập nhật registry cục bộ.
3. Server làm mới hoặc vô hiệu hóa các response cache liên quan.
4. Nếu server thuộc một cụm, thay đổi được nhân bản sang peer theo cơ chế Eureka.
5. Các Eureka Client định kỳ fetch delta hoặc full registry từ server mà chúng kết nối.
6. Client cập nhật registry cache cục bộ.
7. DiscoveryClient trả danh sách instance mới cho thành phần gọi.
8. Nếu LoadBalancer cache danh sách instance, cache này cần hết hạn hoặc được cập nhật trước khi lựa chọn phản ánh thay đổi.

### 6.2. Instance hủy đăng ký hoặc bị eviction

Khi instance dừng có trật tự, client có thể gửi cancel. Nếu instance mất kết nối đột ngột, server có thể phát hiện qua lease expiration và eviction. Sau khi registry thay đổi, response cache và peer được cập nhật theo cơ chế tương ứng; client nhận thay đổi qua lần fetch tiếp theo.

Ngay cả khi server đã xóa instance, một client có thể còn giữ bản ghi cũ trong registry cache. Nếu LoadBalancer cache thêm danh sách đó, khoảng thời gian stale có thể kéo dài thêm tùy TTL và thời điểm cache được làm mới.

### 6.3. Instance thay đổi trạng thái

Khi trạng thái instance chuyển từ UP sang OUT_OF_SERVICE hoặc trạng thái khác, thay đổi cần đi qua registry, response cache và quá trình fetch của client. Thành phần chọn instance chỉ loại hoặc giữ instance theo trạng thái mà nó nhìn thấy và theo chính sách lọc đang dùng.

Không nên giả định thay đổi status được truyền đến mọi client ngay lập tức. Nếu cần ngừng traffic khẩn cấp, hãy kết hợp cơ chế điều phối traffic hoặc gateway phù hợp thay vì chỉ trông chờ vào chu kỳ fetch cache.

## 7. Độ trễ cập nhật được tạo ra ở đâu?

Thời gian từ lúc một thay đổi xảy ra đến lúc ứng dụng sử dụng dữ liệu mới có thể gồm nhiều khoảng:

| Giai đoạn | Nguồn độ trễ | Cách quan sát |
|---|---|---|
| Registry nhận thay đổi | Thời gian xử lý register, renew, cancel hoặc eviction | Log và metric Eureka Server |
| Server response cache | Invalidation hoặc chu kỳ làm mới read-only cache | So sánh registry và phản hồi REST API |
| Peer replication | Kết nối mạng và hàng đợi replication giữa các Eureka Server | Log peer và truy vấn nhiều node |
| Client registry fetch | Chu kỳ fetch và thời gian xử lý delta/full fetch | Log Eureka Client, registry-fetch interval |
| LoadBalancer cache | TTL và cơ chế làm mới danh sách instance | Cấu hình LoadBalancer và log supplier/cache |

Không có một con số tổng cố định áp dụng cho mọi hệ thống. Các bước có thể chạy song song hoặc theo các nhánh khác nhau. Chẳng hạn, client có thể fetch từ một peer đã nhận thay đổi trong khi một peer khác vẫn đang chờ replication.

Ví dụ minh họa: một client vừa fetch registry xong, ngay sau đó một instance mới đăng ký. Client có thể phải đợi gần hết chu kỳ fetch tiếp theo mới nhận được thay đổi. Nếu server response cache chưa được làm mới, client fetch ở lần đó vẫn có thể nhận nội dung cũ; nếu LoadBalancer vừa tạo cache, danh sách được dùng để chọn instance có thể tiếp tục cũ cho đến khi cache được làm mới.

## 8. Ví dụ cấu hình và cách đọc độ trễ

Giả sử một hệ thống thử nghiệm có cấu hình:

~~~yaml
# Eureka Server
eureka:
  server:
    use-read-only-response-cache: true
    response-cache-update-interval-ms: 30000
~~~

~~~yaml
# Eureka Client
eureka:
  client:
    registry-fetch-interval-seconds: 30
    disable-delta: false
~~~

~~~yaml
# Spring Cloud LoadBalancer, nếu ứng dụng có dùng cache
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Đây là cấu hình minh họa để nhận diện các lớp cache. Không cộng máy móc 30 + 30 + 35 giây rồi kết luận đó là thời gian stale tối đa. Thời điểm thay đổi so với lịch refresh, cache invalidation, replication, retry, lỗi mạng và cách supplier làm mới dữ liệu đều ảnh hưởng kết quả.

Để đo thực tế, ghi timestamp khi instance đăng ký, sau đó truy vấn lần lượt:

1. REST API của Eureka Server nhận đăng ký.
2. REST API của từng peer trong cụm.
3. Registry cache mà ứng dụng client đang sử dụng.
4. Danh sách instance được LoadBalancer supplier trả về nếu có dùng LoadBalancer.

So sánh timestamp và instance ID tại từng bước sẽ giúp tìm ra lớp nào đang giữ dữ liệu cũ.

## 9. Chẩn đoán khi client chưa thấy thay đổi

Khi một instance mới đã đăng ký nhưng client chưa nhìn thấy, kiểm tra theo trình tự:

1. Gọi GET /eureka/apps/{APP_NAME} trực tiếp trên Eureka Server mà client đang sử dụng.
2. Nếu chưa có instance, kiểm tra registry, response cache, log register và replication của server.
3. Nếu node này chưa có nhưng peer khác đã có, điều tra kết nối peer và độ trễ nhân bản.
4. Nếu REST API đã có instance nhưng client chưa thấy, kiểm tra registry-fetch interval, log fetch, lỗi delta và trạng thái full fetch.
5. Nếu DiscoveryClient đã thấy instance nhưng request qua LoadBalancer chưa chọn instance đó, kiểm tra cache, supplier và chính sách lọc của LoadBalancer.
6. Nếu tất cả cache đã cập nhật mà request vẫn thất bại, kiểm tra host, port, network policy và sức khỏe endpoint nghiệp vụ.

| Triệu chứng | Lớp có thể liên quan | Hướng kiểm tra |
|---|---|---|
| REST API trả dữ liệu cũ ngay sau register | Server response cache hoặc registry chưa cập nhật | Kiểm tra server log, cache refresh và registry |
| Một Eureka Server có instance, peer khác chưa có | Peer replication | Kiểm tra endpoint peer, mạng và log replication |
| REST API có instance nhưng DiscoveryClient chưa thấy | Eureka Client registry cache | Kiểm tra lần fetch gần nhất, delta/full fetch và cấu hình interval |
| DiscoveryClient thấy instance nhưng LoadBalancer chưa chọn | LoadBalancer cache hoặc supplier/filter | Kiểm tra TTL, cache provider và chính sách chọn instance |
| Instance đã cancel nhưng vẫn được gọi | Client cache hoặc LoadBalancer cache còn stale | Kiểm tra thời điểm fetch, TTL và log request |
| Client fetch thất bại liên tục | Kết nối hoặc lỗi API | Kiểm tra DNS, TLS, authentication, timeout và server health |

## 10. Những nguyên tắc khi điều chỉnh cache

### 10.1. Đừng giảm mọi chu kỳ cùng lúc

Giảm response-cache interval, client fetch interval và LoadBalancer TTL cùng lúc có thể làm tải tăng ở nhiều tầng. Hãy xác định chính xác tầng đang tạo độ trễ, thay đổi từng tham số và đo lại.

### 10.2. Cân bằng độ mới và tải hệ thống

Chu kỳ ngắn giúp dữ liệu mới đến nhanh hơn nhưng tăng request, serialization, xử lý delta và công việc cache. Với hệ thống có nhiều client, một thay đổi nhỏ trong chu kỳ có thể tạo ra lượng request định kỳ đáng kể.

### 10.3. Hiểu dữ liệu stale là điều có thể xảy ra

Discovery là thông tin về instance tại một thời điểm gần đây, không phải bảo đảm instance vẫn sống ngay khi request được gửi. Ứng dụng vẫn cần timeout, retry có giới hạn, circuit breaker và xử lý lỗi kết nối.

### 10.4. Không dùng cache để thay thế health check

Cache chỉ quyết định dữ liệu nào được trả lại nhanh và khi nào dữ liệu được làm mới. Nó không chứng minh instance khỏe. Kết hợp trạng thái discovery với health check, readiness và giám sát runtime.

### 10.5. Thử nghiệm cả đăng ký, hủy đăng ký và phục hồi

Khi thay đổi cache, hãy kiểm thử instance mới, instance dừng có trật tự, instance mất kết nối, thay đổi trạng thái và sự cố giữa các peer. Chỉ kiểm tra trường hợp đăng ký mới là chưa đủ để hiểu toàn bộ đường truyền thay đổi.

## 11. Tổng kết

Eureka Server có response cache để phục vụ REST API hiệu quả; trong triển khai phổ biến, response cache có read-write cache và read-only cache được làm mới định kỳ. Eureka Client giữ registry cache cục bộ và cập nhật bằng full fetch hoặc delta fetch. Nếu ứng dụng dùng Spring Cloud LoadBalancer, danh sách instance có thể được cache thêm một lớp nữa.

Một thay đổi phải đi qua registry, response cache, peer replication nếu có, client fetch và có thể cả LoadBalancer cache trước khi mọi thành phần sử dụng dữ liệu mới. Vì vậy, độ trễ discovery là kết quả của nhiều chu kỳ và cơ chế cập nhật. Khi chẩn đoán, hãy kiểm tra từng lớp theo thứ tự, so sánh thời điểm và instance ID, rồi chỉ điều chỉnh đúng cache đang gây độ trễ. 
