# Quy tắc lựa chọn lớp theo phiên bản runtime trong Multi-Release JAR

Multi-Release JAR (MR-JAR) cho phép một JAR chứa nhiều phiên bản của cùng một class hoặc resource để chạy trên các phiên bản Java khác nhau. Runtime chọn bản phù hợp dựa trên **feature version** của chính JVM đang chạy. Ví dụ, nếu JAR có bản gốc, bản Java 17 và bản Java 21 thì JDK 24 chọn bản Java 21; JDK 17 chọn bản Java 17; runtime chưa có bản thay thế sẽ dùng bản gốc.

MR-JAR là cơ chế chuẩn của JDK từ Java 9, hữu ích khi một thư viện cần giữ khả năng chạy trên baseline cũ nhưng muốn tận dụng API hoặc tối ưu riêng trên JDK mới. Một JAR duy nhất có thể phục vụ nhiều runtime mà không cần đổi tên artifact.

## 1. Cấu trúc của Multi-Release JAR

Một MR-JAR giữ class/resource dùng làm baseline ở thư mục gốc của JAR. Các bản thay thế nằm dưới `META-INF/versions/<N>/`, trong đó `N` là feature version Java từ 9 trở lên.

Ví dụ:

```text
version-choice.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 17/
│       │   └── com/acme/version/VersionChoice.class
│       └── 21/
│           └── com/acme/version/VersionChoice.class
└── com/
    └── acme/
        └── version/
            ├── Main.class
            └── VersionChoice.class
```

Đường dẫn logic của hai class `VersionChoice.class` giống nhau. Bản ở thư mục gốc là baseline; các bản trong `versions/17` và `versions/21` thay thế class đó khi runtime phù hợp.

Không đặt số phiên bản theo dạng `1.7`, `17.0.1` hoặc tên thư mục tùy ý. Tên thư mục phải là feature version dạng số nguyên, ví dụ `9`, `11`, `17`, `21`.

## 2. Bật chế độ Multi-Release trong manifest

Chỉ có thư mục `META-INF/versions` chưa đủ để tạo MR-JAR. Manifest phải khai báo thuộc tính `Multi-Release: true` trong main section:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Thuộc tính này cho runtime biết archive có các entry thay thế theo phiên bản. Nếu thiếu hoặc mang giá trị khác `true`, các đường dẫn dưới `META-INF/versions` không được dùng để thay thế class/resource ở thư mục gốc.

Manifest cần có dòng trống kết thúc main section. Dùng đúng manifest của JAR khi đóng gói; kiểm tra lại bằng `jar --list` và `jar --validate`.

## 3. Quy tắc runtime chọn class

Khi class loader cần đọc một đường dẫn logic trong MR-JAR đã bật `Multi-Release: true`, runtime xét các thư mục version theo thứ tự từ cao xuống thấp:

1. Lấy feature version của runtime, ví dụ JDK 24 có feature version là `24`.
2. Tìm entry tương ứng trong `META-INF/versions/24/`, rồi giảm dần tới `META-INF/versions/9/`.
3. Chọn entry đầu tiên tồn tại, tức entry có version cao nhất nhưng không vượt quá runtime version.
4. Nếu không có entry versioned phù hợp, dùng entry ở thư mục gốc của JAR.

Ví dụ với JAR chỉ có bản gốc, `versions/17` và `versions/21`:

| Runtime | Entry được chọn | Lý do |
|---|---|---|
| Java 8 | Bản gốc | Runtime trước Java 9 không áp dụng cơ chế MR-JAR. |
| Java 9 | Bản gốc | Chưa có entry versioned nào có version nhỏ hơn hoặc bằng 9. |
| Java 17 | `META-INF/versions/17/...` | Có bản 17 và không có bản cao hơn phù hợp. |
| Java 20 | `META-INF/versions/17/...` | Bản 21 cao hơn runtime nên bị bỏ qua. |
| Java 21 | `META-INF/versions/21/...` | Bản 21 vừa khớp runtime. |
| Java 24 | `META-INF/versions/21/...` | Bản 21 là bản cao nhất không vượt quá 24. |

Runtime không yêu cầu phải có thư mục cho mọi phiên bản Java. Chỉ tạo các bản thay thế khi thực sự cần thay đổi implementation hoặc sử dụng API mới.

## 4. Baseline và các bản thay thế

Baseline là class/resource ở thư mục gốc. Nó phải chạy được trên phiên bản Java thấp nhất mà thư viện cam kết hỗ trợ. Mọi class mà baseline tham chiếu cũng phải tương thích với phiên bản đó.

Ví dụ, thư viện hỗ trợ Java 9 trở lên có thể biên dịch baseline bằng `javac --release 9`. Bản thay thế trong `versions/17` có thể biên dịch bằng `--release 17` và dùng API được bổ sung trong Java 17. Bản `versions/21` có thể dùng API của Java 21.

```shell
javac --release 9  -d base-classes  base-src/com/acme/version/*.java
javac --release 17 -d v17-classes   v17-src/com/acme/version/VersionChoice.java
javac --release 21 -d v21-classes   v21-src/com/acme/version/VersionChoice.java
```

`--release N` giới hạn cả class-file target và tập API Java mà source được phép sử dụng. Nhờ đó, bản baseline không vô tình gọi API chỉ tồn tại ở runtime mới hơn.

Không nhất thiết phải tạo bản cho Java 17 hoặc 21 chỉ vì các phiên bản đó tồn tại. Nếu baseline đã đáp ứng hiệu năng và hành vi, runtime mới có thể tiếp tục dùng baseline.

## 5. Tính nhất quán của API giữa các phiên bản

Các class thay thế phải giữ hợp đồng mà consumer nhìn thấy nhất quán giữa các runtime. Đặc biệt, không thiết kế một bản versioned có public API khác với baseline để consumer phải biên dịch theo một tập method khác tùy runtime.

JAR tool cung cấp `jar --validate` để kiểm tra API được export bởi MR-JAR có nhất quán giữa các release hay không. Công cụ cũng phát hiện trường hợp một public class mới chỉ xuất hiện ở thư mục versioned mà không có entry tương ứng ở baseline.

```shell
jar --validate --file version-choice.jar
```

Với archive hợp lệ, lệnh kết thúc thành công. Hãy chạy kiểm tra trên artifact build trước khi phát hành. Kiểm tra này không thay thế test hành vi, kiểm thử tương thích nhị phân hoặc test trên từng runtime mục tiêu.

Implementation bên trong có thể khác nhau theo version, miễn là hợp đồng API cần thiết được giữ ổn định. Nếu cần thêm một API công khai mới, hãy thiết kế chiến lược tương thích rõ ràng thay vì chỉ thêm class vào một thư mục versioned.

## 6. Tạo Multi-Release JAR bằng `jar`

Ví dụ dưới đây tạo một thư viện có baseline Java 9 và hai bản thay thế Java 17, Java 21.

Cấu trúc source:

```text
project/
├── manifest.mf
├── base-src/com/acme/version/
│   ├── Main.java
│   └── VersionChoice.java
├── v17-src/com/acme/version/VersionChoice.java
└── v21-src/com/acme/version/VersionChoice.java
```

**Manifest — `manifest.mf`:**

```text
Manifest-Version: 1.0
Multi-Release: true

```

**Baseline — `base-src/com/acme/version/VersionChoice.java`:**

```java
package com.acme.version;

public final class VersionChoice {
    private VersionChoice() {
    }

    public static String selected() {
        return "base implementation";
    }
}
```

**Entry point — `base-src/com/acme/version/Main.java`:**

```java
package com.acme.version;

public class Main {
    public static void main(String[] args) {
        System.out.println(VersionChoice.selected());
    }
}
```

**Bản Java 17 — `v17-src/com/acme/version/VersionChoice.java`:**

```java
package com.acme.version;

public final class VersionChoice {
    private VersionChoice() {
    }

    public static String selected() {
        String label = " Java 17+ implementation ";
        return label.strip();
    }
}
```

`String.strip()` có từ Java 11, nên source này được biên dịch với `--release 17` và chỉ được runtime 17 trở lên chọn.

**Bản Java 21 — `v21-src/com/acme/version/VersionChoice.java`:**

```java
package com.acme.version;

public final class VersionChoice {
    private VersionChoice() {
    }

    public static String selected() {
        return "Java 21+ implementation";
    }
}
```

### Biên dịch và đóng gói

Chạy các lệnh từ thư mục `project/` bằng JDK 17 trở lên:

```shell
javac --release 9  -d base-classes base-src/com/acme/version/*.java
javac --release 17 -d v17-classes v17-src/com/acme/version/VersionChoice.java
javac --release 21 -d v21-classes v21-src/com/acme/version/VersionChoice.java

jar --create --file version-choice.jar --manifest manifest.mf -C base-classes .
jar --update --file version-choice.jar --release 17 -C v17-classes .
jar --update --file version-choice.jar --release 21 -C v21-classes .
```

`--release 17` và `--release 21` trong lệnh `jar --update` đặt các file theo sau vào `META-INF/versions/17` và `META-INF/versions/21`. Đây là tùy chọn của JAR tool, khác với `javac --release` dùng để biên dịch source.

### Kiểm tra nội dung archive

```shell
jar --list --file version-choice.jar
jar --validate --file version-choice.jar
```

Trong danh sách archive cần thấy baseline ở `com/acme/version/VersionChoice.class` và các bản thay thế ở `META-INF/versions/17/...` cùng `META-INF/versions/21/...`. `jar --validate` xác nhận tính nhất quán của API giữa các release.

## 7. Chạy cùng một JAR trên runtime khác nhau

Chạy ứng dụng trên JDK 24:

```shell
java -cp version-choice.jar com.acme.version.Main
```

Stdout trên JDK 24.0.2:

```text
Java 21+ implementation
```

JDK 24 chọn bản 21 vì đây là thư mục version cao nhất không vượt quá feature version 24.

Để kiểm tra lựa chọn như runtime 17 trên một JDK mới, có thể dùng thuộc tính kiểm thử `jdk.util.jar.version`:

```shell
java -Djdk.util.jar.version=17 -cp version-choice.jar com.acme.version.Main
```

Stdout trên JDK 24.0.2 với version override 17:

```text
Java 17+ implementation
```

Đây là cách kiểm tra lựa chọn entry trên một JDK mới. Trước khi phát hành, vẫn nên chạy test trên các JDK thực tế mà thư viện cam kết hỗ trợ, vì version override không thay thế việc kiểm tra toàn bộ runtime, verifier và API availability của từng JDK.

## 8. Kiểm tra entry được chọn bằng `JarFile`

Cần phân biệt class loader của ứng dụng với API đọc JAR trực tiếp. Các constructor cũ của `JarFile`, ví dụ `new JarFile(file)`, sử dụng base version để giữ hành vi đọc archive truyền thống. Vì vậy, gọi `getJarEntry()` trên đối tượng này không mặc nhiên trả bản theo runtime hiện tại.

Nếu cần đọc view theo runtime, truyền `JarFile.runtimeVersion()` vào constructor có tham số `Runtime.Version`:

```java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class InspectMultiReleaseJar {
    public static void main(String[] args) throws Exception {
        File file = new File(args[0]);

        try (JarFile jar = new JarFile(
                file, true, JarFile.OPEN_READ, JarFile.runtimeVersion())) {
            JarEntry entry = jar.getJarEntry(
                    "com/acme/version/VersionChoice.class");

            System.out.println("runtime version: " + jar.getVersion());
            System.out.println("selected entry: " + entry.getRealName());
        }
    }
}
```

Trên JDK 24.0.2 với JAR ví dụ, output:

```text
runtime version: 24
selected entry: META-INF/versions/21/com/acme/version/VersionChoice.class
```

Muốn xem một release cụ thể, truyền `Runtime.Version.parse("17")` thay cho `JarFile.runtimeVersion()`. Muốn đọc baseline, truyền `JarFile.baseVersion()`. `JarEntry.getRealName()` cho biết đường dẫn entry thực tế đã được chọn.

Không nhầm `JarFile` với `ZipFile`: `JarFile` có API hiểu multi-release và có thể trả view theo version; `ZipFile` là API đọc ZIP thô, không tự áp dụng quy tắc chọn entry logic của MR-JAR.

## 9. Phân tích đúng phiên bản bằng `jdeps`

`jdeps` có tùy chọn `--multi-release N` để phân tích class variant tương ứng với release mục tiêu. Điều này quan trọng khi bản 17 và bản 21 có dependency khác nhau.

```shell
jdeps --multi-release 17 -verbose:class version-choice.jar
jdeps --multi-release 21 -verbose:class version-choice.jar
```

`--multi-release 17` yêu cầu `jdeps` phân tích view của release 17; `--multi-release 21` phân tích view của release 21. Đây là lựa chọn phiên bản cho phân tích tĩnh, không thay đổi runtime đang chạy.

Đừng phân tích MR-JAR bằng một release mặc định rồi kết luận rằng mọi phiên bản của class đều có cùng dependency. Hãy phân tích các release mà dự án thực sự hỗ trợ.

## 10. Quy tắc áp dụng cho classpath và module path

MR-JAR có thể được sử dụng khi JAR nằm trên classpath hoặc module path. Runtime áp dụng lựa chọn versioned entry trong archive khi nạp class/resource. Vị trí JAR vẫn quyết định cách module system nhìn nhận dependency; MR-JAR không tự biến một JAR không có module descriptor thành explicit named module.

Nếu cùng một class tồn tại trong nhiều JAR trên classpath, thứ tự classpath vẫn quyết định archive nào được tìm trước. Quy tắc chọn version chỉ được áp dụng bên trong JAR đã được chọn; MR-JAR không thay đổi thứ tự ưu tiên giữa các JAR.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Runtime luôn dùng baseline. | Manifest thiếu `Multi-Release: true`, sai vị trí manifest hoặc sai tên thư mục version. | Kiểm tra manifest và `jar --list --file`. |
| JDK 24 không chọn bản 21. | Entry không nằm dưới `META-INF/versions/21/`, hoặc JAR không được đánh dấu multi-release. | Kiểm tra đúng đường dẫn archive và manifest. |
| JDK 17 cố dùng class Java 21. | Cấu trúc version bị đặt sai hoặc đang đọc entry thô thay vì view MR-aware. | Kiểm tra class loader/JarFile API và version directory. |
| Runtime mới hơn vẫn dùng bản 17. | Không có thư mục version cao hơn phù hợp, hoặc bản mới chưa được đóng gói vào JAR. | Kiểm tra `jar --list` và tạo lại artifact. |
| `NoSuchMethodError` hoặc `LinkageError` trên một runtime. | Bản versioned có API/bytecode không tương thích với consumer hoặc dependency của runtime đó. | Giữ API ổn định, biên dịch đúng `--release` và test trên runtime mục tiêu. |
| `jar --validate` báo API không nhất quán. | Versioned class làm thay đổi public API hoặc thêm public class không có ở baseline. | Đồng bộ hợp đồng API giữa các release rồi validate lại. |
| `JarFile` đọc bản gốc trong khi class loader dùng bản mới. | Đang dùng constructor cũ của `JarFile`, vốn mở base version. | Dùng constructor có `JarFile.runtimeVersion()` khi cần view runtime. |
| `jdeps` báo dependency khác với ứng dụng đang chạy. | Phân tích sai release hoặc chỉ phân tích một variant. | Dùng `jdeps --multi-release N` cho từng release mục tiêu. |

Runtime chọn bản versioned phù hợp trước khi định nghĩa class. Nếu bản được chọn bị lỗi xác minh, thiếu dependency hoặc không tương thích, JVM không tự động thử lại bản thấp hơn hay baseline. Phải sửa artifact và kiểm thử lại.

## 12. Quy trình phát hành MR-JAR

1. Xác định baseline Java thấp nhất cần hỗ trợ.
2. Biên dịch source baseline bằng `javac --release <baseline>`.
3. Chỉ tạo versioned implementation cho các release thực sự cần tối ưu hoặc dùng API mới.
4. Biên dịch từng variant bằng `javac --release <N>` tương ứng.
5. Tạo manifest có `Multi-Release: true` và đóng gói các variant dưới `META-INF/versions/<N>/`.
6. Chạy `jar --list` để kiểm tra cấu trúc và `jar --validate` để kiểm tra API nhất quán.
7. Chạy ứng dụng trên từng JDK được hỗ trợ; có thể dùng `jdk.util.jar.version` để kiểm tra nhanh selection khi phát triển.
8. Chạy `jdeps --multi-release N` trên từng release cần hỗ trợ và xử lý dependency khác nhau.
9. Kiểm tra checksum, nội dung artifact cuối và chạy integration test trước khi phát hành.

## 13. Checklist

- Manifest có `Multi-Release: true` trong main section.
- Baseline nằm ở đường dẫn class/resource thông thường trong JAR.
- Mỗi bản thay thế nằm đúng dưới `META-INF/versions/<N>/` với `N` là feature version từ 9 trở lên.
- Runtime chọn bản version cao nhất không vượt quá feature version hiện tại; nếu không có thì dùng baseline.
- Source baseline chỉ sử dụng API có trong baseline release.
- Mỗi variant được biên dịch bằng `javac --release` phù hợp.
- Public API giữa các release nhất quán và `jar --validate` thành công.
- Test trên các runtime mục tiêu và phân tích từng variant bằng `jdeps --multi-release N`.
- Khi đọc trực tiếp bằng `JarFile`, chọn rõ `runtimeVersion()`, version cụ thể hoặc `baseVersion()`.

## Tài liệu tham khảo

- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238)
- [Java API — `JarFile` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/JarFile.html)
- [Java API — `Runtime.Version` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Runtime.Version.html)
- [The `jar` Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [The `jdeps` Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
