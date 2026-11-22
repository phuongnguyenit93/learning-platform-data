# Mô tả phụ thuộc giữa các công việc bằng đồ thị có hướng

Một pipeline CI/CD thường gồm nhiều công việc: biên dịch mã nguồn, kiểm tra định dạng, chạy unit test, đóng gói artifact, kiểm thử tích hợp, quét bảo mật và triển khai. Nếu mô tả pipeline chỉ bằng một danh sách tuần tự, các công việc độc lập sẽ phải chờ nhau dù không cần thiết. Nếu cho mọi công việc chạy song song mà không khai báo phụ thuộc, pipeline có thể chạy kiểm thử trước khi artifact sẵn sàng hoặc triển khai trước khi quality gate hoàn tất.

Đồ thị có hướng giúp mô tả rõ công việc nào phải hoàn tất trước công việc nào. Trong pipeline, mô hình thường dùng là đồ thị có hướng không chu trình (Directed Acyclic Graph, viết tắt là DAG). Mỗi đỉnh biểu diễn một công việc; mỗi cạnh biểu diễn quan hệ phụ thuộc và thứ tự thực thi. Từ đồ thị này, hệ thống có thể xác định công việc đủ điều kiện chạy, tận dụng khả năng song song, chặn các bước phụ thuộc khi có lỗi và giúp nhóm hiểu đường đi của một thay đổi từ mã nguồn đến môi trường triển khai.

## 1. Đồ thị có hướng trong pipeline là gì?

Đồ thị có hướng gồm hai thành phần:

- **Đỉnh (vertex hoặc node):** đại diện cho một đối tượng trong quy trình, thường là job hoặc task như compile, unit_test, package, integration_test, deploy.
- **Cạnh có hướng (directed edge):** biểu diễn quan hệ thứ tự hoặc phụ thuộc giữa hai đỉnh.

Trong bài toán pipeline, quy ước dễ đọc là cạnh A → B có nghĩa **B phụ thuộc vào A**: A phải hoàn tất thành công trước khi B được phép chạy. Ví dụ, package cần kết quả compile nên có cạnh compile → package.

Một DAG là đồ thị có hướng không chứa chu trình. Điều đó có nghĩa không thể bắt đầu từ một đỉnh, đi theo các cạnh có hướng rồi quay lại chính đỉnh ban đầu. Pipeline cần có đặc tính này vì một công việc không thể chờ chính nó hoàn tất thông qua một chuỗi phụ thuộc.

Ví dụ đơn giản:

~~~text
source
  |
  v
compile -----> package
  |
  v
unit_test
~~~

Trong hình này, compile phải chạy trước package và unit_test. Nếu package cần cả compile lẫn unit_test, ta thêm cạnh unit_test → package. Đồ thị sẽ mô tả rõ điều kiện đầu vào của package.

### DAG và danh sách công việc tuần tự

Một danh sách tuần tự thường buộc mọi bước chạy theo một thứ tự cố định:

~~~text
compile -> lint -> unit_test -> package -> integration_test -> deploy
~~~

Nhưng lint có thể độc lập với compile, và cả hai có thể chạy cùng lúc. Một đồ thị có hướng biểu diễn được điều đó:

~~~text
             +----> compile ----> package ----> integration_test
source ------|
             +----> lint ------------------------------+
                                                        |
                                                        v
                                                   quality_gate
                                                        ^
                                                        |
             +----> unit_test --------------------------+
~~~

Đồ thị không nói rằng mọi công việc phải chạy song song. Nó chỉ nêu những ràng buộc bắt buộc. Hệ thống lập lịch có thể chạy đồng thời các đỉnh không phụ thuộc nhau khi có đủ runner và tài nguyên.

## 2. Mô hình hóa công việc và quan hệ phụ thuộc

Trước khi viết YAML pipeline, cần xác định rõ các công việc, đầu vào, đầu ra và điều kiện để chúng được thực thi.

### Xác định đỉnh

Một job nên đại diện cho một mục tiêu có thể hiểu và kiểm tra độc lập. Ví dụ:

| Job | Mục tiêu | Đầu vào chính | Đầu ra |
|---|---|---|---|
| compile | Biên dịch mã nguồn | Source code, dependency | Class hoặc binary trung gian |
| lint | Kiểm tra quy ước và chất lượng mã | Source code, rule set | Kết quả phân tích |
| unit_test | Kiểm tra đơn vị | Source code hoặc class đã biên dịch | Test report |
| package | Tạo gói phát hành | Binary, metadata, cấu hình đóng gói | JAR hoặc container image |
| integration_test | Kiểm tra tương tác thành phần | Artifact, service thử nghiệm | Test report |
| security_scan | Kiểm tra rủi ro bảo mật | Source hoặc artifact | Scan report |
| quality_gate | Đánh giá các điều kiện bắt buộc | Kết quả các job trước | Trạng thái đạt hoặc không đạt |
| deploy | Đưa artifact tới môi trường | Artifact đã xác minh | Deployment record |

Không nên chia job quá nhỏ chỉ để tăng số lượng node. Một job cần có ranh giới trách nhiệm đủ rõ, đầu ra có thể quan sát và lý do tồn tại trong pipeline. Ngược lại, nếu một job thực hiện quá nhiều việc không liên quan, lỗi khó khoanh vùng và việc tối ưu song song bị hạn chế.

### Xác định cạnh

Với mỗi job, hãy hỏi:

1. Job cần dữ liệu hoặc kết quả nào trước khi bắt đầu?
2. Job nào tạo ra dữ liệu hoặc kết quả đó?
3. Có phải đợi job trước hoàn tất thành công, hay chỉ cần một artifact đã tồn tại?
4. Nếu job trước thất bại hoặc bị bỏ qua, job hiện tại có còn ý nghĩa không?

Ví dụ, integration_test cần package tạo ra artifact nên có cạnh package → integration_test. Deploy cần quality_gate đạt và cần artifact đã đóng gói nên có hai cạnh package → deploy và quality_gate → deploy.

Đừng tạo cạnh chỉ vì hai job xuất hiện cạnh nhau trong một file YAML. Cạnh cần phản ánh một ràng buộc thực tế. Nếu không có phụ thuộc dữ liệu hoặc điều kiện, hai job có thể chạy độc lập.

### Phân biệt phụ thuộc thứ tự và phụ thuộc dữ liệu

Hai khái niệm này liên quan nhưng không giống nhau:

- **Phụ thuộc thứ tự:** job B chỉ được chạy sau khi job A hoàn tất.
- **Phụ thuộc dữ liệu:** job B cần đầu ra do job A tạo ra, chẳng hạn file JAR, test report hoặc image digest.

Khai báo job B phụ thuộc job A thường giúp hệ thống bảo đảm thứ tự. Tuy nhiên, nhiều nền tảng không tự động chuyển file giữa các runner. Muốn sử dụng đầu ra, cần cơ chế artifact, workspace dùng chung hoặc kho lưu trữ phù hợp.

Ví dụ, compile chạy trên runner 1 và package chạy trên runner 2. Dù package khai báo phụ thuộc compile, thư mục build của runner 1 có thể không tồn tại trên runner 2. Pipeline phải upload artifact sau compile và download artifact trong package, hoặc dùng một cơ chế chia sẻ dữ liệu được nền tảng hỗ trợ.

Cache thường dùng để tăng tốc và có thể bị xóa hoặc làm mới. Artifact là đầu ra có chủ đích của một lần chạy, cần được lưu và truy xuất theo định danh. Không dùng cache làm bằng chứng duy nhất cho đầu ra cần phát hành.

## 3. Đọc một DAG qua fan-out và fan-in

Hai hình dạng thường xuất hiện trong pipeline là fan-out và fan-in.

### Fan-out: một công việc mở ra nhiều nhánh

Fan-out xảy ra khi một job hoàn tất và nhiều job độc lập có thể bắt đầu:

~~~text
                 +----> lint
                 |
compile ---------+----> unit_test
                 |
                 +----> package_check
~~~

Sau khi compile hoàn tất, lint, unit_test và package_check có thể chạy song song nếu không có phụ thuộc khác. Cách tổ chức này giúp giảm thời gian phản hồi và tách kết quả kiểm tra theo mục tiêu.

Fan-out cũng xuất hiện khi chạy ma trận kiểm thử theo nhiều phiên bản JDK, hệ điều hành hoặc cấu hình. Mỗi tổ hợp có thể là một job riêng, cùng phụ thuộc vào một đầu vào chung.

### Fan-in: nhiều nhánh hội tụ vào một công việc

Fan-in xảy ra khi một job cần kết quả từ nhiều job trước:

~~~text
lint -----------+
                |
unit_test ------+----> quality_gate ----> deploy
                |
integration_test+
                |
security_scan --+
~~~

quality_gate chỉ có thể đạt khi tất cả kiểm tra bắt buộc đã hoàn tất và đáp ứng chính sách. Đây là điểm hội tụ để ra quyết định. Một pipeline có thể có nhiều quality gate ở các giai đoạn khác nhau, ví dụ trước merge, trước staging và trước production.

### Kết hợp fan-out và fan-in

Pipeline thực tế thường kết hợp hai dạng:

~~~text
                    +----> lint ---------------------+
                    |                                |
source -> compile --+----> unit_test ----------------+--> quality_gate
                    |                                |          |
                    +----> package -> integration_test+          v
                                 |                    |      deploy_staging
                                 +--> security_scan --+          |
                                                                v
                                                            smoke_test
                                                                |
                                                                v
                                                          deploy_production
~~~

Đồ thị này cho thấy các kiểm tra độc lập có thể bắt đầu sớm, trong khi những bước cần artifact phải chờ package. Sau khi các kết quả hội tụ tại quality_gate, pipeline mới tiến tới triển khai.

## 4. Điều kiện để một job được chạy

Một job thường đủ điều kiện chạy khi tất cả job phụ thuộc bắt buộc đã kết thúc theo trạng thái được nền tảng chấp nhận. Quy tắc cụ thể tùy công cụ CI/CD, nhưng cần phân biệt các trạng thái:

| Trạng thái job trước | Ý nghĩa | Ảnh hưởng thường gặp tới job phụ thuộc |
|---|---|---|
| Success | Hoàn tất thành công | Có thể mở khóa job sau |
| Failed | Có lỗi | Job phụ thuộc thường bị chặn hoặc skipped |
| Cancelled | Bị hủy trước khi hoàn tất | Job phụ thuộc thường không chạy |
| Skipped | Không được thực thi do điều kiện hoặc phụ thuộc | Có thể khiến job sau bị bỏ qua nếu phụ thuộc bắt buộc |
| Pending / Running | Chưa có kết quả cuối | Job phụ thuộc tiếp tục chờ |
| Allowed failure / Warning | Thất bại nhưng được chính sách cho phép | Có thể không chặn luồng, tùy nền tảng và cấu hình |

Không nên mặc định mọi trạng thái không phải success đều có thể chấp nhận. Hãy xác định job nào là bắt buộc, job nào chỉ cung cấp thông tin và ai có quyền cho phép ngoại lệ.

### Job bắt buộc và job tùy chọn

Một số bước có thể chỉ chạy trong điều kiện nhất định. Ví dụ, kiểm tra tài liệu chỉ chạy khi PR thay đổi file Markdown; job publish tài liệu chỉ chạy trên nhánh chính. Khi job điều kiện bị skipped, pipeline cần xác định các job phụ thuộc có nên tiếp tục hay không.

Nếu job sau bắt buộc phải nhận kết quả của job tùy chọn, cần thiết kế rõ hành vi khi job đó không chạy. Có thể dùng dependency tùy chọn nếu nền tảng hỗ trợ, hoặc tách hai luồng thành các nhánh riêng rồi hội tụ ở một job có điều kiện phù hợp. Tránh tạo dependency bắt buộc tới một job có thể không tồn tại trong mọi lần chạy.

### Điều kiện chạy và phụ thuộc không thay thế nhau

Điều kiện như "chỉ chạy trên main" quyết định job có được kích hoạt trong ngữ cảnh hiện tại hay không. Dependency quyết định job cần chờ những công việc nào. Một job có thể đồng thời có cả hai:

- Chỉ chạy trên nhánh main.
- Chỉ bắt đầu sau khi quality_gate thành công.

Cần đọc cả hai quy tắc khi điều tra vì sao một job bị skipped hoặc không được lên lịch.

## 5. Thứ tự topo và cách hệ thống lập lịch DAG

Một DAG không xác định duy nhất một thứ tự thực thi. Nó cho phép nhiều thứ tự hợp lệ, miễn là mọi job đều chạy sau các dependency của nó.

**Thứ tự topo (topological order)** là một cách sắp xếp các đỉnh sao cho với mọi cạnh A → B, A luôn xuất hiện trước B. Ví dụ, nếu compile → package và lint độc lập, cả hai thứ tự sau đều hợp lệ:

~~~text
compile, lint, package
lint, compile, package
~~~

Trong thực tế, hệ thống không nhất thiết chạy từng job theo danh sách này một cách tuần tự. Nó dùng quan hệ phụ thuộc để xác định tập job đã sẵn sàng, sau đó lập lịch các job đó trên runner có sẵn.

### Thuật toán Kahn ở mức khái niệm

Một cách phổ biến để tìm thứ tự topo là theo dõi số dependency chưa hoàn tất của từng node:

1. Tính số cạnh đi vào (indegree) của mỗi node.
2. Đưa các node có indegree bằng 0 vào hàng đợi.
3. Lấy một node khỏi hàng đợi, thêm nó vào thứ tự kết quả.
4. Với mỗi cạnh đi ra từ node đó, giảm indegree của node đích.
5. Khi indegree của một node đích về 0, đưa node đó vào hàng đợi.
6. Tiếp tục đến khi hàng đợi rỗng.

Nếu số node được lấy ra bằng tổng số node, đồ thị không có chu trình. Nếu vẫn còn node chưa được xử lý, có thể tồn tại chu trình hoặc một nhóm node bị mắc kẹt trong quan hệ phụ thuộc.

### Chu trình là lỗi thiết kế

Ví dụ:

~~~text
compile -> package -> integration_test -> compile
~~~

compile chờ integration_test, integration_test chờ package và package lại chờ compile. Không có node nào trong chu trình có thể bắt đầu. Hệ thống có thể báo lỗi cấu hình hoặc pipeline không thể lên lịch.

Khi gặp chu trình:

- Xem lại từng dependency và lý do cần chờ.
- Xác định liệu một job có đang gộp nhiều trách nhiệm khiến dependency quay vòng hay không.
- Tách công việc thành bước chuẩn bị và bước xác minh độc lập.
- Đưa dữ liệu cần thiết qua artifact thay vì tạo dependency ngược chỉ để chia sẻ workspace.
- Kiểm tra dependency được sinh động từ template hoặc matrix, vì chu trình có thể không rõ trong file nguồn.

Không nên xóa cạnh một cách tùy tiện để làm pipeline chạy được. Trước khi bỏ dependency, cần xác minh job đích có đủ dữ liệu và điều kiện để chạy độc lập hay không.

## 6. Đường găng và thời gian pipeline

DAG giúp nhìn ra công việc nào quyết định thời gian hoàn tất của pipeline. Đường đi dài nhất theo thời lượng trong DAG được gọi là **đường găng (critical path)**. Nếu không xét giới hạn runner, tổng thời gian tối thiểu của pipeline bị chi phối bởi đường đi này.

Giả sử pipeline có các thời lượng:

| Công việc | Thời lượng giả định | Phụ thuộc |
|---|---:|---|
| compile | 4 phút | source |
| lint | 2 phút | source |
| unit_test | 6 phút | compile |
| package | 2 phút | compile |
| integration_test | 8 phút | package |
| security_scan | 5 phút | package |
| quality_gate | 1 phút | lint, unit_test, integration_test, security_scan |
| deploy_staging | 3 phút | package, quality_gate |

Thời điểm hoàn tất sớm nhất của từng job phụ thuộc vào thời điểm hoàn tất muộn nhất trong các dependency của nó. Với các số liệu trên:

- compile hoàn tất ở phút 4.
- lint hoàn tất ở phút 2.
- unit_test hoàn tất ở phút 10.
- package hoàn tất ở phút 6.
- integration_test hoàn tất ở phút 14.
- security_scan hoàn tất ở phút 11.
- quality_gate chỉ hoàn tất sau khi mọi đầu vào sẵn sàng, tức phút 15.
- deploy_staging hoàn tất ở phút 18.

Đường găng trong ví dụ là compile → package → integration_test → quality_gate → deploy_staging, tổng 18 phút. Lint và security_scan có thể chạy song song với các nhánh khác nên không quyết định thời gian kết thúc trong trường hợp này.

Thời gian thực tế còn phụ thuộc số runner, thời gian chờ hàng đợi, giới hạn đồng thời, tài nguyên dùng chung và cache. Nếu chỉ có một runner, các job độc lập có thể vẫn phải xếp hàng. Vì vậy, tối ưu DAG cần kết hợp tối ưu cấu trúc phụ thuộc và năng lực thực thi.

### Cách rút ngắn đường găng

- Đưa kiểm tra nhanh và độc lập lên sớm để phát hiện lỗi sớm.
- Chạy song song các job không phụ thuộc nhau.
- Tối ưu job dài nhất trên đường găng, ví dụ chia integration test thành các nhóm có thể chạy độc lập.
- Giảm thời gian khởi tạo runner và tải dependency.
- Dùng artifact giữa các job để tránh build lại cùng đầu vào.
- Tránh thêm dependency chỉ để giữ thứ tự trình bày.
- Theo dõi thời gian chờ runner để phân biệt nút thắt do DAG với nút thắt do thiếu năng lực thực thi.

Chạy song song không phải lúc nào cũng nhanh hơn. Nếu các job cùng sử dụng một database thử nghiệm hoặc một dịch vụ có giới hạn tài nguyên, chạy đồng thời có thể gây tranh chấp, test chập chờn và tổng thời gian tăng lên. Khi đó cần cô lập dữ liệu, giới hạn concurrency hoặc sắp xếp nhóm job theo năng lực môi trường.

## 7. Thiết kế DAG cho pipeline CI/CD

Một cách thiết kế thực tế là bắt đầu từ đầu ra cuối cùng rồi lần ngược các điều kiện cần có.

### Bước 1: Xác định kết quả cuối

Ví dụ, mục tiêu là triển khai một artifact đã xác minh lên staging. Để làm được điều đó, pipeline cần:

- Artifact được tạo từ commit cụ thể.
- Các kiểm tra mã nguồn bắt buộc đạt.
- Integration test trên artifact đạt.
- Security scan đáp ứng chính sách.
- Quality gate tổng hợp chấp thuận.

### Bước 2: Tách các job theo trách nhiệm

Tạo các node compile, lint, unit_test, package, integration_test, security_scan, quality_gate và deploy_staging. Mỗi node có một mục tiêu, input và output rõ ràng.

### Bước 3: Khai báo dependency tối thiểu

- compile phụ thuộc source checkout.
- unit_test phụ thuộc compile nếu cần class đã biên dịch.
- package phụ thuộc compile.
- integration_test và security_scan phụ thuộc package.
- quality_gate phụ thuộc lint, unit_test, integration_test và security_scan.
- deploy_staging phụ thuộc package và quality_gate.

### Bước 4: Xác định đầu ra cần truyền

Artifact package cần được upload một lần và download ở các job kiểm thử hoặc triển khai. Test report và scan report cần được lưu để quality_gate có thể đánh giá. Không giả định runner dùng chung filesystem nếu nền tảng cấp runner riêng cho mỗi job.

### Bước 5: Xác định hành vi khi lỗi

Nếu compile thất bại, unit_test và package không thể chạy. Nếu lint thất bại, integration_test có thể vẫn hữu ích để thu thập thêm thông tin, nhưng deploy phải bị chặn bởi quality_gate. Nếu security_scan là gate bắt buộc, lỗi hoặc thiếu kết quả scan phải chặn phát hành theo chính sách.

### Bước 6: Xem xét điều kiện và nhánh phát hành

PR có thể chạy compile, lint, unit_test và các scan cần thiết. Deploy staging có thể chỉ chạy sau merge lên main. Deploy production có thể cần phê duyệt thủ công hoặc điều kiện release riêng. Các điều kiện này cần được thể hiện rõ trong cấu hình.

## 8. Ví dụ DAG bằng GitHub Actions

GitHub Actions hỗ trợ khai báo dependency giữa các job bằng trường needs. Job chỉ bắt đầu khi các job được liệt kê trong needs đã hoàn tất theo quy tắc trạng thái của nền tảng.

Ví dụ sau mô tả luồng: build_package, lint và unit_test có thể chạy song song; artifact từ build_package được kiểm thử tích hợp và quét bảo mật; các kết quả hội tụ ở quality_gate; sau đó artifact được triển khai lên staging, smoke test và production.

~~~yaml
name: ci-cd

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build_package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon assemble
      - uses: actions/upload-artifact@v4
        with:
          name: application-package
          path: build/libs/*.jar

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon checkstyleMain

  unit_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon test

  integration_test:
    needs: [build_package]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Run integration tests against package
        run: ./scripts/integration-test.sh package

  security_scan:
    needs: [build_package]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Scan package
        run: ./scripts/scan-package.sh package

  quality_gate:
    needs: [lint, unit_test, integration_test, security_scan]
    runs-on: ubuntu-latest
    steps:
      - name: All required checks passed
        run: echo "Quality gate passed"

  deploy_staging:
    needs: [build_package, quality_gate]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Deploy
        run: ./scripts/deploy.sh staging package

  smoke_test:
    needs: [deploy_staging]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify staging
        run: ./scripts/smoke-test.sh staging

  deploy_production:
    needs: [build_package, smoke_test]
    if: github.ref == 'refs/heads/main'
    environment: production
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Deploy
        run: ./scripts/deploy.sh production package
~~~

Đây là ví dụ kiến trúc; các script, task Gradle, môi trường và quyền truy cập cần được cung cấp theo dự án. Một số điểm cần chú ý:

- needs tạo cạnh phụ thuộc. Ví dụ quality_gate chờ lint, unit_test, integration_test và security_scan.
- build_package, lint và unit_test có thể chạy song song vì không khai báo dependency lẫn nhau.
- build_package tạo và upload artifact. Integration test, security scan và các bước deploy lấy đúng artifact đó bằng tên artifact.
- deploy_staging có hai điều kiện tiên quyết: build_package và quality_gate. Nó chỉ chạy trên main theo điều kiện if trong ví dụ.
- deploy_production chờ smoke_test và build_package. Approval cho environment production cần được cấu hình trong bảo vệ môi trường của repository.
- Nếu một dependency bắt buộc thất bại hoặc bị skipped, các job phía sau thường bị skipped. Cần kiểm tra quy tắc if và trạng thái job theo tài liệu nền tảng trước khi áp dụng.
- Workflow tối giản chưa bao gồm xác thực digest, ký provenance hoặc quản lý secret. Những bước đó cần được bổ sung theo chính sách phát hành.

## 9. Biểu diễn DAG trong các nền tảng CI khác nhau

Các nền tảng CI/CD có cú pháp và quy tắc lập lịch khác nhau, nhưng ý tưởng về node và dependency là tương tự.

### GitHub Actions

- Mỗi job là một node.
- needs khai báo các node tiền nhiệm mà job phải chờ.
- Các job không có dependency chung có thể chạy song song nếu runner và giới hạn concurrency cho phép.
- Artifact action dùng để truyền file giữa các job.
- Điều kiện if điều khiển việc một job có chạy trong ngữ cảnh cụ thể hay không.
- Job phụ thuộc vào job thất bại hoặc skipped thường bị skipped, trừ khi dùng điều kiện trạng thái phù hợp như always hoặc failure. Cần dùng các điều kiện này cẩn thận để không vô tình cho deploy chạy khi gate thất bại.

### GitLab CI/CD

GitLab hỗ trợ stages và needs. Nếu chỉ dùng stages, các job trong stage sau thường chờ stage trước hoàn tất. Khi dùng needs, một job có thể bắt đầu ngay khi các dependency được chỉ định hoàn tất, tạo luồng DAG chi tiết hơn.

Ví dụ minh họa:

~~~yaml
stages:
  - build
  - verify
  - deploy

build_app:
  stage: build
  script:
    - ./gradlew assemble
  artifacts:
    paths:
      - build/libs/

unit_test:
  stage: verify
  needs:
    - build_app
  script:
    - ./gradlew test

security_scan:
  stage: verify
  needs:
    - build_app
  script:
    - ./scripts/scan-package.sh build/libs/

deploy_staging:
  stage: deploy
  needs:
    - job: build_app
      artifacts: true
    - job: unit_test
      artifacts: false
    - job: security_scan
      artifacts: false
  script:
    - ./scripts/deploy.sh staging
~~~

Ở ví dụ này, unit_test và security_scan cùng phụ thuộc build_app nên có thể chạy song song sau khi build hoàn tất. deploy_staging chờ cả hai kết quả. Cấu hình artifacts và dependencies cần được kiểm tra theo cách dự án lưu file và phiên bản GitLab đang dùng.

### Jenkins Pipeline

Trong Jenkins Declarative Pipeline, stages và parallel có thể mô tả một số dạng song song. Với pipeline phức tạp, có thể dùng scripted pipeline hoặc các cơ chế orchestration khác để biểu diễn dependency. Dù dùng cú pháp nào, cần bảo đảm các nhánh parallel có điều kiện đầu vào rõ và bước hội tụ chỉ chạy sau khi những nhánh bắt buộc đã hoàn tất.

Không nên sao chép nguyên cấu hình giữa các nền tảng. Hãy chuyển đổi ý nghĩa của đồ thị, sau đó ánh xạ sang cú pháp và ngữ nghĩa của công cụ đang sử dụng.

## 10. Ma trận kiểm thử và DAG động

Nhiều pipeline cần kiểm tra cùng một ứng dụng trên nhiều tổ hợp môi trường. Ví dụ: JDK 17 và 21, Linux và Windows, hoặc nhiều phiên bản database. Ma trận tạo ra nhiều job từ một định nghĩa chung.

~~~text
                 +--> test JDK 17 / Linux --+
build artifact --+--> test JDK 21 / Linux --+--> aggregate_test_results
                 +--> test JDK 21 / Windows-+
~~~

Các job ma trận là những node riêng trong đồ thị thực thi. Job tổng hợp cần chờ tất cả tổ hợp bắt buộc hoặc áp dụng chính sách xác định rõ tổ hợp nào là bắt buộc.

Khi ma trận có job được phép thất bại, cần phân biệt lỗi được chấp nhận với job bị bỏ qua do cấu hình sai. Một nền tảng có thể hỗ trợ continue-on-error hoặc allow_failure, nhưng nếu áp dụng quá rộng, lỗi tương thích có thể bị che khuất.

Một số hệ thống cho phép tạo pipeline con hoặc DAG động dựa trên nội dung repository. Ví dụ, thay đổi trong module A chỉ tạo job kiểm thử A và các module phụ thuộc. Điều này có thể tiết kiệm tài nguyên nhưng đòi hỏi mô hình dependency giữa module chính xác. Nếu xác định sai phạm vi thay đổi, pipeline có thể bỏ qua một kiểm tra cần thiết. Nên có kiểm tra toàn diện định kỳ hoặc trước phát hành để bù đắp cho chiến lược chọn lọc.

## 11. Lỗi thiết kế DAG thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thiếu cạnh phụ thuộc | Job chạy trước khi đầu vào sẵn sàng | Khai báo dependency thực tế và truyền artifact rõ ràng |
| Thêm cạnh không cần thiết | Mất khả năng song song, pipeline chậm | Chỉ giữ dependency có lý do |
| Tạo chu trình | Pipeline không thể lập lịch | Phát hiện chu trình và tách lại trách nhiệm job |
| Nhầm dependency với truyền file | Job sau không tìm thấy artifact | Dùng artifact hoặc workspace được hỗ trợ |
| Job điều kiện là dependency bắt buộc | Job sau bị skipped ngoài dự kiến | Thiết kế optional dependency hoặc điều kiện phù hợp |
| Cho phép failure quá rộng | Quality gate vẫn xanh dù kiểm tra quan trọng lỗi | Phân loại job bắt buộc và job cảnh báo |
| Chạy song song trên tài nguyên dùng chung | Xung đột dữ liệu, flaky test | Cô lập môi trường hoặc giới hạn concurrency |
| Build lại ở nhiều nhánh pipeline | Kết quả artifact không nhất quán | Build một lần, chia sẻ artifact đã định danh |
| Một job tổng hợp không kiểm tra đủ đầu vào | Gate không phản ánh mọi kết quả | Khai báo đầy đủ dependency và xác minh report |
| Không lưu trạng thái từng node | Khó điều tra nút thắt và lỗi | Giữ log, duration và trạng thái theo job |

## 12. Quan sát và vận hành pipeline dạng DAG

Đồ thị dễ hiểu trên giấy chưa chắc dễ vận hành. Khi pipeline chạy thực tế, nhóm cần quan sát được trạng thái và thời gian của từng node.

Các thông tin nên lưu:

- Tên job và định danh lần chạy.
- Commit SHA hoặc release ID liên quan.
- Danh sách dependency của job.
- Thời điểm được đưa vào hàng đợi, bắt đầu và kết thúc.
- Runner hoặc loại tài nguyên thực thi.
- Trạng thái success, failed, cancelled, skipped hoặc warning.
- Log, test report, scan report và artifact liên quan.
- Lý do job không chạy hoặc bị chặn.

Khi một pipeline chậm, phân biệt ba khoảng thời gian:

1. **Queue time:** thời gian job chờ runner.
2. **Execution time:** thời gian job thực sự chạy.
3. **Dependency wait time:** thời gian job chờ các node tiền nhiệm.

Nếu queue time cao, cần xem xét năng lực runner và giới hạn concurrency. Nếu execution time cao, tối ưu script, test, cache hoặc công cụ. Nếu dependency wait time cao, xem lại đường găng và các cạnh không cần thiết.

### Giữ DAG dễ bảo trì

- Dùng tên job mô tả mục tiêu, tránh tên quá chung như task1 hoặc step2.
- Nhóm job theo trách nhiệm như build, test, security và deploy.
- Tái sử dụng template hoặc reusable workflow khi nhiều pipeline có cùng cấu trúc.
- Giữ logic dependency dễ đọc; tránh tạo chuỗi phụ thuộc chỉ để mô phỏng thứ tự trình bày.
- Tài liệu hóa những node có quyền publish, deploy hoặc truy cập secret.
- Kiểm tra DAG khi thay đổi pipeline definition, nhất là khi thêm job điều kiện hoặc ma trận.
- Lưu artifact và report với tên, version hoặc digest đủ để truy vết.

## 13. Checklist thiết kế DAG

Trước khi đưa một pipeline DAG vào sử dụng, hãy rà soát:

- [ ] Mỗi node đại diện cho một công việc có mục tiêu rõ ràng.
- [ ] Mỗi cạnh thể hiện một phụ thuộc thứ tự hoặc đầu vào thực tế.
- [ ] Đồ thị không có chu trình.
- [ ] Các công việc độc lập có thể chạy song song khi tài nguyên cho phép.
- [ ] Job cần artifact có cơ chế upload/download hoặc truyền dữ liệu rõ ràng.
- [ ] Job hội tụ chờ đầy đủ các kiểm tra bắt buộc.
- [ ] Job điều kiện và dependency tùy chọn có hành vi khi skipped được xác định.
- [ ] Failure ở build, test, scan hoặc quality gate chặn đúng các bước phát hành.
- [ ] Các ngoại lệ được giới hạn và ghi nhận.
- [ ] Đường găng và thời gian chờ runner được theo dõi.
- [ ] Artifact được định danh và tái sử dụng nhất quán qua các bước.
- [ ] Log, report và trạng thái từng node đủ để điều tra.
- [ ] Quyền secret và deploy chỉ được cấp cho job cần thiết.

## Kết luận

DAG là cách biểu diễn phụ thuộc giúp pipeline vừa đúng thứ tự vừa khai thác được khả năng chạy song song. Hãy xác định rõ node, cạnh, đầu vào và đầu ra; giữ đồ thị không có chu trình; phân biệt dependency thực thi với việc truyền artifact; và thiết kế điểm hội tụ cho quality gate. Khi kết hợp với quan sát thời gian từng job và quản lý artifact có định danh, DAG giúp pipeline dễ hiểu, dễ tối ưu và đáng tin cậy hơn trong toàn bộ luồng CI/CD.

