# Kiểm tra bộ đệm được dùng qua -Xlog:aot

Một file `.aot` tồn tại trên đĩa chưa chứng minh JVM đã nạp và sử dụng nó. Ở chế độ mặc định `AOTMode=auto`, JVM có thể bỏ qua cache không tương thích rồi tiếp tục chạy ứng dụng theo cách thông thường. Vì vậy, ứng dụng vẫn khởi động thành công nhưng không nhận được lợi ích startup/warmup mà nhóm kỳ vọng.

Trên JDK 26, unified logging với `-Xlog:aot` giúp phát hiện lý do cache không được dùng, đặc biệt là các khác biệt giữa lúc tạo cache và lúc chạy production. Khi cần kiểm tra chắc chắn trong staging hoặc CI, kết hợp log với `-XX:AOTMode=on`: JVM phải nạp cache và sẽ dừng nếu không thể dùng. Sau khi xác nhận cấu hình, production thường quay lại `auto` để ứng dụng vẫn khởi động nếu cache gặp sự cố.

## 1. Vai trò của -Xlog:aot

`-Xlog:aot` bật log của thành phần AOT trong HotSpot bằng unified logging. Đây là tùy chọn chẩn đoán ở runtime, không phải tùy chọn bật AOT và không tự làm cho cache được sử dụng.

Log giúp trả lời những câu hỏi như:

- JVM có gặp vấn đề khi nạp AOT cache hay không?
- Cache có khác cấu hình runtime ở thuộc tính module hoặc tùy chọn JVM nào không?
- Tại sao archived module graph hoặc một phần tối ưu AOT không thể dùng?
- Có cần tạo lại cache với JDK, ứng dụng hoặc cấu hình runtime hiện tại không?

Ví dụ chạy ứng dụng với cache và ghi log ra file:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot:file=aot.log:time,uptime,level,tags -jar app.jar
```

Các phần của `-Xlog` trong ví dụ:

| Thành phần | Ý nghĩa |
|---|---|
| `aot` | Chọn log tag AOT ở mức `info` mặc định |
| `file=aot.log` | Ghi log vào file thay vì chỉ xuất ra console |
| `time,uptime,level,tags` | Ghi thời gian thực, thời gian JVM đã chạy, mức log và tag |

Nếu chỉ muốn xem nhanh trong terminal, dùng:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot -jar app.jar
```

`-Xlog:help` hiển thị cú pháp, các tag và mức log có trong chính JDK đang chạy. Khi cần tăng chi tiết, hãy kiểm tra tag khả dụng trước khi chọn mức `debug` hoặc `trace`; log quá chi tiết có thể tạo nhiều dữ liệu và làm tăng chi phí ghi log.

## 2. Phân biệt log AOT với trạng thái AOTMode

Trên JDK 26, `AOTMode` có các giá trị `auto`, `off`, `record`, `create` và `on`:

| Chế độ | Vai trò | Cache có được đọc khi chạy ứng dụng không? |
|---|---|---|
| `auto` | Chế độ mặc định; tự chọn theo cache và tham số được cung cấp | Có nếu cache hợp lệ; nếu không, JVM chuyển sang chạy không dùng cache |
| `on` | Chạy production và yêu cầu nạp cache | Có; nếu không nạp được thì JVM báo lỗi và thoát |
| `off` | Tắt AOT cache | Không |
| `record` | Chạy workload training để ghi dữ liệu cấu hình AOT | Không phải chế độ production nạp cache để tăng tốc |
| `create` | Dùng file cấu hình training để tạo cache | Ghi cache; không chạy workload ứng dụng trong pha assembly |

Trong `auto`, nếu chỉ định `-XX:AOTCache=app.aot` và cache không thể nạp, JVM vẫn có thể khởi động ứng dụng mà không dùng cache. Vì thế, log không có lỗi rõ ràng hoặc tiến trình trả về thành công không đủ để chứng minh cache đã được dùng.

Trong `on`, cache được yêu cầu phải nạp được. Đây là cách kiểm tra fail-fast phù hợp cho staging/CI. Luôn chỉ định rõ `-XX:AOTCache=app.aot`; nếu bỏ đường dẫn cache, JDK 26 có thể thử dùng default CDS archive trong JDK installation, khiến phép kiểm tra không còn nhắm tới file `.aot` của ứng dụng.

## 3. Quy trình kiểm tra cache trong thực tế

### Bước 1: xác nhận file cache và runtime

Trước khi đọc log, xác nhận JVM đang dùng đúng JDK và đúng file cache:

```bash
java -version
```

Trên PowerShell, có thể kiểm tra file:

```powershell
Test-Path .\app.aot
Get-Item .\app.aot | Select-Object FullName, Length, LastWriteTime
```

Nếu file không tồn tại, không đọc được hoặc có kích thước bằng 0, cần xử lý đường dẫn/quyền truy cập hoặc tạo lại cache trước. Việc `Test-Path` trả `True` chỉ xác nhận file hiện diện, không xác nhận nội dung hợp lệ.

### Bước 2: chạy với auto và bật log AOT

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot:file=aot.log:time,uptime,level,tags -jar app.jar
```

Sau khi ứng dụng khởi động, đọc `aot.log`. Nếu log nêu mismatch hoặc không thể ánh xạ shared spaces, hãy xử lý nguyên nhân trước khi kết luận cache có hiệu lực. Nếu không thấy thông báo lỗi, chuyển sang bước kiểm tra chi tiết và fail-fast; không lấy việc ứng dụng chạy thành công làm bằng chứng duy nhất.

### Bước 3: xem thêm thông tin về class path

Khi cần quan sát lớp nào được nạp từ cache hoặc điều tra khác biệt đường dẫn lớp, thêm tag `class+path`:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot,class+path=info:file=aot-detail.log:time,uptime,level,tags -jar app.jar
```

`-Xlog:aot,class+path=info` là cấu hình hữu ích để theo dõi nội dung lớp liên quan đến cache. Log lớp giúp nhận diện classpath/module path và nguồn lớp được nạp; nó không phải bộ đếm tổng số object được khôi phục và cũng không đo trực tiếp mức giảm startup.

### Bước 4: yêu cầu nạp cache bằng on

Khi cấu hình đã sẵn sàng, chạy cùng ứng dụng và cache với chế độ fail-fast:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=on -Xlog:aot:file=aot-check.log:time,uptime,level,tags -jar app.jar
```

Nếu cache không hợp lệ hoặc runtime không tương thích, JVM báo lỗi và thoát thay vì âm thầm tiếp tục mà không có cache. Đây là phép kiểm tra rõ ràng nhất trong quy trình triển khai. Chạy nó trên staging/CI hoặc trong bước xác nhận image; không nên mặc định dùng `on` ở production nếu việc thêm một JVM option từ nền tảng vận hành có thể làm ứng dụng không khởi động.

### Bước 5: trở về auto trong production

Sau khi xác nhận cache bằng `on`, dùng `auto` khi chạy production:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot:file=aot-production.log:time,uptime,level,tags -jar app.jar
```

`auto` cho phép ứng dụng tiếp tục chạy nếu cache bị thiếu hoặc không tương thích. Giữ log AOT ở mức phù hợp để có thể phát hiện khi cache bị bỏ qua sau một lần cập nhật JDK, dependency hoặc cấu hình triển khai.

## 4. Đọc các thông báo mismatch thường gặp

Oracle Java SE 26 launcher guide đưa ví dụ về khác biệt module giữa lúc tạo archive và lúc chạy. Log có thể chứa các dòng như:

```text
[error][aot] Mismatched values for property jdk.module.addmods
[error][aot] runtime jdk.incubator.vector dump time jdk.jconsole
[error][aot] subgraph jdk.internal.module.ArchivedBootLayer cannot be used because full module graph is disabled
```

Ý nghĩa:

- `jdk.module.addmods` ghi nhận các module được thêm bằng `--add-modules` hoặc được thêm ngầm bởi một tùy chọn runtime.
- `runtime ... dump time ...` cho biết giá trị runtime khác giá trị lúc tạo cache (`dump time`).
- `ArchivedBootLayer` là một phần của archived module graph. Khi full module graph không thể dùng, phần tối ưu dựa trên nó bị vô hiệu hóa.

Ví dụ: cache được tạo với `--add-modules jdk.jconsole`, nhưng production lại chạy với `--add-modules jdk.incubator.vector`. Hai cấu hình khác nhau nên archived module graph không thể được sử dụng như lúc training. Hãy đồng bộ danh sách module giữa hai lần chạy hoặc tạo lại cache với đúng module cần có.

Không phải mọi mismatch đều có cùng mức độ ảnh hưởng. Một số khác biệt làm vô hiệu hóa một phần tối ưu module; nếu cache chứa AOT-linked classes và full module graph không còn dùng được, việc nạp shared spaces có thể thất bại hoàn toàn. Hãy đọc toàn bộ log xung quanh thông báo đầu tiên thay vì chỉ tìm một dòng `Mismatched values` rồi kết luận toàn bộ cache chắc chắn bị loại bỏ.

### 4.1. Tùy chọn runtime tự thêm module

Một số tùy chọn có thể làm thay đổi tập module mà không hiển thị trực tiếp dưới dạng `--add-modules` trong script. Ví dụ, bật Flight Recorder bằng `-XX:StartFlightRecording` có thể thêm module `jdk.jfr`; dùng Vector API có thể thêm `jdk.incubator.vector`.

Nếu training không có module nhưng production tự thêm module đó, log có thể báo mismatch `jdk.module.addmods`. Khi một tùy chọn runtime cần thiết cho production, hãy đưa cùng tùy chọn vào training và assembly, sau đó tạo lại cache. Không gỡ một tùy chọn bảo mật/quan sát chỉ để làm log hết lỗi nếu ứng dụng thực sự cần tùy chọn đó.

### 4.2. Thông báo không thể ánh xạ shared spaces

Một log có thể chứa:

```text
[error][aot] AOT cache has aot-linked classes. It cannot be used when archived full module graph is not used.
[error][aot] Unable to map shared spaces
```

Đây là dấu hiệu nghiêm trọng hơn một mismatch module đơn lẻ: cache có các lớp đã liên kết AOT cần archived full module graph, nhưng runtime không thể dùng graph đó và không thể ánh xạ shared spaces. Với `AOTMode=auto`, ứng dụng có thể tiếp tục chạy mà không hưởng lợi từ cache; với `AOTMode=on`, JVM dừng khi không nạp được cache.

Hãy kiểm tra khác biệt module và các tùy chọn làm thay đổi module graph, rồi tạo lại cache bằng cùng cấu hình runtime. Đừng cố khắc phục bằng cách thêm hàng loạt module một cách phỏng đoán; chỉ đồng bộ các module thực sự cần cho ứng dụng.

## 5. Các nhóm nguyên nhân khiến cache không được dùng

| Nhóm nguyên nhân | Dấu hiệu cần tìm | Cách xử lý |
|---|---|---|
| Sai file hoặc quyền truy cập | File không tồn tại, không đọc được, lỗi mở archive | Kiểm tra đường dẫn tuyệt đối/tương đối, quyền đọc, dung lượng và tính toàn vẹn file |
| Khác JDK release | Cache được tạo bằng JDK khác với runtime | Tạo lại cache bằng đúng JDK release sẽ triển khai |
| Khác OS hoặc CPU architecture | Cache được tạo trên hệ điều hành/kiến trúc khác | Tạo cache riêng cho từng nền tảng triển khai |
| Khác ứng dụng hoặc classpath | JAR thay đổi, thêm/bớt dependency, thay module path hoặc nội dung ứng dụng | Tạo cache sau khi dependency được cố định; phát hành cache cùng đúng artifact ứng dụng |
| Khác module graph | `jdk.module.addmods` hoặc thuộc tính module khác giữa dump time và runtime | Đồng bộ các tùy chọn module ở training, assembly và production |
| JVM option không tương thích | Log AOT nêu mismatch hoặc cache không thể dùng | Rà soát JVM options, JVMTI agent và công cụ instrumentation; xác định option nào thực sự cần |
| Cache cũ hoặc hỏng | Cache không đọc được hoặc không khớp trạng thái ứng dụng hiện tại | Tạo lại cache từ build hiện tại, không tái sử dụng artifact cũ |

Oracle launcher guide nêu ba ràng buộc cơ bản của cache: ứng dụng, JDK release, OS và CPU architecture. Tài liệu AOT của OpenJDK cũng khuyến nghị training và production phải nhất quán, bao gồm JAR, classpath và workload đại diện. Một cache tạo trước khi cập nhật dependency không nên được dùng cho build mới.

Một số tùy chọn module như `--upgrade-module-path`, `--patch-module` và `--limit-modules` làm CDS bị vô hiệu hóa. Nếu AOT cache được tạo với AOT class linking, các thay đổi làm archived module graph không còn khả dụng có thể khiến cache không thể nạp. Dùng `-Xlog:aot` để xác nhận tình huống cụ thể trên JDK đang chạy.

## 6. Mức log và cách lưu log có kiểm soát

`-Xlog` sử dụng cú pháp chung của unified logging:

```text
-Xlog:<tag-selection>:<output>:<decorators>:<output-options>
```

Ví dụ ghi log AOT và xoay file khi log tăng lớn:

```bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot:file=aot.log:time,uptime,level,tags:filecount=5,filesize=10M -jar app.jar
```

`filecount=5` giữ tối đa năm file log xoay vòng; `filesize=10M` đặt ngưỡng xoay xấp xỉ 10 MB. Kích thước thực tế không được bảo đảm chính xác tuyệt đối. Khi chạy container, đặt file log ở volume hoặc hệ thống thu thập log mà tiến trình có quyền ghi.

Để xác nhận tag và cú pháp trên runtime thực tế:

```bash
java -Xlog:help
```

Không dùng log `debug` hoặc `trace` liên tục trên production nếu chưa đánh giá lượng log và chi phí I/O. Bật mức chi tiết trong một cửa sổ chẩn đoán, tái hiện startup cần kiểm tra, lưu log rồi trả cấu hình về mức phù hợp.

## 7. Kết hợp log với phép đo startup

Log trả lời câu hỏi về khả năng nạp cache; benchmark trả lời câu hỏi cache có giúp ứng dụng nhanh hơn hay không. Hai việc này không thay thế nhau.

Một quy trình đo nên có ba lần chạy trên cùng máy và cùng điều kiện:

1. **Baseline:** chạy ứng dụng không chỉ định AOT cache hoặc dùng `-XX:AOTMode=off`.
2. **Cache bắt buộc:** chạy với `-XX:AOTMode=on` để xác nhận cache nạp được và đo startup khi cache được yêu cầu.
3. **Production mode:** chạy với `-XX:AOTMode=auto` để kiểm tra cấu hình vận hành thực tế.

Đo thời gian đến khi ứng dụng thực sự sẵn sàng nhận request, không chỉ thời gian tiến trình xuất hiện. Lặp lại nhiều lần, phân biệt cold start và warm start của filesystem page cache, so sánh median và percentile. Giữ nguyên CPU quota, memory limit, JDK patch, OS, classpath và workload.

Nếu log xác nhận cache nạp được nhưng startup không cải thiện, hãy xem lại độ bao phủ workload training, loại artifact đã được cache, thời gian materialize object và chi phí I/O. Một cache hợp lệ không có nghĩa workload training đã bao phủ đúng các đường chạy quan trọng.

## 8. Quy trình vận hành khuyến nghị

- **Trong CI:** sau khi tạo cache, chạy ứng dụng với `AOTMode=on` và `-Xlog:aot`; build chỉ đạt khi cache nạp được trên đúng runtime image mục tiêu.
- **Trong staging:** bật `-Xlog:aot,class+path=info`, chạy smoke test và kiểm tra log mismatch trước khi phát hành.
- **Trong production:** dùng `AOTMode=auto`; giữ log AOT ở mức đủ để phát hiện cache bị bỏ qua, đồng thời thu thập startup metrics.
- **Khi cập nhật dependency hoặc JDK:** tạo cache mới cùng artifact mới; không dùng cache từ build trước.
- **Khi đổi OS/CPU:** tạo cache riêng cho nền tảng mới và kiểm tra bằng `on` trước khi triển khai.
- **Khi bật thêm agent hoặc module:** đưa các tùy chọn cần thiết vào training/assembly rồi tạo lại cache; dùng log để xác nhận module graph không bị mismatch.
- **Khi điều tra sự cố:** lưu command line thực tế, `java -version`, cache path, `aot.log` và thông tin classpath/module path để tái hiện chính xác.

## 9. Phân biệt trạng thái sử dụng và trạng thái cache tốt

| Quan sát | Có thể kết luận gì? | Chưa thể kết luận gì? |
|---|---|---|
| File `.aot` tồn tại | File đang có trên filesystem | Cache hợp lệ hoặc đã được JVM nạp |
| Ứng dụng khởi động thành công ở `auto` | Ứng dụng chạy được | Cache đã được dùng; JVM có thể đã fallback |
| `-Xlog:aot` không có lỗi | Không thấy lỗi AOT được log ở mức/tag đã bật | Toàn bộ object/class trong cache đã được dùng |
| `-Xlog:aot,class+path=info` cho thấy lớp liên quan cache | Có thêm bằng chứng về class loading và cache | Số lượng object được phục hồi hoặc mức tăng tốc thực tế |
| `AOTMode=on` chạy thành công với cache chỉ định | JVM đã đáp ứng yêu cầu nạp cache trong lần chạy kiểm tra | Workload training đã tối ưu đủ các đường nghiệp vụ |
| Startup benchmark tốt hơn baseline | Cache có lợi trong workload và môi trường đã đo | Mọi môi trường production đều đạt mức cải thiện tương tự |

`-Xlog:aot` là công cụ chẩn đoán tương thích, không phải bảng điều khiển hiệu năng. Dùng `AOTMode=on` để kiểm tra khả năng nạp, log class path để hiểu thêm việc nạp lớp, rồi dùng benchmark để đo lợi ích thực tế.

## 10. Lưu ý phiên bản JDK

Các lệnh trong bài nhắm tới **JDK 26**. Trong JDK 26, chế độ fail-fast có tên `-XX:AOTMode=on`; `auto` là chế độ mặc định và có thể fallback nếu cache không nạp được. Tùy chọn, thông báo log và hành vi AOT có thể thay đổi ở JDK sau. Không sao chép nguyên lệnh hoặc suy luận trạng thái từ tài liệu của JDK mới hơn mà chưa kiểm tra `java --help`/launcher guide của release đang chạy.

JEP 516 đưa AOT object caching sang định dạng GC-agnostic trong JDK 26, cho phép các tối ưu object cache hoạt động với các garbage collector như ZGC. Tuy nhiên, tính tương thích của AOT cache vẫn gắn với ứng dụng, JDK release, OS và CPU architecture; “any GC” không có nghĩa một file cache dùng được cho mọi ứng dụng, mọi JDK hoặc mọi nền tảng.

## Tài liệu tham khảo

- [Java SE 26 `java` Launcher: Ahead-of-Time Cache và `-Xlog:aot`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java SE 26 `java` Launcher: Unified Logging Framework](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [JEP 516: Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
- [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483)
- [Inside Java: Run Into the New Year with Java's Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/)
- [Quarkus: Ahead-of-time (AOT) caching – diagnostics with `-Xlog:aot`](https://quarkus.io/guides/aot/)
