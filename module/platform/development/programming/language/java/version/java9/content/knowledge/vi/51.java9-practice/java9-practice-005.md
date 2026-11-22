# Đóng gói JAR đa phiên bản và kiểm thử trên các JDK đích — Java 9+

## 1. Bài toán: một thư viện, nhiều phiên bản JDK

Một thư viện Java có thể phải phục vụ các ứng dụng triển khai trên những bản JDK khác nhau. Nếu chỉ biên dịch mọi class theo phiên bản Java mới nhất, ứng dụng chạy bằng JDK cũ có thể gặp `UnsupportedClassVersionError`, hoặc `NoSuchMethodError` khi code tham chiếu API chưa có ở runtime đích. Nếu chỉ sử dụng tập API cũ nhất, nhà phát triển không tận dụng được API mới hơn để cải thiện triển khai bên trong thư viện.

**Multi-Release JAR (MRJAR)**, được chuẩn hóa từ **Java 9 qua JEP 238**, giải quyết một trường hợp cụ thể: một tệp JAR chứa **triển khai cơ sở** và các **biến thể của class cho từng phiên bản Java**, trong khi chương trình vẫn sử dụng cùng một tên class/API. Class loader của runtime Java 9+ chọn class phù hợp nhất theo số phiên bản JDK hiện tại.

Ví dụ bài thực hành này dùng các mức còn phổ biến trong những môi trường Java hiện đại: **Java 11 làm baseline**, phiên bản thay thế **Java 17**, và phiên bản thay thế **Java 21**. Một tệp `app.jar` sẽ chạy cùng tên `demo.Greeting` nhưng dùng mã được biên dịch tương ứng với release được chọn. Java 9 là mốc **ra đời cơ chế MRJAR**, chứ không phải bắt buộc mọi dự án ngày nay phải giữ compatibility với Java 9 hoặc Java 8.

Khi áp dụng vào dự án, hãy quyết định phạm vi JDK thực sự phải hỗ trợ trước. Một MRJAR **không phải công cụ nâng cấp tự động**: vẫn cần biên dịch riêng từng biến thể, bảo toàn public API và thử chạy trên từng runtime đích.

## 2. Cấu trúc và quy tắc lựa chọn class

Một MRJAR hợp lệ chứa thuộc tính main manifest:

```text
Multi-Release: true
```

và những class phiên bản đặc biệt nằm dưới `META-INF/versions/N/`, trong đó **N là số phiên bản release nguyên từ 9 trở lên**:

```text
app.jar
├── META-INF/
│   ├── MANIFEST.MF                (Multi-Release: true)
│   └── versions/
│       ├── 17/
│       │   └── demo/Greeting.class  (biến thể dùng được từ Java 17)
│       └── 21/
│           └── demo/Greeting.class  (biến thể dùng được từ Java 21)
└── demo/
    ├── Greeting.class              (baseline Java 11)
    └── Main.class                  (entry point Java 11)
```

Quy tắc tìm class `demo.Greeting` trên **runtime Java 9+**: xét các version directory **không vượt quá phiên bản của runtime**, theo thứ tự giảm dần; nếu không có, dùng entry ở root của JAR.

| Runtime được dùng | Entry được chọn trong ví dụ | Vì sao? |
| --- | --- | --- |
| Java 11 | `demo/Greeting.class` ở root | Chưa đủ Java 17; bản cơ sở biên dịch cho Java 11. |
| Java 17 | `META-INF/versions/17/demo/Greeting.class` | Bản 17 có mặt và tương thích. |
| Java 21 | `META-INF/versions/21/demo/Greeting.class` | Chọn biến thể 21. |
| Java 22–24 | `META-INF/versions/21/demo/Greeting.class` | Không có biến thể cao hơn 21 trong JAR nên dùng bản lớn nhất phù hợp. |

Với một runtime Java 19, class loader cũng chọn bản 17; **không** chọn bản 21 chỉ vì nó nằm trong tệp JAR. Với Java 11, class loader chọn root. Nếu JAR không có `Multi-Release: true`, các entry trong `META-INF/versions/*` sẽ **không** được xử lý như biến thể khi chọn class theo quy tắc MRJAR.

**Điều kiện quan trọng:** runtime không thể giải mã class bytecode của release cao hơn phiên bản mà nó hiểu. Đặt một class được biên dịch bằng `--release 21` vào `META-INF/versions/17/` là sai: class loader trên Java 17 có thể chọn nó rồi thất bại. Vì vậy phải **đồng bộ release khi biên dịch và thư mục phiên bản khi đóng gói**.

## 3. Phạm vi áp dụng và những điều MRJAR không làm

MRJAR phù hợp cho **thư viện** và thành phần framework cần duy trì một API công khai xuyên nhiều release, nhưng muốn triển khai nội bộ khác nhau. Ví dụ:

- Dùng API `java.util.HexFormat` (Java 17) trong triển khai 17, giữ triển khai dự phòng cho baseline.
- Dùng các API collection xuất hiện ở Java 21 trong một phần triển khai mới, trong khi caller vẫn gọi một public method có signature giống bản cơ sở.
- Tối ưu thao tác I/O, dữ liệu, logging hoặc platform integration theo khả năng runtime.

MRJAR **không** bảo đảm:

1. Những dependency khác của ứng dụng tự trở nên tương thích với JDK đích.
2. Biến thể của class đã dùng đúng API trong release mà nó khai báo.
3. Public API xuyên các bản biến thể tự nhất quán.
4. Kiểm thử trên JDK build mới nhất tương đương với thử trên JDK cũ thực.
5. Mọi công cụ đọc JAR, bytecode transformer hoặc scanner bên ngoài đều hiểu MRJAR theo cùng cách.
6. Một JAR có thể sử dụng tất cả API mới khi chạy trên runtime cũ: **code trong baseline phải chỉ dùng API tồn tại ở baseline**.

**Không phải dự án nào cũng nên làm MRJAR.** Nếu toàn bộ người dùng có thể nâng lên Java 21, một thư viện chỉ nhắm Java 21 sẽ đơn giản hơn. MRJAR đáng giá khi cần hỗ trợ đồng thời nhiều runtime và khác biệt implementation thực sự mang lại lợi ích rõ.

## 4. Chuẩn bị bài thực hành độc lập

Ta tạo ba phiên bản của **cùng một class `demo.Greeting`**, cùng chữ ký public:

```java
public static String text()
```

Bản base chạy từ Java 11; bản 17 dùng API `HexFormat` có từ Java 17; bản 21 dùng `List.reversed()` và `getFirst()` theo collection API Java 21. `demo.Main` chỉ nằm ở root và gọi `Greeting.text()`.

Cấu trúc thư mục trước khi biên dịch:

```text
mrjar-demo/
├── src/
│   ├── base/
│   │   └── demo/
│   │       ├── Greeting.java
│   │       └── Main.java
│   ├── v17/
│   │   └── demo/
│   │       └── Greeting.java
│   └── v21/
│       └── demo/
│           └── Greeting.java
└── build/                     (được tạo trước khi biên dịch)
    ├── base/
    ├── v17/
    └── v21/
```

Cần một **JDK có thể biên dịch các target 11, 17 và 21**. Ví dụ này đã được kiểm thử với OpenJDK 24 và `javac --release 11/17/21`. Có thể biên dịch bằng JDK 21+ khi các mức `--release` tương ứng vẫn được compiler cung cấp; không giả định một `javac` cũ có thể hiểu target 21.

**Tạo các thư mục** bằng công cụ file manager hoặc các lệnh phù hợp hệ điều hành. Ví dụ trong Bash:

```bash
mkdir -p src/base/demo src/v17/demo src/v21/demo
mkdir -p build/base build/v17 build/v21
```

Trên PowerShell có thể tạo folder bằng `New-Item -ItemType Directory -Force -Path ...` hoặc tạo thủ công. Sau đó lưu đúng năm file Java dưới đây. Tên package `demo` phải khớp đường dẫn `demo/`.

## 5. File nguồn: phiên bản cơ sở Java 11

File **`src/base/demo/Greeting.java`**:

```java
package demo;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "base: Java 11+";
    }
}
```

Đây là bản duy nhất mà runtime Java 11 dùng. Không import API chỉ có từ Java 17 hoặc Java 21 vào mã nguồn base.

File **`src/base/demo/Main.java`**:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

`Main` không biết bản `Greeting` nào sẽ được class loader chọn. **Đó là điểm mạnh của MRJAR**: caller chỉ phụ thuộc vào API chung, không cần viết `if (javaVersion >= 21)` để tự chọn class ở từng thư mục.

Bản base cần tuân thủ hợp đồng API xuyên release. Nếu `Main` gọi một method không có trong bản Java 11, chương trình có thể thất bại trên Java 11 dù đã đóng gói đầy đủ các bản cao hơn.

## 6. File nguồn: biến thể Java 17

File **`src/v17/demo/Greeting.java`**:

```java
package demo;

import java.util.HexFormat;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "version 17: " +
                HexFormat.of().formatHex(new byte[]{42});
    }
}
```

`HexFormat` có từ Java 17, nên **không được** đặt bytecode của class này ở root nếu muốn chạy trên Java 11. Ở release 17 trở lên, chương trình in ký tự hex của byte `42` (thập phân), tức `2a`.

Ở đây chỉ **implementation** khác bản base: class vẫn là `public final class demo.Greeting`, constructor private, method `public static String text()`. Đó là chiến lược an toàn hơn việc đổi chữ ký method/kiểu trả về giữa các phiên bản.

## 7. File nguồn: biến thể Java 21

File **`src/v21/demo/Greeting.java`**:

```java
package demo;

import java.util.List;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "version 21: " +
                List.of("A", "B").reversed().getFirst();
    }
}
```

Trong Java 21, `List` có các thao tác của sequenced collections: `reversed()` trả view theo chiều ngược, `getFirst()` trả phần tử đầu tiên. Với danh sách `["A", "B"]`, kết quả là `B`. Method công khai của `Greeting` **vẫn y hệt** hai bản kia.

Đây không phải trick “thêm class mới cho Java 21” mà là **thay thế cùng một class** ở thời điểm load. Class `demo.Greeting` mà caller nhìn thấy trong một JVM chỉ có một bản được chọn bởi class loader ấy. Nếu chương trình tạo các custom classloader riêng biệt, việc chọn có thể theo cấu hình và phạm vi của từng classloader; đừng trộn hai bản class cùng tên trong cùng một loader rồi kỳ vọng chúng đồng tồn tại.

## 8. Biên dịch từng bộ nguồn với `javac --release`

Từ thư mục `mrjar-demo`, chạy lần lượt:

```bash
javac --release 11 -d build/base src/base/demo/Greeting.java src/base/demo/Main.java
javac --release 17 -cp build/base -d build/v17 src/v17/demo/Greeting.java
javac --release 21 -cp build/base -d build/v21 src/v21/demo/Greeting.java
```

Giải thích:

- `--release 11` yêu cầu mã nguồn và thư viện Java chuẩn dùng cho release 11; bytecode root có thể được runtime Java 11 đọc.
- `--release 17` cho phép sử dụng `HexFormat` nhưng không cho dùng API chỉ xuất hiện từ Java 21.
- `--release 21` cho phép `List.reversed()`/`getFirst()` từ Java 21.
- `-d build/...` đặt output riêng để không ghi đè file `Greeting.class` của bản khác.
- `-cp build/base` đưa API chung đã biên dịch vào compile classpath cho các biến thể; trong ví dụ, class `Greeting` không cần truy cập helper, nhưng đây là cách hữu ích khi biến thể tham chiếu các class chung của dự án. Phải kiểm soát classpath để tránh compiler vô tình đọc một phiên bản dependency không tương thích.
- `--release` khác `-source`/`-target`: nó còn giới hạn các API chuẩn có thể tham chiếu trong source. Chỉ chỉnh bytecode target mà vẫn compile với API mới có thể dẫn tới lỗi tại runtime cũ.

Sau lệnh trên:

```text
build/base/demo/Greeting.class      (target Java 11)
build/base/demo/Main.class
build/v17/demo/Greeting.class       (target Java 17)
build/v21/demo/Greeting.class       (target Java 21)
```

Các số class-file major tương ứng thông thường là **55** (Java 11), **61** (Java 17), **65** (Java 21). Có thể kiểm tra bằng `javap -verbose ...` hoặc qua công cụ phân tích bytecode đáng tin. Với một bản patch release, cấp bytecode phù hợp vẫn không thay thế kiểm thử API runtime.

**Không compile ba class `Greeting.java` vào một output directory**: file sau sẽ ghi đè file trước, khiến JAR không còn base và phiên bản đúng.

## 9. Tạo JAR đa phiên bản bằng công cụ `jar` của JDK

Một lệnh `jar` từ JDK hiện đại có thể đặt class root và các class biến thể vào đúng vị trí ngay khi tạo:

```bash
jar --create --file app.jar --main-class demo.Main -C build/base . --release 17 -C build/v17 . --release 21 -C build/v21 .
```

Phân tích chính xác:

| Đoạn lệnh | Tác dụng |
| --- | --- |
| `jar --create --file app.jar` | Tạo file lưu trữ JAR mới. |
| `--main-class demo.Main` | Ghi `Main-Class: demo.Main` vào manifest, để chạy bằng `java -jar app.jar`. |
| `-C build/base .` | Đóng gói **mọi nội dung của build/base vào root**. |
| `--release 17 -C build/v17 .` | Đưa class tiếp theo vào `META-INF/versions/17/`. |
| `--release 21 -C build/v21 .` | Đưa class tiếp theo vào `META-INF/versions/21/`. |

Khi tạo MRJAR bằng các vùng `--release`, công cụ `jar` chuẩn thêm thông tin multi-release vào manifest. **Manifest phải có `Multi-Release: true` trong phần main attributes** để Java runtime xem các version entries là class thay thế. Nếu bạn sử dụng công cụ build/JAR khác, phải cấu hình hoặc xác minh thuộc tính ấy, không chỉ chép các file vào `META-INF/versions`.

Kiểm tra JAR:

```bash
jar --list --file app.jar
jar --validate --file app.jar
```

`jar --list` trong bài này cho thấy các entry chính:

```text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/Greeting.class
demo/Main.class
META-INF/versions/17/
META-INF/versions/17/demo/
META-INF/versions/17/demo/Greeting.class
META-INF/versions/21/
META-INF/versions/21/demo/
META-INF/versions/21/demo/Greeting.class
```

Với artifact đúng như ví dụ, `jar --validate --file app.jar` **thành công, exit code 0 và không in lỗi** trên OpenJDK 24. Bộ kiểm tra này phát hiện các vấn đề cấu trúc và nhất quán API công khai giữa biến thể theo khả năng của công cụ. Không xem một lần validate thành công là bằng chứng chắc chắn tương thích runtime hoặc đúng hành vi nghiệp vụ.

**Đừng dùng `jar --extract` trên artifact nguồn cần giữ nguyên để “xem class đang được chọn”**: extract chỉ giải nén entry vật lý. Việc class loader chọn biến thể xảy ra khi runtime nạp class từ tệp JAR có manifest đúng.

## 10. Thực thi và quan sát lựa chọn class

Trên **OpenJDK 24** đã kiểm thử:

```bash
java -jar app.jar
```

Stdout:

```text
version 21: B
```

Vì runtime là Java 24, nó chọn versioned class **21**, không phải versioned class **17** hoặc root **11**. Trường hợp này cũng minh họa **fallback xuống N lớn nhất không vượt runtime** khi JAR không có bản 24.

Với cùng OpenJDK 24, có thể sử dụng các **thuộc tính runtime phục vụ chẩn đoán** để quan sát resolver theo một mức tối đa thấp hơn:

```bash
java -Djdk.util.jar.version=17 -jar app.jar
java -Djdk.util.jar.version=11 -jar app.jar
java -Djdk.util.jar.enableMultiRelease=false -jar app.jar
```

Kết quả **theo đúng thứ tự ba lệnh** khi kiểm thử trên OpenJDK 24:

```text
version 17: 2a
base: Java 11+
base: Java 11+
```

Giải thích:

- `jdk.util.jar.version=17` giới hạn effective version tối đa mà xử lý MRJAR của JDK này xét đến. Class bản 17 được chọn.
- `jdk.util.jar.version=11` khiến runtime JDK 24 giả lập việc giải quyết entry theo mức 11; trong JAR ví dụ không có biến thể 11 nên chọn base.
- `jdk.util.jar.enableMultiRelease=false` tắt xử lý multi-release cho quá trình kiểm thử trên runtime JDK hỗ trợ property này.

**Cảnh báo cực quan trọng:** các `-Djdk.util.jar.*` ở đây là **tùy chọn chẩn đoán của JDK đang chạy**, **không** biến OpenJDK 24 thành Java 11/17 thực, **không** hạ cấp runtime API, class verifier, TLS provider, GC hay môi trường module của một JDK đích cũ. Vì thế chạy được với `-Djdk.util.jar.version=11` **không chứng minh** ứng dụng chạy được trên một tiến trình Java 11 thật. Để chốt tương thích, phải chạy JAR trên **từng JDK thật** trong danh sách hỗ trợ.

Ngoài ra, `-D...` trong một số shell cần được truyền như một đối số nguyên vẹn. Với **Windows PowerShell**, nếu parser của shell tách sai dấu chấm hoặc dấu bằng, đặt toàn bộ option trong dấu nháy đơn, ví dụ `java '-Djdk.util.jar.version=17' -jar app.jar`.

## 11. Kiểm thử bắt buộc trên các JDK đích thật

Dùng CI matrix hoặc các JDK được cài độc lập. Với ví dụ, mục tiêu hỗ trợ gồm **11, 17, 21**, và thêm runtime mới nhất mà sản phẩm dùng (ví dụ 24/25 tùy chính sách) để phát hiện thay đổi hành vi tương lai.

| JDK **thực sự khởi động tiến trình** | Lệnh | Kết quả mong đợi |
| --- | --- | --- |
| Java 11 | `java -jar app.jar` bằng `java` của JDK 11 | `base: Java 11+` |
| Java 17 | `java -jar app.jar` bằng `java` của JDK 17 | `version 17: 2a` |
| Java 21 | `java -jar app.jar` bằng `java` của JDK 21 | `version 21: B` |
| Java 24 | `java -jar app.jar` bằng `java` của JDK 24 | `version 21: B` |

Ở dòng Java 11/17/21, **kết quả là kỳ vọng từ quy tắc MRJAR và code đã biên dịch**, chưa phải log kiểm chứng trên máy này nếu ba JDK đó không được cài. Dòng Java 24 đã được kiểm tra thực tế.

Mẫu lệnh cho **Bash** nếu đã cài các JDK và gán đúng biến môi trường `JDK11_HOME`, `JDK17_HOME`, `JDK21_HOME`:

```bash
"$JDK11_HOME/bin/java" -version
"$JDK11_HOME/bin/java" -jar app.jar

"$JDK17_HOME/bin/java" -version
"$JDK17_HOME/bin/java" -jar app.jar

"$JDK21_HOME/bin/java" -version
"$JDK21_HOME/bin/java" -jar app.jar
```

Trong **PowerShell**, một ví dụ tương đương khi các biến môi trường đã có giá trị:

```powershell
& "$env:JDK11_HOME\bin\java.exe" -version
& "$env:JDK11_HOME\bin\java.exe" -jar app.jar

& "$env:JDK17_HOME\bin\java.exe" -version
& "$env:JDK17_HOME\bin\java.exe" -jar app.jar

& "$env:JDK21_HOME\bin\java.exe" -version
& "$env:JDK21_HOME\bin\java.exe" -jar app.jar
```

Quan trọng là xác minh `java -version`/`java --version` (tùy bản JDK) của **đúng executable** trước khi chạy, thay vì tin giá trị `JAVA_HOME` hoặc cái `java` đứng đầu `PATH`. Với CI container, có thể dùng các runtime image được pin theo version/vendor và chạy lại artifact **được build một lần**.

Nhóm kiểm thử nên gồm:

1. **Smoke test:** `java -jar app.jar` và assert stdout/exit status tương ứng release.
2. **Unit/contract tests:** API public của các biến thể phải cùng chức năng theo tài liệu, không chỉ khác text minh họa.
3. **Dependency tests:** thử classpath/module path và các dependency phiên bản tương ứng trên từng JDK.
4. **Integration tests:** dùng ứng dụng thật tiêu thụ JAR, kể cả custom class loader, ServiceLoader hoặc framework packaging nếu có.
5. **Negative tests:** artifact giả thiếu manifest hoặc chứa class cao hơn thư mục N phải bị phát hiện trước phát hành.
6. **Matrix maintenance:** thử các bản JDK LTS đang được tổ chức hỗ trợ và bản JDK sắp nâng cấp; ghi rõ khi bỏ một bản cũ khỏi danh sách.

## 12. Vì sao `javac --release` chưa đủ để chứng minh tương thích?

`--release N` kiểm soát **ngôn ngữ, bytecode target và các API Java chuẩn khả dụng ở thời điểm compile**. Nó **không** chạy mã trên JVM N, không kiểm chứng compatibility của thư viện bên ngoài với N, không kiểm tra đầy đủ cấu hình TLS, hệ điều hành hay việc một API được gọi qua reflection chỉ khi đến runtime.

Ví dụ sai:

```text
javac --release 21 -d build/base ...
             ↑
root JAR được chạy trên Java 11
             ↓
Java 11 gặp class major 65 không đọc được → UnsupportedClassVersionError
```

Ví dụ khác: class root compile với `--release 11` nhưng dùng dependency bên thứ ba có bytecode Java 21, hoặc reflection gọi `List.reversed` ở Java 11. Compiler có thể không phát hiện mọi trường hợp đó, nhất là khi dependency được nạp động; runtime test mới bắt được.

Ngoài ra, một biến thể Java 17 có thể chạy bình thường trên Java 24 nhưng lỗi trên Java 17 nếu vô tình dùng tính năng API Java 21 qua reflection hoặc dependency. Do đó luôn kiểm thử **release thấp nhất của từng biến thể**.

Chính sách kiểm chứng nên phân hai lớp:

- **Static/build checks:** `javac --release N`, `jar --validate`, `jdeps --multi-release N`, kiểm tra version bytecode và consistency API.
- **Runtime/integration checks:** khởi động JVM thực của từng đích, thực thi method đặc trưng của bản đó, chạy contract tests và kiểm tra dependency.

Không thay thế lớp thứ hai bằng property `jdk.util.jar.version`; property ấy chỉ giúp quan sát việc lựa chọn entry của JDK hiện hành.

## 13. Kiểm tra với `jdeps`, `javap` và manifest

### 13.1. Phân tích phụ thuộc theo từng release

`jdeps` có tùy chọn **`--multi-release version`**, với `version` là `base` hoặc số nguyên từ 9 trở lên, để phân tích các class của MRJAR theo góc nhìn release được chọn.

Ví dụ đã chạy trên OpenJDK 24:

```bash
jdeps --multi-release base --summary app.jar
jdeps --multi-release 21 --summary app.jar
```

Với artifact nhỏ trong bài, cả hai lệnh trả:

```text
app.jar -> java.base
```

Vì `HexFormat` và `List` đều thuộc module `java.base`, bản tóm tắt module **giống nhau** dù implementation đã thay đổi. Đừng coi `jdeps --summary` đủ để xác minh mọi API mới: muốn phân tích chi tiết, dùng `--verbose:class` hoặc giải mã bytecode và đối chiếu release.

Khi chạy `jdeps` với các JAR phụ thuộc dự án thật, thêm classpath/module path cần thiết để công cụ tìm được dependency, tránh hiểu nhầm `not found` là một API JDK bị mất.

### 13.2. Kiểm tra class-file major version

Có thể xem header class đã biên dịch:

```bash
javap -verbose build/base/demo/Greeting.class
javap -verbose build/v17/demo/Greeting.class
javap -verbose build/v21/demo/Greeting.class
```

Tìm dòng `major version`; lần lượt phải là **55**, **61**, **65** trong bài này. Một JAR MRJAR đúng không thể chỉ đổi tên thư mục `META-INF/versions/17` để biến bytecode Java 21 thành Java 17.

### 13.3. Kiểm tra manifest

Trong JAR phải có:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Multi-Release: true
```

Trên một JAR không phải ứng dụng executable, `Main-Class` không bắt buộc. **`Multi-Release: true` mới là tín hiệu nhận diện MRJAR**, được ghi ở phần main section của `META-INF/MANIFEST.MF`. Một file `MANIFEST.MF` thủ công cần định dạng manifest hợp lệ (các header và dòng trống đúng quy tắc); cách ít lỗi là dùng `jar --release` hoặc build plugin có hỗ trợ MRJAR rồi **kiểm tra artifact cuối cùng**.

Nếu công cụ đóng gói khác thêm manifest thủ công nhưng quên `Multi-Release`, Java runtime sẽ đọc bản base dù các entry `versions/*` vẫn tồn tại vật lý. Đó là lý do `jar --list` và `java -jar` là **hai phép kiểm tra khác nhau**.

## 14. Hợp đồng API xuyên release và giới hạn đặc tả

JAR File Specification yêu cầu public/protected API của những class có versioned variant **phải nhất quán** giữa các release tương ứng. Nên giữ cùng:

- Tên class đầy đủ và các modifier có ý nghĩa API.
- Constructor public/protected được phơi ra bên ngoài.
- Tên, tham số, return type và visibility của public/protected methods.
- Các public/protected fields và kiểu dữ liệu của chúng.
- Các interface và kiểu public mà caller cần dùng; hành vi phải đáp ứng cùng contract nghiệp vụ.

**Ví dụ không nên làm:** class `demo.Greeting` ở base có `public static String text()`, còn version 21 chỉ có `public static List<String> text()`. Code đã compile với base sẽ không tìm được method có descriptor cũ trong bản 21 và có thể gặp `NoSuchMethodError`.

Trong ví dụ, cả ba bản giữ nguyên `public static String text()`, nên caller có thể compile với **base** và chạy trên runtime có chọn phiên bản cao hơn mà không đổi lời gọi. Giá trị text khác chỉ để chứng minh lựa chọn class. Trong một thư viện thực, **ý nghĩa nghiệp vụ của method nên ổn định**, không đổi semantics chỉ để tận dụng API mới.

`jar --validate` kiểm tra một phần tính hợp lệ cấu trúc và consistency API, nhưng **không thay thế** suite kiểm thử binary compatibility, reflection behavior, serialization hoặc kiểm thử method contract. Nếu thư viện được publish cho người dùng bên ngoài, hãy đưa cả kiểm tra binary/API compatibility vào CI.

Một lưu ý với **package**: đặt versioned class đúng cấu trúc package, không tự phát minh thêm public class chỉ xuất hiện trên phiên bản cao mà API public base không có. Cách tiếp cận ổn định thường là chỉ thay **implementation** của class đã tồn tại.

Với **resources**: MRJAR có thể chứa một số resource theo version, nhưng các entry đặc biệt bên trong `META-INF` (ví dụ cấu hình dịch vụ) có quy tắc riêng; **không** đặt `META-INF/services/...` trong `META-INF/versions/N/META-INF/services/...` rồi mặc định cơ chế `ServiceLoader` sẽ nhận như muốn. Cấu hình dịch vụ và module metadata cần được kiểm tra theo JAR specification.

## 15. Modular JAR, classpath, module path và các công cụ đóng gói

MRJAR và **modular JAR** là hai khái niệm có thể kết hợp nhưng không đồng nhất:

- MRJAR: chọn các class/resources phù hợp với **runtime version**.
- Modular JAR: khai báo module qua `module-info.class` và tuân theo cách truy cập module của Java Platform Module System.
- Một MRJAR **không có** module descriptor khi đặt trên module path có thể được xử lý như automatic module theo quy tắc JPMS.
- Một dự án cần bảo toàn baseline trước Java 9 nhưng vẫn dùng module descriptor trên các release mới có thể bố trí `module-info.class` trong versioned area thích hợp; đây là trường hợp nâng cao và cần kiểm tra đặc tả module/multi-release. Với ví dụ baseline Java 11, ta **không cần** cấu trúc phức tạp này.

Bài mẫu đóng gói trên **classpath bằng `java -jar`**, không dùng `module-info.java`. Nếu dự án chạy trên module path, thêm kiểm thử `java --module-path ... --module ...` phù hợp module name và main class được cấu hình; đừng mặc định bài test classpath bao phủ cả module readability/exports/opens.

Một thư viện Java thường được đóng bằng Maven hoặc Gradle. Ở đó cần:

1. **Source set riêng** cho base và từng biến thể; tránh compile cùng tên class vào một folder rồi ghi đè.
2. Compiler/toolchain có thể compile target tương ứng bằng `--release N`.
3. Bước packaging đặt output base ở root, output variant ở `META-INF/versions/N`.
4. Manifest có `Multi-Release: true`.
5. Plugin kiểm tra consistency hoặc `jar --validate` chạy trên **artifact cuối**.
6. CI matrix thực thi **chính artifact đã build** trên các JDK đích.

Maven Compiler Plugin phiên bản hiện hành có tài liệu về **multi-release output** và các executions riêng; Maven JAR Plugin hỗ trợ manifest entries và một số phiên bản có tự phát hiện multi-release layout. Cấu hình chi tiết nên khớp đúng phiên bản plugin mà dự án pin, không sao chép tùy chọn từ plugin đời khác. Với Gradle cũng tương tự: các task/toolchain biên dịch từng release, copy output đúng nơi và cấu hình manifest rõ ràng.

**Không phải cứ thêm `Multi-Release: true` là build plugin tự biên dịch các biến thể.** Manifest và bytecode theo release là hai trách nhiệm khác nhau.

## 16. Checklist CI đề xuất trước khi phát hành

| Giai đoạn | Bằng chứng cần thu |
| --- | --- |
| Chọn hỗ trợ | Danh sách JDK baseline và overlay rõ ràng; ví dụ 11/17/21. |
| Compile base | `javac --release 11` thành công, không tham chiếu API Java 17/21. |
| Compile 17/21 | `javac --release 17` và `--release 21` thành công bằng toolchain phù hợp. |
| Build | JAR chứa class root + versioned 17/21 đúng package path. |
| Manifest | Có `Multi-Release: true`; `Main-Class` đúng nếu executable. |
| Validate | `jar --validate --file app.jar` trả exit 0; xử lý warning/error theo chính sách. |
| Dependency | `jdeps --multi-release base/17/21` và kiểm tra classpath/modulepath cần thiết. |
| API contract | Public/protected signatures tương thích; kiểm thử binary/API compatibility. |
| JDK 11 thật | Chạy `java -jar app.jar` và unit tests, kỳ vọng base. |
| JDK 17 thật | Chạy artifact giống hệt trên JDK 17, kỳ vọng version 17. |
| JDK 21 thật | Chạy artifact giống hệt trên JDK 21, kỳ vọng version 21. |
| JDK mới hơn | Chạy trên runtime dự kiến triển khai, xác nhận fallback và integration. |
| Báo cáo | Lưu artifact hash, build JDK, kết quả matrix, version của plugin/dependency. |

Trong CI, nên **build một lần, kiểm thử cùng JAR đã tạo** trên nhiều JDK. Nếu chạy một build khác nhau trên mỗi JDK rồi so sánh output, bạn không còn kiểm tra chính xác tính portable của **một** artifact MRJAR.

Ngoài việc so sánh stdout, hãy kiểm tra **exit code**, các luồng stderr, output phụ, tests và những tình huống khó phát hiện bằng smoke test: reflection, serialization, service loading, checksum, resource lookup và các code path được kích hoạt ở runtime cao hơn.

## 17. Lỗi thường gặp và xử lý

| Triệu chứng | Cách giải thích / khắc phục |
| --- | --- |
| Trên JDK 21 vẫn luôn chạy code ở root | Thiếu `Multi-Release: true`; versioned path sai; không chạy file JAR cuối; hoặc thiết lập MRJAR bị tắt. |
| `UnsupportedClassVersionError` trên JDK thấp | Root hay versioned class chứa bytecode release cao hơn JDK/đường dẫn N; kiểm tra `javac --release`, major version và đóng gói. |
| `NoSuchMethodError` khi gọi class variant | Public API giữa bản base và overlay không tương thích; kiểm tra signature và binary contract. |
| `jar --validate` báo API không đồng nhất | Class có public/protected signature khác nhau; thiết kế lại API chung và build lại các variants. |
| Tạo JAR từ nhiều thư mục nhưng chỉ có một `Greeting.class` | Đã ghi đè các class vào cùng output dir trước khi đóng gói. |
| App trên JDK 11 lỗi dù `--release 11` thành công | Có dependency không tương thích, reflection, native library hay cấu hình runtime; chạy tests trên JDK 11 thật. |
| Chạy `java -Djdk.util.jar.version=11` trên JDK 24 OK rồi nghĩ đã test JDK 11 | Sai: mới kiểm tra lựa chọn entry, không kiểm thử runtime 11 thực. |
| `jdeps` trả cùng `java.base` với bản base và 21 | Các API đều ở module java.base; cần phân tích chi tiết hơn và test runtime. |
| Ứng dụng tìm service resources sai | Nhầm các rule `META-INF` hoặc trình load resource không xử lý MRJAR như class loader mong đợi. |
| Versioned class có tên package lệch root | Cơ chế override theo path không tìm đúng class; kiểm tra `jar --list` và class binary names. |
| Build Maven/Gradle chạy nhưng artifact không phải MRJAR | Kiểm tra output layout, manifest, toolchain, CI và cấu hình plugin. |
| Chương trình launch bằng IDE khác `java -jar` | IDE chạy thư mục `build/classes`, không chạy JAR; MRJAR resolution chỉ được áp dụng đúng khi load từ file JAR với manifest hợp lệ. |
| Test trên JDK mới thất bại khi thêm bản overlay | Có thể overlay dùng API vượt target, behavior khác contract, hoặc dependency; kiểm tra riêng Java versions N-1/N/N+1. |

## 18. Tự kiểm tra kiến thức

**Câu 1.** JAR có base 11, biến thể 17 và 21. Trên Java 19, class `demo.Greeting` nào được chọn? **Biến thể 17**: 21 cao hơn 19 nên không xét, 17 là version lớn nhất còn phù hợp.

**Câu 2.** Vì sao code ở thư mục `META-INF/versions/21` vẫn có thể gây lỗi trên Java 21? **Có thể** vì bytecode được biên dịch cho Java 24, API trong class không tồn tại ở 21, dependency thiếu hoặc API đã không giữ tương thích với base. Chỉ đặt đúng tên thư mục không đủ.

**Câu 3.** Có thể nói JAR đã hỗ trợ Java 11 sau khi chạy `java -Djdk.util.jar.version=11 -jar app.jar` bằng JDK 24 không? **Không**. Phải chạy chính tệp JAR đó bằng Java 11 thật.

**Câu 4.** Nếu project dùng Java 21 làm baseline và không cần hỗ trợ Java 11/17, MRJAR có còn cần thiết? **Không nhất thiết**: một JAR thông thường được biên dịch cho Java 21 đơn giản hơn và thường phù hợp.

**Câu 5.** `jar --validate` thành công có bảo đảm toàn bộ application contract tương thích giữa ba release không? **Không**. Nó hỗ trợ kiểm tra cấu trúc/nhất quán API theo khả năng của công cụ; cần binary compatibility test và integration tests trên runtime đích.

## Tài liệu chính thức và hướng dẫn còn áp dụng

- OpenJDK — [JEP 238: Multi-Release JAR Files](https://openjdk.org/jeps/238): lý do thiết kế, phạm vi chọn class và yêu cầu MRJAR từ Java 9.
- Oracle Java SE 25 — [JAR File Specification — Multi-release JAR files](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html): `Multi-Release: true`, `META-INF/versions/N`, API consistency, resources và module descriptors.
- Oracle Java SE 25 — [`jar` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): `--release`, `--main-class`, `--list` và `--validate`.
- Oracle Java SE 26 — [`jdeps` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): `--multi-release base|N` và phân tích dependencies.
- Oracle Java SE 25 — [`java.util.jar.JarFile`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarFile.html): cấu hình runtime version và hành vi của phiên bản JAR entry.
- Apache Maven — [Guide to Multi-Release JARs](https://maven.apache.org/guides/mini/guide-multi-release-jars.html): hướng dẫn build MRJAR và considerations với Maven plugins.

**Ghi nhớ:** MRJAR là **một JAR** có implementation cơ sở và các biến thể bytecode dưới `META-INF/versions/N`, được kích hoạt bằng `Multi-Release: true`. Từ Java 9, runtime chọn biến thể cao nhất không vượt phiên bản JDK. Muốn phát hành an toàn, cần biên dịch **từng release**, giữ **public API nhất quán**, xác thực cấu trúc bằng `jar --validate`, kiểm tra dependencies, và đặc biệt **chạy chính JAR đó trên các JDK đích thật**.