# Tìm symbol trong thư viện nạp theo đường dẫn, thư viện của class loader và thư viện nền tảng

Để gọi một hàm native bằng Foreign Function & Memory API (FFM API), Java cần biết địa chỉ của hàm đó trong tiến trình. Tên hàm được export từ thư viện native được gọi là **symbol**. `SymbolLookup` cung cấp cách tìm symbol từ các nguồn khác nhau: thư viện được nạp trực tiếp từ đường dẫn hoặc tên, thư viện đã được nạp bởi class loader, và các thư viện nền tảng mà hệ điều hành cung cấp cho tiến trình.

FFM API trở thành API chính thức từ Java 22 và hiện nằm trong package `java.lang.foreign` của module `java.base`. Các ví dụ trong bài sử dụng `SymbolLookup`, `Linker`, `MemorySegment` và `MethodHandle` của API chuẩn hiện hành. Không cần dùng các lớp incubator hoặc preview cũ.

## 1. Symbol và `SymbolLookup` là gì?

Một hàm native được export từ thư viện có thể được tìm bằng tên symbol. Ví dụ, thư viện C có thể cung cấp hàm:

```c
int add(int left, int right) {
    return left + right;
}
```

Khi thư viện được nạp vào tiến trình, dynamic loader của hệ điều hành quản lý các symbol mà thư viện export. Java cần tìm địa chỉ symbol `add` trước khi tạo lời gọi native.

`SymbolLookup` là interface trong `java.lang.foreign` dùng để tìm symbol theo tên:

```java
Optional<MemorySegment> address = lookup.find("add");
```

Phương thức `find(String name)` trả về `Optional<MemorySegment>`:

- Có giá trị nếu lookup tìm thấy symbol.
- Rỗng nếu symbol không tồn tại trong nguồn lookup đó.

`MemorySegment` trả về đại diện cho địa chỉ symbol. Khi symbol là hàm native, segment này được truyền cho `Linker.downcallHandle(...)` để tạo `MethodHandle`. Bản thân `SymbolLookup` chỉ tìm địa chỉ; nó không mô tả chữ ký hàm. Chữ ký vẫn phải được mô tả chính xác bằng `FunctionDescriptor`.

Ba nguồn lookup chính được dùng trong bài:

| Nguồn symbol | API | Vai trò |
| --- | --- | --- |
| Thư viện nạp theo đường dẫn hoặc tên | `SymbolLookup.libraryLookup(...)` | Nạp một thư viện native và tìm symbol trong thư viện đó. |
| Thư viện đã nạp bởi class loader | `SymbolLookup.loaderLookup()` | Tìm symbol trong các thư viện native được nạp bởi class loader của nơi gọi lookup. |
| Thư viện nền tảng | `Linker.defaultLookup()` | Tìm symbol trong tập thư viện nền tảng mà hệ điều hành cung cấp sẵn cho tiến trình. |

## 2. Tìm symbol trong thư viện nạp theo đường dẫn

### 2.1. Dùng `SymbolLookup.libraryLookup(Path, Arena)`

Khi biết chính xác vị trí file thư viện native, dùng overload nhận `Path`:

```java
SymbolLookup lookup = SymbolLookup.libraryLookup(
    Path.of("/opt/myapp/native/libmathops.so"),
    arena
);
```

Đường dẫn phải trỏ đến file thư viện native phù hợp với hệ điều hành và kiến trúc đang chạy. Với API này, nên truyền đường dẫn tuyệt đối để xác định rõ file cần nạp. Phần mở rộng file thay đổi theo nền tảng, ví dụ `.so` trên Linux, `.dylib` trên macOS và `.dll` trên Windows.

Thư viện được nạp thông qua dynamic loader của hệ điều hành. `Arena` truyền vào quản lý vòng đời của lookup và thư viện được nạp. Khi arena đóng, các segment đại diện cho symbol từ lookup đó hết hiệu lực và tài nguyên thư viện được giải phóng theo cơ chế của FFM API. Vì vậy, mọi lời gọi dùng hàm trong thư viện phải hoàn tất trước khi đóng arena.

### 2.2. Ví dụ tìm và gọi hàm `add`

Giả sử thư viện native đã export hàm C `add(int, int)` và file thư viện có đường dẫn phù hợp với nền tảng. Chương trình Java có thể tìm symbol và tạo downcall như sau:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class PathLookupExample {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                Path.of("/opt/myapp/native/libmathops.so"),
                arena
            );

            MemorySegment addAddress = lookup.find("add")
                .orElseThrow(() -> new IllegalArgumentException(
                    "Không tìm thấy symbol add trong libmathops"
                ));

            MemoryLayout cInt = linker.canonicalLayouts().get("int");
            MethodHandle add = linker.downcallHandle(
                addAddress,
                FunctionDescriptor.of(
                    cInt,
                    cInt,
                    cInt
                )
            );

            int result = (int) add.invokeExact(10, 20);
            System.out.println(result); // 30
        }
    }
}
```

`FunctionDescriptor.of(...)` mô tả hàm trả về `int` và nhận hai tham số `int`. Descriptor phải khớp chữ ký thật của hàm native. `invokeExact` gọi hàm theo đúng kiểu đã mô tả; ví dụ khai báo `throws Throwable` để xử lý các lỗi mà `MethodHandle` có thể ném.

Ví dụ lấy layout của kiểu C `int` từ `linker.canonicalLayouts()` để dùng kích thước và alignment theo ABI hiện tại. Cách này giúp mô tả kiểu C native trực tiếp thay vì mặc định mọi kiểu C đều tương đương layout Java trên tất cả nền tảng.

Đường dẫn trong ví dụ là đường dẫn Linux minh họa. Khi chạy trên Windows hoặc macOS, hãy thay bằng đường dẫn tuyệt đối tới file thư viện tương ứng. Thư viện cũng phải được biên dịch cho đúng kiến trúc và ABI của JVM.

### 2.3. Dùng tên thư viện thay cho đường dẫn

Nếu muốn dynamic loader tìm thư viện theo tên và cấu hình tìm kiếm của nền tảng, có thể dùng overload nhận `String`:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup = SymbolLookup.libraryLookup("mathops", arena);

    MemorySegment addAddress = lookup.find("add")
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy add"));

    // Dùng addAddress để tạo downcall handle như ví dụ trước.
}
```

Tên thư viện được ánh xạ theo quy ước đặt tên của nền tảng và được nạp thông qua cơ chế tìm thư viện của hệ thống. Chẳng hạn, tên logic `mathops` thường tương ứng với `libmathops.so` trên Linux hoặc `mathops.dll` trên Windows. Vị trí thư viện phải nằm trong đường dẫn tìm kiếm mà dynamic loader của nền tảng sử dụng.

Chọn overload `Path` khi ứng dụng cần chỉ rõ file cần nạp. Chọn overload `String` khi thư viện được triển khai theo cơ chế tìm kiếm thư viện chuẩn của môi trường chạy.

## 3. Tìm symbol trong thư viện đã nạp bởi class loader

### 3.1. `SymbolLookup.loaderLookup()`

Một ứng dụng có thể đã nạp thư viện native bằng `System.load(...)` hoặc `System.loadLibrary(...)`, ví dụ để tích hợp với JNI hoặc một thành phần khác trong ứng dụng. Nếu thư viện được nạp bởi class loader của lớp đang gọi lookup, FFM API có thể tìm symbol trong thư viện đó bằng:

```java
SymbolLookup lookup = SymbolLookup.loaderLookup();
```

`loaderLookup()` không nạp thêm file thư viện. Nó cung cấp lookup đối với các thư viện native đã được nạp bởi class loader của caller. Do đó, lookup này hữu ích khi ứng dụng muốn sử dụng symbol từ thư viện đã có sẵn trong môi trường chạy.

### 3.2. Ví dụ dùng thư viện đã nạp bằng `System.load`

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;

public class LoaderLookupExample {
    public static void main(String[] args) throws Throwable {
        // System.load yêu cầu đường dẫn tuyệt đối.
        System.load("/opt/myapp/native/libmathops.so");

        // Tìm symbol trong thư viện đã được class loader của lớp này nạp.
        SymbolLookup lookup = SymbolLookup.loaderLookup();
        MemorySegment addAddress = lookup.find("add")
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy add"));

        Linker linker = Linker.nativeLinker();
        MemoryLayout cInt = linker.canonicalLayouts().get("int");
        MethodHandle add = linker.downcallHandle(
            addAddress,
            FunctionDescriptor.of(
                cInt,
                cInt,
                cInt
            )
        );

        int result = (int) add.invokeExact(3, 4);
        System.out.println(result); // 7
    }
}
```

Có thể dùng `System.loadLibrary("mathops")` khi thư viện được cài đặt trong đường dẫn tìm kiếm thư viện của môi trường chạy. Cả `System.load` và `System.loadLibrary` vẫn là API Java hiện hành để nạp thư viện native; `loaderLookup()` cho phép FFM tìm symbol trong các thư viện đã được nạp theo class loader.

### 3.3. Phạm vi của class loader

Lookup này phụ thuộc class loader đã nạp thư viện:

- Thư viện được nạp bởi class loader của caller có thể được tìm qua `loaderLookup()` từ caller đó.
- Thư viện được nạp bởi một class loader khác không tự động trở thành thư viện của class loader hiện tại.
- Lookup không thay thế thao tác nạp thư viện. Nếu thư viện chưa được nạp, cần nạp nó bằng cơ chế phù hợp trước.

Vòng đời của thư viện được nạp bằng `System.load` hoặc `System.loadLibrary` gắn với cơ chế quản lý native library của class loader. Khi thiết kế ứng dụng nhiều class loader hoặc plugin, cần xác định class loader nào sở hữu thư viện và class loader nào thực hiện lookup.

## 4. Tìm symbol trong thư viện nền tảng

### 4.1. `Linker.defaultLookup()`

Một số symbol thuộc thư viện nền tảng được hệ điều hành nạp hoặc cung cấp sẵn cho tiến trình. FFM API cung cấp lookup mặc định của linker thông qua `Linker.defaultLookup()`:

```java
Linker linker = Linker.nativeLinker();
SymbolLookup platformLookup = linker.defaultLookup();
```

Lookup này tìm symbol trong tập thư viện nền tảng mà linker xác định cho hệ điều hành hiện tại. Ví dụ, trên nhiều nền tảng, hàm C tiêu chuẩn như `strlen` có thể được tìm qua lookup mặc định.

`defaultLookup()` không nhận `Arena` vì ứng dụng không trực tiếp nạp một file thư viện mới qua lookup này. Các symbol có sẵn theo môi trường native của tiến trình. Tập symbol cụ thể phụ thuộc hệ điều hành, kiến trúc và linker; không nên giả định mọi hàm của mọi thư viện hệ thống đều có thể tìm thấy.

### 4.2. Ví dụ tìm `strlen`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class PlatformLookupExample {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        SymbolLookup platformLookup = linker.defaultLookup();

        MemorySegment strlenAddress = platformLookup.find("strlen")
            .orElseThrow(() -> new IllegalArgumentException(
                "Nền tảng hiện tại không cung cấp symbol strlen qua defaultLookup"
            ));

        MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
        MethodHandle strlen = linker.downcallHandle(
            strlenAddress,
            FunctionDescriptor.of(sizeT, ValueLayout.ADDRESS)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment text = arena.allocateFrom("Java FFM");
            long length = (long) strlen.invoke(text);
            System.out.println(length); // 8 byte ASCII
        }
    }
}
```

`strlen` nhận địa chỉ chuỗi C kết thúc bằng byte `\0` và trả về `size_t`. Ví dụ lấy layout `size_t` từ `Linker.canonicalLayouts()` để phù hợp với ABI hiện tại, thay vì giả định kiểu này luôn có cùng kích thước trên mọi nền tảng. `Arena` chỉ quản lý chuỗi native được cấp phát; symbol `strlen` được tìm từ lookup nền tảng.

## 5. So sánh và chọn nguồn lookup

| Tình huống | API nên dùng | Vòng đời và lưu ý |
| --- | --- | --- |
| Ứng dụng biết chính xác file thư viện cần nạp | `SymbolLookup.libraryLookup(Path, arena)` | Lookup và thư viện gắn với arena; đóng arena sau khi mọi lời gọi hoàn tất. |
| Thư viện nằm trong đường dẫn tìm kiếm chuẩn của hệ thống | `SymbolLookup.libraryLookup(String, arena)` | Tên được ánh xạ theo quy ước nền tảng; kết quả phụ thuộc cấu hình dynamic loader. |
| Thư viện đã được nạp bằng `System.load` hoặc `System.loadLibrary` bởi class loader hiện tại | `SymbolLookup.loaderLookup()` | Không nạp lại thư viện; phạm vi lookup phụ thuộc class loader của caller. |
| Hàm có sẵn trong thư viện nền tảng của tiến trình | `Linker.defaultLookup()` | Không nạp thư viện tùy chỉnh; symbol phụ thuộc nền tảng. |

Nên chọn nguồn lookup theo nơi sở hữu thư viện. Khi ứng dụng trực tiếp quản lý một thư viện native, `libraryLookup` cùng `Arena` giúp vòng đời thư viện gắn với phạm vi công việc. Khi thư viện đã được một class loader nạp, `loaderLookup` cho phép tái sử dụng. Với symbol nền tảng, dùng `defaultLookup` và kiểm tra symbol có thực sự tồn tại trên nền tảng đích.

## 6. Xử lý trường hợp không tìm thấy symbol

`find` trả về `Optional<MemorySegment>`, do đó cần xử lý trường hợp symbol không tồn tại. Có thể dùng `orElseThrow` để dừng sớm với thông báo rõ ràng:

```java
MemorySegment address = lookup.find("calculate")
    .orElseThrow(() -> new IllegalStateException(
        "Thư viện không export symbol calculate"
    ));
```

Nếu symbol không tìm thấy, hãy kiểm tra lần lượt:

1. Thư viện đúng file, đúng phiên bản và đúng kiến trúc chưa.
2. Thư viện đã được nạp thành công và còn trong vòng đời hợp lệ chưa.
3. Tên symbol có chính xác, bao gồm chữ hoa/chữ thường và quy tắc export của compiler không.
4. Symbol có được export ra dynamic symbol table hay bị ẩn bởi cấu hình visibility không.
5. Lookup có đang dùng đúng nguồn không: `libraryLookup`, `loaderLookup` hay `defaultLookup`.

Với thư viện C++, tên hàm có thể bị compiler biến đổi theo quy tắc name mangling. Nếu muốn tìm bằng tên đơn giản như `add`, hãy cung cấp hàm wrapper có C linkage, chẳng hạn khai báo `extern "C"` trong mã C++ và cấu hình export phù hợp trên nền tảng.

## 7. Native access và vòng đời symbol

Các thao tác nạp thư viện native và gọi hàm native thuộc vùng quyền truy cập native của JVM. Những phương thức restricted của FFM cần native access được cấp rõ ràng. Với ứng dụng trên classpath, có thể khởi chạy:

```bash
java --enable-native-access=ALL-UNNAMED -cp out PathLookupExample
```

Với ứng dụng dạng module, chỉ bật quyền cho module thực sự cần sử dụng native access:

```bash
java --enable-native-access=com.example.app -m com.example.app/com.example.PathLookupExample
```

Từ JDK 24, JVM cảnh báo khi ứng dụng sử dụng native access mà không được bật tường minh theo mặc định hiện hành. Ứng dụng nên cấu hình rõ module cần quyền này để hành vi ổn định qua các phiên bản JDK.

Đặc biệt chú ý vòng đời của symbol và thư viện:

- Với `libraryLookup`, giữ arena mở trong toàn bộ thời gian dùng symbol và downcall handle được tạo từ thư viện đó. Không tiếp tục gọi handle sau khi arena đóng và thư viện hết vòng đời.
- Với `loaderLookup`, bảo đảm class loader sở hữu thư viện còn sống và thư viện chưa bị giải phóng theo vòng đời class loader.
- Với `defaultLookup`, symbol thuộc tập thư viện nền tảng của tiến trình; vẫn phải xác minh symbol có trên hệ điều hành đích.
- Không giữ địa chỉ native hoặc method handle rồi sử dụng sau khi thư viện chứa hàm đã hết vòng đời.

Ngoài ra, tìm thấy symbol không có nghĩa là Java đã biết chữ ký thật của hàm. `FunctionDescriptor` sai kiểu trả về, thứ tự tham số, kích thước con trỏ hoặc quy tắc ABI có thể dẫn đến dữ liệu sai, hỏng bộ nhớ hoặc làm JVM dừng bất thường. Hãy đối chiếu header native và tài liệu thư viện trước khi tạo downcall handle.

## 8. Ghi nhớ

`SymbolLookup` tìm địa chỉ symbol từ một nguồn cụ thể. Dùng `libraryLookup(Path, Arena)` khi cần nạp file thư viện theo đường dẫn, `libraryLookup(String, Arena)` khi muốn nạp theo tên qua cơ chế tìm kiếm của hệ thống, `loaderLookup()` khi thư viện đã được class loader của caller nạp, và `Linker.defaultLookup()` khi tìm symbol từ các thư viện nền tảng của tiến trình.

`find()` trả về `Optional<MemorySegment>`, vì vậy luôn xử lý trường hợp symbol không tồn tại. Sau khi tìm được địa chỉ, dùng `FunctionDescriptor` và `Linker.downcallHandle(...)` để mô tả và tạo lời gọi native. Luôn giữ thư viện, symbol và handle trong vòng đời hợp lệ; xác nhận ABI và native access trước khi chạy.

## Tài liệu tham khảo

- [SymbolLookup — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Linker — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Linker.html)
- [FunctionDescriptor — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
