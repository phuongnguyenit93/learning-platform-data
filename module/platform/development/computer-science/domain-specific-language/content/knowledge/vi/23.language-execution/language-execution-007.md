# Lập lịch

Trong quá trình thực thi ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **lập lịch (scheduling)** là cơ chế quyết định công việc nào được thực hiện, vào thời điểm nào, theo thứ tự nào và sử dụng tài nguyên nào. DSL có thể mô tả workflow, quy trình nghiệp vụ, tác vụ nền, pipeline dữ liệu, chiến lược giao dịch hoặc các quy tắc cần chạy theo thời gian. Runtime cần một scheduler để biến những mô tả đó thành hoạt động có thể điều phối và theo dõi.

Ví dụ, một DSL vận hành đơn hàng có thể khai báo:

~~~text
workflow xu_ly_don_hang {
    step xac_nhan
    step tru_ton_kho after xac_nhan
    step dong_goi after tru_ton_kho
    step giao_hang after dong_goi
}
~~~

Các bước có quan hệ phụ thuộc: trừ tồn kho chỉ được bắt đầu sau khi xác nhận thành công; đóng gói chờ trừ tồn kho; giao hàng chờ đóng gói. Scheduler xác định khi nào mỗi bước đủ điều kiện chạy, đưa bước đó vào hàng đợi, phân phối cho worker và cập nhật trạng thái khi công việc hoàn tất.

Lập lịch cũng có thể dựa trên thời gian hoặc sự kiện:

~~~text
schedule dong_bo_ton_kho {
    every 15 minutes
    run workflow dong_bo_ton_kho
}

schedule gui_bao_cao {
    at 08:00 every weekday in Asia/Ho_Chi_Minh
    run task tao_bao_cao_ngay
}
~~~

Cú pháp trên chỉ minh họa cách một DSL có thể biểu đạt lịch. Ngôn ngữ thực tế cần quy định rõ múi giờ, thời điểm bắt đầu, cách xử lý lần chạy bị lỡ, giới hạn đồng thời, retry và hành vi khi một tác vụ kéo dài sang kỳ tiếp theo.

## 1. Lập lịch trong runtime DSL là gì?

Scheduler là thành phần runtime chịu trách nhiệm chọn và điều phối các đơn vị công việc theo những điều kiện đã khai báo. Đơn vị công việc có thể là task, job, workflow, rule set, pipeline stage hoặc một lời gọi hàm được runtime quản lý.

Lập lịch trả lời bốn câu hỏi cơ bản:

- **Khi nào:** Công việc được kích hoạt theo thời gian, sự kiện, yêu cầu thủ công hay khi dependency hoàn tất?
- **Công việc nào:** Trong số các tác vụ đang chờ, tác vụ nào đủ điều kiện và được chọn trước?
- **Chạy ở đâu:** Worker hoặc tài nguyên nào có khả năng thực hiện công việc?
- **Tiếp theo là gì:** Khi thành công, thất bại, timeout hoặc bị hủy, scheduler cập nhật trạng thái và quyết định công việc kế tiếp.

Scheduler thường không trực tiếp thực hiện nghiệp vụ. Nó quản lý vòng đời và giao việc cho executor hoặc worker. Executor chạy logic do DSL mô tả; scheduler quan sát kết quả rồi tiếp tục điều phối.

### 1.1. Phân biệt schedule, trigger, job và task

Các khái niệm liên quan nhưng có vai trò khác nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| Schedule | Quy tắc xác định thời điểm hoặc điều kiện công việc được kích hoạt |
| Trigger | Sự kiện cụ thể làm công việc trở nên đủ điều kiện chạy |
| Job | Một lần thực hiện có danh tính và trạng thái riêng |
| Task | Đơn vị công việc được thực thi |
| Workflow | Tập task có quan hệ thứ tự, điều kiện hoặc phụ thuộc |
| Scheduler | Thành phần chọn và điều phối công việc |
| Executor | Thành phần thực hiện nội dung công việc |
| Worker | Tiến trình hoặc luồng nhận và chạy job |
| Queue | Nơi giữ công việc đang chờ được phân phối |

Một schedule có thể kích hoạt nhiều job theo thời gian. Mỗi job có thể gồm nhiều task. Một task có thể được thực thi bởi một worker trong executor pool.

### 1.2. Lập lịch không đồng nghĩa với đa luồng

Lập lịch quyết định công việc nào được chọn và khi nào được giao. Đa luồng hoặc concurrency là cách nhiều công việc có thể tiến triển cùng lúc. Scheduler có thể hoạt động trên một luồng nhưng điều phối nhiều worker; ngược lại, chương trình đa luồng không nhất thiết có lịch nghiệp vụ.

### 1.3. Lập lịch không đồng nghĩa với bộ hẹn giờ

Timer phát tín hiệu khi đến thời điểm. Scheduler sử dụng tín hiệu đó cùng dependency, priority, quota, trạng thái và khả năng tài nguyên để quyết định có thực sự chạy công việc hay không. Timer là một nguồn trigger; scheduler là cơ chế điều phối rộng hơn.

## 2. Các mô hình kích hoạt công việc

DSL có thể hỗ trợ nhiều loại trigger. Một schedule có thể dùng một trigger hoặc kết hợp nhiều điều kiện.

### 2.1. Kích hoạt theo thời gian

Time-based scheduling chạy tại một thời điểm hoặc theo chu kỳ:

~~~text
schedule tao_bao_cao {
    at 08:00 every day
    run task tao_bao_cao
}
~~~

Các dạng phổ biến gồm:

- Một lần tại thời điểm xác định.
- Lặp lại sau mỗi khoảng thời gian.
- Theo lịch ngày, tuần, tháng hoặc năm.
- Theo biểu thức lịch như cron.
- Theo thời điểm bắt đầu và kết thúc của một khoảng hiệu lực.

### 2.2. Kích hoạt theo sự kiện

Event-based scheduling chạy khi runtime nhận được sự kiện:

~~~text
schedule xu_ly_don_moi {
    on event DonHangCreated
    run workflow xu_ly_don_hang
}
~~~

Sự kiện có thể đến từ message broker, API, thao tác người dùng, thay đổi dữ liệu hoặc kết quả của task khác. Scheduler cần xác định cách xử lý sự kiện trùng lặp, thứ tự sự kiện và sự kiện đến muộn.

### 2.3. Kích hoạt theo dependency

Một task có thể đủ điều kiện chạy khi các task phụ thuộc hoàn tất:

~~~text
task tao_hoa_don after xac_nhan_thanh_toan
~~~

Scheduler theo dõi trạng thái của các dependency. Task chỉ được đưa vào hàng đợi khi điều kiện phụ thuộc được đáp ứng, ví dụ tất cả task cha thành công hoặc ít nhất một nhánh thỏa điều kiện.

### 2.4. Kích hoạt thủ công

Người dùng hoặc hệ thống bên ngoài có thể yêu cầu chạy một job:

~~~text
command chay_lai_bao_cao {
    invoke task tao_bao_cao
}
~~~

Kích hoạt thủ công thường cần kiểm tra quyền, tham số, giới hạn tần suất và chính sách chạy song song với lịch tự động.

### 2.5. Kích hoạt theo điều kiện

Một schedule có thể kiểm tra điều kiện trước khi tạo job:

~~~text
schedule dong_bo_khi_co_du_lieu {
    every 5 minutes
    when queue.pending_count > 0
    run task dong_bo_du_lieu
}
~~~

Điều kiện nên được đánh giá theo ngữ nghĩa rõ ràng: tại thời điểm trigger, trước khi enqueue hay ngay trước khi worker bắt đầu. Nếu điều kiện thay đổi giữa các bước, kết quả có thể khác nhau.

### 2.6. Kết hợp trigger

Một schedule có thể chạy theo thời gian và sự kiện, nhưng cần quy định cách kết hợp là OR hay AND. Ví dụ “mỗi giờ hoặc khi có sự kiện” khác với “chỉ chạy vào giờ làm việc khi có sự kiện”. Cú pháp DSL phải làm rõ phép kết hợp để tránh kích hoạt ngoài ý muốn.

## 3. Mô hình thời gian và biểu thức lịch

Thời gian là một nguồn phức tạp của lỗi lập lịch. DSL cần xác định đơn vị, múi giờ, lịch, thời điểm tuyệt đối và khoảng thời gian.

### 3.1. Instant và duration

**Instant** biểu diễn một thời điểm trên dòng thời gian; **duration** biểu diễn khoảng thời gian giữa hai thời điểm. Hai khái niệm không thể thay thế nhau.

Ví dụ:

~~~text
start_at = 2026-11-16T08:00:00+07:00
timeout = 30 minutes
~~~

Giá trị đầu là thời điểm có offset; giá trị sau là khoảng thời gian.

### 3.2. Múi giờ

Lịch “08:00 mỗi ngày” cần một múi giờ để xác định instant thực tế. Nếu không khai báo, runtime có thể dùng timezone máy chủ và tạo hành vi khác nhau giữa môi trường phát triển và production.

Nên dùng tên múi giờ có quy tắc lịch sử như IANA Zone ID, ví dụ Asia/Ho_Chi_Minh, thay vì chỉ dùng offset cố định khi lịch cần theo giờ địa phương.

### 3.3. Giờ mùa hè và thời điểm không tồn tại

Ở một số múi giờ, đồng hồ được điều chỉnh theo giờ mùa hè. Khi chuyển giờ, một thời điểm địa phương có thể bị bỏ qua hoặc xuất hiện hai lần. Scheduler cần quy định:

- Với thời điểm không tồn tại, bỏ lần chạy, dịch sang thời điểm hợp lệ tiếp theo hay báo lỗi.
- Với thời điểm xuất hiện hai lần, chạy một lần hay hai lần.
- Khi timezone database được cập nhật, lịch tương lai được tính lại theo quy tắc nào.

Không nên giả định mọi múi giờ đều có ngày dài đúng 24 giờ.

### 3.4. Khoảng thời gian cố định và lịch theo đồng hồ

“Mỗi 24 giờ” có thể có nghĩa chạy sau mỗi 24 giờ kể từ lần trước, trong khi “mỗi ngày lúc 08:00” có nghĩa theo giờ địa phương. Hai lịch có thể lệch nhau khi đổi múi giờ hoặc giờ mùa hè.

~~~text
every 24 hours
~~~

thường biểu diễn chu kỳ duration; còn:

~~~text
at 08:00 every day in Asia/Ho_Chi_Minh
~~~

biểu diễn lịch theo đồng hồ địa phương.

### 3.5. Biểu thức cron

Cron là cách biểu diễn lịch lặp bằng các trường thời gian. Cú pháp cron không hoàn toàn giống nhau giữa các hệ thống: số trường, hỗ trợ giây, ký hiệu ngày trong tuần và cách xử lý ngày cuối tháng có thể khác.

Ví dụ minh họa dạng năm trường:

~~~text
0 8 * * 1-5
~~~

Có thể được hiểu là 08:00 từ thứ Hai đến thứ Sáu trong dialect tương ứng. DSL nên công bố dialect và cung cấp cách xem những thời điểm chạy kế tiếp để người dùng kiểm tra.

### 3.6. Ngày cuối tháng và lịch đặc biệt

Lịch “ngày 31 mỗi tháng” không xác định được trong các tháng ngắn hơn. Runtime cần quy định bỏ tháng đó, chạy vào ngày cuối tháng hay dùng một quy tắc khác. Tương tự, ngày nghỉ, ngày làm việc và lịch tài chính cần calendar được cấu hình rõ.

## 4. Job và vòng đời thực thi

Một schedule tạo ra các lần chạy. Mỗi lần chạy nên có job ID riêng để theo dõi, retry, hủy và truy vết.

### 4.1. Job instance

Job instance chứa thông tin về một lần chạy:

- ID duy nhất.
- Schedule hoặc workflow nguồn.
- Thời điểm trigger dự kiến và thực tế.
- Input parameters hoặc event payload.
- Phiên bản DSL/model được dùng.
- Trạng thái hiện tại.
- Attempt number và lịch sử retry.
- Worker đã nhận job.
- Thời điểm bắt đầu, kết thúc và kết quả.

### 4.2. Các trạng thái thường gặp

Một state machine có thể gồm:

~~~text
SCHEDULED -> QUEUED -> RUNNING -> SUCCEEDED
                            |-> FAILED
                            |-> TIMED_OUT
                            |-> CANCELLED

FAILED -> RETRY_WAIT -> QUEUED
~~~

Đây là mô hình khái niệm. Một hệ thống có thể có thêm trạng thái PAUSED, SKIPPED, BLOCKED, EXPIRED hoặc UNKNOWN.

### 4.3. SCHEDULED và QUEUED

SCHEDULED nghĩa là thời điểm chạy đã được xác định nhưng chưa đến hoặc chưa được kích hoạt. QUEUED nghĩa là job đã đủ điều kiện và đang chờ worker.

### 4.4. RUNNING và terminal states

RUNNING biểu thị worker đã nhận và bắt đầu xử lý. SUCCEEDED, FAILED, TIMED_OUT và CANCELLED thường là trạng thái kết thúc. Một job terminal không nên tự quay lại RUNNING; retry tạo attempt mới hoặc chuyển qua trạng thái chờ retry theo mô hình đã công bố.

### 4.5. Job và attempt

Job biểu diễn yêu cầu nghiệp vụ; attempt biểu diễn một lần thử thực thi. Retry nên giữ job identity để người dùng theo dõi một công việc xuyên suốt, đồng thời có attempt ID riêng để phân biệt log, lỗi và thời gian chạy từng lần.

## 5. Lập lịch workflow theo dependency graph

Workflow thường được biểu diễn thành đồ thị có hướng. Một cạnh A → B có nghĩa B phụ thuộc A.

~~~text
workflow don_hang {
    task xac_nhan
    task kiem_tra_ton_kho
    task tru_ton_kho after kiem_tra_ton_kho
    task tao_hoa_don after xac_nhan, tru_ton_kho
    task giao_hang after tao_hoa_don
}
~~~

### 5.1. DAG

Nếu dependency không có chu trình, đồ thị là Directed Acyclic Graph (DAG). Scheduler có thể chạy các node độc lập song song và chỉ chờ các node có quan hệ phụ thuộc.

~~~mermaid
flowchart TD
    A[Xác nhận] --> D[Tạo hóa đơn]
    B[Kiểm tra tồn kho] --> C[Trừ tồn kho]
    C --> D
    D --> E[Giao hàng]
~~~

### 5.2. Sẵn sàng chạy

Một task được xem là ready khi:

- Tất cả dependency bắt buộc đã hoàn thành theo điều kiện.
- Điều kiện kích hoạt của task đúng.
- Job chưa bị hủy hoặc hết hạn.
- Có quota và tài nguyên phù hợp.

Ready không có nghĩa task sẽ chạy ngay. Nó còn phải chờ scheduler chọn và worker có khả năng nhận.

### 5.3. Topological order

Topological ordering là thứ tự tuyến tính thỏa mọi quan hệ phụ thuộc của DAG. Scheduler có thể dùng thuật toán Kahn hoặc DFS để xác định thứ tự hợp lệ. Nếu graph có chu trình, không tồn tại topological order và workflow cần bị từ chối hoặc xử lý bằng semantics vòng lặp được định nghĩa riêng.

### 5.4. Song song hóa

Hai task không có quan hệ phụ thuộc có thể chạy song song nếu chúng không tranh chấp tài nguyên hoặc trạng thái dùng chung. Tính độc lập về graph chưa đủ để bảo đảm an toàn; cần xem xét side effect và data dependency.

### 5.5. Join và điều kiện hoàn tất

Một task có thể chờ tất cả nhánh cha (all) hoặc chỉ cần một nhánh thành công (any). Với nhánh lỗi, workflow cần quy định tiếp tục, bỏ qua, chạy compensation hay kết thúc thất bại.

~~~text
task gui_thong_bao after all(thanh_toan, cap_nhat_kho)
~~~

### 5.6. Chu trình và vòng lặp

Workflow DAG không cho phép dependency cycle. Nếu miền cần lặp, nên biểu diễn bằng cấu trúc loop, retry hoặc state machine rõ ràng thay vì tạo dependency vòng vô hạn.

## 6. Hàng đợi và phân phối công việc

Queue tách quyết định job đủ điều kiện khỏi việc worker thực sự nhận job.

### 6.1. Ready queue

Khi trigger xảy ra hoặc dependency hoàn tất, job được đưa vào ready queue. Scheduler lấy job từ queue theo chính sách chọn việc.

### 6.2. Queue theo loại công việc

Có thể tách queue theo loại task, tenant, mức ưu tiên hoặc tài nguyên cần thiết. Điều này giúp giới hạn tải và tránh một nhóm công việc chiếm hết worker.

### 6.3. Queue có giới hạn

Nếu queue không giới hạn, một nguồn event nhanh hơn tốc độ xử lý có thể làm bộ nhớ tăng liên tục. Bounded queue cần chính sách khi đầy: backpressure, từ chối, lưu bền vững, gộp sự kiện hoặc bỏ sự kiện theo quy tắc.

### 6.4. Backpressure

Backpressure truyền tín hiệu ngược về producer khi consumer không theo kịp. DSL hoặc runtime có thể giới hạn tốc độ kích hoạt, số job đang chờ hoặc số event được nhận.

### 6.5. Persistent queue

Queue lưu bền vững giữ job qua lần restart của runtime. Nó cần cơ chế ghi nhận trạng thái, lease, retry và khôi phục các job đang chạy dở. Queue trong bộ nhớ đơn giản hơn nhưng có thể mất công việc khi tiến trình dừng.

## 7. Chính sách ưu tiên và chọn công việc

Khi nhiều job cùng sẵn sàng, scheduler cần một chính sách để chọn job kế tiếp.

### 7.1. FIFO

First In, First Out chọn job đến trước. Chính sách dễ hiểu và phù hợp khi các job có mức độ quan trọng tương đương. FIFO không xét deadline hoặc chi phí thực thi.

### 7.2. Priority scheduling

Mỗi job có priority. Scheduler chọn job ưu tiên cao trước:

~~~text
task cap_nhat_so_du {
    priority = 100
}

task tao_bao_cao {
    priority = 20
}
~~~

DSL cần quy định chiều giá trị: số lớn hơn có ưu tiên cao hơn hay ngược lại; giá trị mặc định; phạm vi priority; và cách xử lý job có cùng mức.

### 7.3. Starvation

Nếu job ưu tiên thấp liên tục bị job ưu tiên cao vượt lên, nó có thể không bao giờ được chạy. Đây là starvation. Scheduler có thể dùng aging, tăng priority theo thời gian chờ hoặc dành quota tối thiểu cho mỗi nhóm.

### 7.4. Round robin

Round robin phân phối cơ hội theo vòng giữa các queue hoặc nhóm công việc. Nó hữu ích khi cần công bằng giữa tenant hoặc loại task, nhưng không nhất thiết tối ưu deadline.

### 7.5. Weighted fair scheduling

Weighted fair scheduling phân chia năng lực theo trọng số. Tenant có weight lớn được cấp tỷ lệ worker time cao hơn, nhưng tenant khác vẫn nhận được phần tài nguyên.

### 7.6. Earliest Deadline First

Earliest Deadline First (EDF) ưu tiên job có deadline gần nhất. Nó phù hợp với một số workload có deadline, nhưng cần ước lượng thời gian chạy và chính sách khi không thể đáp ứng tất cả deadline.

### 7.7. Aging và fairness

Aging tăng mức ưu tiên của job theo thời gian chờ để giảm starvation. Fairness cần được đo theo mục tiêu cụ thể: số job, thời gian CPU, thời gian worker hay tài nguyên chuyên biệt.

### 7.8. Tie-breaking

Khi nhiều job có cùng priority hoặc deadline, cần quy tắc phụ ổn định, ví dụ thời điểm enqueue rồi đến job ID. Thứ tự xác định giúp debug và kiểm thử dễ hơn.

## 8. Concurrency và giới hạn chạy đồng thời

Concurrency xác định có bao nhiêu job hoặc task được phép chạy cùng lúc.

### 8.1. Global concurrency limit

Runtime có thể giới hạn tổng số job đang chạy để bảo vệ CPU, bộ nhớ hoặc dịch vụ phụ thuộc.

~~~text
scheduler {
    max_running_jobs = 32
}
~~~

### 8.2. Per-schedule limit

Một schedule có thể giới hạn số lần chạy đồng thời:

~~~text
schedule dong_bo_kho {
    every 5 minutes
    max_concurrent = 1
    run task dong_bo_kho
}
~~~

Nếu lần trước chưa hoàn tất khi trigger mới đến, runtime cần quy định skip, queue, replace hoặc chạy song song.

### 8.3. Per-key concurrency

Có thể cho phép chạy song song giữa các đơn hàng nhưng không chạy đồng thời hai job của cùng một đơn:

~~~text
task cap_nhat_don_hang {
    concurrency_key = don_hang.id
    max_concurrent_per_key = 1
}
~~~

Concurrency key cần được tính ổn định và có phạm vi rõ ràng. Nếu key null hoặc không xác định, runtime cần có chính sách mặc định.

### 8.4. Giới hạn theo tenant

Trong hệ thống nhiều khách hàng, quota theo tenant giúp một tenant có tải lớn không chiếm toàn bộ worker. Quota có thể tính theo số job, CPU time, request rate hoặc resource unit.

### 8.5. Resource semaphore

Một task có thể cần một tài nguyên độc quyền hoặc số lượng giới hạn, ví dụ một kết nối thiết bị hoặc tối đa ba phiên xử lý. Semaphore giúp giới hạn số task đồng thời sử dụng tài nguyên.

### 8.6. Concurrency không bảo đảm thứ tự hoàn tất

Hai task được khởi chạy theo thứ tự A rồi B có thể hoàn tất theo thứ tự B rồi A. Nếu thứ tự hoàn tất ảnh hưởng nghiệp vụ, cần dependency, lock hoặc cơ chế tuần tự hóa thích hợp.

## 9. Tài nguyên và khả năng worker

Scheduler cần biết công việc yêu cầu gì và worker nào có thể đáp ứng.

### 9.1. Resource requirements

Task có thể khai báo tài nguyên:

~~~text
task xu_ly_anh {
    requires cpu = 2
    requires memory = 1 GiB
    requires capability = image-processing
}
~~~

Scheduler chỉ nên giao job cho worker đáp ứng các yêu cầu và quota.

### 9.2. Worker capabilities

Worker có thể đăng ký capability như database, gpu, java-compiler hoặc region-vn. Capability giúp scheduler tránh gửi job đến worker không có thư viện, thiết bị hoặc quyền cần thiết.

### 9.3. Affinity và anti-affinity

Affinity ưu tiên chạy các task liên quan trên cùng worker hoặc cùng vùng dữ liệu để giảm truyền dữ liệu. Anti-affinity yêu cầu các replica chạy tách biệt để giảm rủi ro cùng hỏng.

### 9.4. Resource reservation

Scheduler có thể đặt chỗ tài nguyên trước khi giao job. Reservation cần được giải phóng khi job kết thúc, timeout hoặc bị hủy. Nếu worker chết, lease hoặc timeout giúp thu hồi reservation bị bỏ lại.

### 9.5. Ước lượng và giới hạn

Khai báo tài nguyên là hợp đồng hoặc ước lượng. Runtime cần quyết định điều gì xảy ra khi task dùng vượt mức: throttling, hủy job, tăng giới hạn hoặc ghi nhận violation.

## 10. Deadline, timeout và thời gian chờ

Deadline và timeout đều liên quan thời gian nhưng biểu diễn điều kiện khác nhau.

### 10.1. Deadline

Deadline là thời điểm muộn nhất mà công việc cần hoàn thành:

~~~text
task gui_xac_nhan {
    deadline = triggered_at + 2 minutes
}
~~~

Job có thể bị từ chối nếu không thể bắt đầu kịp hoặc bị đánh dấu trễ nếu hoàn tất sau deadline. Cần quy định scheduler kiểm tra deadline ở thời điểm enqueue, dispatch hay completion.

### 10.2. Execution timeout

Execution timeout giới hạn thời gian task được phép chạy sau khi bắt đầu:

~~~text
task dong_bo {
    timeout = 10 minutes
}
~~~

Khi hết timeout, runtime có thể gửi cancellation signal, ngắt tiến trình hoặc đánh dấu timed out. Không phải tác vụ nào cũng có thể dừng tức thì; cần quy định cách xử lý side effect đang diễn ra.

### 10.3. Queue timeout

Queue timeout giới hạn thời gian job được chờ trước khi worker nhận. Nó khác execution timeout: job có thể chưa bắt đầu nhưng đã quá hạn.

### 10.4. Start deadline và completion deadline

Start deadline yêu cầu job bắt đầu trước một thời điểm; completion deadline yêu cầu hoàn tất trước thời điểm đó. DSL nên dùng tên rõ ràng thay vì một trường deadline mơ hồ nếu cả hai loại đều được hỗ trợ.

### 10.5. Deadline propagation

Workflow có thể truyền deadline còn lại xuống task con. Nếu task cha chỉ còn 20 giây, task con không nên tự nhận timeout 5 phút trừ khi đặc tả cho phép chạy vượt deadline tổng.

## 11. Retry và backoff

Retry là chính sách thử lại công việc sau thất bại tạm thời. Scheduler cần quyết định khi nào tạo attempt mới và cách tránh retry vô hạn.

### 11.1. Retry count

~~~text
task goi_dich_vu {
    retries = 3
}
~~~

Cần làm rõ retries = 3 nghĩa là ba lần thử tổng cộng hay một lần đầu cộng ba lần retry.

### 11.2. Fixed delay

Sau mỗi lần thất bại, chờ một khoảng cố định:

~~~text
retry {
    max_attempts = 4
    delay = 10 seconds
}
~~~

### 11.3. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại, thường theo công thức:

~~~text
delay(n) = min(max_delay, base_delay * 2^(n - 1))
~~~

Có thể thêm jitter ngẫu nhiên để nhiều client không retry cùng lúc sau một sự cố.

### 11.4. Retry theo loại lỗi

Lỗi mạng tạm thời có thể retry; lỗi kiểu dữ liệu hoặc quyền truy cập thường không thể khắc phục bằng cách thử lại ngay. DSL có thể phân loại lỗi retryable và non-retryable hoặc cho phép predicate xác định.

### 11.5. Idempotency

Retry có thể khiến cùng một thao tác được thực hiện nhiều lần. Task có side effect nên hỗ trợ idempotency key, kiểm tra trạng thái trước khi ghi hoặc dùng transaction phù hợp. Không được giả định một lần chạy thất bại nghĩa là không có side effect nào xảy ra.

### 11.6. Retry budget

Retry budget giới hạn tổng số lần thử hoặc tổng thời gian dành cho retry trong một khoảng. Nó ngăn sự cố ở dịch vụ phụ thuộc tạo ra lượng tải lớn hơn khi hệ thống đang suy giảm.

### 11.7. Dead-letter queue

Job vượt quá retry policy có thể được đưa vào dead-letter queue để điều tra hoặc xử lý thủ công. Cần lưu input, lỗi cuối, attempt history và nguồn trigger theo chính sách bảo mật dữ liệu.

## 12. Misfire và các lần chạy bị lỡ

Misfire xảy ra khi một lần chạy theo lịch đã đến hạn nhưng scheduler không thể thực hiện đúng thời điểm, ví dụ runtime dừng, queue đầy hoặc worker không có sẵn.

### 12.1. Các chính sách phổ biến

Khi khởi động lại, scheduler có thể:

- **Skip:** Bỏ qua lần chạy đã lỡ.
- **Fire once now:** Chạy một lần ngay để bù các lần đã lỡ.
- **Catch up all:** Chạy lần lượt tất cả kỳ bị lỡ.
- **Coalesce:** Gộp nhiều lần bị lỡ thành một job.
- **Expire:** Bỏ job nếu đã quá thời hạn cho phép.

### 12.2. Chọn chính sách theo nghiệp vụ

Đồng bộ trạng thái hiện tại có thể chỉ cần chạy một lần sau khi khởi động lại; việc tính lãi theo từng kỳ có thể cần catch up từng kỳ; gửi thông báo định kỳ có thể bỏ qua những lần đã quá hạn. Chính sách không nên dùng chung một cách máy móc.

### 12.3. Catch-up và tải đột biến

Nếu một scheduler dừng nhiều giờ và khi khởi động tạo hàng nghìn job bù, queue có thể bị quá tải. Cần giới hạn catch-up, tốc độ phát job và mức ưu tiên so với công việc mới.

### 12.4. Lưu lần chạy dự kiến cuối cùng

Scheduler bền vững nên lưu trạng thái lịch hoặc cursor thời gian để xác định những lần nào đã được xử lý. Nếu không, restart có thể tạo job trùng hoặc bỏ sót.

## 13. Cancellation, pause và reschedule

Lịch và job có thể được điều khiển sau khi tạo.

### 13.1. Pause schedule

Pause ngăn schedule tạo job mới nhưng không nhất thiết dừng job đang chạy. DSL hoặc API quản trị cần phân biệt pause trigger với cancel active job.

### 13.2. Resume schedule

Khi resume, runtime cần xác định có bù các lần bị lỡ hay áp dụng misfire policy. Hành vi này nên được công bố.

### 13.3. Cancel job

Cancel yêu cầu job dừng. Với task đang chạy, cancellation thường là cooperative: executor nhận tín hiệu và có cơ hội dọn dẹp. Nếu task không hỗ trợ cancellation, runtime cần timeout hoặc cơ chế cô lập tiến trình.

### 13.4. Reschedule

Reschedule thay đổi thời điểm hoặc quy tắc chạy trong tương lai. Cần xác định nó có ảnh hưởng job đã được enqueue hay chỉ các lần trigger sau.

### 13.5. Graceful shutdown

Khi runtime dừng, scheduler có thể ngừng nhận trigger mới, chờ job đang chạy trong một khoảng grace period, lưu trạng thái và đưa job chưa hoàn tất về trạng thái có thể khôi phục.

## 14. Lập lịch phân tán

Trong hệ thống có nhiều runtime instance, nhiều node có thể cùng nhìn thấy một schedule. Nếu không phối hợp, cùng một lần trigger có thể tạo nhiều job trùng lặp.

### 14.1. Single leader

Một node được bầu làm leader để tạo trigger và enqueue job. Các node khác thực thi worker. Cần cơ chế leader election và xử lý khi leader mất kết nối.

### 14.2. Distributed lock

Distributed lock có thể ngăn nhiều node cùng xử lý một schedule tại một thời điểm. Lock cần có lease hoặc expiration để tránh bị giữ mãi khi node chết.

### 14.3. Lease

Lease là quyền sở hữu có thời hạn. Worker nhận job kèm lease; nếu không gia hạn hoặc hoàn tất trước hạn, job có thể được giao lại. Điều này tăng khả năng phục hồi nhưng cũng tạo khả năng một worker cũ vẫn đang chạy sau khi lease hết hạn.

### 14.4. Fencing token

Fencing token là số thế hệ tăng dần gắn với lease. Tài nguyên đích có thể từ chối thao tác từ worker có token cũ, giúp ngăn owner đã mất quyền tiếp tục ghi dữ liệu.

### 14.5. At-least-once và at-most-once

At-least-once delivery có thể giao lại job khi không chắc worker đã hoàn tất; một job có thể được xử lý nhiều lần. At-most-once tránh giao trùng nhưng có thể mất job nếu lỗi xảy ra ở thời điểm không thuận lợi.

Exactly-once execution nói chung khó bảo đảm cho side effect tùy ý. Thực tế thường kết hợp giao at-least-once với idempotency, transaction và deduplication để đạt hiệu ứng nghiệp vụ tương đương một lần.

### 14.6. Clock và thời gian phân tán

Các node có thể lệch đồng hồ. Lịch theo thời gian cần nguồn clock đáng tin cậy, đồng bộ thời gian và quy tắc xử lý timestamp. Không nên dùng thời gian local của mỗi worker làm nguồn duy nhất để xác định thứ tự toàn cục.

### 14.7. Scheduler HA

High availability cần lưu bền vững trạng thái schedule/job, phát hiện node lỗi, khôi phục lease và tránh tạo trigger trùng. Việc chuyển leader phải có quy tắc rõ để không bỏ hoặc nhân đôi lần chạy.

## 15. Đồng thời, thứ tự và tính xác định

Khi nhiều task chạy đồng thời, thứ tự hoàn tất có thể thay đổi giữa các lần thực thi. Điều này ảnh hưởng tính xác định của workflow.

### 15.1. Deterministic scheduling

Scheduler xác định có cùng trạng thái và đầu vào thì chọn cùng công việc tiếp theo theo quy tắc. Determinism hữu ích cho kiểm thử và tái hiện lỗi, nhưng có thể bị phá bởi thời gian thực, event arrival hoặc trạng thái worker.

### 15.2. Deterministic execution

Ngay cả khi thứ tự chọn job ổn định, task vẫn có thể cho kết quả khác do dữ liệu ngoài, randomness, clock hoặc side effect. Lập lịch xác định không tự bảo đảm thực thi xác định.

### 15.3. Ordering guarantee

DSL cần công bố phạm vi bảo đảm thứ tự: theo schedule, theo key, theo workflow, theo tenant hay toàn hệ thống. Không nên để người dùng suy ra thứ tự toàn cục từ thứ tự khai báo nếu scheduler chạy song song.

### 15.4. Serial execution

Nếu các task sửa cùng một trạng thái, có thể yêu cầu chạy tuần tự theo key hoặc trong một critical section. Serial execution giảm race condition nhưng làm giảm throughput.

### 15.5. Event ordering

Event broker có thể bảo đảm thứ tự trong một partition hoặc key nhưng không nhất thiết trên toàn hệ thống. Scheduler cần giữ ordering contract phù hợp với mô hình event của DSL.

### 15.6. Reproducibility

Để tái hiện một lần chạy, cần lưu schedule version, input, event ID, thứ tự task, thời điểm trigger, policy và phiên bản runtime. Log chỉ ghi “job failed” là chưa đủ để tái tạo tình huống.

## 16. Điều kiện, dependency và kết quả thất bại

Một workflow thực tế cần xác định task tiếp theo phụ thuộc kết quả trước đó như thế nào.

### 16.1. Chạy sau thành công

Đây là quan hệ dependency phổ biến nhất. Task con chỉ chạy nếu tất cả task cha thành công.

### 16.2. Chạy sau khi hoàn tất bất kể kết quả

Một task cleanup có thể cần chạy sau khi task cha kết thúc dù thành công hay thất bại:

~~~text
task don_dep after completion(task_xu_ly)
~~~

### 16.3. Nhánh theo kết quả

Workflow có thể chọn nhánh dựa trên outcome:

~~~text
if payment.succeeded:
    run task xuat_kho
else:
    run task huy_don
~~~

### 16.4. Compensation

Nếu một workflow nhiều bước đã tạo side effect rồi thất bại ở bước sau, compensation có thể thực hiện hành động bù như hoàn tiền hoặc trả lại tồn kho. Compensation không phải rollback cơ sở dữ liệu tự động; nó là logic nghiệp vụ được mô tả rõ.

### 16.5. Saga

Saga tổ chức một quy trình phân tán thành nhiều bước có hành động bù tương ứng. Scheduler điều phối bước tiếp theo và compensation khi có lỗi. Mỗi bước cần idempotency và trạng thái bền vững.

### 16.6. Fail-fast và continue-on-error

Một workflow có thể dừng ngay khi task lỗi hoặc tiếp tục các nhánh độc lập. DSL cần quy định rõ phạm vi: một task lỗi có hủy toàn workflow hay chỉ chặn các hậu duệ phụ thuộc vào nó.

## 17. Lập lịch theo sự kiện và event-driven workflow

Event-driven DSL phản ứng với sự kiện thay vì chỉ chạy theo đồng hồ.

### 17.1. Event subscription

Schedule có thể đăng ký nhận một loại event và predicate lọc:

~~~text
schedule don_hang_gia_tri_cao {
    on event DonHangCreated
    where event.total >= 10000000 VND
    run workflow xu_ly_uu_tien
}
~~~

### 17.2. Event time và processing time

Event time là thời điểm sự kiện thực sự xảy ra theo nguồn dữ liệu; processing time là thời điểm runtime nhận và xử lý sự kiện. Event có thể đến muộn hoặc không theo thứ tự, nên DSL cần chọn loại thời gian cho cửa sổ và deadline.

### 17.3. Debounce

Debounce gộp các sự kiện đến gần nhau và chỉ chạy sau khi khoảng yên lặng kết thúc. Nó hữu ích cho tác vụ cập nhật trạng thái sau nhiều thay đổi liên tiếp.

### 17.4. Throttle

Throttle giới hạn số lần kích hoạt trong một khoảng. Ví dụ chỉ cho phép gửi tối đa 10 thông báo mỗi phút.

### 17.5. Coalescing

Coalescing gộp nhiều trigger thành một lần chạy, có thể mang theo danh sách event hoặc trạng thái mới nhất. Cần xác định dữ liệu nào được giữ và có làm mất thông tin sự kiện hay không.

### 17.6. Deduplication

Event ID hoặc idempotency key giúp nhận diện sự kiện đã xử lý. Deduplication cần có thời gian lưu giữ và phạm vi duy nhất rõ ràng.

### 17.7. Windowing

Một số DSL xử lý luồng dữ liệu cần cửa sổ thời gian: tumbling, sliding hoặc session window. Scheduler hoặc stream processor xác định khi nào cửa sổ đóng và khi nào kết quả được phát ra.

## 18. Lập lịch định kỳ và xử lý lần chạy chồng lấn

Lịch định kỳ có thể tạo trigger mới khi lần trước vẫn đang chạy.

### 18.1. Skip

Nếu job trước chưa hoàn tất, bỏ lần trigger mới. Phù hợp khi chỉ cần kết quả gần nhất và không cần chạy bù từng kỳ.

### 18.2. Queue

Giữ lần trigger mới trong queue để chạy sau. Cần giới hạn backlog và quy tắc giữ thứ tự.

### 18.3. Replace hoặc coalesce

Hủy hoặc thay thế job cũ bằng job mới, hoặc gộp nhiều lần trigger thành một job. Cách này phù hợp với tác vụ tính lại snapshot nhưng có thể không phù hợp với xử lý giao dịch từng sự kiện.

### 18.4. Allow overlap

Cho phép nhiều lần chạy cùng schedule đồng thời. Cần bảo đảm task an toàn với dữ liệu dùng chung hoặc có partition key.

### 18.5. Policy minh họa

~~~text
schedule tao_snapshot {
    every 10 minutes
    overlap = coalesce
    max_concurrent = 1
    run task tao_snapshot
}
~~~

Tên policy và cú pháp là minh họa; semantics phải được đặc tả chính xác, nhất là việc job đang chạy có bị hủy hay chỉ gộp trigger chờ.

## 19. Tạm dừng, lịch làm việc và calendar

Một số công việc chỉ được chạy trong khung giờ hoặc ngày làm việc.

### 19.1. Working calendar

DSL có thể tham chiếu calendar chứa ngày làm việc, ngày nghỉ và giờ hoạt động:

~~~text
schedule xu_ly_yeu_cau {
    every 5 minutes
    only during calendar gio_lam_viec
    run task xu_ly_yeu_cau
}
~~~

### 19.2. Holiday calendar

Lịch nghỉ có thể khác nhau theo quốc gia, vùng hoặc tổ chức. Calendar cần được version hóa để lịch sử và lần chạy tương lai có thể được giải thích.

### 19.3. Blackout window

Blackout window là khoảng thời gian không được chạy một số tác vụ, ví dụ khi bảo trì hệ thống hoặc đóng sổ kế toán.

### 19.4. Calendar update

Khi calendar thay đổi, scheduler cần quyết định có tính lại các trigger đã tạo hay chỉ áp dụng cho lịch tương lai. Thay đổi lịch có thể làm dịch chuyển deadline hoặc lần chạy đã được enqueue.

## 20. Tính bền vững và khôi phục trạng thái scheduler

Scheduler production thường cần giữ trạng thái qua restart hoặc lỗi node.

### 20.1. Lưu schedule definition

Lưu biểu thức lịch, timezone, tham số, version DSL và trạng thái pause/active. Nên giữ bản definition đã được validate để tránh đọc một cấu hình dở dang.

### 20.2. Lưu next fire time

Scheduler có thể lưu lần trigger kế tiếp. Khi khởi động, nó so sánh thời gian hiện tại với next fire time và áp dụng misfire policy.

### 20.3. Lưu job state

Job state cần được cập nhật bền vững tại các chuyển trạng thái quan trọng. Cần tránh trạng thái queue nói job đang chờ trong khi worker đã chạy hoặc ngược lại.

### 20.4. Worker crash

Nếu worker chết giữa lúc chạy, job có thể ở RUNNING mãi. Lease timeout hoặc heartbeat cho phép scheduler nhận diện worker không còn hoạt động và quyết định retry hoặc đưa job vào trạng thái cần kiểm tra.

### 20.5. Recovery sau restart

Khi runtime khởi động lại, scheduler đọc schedule và job state, khôi phục queue, kiểm tra lease hết hạn, xử lý misfire và tiếp tục dispatch. Các bước cần có thứ tự để tránh tạo job trùng.

### 20.6. State transition nguyên tử

Việc claim job và chuyển QUEUED sang RUNNING cần được thực hiện nguyên tử hoặc có cơ chế compare-and-set. Nếu hai worker cùng claim một job, side effect có thể bị thực hiện hai lần.

## 21. Kiến trúc scheduler và executor

Một kiến trúc thường tách parser/validator, schedule registry, trigger engine, queue, dispatcher và worker pool.

~~~mermaid
flowchart TD
    A[DSL definitions] --> B[Parser and Validator]
    B --> C[Schedule Registry]
    C --> D[Trigger Engine]
    D --> E[Ready Queue]
    E --> F[Dispatcher]
    F --> G[Worker Pool]
    G --> H[Task Executor]
    H --> I[Result and Events]
    I --> J[Job State Store]
    J --> D
~~~

### 21.1. Schedule registry

Registry giữ các schedule đã đăng ký, phiên bản, trạng thái và metadata. Nó có thể hỗ trợ activate, pause, update hoặc remove schedule.

### 21.2. Trigger engine

Trigger engine tính thời điểm kế tiếp, nhận event và kiểm tra điều kiện kích hoạt. Nó tạo job khi trigger hợp lệ.

### 21.3. Queue và dispatcher

Queue giữ job ready. Dispatcher áp dụng priority, fairness, quota và khả năng worker để chọn job giao đi.

### 21.4. Worker pool

Worker pool quản lý số worker, capability, heartbeat và trạng thái tải. Có thể dùng thread pool trong một tiến trình hoặc worker phân tán qua message broker.

### 21.5. Task executor

Executor gọi logic thực thi DSL, cung cấp context, cancellation token, deadline và transaction scope nếu cần.

### 21.6. State store

State store lưu job, attempt, lease, next fire time và execution result. Với hệ thống cần khôi phục, dữ liệu này phải bền vững và có quy tắc nhất quán.

### 21.7. Control plane và data plane

Control plane quản lý định nghĩa schedule, cấu hình và chính sách. Data plane nhận trigger, dispatch và thực thi job. Tách hai mặt phẳng giúp cập nhật cấu hình mà không làm gián đoạn toàn bộ worker.

## 22. API và mô hình cấu hình cho DSL

DSL cần cung cấp cú pháp dễ đọc nhưng vẫn biểu đạt đủ semantics để runtime không phải đoán.

### 22.1. Schedule declaration

Một khai báo có thể gồm:

~~~text
schedule dong_bo_hang_ngay {
    at 02:00 every day in Asia/Ho_Chi_Minh
    run workflow dong_bo_du_lieu
    max_concurrent = 1
    misfire = coalesce
}
~~~

### 22.2. Task declaration

Task có thể khai báo priority, resource, timeout và retry:

~~~text
task tinh_tong_ket {
    priority = high
    timeout = 5 minutes
    retries = 2
    requires capability = finance
}
~~~

### 22.3. Dependency declaration

Dependency nên phân biệt điều kiện thành công, hoàn tất và kết quả cụ thể:

~~~text
task gui_bien_nhan after success(tao_hoa_don)
task don_dep after completion(xu_ly_don)
~~~

### 22.4. Defaults và inheritance

Một schedule có thể kế thừa policy từ nhóm hoặc project. Cần quy định giá trị cục bộ có override giá trị cha không, danh sách có merge không và xung đột được xử lý thế nào.

### 22.5. Validation trước khi đăng ký

Runtime nên kiểm tra biểu thức lịch, timezone, dependency, priority range, resource request và quyền trước khi activate schedule. Schedule sai cấu hình không nên âm thầm được đăng ký với một hành vi mặc định không rõ.

## 23. Quan sát và vận hành scheduler

Scheduler cần cung cấp thông tin đủ để người vận hành biết job đang ở đâu, vì sao chưa chạy và tài nguyên có đang quá tải không.

### 23.1. Metrics

Các metric hữu ích gồm:

- Số job theo trạng thái.
- Độ dài ready queue.
- Thời gian chờ trung bình và percentile.
- Thời gian thực thi theo task.
- Số retry và tỷ lệ thất bại.
- Số lần misfire hoặc schedule trễ.
- Worker utilization và số worker khả dụng.
- Số job bị từ chối do quota hoặc thiếu capability.

### 23.2. Logs

Log nên có job ID, attempt ID, schedule ID, workflow ID, task name, worker ID và correlation ID. Không nên ghi dữ liệu nhạy cảm trong payload hoặc thông báo lỗi.

### 23.3. Distributed tracing

Trace có thể liên kết trigger, enqueue, dispatch, task execution và các lời gọi dịch vụ bên ngoài. Nó giúp phân biệt thời gian chờ queue với thời gian thực thi.

### 23.4. Audit

Thay đổi schedule, pause/resume, cancel, retry thủ công và chỉnh policy nên được audit nếu có ảnh hưởng nghiệp vụ hoặc vận hành.

### 23.5. Giải thích vì sao job chưa chạy

Một hệ thống dễ vận hành nên có khả năng giải thích job đang BLOCKED do dependency, chờ tài nguyên, bị pause, ngoài working calendar, hết quota hay đang chờ priority. Trạng thái tổng quát PENDING thường không đủ để điều tra.

### 23.6. Lịch sử lần chạy

Người dùng cần xem lần trigger dự kiến, thời gian thực tế, độ trễ, attempt, worker, kết quả và lỗi. Lịch sử giúp đánh giá schedule có đáp ứng SLA hay không.

## 24. Bảo mật và kiểm soát quyền

Lập lịch có thể tạo công việc tự động và lặp lại, vì vậy một khai báo sai hoặc độc hại có thể gây tải lớn hoặc thực hiện hành động ngoài dự kiến.

### 24.1. Authorization

Chỉ chủ thể được phép mới có thể tạo, sửa, pause, resume hoặc cancel schedule. Quyền thực thi task cũng cần được kiểm tra ở runtime, không chỉ khi đăng ký.

### 24.2. Resource quota

Giới hạn số schedule, trigger rate, job concurrency, thời gian chạy và tài nguyên giúp ngăn một project chiếm toàn bộ hệ thống.

### 24.3. Giới hạn biểu thức lịch

Một biểu thức cron có thể kích hoạt quá thường xuyên. Validator có thể từ chối tần suất vượt giới hạn hoặc yêu cầu quyền cao hơn.

### 24.4. Tenant isolation

Queue, state và quota của các tenant cần được phân tách phù hợp. Không nên để một tenant đọc payload hoặc hủy job của tenant khác.

### 24.5. Secret và payload

Job parameters có thể chứa token hoặc dữ liệu cá nhân. Cần giới hạn quyền đọc, mã hóa khi lưu và tránh ghi toàn bộ payload vào log.

### 24.6. Giới hạn retry

Retry vô hạn có thể gây denial of service cho dịch vụ phụ thuộc. Cần max attempts, backoff, retry budget và cơ chế dead-letter.

## 25. Kiểm thử lập lịch

Kiểm thử scheduler cần bao gồm cả quy tắc thời gian, trạng thái, concurrency và lỗi phân tán.

### 25.1. Dùng clock giả lập

Không nên phụ thuộc vào thời gian thực trong unit test. Inject clock hoặc virtual time để tiến nhanh đến thời điểm trigger, kiểm tra deadline và misfire một cách xác định.

### 25.2. Kiểm thử biểu thức lịch

Kiểm tra thời điểm kế tiếp, ngày cuối tháng, năm nhuận, timezone, daylight saving và khoảng thời gian không hợp lệ. Với cron, test theo dialect cụ thể.

### 25.3. Kiểm thử dependency graph

Kiểm tra DAG hợp lệ, chu trình, task ready, join all/any, nhánh thất bại và task cleanup.

### 25.4. Kiểm thử priority và fairness

Tạo nhiều queue có priority và weight khác nhau. Xác minh job ưu tiên cao được chọn đúng nhưng job ưu tiên thấp không bị starvation ngoài chính sách.

### 25.5. Kiểm thử concurrency

Xác minh global limit, per-schedule limit, per-key lock và resource semaphore. Dùng barrier hoặc fake worker để tái hiện race condition.

### 25.6. Kiểm thử retry và idempotency

Giả lập lỗi tạm thời, lỗi vĩnh viễn, worker crash và kết quả không rõ sau side effect. Xác minh attempt count, backoff, deduplication và trạng thái cuối.

### 25.7. Kiểm thử misfire

Tiến clock qua nhiều kỳ trong lúc scheduler tạm dừng rồi khởi động lại. Kiểm tra skip, catch-up, coalesce hoặc expire theo policy.

### 25.8. Kiểm thử phân tán

Mô phỏng hai scheduler cùng claim schedule, lease hết hạn, leader thay đổi và node mất kết nối. Xác minh không có chuyển trạng thái trái phép và side effect được bảo vệ bằng idempotency/fencing khi cần.

### 25.9. Kiểm thử phục hồi

Khởi động lại runtime ở các thời điểm khác nhau: sau enqueue, sau claim, trong lúc task chạy và sau side effect nhưng trước khi ghi success. Kiểm tra job được khôi phục theo semantics đã công bố.

### 25.10. Kiểm thử tải

Tạo burst trigger và queue backlog để đo throughput, queue latency, fairness, bộ nhớ và khả năng backpressure.

## 26. Ví dụ tổng hợp: lập lịch workflow xử lý đơn hàng

Giả sử DSL mô tả quy trình:

~~~text
workflow xu_ly_don_hang {
    task xac_nhan {
        timeout = 30 seconds
        retries = 2
    }

    task kiem_tra_ton_kho after success(xac_nhan) {
        requires capability = inventory
        timeout = 1 minute
    }

    task tru_ton_kho after success(kiem_tra_ton_kho) {
        concurrency_key = don_hang.id
        max_concurrent_per_key = 1
    }

    task tao_hoa_don after success(tru_ton_kho)

    task gui_thong_bao after completion(tao_hoa_don)
}

schedule xu_ly_don_moi {
    on event DonHangCreated
    max_concurrent = 20
    misfire = skip
    run workflow xu_ly_don_hang
}
~~~

### 26.1. Khi event đến

Trigger engine nhận DonHangCreated, kiểm tra schema payload và tạo job. Job được ghi nhận với event ID, schedule ID và input parameters.

### 26.2. Task đầu tiên

Task xac_nhan đủ điều kiện vì không có dependency. Scheduler đưa nó vào ready queue và dispatcher chọn worker phù hợp.

### 26.3. Dependency được mở khóa

Khi xac_nhan thành công, kiem_tra_ton_kho trở thành ready. Nếu worker inventory không khả dụng, task vẫn chờ và trạng thái giải thích cần thể hiện thiếu capability.

### 26.4. Giới hạn theo đơn hàng

tru_ton_kho dùng concurrency key là ID đơn hàng. Hai job của cùng đơn không được trừ tồn kho đồng thời, trong khi các đơn khác vẫn có thể xử lý song song.

### 26.5. Tạo hóa đơn và thông báo

Hóa đơn chỉ được tạo sau khi trừ tồn kho thành công. Thông báo được chạy sau khi bước tạo hóa đơn hoàn tất theo semantics completion; nếu cần chỉ gửi khi hóa đơn thành công, dependency phải dùng success.

### 26.6. Lỗi và retry

Nếu xác nhận thất bại do lỗi mạng tạm thời, scheduler chờ theo retry policy. Nếu kiểm tra tồn kho báo hết hàng, đây có thể là kết quả nghiệp vụ chứ không phải lỗi retryable; workflow chuyển sang nhánh xử lý phù hợp.

### 26.7. Quan sát

Mỗi bước có job/attempt ID, thời gian chờ, worker và kết quả. Người vận hành có thể biết đơn hàng đang chờ inventory, đang retry hay đã hoàn tất.

## 27. Những sai lầm thường gặp

### 27.1. Nhầm trigger với thực thi

Đến thời điểm trigger không có nghĩa task chắc chắn bắt đầu ngay. Job còn có thể chờ queue, quota, dependency hoặc worker.

### 27.2. Không xác định timezone

Lịch theo giờ địa phương nhưng dùng timezone máy chủ có thể chạy sai thời điểm khi triển khai ở vùng khác. Hãy khai báo timezone hoặc quy định mặc định rõ ràng.

### 27.3. Không định nghĩa misfire

Sau khi runtime dừng, scheduler có thể bỏ sót hoặc tạo hàng loạt lần chạy bù. Mỗi loại schedule cần policy phù hợp.

### 27.4. Retry mọi lỗi

Retry lỗi dữ liệu hoặc quyền không giúp khắc phục nguyên nhân và có thể tăng tải. Cần phân loại retryable và non-retryable.

### 27.5. Giả định task chỉ chạy một lần

Trong hệ thống phân tán, job có thể được giao lại sau timeout hoặc worker crash. Task có side effect cần idempotency hoặc cơ chế deduplication.

### 27.6. Không giới hạn concurrency

Trigger dồn dập có thể tạo quá nhiều job chạy cùng lúc, làm cạn connection pool hoặc gây quá tải dịch vụ phụ thuộc.

### 27.7. Không kiểm tra dependency cycle

Workflow có chu trình có thể không bao giờ có task ready. Validator nên phát hiện cycle trước khi activate.

### 27.8. Không chống starvation

Priority cao liên tục có thể chặn job thấp. Cần aging, fairness hoặc quota theo nhóm nếu nghiệp vụ yêu cầu.

### 27.9. Cho rằng thứ tự khai báo là thứ tự hoàn tất

Khai báo task theo thứ tự không tự tạo bảo đảm hoàn tất tuần tự. Cần dependency hoặc serial policy rõ ràng.

### 27.10. Không lưu trạng thái bền vững

Scheduler chỉ giữ trạng thái trong bộ nhớ có thể mất job khi restart. Hệ thống cần đảm bảo phục hồi phải lưu schedule, job và attempt state.

### 27.11. Không giải thích job bị chặn

Một job ở trạng thái pending quá lâu cần có lý do cụ thể như dependency, quota, calendar, pause hoặc thiếu worker capability.

### 27.12. Coi exactly-once là bảo đảm mặc định

Giao job một lần không đồng nghĩa side effect chỉ xảy ra một lần. Cần thiết kế transaction, idempotency, deduplication và fencing theo hệ thống đích.

## 28. Nguyên tắc thiết kế lập lịch cho DSL

Một DSL có scheduler dễ hiểu cần công khai semantics và cho phép người dùng quan sát trạng thái.

### 28.1. Cú pháp lịch phải không mơ hồ

Phân biệt instant với duration, lịch theo đồng hồ với chu kỳ cố định, timezone, ngày nghỉ và cron dialect.

### 28.2. Tách trigger khỏi dispatch

Trigger xác định công việc đủ điều kiện; dispatcher chọn worker dựa trên priority, quota, capability và resource.

### 28.3. Định nghĩa state machine

Mọi chuyển trạng thái cần có điều kiện, tác nhân và quy tắc lưu bền vững. Tránh các trạng thái pending chung chung không giải thích được.

### 28.4. Dependency phải được kiểm tra

Validate cycle, điều kiện join, nhánh lỗi và task cleanup trước khi workflow được kích hoạt.

### 28.5. Giới hạn concurrency và tài nguyên

Hỗ trợ giới hạn toàn cục, theo schedule, tenant, key và loại resource. Mặc định cần an toàn và được tài liệu hóa.

### 28.6. Retry phải có giới hạn

Định nghĩa attempt count, backoff, jitter, retryable errors, budget và dead-letter behavior.

### 28.7. Có chính sách misfire

Mỗi schedule cần quy tắc khi runtime dừng hoặc quá tải: skip, catch-up, coalesce hay expire.

### 28.8. Thiết kế cho phân tán

Nếu chạy nhiều node, cần lease, state store, claim nguyên tử, deduplication và idempotency. Không dựa vào một timer trong bộ nhớ để bảo đảm lịch toàn hệ thống.

### 28.9. Quan sát được

Hiển thị next fire time, job state, queue delay, attempt, worker, dependency block và lý do không dispatch.

### 28.10. Có thể kiểm thử xác định

Cho phép inject clock, fake worker và scheduler simulator để kiểm thử mà không chờ thời gian thực.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Scheduling | Quyết định thời điểm, thứ tự và cách phân phối công việc |
| Scheduler | Thành phần điều phối trigger, queue và worker |
| Trigger | Điều kiện hoặc sự kiện làm job đủ điều kiện được tạo |
| Schedule | Quy tắc kích hoạt job theo thời gian hoặc sự kiện |
| Job | Một lần chạy có danh tính và trạng thái |
| Task | Đơn vị công việc được thực thi |
| Workflow | Tập task có dependency hoặc điều kiện |
| Ready Queue | Hàng đợi chứa job đủ điều kiện dispatch |
| Priority Scheduling | Chọn job dựa trên mức ưu tiên |
| Starvation | Công việc bị trì hoãn vô hạn do luôn bị việc khác vượt lên |
| Aging | Tăng ưu tiên theo thời gian chờ để giảm starvation |
| Round Robin | Phân phối cơ hội theo vòng giữa các nhóm |
| Earliest Deadline First | Ưu tiên job có deadline gần nhất |
| Concurrency Limit | Giới hạn số công việc chạy đồng thời |
| Resource Semaphore | Cơ chế giới hạn số task cùng sử dụng tài nguyên |
| Deadline | Thời điểm muộn nhất cần đạt một điều kiện hoàn thành |
| Timeout | Khoảng thời gian tối đa cho một giai đoạn hoặc lần chạy |
| Retry | Thử lại công việc sau thất bại |
| Backoff | Khoảng chờ tăng dần giữa các lần retry |
| Misfire | Lần chạy theo lịch bị lỡ thời điểm dự kiến |
| Coalescing | Gộp nhiều trigger hoặc lần chạy bị lỡ thành một |
| Idempotency | Chạy lặp không tạo thêm tác động ngoài kết quả đã ổn định |
| Lease | Quyền sở hữu có thời hạn đối với job hoặc tài nguyên |
| Fencing Token | Số thế hệ giúp từ chối thao tác từ owner cũ |
| At-least-once | Giao ít nhất một lần, có thể giao trùng |
| At-most-once | Giao tối đa một lần, có thể mất job |
| DAG | Đồ thị có hướng không chu trình biểu diễn dependency |
| Backpressure | Cơ chế giảm tốc producer khi consumer quá tải |
| Dead-letter Queue | Nơi giữ job không thể xử lý sau chính sách retry |
| Saga | Quy trình phân tán gồm các bước và hành động bù |

Lập lịch là phần điều phối thời gian và tài nguyên của runtime DSL. Một scheduler cần kết hợp trigger, dependency, queue, priority, worker capability, concurrency, deadline và trạng thái job để quyết định công việc nào được chạy tiếp theo. Với lịch định kỳ, hệ thống còn phải xử lý timezone, misfire và các lần chạy chồng lấn; với môi trường phân tán, cần lease, lưu trạng thái bền vững, deduplication và idempotency. Khi các quy tắc này được biểu đạt rõ trong DSL và có thể quan sát, kiểm thử, người dùng có thể dự đoán cách workflow vận hành và người phát triển runtime có cơ sở để thực thi chúng nhất quán.
