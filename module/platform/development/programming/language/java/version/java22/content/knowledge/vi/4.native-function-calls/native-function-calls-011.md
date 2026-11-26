# Thu thập trạng thái lời gọi như `errno` và diễn giải quy ước báo lỗi của thư viện

Khi gọi hàm native từ Java, kết quả trả về thường chưa đủ để giải thích vì sao thao tác thất bại. Một hàm C có thể trả về `NULL`, `-1`, `EOF` hoặc `NaN`, rồi ghi thêm mã lỗi vào trạng thái thread-local như `errno`. API Win32 có thể dùng `GetLastError`, Winsock dùng `WSAGetLastError`, còn một thư viện khác có thể trả mã lỗi trực tiếp hoặc duy trì hàng đợi lỗi riêng.

Foreign Function & Memory API (FFM API) cung cấp `Linker.Option.captureCallState(...)` để chụp các phần trạng thái native ngay sau một downcall. Tính năng này có từ Java 22, khi FFM API được chuẩn hóa theo JEP 454. API hiện nằm trong `java.lang.foreign` thuộc module `java.base`; mã Java 22 dùng API này không cần `--enable-preview` hay module incubator cũ. Các tài liệu Java SE 27 vẫn có FFM API và `captureCallState`.

Sau bài học, bạn có thể:

- Nhận biết thư viện native đang dùng quy ước báo lỗi nào.
- Cấu hình downcall để chụp `errno` hoặc trạng thái lỗi được nền tảng hỗ trợ.
- Đọc trường lỗi từ capture-state segment bằng `StructLayout` và `VarHandle`.
- Diễn giải mã lỗi đúng thời điểm và theo hợp đồng của hàm native.
- Tránh các lỗi phổ biến như đọc `errno` sau một lời gọi khác hoặc coi mọi giá trị `errno` khác 0 là lỗi.

## 1. Kết quả trả về và trạng thái lỗi là hai phần khác nhau

FFM API không tự biến mã lỗi native thành Java exception. Một downcall trả về giá trị theo chữ ký C đã mô tả trong `FunctionDescriptor`. Ứng dụng phải đọc kết quả và áp dụng quy ước lỗi mà tài liệu của hàm quy định.

Các kiểu quy ước thường gặp:

| Quy ước | Ví dụ | Cách diễn giải |
|---|---|---|
| Giá trị đặc biệt kèm `errno` | `fopen` trả `NULL` khi mở file thất bại và đặt `errno` | Kiểm tra giá trị trả về trước; nếu thất bại, đọc `errno` đã chụp. |
| Mã lỗi nằm ngay trong giá trị trả về | Một số API trả `0` khi thành công và mã lỗi khác `0` khi thất bại | Diễn giải mã trả về theo tài liệu; không tự động đọc `errno`. |
| Giá trị đặc biệt kèm trạng thái riêng của hệ điều hành | Một số hàm Win32 báo lỗi qua `GetLastError`; Winsock dùng `WSAGetLastError` | Kiểm tra sentinel trước, rồi đọc đúng trường trạng thái tương ứng. |
| Hàng đợi hoặc đối tượng lỗi riêng | Một số thư viện duy trì error queue hoặc error object | Gọi API truy vấn lỗi riêng của thư viện theo đúng thứ tự được tài liệu chỉ dẫn. |
| Tham số đầu ra | Hàm trả status và ghi chi tiết vào con trỏ đầu ra | Đọc status trước, rồi đọc tham số đầu ra nếu hợp đồng cho phép. |

Không phải mọi hàm native đều dùng `errno`. Ví dụ, nhiều hàm POSIX thuộc nhóm pthread trả trực tiếp mã lỗi thay vì đặt `errno`. Nếu kiểm tra `errno` sau những hàm đó, chương trình có thể đọc một giá trị cũ và hiểu nhầm rằng lời gọi vừa rồi thất bại.

## 2. `errno` là gì và vì sao cần chụp ngay sau downcall?

`errno` là macro của C standard library, biểu diễn trạng thái lỗi gắn với thread hiện tại. Hàm native có thể đặt giá trị này khi gặp lỗi. Mã số thường được định nghĩa bằng các hằng như `ENOENT`, `EACCES`, `EINVAL`, `ENOMEM` hoặc `ERANGE` trong header của nền tảng.

Giá trị số của các hằng lỗi có thể khác giữa hệ điều hành và C runtime. Ví dụ, `ENOENT` thường có giá trị `2` trên nhiều môi trường Unix-like, nhưng không nên viết logic nghiệp vụ dựa trên con số `2`. Hãy dùng hằng được sinh từ header phù hợp với nền tảng hoặc thông tin mà thư viện cung cấp.

`errno` không phải một kết quả trả về độc lập. Theo quy ước C, trước tiên phải kiểm tra hàm có báo thất bại bằng sentinel hay không. Khi hàm thành công, `errno` có thể vẫn giữ mã lỗi của một lời gọi trước đó; không phải mọi hàm đều đặt nó về `0` khi thành công. Vì vậy, không viết logic kiểu `if (errno != 0) { ... }` nếu tài liệu của hàm không quy định cách dùng như vậy.

Ngay cả khi đã biết hàm thất bại, hãy đọc trạng thái lỗi ngay sau lời gọi native. Một downcall khác hoặc một thao tác runtime có thể làm thay đổi trạng thái thread-local. `Linker.Option.captureCallState("errno")` yêu cầu linker sao chép `errno` ngay sau khi hàm native kết thúc vào một `MemorySegment` do ứng dụng cung cấp. Java có thể đọc bản sao này sau đó mà không phụ thuộc vào giá trị `errno` hiện tại của thread.

## 3. Dùng `captureCallState("errno")` trong Java 22

Ba thành phần cần thiết là:

1. `Linker.Option.captureCallState("errno")` yêu cầu chụp trường trạng thái có tên `errno` khi tạo downcall handle.
2. `Linker.Option.captureStateLayout()` trả về `StructLayout` mô tả capture-state segment. Layout phụ thuộc nền tảng và có trường được đặt tên cho trạng thái có thể chụp.
3. `VarHandle` được tạo từ layout để đọc trường `errno` sau khi gọi native function.

Khi một downcall handle được liên kết với tùy chọn này, chữ ký lời gọi được bổ sung một tham số `MemorySegment` để nhận trạng thái. Nếu symbol đã được gắn vào handle khi tạo bằng `downcallHandle(symbol, descriptor, options...)`, tham số capture-state đứng trước các tham số của hàm native. Segment phải có kích thước và alignment tương thích với `captureStateLayout()`; `Arena.allocate(layout)` đáp ứng yêu cầu đó.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

Linker.Option captureErrno = Linker.Option.captureCallState("errno");
StructLayout stateLayout = Linker.Option.captureStateLayout();
VarHandle errnoHandle = stateLayout.varHandle(groupElement("errno"));

try (Arena arena = Arena.ofConfined()) {
    MemorySegment state = arena.allocate(stateLayout);

    // Truyền state vào downcall handle đã được liên kết với captureErrno.
    // Sau lời gọi, đọc errno từ bản sao trong state.
    int errno = (int) errnoHandle.get(state, 0L);
}
```

`0L` là base offset của `VarHandle` được tạo từ memory layout. Không tự tính offset của trường `errno` bằng cách giả định nó luôn nằm ở byte đầu tiên; layout có thể chứa các trường khác hoặc padding tùy nền tảng.

Nếu tên trạng thái không được hỗ trợ trên hệ điều hành hiện tại, `captureCallState(...)` ném `IllegalArgumentException`. Có thể liệt kê tên các trường capture-state mà linker công bố:

```java
var supportedNames = Linker.Option.captureStateLayout()
        .memberLayouts()
        .stream()
        .map(MemoryLayout::name)
        .flatMap(java.util.Optional::stream)
        .toList();

System.out.println(supportedNames);
```

Trên Windows, layout có thể chứa các trường `GetLastError`, `WSAGetLastError` và `errno`. Không giả định mọi hệ điều hành đều hỗ trợ cùng một tập trường hoặc cùng một quy ước báo lỗi.

## 4. Ví dụ thực tế: mở file bằng `fopen`

Hàm C `fopen(const char *filename, const char *mode)` trả về con trỏ `FILE*` khi mở file thành công. Nếu thất bại, hàm trả về con trỏ null và đặt `errno`. Hàm `strerror(int)` chuyển mã `errno` thành chuỗi mô tả cho con người đọc.

Ví dụ dưới đây gọi `fopen`, chụp `errno` ngay trong downcall và chỉ đọc mã lỗi khi con trỏ trả về là null. Nếu mở thành công, chương trình đóng file bằng `fclose`.

```java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.ValueLayout.*;

public class NativeOpenCheck {
    private static final Linker LINKER = Linker.nativeLinker();
    private static final SymbolLookup C_LIBRARY = LINKER.defaultLookup();

    private static final Linker.Option CAPTURE_ERRNO =
            Linker.Option.captureCallState("errno");
    private static final StructLayout STATE_LAYOUT =
            Linker.Option.captureStateLayout();
    private static final VarHandle ERRNO =
            STATE_LAYOUT.varHandle(groupElement("errno"));

    // FILE *fopen(const char *filename, const char *mode)
    private static final MethodHandle FOPEN = LINKER.downcallHandle(
            C_LIBRARY.find("fopen").orElseThrow(),
            FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS),
            CAPTURE_ERRNO);

    // char *strerror(int errnum)
    private static final MethodHandle STRERROR = LINKER.downcallHandle(
            C_LIBRARY.find("strerror").orElseThrow(),
            FunctionDescriptor.of(ADDRESS, JAVA_INT));

    // int fclose(FILE *stream)
    private static final MethodHandle FCLOSE = LINKER.downcallHandle(
            C_LIBRARY.find("fclose").orElseThrow(),
            FunctionDescriptor.of(JAVA_INT, ADDRESS),
            CAPTURE_ERRNO);

    private static void printErrno(MemorySegment state, String function)
            throws Throwable {
        int code = (int) ERRNO.get(state, 0L);
        MemorySegment messagePointer = (MemorySegment) STRERROR.invokeExact(code);
        String message = messagePointer
                .reinterpret(Long.MAX_VALUE)
                .getString(0);

        System.err.printf("%s failed: errno=%d (%s)%n", function, code, message);
    }

    static void inspectFile(String fileName) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment state = arena.allocate(STATE_LAYOUT);
            MemorySegment path = arena.allocateFrom(fileName);
            MemorySegment mode = arena.allocateFrom("r");

            // JDK 27+: captureCallState initializes the captured state before
            // the downcall as well as saving it afterwards. On JDK 22 this
            // initializes only the Java-side buffer; the post-call capture
            // still works as shown in the Java 22 API.
            ERRNO.set(state, 0L, 0);
            MemorySegment file = (MemorySegment) FOPEN.invokeExact(state, path, mode);

            if (file.address() == 0L) {
                printErrno(state, "fopen");
                return;
            }

            ERRNO.set(state, 0L, 0);
            int closeResult = (int) FCLOSE.invokeExact(state, file);
            if (closeResult == -1) { // EOF in the C standard library
                printErrno(state, "fclose");
            }
        }
    }

    public static void main(String[] args) throws Throwable {
        String fileName = args.length == 0
                ? "file-that-does-not-exist.txt"
                : args[0];
        inspectFile(fileName);
    }
}
```

Khi file không tồn tại trên hệ thống kiểu POSIX, kết quả thường có dạng:

```text
fopen failed: errno=2 (No such file or directory)
```

Số `2` và thông điệp trên chỉ là ví dụ thường gặp; mã và câu chữ thực tế phụ thuộc C runtime, hệ điều hành và locale. `fopen` trả về null mới là dấu hiệu thất bại. `errno` cung cấp chi tiết cho thất bại đó.

Trong ví dụ, `strerror` trả về con trỏ tới chuỗi C kết thúc bằng byte NUL. Con trỏ native trả về ban đầu có kích thước segment bằng 0 vì FFM không tự biết vùng nhớ đằng sau địa chỉ dài bao nhiêu. `reinterpret(Long.MAX_VALUE)` là thao tác restricted để gán giới hạn đọc cho con trỏ; chỉ dùng kiểu đọc này khi hợp đồng native bảo đảm con trỏ hợp lệ và chuỗi có ký tự kết thúc NUL. Với API sản xuất trả về vùng nhớ có kích thước xác định, ưu tiên dùng kích thước đó hoặc viết native wrapper sao chép dữ liệu vào buffer có giới hạn rõ ràng. Đọc chuỗi `strerror` ngay sau khi gọi vì thư viện có thể tái sử dụng vùng nhớ chứa thông điệp ở lần gọi sau.

## 5. Đọc đúng quy ước báo lỗi của từng nền tảng

`captureCallState` nhận tên trạng thái được linker hỗ trợ trên nền tảng hiện tại. Với các API Windows, trường cần chụp có thể khác `errno`:

| Nhóm API | Trạng thái thường dùng | Dấu hiệu thất bại cần kiểm tra |
|---|---|---|
| C standard library | `errno` | Theo hợp đồng từng hàm, chẳng hạn `fopen` trả null. |
| Win32 | `GetLastError` | Theo hợp đồng hàm, thường là `FALSE`, `NULL` hoặc một giá trị sentinel khác. |
| Winsock | `WSAGetLastError` | Theo hợp đồng socket API, thường là `SOCKET_ERROR` hoặc giá trị thất bại được mô tả. |
| Thư viện có error queue riêng | API truy vấn lỗi của thư viện | Theo quy ước của thư viện; không thay thế bằng `errno` nếu thư viện không đặt nó. |

Ví dụ, khi linker công bố trường `GetLastError`, có thể liên kết handle với:

```java
Linker.Option captureWindowsError =
        Linker.Option.captureCallState("GetLastError");
```

Sau đó lấy `VarHandle` từ `Linker.Option.captureStateLayout()` bằng tên trường tương ứng và đọc sau khi hàm Win32 báo thất bại. Với Winsock, dùng `WSAGetLastError` nếu đó là trạng thái mà hàm quy định. Đừng gọi một API truy vấn trạng thái lỗi sau downcall rồi mới đọc trạng thái, vì chính lời gọi truy vấn hoặc một lời gọi native khác có thể làm mất thông tin mà bạn muốn giữ.

Nếu API trả trực tiếp mã lỗi, hãy giữ nguyên mã đó. Ví dụ, nhiều hàm pthread trả `0` khi thành công và một mã lỗi khác `0` khi thất bại; tài liệu yêu cầu diễn giải giá trị trả về, không phải đọc `errno`. Với thư viện có error queue, phải truy vấn queue đúng thời điểm và đúng thread theo hợp đồng của thư viện.

## 6. Khác biệt giữa Java 22 và JDK hiện hành

FFM API được chuẩn hóa trong Java 22 theo JEP 454. `Linker.Option.captureCallState(String...)` và `captureStateLayout()` đều có từ Java 22. Các ví dụ dùng `java.lang.foreign`, `Arena`, `MemorySegment`, `FunctionDescriptor` và `Linker`; chúng không dùng API preview cũ trong package `jdk.incubator.foreign`.

Có một thay đổi tài liệu cần lưu ý khi chạy mã trên JDK mới:

| Phiên bản | Hành vi được mô tả cho `captureCallState` |
|---|---|
| Java 22 đến Java 26 | Chụp trạng thái ngay sau downcall và ghi vào capture-state segment. |
| JDK 27 | Khởi tạo phần trạng thái được chọn từ capture-state segment trước downcall, sau đó chụp lại trạng thái ngay sau downcall. |

Vì vậy, trong JDK 27, nếu hàm cần trạng thái ban đầu cụ thể, hãy khởi tạo trường tương ứng trong segment trước lời gọi. Ví dụ, đặt `errno` về `0` bằng `ERRNO.set(state, 0L, 0)` trước downcall. Trong Java 22, thao tác này chỉ đặt giá trị ban đầu cho buffer Java; chức năng chụp `errno` sau lời gọi vẫn hoạt động như bình thường. Không dựa vào giá trị buffer chưa khởi tạo khi chuyển chương trình sang JDK mới.

## 7. Quy tắc thực hành để không đọc nhầm lỗi

- **Đọc hợp đồng của hàm trước khi liên kết.** Xác định kiểu trả về, sentinel, trạng thái phụ và điều kiện nào khiến trạng thái lỗi có ý nghĩa.
- **Kiểm tra kết quả trước khi đọc trạng thái.** Chỉ đọc `errno` sau khi hàm đã báo thất bại theo hợp đồng.
- **Chụp trạng thái trong chính downcall.** Gắn `captureCallState` khi tạo handle để giữ giá trị trước khi lời gọi khác có thể ghi đè.
- **Dùng layout do linker cung cấp.** Không tự định nghĩa struct, offset, kích thước hoặc alignment của capture-state segment.
- **Kiểm tra trường được hỗ trợ.** Tên như `errno`, `GetLastError` và `WSAGetLastError` phụ thuộc nền tảng; tên không hỗ trợ sẽ gây `IllegalArgumentException`.
- **Không ghép `captureCallState` với `Linker.Option.critical(...)`.** Hai linker option này không thể kết hợp trên cùng downcall handle.
- **Giữ mã lỗi gốc trong Java exception hoặc log.** Ghi cả tên hàm, mã số và ngữ cảnh thao tác; thông điệp văn bản chỉ là phần diễn giải bổ sung.
- **Không phân tích chuỗi lỗi để quyết định logic.** Chuỗi từ `strerror` hoặc API hệ điều hành có thể thay đổi theo locale và phiên bản. Dùng mã lỗi hoặc hằng tương ứng để xử lý.
- **Giới hạn vùng nhớ native.** Các con trỏ trả về từ thư viện cần quy tắc rõ về kích thước và vòng đời. Các thao tác như `MemorySegment.reinterpret` là restricted và phải dùng đúng hợp đồng native.

Để gọi các restricted method của FFM API, hãy bật native access cho module chứa mã gọi. Với ứng dụng trên classpath:

```bash
javac NativeOpenCheck.java
java --enable-native-access=ALL-UNNAMED NativeOpenCheck
```

Với ứng dụng dùng named module, thay `ALL-UNNAMED` bằng tên module, ví dụ `--enable-native-access=com.example.nativebridge`. Tùy chọn này cấp quyền gọi các API native bị giới hạn của JVM; nó không tự cấp quyền truy cập file hoặc quyền hệ điều hành cho thư viện C. Đặc biệt, `Linker.downcallHandle(...)` và `MemorySegment.reinterpret(...)` là các thao tác restricted vì linker không thể xác minh hoàn toàn chữ ký hàm hoặc kích thước thật của con trỏ native.

## 8. Kết luận

`Linker.Option.captureCallState(...)` là cơ chế FFM API chuẩn để giữ trạng thái native như `errno` ngay sau một downcall. Tuy nhiên, việc đọc trạng thái chỉ đúng khi hàm thực sự dùng trạng thái đó và kết quả trả về đã chỉ ra lỗi. Với các API trả mã lỗi trực tiếp, trạng thái riêng của Windows hoặc error queue của thư viện, hãy tuân thủ đúng hợp đồng tương ứng.

Khi triển khai, dùng `captureStateLayout()` để cấp phát segment đúng kích thước và alignment, đọc trường bằng `VarHandle`, kiểm tra trạng thái được hỗ trợ trên hệ điều hành và giữ lại mã lỗi gốc để chẩn đoán. FFM API là API chính thức từ Java 22 và vẫn được duy trì trong JDK 27; không cần quay lại các bản FFM incubator hoặc preview cũ.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Oracle Java SE 22: Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [Oracle Java SE 22: Checking for Native Errors Using errno](https://docs.oracle.com/en/java/javase/22/core/checking-native-errors-using-errno.html)
- [Java SE 22 API: `Linker.Option`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Java SE 22 API: `MemoryLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java SE 22 API: `SegmentAllocator`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
- [Java SE 27 API: `Linker.Option`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Oracle Java SE 27: Restricted Methods](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)
- [Oracle Java SE 27: Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/27/core/foreign-function-and-memory-api.html)
