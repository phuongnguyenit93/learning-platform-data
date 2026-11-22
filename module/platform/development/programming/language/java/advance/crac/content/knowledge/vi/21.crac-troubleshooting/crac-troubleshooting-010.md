# Phân biệt lệnh yêu cầu checkpoint báo thành công với ảnh thực sự hợp lệ

Khi tạo checkpoint CRaC, một thông báo như `Command executed successfully` từ `jcmd` rất dễ bị hiểu nhầm là JVM đã tạo được ảnh hoàn chỉnh. Hai điều đó không giống nhau. Lệnh `jcmd` gửi yêu cầu tới JVM; ảnh checkpoint chỉ đáng tin khi quá trình chuẩn bị resource và thao tác checkpoint native đã hoàn tất, các file ảnh được ghi đầy đủ, artifact không bị thay đổi hoặc thiếu file, và một tiến trình mới có thể restore rồi hoạt động đúng.

Đây là điểm chẩn đoán quan trọng: trong implementation `jcmd` hiện được tài liệu CRaC mô tả, output của `JDK.checkpoint` luôn báo thành công; nếu checkpoint gặp lỗi, thông tin được ghi ở console của ứng dụng. Vì vậy, không thể dùng riêng output hoặc exit code của `jcmd` làm tiêu chí publish checkpoint.

Hãy đánh giá theo nhiều lớp bằng chứng: **yêu cầu đã được gửi đúng JVM, callback đã chạy thành công, engine đã tạo artifact, artifact đã được kiểm tra tính toàn vẹn, và restore smoke test đã qua**. Mỗi lớp trả lời một câu hỏi khác nhau.

## 1. Phân biệt năm mức độ thành công

Một checkpoint pipeline nên phân biệt rõ các trạng thái sau:

| Mức | Điều đã xảy ra | Điều chưa được chứng minh |
|---|---|---|
| 1. Request accepted | `jcmd` hoặc API đã gửi yêu cầu checkpoint tới JVM | Callback có hoàn tất hay engine có ghi được ảnh không |
| 2. Resource preparation passed | `beforeCheckpoint(...)` đã chạy và không báo lỗi | Native checkpoint engine có tạo đủ image file không |
| 3. Image creation completed | Engine đã ghi ảnh và thao tác checkpoint kết thúc theo runtime | Artifact có đầy đủ, không bị hỏng khi copy và có thể restore ở môi trường đích không |
| 4. Artifact integrity passed | Thư mục/file tồn tại, metadata và checksum khớp | Ảnh có tương thích với kernel, CPU, JDK và resource ở nơi restore không |
| 5. Restore test passed | Một tiến trình mới restore được, chạy `afterRestore` và vượt qua health/smoke test | Mọi host, mọi cấu hình hoặc mọi workload tương lai đều chắc chắn hoạt động |

Chỉ mức 5 mới cung cấp bằng chứng trực tiếp rằng artifact đã được thử restore trong môi trường cụ thể. Ngay cả khi restore test thành công, phạm vi kết luận vẫn phải gắn với JDK build, OS/kernel, CPU, container runtime, cấu hình và dependency đã được kiểm thử.

## 2. Vì sao `jcmd` có thể báo thành công khi checkpoint thất bại?

Với quy trình thường gặp, JVM được khởi chạy cùng `-XX:CRaCCheckpointTo=PATH`, sau đó một terminal khác gửi lệnh:

```bash
jcmd <pid> JDK.checkpoint
```

Output có thể trông như sau:

```text
1563568:
Command executed successfully
```

Trong implementation mà tài liệu CRaC hiện mô tả, `jcmd` luôn báo thành công ở output này. Lý do là thông báo đó không phải kết quả kiểm chứng cuối cùng của toàn bộ quá trình native checkpoint. Lỗi thực tế có thể xuất hiện trong console của JVM đích, bao gồm lỗi callback, file descriptor còn mở hoặc lỗi từ checkpoint engine.

Do đó, hãy hiểu output này là xác nhận ở tầng công cụ rằng diagnostic command đã được xử lý theo cơ chế attach, không phải chứng nhận ảnh đã được tạo hợp lệ. Nếu dùng vendor JDK hoặc build khác, kiểm tra tài liệu của chính build đó vì cách báo lỗi có thể thay đổi theo phiên bản.

### Kiểm tra đúng JVM trước khi gửi lệnh

Một lỗi chẩn đoán cơ bản là gửi lệnh tới sai PID hoặc sai JVM. Trước khi yêu cầu checkpoint, xác định process và command line:

```bash
jcmd -l
jcmd <pid> VM.command_line
```

Xác nhận:

- PID thuộc đúng ứng dụng cần checkpoint.
- Process chạy bằng đúng JDK CRaC đã chọn.
- JVM được khởi chạy với `-XX:CRaCCheckpointTo` trỏ tới đúng thư mục output.
- Không nhầm một process test, sidecar hoặc JVM quản trị với process ứng dụng.
- User chạy `jcmd` có quyền attach vào JVM đích.

Sau đó mới gửi yêu cầu:

```bash
jcmd <pid> JDK.checkpoint
```

Nếu dùng API trong ứng dụng, lời gọi `Core.checkpointRestore()` là một đường kích hoạt khác. API có thể đưa lỗi checkpoint về caller dưới dạng exception theo hợp đồng của runtime; vẫn cần kiểm tra log và artifact thay vì bỏ qua bằng chứng ở các bước sau.

## 3. Bật log của ứng dụng và đọc lỗi từ đúng nơi

Khi checkpoint thất bại, console của JVM đích thường là nơi đầu tiên cho biết nguyên nhân. Không chỉ xem terminal đang chạy `jcmd`.

Một callback CRaC có thể phát hiện resource chưa được chuẩn bị:

```text
Exception in thread "main" jdk.crac.CheckpointException
    at jdk.crac.Core.checkpointRestore(...)
Suppressed: jdk.crac.impl.CheckpointOpenSocketException: ...
```

Các lỗi thường gặp gồm:

- `CheckpointOpenSocketException`: socket vẫn mở khi checkpoint bắt đầu.
- `CheckpointOpenFileException`: file descriptor chưa được đóng hoặc xử lý theo policy.
- Exception từ `beforeCheckpoint(...)`: ứng dụng không drain được task, không flush được dữ liệu hoặc không thể đưa resource về trạng thái an toàn.
- Lỗi native checkpoint: engine không thể lưu một phần process state, không đủ quyền hoặc kernel không hỗ trợ một tính năng cần thiết.
- Lỗi filesystem: không thể ghi file ảnh, hết dung lượng hoặc thiếu quyền ở checkpoint directory.

Nếu cần tìm nguồn file descriptor, một số CRaC build hỗ trợ:

```bash
java -Djdk.crac.collect-fd-stacktraces=true \
     -XX:CRaCCheckpointTo=/var/tmp/app-checkpoint \
     -jar app.jar
```

Option này yêu cầu JVM thu thập stack trace cho descriptor liên quan, giúp lần ra code đã mở resource. Xác nhận option có trong JDK build đang dùng.

Không tắt log hoặc đóng logging system quá sớm trong `beforeCheckpoint`. Nếu log bị dừng trước khi engine ghi lỗi, nhóm vận hành có thể chỉ nhìn thấy thông báo `jcmd` chung chung. Hãy giữ một output an toàn cho diagnostic, flush log quan trọng và kiểm tra cả stdout/stderr lẫn file log.

## 4. Kiểm tra checkpoint directory sau khi lệnh chạy

`-XX:CRaCCheckpointTo=PATH` chỉ định nơi runtime ghi image. Trong implementation được tài liệu CRaC mô tả, image thường là một directory chứa nhiều file; directory có thể được tạo nếu chưa tồn tại, nhưng các thư mục cha chưa tồn tại sẽ không tự được tạo.

Trước khi chạy, tạo parent directory và dùng một output path mới cho từng lần thử:

```bash
mkdir -p /var/tmp/crac-runs
CHECKPOINT_DIR=/var/tmp/crac-runs/orders-2026-11-13-attempt-01
mkdir "$CHECKPOINT_DIR"
```

Sau khi checkpoint attempt kết thúc, xem directory:

```bash
find "$CHECKPOINT_DIR" -type f -printf '%p %s bytes\n'
du -sh "$CHECKPOINT_DIR"
```

Hãy kiểm tra:

- Directory thuộc đúng attempt hiện tại, không phải ảnh cũ từ lần chạy trước.
- Có các file ảnh/metadata mà engine và version đang dùng tạo ra.
- Các file có kích thước hợp lý và không phải file rỗng bất thường.
- Tổng kích thước không bằng 0 và phù hợp với quy mô process dự kiến.
- Không có lỗi ghi file hoặc thông báo checkpoint thất bại trong log.
- Không có process/engine nào vẫn đang ghi vào directory khi bạn bắt đầu copy hoặc publish.

Không hardcode một danh sách tên file duy nhất cho mọi runtime. Cấu trúc checkpoint phụ thuộc engine, version và cấu hình. Tài liệu CRaC mô tả image dạng directory có nhiều file; hãy dùng cấu trúc thực tế của build và engine đang chạy.

### Vì sao directory tồn tại vẫn chưa đủ?

Directory có thể được tạo ngay khi JVM khởi động với `-XX:CRaCCheckpointTo`, trước khi có checkpoint thành công. Một checkpoint thất bại giữa chừng cũng có thể để lại file hoặc directory một phần. Vì vậy:

- Directory tồn tại không chứng minh checkpoint hoàn tất.
- Có một vài file không chứng minh toàn bộ image đã được ghi.
- File có kích thước lớn không chứng minh metadata và các file liên quan nhất quán.
- Directory cũ có thể làm pipeline tưởng nhầm lần chạy mới đã thành công.

Dùng path mới cho mỗi attempt và chỉ đánh dấu artifact ready sau khi có bằng chứng hoàn tất cùng restore test. Không dùng một directory dùng chung rồi chỉ kiểm tra `test -d`.

## 5. Đọc log của checkpoint engine

Nếu dùng CRIU engine, thư mục image có thể chứa log native như `dump4.log` tùy build/cấu hình. Khi checkpoint thất bại, log này có thể cho biết bước dump nào lỗi và resource hệ điều hành nào không thể lưu.

Ví dụ kiểm tra log nếu file được tạo:

```bash
test -f "$CHECKPOINT_DIR/dump4.log" && \
  tail -n 200 "$CHECKPOINT_DIR/dump4.log"
```

Tên file và mức độ chi tiết phụ thuộc engine. Không phải mọi CRaC engine đều dùng CRIU hoặc tạo `dump4.log`; nếu không có file này, kiểm tra tài liệu của engine đang chạy và log do runtime xuất ra.

Khi log cho thấy lỗi native checkpoint, kiểm tra lần lượt:

1. CRIU/checkpoint engine có đúng version và nằm trong runtime mong đợi không?
2. Executable/helper cần thiết có ownership, permission hoặc SUID đúng theo tài liệu vendor không?
3. Container có capability, namespace và security profile cho phép checkpoint không?
4. Filesystem đích có đủ dung lượng, quyền ghi và hỗ trợ các thao tác cần thiết không?
5. Kernel có hỗ trợ tính năng mà process/resource đang sử dụng không?
6. Process có giữ socket, file, pipe, device hoặc native resource không thể checkpoint không?

Không thay đổi quyền hệ thống một cách tùy tiện chỉ để làm lệnh chạy qua. Đối chiếu yêu cầu bảo mật và hướng dẫn của đúng runtime/engine, đặc biệt khi chạy trong container.

## 6. Phân biệt kiểm tra môi trường CRIU với kiểm tra ảnh

Lệnh:

```bash
criu check
```

kiểm tra các tính năng kernel mà CRIU cần để dump/restore process. Output `Looks good.` cho biết kernel đáp ứng nhóm tính năng mà lệnh kiểm tra; nó không mở một checkpoint directory cụ thể để chứng minh ảnh đó đầy đủ hoặc restore được.

Một process cụ thể có thể dùng thêm tài nguyên cần tính năng kernel khác. Vì vậy, môi trường qua `criu check` vẫn có thể gặp lỗi khi checkpoint một ứng dụng dùng AIO, TUN device, namespace hoặc loại resource đặc thù.

Nếu có `crit`, công cụ này có thể đọc/hiển thị một số metadata và thống kê image CRIU, chẳng hạn process, file descriptor hoặc memory mapping. Đây là thông tin hỗ trợ điều tra cấu trúc image, không thay thế một lần restore thật. Khả năng và cú pháp của công cụ phụ thuộc phiên bản CRIU/CRIT.

| Công cụ/bằng chứng | Câu hỏi trả lời được | Không chứng minh được |
|---|---|---|
| `jcmd ... JDK.checkpoint` | Đã gửi yêu cầu tới JVM nào? | Image đã hoàn chỉnh hay restore được không |
| Application console/log | Callback và runtime đã báo lỗi gì? | Toàn bộ image chắc chắn hợp lệ không |
| Kiểm tra file trong directory | Có file artifact nào được ghi, kích thước ra sao? | Các file liên kết có nhất quán và restore được không |
| `criu check` | Kernel hiện tại có các tính năng CRIU cơ bản được kiểm tra không? | Checkpoint artifact cụ thể hợp lệ không |
| `crit` inspect | Metadata/thống kê image đọc được tới đâu? | Tiến trình sẽ restore và chạy đúng không |
| Checksum | Bytes hiện tại có khớp bytes đã ghi nhận không? | Nội dung bytes đó có phải checkpoint hợp lệ không |
| Restore smoke test | Runtime có đọc ảnh, phục hồi process và chạy qua kịch bản test không? | Mọi host/workload tương lai đều tương thích không |

## 7. Kiểm tra tính toàn vẹn trước khi phân phối artifact

Khi checkpoint đã hoàn tất và engine không còn ghi vào output directory, tạo một gói artifact bất biến hoặc checksum cho toàn bộ file. Với directory nhiều file, checksum của một file đơn lẻ không đại diện cho cả ảnh.

Ví dụ tạo manifest checksum trên Linux:

```bash
cd "$CHECKPOINT_DIR"
find . -type f ! -name CHECKSUMS.sha256 -print0 | sort -z | \
  xargs -0 sha256sum > CHECKSUMS.sha256
```

Khi đóng gói, giữ cấu trúc thư mục và metadata file cần thiết:

```bash
tar -cpf checkpoint.tar -C "$(dirname "$CHECKPOINT_DIR")" \
  "$(basename "$CHECKPOINT_DIR")"
sha256sum checkpoint.tar > checkpoint.tar.sha256
```

Ở nơi nhận, kiểm tra checksum trước khi giải nén/restore:

```bash
sha256sum -c checkpoint.tar.sha256
```

Checksum chỉ xác nhận bytes không bị thay đổi so với manifest checksum. Nó không xác nhận checkpoint được tạo thành công, không kiểm tra compatibility và không thay thế restore test. Nếu checksum được lưu cùng artifact trong cùng một nơi không đáng tin cậy, nó cũng không tự chứng minh nguồn gốc; dùng chữ ký hoặc provenance attestation nếu cần xác minh artifact do pipeline tin cậy tạo ra.

Không sửa, đổi tên hoặc loại bỏ file bên trong checkpoint sau khi checksum được tạo. Nếu cần đóng gói lại, tạo checksum mới cho gói cuối cùng và lưu quan hệ giữa gói với release manifest.

## 8. Restore là phép kiểm tra trực tiếp nhất

Một ảnh chỉ được chứng minh có thể restore khi runtime thực sự khởi chạy từ ảnh đó. Dùng đúng JDK/runtime và một môi trường tương thích với nơi sẽ triển khai.

Ví dụ:

```bash
java -XX:CRaCRestoreFrom=/var/tmp/crac-runs/orders-2026-11-13-attempt-01
```

Option restore thay thế đường khởi tạo JVM thông thường bằng trạng thái process được lưu trong checkpoint theo runtime. Cách gọi chính xác, option engine và yêu cầu giữ image gốc phụ thuộc JDK/engine/vendor; hãy dùng tài liệu của build đã tạo ảnh.

Khi restore test, xác nhận:

1. JVM không báo lỗi đọc image hoặc metadata.
2. Runtime khôi phục process và thực thi `afterRestore(...)`.
3. Các resource được tạo lại: database pool, socket/listener, client, scheduler và exporter nếu ứng dụng dùng chúng.
4. Ứng dụng nạp đúng cấu hình/secret của môi trường kiểm thử restore.
5. Readiness chỉ chuyển sang accepting sau khi dependency bắt buộc đã khỏe.
6. Một request smoke test đi qua đường nghiệp vụ thật và nhận kết quả mong đợi.
7. Log không có lỗi muộn, thread treo hoặc resource stale sau request đầu tiên.

Nếu restore process khởi chạy được nhưng `afterRestore` thất bại, image có thể đọc được nhưng ứng dụng chưa thể phục vụ. Nếu callback hoàn tất nhưng request đầu tiên thất bại do pool/socket/cache cũ, artifact vẫn chưa đạt điều kiện phát hành.

### Chạy restore test trong môi trường cô lập

Restore có thể tiếp tục một process mang theo identity, consumer, scheduler hoặc trạng thái đã có trước checkpoint. Không thử restore một bản sao của checkpoint production vào cùng mạng production mà không kiểm soát side effect. Dùng môi trường canary/test, dependency cô lập, instance ID riêng và endpoint không gửi thông điệp hoặc giao dịch thật.

Một restore test tốt nên kiểm tra cả khả năng phục hồi và hành vi ứng dụng sau phục hồi, nhưng không gây trùng job, message consumer hoặc lease với instance đang phục vụ.

## 9. Ma trận bằng chứng để quyết định artifact có được phát hành không

Pipeline nên lưu kết quả từng lớp thay vì chỉ một cờ `checkpointSuccess`:

| Kiểm tra | Bằng chứng lưu lại | Điều kiện đạt |
|---|---|---|
| Target process | PID, command line, JDK build, checkpoint path | Đúng JVM và đúng output path |
| Request trigger | Lệnh, timestamp, output `jcmd` hoặc API result | Yêu cầu được gửi; không coi đây là kết quả cuối |
| Application callback | Log `beforeCheckpoint`, exception/suppressed exception | Resource preparation hoàn tất, không còn lỗi |
| Native engine | Engine log và exit/result theo runtime | Engine xác nhận thao tác dump hoàn tất |
| Artifact directory | Danh sách file, kích thước, timestamp, tổng dung lượng | Image mới được tạo đầy đủ theo format của engine |
| Integrity | Checksum, manifest, artifact digest | Bytes không bị hỏng hoặc thay đổi khi phân phối |
| Restore | Log restore, callback, exit/result | Process mới khởi chạy từ đúng image |
| Application smoke test | Health/readiness, request mẫu, dependency check | Ứng dụng phục vụ được sau restore |
| Compatibility | JDK, OS/kernel, CPU, engine, container metadata | Nằm trong nhóm môi trường đã kiểm thử |

Một artifact có thể ở trạng thái `CREATED` nhưng chưa `VERIFIED`. Chỉ promotion sang `VERIFIED` hoặc trạng thái tương đương sau khi restore smoke test và kiểm tra ứng dụng đã qua.

## 10. Ví dụ quy trình kiểm tra thủ công

Ví dụ dưới đây minh họa một quy trình trên Linux với CRaC JDK dùng CRIU engine. Thay JDK path, app JAR, PID và directory theo môi trường thật.

### Terminal 1 — Khởi chạy ứng dụng checkpointable

```bash
mkdir -p /var/tmp/crac-runs
CHECKPOINT_DIR=/var/tmp/crac-runs/orders-attempt-01
mkdir "$CHECKPOINT_DIR"

"$JAVA_HOME/bin/java" \
  -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" \
  -jar target/orders-service.jar
```

Chờ ứng dụng khởi động, warm-up và chuyển sang trạng thái chuẩn bị checkpoint. Ghi lại log của process.

### Terminal 2 — Xác định process và gửi yêu cầu

```bash
"$JAVA_HOME/bin/jcmd" -l
"$JAVA_HOME/bin/jcmd" <pid> VM.command_line
"$JAVA_HOME/bin/jcmd" <pid> JDK.checkpoint
```

Output `Command executed successfully` chỉ là tín hiệu ở tầng `jcmd`. Quay lại terminal 1 và đọc log ứng dụng. Chờ runtime/engine kết thúc attempt theo semantics của build.

### Kiểm tra artifact và log

```bash
find "$CHECKPOINT_DIR" -type f -printf '%p %s bytes\n'
du -sh "$CHECKPOINT_DIR"

if [ -f "$CHECKPOINT_DIR/dump4.log" ]; then
  tail -n 200 "$CHECKPOINT_DIR/dump4.log"
fi
```

Đối chiếu kết quả với application log. Nếu có exception hoặc engine error, không publish directory dù nó chứa một số file.

### Restore test

Chạy trên môi trường kiểm thử tương thích:

```bash
"$JAVA_HOME/bin/java" \
  -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

Chờ `afterRestore`, health check và request smoke test. Chỉ sau đó mới tạo gói release, checksum và manifest promotion.

Các command trên là quy trình tham khảo cho build hỗ trợ option tương ứng. Một số vendor/engine có cách lưu trữ, logging, giữ process hoặc restore option khác; luôn đối chiếu tài liệu runtime thực tế.

## 11. Chẩn đoán theo dấu hiệu quan sát được

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `jcmd` báo thành công nhưng không có file ảnh | `jcmd` không phản ánh lỗi native; sai output path; callback/engine thất bại | Đọc console JVM, xác nhận `CRaCCheckpointTo`, xem engine log và timestamp directory |
| Directory tồn tại nhưng rỗng | Directory được tạo lúc startup hoặc checkpoint chưa bắt đầu/đã thất bại | Dùng path mới, xem application log và engine log |
| Directory có một phần file | Checkpoint bị gián đoạn, thiếu dung lượng hoặc lỗi ghi | Không publish; kiểm tra log, disk quota và trạng thái engine |
| Có `CheckpointOpenSocketException` | Listener/client socket còn mở | Tìm resource owner, dừng server/client trong `beforeCheckpoint` |
| Có `CheckpointOpenFileException` | File descriptor chưa đóng hoặc policy không cho phép | Dùng FD stack trace, xác định thư viện sở hữu và lifecycle |
| Có `CheckpointException` với lỗi native | Engine, kernel, privilege hoặc resource native không tương thích | Đọc stack trace, `dump4.log`, permission/capability và kernel support |
| Image đầy đủ nhưng restore báo thiếu CPU feature | Host restore không có tập CPU feature tương thích | Dùng host phù hợp hoặc cấu hình CPU feature theo hướng dẫn runtime |
| Restore báo thiếu file/mapping | Filesystem, mount, binary hoặc native dependency khác môi trường tạo ảnh | So sánh path, mount, permission, image digest và native library |
| Restore thành công nhưng readiness không lên | `afterRestore` hoặc dependency recreation thất bại | Đọc application log, kiểm tra pool, endpoint, credential và resource state |
| Restore được nhưng request đầu tiên lỗi | Cache/client/socket stale hoặc thứ tự readiness sai | Chạy smoke test theo dependency graph, mở traffic sau health check |
| Checksum sai sau khi tải | Artifact hỏng hoặc bị thay đổi khi copy | Tải lại từ nguồn tin cậy, xác minh digest và storage pipeline |

## 12. Những yếu tố làm ảnh không restore được dù file tồn tại

Ảnh có đủ file và checksum đúng vẫn có thể không restore được vì tính toàn vẹn bytes khác với tính tương thích runtime.

### Runtime và hệ điều hành

- JDK vendor/build khi restore khác build tạo ảnh.
- OS library hoặc native ABI đã thay đổi.
- Kernel hoặc checkpoint engine thiếu tính năng cần thiết.
- Container runtime, namespace, cgroup hoặc security profile khác.
- CPU architecture hoặc CPU features không tương thích.

### Filesystem và resource ngoài process

- File, mount hoặc path được lưu trong checkpoint không còn tồn tại.
- Permission/ownership thay đổi.
- Native library hoặc driver không đúng phiên bản.
- Socket/peer, database, broker hoặc service registry không còn ở trạng thái phù hợp.
- Credential hoặc certificate đã hết hạn.

### Trạng thái ứng dụng

- `beforeCheckpoint` không drain hết request/task.
- Background worker còn giữ lock hoặc native resource.
- Cache/static state chứa endpoint hoặc identity của môi trường cũ.
- `afterRestore` không tái tạo client hoặc không cập nhật readiness đúng thứ tự.

Vì thế, kiểm tra image file và checksum là các bước cần thiết nhưng không thay thế restore test trong nhóm môi trường đích.

## 13. Bảo vệ và quản lý checkpoint artifact

Checkpoint có thể chứa heap và native memory của ứng dụng, bao gồm token, password, session, private key, dữ liệu request hoặc cache. Artifact phải được bảo vệ như dữ liệu nhạy cảm.

- Giới hạn quyền đọc checkpoint directory và artifact repository.
- Không publish checkpoint lên registry public.
- Mã hóa khi lưu/truyền theo yêu cầu bảo mật.
- Dùng checksum để phát hiện hỏng dữ liệu và chữ ký/provenance để xác minh nguồn gốc.
- Dùng versioned path riêng cho từng attempt/release.
- Không ghi đè checkpoint đã được xác minh.
- Không copy artifact khi engine vẫn đang ghi.
- Đặt retention và quy trình thu hồi/xóa artifact cũ.
- Không dùng checkpoint của môi trường prepare chứa secret production nếu có thể cấp secret mới sau restore.

Một artifact hợp lệ về kỹ thuật vẫn có thể không được phép phát hành nếu chứa secret hoặc dữ liệu không được phép phân phối. Tính hợp lệ của image và phê duyệt bảo mật là hai điều kiện riêng.

## 14. Tránh các cách kiểm tra dễ tạo kết luận sai

**Chỉ dựa vào `Command executed successfully`.** Output này không chứng minh checkpoint thành công; đọc console của JVM và xác nhận engine output.

**Chỉ kiểm tra exit code của `jcmd`.** Nó không thay thế kết quả checkpoint của JVM/native engine trong implementation được tài liệu mô tả.

**Chỉ kiểm tra checkpoint directory tồn tại.** Directory có thể được tạo trước khi checkpoint hoặc còn lại sau attempt thất bại.

**Chỉ kiểm tra tổng dung lượng lớn.** Kích thước không chứng minh các file liên quan nhất quán hoặc restore được.

**Chạy `criu check` rồi đánh dấu ảnh hợp lệ.** Lệnh này kiểm tra kernel feature support, không xác nhận một image directory cụ thể.

**Tạo checksum rồi bỏ qua restore test.** Checksum chỉ xác nhận bytes không đổi, không xác nhận runtime có thể phục hồi process.

**Restore thử trên máy phát triển khác cấu hình rồi kết luận artifact hỏng.** Trước tiên so sánh JDK, kernel, CPU, filesystem, engine và resource environment; lỗi có thể do host không tương thích.

**Dùng lại directory của lần chạy trước.** File cũ có thể khiến pipeline nhầm một attempt thất bại là checkpoint mới. Dùng path mới và manifest gắn với attempt ID.

## 15. Thiết kế trạng thái pipeline cho checkpoint

Thay vì một biến boolean `success`, có thể dùng trạng thái rõ ràng:

```text
REQUESTED
   |
   v
PREPARING_RESOURCES
   |
   v
ENGINE_WRITING
   |
   v
IMAGE_CREATED
   |
   v
INTEGRITY_VERIFIED
   |
   v
RESTORE_TESTED
   |
   v
APPROVED_FOR_RELEASE
```

Mỗi bước cần lưu timestamp, release ID, process/runtime identity, log reference và artifact digest khi có. Nếu một bước thất bại, chuyển sang `FAILED` hoặc `REJECTED`, giữ lại log phục vụ điều tra và không promote artifact.

Ví dụ manifest kiểm chứng:

```yaml
checkpoint:
  attemptId: orders-2026-11-13-001
  status: RESTORE_TESTED
  applicationImageDigest: sha256:IMAGE_DIGEST
  jdkBuild: crac-jdk-full-build-version
  engine: criuengine
  outputPath: checkpoint/orders-2026-11-13-001
  artifactDigest: sha256:CHECKPOINT_DIGEST
  commandRequestedAt: "2026-11-13T06:00:00Z"
  imageCreatedAt: "2026-11-13T06:00:12Z"
  restoreTest:
    status: PASSED
    environment: approved-linux-node-group
    smokeTest: PASSED
```

Các giá trị là placeholder. Pipeline phải ghi trạng thái từ kết quả thật; không đặt `RESTORE_TESTED` chỉ vì lệnh checkpoint hoặc checksum thành công.

## 16. Checklist phân biệt command success và image validity

### Trước khi gửi lệnh

- [ ] Đã xác nhận đúng PID/JVM và JDK build.
- [ ] JVM có `-XX:CRaCCheckpointTo` trỏ tới output path đúng.
- [ ] Parent directory tồn tại và output path dành riêng cho attempt mới.
- [ ] Process log đang được thu thập và có thể đọc sau khi trigger.
- [ ] Warm-up, drain và resource lifecycle đã được chuẩn bị.

### Sau khi gửi lệnh

- [ ] Không dùng riêng `Command executed successfully` làm kết quả cuối.
- [ ] Đã đọc console/log của JVM đích.
- [ ] Không có `CheckpointException`, suppressed resource exception hoặc native engine error.
- [ ] Engine đã kết thúc thao tác ghi theo semantics của runtime.
- [ ] Checkpoint directory chứa artifact mới, không phải file sót từ lần trước.
- [ ] Các file có kích thước hợp lý và tổng dung lượng phù hợp.
- [ ] Đã xem `dump4.log` hoặc engine log nếu có.

### Trước khi phát hành

- [ ] Artifact được checksum sau khi engine hoàn tất ghi.
- [ ] Checksum được xác minh sau khi copy/tải.
- [ ] Manifest ghép đúng checkpoint với application image/JDK/runtime.
- [ ] Restore test được thực hiện trên môi trường tương thích.
- [ ] `afterRestore` hoàn tất và dependency được tạo lại.
- [ ] Health/readiness và request smoke test thành công.
- [ ] Artifact chỉ được promote sau khi restore test pass.
- [ ] Checkpoint được bảo vệ như artifact có thể chứa dữ liệu nhạy cảm.

## 17. Kết luận

Thông báo `Command executed successfully` từ `jcmd` không phải chứng nhận checkpoint image hợp lệ. Trong implementation được tài liệu CRaC mô tả, `jcmd` có thể luôn báo thành công trong khi lỗi thực tế xuất hiện ở console của JVM. Hãy xác nhận đúng process, đọc application/engine log, kiểm tra checkpoint directory mới, đánh giá file và metadata, tạo checksum sau khi engine ghi xong, rồi restore bằng một tiến trình mới.

`criu check` chỉ kiểm tra khả năng hỗ trợ của kernel; checksum chỉ kiểm tra bytes; directory tồn tại chỉ chứng minh có một path. Bằng chứng mạnh nhất là restore test trên môi trường tương thích, callback phục hồi thành công và ứng dụng vượt qua health cùng smoke test. Chỉ khi đủ các bước đó, checkpoint mới nên được đánh dấu verified và đưa vào release.

## Tài liệu tham khảo

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): mô tả `-XX:CRaCCheckpointTo`, output của `jcmd JDK.checkpoint`, cảnh báo rằng `jcmd` hiện luôn báo thành công và lỗi được ghi ở console ứng dụng, cùng cách restore bằng `-XX:CRaCRestoreFrom`.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): ví dụ `CheckpointException`, lỗi file descriptor/socket, yêu cầu quyền của CRIU engine và vị trí log `dump4.log`.
- [CRIU — Check the kernel](https://criu.org/CLI/cmd/check): giải thích `criu check` kiểm tra các tính năng kernel cần cho CRIU.
- [CRIU — CRIT](https://criu.org/CRIT): mô tả công cụ đọc và hiển thị metadata/thống kê của CRIU image.
- [Azul — Debugging CRaC Failures](https://docs.azul.com/crac/usage/debugging.html): hướng dẫn điều tra lỗi native checkpoint/restore và file descriptor.
