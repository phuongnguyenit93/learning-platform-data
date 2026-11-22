# 12.4. HeapDumpOnOutOfMemoryError, HeapDumpPath và giới hạn của thu dump tự động

Khi một ứng dụng Java hết bộ nhớ, dấu vết có giá trị nhất đôi khi biến mất cùng với tiến trình. Một **heap dump** ghi lại trạng thái các đối tượng trên Java heap tại thời điểm chụp, giúp phân tích đối tượng nào đang chiếm bộ nhớ và những đường tham chiếu nào giữ chúng lại. HotSpot/OpenJDK cung cấp hai tùy chọn thường được dùng cùng nhau: `-XX:+HeapDumpOnOutOfMemoryError` để yêu cầu chụp dump khi JVM phát hiện một số trường hợp hết bộ nhớ, và `-XX:HeapDumpPath=...` để chỉ định nơi lưu.

Tuy nhiên, **bật cờ không bảo đảm luôn có tệp dump sau mọi sự cố OOM**. Điều kiện lỗi, cách JVM kết thúc, quyền ghi, dung lượng đĩa và giới hạn container đều quyết định việc thu thập có thành công hay không. Bài học này áp dụng chủ yếu cho JVM HotSpot/OpenJDK 17+; với JVM khác, cần xác minh hỗ trợ tùy chọn tương ứng.

## 1. Heap dump là gì, có ích đến đâu?

Heap dump ở định dạng HPROF là ảnh chụp biểu diễn các đối tượng, class, mảng và quan hệ tham chiếu mà JVM ghi lại từ heap. Công cụ như Eclipse Memory Analyzer (MAT), VisualVM hoặc những profiler tương thích có thể đọc tệp này để:

- Xem **class histogram**: số lượng instance và bộ nhớ dạng `shallow size` của từng kiểu.
- Xem **dominator tree** và `retained size`: ước lượng dung lượng sẽ có thể giải phóng nếu những đối tượng đang thống trị một tập tham chiếu không còn giữ tập đó.
- Truy ngược **path to GC roots**: vì sao một đối tượng còn reachable, chẳng hạn được giữ bởi một `static Map`, queue, thread, cache, listener hoặc class loader.
- Phân biệt việc nhiều object được giữ có chủ đích với giả thuyết rò rỉ bộ nhớ thông qua quan hệ tham chiếu và bối cảnh nghiệp vụ.

Heap dump **không phải bản ghi toàn bộ lịch sử cấp phát**. Nó không cho biết trực tiếp mỗi object được tạo lúc nào, luồng nào tạo ra nó hay GC đã chạy theo lịch nào nếu không có profiler/JFR/log bổ sung. Dump cũng không trực tiếp phản ánh đầy đủ bộ nhớ ngoài Java heap như thread stack, native allocation, direct buffer, code cache và vùng metaspace. Một ứng dụng có thể hết bộ nhớ ở những vùng đó dù `heap used` chưa gần `-Xmx`.

Một object tồn tại trong dump **chưa đồng nghĩa với memory leak**. Cache hợp lệ, dữ liệu đang xử lý và state của ứng dụng cũng phải còn reachable. Memory leak trên Java thường là tình trạng đối tượng **không còn cần về mặt nghiệp vụ nhưng vẫn bị giữ tham chiếu**, khiến GC không thể thu hồi. Muốn chứng minh điều đó cần đọc đường tham chiếu cùng điều kiện tải, không chỉ nhìn một class có số lượng lớn.

## 2. Hai tùy chọn JVM và cách phối hợp

| Tùy chọn | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `-XX:+HeapDumpOnOutOfMemoryError` | Yêu cầu HotSpot tạo heap dump khi VM xử lý một lỗi hết bộ nhớ thuộc phạm vi hỗ trợ. | Không đảm bảo áp dụng cho mọi `OutOfMemoryError` hoặc trường hợp tiến trình bị hệ điều hành giết. |
| `-XX:HeapDumpPath=<path>` | Chỉ định **tên tệp** hoặc **thư mục** đích của dump. | Chỉ chọn đường dẫn; tự nó không bật việc dump khi OOM. |
| `-Xmx<size>` | Thiết lập giới hạn heap tối đa. | Không phải hạn mức toàn bộ RSS/native memory của JVM; nên cấu hình có tính đến giới hạn container và vùng ngoài heap. |

Ví dụ trên Linux, khi thư mục đã tồn tại và có quyền ghi:

```bash
mkdir -p /var/log/myapp/heap-dumps
java -Xms256m -Xmx1024m \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp/heap-dumps \
  -jar app.jar
```

Nếu cung cấp đường dẫn **thư mục**, HotSpot thường tự đặt tên tương tự `java_pid12345.hprof` theo PID. Nếu cung cấp **tên tệp cụ thể**, chẳng hạn `-XX:HeapDumpPath=/var/log/myapp/heap-dumps/incident.hprof`, dump sẽ hướng tới tệp đó. Nếu không đặt `HeapDumpPath`, HotSpot thường đặt `java_pid<pid>.hprof` trong thư mục làm việc hiện tại của JVM; thư mục đó có thể khác thư mục chứa JAR, đặc biệt trong service hoặc container.

Không giả định JVM tạo hộ thư mục chưa có. Tạo trước, xác minh quyền ghi của **user chạy JVM** và dung lượng trống. Dùng một tên tệp cố định cho nhiều instance/rerun dễ gây xung đột; HotSpot không nên được trông chờ ghi đè an toàn tệp dump đã tồn tại. Cách dùng thư mục riêng cho từng instance hoặc tệp có tên duy nhất thường dễ vận hành hơn.

Cú pháp `-XX:...` phải được đưa vào lệnh **trước** tên class hoặc `-jar` để JVM nhận đúng là tùy chọn của VM. Nếu cấu hình qua `JAVA_TOOL_OPTIONS` hoặc launcher của framework, hãy kiểm tra effective command line vì script khởi động có thể thêm hoặc thay đổi các tham số khác.

## 3. JVM tạo dump tự động vào lúc nào?

Dòng diễn biến thường gặp khi **Java heap thực sự cạn bộ nhớ**:

1. Ứng dụng yêu cầu cấp phát một object/mảng.
2. JVM cố đáp ứng yêu cầu, có thể kích hoạt GC hoặc các bước phục hồi khác tùy collector.
3. Khi không thể cấp phát theo các điều kiện của JVM, HotSpot báo lỗi `OutOfMemoryError` thích hợp.
4. Nếu cờ dump đang bật **và đường đi xử lý lỗi có hỗ trợ**, JVM cố ghi snapshot HPROF ra vị trí cấu hình.
5. Sau đó ứng dụng vẫn đang ở trạng thái thiếu tài nguyên. Ngoại lệ có thể lan ra, bị ứng dụng bắt, hoặc dẫn tới việc tiến trình kết thúc theo cấu hình. Tệp dump chỉ tồn tại nếu thao tác ghi hoàn tất.

Vì thế, **không phải cứ sử dụng heap cao là có dump**. Nếu cache tăng lên 90% `-Xmx` nhưng chưa phát sinh lỗi thuộc diện kích hoạt, JVM không tự chụp. Ngược lại, một lỗi cấp phát có thể xảy ra dù dashboard hiển thị giá trị `used` cuối cùng chưa đạt đúng `-Xmx`, do thời điểm lấy mẫu, kích thước allocation hoặc điều kiện collector.

HotSpot thường chỉ cố ghi một heap dump tự động trong một vòng đời JVM khi gặp sự kiện OOM phù hợp; không thiết kế việc thu tự động như một chuỗi snapshot cho mỗi lần lỗi lặp lại. Muốn so sánh các mốc trước/sau, cần thêm quan sát định kỳ, JFR hoặc chụp thủ công có kiểm soát.

### Các loại OOM không giống nhau

| Tình huống / thông báo thường thấy | Có nên trông chờ dump tự động? | Vì sao |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | **Thường có thể**, nếu HotSpot còn hoạt động và ghi tệp được. | Lỗi cấp phát trong Java heap là trường hợp điển hình của tùy chọn. |
| `OutOfMemoryError: GC overhead limit exceeded` | **Có thể**, tùy VM/collector và đường báo lỗi. | JVM dành quá nhiều thời gian GC nhưng thu hồi quá ít; phải kiểm tra log và dump thực tế. |
| `OutOfMemoryError: Metaspace` | **Có thể** ở đường VM hỗ trợ, nhưng dump heap không trực tiếp đo mọi byte native metaspace. | Class loader/class metadata liên quan, song cần bổ sung thống kê metaspace và class loading. |
| `OutOfMemoryError: Direct buffer memory` | **Không được mặc định là có**. | Có thể do cơ chế cấp phát direct buffer/Java library; đây không phải cạn Java heap thông thường. |
| `OutOfMemoryError: unable to create native thread` | **Không được mặc định là có**. | Thường liên quan giới hạn thread, PID hoặc bộ nhớ native/stack. |
| `new OutOfMemoryError(...)` do mã ứng dụng tự ném | **Không được mặc định là có**. | Một exception được tạo/ném thủ công không đồng nghĩa HotSpot đã phát hiện cạn bộ nhớ ở đường kích hoạt dump. |
| Container `OOMKilled`, kernel OOM killer, `SIGKILL` | **Không** theo cơ chế flag này. | OS kết thúc tiến trình từ bên ngoài; JVM không có cơ hội thực hiện hook OOM để ghi dump. |
| Crash native / `SIGSEGV` / `kill -9` | **Không** theo cơ chế flag này. | Đây không phải Java heap OOM do VM xử lý. |

Tùy phiên bản JVM, cờ kích hoạt dump có thể phản ứng khác với những loại `OutOfMemoryError` hiếm gặp, chẳng hạn yêu cầu mảng vượt giới hạn cho phép. Không dùng duy nhất **tên exception** để khẳng định sẽ có HPROF; điều cần xác nhận là log HotSpot ghi dump và tệp đã hoàn tất.

## 4. Ví dụ Java 17+ có thể chạy độc lập

Bài thực hành sau **cố ý gây Java heap OOM** trong môi trường test để quan sát cơ chế. Không chạy trên production hoặc máy đang chứa dữ liệu quan trọng.

Lưu thành `HeapDumpDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class HeapDumpDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) {
        while (true) {
            RETAINED.add(new byte[1024 * 1024]);
        }
    }
}
```

Mỗi vòng lặp tạo một mảng khoảng 1 MiB và thêm vào danh sách tĩnh, nên toàn bộ những mảng được lưu vẫn reachable. Với giới hạn heap nhỏ, chương trình sẽ không thể tiếp tục cấp phát và thường phát sinh `OutOfMemoryError: Java heap space`.

Trên terminal Bash với JDK 17+:

```bash
javac HeapDumpDemo.java
mkdir -p dumps

java -Xms32m -Xmx64m \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./dumps \
  HeapDumpDemo

ls -lh dumps
```

Lệnh `java` trong ví dụ được dự kiến **kết thúc với lỗi**, vì ta chủ động giữ mảng đến khi cạn heap. Trên HotSpot, terminal thường xuất hiện thông tin tương tự:

```text
java.lang.OutOfMemoryError: Java heap space
Dumping heap to ./dumps/java_pid<process-id>.hprof ...
Heap dump file created [... bytes in ... secs]
```

Đây là **mẫu thông điệp**, không phải stdout/stderr chính xác cho mọi JDK và máy. PID, số byte, thời gian, thứ tự thông báo và stack trace khác nhau; JVM cũng có thể không ghi được dump do sự cố I/O. Tệp mong đợi thường có đuôi `.hprof` trong `./dumps`, ví dụ `java_pid12345.hprof`. Có thể dùng MAT để xem `byte[]` và `ArrayList` cùng đường giữ tham chiếu từ trường tĩnh `RETAINED`.

Nếu viết tên file rõ ràng, ví dụ `-XX:HeapDumpPath=./dumps/test-oom.hprof`, cần đảm bảo không có file trùng tên từ lượt chạy trước. Với đường dẫn tương đối, `./dumps` được hiểu từ **working directory của tiến trình Java**, không phải bắt buộc từ nơi đặt `HeapDumpDemo.class`.

### Tại sao đây là ví dụ retention chứ không đại diện mọi leak?

Trong `HeapDumpDemo`, mảng vẫn reachable vì được giữ bởi `static final List`. GC không thể thu hồi chúng dù chúng được tạo trong các vòng lặp trước. Đây là minh họa đơn giản về **giữ tham chiếu gây tăng heap**; khi điều tra ứng dụng thật, phải chứng minh dữ liệu không còn cần về nghiệp vụ. Một cache giữ dữ liệu để phục vụ request tiếp theo có thể có hình dạng heap tương tự nhưng vẫn là thiết kế hợp lệ nếu giới hạn và chính sách eviction đúng.

## 5. Giới hạn của thu dump tự động

### 5.1. OOM do container và kernel khác JVM OOM

Một container có giới hạn RAM là giới hạn cho tổng tài nguyên bộ nhớ được kernel tính theo cơ chế quản lý container, gồm nhiều thành phần ngoài `heap used`. JVM vẫn có thể có `-Xmx` nhỏ hơn memory limit nhưng tiến trình vượt hạn mức do native allocations, thread stack, direct buffers hoặc các thành phần khác. Khi kernel OOM killer kết thúc tiến trình, bạn có thể thấy `OOMKilled` hoặc exit code `137` mà **không có** exception Java và **không có** heap dump.

Ví dụ giả định:

- Container memory limit: **512 MiB**.
- Java heap max: **384 MiB**.
- Metaspace, thread stacks, JIT/code cache, direct buffers và native allocations cùng tăng.
- Tổng bộ nhớ vượt giới hạn container và kernel kill JVM.

Ở tình huống này, `HeapDumpOnOutOfMemoryError` không có cơ hội chạy. Không thể suy luận “không có .hprof ⇒ không có vấn đề bộ nhớ”. Nếu ứng dụng liên tục bị `OOMKilled`, xem sự kiện container/kernel, memory RSS/cgroup và vùng ngoài heap; điều chỉnh heap budget tổng thể **theo số liệu thực tế**.

### 5.2. Đĩa, đường dẫn và quyền ghi

Dump có thể lớn; dung lượng không cố định bằng `-Xmx` và phụ thuộc số object, cấu trúc dữ liệu cùng định dạng ghi. Một file HPROF nhiều GiB có thể làm đầy volume, tác động dịch vụ khác hoặc không thể ghi hoàn chỉnh.

Các nguyên nhân thường gặp:
- Thư mục đích chưa được tạo, path bị gõ sai hoặc trở thành file thay vì thư mục như dự kiến.
- User chạy JVM không có quyền ghi, filesystem ở chế độ read-only, SELinux/AppArmor/policy hạn chế thao tác.
- Volume hết dung lượng, hết quota hoặc inode; đường dẫn là filesystem tạm có dung lượng nhỏ.
- Nhiều instance dùng chung filename khiến việc tạo file mới xung đột với dump cũ.
- Không có cơ chế sao chép/lưu trữ trước khi container hoặc pod bị thay thế; tệp nằm trên lớp filesystem tạm và bị mất sau restart/redeploy.

**Kiểm tra quyền và dung lượng bằng đúng user/container chạy JVM**, không chỉ bằng user quản trị trên host. Với Kubernetes, nếu muốn giữ dump sau pod bị tạo lại, nên cấu hình volume có khả năng lưu giữ phù hợp, cơ chế sao chép an toàn và chính sách dọn dữ liệu. Đừng dựa vào đường dẫn cục bộ bên trong pod làm nơi lưu trữ lâu dài nếu pod có thể bị thay thế.

### 5.3. Trạng thái tiến trình quá xấu để hoàn tất ghi

Ngay cả khi HotSpot đã phát hiện OOM thuộc diện hỗ trợ, dump vẫn là thao tác I/O đáng kể xảy ra trong tình trạng tài nguyên căng thẳng. JVM có thể bị hệ điều hành kill giữa chừng, mất quyền truy cập volume, crash hoặc bị hệ thống vận hành cưỡng bức dừng do health-check/restart. Vì vậy tệp có thể thiếu, nhỏ bất thường hoặc không mở được. Hãy kiểm tra trạng thái **được tạo hoàn chỉnh** trong log và thử mở bằng trình phân tích, thay vì chỉ kiểm tra có file cùng tên.

Dump có thể dừng ứng dụng trong thời gian đáng kể, gây tăng I/O và tiêu tốn dung lượng. Thời gian xử lý phụ thuộc kích thước và tình trạng heap, đĩa và JVM; không có một con số pause cố định. Trên dịch vụ latency-sensitive, cần cân nhắc tác động này trong kế hoạch xử lý sự cố.

### 5.4. “Có dump” không đồng nghĩa “có đủ nguyên nhân gốc”

Một heap dump được chụp **sau khi JVM đã cố GC để đáp ứng allocation** có thể không còn những object ngắn hạn gây allocation pressure trước đó. Nếu lỗi do tốc độ cấp phát rất cao nhưng object sống ít, dump sau OOM khó cho biết toàn bộ chuỗi allocation dẫn tới áp lực. Nếu lỗi do direct buffer hoặc native memory, HPROF chỉ cho thấy một phần trạng thái.

Nên đi kèm một số bằng chứng: mốc thời gian lỗi, GC logs, heap used/committed/max, RSS/container memory, thread counts, request/batch metrics, allocation profiling và JFR khi phù hợp. Tương quan giữa chúng quan trọng hơn một snapshot đơn lẻ.

### 5.5. Không thể dùng flag để lập lịch hoặc bảo đảm mỗi lỗi một dump

`HeapDumpOnOutOfMemoryError` là cách **phản ứng lúc OOM**, không phải bộ chụp định kỳ, cơ chế giám sát cảnh báo sớm hay công cụ ghi mọi exception `OutOfMemoryError`. Không trông chờ nhiều file từ một tiến trình đang liên tục OOM, đặc biệt khi `HeapDumpPath` chỉ định cùng một filename. Nếu cần so sánh hai thời điểm trước/sau khi dữ liệu tăng, phải thiết kế việc thu thập có kiểm soát khi JVM còn khỏe.

## 6. Phân biệt dump tự động, dump thủ công và JFR

| Công cụ | Khi nào dùng | Hạn chế cần nhớ |
| --- | --- | --- |
| Auto dump: `-XX:+HeapDumpOnOutOfMemoryError` | Muốn có snapshot khi JVM rơi vào một trường hợp OOM được hỗ trợ. | Chỉ chạy khi đúng trigger và JVM còn có thể ghi; có thể chỉ có một snapshot muộn. |
| Manual dump: `jcmd <pid> GC.heap_dump <file>` | Điều tra retention growth trước khi OOM, khi tiến trình còn sống và có quyền attach. | Có thể gây pause đáng kể; mặc định lệnh heap dump của HotSpot có thể yêu cầu full GC trước khi chụp. |
| GC logging: `-Xlog:gc*` | Tìm nhịp GC, before/after, pause, heap capacity và mức thu hồi trong chuỗi thời gian. | Không trực tiếp cho biết đối tượng nào đang giữ tham chiếu. |
| JFR / allocation profiling | Tìm thời điểm, call site, loại đối tượng và áp lực cấp phát; đối chiếu với sự kiện GC. | Phụ thuộc cấu hình sự kiện và overhead; không thay thế việc đọc object graph từ dump. |
| Native Memory Tracking / OS metrics | Điều tra thread stack, native memory, RSS hoặc container OOM. | Không thay thế heap dump để phân tích đường tham chiếu Java. |

Ví dụ chụp thủ công khi ứng dụng vẫn đang hoạt động:

```bash
jcmd <pid> GC.heap_dump /var/log/myapp/heap-dumps/manual-2026-10-29.hprof
```

`<pid>` chỉ là chỗ điền PID thực; không chép nguyên dấu ngoặc nhọn vào terminal. Đảm bảo đủ dung lượng và quyền, vì lệnh có thể pause tiến trình và thường tạo file lớn. Trên một số phiên bản HotSpot, `GC.heap_dump` hỗ trợ tùy chọn `-all` để đưa cả object chưa được GC dọn và không buộc GC trước; cách dùng thay đổi đặc tính snapshot, nên đọc help của chính JVM (`jcmd <pid> help GC.heap_dump`) trước khi chọn.

Khi nghi ngờ ứng dụng tạo nhiều dữ liệu ngắn hạn, JFR thường giúp phân tích allocation churn hơn việc chỉ nhìn snapshot cuối. Khi nghi ngờ object bị giữ lâu, dump + dominator tree + path to GC roots thường trực tiếp hơn.

## 7. Cấu hình trong service/container cho đúng

### 7.1. Thiết lập đường dẫn nhất quán với working directory

Trong service Java trực tiếp, ưu tiên đường dẫn tuyệt đối:

```bash
java -Xms256m -Xmx2g \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/data/diagnostics/heap \
  -Xlog:gc*:file=/data/diagnostics/logs/gc.log:time,uptime,level,tags \
  -jar app.jar
```

Trước khi khởi chạy, hai thư mục `/data/diagnostics/heap` và `/data/diagnostics/logs` phải tồn tại, có quyền ghi. Cần cấu hình log rotation cho GC log, retention/quota cho dump và chính sách truy cập vì dump có thể chứa secret trong chuỗi, token, payload hoặc dữ liệu người dùng.

Trong container, nếu dùng `JAVA_TOOL_OPTIONS`, các cờ JVM tương ứng có thể được chuyển qua biến môi trường:

```bash
docker run --rm \
  --memory=1g \
  -v "$(pwd)/dumps:/dumps" \
  -e JAVA_TOOL_OPTIONS="-Xmx512m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps" \
  myapp:latest
```

Lệnh chỉ minh họa một image Java có launcher tôn trọng `JAVA_TOOL_OPTIONS`; thư mục `./dumps` trên host cần tồn tại và có quyền ghi phù hợp. `--memory=1g` và `-Xmx512m` là số ví dụ để minh họa việc chừa chỗ cho non-heap, **không phải tỷ lệ an toàn phổ quát**. Cân đối theo RSS/native thực đo, số thread, direct buffers và đặc điểm runtime.

### 7.2. Kiểm tra tùy chọn đã thực sự được áp dụng

Khi tiến trình còn sống:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

`VM.command_line` giúp xem tham số JVM được truyền, `VM.flags` xem các cờ ở trạng thái hiện tại. Kết quả thay đổi theo phiên bản và launcher; nếu một flag không hiện trong danh sách ngắn, có thể dùng help/các lựa chọn liệt kê đầy đủ của JVM để đối chiếu. Trên dịch vụ chạy qua systemd, Docker hoặc Kubernetes, cần phân biệt **cấu hình mong muốn** với **lệnh đã khởi chạy thực tế**.

Có thể kiểm tra khả năng ghi trước lúc sự cố bằng một bài thử OOM có kiểm soát trên staging như `HeapDumpDemo`, cùng image, user, mount và giới hạn tài nguyên dự kiến. Đây là cách xác nhận đường đi tạo HPROF tốt hơn chỉ nhìn một dòng cấu hình.

## 8. Sau sự cố: tìm và xác thực dump

Làm theo trình tự để tránh kết luận vội:

1. **Phân loại kết thúc tiến trình.** Log có `java.lang.OutOfMemoryError` do VM báo, hay chỉ có `OOMKilled`/`137`/`SIGKILL`? Nếu OS kill, flag Java không thể giải quyết việc thiếu dump.
2. **Kiểm tra cờ khi JVM khởi động.** Đọc command line, biến môi trường hoặc cấu hình deploy đã được dùng tại thời điểm incident. Sửa config sau sự cố không làm xuất hiện dump cho lần trước.
3. **Tìm thông báo tạo dump trong log.** Các dòng tương tự `Dumping heap to ...`, `Heap dump file created` hoặc thông báo không thể tạo tệp thường cho biết tiến trình đã đến đâu.
4. **Xác định đường dẫn thực.** Với path tương đối, tìm từ working directory của JVM; với directory path, tìm tệp `java_pid*.hprof`; kiểm tra đúng container/mount/host.
5. **Kiểm tra tệp.** Xem file size, thời gian chỉnh sửa, khả năng đọc định dạng HPROF bằng MAT/VisualVM. Một tệp rất nhỏ hoặc lỗi parse có thể là dump chưa hoàn chỉnh.
6. **Phân tích object graph.** Dùng histogram để định hướng, dominator tree để tìm cụm chiếm nhiều retained memory, path to GC roots để chứng minh vì sao còn reachable. Đối chiếu request/batch/cache để biết có bất thường về nghiệp vụ.
7. **Xử lý dữ liệu an toàn.** Giới hạn người có quyền đọc dump, mã hóa khi lưu/truyền, không commit lên Git và xóa theo retention policy; heap có thể chứa mật khẩu, token và dữ liệu cá nhân.

Một lần OOM không có dump cần được xử lý như **thiếu bằng chứng**, không mặc nhiên là lỗi cấu hình flag. Có thể đã mất cơ hội ghi vì kernel kill hoặc sự cố I/O.

## 9. Phân tích ba tình huống minh họa

### Tình huống A — Java heap OOM và có tệp HPROF

Monitoring cho thấy heap used sau GC tăng dần trong nhiều giờ, cuối cùng log báo `OutOfMemoryError: Java heap space` và `Heap dump file created`. Tải tương đối ổn định. Hãy đọc HPROF để tìm những tập object có retained size lớn, ví dụ queue đang tích backlog hoặc cache key không được eviction. Sau đó xác nhận tại sao object vẫn reachable và có còn cần hay không. Nếu cache tăng vì số lượng khách hàng tăng hợp lệ, cần chọn eviction/quota phù hợp hơn là gọi mọi mức tăng là “leak”.

### Tình huống B — Pod OOMKilled, không có HPROF

JVM đặt `-Xmx512m` nhưng pod memory limit `640 MiB`; số thread/direct buffers tăng và pod bị kill. Không có stack trace `Java heap space`, không có dòng tạo heap dump. Đây là dấu hiệu điều tra theo hướng **bộ nhớ tiến trình/container**: RSS/cgroup, thread count, direct memory, metaspace, memory request/limit và native allocations. Việc tăng `-Xmx` có thể khiến áp lực lên container tệ hơn.

### Tình huống C — Java OOM nhưng dump không hoàn tất

Log có `Dumping heap to /dumps/...`, sau đó lỗi I/O hoặc file không mở được; volume gần đầy hoặc pod bị dừng sớm. Cờ đã được bật nhưng quá trình thu thất bại. Hành động đúng là tạo/mount thư mục ghi được, đủ quota/retention và thử kịch bản staging. Không kết luận rằng sự cố không liên quan heap chỉ vì file HPROF vắng mặt.

## 10. Lỗi thường gặp và cách sửa suy luận

- **“Bật `HeapDumpPath` là đủ.”** Sai: cần `-XX:+HeapDumpOnOutOfMemoryError` (hoặc một thao tác chụp khác). `HeapDumpPath` chỉ xác định đường dẫn.
- **“Bất kỳ `OutOfMemoryError` nào cũng có file.”** Sai: phải phân loại loại OOM, JVM/VM path và điều kiện ghi.
- **“Container `OOMKilled` là `OutOfMemoryError` Java.”** Sai: OS có thể kill tiến trình trước khi JVM ném exception.
- **“Đặt `HeapDumpPath=/dumps` thì JVM sẽ tự tạo folder và giữ file qua mọi redeploy.”** Sai: cần tạo sẵn, mount/retention và kiểm tra quyền.
- **“File dump phải có size bằng `-Xmx`.”** Sai: kích thước HPROF phụ thuộc đối tượng/snapshot và overhead định dạng.
- **“Có dump rồi thì biết leak ở dòng code nào.”** Sai: dump cho object graph; cần tìm đường giữ tham chiếu, truy ngược nghiệp vụ và có thể bổ sung allocation profiling.
- **“Dump có object to nhất chính là thủ phạm.”** Sai: object lớn có thể hoàn toàn hợp lệ; xem retained size, dominators và vòng đời.
- **“Có `HeapDumpOnOutOfMemoryError` thì không cần cảnh báo trước OOM.”** Sai: auto dump chỉ có cơ hội chạy **sau khi gặp lỗi** và có thể ghi thất bại.
- **“Thu càng nhiều dump càng tốt.”** Sai: chi phí pause, disk, bảo mật và thời gian phân tích có thể lớn; thu theo kế hoạch có mục tiêu.

## 11. Checklist triển khai và kiểm chứng

Trước khi deploy:
- Xác nhận JVM HotSpot/OpenJDK và cách các `-XX` flags được truyền vào thực tế.
- Chọn nơi lưu dump đủ dung lượng, có quota, không ảnh hưởng trực tiếp ổ đĩa dịch vụ thiết yếu và có chiến lược giữ/xóa.
- Tạo thư mục trước, kiểm tra quyền ghi bằng user chạy ứng dụng; chọn tên/path tránh xung đột giữa instance và lần restart.
- Xem lại `-Xmx` trong tổng memory budget, kể cả metaspace, direct buffers, native memory và thread stacks.
- Đảm bảo HPROF được bảo vệ như dữ liệu nhạy cảm và có quy trình chuyển sang máy phân tích riêng.
- Trên staging, gây Java heap OOM có kiểm soát và mở thử file HPROF thật.

Khi incident xảy ra:
- Phân biệt Java heap OOM, native/direct OOM và container/kernel kill.
- Đối chiếu GC logs, cgroup/RSS, exception và dòng tạo dump.
- Xác nhận dump được ghi hoàn tất, nằm đúng volume, không mất sau restart.
- Dùng MAT/VisualVM tìm retained objects và path to GC roots, rồi kiểm tra giả thuyết trên workload thật.

**Ghi nhớ:** `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath` là cách thu được **một ảnh chụp bộ nhớ có điều kiện** ở thời điểm JVM gặp một loại OOM được hỗ trợ. Chúng hữu ích để điều tra retention/leak trong Java heap, nhưng không bảo đảm hoạt động khi OS kill tiến trình, bộ nhớ ngoài heap cạn, I/O hỏng hay filesystem không lưu giữ. Muốn chẩn đoán đáng tin, phải kết hợp dump với GC log, JFR/metrics, kiểm tra hạ tầng và phân tích đường giữ tham chiếu.