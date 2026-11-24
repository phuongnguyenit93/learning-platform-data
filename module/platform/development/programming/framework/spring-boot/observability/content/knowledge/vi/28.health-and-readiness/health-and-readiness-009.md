# Health group

Trong chương **Health và readiness** của mô-đun **SPRING_BOOT_OBSERVABILITY**, Health group cho phép Spring Boot Actuator gom các health indicators thành những góc nhìn sức khỏe riêng theo mục đích vận hành. Thay vì chỉ có một kết quả tổng hợp từ `/actuator/health`, ứng dụng có thể cung cấp các nhóm như `readiness`, `liveness`, `critical-dependencies` hoặc `external-services`. Mỗi nhóm chỉ kiểm tra những thành phần phù hợp với quyết định mà caller cần đưa ra.

Health group đặc biệt quan trọng khi triển khai ứng dụng trên Kubernetes hoặc nền tảng điều phối tương tự. Liveness trả lời process có cần được khởi động lại hay không; readiness trả lời instance đã sẵn sàng nhận traffic chưa. Hai câu hỏi này khác nhau, vì vậy không nên đưa mọi dependency vào cả hai nhóm. Một database tạm thời unavailable có thể khiến readiness fail, nhưng thường không có nghĩa process cần restart.

Bài này giải thích cách tạo và cấu hình health groups, cách chọn contributors, xử lý status và HTTP mapping, bảo vệ chi tiết health, kiểm thử các trạng thái và tích hợp với deployment probes.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích Health group và vai trò của nó trong Actuator.
2. Phân biệt health group tổng hợp với từng HealthIndicator.
3. Cấu hình readiness/liveness groups và các group nghiệp vụ riêng.
4. Chọn contributors bằng include/exclude và hiểu group membership.
5. Tùy chỉnh status aggregation và HTTP status mapping.
6. Thiết kế liveness không phụ thuộc vào dịch vụ ngoài không thiết yếu.
7. Thiết kế readiness phản ánh đúng khả năng nhận traffic.
8. Bảo vệ health details bằng show-details và authorization.
9. Kiểm thử group endpoints với healthy, degraded và down dependencies.
10. Troubleshoot probe failures và tránh cascading restart/traffic removal.

## 2. Health group là gì?

HealthIndicator hoặc HealthContributor cung cấp trạng thái của một thành phần. Health group là một tập hợp có tên gồm các contributors được Actuator đánh giá và tổng hợp thành một kết quả riêng.

Ví dụ:
- `readiness`: trạng thái sẵn sàng nhận request.
- `liveness`: trạng thái process cần tiếp tục chạy.
- `critical-dependencies`: các dependency thiết yếu cho request path.
- `external-services`: dịch vụ bên ngoài cần theo dõi nhưng không nhất thiết quyết định readiness.
- `startup`: trạng thái hoàn tất các bước khởi tạo cần thiết.

Một contributor có thể xuất hiện trong nhiều groups. Ví dụ, database có thể thuộc `readiness` nếu mọi request đều cần database; nhưng không nên tự động thuộc `liveness`.

Health group không tạo một health check mới cho mỗi member. Nó tổ chức và tổng hợp các kết quả từ HealthContributors đã có.

## 3. Endpoint mặc định và named groups

Endpoint tổng hợp mặc định:

~~~http
GET /actuator/health
~~~

Khi bật health probes, Spring Boot có thể cung cấp các groups dành cho liveness và readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các endpoint tương ứng thường có dạng:

~~~http
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Có thể định nghĩa named groups riêng bằng cấu hình:

~~~yaml
management:
  endpoint:
    health:
      group:
        critical:
          include: db,redis
        external:
          include: search,partnerApi
~~~

Sau đó có thể truy cập:

~~~http
GET /actuator/health/critical
GET /actuator/health/external
~~~

Tên group phải ổn định và không xung đột với endpoint/contributor names. Cấu hình thực tế cần có contributors tương ứng được đăng ký. Nếu tên trong `include` không tồn tại hoặc bị đánh vần sai, group có thể không hoạt động như mong đợi; kiểm tra startup/configuration logs.

## 4. Include và exclude contributors

Các group thường được cấu hình bằng `include` và `exclude`.

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
        external:
          include: search,partnerApi
          exclude: diskSpace
~~~

`include` xác định contributors được đưa vào group. `exclude` loại contributors khỏi group theo tên contributor. Kiểm tra đúng tên bean/indicator và tên chuẩn mà Actuator sử dụng trong ứng dụng.

Một số lưu ý:
- Không giả định mọi contributor tự động thuộc mọi custom group.
- Kiểm tra membership của group bằng response health details ở môi trường được phép.
- Nếu dùng custom HealthContributor, đặt tên bean rõ ràng và ổn định.
- Tránh tạo quá nhiều groups chỉ để nhân bản cùng một danh sách indicators.
- Mỗi group nên phục vụ một quyết định vận hành cụ thể.

## 5. Liveness và readiness có mục đích khác nhau

| Group | Câu hỏi | Thành phần phù hợp |
| --- | --- | --- |
| Liveness | Process có còn sống và có thể tiếp tục chạy không? | livenessState và tín hiệu nội bộ cho thấy process không thể phục hồi. |
| Readiness | Instance có thể nhận traffic mới không? | readinessState, database hoặc dependency bắt buộc theo kiến trúc. |
| Critical dependencies | Các dependency chính có hoạt động không? | Database, cache, broker thiết yếu. |
| External services | Dịch vụ ngoài có đang phản hồi không? | Search, partner API, payment provider. |

Không đưa database hoặc remote API vào liveness chỉ vì chúng quan trọng với business. Nếu dependency outage làm liveness fail, platform có thể restart liên tục mọi replicas mà không khắc phục được nguyên nhân bên ngoài.

Readiness có thể phụ thuộc database nếu request path không thể hoạt động khi database unavailable. Tuy nhiên, cần cân nhắc degraded mode, cache, queueing và số replicas. Nếu tất cả instances cùng fail readiness trong một sự cố database, service sẽ bị loại hoàn toàn khỏi traffic; đó có thể là quyết định đúng hoặc làm sự cố nặng hơn tùy kiến trúc.

## 6. Tự động thêm readiness/liveness state

Spring Boot cung cấp application availability states và các health indicators tương ứng khi probes được bật.

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

`livenessState` phản ánh trạng thái liveness của application; `readinessState` phản ánh trạng thái readiness. Spring Boot và application lifecycle có thể chuyển các state này trong quá trình startup/shutdown.

Ứng dụng cũng có thể điều khiển availability state khi cần:

~~~java
@Component
class WarmupRunner implements ApplicationRunner {

    private final ApplicationAvailability availability;

    WarmupRunner(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        // Thực hiện warm-up cần thiết trước khi đánh dấu ready.
        // Spring Boot quản lý availability lifecycle; chỉ thay đổi state
        // thủ công khi ứng dụng thực sự sở hữu quyết định đó.
    }
}
~~~

Đoạn code minh họa cách truy cập ApplicationAvailability. Trong thực tế, dùng AvailabilityChangeEvent.publish(...) với ReadinessState.ACCEPTING_TRAFFIC hoặc REFUSING_TRAFFIC khi application cần điều khiển readiness tường minh; không tự đặt state chỉ dựa trên transient dependency failure.

## 7. Custom HealthIndicator trong một group

Có thể viết HealthIndicator cho dependency riêng:

~~~java
@Component("partnerApi")
class PartnerApiHealthIndicator implements HealthIndicator {

    private final PartnerClient client;

    PartnerApiHealthIndicator(PartnerClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.ping();
            return Health.up()
                    .withDetail("dependency", "partner-api")
                    .build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "partner-api")
                    .withDetail("error", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

Tên bean `partnerApi` có thể được dùng trong cấu hình group include. Không đưa exception message, URL, credentials hoặc response body vào details.

Health check nên:
- Có timeout ngắn và giới hạn rõ.
- Thực hiện thao tác nhẹ, không chạy query nặng hoặc full scan.
- Không tạo side effects.
- Tránh gọi hàng loạt downstream dependencies quá thường xuyên.
- Có phân loại UP, DOWN hoặc trạng thái phù hợp với policy.
- Không tạo cascading load khi dependency đang gặp sự cố.

Nếu health check dùng cùng connection pool với business traffic, cần tránh tạo thêm tải đáng kể khi hệ thống đang quá tải. Có thể dùng lightweight ping hoặc cached health signal tùy yêu cầu freshness.

## 8. Status aggregation và HTTP status mapping

Health group tổng hợp status từ các members. Spring Boot có status aggregator mặc định, nhưng ứng dụng có thể tùy chỉnh thứ tự severity hoặc HTTP mapping.

~~~yaml
management:
  endpoint:
    health:
      status:
        order: DOWN,OUT_OF_SERVICE,UNKNOWN,UP
        http-mapping:
          down: 503
          out-of-service: 503
      group:
        readiness:
          status:
            order: DOWN,OUT_OF_SERVICE,UNKNOWN,UP
~~~

Status severity và HTTP response code có quan hệ nhưng là hai khái niệm khác nhau:
- Status aggregator chọn status tổng hợp từ contributors.
- HTTP mapper chuyển status đó thành response code.

Ví dụ, readiness DOWN thường được map thành HTTP 503 để platform loại instance khỏi traffic. Đừng thay status order tùy tiện vì nó có thể thay đổi kết quả tổng hợp. Kiểm tra response thực tế của group endpoint sau khi cấu hình.

Một custom status như `DEGRADED` cần được định nghĩa và mapping rõ ràng nếu ứng dụng dùng. Nếu không, platform có thể coi status là UNKNOWN hoặc HTTP 200 tùy mapping, dẫn tới probe behavior ngoài dự kiến.

## 9. Health details và bảo mật

Health endpoints có thể trả chi tiết về database, broker, dependency names, host hoặc trạng thái hệ thống. Cấu hình mức hiển thị:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Các lựa chọn phổ biến tùy version gồm `never`, `when-authorized` và `always`. Trên production, tránh `always` nếu endpoint có thể truy cập từ caller không tin cậy.

Cần phân biệt:
- Health status tối thiểu cho probe.
- Component status để operator hiểu thành phần nào DOWN.
- Details có thể chứa thông tin nội bộ cần role được authorize.

Có thể dùng Spring Security để giới hạn quyền đọc details và endpoint quản trị. Network policy cũng cần ngăn public access nếu management interface không dành cho internet.

Không trả password, connection string, token, full exception message hoặc raw response từ dependency trong Health details. Chỉ trả category/error type đã được lọc.

## 10. Health group và deployment probes

Kubernetes có thể dùng endpoint readiness/liveness làm HTTP probes. Ví dụ cấu hình khái niệm:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

Các thông số trên chỉ minh họa. Port/path cần khớp server hoặc management server configuration. Nếu Actuator chạy trên management port riêng, probe phải gọi đúng port đó.

Readiness probe fail khiến instance không còn được xem là ready sau khi control plane cập nhật endpoints. Liveness probe fail có thể khiến container bị restart. Vì vậy, hai probes không nên dùng cùng một group chỉ vì tiện.

Nếu app khởi động chậm, dùng startup probe để cho process đủ thời gian khởi tạo trước khi liveness bắt đầu. Không dùng liveness để kiểm tra dependency chậm hoặc remote service tạm unavailable.

## 11. Group-specific endpoints và exposure

Custom health group có thể có endpoint riêng, nhưng vẫn phải xem xét web exposure và security. Nếu dùng default health endpoint exposure, các groups thường được truy cập dưới `/actuator/health/{group}` khi group được tạo.

Không expose toàn bộ Actuator endpoints chỉ để probe gọi health group. Chỉ expose health và cấu hình details phù hợp. Kiểm tra management base path, port, address và security matcher.

Nếu custom group cần HTTP status khác với aggregate health, cấu hình group-specific status mapping theo khả năng version đang dùng và kiểm thử response. Không giả định cấu hình group tự động thay đổi global health status.

## 12. Metrics và logs bổ trợ cho health groups

Health group là snapshot trạng thái tại thời điểm được gọi; nó không thay thế metrics lịch sử hoặc alerting.

Kết hợp:
- Health group: instance có thể nhận traffic không?
- Metrics: dependency error rate, latency, pool saturation và request volume biến đổi thế nào?
- Logs: health indicator fail vì lỗi cụ thể nào?
- Traces: request/dependency path nào chậm hoặc thất bại?

Không tạo metric tag từ raw health details hoặc dependency error messages. Nếu cần đếm health check failures, dùng counters với tags hữu hạn như dependency name và outcome.

~~~java
log.atWarn()
        .addKeyValue("event.name", "health.check.failed")
        .addKeyValue("dependency", "partner-api")
        .addKeyValue("outcome", "down")
        .log("Dependency health check failed");
~~~

Log chỉ nên ghi category cần thiết. Không ghi toàn bộ exception hoặc response body nếu chúng có thể chứa dữ liệu nhạy cảm.

## 13. Kiểm thử Health groups

Dùng Spring Boot test để xác minh group membership, status aggregation và HTTP mapping. Mock dependency để điều khiển trạng thái:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ReadinessHealthGroupTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    PartnerClient partnerClient;

    @Test
    void readinessDoesNotDependOnOptionalPartner() throws Exception {
        when(partnerClient.ping()).thenThrow(new RuntimeException());

        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

Test này giả định `partnerApi` không thuộc readiness group. Với Spring Boot versions mới, annotation mock có thể chuyển sang cơ chế `@MockitoBean`; dùng API test phù hợp với version của dự án.

Các test cần có:
1. Tất cả contributors UP thì group UP.
2. Contributor bắt buộc DOWN thì group DOWN.
3. Contributor optional DOWN không làm readiness fail nếu không nằm trong group.
4. Exclude loại đúng contributor.
5. Custom status có HTTP mapping đúng.
6. Health details bị ẩn với anonymous caller.
7. Readiness/liveness endpoints tồn tại khi probes enabled.
8. Startup state không báo ready trước warm-up cần thiết.
9. Indicator timeout không làm request health treo vô hạn.

Không dùng Thread.sleep để đợi health transition nếu có thể điều khiển availability state hoặc mock lifecycle event trực tiếp.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| /actuator/health/readiness trả 404 | Probes chưa enabled hoặc group endpoint không được tạo. | Kiểm tra management.endpoint.health.probes.enabled và version. |
| Custom group trả UNKNOWN | Include trỏ tới contributor không tồn tại hoặc status chưa được map. | Kiểm tra bean names và response components. |
| Readiness DOWN dù API vẫn xử lý được | Group có dependency optional hoặc check quá nghiêm ngặt. | Rà soát group membership và degraded mode. |
| Liveness DOWN khi database outage | Database bị đưa nhầm vào liveness group. | Chỉ dùng process/lifecycle health cho liveness. |
| Probe fail do 404/503 | Path, port, HTTP mapping hoặc exposure không đúng. | Kiểm tra probe config và response thực tế. |
| Health details không hiển thị | show-details policy yêu cầu authorization. | Kiểm tra caller role và security configuration. |
| Health request tạo tải cao | Indicator gọi query nặng hoặc nhiều remote services. | Dùng timeout, lightweight ping hoặc cached state. |
| Một contributor làm group fail | Status aggregation ưu tiên severity của contributor đó. | Xác định member và status order. |
| Tất cả replicas bị remove khỏi service | Readiness phụ thuộc shared dependency đang outage. | Xem lại readiness policy, capacity và degraded mode. |
| Startup probe/liveness restart loop | Startup chưa hoàn tất nhưng liveness đã bắt đầu. | Cấu hình startup probe và startup lifecycle đúng. |

## 15. Runbook: readiness group báo DOWN

1. Gọi /actuator/health/readiness từ network context tương tự platform probe.
2. Xác nhận HTTP status và health status trong response.
3. Nếu details bị ẩn, truy vấn bằng operator identity được phép.
4. Xác định contributor nào làm group DOWN.
5. Kiểm tra group include/exclude và tên bean tương ứng.
6. Đối chiếu dependency latency/error metrics và logs.
7. Kiểm tra health indicator timeout và tải do probe tạo ra.
8. Xác định dependency đó có thật sự bắt buộc cho request path không.
9. Nếu optional, sửa group membership qua change đã kiểm thử; không che lỗi bằng cách ép status UP.
10. Kiểm tra số replicas còn ready và capacity của service.
11. Sau khi dependency hồi phục, xác minh readiness transition trở lại UP.
12. Ghi nhận nguyên nhân và cập nhật health policy/runbook nếu cần.

## 16. Bài tập tự kiểm tra

### Bài 1 — Database outage

Database unavailable trong 2 phút. Có nên đưa database vào cả readiness và liveness không?

**Đáp án:** Thường không đưa vào liveness. Readiness có thể include database nếu mọi request cần DB; liveness nên tập trung process/lifecycle để tránh restart loop do outage bên ngoài.

### Bài 2 — Optional dependency

Search service tạm thời lỗi nhưng ứng dụng có fallback cache. Có nên để search indicator làm readiness fail?

**Đáp án:** Không nhất thiết. Nếu service vẫn đáp ứng request theo degraded mode, search có thể thuộc group external riêng; readiness nên phản ánh khả năng thực tế nhận traffic.

### Bài 3 — Custom group UNKNOWN

Group critical trả UNKNOWN. Cần kiểm tra gì?

**Đáp án:** Kiểm tra contributor names trong include/exclude, HealthContributor beans đã đăng ký và status aggregation/mapping.

### Bài 4 — Readiness DOWN và HTTP 200

Group status DOWN nhưng response HTTP 200. Điều gì có thể sai?

**Đáp án:** HTTP status mapping chưa ánh xạ DOWN thành 503 hoặc custom group mapping khác. Kiểm tra status order và http-mapping của group.

### Bài 5 — Liveness restart loop

Pod restart liên tục khi partner API unavailable. Nguyên nhân thường gặp?

**Đáp án:** External dependency bị đưa vào liveness group. Liveness fail khiến orchestrator restart process dù process không hỏng.

### Bài 6 — Probe gây quá tải

Mỗi readiness check chạy truy vấn báo cáo nặng và được gọi vài giây một lần. Cách sửa?

**Đáp án:** Thay bằng lightweight check có timeout, cached health state hoặc tín hiệu từ client/pool. Health probe không nên làm tăng tải khi hệ thống đã quá tải.

## 17. Checklist triển khai

- [ ] Mỗi Health group có mục đích vận hành cụ thể.
- [ ] Readiness và liveness được thiết kế riêng.
- [ ] Liveness không phụ thuộc remote dependencies không thiết yếu.
- [ ] Readiness chỉ include dependencies thực sự cần cho khả năng nhận traffic.
- [ ] Custom group include/exclude dùng đúng contributor names.
- [ ] Custom HealthIndicators có timeout, nhẹ và không có side effects.
- [ ] Status aggregation và HTTP status mapping được kiểm thử.
- [ ] Health details được bảo vệ bằng show-details và authorization.
- [ ] Probe port/path khớp management/application server.
- [ ] Startup probe được dùng nếu thời gian warm-up dài.
- [ ] Metrics/logs bổ trợ health status và không tạo cardinality cao.
- [ ] Không trả secrets, connection strings hoặc raw exception messages trong details.
- [ ] Integration tests bao phủ healthy, degraded, down và timeout.
- [ ] Có runbook xác định contributor làm readiness fail.
- [ ] Có capacity/degraded-mode plan khi shared dependency outage.
- [ ] Health group được rà soát khi thêm dependency hoặc thay đổi request path.

**Ghi nhớ:** Health group gom các HealthContributors theo một quyết định vận hành cụ thể. Readiness quyết định instance có nhận traffic không; liveness quyết định process có cần restart không. Chọn members bằng include/exclude, dùng health checks nhẹ có timeout, bảo vệ details và kiểm thử status/HTTP mapping. Kết hợp health groups với metrics, logs và traces để hiểu nguyên nhân thay vì chỉ nhìn một trạng thái UP/DOWN.
