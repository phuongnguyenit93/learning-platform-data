# Đề xuất cổng chất lượng phù hợp cho một mô-đun Java

Một nhóm đang chuẩn bị phát hành phiên bản mới của mô-đun tính giá đơn hàng. Mô-đun có unit test, integration test, phân tích tĩnh và kiểm tra bảo mật, nhưng mọi kiểm tra hiện được chạy theo một chuỗi dài. Một lỗi format đơn giản chỉ được phát hiện sau khi toàn bộ end-to-end test hoàn tất. Trong một lần khác, thay đổi migration database chỉ chạy unit test rồi được merge dù chưa kiểm chứng trên database thật.

Bài thực hành này yêu cầu bạn thiết kế **các cổng chất lượng (quality gates) phù hợp cho một mô-đun Java**, sắp xếp phản hồi từ kiểm tra nhanh đến kiểm tra tốn kém, xác định bước nào chặn merge hoặc release, và giải thích cách xử lý các trường hợp lỗi, bị bỏ qua hoặc chưa chạy.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã được xem xét qua độ tin cậy, khả năng hiểu và khả năng thay đổi. Quality gate giúp biến những kỳ vọng đó thành điều kiện có thể kiểm tra. Một pipeline tốt không phải là pipeline có nhiều job nhất; nó là pipeline tạo đủ bằng chứng cho rủi ro của thay đổi, phản hồi kịp thời và thể hiện trung thực điều gì đã được kiểm chứng.

## 1. Mục tiêu thực hành

Sau bài tập, bạn cần có khả năng:

1. Đọc bối cảnh mô-đun Java và xác định các rủi ro chất lượng quan trọng.
2. Phân biệt kiểm tra nhanh, kiểm tra cần build artifact và kiểm tra cần môi trường tích hợp.
3. Sắp xếp gate theo chi phí, dependency và khả năng phát hiện lỗi sớm.
4. Phân loại gate thành **blocking**, **advisory** hoặc **conditional**.
5. Chọn gate phù hợp cho local, pull request, merge vào nhánh chính, release và lịch chạy định kỳ.
6. Thiết kế cách chạy song song mà không làm quá tải runner hoặc môi trường dùng chung.
7. Xử lý rõ trạng thái **PASSED**, **FAILED**, **SKIPPED** và **NOT RUN**.
8. Giải thích ngoại lệ, false positive, flaky test và cách theo dõi chúng.
9. Trình bày quyết định bằng ma trận gate, dependency graph và tiêu chí chấp nhận.

Bạn không cần thiết kế một hệ thống CI cho mọi loại sản phẩm. Hãy tập trung vào mô-đun được mô tả và giải thích vì sao mỗi gate có mặt.

## 2. Bối cảnh mô-đun cần thiết kế gate

Bạn tham gia nhóm phát triển mô-đun Java có tên **order-pricing**. Mô-đun tính tổng tiền đơn hàng trước khi checkout xác nhận đơn.

| Thuộc tính | Giá trị |
| --- | --- |
| Ngôn ngữ/runtime | Java 17 |
| Build | Gradle |
| Kiểu mô-đun | Library nghiệp vụ được ứng dụng checkout sử dụng |
| API chính | Tính phí tiêu chuẩn, phụ phí giao nhanh, phụ phí vùng xa và giảm giá |
| Phụ thuộc | PostgreSQL qua repository adapter; message publisher để phát sự kiện giá đã xác nhận |
| Consumer | Checkout API và một batch repricing worker |
| Dữ liệu nhạy cảm | Giá, mã khách hàng, mã khuyến mãi; không lưu thông tin thẻ trong mô-đun |
| Tần suất thay đổi | Nhiều PR nhỏ mỗi ngày; release theo lịch |
| Rủi ro chính | Tính sai tiền, áp dụng giảm giá sai điều kiện, cập nhật trạng thái không nhất quán, gửi event trùng |

Mô-đun có cấu trúc logic như sau:

~~~mermaid
flowchart TD
    A["Checkout API"] --> B["OrderPricingService"]
    C["Repricing Worker"] --> B
    B --> D["PricingPolicy"]
    B --> E["PromotionPolicy"]
    B --> F["OrderRepository"]
    B --> G["PriceConfirmedPublisher"]
    F --> H[("PostgreSQL")]
    G --> I["Message Broker"]
    I --> J["Downstream Order Consumer"]
~~~

Một thay đổi trong PricingPolicy có thể ảnh hưởng cả checkout trực tiếp và batch repricing. Một thay đổi trong repository hoặc event publisher có thể ảnh hưởng tính nhất quán dữ liệu và xử lý downstream.

### Hợp đồng nghiệp vụ đang được xác nhận

Dùng các quy tắc sau làm cơ sở thiết kế test:

- Giá trị tiền dùng **long theo đơn vị VND nguyên**; không dùng floating point cho phép tính tiền.
- Tổng tiền hàng và các khoản phí đầu vào không được âm.
- Giảm giá không được vượt quá tổng tiền đủ điều kiện giảm.
- Phụ phí giao nhanh và vùng xa được tính độc lập theo chính sách đã cấu hình.
- Một đơn đã xác nhận không được phát sinh một sự kiện xác nhận thứ hai chỉ vì message bị gửi lại.
- Nếu lưu đơn thành công nhưng phát sự kiện thất bại, hệ thống phải có cách phục hồi đã được thiết kế, ví dụ transactional outbox.
- Checkout API và batch worker phải dùng cùng hợp đồng tính giá, nhưng có thể có lịch chạy và workload khác nhau.

Đây là **bối cảnh giả định cho bài thực hành**. Trong hệ thống thật, người sở hữu nghiệp vụ phải xác nhận ngưỡng, mức phí, chính sách khuyến mãi, mã lỗi và quy tắc sự kiện trước khi biến chúng thành test bắt buộc.

## 3. Năng lực và thời gian hiện tại của pipeline

Nhóm đã đo được thời gian trung vị của các bước trên runner CI tiêu chuẩn. Số liệu minh họa:

| Kiểm tra | Thời gian trung vị | Phụ thuộc chính |
| --- | ---: | --- |
| Formatter và whitespace check | 8 giây | Source checkout |
| Validate cấu hình và migration syntax | 12 giây | Source checkout |
| Secret scan trên diff/source | 18 giây | Source checkout |
| Compile production và test source | 35 giây | Dependency resolution |
| Unit test | 55 giây | Compile output |
| Static analysis cần bytecode | 50 giây | Compile output |
| Dependency/license scan từ lockfile | 25 giây | Manifest/lockfile |
| Component/integration test với PostgreSQL container | 3 phút 40 giây | Build output và database container |
| Contract test cho event schema | 1 phút 20 giây | Build output và broker/test harness |
| End-to-end checkout flow trên môi trường preview | 7 phút | Deploy preview và các service phụ thuộc |
| Performance smoke test | 5 phút | Build/deploy và workload cố định |
| Load/resilience suite đầy đủ | 25 phút | Môi trường riêng và dữ liệu đại diện |

Các con số này là **baseline giả định để so sánh quyết định**, không phải ngưỡng bắt buộc cho mọi dự án.

Nhóm có những giới hạn:

- Mỗi pull request nên nhận được **feedback có thể hành động trong khoảng 3 phút** nếu lỗi thuộc các kiểm tra nhanh.
- Các gate bắt buộc trước merge nên hoàn tất trong **khoảng 10 phút** với PR thông thường, nếu runner và môi trường ổn định.
- Chỉ có hai môi trường integration dùng chung; chạy quá nhiều job cùng lúc có thể gây tranh chấp database.
- Load/resilience suite đầy đủ không phù hợp chạy trên mọi commit.
- Branch protection có thể yêu cầu các job cụ thể phải pass.
- Một job bị bỏ qua không được hiển thị như thể đã chạy thành công.

Bạn cần cân bằng tốc độ phản hồi với bằng chứng cần thiết cho tính đúng đắn, bảo mật và khả năng vận hành.

## 4. Các thay đổi mẫu cần xem xét

Hãy dùng bốn loại PR sau để quyết định gate:

| PR | Nội dung | Rủi ro chính |
| --- | --- | --- |
| **PR-A: đổi tên helper và format** | Đổi tên phương thức private, format một số file, không đổi logic. | Lỗi build, thay đổi ngoài ý muốn do thao tác cơ học. |
| **PR-B: đổi quy tắc giảm giá** | Thay đổi điều kiện áp dụng promotion và cách tính tổng tiền. | Sai số tiền, sai biên, regression ở caller. |
| **PR-C: sửa repository/migration** | Thêm cột trạng thái và thay cách lưu giá đã xác nhận. | Schema không tương thích, transaction/rollback, dữ liệu sai. |
| **PR-D: đổi retry và event publisher** | Thay đổi retry, acknowledgment và phát event. | Event trùng/mất, concurrency, queue backlog, lỗi phục hồi. |

Không nên áp dụng cùng một mức kiểm thử cho cả bốn PR. Tuy vậy, mỗi PR vẫn phải đạt các gate nền tảng đã thống nhất như compile và những kiểm tra bắt buộc chung của repository.

## 5. Nhiệm vụ của bạn

Hãy thiết kế một đề xuất có thể được nhóm áp dụng. Bài làm cần trả lời các phần sau.

### Nhiệm vụ 1 — Lập danh mục gate

Liệt kê ít nhất các nhóm kiểm tra:

- Formatter/whitespace/config validation.
- Secret scan.
- Compile.
- Unit test.
- Static analysis.
- Coverage hoặc kiểm tra test quality phù hợp.
- Dependency/license/security scan.
- Component/integration test.
- Contract test.
- End-to-end/smoke test.
- Performance/load/resilience test.
- Review con người và release approval khi cần.

Với mỗi nhóm, ghi:

1. Gate kiểm tra điều gì?
2. Nó cần artifact hoặc môi trường nào?
3. Thời gian/chi phí tương đối?
4. Có thể chạy độc lập hay phải chờ bước khác?
5. Có blocking, advisory hay conditional?
6. Thất bại thì ai xử lý và bước tiếp theo là gì?

### Nhiệm vụ 2 — Sắp xếp thứ tự phản hồi

Thiết kế luồng từ kiểm tra nhanh đến kiểm tra sâu. Bạn cần:

- Đưa kiểm tra cơ học và secret scan lên sớm.
- Đặt compile trước những bước cần bytecode.
- Chạy unit test gần logic nghiệp vụ.
- Chọn đúng integration/contract test cho thay đổi chạm database hoặc event.
- Chọn E2E và performance test theo rủi ro.
- Nêu rõ bước nào có thể chạy song song.

### Nhiệm vụ 3 — Phân loại gate theo điểm trong vòng đời

Đề xuất gate cho:

- Máy developer/local trước khi push.
- Pull request.
- Merge queue hoặc nhánh chính.
- Release candidate.
- Scheduled/nightly pipeline.

Không cần chạy mọi thứ ở mọi điểm. Nhưng phải giải thích **bằng chứng nào là bắt buộc trước merge và bằng chứng nào phải có trước release**.

### Nhiệm vụ 4 — Quyết định cho bốn PR mẫu

Với PR-A đến PR-D, nêu:

- Gate nào bắt buộc chạy?
- Gate nào có thể bỏ qua hợp lý?
- Gate nào cần mở rộng do rủi ro?
- Điều kiện nào khiến PR không được merge?
- Có cần chạy lại gate khi commit mới được push không?

### Nhiệm vụ 5 — Xử lý tình huống thất bại

Giải thích cách xử lý các trường hợp:

- Compile fail, các job phụ thuộc compile bị skip.
- Unit test fail nhưng secret scan đã pass.
- SAST báo finding severity cao nhưng confidence chưa rõ.
- Integration test flaky.
- Load test chưa chạy do môi trường không sẵn sàng.
- Một job bị skip do path filter.
- PR xanh nhưng có commit mới sau kết quả đó.

Không được biến **skipped/not run** thành **passed**.

### Nhiệm vụ 6 — Viết tiêu chí chấp nhận

Đưa ra policy ngắn, đủ rõ để trả lời:

- Gate nào blocking?
- Ai được phép chấp nhận ngoại lệ?
- Ngoại lệ cần bằng chứng gì và hết hạn khi nào?
- Điều kiện nào cần chạy lại test?
- Khi nào cần full suite?
- Kết quả cuối cùng được gắn với revision nào?

## 6. Bài nộp cần có

Một bài làm hoàn chỉnh nên có:

1. **Gate matrix**: bảng kiểm tra, mục tiêu, chi phí, dependency, trạng thái và lý do.
2. **Pipeline graph**: sơ đồ thứ tự và các nhánh song song.
3. **PR policy matrix**: gate theo từng loại PR.
4. **Lifecycle matrix**: local, PR, main, release, nightly.
5. **Failure policy**: cách xử lý fail, skipped, flaky và override.
6. **Acceptance policy**: tiêu chí merge/release.
7. **Giải thích đánh đổi**: tại sao thứ tự đó đủ nhanh nhưng vẫn bảo vệ rủi ro.

Nếu thiếu một phần, hãy ghi rõ giả định và điều cần xác nhận với owner.

## 7. Mẫu bảng để tự điền

Bạn có thể sao chép bảng này để làm bài:

| Gate | Mục tiêu | Chi phí | Dependency | Trigger | Blocking? | Lý do/điều kiện |
| --- | --- | --- | --- | --- | --- | --- |
| Format/config | ... | ... | ... | ... | ... | ... |
| Secret scan | ... | ... | ... | ... | ... | ... |
| Compile | ... | ... | ... | ... | ... | ... |
| Unit test | ... | ... | ... | ... | ... | ... |
| Static analysis | ... | ... | ... | ... | ... | ... |
| Dependency/license | ... | ... | ... | ... | ... | ... |
| Integration/contract | ... | ... | ... | ... | ... | ... |
| E2E/smoke | ... | ... | ... | ... | ... | ... |
| Performance/load | ... | ... | ... | ... | ... | ... |

### Mẫu pipeline graph

~~~text
checkout
  |
  +-- formatter/config
  +-- secret scan
  +-- dependency manifest scan
  |
  v
compile
  |
  +-- unit tests
  +-- static analysis cần bytecode
  |
  v
integration + contract tests
  |
  v
preview deploy + smoke/E2E
  |
  v
performance/release checks theo rủi ro
~~~

Bạn cần điều chỉnh graph này theo dependency thật. Ví dụ dependency scan chỉ cần lockfile có thể chạy trước compile; static analysis cần bytecode phải đợi compile.

## 8. Hướng dẫn xác định blocking và advisory

Một gate nên là **blocking** khi thất bại có nghĩa thay đổi chưa đạt điều kiện chấp nhận đã thống nhất.

Ví dụ thường blocking:

- Source không biên dịch.
- Unit test bắt buộc thất bại.
- Contract test bắt buộc phát hiện schema không tương thích.
- Secret xác nhận bị lộ.
- Finding bảo mật nghiêm trọng đã được xác minh và nằm trong phạm vi áp dụng policy.
- Migration không chạy được trên phiên bản database mục tiêu.
- Thiếu phê duyệt bắt buộc cho vùng rủi ro cao.

Một gate có thể là **advisory** khi nó cung cấp tín hiệu cần xem xét nhưng chưa đủ căn cứ tự động chặn:

- Cảnh báo maintainability mức thấp chưa vi phạm policy.
- Coverage giảm nhẹ nhưng không vi phạm ngưỡng đã chốt và vùng thay đổi có test phù hợp.
- Benchmark dao động trong phạm vi nhiễu.
- Gợi ý refactor không liên quan trực tiếp.

Một gate nên là **conditional** khi chỉ áp dụng theo vùng hoặc loại thay đổi:

- Migration test khi PR chạm schema/migration.
- Contract test khi thay API/event schema.
- Performance test khi thay thuật toán, pool, queue hoặc đường xử lý tải.
- Kiểm tra bảo mật chuyên sâu khi thay authentication, authorization hoặc xử lý dữ liệu nhạy cảm.

**Conditional không có nghĩa là tùy chọn theo ý tác giả.** Điều kiện kích hoạt phải được định nghĩa trong policy hoặc dependency detection đủ tin cậy.

## 9. Lời giải tham khảo: gate matrix

Một phương án phù hợp với bối cảnh giả định:

| Gate | Mục tiêu | Chi phí | Dependency | Trigger | Blocking? |
| --- | --- | --- | --- | --- | --- |
| Formatter/whitespace | Giữ format thống nhất và diff dễ review. | Rất thấp | Source checkout | Mọi PR | Có, nếu là rule repository đã chốt. |
| Config/migration syntax | Phát hiện cấu hình hoặc migration sai cú pháp. | Thấp | Source checkout | Mọi PR có config; migration khi có file liên quan | Có khi thay đổi chạm file đó. |
| Secret scan | Phát hiện credential bị commit. | Thấp | Source checkout/diff | Mọi PR | Có khi finding được xác minh. |
| Compile | Kiểm tra source và test source có build được. | Thấp-vừa | Dependency resolution | Mọi PR | Có. |
| Unit test | Kiểm tra logic và biên nghiệp vụ. | Thấp-vừa | Compile output | Mọi PR | Có với suite bắt buộc. |
| Static analysis | Tìm lỗi tiềm ẩn và rule nghiêm trọng. | Vừa | Source hoặc bytecode tùy tool | Mọi PR | Có với blocker theo policy; cảnh báo thấp có thể advisory. |
| Coverage/test evidence | Kiểm tra vùng thay đổi có test phù hợp. | Vừa | Test + coverage report | Mọi PR logic | Có theo ngưỡng/tiêu chí đã chốt; không dùng phần trăm đơn lẻ. |
| Dependency/license scan | Phát hiện CVE và license không được phép. | Thấp-vừa | Lockfile/graph | Mọi PR đổi dependency; scan đầy đủ định kỳ | Có với finding áp dụng policy. |
| PostgreSQL integration | Kiểm tra transaction, repository và migration. | Cao | Build + DB container | PR-C và thay đổi persistence | Có với thay đổi database. |
| Event contract test | Kiểm tra schema và compatibility consumer/provider. | Vừa-cao | Build + contract harness | PR-D và thay đổi event schema | Có khi contract bị ảnh hưởng. |
| E2E/smoke | Kiểm tra luồng checkout quan trọng qua môi trường. | Cao | Deploy preview | PR chạm luồng checkout; release candidate | Có ở release; PR có thể chọn critical flow theo policy. |
| Performance smoke | Phát hiện hồi quy lớn trên workload cố định. | Cao | Build/deploy | PR chạm đường tính giá nóng hoặc release candidate | Conditional; blocking nếu vi phạm SLO/threshold đã xác nhận. |
| Full load/resilience | Đánh giá capacity, retry và phục hồi. | Rất cao | Môi trường riêng | PR-D lớn, release candidate hoặc nightly | Blocking trước release khi thay đổi làm tăng rủi ro tải/phục hồi. |
| Human review | Xác nhận yêu cầu, thiết kế và rủi ro ngoài khả năng tự động. | Phụ thuộc | Diff và bằng chứng test | Mọi PR | Có theo branch policy. |

Bảng này là **đề xuất cho mô-đun giả định**. Mỗi nhóm cần điều chỉnh theo SLO, chính sách bảo mật, tần suất release và khả năng của môi trường CI.

### Vì sao không đặt mọi gate thành blocking?

Nếu mỗi cảnh báo maintainability hoặc benchmark nhỏ đều chặn PR, nhóm sẽ nhận quá nhiều false positive và thời gian chờ tăng. Blocking cần dành cho điều kiện có tiêu chí chấp nhận rõ, hậu quả đủ lớn hoặc policy bắt buộc.

Ngược lại, không nên biến các gate quan trọng thành advisory chỉ để đạt mục tiêu thời gian. Nếu migration có thể làm mất dữ liệu, test migration phải có chỗ trong điều kiện merge/release thích hợp.

## 10. Lời giải tham khảo: pipeline graph

Một pipeline có thể chạy các kiểm tra độc lập ngay sau checkout, rồi chờ compile cho những bước cần bytecode:

~~~mermaid
flowchart TD
    A["Checkout + xác định revision"] --> B["Formatter / whitespace"]
    A --> C["Secret scan"]
    A --> D["Config và migration syntax"]
    A --> E["Dependency/license scan từ lockfile"]
    B --> F["Compile production + test"]
    D --> F
    F --> G["Unit tests"]
    F --> H["Static analysis cần bytecode"]
    G --> I["Post-compile required gates"]
    H --> I
    E --> I
    C --> I
    I --> J{"Thay đổi chạm persistence?"}
    J -- "Có" --> K["PostgreSQL integration + migration test"]
    J -- "Không" --> L["Contract/integration liên quan"]
    K --> L
    L --> M{"Thay đổi chạm event contract?"}
    M -- "Có" --> N["Event contract test"]
    M -- "Không" --> O["Gate PR hoàn tất"]
    N --> O
    O --> P["Merge queue kiểm tra revision cuối"]
    P --> Q["Release candidate: smoke + E2E"]
    Q --> R["Performance/load/resilience theo rủi ro"]
    R --> S["Release approval"]
~~~

Một số bước có thể chạy song song:

- **Formatter, secret scan, config validation và dependency scan từ lockfile** không cần chờ compile nếu công cụ thực sự độc lập.
- **Unit test và static analysis cần bytecode** có thể chạy song song sau compile, miễn runner đủ tài nguyên.
- **PostgreSQL integration và event contract test** có thể chạy song song nếu chúng dùng môi trường cô lập; nếu dùng chung broker/database thì phải giới hạn concurrency.
- **E2E** cần preview environment đã sẵn sàng.
- **Load/resilience** cần môi trường riêng, không tranh chấp tài nguyên với integration test.

Sơ đồ thể hiện dependency và điều kiện kích hoạt, không phải cấu hình cú pháp của một CI provider.

## 11. Lời giải tham khảo: gate theo vòng đời

| Gate | Local | Pull request | Merge queue/main | Release candidate | Nightly |
| --- | --- | --- | --- | --- | --- |
| Format/config | Nên chạy | Blocking | Không cần chạy lại nếu artifact cùng revision còn hiệu lực | Có thể xác minh trạng thái cuối | Có thể kiểm tra drift |
| Secret scan | Có thể chạy pre-commit | Blocking | Theo policy server-side | Xác nhận image/artifact nếu cần | Quét lịch sử/phạm vi rộng theo policy |
| Compile | Nên chạy | Blocking | Chạy trên tổ hợp mã cuối | Blocking | Có |
| Unit test | Nên chạy liên quan | Blocking | Chạy lại nếu merge queue tạo revision mới | Blocking | Full unit suite |
| Static analysis | Có thể chạy local | Blocking theo rule nghiêm trọng | Theo policy | Xác nhận report cuối | Scan đầy đủ |
| Dependency/license | Có thể chạy | Blocking theo policy | Xác nhận lockfile cuối | Scan artifact/image | Scan toàn dependency graph |
| Integration/contract | Test liên quan | Conditional blocking | Chạy khi merge graph ảnh hưởng | Blocking cho luồng release quan trọng | Full suite |
| E2E/smoke | Không bắt buộc | Critical flow theo rủi ro | Có thể chạy trên preview | Blocking cho luồng trọng yếu | Full regression |
| Performance/load | Benchmark nhỏ khi cần | Conditional | Khi thay đổi nhạy hiệu năng | Blocking theo SLO và loại thay đổi | Full load/resilience |
| Human review | — | Bắt buộc | Approval hợp lệ theo policy | Release approval | Review xu hướng/action |

Lưu ý: “không cần chạy lại” chỉ hợp lệ nếu kết quả gắn với **đúng source revision và artifact** đang được merge. Nếu commit thay đổi hoặc merge queue tạo tổ hợp code mới, các gate bị ảnh hưởng cần chạy lại.

## 12. Lời giải tham khảo: policy cho bốn PR

| PR | Gate bắt buộc | Gate mở rộng | Điều kiện không merge |
| --- | --- | --- | --- |
| **PR-A: rename/format** | Formatter, compile, unit test liên quan, static check cơ bản, review diff. | Có thể không cần DB integration/E2E nếu xác minh không đổi contract và call path. | Compile/test bắt buộc fail; diff cho thấy đổi hành vi ngoài ý muốn; gate nền tảng fail. |
| **PR-B: promotion logic** | Formatter, compile, unit test biên, static analysis, coverage/test evidence, review nghiệp vụ. | Component/integration với caller checkout và batch; contract test nếu output schema thay đổi; E2E critical flow theo policy. | Test giá/discount sai, không bảo vệ biên, caller không tương thích hoặc thiếu approval nghiệp vụ. |
| **PR-C: repository/migration** | Formatter, compile, unit test, migration validation, PostgreSQL integration trên phiên bản mục tiêu, review persistence. | Test upgrade từ schema hiện tại, rollback/recovery, contract nếu dữ liệu xuất ra consumer thay đổi. | Migration không chạy, dữ liệu/bất biến sai, rollback/roll-forward không có phương án chấp nhận được. |
| **PR-D: retry/event publisher** | Formatter, compile, unit test retry/idempotency, static/security, review event contract. | Integration với broker, redelivery/concurrency, contract test, load/resilience và quan sát backlog. | Có nguy cơ event mất/trùng trái hợp đồng, test redelivery fail, không có recovery hoặc chưa đánh giá tác động tải. |

PR-A vẫn phải qua gate nền tảng; “chỉ rename” không phải lý do bỏ compile. PR-C và PR-D cần nhiều kiểm tra hơn vì chúng chạm dữ liệu bền vững, giao tiếp và phục hồi.

## 13. Lời giải tham khảo: ví dụ cấu hình Gradle

Tên task thật phụ thuộc plugin và cách tổ chức repository. Ví dụ các lệnh có thể được cấu hình trong một dự án Gradle:

~~~bash
# Kiểm tra định dạng; chỉ dùng nếu dự án đã cấu hình Spotless.
./gradlew spotlessCheck

# Biên dịch source và test source.
./gradlew compileJava compileTestJava

# Unit test.
./gradlew test

# Kiểm tra tổng hợp của các plugin đã cấu hình.
./gradlew check

# Tạo báo cáo coverage nếu dự án đã cấu hình JaCoCo.
./gradlew jacocoTestReport
~~~

Integration test thường được cấu hình thành source set/task riêng, ví dụ tên task integrationTest, nhưng **không phải task mặc định của mọi dự án Gradle**. Phải xem cấu hình build thực tế trước khi chọn tên task cho CI.

Một số nguyên tắc:

- Task check có thể phụ thuộc nhiều task verification; cần biết graph thực tế để tránh chạy lặp test.
- Không dùng build như một nhãn chung mà không biết nó chạy những gì.
- Tách task nhanh và task dài để pipeline có thể phản hồi sớm.
- Giữ dependency version cố định bằng lockfile/verification phù hợp.
- Lưu test report và artifact để reviewer xem được bằng chứng.
- Cấu hình timeout và cleanup cho container/database.
- Không đưa credential thật vào Gradle command line hoặc log.

### Minh họa dependency giữa các task

~~~kotlin
// Kotlin DSL minh họa; tên task phải khớp cấu hình dự án.
tasks.register("fastQualityGate") {
    dependsOn("spotlessCheck")
    dependsOn("compileJava")
    dependsOn("compileTestJava")
    dependsOn("test")
}
~~~

Đoạn này chỉ minh họa cách gom task; không nên copy nguyên xi nếu check hoặc plugin đã định nghĩa dependency khác. Một task tổng hợp không làm cho các dependency tự chạy song song hoặc nhanh hơn; điều đó còn phụ thuộc Gradle task graph và tài nguyên runner.

## 14. Lời giải tham khảo: test evidence cho quy tắc giá

Với PR-B, unit test nên kiểm tra ít nhất:

- Dưới, tại và trên ngưỡng.
- Promotion hợp lệ và không hợp lệ.
- Discount không vượt quá phần tiền đủ điều kiện.
- Phụ phí cộng độc lập theo chính sách.
- Đầu vào âm hoặc dữ liệu không hợp lệ.
- Kết quả của caller checkout và batch dùng cùng policy.

Ví dụ Java 17:

~~~java
public final class PricingPolicy {
    private PricingPolicy() {
    }

    public static long standardShippingFee(long subtotal) {
        if (subtotal < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }
        return subtotal >= 500_000L ? 0L : 30_000L;
    }

    public static long applyDiscount(
            long eligibleAmount, long requestedDiscount) {
        if (eligibleAmount < 0L || requestedDiscount < 0L) {
            throw new IllegalArgumentException("negative amount");
        }
        return Math.min(eligibleAmount, requestedDiscount);
    }
}
~~~

JUnit 5 minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PricingPolicyTest {
    @ParameterizedTest
    @CsvSource({
            "0, 30000",
            "499999, 30000",
            "500000, 0",
            "500001, 0"
    })
    void appliesFreeShippingBoundary(long subtotal, long expectedFee) {
        assertEquals(expectedFee,
                PricingPolicy.standardShippingFee(subtotal));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> PricingPolicy.standardShippingFee(-1L));
    }

    @Test
    void discountCannotExceedEligibleAmount() {
        assertEquals(100_000L,
                PricingPolicy.applyDiscount(100_000L, 150_000L));
    }
}
~~~

Các expected value được suy từ hợp đồng giả định. Coverage report có thể giúp phát hiện nhánh chưa được chạy, nhưng gate nên xem **chất lượng assertion và vùng rủi ro**, không chỉ đặt một con số phần trăm tùy ý.

## 15. Lời giải tham khảo: xử lý trạng thái gate

Một pipeline cần phân biệt:

| Trạng thái | Ý nghĩa | Quyết định |
| --- | --- | --- |
| **PASSED** | Job đã chạy trên revision xác định và đạt tiêu chí. | Đạt gate đó. |
| **FAILED** | Job đã chạy và phát hiện lỗi hoặc không đạt tiêu chí. | Xử lý theo policy; blocking gate thì không merge. |
| **SKIPPED** | Job bị bỏ qua do điều kiện hoặc dependency. | Không được xem là pass; xác định điều kiện skip có hợp lệ không. |
| **NOT RUN** | Job chưa được thực thi. | Chưa có bằng chứng; chạy khi policy yêu cầu. |
| **CANCELLED** | Job bị hủy trước khi hoàn tất. | Không có kết quả đạt; cần xác định có phải chạy lại. |
| **ERROR/INFRA FAILURE** | Công cụ hoặc môi trường không thể đưa ra kết quả đáng tin. | Xử lý hạ tầng hoặc chạy lại có kiểm soát; không đổi thành pass. |
| **WAIVED** | Có ngoại lệ được người có thẩm quyền chấp nhận. | Lưu lý do, owner, phạm vi, hạn và biện pháp giảm thiểu. |

Ví dụ compile fail nhưng secret scan pass:

- Secret scan giữ trạng thái **PASSED**.
- Compile là **FAILED**.
- Unit test cần bytecode có thể là **SKIPPED**.
- Integration test có thể là **NOT RUN**.
- PR vẫn bị chặn vì compile là gate bắt buộc.

Nếu integration test flaky:

1. Lưu log và revision.
2. Xác minh có phải lỗi code, test data, môi trường hay race.
3. Rerun có giới hạn để thu thập bằng chứng.
4. Nếu tái hiện không ổn định, tạo/đính kèm issue có owner và thời hạn.
5. Không tự động xem một lần pass sau nhiều lần fail là bằng chứng đủ.
6. Nếu test bảo vệ rủi ro nghiêm trọng, cần người có thẩm quyền quyết định điều kiện merge hoặc release.

Nếu load test chưa chạy vì môi trường không sẵn sàng, kết quả phải là **NOT RUN/INFRA FAILURE**, không phải PASSED. Release policy cần quyết định liệu có thể trì hoãn, dùng môi trường thay thế hay phải chờ đủ bằng chứng.

## 16. Ngoại lệ và false positive

Một ngoại lệ hợp lệ không nên chỉ là comment “ignore this warning”.

Hồ sơ ngoại lệ cần:

- Finding hoặc gate cụ thể.
- Revision, artifact và phiên bản dependency liên quan.
- Bằng chứng vì sao finding không áp dụng hoặc vì sao tạm chấp nhận.
- Mức rủi ro còn lại.
- Người/nhóm có quyền phê duyệt.
- Biện pháp giảm thiểu.
- Ngày hết hạn hoặc thời điểm xem lại.
- Link tới issue khắc phục nếu là ngoại lệ tạm thời.

Không cho phép developer tự miễn gate bảo mật nghiêm trọng của chính PR mà không có cơ chế phê duyệt độc lập theo policy.

**False positive được xác minh** có thể được quản lý bằng rule exception hẹp. Không nên tắt toàn bộ scanner vì một finding sai.

## 17. Chính sách chấp nhận merge và release mẫu

Một policy có thể viết:

~~~text
MERGE REQUIREMENTS
- Mọi gate blocking áp dụng cho PR phải PASSED trên revision hiện tại.
- Compile và unit test bắt buộc không được FAILED.
- Secret scan không có secret đã xác minh.
- Finding security phải được xử lý hoặc có waiver hợp lệ.
- Integration/contract test phải chạy khi thay đổi chạm ranh giới tương ứng.
- Reviewer bắt buộc đã approve theo branch policy.
- SKIPPED/NOT RUN không được coi là PASSED.

RELEASE REQUIREMENTS
- Gate merge vẫn còn hiệu lực trên commit/artifact phát hành.
- Migration và contract tương thích được xác minh trên môi trường mục tiêu.
- Smoke/E2E của luồng quan trọng đạt.
- Performance/load/resilience evidence đạt khi loại thay đổi hoặc SLO yêu cầu.
- Các waiver còn hiệu lực, có owner và thời hạn.
- Có phương án rollback/recovery phù hợp với rủi ro.

RERUN POLICY
- Commit mới làm thay đổi source/dependency/config liên quan thì chạy lại gate bị ảnh hưởng.
- Merge queue tạo merge result mới thì xác minh gate trên merge result đó.
- Infra failure được rerun sau khi xác nhận môi trường; không tự chuyển trạng thái sang pass.
~~~

Đây là policy mẫu. Nhóm cần điều chỉnh người phê duyệt waiver, thời hạn, mức severity và gate bắt buộc theo tiêu chuẩn nội bộ.

## 18. Rubric tự đánh giá bài làm

Tổng điểm gợi ý: **100 điểm**.

| Tiêu chí | Điểm | Mức đạt |
| --- | ---: | --- |
| Nhận diện rủi ro của order-pricing | 15 | Chỉ ra đúng tiền, promotion, persistence, event và caller. |
| Gate matrix | 20 | Có mục tiêu, chi phí, dependency, trigger, blocking/advisory/conditional và lý do. |
| Thứ tự và dependency graph | 15 | Kiểm tra nhanh sớm, bước cần artifact chờ đúng dependency, song song có kiểm soát. |
| Lifecycle và PR policy | 15 | Phân biệt local/PR/main/release/nightly và bốn PR mẫu. |
| Failure/skip/waiver policy | 15 | Phân biệt đầy đủ trạng thái, xử lý flaky và false positive. |
| Test và security evidence | 10 | Chọn test biên, integration, contract và bảo mật theo rủi ro. |
| Giải thích đánh đổi | 10 | Giải thích được tốc độ, chi phí CI, mức bảo vệ và giới hạn. |

### Diễn giải kết quả

- **90–100:** Đề xuất có thể đưa ra review nhóm; quyết định rõ và có bằng chứng.
- **75–89:** Khá tốt; cần làm rõ một số dependency, ngoại lệ hoặc trigger.
- **60–74:** Có cấu trúc cơ bản nhưng thiếu phân loại rủi ro hoặc policy.
- **Dưới 60:** Cần làm lại gate matrix và dependency graph trước khi triển khai.

Rubric này đánh giá chất lượng lập luận, không phải phép đo năng lực tuyệt đối.

## 19. Các lỗi thường gặp khi làm bài

| Lỗi | Vì sao chưa phù hợp | Cách cải thiện |
| --- | --- | --- |
| Chạy mọi test tuần tự | Feedback chậm dù có bước độc lập. | Vẽ dependency graph và chạy song song có giới hạn. |
| Chạy mọi test song song | Có thể tranh chấp DB, broker và runner. | Cô lập môi trường, đặt concurrency limit. |
| Đưa E2E lên trước compile | Tốn môi trường để phát hiện lỗi rẻ. | Đưa format/config/compile/unit lên sớm. |
| Bỏ security scan để đạt 10 phút | Tốc độ không được đánh đổi bằng rủi ro không kiểm soát. | Tách scan nhanh và scan sâu theo artifact/môi trường. |
| Dùng coverage làm tiêu chí duy nhất | Coverage không chứng minh expected đúng. | Xem assertion, nhánh rủi ro và test contract. |
| Coi skipped là pass | Không có bằng chứng nhưng báo xanh. | Thể hiện trạng thái chính xác. |
| Retry flaky vô hạn | Che lỗi và kéo dài pipeline. | Retry có giới hạn, điều tra và theo dõi owner. |
| Mọi cảnh báo đều blocking | Tạo false positive và giảm niềm tin. | Severity, confidence và policy rõ. |
| PR nhỏ bỏ mọi test | Có thể bỏ sót lỗi tương thích hoặc tác động gián tiếp. | Giữ gate nền tảng và chọn test theo rủi ro. |
| Không chạy lại sau commit mới | Kết quả cũ không chứng minh revision mới. | Gắn gate với commit/artifact cuối. |

## 20. Bài tập mở rộng

Sau khi hoàn thành lời giải cơ bản, thử điều chỉnh thiết kế trong các tình huống:

### Biến thể A — Mô-đun chỉ có pure functions

Mô-đun chỉ tính giá, không truy cập database hoặc phát event.

**Câu hỏi:** Gate nào có thể giảm hoặc bỏ?

**Gợi ý:** Không cần PostgreSQL integration hay broker contract nếu thật sự không có ranh giới đó. Giữ compile, unit, static, dependency/security và test contract ở caller nếu public API có consumer.

### Biến thể B — Mô-đun xử lý dữ liệu tài chính nhạy cảm

Một thay đổi mới bổ sung xử lý dữ liệu tài chính và audit.

**Câu hỏi:** Cần thêm gate hoặc approval nào?

**Gợi ý:** Tăng kiểm tra authorization, audit, secret/data handling, dependency security và integration test. Release cần approval theo policy và bằng chứng phục hồi/đối soát phù hợp.

### Biến thể C — CI runner bị giới hạn

Runner chỉ có CPU/RAM hạn chế, chạy song song làm unit test chậm gấp đôi.

**Câu hỏi:** Có nên giữ mọi job song song?

**Gợi ý:** Không. Ưu tiên first actionable feedback, giới hạn concurrency và chạy các job ít tranh chấp trước. Đo wall-clock cùng chi phí tài nguyên.

### Biến thể D — Thay đổi chỉ tài liệu

PR chỉ sửa README và ví dụ, không thay code hay cấu hình.

**Câu hỏi:** Có thể chọn gate nhẹ hơn không?

**Gợi ý:** Có thể bỏ integration/E2E nếu path policy đáng tin cậy và không có generated docs/config thực thi. Vẫn cần markdown/link/lint hoặc docs build phù hợp, secret scan và review.

### Biến thể E — Thay đổi schema event dùng chung

Một PR đổi field trong event được nhiều consumer sử dụng.

**Câu hỏi:** Gate nào phải chạy trước merge và release?

**Gợi ý:** Contract compatibility với consumer/provider, kiểm thử versioning và rollout theo pha. Không chỉ compile mô-đun producer.

### Biến thể F — Load test thất bại vì môi trường

Performance gate không chạy được do môi trường test bị hỏng trong ngày release.

**Câu hỏi:** Có thể phát hành không?

**Gợi ý:** Không tự coi là pass. Quyết định phụ thuộc mức rủi ro và policy release; có thể chờ môi trường, dùng môi trường thay thế đã được xác nhận hoặc xin waiver có thẩm quyền, phạm vi và thời hạn.

## 21. Bài nộp cuối cùng

Hãy hoàn thiện một đề xuất tối thiểu gồm:

- Gate matrix cho tất cả nhóm kiểm tra.
- Dependency graph có nhánh song song và điều kiện trigger.
- Lifecycle matrix cho local, PR, main, release và nightly.
- Quyết định cho PR-A, PR-B, PR-C và PR-D.
- Quy tắc cho failed, skipped, not run, flaky, infra failure và waiver.
- Policy merge/release gắn với revision cuối.
- Một đoạn giải thích vì sao thiết kế cân bằng được thời gian phản hồi, chi phí và rủi ro.

Bạn có thể dùng lời giải tham khảo để đối chiếu, nhưng hãy ghi rõ nơi bạn chọn khác và **bằng chứng/bối cảnh nào khiến lựa chọn đó hợp lý hơn**.

---

**Ghi nhớ:** Đề xuất quality gate phải bắt đầu từ **rủi ro và hợp đồng của mô-đun**, sau đó mới chọn công cụ và thứ tự. Đưa kiểm tra nhanh lên sớm, chờ đúng dependency cho compile và test, chạy song song có kiểm soát, mở rộng integration/contract/performance khi thay đổi chạm các ranh giới đó. Phân biệt blocking, advisory và conditional; giữ trạng thái skipped/not run trung thực; gắn kết quả với revision cuối và quản lý waiver có owner, lý do cùng thời hạn. Một thiết kế tốt chứng minh được **vì sao từng gate tồn tại, khi nào phải chạy và điều gì đủ để merge hoặc release an toàn**.
