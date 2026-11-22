# Chọn phạm vi chạy lại mà vẫn giữ bằng chứng kiểm tra hợp lệ

Một pipeline CI/CD có thể chạy qua nhiều bước: checkout mã nguồn, cài dependency, build artifact, chạy unit test, integration test, kiểm tra bảo mật, publish và deploy. Nếu một job thất bại do runner mất kết nối hoặc dịch vụ bên ngoài tạm thời không khả dụng, nhóm thường muốn chạy lại để hoàn tất pipeline.

Nhưng chạy lại toàn bộ pipeline không phải lúc nào cũng cần thiết hoặc an toàn. Nó có thể build một artifact mới, chạy lại các tác dụng phụ, tạo release trùng, triển khai lại một phiên bản đã hoạt động hoặc làm mất ngữ cảnh của các kiểm tra đã thành công. Ngược lại, chỉ chạy lại đúng một job cũng có thể không đủ nếu mã nguồn, dependency, cấu hình hoặc môi trường đã thay đổi kể từ lần kiểm tra trước.

Câu hỏi quan trọng không chỉ là "job nào bị lỗi?" mà còn là: **bằng chứng kiểm tra nào vẫn còn hợp lệ đối với đúng commit và artifact đang được xem xét?**

Bài viết trình bày cách chọn phạm vi rerun trong CI/CD, phân biệt retry tự động với rerun có chủ đích, xác định điều kiện để tái sử dụng kết quả đã đạt, xử lý test flaky và lỗi hạ tầng, đồng thời tránh lặp các tác dụng phụ ở publish/deploy. Mục tiêu là khôi phục pipeline với lượng công việc vừa đủ mà vẫn giữ được chuỗi bằng chứng có thể truy vết.

## 1. Rerun là một quyết định về phạm vi và bằng chứng

Một pipeline thường có đồ thị phụ thuộc. Ví dụ:

~~~text
                 Source commit
                      |
                      v
                    Build
                      |
             +--------+--------+
             |                 |
             v                 v
          Unit test       Static analysis
             |                 |
             +--------+--------+
                      |
                      v
                Integration test
                      |
                      v
                 Package artifact
                      |
                      v
                Security / scan
                      |
                      v
                   Publish
                      |
                      v
                    Deploy
                      |
                      v
                Post-deploy verify
~~~

Khi một bước thất bại, các bước trước đó có thể vẫn hợp lệ. Nếu integration test lỗi do database test tạm ngừng, không nhất thiết phải build lại source và chạy lại static analysis. Nhưng nếu commit đã thay đổi, kết quả unit test và static analysis của commit cũ không chứng minh commit mới đúng.

Rerun vì vậy phải xem xét hai yếu tố:

1. **Phạm vi thực thi:** step, job, stage, workflow hoặc toàn pipeline nào cần chạy lại?
2. **Phạm vi bằng chứng:** kết quả build, test, scan và artifact nào vẫn chứng minh được thuộc tính của source/artifact hiện tại?

Không nên chọn phạm vi chỉ theo nút bấm mà nền tảng CI cung cấp. Hãy chọn theo quan hệ phụ thuộc và tính hợp lệ của bằng chứng.

## 2. Phân biệt retry tự động, rerun và resume

Các khái niệm này thường bị gọi chung là "chạy lại", nhưng mục đích khác nhau.

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Retry | Thử lại một thao tác sau lỗi được xem là tạm thời | Gọi registry lại khi gặp HTTP 503 |
| Rerun | Khởi chạy lại một phạm vi job hoặc pipeline đã kết thúc | Chạy lại integration-test của cùng commit |
| Resume | Tiếp tục một tiến trình dài từ trạng thái/checkpoint đã lưu | Tiếp tục backfill từ batch cuối đã commit |
| Rebuild | Tạo artifact mới từ source và đầu vào build | Build lại sau khi cập nhật dependency |
| Re-deploy | Thực hiện lại thao tác triển khai tới môi trường | Tiếp tục rollout cùng image digest |
| Revert/rollback | Đưa hệ thống về phiên bản hoặc trạng thái trước | Chuyển traffic về artifact trước |

Retry thường diễn ra bên trong một job. Rerun có thể tạo một attempt mới cho job hoặc workflow. Resume sử dụng tiến độ đã lưu. Rebuild tạo đầu ra mới và do đó cần bộ bằng chứng mới. Re-deploy có thể tạo side effect nên phải có cơ chế idempotency hoặc tra cứu trạng thái.

Đặt đúng tên giúp người vận hành biết hành động nào sẽ xảy ra và những bằng chứng nào có thể được giữ lại.

## 3. Những phạm vi có thể chạy lại

### Step hoặc command

Chạy lại một command trong cùng job có thể hữu ích khi runner vẫn sống và thao tác trước đó chắc chắn chưa tạo side effect. Ví dụ tải lại metadata hoặc chạy lại một lệnh kiểm tra thuần túy.

Rủi ro là shell state, file tạm, process nền hoặc dữ liệu đã thay đổi trong workspace có thể khiến lần chạy sau không còn giống lần đầu. Chỉ retry step nếu trạng thái workspace và tác dụng phụ đã được hiểu rõ.

### Job

Job là phạm vi phổ biến để rerun. Ví dụ chạy lại integration-test trong khi giữ kết quả build và unit-test trước đó.

Cách này phù hợp nếu:

- Source commit vẫn là cùng một SHA.
- Artifact đầu vào có digest giống lần chạy trước.
- Dependency và toolchain không thay đổi.
- Job không phụ thuộc vào trạng thái tạm đã bị mất.
- Kết quả của job khác vẫn còn được nền tảng lưu và gắn với đúng run/commit.
- Không có thay đổi môi trường làm mất ý nghĩa của kết quả cũ.

### Stage

Stage gồm nhiều job cùng một giai đoạn. Rerun stage có thể cần thiết khi nhiều job phụ thuộc vào một dịch vụ dùng chung hoặc artifact của stage trước đã hết hạn.

Tuy nhiên, cần xác định job nào có side effect và job nào chỉ kiểm tra. Chạy lại cả stage có thể publish hoặc ghi dữ liệu nhiều lần nếu stage trộn các nhiệm vụ khác nhau.

### Workflow hoặc pipeline

Chạy lại toàn workflow/pipeline có thể hợp lý khi:

- Runner hoặc workspace của nhiều job bị lỗi.
- Artifact trung gian không còn hoặc đã hết hạn.
- Cấu hình pipeline thay đổi.
- Các job phụ thuộc không thể tái sử dụng kết quả cũ.
- Muốn xác minh toàn bộ luồng trên cùng một revision mới.

Đây thường là phạm vi tốn kém nhất và có thể lặp lại các tác dụng phụ. Trước khi chọn, cần biết pipeline có build artifact mới, publish package, tạo release hoặc deploy hay không.

### Deployment operation

Một thao tác triển khai nên được quản lý theo operation ID hoặc release identity. Nếu job deploy bị timeout, lần chạy tiếp theo nên tra cứu trạng thái deployment cũ và tiếp tục/đối soát cùng operation thay vì tạo một deployment mới không liên quan.

## 4. Bằng chứng kiểm tra gồm những gì?

Một dấu tick xanh đơn lẻ không đủ để chứng minh một commit hoặc artifact đã được xác minh. Bằng chứng nên được gắn với những đầu vào cụ thể.

| Bằng chứng | Định danh cần lưu | Thuộc tính được chứng minh |
|---|---|---|
| Build | Commit SHA, build inputs, toolchain, artifact digest | Artifact được tạo từ đầu vào xác định |
| Unit test | Commit SHA, test suite/version, test report | Các test đã chạy đạt trên source cụ thể |
| Integration test | Commit/artifact digest, service version, environment/config revision | Các thành phần tương tác đạt trong môi trường xác định |
| Static analysis | Commit SHA, rule set, analyzer version | Source đáp ứng bộ quy tắc phân tích cụ thể |
| Dependency scan | Lockfile hash, database/rule version, scanner version | Dependency được kiểm tra theo dữ liệu scanner cụ thể |
| Container scan | Image digest, scanner version, policy version | Image cụ thể đạt chính sách scan |
| Publish | Artifact digest, registry/repository, signature/provenance | Artifact được phát hành có danh tính xác định |
| Deploy | Artifact digest, environment, deployment operation ID | Phiên bản cụ thể được triển khai tới môi trường |
| Post-deploy verification | Deployment ID, thời gian, environment, test/check version | Trạng thái sau triển khai đã được xác minh |

Bằng chứng cần đủ metadata để trả lời: kiểm tra cái gì, trên phiên bản nào, bằng công cụ và chính sách nào, ở môi trường nào, vào thời điểm nào và kết quả ra sao?

## 5. Khi nào kết quả đã đạt còn hợp lệ?

Một kết quả kiểm tra có thể được tái sử dụng nếu đầu vào mà kết quả đó phụ thuộc vẫn giống nhau và chính sách cho phép reuse.

### Source commit không đổi

Unit test chạy trên commit A không tự chứng minh commit B đạt, dù B chỉ sửa một dòng. Commit SHA là định danh chính xác của source tree. Nếu source thay đổi, ít nhất các kiểm tra phụ thuộc source cần chạy lại hoặc có cơ chế phân tích tác động được chấp nhận rõ ràng.

Không dùng trạng thái xanh của commit trước để đáp ứng required check cho commit mới.

### Artifact digest không đổi

Nếu integration test và security scan đã chạy trên image digest D, có thể tái sử dụng bằng chứng đó khi triển khai đúng digest D, miễn là môi trường và chính sách liên quan không thay đổi.

Nếu build lại tạo digest D2, dù tag vẫn là latest hoặc version text giống nhau, không được tự động gán kết quả scan của D cho D2. Tag có thể di chuyển; digest mới là định danh nội dung bất biến phù hợp hơn.

### Dependency và toolchain không đổi

Thay đổi lockfile, build plugin, JDK, compiler flags hoặc base image có thể làm thay đổi artifact. Khi đó, build và các test phụ thuộc cần được xem xét lại.

Ngay cả khi source SHA không đổi, đầu vào build khác có thể tạo ra artifact khác. Cần ghi nhận dependency lock hash, toolchain version và build configuration.

### Cấu hình và môi trường không đổi

Integration test phụ thuộc database version, service contract, feature flags, network policy và config revision. Nếu các yếu tố này thay đổi, kết quả cũ có thể không còn đại diện cho môi trường hiện tại.

Ví dụ test đạt trên PostgreSQL 15 không tự động chứng minh tương thích với PostgreSQL 17. Kết quả staging trước khi rotate credential hoặc thay đổi schema cũng không nhất thiết còn đủ cho lần triển khai sau.

### Policy và dữ liệu scanner không đổi

Security scan có thể phụ thuộc phiên bản rule database, vulnerability feed và policy threshold. Một image đã scan tuần trước có thể cần scan lại nếu vulnerability database có bản cập nhật quan trọng hoặc chính sách yêu cầu scan gần thời điểm release.

Tính hợp lệ của bằng chứng vì thế có thể có thời hạn.

## 6. Ma trận quyết định chọn phạm vi rerun

| Nguyên nhân hoặc thay đổi | Phạm vi thường phù hợp | Bằng chứng có thể giữ lại |
|---|---|---|
| Runner mất mạng khi tải dependency, chưa có build output | Retry step hoặc job build | Kết quả độc lập của job khác nếu cùng commit |
| Integration service test tạm ngừng | Rerun integration-test | Build, unit test và static analysis nếu đầu vào không đổi |
| Unit test thất bại do lỗi code | Sửa source, tạo commit mới và chạy lại checks phụ thuộc source | Không dùng test pass của commit cũ cho commit mới |
| Scanner service tạm lỗi, artifact digest không đổi | Rerun job scan | Build và test trên cùng digest |
| Lockfile hoặc toolchain thay đổi | Build lại và chạy lại checks phụ thuộc | Các kiểm tra không phụ thuộc đầu vào thay đổi, nếu policy cho phép |
| Artifact hết hạn hoặc bị xóa | Build/package lại, kiểm tra lại artifact | Test source có thể giữ nếu source và đầu vào không đổi; artifact evidence phải gắn digest mới |
| Deploy job timeout sau khi gửi yêu cầu | Tra cứu operation và resume/reconcile | Build, scan và approval còn hiệu lực nếu đúng digest |
| Môi trường staging thay đổi | Rerun các integration/post-deploy checks liên quan | Unit test trên source có thể giữ |
| Pipeline YAML thay đổi | Chạy lại các job chịu ảnh hưởng bởi logic workflow; có thể cần full pipeline | Chỉ giữ bằng chứng độc lập với phần logic thay đổi |
| Commit mới được push | Chạy checks cho commit mới | Không coi checks của SHA cũ là checks của SHA mới |
| Test flaky, lần đầu fail rồi retry pass | Điều tra và ghi nhận cả hai attempt | Không xóa lịch sử fail; trạng thái pass phải theo policy retry |
| Release publish thành công nhưng response mất | Tra cứu package theo digest/version | Không publish lần hai nếu artifact đã tồn tại đúng nội dung |

Đây là hướng dẫn chọn phạm vi, không phải quy tắc tự động cho mọi nền tảng. Đồ thị phụ thuộc thực tế và chính sách required checks quyết định job nào cần chạy lại.

## 7. Quy trình ra quyết định trước khi bấm rerun

Trước khi chạy lại, hãy trả lời lần lượt:

1. Job lỗi ở bước nào và lỗi có phải lỗi tạm thời không?
2. Source SHA có còn giống lần chạy ban đầu không?
3. Artifact đầu vào có còn tồn tại và digest có khớp không?
4. Toolchain, dependency lock và config revision có thay đổi không?
5. Job đã tạo side effect nào trước khi lỗi?
6. Job phụ thuộc vào artifact, report hoặc output nào của job trước?
7. Bằng chứng của job đã đạt có còn được nền tảng lưu và gắn đúng commit/run không?
8. Retry job có thể ghi đè hoặc nhân đôi dữ liệu không?
9. Nếu job là deploy/publish, có thể tra cứu trạng thái operation trước không?
10. Sau rerun, cần kiểm tra required checks và release record nào?

Nếu chưa xác định được thao tác đã xảy ra hay chưa, không tạo một operation mới chỉ vì job báo timeout. Hãy tra cứu trạng thái hoặc đối soát trước.

## 8. Retry tự động chỉ dành cho lỗi có khả năng hồi phục

Retry tự động giúp xử lý lỗi ngắn hạn mà không cần người vận hành can thiệp. Tuy nhiên, retry không sửa được lỗi code, test assertion sai, thiếu quyền hay cấu hình không hợp lệ.

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Transient infrastructure | Network reset, runner host unavailable | Retry có giới hạn |
| Rate limit | HTTP 429 | Tuân thủ Retry-After |
| Temporary service failure | HTTP 502/503/504 | Backoff và retry nếu thao tác an toàn |
| Resource contention | Lock busy, queue full | Chờ hoặc retry theo budget |
| Authentication/authorization | HTTP 401/403 | Dừng và sửa identity/policy |
| Validation/configuration | Sai schema, thiếu biến bắt buộc | Dừng; không retry cùng đầu vào |
| Test assertion failure | Expected và actual khác nhau | Điều tra code/test; không retry để tìm màu xanh |
| Security policy failure | Vulnerability vượt ngưỡng | Xử lý finding hoặc xin exception đúng quy trình |
| Unknown outcome | Timeout sau khi gửi side effect | Tra cứu trạng thái trước khi gửi lại |

Không nên phân loại mọi exit code khác 0 thành transient. Job cần phát ra loại lỗi hoặc mã lỗi có ý nghĩa để retry policy quyết định chính xác.

## 9. Exponential backoff, jitter và retry budget

Khi dịch vụ tạm thời không khả dụng, retry ngay lập tức có thể làm tăng tải và kéo dài sự cố.

Exponential backoff tăng thời gian chờ theo số lần thử:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait  = random(0, delay)
~~~

Jitter tạo độ ngẫu nhiên để nhiều runner không cùng retry tại một thời điểm. Ví dụ base delay 2 giây, max delay 60 giây, tối đa 4 lần retry. Các giá trị phải phù hợp SLA và hướng dẫn của hệ thống đích.

### Retry budget

Retry budget giới hạn số lần thử hoặc tổng thời gian retry cho một thao tác:

- Max attempts.
- Max elapsed time.
- Request timeout.
- Backoff cap.
- Tôn trọng Retry-After.
- Dừng ngay với lỗi terminal.
- Ghi nhận trạng thái UNKNOWN khi không thể xác định kết quả.

Nếu HTTP client retry 3 lần, SDK retry 3 lần và CI job retry 3 lần, một thao tác có thể tạo 27 request. Các tầng cần dùng chung deadline hoặc retry budget để tránh khuếch đại.

### Circuit breaker

Circuit breaker ngăn caller liên tục gọi một dependency đang lỗi. Nó thường có ba trạng thái:

- **Closed:** request được phép đi qua; bộ đếm lỗi được theo dõi.
- **Open:** khi lỗi vượt ngưỡng, request mới bị từ chối nhanh trong một khoảng thời gian.
- **Half-open:** sau thời gian chờ, chỉ cho một số request thăm dò; nếu dependency hồi phục thì đóng circuit, nếu vẫn lỗi thì mở lại.

Trong CI, circuit breaker hữu ích khi nhiều job cùng phụ thuộc vào registry, test environment hoặc dịch vụ dùng chung. Nó giúp tránh retry storm và trả lỗi rõ ràng để pipeline được thử lại sau. Circuit breaker không biến một check chưa chạy thành pass và không thay thế retry budget hoặc kiểm tra trạng thái side effect.

### Không retry test assertion để biến fail thành pass

Test assertion thất bại thường là tín hiệu về hành vi của phần mềm hoặc chất lượng test. Retry có thể hữu ích để chẩn đoán flaky test, nhưng pipeline phải giữ lại lịch sử lần fail và tuân theo chính sách riêng. Không nên biến một test fail thành pass chỉ bằng cách thử nhiều lần cho tới khi có lần xanh.

## 10. Test flaky và bằng chứng của nhiều attempt

Flaky test là test có thể cho kết quả khác nhau khi chạy lại với cùng commit và điều kiện được cho là tương đương.

Nguyên nhân thường gặp:

- Phụ thuộc thời gian hoặc timezone.
- Dữ liệu dùng chung giữa các test.
- Test chạy song song nhưng không cô lập tài nguyên.
- Network hoặc dịch vụ bên ngoài không ổn định.
- Race condition.
- Thứ tự test hoặc trạng thái còn sót.
- Timeout quá ngắn.
- Cleanup không đầy đủ.

### Lưu kết quả theo attempt

Một báo cáo tốt nên phân biệt:

| Thuộc tính | Ý nghĩa |
|---|---|
| Logical test/job ID | Định danh test hoặc job logic |
| Attempt number | Lần thực thi thứ mấy |
| Commit SHA | Source được kiểm tra |
| Environment | Môi trường chạy |
| Started/finished time | Khoảng thời gian thực thi |
| Initial result | Kết quả lần đầu |
| Retry result | Kết quả các lần retry |
| Final policy result | Kết quả theo quy tắc của pipeline |
| Failure reason | Nguyên nhân hoặc phân loại lỗi |

Nếu lần đầu fail và lần hai pass, lịch sử cần thể hiện cả hai. Có thể cho phép pipeline tiếp tục theo chính sách flaky retry, nhưng không nên ghi nhận test đó ổn định như test luôn pass.

### Quarantine có kiểm soát

Nếu test flaky nghiêm trọng làm chặn pipeline, nhóm có thể quarantine tạm thời. Mỗi test quarantine cần có owner, lý do, ticket, thời hạn và báo cáo riêng. Test bị quarantine không nên được tính như bằng chứng đã xác minh hành vi.

## 11. Giữ nguyên liên kết giữa commit, artifact và test result

Một pipeline có thể có nhiều run trên cùng branch. Nếu chỉ lưu tên branch hoặc tag, kết quả của run cũ có thể bị gắn nhầm vào source mới.

Nên gắn mỗi bằng chứng với:

- Repository và commit SHA.
- Workflow run ID và attempt.
- Artifact name cùng digest.
- Build toolchain và dependency lock hash.
- Test suite và report ID.
- Environment/config revision.
- Scanner và policy version.
- Timestamp và trạng thái kết quả.

Ví dụ manifest bằng chứng:

~~~json
{
  "repository": "acme/order-service",
  "commit": "a1b2c3d4...",
  "workflowRun": "run-4812",
  "artifact": {
    "name": "order-service",
    "digest": "sha256:..."
  },
  "checks": {
    "unitTest": "passed",
    "integrationTest": "passed",
    "dependencyScan": "passed"
  },
  "toolchain": {
    "jdk": "21",
    "gradle": "8.x"
  }
}
~~~

Đây là cấu trúc minh họa. Trong hệ thống thật, manifest cần được tạo từ nguồn đáng tin cậy, gắn chữ ký hoặc provenance theo nhu cầu và không cho job PR không tin cậy tự khai báo kết quả pass.

## 12. Artifact và cache khi chạy lại

Rerun một job có thể cần artifact từ job trước. Cần phân biệt artifact đầu ra bất biến với cache tăng tốc.

### Artifact

Artifact là đầu ra được lưu để job khác hoặc người review sử dụng, ví dụ JAR, container image, test report hoặc scan report.

Khi rerun:

- Kiểm tra artifact có thuộc đúng commit và run không.
- Xác minh digest trước khi sử dụng.
- Kiểm tra artifact còn thời hạn lưu trữ.
- Không dùng artifact PR không tin cậy cho release chỉ vì tên file trùng.
- Nếu build lại tạo digest mới, tạo bộ bằng chứng mới cho artifact đó.

Nếu artifact cũ không còn, có thể cần build lại. Khi đó, không được giả định artifact mới giống byte-for-byte nếu build không tái lập; cần ghi digest và chạy lại các kiểm tra phụ thuộc artifact.

### Cache

Cache phục vụ tốc độ, không phải bằng chứng kiểm tra. Cache có thể bị hết hạn, thay đổi hoặc không tương thích với đầu vào mới.

Nếu cache bị lỗi, có thể xóa cache trong phạm vi phù hợp và chạy lại job. Nhưng cần bảo đảm cache không chứa secret và cache từ vùng không tin cậy không được dùng làm đầu vào tin cậy.

Không dùng trạng thái cache hit như bằng chứng dependency đã được xác minh. Dependency cần lockfile, checksum hoặc cơ chế xác minh riêng.

## 13. Chọn rerun theo đồ thị phụ thuộc

Nếu job B tiêu thụ output của job A, khi A thay đổi hoặc output A được tạo lại, cần xác định B có phải chạy lại hay không.

Ví dụ:

~~~text
                 build
                   |
             artifact digest D1
                   |
          +--------+---------+
          |                  |
          v                  v
       unit test       container scan
          |                  |
          +--------+---------+
                   |
                   v
            integration test
                   |
                   v
                publish
~~~

Nếu integration-test fail do môi trường database, có thể chạy lại integration-test với artifact D1. Unit test và container scan vẫn có thể được giữ nếu đầu vào và policy của chúng không đổi.

Nếu build tạo digest D2, các kiểm tra trên D1 không tự động áp dụng cho D2. Cần chạy lại những job phụ thuộc artifact, chẳng hạn container scan và integration test.

Nếu thay đổi chỉ là policy scan, có thể chỉ cần chạy lại scanner trên digest hiện có. Không nhất thiết phải build lại source nếu scanner có thể đọc artifact cũ và policy không yêu cầu build mới.

### Phân tích tác động thay đổi

Có thể mô tả mỗi job bằng tập đầu vào:

- build phụ thuộc source, lockfile, toolchain và build config.
- unit test phụ thuộc source, test code và test runtime.
- integration test phụ thuộc artifact, service versions và environment config.
- scan phụ thuộc artifact, scanner/rule database và policy.
- deploy phụ thuộc artifact digest, environment và deployment config.

Khi một đầu vào thay đổi, chỉ những bằng chứng phụ thuộc đầu vào đó mới cần được xem xét vô hiệu hóa. Đây là cơ sở của incremental CI, nhưng cần được cấu hình và review cẩn thận để không bỏ sót dependency ẩn.

## 14. Ví dụ GitHub Actions: chạy lại job lỗi

GitHub Actions cho phép rerun failed jobs hoặc rerun toàn bộ workflow tùy thao tác người vận hành và quyền repository. Tên lựa chọn có thể thay đổi theo giao diện nền tảng.

Với pipeline có các job độc lập, có thể tổ chức như sau:

~~~yaml
name: verify

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon assemble
      - uses: actions/upload-artifact@v4
        with:
          name: application-package
          path: build/libs/*.jar

  unit-test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon test

  integration-test:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: artifacts
      - run: ./scripts/run-integration-tests.sh
~~~

Ví dụ này chỉ minh họa đồ thị job. Script integration test đọc package từ thư mục artifacts; trong triển khai thực tế cần xác minh digest của package, đồng thời khởi tạo service test theo phiên bản xác định.

Nếu integration-test lỗi do database test tạm thời không khả dụng, có thể rerun job đó nếu artifact build vẫn còn, đúng commit và chưa hết hạn. Nếu build job chạy lại tạo package khác, integration-test cần dùng artifact mới và kết quả cũ không còn gắn với artifact mới.

### Không dùng rerun như cách sửa source

Nếu unit test fail do assertion hoặc logic, cần sửa code, tạo commit mới và chạy checks cho SHA mới. Rerun cùng commit có thể hữu ích để xác định flaky test, nhưng không thay thế việc sửa lỗi.

## 15. Ví dụ GitLab CI: retry có điều kiện

GitLab CI hỗ trợ cấu hình retry cho một số loại failure. Có thể giới hạn số lần retry và các điều kiện lỗi cụ thể.

Ví dụ:

~~~yaml
integration_test:
  stage: test
  script:
    - ./gradlew --no-daemon integrationTest
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure
~~~

Cấu hình này minh họa việc retry lỗi runner hoặc timeout. Cần kiểm tra danh sách retry condition theo phiên bản GitLab đang dùng. Không nên thêm các loại lỗi do code hoặc assertion vào danh sách chỉ để pipeline xanh.

Một job có thể retry nhiều lần; báo cáo nên lưu attempt và kết quả từng lần. Nếu retry đã tạo artifact hoặc tác dụng phụ, job cần xử lý idempotency hoặc cleanup trước khi chạy lại.

### Retry không tự làm cho side effect an toàn

Nếu script trong job gửi message, tạo release hoặc ghi dữ liệu, GitLab retry job có thể thực hiện lại các tác dụng phụ đó. Cần thiết kế idempotency key, kiểm tra trạng thái hoặc tách các bước side effect sang job riêng có điều kiện.

## 16. Rerun job có tác dụng phụ: publish và deploy

Build và test thường có thể chạy lại nếu đầu vào bất biến. Publish và deploy có thể thay đổi trạng thái bên ngoài, do đó phải thận trọng hơn.

### Publish artifact

Nếu registry đã nhận package nhưng response bị mất, job có thể kết thúc lỗi dù package đã tồn tại.

Trước khi publish lại:

1. Xác định package name/version và digest.
2. Tra cứu registry.
3. Nếu package tồn tại và digest khớp, ghi nhận publish đã hoàn tất.
4. Nếu package tồn tại nhưng digest khác, dừng và xử lý conflict.
5. Nếu chưa tồn tại, publish theo policy.
6. Ghi lại registry location và digest.

Không ghi đè một version bất biến bằng nội dung khác chỉ vì rerun.

### Deploy

Nếu deploy job timeout sau khi gửi yêu cầu, cần tra cứu deployment operation hoặc trạng thái workload. Nếu đúng artifact digest đã chạy, tiếp tục verify. Nếu rollout đang diễn ra, tiếp tục theo dõi. Nếu chưa được tiếp nhận và thao tác có idempotency, gửi lại cùng operation identity.

Không tạo deployment mới hoặc chạy migration lần nữa chỉ vì job CI không nhận được response.

### Tách job kiểm tra và job side effect

Job test/scan nên không có quyền publish/deploy. Job publish/deploy chỉ chạy khi bằng chứng bắt buộc đã đạt và dùng artifact digest đã được phê duyệt. Tách quyền giúp rerun kiểm tra không vô tình lặp tác dụng phụ release.

## 17. Approval và required checks khi rerun

Một release có thể cần approval của reviewer, security hoặc owner môi trường. Rerun cần giữ liên kết giữa approval và đối tượng đã được phê duyệt.

Approval nên ràng buộc với:

- Commit SHA.
- Artifact digest.
- Environment đích.
- Release version.
- Thay đổi cấu hình liên quan.
- Thời điểm và người phê duyệt.

Nếu artifact digest thay đổi sau approval, cần xác định chính sách có yêu cầu phê duyệt lại không. Không nên dùng approval của artifact cũ cho artifact mới chỉ vì tên version giống nhau.

### Required checks

Required check phải phản ánh đúng commit được merge. Nếu commit mới được push, trạng thái của commit trước không thay thế required checks của commit mới.

Khi rerun một job, kiểm tra rằng kết quả cuối được gắn với đúng check context và SHA. Không dùng job tùy chọn hoặc trạng thái skipped để thay thế job bắt buộc.

### Manual rerun có audit

Rerun thủ công nên ghi người yêu cầu, lý do, phạm vi, commit/artifact và attempt. Điều này giúp phân biệt retry tự động với hành động vận hành và hỗ trợ điều tra khi có sự cố.

## 18. Chính sách hết hạn của bằng chứng

Không phải bằng chứng nào cũng có hiệu lực vô thời hạn.

Ví dụ:

- Dependency scan cần chạy lại khi vulnerability database cập nhật hoặc policy yêu cầu.
- Integration test cần chạy lại nếu environment hoặc dependency service thay đổi.
- Approval production có thể hết hạn sau một khoảng thời gian.
- Artifact có thể bị xóa theo retention policy.
- Chứng thư hoặc chữ ký có thể hết hạn hoặc bị thu hồi.
- Kết quả performance test có thể không còn đại diện sau khi cấu hình hạ tầng đổi.

Mỗi loại bằng chứng nên có freshness policy:

| Bằng chứng | Điều kiện hết hiệu lực thường gặp |
|---|---|
| Unit test | Source/test inputs thay đổi |
| Build | Source, dependency, toolchain hoặc build config thay đổi |
| Integration test | Artifact, service version hoặc environment thay đổi |
| Security scan | Artifact hoặc scanner/policy data thay đổi theo chính sách |
| Approval | Artifact, environment, scope hoặc thời hạn approval thay đổi |
| Post-deploy verification | Deployment mới hoặc runtime state thay đổi |
| Performance test | Workload, topology hoặc capacity thay đổi đáng kể |

Freshness policy cần được định nghĩa bởi nhóm sở hữu chất lượng/bảo mật, không nên tự đặt một thời hạn chung cho mọi loại bằng chứng.

## 19. Lưu lịch sử rerun và audit trail

Một pipeline có thể có nhiều attempt cho cùng một commit. Cần lưu lịch sử để biết lần nào fail, lần nào pass và vì sao.

Thông tin nên có:

- Pipeline/workflow run ID.
- Job ID và attempt number.
- Commit SHA.
- Artifact digest.
- Trigger source: push, pull request, schedule, manual rerun.
- Người yêu cầu rerun nếu có.
- Failure classification.
- Retry policy và số lần thử.
- Thời gian từng attempt.
- Environment/config revision.
- Artifact/report được tái sử dụng.
- Kết quả cuối cùng và lý do chấp nhận.

Không xóa log của attempt thất bại khi attempt sau thành công. Lịch sử fail rồi pass có thể cho thấy flaky test, lỗi hạ tầng hoặc chất lượng môi trường.

### Dashboard hữu ích

Có thể theo dõi:

- Tỷ lệ pipeline thành công ngay lần đầu.
- Tỷ lệ job cần retry.
- Tỷ lệ retry thành công.
- Tỷ lệ flaky test.
- Số rerun thủ công theo repository/team.
- Thời gian pipeline sau rerun.
- Số lần publish/deploy bị gọi trùng.
- Số bằng chứng hết hạn trước khi release.
- Số pipeline pass nhưng có job skipped hoặc quarantined.

Các metric này giúp tìm nguyên nhân gốc thay vì coi rerun là hoạt động bình thường không cần điều tra.

## 20. Quy trình vận hành khi pipeline thất bại

Một runbook đơn giản:

1. Mở run và xác định job đầu tiên thất bại, không chỉ job cuối bị cancelled.
2. Đọc log và phân loại lỗi: transient, code/test, config, permission, policy hoặc unknown outcome.
3. Xác nhận commit SHA và artifact digest.
4. Kiểm tra các job đã đạt có còn cùng đầu vào và còn trong retention.
5. Kiểm tra dependency của job lỗi và artifact cần để rerun.
6. Xác định job có side effect hay không.
7. Nếu là lỗi transient, retry job trong retry budget.
8. Nếu là lỗi code/test, sửa source và tạo commit mới.
9. Nếu đầu vào build thay đổi, rebuild và chạy lại các checks phụ thuộc.
10. Nếu deploy/publish có kết quả chưa rõ, tra cứu operation/registry trước khi gửi lại.
11. Xác nhận required checks, approvals và provenance gắn đúng commit/artifact.
12. Ghi lý do rerun và kết quả cuối vào audit trail.

Nếu không thể chứng minh bằng chứng cũ còn hợp lệ, hãy chạy lại kiểm tra cần thiết. Nếu chưa rõ side effect đã xảy ra hay chưa, đối soát trước khi tạo thao tác mới.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Rerun toàn pipeline cho mọi lỗi | Tốn thời gian và lặp side effect | Chọn phạm vi theo dependency graph |
| Giữ kết quả xanh của commit cũ cho commit mới | Bằng chứng không áp dụng cho source hiện tại | Gắn check với commit SHA |
| Dùng tag mutable thay digest | Có thể kiểm tra một image nhưng deploy image khác | Gắn bằng chứng với immutable digest |
| Retry test assertion tới khi pass | Che giấu lỗi hoặc flaky test | Lưu mọi attempt và phân loại |
| Coi cache hit là bằng chứng build/test | Cache không chứng minh tính đúng đắn | Dùng report và provenance có định danh |
| Rerun publish khi không biết registry đã nhận chưa | Tạo package/version trùng hoặc conflict | Tra cứu theo version và digest |
| Rerun deploy sau timeout mà không reconcile | Tạo deployment chồng lấn | Tra cứu operation và observed state |
| Dùng approval cũ cho artifact mới | Release mới chưa được phê duyệt | Ràng buộc approval với digest |
| Bỏ qua job skipped/allowed failure | Pipeline xanh nhưng thiếu kiểm tra bắt buộc | Review trạng thái và policy |
| Xóa lịch sử attempt thất bại | Mất dấu flaky và lỗi hạ tầng | Giữ audit trail đầy đủ |
| Rerun job không có dependency artifact | Job chạy với file thiếu hoặc sai run | Xác minh artifact lineage và retention |
| Retry vô hạn | Kéo dài sự cố và tăng tải | Retry budget, deadline và circuit breaker |

## 22. Checklist chọn phạm vi chạy lại

### Xác định đầu vào

- [ ] Commit SHA của lần chạy có còn là revision cần phát hành?
- [ ] Artifact digest có được xác định và còn tồn tại?
- [ ] Lockfile, toolchain, build config có thay đổi?
- [ ] Environment/config revision có thay đổi?
- [ ] Scanner/policy data có còn trong freshness window?

### Chọn phạm vi

- [ ] Lỗi có được phân loại là transient không?
- [ ] Có thể retry một step/job độc lập không?
- [ ] Các job phụ thuộc có cần chạy lại không?
- [ ] Artifact đầu vào có thể tái sử dụng an toàn không?
- [ ] Rerun stage/workflow có lặp publish, deploy hoặc migration không?
- [ ] Có cần rebuild thay vì rerun không?

### Giữ bằng chứng hợp lệ

- [ ] Test report gắn với đúng commit SHA.
- [ ] Scan report gắn với đúng artifact digest và policy version.
- [ ] Integration result gắn với environment/service version.
- [ ] Required checks phản ánh đúng commit được merge.
- [ ] Approval gắn với artifact và environment được triển khai.
- [ ] Các job skipped/quarantined được thể hiện rõ.
- [ ] Lịch sử các attempt được lưu.

### Kiểm soát side effect

- [ ] Publish có kiểm tra package/version/digest trước khi lặp.
- [ ] Deploy có operation ID hoặc cơ chế reconcile.
- [ ] Migration và data job có idempotency/checkpoint phù hợp.
- [ ] Retry có giới hạn và backoff.
- [ ] Có audit người yêu cầu và lý do rerun.

## Kết luận

Chạy lại pipeline là quyết định về phạm vi thực thi và tính hợp lệ của bằng chứng. Hãy gắn build, test, scan, approval và deploy với commit SHA, artifact digest, toolchain, policy và environment tương ứng. Khi lỗi chỉ mang tính tạm thời, rerun đúng job thường giữ được các kết quả độc lập đã đạt; khi source hoặc đầu vào build thay đổi, cần chạy lại những kiểm tra phụ thuộc; khi publish hoặc deploy có kết quả chưa rõ, phải tra cứu trạng thái trước khi lặp tác dụng phụ. Giữ lịch sử mọi attempt và chỉ cho release đi tiếp khi required checks, approval và provenance còn hợp lệ với đúng artifact được phát hành.

