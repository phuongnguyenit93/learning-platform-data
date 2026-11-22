# Thực hiện kiểm tra khói cho các luồng quan trọng

Sau khi pipeline triển khai một phiên bản mới, trạng thái deploy thành công chỉ cho biết nền tảng đã thực hiện các bước triển khai theo yêu cầu. Nó chưa chứng minh người dùng có thể đăng nhập, tạo đơn hàng, thanh toán, đọc dữ liệu hoặc hoàn tất một luồng nghiệp vụ quan trọng.

**Kiểm tra khói (smoke test)** là tập kiểm tra nhỏ, chạy nhanh sau triển khai để xác nhận những chức năng thiết yếu vẫn hoạt động trong môi trường đích. Smoke test thường đi qua các điểm tích hợp quan trọng và xác minh kết quả quan sát được, giúp phát hiện lỗi cấu hình, kết nối, định tuyến, quyền truy cập hoặc tương thích trước khi mở rộng traffic hay kết thúc release.

Trong năng lực **DEVOPS_CI_CD_FUNDAMENTALS**, kiểm tra khói là bước nối giữa deployment và xác minh sau triển khai. Nó giúp luồng CI/CD không chỉ tạo và đưa artifact lên môi trường mà còn có bằng chứng rằng phiên bản đã triển khai có thể thực hiện các luồng quan trọng.

## 1. Mục tiêu và phạm vi của smoke test

Smoke test trả lời câu hỏi: những chức năng tối thiểu cần thiết để hệ thống có thể phục vụ người dùng có đang hoạt động không?

Một smoke test tốt thường:

- Chạy nhanh và có kết quả rõ ràng.
- Kiểm tra các luồng có ảnh hưởng lớn đến người dùng hoặc hoạt động kinh doanh.
- Đi qua những dependency thiết yếu như database, cache, broker hoặc dịch vụ xác thực.
- Xác minh kết quả nghiệp vụ có ý nghĩa, không chỉ kiểm tra tiến trình đang chạy.
- Dùng dữ liệu kiểm thử được kiểm soát và có thể dọn dẹp.
- Có timeout, log và correlation ID để điều tra.
- Có điều kiện pass/fail đủ rõ để pipeline quyết định tiếp tục, dừng hoặc rollback.

Smoke test không thay thế unit test, integration test, regression test, performance test, security test hoặc exploratory test. Các kiểm tra đó có mục tiêu và độ sâu khác nhau. Smoke test chỉ là lớp xác minh ngắn sau khi một phiên bản đã được triển khai.

Ví dụ với dịch vụ đặt hàng:

| Mức kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Process/health | Ứng dụng có đang chạy? | Process sống, endpoint liveness trả kết quả |
| Readiness | Instance có thể nhận request? | Config và dependency bắt buộc sẵn sàng |
| Smoke test | Luồng quan trọng có hoạt động? | Đọc catalog, tạo đơn test, xem trạng thái đơn |
| Regression | Các hành vi đã có còn đúng trên diện rộng? | Nhiều trường hợp nghiệp vụ, biên và lỗi |
| Performance | Hệ thống chịu tải như mong đợi? | Load test, latency và throughput |

Không nên gọi một request đến endpoint health là smoke test đầy đủ nếu luồng nghiệp vụ chính chưa được kiểm tra.

## 2. Chọn những luồng quan trọng cần kiểm tra

Không cần chạy toàn bộ test suite sau mỗi lần deploy. Hãy chọn một số luồng đại diện cho khả năng phục vụ cốt lõi, dựa trên tác động khi luồng đó hỏng.

Các câu hỏi giúp chọn luồng:

- Người dùng cần làm gì đầu tiên để sử dụng sản phẩm?
- Hành động nào tạo ra giá trị chính hoặc doanh thu?
- Thành phần nào nếu lỗi sẽ khiến nhiều chức năng không dùng được?
- Luồng nào vừa thay đổi trong release?
- Dependency hoặc cấu hình nào có rủi ro cao trong lần triển khai này?
- Có thao tác nào tạo side effect không thể đảo ngược cần dùng sandbox hoặc dữ liệu giả lập?

Ví dụ:

| Loại hệ thống | Luồng smoke test có thể chọn |
| --- | --- |
| Thương mại điện tử | Mở trang sản phẩm, đọc giá/tồn kho, tạo đơn test, đọc trạng thái đơn |
| Ngân hàng hoặc thanh toán | Xác thực test user, truy vấn số dư giả lập, tạo giao dịch sandbox và đọc kết quả |
| SaaS nhiều tenant | Đăng nhập, tải dashboard, đọc dữ liệu đúng tenant, xác minh quyền truy cập |
| Nội dung số | Mở trang, tải nội dung, tìm kiếm và xác minh quyền truy cập |
| API platform | Xác thực client, gọi endpoint chính, kiểm tra schema và dependency |
| Hệ thống xử lý nền | Gửi message test, xác minh consumer xử lý và kết quả xuất hiện trong thời hạn |

Chọn ít luồng nhưng có ý nghĩa. Nếu chỉ kiểm tra trang chủ, hệ thống vẫn có thể lỗi ở đăng nhập hoặc ghi dữ liệu. Nếu chọn quá nhiều luồng, smoke test trở thành regression suite chậm, khó ổn định và khó dùng làm cổng quyết định nhanh.

### 2.1. Bao phủ các đường đi quan trọng

Với mỗi luồng, xác định:

1. Điều kiện ban đầu và danh tính kiểm thử.
2. Request hoặc thao tác người dùng thực hiện.
3. Dependency cần thiết.
4. Kết quả nghiệp vụ mong đợi.
5. Dữ liệu hoặc side effect được tạo.
6. Cách xác minh và dọn dẹp.

Ví dụ luồng tạo đơn hàng:

~~~mermaid
flowchart TD
    A["Smoke test bắt đầu"] --> B["Xác thực test user"]
    B --> C["Đọc catalog và giá"]
    C --> D["Tạo đơn test với idempotency key"]
    D --> E["Đọc lại đơn hàng"]
    E --> F["Xác minh trạng thái và tổng tiền"]
    F --> G["Xác minh event hoặc tác vụ nền nếu cần"]
    G --> H["Dọn dữ liệu test hoặc đánh dấu test"]
    H --> I["Ghi kết quả và correlation ID"]
~~~

Nếu một bước thất bại, báo rõ bước nào, endpoint nào, mã trạng thái hoặc assertion nào không đạt. Không chỉ trả về “smoke test failed”.

## 3. Xác minh đúng phiên bản vừa triển khai

Một smoke test có thể vô tình gửi request đến phiên bản cũ nếu load balancer, DNS, ingress hoặc service discovery chưa cập nhật. Vì vậy, cần biết test đang xác minh đúng artifact dự kiến.

Nên ghi nhận và đối chiếu:

- Release ID hoặc deployment ID.
- Commit SHA.
- Artifact version và digest.
- Môi trường, namespace, region hoặc slot.
- Thời điểm bắt đầu deployment và smoke test.
- Version/build metadata do ứng dụng cung cấp.

Có thể cung cấp endpoint metadata chỉ đọc, ví dụ /version hoặc /build-info, trả về commit, build ID và artifact version. Endpoint này không nên tiết lộ secret, biến môi trường nhạy cảm, cấu hình nội bộ hoặc thông tin có thể giúp kẻ tấn công.

Với rolling hoặc blue-green deployment, cần xác định smoke test đang gọi instance nào. Có thể gọi trực tiếp service nội bộ, route riêng hoặc kiểm tra response header/build metadata. Sau cutover, cần kiểm tra traffic thực sự đi đến phiên bản mới thay vì chỉ kiểm tra một pod chưa nhận request production.

Không nên chỉ dựa vào tên tag có thể thay đổi. Nếu artifact được quản lý bằng digest, hãy liên kết digest đó với deployment record và kết quả smoke test.

## 4. Phân biệt health, readiness và smoke test

Ba loại kiểm tra hỗ trợ nhau:

| Kiểm tra | Mục đích | Ví dụ |
| --- | --- | --- |
| Liveness | Phát hiện tiến trình bị kẹt hoặc cần restart | Process phản hồi health endpoint |
| Readiness | Xác định instance có thể nhận traffic | Dependency bắt buộc và cấu hình đã sẵn sàng |
| Smoke test | Xác minh luồng quan trọng hoạt động từ góc nhìn người dùng/hệ thống gọi | Đăng nhập, đọc dữ liệu, tạo một giao dịch test |

Liveness không nên phụ thuộc mọi dịch vụ bên ngoài. Nếu database tạm thời chậm và liveness thất bại, orchestrator có thể restart hàng loạt instance, làm tình hình tệ hơn.

Readiness có thể kiểm tra dependency thiết yếu, nhưng không nhất thiết thực hiện một giao dịch nghiệp vụ đầy đủ. Smoke test bổ sung bước kiểm tra đó từ bên ngoài ứng dụng hoặc qua API phù hợp.

Một ứng dụng có thể liveness và readiness đều xanh nhưng vẫn lỗi do sai routing, certificate, quyền người dùng, schema response hoặc một luồng nghiệp vụ. Đó là lý do cần smoke test riêng.

## 5. Thiết kế test an toàn cho môi trường sau triển khai

Smoke test production phải tránh làm thay đổi dữ liệu thật ngoài dự kiến. Trước khi chạy, xác định rõ test sẽ đọc, ghi, gửi hoặc kích hoạt điều gì.

### 5.1. Dùng tài khoản và dữ liệu kiểm thử riêng

- Dùng test account hoặc tenant chuyên dụng.
- Đánh dấu dữ liệu do smoke test tạo bằng prefix hoặc metadata riêng.
- Không dùng dữ liệu cá nhân thật nếu không cần thiết.
- Không dùng tài khoản quản trị rộng chỉ để test một luồng đơn giản.
- Tạo dữ liệu với định danh duy nhất theo deployment/run ID.
- Giới hạn quyền và phạm vi dữ liệu của test identity.

Nếu test cần kiểm tra quyền truy cập, dùng các tài khoản có vai trò được định nghĩa sẵn, chẳng hạn viewer và operator. Không dùng credential của người dùng thật.

### 5.2. Kiểm soát side effect

Một số thao tác không thể hoàn tác dễ dàng:

- Gửi email hoặc SMS thật.
- Thanh toán hoặc hoàn tiền.
- Gửi webhook đến đối tác.
- Tạo vận đơn hoặc yêu cầu giao hàng.
- Phát thông báo cho người dùng.
- Kích hoạt workflow hoặc job xử lý dữ liệu lớn.

Ưu tiên sandbox, provider test mode, fake endpoint hoặc dry-run. Nếu phải gọi dịch vụ thật, dùng một quy trình được thiết kế riêng với số tiền nhỏ/định danh test, idempotency và bước hủy/hoàn tất có kiểm soát. Không để smoke test vô tình tạo giao dịch kinh doanh.

### 5.3. Idempotency và khả năng chạy lại

Pipeline có thể retry smoke test khi runner mất kết nối hoặc timeout. Nếu test tạo tài nguyên mới mỗi lần, một lần chạy lại có thể tạo đơn hàng, giao dịch hoặc message trùng lặp.

Dùng idempotency key gắn với một lần chạy hoặc một test case. Khi retry, cùng một thao tác logic phải không tạo thêm side effect. Nếu hệ thống không hỗ trợ idempotency, tạo tài nguyên với ID duy nhất và có bước kiểm tra trước khi tạo.

Không dùng lại một ID cố định giữa nhiều pipeline song song nếu dữ liệu có thể bị ghi đè. Có thể dùng deployment ID và test case ID để tạo namespace riêng.

### 5.4. Dọn dữ liệu

Sau test, xóa hoặc đánh dấu dữ liệu test theo chính sách. Cleanup nên chạy cả khi assertion thất bại. Nếu dữ liệu không thể xóa vì cần audit, hãy đánh dấu test record và đặt thời hạn lưu rõ ràng.

Không để cleanup xóa dữ liệu người dùng thật. Mọi truy vấn xóa phải giới hạn bằng test tenant, test marker hoặc định danh tài nguyên đã tạo trong chính lần chạy đó.

## 6. Kiểm tra API sau triển khai

API smoke test thường nhanh và ổn định hơn thao tác UI. Có thể kiểm tra:

- DNS/TLS và kết nối đến endpoint.
- HTTP status code.
- Response schema và trường bắt buộc.
- Nội dung nghiệp vụ quan trọng.
- Authentication và authorization.
- Khả năng đọc/ghi dữ liệu test.
- Dependency như database, cache hoặc broker.

Ví dụ kiểm tra readiness endpoint:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ -z "$BASE_URL" ]; then
  echo "BASE_URL is required" >&2
  exit 2
fi

status_code=$(curl \
  --silent \
  --show-error \
  --output readiness.json \
  --write-out '%{http_code}' \
  --connect-timeout 3 \
  --max-time 10 \
  "$BASE_URL/ready")

if [ "$status_code" != "200" ]; then
  echo "Readiness check failed: HTTP $status_code" >&2
  cat readiness.json
  exit 1
fi

jq -e '.status == "UP"' readiness.json >/dev/null
echo "Readiness check passed"
~~~

Đoạn script giả định runner có curl và jq, endpoint trả JSON với status UP, và BASE_URL được cấp từ cấu hình môi trường. Trong hệ thống thật, điều chỉnh schema theo API và tránh in response nếu nội dung có thể chứa dữ liệu nhạy cảm.

### 6.1. Smoke test cho một luồng API

Ví dụ dưới đây minh họa kiểm tra catalog và một đơn hàng test. Các endpoint, payload và trường response phải được thay bằng hợp đồng thực tế của ứng dụng:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ -z "$BASE_URL" ] || [ -z "$SMOKE_TEST_TOKEN" ] || [ -z "$SMOKE_RUN_ID" ]; then
  echo "Required smoke-test configuration is missing" >&2
  exit 2
fi

curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  -H "Authorization: Bearer $SMOKE_TEST_TOKEN" \
  "$BASE_URL/api/catalog/health" \
  -o catalog.json

jq -e '.available == true' catalog.json >/dev/null

idempotency_key="smoke-$SMOKE_RUN_ID-order"
http_code=$(curl \
  --silent \
  --show-error \
  --output order.json \
  --write-out '%{http_code}' \
  --connect-timeout 3 \
  --max-time 15 \
  -X POST \
  -H "Authorization: Bearer $SMOKE_TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $idempotency_key" \
  -d '{"testMode":true,"items":[{"sku":"SMOKE-SKU","quantity":1}]}' \
  "$BASE_URL/api/orders")

if [ "$http_code" != "201" ] && [ "$http_code" != "200" ]; then
  echo "Order smoke test failed: HTTP $http_code" >&2
  exit 1
fi

jq -e '.testMode == true and .status != null and .id != null' order.json >/dev/null
echo "Critical API flow passed"
~~~

Ví dụ dùng test token có quyền hẹp, test mode và idempotency key. Hệ thống thật cần có cơ chế bảo đảm testMode không thể bị client lợi dụng để bỏ qua nghiệp vụ hoặc quyền bảo mật. Không đưa token vào log; nền tảng CI phải mask secret và chỉ cấp token cho job smoke test.

Trong production, nếu không có test mode an toàn, hãy thay bước tạo đơn bằng một luồng đọc hoặc một thao tác được thiết kế riêng để không tạo side effect. Nếu có tạo tài nguyên, cần cleanup có giới hạn và xác minh rằng tài nguyên thuộc đúng lần chạy.

## 7. Kiểm tra UI và trải nghiệm người dùng

UI smoke test xác minh các thành phần quan trọng có thể tải và người dùng có thể hoàn tất một hành động cơ bản. Chỉ nên chọn vài luồng ổn định, tránh kiểm tra mọi chi tiết giao diện.

Ví dụ với Playwright:

~~~javascript
import { test, expect } from '@playwright/test';

test('user can view an existing smoke order', async ({ page }) => {
  await page.goto(process.env.BASE_URL + '/orders/smoke-order');

  await expect(
    page.getByRole('heading', { name: 'Order details' })
  ).toBeVisible();

  await expect(
    page.getByTestId('order-status')
  ).toHaveText('CONFIRMED');
});
~~~

Ví dụ này đọc một đơn hàng test đã được chuẩn bị. Với luồng đăng nhập, dùng tài khoản kiểm thử chuyên dụng và không lưu mật khẩu trong mã nguồn. Nếu UI smoke test tạo dữ liệu, phải dùng test fixture riêng và cleanup sau khi chạy.

UI test thường nhạy với thay đổi selector, animation và thời gian tải. Ưu tiên role, label hoặc test ID ổn định; tránh sleep cố định dài nếu có thể chờ điều kiện cụ thể. Khi UI test thất bại, lưu screenshot, trace và console/network error đã lọc secret để hỗ trợ điều tra.

Không để một lỗi quảng cáo, analytics hoặc widget bên thứ ba không quan trọng làm chặn release nếu chúng không thuộc luồng thiết yếu. Xác định rõ dependency nào là bắt buộc và dependency nào có thể degrade gracefully.

## 8. Kiểm tra dependency đồng bộ và bất đồng bộ

Một luồng quan trọng có thể đi qua nhiều hệ thống:

- API gateway hoặc ingress.
- Authentication/identity provider.
- Application service.
- Database.
- Cache.
- Message broker.
- Worker xử lý nền.
- Dịch vụ bên thứ ba.

Smoke test nên xác minh các dependency thực sự cần cho luồng, nhưng không nên biến một bài test thành phép kiểm tra mọi hệ thống trong kiến trúc.

Với xử lý bất đồng bộ, HTTP 202 hoặc thông báo “accepted” chỉ cho biết request đã được tiếp nhận. Cần chờ có giới hạn để xác minh kết quả cuối cùng xuất hiện:

1. Gửi message hoặc yêu cầu test với correlation ID.
2. Nhận response xác nhận đã tiếp nhận.
3. Poll trạng thái hoặc truy vấn kết quả bằng correlation ID.
4. Dừng khi kết quả đạt, trạng thái thất bại hoặc timeout.
5. Ghi queue lag, retry và lỗi consumer nếu không hoàn tất.

Không poll vô hạn. Timeout phải dựa trên SLA của luồng và có log cho biết thời gian chờ. Nếu worker xử lý theo lịch, có thể cần một smoke test riêng hoặc cơ chế trigger an toàn.

Khi dependency không thiết yếu bị lỗi, ứng dụng có thể được thiết kế để degrade gracefully. Smoke test cần kiểm tra hành vi dự kiến đó thay vì mặc định mọi dịch vụ phụ đều phải hoạt động tuyệt đối.

## 9. Đặt timeout, retry và assertion

Một smoke test đáng tin cậy cần giới hạn thời gian và kiểm tra kết quả rõ ràng:

- **Connect timeout:** thời gian tối đa để thiết lập kết nối.
- **Request timeout:** thời gian tối đa cho một request.
- **Flow timeout:** tổng thời gian cho cả luồng.
- **Retry:** số lần thử lại khi lỗi được xem là tạm thời.
- **Backoff:** khoảng nghỉ giữa các lần thử, tránh tạo tải đột biến.
- **Assertion:** điều kiện cụ thể để xác định kết quả đúng.

Không retry tất cả lỗi. HTTP 401 có thể là credential sai; HTTP 403 có thể là permission sai; HTTP 404 có thể là route chưa tồn tại; HTTP 500 có thể là lỗi ứng dụng. Retry vô hạn làm chậm phát hiện và có thể khuếch đại sự cố.

Có thể retry lỗi kết nối tạm thời hoặc trạng thái chưa sẵn sàng trong một cửa sổ ngắn. Khi hết thời gian, test phải thất bại và ghi đủ bằng chứng.

Assertion nên kiểm tra:

- HTTP status hoặc protocol result mong đợi.
- Trường response bắt buộc và kiểu dữ liệu.
- Giá trị nghiệp vụ, chẳng hạn trạng thái đơn hoặc tổng tiền.
- Dữ liệu có thể đọc lại sau khi ghi.
- Phiên bản ứng dụng đúng với release dự kiến.
- Không có lỗi nghiêm trọng hoặc trạng thái bất thường trong luồng.

Không chỉ kiểm tra response có nội dung hoặc HTTP 200. Một API có thể trả 200 với payload chứa lỗi nghiệp vụ.

## 10. Tích hợp smoke test vào CI/CD pipeline

Smoke test thường chạy sau deployment và trước khi release được đánh dấu hoàn tất hoặc traffic được mở rộng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Build và test"] --> B["Quality gates"]
    B --> C["Deploy artifact đã xác định"]
    C --> D["Chờ rollout và readiness"]
    D --> E["Chạy smoke tests"]
    E --> F{"Tất cả critical flows đạt?"}
    F -- "Có" --> G["Theo dõi metrics sau deploy"]
    G --> H{"Guardrails đạt?"}
    H -- "Có" --> I["Đánh dấu release ổn định / mở rộng traffic"]
    H -- "Không" --> J["Dừng rollout hoặc rollback"]
    F -- "Không" --> J
    J --> K["Thu log, báo lỗi và ghi deployment result"]
~~~

Ví dụ pipeline trung lập với nền tảng:

~~~yaml
stages:
  - build
  - test
  - deploy
  - smoke
  - observe

deploy-production:
  stage: deploy
  script:
    - ./scripts/deploy.sh "$ARTIFACT_DIGEST" production

smoke-production:
  stage: smoke
  needs:
    - deploy-production
  script:
    - ./scripts/wait-ready.sh
    - ./scripts/smoke-critical-flows.sh

observe-production:
  stage: observe
  needs:
    - smoke-production
  script:
    - ./scripts/check-release-guardrails.sh
~~~

Đây là cấu hình minh họa; cú pháp needs, stages và điều kiện chạy phụ thuộc nền tảng CI. Pipeline thật cần bảo đảm bước thu thập log và báo cáo vẫn chạy khi smoke test thất bại, đồng thời rollback hoặc dừng rollout được kích hoạt theo policy.

### 10.1. Smoke test sau blue-green hoặc canary

Với blue-green:

- Chạy smoke test trực tiếp vào green trước cutover.
- Xác minh artifact digest và build metadata.
- Sau cutover, chạy một số kiểm tra qua route production để xác minh traffic đã đến green.
- Giữ blue trong cửa sổ rollback.

Với canary:

- Chạy smoke test vào canary trước khi mở traffic.
- Sau khi mở tỷ lệ nhỏ, xác minh cả synthetic flow và metrics trên traffic thật.
- Chỉ tăng tỷ lệ khi guardrails đạt.
- Nếu smoke test hoặc metrics thất bại, dừng tăng traffic và thực hiện hành động đã định.

Không nhầm smoke test trên endpoint nội bộ của canary với việc xác minh người dùng thực sự đang được route đến canary. Hai kiểm tra này có mục tiêu khác nhau.

## 11. Đánh giá kết quả và quyết định release

Kết quả smoke test nên có trạng thái rõ:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| PASS | Tất cả critical assertions đạt | Tiếp tục bước quan sát hoặc mở rộng release |
| FAIL | Một hoặc nhiều luồng quan trọng không đạt | Chặn release, dừng rollout hoặc rollback theo policy |
| INCONCLUSIVE | Không đủ dữ liệu, test environment lỗi hoặc timeout không xác định được nguyên nhân | Giữ rollout, điều tra và chạy lại có kiểm soát |
| SKIPPED | Test không chạy theo policy đã định | Hiển thị rõ lý do; không coi là PASS |

Không biến INCONCLUSIVE thành PASS chỉ để pipeline xanh. Nếu endpoint test không truy cập được do runner hoặc DNS, cần phân biệt lỗi môi trường test với lỗi ứng dụng. Trong lúc điều tra, giữ trạng thái release ở mức chưa được xác minh.

Với luồng có mức độ quan trọng khác nhau, có thể phân loại critical và non-critical. Một widget phụ bị lỗi có thể tạo cảnh báo; đăng nhập hoặc thanh toán thất bại có thể phải chặn release. Tiêu chí phải được thống nhất trước deployment.

## 12. Quan sát sau smoke test

Smoke test thường tạo một số request rất nhỏ. Nó có thể không phát hiện lỗi chỉ xuất hiện dưới tải hoặc sau thời gian dài. Vì vậy, sau khi smoke test đạt, vẫn cần quan sát metrics và log trong cửa sổ phù hợp.

Theo dõi:

- Error rate và latency theo version.
- Tỷ lệ request thành công của critical endpoints.
- Database connection, query latency và lock.
- Cache hit/miss và lỗi kết nối.
- Queue lag, retry, dead-letter và thời gian xử lý.
- Crash, restart, CPU, memory và saturation.
- Business metrics như giao dịch thành công hoặc tỷ lệ hoàn tất.

Gắn kết quả với release ID, artifact digest, environment và thời điểm. Dùng correlation ID để nối log giữa gateway, service và worker.

Không ghi access token, password, dữ liệu cá nhân hoặc payload nhạy cảm vào smoke report. Nếu cần lưu request/response để điều tra, hãy lọc và mask trường nhạy cảm.

## 13. Xử lý khi smoke test thất bại

Khi test thất bại, tránh chạy đi chạy lại mà không thu thập bằng chứng. Một quy trình điều tra ngắn:

1. Xác định release ID, commit và artifact digest vừa deploy.
2. Xác nhận test đang gọi đúng môi trường và phiên bản.
3. Ghi endpoint, thời gian, status code, assertion và correlation ID.
4. Kiểm tra log ứng dụng, ingress, database, broker và dependency liên quan.
5. Phân biệt lỗi ứng dụng, cấu hình, dữ liệu, quyền, routing và runner/test harness.
6. Xác định phạm vi ảnh hưởng và liệu người dùng thật đã nhận phiên bản mới chưa.
7. Dừng rollout hoặc rollback nếu tiêu chí đã định bị vi phạm.
8. Sau khi khắc phục, chạy lại smoke test và lưu kết quả mới.

Không xóa dữ liệu test hoặc container log trước khi thu thập bằng chứng. Không retry một thao tác tạo side effect nếu chưa biết request trước đã được xử lý hay chưa; hãy kiểm tra idempotency key hoặc trạng thái giao dịch.

### 13.1. Khi nào cần rollback?

Rollback hoặc dừng rollout khi:

- Critical flow không thể hoàn tất.
- Dữ liệu ghi ra sai hoặc không thể đọc lại.
- Authentication/authorization có hành vi sai.
- Dependency thiết yếu không truy cập được.
- Có lỗi nghiêm trọng về bảo mật hoặc rò rỉ dữ liệu.
- Metrics sau deploy vượt ngưỡng SLO/guardrail.

Với lỗi nhỏ có workaround và không ảnh hưởng luồng quan trọng, có thể giữ release ở trạng thái cảnh báo trong khi điều tra, nếu policy cho phép. Quyết định cần dựa trên tác động thực tế và tiêu chí đã thống nhất, không dựa trên mong muốn giữ pipeline xanh.

Rollback binary không tự đảo ngược database migration, message đã phát hoặc giao dịch đã hoàn tất. Cần phối hợp với chiến lược tương thích dữ liệu và phục hồi nghiệp vụ.

## 14. Ví dụ smoke test UI với Playwright trong pipeline

Một test UI tối giản có thể chạy sau deploy bằng base URL được cấp từ môi trường:

~~~javascript
import { test, expect } from '@playwright/test';

test('critical customer journey is available', async ({ page }) => {
  const baseUrl = process.env.BASE_URL;
  if (!baseUrl) {
    throw new Error('BASE_URL is required');
  }

  await page.goto(baseUrl + '/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
});
~~~

Ví dụ chỉ kiểm tra trang đăng nhập tải được và các trường thiết yếu xuất hiện. Một smoke test cho luồng đã xác thực cần lấy credential từ secret store, đăng nhập bằng test account, kiểm tra hành động quan trọng và dọn dữ liệu tạo ra. Không hardcode credential trong test file.

Giữ số test UI nhỏ vì browser test có thể chậm và nhạy với thay đổi giao diện. Có thể dùng API smoke test cho các dependency và business assertions, sau đó giữ một UI test ngắn để xác minh trải nghiệm người dùng chính.

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra deployment job thành công | Không biết ứng dụng có phục vụ được người dùng | Chạy smoke test sau readiness |
| Chỉ gọi endpoint liveness | Dependency hoặc luồng nghiệp vụ vẫn có thể lỗi | Kiểm tra critical journey |
| Test quá nhiều trường hợp | Smoke suite chậm và khó ổn định | Giữ phạm vi nhỏ, để regression suite chạy riêng |
| Chỉ kiểm tra HTTP 200 | Payload có thể chứa lỗi nghiệp vụ | Assert schema và giá trị nghiệp vụ |
| Dùng dữ liệu production thật | Gây thay đổi dữ liệu hoặc side effect | Dùng test identity và fixture riêng |
| Không có idempotency | Retry tạo giao dịch hoặc tài nguyên trùng | Dùng idempotency key và xác minh trạng thái |
| Không có timeout | Pipeline treo khi dependency lỗi | Đặt connect/request/flow timeout |
| Retry vô hạn | Kéo dài sự cố và tạo tải thêm | Retry hữu hạn, backoff và phân loại lỗi |
| Test không xác minh version | Có thể kiểm tra nhầm instance cũ | Đối chiếu build metadata/digest |
| Cleanup xóa dữ liệu không giới hạn | Có thể xóa dữ liệu người dùng | Chỉ cleanup resource do test tạo |
| Coi test bị bỏ qua là pass | Release thiếu bằng chứng | Dùng trạng thái SKIPPED riêng |
| Không thu log khi thất bại | Khó điều tra và tái hiện | Lưu report, trace và correlation ID đã lọc |

## 16. Checklist kiểm tra khói sau triển khai

**Trước khi chạy**

- [ ] Đã chọn các luồng quan trọng theo tác động người dùng/nghiệp vụ.
- [ ] Đã xác định môi trường, release ID, commit và artifact digest.
- [ ] Deployment hoàn tất và instance đạt readiness.
- [ ] Test account, token ngắn hạn và dữ liệu kiểm thử đã sẵn sàng.
- [ ] Side effect được tắt, giả lập hoặc giới hạn an toàn.
- [ ] Có idempotency và cleanup cho thao tác ghi.

**Trong khi chạy**

- [ ] Có timeout cho kết nối, request và toàn bộ flow.
- [ ] Assertion kiểm tra kết quả nghiệp vụ, không chỉ HTTP status.
- [ ] Dependency đồng bộ/bất đồng bộ được xác minh trong giới hạn thời gian.
- [ ] Log và correlation ID được lưu mà không lộ secret/PII.
- [ ] Kết quả PASS, FAIL, INCONCLUSIVE hoặc SKIPPED được phân biệt.

**Sau khi chạy**

- [ ] Dữ liệu test được dọn hoặc đánh dấu theo chính sách.
- [ ] Kết quả được liên kết với release và artifact digest.
- [ ] Metrics sau deploy được theo dõi theo version.
- [ ] Có điều kiện dừng rollout và rollback rõ ràng.
- [ ] Khi thất bại, bằng chứng được giữ trước khi cleanup.
- [ ] Release chỉ được đánh dấu ổn định khi đủ bằng chứng theo policy.

## Kết luận

Smoke test sau triển khai xác minh những luồng thiết yếu có hoạt động trên phiên bản vừa được đưa lên môi trường đích hay không. Một bộ kiểm tra hữu ích cần nhỏ, nhanh, có assertion nghiệp vụ, xác minh đúng artifact/version, dùng dữ liệu an toàn, kiểm soát side effect và có timeout rõ ràng.

Kết quả smoke test nên được liên kết với release ID và artifact digest, sau đó kết hợp với metrics/log trong cửa sổ quan sát. Nếu critical flow thất bại, pipeline cần chặn mở rộng, giữ bằng chứng và kích hoạt quy trình điều tra hoặc rollback theo policy. Nhờ vậy, CI/CD có thể xác minh kết quả triển khai bằng hành vi thực tế thay vì chỉ dựa vào trạng thái của công cụ deploy.
