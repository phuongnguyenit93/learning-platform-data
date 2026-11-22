# 6.10 HotSpotDiagnosticMXBean cho heap dump và VM option có thể quản lý

## Mục tiêu học tập

Khi cần điều tra rò rỉ bộ nhớ, phân tích đối tượng đang được giữ lại hoặc xác nhận một JVM flag có thể thay đổi khi ứng dụng đang chạy, Java cung cấp một giao diện quản trị HotSpot chuyên biệt: `com.sun.management.HotSpotDiagnosticMXBean`.

Điểm quan trọng nhất: **cùng là MXBean nhưng không phải mọi method đều chỉ quan sát**. `getDiagnosticOptions()` và `getVMOption(...)` giúp đọc trạng thái; `dumpHeap(...)` tạo một file heap dump có thể lớn và ảnh hưởng tiến trình; `setVMOption(...)` chủ động thay đổi một flag có thể điều chỉnh trong runtime. Một thao tác chẩn đoán thiếu kiểm soát có thể làm thay đổi chính hiện tượng đang được đo.

Học xong bài này, bạn sẽ có thể:

- Hiểu vai trò, module, phạm vi HotSpot và tên JMX ObjectName của `HotSpotDiagnosticMXBean`.
- Lấy MXBean từ `ManagementFactory`, tra `VMOption` và đọc `name`, `value`, `origin`, `isWriteable`.
- Phân biệt **VM option có thể đổi động** với các cờ chỉ được xác định khi khởi động; biết khi nào `setVMOption` có thể bị từ chối.
- Giải thích `dumpHeap(String outputFile, boolean live)`: `live=true/false`, định dạng `.hprof`, đường dẫn trên **máy chạy target JVM**, điều kiện lỗi và chi phí.
- Thiết kế quy trình kiểm soát rủi ro khi chụp heap hoặc thay đổi flag: đúng tiến trình, dung lượng đĩa, dữ liệu nhạy cảm, baseline, thời điểm, phân quyền, xác minh và khôi phục.
- Biên dịch/chạy ví dụ Java 17+ gồm chế độ **fixture xác định**, chế độ chỉ đọc MXBean thật và chế độ dump **chỉ khi chủ động xác nhận trong lab**.
- Ghi kết luận chẩn đoán với phạm vi chứng cứ; không tự biến heap dump thành bằng chứng chắc chắn của memory leak hay coi mọi flag JVM đều thay đổi động.

## 1. HotSpotDiagnosticMXBean nằm ở đâu trong hệ sinh thái MXBeans?

Các MXBean chuẩn trong `java.lang.management` như `MemoryMXBean` hoặc `ThreadMXBean` cung cấp thông tin quản lý chung. `HotSpotDiagnosticMXBean` nằm trong:

```text
Module:      jdk.management
Package:     com.sun.management
Interface:   HotSpotDiagnosticMXBean
JMX name:    com.sun.management:type=HotSpotDiagnostic
```

Đây là giao diện chẩn đoán của **HotSpot VM**, không phải lời hứa rằng mọi triển khai Java VM đều cung cấp đúng interface hay từng option giống nhau. `com.sun.management` là gói mở rộng được JDK cung cấp cho HotSpot; khác với lời gọi Java SE thuần túy mà VM nào cũng phải hỗ trợ.

**Ba lớp cần phân biệt:**

| Lớp | Thành phần | Có thể làm gì? |
| --- | --- | --- |
| API trong ứng dụng | `HotSpotDiagnosticMXBean`, `VMOption` | Đọc flag, ghi heap dump và điều chỉnh flag được phép |
| JMX management | Platform MBeanServer, ObjectName `com.sun.management:type=HotSpotDiagnostic` | Client quản trị truy cập operation khi có kết nối/quyền |
| Bên trong HotSpot | VM flags, memory manager, heap dump implementation | Thực hiện thay đổi hoặc thao tác nặng thực tế |

Để có interface trong Java 17, thường dùng:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;

HotSpotDiagnosticMXBean bean =
        ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
```

Đây là đoạn mã tích hợp, không phải một chương trình độc lập; cách dùng đầy đủ có ở phần lab. Nếu môi trường không hỗ trợ HotSpot MXBean này, không cố suy từ một `null` hoặc lỗi startup rằng heap vẫn hoạt động sai. Cần ghi JVM vendor, phiên bản/patch và API thực sự khả dụng.

**JMX từ xa:** cùng một bean có thể xuất hiện trong platform MBeanServer. Người quản trị dùng JMX có thể đọc thuộc tính, gọi `dumpHeap` hoặc `setVMOption` nếu được phép. **Đọc từ xa không có nghĩa dump sẽ được tải về client**: dump được tạo trên filesystem mà **target JVM** nhìn thấy. Kết nối và việc phân quyền operation là hai vấn đề riêng cần kiểm soát.

## 2. Phân loại bốn method chính theo tác dụng thực tế

Java 17 cung cấp bốn method chính:

| Method | Dạng thao tác | Kết quả/tác dụng | Lưu ý |
| --- | --- | --- | --- |
| `getDiagnosticOptions()` | Quan sát | Danh sách `VMOption` dùng cho chẩn đoán có thể điều chỉnh động | Không phải danh sách **mọi** JVM flag |
| `getVMOption(name)` | Quan sát | Một `VMOption` theo tên nếu tồn tại | Có thể trả flag **không** writable; sai tên → exception |
| `setVMOption(name,value)` | **Can thiệp** | Yêu cầu đổi giá trị option được JVM cho phép thay ở runtime | Kiểm tra `isWriteable`, valid value, quyền, side effect |
| `dumpHeap(outputFile,live)` | **Can thiệp/thu artifact nặng** | Tạo file HPROF của heap | Pause/GC/I/O, disk, dữ liệu nhạy cảm, đường dẫn đích |

Những method đọc vẫn có chi phí gọi management interface; tuy nhiên rủi ro chính nằm ở việc **dump dữ liệu heap lớn** và **đổi cờ có hiệu lực với tiến trình sống**.

Đừng gọi `setVMOption` chỉ để “thử xem flag tồn tại không”; `getVMOption` dùng cho kiểm tra đọc. Đừng gọi `dumpHeap` khi chỉ cần biết heap used/max; hãy bắt đầu bằng `MemoryMXBean`, GC logs, metrics hoặc công cụ đã bật sẵn.

## 3. VMOption: name, value, writeable và origin

`com.sun.management.VMOption` mô tả một giá trị VM option tại thời điểm lấy snapshot.

```java
VMOption opt = bean.getVMOption("SomeOptionName");

String name = opt.getName();
String value = opt.getValue();
boolean canChangeNow = opt.isWriteable();
VMOption.Origin origin = opt.getOrigin();
```

Đây là **mã minh họa tích hợp**. `SomeOptionName` là một tên tượng trưng để giải thích chữ ký API; đừng chạy nguyên chuỗi này trên production. Nên dùng tên đã được xác minh trên JVM mục tiêu.

### 3.1 Ý nghĩa từng trường

- `getName()`: tên option mà HotSpot nhận diện.
- `getValue()`: **chuỗi giá trị tại thời điểm tạo đối tượng `VMOption`**, không phải một binding tự cập nhật khi flag thay đổi.
- `isWriteable()`: JVM thông báo option **có thể được thiết lập động qua management interface**. Tên API dùng chính xác cách viết **`Writeable`**, không phải `Writable`.
- `getOrigin()`: nguồn gốc giá trị tại thời điểm snapshot, giúp phân biệt cờ mặc định với cờ đến từ command line, cấu hình hoặc thay đổi management.

Một `VMOption` trả về trước thay đổi không tự đổi `value` sau `setVMOption`; phải **gọi lại `getVMOption`** để lấy snapshot mới.

### 3.2 Các giá trị `VMOption.Origin` trong Java 17

| Origin | Ý nghĩa |
| --- | --- |
| `DEFAULT` | Option chưa được set, đang dùng default |
| `VM_CREATION` | Được set lúc tạo VM (thường là launcher args/JNI invocation) |
| `ENVIRON_VAR` | Được set qua environment variable |
| `CONFIG_FILE` | Được set bằng configuration file |
| `ERGONOMIC` | VM chọn qua cơ chế tự điều chỉnh/ergonomics |
| `MANAGEMENT` | Được thay đổi qua management interface sau khi VM chạy |
| `ATTACH_ON_DEMAND` | Được set qua attach framework |
| `OTHER` | Đến từ cơ chế khác |

Origin **không phải cơ chế kiểm chứng flag đó đúng về mặt vận hành**. Ví dụ `VM_CREATION` chỉ biết flag được set tại startup, không nói nó tối ưu. `MANAGEMENT` cho biết giá trị đến từ management interface, không đồng nghĩa thay đổi đã cải thiện triệu chứng.

### 3.3 `getDiagnosticOptions` không phải toàn bộ danh sách `-XX`

Theo Javadoc Java 17, “diagnostic option” ở API này là một **writeable VM option có thể được set động**, phục vụ chẩn đoán. Danh sách:

```java
List<VMOption> manageable = bean.getDiagnosticOptions();
```

chỉ thuộc nhóm API định nghĩa; không thay thế output toàn bộ effective VM flags của `jcmd VM.flags -all`, cũng không chứng minh một flag không xuất hiện trong list là không tồn tại.

`getVMOption(name)` cho phép tra một flag theo tên và đọc `isWriteable()`, kể cả khi flag đó không nằm trong danh sách diagnostic writeable. Nếu tên không tồn tại, `IllegalArgumentException` là tín hiệu “option không có trên VM đang chạy”, không có nghĩa cả Java application lỗi.

Khi làm công cụ tự động, **không hardcode danh sách flag writable của một phiên bản JDK** rồi áp lên tất cả. Các flag `-XX` có thể thay đổi hoặc bị bỏ qua qua JDK version, vendor, OS, collector hay lựa chọn runtime khác.

## 4. Heap dump qua `dumpHeap(String outputFile, boolean live)`

Phương thức:

```java
void dumpHeap(String outputFile, boolean live)
        throws IOException;
```

Tạo file ở định dạng tương thích **HPROF heap dump**, chứa thông tin về các object/quan hệ tham chiếu trong Java heap. File này phục vụ phân tích object count, retained size, dominator tree và retaining path bằng các công cụ phù hợp.

### 4.1 `live=true` và `live=false`

| Giá trị | Tập object yêu cầu ghi | Phân tích thích hợp |
| --- | --- | --- |
| `live=true` | Các object đang **reachable** từ những root/đối tượng khác theo ngữ nghĩa của API | Phân tích object được giữ lại, memory retention |
| `live=false` | Bao gồm **cả object không còn reachable** vào thời điểm thu theo khả năng của VM | Điều tra allocation/heap content rộng hơn, hiểu rõ rằng có thể có object rác chưa được thu |

Một object được gọi là “live” ở đây theo định nghĩa **reachable**, **không** đồng nghĩa “vừa được sử dụng bởi request trong một phút” hoặc “không bao giờ là leak”. Một leak trong Java thường là **object vẫn reachable không còn cần thiết về nghiệp vụ**.

**Chi tiết rất quan trọng:** để xác định tập object reachable và chụp snapshot nhất quán, việc tạo dump có thể làm JVM phải đồng bộ/pause và/hoặc thực hiện xử lý GC tùy collector/implementation. Với `live=true` trong HotSpot, người vận hành nên chuẩn bị cho khả năng có GC và ảnh hưởng latency. Không gọi một heap dump là “read-only không tác dụng phụ” chỉ vì method không sửa object trong code ứng dụng.

`live=false` **không** bảo đảm “không pause”, “không đồng bộ” hoặc “dump nhanh”; nó chỉ thay đổi yêu cầu về tập object được đưa vào artifact. Khi so sánh hai dump, phải ghi **cả giá trị `live` và thời điểm** vì tính chất dữ liệu có thể khác.

### 4.2 File được ghi ở đâu?

Javadoc Java 17 quy định:

- Nếu gọi **trực tiếp trong cùng process**, `outputFile` được hiểu theo filesystem mà process JVM đó nhìn thấy.
- Nếu gọi **từ JMX client ở process/máy khác**, dump vẫn được ghi **trên máy target JVM**, không phải trên máy chạy client.
- Nếu dùng **relative path**, nó được tính từ **working directory của target VM lúc khởi động**.
- File dump phải có **suffix `.hprof`** và tên hợp lệ theo OS/VM.

Do đó trong container/Kubernetes, `/tmp/app-heap.hprof` có thể nằm trong filesystem của **container Java**, không phải `/tmp` của máy operator. Nếu target container bị restart, ephemeral artifact có thể mất; cần kế hoạch lấy file ra và giữ bảo mật. Một đường dẫn tồn tại trên máy giám sát **không** chứng minh đường dẫn đó ghi được trong container target.

**Quy tắc thực hành:** ưu tiên đường dẫn tuyệt đối, đã xác minh quyền/dung lượng ở **đúng filesystem target**, tên file độc nhất cho run/PID/timestamp và truy xuất theo quy trình bảo mật. Không đoán đường dẫn đích từ máy client.

### 4.3 Lỗi cần nhận diện

Theo Javadoc Java 17:

| Điều kiện | Exception có thể gặp | Điều cần kiểm tra |
| --- | --- | --- |
| File đích đã tồn tại hoặc không thể tạo/mở/ghi | `IOException` | Tên duy nhất, thư mục, quyền, disk/quota, mount, inode |
| File không kết thúc bằng `.hprof` | `IllegalArgumentException` | Đặt hậu tố chính xác |
| `outputFile == null` | `NullPointerException` | Không truyền `null` |
| Operation không được hỗ trợ | `UnsupportedOperationException` | JVM/vendor/implementation và môi trường |
| Quyền quản lý/ghi file bị từ chối trong cấu hình bảo vệ phù hợp | `SecurityException` | Quyền caller, chính sách quản trị, quyền filesystem |

Nếu không có đủ disk, nên **không gọi dump** thay vì thử rồi gây tràn ổ khi service đã suy giảm. Việc kiểm tra dung lượng trước chỉ là đánh giá rủi ro, không bảo đảm file cuối cùng sẽ vừa vì heap và dung lượng trống có thể biến động.

Một dump có thể có kích thước gần hoặc vượt phần heap đang dùng tùy định dạng/nội dung object/metadata và phương pháp ghi. Không dùng công thức cứng kiểu “file = Xmx” như một cam kết dung lượng. Ngoài ra, disk pressure và I/O amplification có thể ảnh hưởng chính dịch vụ đang chạy.

### 4.4 HPROF có thể chứa dữ liệu nhạy cảm

Heap dump không giống log đã được lọc trường. Nó có thể chứa:

- Dữ liệu từ request/response, customer/session identifiers, email, địa chỉ, dữ liệu nghiệp vụ.
- Token, secrets, password/string còn nằm trong heap, tùy việc ứng dụng lưu giữ.
- Buffer, cache, chuỗi kết nối/URI và dữ liệu nội bộ có tính bảo mật.
- Object graph/quan hệ tham chiếu có thể bộc lộ kiến trúc bên trong.

Áp dụng phân quyền, encryption at rest/in transit nếu chuyển file, lifecycle/retention rõ, nơi lưu không public, hạn chế sao chép và dọn file sau thời hạn. Không đưa HPROF hoặc stack/metadata chứa dữ liệu thực vào chat công khai hay repository.

## 5. Phân biệt `dumpHeap` với `jcmd GC.heap_dump`

Cả hai thường phục vụ mục đích lấy heap dump từ HotSpot, nhưng chúng là **hai giao diện** khác nhau.

| Góc nhìn | `HotSpotDiagnosticMXBean.dumpHeap` | `jcmd <PID> GC.heap_dump` |
| --- | --- | --- |
| Nơi gọi | Trong Java code hoặc qua JMX | CLI/attach diagnostic command |
| Tham số đối tượng | `live=true/false` | Có option như `-all` theo JDK 17 |
| Đích xuất | `outputFile` trên filesystem target JVM | File path được target JVM xử lý |
| Hành vi | Snapshot có thể tác động GC/pause/I/O | Tài liệu JDK 17 nêu mặc định yêu cầu full GC nếu không có `-all` |
| Quyền | Management permissions/JMX/OS tương ứng | Quyền attach vào target process |
| Rủi ro | File HPROF lớn, privacy, đổi trạng thái quan sát | Rủi ro tương tự; phải đọc help/version cụ thể |

Không nhầm rằng `live=false` hay `-all` là tùy chọn “miễn phí GC và pause”. Các cơ chế GC, đồng bộ và chi phí snapshot phụ thuộc bản VM, collector, heap size, workload. Phải dùng thông tin đúng JDK/và hoàn cảnh thật.

Với nhu cầu **chỉ xem heap usage**, `MemoryMXBean.getHeapMemoryUsage()`, GC metrics/JFR hiện có thường ít xâm lấn hơn một heap dump. Chỉ thực hiện dump khi câu hỏi cần object graph/retaining paths mà metric tổng quan không trả lời được.

## 6. `setVMOption`: đổi giá trị động chứ không phải đọc

Phương thức:

```java
void setVMOption(String name, String value);
```

Yêu cầu JVM thay đổi một option có thể chỉnh tại runtime. Giá trị được truyền vào là **String**, kể cả khi option biểu diễn boolean, số nguyên, kích thước hay loại dữ liệu khác. Chỉ các giá trị mà VM chấp nhận mới hợp lệ.

**Trình tự tối thiểu trước khi thay:**

1. Xác nhận đúng **process/JVM/vendor/version/build/PID**.
2. Đọc `getVMOption(name)` và lưu `value`, `origin`, `isWriteable`.
3. Nếu `isWriteable()==false`, **không** thử set để “kiểm tra xem sao”.
4. Xác định thay đổi này ảnh hưởng gì: logging, error handling, chẩn đoán, performance hoặc bảo mật.
5. Chọn mục tiêu, giới hạn tác động, window, owner và phương án khôi phục.
6. Chỉ sau khi được phép, gọi `setVMOption(name,newValue)` trong môi trường/phiên phù hợp.
7. Gọi `getVMOption(name)` **lần nữa**, đối chiếu effective value và origin; kiểm tra metric/trạng thái thực.
8. Nếu phải rollback, dùng chính sách cho flag đó, sau đó **đọc lại** và kiểm chứng tác dụng phụ (file/log/recording có thể không quay lại trạng thái cũ chỉ vì flag được đổi lại).

**Ví dụ mã tích hợp — không được gọi tự động trong bài lab:**

```java
// Preconditions: owner approved the specific flag/change;
// name and newValue already validated for this JVM.
VMOption before = bean.getVMOption(name);
if (!before.isWriteable()) {
    throw new IllegalStateException(
            "VM option cannot be changed dynamically: " + name);
}

String originalValue = before.getValue();
// Record timestamp, PID, originalValue and expected impact.
// bean.setVMOption(name, newValue);       // MUTATING: deliberately disabled.
// VMOption after = bean.getVMOption(name); // Re-read if a change was approved.
```

Đây là đoạn **minh họa tích hợp**, không độc lập và cố tình **không thực thi lệnh set**. Việc bỏ comment tại production đòi hỏi kiểm tra flag cụ thể và quyền vận hành. Lưu lại trạng thái ban đầu nhưng không mặc định rollback bằng `setVMOption(name,originalValue)` sẽ hoàn tác mọi tác động ngoài VM flag (ví dụ file đã ghi hoặc dữ liệu log đã bị thay đổi).

### 6.1 Flag “manageability” không đồng nghĩa mọi thứ đều chỉnh được

- Một số flag chỉ có hiệu lực khi khởi động JVM, như nhiều thiết lập heap/collector cơ bản; không thể biến `-Xmx` thành thay đổi động chỉ vì dùng API management.
- Các cờ `-XX` không có bảo đảm ổn định qua mọi major JDK/vendor.
- `getDiagnosticOptions()` là một nguồn liệt kê các option hỗ trợ điều chỉnh động cho mục tiêu chẩn đoán; không dùng nó để khẳng định **toàn bộ** flag không có trong list đều không tồn tại.
- `getVMOption` cho biết giá trị và writeability **tại thời điểm đọc**; điều kiện runtime có thể thay đổi sau đó.

Nếu set vào option **không tồn tại**, **không writeable** hoặc giá trị **không hợp lệ**, Javadoc cho biết `IllegalArgumentException`. Nếu `name` hoặc `value` null thì `NullPointerException`; một môi trường có security manager/quyền bảo vệ phù hợp có thể sinh `SecurityException`.

### 6.2 Vì sao phải phân biệt `value` và `origin`?

Giả sử một option ở T1 có `value=false`, `origin=DEFAULT`, `writeable=true`. Sau thao tác điều chỉnh hợp lệ tại T2, một **đối tượng `VMOption` mới** có thể cho thấy `value=true`, `origin=MANAGEMENT`.

**Không** kết luận object `before` tự cập nhật. Nó lưu snapshot trước đó theo Javadoc. Nếu cả app và monitoring tool đều lưu object cũ, dashboard có thể hiển thị thông tin stale; cần đặt timestamp cho mỗi mẫu.

Origin cũng giúp điều tra sai khác giữa manifest/JVM args và trạng thái đang chạy: flag có thể đã được đổi sau startup qua management hoặc attach. Tuy nhiên cần đối chiếu event/audit log mới biết **ai** đổi và lý do; `Origin` không là hệ thống audit đầy đủ.

## 7. Java 17+: chương trình lab có chế độ an toàn mặc định

Chương trình dưới đây thực hiện ba chức năng:

1. **`fixture`**: tạo hai `VMOption` mô phỏng bằng constructor chuẩn, phân biệt cờ writeable và non-writeable, in stdout cố định. Chế độ này **không đọc hay sửa flags của JVM đang chạy**.
2. **`inspect`**: đọc HotSpot MXBean **của chính JVM lab**, in tên ObjectName và số diagnostic options; không ghi dump, không thay flag. Có thể truyền một tên flag để quan sát giá trị thực; output phụ thuộc JDK và flags thực.
3. **`dump-lab`**: chỉ ghi heap dump **khi người học tự truyền đầy đủ đường dẫn và chuỗi xác nhận**, trên **JVM lab riêng**. Không có chế độ `setVMOption` tự động để tránh vô ý sửa runtime configuration.

Tạo file **`HotSpotDiagnosticLab.java`**:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

public class HotSpotDiagnosticLab {
    private static HotSpotDiagnosticMXBean bean() {
        HotSpotDiagnosticMXBean result =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);
        if (result == null) {
            throw new IllegalStateException(
                    "HotSpotDiagnosticMXBean unavailable");
        }
        return result;
    }

    private static String describe(VMOption option) {
        return option.getName()
                + " value=" + option.getValue()
                + " writeable=" + option.isWriteable()
                + " origin=" + option.getOrigin();
    }

    private static void fixture() {
        VMOption fixed = new VMOption(
                "ExampleFixed", "512m", false,
                VMOption.Origin.VM_CREATION);
        VMOption dynamic = new VMOption(
                "ExampleDynamic", "false", true,
                VMOption.Origin.DEFAULT);

        System.out.println(describe(fixed));
        System.out.println(describe(dynamic));
        System.out.println(
                "heapDump: file must end with .hprof");
        System.out.println(
                "live=true: reachable objects only");
        System.out.println(
                "setVMOption: mutates a writeable VM option");
    }

    private static void inspect(String name) {
        HotSpotDiagnosticMXBean mx = bean();
        System.out.println("objectName=" + mx.getObjectName());
        List<VMOption> options = mx.getDiagnosticOptions();
        System.out.println("diagnosticOptionCount=" + options.size());

        options.stream()
                .sorted(Comparator.comparing(VMOption::getName))
                .limit(5)
                .forEach(opt -> System.out.println(
                        "manageableName=" + opt.getName()));

        if (name != null) {
            try {
                VMOption opt = mx.getVMOption(name);
                System.out.println("requested=" + describe(opt));
            } catch (IllegalArgumentException exception) {
                System.out.println("optionNotFound=" + name);
            }
        }
    }

    private static void dumpLab(String filename, String confirmation)
            throws IOException {
        if (!"I_UNDERSTAND_THE_RISK".equals(confirmation)) {
            throw new IllegalArgumentException(
                    "explicit confirmation required");
        }

        Path target = Path.of(filename).toAbsolutePath().normalize();
        if (!target.toString().endsWith(".hprof")) {
            throw new IllegalArgumentException(
                    "target must end with .hprof");
        }
        if (Files.exists(target)) {
            throw new IllegalArgumentException(
                    "refuse to use an existing file");
        }
        if (!Files.isDirectory(target.getParent())) {
            throw new IllegalArgumentException(
                    "parent directory does not exist");
        }

        // Writes HPROF on THIS JVM's filesystem. May pause/cause GC.
        bean().dumpHeap(target.toString(), true);
        System.out.println("heapDumpWritten=" + target);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("fixture")) {
            fixture();
            return;
        }
        if ((args.length == 1 || args.length == 2)
                && args[0].equals("inspect")) {
            inspect(args.length == 2 ? args[1] : null);
            return;
        }
        if (args.length == 3 && args[0].equals("dump-lab")) {
            dumpLab(args[1], args[2]);
            return;
        }
        System.out.println(
                "Usage: java HotSpotDiagnosticLab "
                + "fixture|inspect [flag]|dump-lab <file.hprof> "
                + "I_UNDERSTAND_THE_RISK");
    }
}
```

### 7.1 Biên dịch/chạy chế độ xác định

Dùng **JDK 17 HotSpot** hoặc bản JDK 17 phù hợp có `jdk.management`:

```bash
javac HotSpotDiagnosticLab.java
java HotSpotDiagnosticLab fixture
```

**Stdout chính xác** của `fixture`:

```text
ExampleFixed value=512m writeable=false origin=VM_CREATION
ExampleDynamic value=false writeable=true origin=DEFAULT
heapDump: file must end with .hprof
live=true: reachable objects only
setVMOption: mutates a writeable VM option
```

Giải thích:

- `ExampleFixed` và `ExampleDynamic` là **VMOption mô phỏng** do constructor tạo ra, **không** phải hai HotSpot flags đã tồn tại.
- `isWriteable` và `Origin` được in theo chính giá trị truyền vào.
- Không có thao tác `bean().dumpHeap` hoặc `bean().setVMOption` nào chạy trong chế độ `fixture`.
- Vì không dựa vào heap/flag thực, stdout không phụ thuộc JVM arguments hay tải máy.

### 7.2 Chế độ chỉ đọc JVM thực

```bash
java HotSpotDiagnosticLab inspect
```

Lệnh in ObjectName của bean, số lượng option chẩn đoán và tối đa năm **tên** option theo alphabet. Không có stdout cố định vì số lượng/tên flag phụ thuộc JDK/build và option availability.

Nếu đã xác minh tên flag hiện diện trên JVM lab:

```bash
java HotSpotDiagnosticLab inspect HeapDumpOnOutOfMemoryError
```

Đây là **ví dụ tra cứu**, không khẳng định mọi HotSpot build đều phải cung cấp tên đó. Nếu flag không tồn tại, chương trình in `optionNotFound=...`. Nếu tồn tại, in cả `value`, `writeable`, `origin`. **Không đưa output có bí mật cấu hình ra kênh công khai**.

**Lưu ý:** mỗi lệnh `java HotSpotDiagnosticLab ...` khởi động **một JVM mới**. Nó phản ánh settings của chính JVM lab, **không** phản ánh một service Java khác đang chạy dù trên cùng máy. Với service thật, cần JMX kết nối đúng target hoặc đường chẩn đoán khác có quyền phù hợp.

### 7.3 Chế độ tạo dump có chủ đích

Chỉ chạy trong **môi trường lab có quyền**, sau khi kiểm tra dung lượng đĩa/thư mục/retention:

```bash
java HotSpotDiagnosticLab dump-lab ./lab-heap.hprof I_UNDERSTAND_THE_RISK
```

Lệnh này khởi động một JVM lab mới, tạo heap dump của **chính nó** với `live=true` rồi in đường dẫn đầy đủ. **Không thể dự đoán stdout chính xác** vì đường dẫn tuyệt đối, thao tác file và trạng thái VM phụ thuộc máy. Nếu file đã tồn tại, chương trình chủ động từ chối thay vì ghi đè. Chương trình vẫn phải chịu `IOException` hoặc các lỗi khác nếu filesystem không cho ghi.

Không chạy nó với dữ liệu production chỉ để làm bài tập: HPROF có thể chứa nội dung heap nhạy cảm và tạo file lớn. Chuỗi xác nhận chỉ giúp tránh gọi nhầm trong lab, **không thay thế quyền vận hành, policy bảo mật hoặc preflight tài nguyên**.

### 7.4 Chạy trên JVM không có HotSpot bean

Chế độ `fixture` chỉ dùng constructor `VMOption`. Chế độ `inspect` và `dump-lab` đòi HotSpotDiagnosticMXBean khả dụng. Nếu JDK runtime thiếu module `jdk.management` hoặc JVM không hỗ trợ interface, cần dùng công cụ tương ứng thay vì gọi API này và giả định lỗi của ứng dụng.

## 8. Nếu cần gọi qua JMX: điểm khác biệt quan trọng

ObjectName của HotSpotDiagnosticMXBean:

```text
com.sun.management:type=HotSpotDiagnostic
```

Trên JMX client phù hợp, có thể gọi operation `dumpHeap` hoặc `setVMOption` thông qua MBeanServerConnection. Nhưng **JMX remote management cần được bảo vệ nghiêm ngặt**:

- Có xác thực, mã hóa kết nối, firewall/allowlist và quyền tối thiểu theo hệ thống triển khai.
- Không mở remote JMX port ra Internet chỉ để chạy heap dump.
- Chỉ kết nối đúng JVM instance; với container/pod restart, định danh target theo deployment, PID, start time.
- Không đưa credential vào log hoặc command line có thể bị người khác đọc.
- Hệ thống điều khiển có thể phải đi qua audit/change-management; một JMX client đọc cũng có thể gọi operation **mutating** nếu được cấp quyền quá rộng.
- Tệp `dumpHeap` sẽ được tạo **trên target VM**, không tự xuất hiện trên máy remote operator. Cần thủ tục chuyển/cất giữ artifact an toàn.

Ví dụ khái niệm khi đã có `MBeanServerConnection connection` được thiết lập hợp lệ:

```java
HotSpotDiagnosticMXBean remote =
        ManagementFactory.newPlatformMXBeanProxy(
                connection,
                "com.sun.management:type=HotSpotDiagnostic",
                HotSpotDiagnosticMXBean.class);

VMOption current = remote.getVMOption("SomeVerifiedFlag");
```

Đoạn này là mã **tích hợp**, không độc lập: `connection` phải do JMX client đã xác thực tạo ra, `SomeVerifiedFlag` phải là flag hợp lệ. Vì đây là nền tảng quản trị từ xa, cần xử lý network timeout, kết nối ngắt, thay đổi pod/target, quyền và mọi lỗi giao tiếp.

Không tạo remote JMX server trong bài tập chỉ để demo điều này: cấu hình không đúng có thể mở bề mặt tấn công.

## 9. Quy trình chọn phương pháp chẩn đoán ít xâm lấn nhất

Trước khi thao tác, hỏi: **Mình muốn quan sát cấu hình, đo heap pressure hay cần phân tích object graph?**

### 9.1 Khi chỉ cần xác nhận flags

- Thu JDK vendor/version, `VM.command_line`, runtime arguments và build.
- Đọc `getVMOption(name)` cho tên đã biết, ghi `value/writeable/origin`.
- Nếu cần danh sách những options quản lý được, đọc `getDiagnosticOptions()`.
- Không đổi flag. Nếu nghi một flag đã bị chỉnh sau startup, so `origin` với audit/timeline quản trị.

Không cần heap dump để trả lời câu “`-Xmx` đang bao nhiêu?” hoặc “flag này có writable không?”.

### 9.2 Khi memory usage hoặc GC có dấu hiệu bất thường

- Bắt đầu bằng `MemoryMXBean`, per-pool metrics, GC logs/JFR, container memory/RSS, allocation rate và sau-GC occupancy.
- Xem hiện tượng ổn định hay chỉ GC sawtooth bình thường; tìm dependency/workload/memory pressure.
- Chỉ nếu cần **object count, dominator hoặc retaining path**, lập kế hoạch heap dump ở thời điểm đại diện.
- Ghi `live`, VM version, GC collector, workload, heap size và thời gian thu. Tránh dùng một snapshot duy nhất để khẳng định leak lâu dài.

### 9.3 Khi muốn thử điều chỉnh VM option

- Xây dựng giả thuyết và metric/guardrails định trước.
- Xác minh `isWriteable()` và semantics của flag ở phiên bản JDK hiện tại.
- Có owner/phê duyệt, ranh giới áp dụng, canary/rollback nếu trên production.
- Thu baseline, thực hiện **một thay đổi**, đọc lại flag và đo dưới cùng tải.
- Ghi tác dụng phụ/tình trạng khôi phục. Không coi flag được set thành công là nguyên nhân đã được giải quyết.

## 10. Một ví dụ điều tra heap tăng với quyết định có điều kiện

Giả sử dịch vụ `checkout` chạy JVM HotSpot với `-Xmx2g`, heap used sau GC tăng từ 900 MiB lên 1,7 GiB trong vài giờ. Đây là **số liệu giả định** để học cách suy luận.

**Giai đoạn A — Quan sát chưa can thiệp**

- Thu time series heap after GC, allocation rate, request mix, cache stats, transaction volume, container memory và GC pause.
- Xác định ứng dụng có vừa tăng lượng dữ liệu giữ cache hoặc mở thêm session không.
- Đọc flag cần thiết bằng `getVMOption`, không sửa giá trị.
- Đối chiếu heap used với metaspace/direct/native/RSS; container OOM có thể xảy ra ngay cả khi heap chưa đạt `Xmx`.

**Giai đoạn B — Lập kế hoạch dump**

Nếu cần retaining paths, quyết định thời điểm, đường dẫn đích, `live=true` hay `false`, disk/quota headroom, quyền, rủi ro pause và sự tác động tới request latency.

**Giai đoạn C — Dump có kiểm soát**

Vào thời điểm được chấp thuận, gọi `dumpHeap` trên target VM và đánh dấu timestamp. Theo dõi GC/pause/I/O trước-sau. Không chạy đồng thời nhiều dump hoặc đổi nhiều cờ cùng lúc vì sẽ mất khả năng quy nguyên nhân.

**Giai đoạn D — Phân tích**

Dùng công cụ phân tích HPROF tìm objects retained lớn, dominator, đường giữ tham chiếu tới GC roots và xác minh **vòng đời nghiệp vụ**: object đó có còn đáng được giữ không? So với dump khác **cùng phương pháp**, workload và mốc sau GC để có bằng chứng về growth. Thấy một `HashMap` lớn chưa đủ khẳng định leak, vì cache có thể có chủ đích.

**Giai đoạn E — Kết luận đúng phạm vi**

Nên viết: “Tại T2, dump `live=true` cho thấy một tập object vẫn reachable và chiếm phần lớn heap; retaining path dẫn đến cache X. Dữ liệu nhiều mốc và vòng đời cache cần kiểm tra thêm để xác nhận có giữ không cần thiết.” Không nên viết: “Heap dump đã chứng minh tất cả memory pressure đều do bug X” nếu chưa đối chiếu native memory, workload và đối chứng.

## 11. Khi điều tra JVM option khác mong đợi

Ví dụ: manifest khai báo một option ở startup nhưng `getVMOption` tại runtime cho thấy value khác.

Quy trình:

1. Xác nhận **đúng process** và build; Kubernetes có thể đã tạo pod từ revision khác.
2. Đọc `VMOption.getValue()` và `getOrigin()`; ghi timestamp.
3. Đối chiếu command line, môi trường, cgroup/resource policy, JDK ergonomic flags và audit log của management/attach.
4. Kiểm tra option có writeable không, có bị thay trong runtime không; `MANAGEMENT` hoặc `ATTACH_ON_DEMAND` là manh mối nhưng **không tự xác định ai làm**.
5. Nếu nghi ảnh hưởng hiệu năng, chạy phép so sánh có kiểm soát, giữ workload/cấu hình khác tương đương và đo guardrails.
6. Báo kết luận, owner, phương án làm bền thay đổi qua config/deployment nếu thật sự cần. Thay đổi một flag qua management **không tự sửa deployment manifest**; restart JVM có thể đưa nó về cấu hình khác.

Không tự suy mọi cờ runtime động là cấu hình được hỗ trợ lâu dài. Các flag chẩn đoán HotSpot có thể có tác dụng phụ, tính tương thích hoặc giới hạn theo phiên bản.

## 12. Bảng kiểm soát rủi ro cho `dumpHeap` và `setVMOption`

| Kiểm tra | Trước `dumpHeap` | Trước `setVMOption` |
| --- | --- | --- |
| Đúng mục tiêu | JVM/heap/container/PID, thời điểm cần snapshot | JVM/flag/version, giá trị ban đầu |
| Nhu cầu thực | Cần object graph, chưa đủ từ metric nhẹ | Có giả thuyết/tiêu chí đo và thay đổi cần thiết |
| Tài nguyên | Heap size, disk/quota, I/O, pause/GC headroom | CPU, latency, log volume, GC/other side effects |
| Quyền | Ghi file trên target, quyền JMX/OS | Quyền đổi runtime flag, owner/change approval |
| Tham số | Absolute `.hprof`, `live`, tên file duy nhất | `name/value`, `isWriteable`, valid value |
| Dữ liệu nhạy cảm | HPROF may hold secrets, encrypted storage/access | Runtime config có thể làm lộ thông tin hoặc đổi cách ghi log |
| Kiểm chứng | File tồn tại/đọc được, đúng timestamp, size, GC events | `getVMOption` snapshot mới, origin, metric guardrails |
| Khôi phục | Dọn artifact có kiểm soát, lưu evidence cần thiết | Rollback có kiểm chứng; tránh giả định mọi side effect đảo ngược |
| Báo cáo | Dump run ID/path/live/size/tác động | Before/after/owner/metric/giới hạn suy luận |

**Một điểm dễ bỏ sót:** thao tác ghi dump không phải “sửa code” nhưng có thể làm mất baseline heap tự nhiên do GC hoặc pause. Một thay đổi flag không phải “deploy mới” nhưng đủ để làm kết quả profiling không còn tương đương với trước đó.

## 13. Khi nào dùng những công cụ khác?

`HotSpotDiagnosticMXBean` là một mảnh trong bộ công cụ:

| Nhu cầu | Phương tiện phù hợp | Hạn chế |
| --- | --- | --- |
| Heap used/committed/max định kỳ | `MemoryMXBean` và metrics | Không cho retaining path |
| Cơ chế GC/paused time | GC logs, JFR, GC MXBeans | Cần cấu hình và hiểu collector |
| Đường giữ object, dominator | HPROF qua MXBean/jcmd, phân tích bằng heap analyzer | Snapshot nặng, dữ liệu nhạy cảm |
| Native memory | NMT qua `jcmd` khi đã bật | Không bao trùm toàn bộ native allocations |
| Top threads và contention | `ThreadMXBean`, `jcmd Thread.print`, JFR | Chi phí snapshot và giới hạn số liệu |
| Toàn bộ VM flags | `jcmd VM.flags -all`, output startup flags | Không nên coi là toàn bộ flag thay đổi động |
| VM option cụ thể đang được quản lý | `HotSpotDiagnosticMXBean.getVMOption` | Có thể thiếu flag trên VM/JDK khác |
| Thay VM option có thể quản lý | `HotSpotDiagnosticMXBean.setVMOption` | **Mutating**, kiểm soát như thay đổi cấu hình vận hành |

Không gọi `HotSpotDiagnosticMXBean` để tìm deadlock: cơ chế có mục đích khác như `ThreadMXBean.findDeadlockedThreads()`. Không dùng heap dump để đo CPU bottleneck. Chọn công cụ theo câu hỏi chẩn đoán.

## 14. Mẫu báo cáo thao tác và bằng chứng

```text
CONTEXT
- Service, environment, JVM vendor/version/patch, process ID:
- Container/pod/node, deployment/build revision:
- Symptom, request/workload, timezone và timestamp:

OBSERVATION BEFORE
- Heap/GC trend, RSS/container memory, latency/errors:
- Relevant VM option name/value/writeable/origin:
- Reason the lighter diagnostics were insufficient:

PROPOSED ACTION
- Read-only getVMOption/getDiagnosticOptions OR
  dumpHeap(outputFile,live) OR setVMOption(name,newValue):
- Approved owner/operation window/rollback authority:
- Expected GC/pause/CPU/I/O/security effects:
- File path on target VM, disk headroom, retention/access policy:

EXECUTION
- Exact command/API, parameters, timestamps, result/errors:
- For dump: path/size/access/hash if required:
- For flag change: before and after VMOption snapshots:

FOLLOW-UP
- JVM/cgroup/latency/GC metrics after action:
- What is confirmed, supported but uncertain, or untested:
- Alternative explanations, workload/measurement limitations:
- Cleanup of HPROF/recordings/config restoration:
- Next controlled test, owner, verification criteria:
```

Không để giá trị `VMOption.getValue()` chứa bí mật hoặc đường dẫn file HPROF nhạy cảm vào hệ thống log không được bảo vệ. Báo cáo là một phần của quy trình chẩn đoán, không phải nơi thay thế chứng cứ gốc.

## 15. Những lỗi phổ biến

1. **Gọi `dumpHeap` như đọc một counter nhẹ.** Đây là thao tác có thể rất nặng, ảnh hưởng GC/pause/I/O.
2. **Nhầm `live=true` với “chỉ objects đang xử lý request”.** Định nghĩa là object reachable; cache giữ sai vẫn có thể reachable.
3. **Cho rằng `live=false` nghĩa là dump không pause.** Nó thay đổi tập object được ghi, không bảo đảm overhead thấp.
4. **Gọi heap dump từ JMX remote rồi tìm file trên máy client.** File được ghi trong filesystem của target VM.
5. **Dùng đường dẫn tương đối mà không biết working directory của target.** Có thể lưu sai nơi hoặc gặp lỗi không ghi được.
6. **Không dự trù disk/quota và lưu HPROF như log thường.** File lớn có thể đầy disk và chứa dữ liệu nhạy cảm.
7. **Tin rằng dump luôn ghi đè file cũ.** Javadoc Java 17 nêu `IOException` khi outputFile đã tồn tại.
8. **Dùng tên không có đuôi `.hprof`.** API yêu cầu hậu tố và có thể từ chối bằng `IllegalArgumentException`.
9. **Lấy `getDiagnosticOptions()` làm danh sách mọi flag JVM.** API chỉ liệt kê nhóm diagnostic writeable.
10. **Nhầm `VMOption.isWriteable()` với thuộc tính “flag có ích” hoặc “không có side effects”.** Writable chỉ nói tính thay đổi động.
11. **Thử `setVMOption` trước khi đọc/ghi giá trị gốc.** Mất cơ sở rollback và có thể làm lệch phép đo.
12. **Gọi `setVMOption` với flag non-writeable.** `IllegalArgumentException` không phải bug application.
13. **Cho rằng object `VMOption` tự cập nhật sau khi set.** Giá trị là snapshot; phải gọi `getVMOption` lại.
14. **Đọc `origin=MANAGEMENT` rồi khẳng định đã biết người thay đổi.** Origin không phải audit log.
15. **Đổi nhiều flag và tạo dump trong cùng một cửa sổ mà không ghi timeline.** Không thể tách tác động của từng can thiệp.
16. **Suy “không có memory leak” từ một snapshot heap nhỏ.** Có thể dump sai thời điểm, sau GC, dưới tải thấp hoặc thiếu đường retained growth.
17. **Nhầm heap memory với toàn bộ process/container memory.** JNI/native, direct buffers, metaspace, thread stacks và page cache còn tiêu thụ tài nguyên.
18. **Đưa remote JMX không xác thực ra mạng.** Các operation chẩn đoán có thể tạo file lớn hoặc đổi VM option.
19. **Dùng số liệu JDK khác để suy semantics flag JVM hiện tại.** HotSpot flags có thể thay đổi giữa vendor/build/major version.
20. **Xem một lần `setVMOption` thành công là fix.** Phải đo hiệu quả dưới tải, correctness, error rate, guardrails và khả năng duy trì sau restart.

## 16. Câu hỏi tự kiểm tra

1. `HotSpotDiagnosticMXBean` thuộc module/package nào, và ObjectName chính xác của nó trong JMX là gì?
2. `getVMOption(name)` khác `getDiagnosticOptions()` ở phạm vi nào? Vì sao cả hai không thay thế toàn bộ output `jcmd VM.flags -all`?
3. `VMOption.getValue()`, `isWriteable()`, `getOrigin()` cung cấp những thông tin khác nhau thế nào?
4. Vì sao sau `setVMOption(name,newValue)` phải gọi `getVMOption(name)` lần nữa? Object `VMOption` cũ có đổi nội dung không?
5. `dumpHeap(path,true)` và `dumpHeap(path,false)` yêu cầu tập object nào? Có thể dùng `false` để bảo đảm không xảy ra pause hay không?
6. Khi JMX client chạy trên máy A, target JVM chạy trên máy B, file HPROF xuất hiện ở đâu?
7. `dumpHeap` gặp file đã tồn tại hoặc filename thiếu `.hprof` thì có thể báo lỗi nào?
8. Vì sao `isWriteable=true` vẫn không đủ để kết luận “nên chỉnh flag này ngay trên production”?
9. Trong một container memory limit 1 GiB, Java heap used 600 MiB, có thể bị OOMKilled không? Những loại memory khác phải đo?
10. Một heap dump cho thấy nhiều objects thuộc cùng một cache. Những bằng chứng nào cần thêm để xác nhận cache đang giữ đối tượng không còn cần thiết?
11. Nếu `VMOption.getOrigin()==MANAGEMENT`, bạn đã biết ai thực hiện thay đổi chưa? Phải kiểm tra gì thêm?
12. Hãy mô tả một quy trình **đọc trước → xác minh quyền/tài nguyên → thao tác có kiểm soát → đọc lại → đo guardrails → bàn giao và cleanup** cho tình huống cần heap dump.

## Tài liệu tham khảo

- Oracle Java SE 17 — `HotSpotDiagnosticMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html
- Oracle Java SE 17 — `VMOption`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.html
- Oracle Java SE 17 — `VMOption.Origin`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.Origin.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Ghi nhớ:** `HotSpotDiagnosticMXBean` cho phép **đọc các VM options**, **ghi HPROF của Java heap** và **thay đổi một số options có thể quản lý**. Phải phân biệt thao tác đọc với thao tác tạo artifact/đổi runtime state; hiểu `live`, `isWriteable` và `origin`; bảo vệ dữ liệu dump và kiểm soát can thiệp. Một kết quả API thành công chỉ là bằng chứng kỹ thuật ở phạm vi của nó, không tự động chứng minh nguyên nhân memory leak hoặc sự cố đã được khắc phục.