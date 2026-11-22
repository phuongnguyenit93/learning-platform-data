# Phân biệt checkpoint thành công, checkpoint thất bại và restore thất bại

Trong chu kỳ CRaC (Coordinated Restore at Checkpoint), checkpoint và restore là hai thao tác riêng biệt. **Checkpoint thành công** có nghĩa JVM đã tạo được ảnh trạng thái theo yêu cầu. **Checkpoint thất bại** có nghĩa quá trình tạo ảnh không hoàn tất hoặc runtime từ chối yêu cầu. **Restore thất bại** xảy ra ở bước sau, khi JVM không thể khôi phục tiến trình từ ảnh checkpoint hoặc ứng dụng không thể tiếp tục hoạt động bình thường sau khi khôi phục.

Phân biệt đúng ba kết quả này giúp khoanh vùng lỗi chính xác. Một thư mục checkpoint đã xuất hiện chưa đủ chứng minh ảnh hợp lệ; ngược lại, restore thất bại cũng không tự động chứng minh thao tác checkpoint trước đó đã thất bại. Cần đọc kết quả của từng giai đoạn cùng log JVM, log CRIU/nền tảng và trạng thái ứng dụng.

## 1. Nhìn chu kỳ CRaC như các giai đoạn độc lập

Một quy trình điển hình có các giai đoạn sau:

```text
Khởi chạy JVM với -XX:CRaCCheckpointTo
                  |
                  v
       Ứng dụng hoàn tất khởi tạo
                  |
                  v
        Chuẩn bị tài nguyên CRaC
                  |
                  v
          Tạo ảnh checkpoint
                  |
          +-------+-------+
          |               |
        Thành công       Thất bại
          |               |
          v               v
    Lưu ảnh hoàn tất   Dừng điều tra lỗi
          |
          v
  Khởi chạy restore bằng
  -XX:CRaCRestoreFrom=<path>
          |
     +----+----+
     |         |
   Thành công Thất bại
     |         |
     v         v
 Kiểm tra    Điều tra lỗi
 readiness   restore
```

Ở đây có ba điểm cần phân biệt:

1. Quá trình chuẩn bị checkpoint có thể thất bại trước khi JVM bắt đầu ghi ảnh, ví dụ callback tài nguyên báo lỗi.
2. JVM có thể bắt đầu tạo ảnh nhưng gặp lỗi trong lúc dump tiến trình hoặc ghi dữ liệu. Khi đó có thể còn thư mục hay file dở dang.
3. Checkpoint có thể được tạo thành công, nhưng một lần restore sau đó vẫn thất bại do môi trường không tương thích, thiếu tài nguyên hoặc lỗi trong giai đoạn khôi phục.

Việc checkpoint hoàn tất và việc ứng dụng hoạt động tốt sau restore là hai tiêu chí khác nhau. Một hệ thống triển khai nên ghi nhận kết quả của từng giai đoạn riêng biệt.

## 2. Checkpoint thành công nghĩa là gì?

Checkpoint được xem là thành công khi runtime hoàn tất quy trình tạo ảnh và xác nhận kết quả theo cơ chế của bản JDK/CRaC đang sử dụng. Thông thường, điều này bao gồm việc các callback chuẩn bị tài nguyên hoàn tất, tiến trình được dump và dữ liệu checkpoint cần thiết được ghi xong.

Ví dụ, ứng dụng được khởi chạy với thư mục checkpoint:

```bash
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1
java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar application.jar
```

Sau khi ứng dụng sẵn sàng, yêu cầu checkpoint bằng `jcmd`:

```bash
jcmd <pid> JDK.checkpoint
```

Khi đánh giá kết quả, cần xem đồng thời:

- Output và exit status của lệnh điều khiển `jcmd` theo cách runtime hiện tại cung cấp.
- Log JVM cho biết callback trước checkpoint và thao tác checkpoint có hoàn tất hay không.
- Log của CRIU hoặc lớp hạ tầng checkpoint nếu môi trường có cung cấp.
- Trạng thái tiến trình gốc sau checkpoint. Với quy trình dump thông thường, tiến trình có thể kết thúc khi ảnh được tạo; đây không nhất thiết là lỗi. Hành vi cụ thể cần đối chiếu với bản CRaC và cách triển khai đang dùng.
- Dữ liệu checkpoint đã được ghi hoàn tất tại đường dẫn đích và runtime không báo lỗi khi kết thúc thao tác.

Không có một thông báo log duy nhất hoặc một cấu trúc thư mục chung cho mọi bản CRaC. Vì vậy, hãy dùng tài liệu của distribution JDK đang triển khai để xác định tín hiệu thành công chính thức. Có thể dùng sự tồn tại của dữ liệu checkpoint như một bằng chứng bổ sung, nhưng không nên chỉ dựa vào việc thư mục đã được tạo.

Sau khi checkpoint thành công, ảnh đã sẵn sàng cho bước restore trong môi trường tương thích. Điều này chưa chứng minh restore sẽ thành công trên mọi máy, kernel hoặc cấu hình triển khai.

## 3. Checkpoint thất bại nghĩa là gì?

Checkpoint thất bại khi JVM hoặc lớp hạ tầng không thể hoàn tất việc tạo ảnh. Lỗi có thể xảy ra trước khi bắt đầu dump hoặc trong khi đang ghi ảnh.

### 3.1. Thất bại ở bước chuẩn bị tài nguyên

Trước khi checkpoint, CRaC gọi các callback chuẩn bị tài nguyên đã đăng ký, chẳng hạn `beforeCheckpoint`. Ứng dụng hoặc thư viện có thể đóng kết nối, dừng thread, flush dữ liệu và đưa tài nguyên về trạng thái an toàn.

Nếu một callback ném exception hoặc phát hiện tài nguyên chưa thể checkpoint, runtime có thể từ chối thao tác. Ví dụ:

- Connection pool không thể đóng hoặc tạm dừng đúng cách.
- Một socket vẫn đang ở trạng thái không được hỗ trợ.
- Thread nền đang thực hiện công việc mà ứng dụng không thể tạm dừng an toàn.
- Một thư viện phát hiện file handle hoặc tài nguyên native không thể lưu.
- Ứng dụng chưa hoàn tất giao dịch hoặc tác vụ cần thiết trước checkpoint.

Trong tình huống này, lỗi thuộc giai đoạn chuẩn bị. Chưa nên kết luận CRIU dump bị lỗi nếu log cho thấy runtime dừng trước khi bắt đầu dump.

### 3.2. Thất bại trong khi tạo ảnh

Nếu bước chuẩn bị hoàn tất nhưng việc dump tiến trình không thành công, nguyên nhân có thể nằm ở môi trường hoặc hệ thống lưu trữ:

- CRIU hoặc tính năng kernel cần thiết chưa được cài đặt/bật hoặc không tương thích.
- Thiếu quyền cần thiết để dump tiến trình, namespace hoặc tài nguyên liên quan.
- Filesystem không hỗ trợ thao tác cần thiết hoặc thư mục đích không ghi được.
- Hết dung lượng lưu trữ hoặc gặp lỗi I/O.
- Có tài nguyên native, mapping hoặc trạng thái tiến trình mà nền tảng không thể dump.
- Cấu hình container chặn capability, namespace hoặc syscall cần thiết.

Log ở giai đoạn này thường giúp xác định lỗi đến từ JVM, CRIU, kernel hay filesystem. Hãy dùng thông báo lỗi thực tế để chọn hướng điều tra.

### 3.3. Vì sao thư mục tồn tại nhưng checkpoint vẫn thất bại?

Runtime có thể tạo thư mục đích hoặc ghi một phần dữ liệu trước khi gặp lỗi. Do đó, thư mục tồn tại không có nghĩa toàn bộ ảnh đã được tạo thành công. Không tự đổi tên, sửa nội dung hoặc xóa một vài file bên trong ảnh để cố làm checkpoint có vẻ hợp lệ.

Khi thao tác thất bại, hãy giữ log và ghi nhận trạng thái thư mục để điều tra. Sau khi xác định nguyên nhân, chỉ dọn dữ liệu checkpoint dở dang theo quy trình của runtime và quy trình vận hành của ứng dụng. Nếu cần thử lại, dùng một thư mục checkpoint mới hoặc đã được làm sạch đúng cách theo hướng dẫn của bản CRaC, tránh trộn dữ liệu của lần thử cũ với lần mới.

## 4. Restore thất bại nghĩa là gì?

Restore thất bại là tình huống checkpoint đã được tạo hoặc được cho là đã tạo, nhưng JVM không thể khôi phục tiến trình từ ảnh đó hoặc ứng dụng không thể tiếp tục hoạt động sau restore.

Lệnh restore thường có dạng:

```bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoints/release-1
```

Restore có thể thất bại ở nhiều lớp khác nhau:

| Giai đoạn | Biểu hiện | Nhóm nguyên nhân có thể gặp |
| --- | --- | --- |
| Nạp checkpoint | JVM không đọc hoặc không nhận diện được ảnh | Đường dẫn sai, thiếu file, ảnh không hoàn chỉnh hoặc dữ liệu bị hỏng |
| Khôi phục tiến trình | Runtime/CRIU không thể dựng lại tiến trình | Khác biệt kernel, namespace, quyền, kiến trúc CPU hoặc tài nguyên hệ điều hành |
| Khôi phục tài nguyên | Tiến trình được dựng lại nhưng callback sau restore báo lỗi | Database, socket, file, credential hoặc service bên ngoài không thể kết nối lại |
| Khởi động ứng dụng sau restore | JVM đã tiếp tục nhưng ứng dụng không hoàn tất startup | Lỗi trong `afterRestore`, cấu hình môi trường thay đổi, cache hoặc dependency không còn hợp lệ |
| Kiểm tra readiness | Tiến trình sống nhưng không phục vụ được request | Endpoint phụ thuộc tài nguyên chưa phục hồi, tác vụ nền chưa chạy hoặc ứng dụng ở trạng thái lỗi |

Điểm quan trọng là phân biệt **JVM restore thành công** với **ứng dụng sẵn sàng phục vụ**. Nếu tiến trình đã được khôi phục nhưng `afterRestore` thất bại hoặc readiness không đạt, hãy ghi nhận riêng lỗi phục hồi ứng dụng. Không gộp mọi trường hợp thành “checkpoint thất bại”.

## 5. Bảng phân biệt ba kết quả

| Tiêu chí | Checkpoint thành công | Checkpoint thất bại | Restore thất bại |
| --- | --- | --- | --- |
| Thời điểm xảy ra | Khi tạo ảnh trạng thái | Khi chuẩn bị hoặc tạo ảnh | Sau khi đã có ảnh và bắt đầu restore |
| Callback điển hình | `beforeCheckpoint` hoàn tất | Callback chuẩn bị báo lỗi hoặc thao tác dump lỗi | Lỗi khi dựng tiến trình hoặc callback `afterRestore` |
| Ảnh checkpoint | Được runtime xác nhận tạo hoàn tất | Có thể không có hoặc chỉ còn dữ liệu dở dang | Đã tồn tại/được chọn để restore nhưng không thể dùng thành công trong môi trường hiện tại |
| Trạng thái JVM | Thao tác checkpoint hoàn tất theo semantics của runtime | Thao tác bị từ chối hoặc bị ngắt bởi lỗi | JVM không khôi phục được, hoặc khôi phục được nhưng ứng dụng lỗi sau đó |
| Hướng xử lý | Tiếp tục kiểm chứng bằng restore | Điều tra callback, JVM, CRIU, kernel, quyền và storage | Kiểm tra ảnh, tính tương thích môi trường và resource sau restore |

Một trường hợp đặc biệt thường gây nhầm lẫn là checkpoint thành công nhưng restore thất bại. Khi đó kết quả của hai thao tác phải được ghi nhận riêng: checkpoint đã hoàn tất; lần restore cụ thể đã không thành công. Nguyên nhân có thể là môi trường restore khác môi trường tạo checkpoint, ảnh bị thay đổi sau khi tạo, hoặc ứng dụng không thể khôi phục tài nguyên bên ngoài.

## 6. Đọc log theo đúng giai đoạn

Khi điều tra, trước hết xác định lỗi xuất hiện ở thời điểm nào. Tạo một mốc thời gian gồm:

1. JVM bắt đầu chạy với `-XX:CRaCCheckpointTo`.
2. Ứng dụng hoàn tất startup và readiness.
3. Lệnh `jcmd <pid> JDK.checkpoint` được gửi.
4. Callback trước checkpoint bắt đầu và kết thúc.
5. Runtime/CRIU bắt đầu dump và kết thúc hoặc báo lỗi.
6. JVM/tiến trình gốc thay đổi trạng thái.
7. Lệnh restore với `-XX:CRaCRestoreFrom` được chạy.
8. JVM hoàn tất khôi phục, callback sau restore chạy và ứng dụng đạt hoặc không đạt readiness.

Từ timeline này, đối chiếu log để xác định giai đoạn cuối cùng hoàn tất. Ví dụ:

- Nếu log báo lỗi từ `beforeCheckpoint`, tập trung vào resource callback và trạng thái ứng dụng.
- Nếu callback đã hoàn tất nhưng CRIU báo lỗi khi dump, tập trung vào kernel, quyền, namespace và filesystem.
- Nếu checkpoint đã được xác nhận thành công nhưng restore báo không đọc được ảnh, kiểm tra đường dẫn, quyền đọc, tính toàn vẹn và việc ảnh có bị di chuyển/thay đổi không.
- Nếu tiến trình đã được dựng lại nhưng `afterRestore` ném exception, kiểm tra việc tạo lại kết nối và tài nguyên bên ngoài.
- Nếu JVM và callback sau restore hoàn tất nhưng readiness vẫn lỗi, điều tra tầng ứng dụng và dependency như khi xử lý lỗi startup thông thường.

Không nên chỉ tìm từ khóa `ERROR` rồi kết luận. Một log error của ứng dụng có thể không liên quan đến thao tác checkpoint; cần liên kết timestamp, PID, command và giai đoạn đang thực hiện.

## 7. Quy trình xác nhận checkpoint thành công

Có thể dùng quy trình sau để ghi nhận một lần checkpoint:

### Bước 1: Ghi lại thông tin lần chạy

Lưu phiên bản JDK, command line, PID, đường dẫn checkpoint, phiên bản ứng dụng, thông tin kernel/CRIU và cấu hình container nếu có. Dùng đúng `jcmd` đi kèm JDK đang chạy ứng dụng.

```bash
java -version
jcmd -l
```

### Bước 2: Gửi yêu cầu checkpoint

```bash
jcmd <pid> JDK.checkpoint
```

Lưu lại toàn bộ output và exit status của lệnh. Đồng thời lưu log ứng dụng/JVM và log hạ tầng checkpoint trong cùng khoảng thời gian.

### Bước 3: Xác nhận runtime hoàn tất

Đối chiếu output, log callback, log dump và trạng thái tiến trình với tài liệu của bản CRaC đang dùng. Nếu runtime xác nhận checkpoint hoàn tất, ghi nhận kết quả là checkpoint thành công. Việc tiến trình gốc kết thúc có thể là hành vi bình thường của quy trình dump; không tự coi đó là dấu hiệu thất bại.

### Bước 4: Ghi nhận ảnh và bảo vệ dữ liệu

Ghi lại đường dẫn, thời điểm tạo, phiên bản ứng dụng/JDK và metadata do quy trình triển khai quản lý. Không chỉnh sửa các file nội bộ của checkpoint. Kiểm soát quyền truy cập vì ảnh có thể chứa dữ liệu nhạy cảm trong bộ nhớ.

### Bước 5: Kiểm chứng bằng restore

Thực hiện restore trong môi trường tương thích và xác nhận cả hai mức:

- JVM/tiến trình có được khôi phục và tiếp tục hay không.
- Ứng dụng có hoàn tất callback sau restore, kết nối lại tài nguyên và đạt readiness hay không.

Nếu bước này thất bại, giữ nguyên kết quả checkpoint đã được xác nhận và ghi thêm kết quả restore thất bại. Phân loại riêng giúp biết ảnh đã được tạo nhưng chưa thể sử dụng trong môi trường restore đang kiểm tra.

## 8. Quy trình điều tra checkpoint thất bại

Khi checkpoint không hoàn tất, hãy điều tra từ giai đoạn sớm nhất có lỗi:

1. **Xác nhận đúng JVM:** kiểm tra PID, JDK và việc runtime có hỗ trợ lệnh `JDK.checkpoint`.
2. **Kiểm tra callback:** tìm exception từ `beforeCheckpoint` hoặc resource đã đăng ký. Xác định resource cụ thể và điều kiện khiến nó chưa sẵn sàng.
3. **Kiểm tra quyền và storage:** xác nhận user, quyền ghi, dung lượng, filesystem và mount của thư mục đích.
4. **Kiểm tra CRIU/kernel:** đọc log dump để tìm syscall, capability, namespace hoặc resource bị từ chối.
5. **Kiểm tra container:** xác nhận process namespace, capability, security profile và cấu hình runtime cho phép checkpoint.
6. **Thử lại có kiểm soát:** sau khi sửa nguyên nhân, tạo checkpoint vào thư mục đích mới hoặc đã được dọn theo hướng dẫn runtime; lưu lại log của lần thử mới.

Nếu lỗi đến từ callback ứng dụng, tăng quyền hệ điều hành sẽ không giải quyết được nguyên nhân. Nếu log chỉ ra CRIU không thể dump một resource do môi trường, thay đổi logic nghiệp vụ có thể không cần thiết. Hãy dựa vào giai đoạn và thông báo lỗi cụ thể để chọn đúng lớp cần sửa.

## 9. Quy trình điều tra restore thất bại

Khi checkpoint đã được xác nhận nhưng restore không thành công, kiểm tra theo thứ tự:

1. **Đường dẫn và quyền đọc:** JVM restore đang trỏ đúng checkpoint và user có thể đọc đầy đủ dữ liệu cần thiết không?
2. **Ảnh có còn nguyên vẹn:** ảnh có bị xóa một phần, ghi đè, di chuyển không đầy đủ hoặc thay đổi sau khi checkpoint không? Dùng metadata/checksum do quy trình lưu trữ cung cấp nếu có.
3. **Tính tương thích:** JDK, kiến trúc CPU, kernel, CRIU, thư viện native, mount và namespace có đáp ứng yêu cầu của checkpoint không?
4. **Lỗi khôi phục tiến trình:** log CRIU/runtime chỉ ra process, file descriptor, mapping hay tài nguyên hệ điều hành nào không thể dựng lại?
5. **Callback sau restore:** có exception từ `afterRestore` hoặc resource callback nào không?
6. **Readiness và dependency:** database, message broker, DNS, endpoint ngoài, credential hoặc cache có hoạt động trong môi trường restore không?

Một checkpoint được tạo trên máy A không mặc nhiên restore được trên máy B. Tính tương thích phải được xác nhận theo hướng dẫn của bản JDK/CRaC và môi trường cụ thể. Nếu restore trên cùng môi trường thành công nhưng trên môi trường khác thất bại, hãy so sánh các thành phần hệ điều hành và tài nguyên trước khi quy lỗi cho ảnh checkpoint.

## 10. Ghi nhận kết quả trong hệ thống triển khai

Pipeline hoặc script vận hành nên lưu riêng trạng thái checkpoint và restore. Một mô hình trạng thái đơn giản:

| Checkpoint status | Restore status | Ý nghĩa |
| --- | --- | --- |
| `SUCCEEDED` | `NOT_RUN` | Ảnh đã được tạo; chưa kiểm chứng restore |
| `FAILED` | `NOT_RUN` | Không tạo được ảnh; cần điều tra checkpoint |
| `SUCCEEDED` | `SUCCEEDED` | Ảnh được tạo và restore đã được kiểm chứng trong môi trường đã thử |
| `SUCCEEDED` | `FAILED` | Ảnh tạo thành công nhưng lần restore kiểm tra không thành công |
| `UNKNOWN` | `UNKNOWN` | Thiếu log hoặc kết quả chưa đủ để kết luận |

Các nhãn trên là ví dụ cho hệ thống quản lý triển khai, không phải tên trạng thái bắt buộc của CRaC API. Nên bổ sung timestamp, build id, JDK version, checkpoint path, host/runtime identity và mã lỗi để truy vết. Nếu retry, mỗi lần thử nên có định danh riêng để log của các lần chạy không bị trộn lẫn.

Không đánh dấu toàn bộ quy trình là thành công chỉ vì bước checkpoint trả về thành công. Nếu yêu cầu triển khai là “có thể restore và phục vụ traffic”, điều kiện hoàn tất phải bao gồm restore và readiness. Ngược lại, nếu chỉ đang tạo ảnh để lưu trữ, hãy ghi rõ trạng thái là checkpoint thành công nhưng restore chưa được kiểm chứng.

## 11. Ví dụ phân loại tình huống

### Tình huống A: callback từ chối checkpoint

Log cho thấy một resource callback thất bại khi `beforeCheckpoint` đang chạy. Runtime không tiếp tục tạo ảnh.

**Phân loại:** checkpoint thất bại ở bước chuẩn bị tài nguyên.

**Hướng xử lý:** xác định resource, sửa callback hoặc trạng thái ứng dụng, rồi thực hiện lại checkpoint. Không cần điều tra restore vì chưa có ảnh được xác nhận.

### Tình huống B: dump tiến trình lỗi do môi trường

Callback chuẩn bị đã hoàn tất, nhưng log CRIU báo thiếu quyền hoặc không thể xử lý một namespace. Thư mục đích có thể đã xuất hiện một số file.

**Phân loại:** checkpoint thất bại trong giai đoạn dump. Dữ liệu dở dang không được xem là checkpoint hợp lệ.

**Hướng xử lý:** kiểm tra capability, namespace, kernel, security profile, quyền và cấu hình container; sau đó thử lại theo quy trình dọn dẹp của runtime.

### Tình huống C: checkpoint thành công nhưng restore không tương thích

Runtime xác nhận tạo ảnh hoàn tất. Khi restore trên host khác, CRIU hoặc JVM báo không thể dựng lại trạng thái do khác biệt môi trường.

**Phân loại:** checkpoint thành công; restore thất bại trên môi trường thử nghiệm.

**Hướng xử lý:** so sánh JDK, CPU, kernel, CRIU, thư viện native, namespace và mount giữa hai môi trường. Không đổi trạng thái checkpoint ban đầu thành thất bại.

### Tình huống D: JVM restore được nhưng ứng dụng không sẵn sàng

Tiến trình được khôi phục, nhưng callback `afterRestore` không tạo lại được connection pool. JVM vẫn tồn tại nhưng readiness endpoint báo lỗi.

**Phân loại:** tiến trình đã restore; phục hồi ứng dụng thất bại. Theo yêu cầu vận hành, lần restore tổng thể chưa đạt.

**Hướng xử lý:** sửa quy trình tạo lại connection pool, xác thực cấu hình và dependency sau restore, rồi thử lại readiness.

## 12. Kết luận

Checkpoint thành công xác nhận runtime đã tạo xong ảnh trạng thái. Checkpoint thất bại cho biết quá trình chuẩn bị hoặc tạo ảnh không hoàn tất. Restore thất bại là lỗi xảy ra sau đó, khi JVM không thể khôi phục ảnh hoặc ứng dụng không thể tiếp tục hoạt động sau khi khôi phục.

Hãy ghi nhận checkpoint và restore thành hai kết quả riêng, dùng timeline cùng log JVM/CRIU để xác định giai đoạn phát sinh lỗi, và kiểm chứng readiness sau restore khi mục tiêu là đưa ứng dụng trở lại phục vụ traffic. Cách phân loại này giúp tránh xóa nhầm ảnh có thể dùng được, tránh retry sai lớp và rút ngắn thời gian tìm nguyên nhân.
