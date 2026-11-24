# Trạng thái được hỗ trợ và giới hạn chuyển đổi giữa các sổ đăng ký

Trong Spring Cloud Service Discovery, một instance không chỉ có thông tin địa chỉ như host và port. Registry còn cần biểu diễn instance đang hoạt động, đã sẵn sàng nhận request, tạm ngừng nhận traffic hay đã biến mất. Những trạng thái này ảnh hưởng đến cách consumer nhìn thấy và lựa chọn instance.

Spring Cloud Commons cung cấp abstraction `ServiceRegistry` với thao tác đăng ký, hủy đăng ký và cập nhật trạng thái. Tuy nhiên, abstraction này không định nghĩa một bộ trạng thái chuẩn dùng giống hệt cho mọi registry. Eureka, Consul và các implementation khác có mô hình trạng thái, health check và quy tắc chuyển đổi riêng.

Vì vậy, khi thiết kế service discovery, cần phân biệt **trạng thái nghiệp vụ mong muốn** của ứng dụng với **trạng thái kỹ thuật** mà registry hỗ trợ. Khi chuyển từ Eureka sang Consul hoặc ngược lại, phải ánh xạ theo ý nghĩa và hành vi thực tế, không chỉ sao chép chuỗi trạng thái.

## 1. Trạng thái instance có ý nghĩa gì?

Một service ID có thể có nhiều instance. Mỗi instance có vòng đời riêng: khởi động, đăng ký, sẵn sàng nhận traffic, tạm ngừng, gặp lỗi và kết thúc. Registry cần lưu thông tin đủ để các consumer xác định instance nào có thể được dùng.

Các trạng thái thường được nhắc đến trong vận hành:

| Trạng thái khái niệm | Ý nghĩa đối với vòng đời |
|---|---|
| STARTING | Tiến trình đang khởi động, chưa nên nhận request nghiệp vụ |
| UP / HEALTHY | Instance đang hoạt động và có thể được chọn |
| OUT_OF_SERVICE / DRAINING | Instance vẫn tồn tại nhưng cần ngừng nhận request mới |
| DOWN / UNHEALTHY | Instance không đáp ứng điều kiện phục vụ |
| UNKNOWN | Chưa xác định được trạng thái hoặc chưa có đủ dữ liệu |

Đây là cách diễn đạt ở mức nghiệp vụ. Không phải registry nào cũng hỗ trợ tất cả các giá trị trên, và tên gọi cũng có thể khác nhau.

Cần phân biệt ba khái niệm:

- **Registration:** bản ghi cho biết service instance tồn tại và cung cấp endpoint nào.
- **Availability status:** trạng thái mà registry hoặc integration công bố cho instance.
- **Health check result:** kết quả của một phép kiểm tra cụ thể, ví dụ HTTP probe trả thành công hay thất bại.

Một registration có thể tồn tại trong registry trong khi health check đang báo lỗi. Ngược lại, tiến trình có thể đang khỏe nhưng chưa đăng ký thành công. Không nên gộp ba khái niệm thành một cờ boolean duy nhất.

## 2. Hợp đồng trạng thái của ServiceRegistry

Trong Spring Cloud Commons, `ServiceRegistry` là abstraction phía đăng ký. Hợp đồng tổng quát có các thao tác:

~~~java
void register(R registration);

void deregister(R registration);

void setStatus(R registration, String status);

Object getStatus(R registration);
~~~

`R` là kiểu registration cụ thể của implementation. Registration chứa thông tin instance cần thiết cho registry tương ứng.

Ý nghĩa các thao tác:

| Phương thức | Vai trò | Lưu ý |
|---|---|---|
| `register(registration)` | Đăng ký instance | Tạo hoặc công bố registration theo backend |
| `deregister(registration)` | Hủy đăng ký instance | Loại bản ghi hoặc yêu cầu backend ngừng công bố instance |
| `setStatus(registration, status)` | Yêu cầu cập nhật trạng thái | Chuỗi status được diễn giải theo implementation |
| `getStatus(registration)` | Đọc trạng thái hiện tại | Trả về `Object`, không phải một enum portable chung |

Hợp đồng này thống nhất hình thức gọi ở phía ứng dụng, nhưng không đảm bảo semantics trạng thái giữa các backend giống nhau.

### 2.1. Giới hạn của kiểu String và Object

Hai chi tiết trong API rất quan trọng:

- Đầu vào `status` là `String`. Spring Cloud Commons không đưa ra một enum chung bắt buộc cho mọi implementation.
- Kết quả `getStatus()` là `Object`. Kiểu thực tế và cách diễn giải phụ thuộc registry.

Do đó, mã ứng dụng không nên tự giả định mọi registry đều hiểu `UP`, `DOWN` hoặc `OUT_OF_SERVICE` theo cùng một cách. Việc ép kiểu kết quả sang enum riêng của Eureka khi ứng dụng có thể chạy với Consul sẽ tạo phụ thuộc backend và có thể gây lỗi runtime.

Trước khi gọi `setStatus()`, cần kiểm tra tài liệu và implementation của đúng phiên bản Spring Cloud đang dùng. Một số thao tác có thể được hỗ trợ có giới hạn hoặc có hành vi riêng theo backend.

## 3. Các trạng thái của Eureka

Eureka dùng mô hình trạng thái instance riêng. Những giá trị thường gặp trong `InstanceInfo.InstanceStatus` gồm:

| Eureka status | Ý nghĩa khái quát |
|---|---|
| `UP` | Instance đang hoạt động và được xem là có thể phục vụ |
| `DOWN` | Instance được đánh dấu không hoạt động |
| `STARTING` | Instance đang trong quá trình khởi động |
| `OUT_OF_SERVICE` | Instance tạm thời không phục vụ traffic |
| `UNKNOWN` | Trạng thái chưa xác định |

Đây là vocabulary của Eureka, không phải danh sách trạng thái chuẩn của Spring Cloud Commons.

Eureka Client đăng ký instance với Eureka Server và duy trì registration thông qua heartbeat/lease. Trạng thái có thể được cập nhật từ phía client và được truyền đến registry theo cơ chế Eureka. Các health indicator và status propagation có thể ảnh hưởng trạng thái mà Eureka công bố.

### 3.1. Dùng OUT_OF_SERVICE để drain instance

Một tình huống phổ biến là triển khai phiên bản mới hoặc bảo trì một instance. Instance vẫn cần tồn tại trong một khoảng thời gian để hoàn tất request đang xử lý, nhưng không nên nhận request mới.

Với Eureka, `OUT_OF_SERVICE` thường được dùng để biểu thị instance tạm ngừng phục vụ. Consumer và các thành phần discovery cần áp dụng quy tắc lọc trạng thái phù hợp để không chọn instance đó cho request mới.

Luồng drain minh họa:

1. Instance được chuyển sang trạng thái không nhận traffic mới.
2. Trạng thái `OUT_OF_SERVICE` được cập nhật lên Eureka.
3. Consumer nhận dữ liệu registry mới theo chu kỳ refresh.
4. Load balancer ngừng chọn instance sau khi dữ liệu có hiệu lực.
5. Request đang xử lý hoàn tất.
6. Instance được deregister và dừng.

Việc đổi trạng thái không tự hủy các kết nối HTTP đang tồn tại. Graceful shutdown và connection draining vẫn phải được cấu hình riêng ở ứng dụng, HTTP server hoặc hạ tầng triển khai.

### 3.2. Trạng thái có thể bị ảnh hưởng bởi health integration

Nếu ứng dụng dùng health integration để đồng bộ trạng thái Spring Boot với Eureka, trạng thái có thể chịu tác động từ health indicator hoặc lifecycle event. Một thay đổi thủ công có thể không giữ nguyên nếu cơ chế health/status khác tiếp tục cập nhật trạng thái.

Vì vậy, cần xác định nguồn có quyền quyết định cuối cùng:

- Ứng dụng tự gọi cập nhật status?
- Health indicator của Spring Boot?
- Eureka Client lifecycle?
- Cấu hình hoặc automation triển khai?

Tránh để nhiều cơ chế cùng cập nhật trạng thái mà không có thứ tự ưu tiên rõ ràng.

## 4. Trạng thái và health của Consul

Consul biểu diễn sức khỏe service thông qua các health check gắn với registration. Các trạng thái health check thường gặp là:

| Consul check status | Ý nghĩa |
|---|---|
| `passing` | Check thành công |
| `warning` | Check có cảnh báo |
| `critical` | Check thất bại nghiêm trọng |

Service còn có cơ chế **maintenance mode** ở cấp service. Khi service được đưa vào maintenance, Consul có thể loại nó khỏi các kết quả truy vấn thông thường tùy API và cách truy vấn. Maintenance là cơ chế vận hành của Consul, không nên coi là một health check result thông thường.

### 4.1. Health được tính từ các check

Một service có thể gắn nhiều check, ví dụ:

- HTTP check gọi endpoint health của ứng dụng.
- TCP check xác nhận port có thể kết nối.
- TTL check được cập nhật bởi một tiến trình bên ngoài.
- Check khác do agent hoặc môi trường triển khai quản lý.

Trạng thái service trong truy vấn health được tổng hợp từ các check liên quan theo quy tắc của Consul. Nếu một check quan trọng chuyển sang `critical`, service có thể không còn xuất hiện trong truy vấn chỉ lấy instance khỏe.

Do đó, Consul không có nghĩa vụ diễn giải mọi chuỗi status mà một ứng dụng gửi qua `ServiceRegistry.setStatus()` thành cùng một trạng thái như Eureka. Cơ chế health check và maintenance của Consul có semantics riêng.

### 4.2. OUT_OF_SERVICE và maintenance

Một số phiên bản Spring Cloud Consul tích hợp trạng thái `OUT_OF_SERVICE` với cơ chế service maintenance của Consul. Cách xử lý cụ thể cần được kiểm tra theo phiên bản implementation đang dùng.

Không nên suy ra rằng các giá trị Eureka như `STARTING`, `DOWN` hoặc `UNKNOWN` đều có chuyển đổi một-một sang Consul. Nếu cần phân biệt các trạng thái đó, ứng dụng phải định nghĩa cách ánh xạ riêng, có thể dựa trên health check, maintenance hoặc metadata tùy mục tiêu.

## 5. Vì sao trạng thái không chuyển đổi một-một giữa các registry?

Eureka và Consul giải quyết cùng bài toán khám phá service nhưng mô hình quản lý trạng thái khác nhau:

- Eureka có enum trạng thái instance được công bố cùng registration.
- Consul tổng hợp kết quả health check và cung cấp maintenance mode cho service.
- Một registry có thể biểu diễn trạng thái ở cấp instance; registry khác có thể biểu diễn kết quả ở cấp check rồi tổng hợp ở cấp service.
- Cách consumer lọc instance cũng phụ thuộc API truy vấn và cấu hình của discovery client.

Bảng dưới đây là gợi ý ánh xạ theo ý nghĩa, không phải chuyển đổi tự động do Spring Cloud Commons đảm bảo:

| Trạng thái nghiệp vụ | Eureka gợi ý | Consul gợi ý | Giới hạn |
|---|---|---|---|
| Đang khởi động | `STARTING` | Chưa đánh dấu passing cho đến khi readiness đạt | Consul không có enum STARTING tương đương trong health check |
| Sẵn sàng nhận traffic | `UP` | Các check cần thiết đều `passing` | Cần cấu hình check và truy vấn healthy instances |
| Tạm ngừng nhận traffic | `OUT_OF_SERVICE` | Maintenance mode | Phụ thuộc cách Spring Cloud Consul triển khai maintenance |
| Không khỏe | `DOWN` | Check chuyển `critical` | `DOWN` không phải tên trạng thái health check của Consul |
| Chưa xác định | `UNKNOWN` | Chưa có check hoặc trạng thái check chưa đủ dữ liệu | Không có chuyển đổi tương đương trực tiếp |

Không nên ánh xạ `warning` của Consul thành `UP` một cách mặc định. Một warning có thể vẫn cho phép traffic trong chính sách này nhưng cần cảnh báo trong chính sách khác. Quyết định phụ thuộc mức độ nghiêm trọng của check và yêu cầu nghiệp vụ.

Tương tự, `DOWN` của Eureka không tự động tương đương mọi trường hợp `critical` của Consul. Cần xem lý do health check thất bại, chính sách loại instance và cách consumer truy vấn.

## 6. Các chuyển đổi trạng thái thường gặp

Trạng thái cần phản ánh lifecycle của instance. Một mô hình nghiệp vụ đơn giản có thể dùng các trạng thái nội bộ:

- `STARTING`: tiến trình đang khởi tạo.
- `ACCEPTING_TRAFFIC`: ứng dụng sẵn sàng nhận request.
- `DRAINING`: ngừng nhận request mới, hoàn tất request đang xử lý.
- `FAILED`: ứng dụng không còn đáp ứng điều kiện phục vụ.
- `STOPPED`: instance đã dừng và registration cần được loại bỏ.

Đây là mô hình do ứng dụng định nghĩa, không phải enum của Spring Cloud. Adapter cho Eureka hoặc Consul sẽ chuyển các trạng thái nội bộ sang vocabulary mà backend hỗ trợ.

### 6.1. STARTING sang ACCEPTING_TRAFFIC

Một instance chỉ nên được công bố là sẵn sàng sau khi:

1. Application context đã khởi tạo.
2. Cấu hình và dependency bắt buộc đã sẵn sàng.
3. Server đã lắng nghe trên endpoint được công bố.
4. Readiness check đạt điều kiện.
5. Registry/discovery integration đã đăng ký endpoint hợp lệ.

Nếu đăng ký sớm hơn readiness, consumer có thể tìm thấy instance nhưng request nhận lỗi trong thời gian khởi động.

### 6.2. ACCEPTING_TRAFFIC sang DRAINING

Khi deploy hoặc bảo trì:

1. Chuyển instance sang trạng thái không nhận request mới.
2. Gửi thay đổi đến registry theo cơ chế backend.
3. Chờ trạng thái mới lan đến consumer và load balancer.
4. Hoàn tất request đang xử lý trong giới hạn graceful shutdown.
5. Deregister instance.

Thời gian chờ cần dựa trên refresh interval, cache, thời gian request tối đa và connection draining. Không thể giả định mọi consumer đều nhận trạng thái mới ngay sau lời gọi `setStatus()`.

### 6.3. FAILED sang phục hồi

Khi instance phục hồi:

1. Xác nhận nguyên nhân lỗi đã được xử lý.
2. Kiểm tra readiness và dependency bắt buộc.
3. Đưa health check về trạng thái đạt.
4. Xóa maintenance hoặc cập nhật status theo backend.
5. Xác minh consumer đã nhìn thấy instance khỏe.
6. Theo dõi request thực tế trước khi kết luận instance đã phục vụ ổn định.

Không nên chuyển instance sang UP chỉ vì tiến trình đã khởi động lại. Tiến trình có thể sống nhưng database, message broker hoặc dependency quan trọng vẫn chưa sẵn sàng.

### 6.4. Dừng instance

`deregister()` và `setStatus()` là hai thao tác khác nhau:

- `setStatus()` thay đổi trạng thái của một registration đang tồn tại, nếu implementation hỗ trợ.
- `deregister()` yêu cầu loại bỏ registration hoặc ngừng công bố instance.

Đặt status thành `DOWN` không nhất thiết xóa bản ghi. Ngược lại, deregister không phải là một trạng thái health. Sau khi registration bị xóa, việc gọi `getStatus()` với registration đó có thể không còn ý nghĩa hoặc phụ thuộc implementation.

## 7. Ví dụ thiết kế lớp ánh xạ trạng thái

Không nên để mã nghiệp vụ gọi trực tiếp chuỗi trạng thái của Eureka hoặc Consul ở nhiều nơi. Hãy biểu diễn ý định nghiệp vụ bằng enum nội bộ và tập trung ánh xạ tại một adapter.

Ví dụ mô hình nội bộ:

~~~java
public enum ServiceAvailability {
    STARTING,
    ACCEPTING_TRAFFIC,
    DRAINING,
    FAILED,
    STOPPED
}
~~~

Một adapter có thể có trách nhiệm:

~~~java
public interface RegistryStatusPublisher {

    void publishAvailability(
        ServiceAvailability availability
    );
}
~~~

Implementation cho từng backend tự quyết định cách biểu diễn:

- Eureka adapter ánh xạ sang trạng thái instance mà Eureka hỗ trợ.
- Consul adapter cập nhật health check hoặc maintenance theo cách phù hợp.
- Backend khác có thể không hỗ trợ một số trạng thái và phải trả về kết quả không hỗ trợ rõ ràng.

Ví dụ bảng ánh xạ có thể đặt trong cấu hình hoặc mã adapter:

~~~text
ACCEPTING_TRAFFIC -> Eureka UP
DRAINING          -> Eureka OUT_OF_SERVICE
FAILED            -> Eureka DOWN

ACCEPTING_TRAFFIC -> Consul checks passing
DRAINING          -> Consul service maintenance
FAILED            -> Consul checks critical
~~~

Đây là quy ước minh họa. Cần xác minh API và hành vi của đúng implementation, đặc biệt đối với trạng thái STARTING, UNKNOWN và cách Consul health check được cập nhật. Không coi bảng trên là cấu hình tự động có sẵn của Spring Cloud.

Adapter nên xử lý rõ trường hợp không hỗ trợ:

- Từ chối yêu cầu bằng lỗi có ý nghĩa.
- Ghi log status không được hỗ trợ.
- Phát metric để phát hiện trạng thái chuyển đổi thất bại.
- Không âm thầm chuyển mọi trạng thái lạ thành UP.

## 8. Giới hạn khi chuyển đổi Eureka sang Consul

Chuyển backend không chỉ là đổi dependency và địa chỉ registry. Cần xem lại mô hình trạng thái, health check và hành vi truy vấn.

### 8.1. Những gì có thể giữ lại

Thông tin có thể được ánh xạ tương đối trực tiếp:

- Service ID.
- Instance ID, nếu có quy tắc định danh ổn định.
- Host và port có thể truy cập từ consumer.
- Metadata không nhạy cảm như zone, version hoặc nhóm triển khai.
- Ý định nghiệp vụ như sẵn sàng nhận traffic hay đang drain.

### 8.2. Những gì cần thiết kế lại

Các nội dung sau không nên sao chép nguyên trạng:

- Eureka enum status sang Consul check status.
- Heartbeat/lease interval sang Consul health check interval.
- Cách Eureka client công bố health sang cách Consul Agent chạy check.
- Cách consumer lấy danh sách instance và lọc trạng thái.
- Maintenance/deregistration behavior.
- Cache, refresh và thời gian hội tụ.
- Quyền đọc/ghi registry và credential của agent/client.

### 8.3. Bảng chuyển đổi gợi ý

| Nguồn Eureka | Mục tiêu Consul | Việc cần làm |
|---|---|---|
| `UP` | Health checks `passing` | Cấu hình check xác nhận readiness |
| `OUT_OF_SERVICE` | Maintenance mode | Kiểm tra tích hợp maintenance của phiên bản đang dùng |
| `DOWN` | Check `critical` | Xác định phép probe phản ánh lỗi phục vụ |
| `STARTING` | Chưa passing | Chỉ cho check đạt sau khi ứng dụng ready |
| `UNKNOWN` | Chưa có kết luận | Giữ trạng thái chưa sẵn sàng cho đến khi có kết quả đáng tin cậy |

Khi chuyển đổi, cần thử cả hai chiều: instance đăng ký mới và instance bị loại bỏ. Một cấu hình chỉ kiểm tra đăng ký thành công nhưng không kiểm tra deregistration hoặc maintenance sẽ dễ để lại bản ghi cũ trong catalog.

## 9. Giới hạn khi chuyển đổi Consul sang Eureka

Chiều ngược lại cũng cần chính sách riêng.

| Nguồn Consul | Mục tiêu Eureka gợi ý | Giới hạn |
|---|---|---|
| Checks `passing` | `UP` | Cần xác định tập check nào quyết định trạng thái sẵn sàng |
| Checks `warning` | `UP` hoặc `OUT_OF_SERVICE` theo chính sách | Eureka không có trạng thái warning tương đương |
| Checks `critical` | `DOWN` hoặc `OUT_OF_SERVICE` theo chính sách | Phải xác định mức độ lỗi và tác động đến traffic |
| Maintenance mode | `OUT_OF_SERVICE` | Cần chuyển đổi maintenance rõ ràng |
| Chưa có check | `STARTING` hoặc `UNKNOWN` theo chính sách | Không nên tự xem là UP |

Nếu Consul có nhiều check, cần xác định check nào là bắt buộc. Ví dụ, một check monitoring không quan trọng có thể warning trong khi API vẫn phục vụ được; chuyển mọi warning thành DOWN có thể loại instance quá mức cần thiết.

Ngược lại, nếu check database là điều kiện bắt buộc để xử lý nghiệp vụ, trạng thái passing của một HTTP endpoint đơn giản có thể chưa đủ chứng minh service sẵn sàng.

## 10. Các giới hạn cần kiểm tra trước khi gọi setStatus()

Trước khi dùng `ServiceRegistry.setStatus()`, cần xác nhận:

1. Implementation đang inject là Eureka, Consul hay backend khác.
2. Registration object có đúng kiểu mà implementation yêu cầu không.
3. Chuỗi status có được hỗ trợ không và có phân biệt chữ hoa/chữ thường không.
4. Việc đổi status có được ghi vào registry ngay hay chỉ thay đổi trạng thái cục bộ trước.
5. Health integration có thể ghi đè status thủ công không.
6. Consumer có lọc trạng thái đó khỏi danh sách instance không.
7. LoadBalancer có đang dùng cache cũ không.
8. Có cần deregister sau khi drain hay chỉ đổi status.
9. Gọi `getStatus()` trả về kiểu dữ liệu nào trong implementation hiện tại.
10. Backend có hỗ trợ thao tác tương ứng hay không.

Đừng dựa vào tên method chung để suy ra rằng mọi thao tác đều có cùng semantics hoặc cùng thời gian hoàn tất trên tất cả registry.

## 11. Kiểm thử chuyển đổi trạng thái

Kiểm thử nên xác nhận cả trạng thái registry và hành vi request thực tế.

| Kịch bản | Điều cần xác minh |
|---|---|
| Instance khởi động | Đăng ký đúng service ID, endpoint và metadata |
| Readiness chưa đạt | Consumer không chọn instance chưa sẵn sàng |
| Chuyển sang drain | Request mới dần ngừng được gửi đến instance |
| Request đang xử lý | Request hiện tại có đủ thời gian hoàn tất |
| Health check thất bại | Registry cập nhật trạng thái theo threshold đã cấu hình |
| Instance phục hồi | Health check đạt và instance xuất hiện lại trong tập có thể phục vụ |
| Deregister | Registration biến mất theo thời gian dự kiến |
| Registry mất kết nối | Consumer xử lý cache và lỗi refresh đúng chính sách |
| Chuyển Eureka sang Consul | Trạng thái nghiệp vụ giữ đúng ý nghĩa sau khi ánh xạ |
| Chuyển Consul sang Eureka | Warning, critical và maintenance được xử lý theo quy tắc đã chọn |

Không chỉ kiểm tra `getStatus()` ngay sau `setStatus()`. Hãy kiểm tra thêm kết quả truy vấn instance từ phía consumer và gửi request thử. Giá trị status được trả về có thể khác với việc instance có thực sự được LoadBalancer chọn hay không.

## 12. Quan sát và xử lý lỗi chuyển trạng thái

Khi trạng thái không chuyển như mong đợi, kiểm tra theo từng lớp:

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `setStatus()` báo lỗi | Status không hợp lệ hoặc implementation không hỗ trợ | Kiểm tra vocabulary và version backend |
| `getStatus()` khác giá trị vừa đặt | Health integration hoặc backend đã cập nhật trạng thái khác | Kiểm tra nguồn cập nhật và thời điểm |
| Registry đã đổi nhưng consumer vẫn chọn instance | Cache hoặc refresh chưa hội tụ; bộ lọc status khác nhau | Kiểm tra instance supplier, refresh và query semantics |
| Instance vẫn tồn tại sau khi đặt DOWN | Status không đồng nghĩa deregistration | Gọi lifecycle deregister khi cần loại registration |
| Instance biến mất quá sớm | Health check hoặc threshold quá nhạy | Điều chỉnh check interval, timeout và threshold |
| Chuyển registry làm mất trạng thái | Không có mapping tương đương hoặc không chuyển health check | Xây dựng adapter và chính sách chuyển đổi rõ ràng |

Nên ghi nhận service ID, instance ID, trạng thái trước/sau, backend, thời điểm thay đổi và kết quả propagation. Không ghi credential hoặc secret vào log.

## 13. Khuyến nghị thiết kế

- Dùng một mô hình availability nội bộ có ý nghĩa nghiệp vụ rõ ràng.
- Tạo adapter riêng cho từng registry để ánh xạ status và health.
- Chỉ sử dụng trạng thái mà backend thực sự hỗ trợ.
- Không chuyển chuỗi status trực tiếp giữa Eureka và Consul.
- Phân biệt đổi status, health check và deregistration.
- Dùng readiness để xác định thời điểm instance có thể nhận traffic.
- Dùng drain và graceful shutdown khi triển khai hoặc bảo trì.
- Kiểm tra hành vi của consumer và LoadBalancer sau mỗi thay đổi trạng thái.
- Định nghĩa rõ cách xử lý trạng thái không hỗ trợ, warning và unknown.
- Kiểm thử quá trình chuyển đổi trước khi thay registry trong môi trường production.

## 14. Ghi nhớ

- `ServiceRegistry` cung cấp thao tác `register`, `deregister`, `setStatus` và `getStatus`, nhưng không chuẩn hóa toàn bộ vocabulary trạng thái.
- Eureka dùng trạng thái instance như `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE` và `UNKNOWN`.
- Consul dựa vào health check với các kết quả như `passing`, `warning`, `critical`, đồng thời có maintenance mode ở cấp service.
- `OUT_OF_SERVICE` có thể được ánh xạ sang maintenance trong tích hợp Consul phù hợp, nhưng không có mapping một-một cho mọi trạng thái.
- `setStatus()` không thay thế `deregister()`; health check cũng không đồng nghĩa với registration.
- Cache, refresh và health integration có thể làm trạng thái quan sát được khác với giá trị vừa yêu cầu cập nhật.
- Khi chuyển registry, hãy dùng mô hình trạng thái nghiệp vụ và adapter riêng cho từng backend.

Hiểu rõ trạng thái được hỗ trợ và giới hạn chuyển đổi giúp ứng dụng Spring Cloud tránh phụ thuộc vào vocabulary riêng của một registry. Điều này đặc biệt quan trọng khi triển khai bảo trì, graceful shutdown, health check và di chuyển giữa Eureka với Consul.
