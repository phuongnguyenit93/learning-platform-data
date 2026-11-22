# Phân biệt chạy song song công việc với chạy đồng thời nhiều pipeline

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt chạy song song các job trong cùng một pipeline với nhiều lần chạy pipeline chồng lấn thời gian.
- Giải thích quan hệ giữa concurrency, parallelism, dependency graph và năng lực runner.
- Thiết kế DAG để thực hiện độc lập các bước có thể chạy song song, đồng thời giữ đúng thứ tự ở các bước phụ thuộc.
- Nhận diện race condition khi nhiều pipeline cùng truy cập môi trường, database, registry, cache hoặc hạ tầng.
- Chọn giữa isolation, queue, concurrency group, distributed lock và optimistic concurrency control.
- Thiết kế cancellation, retry và idempotency để tránh triển khai sai thứ tự hoặc thực hiện lặp side effect.
- Đặt giới hạn đồng thời theo tài nguyên, môi trường và mức độ rủi ro.
- Quan sát, kiểm thử và truy vết hành vi điều phối trong CI/CD.

## 1. Hai vấn đề thường bị gọi chung là chạy song song

CI/CD có thể thực hiện nhiều công việc cùng lúc theo hai cách khác nhau.

**Chạy song song công việc trong một pipeline (intra-pipeline parallelism)** là việc chia một lần chạy pipeline thành các job hoặc task độc lập, sau đó thực thi chúng đồng thời khi dependency đã sẵn sàng.

Ví dụ, cùng một commit có thể chạy unit test, lint, kiểm tra dependency và build trên các runner khác nhau. Các job này cùng thuộc một pipeline run và thường dùng chung một release context.

**Chạy đồng thời nhiều pipeline (inter-pipeline concurrency)** là khi nhiều lần chạy pipeline khác nhau có thời gian thực thi chồng lấn. Chúng có thể đến từ nhiều commit, pull request, branch, repository, lịch chạy hoặc thao tác thủ công.

Ví dụ:

- Pipeline của commit A đang chạy integration test.
- Developer push commit B và pipeline mới bắt đầu.
- Một pipeline theo lịch chạy nightly cũng đang build.
- Release pipeline của branch main đang chuẩn bị deploy staging.

Đây là các pipeline run độc lập. Chúng có thể dùng chung runner pool, registry, database kiểm thử, môi trường staging hoặc tài khoản cloud.

Hai khái niệm có liên quan nhưng không đồng nghĩa:

| Khía cạnh | Song song trong một pipeline | Đồng thời nhiều pipeline |
|---|---|---|
| Phạm vi | Các job/task của cùng một lần chạy | Nhiều lần chạy độc lập |
| Mục tiêu chính | Giảm thời gian hoàn tất một pipeline | Tăng throughput và tiếp nhận nhiều sự kiện |
| Dependency | Thường được mô tả bằng DAG | Có thể không biết nhau nếu không có cơ chế điều phối |
| Dữ liệu | Có thể chia sẻ artifact/context của cùng run | Có thể tranh chấp tài nguyên dùng chung |
| Điều phối | Job dependency, matrix, runner scheduler | Queue, concurrency group, lock, quota |
| Rủi ro nổi bật | Job chạy khi đầu vào chưa sẵn sàng | Race condition, ghi đè, deploy sai thứ tự |
| Cách kiểm soát | DAG và giới hạn fan-out | Isolation và coordination trên tài nguyên chung |

Một hệ thống CI/CD tốt cần xử lý cả hai. Tăng số job chạy song song trong một pipeline không giải quyết được xung đột giữa hai pipeline run. Ngược lại, tuần tự hóa mọi pipeline không tận dụng được các job độc lập bên trong từng lần chạy.

## 2. Phân biệt concurrency và parallelism

Hai thuật ngữ này thường được dùng thay thế trong hội thoại, nhưng có ý nghĩa kỹ thuật khác nhau.

- **Concurrency (đồng thời):** nhiều công việc có vòng đời chồng lấn. Hệ thống có thể luân phiên thực hiện chúng hoặc thực thi chúng trên nhiều worker.
- **Parallelism (song song):** nhiều công việc thực sự được thực thi cùng một thời điểm, thường trên nhiều CPU core, process, máy hoặc runner.

Ví dụ một runner chỉ có một CPU core vẫn có thể điều phối nhiều process đồng thời bằng cách chuyển đổi giữa chúng. Nhưng tại một thời điểm, CPU có thể chỉ thực thi một luồng lệnh. Nếu hai job chạy trên hai runner riêng biệt, chúng có thể thực sự chạy song song.

Trong CI/CD, người dùng thường quan tâm thời gian hoàn tất và số lượng lần chạy đang hoạt động hơn là cách scheduler phân bổ CPU. Tuy nhiên, phân biệt hai khái niệm giúp hiểu vì sao:

- Có nhiều pipeline run đang ở trạng thái running nhưng một số vẫn đang chờ runner.
- Có nhiều job được khai báo song song nhưng chỉ một số được thực thi vì giới hạn concurrency.
- Tăng số runner không làm một bước migration đơn lẻ chạy nhanh hơn.
- Một pipeline có thể chạy nhiều job song song nhưng vẫn phải chờ bước cuối phụ thuộc vào tất cả kết quả.

Concurrency mô tả sự chồng lấn của công việc; parallelism mô tả việc thực thi đồng thời thực sự. Cả hai đều cần scheduler, tài nguyên và quy tắc điều phối phù hợp.

## 3. Chạy song song trong một pipeline bằng dependency graph

Một pipeline thường được mô hình hóa thành Directed Acyclic Graph (DAG), tức đồ thị có hướng không có chu trình. Mỗi node là một job hoặc task; mỗi cạnh thể hiện dependency.

Ví dụ sau có ba job kiểm tra độc lập. Job package chỉ chạy sau khi cả ba kiểm tra đạt:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Lint"]
    A --> C["Unit tests"]
    A --> D["Dependency scan"]
    B --> E["Package artifact"]
    C --> E
    D --> E
    E --> F["Publish artifact"]
~~~

Nếu các job B, C và D không phụ thuộc lẫn nhau, scheduler có thể chạy chúng đồng thời. Khi tất cả đạt, job E mới được bắt đầu.

Không nên tạo dependency chỉ để workflow nhìn có vẻ tuần tự. Ví dụ, bắt unit test chờ lint hoàn tất sẽ kéo dài thời gian nếu hai bước không dùng đầu ra của nhau.

Ngược lại, không được bỏ dependency thật. Nếu integration test cần service đã được deploy vào môi trường test, nó phải chờ job tạo môi trường và deploy hoàn tất.

Một quy tắc đơn giản:

- Chỉ tạo cạnh dependency khi có quan hệ dữ liệu, trạng thái hoặc điều kiện thực sự.
- Nếu job cần artifact từ job khác, truyền artifact qua cơ chế lưu trữ của pipeline thay vì giả định workspace được chia sẻ.
- Các job độc lập có thể chạy song song nhưng cần có đầu ra và trạng thái riêng.
- Job tổng hợp chỉ tiếp tục khi tất cả dependency bắt buộc đạt.

## 4. Thời gian pipeline và critical path

Chạy song song giúp giảm thời gian tổng thể, nhưng thời gian không đơn giản bằng tổng thời lượng các job chia cho số runner.

Với DAG, thời gian lý tưởng bị giới hạn bởi đường dài nhất từ đầu đến cuối, gọi là critical path. Thời gian thực tế còn cộng thêm thời gian chờ runner, khởi tạo môi trường, tải dependency, truyền artifact và các giới hạn tài nguyên.

Ví dụ:

| Job | Thời lượng giả định | Dependency |
|---|---:|---|
| Checkout | 1 phút | Không |
| Lint | 2 phút | Checkout |
| Unit test | 6 phút | Checkout |
| Dependency scan | 4 phút | Checkout |
| Package | 3 phút | Lint, unit test, scan |
| Publish | 1 phút | Package |

Nếu chạy tuần tự, tổng thời gian khoảng 17 phút. Nếu ba job lint, unit test và scan chạy song song, thời gian lý tưởng khoảng 11 phút: checkout 1 + nhóm kiểm tra 6 + package 3 + publish 1.

Thực tế có thể lâu hơn nếu:

- Chỉ có một runner rảnh.
- Các job phải tải cùng dependency nhiều lần.
- Runner bị giới hạn CPU hoặc memory.
- Registry hoặc package repository bị nghẽn.
- Job dài nhất có thời gian biến động lớn.
- Matrix test tạo quá nhiều job cùng lúc.

Tối ưu pipeline nên bắt đầu từ critical path và thời gian chờ, không chỉ tăng số job. Nếu một job duy nhất chiếm phần lớn thời gian, tăng concurrency của các job khác ít tạo khác biệt.

## 5. Fan-out và fan-in

Fan-out là chia một tập công việc thành nhiều job độc lập. Fan-in là gom kết quả về một bước tổng hợp hoặc bước tiếp theo.

Ví dụ matrix test:

- Test trên nhiều phiên bản Java.
- Test trên nhiều hệ điều hành.
- Test nhiều module độc lập.
- Build nhiều kiến trúc CPU.
- Chạy nhiều nhóm integration test.

~~~mermaid
flowchart TD
    A["Một commit"] --> B["Fan-out"]
    B --> C["Test Java 17"]
    B --> D["Test Java 21"]
    B --> E["Test Linux"]
    B --> F["Test Windows"]
    C --> G["Fan-in: tổng hợp kết quả"]
    D --> G
    E --> G
    F --> G
    G --> H{"Tất cả bắt buộc đạt?"}
    H -- "Có" --> I["Cho phép bước tiếp theo"]
    H -- "Không" --> J["Chặn pipeline"]
~~~

Fan-out cần được giới hạn. Một ma trận 5 hệ điều hành × 4 phiên bản runtime × 6 module có thể tạo 120 job cho một commit. Nếu nhiều pull request cùng chạy, số job có thể vượt xa capacity của runner pool.

Nên dùng:

- Matrix chỉ cho các tổ hợp có giá trị kiểm thử.
- Max parallelism để giới hạn số job đồng thời.
- Chia test thành nhóm có thời lượng cân bằng.
- Dùng runner phù hợp với loại workload.
- Giới hạn số pipeline run được phép fan-out cùng lúc.
- Hủy các job không còn cần thiết khi điều kiện đã rõ, theo chính sách.

## 6. Chạy đồng thời nhiều pipeline xảy ra khi nào?

Một pipeline run mới có thể được tạo bởi nhiều sự kiện:

- Push commit mới.
- Pull request được tạo hoặc cập nhật.
- Merge vào branch chính.
- Tạo tag hoặc release.
- Lịch chạy định kỳ.
- Người dùng bấm chạy thủ công.
- Pipeline khác gọi reusable workflow hoặc downstream pipeline.
- Retry một lần chạy đã thất bại.

Những sự kiện này có thể xảy ra gần nhau. Ví dụ một developer push ba commit trong một phút. Nếu mỗi commit kích hoạt pipeline, cả ba run có thể cùng hoạt động.

Nhiều pipeline run cũng có thể đến từ các branch khác nhau. Một pull request đang chạy test trong khi branch main triển khai staging. Một nightly scan chạy cùng lúc với release pipeline.

Đây không nhất thiết là lỗi. Nhiều run cùng lúc giúp hệ thống tiếp nhận nhiều thay đổi và giảm thời gian chờ. Vấn đề xuất hiện khi chúng tranh chấp một tài nguyên hoặc tạo ra tác động có thứ tự.

## 7. Hai trục điều phối cần được thiết kế riêng

Có thể hình dung hai trục độc lập:

| | Một pipeline run | Nhiều pipeline run |
|---|---|---|
| Chạy tuần tự | Job A rồi B rồi C | Mỗi run được xếp hàng |
| Chạy song song/đồng thời | Các job độc lập trong DAG chạy cùng lúc | Nhiều run được scheduler cấp tài nguyên cùng lúc |

Ví dụ:

- Một pipeline chạy lint, test và scan song song.
- Hai pipeline của hai pull request chạy cùng lúc, mỗi pipeline có DAG riêng.
- Một pipeline chạy test matrix trong khi pipeline khác build artifact.
- Nhiều pipeline cùng yêu cầu deploy một môi trường staging.

Cần chọn chính sách cho từng cấp. Có thể cho phép test song song trong một run và nhiều run test đồng thời, nhưng serialize deploy vào một staging dùng chung.

Đây là điểm quan trọng: concurrency limit của pipeline run và concurrency limit của job không nhất thiết có cùng giá trị hoặc cùng phạm vi.

## 8. Runner scheduler và giới hạn tài nguyên

Job chỉ có thể chạy khi scheduler cấp được runner phù hợp. Runner có thể bị giới hạn bởi:

- Số máy hoặc container runner.
- CPU, memory và disk.
- Runner labels hoặc loại hệ điều hành.
- Giới hạn concurrency của nền tảng.
- Quota theo organization, repository hoặc project.
- Network bandwidth và giới hạn kết nối.
- Rate limit của package registry, cloud API hoặc dịch vụ test.

Khi có nhiều pipeline run, scheduler phải quyết định job nào được chạy trước. Chính sách có thể dựa trên FIFO, priority, runner labels, fairness hoặc quota.

Cần phân biệt:

- **Job pending:** đang chờ dependency hoặc điều kiện.
- **Job queued:** đã sẵn sàng nhưng chưa được cấp runner.
- **Job running:** đã được thực thi.
- **Job blocked:** bị chặn bởi approval, lock hoặc policy.
- **Job cancelled:** đã bị hủy trước hoặc trong khi thực thi.

Nếu pipeline chậm, cần xác định thời gian bị mất ở dependency, queue hay thực thi. Tăng runner chỉ giúp khi bottleneck là thiếu runner và các giới hạn khác cho phép.

Không nên cấp toàn bộ runner cho một nhóm job fan-out dài nếu điều đó làm release job khẩn cấp không có tài nguyên. Có thể cần runner pool riêng, priority hoặc quota theo loại workload.

## 9. Nhiều pipeline có thể tranh chấp tài nguyên dùng chung

Đây là khác biệt rủi ro lớn nhất so với việc chạy các job độc lập trong cùng một pipeline.

Các tài nguyên thường bị chia sẻ:

| Tài nguyên | Xung đột có thể xảy ra |
|---|---|
| Staging environment | Hai release ghi đè phiên bản hoặc cấu hình của nhau |
| Database kiểm thử | Migration và test của hai run làm thay đổi schema lẫn nhau |
| Registry tag | Hai build ghi đè cùng tag như latest |
| Cache | Job không tin cậy ghi dữ liệu mà job khác sử dụng |
| Terraform state | Hai apply cùng cập nhật một state hoặc tài nguyên |
| Test account | Hai run cùng đổi password, quyền hoặc dữ liệu |
| Cloud quota | Nhiều run tạo tài nguyên vượt quota |
| Shared namespace | Job xóa hoặc sửa tài nguyên của run khác |
| Message queue | Consumer test nhận message của pipeline khác |
| External API sandbox | Nhiều run dùng chung quota hoặc trạng thái tài khoản |

Nếu tài nguyên được cô lập theo run, nhiều pipeline có thể chạy đồng thời an toàn hơn. Nếu tài nguyên dùng chung và có trạng thái mutable, cần isolation hoặc coordination.

## 10. Race condition giữa các pipeline

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các thao tác đồng thời.

### 10.1. Hai pipeline cùng deploy staging

- Run A triển khai commit A.
- Run B triển khai commit B.
- Run B hoàn tất trước.
- Run A hoàn tất sau và ghi đè staging bằng commit cũ.

Kết quả staging không còn phản ánh commit mới nhất, dù cả hai pipeline đều báo thành công.

### 10.2. Hai pipeline cùng chạy migration

- Run A kiểm tra migration M chưa tồn tại.
- Run B cũng kiểm tra và thấy M chưa tồn tại.
- Cả hai cùng bắt đầu chạy M.
- Một run có thể gặp lỗi lock, duplicate DDL hoặc trạng thái migration nửa chừng.

Kiểm tra trước khi chạy không đủ nếu thao tác kiểm tra và ghi không được bảo vệ nguyên tử.

### 10.3. Hai pipeline ghi cùng một artifact tag

- Run A build artifact từ commit A và push tag service:latest.
- Run B build từ commit B và push cùng tag.
- Deployment của run A có thể tải tag sau khi nó đã bị run B thay thế.

Dùng digest bất biến và tag chỉ để tra cứu giúp tránh sự mơ hồ này.

### 10.4. Test dùng chung database

Hai run cùng truncate bảng hoặc seed dữ liệu. Test của run A có thể đọc dữ liệu do run B tạo hoặc bị run B xóa.

Cả hai test có thể pass riêng lẻ nhưng thất bại khi chạy đồng thời.

### 10.5. Terraform hoặc hạ tầng dùng chung

Hai run cùng đọc một state cũ rồi lập kế hoạch thay đổi. Nếu state lock không được sử dụng đúng, một apply có thể ghi đè hoặc làm mất cập nhật của apply còn lại.

Cần dùng backend state có locking và kiểm tra drift trước khi apply.

## 11. Isolation thường tốt hơn khóa toàn bộ công việc

Nếu có thể tạo tài nguyên riêng cho mỗi pipeline run, hãy ưu tiên isolation.

Ví dụ:

- Database riêng hoặc schema riêng theo run ID.
- Kubernetes namespace riêng.
- Bucket hoặc prefix riêng.
- Test account riêng.
- Artifact path riêng.
- Cache namespace riêng.
- Port và service endpoint riêng.
- Dataset được seed độc lập.

Một tên tài nguyên có thể được tạo từ project, run ID và attempt ID. Cần có cleanup và TTL để tránh tài nguyên tạm tích lũy.

Isolation cho phép nhiều pipeline run thực sự chạy song song mà ít phải chờ nhau. Tuy nhiên, không phải tài nguyên nào cũng có thể nhân bản. Production, staging dùng chung, database lớn hoặc quota cloud có thể cần coordination.

Không nên khóa toàn bộ pipeline chỉ vì một bước dùng chung tài nguyên. Hãy cô lập các bước độc lập và chỉ serialize vùng có xung đột.

## 12. Concurrency group và queue

Concurrency group gom các lần chạy có khả năng tranh chấp cùng một phạm vi. Khi một run trong nhóm đang hoạt động, run khác có thể phải chờ, bị hủy hoặc được xếp theo chính sách.

Ví dụ các nhóm hợp lý:

- Deploy production của cùng một service.
- Migration trên cùng một database.
- Apply cùng một Terraform state.
- Thay đổi một staging environment dùng chung.
- Publish một release channel có thứ tự.

Một concurrency group nên đại diện cho tài nguyên hoặc trạng thái cần bảo vệ. Không nên dùng một group chung cho mọi job của mọi repository nếu chúng không chia sẻ tài nguyên.

Các chính sách phổ biến:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Allow concurrent | Cho phép nhiều run cùng chạy | Run được cô lập và độc lập |
| Queue/serialize | Chạy từng run theo lượt | Tài nguyên dùng chung cần một writer |
| Cancel previous | Hủy run cũ khi có run mới | Chỉ cần trạng thái mới nhất, run cũ chưa tạo side effect không thể dừng |
| Latest wins | Giữ yêu cầu mới nhất và bỏ yêu cầu cũ theo policy | Deploy môi trường preview hoặc staging theo branch |
| FIFO | Giữ thứ tự yêu cầu | Cần xử lý mọi release theo trình tự |

Tên gọi và semantics cụ thể tùy nền tảng CI/CD. Có hệ thống chỉ giữ một run đang chạy và một run chờ; có hệ thống hỗ trợ queue nhiều run; có hệ thống hủy run cũ khi run mới đến. Cần kiểm tra tài liệu và thử nghiệm hành vi thực tế trước khi dựa vào nó.

## 13. Không phải lúc nào hủy pipeline cũ cũng an toàn

Hủy run cũ có thể giảm tài nguyên lãng phí, nhưng cancellation không đồng nghĩa với rollback.

Ví dụ:

- Job đang chạy unit test có thể hủy an toàn.
- Job đang build artifact tạm có thể hủy và dọn workspace.
- Job đang deploy có thể đã thay đổi một phần instance.
- Job đang chạy migration có thể đã commit một số thay đổi.
- Job đang apply hạ tầng có thể đã tạo tài nguyên nhưng chưa ghi state hoàn chỉnh.
- Job đang gửi message hoặc gọi payment provider có thể đã tạo side effect.

Trước khi bật cancel-in-progress hoặc cơ chế tương tự, hãy xác định:

- Job có thể nhận tín hiệu cancellation không?
- Thao tác có điểm commit không thể đảo ngược không?
- Có cleanup hoặc compensation khi bị hủy không?
- State hiện tại có được ghi nhận không?
- Run mới có chờ run cũ giải phóng lock không?
- Có thể phát hiện một deployment bị dở dang không?

Với bước có side effect, cần thiết kế cancellation cooperative: job kiểm tra tín hiệu dừng tại các checkpoint, hoàn tất hoặc giải phóng tài nguyên theo cách an toàn, rồi mới kết thúc.

Không nên hủy một migration giữa chừng nếu công cụ migration không hỗ trợ phục hồi trạng thái chạy một phần.

## 14. Distributed lock khi nhiều pipeline cùng thay đổi một tài nguyên

Khi một tài nguyên không thể cô lập, distributed lock có thể đảm bảo chỉ một actor được thực hiện vùng thao tác nhạy cảm tại một thời điểm.

Ví dụ, chỉ một pipeline được phép deploy service vào staging dùng chung.

Một lock cần có:

- **Resource key:** định danh chính xác tài nguyên được khóa.
- **Owner:** run ID hoặc identity của pipeline giữ khóa.
- **Lease/expiry:** thời hạn để tránh lock bị giữ vĩnh viễn khi runner chết.
- **Renewal:** cơ chế gia hạn nếu thao tác kéo dài.
- **Release:** giải phóng sau khi hoàn tất.
- **Audit:** ghi nhận ai lấy, gia hạn và giải phóng lock.

Cần tránh một lỗi tinh vi: lease hết hạn trong khi job cũ vẫn còn chạy. Một job mới lấy lock và bắt đầu deploy, nhưng job cũ vẫn tiếp tục ghi tài nguyên.

Có thể dùng **fencing token**: mỗi lần cấp lock tạo một số thứ tự tăng dần. Tài nguyên đích chỉ chấp nhận thao tác từ token mới nhất và từ chối writer cũ. Chỉ có lease timeout mà không có fencing hoặc kiểm tra owner ở tài nguyên đích có thể chưa đủ để ngăn writer cũ tiếp tục.

Không nên tự triển khai distributed lock bằng file tạm hoặc biến môi trường nếu nhiều máy cần phối hợp. Hãy dùng cơ chế lock được backend hỗ trợ, chẳng hạn state locking, database advisory lock hoặc lock service phù hợp.

## 15. Optimistic concurrency và compare-and-swap

Không phải mọi thao tác đều cần khóa trong toàn bộ thời gian. Với một số tài nguyên, có thể đọc revision hiện tại rồi chỉ ghi nếu revision chưa thay đổi.

Ví dụ:

1. Pipeline đọc environment revision 42.
2. Pipeline tính trạng thái mong muốn.
3. Trước khi ghi, nó yêu cầu cập nhật chỉ khi revision vẫn là 42.
4. Nếu revision đã thành 43, thao tác bị từ chối và pipeline phải resolve lại trạng thái.

Đây là optimistic concurrency control hoặc compare-and-swap.

Ưu điểm:

- Không giữ lock lâu.
- Tránh ghi đè một cập nhật mới hơn.
- Phù hợp với API có version hoặc ETag.
- Có thể retry sau khi đọc lại trạng thái.

Giới hạn:

- Có thể phải tính toán lại khi xung đột.
- Không phù hợp nếu thao tác có nhiều side effect không thể đảo ngược trước khi compare.
- Cần backend hỗ trợ conditional update nguyên tử.

Đối với deployment, có thể yêu cầu environment revision vẫn đúng với revision đã kiểm tra trước khi áp dụng manifest. Nếu trạng thái đã đổi, pipeline dừng và đánh giá lại thay vì ghi đè mù quáng.

## 16. Bảo vệ thứ tự release và tránh deploy commit cũ

Push event có thể đến gần nhau hoặc được xử lý với thời gian khác nhau. Run của commit cũ có thể chậm hơn run mới.

Ví dụ:

~~~text
10:00  Commit A được push, Pipeline A bắt đầu
10:02  Commit B được push, Pipeline B bắt đầu
10:05  Pipeline B deploy B thành công
10:08  Pipeline A deploy A hoàn tất
~~~

Nếu không có coordination, môi trường có thể bị quay về commit A dù B mới hơn.

Các cách kiểm soát:

- Dùng desired revision hoặc release sequence để xác định phiên bản được phép deploy.
- Trước deploy, kiểm tra commit/release vẫn là target hợp lệ.
- Serialize deployment theo service/environment.
- Dùng latest-wins cho môi trường preview nếu policy phù hợp.
- Dùng FIFO khi mọi release phải được xử lý theo thứ tự.
- Hủy run cũ trước bước có side effect nếu nó đã lỗi thời.
- Dùng immutable artifact digest và ghi deployment record.

Không nên chỉ so sánh thời gian bắt đầu pipeline. Thời điểm push, thời điểm run được tạo và thời điểm deploy có thể khác nhau. Cần dùng commit ancestry, release sequence hoặc desired state có thẩm quyền.

## 17. Idempotency giúp retry và phối hợp an toàn

CI/CD có thể gửi lại request khi timeout hoặc mất kết nối. Một job cũng có thể được retry thủ công. Nếu thao tác không idempotent, lần chạy lặp có thể tạo tài nguyên hoặc side effect trùng.

Ví dụ:

- Tạo hai deployment record cho cùng release.
- Chạy migration hai lần.
- Tạo nhiều cloud resource trùng tên.
- Gửi hai thông báo phát hành.
- Publish hai artifact khác nhau dưới cùng tag.
- Gửi cùng một message nhiều lần.

Các biện pháp:

- Dùng release ID hoặc operation ID duy nhất.
- Kiểm tra trạng thái trước khi tạo hoặc thay đổi tài nguyên.
- Dùng upsert hoặc API idempotency key khi được hỗ trợ.
- Migration có version và cơ chế nhận biết đã chạy.
- Artifact được định danh bằng digest.
- Job retry chỉ với lỗi tạm thời và có backoff.
- Ghi checkpoint để tiếp tục từ trạng thái đã biết.
- Có compensation hoặc cleanup cho thao tác không thể làm idempotent.

Idempotency không thay thế lock. Hai pipeline có thể cùng kiểm tra một trạng thái chưa tồn tại rồi cùng tạo tài nguyên. Cần một thao tác nguyên tử, unique constraint, lock hoặc conditional create để xử lý race.

## 18. Database migration và tài nguyên dùng chung cần điều phối riêng

Database migration thường có phạm vi ảnh hưởng lớn hơn một job test.

Nếu hai pipeline cùng chạy migration:

- Có thể cùng cố tạo một bảng hoặc index.
- Có thể tranh chấp lock của database.
- Một migration phụ thuộc migration khác có thể chạy sai thứ tự.
- Một pipeline có thể kiểm tra trạng thái trước khi pipeline kia ghi nhận migration.
- Migration dài có thể chặn request production.

Các nguyên tắc:

- Mỗi database hoặc schema có một cơ chế migration lock.
- Migration có version và lịch sử thực thi rõ.
- Dùng transaction nếu database và migration hỗ trợ.
- Xác định hành vi nếu migration thất bại giữa chừng.
- Không cho test job tùy ý chạy migration trên database dùng chung.
- Dùng database hoặc schema riêng cho mỗi test run khi có thể.
- Production migration cần gate, quyền và runbook phù hợp.

Tương tự, Terraform state, Kubernetes namespace, shared staging và registry release channel đều cần coordination theo resource key cụ thể.

## 19. Cache và artifact trong môi trường nhiều pipeline

Cache tăng tốc nhưng cũng có thể là điểm chia sẻ trạng thái.

Một cache key quá chung có thể khiến run của branch này đọc dữ liệu do branch khác tạo. Nếu dữ liệu cache không tương thích hoặc bị đầu độc, kết quả build có thể không đáng tin.

Nên:

- Tạo cache key từ lockfile, toolchain và hệ điều hành.
- Phân vùng theo trust boundary.
- Không dùng cache như nguồn chuẩn của artifact.
- Không để job không tin cậy ghi cache được job phát hành tin cậy sử dụng.
- Có cơ chế invalidate khi dependency hoặc cấu hình thay đổi.

Artifact nên được lưu riêng theo run hoặc release, có digest và metadata. Không dùng một tag mutable chung làm đầu ra duy nhất của nhiều pipeline.

Nếu cần alias như latest hoặc stable, chỉ cập nhật alias qua một bước publish được điều phối, sau khi đã xác minh run nào được phép trở thành bản mới nhất.

## 20. Mô hình điều phối thực tế cho CI/CD

Một mô hình cân bằng thường có các nguyên tắc:

- Job lint, unit test và scan độc lập chạy song song trong một pipeline.
- Integration test chạy trong database hoặc namespace riêng theo run.
- Nhiều pipeline validation có thể chạy đồng thời nếu runner capacity cho phép.
- Build artifact được lưu theo digest bất biến.
- Publish alias hoặc release metadata được điều phối để tránh ghi đè.
- Deploy vào preview environment có thể song song nếu mỗi branch có môi trường riêng.
- Deploy vào staging dùng chung được serialize hoặc kiểm tra desired revision.
- Deploy production dùng lock, approval và identity riêng.
- Migration dùng lock ở cấp database/schema.
- Cleanup chỉ xóa tài nguyên thuộc đúng run ID.

~~~mermaid
flowchart TD
    A["Push / PR event"] --> B["Pipeline run"]
    B --> C["Lint"]
    B --> D["Unit tests"]
    B --> E["Dependency scan"]
    C --> F["Package"]
    D --> F
    E --> F
    F --> G["Artifact registry by digest"]
    G --> H["Integration test in isolated environment"]
    H --> I["Release verification"]
    I --> J["Acquire environment coordination"]
    J --> K["Deploy shared environment"]
    K --> L["Post-deploy verification"]
    L --> M["Release evidence"]
~~~

Trong khi pipeline này đang chạy, các pipeline validation khác vẫn có thể chạy song song. Chỉ bước thay đổi shared environment cần được điều phối.

## 21. Ví dụ cấu hình logic concurrency

YAML sau minh họa ý tưởng tổng quát, không phải cú pháp của một nền tảng cụ thể:

~~~yaml
pipeline:
  jobs:
    lint:
      parallel: true
      needs: [checkout]

    unit_tests:
      parallel: true
      needs: [checkout]
      matrix:
        runtime: [17, 21]
      max_parallel: 4

    dependency_scan:
      parallel: true
      needs: [checkout]

    package:
      needs: [lint, unit_tests, dependency_scan]

    integration_tests:
      needs: [package]
      environment:
        isolation_key: run_id
        cleanup_ttl: 2h

    deploy_staging:
      needs: [integration_tests]
      concurrency:
        resource: service-staging
        policy: queue
      precondition:
        desired_revision_must_match: true

    deploy_production:
      needs: [deploy_staging]
      concurrency:
        resource: service-production
        policy: queue
      approval: required
      lock_lease: bounded
      verify_after_deploy: true
~~~

Cấu hình thể hiện hai cấp:

- Job kiểm thử độc lập có thể fan-out trong một run, với giới hạn max_parallel.
- Deploy staging và production dùng coordination theo tài nguyên môi trường.

Trong triển khai thực tế, cần kiểm tra semantics của công cụ CI: concurrency group có giữ queue hay hủy run cũ, lock có được giữ qua job hay không và cancellation được truyền đến process đang chạy như thế nào.

## 22. Quan sát và đo lường điều phối

Không có metric thì khó biết pipeline chậm do thiếu runner, queue dài hay do dependency.

Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Queue wait time | Thời gian job chờ runner hoặc slot |
| Job execution time | Thời gian thực thi thực tế |
| Pipeline duration | Thời gian từ trigger đến kết quả cuối |
| Active pipeline runs | Số pipeline run đang hoạt động |
| Active jobs / runner utilization | Mức sử dụng runner |
| Concurrency limit hits | Số lần bị chặn bởi giới hạn đồng thời |
| Lock wait time | Thời gian chờ tài nguyên dùng chung |
| Lock timeout / stale lock | Lỗi điều phối hoặc lease hết hạn |
| Cancelled / superseded runs | Số run bị hủy hoặc bị run mới thay thế |
| Deployment revision order | Thứ tự revision được triển khai thực tế |
| Resource contention | CPU, memory, disk, quota hoặc rate limit |
| Test isolation failures | Lỗi do dữ liệu hoặc môi trường bị chia sẻ |

Cần gắn run ID, commit SHA, release ID, environment ID và resource key vào log để có thể truy vết từ job đến tài nguyên.

Nếu queue wait tăng nhưng runner utilization thấp, có thể vấn đề nằm ở concurrency group hoặc approval. Nếu runner utilization luôn cao và queue dài, cần xem xét capacity, giới hạn fan-out và priority. Nếu lock wait cao, có thể resource scope quá rộng hoặc thao tác giữ lock quá lâu.

## 23. Kiểm thử các tình huống cạnh tranh

Không nên chỉ kiểm tra pipeline khi chạy một mình. Cần thử các tình huống nhiều run cùng hoạt động:

- Hai pull request chạy integration test đồng thời.
- Hai commit liên tiếp cùng yêu cầu deploy staging.
- Hai pipeline cùng chạy migration trên một database.
- Một run bị hủy trong lúc đang deploy.
- Runner mất kết nối khi đang giữ lock.
- Lease hết hạn nhưng process cũ chưa dừng.
- Retry sau timeout khi thao tác trước có thể đã thành công.
- Hai pipeline cùng publish alias artifact.
- Một pipeline cũ hoàn tất sau pipeline mới.
- Cleanup của một run chạy khi run khác vẫn dùng tài nguyên.
- Queue hoặc external API đạt rate limit.
- Một pipeline giữ lock quá thời hạn dự kiến.

Kết quả kiểm thử cần chứng minh:

- Không có hai writer cùng sửa tài nguyên độc quyền.
- Không deploy revision cũ sau revision mới khi policy không cho phép.
- Retry không tạo side effect trùng.
- Cancellation không để lại trạng thái nửa chừng không được ghi nhận.
- Lock được giải phóng hoặc fencing ngăn writer cũ.
- Tài nguyên tạm của run này không bị cleanup bởi run khác.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Cho mọi job chạy song song | Tăng tải, tranh chấp và khó debug | Dựa vào DAG và dependency thật |
| Tuần tự hóa toàn bộ pipeline | Thời gian chờ dài, giảm throughput | Chỉ serialize vùng dùng chung tài nguyên |
| Nhầm concurrency của job với concurrency của run | Bỏ sót xung đột giữa nhiều pipeline | Thiết kế hai cấp điều phối riêng |
| Mọi pipeline cùng deploy staging | Run cũ có thể ghi đè run mới | Queue, lock hoặc environment riêng |
| Dùng tag mutable cho artifact | Pipeline có thể deploy nhầm nội dung | Dùng digest bất biến |
| Dùng chung database test | Test phá dữ liệu của run khác | Database/schema/container riêng |
| Hủy run cũ ở mọi thời điểm | Migration hoặc deploy có thể dở dang | Cancellation cooperative và checkpoint |
| Dùng lock không có lease/fencing | Lock stale hoặc writer cũ tiếp tục ghi | Lease, owner check và fencing token |
| Retry mọi lỗi | Lặp side effect hoặc tăng tải | Retry có phân loại, backoff và idempotency |
| Chỉ dùng CI concurrency group để khóa database | Công cụ khác vẫn có thể sửa database | Lock ở chính tài nguyên hoặc backend |
| Cleanup theo tên chung | Xóa tài nguyên của run khác | Gắn resource với run ID và owner |
| Không kiểm tra thứ tự commit | Commit cũ có thể deploy sau commit mới | Desired revision và precondition |
| Chỉ đo tổng thời gian pipeline | Không biết bottleneck ở queue hay execution | Theo dõi queue, lock và critical path |

## 25. Checklist thiết kế điều phối đồng thời

Khi thiết kế pipeline, hãy xác nhận:

- [ ] Đã phân biệt job parallelism trong một run và concurrency giữa nhiều run.
- [ ] DAG chỉ thể hiện dependency thực sự.
- [ ] Fan-out có giới hạn và phù hợp runner capacity.
- [ ] Critical path và queue wait được đo riêng.
- [ ] Nhiều pipeline validation có thể chạy đồng thời khi dữ liệu được cô lập.
- [ ] Tài nguyên dùng chung đã có resource key và owner.
- [ ] Database test, namespace, cache và artifact được phân vùng theo run khi có thể.
- [ ] Deploy vào shared environment được queue hoặc lock.
- [ ] Migration có coordination ở cấp database/schema.
- [ ] Artifact dùng digest bất biến; alias được cập nhật có kiểm soát.
- [ ] Cancellation được thiết kế theo loại thao tác và side effect.
- [ ] Retry có backoff, idempotency key hoặc checkpoint.
- [ ] Lock có owner, lease, renewal, release và cơ chế chống stale writer.
- [ ] Có kiểm tra desired revision trước khi deploy.
- [ ] Cleanup chỉ tác động tài nguyên thuộc đúng run.
- [ ] Có log và metric để truy vết queue, lock, run và deployment order.
- [ ] Đã thử nhiều pipeline chạy cùng lúc, retry, cancellation và runner failure.

## 26. Bài tập tự đánh giá

Một repository có pipeline như sau:

- Mỗi pull request chạy lint, unit test, dependency scan và integration test.
- Integration test dùng chung một database staging.
- Mỗi commit vào main tạo một pipeline deploy staging.
- Pipeline deploy dùng tag image latest.
- Nếu có commit mới, run cũ bị hủy ngay lập tức.
- Migration được chạy ở đầu bước deploy.
- Một nightly pipeline cũng chạy migration và smoke test trên cùng staging.

Khi hai commit liên tiếp được push, nhóm gặp lỗi test không ổn định và đôi khi staging chạy phiên bản cũ hơn commit mới nhất.

Hãy phân tích:

1. Những job nào trong một pipeline có thể chạy song song?
2. Vì sao integration test dùng chung database gây race condition?
3. Có thể cô lập database hoặc schema theo run như thế nào?
4. Cần điều phối các pipeline deploy staging ra sao?
5. Tag latest gây rủi ro gì khi hai build cùng publish?
6. Có nên hủy run cũ ngay cả khi migration đang chạy không?
7. Nightly pipeline cần dùng lock hoặc môi trường riêng nào?
8. Làm thế nào ngăn commit cũ deploy sau commit mới?
9. Retry migration cần bảo đảm idempotency và trạng thái thế nào?
10. Cần theo dõi metric nào để xác định queue, runner hay lock là bottleneck?

Một thiết kế tốt sẽ giữ lint, unit test và scan chạy song song; tạo database riêng cho integration test; build artifact bất biến; chỉ serialize các thao tác thay đổi staging hoặc database dùng chung; và kiểm tra desired revision trước khi deploy.

## Kết luận

Chạy song song công việc trong một pipeline giúp rút ngắn critical path bằng cách thực thi các job độc lập cùng lúc. Chạy đồng thời nhiều pipeline giúp hệ thống tiếp nhận nhiều sự kiện và tăng throughput, nhưng có thể tạo race condition khi các run cùng thay đổi tài nguyên dùng chung.

Hãy mô hình hóa dependency bằng DAG, giới hạn fan-out theo capacity, cô lập dữ liệu và môi trường theo run, rồi dùng queue, lock hoặc compare-and-swap ở những tài nguyên cần phối hợp. Kết hợp idempotency, cancellation an toàn, artifact bất biến và kiểm tra thứ tự revision để pipeline vừa nhanh vừa không ghi đè trạng thái của nhau. Điều phối tốt không có nghĩa mọi thứ phải chạy tuần tự; nó có nghĩa mỗi công việc được chạy đồng thời khi an toàn và được phối hợp đúng lúc khi có xung đột.

