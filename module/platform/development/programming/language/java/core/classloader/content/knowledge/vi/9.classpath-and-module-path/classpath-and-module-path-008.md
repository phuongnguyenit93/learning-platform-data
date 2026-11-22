# Multi-release JAR và chọn bytecode theo phiên bản Java

## 1. Multi-release JAR giải quyết vấn đề gì?

Một thư viện Java đôi khi cần **chạy trên nhiều phiên bản JVM** nhưng muốn tận dụng API hoặc cách cài đặt hiệu quả hơn ở JDK mới. Nếu chỉ đưa class được biên dịch bằng Java 17 vào JAR, Java 8 không thể nạp class đó. Nếu chỉ giữ class tương thích Java 8, thư viện không khai thác được những khả năng xuất hiện từ Java 11, 17 hoặc mới hơn.

**Multi-release JAR (MR-JAR)**, được giới thiệu ở **Java 9 bởi JEP 238**, cho phép một file JAR chứa **nhiều bản class/resource cho những Java release khác nhau**. JVM và class loader hỗ trợ MR-JAR chọn phiên bản phù hợp với **Java runtime thực sự đang chạy**, theo cấu trúc bên trong JAR và thuộc tính manifest.

Hình dung cùng một binary name `demo.Selector`:

```text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── demo/Selector.class      (bản Java 11)
│       └── 17/
│           └── demo/Selector.class      (bản Java 17)
└── demo/
    ├── Main.class                       (bản nền)
    └── Selector.class                   (bản nền, Java 8)
```

Các class `demo.Selector` cùng tên là **các biến thể thay thế nhau**. Trong một lượt nạp tên này qua loader đọc MR-JAR, JVM chọn **một class file phù hợp**. Nó không chạy ba bản đồng thời và không tạo ba đối tượng `Class<?>` chỉ vì cả ba tệp tồn tại trong archive.

Bài này tập trung vào **đường dẫn tìm kiếm trong JAR**, **thuật toán chọn bytecode**, **cách xây dựng một MR-JAR có thể chạy**, **tác động của ClassLoader** và **các lỗi tương thích**.

## 2. Điều kiện để JAR thực sự là multi-release

Chỉ đặt các file bên dưới `META-INF/versions/` **chưa đủ**. JAR phải có main manifest attribute:

```text
Manifest-Version: 1.0
Multi-Release: true

```

File vật lý là `META-INF/MANIFEST.MF`. Thuộc tính `Multi-Release: true` cần nằm ở **main section** (trước dòng trống phân tách các section). Giá trị `true` không phân biệt chữ hoa/chữ thường theo đặc tả, nhưng nên ghi nhất quán như trên.

- Nếu thuộc tính này **không có** hoặc khác `true`, runtime xử lý JAR như JAR thông thường khi tìm class; các mục `META-INF/versions/N` không được dùng làm bản thay thế theo phiên bản.
- `N` trong `META-INF/versions/N` là **số feature release của Java** (ví dụ `9`, `11`, `17`, `21`), **không phải** số major của class file.
- Phiên bản thấp nhất của thư mục versioned có ý nghĩa là **9**. Thư mục `META-INF/versions/8/` không hoạt động như một nhánh dành riêng Java 8 theo quy tắc MR-JAR.
- Mục cho Java 8 hoặc thấp hơn phải nằm ở **thư mục gốc của JAR** nếu thư viện tuyên bố hỗ trợ chúng.
- Thư mục `META-INF/versions/N` phải chứa đúng đường dẫn package như bản root, ví dụ `META-INF/versions/17/com/acme/Foo.class`, không được thay thế bằng tên file khác rồi mong JVM tự map.

Tên `N` phải theo biểu diễn số nguyên dương hợp lệ của đặc tả, không dùng `v17`, `017` hay các chuỗi tùy ý. Dùng đúng `META-INF/versions/17` để tạo nhánh cho Java 17.

**Phân biệt hai loại phiên bản ngay từ đầu:**

| Giá trị | Ví dụ | Ý nghĩa |
|---|---|---|
| Java feature release | `17` | JDK/JVM Java 17 |
| Thư mục MR-JAR | `META-INF/versions/17` | Biến thể được phép chọn từ Java 17 trở lên khi không có bản phù hợp cao hơn |
| Class file major | `61` | Major của class file Java 17 |
| Class file minor | `0` | Bản class thông thường không dùng preview |

`META-INF/versions/17` là **directory targeting Java 17**; nó không đồng nghĩa với `major_version=17` bên trong bytecode.

## 3. Thuật toán chọn entry: số cao nhất không vượt quá runtime

Giả sử runtime đang chạy Java feature version `R` và class loader MR-aware cần tìm một logical entry, chẳng hạn `demo/Selector.class`.

Với Java 9 trở lên và JAR có `Multi-Release: true`, quy tắc khái quát là:

1. Tìm entry cùng đường dẫn tại `META-INF/versions/R/`.
2. Nếu chưa có, tìm lần lượt các thư mục phiên bản thấp hơn, từ `R-1` xuống **`9`**.
3. Lấy **entry có phiên bản cao nhất ≤ R** nếu nó tồn tại.
4. Nếu không thấy bản versioned nào phù hợp, dùng entry trong **thư mục gốc**.
5. Nếu root cũng không có entry phù hợp, quá trình tìm class đó thất bại.

```text
Runtime Java R ≥ 9
  tìm demo/Selector.class
       │
       ▼
META-INF/versions/R/demo/Selector.class?
       │ không có
       ▼
META-INF/versions/(R-1)/demo/Selector.class?
       │ không có
       ▼
... tìm giảm dần đến 9 ...
       │ không có
       ▼
demo/Selector.class ở JAR root
       │
       ▼
ClassLoader định nghĩa class từ bytecode được chọn
```

**Quan trọng:** Runtime **không nhất thiết chọn nhánh có số đúng bằng phiên bản nó đang chạy**. Nếu Java 21 chỉ thấy `versions/17` và `versions/11`, nó chọn **17**, vì đây là bản mới nhất **không vượt 21**. Nếu Java 15 không có bản 15 nhưng có 11, chọn 11. Java 8 không thực thi thuật toán MR-JAR của Java 9 và dùng đường dẫn root như JAR thông thường.

### Ví dụ bảng lựa chọn

Giả sử JAR có:

```text
demo/Selector.class
META-INF/versions/11/demo/Selector.class
META-INF/versions/17/demo/Selector.class
META-INF/versions/21/demo/Helper.class
```

Khi hỏi **`demo.Selector`**:

| Java runtime | Entry được chọn cho `demo.Selector` |
|---|---|
| Java 8 | `demo/Selector.class` (root) |
| Java 9, 10 | `demo/Selector.class` (root) |
| Java 11–16 | `META-INF/versions/11/demo/Selector.class` |
| Java 17–20 | `META-INF/versions/17/demo/Selector.class` |
| Java 21+ | `META-INF/versions/17/demo/Selector.class`, nếu chưa có bản Selector ở nhánh cao hơn |

Entry `versions/21/demo/Helper.class` **không ảnh hưởng** lựa chọn `Selector.class`: JVM chọn **riêng theo từng logical path**, không chọn duy nhất một thư mục cho toàn bộ JAR.

Nếu chỉ có phiên bản `17` mà không có `11`, Java 11 **quay về root**; nó không thử nạp class Java 17 từ nhánh cao hơn rồi hy vọng bytecode hoạt động.

## 4. “Chọn đúng nhánh” và “bytecode tương thích” là hai phép kiểm tra khác nhau

MR-JAR ưu tiên thư mục theo **Java runtime version**, nhưng JVM vẫn phải đọc và xác minh **class file version** thực sự của bytes được chọn.

Trong class file, các trường đầu là magic, `minor_version` và `major_version`. Một số ánh xạ:

| Java release | Class file major | Minor thông thường |
|---|---:|---:|
| Java 8 | 52 | 0 |
| Java 9 | 53 | 0 |
| Java 11 | 55 | 0 |
| Java 17 | 61 | 0 |
| Java 21 | 65 | 0 |
| Java 25 | 69 | 0 |
| Java 26 | 70 | 0 |

Một file dưới `META-INF/versions/17/` **không được** yêu cầu class file version cao hơn khả năng Java 17 hỗ trợ theo đặc tả MR-JAR. Ví dụ đặt bytecode **major 65** (biên dịch cho Java 21) vào nhánh `versions/17` là cấu trúc sai: Java 17 sẽ **chọn** entry này theo đường dẫn nhưng **không thể nạp** bytecode đó.

- Dùng `javac --release 8` để tạo bản root hỗ trợ Java 8.
- Dùng `javac --release 11` để tạo biến thể Java 11.
- Dùng `javac --release 17` để tạo biến thể Java 17.
- Một build dùng JDK 17 trở lên có thể biên dịch cả ba target nếu compiler hỗ trợ chúng; không cần chạy `javac` của từng runtime đích.

`javac --release N` hạn chế cú pháp, class target và tập API chuẩn của release N khi biên dịch. Chỉ đổi tên thư mục thành `versions/N` **không biến** bytecode của bản mới thành bytecode của N.

**Cảnh báo preview bytecode:** `minor=65535` biểu thị phụ thuộc preview của đúng bản Java; bytecode preview không tương thích tự động với các Java release tương lai dù major thấp hơn. Không đóng gói class preview như biến thể dài hạn chỉ vì MR-JAR có nhánh tương ứng. Ưu tiên code dùng API và tính năng Java đã được chuẩn hóa cho đúng runtime.

## 5. Ví dụ hoàn chỉnh: một JAR với ba bản Java 8, 11 và 17

Ta sẽ tạo một `mr-demo.jar` gồm:

- `demo.Main` nằm ở root, biên dịch tương thích Java 8.
- `demo.Selector` bản root trả chuỗi `"base-8"`.
- `demo.Selector` bản Java 11 trả `"java-11"`.
- `demo.Selector` bản Java 17 trả `"java-17"`.

Tất cả các biến thể `Selector` giữ **cùng public API** `public static String selected()`. Đây là mẫu tốt để thấy JVM thực sự thay đổi implementation theo runtime.

### 5.1. Chuẩn bị cấu trúc nguồn

Tạo các file và thư mục như sau:

```text
mr-demo/
├── src/
│   ├── base/
│   │   └── demo/
│   │       ├── Main.java
│   │       └── Selector.java
│   ├── v11/
│   │   └── demo/
│   │       └── Selector.java
│   └── v17/
│       └── demo/
│           └── Selector.java
└── out/
    ├── base/
    ├── v11/
    └── v17/
```

Các thư mục `out` chưa có file, sẽ chứa kết quả biên dịch. Mỗi phiên bản `Selector.java` nằm trong **source root riêng** vì chúng có cùng package/binary name và không thể đặt cùng một đường source compilation thông thường.

### 5.2. Bản Java 8: src/base/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "base-8";
    }
}
```

### 5.3. Lớp chạy chung: src/base/demo/Main.java

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Selected: " + Selector.selected());
    }
}
```

Chú ý `Main` không gọi API chỉ có từ Java 9 trở lên, vì bản root sẽ được biên dịch với `--release 8`. Nó tham chiếu cùng logical type `demo.Selector`; phiên bản nào thực thi phương thức đó được xác định khi runtime nạp `Selector`.

### 5.4. Bản Java 11: src/v11/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "java-11";
    }
}
```

### 5.5. Bản Java 17: src/v17/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "java-17";
    }
}
```

Bản 11 và 17 trong bài chỉ đổi chuỗi output để dễ kiểm chứng. Trong thư viện thực tế, các nhánh có thể triển khai khác nhau (ví dụ dùng API hay thuật toán có mặt ở JDK mới), **nhưng phải giữ hợp đồng API công khai được phép sử dụng chung**.

### 5.6. Biên dịch đúng từng release

Từ thư mục `mr-demo`, với **JDK 17 hoặc mới hơn** có hỗ trợ các target 8, 11, 17, tạo ba thư mục output. Nếu dùng Bash:

```bash
mkdir -p out/base out/v11 out/v17
```

Trên Windows PowerShell, có thể tạo chúng bằng:

```powershell
New-Item -ItemType Directory -Force out/base,out/v11,out/v17 | Out-Null
```

Tiếp theo, chạy các lệnh `javac` sau trong terminal:

```bash
javac --release 8 -d out/base src/base/demo/Main.java src/base/demo/Selector.java
javac --release 11 -d out/v11 src/v11/demo/Selector.java
javac --release 17 -d out/v17 src/v17/demo/Selector.java
```

Kết quả:

```text
out/
├── base/
│   └── demo/
│       ├── Main.class
│       └── Selector.class
├── v11/
│   └── demo/
│       └── Selector.class
└── v17/
    └── demo/
        └── Selector.class
```

Không biên dịch cả ba `Selector.java` vào **một output directory**, vì các class cùng tên sẽ ghi đè hoặc xung đột. Cũng không cần ba bản `Main`; `Main` ở root có thể gọi implementation của `Selector` mà JVM đã chọn.

### 5.7. Đóng gói multi-release JAR

Dùng `jar` tool của JDK 17+:

```bash
jar --create --file mr-demo.jar --main-class demo.Main -C out/base . --release 11 -C out/v11 . --release 17 -C out/v17 .
```

Trong lệnh này có **hai nghĩa khác nhau của `--release`**:

- `javac --release N` chọn cấp độ biên dịch và API tương thích Java N.
- `jar --release N` yêu cầu đóng gói những file theo sau vào `META-INF/versions/N/`.

`jar` tool tạo metadata để archive được nhận diện là MR-JAR, gồm `Multi-Release: true` trong manifest. Tùy phiên bản JDK, quá trình đóng gói có thể kiểm tra một số ràng buộc về các bản class cùng tên.

Archive kết quả có cấu trúc logic:

```text
mr-demo.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── demo/Selector.class
│       └── 17/
│           └── demo/Selector.class
└── demo/
    ├── Main.class
    └── Selector.class
```

Trong `META-INF/MANIFEST.MF`, các thuộc tính quan trọng sẽ gồm:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Multi-Release: true

```

Có thể có thêm thuộc tính do `jar` tool thêm vào (chẳng hạn `Created-By`). Không yêu cầu file manifest trong archive phải chứa **chính xác ba dòng duy nhất** như trích đoạn.

### 5.8. Chạy với những JVM khác nhau

Lệnh chung:

```bash
java -jar mr-demo.jar
```

Nhưng kết quả phụ thuộc vào **phiên bản Java của lệnh `java` đang thực thi**:

| JVM chạy lệnh | Biến thể Selector | Stdout |
|---|---|---|
| Java 8 | Root, target Java 8 | `Selected: base-8` |
| Java 9 hoặc 10 | Root | `Selected: base-8` |
| Java 11–16 | `versions/11` | `Selected: java-11` |
| Java 17–20 | `versions/17` | `Selected: java-17` |
| Java 21 hoặc mới hơn | `versions/17` nếu chưa có biến thể cao hơn | `Selected: java-17` |

Ví dụ nếu đang chạy bằng Java 17, stdout **chính xác** của chương trình là:

```text
Selected: java-17
```

Nếu máy chỉ cài JDK 21, bảng này mô tả hành vi của các JVM tương ứng chứ **không** có nghĩa một lần chạy bằng Java 21 có thể mô phỏng nguyên vẹn JVM 8. Muốn xác nhận Java 8 thực sự chạy, phải sử dụng runtime Java 8; muốn xác nhận Java 11, dùng runtime Java 11. Lệnh `javac --release 8` **không ép `java -jar` chạy như Java 8**.

## 6. Kiểm chứng JAR và bytecode thực tế

Không nên xác nhận MR-JAR chỉ bằng tên file `mr-demo.jar`. Sau build, hãy kiểm tra cả **cấu trúc**, **manifest**, **class file version** và **runtime selection**.

### 6.1. Liệt kê entry vật lý trong archive

```bash
jar --list --file mr-demo.jar
```

Tìm những entry quan trọng:

```text
demo/Main.class
demo/Selector.class
META-INF/versions/11/demo/Selector.class
META-INF/versions/17/demo/Selector.class
META-INF/MANIFEST.MF
```

Đây là **các dòng cần tìm**, không phải toàn bộ stdout có thứ tự cố định. Liệt kê physical entries cho thấy các file tồn tại nhưng **không nói** JVM cụ thể đã chọn file nào.

### 6.2. Xem class file major bằng javap

```bash
javap -verbose -classpath out/base demo.Selector
javap -verbose -classpath out/v11 demo.Selector
javap -verbose -classpath out/v17 demo.Selector
```

Trong output dài của từng lệnh, giá trị mong đợi lần lượt là:

```text
base: major version: 52
v11:  major version: 55
v17:  major version: 61
```

Ba dòng trên là **bảng tóm tắt kết quả**, không phải một đoạn stdout nguyên văn từ một lệnh `javap`. `javap -verbose` cũng hiển thị các trường constant pool, phương thức và attributes.

Với một MR-JAR, `javap` hỗ trợ tùy chọn `--multi-release` ở những JDK có hỗ trợ. Ví dụ:

```bash
javap --multi-release 11 -classpath mr-demo.jar -c demo.Selector
javap --multi-release 17 -classpath mr-demo.jar -c demo.Selector
```

Có thể dùng các lệnh này để xem phiên bản class có hiệu lực ở từng release mục tiêu, thay vì vô tình chỉ xem root. Nếu phân tích trực tiếp file trong JAR bằng công cụ ZIP, phải tự chọn đúng entry vật lý.

### 6.3. Dùng jar --validate

```bash
jar --validate --file mr-demo.jar
```

Công cụ `jar` có khả năng kiểm tra một số ràng buộc, đặc biệt khi tồn tại versioned classes. Tuy nhiên **thành công ở bước validate không chứng minh 100% API, dependency hoặc hành vi runtime của mọi nhánh là tương thích**. Đặc tả không yêu cầu công cụ hoặc JVM kiểm tra đầy đủ tính tương đương của mọi API công khai giữa các bản class.

### 6.4. Xác định runtime thật đang chạy

```bash
java -version
javac -version
```

Hai câu lệnh có thể dùng hai installation khác nhau qua `PATH`, IDE, Gradle toolchain, Docker hay CI. **JVM runtime** quyết định nhánh MR-JAR khi nạp; **compiler** quyết định bytecode major khi build. Trường hợp phát hành từ CI với JDK 21 rồi triển khai lên Java 17 phải được kiểm chứng bằng Java 17 thực tế.

## 7. Mỗi class/resource được chọn riêng, không chọn cả JAR thành “bản 17”

Một hiểu nhầm phổ biến là: nếu runtime chọn version 17 thì **mọi class trong JAR** đều lấy từ `versions/17`. Thực tế, **mỗi logical path** được tra theo chuỗi versioned directories độc lập.

Ví dụ:

```text
demo/Api.class
demo/FeatureA.class
demo/FeatureB.class

META-INF/versions/11/demo/FeatureA.class
META-INF/versions/17/demo/FeatureB.class
```

Trên Java 17:

- `demo.Api` không có entry versioned, nên dùng `demo/Api.class` ở root.
- `demo.FeatureA` dùng `versions/11/demo/FeatureA.class` (cao nhất ≤17 trong các bản của chính FeatureA).
- `demo.FeatureB` dùng `versions/17/demo/FeatureB.class`.

Ba logical classes tồn tại đồng thời trong **một ứng dụng** và có thể dùng các bản tối ưu khác nhau. Điều này giải thích vì sao mã ở một nhánh có thể gặp lỗi nếu API nội bộ giữa các lớp không tương thích.

**Tài nguyên cũng có thể được versioned**, nhưng không phải bất kỳ file nào bên dưới `META-INF` cũng được phép thay thế. Đặc tả quy định **resources nằm dưới `META-INF` không được versioned**, ví dụ cấu hình service provider `META-INF/services/...` không được tùy tiện đặt bản riêng bên dưới `META-INF/versions/N/META-INF/services/...` rồi mong cơ chế multi-release chọn nó.

Nếu ứng dụng/plugin đọc ZIP entries ở mức thấp, nó có thể thấy đường dẫn vật lý của từng phiên bản. Kết quả đọc resource qua `ClassLoader.getResource(...)` hoặc `Class.getResource(...)` có thể phụ thuộc runtime và triển khai JAR-aware của loader; không suy ra mọi API đọc file ZIP đều tự động áp dụng virtual view của MR-JAR.

## 8. Khi có nhiều JAR/classpath entry: thứ tự tìm kiếm nào thắng?

Quy tắc `versions/N` áp dụng **sau khi một class loader đã chọn nguồn JAR thích hợp để tìm tên class**. Nó không thay thế quy tắc delegation giữa ClassLoader hay thứ tự các classpath entries.

Ví dụ:

```text
Host Application ClassLoader
    ├── shared.jar (có demo.Selector)
    └── mr-demo.jar (có demo.Selector + versions/11 + versions/17)

Plugin ClassLoader
    └── plugin.jar
```

Nếu loader được hỏi thấy `demo.Selector` từ `shared.jar` trước theo chính sách và thứ tự classpath đang dùng, bản `Selector` trong `mr-demo.jar` **có thể không được xét**. Ngược lại, nếu nó chọn `mr-demo.jar`, khi đọc logical path `demo/Selector.class` thì MR-JAR chọn entry thích hợp với JVM version.

Tương tự, nếu custom loader kế thừa `ClassLoader.loadClass` mặc định, nó thường dùng thứ tự:

```text
findLoadedClass(name)
    ↓ chưa thấy
parent.loadClass(name) / bootstrap
    ↓ parent không tìm thấy
findClass(name)
    ↓
resolveClass(c) nếu được yêu cầu
```

Chính sách này là **parent-first**. Nếu parent đã định nghĩa `demo.Selector`, loader con thường không tự đọc biến thể `Selector` trong MR-JAR của nó.

**Hai tầng lựa chọn phải tách rõ:**

1. **ClassLoader nào** nhận và giải quyết yêu cầu class theo quy tắc delegation/classpath/module path?
2. **Bên trong MR-JAR đã được chọn**, entry versioned nào phù hợp với Java runtime?

Một loader tự viết `findClass` bằng `ZipFile.getEntry("demo/Selector.class")` chỉ đọc root có thể **bỏ qua** MR-JAR versioning. Loader muốn hỗ trợ MR-JAR phải sử dụng cơ chế đọc JAR phù hợp thay vì giả định bản root luôn là bytecode cuối cùng.

## 9. JarFile, JarEntry và “runtime view”

`java.util.jar.JarFile` là API đọc nội dung JAR. Với MR-JAR, cần phân biệt:

- **Physical view**: toàn bộ đường dẫn thực bên trong ZIP/JAR, gồm root và `META-INF/versions/11`, `META-INF/versions/17`.
- **Runtime-selected view**: khi lookup logical name `demo/Selector.class`, phiên bản cao nhất phù hợp với release được cấu hình sẽ được xem là entry cần dùng.

Theo Java API, một `JarFile` mở theo constructor thông thường **không nhất thiết tự áp dụng** MR-aware lookup cho Java runtime hiện tại; hành vi mặc định của `JarFile` có thể xem JAR như archive không versioned. Khi viết một class loader/JAR reader, có constructor và tham số `Runtime.Version` để yêu cầu nhìn theo một phiên bản mục tiêu, ví dụ `JarFile(File, boolean, int, Runtime.Version)`.

### Ví dụ đọc entry theo runtime version (Java 17+)

Tạo file `JarViewDemo.java`:

```java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;

public final class JarViewDemo {
    private static void check(String path, int feature)
            throws Exception {
        Runtime.Version version = Runtime.Version.parse(
                Integer.toString(feature)
        );

        try (JarFile jar = new JarFile(
                new File(path),
                true,
                ZipFile.OPEN_READ,
                version
        )) {
            JarEntry entry = jar.getJarEntry("demo/Selector.class");
            System.out.println(feature + ": " + entry.getRealName());
        }
    }

    public static void main(String[] args) throws Exception {
        check("mr-demo.jar", 8);
        check("mr-demo.jar", 11);
        check("mr-demo.jar", 17);
        check("mr-demo.jar", 21);
    }
}
```

Giả sử `mr-demo.jar` được tạo đúng như mục 5, biên dịch/chạy chương trình này bằng JDK 21 (hoặc mới hơn) để có môi trường bao quát các mức 8, 11, 17, 21:

```bash
javac JarViewDemo.java
java JarViewDemo
```

Các đường dẫn thực được lựa chọn sẽ là:

```text
8: demo/Selector.class
11: META-INF/versions/11/demo/Selector.class
17: META-INF/versions/17/demo/Selector.class
21: META-INF/versions/17/demo/Selector.class
```

**Điểm cần phân biệt:** Ở ví dụ này, `JarFile` được **cấu hình view theo Runtime.Version** để đọc entry; nó **không khởi chạy code Java dưới nhiều JVM khác nhau**. Kết quả in cho feature 8 là base entry trong virtual lookup. Để chứng minh ứng dụng thực sự chạy ở Java 8, vẫn phải chạy `java -jar mr-demo.jar` với JRE/JDK 8.

Lưu ý: Tham số `Runtime.Version` không thể biến môi trường JVM hiện tại thành phiên bản khác hoặc giúp nạp bytecode mới trên JVM cũ. Đây là API để **chọn entry đọc** từ JAR, phục vụ công cụ phân tích/đóng gói/loader thích hợp.

## 10. Public API phải nhất quán giữa các biến thể

Đặc tả MR-JAR có ràng buộc đối với **public API** của các bản class. Nếu một class public/protected nằm trong một versioned directory của MR-JAR thông thường, nó phải “preside over” định nghĩa tương ứng có tên và mức truy cập thích hợp ở mức thấp hơn/root; các API công khai được kỳ vọng tương đương qua các phiên bản.

Điều này nhằm đảm bảo code của người dùng không phải compile lại theo từng runtime chỉ vì họ chuyển từ Java 11 lên 17.

### Ví dụ API ổn định — đúng hướng

Root:

```java
package api;

public final class Feature {
    public static String value() {
        return "fallback";
    }
}
```

Phiên bản ở `versions/17`:

```java
package api;

public final class Feature {
    public static String value() {
        return "optimized";
    }
}
```

Đây là **hai lựa chọn source thay thế nhau** có cùng binary name, không nên compile chung một output directory. Chúng giữ cùng public method signature và cùng đặc điểm lớp, chỉ khác implementation.

### Ví dụ API bị lệch — nguy hiểm

Root:

```java
package api;

public final class Feature {
    public static String value() {
        return "fallback";
    }
}
```

Versioned branch thay đổi thành:

```java
package api;

public final class Feature {
    // Đã xóa public static String value()!
    public static int valueAsInt() {
        return 1;
    }
}
```

Nếu ứng dụng được compile để gọi `Feature.value()` nhưng JVM chọn bản versioned không còn phương thức này, có thể gặp **`NoSuchMethodError`** lúc liên kết/sử dụng, dù class file major hợp lệ và entry nằm đúng nhánh. Không dùng MR-JAR để lén thay đổi signature của API công khai.

**Có ngoại lệ đối với non-exported packages trong modular multi-release JAR** theo đặc tả module, nhưng đó là trường hợp thiết kế có chủ đích. Đối với thư viện thông thường chạy trên classpath, giữ **API nhị phân công khai nhất quán** giữa mọi nhánh là nguyên tắc quan trọng.

Không dựa hoàn toàn vào `jar --validate` để chứng minh hợp đồng API: công cụ và runtime không bắt buộc kiểm chứng mọi điều kiện. Nên có kiểm tra API binary bằng test/tool chuyên dụng và test ứng dụng trên những JDK được hỗ trợ.

## 11. ClassLoader và định danh kiểu trong MR-JAR

Khi application ClassLoader định nghĩa `demo.Selector` từ `versions/17`, runtime class đó vẫn có binary name **`demo.Selector`**. Đường dẫn `META-INF/versions/17` là **địa chỉ của class file được chọn**, không phải một phần của binary name hoặc Java package.

Vì vậy:

```java
Class<?> selected = Class.forName("demo.Selector");
System.out.println(selected.getName()); // demo.Selector
```

Đây là **trích đoạn**; để chạy độc lập cần một `main` và xử lý `ClassNotFoundException` hoặc khai báo `throws`. `getName()` không trả `META-INF.versions.17.demo.Selector`.

Đối tượng `Class<?>` đại diện một runtime class do **defining loader** đã định nghĩa. Một runtime không nạp nhiều biến thể của cùng binary name vào **cùng defining ClassLoader** rồi thay đổi chúng khi phiên bản Java đã cố định. Một khi `demo.Selector` được định nghĩa, những lời gọi `loadClass` sau thông thường lấy lại class đó.

Nếu có **hai defining ClassLoader độc lập**, chúng có thể tạo hai runtime classes cùng tên từ hai JAR hay thậm chí hai cách xem bytecode. Chúng không tự thành một kiểu, nhưng đây là **cơ chế danh tính ClassLoader**, tách biệt với việc MR-JAR chọn phiên bản theo runtime.

Cũng cần phân biệt:
- **Loading**: ClassLoader/JVM tìm và định nghĩa runtime class từ bytes đã chọn.
- **Linking**: JVM kiểm tra/chuẩn bị và phân giải các tham chiếu khi cần.
- **Initialization**: JVM chạy các biểu thức/khối khởi tạo `static` khi có active use phù hợp.

MR-JAR **chọn class file được nạp**; nó không tự thay đổi quy tắc initialization của Java.

## 12. Java 8, classpath, module path và giới hạn tương thích

### 12.1. Java 8 nhìn thấy gì?

Java 8 **chưa có** cơ chế multi-release. Nó nhận `mr-demo.jar` như JAR thông thường và dùng các mục class ở **root**. Các file nằm bên dưới `META-INF/versions/11` hoặc `META-INF/versions/17` là các archive entries, không trở thành phiên bản được chọn bởi JVM 8.

Điều đó có nghĩa:

- Nếu cần hỗ trợ Java 8, các class bắt buộc để chạy ứng dụng phải có bản phù hợp Java 8 tại root.
- Root không thể sử dụng source/API chuẩn chỉ có ở Java 11/17.
- Không đặt entry point `Main.class` chỉ ở `versions/17` rồi tuyên bố Java 8 có thể chạy `java -jar`.
- Một dependency nằm bên ngoài JAR cũng phải tương thích Java 8; có root bytecode 52.0 thôi chưa đủ.

### 12.2. Java 9+ trên classpath

Với class loader chuẩn hỗ trợ MR-JAR, các phiên bản phù hợp được chọn tự động khi JAR nằm trên classpath. Người dùng không cần gọi riêng `Class.forName("META-INF.versions.17.demo.Selector")` — đây thậm chí không phải binary name của class.

Chạy:

```bash
java -cp mr-demo.jar demo.Main
```

Với JDK 17, chương trình tương đương lựa chọn `versions/17` như `java -jar mr-demo.jar` ở mục 5, cho stdout:

```text
Selected: java-17
```

### 12.3. Module path

MR-JAR có thể xuất hiện trên module path (automatic module hoặc explicit modular multi-release JAR) từ Java 9 trở lên, nhưng **module descriptor** cũng phải tuân theo những giới hạn đặc thù:

- `module-info.class` có thể ở root hoặc vị trí versioned theo quy tắc MR modular JAR.
- Descriptor versioned phải giữ tính nhất quán theo JAR specification; có một số ngoại lệ xác định đối với yêu cầu module nền tảng và `uses`.
- Public/protected classes trong các package **không export** có quy tắc “preside over” khác so với API export.

Đây là các yêu cầu **thêm** của hệ module. Ví dụ ở mục 5 là **classpath / executable JAR không có module-info**, để thấy rõ cơ chế chọn bytecode nền tảng.

### 12.4. Bootstrap loader không hỗ trợ MR-JAR lookup

Đặc tả lưu ý rằng **bootstrap class loader không hỗ trợ MR-JAR** theo cùng cách với class loaders thông thường. Nếu đưa MR-JAR vào bootstrap search path bằng cơ chế như `-Xbootclasspath/a` (trên JVM còn hỗ trợ), archive được xử lý như JAR bình thường. Không suy rộng ví dụ classpath ở mục 5 sang mọi vị trí nạp đặc biệt của JVM.

## 13. Các lỗi thường gặp và cách phát hiện

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Java 17 vẫn dùng bản root | Thiếu `Multi-Release: true`, sai đường dẫn, không có đúng entry, loader không MR-aware hoặc parent chọn class khác | Kiểm tra manifest, `jar --list`, defining loader và classpath |
| Java 11 báo `UnsupportedClassVersionError` | Root hoặc nhánh 11 có bytecode vượt major được Java 11 hỗ trợ | Biên dịch với `javac --release 11` và xác minh major ≤55 |
| Java 8 không chạy JAR | Root chứa class mới hơn Java 8 hoặc thiếu class/dependency ở root | Biên dịch root với `--release 8`; test trên Java 8 |
| Java 21 chọn nhánh 17 | Không có bản 21 cho logical class đang xét | Đây là fallback đúng: lấy bản phù hợp cao nhất ≤21 |
| Class versioned có tên khác hoặc package khác | Entry path không tương ứng binary name | Đặt bản class đúng cùng package và tên như root |
| `jar --validate`/build báo API mismatch | Branch thay signature/modifiers/constructor công khai | Giữ API tương thích hoặc thiết kế lại các nhánh |
| `NoSuchMethodError` khi nâng JVM | Runtime chọn branch có API không khớp caller | So sánh public binary APIs và test trên runtime đích |
| Chỉ dùng root khi đọc bằng công cụ custom | Loader/JarFile mở physical view hoặc bỏ qua versioned entries | Chọn MR-aware lookup/`Runtime.Version` phù hợp |
| Debug qua `Class.getName()` không thấy phiên bản | Binary name không chứa `versions/N` | Xem code source/JAR entry hoặc runtime view đúng |
| Nhánh versioned chứa class chỉ hợp lệ với preview | JVM khác bản preview từ chối class dù chọn nhánh | Không phụ thuộc preview cho MR-JAR phát hành đa JDK |
| “Đã nâng JDK nhưng class cũ không đổi” | Class đã được loader định nghĩa; chưa khởi động lại/chưa thay loader | Khởi động lại process hoặc dùng cơ chế reload được thiết kế |

### Một chuỗi debug có hệ thống

1. Xác nhận **runtime** thực tế: `java -version` tại chính môi trường chạy.
2. Xác nhận JAR thực sự trên **classpath/module path** và không bị JAR khác cùng class name/parent loader che.
3. Liệt kê **physical entries** bằng `jar --list --file <jar>`.
4. Xem main manifest có **`Multi-Release: true`** và đường dẫn `META-INF/versions/N/...` đúng.
5. Xác nhận **entry được chọn** cho logical name ở runtime đó — bằng `JarFile` MR-aware, `javap --multi-release` hoặc chạy thử.
6. Xác nhận **class file major** của chính biến thể đã chọn và API binary với compile target.
7. Chạy test/smoke test trên **mỗi JDK tối thiểu mà thư viện tuyên bố hỗ trợ**, không chỉ JDK build.

Không sửa bằng cách đổi thủ công số `major_version` trong file class: các instruction, constant pool và API của bytecode có thể vẫn yêu cầu tính năng JVM mới.

## 14. Khi nào nên dùng và khi nào không cần?

MR-JAR hữu ích khi thư viện cần đồng thời:

- Một **baseline runtime cũ** còn được khách hàng sử dụng.
- Một hoặc nhiều **implementation tối ưu/tận dụng API mới** trên JDK 9+.
- Một artifact phân phối duy nhất giữ public API ổn định và cho JVM chọn tự động.

Ví dụ thư viện mã hóa, I/O, runtime diagnostics hoặc networking có thể có implementation riêng cho Java 11/17, trong khi API ứng dụng nhìn thấy giống nhau.

Tuy nhiên, MR-JAR làm tăng trách nhiệm maintain: nhiều build targets, nhiều bản bytecode cho cùng binary name, kiểm tra API và test matrix nhiều JDK. Nếu library chỉ hỗ trợ Java 17 trở lên và không cần implementation khác theo runtime, **một JAR thông thường biên dịch `--release 17` có thể đủ**. Không thêm các nhánh versioned chỉ để tăng số thư mục mà không có lợi ích học tập/vận hành rõ ràng.

### Quy trình release nên áp dụng

- Quy định **JDK tối thiểu** và danh sách **nhánh versioned thực sự cần**.
- Giữ root có đầy đủ API/implementation tối thiểu.
- Biên dịch **từng nhánh với `--release N`**, cách ly output directories.
- Đóng gói với `jar --release N` hoặc build task tạo đúng entry và manifest.
- Kiểm tra cấu trúc MR-JAR, class file versions và API consistency.
- Chạy smoke/integration test với các Java runtimes đại diện, đặc biệt **baseline**, **mỗi điểm chuyển nhánh**, **runtime mới nhất được hỗ trợ**.
- Cảnh giác các công cụ shading, repackaging hoặc fat-JAR layout có thể thay đổi entry paths/manifest. Sau khi xuất artifact cuối cùng, **đọc lại chính artifact phát hành** thay vì chỉ kiểm tra thư mục build trung gian.

## 15. Câu hỏi tự kiểm tra

1. **MR-JAR xuất hiện từ bản Java nào?** Java 9, theo JEP 238.
2. **Chỉ tạo `META-INF/versions/17` đã đủ kích hoạt chưa?** Chưa; cần main manifest attribute `Multi-Release: true`.
3. **Đang chạy Java 21, JAR có Selector ở root, versions/11 và versions/17. JVM dùng gì?** `versions/17/demo/Selector.class`.
4. **Đang chạy Java 10 nhưng JAR chỉ có versioned 11, 17 và root. JVM dùng gì?** Root.
5. **Nằm dưới `versions/17` có nghĩa class file major=17 không?** Không; Java 17 tương ứng major 61.
6. **Một class file major 65 đặt dưới `versions/17` có hợp lệ để Java 17 chạy không?** Không; Java 17 không hỗ trợ class file Java 21.
7. **`javac --release 11` và `jar --release 11` làm cùng một việc không?** Không; một cái chọn target biên dịch/API, một cái chọn directory trong MR-JAR.
8. **Java 8 có chọn `versions/11` nếu entry root không tồn tại không?** Không; nó không hỗ trợ multi-release lookup.
9. **Mỗi runtime chỉ chọn duy nhất một thư mục cho toàn JAR không?** Không; chọn phiên bản cao nhất phù hợp **riêng cho mỗi logical entry**.
10. **Cùng binary name `demo.Selector` từ root và versions/17 có tạo hai class khác nhau trong cùng defining ClassLoader khi load một lần không?** Không; loader chọn một entry cho runtime đó.
11. **Thiếu phiên bản 21 có khiến Java 21 không chạy được MR-JAR có versions/17 không?** Không; Java 21 có thể dùng bản 17 nếu tương thích.
12. **`jar --validate` thành công có bảo đảm mọi public API và dependency hoàn toàn tương thích không?** Không; cần thêm kiểm tra binary API và runtime tests.
13. **Đặt `META-INF/services/...` dưới `META-INF/versions/N/META-INF/services` có phải cách chuẩn để version service configuration không?** Không; tài nguyên thuộc `META-INF` không được versioned theo cơ chế đó.
14. **Nếu custom loader chỉ gọi `ZipFile.getEntry("demo/Selector.class")`, nó có tự chọn branch 17 không?** Không; đó là truy vấn đường dẫn vật lý root, phải dùng cơ chế MR-aware nếu muốn lựa chọn theo runtime.

## Tài liệu chuẩn

- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): động cơ và thiết kế cơ chế nhiều phiên bản trong một JAR.
- [JAR File Specification — Multi-release JAR files, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): cấu trúc `META-INF/versions/N`, manifest, thuật toán tìm, ràng buộc bytecode/API và quy tắc module.
- [The jar Command, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): cú pháp `jar --create`, `--release`, `--list` và `--validate`.
- [JarFile API, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): runtime version view và `getRealName()`.
- [javap command, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): phân tích class file và tùy chọn multi-release.

**Điều quan trọng nhất:** Với MR-JAR hợp lệ, ClassLoader hỗ trợ cơ chế này sẽ tìm **entry theo logical name**, chọn bản versioned có **N cao nhất nhưng không vượt phiên bản JVM đang chạy**, và cuối cùng fallback về root. Bytecode được chọn vẫn phải tương thích với JVM; một JAR chứa nhiều bản không thay thế được việc biên dịch đúng target và kiểm thử trên từng runtime được hỗ trợ.
