# Phát hiện API đã bị bỏ và thay bằng API công khai còn hỗ trợ

Khi nâng cấp JDK, một ứng dụng có thể gặp ba loại vấn đề: mã nguồn không biên dịch vì API đã bị xóa, bytecode cũ không liên kết được khi chạy vì class hoặc method không còn tồn tại, và hành vi thay đổi dù chương trình vẫn biên dịch và khởi động thành công. Cần phát hiện cả ba trước khi đưa runtime mới vào production.

Java SE 26 đã xóa một số API như Applet API, `Thread.stop()`, các method TTL cũ của multicast socket, XML interchange của `DescriptorSupport` và finalizer trong Image I/O. JDK 27 cũng đã phát hành vào tháng 9 năm 2026; ngoài các thay đổi của JDK 26, JDK 27 loại bỏ JVMCI và một số tùy chọn launcher cũ. Bài này tập trung vào API và cơ chế công khai còn được hỗ trợ, đồng thời phân biệt trường hợp có API thay thế với trường hợp cần thiết kế lại chức năng.

## 1. Phân biệt API deprecated, deprecated for removal và removed

Không phải mọi cảnh báo deprecated đều có cùng mức độ khẩn cấp:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Deprecated | API vẫn tồn tại nhưng không còn được khuyến nghị; có thể có API thay thế | Lập kế hoạch chuyển sang API được khuyến nghị, kiểm tra lý do deprecated |
| Deprecated for removal | API được đánh dấu có thể bị xóa trong một bản JDK tương lai | Ưu tiên loại bỏ khỏi code và dependency trước lần nâng cấp kế tiếp |
| Removed | API không còn trong runtime | Mã nguồn phải được sửa; bytecode cũ có thể lỗi liên kết lúc chạy |
| Internal/unsupported API | API nội bộ của JDK, không phải hợp đồng tương thích công khai | Chuyển sang API chuẩn hoặc API công khai được tài liệu hóa |
| Removed tool/VM option | Công cụ hoặc cờ khởi chạy không còn được hỗ trợ | Xóa hoặc thay bằng tùy chọn được release notes chỉ rõ |

Annotation `@Deprecated` có thể cung cấp `since` và `forRemoval`. Ví dụ:

```java
@Deprecated(since = "18", forRemoval = true)
public void oldOperation() {
    // API cũ đang chờ bị loại bỏ.
}
```

Không suy luận rằng một API vẫn an toàn chỉ vì nó còn xuất hiện trong JavaDoc của JDK hiện tại. Cần đọc mô tả deprecated, release notes và migration guide của đúng bản JDK mục tiêu.

Khi một method đã bị xóa:

- Biên dịch source code mới thường báo không tìm thấy symbol.
- Bytecode được biên dịch bằng JDK cũ có thể khởi động được nhưng ném `NoSuchMethodError` hoặc `NoClassDefFoundError` khi đường chạy chạm tới API đã mất.
- Reflection, tên class lưu trong cấu hình, plugin hoặc code sinh động có thể chỉ lỗi khi chạy một chức năng hiếm được gọi.

## 2. Quy trình tìm dependency vào API đã bị xóa

Thực hiện việc rà soát trên đúng artifact sẽ được triển khai, bao gồm ứng dụng, thư viện nội bộ và các dependency:

1. Xác định JDK nguồn và JDK đích. Với module này, kiểm tra JDK 26; nếu runtime mục tiêu hiện tại là JDK 27 thì kiểm tra cả thay đổi của JDK 27.
2. Đọc release notes và migration guide của từng bản JDK đi qua. Không chỉ đọc thay đổi của bản đích cuối cùng nếu ứng dụng nhảy qua nhiều major release.
3. Quét API deprecated for removal bằng `jdeprscan`.
4. Quét dependency vào package nội bộ bằng `jdeps --jdk-internals`.
5. Tìm trong source, cấu hình, launcher script, Dockerfile, build file, plugin descriptor, service provider file, reflection string và native integration.
6. Chạy ứng dụng trên JDK đích trước khi hoặc song song với việc biên dịch lại; kiểm tra cả log cảnh báo lẫn hành vi.
7. Cập nhật dependency bên thứ ba, biên dịch lại, chạy unit test, integration test và smoke test trên đúng JDK/provider/OS production.

### Quét API deprecated bằng jdeprscan

`jdeprscan` là công cụ static analysis đi kèm JDK. Nó quét class, thư mục class hoặc JAR để tìm tham chiếu tới các API Java SE đã deprecated. Để liệt kê API deprecated for removal của JDK đang dùng:

```powershell
jdeprscan --list --for-removal
```

Để quét artifact ứng dụng trên Windows:

```powershell
jdeprscan --for-removal --class-path "build\classes;lib\dependency-a.jar;lib\dependency-b.jar" build\app.jar
```

Nếu cần quét toàn bộ API deprecated thay vì chỉ API được đánh dấu for removal, bỏ `--for-removal`:

```powershell
jdeprscan --class-path "build\classes;lib\*" build\app.jar
```

Chạy `jdeprscan` từ JDK đích để danh sách API phản ánh release đang chuẩn bị triển khai. `--list` chỉ in danh sách, không nhận JAR để quét. `--class-path` phải có các dependency mà bytecode được quét tham chiếu; nếu thiếu class, công cụ sẽ báo `cannot find class`, khi đó kết quả chưa đầy đủ.

Giới hạn cần nhớ: `jdeprscan` chỉ báo deprecated API thuộc Java SE. Nó không báo deprecated API riêng của thư viện bên thứ ba, không thay thế `jdeps`, và không thể phát hiện mọi lời gọi được tạo qua reflection hoặc native code.

### Quét JDK internal API bằng jdeps

`jdeps --jdk-internals` tìm tham chiếu bytecode đến package/class nội bộ của JDK:

```powershell
jdeps --jdk-internals --class-path "lib\*" build\app.jar
```

Với multi-release JAR, chỉ định phiên bản bytecode cần phân tích:

```powershell
jdeps --jdk-internals --multi-release 26 --class-path "lib\*" build\app.jar
```

Internal API như `sun.*`, `com.sun.*` hoặc `jdk.internal.*` không phải cam kết tương thích giữa các JDK vendor/release. Một số API có thể vẫn còn trong một JDK nhưng bị đóng gói, đổi implementation hoặc biến mất ở release khác. Đừng coi `--add-exports` hay `--add-opens` là API thay thế.

`jdeps` là static analysis. Nó có thể bỏ sót truy cập qua reflection, `Class.forName()` với tên class lấy từ cấu hình, JNI, native library, bytecode được sinh lúc chạy hoặc plugin được nạp sau khi khởi động. Vì vậy, kết quả quét sạch không chứng minh ứng dụng không có dependency động.

### Biên dịch theo API mục tiêu và kiểm tra lúc chạy

Nếu build bằng JDK 27 nhưng ứng dụng cần tương thích Java 26, dùng `--release 26` để compiler chỉ cho phép API của release 26:

```powershell
javac --release 26 -Xlint:deprecation -d build\classes @sources.txt
```

`sources.txt` chứa danh sách file source theo định dạng argument file của `javac`. `--release` kiểm soát API Java SE có thể dùng khi biên dịch. Nó không quét API nội bộ trong dependency đã biên dịch và không phát hiện cờ VM cũ trong script khởi chạy. Nếu mục tiêu là JDK 27 thì đổi release tương ứng.

Chạy artifact thật trên runtime đích. Kiểm thử đường chạy ít được dùng, plugin, serialization, network, GUI, scheduled task, shutdown hook và các thao tác chỉ chạy khi tắt ứng dụng. Một lần khởi động thành công chưa đủ chứng minh tương thích.

## 3. Thay Thread.stop bằng cancellation có kiểm soát

`Thread.stop()` đã bị xóa trong JDK 26. Đây là API nguy hiểm vì nó có thể dừng thread giữa lúc đang cập nhật object hoặc giữ invariant, khiến dữ liệu và trạng thái dùng chung không nhất quán. Không có API công khai nào thay thế bằng một lệnh “kill thread ngay lập tức” an toàn.

Thiết kế task để tự kết thúc khi nhận tín hiệu interruption hoặc cancellation:

```java
final class ImportTask implements Runnable {
    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                importNextBatch();
            }
        } catch (InterruptedException interrupted) {
            // Khôi phục trạng thái để tầng gọi biết task đã bị interrupt.
            Thread.currentThread().interrupt();
        }
    }

    private void importNextBatch() throws InterruptedException {
        // Xử lý một đơn vị công việc có giới hạn.
        // Các thao tác chờ nên hỗ trợ interruption hoặc timeout.
    }
}
```

Nếu task được submit vào executor, giữ `Future` để yêu cầu hủy:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
Future<?> future = executor.submit(new ImportTask());

// Khi cần yêu cầu task dừng:
future.cancel(true);

executor.shutdown();
if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    executor.shutdownNow(); // Nỗ lực interrupt các task còn chạy.
}
```

`Future.cancel(true)` yêu cầu interrupt thread đang thực thi nếu implementation biết thread đó. Nó không đảm bảo task dừng nếu task bỏ qua interruption hoặc mắc trong native call không thể ngắt. `shutdownNow()` cũng chỉ là best effort. Task phải kiểm tra interruption ở vòng lặp, dùng các API blocking có hỗ trợ interruption, đặt timeout cho I/O và giải phóng tài nguyên trong `finally`/try-with-resources.

Nếu task bị chặn trong một API I/O không phản hồi interruption, chủ sở hữu task có thể cần đóng channel/socket/resource liên quan để làm thao tác thoát ra. Thiết kế resource ownership rõ ràng để việc đóng không ảnh hưởng nhầm tới task khác.

Nếu bắt `InterruptedException` mà không thể ném tiếp, thường phải gọi `Thread.currentThread().interrupt()` trước khi kết thúc hoặc chuyển lỗi. Không dùng `Thread.interrupted()` để kiểm tra tùy tiện vì method này đọc và xóa interrupted status.

## 4. Thay các method TTL cũ của MulticastSocket

JDK 26 xóa các method đã terminally deprecated:

- `MulticastSocket.setTTL(byte)` và `getTTL()`.
- `MulticastSocket.send(DatagramPacket, byte)`.
- `DatagramSocketImpl.setTTL(byte)` và `getTTL()`.

Với multicast socket công khai, dùng `setTimeToLive(int)`, `getTimeToLive()` và `send(DatagramPacket)`:

```java
try (MulticastSocket socket = new MulticastSocket()) {
    socket.setTimeToLive(16);

    int ttl = socket.getTimeToLive();
    System.out.println("Current multicast TTL: " + ttl);

    socket.send(packet);
}
```

`setTimeToLive(int)` dùng kiểu `int` và chấp nhận giá trị từ 0 đến 255. Đây là TTL mặc định của socket cho các multicast packet tiếp theo. API mới không cung cấp tham số TTL riêng trong từng lần gọi `send()` như overload cũ.

Có thể cấu hình socket option chuẩn:

```java
socket.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 16);
int ttl = socket.getOption(StandardSocketOptions.IP_MULTICAST_TTL);
```

Nếu các packet đồng thời cần TTL khác nhau, không thay đổi TTL trên cùng socket mà không đồng bộ: một thread có thể đổi option trước khi thread khác gửi packet. Dùng socket riêng cho từng chính sách TTL hoặc tuần tự hóa thao tác đổi TTL và gửi. Với code multicast dùng NIO, xem `DatagramChannel`/`MulticastChannel` và `StandardSocketOptions.IP_MULTICAST_TTL`.

Nếu đang tự viết implementation dựa trên `DatagramSocketImpl`, hãy kiểm tra lại SPI và thiết kế provider theo API được tài liệu hóa hiện hành. Không giữ override cho method đã bị xóa hoặc dùng reflection để gọi implementation cũ.

## 5. Thay finalization bằng đóng tài nguyên tường minh

JDK 26 loại bỏ các method `finalize()` khỏi `ImageInputStreamImpl` và các lớp con trong Image I/O. JDK 27 cũng loại bỏ `ThreadPoolExecutor.finalize()`. Đây là một phần của quá trình loại bỏ finalization khỏi Java.

Với `ImageInputStream`, API `close()` đã tồn tại và interface triển khai `AutoCloseable`; dùng try-with-resources:

```java
try (ImageInputStream input =
        ImageIO.createImageInputStream(new File("photo.png"))) {
    if (input == null) {
        throw new IOException("No ImageInputStream provider is available");
    }

    // Đọc dữ liệu ảnh trong phạm vi resource còn mở.
}
```

Đối với lớp tự quản lý tài nguyên, cung cấp `close()` và triển khai `AutoCloseable`:

```java
final class NativeBuffer implements AutoCloseable {
    private long address;

    @Override
    public void close() {
        if (address != 0) {
            releaseNativeBuffer(address);
            address = 0;
        }
    }

    private static void releaseNativeBuffer(long address) {
        // Gọi hàm giải phóng native memory do ứng dụng quản lý.
    }
}

try (NativeBuffer buffer = new NativeBuffer()) {
    // Sử dụng buffer.
}
```

`Cleaner` hoặc `PhantomReference` có thể là lớp bảo vệ cuối cùng cho resource khi object bị bỏ quên, nhưng không thay thế việc đóng tài nguyên đúng lúc. Cleanup action không nên giữ tham chiếu mạnh tới object cần được thu hồi. Với resource có vòng đời xác định, ưu tiên `close()`/try-with-resources.

Với `ThreadPoolExecutor`, đừng dựa vào finalizer để shutdown executor. Quản lý vòng đời bằng `ExecutorService.close()` (có thể dùng try-with-resources trên JDK hiện hành), hoặc gọi `shutdown()`/`awaitTermination()` rõ ràng. Nếu executor sống suốt vòng đời ứng dụng, đóng nó trong lifecycle hook của ứng dụng.

## 6. Thay XML interchange đã bị xóa khỏi DescriptorSupport

JDK 26 loại bỏ XML interchange của `javax.management.modelmbean.DescriptorSupport`: constructor `DescriptorSupport(String inStr)`, method `toXMLString()` và exception `XMLParseException` bị xóa. Các API quản lý descriptor vẫn còn hỗ trợ, gồm constructor nhận field names/values, `getFieldNames()`, `getFieldValues()`, `getFields()`, `setField()` và `setFields()`.

Tạo descriptor trực tiếp từ các field:

```java
String[] names = {"name", "descriptorType"};
Object[] values = {"orders", "mbean"};

DescriptorSupport descriptor = new DescriptorSupport(names, values);
descriptor.setField("displayName", "Orders service");

String[] fieldNames = descriptor.getFieldNames();
Object[] fieldValues = descriptor.getFieldValues(fieldNames);

DescriptorSupport copy = new DescriptorSupport(fieldNames, fieldValues);
```

Nếu hệ thống đang truyền `DescriptorSupport.toXMLString()` giữa các process, cần định nghĩa định dạng trao đổi thuộc quyền quản lý của ứng dụng (ví dụ JSON có schema/version rõ ràng), ánh xạ các field sang định dạng đó và kiểm tra kiểu dữ liệu khi đọc. `Descriptor.toString()` chỉ là chuỗi dễ đọc cho con người, không phải định dạng serialization để khôi phục descriptor.

Không dùng `XMLParseException` như exception ứng dụng riêng. Dùng lỗi của định dạng serialization do ứng dụng chọn, hoặc `IOException`/exception miền nghiệp vụ với nguyên nhân cụ thể.

## 7. Các API JDK 26 khác đã bị xóa

| API đã xóa | Cách xử lý hiện hành |
|---|---|
| `java.applet.*`, `javax.swing.JApplet`, `java.beans.AppletInitializer` và overload `Beans.instantiate(..., AppletInitializer)` | Applet không còn được browser hoặc JDK hiện đại hỗ trợ; không có API thay thế một-một. Chuyển chức năng thành web application/service hoặc desktop application độc lập. Với JavaBeans, dùng cơ chế tạo object/factory hoặc dependency injection của ứng dụng thay cho applet lifecycle. |
| `javax.imageio.spi.ServiceRegistry.finalize()` và các `finalize()` của Image I/O streams | Bỏ phụ thuộc finalization; đóng stream bằng `close()`/try-with-resources và quản lý tài nguyên do plugin tạo bằng lifecycle rõ ràng. |
| `javax.management.modelmbean.XMLParseException` | Không còn exception dành cho XML interchange của `DescriptorSupport`; dùng lỗi của định dạng trao đổi do ứng dụng quản lý. |
| `javax.swing.RepaintManager.addDirtyRegion(...)` | Yêu cầu component vẽ lại qua API công khai như `JComponent.repaint()` hoặc overload vùng vẽ của component. Không thao tác trực tiếp với dirty-region queue nội bộ. |
| `Beans.instantiate(..., AppletInitializer)` | Bỏ tham số applet initializer; dùng constructor/factory/container của ứng dụng cho việc tạo bean. |

Không phải API bị xóa nào cũng có replacement trực tiếp. Nếu chức năng gốc đã lỗi thời hoặc không còn được nền tảng hỗ trợ, cần loại bỏ chức năng hoặc thiết kế lại giao thức thay vì tìm một class có tên gần giống.

## 8. Những thay đổi cần biết khi runtime hiện tại là JDK 27

JDK 27 phát hành tháng 9 năm 2026. Khi nâng từ JDK 26 lên JDK 27, cần kiểm tra thêm các thay đổi sau:

| Thành phần bị loại bỏ | Hướng xử lý |
|---|---|
| `ThreadPoolExecutor.finalize()` | Bỏ override/call `finalize()`; đóng executor tường minh bằng `ExecutorService.close()` hoặc `shutdown()`/`awaitTermination()`. |
| JVMCI và các module `jdk.internal.vm.ci`, `jdk.graal.compiler`, `jdk.graal.compiler.management`; cờ `-XX:+UseGraalJIT` và các cờ JVMCI | JVMCI là giao diện compiler thử nghiệm, không phải Java SE API công khai. JDK 27 không còn hỗ trợ đường tích hợp này. Dùng compiler mặc định của HotSpot, hoặc một runtime/phân phối riêng được nhà cung cấp compiler hỗ trợ nếu ứng dụng phụ thuộc Graal. |
| `-noverify`, `-Xverify:none` | Không có replacement. Giữ bytecode verification bật; không vô hiệu hóa kiểm tra class file. |
| `-verifyremote` | Dùng `-Xverify:remote` nếu thật sự cần cùng chế độ xác minh tương ứng. |
| `-noclassgc` | Dùng `-Xnoclassgc` nếu có lý do vận hành đã được đo và kiểm chứng để tắt class unloading. |
| `-Djdk.lang.Process.launchMechanism=VFORK` trên Linux | Bỏ cờ và dùng cơ chế mặc định `POSIX_SPAWN`, hoặc chọn `FORK` nếu cần và đã kiểm thử. |
| `java.locale.useOldISOCodes` | Bỏ property; dùng mã ngôn ngữ ISO hiện hành: `he`, `yi`, `id` thay cho các mã cũ tương ứng. |

JDK 27 cũng deprecated for removal một số overload `DocSourcePositions`/`SourcePositions` nhận `CompilationUnitTree`:

```java
// API mới trong JDK 27:
long start = sourcePositions.getStartPosition(tree);
long end = sourcePositions.getEndPosition(tree);

long docStart = docSourcePositions.getStartPosition(docComment, docTree);
long docEnd = docSourcePositions.getEndPosition(docComment, docTree);
```

Khi dùng Compiler Tree API, chuyển sang overload không cần truyền `CompilationUnitTree`. Đây là thay đổi JDK 27; nếu build target Java 26 thì cần giữ tương thích API theo `--release 26` hoặc cô lập phần tích hợp compiler theo runtime.

## 9. Xử lý dependency vào JDK internal API

Các package nội bộ như `sun.*`, `com.sun.*` hoặc `jdk.internal.*` không phải public API chỉ vì có thể import được trong một số cấu hình. JDK 9 trở đi áp dụng module system và strong encapsulation; việc thêm `--add-exports` hoặc `--add-opens` có thể giúp ứng dụng cũ tạm chạy, nhưng không tạo ra cam kết tương thích.

Ví dụ, nếu code gọi một internal class để thao tác memory, hãy tìm API được chuẩn hóa theo mục đích:

- Truy cập biến/field có ngữ nghĩa cần kiểm soát: xem `VarHandle`.
- Truy cập native memory hoặc native function: xem Foreign Function & Memory API.
- Duyệt stack/caller: xem Stack-Walking API.
- Mã hóa Base64: dùng `java.util.Base64` nếu gặp dependency nội bộ cũ.

Không thay một internal API bằng một API công khai chỉ vì tên tương tự. Phải xác định chính xác semantics đang được dùng: atomicity, memory ordering, lifetime, alignment, exception behavior và hiệu năng.

Nếu buộc phải dùng `--add-exports`/`--add-opens` để triển khai chuyển tiếp:

1. Giới hạn package và module cụ thể; tránh mở toàn bộ module.
2. Ghi issue và phiên bản kết thúc workaround.
3. Thêm kiểm thử chạy trên JDK đích và JDK kế tiếp.
4. Theo dõi warning/diagnostic trong runtime.
5. Xóa cờ ngay khi đã chuyển sang API công khai.

Không dùng các cờ này như một biện pháp thay thế lâu dài cho migration.

## 10. Tìm API thay thế từ tài liệu chính thức

Với mỗi API bị deprecated hoặc removed:

1. Mở trang JavaDoc của element cũ trong JDK nguồn, đọc phần Deprecated và See Also.
2. Mở JavaDoc của API được gợi ý; xác minh Since, module, exception, semantics và khả năng chạy trên release mục tiêu.
3. Kiểm tra API mới có phải public Java SE API hay chỉ là JDK-specific extension.
4. Đọc release notes để biết API bị xóa ở release nào và có thay đổi hành vi liên quan hay không.
5. Nếu không có replacement, xác định chức năng cần loại bỏ hoặc thay đổi ở cấp kiến trúc.
6. Cập nhật cả code, test, dependency, config, launcher flags và tài liệu vận hành.

Phân biệt ba dạng replacement:

- **Thay thế tương đương:** ví dụ `MulticastSocket.getTTL()` sang `getTimeToLive()`.
- **Thay đổi cách sử dụng:** ví dụ `Thread.stop()` sang cooperative cancellation; `finalize()` sang explicit resource lifecycle.
- **Không có replacement một-một:** ví dụ Applet API, SecurityManager hoặc tùy chọn vô hiệu hóa bytecode verification. Cần thiết kế lại hoặc bỏ chức năng.

## 11. Ma trận kiểm thử sau khi thay API

Một migration chưa hoàn tất khi chỉ sửa compile error. Kiểm thử cả source, binary và behavioral compatibility:

| Lớp kiểm thử | Nội dung cần xác nhận |
|---|---|
| Compile | Không còn reference tới API đã xóa; `-Xlint:deprecation` không tạo warning ngoài danh sách đã chấp nhận |
| Bytecode/dependency | `jdeprscan` và `jdeps --jdk-internals` không còn dependency cần loại bỏ |
| Runtime linkage | Không có `NoSuchMethodError`, `NoSuchFieldError`, `NoClassDefFoundError` khi nạp class/plugin |
| Cancellation | Task phản hồi interruption, không để transaction/tài nguyên ở trạng thái dở dang |
| Network | Multicast TTL đúng, interface đúng, packet scope đúng và không có race khi nhiều sender |
| Resource lifecycle | Stream, executor, native resource được đóng khi thành công, lỗi và cancellation |
| JMX/serialization | Descriptor giữ nguyên field/value qua định dạng trao đổi mới; xử lý được field type không phải String |
| GUI/Image I/O | Component repaint đúng; ImageInputStream được đóng và dữ liệu cache được flush |
| Deployment | Script, container image, startup option và service configuration không còn cờ hoặc module đã bị xóa |

Chạy test với đúng OS, architecture, JDK vendor, JDK update, GC, container limit, provider và dependency version như production. Với thay đổi networking hoặc cryptography, test với endpoint/provider thực tế; unit test mock không chứng minh tương thích giao thức.

## 12. Checklist trước khi phát hành

- [ ] Đã xác định JDK nguồn, JDK đích và mọi release trung gian.
- [ ] Đã đọc migration guide, removed APIs, removed tools/components và deprecated API list của JDK đích.
- [ ] Đã chạy `jdeprscan --for-removal` trên ứng dụng và các JAR nội bộ.
- [ ] Đã chạy `jdeps --jdk-internals` trên artifact, bao gồm multi-release JAR khi có.
- [ ] Đã kiểm tra reflection, JNI, plugin, service provider và cấu hình động.
- [ ] Đã thay API bằng public API có semantics phù hợp hoặc thiết kế lại chức năng không còn replacement.
- [ ] Đã loại bỏ workaround `--add-opens`/`--add-exports` không còn cần thiết.
- [ ] Đã rà soát launcher flags, system properties, tool scripts và module path.
- [ ] Đã biên dịch theo `--release` của runtime mục tiêu.
- [ ] Đã chạy integration test và smoke test trên JDK đích.

## 13. Những điểm cần nhớ

- Deprecated, deprecated for removal và removed là ba trạng thái khác nhau; kiểm tra đúng release.
- `jdeprscan` tìm deprecated Java SE API; `jdeps --jdk-internals` tìm dependency bytecode tới internal JDK API. Hai công cụ bổ sung cho nhau.
- Static analysis không phát hiện đầy đủ reflection, JNI, tên class trong cấu hình, cờ launcher hoặc mọi dependency runtime.
- JDK 26 đã xóa Applet API, `Thread.stop()`, method TTL cũ, finalizer của Image I/O và XML interchange của `DescriptorSupport`.
- `Thread.stop()` được thay bằng cancellation hợp tác; không có lệnh kill thread an toàn tương đương.
- Multicast TTL hiện dùng `setTimeToLive(int)`/`getTimeToLive()` hoặc `IP_MULTICAST_TTL`; TTL là cấu hình socket, cần chú ý concurrency.
- Finalization được thay bằng `close()`/`AutoCloseable` và try-with-resources; `Cleaner` chỉ là cơ chế dự phòng.
- JDK 27 loại bỏ `ThreadPoolExecutor.finalize()`, JVMCI và các cờ `-noverify`/`-Xverify:none`; không có replacement cho việc tắt verification.
- `--add-exports` và `--add-opens` là workaround chuyển tiếp, không phải public API thay thế.
- Nếu không có replacement một-một, cần loại bỏ chức năng lỗi thời hoặc thiết kế lại ở cấp ứng dụng/giao thức.

## Tài liệu tham khảo

- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/index.html)
- [Java SE 26: Removed APIs](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html)
- [Java SE 26: Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
- [Java SE 26: jdeprscan command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [Java SE 27: jdeps command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html)
- [Java SE 26: Deprecated API list](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html)
- [Java SE 27: Deprecated API list](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html)
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Java SE 26 API: Thread](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html)
- [Java SE 26 API: MulticastSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/MulticastSocket.html)
- [Java SE 26 API: ImageInputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/stream/ImageInputStream.html)
- [Java SE 26 API: DescriptorSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/modelmbean/DescriptorSupport.html)
- [Java SE 27 API: ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
