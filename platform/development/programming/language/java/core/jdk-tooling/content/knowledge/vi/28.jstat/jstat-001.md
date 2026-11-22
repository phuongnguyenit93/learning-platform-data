# Lệnh jstat trong Java

`jstat` (Java Virtual Machine Statistics Monitoring Tool) là công cụ dòng lệnh thuộc JDK dùng để theo dõi thống kê của một Java HotSpot VM đang chạy. Công cụ có thể hiển thị thông tin về garbage collection (GC), mức sử dụng các vùng heap, class loading, JIT compiler và trạng thái biên dịch method theo từng mẫu thời gian.

`jstat` hữu ích khi cần quan sát nhanh một JVM đang hoạt động: Eden có liên tục đầy không, số lần young/full GC có tăng nhanh không, old generation có tiếp tục tăng sau GC không, Metaspace có tăng theo quá trình nạp class không, hoặc compiler đang biên dịch những method nào.

Trong tài liệu Oracle JDK 21, `jstat` được đánh dấu là **experimental and unsupported**. Tùy chọn và định dạng output có thể thay đổi hoặc bị loại bỏ ở các bản JDK tương lai. Dùng `jstat -options` để xem các thống kê mà JDK đang cài hỗ trợ, tránh viết automation phụ thuộc vào vị trí cột cố định, và cân nhắc JFR/JMX cho giám sát dài hạn.

## 1. jstat dùng để làm gì?

`jstat` đọc các bộ đếm và thống kê mà HotSpot cung cấp cho một JVM đã được instrument. Đây là công cụ lấy mẫu: mỗi lần output thể hiện trạng thái tại thời điểm truy vấn, còn nhiều cột là bộ đếm tích lũy kể từ khi JVM khởi chạy.

Các tình huống sử dụng phổ biến:

- Theo dõi tần suất young GC và full GC.
- Xem mức sử dụng Eden, Survivor, Old Generation và Metaspace.
- Quan sát heap capacity thay đổi theo thời gian.
- Kiểm tra số class đã load/unload và thời gian class loading.
- Theo dõi hoạt động của HotSpot JIT compiler.
- So sánh nhiều mẫu để xác định xu hướng trước khi tạo heap dump hoặc bật profiling sâu hơn.

`jstat` không phải profiler đầy đủ. Nó không cho biết object cụ thể nào đang giữ heap, không cung cấp call tree allocation, và không thay thế GC log hoặc JFR. Khi thấy chỉ số bất thường, hãy dùng kết quả đó để định hướng bước điều tra tiếp theo.

## 2. Cú pháp lệnh

Cú pháp tổng quát:

```sh
jstat -<statOption> [-t] [-h <lines>] <vmid> [<interval> [<count>]]
```

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `-<statOption>` | Nhóm thống kê cần xem, ví dụ `-gcutil`, `-gc` hoặc `-class` |
| `-t` | Thêm cột timestamp là thời gian đã trôi qua kể từ khi JVM đích khởi chạy |
| `-h <lines>` | Lặp lại dòng tiêu đề sau mỗi số mẫu được chỉ định |
| `<vmid>` | Virtual machine identifier của JVM cần theo dõi |
| `<interval>` | Khoảng thời gian giữa các lần lấy mẫu; mặc định tính bằng millisecond |
| `<count>` | Số mẫu cần lấy; nếu bỏ qua, tiếp tục cho đến khi JVM dừng hoặc lệnh bị kết thúc |

Ví dụ lấy 10 mẫu, mỗi mẫu cách nhau 1 giây:

```sh
jstat -gcutil 24680 1000 10
```

Trong ví dụ, `24680` là VMID minh họa. Thay bằng VMID của ứng dụng thực tế.

Nếu bỏ `interval`, công cụ chỉ in một mẫu. Nếu chỉ chỉ định interval mà không chỉ định count, công cụ tiếp tục in mẫu cho đến khi process đích dừng hoặc người vận hành nhấn Ctrl+C.

Interval phải là số dương; đơn vị mặc định là millisecond. Tài liệu JDK cũng mô tả đơn vị giây (`s`) hoặc millisecond (`ms`). Khi dùng giá trị không có hậu tố, ví dụ `1000`, nó được hiểu là 1.000 millisecond.

## 3. Xem các tùy chọn được hỗ trợ

Danh sách output option có thể khác theo JDK, vendor hoặc nền tảng. Kiểm tra trực tiếp:

```sh
jstat -options
```

Trợ giúp tổng quát:

```sh
jstat -help
```

Các output option thường gặp trong Oracle JDK 21:

| Option | Thống kê |
|---|---|
| `-class` | Hoạt động của class loader |
| `-compiler` | Hoạt động của HotSpot JIT compiler |
| `-gc` | Dung lượng và mức sử dụng các vùng heap cùng GC counters |
| `-gccapacity` | Capacity của generation và memory space |
| `-gccause` | Tóm tắt GC tương tự `-gcutil`, kèm nguyên nhân GC |
| `-gcnew` | Thống kê new generation |
| `-gcnewcapacity` | Capacity của new generation |
| `-gcold` | Old generation và Metaspace statistics |
| `-gcoldcapacity` | Capacity của old generation |
| `-gcmetacapacity` | Capacity của Metaspace |
| `-gcutil` | Tóm tắt phần trăm sử dụng các vùng cùng GC counters |
| `-printcompilation` | Thông tin method compilation của HotSpot |

Không phải mọi phiên bản JDK đều cung cấp cùng một tập option. Đặc biệt, các tên có chữ `perm` trong tài liệu Java rất cũ liên quan Permanent Generation; từ Java 8, PermGen đã được thay bằng Metaspace. Trên JDK 21, xem nhóm option Metaspace thay vì áp dụng hướng dẫn PermGen cũ.

## 4. Theo dõi GC nhanh bằng -gcutil

`-gcutil` là một trong những lựa chọn hữu ích nhất khi quan sát GC:

```sh
jstat -gcutil 24680 1000 10
```

Output minh họa:

```text
  S0     S1      E      O      M    CCS    YGC    YGCT    FGC    FGCT     GCT
  0.00  72.50  68.20  45.10  82.30  75.20    120   1.240      2   0.380   1.620
  0.00  72.50  91.40  45.10  82.30  75.20    120   1.240      2   0.380   1.620
  0.00  35.20   4.10  48.30  82.50  75.30    121   1.258      2   0.380   1.638
```

Các số liệu trên chỉ minh họa cách đọc, không phải output cố định hoặc ngưỡng hiệu năng chuẩn.

| Cột | Ý nghĩa |
|---|---|
| `S0` | Phần trăm sử dụng Survivor space 0 so với capacity hiện tại |
| `S1` | Phần trăm sử dụng Survivor space 1 so với capacity hiện tại |
| `E` | Phần trăm sử dụng Eden so với capacity hiện tại |
| `O` | Phần trăm sử dụng Old space so với capacity hiện tại |
| `M` | Phần trăm sử dụng Metaspace so với capacity hiện tại |
| `CCS` | Phần trăm sử dụng Compressed Class Space |
| `YGC` | Số young GC events |
| `YGCT` | Tổng thời gian young GC, tính bằng giây |
| `FGC` | Số full GC events |
| `FGCT` | Tổng thời gian full GC, tính bằng giây |
| `GCT` | Tổng thời gian GC, tính bằng giây |

`S0` và `S1` thường luân phiên vai trò giữa các lần young collection. Eden thường tăng dần khi ứng dụng cấp phát object và giảm sau young GC. Việc Eden gần 100% không tự động là lỗi; đây là hành vi bình thường trước một lần collection.

`O` cần được theo dõi theo xu hướng. Nếu old-space utilization tăng dần và vẫn cao sau nhiều lần GC, ứng dụng có thể đang giữ nhiều object lâu hơn, workload có thể tăng, hoặc heap đang chịu áp lực. Cần kiểm tra nhiều mẫu và workload trước khi kết luận memory leak.

`M` và `CCS` liên quan đến Metaspace và Compressed Class Space, không phải các vùng Java object heap thông thường. Nếu chúng tăng liên tục, hãy kiểm tra class loading, classloader lifecycle, proxy generation và việc redeploy ứng dụng.

## 5. Xem dung lượng và mức sử dụng theo KB bằng -gc

`-gc` hiển thị capacity và utilization dưới dạng KB cùng bộ đếm GC:

```sh
jstat -gc 24680 1000 5
```

Các cột phổ biến trên JDK 21:

| Cột | Ý nghĩa |
|---|---|
| `S0C` / `S1C` | Capacity hiện tại của Survivor space 0/1 |
| `S0U` / `S1U` | Dung lượng đang sử dụng của Survivor space 0/1 |
| `EC` / `EU` | Capacity và dung lượng sử dụng của Eden |
| `OC` / `OU` | Capacity và dung lượng sử dụng của Old space |
| `MC` / `MU` | Metaspace committed size và utilization |
| `CCSC` / `CCSU` | Compressed Class Space committed size và used size |
| `YGC` / `YGCT` | Số young GC và tổng thời gian young GC |
| `FGC` / `FGCT` | Số full GC và tổng thời gian full GC |
| `GCT` | Tổng thời gian GC |

Các cột capacity và used thường được biểu diễn bằng KB theo định nghĩa của từng option. Không nhầm committed/capacity với mức sử dụng thực tế của toàn bộ process. Java process còn có native memory, thread stacks, code cache, direct buffers và các vùng ngoài heap.

Có thể dùng `-gc` để xem dung lượng tuyệt đối thay vì phần trăm. `-gcutil` thuận tiện để nhìn xu hướng nhanh; `-gc` hữu ích khi cần quy đổi mức sử dụng sang KB và so sánh với giới hạn heap.

## 6. Theo dõi nguyên nhân GC bằng -gccause

`-gccause` hiển thị các cột giống `-gcutil` và bổ sung nguyên nhân của lần GC gần nhất cùng nguyên nhân GC hiện tại nếu có:

```sh
jstat -gccause 24680 1000 10
```

Hai cột bổ sung:

| Cột | Ý nghĩa |
|---|---|
| `LGCC` | Nguyên nhân của lần garbage collection gần nhất |
| `GCC` | Nguyên nhân của collection hiện tại nếu có |

Nguyên nhân có thể phụ thuộc collector và tình huống, ví dụ cấp phát không đủ vùng phù hợp hoặc yêu cầu collection từ ứng dụng. Giá trị cụ thể phải được đọc từ output thực tế.

Không suy luận rằng mọi full GC đều do memory leak. GC có thể được kích hoạt bởi allocation pressure, metadata pressure, explicit GC request hoặc chính sách của collector. Hãy kết hợp `LGCC`/`GCC` với GC logs và các chỉ số khác để hiểu nguyên nhân.

## 7. Xem generation capacity bằng -gccapacity

`-gccapacity` hiển thị dung lượng tối thiểu, tối đa và hiện tại của các generation/space:

```sh
jstat -gccapacity 24680
```

Các cột chính trên JDK 21:

| Cột | Ý nghĩa |
|---|---|
| `NGCMN` | Capacity tối thiểu của new generation |
| `NGCMX` | Capacity tối đa của new generation |
| `NGC` | Capacity hiện tại của new generation |
| `S0C` / `S1C` | Capacity hiện tại của Survivor space 0/1 |
| `EC` | Capacity hiện tại của Eden |
| `OGCMN` | Capacity tối thiểu của old generation |
| `OGCMX` | Capacity tối đa của old generation |
| `OGC` | Capacity hiện tại của old generation |
| `OC` | Capacity hiện tại của old space |
| `MCMN` / `MCMX` | Capacity tối thiểu/tối đa của Metaspace |
| `MC` | Metaspace committed size |
| `CCSMN` / `CCSMX` | Capacity tối thiểu/tối đa của Compressed Class Space |
| `CCSC` | Compressed Class Space committed size |

Các cột `YGC` và `FGC` cũng được cung cấp trong output này. Capacity có thể thay đổi khi heap mở rộng hoặc thu hẹp theo chính sách của JVM. Hãy phân biệt capacity hiện tại với mức sử dụng thực tế.

## 8. Theo dõi new generation bằng -gcnew

`-gcnew` tập trung vào young generation:

```sh
jstat -gcnew 24680 1000 10
```

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `S0C` / `S1C` | Capacity Survivor space 0/1 |
| `S0U` / `S1U` | Mức sử dụng Survivor space 0/1 |
| `TT` | Tenuring threshold hiện tại |
| `MTT` | Tenuring threshold tối đa |
| `DSS` | Desired survivor size |
| `EC` / `EU` | Eden capacity và mức sử dụng |
| `YGC` | Số young GC events |
| `YGCT` | Tổng thời gian young GC |

Tenuring threshold là ngưỡng tuổi mà object phải đạt trước khi được xem xét promote khỏi young generation. Giá trị thực tế có thể thay đổi theo tình trạng Survivor space và chính sách thích nghi của collector.

Nếu Survivor space không đủ chỗ cho các object sống sót, JVM có thể promote object sớm hơn. Hãy đọc `TT` cùng `DSS`, `S0U`, `S1U` và GC logs thay vì kết luận chỉ từ một cột.

## 9. Xem capacity của new generation bằng -gcnewcapacity

`-gcnewcapacity` hiển thị giới hạn và capacity của vùng young generation:

```sh
jstat -gcnewcapacity 24680
```

Các cột chính:

- `NGCMN`, `NGCMX`, `NGC`: capacity tối thiểu, tối đa và hiện tại của new generation.
- `S0CMX` và `S1CMX`: capacity tối đa của Survivor space 0/1.
- `S0C` và `S1C`: capacity hiện tại của Survivor space 0/1.
- `ECMX` và `EC`: capacity tối đa và hiện tại của Eden.
- `YGC` và `FGC`: số young/full GC events.

Dùng option này khi cần biết JVM có thể mở rộng young generation đến đâu và capacity hiện tại đang ở mức nào. Kết hợp với `-gcnew` để hiểu utilization và promotion behavior.

## 10. Theo dõi old generation bằng -gcold và -gcoldcapacity

`-gcold` hiển thị mức sử dụng old space và Metaspace liên quan:

```sh
jstat -gcold 24680 1000 5
```

Các cột thường gồm `MC`, `MU`, `CCSC`, `CCSU`, `OC`, `OU`, `YGC`, `FGC`, `FGCT` và `GCT`.

`-gcoldcapacity` hiển thị capacity của old generation:

```sh
jstat -gcoldcapacity 24680
```

Các cột chính:

- `OGCMN`: old generation capacity tối thiểu.
- `OGCMX`: old generation capacity tối đa.
- `OGC`: old generation capacity hiện tại.
- `OC`: old space capacity hiện tại.
- `YGC`, `FGC`, `FGCT`, `GCT`: bộ đếm và thời gian GC.

Nếu `OU` thường xuyên tăng sau các young GC và không giảm đáng kể sau collection phù hợp, hãy kiểm tra object lifetime, cache, queue, static reference và heap dump. Nhưng old space tăng cũng có thể là hành vi bình thường khi workload tăng hoặc heap đang mở rộng.

## 11. Theo dõi Metaspace bằng -gcmetacapacity

Metaspace lưu metadata của class và được cấp phát từ native memory. Nó khác Java object heap.

Chạy:

```sh
jstat -gcmetacapacity 24680
```

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `MCMN` | Metaspace capacity tối thiểu |
| `MCMX` | Metaspace capacity tối đa |
| `MC` | Metaspace committed size |
| `CCSMN` | Compressed Class Space capacity tối thiểu |
| `CCSMX` | Compressed Class Space capacity tối đa |
| `YGC` | Số young GC |
| `FGC` | Số full GC |
| `FGCT` | Tổng thời gian full GC |
| `GCT` | Tổng thời gian GC |

Nếu Metaspace tăng liên tục, kiểm tra classloader có được giải phóng sau redeploy hay không, ứng dụng có tạo class động liên tục không, hoặc framework có sinh proxy/lambda/class mới không.

Metaspace tăng không nhất thiết là leak. Class mới được load trong giai đoạn startup hoặc khi cache/framework khởi tạo có thể làm vùng này tăng rồi ổn định. Hãy xem xu hướng sau khi workload đã ổn định.

## 12. Theo dõi class loading bằng -class

`-class` hiển thị thống kê class loader:

```sh
jstat -class 24680 1000 10
```

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `Loaded` | Số class đã load |
| `Bytes` | Dung lượng class đã load, tính bằng KB |
| `Unloaded` | Số class đã unload |
| `Bytes` | Dung lượng class đã unload, tính bằng KB |
| `Time` | Thời gian thực hiện các thao tác load/unload class |

Các bộ đếm thường tích lũy từ lúc JVM bắt đầu. Nếu `Loaded` tăng liên tục nhưng `Unloaded` gần như không đổi, có thể ứng dụng đang load thêm class theo workload hoặc classloader không được giải phóng.

Để điều tra sâu, kết hợp `-class` với `-gcmetacapacity`, `jcmd VM.classloader_stats` và heap dump khi cần. Chỉ số class loading đơn lẻ không đủ để kết luận classloader leak.

## 13. Theo dõi JIT compiler bằng -compiler và -printcompilation

`-compiler` hiển thị thống kê tổng quát về HotSpot JIT compiler:

```sh
jstat -compiler 24680
```

Các cột thường gồm:

- `Compiled`: số compilation task đã thực hiện.
- `Failed`: số compilation task thất bại.
- `Invalid`: số compilation task bị invalidated.
- `Time`: thời gian thực hiện compilation.
- `FailedType`: loại compilation của lần thất bại gần nhất.
- `FailedMethod`: class và method của lần thất bại gần nhất.

`-printcompilation` hiển thị thông tin method compilation:

```sh
jstat -printcompilation 24680 1000 5
```

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `Compiled` | Số compilation task của method được biên dịch gần nhất |
| `Size` | Số byte bytecode của method |
| `Type` | Loại compilation |
| `Method` | Tên class và method; tên class dùng dấu `/` thay cho dấu chấm |

Các thống kê này giúp quan sát hoạt động JIT, nhưng không thay thế profiler CPU. Nếu muốn biết method nào tiêu thụ CPU nhiều, hãy dùng JFR, async-profiler hoặc công cụ profiling phù hợp.

## 14. Thêm timestamp và lặp lại header

`-t` thêm cột `Timestamp` ở đầu output. Giá trị là số giây đã trôi qua kể từ khi JVM đích khởi chạy, không phải giờ đồng hồ thực tế.

```sh
jstat -gcutil -t 24680 1000 5
```

`-h <n>` yêu cầu in lại dòng header sau mỗi n mẫu. Ví dụ:

```sh
jstat -gcutil -t -h 5 24680 1000 15
```

Cách này hữu ích khi output dài, terminal cuộn qua nhiều mẫu hoặc cần lưu file để xem lại. Header lặp lại giúp người đọc không phải cuộn ngược lên đầu file để nhớ ý nghĩa từng cột.

Không dùng timestamp này làm thời gian wall-clock để đối chiếu trực tiếp với log bên ngoài. Hãy ghi thêm thời điểm bắt đầu thu thập ở phía shell hoặc hệ thống giám sát nếu cần đối chiếu timeline.

## 15. Hiểu VMID và tìm JVM cần theo dõi

`vmid` là Virtual Machine Identifier. Với JVM cục bộ, thành phần thường dùng là LVMID (local VM identifier), thường nhưng không phải lúc nào cũng trùng với PID hệ điều hành.

Có thể tìm JVM bằng:

```sh
jps -l
```

Ví dụ:

```text
24680 com.example.JstatDemo
25120 com.example.OrderService
```

Sau đó chạy:

```sh
jstat -gcutil 24680 1000 10
```

Nếu `jps` không hiển thị process, có thể dùng công cụ hệ điều hành như `ps` trên Linux/macOS hoặc Task Manager/PowerShell trên Windows. Trong Docker, LVMID nhìn từ bên trong container có thể khác PID trên host; chạy công cụ trong đúng PID namespace.

Công cụ thường cần truy cập JVM trên cùng máy và có quyền attach phù hợp. Nếu attach không thành công, kiểm tra user/group, quyền hệ điều hành, cấu hình attach và môi trường container.

## 16. Theo dõi JVM từ xa bằng jstatd

`jstat` hỗ trợ VMID dạng remote. Cú pháp VMID tổng quát theo tài liệu:

```text
[protocol:][//]lvmid[@hostname[:port][/servername]]
```

Ví dụ:

```sh
jstat -gcutil 40496@remote.domain 1000
```

Với hostname và protocol mặc định, `jstat` sử dụng RMI. Trên host đích cần chạy `jstatd` và RMI registry được cấu hình để cung cấp thông tin instrumentation. Port mặc định của RMI registry thường là 1099 nếu không chỉ định port khác.

Remote monitoring không hoạt động chỉ bằng cách thêm hostname. Cần cấu hình `jstatd`, RMI, policy và quyền mạng đúng cách. Chỉ bật dịch vụ trong môi trường được kiểm soát, giới hạn mạng truy cập và tuân theo chính sách bảo mật của tổ chức.

Nếu chỉ giám sát JVM trên cùng máy, dùng local VMID đơn giản sẽ ít cấu hình hơn.

## 17. Ví dụ thực hành Java 17+: tạo allocation workload

Ví dụ sau liên tục cấp phát các mảng byte, giữ một cửa sổ object trong mảng hai chiều rồi thay thế chúng ở vòng lặp tiếp theo. Workload này giúp quan sát Eden và young GC trong khi chương trình chạy.

Tạo file `JstatDemo.java`:

```java
public class JstatDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");

        byte[][] window = new byte[128][];
        while (true) {
            for (int i = 0; i < window.length; i++) {
                window[i] = new byte[256 * 1024];
            }
            Thread.sleep(100);
        }
    }
}
```

Biên dịch:

```sh
javac JstatDemo.java
```

Chạy với heap cố định 128 MB:

```sh
java -Xms128m -Xmx128m JstatDemo
```

Stdout chính xác:

```text
READY
```

Chương trình tiếp tục chạy sau khi in READY. Mở terminal thứ hai, tìm PID bằng `jps -l`, rồi chạy:

```sh
jstat -gcutil <pid> 1000 10
```

Để xem dung lượng theo KB:

```sh
jstat -gc <pid> 1000 10
```

Để thêm timestamp và header định kỳ:

```sh
jstat -gcutil -t -h 5 <pid> 1000 15
```

Workload được thiết kế để tạo allocation liên tục, nhưng số GC event, tỷ lệ utilization và thời điểm collection phụ thuộc JDK, collector, heap configuration và máy đang chạy. Không dùng một con số output cố định làm tiêu chí pass/fail.

Sau khi thực hành, quay lại terminal chạy chương trình và nhấn Ctrl+C để dừng process.

## 18. Cách đọc xu hướng GC qua nhiều mẫu

Đừng kết luận từ một dòng output. Hãy quan sát nhiều mẫu trong một khoảng thời gian và đặt các cột cạnh nhau.

### Eden tăng rồi giảm

Nếu `E` tăng dần rồi giảm mạnh trong khi `YGC` tăng, thường có một young collection xảy ra. Sau collection, Survivor usage có thể tăng và một phần object có thể được promote sang old generation.

### Old space tăng dần

Nếu `O` hoặc `OU` tăng qua nhiều mẫu và không giảm đáng kể sau các collection phù hợp, hãy kiểm tra:

- Cache không giới hạn hoặc thiếu eviction.
- Queue/task backlog tăng.
- Object được giữ bởi static collection hoặc listener.
- Session/request lifecycle không được cleanup.
- Workload hoặc concurrency tăng so với baseline.

Đây là dấu hiệu cần điều tra, không phải bằng chứng duy nhất của memory leak.

### Full GC tăng nhanh

Theo dõi delta của `FGC` và `FGCT` giữa các mẫu. Nếu số full GC tăng nhanh và tổng thời gian full GC tăng đáng kể, ứng dụng có thể đang chịu memory pressure hoặc có vấn đề về allocation/retention.

Đọc thêm `LGCC`/`GCC` từ `-gccause` và đối chiếu GC logs để xác định nguyên nhân.

### Metaspace tăng

Nếu `M`, `MU` hoặc `MC` tăng liên tục, hãy kiểm tra class loading và classloader lifecycle. Nếu ứng dụng triển khai lại nhiều lần, kiểm tra classloader cũ có còn được giữ bởi thread, ThreadLocal, static reference hoặc framework registry không.

### GC time tăng

`YGCT`, `FGCT` và `GCT` là thời gian tích lũy tính bằng giây. So sánh mức tăng giữa hai mẫu để xem thời gian GC có tăng nhanh hay không. Cần kết hợp với thời gian thực và workload; chỉ số tổng tích lũy không tự thể hiện latency của từng request hoặc từng pause.

## 19. Các giới hạn và lưu ý khi phân tích

- `jstat` là experimental/unsupported trong tài liệu Oracle JDK 21; các option và format có thể thay đổi.
- Output là bảng text phân tách bằng whitespace, không phải API có schema ổn định.
- Không nên viết script phụ thuộc vị trí cột hoặc format output; nếu buộc phải parse, cần version-specific tests và chấp nhận phải sửa khi nâng JDK.
- Các cột generation/space phụ thuộc collector và cách JVM expose statistics; không suy luận cấu trúc heap giống nhau cho mọi collector.
- Một số cột là bộ đếm tích lũy từ khi JVM khởi chạy, không phải giá trị của riêng interval vừa qua.
- Timestamp `-t` là elapsed time kể từ khi JVM start, không phải wall-clock timestamp.
- Một mẫu đơn lẻ không đủ để kết luận memory leak hoặc GC problem.
- `jstat` không đo toàn bộ process RSS, native memory, direct buffer hoặc thread stack.
- Không dùng `jstat` thay thế GC logs, JFR hoặc heap dump khi cần nguyên nhân sâu.

Với workload production, chọn interval phù hợp. Interval quá ngắn làm output dày và khó đọc, trong khi thu thập liên tục có thể tạo thêm tải. Bắt đầu bằng 1–5 giây để quan sát xu hướng tổng quan, sau đó điều chỉnh theo sự cố và yêu cầu vận hành.

## 20. Công cụ thay thế và bổ trợ

| Công cụ | Thông tin | Khi nên dùng |
|---|---|---|
| `jcmd <pid> GC.heap_info` | Thông tin tổng quan heap | Kiểm tra heap snapshot nhanh |
| `jcmd <pid> GC.class_histogram` | Thống kê instance theo class | Tìm class chiếm nhiều heap |
| `jcmd <pid> GC.heap_dump` | Tạo heap dump | Phân tích object graph và retained heap |
| `jcmd <pid> VM.classloader_stats` | Thống kê classloader | Điều tra classloader/metaspace |
| JFR/JDK Mission Control | GC, allocation, CPU, thread và runtime events theo thời gian | Điều tra sự cố phức tạp hoặc chập chờn |
| JMX MemoryMXBean/GC MXBeans | Memory pool và GC metrics qua API | Tích hợp metric vào monitoring |
| GC logging | Sự kiện GC chi tiết qua log | Phân tích pause, cause, phase và collector |

Ví dụ kiểm tra heap bằng jcmd:

```sh
jcmd 24680 GC.heap_info
```

Kiểm tra classloader:

```sh
jcmd 24680 VM.classloader_stats
```

Bật GC logging cho lần khởi chạy tiếp theo:

```sh
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

GC logging ghi sự kiện chi tiết hơn so với mẫu thống kê của `jstat`. JFR cung cấp timeline và nhiều loại event khác, hữu ích khi cần liên hệ GC với allocation, CPU và thread behavior.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jstat: command not found` | Chưa cài JDK hoặc `JAVA_HOME/bin` chưa nằm trong PATH | Dùng đúng JDK và kiểm tra vị trí executable |
| `Could not find vmid` | VMID sai hoặc process đã dừng | Dùng `jps -l`/`ps` để xác định lại |
| Không thấy JVM trong `jps` | JVM nằm trong container namespace khác hoặc user không có quyền | Chạy trong đúng container/user |
| Attach bị từ chối | Quyền hệ điều hành hoặc attach mechanism bị chặn | Kiểm tra user/group, policy và cấu hình runtime |
| `jstat -options` không có option mong đợi | Khác phiên bản JDK, vendor hoặc collector | Dùng đúng option mà target JDK hỗ trợ |
| Cột Metaspace không xuất hiện như mong đợi | JDK cũ hoặc runtime/provider khác | Kiểm tra JDK version và `jstat -options` |
| Số YGC/FGC không đổi | Chưa xảy ra collection trong khoảng lấy mẫu | Tăng thời gian quan sát và kiểm tra workload |
| `O` tăng nhưng không giảm | Object được promote/giữ lại, workload tăng hoặc collector chưa thu hồi | So sánh nhiều mẫu, GC logs và heap histogram |
| `M` tăng liên tục | Class được load liên tục hoặc classloader không được giải phóng | Kiểm tra class loading và classloader statistics |
| Output khó đọc khi lưu lâu | Header chỉ xuất hiện ở đầu | Dùng `-h n` để lặp lại header |
| Script phân tích sai cột | Output text thay đổi theo JDK hoặc có cột khác | Không dựa vào parser cố định; dùng JMX/JFR/API có cấu trúc |
| Remote VMID không kết nối | `jstatd`/RMI chưa chạy hoặc network/policy chặn | Kiểm tra service, registry, port và policy |
| Chỉ số heap ổn định nhưng RSS tăng | Bộ nhớ ngoài heap hoặc native memory tăng | Kiểm tra direct memory, NMT và công cụ OS |

Khi công cụ không kết nối được, kiểm tra VMID, quyền và namespace trước. Khi số liệu bất thường, xác nhận bằng nhiều mẫu và công cụ khác trước khi thay đổi heap hoặc GC flags.

## 22. Quy trình giám sát JVM bằng jstat

Một quy trình thực hành:

1. Xác định ứng dụng, JDK version và PID/VMID.
2. Chạy `jstat -options` để xem các thống kê có sẵn.
3. Bắt đầu bằng `jstat -gcutil <vmid> 1000 10` để xem xu hướng GC.
4. Nếu cần dung lượng tuyệt đối, chạy `jstat -gc <vmid> 1000 10`.
5. Nếu full GC tăng, chạy `jstat -gccause` và đối chiếu GC logs.
6. Nếu old-space usage tăng, lấy histogram hoặc heap dump để tìm object retention.
7. Nếu Metaspace tăng, kiểm tra `-class`, `-gcmetacapacity` và classloader statistics.
8. Nếu cần xem JIT, dùng `-compiler` hoặc `-printcompilation`.
9. Ghi lại timestamp, workload, heap settings và collector cùng các mẫu.
10. Chuyển sang JFR/JMX/GC logs nếu cần giám sát dài hạn hoặc phân tích sâu.

Trong báo cáo sự cố, nêu rõ option đã chạy, VMID, interval, count, JDK version và khoảng thời gian lấy mẫu. Phân biệt giá trị phần trăm với KB, bộ đếm tích lũy với giá trị tức thời và thống kê heap với native/process memory.

## 23. Checklist

- [ ] Đã xác định đúng JVM và VMID.
- [ ] Đã kiểm tra output option bằng `jstat -options`.
- [ ] Đã hiểu cú pháp interval và count.
- [ ] Đã dùng `-gcutil` để xem utilization và GC counters.
- [ ] Đã dùng `-gc` khi cần dung lượng theo KB.
- [ ] Đã kiểm tra nguyên nhân GC bằng `-gccause` khi cần.
- [ ] Đã hiểu các option `-gcnew`, `-gcold` và `-gcmetacapacity`.
- [ ] Đã phân biệt class loading với JIT compilation statistics.
- [ ] Đã dùng `-t` và `-h` khi cần timestamp/header lặp lại.
- [ ] Đã so sánh nhiều mẫu trong workload tương đương.
- [ ] Đã không kết luận memory leak từ một mẫu đơn lẻ.
- [ ] Đã nhớ `jstat` là experimental/unsupported trong JDK 21.
- [ ] Đã tránh parse output như giao thức ổn định.
- [ ] Đã cân nhắc JFR, JMX, GC logs và jcmd cho phân tích sâu.

## 24. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jstat` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java SE 21 API — `java.lang.management`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html

`jstat` cung cấp cái nhìn nhanh về GC, heap spaces, class loading và JIT compilation của một HotSpot JVM. Hãy chọn đúng stat option, đọc các bộ đếm theo xu hướng và lấy nhiều mẫu trong workload tương đương. Vì công cụ được đánh dấu experimental/unsupported và output không phải định dạng ổn định, hãy dùng JFR, JMX, GC logs và các diagnostic command của `jcmd` khi cần giám sát hoặc phân tích chuyên sâu.