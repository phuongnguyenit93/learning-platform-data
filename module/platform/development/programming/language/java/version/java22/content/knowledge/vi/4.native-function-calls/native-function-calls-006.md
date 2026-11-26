# Mã hóa chuỗi, ký tự kết thúc và quản lý buffer khi giao tiếp với mã native

Khi Java gọi một hàm native thông qua Foreign Function & Memory API (FFM API), hai phía phải thống nhất cách biểu diễn dữ liệu trong bộ nhớ. Với chuỗi, điều này đặc biệt quan trọng: Java dùng `String` với văn bản Unicode, còn hàm C thường nhận `char *` trỏ tới dãy byte và có thể mong đợi một ký tự kết thúc NUL (`'\0'`). Nếu mã hóa, kích thước buffer hoặc vòng đời vùng nhớ không đúng, native code có thể đọc sai dữ liệu, cắt mất chuỗi hoặc truy cập ngoài vùng nhớ.

FFM API chính thức từ JDK 22 cung cấp `Arena`, `MemorySegment`, `MemoryLayout`, `Linker` và `SymbolLookup` để quản lý vùng nhớ và liên kết hàm native. Bài này tập trung vào cách chuyển chuỗi, bảo đảm ký tự kết thúc và tổ chức buffer an toàn khi gọi hàm native. Các ví dụ dùng API trong `java.lang.foreign` đã được chuẩn hóa qua JEP 454; không dùng các API incubator hoặc preview đời cũ.

## 1. Khác biệt giữa chuỗi Java và chuỗi C

Java `String` biểu diễn văn bản Unicode. Khi chuyển văn bản thành dữ liệu byte, chương trình phải chọn một charset, chẳng hạn UTF-8. Trong khi đó, tham số `char *` của C chỉ là địa chỉ tới byte đầu tiên; bản thân kiểu con trỏ không cho biết charset hoặc độ dài chuỗi.

Nhiều API C quy ước chuỗi kết thúc bằng byte NUL có giá trị `0`. Hàm native đọc từng byte cho tới khi gặp NUL. Vì vậy, một C string thường có dạng:

```text
byte 0   byte 1   byte 2   ...   byte n   byte n+1
  H        i        !       ...    ...       NUL (0)
```

Một số điểm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Java `char` | Một code unit UTF-16, rộng 16 bit. |
| C `char` | Một đơn vị byte, thường dùng để chứa byte của chuỗi đã mã hóa. |
| UTF-8 | Charset mã hóa Unicode thành chuỗi byte có độ dài thay đổi. |
| NUL terminator | Byte `0` kết thúc C string; không phải dấu kết thúc chuỗi Java. |
| Buffer capacity | Tổng số byte vùng nhớ có thể chứa, thường phải tính cả byte NUL. |

Không được giả định rằng một ký tự Unicode luôn chiếm một byte hoặc một `char` Java tương ứng với một `char` C. Ví dụ, ký tự tiếng Việt có dấu có thể chiếm nhiều byte khi mã hóa UTF-8.

## 2. Chọn charset theo hợp đồng của API native

Charset phải được xác định từ tài liệu của thư viện native. UTF-8 là lựa chọn phổ biến cho API mới, nhưng không phải mọi thư viện C đều dùng UTF-8. Một số API cũ có thể sử dụng encoding theo locale hoặc một encoding riêng của nền tảng.

Trong Java, nên biểu thị charset tường minh:

```java
import java.nio.charset.StandardCharsets;

String text = "Xin chào từ Java";
```

Nếu native API yêu cầu UTF-8, dùng `StandardCharsets.UTF_8` khi cấp phát chuỗi và khi đọc kết quả. Tránh phụ thuộc vào charset mặc định của máy vì chương trình có thể chạy trên hệ điều hành hoặc cấu hình locale khác nhau.

Một C string không thể biểu diễn đầy đủ một giá trị Java `String` có chứa ký tự NUL (`'\0'`) theo quy ước kết thúc NUL: phía C sẽ xem byte NUL đầu tiên là điểm kết thúc. Nếu dữ liệu có thể chứa NUL hoặc dữ liệu nhị phân, nên dùng giao thức truyền con trỏ kèm độ dài thay vì C string.

## 3. Chuyển Java String thành C string với `Arena.allocateFrom(...)`

FFM API cung cấp `Arena.allocateFrom(String, Charset)` để mã hóa chuỗi, cấp phát vùng nhớ native vừa đủ và thêm ký tự kết thúc theo charset. Phiên bản không nhận charset sử dụng UTF-8; với UTF-8, terminator là một byte NUL. Truyền charset tường minh giúp hợp đồng dữ liệu dễ nhận biết hơn.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.charset.StandardCharsets;

public class EncodeCString {
    public static void main(String[] args) {
        String message = "Xin chào từ Java";

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom(
                    message, StandardCharsets.UTF_8);

            System.out.println("Số byte đã cấp phát: " + cString.byteSize());
            System.out.println("Đọc lại: " + cString.getString(
                    0, StandardCharsets.UTF_8));
        }
    }
}
```

`allocateFrom(...)` trả về một `MemorySegment` chứa byte đã mã hóa và terminator ở cuối. Với UTF-8, kích thước segment là số byte đã mã hóa cộng thêm một byte NUL. Do UTF-8 dùng số byte thay đổi theo ký tự, không thể tính dung lượng bằng `message.length() + 1` một cách chính xác. Với charset khác, kích thước terminator phụ thuộc vào charset đó; C API nhận `char *` thông thường cần thống nhất một encoding byte như UTF-8.

`Arena.ofConfined()` quản lý vùng nhớ native và giải phóng vùng nhớ khi arena được đóng. `try`-with-resources bảo đảm arena được đóng kể cả khi có ngoại lệ. Trong ví dụ, segment chỉ được dùng bên trong khối `try`.

### Kiểm tra byte kết thúc

Nếu cần xác minh buffer có NUL ở cuối, có thể đọc byte cuối cùng:

```java
long lastByteOffset = cString.byteSize() - 1;
byte terminator = cString.get(java.lang.foreign.ValueLayout.JAVA_BYTE,
        lastByteOffset);

if (terminator != 0) {
    throw new IllegalStateException("C string is not NUL-terminated");
}
```

Đối với chuỗi rỗng, `allocateFrom(...)` vẫn cấp phát byte NUL nên segment có kích thước ít nhất một byte.

## 4. Gọi hàm native nhận `const char *`

Ví dụ đơn giản dưới đây dùng hàm C chuẩn `puts` với chữ ký:

```c
int puts(const char *message);
```

Hàm nhận một con trỏ tới C string, in chuỗi ra standard output, thêm newline và trả về `int`. Với FFM API, có thể mô tả hàm bằng `FunctionDescriptor`, tìm symbol bằng `SymbolLookup` rồi tạo downcall handle bằng `Linker`.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;

public class CallNativeWithCString {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = linker.defaultLookup();

        MethodHandle printMessage = linker.downcallHandle(
                symbols.find("puts").orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.ADDRESS
                )
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment message = arena.allocateFrom(
                    "Hello from Java",
                    StandardCharsets.UTF_8
            );

            int result = (int) printMessage.invokeExact(message);
            if (result < 0) {
                throw new IllegalStateException("Native puts failed");
            }
        }
    }
}
```

`puts` là hàm C chuẩn nhận `const char *`, in chuỗi ra standard output và thêm newline. `ValueLayout.ADDRESS` mô tả tham số con trỏ; trong downcall handle, tham số này được biểu diễn bằng `MemorySegment`. `ValueLayout.JAVA_INT` mô tả kiểu trả về C `int` trong ví dụ.

Tạo downcall handle bằng `Linker.downcallHandle(...)` là thao tác restricted; `SymbolLookup.libraryLookup(...)` ở ví dụ tiếp theo cũng là restricted. Với mã chạy trong unnamed module, có thể bật quyền native access cho chương trình bằng:

```bash
java --enable-native-access=ALL-UNNAMED -cp out CallNativeWithCString
```

`defaultLookup()` tìm symbol trong các thư viện được nạp mặc định bởi runtime. Hàm `puts` thường được cung cấp bởi C runtime; với hàm thuộc thư viện riêng, cần nạp thư viện bằng `SymbolLookup.libraryLookup(...)` và tìm symbol trong lookup tương ứng.

## 5. Nạp thư viện native và gọi hàm trong thư viện riêng

Giả sử thư viện `message` xuất hàm C sau:

```c
int write_greeting(char *buffer, int capacity);
```

Hợp đồng của hàm ví dụ:

- Ghi nội dung UTF-8 vào `buffer`.
- Ghi thêm byte NUL sau byte cuối của nội dung.
- `capacity` là tổng số byte khả dụng, bao gồm vị trí dành cho NUL.
- Trả về số byte nội dung, không tính NUL; trả về `-1` nếu buffer không đủ.

Một phần triển khai C đáp ứng hợp đồng đó:

```c
#include <string.h>

int write_greeting(char *buffer, int capacity) {
    static const char message[] = "Xin chao";
    int length = (int) sizeof(message) - 1;

    if (capacity < (int) sizeof(message)) {
        return -1;
    }

    memcpy(buffer, message, sizeof(message)); /* includes the NUL byte */
    return length;
}
```

Mã Java có thể nạp thư viện và tạo downcall handle như sau:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ReadNativeBuffer {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            Path libraryPath = Path.of(
                    System.getProperty("user.dir"),
                    System.mapLibraryName("message")
            );
            SymbolLookup library = SymbolLookup.libraryLookup(
                    libraryPath, arena);

            MethodHandle writeGreeting = linker.downcallHandle(
                    library.find("write_greeting").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT
                    )
            );

            int capacity = 256;
            MemorySegment buffer = arena.allocate(capacity, 1);

            int written = (int) writeGreeting.invokeExact(buffer, capacity);
            if (written < 0 || written >= capacity) {
                throw new IllegalStateException(
                        "Native function failed or returned an invalid length");
            }

            byte terminator = buffer.get(ValueLayout.JAVA_BYTE, written);
            if (terminator != 0) {
                throw new IllegalStateException(
                        "Native function did not write the NUL terminator");
            }

            String message = buffer.getString(
                    0, StandardCharsets.UTF_8);
            System.out.println(message);
        }
    }
}
```

Tên file thư viện phụ thuộc nền tảng, vì vậy `System.mapLibraryName("message")` tạo tên phù hợp như `message.dll`, `libmessage.so` hoặc `libmessage.dylib`. Đường dẫn trong ví dụ giả định file thư viện nằm ở thư mục làm việc hiện tại; dự án thật nên truyền đường dẫn đã được cấu hình rõ ràng.

Biên dịch và chạy lớp Java (sau khi đã build thư viện native đúng tên và đặt vào thư mục làm việc):

```bash
javac --release 22 -d out src/ReadNativeBuffer.java
java --enable-native-access=ALL-UNNAMED -cp out ReadNativeBuffer
```

Trong ví dụ, cùng một arena quản lý cả thư viện đã nạp và buffer native. Khi arena đóng, các tài nguyên gắn với arena được giải phóng theo hợp đồng API. Vì vậy, chỉ sử dụng symbol và buffer trong phạm vi arena còn sống.

`arena.allocate(capacity, 1)` cấp phát buffer có kích thước 256 byte và alignment 1, phù hợp với một dãy byte. Buffer cần có ít nhất `written + 1` byte để chứa nội dung và NUL. Việc kiểm tra `written < capacity` cùng byte kết thúc bảo đảm `getString(...)` không phải đọc vượt quá vùng buffer trong hợp đồng hàm ví dụ.

## 6. Tự cấp phát buffer và quản lý kích thước

Khi native code ghi dữ liệu vào buffer do Java cấp phát, Java phải biết hoặc xác định được dung lượng cần thiết. Có ba cách thiết kế API thường gặp:

| Kiểu API native | Cách quản lý phía Java |
| --- | --- |
| Kích thước đầu ra tối đa đã biết | Cấp phát buffer đủ lớn theo giới hạn tài liệu. |
| Hàm nhận buffer và capacity | Truyền capacity; kiểm tra mã trả về và không cho native ghi vượt giới hạn. |
| Hàm hỗ trợ truy vấn kích thước trước | Gọi lần đầu để lấy kích thước, cấp phát buffer, rồi gọi lần tiếp theo để ghi dữ liệu. |

Nếu thư viện dùng quy ước trả về số byte cần thiết khi buffer quá nhỏ, hãy đọc kỹ tài liệu để phân biệt số byte gồm hay không gồm NUL. Không được tự suy đoán quy ước đó. Khi tính dung lượng cho C string, phải dành thêm một byte NUL nếu API yêu cầu chuỗi kết thúc bằng NUL.

Không nên chỉ dựa vào giá trị native trả về mà bỏ qua giới hạn segment. Mọi offset và độ dài dùng để đọc kết quả phải nằm trong `buffer.byteSize()`. Nếu native API không bảo đảm giới hạn ghi, Java không thể dùng `MemorySegment` để ngăn một hàm C ghi vượt khỏi buffer qua con trỏ thô; cần sửa hợp đồng native hoặc dùng wrapper C kiểm tra dung lượng.

## 7. Chuỗi có độ dài tường minh và dữ liệu nhị phân

Không phải API native nào cũng dùng NUL-terminated string. Một số API nhận cặp `const char *data, size_t length`. Cách này phù hợp hơn khi:

- Chuỗi có thể chứa byte NUL ở giữa.
- Dữ liệu có thể là binary, không phải văn bản.
- Phía gửi đã biết chính xác số byte.
- API muốn tránh việc native quét bộ nhớ để tìm ký tự kết thúc.

Với dạng API này, có thể mã hóa chuỗi thành byte array bằng Java rồi chép vào segment native:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.charset.StandardCharsets;

String text = "Xin chào";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment bytes = arena.allocate(encoded.length, 1);
    bytes.copyFrom(MemorySegment.ofArray(encoded));

    // Truyền `bytes` và encoded.length tới hàm native nhận pointer + length.
}
```

Ở ví dụ này, buffer chứa đúng các byte UTF-8 và không thêm NUL. Độ dài truyền sang native là `encoded.length`, tức số byte, không phải `text.length()` (số UTF-16 code unit). Kiểu của tham số độ dài phải khớp chữ ký C thực tế; nếu C dùng `size_t`, cần dùng canonical layout `size_t` của `Linker` thay vì mặc định rằng nó luôn là `int` hoặc `long` trên mọi nền tảng.

Khi native trả về một pointer cùng độ dài, hãy xử lý theo hợp đồng quyền sở hữu và vòng đời của pointer. Không được tự ý đóng hoặc giải phóng vùng nhớ mà thư viện native sở hữu; cần dùng hàm release tương ứng của thư viện nếu tài liệu yêu cầu.

## 8. Giữ buffer sống đủ lâu

Thời gian sống của `MemorySegment` phải bao phủ toàn bộ thời gian native code sử dụng địa chỉ của nó.

### Native chỉ dùng pointer trong lúc lời gọi đang chạy

Đây là trường hợp đơn giản nhất. Buffer có thể được cấp phát trong `Arena.ofConfined()` bao quanh lời gọi downcall. Khi hàm trả về, native code không còn được phép giữ hoặc sử dụng pointer đó.

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment input = arena.allocateFrom("request", StandardCharsets.UTF_8);
    callNativeSynchronously(input);
}
```

### Native giữ pointer để dùng sau khi hàm trả về

Nếu thư viện lưu pointer để xử lý bất đồng bộ hoặc dùng trong callback sau này, arena cục bộ sẽ đóng quá sớm. Cần chọn arena có vòng đời dài hơn, chẳng hạn `Arena.ofShared()` nếu segment phải được truy cập từ nhiều thread, và chỉ đóng arena sau khi thư viện đã ngừng sử dụng pointer.

```java
Arena sharedArena = Arena.ofShared();
MemorySegment persistentInput = sharedArena.allocateFrom(
        "long-lived request", StandardCharsets.UTF_8);

registerNativeCallback(persistentInput);

// Chỉ gọi sau khi native library xác nhận không còn giữ pointer.
// sharedArena.close();
```

Đoạn mã trên minh họa vòng đời; ứng dụng phải có cơ chế đồng bộ để biết thời điểm an toàn gọi `close()`. Nếu đóng arena khi native vẫn giữ pointer, lần truy cập sau có thể thất bại hoặc gây lỗi bộ nhớ tùy cách thư viện sử dụng địa chỉ.

`Arena.ofShared()` cho phép truy cập từ nhiều thread nhưng không tự làm cho dữ liệu được đồng bộ. Nếu nhiều thread cùng đọc/ghi buffer, vẫn cần cơ chế đồng bộ hoặc quy tắc ownership rõ ràng.

## 9. Các lỗi thường gặp khi chuyển chuỗi và buffer

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng charset mặc định không khớp thư viện | Văn bản bị lỗi dấu hoặc sai ký tự. | Thống nhất charset và truyền `StandardCharsets.UTF_8` khi API yêu cầu UTF-8. |
| Quên NUL terminator | Hàm C đọc tiếp qua cuối buffer để tìm NUL. | Dùng `Arena.allocateFrom(...)` hoặc tự dành một byte và ghi NUL. |
| Tính dung lượng bằng `String.length()` | Buffer có thể thiếu byte với UTF-8. | Tính trên byte đã mã hóa hoặc dùng `allocateFrom(...)`. |
| Quên tính byte NUL trong capacity | Native không còn chỗ kết thúc chuỗi. | Capacity phải chứa cả nội dung và terminator. |
| Đọc chuỗi native không giới hạn | Có thể đọc vượt segment nếu không tìm thấy NUL. | Kiểm tra hợp đồng, giới hạn segment và terminator trước khi đọc. |
| Đóng arena quá sớm | Segment hết hiệu lực trong khi native còn dùng pointer. | Để arena sống tới khi native hoàn tất; đồng bộ trước khi đóng. |
| Dùng segment heap làm địa chỉ native | Downcall không thể nhận một địa chỉ native hợp lệ từ heap segment. | Cấp phát native segment qua `Arena`. |
| Bỏ qua mã lỗi hoặc độ dài native trả về | Có thể xử lý buffer chưa đầy đủ hoặc không hợp lệ. | Kiểm tra mã trả về, độ dài và quy ước terminator. |

Đặc biệt, không gọi `getString(...)` trên một vùng nhớ native không đáng tin cậy nếu chưa biết vùng đó có NUL trong giới hạn segment. Với dữ liệu có độ dài tường minh, hãy dùng độ dài được kiểm tra để tạo slice và giải mã đúng số byte.

## 10. Khi nào dùng C string và khi nào dùng pointer + length?

| Nhu cầu | C string (NUL-terminated) | Pointer + length |
| --- | --- | --- |
| Tương thích API C truyền thống | Phù hợp khi hợp đồng yêu cầu `char *`. | Chỉ dùng nếu API hỗ trợ. |
| Văn bản UTF-8 không có NUL ở giữa | Phù hợp. | Phù hợp. |
| Dữ liệu có byte NUL ở giữa | Không phù hợp. | Phù hợp. |
| Dữ liệu nhị phân | Không phù hợp. | Phù hợp. |
| Biết chính xác số byte | Vẫn cần NUL nếu API yêu cầu. | Truyền trực tiếp số byte. |
| Nguy cơ native quét quá cuối buffer | Cần bảo đảm terminator trong vùng nhớ. | Cần bảo đảm length không vượt vùng nhớ. |

Hãy tuân thủ chữ ký và hợp đồng của thư viện native. Java không thể tự quyết định một tham số `char *` là chuỗi UTF-8 hay dữ liệu nhị phân; điều đó phải được quy định giữa hai phía.

## 11. Quy trình thực hành an toàn

Khi tích hợp một hàm native xử lý chuỗi, có thể kiểm tra lần lượt:

1. **Đọc chữ ký native**: xác định tham số là `const char *`, `char *`, pointer + length hay wide string.
2. **Xác định charset**: UTF-8, encoding theo locale hay encoding riêng của thư viện.
3. **Xác định quy tắc kết thúc**: NUL terminator hay độ dài tường minh; nếu là NUL, capacity phải có chỗ cho byte kết thúc.
4. **Tạo layout và descriptor đúng ABI**: pointer dùng `ValueLayout.ADDRESS`; kiểu số và kiểu độ dài phải khớp C ABI.
5. **Cấp phát qua arena**: chọn `Arena.ofConfined()` cho lời gọi đồng bộ hoặc arena có vòng đời dài hơn cho pointer được giữ lại.
6. **Kiểm tra kết quả**: xác minh mã trả về, byte length, terminator và giới hạn trước khi giải mã.
7. **Đóng tài nguyên đúng thời điểm**: chỉ đóng arena sau khi native không còn dùng segment hoặc symbol gắn với arena.

## 12. Kiến thức cần nhớ

- `String` là văn bản Unicode; `char *` của C là địa chỉ tới byte. Hai bên phải thống nhất charset.
- C string thường kết thúc bằng byte NUL `0`; byte kết thúc cần được tính vào dung lượng buffer.
- `Arena.allocateFrom(String, Charset)` tạo native segment chứa chuỗi đã mã hóa và NUL terminator.
- `MemorySegment.getString(offset, Charset)` đọc C string theo charset đã chọn; cần bảo đảm NUL nằm trong giới hạn segment.
- Khi native ghi vào buffer, Java phải truyền capacity đúng và kiểm tra độ dài, mã lỗi cùng terminator trước khi đọc.
- Dữ liệu có NUL ở giữa hoặc dữ liệu nhị phân nên dùng pointer + length nếu API native hỗ trợ.
- Arena phải sống lâu hơn mọi lần native sử dụng pointer; arena đóng quá sớm làm segment mất hiệu lực.
- FFM API chính thức từ JDK 22 qua JEP 454; các ví dụ không cần preview hoặc thư viện bytecode/native wrapper bên ngoài.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — chuẩn hóa FFM API trong JDK 22.
- [Arena — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html) — cấp phát và quản lý vòng đời vùng nhớ, bao gồm `allocateFrom`.
- [MemorySegment — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html) — truy cập segment và chuyển đổi chuỗi NUL-terminated.
- [Linker — Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html) — tạo downcall handle và mô tả chữ ký hàm native.
- [Package `java.lang.foreign` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html) — FFM API hiện hành.
