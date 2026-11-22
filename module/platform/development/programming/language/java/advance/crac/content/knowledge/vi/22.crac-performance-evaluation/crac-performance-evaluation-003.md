# Đo thời gian checkpoint và chi phí tạo ảnh

Checkpoint giúp rút ngắn thời gian đưa một ứng dụng Java vào trạng thái sẵn sàng, nhưng việc tạo ảnh cũng tiêu tốn tài nguyên. Runtime phải phối hợp các resource, chụp trạng thái tiến trình và ghi dữ liệu ra storage. Pipeline triển khai có thể còn phải nén, mã hóa, upload, xác minh và publish artifact. Nếu chỉ đo thời gian gọi lệnh checkpoint hoặc chỉ nhìn kích thước thư mục, ta sẽ bỏ sót một phần đáng kể của chi phí.

Đánh giá hiệu năng CRaC (Coordinated Restore at Checkpoint) cần phân biệt ít nhất ba đại lượng: thời gian ứng dụng chuẩn bị dừng công việc, thời gian runtime tạo checkpoint image và thời gian từ lúc bắt đầu checkpoint đến khi artifact có thể được restore ở môi trường đích. Ngoài ra, cần đo khoảng thời gian ứng dụng không nhận traffic, chi phí CPU/memory/I/O, kích thước ảnh và thời gian restore. Các số liệu này trả lời những câu hỏi vận hành khác nhau.

Một benchmark hữu ích phải dùng workload và resource limit đại diện, ghi nhận môi trường nguồn/đích, chạy nhiều lần và kiểm tra restore thực tế. Checkpoint tạo thành công nhưng restore thất bại, hoặc tạo ảnh nhanh nhưng tiêu tốn quá nhiều I/O và làm tăng latency của ứng dụng, vẫn là kết quả không đạt yêu cầu.

## 1. Các thành phần của chi phí checkpoint

Có thể phân rã quy trình thành các giai đoạn sau:

1. **Quiesce ứng dụng:** Ngừng nhận công việc mới, drain request/job đang chạy và đưa resource về trạng thái an toàn.
2. **Callback trước checkpoint:** Các Resource thực hiện beforeCheckpoint(), đóng hoặc chuẩn bị socket, file, pool, executor và dependency theo lifecycle.
3. **Snapshot tiến trình:** Runtime và cơ chế checkpoint của nền tảng thu thập trạng thái cần thiết của process.
4. **Ghi image:** Các trang bộ nhớ và metadata được ghi vào checkpoint directory hoặc storage do runtime chỉ định.
5. **Hoàn tất artifact:** Flush dữ liệu, ghi metadata cuối, xác minh file và hoàn tất thao tác lưu.
6. **Post-processing:** Nén, mã hóa, tạo manifest, checksum/chữ ký hoặc chuyển đổi package nếu pipeline yêu cầu.
7. **Phân phối:** Upload, replicate hoặc copy artifact đến nơi restore.
8. **Publish:** Đánh dấu artifact đã hoàn chỉnh và sẵn sàng được sử dụng.

~~~text
Checkpoint request
       |
       v
Quiesce + beforeCheckpoint callbacks
       |
       v
Runtime snapshot / dump
       |
       v
Write checkpoint files + metadata
       |
       v
Flush / finalize image
       |
       v
Compress / encrypt / sign (nếu có)
       |
       v
Upload / replicate
       |
       v
Verify + publish artifact
       |
       v
Artifact ready for restore
~~~

Không phải mọi nền tảng đều có các ranh giới hoặc callback giống hệt sơ đồ. Một số giai đoạn có thể chạy song song, được tích hợp trong runtime hoặc do hệ thống triển khai thực hiện. Vì vậy, hãy ghi nhận thời gian end-to-end độc lập với các phase metric; không cộng máy móc các phase nếu chúng chồng lấp.

## 2. Phân biệt các loại thời gian

Một con số “checkpoint duration” thường không đủ để đánh giá hệ thống. Cần định nghĩa rõ điểm bắt đầu và kết thúc của mỗi metric.

| Metric | Bắt đầu | Kết thúc | Ý nghĩa |
|---|---|---|---|
| Quiesce duration | Bắt đầu ngừng nhận công việc | Ingress/worker đã dừng và công việc đang chạy đã drain | Chi phí đưa ứng dụng về trạng thái an toàn |
| beforeCheckpoint duration | Bắt đầu callback chuẩn bị | Tất cả Resource callback hoàn tất | Chi phí chuẩn bị tài nguyên |
| Snapshot duration | Runtime bắt đầu tạo ảnh | Runtime hoàn tất phần snapshot theo định nghĩa của nền tảng | Chi phí chụp trạng thái tiến trình |
| Image write duration | Bắt đầu ghi checkpoint data | File data/metadata được ghi xong | Chi phí storage I/O |
| Finalization duration | Bắt đầu finalize | Artifact local nhất quán và hoàn chỉnh | Chi phí flush, metadata, kiểm tra |
| Packaging duration | Bắt đầu nén/đóng gói | Package hoàn tất | Chi phí CPU và I/O bổ sung |
| Encryption duration | Bắt đầu mã hóa | Ciphertext và manifest hoàn tất | Chi phí mật mã |
| Transfer duration | Bắt đầu upload/copy | Artifact đến storage đích | Chi phí network |
| Artifact-ready duration | Checkpoint request bắt đầu | Artifact được xác minh và publish | Thời gian chờ end-to-end |
| Application pause | Ngừng nhận traffic | Instance được phép nhận traffic trở lại | Ảnh hưởng trực tiếp đến availability |
| Restore-to-ready duration | Restore bắt đầu | Instance đạt readiness | Chi phí đưa instance mới vào phục vụ |

Cần phân biệt thời gian tạo ảnh với thời gian instance bị pause. Trong một kiến trúc, ứng dụng có thể tiếp tục chạy sau khi checkpoint local hoàn tất trong khi pipeline upload vẫn đang diễn ra. Ở kiến trúc khác, instance có thể phải chờ publish artifact hoặc restore verification. Định nghĩa application pause theo hành vi thực tế của hệ thống, không suy ra từ thời gian tạo artifact.

Tương tự, thời gian restore không phải là thời gian checkpoint. Hai metric cần được đo riêng, dù đều ảnh hưởng đến thời gian rollout hoặc scale-out.

## 3. Xác định mục tiêu đo trước khi benchmark

Trước khi chạy thử, hãy xác định quyết định mà số liệu sẽ hỗ trợ. Một số mục tiêu thường gặp:

- So sánh startup thông thường với restore từ checkpoint.
- Xác định checkpoint có đủ nhanh để dùng trong autoscaling hay không.
- Ước lượng dung lượng storage và network cần cho artifact.
- Đo ảnh hưởng của heap occupancy đến thời gian dump.
- Đánh giá chi phí nén hoặc mã hóa.
- Xác định CPU quota và storage throughput tối thiểu.
- Kiểm tra checkpoint có làm gián đoạn request đang phục vụ không.
- Tính thời gian từ lúc tạo image đến khi image có thể được sử dụng ở region khác.

Chuyển mục tiêu thành tiêu chí định lượng. Ví dụ:

| Mục tiêu | Metric chính | Metric bổ sung |
|---|---|---|
| Scale-out nhanh | Restore-to-ready p50/p95 | Artifact transfer, readiness failures |
| Giảm gián đoạn | Application pause p95 | Request error rate, drain duration |
| Giảm chi phí lưu trữ | Artifact bytes | Compression ratio, retention |
| Giảm CPU overhead | CPU-seconds/checkpoint | CPU throttling, application latency |
| Tăng tốc publish | Artifact-ready duration | Write throughput, encryption/upload time |
| Đảm bảo độ tin cậy | Restore success rate | Integrity failures, retry count |

Không đặt mục tiêu chỉ là “checkpoint càng nhanh càng tốt”. Một checkpoint nhanh nhưng tiêu thụ lượng CPU lớn, tạo ảnh quá lớn hoặc làm request latency tăng mạnh có thể khiến tổng chi phí hệ thống cao hơn.

## 4. Đo thời gian bằng đồng hồ phù hợp

Đối với khoảng thời gian nằm trong cùng một process đang chạy, dùng đồng hồ monotonic như System.nanoTime() để đo elapsed time. Không dùng System.currentTimeMillis() để tính duration vì wall clock có thể được điều chỉnh.

Ví dụ:

~~~java
long started = System.nanoTime();

prepareResources();

long elapsedNanos = System.nanoTime() - started;
long elapsedMillis = elapsedNanos / 1_000_000;

logger.info("resource preparation took {} ms", elapsedMillis);
~~~

Đoạn này phù hợp để đo một phase đồng bộ trong cùng lần thực thi. Với các phase chạy qua checkpoint/restore, process có thể bị dừng hoặc khôi phục ở thời điểm khác. Không giả định rằng một giá trị nanoTime được lưu trong heap có thể so sánh an toàn qua mọi ranh giới process, host hoặc runtime. Hãy dùng timestamp từ orchestrator/host hoặc telemetry có đồng bộ clock để đo end-to-end.

Nếu start và end nằm trên cùng host, một controller bên ngoài có thể dùng monotonic clock của host. Nếu hai mốc nằm trên hai host khác nhau, wall-clock timestamp cần được đồng bộ và sai số clock phải được tính đến. Distributed tracing có thể giúp liên kết phase nhưng vẫn cần hiểu clock skew.

Các quy tắc thực hành:

- Dùng monotonic clock cho duration nội bộ cùng process.
- Dùng orchestrator hoặc controller để đo checkpoint request đến artifact-ready.
- Ghi timestamp wall-clock cho audit và correlation, không dùng nó một cách ngây thơ làm duration.
- Gắn cùng một checkpoint ID vào callback log, runtime log, storage operation và restore event.
- Ghi rõ đơn vị và ranh giới của metric.

## 5. Đo thời gian callback trước checkpoint

Resource callback là nơi ứng dụng thường dừng worker, drain request, flush dữ liệu và đóng tài nguyên. Có thể đo riêng thời gian của từng resource để biết bước nào chiếm phần lớn thời gian chuẩn bị.

Ví dụ một Resource có metric:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class TimedResource implements Resource {
    private final Lifecycle lifecycle;
    private final DurationRecorder recorder;

    public TimedResource(
            Lifecycle lifecycle,
            DurationRecorder recorder) {
        this.lifecycle = lifecycle;
        this.recorder = recorder;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        long started = System.nanoTime();
        try {
            lifecycle.stopAcceptingWork();
            lifecycle.awaitInFlightWork();
            lifecycle.closeCheckpointSensitiveResources();
        } finally {
            recorder.record(
                    "crac.resource.beforeCheckpoint",
                    System.nanoTime() - started);
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        long started = System.nanoTime();
        try {
            lifecycle.reopenResources();
            lifecycle.verifyReady();
        } finally {
            recorder.record(
                    "crac.resource.afterRestore",
                    System.nanoTime() - started);
        }
    }

    public interface Lifecycle {
        void stopAcceptingWork() throws Exception;
        void awaitInFlightWork() throws Exception;
        void closeCheckpointSensitiveResources() throws Exception;
        void reopenResources() throws Exception;
        void verifyReady() throws Exception;
    }

    public interface DurationRecorder {
        void record(String name, long elapsedNanos);
    }
}
~~~

Đây là ví dụ kiến trúc; Lifecycle và DurationRecorder do ứng dụng định nghĩa. Nếu callback ném exception, finally vẫn ghi nhận thời gian phase. Tuy nhiên, recorder phải đủ an toàn để không gây thêm lỗi trong callback. Một số hệ thống có thể ghi metric vào bộ đệm local hoặc log thay vì gọi một telemetry service đang không sẵn sàng.

Đo từng resource giúp tìm ra thành phần chậm, ví dụ:

- Drain request chờ một request dài.
- Consumer commit offset hoặc đóng session.
- Connection pool chờ request đang sử dụng.
- Scheduler chờ job kết thúc.
- File writer flush dữ liệu.
- Client cloud chờ background refresh dừng.

Không gộp tất cả thành một metric nếu cần tối ưu từng thành phần. Đồng thời, tránh tạo quá nhiều log đồng bộ trong callback vì chính việc logging có thể kéo dài thời gian checkpoint.

## 6. Đo thời gian snapshot và ghi image từ bên ngoài

Các callback ứng dụng chỉ đo phần ứng dụng chuẩn bị tài nguyên. Chúng không đo toàn bộ công việc snapshot hoặc thời gian runtime ghi image. Để đo các phase này, dùng công cụ điều khiển checkpoint hoặc runtime log được nhà cung cấp hỗ trợ.

Controller bên ngoài có thể ghi:

- Thời điểm gửi yêu cầu checkpoint.
- Thời điểm runtime bắt đầu xử lý nếu có event/log tương ứng.
- Thời điểm lệnh hoặc API trả kết quả.
- Thời điểm toàn bộ file checkpoint xuất hiện và ổn định.
- Thời điểm artifact được xác minh và publish.

Ví dụ logic đo trong controller:

~~~text
checkpoint_id = unique_id()

t_request = monotonic_now()
invoke_supported_checkpoint_operation()

wait_until_checkpoint_operation_completes()
t_runtime_done = monotonic_now()

wait_until_all_artifact_files_are_complete()
verify_artifact()
t_artifact_ready = monotonic_now()

snapshot_and_write_ms = t_runtime_done - t_request
artifact_finalize_ms = t_artifact_ready - t_runtime_done
artifact_ready_ms = t_artifact_ready - t_request
~~~

Đây là pseudocode, không phải một lệnh CRaC chuẩn. Cách gọi checkpoint phụ thuộc JDK distribution và nền tảng. Nếu runtime không cung cấp mốc riêng cho snapshot và write, chỉ báo cáo thời gian tổng mà controller thực sự đo được; không suy đoán thời gian nội bộ từ log không có timestamp phù hợp.

Đừng coi lệnh checkpoint trả về là artifact-ready nếu runtime hoặc pipeline còn ghi metadata, flush file, nén, mã hóa hoặc upload. Xác định rõ điều kiện hoàn tất trước khi dừng timer.

## 7. Đo kích thước checkpoint image

Kích thước checkpoint không nhất thiết bằng Java heap size. Image có thể chứa nhiều loại trạng thái khác nhau, tùy runtime và cấu hình:

- Memory pages được checkpoint.
- Native memory và các mapping được hỗ trợ.
- Metadata của process và runtime.
- Thông tin resource hoặc file descriptor cần thiết.
- File phụ trợ do checkpoint engine tạo.
- Các vùng dữ liệu được giữ lại dù không thuộc Java heap.

Vì vậy, cần ghi riêng:

1. Heap used và committed tại thời điểm checkpoint.
2. Process RSS/PSS nếu nền tảng cung cấp.
3. Tổng logical size của checkpoint files.
4. Disk space thực sự được cấp phát.
5. Kích thước sau nén.
6. Kích thước sau mã hóa/package.
7. Kích thước cuối cùng trên storage và số byte truyền qua mạng.

Trên Linux, với thư mục checkpoint, có thể dùng:

~~~bash
du -sh ./checkpoint
du -sb ./checkpoint
find ./checkpoint -type f -printf '%s %p\n'
~~~

du -sh thường hiển thị dung lượng disk được sử dụng theo block; du -sb trên GNU coreutils báo apparent size theo byte. Hai con số có thể khác nhau do sparse file, block allocation và filesystem behavior. Cú pháp find -printf là phần mở rộng GNU, không có trên mọi hệ điều hành. Chọn công cụ tương ứng với môi trường triển khai.

Không chỉ ghi kích thước của file lớn nhất. Một checkpoint có thể có nhiều file nhỏ; file count và metadata overhead cũng ảnh hưởng thời gian tạo, upload và restore.

## 8. Vì sao heap size không dự đoán chính xác image size?

Java heap là một phần của process memory. Heap used cho biết lượng đối tượng đang được sử dụng theo góc nhìn GC; nó không bao quát mọi vùng nhớ mà checkpoint engine có thể cần lưu.

Một số yếu tố làm image size khác heap used:

- Metaspace, code cache và các cấu trúc native của JVM.
- Thread stack và trạng thái thread.
- Direct buffers và native libraries.
- Memory-mapped files.
- Các vùng nhớ shared hoặc private.
- Trang bộ nhớ rỗng hoặc có thể nén.
- Sparse file và cách filesystem cấp phát block.
- Cơ chế deduplication hoặc compression của checkpoint engine.
- File và metadata ngoài heap mà runtime cần bảo tồn.

Một heap committed lớn nhưng phần lớn trang không chứa dữ liệu hữu ích có thể tạo image khác với heap có mức occupancy tương tự nhưng phân bố trang khác. Ngược lại, native memory hoặc mapping lớn có thể làm image lớn dù heap used nhỏ.

Hãy xem heap metrics là một biến giải thích, không phải công thức tính image size.

## 9. Ảnh hưởng của live set và heap occupancy

Live set là lượng dữ liệu cần giữ sau khi GC thu gom các đối tượng không còn được tham chiếu. Heap occupancy tại thời điểm checkpoint có thể ảnh hưởng đến số trang chứa dữ liệu hữu ích và khả năng nén, nhưng quan hệ không luôn tuyến tính.

Khi benchmark, ghi nhận:

- Heap used.
- Heap committed và maximum.
- GC collector và cấu hình.
- Thời điểm GC gần nhất.
- Số lượng object hoặc cấu trúc cache lớn nếu có thể đo.
- Native memory và direct buffer.
- Process RSS/PSS.
- Image size và thời gian ghi.

Không tự động gọi System.gc() trước checkpoint chỉ để làm image nhỏ hơn. Full GC có thể tiêu tốn CPU, tạo pause, làm thay đổi trạng thái heap và khiến benchmark không đại diện production. Nếu muốn đánh giá chính sách explicit GC, hãy chạy nó như một biến thể riêng và tính cả thời gian/CPU GC vào chi phí.

Một workload có cache lớn được giữ sống có thể tạo image lớn hơn dù request rate thấp. Do đó, benchmark cần warm-up và cache state ổn định, tương tự môi trường thật.

## 10. Compression và compression ratio

Nén checkpoint có thể giảm dung lượng storage và network transfer, nhưng tiêu tốn CPU, memory và thời gian. Tùy runtime, image có thể đã được nén một phần hoặc có định dạng tối ưu riêng. Không nên nén thêm nếu chưa đo lợi ích.

Ghi lại ba kích thước:

- S_raw: kích thước checkpoint trước compression.
- S_compressed: kích thước sau compression.
- S_final: kích thước package cuối cùng sau mã hóa/đóng gói.

Compression ratio có thể tính:

\[
R_c = \frac{S_{compressed}}{S_{raw}}
\]

Ví dụ S_raw = 4 GiB và S_compressed = 1,6 GiB thì R_c = 0,4, tương đương giảm khoảng 60% dung lượng so với đầu vào.

Cũng nên đo:

\[
Saving = 1 - R_c
\]

Không chỉ so sánh tỷ lệ nén. Nếu nén làm CPU time tăng mạnh nhưng chỉ giảm một ít dung lượng, có thể không đáng giá. Nếu network là bottleneck hoặc storage đắt, nén có thể mang lại lợi ích lớn.

Nén trước mã hóa thường hiệu quả hơn vì ciphertext có entropy cao và khó nén. Tuy nhiên, phải bảo đảm định dạng package và thứ tự xử lý tương thích với restore pipeline.

## 11. Chi phí mã hóa và xác minh integrity

Nếu checkpoint được mã hóa client-side, pipeline cần đo riêng:

- Thời gian tạo hoặc lấy DEK.
- Thời gian KMS wrap key.
- CPU time cho AEAD encryption.
- Thời gian tạo manifest và chữ ký.
- Thời gian verify checksum/signature.
- Thời gian KMS unwrap khi restore.
- CPU time cho decryption và authentication.
- Memory dùng cho buffer/chunk.

Với checkpoint lớn, không nên nạp toàn bộ image vào heap để mã hóa. Streaming hoặc chunk encryption giúp giới hạn memory, nhưng tạo thêm overhead cho metadata, nonce, tag và file handling.

Nếu encryption được thực hiện song song, wall-clock duration có thể ngắn hơn tổng CPU time của các worker. Hãy ghi cả elapsed time và CPU-seconds để phân biệt throughput với lượng CPU thực sự tiêu thụ.

Đừng bỏ qua chi phí xác minh. Một artifact chỉ được xem là sẵn sàng khi đã kiểm tra tính toàn vẹn theo policy, không phải ngay khi upload hoàn tất.

## 12. Chi phí storage I/O và fsync

Tạo image có thể ghi một lượng dữ liệu lớn trong thời gian ngắn. Storage throughput, latency, filesystem và page cache ảnh hưởng trực tiếp đến thời gian hoàn tất.

Các yếu tố cần ghi nhận:

- Tổng byte được ghi.
- Throughput ghi trung bình và peak.
- Số lượng file và thao tác create/rename.
- fsync hoặc flush latency nếu có log.
- Disk queue depth và I/O wait.
- Loại storage: local SSD, network filesystem, block volume hoặc ephemeral disk.
- Filesystem và mount options.
- Storage quota hoặc throttling.
- Tình trạng disk gần đầy.

Nếu checkpoint directory nằm trên network filesystem, latency metadata hoặc network throughput có thể là bottleneck. Nếu dùng local ephemeral storage, upload đến object storage sẽ là một phase riêng. Đừng gộp hai loại storage vào cùng một phép đo nếu muốn tìm nguyên nhân.

Có thể dùng iostat, pidstat, process I/O counters hoặc metric của volume/cloud storage. Tên metric và quyền truy cập phụ thuộc hệ điều hành và runtime.

## 13. Đo CPU và memory overhead trong lúc tạo ảnh

Checkpoint có thể tạo peak resource usage. Ví dụ, runtime ghi page data trong khi ứng dụng vừa drain request; compression/encryption có thể tạo thêm buffer và worker thread.

Nên ghi:

- CPU user/system time của process và checkpoint helper.
- CPU throttling của cgroup.
- RSS/PSS và peak memory.
- Cgroup memory.current và memory.events.
- Số thread và PIDs usage.
- I/O bytes và I/O wait.
- GC pause và allocation rate.
- Application request latency/error rate trong giai đoạn chuẩn bị.

Trong Linux, có thể dùng /usr/bin/time -v cho một command độc lập như compression hoặc encryption stage để xem elapsed time, CPU time và maximum resident set size. Với process Java đang chạy lâu dài, cần công cụ giám sát process/cgroup hoặc controller riêng; bọc lệnh checkpoint không có nghĩa /usr/bin/time tự đo toàn bộ tài nguyên của target process.

Nếu container bị CPU quota, CPU time thực tế và wall-clock duration có thể chênh lệch lớn. Một bước dùng 10 CPU-seconds có thể mất nhiều giây hơn khi bị throttle. Luôn ghi quota và throttling statistics cùng kết quả benchmark.

## 14. Đo application pause và ảnh hưởng đến request

Đối với service trực tuyến, metric quan trọng có thể là thời gian ứng dụng không nhận request hoặc thời gian request bị ảnh hưởng, chứ không phải thời gian artifact được publish.

Một cách đo:

1. Ghi thời điểm ingress bắt đầu trả trạng thái không nhận công việc mới.
2. Đo số request đang chạy và thời gian drain.
3. Ghi thời điểm các request đang chạy hoàn tất.
4. Ghi thời điểm checkpoint runtime bắt đầu và hoàn tất.
5. Ghi thời điểm ingress được mở lại hoặc instance mới báo ready.
6. Đối chiếu với request latency, error rate và load balancer events.

Nếu hệ thống tạo checkpoint từ một instance riêng, instance phục vụ traffic có thể không bị pause trong toàn bộ thời gian publish. Nếu checkpoint trực tiếp instance đang phục vụ, khoảng downtime có thể khác. Hãy đo kiến trúc thực tế.

Có thể dùng synthetic request liên tục để phát hiện khoảng gián đoạn, nhưng cần tránh để chính probe tạo tải đáng kể hoặc làm sai kết quả. Ghi cả p50/p95/p99 latency và số lỗi, timeout trong cửa sổ checkpoint.

## 15. Benchmark có đối chứng

Để biết CRaC mang lại lợi ích gì, cần so sánh với baseline phù hợp:

- Cold start: khởi chạy JVM mới và chờ readiness.
- Warm restart: khởi động lại từ cùng image/container nhưng không restore checkpoint.
- CRaC restore: restore từ checkpoint artifact.
- Nếu cần, thêm checkpoint + transfer + restore đầy đủ để phản ánh quy trình production.

Đo cùng định nghĩa readiness, cùng workload, cùng dependency và cùng resource limits. Nếu cold start chạy trên máy lớn nhưng restore chạy trong container nhỏ, kết quả không thể so sánh công bằng.

Một bảng kết quả nên có:

| Kịch bản | Startup/restore-to-ready | CPU-seconds | Artifact bytes | Error rate |
|---|---:|---:|---:|---:|
| Cold start | ... | ... | Không áp dụng | ... |
| CRaC restore local | ... | ... | ... | ... |
| CRaC restore remote | ... | ... | ... | ... |

Không chỉ so sánh thời gian từ process launch đến cổng HTTP mở. Readiness cần kiểm tra các dependency quan trọng và khả năng xử lý workload đại diện.

## 16. Thiết kế thí nghiệm và số lần lặp

Một benchmark có thể bị ảnh hưởng bởi JIT warm-up, cache state, GC timing, disk cache, network contention và CPU neighbor. Một lần chạy không đủ để kết luận.

Quy trình gợi ý:

1. Cố định JDK vendor/version/build, CRaC engine và application build.
2. Cố định container image, kernel, filesystem, storage và resource limits.
3. Chuẩn bị workload warm-up giống nhau.
4. Chạy một số lượt làm nóng pipeline và loại khỏi thống kê nếu chúng chỉ dùng để ổn định môi trường.
5. Thực hiện nhiều lần đo độc lập, thường ít nhất 10-20 lượt nếu chi phí cho phép.
6. Ghi mọi lần thất bại và nguyên nhân; không âm thầm bỏ mẫu xấu.
7. Báo cáo median, p90/p95, min/max và độ phân tán.
8. Chạy restore cho artifact được tạo để xác nhận tính sử dụng được.
9. Thử lại dưới tải và điều kiện storage/network đại diện.
10. Lưu metadata môi trường cùng kết quả.

Số lần lặp cần tăng nếu biến động lớn hoặc p95 là tiêu chí SLO. Với phép đo rất đắt, có thể bắt đầu bằng ít lượt để sàng lọc rồi mở rộng cho cấu hình cuối cùng.

Không trộn số liệu của nhiều JDK build hoặc resource profile vào cùng một tập mà không gắn nhãn.

## 17. Các biến cần kiểm soát

Các yếu tố sau có thể làm checkpoint time và image size thay đổi:

| Nhóm | Biến cần ghi |
|---|---|
| JVM | Vendor, version, flags, GC, heap max, heap used |
| CRaC | Runtime build, checkpoint engine, options, resource callbacks |
| Ứng dụng | Build ID, workload, cache size, request concurrency |
| Process | RSS/PSS, thread count, FD count, native memory |
| Container | CPU quota, cpuset, memory limit, PIDs limit |
| Kernel | Version, cgroup v1/v2, CRIU/runtime support |
| Storage | Loại volume, filesystem, throughput, free space |
| Network | Bandwidth, latency, proxy, region, packet loss |
| Pipeline | Compression, encryption, chunk size, upload concurrency |
| Dependency | Database, cache, broker và service readiness |

Thay đổi một biến mỗi lần khi cần xác định quan hệ nhân quả. Nếu thay cùng lúc heap size, CPU quota và compression level, sẽ khó biết yếu tố nào làm thời gian thay đổi.

## 18. Phân tích mối quan hệ giữa image size và checkpoint time

Image size lớn thường làm tăng thời gian ghi và truyền, nhưng không phải lúc nào cũng là yếu tố duy nhất. Nếu snapshot scan hoặc callback chiếm phần lớn thời gian, giảm kích thước package có thể không cải thiện đáng kể tổng duration.

Có thể phân tích bằng cách vẽ:

- Image bytes so với snapshot/write duration.
- Heap used/RSS so với image bytes.
- CPU-seconds so với compression ratio.
- Storage throughput so với image write duration.
- Artifact bytes so với transfer duration.
- Quiesce duration so với số request in-flight.

Nếu write duration tăng gần tuyến tính với image bytes trong cùng storage profile, storage throughput có thể là yếu tố chi phối. Nếu duration tăng dù image size không đổi, hãy xem callback, CPU throttling, metadata operation, filesystem latency hoặc runtime log.

Đừng kết luận quan hệ nhân quả từ tương quan của vài mẫu. Chạy thí nghiệm thay đổi có kiểm soát, ví dụ giữ nguyên workload và storage nhưng thay mức heap live set hoặc compression setting.

## 19. Ước lượng throughput và chi phí pipeline

Có thể tính throughput ghi hoặc truyền đơn giản:

\[
Throughput = \frac{Bytes\ processed}{Elapsed\ seconds}
\]

Ví dụ, nếu 3 GiB ciphertext được upload trong 30 giây, throughput trung bình khoảng 102,4 MiB/s theo cách quy đổi nhị phân. Khi báo cáo, ghi rõ dùng GB hay GiB và MB/s hay MiB/s.

Tổng thời gian artifact-ready:

\[
T_{ready} = T_{quiesce} + T_{snapshot/write} + T_{finalize}
             + T_{compress} + T_{encrypt} + T_{transfer} + T_{verify}
\]

Công thức này là mô hình tuần tự. Nếu một số phase chạy song song hoặc chồng lấp, đo T_ready trực tiếp và mô tả overlap thay vì cộng các duration.

Chi phí tài nguyên có thể ghi dưới dạng:

- CPU-seconds/checkpoint.
- GiB written/checkpoint.
- GiB transferred/checkpoint.
- Peak memory/checkpoint.
- Storage bytes retained theo retention period.
- Số lần KMS/storage request.
- Instance-seconds bị dành riêng cho checkpoint preparation.

Những đơn vị này giúp chuyển benchmark thành dự toán vận hành mà không phụ thuộc một bảng giá cloud cụ thể.

## 20. Tối ưu thời gian callback và quiesce

Nếu quiesce chiếm phần lớn thời gian, hãy tìm operation đang chờ thay vì chỉ tối ưu runtime snapshot.

Các cách có thể xem xét:

- Dừng nhận công việc mới sớm hơn.
- Giới hạn thời gian drain và có chính sách xử lý request quá dài.
- Chia job lớn thành batch có checkpoint nghiệp vụ riêng.
- Tránh flush đồng bộ một lượng dữ liệu không cần thiết trong callback.
- Dùng API close/stop có timeout và quan sát được.
- Dừng scheduler trước khi chờ worker.
- Tránh hai Resource cùng chờ một operation hoặc đóng cùng một client.
- Tách metric theo resource để biết callback nào chậm.

Không bỏ qua việc hoàn tất transaction hoặc đảm bảo dữ liệu bền vững chỉ để giảm checkpoint duration. Thời gian quiesce cần được tối ưu trong giới hạn an toàn nghiệp vụ.

## 21. Tối ưu image write và storage

Nếu ghi image là bottleneck:

- Dùng storage có throughput và IOPS phù hợp.
- Đặt checkpoint directory trên volume được hỗ trợ và có đủ dung lượng.
- Tránh đặt image trên network filesystem chậm nếu runtime không khuyến nghị.
- Theo dõi disk queue và I/O wait.
- Hạn chế file metadata operation không cần thiết.
- Đánh giá compression nếu storage/network là bottleneck.
- Tránh chạy nhiều checkpoint đồng thời trên cùng volume nếu gây contention.
- Đảm bảo artifact được flush/finalize theo yêu cầu trước khi publish.

Không giảm durability bằng cách bỏ fsync hoặc bỏ bước xác minh nếu pipeline cần bảo đảm artifact sau sự cố. Nếu thay đổi durability setting, phải đo và đánh giá rủi ro mất artifact khi host hoặc volume lỗi.

## 22. Tối ưu compression và encryption

Compression có lợi khi storage hoặc network là bottleneck và CPU còn dư. Nếu CPU quota đã thấp, compression có thể làm pipeline chậm hơn và ảnh hưởng workload khác.

Encryption cần được giữ theo yêu cầu bảo mật; hãy tối ưu cách triển khai thay vì bỏ bảo vệ:

- Dùng thư viện AEAD được tối ưu và có hỗ trợ native phù hợp.
- Mã hóa theo chunk để giới hạn memory.
- Chọn chunk size bằng benchmark.
- Giới hạn worker concurrency theo CPU quota.
- Tránh copy buffer nhiều lần.
- Dùng streaming để không nạp cả image vào heap.
- Đo KMS latency tách khỏi CPU encryption time.
- Dùng multipart upload phù hợp với kích thước object.

Nếu nén trước mã hóa, đo cả CPU cost của compression và phần dung lượng tiết kiệm. Đừng chỉ nhìn compression ratio.

## 23. Tính hiệu quả so với cold start

CRaC có chi phí tạo và lưu checkpoint. Lợi ích thường xuất hiện khi cùng một image được restore nhiều lần hoặc khi thời gian startup là yếu tố quan trọng.

Một phép tính đơn giản:

- T_cold: thời gian cold start đến readiness.
- T_checkpoint: thời gian tạo và chuẩn bị artifact.
- T_restore: thời gian restore đến readiness.
- N: số instance được tạo từ một checkpoint.

Tổng thời gian của N instance dùng cold start:

\[
T_{cold,total} = N \times T_{cold}
\]

Mô hình đơn giản cho checkpoint dùng chung:

\[
T_{crac,total} = T_{checkpoint} + T_{distribution}
                 + N \times T_{restore}
\]

Mô hình này chưa tính mức song song, chi phí storage giữ artifact, chi phí vận hành checkpoint builder và tải đồng thời lên dependency. Nó chỉ giúp xác định điểm hòa vốn sơ bộ.

Nếu checkpoint phải tạo lại cho mỗi lần deploy và chỉ restore một instance, chi phí tạo artifact có thể lớn hơn lợi ích. Nếu một image được dùng để scale nhiều replica, chi phí tạo ảnh có thể được phân bổ trên nhiều lần restore.

Cần so sánh cả thời gian và tài nguyên. Một restore nhanh hơn nhưng đòi hỏi nhiều RAM hoặc CPU hơn có thể làm giảm mật độ container trên node.

## 24. Kiểm tra artifact hoàn chỉnh và restore được

Checkpoint thành công không đồng nghĩa artifact chắc chắn restore được ở nơi khác. Sau mỗi lần tạo image trong benchmark, nên có bước xác minh:

- Runtime đã hoàn tất thao tác checkpoint.
- Tất cả file mong đợi tồn tại và có kích thước hợp lý.
- Manifest và metadata tương ứng với JDK/build.
- Không còn file đang được ghi.
- Checksum hoặc authentication verification thành công nếu pipeline sử dụng.
- Artifact có thể được đọc từ storage đích.
- Restore thử nghiệm hoàn tất.
- Ứng dụng đạt readiness và thực hiện được workload đại diện.

Không cần restore mọi artifact production nếu quy trình đã có cơ chế kiểm chứng tương đương và chi phí quá lớn, nhưng benchmark phải xác nhận ít nhất các artifact đại diện. Với thay đổi runtime, format, compression hoặc encryption, chạy restore test là cần thiết.

## 25. Ví dụ báo cáo benchmark

Một báo cáo hữu ích nên chứa cả môi trường, kết quả và định nghĩa metric.

~~~text
Checkpoint ID: build-42-run-07
Application build: 42
JDK: vendor / version / build
CRaC runtime: version
Kernel / cgroups: Linux / v2
Container limits: CPU 2, memory 3 GiB, pids 1024
Storage: local SSD
Workload: warmed cache, 50 concurrent requests before quiesce

Timings:
  quiesce p50/p95:             120 / 185 ms
  beforeCheckpoint p50/p95:     45 /  70 ms
  snapshot + write p50/p95:    820 / 990 ms
  compression p50/p95:         310 / 380 ms
  encryption p50/p95:          140 / 175 ms
  transfer p50/p95:            900 / 1200 ms
  artifact-ready p50/p95:      2250 / 2800 ms
  restore-to-ready p50/p95:   1150 / 1450 ms

Sizes:
  raw image:                   3.8 GiB
  compressed:                  1.5 GiB
  final encrypted artifact:    1.5 GiB + metadata

Resources:
  peak cgroup memory:          ...
  CPU-seconds:                 ...
  bytes written/transferred:   ...
  CPU throttled time:          ...
  restore success:             ...
~~~

Các số trên chỉ minh họa định dạng báo cáo, không phải kết quả đo thực tế hay mục tiêu hiệu năng. Hãy ghi rõ số lượt lặp, percentile, đơn vị, cách làm tròn và liệu các phase có chồng lấp hay không.

## 26. Quan sát và cảnh báo

Trong production, nên theo dõi xu hướng theo từng build và checkpoint ID:

| Metric | Cảnh báo khi |
|---|---|
| Quiesce duration | Tăng bất thường hoặc vượt SLO pause |
| Snapshot/write duration | Tăng dù workload và image size tương tự |
| Artifact bytes | Tăng đột biến giữa các build |
| Compression ratio | Xấu đi bất thường |
| CPU-seconds | Tăng mạnh hoặc gây contention |
| Peak cgroup memory | Gần memory limit |
| CPU throttled time | Tăng trong checkpoint pipeline |
| Transfer duration | Vượt cửa sổ publish |
| Artifact verification failures | Có checksum, signature hoặc metadata mismatch |
| Restore-to-ready | Tăng hoặc có timeout |
| Restore success rate | Giảm theo build hoặc resource profile |

Gắn version JDK, CRaC engine, application build và resource profile vào metric để phân tích regression. Khi có thay đổi dependency, GC, heap sizing hoặc checkpoint engine, so sánh với baseline cùng điều kiện.

Không đặt alert chỉ dựa trên một lần tăng nhẹ. Dùng baseline, percentile và số lần vi phạm trong cửa sổ quan sát phù hợp.

## 27. Những lỗi thường gặp khi đo

**Chỉ đo thời gian lệnh checkpoint trả về.** Artifact có thể còn cần finalize, nén, mã hóa hoặc upload. Đo đến thời điểm artifact-ready.

**Dùng thời gian callback làm thời gian snapshot.** Callback chỉ đo phần ứng dụng chuẩn bị. Đo runtime operation từ controller/log được hỗ trợ.

**Dùng currentTimeMillis để đo duration.** Wall clock có thể nhảy. Dùng monotonic clock cho khoảng thời gian trong cùng tiến trình/host.

**So sánh heap size với image size như hai đại lượng tương đương.** Image có thể chứa native memory, mapping và metadata. Ghi riêng heap, RSS/PSS và artifact bytes.

**Chỉ đo một lần.** JIT, GC, cache, disk và network làm số liệu biến động. Chạy nhiều lượt và báo cáo percentile.

**Ép GC trước mọi checkpoint.** Điều này thay đổi workload và thêm chi phí. Chỉ đo như một biến thể riêng nếu production thật sự làm vậy.

**Đo compression/encryption trên máy lớn rồi triển khai trong container nhỏ.** CPU quota và memory limit làm kết quả khác. Benchmark trong resource profile đích.

**Không đo application pause.** Artifact có thể tạo nhanh nhưng drain request lâu. Đo thời gian ingress bị dừng và request latency.

**Bỏ qua file tạm và disk allocation.** Logical size và dung lượng thực dùng có thể khác. Ghi cả apparent size và allocated size khi cần.

**Không restore thử artifact.** File tạo xong chưa chứng minh tương thích. Thực hiện restore test cho các thay đổi quan trọng.

**Cộng phase duration đang chạy song song.** Tổng phase có thể lớn hơn wall-clock end-to-end. Báo cáo từng phase và T_ready độc lập.

**Không ghi metadata môi trường.** Kết quả không thể tái lập hoặc so sánh. Lưu JDK, kernel, cgroup, storage và workload profile.

## 28. Checklist đo thời gian checkpoint và chi phí tạo ảnh

- [ ] Đã định nghĩa checkpoint request, snapshot complete và artifact-ready chưa?
- [ ] Đã tách quiesce, callback, snapshot/write, finalize và post-processing chưa?
- [ ] Đã đo application pause riêng với artifact creation time chưa?
- [ ] Đã đo restore-to-ready riêng chưa?
- [ ] Dùng monotonic clock cho elapsed time trong cùng process/host chưa?
- [ ] Có controller timestamp cho end-to-end operation không?
- [ ] Có checkpoint ID xuyên suốt log và metric không?
- [ ] Đã ghi heap used/committed, RSS/PSS, native memory và thread count chưa?
- [ ] Đã ghi logical image size, allocated disk size và file count chưa?
- [ ] Đã đo compression ratio, encryption time và transfer bytes chưa?
- [ ] Đã đo CPU-seconds, memory peak, I/O throughput và CPU throttling chưa?
- [ ] Đã ghi CPU/memory/PIDs limits và loại storage chưa?
- [ ] Benchmark dùng workload, warm-up và cache state đại diện chưa?
- [ ] Có baseline cold start và restore-to-ready cùng điều kiện không?
- [ ] Đã chạy nhiều lượt và báo median/p95 hoặc percentile phù hợp chưa?
- [ ] Có giữ lại và giải thích các lần chạy lỗi không?
- [ ] Artifact đại diện đã được verify và restore thử chưa?
- [ ] Đã so sánh chi phí tạo image với lợi ích khi restore nhiều replica chưa?

## Kết luận

Đo hiệu năng checkpoint cần tách thời gian chuẩn bị ứng dụng, snapshot/write, finalize, compression/encryption, transfer và publish. Application pause, artifact-ready duration và restore-to-ready là những metric riêng; không thể thay thế lẫn nhau. Kích thước checkpoint cũng không bằng heap size vì image có thể chứa native memory, mapping và metadata.

Một benchmark đáng tin cậy cần đo cả elapsed time, CPU-seconds, peak memory, I/O, artifact bytes và ảnh hưởng đến request. Dùng monotonic clock cho phase trong cùng process/host, controller bên ngoài cho end-to-end, chạy nhiều lần trong resource profile đại diện và kiểm tra restore thật. Khi có đủ số liệu, nhóm có thể xác định bottleneck nằm ở callback, runtime, storage, compression, encryption hay network, rồi tối ưu đúng phase mà vẫn giữ tính nhất quán và khả năng khôi phục của checkpoint.
