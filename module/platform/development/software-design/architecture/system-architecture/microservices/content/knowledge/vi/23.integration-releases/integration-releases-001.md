# Pipeline độc lập cho từng dịch vụ và điều kiện phát hành tự chủ

## 1. Bối cảnh và mục tiêu

Trong kiến trúc microservices, mỗi dịch vụ đảm nhiệm một năng lực nghiệp vụ, có vòng đời thay đổi riêng và thường do một nhóm chịu trách nhiệm. Nếu mọi dịch vụ phải chờ cùng một pipeline tổng hoặc cùng một đợt triển khai, hệ thống vẫn bị ràng buộc theo nhịp phát hành chung dù đã chia nhỏ mã nguồn.

**Pipeline độc lập** là luồng tự động kiểm tra, đóng gói và triển khai dành cho một dịch vụ cụ thể. **Phát hành tự chủ** là khả năng nhóm sở hữu dịch vụ quyết định khi nào đưa một phiên bản đã đủ điều kiện vào môi trường đích, trong phạm vi các quy tắc an toàn chung. Tự chủ không có nghĩa bỏ qua kiểm thử, bảo mật, hợp đồng tích hợp hoặc khả năng khôi phục.

Sau bài này, người học có thể:
- Phân biệt độc lập về mã nguồn, build, pipeline, artifact và triển khai.
- Thiết kế đường đi từ commit tới production cho từng microservice với các cổng kiểm soát rõ ràng.
- Xác định điều kiện để phát hành một dịch vụ mà không phải đồng bộ phát hành toàn hệ thống.
- Xử lý tương thích API, sự kiện và schema dữ liệu trong quá trình phát hành lệch phiên bản.
- Chọn chiến lược rollout, quan sát và khôi phục phù hợp với rủi ro thay đổi.

## 2. Độc lập thực sự nghĩa là gì?

Một dịch vụ có thể ở repository riêng nhưng vẫn không phát hành độc lập nếu phải dùng phiên bản thư viện chung mới nhất, phải chờ dịch vụ khác nâng cấp API hoặc mọi nhóm đều cần họp để chốt một release train. Ngược lại, nhiều dịch vụ cùng nằm trong monorepo vẫn có thể phát hành độc lập nếu hệ thống build và triển khai xác định đúng phạm vi ảnh hưởng.

| Khía cạnh | Mục tiêu độc lập | Điều cần giữ chung |
| --- | --- | --- |
| Nguồn mã | Thay đổi dịch vụ A không mặc định kích hoạt release B | Chuẩn mã nguồn, quy tắc review, quản lý dependency |
| CI | A có bộ kiểm thử, build và kết quả riêng | Mẫu pipeline, quy tắc tối thiểu về chất lượng |
| Artifact | A tạo image/package bất biến, định danh riêng | Registry, ký artifact, truy xuất nguồn gốc và SBOM |
| CD | A triển khai và rollback riêng, có release history riêng | Cơ chế phân quyền, cấu hình môi trường, quan sát |
| Nghiệp vụ | A có thể tiến hóa giao diện theo hướng tương thích | Hợp đồng giữa producer và consumer, chính sách deprecation |
| Vận hành | Nhóm A sở hữu lỗi và SLO của A | Chính sách an toàn production và xử lý sự cố liên dịch vụ |

Mô hình mong muốn là **tự chủ trong giới hạn chuẩn nền tảng**: platform team cung cấp đường ray triển khai và kiểm soát bắt buộc, còn service team chọn thời điểm phát hành khi đã đi qua các điều kiện đó.

## 3. Luồng CI/CD tham chiếu cho một microservice

~~~mermaid
flowchart TD
    A[Commit hoặc pull request của dịch vụ] --> B[Lint, unit test, kiểm tra mã]
    B --> C[Build và kiểm tra bảo mật]
    C --> D[Integration và contract tests]
    D --> E[Đóng gói artifact bất biến]
    E --> F[Đưa artifact lên registry]
    F --> G[Triển khai vào môi trường kiểm chứng]
    G --> H[Smoke test và kiểm tra tương thích]
    H --> I{Release gate đạt?}
    I -- Không --> J[Chặn phát hành và tạo tín hiệu xử lý]
    I -- Có --> K[Rollout từng phần ở production]
    K --> L{Tín hiệu vận hành ổn định?}
    L -- Không --> M[Dừng rollout, rollback hoặc roll forward]
    L -- Có --> N[Mở rộng traffic và chốt release]
~~~

Các giai đoạn có thể triển khai bằng GitHub Actions, GitLab CI, Jenkins hoặc một hệ thống tương đương. Hình trên mô tả **quan hệ trách nhiệm**, không yêu cầu mỗi dịch vụ sở hữu một công cụ CI riêng.

**CI trên pull request** kiểm chứng thay đổi có thể hợp nhất an toàn. **CI trên nhánh phát hành** tạo artifact được lưu và định danh. **CD** mang đúng artifact đã được kiểm chứng qua các môi trường; tránh rebuild bằng nguồn mã mới ở từng môi trường vì kết quả có thể khác nhau.

Một pipeline hữu ích phải tạo ra bằng chứng: commit, phiên bản, digest image, kết quả test, bản kiểm tra dependency, môi trường đích, lịch sử ai hoặc chính sách nào phê duyệt, và kết quả rollout.

## 4. Kích hoạt đúng dịch vụ cần chạy

**Nhiều repository:** pipeline của catalog-service được kích hoạt bởi thay đổi trong repository catalog-service, các cập nhật cấu hình/secret liên quan và những trigger thủ công hoặc định kỳ được cho phép.

**Monorepo:** pipeline của catalog-service quan sát các đường dẫn thuộc dịch vụ và phụ thuộc build thực tế của nó. Thay đổi ở shared library phải kích hoạt kiểm tra cho các dịch vụ thực sự phụ thuộc thư viện đó; thay đổi README không liên quan không nên gây phát hành hàng loạt.

Ví dụ quy ước kích hoạt dạng mô tả:

~~~yaml
service: catalog-service
ci_triggers:
  - pull_request_affecting: services/catalog/**
  - dependency_change_affecting: services/catalog
  - scheduled_security_scan
cd_trigger:
  - successful_build_on_protected_main
artifact:
  image: registry.example/catalog-service
  identity: immutable_digest
~~~

Đây là **cấu hình minh họa**, không phải cú pháp có thể nạp trực tiếp vào một công cụ CI. Khi hiện thực hóa, cần xác định đồ thị phụ thuộc, đường dẫn cấu hình triển khai, phiên bản image và quyền của trigger. Không để pipeline của A thực hiện lệnh deploy B chỉ vì hai dịch vụ cùng dựa vào một thư viện.

## 5. Các cổng kiểm soát chất lượng của từng pipeline

Mỗi cổng phải trả lời được: **kiểm tra điều gì, bằng chứng nào cho thấy đạt, ai xử lý khi thất bại, và có cho phép đi tiếp hay không**.

| Giai đoạn | Điều kiện gợi ý | Khi không đạt |
| --- | --- | --- |
| Review và build | Nhánh được bảo vệ; review theo quy định; build lặp lại được | Không merge hoặc không tạo release |
| Unit/static analysis | Unit test, lint, quy tắc chất lượng và phát hiện lỗi nghiêm trọng đạt ngưỡng | Chặn build |
| Security/supply chain | Dependency scan, secret scan, image scan, quy tắc license, provenance phù hợp | Chặn khi vi phạm chính sách; ngoại lệ phải được ghi nhận có thời hạn |
| Tích hợp | Test với database, broker và các adapter chính trong môi trường kiểm soát | Chặn đưa artifact đi tiếp |
| Contract | API/event của phiên bản mới còn đáp ứng hợp đồng consumer đang được hỗ trợ | Chặn phát hành breaking change |
| Kiểm chứng triển khai | Startup, readiness, migration, smoke test và xác thực cấu hình/secrets thành công | Chặn promote |
| Production rollout | SLO, error rate, latency, saturation và tín hiệu nghiệp vụ trong ngưỡng chính sách | Tạm dừng, rollback hoặc roll forward |

Ngưỡng cụ thể phải lấy từ yêu cầu nghiệp vụ, mức độ rủi ro và SLO thực tế của từng dịch vụ. Một chính sách chung có thể bắt buộc các loại kiểm tra, nhưng không nên áp một giá trị latency tùy ý cho mọi service.

Một số kiểm tra tích hợp nặng hoặc kiểm thử hỗn loạn có thể chạy theo lịch hay trước thay đổi rủi ro cao; không phải lúc nào cũng cần đặt toàn bộ vào đường đi nhanh của mọi commit. Cần chỉ rõ loại test nào là **release gate** bắt buộc, loại nào là tín hiệu bổ sung và chính sách xử lý khi phát hiện vấn đề muộn.

## 6. Artifact bất biến và truy xuất nguồn gốc

Nguyên tắc quan trọng: **build một lần, phát hành cùng một artifact**.

1. CI build image/package và gắn định danh phiên bản cùng mã commit.
2. Registry lưu artifact theo digest bất biến. Tag có thể thuận tiện để tra cứu nhưng không thay cho digest.
3. Pipeline ghi kết quả kiểm tra, provenance, SBOM hoặc chữ ký theo chính sách tổ chức.
4. CD đưa chính digest đã được chấp thuận qua các môi trường. Khác biệt giữa staging và production nằm ở cấu hình được quản lý, không ở một lần build lại.
5. Mỗi triển khai ghi dịch vụ, môi trường, digest trước/sau, thời điểm, người hoặc automation kích hoạt, kết quả quan sát.

Ví dụ lịch sử phát hành: catalog-service phiên bản 2.8.4 trỏ tới digest sha256:...; production đang chạy 2.8.3; chuyển đổi chỉ ảnh hưởng deployment của catalog-service. Khi sự cố xảy ra, lịch sử này giúp xác định chính xác thứ đã thay đổi và artifact có thể khôi phục.

Không đưa secret vào image hoặc log. Dùng secret manager, danh tính workload, quyền tối thiểu và cơ chế cấp credential ngắn hạn như OIDC khi nền tảng hỗ trợ. Tách rõ quyền build, quyền ghi registry và quyền deploy production.

## 7. Điều kiện để một dịch vụ được phát hành tự chủ

Dịch vụ chỉ thật sự có khả năng phát hành độc lập khi **đồng thời** thỏa mãn các nhóm điều kiện sau.

### 7.1. Ranh giới sở hữu rõ ràng

Có nhóm chịu trách nhiệm code, pipeline, cấu hình, dữ liệu, vận hành và xử lý sự cố của dịch vụ. Tài nguyên triển khai, namespace, service account và quyền CI/CD được tách đủ để release A không vô tình ghi đè B. Hạ tầng dùng chung vẫn được quản lý theo chuẩn chung.

### 7.2. Hợp đồng liên dịch vụ tương thích

API mới cần giữ hành vi đã cam kết với consumer cũ trong cửa sổ tương thích. Hợp đồng REST/gRPC có thể kiểm chứng bằng contract tests; event cần có schema evolution rule. Không giả định producer và mọi consumer đều nâng cấp cùng lúc.

Ví dụ thay đổi response: trước đây GET /products trả về id và name; bản mới thêm optional field category. Consumer cũ thường vẫn đọc được. Ngược lại, xóa name, đổi kiểu id hoặc đổi nghĩa trạng thái có thể là breaking change dù cả hai dịch vụ vẫn build thành công.

Quy trình an toàn khi bỏ trường cũ:
1. Thêm đường đi mới tương thích và công bố hợp đồng mới.
2. Chuyển consumer sang sử dụng đường đi mới, quan sát phiên bản còn sử dụng trường cũ.
3. Chỉ loại bỏ trường cũ sau khi hết giai đoạn hỗ trợ, có bằng chứng không còn consumer phụ thuộc.

### 7.3. Thay đổi dữ liệu không bắt buộc lockstep

Dịch vụ ưu tiên sở hữu schema và quyền ghi dữ liệu của mình. Với migration, dùng chiến lược **expand → migrate → contract**:
- **Expand:** thêm cột/bảng/field mới theo cách ứng dụng cũ vẫn hoạt động.
- **Migrate:** triển khai code đọc/ghi tương thích, chuyển dữ liệu cũ dần dần, kiểm tra hoàn chỉnh.
- **Contract:** loại bỏ cấu trúc cũ sau khi chắc chắn phiên bản cũ không còn sử dụng.

Migration phải có idempotency phù hợp, đánh giá thời gian lock và tải sản xuất, kế hoạch xử lý khi chạy dở. Rollback ứng dụng không tự động đảo ngược một migration phá hủy dữ liệu; nếu không thể đảo ngược an toàn, cần kế hoạch **roll forward**.

### 7.4. Dịch vụ có khả năng vận hành khi phiên bản lệch nhau

Trong rolling/canary deployment, old và new instances cùng tồn tại. Caller và callee cũng có thể ở các version khác nhau. Cần quan tâm timeout, retry có giới hạn, idempotency, circuit breaker, xử lý duplicate event và tính tương thích message. Các biện pháp này giảm phụ thuộc vào thời điểm triển khai đồng loạt.

### 7.5. Bằng chứng vận hành đủ để đưa ra quyết định

Có health/readiness probe, log có correlation id, tracing và metric theo service/version. Mỗi release cần biết phiên bản nào tạo lỗi, người dùng hoặc flow nào bị ảnh hưởng và ngưỡng nào khiến rollout phải dừng.

### 7.6. Quy tắc phát hành minh bạch

Quy định rõ thời điểm có thể tự động promote, khi nào cần duyệt thủ công (ví dụ thay đổi dữ liệu rủi ro cao), ai có quyền override, cách lưu dấu vết phê duyệt và cách xử lý khẩn cấp. Gate có thể khác theo mức độ rủi ro mà vẫn dùng cùng nền tảng CI/CD. Không biến việc chờ một cuộc họp release tập trung thành điều kiện mặc định cho mọi thay đổi nhỏ.

## 8. Từ deploy đến release: rollout và feature flag

**Deploy** là đưa bản chạy mới lên hạ tầng. **Release** là cho người dùng hoặc hệ thống phụ thuộc sử dụng hành vi mới. Hai thời điểm có thể khác nhau nếu dùng feature flag hoặc traffic routing.

- **Rolling update:** thay thế từng phần instance, phù hợp thay đổi tương thích và khả năng quan sát tốt.
- **Canary:** cho một tỷ lệ nhỏ traffic vào bản mới, so sánh tín hiệu với baseline rồi tăng dần.
- **Blue/green:** giữ hai môi trường chạy, chuyển traffic khi phiên bản mới đạt điều kiện; cần tính toán chi phí và tác động dữ liệu.
- **Feature flag:** deploy code trước, mở tính năng riêng theo nhóm hoặc thời gian; có cơ chế dọn flag để tránh nợ kỹ thuật.

Quy tắc canary minh họa: triển khai 5% traffic, theo dõi error rate, độ trễ p95, saturation và tỷ lệ giao dịch thành công trong khoảng quan sát đã định; nếu vượt budget hoặc phát sinh lỗi nghiêm trọng thì tự động dừng, còn tín hiệu ổn định thì chuyển 25%, 50%, 100%. **Các phần trăm và ngưỡng ở đây chỉ là ví dụ**; production phải dùng dữ liệu lưu lượng, SLO và đặc điểm nghiệp vụ thực tế.

Đừng chỉ nhìn HTTP 200. Một dịch vụ thanh toán có thể vẫn phản hồi 200 nhưng ghi giao dịch sai. Release gate cần kết hợp metric hạ tầng, chất lượng request và chỉ số nghiệp vụ.

## 9. Rollback, roll forward và đường xử lý sự cố

Thiết kế cơ chế dừng phát hành trước khi phát hành lần đầu:

- **Rollback artifact:** khi phiên bản mới gây lỗi và dữ liệu/hợp đồng vẫn tương thích, quay traffic hoặc deployment về digest ổn định gần nhất.
- **Roll forward:** khi dữ liệu đã chuyển đổi hoặc việc đảo migration là nguy hiểm, triển khai bản sửa tương thích mới, có thể khóa tính năng lỗi tạm thời.
- **Kill switch/feature flag:** tắt hành vi mới nhanh mà không cần thay toàn bộ image nếu đã thiết kế sẵn.
- **Điều tra:** dùng deployment marker, tracing, logs, alert và event timeline để kết nối lỗi với phiên bản.
- **Hậu kiểm:** ghi nguyên nhân, cải thiện test/gate/runbook khi có chứng cứ thực tế.

Pipeline rollback phải được kiểm thử định kỳ trong điều kiện đại diện. Không tuyên bố rằng một nút rollback có thể phục hồi mọi loại migration, sự kiện đã phát đi hoặc tác động nghiệp vụ ngoài hệ thống.

## 10. Các kiểu phụ thuộc có thể phá vỡ phát hành tự chủ

| Phụ thuộc | Dấu hiệu | Cách cải thiện |
| --- | --- | --- |
| Shared database | Hai dịch vụ cùng sửa trực tiếp một bảng | Tách quyền sở hữu, dùng API/event và kế hoạch di trú dữ liệu |
| Shared library bắt buộc đồng phiên bản | Release A luôn yêu cầu nâng toàn bộ service | Phiên bản hóa thư viện, giữ API tương thích và dependency độc lập |
| Breaking API/event | A deploy là B lỗi ngay | Contract tests, hỗ trợ phiên bản cũ trong cửa sổ chuyển đổi |
| Release train tập trung | Mọi thay đổi chờ ngày phát hành chung | Gate tự động theo service; duyệt theo rủi ro và trách nhiệm |
| Pipeline monolith | Một job rebuild/deploy toàn bộ hệ thống | Tách trigger, artifact, promotion và release history theo service |
| Config/secrets dùng chung thiếu cô lập | Deploy A ghi đè cấu hình B | IaC/manifest tách theo service, policy phân quyền và review |
| Kiểm thử end-to-end duy nhất | Thay đổi nhỏ phải chờ test toàn hệ thống rất lâu | Dịch chuyển kiểm tra hợp đồng và tích hợp về từng service; giữ E2E cho critical journeys |

Một thay đổi có tác động xuyên dịch vụ đôi khi vẫn cần phối hợp. **Tự chủ** là giảm số thay đổi buộc phối hợp, không phủ nhận các tình huống như migration chia sẻ, thay đổi giao thức nền hoặc sự cố nghiêm trọng.

## 11. Ví dụ theo dòng thời gian: catalog-service

Giả sử hệ thống gồm catalog-service, cart-service và order-service. Nhóm catalog muốn thêm trường phân loại sản phẩm, giữ API cũ tương thích.

1. **Code review:** nhóm sửa code catalog và test, thêm field tùy chọn vào hợp đồng response. Pull request chạy CI của catalog; contract test xác nhận cart và order vẫn đọc response hợp lệ.
2. **Build:** pipeline tạo image catalog-service từ commit đã merge, scan dependency/image, phát hành digest bất biến vào registry.
3. **Staging:** CD triển khai catalog bằng digest đó; chạy smoke test, kiểm tra migration thêm cột nếu cần và test nghiệp vụ đọc danh mục.
4. **Production canary:** đưa một phần traffic qua phiên bản mới; theo dõi request latency, lỗi, các thao tác xem sản phẩm và tín hiệu cơ sở dữ liệu.
5. **Promote:** nếu các ngưỡng đạt, tăng traffic tới 100%, ghi release record và thông báo theo kênh nhóm sở hữu.
6. **Sự cố:** nếu lỗi đọc danh mục tăng, dừng canary, đưa traffic về phiên bản cũ hoặc tắt flag; lưu kết quả phục vụ điều tra.

Cart và order không cần build hoặc deploy lại vì hợp đồng vẫn tương thích. Nếu catalog muốn đổi nghĩa mã sản phẩm, nhóm phải thiết kế giai đoạn tương thích và kiểm chứng consumer trước; việc tất cả pipeline đều xanh không bảo đảm thay đổi nghiệp vụ đó an toàn.

## 12. Mô hình trách nhiệm giữa service team và platform team

**Platform team** cung cấp runner, registry, mẫu pipeline, secret management, policy engine, observability stack, GitOps/deployment controller, network policies và các tiêu chuẩn kiểm chứng tối thiểu. Họ quản lý tính tin cậy của nền tảng và các thay đổi hạ tầng dùng chung.

**Service team** sở hữu mã, test, API contract, database migration, SLO, dashboard, alert, ngưỡng rollout đặc thù, tài liệu vận hành và quyết định release theo chính sách. Mẫu pipeline phải cho phép cấu hình hợp lệ theo mức rủi ro mà không để mỗi nhóm tự bỏ security gate cốt lõi.

Một golden path hợp lý tạo sẵn pipeline khi sinh dịch vụ mới: skeleton test, build, scan, publish artifact, deploy, smoke/canary, telemetry, rollback runbook. Nhờ đó nhân rộng tự chủ mà không tạo hàng chục pipeline thiếu nhất quán.

## 13. Đo lường hiệu quả

Không đánh giá chỉ bằng số lần deploy. Theo dõi cùng nhau:

- **Deployment frequency:** tần suất phát hành thành công theo từng dịch vụ.
- **Lead time for changes:** thời gian từ thay đổi mã đến khi chạy trên production.
- **Change failure rate:** tỷ lệ phát hành gây gián đoạn hoặc cần khắc phục.
- **Failed deployment recovery time:** thời gian phục hồi sau một lần triển khai lỗi.
- **Pipeline feedback time:** thời gian developer nhận kết quả build và kiểm thử.
- **Số lần phải phối hợp release:** tỷ lệ thay đổi chỉ của một dịch vụ nhưng cần cập nhật hoặc phê duyệt dịch vụ khác.
- **Chất lượng hệ thống:** SLO, error budget, bảo mật và các chỉ số nghiệp vụ quan trọng.

Nếu deployment frequency tăng nhưng change failure rate và sự cố khách hàng tăng mạnh, quy trình chưa đạt mục tiêu. Ngược lại, gate quá chậm có thể đẩy nhóm tới thao tác thủ công; cần tối ưu tốc độ phản hồi mà vẫn giữ bằng chứng an toàn.

## 14. Bài tập áp dụng

Hệ thống có ba service: account, catalog và checkout. Checkout gọi account và catalog; cả ba dùng một monorepo. Yêu cầu: cho phép nhóm catalog phát hành một bản thêm field tùy chọn mà không triển khai lại checkout.

Hãy thiết kế:
1. Điều kiện path/dependency để chỉ pipeline liên quan chạy, bao gồm khi thay đổi thư viện dùng chung.
2. Cổng unit, integration, contract, security và smoke test dành cho catalog.
3. Cách lưu artifact digest, bản ghi phát hành và tách secret/quyền deploy.
4. Điều kiện mở canary và tín hiệu tự động dừng rollout.
5. Trình tự cần làm nếu ở lần sau muốn xóa field mà checkout cũ đang sử dụng.

Một thiết kế đạt yêu cầu phải cho thấy pipeline của catalog có thể đi tới production với hợp đồng tương thích, đồng thời các thay đổi phá vỡ hợp đồng được phát hiện trước release. Cần nêu rõ phương án xử lý migration hoặc event không thể đảo ngược thay vì chỉ ghi “rollback”.

## 15. Ghi nhớ

- Tách service chỉ hữu ích khi có thể **build, kiểm chứng, deploy và vận hành theo phiên bản riêng**.
- Tự chủ luôn đi cùng contract compatibility, ownership, security policy và observability.
- Artifact bất biến cùng bằng chứng kiểm thử giúp một release truy xuất được và đáng tin cậy.
- Progressive delivery, feature flags và kế hoạch rollback/roll forward làm giảm rủi ro triển khai.
- Mục tiêu cuối cùng là đưa thay đổi nhỏ tới người dùng nhanh, an toàn, có thể kiểm soát và không kéo theo một đợt phát hành toàn hệ thống.
