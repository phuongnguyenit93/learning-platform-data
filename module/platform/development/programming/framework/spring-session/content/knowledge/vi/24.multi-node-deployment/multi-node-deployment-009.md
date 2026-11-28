# Tắt có trật tự và hoàn tất việc lưu phiên trước khi dừng

Trong hệ thống Spring Session chạy nhiều instance, một node có thể được thay thế khi triển khai phiên bản mới, scale in hoặc bảo trì. Nếu tiến trình bị dừng ngay khi request đang xử lý, thay đổi `HttpSession` của request đó có thể chưa được ghi vào Redis hoặc JDBC. Node mới hoặc node còn lại khi nhận request tiếp theo sẽ đọc trạng thái cũ.

Tắt có trật tự (graceful shutdown) giúp node ngừng nhận request mới, chờ các request đang chạy hoàn tất trong một khoảng thời gian giới hạn, rồi mới đóng web server và các tài nguyên phụ thuộc. Với Spring Session, mục tiêu là để filter và repository có cơ hội hoàn tất việc lưu session trước khi ứng dụng đóng kết nối tới kho dữ liệu.

Graceful shutdown không phải lệnh “ghi tất cả session trong bộ nhớ ra kho dữ liệu”. Session được lưu theo vòng đời request và chính sách của repository. Vì vậy, cách triển khai đúng là drain traffic, để request đang hoạt động hoàn tất, giữ Redis/JDBC và connection pool sẵn sàng trong suốt quá trình đó, rồi mới kết thúc tiến trình.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao request đang chạy có thể chưa lưu xong session khi node bị dừng.
- Bật graceful shutdown cho ứng dụng Spring Boot.
- Phối hợp readiness, load balancer, Kubernetes và thời gian chờ dừng.
- Đặt ngân sách timeout đủ cho request đang hoạt động và thao tác lưu session.
- Giữ repository, Redis/JDBC và connection pool hoạt động đến khi request drain hoàn tất.
- Kiểm thử việc cập nhật session trước, trong và sau khi một node dừng.

## 1. Điều gì xảy ra với session khi một node dừng?

Trong ứng dụng Servlet, `SessionRepositoryFilter` bọc request và response để ánh xạ `HttpSession` sang Spring Session repository. Controller có thể gọi `setAttribute()` trong lúc xử lý request, nhưng việc ghi dữ liệu vào repository thường diễn ra khi response được commit hoặc hoàn tất theo cơ chế của filter và repository.

Ví dụ:

~~~java
@PostMapping("/checkout/step")
public String updateStep(
        HttpServletRequest request,
        @RequestParam String step) {

    request.getSession().setAttribute("checkoutStep", step);
    return "redirect:/checkout";
}
~~~

Khi method gọi `setAttribute`, thay đổi được áp dụng vào session mà request đang sử dụng. Repository có thể chưa ghi xong vào Redis/JDBC ở chính thời điểm dòng code đó trả về. Filter cần hoàn tất quá trình lưu khi response được commit.

Nếu tiến trình bị kết thúc cưỡng bức giữa lúc controller đang chạy hoặc trước khi thao tác lưu hoàn tất, request có thể không ghi được thay đổi cuối cùng. Khi request tiếp theo được định tuyến tới node khác, repository trả về phiên với dữ liệu đã lưu trước đó.

Một session đã được lưu thành công trước đó vẫn tồn tại trong kho dữ liệu dùng chung sau khi node dừng. Không cần node cũ “xuất” toàn bộ session của người dùng khi shutdown. Điều cần bảo vệ là các thay đổi của request còn đang xử lý và các tác vụ lưu đang diễn ra.

## 2. Vòng đời request và thời điểm lưu session

Luồng Servlet điển hình:

~~~mermaid
sequenceDiagram
    participant Client
    participant Server as Web server
    participant Filter as SessionRepositoryFilter
    participant App as Controller/Service
    participant Repo as Spring Session repository
    participant Store as Redis/JDBC
    Client->>Server: Request
    Server->>Filter: Dispatch request
    Filter->>Repo: Tải session theo ID
    Repo->>Store: Đọc session
    Store-->>Repo: Dữ liệu đã lưu
    Repo-->>Filter: HttpSession
    Filter->>App: Chạy filter chain/controller
    App->>Filter: setAttribute và tạo response
    Filter->>Repo: Lưu thay đổi khi response commit
    Repo->>Store: Ghi session
    Store-->>Repo: Hoàn tất
    Repo-->>Filter: Lưu xong
    Filter-->>Server: Commit response
    Server-->>Client: HTTP response
~~~

Chi tiết thời điểm lưu phụ thuộc repository và `FlushMode`. Với chế độ lưu theo response/request, filter cần hoàn tất bước lưu trước khi response được gửi đi. Nếu repository dùng chế độ flush ngay, một số thay đổi có thể được gửi sớm hơn, nhưng điều đó không thay thế việc drain request và không bảo đảm mọi thao tác nghiệp vụ trở thành nguyên tử.

Với WebFlux, `WebSession` được quản lý theo lifecycle reactive của request. Các thao tác repository phải được nối vào chuỗi reactive để framework theo dõi việc hoàn tất hoặc lỗi. Không gọi `subscribe()` tách rời rồi giả định công việc sẽ hoàn tất trước khi tiến trình dừng.

## 3. Graceful shutdown khác gì dừng cưỡng bức?

| Cách dừng | Hành vi | Tác động tới request và session |
|---|---|---|
| Graceful shutdown | Ngừng nhận request mới và chờ request đang hoạt động hoàn tất trong thời gian giới hạn | Request có cơ hội hoàn tất filter chain và lưu session |
| Dừng cưỡng bức | Tiến trình bị kết thúc ngay hoặc hết thời gian chờ rồi bị kill | Request đang chạy có thể bị cắt giữa chừng; thay đổi session chưa lưu có thể mất |
| JVM shutdown hook không có drain | Chỉ chạy các hook/cleanup khi tiến trình kết thúc | Không tự bảo đảm web server đã ngừng nhận request hoặc session đã flush |

Graceful shutdown chỉ có tác dụng nếu tín hiệu dừng được gửi theo cách tiến trình có thể xử lý, chẳng hạn `SIGTERM` hoặc lệnh stop của container. `SIGKILL`, kill cưỡng bức hoặc máy chủ mất điện không cho ứng dụng cơ hội chạy lifecycle shutdown.

Một request kéo dài hơn thời gian chờ graceful shutdown có thể bị kết thúc khi timeout hết. Vì thế cần có timeout request, timeout shutdown và thời gian dừng của nền tảng được phối hợp.

## 4. Bật graceful shutdown trong Spring Boot

Với các dòng Spring Boot hỗ trợ graceful shutdown, có thể cấu hình trong `application.yml`:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Ý nghĩa:

- `server.shutdown: graceful` yêu cầu web server ngừng nhận request mới và chờ các request đang hoạt động hoàn tất khi ứng dụng dừng.
- `spring.lifecycle.timeout-per-shutdown-phase` đặt thời gian tối đa cho mỗi phase của quá trình dừng các bean `SmartLifecycle`.

Chọn timeout dựa trên thời gian xử lý request thực tế, không sao chép con số mẫu vào production. Nếu request thông thường hoàn tất trong vài giây nhưng một số request có thể chạy lâu hơn, hãy xác định rõ request nào được phép tiếp tục và request nào phải có timeout riêng.

Graceful shutdown của web server có sẵn trong Spring Boot từ các phiên bản hỗ trợ tính năng này; cần xác minh cấu hình theo đúng phiên bản Boot và server đang dùng. Các server khác nhau có chi tiết triển khai khác nhau, nhưng ứng dụng vẫn cần kiểm thử với container thực tế.

Không nên chỉ thêm `@PreDestroy` để “lưu session”. `@PreDestroy` phù hợp cho việc giải phóng tài nguyên của bean, nhưng không có danh sách đầy đủ các session đang được người dùng sử dụng và không thay thế cơ chế hoàn tất request của `SessionRepositoryFilter`.

## 5. Drain traffic trước khi node biến mất

Graceful shutdown ở ứng dụng xử lý phần request đã đi vào node. Hệ thống điều phối còn phải ngừng định tuyến request mới tới node sắp dừng.

Một quy trình drain thường gồm:

1. Đánh dấu node không còn sẵn sàng nhận traffic mới.
2. Chờ load balancer, service discovery hoặc service mesh cập nhật endpoint.
3. Gửi tín hiệu dừng tới ứng dụng.
4. Web server ngừng nhận request mới và chờ request đang hoạt động.
5. Filter hoàn tất lưu session; repository dùng Redis/JDBC còn kết nối được.
6. Spring context đóng các bean và connection pool sau khi lifecycle cần thiết đã dừng.
7. Tiến trình kết thúc trong thời gian cho phép của nền tảng.

Nếu bước 1 và 2 không được thực hiện, load balancer có thể tiếp tục gửi request tới node trong lúc node đang shutdown. Một số request có thể thất bại khi server đã ngừng nhận kết nối.

Readiness và liveness có mục đích khác nhau:

- Readiness cho biết instance có nên nhận traffic hay không.
- Liveness giúp nền tảng quyết định tiến trình có cần khởi động lại hay không.

Không dùng liveness để đánh dấu node đang drain. Một node đang dừng có thể vẫn khỏe nhưng không còn sẵn sàng nhận request mới.

## 6. Ví dụ triển khai với Kubernetes

Kubernetes thực hiện quy trình kết thúc Pod: Pod được đánh dấu đang terminating, hook `preStop` được chạy nếu có, sau đó container nhận tín hiệu dừng; hết `terminationGracePeriodSeconds` thì container có thể bị kill cưỡng bức. Thời gian chạy `preStop` cũng nằm trong ngân sách grace period.

Ví dụ cấu hình minh họa:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 70
      containers:
        - name: spring-session-app
          image: example/spring-session-app:1.0
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

Các con số chỉ là ví dụ. Lệnh `sleep 5` tạo khoảng đệm để thay đổi endpoint có thời gian lan truyền tới các thành phần định tuyến; nó không tự đánh dấu ứng dụng là unready và không bảo đảm mọi load balancer đã ngừng gửi request.

Ngân sách `terminationGracePeriodSeconds` phải lớn hơn tổng thời gian dự kiến cho hook `preStop`, thời gian drain request của Spring Boot và phần đệm cho việc đóng tài nguyên. Ví dụ trên có 70 giây tổng ngân sách; nếu hook dùng 5 giây và Spring lifecycle có thể chờ 45 giây, phần còn lại dành cho đóng tài nguyên và sai số vận hành.

Trong production:

- Bảo đảm readiness probe phản ánh trạng thái nhận traffic.
- Kiểm tra cách cluster/service mesh loại endpoint khi Pod terminating.
- Đặt `preStop` delay theo thời gian propagation đo được; không mặc định 5 giây phù hợp mọi cụm.
- Đặt `terminationGracePeriodSeconds` đủ dài cho request dài nhất được phép drain.
- Kiểm thử khi scale down và rolling update, không chỉ khi dừng Pod thủ công.

## 7. Phối hợp timeout của request và timeout shutdown

Timeout shutdown phải đủ dài để request đang hoạt động hoàn tất, nhưng không nên vô hạn. Cần thống nhất:

| Timeout | Mục đích |
|---|---|
| Client/request timeout | Giới hạn thời gian client hoặc gateway chờ một request |
| Application request timeout | Giới hạn công việc một handler/service được phép chạy |
| Graceful shutdown timeout | Thời gian web server chờ request đang hoạt động |
| Platform termination grace period | Tổng thời gian nền tảng cho hook, drain và kết thúc tiến trình |
| Redis/JDBC timeout | Giới hạn thời gian thao tác lưu session chờ kho dữ liệu |

Nếu timeout database dài hơn toàn bộ thời gian shutdown còn lại, thao tác lưu session có thể bị cắt khi nền tảng kill tiến trình. Nếu timeout request quá dài và không có giới hạn, một request bị treo có thể giữ node trong trạng thái terminating cho tới khi hết grace period.

Hãy xác định ngân sách theo quan hệ:

~~~text
terminationGracePeriod
  >= preStop / endpoint propagation
   + graceful request drain
   + bean/resource shutdown
   + safety margin
~~~

Các khoảng thời gian không nhất thiết cộng tuyến tính trong mọi nền tảng, nhưng đây là cách lập ngân sách an toàn để tránh cấu hình grace period ngắn hơn thời gian ứng dụng cần.

## 8. Giữ repository và kho dữ liệu hoạt động đến cuối quá trình drain

Một request chỉ có thể lưu session nếu repository và kho dữ liệu còn hoạt động. Khi shutdown:

- Không đóng `DataSource`, connection pool hoặc Redis connection factory trước khi web server hoàn tất drain.
- Không dừng dịch vụ Redis/database dùng chung chỉ vì một application node đang được thay thế.
- Không xóa namespace Redis hoặc truncate bảng Spring Session trong hook shutdown.
- Không đóng scheduler hoặc executor mà request đang cần trước khi request hoàn tất.
- Nếu có bean tự quản lý background task, dừng nhận công việc mới rồi chờ công việc đang chạy theo lifecycle có timeout.

Trong Spring context, các bean có lifecycle được dừng theo thứ tự phase. Nếu ứng dụng tự viết `SmartLifecycle`, hãy xác định phase và callback `stop(Runnable)` để thông báo khi dừng hoàn tất. Không chặn vô hạn trong callback và không giả định thứ tự giữa các bean nếu chưa cấu hình hoặc kiểm thử.

Với `@PreDestroy`, chỉ giải phóng tài nguyên thuộc bean khi các thành phần sử dụng nó đã dừng. Không dùng hook này để duyệt tất cả session và gọi save thủ công: repository quản lý session theo request, còn một session đang hoạt động có thể vẫn được một request khác cập nhật.

## 9. Session đã lưu và session đang được cập nhật

Phân biệt hai trường hợp:

**Session đã được lưu xong:** Dữ liệu nằm trong Redis/JDBC. Khi node dừng, node khác tiếp tục đọc session theo ID. Việc node cũ kết thúc không làm mất session nếu kho dùng chung vẫn hoạt động và TTL chưa hết.

**Session đang được request cập nhật:** Request đã thay đổi object session nhưng thao tác lưu cuối request chưa hoàn tất. Node cần drain request để filter/repository ghi dữ liệu. Nếu request bị kill hoặc thao tác lưu thất bại, thay đổi mới nhất có thể không tồn tại trong kho.

Vì vậy, không cần “flush tất cả session” khi tắt node. Cần hoàn tất những request đang sở hữu thay đổi chưa lưu và không đóng kho dữ liệu quá sớm.

Nếu dùng `FlushMode.IMMEDIATE`, một số thay đổi có thể được ghi sớm hơn theo semantics repository. Điều này có thể giảm cửa sổ chưa lưu, nhưng không bảo đảm mọi quy trình nhiều bước đều nguyên tử và không loại bỏ nhu cầu graceful shutdown.

## 10. Request dài, streaming và tác vụ nền

Không phải mọi request đều kết thúc nhanh:

- Server-Sent Events hoặc streaming response có thể mở trong thời gian dài.
- WebSocket có vòng đời kết nối riêng, không giống request/response ngắn.
- Spring MVC async request có thể chờ `Callable`, `DeferredResult` hoặc tác vụ nền.
- Một handler có thể chờ dịch vụ ngoài hoặc xử lý file lớn.

Nếu các kết nối này giữ node hoạt động, graceful shutdown có thể chờ đến timeout. Cần định nghĩa chính sách riêng: ngừng tạo stream mới, gửi tín hiệu đóng cho client, hoàn tất hoặc hủy tác vụ có kiểm soát, và để client reconnect tới node còn lại.

Không đặt công việc nền dài hạn trong vòng đời của một HTTP request nếu công việc phải tiếp tục sau khi node bị thay thế. Đưa công việc vào queue bền vững hoặc workflow engine; request chỉ ghi nhận yêu cầu và trả mã theo dõi. Session có thể giữ mã tham chiếu để giao diện tra cứu tiến độ.

Đối với tác vụ nền cần dừng có trật tự, dùng cơ chế lifecycle phù hợp để ngừng nhận task mới, chờ task đang chạy hoặc chuyển giao quyền xử lý. Không giả định `server.shutdown=graceful` tự dừng mọi executor tùy chỉnh của ứng dụng.

## 11. Triển khai nhiều node mà không làm gián đoạn phiên

Trong rolling deployment, node mới và node cũ có thể cùng phục vụ traffic trong một khoảng thời gian. Để session tiếp tục hoạt động:

- Các node cùng dùng Redis/JDBC repository chung.
- Cookie name, path, domain, SameSite và cách phân giải session ID tương thích.
- Namespace, serializer, schema và timeout tương thích giữa các phiên bản.
- Node cũ được drain trước khi container bị kill.
- Node mới sẵn sàng nhận traffic trước khi giảm số node cũ xuống dưới năng lực phục vụ.

Không xóa session store trong quá trình deploy. Cũng không đổi serializer hoặc cấu trúc thuộc tính theo cách khiến node mới không đọc được session do node cũ tạo ra. Nếu có thay đổi định dạng, cần triển khai migration tương thích ngược hoặc chờ session cũ hết hạn theo kế hoạch.

Sticky session không thay thế repository dùng chung. Dù load balancer có thể ưu tiên một client về cùng node, khi node bị dừng client vẫn cần được phục vụ bởi node khác và đọc được phiên từ kho chung.

## 12. Kiểm thử graceful shutdown và việc lưu session

Kiểm thử cần chứng minh request đang chạy hoàn tất và thay đổi session có thể đọc được sau khi node dừng.

Một kịch bản tích hợp:

1. Khởi chạy hai instance ứng dụng cùng kết nối Redis hoặc JDBC repository.
2. Gửi request tới instance A để tạo session và nhận cookie.
3. Gửi request cập nhật một thuộc tính session; cố ý giữ request ở trạng thái đang chạy bằng test latch sau khi cập nhật nhưng trước khi response hoàn tất.
4. Gửi tín hiệu graceful shutdown tới instance A.
5. Xác minh instance A ngừng nhận request mới nhưng request đang chạy được phép hoàn tất trong timeout.
6. Đợi request kết thúc và xác nhận response thành công.
7. Gửi request tiếp theo với cùng cookie tới instance B.
8. Xác minh instance B đọc được giá trị mới đã được lưu.

Kiểm thử bổ sung:

| Tình huống | Kết quả mong đợi |
|---|---|
| Request kết thúc trong thời gian drain | Session được lưu và node dừng bình thường |
| Request vượt quá shutdown timeout | Nền tảng có thể kết thúc cưỡng bức; ứng dụng ghi nhận timeout và không tuyên bố request đã lưu |
| Redis/JDBC vẫn hoạt động trong drain | Thao tác lưu session hoàn tất |
| Kho session mất kết nối trong drain | Request lưu phiên báo lỗi; metric/log thể hiện rõ |
| Load balancer đã loại node | Request mới đi tới node còn sẵn sàng |
| Node còn lại đọc cookie cũ | Phiên đã lưu vẫn được tải thành công |
| Rolling deploy đổi phiên bản | Node mới đọc được session do node cũ tạo |

Không chỉ kiểm tra process đã exit. Hãy xác minh trạng thái session trong repository sau khi node cũ dừng, bằng request qua node còn lại hoặc API test phù hợp.

## 13. Quan sát quá trình shutdown

Nên theo dõi các mốc:

- Thời điểm nhận SIGTERM hoặc bắt đầu context close.
- Thời điểm readiness chuyển sang không nhận traffic.
- Thời điểm web server ngừng nhận request mới.
- Số request còn hoạt động và thời gian drain.
- Số request hoàn tất, timeout hoặc bị hủy.
- Lỗi ghi session vào Redis/JDBC trong giai đoạn shutdown.
- Thời gian đóng connection pool và kết thúc process.

Metric và log nên có instance ID, deployment version, correlation ID và tên phase. Không ghi session ID thô, cookie, token hoặc toàn bộ thuộc tính phiên.

Nếu shutdown thường xuyên chạm timeout, hãy điều tra request dài, streaming, pool cạn, repository chậm hoặc traffic chưa được drain. Chỉ tăng timeout có thể che giấu nguyên nhân và kéo dài thời gian rollout.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request cuối cùng mất thay đổi session | Node bị kill trước khi response/filter hoàn tất lưu | Bật graceful shutdown và tăng ngân sách drain phù hợp |
| Node dừng nhưng load balancer vẫn gửi request | Endpoint chưa được loại hoặc readiness không phản ánh drain | Phối hợp readiness, endpoint propagation và preStop |
| Session write lỗi khi shutdown | DataSource/Redis client bị đóng quá sớm hoặc store không khả dụng | Giữ repository và connection pool đến sau khi request drain |
| Pod bị SIGKILL trước khi app hoàn tất | `terminationGracePeriodSeconds` ngắn hơn tổng thời gian cần | Tính lại preStop + drain + cleanup + safety margin |
| Shutdown không bao giờ hoàn tất | Streaming, WebSocket hoặc async request tồn tại quá lâu | Đặt chính sách đóng kết nối, timeout và reconnect |
| `@PreDestroy` chạy nhưng session vẫn mất | Hook không thay thế lifecycle lưu session theo request | Để filter/repository hoàn tất; không dựa vào hook để flush mọi session |
| Node mới không đọc session cũ | Serializer, cookie hoặc schema không tương thích | Dùng rolling-compatible change và kiểm thử phiên bản hỗn hợp |
| Dừng node làm mất toàn bộ session | Dùng repository in-memory cục bộ thay vì store chia sẻ | Dùng Redis/JDBC hoặc repository bền vững phù hợp |

## 15. Checklist trước khi triển khai

- [ ] Bật `server.shutdown: graceful` trên phiên bản Spring Boot hỗ trợ.
- [ ] Đặt `spring.lifecycle.timeout-per-shutdown-phase` theo thời gian request thực tế.
- [ ] Readiness và load balancer ngừng gửi request mới tới node đang drain.
- [ ] Ngân sách termination của nền tảng lớn hơn thời gian hook, drain và đóng tài nguyên.
- [ ] Redis/JDBC repository và connection pool còn hoạt động đến khi request hoàn tất.
- [ ] Không dùng `@PreDestroy` để thay thế việc lưu session theo request.
- [ ] Có chính sách riêng cho streaming, WebSocket và async request dài.
- [ ] Tất cả node dùng chung store và cấu hình cookie/serializer tương thích.
- [ ] Có integration test gửi SIGTERM khi request đang cập nhật session.
- [ ] Đã xác minh node khác đọc được thay đổi session sau khi node cũ dừng.
- [ ] Có metric/log cho request drain, session write failure và shutdown timeout.
- [ ] Đã thử nghiệm scale down, rolling update và tình huống kho dữ liệu lỗi.

Tắt có trật tự giúp Spring Session hoàn tất các thao tác lưu gắn với request đang chạy trước khi node kết thúc. Hãy ngừng định tuyến request mới, bật graceful shutdown của Spring Boot, dành đủ thời gian drain và giữ repository cùng kết nối Redis/JDBC hoạt động tới cuối lifecycle. Session đã lưu trong kho dùng chung sẽ tiếp tục được node khác sử dụng; phần cần bảo vệ là thay đổi của request chưa hoàn tất. Kiểm thử bằng cách dừng một node giữa request cập nhật và xác minh node còn lại đọc được giá trị mới.
