# MemoryPoolMXBean và các vùng bộ nhớ

## 1. Vì sao cần quan sát từng vùng?

Giả sử ứng dụng dùng thêm bộ nhớ dù heap tổng thể chưa đầy. Chỉ đọc một con số heap không cho biết vùng chứa đối tượng, vùng thông tin lớp hay vùng mã máy đang tăng. Cần chia góc nhìn thành các **vùng bộ nhớ được JVM công bố để quản lý**, gọi là memory pool.

`MemoryPoolMXBean` là giao diện giám sát một pool. `MemoryMXBean` cung cấp góc nhìn tổng thể về heap và non-heap; các pool giúp đi sâu hơn vào thành phần đang sử dụng tài nguyên. Pool là một đơn vị quản lý của JVM, không phải một nhóm đối tượng nghiệp vụ do ứng dụng tự đặt tên. [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).

Từ dữ liệu pool, ta có thể đặt những câu hỏi cụ thể: vùng nào tăng, phần đã dùng có giảm sau thu gom không, mức đỉnh là bao nhiêu, có biết giới hạn không và JVM có hỗ trợ cảnh báo cho vùng đó không. Các câu trả lời là bằng chứng giám sát, chưa tự tạo thành kết luận rò rỉ bộ nhớ.

## 2. Heap, non-heap và các tên phụ thuộc triển khai

Mỗi pool được phân loại bằng `getType()`:

| Loại | Ý nghĩa |
| --- | --- |
| `MemoryType.HEAP` | Bộ nhớ heap dùng cho các đối tượng và mảng |
| `MemoryType.NON_HEAP` | Bộ nhớ JVM quản lý cho thông tin lớp, xử lý nội bộ hoặc tối ưu hóa, chẳng hạn mã do JIT tạo |

Không suy ra loại pool chỉ bằng tìm từ “Heap” trong tên. Dùng enum của API để phân loại; dùng tên để hiển thị hoặc đối chiếu với tài liệu của JVM đang chạy. [MemoryType](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryType.html).

Trên một số cấu hình HotSpot, bạn có thể thấy:

| Tên thường gặp | Cách đọc trong đúng cấu hình đó |
| --- | --- |
| `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen` | Các góc nhìn quản lý bộ nhớ heap khi dùng G1 |
| `Metaspace`, `Compressed Class Space` | Các vùng liên quan tới thông tin lớp |
| `CodeHeap ...` | Các phần của vùng mã máy và hạ tầng liên quan |

Đây là **ví dụ triển khai**, không phải danh sách bắt buộc của Java SE. JVM khác, bộ thu gom khác hoặc cấu hình khác có thể công bố tên và số lượng khác. HotSpot có thể chia code cache thành nhiều phần để quản lý các loại mã. [HotSpot Performance Enhancements](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).

Đặc biệt, một memory pool JMX không nhất thiết tương ứng một khối bộ nhớ vật lý liên tục. G1 chia heap thành nhiều region; tập region đóng vai trò Eden, Survivor hoặc Old có thể thay đổi. Không hiểu mỗi dòng pool là một region duy nhất và cũng không suy ra ranh giới địa chỉ từ tên pool. [G1: Heap Layout](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).

## 3. Lấy pool và nhận diện đúng đối tượng

Lấy danh sách trong JVM hiện tại:

```java
List<MemoryPoolMXBean> pools =
        ManagementFactory.getMemoryPoolMXBeans();
```

Đây là đoạn minh họa cần import `java.util.List` và các kiểu `java.lang.management` tương ứng. Không tự tạo đối tượng triển khai pool. Mỗi bean đại diện một pool và có `getName()`, `getType()`, `getObjectName()`. ObjectName có dạng:

```text
java.lang:type=MemoryPool,name=<tên pool>
```

Nếu cần truy cập qua JMX, dùng `getObjectName()` thay vì tự ghép chuỗi và tự xử lý ký tự đặc biệt. Khi công cụ kết nối tới JVM khác, lấy các bean qua `MBeanServerConnection` của JVM đích; factory không nhận kết nối là đường truy cập cục bộ. [ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

JVM có thể tạo hoặc loại bỏ pool trong quá trình chạy. Một bean không còn hợp lệ có `isValid() == false`; `getUsage()` có thể trả `null`. Kiểm tra hợp lệ một lần không ngăn trạng thái thay đổi sau đó, nên mã đọc vẫn cần xử lý kết quả không có dữ liệu. [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

## 4. Đọc một MemoryUsage đúng cách

Một ảnh chụp `MemoryUsage` gồm bốn số theo **byte**:

| Trường | Ý nghĩa |
| --- | --- |
| `init` | Dung lượng yêu cầu ban đầu; `-1` nếu không xác định |
| `used` | Dung lượng đang dùng |
| `committed` | Dung lượng được bảo đảm sẵn cho JVM sử dụng |
| `max` | Giới hạn có thể sử dụng nếu xác định được; `-1` nếu không xác định |

Trong một ảnh chụp hợp lệ, `used <= committed`; nếu `max` xác định thì `committed <= max`. `committed` không đồng nghĩa mọi byte đều chứa đối tượng còn sống. `max == -1` chỉ nói API không xác định giới hạn đó, không chứng minh tài nguyên vật lý vô hạn. [MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

Ví dụ tính tỷ lệ dung lượng đã dùng:

```java
MemoryUsage usage = pool.getUsage();
if (usage != null && usage.getMax() > 0) {
    double percent = 100.0 * usage.getUsed() / usage.getMax();
}
```

Đây là đoạn minh họa trong phạm vi đã có `pool`. Dùng `100.0` để tính số thực. Khi không có `max` hợp lệ, hiển thị “không có tỷ lệ” thay vì 0%. Tỷ lệ `used / committed` cũng có thể hữu ích nhưng trả lời câu hỏi khác, không được gắn nhãn là phần trăm giới hạn tối đa.

Giữ lại một đối tượng `MemoryUsage` rồi đọc các trường của nó. Gọi `getUsage()` nhiều lần để lấy từng trường có thể trộn các thời điểm khác nhau. Tương tự, việc lần lượt đọc nhiều pool không tạo một ảnh chụp nguyên tử của toàn JVM.

## 5. Hiện tại, mức đỉnh và sau thu gom là ba góc nhìn

| Phương thức | Câu hỏi |
| --- | --- |
| `getUsage()` | Hiện tại pool được ước tính dùng bao nhiêu? |
| `getPeakUsage()` | Mức đỉnh được ghi nhận từ khi JVM khởi động hoặc từ lần đặt lại gần nhất là gì? |
| `getCollectionUsage()` | Sau lần gần nhất JVM cố gắng thu hồi đối tượng không dùng trong pool, tình hình là gì? |

`getPeakUsage()` có thể trả `null` nếu pool không còn hợp lệ. `getCollectionUsage()` có thể trả `null` nếu JVM không hỗ trợ phép đo. Đọc dữ liệu sau thu gom **không yêu cầu JVM chạy GC mới**; đó là dữ liệu của lần xử lý đã xảy ra. Không mặc định đây là ảnh chụp ngay sau một lần thu gom toàn bộ heap. [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

Ví dụ suy luận: pool tăng mạnh trong lúc xử lý lô dữ liệu rồi giảm sau khi công việc kết thúc có ý nghĩa khác với mức còn lại sau thu gom tăng qua nhiều đợt tải tương đương. Hãy so sánh cùng pool, cùng loại số liệu và bối cảnh tải; đừng lấy đỉnh của một ngày so với giá trị hiện tại của một ngày khác rồi gọi đó là tốc độ rò rỉ.

`resetPeakUsage()` đặt lại thống kê đỉnh theo mức sử dụng hiện tại. Nó không giải phóng pool, không làm `used` về 0 và không phải thao tác GC. Chỉ gọi khi chủ động thiết lập một cửa sổ đo mới; không đặt lại trong mỗi lần lấy mẫu vì sẽ phá ý nghĩa thống kê đỉnh.

## 6. Quan hệ giữa pool và bộ quản lý bộ nhớ

Một pool có ít nhất một memory manager quản lý; một manager có thể quản lý nhiều pool. Lấy quan hệ bằng:

```java
String[] managerNames = pool.getMemoryManagerNames();
```

Có thể đi chiều ngược lại với `MemoryManagerMXBean.getMemoryPoolNames()`. Bộ thu gom rác là một loại memory manager, nhưng không phải mọi manager đều là bộ thu gom heap. Quan hệ có thể nhiều-nhiều; không ép mỗi pool vào đúng một collector. [MemoryManagerMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryManagerMXBean.html), [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html).

Khi thấy `CodeCacheManager` quản lý code heap hoặc `Metaspace Manager` quản lý vùng thông tin lớp, hãy hiểu đó là dữ liệu của triển khai đang chạy. Không dùng các tên này như enum cố định trong logic chung cho mọi JVM.

## 7. Chương trình Java: kiểm kê pool chỉ bằng thao tác đọc

Ví dụ Java 17+ sau đọc từng pool, xử lý thiếu dữ liệu, tính tỷ lệ khi có giới hạn và in khả năng hỗ trợ ngưỡng. Nó không gọi GC, không thay ngưỡng và không đặt lại đỉnh.

Lưu thành `MemoryPoolInventory.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class MemoryPoolInventory {
    static String bytes(long value) {
        return value < 0 ? "undefined" : Long.toString(value);
    }

    static String percent(MemoryUsage usage) {
        if (usage.getMax() <= 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT, "%.1f%%",
                100.0 * usage.getUsed() / usage.getMax());
    }

    public static void main(String[] args) {
        List<MemoryPoolMXBean> pools =
                new ArrayList<>(ManagementFactory.getMemoryPoolMXBeans());
        pools.sort(Comparator.comparing(MemoryPoolMXBean::getName));

        for (MemoryPoolMXBean pool : pools) {
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                System.out.println(pool.getName() + ": unavailable");
                continue;
            }

            System.out.printf(Locale.ROOT,
                    "%s | %s | used=%s | committed=%s | max=%s | ratio=%s%n",
                    pool.getName(), pool.getType().name(),
                    bytes(usage.getUsed()), bytes(usage.getCommitted()),
                    bytes(usage.getMax()), percent(usage));

            System.out.printf(
                    "  usageThreshold=%s, collectionThreshold=%s, managers=%s%n",
                    pool.isUsageThresholdSupported(),
                    pool.isCollectionUsageThresholdSupported(),
                    String.join(", ", pool.getMemoryManagerNames()));
        }
    }
}
```

Chạy:

```shell
javac MemoryPoolInventory.java
java MemoryPoolInventory
```

Stdout dưới đây là **một lần chạy thực tế trên JDK 24 dùng G1**. Các số, tên pool, danh sách manager và khả năng hỗ trợ có thể khác ở lần chạy hoặc môi trường khác:

```text
CodeHeap 'non-nmethods' | NON_HEAP | used=1801856 | committed=2555904 | max=7602176 | ratio=23.7%
  usageThreshold=true, collectionThreshold=false, managers=CodeCacheManager
CodeHeap 'non-profiled nmethods' | NON_HEAP | used=62592 | committed=2555904 | max=122093568 | ratio=0.1%
  usageThreshold=true, collectionThreshold=false, managers=CodeCacheManager
CodeHeap 'profiled nmethods' | NON_HEAP | used=186112 | committed=2555904 | max=121962496 | ratio=0.2%
  usageThreshold=true, collectionThreshold=false, managers=CodeCacheManager
Compressed Class Space | NON_HEAP | used=61264 | committed=131072 | max=1073741824 | ratio=0.0%
  usageThreshold=true, collectionThreshold=false, managers=Metaspace Manager
G1 Eden Space | HEAP | used=0 | committed=100663296 | max=undefined | ratio=n/a
  usageThreshold=false, collectionThreshold=true, managers=G1 Old Generation, G1 Young Generation
G1 Old Gen | HEAP | used=0 | committed=2046820352 | max=31675383808 | ratio=0.0%
  usageThreshold=true, collectionThreshold=true, managers=G1 Old Generation, G1 Concurrent GC, G1 Young Generation
G1 Survivor Space | HEAP | used=0 | committed=0 | max=undefined | ratio=n/a
  usageThreshold=false, collectionThreshold=true, managers=G1 Old Generation, G1 Young Generation
Metaspace | NON_HEAP | used=714888 | committed=851968 | max=undefined | ratio=n/a
  usageThreshold=true, collectionThreshold=false, managers=Metaspace Manager
```

Đọc kết quả này theo các điểm sau:

- `max=undefined` và `ratio=n/a` thể hiện dữ liệu không xác định; chương trình không chia cho `-1`.
- `NON_HEAP` cho biết đây không phải vùng heap chứa đối tượng ứng dụng thông thường.
- `usageThreshold=false` không có nghĩa không đọc được dung lượng; nó chỉ báo không hỗ trợ loại ngưỡng đó.
- Một pool có thể được nhiều manager quản lý.
- Giá trị `used=0` ở một ảnh chụp không chứng minh ứng dụng không tạo đối tượng; cách thống kê và thời điểm công bố dữ liệu phụ thuộc JVM.

Chương trình sắp xếp bản sao danh sách để đầu ra dễ đọc, không phụ thuộc thứ tự factory trả về. Muốn quan sát xu hướng, chạy tác vụ lấy mẫu trong **cùng tiến trình đang cần đo** hoặc dùng kết nối quản lý tới tiến trình đó; khởi động chương trình này nhiều lần chỉ đo nhiều JVM mới.

## 8. Ngưỡng sử dụng và ngưỡng sau thu gom

Hai nhóm ngưỡng là những khả năng độc lập:

| Nhóm | Kiểm tra hỗ trợ | Cấu hình |
| --- | --- | --- |
| Usage threshold | `isUsageThresholdSupported()` | `setUsageThreshold(bytes)` |
| Collection usage threshold | `isCollectionUsageThresholdSupported()` | `setCollectionUsageThreshold(bytes)` |

Kiểm tra trước khi gọi getter, setter hoặc phép kiểm tra vượt ngưỡng của nhóm tương ứng. Ngưỡng phải không âm và không vượt `max` nếu giới hạn đó được xác định. Đặt 0 tắt kiểm tra vượt ngưỡng; ngưỡng dương bật khả năng kiểm tra của nhóm. Ngưỡng không thay đổi dung lượng pool và không tăng giới hạn heap. [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

Usage threshold quan sát việc mức dùng đạt hoặc vượt ngưỡng do JVM phát hiện. Collection usage threshold quan sát mức dùng sau nỗ lực thu hồi của JVM. Cảnh báo sau thu gom có thể giúp nhận biết phần sử dụng còn cao, nhưng vẫn cần đối chiếu với tải và loại collector.

Ví dụ chính sách minh họa: pool có `max` xác định, hỗ trợ ngưỡng và đã được chọn đúng cho mục tiêu vận hành thì có thể đặt ngưỡng ở một tỷ lệ của giới hạn đó. Không áp dụng “80% cho mọi pool”: một vùng được thiết kế để đầy rồi thu gom thường xuyên có hành vi khác vùng lưu thông tin lớp hay vùng đối tượng tồn tại lâu.

Các phương thức `getUsageThresholdCount()` và `getCollectionUsageThresholdCount()` là bộ đếm do JVM công bố cho các sự kiện phát hiện tương ứng. Chúng không phải số lần mã lấy mẫu gọi getter, không phải số byte vượt ngưỡng và không phải bằng chứng đã xảy ra `OutOfMemoryError`.

## 9. Nhận thông báo từ đúng nguồn

Thông báo bộ nhớ được phát bởi **MemoryMXBean**, dù điều kiện thuộc về một pool cụ thể. Dữ liệu thông báo gồm tên pool, ảnh chụp dung lượng và số đếm. Hai loại chính là:

- `MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED`
- `MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED`

`userData` là `CompositeData`; dùng `MemoryNotificationInfo.from()` để chuyển đổi. Với usage threshold, giữ mức sử dụng ở trên ngưỡng không đồng nghĩa được phát thông báo liên tục: muốn có đợt vượt tiếp theo, mức dùng cần xuống dưới ngưỡng rồi đạt/vượt lại. Không áp dụng máy móc quy tắc này cho bộ đếm sau thu gom. [MemoryNotificationInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html).

Bộ xử lý thông báo nên làm việc nhẹ: ghi nhận pool, thời điểm, mức dùng và chuyển công việc nặng sang luồng xử lý phù hợp. Tránh cấp phát thêm lượng dữ liệu lớn ngay trong đường cảnh báo thiếu bộ nhớ.

Cảnh báo là tín hiệu chủ động để điều chỉnh tải hoặc điều tra, không phải cơ chế bảo đảm ngăn mọi lỗi hết bộ nhớ. JVM quyết định thời điểm phát hiện theo khả năng của pool; không dùng ngưỡng như một hạn mức thời gian thực cho mọi lần cấp phát.

## 10. Pool không đại diện toàn bộ bộ nhớ tiến trình

Không cộng tất cả `max` của các pool rồi gọi kết quả là giới hạn tiến trình. Có giá trị không xác định, giới hạn riêng theo thành phần, cách chia vùng có thể động và các phép đo không diễn ra đồng thời. Tương tự, tổng `used` từ các pool không phải phép đo RSS của hệ điều hành.

Direct buffer và mapped buffer có giao diện riêng là `BufferPoolMXBean`, thường dưới miền `java.nio`. Danh sách `MemoryPoolMXBean` không tự thay thế giao diện đó. Nếu nghi phần bộ nhớ ngoài heap, cần kiểm tra đúng nguồn dữ liệu. [BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html).

Với HotSpot, Native Memory Tracking là một công cụ bổ sung cho một số nhóm cấp phát nội bộ, có yêu cầu bật và chi phí riêng. Nó cũng không bao phủ mọi cấp phát của mã native bên thứ ba. Muốn giải thích toàn bộ bộ nhớ tiến trình cần kết hợp số liệu JVM với công cụ hệ điều hành phù hợp. [Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html).

## 11. Những lỗi nên tự phát hiện

| Nhận định hoặc cách làm | Điều cần sửa |
| --- | --- |
| Mọi JVM đều có đúng các pool của G1 | Khám phá danh sách thực tế và đọc `getType()` |
| `max=-1` nghĩa pool không dùng bộ nhớ | Giữ ý nghĩa “không xác định giới hạn” |
| `getCollectionUsage()` bắt JVM chạy GC | Đây là lần đọc dữ liệu đã có, có thể trả `null` |
| Reset peak giúp hạ áp lực bộ nhớ | Nó chỉ thay thống kê mức đỉnh |
| Mọi pool đều hỗ trợ ngưỡng | Kiểm tra riêng từng khả năng |
| Vượt ngưỡng đồng nghĩa rò rỉ | Đối chiếu xu hướng, tải và dữ liệu sau thu gom |
| Tổng pool bằng toàn bộ bộ nhớ tiến trình | Phân biệt phạm vi MXBean, buffer, native và hệ điều hành |

Bài tập: chạy chương trình kiểm kê trong hai cấu hình JVM hợp lệ của bạn, lưu tên pool, loại, giới hạn và khả năng ngưỡng. Giải thích điểm khác biệt dựa trên cấu hình thực tế, không sửa mã bằng cách ghi cứng một danh sách tên mới.

Khi đọc pool, luôn gắn **danh tính vùng, loại bộ nhớ, thời điểm, trạng thái dữ liệu và phạm vi phép đo** với con số. Đó là cơ sở để phân tích bộ nhớ bằng bằng chứng thay vì suy luận từ một tỷ lệ riêng lẻ.
