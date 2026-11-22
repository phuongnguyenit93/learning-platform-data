# Quyền truy cập native không xác nhận chữ ký C hoặc độ an toàn của thư viện

Khi Java gọi hàm trong thư viện C/C++ qua Foreign Function & Memory API (FFM) hoặc Java Native Interface (JNI), việc được cấp **quyền truy cập native** chỉ có nghĩa là ứng dụng được phép thực hiện một số thao tác có rủi ro như nạp thư viện và liên kết lời gọi native. Quyền này **không chứng minh** rằng mô tả hàm ở phía Java trùng với chữ ký nhị phân của hàm C, dữ liệu truyền vào hợp lệ, con trỏ còn sống, hoặc thư viện đáng tin cậy. Một lời gọi được cho phép vẫn có thể làm sai dữ liệu, hỏng bộ nhớ hoặc khiến cả JVM dừng bất thường.

**Mục tiêu:** phân biệt kiểm soát quyền với kiểm tra hợp đồng ABI; biết đọc một chữ ký C và đối chiếu `FunctionDescriptor`; hiểu rủi ro khi nạp thư viện; thiết kế cách kiểm thử và cô lập native code.

## 1. Bốn câu hỏi độc lập ở ranh giới Java ↔ native

| Câu hỏi | Cơ chế liên quan | Điều nó không bảo đảm |
| --- | --- | --- |
| Mã Java có quyền làm thao tác native bị hạn chế không? | `--enable-native-access` cho module thích hợp; chính sách JDK với restricted methods/JNI | Không xác minh chữ ký C, nguồn gốc thư viện hay dữ liệu đầu vào |
| Thư viện/symbol có được tìm thấy không? | `System.loadLibrary`/`System.load` (JNI), `SymbolLookup` và bộ nạp hệ điều hành (FFM) | Tìm được symbol không chứng minh đó là hàm mong muốn hoặc đúng phiên bản |
| Java sẽ truyền đối số và nhận kết quả theo ABI nào? | `Linker`, `FunctionDescriptor`, `MemoryLayout`, `MethodHandle` (FFM); khai báo JNI và mã C tương ứng | Linker không có bản khai C đáng tin cậy để so khớp tự động |
| Native code có hành xử an toàn và đúng hợp đồng không? | Thiết kế thư viện, kiểm thử, kiểm soát đầu vào, quản lý bộ nhớ, kiểm toán nguồn/phân phối | JVM không thể bảo đảm an toàn của mã máy tùy ý đang chạy trong cùng tiến trình |

Đây là các tầng khác nhau. Ví dụ, `findOrThrow("strlen")` xác nhận tìm được địa chỉ symbol theo bộ tìm kiếm đã chọn; `downcallHandle(...)` dựng cơ chế gọi theo mô tả mà **người viết Java cung cấp**. Hai bước này không đọc prototype C để xác nhận số lượng hay kiểu tham số thực tế.

Ở phía Java, `invokeExact` kiểm tra kiểu đối số Java so với `MethodType` của method handle. Điều đó chỉ xác nhận lời gọi phù hợp với **chữ ký đã khai báo cho handle**, không xác nhận handle đó đúng với hàm native phía dưới.

## 2. Quyền native là ranh giới cấp phép, không phải chứng nhận an toàn

FFM trở thành API chính thức từ **JDK 22**. Các thao tác như tạo downcall handle, tạo upcall stub, nạp thư viện native qua `SymbolLookup.libraryLookup` và một số thao tác diễn giải lại vùng nhớ được đánh dấu là **restricted** vì dùng sai có thể phá vỡ tính toàn vẹn JVM. Kể từ **JDK 24**, các thao tác nạp/liên kết native liên quan đến JNI cũng chịu chính sách cảnh báo/quyền native.

Với chương trình đặt trên classpath, cách chạy chủ động cấp quyền cho unnamed modules là:

~~~bash
java --enable-native-access=ALL-UNNAMED SafeNativeCall
~~~

Với mã trong named module `com.example.bridge`, có thể cấp hẹp hơn:

~~~bash
java --enable-native-access=com.example.bridge --module-path mods -m com.example.bridge/com.example.bridge.Main
~~~

Chỉ dùng lệnh thứ hai khi cấu trúc module, tên module và main class đúng với dự án thực tế. `ALL-UNNAMED` cấp cho **tất cả** unnamed modules trên classpath; nó không chọn riêng một JAR. Ưu tiên named module khi có thể để giới hạn phạm vi được phép gọi restricted methods.

Trong **JDK 24/25**, nếu không cấp quyền, chính sách mặc định là cảnh báo cho các thao tác native không được cấp phép; có thể dùng `--illegal-native-access=deny` để phát hiện bằng ngoại lệ `IllegalCallerException`. Chính sách mặc định có thể nghiêm ngặt hơn ở các JDK sau, vì vậy hãy kiểm tra tài liệu đúng phiên bản đang triển khai. Không dựa vào việc “vẫn chạy dù có warning” làm hợp đồng lâu dài.

**Điểm mấu chốt:** `--enable-native-access` không quét bytecode native, không kiểm tra chữ ký số thư viện, không sandbox C/C++, không xác nhận `FunctionDescriptor` và không ngăn một hàm native cố ý đọc/ghi bộ nhớ mà tiến trình được phép truy cập.

## 3. Vì sao Linker không thể tự xác nhận chữ ký hàm C?

Xét hàm chuẩn C:

~~~c
size_t strlen(const char *s);
~~~

Một symbol động thường cung cấp **tên và địa chỉ**, không mang theo metadata chuẩn để Java biết chắc nó nhận một `char*` và trả `size_t`. Thông tin ABI (Application Binary Interface) phụ thuộc hệ điều hành, kiến trúc, compiler và cách biên dịch thư viện. `Linker.nativeLinker()` hiểu quy ước gọi của nền tảng hiện tại, nhưng **không biết prototype thật** của symbol mà ứng dụng chọn.

Với lời gọi qua FFM, người viết phải tự mô hình hóa đúng:

- **Kiểu trả về và kiểu từng đối số:** `int`, `long`, `size_t`, `double`, pointer, cấu trúc trả về theo giá trị.
- **Độ rộng/độ căn chỉnh theo ABI:** ví dụ C `long` thường là 64 bit trên Linux/x64 nhưng 32 bit trên Windows/x64; `size_t` thường 64 bit trên hai nền tảng 64 bit này. Không suy ra C `long` từ Java `long` theo tên.
- **Con trỏ:** `char *` thường được biểu diễn bởi `ValueLayout.ADDRESS` và carrier Java là `MemorySegment`; vẫn phải thỏa thuận về encoding, kết thúc chuỗi bằng NUL, chiều dài hợp lệ, nullability, quyền sở hữu và thời gian sống.
- **Struct/union/array:** layout phải phản ánh padding, alignment và quy tắc truyền/nhận struct của ABI, không chỉ cộng kích thước từng trường.
- **Hàm biến đối số và callback:** cần xét quy tắc promotions/`Linker.Option.firstVariadicArg`, calling convention, callback function pointer, việc giữ callback còn sống và luồng được phép gọi.
- **C++:** export tên symbol, name mangling, ABI, exception và object layout không được suy ra từ chữ ký Java. Thường nên tạo một lớp giao diện `extern "C"` có hợp đồng ổn định nếu phải dùng FFM với thư viện C++.

`linker.canonicalLayouts().get("size_t")` giúp lấy layout C theo ABI hiện tại. Nó **không** kiểm chứng rằng symbol đã chọn thực sự trả `size_t`; sự tương ứng đó vẫn phải căn cứ vào header/API contract của thư viện.

## 4. Ví dụ đúng: gọi `strlen` qua FFM trên Linux/x86-64

Điều kiện: **JDK 22+**, ví dụ này nhắm **Linux x86-64** với `strlen` có sẵn trong default lookup, `size_t` rộng 64 bit. Trên hệ điều hành/ABI khác, phải xác nhận cách tìm thư viện và mapping kiểu C trước khi sử dụng.

Lưu tệp **`SafeNativeCall.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public class SafeNativeCall {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MethodHandle strlen = linker.downcallHandle(
                linker.defaultLookup().findOrThrow("strlen"),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS
                )
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom("Java");
            long length = (long) strlen.invokeExact(cString);
            System.out.println(length);
        }
    }
}
~~~

Biên dịch và chạy trong cùng môi trường:

~~~bash
javac SafeNativeCall.java
java --enable-native-access=ALL-UNNAMED SafeNativeCall
~~~

Kết quả chuẩn dự kiến trên môi trường đã nêu:

~~~text
4
~~~

Giải thích từng khâu:

1. `defaultLookup().findOrThrow("strlen")` tìm **địa chỉ** hàm trong những thư viện mà native linker của nền tảng phơi bày.
2. `FunctionDescriptor.of(JAVA_LONG, ADDRESS)` mô tả lời gọi: trả về một giá trị 64 bit, nhận một địa chỉ. Đây là mapping phù hợp với `size_t strlen(const char *)` trên Linux/x86-64, **do tác giả ví dụ chọn từ hợp đồng C**.
3. `arena.allocateFrom("Java")` tạo vùng nhớ native chứa chuỗi UTF-8 kết thúc bằng NUL, dùng được cho lời gọi này. `Arena.ofConfined()` quản lý vòng đời vùng nhớ và ràng buộc truy cập vào thread sở hữu.
4. `invokeExact(cString)` chuyển sang native. Giá trị `4` là số **byte** của chuỗi C trước NUL; với chuỗi UTF-8 chứa ký tự đa byte, `strlen` không trả số ký tự Java/Unicode.
5. Khi thoát `try`, arena được đóng, vùng nhớ được giải phóng. Điều này an toàn ở đây vì `strlen` chỉ đọc trong thời gian lời gọi; không áp dụng máy móc cho hàm native **giữ lại pointer** sau khi trả về.

Ví dụ cho thấy một hợp đồng được mô hình hóa đúng, **không chứng minh FFM có thể tự phát hiện mọi mô tả sai**.

## 5. Ví dụ sai: mô tả của Java khác prototype C

**Đoạn sau chỉ để phân tích; KHÔNG chạy thử trên JVM hoặc dữ liệu thật.** Giả sử vẫn gọi hàm `strlen` ở trên nhưng khai báo kết quả là 32 bit:

~~~java
// SAI trên Linux/x86-64: strlen trả size_t 64 bit.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
);

// Không tạo/invoke downcall handle với descriptor sai này.
~~~

`ValueLayout.JAVA_INT` tạo giả định về giá trị trả về khác với ABI thực tế. Với input ngắn, kết quả có thể trông “đúng”, khiến lỗi ẩn; ở tình huống khác có thể bị cắt bớt hoặc gây hành vi không xác định. Các sai lệch nguy hiểm hơn gồm: khai báo thiếu/thừa tham số, coi integer là pointer, sai struct-by-value, sai ABI callback hoặc trỏ tới vùng đã giải phóng. Một sai lệch có thể dẫn đến đọc/ghi sai địa chỉ, hỏng heap/native memory hay crash JVM.

**Hai kiểu kiểm tra không thay thế nhau:**

- `WrongMethodTypeException` có thể xuất hiện nếu **Java code** gọi `invokeExact` với kiểu Java không khớp với method handle đã dựng.
- Descriptor **hợp lệ về mặt cú pháp/linker** vẫn có thể **sai so với C**. Thư viện không buộc phải trả một Java exception rõ ràng; kết quả có thể âm thầm sai hoặc khiến tiến trình sập.

Không dùng crash làm cách “kiểm chứng signature”. Hãy so đối chiếu với header và ABI, rồi kiểm thử trong môi trường được cô lập.

## 6. Thư viện được nạp thành công vẫn có thể không an toàn

Cần tách ít nhất ba khía cạnh:

**Nguồn gốc và tính toàn vẹn.** Một tệp có tên `libexample.so` hoặc `example.dll` có thể bị thay thế theo đường dẫn tìm kiếm, biến môi trường, bản phân phối hoặc thư viện phụ thuộc. Kiểm tra nhà cung cấp, phiên bản, bản build, nguồn tải, hash được đối chiếu từ kênh đáng tin và chữ ký phát hành khi có. Hash trùng với hash do chính nguồn không tin cậy cung cấp không tự tạo ra độ tin cậy.

**Hành vi khi nạp và khi chạy.** Native loader có thể kích hoạt mã khởi tạo thư viện trước khi Java gọi một hàm mong muốn (ví dụ initializer trên Unix hoặc entry point DLL trên Windows). Thư viện có thể gọi hệ điều hành, truy cập tài nguyên theo quyền của tiến trình, tạo thread, sửa memory, gọi thư viện khác hoặc gặp lỗ hổng. `--enable-native-access` không kiểm toán các hành vi này.

**Đúng hợp đồng nhưng vẫn lỗi logic.** Một `FunctionDescriptor` khớp C không ngăn C ghi quá `capacity`, giữ pointer hết hạn, dùng dữ liệu thiếu kiểm tra, không đồng bộ thread hoặc dùng phiên bản thư viện thay đổi semantics. “ABI đúng” là điều kiện cần cho lời gọi, không phải bằng chứng an toàn bảo mật.

Ví dụ giả định:

~~~c
// Chữ ký chỉ nói về kiểu, không bảo đảm hàm tôn trọng capacity.
int fill_buffer(unsigned char *out, size_t capacity);
~~~

Java có thể truyền đúng pointer và độ dài, nhưng nếu `fill_buffer` ghi `capacity + 1` byte thì quyền native, linker và kiểu Java đều không chặn được tác động ở bên trong C.

## 7. JNI có khác không?

JNI thường khai báo một phương thức Java `native` và triển khai hàm tương ứng bằng C/C++. JVM biết chữ ký phương thức **Java**; trình biên dịch C có thể kiểm tra khai báo C nếu project dùng đúng header (ví dụ header sinh bởi `javac -h`). Tuy nhiên:

- `System.load`/`System.loadLibrary` chỉ thực hiện nạp thư viện theo quy tắc tìm kiếm; nó không xác nhận thư viện vô hại.
- Kiểm tra tên hàm hoặc phương thức Java không chứng minh code C dùng đúng `JNIEnv*`, `jobject`/`jclass`, loại dữ liệu JNI, vòng đời global/local references hay quy tắc xử lý exception/thread.
- Native code chạy trong tiến trình JVM vẫn có thể gây memory corruption hoặc crash. Các ràng buộc native-access của JDK mới áp dụng cho việc nạp/liên kết liên quan đến JNI, nhưng không biến C thành bộ nhớ được Java kiểm soát.

Vì vậy, khác biệt về API giữa JNI và FFM không làm thay đổi nguyên tắc: **quyền được gọi ≠ chữ ký đúng ≠ thư viện đáng tin ≠ thực thi an toàn**.

## 8. Cách xây dựng một ranh giới native có thể kiểm chứng

Khi tích hợp thư viện thực tế, nên làm theo thứ tự:

1. **Chốt hợp đồng C trước khi viết Java.** Chọn phiên bản header và binary cùng bản build, ghi rõ tên exported symbol, kiểu/constness, ABI mục tiêu, ownership, nullability, lifetime, lỗi trả về, thread-safety và semantics. Với C++ nên đóng gói sau một giao diện C ổn định nếu khả thi.
2. **Mapping từng kiểu theo nền tảng.** So `sizeof`/`alignof`/`offsetof` của C trên chính target build; dùng `canonicalLayouts()`, cấu trúc có padding phù hợp và kiểm tra return/argument layout. Đặc biệt kiểm tra C `long`, `size_t`, `wchar_t`, struct-by-value, pointer đến pointer, hàm variadic.
3. **Giữ quyền native ở lớp adapter nhỏ.** Tập trung `Linker`/`SymbolLookup`, không để mọi phần nghiệp vụ tùy ý gọi native; grant module cụ thể khi được; không phân phối `ALL-UNNAMED` như mặc định tràn lan.
4. **Kiểm soát tệp được nạp.** Dùng bản phát hành được phê duyệt, đường dẫn rõ ràng, thư mục không cho người không tin cậy ghi; kiểm tra dependency native đi kèm; ghim phiên bản tương thích và kiểm soát cập nhật.
5. **Kiểm soát bộ nhớ và luồng.** Xác định ai cấp phát/giải phóng; không giữ `MemorySegment`/pointer qua thời điểm hết hiệu lực; kiểm tra kích thước và integer overflow; xử lý buffer length, UTF-8/NUL, null pointer và callback lifetime; không gọi từ thread sai với confined arena.
6. **Kiểm thử tại ranh giới.** Kiểm tra zero/maximum length, Unicode nhiều byte, lỗi và null theo contract, input bất thường, concurrency, version mismatch. Chạy thử integration native riêng từng OS/architecture và với binary thực tế. Khi kiểm soát được mã C, dùng ASan/UBSan hoặc công cụ tương đương cho build kiểm thử.
7. **Cô lập thư viện rủi ro cao.** Nếu không thể tin cậy thư viện, cân nhắc gọi qua một tiến trình phụ với giao thức dữ liệu và quyền OS hạn chế. Khi tiến trình phụ lỗi, JVM chính có thể quan sát và khởi động lại thay vì chia sẻ trực tiếp cùng không gian địa chỉ.
8. **Quan sát lúc vận hành.** Ghi nhận native library/version thực tế, mã lỗi/`errno` khi API yêu cầu; xem crash log JVM (`hs_err_pid...`), JFR native-library load/unload events khi hỗ trợ. Trên JDK thích hợp, dùng `jnativescan` để phát hiện dấu hiệu sử dụng JNI; nó không phải công cụ chứng nhận binary an toàn.

Một wrapper Java chỉ nên công bố API cấp cao sau khi nó đã kiểm tra tham số, sở hữu buffer rõ ràng và chuyển lỗi C thành kết quả/ngoại lệ có thể hiểu. Việc wrapper hoạt động đúng ở một môi trường không thay thế kiểm thử trên tất cả ABI mà ứng dụng hỗ trợ.

## 9. Nhận diện lỗi và hướng điều tra

| Dấu hiệu | Câu hỏi nên kiểm tra trước |
| --- | --- |
| `UnsatisfiedLinkError`, không tìm thấy symbol/thư viện | Tên, thư mục, kiến trúc, phiên bản, dependency, export; không suy ra rằng chữ ký đúng khi lỗi được sửa |
| Cảnh báo native access hoặc `IllegalCallerException` | Module nào gọi restricted method, JDK/chính sách nào đang chạy, đã cấp quyền đúng phạm vi chưa |
| `WrongMethodTypeException` | Carrier và kiểu Java ở `invokeExact` có khớp `MethodType` được tạo từ descriptor không |
| Kết quả sai ở 32/64 bit hoặc chỉ sai trên một OS | `size_t`/`long`, signedness, packing/alignment, calling convention và version ABI |
| Crash JVM, dữ liệu hỏng hoặc lỗi không ổn định | Descriptor sai, pointer/lifetime, native buffer overflow, callback/thread, lỗi thực thi trong thư viện; phân tích crash log và native debugging trong môi trường cô lập |
| Library có tên đúng nhưng xuất hiện hành vi lạ | Đường dẫn binary thực tế, hash/ký phát hành, dependency transitively loaded, quyền tiến trình và khả năng bị thay thế binary |

`IllegalCallerException` là dấu hiệu **quyền**; `WrongMethodTypeException` là dấu hiệu **kiểu phía Java**; cả hai không đại diện cho việc kiểm chứng toàn bộ hợp đồng C hay tính an toàn native.

## 10. Tự kiểm tra hiểu biết

**Tình huống A.** Bật `--enable-native-access=ALL-UNNAMED`, `findOrThrow` thấy symbol và `downcallHandle` tạo thành công. Có được kết luận `FunctionDescriptor` khớp prototype C? **Không.** Cần header/build ABI tương ứng và kiểm thử; linker không thể tự suy ra kiểu và số đối số từ địa chỉ symbol.

**Tình huống B.** `strlen("Tiếng Việt")` qua FFM trả số khác với `String.length()`. Có nhất thiết là lỗi signature? **Không.** `strlen` đếm byte UTF-8 trước NUL, còn `String.length()` đếm UTF-16 code units; cần phân biệt representation trước khi chẩn đoán.

**Tình huống C.** Thư viện được ký bởi nhà cung cấp hợp lệ, và C header trùng layout Java. Có thể xem là tuyệt đối an toàn? **Không.** Nguồn gốc đáng tin và ABI đúng giảm một nhóm rủi ro; vẫn phải xem lỗi bộ nhớ, input, dependency, quyền thực thi, quản lý lifecycle và phạm vi cô lập.

**Tình huống D.** Một phương thức C lưu `char*` đầu vào để dùng sau khi trả về. Có nên truyền pointer từ `Arena.ofConfined()` rồi đóng arena ngay? **Không.** Phải theo contract giữ pointer, bảo đảm vùng nhớ tồn tại đến khi native hoàn tất và có cơ chế kết thúc ownership rõ ràng.

## Tài liệu tra cứu

- [JDK 25 – Linker API và Safety considerations](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [JDK 25 – Restricted Methods và native access](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)
- [dev.java – Foreign Function and Memory API](https://dev.java/learn/api/io/ffm/)
- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)

**Kết luận thực hành:** Cấp quyền native là quyết định *cho phép vượt ranh giới quản lý của JVM*. Chữ ký C/ABI, độ tin cậy của binary và an toàn bộ nhớ phải được xác minh bằng các cơ chế độc lập; không có cờ cấp quyền nào làm thay công việc đó.