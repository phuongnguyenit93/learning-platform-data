# Kiểm tra lại artifact hoặc cấu hình nếu có thay đổi sau phê duyệt

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao một lần phê duyệt chỉ có giá trị đối với đúng artifact, cấu hình, môi trường và chính sách đã được xem xét.
- Nhận diện các thay đổi làm cho bằng chứng hoặc quyết định phê duyệt trở nên lỗi thời.
- Thiết kế cách ghi nhận dấu vân tay của artifact và cấu hình trong hồ sơ phê duyệt.
- Phân biệt thay đổi có ảnh hưởng đến hành vi triển khai với thay đổi chỉ mang tính mô tả.
- Tổ chức kiểm tra lại và yêu cầu phê duyệt mới khi đối tượng phát hành thay đổi.
- Ngăn thay đổi xảy ra giữa lần kiểm tra cuối và thời điểm triển khai.
- Lưu dấu vết để giải thích chính xác phiên bản nào đã được phê duyệt và phiên bản nào thực sự được triển khai.

## 1. Vì sao phải kiểm tra lại sau phê duyệt?

Trong quy trình CI/CD, một lần phê duyệt thường được đưa ra sau khi người duyệt xem xét artifact, kết quả kiểm thử, cấu hình và phạm vi triển khai. Nhưng từ thời điểm phê duyệt đến lúc triển khai, những thành phần này vẫn có thể thay đổi.

Ví dụ:

- Artifact được build lại từ cùng một nhánh và tạo ra digest khác.
- Tag như latest hoặc release được trỏ sang một image khác.
- Helm values hoặc manifest triển khai được chỉnh sửa.
- Feature flag được bật hoặc tắt.
- Secret được xoay vòng hoặc tham chiếu sang phiên bản khác.
- Một dependency hoặc image nền bị thay đổi.
- Môi trường đích được cập nhật bởi một pipeline khác.
- Chính sách phát hành được sửa sau khi người duyệt đã xem xét.
- Kết quả kiểm thử hoặc báo cáo bảo mật không còn gắn với artifact đang chuẩn bị triển khai.

Nếu pipeline chỉ kiểm tra trạng thái approval là approved mà không xác minh đối tượng hiện tại, hệ thống có thể triển khai một phiên bản khác với phiên bản người duyệt đã xem xét.

Đây là một dạng lỗi về tính toàn vẹn của quy trình: quyết định được đưa ra cho một trạng thái, nhưng hành động lại áp dụng lên trạng thái khác.

Nguyên tắc cốt lõi:

> Phê duyệt phải gắn với đúng đối tượng và phạm vi đã được xem xét. Nếu một thay đổi có ý nghĩa làm đối tượng đó khác đi, cần kiểm tra lại và quyết định xem có phải phê duyệt lại hay không.

Vì vậy, approval không nên chỉ là một cờ trạng thái độc lập. Nó cần có ngữ cảnh, bằng chứng, thời điểm, người duyệt và định danh của nội dung được phê duyệt.

## 2. Phê duyệt điều gì?

Một yêu cầu triển khai thường gồm nhiều thành phần. Chỉ ghi nhận phiên bản ứng dụng là chưa đủ nếu kết quả thực tế còn phụ thuộc vào cấu hình và môi trường.

Một hồ sơ phê duyệt nên xác định tối thiểu:

| Thành phần | Định danh nên ghi nhận | Vì sao cần |
|---|---|---|
| Artifact | Digest hoặc ID bất biến | Xác định chính xác gói được triển khai |
| Source | Commit SHA và repository | Truy vết mã nguồn tạo ra artifact |
| Build | Pipeline run, toolchain và provenance | Biết artifact được tạo như thế nào |
| Deployment manifest | Revision hoặc digest của manifest | Xác định tài nguyên và tham số triển khai |
| Configuration | Revision hoặc fingerprint cấu hình đã resolve | Xác định hành vi ứng dụng dự kiến |
| Environment | Environment ID và phiên bản trạng thái liên quan | Xác định nơi nhận thay đổi |
| Policy | Phiên bản policy hoặc rule set | Biết tiêu chí phê duyệt tại thời điểm đó |
| Evidence | Test, scan, signature và verification result | Chứng minh các điều kiện đã đạt |
| Approval | Actor, thời điểm, phạm vi và kết quả | Xác định ai đã cho phép hành động nào |

Không phải mọi hệ thống đều có thể đóng gói tất cả thông tin vào một digest duy nhất. Tuy nhiên, pipeline cần có một bản ghi hoặc manifest tổng hợp đủ để liên kết những định danh này.

Có thể gọi tập hợp đó là **deployment request snapshot**: ảnh chụp có phiên bản của yêu cầu triển khai tại thời điểm người duyệt xem xét.

Ví dụ, người duyệt không chỉ phê duyệt ứng dụng phiên bản 2.8.1. Họ phê duyệt image có digest cụ thể, cấu hình staging đã được kiểm tra, manifest triển khai xác định, môi trường production mục tiêu và tập bằng chứng tương ứng.

## 3. Artifact phải được định danh bất biến

Artifact là đối tượng quan trọng nhất của một lần phát hành. Nếu người duyệt xem image A nhưng pipeline triển khai image B, approval cũ không thể được coi là hợp lệ cho B.

Không nên dùng tag có thể thay đổi như latest, stable hoặc tên nhánh làm định danh cuối cùng cho artifact production. Tag có thể hữu ích để tìm phiên bản, nhưng pipeline nên resolve tag thành digest rồi sử dụng digest đó xuyên suốt các bước kiểm tra, phê duyệt và triển khai.

Ví dụ:

~~~text
Tag được yêu cầu: service-api:release
Digest đã resolve: sha256:abc123...
Approval gắn với: sha256:abc123...
Deploy phải dùng: sha256:abc123...
~~~

Nếu tag được cập nhật sang digest khác sau khi phê duyệt, pipeline phải nhận diện sự khác biệt và dừng luồng hiện tại. Người vận hành cần xem xét lại artifact mới.

Một artifact bất biến cũng cần có bằng chứng nguồn gốc:

- Commit tạo ra artifact.
- Pipeline run đã build artifact.
- Các kiểm tra đã chạy trên artifact hoặc đúng commit tương ứng.
- Digest được lưu trong registry.
- Chữ ký hoặc provenance nếu chính sách yêu cầu.
- Trạng thái thu hồi hoặc cảnh báo bảo mật nếu có.

Nếu artifact được build lại từ cùng commit, không nên giả định digest sẽ giống nhau. Build có thể phụ thuộc thời gian, dependency, toolchain hoặc dữ liệu môi trường. Chính digest mới là định danh nội dung được phát hành.

## 4. Cấu hình cũng là một phần của đối tượng phê duyệt

Nhiều quy trình chỉ gắn approval với image hoặc phiên bản ứng dụng. Tuy nhiên, cùng một artifact có thể tạo ra hành vi khác nhau khi cấu hình thay đổi.

Ví dụ:

- Giá trị giới hạn timeout thay đổi từ 2 giây thành 30 giây.
- URL của payment provider chuyển từ sandbox sang endpoint production.
- Feature flag mở một chức năng cho toàn bộ người dùng.
- Số replica tăng đột ngột và làm thay đổi tải hoặc chi phí.
- Network policy cho phép thêm một nguồn truy cập.
- Helm values đổi service account hoặc quyền truy cập.
- Cấu hình migration bật chế độ xóa dữ liệu cũ.

Vì vậy, cần phân biệt các loại cấu hình:

| Loại cấu hình | Ví dụ | Cách theo dõi |
|---|---|---|
| Cấu hình đóng gói cùng artifact | File mặc định trong image | Artifact digest |
| Deployment configuration | Helm values, Kubernetes manifest, Terraform variables | Revision hoặc fingerprint của cấu hình đã resolve |
| Runtime configuration | Config service, feature flag, tham số được đọc lúc chạy | Version hoặc snapshot tại thời điểm phê duyệt |
| Secret reference | Tên secret, version ID hoặc secret revision | Tham chiếu và version metadata, không lưu giá trị bí mật |
| Environment configuration | Network, quota, policy, dependency endpoint | Environment revision hoặc các trạng thái liên quan |

Không nên ghi giá trị secret vào hồ sơ phê duyệt hoặc tạo báo cáo chứa plaintext. Có thể ghi tên tham chiếu, version ID hoặc metadata an toàn để biết phiên bản credential nào được dùng.

Với cấu hình động từ một config service, việc ghi lại tên file trong repository là chưa đủ. Pipeline cần xác định revision thực tế đã được resolve hoặc snapshot cấu hình được áp dụng cho lần triển khai.

## 5. Phân biệt thay đổi có ý nghĩa và thay đổi không ảnh hưởng

Không phải mọi chỉnh sửa đều làm thay đổi rủi ro phát hành. Một thay đổi comment trong file cấu hình có thể không làm thay đổi hành vi. Ngược lại, thay đổi một giá trị timeout hoặc quyền truy cập có thể ảnh hưởng đáng kể.

Cần xây dựng quy tắc phân loại thay đổi:

| Loại thay đổi | Ví dụ | Hành động gợi ý |
|---|---|---|
| Nội dung artifact | Digest image hoặc package thay đổi | Bắt buộc kiểm tra lại và phê duyệt mới |
| Deployment manifest | Replica, port, service account, volume hoặc network policy đổi | Revalidate; phê duyệt lại nếu ảnh hưởng hành vi hoặc quyền |
| Runtime config | Feature flag, endpoint, timeout, giới hạn nghiệp vụ đổi | Revalidate và đánh giá mức độ cần phê duyệt lại |
| Secret reference/version | Credential hoặc key version đổi | Kiểm tra chính sách, có thể yêu cầu phê duyệt lại |
| Environment state | Cluster, schema, quota hoặc dependency thay đổi | Kiểm tra lại điều kiện môi trường và tính tương thích |
| Policy | Rule bảo mật hoặc tiêu chí phát hành đổi | Đánh giá lại theo policy mới |
| Metadata mô tả | Comment, nhãn hiển thị hoặc mô tả không tác động | Có thể giữ approval nếu xác minh được không đổi nội dung thực thi |

Một chính sách bảo thủ có thể yêu cầu phê duyệt lại khi bất kỳ revision nào trong snapshot thay đổi. Cách này dễ hiểu và giảm nguy cơ bỏ sót.

Khi hệ thống trưởng thành hơn, có thể dùng semantic diff để phân biệt thay đổi có ảnh hưởng với thay đổi không ảnh hưởng. Tuy nhiên, quy tắc miễn trừ phải rõ ràng và có thể kiểm toán. Không nên tự suy đoán rằng một thay đổi là vô hại chỉ vì số dòng thay đổi ít.

Nếu không thể xác định chắc chắn thay đổi có ảnh hưởng hay không, nên xem approval cũ là stale và chạy lại các kiểm tra cần thiết.

## 6. Khi nào approval trở nên stale?

Approval được coi là stale khi những điều kiện làm cơ sở cho quyết định đã thay đổi hoặc không còn đủ tin cậy.

Một số điều kiện phổ biến:

1. Artifact digest khác với digest trong hồ sơ phê duyệt.
2. Source commit hoặc provenance không còn khớp với artifact đã duyệt.
3. Manifest triển khai thay đổi sau khi phê duyệt.
4. Runtime configuration thay đổi ở trường có ảnh hưởng đến hành vi.
5. Secret reference hoặc version thay đổi theo chính sách cần kiểm soát.
6. Environment revision thay đổi và làm mất điều kiện tương thích.
7. Kết quả test hoặc scan đã hết hạn hoặc bị thu hồi.
8. Policy version mới có yêu cầu khác.
9. Approval hết thời hạn hiệu lực.
10. Người duyệt hoặc vai trò phê duyệt không còn hợp lệ theo chính sách hiện tại.

Không nên chỉ dùng thời gian để xác định approval stale. Một approval mới 5 phút vẫn có thể stale nếu artifact vừa bị thay đổi. Ngược lại, một approval lâu hơn có thể vẫn còn hiệu lực nếu toàn bộ đối tượng, bằng chứng và chính sách đều được xác nhận còn hợp lệ và chưa hết hạn.

Có thể dùng đồng thời hai nhóm điều kiện:

- **Content freshness:** artifact, cấu hình, môi trường và bằng chứng vẫn khớp.
- **Time freshness:** approval và bằng chứng chưa vượt quá thời hạn được chính sách cho phép.

Cả hai đều cần đạt trước khi triển khai.

## 7. Kiểm tra lại ở những thời điểm nào?

Không nên chỉ kiểm tra một lần ngay sau khi người dùng gửi yêu cầu. Một luồng phát hành có thể kéo dài và trạng thái phụ thuộc có thể thay đổi trong lúc chờ.

Các điểm kiểm tra hữu ích:

### 7.1. Trước khi tạo yêu cầu phê duyệt

Pipeline resolve artifact và cấu hình, tính fingerprint, kiểm tra test/scan, rồi tạo deployment request snapshot.

Mục tiêu là cung cấp cho người duyệt một đối tượng rõ ràng và bằng chứng phù hợp.

### 7.2. Khi người duyệt mở yêu cầu

Giao diện hoặc bước phê duyệt cần hiển thị artifact, môi trường, thay đổi cấu hình, bằng chứng và phạm vi tác động. Nếu snapshot đã thay đổi trong lúc yêu cầu chờ, cần đánh dấu stale và không cho phê duyệt dựa trên dữ liệu cũ.

### 7.3. Ngay sau khi phê duyệt

Ghi lại approval record gắn với snapshot cụ thể. Nếu có thay đổi đồng thời trong lúc người duyệt thao tác, cần xác nhận approval được ghi cho revision nào.

### 7.4. Ngay trước khi deploy

Đây là lần kiểm tra quan trọng nhất. Pipeline cần resolve lại hoặc đọc trạng thái hiện tại và so sánh với snapshot đã được duyệt.

- Nếu khớp, có thể tiếp tục theo policy.
- Nếu khác, dừng triển khai và đánh dấu approval stale.
- Nếu không thể kiểm tra, dừng ở trạng thái blocked thay vì mặc định cho qua.

### 7.5. Trong và sau rollout

Một số cấu hình hoặc trạng thái môi trường có thể thay đổi khi rollout đang diễn ra. Cần xác minh phiên bản thực tế, cấu hình đã áp dụng và tín hiệu sức khỏe sau triển khai.

Nếu phát hiện đối tượng thực tế khác đối tượng được phê duyệt, dừng rollout nếu có thể và kích hoạt quy trình xử lý sự cố hoặc khôi phục phù hợp.

## 8. Tránh lỗi TOCTOU giữa kiểm tra và triển khai

TOCTOU (time-of-check to time-of-use) là tình huống trạng thái thay đổi sau khi kiểm tra nhưng trước khi sử dụng.

Ví dụ:

1. Pipeline xác minh digest và cấu hình.
2. Approval được ghi nhận.
3. Một pipeline khác cập nhật manifest hoặc thay đổi môi trường.
4. Pipeline đầu tiên tiếp tục deploy dựa trên kết quả kiểm tra cũ.

Dù mỗi bước riêng lẻ đều thành công, toàn bộ luồng vẫn có thể triển khai một trạng thái chưa được phê duyệt.

Có thể giảm rủi ro bằng các cơ chế sau:

**Deployment lock:** khóa phạm vi tài nguyên trong khoảng thời gian từ kiểm tra cuối đến khi hoàn tất thao tác nhạy cảm. Khóa cần có owner, timeout và cơ chế giải phóng an toàn.

**Compare-and-swap hoặc conditional update:** chỉ cho phép deploy nếu revision hiện tại vẫn bằng revision đã được kiểm tra. Nếu trạng thái đã đổi, thao tác bị từ chối.

**Immutable reference:** sử dụng digest và revision bất biến thay cho tag hoặc alias có thể thay đổi.

**Revalidation sát thời điểm sử dụng:** thực hiện kiểm tra ngay trước thao tác deploy, sau khi đã có quyền và lock cần thiết.

**Single deployment controller:** điều phối các thay đổi lên cùng môi trường qua một cơ chế duy nhất để tránh nhiều pipeline cập nhật cạnh tranh.

Lock không thay thế việc xác minh. Một lock có thể ngăn pipeline khác thay đổi tài nguyên trong lúc triển khai, nhưng vẫn cần kiểm tra trạng thái trước khi lấy lock và xác nhận revision sau khi lấy lock.

## 9. Quy trình xử lý khi phát hiện thay đổi sau phê duyệt

Khi pipeline phát hiện snapshot hiện tại khác snapshot đã được phê duyệt, cần có hành vi xác định.

Một luồng xử lý tham khảo:

1. Dừng trước bước có tác động.
2. Ghi nhận trường nào thay đổi, revision cũ và revision mới.
3. Xác định loại thay đổi và chính sách áp dụng.
4. Chạy lại những kiểm tra bị ảnh hưởng.
5. Tạo snapshot mới nếu thay đổi được chấp nhận.
6. Yêu cầu phê duyệt mới nếu chính sách yêu cầu.
7. Chỉ tiếp tục khi approval gắn với snapshot mới còn hiệu lực.

~~~mermaid
flowchart TD
    A["Deployment request đã được phê duyệt"] --> B["Resolve trạng thái hiện tại"]
    B --> C["So sánh với approval snapshot"]
    C --> D{"Có thay đổi?"}
    D -- "Không" --> E["Kiểm tra freshness và policy"]
    E --> F{"Còn hợp lệ?"}
    F -- "Có" --> G["Lấy lock và kiểm tra lại"]
    G --> H["Deploy đúng artifact/config đã duyệt"]
    F -- "Không" --> X["Block và điều tra"]
    D -- "Có" --> I["Phân loại thay đổi"]
    I --> J["Chạy lại kiểm tra bị ảnh hưởng"]
    J --> K{"Cần phê duyệt lại?"}
    K -- "Có" --> L["Tạo snapshot mới và yêu cầu approval mới"]
    K -- "Không" --> M["Ghi lý do và bằng chứng miễn phê duyệt"]
    L --> N["Chờ quyết định mới"]
    M --> N
    N --> B
    H --> O["Verify và ghi release evidence"]
~~~

Không nên tự động chuyển approval cũ sang snapshot mới chỉ vì pipeline có thể chạy lại test. Kết quả kiểm thử mới cung cấp bằng chứng kỹ thuật; nó không thay thế quyết định của người có thẩm quyền khi phạm vi hoặc rủi ro đã thay đổi.

## 10. Thiết kế approval snapshot và fingerprint

Một snapshot nên chứa các trường cần thiết để so sánh trạng thái được duyệt với trạng thái sắp triển khai.

Ví dụ cấu trúc logic:

~~~yaml
deployment_request:
  request_id: release-2026-042
  target_environment: production

  artifact:
    repository: registry.example.test/team/service-api
    digest: sha256:abc123
    source_commit: 7f3a91c
    build_run: ci-1842

  deployment:
    manifest_revision: 91bd22a
    values_fingerprint: sha256:def456
    runtime_config_revision: config-218
    secret_references:
      - name: payment-api-key
        version: 12

  evidence:
    test_report: test-run-1842
    security_report: scan-1842
    provenance: provenance-1842

  policy:
    policy_revision: release-policy-18

  approval:
    status: approved
    actor: approver-id-from-platform
    approved_at: timestamp
    expires_at: timestamp
    snapshot_id: snapshot-73
~~~

Đây là mô hình minh họa, không phải schema bắt buộc của một nền tảng cụ thể. Các ID trong ví dụ chỉ thể hiện loại dữ liệu cần liên kết.

Fingerprint cấu hình cần được tính từ nội dung đã chuẩn hóa hoặc trạng thái đã resolve. Nếu chỉ hash file nguồn nhưng hệ thống còn hợp nhất nhiều file, biến môi trường và giá trị từ config service, fingerprint đó có thể không đại diện cho cấu hình thực tế.

Một số nguyên tắc:

- Dùng định dạng canonical để thứ tự key hoặc khoảng trắng không làm thay đổi fingerprint nếu không ảnh hưởng ngữ nghĩa.
- Ghi rõ phiên bản công cụ hoặc thuật toán tạo fingerprint.
- Không đưa plaintext secret vào snapshot hoặc hash đầu vào có thể bị lộ qua từ điển giá trị.
- Với secret, ghi tham chiếu và version ID do secret manager cung cấp.
- Liên kết fingerprint với environment và artifact cụ thể.
- Lưu snapshot bất biến để người kiểm toán có thể xem lại nội dung đã được phê duyệt.

Nếu cấu hình được tạo từ nhiều nguồn, cần ghi nhận tất cả nguồn và revision liên quan. Ví dụ Helm values có thể được hợp nhất với defaults của chart và biến môi trường do deployment platform cấp.

## 11. Revalidation không phải lúc nào cũng có nghĩa là chạy lại toàn bộ pipeline

Khi một thành phần thay đổi, cần xác định những bằng chứng nào bị ảnh hưởng.

| Thay đổi | Kiểm tra nên chạy lại |
|---|---|
| Artifact digest đổi | Build provenance, test phù hợp, scan artifact, policy và approval |
| Deployment manifest đổi | Validate manifest, policy, quyền, resource/quota và approval theo mức ảnh hưởng |
| Runtime config đổi | Schema/config validation, integration hoặc smoke test liên quan, policy và approval nếu cần |
| Secret version đổi | Kiểm tra tham chiếu, quyền, trạng thái credential và test kết nối phù hợp |
| Environment state đổi | Readiness, compatibility, capacity và deployment conflict checks |
| Policy version đổi | Đánh giá lại toàn bộ điều kiện mà policy mới yêu cầu |
| Chỉ metadata mô tả đổi | Xác minh semantic content không đổi và ghi audit |

Ví dụ, nếu chỉ thay đổi một comment không ảnh hưởng nội dung thực thi, có thể không cần chạy lại toàn bộ unit test. Nhưng nếu image digest thay đổi, các bằng chứng gắn với artifact cũ không còn đủ để cho phép deploy artifact mới.

Một mô hình hiệu quả là ánh xạ mỗi loại thay đổi đến tập kiểm tra phụ thuộc. Tuy nhiên, khi không thể xác định chính xác phạm vi ảnh hưởng, nên chạy lại tập kiểm tra rộng hơn hoặc yêu cầu đánh giá lại.

## 12. Approval có thời hạn và điều kiện hết hiệu lực

Ngay cả khi nội dung không thay đổi, một approval vẫn có thể mất hiệu lực theo thời gian hoặc chính sách.

Ví dụ:

- Approval chỉ có giá trị trong một cửa sổ phát hành.
- Báo cáo vulnerability scan chỉ được chấp nhận trong một khoảng thời gian.
- Chứng thư ký artifact sắp hết hạn hoặc bị thu hồi.
- Người phê duyệt không còn thuộc nhóm có thẩm quyền.
- Change window đã kết thúc.
- Môi trường đã trải qua một thay đổi lớn.

Vì vậy, hồ sơ phê duyệt nên có thời điểm tạo và thời điểm hết hạn. Khi approval hết hạn, pipeline phải quay lại bước xác minh và phê duyệt theo chính sách.

Không nên gia hạn approval tự động nếu điều kiện đã thay đổi hoặc người duyệt không còn đủ thẩm quyền. Gia hạn phải được ghi nhận như một quyết định có chủ đích.

## 13. Xử lý các tình huống thay đổi cụ thể

### 13.1. Artifact được build lại sau phê duyệt

Ngay cả khi source commit không đổi, build mới có thể tạo digest khác. Pipeline cần coi đây là artifact mới, kiểm tra provenance và các bằng chứng liên quan, sau đó yêu cầu approval mới nếu policy yêu cầu.

Không được thay digest trong deployment request rồi giữ nguyên trạng thái approved.

### 13.2. Cấu hình thay đổi nhưng artifact giữ nguyên

Ví dụ image không đổi nhưng feature flag bật một luồng thanh toán mới. Pipeline cần kiểm tra cấu hình đã resolve, đánh giá tác động và xác định có cần kiểm thử tích hợp hoặc phê duyệt lại hay không.

### 13.3. Secret được xoay vòng

Không ghi giá trị secret vào snapshot. Ghi secret reference và version metadata. Khi version thay đổi, kiểm tra credential mới có được cấp cho đúng workload, còn hiệu lực và tương thích với dịch vụ đích hay không. Mức phê duyệt lại phụ thuộc chính sách bảo mật và tác động của lần xoay vòng.

### 13.4. Môi trường thay đổi bởi pipeline khác

Nếu một pipeline khác thay đổi schema, network policy hoặc phiên bản service dependency sau approval, cần revalidate điều kiện môi trường. Nếu trạng thái mới làm thay đổi rủi ro hoặc tính tương thích, approval cũ có thể stale.

### 13.5. Policy phát hành được cập nhật

Nếu policy mới bổ sung một kiểm tra bắt buộc, yêu cầu phê duyệt trước đó cần được đánh giá lại theo policy mới. Hồ sơ phải ghi rõ phiên bản policy nào đã được áp dụng.

## 14. Audit trail cho thay đổi và phê duyệt lại

Khi approval bị vô hiệu hóa, cần giữ lại lịch sử thay vì ghi đè trạng thái cũ.

Một bản ghi audit nên thể hiện:

| Trường | Nội dung |
|---|---|
| Approval ID | Định danh quyết định trước đó |
| Snapshot ID | Đối tượng đã được phê duyệt |
| Current snapshot | Đối tượng tại thời điểm kiểm tra lại |
| Changed fields | Những trường hoặc revision đã thay đổi |
| Change classification | Artifact, config, environment, policy hoặc evidence |
| Detection time | Thời điểm phát hiện |
| Validation result | Kiểm tra nào cần chạy lại và kết quả |
| Approval disposition | Giữ hiệu lực, stale, revoked hoặc cần approval mới |
| New approval ID | Quyết định mới nếu có |
| Actor | Người hoặc workload thực hiện hành động |
| Deployment ID | Lần triển khai cuối cùng |

Không xóa approval cũ khi tạo approval mới. Giữ lịch sử giúp xác định vì sao quyết định trước đó không còn hiệu lực và ai đã chấp nhận trạng thái mới.

Cần phân biệt:

- **Stale:** điều kiện đã thay đổi nên quyết định cũ không còn áp dụng.
- **Revoked:** người có thẩm quyền chủ động thu hồi quyết định.
- **Expired:** hết thời hạn hiệu lực.
- **Superseded:** đã có quyết định mới thay thế.

Các trạng thái này giúp báo cáo và điều tra rõ ràng hơn.

## 15. Ví dụ logic kiểm tra trước deploy

YAML sau mô tả luồng tổng quát. Đây không phải cú pháp trực tiếp của GitHub Actions, GitLab CI hoặc Jenkins:

~~~yaml
release:
  request:
    artifact_digest: required
    source_commit: required
    target_environment: required
    manifest_revision: required
    config_fingerprint: required
    policy_revision: required

  approval:
    bind_to:
      - artifact_digest
      - source_commit
      - target_environment
      - manifest_revision
      - config_fingerprint
      - policy_revision
      - evidence_revision
    require:
      - authorized_approver
      - approval_not_expired

  pre_deploy:
    steps:
      - resolve_current_artifact
      - resolve_current_configuration
      - resolve_current_environment
      - compare_with_approved_snapshot
      - verify_evidence_freshness
      - verify_policy_revision

    on_mismatch:
      - mark_approval_stale
      - record_changed_fields
      - rerun_affected_checks
      - request_new_approval_if_required
      - stop_deployment

    on_match:
      - acquire_environment_lock
      - compare_revision_again
      - deploy_approved_digest
      - verify_running_artifact_and_configuration
      - record_deployment_evidence
~~~

Điểm quan trọng là pipeline phải so sánh lại sau khi có được quyền điều phối hoặc lock cần thiết. Nếu trạng thái thay đổi giữa lần so sánh và thao tác deploy, conditional update hoặc bước kiểm tra bổ sung phải ngăn việc sử dụng approval cũ.

## 16. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Approval chỉ lưu trạng thái approved | Không biết đối tượng nào đã được duyệt | Gắn approval với snapshot và artifact digest |
| Dùng tag mutable để deploy | Tag có thể trỏ sang artifact khác | Resolve và deploy bằng digest |
| Chỉ kiểm tra source commit | Cấu hình hoặc image có thể đã thay đổi | Theo dõi cả artifact, manifest và runtime config |
| Không kiểm tra lại trước deploy | TOCTOU có thể làm triển khai trạng thái chưa duyệt | Revalidate sát thời điểm sử dụng |
| Thay config sau approval nhưng giữ approval | Hành vi thực tế khác điều người duyệt xem xét | Phân loại thay đổi và invalidate khi cần |
| Ghi plaintext secret vào snapshot | Rò rỉ credential | Ghi reference và version metadata |
| Chạy lại mọi thứ cho mọi thay đổi nhỏ | Pipeline chậm và lãng phí | Ánh xạ thay đổi với tập kiểm tra bị ảnh hưởng |
| Bỏ qua thay đổi vì cho là không đáng kể | Có thể bỏ sót thay đổi quyền hoặc hành vi | Dùng semantic diff và policy có thể kiểm toán |
| Ghi đè approval cũ | Mất dấu vết quyết định | Giữ lịch sử và liên kết approval mới |
| Không có lock hoặc conditional deploy | Trạng thái có thể đổi sau kiểm tra cuối | Điều phối và kiểm tra revision nguyên tử |

## 17. Checklist kiểm tra lại sau phê duyệt

Trước khi triển khai một release đã được phê duyệt, hãy xác nhận:

- [ ] Approval gắn với một snapshot cụ thể.
- [ ] Artifact được định danh bằng digest hoặc ID bất biến.
- [ ] Source commit và provenance khớp với artifact.
- [ ] Deployment manifest và cấu hình đã resolve đúng revision.
- [ ] Runtime config và feature flag liên quan còn khớp.
- [ ] Secret chỉ được tham chiếu bằng ID/version an toàn.
- [ ] Environment và dependency state còn đáp ứng điều kiện.
- [ ] Test, scan và evidence chưa hết hạn hoặc bị thu hồi.
- [ ] Policy revision hiện tại phù hợp với approval.
- [ ] Approval còn thời hạn và người duyệt còn đủ thẩm quyền.
- [ ] Thay đổi sau phê duyệt đã được phân loại và xử lý.
- [ ] Kiểm tra cuối được thực hiện sát thời điểm deploy.
- [ ] Có lock hoặc conditional update để giảm TOCTOU.
- [ ] Sau deploy đã xác minh artifact và cấu hình thực tế.
- [ ] Audit trail lưu snapshot cũ, thay đổi, quyết định mới và deployment ID.

## 18. Bài tập tự đánh giá

Một release của dịch vụ API đã được phê duyệt để triển khai production. Người duyệt đã xem image digest A, manifest revision 12, runtime config revision 31 và báo cáo scan S-204. Trong thời gian chờ cửa sổ triển khai:

- Một pipeline khác build lại image từ cùng commit và tạo digest B.
- Nhóm vận hành thay đổi timeout trong runtime config lên revision 32.
- Secret manager xoay payment key từ version 7 sang version 8.
- Policy phát hành được cập nhật để yêu cầu scan mới hơn.
- Một pipeline khác cập nhật resource quota của môi trường production.

Hãy phân tích:

1. Thành phần nào làm approval cũ chắc chắn không còn áp dụng?
2. Những thay đổi nào cần chạy lại kiểm tra kỹ thuật?
3. Secret version thay đổi có cần phê duyệt lại không? Điều kiện nào quyết định?
4. Làm thế nào xác định image B có thể thay thế image A?
5. Scan S-204 còn đủ bằng chứng cho digest B không?
6. Runtime config revision 32 cần được kiểm tra những gì?
7. Policy mới ảnh hưởng đến approval cũ ra sao?
8. Làm thế nào ngăn environment quota đổi sau lần revalidation cuối nhưng trước deploy?
9. Audit trail cần lưu những thông tin nào để giải thích quyết định cuối cùng?

Một thiết kế tốt sẽ không tiếp tục triển khai chỉ vì approval trước đó có trạng thái approved. Nó cần so sánh snapshot, phân loại thay đổi, thu thập lại bằng chứng và yêu cầu quyết định mới khi phạm vi hoặc rủi ro thay đổi.

## Kết luận

Phê duyệt trong CI/CD chỉ có ý nghĩa khi nó gắn với đúng artifact, cấu hình, môi trường, bằng chứng và chính sách đã được xem xét. Nếu một thành phần có ảnh hưởng thay đổi sau phê duyệt, pipeline cần phát hiện, đánh giá mức tác động và kiểm tra lại trước khi triển khai.

Hãy dùng artifact digest và revision bất biến, lưu approval snapshot, kiểm tra freshness của bằng chứng, xác minh trạng thái sát thời điểm deploy và ngăn thay đổi đồng thời bằng lock hoặc conditional update. Khi approval trở nên stale, giữ lại lịch sử, chạy lại các kiểm tra bị ảnh hưởng và yêu cầu phê duyệt mới theo chính sách. Cách làm này bảo đảm phiên bản thực sự được triển khai vẫn nằm trong phạm vi quyết định mà người có thẩm quyền đã chấp nhận.

