# Class.forName(Module, name) và trường hợp không tìm thấy lớp

## 1. Vấn đề cần giải quyết

Trong Java 9+ (bao gồm Java 17 và Java 21), ngoài các overload quen thuộc của `Class.forName`, Java cung cấp:

~~~java
public static Class<?> forName(Module module, String name)
~~~

Đây là API **tìm lớp theo một `Module` cụ thể**, phù hợp khi ứng dụng cần làm việc với **Java Platform Module System (JPMS)**. Nó có hai khác biệt đặc biệt dễ nhầm:

- **Không tìm thấy lớp trong module chỉ định → trả về `null`.** Đây **không** phải đường đi thông thường ném `ClassNotFoundException` như `Class.forName(String)` hoặc `Class.forName(String, boolean, ClassLoader)`.
- **Không tự liên kết hoặc khởi tạo lớp.** Theo hợp đồng của overload này, phương thức cố gắng **locate/load** class hoặc interface, **không link class, không chạy class initializer**.

Ngoài trường hợp thực sự không có định nghĩa lớp, `null` cũng có thể là kết quả khi tên lớp thuộc **module khác**, kể cả trong trường hợp loader của module được yêu cầu có thể nạp lớp đó. Bởi vậy, từ `result == null` **không thể suy ra duy nhất** rằng bytecode hoặc JAR bị thiếu.

### Bạn sẽ học được

1. Hiểu chính xác ý nghĩa hai tham số `Module module` và `String name`.
2. Phân biệt **đúng module**, **sai module** và **không có lớp theo tên**.
3. Xử lý `null` an toàn, tránh `NullPointerException` do lập tức gọi method trên kết quả.
4. Phân biệt overload theo `Module` với overload theo tên và `ClassLoader`.
5. Giải thích việc tìm được `Class<?>` **không chứng minh** đã liên kết, khởi tạo hoặc được phép truy cập lớp.
6. Biên dịch và chạy ví dụ JPMS Java 17+ kiểm chứng đủ bốn trường hợp: tìm được, thiếu tên, sai module, và không kích hoạt initialization.

## 2. Ý nghĩa của API và các tham số

~~~java
Class<?> result = Class.forName(module, "com.example.MyService");
~~~

- `module` là **đối tượng `java.lang.Module`**, không phải tên module dạng `String`. Có thể lấy từ `SomeClass.class.getModule()` hoặc từ `ModuleLayer.findModule(...)` sau khi module đã được resolve.
- `name` là **binary name** của class/interface được tìm, ví dụ `"java.lang.String"` hoặc `"com.example.Outer$Inner"` đối với lớp lồng nhau.
- Kết quả kiểu `Class<?>` nếu tên thuộc lớp nằm trong module được yêu cầu và việc tìm/nạp thành công.
- Kết quả `null` nếu **không tìm được class trong module được chỉ định**.
- Phương thức được giới thiệu từ **Java 9**.

Cần hiểu “tìm trong module” là **giới hạn xác định kết quả trả về**; một loader có thể định nghĩa nhiều named modules hoặc một named và một unnamed module. Việc chỉ truyền đúng loader chưa đủ để biết class thuộc module nào.

### Module, package, ClassLoader và class là bốn thứ khác nhau

~~~text
ModuleLayer
  └── Module "shop.api"
       ├── package "shop.api"
       │    └── class "shop.api.Service"
       └── ánh xạ tới một defining ClassLoader

Class.forName(module, "shop.api.Service")
    │
    ├── định nghĩa lớp đúng thuộc module?  -> Class<?>
    └── không có lớp đúng module?          -> null
~~~

Một `Module` có tên là **named module**. Một class thông thường trên classpath thuộc **unnamed module** của defining loader. API nhận chính đối tượng `Module` và áp dụng cho module phù hợp, không chỉ nhận một tên module trên module path.

Với named module, hãy bắt đầu từ thông tin thực tế:

~~~java
Module actual = SomeType.class.getModule();
System.out.println(actual.getName());  // tên module, hoặc null nếu unnamed
System.out.println(actual.isNamed());   // true với named module
~~~

Hai dòng là **mã minh họa bên trong một phương thức**; chưa phải chương trình runnable độc lập.

## 3. Trường hợp trả về `null`

### 3.1. Tên lớp thực sự không tồn tại trong module

~~~java
Module base = String.class.getModule(); // java.base

Class<?> missing =
        Class.forName(base, "java.lang.NoSuchType");

System.out.println(missing == null);    // true
~~~

Điều này khác với:

~~~java
Class.forName("java.lang.NoSuchType");
~~~

Overload một tham số trên sẽ ném `ClassNotFoundException` (nếu không có lớp cùng tên và không phát sinh lỗi khác).

Khi dùng overload theo module, **`null` là giá trị kết quả hợp lệ cần xử lý**, không phải một exception cần catch.

### 3.2. Lớp tồn tại nhưng nằm trong module khác

Ví dụ:

~~~java
Module base = String.class.getModule(); // java.base
Class<?> other = Class.forName(
        base, "java.util.logging.Logger");
System.out.println(other == null); // true
~~~

`java.util.logging.Logger` là một class có thật, nhưng thuộc **module `java.logging`**, không thuộc `java.base`. Kết quả vì thế là `null` trong cấu hình Java tiêu chuẩn của ví dụ.

Nếu truyền đúng module:

~~~java
Module logging = java.util.logging.Logger.class.getModule();
Class<?> found = Class.forName(
        logging, "java.util.logging.Logger");
System.out.println(found == java.util.logging.Logger.class); // true
~~~

**Điểm tinh tế của hợp đồng:** nếu ClassLoader được gán cho module `M` cũng định nghĩa các module khác, phương thức có thể **load thành công** một class trong module khác rồi vẫn trả về `null` vì class đó **không thuộc `M`**. Kết quả `null` không bắt buộc có nghĩa loader không tìm được bytecode.

Vì vậy, không nên dùng:

~~~java
if (Class.forName(requestedModule, name) == null) {
    // KHÔNG đủ bằng chứng để khẳng định "JAR không tồn tại"
}
~~~

Đoạn trên là ví dụ về **suy luận không hợp lệ**, không phải chương trình độc lập. Cần kiểm tra đúng module, tên nhị phân, module resolution và các nguồn chứa class trước khi kết luận.

### 3.3. Tên không đúng định dạng kỳ vọng hoặc không phải class được hỗ trợ

API yêu cầu **binary name** của class/interface, không phải đường dẫn file, không phải tên package, và không hỗ trợ array types.

| `name` | Nhận xét |
|---|---|
| `"java.lang.String"` | Binary name hợp lệ cho lớp `String`; phải đi cùng module `java.base` |
| `"java.util.Map$Entry"` | Binary name của nested interface `Entry` |
| `"java.util.Map.Entry"` | Tên source/canonical dạng lồng, **không phải** binary name đúng của `Entry` |
| `"java/lang/String.class"` | Đường dẫn tài nguyên class, không phải binary name |
| `"[Ljava.lang.String;"` | Descriptor/array name; overload theo `Module` **không hỗ trợ array types** |
| `"int"` hoặc `"void"` | Không dùng API này để thu được primitive/void `Class` objects |

Để lấy `Class` của primitive/void, dùng `int.class` hoặc `void.class`. Để lấy class của array, dùng `String[].class` hoặc API theo loader phù hợp với array-name syntax. Không nên xem `Class.forName(module, "[Ljava.lang.String;")` là API thay thế hợp lệ cho array class.

### 3.4. Trường hợp module chưa được resolve

Một module JAR có mặt trên `--module-path` chưa chắc đã được **resolve** vào boot layer hoặc layer tùy chỉnh. Nếu bạn chưa có `Module` object tương ứng, vấn đề cần giải quyết trước tiên là **module resolution**, không phải gọi `Class.forName(module, name)`.

Ví dụ kiểm tra có chọn module hay không:

~~~java
Module module = ModuleLayer.boot()
        .findModule("shop.api")
        .orElse(null);
~~~

Nếu `module == null`, điều đó cho biết **không tìm thấy module theo tên trong phạm vi layer lookup này**. Nó chưa chứng minh JAR `shop.api` không tồn tại trên ổ đĩa. Cần kiểm tra module path, root modules, `requires` và `Configuration`.

**Quan trọng:** không được gọi `Class.forName(null, name)`. Overload theo module sẽ ném `NullPointerException` nếu `module` hoặc `name` là `null`.

## 4. Không liên kết và không khởi tạo: ý nghĩa chính xác

### 4.1. Phân biệt các giai đoạn

- **Loading:** tìm và định nghĩa biểu diễn runtime của một class/interface.
- **Linking:** verification, preparation và resolution theo quy định JVM.
- **Initialization:** chạy class initializer, bao gồm các biểu thức và khối `static` tương ứng.

Theo Java SE 17/21 `Class` Javadoc, overload:

~~~java
Class.forName(module, binaryName)
~~~

**cố gắng locate/load**, **không link** và **không chạy class initializer**. Đây là phát biểu về **hợp đồng phương thức**; không phải cam kết rằng class chưa bao giờ được JVM xử lý thêm vì các thao tác độc lập khác.

Đối chiếu các overload:

| API | Phạm vi yêu cầu | Khi không tìm thấy | Linking và initialization |
|---|---|---|---|
| `Class.forName(Module, String)` | Class **thuộc module chỉ định** | **Trả `null`** | Không tự link, không chạy initializer |
| `Class.forName(String)` | Theo defining loader của caller trong tình huống thông thường | **`ClassNotFoundException`** | Yêu cầu initialization nếu cần; kéo theo linking |
| `Class.forName(String, false, ClassLoader)` | Theo loader chỉ định | **`ClassNotFoundException`** | Không yêu cầu initialization; vẫn có thể load/link theo hợp đồng overload |
| `Class.forName(String, true, ClassLoader)` | Theo loader chỉ định | **`ClassNotFoundException`** | Yêu cầu initialization |
| `MyType.class` | Class literal của kiểu biết tại compile time | Không có đường “không tìm thấy” theo kiểu API nhận tên String | Không tự yêu cầu initialization của `MyType` |

**Không suy rộng:** “`Class.forName(Module,String)` không link” không có nghĩa mọi overload `Class.forName` đều không link. Cần đọc đúng phần tài liệu của overload đang dùng.

### 4.2. Vì sao không thấy `static` chạy?

~~~java
class InitMarker {
    static {
        System.out.println("INITIALIZED");
    }
}
~~~

Nếu một lời gọi `Class.forName(module, "some.package.InitMarker")` trả về `Class<?>`, riêng lời gọi đó **không** khiến dòng `INITIALIZED` được in. Nếu code sau đó **đọc một nonconstant static field**, **gọi static method**, hoặc **tạo instance** của lớp chưa khởi tạo, khối `static` có thể chạy tại thời điểm sau.

**Cảnh báo suy luận:** không thấy `INITIALIZED` không chứng minh lớp chưa load. Ngược lại, có `Class<?>` không đồng nghĩa initializer đã chạy. Ví dụ độc lập ở mục 6 được thiết kế để quan sát thứ tự này.

## 5. “Trả null” không có nghĩa mọi thất bại đều được biến thành null

Đây là điểm cần phân biệt để viết code production chính xác. `Class.forName(Module, String)` trả `null` **khi không tìm được lớp theo yêu cầu**. Tuy nhiên Javadoc còn quy định các ngoại lệ/lỗi riêng:

| Tình huống | Hành vi |
|---|---|
| Không tìm thấy class/interface đúng module | `null` |
| Class cùng tên được loader load nhưng thuộc module khác | `null` |
| Tham số `module == null` hoặc `name == null` | `NullPointerException` |
| Thất bại liên quan đến class loading/linkage theo hợp đồng API | Có thể ném `LinkageError` |
| Truy cập bị cơ chế kiểm tra bảo mật từ chối (khi áp dụng) | Có thể ném `SecurityException` |

Do đó, cách xử lý sau **sai** vì nhận định mọi thất bại đều là `null`:

~~~java
Class<?> result = Class.forName(module, name);
if (result == null) {
    System.out.println("Everything that can go wrong happened here");
}
~~~

Trong ứng dụng thật:

1. **Validate đầu vào** `module`, `name` theo hợp đồng ứng dụng.
2. **Xử lý `null`** như tình huống class không được tìm thấy trong module được chỉ định.
3. **Không nuốt `LinkageError`** hoặc các lỗi hệ thống một cách tùy tiện; ghi lại thông tin và xử lý theo policy riêng vì đó là loại lỗi khác.
4. Nếu có yêu cầu chính sách bảo mật, không gộp `SecurityException` vào “module không có class”.

Bảng trên nói về **hành vi được Javadoc định nghĩa**; một ứng dụng không nhất thiết gặp mọi trường hợp đó trong runtime thông thường.

## 6. Ví dụ Java 17+ chạy độc lập: tìm được, không tìm được, sai module, chưa initialize

Chúng ta tạo một **named module `lookup.demo`** có lớp `Target` với khối `static` in thông báo. Chương trình thử tìm `Target` trong đúng module, tìm một lớp không tồn tại, tìm một class thuộc module khác, và cuối cùng mới chủ động kích hoạt initialization của `Target`.

### 6.1. Cây thư mục

~~~text
project/
  src/
    lookup.demo/
      module-info.java
      lesson/
        lookup/
          Main.java
          Target.java
  mods/
    lookup.demo/           # thư mục output sau khi biên dịch
~~~

### 6.2. Tệp `src/lookup.demo/module-info.java`

~~~java
module lookup.demo {
    requires java.logging;
}
~~~

Module `lookup.demo` khai báo dependency `requires java.logging;` để trình biên dịch và runtime có thể tham chiếu tới `java.util.logging.Logger`. Module này **không exports** package `lesson.lookup`; thực hành vẫn có thể lấy `Class<?>` của một class trong module, vì overload `forName(Module,String)` không kiểm tra khả năng truy cập class của caller.

### 6.3. Tệp `src/lookup.demo/lesson/lookup/Target.java`

~~~java
package lesson.lookup;

final class Target {
    static {
        System.out.println("TARGET_INITIALIZED");
    }

    static int VALUE = 7;
}
~~~

`Target` là lớp **package-private**. Trường `VALUE` là `static` và không `final`, nên đọc lần đầu sẽ kích hoạt khởi tạo `Target` nếu chưa xảy ra. Khối `static` dùng để quan sát thời điểm khởi tạo.

### 6.4. Tệp `src/lookup.demo/lesson/lookup/Main.java`

~~~java
package lesson.lookup;

public class Main {
    public static void main(String[] args) {
        Module own = Main.class.getModule();
        Module logging = java.util.logging.Logger.class.getModule();

        System.out.println("module=" + own.getName());

        System.out.println("found="
                + (Class.forName(own, "lesson.lookup.Target") == Target.class));

        System.out.println("missing="
                + (Class.forName(own, "lesson.lookup.Missing") == null));

        System.out.println("wrongModule="
                + (Class.forName(own, "java.util.logging.Logger") == null));

        System.out.println("correctModule="
                + (Class.forName(logging, "java.util.logging.Logger")
                    == java.util.logging.Logger.class));

        System.out.println("arrayUnsupported="
                + (Class.forName(own, "[Llesson.lookup.Target;") == null));

        System.out.println("beforeInitializer");
        System.out.println("value=" + Target.VALUE);
    }
}
~~~

### 6.5. Biên dịch và chạy

Đứng tại thư mục `project`, sử dụng JDK 17 trở lên:

~~~sh
javac --release 17 -d mods/lookup.demo src/lookup.demo/module-info.java src/lookup.demo/lesson/lookup/Main.java src/lookup.demo/lesson/lookup/Target.java
java --module-path mods -m lookup.demo/lesson.lookup.Main
~~~

Các lệnh trên biên dịch thành module được unpack (exploded module) trong `mods/lookup.demo`, rồi khởi chạy class `lesson.lookup.Main` thuộc module `lookup.demo`. Không yêu cầu Gradle hoặc Maven.

**Stdout chính xác:**

~~~text
module=lookup.demo
found=true
missing=true
wrongModule=true
correctModule=true
arrayUnsupported=true
beforeInitializer
TARGET_INITIALIZED
value=7
~~~

### 6.6. Đọc kết quả theo thứ tự

| Dòng | Nguyên nhân | Kết luận |
|---|---|---|
| `module=lookup.demo` | `Main.class.getModule()` | Module hiện tại có tên `lookup.demo` |
| `found=true` | Tìm `Target` trong đúng module; so với `Target.class` | Có `Class<?>` đúng module nhưng `Target` chưa bị initializer chạy bởi thao tác này |
| `missing=true` | Không có `lesson.lookup.Missing` trong module | Kết quả là `null`, không phải `ClassNotFoundException` |
| `wrongModule=true` | `Logger` thuộc `java.logging`, không thuộc `lookup.demo` | Lớp **có thật** nhưng module yêu cầu sai, vẫn `null` |
| `correctModule=true` | Lấy module của `Logger` rồi tìm lại | Đúng module trả đúng `Class<?>` |
| `arrayUnsupported=true` | Truyền tên kiểu mảng `[Llesson.lookup.Target;` | Overload theo module không hỗ trợ array classes |
| `beforeInitializer` | Mốc quan sát | Chưa có dòng `TARGET_INITIALIZED` |
| `TARGET_INITIALIZED` | Đọc nonconstant `Target.VALUE` | Lúc này initialization của `Target` mới diễn ra |
| `value=7` | Giá trị của trường sau khởi tạo | Confirm giá trị truy cập hợp lệ |

**Đặc biệt:** lớp `Target` không `public`, nhưng phương thức vẫn trả `Class<?>` của nó. Điều này cho thấy việc **tìm thấy metadata** không tự quyết định khả năng truy cập member/class từ mọi caller. Reflection và truy cập qua ranh giới named module còn có quy tắc riêng.

### 6.7. Bài thử thay đổi

1. Đổi `"lesson.lookup.Target"` thành `"lesson.lookup.NoTarget"` ở phép tìm đầu: `Class.forName(own, ...)` trả `null`, nhưng phép so sánh với `Target.class` vẫn hợp lệ.
2. Đổi `own` ở phép tìm `Target` thành `logging`: nhận `null` dù tên `Target` và bytecode hợp lệ, do chỉ định sai module.
3. Bỏ dòng `System.out.println("value=" + Target.VALUE);`: nếu không có active use khác, dòng `TARGET_INITIALIZED` **không xuất hiện**.
4. Đổi overload sang `Class.forName("lesson.lookup.Target")` trước dòng `beforeInitializer`: overload một tham số sẽ yêu cầu initialization; dòng `TARGET_INITIALIZED` sẽ xuất hiện sớm hơn.
5. Chạy thử trong một **JVM mới** sau mỗi biến thể, bởi initializer chỉ chạy một lần cho mỗi định nghĩa lớp đã khởi tạo.

## 7. Đối chiếu với `Class.forName(String, boolean, ClassLoader)`

Nếu code chỉ có `ClassLoader` thay vì `Module`:

~~~java
ClassLoader loader = Main.class.getClassLoader();
Class<?> found = Class.forName(
        "lesson.lookup.Target", false, loader);
~~~

Đoạn trên là **mã minh họa** bên trong module `lookup.demo`, với `Main` thuộc module đó.

Khác biệt cần hiểu:

- **Overload theo loader** `Class.forName(name, false, loader)` tìm theo loader. Nếu không tìm được, nó ném **`ClassNotFoundException`**, cần catch hoặc khai báo `throws`.
- **Overload theo module** `Class.forName(module, name)` tìm class đúng module và trả **`null`** nếu không có class đó trong module. Nó không yêu cầu `ClassNotFoundException` trong signature.
- **Overload theo loader** có boolean `initialize` để chọn yêu cầu khởi tạo; **overload theo module không có boolean** và theo hợp đồng **không khởi tạo**.
- **Overload theo module** còn có giới hạn về array classes; overload theo loader hỗ trợ kiểu tên mảng được API tài liệu hóa.
- Loader định nghĩa nhiều named modules có thể trả một class được tìm bằng **overload theo loader** trong khi **overload theo module** trả `null` nếu class ở module khác.

### Mẫu code xử lý kết quả an toàn

Trong luồng cần tìm một lớp tùy chọn tại module đã được resolve:

~~~java
static Class<?> findOptionalClass(Module module, String binaryName) {
    java.util.Objects.requireNonNull(module, "module");
    java.util.Objects.requireNonNull(binaryName, "binaryName");
    return Class.forName(module, binaryName);
}
~~~

Đây là **method minh họa**, có thể đặt trong class tiện ích. Caller xử lý kết quả:

~~~java
Class<?> type = findOptionalClass(module, "com.example.Plugin");
if (type == null) {
    System.out.println("Module này không cung cấp lớp yêu cầu");
} else {
    System.out.println(type.getName());
}
~~~

Mẫu này không tự tạo instance và không tự đảm bảo quyền reflective access. Nếu cần khởi tạo/khởi chạy class, bước tiếp theo phải xét riêng: constructor, quyền truy cập JPMS, exception do initializer và tính hợp lệ của API dùng chung.

**Không coi `null` là bằng chứng “thiếu file”.** Trong công cụ debug, nên ghi thêm `module.getName()` hoặc định danh module phù hợp, `binaryName`, layer/loader liên quan và danh sách module đã resolve (nếu có).

## 8. Những lỗi và ngộ nhận thường gặp

### “`forName` không tìm thấy lớp thì luôn ném `ClassNotFoundException`.”

Sai. Chỉ các overload theo tên/loader có hợp đồng ném checked exception đó khi class không được tìm thấy. **Overload `(Module,String)` trả `null`** cho trường hợp không tìm thấy đúng module.

### “Có một lớp cùng tên đâu đó trong classpath/module path thì overload phải trả Class.”

Sai. Module được chỉ định là thành phần quan trọng của phép tìm. Class thuộc module khác có thể khiến kết quả trả `null` dù bytecode tồn tại.

### “Không ném `ClassNotFoundException` thì không có ngoại lệ nào khác.”

Sai. `NullPointerException` cho tham số null, `LinkageError` trong các trường hợp lỗi loading/linkage và `SecurityException` khi điều kiện bảo mật liên quan không được đáp ứng vẫn có thể xảy ra theo Javadoc.

### “Nhận được `Class<?>` là class đã chạy `static {}`.”

Sai. `Class.forName(Module,String)` không kích hoạt initializer. Để kiểm chứng, đặt khối `static` in log và dùng một thao tác active use sau đó.

### “API này tương tự `Class.forName(name, false, loader)` về mọi mặt.”

Sai. Khác **đơn vị phạm vi** (module so với loader), **kết quả khi thiếu lớp** (null so với checked exception), **liên kết**, và **hỗ trợ array types**.

### “Dùng `com.example.Outer.Inner` là đúng tên của nested class.”

Thông thường sai với lớp lồng thực sự. Binary name phải dùng `$`, ví dụ `com.example.Outer$Inner`. `.` phân cách các package và tên top-level class, không thay thế quy tắc binary name của nested class.

### “Nếu `Class.forName(module, name)` trả về Class thì caller chắc chắn được truy cập class/method.”

Sai. Javadoc nêu rõ overload này **không kiểm tra class accessibility đối với caller**. Quy tắc `exports`, `opens`, readability, visibility Java và kiểm tra reflection có thể ảnh hưởng cách sử dụng sau đó.

### “Chỉ định một `Module` có tên sẽ tự resolve mọi JAR ở module path.”

Sai. `Module` object gắn với module đã được biểu diễn trong cấu hình runtime tương ứng. Module resolution/layer xây dựng theo bước riêng; `Class.forName` không thay thế quá trình đó.

### “Trả `null` nghĩa là chắc chắn chưa từng load class nào.”

Sai. Loader của một module có thể load class thuộc module khác rồi overload vẫn trả `null` do lớp không thuộc module được yêu cầu. Cần phân biệt hiệu ứng tìm/nạp và điều kiện kết quả đúng module.

## 9. Quy trình chẩn đoán khi kết quả là `null`

Khi gặp `Class<?> candidate = Class.forName(module, name);` và `candidate == null`:

1. **Kiểm tra `name`:** có đúng binary name, đúng hoa/thường, đúng nested-class `$`? Có vô tình truyền array descriptor hoặc đường dẫn `.class`?
2. **Kiểm tra `module` thực tế:** in `module.getName()`, `module.isNamed()`; nếu module lấy từ `Class.getModule()` thì đảm bảo đó là lớp “mốc” đúng ngữ cảnh.
3. **Kiểm tra lớp thuộc module nào:** với class mà ứng dụng đã biết, quan sát `KnownType.class.getModule()`; với plugin/dynamic module thì kiểm tra descriptor, package và nguồn module.
4. **Kiểm tra resolution:** named module đã được resolve trong boot layer hay child `ModuleLayer` phù hợp chưa? File có trên module path chưa đủ.
5. **Kiểm tra loader mapping:** `module.getClassLoader()`, `ModuleLayer.findLoader(name)` nếu thích hợp; phân biệt module nào do loader định nghĩa.
6. **Nếu thành công nhưng không gọi được member:** kiểm tra visibility Java, readability, `exports`/`opens` và điều kiện reflection, thay vì thay đổi phép tìm đã thành công.
7. **Nếu thực sự có lỗi ném ra:** ghi nguyên exception/error/cause; đừng ép mọi thất bại thành nhánh `null`.

### So sánh triệu chứng

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| `Class.forName(module, name) == null` | Tên, đúng module, module resolution; không kết luận ngay thiếu JAR |
| `Class.forName(name)` ném `ClassNotFoundException` | Loader tìm lớp, binary name, classpath/module path |
| `NullPointerException` từ overload theo module | Có truyền `module` hoặc `name` bằng null không? |
| `LinkageError` | Class-file/definition/dependency và lỗi linkage; ghi cause thực tế |
| Tìm được `Class<?>` nhưng thao tác sau đó lỗi quyền truy cập | Quy tắc JPMS `requires`/`exports`/`opens` và access Java |
| Có `Class<?>` nhưng không thấy log `static` | Đây là bình thường: overload theo module không khởi tạo |
| Plugin tìm được lớp cùng tên nhưng sai kiểu/loader | Defining loader, module membership và runtime type identity |

## 10. Câu hỏi tự kiểm tra

1. `Class.forName(Module,String)` xuất hiện từ Java mấy? Hai tham số có ý nghĩa gì?
2. Nếu lớp không nằm trong module truyền vào, kết quả mặc định là gì?
3. `Class.forName(module, "foo.Bar") == null` có chứng minh JAR chứa `foo.Bar` không tồn tại không? Vì sao?
4. Phân biệt `ClassNotFoundException` và giá trị `null` ở hai overload `Class.forName`.
5. Vì sao `Class.forName(module, name)` trả về `Class<?>` chưa chứng minh class đã initialization?
6. Theo Javadoc, overload này có tự link class không? Overload `Class.forName(name, false, loader)` giống hệt về điều đó không?
7. Trong ví dụ `lookup.demo`, tại sao `wrongModule=true` nhưng `correctModule=true`?
8. Vì sao `Class.forName(own, "[Llesson.lookup.Target;")` không phải cách hỗ trợ để lấy array class?
9. Tại sao `Target` là package-private nhưng vẫn có thể nhận `Class<?>` từ phương thức theo module?
10. Nếu truyền `null` làm `Module` hoặc `name`, API trả null hay ném loại lỗi nào?
11. Khi nào `SecurityException` hoặc `LinkageError` có thể là hướng chẩn đoán riêng thay vì xử lý nhánh null?
12. Nếu lớp thuộc module khác do cùng loader định nghĩa, overload theo module có thể trả null không?

**Tiêu chí hoàn thành:** chạy đúng ví dụ Java 17+, giải thích đầy đủ tám dòng stdout, phân biệt trường hợp “thiếu class” với “class thuộc module khác”, và xử lý đúng hai nhóm kết quả **`Class<?>` hoặc `null`** cùng những lỗi riêng được tài liệu hóa.

## 11. Tài liệu chính thức

- [Java SE 21 — `Class.forName(Module, String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.Module,java.lang.String)): nguồn chính về module scope, `null`, linking, initialization, array types, exceptions.
- [Java SE 17 — `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hành vi overload đã tồn tại trong Java 17.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): nhận diện named/unnamed module, loader và layer.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module resolution context, tìm module và mapping loader.
- [JVM Specification 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): nền tảng loading/linking/initialization khi cần phân tích lỗi sâu.

Ví dụ sử dụng API phù hợp Java 17 trở lên và cố ý tách bước tìm lớp theo module khỏi bước chủ động initialization.