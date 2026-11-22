# Thực hành: Tạo adapter runtime bằng Hidden Class và MethodHandle trong Java

## 1. Bài toán cần giải quyết

Giả sử ứng dụng có nhiều hàm xử lý `String` nhưng phần còn lại của hệ thống chỉ muốn làm việc qua một hợp đồng chung:

```java
interface Adapter {
    String transform(String input);
}
```

Tại thời điểm chạy, chương trình chọn một phương thức đích — ví dụ chuẩn hóa chữ hoa hoặc thêm thẻ — rồi tạo một đối tượng triển khai `Adapter` để gọi đúng phương thức đã chọn. Bài toán gồm **hai tầng động**:

1. **`MethodHandle`** mô tả phương thức thực sự cần gọi, có chữ ký tham số và kiểu trả về rõ ràng.
2. **Hidden class** được JVM định nghĩa từ bytecode trong lúc chạy, tạo ra một loại đối tượng triển khai `Adapter` mà ứng dụng không cần công bố hay tra cứu qua tên lớp thông thường.

Bài thực hành sử dụng `MethodHandles.Lookup.defineHiddenClass`, API chính thức xuất hiện từ **Java 15** theo JEP 371 và vẫn được hỗ trợ trên các Java hiện đại. Mã mẫu biên dịch/chạy với **Java 17+**; khi triển khai thực tế nên chọn JDK/runtime còn được nhà cung cấp hỗ trợ theo chính sách dự án. Không cần API nội bộ JDK hay tính năng preview.

**Kết quả cần đạt:** cùng một hidden class có thể nhận hai `MethodHandle` khác nhau qua constructor và tạo hai adapter hoạt động theo hai chiến lược. Ví dụ chọn **mẫu class đã biên dịch sẵn** để học đúng quá trình định nghĩa hidden class; ở dự án có yêu cầu sinh cấu trúc khác nhau, bytecode có thể được tạo động bằng thư viện đáng tin cậy.

## 2. Khi nào hidden class và MethodHandle phù hợp?

### Hidden class là gì?

Một hidden class là lớp/interface được định nghĩa thông qua API lookup, thay vì được định nghĩa như một lớp ứng dụng có thể tra cứu bằng binary name thông thường. Các đặc điểm quan trọng:

- Có thể khởi tạo đối tượng, triển khai interface, có constructor và phương thức, như các lớp Java khác.
- `Class.isHidden()` trả về `true`. Bạn vẫn có thể quan sát nó qua đối tượng `Class<?>` hoặc đối tượng triển khai interface; “hidden” **không** có nghĩa không thể phản chiếu, không phải cơ chế bảo mật.
- Tên nhận từ `getName()` của hidden class chứa `/` và hậu tố do JVM tạo, **không phải binary name hợp lệ** để `Class.forName(...)` tra cứu.
- Mỗi lần định nghĩa thành công cho ra **một loại lớp riêng**, kể cả khi bytecode đầu vào giống nhau.
- Mặc định, hidden class có thể được dỡ khỏi bộ nhớ khi không còn tham chiếu giữ nó sống, dù class loader liên quan vẫn còn. Tùy chọn `STRONG` thay đổi mối quan hệ vòng đời với class loader.

Hidden class hữu ích cho các lớp triển khai phụ trợ được tạo lúc chạy, ví dụ adapter chuyên biệt, triển khai ngôn ngữ động, runtime code generation. Với adapter interface đơn giản, **lambda, method reference, `MethodHandleProxies` hoặc interface thông thường** có thể ít phức tạp hơn; chỉ dùng hidden class khi thực sự cần kiểm soát lớp được JVM định nghĩa động, quyền truy cập và vòng đời.

### MethodHandle là gì?

`java.lang.invoke.MethodHandle` là tham chiếu đến một thao tác có thể gọi, ví dụ static method, instance method, constructor hay truy cập trường. Khác với một con trỏ “chung chung”, mỗi handle có `MethodType` mô tả rõ các tham số và kiểu trả về.

Ví dụ:

```java
MethodType targetType =
        MethodType.methodType(String.class, String.class);
MethodHandle target = MethodHandles.lookup().findStatic(
        HiddenAdapterDemo.class, "upper", targetType);
```

Đoạn này chỉ hợp lệ khi đặt trong ngữ cảnh có thể truy cập `HiddenAdapterDemo.upper`, ví dụ ngay bên trong `HiddenAdapterDemo` như chương trình hoàn chỉnh bên dưới. Chữ ký mục tiêu là **`(String)String`**: nhận một `String` và trả về một `String`.

`invokeExact` yêu cầu kiểu tại call site trùng chính xác với `MethodType` của handle; nếu lệch có thể ném `WrongMethodTypeException`. `asType` tạo handle thích ứng với kiểu được yêu cầu khi có phép chuyển đổi hợp lệ. Phải phân biệt:

- `MethodHandle`: **điểm gọi thao tác**.
- Hidden class: **loại đối tượng** được tạo lúc runtime.
- Interface `Adapter`: **hợp đồng tĩnh** mà ứng dụng sẽ sử dụng.

## 3. Luồng tạo runtime adapter

```text
                Bytecode "AdapterTemplate.class"
                               |
                 Lookup.defineHiddenClass(...)
                               |
                      hidden Lookup
                               |
                hidden Lookup.findConstructor
                               |
          asType((MethodHandle) -> Adapter)
                               |
      +------------------------+----------------------+
      |                                               |
  target "upper"                                  target "tag"
      |                                               |
  Adapter a                                      Adapter b
      |                                               |
  a.transform(...)                               b.transform(...)
      |                                               |
  MethodHandle.invokeExact                    MethodHandle.invokeExact
```

Các bước thực tế:

1. Biên dịch một **template class** có constructor nhận `MethodHandle` và method triển khai interface. Trong bài tập, template được đặt trong cùng file nguồn Java với class public để dễ theo dõi.
2. Khi chương trình chạy, đọc **bytecode `AdapterTemplate.class`** từ classpath dưới dạng `byte[]`.
3. Dùng `MethodHandles.lookup().defineHiddenClass(bytes, true)`. Bytecode phải thuộc **cùng package** với lookup class; lookup cần quyền tương ứng.
4. Lấy `Lookup` được trả về và tìm constructor của **chính hidden class**. Không dùng `Class.forName` để tìm lớp ẩn.
5. Chuyển kiểu factory handle từ trả về loại hidden cụ thể sang trả về interface `Adapter` bằng `asType`.
6. Truyền từng target `MethodHandle` vào factory, tạo adapter và gọi qua interface.

**Lưu ý về giới hạn ví dụ:** bytecode template là classfile được biên dịch trước, và file đó cũng tồn tại trên classpath. Bản hidden do `defineHiddenClass` định nghĩa **là một class khác** với bản named template; trong ví dụ không cần load bản named template. “Tạo adapter tại runtime” ở đây nghĩa là **định nghĩa lớp ẩn và gắn target lúc chạy**, không phải trình bày một bytecode generator hoàn chỉnh.

## 4. Code Java hoàn chỉnh

Tạo tệp **`src/demo/adapter/HiddenAdapterDemo.java`** với nội dung sau. Một tệp nguồn có **một public class** và thêm một top-level class không `public` cùng package: `javac` sẽ tạo hai classfile. Giữ cả hai trong cùng package để `defineHiddenClass` được phép định nghĩa template.

```java
package demo.adapter;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class HiddenAdapterDemo {
    // API mà phần còn lại của ứng dụng cần biết.
    public interface Adapter {
        String transform(String input);
    }

    // Hai mục tiêu khác nhau; các method này là private.
    private static String upper(String input) {
        return input.trim().toUpperCase(Locale.ROOT);
    }

    private static String tag(String input) {
        return "<" + input + ">";
    }

    public static void main(String[] args) throws Throwable {
        // 1. Lấy lookup từ chính host class.
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType targetType =
                MethodType.methodType(String.class, String.class);

        // Lookup của host có quyền tham chiếu private static methods.
        MethodHandle upper = lookup.findStatic(
                HiddenAdapterDemo.class, "upper", targetType);
        MethodHandle tag = lookup.findStatic(
                HiddenAdapterDemo.class, "tag", targetType);

        // 2. Đọc classfile đã compile từ classpath.
        byte[] bytes;
        try (InputStream in = HiddenAdapterDemo.class
                .getResourceAsStream("AdapterTemplate.class")) {
            if (in == null) {
                throw new IOException("AdapterTemplate.class not found");
            }
            bytes = in.readAllBytes();
        }

        // 3. Định nghĩa một hidden class tại runtime.
        MethodHandles.Lookup hiddenLookup =
                lookup.defineHiddenClass(bytes, true);
        Class<?> hiddenClass = hiddenLookup.lookupClass();

        // 4. Constructor thực tế: (MethodHandle) -> hiddenClass.
        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenClass,
                MethodType.methodType(void.class, MethodHandle.class));

        // 5. Thích ứng kiểu trả về sang interface Adapter.
        MethodHandle factory = constructor.asType(
                MethodType.methodType(Adapter.class, MethodHandle.class));

        // 6. Tạo hai adapter, mỗi adapter giữ một method handle.
        Adapter a = (Adapter) factory.invokeExact(upper);
        Adapter b = (Adapter) factory.invokeExact(tag);

        System.out.println("upper=" + a.transform("  java 15  "));
        System.out.println("tag=" + b.transform("Java"));
        System.out.println("hidden=" + hiddenClass.isHidden());
        System.out.println("sameClass=" + (a.getClass() == b.getClass()));
        System.out.println(
                "binaryName=" + !hiddenClass.getName().contains("/"));
        System.out.println(
                "canonicalName=" + hiddenClass.getCanonicalName());
    }
}

// Template chỉ là nguồn bytecode; đối tượng được tạo từ hidden copy.
final class AdapterTemplate implements HiddenAdapterDemo.Adapter {
    private final MethodHandle target;

    AdapterTemplate(MethodHandle target) {
        MethodType expected =
                MethodType.methodType(String.class, String.class);
        if (!expected.equals(target.type())) {
            throw new IllegalArgumentException(
                    "Expected (String)String, got " + target.type());
        }
        this.target = target;
    }

    @Override
    public String transform(String input) {
        try {
            // Call site nhận String và trả String: khớp target.type().
            return (String) target.invokeExact(input);
        } catch (RuntimeException | Error ex) {
            throw ex;
        } catch (Throwable ex) {
            // Interface không khai báo checked exception.
            throw new IllegalStateException("Target failed", ex);
        }
    }
}
```

### Build và chạy

Yêu cầu: **JDK 17+** và classpath có hai classfile do `javac` tạo ra. Tại thư mục chứa thư mục `src`, tạo thư mục `out` trước rồi chạy:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/demo/adapter/HiddenAdapterDemo.java
java -cp out demo.adapter.HiddenAdapterDemo
```

Kết quả có hai classfile cần thiết:

```text
out/demo/adapter/HiddenAdapterDemo.class
out/demo/adapter/HiddenAdapterDemo$Adapter.class
out/demo/adapter/AdapterTemplate.class
```

**Stdout chính xác:**

```text
upper=JAVA 15
tag=<Java>
hidden=true
sameClass=true
binaryName=false
canonicalName=null
```

Mẫu đã được kiểm tra thực tế bằng **JDK 24** với `javac --release 17`: biên dịch thành công và stdout khớp sáu dòng trên.

Giải thích kết quả:

- `upper=JAVA 15`: adapter `a` gọi `upper` qua `MethodHandle`; `trim()` xóa khoảng trắng và `Locale.ROOT` giúp thao tác chữ hoa không phụ thuộc locale mặc định.
- `tag=<Java>`: cùng loại hidden adapter nhưng target `tag` khác, nên hành vi khác.
- `hidden=true`: `lookupClass()` thực sự trả về hidden class.
- `sameClass=true`: hai đối tượng được tạo bằng **một hidden class đã định nghĩa**, mỗi đối tượng mang target riêng.
- `binaryName=false`: tên hidden class chứa dấu `/`, không thể dùng làm binary name để tìm bằng `Class.forName`.
- `canonicalName=null`: hidden class không có canonical name thông thường.

Tên classfile `HiddenAdapterDemo$Adapter.class` chứa `$` vì `Adapter` là interface lồng trong `HiddenAdapterDemo`. Đó là tên tệp thực tế, không phải lệnh phải tự gõ. Chương trình dùng `getResourceAsStream("AdapterTemplate.class")` nên **không cần biết absolute path hoặc hard-code đường dẫn bên ngoài classpath**.

## 5. Tại sao ví dụ này thật sự dùng được MethodHandle?

### 5.1. Handle giữ quyền truy cập đã được kiểm tra khi tạo

Hai phương thức `upper` và `tag` đều là **private** của `HiddenAdapterDemo`. `MethodHandles.lookup()` được gọi bên trong chính class đó nên có thể lấy handle qua `findStatic`. Sau đó, template hidden nhận handle như một giá trị constructor và gọi `invokeExact` mà **không cần tự đọc private method bằng reflection**.

Quyền truy cập của `MethodHandle` được kiểm tra khi tạo handle; việc truyền một handle có quyền gọi private method cho code khác chính là truyền một **capability**. Vì thế, không phát tán handle đến mã không tin cậy nếu việc gọi phương thức đích không được phép.

### 5.2. Chữ ký chính xác là phần quan trọng nhất

Trong mã trên, kiểu đích là:

```java
MethodType.methodType(String.class, String.class)
```

Có thể đọc là `(String)String`. Trong template:

```java
return (String) target.invokeExact(input);
```

Kiểu tĩnh của `input` là `String`, kiểu kết quả tại call site được xác định bởi cast `(String)`. JVM kiểm tra đúng cả hai; nếu handle thực tế là `(int)int` mà đem gọi như `(String)String` thì `invokeExact` sẽ không tự chuyển kiểu và có thể ném `WrongMethodTypeException`.

Constructor bảo vệ vấn đề này ngay lúc tạo adapter:

```java
if (!expected.equals(target.type())) {
    throw new IllegalArgumentException(
            "Expected (String)String, got " + target.type());
}
```

Vì vậy, adapter lỗi chữ ký bị từ chối **trước lần transform đầu tiên**.

### 5.3. Vì sao factory phải gọi `asType`?

`findConstructor(hiddenClass, methodType(void.class, MethodHandle.class))` trả về một handle có kiểu:

```text
(MethodHandle)HiddenClass
```

Tên `HiddenClass` là ký hiệu cho đối tượng `Class<?>` động được JVM tạo; tên binary cụ thể không thể viết trực tiếp trong mã nguồn. Nếu cố gọi:

```java
Adapter a = (Adapter) constructor.invokeExact(upper);
```

thì kiểu trả về suy ra tại call site là `Adapter`, nhưng handle thực tế trả về chính **hiddenClass**: chữ ký **không khớp tuyệt đối**. Cách đúng trong ví dụ:

```java
MethodHandle factory = constructor.asType(
        MethodType.methodType(Adapter.class, MethodHandle.class));
Adapter a = (Adapter) factory.invokeExact(upper);
```

`asType` thích ứng kết quả từ hidden class sang interface mà hidden class **thực sự triển khai**. Sau khi thích ứng, kiểu factory là `(MethodHandle)Adapter`, khớp đúng call site `invokeExact`.

`asType` không cho phép “ép bừa”: chỉ những phép chuyển đổi hợp lệ mới dùng được. Một phiên bản adapter không triển khai `Adapter` sẽ không thể tạo đối tượng thỏa hợp đồng này bằng lời cast vô căn cứ.

## 6. Phân biệt hidden class với class bình thường

| Tiêu chí | Class bình thường | Hidden class |
|---|---|---|
| Định nghĩa thường gặp | JVM/class loader đọc theo binary name; có thể qua `ClassLoader#defineClass` | `Lookup#defineHiddenClass` từ `byte[]` |
| Có thể dùng `Class.forName(binaryName)` | Thường có, nếu class loader nhìn thấy | Không thể tra cứu **hidden copy** qua tên |
| Có đối tượng `Class<?>` | Có | Có |
| Có thể triển khai interface và tạo instance | Có | Có |
| Tên `getName()` | Binary name bình thường | Tên có hậu tố riêng chứa `/` |
| `isHidden()` | `false` | `true` |
| Vòng đời mặc định | Gắn mạnh với class loader định nghĩa | Có thể được dỡ khi không còn tham chiếu giữ lớp sống, dù loader còn |
| Dùng cho public API dài hạn | Thường phù hợp | Thường phù hợp hơn với lớp triển khai nội bộ được tạo lúc chạy |

Trong ví dụ, `AdapterTemplate.class` **vẫn là một classfile có tên bình thường trên classpath**. Người dùng có thể load bản named template bằng tên thông thường nếu truy cập được. Tuy nhiên **hidden copy** được `defineHiddenClass` tạo ra có **class identity riêng**; đừng nhầm hai thực thể này. Chương trình chủ động chỉ thao tác qua `hiddenLookup.lookupClass()` và factory của hidden copy.

Một hidden class mới định nghĩa từ cùng mảng byte cũng sẽ có identity khác. Điều này có ích cho adapter chuyên biệt theo từng đợt/cấu hình, nhưng tạo quá nhiều hidden class khi xử lý mỗi request có thể làm tăng chi phí định nghĩa, verify, link và sử dụng bộ nhớ class metadata. Nên tái sử dụng class/factory theo nhu cầu.

## 7. Quyền lookup, package, module và nestmate

`defineHiddenClass` không phải API tự do nạp bytecode vào bất kỳ package nào:

1. **`Lookup` phải có đủ quyền**. `MethodHandles.lookup()` trong class tự quản lý hợp lý cho ví dụ; `publicLookup()` không có đầy đủ đặc quyền cần thiết.
2. Bytecode được định nghĩa phải có tên class thuộc **cùng package** với lookup class. Ở đây cả `HiddenAdapterDemo` và `AdapterTemplate` đều nằm trong `demo.adapter`.
3. Lookup và module/ranh giới truy cập vẫn có hiệu lực. Không nên tìm cách đi vòng quyền Java Platform Module System (JPMS) bằng class ẩn.
4. `defineHiddenClass(bytes, true)` có tham số `initialize=true`, nghĩa là khởi tạo lớp đã định nghĩa trước khi trả về. Chỉ dùng `false` khi thực sự muốn để JVM khởi tạo sau theo quy tắc thông thường.

### `NESTMATE` có cần trong ví dụ không?

Không. Template chỉ gọi `MethodHandle` đã được tạo hợp lệ trong host; nó **không trực tiếp truy cập trường/phương thức private của host**. Vì vậy mẫu dùng:

```java
lookup.defineHiddenClass(bytes, true);
```

Nếu thiết kế bytecode của hidden class cần trở thành **nestmate** của lookup class để trực tiếp truy cập thành viên private trong cùng nest, API hỗ trợ:

```java
lookup.defineHiddenClass(
        bytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
```

Đây là **đoạn API minh họa**, không yêu cầu thay đổi mẫu đang chạy. `NESTMATE` cấp quyền truy cập private theo quy tắc nest; chỉ bật khi có nhu cầu thật. Không coi tùy chọn này là một cách mở quyền truy cập vào class của module/package không liên quan.

### `STRONG` ảnh hưởng gì?

`MethodHandles.Lookup.ClassOption.STRONG` yêu cầu hidden class có quan hệ mạnh với defining class loader, giống lớp thông thường. Mặc định không bật `STRONG`, hidden class có thể bị unload khi không còn được tham chiếu, dù loader còn tồn tại.

Điều này không có nghĩa tạo xong là lớp bị xóa ngay: reference tới `Class<?>`, instance, `Lookup` hoặc `MethodHandle` liên quan có thể giữ hidden class còn sống. Đối với adapter ngắn hạn, mặc định thường phù hợp; với cache vòng đời dài, hãy thiết kế cách giữ và giải phóng tham chiếu một cách có chủ đích. Không dùng `STRONG` vô điều kiện.

## 8. Kiểm thử runtime adapter

Các bài test quan trọng là **hành vi**, **kiểu**, **identity**, **điều kiện lỗi** và **vòng đời**.

| Ca kiểm thử | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Tạo hidden class | `defineHiddenClass(bytes, true)` | `lookupClass().isHidden()` là `true` |
| Bind target số 1 | Handle `upper(String)` | `"  java 15  "` → `"JAVA 15"` |
| Bind target số 2 | Handle `tag(String)` | `"Java"` → `"<Java>"` |
| Interface | Hai instance do factory tạo | Cả hai là `Adapter` và gọi được `transform` |
| Cùng một hidden class | Hai instance từ cùng factory | `a.getClass() == b.getClass()` |
| Hai lần định nghĩa lớp | Gọi `defineHiddenClass` hai lần với cùng bytes | Hai giá trị `Class<?>` là **khác nhau** |
| Sai chữ ký target | Target kiểu `(int)int` | Constructor từ chối bằng `IllegalArgumentException` |
| Mất resource | Không đóng gói `AdapterTemplate.class` | Báo rõ resource không tìm thấy (mẫu ném `IOException`) |
| Lookup thiếu quyền / khác package | Lookup hoặc classfile không phù hợp | Định nghĩa thất bại; báo lỗi gốc, không bỏ qua |
| Gọi target ném lỗi | Target ném `RuntimeException` | Adapter chuyển tiếp exception; checked `Throwable` được bọc như mã mẫu |
| Tên lớp ẩn | `hiddenClass.getName()` | Có `/`; không khẳng định suffix `/0x...` cố định |
| Đo vòng đời | Bỏ tham chiếu tới lớp/instance/handle | Không viết test yêu cầu GC xảy ra ngay lập tức |

### Kiểm thử một target có sai kiểu

Có thể thêm **đoạn sau trong `main`** sau khi đã tạo `factory`:

```java
MethodHandle wrongTarget = lookup.findStatic(
        Math.class, "abs", MethodType.methodType(int.class, int.class));

try {
    Adapter invalid = (Adapter) factory.invokeExact(wrongTarget);
    throw new AssertionError("Expected wrong target type to be rejected");
} catch (IllegalArgumentException expected) {
    System.out.println("wrongTypeRejected=true");
}
```

Đoạn này **không có trong chương trình chính ở mục 4**, nên nếu thêm thì stdout sẽ có một dòng mới:

```text
wrongTypeRejected=true
```

Lỗi bị phát hiện ngay trong constructor `AdapterTemplate`, vì `wrongTarget.type()` là `(int)int`, trong khi adapter yêu cầu `(String)String`. Đây là kiểm tra contract riêng; nó khác với việc cố gọi nhầm `invokeExact` và đợi `WrongMethodTypeException`.

### Chú ý khi test unload và hiệu năng

Không nên assert GC sẽ unload lớp trong một khoảng mili giây cố định: garbage collection không có cam kết thời điểm. Nếu phải đo unload, dùng bài test quan sát với công cụ JDK/JFR và nhiều lượt chạy, ghi rõ runtime và GC. Tương tự, một phép đo microbenchmark đơn lẻ không chứng minh `MethodHandle` luôn nhanh hơn reflection hoặc một phương thức Java trực tiếp; JIT và cách tổ chức call site ảnh hưởng lớn.

## 9. Từ ví dụ đến adapter dùng trong dự án

### 9.1. Khi cần thay đổi mục tiêu động

Trong ví dụ, một class hidden được dùng với nhiều handle. Một factory có thể cache:

```text
hidden class + constructor handle -> (MethodHandle)Adapter
```

Sau đó tầng ứng dụng tạo adapter theo cấu hình. Khi phương thức đích nằm ở một object instance, `Lookup.findVirtual` trả về handle gồm cả receiver. Có thể dùng `bindTo(receiver)` để gắn receiver và đưa handle về chữ ký `(String)String`:

```java
// Minh họa khi Service có String process(String).
MethodHandle method = lookup.findVirtual(
        Service.class,
        "process",
        MethodType.methodType(String.class, String.class));
MethodHandle bound = method.bindTo(service);
```

Đây là **đoạn minh họa**, cần khai báo `Service`, `service` và một lookup có quyền truy cập thích hợp. Sau `bindTo(service)`, handle sẽ không còn tham số receiver ở đầu. Chỉ truyền vào template khi `bound.type()` đúng `(String)String`.

Khi mục tiêu có chữ ký khác (ví dụ `(CharSequence)String`), hãy quyết định có chuyển đổi hợp lệ qua `asType` hay cần viết adapter logic rõ ràng. Không đánh đổi kiểm soát kiểu chỉ để làm cho mọi signature “chạy được”.

### 9.2. Khi cần bytecode thực sự mới

Có hai biến thể triển khai cần phân biệt:

- **Template + hidden definition:** như chương trình mục 4; bytecode cấu trúc sẵn, target chọn lúc chạy.
- **Generated bytecode + hidden definition:** xây `byte[]` cho một class mới bằng công cụ hỗ trợ classfile/JVM đáng tin cậy, sau đó định nghĩa qua `defineHiddenClass`. Cách này hợp lý nếu adapter cần phương thức, trường hay luồng điều khiển chuyên biệt, nhưng phải quản lý verifier, constant pool, package, Java class-file version và quyền truy cập.

Bài tập chọn phương án đầu để tập trung vào hai API chính mà không phụ thuộc thư viện bytecode bên ngoài. Đừng dùng API nội bộ không được hỗ trợ của JDK để dựng bytecode khi có lựa chọn công khai phù hợp.

### 9.3. Khi nào nên chọn phương án đơn giản?

Nếu chỉ muốn chuyển một hàm sang một interface chức năng, lambda/method reference hoặc một adapter class thường dễ viết và bảo trì hơn. Hidden class có giá trị khi cần **định nghĩa loại lớp phụ trợ lúc runtime**, identity/vòng đời linh hoạt hoặc thực thi bytecode chuyên biệt. Không dùng hidden class như một lớp bảo vệ thông tin: mã bytecode không đáng tin cậy vẫn có thể thực thi trong môi trường và phạm vi đặc quyền mà bạn cấp.

## 10. Những lỗi phổ biến và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `AdapterTemplate.class not found` | Bản build chỉ đóng gói class public hoặc thiếu resource | Kiểm tra file `out/demo/adapter/AdapterTemplate.class` và JAR/classpath |
| `IllegalArgumentException` tại `defineHiddenClass` | Bytecode của package khác với lookup hoặc classfile không hợp lệ cho API | Kiểm tra package khai báo trong classfile và lookup class |
| `IllegalAccessException` tại `defineHiddenClass` | Lookup thiếu quyền cần thiết | Lấy lookup trong class hợp lệ, kiểm tra ranh giới module/package |
| `NoSuchMethodException` khi `findConstructor` | Constructor không khớp `(MethodHandle)void` | Kiểm tra chính xác kiểu tham số và bytecode template |
| `WrongMethodTypeException` | `invokeExact` dùng descriptor khác `MethodHandle.type()` | Đối chiếu static argument/return types; thích ứng bằng `asType` khi hợp lệ |
| `IllegalArgumentException` từ constructor template | Handle đích không có chữ ký `(String)String` | Chuẩn hóa hoặc từ chối target ngay lúc bind |
| `ClassCastException` khi ép sang `Adapter` | Hidden class thực tế không triển khai interface mong đợi | Sửa template, không chỉ ép kiểu |
| `ClassNotFoundException` khi tìm tên hidden class | Hidden class không tìm bằng tên theo class loader | Giữ `Class<?>` và `Lookup` trả về từ `defineHiddenClass` |
| Dùng `publicLookup()` và lỗi quyền | Lookup công khai không đủ đặc quyền | Dùng lookup có quyền phù hợp theo API |
| Chương trình có nhiều lớp bị định nghĩa vô hạn | Tạo hidden class mỗi request hoặc giữ reference lâu | Cache factory, đặt chính sách vòng đời và quan sát class metadata |
| Kết quả test khác do locale | Hàm chuẩn hóa phụ thuộc default locale | Dùng `Locale.ROOT` khi logic yêu cầu quy tắc locale trung lập |

**Không xử lý lỗi tạo lớp bằng cách âm thầm retry với bytecode khác hoặc bỏ qua exception.** Hãy log package, chữ ký mục tiêu và nguyên nhân phù hợp; không log bytecode/handle nhạy cảm nếu chúng có thể lộ logic nội bộ.

## 11. Bài tập củng cố

**Bài 1 — Thêm một target mới.** Viết phương thức `private static String brackets(String input)` trả về `"[" + input + "]"`. Tìm handle qua `lookup.findStatic`, truyền vào `factory`. Với `"A"`, đáp án là `[A]`. Không cần định nghĩa thêm hidden class vì contract vẫn `(String)String`.

**Bài 2 — Hai lần gọi `defineHiddenClass`.** Dùng cùng `bytes` để định nghĩa hai lần, lấy `Class<?>` từ hai lookup trả về và so sánh bằng `==`. Đáp án: `false` — chúng là hai class identity khác nhau. Chương trình mục 4 chỉ định nghĩa **một lần**, nên hai adapter ở đó có cùng class identity.

**Bài 3 — Thay target bằng `Math.abs(int)`.** Dùng `MethodHandles.lookup().findStatic(Math.class, "abs", MethodType.methodType(int.class, int.class))` rồi truyền vào factory. Adapter từ chối với `IllegalArgumentException` do sai contract `(String)String`. Không sửa bằng cách bỏ kiểm tra chữ ký rồi hy vọng `invokeExact` tự chuyển kiểu.

**Bài 4 — Vì sao hidden class vẫn implement được `Adapter`?** Vì classfile template khai báo `implements HiddenAdapterDemo.Adapter` và việc định nghĩa hidden class bảo toàn khả năng thực thi/quan hệ kiểu của lớp đó. “Hidden” làm thay đổi khả năng tra cứu theo tên và cơ chế vòng đời, không cấm ép kiểu tới interface đã triển khai.

**Bài 5 — `NESTMATE` có cần để gọi private `upper` không?** Trong mẫu này **không**. `upper` đã được lookup hợp lệ trong host chuyển thành `MethodHandle`. Hidden template chỉ gọi handle đó. Chỉ cần `NESTMATE` nếu bytecode hidden class muốn **trực tiếp** truy cập thành viên private thuộc cùng nest theo cơ chế của JVM.

**Bài 6 — Có nên tạo một hidden class cho mỗi request?** Thông thường không. Định nghĩa class mới tốn chi phí và việc giữ quá nhiều `Class<?>`/`Lookup`/`MethodHandle` có thể làm bộ nhớ class metadata tăng. Dùng một hidden class/factory có cache khi các request dùng chung cấu trúc adapter; tạo bản mới khi thật sự cần identity hoặc cấu trúc bytecode riêng.

## 12. Checklist trước khi đưa vào sản phẩm

1. Xác nhận mục tiêu **thật sự cần hidden class**, hoặc có thể dùng adapter Java thường/lambda.
2. Định nghĩa interface và **MethodType contract** trước khi tạo bytecode.
3. Dùng **lookup hợp lệ**, đúng package và module; giảm đặc quyền như `NESTMATE` nếu không cần.
4. Chỉ sử dụng **class bytes đáng tin cậy**; hidden class không sandbox bytecode.
5. Kiểm tra nguồn classfile sau đóng gói; thử cả chạy từ thư mục classpath và artifact thực tế.
6. Chuẩn hóa và kiểm tra **chữ ký handle** trước lần gọi đầu tiên.
7. Phân biệt **hidden class identity** với bản template classfile có tên bình thường.
8. Lập chiến lược cache, vòng đời và quan sát chi phí định nghĩa class trong production.
9. Test tạo adapter, chọn target, xử lý exception và chạy trên JDK thực tế.
10. Dùng phiên bản Java hiện được tổ chức hỗ trợ và kiểm thử khi nâng runtime.

## 13. Ghi nhớ

Một **runtime adapter bằng hidden class + MethodHandle** gồm ba phần phối hợp: **hợp đồng interface**, **bytecode được định nghĩa thành hidden class tại runtime**, và **handle trỏ đến phương thức đích**. `defineHiddenClass` tạo lớp; `findConstructor` kết hợp `asType` tạo factory an toàn về kiểu; `invokeExact` gọi target bằng chữ ký chính xác.

Hidden class giải quyết việc **định nghĩa và quản lý lớp triển khai động**. MethodHandle giải quyết việc **tham chiếu và gọi hành vi động**. Dùng cả hai khi lợi ích tương xứng với độ phức tạp, quản lý quyền lookup và bộ nhớ rõ ràng.

### Tài liệu chính thức để đọc thêm

- [OpenJDK JEP 371 — Hidden Classes (Java 15)](https://openjdk.org/jeps/371)
- [Java SE 25 — MethodHandles.Lookup: defineHiddenClass, findConstructor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 25 — MethodHandle: invokeExact, invoke, asType, bindTo](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 25 — MethodHandles.Lookup.ClassOption: NESTMATE, STRONG](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html)
- [Java SE 25 — Class.isHidden](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)
- [Oracle JDK 15 Release Notes — Hidden Classes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html)
