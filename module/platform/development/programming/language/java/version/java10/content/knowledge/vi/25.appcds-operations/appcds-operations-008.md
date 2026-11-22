# Nhật ký CDS để xác minh lớp được nạp từ kho chia sẻ

## 1. Câu hỏi vận hành cần trả lời

Khi bật **Class Data Sharing (CDS)** hoặc **Application Class-Data Sharing (AppCDS)** trong HotSpot JVM, câu hỏi quan trọng không phải chỉ là “có file archive hay chưa?” mà là:

**“Trong lần khởi chạy này, lớp ứng dụng cụ thể có thực sự được nạp từ kho dữ liệu lớp chia sẻ hay vẫn được nạp từ JAR?”**

AppCDS được giới thiệu trong **Java 10** qua **JEP 310**. Đây là cơ chế lưu một phần class metadata đã được chuẩn bị vào archive, để các JVM phù hợp có thể memory-map và dùng lại. Tính năng CDS/AppCDS vẫn được sử dụng trong JDK hiện đại, bên cạnh những khả năng **AOT cache** mới hơn. Bài thuộc chủ đề **Vận hành AppCDS**, tập trung vào **nhật ký CDS để xác minh lớp được nạp từ kho chia sẻ**, không chỉ giải thích lý thuyết archive.

Một số sự thật dễ nhầm:

- Một file `app.jsa` **tồn tại** nhưng chưa chắc runtime **đã dùng nó**.
- JVM **mở/memory-map archive thành công** không chứng minh **mọi lớp ứng dụng** được nạp từ archive đó.
- Các lớp lõi JDK có thể dùng **CDS archive mặc định**, trong khi lớp ứng dụng **vẫn nạp từ JAR**.
- Lần chạy **tạo archive** và lần chạy **sử dụng archive** có thể khác JDK, JAR, classpath, flags hoặc workload.
- Ứng dụng cho stdout đúng **không chứng minh** archive được dùng; CDS là tối ưu hóa, không được đổi kết quả nghiệp vụ.
- Một lần chạy nhanh hơn **không đủ chứng minh** AppCDS hoạt động: còn tác động của filesystem cache, CPU, mạng, framework và JIT.

Để có kết luận đáng tin, chúng ta phối hợp hai nguồn:

1. **`-Xlog:cds`**: thông tin JVM mở, kiểm tra, map archive nào và vì sao có thể dùng hoặc không dùng.
2. **`-Xlog:class+load`**: thông tin **từng lớp** đã load và **source** của lớp đó. Đây là bằng chứng trực tiếp để kiểm tra “lớp X có đến từ shared archive không?”.

Trên các HotSpot/JDK hỗ trợ **AOT cache**, `-Xlog:aot` còn giúp theo dõi cache AOT. Không đồng nhất log AOT với log per-class của AppCDS; cần xem đúng cơ chế và phiên bản JDK đang dùng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **CDS của JDK** và **AppCDS của ứng dụng** khi xem log.
- Đọc được `source: shared objects file`, `source: shared objects file (top)` và `source: file:/.../app.jar`.
- Bật Unified Logging đúng cách bằng `-Xlog:cds=info` và `-Xlog:class+load=info`.
- Tạo JAR, tạo dynamic archive, chạy lại có log rồi so sánh với `-Xshare:off` bằng ví dụ **Java 17+ chạy được**.
- Biết nên kết luận gì khi **thấy/không thấy** tên lớp trong log.
- Phân biệt xác minh **archive được mở**, **archive được map**, **lớp cụ thể được nạp từ archive** và **hiệu năng cải thiện**.
- Chẩn đoán những sai khác do classpath, JDK build, archive, flags, modules và container.
- Giảm độ ồn/log rotation, bảo vệ thông tin đường dẫn nội bộ và ghi báo cáo kỹ thuật có phạm vi.
- Hiểu vai trò của AOT cache từ JDK 24+ và logging hiện đại trên JDK 25+.

## 2. Thang bằng chứng: từ file trên đĩa đến lớp được chia sẻ

Các mức bằng chứng sau **không tương đương**:

~~~text
File demo.jsa đã tồn tại
         |
         v
JVM thử mở demo.jsa
         |
         v
JVM mở và map vùng archive phù hợp
         |
         v
Lớp ứng dụng X được load từ shared archive
         |
         v
Ứng dụng đo được mức tiết kiệm startup/RAM
~~~

| Bằng chứng | Chỉ cho phép kết luận |
| --- | --- |
| `demo.jsa` tồn tại | Có một file archive tại thời điểm kiểm tra. |
| `cds` log nói `Opened archive ...demo.jsa` | JVM đã mở được file archive đó. |
| `cds` log nói các vùng archive đã được map | Một số vùng archive được ánh xạ thành công. |
| `class+load` log cho **lớp X** nói `source: shared objects file (top)` | Lớp X trong lượt chạy này được nạp từ **top/dynamic archive** theo định dạng log HotSpot đó. |
| `class+load` log cho **lớp X** nói `source: shared objects file` | Lớp X được nạp từ shared archive; cần biết đó là base/static archive trong cấu hình cụ thể. |
| `class+load` log cho **lớp X** nói `source: file:/.../app.jar` | Lớp X lấy từ JAR theo đường nạp thông thường trong lượt chạy đó. |
| Một lần chạy nhanh hơn | **Không đủ** để xác nhận nguồn nạp từng lớp hoặc tỷ lệ cải thiện ổn định. |

**Chốt nguyên tắc:** Nếu yêu cầu là **“xác minh lớp X đã dùng kho chia sẻ”**, hãy lấy **sự kiện nạp lớp X** trong `class+load` làm bằng chứng chính. Log `cds` là bằng chứng hỗ trợ về trạng thái archive, không thay thế per-class event.

### 2.1. Vì sao log của lớp `java.*` có thể gây hiểu lầm?

Một JDK hiện đại thường có sẵn archive CDS mặc định. Kết quả như:

~~~text
[info][class,load] java.lang.Object source: shared objects file
[info][class,load] java.lang.String source: shared objects file
~~~

chỉ xác nhận một số **lớp JDK** đến từ shared archive. Nó **không xác nhận** các lớp `com.company.*` hay `demo.*` thuộc ứng dụng đã dùng AppCDS.

Nếu đồng thời có:

~~~text
[info][class,load] com.example.Main source: file:/.../app.jar
~~~

thì `com.example.Main` **đã được nạp từ JAR**, dù các lớp của JDK dùng CDS thành công.

## 3. Unified Logging: cờ hiện hành cần dùng

HotSpot sử dụng **JVM Unified Logging** với cú pháp tổng quát:

~~~text
-Xlog:<tag-selector>=<level>:<output>:<decorators>:<output-options>
~~~

Những phần chính:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| `tag-selector` | Chọn loại thông tin. | `cds`, `class+load`, `aot`. |
| `level` | Độ chi tiết log. | `info`, `debug`, `trace`. |
| `output` | Console hoặc file. | `stdout`, `stderr`, `file=cds.log`. |
| `decorators` | Thời gian, level, tags, v.v. | `uptime,level,tags`. |
| `output-options` | Giới hạn file và xoay vòng. | `filecount=5,filesize=10M`. |

Những lệnh cơ bản:

~~~bash
java -Xlog:cds=info -cp demo.jar CdsLogProof
java -Xlog:class+load=info -cp demo.jar CdsLogProof
~~~

Dùng một lệnh có cả hai log, mỗi nguồn ở file riêng:

~~~bash
java -XX:SharedArchiveFile=demo.jsa -Xlog:cds=info:file=cds-use.log -Xlog:class+load=info:file=class-use.log -cp demo.jar CdsLogProof
~~~

Lưu ý:

- `cds` là tag của hoạt động Class Data Sharing.
- `class+load` là **tổ hợp hai tag** `class` và `load`; dấu cộng có ý nghĩa trong selector.
- Mức `info` phù hợp để xác minh nguồn nạp lớp trong demo.
- `debug` có thể cung cấp chi tiết hơn, nhưng log lớn hơn.
- Không bật `-Xlog:all=trace` lâu dài chỉ để tìm một lớp.
- Những lệnh này áp dụng cho **HotSpot/OpenJDK** với hệ thống log tương ứng, không phải lời cam kết tất cả JVM khác hãng hỗ trợ đúng cú pháp.

### 3.1. Hỏi JVM đang dùng có hỗ trợ tag/level nào

~~~bash
java -Xlog:help
~~~

Lệnh liệt kê tag, level, decorator và output option **thực sự được bản JVM đó hỗ trợ**. Dùng khi triển khai trên JDK/VM không giống máy phát triển.

### 3.2. Đừng dùng các cờ logging cũ đã bị thay thế

Với HotSpot hiện đại, `-Xlog:class+load=info` là lựa chọn thích hợp để theo dõi nạp lớp. Những cờ logging cũ đã được thay bằng Unified Logging có thể không còn được chấp nhận. Bài này **không** dùng cờ đã bị loại bỏ làm giải pháp vận hành.

### 3.3. Hiểu định dạng một dòng log

Một dòng đã quan sát trên JDK 24:

~~~text
[0.036s][info][class,load] CdsLogProof source: shared objects file (top)
~~~

Ý nghĩa:

- `0.036s`: thời gian tính từ lúc JVM bắt đầu; thay đổi giữa các lượt chạy.
- `info`: log level.
- `class,load`: nhóm tags.
- `CdsLogProof`: tên lớp đã được nạp.
- `source: shared objects file (top)`: nguồn lớp là **dynamic/top shared archive** trong thử nghiệm.

**Đừng assert timestamp, thứ tự mọi dòng, địa chỉ bộ nhớ hoặc đường dẫn tuyệt đối** trong kiểm thử đa nền tảng. Tên lớp + nguồn nạp + đúng lượt chạy có giá trị chứng minh cao hơn.

## 4. Cách hiểu ba loại `source` quan trọng

### 4.1. `source: shared objects file`

Ví dụ:

~~~text
java.lang.Object source: shared objects file
~~~

Đây là dấu hiệu lớp được lấy từ một CDS archive. Trong một cấu hình **base + top** của HotSpot, dấu hiệu **không có `(top)`** thường là archive nền/static.

**Không viết rule:** “mọi lớp có `source: shared objects file` đều chỉ là lớp JDK.” Một **static archive do ứng dụng tạo** cũng có thể chứa lớp ứng dụng; khi ấy cần nhìn topology/cấu hình archive để hiểu nguồn. Dấu hiệu chỉ chứng minh **shared archive**.

### 4.2. `source: shared objects file (top)`

Ví dụ:

~~~text
CdsLogProof source: shared objects file (top)
CdsLogProof$Worker source: shared objects file (top)
~~~

Đây là dấu hiệu đặc trưng của **dynamic/top archive** trong JDK 24 được kiểm chứng. Nếu lớp này thuộc JAR demo, đó là **chứng cứ trực tiếp AppCDS cho lớp cụ thể ấy**.

Nhưng không nên suy rộng “mọi JDK và mọi kiểu archive phải có `(top)`”. Static archive chứa lớp ứng dụng có thể cho dạng nguồn khác.

### 4.3. `source: file:/.../demo.jar`

Ví dụ:

~~~text
CdsLogProof source: file:/.../demo.jar
~~~

Điều này có nghĩa lớp được nạp từ file/JAR thông thường trong lượt chạy. **Không phải lỗi chức năng**; JVM vẫn hoàn toàn có thể chạy đúng. Nếu mục tiêu là tối ưu AppCDS cho lớp đó, bạn cần kiểm tra lý do nó không được lấy từ archive.

Các lớp từ module image hoặc class loader tùy chỉnh có thể có source khác; không cứng hóa bộ parser log để coi mọi source ngoài ba nhãn trên là lỗi.

### 4.4. Lớp lambda/generated class có thể làm test mong manh

Nếu chương trình dùng Stream lambda, log có thể chứa một tên dạng:

~~~text
CdsLogProof$$Lambda/... source: shared objects file (top)
~~~

Tên, số thứ tự, hậu tố địa chỉ và nguồn nạp **có thể thay đổi** giữa JDK, VM flags và kiểu tối ưu. Muốn xác minh ổn định hơn, hãy chọn **lớp application tự định nghĩa**, như `CdsLogProof` hoặc `CdsLogProof$Worker`.

## 5. Bài lab Java 17+: nguồn, JAR, archive, log và đối chứng

Đây là một chương trình độc lập, đã **biên dịch và chạy bằng HotSpot JDK 24**. Bài thử tạo dynamic archive, sử dụng archive và đối chứng khi tắt CDS. Ngoài JDK, không cần thư viện phụ.

### 5.1. Tạo `CdsLogProof.java`

~~~java
import java.util.List;

public class CdsLogProof {
    static final class Worker {
        static String label() {
            return "ready";
        }
    }

    public static void main(String[] args) {
        var ids = List.of(2, 3, 5);
        int total = ids.stream()
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println("status=" + Worker.label());
        System.out.println("total=" + total);
    }
}
~~~

Stdout của chương trình khi chạy đúng:

~~~text
status=ready
total=10
~~~

Hai dòng trên phản ánh **logic ứng dụng**, không phải bằng chứng CDN/CDS. Bằng chứng class sharing sẽ nằm trong file log JVM ở các bước sau.

### 5.2. Compile và đóng gói thành JAR

Linux/macOS:

~~~bash
mkdir -p classes
javac -encoding UTF-8 -d classes CdsLogProof.java
jar --create --file demo.jar -C classes .
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory classes -Force | Out-Null
javac -encoding UTF-8 -d classes CdsLogProof.java
jar --create --file demo.jar -C classes .
~~~

Lệnh `javac` tạo class chính và class lồng trong thư mục `classes`. Lệnh `jar` đóng gói chúng vào `demo.jar`.

**Vì sao dùng JAR thay vì `-cp classes`?** Tài liệu CDS hiện hành quy định những giới hạn với classpath/module path khi tạo archive, gồm trường hợp **non-empty directories**. Dùng JAR bất biến giúp demo đơn giản và tránh phụ thuộc vào đường tải lớp không được hỗ trợ trong kịch bản archive cụ thể.

Có thể xem các entry:

~~~bash
jar --list --file demo.jar
~~~

Bạn sẽ thấy các file class, trong đó có `CdsLogProof.class` và `CdsLogProof$Worker.class`.

### 5.3. Chạy bình thường

~~~bash
java -cp demo.jar CdsLogProof
~~~

Stdout:

~~~text
status=ready
total=10
~~~

JDK hiện đại có thể **đã dùng default CDS archive** cho lớp JDK ở bước này; “chạy bình thường” không đồng nghĩa “CDS tắt hoàn toàn”.

### 5.4. Tạo dynamic AppCDS archive

~~~bash
java -XX:ArchiveClassesAtExit=demo.jsa -cp demo.jar CdsLogProof
~~~

Trên JDK hỗ trợ, JVM ghi một **dynamic archive** lúc ứng dụng kết thúc bình thường. Khi dùng base archive mặc định, top archive chỉ cần ghi những lớp phù hợp chưa có trong base.

Kết quả đã kiểm chứng trên JDK 24:

- Exit code `0`.
- File `demo.jsa` được tạo.
- Stdout vẫn là `status=ready`, `total=10`.

**Giới hạn:** File tạo thành công không chứng minh mọi class trong JAR đều được archive. Chỉ các lớp được kích hoạt và đủ điều kiện mới có cơ hội được ghi.

### 5.5. Chạy với archive và bật đúng hai nguồn log

~~~bash
java -XX:SharedArchiveFile=demo.jsa -Xlog:cds=info:file=cds-use.log -Xlog:class+load=info:file=class-use.log -cp demo.jar CdsLogProof
~~~

Chương trình tiếp tục in:

~~~text
status=ready
total=10
~~~

Hai file có vai trò khác nhau:

- `cds-use.log`: xác nhận trạng thái mở/ánh xạ archive.
- `class-use.log`: quan sát source của từng class được load.

**Đừng chạy lại `-XX:ArchiveClassesAtExit` ở bước xác minh rồi cho rằng log training là log production**. Đây là một **lượt runtime riêng** dùng `-XX:SharedArchiveFile`.

### 5.6. Trích log trên Linux/macOS

~~~bash
grep 'CdsLogProof' class-use.log
grep 'java.lang.Object' class-use.log
grep -E 'Opened archive|Mapped' cds-use.log
~~~

Windows PowerShell:

~~~powershell
Select-String -Path class-use.log -Pattern 'CdsLogProof'
Select-String -Path class-use.log -Pattern 'java.lang.Object'
Select-String -Path cds-use.log -Pattern 'Opened archive|Mapped'
~~~

**Trích log thực tế được kiểm chứng trên JDK 24**, bỏ timestamp và đường dẫn máy:

~~~text
[info][class,load] CdsLogProof source: shared objects file (top)
[info][class,load] CdsLogProof$Worker source: shared objects file (top)
[info][class,load] java.lang.Object source: shared objects file
[info][cds] Opened archive .../classes.jsa.
[info][cds] Opened archive .../demo.jsa.
~~~

Các dòng `Opened archive` đến từ `cds-use.log`, còn `source` đến từ `class-use.log`. Chúng không nhất thiết xuất hiện theo thứ tự trên trong file gốc.

Kết luận đúng: **CdsLogProof và Worker đã nạp từ dynamic/top shared archive trong lượt chạy thử nghiệm**, còn `java.lang.Object` đến từ shared archive nền. Các log mapping cho biết JVM mở được các archive liên quan.

### 5.7. Đối chứng với `-Xshare:off`

~~~bash
java -Xshare:off -Xlog:class+load=info:file=class-off.log -cp demo.jar CdsLogProof
~~~

Stdout vẫn là:

~~~text
status=ready
total=10
~~~

Nhưng trong `class-off.log`, kết quả quan sát cho lớp ứng dụng chuyển thành:

~~~text
[info][class,load] CdsLogProof source: file:/.../demo.jar
[info][class,load] CdsLogProof$Worker source: file:/.../demo.jar
~~~

Đó là **đối chứng có ý nghĩa**: cùng JAR và code có output như nhau, trong khi nguồn nạp lớp thay đổi. Không có `-Xshare:off`, việc một app chạy thành công không đủ để kết luận archive hoạt động.

### 5.8. Bảng kết quả kiểm chứng

| Hoạt động | Kết quả JDK 24 thử nghiệm |
| --- | --- |
| Compile bằng `javac` | Thành công. |
| Tạo `demo.jar` | Thành công. |
| Tạo `demo.jsa` với `ArchiveClassesAtExit` | Exit code 0, file tồn tại. |
| Chạy lại với `SharedArchiveFile` | Exit code 0, stdout đúng. |
| `cds-use.log` | Có `Opened archive` cho base archive và `demo.jsa`. |
| `class-use.log` | Lớp chính và lớp lồng có `source: shared objects file (top)`. |
| `class-use.log` | `java.lang.Object` có `source: shared objects file`. |
| `class-off.log` | Lớp ứng dụng có `source: file:/.../demo.jar`. |
| Stdout ở train/use/off | Luôn hai dòng `status=ready` và `total=10`. |

Trong thử nghiệm này, các bước đã được tự động đối chiếu và có **exit code 0**. Trên JVM/JDK/OS khác, **timestamp, log order, tên file archive nền, địa chỉ ảo và path** có thể khác; hãy đọc log thực tế thay vì sao chép kết quả máy thử.

## 6. Đọc log `cds`: mở được file chưa có nghĩa lớp X dùng file đó

Một số dòng `cds-use.log` có thể giống:

~~~text
[info][cds] trying to map .../classes.jsa
[info][cds] Opened archive .../classes.jsa.
[info][cds] trying to map .../demo.jsa
[info][cds] Opened archive .../demo.jsa.
[info][cds] Mapped static region #1 ... (ReadOnly)
~~~

Thông tin trên chứng minh JVM **đã thử mở/mapping archive**. Dù như vậy, vẫn cần kiểm tra **`class+load`** của lớp đích.

Bảng phân công:

| Bạn đang hỏi | Nguồn log nên xem |
| --- | --- |
| JVM có mở đúng `demo.jsa` không? | `-Xlog:cds=info`. |
| JVM có map các vùng của archive không? | `-Xlog:cds=info` và tăng `debug` nếu cần. |
| Class X được nạp từ JAR hay shared archive? | `-Xlog:class+load=info`. |
| X có đến từ dynamic top archive không? | `class+load`, tìm X với `source: shared objects file (top)`. |
| JDK chỉ đang dùng base archive? | `cds` để xem topology, `class+load` để kiểm tra lớp app. |
| Cache AOT mới trên JDK 25+ có dùng được không? | `-Xlog:aot` và docs AOT của JDK đó. |
| Startup có cải thiện đáng kể không? | Benchmark riêng, không suy từ log class source. |

**Một kết luận chính xác phải ghi rõ:** lớp nào, JVM instance nào, lệnh chạy nào, build JDK nào, và nguồn nạp trong log.

### 6.1. Không đồng nhất “nạp từ shared archive” với “metadata đã chia sẻ RAM vật lý”

CDS lưu dữ liệu lớp đã chuẩn bị vào archive và runtime có thể memory-map chúng. Log nạp lớp xác nhận **nguồn lớp**; nó không tự đo số **physical pages** được chia sẻ với JVM khác.

Với nhiều tiến trình, dùng metric như RSS/PSS/private mappings theo công cụ OS tương ứng khi phân tích memory footprint. Không diễn giải một dòng log thành “đã tiết kiệm đúng X MiB”.

## 7. Nếu không thấy lớp ứng dụng trong log?

Giả sử lệnh:

~~~bash
grep 'com.example.ReportService' class-use.log
~~~

không trả dòng nào. Đó là dấu hiệu **chưa có bằng chứng**, không nhất thiết là “ReportService không được archive”.

Các khả năng:

1. Workload không chạy code dùng lớp này, nên lớp **chưa load**.
2. Bạn xem log của **JVM khác** hoặc thời điểm khác.
3. Logging được bật không đúng level/tag, hoặc sau khi lớp đã load.
4. File log ở đường dẫn khác, đã bị xoay vòng, hoặc bộ thu thập log đã loại bớt.
5. Tên lớp không đúng: nested class dùng `$`, lambda có tên generated.
6. Một classloader/tầng framework khác tạo tên lớp mà bạn không dự kiến.

**Quy trình:** kích hoạt một workload chắc chắn sử dụng lớp, xem một event class-load cho nó, rồi mới xét `source`. Nếu hoàn toàn không có event, chưa có đủ thông tin để kết luận **từ archive** hay **từ JAR**.

### 7.1. Nếu có event lớp app nhưng source là JAR?

Lúc đó có thể nói chính xác: “Trong lượt chạy đang xem, lớp này được nạp từ JAR.” Nhưng nguyên nhân có thể khác nhau:

- App archive **không có lớp** này do training run không kích hoạt nó.
- Archive bị bỏ qua do JDK/JAR/classpath thay đổi.
- Classloader/agent/custom loading không đủ điều kiện dùng archived copy.
- Startup flags chưa thực sự truyền app archive.
- Lớp bị transform hoặc có ràng buộc khác theo HotSpot.

Lúc này mới đọc **`cds` log** để điều tra nguyên nhân. Đừng mặc định lỗi luôn do một nguyên nhân như “archive hỏng”.

### 7.2. Nếu chỉ thấy `java.lang.Object` từ shared archive?

Có thể trả lời **base CDS đang có tác dụng với lớp này**; chưa có bằng chứng AppCDS của ứng dụng hoạt động. Hãy lọc thêm tên lớp app và xem top archive có được mở không.

### 7.3. Nếu ứng dụng chạy tốt nhưng archive không được dùng?

Trong nhiều cấu hình JVM cho phép **fallback** sang đường nạp thông thường. Đây có thể là hành vi chủ ý để ứng dụng vẫn hoạt động khi cache không phù hợp. Cần phân biệt mục tiêu **availability** với mục tiêu **startup optimization**.

## 8. Log của lượt **huấn luyện** và lượt **sử dụng** khác nhau

| Giai đoạn | Ví dụ lệnh | Thứ cần xác minh |
| --- | --- | --- |
| Tạo archive | `-XX:ArchiveClassesAtExit=demo.jsa` | Archive được ghi sau một workload; có file phù hợp để dùng thử. |
| Dùng archive | `-XX:SharedArchiveFile=demo.jsa` | JVM có mở/map đúng archive không và từng lớp có source từ archive không? |
| Đối chứng | `-Xshare:off` | Ứng dụng vẫn chạy đúng, lớp từ nguồn thường; dùng để so benchmark. |

Lỗi thường gặp: xem log `class+load` của **training run** rồi báo “production đã nạp lớp X từ archive”. Đó là hai process với hai giai đoạn khác nhau.

Cũng không được suy luận “một lớp đã nạp khi training thì chắc chắn được archive” — việc ghi vào archive còn phụ thuộc điều kiện HotSpot và môi trường.

### 8.1. Để log của từng giai đoạn ở file khác nhau

Nếu cần log training:

~~~bash
java -Xlog:cds=info:file=cds-train.log -XX:ArchiveClassesAtExit=demo.jsa -cp demo.jar CdsLogProof
~~~

Khi dùng:

~~~bash
java -XX:SharedArchiveFile=demo.jsa -Xlog:cds=info:file=cds-use.log -Xlog:class+load=info:file=class-use.log -cp demo.jar CdsLogProof
~~~

Không dùng chung một file log cho các lượt nếu điều đó khiến khó phân biệt lệnh hoặc thời điểm nào tạo ra thông điệp.

## 9. Những điều kiện làm archive không còn áp dụng được

AppCDS archive có liên hệ chặt với **JDK build và nội dung ứng dụng**. Những điểm cần kiểm tra khi log không có shared source:

| Yếu tố | Rủi ro | Cách xác minh |
| --- | --- | --- |
| **JDK build** | Build khác có thể không hiểu archive cũ. | Đối chiếu JDK thực tế và log CDS; tạo lại khi đổi JDK. |
| **JAR** | Thay đổi content khiến metadata không còn khớp. | Giữ JAR immutable sau khi dump, đối chiếu digest/version. |
| **Classpath** | Sai thứ tự/phần tử, đường dẫn khác kịch bản hỗ trợ. | Xem startup command thật và restrictions của JDK. |
| **Module path/options** | Module graph/options không nhất quán. | Đối chiếu các options giữa train/use. |
| **OS/CPU** | Archive phụ thuộc nền tảng/runtime. | Tạo/test ở môi trường tương thích với deployment. |
| **Classloader/agent** | Lớp transform hoặc custom loading có thể không dùng archive. | Xem event class source và log từ loader/agent. |
| **Archive permissions/path** | File không đọc được hay không mount trong container. | Đọc lỗi trong `cds` log, kiểm tra quyền. |
| **VM flags** | Một số flags khiến CDS không dùng được hoặc giảm phạm vi. | Xem log compatibility và Java launcher docs. |

Đây là **các nhóm nguyên nhân để điều tra**, không phải lời cam kết mọi thay đổi trong bảng đều gây lỗi mọi JDK.

### 9.1. `-Xshare:auto`, `-Xshare:on` và `-Xshare:off`

| Cờ | Hành vi | Phù hợp |
| --- | --- | --- |
| `-Xshare:auto` | Dùng archive nếu phù hợp, có thể tiếp tục bình thường nếu không dùng được. | Thường phù hợp production; JDK hiện đại bật CDS tự động. |
| `-Xshare:on` | Buộc dùng CDS; có thể khiến JVM thoát nếu không thể dùng. | QA/fail-fast diagnostics, **không phải mặc định production**. |
| `-Xshare:off` | Tắt CDS. | Đối chứng benchmark và điều tra nạp lớp. |

Tài liệu Oracle cảnh báo `-Xshare:on` có thể gây lỗi startup khi archive hoặc VM options không tương thích. Đừng đặt production vào trạng thái không khởi động được chỉ để buộc một tối ưu hoạt động.

### 9.2. Static archive so với dynamic/top archive

Archive **base/static** có thể chứa cả lớp JDK và lớp ứng dụng theo quy trình tạo. Archive **dynamic/top** bổ sung những lớp được quan sát trong training run dựa vào base. Khi dùng top archive, có thể chỉ truyền:

~~~bash
java -XX:SharedArchiveFile=demo.jsa -cp demo.jar CdsLogProof
~~~

vì archive động mang thông tin base tương ứng theo tài liệu JDK. Nếu cấu hình dùng hai archive tường minh, tham số có thể có dạng `base.jsa:top.jsa` trên Unix hoặc `base.jsa;top.jsa` trên Windows.

**Không nhầm** hậu tố `(top)` trong log với một chuỗi bắt buộc phải xuất hiện khi dùng **static archive** chứa lớp ứng dụng.

## 10. Khi cần log chi tiết hơn và cách kiểm soát độ ồn

Bật log với `info` trước:

~~~bash
java -Xlog:cds=info -Xlog:class+load=info -cp demo.jar CdsLogProof
~~~

Nếu gặp lỗi mapping/compatibility khó hiểu, có thể dùng `-Xlog:cds=debug` trong một lần tái hiện kiểm soát. Với ứng dụng lớn, log tất cả lớp có thể rất nhiều, nên nên ghi ra file riêng và dùng rotation.

### 10.1. Ví dụ xoay vòng log

~~~bash
java -Xlog:class+load=info:file=classload.log:uptime,level,tags:filecount=5,filesize=10M -cp demo.jar CdsLogProof
~~~

Theo Unified Logging, tham số cuối cho phép **giữ một số file log luân phiên** với kích thước được giới hạn; cần kiểm tra cú pháp/khả năng hỗ trợ ở JDK triển khai.

Lưu ý `filecount=5` không có nghĩa tổng log luôn chính xác 50 MiB trong mọi trường hợp; còn tính đến file hiện tại, rotation policy và filesystem. Mục tiêu là tránh ghi log vô hạn.

### 10.2. Lọc đúng lớp và không mất ngữ cảnh

Nếu chỉ cần lớp đích:

~~~bash
grep 'CdsLogProof' class-use.log
~~~

Nếu cần điều tra nguyên nhân archive không dùng được, **giữ cả `cds-use.log`** để thấy warning/error trước khi lớp được nạp.

Không nên chỉ trích dòng `source` rồi xóa log gốc ngay nếu chưa ghi lại **JDK build, JVM flags, path, thời điểm, workload và instance**. Chẩn đoán archive cần một tập chứng cứ nhất quán.

### 10.3. Bảo mật log

Class-load logs có thể chứa tên package nội bộ, đường dẫn JAR, thư mục cài đặt hoặc username trong path. Hạn chế quyền đọc, thời gian lưu giữ và **ẩn đường dẫn nhạy cảm khi chia sẻ log ra bên ngoài**. Checksum archive như CRC không thay thế bảo vệ nguồn gốc artifact hoặc phân quyền.

## 11. Vận hành trong CI/CD, container và nhiều JVM

Trong CI/CD, một ảnh container có thể chứa cả JAR và archive, nhưng phải kiểm chứng trong **runtime image cuối**:

1. Build JAR bất biến.
2. Tạo archive bằng JDK/build tương thích.
3. Đưa archive vào image với đường dẫn/quyền thích hợp.
4. Chạy cùng flags ứng dụng dùng trong môi trường thật.
5. Thu `cds` log và `class+load` log của **đúng process**.
6. Tìm lớp ứng dụng đích và `source`, ghi lại kết quả.
7. Benchmark startup/footprint trong điều kiện so sánh hợp lý.

Các lỗi thường gặp trong container:

- Training ở một image khác JDK hoặc kiến trúc.
- `demo.jsa` nằm ở thư mục khác khi container chạy.
- Entry-point không truyền JVM flag.
- Filesystem read-only khiến không thể tạo file `cds-use.log`.
- Log được ghi trong container nhưng hệ thống quan sát chỉ thu stdout.
- Nhiều pod và process khác nhau khiến người vận hành xem nhầm log.

**Không dùng log từ máy build làm bằng chứng cho pod production.** Phải kiểm chứng JVM đang hoạt động ở môi trường triển khai thật.

### 11.1. AppCDS và nhiều JVM

Memory-mapped class metadata có thể chia sẻ các trang file-backed giữa **những JVM trên cùng host**. Nhưng log class source **không tự đo** số lượng trang vật lý được dùng chung.

RSS của từng process có thể tính cả trang shared; nếu cộng RSS lại, có khả năng đếm trùng. Trên OS hỗ trợ, PSS/shared/private mappings có thể giúp phân tích. Hai container ở **hai host khác nhau** không chia sẻ cùng RAM dù dùng một JAR và archive giống nhau.

### 11.2. Phân biệt mức tiết kiệm startup và bằng chứng load

Ngay cả khi đã thấy:

~~~text
CdsLogProof source: shared objects file (top)
~~~

bạn vẫn chỉ biết **lớp này nạp từ top archive**. Chưa thể khẳng định startup nhanh hơn 20% hay giảm 100 MiB heap. Muốn có kết luận hiệu năng, phải đo nhiều lần với cùng CPU, memory, JDK, JAR, workload, cache tình trạng nóng/lạnh và điểm đo “application ready” rõ ràng.

## 12. JDK hiện đại: AOT cache và `-Xlog:aot`

CDS/AppCDS Java 10 vẫn là kiến thức có giá trị, nhưng không nên coi **`.jsa` dynamic archive** là tất cả công cụ tối ưu khởi động của JDK hiện đại.

- **JDK 24, JEP 483**: Ahead-of-Time Class Loading & Linking mở rộng khả năng chuẩn bị công việc nạp/liên kết lớp.
- **JDK 25, JEP 514**: đơn giản hóa quy trình tạo AOT cache bằng command-line ergonomics mới.
- **AOT cache** có phạm vi artifact rộng hơn AppCDS truyền thống; các cờ/cache file và log phải được đọc theo **đúng bản JDK**.

Ví dụ lệnh **chỉ dành cho JDK 25+**, không phải phần đã kiểm chứng bằng JDK 24:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp demo.jar CdsLogProof
java -XX:AOTCache=app.aot -Xlog:aot -Xlog:class+load=info -cp demo.jar CdsLogProof
~~~

Phân biệt:

| Công cụ/cờ | Ý nghĩa |
| --- | --- |
| `-XX:ArchiveClassesAtExit=demo.jsa` | Tạo dynamic CDS archive theo workflow CDS. |
| `-XX:SharedArchiveFile=demo.jsa` | Chạy dùng CDS archive đã tạo. |
| `-Xlog:cds` | Chẩn đoán CDS archives. |
| `-Xlog:class+load` | Xem lớp được nạp từ nguồn nào. |
| `-XX:AOTCacheOutput=app.aot` | Tạo AOT cache theo workflow JDK mới. |
| `-XX:AOTCache=app.aot` | Yêu cầu sử dụng AOT cache. |
| `-Xlog:aot` | Chẩn đoán trạng thái sử dụng AOT cache ở JVM hỗ trợ. |

Không tuyên bố mọi dòng `aot` đều có nghĩa một lớp đã đến từ `shared objects file (top)`. **AOT cache không phải tên mới cho cùng một file `.jsa`**, và cách log mô tả class loading có thể thay đổi khi JDK tối ưu hóa sâu hơn.

Tài liệu Java launcher hiện đại khuyến khích cấu hình AOT ở chế độ có thể fallback phù hợp production và dùng chế độ fail-fast khi cần kiểm tra lỗi cấu hình. Hãy xem tài liệu của đúng JDK/framework nếu triển khai tính năng này.

## 13. Mẫu báo cáo xác minh lớp được nạp từ archive

Một báo cáo vận hành tốt cần có phạm vi cụ thể:

~~~text
Runtime: HotSpot JDK 24.x (môi trường thử nghiệm)
Application JAR: demo.jar, không đổi giữa train/use
Archive: demo.jsa (dynamic/top)
Command: java -XX:SharedArchiveFile=demo.jsa ...
CDS log: mở được base và demo.jsa
Classload evidence:
  CdsLogProof source: shared objects file (top)
  CdsLogProof$Worker source: shared objects file (top)
Baseline -Xshare:off:
  CdsLogProof source: file:/.../demo.jar
Functional stdout: giống nhau ở cả hai lượt
Conclusion: Hai lớp ứng dụng đã được nạp từ dynamic archive trong lượt thử nghiệm.
Not concluded: Không tuyên bố mọi lớp đều archive hay tiết kiệm X% RAM.
~~~

Thông tin trong mẫu dựa trên demo đã thực chạy; khi dùng cho ứng dụng khác, phải thay bằng chứng **đúng JDK, log, lớp và workload của ứng dụng đó**.

### 13.1. Các tiêu chí “PASS” hợp lý

Đối với mục tiêu **kiểm tra AppCDS per-class**, một bộ kiểm tra có thể yêu cầu:

- Lệnh tạo archive hoàn tất, file tồn tại.
- Lượt chạy với archive kết thúc thành công.
- `cds` log xác nhận archive mong đợi đã được mở/mapping.
- `class+load` log có **đúng lớp ứng dụng đã được nạp** và source là shared archive tương ứng.
- Lượt `-Xshare:off` vẫn chạy đúng cùng logic (đối chứng).

**Không** kiểm tra timestamp, địa chỉ hex, đường dẫn tạm hoặc toàn bộ số lượng lớp; các chi tiết đó không phải hợp đồng ổn định trên mọi HotSpot/JDK.

## 14. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Thấy file `demo.jsa` và kết luận “CDS đã dùng”. | Runtime có thể không mở file. | Kiểm tra `cds` log khi chạy. |
| Thấy `Opened archive` và kết luận lớp X từ archive. | Mở archive chưa phải per-class evidence. | Kiểm tra `class+load` cho X. |
| Chỉ thấy `java.lang.Object` từ shared archive và báo AppCDS thành công cho ứng dụng. | Đây có thể là CDS mặc định của JDK. | Kiểm tra class app, không chỉ class JDK. |
| Bắt buộc mọi AppCDS log có `(top)`. | Static archive chứa ứng dụng có thể không phải top. | Xem topology của archive. |
| Kết quả app khác nhau khi bật/tắt CDS được cho là bình thường. | CDS không được đổi semantics nghiệp vụ. | Điều tra đầu vào, runtime state hoặc lỗi ứng dụng. |
| Dùng log training run để báo runtime. | Hai quá trình khác nhau. | Thu log ở lần dùng archive. |
| Không thấy tên lớp trong log là kết luận lớp đã fallback. | Lớp có thể chưa load. | Kích hoạt workload và kiểm tra logging. |
| `source: file:...jar` được coi là lỗi Java. | Đây là đường nạp bình thường. | Chỉ đánh dấu AppCDS per-class chưa áp dụng. |
| Lạm dụng `-Xshare:on` ở production. | Archive không phù hợp có thể làm JVM thoát. | Dùng auto, chỉ fail-fast khi cần QA. |
| Bật `-Xlog:all=trace` lâu dài. | Log quá lớn, gây overhead và lộ thông tin. | Chọn tag/level cụ thể, rotation. |
| Đóng đinh tên lambda và thời gian log. | JVM sinh tên/địa chỉ/thứ tự khác nhau. | Chọn lớp ứng dụng ổn định. |
| Đổi JDK/JAR sau khi dump nhưng dùng archive cũ. | Không bảo đảm tương thích. | Tạo lại archive và đọc log mới. |
| Dùng log CDS như phép đo RAM tiết kiệm. | Không biết shared physical pages hay heap. | Dùng benchmark và OS memory metrics. |
| Dùng `-Xlog:cds` để khẳng định mọi AOT optimization. | AOT cache có phạm vi khác. | Xem `-Xlog:aot` của JDK mới. |
| Chia sẻ log đường dẫn nội bộ công khai. | Có thể lộ cấu trúc ứng dụng và tài khoản. | Scrub path và quản lý quyền/retention. |

## 15. Bài tập thực hành và đáp án

### Bài 1 — Chỉ có lớp JDK được chia sẻ

~~~text
java.lang.Object source: shared objects file
com.example.App source: file:/opt/app/app.jar
~~~

**Đáp án:** Có bằng chứng CDS nền cho `Object`; `App` lấy từ JAR. **Chưa** có bằng chứng AppCDS cho lớp `App`.

### Bài 2 — Top archive

~~~text
CdsLogProof source: shared objects file (top)
~~~

**Đáp án:** Trên HotSpot được dùng trong bài, lớp `CdsLogProof` đã được nạp từ dynamic/top shared archive **trong lượt chạy ghi log**.

### Bài 3 — Archive file tồn tại

Bạn thấy `demo.jsa` tồn tại nhưng không có log runtime. Có đủ kết luận không?

**Đáp án:** Không. Phải chạy với `-XX:SharedArchiveFile` và xem log `cds`/`class+load`.

### Bài 4 — Log `Opened archive`

`cds-use.log` ghi `Opened archive demo.jsa` nhưng lớp app có `source: file:/.../demo.jar`.

**Đáp án:** JVM đã mở archive nhưng lớp app đó **không được nạp từ archive** trong lượt chạy; cần điều tra điều kiện app/classloader/classpath nếu muốn tối ưu.

### Bài 5 — Không thấy lớp

`grep ReportService class-use.log` không cho kết quả.

**Đáp án:** Chưa đủ thông tin. Cần biết lớp có thực sự được load không, log có bật đúng JVM/file và tên lớp có chính xác không.

### Bài 6 — Chọn log

Muốn biết một lớp cụ thể đến từ đâu, chọn `-Xlog:cds` hay `-Xlog:class+load`?

**Đáp án:** `class+load` cho **per-class source**. `cds` giúp biết archive được kiểm tra/mapping thế nào. Nên phối hợp cả hai.

### Bài 7 — Đối chứng

Chạy `-Xshare:off` cho cùng stdout như chạy với shared archive. Điều đó chứng minh gì?

**Đáp án:** Hành vi chức năng giống nhau khi tắt/bật CDS, như kỳ vọng. Để chứng minh nguồn lớp khác nhau, phải xem log của mỗi lượt.

### Bài 8 — Fail-fast

Có nên đặt `-Xshare:on` vào mọi container production?

**Đáp án:** Không nên mặc định. JVM có thể thất bại startup khi archive không phù hợp; dùng chính sách auto/fallback trong production, còn `on` cho test chủ động.

### Bài 9 — Top hay static?

Một static archive có lớp `com.example.Main` và log ghi `source: shared objects file`, không có `(top)`. Nó có nghĩa lớp không được chia sẻ?

**Đáp án:** Không. Dạng không `(top)` vẫn có thể là lớp từ shared static archive; xem cấu hình/topology archive.

### Bài 10 — Thay JAR sau huấn luyện

Bạn đổi JAR nhưng giữ `demo.jsa` cũ.

**Đáp án:** Không được tin archive vẫn dùng được. Cần tạo lại archive với JAR/JDK phù hợp, sau đó xác minh qua log runtime.

### Bài 11 — Hiệu năng

Một log lớp có `source: shared objects file (top)`, liệu có được nói ứng dụng đã tăng tốc 25%?

**Đáp án:** Không. Log chỉ chứng minh nguồn nạp của lớp đó. Hiệu năng cần benchmark có baseline và nhiều lượt chạy.

### Bài 12 — JDK 25+ AOT cache

Ứng dụng dùng `app.aot`. Có được coi mọi dòng `aot` là per-class CDS evidence không?

**Đáp án:** Không. Phải đọc `-Xlog:aot` cho trạng thái cache, đọc tài liệu của JDK cụ thể và xem nguồn lớp được log phù hợp; không đánh đồng `.aot` với `.jsa` top archive.

### Bài 13 — Lambda

Log có `CdsLogProof$$Lambda/0x...`. Có nên assert toàn bộ tên đó?

**Đáp án:** Không. Generated class name và hậu tố có thể thay đổi; chọn tên lớp ứng dụng ổn định hơn.

### Bài 14 — Nhiều container

Hai container trên hai host đều ghi lớp app từ shared archive. Có nghĩa chúng đang chia sẻ cùng trang RAM vật lý?

**Đáp án:** Không. Cùng host mới có cơ hội dùng chung file-backed physical pages; mỗi host vẫn có RAM riêng. Log chứng minh nguồn lớp trong từng JVM, không chứng minh RAM liên host.

## 16. Checklist chốt QA

- [ ] Tôi biết rõ đây là log của **lượt runtime dùng archive**, không chỉ training run.
- [ ] Tôi xác định JDK build, JAR, archive path, VM flags, workload và JVM instance.
- [ ] Tôi chọn **lớp ứng dụng thật** làm mục tiêu, không chỉ một lớp `java.*`.
- [ ] Tôi dùng `-Xlog:class+load=info` để xác minh **source** của lớp đó.
- [ ] Tôi dùng `-Xlog:cds=info` để biết trạng thái archive, không coi `Opened` là đủ.
- [ ] Tôi hiểu `source: shared objects file` và `source: shared objects file (top)` theo topology.
- [ ] Tôi hiểu `source: file:/...jar` nghĩa là lớp dùng nguồn JAR ở lượt đó.
- [ ] Tôi không kết luận lớp fallback khi chưa biết lớp có load hay không.
- [ ] Tôi giữ cả log gốc khi cần điều tra compatibility/error.
- [ ] Tôi thử `-Xshare:off` khi cần đối chứng và kiểm tra logic không đổi.
- [ ] Tôi không bật `-Xshare:on` bừa trên production.
- [ ] Tôi không dùng kết quả log lớp để suy ra mức tăng hiệu năng cụ thể.
- [ ] Tôi biết các archive có thể phụ thuộc JDK/JAR/classpath/modules.
- [ ] Tôi không hard-code timestamp, absolute path, generated lambda name.
- [ ] Tôi ghi log file riêng và cấu hình rotation/quyền truy cập phù hợp.
- [ ] Tôi không lộ log chứa thông tin nội bộ không cần thiết.
- [ ] Tôi kiểm chứng chính container/runtime image mà ứng dụng chạy.
- [ ] Nếu dùng JDK mới, tôi phân biệt AppCDS `.jsa` và AOT cache `.aot`.
- [ ] Tôi nêu kết luận chính xác: **lớp X lấy từ archive Y ở lượt chạy Z**, không phóng đại phạm vi.

## 17. Nguồn tham khảo chính thức đang được hỗ trợ

1. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): AppCDS được bổ sung trong Java 10.
2. [Oracle Java SE 25 — The java Command: Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): hướng dẫn static/dynamic archive và **xác minh trực tiếp bằng `-Xlog:class+load`**.
3. [Oracle Java SE 25 — The java Command: Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): cú pháp `-Xlog`, level, tags, output file, decorators, rotation.
4. [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): cơ chế map archive, các cờ `-Xshare:auto/on/off`, lưu ý production.
5. [Oracle Java SE 25 — The java Command: Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache): AOT cache flags, `-Xlog:aot` và cách fallback.
6. [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive được đưa vào quy trình phân phối JDK.
7. [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): tạo dynamic archive trên base archive.
8. [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): khả năng AOT trên JDK 24.
9. [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): workflow cache tiện lợi hơn ở JDK 25.
10. [Oracle Java SE 25 — CDS classpath restrictions](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#restrictions-on-class-path-and-module-path): các ràng buộc khi tạo/đọc archive.

**Kết luận:** Trong vận hành AppCDS, **file archive tồn tại** hay log `Opened archive` chưa chứng minh lớp ứng dụng đã được dùng lại. Để xác minh **lớp cụ thể**, đọc `-Xlog:class+load=info` trong **lượt chạy với archive** và tìm `source: shared objects file` hoặc `source: shared objects file (top)` phù hợp kiểu archive. Dùng `-Xlog:cds=info` để hiểu archive được mở/map, `-Xshare:off` làm đối chứng, và `-Xlog:aot` cho AOT cache ở những JDK mới. Kết luận phải gắn với đúng lớp, JDK, JVM instance và workload; hiệu năng là một phép đo độc lập.