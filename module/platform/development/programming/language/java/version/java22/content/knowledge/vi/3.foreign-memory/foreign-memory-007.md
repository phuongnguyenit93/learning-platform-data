# Padding, offset và alignment khi ánh xạ cấu trúc C sang Java

## Bộ nhớ ngoại lai trong Java hiện đại

Foreign Function & Memory (FFM) API cho phép Java mô tả và truy cập vùng nhớ bên ngoài heap, đồng thời liên kết với hàm native. API này được hoàn thiện trong JDK 22 theo JEP 454 và tiếp tục là API chính thức trong các JDK hiện hành. Các ví dụ dưới đây dùng `java.lang.foreign` với `MemoryLayout`, `MemorySegment`, `Arena` và `Linker`; không cần bật preview trên JDK 22 trở lên.

Khi Java đọc hoặc ghi một cấu trúc C (`struct`), hai phía phải hiểu vùng nhớ theo cùng một cách. C compiler quyết định kích thước, căn chỉnh và vị trí của từng trường theo ABI (Application Binary Interface), kiến trúc, hệ điều hành và các tùy chọn biên dịch. Java phải mô tả chính xác bố cục đó bằng `MemoryLayout`. Nếu offset hoặc kích thước sai, Java có thể đọc nhầm trường, ghi đè dữ liệu bên cạnh hoặc truyền cấu trúc sai cho hàm native.

## 1. Kích thước, offset, alignment và padding

Bốn khái niệm này mô tả những khía cạnh khác nhau của bố cục bộ nhớ:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Kích thước (`byteSize`) | Số byte mà một trường hoặc toàn bộ cấu trúc chiếm. |
| Offset (`byteOffset`) | Số byte tính từ đầu cấu trúc đến vị trí bắt đầu của một trường. |
| Alignment (`byteAlignment`) | Yêu cầu địa chỉ bắt đầu phải là bội số của một số byte nhất định. Ví dụ alignment 4 nghĩa là địa chỉ phải chia hết cho 4. |
| Padding | Các byte đệm compiler đặt giữa các trường hoặc ở cuối cấu trúc để đáp ứng alignment và kích thước cấu trúc. |

Giả sử một ABI phổ biến có các đặc điểm sau:

- `char`: kích thước 1 byte, alignment 1.
- `int`: kích thước 4 byte, alignment 4.
- `short`: kích thước 2 byte, alignment 2.

Với cấu trúc C:

```c
struct Record {
    char kind;
    int id;
    short score;
};
```

Compiler thường đặt các trường như sau:

| Thành phần | Offset | Kích thước | Lý do |
| --- | ---: | ---: | --- |
| `kind` | 0 | 1 | Trường đầu tiên bắt đầu tại byte 0. |
| Padding | 1 | 3 | Đưa `id` đến offset 4, là bội số của 4. |
| `id` | 4 | 4 | Bắt đầu tại địa chỉ căn chỉnh 4 byte. |
| `score` | 8 | 2 | Offset 8 đáp ứng alignment 2. |
| Padding cuối | 10 | 2 | Đưa kích thước cấu trúc lên 12, là bội số của alignment cấu trúc 4. |

Do đó, trong ví dụ ABI này, `sizeof(struct Record)` là 12 byte và alignment của cấu trúc là 4 byte. Padding cuối cũng quan trọng như padding giữa các trường: khi tạo mảng `struct Record`, phần tử tiếp theo bắt đầu sau toàn bộ 12 byte của phần tử hiện tại.

Các con số trên chỉ minh họa một ABI thông dụng. Ngôn ngữ C không bảo đảm mọi nền tảng đều có kích thước và alignment như vậy; compiler còn có thể thay đổi bố cục theo tùy chọn đóng gói hoặc căn chỉnh đặc biệt.

## 2. Mô tả struct bằng MemoryLayout

`MemoryLayout.structLayout(...)` tạo một `StructLayout`, trong đó các thành phần được đặt nối tiếp theo thứ tự khai báo. Factory này **không tự chèn padding** để căn chỉnh thành phần tiếp theo. Nếu offset hiện tại không đáp ứng alignment của thành phần kế tiếp, việc tạo layout có thể thất bại. Muốn mô tả đúng C struct, hãy chèn `MemoryLayout.paddingLayout(byteSize)` tại những vị trí cần đệm.

`PaddingLayout` có alignment tự nhiên bằng 1. Nó chiếm đúng số byte đã khai báo nhưng không làm tăng alignment của struct. Alignment của một group layout thông thường là alignment lớn nhất trong các thành phần của nó.

Layout tường minh cho ví dụ `Record` ở trên:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

MemoryLayout RECORD_LAYOUT = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("id"),
    ValueLayout.JAVA_SHORT.withName("score"),
    MemoryLayout.paddingLayout(2)
);

long size = RECORD_LAYOUT.byteSize();
long alignment = RECORD_LAYOUT.byteAlignment();
long idOffset = RECORD_LAYOUT.byteOffset(groupElement("id"));
long scoreOffset = RECORD_LAYOUT.byteOffset(groupElement("score"));

// size = 12, alignment = 4, idOffset = 4, scoreOffset = 8
```

Các layout `JAVA_BYTE`, `JAVA_INT` và `JAVA_SHORT` phù hợp với ví dụ ABI đã nêu. Khi ánh xạ chương trình C thực tế trên nhiều nền tảng, hãy lấy layout kiểu C từ native linker thay vì giả định các kiểu C luôn có cùng kích thước với kiểu Java cùng tên.

## 3. Dùng canonical layouts của native linker

`Linker.nativeLinker().canonicalLayouts()` trả về ánh xạ từ tên kiểu dữ liệu của ABI native hiện tại sang layout tương ứng. Native linker bảo đảm cung cấp layout cho các kiểu C cơ bản như `char`, `short`, `int`, `long`, `long long`, `float`, `double`, `size_t`, `wchar_t` và `void*`.

Điều này đặc biệt quan trọng với `long` và `size_t`. Chẳng hạn, C `long` có thể có kích thước 8 byte trên Linux/x64 nhưng 4 byte trên Windows/x64; `size_t` cũng phụ thuộc mô hình dữ liệu 32-bit hay 64-bit. Dùng `ValueLayout.JAVA_LONG` cho C `long` ở mọi nền tảng sẽ không chính xác.

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

import java.util.Map;

Map<String, MemoryLayout> C_TYPES = Linker.nativeLinker().canonicalLayouts();

MemoryLayout C_CHAR = C_TYPES.get("char");
MemoryLayout C_INT = C_TYPES.get("int");
MemoryLayout C_SHORT = C_TYPES.get("short");
MemoryLayout C_LONG = C_TYPES.get("long");
MemoryLayout C_SIZE_T = C_TYPES.get("size_t");
```

Các layout trong map mang theo kích thước, alignment và đặc tính phù hợp với ABI đang chạy. Map này không phải một bảng ánh xạ cố định cho mọi hệ điều hành; nó mô tả native platform mà JVM hiện tại đang sử dụng.

## 4. Tính padding theo alignment của từng trường

Với một struct thông thường không dùng thuộc tính đóng gói hoặc căn chỉnh đặc biệt, có thể tính padding trước mỗi trường theo công thức:

\[
padding = (alignment - (offset \bmod alignment)) \bmod alignment
\]

Sau khi chèn padding, trường bắt đầu tại offset là bội số của alignment yêu cầu. Khi đã thêm tất cả trường, tính padding cuối để tổng kích thước là bội số của alignment của struct.

Ví dụ helper sau dựng layout `Record` từ các canonical layout của ABI. Helper giả định alignment của struct bằng alignment lớn nhất trong các trường, đúng với struct thông thường không bị thay đổi bằng thuộc tính compiler riêng:

```java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

static final Map<String, MemoryLayout> C_TYPES =
    Linker.nativeLinker().canonicalLayouts();

static long paddingFor(long offset, long alignment) {
    return (alignment - (offset % alignment)) % alignment;
}

static long addField(
        List<MemoryLayout> members,
        long offset,
        MemoryLayout field) {

    long padding = paddingFor(offset, field.byteAlignment());
    if (padding > 0) {
        members.add(MemoryLayout.paddingLayout(padding));
        offset += padding;
    }

    members.add(field);
    return offset + field.byteSize();
}

static MemoryLayout recordLayout() {
    MemoryLayout kind = C_TYPES.get("char").withName("kind");
    MemoryLayout id = C_TYPES.get("int").withName("id");
    MemoryLayout score = C_TYPES.get("short").withName("score");

    List<MemoryLayout> members = new ArrayList<>();
    long offset = 0;
    offset = addField(members, offset, kind);
    offset = addField(members, offset, id);
    offset = addField(members, offset, score);

    long structAlignment = Math.max(
        kind.byteAlignment(),
        Math.max(id.byteAlignment(), score.byteAlignment())
    );
    long tailPadding = paddingFor(offset, structAlignment);
    if (tailPadding > 0) {
        members.add(MemoryLayout.paddingLayout(tailPadding));
    }

    return MemoryLayout.structLayout(members.toArray(MemoryLayout[]::new));
}
```

Helper này tránh hardcode các số padding của ví dụ. Với struct có `_Alignas`, `#pragma pack`, `__attribute__((packed))` hoặc quy tắc ABI đặc biệt, cần điều chỉnh alignment và cách tính theo đúng compiler đã tạo thư viện native.

## 5. Đọc và ghi trường bằng offset

Sau khi có layout đúng, `byteOffset(PathElement...)` tính vị trí trường theo đường dẫn layout. Với trường trực tiếp của struct, dùng `PathElement.groupElement("tên_trường")`. Với trường lồng nhau, nối nhiều path element; với phần tử mảng có chỉ số cố định, thêm `PathElement.sequenceElement(index)`.

Ví dụ sau cấp phát một vùng nhớ theo layout rồi đọc và ghi từng trường. Các kiểu truy cập lấy từ canonical layout để giữ đúng kích thước và alignment của ABI hiện tại:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import java.util.Map;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

Map<String, MemoryLayout> c = Linker.nativeLinker().canonicalLayouts();
ValueLayout.OfByte C_CHAR = (ValueLayout.OfByte) c.get("char");
ValueLayout.OfInt C_INT = (ValueLayout.OfInt) c.get("int");
ValueLayout.OfShort C_SHORT = (ValueLayout.OfShort) c.get("short");

MemoryLayout recordLayout = recordLayout(); // layout được tạo ở ví dụ trước

try (Arena arena = Arena.ofConfined()) {
    MemorySegment record = arena.allocate(recordLayout);

    long kindOffset = recordLayout.byteOffset(groupElement("kind"));
    long idOffset = recordLayout.byteOffset(groupElement("id"));
    long scoreOffset = recordLayout.byteOffset(groupElement("score"));

    record.set(C_CHAR, kindOffset, (byte) 'A');
    record.set(C_INT, idOffset, 42);
    record.set(C_SHORT, scoreOffset, (short) 900);

    byte kind = record.get(C_CHAR, kindOffset);
    int id = record.get(C_INT, idOffset);
    short score = record.get(C_SHORT, scoreOffset);
}
```

`Arena.allocate(recordLayout)` cấp phát vùng nhớ có kích thước và alignment theo layout. Các thao tác `MemorySegment.get` và `set` vẫn kiểm tra giới hạn vùng nhớ và alignment của kiểu truy cập. Vì vậy, một offset tính sai hoặc một layout không phản ánh đúng cấu trúc native có thể gây lỗi truy cập hoặc làm sai dữ liệu.

### Trường lồng nhau và mảng

Layout path có thể đi qua nhiều cấp. Ví dụ, nếu `header` là một struct con và `items` là một sequence, có thể tính offset của một trường lồng nhau như sau:

```java
long headerCodeOffset = OUTER_LAYOUT.byteOffset(
    groupElement("header"),
    groupElement("code")
);

long thirdItemValueOffset = OUTER_LAYOUT.byteOffset(
    groupElement("items"),
    MemoryLayout.PathElement.sequenceElement(2),
    groupElement("value")
);
```

Kích thước của layout phần tử quyết định bước nhảy giữa các phần tử trong sequence. Khi sequence chứa struct, kích thước struct phải bao gồm cả padding cuối; nếu thiếu tail padding, offset của phần tử thứ hai trở đi sẽ sai.

## 6. Alignment đặc biệt và packed struct

Một số chương trình C dùng quy tắc căn chỉnh khác struct thông thường. Ví dụ, compiler có thể hỗ trợ `#pragma pack` hoặc `__attribute__((packed))` để giảm padding. Đây là chỉ thị phụ thuộc compiler/ABI; layout Java phải mô phỏng đúng kết quả thực tế của compiler.

`withByteAlignment(long)` tạo layout có alignment constraint khác. Giá trị alignment phải là lũy thừa của 2. Với một struct packed dùng alignment 1 cho trường `int`, ý tưởng mô tả có thể như sau:

```java
MemoryLayout packedInt = C_INT.withByteAlignment(1).withName("id");

MemoryLayout packedRecord = MemoryLayout.structLayout(
    C_CHAR.withName("kind"),
    packedInt
);
```

Khi đó trường `id` có thể bắt đầu ngay sau `kind`, không cần padding để căn chỉnh 4 byte. Chỉ dùng cách này nếu struct native thực sự được biên dịch với quy tắc packed tương ứng. Một số native linker có thể từ chối packed struct khi layout được dùng trong function descriptor; khả năng hỗ trợ phụ thuộc linker và ABI.

Với cấu trúc được căn chỉnh lớn hơn alignment tự nhiên của các trường, có thể đặt alignment cho layout nhóm bằng `withByteAlignment(...)` và bổ sung padding cuối để kích thước đáp ứng yêu cầu ABI. Không nên tự đặt alignment theo suy đoán; hãy xác minh bằng compiler C.

## 7. Xác minh layout với compiler C

Trước khi dùng layout Java để trao đổi dữ liệu với thư viện native, hãy xác minh kích thước, alignment và offset bằng chính compiler cùng tùy chọn đã dùng để biên dịch thư viện. Trong C11, có thể dùng `sizeof`, `_Alignof` và `offsetof`:

```c
#include <stddef.h>
#include <stdio.h>

struct Record {
    char kind;
    int id;
    short score;
};

int main(void) {
    printf("size=%zu\n", sizeof(struct Record));
    printf("alignment=%zu\n", _Alignof(struct Record));
    printf("kind=%zu\n", offsetof(struct Record, kind));
    printf("id=%zu\n", offsetof(struct Record, id));
    printf("score=%zu\n", offsetof(struct Record, score));
}
```

Đối chiếu các giá trị này với `recordLayout.byteSize()`, `recordLayout.byteAlignment()` và các kết quả `byteOffset(...)` ở Java. Nếu thư viện được biên dịch bằng cờ như `-fpack-struct`, `#pragma pack` hoặc tùy chọn ABI khác, chương trình kiểm tra phải dùng cùng cấu hình.

## 8. Những lỗi thường gặp

- **Cho rằng `structLayout` tự chèn padding:** các thành phần được đặt nối tiếp; phải mô tả padding cần thiết một cách tường minh.
- **Bỏ qua padding cuối:** kích thước struct và stride của mảng struct sẽ không còn khớp với `sizeof` phía C.
- **Dùng offset hardcode cho mọi nền tảng:** kích thước và alignment của kiểu C có thể thay đổi theo ABI. Lấy kiểu cơ bản từ `canonicalLayouts()` rồi tính offset từ layout.
- **Dùng kiểu Java cùng tên để thay thế kiểu C:** C `long` không phải lúc nào cũng có cùng kích thước với Java `long`; `size_t` cũng phụ thuộc mô hình dữ liệu.
- **Giảm alignment để tránh lỗi tạo layout:** chỉ làm vậy khi native struct thật sự được đóng gói hoặc ABI yêu cầu alignment yếu hơn.
- **Xem byte padding là dữ liệu:** padding phục vụ bố cục, không phải trường có ý nghĩa. Giá trị của các byte này có thể không được khởi tạo; không dùng chúng làm dữ liệu nghiệp vụ hoặc định dạng truyền mạng.
- **Bỏ qua byte order:** alignment và padding không quyết định thứ tự byte của số nguyên. Khi đọc định dạng nhị phân hoặc giao thức mạng, phải theo byte order được đặc tả riêng, không mặc định nó giống bố cục native.

`structLayout` mô tả các trường nối tiếp của C struct. Với C `union`, các thành phần dùng chung offset bắt đầu; cần dùng `MemoryLayout.unionLayout(...)` thay vì `structLayout(...)`.

## Kết luận

Để ánh xạ C struct chính xác, trước hết xác định ABI và layout của từng kiểu C. Sau đó tính padding trước mỗi trường, offset của trường, alignment của struct và padding cuối; mô tả các thành phần đó bằng `structLayout` và `paddingLayout`. Dùng `byteOffset` để truy cập trường theo tên, dùng canonical layouts để thích ứng với nền tảng và xác minh kết quả bằng `sizeof`, `_Alignof` cùng `offsetof` từ compiler C.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [MemoryLayout — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [StructLayout — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [PaddingLayout — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/PaddingLayout.html)
- [Linker — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Linker.html)
- [java.lang.foreign — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html)
