# Evidence của verification: bằng chứng kiểm chứng yêu cầu bảo mật

## 1. Vì sao cần quản lý bằng chứng?

Một dashboard có màu xanh hoặc một báo cáo “test passed” chưa đủ để người khác xác nhận yêu cầu bảo mật đã được đáp ứng. Có thể báo cáo không ghi phiên bản phần mềm, chỉ kiểm tra một đường truy cập, dùng sai tài khoản hoặc được tạo trước khi cấu hình thay đổi.

Evidence của verification là các thông tin và hiện vật được thu thập, gắn ngữ cảnh và xem xét để hỗ trợ kết luận về một yêu cầu xác định. Giá trị của chúng nằm ở mối liên hệ giữa điều được khẳng định, cách kiểm chứng và điều thực sự quan sát được.

NIST mô tả verification theo hướng xác nhận các yêu cầu đã đặc tả được đáp ứng thông qua bằng chứng khách quan. Trong bài này, trọng tâm là kiểm chứng yêu cầu bảo mật, không phải xác minh danh tính của một cá nhân. [Nguồn: NIST CSRC — Verification](https://csrc.nist.gov/glossary/term/verification).

Trong chương Kiểm thử yêu cầu của module Security Requirements, bằng chứng giúp nối mục tiêu an toàn thông tin và rủi ro với kiến trúc, ca kiểm thử, kết quả và quyết định phát hành hoặc vận hành.

Sau bài học, người học có thể:

- Xác định bằng chứng cần có cho từng tiêu chí chấp nhận.
- Phân biệt quan sát, kết quả, kết luận và quyết định quản trị.
- Gắn bằng chứng với đúng bản triển khai, cấu hình, phạm vi và thời gian.
- Bảo vệ nguồn gốc, tính toàn vẹn và dữ liệu nhạy cảm trong hồ sơ.
- Đánh giá khi nào bằng chứng đủ, còn áp dụng hoặc cần kiểm chứng lại.

Các mã định danh, thời hạn và cấu trúc dữ liệu trong bài là ví dụ thiết kế nội bộ cho một hệ thống giả định. Chúng không phải schema bắt buộc của NIST hoặc điều kiện đủ để chứng nhận tuân thủ.

## 2. Tách yêu cầu, quan sát, kết quả và quyết định

Giả sử yêu cầu là: “Người dùng chỉ đọc được hóa đơn của tổ chức mà họ có quyền.”

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Yêu cầu | Điều hệ thống phải bảo đảm | Cách ly quyền đọc hóa đơn giữa các tổ chức |
| Tiêu chí chấp nhận | Điều kiện cụ thể để đánh giá | Người A không nhận dữ liệu B qua các đường đã liệt kê |
| Phương pháp | Cách thu thập bằng chứng | Kiểm thử API, đường tải và xem cấu hình quyền |
| Quan sát | Dữ kiện được ghi nhận | Request có danh tính A nhận lỗi chung, không có dữ liệu B |
| Kết quả | Đối chiếu quan sát với tiêu chí | Ca T-AUTHZ-07 đạt trên bản triển khai đang kiểm tra |
| Kết luận | Mệnh đề được bằng chứng hỗ trợ | Các tiêu chí trong phạm vi kiểm chứng đã đạt |
| Quyết định | Hành động theo thẩm quyền | Chấp nhận phát hành, yêu cầu sửa hoặc xem xét ngoại lệ |

Một dòng “PASS” là bản tóm tắt kết quả, không thay thế toàn bộ căn cứ. Chữ ký phê duyệt là bằng chứng của quyết định, không tự chứng minh hành vi hệ thống.

Cũng cần phân biệt verification với việc đánh giá yêu cầu có phù hợp nhu cầu sử dụng thực tế hay không. Hệ thống có thể đáp ứng đúng một yêu cầu đã đặc tả nhưng yêu cầu đó còn thiếu đường truy cập hoặc chưa xử lý đúng rủi ro. Vì vậy, bằng chứng kiểm chứng phải được đặt trong bối cảnh phạm vi yêu cầu.

### Lập luận nối bằng chứng với kết luận

Một hồ sơ cần thể hiện:

~~~text
Khẳng định:
  API xuất hóa đơn thực thi quyền theo tổ chức.

Bằng chứng:
  Danh tính và quyền thử; dữ liệu tổng hợp; kết quả ca hợp lệ và trái quyền;
  phản hồi, tác dụng phụ nghiệp vụ và cấu hình triển khai liên quan.

Lập luận:
  Các ca đại diện kiểm tra đúng điểm thực thi và các kết quả thỏa tiêu chí.

Giới hạn:
  Chưa kiểm tra đường tải file mới hoặc tác vụ nền ngoài danh sách phạm vi.
~~~

Không bỏ phần giới hạn rồi nâng kết luận thành “toàn bộ hệ thống không có lỗi phân quyền”.

## 3. Các nguồn evidence và phạm vi sử dụng

NIST SP 800-53A sử dụng các phương pháp đánh giá như xem xét đối tượng, phỏng vấn và kiểm thử để thu thập bằng chứng. Việc chọn phương pháp cần phù hợp với mục tiêu và đối tượng đánh giá. [Nguồn: NIST CSRC — Assessment Method](https://csrc.nist.gov/glossary/term/assessment_method).

Bảng dưới là cách áp dụng minh họa cho phát triển phần mềm:

| Nguồn bằng chứng | Điều có thể hỗ trợ | Giới hạn cần ghi |
| --- | --- | --- |
| Yêu cầu và thiết kế đã review | Phạm vi, giả định, vị trí kiểm soát và tiêu chí | Chưa chứng minh triển khai thực tế đúng thiết kế |
| Code review | Logic được xem xét tại một revision | Chưa chứng minh artifact triển khai được tạo từ revision đó |
| Kết quả kiểm thử tự động | Hành vi trên fixture và môi trường xác định | Phụ thuộc assertion, mock, độ bao phủ và chất lượng dữ liệu |
| Kiểm thử thủ công | Hành vi hoặc cấu hình cần quan sát chuyên môn | Cần bước thực hiện, dữ kiện và người đánh giá rõ ràng |
| Cấu hình hiệu lực | Trạng thái thực tế tại thời điểm thu thập | Có thể thay đổi sau đó; khác với cấu hình mong muốn trong repository |
| Log và trace | Chuỗi sự kiện, danh tính, thời gian và kết quả | Thiếu log không tự chứng minh sự kiện không xảy ra |
| Báo cáo scanner | Phát hiện trong phạm vi và quy tắc đã chạy | Không chứng minh mọi lớp kiểm soát hoặc mọi điểm yếu |
| Phỏng vấn, xác nhận vận hành | Hiểu quy trình, trách nhiệm và vị trí nguồn dữ liệu | Với hành vi kỹ thuật, thường cần đối chiếu bằng chứng thực hiện |
| Báo cáo diễn tập | Khả năng phục hồi trong kịch bản cụ thể | Chưa chứng minh mọi dạng sự cố đều được xử lý |
| Hồ sơ phê duyệt | Ai quyết định, khi nào, trên căn cứ nào | Quyết định chấp nhận rủi ro không biến yêu cầu chưa đạt thành đã đạt |

Không có một loại tài liệu luôn mạnh hơn mọi loại khác. Ảnh chụp có thể hữu ích để ghi lại trạng thái giao diện, trong khi một export cấu hình có nguồn gốc rõ ràng có thể phù hợp hơn cho tiêu chí quyền hiệu lực. Lựa chọn cần theo điều muốn chứng minh.

## 4. Các thuộc tính của evidence có giá trị

Một hồ sơ tốt cần được đánh giá theo nhiều chiều:

- **Liên quan:** trả lời đúng tiêu chí, không chỉ có tên công cụ hoặc tên kiểm soát.
- **Đủ phạm vi:** bao phủ tài sản, đường truy cập, vai trò và thời điểm đã cam kết.
- **Có nguồn gốc:** xác định ai hoặc hệ thống nào thu thập và từ đối tượng nào.
- **Đúng phiên bản:** gắn với yêu cầu, code, artifact, cấu hình và chính sách phù hợp.
- **Có thể kiểm tra lại:** đủ thông tin để hiểu hoặc thực hiện lại phương pháp khi cần.
- **Được bảo vệ:** hạn chế thay đổi, truy cập, xóa và lộ dữ liệu ngoài mục đích.
- **Còn áp dụng:** chưa có thay đổi làm mất cơ sở của kết luận.
- **Minh bạch giới hạn:** thể hiện dữ liệu thiếu, giả định và các phần chưa được đánh giá.

“Khách quan” không có nghĩa mọi dữ liệu đều đúng chỉ vì được máy tạo. Một job tự động có thể chạy nhầm môi trường hoặc dùng mock luôn cho phép. Cần xem nguồn, cấu hình và cách tạo kết quả.

## 5. Đặc tả evidence cùng tiêu chí chấp nhận

Không nên đợi đến cuối đợt kiểm thử mới hỏi cần chụp hoặc lưu gì. Khi viết tiêu chí, xác định trước “hợp đồng bằng chứng”.

| Mục | Nội dung cần thống nhất |
| --- | --- |
| Khẳng định cần chứng minh | Mệnh đề cụ thể, có phạm vi và phiên bản |
| Nguồn yêu cầu | Mã yêu cầu, rủi ro, nghĩa vụ hoặc chính sách liên quan |
| Đối tượng | Dịch vụ, endpoint, dữ liệu, vai trò, môi trường |
| Phương pháp | Test, review, xem cấu hình, đối soát hoặc kết hợp |
| Tiền điều kiện | Danh tính, quyền, dữ liệu và phụ thuộc phải có |
| Kết quả mong đợi | Hành vi, ngưỡng, thời gian và tác dụng phụ được phép hoặc bị cấm |
| Dữ liệu cần ghi | Quan sát đủ để kiểm tra từng điều kiện |
| Định danh triển khai | Artifact, cấu hình, chính sách, phụ thuộc quan trọng |
| Thời gian | Mốc bắt đầu, kết thúc, múi giờ và cách đo khoảng thời gian |
| Công cụ / người thực hiện | Phiên bản harness, quy tắc scanner hoặc người đánh giá |
| Bảo vệ | Quyền truy cập, loại dữ liệu, redaction và nơi lưu |
| Tái sử dụng | Điều kiện còn áp dụng và thay đổi buộc kiểm chứng lại |
| Quyết định | Người xem xét, trạng thái, phát hiện và điều kiện đóng |

Ví dụ tiêu chí thu hồi phiên trong 60 giây cần có bằng chứng mốc thu hồi tại nguồn có thẩm quyền, các request mới qua đường liên quan, thời điểm server đánh giá và kết quả. Chỉ có ảnh tài khoản bị khóa không chứng minh phiên cũ đã mất quyền truy cập.

Một tiêu chí về quản lý khóa có thể cần xem cấu hình và quyền hiệu lực, không thể thay bằng ảnh API trả 200. Chọn nguồn evidence theo thuộc tính cần xác nhận.

## 6. Tình huống: bằng chứng cho phân quyền xuất hóa đơn

### 6.1. Yêu cầu và phạm vi

Giả sử:

**SEC-AUTHZ-31 v2:** người dùng chỉ tạo và tải bản xuất hóa đơn trong tổ chức mà họ có quyền; API, worker và đường tải không được làm mất ràng buộc này.

Các tiêu chí gồm:

- AC-31-01: người có quyền xuất tại A tạo được bản xuất đúng dữ liệu A.
- AC-31-02: người A không tạo được bản xuất dữ liệu B qua API.
- AC-31-03: worker giữ đúng tổ chức và tập dữ liệu được cấp.
- AC-31-04: người A không tải được file thuộc B qua đường tải được hỗ trợ.
- AC-31-05: các thao tác thuộc phạm vi có audit đáp ứng yêu cầu liên quan.

Fixture có tài khoản A-exporter và B-exporter với quyền tách biệt, hóa đơn tổng hợp có giá trị phân biệt và các phiên client độc lập.

### 6.2. Bộ evidence minh họa

| Mã | Nội dung | Mục đích |
| --- | --- | --- |
| E-01 | Snapshot yêu cầu và tiêu chí đã dùng | Biết đang đánh giá điều kiện nào |
| E-02 | Định danh artifact, triển khai, cấu hình và policy | Gắn kết quả với đối tượng thực tế |
| E-03 | Mô tả fixture, quyền và dữ liệu kỳ vọng | Xác nhận tiền điều kiện độc lập với response |
| E-04 | Kết quả test API hợp lệ và trái quyền | Hỗ trợ AC-31-01, AC-31-02 |
| E-05 | Quan sát worker và tập bản ghi trong file | Hỗ trợ AC-31-03 |
| E-06 | Request tải file bằng các danh tính thử | Hỗ trợ AC-31-04 |
| E-07 | Audit có mã tương quan và thời gian | Hỗ trợ AC-31-05 |
| E-08 | Kết luận, phát hiện và quyết định đánh giá | Giữ lập luận và trách nhiệm |

Trong tình huống giả định, API từ chối yêu cầu trái quyền và worker tạo đúng file, nhưng đường tải vẫn trả file B cho người A biết mã file. Kết quả:

| Tiêu chí | Kết quả |
| --- | --- |
| AC-31-01 | PASS |
| AC-31-02 | PASS |
| AC-31-03 | PASS |
| AC-31-04 | FAIL |
| AC-31-05 | PASS trên các thao tác đã kiểm tra |

Không được dùng báo cáo “các test API đã PASS” để kết luận SEC-AUTHZ-31 đạt toàn bộ. Bằng chứng E-06 cho thấy một tiêu chí trực tiếp không đạt. Kết luận phải giữ rõ đường lỗi, điều kiện khai thác trong fixture và phạm vi đã đánh giá.

Nếu E-06 chưa được thu thập, AC-31-04 là chưa đánh giá, không tự là PASS hoặc FAIL. Thiếu bằng chứng và có bằng chứng vi phạm là hai tình huống khác nhau.

### 6.3. Tách dữ liệu gốc, bản đã xử lý và bản tóm tắt

Một gói evidence có thể gồm:

~~~text
evidence-package/
  manifest.json
  requirement-snapshot.txt
  test-results.json
  sanitized-http-observations.txt
  effective-policy-snapshot.json
  audit-query-and-results.txt
  assessment-decision.txt
~~~

Đây là cấu trúc minh họa, không phải các file bắt buộc phải tạo cho mọi bài kiểm tra.

Dữ liệu gốc có thể chứa thông tin nhạy cảm, cần nơi lưu và quyền riêng. Bản đã redaction phục vụ người xem xét rộng hơn; bản tóm tắt dùng để ra quyết định hoặc theo dõi. Các bản cần giữ quan hệ nguồn gốc để không nhầm một bảng đã lọc với toàn bộ quan sát.

Đừng tự xóa dữ kiện mâu thuẫn với kết luận mong muốn. Nếu một lần chạy FAIL rồi lần sau PASS, giữ liên kết giữa lỗi, thay đổi khắc phục và lần kiểm chứng lại.

## 7. Manifest và ánh xạ từng kết luận

Manifest là chỉ mục của gói evidence: định danh, phạm vi, các hiện vật, quan hệ truy vết và điều kiện đọc. Nó hỗ trợ tìm và kiểm tra dữ liệu, không tự thay thế nội dung hiện vật.

Ví dụ JSON dưới đây là schema nội bộ minh họa, không phải định dạng SLSA hoặc chuẩn chứng nhận. Các giá trị dạng <...> là placeholder.

~~~json
{
  "evidencePackageId": "EV-AUTHZ-31-RUN-042",
  "requirement": {
    "id": "SEC-AUTHZ-31",
    "version": "2"
  },
  "scope": {
    "service": "billing-export",
    "environment": "verification",
    "paths": ["export-api", "export-worker", "download-api"]
  },
  "subject": {
    "sourceRevision": "<source-revision>",
    "artifactDigest": "sha256:<artifact-digest>",
    "deploymentId": "<deployment-id>",
    "effectiveConfigDigest": "sha256:<config-snapshot-digest>",
    "policyVersion": "<policy-version>"
  },
  "execution": {
    "runId": "RUN-042",
    "testSuiteRevision": "<test-suite-revision>",
    "startedAt": "<ISO-8601-timestamp>",
    "completedAt": "<ISO-8601-timestamp>"
  },
  "findings": [
    {
      "criterionId": "AC-31-04",
      "result": "FAIL",
      "evidenceRefs": ["E-03", "E-06"],
      "findingId": "F-AUTHZ-09"
    }
  ],
  "limitations": [
    "Chỉ kết luận cho phạm vi và bản triển khai đã ghi nhận"
  ]
}
~~~

Một gói thực tế cần ánh xạ đầy đủ các tiêu chí thuộc phạm vi, bao gồm kết quả chưa đánh giá. Ví dụ chỉ hiển thị một finding để tập trung vào cấu trúc.

Manifest có thể giữ tham chiếu tới cấu hình hoặc dữ liệu được giới hạn quyền, thay vì nhúng toàn bộ nội dung. Digest phải gắn với đúng phiên bản hiện vật được tham chiếu; nếu bản đã redaction có nội dung khác, nó có digest và quan hệ nguồn riêng.

Một gói “đầy đủ file” nhưng không biết file nào hỗ trợ AC-31-04 vẫn khó kiểm tra. Ánh xạ nên đi tới đúng đoạn quan sát, bản ghi hoặc ca thử, với đủ ngữ cảnh để tránh chọn lọc dữ liệu.

## 8. Ràng buộc bằng chứng với đúng đối tượng triển khai

“Đã kiểm thử commit X” chưa chứng minh artifact đang chạy được tạo từ commit X. “Đã kiểm thử image release-2” cũng chưa đủ nếu tag đó có thể trỏ sang nội dung khác.

Cần giữ các liên kết phù hợp với hệ thống:

1. Revision nguồn dùng để tạo artifact.
2. Artifact cụ thể được tạo, thường có định danh nội dung.
3. Bản triển khai thực sự dùng artifact đó.
4. Cấu hình và policy hiệu lực khi đánh giá.
5. Phiên bản bộ kiểm thử, quy tắc scanner và phụ thuộc liên quan tới kết luận.

Trong SLSA, provenance cung cấp thông tin có thể kiểm chứng về nguồn gốc và cách một artifact được tạo. Có thể dùng loại thông tin này để hỗ trợ liên kết nguồn với artifact; nó không tự chứng minh yêu cầu phân quyền hoặc logging của ứng dụng đã đạt. [Nguồn: SLSA v1.2 — Provenance](https://slsa.dev/spec/v1.2/provenance).

### Cấu hình mong muốn khác cấu hình hiệu lực

Một file cấu hình trong repository có thể đúng, nhưng biến môi trường, feature flag, policy tại IdP hoặc cấu hình gateway đang khác.

Với tiêu chí bị ảnh hưởng bởi các yếu tố đó, cần snapshot hoặc tham chiếu có phiên bản tới trạng thái hiệu lực. Thu thập trong cửa sổ kiểm chứng và kiểm soát thay đổi giữa lúc chụp trạng thái với lúc chạy test.

Không phải đóng băng mọi thứ trong môi trường. Cần nhận diện những thành phần ảnh hưởng tới khẳng định. Ví dụ nếu kiểm chứng thu hồi phiên, cơ chế cache quyết định và policy tại resource server có thể quan trọng hơn một cấu hình giao diện không liên quan.

Khi bằng chứng chỉ gắn với môi trường kiểm thử, nêu rõ điều đó. Để hỗ trợ quyết định triển khai ở môi trường mục tiêu, cần xem các khác biệt liên quan và bằng chứng xác nhận cấu hình cần thiết đã được áp dụng.

## 9. Tính toàn vẹn, nguồn gốc và khả năng kiểm tra lại

### 9.1. Digest hỗ trợ điều gì?

Digest như SHA-256 có thể hỗ trợ phát hiện việc nội dung đã thay đổi so với một giá trị tham chiếu đáng tin cậy.

Quy trình minh họa:

- Hoàn tất và định danh hiện vật.
- Tính digest trên đúng dữ liệu sẽ được tham chiếu.
- Ghi quan hệ giữa hiện vật, digest, người hoặc hệ thống thu thập.
- Bảo vệ nơi lưu digest và hiện vật theo thiết kế.
- Khi kiểm tra lại, tính digest và đối chiếu đúng phiên bản.

Nếu người có quyền sửa file cũng có thể thay digest và manifest mà không để lại dấu vết, việc đối chiếu có thể không phát hiện được hành vi đó. Digest không tự chứng minh ai đã tạo file, file được tạo khi nào hoặc dữ liệu nguồn là đúng.

Hash cũng không phải cơ chế che bí mật. Không dùng việc băm một giá trị dễ đoán làm căn cứ rằng dữ liệu nhạy cảm đã được bảo vệ đủ.

### 9.2. Chữ ký và xác nhận nguồn phát hành

Nếu dùng chữ ký hoặc attestation, phải kiểm tra nội dung được ký, đối tượng được tham chiếu, danh tính ký, nguồn tin cậy và chính sách chấp nhận tương ứng. Chữ ký hợp lệ với một khóa bất kỳ chưa đủ nếu khóa đó không thuộc nguồn được tin cậy.

Chữ ký giúp bảo vệ quan hệ giữa nguồn phát hành và nội dung trong điều kiện tin cậy đã thiết lập. Nó không biến một test sai assertion hoặc một báo cáo chạy nhầm môi trường thành bằng chứng đúng.

Tránh tự nhận gói evidence “đạt một mức bảo đảm” chỉ vì chứa chữ ký. Mức bảo đảm phụ thuộc cả cách thu thập, quyền tạo dữ liệu, môi trường thực hiện và kiểm soát nguồn phát hành.

### 9.3. Khả năng kiểm tra lại và chuỗi quản lý

Với bằng chứng quan trọng, nên ghi nhận ai thu thập, ai chuyển giao, các lần chuyển đổi hoặc redaction và vị trí lưu từng phiên bản. Khi tải hoặc xuất từ hệ thống ngoài, giữ định danh nguồn và tham số truy vấn cần thiết.

Khả năng kiểm tra lại không luôn có nghĩa dựng lại chính xác từng byte của một môi trường đang chạy. Cần đủ thông tin để người xem xét hiểu phương pháp, kiểm tra dữ kiện và thực hiện lại phép đánh giá tương đương khi cần.

Nếu nguồn chỉ còn một URL hết hạn hoặc dashboard thay đổi liên tục, hồ sơ có thể mất khả năng xem xét. Cần snapshot hoặc cơ chế lưu phiên bản phù hợp với yêu cầu bằng chứng.

## 10. Evidence cho năm nhóm yêu cầu bảo mật

| Nhóm | Khẳng định minh họa | Bằng chứng nên kết hợp | Chưa đủ để kết luận |
| --- | --- | --- | --- |
| Xác thực | Mọi đường quản trị trong phạm vi thực thi chính sách xác thực | Policy hiệu lực, phiên thử, ca hợp lệ và thiếu điều kiện, kết quả đầu cuối | Chỉ thấy tài khoản đã đăng ký MFA |
| Phân quyền | Hành động giới hạn đúng chủ thể, tài nguyên và tổ chức | Fixture quyền, ca cho phép và từ chối, tác dụng phụ, đường API/worker/tải | Chỉ có annotation hoặc HTTP 403 |
| Dữ liệu | Dữ liệu được bảo vệ theo phạm vi và cơ chế đã yêu cầu | Cấu hình lưu/truyền, cơ chế khóa, quyền hiệu lực, kiểm tra hành vi và bản sao liên quan | Chỉ không thấy chuỗi rõ trong một file |
| Logging | Sự kiện bắt buộc có thể truy xuất đúng nội dung và thời hạn | Chuỗi hành động tổng hợp, mã tương quan, truy vấn, kết quả và phép đo thời gian | Chỉ có heartbeat collector hoặc một ảnh log |
| Phục hồi | Hệ thống phục hồi dữ liệu và nghiệp vụ theo yêu cầu | Báo cáo diễn tập, mốc dữ liệu, thời gian, kiểm tra quyền và chức năng sau phục hồi | Chỉ có tác vụ backup báo thành công |

### Ví dụ logging: giữ cả điều kỳ vọng và điều quan sát

Giả sử phép kiểm tra tạo ba thao tác thay đổi quyền. Báo cáo chỉ liệt kê hai sự kiện nhận được có thể trông hợp lệ nếu không lưu danh sách ba thao tác kỳ vọng.

Cần có tập hành động đã phát sinh, mối tương quan tới sự kiện, điều kiện khử trùng lặp nếu có retry và giới hạn độ trễ. Khi chỉ quan sát hai trong ba sự kiện, không dùng “hai sự kiện đều đúng cấu trúc” để kết luận yêu cầu đầy đủ đã đạt.

### Ví dụ phục hồi: chứng minh kết quả

Với một mục tiêu RTO/RPO đã được phê duyệt, lưu mốc sự cố, mốc dịch vụ đạt điều kiện sẵn sàng và mốc dữ liệu nhất quán khôi phục được. Kèm kết quả kiểm tra nghiệp vụ, quyền truy cập và các phụ thuộc cần thiết.

Không dùng thời gian sửa file backup làm bằng chứng duy nhất cho tuổi dữ liệu khôi phục. Nếu diễn tập loại trừ dịch vụ danh tính hoặc khóa giải mã, kết luận phải phản ánh phần loại trừ đó.

## 11. Bảo vệ dữ liệu trong gói evidence

HTTP trace, log và ảnh chụp có thể chứa token, cookie, thông tin cá nhân, nội dung hóa đơn hoặc cấu hình nhạy cảm. Kho bằng chứng cần được thiết kế như một nơi xử lý dữ liệu có giá trị, với quyền đọc, ghi, xóa và xuất phù hợp.

Nguyên tắc thực hiện:

- Dùng dữ liệu tổng hợp khi vẫn chứng minh được tiêu chí.
- Thu thập phần cần thiết cho kết luận, tránh dump toàn bộ dữ liệu theo thói quen.
- Loại bỏ thông tin xác thực khỏi bản được chia sẻ.
- Tách quyền trên dữ liệu gốc với quyền trên báo cáo tóm tắt.
- Ghi nhận việc truy cập hoặc thay đổi evidence quan trọng.
- Áp dụng bảo vệ lưu trữ, quản lý khóa và sao lưu theo phân loại.
- Kiểm soát việc tải xuống và chia sẻ liên kết nếu nguồn có dữ liệu nhạy cảm.

### Redaction phải giữ giá trị chứng minh

Nếu cần chứng minh người A không nhận dữ liệu B, không được che mất mọi dấu hiệu phân biệt A và B rồi vẫn tuyên bố bản đã che đủ chứng minh cách ly.

Có thể thay tên thật bằng mã tổng hợp hoặc bí danh nhất quán, giữ quan hệ so sánh cần thiết. Bản gốc và bản đã xử lý cần định danh riêng, mô tả cách chuyển đổi và quyền truy cập tương ứng.

Nếu chính tiêu chí đang kiểm tra việc lộ bí mật trong log, không phát tán bí mật đó để báo lỗi. Có thể lưu bằng chứng chi tiết trong phạm vi hạn chế và báo cáo mẫu nhận diện đã che theo cách vẫn cho người có thẩm quyền xác minh được finding.

### Lưu giữ và kết thúc vòng đời

Thời hạn lưu cần dựa trên mục đích, rủi ro, nhu cầu điều tra, hợp đồng và nghĩa vụ áp dụng. Không suy ra một số năm chung từ tên tiêu chuẩn hoặc tên loại báo cáo.

Cần xác định cả việc xóa, thu hồi quyền và xử lý bản sao khi hết mục đích. Ghi nhận “bằng chứng đã bị xóa theo chính sách” khác với việc bằng chứng không từng tồn tại hoặc đã chứng minh mọi thuộc tính.

## 12. Bằng chứng còn áp dụng hay đã hết cơ sở?

Một báo cáo cũ vẫn có thể là bằng chứng đúng về lịch sử, nhưng không còn đủ để hỗ trợ kết luận cho hiện trạng. Cần phân biệt tính toàn vẹn của hồ sơ với khả năng áp dụng kết quả.

Các thay đổi có thể làm ảnh hưởng:

| Thay đổi | Phần evidence cần xem lại |
| --- | --- |
| Sửa logic kiểm tra quyền | Các ca và review liên quan tới chức năng, đối tượng, thuộc tính |
| Thêm API hoặc đường tải | Phạm vi truy cập, ca cho phép và từ chối, ánh xạ tiêu chí |
| Đổi IdP hoặc policy phiên | Xác thực, thu hồi, ngữ cảnh danh tính và thời hạn |
| Đổi cấu hình mã hóa hoặc khóa | Quyền, cơ chế bảo vệ và khả năng phục hồi |
| Thay collector hoặc schema audit | Độ đầy đủ, nội dung và độ trễ bằng chứng |
| Đổi chiến lược sao lưu | Kịch bản phục hồi, mốc dữ liệu và thời gian |
| Thay môi trường hoặc phụ thuộc quan trọng | Các giả định mà kết luận trước dựa vào |
| Phát hiện assertion hoặc công cụ có lỗi | Các kết quả được tạo bởi phần đánh giá bị ảnh hưởng |

Không nhất thiết chạy lại mọi thứ cho mọi thay đổi. Cần phân tích tác động, xác định bằng chứng nào vẫn áp dụng và ghi căn cứ tái sử dụng.

### Ví dụ thay đổi cấu hình mà không đổi artifact

Bản R1 đã được kiểm chứng với policy P1. Sau đó artifact không đổi nhưng gateway chuyển sang P2, mở thêm đường tải file.

Digest artifact vẫn khớp không có nghĩa AC-31-04 tiếp tục được chứng minh. Phải xem policy mới và đường truy cập mới có nằm trong bằng chứng cũ không.

Ngược lại, nếu chỉ thay phần mô tả giao diện không ảnh hưởng đường kiểm soát hoặc quan sát, có thể tái sử dụng phần evidence phù hợp trên căn cứ được ghi lại. Quyết định cần dựa vào tác động, không chỉ vào số ngày đã qua.

### Tách ba chiều trạng thái

- **Kết quả đánh giá:** PASS, FAIL hoặc chưa đủ căn cứ cho tiêu chí.
- **Khả năng áp dụng:** còn áp dụng, bị thay thế hoặc cần xem xét lại.
- **Quyết định:** chấp nhận, yêu cầu xử lý hoặc cho phép có điều kiện theo thẩm quyền.

Một PASS tại thời điểm trước có thể vẫn đúng về lịch sử nhưng cần xem xét lại cho hiện tại. Một FAIL có ngoại lệ còn hiệu lực vẫn là FAIL về kỹ thuật; hồ sơ ngoại lệ ghi quyết định và giới hạn vận hành riêng.

Khi sửa lỗi đánh giá hoặc bổ sung kết luận, tạo phiên bản hoặc bản ghi bổ sung có quan hệ với bản cũ. Không thay âm thầm lịch sử để mọi lần chạy trông như đều đạt.

## 13. Quy trình thu thập và xem xét evidence

Có thể tổ chức theo chín bước:

1. **Lập kế hoạch:** xác định yêu cầu, tiêu chí, phạm vi, phương pháp và hợp đồng bằng chứng.
2. **Chuẩn bị:** xác nhận fixture, quyền, môi trường, công cụ và điểm quan sát.
3. **Thu thập:** ghi đủ kết quả hợp lệ, bị cấm, điều kiện biên và lỗi theo kế hoạch.
4. **Gắn ngữ cảnh:** liên kết đối tượng, phiên bản, chính sách, thời gian và người thực hiện.
5. **Bảo vệ:** định danh hiện vật, kiểm soát truy cập, lưu bản gốc và bản xử lý đúng mục đích.
6. **Đối chiếu:** ánh xạ từng tiêu chí với quan sát, kiểm tra mâu thuẫn và phần thiếu.
7. **Kết luận:** ghi kết quả, mức giới hạn và finding; không dùng quyết định để sửa dữ kiện.
8. **Quyết định:** người có thẩm quyền xác nhận hành động và điều kiện tiếp tục.
9. **Duy trì:** theo dõi thay đổi, khả năng áp dụng, lưu giữ và kiểm chứng lại.

Người tạo evidence nên cung cấp đủ căn cứ để người xem xét hiểu được kết luận. Với nội dung quan trọng, tổ chức cần chọn mức độc lập xem xét phù hợp; không mặc định một nút “approve” thay cho đánh giá chất lượng.

### Những điểm người xem xét cần xác nhận

- Tiêu chí được dùng có đúng phiên bản và đúng phạm vi không?
- Đối tượng thực tế có khớp manifest và bản triển khai cần quyết định không?
- Tiền điều kiện và kết quả kỳ vọng có nguồn độc lập đủ rõ không?
- Bằng chứng có hỗ trợ từng phần khẳng định, hay chỉ chứng minh một trường hợp dễ?
- Có dữ kiện mâu thuẫn, lần chạy thất bại hoặc đường chưa đánh giá không?
- Công cụ và môi trường có bỏ qua kiểm soát đang cần kiểm chứng không?
- Bản đã redaction còn giữ giá trị chứng minh cần thiết không?
- Điều kiện nào làm kết luận hết cơ sở và ai theo dõi?

Các câu hỏi này hướng việc xem xét vào chất lượng kết luận. Không cần thu thập thêm tài liệu chỉ để tăng số trang khi tài liệu đó không giải quyết khoảng trống nào.

## 14. Tích hợp vào pipeline và hồ sơ phát hành

Pipeline có thể tự tạo run ID, ghi revision, nhận định danh artifact, thu kết quả test và xây chỉ mục evidence. Tuy nhiên, các điều kiện đánh giá phải được thiết kế từ yêu cầu; tự động hóa không tự xác định được một phạm vi còn thiếu.

Ví dụ luồng xử lý minh họa:

~~~text
Khi một lần verification hoàn tất:

1. Xác nhận định danh yêu cầu, bộ tiêu chí và đối tượng.
2. Lưu quan sát cùng kết quả của từng ca, kể cả ca lỗi hoặc bị bỏ qua.
3. Kiểm tra hiện vật được tham chiếu có tồn tại và khớp phiên bản.
4. Ánh xạ từng tiêu chí bắt buộc tới evidence tương ứng.
5. Giữ trạng thái chưa đánh giá nếu không đủ evidence.
6. Xuất bản tóm tắt có liên kết an toàn tới gói được bảo vệ.
7. Chuyển kết luận và finding tới quy trình quyết định đã thống nhất.
~~~

Đây là mô tả quy trình, không phải một công cụ hoặc schema phải cài đặt.

NIST có ví dụ triển khai SSDF đề cập việc ghi nhận phê duyệt, từ chối và yêu cầu ngoại lệ của các kiểm tra bảo mật trong hệ thống workflow. Có thể dùng cách tiếp cận đó để giữ dấu vết quyết định cùng dữ kiện kiểm chứng. [Nguồn: NIST NCCoE — SSDF Analysis, PO.4.2](https://pages.nist.gov/nccoe-devsecops/appendix-c.html).

### Đo độ bao phủ bằng chứng

Giả sử có 10 tiêu chí trong danh sách: 6 PASS, 1 FAIL, 2 chưa đánh giá và 1 được xác nhận không áp dụng. Khi mẫu số là 9 tiêu chí áp dụng:

- Độ bao phủ đã đánh giá: 7/9, khoảng 77,8%.
- Tỷ lệ đáp ứng đã được chứng minh: 6/9, khoảng 66,7%.
- Có 1 FAIL và 2 tiêu chí chưa đủ căn cứ; phải thể hiện rõ.

Tỷ lệ PASS trong nhóm đã đánh giá là 6/7, khoảng 85,7%, nhưng không đại diện cho toàn bộ 9 tiêu chí áp dụng. Một tiêu chí quan trọng FAIL cũng không được che bằng số lượng lớn tiêu chí ít rủi ro đã PASS.

Mẫu số cần dựa vào phạm vi yêu cầu có quản lý, không chỉ những ca đã chạy. Một tiêu chí có nhiều ca không được đếm thành nhiều yêu cầu đã chứng minh nếu các điều kiện bắt buộc khác còn thiếu.

### Hồ sơ phát hành

Bản tóm tắt phục vụ quyết định nên ghi: bản triển khai, phạm vi yêu cầu, các kết quả, phần chưa đánh giá, finding còn mở, ngoại lệ liên quan, giới hạn áp dụng và người quyết định.

Không cần chép toàn bộ log vào hồ sơ này. Cần liên kết ổn định, quyền truy cập phù hợp và khả năng tìm đúng evidence hỗ trợ từng kết luận.

## 15. Những lỗi thường gặp

| Lỗi | Rủi ro kết luận | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ lưu ảnh dashboard xanh | Không biết tiêu chí, bản triển khai hoặc phần thiếu | Giữ chỉ mục, kết quả chi tiết và phạm vi |
| Chỉ ghi commit | Artifact hoặc cấu hình thực tế có thể khác | Liên kết nguồn, artifact, triển khai và policy hiệu lực |
| Lưu đường dẫn tới báo cáo thay đổi liên tục | Không tái hiện được dữ kiện đã dùng | Lưu phiên bản hoặc snapshot có định danh |
| Chỉ giữ lần chạy PASS cuối | Che mất lỗi lặp lại hoặc kết quả không ổn định | Giữ quan hệ các lần chạy và lý do kiểm chứng lại |
| Dùng một chữ ký thay cho đánh giá | Nội dung sai vẫn có thể được ký | Kiểm tra cả nguồn tin cậy và giá trị chứng minh |
| Coi digest là bằng chứng nguồn gốc đầy đủ | Không biết ai tạo hoặc ai thay file và digest | Bảo vệ manifest, quyền phát hành và dấu vết thay đổi |
| Chỉ dùng báo cáo scanner | Bỏ sót logic nghiệp vụ và ranh giới kiến trúc | Kết hợp phương pháp theo tiêu chí |
| Che hết ngữ cảnh trong bản redaction | Người xem không thể đối chiếu chủ thể và dữ liệu | Giữ quan hệ cần chứng minh bằng mã an toàn |
| Đánh dấu phần chưa chạy là PASS | Báo cáo an toàn giả | Tách kết quả chưa đánh giá và điều kiện áp dụng |
| Dùng evidence cũ chỉ vì chưa hết số ngày quy định | Bỏ qua thay đổi ảnh hưởng kết luận | Phân tích tác động và kiểm tra phiên bản |
| Có ngoại lệ nên đổi FAIL thành PASS | Mất sự thật kỹ thuật và cơ sở quản trị | Giữ evidence, kết quả và quyết định riêng |
| Lưu token vào trace chia sẻ rộng | Gói evidence trở thành nguồn truy cập trái phép | Giảm dữ liệu và giới hạn quyền theo mục đích |

## 16. Thực hành xây dựng một gói evidence

Với chức năng xuất hóa đơn, chọn một yêu cầu phân quyền và một yêu cầu audit. Xác định tiêu chí chấp nhận, fixture, các đường truy cập, bản triển khai và điều kiện đo.

Thiết kế manifest, ánh xạ từng tiêu chí tới nguồn evidence, phân biệt dữ liệu gốc với bản chia sẻ và ghi rõ kết luận có thể đưa ra. Sau đó xét ba thay đổi: mở thêm đường tải file, đổi policy tại gateway và phát hiện một assertion cũ bị sai.

Gói evidence cần chỉ ra được phần kết luận nào bị ảnh hưởng, bằng chứng nào vẫn có giá trị lịch sử, phần nào phải thu thập lại và ai quyết định hành động tiếp theo.

Evidence của verification có giá trị khi người khác có thể kiểm tra vì sao một kết luận được đưa ra, trên đối tượng nào và trong giới hạn nào. Một hồ sơ tốt giữ rõ yêu cầu, dữ kiện, lập luận và trách nhiệm, đồng thời bảo vệ chính thông tin được dùng để chứng minh bảo mật.
