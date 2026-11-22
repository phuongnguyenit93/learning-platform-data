# Native library trong JMOD

Native library là thư viện được biên dịch thành mã máy dành cho một hệ điều hành và kiến trúc CPU cụ thể. Java có thể gọi mã native thông qua JNI (Java Native Interface), một số thư viện trung gian như JNA, hoặc các API native access phù hợp với phiên bản JDK. Trong hệ sinh thái module của Java, JMOD có thể đóng gói native library cùng với lớp Java để công cụ liên kết runtime sử dụng.

Bài này tập trung vào vai trò của native library trong JMOD: cách chuẩn bị thư viện native, đưa nó vào JMOD bằng `jmod --libs`, kiểm tra và trích xuất archive, rồi liên kết module thành runtime image bằng `jlink`. Cần phân biệt việc đóng gói file native với việc Java nạp và gọi được thư viện đó: JMOD chỉ lưu trữ artifact, còn mã Java, native ABI, đường dẫn nạp và nền tảng chạy phải tương thích.

## 1. Native library là gì?

Native library là mã đã được biên dịch cho hệ điều hành/CPU đích. Một số định dạng thường gặp:

| Nền tảng | Tên file thường gặp |
|---|---|
| Windows | `acme.dll` |
| Linux | `libacme.so` |
| macOS | `libacme.dylib` |

Khác với file `.class` chứa bytecode Java, native library chứa mã máy mà hệ điều hành nạp vào tiến trình. Thư viện có thể cung cấp chức năng xử lý ảnh, mã hóa, giao tiếp thiết bị, xử lý âm thanh, gọi thư viện hệ thống hoặc tận dụng mã C/C++ đã có.

Một native library thường được gọi là shared library hoặc dynamic library. File tĩnh như `.a` trên Linux/macOS hoặc `.lib` dạng static library trên Windows thường được liên kết vào shared library trong quá trình build native; JVM không nạp trực tiếp file static archive đó bằng `System.loadLibrary`.

Native library phụ thuộc vào:

- Hệ điều hành và định dạng binary.
- Kiến trúc CPU, ví dụ x86-64 hoặc AArch64.
- ABI và calling convention của compiler/native toolchain.
- Các thư viện hệ thống hoặc shared library khác mà nó liên kết tới.
- Phiên bản JNI/API native mà nó sử dụng.

Vì vậy, một file `.so` build cho Linux x86-64 không thể dùng thay cho `.dll` trên Windows hoặc binary AArch64. Chỉ đổi tên file không thể chuyển đổi binary giữa các nền tảng.

## 2. JMOD lưu native library ở đâu?

JMOD là định dạng archive dành cho việc đóng gói module Java ở giai đoạn phát triển và liên kết runtime. Nó có thể chứa class, resource và các thành phần bổ sung phục vụ việc tạo runtime image.

Một JMOD thường có các section như:

| Section trong JMOD | Nội dung |
|---|---|
| `classes/` | Class file, module descriptor và resource của module. |
| `lib/` | Native library được cung cấp cho module. |
| `bin/` | Native command đi kèm module. |
| `include/` | Header file, thường dùng cho tích hợp native. |
| `conf/` | File cấu hình. |
| `legal/` | Thông báo giấy phép và nội dung pháp lý. |
| `man/` | Trang hướng dẫn lệnh. |

Tùy chọn `jmod create --libs` chỉ định thư mục chứa native library để đưa vào section `lib/` của JMOD. Tùy chọn `--header-files` dành cho header file; `--cmds` dành cho native command. Không nên đặt nhầm header hoặc executable vào thư mục native library rồi kỳ vọng chúng được xử lý như cùng một loại nội dung.

Ví dụ JMOD có thể chứa:

~~~text
com.acme.nativebridge.jmod
├── classes/
│   ├── module-info.class
│   └── com/acme/nativebridge/NativeBridge.class
└── lib/
    └── libacme.so
~~~

Tên và đường dẫn entry thực tế phụ thuộc nội dung đầu vào và cách tạo JMOD. Dùng `jmod list` để xem archive cụ thể thay vì giả định mọi JMOD đều có cùng tập entry.

## 3. JMOD khác JAR như thế nào?

JAR là định dạng phổ biến để đóng gói lớp Java và resource, có thể dùng trên classpath hoặc module path khi chạy ứng dụng. JMOD được thiết kế cho quá trình phát triển module và liên kết runtime image, đồng thời hỗ trợ các section bổ sung như native libraries, commands, headers và legal notices.

| Tiêu chí | Modular JAR | JMOD |
|---|---|---|
| Chứa class và resource | Có | Có |
| Chứa module descriptor | Có thể có `module-info.class` | Có thể có trong section `classes` |
| Chứa native library theo section riêng | Không có section chuyên biệt tương đương | Có section `lib` |
| Dùng trực tiếp trên runtime module path | Có | Không phải mục đích sử dụng |
| Đầu vào cho `jlink` | Có thể | Có |
| Đóng gói header, native command và legal notices theo section | Không có cấu trúc section JMOD tương đương | Có |

Điểm quan trọng: JMOD không phải file JAR có thể chạy bằng `java -jar`. JMOD được dùng như đầu vào cho các công cụ như `jlink`. Sau khi liên kết, ứng dụng chạy bằng launcher Java trong runtime image được tạo ra.

Nếu chỉ cần phân phối một thư viện Java thuần hoặc ứng dụng Java thông thường, modular JAR thường phù hợp hơn. JMOD có ý nghĩa khi cần đóng gói thành phần phục vụ quá trình tạo runtime image, đặc biệt khi module đi kèm native library.

## 4. Java gọi native library bằng JNI

JNI cho phép phương thức Java được cài đặt bằng mã native. Một phương thức khai báo từ khóa `native` không có thân Java; JVM tìm implementation tương ứng trong native library đã được nạp.

Ví dụ module:

~~~text
native-module/
├── src/
│   ├── module-info.java
│   └── com/acme/nativebridge/NativeBridge.java
├── native/
│   ├── src/
│   │   └── acme.c
│   └── linux-x86_64/
└── build/
~~~

File `src/module-info.java`:

~~~java
module com.acme.nativebridge {
    exports com.acme.nativebridge;
}
~~~

File `src/com/acme/nativebridge/NativeBridge.java`:

~~~java
package com.acme.nativebridge;

public final class NativeBridge {
    static {
        System.loadLibrary("acme");
    }

    private NativeBridge() {
    }

    public static native String platformName();

    public static void main(String[] args) {
        System.out.println(platformName());
    }
}
~~~

Lời gọi `System.loadLibrary("acme")` yêu cầu JVM nạp thư viện theo tên logic. Trên các nền tảng thông dụng, tên logic này được ánh xạ thành tên file phù hợp, ví dụ `libacme.so` trên Linux, `libacme.dylib` trên macOS hoặc `acme.dll` trên Windows. Không truyền prefix/suffix vào đối số của `loadLibrary`.

Nếu đã có đường dẫn tuyệt đối tới file native, API `System.load("/absolute/path/to/library")` có thể được dùng thay thế. `System.load` yêu cầu đường dẫn tuyệt đối; `System.loadLibrary` nhận tên thư viện logic.

Việc khai báo phương thức `native` không tự tạo implementation. Cần biên dịch mã C/C++ thành shared library có symbol JNI tương ứng và bảo đảm binary tương thích với JVM.

## 5. Tạo JNI header và native implementation

`javac -h` tạo header C/C++ từ các phương thức native đã khai báo. Từ thư mục gốc dự án, biên dịch module và sinh header:

~~~bash
mkdir -p build/classes build/include

javac -h build/include -d build/classes src/module-info.java src/com/acme/nativebridge/NativeBridge.java
~~~

Header được sinh có tên dựa trên package và class, ví dụ:

~~~text
build/include/com_acme_nativebridge_NativeBridge.h
~~~

Tạo file `native/src/acme.c`:

~~~c
#include "com_acme_nativebridge_NativeBridge.h"

JNIEXPORT jstring JNICALL
Java_com_acme_nativebridge_NativeBridge_platformName(JNIEnv *env, jclass type) {
    return (*env)->NewStringUTF(env, "native library loaded");
}
~~~

Tên hàm JNI phải khớp quy tắc ánh xạ package, class và method của JNI. Khi tên method có overload hoặc tên chứa ký tự đặc biệt, quy tắc symbol có thể phức tạp hơn; dùng header do `javac -h` sinh để tránh tự đoán chữ ký.

Trên Linux x86-64, một lệnh minh họa để biên dịch shared library:

~~~bash
mkdir -p native/linux-x86_64

cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o native/linux-x86_64/libacme.so native/src/acme.c
~~~

Lệnh trên giả định đã cài C compiler tương thích, `JAVA_HOME` trỏ tới JDK đang dùng và các đường dẫn source/header tồn tại. Các tùy chọn native compiler thay đổi theo toolchain. Với Windows cần compiler tạo DLL và header platform trong `include/win32`; với macOS cần tạo dynamic library phù hợp và dùng header trong `include/darwin`.

`jmod` không biên dịch C/C++ và không tạo file DLL/SO/DYLIB. Công việc build native phải hoàn tất trước; `jmod` chỉ đóng gói binary đã có.

## 6. Tạo JMOD và đưa thư viện vào section lib

Sau khi đã có:

- `build/classes/module-info.class` và các class Java.
- `native/linux-x86_64/libacme.so` là shared library đã biên dịch.

Có thể tạo JMOD:

~~~bash
mkdir -p build

jmod create --class-path build/classes --libs native/linux-x86_64 --module-version 1.0.0 --target-platform linux-x86_64 build/com.acme.nativebridge.jmod
~~~

Ý nghĩa các tùy chọn:

- `create` tạo archive JMOD mới.
- `--class-path build/classes` lấy module descriptor, class và resource từ thư mục đã biên dịch.
- `--libs native/linux-x86_64` thêm native library vào section `lib/`.
- `--module-version 1.0.0` ghi phiên bản module.
- `--target-platform linux-x86_64` ghi nền tảng mục tiêu cho JMOD.
- Đối số cuối là đường dẫn JMOD đầu ra.

Thư mục `build/classes` cần chứa `module-info.class` và cây package phù hợp. Nếu thiếu module descriptor, archive có thể không đại diện cho module mà `jlink` mong đợi.

`--target-platform` chỉ ghi thông tin nền tảng mục tiêu; nó không chuyển đổi hoặc biên dịch lại native binary. Tên nền tảng cần được thống nhất trong quy trình build của dự án và phải tương ứng với binary được đóng gói. Với native code, thông thường cần tạo JMOD riêng cho từng hệ điều hành/kiến trúc được hỗ trợ.

Nếu module cần cung cấp C/C++ header cho bên tích hợp, có thể dùng `--header-files`. Nếu có native command đi kèm, dùng `--cmds`. Các loại nội dung này có section riêng và không thay thế `--libs`.

## 7. Liệt kê và mô tả native library trong JMOD

Sau khi tạo archive, kiểm tra danh sách entry:

~~~bash
jmod list build/com.acme.nativebridge.jmod
~~~

Có thể thấy các entry thuộc section classes và lib. Với ví dụ trên, entry native library sẽ nằm dưới section `lib/`.

Dùng describe để xem thông tin module:

~~~bash
jmod describe build/com.acme.nativebridge.jmod
~~~

Lệnh này hiển thị thông tin module như tên, phiên bản, các yêu cầu/exports và target platform nếu được ghi nhận. Nó không kiểm tra toàn bộ tính đúng đắn của mã native hoặc bảo đảm thư viện có thể nạp thành công.

Nếu cần kiểm tra nội dung archive trên hệ thống tệp, dùng extract:

~~~bash
jmod extract --dir build/extracted build/com.acme.nativebridge.jmod
~~~

Sau khi giải nén, có thể kiểm tra file:

~~~text
build/extracted/
├── classes/
│   ├── module-info.class
│   └── com/acme/nativebridge/NativeBridge.class
└── lib/
    └── libacme.so
~~~

Trên PowerShell, có thể xem nội dung thư mục sau khi giải nén bằng `Get-ChildItem -Recurse build/extracted`. Trên Linux/macOS, dùng `find build/extracted -type f`.

Giải nén JMOD chỉ giúp kiểm tra hoặc lấy các entry ra. Nó không tự cài native library vào hệ điều hành, không đăng ký thư viện với JVM và không tạo runtime image.

## 8. Liên kết JMOD vào runtime image bằng jlink

JMOD chứa native library được thiết kế để công cụ liên kết runtime sử dụng. `jlink` đọc các module đầu vào, giải quyết module dependency và tạo một runtime image tùy chỉnh.

Ví dụ trên Linux/macOS, nếu JDK hiện tại có thư mục `jmods` và JMOD ứng dụng nằm trong `build`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.acme.nativebridge --output build/runtime
~~~

Trên Windows, dấu phân cách giữa các thành phần module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;build" --add-modules com.acme.nativebridge --output build/runtime
~~~

`--module-path` chỉ định nơi tìm JMOD/JAR module. `--add-modules` chọn module gốc cần đưa vào image; các module phụ thuộc được giải quyết theo đồ thị module. `--output` chỉ định thư mục runtime image.

Native library thuộc module được chọn có thể được đưa vào runtime image theo bố cục nền tảng do JDK tạo. Hãy kiểm tra thư mục `lib` của image và thuộc tính `java.library.path` của runtime mới để xác nhận vị trí tìm thư viện trên nền tảng đích.

Chạy ứng dụng bằng runtime image:

~~~bash
build/runtime/bin/java -m com.acme.nativebridge/com.acme.nativebridge.NativeBridge
~~~

Output mong đợi nếu native library được liên kết, tìm thấy và nạp thành công:

~~~text
native library loaded
~~~

Trên Windows, launcher nằm tại `build/runtime/bin/java.exe`. Cần chạy runtime image trên nền tảng tương thích với JMOD và native binary được đóng gói.

## 9. JMOD không thay thế cơ chế nạp native library

Có ba bước riêng biệt:

1. **Đóng gói:** `jmod --libs` đưa binary native vào JMOD.
2. **Liên kết runtime:** `jlink` dùng JMOD khi tạo runtime image và đưa các thành phần cần thiết vào image.
3. **Nạp lúc chạy:** JVM nạp thư viện khi mã Java gọi `System.loadLibrary` hoặc `System.load`.

Nếu chỉ tạo JMOD nhưng không đưa module vào runtime image, điều đó không tự làm cho thư viện xuất hiện trên native library search path của một JVM bất kỳ. JMOD cũng không được dùng như một thư mục native library bằng cách thêm trực tiếp vào `java.library.path`.

`System.loadLibrary` tra cứu thư viện theo quy tắc native library của JVM và nền tảng. Thuộc tính `java.library.path` thể hiện các thư mục JVM dùng để tìm thư viện theo tên. Ngoài ra, shared library có thể phụ thuộc vào các thư viện native khác; dynamic loader của hệ điều hành cần tìm được những dependency đó.

Khi cần xác định đường dẫn nạp thực tế, ứng dụng có thể in:

~~~java
System.out.println(System.getProperty("java.library.path"));
~~~

Thuộc tính này giúp chẩn đoán thư viện được tìm ở đâu. Nó không chứng minh file native có đúng kiến trúc, đúng ABI hoặc đủ dependency.

## 10. Native library và target platform

Một JMOD có native library gắn với nền tảng cụ thể. Ví dụ:

| JMOD | Native binary | Nền tảng |
|---|---|---|
| com.acme.nativebridge-linux-x64.jmod | libacme.so | Linux x86-64 |
| com.acme.nativebridge-linux-aarch64.jmod | libacme.so | Linux AArch64 |
| com.acme.nativebridge-windows-x64.jmod | acme.dll | Windows x86-64 |
| com.acme.nativebridge-macos-aarch64.jmod | libacme.dylib | macOS AArch64 |

Tên file JMOD trong bảng chỉ là quy ước đặt tên của dự án. `--target-platform` cần được đặt phù hợp với nền tảng mà native binary thực sự hỗ trợ.

Một quy trình phát hành đa nền tảng thường tạo artifact riêng:

- Biên dịch Java module.
- Biên dịch native library bằng toolchain cho từng hệ điều hành/kiến trúc.
- Tạo JMOD tương ứng với native binary đó.
- Liên kết runtime image trên môi trường tương thích.
- Chạy kiểm thử nạp thư viện và kiểm thử chức năng trên từng nền tảng.

Không nên đóng gói một native binary duy nhất rồi gắn nhãn hỗ trợ nhiều hệ điều hành. Cross-compilation, nếu được sử dụng, phải do native toolchain hỗ trợ và cần kiểm thử trên target platform thật.

## 11. Header file, native command và native library khác nhau

JMOD hỗ trợ nhiều loại nội dung native, nhưng chúng phục vụ các mục đích khác nhau:

| Nội dung | Tùy chọn jmod | Vai trò |
|---|---|---|
| Shared library JNI | `--libs` | File .dll, .so hoặc .dylib mà JVM có thể nạp. |
| Header C/C++ | `--header-files` | Header để compiler/native developer sử dụng khi tích hợp. |
| Native executable/command | `--cmds` | Lệnh hệ điều hành đi kèm module. |

Ví dụ, header được sinh bởi `javac -h` có thể được đưa vào JMOD nếu module cần phân phối header cho bên build native:

~~~bash
jmod create --class-path build/classes --libs native/linux-x86_64 --header-files build/include --module-version 1.0.0 --target-platform linux-x86_64 build/com.acme.nativebridge.jmod
~~~

Header file không phải shared library và không thể nạp bằng `System.loadLibrary`. Tương tự, native command là chương trình thực thi độc lập, không phải thư viện JNI.

## 12. Lỗi thường gặp khi đóng gói và nạp native library

| Lỗi hoặc hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| `UnsatisfiedLinkError: no acme in java.library.path` | JVM không tìm thấy file thư viện theo tên logic. | Kiểm tra `System.loadLibrary`, `java.library.path` và thư mục runtime image. |
| `UnsatisfiedLinkError` báo thiếu JNI method | Native binary không có symbol JNI đúng tên/chữ ký hoặc build từ header cũ. | Sinh lại header bằng `javac -h`, kiểm tra symbol và build lại thư viện. |
| `wrong ELF class` hoặc lỗi định dạng binary | Kiến trúc/bitness của thư viện không khớp JVM hoặc hệ điều hành. | Kiểm tra kiến trúc native binary và JDK; build đúng target. |
| DLL/SO tìm thấy nhưng không nạp được | Thiếu shared library phụ thuộc hoặc ABI không tương thích. | Kiểm tra dependency bằng công cụ hệ điều hành và cung cấp đúng native dependencies. |
| JMOD có file trong `lib/` nhưng ứng dụng vẫn không tìm thấy | JMOD chưa được liên kết vào runtime image, module chưa được chọn hoặc native path không bao gồm vị trí đó. | Kiểm tra lệnh `jlink`, module path, runtime image và `java.library.path`. |
| `jlink` báo không tìm thấy module | JMOD không nằm trong module path hoặc module descriptor sai/tên module khác. | Dùng `jmod describe` và kiểm tra `--module-path`. |
| JMOD được tạo nhưng không liên kết được trên máy khác | JMOD/native library dành cho target platform khác hoặc binary không tương thích. | Tạo artifact riêng theo nền tảng và dùng JDK/linker phù hợp. |
| Chạy tốt trên máy build nhưng lỗi trên máy người dùng | Máy build có native dependency cài sẵn mà image phân phối không chứa. | Kiểm tra dependency native và đóng gói/cài đặt chúng theo chính sách sản phẩm. |

Một số lỗi native chỉ xuất hiện khi JVM thực sự nạp hoặc gọi method. Việc `jmod list` thành công chỉ chứng minh archive có thể được đọc; nó không xác minh symbol, ABI hoặc logic của native code.

## 13. An toàn và vận hành native library

Native code chạy trong cùng tiến trình với JVM và có thể truy cập bộ nhớ, tài nguyên hệ điều hành hoặc API hệ thống ở mức thấp. Một lỗi trong native code có thể làm hỏng bộ nhớ, treo tiến trình hoặc khiến JVM crash thay vì phát sinh Java exception thông thường.

Các nguyên tắc cần áp dụng:

- Chỉ đóng gói native binary từ nguồn và quy trình build được kiểm soát.
- Xác minh checksum/chữ ký artifact theo quy trình phát hành.
- Build riêng theo OS, kiến trúc và ABI được hỗ trợ.
- Kiểm tra dependency native bắc cầu, không chỉ file JNI chính.
- Kiểm thử trên runtime image cuối cùng, không chỉ trên máy phát triển có nhiều thư viện đã cài.
- Quản lý vòng đời bộ nhớ và handle native cẩn thận; không giả định garbage collector tự giải phóng mọi tài nguyên native.
- Ghi lại phiên bản compiler, native SDK và target platform để có thể tái tạo artifact.

JMOD không sandbox native library và không làm mã native an toàn hơn. Việc đưa một file vào module chỉ là tổ chức và đóng gói artifact; quyền thực thi và rủi ro của native code vẫn tồn tại.

## 14. Checklist cho quy trình JMOD có native library

Trước khi phát hành module có native code, hãy kiểm tra:

1. Module Java có `module-info.class` và class/resource cần thiết.
2. Các phương thức native có khai báo Java đúng và header JNI được sinh từ đúng phiên bản source.
3. Native library được build thành shared library đúng định dạng cho target.
4. `jmod create --libs` trỏ đúng thư mục chứa binary đã build.
5. `--target-platform` phản ánh đúng OS/CPU mục tiêu.
6. `jmod list` cho thấy native library nằm trong section `lib/`.
7. `jmod describe` hiển thị đúng module và metadata cần thiết.
8. `jlink` chọn module và tạo runtime image từ module path đúng.
9. Runtime image chứa native library ở bố cục phù hợp; `java.library.path` có thể tìm thấy nó.
10. Ứng dụng thực sự gọi được JNI method trên máy hoặc môi trường target.
11. Các shared library phụ thuộc đều có thể được dynamic loader tìm thấy.
12. CI chạy kiểm thử riêng cho từng nền tảng được hỗ trợ.

Native library trong JMOD là cách đóng gói mã native gắn với một module để phục vụ quá trình tạo runtime image. `jmod --libs` đưa shared library vào archive; `jlink` liên kết module vào runtime image; còn `System.loadLibrary` hoặc `System.load` mới là bước JVM nạp thư viện khi ứng dụng chạy. Hiểu rõ ba bước này và kiểm soát target platform, ABI, dependency cùng đường dẫn nạp sẽ giúp ứng dụng Java tích hợp native code một cách có thể kiểm tra và tái lập.
