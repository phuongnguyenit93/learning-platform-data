# Phân biệt Web Flow với WebFlux, Spring Batch và bộ máy quy trình nghiệp vụ

Spring có nhiều công nghệ dùng từ “flow”, “reactive”, “job” hoặc “workflow”, nhưng chúng giải quyết những bài toán khác nhau. **Spring Web Flow** điều khiển hành trình tương tác nhiều bước của người dùng trên giao diện web. **Spring WebFlux** cung cấp mô hình lập trình web reactive, non-blocking. **Spring Batch** xử lý khối lượng dữ liệu và công việc nền theo job/step. **Bộ máy quy trình nghiệp vụ** (business process/workflow engine) điều phối quy trình dài hạn giữa con người, hệ thống, thời gian và sự kiện.

Bài thuộc chương **Bản đồ Web Flow** của module **SPRING_WEB_FLOW**. Mục tiêu là giúp bạn chọn đúng công nghệ, hiểu ranh giới của từng thành phần và biết cách phối hợp chúng trong một hệ thống. Ta sẽ dùng một quy trình đăng ký dịch vụ làm ví dụ: người dùng nhập thông tin, hệ thống kiểm tra, nhân viên duyệt, dữ liệu được nhập vào hệ thống và thông báo được gửi.

Ví dụ kỹ thuật dựa trên Spring Web Flow 3.x, Spring Framework 6.x, Spring WebFlux và Spring Batch hiện đại. Cú pháp cấu hình cụ thể có thể thay đổi theo phiên bản và cách tích hợp; hãy đối chiếu BOM/dependency của dự án trước khi sao chép nguyên mẫu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả bài toán cốt lõi mà Spring Web Flow giải quyết.
2. Phân biệt Web Flow với WebFlux dù tên gọi gần giống nhau.
3. Phân biệt một hành trình tương tác với một batch job chạy nền.
4. Nhận biết khi nào cần BPMN/workflow engine để điều phối quy trình nghiệp vụ dài hạn.
5. So sánh bốn công nghệ theo mô hình thực thi, trạng thái, độ bền dữ liệu và cách tương tác.
6. Chọn nơi chịu trách nhiệm cho UI navigation, reactive I/O, batch processing và business orchestration.
7. Thiết kế kiến trúc phối hợp các công nghệ qua service/API và sự kiện.
8. Tránh các anti-pattern như dùng flowScope làm kho dữ liệu lâu dài hoặc dùng WebFlux để thay một workflow engine.
9. Xác định cách kiểm thử và vận hành phù hợp cho từng loại workload.

## 2. Bức tranh tổng quan

Hãy bắt đầu bằng câu hỏi: **điều gì đang được điều khiển?**

| Công nghệ | Đối tượng được điều khiển | Bài toán chính |
| --- | --- | --- |
| **Spring Web Flow** | Hành trình tương tác của một người dùng trong web application | Nhiều màn hình, event, transition, form binding, validation, browser history |
| **Spring WebFlux** | Xử lý HTTP request/response và luồng dữ liệu reactive | I/O non-blocking, streaming, backpressure, concurrency |
| **Spring Batch** | Job và các step xử lý dữ liệu | Import/export, ETL, đối soát, xử lý theo lô, restart/retry |
| **BPM/workflow engine** | Instance của một quy trình nghiệp vụ | Phê duyệt, human task, timer, message, SLA, audit, orchestration dài hạn |

~~~mermaid
flowchart TB
    U["Người dùng trên trình duyệt"]
    WF["Spring Web Flow<br/>Điều khiển hành trình UI"]
    RX["Spring WebFlux<br/>HTTP reactive và streaming"]
    BE["Business services"]
    BPM["BPM / Workflow engine<br/>Điều phối quy trình nghiệp vụ"]
    BA["Spring Batch<br/>Job xử lý dữ liệu"]
    DB[("Database / message broker")]

    U --> WF
    U --> RX
    WF --> BE
    RX --> BE
    BE <--> BPM
    BPM --> BE
    BE --> DB
    BPM --> DB
    BPM --> BA
    BA --> DB
~~~

Sơ đồ cho thấy chúng có thể cùng xuất hiện trong một kiến trúc. Web Flow không cần thay WebFlux; Batch không cần thay BPM engine. Mỗi thành phần nhận một trách nhiệm cụ thể và giao tiếp qua service, API, message hoặc dữ liệu bền vững.

## 3. Spring Web Flow: điều khiển hành trình nhiều bước trên web

Spring Web Flow là framework để định nghĩa và thực thi một **flow** gồm các state và transition. Nó phù hợp với hành trình có nhiều bước, nơi ứng dụng cần nhớ người dùng đang ở đâu, nhận event nào, bind dữ liệu form ra sao và chuyển sang bước tiếp theo theo quy tắc đã khai báo.

Ví dụ hành trình đăng ký:

~~~mermaid
stateDiagram-v2
    [*] --> enterProfile
    enterProfile --> choosePlan: next
    choosePlan --> review: next
    review --> enterProfile: back
    review --> submit: confirm
    submit --> completed: accepted
    submit --> review: rejected
    completed --> [*]
~~~

Các khái niệm cốt lõi:

- **Flow definition:** bản định nghĩa state, event, transition, action và outcome.
- **Flow execution:** một lần chạy cụ thể của flow definition.
- **State:** bước hiện tại, ví dụ view-state hoặc action-state.
- **Event:** tín hiệu như next, back, confirm hoặc cancel.
- **Transition:** quy tắc xử lý event và chọn state tiếp theo.
- **Flow scope:** dữ liệu gắn với một flow execution.
- **Execution repository:** nơi quản lý execution và snapshot phục vụ tiếp tục/quay lại.

### 3.1. Ví dụ flow XML

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="registration"
         class="com.example.registration.RegistrationDraft"/>

    <view-state id="profile"
                view="registration/profile"
                model="registration">
        <transition on="next" to="plan"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="plan" view="registration/plan">
        <transition on="back" to="profile" validate="false"/>
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="registration/review">
        <transition on="back" to="plan" validate="false"/>
        <transition on="confirm" to="submit"/>
    </view-state>

    <action-state id="submit">
        <evaluate expression="registrationService.submit(registration)"/>
        <transition on="success" to="completed"/>
        <transition on="rejected" to="review"/>
    </action-state>

    <end-state id="completed"/>
    <end-state id="cancelled"/>
</flow>
~~~

Flow định nghĩa đường đi của giao diện. Action-state gọi service nghiệp vụ; service chịu trách nhiệm transaction, authorization và tính đúng đắn của dữ liệu. Không nên biến flow execution thành nơi duy nhất lưu một đăng ký đã được xác nhận.

### 3.2. Khi nào Web Flow phù hợp?

- Quy trình web có nhiều màn hình và nhánh điều hướng.
- Form dài cần chia bước, validate theo bước và quay lại chỉnh sửa.
- Một execution cần giữ draft tạm trong lúc người dùng tương tác.
- Browser Back/refresh cần được xử lý theo flow execution/history.
- Các bước có event và điều kiện chuyển tiếp tương đối rõ.

### 3.3. Khi nào Web Flow không phải công cụ chính?

- Xử lý hàng triệu bản ghi theo lô.
- Streaming dữ liệu liên tục với backpressure.
- Quy trình nghiệp vụ kéo dài nhiều ngày, có timer, message correlation, SLA và human task độc lập với session trình duyệt.
- Điều phối nhiều dịch vụ phân tán với retry, compensation và audit quy trình ở cấp doanh nghiệp.

Web Flow có thể gọi những hệ thống đó, nhưng không tự biến thành batch engine, reactive runtime hay BPM engine.

## 4. Spring WebFlux: mô hình lập trình web reactive

Spring WebFlux là web framework reactive của Spring. Nó hỗ trợ xây dựng ứng dụng HTTP theo mô hình non-blocking, dùng Reactive Streams và các kiểu như `Mono`, `Flux`. Mục tiêu là xử lý I/O bất đồng bộ và luồng dữ liệu hiệu quả, đặc biệt khi workload có nhiều thao tác I/O hoặc cần streaming.

### 4.1. Ví dụ WebFlux controller

~~~java
@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    private final RegistrationQueryService queryService;

    public RegistrationController(RegistrationQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    public Mono<RegistrationView> getOne(@PathVariable String id) {
        return queryService.findById(id);
    }

    @GetMapping("/events")
    public Flux<RegistrationEvent> events() {
        return queryService.streamRecentEvents();
    }
}
~~~

`Mono<T>` biểu diễn tối đa một kết quả bất đồng bộ; `Flux<T>` biểu diễn một chuỗi 0..N phần tử. WebFlux cũng có functional endpoint với RouterFunction/HandlerFunction.

### 4.2. WebFlux không phải “Web Flow phiên bản reactive”

Hai tên có chữ “Web” và “Flow” nhưng mục tiêu khác nhau:

| Tiêu chí | Spring Web Flow | Spring WebFlux |
| --- | --- | --- |
| Mục tiêu | Điều khiển hành trình nhiều bước | Xử lý HTTP reactive |
| Đơn vị chính | Flow execution/state/event | Request, publisher, signal |
| Trạng thái | Có state machine và flow scope | Không tự cung cấp workflow state machine |
| Điều hướng | Transition trong flow definition | Router/controller quyết định response |
| UI nhiều bước | Có cơ chế chuyên biệt | Tự xây dựng bằng API, client state hoặc service |
| Streaming/backpressure | Không phải mục tiêu chính | Là năng lực cốt lõi |
| Stack web | Servlet/Spring MVC integration | Reactive stack, thường chạy trên runtime reactive |

WebFlux không tự lưu “người dùng đang ở bước 3 của wizard” và không cung cấp transition XML, flow execution repository hay browser history policy như Web Flow. Muốn xây wizard với WebFlux, đội phát triển phải thiết kế trạng thái và persistence của quy trình riêng, hoặc dùng một workflow/state-machine service phù hợp.

**Lưu ý tích hợp:** Spring Web Flow cung cấp integration theo Servlet API/Spring MVC, chẳng hạn FlowHandlerMapping và FlowHandlerAdapter. Nó không phải một thành phần reactive-native có thể gắn trực tiếp vào WebFlux runtime như một controller WebFlux. Nếu hệ thống dùng WebFlux cho API và vẫn cần Web Flow cho wizard, hãy đặt chúng ở ranh giới ứng dụng/service phù hợp, hoặc để một ứng dụng Spring MVC/Web Flow riêng phục vụ UI.

### 4.3. WebFlux không làm cho mọi code tự động non-blocking

Nếu controller reactive gọi JDBC blocking, đọc file blocking hoặc gọi một thư viện đồng bộ trên event-loop, ứng dụng vẫn có thể bị chặn. Cần chọn driver/client reactive phù hợp hoặc cô lập thao tác blocking trên scheduler thích hợp. Không nên chuyển sang WebFlux chỉ vì nghĩ rằng nó luôn nhanh hơn MVC.

### 4.4. Khi nào WebFlux phù hợp?

- API có nhiều I/O bất đồng bộ.
- Streaming event hoặc dữ liệu theo thời gian thực.
- Gateway hoặc backend tổng hợp nhiều reactive service.
- Ứng dụng cần backpressure khi producer/consumer có tốc độ khác nhau.
- Stack dữ liệu hỗ trợ reactive end-to-end.

Nếu ứng dụng chủ yếu dùng JDBC, xử lý request/response thông thường và không có nhu cầu streaming/concurrency đặc thù, Spring MVC có thể đơn giản và phù hợp hơn.

## 5. Spring Batch: xử lý job và dữ liệu theo lô

Spring Batch là framework xử lý batch workload. Một job gồm một hoặc nhiều step; step có thể dùng chunk-oriented processing hoặc tasklet. Framework cung cấp cơ chế quản lý job execution, step execution, checkpoint/restart, retry/skip và metadata qua JobRepository.

### 5.1. Ví dụ job import

~~~java
@Configuration
public class ImportJobConfiguration {

    @Bean
    Job importCustomers(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importCustomers", jobRepository)
            .start(importStep)
            .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<CustomerRow> reader,
            ItemProcessor<CustomerRow, Customer> processor,
            ItemWriter<Customer> writer) {
        return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerRow, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
    }
}
~~~

Đây là ví dụ chunk processing: đọc, xử lý và ghi theo nhóm 500 item trong transaction boundary của chunk. Kích thước chunk là lựa chọn vận hành, không phải con số cố định cho mọi workload.

### 5.2. Spring Batch không phải Web Flow

| Tiêu chí | Spring Web Flow | Spring Batch |
| --- | --- | --- |
| Mục tiêu | Hành trình tương tác người dùng | Xử lý công việc theo lô |
| Trigger | HTTP event từ người dùng | Scheduler, operator, API/job launcher |
| Đơn vị chính | Flow execution | JobExecution/StepExecution |
| Trạng thái | State và snapshot của UI flow | Metadata job, checkpoint và execution status |
| Thời lượng | Thường gắn với phiên tương tác; có thể kéo dài theo repository | Có thể chạy lâu ở background |
| Lỗi | Render lỗi, transition khác, restart flow theo policy | Retry, skip, restart job/step theo cấu hình |
| Kết quả | UI state/outcome | File, database rows, report, event hoặc kết quả batch |

Spring Batch cũng có khái niệm **job flow** để nối các step theo điều kiện. Từ “flow” ở đây chỉ cấu trúc điều khiển bên trong batch job; nó không phải Spring Web Flow và không quản lý trình duyệt hay form nhiều bước.

### 5.3. Khi nào Spring Batch phù hợp?

- Import/export dữ liệu lớn.
- Đồng bộ dữ liệu định kỳ.
- ETL, chuẩn hóa và kiểm tra dữ liệu.
- Đối soát giao dịch theo ngày.
- Tính toán báo cáo hoặc tổng hợp dữ liệu.
- Xử lý lại dữ liệu thất bại có checkpoint/restart.

Một flow web có thể cho người dùng upload file và khởi chạy batch job. Web Flow quản lý màn hình upload/confirm; Spring Batch xử lý file ở background; UI truy vấn trạng thái job qua service/API.

## 6. Bộ máy quy trình nghiệp vụ (BPM/workflow engine)

BPM/workflow engine điều phối một **quy trình nghiệp vụ** có thể kéo dài qua nhiều người, nhiều hệ thống và nhiều thời điểm. Nhiều engine hỗ trợ BPMN 2.0, human task, timer, message event, gateway, process variable, audit trail, retry và quản lý process instance.

Ví dụ phê duyệt đăng ký dịch vụ:

~~~mermaid
flowchart TD
    A["Khách hàng gửi đăng ký"] --> B["Tạo process instance"]
    B --> C["Kiểm tra tự động"]
    C --> D{"Đủ điều kiện?"}
    D -->|"Không"| R["Từ chối và thông báo"]
    D -->|"Có"| H["Tạo human task cho nhân viên"]
    H --> W["Chờ nhân viên xử lý"]
    W --> T{"Quyết định"}
    T -->|"Duyệt"| P["Kích hoạt dịch vụ"]
    T -->|"Từ chối"| R
    P --> N["Gửi thông báo"]
    N --> E["Kết thúc process"]
    R --> E
~~~

Process có thể chờ nhiều giờ hoặc nhiều ngày. Người dùng có thể logout, đổi thiết bị hoặc đóng trình duyệt; process instance vẫn tồn tại trong engine và chờ message/task tiếp theo.

### 6.1. Các khái niệm thường gặp

- **Process definition:** mô hình quy trình, thường được biểu diễn bằng BPMN.
- **Process instance:** một lần chạy của quy trình.
- **User task:** công việc cần một người hoặc nhóm người thực hiện.
- **Service task/worker:** công việc được hệ thống thực hiện.
- **Gateway:** điều kiện rẽ nhánh hoặc đồng bộ.
- **Timer event:** kích hoạt theo thời gian hoặc deadline.
- **Message/signal event:** tiếp tục quy trình khi nhận sự kiện.
- **Process variable:** dữ liệu phục vụ quyết định và điều phối.
- **Audit/history:** lịch sử các bước, quyết định và người thực hiện.

### 6.2. BPM engine khác Web Flow ở đâu?

| Tiêu chí | Spring Web Flow | BPM/workflow engine |
| --- | --- | --- |
| Trọng tâm | Tương tác web trong một flow execution | Vòng đời quy trình nghiệp vụ |
| Người tham gia | Thường là người dùng đang tương tác với ứng dụng | Có thể nhiều người, nhóm, hệ thống |
| Mô hình | State, event, transition | BPMN/process definition hoặc DSL riêng |
| Chờ lâu | Phụ thuộc repository/session/execution policy | Thường là năng lực cốt lõi, process tồn tại độc lập |
| Human task | Có thể hiển thị form trong một flow | Thường có task assignment, candidate group, due date |
| Timer/message | Không phải năng lực orchestration doanh nghiệp chính | Thường được hỗ trợ trực tiếp |
| Audit nghiệp vụ | Cần tự thiết kế thêm | Thường có process history/audit |
| Gắn với trình duyệt | Có continuation URL và view lifecycle | Không phụ thuộc một tab hay browser session |

Web Flow có thể làm giao diện cho một bước của BPM process, nhưng BPM engine nên giữ quyền sở hữu process instance, task assignment và lifecycle dài hạn. Không dùng flowScope làm bản sao thay thế process variables hoặc audit log.
## 7. Bảng so sánh bốn công nghệ

Bảng sau tổng hợp những khác biệt có ảnh hưởng trực tiếp tới quyết định kiến trúc:

| Tiêu chí | Web Flow | WebFlux | Spring Batch | BPM/workflow engine |
| --- | --- | --- | --- | --- |
| Bài toán chính | Multi-step UI | Reactive web I/O | Batch workload | Business process orchestration |
| Đơn vị điều khiển | Flow execution | HTTP request/publisher | Job/step execution | Process instance/task |
| Trigger | User event | HTTP request, stream subscription | Job launch/schedule | Message, timer, user task, service event |
| Mô hình điều khiển | State/event/transition | Reactive pipeline/router | Step/chunk/tasklet/job flow | BPMN/DSL, gateway, task/event |
| Trạng thái | Execution repository và scopes | Không có workflow persistence mặc định | JobRepository/checkpoint | Process database/history |
| Tương tác người dùng | View-state, form, browser history | API, streaming, reactive response | Thường qua launcher/monitor UI | User task/inbox/task form |
| Chạy nền | Không phải mục tiêu chính | Có thể phục vụ reactive request/stream | Có | Có |
| Chờ nhiều ngày | Không phải lựa chọn tự nhiên | Không nên giữ HTTP request mở để chờ | Job có thể chạy dài nhưng không thay human workflow | Năng lực thường có sẵn |
| Retry/restart | Theo flow/repository và logic ứng dụng | Theo request/client/service policy | Job/step retry, restart theo cấu hình | Process retry, timer, incident policy |
| Audit quy trình | Cần bổ sung | Cần bổ sung | Job metadata | Thường là tính năng chính |
| Backpressure | Không | Có | Chunk/partition throttling theo batch model | Không phải khái niệm cốt lõi |
| Phù hợp với | Wizard, checkout, onboarding | API, gateway, SSE/WebSocket, streaming | Import, ETL, reconciliation | Approval, case, orchestration |

### 7.1. Chúng có thể thay thế nhau ở điểm nào?

Có một số phần giao nhau nhưng không đồng nghĩa:

- Web Flow và BPM engine đều có state/transition, nhưng quy mô vòng đời và đối tượng điều khiển khác nhau.
- WebFlux và Web Flow đều xử lý request web, nhưng WebFlux không có state machine UI chuyên biệt.
- Spring Batch và BPM engine đều điều phối công việc, nhưng Batch tập trung vào data processing/job execution; BPM tập trung vào business process, human task và event.
- WebFlux có thể expose API để khởi chạy/quan sát Batch job hoặc BPM process; nó không thay thế execution engine.

## 8. Chọn công nghệ bằng câu hỏi quyết định

Thay vì bắt đầu từ tên framework, hãy bắt đầu từ yêu cầu:

~~~mermaid
flowchart TD
    A["Yêu cầu mới"] --> B{"Cần điều khiển nhiều bước UI<br/>trong một web interaction?"}
    B -->|"Có"| C["Spring Web Flow"]
    B -->|"Không"| D{"Cần HTTP reactive,<br/>streaming hoặc backpressure?"}
    D -->|"Có"| E["Spring WebFlux"]
    D -->|"Không"| F{"Cần xử lý dữ liệu/job<br/>theo lô?"}
    F -->|"Có"| G["Spring Batch"]
    F -->|"Không"| H{"Cần điều phối process dài hạn<br/>qua người, timer, message, hệ thống?"}
    H -->|"Có"| I["BPM / Workflow engine"]
    H -->|"Không"| J["Spring MVC/service thông thường<br/>hoặc công cụ phù hợp khác"]
~~~

Đây là hướng dẫn chọn điểm bắt đầu, không phải quy tắc loại trừ. Một hệ thống có thể cần cả bốn:

- Web Flow cho wizard tạo yêu cầu.
- BPM engine cho phê duyệt và SLA.
- Batch cho nhập dữ liệu hàng loạt.
- WebFlux cho API event stream hoặc gateway reactive.

### 8.1. Câu hỏi cần trả lời trước khi chọn

1. **Ai đang chờ?** Người dùng trên trang web, một job runner, hay một quy trình nghiệp vụ chờ nhiều vai trò?
2. **Trạng thái sống bao lâu?** Một vài phút tương tác, một job vài giờ, hay process nhiều ngày?
3. **Điều gì phải được lưu bền vững?** Draft UI, checkpoint dữ liệu, hay process/audit history?
4. **Điều gì kích hoạt bước tiếp theo?** Click của người dùng, HTTP signal, scheduler, message hay timer?
5. **Nếu process restart thì tiếp tục ở đâu?** Execution repository, JobRepository hay BPM process database?
6. **Có human task và SLA không?** Nếu có, BPM/workflow engine thường phù hợp hơn.
7. **Có streaming/backpressure không?** Nếu có, WebFlux có thể phù hợp cho lớp HTTP.

## 9. Ví dụ xuyên suốt: đăng ký dịch vụ và phê duyệt

Giả sử doanh nghiệp có quy trình:

1. Khách hàng nhập thông tin và chọn gói.
2. Khách hàng xem lại và gửi đăng ký.
3. Hệ thống kiểm tra dữ liệu, lưu đăng ký.
4. Nhân viên nhận task, xem hồ sơ và duyệt/từ chối.
5. Khi duyệt, hệ thống kích hoạt dịch vụ.
6. Dữ liệu đăng ký được nhập vào hệ thống khác theo batch.
7. Khách hàng xem trạng thái và nhận thông báo.

Không có một framework đơn lẻ nào phải sở hữu toàn bộ hành trình. Có thể phân chia như sau:

| Bước | Công nghệ phù hợp | Lý do |
| --- | --- | --- |
| Nhập hồ sơ nhiều màn hình | Web Flow | View-state, binding, validation, back/next |
| API truy vấn trạng thái | MVC hoặc WebFlux | Chọn theo nhu cầu I/O và streaming |
| Lưu hồ sơ và tạo process | Business service + BPM engine | Database commit và process start |
| Chờ nhân viên duyệt | BPM engine | Human task, assignment, due date |
| Import hồ sơ đã duyệt | Spring Batch | Job xử lý dữ liệu và restart |
| Stream cập nhật trạng thái | WebFlux (nếu cần reactive stream) | SSE/WebSocket hoặc Flux |

~~~mermaid
sequenceDiagram
    actor Customer as Khách hàng
    participant WF as Spring Web Flow
    participant S as Registration Service
    participant BPM as BPM Engine
    actor Clerk as Nhân viên
    participant Batch as Spring Batch
    participant API as WebFlux API

    Customer->>WF: Nhập hồ sơ và xác nhận
    WF->>S: submitRegistration(draft)
    S->>S: Transaction lưu hồ sơ
    S->>BPM: Start approval process
    BPM-->>S: processInstanceId
    S-->>WF: registrationId + processInstanceId
    WF-->>Customer: Trang đã tiếp nhận
    BPM->>Clerk: Tạo human task
    Clerk->>BPM: Duyệt hồ sơ
    BPM->>S: Approval outcome
    S->>Batch: Gửi job đồng bộ dữ liệu
    Customer->>API: Theo dõi trạng thái
    API-->>Customer: Event stream nếu được bật
~~~

Ở đây, Web Flow kết thúc sau khi đăng ký được tiếp nhận. BPM engine tiếp tục process ngay cả khi khách hàng đóng tab. Batch xử lý công việc dữ liệu độc lập; WebFlux chỉ tham gia nếu API/streaming reactive mang lại lợi ích.

## 10. Các mẫu tích hợp phù hợp

### 10.1. Web Flow gọi service rồi khởi động BPM process

Action của Web Flow gọi một application service:

~~~java
public String submit(RegistrationDraft draft) {
    Registration registration = registrationService.create(draft);
    approvalProcessService.start(registration.getId());
    return "success";
}
~~~

Đây là phác thảo để giải thích ranh giới. Trong triển khai thật, lưu registration và phát lệnh start process cần được thiết kế nhất quán. Nếu hai hệ thống dùng hai transaction khác nhau, cân nhắc transactional outbox: transaction lưu hồ sơ đồng thời ghi event; worker gửi event để start BPM process và có cơ chế retry/idempotency.

### 10.2. WebFlux expose trạng thái và event stream

Một API reactive có thể stream các cập nhật trạng thái:

~~~java
@RestController
@RequestMapping("/api/registrations")
class RegistrationStatusController {

    private final RegistrationEventService events;

    @GetMapping(value = "/{id}/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<RegistrationStatus>> events(
            @PathVariable String id) {
        return events.streamForAuthorizedRegistration(id)
            .map(status -> ServerSentEvent.builder(status).build());
    }
}
~~~

`Mono<T>` biểu diễn tối đa một kết quả bất đồng bộ; `Flux<T>` biểu diễn một chuỗi 0..N phần tử. `streamForAuthorizedRegistration` phải xác thực quyền đọc registration trước khi phát event và cần quản lý subscription, timeout, reconnect, backpressure cũng như quyền truy cập trong suốt stream. Nếu event stream không cần thiết, endpoint MVC thông thường có thể đơn giản hơn.

### 10.3. BPM engine khởi chạy Spring Batch

Khi process được duyệt, một service hoặc worker có thể khởi chạy batch job với tham số nhận diện nghiệp vụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("registrationId", registrationId)
    .addString("requestId", synchronizationRequestId)
    .toJobParameters();

jobLauncher.run(syncRegistrationJob, parameters);
~~~

Đảm bảo job parameters xác định đúng tính duy nhất của lần chạy theo yêu cầu. Khi process gửi lệnh nhiều lần, service cần idempotency để tránh khởi chạy các lần đồng bộ trùng ngoài ý muốn.

### 10.4. BPM user task có thể dùng UI riêng

BPM engine thường cung cấp API để query task, claim/assign task và complete task. Giao diện xử lý task có thể là Spring MVC, WebFlux hoặc một frontend độc lập. Web Flow có thể điều khiển form nhiều bước trong UI đó, nhưng engine vẫn sở hữu task state và quyền assignment.

## 11. Ranh giới dữ liệu và quyền sở hữu trạng thái

Sai lầm kiến trúc thường bắt đầu khi hai thành phần cùng nghĩ mình là nguồn sự thật cho một trạng thái.

| Loại trạng thái | Nơi nên sở hữu | Ví dụ |
| --- | --- | --- |
| Vị trí hiện tại trong wizard | Web Flow execution | Đang ở bước review |
| Giá trị form chưa gửi | Flow scope hoặc draft store | Tên, lựa chọn gói |
| Hồ sơ đã gửi | Database nghiệp vụ | Registration ID, trạng thái SUBMITTED |
| Task đang chờ ai duyệt | BPM engine | Task assignee, candidate group, due date |
| Tiến độ import/export | Spring Batch JobRepository | JobExecution, StepExecution |
| Kết quả event stream | Event store/broker hoặc read model | Trạng thái mới nhất để phát cho client |

### 11.1. FlowScope không phải database

FlowScope phù hợp với dữ liệu cần tồn tại trong một flow execution. Nó không phải kho dữ liệu dài hạn:

- Có thể mất khi session/execution hết hạn hoặc repository dọn execution.
- Không phải nguồn audit có thể truy vấn độc lập.
- Không nên giữ credential, token hoặc bí mật thanh toán.
- Không nên giữ entity graph lớn hoặc object không tương thích serialization.

Khi dữ liệu cần tồn tại sau khi flow kết thúc, lưu vào database/service.

### 11.2. Process variable không phải bản sao toàn bộ domain model

BPM engine thường cần process variables để điều phối và đánh giá gateway. Chỉ lưu dữ liệu cần cho quy trình; không nhất thiết serialize toàn bộ entity graph. Dữ liệu nghiệp vụ chính vẫn nên nằm trong database của domain service, process giữ ID và thông tin điều phối cần thiết.

### 11.3. Job metadata không phải business record

Spring Batch JobRepository lưu metadata của lần chạy và checkpoint. Nó giúp restart job, nhưng không thay database nghiệp vụ lưu kết quả import hoặc lịch sử giao dịch.

## 12. Lỗi và phục hồi khác nhau theo công nghệ

| Vấn đề | Web Flow | WebFlux | Spring Batch | BPM engine |
| --- | --- | --- | --- | --- |
| Người dùng gửi lại request | Kiểm tra execution key, event và idempotency service | Thiết kế retry/idempotency ở API/service | Không phải trigger job mặc định | Correlate message/task command theo process |
| Session/browser mất | Execution có thể hết hạn; đưa người dùng tới recovery | HTTP connection kết thúc; client reconnect nếu cần | Không ảnh hưởng job đang chạy | Process instance tiếp tục độc lập |
| Process/job restart | Restore execution/snapshot theo repository | Reconnect/retry theo client và stream contract | Restart job/step từ repository/checkpoint | Engine khôi phục process instance |
| Một bước nghiệp vụ thất bại | Transition sang nhánh lỗi hoặc giữ view | Trả error signal/HTTP response | Retry/skip/rollback theo step | Incident/retry/compensation theo engine |
| Tác vụ bên ngoài commit nhưng response mất | Tra cứu theo idempotency key | Tra cứu theo request ID | Job restart cần writer idempotent | Worker command cần deduplication |

Không có một chiến lược retry duy nhất cho cả bốn công nghệ. Hãy đặt retry tại ranh giới có đủ thông tin để xác định thao tác có thể lặp hay không.

## 13. Bảo mật và phân quyền

Mỗi công nghệ có ranh giới bảo mật riêng:

- **Web Flow:** bảo vệ flow/state/transition và kiểm tra quyền trên tài nguyên ở service.
- **WebFlux:** bảo vệ endpoint, subscription và từng resource; không phát event cho người dùng không có quyền.
- **Spring Batch:** giới hạn ai được launch/restart/stop job; bảo vệ job parameters và dữ liệu đầu vào.
- **BPM engine:** kiểm soát quyền start process, claim task, complete task, delegate và xem process history.

Ẩn nút trên giao diện không phải authorization. Một request trực tiếp, API call hoặc job launcher có thể bỏ qua giao diện. Luôn kiểm tra quyền ở server-side service hoặc engine API.

## 14. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| WebFlux là phiên bản reactive của Web Flow | WebFlux là web framework reactive; không có flow state machine UI tương đương |
| Spring Batch có “flow” nên giống Web Flow | Batch flow nối các step trong job, không điều khiển browser/form |
| Web Flow có state nên là BPM engine | State của UI flow không tự cung cấp human task, SLA, timer và audit process đầy đủ |
| WebFlux giữ Mono/Flux là đủ cho workflow dài hạn | Publisher không thay thế durable process state |
| Session còn thì mọi execution còn | Execution có thể bị loại do giới hạn riêng |
| Job hoàn tất nghĩa quy trình nghiệp vụ hoàn tất | Job chỉ hoàn tất phần batch; BPM process có thể còn chờ task hoặc event |
| BPM engine phải hiển thị UI | Engine điều phối process; UI có thể do ứng dụng xây |
| Dùng một framework cho toàn bộ hệ thống sẽ đơn giản hơn | Có thể tạo coupling và buộc công nghệ làm việc ngoài thế mạnh |

### 14.1. Một quy tắc thực tế

Nếu yêu cầu mô tả **người dùng bấm nút nào và màn hình kế tiếp là gì**, hãy xem Web Flow.

Nếu yêu cầu mô tả **request được xử lý bất đồng bộ và stream dữ liệu thế nào**, hãy xem WebFlux.

Nếu yêu cầu mô tả **hàng nghìn hoặc hàng triệu record được đọc, biến đổi và ghi ra sao**, hãy xem Spring Batch.

Nếu yêu cầu mô tả **ai phải làm bước nào, trước hạn nào, chờ sự kiện gì và điều gì xảy ra nếu quá hạn**, hãy xem BPM/workflow engine.

## 15. Kiểm thử và vận hành theo workload

### 15.1. Web Flow

- Test flow definition, state, event và transition.
- Test binding/validation theo từng bước.
- Test browser Back, refresh, duplicate tab và execution timeout.
- Test repository/snapshot policy.
- Test authorization tại flow và service.

### 15.2. WebFlux

- Test HTTP status, body và reactive signal.
- Dùng WebTestClient cho endpoint reactive.
- Test cancellation, timeout, retry và error mapping.
- Test backpressure/stream lifecycle khi workload yêu cầu.
- Kiểm tra không gọi blocking I/O trên event-loop.

### 15.3. Spring Batch

- Test reader, processor, writer.
- Test job/step execution và restart.
- Test retry/skip, rollback và checkpoint.
- Test job parameters và tính idempotent của writer.
- Theo dõi read/write/skip count, duration và failure.

### 15.4. BPM/workflow engine

- Test process path, gateway và message correlation.
- Test claim/complete task, assignment và quyền.
- Test timer, deadline, retry và compensation.
- Test process restart sau engine restart.
- Theo dõi process instance đang chờ, task quá hạn và incident.

## 16. Lộ trình thiết kế một hệ thống phối hợp các công nghệ

Với ví dụ đăng ký dịch vụ, có thể triển khai theo trình tự:

1. Xây domain service và database để lưu đăng ký; định nghĩa trạng thái nghiệp vụ có thẩm quyền.
2. Dùng Web Flow cho wizard nhập liệu và review, giữ draft tạm theo execution.
3. Khi xác nhận, gọi application service có transaction và idempotency; trả registration ID.
4. Phát event qua transactional outbox để khởi động BPM process.
5. BPM engine tạo human task cho nhân viên và quản lý deadline/decision.
6. Khi được duyệt, process gọi service kích hoạt và yêu cầu đồng bộ.
7. Spring Batch xử lý đồng bộ dữ liệu lớn, lưu JobExecution và checkpoint.
8. Nếu cần cập nhật gần real-time, WebFlux cung cấp API/SSE để client theo dõi trạng thái.
9. Mọi thao tác tra cứu/duyệt đều kiểm tra authorization ở server.
10. Quan sát riêng flow execution, process instance, batch job và reactive stream.

### 16.1. Chọn ranh giới đồng bộ hay bất đồng bộ

Không phải mọi lời gọi giữa các thành phần đều cần message broker. Nếu người dùng cần biết ngay hồ sơ được lưu thành công, service có thể commit đồng bộ rồi trả ID. Nếu cần khởi động process/batch sau commit, outbox/event giúp tách thời gian và retry. Chọn đồng bộ hay bất đồng bộ dựa trên yêu cầu latency, độ tin cậy và khả năng phục hồi.

## 17. Bài tập thực hành

### Bài A — phân loại yêu cầu

Phân loại các yêu cầu sau vào Web Flow, WebFlux, Spring Batch hoặc BPM engine:

- Wizard mở tài khoản gồm năm màn hình.
- API stream trạng thái xử lý qua Server-Sent Events.
- Import 2 triệu dòng CSV mỗi đêm.
- Hồ sơ chờ trưởng phòng duyệt trong ba ngày.
- Form cho người dùng sửa thông tin trước khi gửi.
- Đối soát giao dịch theo ngày và restart từ checkpoint.

**Đạt khi:** giải thích được đối tượng được điều khiển và vì sao công nghệ phù hợp.

### Bài B — tách UI flow và business process

Tạo flow XML gồm profile, review, completed. Khi submit, gọi service lưu Registration và nhận registration ID. Sau khi flow kết thúc, mở một flow mới để tra cứu trạng thái hồ sơ.

**Đạt khi:** trạng thái đã gửi không phụ thuộc execution của wizard ban đầu.

### Bài C — launch batch từ service

Tạo job import dữ liệu đã duyệt. Launch job bằng registration ID và request ID; gửi lại cùng request ID không tạo một lần xử lý nghiệp vụ trùng.

**Đạt khi:** job có thể restart và writer xử lý idempotent.

### Bài D — human task với BPM

Mô hình hóa bước nhân viên duyệt bằng user task. UI lấy task list từ engine, claim task, hiển thị form và complete task bằng decision. Có thể dùng Web Flow cho form nhiều bước.

**Đạt khi:** task assignment và process lifecycle nằm trong engine, còn flow chỉ điều khiển UI.

### Bài E — streaming trạng thái

Expose API WebFlux phát trạng thái registration. Chỉ user có quyền đọc registration mới subscribe được. Test client reconnect và stream cancellation.

**Đạt khi:** WebFlux chỉ cung cấp giao tiếp reactive; nguồn trạng thái vẫn là service/process read model có thẩm quyền.

## 18. Checklist lựa chọn kiến trúc

- [ ] Đã xác định đối tượng cần điều khiển: UI flow, HTTP stream, batch job hay business process.
- [ ] Đã xác định vòng đời trạng thái và nơi lưu bền vững.
- [ ] Không nhầm WebFlux với Web Flow.
- [ ] Không nhầm job flow của Spring Batch với browser flow.
- [ ] Có human task, timer, message correlation hoặc SLA thì đã đánh giá BPM engine.
- [ ] FlowScope chỉ giữ dữ liệu tạm theo execution.
- [ ] Business record được lưu trong database nghiệp vụ.
- [ ] Batch metadata/checkpoint được quản lý bởi JobRepository.
- [ ] BPM process instance và task assignment được engine sở hữu.
- [ ] API reactive chỉ được chọn khi có nhu cầu non-blocking/streaming thực tế.
- [ ] Side effect có transaction/idempotency.
- [ ] Có outbox hoặc cơ chế đáng tin cậy khi phát event sau commit.
- [ ] Authorization được kiểm tra ở mọi ranh giới server-side.
- [ ] Có test restart/retry cho từng loại execution.
- [ ] Logging/metrics phân biệt flow, stream, job và process instance.

## 19. Câu hỏi tự kiểm tra

**1. Spring Web Flow giải quyết bài toán gì?** Điều khiển hành trình UI nhiều bước bằng state, event và transition.

**2. WebFlux có phải Web Flow reactive không?** Không. WebFlux là web framework reactive, không cung cấp state machine UI tương đương.

**3. Mono và Flux là gì?** Publisher reactive biểu diễn tối đa một kết quả và chuỗi 0..N kết quả.

**4. Spring Batch dùng Job và Step để làm gì?** Tổ chức workload nền theo lô, hỗ trợ chunk/tasklet, checkpoint, retry và restart.

**5. Job flow của Spring Batch có quản lý browser history không?** Không. Nó điều phối các step trong một batch job.

**6. Khi nào cần BPM/workflow engine?** Khi quy trình kéo dài qua nhiều người/hệ thống, có human task, timer, message, SLA hoặc audit.

**7. Web Flow có thể làm UI cho BPM user task không?** Có thể, nhưng BPM engine vẫn nên sở hữu task state và process lifecycle.

**8. Có nên lưu booking đã xác nhận chỉ trong flowScope không?** Không. Dữ liệu đã commit phải nằm trong database nghiệp vụ.

**9. Có thể dùng WebFlux để launch Spring Batch không?** Có thể expose endpoint reactive gọi job launcher/service, nhưng batch job vẫn do Spring Batch thực thi.

**10. Một hệ thống có thể dùng cả bốn công nghệ không?** Có, nếu mỗi công nghệ có ranh giới và nguồn trạng thái rõ ràng.

## 20. Tài liệu tham khảo

1. [Spring Web Flow Reference Guide 3.0.2](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — flow execution, state, transition, scope và Spring MVC integration.
2. [Spring Framework — Web Reactive](https://docs.spring.io/spring-framework/reference/web/webflux.html) — mô hình reactive web, annotated controllers, functional endpoints và runtime.
3. [Spring Framework — Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — Reactor, Mono/Flux và tích hợp Reactive Streams.
4. [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/) — job, step, chunk processing, JobRepository, restart và retry.
5. [OMG BPMN 2.0](https://www.omg.org/spec/BPMN/2.0/) — ký hiệu và mô hình quy trình nghiệp vụ.
6. [Camunda Documentation](https://docs.camunda.io/) — ví dụ một nền tảng workflow/process orchestration hỗ trợ BPMN.
7. [Flowable Documentation](https://www.flowable.com/open-source/docs/) — ví dụ workflow/BPM engine với process, task và event.

**Điểm cần nhớ:** Web Flow điều khiển hành trình UI; WebFlux điều khiển cách xử lý HTTP reactive; Spring Batch điều khiển job dữ liệu; BPM/workflow engine điều khiển quy trình nghiệp vụ dài hạn. Hãy chọn theo vòng đời và đối tượng được điều khiển, rồi kết nối chúng qua service/API/event. Mỗi loại trạng thái cần một nơi sở hữu rõ ràng để session hết hạn, job restart hoặc process chờ người duyệt không làm mất tính nhất quán nghiệp vụ.
