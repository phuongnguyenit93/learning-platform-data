# Tạo multi-release JAR và kiểm thử trên các JDK được hỗ trợ

## 1. Mục tiêu bài thực hành

Trong **Java Advance Compatibility Migration**, một thư viện Java có thể cần giữ Java 8 là phiên bản thấp nhất được hỗ trợ nhưng đồng thời muốn dùng API mới của Java 17 hoặc tối ưu hóa riêng cho JDK mới. Nếu biên dịch toàn bộ thư viện với Java 17, người dùng Java 8/11 có thể gặp UnsupportedClassVersionError. Nếu chỉ giữ implementation Java 8, thư viện bỏ lỡ các API hữu ích trên runtime mới.

**Multi-release JAR (MR-JAR)** là định dạng JAR có thể chứa nhiều bản của một class hoặc resource theo **Java feature release**. Các class nền nằm ở root; biến thể được đặt trong META-INF/versions/N và manifest có thuộc tính Multi-Release: true. Runtime Java 9+ có cơ chế chọn entry có version cao nhất không vượt version runtime, còn Java 8 dùng root classes và không thực hiện việc chọn versioned entries.

Bài thực hành sẽ:

1. Tạo lớp public org.example.mrjar.HexCodec có API ổn định.
2. Viết implementation nền **Java 8** dùng thao tác bit để mã hóa bytes sang hex.
3. Viết implementation **Java 17** cùng signature, dùng java.util.HexFormat.
4. Biên dịch bằng javac --release 8 và --release 17 với output directories riêng.
5. Đóng gói duy nhất một file hex-codec-mr.jar chứa manifest Multi-Release: true.
6. Xác nhận JDK 8/11 dùng bản nền, JDK 17/21 dùng bản Java 17.
7. So sánh class-file versions, validate JAR, kiểm thử contract và CI matrix.
8. Hiểu cách mở rộng trong Gradle, module path, fat JAR, dependency và runtime deployment.

**Kết quả kỳ vọng**: cùng một file JAR chạy thành công trên Java 8, 11, 17, 21, cho kết quả encode nhất quán nhưng dùng implementation phù hợp từng runtime. Các đoạn lệnh và output bên dưới là ví dụ để người học thực hiện; không phải log đã chạy trong workspace hiện tại.

## 2. MR-JAR giải quyết điều gì và không giải quyết điều gì?

| Nhu cầu | MR-JAR có phù hợp? | Giới hạn |
|---|---|---|
| Giữ Java minimum cũ, dùng API Java mới khi có | Có | Root code và dependencies vẫn phải chạy trên minimum Java. |
| Tối ưu implementation theo JDK version | Có | Cần chứng minh benefit và behavioral compatibility. |
| Duy trì một artifact Maven/Gradle | Có | CI phải test cùng artifact trên nhiều JDK. |
| Cho Java 8 thực thi class bytecode Java 17 | Không | Java 8 không hiểu class-file version Java 17. |
| Tự chuyển từ javax.* sang jakarta.* | Không | Binary API/framework/container compatibility cần xử lý riêng. |
| Tự chọn binary theo CPU, OS, libc | Không | JNI/JNA/native agent cần platform-specific packaging. |
| Tự xử lý dependency Java17-only trên Java 8 | Không | Runtime dependency graph và class loading vẫn có thể không tương thích. |
| Giải quyết thay đổi dữ liệu và event schemas | Không | Cần migration và compatibility contract riêng. |

MR-JAR không phải cơ chế để cùng một public class có API hoàn toàn khác nhau tùy JDK. Thiết kế an toàn là **giữ public/protected contract nhất quán, thay implementation nội bộ**. Các công cụ đóng gói có thể kiểm tra một số ràng buộc API, nhưng vẫn cần consumer integration tests.

### 2.1. Khi nào không nên dùng MR-JAR?

Nếu ứng dụng chỉ hỗ trợ Java 21, việc giữ nhiều implementations có thể là gánh nặng không cần thiết. Nếu major dependency mới không hỗ trợ Java 8, hoặc public API cần thay đổi căn bản, có thể phù hợp hơn khi nâng minimum Java, phát hành major version hoặc tách artifacts. MR-JAR hữu ích nhất khi phần cần specialization **nhỏ, ổn định và có đủ test coverage**.

## 3. Cơ chế chọn class theo phiên bản runtime

Một MR-JAR ví dụ:

~~~text
hex-codec-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 17/
│           └── org/example/mrjar/HexCodec.class
└── org/example/mrjar/
    ├── HexCodec.class
    └── Demo.class
~~~

Manifest:

~~~text
Manifest-Version: 1.0
Main-Class: org.example.mrjar.Demo
Multi-Release: true
~~~

Với class HexCodec:

| Java runtime | Class JVM chọn |
|---|---|
| Java 8 | Root org/example/mrjar/HexCodec.class. |
| Java 11 | Root class, vì không có variant 9–11. |
| Java 17 | META-INF/versions/17/org/example/mrjar/HexCodec.class. |
| Java 21 | Bản versions/17, vì chưa có variant 18–21. |

Việc chọn là **theo từng class/entry**. Demo chỉ có root nên Java 21 vẫn dùng root Demo. Một class khác có bản versions/11 có thể được nạp từ versions/11 trong cùng JAR.

### 3.1. Thư mục versions không chứa application version

Tên N là feature release Java, không phải version thư viện, build update hay semantic version ứng dụng:

~~~text
Hợp lệ về ý nghĩa Java release:
  META-INF/versions/9/
  META-INF/versions/11/
  META-INF/versions/17/
  META-INF/versions/21/

Không dùng để chọn Java release:
  META-INF/versions/java17/
  META-INF/versions/17.0.12/
  META-INF/versions/app-v2/
~~~

Java 17.0.x dùng thư mục 17. Nếu không có phiên bản 17 nhưng có 11, runtime sẽ chọn 11 cho class tương ứng.

### 3.2. Class-file version phải phù hợp

| Java | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Trong bài này, root classes phải là major 52; bản versions/17 có major 61 hoặc thấp hơn phù hợp Java 17. Không đưa class major 65 vào versions/17 vì JDK 17 không thể nạp bytecode đó.

### 3.3. Manifest quyết định MR behavior

Chỉ có thư mục META-INF/versions/17 trong ZIP chưa đủ. Manifest cuối cùng cần có Multi-Release: true. Một plugin đóng gói lại có thể loại bỏ attribute đó; do vậy cần kiểm tra **artifact cuối được phát hành**, không chỉ thư mục source hoặc JAR trung gian.

## 4. Chuẩn bị môi trường và cấu trúc thư mục

Môi trường thực hành:

- **Build JDK:** JDK 21 có javac/jar hỗ trợ --release.
- **Target bytecode root:** Java 8.
- **Target bytecode variant:** Java 17.
- **Test runtimes:** JDK 8, 11, 17, 21.
- Terminal, filesystem và quyền tạo files.
- Không cần application server, framework hoặc dependency ngoài.

Cấu trúc:

~~~text
hex-codec-lab/
├── src/
│   ├── base/java/org/example/mrjar/
│   │   ├── HexCodec.java
│   │   └── Demo.java
│   └── versions/17/java/org/example/mrjar/
│       └── HexCodec.java
├── manifest.mf
├── build/classes/
│   ├── base/
│   └── java17/
└── dist/
    └── hex-codec-mr.jar
~~~

**Quan trọng:** hai file HexCodec.java có cùng package/class name, nhưng khác source roots và output directories. Nếu biên dịch chúng cùng source set, compiler có thể báo duplicate class hoặc một bản overwrite bản kia, làm mất khả năng chọn variant.

### 4.1. Kiểm tra toolchain thực sự

~~~bash
java -version
javac -version
jar --help
~~~

Nếu máy có nhiều JDK, ưu tiên đường dẫn tuyệt đối hoặc toolchains được quản lý. Lệnh java -version trong một shell chưa chắc chứng minh javac/jar hoặc JVM trong container production là cùng installation.

## 5. Viết lớp nền cho Java 8

File: src/base/java/org/example/mrjar/HexCodec.java

~~~java
package org.example.mrjar;

public final class HexCodec {

    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        if (bytes == null) {
            throw new IllegalArgumentException(
                    "bytes must not be null");
        }

        char[] output = new char[bytes.length * 2];

        for (int i = 0; i < bytes.length; i++) {
            int value = bytes[i] & 0xff;
            output[2 * i] = HEX[value >>> 4];
            output[2 * i + 1] = HEX[value & 0x0f];
        }

        return new String(output);
    }

    public static String implementation() {
        return "base-java8";
    }
}
~~~

### 5.1. Giải thích

Lớp dùng những Java APIs có sẵn trên Java 8. Bytes của Java là signed (-128..127), nên bytes[i] & 0xff chuyển về khoảng 0..255 khi tách hai nibbles. Với byte FF, kết quả hex là ff, không phải chuỗi biểu diễn số âm.

API công khai được giữ cố định:

~~~java
public static String encode(byte[] bytes);
public static String implementation();
~~~

implementation() chỉ là marker chẩn đoán của bài lab để kiểm tra class loading; không nên tự xem nó như cơ chế security/feature negotiation của sản phẩm thực.

### 5.2. Hợp đồng hành vi

| Input | Expected result |
|---|---|
| new byte[0] | Chuỗi rỗng. |
| new byte[] {0} | "00". |
| new byte[] {0, 42, (byte) 255} | "002aff". |
| new byte[] {(byte) 128} | "80". |
| null | IllegalArgumentException. |

Mọi variant phải giữ những semantics này. Một public API signature giống nhau nhưng output khác, exception khác hoặc encoding khác vẫn có thể là regression nghiệp vụ.

## 6. Viết lớp Demo chạy được trên Java 8

File: src/base/java/org/example/mrjar/Demo.java

~~~java
package org.example.mrjar;

public final class Demo {

    private Demo() {
    }

    public static void main(String[] args) {
        byte[] data = {0x00, 0x2a, (byte) 0xff};
        String result = HexCodec.encode(data);

        if (!"002aff".equals(result)) {
            throw new AssertionError(
                    "Unexpected encoding: " + result);
        }

        if (!"".equals(HexCodec.encode(new byte[0]))) {
            throw new AssertionError("Empty input mismatch");
        }

        try {
            HexCodec.encode(null);
            throw new AssertionError("Null input accepted");
        } catch (IllegalArgumentException expected) {
            // API contract thống nhất giữa các implementations.
        }

        String spec = System.getProperty(
                "java.specification.version");
        String selected = HexCodec.implementation();

        System.out.println("java.specification.version=" + spec);
        System.out.println("implementation=" + selected);
        System.out.println("result=" + result);
    }
}
~~~

Demo chỉ sử dụng APIs phù hợp Java 8. Khi chạy bằng Java 17, chính HexCodec được runtime chọn lại từ variant; Demo vẫn được lấy ở root.

### 6.1. Vì sao test chỉ kiểm tra output chưa đủ?

Hai implementations có thể trả cùng "002aff". Nếu manifest thiếu Multi-Release: true thì JDK 17 có thể tiếp tục dùng bản base, Demo vẫn PASS về output. Ta cần **thêm assertion kiểm tra marker theo runtime** ở phần kiểm thử để xác nhận cơ chế MR-JAR thật sự hoạt động.

## 7. Viết implementation chuyên biệt Java 17

File: src/versions/17/java/org/example/mrjar/HexCodec.java

~~~java
package org.example.mrjar;

import java.util.HexFormat;

public final class HexCodec {

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        if (bytes == null) {
            throw new IllegalArgumentException(
                    "bytes must not be null");
        }

        return HexFormat.of().formatHex(bytes);
    }

    public static String implementation() {
        return "java17";
    }
}
~~~

HexFormat có từ Java 17, cung cấp encoding hex mà không cần tự viết vòng lặp. Kết quả mặc định từ HexFormat.of().formatHex là hex chữ thường, khớp với implementation nền trong ví dụ.

### 7.1. Vì sao không gọi HexFormat trực tiếp từ root?

Java 8 không có java.util.HexFormat. Một đoạn code root tham chiếu HexFormat có thể không compile với --release 8; ngay cả khi đặt trong nhánh chỉ chạy trên Java 17, compiler vẫn phải resolve kiểu và method.

Thiết kế MR-JAR tách hai class files để runtime cũ **không phải nạp class chứa tham chiếu tới API chưa tồn tại**.

### 7.2. API public phải ổn định

Bản Java 17 vẫn có đúng hai public static methods nhận và trả cùng types. Không đổi encode(byte[]) thành encode(ByteBuffer), không đổi return type từ String sang byte[] và không xóa method mà consumer đã sử dụng.

Đối với một thư viện thực tế, nếu muốn giảm duplication, có thể giữ public facade ổn định ở root rồi version hóa một implementation class nội bộ. Nhưng mô hình nào cũng phải kiểm tra binary compatibility và classloading.

## 8. Tạo manifest

File manifest.mf:

~~~text
Manifest-Version: 1.0
Main-Class: org.example.mrjar.Demo
Multi-Release: true

~~~

Manifest cần tuân thủ cú pháp JAR manifest, bao gồm dòng trống kết thúc phần main attributes. Ở ví dụ này:

- Main-Class cho phép chạy java -jar.
- Multi-Release: true bật MR-JAR resolution.
- Manifest-Version khai báo phiên bản định dạng manifest.

**Không được nhầm** Multi-Release với tên file module-info hoặc với Java release version. Tự tạo directory versions/17 không làm JVM chọn class đó nếu manifest/artifact không hợp lệ.

## 9. Compile root classes bằng javac --release 8

Giả sử dùng javac của **JDK 21** và đứng tại project root:

~~~bash
mkdir -p build/classes/base build/classes/java17 dist

javac --release 8 \
  -d build/classes/base \
  src/base/java/org/example/mrjar/HexCodec.java \
  src/base/java/org/example/mrjar/Demo.java
~~~

Output dự kiến:

~~~text
build/classes/base/org/example/mrjar/HexCodec.class
build/classes/base/org/example/mrjar/Demo.class
~~~

### 9.1. Vì sao dùng --release thay cho chỉ -source/-target?

--release 8 không chỉ chọn bytecode/class-file target mà còn giới hạn public Java platform APIs sẵn có ở Java 8 theo cơ chế compiler hỗ trợ. Chỉ dùng -source 8 -target 8 khi build bằng JDK mới có thể tạo bytecode version 52 nhưng vô tình tham chiếu API JDK mới hơn, gây lỗi linkage trên Java 8.

Lưu ý: --release **không** tự hạ class-file version của thư viện third-party đã compile trên Java 17/21. Phải kiểm tra runtime dependency graph riêng.

### 9.2. Tránh dùng javac mặc định

Không dùng javac source.java mà không đặt release, rồi giả định class sẽ chạy trên Java 8. Compiler JDK 21 mặc định có thể tạo class major 65. Phải xác nhận bằng javap và runtime test sau packaging.

## 10. Compile Java 17 variant riêng

~~~bash
javac --release 17 \
  -cp build/classes/base \
  -d build/classes/java17 \
  src/versions/17/java/org/example/mrjar/HexCodec.java
~~~

Output:

~~~text
build/classes/java17/org/example/mrjar/HexCodec.class
~~~

Phiên bản 17 được xuất riêng để jar tool đặt đúng vào META-INF/versions/17. Không biên dịch toàn bộ src/base và src/versions/17 vào chung một classes directory.

### 10.1. Compile classpath trong dự án lớn

Một variant có thể cần tham chiếu những class khác từ phần base hoặc dependency ngoài. Khi đó compile classpath phải bao gồm đúng những dependencies dùng tại Java release đích, nhưng không được làm code root vô tình liên kết với API mới.

Trong ví dụ, HexCodec Java 17 độc lập và chỉ dùng java.util.HexFormat, nên ít có rủi ro từ third-party libraries.

## 11. Đóng gói MR-JAR

~~~bash
jar --create \
  --file dist/hex-codec-mr.jar \
  --manifest manifest.mf \
  -C build/classes/base . \
  --release 17 \
  -C build/classes/java17 .
~~~

| Phần lệnh | Ý nghĩa |
|---|---|
| --create | Tạo JAR mới. |
| --file dist/hex-codec-mr.jar | Chọn đường dẫn artifact. |
| --manifest manifest.mf | Dùng manifest đã khai báo multi-release. |
| -C build/classes/base . | Đưa classes nền vào root JAR. |
| --release 17 | Đưa những entries tiếp theo vào vùng versioned 17. |
| -C build/classes/java17 . | Đưa Java 17 HexCodec.class vào META-INF/versions/17. |

Đây là cú pháp jar tool của JDK hỗ trợ MR-JAR. Không nên đổi tên thư mục versions thủ công hoặc rename class files để giả lập --release; nội dung bytecode vẫn phải compile đúng.

### 11.1. Các entries kỳ vọng

~~~text
META-INF/MANIFEST.MF
org/example/mrjar/HexCodec.class
org/example/mrjar/Demo.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Thứ tự liệt kê có thể khác; điều quan trọng là **đường dẫn chính xác**. Đặc biệt không được có prefix build/classes/java17 bên trong JAR.

### 11.2. Vì sao không zip hai classes cùng path?

ZIP/JAR chỉ có một logical root path cho một class. Nếu đưa hai versions của HexCodec.class vào cùng org/example/mrjar/HexCodec.class, một bản có thể overwrite bản khác hoặc gây duplicate entry. MR-JAR yêu cầu class mới nằm ở đường dẫn versioned riêng.

## 12. Kiểm tra cấu trúc JAR và manifest

Liệt kê:

~~~bash
jar --list --file dist/hex-codec-mr.jar
~~~

Tìm cả hai entries:

~~~text
org/example/mrjar/HexCodec.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Đọc manifest từ JAR cuối qua công cụ ZIP hoặc giải nén vào thư mục kiểm tra riêng. Phải thấy:

~~~text
Multi-Release: true
Main-Class: org.example.mrjar.Demo
~~~

**Không chỉ kiểm tra file manifest.mf trên filesystem:** Maven/Gradle plugin, shading hoặc repackaging có thể ghi đè manifest sau bước build trung gian.

### 12.1. jar --validate

~~~bash
jar --validate --file dist/hex-codec-mr.jar
~~~

Trên JDK phù hợp, công cụ kiểm tra cấu trúc và một số ràng buộc về versioned entries/API của multi-release JAR. CI cần xem exit code; không coi thông báo lỗi thành warning rồi cho publish.

**Giới hạn:** jar --validate không thay unit tests, consumer compatibility tests, runtime class selection assertions hay benchmark. Nó không tự chạy code hoặc phát hiện sai semantics nghiệp vụ.

### 12.2. Kiểm tra bytecode bằng javap

~~~bash
javap -verbose \
  -classpath build/classes/base \
  org.example.mrjar.HexCodec

javap -verbose \
  -classpath build/classes/java17 \
  org.example.mrjar.HexCodec
~~~

Trong output, root class expected major version **52**, variant expected major version **61**. Trên JDK hỗ trợ, có thể inspect versioned content bằng:

~~~bash
javap --multi-release 17 \
  -classpath dist/hex-codec-mr.jar \
  org.example.mrjar.HexCodec
~~~

Kết quả công cụ cần được so với cấu trúc artifact, nhưng runtime test ở bước sau vẫn là bằng chứng quan trọng nhất về class mà JVM thực sự nạp.

## 13. Chạy cùng một artifact trên các JDK

Giả sử có bốn installations đặt trong các biến JDK8_HOME, JDK11_HOME, JDK17_HOME, JDK21_HOME trên shell Unix-like:

~~~bash
"$JDK8_HOME/bin/java"  -jar dist/hex-codec-mr.jar
"$JDK11_HOME/bin/java" -jar dist/hex-codec-mr.jar
"$JDK17_HOME/bin/java" -jar dist/hex-codec-mr.jar
"$JDK21_HOME/bin/java" -jar dist/hex-codec-mr.jar
~~~

Trên Windows, dùng đường dẫn java.exe phù hợp với PowerShell/cmd; không sao chép cú pháp biến shell Unix một cách máy móc.

Kết quả kỳ vọng:

~~~text
JDK 8:
  java.specification.version=1.8
  implementation=base-java8
  result=002aff

JDK 11:
  java.specification.version=11
  implementation=base-java8
  result=002aff

JDK 17:
  java.specification.version=17
  implementation=java17
  result=002aff

JDK 21:
  java.specification.version=21
  implementation=java17
  result=002aff
~~~

Đây là **output mẫu**, không phải kết quả đã đo. Nếu JDK 17 xuất base-java8 nhưng result vẫn đúng thì phần chức năng đạt, nhưng **multi-release selection chưa đạt**.

### 13.1. Đừng tạo bốn JAR khác nhau

Mục tiêu bài lab là build once/test many:

~~~text
Build JDK 21
    │
    ▼
hex-codec-mr.jar (một checksum)
    │
    ├── JDK 8
    ├── JDK 11
    ├── JDK 17
    └── JDK 21
    │
    ▼
Contract tests + class-selection tests
~~~

Nếu mỗi runtime có một JAR riêng, bạn chưa chứng minh cơ chế multi-release của cùng một artifact. Trong CI, nên phân phối file qua artifact store và xác minh checksum giữa các jobs.

### 13.2. java -cp cũng cần được thử

MR-JAR thường được dùng làm library thay vì executable application:

~~~bash
"$JDK17_HOME/bin/java" \
  -cp dist/hex-codec-mr.jar \
  org.example.mrjar.Demo
~~~

Khi được class loader chuẩn nạp từ final JAR, bản versions/17 sẽ được chọn. Tuy nhiên, nếu classpath có loose build/classes/base đứng trước JAR, HexCodec có thể được lấy từ directory đó thay vì MR-JAR.

Không kiểm thử MR-JAR bằng classpath có những source output directories gây shadowing khi mục tiêu là validate final artifact.

## 14. Bổ sung assertion cho runtime selection

Demo ban đầu kiểm tra encode result, nhưng cần xác nhận implementation() tương ứng JDK. Thêm đoạn sau vào phương thức main:

~~~java
String version = System.getProperty(
        "java.specification.version");

int feature;
if (version.startsWith("1.")) {
    feature = Integer.parseInt(version.substring(2));
} else {
    feature = Integer.parseInt(version);
}

String expected = feature >= 17
        ? "java17"
        : "base-java8";

String actual = HexCodec.implementation();

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected variant " + expected
                    + ", got " + actual);
}
~~~

Đây là fragment được đặt **bên trong Demo.main**, không phải một file Java đầy đủ độc lập. Nó xử lý java.specification.version = 1.8 trên JDK 8 và các giá trị 11/17/21.

Khi đóng gói lại và chạy:

- Java 8/11 chọn base; selection assertion PASS.
- Java 17/21 chọn Java 17; selection assertion PASS.
- Nếu manifest mất Multi-Release: true, JDK 17/21 dùng root, test FAIL.
- Nếu versioned class nằm sai path, JDK 17/21 dùng root, test FAIL.

Với thư viện thực tế, marker có thể nằm trong internal test fixture hoặc consumer smoke test; không nhất thiết cần public method chỉ để kiểm tra implementation.

## 15. Functional contract tests trên mọi JDK

Không chỉ kiểm tra implementation marker. Mọi variant phải giữ contract:

| Test | Input | Expected |
|---|---|---|
| H-01 | byte array rỗng | Chuỗi rỗng. |
| H-02 | 00 | "00". |
| H-03 | 0F | "0f". |
| H-04 | 10 | "10". |
| H-05 | 7F | "7f". |
| H-06 | 80 | "80". |
| H-07 | FF | "ff". |
| H-08 | 00 2A FF | "002aff". |
| H-09 | null | IllegalArgumentException. |
| H-10 | bytes được tạo bằng fixed seed | Hex output nhất quán với oracle. |

### 15.1. JUnit Jupiter ví dụ

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.example.mrjar.HexCodec;

final class HexCodecContractTest {

    @Test
    void encodesBoundaryValues() {
        byte[] bytes = {0x00, 0x2a, (byte) 0xff};
        assertEquals("002aff", HexCodec.encode(bytes));
    }

    @Test
    void acceptsEmptyArray() {
        assertEquals("", HexCodec.encode(new byte[0]));
    }

    @Test
    void rejectsNullArray() {
        assertThrows(IllegalArgumentException.class,
                () -> HexCodec.encode(null));
    }
}
~~~

Đoạn test cần JUnit Jupiter dependencies phù hợp. Khi chạy trên Java 8, phải chọn JUnit/runtime dependencies hỗ trợ Java 8; đừng dùng một test framework version chỉ chạy Java 17 rồi kết luận Java 8 library không tương thích.

### 15.2. Gradle test có thể không nạp final JAR

Gradle Java Test task mặc định thường dùng output của source sets, tức classes directories, thay vì packaged JAR. Nó có thể chỉ nạp base HexCodec và không kiểm tra MR selection.

Vì vậy tách:

1. **Source-level tests:** logic của base và variant, chạy trên compiler/runtime phù hợp.
2. **Artifact-level smoke tests:** nạp **JAR đã đóng gói cuối cùng** trên JDK 8/11/17/21 và assert implementation marker lẫn behavior.

Nếu chỉ làm nhóm 1, bước multi-release packaging có thể hỏng mà CI vẫn xanh.

## 16. Mô hình Gradle build MR-JAR

Trong project Gradle, thường tách base và Java 17 variant thành hai compilation tasks. Ví dụ này dùng Gradle **Kotlin DSL** và toolchain JDK 21. Layout tương ứng:

~~~text
src/main/java/org/example/mrjar/HexCodec.java
src/main/java/org/example/mrjar/Demo.java
src/java17/java/org/example/mrjar/HexCodec.java
~~~

Chỉ đổi path source roots so với các phần trước; nội dung Java giữ nguyên.

### 16.1. build.gradle.kts minh họa

~~~kotlin
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.tasks.Jar

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.named<JavaCompile>("compileJava") {
    options.release.set(8)
}

val compileJava17 by tasks.registering(JavaCompile::class) {
    source = fileTree("src/java17/java") {
        include("**/*.java")
    }

    destinationDirectory.set(
        layout.buildDirectory.dir("classes/java/java17")
    )
    javaCompiler.set(javaToolchains.compilerFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    options.release.set(17)

    classpath = files(
        sourceSets.main.get().output,
        configurations.compileClasspath
    )
    dependsOn(tasks.named("classes"))
}

tasks.named<Jar>("jar") {
    dependsOn(compileJava17)

    manifest {
        attributes(
            "Main-Class" to "org.example.mrjar.Demo",
            "Multi-Release" to "true"
        )
    }

    into("META-INF/versions/17") {
        from(compileJava17.flatMap { it.destinationDirectory })
    }

    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Đây là **mẫu tham khảo** cần được điều chỉnh theo phiên bản Gradle/plugins và source sets thực tế. Trong dự án lớn có thể tạo dedicated source set cho Java 17, khai báo dependency buckets và kiểm soát compile order chi tiết hơn.

### 16.2. Giải thích Gradle tasks

- compileJava biên dịch main classes --release 8.
- compileJava17 chỉ lấy src/java17/java và --release 17, không overwrite main output.
- compileJava17 có dependency tới base output.
- jar task đóng gói main output ở root.
- jar task đặt Java 17 output dưới META-INF/versions/17.
- Manifest của JAR khai báo Multi-Release: true.

Build bằng JDK 21 **không** khiến root bytecode thành Java 21 nếu compileJava đã đặt options.release=8. Nhưng các third-party runtime dependencies vẫn cần kiểm tra.

### 16.3. Lệnh dùng trong project thử nghiệm

~~~bash
./gradlew clean jar
jar --list --file build/libs/hex-codec-lab.jar
jar --validate --file build/libs/hex-codec-lab.jar
~~~

Tên file thực tế phụ thuộc project name, version và Gradle archive settings. Những lệnh này là **ví dụ**, không được thực thi trong tác vụ viết bài hiện tại.

### 16.4. Không chỉ validate intermediate jar

Nếu dự án còn Shadow plugin, Maven Shade, bootJar hoặc framework repackaging, artifact cuối cùng có thể khác build/libs JAR do Java plugin tạo ra. Luôn kiểm tra manifest/entries và chạy runtime smoke với artifact **sẽ được publish/deploy**, không chỉ một JAR tạm trong build.

## 17. Gradle Test runtime và JDK matrix

Một phương án chọn JDK cho Test tasks:

~~~kotlin
val testJdk = providers.gradleProperty("testJdk")
    .orElse("17")
    .map(String::toInt)

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(
            JavaLanguageVersion.of(testJdk.get())
        )
    })
}
~~~

Trong CI, có thể chạy:

~~~bash
./gradlew test -PtestJdk=8
./gradlew test -PtestJdk=11
./gradlew test -PtestJdk=17
./gradlew test -PtestJdk=21
~~~

Nhưng phải phân biệt **Gradle tests chạy trên classes** với **smoke test chạy trên final MR-JAR**. Chọn Java launcher cho Test task chưa tự làm classpath trỏ vào JAR versioned; cần artifact-level job riêng như phần 13–14.

Nếu chạy nhiều Gradle jobs song song, cần quản lý build directory/caches và toolchains để tránh race hoặc nhầm output.

## 18. Thiết kế CI build once, test many

Một matrix minh họa:

| CI job | JDK | Kiểm tra bắt buộc |
|---|---|---|
| package | Build JDK 21 | Root --release 8, variant --release 17, jar validation. |
| smoke-java8 | Java 8 | base-java8, behavior đúng, exit 0. |
| smoke-java11 | Java 11 | base-java8, behavior đúng, exit 0. |
| smoke-java17 | Java 17 | java17, behavior đúng, exit 0. |
| smoke-java21 | Java 21 | java17, behavior đúng, exit 0. |
| consumer-library | Các JDK công bố | Public API có thể dùng từ app khác. |
| packaging-integration | JDK/framework liên quan | Nested/fat JAR vẫn giữ MR resolution. |

Một CI provider có thể dùng concept:

~~~yaml
strategy:
  matrix:
    java: ['8', '11', '17', '21']
~~~

Đây là **trích đoạn minh họa**, không phải workflow GitHub Actions hoàn chỉnh. Workflow thực cần checkout, Java setup, build artifact upload/download, permissions và cách xác minh checksum.

### 18.1. Shell pseudo-CI

~~~bash
set -eu

JAR=dist/hex-codec-mr.jar

jar --validate --file "$JAR"

"$JDK8_HOME/bin/java"  -jar "$JAR"
"$JDK11_HOME/bin/java" -jar "$JAR"
"$JDK17_HOME/bin/java" -jar "$JAR"
"$JDK21_HOME/bin/java" -jar "$JAR"
~~~

Khi Demo đã được bổ sung assertion version selection, bất kỳ JDK nào nạp nhầm class sẽ tạo non-zero exit code.

**Nguyên tắc quality gate:** thiếu một runtime test bắt buộc hoặc thiếu artifact metadata không được tự động coi là PASS. Nếu môi trường CI chưa có JDK 8, phải ghi là chưa có bằng chứng cho Java 8, thay vì tuyên bố hỗ trợ vì Java 21 chạy tốt.

### 18.2. Cùng checksum của một artifact

Nếu CI rebuild JAR riêng trong từng matrix job, có thể vô tình tạo:

~~~text
JDK 8  → root-only artifact
JDK 11 → root-only artifact
JDK 17 → Java17-only artifact
JDK 21 → Java17-only artifact
~~~

Bốn artifact đều có thể chạy nhưng không chứng minh MR-JAR. Hãy build một artifact, lưu checksum (ví dụ SHA-256 theo policy), đưa chính artifact đó vào các runtime jobs.

## 19. Binary API compatibility và consumer tests

Đối với versioned class, Java compiler/JVM phải thấy hợp đồng public/protected tương thích.

### 19.1. So signatures bằng javap

~~~bash
javap -public \
  -classpath build/classes/base \
  org.example.mrjar.HexCodec

javap -public \
  -classpath build/classes/java17 \
  org.example.mrjar.HexCodec
~~~

Expected public methods:

~~~text
public static java.lang.String encode(byte[]);
public static java.lang.String implementation();
~~~

Một tool so API binary có thể kiểm tra thêm superclass, interfaces, fields, annotations và những thay đổi public/protected khác. Nhưng API equality cũng không chứng minh output semantics đúng.

### 19.2. Consumer đã compile trên Java 8

Một kịch bản có giá trị:

1. Compile consumer riêng với --release 8 và public API của root.
2. Đóng gói consumer cùng dependency MR-JAR đã build.
3. Chạy consumer trên JDK 8/11/17/21.
4. Kiểm tra không có NoSuchMethodError, IllegalAccessError, LinkageError.
5. Kiểm tra output và exception semantics.

Nếu bản Java 17 bỏ một method mà binary consumer vẫn gọi, lỗi có thể chỉ xuất hiện trên JDK 17/21, còn tests Java 8/11 PASS.

### 19.3. Ví dụ API break

Root:

~~~java
public static String encode(byte[] bytes);
~~~

Variant sai:

~~~java
public static byte[] encode(byte[] bytes);
~~~

Đó là thay đổi JVM method descriptor, không phải chỉ một tối ưu implementation. Không nên lợi dụng MR-JAR để phát hành API diverging theo JDK nếu consumer contract yêu cầu ổn định.

## 20. Module path và JPMS

Java 9 giới thiệu module system. Một MR-JAR có thể chạy trên classpath và có những cách tích hợp với module path, nhưng public packages, module descriptors, exports/opens và service resolution cần xem xét riêng.

### 20.1. Classpath PASS chưa chắc module path PASS

Trên module path có thể gặp:

- Module name không ổn định.
- Split packages giữa nhiều modules.
- Reflection không có opens.
- Service providers chưa được khai báo đúng.
- Dependency thiếu requires hoặc không resolve.

Nếu library được công bố hỗ trợ module path, hãy test một consumer module thật sự trên các JDK được hỗ trợ.

### 20.2. module-info.class trong MR-JAR

Một số project giữ base Java 8 nhưng cung cấp module descriptor cho Java 9 trở lên qua versioned entries, ví dụ concept:

~~~text
root Java 8 classes
META-INF/versions/9/module-info.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Descriptor phải được compile theo Java release tương ứng và tuân thủ module/JAR constraints. Không đặt Java 17 module-info.class vào versions/9 rồi kỳ vọng JDK 9 có thể đọc nó.

Với bài lab này, chưa cần module-info.class; nên làm đúng classpath MR-JAR trước khi mở rộng sang modular packaging.

## 21. ServiceLoader và custom classloaders

Nếu library dùng ServiceLoader hoặc plugin architecture, cần test runtime discovery.

Ví dụ service descriptor:

~~~text
META-INF/services/org.example.api.CodecProvider
~~~

Một provider class chỉ tồn tại trong versions/17 có thể không khả dụng trên Java 8. Tốt hơn là giữ service provider contract phù hợp minimum Java và version hóa implementation có kiểm soát.

### 21.1. Class loader tùy chỉnh

Một plugin loader tự đọc raw ZIP entries có thể lấy root class thay vì áp dụng MR-JAR semantics. Không mặc định mọi launcher, application server, nested JAR loader hoặc bytecode transformer xử lý versioned entries giống standard JVM class loader.

Đối với framework dùng custom classloading:

1. Kiểm tra framework version được hỗ trợ.
2. Package MR-JAR giống production.
3. Gọi class qua loader thật của framework.
4. Assert variant marker và behavior.
5. Test ServiceLoader/reflection nếu có.

### 21.2. Raw ZIP khác runtime resolution

Khi mở JAR như một ZIP thuần, công cụ có thể nhìn cả:

~~~text
org/example/mrjar/HexCodec.class
META-INF/versions/17/org/example/mrjar/HexCodec.class
~~~

Runtime Java chọn một bản theo feature version. Công cụ static scanner có thể cần kiểm tra **tất cả variants**, không chỉ entry root; ngược lại, công cụ bytecode rewriting cần giữ đúng layout và signatures sau xử lý.

## 22. Resources và versioned entries

Trong các môi trường MR-JAR-aware, việc lookup resources có thể chịu ảnh hưởng bởi versioned entries; nhưng raw ZIP tooling và custom classloaders có thể có hành vi khác.

Ví dụ concept:

~~~text
config/default.properties
META-INF/versions/17/config/default.properties
~~~

Nếu muốn version hóa resources, cần test riêng với ClassLoader.getResource/getResourceAsStream hoặc API đang dùng trong app. Kiểm tra xem framework loader có thực sự áp dụng semantics theo runtime version không.

Đối với bài thực hành đầu tiên, chỉ override HexCodec.class để giữ mô hình đơn giản. Không lưu secrets trong JAR hoặc versioned resource: các entries vẫn có thể được giải nén như ZIP và không được mã hóa bởi MR-JAR.

## 23. Fat JAR, shading và nested libraries

Packaging plugins như Shadow/Maven Shade hoặc executable JAR packaging có thể làm hỏng MR-JAR nếu cấu hình/version không hỗ trợ:

- Manifest Multi-Release: true bị bỏ.
- META-INF/versions/N bị loại khỏi archive.
- Versioned class bị chuyển lên root.
- Relocation class names chỉ áp dụng cho base, không áp dụng cho versions.
- Duplicate files bị merge sai.
- Nested JAR classloader bỏ qua MR resolution.

### 23.1. Hai vòng kiểm thử

~~~text
Thư viện gốc hex-codec-mr.jar
       │
       ├── jar validation
       └── direct runtime matrix
              │
              ▼
Consumer application packaging
       │
       ├── fat/shaded/boot JAR
       └── framework classloader
              │
              ▼
Consumer integration matrix
~~~

Không kết luận một Spring Boot/OSGi/application-server deployment sẽ chọn đúng Java17 variant chỉ vì direct classpath test của library PASS. Phải test artifact thực sự triển khai.

### 23.2. JAR signing

Nếu có ký JAR, việc chỉnh sửa manifest hoặc class files sau bước ký có thể làm signatures không còn hợp lệ. Thiết kế pipeline compile → assemble → validate → sign/publish và kiểm tra artifact đã ký theo policy.

## 24. Dependency graph và Java minimum

MR-JAR chỉ chọn classes theo JDK version; không tự giải quyết mọi dependency. Đặc biệt:

- Dependency Java 17-only được khai báo là runtime bắt buộc có thể làm JDK 8 fail nếu bị nạp.
- Class mới có thể được framework scanner eager-load trên runtime cũ.
- Third-party bytecode không bị javac --release 8 tự chuyển thành Java8-compatible.
- Reflection, ServiceLoader và native libraries có thể chạm lỗi muộn khi feature được gọi.

Vì vậy hãy kiểm tra:

1. Resolved runtimeClasspath hoặc Maven dependency tree.
2. Minimum Java version của dependencies trực tiếp/bắc cầu.
3. Class-file versions bên trong dependency JARs.
4. Native libraries/agents và OS ABI nếu có.
5. Consumer integration chạy trên Java minimum.

Đôi khi nên tách dependency chuyên biệt thành artifact khác thay vì cố giấu nó trong MR-JAR. Nếu toàn bộ sản phẩm đã chuyển sang Java 17, việc nâng minimum version có thể đơn giản hơn giữ nhiều compatibility variants.

## 25. Mở rộng: thêm Java 21 variant

Nếu muốn tiếp tục lab, thêm một source root:

~~~text
src/versions/21/java/org/example/mrjar/HexCodec.java
~~~

Class này phải có **cùng public signatures**. Có thể dùng APIs xuất hiện ở Java 21 trong phần implementation, ví dụ SequencedCollection.getFirst(), nhưng vẫn phải giữ encode output và error contracts.

Compile:

~~~bash
mkdir -p build/classes/java21

javac --release 21 \
  -d build/classes/java21 \
  src/versions/21/java/org/example/mrjar/HexCodec.java
~~~

Package khi đã có source/compiled variant:

~~~bash
jar --create \
  --file dist/hex-codec-mr.jar \
  --manifest manifest.mf \
  -C build/classes/base . \
  --release 17 \
  -C build/classes/java17 . \
  --release 21 \
  -C build/classes/java21 .
~~~

Khi đó runtime selection đổi thành:

| Runtime | Expected implementation |
|---|---|
| Java 8/11 | base-java8 |
| Java 17 | java17 |
| Java 21 | java21, nếu bản Java21 trả marker đó |

Không chỉ thêm versions/21 directory rỗng và kỳ vọng JVM tự tạo specialization. Cần compile/packaging/test đầy đủ, cập nhật Gradle tasks và CI assertions.

### 25.1. Bài tập tự mở rộng

Thử tạo bản Java 21 dùng một API mới nhưng vẫn encode đúng "002aff" cho dãy bytes mẫu. Trước khi chấp nhận variant mới, chạy:

- jar --validate.
- Public API signature comparison.
- JDK8/JDK11/JDK17/JDK21 smoke tests.
- Contract test cho bytes rỗng, FF, null và dữ liệu lớn.
- Consumer integration trên packaging thực tế.

## 26. Benchmark và hiệu năng giữa variants

Không mặc định HexFormat Java 17 nhanh hơn vòng lặp Java 8 trong mọi tình huống. Benchmark cần kiểm soát JIT, warmup, workload, hardware, memory và JDK update.

Nếu muốn so **thuật toán**:

- Chạy hai implementations trên **cùng JDK 17** nếu có thể.
- Dùng cùng dataset, input distribution và collector/flags.
- JMH hoặc một harness benchmark phù hợp với warmup/measurement/forks.
- Đo throughput, ns/op, allocation nếu liên quan.

Nếu so Java 8 runtime với Java 17 runtime, chênh lệch còn bao gồm JIT/GC/runtime implementation, nên không thể quy toàn bộ cho API HexFormat.

### 26.1. Behavior trước, benchmark sau

Chỉ benchmark sau khi xác nhận outputs tương đương trên tất cả test cases. Một implementation nhanh nhưng bỏ qua validation, dùng encoding sai hoặc đọc thiếu dữ liệu không được xem là cải thiện có thể phát hành.

### 26.2. Dữ liệu lớn và memory usage

Trong bản base, new char[bytes.length * 2] có thể overflow/thiếu bộ nhớ khi input quá lớn. Bản Java 17 dùng HexFormat cũng cần memory để tạo output. Trong sản phẩm thực tế, phải có max input policy hoặc streaming interface phù hợp; nếu thêm validation, áp dụng **giống nhau ở root và versioned class**.

## 27. Bảng lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| JDK 8 gặp UnsupportedClassVersionError | Root hoặc dependency compile quá Java8. | javap major version, --release 8, runtime dependencies. |
| JDK 17 vẫn in base-java8 | Manifest thiếu Multi-Release, path sai, classpath shadowing. | Đọc manifest/artifact, marker, classpath. |
| JDK 11 nạp class Java 17 | Class Java17 bị đặt ở root hoặc custom loader sai. | Kiểm tra JAR layout/bytecode. |
| javac không nhận HexFormat | Compile variant bằng JDK <17 hoặc --release 8. | javac -version, options.release. |
| jar --validate báo API mismatch | Variant đổi public/protected signatures hoặc layout sai. | javap -public, sửa contract. |
| Duplicate class lúc compile | Hai HexCodec.java nằm cùng source set. | Tách source roots/output. |
| Unit tests PASS, final JAR lỗi | Tests chạy loose classes, package cuối sai. | Artifact-level smoke tests. |
| NoSuchMethodError trên một JDK | API binary variant/dependency mismatch. | Consumer binary tests, dependency analysis. |
| ServiceLoader fail chỉ trên Java8 | Provider/config chỉ có ở Java17. | Java8 integration test. |
| Fat JAR nạp bản sai | Shading/nested classloader không giữ MR semantics. | Verify final artifact/framework runtime. |
| Agent/native lỗi trên Linux arm64 | MR-JAR không chọn OS/CPU ABI. | Native artifacts và environment matrix. |
| Kết quả khác giữa CI runners | Toolchains/flags/caches/dependencies khác. | Pin versions, artifact digest và baseline. |

### 27.1. Một quy trình điều tra nhanh

Khi Java 17 không dùng variant:

1. Kiểm tra đúng Java executable/version.
2. Kiểm tra final JAR path và checksum.
3. Đọc MANIFEST.MF trong final JAR.
4. Kiểm tra META-INF/versions/17 path chính xác.
5. Kiểm tra major version của variant <= Java17 limit.
6. Xem classpath có loose base classes hoặc duplicate JARs không.
7. Kiểm tra custom classloader/nested packaging.
8. Chạy selection assertions và lưu exit code/log.

Đừng sửa code encode khi lỗi thực tế chỉ là manifest hoặc cấu trúc JAR.

## 28. Những ngộ nhận cần tránh

**“MR-JAR chạy được mọi Java version.”** Không. Root và dependencies phải hỗ trợ Java minimum, còn các runtime ngoài support matrix chưa có bằng chứng.

**“Có thư mục versions là đủ.”** Không. Manifest và versioned layout phải hợp lệ.

**“Java 21 tự chạy Java17 code trong Java8.”** Không. Java8 runtime chỉ có APIs/bytecode mà nó hỗ trợ.

**“Biên dịch với JDK21 đồng nghĩa output class Java21.”** Tùy options.release/--release. Cần kiểm tra bytecode và runtime load.

**“jar --validate là đủ.”** Không. Chỉ là validation cấu trúc/API ở phạm vi công cụ; functional/integration tests vẫn bắt buộc.

**“Gradle Test tasks tự thử MR-JAR.”** Không nhất thiết, vì test classpath có thể là classes directories.

**“MR-JAR thay Maven/Gradle dependency constraints.”** Không. Dependency Java minimum và runtime linkage vẫn cần kiểm tra.

**“MR-JAR là cơ chế bảo mật hoặc ẩn code.”** Không. Entries vẫn đọc được từ ZIP.

**“MR-JAR chọn native library theo OS/CPU.”** Không. Versioned directories chỉ theo Java release.

**“Tối ưu bản Java17 thì public signatures có thể tùy ý thay.”** Không. Consumer cần API contract ổn định; nếu cần breaking changes, xem xét major release/artifact riêng.

## 29. Checklist nghiệm thu bài thực hành

### 29.1. Compile và JAR format

- [ ] Root HexCodec/Demo compile với --release 8.
- [ ] Java17 HexCodec compile với --release 17.
- [ ] Output root và Java17 không overwrite nhau.
- [ ] Manifest cuối chứa Multi-Release: true và Main-Class đúng.
- [ ] JAR chứa root HexCodec.class và versions/17 HexCodec.class.
- [ ] jar --validate PASS.
- [ ] Class-file major versions phù hợp 52 và 61.

### 29.2. Runtime

- [ ] JDK8: implementation=base-java8, result=002aff.
- [ ] JDK11: implementation=base-java8, result=002aff.
- [ ] JDK17: implementation=java17, result=002aff.
- [ ] JDK21: implementation=java17, result=002aff.
- [ ] Selection assertion được chạy trên final artifact.
- [ ] Test null, empty, FF và input boundaries.
- [ ] Không nạp nhầm loose classes khi test packaged JAR.
- [ ] Một artifact checksum được dùng trong toàn bộ runtime matrix.

### 29.3. Release/integration

- [ ] Base/variant public signatures tương thích.
- [ ] Consumer Java8-compiled code chạy trên JDK matrix.
- [ ] Runtime dependency graph hỗ trợ Java minimum.
- [ ] Module path/ServiceLoader/custom loader có test nếu sản phẩm dùng.
- [ ] Shaded/fat/nested JAR cuối giữ đúng MR semantics.
- [ ] JDK compiler/Gradle plugins và artifact provenance được ghi lại.
- [ ] Release notes nêu support matrix thực tế và hạn chế.

Checklist này dành cho **người học tự kiểm chứng**. Không tự đánh dấu các bước đã chạy nếu chỉ đọc hướng dẫn hoặc xem output giả định.

## 30. Mẫu báo cáo kết quả

~~~text
Module: Java Advance Compatibility Migration
Lesson: Tạo multi-release JAR và kiểm thử trên các JDK được hỗ trợ

Artifact:
  jar path:
  jar checksum:
  manifest Multi-Release:
  root class major:
  versioned class major:
  jar --validate exit code:

Build:
  JDK vendor/build:
  javac --release base:
  javac --release variant:
  build tool/plugin versions:

Runtime:
  Java 8: selected class / output / exit status
  Java 11: selected class / output / exit status
  Java 17: selected class / output / exit status
  Java 21: selected class / output / exit status

Contracts:
  encode empty:
  encode 002aff fixture:
  encode null:
  public API diff:

Integration:
  classpath:
  module path if applicable:
  shaded/boot JAR if applicable:
  minimum-JDK dependency check:

Decision:
  PASS / FAIL / INCONCLUSIVE:
  blockers:
  owner:
  evidence reference:
~~~

Không điền các kết quả PASS giả. Mỗi giá trị nên lấy từ lệnh thực thi, test reports, artifact metadata và runtime đã kiểm chứng.

## 31. Quy trình áp dụng MR-JAR trong dự án migration thật

**Bước 1 — Xác định Java minimum và target matrix.** Không nâng ngầm minimum Java khi thư viện vẫn cam kết hỗ trợ JDK cũ.

**Bước 2 — Chọn implementation có lợi ích rõ.** Ưu tiên một API nội bộ hoặc utility nhỏ; tránh duplicate toàn bộ framework modules.

**Bước 3 — Viết contract tests.** Public API, input/output, exception behavior, serialization và concurrency nếu có.

**Bước 4 — Tách source roots.** Root code/variant code và compiled output cần riêng biệt.

**Bước 5 — Biên dịch --release.** Dùng toolchain đủ mới và giữ restrictions của Java minimum.

**Bước 6 — Đóng gói đúng MR layout.** Manifest Multi-Release: true, META-INF/versions/N đúng path.

**Bước 7 — Validate artifact.** jar --list, jar --validate, class-file versions, public API diff.

**Bước 8 — Runtime matrix.** Chạy **một artifact** trên tất cả JDK được hỗ trợ; assert cả version selection và behavior.

**Bước 9 — Kiểm thử consumer packaging.** Test shaded/fat JAR, framework loader, classpath/module path nếu có.

**Bước 10 — Release và theo dõi.** Version hóa build metadata/checksum, ghi support contract và có phương án rollback artifact nếu bản đóng gói mới bị lỗi.

## 32. Kết luận

**Multi-release JAR cho phép một Java artifact chứa implementation nền và các variants theo JDK release.** Với root classes biên dịch Java 8, bản Java 17 trong META-INF/versions/17 và manifest Multi-Release: true, một thư viện có thể hỗ trợ JDK 8/11 và đồng thời sử dụng java.util.HexFormat trên JDK 17/21 mà không đòi Java 8 hiểu bytecode mới.

Điểm mấu chốt của bài thực hành không phải chỉ tạo được một file JAR. Cần **compile đúng --release, validate manifest/class versions, chạy cùng artifact trên Java 8/11/17/21, kiểm tra class được chọn và hợp đồng API**, sau đó lặp lại với packaging thật của ứng dụng tiêu thụ thư viện.

Trong Java Advance Compatibility Migration, MR-JAR là công cụ có giá trị khi cần duy trì minimum Java cũ và chuyên biệt hóa một số implementations. Nó không tự xử lý dependency compatibility, native ABI, modules, dữ liệu hay bảo mật. Chỉ khi có support matrix, regression tests và CI gates dựa trên **runtime thực sự được công bố**, nhóm mới có cơ sở tin cậy để phát hành multi-release JAR cho cả JDK cũ lẫn JDK mới.
