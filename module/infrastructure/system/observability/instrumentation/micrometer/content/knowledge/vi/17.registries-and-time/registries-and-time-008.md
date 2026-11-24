# Ảnh hưởng của ứng dụng dừng, registry đóng hoặc đích nhận gián đoạn

Metrics của Micrometer trước hết tồn tại trong tiến trình ứng dụng. Mã instrumentation cập nhật Counter, Gauge, Timer hoặc meter khác; MeterRegistry giữ và chuyển các phép đo theo cơ chế của registry; exporter hoặc endpoint đưa dữ liệu đến hệ thống giám sát. Nếu ứng dụng dừng, registry bị đóng hoặc backend mất kết nối, một phần dữ liệu có thể không đến được nơi lưu trữ.

Điểm quan trọng là metrics phục vụ quan sát vận hành và thường có tính chất best-effort. MeterRegistry không phải hàng đợi sự kiện bền vững hay sổ cái giao dịch. Mức độ mất dữ liệu phụ thuộc vào mô hình pull hay push, loại registry, chu kỳ publish, khả năng retry/buffer của implementation và cách ứng dụng shutdown.

## 1. Theo dõi đường đi của một phép đo

Một phép đo đi qua nhiều thành phần trước khi có thể xuất hiện trên dashboard:

~~~mermaid
flowchart LR
    A["Mã ứng dụng"] --> B["Meter"]
    B --> C["MeterRegistry"]
    C --> D["Exporter hoặc scrape endpoint"]
    D --> E["Backend metrics"]
    E --> F["Dashboard và cảnh báo"]
    G["Ứng dụng dừng / registry close"] -.-> C
    H["Mạng hoặc backend gián đoạn"] -.-> D
~~~

Mỗi thành phần có một vai trò riêng:

- **Mã ứng dụng** ghi nhận sự kiện hoặc trạng thái. Nếu mã không cập nhật meter, registry không có dữ liệu mới để xuất.
- **MeterRegistry** giữ meter và các giá trị đo trong phạm vi vòng đời của registry.
- **Exporter hoặc endpoint** chuyển dữ liệu theo giao thức mà backend hỗ trợ.
- **Backend** tiếp nhận, lưu trữ, lập chỉ mục và cung cấp dữ liệu cho truy vấn.

Một lần gọi **increment()** thành công chỉ xác nhận meter trong tiến trình đã được cập nhật. Nó không chứng minh backend đã nhận dữ liệu. Tương tự, endpoint scrape trả dữ liệu không có nghĩa Prometheus đã lưu thành công mẫu đó; việc scrape và ghi dữ liệu là hai bước riêng.

## 2. Phân biệt registry pull và registry push

Cách ứng dụng tương tác với backend quyết định điều gì xảy ra khi đích nhận gián đoạn.

| Mô hình | Cách dữ liệu được chuyển | Ví dụ | Khi đích nhận gián đoạn |
|---|---|---|---|
| Pull | Backend chủ động đọc endpoint của ứng dụng theo chu kỳ | Prometheus | Lần scrape thất bại sẽ không có mẫu ở thời điểm đó; ứng dụng có thể không biết scraper đang lỗi |
| Push hoặc step | Registry chủ động gửi dữ liệu theo chu kỳ | Một số registry cho StatsD, Datadog hoặc backend push khác | Publisher có thể gặp lỗi kết nối; retry, buffer và xử lý step phụ thuộc implementation |
| In-memory | Registry chỉ giữ dữ liệu trong bộ nhớ | SimpleMeterRegistry | Dữ liệu chỉ tồn tại trong tiến trình và không được xuất đến backend |

Prometheus là ví dụ điển hình của mô hình pull. Ứng dụng cần cung cấp endpoint để Prometheus scrape; trong Spring Boot, Actuator có thể tự cấu hình endpoint Prometheus khi dependency phù hợp có mặt. Nếu endpoint không truy cập được, Prometheus không lấy được mẫu ở lần scrape đó. [Tài liệu Prometheus của Micrometer](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)

Với registry push hoặc step, registry thường có tác vụ publish chạy định kỳ. Dữ liệu được gửi theo chu kỳ và quy tắc của từng backend. Không thể suy ra rằng mọi registry push đều có cùng chính sách retry, lưu đệm hoặc gửi lại dữ liệu bị lỗi.

## 3. Khi ứng dụng dừng

Khi tiến trình dừng, các giá trị meter lưu trong bộ nhớ của tiến trình cũng kết thúc theo vòng đời đó. Sự khác biệt lớn nằm ở việc ứng dụng có đủ thời gian shutdown có trật tự hay bị kết thúc đột ngột.

### Shutdown có trật tự

Trong graceful shutdown, ứng dụng có cơ hội:

1. Ngừng nhận công việc mới.
2. Chờ request đang xử lý và message đang thực thi hoàn tất trong giới hạn thời gian.
3. Dừng scheduler hoặc worker do ứng dụng sở hữu.
4. Cho registry hoàn thành những hoạt động publish đang được hỗ trợ.
5. Đóng registry và tài nguyên exporter theo lifecycle.

Nếu công việc vẫn ghi meter sau khi registry đã đóng, số đo có thể không được ghi nhận hoặc không được xuất. Vì vậy, registry cần sống cho đến khi những thành phần sử dụng nó đã ngừng hoạt động.

Graceful shutdown làm giảm nguy cơ bỏ dở công việc đang xử lý, nhưng không bảo đảm mọi metrics đều đến backend. Nếu backend đang mất kết nối hoặc chu kỳ publish chưa đến, dữ liệu cuối vẫn có thể chưa được chuyển.

### Shutdown đột ngột

Khi tiến trình bị kill cưỡng bức, JVM crash, máy chủ mất điện hoặc container hết thời gian termination, mã cleanup có thể không chạy. Những dữ liệu chỉ còn trong bộ nhớ và chưa được scrape/publish sẽ mất cùng tiến trình.

Không nên dựa vào shutdown hook để bảo đảm xuất toàn bộ metrics. Shutdown hook cũng không chạy trong mọi tình huống như kill cưỡng bức hoặc mất điện. Hãy dùng lifecycle của framework và coi việc gửi metrics cuối là best-effort.

## 4. Pull registry khi ứng dụng dừng

Với mô hình pull, ứng dụng không gửi một gói dữ liệu cuối đến Prometheus. Nó chỉ cung cấp dữ liệu hiện tại qua endpoint. Prometheus định kỳ truy cập endpoint này và lưu mẫu nếu scrape thành công.

Khi ứng dụng chuẩn bị dừng:

- Nếu Prometheus scrape thành công trước khi endpoint ngừng phục vụ, mẫu cuối cùng có thể được lưu.
- Nếu endpoint dừng trước lần scrape tiếp theo, lần scrape đó thất bại và không có mẫu mới.
- Nếu ứng dụng khởi động lại ở địa chỉ hoặc target identity tương ứng, Prometheus sẽ scrape các giá trị mới của tiến trình mới.
- Không có thao tác flush chung ở phía ứng dụng để buộc Prometheus lưu một mẫu cuối.

Trong Spring Boot, endpoint Prometheus của Actuator cần được expose và bảo vệ phù hợp. Nếu dùng HTTP server riêng để phục vụ PrometheusMeterRegistry.scrape(), lifecycle của HTTP server cũng cần được quản lý; đóng registry không nhất thiết thay thế bước dừng server riêng do ứng dụng tạo.

Một khoảng trống scrape khi target dừng không đồng nghĩa giá trị metrics bằng 0. Nó có nghĩa backend không nhận được mẫu mới. Dashboard và cảnh báo nên phân biệt rõ **zero** với **no data** hoặc target không khả dụng.

## 5. Push và step registry khi ứng dụng dừng

Registry push thường có publisher chạy theo chu kỳ. Một phần dữ liệu có thể đang nằm trong trạng thái tích lũy của step hiện tại khi ứng dụng bắt đầu shutdown.

Không nên giả định lời gọi **close()** luôn phát một lần publish cuối. Contract chung của **MeterRegistry.close()** là giải phóng tài nguyên; sau khi đóng, registry không nhận meter mới và hoạt động publishing dừng. Contract này không hứa rằng mọi giá trị chưa gửi sẽ được flush thành công trước khi đóng. [MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)

Một số registry hoặc exporter cụ thể có thể cung cấp thao tác flush, shutdown hoặc publish riêng. Hãy kiểm tra tài liệu của đúng implementation và phiên bản đang sử dụng. Nếu có bước publish cuối, bước đó vẫn cần thời gian, kết nối mạng và backend sẵn sàng; nó không thể bảo đảm thành công khi đích nhận đang gián đoạn.

Với registry step, cách tính và publish dữ liệu theo cửa sổ phụ thuộc implementation. Nếu tiến trình dừng trước chu kỳ publish tiếp theo, dữ liệu thuộc step chưa gửi có thể không đến backend. Hãy kiểm thử tình huống shutdown ở giữa step thay vì suy đoán rằng registry sẽ tự gửi phần còn lại.

## 6. Đóng MeterRegistry có ý nghĩa gì?

**MeterRegistry.close()** là thao tác kết thúc vòng đời của registry. Theo API chung, registry đã đóng sẽ không nhận meter mới và hoạt động publishing sẽ dừng. Một số implementation còn phải giải phóng scheduler, thread, client hoặc tài nguyên riêng. [MeterRegistry Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)

Đóng registry chỉ kết thúc việc thu thập và xuất dữ liệu từ registry đó. Nó không xóa những mẫu đã được backend tiếp nhận; thời gian lưu các mẫu cũ tuân theo retention policy của backend.

Sau khi đóng:

- Không tiếp tục sử dụng registry để đăng ký meter mới.
- Không kỳ vọng các lần ghi mới tiếp tục được publish.
- Không dùng lại registry đã đóng khi ứng dụng khởi động lại một phần; hãy tạo registry mới theo lifecycle mới.
- Không gọi close từ một service chỉ đang sử dụng registry được inject.
- Chỉ chủ sở hữu registry hoặc container quản lý lifecycle mới chịu trách nhiệm đóng nó.

Trong Spring Boot, registry được quản lý như bean và được đóng khi ApplicationContext kết thúc. Component nghiệp vụ chỉ nên nhận registry qua dependency injection. Trong ứng dụng Java độc lập, nơi tạo registry phải chịu trách nhiệm đóng registry khi chương trình kết thúc.

Ví dụ quản lý registry thủ công:

~~~java
MeterRegistry registry = createRegistry();

try {
    runApplication(registry);
} finally {
    registry.close();
}
~~~

Ví dụ này thể hiện quyền sở hữu vòng đời. Nếu registry có yêu cầu publish cuối, hãy thực hiện bằng API được registry cụ thể hỗ trợ trước khi close và dành đủ thời gian cho thao tác đó. Không gọi một phương thức **flush()** giả định trên MeterRegistry chung, vì API đó không tồn tại như một contract phổ quát.

## 7. Đích nhận metrics bị gián đoạn

Backend có thể tạm thời không nhận dữ liệu vì mất mạng, DNS lỗi, TLS hoặc chứng chỉ hết hạn, thông tin xác thực sai, giới hạn tốc độ, quota, timeout hoặc backend đang bảo trì.

Ảnh hưởng phụ thuộc mô hình xuất:

### Với pull

Ứng dụng thường chỉ phục vụ endpoint. Nếu Prometheus hoặc scraper không thể kết nối, lần scrape thất bại. Ứng dụng có thể vẫn xử lý request và tiếp tục cập nhật meter bình thường, nhưng backend không có mẫu ở khoảng thời gian bị mất kết nối.

Khi scraper hoạt động trở lại, nó lấy trạng thái hiện tại của registry. Những trạng thái trung gian đã xảy ra rồi kết thúc giữa hai lần scrape không thể được tái tạo từ Gauge hiện tại.

### Với push

Publisher gửi dữ liệu và có thể nhận lỗi từ mạng hoặc backend. Việc retry, backoff, buffering, giới hạn số lần thử và cách xử lý dữ liệu của step đã thất bại tùy thuộc registry hoặc exporter.

Không có bảo đảm chung rằng Micrometer sẽ lưu vô hạn các batch bị lỗi rồi gửi lại sau khi backend phục hồi. Một registry có thể giữ trạng thái tích lũy trong bộ nhớ; registry khác có thể dùng dữ liệu theo step hoặc buffer giới hạn. Khi buffer đầy, publisher có thể bỏ dữ liệu, chặn tác vụ hoặc báo lỗi tùy implementation.

### Giá trị nào có thể còn và giá trị nào không?

| Loại dữ liệu | Trong lúc backend mất kết nối | Sau khi kết nối lại |
|---|---|---|
| Gauge | Chỉ phản ánh trạng thái hiện tại trong tiến trình | Có thể xuất giá trị hiện tại; trạng thái trung gian đã qua không được phát lại |
| Counter tích lũy | Giá trị trong tiến trình có thể tiếp tục tăng | Registry/backend có thể quan sát mức tích lũy mới nếu implementation giữ được; không bảo đảm cho mọi step registry |
| Timer count và total time | Có thể tiếp tục tích lũy trong registry | Khả năng phục hồi phụ thuộc registry, cửa sổ thống kê và cơ chế publish |
| Histogram hoặc percentile | Trạng thái phân phối được giữ theo cách của implementation | Không có cam kết chung về replay đầy đủ các bucket bị lỡ |
| Log hoặc sự kiện nghiệp vụ bền vững | Có thể tồn tại trong kho riêng | Có thể phát lại theo chính sách của kho đó |

Đối với pull, bảng này cần hiểu theo nghĩa backend chỉ nhìn thấy giá trị khi scrape. Đối với push, việc dữ liệu còn trong registry hay được giữ trong buffer không đồng nghĩa dữ liệu đã được lưu bền vững.

## 8. Ảnh hưởng khi ứng dụng khởi động lại

Meter lưu trong bộ nhớ thường bắt đầu lại cùng tiến trình mới. Counter và các phép đo tích lũy như Timer count/total time có thể reset. Đây là hành vi bình thường của metrics gắn với một process.

Với Prometheus, các phép toán như **rate()** được thiết kế để xử lý counter reset khi backend quan sát được mẫu trước và sau lần reset. Tuy nhiên, rate() không thể tái tạo những mẫu chưa từng được scrape trong khoảng ứng dụng dừng hoặc backend mất kết nối.

Ví dụ, một instance đã đếm 1.000 request rồi restart. Counter ở process mới có thể bắt đầu lại từ 0 và tiếp tục tăng. Truy vấn rate có thể nhận diện reset dựa trên các mẫu đã lưu, nhưng biểu đồ counter thô sẽ có bước giảm. Đây không phải dấu hiệu nghiệp vụ đã đảo ngược.

Gauge có ngữ nghĩa khác. Sau restart, Gauge đọc trạng thái hiện tại của process mới. Nó có thể thấp hơn, cao hơn hoặc bằng giá trị trước đó. Không dùng Gauge để tính mức tăng tích lũy qua nhiều lần khởi động.

Để phân tích triển khai và restart, nên giữ các chiều nhận diện ổn định như service, environment và một định danh instance phù hợp. Cần phân biệt thời điểm bắt đầu process với danh tính của service; không dùng request ID hoặc định danh có cardinality cao làm tag.

## 9. Thiết kế graceful shutdown trong Spring Boot

Spring Boot hỗ trợ graceful shutdown cho web server nhúng. Trong giai đoạn shutdown, server ngừng nhận request mới và cho request đang xử lý cơ hội hoàn tất trong khoảng timeout được cấu hình. Cơ chế cụ thể và mặc định có thể khác giữa phiên bản Spring Boot và web server. [Spring Boot Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)

Ví dụ cấu hình cho các phiên bản hỗ trợ explicit graceful mode:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Timeout cần được chọn dựa trên thời gian xử lý request, worker nền và những bước shutdown thực tế. Không đặt timeout nhỏ hơn thời gian cần để hoàn tất công việc đang chạy. Trong môi trường container, termination grace period của nền tảng cũng phải đủ dài để chứa thời gian drain, shutdown của ứng dụng và phần dự phòng.

Một thứ tự shutdown thực tế:

1. Đánh dấu instance không nhận traffic mới hoặc loại nó khỏi service discovery.
2. Ngừng nhận request, message hoặc job mới.
3. Chờ request và worker đang chạy hoàn tất trong giới hạn.
4. Dừng scheduler và producer do ứng dụng sở hữu.
5. Thực hiện publish cuối nếu registry cụ thể có hỗ trợ và backend đang sẵn sàng.
6. Đóng MeterRegistry cùng tài nguyên exporter.
7. Đóng HTTP server hoặc transport riêng nếu ứng dụng tự tạo.
8. Kết thúc tiến trình.

Không cần thêm một JVM shutdown hook tự quản lý registry nếu Spring ApplicationContext đã sở hữu lifecycle. Nhiều cơ chế cleanup cạnh tranh có thể khiến registry bị đóng sớm hoặc đóng lặp.

## 10. Không dùng metrics làm kho dữ liệu bền vững

Metrics có thể mất mẫu do scrape thất bại, push thất bại, buffer đầy, process restart hoặc shutdown đột ngột. Đây là đặc tính cần tính đến khi thiết kế hệ thống quan sát.

Không dùng Counter làm nguồn duy nhất cho:

- Đối soát thanh toán.
- Sổ cái kế toán.
- Lịch sử đơn hàng hoặc trạng thái giao dịch.
- Bằng chứng kiểm toán cần đầy đủ từng sự kiện.
- Hàng đợi công việc cần xử lý lại sau crash.

Nếu cần bảo đảm không mất sự kiện nghiệp vụ, hãy lưu sự kiện trong database, transactional outbox, message broker hoặc event log có durability. Metrics có thể được tổng hợp từ nguồn bền vững hoặc phát song song để hỗ trợ dashboard và cảnh báo.

Một Counter trong Micrometer cho biết số lượng sự kiện đã được instrumentation ghi nhận trong phạm vi vòng đời của registry. Nó không thay thế transaction commit, message acknowledgement hay cơ chế lưu trữ bền vững.

## 11. Theo dõi chính đường xuất metrics

Khi backend mất kết nối, đội vận hành cần biết exporter có đang gửi thành công hay không. Nếu chỉ nhìn dashboard nghiệp vụ, khoảng trống dữ liệu có thể bị nhầm với lưu lượng bằng 0.

Nên theo dõi các dấu hiệu sau bằng log, health check hoặc telemetry độc lập:

- Lần publish thành công gần nhất và độ trễ kể từ lần đó.
- Số lần publish lỗi, timeout hoặc bị backend từ chối.
- Số batch đang chờ và dung lượng buffer nếu exporter cung cấp.
- Số batch bị bỏ hoặc số lần retry vượt giới hạn.
- Thời gian xử lý một lần publish.
- Trạng thái target scrape và lỗi scrape ở phía backend.
- Trạng thái tiến trình, readiness và thời điểm restart.

Nếu metrics exporter tự báo lỗi qua chính backend đang mất kết nối, cảnh báo đó cũng có thể không đến nơi. Vì vậy, log cục bộ, health endpoint hoặc giám sát ở tầng agent/sidecar có thể là kênh độc lập cần thiết.

Không thêm tag có giá trị tùy ý như URL đầy đủ, exception message hoặc request ID vào các metrics exporter. Các tag này làm cardinality tăng và khiến chính hệ thống quan sát khó vận hành hơn.

## 12. Kiểm thử shutdown và gián đoạn backend

Kiểm thử instrumentation cần bao phủ cả vòng đời registry và đường truyền dữ liệu. Có thể dùng registry trong bộ nhớ để kiểm tra trạng thái meter, nhưng cần thêm kiểm thử tích hợp với exporter/backend khi muốn xác minh hành vi publish.

| Tình huống | Điều cần xác minh |
|---|---|
| Graceful shutdown | Request đang chạy hoàn tất trong timeout; worker ngừng trước khi registry đóng |
| Shutdown đột ngột | Xác định dữ liệu in-memory chưa publish bị mất và dashboard thể hiện khoảng trống |
| Đóng registry | Registry chuyển sang closed, không còn publish và không được sử dụng lại |
| Push backend timeout | Lỗi được ghi nhận, retry/buffer đúng cấu hình của exporter |
| Backend phục hồi | Xác minh dữ liệu nào được tiếp tục gửi và dữ liệu nào đã mất |
| Pull scrape thất bại | Scraper báo lỗi hoặc thiếu mẫu; ứng dụng không bị nhầm là có metric bằng 0 |
| Restart process | Counter reset được xử lý đúng trong truy vấn rate; Gauge phản ánh trạng thái process mới |
| Shutdown giữa step | Xác minh hành vi của registry cụ thể với phần dữ liệu chưa đến chu kỳ publish |

Một kiểm thử tích hợp cho registry push nên dùng endpoint HTTP giả lập để lần lượt trả thành công, timeout hoặc lỗi server. Kiểm tra số lần gọi, thời gian chờ, retry và việc đóng publisher. Với pull registry, có thể scrape endpoint trước khi shutdown, dừng server rồi xác nhận scraper không thể lấy mẫu ở lần tiếp theo.

Đừng dựa vào Thread.sleep() dài để kiểm tra chính xác lịch publish. Nếu implementation hỗ trợ clock hoặc scheduler có thể điều khiển trong test, hãy dùng chúng; nếu không, đặt timeout rõ ràng và kiểm tra kết quả quan sát được thay vì giả định thời điểm tuyệt đối.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ increment() đồng nghĩa backend đã lưu | Đánh giá sai độ bền dữ liệu | Phân biệt cập nhật meter, publish/scrape và lưu backend |
| Đóng registry trước khi worker kết thúc | Mất các phép đo cuối hoặc publisher dừng sớm | Drain công việc trước khi close |
| Giả định close() luôn flush | Dữ liệu step cuối có thể không được gửi | Kiểm tra API và hành vi registry cụ thể |
| Cho rằng Prometheus sẽ scrape sau khi app dừng | Không có endpoint để scrape | Cho scrape trước shutdown nếu cần và chấp nhận giới hạn thời điểm |
| Giả định mọi push registry retry vô hạn | Mất batch khi buffer đầy hoặc process dừng | Xem chính sách retry/buffer của implementation |
| Xem khoảng trống metrics là giá trị 0 | Dashboard và cảnh báo sai | Phân biệt no data, target down và zero |
| Dùng Counter làm sổ giao dịch | Không bảo đảm đầy đủ sau crash/restart | Lưu sự kiện trong hệ thống bền vững |
| Đóng registry được inject từ service | Các component khác mất khả năng publish | Để chủ sở hữu hoặc Spring quản lý lifecycle |
| Không giám sát exporter | Không phát hiện dữ liệu ngừng đến backend | Theo dõi lỗi publish, scrape và thời điểm thành công gần nhất |

## 14. Checklist vận hành

- [ ] Xác định registry đang dùng mô hình pull, push hay chỉ in-memory.
- [ ] Biết chu kỳ scrape hoặc publish và thời gian timeout của exporter.
- [ ] Xác định rõ ai sở hữu MeterRegistry và ai gọi close.
- [ ] Không đóng registry khi request hoặc worker vẫn còn ghi meter.
- [ ] Không giả định close() thực hiện final flush.
- [ ] Kiểm tra API flush/publish riêng của backend nếu yêu cầu có lần gửi cuối.
- [ ] Cấu hình graceful shutdown và timeout phù hợp với workload.
- [ ] Đặt termination grace period của container đủ dài cho quy trình shutdown.
- [ ] Có cảnh báo riêng cho target down, scrape failure hoặc publish failure.
- [ ] Hiểu cách Counter và Timer reset khi process restart.
- [ ] Phân biệt zero với no data trên dashboard.
- [ ] Lưu sự kiện nghiệp vụ quan trọng trong hệ thống có durability.
- [ ] Kiểm thử backend outage, shutdown giữa step và restart trước khi triển khai.

Ứng dụng dừng, registry đóng và backend gián đoạn đều có thể tạo khoảng trống trong metrics, nhưng nguyên nhân và cách xử lý khác nhau. Hãy xác định mô hình pull/push, quản lý registry theo đúng lifecycle, drain công việc trước khi close và kiểm chứng hành vi publish của registry cụ thể. Với dữ liệu cần đầy đủ tuyệt đối, hãy dùng hệ thống lưu sự kiện bền vững; metrics giữ vai trò tín hiệu quan sát vận hành.

## Tài liệu tham khảo

- [Micrometer Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)
- [Spring Boot Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

