# Test high-cardinality key

Trong chương **Testing observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, test high-cardinality key là nhóm kiểm thử nhằm phát hiện metric tags/labels hoặc attributes có thể tạo ra quá nhiều giá trị khác nhau. Một tag như `tenantId`, `userId`, `requestId`, raw URL hay SQL statement có thể trông hữu ích khi debug một request, nhưng khi được đưa vào metrics, mỗi giá trị mới có thể tạo một time series mới trong backend.

Cardinality là thuộc tính của toàn bộ tập dimensions trên một metric, không chỉ một key riêng lẻ. Vì vậy, kiểm thử cần xác minh cả nguồn dữ liệu (route, exception, tenant, dependency), cách chuẩn hóa, số lượng tổ hợp được tạo và tác động của histogram. Một unit test chỉ kiểm tra tên tag hoặc một request cố định thường không phát hiện được vấn đề; cần dùng nhiều giá trị đầu vào khác nhau, integration tests qua framework instrumentation và budget assertions.

Bài này hướng dẫn xây dựng kiểm thử có thể ngăn high-cardinality keys lọt vào metrics trong Spring Boot/Micrometer, đồng thời giữ khả năng điều tra chi tiết bằng logs/traces có kiểm soát.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Nhận diện metric tag keys và values có nguy cơ cardinality cao.
2. Phân biệt metric labels với trace attributes và structured log fields.
3. Tính upper bound series từ các dimensions.
4. Viết unit tests kiểm tra MeterRegistry và tag values.
5. Kiểm thử MeterFilter limits và hành vi khi vượt ngưỡng.
6. Gửi nhiều HTTP paths/identifiers để xác minh route normalization.
7. Kiểm thử custom Observation conventions và instrumentation.
8. Đánh giá histogram bucket multiplication trong series budget.
9. Dùng generated/property-based inputs để phát hiện values động.
10. Thiết lập regression gate để ngăn cardinality tăng ngoài dự kiến.

## 2. High-cardinality key là gì?

Metric series thường được xác định bởi metric name và toàn bộ tag/label values. Một key có cardinality cao khi nó nhận nhiều giá trị khác nhau, đặc biệt khi giá trị đến từ từng request hoặc entity.

| Key | Ví dụ value | Rủi ro |
| --- | --- | --- |
| tenantId | tenant-abc | Số tenant có thể tăng liên tục. |
| userId | u-10001, u-10002 | Một series cho từng user. |
| requestId | UUID mỗi request | Gần như mỗi request một giá trị. |
| traceId | Trace ID | Mỗi trace khác nhau. |
| uri | /orders/10001 | Raw path tạo series theo resource ID. |
| sql | Full SQL text | Literal values và query động. |
| exception.message | Message kèm host/input | Giá trị không ổn định. |
| email | alice@example.com | PII và cardinality lớn. |

Key name tự nó chưa đủ để kết luận. uri có thể an toàn nếu value là route template /orders/{orderId}; status có thể có cardinality cao nếu code gắn nguyên error message vào đó. Test cần kiểm tra values thực tế và nơi chúng được gắn.

## 3. Phân biệt metrics, traces và logs trong test

Không phải mọi high-cardinality information đều cần bị loại bỏ khỏi observability. Điều quan trọng là không đưa identifier không giới hạn vào metric dimensions.

| Signal | Dữ liệu phù hợp | Cần kiểm thử |
| --- | --- | --- |
| Metrics | method, route template, status class, outcome, service name cố định | Tập values hữu hạn và series budget. |
| Traces | trace/span IDs, request-specific attributes đã được policy cho phép | Privacy, sampling, attribute policy và retention. |
| Logs | request ID hoặc entity ID khi có nhu cầu điều tra hợp lệ | Masking, access control và retention. |
| Exemplars | Liên kết metric sample với trace | Backend hỗ trợ, không biến trace ID thành label. |

Ví dụ, test nên thất bại nếu requestId xuất hiện trong Meter.Id.tags, nhưng không nhất thiết thất bại nếu request ID xuất hiện trong structured log field đã được cho phép. Không áp dụng cùng một rule máy móc cho mọi signal.

## 4. Lập inventory và budget trước khi viết test

Bắt đầu bằng inventory metric families quan trọng: http.server.requests, http.client.requests, jdbc/connection-pool metrics, business timers/counters, scheduler/task metrics, cache, messaging và executor metrics.

Với mỗi metric, ghi các keys dự kiến, tập values tối đa, owner và budget. Upper bound đơn giản:

~~~text
series_combinations =
    values(method)
    * values(route)
    * values(status)
    * values(outcome)
~~~

Ví dụ:

~~~text
method  = 5
route   = 30
status  = 8
outcome = 4

upper bound = 5 * 30 * 8 * 4 = 4,800
~~~

Nếu một key tenantId có 2.000 giá trị được thêm vào:

~~~text
4,800 * 2,000 = 9,600,000 combinations
~~~

Đây là upper bound giả định mọi tổ hợp có thể xảy ra. Test budget nên ghi rõ giả định, vì một số combinations có thể không hợp lệ trong ứng dụng.

Với classic histogram, nhân tiếp theo số bucket series và _count/_sum theo exposition format. Đừng chỉ assert số meter objects trong registry rồi kết luận backend chỉ có từng ấy series.

## 5. Unit test không cho phép identifier keys

Có thể kiểm tra tags của một meter sau khi gọi code instrumented. Ví dụ helper assertion:

~~~java
static void assertNoHighCardinalityKeys(MeterRegistry registry) {
    Set<String> forbidden = Set.of(
            "userId",
            "tenantId",
            "requestId",
            "traceId",
            "email",
            "sql"
    );

    List<String> violations = registry.getMeters().stream()
            .flatMap(meter -> meter.getId().getTags().stream())
            .map(Tag::getKey)
            .filter(forbidden::contains)
            .distinct()
            .toList();

    assertThat(violations).isEmpty();
}
~~~

Đây là ví dụ minh họa. Bộ key cấm phải phù hợp naming conventions của dự án; cần kiểm tra cả snake_case, kebab-case hoặc aliases nếu instrumentation dùng nhiều conventions.

Test nên chạy sau khi kích hoạt những operations tạo meter. Registry rỗng không chứng minh instrumentation an toàn.

### Kiểm tra giá trị tag

Ngoài key name, kiểm tra values có phải raw identifier hay không. Ví dụ route tag chỉ nên chứa route template:

~~~java
assertThat(uriValues)
        .contains("/orders/{orderId}")
        .doesNotContain("/orders/10001", "/orders/10002");
~~~

Đừng chỉ blacklist một vài ID cố định. Tốt hơn là tạo hàng trăm identifiers ngẫu nhiên trong test rồi xác minh số lượng uri values vẫn giữ ở mức một.

## 6. Integration test cho route normalization

HTTP instrumentation có thể lấy route template từ framework sau khi handler mapping hoàn tất. Test cần gửi requests thật qua MockMvc/WebTestClient hoặc embedded server để xác minh giá trị cuối cùng.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpMetricCardinalityTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void differentOrderIdsShareOneUriTag() throws Exception {
        for (int id = 1; id <= 100; id++) {
            mockMvc.perform(get("/orders/{id}", id))
                    .andExpect(status().isOk());
        }

        Set<String> uriValues = registry.find("http.server.requests")
                .meters()
                .stream()
                .flatMap(meter -> meter.getId().getTags().stream())
                .filter(tag -> tag.getKey().equals("uri"))
                .map(Tag::getValue)
                .collect(Collectors.toSet());

        assertThat(uriValues).contains("/orders/{id}");
        assertThat(uriValues).doesNotContain("/orders/1", "/orders/100");
    }
}
~~~

Test cần route controller thật và endpoint trả status xác định. Tên meter/tag có thể khác theo Boot/Micrometer version và naming convention; inspect registry trong dự án trước khi cố định assertion.

Bổ sung các trường hợp: query parameters chứa IDs/emails không được thêm vào tags; unknown routes không tạo raw path values; error routes và exception handlers vẫn dùng route template; nested routes được normalize; HTTP client destination dùng logical service name thay host/path động.

## 7. Kiểm thử MeterFilter giới hạn tag values

Micrometer MeterFilter.maximumAllowableTags có thể giới hạn số tag values của một meter. Có thể test behavior trực tiếp với registry:

~~~java
@Test
void deniesNewUriValuesAfterLimit() {
    MeterRegistry registry = new SimpleMeterRegistry();
    registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                    "demo.requests",
                    "uri",
                    2,
                    MeterFilter.deny()
            )
    );

    registry.counter("demo.requests", "uri", "/orders").increment();
    registry.counter("demo.requests", "uri", "/customers").increment();
    registry.counter("demo.requests", "uri", "/payments").increment();

    assertThat(registry.find("demo.requests")
            .tag("uri", "/orders").counter()).isNotNull();
    assertThat(registry.find("demo.requests")
            .tag("uri", "/customers").counter()).isNotNull();
    assertThat(registry.find("demo.requests")
            .tag("uri", "/payments").counter()).isNull();
}
~~~

Test minh họa filter deny khi vượt giới hạn. Cần xác minh behavior theo Micrometer version, filter order và registry cụ thể. Trong ứng dụng thực, meter có thể được đăng ký từ nhiều instrumentation sources; integration test phải dùng đúng meter name và tag key.

Lưu ý:
- Filter bảo vệ khi tạo meter mới; không tự xóa series đã có.
- Filter không sửa raw values thành route template.
- Filter không áp dụng cho logs/traces.
- Test phải xác minh behavior khi giới hạn bị vượt, không chỉ xác minh bean filter tồn tại.

## 8. Test custom Observation conventions

Nếu ứng dụng dùng Observation API, conventions có thể quyết định tên và key-values. Test cần kiểm tra low-cardinality key-values trước khi chúng được đưa vào metrics.

~~~java
class OrderObservationConvention
        implements ObservationConvention<ServerRequestObservationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ServerRequestObservationContext;
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of("operation", "order.read"),
                KeyValue.of("outcome", "success")
        );
    }

    @Override
    public String getName() {
        return "order.request";
    }
}
~~~

Ví dụ chỉ minh họa ý tưởng; chọn context/convention phù hợp instrumentation thực tế. Không đưa request object, principal, tenant ID hoặc raw URI vào low-cardinality values.

Nếu cần request-specific details, cân nhắc high-cardinality trace attributes với privacy review. Test nên xác nhận chúng không xuất hiện trong metrics registry.

## 9. Property-based và generated input tests

Một số lỗi chỉ lộ ra khi values thay đổi liên tục. Có thể tạo generated inputs:
- 1.000 user IDs.
- 500 tenant IDs.
- Nhiều order/resource IDs trên cùng route.
- Query strings ngẫu nhiên.
- Exception messages có host, UUID hoặc input values.
- SQL statements với literals khác nhau.

Invariant quan trọng:
- Số uri tag values bằng số route templates, không phải số resource IDs.
- Không có identifier keys trong metrics.
- Outcome/status values thuộc allowlist.
- Số combinations không vượt budget.
- Error message không trở thành tag value.
- Thay input identifiers không làm xuất hiện metric series mới.

Property-based testing framework có thể tạo data theo seed để tái lập lỗi. Nếu không dùng framework riêng, vòng lặp generated inputs cũng có thể kiểm tra invariant, nhưng cần log seed khi test fail.

## 10. Histogram và series budget tests

Histogram làm tăng series count theo mỗi label set. Với Prometheus classic histogram, thường có một series cho mỗi bucket, cộng _count và _sum. Ví dụ 10 finite buckets, bucket +Inf, count và sum tương ứng 13 series cho mỗi label combination.

Test budget cần:
1. Xác định metric families bật histogram.
2. Đọc bucket configuration theo environment.
3. Tính số label combinations được phép.
4. Nhân với số bucket/count/sum.
5. So sánh với budget của metric family.
6. Xác minh exporter output nếu backend format có khác biệt.

Không assert một con số cố định cho mọi registry. Native histogram, OTLP histogram và Prometheus classic histogram có representation khác nhau. Budget test phải biết exporter format production đang sử dụng.

## 11. Test exemplar và correlation

Nếu registry/backend hỗ trợ exemplars, test có thể xác minh metric sample được liên kết tới trace context mà không thêm trace ID thành label.

Các điều cần xác nhận:
- Exemplar support được bật ở registry/exporter.
- Trace ID không xuất hiện trong metric Meter.Id.tags.
- Trace ID chỉ nằm trong exemplar metadata theo backend format.
- Sampling/tracing context đang active khi ghi measurement.
- Không đưa sensitive baggage vào exemplar hoặc span attributes.

Nếu exemplar không được hỗ trợ, dùng structured logs và trace backend để correlation. Không tạo metric label traceId làm phương án thay thế.

## 12. Kiểm thử ở nhiều tầng

| Tầng test | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Unit | Kiểm tra tag policy/convention. | Không có tenantId trong low-cardinality values. |
| MeterRegistry integration | Kiểm tra meters sau instrumentation. | Không có forbidden tag keys. |
| Web integration | Kiểm tra framework route normalization. | 100 order IDs chỉ tạo một uri tag value. |
| Exporter integration | Kiểm tra series exposition/OTLP output. | Histogram series count đúng dự toán. |
| Load/staging | Kiểm tra cardinality trong workload gần thực tế. | Active series không tăng tuyến tính theo request IDs. |
| Production monitoring | Phát hiện drift sau deploy. | Alert khi active series/churn vượt baseline. |

Không thay thế integration test bằng cách tự tạo meter trong test rồi gắn sẵn route template. Test phải đi qua instrumentation boundary cần được bảo vệ.

## 13. Regression gate trong CI

Tạo test suite chuyên về metric contract và chạy khi thay đổi metric name/tag key, Observation convention, HTTP route/controller mapping, dependency instrumentation, histogram/SLO configuration, Micrometer/Spring Boot version hoặc registry/exporter.

Một regression report nên nêu metric family mới/thay đổi, tag keys được thêm/bỏ, upper-bound series trước/sau, histogram multiplier, budget owner và test data/seed dùng để xác minh.

Không nhất thiết mọi metric đều có cùng ngưỡng. Dùng per-family budgets và yêu cầu review khi thêm dimension mới.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Test pass nhưng production cardinality cao | Test không dùng data distribution thật hoặc thiếu integration boundary. | Tạo generated identifiers và gửi request qua server thật. |
| uri tag chứa IDs | Instrumentation dùng raw path thay route template. | Kiểm tra route mapping và meter values. |
| Forbidden key vẫn xuất hiện | Naming alias chưa có trong blacklist hoặc filter order sai. | Chuẩn hóa key names và inspect toàn registry. |
| MeterFilter không deny | Sai meter name/tag key hoặc filter đăng ký quá muộn. | Kiểm tra configuration order và exact meter ID. |
| Registry meter count thấp nhưng backend series cao | Histogram/exporter nhân series hoặc nhiều instances. | Kiểm tra exposition format và replica multiplier. |
| Request ID xuất hiện trong metrics | Custom convention/filter thêm dynamic value. | Kiểm tra low-cardinality KeyValues. |
| Test bị flaky | Shared registry hoặc asynchronous instrumentation chưa hoàn tất. | Dùng registry riêng, reset state và đồng bộ test lifecycle. |
| Test không thấy meter | Endpoint không chạy, filter chưa được gọi hoặc config sai. | Kiểm tra request status, registry bean và meter creation. |
| Series tăng sau upgrade | Binder/convention đổi tag set. | So sánh meter metadata trước/sau version bump. |
| Bỏ ID tag làm mất khả năng debug | Correlation channel chưa có. | Dùng structured logs, traces hoặc exemplars. |

## 15. Runbook khi test phát hiện high-cardinality key

1. Xác định metric name và tag key bị vi phạm.
2. Truy nguồn instrumentation: binder, Observation convention, annotation, filter hoặc custom meter.
3. Lấy nhiều values thực tế và phân loại identifier/route/exception dimensions.
4. Xác định metric family có cần dimension đó cho alert/dashboard nào không.
5. Nếu không cần, loại bỏ key khỏi metrics.
6. Nếu cần phân nhóm, map values về allowlist hữu hạn.
7. Với HTTP, dùng route template; với SQL, dùng operation/fingerprint ổn định.
8. Chuyển request-specific details sang logs/traces theo privacy policy.
9. Cập nhật upper-bound budget và histogram multiplier.
10. Viết regression test với generated inputs và integration path.
11. Chạy lại suite và xác minh exporter output.
12. Theo dõi active series/churn sau deploy để xác nhận fix.

## 16. Bài tập tự kiểm tra

### Bài 1 — Nhận diện key

Một Timer có tags method, uri, tenantId, outcome. Key nào cần kiểm tra hoặc loại khỏi metric?

**Đáp án:** tenantId thường có cardinality cao và nên chuyển sang logs/traces hoặc nhóm tenant tier. uri chỉ an toàn nếu là route template. method và outcome thường có tập giá trị hữu hạn.

### Bài 2 — Test một request

Test gửi một request tới /orders/1 và xác nhận có meter. Vì sao chưa đủ?

**Đáp án:** Một request không cho biết raw URI có tạo series riêng cho mỗi ID không. Cần gửi nhiều IDs và assert số uri values vẫn bằng số route templates.

### Bài 3 — Filter limit

maximumAllowableTags được đặt limit 100. Điều đó có chứng minh tag design tốt không?

**Đáp án:** Không. Filter chỉ chặn meter mới sau ngưỡng; 100 raw values vẫn có thể quá nhiều. Cần normalize tại source và đặt budget dựa trên use case.

### Bài 4 — Histogram

Metric có 2.000 label combinations và 13 bucket series cộng count/sum. Ước lượng số series?

**Đáp án:** 2.000 × 15 = 30.000 series theo classic histogram format giả định.

### Bài 5 — Trace ID

Test phát hiện traceId không có trong metric tags. Có cần xóa trace ID khỏi traces/logs không?

**Đáp án:** Không tự động. Trace/log có thể cần request-specific correlation theo policy; cần bảo vệ privacy, sampling, access và retention riêng.

### Bài 6 — Production drift

CI pass nhưng active series tăng mạnh sau release. Điều gì cần kiểm tra?

**Đáp án:** Input distribution, replicas, histogram config, binder/convention changes, exporter format và instrumentation sources chưa được bao phủ trong CI.

## 17. Checklist triển khai

- [ ] Có inventory metric families và tag keys được phép.
- [ ] High-cardinality keys được xác định theo values thực tế, không chỉ tên key.
- [ ] Unit tests kiểm tra forbidden keys trong MeterRegistry.
- [ ] Tests kiểm tra tag values và upper-bound combinations.
- [ ] Integration tests gửi nhiều IDs qua route mapping thật.
- [ ] Raw paths/query parameters không trở thành metric tags.
- [ ] Tenant/user/request/trace IDs không nằm trong metric labels.
- [ ] Exception messages và raw SQL không trở thành tag values.
- [ ] MeterFilter limits được test với trường hợp vượt ngưỡng.
- [ ] Observation conventions chỉ đưa bounded values vào low-cardinality keys.
- [ ] Histogram buckets/count/sum được tính vào series budget.
- [ ] Exporter format được kiểm tra bằng integration test.
- [ ] Exemplars được dùng nếu cần metric-to-trace correlation và backend hỗ trợ.
- [ ] Logs/traces giữ identifier theo privacy, sampling và retention policy.
- [ ] CI regression gate chạy khi metric/tag/config/version thay đổi.
- [ ] Production active series và churn được theo dõi sau deploy.

**Ghi nhớ:** Test high-cardinality key phải kiểm tra values và tổ hợp series qua đường instrumentation thực tế. Dùng generated identifiers, route integration tests, MeterRegistry assertions, MeterFilter tests và histogram budget calculations. Metrics chỉ giữ dimensions hữu hạn; request-specific details được xử lý ở logs/traces hoặc exemplars theo policy. Kết hợp CI regression gates với theo dõi active series sau deploy để phát hiện cardinality drift.
