# 11.7. Giới hạn cột số liệu và định dạng experimental của jstat khi tự động hóa

## 1. Bài toán và kết quả cần đạt

`jstat` là công cụ đi kèm JDK để quan sát các thống kê của JVM HotSpot đang chạy, đặc biệt là mức sử dụng các vùng bộ nhớ và bộ đếm garbage collection (GC). Khi kiểm tra một tiến trình bị chậm hoặc có dấu hiệu áp lực heap, một vài lệnh `jstat` thường cho cái nhìn ban đầu rất nhanh. Tuy nhiên, **đầu ra của `jstat` không phải hợp đồng dữ liệu ổn định cho phần mềm giám sát tự động**.

Sau bài này, người học có thể:

- Chọn đúng nhóm cột của `-gc`, `-gcutil` và hiểu đơn vị phần trăm, KB, số lần, giây.
- Giải thích vì sao vị trí, số lượng, cách trình bày và ý nghĩa cột không được giả định cố định giữa các môi trường.
- Nhận diện ảnh hưởng của `-t`, `-h`, collector, phiên bản JDK, thời gian lấy mẫu và vòng đời PID.
- Thiết kế biện pháp kiểm tra schema và xử lý lỗi cho một công cụ phân tích tạm thời, đồng thời chọn JMX/JFR/GC log cho giám sát lâu dài.

**Ranh giới:** bài tập trung vào độ tin cậy của các cột số liệu và việc tiêu thụ đầu ra `jstat`. Phần chọn GC, tuning heap và phân tích pause chuyên sâu cần thêm dữ liệu khác.

## 2. Hiểu chính xác trạng thái “experimental”

Tài liệu lệnh `jstat` của Oracle JDK ghi rõ công cụ thuộc diện **experimental and unsupported** và cảnh báo không nên viết script dựa vào định dạng xuất ra vì có thể thay đổi ở các bản phát hành tiếp theo. Từ đó suy ra:

1. Một lệnh chạy thành công hôm nay **không chứng minh** header, số cột, số chữ số thập phân hay thứ tự cột là API bất biến của mọi bản JDK.
2. Các tùy chọn và chức năng thống kê cũng có thể thay đổi, bị bỏ hoặc không tương ứng giống nhau khi đổi VM/collector.
3. Việc xuất ra bảng có vẻ “dễ parse” chỉ phục vụ quan sát; Google Sheets, shell, Java hay Python đọc được bảng không biến nó thành giao thức chính thức.
4. `experimental` **không có nghĩa** mọi con số đều sai. Nó nói về mức bảo đảm tương thích và hỗ trợ. Có thể dùng để chẩn đoán thủ công, nhưng không thể hứa một exporter thu thập metrics sản xuất sẽ không hỏng sau nâng cấp.

`jstat` đọc các thống kê mà JVM HotSpot instrumented công bố. Nó không thay thế trace sự kiện GC chi tiết, heap dump hay thước đo độ trễ ứng dụng. Một lần chụp số liệu có thể thiếu thời điểm pause vừa diễn ra giữa hai mẫu.

## 3. Những lệnh quan sát cơ bản

~~~bash
# Xem các chế độ mà bản jstat được cài đặt thực sự hỗ trợ
jstat -options

# Ví dụ PID 21891: 5 mẫu, cách nhau khoảng 1 giây, có uptime và lặp header
jstat -gcutil -t -h3 21891 1000 5

# Dung lượng/sử dụng vùng heap; đối chiếu với chỉ số phần trăm
jstat -gc 21891 1000 5

# Thông tin nguyên nhân GC nếu VM hỗ trợ tùy chọn này
jstat -gccause 21891 1000 5
~~~

Cú pháp thông thường là `jstat <statOption> [-t] [-hN] <vmid> [interval [count]]`. `interval` mặc định tính theo mili giây; có thể ghi rõ `1s` hoặc `1000ms`. Khi đã chỉ định `interval` mà không có `count`, lệnh tiếp tục lấy mẫu cho tới khi dừng hoặc tiến trình đích kết thúc; công việc tự động nên đặt số mẫu/timeout hữu hạn.

- `vmid` thường là PID JVM cục bộ, nhưng không phải mọi môi trường đều bảo đảm vmid trùng OS PID; tiến trình trong container/namespace có thể gây nhầm lẫn. Hãy xác nhận đúng JVM.
- `-t` thêm cột đầu `Timestamp`: số giây kể từ lúc JVM đích khởi động, **không phải** Unix epoch hoặc giờ đồng hồ.
- `-h3` lặp lại hàng tiêu đề sau mỗi ba mẫu; đừng coi hàng tiêu đề thứ hai là dữ liệu số.
- Thời gian lấy mẫu thực tế có jitter khi JVM hoặc hệ điều hành bận, không nhất thiết cách đều chính xác 1.000 giây.
- `-gcutil` thường tiện xem nhanh tỷ lệ; `-gc` cho thấy dung lượng được báo cáo bằng KB. Đừng suy một đại lượng tuyệt đối từ tỷ lệ mà không biết mẫu số và thời điểm đo.

Đầu ra chỉ là văn bản có các trường ngăn bằng khoảng trắng và được căn cột để người đọc nhìn. “Cột thứ 8” không tự mang ý nghĩa lâu dài.

## 4. Ý nghĩa các cột: tên quan trọng hơn vị trí

Các nhóm dưới đây mô tả cách đặt tên trong tài liệu Oracle JDK 25; **hệ thống chạy thực tế phải kiểm tra header và tài liệu của đúng JDK/VM**. Bảng là từ điển đọc số liệu, không phải danh sách cột bắt buộc có mặt trên mọi môi trường.

| Cột thường gặp | Chế độ | Nội dung và đơn vị | Giới hạn khi sử dụng |
| --- | --- | --- | --- |
| `S0`, `S1` | `-gcutil` | Mức sử dụng hai Survivor space, % dung lượng hiện tại | Không cho biết số byte tuyệt đối; cách biểu diễn vùng nhớ phụ thuộc collector |
| `E` | `-gcutil` | Mức sử dụng Eden, % dung lượng hiện tại | Tăng/giảm nhanh theo cấp phát và GC; một mẫu cao chưa chứng minh rò rỉ |
| `O` | `-gcutil` | Mức sử dụng Old space, % dung lượng hiện tại | Không đồng nghĩa % của toàn heap; dung lượng có thể đổi |
| `M` | `-gcutil` | Mức sử dụng Metaspace, % dung lượng hiện tại | Metaspace thuộc native memory; không coi như vùng Eden/Old |
| `CCS` | `-gcutil` | Tỷ lệ sử dụng Compressed Class Space, % | Không nên ép mọi collector/JVM phải xuất cùng trường |
| `S0C/S1C`, `S0U/S1U` | `-gc` | Dung lượng/đã dùng của Survivor space, KB | `C` và `U` là hai đại lượng khác nhau |
| `EC/EU`, `OC/OU` | `-gc` | Dung lượng/đã dùng của Eden và Old, KB | Giá trị công bố theo mô hình vùng nhớ của JVM |
| `MC/MU`, `CCSC/CCSU` | `-gc` | Committed/used Metaspace và Compressed Class Space, KB | “Committed” không đồng nghĩa “maximum” |
| `YGC`, `FGC` | `-gc`, `-gcutil` | Bộ đếm sự kiện young GC và full GC | Số đếm tích lũy; không suy toàn bộ sự kiện hay pause chỉ từ hai cột |
| `YGCT`, `FGCT`, `GCT` | `-gc`, `-gcutil` | Thời gian GC tích lũy được báo cáo, **giây** | Không phải trực tiếp độ trễ p95/p99, cũng không phải số lần GC |
| `LGCC`, `GCC` | `-gccause` | Nguyên nhân GC gần nhất/đang thực hiện (khi có) | Là trường văn bản; giá trị có thể có khoảng trắng, không parse như số |

Ví dụ, `OU = 300000` trong `-gc` được diễn giải là giá trị theo **KB**, còn `O = 75.00` trong `-gcutil` là **75% dung lượng Old hiện tại**. Không thể coi 75.00 là 75 MB. Khi cùng quan sát một thời điểm và cùng vùng được báo cáo, có thể kiểm tra tương đối `OU / OC × 100`; không coi phép tính này là đúng trong mọi trường hợp capacity bằng 0, số liệu không tương thích hoặc mẫu được lấy khác thời điểm.

Lưu ý tên cột không tự nói lên semantics của mọi collector. Các collector có concurrent phase hoặc mô hình heap khác nhau có thể khiến cách phân loại young/full/old không trùng cách bạn hình dung từ một collector thế hệ truyền thống. Các trường `YGC/FGC/GCT` là góc nhìn của instrumented counters, không phải một bản ghi sự kiện chuẩn hoá của tất cả collector. Khi thay collector, phải đối chiếu GC log/JFR và kiểm tra lại cách diễn giải.

### Ba kiểu số không được trộn

- **Gauge tại thời điểm đo:** `E`, `O`, `EU`, `OU`, `EC`, `OC`. Có thể tăng, giảm hoặc đổi mẫu số sau GC/resize.
- **Counter tích lũy:** `YGC`, `FGC`. Lấy hiệu giữa hai thời điểm trong **cùng một đời JVM**, không cộng trực tiếp các giá trị snapshot thành “số GC trong phút”.
- **Thời gian tích lũy:** `YGCT`, `FGCT`, `GCT`. Đơn vị giây; hiệu hai mẫu phản ánh mức tăng counter thời gian được công bố, không cho biết phân vị pause và không khẳng định tương đương tổng thời gian stop-the-world.

## 5. Các giả định dễ làm hỏng automation

| Giả định sai | Ví dụ hậu quả | Cách kiểm soát |
| --- | --- | --- |
| Cột thứ N luôn là `YGC` | Bật `-t` khiến mọi index dịch một vị trí | Dựa vào tên header ở mỗi phiên lấy mẫu |
| Header chỉ xuất hiện một lần | `-h3` đưa chữ `YGC` vào phép tính numeric | Nhận diện và bỏ/kiểm tra header lặp |
| Mọi bản JDK có cùng cột | Thêm/bớt hoặc đổi tên trường khiến gán nhầm metric | Ghi lại phiên bản, fingerprint header; fail closed khi không tương thích |
| Mọi ô đều là số hữu hạn | Giá trị trống/không áp dụng/`NaN` bị xuất nhầm thành 0 | Kiểm tra kiểu và khoảng hợp lệ; đánh dấu không có số liệu |
| Nhiều khoảng trắng có nghĩa nhiều cột rỗng | Parser tách theo một dấu cách sẽ lệch token | Tách các cột số bằng whitespace liên tiếp, kiểm tra đúng số trường |
| Mọi tùy chọn đều xuất dữ liệu thuần số | `-gccause` có nguyên nhân dạng chữ và khoảng trắng | Parser theo schema riêng; không parse `-gccause` như `-gcutil` |
| Timestamp là thời gian hệ thống | Dashboard vẽ uptime thành epoch sai năm | Dùng wall-clock riêng do collector ghi; Timestamp phục vụ đối chiếu uptime |
| Counter luôn tăng giữa hai lần chạy script | PID đã được tái sử dụng hoặc JVM khởi động lại | Gắn nhận diện tiến trình + start time; loại hiệu âm/reset |
| Chu kỳ 1000 ms luôn chính xác | Tính rate từ khoảng lấy mẫu danh nghĩa sai | Dùng thời gian thực hoặc hiệu uptime khi thích hợp |
| `GCT` là total STW pause latency | Alert độ trễ bị diễn giải quá mức | Dùng GC log/JFR và ứng dụng đo latency để xác minh |
| Mất mẫu hay thoát lỗi bằng 0 là “GC bình thường” | Dashboard che khuất sự cố attach, timeout, thiếu quyền | Phân biệt trạng thái thiếu dữ liệu với giá trị 0 |

Đặc biệt, không được viết parser dạng `awk '{print $8}'` hay `split(" ")[7]` rồi gắn nhãn `jvm_gc_events_total`. Nó chỉ tình cờ đúng với **một** cấu hình header cụ thể. Khi xuất metric dài hạn, lỗi gán nhãn âm thầm còn nguy hiểm hơn một lần chạy thất bại rõ ràng.

## 6. Phân tích hai mẫu mà không suy diễn quá mức

Đoạn dưới **là dữ liệu minh họa**, không phải output bắt buộc của mọi JDK:

~~~text
Timestamp S0    S1    E     O     M     CCS   YGC YGCT  FGC FGCT  GCT
10.0      0.00  50.00 80.00 55.00 90.00 70.00 10  0.400 0   0.000 0.400
20.0      0.00  30.00 10.00 56.00 90.00 70.00 12  0.520 0   0.000 0.520
~~~

Giữa hai mốc uptime 10 giây và 20 giây:

1. `ΔYGC = 12 - 10 = 2`: counter young GC tăng hai sự kiện.
2. `ΔYGCT = 0.520 - 0.400 = 0.120 s`: counter thời gian young GC tăng 120 ms.
3. `ΔGCT = 0.120 s` và `Δuptime = 10 s`: tỷ số mô tả theo counter là `0.120/10 × 100 = 1.2%` cho **cửa sổ minh họa này**.
4. `E` giảm 80% xuống 10% và `O` tăng 55% lên 56%; những thay đổi này phù hợp với hoạt động cấp phát/thu gom, nhưng **không đủ** để chứng minh các đối tượng cụ thể đã được promote, một leak, hay thời lượng pause lớn nhất.

Để đánh giá sức khỏe dịch vụ, đối chiếu tần suất GC, phân bố pause trong GC log/JFR, throughput và latency thực tế. Tỷ lệ counter thời gian GC trên uptime chỉ là tín hiệu sơ bộ; không tự quy đổi thành phần trăm CPU, tổng thời gian ngừng thế giới hay SLA latency.

## 7. Ví dụ Java 17+: parser dựa vào header cho dữ liệu thử nghiệm

Đây là **bài tập xử lý snapshot đã lưu**, nhằm cho thấy kiểm tra schema và từ chối dữ liệu sai; **không phải đề xuất viết exporter production bằng cách scrape `jstat`**. Chương trình không attach JVM, nên chạy được ở bất kỳ máy có JDK 17+. Nó kiểm tra header lặp, số trường, cột bắt buộc, số hữu hạn và reset counter. Các con số mô phỏng được cố ý cố định để có stdout kiểm chứng.

Lưu vào tệp `JstatHeaderDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class JstatHeaderDemo {
    record Sample(double uptime, long ygc, double ygct,
                  long fgc, double fgct, double gct) {}

    static double decimal(String[] data, Map<String, Integer> columns, String name) {
        double value = Double.parseDouble(data[columns.get(name)]);
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    static long integer(String[] data, Map<String, Integer> columns, String name) {
        long value = Long.parseLong(data[columns.get(name)]);
        if (value < 0) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    static List<Sample> parse(String output) {
        String[] signature = null;
        Map<String, Integer> columns = null;
        List<Sample> samples = new ArrayList<>();

        for (String line : output.lines().toList()) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String[] fields = trimmed.split("\\s+");

            if (fields[0].equals("Timestamp")) {
                if (signature != null && !Arrays.equals(signature, fields)) {
                    throw new IllegalArgumentException("Header changed");
                }
                signature = fields;
                columns = new HashMap<>();
                for (int i = 0; i < fields.length; i++) {
                    if (columns.put(fields[i], i) != null) {
                        throw new IllegalArgumentException("Duplicate column");
                    }
                }
                for (String required : List.of(
                        "Timestamp", "YGC", "YGCT", "FGC", "FGCT", "GCT")) {
                    if (!columns.containsKey(required)) {
                        throw new IllegalArgumentException("Missing " + required);
                    }
                }
                continue; // Header lap lai khong phai snapshot.
            }

            if (columns == null || fields.length != signature.length) {
                throw new IllegalArgumentException("Missing header or bad row width");
            }
            samples.add(new Sample(
                decimal(fields, columns, "Timestamp"),
                integer(fields, columns, "YGC"),
                decimal(fields, columns, "YGCT"),
                integer(fields, columns, "FGC"),
                decimal(fields, columns, "FGCT"),
                decimal(fields, columns, "GCT")
            ));
        }
        if (samples.size() < 2) {
            throw new IllegalArgumentException("Need at least two samples");
        }
        return samples;
    }

    public static void main(String[] args) {
        String fixture = """
            Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT GCT
            10.0 0.00 50.00 80.00 55.00 90.00 70.00 10 0.400 0 0.000 0.400
            Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT GCT
            20.0 0.00 30.00 10.00 56.00 90.00 70.00 12 0.520 0 0.000 0.520
            """;

        List<Sample> samples = parse(fixture);
        Sample first = samples.get(0);
        Sample last = samples.get(samples.size() - 1);

        if (last.uptime <= first.uptime || last.ygc < first.ygc
                || last.ygct < first.ygct || last.fgc < first.fgc
                || last.fgct < first.fgct || last.gct < first.gct) {
            throw new IllegalStateException("Restart, reset or invalid time window");
        }
        System.out.printf(Locale.ROOT,
            "dYGC=%d, dYGCT=%.3f s, dGCT=%.3f s, dt=%.1f s%n",
            last.ygc - first.ygc, last.ygct - first.ygct,
            last.gct - first.gct, last.uptime - first.uptime);
    }
}
~~~

~~~bash
javac JstatHeaderDemo.java
java JstatHeaderDemo
~~~

Stdout của fixture trên:

~~~text
dYGC=2, dYGCT=0.120 s, dGCT=0.120 s, dt=10.0 s
~~~

**Điểm cần hiểu trong mã:** `columns.get(name)` tìm vị trí theo header; code không sử dụng index cố định. Header lặp phải giống header ban đầu. Dữ liệu không khớp hợp đồng phiên chạy sẽ ném exception thay vì âm thầm đổi nghĩa metric. Chương trình chỉ biết các trường numeric của `-gcutil -t`, không xử lý văn bản `-gccause`. Nếu đầu ra từ bản JDK thực tế có header khác, phải xem đó là thay đổi schema và thẩm định lại trước khi dùng.

Chương trình demo cũng **không xác minh danh tính tiến trình, cùng một đời JVM, thời gian wall-clock hay kết nối tới target**: những điều này phải được quản lý ở tầng thu thập. Header trùng nhau hoàn toàn vẫn không bảo đảm tương thích ngữ nghĩa qua phiên bản HotSpot.

## 8. Nếu bắt buộc thu thập tạm từ jstat

Chỉ nên làm ở môi trường đã khóa phiên bản JDK/VM/collector và chấp nhận bảo trì khi nâng cấp, ví dụ một script chẩn đoán chạy trong ca xử lý sự cố. Hợp đồng tối thiểu:

1. **Nhận diện nguồn:** lưu `vmid/PID`, start time JVM, vendor/version của JVM đích, collector/flags khi có, phiên bản binary `jstat`, câu lệnh và thời điểm hệ thống ghi nhận mẫu. Không gộp các PID tái sử dụng.
2. **Chặn phiên chạy vô hạn:** dùng `count`, timeout cho tiến trình con, giới hạn số byte stdout/stderr, thu exit code. Nếu không attach được vì quyền người dùng, container, VM đã dừng hoặc perf counters không truy cập được, trả trạng thái “unavailable”.
3. **Đối chiếu cấu trúc:** giữ raw header, lập map tên cột, xác minh các trường bắt buộc chỉ xuất hiện một lần, số token phải khớp. Nếu schema thay đổi, báo lỗi có ngữ cảnh và lưu dữ liệu thô để phân tích.
4. **Kiểm tra giá trị:** chỉ chấp nhận số hữu hạn trong phạm vi hợp lý; không ép ô rỗng, lỗi parse, thiếu trường hay `NaN` thành 0. Các giá trị phần trăm cần được xem xét theo mô hình vùng nhớ của collector trước khi áp đặt ngưỡng.
5. **Tính delta đúng vòng đời:** xác minh JVM chưa restart, uptime tăng, counter không giảm; tách gauge và counter; gắn nhãn đơn vị, cửa sổ thời gian và số mẫu; không lấy chênh lệch từ hai JVM khác nhau.
6. **Kiểm soát nâng cấp:** thử lại với các JDK/collector thật sự vận hành và bộ fixture gồm header lặp, thêm/bớt cột, giá trị thiếu, timeout, restart; không tự động “sửa” bằng cách dịch chỉ số.
7. **Giám sát chất lượng thu thập:** theo dõi số lần fail/timeout/schema mismatch; dữ liệu vắng mặt phải hiển thị rõ, không được lấp bằng 0 hoặc giữ vô hạn giá trị cũ.

Có thể dùng `jstat -options` để khám phá tùy chọn có ở bản công cụ đang chạy; đó **không** phải sơ đồ cột máy đọc được. Thử lệnh trên đúng JVM trong staging trước khi dùng trong quy trình ứng cứu. Khi thay đổi cấu hình collector, hãy đánh giá lại cả ngữ nghĩa metric chứ không chỉ syntax của parser.

## 9. Công cụ thay thế theo nhu cầu

| Nhu cầu | Ưu tiên xem xét | Vì sao phù hợp hơn việc parse jstat |
| --- | --- | --- |
| Chẩn đoán nhanh trong phiên terminal | `jstat`, kết hợp `jcmd <pid> GC.heap_info` | Nhanh, thủ công, có thể đối chiếu nhiều góc nhìn; tránh cam kết schema dài hạn |
| Metrics định kỳ, dashboard và alert | JMX `MemoryMXBean`, `MemoryPoolMXBean`, `GarbageCollectorMXBean` qua exporter phù hợp | Giao diện quản lý kiểu dữ liệu rõ hơn; vẫn cần hiểu collector và quyền truy cập |
| Cần diễn biến và thời lượng từng GC/pause | Unified GC logging `-Xlog:gc*` hoặc Java Flight Recorder (JFR) | Mang theo ngữ cảnh sự kiện và thời gian; phân tích bằng công cụ tương ứng với JDK |
| Điều tra heap bất thường, nghi rò rỉ | `jcmd` để lấy thông tin heap/histogram; heap dump khi đã đánh giá tác động | Cung cấp cấu trúc đối tượng/heap sâu hơn; một số lệnh có thể tiêu tốn tài nguyên đáng kể |
| Đánh giá trải nghiệm dịch vụ | Latency p95/p99, error rate, throughput, CPU, memory + GC | Hiểu triệu chứng người dùng thực sự; GC chỉ là một nguồn bằng chứng |

Ví dụ lấy thông tin kiểm tra qua `jcmd` (chỉ khi được phép truy cập tiến trình):

~~~bash
jcmd 21891 VM.version
jcmd 21891 VM.flags
jcmd 21891 GC.heap_info
~~~

Khi dùng GC log, một cấu hình ví dụ với HotSpot hiện đại là:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Cú pháp logging và tập tag cũng cần đối chiếu với bản JDK triển khai. Không kích hoạt thao tác đắt như heap dump hoặc class histogram ở production chỉ để bù cho thiếu cột trong `jstat`.

## 10. Checklist tự kiểm tra và bài tập

Trước khi tin bất kỳ biểu đồ sinh từ `jstat`, hãy trả lời được: đang nhìn đúng JVM nào; JDK và GC nào; cột có trên output thật không; đơn vị là gì; mẫu nào bị thiếu; có restart không; thời gian lấy mẫu thực tế ra sao; thay đổi phiên bản được phát hiện bằng cách nào; chỉ số cần bổ trợ bằng GC log/JFR hoặc latency nào.

**Bài tập 1.** Giả sử một parser hard-code index 7 để lấy `YGC`. Sau khi thêm `-t`, hãy chỉ ra vì sao số đó có thể chuyển sang cột khác; sửa parser để tra cứu `YGC` bằng header.

**Bài tập 2.** Trong fixture Java, thay một lần lặp header bằng header thiếu `GCT` và chạy lại. Kết quả mong đợi: chương trình từ chối dữ liệu với `Header changed`, không phát số đo. Tiếp theo đổi một dòng số sang `NaN` ở trường `YGCT`: kết quả mong đợi là `Invalid YGCT`.

**Bài tập 3.** Sau một đợt triển khai, `YGC` giảm từ 150 xuống 3. Vì sao không được tính `ΔYGC = -147` rồi đưa vào biểu đồ? Hãy kiểm tra process start time/uptime và loại cửa sổ so sánh có restart.

**Bài tập 4.** `O` tăng đều còn độ trễ dịch vụ bình thường. Có đủ kết luận memory leak không? Không: cần lịch sử heap/GC sau thu gom, retention, GC log/JFR và bằng chứng từ ứng dụng.

**Thông điệp chính:** `jstat` là công cụ chẩn đoán hữu ích cho người đọc, nhưng định dạng experimental của nó không phải schema ổn định cho automation. Tôn trọng tên cột, đơn vị, vòng đời JVM, collector và trạng thái thiếu dữ liệu; dùng nguồn telemetry chuyên dụng khi cần số liệu bền vững.

## Tài liệu đối chiếu

- Oracle Java SE 25, [The jstat Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jstat.html) — cú pháp, cột dữ liệu, ví dụ `-t`/`-h` và cảnh báo experimental.
- Oracle Java SE 25, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) — hướng sử dụng `jcmd` và JFR cho điều tra JVM.
- Oracle Java SE 25, [The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — cấu hình Unified Logging qua `-Xlog`.
