# @Native: đánh dấu hằng số cho mã native trong Java Core

`@Native` là một annotation chuẩn của Java, khai báo tại `java.lang.annotation.Native` từ Java 8. Nó đánh dấu **trường định nghĩa một giá trị hằng có thể được tham chiếu từ mã native** (chẳng hạn C/C++ qua JNI). Công cụ tạo native header, đặc biệt lệnh `javac -h`, có thể dùng dấu này để đưa giá trị hằng Java vào header cho phía native.

Điều cần nắm: `@Native` là **metadata dành cho công cụ biên dịch/tạo header**. Nó không biến một trường Java thành phương thức native, không tự nạp thư viện C/C++ và không khiến JVM chuyển đổi dữ liệu hay đồng bộ giá trị lúc chạy.

## 1. Mục tiêu của bài

Sau khi học, bạn có thể:

- Nêu đúng mục đích của `@Native` và hoàn cảnh nó hữu ích.
- Xác định vị trí áp dụng (`FIELD`), vòng đời (`SOURCE`) và việc annotation không có phần tử cấu hình.
- Viết một class Java 17+ có hằng số được gắn `@Native`, sử dụng `javac -h` để tạo native header.
- Đọc được các macro hằng số trong file `.h` được tạo và giải thích cách mã C/C++ dùng chúng.
- Phân biệt `@Native` với từ khóa `native`, JNI, `System.loadLibrary(...)` và annotation runtime.
- Tránh các trường hợp hằng số không đủ điều kiện, header cũ và giả định sai về Reflection.

## 2. Tại sao cần đánh dấu hằng số cho native code?

Giả sử ứng dụng Java giao tiếp với một thư viện C/C++ dùng mã trạng thái. Ở Java có:

~~~java
public static final int STATUS_OK = 0;
public static final int STATUS_BUSY = 42;
~~~

Phía C cũng có thể cần hai con số `0` và `42`. Nếu lập trình viên tự chép số sang file C header, mỗi lần Java đổi hằng số đều phải cập nhật thủ công bản sao đó. Bỏ sót một bên sẽ làm hai phía hiểu khác nhau về cùng một mã trạng thái.

`@Native` giúp thể hiện rõ ý định: *hằng số này có thể được tham chiếu từ mã native*. Kết hợp `javac -h`, thông tin được xuất vào header, nhờ vậy mã native có thể dùng tên macro được tạo thay vì viết lặp lại literal.

Ví dụ:

~~~java
import java.lang.annotation.Native;

public final class NativeCodes {
    @Native
    public static final int STATUS_OK = 0;

    @Native
    public static final int STATUS_BUSY = 42;
}
~~~

Trong bối cảnh này, `@Native` không thay đổi giá trị `STATUS_OK` hay `STATUS_BUSY`, cũng không làm chúng “native” về kiểu dữ liệu. Chúng vẫn là các hằng số Java bình thường. Annotation chủ yếu là tín hiệu cho công cụ tạo header.

## 3. Đặc điểm kỹ thuật của `java.lang.annotation.Native`

Java SE định nghĩa `@Native` với các meta-annotation sau:

~~~java
@Documented
@Target(ElementType.FIELD)
@Retention(RetentionPolicy.SOURCE)
public @interface Native {
}
~~~

Đoạn mã trên minh họa định nghĩa API của JDK; bạn **không** cần và không nên tự khai báo lại annotation có tên trùng `java.lang.annotation.Native`.

| Đặc điểm | Ý nghĩa |
| --- | --- |
| Package | `java.lang.annotation` — cần import `java.lang.annotation.Native` |
| Có từ | Java 8 |
| `@Target(FIELD)` | Chỉ gắn trực tiếp trên khai báo trường (field), không gắn trên class hoặc method |
| `@Retention(SOURCE)` | Compiler xử lý trong giai đoạn source; annotation không được giữ trong `.class` |
| `@Documented` | Annotation có thể xuất hiện trong tài liệu Javadoc cho phần tử liên quan |
| Element | Không có element cần truyền; cú pháp sử dụng là `@Native` |
| Công dụng điển hình | Đánh dấu trường hằng số mà công cụ tạo native header cần nhận biết |

Từ `@Retention(SOURCE)` suy ra **Reflection runtime không nhìn thấy `@Native`** trên field, ngay cả khi field đó có thể được tra cứu bằng Reflection. Đây là lựa chọn hợp lý vì công cụ tạo header sử dụng thông tin lúc biên dịch.

`@Target(FIELD)` chỉ kiểm soát vị trí hợp lệ về mặt cú pháp. Nó không tự đảm bảo field là hằng số; để header xuất giá trị ổn định, bạn nên dùng `static final`, kiểu nguyên thủy thích hợp (ví dụ `int`, `long`) và biểu thức khởi tạo là hằng số tại thời điểm biên dịch.

## 4. Ví dụ đầy đủ Java 17+: tạo header từ các hằng số

Tạo **một file duy nhất** tên `NativeCodes.java`, không khai báo `package` để tên file header dễ quan sát:

~~~java
import java.lang.annotation.Native;

public final class NativeCodes {
    @Native
    public static final int STATUS_OK = 0;

    @Native
    public static final int STATUS_BUSY = 42;

    @Native
    public static final long MAX_BUFFER_BYTES = 4096L;

    private NativeCodes() {
        // Utility class: không khởi tạo instance.
    }

    public static void main(String[] args) throws NoSuchFieldException {
        System.out.println("STATUS_OK=" + STATUS_OK);
        System.out.println("STATUS_BUSY=" + STATUS_BUSY);
        System.out.println("MAX_BUFFER_BYTES=" + MAX_BUFFER_BYTES);
        System.out.println("RUNTIME_VISIBLE=" +
                NativeCodes.class.getField("STATUS_OK")
                        .isAnnotationPresent(Native.class));
    }
}
~~~

Ở thư mục chứa `NativeCodes.java`, thực hiện bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 -h headers NativeCodes.java
java NativeCodes
~~~

`javac -h headers` biên dịch file Java như bình thường và yêu cầu tạo các JNI/native header trong thư mục `headers`. Trình biên dịch có thể tạo thư mục output cần thiết. Với class không có package như ví dụ, bạn sẽ thấy file `headers/NativeCodes.h`.

Stdout của lệnh `java NativeCodes`:

~~~text
STATUS_OK=0
STATUS_BUSY=42
MAX_BUFFER_BYTES=4096
RUNTIME_VISIBLE=false
~~~

Giải thích từng dòng:

1. Ba dòng đầu đến từ **giá trị các trường Java**, không phải từ việc chạy thư viện native.
2. `NativeCodes.class.getField("STATUS_OK")` lấy đối tượng Reflection cho trường public.
3. `isAnnotationPresent(Native.class)` trả `false` vì `@Native` có retention `SOURCE`: metadata này không còn trong class khi chương trình chạy.
4. Dù Reflection trả `false`, `javac -h` vẫn dùng được annotation trong giai đoạn biên dịch để tạo header.

### Header được tạo có gì?

Trong file `headers/NativeCodes.h`, các khai báo liên quan đến hằng số có dạng:

~~~c
#undef NativeCodes_STATUS_OK
#define NativeCodes_STATUS_OK 0L
#undef NativeCodes_STATUS_BUSY
#define NativeCodes_STATUS_BUSY 42L
#undef NativeCodes_MAX_BUFFER_BYTES
#define NativeCodes_MAX_BUFFER_BYTES 4096LL
~~~

Đây là các dòng macro được kiểm chứng từ ví dụ với JDK 21. Header thực tế còn có phần guard, comment và include do `javac` sinh; trình bày trên chỉ trích **những dòng quan trọng về hằng số**. Đối với giá trị `int`, header sinh literal kiểu C với hậu tố `L`; đối với `long` Java, literal macro có thể dùng hậu tố `LL`.

Tên macro kết hợp tên class và tên field, ví dụ `NativeCodes_STATUS_BUSY`. Khi class thuộc package, tên file header và tiền tố macro phản ánh tên Java đủ chuẩn, có chuyển đổi ký tự theo quy tắc JNI. Do đó hãy xem file `.h` thực sự được tạo thay vì tự đoán tên macro.

Phía native có thể tham chiếu header trong mã C như sau (đoạn mã **minh họa phía C**, không phải một chương trình C hoàn chỉnh):

~~~c
#include "NativeCodes.h"

int is_busy_code(int status) {
    return status == NativeCodes_STATUS_BUSY;
}
~~~

Khi biên dịch C, cần cấu hình đúng đường dẫn include tới thư mục header đã tạo và JNI headers của JDK (vì native header được tạo có thể include `jni.h`). Chỉ đưa file `.h` vào source C không tự tạo một thư viện native, và ví dụ Java ở trên không yêu cầu chạy code C để có stdout đã nêu.

## 5. Cơ chế hoạt động từ mã Java đến header

~~~text
NativeCodes.java
   |
   |  @Native trên static final int/long
   v
javac -h headers NativeCodes.java
   |
   +--> NativeCodes.class
   |       bytecode dùng hằng số bình thường;
   |       @Native với SOURCE retention không được lưu lại
   |
   +--> headers/NativeCodes.h
           macro tương ứng với các hằng được xuất
                      |
                      v
           mã C/C++ include header
           và dùng tên macro trong lúc build native
~~~

Cần phân biệt rõ **hai sản phẩm**: `.class` dành cho JVM và `.h` dành cho toolchain native. Annotation cung cấp một chỉ dẫn trong quá trình tạo header. Nó không tạo cầu nối gọi hàm Java ↔ C/C++, không thực hiện marshaling dữ liệu, không cung cấp cơ chế gọi native tự động.

Mã Java và mã C/C++ chỉ dùng cùng định nghĩa khi quy trình build của dự án thực sự **tạo lại header và biên dịch lại code native khi các hằng số thay đổi**. Nếu dùng header cũ, số trong mã C/C++ vẫn có thể lệch với Java. Hằng số compile-time Java cũng có thể bị inline vào bytecode của mã gọi; thay đổi giá trị hằng số có thể cần biên dịch lại mã phụ thuộc.

## 6. `@Native` khác gì từ khóa `native` và JNI?

Hai cách viết sau nhắm tới các đối tượng khác nhau:

~~~java
import java.lang.annotation.Native;

class NativeExample {
    @Native
    public static final int OPERATION_READ = 1;

    public native int readValue();
}
~~~

**`@Native`** đặt trên field, gợi ý cho công cụ tạo header rằng hằng số có thể được tham chiếu từ code native. **`native`** là modifier của method; nó khai báo một phương thức được triển khai bằng native code, nên không có Java method body. Code minh họa trên chỉ là khai báo, không phải chương trình có thể chạy độc lập: muốn gọi `readValue()` phải có implementation native phù hợp và việc nạp thư viện cần thiết.

| Vấn đề | `@Native` trên field | `native` trên method |
| --- | --- | --- |
| Mục đích | Xuất metadata của hằng số phục vụ native header | Khai báo method triển khai ngoài Java |
| Vị trí | Field | Method |
| Bản thân có gọi C/C++ không? | Không | Không tự gọi nếu không có invocation/implementation |
| Có thể khiến `javac -h` tạo header? | Có, khi field là hằng số phù hợp | Có, khi class chứa native method |
| Có nạp thư viện? | Không | Không; việc nạp thư viện là một bước riêng khi ứng dụng dùng JNI |

**JNI (Java Native Interface)** là tập hợp quy ước/API giúp Java và native code làm việc cùng nhau. `@Native` có thể tham gia vào quy trình tạo header của JNI, nhưng tự nó **không phải JNI bridge**. Lệnh `System.loadLibrary("...")` là cơ chế nạp native library khi cần; không liên quan trực tiếp tới việc có hay không có `@Native` trên một trường.

`@Native` cũng không phải công cụ tạo GraalVM Native Image, không tự chuyển Java thành mã máy native và không thay thế `javac -h`.

## 7. Khi nào nên và không nên dùng?

Dùng `@Native` khi dự án thực sự có thành phần C/C++ phụ thuộc một tập giá trị hằng Java, và build native tiêu thụ header được công cụ tạo ra. Những tình huống phù hợp gồm mã trạng thái, cờ bitmask, mã thao tác hoặc giới hạn kích thước đã ổn định và cần được dùng ở cả hai phía.

Ví dụ hằng số cờ bitmask:

~~~java
import java.lang.annotation.Native;

class FileFlags {
    @Native public static final int READ  = 1 << 0;
    @Native public static final int WRITE = 1 << 1;
}
~~~

`1 << 0` và `1 << 1` là **biểu thức hằng số tại thời điểm biên dịch**; hai trường tương ứng có giá trị `1` và `2`. Đây là trường hợp hợp lý để xuất hằng số qua header.

Không cần `@Native` cho mọi `static final`. Một hằng số chỉ dùng nội bộ Java không có lý do phải được đưa vào native header. Cũng không nên xem `@Native` như công cụ kiểm tra validation, persistence, security hay dependency injection: nó không cung cấp những chức năng đó.

Cần phân biệt một *constant variable* với trường chỉ có modifier `final`. Ví dụ sau không phù hợp để xuất macro hằng số:

~~~java
import java.lang.annotation.Native;

class BadConstantExample {
    @Native
    static final int VALUE = Integer.parseInt("42");
}
~~~

Mặc dù field được khai báo `static final`, phép gọi `Integer.parseInt("42")` không phải **constant expression** của Java; không thể trông đợi nó được xuất như một macro hằng số tương tự `42`. `@Native` không biến phép tính runtime thành một biểu thức hằng.

## 8. Lỗi thường gặp và cách kiểm tra

**Lỗi 1 — Nhầm package:** Viết `import java.lang.Native;` là sai. Tên đầy đủ là `java.lang.annotation.Native`.

**Lỗi 2 — Gắn vào sai loại khai báo:** `@Native` có target `FIELD`. Gắn lên method/class sẽ gây lỗi biên dịch. Đặt trên field khai báo giá trị hằng số mà native code cần tham chiếu.

**Lỗi 3 — Chờ Reflection đọc được annotation:** `@Native` là `SOURCE`, nên không đọc được qua `Field.getAnnotation(Native.class)` khi chạy. Dùng `javac -h` để quan sát vai trò thực tế.

**Lỗi 4 — Chỉ chạy `javac NativeCodes.java`:** Lệnh đó biên dịch Java nhưng không yêu cầu tạo native header. Khi muốn tạo header, dùng tùy chọn `-h <thu_muc>`, ví dụ `javac -h headers NativeCodes.java`.

**Lỗi 5 — Đánh dấu field nhưng giá trị không phải hằng số compile-time:** `final` chỉ chặn gán lại sau khởi tạo, không đồng nghĩa “có thể xuất literal lúc compile”. Chọn kiểu nguyên thủy và biểu thức hằng số theo quy tắc Java; kiểm tra file `.h` thật sự sinh ra.

**Lỗi 6 — Tưởng header xuất mọi field:** `javac -h` không có nghĩa mọi field của class đều trở thành macro. Với tình huống annotation, hãy đánh dấu cụ thể các constant field native code cần và kiểm tra nội dung output.

**Lỗi 7 — Sửa `.h` thủ công:** File header do `javac` sinh có thể bị ghi đè ở lần build tiếp theo. Sửa giá trị gốc trong `.java`, tạo lại header rồi biên dịch lại native code phụ thuộc.

**Lỗi 8 — Nhầm header với thư viện:** Có `.h` không đồng nghĩa có file `.dll`/`.so`, implementation native, quá trình linking hoặc load library. Chúng là các bước riêng nếu ứng dụng thực sự gọi native method.

## 9. Bài tập tự luyện

1. Tạo `NativeCodes.java` như ví dụ. Dự đoán stdout rồi chạy `javac -h headers NativeCodes.java` và `java NativeCodes`. Xác nhận cả ba giá trị và `RUNTIME_VISIBLE=false`.
2. Mở `headers/NativeCodes.h`, tìm các macro của `STATUS_OK`, `STATUS_BUSY` và `MAX_BUFFER_BYTES`. Giải thích vì sao dùng tên được sinh giúp tránh chép số thủ công.
3. Thêm `@Native public static final int FLAG_COMBINED = (1 << 0) | (1 << 2);` vào class. Dự đoán macro xuất giá trị nào, tạo lại header và kiểm tra (kết quả số là `5`).
4. Bỏ `@Native` khỏi `STATUS_BUSY` rồi tạo lại header vào một thư mục output sạch. Kiểm tra macro nào không còn xuất hiện và giải thích lý do.
5. Thêm một method `public native void ping();` nhưng **không gọi nó**. Dùng `javac -h` quan sát các khai báo JNI method khác với macro hằng số ra sao.
6. Tự giải thích vì sao `getAnnotation(Native.class)` không trả về annotation, mặc dù `javac -h` vẫn sinh header.

## 10. Điểm cần ghi nhớ

- `@Native` là annotation có sẵn từ Java 8, tên đầy đủ `java.lang.annotation.Native`.
- Nó chỉ áp dụng cho field (`@Target(FIELD)`), có retention `SOURCE` và dùng để đánh dấu hằng số có thể được native code tham chiếu.
- `javac -h` có thể tạo native header và macro cho những hằng số đó, ngay cả khi class không khai báo native method.
- Một field được gắn `@Native` vẫn là field Java bình thường; mã native không tự chạy và Reflection runtime không thấy annotation.
- Quy trình build cần tạo lại header và xây dựng lại các thành phần phụ thuộc khi thay đổi hằng số.

### Tham khảo

- Oracle Java SE 17 — [`java.lang.annotation.Native`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Native.html).
- Oracle Java SE 17 — [Tài liệu `javac`, tùy chọn `-h`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
