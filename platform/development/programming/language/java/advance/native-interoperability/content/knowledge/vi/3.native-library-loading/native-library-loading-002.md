# Phân biệt `System.load` (đường dẫn tuyệt đối) và `System.loadLibrary` (tên thư viện) trong Java

## 1. Bài toán: JVM cần nạp một thư viện native

Khi chương trình Java gọi mã C/C++ qua **JNI (Java Native Interface)**, JVM phải nạp thư viện native tương ứng vào tiến trình trước khi liên kết và thực thi phương thức `native`. Trên các hệ điều hành thông dụng, thư viện động thường có đuôi `.dll` (Windows), `.so` (Linux), `.dylib` (macOS). Hai API tiêu chuẩn để nạp thư viện là:

```java
System.load("/duong/dan/tuyet/doi/den/thu-vien.so");
System.loadLibrary("tenThuVien");
```

**Khác biệt cốt lõi:** `System.load` nhận **đường dẫn tuyệt đối đến thư viện**; `System.loadLibrary` nhận **tên logic của thư viện**, để JVM tìm và ánh xạ sang tệp/phần triển khai native phù hợp.

Cả hai đều là phương thức `static void` của `java.lang.System`, cuối cùng ủy quyền cho các API tương ứng trong `java.lang.Runtime`. Cả hai đều nạp mã native vào **cùng tiến trình JVM**; chúng không khởi chạy một chương trình con. Hai phương thức khác nhau chủ yếu ở **cách chỉ định và tìm thư viện**, không phải ở cách JNI gọi một hàm C sau khi thư viện đã được nạp thành công.

## 2. Bảng đối chiếu trực tiếp

| Tiêu chí | `System.load(String filename)` | `System.loadLibrary(String libname)` |
| --- | --- | --- |
| Đối số | Tên tệp/đường dẫn **tuyệt đối** của thư viện | **Tên logic** thư viện, không kèm đường dẫn, tiền tố và phần mở rộng đặc thù hệ điều hành |
| Ví dụ Linux | `System.load("/opt/demo/native/libnativeops.so")` | `System.loadLibrary("nativeops")` |
| Ví dụ Windows | `System.load("C:\\apps\\demo\\nativeops.dll")` | `System.loadLibrary("nativeops")` |
| Tìm tệp đích | Dựa trên đường dẫn cụ thể do chương trình cung cấp | JVM/`ClassLoader` tìm thư viện theo tên, bao gồm cơ chế `findLibrary` và đường dẫn thư viện (`java.library.path`) phù hợp |
| Tên tệp `.dll`/`.so`/`.dylib` | Lập trình viên chỉ rõ, hoặc chủ động tạo bằng `System.mapLibraryName` | JVM ánh xạ tên logic sang tên thư viện native thích hợp |
| Đổi thư mục đặt thư viện | Cần thay giá trị đường dẫn đưa vào `load` | Có thể thay cấu hình tìm thư viện, ví dụ `-Djava.library.path=...` khi khởi động |
| Tính di động của lời gọi | Thấp hơn nếu hard-code đường dẫn/đuôi tệp; có thể cải thiện bằng `Path` và `mapLibraryName` | Cao hơn ở mức mã Java; vẫn cần thư viện native biên dịch cho từng hệ điều hành/CPU |
| Tình huống phù hợp | Biết chính xác tệp đã đóng gói/giải nén và muốn nạp tệp đó | Muốn gọi một thư viện native theo tên và cấu hình vị trí khi triển khai |

**Đừng hiểu nhầm:** `loadLibrary` không thể biến một tệp Linux `.so` thành DLL Windows. Ở mỗi nền tảng vẫn phải cung cấp binary đúng hệ điều hành, kiến trúc CPU, ABI và các thư viện phụ thuộc.

## 3. `System.load`: biết chính xác tệp cần nạp

Chữ ký:

```java
public static void load(String filename);
```

Đối số `filename` phải là **đường dẫn tuyệt đối**. Ví dụ trên Linux:

```java
System.load("/opt/myapp/native/libnativeops.so");
```

Trên Windows, nếu viết chuỗi Java với dấu `\` thì phải escape thành `\\`:

```java
System.load("C:\\apps\\myapp\\nativeops.dll");
```

Dòng dưới đây **không hợp lệ** vì là đường dẫn tương đối, dù tệp có tồn tại:

```java
System.load("./native/libnativeops.so");
```

Với tệp thư viện động thông thường, lời gọi này gây `UnsatisfiedLinkError` do đối số không phải đường dẫn tuyệt đối.

### 3.1. Tạo đường dẫn tuyệt đối bằng `Path`

Không cần hard-code `/` hay `\`. Nếu ứng dụng cố ý đặt thư viện trong thư mục `native` bên dưới thư mục làm việc, có thể viết:

```java
import java.nio.file.Path;

Path library = Path.of(
        "native",
        System.mapLibraryName("nativeops")
).toAbsolutePath().normalize();

System.load(library.toString());
```

- `System.mapLibraryName("nativeops")` tạo tên tệp native theo quy ước của nền tảng hiện tại.
- `Path.of(...)` tạo đường dẫn một cách độc lập với ký tự phân cách thư mục của hệ điều hành.
- `toAbsolutePath()` chuyển đường dẫn tương đối dựa trên **thư mục làm việc của tiến trình** (thường liên quan `user.dir`); `normalize()` xử lý các thành phần `.` và `..` theo cú pháp.
- `System.load(...)` nhận một đường dẫn tuyệt đối. Đoạn code này **chỉ thành công nếu tệp thật sự nằm đúng vị trí** và các điều kiện nạp binary được đáp ứng.

`normalize()` không bảo đảm tệp tồn tại, không xác thực chữ ký thư viện và cũng không khắc phục một binary sai kiến trúc. Nếu vị trí thư viện có thể bị thay đổi bởi dữ liệu không tin cậy, phải kiểm soát đường dẫn và nguồn gốc tệp trước khi nạp.

### 3.2. Khi nào `load` có lợi?

- Ứng dụng tự giải nén thư viện native đã đóng gói ra một thư mục cụ thể được quản lý.
- Thư viện nằm tại đường dẫn cố định theo quy trình triển khai (ví dụ thư mục native của ứng dụng), và cần chỉ định tệp chính xác.
- Có nhiều biến thể/phiên bản thư viện, cần chọn một tệp đã được kiểm tra tương thích trước khi nạp.
- Không muốn phụ thuộc vào việc JVM có tìm đúng thư viện đích trong tập đường dẫn tìm kiếm theo tên hay không.

`System.load` **không cần `java.library.path` để xác định chính thư viện đích**. Tuy nhiên thư viện đích có thể còn phụ thuộc vào những thư viện native khác; các dependency đó vẫn do bộ nạp thư viện của hệ điều hành giải quyết theo quy tắc riêng.

## 4. `System.loadLibrary`: giao tên logic cho JVM tìm kiếm

Chữ ký:

```java
public static void loadLibrary(String libname);
```

Cách dùng điển hình:

```java
static {
    System.loadLibrary("nativeops");
}
```

Đối số `nativeops` là **tên logic**. Theo quy ước thông dụng, với cùng tên ấy JVM có thể tìm:

| Nền tảng | Tên tệp thư viện thông dụng |
| --- | --- |
| Windows | `nativeops.dll` |
| Linux | `libnativeops.so` |
| macOS | `libnativeops.dylib` |

Hãy dùng `System.mapLibraryName("nativeops")` để lấy tên tệp theo quy tắc của JVM hiện hành thay vì tự nối `lib`/đuôi tệp trong code.

Những lời gọi sau **sai về cách truyền đối số**, không phải cách gọi thông thường của `loadLibrary`:

```java
System.loadLibrary("libnativeops.so");         // Sai: tên tệp có prefix/extension
System.loadLibrary("/opt/demo/libnativeops.so"); // Sai: chứa đường dẫn
System.loadLibrary("native/nativeops");         // Sai: chứa phân cách đường dẫn
```

Trái lại, `System.loadLibrary("nativeops")` đúng cú pháp nhưng **chưa chắc nạp được** nếu thư viện thiếu, sai kiến trúc, thiếu dependency, không tương thích hoặc thư mục tìm kiếm chưa đúng.

### 4.1. JVM tìm thư viện ở đâu?

Để hiểu chính xác, có hai cơ chế cần phân biệt:

1. JVM có thể hỏi `ClassLoader.findLibrary(String libname)` của class loader liên quan để lấy **đường dẫn tuyệt đối** của thư viện. Cơ chế này đặc biệt hữu ích cho những framework/class loader tự quản lý thư viện native.
2. Với triển khai JDK thông dụng, nếu `findLibrary` trả về `null`, JVM tìm theo đường dẫn thư viện được cấu hình trong **`java.library.path`**, cùng các quy tắc tìm thư viện của nền tảng/triển khai. Java không hứa rằng mọi JVM sử dụng cùng một thứ tự tìm kiếm nội bộ.

Ví dụ cấu hình khi khởi chạy:

```bash
java -Djava.library.path=/opt/myapp/native -cp app.jar com.example.Main
```

Lưu ý:

- `-Djava.library.path=...` là **tùy chọn JVM**; đặt trước tên lớp hoặc `-jar` khi chạy.
- `java.library.path` là đường dẫn tìm kiếm **thư viện native**, khác với `-cp`/`CLASSPATH` dùng để tìm **lớp và tài nguyên Java**.
- Không giả định rằng `System.setProperty("java.library.path", "...")` **sau khi JVM đã khởi động** sẽ khiến cơ chế nạp thư viện cập nhật ngay: kết quả phụ thuộc triển khai, có thể có cache. Hãy cấu hình ngay từ lúc khởi động hoặc dùng `System.load` với đường dẫn đã được xác định.
- Việc một tệp `.so`/`.dll` được đặt trong JAR thông thường **không có nghĩa JVM tự nạp trực tiếp tệp đó từ JAR**. Khi cần, giải nén ra tệp phù hợp và nạp bằng cơ chế đã lựa chọn.
- Đường dẫn tìm thư viện đích của JVM khác với đường dẫn tìm **thư viện phụ thuộc** của loader hệ điều hành; xem phần xử lý lỗi bên dưới.

## 5. Ví dụ JNI chạy được: cùng một thư viện, hai cách nạp

Ví dụ dùng **Java 17+**, C và JNI để minh họa rằng cả hai API đều dẫn đến cùng hàm native sau khi nạp thành công. Với Java 17–23, chạy như phần hướng dẫn. Với JDK 24 trở lên, xem thêm tùy chọn quyền native access ở mục 7.

### 5.1. Tạo `NativeLoadDemo.java`

```java
import java.nio.file.Path;

public final class NativeLoadDemo {
    static {
        String mode = System.getProperty("load.mode", "name");

        if ("absolute".equals(mode)) {
            Path library = Path.of(
                    "native",
                    System.mapLibraryName("nativeops")
            ).toAbsolutePath().normalize();
            System.load(library.toString());
        } else if ("name".equals(mode)) {
            System.loadLibrary("nativeops");
        } else {
            throw new IllegalArgumentException(
                    "Unsupported load.mode: " + mode
            );
        }
    }

    private NativeLoadDemo() {
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println(add(20, 22));
    }
}
```

Ở chế độ mặc định `name`, chương trình gọi `System.loadLibrary("nativeops")`. Khi chạy với `-Dload.mode=absolute`, chương trình tự tạo đường dẫn tuyệt đối đến tệp dưới thư mục `native` rồi gọi `System.load(...)`.

`add` là phương thức JNI; khai báo `native` thông báo cho JVM rằng phần thân đến từ hàm native. Giá trị `20 + 22` được chọn để kết quả dễ kiểm tra. Hai **lần chạy là hai tiến trình JVM độc lập**, mỗi lần chỉ thực hiện **một** trong hai cách nạp.

### 5.2. Tạo header JNI và `NativeLoadDemo.c`

Sau khi lưu `NativeLoadDemo.java`, biên dịch:

```bash
javac -h . NativeLoadDemo.java
```

Lệnh tạo `NativeLoadDemo.class` và header `NativeLoadDemo.h`. Tiếp theo tạo tệp `NativeLoadDemo.c`:

```c
#include "NativeLoadDemo.h"

JNIEXPORT jint JNICALL Java_NativeLoadDemo_add(
        JNIEnv *env, jclass declaringClass, jint a, jint b) {
    (void) env;
    (void) declaringClass;
    return a + b;
}
```

Header do `javac -h` sinh ra khai báo `jni.h` và chữ ký hàm `Java_NativeLoadDemo_add` đúng với lớp/method. Vì `add` là `static`, tham số JNI ẩn thứ hai là `jclass`; hai đối số `int` của Java tương ứng hai `jint` trong C. Đây là ví dụ độc lập, không cần lớp/package Java khác.

### 5.3. Biên dịch và chạy trên Linux

Điều kiện: `JAVA_HOME` trỏ đến JDK, máy có GCC, và các lệnh chạy trong thư mục chứa hai tệp nguồn:

```bash
mkdir -p native
javac -h . NativeLoadDemo.java
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  NativeLoadDemo.c -o native/libnativeops.so

# Cách 1: nạp theo tên từ thư mục tìm kiếm
java -Djava.library.path=native NativeLoadDemo

# Cách 2: nạp theo đường dẫn tuyệt đối do Java tạo
java -Dload.mode=absolute NativeLoadDemo
```

### 5.4. Biên dịch và chạy trên macOS

Điều kiện: `JAVA_HOME` trỏ đến JDK, có Clang/Xcode Command Line Tools:

```bash
mkdir -p native
javac -h . NativeLoadDemo.java
clang -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  NativeLoadDemo.c -o native/libnativeops.dylib

java -Djava.library.path=native NativeLoadDemo
java -Dload.mode=absolute NativeLoadDemo
```

### 5.5. Biên dịch và chạy trên Windows

Mở **x64 Native Tools Command Prompt for Visual Studio** tương ứng với JDK x64, cấu hình `JAVA_HOME` trỏ đến JDK, rồi dùng `cmd.exe`:

```bat
mkdir native
javac -h . NativeLoadDemo.java
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" NativeLoadDemo.c /link /OUT:native\nativeops.dll

java -Djava.library.path=native NativeLoadDemo
java -Dload.mode=absolute NativeLoadDemo
```

**Đầu ra chuẩn (stdout)** của *mỗi lần chạy* khi nạp thành công:

```text
42
```

Ví dụ sử dụng tên thư viện `nativeops` một cách nhất quán: Java dùng `System.mapLibraryName("nativeops")` khi cần đường dẫn, còn tên file xuất ra ở ba hệ điều hành tuân theo quy ước JNI thông dụng. Cách `loadLibrary` tìm file do `-Djava.library.path=native` chỉ định; cách `load` đã chủ động dựng vị trí `native/<tên-tệp>` thành đường dẫn tuyệt đối nên không cần tùy chọn đó.

**Ranh giới của ví dụ:** ví dụ JNI hoàn chỉnh chỉ làm phép cộng để kiểm tra khâu nạp và liên kết. Nó không nhằm chứng minh mã C nhanh hơn Java, cũng không mô tả toàn bộ chi tiết phân phối SDK native trong sản phẩm thật.

## 6. Lỗi thường gặp: nhận diện nguyên nhân và cách xử lý

### 6.1. `UnsatisfiedLinkError` với `System.load`

**Tình huống:** truyền đường dẫn tương đối:

```java
System.load("native/libnativeops.so"); // Sai vì không phải đường dẫn tuyệt đối
```

**Giải pháp:** dùng `Path.toAbsolutePath()` như ví dụ hoặc truyền một đường dẫn tuyệt đối thực sự. Đừng nhầm “tệp có tồn tại” với “đường dẫn đã là tuyệt đối”; đó là hai điều kiện khác nhau.

**Tình huống khác:** đường dẫn tuyệt đối nhưng tệp không tồn tại, không đọc được, sai kiến trúc, không phải thư viện native hợp lệ, hoặc thiếu dependency. Khi ấy cần kiểm tra **tệp, quyền truy cập, binary và hệ thống thư viện phụ thuộc**, thay vì chỉ sửa cú pháp đường dẫn.

### 6.2. `UnsatisfiedLinkError: no ... in java.library.path`

**Tình huống:** gọi `System.loadLibrary("nativeops")` nhưng thư viện không nằm trong vị trí JVM đang tìm.

**Giải pháp:**

- Kiểm tra `System.mapLibraryName("nativeops")` trả tên gì và file thực tế có tên tương ứng không.
- Truyền `-Djava.library.path=/thu/muc/chua/thu/vien` ngay khi khởi động, hoặc triển khai `ClassLoader.findLibrary` nếu đó là cơ chế nạp của framework.
- Kiểm tra tên truyền vào `loadLibrary` là tên **logic**, không chứa `lib`/đuôi tệp và không chứa ký tự phân cách thư mục.
- Xác minh đường dẫn cấu hình được JVM dùng. Có thể quan sát bằng `System.getProperty("java.library.path")` hoặc `java -XshowSettings:properties -version`; đầu ra cài đặt JVM có thể nằm ở stderr.

Nội dung/chữ của thông báo lỗi cụ thể có thể thay đổi theo JDK, JVM và OS. Đừng lập trình dựa trên việc so khớp nguyên văn thông báo.

### 6.3. Đã tìm thấy thư viện chính nhưng vẫn nạp thất bại

Giả sử `libnativeops.so` phụ thuộc vào `libvendor.so`. Khi `nativeops` đã nằm trong `java.library.path`, JVM **vẫn có thể** nạp thất bại nếu linker của Linux không tìm thấy `libvendor.so`.

Cần phân biệt:

- **JVM tìm thư viện chính:** `java.library.path` và `ClassLoader.findLibrary` có vai trò trong `System.loadLibrary`.
- **Loader hệ điều hành tìm dependency:** chịu chi phối bởi cơ chế liên kết/đường dẫn riêng, ví dụ RUNPATH/RPATH và cấu hình hệ thống trên Linux, cơ chế `@rpath` trên macOS, hay thứ tự tìm DLL trên Windows.

Công cụ hỗ trợ chẩn đoán: `ldd` trên Linux (chỉ dùng với binary tin cậy), `otool -L` trên macOS, `dumpbin /DEPENDENTS` trên Windows nếu có Visual Studio tools. Chỉ thêm `-Djava.library.path` không bảo đảm giải quyết mọi dependency lỗi.

### 6.4. Thư viện đã nạp nhưng không liên kết được phương thức native

Nếu thư viện load thành công mà lời gọi `add(...)` vẫn gây `UnsatisfiedLinkError`, kiểm tra tên ký hiệu JNI, package/class, chữ ký/overload, kiểu trả về, thư viện chứa đúng hàm được xuất hay chưa. Với JNI, nên sinh header bằng:

```bash
javac -h . NativeLoadDemo.java
```

và triển khai theo header, thay vì tự đoán tên ký hiệu. **Nạp được DLL/.so** và **tìm đúng hàm JNI** là hai bước khác nhau.

### 6.5. Kiến trúc không tương thích và class loader

- JVM x64 cần binary tương thích x64; DLL ARM hoặc thư viện dùng ABI không tương thích có thể không nạp được.
- Nếu cùng một thư viện JNI được cố nạp từ các **class loader khác nhau**, JVM có thể báo thư viện đã được nạp ở class loader khác. Việc gọi lại trong cùng bối cảnh không đồng nghĩa được phép chia sẻ mọi JNI library qua các class loader.
- Không tùy tiện chuyển sang tên file có đuôi `.so.1`, `.so.2` hoặc tùy chỉnh quy ước. Với tên tệp khác thông lệ, hãy hiểu cơ chế liên kết/symlink của hệ điều hành và cân nhắc `System.load` theo tệp cụ thể.

## 7. Lưu ý khi triển khai trên JDK hiện đại

Từ **JDK 24**, các thao tác tải thư viện/native access qua JNI, bao gồm `System.load` và `System.loadLibrary`, thuộc cơ chế **native-access restrictions**. Nếu quyền chưa được bật, JDK có thể phát cảnh báo hoặc từ chối theo phiên bản/cấu hình `--illegal-native-access`.

Với chương trình chạy trên **classpath** như `NativeLoadDemo`, có thể cấp quyền rõ ràng (dùng trên JDK hỗ trợ tùy chọn này):

```bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=native NativeLoadDemo
java --enable-native-access=ALL-UNNAMED -Dload.mode=absolute NativeLoadDemo
```

Trong ứng dụng đã module hóa, nên chỉ bật native access cho **module cụ thể** cần dùng, thay vì toàn bộ `ALL-UNNAMED`. Các ví dụ Java 17 dùng lệnh ở mục 5; không giả định mọi phiên bản JDK cũ đều nhận tùy chọn native access mới.

**Bảo mật:** việc nạp thư viện native thực thi mã máy với quyền của tiến trình JVM. Dù gọi bằng tên hay bằng đường dẫn, ứng dụng cần xác minh nguồn gốc binary, quyền ghi vào thư mục thư viện và phiên bản/dependency. Đường dẫn tuyệt đối giúp **chọn đúng tệp** nhưng **không tự xác thực tệp an toàn**; tìm kiếm theo tên thuận tiện nhưng cần tránh thư mục có thể bị chèn binary không tin cậy.

## 8. Khi nào chọn cách nào trong dự án thực tế?

**Chọn `System.load`** khi:

1. Bạn đã có **đường dẫn tuyệt đối đến đúng tệp** (ví dụ sau khi giải nén binary theo OS/CPU).
2. Bạn muốn ứng dụng kiểm soát rõ thư viện nào được nạp và có thể ghi log/chẩn đoán đường dẫn đó.
3. Bạn quản lý cả đường dẫn, tên file, phiên bản và quyền truy cập của thư viện trong quy trình đóng gói.

**Chọn `System.loadLibrary`** khi:

1. Chỉ cần một **tên logic ổn định** (`"nativeops"`) trên nhiều hệ điều hành.
2. Bộ cài/triển khai sẽ cấu hình vị trí tìm thư viện thông qua JVM hoặc class loader.
3. Không cần gắn đường dẫn tuyệt đối vào code Java; tên thư viện tuân thủ quy tắc ánh xạ của JVM.

**Không chọn chỉ dựa trên “phương thức nào nhanh hơn”.** Sau khi đã nạp và liên kết, cả hai phương thức có thể dẫn đến cùng hàm JNI; yếu tố khác biệt chủ yếu là quản lý phân phối, tìm thư viện, kiểm soát phiên bản và xử lý lỗi. Hai phương thức đều có thể phát sinh lỗi khi nạp binary không hợp lệ.

### Quy tắc nhớ nhanh

- Có **tên** `nativeops` → `System.loadLibrary("nativeops")`.
- Có **đường dẫn tuyệt đối** `/opt/app/native/libnativeops.so` → `System.load("/opt/app/native/libnativeops.so")`.
- Có **đường dẫn tương đối** → chuyển thành tuyệt đối trước khi gọi `load`, hoặc cấu hình thư mục tìm kiếm để dùng `loadLibrary`.
- `java.library.path` giúp JVM tìm **thư viện theo tên**; không phải Java classpath và không phải câu trả lời cho mọi dependency native.

## 9. Câu hỏi tự kiểm tra

**1. Vì sao `System.loadLibrary("/usr/lib/libabc.so")` sai?** Vì phương thức nhận **tên logic**, không nhận đường dẫn hay tên file kèm prefix/extension. Nếu đã biết đường dẫn tuyệt đối tới `libabc.so`, sử dụng `System.load("/usr/lib/libabc.so")` (với giả thiết tệp có tồn tại và tương thích).

**2. Vì sao `System.load("libabc.so")` sai dù thư viện ở thư mục hiện hành?** Vì `load` yêu cầu **đường dẫn tuyệt đối**. Có thể dùng `Path.of("libabc.so").toAbsolutePath().toString()` nếu chủ đích dùng thư mục hiện hành.

**3. `System.loadLibrary("abc")` trên Linux có nhất thiết tải đúng `libabc.so` không?** Không: đó là tên tệp động thông dụng, nhưng nạp thành công còn phụ thuộc thư viện phù hợp có nằm trên đường dẫn tìm kiếm không, quy tắc JVM/class loader và dependency của binary. Có trường hợp thư viện liên kết tĩnh và quy tắc triển khai riêng.

**4. Sửa `System.setProperty("java.library.path", "/new")` ngay trước `loadLibrary` có chắc thành công?** Không được bảo đảm. Hãy cấu hình từ lúc khởi động với `-Djava.library.path` hoặc dùng `load` sau khi xác định đường dẫn tuyệt đối.

**5. Hai phương thức có đảm bảo an toàn bộ nhớ hơn JNI không?** Không. Cả hai chỉ phục vụ việc nạp thư viện. Mã native và cơ chế quản lý bộ nhớ/ABI/JNI vẫn phải đúng, và lỗi native có thể ảnh hưởng toàn bộ tiến trình JVM.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — `System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): chữ ký `load`, `loadLibrary` và `mapLibraryName`.
- [Oracle Java 17 — `Runtime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): yêu cầu đường dẫn tuyệt đối của `load`, tên logic của `loadLibrary`, hành vi và lỗi.
- [Oracle Java 17 — `ClassLoader.findLibrary`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String)): cơ chế class loader xác định đường dẫn thư viện, liên quan `java.library.path`.
- [Oracle Java 17 — JNI Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): nạp thư viện, liên kết native method và vòng đời JNI.
- [OpenJDK — JEP 472](https://openjdk.org/jeps/472): native-access restrictions đối với JNI từ JDK 24.