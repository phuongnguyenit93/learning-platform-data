# Biên dịch phụ thuộc đã được tạo bởi JDK mới hơn

Trong một dự án Java, mã nguồn ứng dụng có thể **không sử dụng cú pháp Java mới**, nhưng vẫn không biên dịch hoặc chạy được trên Java cũ vì một **thư viện phụ thuộc (`.class` hoặc `.jar`)** đã được tạo bởi JDK mới hơn. Ví dụ, ứng dụng muốn hỗ trợ Java 17 nhưng thư viện trên classpath chứa class file của Java 21 sẽ gặp vấn đề về tương thích bytecode. Nếu đổi JDK chạy compiler từ 17 lên 21, bước compile có thể qua, nhưng ứng dụng **vẫn không thể mặc nhiên chạy trên Java 17**.

Bài này phân biệt rõ **khả năng đọc class file của compiler**, **class file mới do ứng dụng tạo**, **API nền tảng và API thư viện**, **khả năng nạp bytecode của JVM runtime**, rồi hướng dẫn phát hiện nguyên nhân và chọn cách xử lý đúng. Các ví dụ tập trung vào Java 17 và 21.

## 1. Trước hết phân biệt bốn phiên bản

Khi debug một lần biên dịch có dependency, hãy ghi nhận bốn thành phần độc lập:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **JDK chạy `javac`** | JDK 17 hoặc JDK 21 | Quyết định phiên bản class file cao nhất compiler thường có thể đọc và những target `--release` được hỗ trợ |
| **Release mục tiêu của nguồn ứng dụng** | `--release 17` | Quy định cú pháp nguồn, class-file target và API nền tảng Java 17 mà chính mã ứng dụng được phép dùng |
| **Phiên bản class file của dependency** | Library `.class` có major `65` | Nói dependency đã được xuất ở định dạng class file của Java 21, bất kể code ứng dụng muốn target gì |
| **JVM chạy ứng dụng** | Runtime Java 17 | Phải nạp được **mọi class thực sự được sử dụng**, bao gồm dependency, không chỉ `Main.class` |

Một tình huống phổ biến:

```text
Application source
    |
    | javac JDK 21 --release 17
    v
Application.class  (major 61 = Java 17)
    |
    +-- uses Library.class (major 65 = Java 21)
                         |
                         v
                Java 17 runtime cannot load this class
```

Sơ đồ trên mô tả **rủi ro thực tế của ứng dụng**, kể cả khi compiler JDK 21 có khả năng đọc thư viện major 65 và biên dịch thành công mã ứng dụng thành major 61. Việc class mới target 17 **không hạ cấp** class nằm sẵn trong một JAR phụ thuộc.

**Định nghĩa ngắn:** *Compile-time compatibility* trả lời “`javac` có đọc, liên kết và kiểm tra được dependency không?”; *runtime compatibility* trả lời “JVM đích có nạp và thực thi được mọi class/dependency cần thiết không?”. Hai kết luận có thể khác nhau.

## 2. Major/minor version của Java class file

Mỗi `.class` bắt đầu bằng header bao gồm magic number `CAFEBABE`, `minor_version` và `major_version`. JVM dùng các version này để xác định class file có thuộc định dạng nó hỗ trợ không. Một số mốc hay gặp:

| Java release | Class-file major version | Ví dụ |
| --- | --- | --- |
| Java 8 | 52 | `52.0` |
| Java 11 | 55 | `55.0` |
| Java 17 | 61 | `61.0` |
| Java 18 | 62 | `62.0` |
| Java 20 | 64 | `64.0` |
| Java 21 | 65 | `65.0` |
| Java 22 | 66 | `66.0` |
| Java 23 | 67 | `67.0` |
| Java 24 | 68 | `68.0` |

Với những Java release hiện đại trong bảng, major version tăng một đơn vị khi release tăng một đơn vị. Không suy rộng một công thức đơn giản cho mọi bản Java 1.x lịch sử.

**Ví dụ:** Class file `65.0` được tạo theo định dạng Java 21. `javac` JDK 17 thông thường **không thể đọc** định dạng đó làm dependency. JVM Java 17 cũng **không thể nạp** class file major 65. JVM Java 21 có thể nạp class major 61 của Java 17 trong những điều kiện tương thích thông thường; chiều ngược lại không được bảo đảm.

### Preview features và minor version `65535`

Một class file dùng **preview features** có thể mang minor version `65535` (với major version tương ứng bản Java dùng preview). Đây là trường hợp đặc biệt: class preview chỉ được JVM **đúng Java release** hỗ trợ khi chạy với cấu hình preview phù hợp; ngay cả JVM release mới hơn cũng không mặc nhiên được nạp class preview cũ. Khi xem `65.65535`, hãy điều tra preview settings riêng, thay vì chỉ kết luận “JVM cần major ít nhất 65”.

## 3. Quan sát version bằng `javap` và xác định đúng artifact

Để xem major version của class file, sử dụng `javap` của một JDK **đủ mới để hiểu định dạng file cần kiểm tra**:

```sh
javap -verbose -classpath build/lib library.Library
```

Tìm đoạn:

```text
minor version: 0
major version: 65
```

Đây là **ví dụ đầu ra cần tìm khi class được biên dịch cho Java 21**, không phải kết quả mặc định của mọi file `Library.class`.

Nếu phụ thuộc là JAR:

```sh
jar --list --file libs/vendor.jar
javap -verbose -classpath libs/vendor.jar library.Library
```

`jar --list` cho biết các entry; `javap` đọc class dựa trên classpath và tên kiểu. Với JAR phức tạp, cần bảo đảm bạn đang xem **entry thực sự được compiler/runtime lựa chọn**. Có thể tồn tại nhiều phiên bản cùng một tên class trong multi-release JAR.

**Không dùng tên file JAR để suy ra Java release.** `my-lib-2.0.jar` hoặc manifest có trường ghi JDK build **không đủ chứng minh** tất cả class file đều cùng một major version. Thư viện có thể chứa class files hỗn hợp, class đã shade, generated code hoặc các entry versioned.

Trước khi phân tích sự cố, nên ghi:

```sh
java -version
javac -version
```

Hai lệnh có thể trỏ đến hai JDK khác nhau nếu `PATH`, `JAVA_HOME`, IDE hoặc build tool cấu hình không đồng nhất. Với project có nhiều Java toolchains, phải xem **compiler và runtime thực sự được dùng trong từng tác vụ**.

## 4. Ví dụ đầy đủ: thư viện Java 21, ứng dụng Java 17

Chuẩn bị hai JDK (17 và 21) cùng project source. Mỗi khối lệnh yêu cầu **chọn JDK ghi ở tiêu đề làm JDK đang hoạt động** bằng `JAVA_HOME`/`PATH` hoặc gọi trực tiếp đường dẫn đến executable của JDK đó. Không giả định hệ điều hành có một chương trình tên `javac21`.

Cấu trúc:

```text
project/
├── src/
│   ├── library/
│   │   └── library/
│   │       └── Library.java
│   └── app/
│       └── client/
│           └── Main.java
└── build/                   # đầu ra sinh sau khi compile
```

Tệp `src/library/library/Library.java`:

```java
package library;

public final class Library {
    private Library() {
    }

    public static int answer() {
        return 42;
    }
}
```

Tệp `src/app/client/Main.java`:

```java
package client;

import library.Library;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Thư viện: " + Library.answer());
    }
}
```

Cả hai file đều dùng cú pháp có sẵn trên Java 17. **Thứ quyết định lỗi trong thí nghiệm là class-file version của `Library.class`**, không phải một cú pháp Java mới nằm trong source của library.

### 4.1. Tạo dependency bằng JDK 21

Chọn **JDK 21**, kiểm tra:

```sh
javac -version
javac --release 21 -encoding UTF-8 -d build/lib21 src/library/library/Library.java
javap -verbose -classpath build/lib21 library.Library
```

Class file được tạo tại:

```text
build/lib21/library/Library.class
```

`javap -verbose` cho biết `major version: 65`. Compiler thành công thường không in stdout nào. Ghi nhớ rằng **tên thư mục `lib21` chỉ là quy ước**; bằng chứng thật nằm ở class-file header và toolchain đã tạo nó.

### 4.2. Dùng `javac` JDK 17 để biên dịch ứng dụng

Chọn **JDK 17**, kiểm tra `javac -version` phải là 17.x, rồi chạy:

```sh
javac --release 17 -encoding UTF-8 -cp build/lib21 -d build/app17 src/app/client/Main.java
```

Lượt biên dịch này **thất bại** vì `javac` 17 phải đọc `library.Library` major 65 để phân giải `Library.answer()`, trong khi nó chỉ hiểu các class-file versions phù hợp với JDK 17 trở về trước. Diagnostics điển hình:

```text
bad class file: .../library/Library.class
class file has wrong version 65.0, should be 61.0
```

Đây là **trích đoạn thông báo thường gặp**, không cam kết nguyên văn gồm đúng đường dẫn, vị trí, dấu câu hoặc số dòng trên mọi JDK. Một compiler có thể viết “cannot access Library” hay “bad class file”; hãy đọc cả phần cause, đặc biệt **wrong version 65.0 / 61.0**.

**Kết luận tại thời điểm này:** Lỗi xảy ra ở **compile-time**, trước khi chạy `Main`. Thêm `--release 17` không khiến `javac` 17 đọc được một class file tương lai.

### 4.3. Cách sửa để hỗ trợ Java 17 thực sự: biên dịch lại dependency

Chọn **JDK 21** và biên dịch lại chính source của thư viện với target 17:

```sh
javac --release 17 -encoding UTF-8 -d build/lib17 src/library/library/Library.java
javap -verbose -classpath build/lib17 library.Library
```

Lần này output của thư viện là `build/lib17/library/Library.class`, có **major version 61**. Nguồn thư viện phù hợp Java 17 nên biên dịch được với target này.

Chọn **JDK 17**, biên dịch app với dependency mới:

```sh
javac --release 17 -encoding UTF-8 -cp build/lib17 -d build/app17 src/app/client/Main.java
```

Chạy bằng **JVM Java 17**. Trên Linux/macOS, classpath phân cách bằng dấu hai chấm:

```sh
java -cp build/app17:build/lib17 client.Main
```

Trên Windows PowerShell/cmd, classpath phân cách bằng dấu chấm phẩy và nên đặt trong dấu nháy:

```powershell
java -cp "build/app17;build/lib17" client.Main
```

**Stdout chính xác** của chương trình khi dùng hai class files biên dịch cho Java 17:

```text
Thư viện: 42
```

Kết quả sau sửa:

```text
build/
├── lib17/
│   └── library/Library.class    # major 61
└── app17/
    └── client/Main.class        # major 61
```

Với ví dụ không có phụ thuộc ngoài nào khác, cả application và library đều có version mà Java 17 hiểu được. Đây là cách kiểm chứng có ý nghĩa hơn việc chỉ cho `Main.class` đạt major 61.

### 4.4. Cảnh báo quan trọng: compiler mới vẫn có thể tạo bản build đánh lừa

Giữ `build/lib21` là dependency major 65. Chọn **JDK 21** và biên dịch app như sau:

```sh
javac --release 17 -encoding UTF-8 -cp build/lib21 -d build/app17 src/app/client/Main.java
```

Trong tình huống này, `javac` 21 **hiểu** class major 65 của thư viện, và có thể biên dịch ứng dụng thành `Main.class` major 61. **`--release 17` không kiểm tra hoặc chuyển đổi tất cả class files của thư viện bên thứ ba trên classpath thành major 61.**

Nếu chạy hai output đó bằng **Java 21**, chương trình đơn giản trên chạy và in:

```text
Thư viện: 42
```

Nhưng nếu chạy bằng **Java 17**, khi JVM cố nạp `library.Library` major 65, nó sẽ ném `UnsupportedClassVersionError`. Trong output của một JVM Java 17, lỗi có thể nêu:

```text
java.lang.UnsupportedClassVersionError: library/Library has been compiled by a more recent version of the Java Runtime (class file version 65.0), this version of the Java Runtime only recognizes class file versions up to 61.0
```

Đây là **thông báo minh họa**: câu chữ/stack trace phụ thuộc phiên bản JVM và thời điểm load class. Điểm chắc chắn là runtime Java 17 không hỗ trợ định dạng class major 65.

**Bài học:** “Biên dịch thành công với `--release 17`” **chưa chứng minh** tất cả dependencies có thể chạy trên Java 17. Phải kiểm tra version và API của **toàn bộ runtime dependency graph**.

## 5. `--release` bảo đảm điều gì và không bảo đảm điều gì?

Đối với **source đang được `javac` biên dịch**, `--release N` điều khiển:

1. Cú pháp và tính năng ngôn ngữ được chấp nhận theo Java `N`.
2. Class-file target version tương ứng `N`.
3. **API nền tảng Java/JDK được công bố** ở release `N` mà source có thể tham chiếu.

Ví dụ, JDK 21 + `--release 17` không cho một source bình thường gọi một JDK API chỉ xuất hiện từ Java 21. Đó là điểm mạnh hơn của `--release` so với việc chỉ dùng `-source` và `-target` trên một JDK mới.

Nhưng `--release` **không phải bộ phân tích tương thích mọi JAR**:

- Không biên dịch lại dependency có sẵn trên classpath/module path.
- Không bắt buộc tất cả class files của dependency phải có major version nhỏ hơn hoặc bằng target release.
- Không xác minh toàn bộ các method/field phụ thuộc ở runtime đều tồn tại và hoạt động trên Java `N`.
- Không ngăn dependency bị đóng gói nhầm version, shadowed class hoặc JAR có multi-release layout sai.
- Không nâng cấp một compiler cũ để nó đọc được class-file format mới.
- Không chuyển syntax Java mới thành syntax Java cũ nếu chính source không tương thích với `--release`.

### Vì sao `-source` / `-target` cũng không phải giải pháp?

`-source 17` giới hạn ngôn ngữ nguồn; `-target 17` chọn class-file format của **đầu ra đang biên dịch**. Chúng không thay đổi class file ở bên trong `vendor.jar` và không tự giới hạn đầy đủ JDK platform APIs khi compiler mới hơn.

Vì vậy, đổi `--release 17` thành `-source 17 -target 17` **không chữa lỗi dependency major 65**. Cách hiệu quả là chọn đúng phiên bản thư viện hoặc build thư viện cho Java 17, rồi chạy xác minh trên Java 17.

## 6. Phân biệt lỗi compiler và lỗi runtime

| Dấu hiệu | Giai đoạn xảy ra | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- | --- |
| `bad class file: ... wrong version 65.0, should be 61.0` | `javac` cũ đọc dependency | Compiler không hỗ trợ class-file version mới | Kiểm tra `javac -version` và class file của dependency |
| `UnsupportedClassVersionError` | JVM tải class | Runtime JVM không hỗ trợ major/minor version của class | Kiểm tra `java -version`, class thực sự được load, mọi runtime dependency |
| `NoSuchMethodError` | Linkage/lúc gọi method | Đã compile với ABI/version của library khác với runtime | So sánh method signatures và JAR được đóng gói/chạy |
| `NoClassDefFoundError` | Class loading/linkage | Thiếu dependency runtime hoặc class load/init thất bại | Kiểm tra runtime classpath/module path, log cause |
| `ClassNotFoundException` | Nạp lớp theo tên qua API có thể phát checked exception | Class không có ở đường nạp, sai tên hoặc loader | Kiểm tra class loader và tên class |
| `package ... does not exist` | `javac` phân giải dependency | Sai/mất classpath, module path, package hoặc JAR | Kiểm tra đường dẫn, artifact contents |
| `cannot access ...` + version mismatch | `javac` phân giải type | Dependency có class format không đọc được hoặc file hỏng | Đọc nested diagnostic, không chỉ dòng đầu |

**`UnsupportedClassVersionError`** là một `LinkageError` (nhánh `ClassFormatError`), phát sinh khi VM đọc class có major/minor version không được hỗ trợ. Nó không phải lỗi cú pháp `.java`. Ngược lại, thông báo `bad class file` từ `javac` là lỗi trong quá trình phân tích dependency **trước runtime**.

Đôi khi việc build có nhiều công đoạn khiến log lẫn nhau: Gradle/Maven có thể dùng compiler JDK 21, rồi chạy unit tests bằng JDK 17. Vì vậy một lệnh `compileJava` thành công không nói gì chắc chắn về `test` hoặc production JVM.

## 7. Các phương án xử lý đúng theo hoàn cảnh

### Phương án A — Chọn bản thư viện hỗ trợ Java đích

Nếu ứng dụng **phải chạy Java 17**, ưu tiên phiên bản thư viện được tác giả công bố hỗ trợ Java 17 và có artifact thật sự biên dịch tương thích. Ghi rõ version trong dependency management, chạy kiểm tra đầu ra, và xác nhận các dependencies bắc cầu cũng phù hợp.

Cần đối chiếu:

- **Release notes/compatibility matrix** của thư viện: minimum Java runtime là bao nhiêu?
- Artifact đã tải trong Maven/Gradle cache: là phiên bản nào, đến từ repository nào?
- Class-file major thực tế của classes cần sử dụng.
- Phụ thuộc bắc cầu và plugin/agent được nạp ở runtime.

Không suy ra “library source có thể viết theo Java 17” từ “JAR hiện tại đã được tác giả tạo bằng JDK 21”: source có thể viết lại/biên dịch lại được, nhưng **artifact cụ thể đang phân phối** vẫn có class files major 65.

### Phương án B — Rebuild thư viện với target thấp hơn

Nếu sở hữu source thư viện và nó tương thích với Java 17, dùng toolchain phù hợp:

```sh
javac --release 17 -encoding UTF-8 -d build/lib17 src/library/library/Library.java
```

Đối với thư viện thực tế, Maven/Gradle có thể quản lý source sets, dependency graph, annotation processors và packaging. Nếu source hoặc dependency của thư viện **bắt buộc dùng API/tính năng chỉ có ở Java 21**, việc thêm `--release 17` sẽ làm compilation thất bại. Đó là tín hiệu phải **thay implementation**, **chọn phiên bản thư viện khác** hoặc **nâng minimum Java** của sản phẩm.

Không sửa byte major 65 thành 61 bằng hex editor: class mới có thể chứa constant-pool entries, attributes, bootstrap instructions hay API dependencies mà Java 17 không hiểu. Đổi header không phải chuyển đổi ngữ nghĩa/bytecode hợp lệ.

### Phương án C — Nâng JDK compiler và cả runtime khi được phép

Nếu sản phẩm **chấp nhận Java 21 trở lên**, nâng toolchain và runtime tương ứng là một lựa chọn hợp lệ. Trong trường hợp ấy, dùng `--release 21` để thể hiện rõ minimum Java 21 của ứng dụng, khi thật sự phù hợp với platform APIs/dependencies.

Lưu ý: Nâng **chỉ compiler** để đọc dependency major 65 nhưng vẫn triển khai production trên Java 17 sẽ tạo sự cố runtime như mục 4.4. Quyết định nên được nêu trong hợp đồng deploy (base image, CI/JDK, container runtime, máy khách).

### Phương án D — Multi-release JAR khi cần hỗ trợ nhiều JVM

Một **multi-release JAR** có thể chứa bản class tương thích ở root và những implementation dành riêng cho Java release mới dưới `META-INF/versions/N/`. Manifest cần có:

```text
Multi-Release: true
```

Ví dụ sơ đồ (chỉ là cấu trúc minh họa):

```text
example-mr.jar
├── META-INF/MANIFEST.MF
├── library/Library.class                 # base, tương thích Java 17
└── META-INF/versions/21/
    └── library/Library.class             # implementation riêng cho Java 21
```

JVM Java 17 chọn phiên bản gốc phù hợp; JVM Java 21 có thể chọn entry `versions/21` nếu JAR được đánh dấu multi-release hợp lệ. Các công cụ biên dịch/đóng gói phải xử lý đúng quy tắc chọn versioned entry và tính tương thích API. Không thể chỉ đặt tùy ý một class 65 vào JAR thông thường rồi hy vọng Java 17 tự bỏ qua nó.

**Multi-release JAR không tự giải quyết thay đổi public API tùy tiện.** Các lớp versioned phải tuân thủ những quy tắc nhất định của JAR File Specification để giữ hợp đồng ở các phiên bản. Nếu công cụ phân tích bytecode bên ngoài quét toàn bộ JAR mà không hiểu multi-release layout, nó vẫn có thể vấp phải entry phiên bản cao; cần cập nhật công cụ hoặc cấu hình đúng cách.

## 8. Trường hợp JPMS và annotation processors

### Dependency trên module path

Nếu dependency là một named module, bạn dùng `--module-path`/`module-info.java` thay vì classpath thuần. Compiler vẫn phải đọc `module-info.class` và các class cần thiết. Một module được tạo bởi JDK mới hơn có thể gây **version mismatch**, hoặc chứa metadata/module declarations/API mà JDK cũ chưa hiểu.

Không nhầm với **module readability** và **exports**: một lỗi “module does not read ...” hay “package not exported” là vấn đề **quan hệ truy cập JPMS**, không tự động là class-file version mismatch. Phải đọc diagnostic thực tế.

### Annotation processors và compiler plugins

Một JAR dùng làm **annotation processor** cũng chứa class files và **được chạy trong quá trình biên dịch**. Processor tạo bằng JDK 21 có thể không chạy trong JVM JDK 17 dùng để chạy compiler, ngay cả khi source chính dùng `--release 17`. Tùy môi trường, lỗi có thể xuất hiện khi compiler cố nạp processor, như `UnsupportedClassVersionError`, hoặc thông báo “bad service configuration” do class processor không tải được.

Ở đây nên phân biệt:

- **Compile dependency:** JAR mà source cần đọc type/ABI của nó.
- **Processor/plugin dependency:** JAR chứa mã được thực thi bên trong/đi kèm compiler và cần tương thích với JVM thực thi compiler.
- **Runtime dependency:** JAR được đóng gói/chạy cùng ứng dụng và phải tương thích với JVM triển khai.

Một artifact có thể nằm trong nhiều nhóm, nhưng cách phát sinh lỗi không giống nhau. Trên Maven/Gradle, inspect từng configuration (`compileClasspath`, `annotationProcessor`, `runtimeClasspath` hoặc cấu hình tương đương) thay vì kết luận chỉ từ một file JAR trùng tên.

## 9. Maven, Gradle và CI: kiểm soát toolchain/target

Cấu hình **Java release của code được tạo ra** và **JDK thực thi compiler** là hai chiều cần xem riêng.

### Maven

Với `maven-compiler-plugin` đủ mới, ví dụ khai báo:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đây là cấu hình cho compilation của module Maven hiện tại. Nó **không tác động ngược** tới JAR phụ thuộc đã xuất bản. Maven có thể sử dụng toolchains hoặc JDK chạy Maven tùy cấu hình project, vì thế cần xác minh compiler thực tế, dependencies đã resolve và surefire/failsafe runtime.

Một dependency yêu cầu Java 21 vẫn có thể lọt vào dependency graph nếu không có kiểm tra minimum runtime riêng. Dùng cơ chế quản lý version, quy tắc build và test để khóa compatibility.

### Gradle

Ở một dự án Gradle JVM, hai khái niệm thường được dùng:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Đây là **snippet cấu hình Gradle Groovy DSL**, không phải một tệp Java độc lập. Cấu hình toolchain chọn JDK 17 cho Java compilation trong các tác vụ được quản lý phù hợp; `options.release` chọn target 17 của `javac`. Toolchains, Gradle version và task cụ thể có thể yêu cầu cấu hình riêng; không mặc định mọi external plugin hoặc test process sẽ dùng đúng toolchain nếu chưa kiểm chứng.

Nếu JavaCompile thật sự dùng **JDK 17**, một dependency major 65 trên compile classpath sẽ làm compiler từ chối như mục 4.2. Điều đó **giúp phát hiện lỗi sớm**, nhưng muốn đảm bảo toàn bộ runtime dependency graph tương thích vẫn cần test/kiểm tra các artifact.

### CI: kiểm chứng tối thiểu có giá trị

Một pipeline nhắm Java 17 nên:

1. **Xác định runtime tối thiểu** được sản phẩm hứa hỗ trợ; ví dụ Java 17.
2. Dùng toolchain tương thích hoặc biên dịch với `--release 17` trên compiler mới đủ khả năng.
3. Rà dependency graph và class-file versions, bao gồm transitive dependencies và các artifact có multi-release layout.
4. **Chạy integration/smoke tests bằng chính JVM Java 17** sau khi đóng gói. Test chỉ bằng JDK 21 không chứng minh chạy được trên JDK 17.
5. Xác minh image/container/server runtime thật sự là Java 17; một base image vô tình nâng lên Java 21 có thể che lỗi cho đến khi triển khai ở môi trường khác.
6. Ghi log `java -version`, `javac -version` và versions của dependencies để tái lập lỗi.

**Test trên Java tối thiểu là bước bổ sung thiết yếu.** Kiểm tra major version là quan trọng nhưng chưa đủ: class file 61 vẫn có thể tham chiếu đến API/thư viện vắng mặt hoặc khác ABI ở runtime.

## 10. Checklist điều tra thực tế theo thứ tự

Khi gặp lỗi biên dịch một dependency được tạo bởi JDK mới hơn:

**Bước 1 — Đọc lỗi đầy đủ.** Có `wrong version N.0` không? Cần phân biệt đây là compiler error, linker error hay exception runtime.

**Bước 2 — Kiểm tra công cụ.**

```sh
javac -version
java -version
```

Nếu build tool có toolchain riêng, xem task log hoặc cấu hình thay vì chỉ tin `java` trong terminal.

**Bước 3 — Xác định đúng JAR/class đang được chọn.** Kiểm tra compile classpath/module path, runtime classpath/module path, transitive dependencies, shaded packages và class loader nếu có nhiều bản thư viện.

**Bước 4 — Xem header class thực tế.** Dùng `javap -verbose` của JDK phù hợp để đọc major/minor. Với multi-release JAR, biết entry nào được lựa chọn.

**Bước 5 — So sánh ba con số.** Compiler JDK hỗ trợ tới đâu? Dependency major bao nhiêu? JVM đích hỗ trợ major bao nhiêu? Nhớ rằng `--release` không thay dependency.

**Bước 6 — Chọn một cách sửa có thể duy trì.** Hạ version thư viện, rebuild bằng `--release` phù hợp, chọn MR-JAR đúng, hay nâng minimum Java của ứng dụng. Không chỉnh bytes class file thô.

**Bước 7 — Biên dịch và chạy lại từ output sạch được quản lý.** Tránh nhầm class cũ hoặc JAR cũ. Chỉ làm sạch **thư mục build output thuộc quyền sở hữu dự án**, không xóa source hoặc dữ liệu chưa xác định.

**Bước 8 — Kiểm thử bản đóng gói cuối.** Một class ở `build/classes` không đại diện chắc chắn nội dung của JAR/container cuối cùng. Kiểm tra artifact đã publish/deploy và chạy trên JVM mục tiêu.

## 11. Các hiểu nhầm cần loại bỏ

**“`--release 17` biến mọi dependency thành Java 17.”** Sai. Nó áp dụng cho mã nguồn đang được compiler biên dịch và API nền tảng mục tiêu; không rewrite JAR.

**“Thư viện được build bằng JDK 21 chắc chắn là Java 21-only.”** Không nhất thiết. Nếu tác giả dùng `--release 17`, class file tạo ra có thể là major 61. Phải đọc artifact thật.

**“Mã app có major 61 nên ứng dụng chạy được trên Java 17.”** Chưa đủ. Dependency major 65, ABI mới hoặc API Java 21 vẫn có thể làm fail.

**“Nâng `javac` là chữa xong lỗi Java 17.”** Chỉ có thể chữa bước compiler không hiểu class file mới. Nếu runtime vẫn là Java 17, class mới vẫn không được nạp.

**“Đổi minor/major bytes trong `.class` là downcompile.”** Sai. Có thể làm class file hỏng hoặc gặp instruction/metadata/API không hỗ trợ.

**“Mọi `UnsupportedClassVersionError` đều xảy ra lúc startup.”** Không bắt buộc. Class có thể chỉ được tải khi nhánh code liên quan chạy, nên lỗi có thể xuất hiện muộn.

**“Class-file version thấp chứng minh mọi API đều tương thích.”** Không. Có thể phát sinh `NoSuchMethodError`/`NoClassDefFoundError` do API/ABI runtime khác, kể cả khi major hợp lệ.

**“JDK mới luôn chạy được mọi class cũ trong mọi hoàn cảnh.”** Tương thích hướng lên là mục tiêu chung, nhưng preview class files, API đã thay đổi, security/module encapsulation và thay đổi runtime có các điều kiện riêng. Kiểm thử trên JVM thực tế vẫn cần thiết.

## 12. Bảng quyết định nhanh

| Hiện trạng | Có thể compile? | Có thể chạy Java 17? | Hành động |
| --- | --- | --- | --- |
| JDK 17 compiler + dependency major 65 | Không, nếu cần đọc class đó | Không | Dùng dependency Java 17 hoặc rebuild |
| JDK 21 compiler `--release 17` + dependency major 65 | Có thể | **Không** nếu runtime phải nạp class 65 | Không dựa vào compile-pass; sửa dependency/runtime |
| JDK 21 compiler `--release 17` + dependency major 61 | Có thể | Có thể, nếu APIs và các dependency khác phù hợp | Test bằng Java 17 |
| JDK 17 compiler + dependency major 61 | Có thể, nếu API/ABI hợp lệ | Có thể, nếu runtime graph phù hợp | Test từ artifact đóng gói |
| JDK 21 compiler/runtime + dependency major 65 | Có thể | Không áp dụng mục tiêu Java 17 | Công bố minimum Java 21 nếu sản phẩm chấp nhận |

Từ **“có thể”** là chủ ý: class-file version chỉ là một điều kiện cần. Module graph, visibility, APIs, annotation processors, JNI/native code và thực tế build cũng có thể ảnh hưởng.

**Điểm cần ghi nhớ:** Việc ứng dụng **biên dịch cho Java 17** và việc **toàn bộ thư viện đi kèm thực sự hỗ trợ Java 17** là hai kiểm tra khác nhau. Xác minh version từ artifact, khóa toolchain/dependency, và chạy bản đóng gói cuối bằng **JVM tối thiểu** mà sản phẩm cam kết hỗ trợ.

## Tài liệu tham khảo chính thức

- Oracle, *The javac Command* (JDK 21), `--release`, `--class-path` và *Compiling for Earlier Releases*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java Virtual Machine Specification 17, `4.1, *The ClassFile Structure* (major/minor version): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Oracle Java SE 17 API, `UnsupportedClassVersionError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html
- Oracle Java SE 17, *JAR File Specification*, multi-release JAR: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Oracle, *Preparing for Migration* (JDK 24), thông tin về `--release` và tương thích class files: https://docs.oracle.com/en/java/javase/24/migrate/preparing-migration.html