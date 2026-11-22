# Mô-đun `jdk.nio.mapmode` và `ExtendedMapMode` khi ánh xạ bộ nhớ NVM

## 1. Bối cảnh và mục tiêu

**NVM (Non-Volatile Memory)** là bộ nhớ có khả năng giữ dữ liệu sau khi mất điện. Với phần cứng và hệ thống tệp phù hợp, ứng dụng có thể **ánh xạ vùng tệp trên persistent memory** vào không gian địa chỉ của tiến trình, rồi đọc/ghi qua `MappedByteBuffer`. Điều này có thể tránh một số tầng I/O truyền thống, nhưng **không tự động biến mọi thao tác ghi thành giao dịch bền vững**.

Từ **Java 14**, JEP 352 — *Non-Volatile Mapped Byte Buffers* — bổ sung hai chế độ ánh xạ đặc thù của JDK:

- `ExtendedMapMode.READ_ONLY_SYNC` — ánh xạ chỉ đọc trên tệp được hỗ trợ bởi NVM.
- `ExtendedMapMode.READ_WRITE_SYNC` — ánh xạ đọc/ghi trên tệp được hỗ trợ bởi NVM, với cơ chế `force` có thể dùng ghi trả các cache line.

Hai hằng số được định nghĩa trong lớp `jdk.nio.mapmode.ExtendedMapMode` thuộc **mô-đun có tên `jdk.nio.mapmode`**. Đến các JDK hiện hành, mô-đun và lớp này **vẫn tồn tại và được tài liệu hóa**; đây là **API đặc thù của JDK** chứ không phải một tính năng Java SE đa nền tảng được mọi JVM cam kết hỗ trợ.

**Mục tiêu bài học:** biết khai báo module, import đúng lớp, dùng `FileChannel.map(...)` với `ExtendedMapMode`, phân biệt với các `MapMode` tiêu chuẩn, kiểm soát tính bền vững qua `MappedByteBuffer.force()`, xử lý điều kiện nền tảng và có chương trình Java 17+ chạy được ngay cả khi máy không có NVM/DAX.

**Lưu ý phiên bản:** bài chỉ dùng cú pháp và API còn phù hợp với Java 17+, không yêu cầu preview flag hay cách dùng đã legacy. JEP 352 xuất hiện từ Java 14 là một mốc lịch sử, không phải lời hứa rằng mọi máy chạy Java 14+ đều có phần cứng lưu trữ cho `MAP_SYNC`.

## 2. Tách bạch module, package, lớp và kiểu MapMode

Ba tên rất dễ nhầm:

| Thành phần | Tên đầy đủ | Vai trò |
| --- | --- | --- |
| **JPMS module** | `jdk.nio.mapmode` | Cung cấp những chế độ ánh xạ tệp đặc thù JDK |
| **Package** | `jdk.nio.mapmode` | Chứa lớp `ExtendedMapMode` |
| **Lớp API** | `jdk.nio.mapmode.ExtendedMapMode` | Cung cấp các hằng số `READ_ONLY_SYNC` và `READ_WRITE_SYNC` |
| **Kiểu của hằng số** | `FileChannel.MapMode` | Kiểu tham số mà `FileChannel.map(...)` nhận |

Dù module và package có cùng tên, **`requires` nhận tên module, còn `import` nhận tên lớp/package**.

Với ứng dụng **JPMS có tên**, khai báo trong `module-info.java`:

```java
module com.example.nvm {
    requires jdk.nio.mapmode;
}
```

Trong lớp Java dùng:

```java
import jdk.nio.mapmode.ExtendedMapMode;
import java.nio.channels.FileChannel;
import java.nio.MappedByteBuffer;
```

Bạn **không cần** viết `requires java.base;`, vì mọi module Java tự đọc `java.base`, nơi có `FileChannel` và `MappedByteBuffer`.

**Điều không đúng:** `requires jdk.nio.mapmode.ExtendedMapMode;`. Đây là tên **lớp**, không phải module. Cũng không có lý do dùng `--add-exports jdk.nio.mapmode/...` đối với package công khai đã được module xuất ra.

### Dùng trong ứng dụng classpath (unnamed module)

Khi không có `module-info.java`, để compiler và launcher phân giải module đặc thù này một cách tường minh, dùng:

```bash
javac --release 17 --add-modules jdk.nio.mapmode NvmMappingDemo.java
java --add-modules jdk.nio.mapmode NvmMappingDemo
```

`--add-modules jdk.nio.mapmode` đưa module JDK này vào tập module được phân giải cho chương trình classpath. Trong một ứng dụng JPMS có `requires jdk.nio.mapmode;`, việc phân giải được điều khiển bởi module descriptor nên **không cần thêm `--add-modules` cho ví dụ cơ bản**.

Có thể khám phá module trên JDK đang dùng:

```bash
java --describe-module jdk.nio.mapmode
```

Đầu ra sẽ nêu module và package được export, ví dụ có dòng `exports jdk.nio.mapmode`. Nếu runtime image tự tạo bằng `jlink` **không chứa module này**, chương trình phụ thuộc vào nó có thể không khởi động được. Việc nhìn thấy module **chỉ chứng minh API hiện diện**, chưa chứng minh thiết bị hỗ trợ map mode đồng bộ.

## 3. So sánh `FileChannel.MapMode` tiêu chuẩn và chế độ mở rộng

`FileChannel` thuộc `java.base` đã có các mode tiêu chuẩn:

| Mode | Thuộc API | Ý nghĩa cơ bản |
| --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | Java SE | Ánh xạ chỉ đọc; sửa buffer sẽ gây `ReadOnlyBufferException` |
| `FileChannel.MapMode.READ_WRITE` | Java SE | Ánh xạ đọc/ghi, các thay đổi được lan truyền tới tệp theo ngữ nghĩa mapping |
| `FileChannel.MapMode.PRIVATE` | Java SE | Ánh xạ private/copy-on-write; thay đổi không được ghi trở lại tệp |
| `ExtendedMapMode.READ_ONLY_SYNC` | JDK-specific | Ánh xạ **chỉ đọc** với ngữ nghĩa SYNC cho tệp trên NVM |
| `ExtendedMapMode.READ_WRITE_SYNC` | JDK-specific | Ánh xạ **đọc/ghi** với ngữ nghĩa SYNC cho tệp trên NVM; `force()` dùng cơ chế ghi trả cache line trên triển khai hỗ trợ |

Hai hằng số mở rộng có **kiểu tĩnh là `FileChannel.MapMode`**, nên dùng trực tiếp trong API đã có:

```java
MappedByteBuffer readOnly = channel.map(
        ExtendedMapMode.READ_ONLY_SYNC, 0, length);

MappedByteBuffer readWrite = channel.map(
        ExtendedMapMode.READ_WRITE_SYNC, 0, length);
```

Đây là đoạn **minh họa**, giả định `channel` là `FileChannel` với quyền truy cập và `length` phù hợp, tệp đang nằm trên thiết bị/hệ thống tệp có hỗ trợ persistent-memory mapping. Trên máy thông thường, các lời gọi này **có thể thất bại**, không được coi là ví dụ chạy thành công ở mọi môi trường.

**Điểm mấu chốt:** `ExtendedMapMode` **không tạo phương thức `map` mới**. Nó chỉ bổ sung các giá trị `MapMode` có thể truyền vào `FileChannel.map(FileChannel.MapMode, long, long)`. Giá trị trả về vẫn là `MappedByteBuffer`.

### `READ_ONLY_SYNC` không cho phép ghi

`READ_ONLY_SYNC` chỉ đọc. Một phép `buffer.put(...)` trên vùng chỉ đọc sẽ gây `ReadOnlyBufferException`, tương tự `FileChannel.MapMode.READ_ONLY`. Không chọn `READ_ONLY_SYNC` chỉ vì muốn đọc dữ liệu rồi cập nhật tại chỗ.

### `READ_WRITE_SYNC` khác với `StandardOpenOption.SYNC`

Đây là **hai tầng khác nhau**:

- `ExtendedMapMode.READ_WRITE_SYNC`: **chế độ ánh xạ**, truyền cho `FileChannel.map` để dùng cơ chế NVM/DAX khi được hỗ trợ.
- `StandardOpenOption.SYNC` hoặc `DSYNC`: **tùy chọn mở tệp**, ảnh hưởng cách những phương thức ghi vào channel đồng bộ dữ liệu ra storage.
- `MappedByteBuffer.force()`: yêu cầu ghi các **thay đổi qua buffer mapped** ra vùng lưu trữ tương ứng.

Đừng giả định chỉ mở `FileChannel` bằng `StandardOpenOption.SYNC` là đã có một `READ_WRITE_SYNC` memory mapping. Và đừng thay `buffer.force()` bằng `channel.force(true)` rồi tự cho rằng mọi thay đổi thực hiện qua `MappedByteBuffer.put(...)` đã được bảo đảm flush: tài liệu `FileChannel.force` chỉ cam kết một phạm vi nhất định đối với ghi qua channel.

## 4. Vì sao NVM cần phần cứng, filesystem và OS phù hợp?

**NVM không đồng nghĩa bất kỳ ổ SSD/NVMe nào.** Tên **NVMe** thường chỉ giao thức của thiết bị block storage; còn trường hợp của JEP 352 liên quan tới **persistent memory mà hệ điều hành hỗ trợ ánh xạ trực tiếp** qua cơ chế tương ứng, đặc biệt **DAX (Direct Access)** ở Linux.

Trên Linux, tài liệu `ExtendedMapMode` cho biết việc ánh xạ SYNC dùng các cờ `MAP_SHARED_VALIDATE` và `MAP_SYNC` khi gọi `mmap`. Để thành công cần có sự hỗ trợ phối hợp của:

1. **JVM/implementation:** hỗ trợ những map mode mở rộng này.
2. **OS và kiến trúc:** cung cấp cơ chế ánh xạ và flush cần thiết.
3. **Thiết bị lưu trữ:** có khả năng NVM/persistent memory phù hợp.
4. **Filesystem và cấu hình mount:** có cơ chế DAX/MAP_SYNC tương ứng.
5. **Tệp cụ thể:** nằm trên filesystem hỗ trợ, mở đúng quyền, kích thước và vùng map hợp lệ.

Nếu chỉ thấy `jdk.nio.mapmode` trong `java --list-modules`, bạn **chưa biết** điều kiện 2–5 có đáp ứng không.

### Điều gì xảy ra khi môi trường không hỗ trợ?

Javadoc `ExtendedMapMode` nêu `FileChannel.map(...)` có thể ném **`UnsupportedOperationException`** nếu implementation không hỗ trợ mode đó. Trên một filesystem hoặc thiết bị không hỗ trợ mapping được yêu cầu, lời gọi cũng có thể thất bại qua **`IOException`** do lỗi native mapping.

Điều này không phải lỗi cú pháp Java. Chương trình có thể **biên dịch hoàn toàn đúng** rồi vẫn không ánh xạ SYNC được tại runtime.

Các trường hợp cần xét riêng:

- **Windows/máy không có mapping mode hỗ trợ:** thường bị từ chối.
- **Linux trên filesystem thường không hỗ trợ DAX/MAP_SYNC:** có thể từ chối dù JVM có hằng số `READ_WRITE_SYNC`.
- **Linux với DAX thực sự:** có thể thành công, nhưng vẫn phải kiểm tra I/O, quyền, kích thước vùng map và khả năng flush của hệ thống.
- **Runtime image cắt giảm module:** có thể thất bại **ngay khi phân giải module**, trước khi ứng dụng gọi `map`.

**Không nên viết fallback im lặng và coi nó tương đương NVM.** Nếu sản phẩm **bắt buộc** có NVM để đáp ứng mục tiêu độ bền hay hiệu năng, hãy *fail fast* với chẩn đoán rõ ràng. Nếu NVM chỉ là **tối ưu tùy chọn**, có thể có fallback sang `READ_WRITE` chuẩn với lời giải thích rõ về sự khác biệt ngữ nghĩa và hiệu năng.

## 5. Ví dụ Java 17+ hoàn chỉnh, không yêu cầu máy có NVM

Mẫu sau thực hiện hai việc:

1. **Luôn** ghi/đọc một tệp nhỏ bằng mapping tiêu chuẩn để học `FileChannel.map` và `MappedByteBuffer.force()`.
2. **Thử** dùng `ExtendedMapMode.READ_WRITE_SYNC` trên tệp thử nghiệm. Trên một máy không hỗ trợ, thông báo trạng thái thay vì đòi NVM phải hoạt động. Đường thử là **kiểm tra khả năng**, không thay thế benchmark hoặc xác minh durability của thiết bị thật.

Lưu toàn bộ vào **`NvmMappingDemo.java`**:

```java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class NvmMappingDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("module=" + ExtendedMapMode.class.getModule().getName());
        System.out.println("readOnlyMode=" + ExtendedMapMode.READ_ONLY_SYNC);
        System.out.println("readWriteMode=" + ExtendedMapMode.READ_WRITE_SYNC);

        Path file = Files.createTempFile("jep352-demo-", ".bin");
        try {
            Files.write(file, "ABCD".getBytes(StandardCharsets.US_ASCII));
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                MappedByteBuffer standard = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, 4);
                standard.put(0, (byte) 'N');
                standard.force();
            }

            System.out.println("standardReadBack=" +
                    Files.readString(file, StandardCharsets.US_ASCII));

            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try {
                    MappedByteBuffer sync = channel.map(
                            ExtendedMapMode.READ_WRITE_SYNC, 0, 4);
                    sync.put(1, (byte) 'V');
                    sync.force();
                    System.out.println("syncMapping=SUPPORTED");
                } catch (UnsupportedOperationException e) {
                    System.out.println("syncMapping=UNSUPPORTED");
                } catch (java.io.IOException e) {
                    System.out.println("syncMapping=IO_ERROR");
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**, với module mở rộng được phân giải rõ:

```bash
javac --release 17 --add-modules jdk.nio.mapmode NvmMappingDemo.java
java --add-modules jdk.nio.mapmode NvmMappingDemo
```

**Đầu ra đã kiểm chứng trên OpenJDK 24 / Windows không hỗ trợ SYNC mapping:**

```text
module=jdk.nio.mapmode
readOnlyMode=READ_ONLY_SYNC
readWriteMode=READ_WRITE_SYNC
standardReadBack=NBCD
syncMapping=UNSUPPORTED
```

Giải thích:

1. `module=jdk.nio.mapmode`: lớp `ExtendedMapMode` nằm trong module JDK có tên `jdk.nio.mapmode`.
2. `readOnlyMode` và `readWriteMode`: minh họa **giá trị tên của hai `MapMode`** từ API mở rộng.
3. `standardReadBack=NBCD`: vùng tệp ban đầu chứa `ABCD`, được ánh xạ với `READ_WRITE` chuẩn; `put(0, 'N')` sửa byte đầu, `force()` yêu cầu đồng bộ, đọc lại thành `NBCD`.
4. `syncMapping=UNSUPPORTED`: JVM trên **máy kiểm thử cụ thể** không cho dùng `READ_WRITE_SYNC`. **Đây không phải lỗi thiếu `--add-modules`** vì module và các hằng số đã được phân giải thành công.
5. Chỉ khi ánh xạ SYNC thực sự được hỗ trợ, chương trình mới in `syncMapping=SUPPORTED`; nếu gặp `IOException` ở bước map, in `syncMapping=IO_ERROR`.

**Không suy diễn đầu ra cuối cho mọi máy:** bốn dòng đầu là phần ổn định ở môi trường có API; dòng `syncMapping` **phụ thuộc nền tảng/tệp**. Trên Linux DAX có thể thấy `SUPPORTED`; trên filesystem thiếu điều kiện có thể thấy `IO_ERROR` hoặc `UNSUPPORTED`. Bài này không tuyên bố đã kiểm chứng dòng SYNC thành công trên NVM thật.

**Vì sao ví dụ không tự fallback khi `map` SYNC thất bại?** Vì mục tiêu là **quan sát khả năng hỗ trợ**, không che lỗi bằng mapping thường. Trong hệ thống thật, nếu có fallback, phải phân biệt “mode không được hỗ trợ” với “file hỏng, hết quyền, hết dung lượng hoặc I/O lỗi”; không bắt toàn bộ `IOException` rồi lặng lẽ coi như đã có NVM durability.

**Chú ý tài nguyên:** ví dụ dùng file tạm và xóa trong `finally`. Một mapping `MappedByteBuffer` có thời gian sống gắn với buffer (thường đến lúc GC thu gom), nên **đóng `FileChannel` không đồng nghĩa unmap ngay lập tức**. Trên hệ điều hành/filesystem có quy tắc khóa file nghiêm ngặt, thao tác xóa file vẫn đang map có thể không thành công; không dùng file tạm như mẫu quản lý vòng đời production. Việc tạo/xóa bản test cần quyền tương ứng.

## 6. Ứng dụng JPMS: `requires jdk.nio.mapmode;`

Nếu dự án của bạn có `module-info.java`, lệnh `--add-modules` của chương trình classpath có thể được thay bằng một module descriptor rõ ràng.

### 6.1. Cấu trúc dự án

```text
src/
└── com.example.nvm/
    ├── module-info.java
    └── com/
        └── example/
            └── nvm/
                └── Main.java
```

### 6.2. `src/com.example.nvm/module-info.java`

```java
module com.example.nvm {
    requires jdk.nio.mapmode;
}
```

### 6.3. `src/com.example.nvm/com/example/nvm/Main.java`

```java
package com.example.nvm;

import jdk.nio.mapmode.ExtendedMapMode;

public class Main {
    public static void main(String[] args) {
        System.out.println("module=" + ExtendedMapMode.class.getModule().getName());
        System.out.println("syncMode=" + ExtendedMapMode.READ_WRITE_SYNC);
    }
}
```

### 6.4. Biên dịch và chạy

Đứng ở thư mục cha của `src`:

```bash
javac --release 17 -d out --module-source-path src -m com.example.nvm
java --module-path out --module com.example.nvm/com.example.nvm.Main
```

**Stdout đã kiểm chứng trên OpenJDK 24:**

```text
module=jdk.nio.mapmode
syncMode=READ_WRITE_SYNC
```

Ví dụ modular này chỉ kiểm tra **khai báo dependency + truy cập API**. Nó **không gọi `FileChannel.map(READ_WRITE_SYNC, ...)`**, nên không cần DAX và không kiểm tra hỗ trợ SYNC mapping thực sự. Khi thêm thao tác map vào một ứng dụng JPMS đầy đủ, những điều kiện hỗ trợ hệ thống tệp/phần cứng ở phần 4 vẫn áp dụng.

**Khác biệt cần nhớ:**

- **Classpath:** dùng `javac ... --add-modules jdk.nio.mapmode` và `java --add-modules jdk.nio.mapmode ...` như ví dụ phần 5.
- **JPMS:** khai báo `requires jdk.nio.mapmode;` trong `module-info.java`; build/run bằng `--module-source-path` và `--module-path`.
- **Runtime image tối giản:** khi đóng gói bằng `jlink` hoặc `jpackage`, hãy bảo đảm module `jdk.nio.mapmode` được đưa vào runtime; có mặt tại compile-time không đồng nghĩa được phân phối trong runtime.

## 7. Dùng `READ_WRITE_SYNC` khi thật sự có NVM/DAX

Đoạn sau là **mẫu chuyên biệt cho môi trường có DAX**, không phải chương trình độc lập và **không dự kiến chạy thành công trên Windows/filesystem thường**:

```java
Path file = Path.of("/mnt/dax/records.bin");

// Giả định: file đã có sẵn, dài ít nhất 4096 byte,
// nằm trên filesystem hỗ trợ persistent-memory MAP_SYNC.
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

    MappedByteBuffer buffer = channel.map(
            ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);

    buffer.putLong(0, 42L);
    buffer.force(0, Long.BYTES);
}
```

Trong một lớp thực tế cần `import` các API `Path`, `FileChannel`, `MappedByteBuffer`, `StandardOpenOption` và `ExtendedMapMode`, đồng thời xử lý `IOException` cùng lỗi unsupported. Địa chỉ `/mnt/dax/records.bin` **chỉ minh họa** một mount do người vận hành cấu hình, không phải đường dẫn NVM cố định trên mọi máy Linux.

### Vì sao gọi `force`?

`READ_WRITE_SYNC` thiết lập cách ánh xạ vùng tệp với những bảo đảm của mode SYNC trên nền tảng hỗ trợ. **Nó không có nghĩa rằng mỗi lệnh `buffer.putLong(...)` tự biến thành một transaction bền vững và không cần đồng bộ.**

Theo tài liệu `ExtendedMapMode`, đối với buffer được ánh xạ với `READ_WRITE_SYNC`, thao tác `force` trên triển khai hỗ trợ **sử dụng cache-line writeback** thay vì một file-device flush truyền thống. Vì vậy:

```java
buffer.putLong(0, value);
buffer.force(0, Long.BYTES);
```

là ý tưởng cốt lõi: **ghi dữ liệu, rồi yêu cầu đẩy thay đổi cần thiết tới persistent storage**.

**`MappedByteBuffer.force()` khác `load()`:** `load()` chỉ cố đưa trang nhớ vào RAM/physical memory để truy cập nhanh hơn; **không phải thao tác bảo đảm lưu bền vững**. `isLoaded()` cũng chỉ là gợi ý về trạng thái loaded, không phải phép kiểm tra dữ liệu đã sống sót sau crash.

**`force(int index, int length)`** có thể đồng bộ một vùng cụ thể; `force()` áp dụng toàn bộ capacity. Cơ chế flush được triển khai tự do ghi ra thêm byte lân cận theo granularity của thiết bị.

### Tính bền vững không thay thế thiết kế chống crash

Ngay cả có `MAP_SYNC` và `force`, vẫn phải xét:

- Một update nhiều trường có thể bị crash ở giữa; không mặc nhiên atomic.
- Dữ liệu header, length, checksum và payload cần thứ tự cập nhật hợp lệ nếu có thể gián đoạn.
- Hai tiến trình cùng map một file cần quy tắc đồng bộ/lock và ghi nhận ordering; `force` không tự giải quyết data race.
- File, quyền, filesystem và hardware cần khả năng phục hồi như thiết kế yêu cầu.
- Kiểm tra **khả năng đọc lại** ngay sau `force` không chứng minh chống mất điện; phải có test phục hồi sau restart/crash/power cycle trên môi trường an toàn nếu yêu cầu durability cao.

Một thiết kế nghiêm túc có thể dùng cấu trúc record có phiên bản, checksum, commit marker, double-buffering hoặc log ghi trước, cùng cơ chế recovery. Đừng coi ExtendedMapMode là giải pháp transaction/database miễn phí.

## 8. Thao tác với `READ_ONLY_SYNC`

Mode chỉ đọc phù hợp khi muốn **quan sát vùng tệp trên NVM mà không sửa**:

```java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ)) {
    MappedByteBuffer buffer = channel.map(
            ExtendedMapMode.READ_ONLY_SYNC, 0, size);
    byte first = buffer.get(0);
    System.out.println(first);
}
```

Đoạn này là **mã minh họa**, giả định `file` có dữ liệu và `size` dương, không vượt giới hạn ánh xạ; cùng yêu cầu NVM/DAX như `READ_WRITE_SYNC`. `FileChannel` cần được mở để đọc. Không dùng `buffer.put(...)`, vì buffer chỉ đọc.

Nếu không cần tính năng ánh xạ NVM đặc thù, `FileChannel.MapMode.READ_ONLY` là lựa chọn **Java SE phổ biến và dễ triển khai** hơn, không cần module `jdk.nio.mapmode`.

## 9. Giới hạn và hành vi quan trọng của memory-mapped buffers

### 9.1. Kích thước ánh xạ

Trong Java 17, `FileChannel.map(FileChannel.MapMode,long,long)` trả về `MappedByteBuffer`, có API chỉ số dựa trên `int`. Một buffer ánh xạ đơn lẻ có giới hạn kích thước liên quan `Integer.MAX_VALUE`; nếu xử lý file rất lớn nên **ánh xạ theo vùng (window)** hoặc cân nhắc API hiện đại phù hợp với JDK mục tiêu thay vì mong một `MappedByteBuffer` có thể có capacity lớn tùy ý.

`position`, `size` phải là số không âm và hợp lệ theo API; luôn kiểm tra kích thước tệp, vùng map và quyền truy cập. Tránh ánh xạ ra ngoài vùng hợp lệ rồi tạo lỗi I/O khó chẩn đoán.

### 9.2. Vòng đời mapping

`MappedByteBuffer` là direct byte buffer ánh xạ tới file. Mapping có thể **còn tồn tại sau khi `FileChannel` đã đóng**, cho tới khi buffer được GC thu gom. Java 17 không có một phương thức public chuẩn `unmap()` trên `MappedByteBuffer`.

Do đó:

- Không giữ buffer mapped quá lâu mà không có nhu cầu.
- Không dựa vào `channel.close()` để hứa đã unmap.
- Không xóa/truncate/resize file đang được truy cập bởi mapping mà không có điều phối.
- Kiểm tra chính sách mở file và xóa file trên OS đích, nhất là Windows.
- Không gọi API nội bộ `sun.misc.Unsafe` hoặc `jdk.internal.*` chỉ để cưỡng ép unmap nếu không có đánh giá tương thích/bảo trì rõ ràng.

Nếu bạn đang dùng bản JDK mới hơn với các API quản lý memory mapping có vòng đời tường minh, đó là một lựa chọn kiến trúc **khác**, cần lựa chọn theo version và nhu cầu; bài này giữ ví dụ thống nhất Java 17+.

### 9.3. Đọc/ghi cùng dữ liệu từ nhiều nơi

Mapping có thể phản ánh thay đổi từ file hoặc tiến trình khác theo quy tắc OS, nhưng **thời điểm nhìn thấy thay đổi giữa các tiến trình có thể không được bảo đảm như một biến Java bình thường**. Khi dữ liệu được chia sẻ, thiết kế cần xử lý đồng bộ, lock (nếu phù hợp), checksum và tính nhất quán cấu trúc.

### 9.4. An toàn dữ liệu

Ánh xạ file không tự mã hóa nội dung. Dữ liệu NVM có thể **tồn tại sau khi process kết thúc hoặc hệ thống khởi động lại**, vì vậy phải quản lý quyền file, phân quyền thư mục, chính sách xóa/retention và bảo vệ thông tin nhạy cảm như đối với storage bền vững. Không ghi secret vào file test không bảo vệ rồi cho rằng nó “chỉ ở memory”.

## 10. Lỗi thường gặp và cách xử lý

| Sai lầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `requires jdk.nio.mapmode.ExtendedMapMode;` | Nhầm tên lớp với module | Dùng `requires jdk.nio.mapmode;` |
| Trong classpath quên phân giải module JDK này | Compiler/runtime không thấy package/class | Thêm `--add-modules jdk.nio.mapmode` khi compile và chạy |
| Tưởng `ExtendedMapMode` là một `FileChannel` mới | API chỉ định nghĩa các mode mở rộng | Dùng `FileChannel.map(ExtendedMapMode.READ_WRITE_SYNC, ...)` |
| Tưởng có API nghĩa là mọi máy hỗ trợ SYNC mapping | Thiếu OS, DAX, NVM hoặc filesystem | Kiểm tra `map` thực tế trên môi trường đích |
| Gọi `READ_WRITE_SYNC` trên Windows hoặc disk thường | Nền tảng/map mode có thể không hỗ trợ | Xử lý `UnsupportedOperationException`, chẩn đoán `IOException` |
| Nhầm SSD NVMe với persistent memory DAX | Hai công nghệ có đặc điểm truy cập khác nhau | Xác nhận phần cứng, filesystem và kernel |
| Coi `READ_WRITE_SYNC` tự sync từng byte khi gọi `put` | Thiếu thao tác/policy flush | Dùng `MappedByteBuffer.force()` theo hợp đồng durability |
| Chỉ gọi `FileChannel.force()` sau `buffer.put(...)` | Không phải bảo đảm thay thế flush buffer mapped | Gọi `buffer.force()` |
| Coi `buffer.load()` là durability check | `load` chỉ đề nghị nạp trang vào memory | Dùng `force` và kiểm thử phục hồi thực |
| Dùng `READ_ONLY_SYNC` rồi `put` | Mapping chỉ đọc | Chọn `READ_WRITE_SYNC` khi thật sự cần ghi |
| Bắt mọi `IOException` và im lặng fallback | Có thể che file hỏng, hết quyền, lỗi đĩa | Phân biệt unsupported với lỗi I/O thực và ghi log hợp lý |
| Cho rằng `close()` của channel unmap ngay | Mapping có vòng đời riêng | Quản lý buffer và tránh xóa/thu nhỏ file sớm |
| Map tệp rất lớn bằng một `MappedByteBuffer` | Giới hạn chỉ số `int` | Ánh xạ theo vùng hoặc chọn API tương ứng |
| Thiết kế ghi nhiều field không có commit/recovery | Crash giữa update có thể làm hỏng record | Dùng checksum, log, commit marker và recovery |
| `jlink` runtime image thiếu `jdk.nio.mapmode` | Module không được phân giải khi chạy | Thêm module vào image hoặc dùng runtime đầy đủ |
| Đánh đồng `READ_WRITE_SYNC` với database transaction | `force` không bảo đảm atomic update logic | Thiết kế transactional protocol riêng khi cần |

## 11. Bài tập có đáp án

**Câu 1.** Tên module chứa `ExtendedMapMode` là gì?  
**Đáp án:** `jdk.nio.mapmode`. Lớp có tên đầy đủ `jdk.nio.mapmode.ExtendedMapMode`.

**Câu 2.** Trong `module-info.java`, directive chính xác là gì?  
**Đáp án:** `requires jdk.nio.mapmode;`.

**Câu 3.** Trong một ứng dụng classpath chưa có `module-info.java`, lệnh nào giúp phân giải module?  
**Đáp án:** `--add-modules jdk.nio.mapmode` ở lệnh `javac`/`java` nếu cần, như chương trình đã thử nghiệm.

**Câu 4.** Hai hằng số trong `ExtendedMapMode` tên gì và thuộc kiểu nào?  
**Đáp án:** `READ_ONLY_SYNC` và `READ_WRITE_SYNC`, đều có kiểu `FileChannel.MapMode`.

**Câu 5.** Có thể viết `channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096)` trên máy có ổ SSD NVMe thông thường và mặc nhiên thành công không?  
**Đáp án:** Không. Phải có hỗ trợ mapping NVM/DAX của JVM, OS, filesystem và thiết bị. NVMe SSD thông thường không đồng nghĩa NVM DAX.

**Câu 6.** `READ_WRITE_SYNC` có tự biến mỗi `putLong` thành một giao dịch dữ liệu bền vững, atomic không?  
**Đáp án:** Không. `MappedByteBuffer.force()` liên quan tới flush; atomicity/consistency của record nhiều byte cần thiết kế riêng.

**Câu 7.** Vì sao dùng `buffer.force()` thay vì chỉ `channel.force(true)` sau khi viết qua `MappedByteBuffer`?  
**Đáp án:** `FileChannel.force` không luôn bảo đảm flush các thay đổi qua buffer mapped; `MappedByteBuffer.force` dành cho thay đổi trên buffer.

**Câu 8.** Máy không có NVM nhưng muốn dùng file mapping tiêu chuẩn thì chọn gì?  
**Đáp án:** `FileChannel.MapMode.READ_WRITE` hoặc `READ_ONLY`, không cần `jdk.nio.mapmode`.

**Câu 9.** Đóng `FileChannel` có chắc unmap buffer ngay không?  
**Đáp án:** Không. Buffer mapped có thể sống tiếp tới khi GC giải phóng mapping.

**Câu 10.** Có cần `--enable-preview` cho `ExtendedMapMode` ở Java 17+ không?  
**Đáp án:** Không. Đây là API JDK-specific có từ Java 14, được tài liệu hóa trong JDK hiện hành, không phải cú pháp preview.

**Câu 11.** Cách nào chứng minh dữ liệu bền vững sau sự cố điện tốt hơn việc đọc lại ngay trong cùng process?  
**Đáp án:** Thử nghiệm phục hồi có kiểm soát sau restart/crash/power interruption trên môi trường và thiết bị phù hợp, kiểm tra cấu trúc và checksum; không thử ngắt điện tùy tiện trên hệ thống đang dùng.

## 12. Tổng kết và nguồn chính thức

**Một câu dễ nhớ:** `jdk.nio.mapmode` là **module**, `ExtendedMapMode` là **lớp cung cấp hai `FileChannel.MapMode` SYNC**, còn `FileChannel.map(...)` là **điểm thực hiện ánh xạ**.

Để áp dụng đúng:
1. Khai báo/phân giải module `jdk.nio.mapmode`.
2. Chọn `READ_ONLY_SYNC` hay `READ_WRITE_SYNC` theo quyền đọc/ghi.
3. Xác minh môi trường **thực sự hỗ trợ NVM/DAX/MAP_SYNC**.
4. Với ghi dữ liệu qua mapping, dùng `MappedByteBuffer.force()` và thiết kế crash-recovery phù hợp.
5. Nếu không có NVM, dùng map mode tiêu chuẩn hoặc báo lỗi theo yêu cầu sản phẩm, **không tự gắn nhãn khả năng SYNC cho fallback**.

**Tài liệu chính thức vẫn còn hiệu lực:**

- [Oracle Java SE 25 — module `jdk.nio.mapmode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/module-summary.html): tên module, package và tính chất JDK-specific.
- [Oracle Java SE 25 — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_ONLY_SYNC`, `READ_WRITE_SYNC`, lỗi unsupported và ghi chú `MAP_SYNC`/cache-line writeback.
- [Oracle Java SE 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `map`, `force`, quyền truy cập và kiểu `MapMode`.
- [Oracle Java SE 17 — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `force(index,length)`, `load()`, vòng đời mapping và tính nhất quán.
- [Oracle Java SE 17 — module `jdk.nio.mapmode`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.nio.mapmode/module-summary.html): module có từ Java 14 và vẫn được xuất trong Java 17.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): lý do thêm hai map mode SYNC trong Java 14.
