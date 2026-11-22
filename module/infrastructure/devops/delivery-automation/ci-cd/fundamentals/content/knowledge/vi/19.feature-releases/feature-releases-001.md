# Phân biệt triển khai phần mềm với mở tính năng cho người dùng

Trong CI/CD, hai việc thường bị gộp làm một là **triển khai phần mềm (deployment)** và **phát hành tính năng (feature release)**. Triển khai đưa phiên bản ứng dụng đến môi trường chạy. Phát hành quyết định người dùng nào được phép nhìn thấy hoặc sử dụng một khả năng mới. Hai việc có thể diễn ra cùng lúc, nhưng không bắt buộc phải như vậy.

Một nhóm có thể triển khai code mới lên production vào buổi sáng nhưng giữ tính năng ở trạng thái tắt. Sau khi kiểm tra vận hành, nhóm bật tính năng cho nhân viên nội bộ, một nhóm nhỏ người dùng rồi mở rộng dần. Cách tách này giảm áp lực phải hoàn thành mọi quyết định sản phẩm và vận hành trong cùng một lần deploy, đồng thời cho phép kiểm soát phạm vi ảnh hưởng khi có vấn đề.

## 1. Deployment và feature release giải quyết hai câu hỏi khác nhau

**Deployment** trả lời: phiên bản phần mềm nào đang được cài đặt hoặc chạy trên môi trường?

**Feature release** trả lời: ai được sử dụng tính năng nào, vào thời điểm nào và theo điều kiện nào?

| Khía cạnh | Deployment | Feature release |
|---|---|---|
| Đối tượng thay đổi | Binary, container image, package, manifest | Trạng thái flag, rule, cohort hoặc cấu hình phát hành |
| Phạm vi | Instance, cluster, service, region hoặc môi trường | Người dùng, tenant, nhóm, request hoặc tỷ lệ traffic |
| Công cụ thường dùng | CI/CD, orchestrator, deployment controller | Feature flag service, config service, release control plane |
| Kết quả | Phiên bản code mới có mặt trong môi trường | Một nhóm đối tượng được tiếp cận khả năng mới |
| Cách quay lại | Rollback hoặc roll forward artifact | Tắt flag, thu hẹp audience hoặc đổi rule |
| Rủi ro chính | Lỗi khởi động, rollout, tài nguyên hoặc tương thích | Phân phối sai đối tượng, logic mới gây lỗi, metric xấu |

Ví dụ, một ứng dụng thanh toán có phiên bản 2.8 chứa cả luồng thanh toán cũ và luồng thanh toán mới. Pipeline triển khai image 2.8 lên production. Flag new-payment-flow vẫn tắt nên mọi người tiếp tục dùng luồng cũ. Sau khi nhóm kiểm tra smoke test và bật cho nhân viên nội bộ, tính năng mới bắt đầu được phát hành mà không cần build hoặc deploy lại.

Tách hai hoạt động cho phép đội kỹ thuật kiểm chứng khả năng chạy của code trước khi đội sản phẩm quyết định mở rộng trải nghiệm người dùng.

## 2. Mô hình triển khai trước, phát hành sau

Một quy trình phổ biến có thể chia thành các giai đoạn:

1. Build artifact bất biến và kiểm thử trong CI.
2. Triển khai artifact lên môi trường đích với tính năng mới ở trạng thái tắt.
3. Xác minh service khởi động, health check, log và metric cơ bản.
4. Bật tính năng cho nhóm nội bộ hoặc tài khoản thử nghiệm.
5. Quan sát lỗi, latency, conversion và các chỉ số nghiệp vụ.
6. Mở rộng audience theo từng bước khi điều kiện đạt.
7. Phát hành đầy đủ khi có đủ bằng chứng.
8. Xóa code path cũ và flag tạm thời khi không còn cần rollback bằng toggle.

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A[Build và test artifact] --> B[Deploy lên production]
    B --> C[Feature flag mặc định OFF]
    C --> D[Smoke test và xác minh vận hành]
    D --> E[Enable nội bộ]
    E --> F[Rollout theo cohort]
    F --> G{Metric và guardrail đạt?}
    G -- Không --> H[Disable flag hoặc thu hẹp rollout]
    G -- Có --> I[Mở rộng audience]
    I --> J[Release hoàn tất]
    J --> K[Loại bỏ flag và code cũ]
~~~

Trong mô hình này, deploy không đồng nghĩa người dùng đã thấy tính năng. Tính năng chỉ được mở khi policy phát hành cho phép.

Tách giai đoạn không có nghĩa mọi lần release đều cần feature flag. Một thay đổi tài liệu, sửa lỗi nhỏ hoặc tính năng không có rủi ro về audience có thể được deploy và phát hành cùng lúc. Feature flag hữu ích khi cần kiểm soát thời điểm, đối tượng hoặc khả năng tắt nhanh.

## 3. Feature flag hoạt động như thế nào?

Feature flag là một điều kiện quyết định một nhánh hành vi trong ứng dụng có được thực thi hay không. Ứng dụng đánh giá flag theo key và ngữ cảnh, sau đó chọn code path tương ứng.

Ví dụ cấu hình:

~~~yaml
flags:
  new-payment-flow:
    enabled: false
    description: "Luồng thanh toán mới"
    owner: payments-team
    environment: production
    defaultValue: false
~~~

Ứng dụng có thể kiểm tra flag trước khi chọn luồng xử lý:

~~~java
public PaymentResult processPayment(
        PaymentRequest request,
        EvaluationContext context) {

    if (featureFlags.isEnabled("new-payment-flow", context)) {
        return newPaymentProcessor.process(request);
    }

    return legacyPaymentProcessor.process(request);
}
~~~

Trong ví dụ, flag quyết định code path nào được gọi. Cả hai processor đều được đóng gói trong artifact đã deploy. Thay đổi trạng thái flag không cần build lại image nếu hệ thống flag hỗ trợ cập nhật cấu hình độc lập.

Một feature flag thường có các thành phần:

- **Key:** định danh ổn định, ví dụ new-payment-flow.
- **Default value:** giá trị dự phòng nếu không lấy được rule.
- **Environment:** môi trường mà rule áp dụng.
- **Targeting rules:** điều kiện chọn người dùng hoặc tenant.
- **Rollout percentage:** tỷ lệ đối tượng được bật.
- **Owner:** nhóm chịu trách nhiệm.
- **Description:** lý do và mục đích.
- **Lifecycle metadata:** ngày tạo, ngày xem xét và ngày dự kiến xóa.

Flag cần được đặt tên rõ nghĩa và có owner. Một key chung chung như enable-new hoặc flag-123 khó hiểu khi cần điều tra sự cố.

## 4. Các loại feature flag và cách sử dụng

Không phải flag nào cũng có cùng vòng đời hoặc mục đích.

| Loại flag | Mục đích | Thời gian tồn tại thường gặp |
|---|---|---|
| Release flag | Giữ code mới ở trạng thái tắt cho đến khi sẵn sàng phát hành | Tạm thời, nên xóa sau release |
| Operational flag | Bật/tắt chức năng để bảo vệ hệ thống khi tải hoặc dependency gặp vấn đề | Có thể tồn tại lâu hơn, cần owner |
| Experiment flag | Chia nhóm để so sánh trải nghiệm hoặc kết quả thử nghiệm | Theo thời gian thí nghiệm |
| Permission/entitlement flag | Kiểm soát khả năng theo gói dịch vụ hoặc quyền sản phẩm | Có thể dài hạn, cần tích hợp authorization đúng cách |
| Kill switch | Tắt nhanh một chức năng có rủi ro cao | Có thể dài hạn, cần kiểm soát thao tác |

Một số hệ thống gọi tất cả các loại trên là feature flag, nhưng nhóm nên phân loại để biết flag nào cần xóa, flag nào cần audit thường xuyên và flag nào liên quan đến chính sách quyền truy cập.

Flag không nên thay thế hệ thống authorization. Ví dụ, một flag bật chức năng quản trị không chứng minh người gọi có quyền quản trị. Ứng dụng vẫn phải kiểm tra danh tính và quyền truy cập ở server cho từng thao tác nhạy cảm.

## 5. Phát hành theo nhóm người dùng

Targeting rules xác định đối tượng được bật tính năng. Có thể chọn theo:

- Nhóm nhân viên nội bộ.
- Danh sách tài khoản thử nghiệm.
- Tenant hoặc tổ chức cụ thể.
- Khu vực địa lý nếu phù hợp với sản phẩm và chính sách.
- Gói dịch vụ hoặc trạng thái đăng ký.
- Phiên bản client hoặc loại thiết bị.
- Cohort được chọn bằng tỷ lệ phần trăm.

Ví dụ policy:

~~~yaml
flags:
  new-payment-flow:
    enabled: true
    targeting:
      - name: internal-users
        attribute: userGroup
        operator: equals
        value: employee
        variation: on
      - name: pilot-tenants
        attribute: tenantId
        operator: in
        values:
          - tenant-104
          - tenant-208
        variation: on
    defaultVariation: off
~~~

Rule chỉ là ví dụ minh họa. Hệ thống thực tế cần xác định thứ tự ưu tiên, cách xử lý rule chồng lấn và giá trị mặc định khi không có context.

Đối với rollout theo phần trăm, nên dùng phép phân nhóm ổn định dựa trên định danh phù hợp như user ID hoặc tenant ID. Nếu chọn ngẫu nhiên lại ở mỗi request, cùng một người có thể lúc thấy tính năng mới, lúc thấy tính năng cũ; điều đó gây trải nghiệm không nhất quán và làm sai dữ liệu đo lường.

Không đưa thông tin cá nhân nhạy cảm vào targeting context nếu không thực sự cần. Dùng định danh nội bộ hoặc thuộc tính đã được giảm thiểu, kiểm soát quyền truy cập và thời hạn lưu.

## 6. Rollout tăng dần và progressive delivery

Progressive delivery là cách mở rộng thay đổi từng bước, sử dụng metric và guardrail để quyết định có tiếp tục hay dừng. Feature flag có thể điều khiển tỷ lệ người dùng nhận tính năng, trong khi deployment strategy điều khiển phiên bản code nhận traffic.

Một kế hoạch rollout minh họa:

| Giai đoạn | Audience | Điều kiện chuyển bước |
|---|---:|---|
| Internal | Nhân viên và tester | Luồng chính hoạt động, không có lỗi nghiêm trọng |
| Pilot | Một nhóm tenant được chọn | Error rate, latency và phản hồi đạt ngưỡng |
| Small rollout | 1-5% người dùng phù hợp | Metric ổn định qua khoảng quan sát đã định |
| Medium rollout | 10-25% | Không tăng lỗi hoặc giảm chỉ số nghiệp vụ |
| Broad rollout | 50-75% | Guardrail tiếp tục đạt |
| General availability | 100% audience mục tiêu | Đã được phê duyệt và có kế hoạch vận hành |

Các tỷ lệ trên chỉ là ví dụ. Tính năng có lượng traffic thấp hoặc rủi ro cao có thể cần giai đoạn dài hơn; tính năng ít tác động có thể dùng lộ trình đơn giản hơn.

Mỗi giai đoạn cần có:

- Audience hoặc tỷ lệ cụ thể.
- Thời gian quan sát tối thiểu.
- Chỉ số thành công.
- Ngưỡng dừng.
- Người chịu trách nhiệm quyết định.
- Hành động nếu guardrail không đạt.

Không nên tăng tỷ lệ chỉ vì không thấy lỗi trong vài phút đầu. Một số lỗi chỉ xuất hiện khi có traffic lớn, khi người dùng đi qua luồng hiếm hoặc khi hệ thống xử lý dữ liệu thực tế.

## 7. Phân biệt feature rollout với canary deployment

Canary deployment và feature rollout đều mở rộng thay đổi theo từng bước, nhưng chúng kiểm soát hai đối tượng khác nhau.

- **Canary deployment:** điều khiển lượng traffic đi đến phiên bản ứng dụng mới hoặc một nhóm instance mới.
- **Feature rollout:** điều khiển đối tượng được chạy một tính năng cụ thể trong code.

| Tình huống | Canary deployment | Feature rollout |
|---|---|---|
| Hai phiên bản binary cùng tồn tại | Thường có | Không bắt buộc |
| Chia traffic theo instance hoặc route | Có | Có thể không |
| Chọn người dùng theo tenant hoặc cohort | Có thể | Là trường hợp phổ biến |
| Tắt riêng một tính năng | Không nhất thiết | Có |
| Quay về code cũ | Chuyển traffic hoặc rollback deployment | Tắt flag nếu code cũ vẫn còn |
| Phạm vi quan sát | Phiên bản/service | Tính năng/đối tượng |

Có thể kết hợp hai cơ chế. Ví dụ, triển khai image mới trên 10% instance, sau đó chỉ bật tính năng mới cho 1% tenant đang đi qua các instance đó. Như vậy, nhóm có thể tách rủi ro do binary mới khỏi rủi ro do logic tính năng mới.

Không nên gọi mọi rollout theo phần trăm là canary deployment. Cần nói rõ phần trăm đang đại diện cho traffic, instance, tenant hay người dùng.

## 8. Kill switch và khả năng tắt nhanh

Kill switch là một cơ chế cho phép vô hiệu hóa chức năng khi có sự cố. Nó hữu ích với chức năng có thể gây ảnh hưởng lớn đến latency, chi phí, dữ liệu hoặc dịch vụ phụ thuộc.

Ví dụ:

- Tắt xử lý thanh toán qua nhà cung cấp mới.
- Ngừng tạo báo cáo nặng khi hệ thống quá tải.
- Tắt một luồng tìm kiếm mới gây tăng latency.
- Ngừng gửi thông báo khi provider gặp sự cố.
- Chuyển về code path cũ khi tính năng mới có lỗi.

Một kill switch cần được thiết kế trước khi phát hành:

1. Có key và owner rõ ràng.
2. Giá trị mặc định phù hợp khi hệ thống flag không truy cập được.
3. Có người hoặc quy trình được quyền bật/tắt.
4. Thay đổi được ghi audit.
5. Ứng dụng nhận cập nhật trong thời gian dự kiến.
6. Có metric xác nhận chức năng đã thực sự bị tắt.
7. Có runbook nêu rõ tác động phụ khi tắt.

Kill switch không đảm bảo mọi request đang xử lý sẽ dừng ngay. Nếu ứng dụng cache flag, cần xác định TTL, cơ chế push update và hành vi khi mất kết nối. Với chức năng nhạy cảm, có thể cần kiểm tra flag thường xuyên hơn hoặc dùng cơ chế ngắt ở tầng service.

Không nên để kill switch làm hỏng luồng dữ liệu. Ví dụ, tắt một consumer có thể khiến message backlog tăng; tắt ghi dữ liệu có thể ảnh hưởng tính nhất quán. Runbook phải mô tả hệ quả và cách phục hồi sau khi bật lại.

## 9. Theo dõi metric và guardrail khi phát hành

Feature rollout cần được điều khiển bằng bằng chứng. Trước khi bật tính năng, hãy xác định metric nào phản ánh chất lượng kỹ thuật và kết quả nghiệp vụ.

| Nhóm metric | Ví dụ | Mục đích |
|---|---|---|
| Reliability | Error rate, exception count, timeout | Phát hiện lỗi chức năng |
| Performance | p50/p95/p99 latency, throughput | Phát hiện suy giảm hiệu năng |
| Resource | CPU, memory, connection pool, queue depth | Phát hiện áp lực hạ tầng |
| Business | Checkout completion, payment success, conversion | Đo kết quả người dùng |
| Experience | Crash rate, abandonment, support tickets | Đánh giá trải nghiệm |
| Dependency | Provider error, API 429/5xx | Phát hiện lỗi dịch vụ ngoài |

Cần so sánh nhóm bật flag với nhóm đối chứng phù hợp, đồng thời kiểm soát khác biệt về thời gian, loại người dùng và tải. Một metric tổng hợp toàn hệ thống có thể che khuất lỗi chỉ xảy ra trong nhóm pilot.

Ví dụ, payment success rate giảm từ 99,8% xuống 97,5% trong cohort mới là tín hiệu cần điều tra, dù error rate tổng thể chưa tăng nhiều. Ngưỡng cụ thể phải dựa trên baseline và yêu cầu dịch vụ.

Đặt guardrail trước khi rollout. Nếu error rate vượt ngưỡng, latency p95 tăng mạnh hoặc conversion giảm bất thường, dừng mở rộng và cân nhắc tắt flag. Không chờ đến khi toàn bộ audience được bật mới xem xét số liệu.

## 10. Đánh giá tính an toàn của flag trong ứng dụng

Flag là một nhánh logic chạy trong ứng dụng nên cần được kiểm thử như code thông thường.

Cần kiểm tra:

- Hành vi khi flag tắt.
- Hành vi khi flag bật.
- Hành vi khi flag service không truy cập được.
- Hành vi khi context thiếu hoặc không hợp lệ.
- Rule chồng lấn và thứ tự ưu tiên.
- Cache và thời gian lan truyền thay đổi.
- Tính nhất quán giữa các instance.
- Tương thích với dữ liệu và schema hiện tại.
- Không để client tự quyết định quyền truy cập nhạy cảm.

Đối với backend, nên đánh giá flag ở server bằng context đã được xác thực. Không tin giá trị user ID hoặc role do client gửi nếu chưa xác minh. Với frontend, flag có thể điều khiển hiển thị giao diện, nhưng API phía server vẫn phải kiểm tra quyền.

Khi flag service lỗi, không có một giá trị fallback phù hợp cho mọi flag. Release flag thường có thể mặc định tắt để giữ code path đã ổn định. Một operational flag bảo vệ hệ thống có thể cần fallback khác. Hãy xác định default theo hậu quả an toàn của từng tính năng và kiểm thử trường hợp đó.

## 11. Tương thích dữ liệu và database khi tách deploy khỏi release

Một tính năng mới có thể yêu cầu thêm cột, bảng, index hoặc cấu trúc message. Nếu migration phá vỡ khả năng chạy của phiên bản cũ, việc giữ flag ở trạng thái tắt cũng không đủ an toàn.

Nên dùng chiến lược expand-and-contract:

1. **Expand:** thêm schema mới theo cách tương thích ngược, chưa xóa cấu trúc cũ.
2. Deploy code có thể hoạt động với cả schema cũ và mới.
3. Giữ flag tắt, kiểm tra code mới và migration.
4. Bật tính năng cho cohort nhỏ.
5. Theo dõi dữ liệu và xác minh không còn consumer cũ.
6. **Contract:** chỉ xóa cấu trúc cũ sau khi tất cả phiên bản liên quan đã chuyển đổi và không còn cần rollback về code cũ.

Ví dụ, nếu tính năng mới cần trường payment_method_v2, có thể thêm trường trước, cho code mới ghi/đọc theo cách tương thích, rồi bật flag. Sau khi phát hành ổn định và phiên bản cũ không còn chạy, mới lên kế hoạch bỏ trường cũ.

Không nên xóa dữ liệu hoặc schema chỉ vì flag đã bật 100%. Có thể còn job nền, consumer cũ hoặc phiên bản ứng dụng khác đang phụ thuộc vào cấu trúc cũ.

## 12. Quản lý flag như một cấu hình có quyền và audit

Feature flag có thể thay đổi hành vi production mà không cần deploy. Vì vậy, quyền sửa flag có thể tương đương quyền thay đổi một phần hành vi hệ thống.

Cần kiểm soát:

- Ai được tạo, sửa, bật hoặc tắt flag.
- Ai được thay đổi targeting rules và rollout percentage.
- Flag nào cần approval khi thay đổi ở production.
- Ai là owner của flag.
- Mọi thay đổi có audit log và timestamp.
- Có khả năng khôi phục giá trị trước đó.
- Rule có giới hạn môi trường và audience.
- API token quản lý flag được bảo vệ như secret.

Không nên cấp quyền quản trị flag cho mọi developer hoặc mọi pipeline. Một workflow deploy không nhất thiết phải có quyền bật tính năng cho toàn bộ người dùng. Tách quyền deploy và quyền release giúp kiểm soát rủi ro rõ hơn.

Với thay đổi khẩn cấp, cần có quy trình break-glass được audit. Sau khi xử lý xong, nhóm phải rà soát thay đổi và khôi phục quyền tạm thời.

## 13. Tránh flag tồn tại quá lâu

Release flag thường được tạo để giảm rủi ro trong giai đoạn chuyển đổi. Nếu không xóa sau khi tính năng ổn định, code sẽ tích lũy nhiều nhánh cũ và mới.

Hậu quả có thể gồm:

- Tăng số tổ hợp trạng thái cần kiểm thử.
- Code path cũ không còn được chạy nhưng vẫn phải bảo trì.
- Điều kiện lồng nhau làm giảm khả năng đọc hiểu.
- Rule targeting lỗi thời.
- Người vận hành không biết flag nào còn tác dụng.
- Một flag cũ vô tình được bật lại và kích hoạt code không còn tương thích.

Mỗi flag nên có metadata:

| Trường | Ví dụ |
|---|---|
| Key | new-payment-flow |
| Type | release |
| Owner | payments-team |
| Created | 2026-11-01 |
| Review date | 2026-11-20 |
| Planned removal | 2026-12-15 |
| Default after release | true |
| Cleanup issue | PAY-482 |

Khi tính năng đã được mở hoàn toàn và không còn cần toggle để rollback, nhóm nên xóa flag, nhánh code cũ và rule không còn dùng. Có thể giữ operational kill switch lâu dài nếu có lý do vận hành, nhưng phải có owner và quy trình review riêng.

## 14. Khi nào nên rollback deployment và khi nào chỉ cần tắt flag?

Tắt flag và rollback artifact là hai hành động khác nhau.

| Tình huống | Hành động thường phù hợp |
|---|---|
| Tính năng mới gây lỗi nhưng code cũ vẫn hoạt động trong cùng artifact | Tắt flag hoặc thu hẹp audience |
| Binary mới gây crash trước khi flag được đánh giá | Rollback hoặc roll forward artifact |
| Lỗi chỉ xuất hiện với một cohort | Tắt flag cho cohort đó và điều tra |
| Cấu hình flag sai | Khôi phục rule hoặc version cấu hình trước |
| Database migration không tương thích | Xử lý migration/data theo runbook; rollback code có thể chưa đủ |
| Dependency hoặc nền tảng gặp sự cố | Dùng kill switch, fallback hoặc chuyển traffic theo thiết kế |

Trước khi tắt flag, xác định hành vi fallback có an toàn không. Nếu code path cũ đã bị xóa hoặc dữ liệu mới không còn tương thích, tắt flag có thể làm lỗi nghiêm trọng hơn.

Trước khi rollback artifact, kiểm tra migration, config và các thay đổi phụ thuộc. Rollback image không tự động khôi phục schema, message đã gửi hoặc giao dịch đã ghi.

## 15. Ví dụ một lần phát hành tính năng từ đầu đến cuối

Giả sử nhóm phát triển luồng thanh toán mới cho dịch vụ Java:

1. Developer thêm code mới sau flag new-payment-flow, giữ default là false.
2. CI chạy unit test cho cả nhánh flag bật và tắt, integration test và static analysis.
3. Build pipeline tạo image 2.8.1 bất biến và lưu digest.
4. Deployment pipeline triển khai image lên staging, sau đó production.
5. Smoke test xác minh service và luồng thanh toán cũ hoạt động.
6. Release owner bật flag cho nhân viên nội bộ.
7. Nhóm quan sát payment success rate, latency, provider errors và log.
8. Flag được mở cho một nhóm tenant pilot.
9. Nếu guardrail đạt, rollout tăng dần theo cohort.
10. Nếu lỗi tăng, flag được tắt hoặc thu hẹp phạm vi trong khi nhóm điều tra.
11. Khi tính năng ổn định, mở cho toàn bộ audience mục tiêu.
12. Nhóm xóa release flag và code path cũ theo một thay đổi riêng, có kiểm thử.

Trong toàn bộ quy trình, artifact digest không thay đổi khi mở rộng audience. Thay đổi release chủ yếu nằm ở trạng thái flag và targeting policy. Điều đó giúp phân biệt lỗi do binary mới với lỗi do tính năng mới được mở cho người dùng.

## 16. Checklist phân biệt deployment và feature release

Trước khi phát hành một tính năng có kiểm soát, hãy kiểm tra:

- [ ] Đã xác định rõ deployment đưa phiên bản code nào lên môi trường.
- [ ] Đã xác định riêng điều kiện và audience của feature release.
- [ ] Artifact được build một lần và có định danh bất biến.
- [ ] Feature flag có default value an toàn và owner rõ ràng.
- [ ] Code path bật và tắt đều được kiểm thử.
- [ ] Targeting rules dùng context đã xác thực và không lộ dữ liệu nhạy cảm.
- [ ] Rollout có cohort, tỷ lệ, thời gian quan sát và guardrail.
- [ ] Metric kỹ thuật và nghiệp vụ được theo dõi theo nhóm bật/tắt.
- [ ] Có kill switch và runbook cho tính năng rủi ro cao.
- [ ] Flag service có hành vi fallback và cache được kiểm thử.
- [ ] Database migration tương thích với code cũ và mới.
- [ ] Quyền bật flag production được giới hạn và audit.
- [ ] Có tiêu chí dừng rollout và người ra quyết định.
- [ ] Có kế hoạch tắt flag, rollback artifact hoặc roll forward.
- [ ] Release flag tạm thời có thời hạn và issue cleanup.

Deployment đưa code đến nơi chạy; feature release kiểm soát ai được dùng code đó. Khi hai hoạt động được quản lý riêng, nhóm có thể xác minh phiên bản mới trước khi mở tính năng, thử nghiệm theo nhóm nhỏ, phản ứng nhanh bằng flag và phát hành có kiểm soát mà không phải build lại chỉ để thay đổi audience.

