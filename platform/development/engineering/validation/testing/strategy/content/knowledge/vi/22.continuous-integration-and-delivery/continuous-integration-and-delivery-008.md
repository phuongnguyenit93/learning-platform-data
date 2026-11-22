# Thiết kế cách xử lý timeout, hủy và dọn tài nguyên

Một pipeline CI/CD có thể khởi chạy nhiều công việc: build, kiểm thử, đóng gói, triển khai, migration, tạo môi trường tạm và gửi yêu cầu đến dịch vụ bên ngoài. Một bước có thể bị treo, chạy lâu hơn dự kiến hoặc không còn cần thiết sau khi một bước khác thất bại. Nếu không có chính sách timeout và hủy rõ ràng, runner có thể bị chiếm dụng, tiến trình con tiếp tục chạy, môi trường tạm bị bỏ lại và các lần chạy sau bị ảnh hưởng bởi tài nguyên cũ. Ngược lại, hủy quá sớm hoặc dọn tài nguyên khi công việc vẫn đang sử dụng chúng có thể làm mất dữ liệu, để lại trạng thái triển khai không nhất quán hoặc che giấu nguyên nhân thất bại.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, thiết kế cách xử lý timeout, hủy và dọn tài nguyên là một phần của chiến lược xác thực và vận hành pipeline. Mục tiêu là giới hạn thời gian chờ, truyền tín hiệu hủy đúng cách, bảo đảm các bước dừng an toàn và thu hồi tài nguyên trong phạm vi được phép. Chính sách cần áp dụng từ một lệnh test đơn lẻ đến toàn bộ workflow, bao gồm runner, tiến trình con, container, môi trường tạm, dữ liệu, queue và dịch vụ ngoài.

## 1. Phân biệt timeout, hủy và cleanup

### Timeout là giới hạn thời gian

Timeout xác định khoảng thời gian tối đa mà một thao tác, bước hoặc workflow được phép chờ hay thực thi trước khi hệ thống áp dụng hành động đã định. Timeout có thể được đặt cho:

- Kết nối đến dịch vụ.
- Thời gian chờ phản hồi.
- Một lệnh hoặc test case.
- Một job hoặc stage trong pipeline.
- Toàn bộ workflow.
- Một thao tác triển khai hoặc migration.
- Thời gian chờ một tác vụ bất đồng bộ đạt trạng thái cuối.

Timeout là cơ chế giới hạn, không tự giải quyết mọi trạng thái dở dang. Khi hết thời gian, hệ thống cần xác định có gửi tín hiệu hủy, chờ tác vụ dừng, kết thúc cưỡng bức hay chuyển sang xử lý phục hồi.

### Hủy là yêu cầu dừng công việc

Hủy (cancellation) là việc yêu cầu một tác vụ không tiếp tục thực hiện công việc. Tín hiệu hủy có thể xuất phát từ:

- Người dùng hoặc người vận hành nhấn Cancel.
- Một bước phụ thuộc thất bại.
- Workflow bị thay thế bởi lần chạy mới.
- Điều kiện chất lượng không đạt.
- Hết timeout.
- Một chính sách tài nguyên hoặc an toàn được kích hoạt.

Hủy thường cần được truyền từ workflow đến job, process, thread, container và các tác vụ con. Một tín hiệu hủy không bảo đảm mọi thành phần dừng ngay lập tức. Thành phần cần có điểm kiểm tra hủy và hành vi kết thúc phù hợp.

### Cleanup là thu hồi tài nguyên

Cleanup là hoạt động giải phóng hoặc đưa tài nguyên về trạng thái được quản lý sau khi công việc kết thúc, thất bại hoặc bị hủy. Tài nguyên có thể gồm:

- Runner, process và container.
- Workspace, file tạm và artifact chưa cần giữ.
- Database, schema, tenant hoặc namespace tạm.
- Queue, message, worker và subscription.
- Cloud resource, máy ảo hoặc môi trường preview.
- Lock, lease, port và credential tạm.
- Giao dịch sandbox, webhook và dữ liệu ở nhà cung cấp ngoài.

Cleanup có thể chạy sau thành công, thất bại, timeout hoặc hủy. Một số tài nguyên cần giữ để điều tra; vì vậy cleanup phải phân biệt tài nguyên tạm với bằng chứng cần lưu theo retention.

### Ba hoạt động có quan hệ nhưng không thay thế nhau

| Hoạt động | Câu hỏi chính | Kết quả cần đạt |
|---|---|---|
| Timeout | Công việc được phép chạy hoặc chờ bao lâu? | Không chờ vô hạn; có hành động khi quá hạn |
| Hủy | Làm thế nào yêu cầu công việc dừng? | Công việc ngừng an toàn hoặc được ghi nhận không thể dừng |
| Cleanup | Làm thế nào thu hồi tài nguyên sau đó? | Không còn tài nguyên tạm ngoài chính sách giữ lại |

Đặt timeout mà không xử lý hủy có thể để lại tiến trình chạy nền. Hủy mà không cleanup có thể để lại database hoặc container. Cleanup khi chưa xác minh tác vụ đã dừng có thể xóa tài nguyên mà tác vụ vẫn đang sử dụng.

## 2. Xác định phạm vi và mục tiêu timeout

### Phân cấp timeout

Không nên chỉ có một timeout duy nhất cho cả pipeline. Hãy phân cấp theo ranh giới công việc:

| Cấp | Ví dụ | Mục tiêu |
|---|---|---|
| Kết nối | Kết nối database, registry hoặc API | Tránh chờ kết nối vô hạn |
| Request | Gọi API hoặc nhà cung cấp | Giới hạn thời gian chờ phản hồi |
| Hoạt động | Build, test, migration hoặc upload | Giới hạn một thao tác cụ thể |
| Job | Một job trên runner | Thu hồi runner bị treo |
| Stage | Một nhóm job có quan hệ | Ngăn một giai đoạn chặn toàn workflow |
| Workflow | Toàn bộ pipeline | Bảo đảm thời gian kết thúc tổng thể |
| Cleanup | Thu hồi container, schema hoặc môi trường | Giới hạn thời gian dọn nhưng vẫn ghi nhận phần còn sót |

Timeout ở cấp thấp nên ngắn hơn hoặc được tính trong ngân sách của cấp cao hơn. Nếu request có timeout 10 phút nhưng job chỉ còn 2 phút, cần có quy tắc rõ để request không bị cắt đột ngột mà không lưu kết quả.

### Chọn timeout theo mục tiêu và dữ liệu lịch sử

Timeout nên dựa trên:

- Thời gian chạy bình thường và phân vị p95/p99.
- Mức biến động giữa các runner và môi trường.
- Thời gian khởi tạo, tải dependency và setup.
- Kích thước dataset và số lượng test.
- Độ trễ của dịch vụ phụ thuộc.
- Thời gian cần để hoàn thành thao tác an toàn.
- Ngân sách thời gian của stage và workflow.
- Hậu quả nếu thao tác bị ngắt ở từng thời điểm.

Không đặt timeout quá sát p50 vì một biến động nhỏ có thể gây hủy giả. Cũng không đặt quá dài chỉ để che giấu tác vụ treo. Theo dõi timeout rate và thời gian thực tế để điều chỉnh.

### Phân biệt thời gian thực thi với thời gian chờ

Một bước có thể tiêu tốn thời gian ở nhiều giai đoạn:

- Chờ runner.
- Provision môi trường.
- Tải image hoặc dependency.
- Chạy lệnh.
- Chờ job bất đồng bộ.
- Thu thập artifact.
- Cleanup.

Nếu chỉ đo thời gian lệnh, nhóm có thể bỏ qua thời gian chờ runner hoặc provisioning. Mỗi ranh giới cần timestamp để xác định nơi ngân sách bị tiêu thụ.

### Định nghĩa hành vi khi quá hạn

Với mỗi timeout, xác định:

1. Tín hiệu hoặc bộ đếm nào xác định quá hạn?
2. Tác vụ đang ở trạng thái nào?
3. Có thể dừng mềm hay phải dừng cưỡng bức?
4. Có cần hoàn tất transaction, rollback hoặc lưu checkpoint không?
5. Cần giữ lại bằng chứng nào?
6. Cleanup nào được phép chạy?
7. Nếu cleanup cũng timeout, ai hoặc tiến trình nào xử lý phần còn lại?
8. Pipeline kết thúc với trạng thái nào?

Không để mỗi script tự xử lý timeout theo cách riêng mà không có quy ước chung.

## 3. Thiết kế timeout theo loại công việc

### Timeout cho kết nối và request

Đối với kết nối mạng, nên phân biệt:

- **Connect timeout:** thời gian tối đa để thiết lập kết nối.
- **Read timeout:** thời gian tối đa chờ dữ liệu phản hồi.
- **Write timeout:** thời gian tối đa gửi dữ liệu.
- **Overall deadline:** giới hạn tổng thời gian của cả thao tác, bao gồm retry và các lần gọi phụ.

Một request có thể có read timeout ngắn nhưng nhiều lần retry khiến tổng thời gian vượt ngân sách. Vì vậy, cần có deadline tổng và truyền deadline hoặc thời gian còn lại đến các dịch vụ con khi có thể.

### Timeout cho test và test suite

Timeout của test cần phản ánh mục tiêu kiểm tra. Một unit test thường có giới hạn ngắn; một E2E đi qua nhiều dịch vụ cần thời gian lớn hơn nhưng phải có giới hạn.

Nên quy định:

- Timeout mặc định theo cấp test.
- Timeout riêng cho test có lý do.
- Timeout cho từng bước bất đồng bộ.
- Timeout tổng cho suite.
- Thông tin trạng thái cuối khi hết hạn.
- Quy tắc retry và cách lưu kết quả lần đầu.

Không tăng timeout của toàn suite để xử lý một test chậm. Tìm nguyên nhân ở test hoặc phụ thuộc cụ thể trước.

### Timeout cho migration và triển khai

Migration hoặc deploy có thể thay đổi trạng thái lâu dài. Khi đặt timeout, cần tính đến:

- Thời gian khóa hoặc chờ lock.
- Kích thước dữ liệu và thời gian backfill.
- Tính tương thích giữa phiên bản cũ và mới.
- Khả năng tiếp tục từ checkpoint.
- Khả năng rollback hoặc chạy bước bù.
- Trạng thái khi tiến trình bị dừng giữa chừng.

Không giả định rằng timeout có nghĩa migration đã rollback. Có thể một phần thay đổi đã commit hoặc tác vụ bên ngoài đã hoàn tất. Cần kiểm tra trạng thái thực tế trước khi chạy lại.

### Timeout cho cleanup

Cleanup cũng phải có ngân sách. Nếu cleanup không có timeout, runner có thể tiếp tục bị giữ sau khi test đã kết thúc. Nếu timeout quá ngắn, tài nguyên có thể bị bỏ lại mà không được ghi nhận.

Khi cleanup hết hạn:

- Lưu danh sách tài nguyên còn tồn tại.
- Ghi nguyên nhân và bước cleanup cuối cùng.
- Đánh dấu run cần dọn tiếp.
- Chuyển phần việc còn lại cho janitor hoặc quy trình vận hành.
- Không báo môi trường sạch nếu chưa xác minh.

## 4. Truyền và xử lý tín hiệu hủy

### Hủy theo tầng

Một workflow thường có cây công việc: workflow chứa stage, stage chứa job, job khởi chạy process và process tạo tiến trình con hoặc container. Tín hiệu hủy cần được truyền xuống các tầng liên quan.

~~~mermaid
flowchart TD
    A["Hủy workflow"] --> B["Hủy các stage chưa hoàn tất"]
    B --> C["Hủy job đang chạy"]
    C --> D["Gửi tín hiệu dừng đến process"]
    D --> E["Dừng task con và container"]
    E --> F["Chờ kết thúc trong grace period"]
    F --> G{"Đã dừng?"}
    G -->|Có| H["Chạy cleanup và lưu bằng chứng"]
    G -->|Không| I["Kết thúc cưỡng bức theo chính sách"]
    I --> J["Ghi tài nguyên còn sót và giao janitor"]
~~~

Sơ đồ là mô hình khái quát. Nền tảng CI có thể dùng cơ chế hủy khác nhau, vì vậy cần kiểm tra cách runner truyền tín hiệu đến process con và container thực tế.

### Hủy mềm và hủy cưỡng bức

Hủy mềm yêu cầu tác vụ dừng tại điểm an toàn. Tác vụ có thể:

- Ngừng nhận công việc mới.
- Hoàn tất hoặc rollback phần đang xử lý nếu có thể.
- Flush log và trạng thái cần thiết.
- Đóng kết nối.
- Thu hồi lock hoặc lease.
- Ghi trạng thái cancelled.

Hủy cưỡng bức kết thúc process khi thời gian chờ dừng mềm đã hết hoặc tác vụ không phản hồi. Đây là biện pháp cuối cùng vì có thể để lại trạng thái dở dang. Sau hủy cưỡng bức, cần kiểm tra tài nguyên và trạng thái nghiệp vụ trước khi tiếp tục.

### Grace period

Grace period là khoảng thời gian dành cho tác vụ thực hiện shutdown an toàn sau khi nhận tín hiệu hủy. Khoảng này cần đủ cho các bước cần thiết nhưng không dài đến mức vô hiệu hóa timeout tổng.

Quy định rõ:

- Tác vụ nào được hoàn tất trong grace period.
- Công việc mới có bị ngừng tiếp nhận không.
- Transaction đang mở được commit hay rollback.
- Message đã nhận nhưng chưa xử lý được xử lý ra sao.
- Log và artifact nào phải flush.
- Hết grace period thì hành động nào được thực hiện.

### Hủy các tiến trình con

Một lệnh build hoặc test có thể khởi chạy shell, browser, driver, server, worker và container. Chỉ kết thúc process cha chưa chắc đã dừng toàn bộ process con.

Cần kiểm tra:

- Runner có quản lý process tree không?
- Process con có nhận tín hiệu hủy không?
- Container có được stop và remove không?
- Browser hoặc driver có bị bỏ lại không?
- Background service có PID hoặc handle để dừng không?
- Có cơ chế xác minh process đã kết thúc không?

Không dùng thao tác kill theo tên process rộng nếu có thể ảnh hưởng đến job khác trên cùng máy. Ưu tiên quản lý theo process group, job object, container ID hoặc định danh thuộc run.

### Hủy tác vụ bất đồng bộ

Một job có thể đã được đưa vào queue khi runner nhận tín hiệu hủy. Việc dừng runner không tự động thu hồi message hoặc dừng worker. Cần xác định:

- Có thể hủy job bằng job ID không?
- Nếu message đã được nhận, worker có kiểm tra cancellation token không?
- Tác vụ có idempotent khi bị gửi lại không?
- Có cần đánh dấu trạng thái cancelled trong nguồn có thẩm quyền không?
- Tác dụng phụ đã xảy ra có cần bù hoặc đối soát không?
- Nếu không thể hủy, có thể để tác vụ hoàn tất và chỉ dọn sau không?

Hủy một request không có nghĩa tác dụng phụ đã được đảo ngược. Ví dụ, request thanh toán timeout có thể đã được nhà cung cấp xử lý. Phải truy vấn hoặc đối soát trạng thái trước khi thử lại hay cleanup dữ liệu liên quan.

## 5. Thiết kế shutdown an toàn cho các loại công việc

### Build và test

Khi build hoặc test bị hủy:

- Ngừng nhận test hoặc task mới.
- Lưu kết quả test đã hoàn tất.
- Ghi rõ test đang chạy bị cancelled.
- Thu thập log và artifact hữu ích.
- Dừng process con, browser và container.
- Cleanup dữ liệu theo run ID.
- Không đánh dấu suite là pass nếu một phần bị hủy.

Trạng thái cancelled cần khác passed, failed và skipped. Báo cáo phải nêu rõ phạm vi nào chưa được thực thi.

### Migration database

Khi migration bị timeout hoặc hủy:

1. Ngăn bắt đầu migration mới trên cùng phạm vi.
2. Kiểm tra migration đang ở bước nào.
3. Xác minh transaction hoặc lock còn tồn tại không.
4. Kiểm tra schema và dữ liệu thực tế.
5. Chọn tiếp tục, rollback hoặc chạy bước phục hồi theo thiết kế.
6. Ghi lại version migration và checkpoint.
7. Chỉ giải phóng môi trường khi trạng thái đã rõ.

Migration dài nên được thiết kế theo bước có thể tiếp tục hoặc có chiến lược expand-and-contract khi phù hợp. Không xóa database test ngay nếu cần bằng chứng để xác định migration đã áp dụng một phần.

### Triển khai và môi trường tạm

Khi deploy bị hủy:

- Ngừng các bước chưa bắt đầu.
- Xác định phiên bản nào đang phục vụ.
- Kiểm tra tài nguyên đã tạo hoặc thay đổi.
- Hoàn tất bước chuyển trạng thái an toàn hoặc rollback theo runbook.
- Không xóa tài nguyên đang được traffic sử dụng.
- Ghi lại trạng thái release và các bước chưa hoàn tất.
- Chỉ cleanup preview environment sau khi xác nhận không còn phụ thuộc.

Một lệnh deploy bị hủy không bảo đảm môi trường quay về phiên bản trước. Cần kiểm tra health, routing, database compatibility và trạng thái rollout.

### Performance và resilience test

Các bài tải hoặc fault injection có thể gây tác động kéo dài. Khi bị hủy:

- Dừng phát sinh tải mới.
- Dừng injector và tác nhân tạo lỗi.
- Chờ request đang xử lý kết thúc trong giới hạn.
- Khôi phục cấu hình hoặc dependency đã thay đổi.
- Xác minh hệ thống trở lại baseline.
- Thu thập metric và trace trước khi reset.
- Dọn dữ liệu và tài nguyên test sau khi an toàn.

Nếu không thể xác minh hệ thống đã trở lại trạng thái bình thường, không tự động bắt đầu test tiếp theo trên cùng môi trường.

## 6. Thiết kế cleanup đáng tin cậy

### Ghi nhận tài nguyên ngay khi tạo

Cleanup chỉ có thể thu hồi chính xác khi biết tài nguyên nào thuộc lần chạy. Ngay sau khi tạo tài nguyên, ghi nhận:

- Run ID và job ID.
- Loại tài nguyên và ID của nó.
- Môi trường và namespace.
- Chủ sở hữu hoặc suite tạo.
- Thời điểm tạo và thời điểm hết hạn.
- Trạng thái hiện tại.
- Quan hệ phụ thuộc nếu cần.

Có thể lưu registry tài nguyên ở nơi runner và janitor có thể truy cập theo quyền được cấp. Registry không nên chứa secret hoặc payload nhạy cảm.

### Cleanup theo thứ tự phụ thuộc

Tài nguyên được tạo theo quan hệ cha-con thường cần được dọn theo thứ tự ngược hoặc theo quy tắc riêng. Ví dụ:

- Dừng worker trước khi xóa queue namespace.
- Hủy job hoặc xác minh job đã kết thúc trước khi xóa dữ liệu đầu vào.
- Thu hồi token và phiên trước khi xóa tài khoản.
- Xóa file hoặc object trước khi xóa metadata tham chiếu nếu hợp đồng yêu cầu.
- Xóa bản ghi con trước bản ghi cha khi không có cascade an toàn.

Thứ tự thực tế phải dựa trên kiến trúc. Không áp dụng một thứ tự chung nếu hệ thống có audit, retention hoặc tác dụng phụ không thể đảo ngược.

### Cleanup phải idempotent

Một cleanup idempotent có thể chạy nhiều lần mà vẫn đưa tài nguyên về trạng thái mục tiêu. Điều này quan trọng khi:

- Runner bị ngắt giữa cleanup.
- Một API xóa timeout nhưng yêu cầu có thể đã thành công.
- Janitor chạy lại tài nguyên cũ.
- Nhiều bước teardown cùng phát hiện một tài nguyên.

Trước khi xóa, kiểm tra quyền sở hữu và phạm vi. Nếu tài nguyên đã không tồn tại, ghi nhận kết quả phù hợp thay vì coi đó là lỗi nghiêm trọng. Nếu tài nguyên thuộc run khác, dừng và báo lỗi.

### Tách cleanup bắt buộc và cleanup best-effort

Một số bước cleanup là bắt buộc để bảo đảm an toàn, ví dụ thu hồi credential tạm hoặc dừng load generator. Một số bước có thể best-effort, ví dụ xóa screenshot tạm đã hết hạn.

Phân loại rõ:

- **Bắt buộc:** nếu thất bại, run phải báo cleanup failure và có thể cần chặn tái sử dụng môi trường.
- **Best-effort:** có thể giao janitor xử lý sau nếu có TTL và không gây rủi ro tức thời.
- **Giữ lại có chủ đích:** artifact hoặc dữ liệu cần cho điều tra, theo retention.
- **Không thể tự xóa:** tài nguyên nhà cung cấp cần quy trình hoặc thời gian tự hết hạn.

Không gộp mọi lỗi cleanup thành cảnh báo không quan trọng. Một credential chưa thu hồi hoặc load generator còn chạy có thể gây hậu quả lớn hơn file tạm chưa xóa.

### Cleanup khi setup chỉ hoàn thành một phần

Setup có thể tạo tenant thành công nhưng thất bại khi tạo user hoặc queue. Registry cần được cập nhật từng bước để cleanup biết những tài nguyên nào đã tồn tại.

Mỗi thao tác setup nên:

1. Tạo một tài nguyên.
2. Ghi ID và trạng thái vào registry.
3. Xác minh tài nguyên có thể truy cập.
4. Tiếp tục tạo phụ thuộc tiếp theo.

Nếu ghi registry thất bại sau khi tài nguyên đã được tạo, cần có cách tìm và đối soát tài nguyên mồ côi, ví dụ marker ownership và TTL.

## 7. Bảo đảm cleanup khi runner hoặc workflow bị gián đoạn

### Không phụ thuộc duy nhất vào finally hoặc teardown

Khối finally, hook teardown hoặc bước always hữu ích khi tiến trình có cơ hội kết thúc bình thường. Tuy nhiên, chúng có thể không chạy khi:

- Máy runner bị mất điện hoặc bị thu hồi.
- Container bị kill cưỡng bức.
- Workflow bị hủy ở cấp nền tảng.
- Process bị crash hoặc hết bộ nhớ.
- Mất kết nối trước khi gửi lệnh cleanup.
- Nền tảng CI dừng job vượt giới hạn.

Do đó, cần kết hợp cleanup tại chỗ với cơ chế độc lập như TTL, janitor, lease và registry tài nguyên.

### Lease và heartbeat

Lease là quyền sử dụng tài nguyên có thời hạn. Một run có thể gia hạn lease khi còn hoạt động. Nếu heartbeat ngừng và lease hết hạn, janitor có thể xem tài nguyên là ứng viên cleanup sau khi kiểm tra ownership và trạng thái.

Cần xác định:

- Thời hạn lease và khoảng heartbeat.
- Cách gia hạn và xử lý lỗi gia hạn.
- Cách phân biệt run chậm với run đã chết.
- Điều kiện an toàn trước khi thu hồi tài nguyên.
- Cách tránh janitor xóa tài nguyên đang được run hợp lệ sử dụng.

Không dựa chỉ vào việc heartbeat vắng mặt trong một khoảng ngắn để xóa tài nguyên quan trọng. Dùng lease, run status và xác minh trạng thái kết hợp.

### Janitor hoặc sweeper

Một tiến trình độc lập có thể quét tài nguyên quá hạn hoặc thuộc run đã kết thúc. Janitor nên:

- Chỉ xử lý tài nguyên có marker và registry hợp lệ.
- Kiểm tra môi trường và owner.
- Xác minh run không còn hoạt động hoặc lease đã hết.
- Áp dụng thứ tự cleanup.
- Retry lỗi tạm thời với giới hạn.
- Ghi audit và kết quả.
- Đưa trường hợp không rõ quyền sở hữu vào hàng đợi điều tra.
- Không xóa dữ liệu cần giữ theo retention.

Janitor cần được kiểm thử riêng vì lỗi của nó có thể xóa tài nguyên ngoài phạm vi.

### TTL như lớp bảo vệ cuối

Mọi tài nguyên tạm nên có thời hạn tối đa phù hợp. TTL giúp tránh tài nguyên tồn tại vô hạn khi runner biến mất. Tuy nhiên, TTL không thay thế cleanup ngay sau khi kết thúc và không nên xóa tài nguyên đang được một run hợp lệ sử dụng.

Cần phân biệt thời điểm hết hiệu lực với thời điểm xóa vật lý. Với artifact phục vụ điều tra, retention có thể dài hơn TTL của môi trường test nhưng vẫn phải có giới hạn.

## 8. Xử lý retry, chạy lại và hủy đồng thời

### Retry sau timeout

Trước khi retry, cần xác định thao tác trước có thể đã hoàn tất hay chưa. Đây là điều đặc biệt quan trọng với:

- Tạo đơn hoặc giao dịch.
- Gửi email hoặc webhook.
- Tạo môi trường cloud.
- Áp dụng migration.
- Phát message hoặc tạo job.
- Thay đổi routing hoặc deploy.

Dùng idempotency key, operation ID hoặc truy vấn trạng thái để tránh lặp tác dụng phụ. Nếu không thể xác định kết quả, chuyển sang trạng thái cần đối soát thay vì retry mù.

### Retry cleanup

Cleanup có thể được retry nếu thao tác có tính idempotent và vẫn nằm trong phạm vi được phép. Cần:

- Giới hạn số lần và khoảng chờ.
- Lưu kết quả từng lần.
- Phân biệt lỗi tạm thời với lỗi quyền hoặc tài nguyên không tồn tại.
- Không retry vô hạn.
- Đưa tài nguyên chưa dọn vào registry hoặc hàng đợi xử lý.
- Có cảnh báo khi vượt thời hạn cleanup.

### Hủy trùng hoặc hủy đồng thời

Người dùng có thể nhấn Cancel đồng thời với timeout hoặc một stage thất bại. Hệ thống cần xử lý các tín hiệu lặp mà không chạy cleanup xung đột.

Quy định:

- Một trạng thái kết thúc có thẩm quyền cho run.
- Chuyển trạng thái có tính nguyên tử hoặc kiểm soát đồng thời.
- Cleanup chỉ có một owner hoặc dùng lease/lock phù hợp.
- Các yêu cầu hủy lặp được xem là idempotent.
- Lý do hủy đầu tiên và các tín hiệu tiếp theo được ghi lại.
- Không chuyển một run đã hoàn tất thành cancelled nếu trạng thái hoàn tất đã được xác nhận.

### Phân biệt cancelled, timed out và failed

Các trạng thái này mang ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| Passed | Các bước bắt buộc hoàn tất và đạt | Lưu bằng chứng, cleanup |
| Failed | Có bước thực thi vi phạm tiêu chí hoặc lỗi không xử lý được | Lưu lỗi, cleanup và điều tra |
| Timed out | Một deadline hết hạn trước khi đạt trạng thái cuối | Gửi hủy, xác minh trạng thái, cleanup |
| Cancelled | Có yêu cầu dừng chủ động hoặc do workflow | Dừng công việc và cleanup |
| Cleanup failed | Công việc chính đã kết thúc nhưng thu hồi tài nguyên không hoàn tất | Giao janitor, cảnh báo và giữ trạng thái |
| Incomplete/Unknown | Không xác định được kết quả do runner hoặc hệ thống mất liên lạc | Đối soát trước khi retry hoặc xóa |

Một run có thể có kết quả chính là timed out và kết quả teardown là cleanup failed. Không ghi đè nguyên nhân ban đầu bằng lỗi cleanup.

## 9. Thiết kế trạng thái và báo cáo của pipeline

### Dùng mô hình trạng thái rõ ràng

Một workflow có thể theo dõi các trạng thái:

- Queued.
- Running.
- Cancelling.
- Timed out.
- Cancelled.
- Failed.
- Succeeded.
- Cleaning up.
- Cleanup failed.
- Completed with retained artifacts.

Không phải nền tảng nào cũng hỗ trợ đúng các trạng thái này. Có thể biểu diễn bằng trạng thái chính và trường kết quả cleanup riêng, miễn là báo cáo không làm mất thông tin.

### Báo cáo deadline và bước gây timeout

Khi timeout, báo cáo nên có:

- Workflow, stage, job và step ID.
- Deadline được cấu hình.
- Thời điểm bắt đầu và thời điểm hết hạn.
- Thời gian thực thi và thời gian chờ.
- Trạng thái tác vụ cuối cùng quan sát được.
- Tín hiệu hủy đã gửi và thời gian chờ grace period.
- Process hoặc resource còn tồn tại.
- Bằng chứng log/trace liên quan.
- Trạng thái cleanup và hành động tiếp theo.

Không chỉ ghi “job timed out”. Người điều tra cần biết công việc đã bị kẹt ở đâu và tài nguyên nào còn hoạt động.

### Lưu bằng chứng trước khi cleanup

Cleanup có thể xóa dữ liệu cần để điều tra. Trước khi xóa, xác định artifact cần giữ:

- Log và trace trong khoảng thời gian liên quan.
- Test report và kết quả từng test.
- Seed, fixture ID và run metadata.
- Screenshot/video nếu có ích.
- Trạng thái migration hoặc deployment.
- ID giao dịch hoặc message cần đối soát.

Artifact phải được khử dữ liệu nhạy cảm và lưu theo retention. Không giữ toàn bộ dữ liệu môi trường chỉ vì có thể cần điều tra.

## 10. Kiểm thử chính sách timeout, hủy và cleanup

### Kiểm thử timeout

Tạo tình huống có thể kiểm soát:

- Request không phản hồi.
- Test vượt deadline.
- Job bất đồng bộ không đạt trạng thái cuối.
- Cleanup bị chậm.
- Runner không nhận được heartbeat.
- Migration chờ lock lâu hơn ngưỡng.

Xác minh timeout được phát hiện đúng cấp, báo cáo có deadline và trạng thái cuối, hành động hủy được kích hoạt và không có retry mù.

### Kiểm thử hủy mềm và hủy cưỡng bức

Xác minh:

- Tín hiệu hủy được truyền đến process con.
- Tác vụ ngừng nhận công việc mới.
- Transaction hoặc message được xử lý theo quy tắc.
- Grace period được áp dụng.
- Process không phản hồi được kết thúc theo chính sách.
- Không để lại container hoặc worker ngoài dự kiến.
- Trạng thái run phản ánh đúng phần việc chưa hoàn tất.

Thử nghiệm cần chạy trong môi trường kiểm soát để không gây ảnh hưởng đến người dùng hoặc tài nguyên ngoài phạm vi.

### Kiểm thử cleanup và janitor

Các tình huống nên gồm:

- Cleanup sau pass.
- Cleanup sau fail.
- Cleanup sau timeout.
- Cleanup sau cancel.
- Runner bị kill trước teardown.
- Setup chỉ tạo được một phần.
- API xóa timeout nhưng tài nguyên đã bị xóa.
- Tài nguyên thuộc run khác.
- Lease hết hạn trong khi run đang hoạt động.
- Janitor gặp lỗi quyền hoặc phụ thuộc.

Xác minh không xóa nhầm tài nguyên, có thể retry an toàn và mọi phần còn sót đều được ghi nhận.

### Kiểm thử race condition

Có thể xảy ra race giữa:

- Job hoàn tất và người dùng nhấn Cancel.
- Timeout và phản hồi thành công đến cùng lúc.
- Cleanup và worker đang xử lý.
- Janitor và run đang gia hạn lease.
- Retry và request ban đầu chưa xác định kết quả.

Cần xác định trạng thái có thẩm quyền và kiểm tra các chuyển trạng thái đồng thời. Chạy lại các tình huống với lịch sự kiện khác nhau để tìm lỗi cạnh tranh.

## 11. Ví dụ: pipeline CI/CD triển khai môi trường preview

Giả sử một pull request tạo môi trường preview gồm ứng dụng, database tạm, queue, worker và domain riêng. Pipeline chạy migration, smoke test và E2E, sau đó xóa môi trường khi kết thúc.

### Quy tắc timeout

- Provision có deadline riêng.
- Migration có deadline theo kích thước dữ liệu và bước thực thi.
- Smoke test và E2E có timeout riêng.
- Toàn workflow có deadline tổng.
- Cleanup có ngân sách riêng và thời gian retry giới hạn.

Các giá trị cần dựa trên số liệu thực tế. Deadline tổng phải bao gồm cả cleanup cần thiết hoặc quy định rõ phần cleanup tiếp tục qua janitor.

### Quy tắc hủy

Khi pull request bị đóng hoặc người dùng nhấn Cancel:

1. Đánh dấu run là Cancelling.
2. Ngừng stage chưa bắt đầu.
3. Gửi tín hiệu hủy cho test runner.
4. Dừng process con, browser và worker tạm.
5. Chờ grace period.
6. Kiểm tra migration và trạng thái triển khai.
7. Nếu không dừng được, kết thúc cưỡng bức theo chính sách và ghi lại phần chưa rõ.
8. Chuyển sang cleanup.

Nếu một deployment đã chuyển traffic hoặc migration đã commit, phải chạy bước phục hồi hoặc giữ môi trường để điều tra theo runbook. Không xóa database ngay chỉ vì pipeline đã bị hủy.

### Quy tắc cleanup

Mỗi tài nguyên có run ID và expiresAt:

- Domain và routing record.
- Application deployment.
- Database/schema.
- Queue và worker.
- Secret hoặc credential tạm.
- Object storage và artifact.
- Test account và dữ liệu E2E.

Cleanup dừng worker trước, xử lý queue và tác vụ còn tồn, thu hồi secret, xóa dữ liệu và hạ tầng theo dependency graph. Artifact cần điều tra được giữ riêng theo retention.

### Xác minh kết quả

Pipeline chỉ báo cleanup thành công khi:

- Tài nguyên thuộc run đã được xóa hoặc được giữ lại có chủ đích.
- Không còn worker hoặc process phục vụ preview.
- Credential tạm đã bị thu hồi.
- Routing không còn trỏ đến môi trường đã xóa.
- Registry được cập nhật.
- Tài nguyên chưa dọn được giao janitor và có cảnh báo.

Nếu cleanup thất bại, báo cáo trạng thái Cleanup failed hoặc trạng thái tương đương; không đánh dấu môi trường sạch.

## 12. Những sai lầm thường gặp

- **Chỉ đặt timeout cho workflow:** một request hoặc process con có thể chờ vô hạn.
- **Timeout mà không gửi tín hiệu hủy:** công việc nền tiếp tục chạy sau khi job kết thúc.
- **Chỉ kill process cha:** browser, worker hoặc container con vẫn tồn tại.
- **Hủy ngay không có grace period:** transaction hoặc trạng thái triển khai có thể dở dang.
- **Cleanup trước khi tác vụ dừng:** worker tiếp tục sử dụng dữ liệu đã bị xóa.
- **Dựa duy nhất vào finally hoặc teardown:** runner bị kill có thể không chạy cleanup.
- **Không ghi registry tài nguyên:** không biết chính xác thứ gì cần thu hồi.
- **Cleanup theo tên hoặc pattern rộng:** có thể xóa tài nguyên của run khác.
- **Retry sau timeout mà không đối soát:** tạo giao dịch hoặc tác dụng phụ trùng.
- **Đặt timeout quá dài để che tác vụ treo:** chiếm runner và trì hoãn phát hiện lỗi.
- **Đặt timeout quá ngắn:** tạo hủy giả khi môi trường biến động bình thường.
- **Không tách lỗi chính và lỗi cleanup:** mất nguyên nhân ban đầu.
- **Không có TTL hoặc janitor:** tài nguyên mồ côi tồn tại vô thời hạn.
- **Xóa artifact trước khi lưu bằng chứng:** làm mất khả năng điều tra.
- **Coi cleanup best-effort là luôn thành công:** không phát hiện credential hoặc worker còn sót.
- **Không kiểm thử race giữa timeout và completion:** trạng thái cuối có thể bị ghi sai.

## 13. Đầu ra cần có trước khi chốt chính sách timeout, hủy và cleanup

Một thiết kế đủ dùng nên có:

1. **Ma trận timeout:** connect, request, activity, job, stage, workflow và cleanup.
2. **Ngân sách thời gian:** baseline, phân vị, grace period và deadline tổng.
3. **Mô hình hủy:** nguồn tín hiệu, cách truyền, hủy mềm, hủy cưỡng bức và trạng thái cuối.
4. **Quy tắc theo loại công việc:** build, test, migration, deploy, performance và resilience.
5. **Danh mục tài nguyên:** owner, run ID, namespace, thời hạn và dependency.
6. **Registry tài nguyên:** cách ghi nhận, cập nhật và truy vấn tài nguyên đã tạo.
7. **Chiến lược cleanup:** thứ tự, idempotency, phân loại bắt buộc/best-effort và xử lý lỗi.
8. **Cơ chế dự phòng:** lease, heartbeat, TTL và janitor khi runner bị gián đoạn.
9. **Chính sách retry:** idempotency, đối soát và giới hạn retry sau timeout.
10. **Mô hình trạng thái và báo cáo:** phân biệt failed, timed out, cancelled và cleanup failed.
11. **Quy tắc bằng chứng:** artifact cần lưu, khử dữ liệu nhạy cảm và retention.
12. **Kế hoạch kiểm thử:** timeout, hủy, cleanup, runner interruption và race condition.

Trước khi đưa vào pipeline, hãy rà soát:

- Mỗi thao tác có timeout phù hợp và deadline tổng không?
- Hành vi khi quá hạn có được xác định rõ không?
- Tín hiệu hủy có truyền đến process con, container và tác vụ bất đồng bộ không?
- Có grace period và hành vi kết thúc cưỡng bức không?
- Trạng thái migration hoặc deploy có được xác minh trước khi cleanup không?
- Mọi tài nguyên được ghi nhận theo run ID và owner không?
- Cleanup có idempotent, giới hạn phạm vi và có thể chạy lại không?
- Có cơ chế xử lý khi runner bị kill hoặc teardown không chạy không?
- TTL và janitor có thể thu hồi tài nguyên mồ côi an toàn không?
- Retry có kiểm tra kết quả thao tác trước để tránh tác dụng phụ trùng không?
- Báo cáo có tách lỗi chính, timeout, cancel và cleanup failure không?
- Bằng chứng điều tra có được giữ theo retention mà không lộ dữ liệu nhạy cảm không?

Thiết kế timeout, hủy và cleanup giúp pipeline kết thúc có kiểm soát ngay cả khi công việc chậm, thất bại hoặc bị dừng giữa chừng. Khi deadline rõ, tín hiệu hủy được truyền đúng tầng, trạng thái dở dang được đối soát và tài nguyên được thu hồi theo ownership, nhóm có thể duy trì môi trường CI/CD ổn định và kết quả xác thực đáng tin cậy. Hãy kiểm tra lại chính sách khi thời gian chạy, kiến trúc pipeline, loại tài nguyên hoặc yêu cầu vận hành thay đổi.

