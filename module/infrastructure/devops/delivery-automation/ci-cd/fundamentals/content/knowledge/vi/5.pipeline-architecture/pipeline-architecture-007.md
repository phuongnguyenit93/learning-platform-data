# Tách kiểm tra nhanh với kiểm tra cần nhiều tài nguyên

Một pipeline CI/CD tốt phải trả lời nhanh câu hỏi liệu thay đổi có đang đi đúng hướng hay không, đồng thời vẫn có đủ kiểm tra sâu để bảo vệ chất lượng bản phát hành. Hai mục tiêu này có chi phí khác nhau. Kiểm tra định dạng, phân tích tĩnh và unit test thường chạy nhanh, ít phụ thuộc môi trường. Kiểm thử đầu cuối, kiểm thử tải, kiểm thử tích hợp nhiều dịch vụ hoặc quét bảo mật toàn diện có thể cần nhiều CPU, bộ nhớ, thời gian, máy chạy chuyên dụng và tài nguyên dùng chung.

Nếu đưa mọi kiểm tra vào cùng một luồng bắt buộc cho mỗi lần cập nhật pull request, phản hồi có thể chậm và hàng đợi CI tăng. Nếu loại bỏ kiểm tra nặng khỏi mọi cổng quyết định, lỗi quan trọng có thể đi xa hơn trước khi được phát hiện. Kiến trúc pipeline cần phân tầng công việc theo chi phí và rủi ro, chọn đúng thời điểm chạy, đồng thời quy định rõ kiểm tra nào phải chặn hợp nhất, kiểm tra nào phải đạt trước phát hành và kiểm tra nào có thể chạy định kỳ.

Bài học này trình bày cách tách luồng kiểm tra nhanh với luồng kiểm tra cần nhiều tài nguyên, tổ chức chúng thành các lane và job có quan hệ phụ thuộc, phân bổ runner, tối ưu thời gian phản hồi và đo hiệu quả mà không làm suy yếu cổng chất lượng.

## 1. Hiểu hai nhóm kiểm tra

**Kiểm tra nhanh (fast checks)** là những kiểm tra có thời gian chạy ngắn, chi phí tài nguyên thấp hoặc tương đối ổn định, thường có thể chạy trên mọi pull request. Chúng giúp phát hiện sớm lỗi phổ biến và cung cấp phản hồi trong thời gian đủ ngắn để nhà phát triển còn nhớ rõ thay đổi vừa thực hiện.

Ví dụ:

- Kiểm tra định dạng, quy ước và lint.
- Phân tích tĩnh hoặc kiểm tra kiểu dữ liệu.
- Kiểm thử đơn vị.
- Build module nhỏ hoặc build ứng dụng với cấu hình cơ bản.
- Kiểm tra cấu hình, schema và tính hợp lệ của tệp.
- Phát hiện secret bị commit và kiểm tra dependency ở phạm vi thay đổi.
- Một số contract test hoặc component test có thể chạy nhanh.

**Kiểm tra cần nhiều tài nguyên (resource-intensive checks)** là những kiểm tra tiêu thụ đáng kể thời gian hoặc tài nguyên tính toán, cần nhiều dịch vụ phụ thuộc, dữ liệu lớn, môi trường chuyên biệt hoặc nhiều biến thể cấu hình.

Ví dụ:

- Kiểm thử tích hợp khởi tạo nhiều dịch vụ, cơ sở dữ liệu hoặc message broker.
- Kiểm thử hệ thống và end-to-end trên nhiều luồng nghiệp vụ.
- Kiểm thử nhiều phiên bản runtime, hệ điều hành, trình duyệt hoặc kiến trúc CPU.
- Kiểm thử tải, stress test, soak test và benchmark.
- Quét bảo mật toàn diện trên repository, container image hoặc hệ thống phụ thuộc.
- Build nhiều module lớn hoặc tạo nhiều loại artifact.
- Kiểm thử migration trên bản sao dữ liệu lớn.
- Kiểm thử tương thích ngược và hồi quy trên toàn bộ sản phẩm.

Ranh giới không chỉ được xác định bằng số phút. Một job chạy hai phút nhưng cần thiết bị chuyên dụng, môi trường độc quyền hoặc nhiều dịch vụ dùng chung vẫn có thể có chi phí vận hành cao. Ngược lại, một job chạy lâu hơn nhưng chỉ dùng CPU và bộ nhớ ổn định có thể được xếp vào nhóm kiểm tra mở rộng mà không cần runner đặc biệt.

Vì vậy, khi phân loại một kiểm tra, hãy xem xét cả thời gian chạy, CPU, bộ nhớ, I/O, số dịch vụ phụ thuộc, thời gian chờ tài nguyên, chi phí môi trường và mức độ quan trọng của kết quả.

## 2. Mục tiêu kiến trúc: phản hồi nhanh và xác minh đủ sâu

Kiến trúc nên tạo ra hai khả năng bổ trợ:

1. **Vòng phản hồi nhanh:** kiểm tra các lỗi có xác suất cao và chi phí thấp ngay khi pull request được tạo hoặc cập nhật.
2. **Vòng xác minh mở rộng:** chạy các kiểm tra sâu trên thay đổi phù hợp, trạng thái nhánh chung, bản build phát hành hoặc theo lịch.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A["Pull request / cập nhật commit"] --> B["Fast lane"]
    B --> C{"Kiểm tra nhanh đạt?"}
    C -- "Không" --> D["Phản hồi lỗi cho tác giả"]
    D --> A
    C -- "Có" --> E["Phân tích phạm vi thay đổi"]
    E --> F["Targeted heavy checks"]
    F --> G{"Kiểm tra bắt buộc theo rủi ro đạt?"}
    G -- "Không" --> D
    G -- "Có" --> H["Review và hợp nhất"]
    H --> I["Pipeline nhánh dùng chung"]
    I --> J["Full integration / regression"]
    J --> K["Build và lưu artifact"]
    K --> L["Kiểm chứng môi trường"]
    M["Lịch định kỳ"] --> N["Full matrix / load / scan"]
    N --> O["Báo cáo và tạo công việc xử lý"]
    P["Yêu cầu phát hành"] --> Q["Release validation"]
    Q --> R{"Các cổng phát hành đạt?"}
    L --> R
    O --> R
    R -- "Đạt" --> S["Promote và triển khai"]
    R -- "Không đạt" --> T["Dừng phát hành, điều tra"]
~~~

Sơ đồ thể hiện một mô hình tham khảo. Không phải mọi dự án đều cần chạy toàn bộ kiểm thử tải hoặc full matrix trước mỗi release. Các cổng thực tế phải dựa trên rủi ro sản phẩm, yêu cầu vận hành và chính sách phát hành.

Điểm quan trọng là mỗi nhóm kiểm tra có một **thời điểm phải hoàn thành**. Nếu một kiểm tra bảo mật hoặc tương thích là điều kiện bắt buộc để phát hành, việc chạy nó theo lịch không đủ để thay thế cổng trước release. Ngược lại, một benchmark dài hạn dùng để theo dõi xu hướng có thể chạy định kỳ và không cần chặn mọi pull request.

## 3. Phân loại kiểm tra theo chi phí và rủi ro

Có thể bắt đầu bằng bảng phân loại sau rồi điều chỉnh theo số liệu thực tế của repository:

| Loại kiểm tra | Chi phí thường gặp | Thời điểm phù hợp | Vai trò cổng |
|---|---|---|---|
| Format, lint, kiểm tra cấu hình | Thấp | Mỗi pull request | Thường bắt buộc trước merge |
| Static analysis, type check | Thấp đến trung bình | Mỗi pull request | Bắt buộc theo chính sách |
| Unit test | Thấp đến trung bình | Mỗi pull request và nhánh chính | Thường bắt buộc |
| Build ứng dụng hoặc module bị ảnh hưởng | Trung bình | Pull request và nhánh chính | Bắt buộc nếu đầu ra cần build |
| Component test | Trung bình | Pull request theo phạm vi thay đổi | Bắt buộc với thành phần liên quan |
| Integration test nhiều dịch vụ | Trung bình đến cao | Pull request chọn lọc, sau merge | Bắt buộc trước phát hành nếu bao phủ rủi ro quan trọng |
| End-to-end toàn hệ thống | Cao | Nhánh chính, staging hoặc release candidate | Chặn phát hành theo mức độ quan trọng |
| Cross-browser / cross-platform matrix | Cao | Pull request theo thay đổi UI, nhánh chính hoặc lịch | Chọn matrix tối thiểu trước merge, mở rộng sau |
| Full security scan | Trung bình đến cao | Nhánh chính và trước release | Cổng bắt buộc theo chính sách rủi ro |
| Load / stress / soak test | Cao đến rất cao | Trước release, theo lịch hoặc khi thay đổi hiệu năng | Chặn release khi có ngưỡng hiệu năng bắt buộc |
| Kiểm thử migration trên dữ liệu lớn | Cao | Pull request liên quan schema, staging hoặc release | Bắt buộc trước thay đổi dữ liệu nhạy cảm |
| Full regression suite | Cao | Nhánh chính, nightly hoặc release candidate | Cổng theo chiến lược phát hành |

Bảng này là điểm khởi đầu, không phải quy tắc cứng. Ví dụ, một dự án thư viện nhỏ có thể chạy toàn bộ test trong vài phút, nên không cần nhiều lane. Một hệ thống nhiều dịch vụ có thể cần chọn kiểm thử theo service và chạy full suite trên nhánh chính.

### 3.1. Đánh giá chi phí thực tế

Để tránh phân loại theo cảm tính, hãy thu thập:

- Thời gian chạy p50 và p90 của job, không chỉ thời gian trung bình.
- Thời gian chờ runner trước khi job bắt đầu.
- CPU, bộ nhớ đỉnh và dung lượng đĩa.
- Số lượng service, container hoặc máy ảo cần khởi tạo.
- Thời gian tạo dữ liệu và dọn dẹp môi trường.
- Tỷ lệ job thất bại do sản phẩm, do test không ổn định và do hạ tầng.
- Chi phí hoặc giới hạn quota của runner và dịch vụ ngoài.
- Mức độ nghiêm trọng nếu kiểm tra bị trì hoãn đến giai đoạn sau.

Thời gian chạy và thời gian chờ là hai đại lượng khác nhau. Một job có thể chỉ chạy ba phút nhưng chờ runner hai mươi phút do pool thiếu tài nguyên. Nếu chỉ tối ưu mã kiểm thử, nhóm sẽ không giải quyết được nút thắt thực tế.

### 3.2. Không đồng nhất kiểm tra nhanh với kiểm tra ít quan trọng

Một kiểm tra nhanh có thể là cổng bảo vệ rất quan trọng, như phát hiện secret, kiểm tra license hoặc ngăn dependency bị cấm. Một kiểm thử nặng cũng có thể là điều kiện bắt buộc trước khi phát hành, như kiểm thử migration hoặc tải cho một dịch vụ giao dịch.

Hãy phân loại theo hai trục riêng:

- **Chi phí thực thi:** thấp, trung bình hoặc cao.
- **Mức độ rủi ro được kiểm soát:** thấp, trung bình hoặc cao.

Một kiểm tra có chi phí cao và rủi ro cao cần được tối ưu để chạy có mục tiêu, cấp đủ tài nguyên và đặt trước cổng quyết định phù hợp. Không nên loại nó khỏi quy trình chỉ vì thời gian chạy dài.

## 4. Tổ chức pipeline thành các lane

Một lane là một luồng công việc có mục tiêu và đặc tính tài nguyên tương đối rõ. Lane không nhất thiết là một pipeline độc lập; nó có thể là một nhóm stage hoặc job trong cùng workflow.

### Fast lane

Fast lane nhận thay đổi mới và chạy các kiểm tra có phản hồi nhanh. Mục tiêu là trả lời sớm liệu thay đổi có đủ điều kiện tiếp tục review và tích hợp hay không.

Thông thường fast lane gồm:

- Checkout mã nguồn và khôi phục cache an toàn.
- Kiểm tra định dạng, lint và cấu hình.
- Phân tích tĩnh và kiểm tra kiểu.
- Unit test.
- Build nhanh hoặc build module bị ảnh hưởng.
- Các kiểm tra bảo mật nhanh có tính chặn.

Fast lane nên có timeout hợp lý, log dễ đọc và trạng thái check rõ ràng. Khi một bước nền tảng thất bại, pipeline cần phân biệt lỗi mã nguồn với lỗi runner hoặc dịch vụ phụ thuộc.

### Targeted lane

Targeted lane chạy các kiểm tra cần nhiều tài nguyên nhưng chỉ trên phần bị ảnh hưởng hoặc rủi ro cụ thể. Ví dụ, một thay đổi ở module thanh toán có thể kích hoạt integration test của thanh toán, contract test với đơn hàng và một số luồng end-to-end liên quan.

Lane này giúp tránh chạy toàn bộ hệ thống cho mọi thay đổi. Việc chọn phạm vi phải dựa trên dependency graph, cấu hình module, nhãn thay đổi hoặc quy tắc được quản lý. Khi không xác định được phạm vi an toàn, pipeline nên mở rộng sang bộ kiểm tra đầy đủ đã quy định.

### Full validation lane

Full validation lane chạy bộ kiểm tra rộng trên trạng thái nhánh dùng chung hoặc release candidate. Nó có thể bao gồm full regression, integration test toàn hệ thống, ma trận runtime và quét bảo mật sâu.

Lane này thường có thể chạy sau merge, theo lịch hoặc trước release. Các kiểm tra được xem là cổng phát hành phải hoàn thành trước khi promote artifact đến môi trường đích.

### Scheduled lane

Scheduled lane chạy các tác vụ không cần chờ mỗi pull request, chẳng hạn:

- Full regression trên nhánh chính.
- Kiểm thử tải và soak test.
- Quét dependency toàn diện theo lịch.
- Kiểm thử nhiều phiên bản runtime hoặc nền tảng.
- Kiểm tra tương thích dài hạn và benchmark.
- Phát hiện xu hướng tăng thời gian build hoặc giảm hiệu năng.

Kết quả scheduled lane cần được theo dõi và có người chịu trách nhiệm. Nếu một lỗi được phát hiện nhưng không tạo cảnh báo hoặc công việc xử lý, việc chạy định kỳ không đem lại giá trị bảo vệ thực tế.

### Release lane

Release lane xác nhận bản phát hành cụ thể. Nó cần kiểm tra đúng artifact dự kiến triển khai, metadata, chữ ký hoặc provenance nếu có, cấu hình môi trường, các kiểm thử chấp nhận và tiêu chí vận hành.

Không nên chỉ dựa vào kết quả của một pipeline chạy trên commit gần giống. Cần đối chiếu commit SHA và artifact digest để bảo đảm bản đã kiểm tra chính là bản sẽ được phát hành.

## 5. Thiết kế quan hệ phụ thuộc trong DAG

Pipeline hiện đại thường chạy các job theo đồ thị phụ thuộc (DAG). Những job độc lập có thể chạy song song; job chỉ bắt đầu khi các điều kiện đầu vào đã sẵn sàng.

Ví dụ:

~~~mermaid
flowchart TD
    A["Checkout + chuẩn bị dependency"] --> B["Lint / static analysis"]
    A --> C["Unit tests"]
    A --> D["Build module thay đổi"]
    B --> E{"Fast gate"}
    C --> E
    D --> E
    E --> F["Chọn phạm vi kiểm thử"]
    F --> G["Integration test service A"]
    F --> H["Integration test service B"]
    F --> I["Contract tests"]
    G --> J{"Targeted gate"}
    H --> J
    I --> J
    J --> K["Review / merge"]
    K --> L["Full regression"]
    K --> M["Security scan artifact"]
    L --> N["Release candidate gate"]
    M --> N
    N --> O["Publish / promote artifact"]
~~~

Một số nguyên tắc khi xây dựng DAG:

- Khai báo dependency thực sự giữa các job; không nối tuần tự chỉ vì dễ viết.
- Chạy song song các kiểm tra độc lập nếu runner và dịch vụ phụ thuộc đủ khả năng.
- Tránh để job nặng chiếm runner cần thiết cho fast lane.
- Dùng gate tổng hợp để xác định rõ điều kiện tiếp tục.
- Khi một job bắt buộc thất bại, dừng các job phụ thuộc vào kết quả đó.
- Cho phép thu thập log và báo cáo từ các job đã chạy dù một job khác thất bại.
- Không để bước publish hoặc deploy chạy khi kiểm tra bắt buộc chưa đạt.

Song song hóa không phải lúc nào cũng làm pipeline nhanh hơn. Nếu nhiều job đồng thời cùng khởi tạo cơ sở dữ liệu, tải image hoặc gọi một sandbox dùng chung, thời gian có thể tăng do tranh chấp tài nguyên. Cần đo tổng thời gian và thời gian chờ của từng job sau khi thay đổi mức song song.

## 6. Ví dụ cấu hình pipeline theo nhiều nhóm tài nguyên

Ví dụ dưới đây là mô hình khái niệm để minh họa cách phân chia lane, trigger và resource class. Nó không phải cú pháp thực thi của GitHub Actions, GitLab CI hay Jenkins:

~~~yaml
pipeline:
  pull_request:
    fast_lane:
      runner: standard
      required: true
      timeout: short
      jobs:
        - lint
        - static_analysis
        - unit_tests
        - build_affected_modules

    targeted_lane:
      runner: integration
      required_when: affected_services_detected
      timeout: medium
      jobs:
        - affected_integration_tests
        - contract_tests
        - focused_end_to_end_tests

  push_to_shared_branch:
    validation_lane:
      runner: integration
      required_before_artifact: true
      jobs:
        - full_integration_tests
        - regression_subset

    package_lane:
      needs: [validation_lane]
      runner: standard
      jobs:
        - build_release_artifact
        - calculate_digest
        - publish_artifact

  schedule:
    full_validation:
      runner: high_memory
      cadence: nightly
      jobs:
        - full_regression_matrix
        - cross_platform_tests
        - dependency_full_scan

    performance:
      runner: performance
      cadence: weekly
      jobs:
        - load_tests
        - stress_tests
        - soak_tests

  release:
    release_gate:
      needs: [package_lane]
      runner: integration
      jobs:
        - verify_artifact_provenance
        - release_acceptance_tests
        - deployment_smoke_tests
~~~

Khi triển khai thật, hãy thay các tên runner, trigger và điều kiện bằng cấu hình cụ thể của nền tảng. Đặc biệt, không coi các trường như required, resource class hoặc cadence trong ví dụ là cú pháp tiêu chuẩn.

## 7. Chọn kiểm tra theo phạm vi thay đổi

Selective testing là cách chỉ chạy các kiểm tra liên quan đến phần mã nguồn bị thay đổi. Đây là một kỹ thuật quan trọng để giảm thời gian và chi phí, nhất là trong monorepo hoặc hệ thống có nhiều service.

Có thể xác định phạm vi bằng:

- Đường dẫn file thay đổi.
- Module hoặc service sở hữu file.
- Dependency graph giữa module.
- Nhãn hoặc metadata trên pull request.
- Danh sách test liên kết với thành phần.
- Phân tích thay đổi API, schema hoặc cấu hình triển khai.

Ví dụ, thay đổi chỉ ở giao diện có thể kích hoạt lint, unit test UI và một số browser test. Thay đổi thư viện dùng chung có thể kích hoạt test của mọi module phụ thuộc. Thay đổi pipeline, build script hoặc dependency lockfile có thể yêu cầu chạy lại phạm vi rộng hơn.

### 7.1. Xây dựng quy tắc ảnh hưởng

Một bản đồ ảnh hưởng có thể mô tả:

| Vùng thay đổi | Kiểm tra có thể kích hoạt |
|---|---|
| Module giao diện | UI unit test, component test, browser smoke test |
| API công khai | Contract test, integration test của consumer |
| Thư viện dùng chung | Test của module phụ thuộc và build toàn bộ liên quan |
| Schema cơ sở dữ liệu | Migration test, integration test, tương thích phiên bản |
| Cấu hình build hoặc dependency | Build và test rộng hơn |
| Dockerfile hoặc container base image | Build image, scan image, smoke test container |
| Pipeline hoặc script triển khai | Kiểm tra cấu hình, pipeline validation, thử nghiệm deploy an toàn |
| Không xác định được vùng ảnh hưởng | Chạy bộ kiểm tra rộng theo chính sách |

### 7.2. Tránh bỏ sót do bộ lọc thay đổi

Path filter đơn giản có thể bỏ qua rủi ro nếu không tính đến:

- Module dùng chung hoặc dependency gián tiếp.
- Tệp cấu hình toàn cục.
- Build script và plugin.
- Generated code hoặc schema được dùng ở nhiều nơi.
- Thay đổi trong workflow CI/CD.
- Dependency lockfile hoặc phiên bản toolchain.
- Tệp bị đổi tên, di chuyển hoặc xóa.

Cần có quy tắc fallback. Nếu công cụ không xác định được ảnh hưởng, nếu dependency graph lỗi hoặc nếu thay đổi thuộc vùng nền tảng, hãy chạy bộ kiểm tra rộng hơn. Tối ưu thời gian không được dựa trên giả định rằng mọi thay đổi đều có thể phân loại chính xác.

### 7.3. Kết hợp chọn lọc với cổng bắt buộc

Một số kiểm tra có thể chỉ chạy khi vùng liên quan thay đổi. Tuy nhiên, trạng thái "không cần chạy" phải khác với trạng thái "đã chạy và đạt". Dashboard hoặc check tổng hợp cần thể hiện rõ lý do job được bỏ qua, phạm vi được đánh giá và quy tắc đã áp dụng.

Với thay đổi có rủi ro cao, có thể yêu cầu người review xác nhận phạm vi test hoặc kích hoạt thêm bộ kiểm tra. Cơ chế này cần được quản lý rõ để tránh biến nhãn tùy ý thành cách bỏ qua kiểm tra.

## 8. Phân bổ runner và giới hạn tài nguyên

Runner là máy hoặc môi trường thực thi job CI. Việc tách nhóm runner giúp job nặng không làm chậm các kiểm tra cần phản hồi nhanh.

Một mô hình phân bổ tham khảo:

| Nhóm runner | Đặc điểm | Công việc phù hợp |
|---|---|---|
| Standard | CPU và bộ nhớ vừa phải, khởi tạo nhanh | Lint, static analysis, unit test, build nhỏ |
| Integration | Có thể chạy container và nhiều service phụ thuộc | Integration test, contract test, component test |
| High-memory / large CPU | Tài nguyên tính toán lớn | Full regression, build lớn, phân tích dữ liệu |
| Performance | Môi trường ổn định, ít nhiễu, tài nguyên được kiểm soát | Load test, stress test, benchmark |
| Specialized | Có thiết bị, runtime hoặc nền tảng đặc thù | Mobile, GPU, cross-platform hoặc hardware test |

Không phải tổ chức nào cũng cần nhiều loại runner vật lý. Có thể dùng cùng hạ tầng với các giới hạn CPU, memory, concurrency và queue khác nhau. Điều quan trọng là fast lane có đủ năng lực để phản hồi nhanh trong giờ cao điểm.

### 8.1. Kiểm soát mức song song

Nếu số job nặng tăng không giới hạn, hệ thống có thể gặp:

- Hết runner và tăng thời gian chờ.
- Cạn CPU hoặc bộ nhớ trên máy chạy.
- Quá tải cơ sở dữ liệu, registry hoặc dịch vụ test.
- Va chạm dữ liệu giữa các job.
- Tăng chi phí cloud hoặc vượt quota.
- Benchmark thiếu ổn định do các job khác gây nhiễu.

Nên đặt concurrency limit theo nhóm tài nguyên, giới hạn số môi trường tạm được tạo đồng thời và dùng hàng đợi riêng cho tác vụ performance. Các job cần kết quả đo hiệu năng đáng tin cậy nên chạy trên môi trường có tải nền được kiểm soát.

### 8.2. Cô lập môi trường và dữ liệu

Mỗi job tích hợp nên có dữ liệu hoặc namespace riêng khi có thể. Nếu nhiều job cùng ghi vào một cơ sở dữ liệu test, kết quả có thể thất thường và khó tái hiện. Hãy tạo fixture tối thiểu, làm sạch dữ liệu sau test và có timeout cho dịch vụ phụ thuộc.

Với kiểm thử tải, không nên dùng chung môi trường với kiểm thử chức năng thông thường vì tải nhân tạo có thể làm sai kết quả hoặc gây ảnh hưởng các job khác.

## 9. Tối ưu thời gian mà vẫn giữ độ tin cậy

### Chạy song song theo dependency

Chia test thành các shard hoặc nhóm độc lập. Job tổng hợp chờ các kết quả bắt buộc. Cách này hữu ích khi một bộ test lớn có thể tách thành nhiều phần mà không chia sẻ trạng thái.

### Chia shard theo thời gian lịch sử

Không chia đều số lượng test nếu mỗi test có thời gian chạy rất khác nhau. Dùng thời gian chạy lịch sử để phân bổ shard tương đối cân bằng. Theo dõi shard chậm nhất vì nó thường quyết định thời điểm gate hoàn tất.

### Dùng cache có khóa chính xác

Cache dependency và build output có thể giảm thời gian đáng kể. Cache key nên bao gồm các đầu vào ảnh hưởng đến kết quả như lockfile, phiên bản toolchain, cấu hình build và hệ điều hành. Không dùng cache cũ khi đầu vào đã thay đổi.

Cache là tối ưu hiệu năng, không phải nguồn chân lý. Khi cần xác minh một lỗi nghi ngờ do cache, pipeline nên có cách chạy sạch để so sánh.

### Tái sử dụng artifact và môi trường

Nếu các bước sau chỉ cần kiểm thử cùng một đầu ra, hãy build một lần rồi truyền artifact giữa các job. Tránh build lại khác cấu hình ở từng lane. Với môi trường test, có thể dùng image đã chuẩn hóa hoặc snapshot khi cơ chế đó bảo đảm tính cô lập.

### Dừng công việc đã lỗi thời

Khi một pull request có commit mới, các job của commit cũ có thể bị hủy nếu không còn giá trị. Tuy nhiên, cần giữ lại những job đang phục vụ điều tra hoặc tác vụ release đã được xác nhận. Quy tắc hủy phải tránh để job cũ tiếp tục ghi đè trạng thái hoặc môi trường của job mới.

### Tránh retry vô hạn

Retry chỉ phù hợp khi có bằng chứng về lỗi tạm thời của hạ tầng hoặc khi test được thiết kế để chịu retry. Nếu test không ổn định, hãy ghi nhận số lần retry, kết quả ban đầu và kết quả cuối. Một job đạt sau nhiều lần thử vẫn là tín hiệu cần điều tra.

### Giảm công việc khởi tạo

Dùng dependency service được chuẩn hóa, image đã build, fixture nhỏ và quy trình setup có thể tái sử dụng. Đừng tải lại dữ liệu lớn hoặc cài công cụ giống nhau ở mọi job nếu có thể dùng image runner đã được quản lý phiên bản.

## 10. Đặt cổng chất lượng đúng thời điểm

Việc chia lane chỉ có ý nghĩa khi nhóm xác định rõ điều kiện để tiếp tục.

| Cổng | Thời điểm | Ví dụ điều kiện |
|---|---|---|
| Fast gate | Trước review/merge | Lint, static analysis và unit test bắt buộc đạt |
| Targeted gate | Trước merge với thay đổi có ảnh hưởng | Integration hoặc contract test liên quan đạt |
| Integrated gate | Sau merge | Build và kiểm thử trên commit nhánh chung đạt |
| Artifact gate | Trước publish/promote | Artifact hợp lệ, có digest và metadata |
| Release gate | Trước triển khai đích | Full test theo rủi ro, scan và phê duyệt cần thiết đạt |
| Runtime gate | Sau triển khai | Health check, smoke test và chỉ số vận hành trong ngưỡng |

Một số kiểm tra có thể chạy ở nhiều cổng với phạm vi khác nhau. Ví dụ, pull request chạy contract test của API bị thay đổi; sau merge chạy contract test với toàn bộ consumer; trước release chạy thêm kiểm tra tương thích ngược.

Không nên đánh đồng việc job chạy theo lịch với việc cổng đã đạt. Nếu full security scan là điều kiện bắt buộc của bản phát hành, release pipeline phải kiểm tra kết quả gần nhất còn hợp lệ và gắn với đúng artifact hoặc commit. Nếu kết quả đã cũ hoặc đầu vào thay đổi, cần chạy lại.

## 11. Bảo mật khi dùng runner cho kiểm tra nặng

Một số kiểm thử tích hợp cần quyền truy cập mạng, container đặc quyền, dịch vụ cloud hoặc secret. Job nặng không nên tự động nhận quyền cao hơn chỉ vì cần nhiều tài nguyên.

Áp dụng các nguyên tắc:

- Cấp quyền tối thiểu theo từng job.
- Tách runner cho mã nguồn chưa tin cậy và runner có quyền triển khai.
- Không cấp secret production cho pipeline pull request từ fork hoặc nguồn chưa được tin cậy.
- Giới hạn mạng và quyền ghi của runner khi kiểm thử.
- Dùng thông tin xác thực ngắn hạn nếu nền tảng hỗ trợ.
- Hủy môi trường tạm và thu hồi credential sau khi job kết thúc.
- Ghi log truy cập và phiên bản image runner để điều tra.

Nếu cần kiểm thử trên dữ liệu gần với production, hãy dùng bản sao đã được xử lý theo chính sách dữ liệu. Không sao chép bí mật hoặc dữ liệu nhạy cảm vào môi trường CI chỉ để kiểm thử thuận tiện.

## 12. Xử lý lỗi và kết quả không ổn định

Khi fast lane thất bại, phản hồi nên chỉ ra bước lỗi và gắn với commit hiện tại. Nhà phát triển cần biết lỗi có thể sửa ngay hay cần người vận hành kiểm tra runner.

Khi targeted hoặc full validation thất bại, cần xác định phạm vi ảnh hưởng và liệu lỗi có chặn merge, publish hoặc release. Một kiểm tra nặng không đạt có thể đến từ nhiều nguyên nhân:

- Lỗi chức năng chỉ xuất hiện khi các dịch vụ tương tác.
- Môi trường test không sẵn sàng hoặc dữ liệu không hợp lệ.
- Runner thiếu CPU, bộ nhớ hoặc dung lượng.
- Dịch vụ phụ thuộc bị giới hạn tốc độ hoặc mất kết nối.
- Test không ổn định do thời gian, thứ tự chạy hoặc chia sẻ dữ liệu.
- Thay đổi hiệu năng làm vượt ngưỡng đã thống nhất.

Log nên ghi rõ commit, pipeline run, test shard, cấu hình môi trường, resource class và thời gian chờ. Điều này giúp phân biệt lỗi sản phẩm với lỗi hạ tầng.

Với flaky test, cần có chủ sở hữu và thời hạn xử lý. Nếu phải tạm thời đưa test ra khỏi gate, ngoại lệ cần có lý do, phạm vi và thời điểm khôi phục. Không nên âm thầm biến một kiểm tra bắt buộc thành cảnh báo vô thời hạn.

## 13. Đo lường hiệu quả kiến trúc pipeline

Để biết việc tách lane có hiệu quả hay không, hãy đo cả tốc độ, chi phí và chất lượng:

| Chỉ số | Ý nghĩa | Dấu hiệu cần xem xét |
|---|---|---|
| PR feedback time p50/p90 | Thời gian nhận kết quả fast gate | p90 tăng có thể do runner queue hoặc job chậm |
| Queue wait time | Thời gian chờ runner | Cao cho thấy thiếu năng lực hoặc phân bổ pool chưa hợp lý |
| Job duration p50/p90 | Thời gian thực thi thực tế | Job kéo dài có thể cần chia shard hoặc tối ưu setup |
| Runner utilization | Mức sử dụng tài nguyên | Quá cao gây chờ; quá thấp có thể là phân bổ dư |
| Cache hit rate | Tỷ lệ cache được dùng hợp lệ | Thấp có thể do key thay đổi quá thường xuyên |
| Flaky test rate | Tỷ lệ test không ổn định | Cao làm giảm độ tin cậy của gate |
| Compute cost per change | Chi phí CI cho mỗi thay đổi | Tăng nhanh có thể do chạy lặp hoặc matrix quá rộng |
| Heavy-check detection rate | Lỗi quan trọng được phát hiện ở lane mở rộng | Thấp bất thường có thể chỉ ra khoảng trống test |
| Defect escape rate | Lỗi lọt đến môi trường sau hoặc người dùng | Cần xem lại phạm vi và thời điểm kiểm tra |

Không nên đặt mục tiêu giảm thời gian pipeline bằng mọi giá. Một thay đổi kiến trúc tốt cần cải thiện thời gian phản hồi mà vẫn giữ hoặc nâng khả năng phát hiện lỗi quan trọng. Cũng không nên đánh giá bằng tổng thời gian job đơn thuần: chạy mười job song song trong hai phút có thể tiêu thụ nhiều tài nguyên hơn một job chạy mười phút.

## 14. Tình huống mẫu: monorepo có nhiều module

Giả sử một monorepo chứa ba nhóm: API, giao diện web và thư viện dùng chung. Một pull request chỉ sửa CSS của giao diện.

Một pipeline không phân tầng có thể build mọi module, khởi tạo toàn bộ dịch vụ, chạy full end-to-end suite và quét toàn bộ ma trận runtime cho mỗi lần cập nhật. Phản hồi trở nên chậm dù phần lớn kiểm tra không liên quan đến thay đổi.

Một kiến trúc phân tầng có thể hoạt động như sau:

1. Fast lane chạy format, lint, static analysis, unit test UI và build giao diện.
2. Change analysis xác định thay đổi chỉ nằm trong UI, không chạm thư viện dùng chung hoặc API.
3. Targeted lane chạy component test và một số browser smoke test cho giao diện.
4. Khi pull request đạt và được hợp nhất, pipeline nhánh chính chạy integration test của giao diện với API đã triển khai trong môi trường test.
5. Full regression và cross-browser matrix chạy theo lịch hoặc trước release candidate.
6. Nếu pull request sửa thư viện dùng chung, dependency graph mở rộng phạm vi sang API và UI; nếu không xác định được ảnh hưởng, pipeline chạy bộ test rộng hơn.
7. Artifact được tạo từ commit tích hợp đã xác minh và được promote qua môi trường.

Cách tổ chức này giảm công việc không liên quan cho thay đổi nhỏ, đồng thời giữ các kiểm tra rộng ở thời điểm cần thiết. Nếu thay đổi ảnh hưởng một luồng nghiệp vụ quan trọng, targeted lane có thể vẫn phải chạy bộ end-to-end liên quan trước khi cho phép merge.

## 15. Lộ trình thực hành

Có thể áp dụng trên một repository hiện có theo các bước:

1. **Lập danh sách kiểm tra:** thu thập toàn bộ job hiện tại, mục đích, thời gian chạy, thời gian chờ, tài nguyên và mức độ rủi ro.
2. **Phân loại:** gắn nhãn fast, targeted, full, scheduled hoặc release; ghi rõ lý do và gate mà job bảo vệ.
3. **Tạo fast lane:** gom các kiểm tra nhanh, ổn định và cần thiết cho mọi thay đổi vào luồng phản hồi sớm.
4. **Tách runner:** xác định pool hoặc resource class cho integration, full regression và performance test.
5. **Xây dựng dependency graph:** khai báo module, service và test bị ảnh hưởng bởi từng vùng mã nguồn.
6. **Thêm targeted lane:** chạy kiểm tra nặng theo phạm vi thay đổi và có fallback khi không xác định được phạm vi.
7. **Tổ chức full validation:** chạy kiểm thử toàn diện trên nhánh chung, theo lịch hoặc trước release theo chính sách.
8. **Thiết lập gate:** chỉ rõ kiểm tra nào phải đạt trước merge, trước publish và trước triển khai môi trường đích.
9. **Đo trước và sau:** so sánh PR feedback p50/p90, queue wait, chi phí runner, flaky test và lỗi lọt.
10. **Diễn tập lỗi:** tạo một lỗi chỉ xuất hiện trong integration test hoặc performance test, xác nhận pipeline dừng đúng bước và lưu đủ bằng chứng.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Phân biệt được chi phí thực thi với mức độ rủi ro của một kiểm tra.
- Phân loại được fast, targeted, full, scheduled và release checks.
- Thiết kế được DAG cho các job độc lập và phụ thuộc.
- Phân bổ runner và giới hạn concurrency phù hợp.
- Chọn được test theo vùng thay đổi và có fallback an toàn.
- Đặt quality gate đúng thời điểm trước merge, publish và release.
- Tối ưu cache, sharding và môi trường mà vẫn giữ kết quả có thể tin cậy.
- Đo được thời gian phản hồi, thời gian chờ, chi phí và độ ổn định của pipeline.

## Kết luận

Tách kiểm tra nhanh với kiểm tra cần nhiều tài nguyên là một quyết định kiến trúc về thời điểm phản hồi, năng lực thực thi và mức độ rủi ro. Fast lane giúp nhà phát triển nhận tín hiệu sớm. Targeted lane tập trung tài nguyên vào phần thay đổi có ảnh hưởng. Full validation và scheduled lane xác minh hệ thống trên phạm vi rộng. Release lane bảo đảm đúng artifact đã vượt qua các điều kiện cần thiết trước khi đến môi trường đích.

Khi các lane có mục tiêu, đầu vào, tài nguyên, quan hệ phụ thuộc và cổng quyết định rõ ràng, pipeline có thể phản hồi nhanh hơn mà vẫn giữ được chiều sâu kiểm chứng. Hiệu quả cần được xác nhận bằng số liệu về thời gian, hàng đợi, chi phí, độ ổn định và lỗi lọt, sau đó điều chỉnh theo kiến trúc và rủi ro thực tế của sản phẩm.

