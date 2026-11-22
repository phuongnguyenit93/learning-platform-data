# Phân loại lỗi mã nguồn, kiểm thử, hạ tầng và cấu hình

Một pipeline CI/CD thất bại không phải lúc nào cũng có nghĩa mã nguồn mới bị lỗi. Build có thể dừng vì compiler phát hiện lỗi; test có thể thất bại do regression hoặc do dữ liệu kiểm thử không ổn định; runner có thể hết dung lượng; registry có thể tạm thời không truy cập được; cấu hình môi trường có thể thiếu biến bắt buộc hoặc trỏ nhầm dịch vụ. Nếu chỉ nhìn dấu X đỏ của pipeline rồi retry toàn bộ job, nhóm có thể tốn thời gian, che khuất nguyên nhân và làm tăng tải lên hệ thống đang gặp sự cố.

Muốn xử lý thất bại hiệu quả, trước hết phải **phân loại lỗi theo miền phát sinh và bằng chứng quan sát được**. Bài học này tập trung vào bốn nhóm chính: lỗi mã nguồn, lỗi kiểm thử, lỗi hạ tầng và lỗi cấu hình. Sau đó, bài học liên hệ cách phân loại với quyết định sửa mã, sửa test, khôi phục runner, điều chỉnh cấu hình hoặc retry có giới hạn.

Mục tiêu không phải gắn nhãn thật nhanh cho mọi lỗi. Mục tiêu là xác định điều gì đã hỏng, lỗi có tái hiện được không, có thể retry an toàn không, ai sở hữu việc xử lý và bằng chứng nào cần lưu để tránh lặp lại cùng một sự cố.

## 1. Vì sao cần phân loại lỗi trước khi retry?

Retry là chạy lại một bước hoặc một job sau khi thất bại. Nó hữu ích khi nguyên nhân có tính tạm thời, chẳng hạn network reset hoặc dịch vụ registry vừa quá tải. Nhưng retry không sửa được lỗi logic, assertion sai, cấu hình thiếu hay quyền truy cập bị từ chối.

Nếu retry sai loại lỗi, có thể xảy ra:

- Một lỗi code bị che bởi lần chạy tình cờ không đi qua nhánh lỗi.
- Một flaky test tiếp tục làm pipeline lúc xanh lúc đỏ, khiến nhóm mất niềm tin vào kết quả.
- Một runner thiếu disk tiếp tục nhận job và làm nhiều pipeline khác thất bại.
- Một secret hoặc endpoint sai bị thử lại nhiều lần nhưng không thể tự đúng lên.
- Một dịch vụ phụ thuộc đang quá tải nhận thêm request do nhiều job retry đồng thời.
- Bằng chứng của lần chạy đầu bị ghi đè bởi log của lần chạy sau.

Một quy trình xử lý tốt thường đi theo thứ tự:

1. Thu thập lỗi, mã thoát, log, test report và trạng thái runner.
2. Xác định bước thất bại và thời điểm bắt đầu.
3. Phân loại miền phát sinh: source, test, infrastructure hoặc configuration.
4. Kiểm tra khả năng tái hiện và đối chiếu với thay đổi gần nhất.
5. Quyết định sửa nguyên nhân, retry có điều kiện hay chuyển người phụ trách.
6. Chạy lại đúng phạm vi cần xác minh và lưu kết quả.

~~~mermaid
flowchart TD
    A["Pipeline thất bại"] --> B["Thu thập log, exit code, report"]
    B --> C["Xác định job và bước lỗi"]
    C --> D{"Có bằng chứng lỗi hạ tầng tạm thời?"}
    D -- "Có" --> E["Retry có giới hạn / kiểm tra runner"]
    D -- "Không" --> F{"Lỗi có tái hiện ổn định?"}
    F -- "Có" --> G{"Miền phát sinh"}
    G -- "Mã nguồn" --> H["Sửa code hoặc dependency"]
    G -- "Kiểm thử" --> I["Sửa sản phẩm hoặc test"]
    G -- "Cấu hình" --> J["Sửa cấu hình / quyền / secret"]
    F -- "Không rõ" --> K["Thu thập thêm bằng chứng"]
    K --> G
    E --> L["Xác minh kết quả sau xử lý"]
    H --> L
    I --> L
    J --> L
    L --> M["Ghi nguyên nhân và kết quả"]
~~~

Không nên kết luận nguyên nhân chỉ từ một dòng log cuối cùng. Dòng cuối có thể là nơi tiến trình dừng, không phải nơi lỗi bắt đầu. Hãy tìm lỗi đầu tiên có ý nghĩa trong chuỗi sự kiện và kiểm tra các nguyên nhân dây chuyền.

## 2. Bốn miền lỗi chính

Bốn nhóm trong bài học là cách phân loại thực dụng cho CI/CD. Một sự cố có thể liên quan nhiều miền. Ví dụ, cấu hình sai khiến ứng dụng không kết nối database, sau đó integration test thất bại. Khi đó, lỗi quan sát được ở test nhưng nguyên nhân gốc thuộc configuration.

| Miền lỗi | Bản chất | Dấu hiệu thường gặp | Cách xử lý chính |
|---|---|---|---|
| Mã nguồn | Code, dependency hoặc build logic không đáp ứng yêu cầu | Compile error, static analysis, assertion, exception tái hiện ổn định | Sửa code, dependency hoặc build definition |
| Kiểm thử | Test, fixture, dữ liệu hoặc môi trường test có vấn đề | Flaky, timeout ngẫu nhiên, test order dependency, fixture lỗi | Xác minh test, sửa fixture hoặc sản phẩm |
| Hạ tầng | Runner, network, storage, registry hoặc dịch vụ nền tảng không sẵn sàng | Runner offline, disk full, 5xx từ service, DNS/network error | Khôi phục hạ tầng hoặc retry lỗi tạm thời |
| Cấu hình | Giá trị, quyền, secret hoặc tham số môi trường sai/thiếu | Missing variable, invalid URL, permission denied, sai endpoint | Sửa nguồn cấu hình và xác thực lại |

Cần phân biệt **triệu chứng** với **nguyên nhân gốc**:

- Test báo timeout là triệu chứng. Nguyên nhân có thể là code chậm, runner quá tải, database test không phản hồi hoặc timeout cấu hình quá thấp.
- Deploy báo unauthorized là triệu chứng. Nguyên nhân có thể là token hết hạn, role thiếu quyền hoặc job dùng nhầm identity.
- Build không tải được dependency là triệu chứng. Nguyên nhân có thể là registry lỗi, proxy sai, credential hết hạn hoặc dependency version không tồn tại.

Khi phân loại, ghi cả miền lỗi quan sát được và nguyên nhân gốc nếu đã xác định. Nếu chưa đủ bằng chứng, dùng trạng thái chưa rõ thay vì đoán.

## 3. Lỗi mã nguồn

Lỗi mã nguồn xuất hiện khi source, dependency hoặc build logic không hợp lệ hoặc không đáp ứng yêu cầu của ứng dụng.

### 3.1. Dấu hiệu nhận biết

Các dấu hiệu thường gặp:

- Compiler báo lỗi cú pháp, kiểu dữ liệu hoặc symbol không tồn tại.
- Linter hoặc static analyzer phát hiện quy tắc bị vi phạm.
- Unit test thất bại ổn định sau một thay đổi code.
- Build task không tạo được output do cấu hình build hoặc source không tương thích.
- Ứng dụng ném exception khi đi qua một nhánh xử lý cụ thể.
- Dependency mới gây xung đột phiên bản hoặc thay đổi API.
- Security scanner phát hiện một vấn đề có thể truy về code hoặc dependency.

Một lỗi source thường có khả năng tái hiện khi dùng cùng commit, toolchain và đầu vào. Tuy nhiên, race condition, lỗi đồng thời hoặc phụ thuộc thời gian có thể khiến lỗi chỉ xuất hiện không đều. Không nên coi một lỗi không tái hiện ngay là lỗi hạ tầng.

### 3.2. Cách điều tra

1. Xác định commit SHA và thay đổi liên quan.
2. Đọc lỗi đầu tiên từ compiler, analyzer hoặc runtime stack trace.
3. Chạy lại đúng build/test command trong môi trường tương đương.
4. So sánh với commit trước hoặc lần chạy cuối cùng thành công.
5. Kiểm tra dependency lockfile, compiler và build tool version.
6. Thu hẹp đến module, file hoặc task gây lỗi.
7. Sửa nguyên nhân và chạy lại kiểm tra mục tiêu, sau đó chạy bộ test bắt buộc.

Ví dụ lỗi compile:

~~~text
src/main/java/example/OrderService.java:42: error: cannot find symbol
    paymentClient.authorize(order);
                 ^
  symbol:   method authorize(Order)
  location: variable paymentClient of type PaymentClient
~~~

Thông báo này chỉ ra code gọi một method không có trong kiểu PaymentClient đang được compiler sử dụng. Retry build không thay đổi kết quả. Cần kiểm tra API của dependency, phiên bản thư viện hoặc tên method đã thay đổi.

### 3.3. Dependency và build definition

Không phải lỗi build nào cũng nằm trong source ứng dụng. Thay đổi dependency, plugin, compiler option hoặc build script cũng là thay đổi mã có thể gây lỗi.

Cần xem:

- Dependency có được khai báo và khóa phiên bản không?
- Lockfile hoặc dependency constraints có thay đổi không?
- Repository có cung cấp đúng package/version không?
- Plugin có tương thích với phiên bản runtime/build tool không?
- Build có phụ thuộc file hoặc biến môi trường chưa khai báo không?
- Artifact có được tạo từ đúng commit và toolchain không?

Nếu package không tồn tại hoặc phiên bản không tương thích, retry không giúp ích. Nếu registry tạm thời không truy cập được, đó có thể là lỗi hạ tầng và retry có giới hạn có thể phù hợp.

### 3.4. Khi nào không nên retry lỗi source?

Không retry để xử lý:

- Compile error tái hiện ổn định.
- Static analysis violation có bằng chứng rõ.
- Unit test assertion thất bại do kết quả thực tế sai.
- Dependency version không tồn tại hoặc không tương thích.
- Build script có lỗi logic.
- Security gate phát hiện vấn đề cần sửa hoặc đánh giá.

Có thể chạy lại sau khi code hoặc dependency đã thay đổi. Đó là xác minh bản sửa, không phải retry cùng một đầu vào.

## 4. Lỗi kiểm thử

Lỗi kiểm thử là nhóm cần phân tích cẩn thận nhất vì test có thể phát hiện lỗi thật của sản phẩm, nhưng bản thân test hoặc môi trường test cũng có thể không ổn định.

### 4.1. Phân biệt test failure và test infrastructure failure

**Test failure** xảy ra khi test chạy được nhưng kết quả thực tế không khớp kỳ vọng. Ví dụ, đơn hàng được tính sai tổng tiền hoặc người dùng không có quyền vẫn đọc được dữ liệu.

**Test infrastructure failure** xảy ra khi test không thể thực thi đáng tin cậy do database test không khởi động, container registry không truy cập được, runner hết tài nguyên hoặc dịch vụ giả lập bị lỗi.

Một số dấu hiệu:

| Dấu hiệu | Khả năng | Kiểm tra |
|---|---|---|
| Assertion thất bại cùng một giá trị | Regression hoặc kỳ vọng test lỗi thời | Xác minh yêu cầu và thay đổi code |
| Cùng test lúc pass lúc fail | Flaky test, race hoặc môi trường biến động | Chạy lặp có kiểm soát, xem thứ tự và tài nguyên |
| Nhiều test cùng timeout | Runner hoặc dependency test quá tải | Xem CPU, memory, network và service health |
| Chỉ thất bại khi chạy song song | Shared state, port hoặc dữ liệu dùng chung | Kiểm tra isolation và cleanup |
| Test không tìm thấy fixture | Đường dẫn, artifact test hoặc setup sai | Kiểm tra working directory và setup step |
| Snapshot thay đổi ngoài dự kiến | Output thay đổi hoặc snapshot lỗi thời | Review diff, không cập nhật snapshot mù quáng |

### 4.2. Flaky test

Flaky test là test có cùng đầu vào nhưng kết quả thay đổi giữa các lần chạy mà không có thay đổi tương ứng trong sản phẩm hoặc kỳ vọng.

Nguyên nhân phổ biến:

- Phụ thuộc thời gian hoặc timezone.
- Dùng sleep cố định thay cho chờ điều kiện.
- Race condition và xử lý đồng thời.
- Dữ liệu test dùng chung giữa các test.
- Thứ tự thực thi ảnh hưởng kết quả.
- Port hoặc file tạm bị tranh chấp.
- Gọi dịch vụ bên ngoài không ổn định.
- Test không cleanup tài nguyên sau khi chạy.

Không nên chỉ tăng số lần retry test để làm pipeline xanh. Retry có thể giúp xác nhận tính không ổn định, nhưng không loại bỏ nguyên nhân. Test flaky cần được ghi nhận, gán owner và có kế hoạch sửa.

### 4.3. Quy trình xác minh flaky test

1. Ghi lại test name, seed, thời gian, runner và commit.
2. Chạy test riêng lẻ để kiểm tra khả năng tái hiện.
3. Chạy nhiều lần với cùng cấu hình và seed nếu framework hỗ trợ.
4. Chạy cả suite để phát hiện phụ thuộc thứ tự.
5. Chạy song song và tuần tự để so sánh.
6. Kiểm tra clock, timezone, network, fixture và shared state.
7. Sửa test hoặc code nếu phát hiện race thực sự.
8. Nếu tạm quarantine, phải ghi owner, lý do, thời hạn và bộ kiểm tra thay thế.

Quarantine không có nghĩa xóa test khỏi chất lượng phát hành. Nếu test bảo vệ chức năng quan trọng, cần có biện pháp kiểm tra thay thế trong thời gian xử lý.

### 4.4. Phân biệt test timeout với test assertion

Timeout có thể là lỗi sản phẩm, test hoặc hạ tầng. Hãy xác định test đang chờ điều gì:

- Chờ HTTP response: xem server, dependency và network.
- Chờ database lock: xem transaction, pool và dữ liệu dùng chung.
- Chờ message: xem producer, consumer, queue và test setup.
- Chờ UI element: xem ứng dụng, selector và đồng bộ giao diện.
- Chờ job: xem worker, queue lag và deadline.

Assertion failure thường cho biết một điều kiện đã được kiểm tra nhưng sai. Timeout thường cho biết điều kiện không đạt trong thời hạn. Hai loại này cần hướng điều tra khác nhau.

## 5. Lỗi hạ tầng

Lỗi hạ tầng phát sinh từ môi trường thực thi pipeline hoặc các dịch vụ nền tảng mà job phụ thuộc.

### 5.1. Nhóm lỗi thường gặp

- Runner offline, bị terminate hoặc mất kết nối.
- Disk full, inode exhaustion hoặc workspace hết dung lượng.
- CPU/memory thiếu, process bị OOM kill.
- DNS, proxy, firewall hoặc network route lỗi.
- Package registry, artifact store hoặc container registry không sẵn sàng.
- API của cloud provider hoặc nền tảng CI trả 5xx/rate limit.
- Database, message broker hoặc service test không khởi động.
- Certificate hết hạn hoặc clock lệch trên runner.
- Container image pull thất bại do registry/network.

### 5.2. Dấu hiệu nhận biết

| Dấu hiệu | Miền hạ tầng có thể liên quan | Bằng chứng cần lấy |
|---|---|---|
| Job bị mất giữa chừng, không có test report | Runner/host bị dừng | Runner event, host status, termination reason |
| No space left on device | Storage | Disk usage, inode, workspace size |
| Exit 137 hoặc OOMKilled | Memory/container limit | Memory metric, kernel/container event |
| DNS lookup timeout | DNS/network | Resolver log, DNS query, network trace |
| HTTP 429 hoặc 503 từ registry | Rate limit/service availability | Response header, status, service status |
| Nhiều repository thất bại cùng lúc | Shared infrastructure/dependency | Phạm vi ảnh hưởng theo runner/region/service |
| Chỉ một runner pool lỗi | Runner image hoặc pool config | Image version, pool health, node events |

Một lỗi xảy ra đồng thời ở nhiều repository có thể gợi ý sự cố dùng chung, nhưng vẫn cần kiểm tra. Một thay đổi thư viện hoặc credential được áp dụng diện rộng cũng có thể làm nhiều pipeline thất bại cùng lúc.

### 5.3. Xác minh trước khi retry

Trước khi retry lỗi hạ tầng, kiểm tra:

- Dịch vụ phụ thuộc đã phục hồi chưa?
- Runner mới có khỏe và đủ dung lượng không?
- Request trước có thể đã được server xử lý dù client mất response không?
- Retry có làm tăng tải lên dịch vụ đang quá tải không?
- Có giới hạn rate hoặc Retry-After cần tuân thủ không?
- Có cần chuyển sang runner pool hoặc region khác không?

Nếu runner bị hỏng, chạy lại trên cùng runner có thể tái tạo lỗi. Cần cấp runner sạch hoặc khôi phục pool trước.

## 6. Lỗi cấu hình

Lỗi cấu hình xảy ra khi giá trị hoặc quy tắc được cung cấp cho job/ứng dụng không đúng với yêu cầu của môi trường.

### 6.1. Các loại lỗi cấu hình

- Thiếu biến môi trường bắt buộc.
- Sai tên biến hoặc sai kiểu dữ liệu.
- URL, hostname, port hoặc namespace không đúng.
- Cấu hình trỏ nhầm staging sang production hoặc ngược lại.
- Secret hết hạn, bị thu hồi hoặc được cấp sai scope.
- Token có danh tính đúng nhưng thiếu quyền.
- Feature flag hoặc build profile tạo tổ hợp không hợp lệ.
- Config file không được mount hoặc có định dạng sai.
- Thứ tự precedence khiến giá trị mặc định ghi đè giá trị môi trường.
- Thay đổi cấu hình trực tiếp tạo ra configuration drift.

### 6.2. Dấu hiệu và hướng kiểm tra

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Missing required variable | Pipeline/environment chưa khai báo | Kiểm tra tên và scope biến |
| Invalid URL/port | Giá trị sai định dạng hoặc sai môi trường | Validate schema và allowlist |
| Unauthorized/forbidden | Token thiếu scope hoặc role | Xác minh identity, permission và audience |
| Secret not found | Sai secret reference hoặc environment | Kiểm tra secret name/version và quyền đọc |
| Certificate verify failed | CA bundle, hostname hoặc certificate sai/hết hạn | Kiểm tra trust chain và clock |
| Kết nối nhầm dịch vụ | Precedence hoặc endpoint sai | Ghi nguồn của giá trị hiệu lực, không in secret |
| Local pass nhưng CI fail | Khác runtime, env var, filesystem hoặc permission | So sánh cấu hình đã redact và toolchain |

### 6.3. Cấu hình và secret cần được xác minh an toàn

Không in toàn bộ environment hoặc secret để điều tra. Có thể ghi:

- Tên thuộc tính bị thiếu.
- Nguồn cấu hình được chọn.
- Phiên bản hoặc revision của config.
- Secret reference và trạng thái truy cập, không ghi giá trị.
- Identity, role hoặc scope đã sử dụng.
- Kết quả validation.

Nếu nghi ngờ secret bị lộ, cần thu hồi hoặc luân chuyển và xác định phạm vi ảnh hưởng. Retry cùng secret đã hết hạn không thể khắc phục vấn đề.

## 7. Phân loại theo khả năng retry

Sau khi xác định miền lỗi, cần đánh giá khả năng retry. Miền lỗi không quyết định tuyệt đối: lỗi hạ tầng có thể là vĩnh viễn do cấu hình network sai; lỗi test có thể là transient do database test vừa khởi động.

| Loại lỗi | Retry cùng đầu vào? | Hành động khuyến nghị |
|---|---|---|
| Compile error | Không | Sửa source hoặc dependency |
| Assertion failure ổn định | Không | Điều tra regression hoặc test expectation |
| Flaky test | Chỉ dùng để xác nhận có kiểm soát | Ghi flaky, tìm race và sửa test/sản phẩm |
| Runner bị terminate | Có, sau khi dùng runner khỏe | Thu thập runner event, cấp runner mới |
| Network reset tạm thời | Có giới hạn | Backoff, jitter và timeout |
| Registry trả 429 | Có theo chính sách | Tuân thủ Retry-After và retry budget |
| Permission denied | Không | Sửa identity, role hoặc policy |
| Missing configuration | Không | Bổ sung và validate cấu hình |
| Secret hết hạn | Không với secret cũ | Luân chuyển hoặc cấp credential mới |
| Artifact digest mismatch | Không | Dừng pipeline, xác minh nguồn và tính toàn vẹn |
| Dependency service 5xx | Có điều kiện | Retry giới hạn, circuit breaker nếu phù hợp |
| Quota hoặc capacity exhausted | Không retry dồn dập | Chờ capacity, giảm concurrency hoặc tăng quota |

Cần phân biệt ba quyết định:

- **Retry:** chạy lại cùng thao tác vì lỗi được đánh giá là tạm thời và thao tác an toàn khi lặp.
- **Fix and rerun:** sửa nguyên nhân rồi chạy lại để xác minh.
- **Escalate/hold:** dừng pipeline, giữ bằng chứng và chuyển cho owner khi chưa đủ thông tin hoặc có rủi ro.

## 8. Thiết kế retry có giới hạn

Retry chỉ nên được áp dụng cho thao tác có khả năng thành công ở lần thử sau. Mỗi chính sách retry cần có số lần tối đa, timeout tổng, khoảng chờ và loại lỗi được phép retry.

### 8.1. Exponential backoff

Exponential backoff tăng khoảng chờ theo số lần thử. Một dạng đơn giản:

\[
d_n = \min(d_{\max}, d_0 \times 2^n)
\]

Trong đó:

- \(d_0\): khoảng chờ ban đầu.
- \(n\): số lần retry đã thực hiện.
- \(d_{\max}\): giới hạn thời gian chờ tối đa.

Ví dụ, khoảng chờ có thể tăng từ 1 giây lên 2, 4, 8 giây rồi dừng ở mức tối đa. Giá trị thực tế phụ thuộc latency và rate limit của dịch vụ.

### 8.2. Jitter

Nếu nhiều job cùng retry theo lịch giống nhau, chúng có thể tạo ra một đợt request đồng thời và làm dịch vụ quá tải hơn. Jitter thêm độ ngẫu nhiên vào khoảng chờ để phân tán request.

Một cách phổ biến là full jitter:

\[
d_n = U(0,\min(d_{\max},d_0 \times 2^n))
\]

Trong đó \(U(0,x)\) là giá trị ngẫu nhiên trong khoảng từ 0 đến \(x\).

Với HTTP 429 hoặc 503, nếu server trả Retry-After, client nên tôn trọng hướng dẫn đó trong giới hạn timeout và policy của mình.

### 8.3. Retry budget

Retry budget giới hạn tổng số lần thử lại trong một khoảng thời gian hoặc tỷ lệ so với request gốc. Nếu mọi request đều retry nhiều lần, một sự cố nhỏ có thể biến thành retry storm.

Có thể giới hạn:

- Tối đa N lần retry cho một request/job.
- Tỷ lệ retry tối đa trên tổng request.
- Tổng thời gian retry của một job.
- Số job đồng thời đang retry đến một dependency.
- Số lần rerun thủ công trong một cửa sổ.

Retry budget giúp hệ thống thất bại có kiểm soát và bảo vệ dịch vụ phụ thuộc.

### 8.4. Không retry lỗi không thể tự phục hồi

Các lỗi như sai cú pháp, thiếu biến, permission denied, artifact không hợp lệ hoặc assertion sai thường không tự biến mất. Retry chỉ tạo thêm log và tải.

Nên phân loại error code hoặc response status theo tài liệu của công cụ. Không retry mọi mã HTTP 4xx/5xx theo một quy tắc chung: 429 có thể retry sau thời gian chờ; 401 có thể cần credential mới; 403 thường cần quyền; 404 có thể là sai resource hoặc eventual consistency tùy API.

## 9. Timeout, idempotency và thao tác an toàn khi retry

Timeout giới hạn thời gian chờ, nhưng không chứng minh thao tác ở server đã dừng. Một deploy API có thể đã áp dụng thay đổi rồi response bị mất. Nếu client retry một lệnh không idempotent, hệ thống có thể tạo tài nguyên hoặc release trùng.

Trước khi retry thao tác thay đổi, cần:

1. Xác định thao tác đã đến server hay chưa.
2. Truy vấn trạng thái hiện tại.
3. Dùng idempotency key hoặc release ID ổn định nếu API hỗ trợ.
4. Chỉ gửi lại khi có thể chứng minh thao tác chưa hoàn tất hoặc API bảo đảm idempotent.
5. Giữ một timeout tổng cho toàn bộ lần thử.

Ví dụ:

~~~text
request_id = release-2026-11-18-01
attempt 1: apply request_id
response: connection reset
query status by request_id
if status == SUCCEEDED:
    do not submit again
if status == RUNNING:
    continue polling
if status == NOT_FOUND and API guarantees idempotency:
    retry with the same request_id
otherwise:
    stop and investigate
~~~

Không tạo idempotency key mới cho mỗi lần retry nếu mục tiêu là nhận diện cùng một thao tác logic. Nếu mỗi lần thử có key khác nhau, server có thể coi chúng là các thao tác riêng.

## 10. Circuit breaker và giới hạn áp lực lên dependency

Circuit breaker là cơ chế tạm ngừng gọi một dependency khi tỷ lệ lỗi hoặc timeout vượt điều kiện đã định. Nó hữu ích khi dịch vụ phụ thuộc đang gặp sự cố kéo dài và retry liên tục có thể làm tình hình tệ hơn.

Ba trạng thái thường gặp:

- **Closed:** request được phép đi qua; hệ thống theo dõi lỗi.
- **Open:** tạm chặn request đến dependency trong một khoảng thời gian.
- **Half-open:** cho phép một số request thử để xác định dependency đã phục hồi chưa.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Lỗi vượt ngưỡng
    Open --> HalfOpen: Hết thời gian chờ
    HalfOpen --> Closed: Probe thành công
    HalfOpen --> Open: Probe thất bại
~~~

Circuit breaker thường nằm trong ứng dụng hoặc client gọi dịch vụ, còn retry policy có thể nằm ở client, job hoặc pipeline. Hai cơ chế cần phối hợp. Nếu circuit đang open, retry liên tục từ nhiều job thường không có ích.

Không nên dùng circuit breaker để che giấu dependency hỏng. Cần phát metric cho trạng thái breaker, số request bị từ chối, thời gian open và kết quả probe.

## 11. Xử lý lỗi kiểm thử và hạ tầng trong CI

Pipeline nên phân biệt kết quả test với trạng thái của runner và dịch vụ test.

Một số thực hành:

- Lưu JUnit/XML report, coverage và log ngay cả khi test thất bại.
- Ghi test name, seed, thời gian, runner image, runtime và commit SHA.
- Thu thập trạng thái container/service dependency khi integration test lỗi.
- Tách test suite nhanh khỏi test suite cần hạ tầng nặng.
- Dùng service container hoặc môi trường test cô lập khi phù hợp.
- Cleanup database, queue, file và container sau test.
- Giới hạn concurrency để tránh runner hoặc dependency test quá tải.
- Chỉ rerun test thất bại theo chính sách, không mặc định chạy lại cả suite.

### 11.1. Rerun test thất bại

Một số nền tảng hỗ trợ rerun failed jobs hoặc test retry. Cần lưu kết quả lần đầu và lần retry. Nếu lần đầu fail, lần sau pass, kết quả tổng không nên xóa lịch sử; hãy đánh dấu flaky hoặc intermittent và tạo dữ liệu cho việc điều tra.

Với test bảo vệ bảo mật, phân quyền hoặc tính đúng đắn dữ liệu, không nên cho phép một lần pass sau retry tự động xóa cảnh báo của lần fail đầu mà không review.

### 11.2. Kiểm tra runner trước khi quy lỗi cho code

Khi nhiều test không liên quan cùng timeout, kiểm tra runner:

- CPU throttling và memory pressure.
- Disk, inode và workspace.
- Process còn sót từ job trước.
- DNS, proxy và kết nối đến service test.
- Phiên bản runner image và toolchain.
- Thời điểm sự cố so với các job khác trên cùng pool.

Nếu runner persistent bị nhiễm trạng thái từ job trước, cần cleanup hoặc tái tạo runner. Không nên tiếp tục retry trên cùng máy mà không xác minh.

## 12. Ghi nhận lỗi và bằng chứng để truy vết

Mỗi lần thất bại nên có một bản ghi đủ để người khác tiếp tục điều tra mà không phải chạy lại chỉ để lấy log.

Các trường nên lưu:

- Pipeline run ID và job ID.
- Repository, branch, commit SHA và pull request.
- Stage, job, step và command thất bại.
- Exit code, signal hoặc HTTP status.
- Error class hoặc failure category.
- Runner ID/image, OS, runtime và toolchain version.
- Environment/config revision liên quan.
- Thời điểm bắt đầu, kết thúc và thời lượng.
- Test report, log và trace ID đã được làm sạch dữ liệu nhạy cảm.
- Số lần retry và kết quả mỗi lần.
- Nguyên nhân gốc, owner và hành động khắc phục nếu đã xác định.

### 12.1. Trạng thái phân loại có thể dùng

Có thể chuẩn hóa một số nhãn:

| Nhãn | Ý nghĩa |
|---|---|
| **SOURCE_FAILURE** | Lỗi source, dependency hoặc build definition |
| **TEST_FAILURE** | Assertion hoặc hành vi sản phẩm không đạt |
| **FLAKY_TEST** | Kết quả test không ổn định, cần điều tra |
| **INFRA_FAILURE** | Runner hoặc dịch vụ nền tảng gặp lỗi |
| **CONFIG_FAILURE** | Thiếu/sai giá trị, quyền, secret hoặc endpoint |
| **UNKNOWN** | Chưa đủ bằng chứng để phân loại |
| **RECOVERED_RETRY** | Retry sau lỗi tạm thời và đã thành công |
| **FIXED_AND_VERIFIED** | Đã sửa nguyên nhân và xác minh lại |

Nhãn nên mô tả bằng chứng và không thay thế phần nguyên nhân gốc. Một lỗi có thể mang TEST_FAILURE ở lớp quan sát và CONFIG_FAILURE ở nguyên nhân gốc. Nếu hệ thống hỗ trợ, hãy lưu cả hai trường.

### 12.2. Không đưa secret vào báo cáo

Trước khi upload log hoặc report, cần redact token, password, private key, cookie, connection string và payload nhạy cảm. Giữ tên biến hoặc secret reference có thể đủ để điều tra. Giới hạn quyền đọc artifact chứa log và áp dụng retention phù hợp.

## 13. Ví dụ chính sách phân loại và retry

Ví dụ YAML sau là cấu hình khái niệm, không phải schema của một nền tảng CI/CD cụ thể:

~~~yaml
failure_policy:
  source_failure:
    retry: false
    action: fix_source_or_dependency
    owner: code_owner

  test_failure:
    assertion:
      retry: false
      action: investigate_product_or_expectation
    flaky:
      diagnostic_reruns: 2
      preserve_first_result: true
      action: create_flaky_test_record

  infrastructure_failure:
    retryable:
      - network_reset
      - service_503
      - rate_limited
      - runner_terminated
    max_attempts: 3
    backoff: exponential
    jitter: full
    action_after_exhaustion: escalate_infrastructure

  configuration_failure:
    retry: false
    action: validate_config_identity_and_permissions

  common:
    total_timeout: 20m
    preserve_logs: true
    redact_secrets: true
    require_failure_category: true
~~~

Trong thực tế, cần ánh xạ category sang exit code, error signature hoặc response status của công cụ. Không nên chỉ phân loại bằng cách tìm chuỗi chữ trong log nếu có thể lấy mã lỗi hoặc trạng thái có cấu trúc.

## 14. Tình huống mẫu: integration test thất bại do database test

Giả sử pipeline của một dịch vụ đơn hàng chạy integration test. Nhiều test liên quan đến database cùng timeout, trong khi unit test và compile đều pass.

1. Xác định các test thất bại có chung dependency database.
2. Đọc log cho thấy test không nhận được kết nối trong thời hạn.
3. Kiểm tra runner: CPU và memory bình thường, disk còn đủ.
4. Kiểm tra service container: database mất nhiều thời gian khởi động và health check chưa đạt.
5. Xác định nguyên nhân là timeout setup của database test quá ngắn trong runner chậm hơn, không phải assertion của ứng dụng.
6. Điều chỉnh readiness wait theo điều kiện thực tế, có timeout tổng và log trạng thái.
7. Chạy lại integration suite trên runner tương đương.
8. Xác nhận database đạt health trước khi test bắt đầu và toàn bộ test pass.
9. Ghi failure category là INFRA_FAILURE hoặc TEST_ENVIRONMENT_FAILURE theo taxonomy của nhóm; ghi nguyên nhân cụ thể là service readiness timeout.
10. Theo dõi các lần chạy sau để xác nhận sự cố không lặp lại.

Nếu database đã sẵn sàng mà assertion về dữ liệu vẫn sai, cần chuyển điều tra sang source/test. Phân loại phải dựa trên bằng chứng, không dựa trên việc test có tên là integration test.

## 15. Lộ trình thực hành

Có thể thực hành trên một repository mẫu theo các bước:

1. **Thu thập baseline:** lấy một pipeline thành công và lưu log, test report, runner image, commit và thời gian chạy.
2. **Tạo lỗi source có kiểm soát:** làm một compile error hoặc unit assertion thất bại; xác nhận pipeline không retry tự động.
3. **Tạo test failure:** làm test assertion sai và xác nhận report chỉ ra test cùng expected/actual.
4. **Tạo flaky test:** tạo race hoặc phụ thuộc thứ tự trong môi trường thử nghiệm; chạy lặp và ghi nhận kết quả từng lần.
5. **Tạo lỗi hạ tầng:** làm service test không sẵn sàng hoặc mô phỏng network reset; xác nhận retry chỉ áp dụng với lỗi được cho phép.
6. **Tạo lỗi cấu hình:** bỏ một biến bắt buộc hoặc dùng endpoint sai; xác nhận validation dừng sớm và không lộ secret.
7. **Thiết lập retry policy:** cấu hình số lần tối đa, backoff, jitter và timeout tổng.
8. **Kiểm tra idempotency:** mô phỏng mất response sau một thao tác thay đổi và xác minh script truy vấn trạng thái trước khi gửi lại.
9. **Kiểm tra bằng chứng:** xác nhận log, report, category và retry history được lưu, secret đã redact.
10. **Viết runbook:** mô tả dấu hiệu, bằng chứng, owner và hành động cho từng nhóm lỗi.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Phân biệt được lỗi mã nguồn, kiểm thử, hạ tầng và cấu hình.
- Phân biệt triệu chứng với nguyên nhân gốc.
- Nhận biết flaky test và cách xác minh có kiểm soát.
- Xác định được lỗi nào retry được và lỗi nào cần sửa trước.
- Thiết lập retry có giới hạn với exponential backoff, jitter và timeout.
- Dùng idempotency để tránh lặp thao tác thay đổi ngoài ý muốn.
- Biết khi nào cần circuit breaker hoặc dừng retry.
- Thu thập log, report, runner metadata và retry history.
- Redact secret trước khi lưu bằng chứng.
- Ghi được category, owner, nguyên nhân và kết quả khắc phục.

## Kết luận

Phân loại lỗi là bước đầu tiên để xử lý pipeline thất bại một cách có hệ thống. Lỗi mã nguồn thường cần sửa source hoặc dependency; lỗi kiểm thử cần xác định regression hay flaky behavior; lỗi hạ tầng cần khôi phục runner hoặc dependency; lỗi cấu hình cần sửa giá trị, identity, quyền hoặc secret. Cùng một triệu chứng có thể bắt nguồn từ nhiều miền, vì vậy quyết định phải dựa trên bằng chứng.

Retry chỉ phù hợp với lỗi tạm thời và thao tác an toàn khi lặp. Exponential backoff, jitter, retry budget, timeout và idempotency giúp giới hạn tác động. Với lỗi không thể tự phục hồi, pipeline cần dừng, lưu bằng chứng và chuyển đúng owner. Khi mọi lần thất bại đều có category, lịch sử retry và kết quả xử lý, nhóm có thể giảm pipeline đỏ giả, rút ngắn thời gian điều tra và giữ độ tin cậy của luồng CI/CD.

