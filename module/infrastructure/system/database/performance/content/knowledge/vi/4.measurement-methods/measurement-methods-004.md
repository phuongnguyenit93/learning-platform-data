# Làm nóng hệ thống và phân biệt bộ đệm nóng với bộ đệm lạnh

Trong tối ưu hiệu năng cơ sở dữ liệu, cùng một câu truy vấn có thể có thời gian phản hồi rất khác nhau giữa lần chạy đầu tiên và những lần chạy tiếp theo. Lần đầu có thể phải đọc trang dữ liệu từ thiết bị lưu trữ, nạp trang vào bộ nhớ, biên dịch hoặc chọn kế hoạch thực thi; các lần sau có thể tận dụng dữ liệu và kế hoạch đã nằm trong bộ đệm. Nếu đo hai trạng thái này như thể chúng tương đương, kết quả benchmark sẽ khó diễn giải và có thể dẫn đến quyết định tối ưu sai.

Trong phạm vi **DATABASE_PERFORMANCE**, phương pháp đo cần mô tả rõ trạng thái hệ thống trước khi bắt đầu, cách làm nóng bằng tải đại diện và cách nhận biết bộ đệm nóng hay lạnh. Đây là một phần của quy trình đo đạc tải, phân tích kế hoạch thực thi, thống kê truy cập dữ liệu và kiểm chứng thay đổi SQL, chỉ mục, I/O hoặc bộ nhớ. Mục tiêu là tạo ra kết quả có thể lặp lại, giải thích được và phản ánh đúng điều kiện vận hành.

## 1. Bộ đệm nóng và bộ đệm lạnh là gì?

**Bộ đệm (cache/buffer)** giữ dữ liệu hoặc kết quả trung gian trong vùng truy cập nhanh để giảm công việc phải thực hiện lại. Khi dữ liệu cần thiết đã có trong bộ đệm, hệ thống thường tránh được một phần thao tác đọc từ tầng lưu trữ hoặc xử lý lại.

- **Bộ đệm lạnh (cold cache)** là trạng thái mà phần dữ liệu hoặc cấu trúc cần cho workload chưa có sẵn trong tầng cache đang xét. Hệ thống phải nạp chúng từ tầng thấp hơn hoặc tạo lại chúng trước khi tiếp tục.
- **Bộ đệm nóng (warm/hot cache)** là trạng thái mà phần lớn dữ liệu hoặc cấu trúc thường xuyên cần dùng đã có trong cache. Các lần truy cập tiếp theo có thể phục vụ từ bộ nhớ hoặc tái sử dụng kết quả đã chuẩn bị.
- **Làm nóng hệ thống (warm-up)** là quá trình chạy một workload được chọn có chủ đích để đưa các thành phần cần thiết vào trạng thái ổn định trước khi bắt đầu cửa sổ đo chính thức.

“Lạnh” và “nóng” luôn phải gắn với một tầng cache cụ thể. Một máy chủ vừa khởi động có thể có buffer pool của cơ sở dữ liệu lạnh, trong khi hệ điều hành hoặc thiết bị lưu trữ vẫn giữ một phần dữ liệu. Một truy vấn có thể dùng cache dữ liệu nóng nhưng vẫn phải tạo kế hoạch thực thi mới. Vì vậy, không nên dùng một nhãn chung “cold start” mà không nói rõ trạng thái nào được làm lạnh.

## 2. Các tầng cache ảnh hưởng đến phép đo

Một yêu cầu đọc dữ liệu có thể đi qua nhiều tầng. Tùy hệ quản trị, hệ điều hành và kiến trúc triển khai, các tầng này có thể bao gồm:

| Tầng | Nội dung được giữ | Ảnh hưởng khi lạnh | Điều cần quan sát |
|---|---|---|---|
| Cache ứng dụng | Kết quả truy vấn hoặc đối tượng nghiệp vụ | Ứng dụng phải gọi xuống cơ sở dữ liệu | Cache hit/miss, số lần gọi DB, độ trễ ứng dụng |
| Cache kế hoạch thực thi | Kế hoạch hoặc thông tin biên dịch truy vấn | Có thể phát sinh phân tích, biên dịch hoặc tối ưu lại | Số lần compile/recompile, thời gian chuẩn bị truy vấn |
| Buffer pool/buffer cache của DB | Trang dữ liệu và trang chỉ mục | Có thể phải đọc trang từ tầng lưu trữ | Logical reads, physical reads, buffer hit, page reads |
| Cache trang của hệ điều hành | Các khối dữ liệu tệp đã đọc gần đây | Có thể phát sinh I/O thiết bị nếu trang không còn trong bộ nhớ | Page cache, page faults, I/O bytes, read latency |
| Cache của thiết bị hoặc dịch vụ lưu trữ | Dữ liệu được giữ ở controller, node hoặc tầng lưu trữ phân tán | Có thể tăng độ trễ truy cập storage | IOPS, throughput, latency và số lần đọc thực tế theo công cụ của nền tảng |

Không phải hệ quản trị nào cũng dùng mọi tầng theo cùng cách. Ví dụ, PostgreSQL có shared buffers và có thể hưởng lợi từ page cache của hệ điều hành; SQL Server có buffer pool và cơ chế cache kế hoạch; InnoDB của MySQL dùng buffer pool cho trang dữ liệu và chỉ mục. Các tên gọi, số liệu và cách quản lý cache phụ thuộc phiên bản cùng cấu hình.

### Cache dữ liệu và cache kế hoạch là hai việc khác nhau

Cache dữ liệu giữ các trang hoặc khối dữ liệu đã đọc. Cache kế hoạch giữ thông tin cần để thực thi câu truy vấn. Một truy vấn có thể:

- Có kế hoạch đã được cache nhưng dữ liệu cần đọc vẫn chưa nằm trong buffer pool.
- Có dữ liệu nằm trong buffer pool nhưng cần tạo hoặc biên dịch lại kế hoạch.
- Có cả kế hoạch và dữ liệu đều nóng.
- Có cả hai đều lạnh sau khi khởi động hoặc sau một thay đổi làm mất hiệu lực cache.

Khi so sánh lần chạy đầu với lần chạy sau, cần xác định yếu tố nào đã thay đổi. Nếu lần đầu chậm vì compile và các lần sau nhanh hơn, kết luận “cache dữ liệu làm truy vấn nhanh hơn” là chưa đủ căn cứ.

## 3. Vì sao trạng thái cache làm thay đổi kết quả đo?

Khi trang dữ liệu chưa có trong bộ nhớ, cơ sở dữ liệu có thể phải đọc trang từ tầng lưu trữ rồi đưa vào buffer pool. Thao tác này thường tốn thời gian hơn đọc trang đã có trong bộ nhớ. Truy vấn quét một phạm vi lớn có thể tạo ra nhiều lượt đọc vật lý và cạnh tranh I/O với các truy vấn khác.

Khi các trang thường dùng đã nằm trong bộ nhớ, truy vấn có thể thực hiện chủ yếu bằng logical reads. Độ trễ có thể giảm, nhưng vẫn phụ thuộc CPU, khóa, số hàng cần xử lý, tính toán, mạng và mức độ đồng thời. Cache nóng không bảo đảm truy vấn luôn nhanh nếu kế hoạch thực thi kém hoặc có tranh chấp giao dịch.

Sự khác biệt còn phụ thuộc kích thước working set. **Working set** là tập dữ liệu và cấu trúc mà workload thực sự truy cập trong một khoảng thời gian. Nếu working set vừa với dung lượng cache hữu dụng, hệ thống có thể giữ phần lớn dữ liệu cần thiết. Nếu working set lớn hơn nhiều so với cache, trang liên tục bị thay thế và tỷ lệ cache hit có thể giảm dù workload đã chạy lâu.

Một tỷ lệ cache hit cao cũng không tự động chứng minh hệ thống khỏe. Chỉ số này có thể cao vì workload rất nhỏ, vì truy vấn lặp lại cùng một trang, hoặc vì mẫu đo chưa bao gồm các thao tác nặng. Hãy đọc tỷ lệ cùng số lần đọc tuyệt đối, lượng dữ liệu, độ trễ I/O và độ trễ truy vấn.

## 4. Phân biệt phép đo lạnh và phép đo nóng

Hai trạng thái trả lời hai câu hỏi vận hành khác nhau.

**Đo lạnh** giúp hiểu hành vi khi hệ thống phải nạp dữ liệu hoặc cấu trúc cần thiết từ tầng thấp hơn. Trạng thái này hữu ích khi đánh giá:

- Lần truy cập đầu sau khi triển khai hoặc khởi động lại.
- Khối lượng đọc tăng đột biến sau một khoảng thời gian ít hoạt động.
- Truy vấn báo cáo hoặc truy vấn ít gặp có working set chưa nằm trong bộ nhớ.
- Khả năng phục hồi hiệu năng sau failover hoặc thay thế node.

**Đo nóng** giúp hiểu hiệu năng khi hệ thống đã chạy với workload đại diện và các trang thường dùng đã được nạp. Trạng thái này phù hợp để đánh giá:

- Độ trễ ổn định trong giờ hoạt động thông thường.
- Khả năng phục vụ workload lặp lại.
- Hiệu quả của chỉ mục và thay đổi SQL sau khi hệ thống ổn định.
- Khả năng duy trì cache residency khi có đồng thời và tải kéo dài.

Kết quả lạnh và nóng nên được báo cáo thành hai nhóm. Không lấy một lượt lạnh duy nhất rồi gộp với hàng trăm lượt nóng để tính một con số trung bình, vì số liệu đó phụ thuộc vào tỷ lệ lượt chạy ở mỗi trạng thái và không đại diện rõ ràng cho tình huống nào.

## 5. Xác định mục tiêu warm-up trước khi đo

Warm-up không đơn giản là chạy truy vấn vài lần rồi bắt đầu đồng hồ. Cần xác định điều kiện nào cho thấy workload đã đạt trạng thái đủ ổn định.

Trước hết, mô tả workload cần làm nóng:

- Nhóm giao dịch và truy vấn quan trọng.
- Tần suất tương đối của từng nhóm.
- Phân bố tham số và độ chọn lọc của dữ liệu.
- Tập bảng, phân vùng và chỉ mục thường được truy cập.
- Mức đồng thời dự kiến.
- Khoảng thời gian hoạt động cần mô phỏng.
- Dung lượng dữ liệu và kích thước working set gần với môi trường thực tế.

Sau đó, chọn các dấu hiệu để xác nhận warm-up. Có thể dùng một số điều kiện kết hợp:

1. Số lượt đọc vật lý hoặc lượng đọc từ storage giảm về mức ổn định đối với workload đang chạy.
2. Logical reads trên mỗi giao dịch không dao động bất thường giữa các cửa sổ đo.
3. Độ trễ p50, p95 và p99 ổn định qua nhiều cửa sổ liên tiếp.
4. Cache residency hoặc buffer hit của nhóm dữ liệu mục tiêu đạt vùng ổn định, nếu hệ quản trị cung cấp số liệu phù hợp.
5. CPU, I/O và hàng đợi không còn biến động do chính quá trình nạp cache.
6. Tỷ lệ hoàn tất, số lỗi và số timeout không cho thấy warm-up đang làm hệ thống quá tải.

Không có một ngưỡng phần trăm cache hit hoặc một thời gian warm-up cố định phù hợp cho mọi hệ thống. Hãy chọn tiêu chí theo workload và ghi lại chúng trong báo cáo để người khác có thể lặp lại phép đo.

## 6. Thiết kế workload làm nóng có tính đại diện

Một workload warm-up tốt cần tái hiện tập truy cập mà hệ thống sẽ gặp trong cửa sổ đo. Chạy lặp một câu SELECT nhỏ có thể làm nóng vài trang nhưng không đại diện cho hệ thống có nhiều loại giao dịch.

Ví dụ, ứng dụng bán hàng có thể có các nhóm thao tác như:

- Tra cứu sản phẩm theo mã và theo danh mục.
- Đọc tồn kho và giá theo cửa hàng.
- Tạo đơn hàng và cập nhật trạng thái.
- Đọc lịch sử giao dịch của khách hàng.
- Truy vấn báo cáo theo ngày hoặc theo vùng.

Nếu chỉ làm nóng truy vấn tra cứu một sản phẩm phổ biến, cache có thể chứa một số trang rất nhỏ nhưng chưa có dữ liệu tồn kho, chỉ mục lịch sử hoặc phân vùng báo cáo. Phép đo sau đó sẽ phản ánh một workload lệch.

Hãy lấy phân bố truy cập từ log, trace hoặc thống kê truy vấn đã được làm sạch. Dùng các tham số đại diện: giá trị phổ biến, giá trị ít gặp, phạm vi ngày rộng và hẹp, bản ghi có nhiều hoặc ít quan hệ liên quan. Nếu chỉ dùng một tham số cố định, cache có thể nóng cho một nhánh dữ liệu nhưng lạnh với phần còn lại.

### Tránh warm-up làm thay đổi dữ liệu nghiệp vụ

Đối với truy vấn đọc, có thể chạy các thao tác đại diện trên dữ liệu kiểm thử hoặc dữ liệu chỉ đọc. Đối với giao dịch ghi, cần có dữ liệu riêng, transaction có thể rollback hoặc cơ chế khôi phục trạng thái để không tạo ra đơn hàng, thanh toán hay cập nhật tồn kho ngoài ý muốn.

Một số giao dịch ghi có thể làm nóng trang dữ liệu nhưng đồng thời thay đổi trạng thái, tạo log, làm bẩn buffer và kích hoạt checkpoint. Vì vậy, không nên xem việc phát lại toàn bộ luồng ghi trên cơ sở dữ liệu thật là một cách warm-up vô hại. Hãy dùng môi trường thử nghiệm có thể khôi phục hoặc kịch bản được thiết kế để an toàn.

## 7. Quy trình đo trạng thái nóng

Một quy trình đo nóng có thể tổ chức thành các bước sau:

1. **Cố định cấu hình:** ghi phiên bản hệ quản trị, cấu hình bộ nhớ, kích thước pool, chỉ mục, thống kê, phiên bản ứng dụng và cấu hình workload.
2. **Chuẩn bị dữ liệu:** dùng cùng snapshot hoặc bộ dữ liệu có kích thước và phân bố tương đương cho các lần so sánh.
3. **Khởi động và kiểm tra:** xác nhận dịch vụ sẵn sàng, kết nối hoạt động và không có sự kiện bảo trì hoặc tải nền bất thường.
4. **Chạy warm-up:** phát workload đại diện với mức đồng thời dự kiến; không đưa thời gian warm-up vào cửa sổ đo chính thức.
5. **Kiểm tra điều kiện ổn định:** xem physical reads, độ trễ phân vị, cache/buffer, CPU, I/O và hàng đợi qua nhiều cửa sổ.
6. **Đo chính thức:** giữ nguyên workload, thời lượng và mức đồng thời; thu thập số liệu ở cùng khoảng thời gian.
7. **Lặp lại:** thực hiện nhiều lượt để thấy độ biến thiên; ghi rõ cache có được giữ giữa các lượt hay không.

Ví dụ giả mã mô tả ranh giới giữa warm-up và đo chính thức:

~~~text
prepare_database_with_known_dataset()
verify_configuration_and_background_activity()

start_warmup()
run_representative_workload(duration_or_until_stable)
stop_warmup()

if not warmup_criteria_met:
    mark_run_invalid_or_continue_warmup()

start_measurement_window()
run_same_workload_at_target_concurrency()
collect_latency_errors_reads_cpu_io_and_cache_metrics()
stop_measurement_window()

save_run_metadata_and_results()
~~~

Điều kiện ổn định phải được định nghĩa trước khi chạy. Nếu người thực hiện tự chọn thời điểm bắt đầu đo sau khi nhìn thấy kết quả, phép đo dễ bị thiên lệch.

## 8. Quy trình đo trạng thái lạnh

Đo lạnh khó chuẩn hóa hơn vì nhiều tầng cache nằm ngoài quyền kiểm soát trực tiếp của ứng dụng. Khởi động lại tiến trình cơ sở dữ liệu có thể làm mất một phần cache nội bộ, nhưng dữ liệu vẫn có thể nằm trong page cache của hệ điều hành hoặc cache của nền tảng lưu trữ. Ngược lại, khởi động lại máy chủ có thể ảnh hưởng đến môi trường và không phải lúc nào cũng tạo ra trạng thái lạnh hoàn toàn.

Một phép đo lạnh có thể được tổ chức trong môi trường kiểm thử cô lập:

1. Chuẩn bị một bản dữ liệu có thể khôi phục về cùng trạng thái.
2. Xác định rõ muốn làm lạnh tầng nào: cache dữ liệu của DB, cache kế hoạch, cache ứng dụng hay toàn bộ đường đọc.
3. Dùng cơ chế khởi tạo lại được hỗ trợ bởi hệ quản trị hoặc nền tảng trong môi trường thử nghiệm.
4. Ghi nhận những tầng cache không thể làm lạnh hoặc không thể xác minh.
5. Chạy đúng workload và tham số đã định nghĩa; ghi riêng lượt đầu và các lượt kế tiếp.
6. Khôi phục trạng thái ban đầu trước lần lặp tiếp theo nếu mục tiêu là so sánh nhiều lần cold start.
7. Báo cáo điều kiện thực tế thay vì gọi phép đo là “cold hoàn toàn” khi page cache hoặc cache storage vẫn còn dữ liệu.

Không nên xóa cache toàn cục, khởi động lại máy chủ hoặc ép hệ điều hành loại bỏ trang bộ nhớ trên hệ thống production chỉ để tạo một phép đo lạnh. Những thao tác đó có thể làm suy giảm hiệu năng của các ứng dụng khác và tạo ra một sự kiện vận hành ngoài dự kiến. Hãy dùng môi trường benchmark được kiểm soát, bản sao dữ liệu hoặc quy trình bảo trì đã được phê duyệt.

### Cold cache không đồng nghĩa với lần chạy đầu tiên của mọi truy vấn

Một lần chạy đầu có thể bị ảnh hưởng bởi nhiều yếu tố ngoài cache dữ liệu: kết nối mới, TLS handshake, tạo session, tải thư viện, JIT ở tầng ứng dụng, compile kế hoạch, khởi tạo pool và các tác vụ nền. Khi muốn đo riêng cache dữ liệu, hãy giữ các yếu tố này cố định hoặc đo riêng từng thành phần.

Ví dụ, có thể tạo pool kết nối trước và xác nhận kết nối ổn định, nhưng vẫn khởi tạo cache dữ liệu theo trạng thái thử nghiệm đã định. Nếu mục tiêu là đo trải nghiệm cold start đầu cuối của ứng dụng, cần ghi nhận tất cả các bước khởi tạo như một phần của phép đo và mô tả rõ phạm vi đó.

## 9. Chọn chỉ số để xác nhận cache đang nóng hay lạnh

Không nên dựa vào một chỉ số duy nhất. Kết hợp số liệu của ứng dụng, hệ quản trị, hệ điều hành và tầng lưu trữ.

| Chỉ số | Dấu hiệu có thể gặp khi lạnh | Dấu hiệu có thể gặp khi nóng | Giới hạn khi diễn giải |
|---|---|---|---|
| Physical reads / số trang đọc từ storage | Tăng khi trang chưa có trong buffer hoặc cache thấp hơn | Giảm khi trang thường dùng đã được giữ trong cache | Cách đếm khác nhau theo hệ quản trị; cần biết phạm vi |
| Logical reads | Có thể cao nếu truy vấn phải xử lý nhiều trang | Có thể ổn định giữa các lượt | Logical reads không chứng minh trang được lấy từ storage |
| Buffer/cache hit | Có thể thấp trong giai đoạn nạp dữ liệu | Có thể tăng khi working set được giữ lại | Tỷ lệ tổng hợp có thể che khuất một nhóm truy vấn xấu |
| Read latency và I/O queue | Có thể tăng khi phát sinh đọc vật lý | Có thể giảm khi phần lớn đọc được phục vụ từ bộ nhớ | Bị ảnh hưởng bởi nhiều workload cùng dùng storage |
| p95/p99 latency | Có thể cao ở lượt đầu | Có thể giảm và ổn định | Còn phụ thuộc khóa, CPU, mạng và mức đồng thời |
| CPU và thời gian compile | Có thể tăng khi chuẩn bị kế hoạch hoặc nạp metadata | Có thể giảm nếu kế hoạch được tái sử dụng | Cache dữ liệu và cache kế hoạch cần được tách riêng |
| Cache eviction / page turnover | Có thể cao khi working set lớn hoặc warm-up gây áp lực | Có thể thấp hơn khi working set phù hợp | Phải diễn giải cùng dung lượng và chính sách thay thế |

Khi báo cáo, hãy lưu cả giá trị tuyệt đối và tỷ lệ. Ví dụ, cache hit 99% trên 100 lượt đọc khác với 99% trên hàng tỷ lượt đọc; số lượng đọc vật lý còn lại và độ trễ của chúng có thể tạo ảnh hưởng rất khác nhau.

## 10. Ví dụ: đo truy vấn danh mục sản phẩm

Giả sử một truy vấn đọc danh mục sản phẩm theo nhóm có độ trễ 180 ms ở lần chạy đầu, sau đó còn 25 ms ở các lần chạy tiếp theo. Chỉ nhìn hai con số chưa đủ kết luận nguyên nhân.

Một cách điều tra có hệ thống:

1. Ghi lại execution plan, số hàng trả về, logical reads, physical reads và thời gian CPU của truy vấn.
2. Đối chiếu số liệu buffer pool và page cache trước, trong và sau lần chạy đầu.
3. Kiểm tra thời gian compile hoặc chuẩn bị truy vấn để xác định có chi phí tạo kế hoạch đáng kể hay không.
4. Chạy lại với cùng tham số và cùng dữ liệu, quan sát physical reads có giảm trong khi logical reads tương đối ổn định không.
5. Thay đổi tham số để truy cập nhóm sản phẩm khác, xem mức giảm độ trễ có lặp lại hay chỉ xảy ra với một nhóm trang đã được nạp.
6. Chạy workload nhiều người dùng để xác định các trang đã nạp có còn được giữ trong cache khi tải thực tế tăng hay bị thay thế liên tục.

Nếu physical reads giảm rõ rệt và độ trễ giảm tương ứng, dữ liệu cache có thể là một phần nguyên nhân. Nếu physical reads gần như không đổi nhưng compile time giảm, khác biệt có thể đến từ cache kế hoạch. Nếu cả hai đều ổn định nhưng p99 tăng khi nhiều người dùng chạy đồng thời, cần điều tra CPU, khóa, I/O queue và tài nguyên khác.

## 11. Những sai lầm thường gặp khi làm nóng và đo cache

- **Chạy một truy vấn duy nhất để warm-up:** chỉ một phần nhỏ working set được nạp, khiến kết quả không đại diện.
- **Warm-up bằng tham số quá phổ biến:** cache chỉ nóng cho dữ liệu thường gặp, trong khi các trường hợp ít gặp vẫn lạnh.
- **Bắt đầu đo theo thời gian cố định:** thời gian đó có thể quá ngắn với dữ liệu lớn hoặc quá dài với workload nhỏ. Hãy xác nhận tiêu chí ổn định.
- **Gộp lượt lạnh và lượt nóng:** trung bình cuối cùng khó giải thích và phụ thuộc số lượt ở mỗi trạng thái.
- **Dùng cache hit ratio làm bằng chứng duy nhất:** tỷ lệ cao vẫn có thể đi cùng p99 xấu, I/O lớn hoặc một truy vấn quan trọng bị cache miss.
- **Coi restart DB là làm lạnh toàn bộ:** page cache hệ điều hành và cache storage có thể vẫn giữ dữ liệu.
- **Chạy warm-up với tải quá mạnh:** quá trình nạp cache có thể tạo I/O burst, tăng hàng đợi và đẩy các trang hữu ích khác ra khỏi cache.
- **Thay đổi cấu hình giữa các lần đo:** dung lượng buffer, số kết nối, thống kê hoặc chỉ mục khác nhau khiến kết quả không còn so sánh trực tiếp.
- **Bỏ qua tác vụ nền:** checkpoint, backup, vacuum, compaction, replication hoặc tác vụ bảo trì có thể ảnh hưởng đến I/O và độ trễ.
- **Đọc kết quả mà không ghi metadata:** không lưu trạng thái cache, thời gian khởi động, workload và mức tải sẽ khiến phép đo khó tái lập.

## 12. Dùng kết quả cache để đánh giá thay đổi SQL và chỉ mục

Khi tối ưu SQL hoặc thiết kế chỉ mục, cần đo cả trạng thái lạnh và nóng nếu cả hai đều xuất hiện trong vận hành.

Một chỉ mục mới có thể giảm số trang phải đọc và cải thiện truy vấn ở trạng thái lạnh. Nhưng chỉ mục cũng làm tăng kích thước dữ liệu, chi phí ghi và áp lực bộ nhớ. Nếu chỉ đo khi cache nóng, phần đọc từ storage vốn đã ít có thể khiến lợi ích của chỉ mục khó thấy; ngược lại, nếu chỉ đo lạnh, có thể đánh giá quá cao lợi ích trong workload chủ yếu chạy trên cache.

Hãy so sánh trước và sau thay đổi theo cùng quy trình:

- Dùng cùng snapshot dữ liệu, cùng phiên bản hệ quản trị và cùng cấu hình.
- Cập nhật hoặc thu thập thống kê theo quy trình giống nhau.
- Đo cold run trong môi trường có thể khôi phục và ghi rõ tầng cache được kiểm soát.
- Warm-up bằng cùng workload, cùng phân bố tham số và mức đồng thời.
- Đo p50, p95, p99, throughput, logical reads, physical reads, CPU, I/O và dung lượng chỉ mục.
- Kiểm tra cả truy vấn đọc lẫn thao tác ghi chịu ảnh hưởng bởi chỉ mục.
- Lặp lại đủ số lượt để đánh giá biến thiên; giữ nguyên quy tắc loại bỏ warm-up.
- Xác nhận kết quả dữ liệu và tính đúng đắn giao dịch sau điều chỉnh.

Không kết luận một thay đổi tốt chỉ vì lượt chạy nóng nhanh hơn. Cần xác định liệu hiệu năng cải thiện do kế hoạch tốt hơn, số trang đọc ít hơn, dữ liệu đã được cache hay một điều kiện tải khác đã thay đổi.

## 13. Ghi nhận điều kiện đo để người khác có thể lặp lại

Mỗi lượt benchmark nên có một bản mô tả ngắn gồm:

| Trường cần lưu | Nội dung |
|---|---|
| Mục tiêu đo | Cold start, warm steady state hoặc khả năng giữ cache dưới tải |
| Phạm vi cache | Cache ứng dụng, kế hoạch, buffer pool, page cache hoặc tầng storage |
| Cách chuẩn bị | Khởi động lại, khôi phục snapshot, warm-up workload hoặc giữ nguyên trạng thái |
| Dữ liệu | Kích thước, phân bố, snapshot và trạng thái thống kê |
| Workload | Nhóm truy vấn, tỷ lệ đọc/ghi, tham số và phân bố tần suất |
| Tải | Số người dùng đồng thời, tốc độ gửi yêu cầu và thời lượng |
| Tiêu chí warm-up | Điều kiện ổn định đã chọn và số cửa sổ liên tiếp cần đạt |
| Chỉ số | Độ trễ phân vị, throughput, reads, cache, CPU, I/O, lỗi và timeout |
| Tác vụ nền | Backup, checkpoint, vacuum, replication hoặc sự kiện liên quan |
| Giới hạn | Tầng cache không thể làm lạnh, không thể quan sát hoặc nằm ngoài quyền kiểm soát |

Metadata này giúp phân biệt một thay đổi hiệu năng thật với sự khác biệt do môi trường. Khi so sánh nhiều lần chạy, cần đối chiếu điều kiện đo trước khi so sánh số liệu.

## 14. Checklist thực hiện phép đo

- [ ] Đã xác định rõ đang đo cache dữ liệu, cache kế hoạch hay cold start đầu cuối.
- [ ] Đã mô tả các tầng cache có mặt trong kiến trúc.
- [ ] Đã chuẩn bị dữ liệu và cấu hình tương đương giữa các lần chạy.
- [ ] Workload warm-up phản ánh nhóm truy vấn, tham số và working set thực tế.
- [ ] Giao dịch ghi trong warm-up không làm thay đổi dữ liệu nghiệp vụ ngoài ý muốn.
- [ ] Tiêu chí kết thúc warm-up được xác định trước và kiểm tra bằng nhiều chỉ số.
- [ ] Thời gian warm-up không bị tính vào cửa sổ benchmark chính thức.
- [ ] Cold run được thực hiện trong môi trường kiểm soát, có thể khôi phục và ghi rõ giới hạn cache.
- [ ] Không xóa cache hoặc khởi động lại hạ tầng production chỉ để phục vụ benchmark.
- [ ] Kết quả nóng và lạnh được báo cáo riêng với p50, p95, p99 và số lần đọc.
- [ ] Đã ghi nhận CPU, I/O, bộ nhớ, cache eviction, lỗi và timeout.
- [ ] Đã lặp lại phép đo và lưu metadata để có thể tái lập.
- [ ] Sau khi thay đổi SQL hoặc chỉ mục, đã kiểm tra cả hiệu năng đọc, ghi và tính đúng đắn dữ liệu.

Làm nóng hệ thống giúp phép đo phản ánh trạng thái hoạt động ổn định, còn đo lạnh cho biết chi phí khi dữ liệu hoặc cấu trúc cần thiết chưa có trong cache. Hai trạng thái đều có giá trị nếu được xác định đúng phạm vi và kiểm soát được điều kiện thử nghiệm. Khi kết hợp workload đại diện, tiêu chí warm-up rõ ràng, số liệu ở nhiều tầng và metadata đầy đủ, nhóm phát triển có thể giải thích sự khác biệt giữa các lần chạy và đánh giá đáng tin cậy tác động của thay đổi SQL, chỉ mục, bộ nhớ và I/O.
