# Chọn giải pháp theo tần suất khởi động, trạng thái ứng dụng và chi phí tích hợp

Một ứng dụng Java khởi động chậm không tự động có nghĩa là ứng dụng đó cần CRaC (Coordinated Restore at Checkpoint). Có nhiều cách giảm thời gian từ lúc process được tạo đến lúc ứng dụng sẵn sàng: tối ưu startup, dùng Class Data Sharing (CDS/AppCDS), dùng các kỹ thuật AOT, biên dịch thành native executable, giữ sẵn instance trong warm pool hoặc tạo checkpoint để restore tiến trình đã warm-up.

Mỗi cách giải quyết một phần khác nhau của bài toán. Một số giảm chi phí khởi tạo class và runtime; một số loại bỏ bước khởi động JVM thông thường; một số giữ sẵn process; CRaC khôi phục trạng thái của một tiến trình đã chạy. Lợi ích thực tế phụ thuộc vào tần suất cần tạo instance mới, mức độ stateful của ứng dụng, thời gian warm-up, yêu cầu tương thích và chi phí tích hợp.

Bài này đưa ra cách lựa chọn giải pháp theo ba nhóm yếu tố chính:

- **Tần suất khởi động:** hệ thống thường xuyên tạo process mới hay giữ instance chạy dài hạn?
- **Trạng thái ứng dụng:** startup chỉ tạo object nội bộ hay còn kết nối database, nạp secret, cache, session, lease và tài nguyên bên ngoài?
- **Chi phí tích hợp:** đội ngũ phải thay đổi code, build, runtime, hạ tầng, kiểm thử và vận hành đến mức nào?

Mục tiêu là chọn giải pháp đáp ứng mục tiêu time-to-ready với tổng chi phí và rủi ro phù hợp. Không nên chọn CRaC chỉ vì nó có khả năng restore nhanh; cần xác định phần thời gian nào thực sự có thể tiết kiệm và phần state nào có thể phục hồi an toàn.

## 1. Xác định vấn đề khởi động cần giải quyết

Trước khi so sánh công nghệ, cần đo đúng thời gian khởi động. Một ứng dụng Java thường đi qua nhiều giai đoạn:

1. Container hoặc VM được cấp phát.
2. JVM process được tạo.
3. JVM nạp runtime, module và class.
4. Framework tạo application context.
5. Ứng dụng đọc cấu hình và secret.
6. Kết nối database, broker, cache và service khác.
7. Nạp dữ liệu hoặc dựng cache.
8. Warm-up JIT và các đường xử lý quan trọng.
9. Chạy health check.
10. Readiness chuyển sang true và instance nhận traffic.

Thời gian từ bước 1 đến bước 9 có thể dài hơn nhiều so với thời gian JVM process bắt đầu chạy. Nếu chỉ đo thời gian thực thi lệnh java, bạn có thể tối ưu nhầm phần không phải bottleneck.

### 1.1 Phân tách các mốc thời gian

Có thể ghi nhận các mốc sau:

~~~text
T0: container/VM allocation begins
T1: container is running
T2: JVM process starts
T3: application context initialized
T4: mandatory dependencies connected
T5: cache and warm-up completed
T6: readiness becomes true
T7: first production request completes
~~~

Các chỉ số có ý nghĩa:

- **Container provisioning time:** T1 - T0.
- **JVM startup time:** từ T2 đến lúc JVM có thể thực thi application code.
- **Application initialization time:** T3 - T2.
- **Dependency initialization time:** T4 - T3.
- **Warm-up time:** T5 - T4.
- **Time-to-ready:** T6 - T0.
- **First-request latency:** thời gian xử lý request đầu tiên sau khi nhận traffic.

Time-to-ready thường là chỉ số quan trọng với autoscaling, serverless-like workload và rollout. First-request latency quan trọng khi JIT hoặc cache tiếp tục warm-up sau readiness.

### 1.2 Đo phân phối, không chỉ một lần chạy

Startup time có thể biến động do tải node, image pull, DNS, database, network, GC, JIT và cache. Hãy đo nhiều lần và theo dõi p50, p95, p99 cùng số lần cold start.

Ví dụ, p50 startup 2 giây nhưng p99 là 18 giây có thể gây vấn đề lớn khi scale-out đột ngột. Ngược lại, startup 8 giây ổn định có thể chấp nhận được với service chỉ deploy vài lần mỗi ngày.

Cần phân biệt:

- Cold start trên host chưa có container image.
- Cold start khi image đã có trên node.
- JVM start mới trong container đã chạy.
- Restore checkpoint từ local storage.
- Restore checkpoint sau khi tải artifact qua network.
- Instance restart sau crash.
- Scale-out do traffic tăng.

Các trường hợp này có chi phí khác nhau. Đừng so sánh CRaC restore từ local disk với JVM startup bao gồm cả image pull rồi kết luận CRaC luôn nhanh hơn.

## 2. Tần suất khởi động quyết định giá trị kinh tế

Giảm startup time có giá trị nhất khi hệ thống thường xuyên cần instance mới và độ trễ khởi động ảnh hưởng tới latency, capacity hoặc chi phí.

Tần suất khởi động có thể đến từ:

- Autoscaling khi traffic thay đổi.
- Serverless hoặc scale-to-zero.
- Rolling deployment.
- Node replacement và cluster upgrade.
- Crash recovery.
- Batch job hoặc worker chạy theo lịch.
- Test environment được tạo và hủy liên tục.
- Tenant hoặc workload mới cần process riêng.
- Burst workload theo giờ hoặc theo mùa.

Một service chạy liên tục nhiều tuần và chỉ restart khi deploy có thể không thu được nhiều lợi ích từ checkpoint. Một worker được tạo hàng nghìn lần mỗi ngày có thể hưởng lợi lớn nếu startup và warm-up chiếm phần đáng kể trong thời gian xử lý.

### 2.1 Phân biệt request frequency và process startup frequency

Một API có hàng triệu request mỗi giờ nhưng chỉ chạy một nhóm instance ổn định. Request frequency cao không có nghĩa process startup frequency cao.

Ngược lại, một job chỉ nhận vài request nhưng mỗi request tạo một JVM riêng. Process startup frequency trong trường hợp đó rất cao.

Hãy đo:

- Số instance mới mỗi phút/giờ/ngày.
- Số lần restart mỗi instance.
- Tỷ lệ instance được tạo do autoscaling.
- Tỷ lệ cold start so với warm reuse.
- Số workload kết thúc nhanh sau khi startup.
- Số lần checkpoint/restore thực tế có thể thay thế startup mới.

### 2.2 Tính số phút khởi động có thể tiết kiệm

Một ước lượng đơn giản:

~~~text
SavedStartupTime =
    NewInstancesPerPeriod
    x (BaselineTimeToReady - OptimizedTimeToReady)
~~~

Ví dụ:

- Baseline time-to-ready: 12 giây.
- Sau tối ưu: 4 giây.
- Số instance mới: 900 mỗi ngày.

Thời gian chờ tiết kiệm được:

~~~text
900 x (12 - 4) = 7,200 seconds
                     = 120 minutes/day
~~~

Đây là tổng thời gian khởi động tiết kiệm trên các lần tạo instance, không phải 120 phút CPU time hoặc 120 phút tiết kiệm chi phí trực tiếp. Cần xác định phần lợi ích nào thực sự chuyển thành doanh thu, latency, capacity hoặc giảm tài nguyên.

### 2.3 Khi tần suất khởi động thấp

Nếu instance chạy dài hạn và restart hiếm, nên ưu tiên:

- Tối ưu startup path.
- Loại bỏ initialization không cần thiết.
- Kết nối dependency lazy khi phù hợp.
- Dùng CDS/AppCDS nếu class loading đáng kể.
- Điều chỉnh deployment strategy và readiness.
- Giữ một lượng warm capacity nhỏ nếu chi phí hợp lý.

CRaC có thể vẫn hữu ích nếu startup cực kỳ đắt hoặc rollout cần phục hồi nhanh, nhưng phải tính chi phí tạo, kiểm thử, lưu trữ và duy trì checkpoint artifact.

## 3. Trạng thái ứng dụng ảnh hưởng tới khả năng dùng từng giải pháp

Hai ứng dụng có cùng thời gian startup có thể cần giải pháp khác nhau vì trạng thái chúng giữ trong bộ nhớ khác nhau.

### 3.1 Ứng dụng stateless hoặc gần stateless

Ví dụ:

- API đọc dữ liệu từ database.
- Worker xử lý request độc lập.
- Service chỉ giữ cache có thể rebuild.
- Application context không gắn với một tenant hoặc instance cụ thể.

Những ứng dụng này thường dễ dùng CRaC hơn vì sau restore có thể:

- Reconnect database.
- Resolve endpoint mới.
- Lấy credential theo workload identity.
- Rebuild cache.
- Rejoin broker group.
- Mở readiness sau khi validation hoàn tất.

Tuy nhiên, stateless ở tầng nghiệp vụ không có nghĩa process không giữ state. HTTP client, TLS context, thread pool, scheduler, DNS cache và framework singleton vẫn có thể giữ trạng thái runtime.

### 3.2 Ứng dụng stateful

Ví dụ:

- Session store nằm trong heap.
- In-memory workflow engine.
- Long-running stream processor.
- Game server giữ session hoặc world state.
- Worker giữ cursor, offset hoặc state machine.
- Service có leader lease hoặc lock.
- Application giữ native handle hoặc connection lâu dài.

Với nhóm này, cần trả lời:

- State có được lưu bền vững ở ngoài process không?
- Có thể replay hoặc reconstruct sau restore không?
- Có instance identity hoặc ownership gắn với process cũ không?
- State có thể bị nhân bản khi restore cùng image nhiều lần không?
- Có thể tạo duplicate side effect không?
- Có cần fencing token hoặc coordination bên ngoài không?
- State có hết hạn trong lúc image được giữ không?

Nếu state chỉ tồn tại trong heap và không có cách durable hoặc reconcile, việc restore một image có thể đưa ứng dụng trở lại một snapshot cũ. Điều đó có thể gây mất cập nhật hoặc lặp xử lý. Trước khi chọn CRaC, cần thiết kế state recovery.

### 3.3 Phân loại state

| Loại state | Ví dụ | Cách xử lý khi restore |
|---|---|---|
| Immutable startup data | Rule cố định theo release, parsed metadata | Có thể giữ nếu version tương thích |
| Rebuildable cache | Reference data, computed lookup | Giữ nếu còn hợp lệ hoặc rebuild |
| Dynamic configuration | Feature flags, endpoint, limits | Refresh theo revision/policy |
| Credentials | Token, secret, certificate | Lấy mới hoặc revalidate |
| External connections | JDBC, HTTP pool, broker client | Đóng/recreate/reconnect |
| Durable business state | Order, account, workflow record | Đọc từ nguồn có thẩm quyền |
| Temporary ownership | Lease, lock, leader state | Reacquire hoặc validate |
| Event processing state | Offset, cursor, assignment | Rejoin/replay/deduplicate |
| Instance-specific identity | Pod ID, node ID, process generation | Cấp lại sau restore |

Một checkpoint tốt thường giữ lại những trạng thái khởi tạo tốn kém nhưng ổn định, đồng thời phục hồi các trạng thái động và tài nguyên bên ngoài sau restore.

## 4. Các lựa chọn giảm startup time

Không có một giải pháp phù hợp với mọi workload. Hãy so sánh các lựa chọn theo phần startup mà chúng giảm được, mức độ thay đổi ứng dụng và chi phí vận hành.

### 4.1 Tối ưu startup thông thường

Đây thường là bước đầu tiên nên thực hiện:

- Loại bỏ classpath và dependency không cần thiết.
- Trì hoãn initialization không phục vụ request đầu tiên.
- Giảm số lần scan classpath hoặc component scan.
- Tránh tải toàn bộ dữ liệu nếu chỉ một phần cần ngay.
- Dùng connection pool có kích thước phù hợp.
- Giảm các lần gọi network tuần tự trong startup.
- Chạy các bước độc lập song song nếu an toàn.
- Chuyển tác vụ không bắt buộc sang background sau readiness.
- Đo và loại bỏ initializer chậm.

Ưu điểm:

- Ít phụ thuộc nền tảng.
- Dễ debug.
- Giữ mô hình JVM thông thường.
- Không cần checkpoint artifact hoặc native executable.
- Có thể cải thiện cả startup lẫn vận hành lâu dài.

Nhược điểm:

- Có giới hạn; một số framework hoặc workload có chi phí khởi tạo vốn dĩ lớn.
- Lazy initialization có thể chuyển latency sang request đầu tiên.
- Chạy background có thể làm readiness phản ánh không đầy đủ mức sẵn sàng.

Nên bắt đầu bằng profiling startup và xác định bottleneck trước khi thêm công nghệ mới.

### 4.2 Class Data Sharing (CDS) và AppCDS

CDS cho phép JVM chia sẻ metadata của class đã được lưu trong archive. AppCDS mở rộng khả năng này cho class của ứng dụng và dependency, tùy JDK và cách cấu hình.

CDS/AppCDS có thể giảm một phần chi phí class loading và memory footprint. Nó không lưu trạng thái heap của một tiến trình ứng dụng đã chạy, không giữ application context đã tạo và không thay thế việc kết nối database hoặc nạp cache.

Phù hợp khi:

- Startup có chi phí class loading đáng kể.
- Ứng dụng dùng nhiều class/framework.
- Muốn giữ mô hình JVM bình thường.
- Muốn tối ưu ít thay đổi lifecycle.
- Workload chạy trên JDK hỗ trợ tính năng tương ứng.

Cần kiểm tra archive được tạo và sử dụng đúng JDK/build. Thay đổi classpath, JDK hoặc dependency có thể yêu cầu tạo archive mới.

### 4.3 Ahead-of-Time (AOT) cache và AOT compilation

AOT là nhóm kỹ thuật có nhiều hình thức. Tùy JDK và framework, AOT có thể lưu thông tin đã phân tích hoặc biên dịch trước một phần code để giảm công việc khi chạy.

AOT cache không đồng nghĩa native executable. Một số cơ chế vẫn chạy trong JVM và vẫn cần khởi tạo object, kết nối dependency, nạp config và thực hiện warm-up động.

Phù hợp khi:

- Runtime hoặc framework có AOT support phù hợp.
- Phần startup tốn kém nằm trong phân tích hoặc biên dịch có thể thực hiện trước.
- Muốn giảm startup mà vẫn giữ JVM.
- Đội ngũ chấp nhận build pipeline bổ sung.

Cần đánh giá tính ổn định của cache theo JDK, classpath, application build và môi trường. Không mặc định mọi AOT artifact có thể chia sẻ giữa các build.

### 4.4 GraalVM Native Image

GraalVM Native Image biên dịch ứng dụng Java thành executable native trước khi triển khai. Một số workload có thể đạt startup nhanh và footprint thấp hơn JVM truyền thống.

Đổi lại, quá trình build và runtime có đặc tính khác:

- Cần xử lý reflection, dynamic proxies, resource và class loading.
- Có thể cần metadata hoặc configuration bổ sung cho framework/library.
- Một số thư viện native và dynamic behavior cần điều chỉnh.
- Build có thể lâu và tốn tài nguyên.
- Runtime behavior, memory management và performance profile khác JVM.
- JIT optimization trong quá trình chạy không giống JVM thông thường.

Native Image phù hợp khi startup và memory footprint là yêu cầu rất quan trọng, workload tương thích và đội ngũ có thể duy trì native build pipeline.

Nó không phải giải pháp thay thế trực tiếp cho mọi ứng dụng Java. Hãy thử build một vertical slice có đủ framework, reflection, JDBC, TLS và dependency quan trọng trước khi cam kết chuyển toàn bộ.

### 4.5 Giữ warm pool hoặc minimum replicas

Một lựa chọn vận hành là giữ sẵn một số instance đã chạy và ready. Khi traffic tăng, scheduler gửi request tới instance đã tồn tại thay vì đợi tạo process mới.

Ưu điểm:

- Không cần thay đổi runtime hoặc tạo checkpoint.
- Dễ áp dụng với ứng dụng hiện có.
- Có thể giảm cold start trực tiếp.
- Giữ trạng thái connection và cache đang hoạt động.

Nhược điểm:

- Tốn tài nguyên khi không có traffic.
- Không loại bỏ startup khi warm pool cạn.
- Instance vẫn có thể chết hoặc bị thay thế.
- Cần quản lý capacity và scale-down.
- Có thể giữ connection hoặc credential lâu hơn mong muốn.

Warm pool phù hợp khi startup hiếm hoặc có thể dự báo, và chi phí giữ idle capacity thấp hơn chi phí cold start.

### 4.6 CRaC checkpoint/restore

CRaC phối hợp ứng dụng với checkpoint engine để lưu trạng thái tiến trình đã chạy và khôi phục tiến trình đó sau này.

Ứng dụng có thể được warm-up trước checkpoint. Khi restore, phần lớn class loading, object creation và một số công việc startup đã hoàn tất trong snapshot. Resource callback giúp ứng dụng đóng hoặc phục hồi tài nguyên không thể giữ nguyên qua checkpoint.

CRaC phù hợp khi:

- Tần suất tạo instance cao.
- Startup và warm-up tốn thời gian.
- Heap có nhiều trạng thái ổn định có thể giữ lại.
- Dependency có thể reconnect/reconcile.
- JDK/engine/platform có thể được kiểm soát.
- Đội ngũ có thể duy trì Resource lifecycle và restore testing.

Chi phí gồm:

- Tích hợp callback và quản lý resource.
- Tạo và lưu checkpoint artifact.
- Kiểm thử source-target compatibility.
- Quản lý image version, age và invalidation.
- Bảo mật heap snapshot có thể chứa secret/data.
- Vận hành fallback khi restore lỗi.
- Theo dõi external state và readiness.

CRaC không tự giải quyết state consistency. Nó giúp khôi phục process nhanh; ứng dụng vẫn phải đảm bảo trạng thái bên ngoài hợp lệ.

## 5. So sánh các giải pháp

| Giải pháp | Phần startup chủ yếu giảm | Thay đổi ứng dụng | Chi phí vận hành | Khi phù hợp |
|---|---|---|---|---|
| Tối ưu startup | Initialization không cần thiết, network và framework work | Thấp đến trung bình | Thấp | Gần như mọi ứng dụng |
| CDS/AppCDS | Class loading và metadata | Thấp đến trung bình | Thấp đến trung bình | Class loading là bottleneck |
| AOT cache/compilation | Một phần phân tích/biên dịch trước | Trung bình | Trung bình | Framework/JDK có hỗ trợ phù hợp |
| Native Image | JVM startup và một số runtime initialization | Trung bình đến cao | Cao ở build/debug | Workload tương thích, startup/footprint rất quan trọng |
| Warm pool | Chờ tạo process mới | Thấp | Chi phí idle capacity | Traffic có thể dự báo hoặc cần capacity sẵn |
| CRaC | Nhiều bước khởi tạo process đã được snapshot | Trung bình đến cao | Cao hơn về lifecycle/artifact/compatibility | Startup thường xuyên, warm-up đắt và state phục hồi được |

Bảng là định hướng, không phải benchmark. Kết quả thực tế phụ thuộc framework, JDK, workload, native dependencies, platform và cách đo.

### 5.1 Có thể kết hợp các giải pháp

Một hệ thống không nhất thiết phải chọn duy nhất một kỹ thuật.

Ví dụ:

- Tối ưu startup trước, sau đó dùng CDS để giảm class loading.
- Dùng CRaC cho service có cold start cao và warm pool cho burst cực lớn.
- Dùng Native Image cho một worker nhỏ, giữ JVM cho service có dynamic library phức tạp.
- Dùng warm pool cho control plane và CRaC cho data plane.
- Dùng AOT ở build time rồi checkpoint một process đã warm-up nếu runtime hỗ trợ và đã kiểm chứng tổ hợp.

Tuy nhiên, mỗi lớp tối ưu cần được đo riêng. Kết hợp công nghệ không tự động cộng dồn lợi ích; một bước đã được tối ưu có thể làm lợi ích biên của bước tiếp theo nhỏ đi.

## 6. Đánh giá theo tần suất khởi động

Có thể chia workload thành các nhóm để chọn hướng ban đầu.

| Tần suất tạo process | Ví dụ | Hướng ưu tiên |
|---|---|---|
| Rất thấp | Service chạy dài hạn, deploy vài lần mỗi tuần | Tối ưu startup, CDS/AppCDS |
| Thấp đến trung bình | API autoscale nhẹ, worker chạy lâu | Tối ưu startup, CDS/AOT, warm pool nhỏ |
| Cao theo burst | API scale nhanh khi traffic tăng | Warm pool, CRaC hoặc kết hợp |
| Rất cao | Worker ngắn hạn, job tạo process liên tục | CRaC, Native Image hoặc thiết kế lại thành worker pool |
| Scale-to-zero | Workload gần như không chạy khi idle | CRaC hoặc Native Image; so sánh chi phí giữ warm pool |
| Tạo mới theo tenant | Mỗi tenant cần runtime riêng | CRaC/Native Image nếu state tách biệt và startup đủ đắt |

Tần suất cao chưa đủ để chọn CRaC. Nếu process chỉ mất 100 ms để startup thì lợi ích nhỏ. Nếu process mất 15 giây nhưng warm-up chủ yếu là gọi service bên ngoài chậm, checkpoint có thể giảm phần khởi tạo nội bộ nhưng vẫn phải reconnect dependency sau restore.

### 6.1 Startup ngắn, tần suất cao

Nếu JVM startup vốn đã nhanh và application context nhỏ, Native Image hoặc CRaC có thể tăng độ phức tạp nhiều hơn lợi ích.

Hãy đo trước:

- JVM startup.
- Application context.
- Network initialization.
- Time-to-ready.
- First request.

Có thể một thay đổi đơn giản như bỏ synchronous call tới analytics service trong startup đã giải quyết vấn đề.

### 6.2 Startup dài, tần suất thấp

Nếu startup kéo dài nhưng chỉ xảy ra khi deploy hoặc node replacement, tối ưu startup và CDS thường có tỷ lệ lợi ích/chi phí tốt hơn.

Có thể giảm downtime bằng rolling deployment và giữ đủ capacity cũ trong khi instance mới khởi động. Không nhất thiết phải thay lifecycle của ứng dụng.

### 6.3 Startup dài, tần suất cao

Đây là nhóm đáng đánh giá CRaC hoặc Native Image. Cần so sánh:

- Phần thời gian CRaC có thể snapshot.
- Phần thời gian phải thực hiện lại sau restore.
- Chi phí checkpoint creation và storage.
- Số lần restore mỗi image.
- Chi phí compatibility testing.
- Chi phí giữ warm pool làm phương án khác.

Nếu phần lớn thời gian startup nằm ở dữ liệu có thể snapshot và các resource có thể phục hồi, CRaC có tiềm năng lớn.

## 7. Đánh giá theo trạng thái ứng dụng

### 7.1 State đơn giản, có thể dựng lại

Ứng dụng có application context và cache nội bộ, nhưng dữ liệu nguồn nằm ở database hoặc service bên ngoài. Cache có thể tải lại sau restore.

Đây là ứng viên tốt cho CRaC nếu:

- Cache không chứa dữ liệu nhạy cảm hoặc artifact được bảo vệ phù hợp.
- Cache có revision/TTL.
- Connection có thể tạo lại.
- Instance identity được cấp mới.
- Readiness chờ dependency bắt buộc.

CDS/AppCDS vẫn có thể đủ nếu bottleneck chủ yếu là class loading.

### 7.2 State lớn nhưng bất biến theo release

Ví dụ, một service nạp model, rule set hoặc metadata lớn khi startup. Nếu state không chứa dữ liệu nhạy cảm và được pin theo release, checkpoint có thể tiết kiệm thời gian nạp.

Cần gắn image với digest/version của model và rule set. Nếu model thay đổi, image cũ cần bị invalidated hoặc code phải có cơ chế refresh an toàn.

### 7.3 State thay đổi liên tục

Nếu process giữ state cập nhật liên tục và không có durable source, snapshot có thể trở nên stale rất nhanh.

Ví dụ:

- Session state chỉ nằm trong heap.
- In-memory queue không có durable log.
- Workflow state chưa được commit.
- Counter hoặc sequence được cập nhật local.
- Distributed lock được giữ trong process.

Trước khi dùng CRaC, cần đưa state quan trọng vào durable store, dùng event replay hoặc xác định quy tắc reconciliation. Nếu không, warm pool hoặc startup optimization có thể ít rủi ro hơn.

### 7.4 State gắn với identity hoặc ownership

Các object như pod ID, leader flag, lease token, OAuth refresh token hoặc consumer partition assignment không nên được nhân bản như state dùng chung.

Sau restore, ứng dụng cần:

- Tạo instance identity mới.
- Lấy credential theo workload identity.
- Rejoin broker group.
- Acquire lease mới.
- Dùng fencing token hoặc idempotency key.
- Không tiếp tục side effect dựa trên ownership trong heap.

Nếu ứng dụng không thể thực hiện các bước này an toàn, CRaC integration cost có thể cao.

## 8. Chi phí tích hợp cần được tính đầy đủ

Chi phí không chỉ là số dòng code thêm vào. Cần tính chi phí ban đầu và chi phí vận hành theo vòng đời.

### 8.1 Chi phí code và lifecycle

Với CRaC, cần xác định resource nào phải:

- Dừng trước checkpoint.
- Drain request hoặc transaction.
- Đóng socket, pool và client.
- Pause scheduler và consumer.
- Recreate sau restore.
- Refresh secret/config.
- Validate trước readiness.

Ứng dụng dùng nhiều thư viện bên thứ ba có thể cần kiểm tra từng thư viện. Nếu library giữ native handle hoặc thread nền mà không có lifecycle phù hợp, integration cost tăng.

### 8.2 Chi phí build và platform

Có thể cần:

- CRaC-enabled JDK distribution.
- Checkpoint engine.
- Host kernel/capability phù hợp.
- Container image pin theo digest.
- Runner hoặc node pool riêng.
- Artifact storage cho checkpoint.
- Quyền và security policy riêng.
- Source-target compatibility matrix.

Với Native Image, chi phí tập trung nhiều hơn vào build configuration, reflection/resource metadata, native dependency và debug executable.

Với warm pool, chi phí tập trung vào capacity, scheduling, idle resource và scale policy.

### 8.3 Chi phí kiểm thử

CRaC cần test cả:

- beforeCheckpoint/afterRestore callback.
- Real process checkpoint/restore.
- Source-target matrix.
- External dependency reconciliation.
- Multiple restores từ cùng image.
- Restore sau khi config/secret/schema thay đổi.
- Failure và fallback.
- Performance và resource usage.

Một unit test callback không thay thế real restore test. Tương tự, Native Image cần test executable thực tế trên target platform chứ không chỉ compile thành công.

### 8.4 Chi phí bảo mật

Checkpoint image có thể chứa heap data và secret đã giải mã. Cần:

- Synthetic data trong image build khi có thể.
- Credential giới hạn và TTL ngắn.
- Lấy production secret sau restore.
- Mã hóa artifact.
- ACL và audit access.
- Retention/revocation.
- Không publish checkpoint vào registry công khai.
- Kiểm tra nhiều replica không dùng chung token hoặc identity.

### 8.5 Chi phí vận hành dài hạn

Cần tính:

- Rebuild image theo release/runtime change.
- Restore matrix khi kernel/JDK/engine thay đổi.
- Theo dõi tuổi ảnh và compatibility.
- Quản lý artifact cũ.
- Debug restore failure.
- Duy trì fallback path.
- Hỗ trợ incident khi callback hoặc dependency lỗi.

Một giải pháp giảm 8 giây startup nhưng đòi hỏi nhiều giờ vận hành mỗi tháng có thể không kinh tế nếu chỉ tạo vài instance mỗi ngày.

## 9. Ước lượng break-even và tổng chi phí

Không nên chỉ so sánh startup duration. Hãy đưa lợi ích và chi phí về cùng khoảng thời gian.

Có thể dùng mô hình đơn giản:

~~~text
BenefitPerPeriod =
    NumberOfStarts
    x ValueOfTimeSavedPerStart

CostPerPeriod =
    BuildAndTestCost
    + ArtifactStorageCost
    + RuntimeOverhead
    + OperationsCost
    + IdleCapacityCost
    + FailureRecoveryCost

NetValue =
    BenefitPerPeriod - CostPerPeriod
~~~

ValueOfTimeSavedPerStart có thể gồm:

- Giảm request chờ cold start.
- Giảm số instance cần giữ warm.
- Tăng tốc rollout hoặc recovery.
- Giảm thời gian job hoàn thành.
- Giảm CPU/memory startup overhead.
- Cải thiện trải nghiệm người dùng.

Không quy đổi giây tiết kiệm thành tiền nếu chưa xác định được tác động thực tế.

### 9.1 So sánh CRaC với warm pool

Giả sử:

- Mỗi lần cold start JVM mất 10 giây.
- Warm pool giữ 3 instance idle.
- Một instance idle dùng 0.5 CPU core và 512 MiB RAM.
- Hệ thống tạo trung bình 500 instance mới mỗi ngày.
- CRaC restore time là 2 giây, nhưng phải duy trì builder, matrix tests và artifact storage.

Warm pool có chi phí idle capacity liên tục. CRaC có chi phí tạo image và kiểm thử theo release. Điểm hòa vốn phụ thuộc số lần tạo instance và giá trị của 8 giây giảm được.

### 9.2 So sánh theo vòng đời release

Với mỗi release, có thể ước lượng:

- Thời gian build JAR/container.
- Thời gian warm-up và checkpoint.
- Thời gian restore matrix.
- Storage của checkpoint.
- Số lần restore trong release lifetime.
- Chi phí vận hành và incident.
- Thời gian tiết kiệm trên mỗi instance.

Nếu một image chỉ được restore 5 lần trước khi release tiếp theo thay thế, chi phí checkpoint và kiểm thử có thể không được bù lại. Nếu image được restore hàng chục nghìn lần, chi phí build có thể trở nên nhỏ so với tổng lợi ích.

### 9.3 Đưa rủi ro vào mô hình

Tổng chi phí nên tính cả rủi ro:

- Restore failure làm rollout chậm.
- Image stale làm ứng dụng lỗi sau restore.
- Compatibility drift khiến image không dùng được trên node mới.
- Artifact chứa secret bị lộ.
- Duplicate side effect do nhiều instance restore.
- Fallback startup làm tăng capacity đột ngột.

Không cần quy đổi mọi rủi ro thành một con số chính xác. Có thể dùng mức thấp/trung bình/cao và đặt release gate cho rủi ro không chấp nhận được.

## 10. Ma trận lựa chọn giải pháp

Bảng dưới đây dùng để sàng lọc ban đầu. Hãy đánh giá theo workload thực tế và proof of concept.

| Tiêu chí | Startup optimization | CDS/AppCDS | AOT/Native Image | Warm pool | CRaC |
|---|---|---|---|---|---|
| Startup frequency thấp | Rất phù hợp | Có thể | Có thể | Thường dư thừa | Có thể quá phức tạp |
| Startup frequency cao | Có ích nhưng giới hạn | Có ích | Phù hợp nếu tương thích | Phù hợp nếu idle cost chấp nhận được | Phù hợp nếu state phục hồi được |
| Giữ heap đã warm-up | Không | Không | Không giữ heap JVM | Có, vì process vẫn chạy | Có, từ checkpoint |
| Giữ kết nối hiện tại | Theo startup logic | Theo startup logic | Theo startup logic | Có thể giữ khi process còn sống | Thường cần recreate |
| Yêu cầu Resource callback | Không | Không | Không theo CRaC lifecycle | Không | Có |
| Phụ thuộc host/kernel checkpoint | Không | Không theo process checkpoint | Theo native binary/platform | Không | Có |
| Thay đổi build pipeline | Thấp | Trung bình | Cao | Thấp | Trung bình đến cao |
| Chi phí idle capacity | Không | Không | Không | Có | Thường thấp hơn warm pool, nhưng có artifact/storage |
| State reconciliation | Theo startup | Theo startup | Theo startup | Theo instance lifecycle | Bắt buộc với state động |
| Fallback | JVM startup | JVM startup | JVM startup/JVM build nếu duy trì | Tạo instance mới | Fresh JVM startup |

### 10.1 Chọn theo điểm nghẽn

- Nếu class loading chiếm phần lớn startup: thử CDS/AppCDS.
- Nếu framework có nhiều bước phân tích/khởi tạo có thể thực hiện trước: thử AOT phù hợp.
- Nếu application initialization tuần tự và có thể tối ưu: sửa startup path.
- Nếu cần capacity sẵn và workload có thể dự báo: warm pool.
- Nếu cần cold start nhanh, warm-up đắt và state có thể phục hồi: CRaC.
- Nếu startup và memory footprint là yêu cầu trọng yếu, ứng dụng tương thích native compilation: đánh giá Native Image.

Không chọn công nghệ chỉ theo benchmark của ứng dụng khác. Framework, driver, dependency và trạng thái ứng dụng có thể làm kết quả khác nhau.

## 11. Quy trình ra quyết định

Có thể đi qua các bước sau để thu hẹp lựa chọn.

### Bước 1 — Đặt mục tiêu

Xác định mục tiêu cụ thể:

- Time-to-ready tối đa.
- First-request latency tối đa.
- Số instance mới mỗi phút.
- Mức cold start chấp nhận được.
- Memory footprint mỗi instance.
- Thời gian rollout/recovery.
- Ngân sách idle capacity.

Ví dụ: p95 time-to-ready phải dưới 3 giây khi scale-out 50 instance trong một phút. Mục tiêu cụ thể giúp so sánh các phương án.

### Bước 2 — Đo baseline

Chạy workload trên môi trường gần production và đo các mốc T0–T7. Xác định phần nào thuộc JVM, framework, dependency, cache và warm-up.

Không tối ưu startup trước khi biết phần lớn thời gian nằm ở đâu.

### Bước 3 — Kiểm tra tần suất tạo process

Tính số cold start trong một ngày hoặc release lifetime. Phân biệt restart do deploy, autoscale, crash và job scheduling.

Nếu startup hiếm, một tối ưu nhẹ có thể đủ.

### Bước 4 — Kiểm kê application state

Phân loại cache, config, credential, connection, session, lease, cursor và native resource. Đánh dấu state nào immutable, rebuildable, external-authoritative hoặc instance-specific.

Nếu state không thể reconcile an toàn, cần xử lý state architecture trước khi chọn CRaC.

### Bước 5 — Ước lượng chi phí tích hợp

Với mỗi phương án, ước lượng:

- Code changes.
- Build changes.
- Platform constraints.
- Test coverage.
- Security controls.
- Operational ownership.
- Fallback.
- Chi phí bảo trì theo release.

Không chỉ tính chi phí prototype; tính chi phí duy trì khi JDK, kernel và dependency thay đổi.

### Bước 6 — Chọn hai hoặc ba phương án để thử

Thường nên so sánh baseline tối ưu với một phương án runtime và một phương án vận hành. Ví dụ:

- Startup optimization + CDS.
- CRaC.
- Warm pool.

Nếu Native Image có khả năng tương thích tốt, có thể đưa vào proof of concept riêng.

### Bước 7 — Chạy proof of concept bằng cùng workload

Dùng cùng dữ liệu giả, dependency profile, resource limits và test scenario. Đo time-to-ready, first-request latency, memory, CPU, build time và failure rate.

Với CRaC, test real checkpoint/restore trên target profiles. Với Native Image, test executable trên target platform. Với warm pool, đo cả idle capacity và thời gian cấp instance.

### Bước 8 — Tính TCO và rủi ro

So sánh lợi ích thực tế với build, test, storage, idle capacity và operations. Xác định các rủi ro có thể chặn adoption.

### Bước 9 — Triển khai theo phạm vi nhỏ

Chọn một service hoặc worker có owner rõ ràng, rollout canary và giữ fallback. Đừng thay toàn bộ nền tảng trước khi có bằng chứng.

### Bước 10 — Đánh giá lại sau vận hành

Sau vài tuần hoặc một release cycle, đo cold start thực tế, restore failure, time-to-ready và chi phí. Có thể giải pháp đã chọn không còn phù hợp khi workload thay đổi.

## 12. Ví dụ lựa chọn theo từng loại workload

### 12.1 API chạy dài hạn, ít restart

Một API chạy 20 instance ổn định, mỗi ngày deploy một lần. Startup mất 4 giây, nhưng rolling deployment luôn giữ đủ capacity cũ.

Hướng lựa chọn:

- Profiling startup.
- Tối ưu các synchronous dependency call.
- Thử CDS/AppCDS nếu class loading đáng kể.
- Duy trì rolling deployment và readiness đúng.
- Chưa cần CRaC nếu lợi ích cold start nhỏ.

Lý do: số lần tạo instance không cao và hệ thống đã che phần lớn startup latency bằng deployment strategy.

### 12.2 Worker ngắn hạn, khởi động hàng nghìn lần

Một worker xử lý job độc lập. Mỗi process mất 8 giây tạo framework context và nạp rule set, nhưng job chỉ chạy 20 giây.

Hướng lựa chọn:

- Đầu tiên xem có thể chuyển sang worker pool dài hạn hay không.
- Nếu process isolation là yêu cầu, thử CRaC với rule set đã pin và cache có thể giữ.
- Đánh giá Native Image nếu framework và dependency tương thích.
- So sánh với warm pool và chi phí idle capacity.

Lý do: startup chiếm tỷ lệ lớn trong tổng thời gian job và tần suất tạo process cao.

### 12.3 Service scale-to-zero

Một service có traffic không đều, phần lớn thời gian không có instance. Khi có request, cold start 15 giây.

Hướng lựa chọn:

- Nếu giữ một warm instance có chi phí thấp, warm pool có thể đơn giản nhất.
- Nếu muốn scale-to-zero thực sự, thử CRaC hoặc Native Image.
- Với CRaC, xác định external state nào phải lấy lại sau restore và đo time-to-ready.
- Đặt fallback JVM startup nếu checkpoint không tương thích.

Lý do: mục tiêu là giảm thời gian từ zero capacity tới ready, nhưng idle cost và restore cost phải được so sánh.

### 12.4 Service có cache lớn, ít thay đổi

Một service nạp bộ dữ liệu tham chiếu 2 GB khi startup. Dữ liệu thay đổi theo release hàng tuần.

Hướng lựa chọn:

- Có thể warm-up cache rồi tạo checkpoint theo data revision.
- Gắn image với digest của dataset.
- Invalidate image khi dataset version thay đổi.
- Sau restore, kiểm tra revision trước khi nhận traffic.
- Đánh giá memory footprint và thời gian tải checkpoint.

Lý do: dữ liệu lớn, tương đối ổn định và tốn thời gian nạp có thể là phần state đáng giữ lại.

### 12.5 Stateful stream processor

Một consumer giữ offset, assignment và state trong heap. Broker có thể rebalance khi process bị checkpoint.

Hướng lựa chọn:

- Ưu tiên durable state, replay và consumer group coordination.
- Dùng idempotent processing và commit semantics đúng.
- Nếu dùng CRaC, dừng consumer trước checkpoint và rejoin group sau restore.
- Không tiếp tục assignment cũ hoặc dùng offset chỉ lưu trong heap.
- Kiểm thử duplicate processing và failover.

Lý do: state có ownership và ordering semantics; startup speed không được làm giảm correctness.

### 12.6 Ứng dụng native dependency phức tạp

Ứng dụng dùng JNI, native thread, driver đặc thù và file mapping. Startup chậm nhưng native state khó phục hồi.

Hướng lựa chọn:

- Đo xem bottleneck có nằm ở Java class loading không.
- Thử CDS/AOT hoặc tối ưu startup trước.
- Đánh giá Native Image nếu native dependency hỗ trợ.
- Chỉ chọn CRaC sau khi có proof of concept với engine/platform thật và callback lifecycle rõ ràng.

Lý do: integration cost và compatibility risk có thể cao hơn lợi ích.

## 13. Proof of concept cần đo gì?

Một PoC hữu ích phải so sánh các phương án trên cùng workload.

| Nhóm | Số đo |
|---|---|
| Startup | p50/p95/p99 time-to-ready |
| Request | First-request latency và latency sau warm-up |
| Scale | Instance creation rate và cold start percentage |
| CPU | CPU time trong startup và warm-up |
| Memory | RSS/PSS, heap và native memory |
| Build | Build time và artifact size |
| CRaC | Checkpoint time, restore time, artifact size, callback time |
| Native Image | Native build time, executable size, runtime footprint |
| Warm pool | Idle CPU/RAM và pool miss rate |
| Reliability | Restore/startup failure rate, readiness failure |
| Integration | Số resource cần callback hoặc custom configuration |
| Operations | Thời gian xử lý incident, retest và release maintenance |

### 13.1 Giữ workload giống nhau

Để so sánh công bằng:

- Cùng application version.
- Cùng dependency version.
- Cùng dataset hoặc synthetic fixture.
- Cùng CPU/memory limit.
- Cùng target node class.
- Cùng số request warm-up.
- Cùng readiness criteria.
- Cùng external dependency latency.
- Cùng số lần lặp.

Nếu một phương án được chạy trên node nhanh hơn hoặc database gần hơn, kết quả không còn so sánh trực tiếp.

### 13.2 Đo cả failure path

Với CRaC, thử restore lỗi do dependency chưa sẵn sàng, config mismatch hoặc target profile không hợp lệ. Với Native Image, thử startup khi resource hoặc native dependency thiếu. Với warm pool, thử khi pool cạn.

Giải pháp tốt phải có fallback và failure behavior rõ ràng, không chỉ có kết quả benchmark đẹp trong điều kiện lý tưởng.

## 14. Các dấu hiệu CRaC là lựa chọn phù hợp

CRaC đáng được đưa vào shortlist khi nhiều điều kiện sau cùng đúng:

- Có nhiều lần tạo process mới.
- Startup và warm-up chiếm phần đáng kể trong time-to-ready.
- Nhiều chi phí khởi tạo có thể snapshot và reuse.
- Application state có thể phân loại và reconcile.
- Resource lifecycle có thể quản lý qua callback.
- JDK/engine/host platform có thể pin và kiểm thử.
- Có khả năng bảo vệ checkpoint artifact.
- Đội ngũ có năng lực vận hành compatibility matrix và rebuild policy.
- Lợi ích đo được vượt chi phí build/test/operations.

CRaC ít phù hợp hơn khi:

- Startup vốn đã nhanh.
- Process hầu như không restart.
- Phần lớn startup time nằm ở dependency bên ngoài mà vẫn phải chạy lại sau restore.
- Ứng dụng giữ state không durable và không thể reconcile.
- Native resource không thể phục hồi an toàn.
- Môi trường restore thay đổi liên tục và không thể kiểm soát.
- Không thể bảo vệ checkpoint artifact.
- Chi phí tích hợp lớn hơn lợi ích cold start.

Đây là tiêu chí sàng lọc, không phải danh sách cấm. Một PoC trên đúng workload mới có thể xác nhận chi phí và lợi ích.

## 15. Những sai lầm thường gặp khi chọn giải pháp

### Chọn công nghệ theo benchmark của ứng dụng khác

Startup time phụ thuộc framework, dependency, data và host. Benchmark ngoài chỉ giúp tạo giả thuyết. Hãy đo ứng dụng của mình.

### Nhầm request frequency với startup frequency

Một API có nhiều request nhưng ít instance mới có thể không cần giải pháp cold start. Đếm số process creation thực tế.

### Chỉ đo JVM startup

Time-to-ready còn gồm framework, network, cache và readiness. Đo toàn bộ đường đi.

### Chọn CRaC vì restore nhanh mà bỏ qua state

Restore process nhanh nhưng connection, secret, lease và broker assignment vẫn cần phục hồi. Tính time-to-ready sau reconcile.

### Chọn Native Image mà chưa kiểm tra dependency

Reflection, dynamic class loading và native library có thể làm migration phức tạp. Làm PoC với dependency thực tế.

### Dùng warm pool mà không tính idle cost

Instance luôn ready tiêu thụ tài nguyên khi không có traffic. Đo pool miss rate và idle CPU/RAM.

### Lazy initialization làm chậm request đầu tiên

Chuyển công việc khỏi startup có thể làm first-request latency tăng. Đo cả startup và request path.

### Bỏ qua fallback

Checkpoint restore hoặc native executable có thể thất bại trên target mới. Giữ đường khởi động an toàn và kiểm thử nó.

### Không tính chi phí duy trì

Mỗi JDK, kernel, dependency hoặc release mới có thể kích hoạt retest/rebuild. Tính chi phí theo vòng đời, không chỉ PoC.

## 16. Checklist lựa chọn

Trước khi quyết định, hãy trả lời các câu hỏi sau:

### Tần suất khởi động

- Số instance mới mỗi giờ/ngày là bao nhiêu?
- Cold start xảy ra do autoscaling, deployment, crash hay job scheduling?
- Startup chiếm bao nhiêu phần trăm thời gian job?
- p95/p99 time-to-ready có vi phạm SLO không?
- Warm pool có thể đáp ứng với chi phí chấp nhận được không?

### Trạng thái ứng dụng

- State nào nằm trong heap?
- State nào có thể rebuild?
- State nào có nguồn authoritative bên ngoài?
- Credential và identity có được lấy mới sau restore không?
- Connection, thread, scheduler và native resource có thể phục hồi không?
- Restore nhiều instance có gây duplicate side effect không?
- Cache có version/TTL và invalidation policy không?

### Chi phí tích hợp

- JDK/engine/host platform có thể pin không?
- Có cần self-hosted runner hoặc node pool riêng không?
- Bao nhiêu resource cần callback?
- Có thể chạy real restore test trong CI không?
- Artifact storage và access control đã có chưa?
- Đội ngũ có thể duy trì compatibility matrix và age policy không?
- Fallback path có được kiểm thử không?

### Kết quả kinh doanh và vận hành

- Mục tiêu time-to-ready cụ thể là gì?
- Bao nhiêu giây cold start thực sự được tiết kiệm?
- Lợi ích có chuyển thành latency, throughput hoặc cost không?
- Chi phí build, storage, idle capacity và operations là bao nhiêu?
- Rủi ro còn lại có nằm trong mức chấp nhận được không?

## 17. Quy trình lựa chọn và triển khai

Một quy trình có thể áp dụng cho một service Java:

**Bước 1 — Đo baseline.** Thu thập startup phases, time-to-ready, first-request latency và process creation frequency trên môi trường gần production.

**Bước 2 — Xác định bottleneck.** Tách class loading, framework initialization, dependency connection, data loading và warm-up.

**Bước 3 — Phân loại application state.** Ghi rõ cache, config, credential, connection, session, lease, cursor và native resource.

**Bước 4 — Tạo shortlist.** Chọn startup optimization, CDS/AOT, Native Image, warm pool hoặc CRaC dựa trên bottleneck và state.

**Bước 5 — Ước lượng integration cost.** Tính code, build, platform, testing, security và operations theo release lifecycle.

**Bước 6 — Chạy PoC công bằng.** Dùng cùng workload, dependency, data, resource limit và target profile; đo cả startup lẫn time-to-ready.

**Bước 7 — Kiểm thử failure và fallback.** Thử dependency outage, target mismatch, credential refresh và restore/startup failure.

**Bước 8 — So sánh TCO.** Đưa startup savings, idle capacity, build/test, artifact storage và operational effort vào cùng khoảng thời gian.

**Bước 9 — Rollout canary.** Triển khai một workload nhỏ, theo dõi latency, failure rate và resource usage.

**Bước 10 — Mở rộng hoặc điều chỉnh.** Chỉ mở rộng khi lợi ích thực tế vượt chi phí và đội ngũ có thể duy trì lifecycle.

## 18. Kết luận lựa chọn

Tần suất khởi động cho biết lợi ích cold start có thể xuất hiện bao nhiêu lần. Trạng thái ứng dụng cho biết phần nào có thể giữ lại an toàn và phần nào phải phục hồi. Chi phí tích hợp cho biết đội ngũ có thể duy trì giải pháp trong suốt vòng đời ứng dụng hay không.

Với startup hiếm, hãy ưu tiên tối ưu startup path và các cơ chế ít thay đổi lifecycle như CDS/AppCDS. Với startup thường xuyên nhưng ứng dụng có thể chạy trong warm pool, hãy so sánh chi phí giữ idle capacity với các phương án khác. Với workload scale-to-zero hoặc tạo process liên tục, CRaC và Native Image đáng được thử nghiệm nếu trạng thái và dependency phù hợp. Với ứng dụng stateful hoặc native-heavy, hãy đánh giá chi phí phục hồi và tính nhất quán trước khi tập trung vào tốc độ.

Quyết định tốt dựa trên time-to-ready, startup frequency, state recovery, compatibility và tổng chi phí vận hành đo được. Hãy dùng PoC trên đúng workload và giữ fallback rõ ràng trước khi áp dụng rộng.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và phối hợp với ứng dụng.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): chuẩn bị runtime và chạy ứng dụng CRaC.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource callback trước checkpoint và sau restore.
- [OpenJDK — Class Data Sharing](https://openjdk.org/jeps/310): Application Class-Data Sharing.
- [Java Launcher — Class Data Sharing](https://docs.oracle.com/en/java/javase/21/vm/class-data-sharing.html): cấu hình CDS và AppCDS trong JVM.
- [GraalVM — Native Image](https://www.graalvm.org/latest/reference-manual/native-image/): biên dịch ứng dụng Java thành native executable.
- [GraalVM — Native Image Build Configuration](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildConfiguration/): cấu hình build và metadata cho Native Image.
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): AOT processing trong Spring Boot.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): scale workload theo nhu cầu.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): vòng đời pod và trạng thái sẵn sàng.

