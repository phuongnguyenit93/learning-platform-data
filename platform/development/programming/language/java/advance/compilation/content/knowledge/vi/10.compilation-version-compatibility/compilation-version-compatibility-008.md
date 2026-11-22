# Ảnh hưởng của API deprecated, forRemoval và tính năng bị loại bỏ trong Java

Khi nâng cấp JDK hoặc thư viện Java, không phải mọi API từng hoạt động đều còn là lựa chọn tốt. Một API có thể **được khuyến cáo ngừng sử dụng** (*deprecated*), **được đánh dấu dự kiến loại bỏ** (*deprecated for removal*), hoặc **đã thực sự biến mất** khỏi phiên bản mới. Ba trạng thái này gây hậu quả khác nhau đối với compiler, bytecode, môi trường chạy và kế hoạch di trú.

Bài thuộc nhóm **tương thích phiên bản** của Java Advance – compilation: trọng tâm không chỉ là đọc annotation `@Deprecated` mà còn phải hiểu **build cảnh báo hay thất bại khi nào, binary cũ liên kết ra sao, `--release` bảo đảm điều gì và cần kiểm tra gì trước khi nâng cấp**.

## 1. Phân biệt ba trạng thái

| Trạng thái | Ý nghĩa | Khi biên dịch source dùng API đó | Khi chạy binary đã biên dịch |
| --- | --- | --- | --- |
| API còn tồn tại, `@Deprecated(forRemoval=false)` | Không nên tiếp tục dùng; chưa tuyên bố ý định cụ thể loại bỏ tại thời điểm đánh dấu | Thường là **ordinary deprecation warning** khi được dùng trong ngữ cảnh kích hoạt cảnh báo; không tự động là lỗi | Thường vẫn liên kết/chạy nếu API và dependency vẫn hiện diện, tương thích |
| API còn tồn tại, `@Deprecated(forRemoval=true)` | Đã tuyên bố **ý định loại bỏ ở một phiên bản tương lai** | **Removal warning**, thường hiển thị mặc định với `javac`; bản thân annotation chưa xóa API | Vẫn có thể chạy khi API còn hiện diện và hợp lệ |
| API/tính năng đã bị loại bỏ trong target/runtime | Không còn định nghĩa hoặc hỗ trợ thích hợp | Source có thể lỗi kiểu `cannot find symbol`/`package does not exist`/module không thấy; cú pháp hoặc option bị xóa có thể lỗi tương ứng | Binary cũ có thể gặp `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchFieldError`, lỗi module hoặc thay đổi hành vi tùy tình huống |

**Quan trọng:** `forRemoval=true` **không phải ngày hẹn xóa tự động**, không ngầm nghĩa “sẽ bị xóa ngay ở release kế tiếp” và không bảo đảm API bị xóa trong một phiên bản cụ thể. Nó là tín hiệu cần hành động sớm. Ngược lại, `forRemoval=false` **không cam kết API được giữ vĩnh viễn**.

Một API có thể deprecated vì: giải pháp thay thế tốt hơn; thiết kế lỗi thời; rủi ro an toàn; khả năng dùng sai; hoặc tương lai có thể thay đổi không tương thích. Không nên suy ra API **đang sai hoặc lập tức ngừng hoạt động** chỉ từ chữ “Deprecated”.

## 2. Cú pháp và ý nghĩa của `@Deprecated`

Annotation chuẩn `java.lang.Deprecated` đã tồn tại từ Java 5; hai phần tử `since` và `forRemoval` được bổ sung từ Java 9.

~~~java
@Deprecated(since = "2.0", forRemoval = true)
public static void oldOperation() {
    // ...
}
~~~

- `since` là **chuỗi thông tin** chỉ phiên bản mà element được đánh dấu deprecated; giá trị mặc định là chuỗi rỗng `""`. Với thư viện riêng, `"2.0"` có thể là phiên bản thư viện, không nhất thiết là phiên bản JDK.
- `forRemoval` là boolean, mặc định `false`. `true` thể hiện ý định loại bỏ; `false` chỉ khuyến cáo tránh sử dụng mà chưa có ý định loại bỏ cụ thể tại thời điểm annotation.
- `@Deprecated` có thể đánh dấu class, interface, method, constructor, field, module, package... tùy target được annotation hỗ trợ. Quy tắc phát warning khác nhau theo loại element; chẳng hạn đánh dấu một local variable hoặc parameter không khiến mọi chỗ dùng nó tự phát sinh deprecation warning.
- Annotation có runtime retention, nên reflection có thể đọc thông tin deprecation. Tuy nhiên, **reflection đọc được annotation không có nghĩa code dùng API chỉ gặp vấn đề ở runtime**: cảnh báo liên quan đến việc dùng tên API thường được compiler phát hiện ngay từ source.

Cú pháp tương đương khi không định thay đổi mặc định:

~~~java
@Deprecated
public void oldMethod() {
    // forRemoval=false, since=""
}
~~~

Và khi biết phiên bản bắt đầu deprecated nhưng chưa dự định xóa:

~~~java
@Deprecated(since = "1.3", forRemoval = false)
public void oldMethod() {
}
~~~

### `@Deprecated` và Javadoc `@deprecated` không giống nhau

**Annotation** `@Deprecated` phục vụ compiler, tooling và reflection. **Javadoc tag** `@deprecated` (chữ `d` thường) giải thích *tại sao không nên dùng* và *phải thay bằng gì*.

Ví dụ viết API có trách nhiệm:

~~~java
/**
 * Tạo chuỗi theo định dạng cũ.
 *
 * @deprecated Kể từ 2.0, dùng {@link #format(String)}
 *             để thống nhất định dạng đầu ra.
 */
@Deprecated(since = "2.0", forRemoval = false)
public static String oldFormat(String value) {
    return "old:" + value;
}

public static String format(String value) {
    return "new:" + value;
}
~~~

Đây là **đoạn method minh họa bên trong một class**, chưa phải chương trình độc lập. Nên dùng **cả annotation và Javadoc tag**: annotation để công cụ nhận biết trạng thái, tài liệu để người sử dụng biết lộ trình di trú. Khi một method thay đổi hành vi, tài liệu phải nói rõ khác biệt; chỉ viết “use X instead” mà không giải thích semantics có thể gây lỗi logic.

## 3. Thực hành Java 17+: ordinary warning và removal warning

Ví dụ hoàn chỉnh gồm **hai tệp** trong package `training`.

**File `src/training/LegacyApi.java`:**

~~~java
package training;

public final class LegacyApi {
    private LegacyApi() {
    }

    /**
     * @deprecated Use {@link #format(String)} instead.
     */
    @Deprecated(since = "1.0", forRemoval = false)
    public static String oldFormat(String name) {
        return "hello " + name;
    }

    /**
     * @deprecated Use {@link #limit()} instead.
     */
    @Deprecated(since = "2.0", forRemoval = true)
    public static int oldLimit() {
        return 10;
    }

    public static String format(String name) {
        return "modern " + name;
    }

    public static int limit() {
        return 20;
    }
}
~~~

**File `src/training/Client.java`:**

~~~java
package training;

public final class Client {
    public static void main(String[] args) {
        System.out.println(LegacyApi.oldFormat("An"));
        System.out.println(LegacyApi.oldLimit());
        System.out.println(LegacyApi.format("An"));
        System.out.println(LegacyApi.limit());
    }
}
~~~

Đứng ở thư mục có `src`, sử dụng **JDK 17+**:

~~~bash
mkdir out
javac -encoding UTF-8 --release 17 -Xlint:deprecation -Xlint:removal -d out src/training/LegacyApi.java src/training/Client.java
java -cp out training.Client
~~~

Nếu `out` đã tồn tại, bỏ qua lệnh `mkdir out`.

**Stdout của chương trình:**

~~~text
hello An
10
modern An
20
~~~

Khi `javac` compile `Client.java`, nó nhận biết:

- `oldFormat(String)` được deprecated, nhưng `forRemoval=false` ⇒ cảnh báo mang nhãn **`[deprecation]`** khi bật `-Xlint:deprecation`.
- `oldLimit()` được đánh dấu `forRemoval=true` ⇒ cảnh báo **`[removal]`** khi bật `-Xlint:removal`.
- `format` và `limit` không deprecated ⇒ không phát hai cảnh báo trên.

Cảnh báo của compiler thường xuất hiện **trên stderr**, không phải stdout của `java`. Nội dung số dòng, đường dẫn file và cách trình bày chính xác tùy phiên bản `javac`, vì thế không nên coi chúng là stdout cố định. Với source ví dụ này, compiler sẽ chỉ ra hai điểm dùng API cũ trong `Client`; chương trình vẫn chạy sau khi build thành công.

Một cách diễn đạt ngắn gọn là:

~~~text
[deprecation] oldFormat(String) ... has been deprecated
[removal] oldLimit() ... has been deprecated and marked for removal
~~~

Hai dòng trên chỉ là **mô phỏng phần thông điệp quan trọng**, không phải chép nguyên stderr của một máy cụ thể.

## 4. Quy tắc `javac` về hai loại cảnh báo

Theo tài liệu JDK, deprecation thông thường và deprecation-for-removal là **hai nhóm cảnh báo độc lập**.

| Điều khiển | Ý nghĩa |
| --- | --- |
| `-Xlint:deprecation` | In chi tiết cảnh báo ordinary deprecation |
| `-Xlint:removal` | In chi tiết cảnh báo API marked for removal |
| `-Xlint:-deprecation` | Tắt nhóm ordinary deprecation |
| `-Xlint:-removal` | Tắt nhóm removal |
| `-Xlint:all` | Bật các nhóm lint áp dụng được, không chỉ deprecation |
| `-Werror` | Làm cho compilation thất bại nếu có warning được phát ra |
| `-Xmaxwarns 100` | Điều khiển tối đa số warning được hiển thị, **không giải quyết lỗi** |

Với `javac` hiện đại, **`-Xlint:removal` bật theo mặc định**, còn ordinary deprecation có thể chỉ được báo bằng dòng tổng kết “uses or overrides a deprecated API” nếu không bật `-Xlint:deprecation`. Đừng khẳng định một source không có vấn đề chỉ vì output không có từng dòng warning chi tiết.

Thử build nghiêm ngặt:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:deprecation -Xlint:removal -Werror -d out src/training/LegacyApi.java src/training/Client.java
~~~

Với hai lời gọi deprecated trong `Client.java`, compilation **thất bại vì warnings bị coi là lỗi**. Việc compiler có để lại một vài artifact trung gian hay không không phải điều nên dựa vào; hãy dùng clean build trong CI nếu cần xác nhận kết quả.

**Bật cảnh báo giúp phát hiện rủi ro**, nhưng không phải bảo đảm compiler sẽ tìm ra mọi API nguy hiểm: code được gọi bằng reflection, service loader, method handle, native interop hay đường xử lý chỉ có ở runtime có thể cần kiểm tra riêng.

### `@SuppressWarnings` có dùng được không?

Có, nhưng phải dùng **đúng key**:

~~~java
@SuppressWarnings("deprecation")
static void callOldFormat() {
    LegacyApi.oldFormat("An");
}

@SuppressWarnings("removal")
static void callOldLimit() {
    LegacyApi.oldLimit();
}

@SuppressWarnings({"deprecation", "removal"})
static void callBoth() {
    LegacyApi.oldFormat("An");
    LegacyApi.oldLimit();
}
~~~

Ba method trên là **đoạn minh họa đặt trong class cùng package hoặc có import phù hợp**, không phải một chương trình độc lập.

`"deprecation"` **không** tự tắt `"removal"`; `"removal"` cũng không tắt ordinary deprecation. Suppression có hiệu lực tại phạm vi được chú thích theo quy tắc compiler; cần giới hạn phạm vi nhỏ, ghi chú lý do và thời hạn thay thế.

**Suppression chỉ ẩn warning, không khôi phục API đã bị xóa.** Khi method/class không còn tồn tại trong target API, source vẫn không compile hoặc binary vẫn lỗi lúc liên kết. Tắt warning không làm mã trở nên tương thích hơn.

## 5. Đổi sang API mới: phải kiểm tra ngữ nghĩa

Nếu đổi hai lời gọi trong `Client`:

~~~java
System.out.println(LegacyApi.format("An"));
System.out.println(LegacyApi.limit());
~~~

thì output của hai dòng lần lượt là:

~~~text
modern An
20
~~~

Code không còn phụ thuộc hai deprecated methods, nhưng kết quả chương trình đã **thay đổi** so với `oldFormat` và `oldLimit`. Điều này minh họa rằng migration không luôn là thay tên method cơ học.

Một chiến lược thay thế an toàn:

1. Đọc Javadoc của API cũ và mới, đặc biệt khác biệt về input, output, null handling, exception, threading, timezone, charset, default values và security behavior.
2. Viết test cho use cases thật và các trường hợp biên.
3. Migrate call sites theo từng nhóm; nếu phải hỗ trợ API cũ, làm lớp adapter nhỏ, rõ phạm vi.
4. Bật lint và kiểm tra build trên các JDK mục tiêu.
5. Xóa các suppression tạm thời sau khi migration hoàn tất.

Nếu một API được deprecated vì **nguy cơ bảo mật**, chỉ giữ nguyên API cũ để “không thay đổi output” có thể không phải lựa chọn chấp nhận được. Ngược lại, thay thế có cùng tên chức năng nhưng khác semantics cũng có thể tạo bug trong production. Quyết định cần dựa vào hợp đồng API cụ thể.

## 6. Điều gì xảy ra khi API bị loại bỏ?

**Deprecated** vẫn là một phần API hiện tại; **removed** nghĩa là một lớp, method, field, module, tool, option hoặc hành vi không còn được cung cấp như trước.

Ảnh hưởng thường trải qua hai trường hợp khác nhau.

### 6.1. Biên dịch source cũ trên library/JDK mới

Ví dụ source gọi một method đã bị loại bỏ:

~~~java
String message = LegacyApi.oldFormat("An");
~~~

Khi compiler chỉ thấy bản `LegacyApi` **đã xóa `oldFormat`**, sẽ gặp lỗi tương tự `cannot find symbol`. Nếu cả package hoặc module bị xóa, có thể thấy `package ... does not exist` hoặc `module not found`. Cảnh báo deprecated không còn là vấn đề chính: **compiler không còn tìm được declaration hợp lệ**.

Nếu source code sử dụng một **cú pháp ngôn ngữ** không được target release hỗ trợ, lỗi là cú pháp/source-level. Nếu dùng **tùy chọn launcher/compiler** đã loại bỏ, lệnh build có thể bị từ chối. Không trộn những lỗi này thành một “deprecated warning”.

### 6.2. Binary cũ chạy với bản thư viện mới

Bytecode Java thường giữ tham chiếu ký hiệu tới class, method và field theo các tên/descriptor được compile. Nếu thư viện triển khai ở runtime không còn đáp ứng tham chiếu đã phát ra, JVM có thể ném **linkage errors**.

| Thành phần thay đổi | Hiện tượng có thể gặp |
| --- | --- |
| Class bị xóa khỏi runtime | `NoClassDefFoundError` khi bytecode cần class đó; `ClassNotFoundException` khi chủ động tìm bằng API như `Class.forName` |
| Method bị xóa/đổi descriptor | `NoSuchMethodError` khi call site được phân giải |
| Field bị xóa/đổi descriptor | `NoSuchFieldError` |
| Thay đổi static/instance hoặc kiểu khai báo không tương thích | Có thể gây `IncompatibleClassChangeError` hoặc lỗi liên kết liên quan |
| Module dependency bị loại bỏ hoặc không được resolve | Lỗi module resolution/initialization, tùy cách launch |
| Runtime quá cũ so với class-file version | `UnsupportedClassVersionError`, không nhất thiết liên quan deprecation |

**Không cam kết mọi binary cũ đều vỡ** ngay khi một API bị xóa: chỉ những đường sử dụng cần resolve tham chiếu bị thiếu mới có thể gây lỗi tương ứng. Một binary không còn gọi method đó có thể vẫn hoạt động; app dùng reflection/native access còn chịu cơ chế riêng.

### 6.3. Thí nghiệm tương thích binary: bỏ method mà không biên dịch lại client

Tạo ba source files trong ba source roots riêng:

~~~text
compat-lab/
├── api-v1/lib/Greeter.java
├── api-v2/lib/Greeter.java
└── client/app/Main.java
~~~

**File `api-v1/lib/Greeter.java`:**

~~~java
package lib;

public final class Greeter {
    @Deprecated(since = "1.0", forRemoval = true)
    public static String greet() {
        return "legacy";
    }
}
~~~

**File `api-v2/lib/Greeter.java`:**

~~~java
package lib;

public final class Greeter {
    public static String welcome() {
        return "modern";
    }
}
~~~

**File `client/app/Main.java`:**

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
~~~

Tạo trước các thư mục output `build/v1`, `build/v2` và `build/client`. Từ thư mục `compat-lab`, compile **hai phiên bản API riêng biệt**:

~~~bash
javac -encoding UTF-8 --release 17 -d build/v1 api-v1/lib/Greeter.java
javac -encoding UTF-8 --release 17 -d build/v2 api-v2/lib/Greeter.java
javac -encoding UTF-8 --release 17 -cp build/v1 -d build/client client/app/Main.java
~~~

Lệnh compile client nhìn thấy `build/v1`, nơi `greet()` còn tồn tại. Trên Windows, chạy:

~~~bash
java -cp "build/client;build/v1" app.Main
~~~

Trên Linux/macOS, chạy:

~~~bash
java -cp "build/client:build/v1" app.Main
~~~

Stdout trong cả hai trường hợp:

~~~text
legacy
~~~

**Thử cố tình dùng binary API mới mà không biên dịch lại client:**

Windows:

~~~bash
java -cp "build/client;build/v2" app.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/client:build/v2" app.Main
~~~

Lời gọi tới `lib.Greeter.greet()` không còn method đích trong `build/v2`. Khi JVM cần resolve method, ứng dụng sẽ thất bại với **`java.lang.NoSuchMethodError`**. Phần stack trace, đường dẫn hoặc module thông tin tùy runtime; đây là lỗi được mong đợi của **thí nghiệm cố ý không tương thích**, không phải output chuẩn của chương trình thành công.

Nếu biên dịch lại `Main.java` với `-cp build/v2`, compiler báo method `greet()` không được tìm thấy. Hai thí nghiệm cho thấy:

- **Source incompatibility:** code cũ không compile trên API mới.
- **Binary incompatibility:** binary đã compile cũ bị lỗi khi liên kết/lời gọi với API mới.

Trong thực tế, bảo đảm deployment đúng **phiên bản library** quan trọng không kém việc build thành công.

## 7. `--release` làm được gì và không làm được gì?

Giả sử đang dùng JDK mới nhưng ứng dụng phải tương thích Java 17:

~~~bash
javac --release 17 -d out src/training/LegacyApi.java src/training/Client.java
~~~

`--release 17` đặt mục tiêu **cú pháp/ngôn ngữ, class-file target và tập API nền tảng được hỗ trợ của Java 17** theo cơ chế `javac`. Nó hữu ích để tránh vô tình gọi một **Java platform API** chỉ có trên JDK mới hơn.

So sánh:

- `-source 17` kiểm soát mức cú pháp nguồn, không tự bảo đảm mọi Java platform API đã gọi có mặt ở Java 17.
- `-target 17` kiểm soát class-file target, không độc lập bảo đảm compatibility của API.
- `--release 17` kết hợp kiểm soát source level, target và Java platform API tương ứng release.

**Giới hạn quan trọng:**

1. `--release 17` không biến JAR của **thư viện bên thứ ba phiên bản 5** thành API của phiên bản 3. Phải quản lý dependency theo artifact/version cụ thể.
2. `--release 17` không chứng minh runtime tương lai còn giữ API đó nếu phiên bản runtime sau này đã loại bỏ API, thay đổi hành vi hoặc môi trường cấu hình.
3. `--release` không kiểm tra tất cả hành vi chỉ phát hiện lúc chạy như reflection, native libraries, TLS defaults, filesystem permissions hoặc service providers.
4. JDK compiler chỉ hỗ trợ một **tập các release target nhất định**. Kiểm tra bằng `javac --help`; không mặc định compiler mới có thể target mọi Java version quá cũ.
5. Khi target platform API của release cũ, không được dùng các tùy chọn phá encapsulation của platform API để lách những ràng buộc của `--release`.

Vì vậy **compile bằng `--release 17` là bước cần nhưng chưa đủ** trong quy trình nâng cấp nhiều phiên bản JDK.

### Cùng một source trên hai API baselines

Mã gọi API có trong Java 17 nhưng đã bị xóa ở một JDK muộn hơn có thể compile thành công với `--release 17`. Điều đó không có nghĩa nó sẽ chạy trên mọi JDK mới: runtime mới phải còn cung cấp các lớp và method được bytecode tham chiếu.

Ngược lại, nếu compile source **theo release mới đã xóa API**, compiler có thể từ chối ngay. Đừng nhầm “biên dịch được cho Java 17” với “đã kiểm thử đầy đủ trên Java 17 và mọi Java mới hơn”.

## 8. API, module, công cụ và tính năng bị loại bỏ là những phạm vi khác nhau

Java được phát triển theo phiên bản; đối tượng bị deprecated/removed không chỉ là một method.

| Phạm vi | Ví dụ ảnh hưởng | Cách kiểm tra |
| --- | --- | --- |
| **Method / field / class trong API** | Call site không còn compile hoặc link được | Javadoc, binary compatibility, build và smoke tests |
| **Package / JDK module** | `requires` không resolve; import package mất; class không còn | Module graph, module path, dependency artifacts |
| **Công cụ JDK** | Script CI gọi executable không còn | Migration guide, `java -version`, kiểm tra build script |
| **Tùy chọn compiler/launcher/JVM** | Startup hoặc build bị từ chối; tùy chọn có thể chỉ còn cảnh báo/bị bỏ qua | Test chính lệnh CLI trên các JDK mục tiêu |
| **Ngôn ngữ/source feature** | Cú pháp không được hỗ trợ bởi target source version | `javac --release N`, JLS cho N |
| **Runtime behavior** | Cùng bytecode nhưng khác mặc định/khả năng triển khai | Integration tests, release notes, cấu hình runtime |

### Ví dụ đã xảy ra trong JDK

- **Java 11:** các module Java EE/CORBA từng được cung cấp cùng JDK như `java.xml.bind`, `java.xml.ws` và `java.corba` đã bị loại bỏ khỏi JDK theo **JEP 320**. Code cũ có thể phải thêm các dependency bên ngoài hoặc migrate sang API mới. Với JAXB, chú ý có các thế hệ namespace/artifact khác nhau, không đơn thuần thay một import.
- **Java 15:** Nashorn JavaScript engine và công cụ `jjs` bị loại bỏ theo **JEP 372**. Một ứng dụng dùng `ScriptEngineManager` mà kỳ vọng engine JavaScript mặc định có thể cần engine khác; bản thân Java Scripting API và việc mất một engine cụ thể là hai vấn đề khác nhau.
- **Java 17:** Java RMI Activation API đã bị loại bỏ theo lộ trình removal. Không đồng nghĩa **toàn bộ RMI** đều bị xóa khỏi Java.

Các ví dụ lịch sử chứng minh rằng “deprecated for removal” có thể dẫn đến **xóa thật**, nhưng không tạo một quy tắc cố định “chờ bao nhiêu release thì xóa”. Tra đúng JEP/migration guide/release notes của **release đang sử dụng** trước khi kết luận trạng thái của bất kỳ API cụ thể nào.

## 9. Công cụ phát hiện deprecation và removal

### 9.1. `javac`: thấy những chỗ source gọi API cũ

Khi đang compile mã nguồn:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/training/LegacyApi.java src/training/Client.java
~~~

Đọc cả warnings để tìm các call sites; sau khi migrate, có thể bật `-Werror` ở CI để ngăn thêm các lần dùng API deprecated mới. Nên kiểm soát theo từng module/package nếu codebase có số lượng warning cũ lớn, để lộ trình không làm nhóm ngừng phát triển.

### 9.2. `jdeprscan`: quét reference tới Java platform APIs deprecated

`jdeprscan` là công cụ thuộc JDK, có thể quét các class/JAR/directory đã biên dịch để báo những tham chiếu tới Java platform APIs deprecated thuộc release được chỉ định. Ví dụ khảo sát danh mục API marked for removal của Java 17:

~~~bash
jdeprscan --release 17 --list --for-removal
~~~

Hoặc quét output của dự án (`out` phải chứa class files):

~~~bash
jdeprscan --release 17 --for-removal out
~~~

Các tool options/release khả dụng phụ thuộc bản JDK đang chạy; kiểm tra `jdeprscan --help`. Khi quét cần đủ classpath để resolve dependencies, nếu thiếu có thể có lỗi hoặc kết quả không đầy đủ. `jdeprscan` nhắm tới **deprecated Java platform APIs**, không phải bộ máy phát hiện mọi deprecated API tùy ý của third-party JAR, và không phát hiện mọi lời gọi động qua reflection.

### 9.3. `jdeps` và class-file inspection

`jdeps` hữu ích để phân tích dependency ở mức package/module, hỗ trợ nhận diện tham chiếu tới internal APIs và điểm migration liên quan. Nhưng nó không phải phương pháp duy nhất để quyết định rằng một method đã bị xóa hoặc việc thay thế có tương đương về semantics.

`javap -v` có thể hiển thị metadata `Deprecated` và annotations trong các class files mà compiler đã sinh; các attributes và cách trình bày cụ thể phụ thuộc compiler/JDK. Không dựa vào một bảng disassembly để kết luận runtime an toàn mà bỏ qua tests.

### 9.4. Documentation và CI matrix

Nên kết hợp:

- Java API documentation: đọc phần deprecated, `since`, `forRemoval`, alternative và các caveats.
- JDK migration guide, JEPs, release notes: biết module/tool/option/behavior nào bị bỏ theo từng release.
- Dependency changelog và semantic-versioning policy của từng thư viện.
- Clean build cùng warnings và test trên **JDK tối thiểu được hỗ trợ** lẫn **JDK mục tiêu sắp triển khai**.
- Kiểm tra runtime bằng đúng dependency graph, không dùng thư viện khác phiên bản so với bản đã kiểm thử.

## 10. Chiến lược chuyển đổi an toàn

Một dự án lâu năm thường không thể xóa hết deprecated APIs trong một commit. Có thể thực hiện tuần tự:

1. **Chốt baseline:** ghi Java runtime versions được hỗ trợ, compiler version, `--release` target, dependencies và các JDK build/run thực tế. Tránh “works on my machine” bằng lockfile/version management phù hợp.
2. **Lập danh sách:** bật `-Xlint:deprecation` và `-Xlint:removal`, chạy `jdeprscan` cho JDK APIs, phân loại warnings theo module và thư viện.
3. **Ưu tiên rủi ro:** API `forRemoval=true`, vấn đề bảo mật hoặc API đã bị xóa trên target JDK cần được ưu tiên hơn deprecation thông thường chỉ vì có replacement tiện lợi hơn.
4. **Đọc contract thay thế:** kiểu trả về, nullability, exception types, encoding, performance, initialization, concurrency, resource ownership và security controls có thể khác.
5. **Tạo kiểm thử hành vi:** unit/integration tests cho luồng thường và trường hợp lỗi; binary compatibility tests khi thư viện cung cấp API cho bên ngoài.
6. **Migrate từng vùng nhỏ:** thay call sites, chuyển dependency/module descriptors, xóa bridge adapter khi không còn cần. Nếu bắt buộc giữ compatibility, cân nhắc façade với version-aware implementation nhưng không giả vờ API đã xóa vẫn có mặt.
7. **Nâng cảnh báo lên chính sách CI:** có thể bật `-Werror` sau khi giải quyết warnings hiện tại; không lạm dụng `@SuppressWarnings` rộng khắp.
8. **Kiểm tra deployment:** chạy test trên JDK mới với module/classpath thật, quan sát stack trace, module resolution, reflection, native integration, serialization và startup options.
9. **Theo dõi release kế tiếp:** một lần migrate thành công không xóa rủi ro deprecation mới xuất hiện.

### Thứ tự ưu tiên điển hình

| Mức | Điều kiện | Hành động |
| --- | --- | --- |
| P0 | Đã bị loại khỏi JDK/library mục tiêu hoặc gây lỗi runtime | Chặn rollout; sửa build/dependency/code ngay |
| P1 | `forRemoval=true` hoặc deprecation do an toàn/bảo mật | Lên kế hoạch thay sớm, có tests |
| P2 | Deprecated thông thường, có replacement ổn định | Migrate có kiểm soát theo vòng phát triển |
| Theo dõi | Deprecated nhưng chưa có replacement/không ảnh hưởng ở target hiện tại | Ghi nhận rủi ro và đánh giá mỗi lần nâng version |

Phân loại P0/P1/P2 là một **quy trình đề xuất**, không phải nhãn chuẩn của JDK; mức ưu tiên cuối cùng phụ thuộc hệ thống thật.

## 11. Các hiểu lầm phổ biến

**“Có `@Deprecated` là lỗi biên dịch.”** Sai. Thông thường là warning; có thể thất bại do `-Werror` hoặc chính sách build, không phải annotation làm API lập tức biến mất.

**“`forRemoval=true` nghĩa là phiên bản tiếp theo chắc chắn xóa.”** Sai. Đây là thông báo ý định và tín hiệu rủi ro, không phải lịch xóa được Java bảo đảm.

**“`since="17"` nghĩa API chỉ tồn tại từ Java 17.”** Sai. Trong `@Deprecated`, `since` ghi **thời điểm bắt đầu deprecated**, không phải thời điểm API lần đầu tồn tại. Tài liệu `@since` có vai trò khác.

**“Tắt warning bằng `@SuppressWarnings` là tương thích.”** Sai. Khi symbol bị xóa, compilation hoặc linking vẫn lỗi.

**“`-Xlint:deprecation` tự bao gồm removal warning.”** Không nên suy luận vậy: đây là hai nhóm riêng, điều khiển qua `deprecation` và `removal` độc lập.

**“Build thành công ở JDK mới chứng tỏ binary deploy ở JDK cũ chạy được.”** Sai. Cần `--release` phù hợp, dependency compatibility và test runtime thực tế.

**“Compile với API v1, chạy với API v2 luôn ổn nếu tên class giống.”** Sai. JVM còn phân giải method/field descriptors và module/dependency; có thể gặp linkage errors.

**“Không thấy warning thì dự án không dùng API bị loại bỏ.”** Sai. Có thể chưa bật lint, có suppression, dùng reflection, binary đã biên dịch, hay đi qua library khác.

**“Một feature/tool bị removed nghĩa mọi API liên quan đều bị xóa.”** Sai. Chẳng hạn Nashorn engine và công cụ `jjs` bị bỏ không đồng nghĩa mọi API của Java Scripting lập tức bị loại bỏ.

## 12. Bài tập tự kiểm tra

**1.** `@Deprecated(since="2.1", forRemoval=false)` cho biết điều gì?

Đó là API được đánh dấu deprecated từ phiên bản `2.1` của thành phần liên quan; chưa biểu thị ý định loại bỏ cụ thể tại thời điểm annotation. Không có nghĩa API được thêm mới ở `2.1`.

**2.** Nếu method đã `forRemoval=true` nhưng vẫn tồn tại trong JDK đang chạy, lời gọi có chắc thất bại?

Không. Compiler có thể báo removal warning; runtime vẫn có thể chạy nếu symbol hiện diện và hoạt động như mong đợi. Trạng thái deprecation riêng không xóa method.

**3.** Vì sao `@SuppressWarnings("deprecation")` chưa chắc che removal warning?

Vì `deprecation` và `removal` là hai lint categories riêng; để che removal warning phải dùng `"removal"` (nhưng nên xử lý nguyên nhân thay vì che).

**4.** `javac -Werror` có làm API bị loại bỏ không?

Không. Nó chỉ khiến compilation thất bại khi có warnings được phát ra. Class/library không bị xóa bởi flag này.

**5.** Client compile với library v1, runtime dùng library v2 đã xóa method. Có thể gặp lỗi nào?

`NoSuchMethodError` khi JVM cần phân giải call site tới method đã mất; chính xác còn phụ thuộc sự thay đổi API và đường chạy.

**6.** Vì sao `--release 17` chưa bảo đảm third-party dependency tương thích?

Vì `--release` kiểm tra level của **Java platform API** theo release; các thư viện bên ngoài cần được chọn phiên bản và kiểm thử riêng.

**7.** `jdeprscan` có thay thế toàn bộ unit/integration tests và static analysis không?

Không. Nó tập trung vào sử dụng deprecated Java platform APIs trong compiled artifacts; nó không bảo đảm phát hiện mọi lời gọi động hoặc thay đổi hành vi runtime.

**8.** Khi JDK bỏ một module như `java.xml.bind`, chỉ thêm import có giải quyết được không?

Không. Cần xác định dependency thay thế, module/classpath cấu hình, package namespace và migration phù hợp.

**9.** Vì sao method thay thế vẫn phải được test dù hết warning?

Vì replacement có thể trả giá trị khác, xử lý null/exception khác hoặc mang ràng buộc security/concurrency khác.

**10.** Nên xử lý gì trước khi nâng JDK production?

Kiểm kê deprecations/removals, đối chiếu migration guide, compile target đúng, kiểm tra binary dependencies và chạy kiểm thử trên JDK mục tiêu thật.

## 13. Checklist cuối cùng

- [ ] Đã phân biệt **deprecated**, **deprecated for removal** và **removed**?
- [ ] Đã đọc `since` đúng nghĩa là phiên bản **bắt đầu deprecated**?
- [ ] Đã bật cả hai `-Xlint:deprecation` và `-Xlint:removal` khi audit?
- [ ] Đã rà soát API replacements theo **ngữ nghĩa** chứ không chỉ theo tên?
- [ ] Đã kiểm tra `--release` và class-file target của build?
- [ ] Đã xác minh phiên bản JDK, library, module path/classpath lúc runtime?
- [ ] Đã kiểm tra JDK migration guide cho module, tool, JVM flag và hành vi bị loại bỏ?
- [ ] Đã kiểm thử cả **recompile từ source** và **chạy binary đã biên dịch** khi cần backward compatibility?
- [ ] Đã tránh dùng suppression như phương án vá lâu dài?
- [ ] Đã lên lịch sửa các API marked for removal trước khi chúng trở thành blocker?

## Tài liệu chính thức để đối chiếu

- [Oracle Java 17 – `java.lang.Deprecated`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): định nghĩa annotation, `since` và `forRemoval`.
- [Oracle Java 17 – Enhanced Deprecation](https://docs.oracle.com/en/java/javase/17/core/enhanced-deprecation1.html): ordinary/removal warnings, lint keys và `@SuppressWarnings`.
- [Oracle Java 17 – `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-Xlint`, `-Werror`.
- [Oracle Java 17 – `jdeprscan`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): kiểm tra deprecated Java platform APIs.
- [JEP 320 – Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320) và [JEP 372 – Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): ví dụ loại bỏ thực tế.

**Kết luận:** `@Deprecated` là **cảnh báo thiết kế/API**, `forRemoval=true` là **tín hiệu chuẩn bị cho việc xóa**, còn **removed** là thay đổi có thể làm source không compile hoặc binary không còn link/chạy được. Để giữ tương thích phiên bản, phải kết hợp lint warnings, quản lý release/dependencies, hiểu binary linkage và kiểm thử trên runtime mục tiêu — không chỉ ẩn warning hoặc đổi tên method.
