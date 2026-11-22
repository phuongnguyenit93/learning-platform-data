# Đọc cấu trúc YAML hoặc DSL ở mức khái niệm

Pipeline CI/CD thường được mô tả bằng một tệp cấu hình nằm cùng repository với mã nguồn. Tệp đó có thể dùng YAML, một DSL (Domain-Specific Language) hoặc kết hợp cả hai. Khi đọc một pipeline, mục tiêu không chỉ là hiểu từng dòng cú pháp. Cần nhận ra pipeline bắt đầu từ sự kiện nào, công việc được chia thành những phần nào, phần nào phụ thuộc phần nào, lệnh chạy ở đâu, dữ liệu được chuyển giao ra sao và những điều kiện nào cho phép phát hành.

Một tệp YAML có thể trông giống tài liệu dữ liệu đơn giản, nhưng các khóa của nó được nền tảng CI/CD diễn giải theo một schema và một mô hình thực thi cụ thể. Một DSL có thể trông giống chương trình thông thường, nhưng các hàm và cấu trúc của nó thường đại diện cho job, stage, agent, step hoặc quy tắc điều phối. Vì vậy, cần đọc đồng thời ba lớp: cú pháp của ngôn ngữ, ý nghĩa mà nền tảng gán cho cấu trúc và tác động khi pipeline thực thi.

## 1. Phân biệt YAML, DSL và ngữ nghĩa của pipeline

### YAML là định dạng biểu diễn dữ liệu

YAML mô tả dữ liệu có cấu trúc thông qua ánh xạ khóa-giá trị, danh sách và giá trị đơn. Bản thân YAML không biết khái niệm build, test, deploy hay runner. Ví dụ:

~~~yaml
application:
  name: order-service
  environments:
    - development
    - staging
    - production
  checks:
    tests_required: true
    retry_limit: 2
~~~

Đoạn trên chỉ biểu diễn một cấu trúc dữ liệu. Nó chưa phải pipeline có thể chạy vì chưa có nền tảng nào được chỉ định cách diễn giải các khóa application, environments hoặc checks.

### DSL cung cấp từ vựng chuyên biệt

**DSL** là ngôn ngữ được thiết kế cho một miền công việc cụ thể. Trong CI/CD, DSL có thể cung cấp các khái niệm như pipeline, stage, agent, node, step, input, post-action hoặc điều kiện. Một số nền tảng dùng YAML làm cú pháp bên ngoài và định nghĩa DSL thông qua schema của các khóa. Nền tảng khác dùng DSL dạng mã, chẳng hạn cú pháp dựa trên Groovy hoặc một ngôn ngữ lập trình được nhúng.

DSL thường quy định:

- Những cấu trúc nào được phép khai báo.
- Mỗi cấu trúc nhận những thuộc tính nào.
- Cách khai báo thứ tự, phụ thuộc và chạy song song.
- Cách truyền biến, tham số và kết quả giữa các bước.
- Điều kiện chạy, xử lý lỗi và hành động sau khi hoàn tất.
- Quyền thực thi và môi trường mà pipeline được phép sử dụng.

### Ba lớp cần đọc cùng nhau

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Cú pháp | Tệp được viết đúng cấu trúc ngôn ngữ chưa? | Thụt lề YAML, dấu hai chấm, danh sách, chuỗi |
| Schema và DSL | Nền tảng hiểu khóa hoặc câu lệnh đó là gì? | jobs, stages, runner, steps, depends_on |
| Ngữ nghĩa thực thi | Khi chạy, hệ thống thực hiện hành động nào và trong điều kiện nào? | Chờ job khác, chạy lệnh shell, tải artifact, yêu cầu phê duyệt |

Một tệp có thể hợp lệ về cú pháp YAML nhưng vẫn không hợp lệ với schema của nền tảng. Tệp cũng có thể vượt qua kiểm tra schema nhưng tạo ra luồng thực thi sai với mục đích của nhóm. Ví dụ, một job triển khai production có thể được khai báo đúng, nhưng thiếu điều kiện giới hạn nhánh hoặc môi trường bảo vệ.

## 2. Nhận diện cấu trúc YAML cơ bản

Trước khi đọc logic CI/CD, cần hiểu cách YAML tổ chức dữ liệu.

### Ánh xạ khóa-giá trị

Ánh xạ (mapping) là tập hợp các khóa và giá trị:

~~~yaml
job:
  name: build
  timeout_minutes: 20
  allow_failure: false
~~~

Ở đây job là khóa cấp cao nhất. Giá trị của nó là một ánh xạ lồng nhau gồm name, timeout_minutes và allow_failure. Mức thụt lề thể hiện quan hệ cha-con.

### Danh sách

Danh sách (sequence) biểu diễn nhiều phần tử theo thứ tự:

~~~yaml
steps:
  - name: Compile
    command: ./gradlew classes
  - name: Run unit tests
    command: ./gradlew test
~~~

Mỗi dấu gạch đầu dòng bắt đầu một phần tử của danh sách steps. Mỗi phần tử ở ví dụ này lại là một ánh xạ có hai khóa. Thứ tự phần tử có thể mang ý nghĩa thực thi nếu DSL định nghĩa steps chạy tuần tự.

### Giá trị đơn và kiểu dữ liệu

YAML có thể biểu diễn chuỗi, số, giá trị boolean và null:

~~~yaml
timeout_minutes: 15
retry_limit: 2
continue_on_error: false
description: "Run integration checks"
optional_parameter: null
~~~

Khi đọc cấu hình, đừng giả định mọi giá trị đều là chuỗi. Giá trị false không tương đương chuỗi "false"; số 2 không nhất thiết tương đương chuỗi "2". Schema có thể yêu cầu kiểu cụ thể và từ chối kiểu không phù hợp.

Một số parser hoặc phiên bản YAML có khác biệt trong cách nhận diện giá trị không đặt trong dấu nháy. Khi một chuỗi có thể bị hiểu thành boolean, số, ngày hoặc có ký tự đặc biệt, hãy dùng cách trích dẫn theo quy ước của nền tảng. Tên khóa và kiểu dữ liệu cũng phải tuân theo schema của công cụ CI/CD.

### Chuỗi nhiều dòng

YAML có hai kiểu khối chuỗi thường gặp:

- Dấu | giữ các ký tự xuống dòng trong nội dung.
- Dấu > thường gộp các dòng liên tiếp thành khoảng trắng theo quy tắc YAML.

~~~yaml
script_literal: |
  echo "Prepare workspace"
  ./gradlew test

description_folded: >
  This job validates the source
  before an artifact is published.
~~~

Với lệnh shell nhiều dòng, kiểu | thường dễ đọc vì giữ ranh giới từng lệnh. Tuy nhiên, cách nền tảng truyền chuỗi đến shell và cách xử lý lỗi giữa các lệnh vẫn phụ thuộc runner, shell và DSL. Không nên suy ra rằng chỉ cần một dòng lệnh thất bại thì toàn bộ khối chắc chắn dừng; hãy kiểm tra hành vi shell và cấu hình thực thi.

### Những lỗi cú pháp thường gặp

- Dùng tab để thụt lề trong khi YAML yêu cầu thụt bằng dấu cách.
- Đặt khóa cùng cấp ở các mức thụt lề khác nhau.
- Thiếu dấu hai chấm sau khóa hoặc viết sai cấu trúc danh sách.
- Dùng chuỗi chứa dấu hai chấm, dấu thăng hoặc ký tự đặc biệt mà không trích dẫn phù hợp.
- Nhầm chuỗi nhiều dòng với một danh sách các lệnh.
- Dùng anchor, alias hoặc merge key mà parser hay nền tảng không hỗ trợ như mong đợi.

Anchor và alias có thể giúp tái sử dụng đoạn YAML, nhưng không phải mọi nền tảng đều hỗ trợ mọi tính năng YAML hoặc cùng cách xử lý. Cấu hình tái sử dụng cũng cần dễ đọc sau khi mở rộng, vì người review phải hiểu được nội dung thực tế được áp dụng cho job.

## 3. Mô hình khái niệm của một pipeline

Tên khóa cụ thể thay đổi theo sản phẩm, nhưng phần lớn pipeline có những thành phần tương tự:

| Thành phần | Vai trò | Câu hỏi khi đọc |
|---|---|---|
| Pipeline hoặc workflow | Đơn vị điều phối tổng thể | Tên và phạm vi của luồng là gì? |
| Trigger hoặc event | Sự kiện khởi chạy | Push, pull request, lịch hay thao tác thủ công? |
| Parameter hoặc input | Giá trị đầu vào do người gọi cung cấp | Có giá trị mặc định và giới hạn hợp lệ không? |
| Stage | Nhóm công việc theo giai đoạn | Những công việc nào thuộc cùng giai đoạn? |
| Job | Đơn vị công việc được scheduler phân phối | Job chạy trên runner nào và phụ thuộc đâu? |
| Step hoặc task | Hành động bên trong job | Lệnh hoặc action nào được thực hiện? |
| Runner hoặc agent | Máy hoặc môi trường thực thi | Hệ điều hành, công cụ và quyền truy cập là gì? |
| Variable hoặc environment | Cấu hình được đưa vào lúc chạy | Phạm vi và nguồn giá trị ở đâu? |
| Artifact | Đầu ra được lưu và chuyển tiếp | Job sau nhận đúng sản phẩm nào? |
| Condition hoặc rule | Điều kiện cho phép thực thi | Khi nào job được chạy hoặc bỏ qua? |
| Secret và permission | Thông tin nhạy cảm và quyền | Pipeline được phép đọc hoặc thay đổi tài nguyên nào? |

Không phải nền tảng nào cũng có đủ tất cả các lớp. Có hệ thống tổ chức theo stage rồi đến job; hệ thống khác khai báo trực tiếp danh sách job và quan hệ phụ thuộc. Một số nền tảng xem mỗi step là một lệnh trong cùng máy thực thi; hệ thống khác tạo môi trường riêng cho từng task. Cần hiểu mô hình của công cụ đang dùng trước khi diễn giải tên khóa.

## 4. Ví dụ cấu trúc pipeline ở mức khái niệm

Ví dụ dưới đây dùng các tên khóa trung lập để minh họa cách đọc. Đây là **mô hình YAML giả định**, không phải tệp có thể chạy trực tiếp trên một nền tảng CI/CD cụ thể:

~~~yaml
pipeline:
  name: order-service-delivery

  triggers:
    - event: push
      branches:
        - main
    - event: pull_request

  permissions:
    repository: read

  jobs:
    validate:
      runner: linux-small
      steps:
        - name: Check formatting
          command: ./gradlew spotlessCheck
        - name: Static analysis
          command: ./gradlew checkstyleMain

    build:
      depends_on:
        - validate
      runner: linux-medium
      steps:
        - name: Compile and package
          command: ./gradlew assemble
        - name: Publish package
          publish:
            name: order-service-package
            path: build/libs/*.jar

    test:
      depends_on:
        - build
      runner: linux-medium
      inputs:
        artifacts:
          - order-service-package
      steps:
        - name: Run integration tests
          command: ./gradlew integrationTest

    release:
      depends_on:
        - test
      condition: branch == "main"
      environment: production
      steps:
        - name: Deploy verified package
          command: ./deploy.sh
~~~

Đọc cấu trúc từ ngoài vào trong:

1. **pipeline.name** đặt tên luồng giao hàng.
2. **triggers** khai báo pipeline có thể khởi chạy khi có push lên main hoặc khi có pull request.
3. **permissions** thể hiện quyền mặc định mà pipeline được cấp theo mô hình giả định này.
4. **jobs** chứa bốn công việc: validate, build, test và release.
5. **runner** chọn loại môi trường thực thi cho từng job.
6. **steps** liệt kê hành động được thực hiện bên trong job.
7. **depends_on** biểu diễn quan hệ phụ thuộc giữa các job.
8. **publish** tạo artifact để job khác sử dụng.
9. **inputs.artifacts** khai báo artifact đầu vào của job test.
10. **condition** giới hạn job release chỉ chạy khi nhánh là main.

Từ cấu trúc này có thể hình dung luồng: validate hoàn tất trước build; build tạo package; test sử dụng package; release chỉ được thực hiện sau test và khi điều kiện nhánh thỏa mãn. Nếu validate thất bại, các job phụ thuộc không nên tiếp tục theo chính sách của pipeline.

Ví dụ chỉ minh họa cách tổ chức. Trên công cụ thật, tên khóa, biểu thức nhánh, cú pháp trigger, cách tải artifact và quyền truy cập có thể hoàn toàn khác. Khi áp dụng, phải tra schema và tài liệu của đúng phiên bản nền tảng.

## 5. Đọc trigger và điều kiện chạy

Trigger trả lời câu hỏi **khi nào pipeline được tạo hoặc khởi chạy**. Điều kiện ở job hoặc step trả lời câu hỏi **phần cụ thể đó có được thực thi trong lần chạy này hay không**. Hai lớp này có thể tồn tại đồng thời.

Các loại trigger thường gặp:

- Sự kiện Git như push, tạo tag, mở hoặc cập nhật pull request.
- Lịch chạy định kỳ.
- Thao tác thủ công hoặc yêu cầu từ một pipeline khác.
- Sự kiện từ hệ thống bên ngoài như phát hành artifact hoặc thay đổi trạng thái môi trường.

Khi đọc trigger, kiểm tra cả phạm vi nhánh, tag, đường dẫn và loại sự kiện. Ví dụ, một pipeline chạy khi có thay đổi trong thư mục dịch vụ A có thể bỏ qua thay đổi chỉ ảnh hưởng dịch vụ B.

Điều kiện thực thi thường dùng để:

- Chỉ chạy release trên nhánh hoặc tag được bảo vệ.
- Bỏ qua job khi không có file thuộc phạm vi cần kiểm tra.
- Chạy bước thông báo khi pipeline thất bại.
- Chỉ triển khai môi trường production khi có phê duyệt.
- Chạy tác vụ dọn dẹp bất kể kết quả của bước trước, nếu nền tảng hỗ trợ.

Không nên chỉ đọc tên điều kiện. Hãy xác định biến được tham chiếu lấy từ đâu, biểu thức được đánh giá lúc nào và điều gì xảy ra khi giá trị không tồn tại. Điều kiện sai có thể khiến kiểm tra bị bỏ qua hoặc triển khai chạy ngoài dự kiến.

## 6. Đọc stage, job, step và quan hệ phụ thuộc

### Stage là nhóm logic

Stage thường biểu diễn một giai đoạn lớn như validate, build, test hoặc deploy. Trong mô hình stage-based, các stage có thể chạy tuần tự; những job cùng stage có thể chạy song song nếu đủ runner và không có ràng buộc khác.

Stage giúp con người đọc luồng ở mức tổng quan. Nó không nhất thiết là đơn vị scheduler thực thi; điều này tùy nền tảng.

### Job là đơn vị được lập lịch

Job thường được scheduler đưa lên một runner hoặc agent. Job có thể khai báo:

- Máy hoặc loại runner.
- Các bước thực hiện.
- Biến môi trường và tham số.
- Timeout, retry và giới hạn tài nguyên.
- Quan hệ phụ thuộc và điều kiện.
- Artifact đầu vào và đầu ra.

Một job có thể chạy trên máy riêng với job khác. Vì vậy, không nên giả định file tạm hoặc tiến trình được tạo trong job trước sẽ tồn tại ở job sau. Dữ liệu cần chuyển giao thường phải được khai báo rõ bằng artifact, cache hoặc cơ chế chia sẻ được nền tảng hỗ trợ.

### Step là hành động trong job

Step có thể là lệnh shell, action đóng gói sẵn, plugin, task chuyên biệt hoặc một đoạn mã DSL. Trong cùng job, các step thường chạy theo thứ tự khai báo, nhưng quy tắc xử lý lỗi, điều kiện bỏ qua và cách chia sẻ workspace phụ thuộc nền tảng.

Khi đọc từng step, hỏi:

1. Step thực hiện hành động gì?
2. Đầu vào của nó đến từ biến, file, artifact hay dịch vụ bên ngoài?
3. Nó tạo ra đầu ra nào?
4. Nếu thất bại, job dừng, retry hay tiếp tục?
5. Nó cần quyền hoặc secret nào?

### Dependency tạo thành đồ thị

Pipeline không chỉ là danh sách lệnh nối tiếp. Quan hệ phụ thuộc giữa job tạo thành một đồ thị có hướng không chu trình (DAG) trong nhiều hệ thống.

~~~mermaid
flowchart TD
    A[Validate] --> B[Build]
    B --> C[Test integration]
    B --> D[Test security]
    C --> E[Release]
    D --> E
~~~

Trong sơ đồ này, hai nhóm test có thể chạy song song sau build. Release chỉ đủ điều kiện khi cả hai nhánh phụ thuộc hoàn tất thành công. Một số nền tảng cho phép khai báo phụ thuộc trực tiếp; một số dùng stage hoặc cơ chế điều phối khác.

Khi đọc dependency, hãy tìm:

- Job nào là điều kiện bắt buộc của job hiện tại?
- Có job nào được chạy song song không?
- Job nào có thể bị bỏ qua và điều đó ảnh hưởng đến dependency ra sao?
- Một job có đang chờ một công việc không cần thiết không?
- Có đường nào dẫn tới release mà bỏ qua kiểm tra bắt buộc không?

Đừng nhầm thứ tự xuất hiện trong file với thứ tự thực thi. Nếu DSL dùng DAG, scheduler có thể chạy job theo khả năng sẵn sàng thay vì theo thứ tự văn bản.

## 7. Đọc runner, workspace và môi trường thực thi

Runner hoặc agent là nơi lệnh thực sự được thực hiện. Cấu hình runner có thể quyết định:

- Hệ điều hành và kiến trúc CPU.
- Image container hoặc môi trường runtime.
- Phiên bản JDK, Node.js, Python hay công cụ build.
- CPU, bộ nhớ, dung lượng đĩa và giới hạn thời gian.
- Quyền truy cập mạng, repository, registry và môi trường triển khai.
- Cách checkout source và lưu workspace.

Nếu pipeline chạy trên runner dùng chung, job có thể chịu ảnh hưởng từ tải của các job khác. Nếu runner tự quản lý, nhóm cần duy trì bản vá hệ điều hành, công cụ, quyền truy cập và khả năng cô lập. Nếu dùng runner tạm thời, không nên dựa vào file còn sót từ lần chạy trước.

Khi đọc một job, hãy kiểm tra môi trường có đủ công cụ và phiên bản cần thiết hay không. Việc không khóa phiên bản công cụ có thể khiến cùng một commit tạo ra kết quả khác nhau ở những thời điểm khác nhau.

## 8. Đọc biến, tham số và biểu thức

Pipeline thường nhận cấu hình từ nhiều nguồn:

- Giá trị khai báo trực tiếp trong file.
- Tham số do người khởi chạy cung cấp.
- Biến cấp pipeline, job hoặc step.
- Cấu hình môi trường.
- Secret store hoặc identity provider.
- Metadata do nền tảng cung cấp, như commit SHA, tên nhánh hoặc mã lần chạy.

### Phạm vi và độ ưu tiên

Biến có thể có phạm vi toàn pipeline, một job hoặc một step. Nếu cùng tên xuất hiện ở nhiều phạm vi, nền tảng sẽ áp dụng quy tắc ưu tiên riêng. Không nên đoán rằng biến ở phạm vi hẹp luôn thắng hoặc biến cấp pipeline luôn thắng; hãy xác minh quy tắc của công cụ.

Nên ưu tiên truyền cấu hình vào đúng phạm vi cần dùng. Một secret chỉ phục vụ bước deploy không cần được cấp cho toàn bộ job build và test.

### Thời điểm đánh giá biểu thức

Một biểu thức có thể được đánh giá:

- Khi nền tảng phân tích cấu hình.
- Khi lập kế hoạch DAG hoặc tạo job.
- Khi job bắt đầu.
- Khi shell thực thi lệnh.

Sự khác biệt này quan trọng. Biểu thức của nền tảng CI/CD và biến môi trường của shell là hai cơ chế khác nhau. Cú pháp nội suy của công cụ không nhất thiết giống cú pháp như $NAME trong Bash hoặc %NAME% trong Windows shell.

Khi đọc một lệnh có nội suy, hãy xác định ai thay thế giá trị, thay thế ở thời điểm nào và giá trị đến từ nguồn đáng tin cậy nào. Tránh đưa dữ liệu do người dùng hoặc pull request không đáng tin cậy trực tiếp vào chuỗi lệnh shell mà không kiểm tra và trích dẫn an toàn.

### Tham số đầu vào

Tham số thủ công có thể điều khiển môi trường đích, phiên bản hoặc phạm vi triển khai. Tham số cần có kiểu dữ liệu, giá trị mặc định, tập giá trị cho phép và kiểm tra quyền phù hợp. Không nên để một chuỗi tự do quyết định lệnh shell hoặc tên môi trường production mà không xác thực.

## 9. Phân biệt artifact, cache và workspace

Ba khái niệm này thường bị nhầm lẫn:

| Khái niệm | Mục đích | Đặc điểm |
|---|---|---|
| Workspace | Thư mục làm việc của job | Có thể chỉ tồn tại trong vòng đời runner hoặc job |
| Cache | Tái sử dụng dữ liệu để giảm thời gian xử lý | Có thể bị loại bỏ, hết hạn hoặc không được khôi phục |
| Artifact | Lưu đầu ra của một lần chạy để kiểm tra, tải xuống hoặc chuyển cho bước sau | Cần định danh và liên kết với lần chạy hoặc phiên bản cụ thể |

Cache phù hợp với dependency đã tải, dữ liệu build có thể tái tạo hoặc kết quả trung gian giúp tăng tốc. Không nên dùng cache như kênh duy nhất để chuyển một binary cần phát hành.

Artifact nên có tên, phiên bản hoặc định danh, nguồn commit và thông tin kiểm tra tính toàn vẹn. Một luồng giao hàng đáng tin cậy thường build artifact một lần, sau đó kiểm thử và triển khai chính artifact đó qua các môi trường. Nếu build lại ở mỗi môi trường, kết quả có thể khác dù mã nguồn không đổi.

Khi đọc pipeline, hãy xác định:

- Job nào tạo artifact?
- Đường dẫn và quy tắc đặt tên là gì?
- Artifact được lưu bao lâu?
- Job sau tải đúng artifact nào?
- Có checksum, chữ ký hoặc metadata truy xuất nguồn gốc không?
- Có vô tình dùng artifact từ một lần chạy hoặc nhánh không đáng tin cậy không?

## 10. Đọc secret, permission và ranh giới tin cậy

Pipeline là mã thực thi. Bất kỳ step nào chạy lệnh đều có thể đọc file, gọi mạng hoặc sử dụng quyền mà runner được cấp. Vì vậy, khi review cấu hình, cần xem bảo mật cùng với logic build.

### Secret

Secret có thể là token, mật khẩu, khóa ký, thông tin đăng nhập registry hoặc credential triển khai. Một cấu hình tốt cần:

- Lấy secret từ kho quản lý bí mật hoặc cơ chế identity được bảo vệ.
- Chỉ cấp secret cho job và môi trường cần sử dụng.
- Tránh ghi secret vào log, artifact, cache hoặc file không được bảo vệ.
- Không đưa secret vào tham số dòng lệnh nếu công cụ có thể ghi lại lệnh.
- Xoay vòng và thu hồi credential theo chính sách.

Ẩn giá trị trong giao diện log không đảm bảo secret không thể bị rò rỉ qua mã hóa, biến đổi hoặc gửi ra mạng. Step được cấp secret cần được xem là một phần của vùng tin cậy.

### Quyền tối thiểu

Job chỉ nên có quyền cần thiết để hoàn thành mục tiêu. Job kiểm tra mã nguồn thường chỉ cần quyền đọc repository. Job phát hành có thể cần quyền ghi registry hoặc triển khai, nhưng quyền đó nên được giới hạn theo môi trường và điều kiện.

Kiểm tra xem quyền được cấp ở cấp workflow, job hay token. Nếu một job không cần quyền ghi, đừng cấp quyền ghi chỉ vì một job khác cần nó.

### Pull request từ nguồn không tin cậy

Pull request từ fork hoặc nguồn bên ngoài có thể chứa mã do người khác kiểm soát. Nếu pipeline chạy mã đó trong môi trường có secret hoặc quyền ghi, mã độc có thể lấy cắp credential hoặc thay đổi tài nguyên.

Với sự kiện không đáng tin cậy, giới hạn quyền, không cấp secret nhạy cảm, tách job kiểm tra khỏi job phát hành và yêu cầu phê duyệt cho môi trường được bảo vệ. Cần đọc kỹ điều kiện trigger và nguồn sự kiện, không chỉ tên nhánh.

## 11. Đọc DSL dạng mã

Một số hệ thống cho phép định nghĩa pipeline bằng ngôn ngữ lập trình hoặc DSL có cú pháp gần với ngôn ngữ lập trình. Khi đó, ngoài các khái niệm pipeline, cần đọc thêm cấu trúc điều khiển của mã.

Ví dụ giả định:

~~~groovy
pipeline {
    agent { label 'linux-builder' }

    stages {
        stage('Build') {
            steps {
                sh './gradlew assemble'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew test'
            }
        }
    }
}
~~~

Đoạn minh họa dùng hình thức DSL kiểu Groovy để thể hiện một pipeline gồm agent và hai stage. Cú pháp cụ thể, từ khóa hợp lệ và hành vi thực thi phụ thuộc công cụ; không nên sao chép ví dụ khái niệm vào dự án mà chưa kiểm tra phiên bản và tài liệu.

Khi đọc DSL dạng mã, hãy tìm:

- **Khai báo:** pipeline, stage, job, agent hoặc node được tạo ở đâu?
- **Khối lồng nhau:** một block định nghĩa phạm vi cấu hình hay phạm vi thực thi?
- **Hàm và plugin:** hàm nào là API của nền tảng, hàm nào là hàm do nhóm tự viết?
- **Biến và tham số:** giá trị được truyền qua đối số, biến toàn cục hay môi trường?
- **Điều khiển luồng:** if, loop, function hoặc exception có làm thay đổi thứ tự job không?
- **Tác dụng phụ:** mã có sửa workspace, gọi API, tạo artifact hoặc triển khai không?
- **Thư viện dùng chung:** logic nào nằm ngoài file pipeline và phiên bản nào được nạp?

DSL dạng mã linh hoạt hơn cấu hình khai báo, nhưng có thể khó hiểu nếu logic điều phối bị ẩn trong nhiều hàm, thư viện hoặc nhánh điều kiện. Ưu tiên cấu trúc khai báo rõ ràng cho luồng chuẩn; chỉ dùng logic tùy biến khi có lý do cụ thể và có thể kiểm thử.

## 12. Cách đọc một tệp pipeline từ đầu đến cuối

Có thể dùng trình tự sau để review mà không bị sa vào từng dòng lệnh ngay từ đầu:

**Bước 1: Xác định nền tảng và phiên bản.** Tìm loại runner, phiên bản schema hoặc plugin, cách pipeline được nạp và tài liệu tham chiếu. Nếu chưa biết nền tảng, không thể kết luận khóa nào là hợp lệ.

**Bước 2: Đọc phạm vi và trigger.** Xác định pipeline áp dụng cho repository, nhánh, tag, đường dẫn và sự kiện nào. Kiểm tra cả trigger thủ công và trigger từ pipeline khác.

**Bước 3: Vẽ danh sách job và quan hệ phụ thuộc.** Tìm stage, job, step, depends_on, needs hoặc cấu trúc tương đương. Phân biệt thứ tự văn bản với thứ tự scheduler thực thi.

**Bước 4: Kiểm tra môi trường chạy.** Xác định runner, image, công cụ, phiên bản runtime, workspace và quyền truy cập mạng.

**Bước 5: Theo dõi dữ liệu.** Xác định đầu vào, biến, secret, cache, artifact và đầu ra của từng job. Kiểm tra định danh artifact có gắn với đúng commit và lần chạy không.

**Bước 6: Đọc điều kiện và xử lý lỗi.** Tìm if, rules, when, retry, timeout, continue-on-error, finally hoặc post-action tương đương. Xem điều gì xảy ra khi job bị bỏ qua, thất bại hoặc bị hủy.

**Bước 7: Kiểm tra quyền và môi trường bảo vệ.** Xác định job nào có thể ghi repository, phát hành package, truy cập secret hoặc triển khai production. Kiểm tra nguồn sự kiện có đáng tin cậy không.

**Bước 8: Xác minh cách tái sử dụng.** Tìm template, include, extends, anchor, shared library hoặc action bên ngoài. Xác định phiên bản và nguồn của thành phần được tái sử dụng.

**Bước 9: Kiểm tra bằng công cụ.** Dùng validator hoặc linter đúng nền tảng, chạy kiểm tra cấu hình nếu có, và xem pipeline thực tế trên một thay đổi thử nghiệm an toàn. Kiểm tra cú pháp chỉ là bước đầu; cần xác minh luồng và quyền thực thi.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| YAML hợp lệ nghĩa là pipeline chạy được | YAML chỉ xác nhận cú pháp; schema và ngữ nghĩa còn phải được kiểm tra |
| Khóa có tên dễ hiểu chắc chắn được nền tảng hỗ trợ | Khóa phải tồn tại trong schema của đúng công cụ và phiên bản |
| Job viết trước sẽ chạy trước | Scheduler dựa vào dependency, stage và điều kiện |
| Hai job dùng chung workspace | Điều đó phụ thuộc loại runner và cơ chế workspace |
| Cache là artifact phát hành | Cache có thể bị loại bỏ; artifact cần định danh và lưu trữ có chủ đích |
| Step chạy lỗi luôn làm job thất bại | Có thể có retry, điều kiện cho phép lỗi hoặc xử lý lỗi riêng |
| Biến CI giống biến shell | Cú pháp và thời điểm nội suy có thể khác nhau |
| Secret được che trong log là an toàn | Step có secret vẫn có thể ghi, mã hóa hoặc gửi giá trị ra ngoài |
| Tệp pipeline chỉ là cấu hình | Nó điều khiển mã và quyền được thực thi trong hạ tầng CI/CD |
| Tái sử dụng template luôn làm cấu hình an toàn hơn | Template có thể ẩn logic, quyền và nguồn phụ thuộc cần được review |

## 14. Nguyên tắc thực hành khi đọc và review

- Bắt đầu từ cấu trúc tổng thể, sau đó lần theo dependency và dữ liệu; cuối cùng mới đọc sâu từng lệnh.
- Phân biệt cú pháp YAML với schema và hành vi do DSL quy định.
- Không suy ra thứ tự thực thi chỉ từ vị trí dòng trong file.
- Xác định runner, quyền, secret và nguồn sự kiện trước khi đánh giá độ an toàn.
- Kiểm tra cách artifact được tạo, định danh, lưu trữ và chuyển qua các môi trường.
- Dùng tên biến và job có ý nghĩa; tránh điều kiện lồng nhau khó kiểm tra.
- Tách logic dùng chung thành template hoặc thư viện có phiên bản và chủ sở hữu rõ ràng.
- Chạy validator/linter phù hợp và kiểm tra hành vi trên pipeline thử nghiệm trước khi áp dụng thay đổi có ảnh hưởng rộng.

Khi đọc được cấu trúc YAML hoặc DSL ở mức khái niệm, ta có thể giải thích một pipeline đang phản ứng với sự kiện nào, các job phối hợp ra sao, dữ liệu đi qua những bước nào và quyền nào được sử dụng. Khả năng đó giúp review pipeline như một phần mã nguồn có thể kiểm soát, kiểm thử và truy vết, thay vì xem nó như một tệp cấu hình khó hiểu.
