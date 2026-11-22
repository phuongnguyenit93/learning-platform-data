# Multi-release JAR: cấu trúc META-INF/versions và lựa chọn lớp

Trong **Java Advance Compatibility Migration**, có những thư viện cần tiếp tục chạy trên Java 8 hoặc Java 11 nhưng muốn sử dụng API mới, cơ chế tối ưu hoặc cách tương tác với JDK tốt hơn khi ứng dụng chạy trên Java 17, 21 hay các phiên bản mới. Việc phát hành một JAR cho mỗi JDK làm tăng chi phí vận hành, nhưng biên dịch toàn bộ thư viện cho Java mới sẽ khiến người dùng JDK cũ gặp lỗi tải lớp.

**Multi-release JAR (MRJAR)** là cơ chế được giới thiệu ở **Java 9 theo JEP 238**, cho phép một JAR chứa **implementation cơ sở** cùng những phiên bản class/resource thay thế dành cho các Java releases cao hơn. Khi runtime hoặc công cụ hỗ trợ MRJAR truy cập một class, nó có thể chọn entry trong `META-INF/versions/<N>/` phù hợp với Java runtime thay vì luôn dùng entry nằm ở gốc JAR.

MRJAR **không phải** cơ chế tự động chuyển đổi toàn bộ thư viện sang JDK mới, cũng không phải một dạng shading hay thay đổi public API tùy ý. Nó là một **quy ước đóng gói có manifest và quy tắc lựa chọn phiên bản**, giúp duy trì một hợp đồng API chung trong khi triển khai logic chuyên biệt cho các JDK khác nhau.

Bài học giải thích cấu trúc archive, thuật toán lựa chọn lớp, manifest `Multi-Release: true`, biên dịch đúng class-file version, ví dụ Java chạy được trên nhiều JDK, cách build với `javac`/`jar` và hướng tổ chức Gradle/Maven, mối liên hệ JPMS, rủi ro đối với class loader và tools, cùng chiến lược kiểm thử khi nâng JDK.

## 1. Bài toán mà multi-release JAR giải quyết

Giả sử một thư viện mã hóa dữ liệu phải chạy trên **Java 8**, nhưng khi chạy trên **Java 17** muốn dùng `java.util.HexFormat` được bổ sung từ Java 17 để triển khai tác vụ chuyển bytes thành chuỗi hex.

Nếu viết trực tiếp:

~~~java
import java.util.HexFormat;

public final class HexCodec {
    public static String encode(byte[] input) {
        return HexFormat.of().formatHex(input);
    }
}
~~~

và biên dịch với Java 17, artifact sẽ không dùng được nguyên trạng trên Java 8: phiên bản class file và API nền tảng không đáp ứng runtime cũ.

Có những giải pháp khác:

- Chỉ sử dụng API Java 8 cho mọi runtime, từ bỏ implementation chuyên biệt.
- Phát hành artifact riêng như `hex-codec-java8.jar` và `hex-codec-java17.jar`.
- Sử dụng reflection/`MethodHandle`/runtime feature detection để gọi API mới nếu có.
- Tạo **multi-release JAR**: một API chung, implementation cơ sở Java 8 và implementation thay thế Java 17.

MRJAR phù hợp khi thư viện có **cùng public contract**, nhưng cần implementation tối ưu hoặc integration khác nhau theo JDK.

### 1.1. Một JAR, nhiều implementation

~~~text
               hexcodec-mr.jar
                       |
         +-------------+--------------+
         |                            |
         v                            v
  Base class (Java 8)       Java 17 class override
  com/example/HexCodec     META-INF/versions/17/
                            com/example/HexCodec
         |                            |
         +-------------+--------------+
                       |
                       v
                  Java runtime
           Chọn implementation phù hợp
~~~

Một JAR vật lý có thể chứa nhiều file class có cùng tên logic nhưng ở **đường dẫn archive khác nhau**. Đây là cấu trúc có chủ đích, không phải hai class trùng tên trong cùng một package directory.

### 1.2. Không phải mọi thư viện đều cần MRJAR

Nếu thư viện có thể dùng một implementation Java 8 ổn định, ít code và hiệu năng đáp ứng yêu cầu, giữ một code path thường đơn giản hơn. MRJAR tạo thêm chi phí build, test, scanning, debugging và maintenance. Chỉ áp dụng khi lợi ích từ implementation theo JDK xứng đáng.

## 2. Khái niệm cơ bản

| Thuật ngữ | Ý nghĩa |
|---|---|
| Base entry | Class/resource ở đường dẫn thông thường của JAR |
| Versioned entry | Entry thay thế dưới `META-INF/versions/N/` |
| Versioned directory | Thư mục mang số phiên bản Java như `9`, `11`, `17`, `21` |
| Multi-Release manifest attribute | Thuộc tính `Multi-Release: true` trong main section của manifest |
| Runtime feature version | Số Java release của runtime, ví dụ 17 hoặc 21 |
| Class-file major version | Số phiên bản định dạng bytecode, ví dụ 61 cho Java 17 |
| Logical resource name | Tên class/resource được yêu cầu như `com/example/HexCodec.class` |
| Physical ZIP entry | Đường dẫn thật bên trong JAR, ví dụ `META-INF/versions/17/com/example/HexCodec.class` |
| Version-aware lookup | Cơ chế tìm entry theo quy tắc MRJAR |
| Base fallback | Sử dụng entry ở gốc nếu không có override thích hợp |

**Java feature release** (17) và **class-file major version** (61) là hai hệ số khác nhau. Thư mục `META-INF/versions/17/` dùng số **17**, không dùng số **61**.

## 3. Cấu trúc thư mục chuẩn của multi-release JAR

Ví dụ một archive:

~~~text
hexcodec-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── com/
│       │       └── example/
│       │           └── codec/
│       │               └── HexCodec.class
│       └── 17/
│           └── com/
│               └── example/
│                   └── codec/
│                       └── HexCodec.class
├── com/
│   └── example/
│       └── codec/
│           └── HexCodec.class
└── README.txt
~~~

Ý nghĩa:

- `com/example/codec/HexCodec.class`: bản cơ sở, dùng khi không có override phù hợp.
- `META-INF/versions/11/com/example/codec/HexCodec.class`: bản cho Java 11 trở lên cho đến khi có bản cao hơn phù hợp.
- `META-INF/versions/17/com/example/codec/HexCodec.class`: bản cho Java 17 trở lên cho đến khi có bản cao hơn phù hợp.
- `META-INF/MANIFEST.MF`: mang dấu hiệu cho biết archive được xử lý như MRJAR.
- Các class không có bản override tiếp tục lấy từ đường dẫn cơ sở.

### 3.1. Mỗi lớp có thể có tập phiên bản khác nhau

Không bắt buộc mọi class đều có override ở mọi thư mục:

~~~text
com/example/A.class
com/example/B.class

META-INF/versions/11/com/example/A.class
META-INF/versions/17/com/example/B.class
~~~

Trên Java 17, `A` có thể được chọn từ bản 11, còn `B` được chọn từ bản 17. **Quy tắc lựa chọn áp dụng theo từng tên class/resource được yêu cầu**, không có một “version duy nhất cho toàn bộ JAR”.

### 3.2. Thư mục số phiên bản không phải tùy ý

Cấu trúc versioned directory dùng các release numbers từ **9 trở lên**, ví dụ `9`, `11`, `17`. Không dùng tên như `java17`, `jdk-17`, `61` hoặc `8` làm directory version của MRJAR theo quy ước chuẩn.

Nếu bạn có nhu cầu hỗ trợ Java 8, bản Java 8 phải nằm **ở gốc JAR**, không trong `META-INF/versions/8`.

## 4. Manifest: điều kiện để kích hoạt chế độ multi-release

Một MRJAR cần khai báo trong **main section** của `META-INF/MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

Dòng trống cuối biểu thị kết thúc section theo cấu trúc manifest. Khi dùng công cụ build, các manifest entries có thể được tạo tự động.

Một JAR có thư mục `META-INF/versions/17` **nhưng thiếu thuộc tính `Multi-Release: true`** không được mặc định coi là MRJAR trong cơ chế load class thông thường. Một class loader Java có thể chỉ thấy class cơ sở; các entry dưới versioned directory vẫn là những file ZIP có tên vật lý của chúng.

### 4.1. Dùng đúng tên và giá trị

Tên attribute là `Multi-Release`, giá trị kích hoạt là `true`. Tốt nhất dùng công cụ `jar`, Maven JAR plugin hoặc Gradle `Jar.manifest` để tạo attribute, thay vì tự sửa file manifest sau khi archive đã đóng gói.

### 4.2. Manifest không thay thế nội dung lớp

Bật `Multi-Release: true` không tự tạo version-specific classes. Nếu chỉ có base entries, JAR vẫn chạy theo base. Cơ chế thực sự có tác dụng khi archive tồn tại các versioned entries hợp lệ.

### 4.3. Không nhầm với Automatic-Module-Name

`Automatic-Module-Name` là attribute phục vụ tên automatic module trong JPMS. Nó không bật MRJAR và không thay thế `Multi-Release: true`.

Một JAR có thể có cả hai:

~~~text
Manifest-Version: 1.0
Multi-Release: true
Automatic-Module-Name: com.example.codec

~~~

Hai thuộc tính xử lý hai vấn đề khác nhau: **lựa chọn implementation theo JDK** và **định danh module**.

## 5. Quy tắc lựa chọn lớp theo phiên bản runtime

Khi một class/resource được yêu cầu qua cơ chế MR-aware, runtime xét các versioned entries theo nguyên tắc:

1. Xác định Java runtime feature version, ví dụ 17.
2. Tìm phiên bản tương ứng với tên logical entry ở versioned directory có **N lớn nhất nhưng không vượt quá runtime version**.
3. Nếu không có override phù hợp, dùng base entry.
4. Nếu có nhiều override ở các N phù hợp, chọn **N lớn nhất**.
5. Entry của N cao hơn runtime không được sử dụng như implementation cho runtime thấp hơn.

Ví dụ có base, Java 11 và Java 17:

| Runtime | Class được chọn |
|---|---|
| Java 8 | `com/example/codec/HexCodec.class` (base) |
| Java 9 | Base (không có override 9) |
| Java 10 | Base |
| Java 11 | `META-INF/versions/11/.../HexCodec.class` |
| Java 16 | Bản ở `versions/11` |
| Java 17 | Bản ở `versions/17` |
| Java 21 | Bản ở `versions/17` nếu không có bản 18–21 phù hợp |

**Không có phép nội suy hoặc compile lại bytecode.** Java 16 chỉ chọn class đã được đóng gói ở phiên bản 11; Java 21 có thể chọn bản 17 mà không tự nâng nó thành code Java 21.

### 5.1. Pseudocode lựa chọn

~~~text
function resolve(logicalName, runtimeVersion):
    for version from runtimeVersion down to 9:
        candidate = "META-INF/versions/" + version + "/" + logicalName
        if candidate exists and versioned entry is applicable:
            return candidate

    return logicalName at JAR root
~~~

Pseudocode giải thích nguyên lý, không đại diện chính xác toàn bộ cache, module/classloader, resource behavior, security checks và implementation details trong JVM.

### 5.2. Không có lớp thay thế thì dùng base

Nếu `Order.class` chỉ nằm ở gốc, runtime Java 21 vẫn nạp base. Một MRJAR có thể tối ưu chỉ một vài class thay vì nhân bản toàn bộ thư viện.

### 5.3. Runtime không dùng bản cao hơn khả năng của nó

Java 11 không lấy `versions/17/...` chỉ vì đó là phiên bản mới hơn trong archive. Cơ chế MRJAR cố ý tránh việc runtime thấp đọc class được viết cho release cao hơn.

## 6. Lựa chọn class khác với lựa chọn phiên bản artifact

MRJAR không phải Maven/Gradle dependency resolution.

~~~text
Maven/Gradle chọn:
  org.example:hexcodec:1.2.0
                   |
                   v
             Một JAR artifact
                   |
             Class loader / JVM
                   |
                   v
     Chọn base / versions/11 / versions/17
~~~

Build tool chọn **một phiên bản artifact** như `1.2.0`. Bên trong artifact đó, JVM có thể chọn implementation phù hợp với runtime. Thay `hexcodec:1.2.0` bằng `hexcodec:1.3.0` là thay dependency version; nạp `versions/17` thay base là hành vi **bên trong cùng artifact**.

Điều này quan trọng khi debug: hai môi trường dùng **cùng checksum JAR** vẫn có thể chạy **class bytecode khác nhau** nếu JDK runtime khác.

## 7. Ví dụ chạy thực tế: API giữ nguyên, implementation khác nhau

Ta xây một thư viện `HexCodec` có cùng API:

~~~java
public static String encode(byte[] input)
public static String implementation()
~~~

Bản base biên dịch cho Java 8, bản Java 17 dùng `java.util.HexFormat`.

### 7.1. Cấu trúc source dự kiến

~~~text
hexcodec-example/
├── manifest.mf
├── src/
│   ├── base/
│   │   └── com/example/codec/HexCodec.java
│   ├── java17/
│   │   └── com/example/codec/HexCodec.java
│   └── app/
│       └── com/example/app/Main.java
└── build/
    ├── classes-base/
    ├── classes-17/
    ├── app/
    └── hexcodec-mr.jar
~~~

**Lưu ý:** Hai file Java có cùng package/class name, nhưng **không được compile chung như hai source files trong cùng một javac invocation**. Chúng thuộc hai source trees/compilation tasks riêng.

### 7.2. Implementation base cho Java 8

File `src/base/com/example/codec/HexCodec.java`:

~~~java
package com.example.codec;

public final class HexCodec {

    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexCodec() {
    }

    public static String encode(byte[] input) {
        StringBuilder result = new StringBuilder(input.length * 2);

        for (byte b : input) {
            int value = b & 0xff;
            result.append(HEX[value >>> 4]);
            result.append(HEX[value & 0x0f]);
        }

        return result.toString();
    }

    public static String implementation() {
        return "base-java8";
    }
}
~~~

Code này chỉ dùng Java SE APIs và cú pháp phù hợp Java 8.

### 7.3. Implementation thay thế cho Java 17

File `src/java17/com/example/codec/HexCodec.java`:

~~~java
package com.example.codec;

import java.util.HexFormat;

public final class HexCodec {

    private HexCodec() {
    }

    public static String encode(byte[] input) {
        return HexFormat.of().formatHex(input);
    }

    public static String implementation() {
        return "java17-hexformat";
    }
}
~~~

Hai bản có **cùng public class**, cùng tên package và cùng public static method signatures. Phần cài đặt thay đổi nhưng người sử dụng không phải import package khác.

### 7.4. Chương trình tiêu thụ API

File `src/app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.codec.HexCodec;

public final class Main {

    public static void main(String[] args) {
        byte[] input = new byte[] { 0, 15, -1 };

        System.out.println(HexCodec.encode(input));
        System.out.println(HexCodec.implementation());
    }
}
~~~

Kết quả `encode` ở cả hai version phải là:

~~~text
000fff
~~~

Dòng `implementation` chỉ nhằm minh họa class nào được runtime chọn; một thư viện production thường không cần công khai method như vậy.

## 8. Biên dịch hai source trees bằng javac

Ví dụ lệnh kiểu Unix/Linux/macOS hoặc shell có công cụ tương đương. Thư mục nguồn phải được tạo theo cấu trúc ở trên.

### 8.1. Biên dịch bản base theo Java 8

Dùng JDK đủ mới có hỗ trợ `--release 8`:

~~~bash
mkdir -p build/classes-base build/classes-17 build/app

javac --release 8 \
  -d build/classes-base \
  src/base/com/example/codec/HexCodec.java
~~~

`--release 8` giúp compiler hạn chế **cú pháp, class-file target và Java SE API** theo Java 8, thay vì chỉ đặt `-target 8` nhưng vô tình tham chiếu Java API mới.

Nếu project đang dùng toolchain rất mới, luôn xác minh javac release list còn hỗ trợ target cũ mà tổ chức yêu cầu.

### 8.2. Biên dịch bản Java 17

~~~bash
javac --release 17 \
  -d build/classes-17 \
  src/java17/com/example/codec/HexCodec.java
~~~

Bản này được phép dùng `HexFormat` vì API đã có từ Java 17. Không được để base class tham chiếu `HexFormat` hoặc class phiên bản 17 trong static initializer/constant pool của đường code bắt buộc trên Java 8.

### 8.3. Kiểm tra class-file major

~~~bash
javap -verbose \
  -classpath build/classes-base \
  com.example.codec.HexCodec
~~~

Expected base:

~~~text
major version: 52
~~~

Tương tự:

~~~bash
javap -verbose \
  -classpath build/classes-17 \
  com.example.codec.HexCodec
~~~

Expected Java 17:

~~~text
major version: 61
~~~

Major 52 tương ứng Java 8; major 61 tương ứng Java 17. Class-file major và số version directory không phải cùng một giá trị.

## 9. Đóng gói bằng jar tool và manifest

Tạo `manifest.mf`:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

Sau khi compile cả hai source trees, có thể dùng công cụ `jar` của JDK hỗ trợ multi-release option:

~~~bash
jar --create \
    --file build/hexcodec-mr.jar \
    --manifest manifest.mf \
    -C build/classes-base . \
    --release 17 \
    -C build/classes-17 .
~~~

Ý nghĩa:

- `--create` tạo archive mới.
- `--file` chỉ định artifact.
- `--manifest` cung cấp manifest có `Multi-Release: true`.
- `-C build/classes-base .` đưa base classes vào JAR root.
- `--release 17` chuyển vùng đóng gói tiếp theo vào `META-INF/versions/17/`.
- `-C build/classes-17 .` thêm class Java 17 vào vùng versioned.

Cú pháp này minh họa khả năng `jar --release` của các JDK hiện đại. Với các bản JDK/tool khác nhau, cần kiểm tra `jar --help`, output manifest và nội dung archive thực tế.

### 9.1. Xem archive contents

~~~bash
jar --list --file build/hexcodec-mr.jar
~~~

Những entry liên quan nên có:

~~~text
META-INF/MANIFEST.MF
com/example/codec/HexCodec.class
META-INF/versions/17/com/example/codec/HexCodec.class
~~~

Nếu thiếu `META-INF/versions/17`, bản Java 17 chưa được đưa vào archive hoặc task đóng gói chạy sai.

### 9.2. Validate multi-release JAR

JDK `jar` tool có chức năng kiểm tra multi-release JAR:

~~~bash
jar --validate --file build/hexcodec-mr.jar
~~~

Chức năng validation có thể phát hiện một số vi phạm về cấu trúc/API consistency. Nó **không thay thế** contract tests, kiểm tra behavior hoặc chạy thực tế trên nhiều JDK.

### 9.3. Manifest phải có dấu hiệu kích hoạt

Ngay cả khi file versioned đã có, phải xác minh manifest được build đưa vào archive với attribute `Multi-Release: true`.

Một số build plugins có thể tự tạo hoặc hợp nhất manifest, nên không nên chỉ xem `manifest.mf` trong source tree và giả định archive đã giữ nguyên.

## 10. Biên dịch ứng dụng tiêu thụ và thử chạy

Biên dịch `Main` với API Java 8 của MRJAR:

~~~bash
javac --release 8 \
  -classpath build/hexcodec-mr.jar \
  -d build/app \
  src/app/com/example/app/Main.java
~~~

Với hệ Unix dùng dấu `:` để ngăn cách classpath:

~~~bash
java \
  -classpath "build/app:build/hexcodec-mr.jar" \
  com.example.app.Main
~~~

Trên Windows, classpath separator thường là dấu `;`:

~~~powershell
java -classpath "build/app;build/hexcodec-mr.jar" com.example.app.Main
~~~

### 10.1. Kết quả minh họa khi chạy bằng Java 8

~~~text
000fff
base-java8
~~~

Java 8 chưa có MRJAR-aware loading nên dùng base entry như JAR thông thường.

### 10.2. Kết quả minh họa khi chạy bằng Java 17

~~~text
000fff
java17-hexformat
~~~

Khi JDK 17 hỗ trợ MRJAR và đọc attribute/entry hợp lệ, `HexCodec` được nạp từ `META-INF/versions/17`.

### 10.3. Khi chạy trên Java 21

Nếu archive không có `versions/18`, `versions/19`, `versions/20` hoặc `versions/21` phù hợp, Java 21 có thể tiếp tục dùng bản `versions/17`.

### 10.4. Kết quả cần được kiểm chứng trên runtime thật

Các output trên là **kỳ vọng của ví dụ**, không phải kết quả đã chạy trên máy người học. Phải thực hiện test bằng JDK 8/17/21 thật trong môi trường hỗ trợ tương ứng, không chỉ đổi biến `JAVA_HOME` trên shell không liên quan tới process.

## 11. Thứ tự ưu tiên khi có nhiều bản override

Giả sử một thư viện có:

~~~text
com/example/Feature.class

META-INF/versions/9/com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

Dưới cơ chế MR-aware:

| Java runtime | Class được chọn |
|---|---|
| Java 8 | Base |
| Java 9 | Version 9 |
| Java 10 | Version 9 |
| Java 11 | Version 11 |
| Java 16 | Version 11 |
| Java 17 | Version 17 |
| Java 20 | Version 17 |
| Java 21 | Version 21 |
| Java 25 | Version 21, nếu không có bản cao hơn phù hợp |

**Runtime chọn bản N lớn nhất không vượt quá feature version của chính nó**. Không phải luôn chọn Java release gần nhất theo tên file, và cũng không phải chọn entry có class-file major “cao nhất mà classloader cố đọc”.

### 11.1. Vì sao Java 16 chọn version 11 thay vì base?

Vì `11 ≤ 16` và không có override version 12–16. Tính năng Java mới có thể kế thừa implementation đã được chuyên biệt cho một release cũ hơn mà vẫn phù hợp.

### 11.2. Có thể bỏ qua các mốc trung gian

Một JAR chỉ có `versions/17` vẫn hợp lệ khi base cung cấp API cho những runtime dưới 17. Không phải tạo thư mục 9, 10, 11, ..., 16 chỉ để “đủ số”.

## 12. Class-file version và yêu cầu biên dịch

Các con số cần phân biệt:

| Java release | MRJAR directory | Class-file major |
|---|---|---:|
| Java 8 | Base JAR root | 52 |
| Java 9 | `META-INF/versions/9` | 53 |
| Java 11 | `META-INF/versions/11` | 55 |
| Java 17 | `META-INF/versions/17` | 61 |
| Java 21 | `META-INF/versions/21` | 65 |
| Java 25 | `META-INF/versions/25` | 69 |

Version-specific class phải được biên dịch cho release mà thư mục đại diện hoặc release thấp hơn tương thích theo quy tắc MRJAR/packaging; trong thực hành nên đặt **`--release N` cho source tree version N** để tránh vô tình dùng Java APIs mới hơn.

Ví dụ sai:

~~~text
META-INF/versions/11/com/example/Feature.class
    nhưng class file được biên dịch cho Java 17 (major 61)
~~~

Một Java 11 runtime có thể chọn entry version 11 rồi không nạp được class vì bytecode quá mới. Đây là lỗi đóng gói nghiêm trọng, không được chữa bằng cách “mở module” hoặc đổi manifest.

### 12.1. Dùng --release thay vì chỉ -source/-target

`-source` điều khiển cú pháp; `-target` điều khiển bytecode target. Một số cấu hình cũ dùng compiler JDK mới với `-source 8 -target 8` nhưng vẫn cho phép tham chiếu Java SE APIs mới, làm runtime Java 8 lỗi.

`--release 8` giúp kiểm soát cả API baseline của nền tảng, tránh nhiều lỗi loại này.

### 12.2. Annotation processor và generated code

Nếu version-specific source sử dụng annotation processors, cần tách output của từng compilation và bảo đảm generated classes nằm đúng base/versioned directories. Không để file generated cho Java 17 lọt vào base tree.

## 13. Giữ hợp đồng API nhất quán giữa các versions

Mục tiêu phổ biến của MRJAR là **thay implementation nhưng giữ public/protected API tương đương** giữa base và versioned classes.

Ví dụ API base:

~~~java
public final class HexCodec {
    public static String encode(byte[] input) { /* ... */ }
}
~~~

Nếu bản Java 17 đổi thành:

~~~java
public final class HexCodec {
    public static byte[] encode(byte[] input) { /* ... */ }
}
~~~

thì **return type đã đổi**, source/binary clients có thể bị ảnh hưởng. Điều này không phù hợp cách dùng MRJAR để duy trì một thư viện API ổn định.

Về thiết kế, nên giữ:

- Fully qualified class names được công khai.
- Public/protected constructors và methods tương thích.
- Field contracts và inheritance/interfaces đã cam kết.
- Exception semantics theo API contract.
- Serialization/protocol/data format.
- Behavior quan trọng mà consumers dựa vào.

### 13.1. Public API giống không bảo đảm behavior giống

Hai implementation của `HexCodec.encode` có thể cùng signature nhưng khác cách xử lý null, UTF-8, casing hoặc error behavior. `jar --validate` không chứng minh các output tương đương.

Do đó, cần chạy **cùng contract test suite** trên runtime lựa chọn base và runtime lựa chọn override.

### 13.2. Internal helpers có thể chuyên biệt

Một implementation versioned có thể có private/package-private helpers riêng để tận dụng JDK mới, miễn phù hợp các quy tắc đóng gói và không làm hỏng public API. Chúng cần được đóng gói đúng versioned tree và không được base implementation vô tình tham chiếu.

### 13.3. Giữ tương thích nhị phân

Trong thực tế, consumers có thể được biên dịch trên Java 8 nhưng chạy trên Java 17. Nếu versioned class xóa một method public mà bytecode của consumer cần, có thể xảy ra `NoSuchMethodError` lúc runtime.

Đừng đánh giá tương thích chỉ bằng cách compile lại mọi consumer trên JDK mới; cần test cả **older-compiled clients** nếu đó là yêu cầu của thư viện.

## 14. Multi-release JAR không phải thư viện có nhiều public APIs theo JDK

Một cám dỗ là thêm public API `newFeatureOnlyOnJava17()` vào `versions/17` và để nó vắng mặt ở base. Cách này gây vấn đề:

- Client Java 8 không thể nhìn thấy API.
- Compiler có thể tạo code tham chiếu API không tồn tại khi chạy ở JDK thấp hơn.
- `jar --validate` hoặc công cụ kiểm tra API consistency có thể cảnh báo/từ chối sự khác biệt.
- Tài liệu thư viện trở nên phụ thuộc runtime.
- Framework reflection hoặc tooling có thể thấy các API khác nhau theo môi trường.

Tốt hơn là giữ **một public facade ổn định**, điều khiển implementation bằng MRJAR. Nếu thực sự cần những API khác nhau theo JDK, cân nhắc phát hành modules/artifacts riêng hoặc định nghĩa một contract rõ về phiên bản hỗ trợ.

## 15. Versioned resources: không chỉ có .class

MRJAR cho phép có version-specific resources trong cấu trúc phù hợp khi runtime sử dụng cơ chế resource lookup có nhận biết MRJAR.

Ví dụ:

~~~text
com/example/codec/defaults.properties
META-INF/versions/17/com/example/codec/defaults.properties
~~~

Trong một số đường truy cập MR-aware, lookup logical name `com/example/codec/defaults.properties` có thể chọn resource phiên bản 17 trên Java 17.

Tuy nhiên, cần phân biệt:

- Resource lookup qua class loader/JAR APIs có hỗ trợ MRJAR.
- Mở file vật lý bằng `ZipFile` hoặc công cụ unzip thông thường.
- Duyệt ZIP entries bằng scanner bên ngoài.
- Một framework tự implement resource loader, không áp quy tắc MRJAR.

**Không giả định mọi thư viện đọc ZIP hoặc mọi resource framework đều thực hiện lựa chọn phiên bản giống JVM class loader**. Hãy kiểm tra đúng API tiêu thụ resource.

### 15.1. Cấu hình và tài nguyên nhạy cảm

Không dùng versioned resources để lén thay đổi secrets, connection endpoints hoặc security policy theo JDK mà không có ownership rõ. Một JAR có thể dùng cùng checksum nhưng đọc cấu hình khác trên runtime khác; đây là nguồn lỗi khó quan sát.

### 15.2. META-INF có các quy tắc đặc biệt

Nhiều metadata trong `META-INF` như manifest, signatures và service provider configuration có quy tắc riêng; **không coi mọi entry trong META-INF đều có thể version bằng cách chép vào versions/N/META-INF/**.

Ví dụ thông thường, `META-INF/services/...` là metadata service configuration ở JAR root, không nên tự giả định đặt nó trong versioned tree sẽ được `ServiceLoader` xử lý như các class files. Nếu cần provider theo JDK, hãy thiết kế provider classes và service registration theo đặc tả/tooling phù hợp, rồi test thực tế.

## 16. Class loader và API truy cập archive

Quy tắc lựa chọn MRJAR được hiện thực trong các cơ chế Java hỗ trợ. Nhưng không phải mọi cách truy cập ZIP đều giống nhau.

| Cách truy cập | Điều cần lưu ý |
|---|---|
| Standard Java application class loading trên JDK hỗ trợ MRJAR | Có thể chọn versioned class phù hợp |
| `java.util.jar.JarFile` với runtime-version-aware constructor | Có khả năng tra logical entries theo version chọn |
| Plain `ZipFile`/ZIP enumeration | Nhìn các physical ZIP entries, không tự có cùng semantics class resolution |
| `jar --list` | Liệt kê entries vật lý, không có nghĩa chọn một override để chạy |
| Custom class loader | Phải kiểm tra implementation có MR-aware không |
| Nested JAR loader trong executable framework | Cần kiểm tra loader/version framework hỗ trợ MRJAR |
| Bytecode scanning/annotation scanning | Có thể đọc base, tất cả versions hoặc variant tùy tool |
| Native-image/AOT build pipeline | Lựa chọn class ở build-time và runtime cần được xác minh riêng |

Một số trường hợp custom class loader tự đọc bytes từ `ZipFile` rồi gọi `defineClass`. Nếu code chỉ tìm `com/example/Feature.class` ở JAR root, nó có thể bỏ qua override dù manifest đúng.

### 16.1. JarFile có lựa chọn phiên bản khi mở

Java có API `JarFile` để làm việc với multi-release archives. Ví dụ code minh họa trên JDK hiện đại:

~~~java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;

public final class InspectMrJar {

    public static void main(String[] args) throws Exception {
        File archive = new File("build/hexcodec-mr.jar");

        try (JarFile jar = new JarFile(
                archive,
                true,
                ZipFile.OPEN_READ,
                Runtime.version())) {

            System.out.println("MRJAR = " + jar.isMultiRelease());

            JarEntry entry =
                    jar.getJarEntry("com/example/codec/HexCodec.class");

            System.out.println(entry == null
                    ? "not found"
                    : entry.getName());
        }
    }
}
~~~

Constructor có tham số `Runtime.Version` minh họa việc **chọn version context rõ ràng** khi làm việc với MRJAR. Cần hiểu behavior theo JDK/version/API đang dùng, nhất là khi tools tự mở archive bằng constructor/ZIP API khác.

### 16.2. Tại sao jar tf luôn liệt kê cả base và versions?

`jar tf` cho thấy nội dung archive; nó không phải một JVM đang chạy business code. Việc nhìn thấy cả `com/example/Feature.class` và `META-INF/versions/17/com/example/Feature.class` trong listing là bình thường.

## 17. Quan sát lớp được chọn khi chạy

Khi cần biết implementation nào được nạp trên runtime thật, có thể:

- Gắn method diagnostic chỉ dùng cho test như `implementation()` của ví dụ.
- Dùng class loading logs của JVM.
- Ghi JDK vendor/version và checksum JAR.
- Dùng `javap` hoặc công cụ đọc bytecode với từng physical entry.
- Kiểm tra class loader và location của code source.
- Chạy behavioral contract tests trên các JDK cụ thể.

Ví dụ bật log nạp lớp với Java hiện đại:

~~~bash
java -Xlog:class+load=info \
  -classpath "build/app:build/hexcodec-mr.jar" \
  com.example.app.Main
~~~

`-Xlog` là cơ chế logging của JVM hiện đại, không phải cú pháp tương thích Java 8. Với Java 8 cần dùng flags logging khác nếu cần. Đừng bật log quá rộng trên production trong thời gian dài vì có thể tạo nhiều dữ liệu.

### 17.1. CodeSource location không luôn chỉ đúng physical versioned entry

Một class có thể được báo là nạp từ JAR path, nhưng log hoặc `ProtectionDomain.getCodeSource()` không nhất thiết hiển thị `META-INF/versions/17` như một physical path. Tùy class loader/JAR URL semantics, location có thể là archive chung.

Vì vậy, nếu cần chứng minh override đã được chọn, dùng test behavior hoặc công cụ kiểm tra đúng entry bytes, thay vì chỉ nhìn một URL code source.

## 18. MRJAR và JPMS (Java Platform Module System)

Java 9 giới thiệu **JPMS** cùng thời điểm MRJAR. Hai tính năng bổ sung cho nhau nhưng không giống nhau.

Một thư viện có thể:

1. Là MRJAR trên classpath, không có `module-info.class`.
2. Là MRJAR được đặt trên module path như một automatic module nếu không có explicit descriptor.
3. Có `module-info.class` phù hợp để trở thành explicit module trên Java 9+.
4. Có module descriptor trong versioned tree trong một số cấu trúc MRJAR phục vụ tương thích Java 8 và Java 9+.

### 18.1. Vì sao đặt module-info.class ở phiên bản 9?

Java 8 không hiểu JPMS. Một thư viện muốn giữ base classes Java 8 nhưng đưa module descriptor cho Java 9+ có thể tổ chức:

~~~text
com/example/codec/HexCodec.class
META-INF/versions/9/module-info.class
META-INF/MANIFEST.MF
~~~

Khi dùng một cấu trúc MRJAR phù hợp, Java 9+ trên module path có thể nhận module descriptor theo cơ chế mà module system hỗ trợ, trong khi Java 8 classpath chỉ xử lý base classes.

Điều này đòi hỏi packaging/toolchain đúng và compatibility constraints. Không tự đặt một `module-info.class` vào bất kỳ vị trí nào rồi suy rằng module system sẽ hiểu.

### 18.2. module-info.class không phải replacement của business class

Module descriptor mô tả module name, `requires`, `exports`, `opens` và các chỉ báo khác. Đây là metadata module, không phải một implementation thay thế cho `HexCodec`.

### 18.3. Classpath và module path khác nhau

Classpath thường đặt classes vào unnamed module, trong khi module path có module resolution và access rules. Một MRJAR có thể chạy ổn trên classpath nhưng gặp vấn đề `requires`/`exports`/`opens` trên module path.

Trong migration Java 8 → Java 17, cần test cả deployment mode nếu sản phẩm hỗ trợ cả hai. Không dùng MRJAR để lách mạnh các quy tắc module encapsulation.

## 19. Hợp đồng API và module descriptor

Một bản Java 17 của library có thể dùng private implementation chuyên biệt, nhưng module exports và services phải nhất quán với API hứa hẹn cho consumers.

Khi có JPMS:

- Các packages công khai thường phải được `exports` đúng.
- Reflection framework có thể cần `opens` phù hợp.
- Các thư viện versioned có dependency mới phải xem `requires` và module resolution.
- Split packages giữa modules vẫn có thể là blocker.
- Service binding có thể dùng `uses`/`provides` trong descriptor.

Nếu bản versioned sử dụng một thư viện không có trong module graph hoặc không được khai báo đúng, class có thể load thất bại dù archive có đúng entry.

**MRJAR giải quyết lựa chọn entry, không tự giải quyết tính hợp lệ của module graph.**

## 20. Dùng MRJAR để hỗ trợ thư viện trên JDK mới

Một trường hợp thực tế trong Java Compatibility Migration là code cũ từng dựa vào implementation riêng:

~~~text
Base: logic hoạt động trên Java 8
Java 11: dùng API mới để tránh legacy workaround
Java 17: dùng public API mới thay thao tác reflection cũ
~~~

Một hướng thiết kế:

~~~text
PublicFacade (hợp đồng chung)
       |
       +-- Base implementation: Java 8 compatible
       |
       +-- META-INF/versions/11: implementation cho Java 11+
       |
       +-- META-INF/versions/17: implementation cho Java 17+
~~~

Không nhất thiết phải thêm bản overlay ở mỗi release. Chỉ tạo nơi thật sự có khác biệt cần thiết.

### 20.1. Khi không nên dùng MRJAR để “cứu” thư viện cũ

MRJAR không sửa được:

- Một dependency khác bị bỏ duy trì và không tương thích runtime.
- Public API của thư viện thay đổi không thể giữ nhất quán.
- Runtime thiếu module/dependency mà versioned implementation cần.
- Thay đổi giao thức/serialization khác semantics.
- Vấn đề bảo mật do API/cipher yếu nếu bản cũ vẫn được phân phối và được dùng.
- Một class loader tùy biến không hỗ trợ MRJAR.
- Framework không hỗ trợ format archive hoặc shading làm hỏng cấu trúc.

Nếu chỉ hỗ trợ Java 17 trở lên, đôi khi đơn giản hơn là **nâng baseline toàn bộ thư viện** thay vì giữ base Java 8 và multiple variants.

## 21. Build bằng Gradle: tổ chức source set và task

Gradle không tự hiểu `src/java17` là một source tree phải đưa vào `META-INF/versions/17` chỉ vì project dùng Java toolchain. Cần cấu hình compilation và packaging riêng hoặc dùng plugin đáng tin cậy.

Một ví dụ Groovy DSL thể hiện phương pháp:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// Code ở src/main/java là base, tương thích Java 8.
tasks.named('compileJava', JavaCompile) {
    options.release = 8
}

def compileJava17 = tasks.register('compileJava17', JavaCompile) {
    dependsOn(tasks.named('compileJava'))

    source = fileTree('src/java17/java') {
        include '**/*.java'
    }

    classpath = files(sourceSets.main.output)
    destinationDirectory = layout.buildDirectory.dir('classes/java17')

    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }

    options.release = 17
}

tasks.named('jar', Jar) {
    dependsOn(compileJava17)

    manifest.attributes('Multi-Release': 'true')

    into('META-INF/versions/17') {
        from(compileJava17.flatMap { it.destinationDirectory })
    }
}
~~~

Ví dụ giả định Gradle version có các APIs `toolchain`, `destinationDirectory`, `tasks.named` và provider mapping tương ứng. Tùy Gradle wrapper, cách khai báo task và configuration có thể cần điều chỉnh.

### 21.1. Vì sao cần tách compilation?

Nếu Java 17 source được đưa vào `sourceSets.main.java`, compiler có thể thấy **hai classes cùng fully qualified name** (`HexCodec` base và Java17), gây duplicate class error.

Vì vậy:

- Base tree vào `src/main/java`.
- Java 17 tree vào `src/java17/java`.
- Hai compilations có destination directories khác nhau.
- `jar` task đưa classes Java 17 vào path versioned.
- Manifest đánh dấu MRJAR.

### 21.2. Tránh compiler classpath “nhìn nhầm” implementation

Khi compile versioned implementation, có thể cần base output trên classpath để kế thừa utility/public contracts, nhưng không được để overlay output bị build tooling tái sử dụng làm base source. Luồng phụ thuộc phải rõ, tránh cycle hoặc vô tình compile chung.

### 21.3. Gradle tests cần chạy JAR thật

Gradle `test` mặc định có thể dùng compiled class directories của source set thay vì JAR package cuối. Nếu mục tiêu là xác minh MRJAR **runtime selection**, cần integration test riêng với **đã đóng gói JAR** trên JDK 8/11/17/21 tương ứng.

Nếu test chỉ dùng `build/classes/java/main`, nó có thể luôn chạy base implementation dù Java 17 runtime, cho kết quả sai về MRJAR.

## 22. Maven: manifest và biên dịch versioned sources

Trong Maven, thường cần cấu hình nhiều bước:

1. Biên dịch base source bằng `--release 8`.
2. Biên dịch Java 17 overlay source bằng `--release 17` vào output riêng hoặc layout versioned phù hợp.
3. Đưa overlay files vào `META-INF/versions/17` trong JAR.
4. Ghi `Multi-Release: true` vào manifest.
5. Validate archive và chạy integration tests trên nhiều JDK.

Ví dụ Maven JAR Plugin để đặt manifest attribute:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifestEntries>
                <Multi-Release>true</Multi-Release>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
~~~

**Fragment này chỉ cấu hình manifest; nó chưa tự compile Java 17 source tree hoặc di chuyển files vào versioned directory.**

Tùy Maven Compiler Plugin version, có thể sử dụng các chức năng multi-release output hoặc cấu hình compilation executions riêng, kết hợp resources/assembly steps. Cần xem documentation của phiên bản plugin được dùng, đặc biệt với multi-module builds và generated sources.

### 22.1. Đừng compile cả source trees vào target/classes root

Nếu hai bản `com.example.codec.HexCodec` cùng được compile vào `target/classes/com/example/codec`, bản sau có thể ghi đè bản trước. Artifact mất base entry hợp lệ cho Java 8 hoặc không có override.

Mỗi JDK variant cần output path riêng trước packaging.

### 22.2. Maven test classpath không phải JAR runtime

Tương tự Gradle, Maven unit tests có thể dùng `target/classes` trực tiếp. Muốn test overlay selection cần chạy integration tests hoặc Java process dùng **artifact JAR đã được đóng gói**, dưới từng JDK runtime cần hỗ trợ.

## 23. Khi chỉ cần Gradle/Maven artifact thông thường

Không phải mọi thư viện multi-JDK đều cần MRJAR. Các lựa chọn có thể gồm:

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| Một JAR biên dịch cho Java thấp nhất | Đơn giản, ít tests variants | Không dùng trực tiếp APIs mới ở implementation |
| MRJAR | Một artifact, implementation theo JDK | Build/test/tooling phức tạp hơn |
| Artifacts riêng theo classifier | Version selection do build/dependency management | Consumer phải chọn đúng variant |
| Nâng Java baseline | Giảm đường code, tận dụng JDK mới | Loại bỏ consumers dùng JDK cũ |
| Reflection/feature detection | Có thể giữ một class file base | Khó đọc/debug, runtime checks và access issues |
| Service-based abstraction | Tách implementations qua SPI | Thêm wiring và dependency management |

Chọn MRJAR khi có lý do rõ để giữ **một tọa độ artifact** mà vẫn hỗ trợ các JDK versions khác nhau với APIs/logic đặc thù.

## 24. MRJAR trong fat JAR, shaded JAR và executable JAR

Một điểm dễ gây lỗi là **đóng gói lại** MRJAR vào một artifact khác.

Ví dụ:

~~~text
dependency-hexcodec.jar    (MRJAR đúng)
            |
            v
Maven Shade / Gradle Shadow / Spring Boot packaging
            |
            v
application.jar            (layout/class loader khác)
~~~

Các vấn đề:

- Plugin shade/merge có thể bỏ manifest `Multi-Release: true`.
- Các entries dưới `META-INF/versions` bị loại hoặc làm phẳng.
- Versioned classes bị relocate tên package không đồng bộ với base.
- Duplicate handling chọn sai một class.
- Signatures hoặc checksums của JAR gốc không còn hợp lệ sau biến đổi.
- Nested JAR loader của framework phải hỗ trợ lựa chọn đúng versioned entry.
- Analyzer/quét license/CVE có thể đọc cả các physical classes.

### 24.1. Nested JAR không đồng nghĩa đã mất MRJAR

Một số executable frameworks có class loaders hỗ trợ các nested libraries với MRJAR semantics. Nhưng không thể suy từ việc archive có file `META-INF/versions` rằng mọi launcher custom đều chọn đúng lớp.

Cần kiểm tra **đúng launcher và framework version** bằng test runtime; không chỉ chạy `java -cp dependency.jar` rồi kết luận executable package cuối hoạt động tương đương.

### 24.2. Sau shading phải kiểm tra artifact cuối

Các bước:

1. Build dependency MRJAR đúng.
2. Build shaded/fat JAR.
3. Inspect physical entries và manifest của artifact cuối.
4. Chạy logic khác nhau theo runtime để xác minh class selection.
5. Chạy contract tests trên JDK thấp/cao.
6. Quét signatures, duplicate classes và dependencies nếu pipeline yêu cầu.

Nếu shading làm mất semantics MRJAR, có thể chọn giữ nested dependency JAR nguyên vẹn thay vì gộp classes hoặc điều chỉnh plugin config theo documentation.

## 25. MRJAR và custom class loaders

Ứng dụng web, OSGi, plugin engines, application servers hoặc tự viết class loader có thể nạp JAR theo cách riêng.

Các câu hỏi:

- Loader có dùng MR-aware `JarFile`/lookup không?
- Loader có đọc JAR như ZIP và bỏ qua manifest không?
- Loader có cache bytes từ một runtime rồi dùng lại trên runtime khác không?
- Child-first/parent-first delegation có khiến class cùng tên được nạp từ library khác không?
- Framework scanning có thấy cả base và override như nhiều classes khác nhau không?
- Container đang chạy JDK nào, và có nạp artifact trong quá trình hot deploy không?

Nếu loader không áp MRJAR semantics, Java 17 process vẫn có thể dùng base class. Tình huống này không nhất thiết gây exception; nó có thể khiến **tối ưu hóa hoặc fix dành cho Java 17 không được kích hoạt**, dẫn tới behavior khác kỳ vọng.

### 25.1. Xác định loader đã chọn gì

Dùng test diagnostic `HexCodec.implementation()` hoặc một tính năng hành vi có thể quan sát. Đừng dựa duy nhất vào `Class.getResource` hoặc JAR file listing khi kiểm tra selection vì URL/entry handling có thể khác.

## 26. Static analysis, code coverage và bytecode tools

MRJAR làm quá trình scan phức tạp hơn vì archive chứa **nhiều physical class files cho cùng logical class name**.

Ví dụ:

~~~text
com/example/codec/HexCodec.class                  (major 52)
META-INF/versions/17/com/example/codec/HexCodec.class (major 61)
~~~

Một analyzer có thể:

- Chỉ phân tích base classes.
- Phân tích tất cả physical entries.
- Chọn variant theo runtime.
- Không hiểu MRJAR và coi versioned classes như “duplicate”.
- Thất bại khi gặp class-file major mới dù analyzer đang chạy trên JDK cũ.
- Báo những findings khác nhau theo JDK target.

### 26.1. JaCoCo và instrumentation

Nếu tests chạy trên Java 17 và JVM nạp versioned implementation, JaCoCo cần hỗ trợ class-file major và bytecode constructs tương ứng. Nhưng khi report task chỉ lấy base classes, mapping coverage có thể sai hoặc thiếu dữ liệu.

Cần ghi rõ:

- JaCoCo agent/report versions.
- Test JVM version.
- Physical class variant đã nạp.
- Class files được đưa vào report.
- Source files đúng phiên bản.
- Exclusions và aggregate report behavior.

Một report "100%" ở base classes không chứng minh Java17-specific implementation đã được test.

### 26.2. SpotBugs/PMD/Checkstyle

- SpotBugs và bytecode analyzers có thể cần hiểu phiên bản class file cao nhất được quét.
- PMD/Checkstyle source scanners cần hiểu source syntax của các variant.
- Custom rules cần được kiểm tra với từng source tree/version nếu có API chuyên biệt.
- Code quality pipeline phải biết rõ scope, tránh bỏ quên version-specific code.

### 26.3. jdeps

`jdeps` hữu ích để xem dependencies và một số JDK internal API references, nhưng cần hiểu cách tool xử lý MRJAR:

~~~bash
jdeps --multi-release 17 \
  build/hexcodec-mr.jar
~~~

Tùy JDK/tool version và analysis mode, `--multi-release 17` hướng công cụ phân tích variant phù hợp Java 17. Với một JAR nhiều versions, nên khảo sát variant base và các target releases được hỗ trợ, không chỉ một lần quét trên JDK của CI.

`jdeps` không nhìn thấy đầy đủ reflection với tên class được xây dựng bằng chuỗi hoặc native code.

## 27. Kiểm tra bằng jar --validate và giới hạn

~~~bash
jar --validate --file build/hexcodec-mr.jar
~~~

Công cụ có thể kiểm tra cấu trúc MRJAR và tính nhất quán của public API theo những quy tắc nó hỗ trợ.

Tuy nhiên:

- Không kiểm tra logic implementation có đúng không.
- Không kiểm chứng binary/data format compatibility của mọi dependency.
- Không chứng minh module graph hợp lệ trong mọi configuration.
- Không chứng minh class loader custom xử lý MRJAR đúng.
- Không kiểm tra security vulnerabilities của thư viện.
- Không thay runtime tests trên Java 8/11/17/21.
- Không thay API/ABI compatibility regression tests khi thư viện phát hành version mới.

Nên xem `jar --validate` là **một lớp kiểm tra cấu trúc**, không phải dấu chứng nhận mọi runtime đều hoạt động.

## 28. MRJAR và tài nguyên META-INF/services

Java service provider mechanism thường dùng file:

~~~text
META-INF/services/com.example.spi.CodecProvider
~~~

Cùng provider class/interface tương ứng.

Không nên mặc định đặt:

~~~text
META-INF/versions/17/META-INF/services/com.example.spi.CodecProvider
~~~

sẽ khiến Java 17 `ServiceLoader` tự ưu tiên cấu hình service mới. Resource metadata trong `META-INF` có quy tắc riêng, và các entry versioned không thể được suy diễn là một hệ metadata đầy đủ thay thế.

Nếu cần service implementation khác nhau theo JDK:

1. Xác định SPI contract chung.
2. Kiểm tra service registration ở root.
3. Thiết kế provider class hoặc facade có implementation theo runtime.
4. Kiểm tra `ServiceLoader` trên các JDK mục tiêu.
5. Nếu dùng JPMS, cân nhắc `uses`/`provides` đúng với module descriptor.
6. Không tạo trùng providers hoặc lệch metadata khi shade/JAR merge.

Nhiều ứng dụng có thể giải quyết việc chọn provider bằng abstraction khác thay vì cố version trực tiếp file services.

## 29. Security và supply-chain khi dùng MRJAR

MRJAR có thể chứa nhiều implementation, nên các công cụ security scanning cần bao phủ cả base và overlays.

Rủi ro:

- JDK 8 path và JDK 17 path có vulnerabilities khác nhau.
- Security scanner chỉ đọc base và bỏ sót versioned implementation.
- License scanner bỏ qua package nằm trong versioned directory.
- Hash/signature verification bị thay khi shading.
- Legacy code có lỗ hổng vẫn được ship vì muốn hỗ trợ JDK cũ.
- Developer test Java17 nhưng production Java11 chọn implementation khác.
- Tooling bỏ qua class files version cao dẫn tới kết quả scan thiếu.

Một JAR không tự trở nên an toàn vì Java17-specific code đã sửa một vấn đề; users trên Java8 có thể vẫn chạy base path. Nếu bản base có rủi ro không chấp nhận được, cần cân nhắc **ngừng hỗ trợ Java8**, thay cấu trúc API hoặc phát hành bản khác có policy rõ ràng.

### 29.1. SBOM và inventory

SBOM thường liệt kê artifact coordinates, version và checksum. Với MRJAR, có thể bổ sung metadata:

- Minimum supported Java.
- Versioned directories có trong archive.
- Toolchain/compiler releases dùng cho từng tree.
- Security scan coverage đối với từng variant.
- Test matrix theo runtime.
- Maintainer/owner của từng implementation path.

Không phải SBOM format nào cũng có field riêng cho variants, nhưng tài liệu build/release có thể ghi thông tin bổ sung để hỗ trợ audit.

### 29.2. Ký JAR và sửa archive

Nếu một JAR đã được ký, thay đổi manifest hoặc class entries sau khi ký có thể làm signature verification thất bại. Nên tạo đầy đủ MRJAR, validate, test rồi thực hiện bước signing theo quy trình phát hành được tổ chức phê duyệt.

## 30. Reproducible builds và provenance

Một artifact dùng nhiều compilations dễ gặp các biến không nhất quán:

- Base build chạy một compiler JDK, overlay build chạy compiler khác.
- Source files được sao chép/ghi đè giữa tasks.
- ZIP entry order/timestamps khác qua mỗi build.
- Dynamic dependency versions khác giữa environments.
- Manifest attribute bị plugin tự thay.
- Tools build một phần overlay rồi dùng cache cũ.
- Code generation output chứa absolute path hoặc timestamp.
- Class file khác nhau do compiler settings.

Một quy trình build tốt cần ghi:

1. Source Git commit.
2. Build tool wrapper/version.
3. JDK compiler releases cho từng variant.
4. `--release` của mỗi compilation.
5. Dependencies và artifact checksums.
6. Packaging tool/plugin version.
7. Manifest và archive layout.
8. `jar --validate` result.
9. Test matrix results.
10. Artifact checksum và signing metadata.

Khi có report "Java 17 chọn sai class", những thông tin này giúp phân biệt runtime issue với artifact đã bị đóng gói sai.

## 31. Performance: MRJAR có tự nhanh hơn không?

Không. MRJAR chỉ chọn implementation; hiệu năng do implementation và runtime quyết định.

Một bản Java17-specific có thể dùng API tối ưu hơn hoặc giảm reflection overhead. Nhưng có thể cũng làm tăng allocations, thay behavior GC hoặc gây bug mới.

Cần đo trên cùng workload:

- Throughput.
- p50/p95/p99 latency.
- CPU utilization.
- Heap allocations và GC.
- Startup/class loading.
- I/O, compression hoặc cryptographic throughput nếu liên quan.
- Behavior dưới concurrency.
- Error/timeout rate.

**Không benchmark trên class directories rồi khẳng định đã đo versioned implementation.** Chạy packaged JAR trong runtime phù hợp và xác minh class selection trước.

### 31.1. JIT có thể làm base implementation đủ tốt

Một implementation base có thể được JIT của Java 17 tối ưu tốt dù nó không dùng API mới. MRJAR nên được quyết định dựa trên benchmark và tính tương thích, không dựa vào giả định “Java mới phải có code riêng”.

## 32. Giữ phiên bản tương thích khi publish thư viện

Khi phát hành MRJAR lên Maven repository, consumers có thể sử dụng cùng tọa độ:

~~~text
com.example:hexcodec:1.4.0
~~~

Tuy nhiên, tài liệu phải công bố rõ:

- Java minimum được hỗ trợ.
- Java releases có implementation riêng.
- Public API support và policy.
- Có sử dụng preview/incubator features hay không.
- Có phụ thuộc module/native libraries khác theo runtime không.
- Test matrix và giới hạn class loaders được hỗ trợ.
- Lịch ngừng hỗ trợ các runtime cũ.
- Security patch policy cho base và overlays.

Không nên kỳ vọng consumers tự đoán rằng Java21 đang dùng code path khác Java11 chỉ từ artifact version.

### 32.1. SemVer không thay runtime compatibility statement

Semantic versioning có thể mô tả API compatibility giữa các artifact releases, nhưng một MRJAR còn có **nhiều implementation paths bên trong một release**. Test/version release policy phải tính đến từng đường runtime.

## 33. Triển khai trên Spring Boot, Tomcat và application server

Trong Java web deployment, MRJAR có thể xuất hiện như dependency ở:

- Spring Boot executable JAR chứa nested libraries.
- WAR `WEB-INF/lib`.
- Tomcat/container shared library directory.
- Application server module path.
- Java agent hoặc instrumentation JAR.

Một thư viện MRJAR chạy được bằng `java -cp lib.jar` chưa chắc hoạt động tương tự khi được một custom launcher/webapp classloader nạp.

### 33.1. External WAR

Một WAR có thể được deploy vào Tomcat đang chạy JDK17, trong khi local tests dùng JDK21. Nếu dependency MRJAR có `versions/21`, local chọn bản21 nhưng production chọn bản17 (hoặc base). Điều này có thể thay behavior mà không đổi checksum WAR.

### 33.2. Container image và JDK drift

Khi nâng base image từ JDK17 lên JDK21, ứng dụng có thể tự chuyển sang một implementation khác ở `META-INF/versions/21` mà không thay dependency version. Vì vậy, đợt đổi image vẫn cần regression tests cho MRJAR dependencies.

### 33.3. JPMS và application servers

Nếu môi trường dùng module path/JPMS, kiểm tra module descriptor và module graph, không chỉ classpath selection. Application servers có classloading rules riêng có thể xử lý archive khác trực tiếp Java classpath.

## 34. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Ưu tiên kiểm tra |
|---|---|---|
| Java17 vẫn chạy base | Manifest thiếu `Multi-Release: true`, overlay sai path, custom loader | Manifest, JAR layout, loader, runtime version |
| Java11 chọn base dù có Java17 overlay | Hành vi đúng theo quy tắc N ≤ runtime | Có cần tạo `versions/11` không? |
| Java17 báo `NoSuchMethodError` | Public API của overlay khác base hoặc dependency mismatch | `jar --validate`, signatures, runtime graph |
| Java11 báo `UnsupportedClassVersionError` | Version 11 entry được compile bằng Java17 | `javap` major, `--release 11` |
| Base Java8 báo `ClassNotFoundException: java.util.HexFormat` | Base code vô tình tham chiếu Java17 API | Biên dịch `--release 8` và test Java8 |
| `jar --validate` báo API inconsistency | Versioned public/protected API khác base | API signatures và compilation |
| Tests pass nhưng Java17 override không chạy | Tests dùng output classes thay JAR | Integration tests dùng packaged JAR |
| JaCoCo coverage thiếu | Report đọc base nhưng JVM chạy overlay | Execution data, class files, source mapping |
| SpotBugs báo unsupported class major | Analyzer/ASM chưa hỗ trợ variant cao | Analyzer version, class-file major |
| ServiceLoader không tìm provider | Services metadata/loader/module config sai | Root META-INF/services, JPMS descriptors |
| Sau shading override biến mất | Manifest/versions entries bị bỏ hoặc relocate sai | Inspect final artifact |
| Chạy trên server khác nhau cho output khác | JDK, classloader hoặc image khác | Runtime logs, JAR checksum |
| Vẫn dùng code cũ sau rollout | Cache/exploded archive, launcher hoặc artifact cũ | Deployment/checksum/logging |
| Security scan không thấy bug trong overlay | Scanner không đọc versioned tree | Variant coverage và tooling |

Không vội kết luận một classloader “bị lỗi” nếu môi trường đang dùng Java thấp hơn version directory hoặc có chủ đích tắt MRJAR behavior trong một công cụ. Thu thập JDK, manifest, entries và loader context trước.

## 35. Ví dụ điều tra: Java17 không chọn implementation mới

Giả sử `HexCodec.implementation()` in ra `base-java8` dù application chạy Java17.

Bước kiểm tra:

1. Xác nhận JVM của process thực tế là Java17, không phải shell bên ngoài.
2. Xem manifest thật trong JAR, xác minh `Multi-Release: true`.
3. Dùng `jar --list` kiểm tra đường dẫn `META-INF/versions/17/com/example/codec/HexCodec.class`.
4. Dùng `javap` kiểm tra base/overlay class-files và public method signatures.
5. Chạy `jar --validate`.
6. Chạy thử trực tiếp `java -cp build/hexcodec-mr.jar...` theo ví dụ tối giản.
7. Nếu chạy trực tiếp được nhưng trong framework không được, điều tra custom/nested classloader.
8. Xác định có một class `com.example.codec.HexCodec` khác đang được ưu tiên nạp từ library khác không.
9. Kiểm tra fat JAR/shading/relocation và container libraries.
10. Test behavior lại trên artifact cuối sẽ deploy.

### 35.1. Sai manifest

Archive có:

~~~text
META-INF/versions/17/com/example/codec/HexCodec.class
~~~

nhưng manifest không có attribute `Multi-Release: true`. Công cụ đọc ZIP vẫn liệt kê entry đó, nhưng Java class lookup bình thường có thể nạp base. Cần sửa packaging, không sửa Java code.

### 35.2. Sai đường dẫn lớp

Archive có:

~~~text
META-INF/versions/17/HexCodec.class
~~~

trong khi logical class name là `com/example/codec/HexCodec.class`. Versioned entry phải giữ **đường dẫn package/class tương ứng** bên dưới version directory.

### 35.3. Lớp khác đã được nạp trước

Một ứng dụng có thể có nhiều JAR chứa cùng fully qualified class. Class loader có thể chọn class từ JAR khác trước khi xem MRJAR được mong đợi. Kiểm tra dependency graph và class loading logs, không mặc định tên logical class thuộc MRJAR đã khai báo.

## 36. Ví dụ điều tra: Java11 nạp class không được hỗ trợ

Triệu chứng:

~~~text
java.lang.UnsupportedClassVersionError:
com/example/Feature has been compiled by a more recent
version of the Java Runtime
~~~

JAR chứa:

~~~text
META-INF/versions/11/com/example/Feature.class
~~~

nhưng `Feature.class` thực tế có major **61**. Java11 chọn version directory 11 đúng quy tắc nhưng class file được compile cho Java17, nên runtime không nạp được.

Cách sửa:

- Biên dịch implementation trong `versions/11` bằng JDK thích hợp và `--release 11`.
- Đặt Java17 implementation ở `versions/17`.
- Biên dịch base với `--release 8` nếu cần hỗ trợ Java8.
- Chạy validation và runtime tests trên Java11/17.
- Không dùng `--add-opens` hoặc đổi manifest để che lỗi class-file version.

## 37. Ví dụ điều tra: JaCoCo báo coverage 0 với MRJAR

Tình huống:

- Test JVM chạy Java17.
- Runtime nạp `META-INF/versions/17/com/example/codec/HexCodec.class`.
- JaCoCo execution data được ghi.
- Report task được cung cấp **base class file** `com/example/codec/HexCodec.class`.

Vì bytecode/probe mapping không tương ứng, report có thể bỏ class, cảnh báo mismatch hoặc hiển thị coverage không đúng kỳ vọng.

Hướng giải quyết:

1. Xác định class variant test JVM nạp.
2. Kiểm tra JaCoCo version hỗ trợ class-file major.
3. Cấu hình report với class files tương ứng runtime variant.
4. Đảm bảo source mapping đúng.
5. Test base runtime riêng khi library vẫn hỗ trợ Java8.
6. Không gộp execution data của các variant khác nhau một cách tùy tiện.
7. Phân biệt line coverage của logic chung với logic chỉ có trên JDK17.

Coverage report tạo thành công không chứng minh mọi runtime path đã được kiểm thử.

## 38. Ma trận kiểm thử MRJAR trong migration

Ví dụ một library cam kết chạy Java8, Java11, Java17 và Java21:

| Hạng mục | Java8 | Java11 | Java17 | Java21 |
|---|---|---|---|---|
| JAR có thể được nạp | Test | Test | Test | Test |
| Implementation được chọn | Base | Override11 hoặc base | Override17 | Override21 hoặc phiên bản thấp nhất phù hợp |
| Public API compatibility | Test | Test | Test | Test |
| Contract/behavior equivalence | Test | Test | Test | Test |
| Binary client built for Java8 | Test | Test | Test | Test |
| Serialization/protocol output | Test | Test | Test | Test |
| Reflection/JPMS nếu áp dụng | N/A hoặc theo mô hình | Test | Test | Test |
| Resource lookup | Test | Test | Test | Test |
| ServiceLoader/provider behavior | Test | Test | Test | Test |
| Tests với packaged JAR | Test | Test | Test | Test |
| Coverage của variant | Test | Test | Test | Test |
| Security scan/exposure | Review | Review | Review | Review |
| Performance baseline | Benchmark | Benchmark | Benchmark | Benchmark |

Các ô là **hạng mục cần thực hiện**, không phải kết quả PASS. Chọn những JDK mà artifact thực sự cam kết hỗ trợ; nếu phiên bản Java đã EOL và không còn được tổ chức chấp nhận, cần cân nhắc loại khỏi support matrix thay vì mặc định tiếp tục bảo trì vô thời hạn.

### 38.1. Contract test phải chạy cùng bộ input

Ví dụ cho `HexCodec`:

- Input rỗng.
- Byte values 0, 15, 127, 128, 255.
- Dữ liệu ngẫu nhiên có seed xác định.
- Input lớn.
- Null handling theo API contract.
- Concurrency nếu API được cam kết thread-safe.

So sánh outputs và exceptions của các implementations. Nếu chỉ kiểm tra `implementation()` khác nhau thì đã chứng minh selection, **chưa chứng minh hai bản có semantics giống nhau**.

### 38.2. Kiểm thử trên version không có override riêng

Nếu library có override 11 và 17, hãy chạy thêm Java16 (nếu môi trường/chiến lược hỗ trợ) để kiểm tra Java16 chọn version11. Tương tự, Java21 chọn version17 khi không có bản21. Đây là những trường hợp hữu ích để phát hiện giả định “chỉ chạy trên đúng N”.

## 39. Quy trình phát hành MRJAR

Một pipeline có thể chia như sau:

~~~text
Base source (Java 8)
      |
      +--> javac --release 8
      |
      v
Base output
      |
      +-----------------------------+
      |                             |
Java11 source                  Java17 source
      |                             |
javac --release 11          javac --release 17
      |                             |
      v                             v
versions/11 output           versions/17 output
      |                             |
      +--------------+--------------+
                     |
                     v
           Jar packaging + manifest
                     |
                     v
               jar --validate
                     |
                     v
              Inspect JAR entries
                     |
                     v
        Test on each supported runtime
                     |
                     v
        Static/security/coverage analysis
                     |
                     v
            Publish + artifact checksum
~~~

Cần đảm bảo compilation/packaging dependencies đã được ràng buộc trong build pipeline; không để `jar` task chạy trước khi versioned classes hoàn tất.

### 39.1. Release gating

Chỉ đánh dấu release sẵn sàng khi:

- Manifest đúng.
- Base và overlays có class-file targets phù hợp.
- Public API consistency được kiểm tra.
- Đã test JAR artifact trên các runtime được hỗ trợ.
- Class/resource selection và semantics đạt yêu cầu.
- Dependency/security scanner đã bao phủ variants.
- Integration với launcher/server thực tế được xác minh.
- Artifact được version, checksum và ký theo policy.

## 40. Những anti-pattern cần tránh

### 40.1. Chép source Java17 vào base tree rồi dùng --target 8

Nếu code tham chiếu Java17 APIs, `-target 8` đơn lẻ không bảo đảm chạy được Java8. Tách source trees và dùng `--release` phù hợp.

### 40.2. Đặt directory bằng class-file major

`META-INF/versions/61` **không** có nghĩa Java17. Directory phải mang Java feature release như `17`.

### 40.3. Thiếu Multi-Release manifest attribute

Có overlay entries nhưng JVM vẫn có thể dùng base class. Manifest là phần thiết yếu của định dạng.

### 40.4. Đổi public API giữa base và overlay

Cùng một tọa độ artifact nhưng khác method contract theo JDK làm consumers khó biên dịch/test và có thể lỗi linkage.

### 40.5. Test bằng classes directory rồi kết luận MRJAR hoạt động

Classes directory không có manifest và quy tắc versioned archive. Hãy test **packaged JAR**.

### 40.6. Chỉ test trên JDK mới nhất

Một JAR có thể chạy trên Java21 nhưng Java11 branch bị lỗi vì compiler target sai. Phải test runtime thấp nhất được hỗ trợ và những mốc override.

### 40.7. Merge/shade làm mất META-INF/versions

Shading có thể thay cấu trúc và manifest; inspect final artifact và test behavior trước release.

### 40.8. Coi mọi ZIP scanner là MR-aware

`ZipFile` hoặc custom loader có thể đọc physical entries mà không áp runtime-selection logic.

### 40.9. Chỉ scan base class về security

Versioned implementation cũng là production code và cần bảo trì, test, scan.

### 40.10. Dùng MRJAR để cố giữ hỗ trợ JDK EOL không có security patches

Một artifact có thể hỗ trợ nhiều JDK về mặt kỹ thuật, nhưng policy bảo mật có thể yêu cầu bỏ runtime quá cũ. MRJAR không thay được security maintenance của nền tảng.

## 41. Checklist trước khi giao MRJAR cho consumers

- [ ] Đã xác định Java minimum và những JDK releases được hỗ trợ.
- [ ] Base classes được biên dịch theo target thấp nhất phù hợp.
- [ ] Versioned classes nằm dưới đúng `META-INF/versions/N` với N từ 9.
- [ ] Class-file major của mỗi versioned entry tương thích với N.
- [ ] Manifest của archive có `Multi-Release: true`.
- [ ] Public/protected API consistency giữa base và overlays được kiểm chứng.
- [ ] `jar --validate` đã được chạy khi toolchain hỗ trợ.
- [ ] JAR listing cho thấy base và overlays đúng path.
- [ ] Contract tests chạy trên mọi runtime cam kết.
- [ ] Tests dùng packaged JAR, không chỉ output classes directory.
- [ ] Đã test Java runtimes nằm giữa các mốc override khi phù hợp.
- [ ] Resource/ServiceLoader/JPMS behavior được kiểm tra nếu library sử dụng.
- [ ] Nested JAR, shading hoặc WAR packaging không phá selection.
- [ ] Static analysis và security scanner bao phủ versioned code.
- [ ] Coverage được gắn với bytecode variant thực sự chạy.
- [ ] Build tool/compiler versions, checksums và provenance được ghi.
- [ ] Mọi khác biệt runtime/behavior có tài liệu và owner rõ ràng.

Danh sách này là hướng dẫn dành cho người thực hiện migration, **không phải chứng nhận một artifact cụ thể đã được kiểm thử**.

## 42. Nguyên tắc kết luận

- **Multi-release JAR là cơ chế Java 9/JEP 238 để một artifact mang nhiều implementation theo JDK**, không phải cách tự động nâng source lên API mới.
- **`META-INF/versions/N` dùng Java release N, không dùng class-file major.** Java17 dùng directory `17`, class-file major tương ứng thường là `61`.
- **Manifest `Multi-Release: true` là điều kiện quan trọng** để runtime nhận biết format.
- **Runtime chọn entry có N lớn nhất không vượt quá Java feature version của nó**, rồi fallback về base nếu không có override.
- **Mỗi logical class có thể chọn override khác nhau.** Không có “một version duy nhất của toàn bộ JAR” khi một số class chỉ có base.
- **Giữ public/protected API ổn định giữa các implementations.** Thay thuật toán nội bộ được, nhưng phải bảo vệ binary và behavior contracts.
- **Base source phải tương thích Java thấp nhất được hỗ trợ** và các overlay compilations phải có `--release` phù hợp.
- **`jar --validate` giúp kiểm tra cấu trúc/API consistency**, nhưng không thay integration/behavior tests.
- **Gradle/Maven cần tổ chức nhiều compile outputs và đóng gói versioned directories đúng cách**; test classes directory không đủ.
- **JPMS, ServiceLoader, custom class loaders và resource lookup có các quy tắc riêng**; không được suy rằng mọi tool/JAR loader đều MR-aware.
- **Fat JAR, shading, WAR và nested dependencies có thể làm thay đổi cách chọn class**; phải kiểm tra final artifact.
- **Security, coverage và static analysis phải tính đến từng variant** thay vì chỉ quét base.
- **Một JAR checksum không đổi vẫn có thể chạy code khác khi nâng JDK**, nên đổi JDK/image là lý do để chạy regression tests.

Trong Java Advance Compatibility Migration, MRJAR là một công cụ hữu ích để **duy trì khả năng chạy trên JDK cũ trong khi cung cấp implementation chuyên biệt cho JDK mới**. Nhưng lợi ích này chỉ bền vững khi cấu trúc `META-INF/versions` đúng, manifest được thiết lập rõ ràng, các class giữ chung hợp đồng API và mỗi runtime path được kiểm thử bằng artifact đóng gói thật. Khi quản lý tốt những yếu tố đó, một thư viện có thể tiến hóa theo Java mà không đòi mọi consumer phải nâng JDK cùng lúc.
