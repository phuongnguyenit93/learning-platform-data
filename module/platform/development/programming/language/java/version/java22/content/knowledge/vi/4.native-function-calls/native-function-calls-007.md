# Nhận kết quả trong vùng nhớ do bên gọi cấp phát và xác định trách nhiệm giải phóng

Khi gọi hàm native bằng Foreign Function & Memory API (FFM), một cách trao đổi dữ liệu phổ biến là **Java cấp phát vùng nhớ trước, truyền địa chỉ và sức chứa cho hàm native, rồi đọc kết quả ngay trên vùng nhớ đó**. Cách làm này thường được gọi là caller-allocated output buffer hoặc output parameter.

Điểm quan trọng là phải xác định rõ ai sở hữu vùng nhớ. Nếu Java cấp phát bằng `Arena`, Java quản lý vòng đời và giải phóng vùng nhớ khi đóng arena. Hàm native chỉ ghi dữ liệu vào vùng nhớ được mượn theo hợp đồng của lời gọi; nó không được tự ý giải phóng hoặc tiếp tục giữ con trỏ sau khi lời gọi kết thúc. Nếu chính hàm native cấp phát kết quả, Java phải gọi đúng hàm giải phóng do thư viện quy định.

Bài học sử dụng FFM API ổn định trong package `java.lang.foreign`, được chuẩn hóa từ Java 22 qua JEP 454. Các ví dụ dùng `Arena`, `MemorySegment`, `Linker`, `SymbolLookup` và `FunctionDescriptor`; không dùng API incubator cũ.

## 1. Hai kiểu hợp đồng trả kết quả từ hàm native

Hàm native có thể cung cấp dữ liệu đầu ra theo hai mô hình chính:

| Mô hình | Cách hoạt động | Trách nhiệm giải phóng |
|---|---|---|
| Bên gọi cấp phát (caller-allocated) | Java tạo buffer hoặc cấu trúc trong `Arena`, truyền địa chỉ và thường cả capacity cho native function. Hàm native ghi kết quả vào đó. | Java đóng `Arena` sau khi không còn sử dụng vùng nhớ. Native function không được `free` vùng nhớ này. |
| Bên được gọi cấp phát (callee-allocated) | Native function tự cấp phát, rồi trả về con trỏ hoặc ghi con trỏ vào output parameter. | Java phải gọi đúng hàm release/destroy do thư viện cung cấp, theo đúng allocator đã cấp phát. Đóng `Arena` Java không tự giải phóng vùng nhớ native đó. |

Hai mô hình có thể cùng xuất hiện trong một API. Chẳng hạn, hàm có thể nhận một buffer do Java cấp phát nhưng đồng thời trả về số byte đã ghi; hoặc hàm có thể trả về một con trỏ tới đối tượng mà thư viện tự tạo. Cần đọc hợp đồng native API để xác định trường hợp đang dùng.

## 2. Mô hình caller-allocated output buffer

Giả sử thư viện C cung cấp hàm:

```c
int32_t write_message(char *destination, int32_t capacity);
```

Hợp đồng của hàm:

- `destination` trỏ tới buffer do bên gọi cấp phát.
- `capacity` là số byte tối đa mà hàm được phép ghi, bao gồm byte null kết thúc chuỗi C.
- Khi thành công, hàm ghi chuỗi UTF-8 kết thúc bằng `\0` vào buffer và trả về số byte nội dung, không tính byte null.
- Khi buffer không đủ lớn hoặc con trỏ không hợp lệ, hàm trả về số âm và không ghi dữ liệu vượt giới hạn.
- Hàm chỉ sử dụng con trỏ trong thời gian thực thi lời gọi; không giữ lại con trỏ và không giải phóng buffer.

Đây là hợp đồng quan trọng hơn bản thân cú pháp FFM. FFM giúp Java truyền địa chỉ và quản lý vòng đời vùng nhớ, nhưng không thể tự sửa một native function ghi vượt capacity hoặc sử dụng con trỏ sau khi Java đã đóng arena.

## 3. Ví dụ native function ghi vào buffer do Java cấp phát

### Phần C: ghi dữ liệu vào buffer

File `message.c`:

```c
#include <stdint.h>
#include <string.h>

int32_t write_message(char *destination, int32_t capacity) {
    static const char message[] = "Hello from native code";
    const int32_t required = (int32_t) sizeof(message);

    if (destination == NULL || capacity < required) {
        return -1;
    }

    // sizeof(message) bao gồm cả byte '\0' ở cuối.
    memcpy(destination, message, sizeof(message));

    // Trả về số byte nội dung, không tính byte '\0'.
    return (int32_t) (sizeof(message) - 1);
}
```

Hàm nhận một con trỏ và capacity. `memcpy` chỉ ghi khi capacity đủ chứa toàn bộ chuỗi cùng byte kết thúc. Hàm không gọi `malloc` và cũng không gọi `free`, bởi buffer thuộc về bên gọi.

Ví dụ này dùng `int32_t` cho capacity và giá trị trả về để ánh xạ trực tiếp sang `ValueLayout.JAVA_INT`. Với API thực tế dùng `size_t`, `long`, `wchar_t` hoặc kiểu phụ thuộc nền tảng, phải ánh xạ đúng kích thước, alignment và ABI của hệ điều hành/compiler; không mặc định mọi kiểu C đều tương ứng với cùng một kiểu Java.

### Phần Java: cấp phát, truyền địa chỉ và đọc kết quả

File `NativeBufferDemo.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class NativeBufferDemo {
    private static final int CAPACITY = 128;

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Arena quản lý cả buffer và vòng đời thư viện được nạp.
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                Path.of("./libmessage.so").toAbsolutePath(), arena
            );

            MemorySegment symbol = library.find("write_message")
                .orElseThrow(() -> new IllegalStateException("Missing write_message"));

            MethodHandle writeMessage = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,  // int32_t return value
                    ValueLayout.ADDRESS,   // char *destination
                    ValueLayout.JAVA_INT   // int32_t capacity
                )
            );

            // Java cấp phát 128 byte và giữ quyền sở hữu buffer.
            MemorySegment output = arena.allocate(CAPACITY);

            // Truyền địa chỉ buffer cùng capacity cho hàm native.
            int written = (int) writeMessage.invokeExact(output, CAPACITY);

            if (written < 0 || written >= CAPACITY) {
                throw new IllegalStateException("Native function failed or returned an invalid length");
            }

            // Kiểm tra byte null kết thúc trước khi đọc chuỗi C.
            if (output.get(ValueLayout.JAVA_BYTE, written) != 0) {
                throw new IllegalStateException("Native function did not terminate the string");
            }

            String message = output.getString(0);
            System.out.println("Bytes written: " + written);
            System.out.println("Message: " + message);
        }
        // Khi thoát try, Arena giải phóng buffer và đóng library lookup.
    }
}
```

Trong ví dụ này, `FunctionDescriptor` mô tả chính xác chữ ký C: trả về `int32_t`, nhận `char *` và `int32_t`. `MethodHandle` được tạo bởi `downcallHandle` có kiểu gọi tương ứng với `MemorySegment` và `int` ở phía Java.

`arena.allocate(CAPACITY)` cấp phát vùng nhớ native do arena quản lý. Khi truyền `output` vào vị trí `ADDRESS`, FFM chuyển segment thành địa chỉ mà hàm C có thể ghi. Java đọc dữ liệu trước khi đóng arena; sau khi khối `try` kết thúc, segment không còn hợp lệ.

Trên Linux có thể biên dịch thư viện mẫu bằng:

```bash
cc -shared -fPIC -o libmessage.so message.c
javac NativeBufferDemo.java
java --enable-native-access=ALL-UNNAMED NativeBufferDemo
```

Tên file thư viện và tùy chọn tạo shared library khác nhau theo hệ điều hành. Ví dụ Java dùng `libmessage.so` cho Linux; khi chạy trên macOS hoặc Windows, thay bằng tên thư viện tương ứng. `--enable-native-access=ALL-UNNAMED` cấp native access cho mã chạy trên classpath; với ứng dụng module, hãy cấp quyền cho đúng module cần gọi native code.

Kết quả dự kiến:

```text
Bytes written: 22
Message: Hello from native code
```

Giá trị byte được trả về không bao gồm byte null cuối chuỗi. Java kiểm tra giá trị đó nằm trong giới hạn buffer và kiểm tra terminator trước khi gọi `getString(0)`. Việc kiểm tra phía Java không thể ngăn native code ghi tràn bộ nhớ; hàm C vẫn phải tuân thủ capacity như hợp đồng đã nêu.

## 4. Ai sở hữu và ai giải phóng buffer?

Trong ví dụ trên, quyền sở hữu được phân chia như sau:

| Tài nguyên | Bên tạo/cấp phát | Bên được phép giải phóng | Thời điểm hợp lệ |
|---|---|---|---|
| `MemorySegment output` | Java qua `Arena.allocate` | `Arena` giải phóng khi đóng | Native function chỉ ghi trong thời gian buffer còn sống. |
| Shared library | `SymbolLookup.libraryLookup` nạp vào tiến trình | Arena gắn với library lookup quản lý vòng đời nạp thư viện | Không đóng arena/unload thư viện khi vẫn còn gọi function handle hoặc native code cần thư viện. |
| Chuỗi C ghi trong output | Native function ghi vào buffer Java đã cấp | Không có thao tác `free` riêng; buffer vẫn thuộc arena | Java đọc hoặc sao chép dữ liệu trước khi arena đóng. |

Quy tắc cần nhớ:

1. Java cấp phát thì Java quản lý vòng đời. Native function chỉ mượn địa chỉ theo hợp đồng.
2. Native function không được gọi `free(destination)` với buffer do Java/Arena cấp phát.
3. Java không được tiếp tục đọc hoặc truyền segment sau khi arena đã đóng.
4. Nếu cần giữ kết quả lâu hơn, hãy sao chép sang bộ nhớ Java như `String` hoặc `byte[]` trước khi đóng arena.
5. Nếu native function giữ con trỏ để dùng bất đồng bộ sau khi trả về, arena phải còn sống trong toàn bộ thời gian đó. Không được đóng arena trong khi native code vẫn có thể truy cập buffer.

`Arena.ofConfined()` phù hợp khi một thread cấp phát, gọi native function và đọc kết quả. Nếu vùng nhớ phải được truy cập từ nhiều thread, có thể cân nhắc `Arena.ofShared()` và đồng thời thiết kế đồng bộ hóa, quyền sở hữu cũng như thời điểm đóng arena. Shared arena không tự làm cho truy cập đồng thời vào buffer trở nên an toàn.

## 5. Khi native function tự cấp phát kết quả

Một số thư viện không nhận buffer từ caller. Thay vào đó, hàm native gọi `malloc` hoặc allocator riêng rồi trả về con trỏ. Khi đó, trách nhiệm giải phóng thay đổi:

```c
#include <stdlib.h>
#include <string.h>

char *create_message(void) {
    const char message[] = "Created by native code";
    char *result = malloc(sizeof(message));
    if (result == NULL) {
        return NULL;
    }
    memcpy(result, message, sizeof(message));
    return result;
}

void destroy_message(char *result) {
    free(result);
}
```

Trong hợp đồng này, `create_message` tạo vùng nhớ và chuyển quyền quản lý cho bên gọi theo quy ước của thư viện. Java phải gọi `destroy_message` đúng một lần cho kết quả hợp lệ, sau khi đã đọc hoặc sao chép dữ liệu. Nên ưu tiên hàm `destroy` do chính thư viện cung cấp vì allocator có thể khác nhau giữa runtime C, compiler hoặc module native.

Không được giả định rằng đóng `Arena` sẽ gọi `free` trên mọi con trỏ do native function trả về. Arena chỉ quản lý vùng nhớ mà nó cấp phát hoặc tài nguyên được đăng ký theo cơ chế quản lý vòng đời của nó. Một con trỏ do `malloc` trong thư viện C trả về phải được giải phóng bằng allocator tương ứng.

Nếu API native vừa trả con trỏ vừa trả kích thước, Java phải dùng đúng kích thước đó khi tạo view để đọc dữ liệu, đồng thời xác minh con trỏ không null và kích thước hợp lệ. Khi API cung cấp chuỗi C kết thúc null, vẫn phải bảo đảm chuỗi có terminator trong vùng nhớ hợp lệ trước khi đọc. Không đọc một địa chỉ tùy ý với giả định rằng luôn tồn tại byte kết thúc.

Trình tự vòng đời cho kết quả do native cấp phát thường là:

1. Gọi hàm native để nhận con trỏ và kích thước.
2. Kiểm tra trạng thái lỗi, con trỏ null và kích thước theo hợp đồng.
3. Đọc hoặc sao chép dữ liệu trong khi vùng nhớ còn hợp lệ.
4. Gọi hàm release/destroy tương ứng đúng một lần, kể cả khi bước đọc gặp lỗi (thường đặt thao tác release trong `finally`).
5. Chỉ sau đó mới đóng arena hoặc giải phóng tài nguyên quản lý thư viện nếu không còn sử dụng.

Nếu API không tài liệu hóa cách giải phóng, cần tra hợp đồng thư viện trước khi sử dụng; không đoán allocator từ kiểu con trỏ.

## 6. Trường hợp output là struct hoặc mảng

Caller-allocated output không chỉ dành cho chuỗi. Native function có thể ghi một cấu trúc C hoặc nhiều phần tử vào buffer:

```c
#include <stdint.h>

struct Point {
    int32_t x;
    int32_t y;
};

int32_t read_point(struct Point *out_point) {
    if (out_point == NULL) {
        return -1;
    }
    out_point->x = 10;
    out_point->y = 20;
    return 0;
}
```

Phía Java cần mô tả struct bằng `MemoryLayout.structLayout(...)` với đúng thứ tự trường, kích thước, alignment và padding theo ABI của native compiler. Sau đó cấp phát segment có kích thước tương ứng, truyền địa chỉ cho hàm, rồi đọc các trường bằng `VarHandle` hoặc layout path. Không tự giả định rằng struct C luôn được đóng gói giống các trường Java liền nhau; compiler có thể chèn padding để đáp ứng alignment.

Với output là mảng, caller thường truyền thêm capacity hoặc số phần tử. Native function phải kiểm tra giới hạn trước khi ghi. Java cần xác minh số phần tử thực tế được trả về không vượt quá số phần tử đã cấp phát trước khi duyệt segment.

## 7. Những lỗi quản lý bộ nhớ thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Buffer quá nhỏ | Native code ghi vượt vùng nhớ, có thể làm hỏng tiến trình. | Truyền capacity và yêu cầu native function kiểm tra trước khi ghi. |
| Đọc kết quả sau khi đóng arena | Truy cập segment đã hết vòng đời. | Đọc hoặc sao chép kết quả trước khi đóng arena. |
| Gọi `free` trên buffer do Java cấp phát | Giải phóng sai allocator, gây undefined behavior. | Để arena quản lý segment của nó. |
| Không gọi hàm destroy cho vùng nhớ do native cấp | Rò rỉ bộ nhớ native. | Gọi đúng hàm release theo tài liệu thư viện, thường trong `finally`. |
| Gọi destroy hai lần | Double-free và có thể làm hỏng heap native. | Theo dõi rõ quyền sở hữu và chỉ release một lần. |
| Native giữ con trỏ sau khi lời gọi kết thúc | Use-after-free nếu arena đã đóng. | Không để native giữ pointer, hoặc giữ arena sống đến khi native hoàn tất. |
| Dùng sai layout/ABI | Đọc sai dữ liệu, sai alignment hoặc crash. | Ánh xạ đúng kiểu C, kích thước, alignment, padding và calling convention. |
| Giả định FFM kiểm soát mọi truy cập native | Native code vẫn có thể ghi sai địa chỉ hoặc vượt buffer. | Xem native library là mã có quyền truy cập bộ nhớ tiến trình và xác thực hợp đồng. |

## 8. Checklist trước khi gọi native function

- Xác định rõ buffer do Java hay native code cấp phát.
- Xác định capacity tính theo byte hay phần tử, có bao gồm byte null kết thúc hay không.
- Kiểm tra chữ ký hàm, kiểu trả về và layout theo ABI của nền tảng.
- Chỉ truyền segment còn sống và có quyền truy cập phù hợp.
- Xác minh trạng thái trả về và số byte/phần tử đã ghi trước khi đọc.
- Sao chép dữ liệu sang vùng nhớ Java nếu cần giữ sau khi arena đóng.
- Nếu native code cấp phát, xác định chính xác hàm destroy và gọi đúng một lần.
- Bảo đảm native code không giữ con trỏ vượt quá vòng đời buffer.
- Cấp native access cho đúng module hoặc classpath cần gọi FFM restricted operations.

## 9. Kết luận

Với output buffer do caller cấp phát, Java dùng `Arena` để tạo vùng nhớ, truyền `MemorySegment` cho downcall và đọc kết quả khi arena còn mở. Native function chỉ mượn địa chỉ, phải tuân thủ capacity và không được tự giải phóng buffer. Khi native function tự cấp phát, quyền giải phóng thuộc về hợp đồng native API; Java phải gọi đúng hàm release của cùng thư viện thay vì trông đợi `Arena` tự thu hồi vùng nhớ đó.

Nắm chắc quyền sở hữu, capacity, ABI và vòng đời của con trỏ là điều kiện quan trọng để dùng FFM an toàn. FFM cung cấp các công cụ quản lý vùng nhớ có cấu trúc, nhưng ranh giới native vẫn đòi hỏi lập trình viên tuân thủ chính xác hợp đồng của thư viện được gọi.

## Tài liệu tham khảo

- [JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Foreign Function and Memory API – Java SE 25](https://docs.oracle.com/en/java/javase/25/core/foreign-function-and-memory-api.html)
- [Arena – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [MemorySegment – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Linker – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [SymbolLookup – Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
