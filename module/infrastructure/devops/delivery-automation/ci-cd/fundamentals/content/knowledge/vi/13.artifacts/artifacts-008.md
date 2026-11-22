# Quản lý thời gian lưu để hỗ trợ kiểm chứng và quay lui

Artifact là sản phẩm cụ thể được tạo ra từ một revision mã nguồn, chẳng hạn JAR, package, binary, container image hoặc bundle frontend. Sau khi build và kiểm thử, artifact có thể được triển khai ở nhiều môi trường và được dùng lại khi cần phục hồi phiên bản ổn định. Tuy nhiên, nếu artifact hoặc bằng chứng liên quan bị xóa quá sớm, nhóm có thể không còn cách xác minh một bản phát hành cũ hoặc quay lui khi xảy ra sự cố.

**Retention (thời gian lưu)** là chính sách xác định artifact và dữ liệu liên quan được giữ trong bao lâu, ở đâu, với điều kiện nào và khi nào được phép xóa. Mục tiêu là cân bằng khả năng kiểm chứng, khôi phục, điều tra và tuân thủ với chi phí lưu trữ, bảo mật và vận hành.

Trong CI/CD, retention cần được thiết kế cùng vòng đời phát hành. Một artifact đang chạy ở production, một artifact đã được phê duyệt để rollback và một artifact tạm của pull request có giá trị lưu giữ khác nhau. Chính sách tốt phân biệt các nhóm này, gắn dữ liệu với commit và digest, đồng thời bảo vệ những phiên bản còn cần cho vận hành.

## 1. Vì sao cần chính sách retention?

Nếu chỉ giữ artifact mới nhất, nhóm có thể gặp các vấn đề sau:

- Không thể quay lại phiên bản ổn định trước đó khi bản phát hành mới gây lỗi.
- Không thể xác định binary đã được triển khai có đúng là binary đã qua kiểm thử hay không.
- Không còn test report, SBOM, chữ ký hoặc provenance để điều tra sự cố và lỗ hổng.
- Không thể tái hiện một lỗi đã xảy ra ở phiên bản cũ vì dependency hoặc image tương ứng đã bị xóa.
- Không đáp ứng được yêu cầu lưu bằng chứng kiểm toán hoặc yêu cầu hợp đồng.

Ngược lại, giữ mọi artifact vô thời hạn cũng tạo rủi ro. Dữ liệu cũ chiếm dung lượng, làm tăng chi phí registry và backup, kéo dài thời gian quét, và có thể lưu lại binary chứa lỗ hổng hoặc dữ liệu nhạy cảm không còn cần thiết.

Retention là một quyết định vận hành, không chỉ là cấu hình xóa file sau một số ngày. Chính sách cần trả lời: artifact nào phải còn sẵn sàng, bằng chứng nào phải đi cùng, ai được xóa, và điều kiện nào cho phép dọn dẹp.

## 2. Phân loại artifact và dữ liệu cần lưu

Không phải mọi đầu ra pipeline đều có cùng giá trị. Hãy phân loại trước khi đặt TTL (time to live).

| Nhóm | Ví dụ | Mục đích lưu giữ |
|---|---|---|
| Artifact phát hành | JAR, package, container image, binary đã được phê duyệt | Triển khai lại, rollback, phân phối và điều tra |
| Artifact trung gian | Test bundle, build output, package từ pull request | Debug hoặc tái sử dụng trong thời gian ngắn |
| Bằng chứng kiểm thử | Unit/integration test report, scan report, smoke test result | Chứng minh điều kiện chất lượng đã được đáp ứng |
| Provenance và metadata | Commit SHA, pipeline run, toolchain, build parameters, digest | Truy vết nguồn gốc và tái dựng ngữ cảnh build |
| SBOM và chữ ký | Danh sách thành phần, signature, attestation | Phân tích chuỗi cung ứng và xác minh tính toàn vẹn |
| Dữ liệu triển khai | Manifest, Helm chart, release descriptor, migration metadata | Hiểu cấu hình đã triển khai và hỗ trợ rollback |
| Log vận hành liên quan | Deploy log, approval record, audit event | Điều tra ai đã thực hiện hành động và kết quả ra sao |

Một artifact phát hành cần liên kết với bằng chứng của chính nó. Ví dụ, nếu image có digest `sha256:...`, test report, SBOM, chữ ký và provenance phải chỉ ra digest đó hoặc một định danh không nhập nhằng tương ứng. Lưu report mà không biết nó kiểm tra artifact nào sẽ làm giảm đáng kể giá trị kiểm chứng.

Không lưu secret, private key, token, mật khẩu hoặc dữ liệu cá nhân không cần thiết trong artifact và metadata. Nếu log vô tình chứa bí mật, cần xử lý theo quy trình sự cố và chính sách xóa/thu hồi; việc đặt TTL thông thường không thay thế xử lý lộ lọt.

## 3. Xác định thời gian lưu dựa trên mục đích

Không có một con số retention phù hợp cho mọi hệ thống. Thời gian cần thiết phụ thuộc vào tần suất phát hành, tốc độ phát hiện lỗi, thời gian khôi phục, yêu cầu kiểm toán, chính sách bảo mật và chi phí lưu trữ.

Một số câu hỏi cần trả lời:

1. **Rollback cần lùi bao xa?** Nếu sự cố thường được phát hiện sau vài ngày hoặc một chu kỳ tải, chỉ giữ bản trước ngay lập tức có thể không đủ.
2. **Artifact được triển khai ở đâu?** Mọi phiên bản còn chạy ở production hoặc môi trường quan trọng phải tiếp tục truy xuất được.
3. **Có yêu cầu kiểm toán hay hợp đồng không?** Một số bằng chứng cần được giữ theo thời hạn do tổ chức hoặc quy định áp dụng xác định.
4. **Có thể build lại chính xác không?** Nếu không thể tái tạo artifact cũ, việc lưu artifact gốc có giá trị cao hơn.
5. **Artifact có rủi ro bảo mật không?** Phiên bản có lỗ hổng cần được cách ly, gắn cảnh báo hoặc giới hạn truy cập, nhưng vẫn có thể cần giữ bằng chứng để điều tra.
6. **Chi phí lưu trữ ra sao?** Artifact lớn, image nhiều layer và log chi tiết có thể cần tầng lưu trữ khác nhau.

### Ví dụ phân tầng chính sách

Bảng sau chỉ là ví dụ khởi đầu để thảo luận; cần điều chỉnh theo nhu cầu thực tế và nghĩa vụ lưu trữ của tổ chức.

| Loại dữ liệu | Ví dụ chính sách tham khảo | Điều kiện bổ sung |
|---|---|---|
| Artifact pull request hoặc build tạm | 7–30 ngày | Xóa sớm hơn khi PR đóng nếu không còn cần điều tra |
| Artifact của nhánh tích hợp | Giữ một số lượng build gần nhất hoặc 14–30 ngày | Không giữ vô hạn mọi snapshot |
| Artifact release đã phát hành | 180 ngày hoặc lâu hơn theo rollback/audit window | Giữ mọi phiên bản còn được môi trường sử dụng hoặc còn trong rollback set |
| Artifact hiện đang chạy production | Không xóa khi còn được tham chiếu | Chỉ bỏ bảo vệ khi đã thay thế và hết thời gian rollback |
| Test report, scan report và provenance | Ít nhất bằng thời gian cần chứng minh release tương ứng | Liên kết với commit, digest và release ID |
| Audit/approval record | Theo chính sách kiểm toán và pháp lý | Có thể có legal hold hoặc yêu cầu lưu bất biến |

Không nên áp dụng cùng TTL cho image, report và log chỉ vì chúng được tạo trong một pipeline. Artifact có thể cần lưu lâu hơn log debug chi tiết; ngược lại, audit record có thể cần giữ lâu hơn artifact tạm.

## 4. Thiết kế rollback window

Rollback window là khoảng thời gian mà nhóm cam kết có thể quay về một phiên bản trước đó bằng artifact và dữ liệu đã lưu. Nó nên được xác định dựa trên rủi ro và khả năng vận hành.

Một cách suy nghĩ thực tế:

- Xác định khoảng thời gian tối đa thường cần để phát hiện một lỗi sau release.
- Cộng thêm thời gian điều tra, phê duyệt và thực hiện rollback.
- Xem xét lịch phát hành: nếu deploy nhiều lần trong ngày, cần giữ đủ số phiên bản đã biết là tốt để tránh mất bản ổn định gần nhất.
- Xem xét thời gian tương thích của database schema, message format và API.
- Dự phòng cho tình huống một bản release bị phát hiện lỗi sau khi đã có nhiều bản mới hơn.

Ví dụ, nhóm phát hành mỗi tuần và thường cần tối đa hai tuần để phát hiện lỗi nghiệp vụ trễ. Nhóm có thể cần giữ nhiều release ổn định trong khoảng dài hơn hai tuần, thay vì chỉ giữ hai artifact gần nhất. Con số cuối cùng cần dựa trên dữ liệu sự cố và khả năng khôi phục đã diễn tập.

### Không xóa artifact đang được sử dụng

Một điều kiện quan trọng là artifact còn được bất kỳ môi trường nào tham chiếu không được đưa vào hàng đợi xóa thông thường. Trước khi xóa, hệ thống cần kiểm tra:

- Digest có còn được deployment hiện tại tham chiếu không?
- Có release nào đang ở trạng thái rollback candidate không?
- Có rollout, canary hoặc blue-green deployment nào vẫn cần image cũ không?
- Có bản cài đặt hoặc khách hàng đang được hỗ trợ bằng phiên bản này không?
- Có investigation, security incident hoặc legal hold đang yêu cầu giữ không?

Nếu không có dữ liệu chính xác về các tham chiếu đang hoạt động, cần giữ an toàn hơn hoặc chuyển sang trạng thái cách ly chờ xác minh. Không nên dựa riêng vào ngày upload để xóa artifact.

## 5. Immutable artifact và định danh để truy xuất

Retention chỉ có ích khi nhóm tìm và lấy đúng artifact. Mỗi artifact phát hành nên có:

- Tên sản phẩm và loại artifact.
- Version hoặc release ID dễ đọc.
- Commit SHA nguồn.
- Pipeline run ID và thời điểm build.
- Digest hoặc checksum xác định nội dung.
- Provenance, SBOM, chữ ký và kết quả kiểm tra tương ứng nếu có.

Tag như `latest`, `stable` hoặc `production` thường là tham chiếu có thể di chuyển. Chúng hữu ích cho việc tra cứu hoặc triển khai tiện lợi, nhưng không nên là định danh duy nhất của một bản đã được kiểm chứng. Hãy dùng digest hoặc checksum khi cần bảo đảm chính xác nội dung.

Registry nên hỗ trợ immutable tag hoặc chính sách ngăn ghi đè phiên bản phát hành. Nếu cần thay đổi artifact, hãy tạo version/digest mới. Không chỉnh sửa nội dung của artifact cũ tại chỗ vì điều đó phá vỡ quan hệ giữa test evidence, provenance và binary được triển khai.

## 6. Lưu artifact cùng bằng chứng kiểm chứng

Một release record nên cho phép truy ngược từ môi trường đang chạy về đúng đầu vào và quyết định phát hành. Ví dụ:

```text
Release: orders-service 2.7.1
Source commit: 4f2a9c1...
Pipeline run: ci-18452
Artifact: registry.example.com/orders-service
Digest: sha256:...
Test evidence: test-report-18452
Security evidence: scan-report-18452
SBOM: sbom-2.7.1
Provenance: provenance-2.7.1
Deployment: production-eu / deployment-927
```

Các giá trị trên là dữ liệu minh họa. Trong hệ thống thật, dùng định danh đầy đủ và liên kết được máy đọc; không dựa vào tên file hoặc tên tag dễ trùng.

Khi điều tra, nhóm cần trả lời được:

- Artifact được tạo từ commit nào và pipeline run nào?
- Toolchain, dependency và base image nào đã tham gia build?
- Artifact đã vượt qua test và security gate nào?
- Ai hoặc quy trình nào đã phê duyệt promote?
- Digest nào đã được triển khai ở từng môi trường?
- Artifact nào là bản ổn định trước đó và còn có thể dùng để rollback?

Giữ report trong thời gian tương ứng với release giúp câu trả lời không biến mất khi artifact còn tồn tại. Với bằng chứng cần phục vụ audit, nên lưu cả thời điểm, danh tính thực hiện và dấu vết thay đổi của policy.

## 7. Ví dụ policy retention dưới dạng mã

Chính sách có thể được mô tả trong cấu hình registry, pipeline hoặc hệ thống quản lý artifact. Ví dụ dưới đây là mã giả, thể hiện ý tưởng phân loại và điều kiện bảo vệ:

```yaml
retention:
  pull_request:
    max_age_days: 14
    keep_if:
      - active_investigation

  branch_build:
    max_age_days: 30
    keep_last: 20

  release:
    min_age_days: 365
    keep_last: 10
    retain_evidence: true

  protected_artifacts:
    keep_if:
      - referenced_by_deployment
      - in_rollback_window
      - legal_hold
      - security_investigation

cleanup:
  dry_run_before_delete: true
  require_audit_record: true
  delete_only_unreferenced: true
```

Các khóa và giá trị trên không phải schema chuẩn của một registry cụ thể. Hệ thống thực tế có thể cấu hình retention theo tag pattern, repository, package type hoặc lifecycle rule riêng. Cần chuyển các điều kiện nghiệp vụ như `referenced_by_deployment` và `in_rollback_window` thành cơ chế có thể kiểm tra tự động hoặc quy trình phê duyệt.

Một cleanup job an toàn thường thực hiện theo hai pha:

1. **Lập danh sách:** xác định artifact hết hạn, kiểm tra tham chiếu đang dùng, rollback candidate, hold và chính sách retention.
2. **Thực thi:** chỉ xóa những artifact đủ điều kiện; ghi lại danh tính job, thời điểm, lý do và danh sách digest đã xóa.

Trước khi áp dụng tự động trên toàn registry, chạy chế độ dry-run và review danh sách dự kiến. Kiểm tra cả trường hợp tag nhiều tên cùng trỏ đến một digest và manifest đa kiến trúc có quan hệ với image con.

## 8. Dùng lifecycle và tầng lưu trữ phù hợp

Artifact có tần suất truy cập và yêu cầu phục hồi khác nhau. Có thể tổ chức nhiều tầng:

- **Hot storage:** artifact đang phát hành, đang triển khai hoặc nằm trong rollback window; cần tải nhanh.
- **Warm storage:** release cũ và bằng chứng ít truy cập nhưng vẫn cần cho điều tra hoặc audit.
- **Archive storage:** dữ liệu cần giữ dài hạn nhưng ít khi truy cập; thời gian khôi phục có thể lâu hơn.
- **Expired/pending deletion:** dữ liệu đã hết hạn nhưng đang chờ kiểm tra tham chiếu hoặc thời gian bảo vệ cuối cùng.

Việc chuyển tầng cần giữ nguyên định danh, checksum và metadata. Nếu archive yêu cầu thao tác restore trước khi deploy, quy trình rollback phải tính cả thời gian restore và xác minh tính toàn vẹn.

Không phải registry nào cũng hỗ trợ mọi tầng hoặc lifecycle rule. Có thể cần kết hợp artifact registry với object storage, catalog metadata hoặc hệ thống audit. Tránh tạo nhiều bản sao không được quản lý vì chúng có thể lệch digest, quyền truy cập và chính sách xóa.

## 9. Retention, backup và khả năng phục hồi

Retention và backup có mục đích khác nhau:

- **Retention** xác định dữ liệu được giữ theo vòng đời và chính sách nghiệp vụ.
- **Backup/replication** bảo vệ khả năng khôi phục khi registry, tài khoản, vùng lưu trữ hoặc dữ liệu bị mất/hỏng.

Giữ artifact 365 ngày trong một registry không đồng nghĩa có thể phục hồi nếu registry bị xóa nhầm hoặc tài khoản bị xâm nhập. Với artifact phát hành quan trọng, cần xem xét replication, backup metadata, quyền quản trị tách biệt và thử phục hồi định kỳ.

Checksum hoặc digest nên được kiểm tra sau khi copy/restore. Chữ ký và provenance cần còn truy xuất được; nếu khóa ký đã luân chuyển hoặc hết hạn, giữ metadata về danh tính và trạng thái tin cậy tại thời điểm ký theo chính sách của tổ chức.

Hãy kiểm thử quy trình restore thực tế. Một bản backup chưa từng được phục hồi thử không chứng minh rằng nhóm có thể lấy lại artifact trong thời gian yêu cầu.

## 10. Bảo mật và quyền xóa artifact

Artifact cũ vẫn có thể chứa mã nguồn đã biên dịch, cấu hình nhạy cảm hoặc dependency có lỗ hổng. Vì vậy, retention cần đi cùng kiểm soát truy cập:

- Chỉ cấp quyền đọc artifact cho pipeline và nhóm cần sử dụng.
- Tách quyền publish, promote, delete và quản trị retention.
- Hạn chế xóa artifact phát hành; yêu cầu approval hoặc quyền riêng cho thao tác phá hủy.
- Mã hóa khi lưu trữ và truyền tải theo khả năng của nền tảng.
- Quét artifact và SBOM theo lịch phù hợp; phát hiện lỗ hổng mới ở release cũ cần được đánh giá.
- Gắn trạng thái revoked/quarantined cho artifact không còn được phép triển khai.
- Không dùng retention như lý do giữ secret; thu hồi credential đã lộ và xử lý dữ liệu nhạy cảm theo quy trình riêng.

Một artifact bị thu hồi vì lỗ hổng không nhất thiết phải bị xóa ngay trong mọi trường hợp. Có thể cần giữ bản sao cách ly, hạn chế quyền truy cập và gắn nhãn không được deploy để phục vụ điều tra. Quyết định xóa phải cân bằng yêu cầu bảo mật, điều tra và nghĩa vụ lưu trữ.

## 11. Phối hợp retention với database và cấu hình khi rollback

Rollback không chỉ là chọn lại một file JAR hoặc container image. Một lần phát hành có thể thay đổi:

- Database schema và dữ liệu.
- Message format hoặc event contract.
- Cấu hình runtime và feature flag.
- Helm chart, manifest, infrastructure definition.
- API contract với consumer khác.
- Secret reference hoặc quyền truy cập dịch vụ.

Nếu artifact cũ còn được lưu nhưng migration database đã phá vỡ tương thích, triển khai lại artifact cũ có thể không khôi phục được hệ thống. Dùng chiến lược expand-and-contract khi có thể: mở rộng schema để phiên bản cũ và mới cùng hoạt động, chuyển đổi dữ liệu có kiểm soát, rồi chỉ loại bỏ cấu trúc cũ sau khi hết rollback window.

Release bundle nên giữ hoặc tham chiếu đến manifest triển khai, chart version, migration metadata và cấu hình không bí mật tương ứng. Secret không nên được đóng gói; hãy dùng secret manager và danh tính runtime hiện hành. Khi rollback, xác định rõ phiên bản cấu hình nào cần khôi phục và secret reference nào vẫn hợp lệ.

## 12. Quy trình dọn dẹp artifact an toàn

Một lifecycle job có thể đi qua các bước:

1. Tạo danh sách artifact theo repository, loại, tag, digest, ngày tạo và release status.
2. Đối chiếu với inventory deployment để biết digest nào còn đang chạy.
3. Đánh dấu các release trong rollback window, đang điều tra hoặc legal hold.
4. Kiểm tra bằng chứng bắt buộc đã được lưu theo retention riêng.
5. Chọn artifact hết hạn, không được tham chiếu và không bị hold.
6. Chạy dry-run, tạo báo cáo và yêu cầu phê duyệt nếu policy yêu cầu.
7. Xóa theo batch nhỏ, ghi audit record và xác minh kết quả.
8. Cập nhật catalog để tránh tham chiếu đến artifact đã xóa.

Nếu registry có garbage collection, cần hiểu cách nó xử lý manifest, tag và layer dùng chung. Xóa một tag không nhất thiết xóa layer ngay; chạy garbage collection có thể ảnh hưởng đến layer không còn được tham chiếu. Thực hiện theo hướng dẫn của registry và kiểm tra ảnh hưởng trước khi chạy trên dữ liệu production.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ giữ artifact mới nhất | Không còn bản ổn định để rollback | Giữ đủ release trong rollback window và các artifact đang được tham chiếu |
| TTL chung cho mọi artifact | Xóa sớm bằng chứng quan trọng hoặc giữ quá nhiều dữ liệu tạm | Phân loại theo loại dữ liệu và mục đích |
| Xóa theo tuổi mà không kiểm tra deployment | Xóa image vẫn đang chạy hoặc cần khôi phục | Đối chiếu digest với inventory môi trường |
| Chỉ giữ binary, xóa test report/provenance | Không chứng minh được binary đã qua kiểm tra nào | Lưu evidence cùng thời hạn phù hợp với release |
| Dùng tag di động làm định danh duy nhất | Không biết chính xác nội dung nào đã được deploy | Lưu digest/checksum và giữ metadata |
| Cho mọi pipeline quyền delete | Job lỗi hoặc bị xâm nhập có thể xóa release | Tách quyền publish/promote/delete và audit |
| Giữ artifact vô thời hạn | Tăng chi phí và bề mặt rủi ro | Có lifecycle, tiering và review định kỳ |
| Cho rằng artifact cũ bảo đảm rollback | Bỏ qua migration, config hoặc API compatibility | Diễn tập rollback toàn bộ release context |

## 14. Checklist thiết kế retention policy

- [ ] Phân loại artifact phát hành, build tạm, test evidence, provenance, SBOM và deployment metadata.
- [ ] Xác định rollback window theo thời gian phát hiện lỗi, tần suất release và khả năng phục hồi.
- [ ] Giữ mọi artifact còn được môi trường tham chiếu hoặc còn là rollback candidate.
- [ ] Liên kết artifact với commit SHA, pipeline run, digest và test/security evidence.
- [ ] Dùng immutable reference cho artifact phát hành và ngăn ghi đè nội dung.
- [ ] Đặt TTL khác nhau theo loại dữ liệu, rủi ro và yêu cầu audit.
- [ ] Có legal hold/security hold và trạng thái quarantine/revoked khi cần.
- [ ] Tách quyền publish, promote, delete và quản trị lifecycle.
- [ ] Dùng dry-run, kiểm tra tham chiếu và audit log trước khi xóa.
- [ ] Có backup/replication và thử restore cho artifact quan trọng.
- [ ] Giữ manifest, chart, migration metadata và cấu hình không bí mật cần thiết cho rollback.
- [ ] Diễn tập rollback và xác minh thời gian khôi phục thực tế.

Retention tốt bảo đảm nhóm còn đúng artifact và bằng chứng khi cần kiểm chứng hoặc phục hồi. Khi thời gian lưu được gắn với release lifecycle, digest, deployment inventory và rollback window, việc dọn dẹp có thể giảm chi phí mà không làm mất khả năng truy vết và khôi phục của CI/CD.
