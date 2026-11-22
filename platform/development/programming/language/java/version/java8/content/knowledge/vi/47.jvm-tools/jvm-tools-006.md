# jdeps và tìm phụ thuộc API nội bộ trong Java

## 1. jdeps dùng để làm gì?

`jdeps` là công cụ phân tích phụ thuộc của class Java, được cung cấp trong JDK. Công cụ đọc các file `.class`, thư mục chứa class hoặc JAR để xác định class/package/module mà chương trình tham chiếu. Một trường hợp sử dụng quan trọng là tìm các phụ thuộc vào **JDK internal APIs** — những API thuộc phần triển khai nội bộ của JDK và không có cam kết ổn định như Java SE APIs.

Lệnh trọng tâm:

```bash
jdeps --jdk-internals path/to/application.jar
```

`--jdk-internals` yêu cầu jdeps tìm các phụ thuộc ở cấp class tới JDK internal APIs. Kết quả thường cho biết class nào tham chiếu API nội bộ nào và module JDK chứa API đó. Công cụ cũng có thể gợi ý replacement khi biết mapping tương ứng.

`jdeps` hữu ích khi nâng JDK, kiểm tra thư viện bên thứ ba, chuẩn bị ứng dụng cho module system/strong encapsulation, hoặc đưa kiểm tra tương thích vào CI. Nó là **static dependency analyzer**: đọc quan hệ trong bytecode, không chạy ứng dụng để quan sát mọi đường thực thi. Vì vậy kết quả là một phần quan trọng của kiểm tra, không thay thế runtime tests.

Bài thuộc chủ đề cha **“JVM và công cụ”**, đề bài trực tiếp **“jdeps và tìm phụ thuộc API nội bộ”**. Nội dung tập trung vào các option còn được hỗ trợ trong JDK hiện đại, cách quét ứng dụng và thư viện, giới hạn static analysis, cách xử lý kết quả và các thay thế API đang được khuyến nghị.

### Mục tiêu học tập

1. Hiểu JDK internal API là gì và vì sao phụ thuộc vào chúng có rủi ro.
2. Phân biệt Java SE API, JDK-specific API được hỗ trợ và internal implementation API.
3. Dùng `jdeps --jdk-internals` để tìm phụ thuộc nội bộ.
4. Quét class, thư mục class, JAR và ứng dụng có dependency.
5. Hiểu vai trò của class path, module path, recursive analysis và multi-release JAR.
6. Đọc kết quả, module đích và suggested replacement.
7. Biết những gì jdeps không phát hiện, đặc biệt reflection và tên class được tạo động.
8. Hiểu strong encapsulation từ JDK 17 và vì sao `--illegal-access` không còn là cách khắc phục.
9. Phân biệt `--add-exports` với `--add-opens` khi phải duy trì workaround tạm thời.
10. Thay internal API bằng API chuẩn như `VarHandle` hoặc Foreign Function & Memory API khi phù hợp.
11. Gọi jdeps bằng command line hoặc `ToolProvider`.
12. Tích hợp report vào build/CI mà không hiểu sai exit code.

## 2. JDK internal API và lý do nên tìm chúng

Java cung cấp các API được định nghĩa trong Java SE, ví dụ `java.lang`, `java.util`, `java.nio` và `java.time`. Hợp đồng của những API này được đặc tả và duy trì theo quy tắc tương thích của nền tảng.

JDK cũng cần các class/method để triển khai JVM, class loading, garbage collection, compiler, networking, reflection và memory management. Một số class nằm trong package như `jdk.internal.*`, `sun.*` hoặc package đặc thù của implementation. Những API này thường **không phải public supported contract** cho ứng dụng.

Một chương trình có thể biên dịch và chạy với một JDK cụ thể khi tham chiếu internal API. Điều đó không có nghĩa API sẽ tồn tại trong JDK tiếp theo, giữ nguyên signature/semantics, tiếp tục được export cho module ứng dụng, hoặc có cùng implementation trên mọi vendor.

### 2.1. Ba nhóm API cần phân biệt

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Java SE API | `java.util.Base64`, `java.lang.invoke.VarHandle` | API chuẩn, có đặc tả công khai |
| JDK-specific API được tài liệu hóa | Một số API mở rộng do JDK cung cấp | Chỉ dùng theo cam kết của tài liệu tương ứng |
| JDK internal API | `jdk.internal.*`, nhiều API `sun.*` | Phụ thuộc chi tiết triển khai; có thể đổi hoặc bị hạn chế |

Không phân loại API chỉ bằng prefix package. Có những package mang tên `com.sun.*` được tài liệu hóa và hỗ trợ cho mục đích cụ thể; không nên kết luận mọi package có prefix đó đều là internal. Dùng kết quả phân tích, tài liệu API và trạng thái export/support của đúng JDK.

### 2.2. Vì sao phụ thuộc nội bộ dễ vỡ khi nâng JDK?

JDK có thể thay đổi cấu trúc bên trong mà không phải giữ tương thích cho ứng dụng sử dụng internal API. Khi nâng JDK, bạn có thể gặp:

- Compile error vì package không còn được export.
- Linkage error như `NoClassDefFoundError` hoặc `NoSuchMethodError`.
- `IllegalAccessError` khi module không được phép truy cập type/member.
- `InaccessibleObjectException` khi reflection cố truy cập thành viên private không được mở.
- Runtime behavior khác nhau giữa vendor hoặc version.
- Cảnh báo deprecation/removal đối với API từng được dùng rộng rãi.

**Một ứng dụng chỉ dùng public Java SE APIs có khả năng tương thích tốt hơn** so với ứng dụng dựa vào chi tiết nội bộ của JDK.

### 2.3. API còn truy cập được không đồng nghĩa được hỗ trợ

Ví dụ quan trọng là `sun.misc.Unsafe`. Class này vẫn còn trong JDK hiện đại và package `sun.misc` không bị strong encapsulation giống nhiều package nội bộ khác. Tuy nhiên, các memory-access methods của `Unsafe` là API không được hỗ trợ, đã deprecated for removal trong JDK 23 và phát cảnh báo runtime khi được gọi từ JDK 24 trở lên. JDK 26 migration guide khuyến nghị chuyển sang API chuẩn như `VarHandle` và Foreign Function & Memory API.

Vì vậy, `jdeps` có thể báo một phụ thuộc ngay cả khi code vẫn biên dịch. Báo cáo nói rằng ứng dụng đang phụ thuộc vào internal API; nó không nhất thiết khẳng định API đó đã bị chặn trong phiên bản hiện tại.

## 3. jdeps phân tích những gì?

`jdeps` đọc bytecode và tạo dependency graph. Đầu vào có thể là:

- Một file `.class`.
- Một thư mục chứa class files.
- Một JAR.
- Một class được chỉ định bằng tên đầy đủ trong ngữ cảnh class path.
- Một module hoặc tập module theo các tùy chọn module analysis.

Công cụ có thể hiển thị phụ thuộc ở nhiều mức: package-level, class-level, archive-level và module-level. `--jdk-internals` tập trung vào **class-level dependencies tới JDK internal APIs**.

### 3.1. Phân tích bytecode, không phải source code

Một file `.java` chưa biên dịch không phải đầu vào thông thường của jdeps. Quy trình:

```text
Java source (.java)
       |
       v
javac
       |
       v
.class files / JAR
       |
       v
jdeps --jdk-internals
       |
       v
Dependency report
```

Hãy chạy build trước khi phân tích. Nếu ứng dụng có nhiều source set, generated classes hoặc module, bảo đảm artifact được quét chứa đúng bytecode sẽ phát hành.

### 3.2. Phụ thuộc gián tiếp từ thư viện

Ứng dụng có thể không import internal API, nhưng một thư viện trong runtime dependency graph lại dùng nó. Khi quét, phải đưa các dependency JAR cần phân tích/resolve vào class path hoặc module path.

```text
application.jar
  +-- logging-library.jar
  +-- bytecode-library.jar
  +-- database-driver.jar
          |
          +-- tham chiếu JDK internal API
```

Nếu chỉ quét một class riêng lẻ mà không cung cấp dependency set thực tế, kết quả có thể thiếu ngữ cảnh. Hãy phân tích artifact ứng dụng cùng các dependency thực sự được triển khai.

### 3.3. Không nhầm jdeps với công cụ khác

| Công cụ | Mục đích chính |
| --- | --- |
| `jdeps` | Phân tích phụ thuộc class/package/module và tìm JDK internal APIs |
| `jdeprscan` | Quét việc sử dụng API đã deprecated |
| `javap` | Disassemble/inspect class file, signature và bytecode |
| `jlink` | Tạo custom runtime image từ các module cần thiết |
| `javac` | Biên dịch source Java thành class file |

Một API có thể là public nhưng deprecated; `jdeprscan` phù hợp hơn để tìm trường hợp đó. Một API có thể không deprecated nhưng vẫn là internal; `jdeps --jdk-internals` phù hợp để tìm trường hợp này. Hai loại kiểm tra bổ sung cho nhau.

## 4. Lệnh trọng tâm: --jdk-internals

Cú pháp:

```bash
jdeps --jdk-internals path/to/application.jar
```

Có alias ngắn `-jdkinternals`, nhưng nên dùng tên dài `--jdk-internals` trong script mới để ý định rõ ràng.

`--jdk-internals` tìm class-level dependencies trong JDK internal APIs. Theo tài liệu jdeps hiện hành, mặc định nó phân tích các class được chỉ định qua input files và `--class-path`, trừ khi có `-include` giới hạn tập class.

Với một class:

```bash
jdeps --jdk-internals build/classes/com/example/UnsafeConsumer.class
```

Với thư mục class:

```bash
jdeps --jdk-internals build/classes
```

Với JAR:

```bash
jdeps --jdk-internals build/libs/application.jar
```

Hãy chạy trên artifact có thể triển khai. Nếu report có internal API, xác định class nguồn, module JDK đích và thư viện sở hữu class đó.

### 4.1. Output minh họa

```text
sample.jar -> jdk.unsupported
   demo.UnsafeConsumer -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your application.
```

Cách diễn đạt và suggested replacement có thể thay đổi theo JDK version. Hãy đọc toàn bộ report, không chỉ một dòng summary.

### 4.2. Ý nghĩa output

| Thành phần | Ý nghĩa |
| --- | --- |
| `sample.jar` | Archive chứa class đang được phân tích |
| `jdk.unsupported` | Module JDK chứa dependency được báo |
| `demo.UnsafeConsumer` | Class trong ứng dụng/thư viện có tham chiếu |
| `sun.misc.Unsafe` | Internal API được tham chiếu |
| `JDK internal API` | jdeps phân loại dependency là internal |

Khi nhiều class phụ thuộc cùng một API, report có thể có nhiều dòng. Cần truy ngược tới owner của từng class để biết vấn đề nằm trong source code nội bộ hay dependency ngoài.

### 4.3. Suggested Replacement là gợi ý, không phải auto-fix

Một số internal APIs có mapping tới replacement đã biết. jdeps có thể hiển thị bảng gợi ý. Đây là điểm bắt đầu để tìm tài liệu, không phải phép sửa tự động. Một API nội bộ có thể được dùng cho nhiều mục đích; hãy hiểu operation thực tế trước khi thay thế.

## 5. Các option hữu ích khi quét ứng dụng

### 5.1. Class path

`--class-path` (alias `-cp`/`-classpath`) chỉ định nơi jdeps tìm class files và dependency JAR.

```bash
jdeps --jdk-internals --class-path "lib/*" build/libs/application.jar
```

Trên Windows, dấu phân tách nhiều path entries là `;`; trên Linux/macOS là `:`.

```bash
# Linux / macOS
jdeps --jdk-internals --class-path "lib/a.jar:lib/b.jar" app.jar
```

```powershell
# Windows PowerShell
jdeps --jdk-internals --class-path "lib/a.jar;lib/b.jar" app.jar
```

Dùng đúng dependency set của môi trường triển khai. Nếu thiếu một JAR quan trọng, kết quả có thể báo missing dependencies hoặc không phản ánh đầy đủ graph mà ứng dụng chạy thực tế.

### 5.2. Module path

Ứng dụng modular sử dụng module path:

```bash
jdeps --jdk-internals --module-path mods --add-modules com.example.app app.jar
```

- `--module-path` chỉ định nơi tìm module.
- `--add-modules` thêm module vào root set cho phân tích.
- `--module` chỉ định root module trong module analysis.
- `--system` cho phép chỉ định system module path của một Java home khác khi cần.

Class path và module path là hai cơ chế phân giải khác nhau. Không đặt tất cả dependency JAR vào class path nếu ứng dụng thực sự triển khai chúng như named modules.

### 5.3. Recursive analysis

`--recursive` (alias `-R`) yêu cầu jdeps đi theo runtime dependencies một cách đệ quy:

```bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
```

Khi muốn phân tích dependency graph rộng hơn, hãy bảo đảm class path/module path chứa các artifact liên quan. Recursive analysis không thể tự phát hiện thư viện không nằm trong dependency universe được cung cấp.

### 5.4. Multi-release JAR

Một multi-release JAR có thể chứa class implementation khác nhau trong `META-INF/versions/N`. Khi phân tích JAR loại này, chỉ định phiên bản Java cần kiểm tra:

```bash
jdeps --jdk-internals --multi-release 17 library.jar
```

`--multi-release` nhận version integer từ 9 trở lên hoặc `base`. Chọn version phù hợp với runtime target. Nếu thư viện hỗ trợ nhiều runtime, nên kiểm tra các version mà dự án công bố hỗ trợ, thay vì chỉ xem base entries.

### 5.5. Chỉ phân tích public API signatures

`--api-only` giới hạn phân tích vào API signatures, ví dụ field types, parameter types, return types và checked exception types của public/protected members trong public classes:

```bash
jdeps --jdk-internals --api-only library.jar
```

Chế độ này hữu ích khi kiểm tra library có đưa internal type vào public API hay không. Tuy nhiên, nó **không phải full scan**: internal API được dùng trong method body hoặc implementation detail có thể không xuất hiện. Khi kiểm tra toàn bộ code, chạy `--jdk-internals` mà không thêm `--api-only`.

### 5.6. Hiển thị class-level dependencies nói chung

Nếu cần xem nhiều loại class dependencies, không chỉ internal APIs:

```bash
jdeps -verbose:class -filter:none application.jar
```

`-verbose:class` hiển thị class-level dependencies. `-filter:none` bỏ các bộ lọc mặc định về phụ thuộc trong cùng archive/package. Đây là chế độ khác với `--jdk-internals`.

### 5.7. Các tùy chọn module graph khác

| Option | Tác dụng |
| --- | --- |
| `--list-deps` | Liệt kê module dependencies và package names của JDK internal APIs nếu có |
| `--list-reduced-deps` | Liệt kê module dependencies sau khi loại các read edges được suy ra |
| `--print-module-deps` | In danh sách module dạng comma-separated, có thể dùng cho `jlink --add-modules` |
| `--check` | Phân tích dependency/readability graph của module được chỉ định |
| `--dot-output dir` | Xuất dependency graph dạng DOT |
| `--missing-deps` | Tìm missing dependencies |

Các tùy chọn này phục vụ phân tích dependency/module graph nói chung. Không nhầm chúng với `--jdk-internals`; mỗi option trả lời một câu hỏi khác nhau.

## 6. Đọc kết quả và ưu tiên xử lý

Không phải mọi finding có mức rủi ro giống nhau. Hãy phân loại theo:

1. Internal API được dùng là gì?
2. Class nào tham chiếu?
3. Class đó thuộc application hay third-party library?
4. API được dùng trong public/protected signature hay chỉ implementation?
5. API có còn hiện diện trong JDK mục tiêu không?
6. Package/module có được export/open trong runtime mục tiêu không?
7. Có replacement chuẩn nào đáp ứng đúng semantics?
8. Có runtime-only path mà jdeps không nhìn thấy không?

### 6.1. Tìm owner của dependency

Nếu report chỉ ra `vendor-library.jar -> sun.internal.SomeType`, tìm class cụ thể của library và xác định dependency version. Thường giải pháp tốt nhất là nâng lên version đã loại bỏ internal API hoặc dùng thư viện thay thế được duy trì.

Nếu class thuộc source code của ứng dụng, tìm import/reference trong source, sửa trực tiếp và thêm regression test.

### 6.2. Ưu tiên theo phạm vi ảnh hưởng

| Mức ưu tiên | Tình huống | Hành động |
| --- | --- | --- |
| Cao | Internal API đã bị loại bỏ hoặc không truy cập được trong target JDK | Thay thế/upgrade trước release |
| Cao | Internal API nằm trong public library signature | Loại khỏi public contract |
| Cao | Deep reflection bị strong encapsulation chặn | Nâng thư viện hoặc chuyển sang supported extension point |
| Trung bình | API vẫn truy cập nhưng unsupported/deprecated for removal | Lập kế hoạch migration và test target releases |
| Trung bình | Dependency gián tiếp từ third-party JAR | Nâng phiên bản hoặc thay thư viện |
| Cần xác minh | Finding có thể là JDK-specific extension được tài liệu hóa | Đọc docs và xác nhận support status |

Một finding vẫn cần được xử lý ngay cả khi ứng dụng hiện chạy được. Không đợi đến khi API bị xóa mới bắt đầu migration.

## 7. jdeps có giới hạn gì?

### 7.1. Reflection không được phát hiện đầy đủ

Ví dụ:

```java
Class<?> type = Class.forName("sun.misc.Unsafe");
```

Chuỗi tên class không nhất thiết tạo static class dependency giống direct type reference. Oracle migration guide nêu rõ jdeps là static analysis và không cảnh báo khi code dùng reflection để gọi internal API.

Các trường hợp có thể bị bỏ sót:

- `Class.forName` với tên class dạng String.
- Reflection qua `Method`/`Field` và tên member được tạo lúc runtime.
- Tên package/class đọc từ configuration hoặc database.
- Bytecode được sinh hoặc transform sau thời điểm chạy jdeps.
- Native/JNI code truy cập chi tiết triển khai của JVM.
- Class được tải từ plugin hoặc directory không có trong input/classpath/module path.

### 7.2. Không thay thế runtime tests

Sau khi chạy jdeps, vẫn cần:

- Chạy integration tests trên JDK target.
- Chạy các code path khởi động, shutdown, serialization, reflection và framework initialization.
- Kiểm tra `InaccessibleObjectException`, `IllegalAccessError` và linkage errors.
- Kiểm tra plugin, agent, instrumentation và runtime dependencies.
- Xác minh môi trường thực tế dùng cùng driver/library versions với môi trường test.

### 7.3. Không phải security scanner

`jdeps` không kiểm tra toàn bộ lỗ hổng bảo mật, không đánh giá chất lượng mật mã, không phát hiện mọi nguy cơ deserialization, SQL injection hoặc dependency vulnerability. Nó tập trung vào quan hệ phụ thuộc của bytecode và module.

### 7.4. Không quét được dependency chưa được cung cấp

Nếu một JAR chỉ xuất hiện trong container image hoặc plugin directory mà không được đưa vào input/classpath/module path, jdeps không thể phân tích class bên trong JAR đó. Tạo danh sách runtime artifacts từ packaging/deployment configuration để bảo đảm coverage.

### 7.5. Kết quả phụ thuộc phiên bản JDK dùng để chạy jdeps

Internal API list, module graph và trạng thái API thay đổi theo JDK. Hãy chạy jdeps từ JDK mà ứng dụng nhắm tới hoặc dùng đúng JDK target trong pipeline migration. Ghi lại `jdeps --version` trong report để kết quả có thể tái lập.

## 8. Strong encapsulation trong JDK hiện đại

Java module system được giới thiệu từ JDK 9. Quá trình encapsulation được tăng cường qua các release. Từ **JDK 17**, JDK strongly encapsulates internal elements; reflection truy cập non-public fields/methods trong các package `java.*` không còn được cho phép mặc định và có thể ném `InaccessibleObjectException`.

### 8.1. --illegal-access đã obsolete

`--illegal-access` từng là tùy chọn chuyển tiếp trong JDK 9–16 để điều chỉnh illegal reflective access. Trong JDK 17, tùy chọn này **obsolete và không còn mở quyền truy cập**; dùng nó chỉ tạo warning và không khắc phục lỗi.

Không dùng như giải pháp:

```bash
java --illegal-access=permit -jar application.jar
```

Thay vào đó, loại bỏ dependency nội bộ hoặc nếu thật sự cần compatibility workaround, chỉ mở/export đúng package cần thiết trong thời gian giới hạn.

### 8.2. --add-exports dành cho truy cập public types/members

Cú pháp:

```bash
java --add-exports source.module/package=target.module -jar application.jar
```

Ví dụ với classpath application:

```bash
java --add-exports java.management/sun.management=ALL-UNNAMED -jar application.jar
```

`--add-exports` cho phép target module truy cập public types/members của package được chỉ định trong source module. Nó cũng có thể được dùng lúc compile. Đây là quyền truy cập có phạm vi rõ, nhưng **không biến internal API thành supported API**.

### 8.3. --add-opens dành cho deep reflection

Cú pháp:

```bash
java --add-opens source.module/package=target.module -jar application.jar
```

Ví dụ:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
```

`--add-opens` mở package cho deep reflection vào non-public members trong runtime. Nó không giống `--add-exports` và không thay thế compile-time export.

Chỉ dùng package/target cụ thể mà dependency thực sự cần. Tránh mở hàng loạt package cho `ALL-UNNAMED` nếu không có lý do rõ ràng.

### 8.4. Workaround không thay cho migration

Nếu phải dùng `--add-exports` hoặc `--add-opens` để duy trì dependency cũ:

1. Ghi rõ library/version nào cần quyền truy cập.
2. Xác định chính xác module/package và target module.
3. Chỉ cấp quyền tối thiểu.
4. Theo dõi version thư viện đã sửa.
5. Loại bỏ flag khi dependency được nâng cấp.
6. Chạy tests trên JDK mới mà không có workaround để xác nhận migration.

Không đưa flag thành cấu hình vĩnh viễn chỉ để che finding từ jdeps.

## 9. Thay internal APIs bằng API chuẩn

Không có một replacement duy nhất cho mọi internal API. Chọn theo operation thực tế.

### 9.1. Memory access và atomic field access

`sun.misc.Unsafe` có các memory-access methods từng được dùng cho offset-based access, atomic operations và low-level memory manipulation. Các lựa chọn chuẩn hiện đại gồm:

- `java.lang.invoke.VarHandle` cho variable, field, array element access và atomic/volatile access modes.
- `java.util.concurrent.atomic` cho atomic variables/data structures có semantics phù hợp.
- Foreign Function & Memory API cho native/off-heap memory trên JDK 22+.

Ví dụ dùng `VarHandle` cho volatile int field:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
```

Đây là ví dụ Java 17+ dùng API chuẩn. Không copy nguyên logic offset/unsafe của thư viện sang VarHandle nếu chưa kiểm tra memory ordering, alignment, atomicity và concurrency semantics.

### 9.2. Native/off-heap memory

Foreign Function & Memory API được chuẩn hóa trong JDK 22. Các khái niệm hiện đại gồm `Arena`, `MemorySegment` và `ValueLayout`. API cung cấp scope/lifetime và bounds cho memory segments, giúp giảm rủi ro pointer arithmetic thủ công.

Ví dụ tối giản trên JDK 22+:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class MemorySegmentDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            int value = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println("value=" + value);
        }
    }
}
```

Biên dịch/chạy với JDK 22+:

```bash
javac MemorySegmentDemo.java
java MemorySegmentDemo
```

Stdout:

```text
value=42
```

Ví dụ minh họa allocation trong native memory arena. Foreign Function & Memory API không phải replacement tự động cho mọi cách dùng Unsafe; cần đối chiếu layout, lifetime, alignment, access scope và FFI requirements.

### 9.3. Chọn replacement theo mục đích

Khi jdeps báo một API nội bộ, tìm replacement theo mục đích: encoding, networking, reflection, concurrency, memory, file access hoặc class-file processing. Chọn Java SE APIs hoặc thư viện được duy trì và có contract công khai.

Không tự thay mọi package `sun.*` bằng một package `java.*` có tên tương tự. Cần hiểu hành vi thực tế, error handling và performance requirements.

## 10. Quy trình migration dựa trên jdeps

Một quy trình thực tế:

1. **Build artifact** đúng như release sẽ phát hành.
2. **Inventory runtime dependencies**: application JAR, library JAR, module path, plugin và shaded/fat JAR.
3. **Chạy jdeps --jdk-internals** với dependency paths đầy đủ.
4. **Lưu report** cùng JDK version và build identifier.
5. **Phân loại findings** theo owner, API, module và mức độ rủi ro.
6. **Upgrade third-party libraries** trước nếu có version đã sửa.
7. **Thay references trong source** bằng supported APIs nếu dependency do ứng dụng sở hữu.
8. **Chạy jdeps lại** trên artifact mới.
9. **Chạy runtime tests** trên JDK target, đặc biệt code paths dùng reflection/plugin/native code.
10. **Loại bỏ add-exports/add-opens workarounds** khi không còn cần.
11. **Đưa kiểm tra vào CI** để phát hiện dependency nội bộ mới trước release.

### 10.1. Quét artifact ứng dụng và thư viện

```bash
jdeps --jdk-internals --class-path "lib/*" build/application.jar
jdeps --jdk-internals --recursive --class-path "lib/*" build/application.jar
```

Lệnh đầu phân tích input và class path được chỉ định. Lệnh thứ hai mở rộng việc duyệt runtime dependencies. Tùy dự án, bổ sung module path, multi-release version hoặc thư mục plugin.

### 10.2. Báo cáo riêng public API của library

Nếu phát hành library cho bên thứ ba sử dụng, kiểm tra public/protected signatures:

```bash
jdeps --jdk-internals --api-only build/libs/library.jar
```

Finding trong API signature đặc biệt đáng chú ý vì nó đưa internal type vào contract mà consumer phải nhìn thấy. Đây là lượt kiểm tra bổ sung; vẫn chạy full scan để tìm internal API trong implementation.

### 10.3. Exit code 0 không có nghĩa report sạch

Trong thử nghiệm JDK 24.0.2 của bài này, jdeps đã tìm thấy `sun.misc.Unsafe` nhưng kết thúc với `exitCode=0`. Điều đó có nghĩa lệnh phân tích chạy thành công; nó **không có nghĩa report không có finding**.

CI cần kiểm tra nội dung report theo policy của dự án. Có thể lưu report làm artifact, đối chiếu với allowlist đã review hoặc dùng một bước script riêng để quyết định build có bị chặn hay không. Không chỉ kiểm tra exit code của jdeps.

### 10.4. Quản lý allowlist có kiểm soát

Nếu một dependency nội bộ chưa thể thay ngay, allowlist nên ghi:

- Tên artifact và version.
- Class và internal API được báo.
- Owner chịu trách nhiệm.
- Lý do tồn tại và mức độ chấp nhận rủi ro.
- JDK version đang hỗ trợ.
- Kế hoạch và điều kiện xóa exception.

Không cho phép allowlist theo package wildcard quá rộng. Một finding mới trong cùng package có thể là dependency khác cần xem xét.

## 11. Chương trình Java 17+ hoàn chỉnh: gọi jdeps qua ToolProvider

Ngoài command line, JDK cung cấp `ToolProvider` để gọi một số JDK tools từ Java. Module `jdk.jdeps` cung cấp tool provider tên `jdeps`.

Ví dụ dưới đây có hai source files:

- `demo/UnsafeConsumer.java`: class thử nghiệm cố ý tham chiếu một JDK internal API để jdeps có finding.
- `JdepsRunner.java`: tìm ToolProvider, gọi `jdeps --jdk-internals` và in report.

**Chỉ class UnsafeConsumer là specimen để phân tích.** Không dùng `Unsafe` trong ứng dụng production.

### 11.1. File demo/UnsafeConsumer.java

```java
package demo;

public final class UnsafeConsumer {
    public static String referencedClassName() {
        return sun.misc.Unsafe.class.getName();
    }
}
```

Code cố ý tham chiếu `sun.misc.Unsafe`. Khi compile bằng JDK hiện đại, compiler có thể cảnh báo đây là proprietary internal API. Lời gọi `Unsafe.class.getName()` chỉ tạo static type reference để jdeps phát hiện; không gọi memory-access method.

### 11.2. File JdepsRunner.java

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.spi.ToolProvider;

public class JdepsRunner {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass one class or JAR path");
        }

        ToolProvider jdeps = ToolProvider.findFirst("jdeps")
                .orElseThrow(() -> new IllegalStateException(
                        "The jdeps tool is not present in this JDK"));

        StringWriter buffer = new StringWriter();

        int exitCode = jdeps.run(
                new PrintWriter(buffer, true),
                new PrintWriter(System.err, true),
                "--jdk-internals",
                args[0]);

        System.out.print(buffer);
        System.out.println("jdepsExitCode=" + exitCode);

        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }
}
```

`ToolProvider.findFirst("jdeps")` tìm tool provider. `ToolProvider.run` nhận output/error writers, sau đó là arguments giống command line. Giá trị trả về là exit code của tool.

API ToolProvider của `jdeps` được cung cấp qua module `jdk.jdeps` từ JDK 9. Ví dụ này chạy với JDK 17+ có tool module.

### 11.3. Biên dịch và đóng JAR

Từ thư mục chứa `src`:

```bash
javac -d out src/demo/UnsafeConsumer.java
javac -d out src/JdepsRunner.java
jar --create --file out/sample.jar -C out demo
```

Compiler có thể in warning tương tự:

```text
UnsafeConsumer.java:4: warning: Unsafe is internal proprietary API
    return sun.misc.Unsafe.class.getName();
                   ^
1 warning
```

Warning text và source line có thể thay đổi theo JDK/compiler version. Điều quan trọng là class file được tạo thành công để tiếp tục phân tích.

### 11.4. Chạy chương trình phân tích

```bash
java -cp out JdepsRunner out/sample.jar
```

Stdout đã kiểm chứng trên OpenJDK 24.0.2:

```text
sample.jar -> jdk.unsupported
   demo.UnsafeConsumer -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your application.
Please modify code to eliminate dependence on any JDK internal APIs.

For the most recent update on JDK internal API replacements, please check:
https://wiki.openjdk.org/display/JDK8/Java+Dependency+Analysis+Tool

JDK Internal API                         Suggested Replacement
----------------                         ---------------------
sun.misc.Unsafe                          See https://openjdk.org/jeps/260
jdepsExitCode=0
```

Output có thể khác đôi chút ở JDK version khác, đặc biệt bảng suggested replacement và wording warning. Dòng finding chính là:

```text
demo.UnsafeConsumer -> sun.misc.Unsafe JDK internal API (jdk.unsupported)
```

**Lưu ý về exit code:** `jdepsExitCode=0` xuất hiện dù report có finding. CI phải đọc/đánh giá report, không chỉ coi exit code 0 là “không phụ thuộc internal API”.

### 11.5. Nếu không tìm thấy ToolProvider

Nếu `ToolProvider.findFirst("jdeps")` không tìm thấy tool, kiểm tra:

- Đang dùng JDK đầy đủ thay vì runtime image bị cắt module/tool.
- Module `jdk.jdeps` có trong runtime image.
- Ứng dụng được chạy với module configuration phù hợp.
- Đường dẫn JDK được chọn trong CI/IDE đúng với dự kiến.

Trong custom runtime image tạo bằng `jlink`, có thể phải thêm module `jdk.jdeps` nếu cần chạy ToolProvider bên trong image. Nếu chỉ cần quét build artifact, gọi binary `jdeps` từ một JDK đầy đủ trong build pipeline.

## 12. Các lỗi thường gặp

### Lỗi 1. Chỉ quét source code

`jdeps` phân tích bytecode. **Sửa:** build class files/JAR trước rồi mới chạy.

### Lỗi 2. Chỉ quét JAR của ứng dụng

Dependency có thể là nguồn duy nhất của internal API. **Sửa:** cung cấp runtime class path/module path đầy đủ và quét libraries.

### Lỗi 3. Quên multi-release JAR

Versioned class trong `META-INF/versions` có thể dùng API khác base entry. **Sửa:** dùng `--multi-release` với runtime target.

### Lỗi 4. Dùng --api-only cho full scan

Option này chỉ xét API signatures. **Sửa:** bỏ `--api-only` khi cần kiểm tra toàn bộ implementation.

### Lỗi 5. Cho rằng jdeps phát hiện mọi reflection

Static analyzer không thể suy ra mọi tên class/member được tạo ở runtime. **Sửa:** bổ sung runtime tests, code/config review và kiểm tra reflection.

### Lỗi 6. Dùng --illegal-access=permit trên JDK 17+

Tùy chọn này obsolete và không khôi phục quyền truy cập. **Sửa:** migrate dependency; dùng add-exports/add-opens chỉ khi cần workaround cụ thể và tạm thời.

### Lỗi 7. Nhầm --add-exports với --add-opens

Một bên cho phép truy cập public types/members trong package; bên kia mở deep reflection vào non-public members. **Sửa:** chọn đúng quyền theo loại access.

### Lỗi 8. Nghĩ API đang export thì được hỗ trợ

Internal API có thể vẫn truy cập được nhưng unsupported. **Sửa:** đọc contract và trạng thái API, không chỉ thử compile.

### Lỗi 9. Nhầm mọi com.sun.* là internal

Một số API được tài liệu hóa riêng. **Sửa:** dùng jdeps output và docs chính thức thay vì heuristic package prefix.

### Lỗi 10. Chỉ nhìn warning mà không xác định owner

Finding có thể đến từ JAR bên thứ ba. **Sửa:** tìm class/archive sở hữu dependency và version tương ứng.

### Lỗi 11. Coi suggested replacement là auto-fix

Replacement có thể không khớp semantics cụ thể của ứng dụng. **Sửa:** kiểm tra operation, memory ordering, errors và lifecycle.

### Lỗi 12. Dùng Unsafe vì vẫn còn trong JDK

Một số methods đã deprecated for removal và có runtime warnings. **Sửa:** chuyển sang VarHandle/FFM hoặc API phù hợp chức năng thực.

### Lỗi 13. Chỉ quét một JDK version

Internal API set/module graph thay đổi theo JDK. **Sửa:** chạy tool của JDK target và ghi version trong report.

### Lỗi 14. Tin exit code 0 nghĩa không có finding

Tool có thể chạy thành công và vẫn in internal dependencies. **Sửa:** kiểm tra nội dung report theo policy.

### Lỗi 15. Bỏ qua missing dependencies

Nếu dependency chưa resolve, report có thể chưa đầy đủ. **Sửa:** cung cấp classpath/module path đúng; xử lý missing dependencies trước khi kết luận.

### Lỗi 16. Dùng --ignore-missing-deps để làm report sạch

Option này che missing dependencies chứ không sửa chúng. **Sửa:** chỉ dùng khi có lý do rõ; không dùng trong lượt kiểm tra coverage đầu tiên.

### Lỗi 17. Dùng class path cho ứng dụng modular mà không kiểm tra module path

Có thể thiếu dependency hoặc sai graph. **Sửa:** cung cấp module path và module roots đúng.

### Lỗi 18. Chạy jdeps trên artifact cũ

Báo cáo không phản ánh code vừa sửa hoặc dependency vừa nâng. **Sửa:** chạy trên artifact mới sau build.

### Lỗi 19. Không test runtime reflection sau khi jdeps sạch

Reflection-only internal access có thể không xuất hiện trong report. **Sửa:** test code paths có reflection trên JDK target mà không có broad flags.

### Lỗi 20. Giữ add-opens/add-exports mãi mãi

Workaround che dependency và tăng bề mặt truy cập. **Sửa:** gắn owner/deadline, nâng library và loại bỏ flag khi migration hoàn tất.

### Lỗi 21. Nghĩ jdeps là security vulnerability scanner

Công cụ chỉ phân tích dependency graph và internal API. **Sửa:** dùng kiểm tra bảo mật chuyên biệt cho dependency CVE, secret, cryptography và runtime threats.

### Lỗi 22. Không quét plugin và generated classes

Những artifact được tải sau startup cũng có thể chứa internal dependencies. **Sửa:** inventory các class/JAR được triển khai, gồm plugin và generated code.

## 13. Bài tập thực hành và đáp án

**Bài 1.** `jdeps` dùng để làm gì?  
**Đáp án:** Phân tích phụ thuộc của class/package/module trong Java class files, directories và JARs.

**Bài 2.** Lệnh nào tìm JDK internal API dependencies?  
**Đáp án:** `jdeps --jdk-internals application.jar`.

**Bài 3.** `--jdk-internals` báo phụ thuộc ở mức nào?  
**Đáp án:** Class-level dependencies tới JDK internal APIs.

**Bài 4.** jdeps có đọc trực tiếp source `.java` chưa biên dịch không?  
**Đáp án:** Quy trình thông thường cần class files/JAR đã build.

**Bài 5.** Vì sao phải đưa dependency JAR vào class path?  
**Đáp án:** Để jdeps resolve và phân tích các class trong runtime dependency set, gồm thư viện bên thứ ba.

**Bài 6.** `--module-path` dùng cho trường hợp nào?  
**Đáp án:** Khi phân tích ứng dụng/module được resolve qua module path.

**Bài 7.** `--multi-release 17` có ý nghĩa gì?  
**Đáp án:** Chọn version 17 khi phân tích multi-release JAR.

**Bài 8.** `--api-only` phân tích phần nào?  
**Đáp án:** API signatures của public/protected members thuộc public classes; không phải full implementation scan.

**Bài 9.** jdeps có phát hiện mọi reflection call không?  
**Đáp án:** Không. Reflection hoặc tên class được tạo động có thể không xuất hiện như static dependency.

**Bài 10.** JDK 17 thay đổi gì về strong encapsulation?  
**Đáp án:** Internal elements được strongly encapsulated; reflection truy cập non-public members trong java.* packages không còn được cho phép mặc định.

**Bài 11.** `--illegal-access=permit` có khắc phục strong encapsulation trên JDK 17 không?  
**Đáp án:** Không. Option này obsolete và không còn tác dụng mở quyền truy cập.

**Bài 12.** `--add-exports` khác `--add-opens` ở đâu?  
**Đáp án:** add-exports cho phép truy cập public types/members trong package; add-opens cho phép deep reflection vào non-public members.

**Bài 13.** Finding `sun.misc.Unsafe` nghĩa là code đã không thể chạy?  
**Đáp án:** Không nhất thiết. Class vẫn có thể truy cập trong JDK hiện đại nhưng unsupported; memory-access methods đã deprecated for removal và có runtime warnings từ JDK 24.

**Bài 14.** API chuẩn nào thay thế nhiều memory access use cases của Unsafe?  
**Đáp án:** VarHandle cho variable/field/array access; Foreign Function & Memory API cho native/off-heap memory trên JDK 22+.

**Bài 15.** `jdepsExitCode=0` có chứng minh report không có finding không?  
**Đáp án:** Không. Nó có thể chỉ biểu thị lệnh phân tích thành công; phải đọc report.

**Bài 16.** Công cụ nào chuyên quét deprecated APIs?  
**Đáp án:** `jdeprscan`.

**Bài 17.** Có thể kết luận mọi `com.sun.*` là internal chỉ từ tên package không?  
**Đáp án:** Không. Phải kiểm tra API documentation và support status.

**Bài 18.** Vì sao chạy jdeps của target JDK hữu ích?  
**Đáp án:** Kết quả được đối chiếu với internal API inventory/module graph của phiên bản JDK ứng dụng nhắm tới.

**Bài 19.** jdeps có thay runtime integration test không?  
**Đáp án:** Không. Cần runtime tests để phát hiện reflection, dynamic loading, native access và behavior differences.

**Bài 20.** Một third-party library tạo finding, xử lý thế nào?  
**Đáp án:** Xác định owner/version, kiểm tra release đã sửa, nâng hoặc thay thư viện; nếu chưa thể, ghi exception có owner và thời hạn.

## 14. Checklist khi dùng jdeps trong dự án

- [ ] Xác định JDK runtime target và ghi rõ version.
- [ ] Dùng binary `jdeps` thuộc JDK target hoặc JDK được chọn rõ ràng.
- [ ] Build artifact mới nhất trước khi quét.
- [ ] Quét app JAR, class directories và libraries cần triển khai.
- [ ] Cung cấp class path đầy đủ nếu dùng classpath dependencies.
- [ ] Cung cấp module path/root modules cho ứng dụng modular.
- [ ] Dùng `--jdk-internals` để tìm JDK internal API references.
- [ ] Dùng `--multi-release` đúng target khi phân tích multi-release JAR.
- [ ] Chỉ dùng `--api-only` như lượt kiểm tra public API bổ sung.
- [ ] Kiểm tra missing dependencies và tránh che chúng bằng ignore option.
- [ ] Đọc từng finding và xác định class/archive owner.
- [ ] Phân biệt internal API với deprecated public API.
- [ ] Không coi package prefix là tiêu chí duy nhất.
- [ ] Không coi exit code 0 là report sạch.
- [ ] Lưu report, JDK version và artifact/build identifier.
- [ ] Nâng third-party dependencies đã loại bỏ internal API.
- [ ] Thay internal references bằng supported Java SE/JDK APIs phù hợp.
- [ ] Không dùng `--illegal-access` như workaround trên JDK 17+.
- [ ] Giới hạn add-exports/add-opens và có kế hoạch xóa.
- [ ] Bổ sung runtime tests cho reflection, plugin, native code và generated classes.
- [ ] Chạy lại jdeps sau mỗi thay đổi dependency/source.
- [ ] Thiết lập CI review/gating theo nội dung findings, không chỉ exit status.

## 15. Tài liệu chính thức và nguồn tham khảo hiện hành

1. [Oracle JDK 26 — The jdeps Command: options, --jdk-internals, class path, module path, multi-release JAR và module analysis](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
2. [Oracle JDK 26 Migration Guide — Strong Encapsulation, --add-exports, --add-opens và --illegal-access](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
3. [Oracle JDK 26 Migration Guide — Plan for Removal of sun.misc.Unsafe](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
4. [Oracle Java SE 26 — Module jdk.jdeps: ToolProvider cho jdeps/javap](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jdeps/module-summary.html)
5. [Oracle Java SE 26 — VarHandle API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html)
6. [Oracle Java SE 26 — MemorySegment API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/MemorySegment.html)
7. [Oracle JDK 23 Release Notes — JEP 471: Deprecate memory-access methods in sun.misc.Unsafe for removal](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
8. [Oracle JDK 24 Release Notes — JEP 498: Warn upon use of memory-access methods in sun.misc.Unsafe](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html)
9. [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
10. [OpenJDK JEP 471 — Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471)
11. [OpenJDK JEP 498 — Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498)

**Ghi nhớ:** Dùng `jdeps --jdk-internals` để tìm class-level dependencies vào JDK internal APIs. Quét đúng artifact và dependency paths, đọc finding để xác định owner, rồi thay bằng API được hỗ trợ hoặc nâng thư viện. jdeps không phát hiện đầy đủ reflection/dynamic loading; do đó vẫn phải kiểm thử runtime trên JDK mục tiêu. Strong encapsulation từ JDK 17 khiến internal access trở thành rủi ro thực tế hơn; `--illegal-access` đã obsolete. Các workaround `--add-exports`/`--add-opens` chỉ nên dùng hẹp và tạm thời. **Một báo cáo có finding vẫn có thể có exit code 0** — hãy kiểm tra nội dung báo cáo thay vì coi exit code là kết luận sạch.
