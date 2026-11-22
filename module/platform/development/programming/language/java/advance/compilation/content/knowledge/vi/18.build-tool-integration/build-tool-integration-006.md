# Tệp `.class` cũ, hằng số được nhúng và rủi ro của đầu ra thiếu cập nhật

## 1. Vấn đề thực tế

Khi chỉnh sửa mã Java, việc lưu tệp `.java` không làm cho chương trình đang chạy tự nhận thay đổi. `javac` biên dịch mã nguồn thành tệp `.class`; công cụ build đóng gói các tệp đó thành JAR/WAR hoặc thư mục đầu ra; JVM sau đó nạp lớp từ *artifact* nằm trên classpath/module path. Vì thế, chương trình có thể chạy thành công nhưng hành xử như phiên bản cũ nếu một mắt xích vẫn chứa bytecode cũ.

Đặc biệt nguy hiểm là **hằng số được nhúng khi biên dịch** (*compile-time constant inlining*). Một ứng dụng đã được biên dịch có thể tiếp tục in giá trị cũ của hằng số do thư viện cung cấp, dù tệp `.class` của thư viện đã được biên dịch lại và JVM thực sự đang nạp bản thư viện mới. Đây là hành vi theo đặc tả ngôn ngữ Java, không nhất thiết là lỗi của JVM hay cache.

Sau bài này, bạn cần phân biệt được ba tình huống thường bị gọi chung là “build không cập nhật”:

| Hiện tượng | Bản cũ nằm ở đâu? | Bước kiểm chứng hữu ích |
| --- | --- | --- |
| Tệp `.class` đầu ra vẫn là bản cũ | Thư mục biên dịch hoặc artifact chưa được tạo lại | Kiểm tra timestamp/hash, `javap` và nội dung JAR |
| Thư viện đã mới nhưng ứng dụng vẫn dùng hằng số cũ | Giá trị đã được đưa thẳng vào bytecode của **lớp gọi** khi lớp gọi được biên dịch trước đây | `javap -c` lớp gọi, sau đó biên dịch lại lớp gọi |
| Artifact mới tồn tại nhưng runtime nạp bản khác | Classpath/module path, dependency phiên bản cũ, image triển khai cũ hoặc JVM chưa khởi động lại | Xác định vị trí lớp thực tế được nạp và phiên bản artifact |

Cách xử lý phải dựa trên vị trí của bytecode hoặc giá trị cũ. “Chạy lại một lệnh build” có thể chưa đủ nếu phần phụ thuộc, bản đóng gói hoặc môi trường thực thi vẫn chưa đồng bộ.

## 2. Từ mã nguồn đến lớp mà JVM sử dụng

Một luồng build đơn giản:

```text
BuildInfo.java --javac--> build/lib/demo/BuildInfo.class --đóng gói--> library.jar
Client.java    --javac--> build/app/demo/Client.class  --đóng gói--> app.jar
                                                                   |
                                        runtime classpath/module path
                                                                   |
                                                         JVM nạp các lớp
```

Ở bước biên dịch, `Client.java` cần nhìn thấy API của `BuildInfo`, thông qua mã nguồn hoặc bytecode có trên compile classpath. Sau biên dịch, `Client.class` là một đầu ra độc lập: chạy `Client.class` không đồng nghĩa JVM sẽ biên dịch lại `Client.java`.

Một số nguyên nhân thường tạo đầu ra thiếu cập nhật:

- Chỉ biên dịch lại thư viện, không biên dịch lại các lớp ứng dụng có phụ thuộc.
- Build tăng dần nhận diện thiếu một quan hệ phụ thuộc, hoặc dùng cache/đầu ra sinh từ cấu hình cũ.
- Tệp nguồn được đổi tên/xóa, nhưng tệp `.class` cũ vẫn tồn tại trong thư mục đầu ra vì bước compile không tự dọn các lớp đã mất.
- JAR mới được tạo nhưng bước chạy/deploy vẫn trỏ tới JAR, thư mục, container image hoặc dependency phiên bản trước.
- Có nhiều bản của cùng một lớp trên classpath; thứ tự phân giải khiến JVM dùng bản không mong muốn.
- Thay đổi tệp JAR trên đĩa trong khi JVM đang chạy; lớp đã nạp vẫn ở trong JVM/class loader hiện tại, trừ khi có cơ chế nạp lại lớp chuyên biệt.

**Không thể kết luận “có lỗi source code” chỉ từ việc kết quả chạy không đổi.** Trước tiên phải xác định `.class` nào đã biên dịch, được đóng gói, và được nạp.

## 3. Hằng số nào bị nhúng khi biên dịch?

Theo Java Language Specification (JLS `4.12.4 và `15.29), *constant variable* là biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng một biểu thức hằng tại thời điểm biên dịch. Các trường `public static final` thuộc loại này thường được javac thay bằng giá trị ngay tại nơi sử dụng.

```java
public final class Constants {
    public static final int PORT = 8080;          // Hằng số biên dịch
    public static final String REGION = "apac";    // Hằng số biên dịch
    public static final int LIMIT = 10 * 2;        // Hằng số biên dịch

    public static final int FROM_METHOD = load();  // Không phải hằng số biên dịch
    public static final Integer BOXED = 20;        // Integer không phải kiểu primitive/String
    public static final String COPY = new String("apac"); // Không phải biểu thức hằng

    private static int load() {
        return 20;
    }
}
```

Ba trường đầu có thể được nhúng trong bytecode của lớp sử dụng. Ba trường sau vẫn là trường cần đọc lúc thực thi (trừ các tối ưu runtime riêng biệt không thay đổi quy tắc tương thích nhị phân). `static final` **không** đồng nghĩa với “luôn được nhúng”; điều kiện quyết định là kiểu và biểu thức khởi tạo có đáp ứng định nghĩa *constant variable* hay không. Trường hằng của `interface` cũng cần chú ý vì mặc định là `public static final`.

Một trình biên dịch có thể sinh lệnh tải literal như `iconst_1` hoặc `ldc`, và có thể gộp phép nối chuỗi với hằng số thành một literal duy nhất. Trong tình huống đó, bytecode của lớp gọi **không cần thực hiện `getstatic`** để lấy giá trị mới từ lớp định nghĩa hằng số.

Hệ quả quan trọng:

1. Đổi `public static final int VERSION = 1` thành `... = 2` và biên dịch lại **chỉ** lớp khai báo không bắt buộc làm lớp gọi đang tồn tại thấy số 2.
2. Sự thay đổi giá trị này có thể vẫn **tương thích nhị phân**: chương trình không ném lỗi liên kết, nhưng dùng logic lỗi thời. “Chạy được” không chứng minh “đúng phiên bản”.
3. Việc đọc một hằng số nhúng thậm chí có thể không kích hoạt khởi tạo lớp khai báo tại runtime. Không nên suy ra lớp đã được nạp hoặc chạy `<clinit>` chỉ vì mã nguồn có tham chiếu `Constants.PORT`.
4. Các trường dùng trong `case` label hoặc giá trị annotation có yêu cầu biểu thức hằng riêng; không thể tùy tiện thay chúng bằng lời gọi phương thức runtime.

## 4. Thí nghiệm tái hiện: thư viện mới, ứng dụng vẫn in hằng số cũ

Dùng Java 17 trở lên, tạo cấu trúc sau trong một thư mục thử nghiệm riêng:

```text
src/
  demo/
    BuildInfo.java
    Client.java
build/
  lib/             (do javac tạo)
  app/             (do javac tạo)
```

**Tệp `src/demo/BuildInfo.java` — phiên bản 1:**

```java
package demo;

public final class BuildInfo {
    public static final int FORMAT = 1;
    public static final String CHANNEL = "alpha";

    private BuildInfo() { }

    public static int runtimeFormat() {
        return 1;
    }
}
```

**Tệp `src/demo/Client.java`:**

```java
package demo;

public final class Client {
    public static void main(String[] args) {
        System.out.println("FORMAT=" + BuildInfo.FORMAT);
        System.out.println("CHANNEL=" + BuildInfo.CHANNEL);
        System.out.println("runtimeFormat=" + BuildInfo.runtimeFormat());
    }
}
```

Trong PowerShell, chạy từ thư mục chứa `src`:

```powershell
New-Item -ItemType Directory -Force build/lib, build/app | Out-Null
javac -d build/lib src/demo/BuildInfo.java
javac -cp build/lib -d build/app src/demo/Client.java
java -cp "build/app;build/lib" demo.Client
```

Kết quả lần 1:

```text
FORMAT=1
CHANNEL=alpha
runtimeFormat=1
```

Bây giờ **chỉ sửa `BuildInfo.java`**: đổi `FORMAT = 2`, `CHANNEL = "beta"` và `return 2;`. Nội dung hoàn chỉnh sau sửa là:

```java
package demo;

public final class BuildInfo {
    public static final int FORMAT = 2;
    public static final String CHANNEL = "beta";

    private BuildInfo() { }

    public static int runtimeFormat() {
        return 2;
    }
}
```

**Chỉ biên dịch lại thư viện**, giữ nguyên `build/app/demo/Client.class`:

```powershell
javac -d build/lib src/demo/BuildInfo.java
java -cp "build/app;build/lib" demo.Client
```

Kết quả lần 2:

```text
FORMAT=1
CHANNEL=alpha
runtimeFormat=2
```

Đây là kết quả đúng theo cơ chế biên dịch:

- `Client.class` được biên dịch từ lúc `FORMAT` bằng 1 và `CHANNEL` bằng `"alpha"`; các literal cũ nằm trong bytecode của nó.
- Lời gọi `BuildInfo.runtimeFormat()` là lời gọi phương thức khi chạy, nên JVM thực thi phương thức mới trả 2.
- Không cần giả định JVM nạp nhầm `BuildInfo.class`: cùng một lần chạy đã đọc được logic mới của phương thức, nhưng vẫn sử dụng hai hằng số cũ.

Xem bằng `javap`:

```powershell
javap -classpath build/app -c demo.Client
javap -classpath build/lib -verbose demo.BuildInfo
```

Trong phần bytecode của `Client.main`, bạn sẽ thấy các literal tương đương `"FORMAT=1"` và `"CHANNEL=alpha"` (javac có thể gộp phép nối chuỗi ngay lúc biên dịch), trong khi lời gọi `runtimeFormat()` là một lệnh `invokestatic`. Trong thông tin của `BuildInfo` mới, các trường hằng có thuộc tính `ConstantValue` chứa 2 và `"beta"`. Chi tiết mã lệnh/constant-pool có thể khác giữa các phiên bản compiler; điều cốt lõi là **literal cũ nằm trong `Client.class`**.

Cuối cùng, **biên dịch lại lớp gọi**:

```powershell
javac -cp build/lib -d build/app src/demo/Client.java
java -cp "build/app;build/lib" demo.Client
```

Kết quả lần 3:

```text
FORMAT=2
CHANNEL=beta
runtimeFormat=2
```

Thí nghiệm dùng dấu `;` làm dấu phân tách classpath theo Windows/PowerShell. Trên Linux/macOS, thay bằng dấu `:`, ví dụ `java -cp "build/app:build/lib" demo.Client`. Các lệnh tạo thư mục cũng có thể thay bằng `mkdir -p build/lib build/app`.

### Vì sao một số lần chạy lại cho kết quả khác?

Nếu bạn dùng lệnh `javac` không kiểm soát source path/classpath, compiler có thể tìm thấy nguồn phụ thuộc và tự biên dịch nó. Thí nghiệm ở trên cố ý tách đầu ra thư viện và ứng dụng để kiểm soát chính xác lớp nào được biên dịch lại. Theo hướng dẫn `javac`, khi cả source lẫn class tồn tại trên các đường tìm kiếm, quyết định dùng source hay class còn phụ thuộc đường dẫn và quy tắc lựa chọn nguồn. Vì vậy, hãy dùng `-d`, `-cp`, `-sourcepath` khi cần và kiểm tra các lệnh build thật được thực thi; đừng suy luận chỉ dựa vào thời điểm sửa tệp.

## 5. Cũ ở bytecode, cũ ở classpath hay cũ ở JVM?

### 5.1. Tệp `.class` mồ côi trong thư mục đầu ra

Giả sử bản cũ có `src/demo/LegacyTool.java`, sau đó bạn đổi tên nguồn thành `ModernTool.java`. Chạy `javac -d build/classes src/demo/ModernTool.java` sẽ tạo `ModernTool.class`; lệnh này **không tự xóa** `build/classes/demo/LegacyTool.class` đã tạo từ lần trước. Nếu bộ đóng gói quét toàn bộ thư mục đầu ra, artifact có thể vẫn chứa `LegacyTool.class`.

Tương tự, khi xóa một nested class, đổi tên package hay thay code generator, các tệp phát sinh cũ có thể vẫn sót. Chúng không nhất thiết được JVM nạp, nhưng là rủi ro đáng kiểm tra vì làm artifact chứa bytecode ngoài ý muốn.

Cách xử lý là dọn **đúng thư mục đầu ra do build sở hữu** rồi compile/package lại. Không xóa bừa thư mục nguồn hoặc output đang chia sẻ với bước khác. Với công cụ build có tác vụ `clean`, dùng tác vụ chuẩn của dự án trước khi build lại nếu nghi ngờ tệp mồ côi.

### 5.2. Compile classpath khác runtime classpath

Một module có thể biên dịch với `lib-v2.jar` nhưng lúc chạy lại dùng `lib-v1.jar`; hoặc ngược lại, có hai JAR chứa cùng tên lớp và bản cũ được tìm thấy trước. Khi đó không phải do *constant inlining* đơn thuần: mã chạy đang liên kết với một lớp/thư viện khác so với dự kiến.

Để xác định nguồn lớp khi chạy Java 17+:

```powershell
java -Xlog:class+load=info -cp "build/app;build/lib" demo.Client
```

Log có thể rất dài; lọc tên lớp cần tìm khi điều tra. Trong một chương trình chẩn đoán, có thể in nguồn bytecode của lớp bằng:

```java
System.out.println(
    BuildInfo.class.getProtectionDomain().getCodeSource()
);
```

Đoạn này là **mã minh họa cần đặt vào phương thức**, không phải chương trình Java chạy độc lập. `CodeSource` có thể là `null` trong một số môi trường (ví dụ lớp được nạp đặc biệt); không xem nó là bằng chứng tuyệt đối cho mọi loader.

### 5.3. Artifact đã mới nhưng tiến trình vẫn cũ

Khi tiến trình JVM đã nạp một lớp, thay JAR trên đĩa không tự thay bytecode đang chạy. Bạn thường phải triển khai lại phiên bản đã đóng gói và khởi động lại tiến trình hoặc dùng cơ chế reload được thiết kế rõ ràng. Cần xác minh JAR thực sự có trong container/image, server đang dùng đường dẫn nào và tiến trình có được khởi động từ artifact mới hay không.

Đừng nhầm điều này với lỗi hằng số: **khởi động lại riêng JVM vẫn có thể in `FORMAT=1`** nếu `Client.class` chưa được biên dịch lại; khởi động lại không thể xóa literal đã được nhúng trong bytecode của client.

## 6. Tương thích nhị phân: không lỗi liên kết vẫn có thể sai

JLS `13 mô tả tính tương thích nhị phân của lớp đã biên dịch. Với trường `static` là *constant variable*, việc thay đổi giá trị hằng số hoặc bỏ `final` có thể không làm binary client cũ mất khả năng chạy; binary client đó vẫn giữ giá trị đã nhúng đến khi được biên dịch lại.

Phân biệt hai họ lỗi:

| Thay đổi | Binary client cũ có thể gặp gì? |
| --- | --- |
| Đổi giá trị `public static final int LIMIT = 10` thành 20 | Thường chạy bình thường nhưng vẫn đọc 10 nếu đã nhúng |
| Xóa hoặc đổi chữ ký một phương thức đang được gọi | Có thể sinh `NoSuchMethodError` khi liên kết/lời gọi xảy ra |
| Xóa trường mà bytecode client thực sự truy cập bằng `getstatic`/`getfield` | Có thể sinh `NoSuchFieldError` |
| Chuyển trường từ `static` sang instance hoặc ngược lại | Có thể sinh `IncompatibleClassChangeError` |
| Đổi hằng số thành giá trị khác nhưng client cũ không chứa tham chiếu trường runtime | Có thể không xuất hiện lỗi nào, chỉ sai kết quả |

Bảng mô tả các trường hợp điển hình; lỗi chính xác còn tùy bytecode mà client đã biên dịch và thay đổi API cụ thể. Không nên áp dụng nhận định “xóa trường luôn làm mọi client cũ lỗi” cho các lệnh đã nhúng literal, vì có thể không còn tham chiếu trường ở runtime.

Tính tương thích **mã nguồn** (biên dịch lại được hay không), **nhị phân** (binary cũ có liên kết/chạy được không) và **ngữ nghĩa** (chạy ra kết quả đúng không) là ba câu hỏi khác nhau. Một thay đổi có thể vượt qua hai câu đầu nhưng thất bại ở câu cuối.

## 7. Build tăng dần, cache và biên dịch phụ thuộc

Các hệ thống build như Gradle/Maven có chiến lược xác định tác vụ nào phải chạy và file nào có thể tái sử dụng. Incremental compilation, build cache và dependency resolution giúp tiết kiệm thời gian, nhưng cần cấu hình phụ thuộc và đầu vào chính xác. Không nên kết luận mọi incremental compiler đều xử lý sai constant inlining: một số công cụ có cơ chế theo dõi các hằng số ảnh hưởng đến lớp phụ thuộc và kích hoạt biên dịch cần thiết.

Vấn đề vẫn có thể xuất hiện khi:

- Client và thư viện được build, lưu cache, phát hành hoặc triển khai bằng **hai pipeline độc lập**.
- Dependency đã thay đổi ở thư viện ngoài nhưng client artifact không được build/phát hành lại.
- Một tác vụ tùy biến không khai báo đầy đủ input/output, hoặc output cũ không được dọn.
- Build local dùng bản thư viện mới trong khi CI/deployment resolve về bản cũ, hoặc dùng cùng version cho artifact khác nội dung.
- Cùng tên lớp xuất hiện ở nhiều dependency và kết quả phân giải khác nhau giữa compile/runtime.

Đối với Gradle, hãy kiểm tra dependency graph, task đã thực thi hay `UP-TO-DATE`/`FROM-CACHE`, cấu hình Java compilation và nội dung artifact. Đối với Maven, xác minh các dependency versions, phase compile/package và output tại `target/classes`. **Không áp đặt `clean` cho mọi build**: nó là bước chẩn đoán hoặc phục hồi hữu ích khi nghi ngờ output lỗi thời, còn sửa căn nguyên cần điều chỉnh đúng dependency, input/output, version hoặc quy trình phát hành.

## 8. Quy trình chẩn đoán có thể lặp lại

Khi “đã đổi source nhưng kết quả vẫn cũ”, thực hiện theo thứ tự sau để khoanh vùng:

1. **Chốt hiện tượng.** Ghi lại expected/actual, lệnh build/run, JDK, branch, commit, dependency versions và artifact đang chạy. Dùng một thay đổi dễ nhận biết để kiểm chứng.
2. **Xác định lớp đang dùng.** Kiểm tra classpath/module path, resolved dependencies, JAR thực tế và log tải lớp. Với JAR, lệnh `jar tf path/to/library.jar` liệt kê tên entry; với bản đã đóng gói, dùng `javap -classpath path/to/library.jar -verbose demo.BuildInfo` để xem bytecode thật.
3. **So sánh lớp cung cấp và lớp gọi.** Xem `javap -c` client để tìm literal cũ hoặc lệnh `getstatic`/`invokestatic`; xem `ConstantValue` trong lớp định nghĩa nếu có. Nếu literal nằm trong client, chỉ cập nhật library là chưa đủ.
4. **Biên dịch/đóng gói lại phần bị ảnh hưởng.** Đồng bộ dependency, biên dịch lại các client phụ thuộc hằng số, sau đó dựng artifact nhất quán. Nếu nghi output mồ côi hoặc cache đầu vào sai, dùng clean build của đúng module và kiểm tra lại kết quả.
5. **Kiểm tra artifact sau build.** Xem entry JAR, bytecode, version/build identifier, hash khi cần. Việc build thành công không bảo đảm chương trình chạy artifact đó.
6. **Kiểm tra triển khai.** Đảm bảo tiến trình/container/worker thật sự chạy bản đã xác minh; khởi động lại khi cần. Chạy lại test/đối chiếu log trên chính artifact sẽ triển khai.
7. **Tìm nguyên nhân gốc.** Tại sao dependency, output, cache hoặc release không được cập nhật? Ghi nhận và sửa ở build graph, tác vụ hoặc release process để không tái diễn.

Ví dụ các lệnh kiểm tra nhanh, thay tên đường dẫn theo dự án:

```powershell
javac -version
java -version
javap -classpath build/app -c demo.Client
javap -classpath build/lib -verbose demo.BuildInfo
Get-FileHash build/lib/demo/BuildInfo.class
Get-FileHash build/app/demo/Client.class
```

Nếu sử dụng JAR:

```powershell
jar tf path/to/library.jar
javap -classpath path/to/library.jar -verbose demo.BuildInfo
```

Không dùng chỉ timestamp để khẳng định hai binary giống/khác nhau: file copy, filesystem và build cache có thể làm timestamp gây hiểu nhầm. Hash hỗ trợ so sánh nội dung, còn `javap` giải thích ý nghĩa bytecode.

## 9. Thiết kế API và chiến lược phòng ngừa

### 9.1. Chỉ dùng compile-time constant cho giá trị thật sự ổn định

Các hằng số mang ý nghĩa bất biến theo API, chẳng hạn mã định danh giao thức đã cố định hoặc giá trị toán học, có thể phù hợp để công khai bằng `public static final`. Nhưng nếu giá trị có thể thay đổi theo phiên bản, môi trường hoặc cấu hình, công khai nó như một compile-time constant sẽ tạo rủi ro stale client.

Ví dụ, thay vì dùng `public static final int CURRENT_FORMAT = 1` nếu số này thường xuyên được cập nhật giữa các bản phát hành, có thể chuyển sang accessor:

```java
package demo;

public final class FormatPolicy {
    private FormatPolicy() { }

    private static final int CURRENT_FORMAT = 2;

    public static int currentFormat() {
        return CURRENT_FORMAT;
    }
}
```

Client dùng `FormatPolicy.currentFormat()` và gọi phương thức trên bản thư viện được nạp lúc chạy. Giá trị hằng có thể được tối ưu **bên trong** chính thư viện, nhưng client gọi phương thức không bị nhúng số 2 vào bytecode của nó theo cơ chế constant-variable field access. Tất nhiên, thay đổi signature phương thức hoặc triển khai nhầm JAR vẫn có thể gây lỗi; accessor không thay thế việc kiểm soát version.

Nếu cần cấu hình theo môi trường, ưu tiên đọc từ một nguồn cấu hình runtime có quy trình quản lý và kiểm thử rõ ràng. Không dùng `static final` chỉ để “bắt code ngắn hơn” khi giá trị có nhu cầu cập nhật thường xuyên.

### 9.2. Phát hành cùng một tập phiên bản đã kiểm tra

- Khai báo dependency trực tiếp, rõ version và quy tắc resolve; tránh tái sử dụng cùng version cho các binary khác nhau.
- Nếu đổi giá trị hằng số public mà client phụ thuộc vào, biên dịch lại, kiểm thử và phát hành client phù hợp, đặc biệt ở biên giới nhiều repository/service hoặc SDK cho bên thứ ba.
- Đưa build identifier (version/commit) vào artifact hoặc log khởi động, và kiểm tra nó ở runtime khi điều tra.
- Làm cho CI tạo artifact từ đầu vào có thể truy vết; kiểm tra nội dung JAR sau khi đóng gói và chạy smoke/integration test dùng **artifact thực tế**.
- Cấu hình input/output cho tác vụ build tùy biến chính xác để cache/incremental build hoạt động đáng tin; cân nhắc clean build khi cần chứng minh tính tái lập.

### 9.3. Kiểm thử đúng ranh giới thay đổi

Một unit test biên dịch chung nguồn mới có thể không lộ lỗi vì tất cả lớp đều được build lại. Với thư viện dùng bởi client đã phát hành, nên có bài kiểm thử tương thích: biên dịch client bằng thư viện phiên bản cũ, thay thư viện runtime bằng phiên bản mới, rồi quan sát hành vi; sau đó biên dịch lại client và so sánh. Thí nghiệm mục 4 là phiên bản tối giản của phép kiểm tra này.

Không sửa API chỉ để tránh lỗi build nếu bản thân hằng số phải được dùng trong `switch case` hoặc annotation và bắt buộc là compile-time constant: trong trường hợp đó, hãy coi việc đồng bộ/recompile client là một phần của hợp đồng thay đổi.

## 10. Tự kiểm tra hiểu bài

**Tình huống A:** `Library.VERSION` là `public static final int VERSION = 1`, bạn đổi thành 2 và build lại thư viện. Một chương trình cũ vẫn in 1, nhưng lời gọi phương thức mới của thư viện chạy đúng. Nguyên nhân khả dĩ nhất?  
**Đáp án:** Giá trị 1 đã được nhúng trong binary của chương trình cũ; cần biên dịch lại lớp dùng hằng số và phát hành/deploy artifact đó.

**Tình huống B:** Bạn xóa tệp `Obsolete.java`, build lại một số nguồn, nhưng `Obsolete.class` vẫn có trong JAR. Vì sao?  
**Đáp án:** Đầu ra compile trước đó còn trong thư mục đóng gói; compile mới không có nghĩa tự dọn tất cả file class mồ côi. Dọn output build-owned đúng cách và đóng gói lại.

**Tình huống C:** `public static final String NAME = System.getenv("NAME");` có được xem là constant variable không?  
**Đáp án:** Không; lời gọi phương thức không phải biểu thức hằng lúc biên dịch. Giá trị được gán khi lớp khởi tạo, và client truy cập trường qua cơ chế runtime (giá trị còn tùy thời điểm khởi tạo và môi trường).

**Tình huống D:** Khởi động lại JVM có luôn sửa được giá trị hằng số cũ không?  
**Đáp án:** Không. Nếu `Client.class` đã nhúng literal cũ thì JVM mới vẫn chạy bytecode cũ. Phải xác nhận client được biên dịch và triển khai lại.

**Tình huống E:** Một thay đổi “binary compatible” có bảo đảm hành vi business logic đúng không?  
**Đáp án:** Không. Thay đổi hằng số public có thể không gây lỗi linkage nhưng khiến client cũ dùng giá trị sai.

## 11. Ghi nhớ

- `.java` là nguồn; `.class`/JAR là thứ được dùng để chạy. Phải theo dõi cả **compile output → package → runtime**.
- `final` và `static final` không tự động có nghĩa là hằng số được nhúng; kiểm tra **constant variable** theo JLS.
- Đổi giá trị một compile-time constant có thể buộc **biên dịch lại client**, dù thư viện mới đã được nạp.
- Class mồ côi, dependency cũ, classpath lệch và tiến trình chưa restart là các nguyên nhân khác nhau, cần chẩn đoán riêng.
- Dùng `javap`, danh sách entry của JAR, log nạp lớp và test trên artifact thực tế để xác nhận; chỉ dùng `clean` khi có lý do và sửa căn nguyên nếu lỗi lặp lại.

### Tài liệu chuẩn

- [JLS `4.12.4 — final variables, constant variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4)
- [JLS `13.4.9 — final fields và static constant variables, tương thích nhị phân](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9)
- [JLS `15.29 — constant expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29)
- [Tài liệu lệnh javac (Java 21): classpath, source path và đầu ra -d](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
