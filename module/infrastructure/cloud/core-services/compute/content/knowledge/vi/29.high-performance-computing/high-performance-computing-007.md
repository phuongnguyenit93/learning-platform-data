# Checkpoint và phục hồi công việc chạy dài

## Mục tiêu bài học

Các workload điện toán hiệu năng cao (HPC) thường chạy hàng giờ hoặc nhiều ngày, xử lý tập dữ liệu lớn, mô phỏng số, huấn luyện mô hình hoặc tính toán phân tán trên nhiều node. Một lỗi phần cứng, node mất kết nối, job hết wall time, Spot instance bị thu hồi hoặc tiến trình bị dừng có thể làm mất nhiều giờ tính toán nếu ứng dụng không lưu trạng thái trung gian.

Checkpoint là bản lưu trạng thái đủ để một công việc tiếp tục từ một điểm đã hoàn thành trước đó. Recovery là quy trình xác minh checkpoint, khôi phục môi trường và tiếp tục tính toán sau gián đoạn. Hai cơ chế này giúp giảm lượng công việc phải chạy lại, rút ngắn thời gian phục hồi và kiểm soát chi phí cho workload dài hạn.

Sau bài học này, bạn có thể:

- Phân biệt checkpoint, snapshot, backup và output trung gian.
- Xác định trạng thái cần lưu để tiếp tục một job đúng kết quả.
- Chọn checkpoint đồng bộ, bất đồng bộ, toàn phần hoặc gia tăng.
- Tính chu kỳ checkpoint theo chi phí lưu và xác suất lỗi.
- Thiết kế checkpoint nhất quán cho ứng dụng phân tán và MPI.
- Chọn filesystem, block storage, object storage và local scratch phù hợp.
- Phối hợp checkpoint với scheduler, wall time, preemption và tín hiệu shutdown.
- Khôi phục job từ checkpoint đã xác minh, tránh ghi đè dữ liệu tốt.
- Theo dõi checkpoint overhead, recovery time và lượng công việc bị mất.

## 1. Vì sao công việc chạy dài cần checkpoint?

Một job HPC thường thực hiện một chuỗi bước phụ thuộc nhau. Mỗi bước có thể tiêu tốn CPU/GPU, bộ nhớ, network và I/O. Nếu job dừng ở bước thứ 95 trong 100 bước mà không có checkpoint, hệ thống có thể phải chạy lại từ đầu.

Các nguyên nhân gián đoạn phổ biến:

- Node hoặc host gặp lỗi phần cứng.
- Kernel, hệ điều hành hoặc container runtime gặp sự cố.
- Job chạm giới hạn wall time của scheduler.
- Cloud capacity bị thu hồi hoặc Spot instance bị interruption.
- Tiến trình bị OOM kill hoặc vượt giới hạn tài nguyên.
- Network partition làm mất một phần node trong job phân tán.
- Người vận hành dừng job để bảo trì hoặc nâng cấp.
- Lỗi ứng dụng, thư viện, driver hoặc dữ liệu đầu vào.
- Job bị preempt để nhường tài nguyên cho workload ưu tiên cao hơn.

Không phải mọi lỗi đều có thể báo trước. Vì vậy, ứng dụng không nên chỉ dựa vào shutdown hook ở thời điểm sắp bị dừng. Checkpoint định kỳ và checkpoint tại ranh giới công việc giúp giảm thiệt hại khi tiến trình biến mất đột ngột.

### 1.1. Checkpoint giảm thời gian tính toán bị mất

Giả sử một mô phỏng chạy 12 giờ và lưu checkpoint mỗi 30 phút. Nếu job bị lỗi ngẫu nhiên, phần công việc phải chạy lại thường nhỏ hơn nhiều so với trường hợp không có checkpoint. Đổi lại, mỗi lần lưu checkpoint tiêu tốn thời gian ghi dữ liệu, I/O và có thể làm các worker tạm dừng.

Checkpoint cần cân bằng ba mục tiêu:

- Giảm lượng tính toán phải làm lại sau lỗi.
- Giữ overhead lưu checkpoint ở mức chấp nhận được.
- Bảo đảm checkpoint đủ nhất quán và bền vững để phục hồi được.

Một checkpoint được ghi nhanh nhưng không nhất quán có thể vô dụng. Một checkpoint đầy đủ nhưng mất quá nhiều thời gian ghi có thể làm giảm throughput tổng thể.

## 2. Phân biệt checkpoint, snapshot, backup và output

Các thuật ngữ này liên quan nhưng có mục đích khác nhau.

| Khái niệm | Mục đích | Nội dung thường lưu |
|---|---|---|
| Checkpoint | Tiếp tục một job đang chạy | Trạng thái tính toán, iteration, bộ nhớ nghiệp vụ, RNG, offset |
| Snapshot | Ghi lại trạng thái của một tài nguyên tại một thời điểm | Disk, volume, VM hoặc filesystem |
| Backup | Bảo vệ dữ liệu để khôi phục sau mất mát hoặc hỏng dữ liệu | Bản sao dữ liệu, metadata và lịch sử |
| Intermediate output | Kết quả trung gian của một bước | File kết quả, partition, tensor hoặc artifact |
| Final output | Kết quả hoàn tất của job | Báo cáo, mô hình, dữ liệu đã xử lý |

Snapshot VM hoặc volume không nhất thiết là checkpoint ứng dụng. Nếu snapshot được tạo khi nhiều process đang ghi dữ liệu, nó có thể chỉ nhất quán ở mức crash-consistent. Ứng dụng phân tán có thể cần một điểm đồng bộ logic giữa các node.

Backup cũng không tự động giúp tiếp tục tính toán từ đúng iteration. Backup có thể khôi phục dữ liệu, nhưng ứng dụng cần biết cách đọc và diễn giải state.

### 2.1. Checkpoint phải trả lời được câu hỏi phục hồi

Một checkpoint hữu ích phải xác định:

- Job đang ở bước hoặc iteration nào?
- Input nào đã được xử lý?
- State nào đã được commit?
- Phiên bản code và schema nào đã tạo checkpoint?
- Có bao nhiêu worker/rank và cách phân chia dữ liệu ra sao?
- File nào thuộc cùng một generation checkpoint?
- Có thể xác minh checkpoint hoàn chỉnh hay không?
- Có thể tiếp tục với số node hoặc cấu hình tài nguyên khác không?

Nếu thiếu metadata này, operator có thể khôi phục nhầm file, chạy lại dữ liệu đã xử lý hoặc kết hợp các state không thuộc cùng một thời điểm.

## 3. Xác định trạng thái cần lưu

Checkpoint không nhất thiết lưu toàn bộ RAM của process. Cần lưu phần state đủ để ứng dụng tái tạo trạng thái logic và tiếp tục tính toán chính xác.

Các thành phần thường gặp:

| Thành phần | Ví dụ |
|---|---|
| Progress | Iteration, timestep, batch index, task ID |
| Application state | Ma trận, vector, trạng thái solver, cấu trúc dữ liệu |
| Input position | File offset, partition, cursor, sequence number |
| Random state | Seed và trạng thái RNG của CPU/GPU |
| Distributed state | Rank, world size, shard, partition map |
| ML training state | Model, optimizer, scheduler, gradient scaler |
| Data pipeline | Sampler state, dataloader position, shuffle state |
| Output commit | Danh sách output đã hoàn tất, checksum và manifest |
| Compatibility metadata | App version, schema version, library/runtime version |

Không phải ứng dụng nào cũng cần mọi trường. Hãy xác định state dựa trên thuật toán và yêu cầu tái lập kết quả.

### 3.1. State và derived data

Phân biệt dữ liệu bắt buộc để tiếp tục với dữ liệu có thể tái tạo:

- **Essential state:** mất đi sẽ không thể tiếp tục đúng từ checkpoint.
- **Derived state:** có thể tính lại từ input và essential state.
- **Cache:** giúp tăng tốc nhưng không quyết định tính đúng đắn.
- **Temporary state:** file tạm hoặc buffer chưa commit.

Có thể không lưu cache để giảm dung lượng checkpoint, nhưng cần tính thời gian tạo lại cache trong recovery time. Với workload phụ thuộc cache lớn, thời gian warmup sau phục hồi có thể đáng kể.

### 3.2. Ranh giới checkpoint

Chọn ranh giới mà state nhất quán và có thể khôi phục:

- Sau khi hoàn tất một timestep mô phỏng.
- Sau một batch dữ liệu đã commit.
- Sau một epoch hoặc optimizer step trong training.
- Sau khi xử lý xong một partition.
- Sau khi tất cả rank hoàn thành một collective phase.
- Sau khi output trung gian đã được ghi bền vững.

Không lưu state ở giữa một transaction hoặc collective operation nếu ứng dụng không có cơ chế khôi phục trạng thái dang dở.

## 4. Các chiến lược checkpoint

### 4.1. Full checkpoint

Full checkpoint lưu toàn bộ state cần thiết tại một generation.

Ưu điểm:

- Đơn giản để hiểu và phục hồi.
- Không cần ghép nhiều generation.
- Dễ xác minh tính toàn vẹn.
- Ít phụ thuộc vào lịch sử checkpoint trước đó.

Nhược điểm:

- Dung lượng lớn.
- Thời gian ghi có thể dài.
- Tạo nhiều I/O và chi phí lưu trữ.
- Có thể làm tăng network traffic khi nhiều node ghi đồng thời.

Full checkpoint phù hợp khi state vừa phải, recovery đơn giản quan trọng hơn chi phí ghi, hoặc thời gian ghi nằm trong ngân sách.

### 4.2. Incremental checkpoint

Incremental checkpoint chỉ lưu phần state thay đổi kể từ checkpoint trước hoặc từ một base generation.

Ưu điểm:

- Giảm lượng dữ liệu phải ghi.
- Có thể tăng tần suất checkpoint.
- Giảm network/storage I/O nếu phần thay đổi nhỏ.

Nhược điểm:

- Recovery phải ghép base và các delta.
- Một delta hỏng có thể ảnh hưởng các generation sau.
- Quản lý retention và compaction phức tạp.
- Cần xác định rõ thứ tự và quan hệ phụ thuộc giữa các generation.

Giữ một full checkpoint định kỳ và một chuỗi delta có giới hạn giúp kiểm soát thời gian phục hồi. Định kỳ tạo base mới để không phải đọc quá nhiều delta.

### 4.3. Synchronous checkpoint

Trong synchronous checkpoint, worker dừng hoặc chờ tại một điểm an toàn cho đến khi dữ liệu checkpoint được ghi xong.

Ưu điểm là dễ xác định checkpoint đã bền vững trước khi tiếp tục. Nhược điểm là thời gian I/O trực tiếp làm giảm thời gian tính toán hữu ích.

Với job phân tán, synchronous checkpoint thường yêu cầu phối hợp giữa các rank để tất cả lưu state của cùng một logical step.

### 4.4. Asynchronous checkpoint

Asynchronous checkpoint cho phép ứng dụng tiếp tục tính toán trong khi state được ghi ở background.

Có thể dùng copy-on-write, snapshot buffer hoặc double buffering để tạo bản state nhất quán mà không khóa toàn bộ ứng dụng quá lâu.

Lợi ích:

- Giảm thời gian pause nhìn thấy bởi ứng dụng.
- Có thể chồng lấp I/O với compute.
- Tăng throughput khi storage đủ băng thông.

Rủi ro:

- State nguồn có thể tiếp tục thay đổi khi writer đang ghi.
- Buffer phụ tiêu tốn RAM.
- I/O nền có thể tranh chấp CPU, memory bandwidth và storage.
- Job có thể gặp lỗi trước khi checkpoint bất đồng bộ hoàn tất.

Chỉ đánh dấu generation là committed sau khi toàn bộ dữ liệu đã ghi và xác minh thành công. Không coi việc bắt đầu ghi background là checkpoint đã an toàn.

## 5. Chọn chu kỳ checkpoint

Checkpoint quá thường xuyên làm tăng overhead. Checkpoint quá thưa làm tăng lượng công việc bị mất khi lỗi xảy ra.

Các yếu tố quyết định chu kỳ:

- Thời gian ghi một checkpoint.
- Mean time between failures (MTBF) hoặc tỷ lệ gián đoạn quan sát được.
- Chi phí chạy lại công việc.
- Wall time còn lại.
- Dung lượng và băng thông storage.
- Khả năng checkpoint bất đồng bộ.
- Mức mất công việc tối đa chấp nhận được.

### 5.1. Mô hình overhead đơn giản

Giả sử:

- C là thời gian ghi một checkpoint.
- M là thời gian trung bình giữa các lỗi.
- T là khoảng thời gian giữa hai checkpoint.
- Mỗi lỗi làm mất trung bình khoảng T/2 công việc kể từ checkpoint gần nhất.
- C nhỏ hơn nhiều so với T và M.

Overhead gần đúng theo tỷ lệ thời gian có thể mô hình hóa:

~~~text
Overhead(T) ≈ C / T + T / (2 * M)
~~~

Thành phần C/T là thời gian dành cho checkpoint; T/(2*M) là phần công việc kỳ vọng bị mất do lỗi ngẫu nhiên trong mô hình đơn giản.

Lấy đạo hàm và tìm điểm cực tiểu cho biểu thức này cho chu kỳ gần đúng:

~~~text
T_opt ≈ sqrt(2 * C * M)
~~~

Công thức này là mô hình ước lượng ban đầu, không phải giá trị cấu hình bắt buộc. Nó giả định lỗi phân bố ngẫu nhiên, thời gian checkpoint tương đối ổn định và chưa tính đầy đủ thời gian restart, chi phí phục hồi, contention hoặc lỗi correlated.

### 5.2. Ví dụ tính chu kỳ

Giả sử một checkpoint mất 2 phút và thời gian trung bình giữa các lỗi được ước lượng là 20 giờ.

Đổi đơn vị về phút:

- C = 2 phút.
- M = 20 × 60 = 1.200 phút.

~~~text
T_opt ≈ sqrt(2 * 2 * 1200)
      ≈ sqrt(4800)
      ≈ 69.3 phút
~~~

Giá trị khoảng 69 phút là điểm bắt đầu để thử nghiệm. Nếu job có deadline, interruption thường tập trung theo lịch bảo trì hoặc Spot notice, hoặc thời gian ghi checkpoint thay đổi theo tải storage, cần điều chỉnh dựa trên dữ liệu thực tế.

### 5.3. Đặt giới hạn RPO

Recovery Point Objective (RPO) là lượng công việc hoặc dữ liệu tối đa có thể chấp nhận mất khi xảy ra lỗi.

Nếu yêu cầu không mất quá 15 phút tính toán, chu kỳ checkpoint phải đủ ngắn để đáp ứng RPO, có tính đến checkpoint thất bại và thời gian lưu bền vững. Một checkpoint mới chỉ được coi là điểm phục hồi sau khi commit hoàn tất.

RPO không chỉ là chu kỳ theo lịch. Nếu checkpoint gần nhất bị hỏng hoặc không tương thích, điểm phục hồi thực tế có thể cũ hơn một hoặc nhiều generation.

### 5.4. Đo thay vì chỉ dựa vào công thức

Ghi lại:

- Thời gian bắt đầu và hoàn tất checkpoint.
- Bytes ghi và throughput storage.
- Pause time của ứng dụng.
- Tỷ lệ checkpoint thành công.
- Thời gian phục hồi từ từng generation.
- Số phút tính toán bị mất sau lỗi.
- Số lần lỗi/gián đoạn theo loại workload.

Thử một số chu kỳ khác nhau và so sánh throughput hữu ích, tổng runtime và cost per completed job. Với workload biến động, có thể dùng chu kỳ thích nghi theo dung lượng state, tải storage hoặc wall time còn lại.

## 6. Tạo checkpoint nhất quán và nguyên tử

Một checkpoint không được công bố là hợp lệ khi chỉ mới ghi một phần file. Nếu process bị dừng giữa lúc ghi, recovery có thể đọc dữ liệu dở dang và làm hỏng trạng thái.

Một quy trình an toàn:

1. Chọn logical checkpoint ID hoặc generation duy nhất.
2. Chụp state tại ranh giới nhất quán.
3. Ghi từng phần vào vị trí tạm hoặc prefix generation mới.
4. Flush dữ liệu và hoàn tất các thao tác ghi.
5. Tính checksum và kích thước cho từng file.
6. Đọc/xác minh metadata cần thiết.
7. Ghi manifest mô tả toàn bộ file, version và checkpoint step.
8. Chỉ sau khi tất cả phần hoàn tất mới công bố generation là committed.
9. Giữ lại generation trước đó cho đến khi generation mới được xác minh.

### 6.1. POSIX filesystem

Với filesystem POSIX, một pattern thường dùng là ghi file tạm trong cùng filesystem, flush dữ liệu, sau đó rename sang tên chính thức. Rename trong cùng filesystem thường cung cấp tính nguyên tử ở mức directory entry, nhưng độ bền sau crash còn phụ thuộc việc fsync file và directory cũng như semantics của filesystem.

Pseudo-code:

~~~python
write(temp_path, checkpoint_bytes)
flush_and_fsync(temp_path)
verify_checksum(temp_path)
atomic_rename(temp_path, committed_path)
fsync_parent_directory(committed_path)
~~~

Các hàm trên là pseudo-code mô tả thứ tự thao tác. Với parallel filesystem HPC, cần xác minh semantics thực tế của client, metadata server và cache; không mặc định mọi thao tác rename/fsync đều có cùng bảo đảm trên mọi filesystem.

### 6.2. Object storage

Object storage thường cung cấp thao tác PUT object, không có semantics rename nguyên tử giống POSIX filesystem. Không nên mô phỏng rename bằng copy rồi delete và giả định nó là transaction.

Một pattern phù hợp:

1. Ghi mỗi generation vào prefix duy nhất.
2. Dùng object key bất biến cho từng rank/file.
3. Kiểm tra checksum, kích thước và metadata.
4. Ghi manifest hoàn chỉnh sau cùng.
5. Cập nhật pointer/latest bằng conditional write hoặc version control nếu dịch vụ hỗ trợ.
6. Recovery chỉ chọn generation có manifest committed và mọi object cần thiết đều tồn tại.

Ví dụ cấu trúc:

~~~text
checkpoints/
  job-4821/
    generation-000120/
      rank-0000.bin
      rank-0001.bin
      rank-0002.bin
      manifest.json
    generation-000121/
      rank-0000.bin
      rank-0001.bin
      manifest.json
    latest.json
~~~

Manifest phải xác định checkpoint step, số rank, tên object, checksum, kích thước, app version và schema version. Pointer latest chỉ trỏ tới generation đã commit.

### 6.3. Manifest là điểm commit

Manifest là bằng chứng một generation đã hoàn tất. Không tạo manifest trước khi mọi file checkpoint đã ghi xong.

Nếu job dừng trước khi manifest được ghi, generation đó được xem là incomplete và recovery bỏ qua. Nếu manifest tồn tại nhưng một object bị thiếu hoặc checksum sai, generation không hợp lệ và cần lùi về checkpoint trước.

Đây là cách tránh chọn nhầm checkpoint mới nhất chỉ dựa vào tên thư mục hoặc timestamp.

## 7. Checkpoint cho ứng dụng phân tán và MPI

Một job MPI thường có nhiều rank chạy đồng thời và trao đổi message. State của các rank có quan hệ với nhau. Nếu mỗi rank checkpoint tại một thời điểm khác nhau mà không phối hợp, recovery có thể ghép các trạng thái không tương thích.

### 7.1. Coordinated checkpoint

Coordinated checkpoint tạo một điểm phục hồi logic chung:

1. Điều phối các rank tiến tới checkpoint boundary.
2. Dừng hoặc đồng bộ các hoạt động cần thiết.
3. Đảm bảo các collective/message đang xử lý ở trạng thái an toàn.
4. Mỗi rank ghi state của mình.
5. Tập hợp kết quả và xác minh mọi rank đã hoàn tất.
6. Ghi manifest chung cho generation.
7. Cho phép job tiếp tục.

Một barrier có thể giúp các rank đồng bộ, nhưng barrier đơn lẻ không tự bảo đảm toàn bộ communication state đã được lưu nhất quán. Ứng dụng cần định nghĩa rõ những message nào đã được xử lý, những message nào còn pending và state nào thuộc cùng logical step.

### 7.2. Uncoordinated checkpoint

Uncoordinated checkpoint cho phép mỗi rank lưu độc lập. Cách này có thể giảm thời gian chờ đồng bộ, nhưng recovery phức tạp hơn vì có thể xuất hiện inconsistent global state, orphan message hoặc dependency giữa các rank.

Các kỹ thuật như message logging hoặc protocol chuyên dụng có thể giải quyết một số vấn đề, nhưng làm tăng độ phức tạp và overhead. Với ứng dụng MPI thông thường, coordinated checkpoint thường dễ thiết kế và kiểm thử hơn.

### 7.3. Manifest phân tán

Manifest chung nên lưu:

- Job ID và checkpoint generation.
- Logical timestep/iteration.
- Số rank và mapping rank-to-file.
- Node/rank topology nếu cần.
- Checksum và kích thước mỗi file.
- Application build/version.
- MPI/library version nếu ảnh hưởng compatibility.
- Schema version.
- Thời điểm checkpoint và trạng thái commit.

Nếu recovery thay đổi số rank, ứng dụng phải hỗ trợ repartition hoặc remap state. Không mặc định checkpoint tạo với 128 rank có thể khôi phục bằng 64 rank.

## 8. Checkpoint cho huấn luyện machine learning

Workload training dài hạn thường cần lưu nhiều hơn model weights. Nếu chỉ lưu weights, training có thể tiếp tục từ mô hình hiện tại nhưng optimizer và lịch học có thể bị reset, làm thay đổi quỹ đạo huấn luyện.

Một checkpoint training thường có:

- Model parameters và buffers.
- Optimizer state, ví dụ momentum hoặc Adam moments.
- Learning rate scheduler state.
- Gradient scaler state khi dùng mixed precision.
- Global step, epoch và batch position.
- Random state của Python, framework, CPU và GPU.
- Sampler/shuffle state của dataset.
- Distributed rank state hoặc shard metadata.
- Cấu hình model, optimizer và training run.
- Version code, framework và schema.

### 8.1. Ranh giới optimizer step

Nên checkpoint tại ranh giới optimizer step hoàn chỉnh, sau khi gradient accumulation và optimizer update kết thúc. Nếu lưu giữa accumulation mà không lưu đầy đủ gradient buffers và trạng thái liên quan, quá trình resume có thể khác với chạy liên tục.

Với distributed data parallel, mỗi rank có thể cần lưu state riêng hoặc dùng cơ chế sharded checkpoint. Cần bảo đảm tất cả rank thuộc cùng một training step trước khi công bố generation.

### 8.2. Ví dụ PyTorch khái niệm

~~~python
checkpoint = {
    "step": global_step,
    "model": model.state_dict(),
    "optimizer": optimizer.state_dict(),
    "scheduler": scheduler.state_dict(),
    "rng_cpu": torch.get_rng_state(),
    "rng_cuda": torch.cuda.get_rng_state_all(),
    "config": training_config,
}

save_to_temporary_location(checkpoint)
verify_and_publish_checkpoint()
~~~

Đây là ví dụ khái niệm. Trong môi trường distributed hoặc sharded training, mỗi rank có thể cần lưu phần state riêng, đồng bộ completion và dùng API checkpoint chuyên biệt của framework. Không gom toàn bộ state lên một process nếu làm cạn RAM hoặc network.

### 8.3. Data loader và tính tái lập

Để tiếp tục chính xác, cần biết batch tiếp theo là gì. Nếu sampler shuffle ngẫu nhiên, chỉ lưu epoch và batch index có thể chưa đủ; cần lưu RNG/sampler state hoặc một cách tái tạo thứ tự dữ liệu ổn định.

Với dataset stream hoặc shard, lưu partition và offset. Khi phục hồi, tránh xử lý lại một batch đã commit hoặc bỏ qua batch chưa xử lý.

## 9. Chọn nơi lưu checkpoint

Nơi lưu ảnh hưởng trực tiếp tới thời gian ghi, khả năng sống sót sau lỗi node và chi phí.

| Storage | Ưu điểm | Giới hạn/cân nhắc |
|---|---|---|
| Local NVMe/SSD | I/O nhanh, latency thấp | Có thể mất khi node bị hỏng hoặc thu hồi |
| Network block volume | Có thể tồn tại độc lập với VM | IOPS/throughput và zone attachment có giới hạn |
| Parallel filesystem HPC | Throughput cao cho nhiều node/rank | Có thể tranh chấp metadata và băng thông khi nhiều job ghi cùng lúc |
| Shared POSIX filesystem | Dễ dùng với ứng dụng file-based | Hiệu năng phụ thuộc backend, locking và metadata |
| Object storage | Bền vững, mở rộng và phù hợp lưu generation | Latency cao hơn, semantics API khác filesystem |
| Database/metadata store | Phù hợp lưu manifest và trạng thái nhỏ | Không phù hợp chứa checkpoint dung lượng rất lớn |

### 9.1. Hierarchical checkpointing

Có thể dùng nhiều tầng:

- Lưu nhanh vào local NVMe hoặc memory snapshot để giảm pause.
- Sao chép bất đồng bộ sang parallel filesystem hoặc object storage.
- Chỉ đánh dấu durable khi bản lưu ở tầng bền vững đã được xác minh.

Nếu node mất trước khi bản sao bền vững hoàn tất, checkpoint local có thể mất. Vì vậy, chỉ dùng local tier như cache hoặc bản tạm; RPO phải tính theo generation đã được commit ở storage chịu được failure domain cần bảo vệ.

### 9.2. Parallel filesystem và write contention

Nhiều rank cùng ghi file nhỏ có thể làm metadata server quá tải. Một số cách giảm áp lực:

- Gộp state thành file lớn theo rank group.
- Dùng aggregator rank hoặc I/O node.
- Điều chỉnh số writer đồng thời.
- Ghi theo chunk lớn và tuần tự hợp lý.
- Tránh tạo hàng triệu file nhỏ.
- Thử nghiệm với concurrency tương đương production.

Aggregator giúp giảm số file nhưng có thể trở thành bottleneck hoặc điểm lỗi. Cần đo throughput và khả năng chịu lỗi của đường ghi.

### 9.3. Object storage và upload multipart

Với checkpoint lớn, multipart upload có thể tăng throughput và cho phép retry từng part. Chỉ công bố manifest sau khi multipart upload hoàn tất và object có checksum hợp lệ.

Quản lý upload chưa hoàn tất để tránh tích tụ part và chi phí. Lifecycle policy có thể xóa multipart upload dang dở, nhưng cần bảo đảm không xóa generation đang được ghi.

## 10. Bảo vệ tính toàn vẹn và khả năng tương thích

Checkpoint có thể tồn tại lâu hơn phiên bản ứng dụng đã tạo ra nó. Khi code, schema hoặc thư viện thay đổi, file cũ có thể không đọc được hoặc có thể được đọc sai.

Mỗi generation nên lưu:

- Checkpoint schema version.
- Application version/build ID.
- Library/runtime version cần thiết.
- Model/config version.
- Architecture hoặc precision mode nếu ảnh hưởng binary format.
- Endianness/serialization metadata nếu định dạng phụ thuộc.
- Checksum cho từng file và manifest.

### 10.1. Checksum và validation

Trước khi resume:

1. Kiểm tra manifest tồn tại và có trạng thái committed.
2. Kiểm tra mọi file cần thiết tồn tại.
3. So sánh kích thước với manifest.
4. Xác minh checksum.
5. Kiểm tra schema và application version.
6. Kiểm tra số rank/shard và mapping.
7. Chạy validation nội dung nếu ứng dụng có invariant.
8. Chỉ bắt đầu compute sau khi toàn bộ điều kiện đạt.

Checksum phát hiện hỏng dữ liệu nhưng không chứng minh state logic đúng. Có thể cần kiểm tra range, conservation law, model tensor shape hoặc invariant nghiệp vụ.

### 10.2. Schema migration

Nếu checkpoint cũ không tương thích với ứng dụng mới, có ba lựa chọn:

- Dùng đúng phiên bản ứng dụng đã tạo checkpoint để resume.
- Chuyển đổi checkpoint bằng migration tool có version và kiểm thử.
- Bắt đầu job mới từ input gốc nếu không thể chuyển đổi an toàn.

Không sửa trực tiếp checkpoint duy nhất. Giữ bản gốc, tạo generation đã chuyển đổi và ghi lại nguồn/version mapping.

## 11. Phục hồi job từ checkpoint

Recovery cần có trình tự rõ ràng. Khôi phục nhầm generation hoặc khởi động đồng thời hai bản job có thể làm trùng output và phá tính nhất quán.

Một quy trình:

1. Xác định job bị dừng và nguyên nhân.
2. Kiểm tra scheduler state và xác nhận process cũ không còn sở hữu tài nguyên.
3. Tìm generation committed mới nhất.
4. Xác minh manifest, checksum và compatibility.
5. Xác định input, config và phiên bản ứng dụng cần thiết.
6. Cấp tài nguyên phù hợp cho job mới.
7. Đọc checkpoint và phục hồi state.
8. Kiểm tra logical step, partition, rank mapping và output đã commit.
9. Tiếp tục từ điểm kế tiếp chưa hoàn tất.
10. Ghi checkpoint generation mới và xác minh.
11. Xác nhận final output và cập nhật trạng thái job.

~~~mermaid
flowchart TD
    A["Job dừng / node mất"] --> B["Xác nhận job cũ đã kết thúc"]
    B --> C["Tìm checkpoint committed"]
    C --> D["Verify manifest, checksum, version"]
    D --> E{"Checkpoint hợp lệ?"}
    E -->|Không| F["Lùi về generation trước"]
    F --> D
    E -->|Có| G["Cấp tài nguyên và khôi phục state"]
    G --> H["Kiểm tra input/output đã commit"]
    H --> I["Resume từ logical step kế tiếp"]
    I --> J["Checkpoint generation mới"]
    J --> K["Hoàn tất và xác minh output"]
~~~

### 11.1. Chọn generation hợp lệ mới nhất

Không chọn chỉ theo tên lớn nhất hoặc timestamp mới nhất. Chọn generation có manifest committed, mọi file tồn tại, checksum đúng và schema tương thích.

Nếu generation mới nhất bị lỗi, lùi về generation hợp lệ trước đó. Ghi nhận lượng công việc phải chạy lại và lý do loại generation hỏng.

### 11.2. Tránh hai job cùng ghi một output

Khi job được requeue, phải bảo đảm instance/job cũ không còn ghi output. Dùng lease, fencing token hoặc scheduler ownership để tránh hai execution cùng cập nhật một kết quả.

Một job restart nên có execution ID mới nhưng giữ logical job ID và checkpoint lineage. Output commit cần phân biệt attempt và generation.

## 12. Output commit và exactly-once effect

Checkpoint state không đủ nếu output bên ngoài đã được ghi nhưng chưa được đánh dấu hoàn tất. Ví dụ worker ghi kết quả vào database, sau đó bị dừng trước khi cập nhật checkpoint. Khi resume, worker có thể ghi lại kết quả.

Một pattern an toàn:

1. Ghi output vào vị trí tạm gắn với job/step.
2. Xác minh output hoàn chỉnh.
3. Commit output bằng manifest hoặc transaction.
4. Cập nhật checkpoint/processed marker trong cùng transaction logic nếu có thể.
5. Khi recovery, đọc manifest để bỏ qua step đã commit.
6. Dùng idempotency key hoặc unique key cho side effect.

Với object storage, dùng key bất biến theo job ID, step và generation. Công bố manifest sau khi tất cả object hoàn tất. Với database, dùng transaction hoặc unique constraint. Không dựa vào tên file để suy đoán output đã commit.

Exactly-once processing trên toàn hệ thống thường đòi hỏi thiết kế giao dịch và idempotency ở từng side effect. Checkpoint đơn lẻ không tạo ra bảo đảm exactly-once.

## 13. Phối hợp checkpoint với scheduler và wall time

HPC scheduler thường cấp tài nguyên trong một khoảng wall time. Job có thể bị kết thúc khi tới giới hạn, kể cả khi ứng dụng vẫn đang tính toán đúng.

Kế hoạch checkpoint cần tính đến:

- Thời gian còn lại trước wall-time limit.
- Thời gian checkpoint p95/p99.
- Thời gian shutdown và flush.
- Thời gian scheduler gửi warning signal.
- Thời gian dự phòng cho node chậm hoặc filesystem tải cao.
- Chính sách requeue/preemption của scheduler.

Không đợi tới giây cuối mới bắt đầu checkpoint. Nếu checkpoint kéo dài hơn thời gian còn lại, job có thể bị kill giữa lúc ghi.

### 13.1. Tín hiệu cảnh báo trước khi kết thúc

Một số scheduler cho phép gửi signal trước wall-time limit. Với Slurm, có thể cấu hình tín hiệu cảnh báo trước một khoảng thời gian:

~~~bash
#!/bin/bash
#SBATCH --job-name=long-simulation
#SBATCH --time=08:00:00
#SBATCH --signal=USR1@300

srun ./solver --resume-from latest
~~~

Ví dụ yêu cầu gửi USR1 trước 300 giây so với giới hạn thời gian. Ứng dụng solver cần có signal handler hoặc cơ chế điều khiển để bắt đầu checkpoint và thoát an toàn. Cấu hình signal và cách truyền tới job step cần được xác minh theo phiên bản và chính sách Slurm tại cluster.

Không thực hiện I/O phức tạp hoặc gọi hàm không async-signal-safe trực tiếp trong signal handler cấp thấp. Handler nên đặt cờ hoặc đánh thức event loop; luồng chính thực hiện checkpoint tại safe point.

### 13.2. Requeue

Một số scheduler cho phép requeue job sau preemption hoặc khi job được cấu hình phù hợp. Requeue không tự khôi phục state ứng dụng. Script hoặc workflow phải xác định checkpoint hợp lệ và truyền đúng tham số resume.

Cần tránh vòng lặp requeue vô hạn khi checkpoint hỏng hoặc job luôn thất bại ở cùng bước. Ghi attempt count, giới hạn số lần restart và chuyển job sang trạng thái cần điều tra khi vượt ngưỡng.

### 13.3. Cloud Spot interruption

Nếu HPC job chạy trên cloud Spot/preemptible VM, interruption notice có thể cung cấp thời gian ngắn để dừng. Hãy:

- Nhận notice qua cơ chế của provider.
- Ngừng nhận task mới hoặc giảm công việc đang khởi chạy.
- Bắt đầu checkpoint nếu còn đủ thời gian.
- Ưu tiên checkpoint vào storage bền vững ngoài instance.
- Không phụ thuộc local ephemeral disk.
- Chuẩn bị capacity thay thế và quy trình resume.

Nếu không có đủ thời gian, bỏ qua checkpoint mới chưa hoàn tất và phục hồi từ generation committed gần nhất. Không công bố checkpoint dở dang để cố tận dụng vài giây còn lại.

## 14. Phục hồi job phân tán

Với job nhiều node, recovery cần cấp lại tài nguyên tương thích và khôi phục toàn bộ rank/shard thuộc cùng generation.

Các câu hỏi cần giải quyết:

- Có cần giữ nguyên số node/rank không?
- Có thể thay đổi placement hoặc network topology không?
- State có gắn với local disk của node cũ không?
- MPI implementation có tương thích với checkpoint không?
- Có cần tạo lại communicator và collective state?
- Dữ liệu input có còn cùng version không?
- Checkpoint của tất cả rank đã được commit cùng generation chưa?

### 14.1. Restart cùng topology

Khôi phục cùng số rank và mapping đơn giản hơn khi checkpoint chứa state theo rank. Cần xác minh node mới có cùng kiến trúc, runtime, library và filesystem path cần thiết.

### 14.2. Restart với topology khác

Nếu số rank thay đổi, ứng dụng phải hỗ trợ repartition state. Ví dụ ma trận được chia theo hàng cho 16 rank cần được phân chia lại khi resume với 8 rank.

Một số framework hỗ trợ resharding hoặc elastic training; một số solver MPI không hỗ trợ. Không chỉ đổi số task trong scheduler rồi kỳ vọng binary tự khôi phục đúng.

### 14.3. Partial node failure

Khi một rank lỗi, các rank còn lại có thể bị treo trong collective operation hoặc communicator mất hiệu lực. Nếu ứng dụng không hỗ trợ fault-tolerant MPI, thường cần kết thúc toàn bộ job step và restart từ checkpoint toàn cục.

Chỉ tiếp tục các rank còn sống khi runtime, communication library và ứng dụng có giao thức phục hồi được thiết kế rõ.

## 15. Tối ưu checkpoint cho GPU và workload lớn

Checkpoint GPU có thể chứa model weights, optimizer state, activation hoặc dữ liệu mô phỏng. Dung lượng lớn làm tăng thời gian copy từ GPU memory sang host memory và ghi storage.

Một số cách tối ưu:

- Chỉ lưu state cần thiết để resume.
- Ghi tại ranh giới iteration/step an toàn.
- Dùng asynchronous copy khi framework hỗ trợ và bảo đảm snapshot nhất quán.
- Dùng sharded checkpoint để tránh gom toàn bộ state vào một node.
- Điều chỉnh số writer và kích thước chunk.
- Nén nếu tiết kiệm I/O lớn hơn chi phí CPU/GPU.
- Dùng incremental checkpoint khi state thay đổi ít.
- Đo contention với training/inference và network collective.

Nén có thể giảm dung lượng truyền nhưng tiêu tốn CPU và kéo dài thời gian trước khi checkpoint bền vững. Với GPU job, nén trên CPU có thể cạnh tranh tài nguyên của data loader hoặc communication thread. Benchmark end-to-end thay vì chỉ đo tốc độ nén.

### 15.1. Snapshot RAM và process-level checkpoint

Một số công nghệ có thể snapshot memory/process state để phục hồi process gần như nguyên trạng. Đây là kỹ thuật khác với application-level checkpoint.

Process-level checkpoint phụ thuộc kernel, runtime, driver, file descriptor, network socket, GPU state và cấu hình host. Nó có thể không tương thích giữa node hoặc phiên bản khác nhau.

Application-level checkpoint thường dễ chuyển giữa node và phiên bản hơn vì lưu state logic, nhưng cần ứng dụng hỗ trợ serialization/resume. Chọn theo yêu cầu portability và mức độ kiểm soát ứng dụng.

## 16. Bảo mật và quản lý vòng đời checkpoint

Checkpoint có thể chứa dữ liệu đầu vào, model weights, thông tin người dùng, state nội bộ hoặc dữ liệu nhạy cảm. Cần bảo vệ tương tự dữ liệu production.

Nguyên tắc:

- Mã hóa khi truyền và khi lưu.
- Dùng workload identity và quyền tối thiểu.
- Tách quyền ghi checkpoint khỏi quyền xóa/retention.
- Không lưu secret dài hạn trong checkpoint nếu có thể lấy lại an toàn khi resume.
- Giới hạn quyền đọc theo job, project hoặc tenant.
- Ghi audit log cho create, read, restore, delete và redrive.
- Dùng checksum để phát hiện hỏng dữ liệu.
- Đặt retention theo giá trị phục hồi và yêu cầu compliance.
- Xóa checkpoint cũ theo policy, giữ generation cần cho rollback.
- Bảo vệ manifest khỏi bị sửa hoặc trỏ sang object không đáng tin.

Không ghi access token hoặc credential ngắn hạn vào checkpoint. Khi resume, cấp lại credential theo identity của execution mới.

### 16.1. Retention và cleanup

Giữ quá ít checkpoint có thể làm mất điểm phục hồi nếu generation mới hỏng. Giữ quá nhiều làm tăng storage cost và tạo dữ liệu nhạy cảm tồn tại lâu hơn cần thiết.

Một policy có thể giữ:

- Generation mới nhất đã xác minh.
- Một hoặc vài generation trước để rollback.
- Full checkpoint định kỳ làm base.
- Delta cần thiết để phục hồi từ base.
- Checkpoint được gắn retention lock nếu có yêu cầu audit.

Chỉ xóa generation cũ sau khi xác minh generation mới và dependency chain còn đầy đủ. Với incremental checkpoint, không xóa base nếu delta còn phụ thuộc vào nó.

## 17. Theo dõi hiệu quả checkpoint và recovery

Theo dõi checkpoint ở cấp job, node, rank và storage.

| Metric | Ý nghĩa |
|---|---|
| checkpoint_duration_seconds | Thời gian tạo một checkpoint |
| checkpoint_bytes_written | Dung lượng ghi mỗi generation |
| checkpoint_success_total | Số checkpoint hoàn tất |
| checkpoint_failure_total | Số checkpoint thất bại |
| checkpoint_pause_seconds | Thời gian ứng dụng bị dừng để lưu |
| checkpoint_age_seconds | Tuổi của generation committed mới nhất |
| checkpoint_validation_failures | Số generation không qua kiểm tra |
| recovery_duration_seconds | Thời gian từ bắt đầu restore tới resume |
| recovery_success_total | Số lần phục hồi thành công |
| lost_compute_seconds | Lượng thời gian tính toán phải chạy lại |
| job_restart_count | Số lần job được restart |
| storage_throughput_bytes_per_second | Throughput ghi/đọc checkpoint |
| checkpoint_overhead_ratio | Tỷ lệ thời gian checkpoint so với tổng runtime |

### 17.1. Các chỉ số SLO

Có thể đặt mục tiêu:

- RPO: lượng tính toán tối đa chấp nhận mất.
- RTO: thời gian tối đa từ lúc phát hiện job dừng đến khi job tiếp tục.
- Checkpoint success rate: tỷ lệ checkpoint commit thành công.
- Recovery success rate: tỷ lệ job resume thành công.
- Maximum checkpoint age: tuổi tối đa của checkpoint hợp lệ.
- Checkpoint overhead budget: tỷ lệ runtime dành cho checkpoint.

Đặt ngưỡng theo loại workload. Một mô phỏng khoa học có thể chấp nhận RTO vài chục phút; một pipeline gần thời gian thực có thể cần phục hồi nhanh hơn.

### 17.2. Phân biệt checkpoint chậm và recovery chậm

Checkpoint chậm thường liên quan tới serialize, copy memory, filesystem metadata hoặc storage throughput.

Recovery chậm có thể do:

- Cấp lại node và GPU.
- Pull image/container.
- Attach volume.
- Download checkpoint lớn.
- Giải nén và deserialize.
- Rebuild communicator hoặc data partition.
- Warm cache và compile kernel.

Tối ưu recovery cần đo từng giai đoạn, không chỉ tối ưu thời gian ghi checkpoint.

## 18. Kiểm thử khả năng phục hồi

Checkpoint chỉ đáng tin khi đã thử khôi phục. Một job ghi được file chưa chứng minh có thể resume đúng.

Các kịch bản nên kiểm thử:

1. Job dừng bình thường sau checkpoint.
2. Job bị kill ngay trước khi checkpoint bắt đầu.
3. Job bị kill giữa lúc ghi một file.
4. Job bị kill sau khi ghi file nhưng trước manifest commit.
5. Một rank không ghi được checkpoint.
6. Checksum của một file bị sai.
7. Generation mới thiếu object.
8. Ứng dụng mới không đọc được schema cũ.
9. Node local scratch biến mất.
10. Job được requeue với số node hoặc rank khác.
11. Scheduler gửi warning signal trước wall time.
12. Spot interruption xảy ra trong lúc compute hoặc lúc checkpoint.
13. Output đã commit nhưng checkpoint chưa cập nhật.
14. Hai execution cùng cố ghi một logical job.

Sau mỗi test, xác minh:

- Recovery chọn đúng generation.
- Không đọc generation incomplete.
- Job tiếp tục từ logical step đúng.
- Output không bị thiếu hoặc nhân đôi.
- State phân tán nhất quán.
- RPO và RTO đạt mục tiêu.
- Chi phí retry và dữ liệu tạm được kiểm soát.

### 18.1. Fault injection có kiểm soát

Có thể chủ động kill process, làm chậm storage hoặc ngắt một worker trong môi trường thử nghiệm. Giới hạn phạm vi, dùng dữ liệu có thể tái tạo và xác minh không tác động workload khác.

Không thử phá hủy checkpoint duy nhất hoặc xóa dữ liệu production để kiểm tra recovery. Tạo bản sao thử nghiệm và xác nhận đường rollback trước khi fault injection.

## 19. Runbook phục hồi công việc chạy dài

Một runbook nên có owner, điều kiện dừng và thao tác có thể kiểm chứng.

### Khi job dừng bất thường

1. Ghi job ID, execution ID, scheduler state và thời điểm dừng.
2. Xác nhận process cũ không còn chạy hoặc ghi output.
3. Kiểm tra node, filesystem, storage và nguyên nhân lỗi.
4. Tìm generation checkpoint committed gần nhất.
5. Xác minh manifest, checksum, schema và app version.
6. Kiểm tra input version và output đã commit.
7. Cấp lại resource và placement phù hợp.
8. Resume từ generation hợp lệ.
9. Theo dõi tiến độ, lỗi và checkpoint tiếp theo.
10. Đối chiếu output cuối và ghi nhận thời gian phục hồi.

### Khi checkpoint mới không hợp lệ

- Không ghi đè checkpoint trước.
- Đánh dấu generation mới là invalid trong metadata/audit.
- Lùi về generation committed trước đó.
- Tính lượng công việc phải chạy lại.
- Kiểm tra storage error, checksum và lỗi writer.
- Sửa nguyên nhân trước khi tăng tần suất checkpoint.

### Khi recovery liên tục thất bại

- Dừng retry tự động sau ngưỡng.
- Giữ nguyên checkpoint và log để điều tra.
- Kiểm tra compatibility và schema migration.
- Xác minh số rank, architecture và dependency.
- Thử restore bản sao trong môi trường cô lập.
- Chỉ chạy lại production sau khi xác định điểm phục hồi hợp lệ.

## 20. Lỗi thường gặp và cách tránh

**Chỉ lưu model weights:** optimizer, RNG, sampler hoặc solver state bị mất. Lưu toàn bộ state cần thiết cho resume.

**Ghi đè checkpoint tốt:** process bị kill giữa lần ghi mới và làm mất điểm phục hồi trước. Dùng generation bất biến và manifest commit sau cùng.

**Coi file tồn tại là checkpoint hoàn chỉnh:** file có thể thiếu bytes hoặc chưa flush. Xác minh checksum, size và manifest.

**Mỗi MPI rank ghi độc lập không có coordination:** state có thể thuộc các logical step khác nhau. Dùng coordinated checkpoint hoặc giao thức phục hồi rõ ràng.

**Chỉ lưu trên local disk:** node mất thì checkpoint mất. Sao chép sang storage bền vững và chỉ commit sau khi bản bền vững hoàn tất.

**Checkpoint quá thường xuyên:** I/O chiếm runtime và gây contention. Đo C, MTBF và overhead để chọn chu kỳ.

**Checkpoint quá thưa:** mất nhiều giờ tính toán khi lỗi. Đặt RPO và kiểm thử interruption.

**Async checkpoint không snapshot state:** writer đọc state đang thay đổi. Dùng copy-on-write, immutable buffer hoặc safe point.

**Không lưu version/schema:** ứng dụng mới không đọc được checkpoint cũ. Ghi compatibility metadata và migration path.

**Resume với topology khác mà không hỗ trợ repartition:** state bị phân phối sai. Giữ topology hoặc dùng framework có resharding.

**Không phối hợp output và checkpoint:** output bị ghi trùng hoặc bỏ sót sau recovery. Dùng commit manifest, transaction và idempotency.

**Tin rằng scheduler requeue tự phục hồi:** requeue chỉ chạy lại job; ứng dụng phải đọc checkpoint và resume.

**Không kiểm thử restore:** file checkpoint tồn tại nhưng không thể khôi phục. Thực hiện recovery drill định kỳ.

## 21. Checklist checkpoint và recovery

- [ ] Đã xác định failure model và RPO/RTO.
- [ ] Đã liệt kê essential state, derived state và output đã commit.
- [ ] Checkpoint được tạo tại logical safe point.
- [ ] Chu kỳ checkpoint được chọn từ thời gian ghi, MTBF và overhead đo được.
- [ ] Có full checkpoint hoặc base generation và chính sách incremental rõ ràng.
- [ ] Async checkpoint dùng snapshot nhất quán.
- [ ] Generation có ID duy nhất và manifest commit sau cùng.
- [ ] Mỗi file có size/checksum và schema/application version.
- [ ] Checkpoint bền vững ngoài local ephemeral storage.
- [ ] Distributed ranks đồng bộ và được mô tả trong manifest chung.
- [ ] ML training lưu optimizer, scheduler, RNG và sampler state khi cần.
- [ ] Scheduler warning signal và wall-time budget được tính đến.
- [ ] Requeue không tạo hai execution cùng ghi một logical job.
- [ ] Recovery chọn generation committed hợp lệ mới nhất.
- [ ] Output có commit marker hoặc idempotency để tránh duplicate.
- [ ] Credential được cấp lại khi resume, không lưu secret dài hạn trong checkpoint.
- [ ] Retention giữ đủ generation để rollback và cleanup không xóa base cần thiết.
- [ ] Có dashboard checkpoint age, duration, failure, recovery time và lost compute.
- [ ] Đã kiểm thử lỗi giữa lúc ghi, checksum sai, thiếu file và node mất đột ngột.
- [ ] Có runbook và owner cho phục hồi job thất bại.

Checkpoint biến một công việc chạy dài thành các đoạn có thể phục hồi, nhưng chỉ hữu ích khi state được lưu nhất quán, bền vững và có thể xác minh. Hãy chọn safe point phù hợp, tính chu kỳ theo chi phí ghi và rủi ro lỗi, commit generation bằng manifest sau khi mọi dữ liệu hoàn tất, rồi kiểm tra compatibility trước khi resume. Kết hợp checkpoint với scheduler signal, storage phù hợp, idempotent output và recovery drill giúp workload HPC tiếp tục sau lỗi mà không phải chạy lại toàn bộ công việc hoặc làm sai lệch kết quả.
