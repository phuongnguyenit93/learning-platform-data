# 12.6 Lập kế hoạch thời gian dừng, dung lượng đĩa và quyền truy cập file dump

> **Ngữ cảnh:** Java 21, chẩn đoán rò rỉ hoặc tăng trưởng Java heap bằng **heap dump** định dạng HPROF. Mục tiêu bài này là lập kế hoạch vận hành an toàn trước khi tạo dump trên ứng dụng đang chạy: ảnh hưởng tới dịch vụ, dung lượng lưu trữ, quyền tạo/đọc tệp, tính bảo mật và quy trình khôi phục. Các ví dụ shell hướng tới Linux; nguyên tắc tương tự áp dụng cho Windows và container với đường dẫn, quyền và công cụ phù hợp.

## 1. Vì sao cần kế hoạch trước khi bấm tạo heap dump?

Heap dump là ảnh chụp các đối tượng Java trên heap cùng thông tin lớp và tham chiếu cần thiết để phân tích. Nó giúp truy vết đối tượng bị giữ lại, nhưng **không phải** bản sao toàn bộ RAM tiến trình: native memory, file descriptor, socket buffer và nhiều tài nguyên ngoài heap không được thể hiện đầy đủ. Không thể suy ra tổng RSS hay toàn bộ nguyên nhân `OutOfMemoryError` chỉ từ một HPROF.

Việc thu thập thường đụng ba giới hạn vận hành:

1. **Thời gian gián đoạn / độ trễ:** lệnh tạo heap dump trên JDK 21 được tài liệu `jcmd` đánh dấu **Impact: High**, tùy kích thước và nội dung heap. Mặc định lệnh yêu cầu **full GC** trước khi dump; quá trình quan sát và ghi có thể làm ứng dụng dừng hoặc chậm đáng kể, gây timeout, rớt health check và giảm throughput. Không có cam kết thời gian dừng cố định.
2. **Dung lượng đĩa và I/O:** dump có thể rất lớn, việc tạo tệp cần đủ chỗ trên **filesystem nhìn từ JVM đích** cùng băng thông ghi; nếu đĩa đầy sẽ ảnh hưởng cả ứng dụng, log, database hoặc node.
3. **Quyền truy cập và bảo mật:** dump có thể chứa chuỗi, đối tượng request, session, token, dữ liệu khách hàng và thông tin nội bộ còn nằm trong heap. Tài khoản chạy JVM cần quyền ghi, trong khi người khác chỉ nên được đọc khi thực sự có nhiệm vụ.

Vì vậy, yêu cầu dump là một **thao tác chẩn đoán có rủi ro vận hành**. Cần quyết định người phê duyệt, cửa sổ thực hiện, chỗ lưu, cách kiểm tra, nơi chuyển giao, thời hạn giữ và phương án hủy trước khi chạy lệnh.

## 2. Chọn cách thu thập phù hợp với tình huống

| Cách thu thập trên Java 21 | Thời điểm | Tác động / lưu ý | Khi nên dùng |
| --- | --- | --- | --- |
| `jcmd <PID> GC.heap_dump <file>` | Chủ động với JVM còn sống | **Impact: High**; mặc định yêu cầu full GC; ghi HPROF vào filesystem JVM đích | Cần snapshot có kiểm soát trước khi restart hoặc khi có dấu hiệu leak |
| `jcmd <PID> GC.heap_dump -all <file>` | Chủ động | Gồm cả đối tượng không còn reachable, không yêu cầu full GC **do riêng lệnh này**; vẫn là dump có chi phí cao | Cần nhìn cả đối tượng unreachable và hiểu sự khác biệt ngữ nghĩa |
| `jcmd <PID> GC.heap_dump -gz=1 <file.gz>` | Chủ động | Nén gzip mức 1 (nhanh nhất trong các mức 1–9), đổi CPU/thời gian lấy ít dung lượng hơn; không có tỷ lệ nén bảo đảm | Khi hạn chế dung lượng, đã thử trên workload tương tự |
| `-XX:+HeapDumpOnOutOfMemoryError` với `-XX:HeapDumpPath` | Tự động khi JVM phát sinh OOME thuộc trường hợp hỗ trợ | Cần cấu hình **trước khi khởi động**; sự cố có thể khiến dump không kịp ghi (hết đĩa, JVM bị kill, quyền sai) | Muốn có bằng chứng khi lỗi tái hiện không thể canh đúng lúc |

**Không nhầm `-all` với chế độ “không dừng dịch vụ”.** Tùy chọn này thay đổi tập đối tượng và bỏ yêu cầu full GC mặc định, nhưng thao tác dump vẫn có thể chặn JVM và kéo dài. `-gz=1` cũng không phải cách bảo đảm giảm tổng thời gian vì nén tiêu thụ CPU.

Nếu mục tiêu chỉ là biết xu hướng tăng heap, hãy cân nhắc bắt đầu bằng **GC logs, chỉ số heap theo thời gian, JFR hoặc quan sát telemetry**. `GC.class_histogram` có thể hỗ trợ điều tra nhưng cũng được `jcmd` xếp **Impact: High**. Chỉ nâng lên heap dump khi giá trị bằng chứng phù hợp với chi phí vận hành.

## 3. Lập ngân sách thời gian và tác động tới dịch vụ

### 3.1. Tách ba thời lượng

- **Thời gian xử lý yêu cầu dump:** từ khi phát lệnh đến lúc `jcmd` trả kết quả; bao gồm việc phối hợp với JVM, GC nếu được yêu cầu, lấy snapshot và ghi tệp.
- **Thời gian ứng dụng mất khả năng đáp ứng / bị chậm:** đo bằng metrics thực tế (request latency, error rate, health checks, throughput). Không được tự động coi nó bằng toàn bộ wall-clock thời gian của lệnh hoặc chỉ thời gian GC.
- **Thời gian xử lý sau dump:** kiểm tra dung lượng, checksum, di chuyển, mã hóa, phân tích; có thể tiếp tục gây I/O pressure nếu lưu cùng đĩa với ứng dụng.

Ước lượng kỹ thuật sơ bộ bằng **dung lượng dump dự kiến / băng thông ghi duy trì đo thực tế**, cộng chi phí JVM/GC và contention. Đây là đầu mối để đặt **cửa sổ thao tác**, không phải upper bound hay SLA.

**Ví dụ tính toán, chỉ để lập kế hoạch:** Nếu một HPROF dự kiến cỡ 8 GiB, thiết bị ghi duy trì khoảng 150 MiB/s, riêng khối lượng dữ liệu ghi đã có tỷ lệ `8192 MiB / 150 MiB/s ≈ 55 giây`. Full GC, định dạng hóa dữ liệu, tranh chấp I/O và throttling có thể làm tổng thời gian lớn hơn nhiều. Không được kết luận “pause đúng 55 giây”.

### 3.2. Bản kế hoạch trước khi thực thi

Trước khi dump một service production, thống nhất các điểm sau:

- **Mục tiêu bằng chứng:** snapshot đang tăng heap, trước restart, hay tự động khi OOME? Cần một hay nhiều snapshot và thời điểm nào có dữ liệu đại diện?
- **Ngưỡng tác động chấp nhận được:** SLO/p95/p99, request timeout, readiness/liveness probes, ngân sách lỗi, số replica còn phục vụ và khả năng drain traffic.
- **Khung giờ:** ưu tiên giờ ít tải; thực hiện từng instance nếu chạy nhiều replica, giữ capacity dự phòng. Có người theo dõi metrics và biết khi nào dừng chiến dịch.
- **Phương án giảm ảnh hưởng:** chuyển lưu lượng khỏi instance cần dump nếu kiến trúc cho phép; điều tra trên replica cô lập có trạng thái/tải đại diện; thử trước trong staging với cùng collector/JDK/loại storage.
- **Kịch bản dự phòng:** nếu dump kéo dài, error rate tăng hoặc volume gần đầy, quy trình rollback/traffic switch/restart phải sẵn sàng. Việc dừng lệnh chẩn đoán không nhất thiết hủy tức thì công việc đang diễn ra bên trong JVM.
- **Điểm dừng ra quyết định:** xác định ai được phép đánh đổi availability để giữ bằng chứng, ai xem trạng thái hệ thống, ai có quyền xử lý file nhạy cảm.

**Quan trọng:** Test với heap nhỏ không dự báo chính xác thời lượng dump cho heap lớn; bản build Java, GC, số đối tượng, tỷ lệ còn sống, tốc độ đĩa, tải và dạng storage đều ảnh hưởng. Thời gian đo trong staging là tham chiếu, không phải cam kết.

## 4. Lập ngân sách dung lượng đĩa

### 4.1. Phân biệt `-Xmx`, heap đang dùng và kích thước HPROF

- `-Xmx` là **giới hạn heap tối đa**, không phải kích thước dump chắc chắn.
- **Used heap** là chỉ số heap đang dùng tại thời điểm đo; snapshot sau full GC có thể khác đáng kể so với trước.
- **HPROF file size** phụ thuộc số và dạng đối tượng, metadata, tham chiếu, lựa chọn `-all` và nén; không có công thức chính xác “`HPROF = Xmx`”.
- Nếu bật `-gz`, cần biết cả dung lượng **đầu ra nén** và khả năng công cụ phân tích đọc trực tiếp hay cần giải nén ra volume khác.

Hãy lấy kích thước từ **dump thật của tải tương tự** nếu có. Khi chưa có, dành buffer bảo thủ và áp dụng giới hạn vận hành; hệ số như **1,5–2 × `-Xmx` cho mỗi dump chưa nén** chỉ là *heuristic ban đầu* để dự trù, **không bảo đảm đủ trong mọi hệ thống**. Điều chỉnh bằng phép đo HPROF thật, các quota và headroom thực tế.

Công thức ngân sách hữu ích:

```text
RequiredFreeSpace =
    (số dump dự kiến đồng thời × dung lượng dự kiến mỗi dump)
  + chỗ cho log/temporary/ứng dụng trong cửa sổ
  + headroom chống sai số
```

**Ví dụ:** JVM `-Xmx8g`, chưa có dump mẫu. Chọn giả định dự phòng 1,5 × 8 GiB = **12 GiB/dump**. Muốn giữ **hai** bản chụp cùng lúc và chừa thêm **4 GiB** cho headroom hoạt động của volume → dự trù tối thiểu **28 GiB khả dụng** trên volume được chỉ định (`2 × 12 + 4`). Đây là **quy tắc ngân sách minh họa**; cần tăng nếu dữ liệu đo, filesystem quota hoặc tải log yêu cầu.

### 4.2. Kiểm tra đúng volume và giới hạn

Trên Linux, thực hiện ở môi trường mà **JVM đích thực sự nhìn thấy đường dẫn**; ví dụ giả định service dùng `/srv/heapdumps`:

```bash
df -h /srv/heapdumps
df -i /srv/heapdumps
ls -ld /srv/heapdumps
```

`df -h` cho biết còn bao nhiêu byte trên filesystem, `df -i` cho biết inode; cả hai **không thay thế** kiểm tra disk quota của user, PVC quota, ephemeral storage limit, policy của nền tảng hoặc dung lượng dành cho log. Có đĩa trống trên host cũng không đồng nghĩa volume mount trong container còn chỗ.

Khi chạy trong container/Kubernetes:

1. Phân biệt đường dẫn **trong container** với đường dẫn **trên node/host**; dùng absolute path tồn tại và writable trong container JVM.
2. Xem volume đó là **ephemeral filesystem** hay persistent/attached volume. Nếu pod bị thay, dump trên filesystem tạm có thể mất; cần phương án xuất file trước khi pod terminate.
3. Tính cả giới hạn **ephemeral-storage**, quota, write throughput và chính sách admission. File lớn có thể kích hoạt eviction ngay cả khi host còn dung lượng.
4. Đặt lịch truyền file ra nơi lưu riêng; không nên để dump giữ lâu trên cùng volume dùng cho logs hoặc dữ liệu quan trọng.
5. Với image Java tối giản chỉ có JRE, `jcmd` có thể không sẵn; chuẩn bị bộ JDK/tooling thích hợp và quyền attach **trước sự cố**.

Đối với máy Windows, phải kiểm tra dung lượng ổ đĩa tương ứng, ACL của thư mục và quyền của account chạy Windows service; ví dụ đường dẫn `D:\secure-dumps\heap-1234.hprof`. Không áp dụng nguyên xi lệnh `df`, `chmod`, `sudo`.

## 5. Quyền tạo, đọc và chia sẻ file dump

### 5.1. Ba lớp quyền độc lập

**(1) Quyền gửi lệnh cho JVM.** Theo tài liệu JDK 21, `jcmd` phải chạy trên cùng máy với JVM và dùng **effective user và group identifiers** phù hợp với tiến trình Java. PID cũng phải được nhìn thấy trong cùng môi trường/process namespace; `jcmd -l` từ host có thể không liệt kê JVM trong một Docker namespace riêng. Một số JVM chặn attach bằng `-XX:+DisableAttachMechanism`.

**(2) Quyền JVM ghi dump.** File được tạo qua tiến trình JVM đích, do đó **chính account chạy service** phải có quyền tạo và ghi trong thư mục đầu ra; quyền của người thao tác ở terminal không tự động cấp quyền cho JVM. Thư mục phải tồn tại từ trước và nằm trên volume đủ dung lượng.

**(3) Quyền người phân tích đọc/sao chép dump.** Chỉ các thành viên được giao xử lý sự cố mới được quyền truy cập. Có thể tách nhóm vận hành (được phép yêu cầu dump) khỏi nhóm phân tích (được phép truy cập bản sao đã chuyển giao).

### 5.2. Chuẩn bị thư mục trên Linux (ví dụ)

Giả sử JVM chạy dưới account và group đều tên `app`, quản trị viên chuẩn bị:

```bash
sudo install -d -o app -g app -m 0700 /srv/heapdumps
sudo -u app test -w /srv/heapdumps
ls -ld /srv/heapdumps
```

`0700` chỉ cho owner truy cập directory; quyền và UID/GID phải thay theo thực tế. Dùng ACL nếu quy trình cần người đọc bổ sung. Nếu cấu hình `umask`, hãy cấu hình cho **tiến trình service/JVM lúc khởi động**, không nghĩ rằng đổi `umask` ở terminal đang gọi `jcmd` sẽ tự kiểm soát quyền file JVM sinh ra.

Giữ thư mục ngoài public web root, shared temp không kiểm soát, thư mục source code và nơi log tự động được gửi tới nhiều bên. Hạn chế truy cập theo **least privilege**, mã hóa khi lưu hoặc truyền, kiểm soát audit và thời hạn lưu trữ. **Không đính kèm HPROF trực tiếp vào ticket công khai, chat hoặc repository.**

### 5.3. Xác minh trước khi ghi

- Người thao tác có thể attach đúng JVM/PID và đúng JDK; account service có thể ghi vào thư mục.
- Tên file mới **duy nhất**, tránh đụng file hiện có. `GC.heap_dump` trên JDK 21 mặc định **không overwrite** file có sẵn; đừng bật `-overwrite` tùy tiện.
- Thư mục không có symlink/đường dẫn dễ bị điều hướng tới nơi không được phép; mount và owner đúng theo cấu hình đã duyệt.
- Có người chịu trách nhiệm cấp quyền cho bước copy, ghi checksum và xóa khi hết hạn; không biến một file chẩn đoán ngắn hạn thành kho lưu vô thời hạn.

## 6. Quy trình thực thi có kiểm soát bằng `jcmd`

Các ví dụ dưới đây **chỉ là runbook minh họa**. Thay `<PID>`, account, tên file, đường dẫn và cửa sổ thời gian bằng giá trị đã xác minh. Các lệnh thực hiện **trên host/container sở hữu JVM**, với quyền hợp lệ, sau khi có đủ ngân sách thời gian và đĩa.

### 6.1. Preflight

```bash
java -version
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.flags
df -h /srv/heapdumps
df -i /srv/heapdumps
```

- `java -version` ở shell chỉ là tham khảo; `jcmd <PID> VM.version` cho biết JVM đích, `VM.flags` giúp biết tùy chọn heap đã cấu hình.
- Xác nhận PID bằng service manager/process list, nhất là khi trong container. Tránh gửi lệnh theo main-class hoặc PID `0` vì có thể khớp **nhiều JVM**, trong khi mục tiêu là một tiến trình.
- Đừng đọc lệnh `GC.heap_info` như một phép đo dung lượng HPROF tương lai; nó cho thống kê heap tại thời điểm quan sát.
- Khi cần cú pháp thực tế mà JVM hỗ trợ, chạy `jcmd <PID> help GC.heap_dump`; bộ công cụ nên cùng phiên bản JDK với target.

### 6.2. Thu thập một HPROF không nén

```bash
jcmd <PID> GC.heap_dump /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
```

Chuỗi thời gian trong tên file là **ví dụ**, phải thay bằng thời điểm thu thập thật và kiểm tra file chưa tồn tại. Dùng đường dẫn tuyệt đối; file sẽ xuất hiện trong namespace filesystem của JVM, không phải mặc nhiên trên máy của người quản trị.

Đo thời điểm bắt đầu/kết thúc lệnh, quan sát latency, error rate, node I/O, dung lượng đĩa và health probes trong toàn bộ cửa sổ. Dữ liệu liên quan phải được ghi cùng **version JDK, GC, `-Xmx`, PID, instance/pod, thời điểm, tải và cấu hình dump**, để sau này diễn giải đúng.

### 6.3. Tùy chọn nén và lấy thêm đối tượng

```bash
jcmd <PID> GC.heap_dump -gz=1 /srv/heapdumps/heap-<PID>-20261029T101500Z.hprof.gz
jcmd <PID> GC.heap_dump -all /srv/heapdumps/heap-<PID>-20261029T103000Z.hprof
```

Đây là **hai ví dụ cho hai mục đích khác nhau**, không phải khuyến khích chụp ba dump liền nhau trên production. `-gz=1` ghi gzip và có trade-off CPU; `-all` giữ cả đối tượng unreachable, khác với snapshot reachable sau full GC. Nếu dùng `-all` khi phân tích retention, phải biết rằng tập đối tượng bao gồm cả object đã mất tham chiếu nhưng chưa được GC thu hồi.

**Không dùng `-all` hoặc nén chỉ để né khung bảo trì khi chưa đo được tác động.**

### 6.4. Kiểm tra đầu ra và bàn giao

```bash
ls -lh /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
stat /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
sha256sum /srv/heapdumps/heap-<PID>-20261029T100000Z.hprof
df -h /srv/heapdumps
```

Thành công nghĩa là **lệnh trả về thành công, file tồn tại và có kích thước hợp lý**, có thể được công cụ phân tích HPROF tương thích mở, checksum ở nơi nhận khớp với nguồn. Không xem file nonzero bất kỳ là bằng chứng đầy đủ: ghi thất bại giữa chừng có thể để lại file hỏng hoặc không hoàn chỉnh.

Sau khi copy bằng kênh truyền được phép, tính lại checksum ở nơi nhận. Chỉ xóa bản nguồn khi chủ sở hữu sự cố đã xác nhận bản sao có thể đọc được, việc bàn giao thành công và policy cho phép. Không để thao tác copy khiến cùng volume phát sinh đỉnh I/O ngay sau dump.

## 7. Chuẩn bị tự động khi `OutOfMemoryError`

Thay vì cố chờ `OutOfMemoryError` rồi mới chạy `jcmd`, có thể bật hai cờ ở startup (đường dẫn là directory được tạo và phân quyền trước):

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/srv/heapdumps/ \
     -Xmx2g -jar app.jar
```

`-XX:+HeapDumpOnOutOfMemoryError` mặc định tắt; `-XX:HeapDumpPath` định vị tệp/thư mục dump. Không chỉ dựa vào default working directory vì thường khó biết hoặc không writable; với đường dẫn directory tồn tại, HotSpot có thể đặt tên mặc định theo PID. Kiểm tra thực tế với đúng JDK/image/service manager mà bạn triển khai.

Giới hạn cần nhớ:

- OOME không nhất thiết là Java heap leak; có thể do giới hạn heap quá thấp, metaspace/native resources hoặc memory pressure của nền tảng.
- JVM/pod bị **OOMKilled/SIGKILL** có thể chết trước khi Java kịp phát ra OOME và ghi dump.
- Nếu sự cố do đĩa hoặc volume đã đầy, file dump rất có thể không được tạo; một cờ không thay thế kế hoạch capacity.
- Dump phát sinh tự động **trong thời điểm hệ thống đang lỗi** có thể kéo dài thời gian phục hồi. Phải tính chuyện health checks, restart policy và nơi bảo toàn artifact.
- Nếu JVM khởi động lại nhiều lần, cần chính sách naming, quota và retention để không tích tụ hàng loạt dump.
- Không dùng việc cố ý gây OOME trên production làm cách “kiểm tra cấu hình”; thử trên môi trường an toàn trước.

## 8. Thực hành nhỏ có thể chạy trên JDK 21

Dùng chương trình mẫu sau trong máy hoặc container thử nghiệm; nó giữ khoảng 8 MiB mảng byte trên Java heap để người học chụp một dump **không chứa dữ liệu thật**.

Tạo file **`HeapDumpLab.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapDumpLab {
    private static final List<byte[]> ROOTS = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 8; i++) {
            ROOTS.add(new byte[1_048_576]);
        }

        System.out.println("READY: retained " + ROOTS.size() + " MiB");
        System.out.println("Press ENTER to exit");
        System.in.read();
        System.out.println("DONE");
    }
}
```

**Terminal A (interactive, giữ chương trình chờ nhập):**

```bash
javac HeapDumpLab.java
java -Xms32m -Xmx64m HeapDumpLab
```

**Stdout của chính chương trình**, sau khi bạn nhấn ENTER để kết thúc:

```text
READY: retained 8 MiB
Press ENTER to exit
DONE
```

Nếu stdin bị đóng ngay, chương trình có thể thoát trước khi chụp; hãy chạy trong terminal tương tác. `8 MiB` là dung lượng **mảng được giữ tham chiếu**, không phải lời hứa file HPROF đúng 8 MiB.

**Terminal B (trong khi Terminal A còn chờ):**

```bash
jcmd -l
jcmd <LAB_PID> GC.heap_dump /tmp/heap-lab-unique.hprof
ls -lh /tmp/heap-lab-unique.hprof
```

Thay `<LAB_PID>` bằng PID của `HeapDumpLab` xác định từ danh sách trên; dùng đường dẫn duy nhất ở thư mục thử nghiệm có quyền ghi. Học viên đo thời gian dump thực tế, kích thước HPROF và thử so sánh khi tăng số mảng; không cần OOME để luyện quy trình. **Không gửi file lab này lên dịch vụ công cộng.**

Đối với môi trường có quyền chặt, ưu tiên tạo thư mục riêng `0700` thay cho `/tmp`; `/tmp` ở đây chỉ dùng làm ví dụ thực hành cục bộ.

## 9. Mẫu phiếu phê duyệt và bàn giao

Mỗi lần dump production nên có một bản ghi ngắn, đủ để người khác tái hiện quyết định:

| Trường | Ví dụ minh họa |
| --- | --- |
| Mục tiêu / sự cố | Phân tích heap tăng sau 4 giờ tải |
| Service / JVM / GC | `payment-api`, Java 21, G1, PID đã xác thực |
| Người cho phép / người thực hiện | On-call chịu trách nhiệm và operator được cấp quyền |
| Cửa sổ | 01:00–01:30 UTC sau khi chuyển traffic |
| Ngưỡng dừng quan sát | Error rate hoặc độ trễ vượt ngưỡng đã thống nhất |
| Heap / dump dự kiến | `-Xmx8g`; dự trù 12 GiB mỗi dump, sẽ đối chiếu thực tế |
| Vị trí / free space | Volume riêng `/srv/heapdumps`, tối thiểu headroom đã duyệt |
| Quyền / phân loại | Service account ghi, nhóm phân tích được đọc bản sao, dữ liệu nhạy cảm |
| File / checksum / kích thước | Ghi sau khi tạo thành công |
| Nơi nhận / TTL | Kho riêng có audit, thời gian giữ theo policy |
| Kết quả vận hành | Wall-clock, p95/p99, error rate, mức sử dụng volume trước/sau |

Các giá trị trong bảng là **ví dụ**, không phải cấu hình mặc định cho mọi hệ thống. Khung giờ phải được chọn theo lịch sản phẩm và timezone thực tế.

## 10. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `jcmd` không thấy PID | Khác user, container PID namespace, quyền attach, JVM khác JDK/tool | Chạy cùng môi trường, kiểm tra process manager, effective UID/GID, `-XX:+DisableAttachMechanism` |
| Lệnh chạy nhưng không tạo được file | Đường dẫn không tồn tại, quyền **JVM** không đủ, file trùng, filesystem full/quota | Kiểm tra owner, mount, `df`, quota, tên duy nhất; xem thông báo `jcmd` |
| File nhỏ hoặc hỏng | Dump không hoàn tất, bị kill/evict, hết đĩa | Kiểm tra exit, log, kích thước, tool mở HPROF, checksum |
| Tạo dump làm service timeout | Full GC, độ lớn heap, write contention, ít replica dự phòng | Đo metrics, drain/đổi replica, lặp thử ở staging, chọn lại cửa sổ |
| Dump làm đầy volume logs | Chia sẻ volume, ước lượng chỉ từ used heap, quên giữ nhiều bản | Dùng volume riêng, tính số bản, tăng headroom, retention |
| Có `HeapDumpOnOutOfMemoryError` nhưng không thấy file | Crash/kill không theo đường Java OOME, PID đổi, đường dẫn không writable, hết chỗ | Kiểm tra startup flags, event của orchestrator và filesystem đúng pod/host |
| Sau khi copy file không mở được | Copy gián đoạn hoặc cần giải nén, bản ghi chưa hoàn thành | So checksum, dung lượng, kiểm tra HPROF/gzip, công cụ phân tích |
| Dump lộ trong artifact/ticket | Chia sẻ quá rộng, public bucket, backup tự động, ACL mặc định | Cô lập nguồn/đích, mã hóa, xác minh ACL, thu hồi quyền và xử lý theo quy trình sự cố |

Một **heap dump không xác nhận rò rỉ chỉ bằng kích thước lớn**. Để kết luận leak, cần bối cảnh thời gian, retained objects, GC và so sánh snapshot/tải. Bài này giới hạn ở **kế hoạch và thu thập an toàn**; phân tích dominator tree và GC root là bước chuyên sâu tiếp theo.

## 11. Checklist trước, trong và sau

**Trước khi chụp**

- [ ] Đã xác định mục tiêu, JVM/JDK/GC/PID, thời điểm tải đại diện.
- [ ] Đã có lịch tác động dịch vụ, số replica dự phòng, người theo dõi và ngưỡng xử lý.
- [ ] Đã dự trù kích thước *mỗi dump* × số lượng, băng thông và headroom, kiểm tra volume/quota đúng namespace.
- [ ] Account JVM có quyền ghi thư mục riêng; account operator có quyền attach hợp lệ.
- [ ] Đã thống nhất định danh file duy nhất, nơi nhận, mã hóa, người đọc và ngày hết hạn.

**Trong khi chụp**

- [ ] Chạy đúng một lệnh trên đúng PID; ghi mốc thời gian và tùy chọn.
- [ ] Theo dõi p95/p99, lỗi, CPU, GC, I/O, dung lượng đĩa, health checks.
- [ ] Ghi nhận mọi bất thường và quyết định can thiệp.

**Sau khi chụp**

- [ ] Xác nhận lệnh thành công, file hợp lệ và đúng vị trí.
- [ ] Ghi kích thước, checksum, JVM version và metadata điều tra.
- [ ] Chuyển giao qua kênh bảo mật; so checksum ở nơi nhận; cấp quyền tối thiểu.
- [ ] Theo dõi phục hồi latency/throughput và dung lượng volume.
- [ ] Xóa bản nguồn/bản sao khi đủ điều kiện policy; lưu dấu vết bàn giao và kết thúc.

## 12. Nguồn tham khảo

- [Oracle JDK 21 — `jcmd`, đặc biệt `GC.heap_dump` và lựa chọn `-all`, `-gz`, `-overwrite`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `java`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `DisableAttachMechanism`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle JDK 21 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)
