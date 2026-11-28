# Phân biệt reserved, committed và used khi đọc số liệu

Metaspace lưu metadata của class trong bộ nhớ native của JVM. Khi theo dõi Metaspace, ba số liệu **reserved**, **committed** và **used** mô tả ba lớp khác nhau của vùng nhớ. Chúng không thể thay thế cho nhau và cũng không đồng nghĩa với RSS hoặc tổng RAM mà tiến trình đang chiếm.

- **Reserved:** không gian địa chỉ ảo mà JVM dành trước cho Metaspace để có thể mở rộng về sau.
- **Committed:** phần vùng nhớ đã được JVM commit để allocator có thể sử dụng.
- **Used:** phần dung lượng trong vùng committed hiện đang được dùng để chứa metadata.

Vì vậy, reserved lớn không có nghĩa JVM đang dùng từng ấy RAM vật lý; committed lớn hơn used không tự động là rò rỉ; và used tăng liên tục mới là tín hiệu cần điều tra cùng vòng đời class loader, class unloading và workload.

## 1. Metaspace nằm ở đâu?

Từ Java 8, HotSpot dùng Metaspace trong native memory để lưu class metadata thay cho PermGen. Metaspace tăng trưởng theo nhu cầu và có thể lấy thêm vùng địa chỉ ảo khi cần. Nó không nằm trong Java heap, vì vậy chỉ nhìn `-Xmx` hoặc biểu đồ heap không đủ để đánh giá bộ nhớ metadata.

Các class được định nghĩa bởi class loader gắn với metadata và vùng lưu trữ do Metaspace quản lý. Khi class loader không còn được tham chiếu và đủ điều kiện unload, JVM có thể thu hồi metadata tương ứng trong một lần GC có xử lý class unloading.

Metaspace có allocator và quản lý chunk riêng. Một phần vùng nhớ đã commit có thể chưa chứa metadata hữu ích của ứng dụng tại thời điểm quan sát; nó có thể là phần trống trong chunk đã cấp phát hoặc không gian được giữ để tái sử dụng.

## 2. Reserved: vùng địa chỉ ảo được dành trước

Reserved biểu thị không gian địa chỉ ảo mà JVM đã đặt chỗ cho một vùng nhớ. Đây là cam kết về phạm vi địa chỉ có thể dùng, chưa phải bằng chứng rằng toàn bộ vùng đó đã được commit hoặc đã chiếm RAM vật lý.

Ví dụ minh họa:

| Trạng thái | Dung lượng |
| --- | ---: |
| Reserved | 512 MiB |
| Committed | 64 MiB |
| Used | 42 MiB |

Trong ví dụ, JVM dành 512 MiB không gian địa chỉ cho vùng Metaspace, nhưng mới commit 64 MiB và đang dùng 42 MiB metadata. Không thể kết luận tiến trình đã tiêu thụ 512 MiB RAM chỉ từ số reserved.

Reserved có thể lớn do cách JVM chuẩn bị không gian để tăng trưởng, do cấu hình class space hoặc do cách triển khai của JVM và nền tảng. Hãy so sánh số liệu trên cùng JDK, cùng cấu hình và cùng môi trường thay vì đánh giá một con số riêng lẻ.

## 3. Committed: phần vùng nhớ JVM đã commit

Committed là dung lượng JVM đã commit để Metaspace allocator có thể dùng. Nó thường bao gồm cả metadata đang sử dụng và phần dung lượng trống còn lại bên trong các chunk đã commit.

Trong ví dụ trên:

- 64 MiB đã được commit.
- 42 MiB đang được dùng.
- Khoảng 22 MiB còn lại là khoảng cách giữa committed và used ở phạm vi số liệu minh họa.

Khoảng cách này không mặc định là lãng phí hoặc rò rỉ. JVM có thể giữ các chunk đã commit để phục vụ những lần nạp class tiếp theo, tránh phải liên tục commit/uncommit vùng nhớ. Sau class unloading, used có thể giảm trong khi committed chưa giảm ngay.

Committed cũng không đồng nghĩa với resident set size (RSS). Trang nhớ đã commit có thể chưa được chạm đến và chưa hiện diện đầy đủ trong RAM vật lý. RSS là số đo ở cấp tiến trình/hệ điều hành, có phạm vi rộng hơn và bao gồm nhiều vùng nhớ khác ngoài Metaspace.

## 4. Used: metadata đang chiếm dụng

Used biểu thị lượng Metaspace hiện được allocator xem là đã sử dụng cho metadata. Đây thường là số cần theo dõi khi muốn biết lượng metadata đang sống tăng hay giảm.

Used có thể tăng khi:

- Ứng dụng nạp thêm class hoặc tạo thêm class loader.
- Framework sinh class động, proxy hoặc bytecode trong runtime.
- Ứng dụng triển khai plugin, hot reload hoặc nhiều deployment trong cùng JVM.
- Class loader cũ vẫn còn được tham chiếu nên class do nó định nghĩa chưa thể unload.

Used có thể giảm sau một GC có class unloading nếu class loader và các class tương ứng đã không còn được giữ sống. Việc giảm used phụ thuộc vào khả năng thu hồi metadata; chỉ gọi `System.gc()` không bảo đảm class loader sẽ unload.

Nếu used tăng theo từng chu kỳ deploy hoặc reload và không giảm sau các lần GC phù hợp, hãy điều tra class loader retention, thread context class loader, static reference, ThreadLocal, listener, cache, MBean và các object giữ class loader.

## 5. Quan hệ giữa ba số liệu

Với cùng một phạm vi đo và cùng thời điểm, có thể hình dung:

```text
Reserved
└── Committed
    ├── Used
    └── Committed but currently unused
```

Thông thường, trong cùng một phạm vi đo:

`Used <= Committed <= Reserved`

Đây là mô hình giải thích ở cấp vùng Metaspace; khi đọc báo cáo thực tế, cần so sánh đúng cùng category và cùng cách tính. Một số công cụ hiển thị riêng Metaspace metadata và Compressed Class Space, hoặc tổng hợp theo category khác nhau. Không lấy số ở hai phạm vi khác nhau rồi áp dụng bất đẳng thức như thể chúng là cùng một pool.

Các phép trừ giúp đặt câu hỏi:

- `Reserved - Committed`: bao nhiêu không gian đã dành nhưng chưa commit?
- `Committed - Used`: bao nhiêu dung lượng đã commit nhưng hiện chưa được dùng cho metadata?

Hai khoảng chênh lệch này mô tả trạng thái allocator, không tự đưa ra kết luận về rò rỉ hoặc áp lực RAM.

## 6. JMX `MemoryUsage`: đọc used, committed và max

Java Management API cung cấp `MemoryPoolMXBean` và `MemoryUsage`. Với HotSpot, pool thường có tên `Metaspace`; khi compressed class pointers được dùng, có thể thấy pool riêng `Compressed Class Space`.

`MemoryUsage` cung cấp:

| Getter | Ý nghĩa |
| --- | --- |
| `getUsed()` | Dung lượng hiện được dùng. |
| `getCommitted()` | Dung lượng đã commit. |
| `getMax()` | Giới hạn tối đa nếu xác định được; `-1` nghĩa là không xác định. |
| `getInit()` | Giá trị khởi tạo nếu xác định được; `-1` nghĩa là không xác định. |

Đối tượng `MemoryUsage` không có trường `reserved`. Vì thế, JMX `MemoryPoolMXBean` phù hợp để đọc used/committed/max, nhưng không đủ để lấy cả ba số reserved/committed/used từ một API duy nhất.

Ví dụ liệt kê các pool non-heap và in số liệu:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;

class MetaspaceUsage {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() != MemoryType.NON_HEAP) {
                continue;
            }

            String name = pool.getName();
            if (!name.contains("Metaspace") && !name.contains("Class Space")) {
                continue;
            }

            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                System.out.println(name + ": usage unavailable");
                continue;
            }

            System.out.printf(
                "%s: used=%.1f MiB, committed=%.1f MiB, max=%s%n",
                name,
                usage.getUsed() / (double) MIB,
                usage.getCommitted() / (double) MIB,
                formatMax(usage.getMax())
            );
        }
    }

    private static String formatMax(long max) {
        return max < 0 ? "undefined"
            : String.format("%.1f MiB", max / (double) MIB);
    }
}
```

Tên pool và cách JVM chia pool là chi tiết triển khai; code trên lọc theo tên thường gặp của HotSpot. Khi hỗ trợ nhiều JVM vendor, hãy in toàn bộ pool non-heap và xác định pool phù hợp theo tài liệu của JVM đó.

`MemoryMXBean.getNonHeapMemoryUsage()` trả số liệu tổng non-heap, có thể bao gồm Metaspace, Compressed Class Space, Code Cache và các vùng non-heap khác. Không dùng tổng non-heap làm số Metaspace riêng.

## 7. Reserved và committed qua Native Memory Tracking

Native Memory Tracking (NMT) của HotSpot theo dõi bộ nhớ native do JVM quản lý. NMT có thể báo cáo reserved và committed theo category, hữu ích để nhìn Metaspace cùng các vùng native khác.

Phải bật NMT khi khởi động JVM; không thể bật đầy đủ hồi tố cho một tiến trình đã chạy:

```text
-XX:NativeMemoryTracking=summary
```

Hoặc dùng mức chi tiết hơn khi cần chẩn đoán:

```text
-XX:NativeMemoryTracking=detail
```

NMT có overhead về bộ nhớ và CPU, đặc biệt ở mức `detail`. Chỉ bật mức cần thiết trong môi trường chẩn đoán hoặc kiểm thử đã đánh giá overhead.

Sau khi JVM chạy, lấy PID và xem summary:

```powershell
jcmd <pid> VM.native_memory summary scale=MB
```

Để so sánh thay đổi theo thời gian:

```powershell
jcmd <pid> VM.native_memory baseline
```

Chờ workload hoặc một chu kỳ deploy/reload, sau đó:

```powershell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

NMT thường trình bày `reserved` và `committed` theo category như `Class`, `Metaspace` hoặc `Compressed Class Space`, tùy phiên bản và cách JVM báo cáo. Đối chiếu category và phần con tương ứng; không cộng cả parent lẫn child vì có thể đếm trùng.

NMT summary không nhất thiết cung cấp cùng định nghĩa `used` như JMX `MemoryUsage`. Có thể dùng lệnh chẩn đoán Metaspace của HotSpot để xem thống kê allocator chi tiết hơn:

```powershell
jcmd <pid> VM.metaspace
```

Danh sách lệnh và tham số chẩn đoán có thể thay đổi theo JDK vendor/build. Kiểm tra lệnh được hỗ trợ trên JVM đang chạy bằng:

```powershell
jcmd <pid> help
```

## 8. Đọc số liệu từ một tình huống thực tế

Giả sử dashboard hiển thị:

| Thời điểm | Reserved | Committed | Used |
| --- | ---: | ---: | ---: |
| Sau startup | 512 MiB | 48 MiB | 31 MiB |
| Sau warm-up | 512 MiB | 64 MiB | 46 MiB |
| Sau deploy plugin | 512 MiB | 96 MiB | 78 MiB |
| Sau class unloading | 512 MiB | 96 MiB | 49 MiB |

Có thể diễn giải:

1. Reserved không đổi: vùng địa chỉ ảo dành cho Metaspace vẫn giữ nguyên.
2. Committed tăng: JVM đã commit thêm chunk để đáp ứng việc nạp metadata.
3. Used tăng sau deploy: plugin có thể đã nạp thêm class.
4. Used giảm sau class unloading: một phần metadata đã được thu hồi.
5. Committed vẫn ở 96 MiB: JVM đang giữ vùng đã commit để có thể tái sử dụng; điều đó không tự chứng minh có leak.

Nếu các lần deploy tiếp theo làm used tăng mãi và không giảm, cần kiểm tra class loader cũ có còn được giữ bởi thread, cache hoặc static reference không. Nếu used ổn định nhưng committed cao hơn, đó có thể chỉ là phần chunk được giữ để tái sử dụng.

## 9. Đừng nhầm Metaspace với toàn bộ non-heap hoặc RAM tiến trình

JVM quản lý nhiều vùng native/non-heap:

- Metaspace chứa class metadata.
- Compressed Class Space là vùng dành cho compressed class pointers trong cấu hình HotSpot phù hợp.
- Code Cache chứa mã máy do JIT compiler tạo.
- Thread stacks, direct buffers, GC structures và các native allocation khác cũng tiêu thụ native memory.

Do đó:

- Heap used thấp không có nghĩa tổng bộ nhớ JVM thấp.
- Non-heap used cao không đồng nghĩa Metaspace used cao.
- Metaspace committed không phải RSS.
- RSS không thể được suy ra bằng cách cộng riêng Metaspace used và heap used.

Khi điều tra tổng RAM tiến trình, kết hợp NMT, OS process metrics và JMX heap/non-heap. Đảm bảo các nguồn đo cùng thời điểm và hiểu phạm vi từng metric.

## 10. `MaxMetaspaceSize` và `MetaspaceSize` tác động thế nào?

Hai flag có tên gần nhau nhưng vai trò khác nhau:

| Flag | Vai trò |
| --- | --- |
| `-XX:MaxMetaspaceSize` | Giới hạn trên cho dung lượng Metaspace mà JVM có thể sử dụng; nếu metadata không thể cấp phát trong giới hạn, ứng dụng có thể gặp `OutOfMemoryError: Metaspace`. |
| `-XX:MetaspaceSize` | Ngưỡng ban đầu liên quan tới việc kích hoạt GC để thu hồi class metadata; JVM có thể điều chỉnh ngưỡng này theo hành vi runtime. Đây không phải giới hạn tối đa. |

Không diễn giải `MetaspaceSize` là lượng RAM khởi tạo được cấp phát hoặc là hard cap. Cũng không xem `MaxMetaspaceSize` là kích thước reserved virtual address space.

Chỉ đặt `MaxMetaspaceSize` sau khi đo workload, tốc độ nạp class và mức tăng trưởng theo thời gian. Giới hạn quá thấp có thể làm GC metadata diễn ra thường xuyên hoặc gây lỗi cấp phát khi ứng dụng cần thêm class. Trước khi tăng cap, xác định used tăng do workload bình thường, class generation hay class loader bị giữ sống.

## 11. Class unloading và dấu hiệu class loader leak

Metaspace thường tăng khi class được nạp. Việc class loader không còn được dùng là điều kiện quan trọng để metadata của các class do nó định nghĩa có thể được thu hồi.

Các dấu hiệu cần điều tra:

- Used tăng theo mỗi lần redeploy hoặc reload plugin.
- Số class loader tăng dần qua các chu kỳ.
- Sau GC có class unloading, used không giảm như dự kiến.
- Heap dump cho thấy class loader cũ còn reachable từ static collection, thread, ThreadLocal, executor, MBean hoặc cache.
- Framework tạo proxy/class động nhưng không giải phóng cache hoặc class loader tương ứng.

Có thể dùng các công cụ chẩn đoán HotSpot như:

```powershell
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
```

Kết hợp log class loading/unloading, JFR và heap dump khi cần tìm đường tham chiếu giữ class loader. Không kết luận class loader leak chỉ vì committed chưa giảm; theo dõi used và số class loader qua nhiều chu kỳ mới có ý nghĩa hơn.

## 12. Quy trình đọc số liệu có hệ thống

1. **Xác định metric:** dashboard đang hiển thị Metaspace used, committed, reserved, non-heap hay RSS?
2. **Xác định nguồn:** JMX, NMT, `jcmd VM.metaspace` hay OS monitor?
3. **Xác định phạm vi:** Metaspace, Compressed Class Space, category `Class` hay tổng native memory?
4. **So sánh theo thời gian:** lấy baseline sau startup/warm-up rồi đo sau workload, deploy và class unloading.
5. **Đối chiếu used với committed:** used tăng cho thấy metadata sống tăng; committed tăng mà used ổn định có thể là allocator mở rộng hoặc giữ chunk để tái sử dụng.
6. **Đối chiếu reserved:** reserved lớn một mình không chứng minh RAM bị chiếm hoặc leak.
7. **Kiểm tra class loader:** nếu used tăng kéo dài, xem số loader, class generation và các tham chiếu giữ loader.
8. **Đo cả process memory:** nếu RSS tăng nhưng Metaspace used ổn định, điều tra direct buffer, thread stack, code cache, GC và native library.

## 13. Những lỗi diễn giải thường gặp

| Cách hiểu sai | Cách hiểu đúng |
| --- | --- |
| Reserved 1 GiB nghĩa là JVM đã chiếm 1 GiB RAM. | Reserved là không gian địa chỉ ảo đã dành; chưa đồng nghĩa committed hoặc resident. |
| Committed luôn bằng RAM vật lý đang resident. | Committed là dung lượng JVM đã commit; RSS là số đo khác ở cấp hệ điều hành. |
| Committed lớn hơn used là memory leak. | Phần chênh lệch có thể là chunk trống được giữ để tái sử dụng. |
| Used giảm thì committed phải giảm ngay. | JVM có thể giữ committed chunks sau class unloading. |
| JMX `MemoryUsage` có thể trả reserved. | `MemoryUsage` cung cấp init, used, committed và max; không có reserved. |
| `MemoryMXBean.getNonHeapMemoryUsage()` chính là Metaspace. | Non-heap gồm nhiều pool, không chỉ Metaspace. |
| `MetaspaceSize` là hard cap. | `MaxMetaspaceSize` mới là giới hạn tối đa; `MetaspaceSize` là ngưỡng GC ban đầu có thể điều chỉnh. |
| RSS tăng chắc chắn do Metaspace. | RSS còn chịu ảnh hưởng của heap, direct memory, thread stacks, code cache và native allocations khác. |

## 14. Những điểm cần nhớ

- Reserved là vùng địa chỉ ảo đã dành; không phải RAM đã sử dụng.
- Committed là phần JVM đã commit để allocator dùng; không đồng nghĩa RSS.
- Used là metadata đang được dùng và là chỉ số quan trọng để theo dõi tăng trưởng class metadata.
- JMX `MemoryUsage` cho used/committed/max, không có reserved.
- NMT và `jcmd VM.native_memory` giúp xem reserved/committed theo category; `jcmd VM.metaspace` cung cấp góc nhìn allocator của HotSpot.
- Committed có thể giữ ở mức cao sau khi used giảm vì JVM tái sử dụng chunk.
- Theo dõi class loader và class unloading khi used tăng liên tục qua các chu kỳ.
- `MaxMetaspaceSize` là giới hạn; `MetaspaceSize` là ngưỡng GC ban đầu, không phải hard cap.
- Đọc metric cùng phạm vi, cùng thời điểm và kết hợp JMX, NMT cùng số liệu hệ điều hành.

Khi đọc Metaspace, hãy bắt đầu bằng câu hỏi số liệu đang mô tả không gian địa chỉ, dung lượng JVM đã commit hay metadata đang sống. Chỉ sau khi phân biệt ba lớp đó mới đánh giá được tăng trưởng bình thường, phần chunk được giữ để tái sử dụng hay dấu hiệu class loader retention cần điều tra.

## Tài liệu tham khảo

- [JEP 122: Remove the Permanent Generation](https://openjdk.org/jeps/122)
- [MemoryUsage – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.management/java/lang/management/MemoryUsage.html)
- [MemoryPoolMXBean – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Native Memory Tracking – Java SE 16 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/16/troubleshoot/diagnostic-tools.html)
- [jcmd – Java SE 16 Tools Reference](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jcmd.html)
- [Native Memory Tracking – Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
