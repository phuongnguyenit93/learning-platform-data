# Kiểm tra giá trị trả về trước khi đọc mã lỗi theo hợp đồng của hàm khi gọi native bằng FFM

## 1. Vì sao phải kiểm tra giá trị trả về trước?

Với **Foreign Function & Memory API (FFM)** của Java, một lời gọi native (*downcall*) được biểu diễn bằng `MethodHandle` do `Linker.downcallHandle` tạo. Java có thể gọi các hàm C như `fopen`, `tmpfile`, `fclose`, `read` hoặc một hàm Windows API mà không cần tự viết JNI wrapper. Tuy nhiên FFM **không tự biến tất cả lỗi C thành Java exception**.

Hợp đồng lỗi của từng native function thường có hai phần:

1. **Giá trị trả về** quyết định cuộc gọi thành công, thất bại, kết thúc luồng dữ liệu, hay một kết quả bình thường.
2. **Mã lỗi phụ trợ** như C `errno`, Windows `GetLastError` hoặc WinSock `WSAGetLastError` chỉ có ý nghĩa trong **những trường hợp mà hợp đồng hàm cho phép đọc nó**.

Ví dụ C:

```c
FILE *f = fopen("missing.txt", "rb");
if (f == NULL) {
    int saved_errno = errno;  /* Lỗi có ý nghĩa theo hợp đồng fopen. */
    /* Xử lý hoặc báo lỗi dựa trên saved_errno. */
} else {
    /* fopen thành công: KHÔNG coi errno != 0 là thất bại. */
    /* Dùng f rồi fclose(f) đúng lúc. */
}
```

**Quy tắc học quan trọng nhất:**

> **Native result → diễn giải theo hợp đồng riêng của hàm → nếu kết quả chỉ ra lỗi và API định nghĩa kênh lỗi phụ trợ thì mới đọc mã lỗi đã được capture.** Không đảo trình tự này.

Hệ quả trực tiếp:

- `errno != 0` **không phải** dấu hiệu tổng quát của một C function vừa thất bại.
- `GetLastError() != 0` **không phải** dấu hiệu tổng quát của một Win32 call vừa thất bại.
- `result == 0` cũng **không** luôn là lỗi. Ví dụ `read` trả 0 khi tới EOF, trong khi Win32 `CloseHandle` trả 0 khi thất bại; `getaddrinfo` trả 0 khi thành công.
- `result == -1` không luôn là lỗi: một số API dùng `-1` làm giá trị hợp lệ; phải đọc đúng tài liệu hàm và có thể cần quy trình `errno = 0` trước call.
- Ngay cả khi FFM đã **capture** trạng thái lỗi kịp thời, ứng dụng vẫn phải **quyết định có đọc/diễn giải nó hay không dựa trên kết quả native**.

Bài học tập trung vào FFM **JDK 22+** (JEP 454, API đã ổn định). Các ví dụ Java hoàn chỉnh đã được biên dịch và chạy với **JDK 24**. Chúng dùng `java.lang.foreign`, `java.lang.invoke` và cờ `--enable-native-access=ALL-UNNAMED` cho downcall restricted API ở classpath. Không dùng trực tiếp ví dụ này trên JDK 17: FFM ở JDK 17 có API incubator khác.

## 2. Không có một quy ước trả lỗi chung cho mọi hàm C

Để triển khai wrapper chính xác, hãy bắt đầu từ **Return value / Errors** trong tài liệu của **chính native function đang gọi**, không bắt đầu bằng phỏng đoán về `errno`.

| Hàm hoặc họ API | Dấu hiệu theo return contract | Khi nào xem mã lỗi phụ trợ? |
| --- | --- | --- |
| C `fopen(path, mode)` | `FILE*` khác NULL: thành công; `NULL`: thất bại | Khi `NULL`, đọc `errno` của **chính call** |
| C `tmpfile()` | `FILE*` khác NULL: thành công; `NULL`: thất bại | Khi `NULL`, xem `errno` |
| C `fclose(FILE*)` | `0`: thành công; `EOF` (thường `-1`): lỗi | Khi trả lỗi, xem `errno` theo hợp đồng thư viện |
| POSIX `open(path, flags)` | File descriptor `>= 0`: thành công, `-1`: lỗi | Chỉ khi `-1`; **fd = 0 là hợp lệ** |
| POSIX `read(fd, buffer, n)` | Số byte `>0`: dữ liệu; `0`: EOF; `-1`: lỗi | Chỉ khi `-1`; đọc ít hơn `n` chưa hẳn lỗi |
| C `fread(...)` | Số phần tử đã đọc; thấp hơn yêu cầu có thể là EOF hoặc lỗi | Phân biệt bằng `ferror`/`feof`; không tự suy từ `errno` |
| POSIX `getaddrinfo(...)` | `0` thành công; số khác 0 là mã lỗi `EAI_*` **trả trực tiếp** | Dùng `gai_strerror(result)`; `errno` chỉ liên quan một số trường hợp như `EAI_SYSTEM` |
| POSIX `pthread_*` (nhiều hàm) | `0` thành công, số khác 0 là error code **trả trực tiếp** | Không giả định các hàm này tự đặt `errno` |
| Win32 `CloseHandle(h)` | `BOOL != 0` thành công, `0` thất bại | `GetLastError` khi trả `0` |
| Win32 `GetFileAttributesW(path)` | `INVALID_FILE_ATTRIBUTES` (`0xFFFFFFFF`) là lỗi | `GetLastError` khi gặp sentinel này |
| WinSock hàm được tài liệu hóa dùng `WSAGetLastError` | Sentinel cụ thể (`SOCKET_ERROR`, `INVALID_SOCKET`, …) | Chỉ khi trạng thái yêu cầu; dùng **WSAGetLastError**, không lẫn Win32 |
| COM/Win32 `HRESULT` | `SUCCEEDED(hr)` / `FAILED(hr)` dựa trên bit sign | Chính `HRESULT` đã biểu thị tình trạng; chỉ đọc kênh phụ trợ nếu API có nói |

Bảng là **định hướng đọc hợp đồng**, không thay thế documentation từng function. Những kiểu như `size_t`, `ssize_t`, `long`, `BOOL`, `DWORD` và pointer phải được mô tả bằng `FunctionDescriptor` phù hợp ABI cụ thể. Ví dụ `BOOL` thường là 32-bit integer của Win32, không phải `ValueLayout.JAVA_BOOLEAN`.

## 3. Vì sao errno có thể khác 0 dù native call thành công?

### 3.1. errno không phải “cờ thành công/thất bại”

Trong C/POSIX, `errno` là trạng thái lỗi có ngữ cảnh **theo luồng**. Nhiều hàm chỉ thiết lập `errno` khi gặp lỗi và **không bắt buộc reset thành 0 khi thành công**. Một số hàm còn được phép thay đổi `errno` ngay cả khi thành công.

Giả sử:

```text
Lần 1: fopen(missing, "rb") -> NULL, errno = ENOENT
Lần 2: tmpfile()            -> FILE* khác NULL
                              errno có thể vẫn là ENOENT
```

Nếu sau lần 2 viết:

```java
// SAI: biến cả cuộc gọi thành công thành lỗi.
if (capturedErrno != 0) {
    throw new IOException("tmpfile failed");
}
```

thì có thể ném exception dù `tmpfile` đã trả về một `FILE*` hợp lệ. Đọc lỗi phải dựa trên return contract: `tmpfile` **chỉ thất bại nếu trả NULL**.

Trong thử nghiệm JDK 24 trên Windows C runtime, `fopen` cho file không tồn tại đặt `errno = 2`, sau đó `tmpfile` trả file pointer hợp lệ nhưng giá trị `errno` capture được **vẫn có thể là 2**. Đó là **quan sát minh họa**, không phải bảo đảm mọi CRT hoặc OS sẽ giữ nguyên con số này.

### 3.2. Không tự reset errno sau từng call

Một hiểu lầm khác: “Trước mọi native call, cứ reset `errno = 0` để dễ kiểm tra.” Điều này **không giải quyết** lỗi logic nếu vẫn kết luận thành bại chỉ từ errno.

- Với `fopen`, `tmpfile`, `open` hoặc `read`, return contract đã nêu rõ sentinel. **Không cần reset errno** để quyết định thành công.
- Một số API có **giá trị sentinel vừa có thể thành công, vừa có thể báo lỗi**. Với trường hợp đặc biệt đó, tài liệu có thể yêu cầu đặt `errno = 0` **trước khi gọi hàm** rồi phân loại cả giá trị trả về và `errno`.
- Mã lỗi có thể là kênh riêng như `HRESULT` hoặc `EAI_*`, không cần `errno`.

**Không nhầm:** `capturedState.set(JAVA_INT, ..., 0)` chỉ thay đổi **buffer Java cấp cho capture**, **không reset native thread-local errno thực sự**. Nếu một API cần reset errno trước call, phải làm qua cơ chế native đúng thread/đúng CRT và theo tài liệu hàm.

## 4. Vấn đề thời gian: dù đã biết call thất bại, mã lỗi vẫn có thể bị ghi đè

Trong C thông thường:

```c
FILE *f = fopen(path, "rb");

if (f == NULL) {
    int saved = errno; /* LƯU NGAY ở thời điểm hợp đồng báo lỗi. */
    log_message("open failed");  /* Có thể thực hiện các call native khác. */
    report_error(saved);        /* Dùng mã đã lưu, không đọc lại errno. */
}
```

Nếu mã C gọi thêm `printf`, `malloc`, `strerror` hoặc API khác **trước khi copy `errno`**, giá trị TLS có thể đổi và mất nguyên nhân của `fopen`. Trong Java FFM, quá trình chuyển từ native sang Java có thể liên quan runtime/linker; nên **đọc errno bằng cách gọi một hàm khác sau khi downcall đã trả về không đủ tin cậy**.

FFM giải quyết việc *chụp snapshot* bằng:

```java
Linker.Option.captureCallState("errno")
```

Linker ghi trạng thái cần capture **ngay sau native call, trước khi runtime hoặc thao tác thông thường có cơ hội ghi đè**. Code Java sau đó có thể kiểm tra return value và **chỉ nếu đã thất bại** đọc code đã capture.

**Hai thao tác có nhiệm vụ khác nhau:**

- `captureCallState`: lưu dữ liệu kịp thời, bất kể thành công/thất bại.
- `if (nativeReturn indicates failure)`: chọn lúc có ý nghĩa để diễn giải dữ liệu đã lưu.

Capture trạng thái **không thay thế việc kiểm tra giá trị trả về**; nó cũng không biến exception của Java thành errno.

## 5. Cấu tạo captureCallState trong FFM

### 5.1. Từ SymbolLookup đến MethodHandle

Một downcall thường bắt đầu bằng:

```java
Linker linker = Linker.nativeLinker();
SymbolLookup c = linker.defaultLookup();

MethodHandle fopen = linker.downcallHandle(
        c.findOrThrow("fopen"),
        FunctionDescriptor.of(
                ValueLayout.ADDRESS,  // FILE * result
                ValueLayout.ADDRESS,  // const char *filename
                ValueLayout.ADDRESS), // const char *mode
        Linker.Option.captureCallState("errno"));
```

**Đây là đoạn minh họa**, nằm trong class có `import java.lang.foreign.*; import java.lang.invoke.MethodHandle;`. Việc link phải đúng ABI hàm C; sai descriptor có thể dẫn tới crash/memory corruption. Method handle trên được **bound** vào symbol `fopen` cụ thể bằng overload `downcallHandle(symbol, descriptor, option)`.

### 5.2. Buffer capture là một MemorySegment riêng

`Linker.Option.captureStateLayout()` trả `StructLayout` phụ thuộc nền tảng, chứa những field tên tương ứng với trạng thái có thể capture. Chẳng hạn môi trường Windows có thể hỗ trợ `errno`, `GetLastError` và `WSAGetLastError`, trong khi Unix-like platform thường dùng `errno`.

Không tự đoán offsets hoặc giả định layout capture giống nhau trên mọi máy. Dùng:

```java
StructLayout stateLayout = Linker.Option.captureStateLayout();
MemorySegment state = arena.allocate(stateLayout);
VarHandle errnoField = stateLayout.varHandle(
        MemoryLayout.PathElement.groupElement("errno"));
```

Đọc snapshot bằng:

```java
int savedErrno = (int) errnoField.get(state, 0L);
```

`0L` là tọa độ offset do `VarHandle` yêu cầu cho layout path trong cách dùng này. Cấp phát `arena.allocate(stateLayout)` cũng bảo đảm dung lượng và căn chỉnh tương ứng. **Không** cấp buffer chỉ một `JAVA_INT` rồi truyền tùy tiện nếu state layout nền tảng lớn hơn hoặc có padding.

### 5.3. Một tham số mới xuất hiện trong signature của downcall

Với downcall **bound** như trên, `captureCallState` tạo thêm một tham số `MemorySegment` ở đầu các đối số Java của `MethodHandle`:

```java
MemorySegment file = (MemorySegment) fopen.invokeExact(
        state,       // Tham số do FFM thêm để lưu call state.
        pathCString, // Đối số C số 1.
        modeCString  // Đối số C số 2.
);
```

Không nhầm tham số `state` với một đối số thực của `fopen`. Ở C, prototype vẫn là `FILE *fopen(const char *, const char *)`.

Với **unbound downcall handle**, địa chỉ target function xuất hiện trong danh sách Java parameters trước buffer capture. Với overload **bound symbol** dùng trong bài, function address đã gắn vào handle, nên tham số mới đầu tiên chính là `state`.

`MethodHandle.invokeExact` cần **kiểu tham số và kiểu trả về chính xác**; ví dụ kết quả `fopen` phải cast là `MemorySegment`, còn `fclose` trả `int`. Lỗi `WrongMethodTypeException` là lỗi cấu hình/invocation Java, **không phải** `errno` từ một C function đã báo thất bại.

### 5.4. Lấy danh sách state fields có hỗ trợ trên nền tảng

`captureCallState` có thể ném `IllegalArgumentException` nếu tên field yêu cầu không hỗ trợ ở platform hiện tại. Dùng:

```java
var supported = Linker.Option.captureStateLayout()
        .memberLayouts().stream()
        .map(MemoryLayout::name)
        .flatMap(java.util.Optional::stream)
        .toList();
System.out.println(supported);
```

Đây là snippet đặt trong class đã import `java.lang.foreign.*`. Danh sách là **platform-dependent**, vì vậy không hardcode output. Nếu native API thuộc Win32, hãy capture `GetLastError`; nếu thuộc WinSock và tài liệu yêu cầu WinSock error, capture `WSAGetLastError`; nếu thuộc C runtime/POSIX, xem xét `errno`.

## 6. Chương trình Java hoàn chỉnh: kiểm tra fopen trước khi đọc errno

Ví dụ sử dụng **C standard library** qua FFM. Chương trình:

1. Tạo một thư mục tạm bằng Java, bảo đảm file `absent-file.txt` chưa tồn tại trong thư mục mới.
2. Gọi `fopen(path, "rb")`; theo hợp đồng, `NULL` nghĩa là lỗi.
3. **Chỉ sau khi thấy result == NULL** mới đọc `errno` đã được FFM capture.
4. Gọi `tmpfile()`; thành công nếu trả pointer khác NULL, **không nhìn errno để quyết định thành bại**.
5. Gọi `fclose(FILE*)`; thành công nếu trả `0`.
6. Giải phóng tài nguyên Java (arena) và thư mục tạm. `FILE*` được đóng tường minh bởi `fclose`, **không** được giải phóng bằng `Arena.close`.

### 6.1. Tệp NativeReturnFirstDemo.java

```java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class NativeReturnFirstDemo {
    private static final Linker LINKER = Linker.nativeLinker();
    private static final SymbolLookup C = LINKER.defaultLookup();

    private static final Linker.Option CAPTURE =
            Linker.Option.captureCallState("errno");

    private static final StructLayout STATE =
            Linker.Option.captureStateLayout();

    private static final VarHandle ERRNO =
            STATE.varHandle(groupElement("errno"));

    // FILE *fopen(const char *filename, const char *mode)
    private static final MethodHandle FOPEN = LINKER.downcallHandle(
            C.findOrThrow("fopen"),
            FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS),
            CAPTURE);

    // FILE *tmpfile(void)
    private static final MethodHandle TMPFILE = LINKER.downcallHandle(
            C.findOrThrow("tmpfile"),
            FunctionDescriptor.of(ADDRESS),
            CAPTURE);

    // int fclose(FILE *stream)
    private static final MethodHandle FCLOSE = LINKER.downcallHandle(
            C.findOrThrow("fclose"),
            FunctionDescriptor.of(JAVA_INT, ADDRESS),
            CAPTURE);

    public static void main(String[] args) throws Throwable {
        Path directory = Files.createTempDirectory("ffm-return-first-");

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment callState = arena.allocate(STATE);
            MemorySegment missing = arena.allocateFrom(
                    directory.resolve("absent-file.txt").toString());
            MemorySegment mode = arena.allocateFrom("rb");

            MemorySegment file = (MemorySegment) FOPEN.invokeExact(
                    callState, missing, mode);

            // 1) Luôn xét return contract trước.
            if (file.address() == 0) {
                // 2) Chỉ vì fopen đã thất bại, errno mới có ý nghĩa.
                int savedErrno = (int) ERRNO.get(callState, 0L);
                System.out.println("fopen failed: true");
                System.out.println("errno captured on failure: "
                        + (savedErrno != 0));
            } else {
                // Nhánh phòng vệ: không rò FILE* nếu môi trường lạ.
                try {
                    throw new AssertionError("Unexpected existing file");
                } finally {
                    int ignored = (int) FCLOSE.invokeExact(callState, file);
                }
            }

            MemorySegment temporary =
                    (MemorySegment) TMPFILE.invokeExact(callState);

            // Không xem errno của tmpfile trước khi xét FILE*.
            if (temporary.address() == 0) {
                int savedErrno = (int) ERRNO.get(callState, 0L);
                throw new IllegalStateException(
                        "tmpfile failed, errno=" + savedErrno);
            }
            System.out.println("tmpfile succeeded: true");

            // Sau call thành công, bỏ qua errno dù nó có thể khác 0.
            int closed = (int) FCLOSE.invokeExact(callState, temporary);
            if (closed != 0) {
                int savedErrno = (int) ERRNO.get(callState, 0L);
                throw new IllegalStateException(
                        "fclose failed, errno=" + savedErrno);
            }
            System.out.println("fclose succeeded: true");

        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

**Build/run bằng JDK 22+ trên platform có C runtime exports tương ứng:**

```bash
javac NativeReturnFirstDemo.java
java --enable-native-access=ALL-UNNAMED NativeReturnFirstDemo
```

**Stdout đã kiểm tra trên JDK 24 / Windows (C runtime hỗ trợ `fopen`, `tmpfile`, `fclose`):**

```text
fopen failed: true
errno captured on failure: true
tmpfile succeeded: true
fclose succeeded: true
```

**Độ ổn định:** ví dụ chủ động không in giá trị `errno` cụ thể vì mã số và thông báo lỗi phụ thuộc OS/CRT; chỉ kiểm tra mã lỗi khác 0 sau một thất bại được hợp đồng `fopen` xác nhận. `tmpfile()` cần thư mục tạm và tài nguyên hệ điều hành; trên môi trường không cho phép tạo file tạm, hàm có thể thất bại và chương trình sẽ ném lỗi có `errno` theo đúng contract thay vì in stdout thành công. Một số nền tảng có export name/library lookup khác; khi đó cần chỉ định đúng native library và ABI.

### 6.2. Tại sao ví dụ không dựa vào errno sau thành công?

Hai câu lệnh quan trọng là:

```java
MemorySegment temporary =
        (MemorySegment) TMPFILE.invokeExact(callState);

if (temporary.address() == 0) {
    int savedErrno = (int) ERRNO.get(callState, 0L);
    throw new IllegalStateException("tmpfile failed, errno=" + savedErrno);
}
```

Giả sử buffer `callState` sau `tmpfile` chứa một mã lỗi khác 0 từ hoạt động trước hoặc từ nội bộ CRT. `temporary.address() != 0` **vẫn là bằng chứng thành công theo hợp đồng `tmpfile`**. Việc diễn giải `errno` khi không có sentinel lỗi có thể tạo false positive.

Tương tự, `fclose` trả `0` trên thành công; Java không phải đọc trạng thái lỗi chỉ để tìm một số khác 0.

### 6.3. Vì sao không truyền file pointer vào Java Arena.close?

`MemorySegment` trả về từ `fopen`/`tmpfile` chỉ bọc địa chỉ native `FILE*`; đối tượng Java không sở hữu cơ chế đóng stream. `arena.close()` giải phóng những vùng memory **đã được arena cấp phát** (ví dụ C strings và capture-state buffer), **không tự gọi `fclose` đối với FILE*** do C runtime cấp. Phải gọi `fclose` đúng hợp đồng, và nếu bỏ dở workflow giữa các bước nên bảo vệ stream bằng `try/finally` hoặc wrapper `AutoCloseable`.

### 6.4. Điều gì được kiểm thử thật?

Mã `NativeReturnFirstDemo.java` được biên dịch và chạy bằng JDK 24, với `--enable-native-access=ALL-UNNAMED`. Trên máy thử, `fopen` trả NULL, `errno` được capture; `tmpfile` trả nonnull; `fclose` trả 0. Bài **không yêu cầu cài C compiler** vì dùng các hàm C runtime đã có trong tiến trình.

## 7. Windows có kênh riêng: GetLastError không đồng nghĩa errno

### 7.1. Hợp đồng Win32

Một số Win32 APIs dùng mã lỗi do `GetLastError()` trả về. Đây là trạng thái theo thread Windows, **không phải** biến `errno` của C runtime. Cũng không giống WinSock `WSAGetLastError()`.

Ví dụ:

- `BOOL CloseHandle(HANDLE h)`: kết quả **khác 0 là thành công**; `0 là lỗi`, đọc `GetLastError` để hiểu lý do.
- `DWORD GetFileAttributesW(LPCWSTR path)`: trả `INVALID_FILE_ATTRIBUTES` (`0xFFFFFFFF`) khi lỗi; các giá trị thuộc tính khác là kết quả thành công, **không cần đọc GetLastError**.
- WinSock API có thể yêu cầu `WSAGetLastError`, không phải `GetLastError`.

Microsoft lưu ý một số API đặt last-error thành 0 khi thành công, một số **không reset**, và một số có thể đặt giá trị ngay cả trên success. Do đó `GetLastError()!=0` **không phải điều kiện thất bại chung**.

### 7.2. Vì sao captureCallState("GetLastError") hữu ích?

Trình tự đúng:

```text
Java gọi downcall Win32
  -> hàm C/Win32 thực thi
  -> FFM chụp GetLastError ngay sau call vào MemorySegment
  -> Java nhận kết quả int/DWORD/BOOL
  -> xét result theo tài liệu API
      |
      +-- thất bại: đọc GetLastError snapshot
      |
      +-- thành công: bỏ qua snapshot hoặc chỉ dùng khi API định nghĩa rõ
```

Không gọi bừa một downcall `GetLastError()` mới sau khi Java đã chuyển qua các native calls khác: error state có thể đã bị thay đổi. Capture option cho phép giữ snapshot đúng thời điểm.

### 7.3. Chương trình Windows độc lập: GetFileAttributesW

Chương trình sau **chỉ chạy trên Windows**, dùng `kernel32.dll`. Thư mục tạm do Java tạo để bảo đảm `absent-file.dat` chưa tồn tại. Hàm Win32 trả sentinel `INVALID_FILE_ATTRIBUTES`; **chỉ trong nhánh sentinel** mới đọc mã `GetLastError` đã capture.

**Tệp `Win32ReturnFirstDemo.java`:**

```java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class Win32ReturnFirstDemo {
    public static void main(String[] args) throws Throwable {
        Path directory = Files.createTempDirectory("ffm-winerr-");

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();

            SymbolLookup kernel32 = SymbolLookup.libraryLookup(
                    "kernel32.dll", arena);

            StructLayout stateLayout =
                    Linker.Option.captureStateLayout();

            VarHandle errorField = stateLayout.varHandle(
                    groupElement("GetLastError"));

            // DWORD GetFileAttributesW(LPCWSTR lpFileName)
            MethodHandle attributes = linker.downcallHandle(
                    kernel32.findOrThrow("GetFileAttributesW"),
                    FunctionDescriptor.of(JAVA_INT, ADDRESS),
                    Linker.Option.captureCallState("GetLastError"));

            MemorySegment callState = arena.allocate(stateLayout);

            MemorySegment name = arena.allocateFrom(
                    directory.resolve("absent-file.dat").toString(),
                    StandardCharsets.UTF_16LE);

            int result = (int) attributes.invokeExact(callState, name);

            // INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF = int -1.
            if (result == -1) {
                int winError = (int) errorField.get(callState, 0L);
                System.out.println("Win32 call failed: true");
                System.out.println("GetLastError captured on failure: "
                        + (winError != 0));
            } else {
                System.out.println("Win32 call succeeded");
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

**Lệnh chạy trên Windows:**

```bat
javac Win32ReturnFirstDemo.java
java --enable-native-access=ALL-UNNAMED Win32ReturnFirstDemo
```

**Stdout đã xác minh với JDK 24 trên Windows:**

```text
Win32 call failed: true
GetLastError captured on failure: true
```

Phân tích:

1. Tên function là `GetFileAttributesW`, bản wide-character; `StandardCharsets.UTF_16LE` cung cấp chuỗi UTF-16LE đúng loại `LPCWSTR` và hàm `allocateFrom` tạo phần kết thúc NUL theo encoding.
2. `JAVA_INT` dùng để biểu diễn `DWORD` 32-bit khi đi qua `MethodHandle`. Giá trị unsigned `0xFFFFFFFF` có biểu diễn signed `int == -1`. Không gọi `GetLastError` chỉ vì một flag trong kết quả tình cờ khác 0.
3. Khi `result == -1`, mới đọc `GetLastError` vừa được FFM capture. Trên máy thử, code trả `2` (file not found), nhưng bài kiểm tra chỉ yêu cầu **khác 0** và không dùng mã số làm contract chung mọi tình huống.
4. `GetLastError` không dùng thay cho C `errno`. Nếu đang gọi `fopen` của CRT trên Windows, nhánh lỗi thường xem **errno của CRT**, không tự động xem Win32 last-error.

### 7.4. Chú ý khi chọn loại Win32 failure sentinel

Không quy đồng Win32 với “trả 0 là lỗi”:

| Win32 API/họ API | Return status cần xét |
| --- | --- |
| `CloseHandle` | BOOL = 0 là lỗi |
| `GetFileAttributesW` | DWORD = 0xFFFFFFFF là lỗi |
| `CreateFileW` | HANDLE = `INVALID_HANDLE_VALUE` là lỗi, **không phải luôn NULL** |
| `HRESULT`-returning API | Dùng `FAILED(hr)`/`SUCCEEDED(hr)`, không mặc định mọi nonzero là lỗi |

Nếu API có điều kiện trả giá trị “thành công có thông tin bổ sung”, đọc `GetLastError` đúng đoạn tài liệu hàm đó, không áp dụng một quy tắc chung.

## 8. Các API trả mã lỗi trực tiếp: không được dùng errno làm kênh chính

Một số native functions encode lý do lỗi **ngay trong return value**. Ví dụ POSIX:

```c
int rc = getaddrinfo(node, service, hints, &result);
if (rc != 0) {
    /* rc là mã EAI_* (không phải -1 chung cho errno).
       gai_strerror(rc) thường dùng để mô tả lỗi. */
} else {
    /* result hợp lệ; sau dùng phải freeaddrinfo(result). */
}
```

Theo tài liệu `getaddrinfo`, nếu `rc == EAI_SYSTEM` thì một lỗi hệ thống liên quan có thể được phản ánh trong `errno`. Nhưng với mã lỗi `EAI_*` khác, đọc `errno` thay cho `rc` là **sai**.

Tương tự nhiều POSIX `pthread_*` trả `0` hoặc trả **error number** trực tiếp, không thiết lập `errno`. Và với một số C++/library-specific APIs, output parameter hoặc một struct kết quả có thể chứa trạng thái; cần bám đúng API docs.

Trong FFM, nên chuyển kết quả thành Java abstraction rõ ràng:

```java
// Pseudocode: rc là mã trả về của native getaddrinfo.
if (rc != 0) {
    throw new NativeAddressResolutionException(rc);
}
// Không phụ thuộc errno ở nhánh thành công.
```

**Đoạn trên là pseudocode**, vì `NativeAddressResolutionException` là tên exception do ứng dụng tự định nghĩa, chưa có sẵn trong JDK. Khi dùng FFM thực tế, cần function descriptor đúng `struct addrinfo**`, đúng C layout và policy giải phóng.

## 9. Trạng thái thành công, EOF và partial result không giống lỗi

### 9.1. POSIX read

```c
ssize_t n = read(fd, buffer, capacity);
if (n < 0) {
    int saved_errno = errno;
    /* Lỗi: dùng saved_errno. */
} else if (n == 0) {
    /* EOF: thường là kết thúc stream/file bình thường. */
} else {
    /* n bytes đã được đọc, kể cả n < capacity. */
}
```

Một lần `read` trả **ít byte hơn yêu cầu** có thể hoàn toàn bình thường (pipe, socket, file near EOF). `n == 0` là EOF trong nhiều ngữ cảnh, không phải lỗi để gọi `perror`. Trong FFM, phải map `ssize_t` theo native ABI: trên các hệ thông dụng 64-bit, often 64-bit, nhưng không được dùng `JAVA_LONG` mù quáng trên mọi target. Không dùng `captureCallState("errno")` để thay cho phân loại `n<0 / n==0 / n>0`.

### 9.2. fread

`fread(ptr, size, count, stream)` trả **số phần tử đã đọc đầy đủ**. Nếu kết quả thấp hơn `count`, có thể do EOF **hoặc** lỗi I/O. Hợp đồng yêu cầu xem `feof(stream)` và `ferror(stream)` để phân biệt. `errno` riêng lẻ không diễn tả hết trạng thái stream.

Với `size == 0` hoặc `count == 0`, kết quả 0 có thể là **thành công hợp lệ**, không phải lỗi. Vì vậy logic `if (result == 0) throw ...` là sai cho `fread`.

### 9.3. API trả pointer hoặc integer 0 hợp lệ

- POSIX file descriptor bằng `0` có thể là valid descriptor. Kiểm tra `fd == -1` theo hợp đồng `open`.
- Hàm trả số lượng dữ liệu có thể trả `0` khi không có dữ liệu, không đồng nghĩa thất bại.
- C `NULL` là lỗi đối với `fopen`, nhưng với các API khác `NULL` có thể có nghĩa “không tìm thấy” như một kết quả bình thường, tùy contract.
- Một callback native trả `void` có thể dùng cơ chế báo lỗi riêng, không tự có một giá trị return để suy luận.

Cần thiết kế Java method rõ ràng: một trường hợp “not found” có thể được ánh xạ thành `Optional.empty()`, còn lỗi hệ thống có thể thành exception — **nhưng chỉ khi C API đã phân biệt hai trạng thái đó theo hợp đồng**.

## 10. Trường hợp đặc biệt: giá trị sentinel cũng có thể là kết quả thành công

Một số hàm như `strtol` hoặc POSIX `getpriority` có thể trả giá trị trùng sentinel lỗi. Khi đó **return value vẫn phải được đọc trước**, nhưng chỉ một mình return value chưa đủ phân loại.

Theo tài liệu từng API, mẫu có thể là:

```c
errno = 0;                  /* Đặt TRƯỚC native call. */
long value = strtol(s, &end, 10);

if (/* contract says range error based on value AND errno */) {
    /* Check captured/saved errno, e.g. ERANGE. */
}
/* Kiểm tra end pointer để biết có chuyển được chữ số nào không. */
```

Đây là **phác thảo C**, không phải chương trình chạy độc lập. `strtol` cần xem `endptr`, `ERANGE`, `LONG_MIN`/`LONG_MAX` và các quy tắc locale/range của C runtime; không thể quyết định bằng một điều kiện duy nhất `result == -1`. Đặc biệt, trên Windows LLP64 C `long` thường 32-bit, trên Linux LP64 thường 64-bit; phải map đúng ABI vào `FunctionDescriptor`.

Nếu FFM cần mẫu “reset errno trước call”, hãy chuẩn bị một wrapper native thiết lập errno trong **chính thread/CRT phù hợp** rồi gọi target function trong cùng critical sequence; **không** dùng thao tác set số 0 vào Java capture-state buffer để mô phỏng.

Điểm cần nhớ: **“kiểm tra return trước”** không phải “không bao giờ xem errno nếu return có thể hợp lệ”. Nó có nghĩa **bắt đầu từ contract trả về**, rồi dùng kết hợp return/error state đúng như contract quy định.

## 11. Java exception và native error là hai kênh khác nhau

Một native function có thể trả `-1` mà **không ném Java exception**. FFM downcall thường trả trực tiếp giá trị theo ABI; nó không tự biết rằng `-1` có nghĩa “file not found”.

Ngược lại, Java code có thể nhận một exception trước khi native function thực sự chạy:

- `IllegalCallerException` nếu native access chưa được cấp cho restricted operation.
- `NoSuchElementException` nếu `SymbolLookup.findOrThrow("name")` không tìm được symbol.
- `WrongMethodTypeException` nếu `MethodHandle.invokeExact` có signature không khớp.
- `IllegalArgumentException` hoặc `IllegalStateException` do layout/memory scope/misalignment/lifetime.
- Lỗi linker do `FunctionDescriptor` không hợp lệ hoặc ABI không được hỗ trợ.

**Những lỗi này không cần tra `errno` của C call nào đó.** Một Java exception về link hay method handle cũng không bảo đảm native function đã được gọi. Phải phân biệt kênh Java/JVM và mã lỗi **do native function trả ra theo API contract**.

Cảnh báo ngược lại: một descriptor sai mà vẫn gọi được có thể gây JVM crash hoặc memory corruption, không nhất thiết luôn ném Java exception. Do đó cần xác minh C prototype, pointer size, signedness, calling convention và struct layout.

## 12. Lưu mã lỗi đã capture trước khi làm bất cứ điều gì khác

Một downcall có capture buffer đem lại snapshot **ngay sau call**. Nhưng nếu **dùng lại chính buffer đó cho call tiếp theo**, trường dữ liệu sẽ bị ghi đè. Giữ mã bằng biến Java primitive:

```java
MemorySegment pointer =
        (MemorySegment) FOPEN.invokeExact(state, name, mode);

if (pointer.address() == 0) {
    int originalErrno = (int) ERRNO.get(state, 0L);

    // Từ đây originalErrno an toàn trước việc ghi đè state
    // bởi các downcalls khác hoặc thay đổi native TLS errno.
    logFailure(originalErrno); // Hàm ứng dụng tự định nghĩa.
}
```

**Đoạn là snippet**, giả định `FOPEN`/`ERRNO`/`state`/`name`/`mode` và `logFailure` tồn tại trong class.

Không đọc `state` sau khi gọi thêm một hàm được liên kết bằng `captureCallState` với **cùng buffer** rồi tưởng đó vẫn là mã lỗi của `FOPEN`.

### 12.1. Mỗi lời gọi hoặc mỗi luồng phải có capture storage phù hợp

`errno` và Windows last-error là trạng thái liên quan tới **native thread**. FFM ghi snapshot vào `MemorySegment` do caller cung cấp. Nếu hai Java threads cùng dùng **một mutable capture segment** mà không đồng bộ, kết quả capture có thể bị ghi đè bởi lời gọi khác.

Mẫu đơn giản: cấp một `MemorySegment` state **riêng cho từng native call** hoặc từng call sequence được kiểm soát, ví dụ trong `try (Arena arena = Arena.ofConfined())` cùng thread. Không chuyển confined `MemorySegment` sang thread khác; không giữ capture state sau khi arena đóng.

Nếu cần đa luồng, dùng state buffer riêng được cấp phát từ arena tương ứng hoặc quản lý đồng bộ thích hợp. Lưu trạng thái lỗi thành `int`/Java record ngay sau khi xác định failure để thông tin không phụ thuộc vòng đời capture memory.

### 12.2. Error code không phải resource handle

Một `errno` là con số, không yêu cầu `free`. Nhưng `fopen` thành công trả `FILE*` phải gọi `fclose`, ngay cả khi bạn không cần đọc/ghi. `GetFileAttributesW` không trả resource handle; `CreateFileW` trả HANDLE phải đóng bằng đúng API nếu thành công. Đừng nhầm trách nhiệm cleanup với trách nhiệm đọc status.

## 13. Thiết kế wrapper FFM: trả giá trị Java rõ ràng, không giấu lỗi native

Một wrapper tốt làm ranh giới giữa Java application và C API:

```text
Java service calls wrapper
       |
       v
FFM downcall -> native return + captured state
       |
       v
Check native return contract
       |
       +-- SUCCESS -> produce Java result, manage native resource
       |
       +-- END/EMPTY/NOT_FOUND -> Java EOF/Optional/empty outcome
       |                          (nếu contract định nghĩa)
       |
       +-- FAILURE -> read captured error code if needed
                      -> translate/throw/report with context
```

Ví dụ thiết kế có thể dùng một exception riêng giữ ba trường:

```java
public final class NativeCallException extends RuntimeException {
    private final String operation;
    private final String errorDomain;
    private final int code;

    public NativeCallException(
            String operation, String errorDomain, int code) {
        super(operation + " failed: " + errorDomain + "=" + code);
        this.operation = operation;
        this.errorDomain = errorDomain;
        this.code = code;
    }

    public String operation() { return operation; }
    public String errorDomain() { return errorDomain; }
    public int code() { return code; }
}
```

Đây là **class Java độc lập có thể biên dịch**, nhưng không có `main` vì chỉ là mô hình exception ứng dụng. Khi throw:

```java
if (file.address() == 0) {
    int errno = (int) ERRNO.get(state, 0L);
    throw new NativeCallException("fopen", "errno", errno);
}
```

là **đoạn sử dụng**, cần các biến và class đã định nghĩa. Trường `errorDomain` giữ rõ `errno`, `GetLastError`, `WSAGetLastError` hay mã trả trực tiếp như `EAI_*`; không gộp mọi số nguyên vào một bảng thông báo lỗi sai nền tảng.

### 13.1. Kể đủ ngữ cảnh, không làm lộ dữ liệu nhạy cảm

Một thông báo lỗi hữu ích nêu native function, status, error domain, số lỗi và chi tiết tài nguyên phù hợp (ví dụ loại tệp hoặc action). Với path người dùng hoặc tên dữ liệu nhạy cảm, cân nhắc logging/redaction trước khi ghi toàn bộ vào logs.

Không nên format lỗi bằng cách gọi một native function khác **trước khi đã lưu** mã lỗi gốc. Sau khi đã lưu thành số Java, có thể gọi `strerror`/`FormatMessage` hoặc thực hiện xử lý khác theo ownership/lifetime của chuỗi trả về. Tránh `reinterpret(Long.MAX_VALUE)` một pointer chuỗi tùy ý chỉ để đọc message nếu không biết bounds.

### 13.2. Chính sách retry dựa trên mã lỗi cụ thể

Không retry mọi lỗi chỉ vì `errno != 0`. Ví dụ POSIX:

- `EINTR`: nhiều hàm có thể bị ngắt bởi signal; có thể retry tùy contract và semantics.
- `EAGAIN`/`EWOULDBLOCK`: với nonblocking I/O, tình trạng “hiện không có dữ liệu/không sẵn sàng” có thể cần event loop thay vì busy loop.
- `ENOENT`: file không tồn tại không nhất thiết là lỗi tạm thời; retry mù quáng sẽ không sửa sai path.
- `EACCES`: thiếu quyền không nên lặp lại vô hạn.

Mã số và cách xử lý thuộc **hợp đồng native function và nền tảng**, không phải một policy chung cho mọi syscall. Không hardcode một số nguyên như `2` để đại diện `ENOENT` trên tất cả runtime; dùng biểu tượng/hàm chuyển đổi tương ứng khi có.

## 14. Điều đặc biệt cần tránh ở code nhiều downcall liên tiếp

### Anti-pattern A: kiểm tra errno trước return

```java
MemorySegment result =
        (MemorySegment) TMPFILE.invokeExact(state);
int errno = (int) ERRNO.get(state, 0L);

if (errno != 0) {
    throw new IllegalStateException("tmpfile failed");
}
// SAI: có thể ném dù result là pointer hợp lệ.
```

**Sửa:** chỉ khi `result.address() == 0` mới đọc lỗi và ném. Nếu pointer hợp lệ, dùng rồi `fclose` đúng lúc.

### Anti-pattern B: phân loại return status sai

```java
int fd = (int) OPEN.invokeExact(state, path, flags);
if (fd == 0) {  // SAI với POSIX open: fd = 0 có thể hợp lệ.
    throw new IOException("open failed");
}
```

**Sửa:** dựa trên `fd == -1` trong hợp đồng `open`. Snippet giả định C prototype/layout đúng và `OPEN` đã được liên kết, không phải chương trình đầy đủ.

### Anti-pattern C: gọi thêm native function trước khi lưu mã lỗi

```java
MemorySegment result =
        (MemorySegment) FOPEN.invokeExact(state, name, mode);

if (result.address() == 0) {
    // Một downcall khác dùng CÙNG state có thể ghi đè snapshot.
    doSomeOtherDowncall(state);
    int wrongErrno = (int) ERRNO.get(state, 0L);
}
```

**Sửa:** copy `int originalErrno = ...` **trước** mọi downcall tái sử dụng state. Lỗi này độc lập với lỗi đọc trực tiếp native errno sau return.

### Anti-pattern D: xem lỗi Java như lỗi C

```java
try {
    int value = (int) handle.invokeExact(...);
} catch (WrongMethodTypeException e) {
    // SAI: không thể giả định có errno hợp lệ của native call.
}
```

Mã trên là **pseudocode** cho một invocation không có context. Lỗi MethodHandle là vấn đề type signature/linking ở Java. Xử lý độc lập; không tạo báo cáo kiểu “native call errno = ...” khi native function có thể chưa chạy.

### Anti-pattern E: đọc GetLastError của một C runtime function

```text
fopen() trả NULL
    -> dùng errno của C runtime, theo hợp đồng fopen

GetFileAttributesW() trả INVALID_FILE_ATTRIBUTES
    -> dùng GetLastError của Win32, theo hợp đồng Win32

WinSock API trả socket sentinel
    -> dùng WSAGetLastError nếu API tài liệu hóa
```

Lẫn các error domains dễ dẫn đến mã lỗi **không liên quan** và chẩn đoán sai.

## 15. Checklist code review một wrapper downcall

1. **Prototypes:** `FunctionDescriptor` khớp tên hàm và ABI gốc chưa? Return là `ADDRESS`, `JAVA_INT`, `JAVA_LONG` hay struct?
2. **Native status contract:** API báo thành công/lỗi bằng `NULL`, `-1`, `0`, `HRESULT`, `INVALID_HANDLE_VALUE`, `size_t(-1)`, hay giá trị trực tiếp?
3. **EOF/partial:** 0 hoặc short result có ý nghĩa bình thường không? Có cần `feof`/`ferror` không?
4. **Error domain:** khi thất bại, nên dùng `errno`, `GetLastError`, `WSAGetLastError`, `EAI_*` hay output parameter riêng?
5. **Capture timing:** có `captureCallState("...")` cho kênh cần thiết để snapshot ngay sau downcall không? Hay C wrapper lưu đúng lúc?
6. **Buffer capture:** `state` có đúng `captureStateLayout()`, alignment và lifetime không? Có share across threads/calls mà không đồng bộ không?
7. **Parameter order:** MethodHandle có thêm `MemorySegment state` ở vị trí đúng sau bound/unbound function address không?
8. **Decision order:** code đã **kiểm tra result trước** rồi chỉ đọc mã lỗi nếu contract yêu cầu chưa?
9. **Preserve code:** nếu cần log/retry/call native tiếp, đã copy error code vào biến Java trước khi snapshot bị ghi đè chưa?
10. **Success path:** code có bị nhầm `errno != 0` hoặc `GetLastError != 0` là lỗi dù result thành công không?
11. **Ownership:** native call trả handle/pointer phải đóng/free bằng API nào, trong thời gian nào?
12. **Exceptions:** wrapper có phân biệt Java linking/memory exceptions với native error code hay không?
13. **Platforms:** liệu error names, codes, library symbols và native type sizes có thay đổi theo OS/ABI không?
14. **Tests:** có kiểm tra success, failure, nonzero stale error trên success, EOF/partial, invalid arguments và cleanup không?

## 16. Bài tập tự kiểm tra

**Câu 1.** `fopen` trả `FILE*` khác NULL nhưng buffer capture cho thấy `errno = 2`. Có nên ném exception “file không tồn tại” không?

**Đáp án:** Không. Theo hợp đồng `fopen`, pointer khác NULL là thành công. `errno` khác 0 trên thành công có thể là trạng thái cũ hoặc thay đổi không liên quan.

**Câu 2.** `fopen` trả NULL. Nên đọc gì và khi nào?

**Đáp án:** Native function đã báo thất bại, nên đọc `errno` đã **được FFM capture ngay sau lời gọi**, lưu thành `int`, rồi báo lỗi/throw theo chính sách.

**Câu 3.** `read` trả `0` trong POSIX I/O. Có nên ném exception vì `errno != 0` không?

**Đáp án:** Thông thường không. `read` trả 0 biểu thị EOF, không phải lỗi. Chỉ `-1` báo lỗi để dùng `errno`; xử lý khác nếu API cụ thể có ràng buộc riêng.

**Câu 4.** Một native `open` trả file descriptor `0`. Có hợp lệ không?

**Đáp án:** Có. FD 0 có thể được tái sử dụng; điều kiện lỗi là `-1` theo hợp đồng POSIX `open`.

**Câu 5.** `getaddrinfo` trả `EAI_NONAME`. Bạn có nên dùng `errno` để quyết định lỗi không?

**Đáp án:** Không. `getaddrinfo` trả `EAI_*` trực tiếp. Dùng mã trả về và `gai_strerror`; `errno` chỉ có ý nghĩa phụ trợ với một số mã như `EAI_SYSTEM`.

**Câu 6.** Vì sao `captureCallState("errno")` thêm một tham số vào `MethodHandle` mà không thêm tham số vào C function thật?

**Đáp án:** Tham số mới là `MemorySegment` do linker dùng làm **buffer snapshot execution state**. Với bound handle, nó đứng trước các đối số C; với unbound handle nó đứng sau địa chỉ function target.

**Câu 7.** Dùng `state.set(..., 0)` trước call có làm `errno` của native thread bằng 0 không?

**Đáp án:** Không. Đó chỉ là bộ đệm Java cho dữ liệu capture. Nếu hợp đồng cần reset native errno, phải thực hiện theo C/native runtime thực sự trên đúng thread.

**Câu 8.** Win32 `GetFileAttributesW` trả `-1` dạng Java `int`. Bạn nên dùng `GetLastError` hay `errno`?

**Đáp án:** `GetLastError` theo hợp đồng Win32, thông qua `captureCallState("GetLastError")`. `-1` biểu diễn `INVALID_FILE_ATTRIBUTES == 0xFFFFFFFF` của `DWORD`.

**Câu 9.** Một WinSock function báo lỗi theo `WSAGetLastError`. Bạn dùng `GetLastError` có luôn đúng không?

**Đáp án:** Không. Windows Sockets có kênh `WSAGetLastError` riêng; phải tra documentation của function đang gọi.

**Câu 10.** Bạn dùng lại cùng `MemorySegment callState` cho hai downcalls. Sau call thứ hai, phần `errno` trong buffer có nhất thiết là mã lỗi của call thứ nhất không?

**Đáp án:** Không. Downcall thứ hai với capture option có thể ghi đè. Lưu `int code = ...` từ call thứ nhất ngay sau khi xác định failure.

**Câu 11.** `tmpfile()` trả pointer hợp lệ và `errno` khác 0. Nên làm gì?

**Đáp án:** Coi `tmpfile` là thành công, dùng pointer và `fclose` đúng hạn. Không tự biến mã lỗi cũ thành exception.

**Câu 12.** Một `MethodHandle.invokeExact` ném `WrongMethodTypeException`. Có thể kết luận native function trả lỗi và đọc `errno` không?

**Đáp án:** Không. Đây là lỗi Java signature, native call có thể chưa được thực hiện. Phải sửa descriptor/cast/invocation.

**Câu 13.** Khi `strtol` có thể trả một giá trị trùng sentinel lỗi, có thể chỉ dựa trên `result == -1` không?

**Đáp án:** Không. Cần hợp đồng `strtol` về `errno`/`ERANGE`, `endptr` và có thể cần reset native errno trước call; đồng thời phải map đúng C `long` theo ABI.

**Câu 14.** Vì sao mã lỗi được capture kịp thời vẫn không tự trở thành một Java exception?

**Đáp án:** FFM chỉ mang số native error state vào buffer. Java wrapper phải đọc **result theo contract**, rồi quyết định báo lỗi, retry, trả `Optional.empty`, hoặc chuyển thành exception.

## 17. Tóm tắt cuối bài

- **Return value là điểm khởi đầu.** Hãy đọc “Return value / Errors” của đúng native function và xác định sentinel, EOF, partial result hoặc mã lỗi trực tiếp.
- **errno/GetLastError không phải boolean failure flag.** Có thể khác 0 dù call thành công; không dùng riêng lẻ để phân loại.
- **captureCallState chụp kịp thời**, nhưng **đọc/diễn giải có điều kiện** theo native result.
- **Khi call thất bại**, lưu mã lỗi trong một biến Java trước khi dùng lại capture buffer hoặc gọi native API khác.
- **Không trộn error domains:** C `errno`, Win32 `GetLastError`, WinSock `WSAGetLastError`, `EAI_*`, `HRESULT` và Java exception thuộc những hợp đồng khác nhau.
- **FFM không tự đóng handle**, không tự ném exception theo mọi C sentinel, và không bảo đảm memory safety nếu FunctionDescriptor/ABI bị khai báo sai.
- **Testing tốt** phải có trường hợp thành công với mã lỗi cũ khác 0, không chỉ thử một failure case.

## Tài liệu tham khảo đáng tin cậy

- [Oracle Java SE 24 — Checking for Native Errors Using errno](https://docs.oracle.com/en/java/javase/24/core/checking-native-errors-using-errno.html)
- [Oracle Java SE 24 — Linker.Option.captureCallState / captureStateLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Oracle Java SE 24 — Linker và downcallHandle](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 24 — FFM API Overview](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html)
- [man7.org — errno(3), khi nào errno có nghĩa và errno trên success](https://man7.org/linux/man-pages/man3/errno.3.html)
- [man7.org — fopen(3), FILE* hoặc NULL](https://man7.org/linux/man-pages/man3/fopen.3.html)
- [man7.org — getaddrinfo(3), trả EAI_* trực tiếp](https://man7.org/linux/man-pages/man3/getaddrinfo.3.html)
- [Microsoft Learn — GetLastError, điều kiện và thời điểm đọc](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror)
- [Microsoft Learn — GetFileAttributesW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileattributesw)
- [Microsoft Learn — CloseHandle return value](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle)
- [Microsoft Learn — WSAGetLastError](https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-wsagetlasterror)
- [JEP 454 — Foreign Function & Memory API, final from JDK 22](https://openjdk.org/jeps/454)

**Kết luận:** trong FFM, **mã lỗi chỉ có nghĩa trong điều kiện do hợp đồng của chính native function đặt ra**. Hãy kiểm tra return value đầu tiên; khi nó báo lỗi mới đọc đúng trạng thái đã được `captureCallState` lưu, rồi báo lỗi và cleanup phù hợp. **Bắt đầu từ return contract, không bắt đầu từ errno.**
