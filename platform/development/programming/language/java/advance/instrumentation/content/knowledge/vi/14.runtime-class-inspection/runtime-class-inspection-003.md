# Bootstrap loader, hidden class và array class trong kết quả khảo sát

> **Ý chính:** `Instrumentation.getAllLoadedClasses()` không chỉ trả những class ứng dụng có binary name thông thường. Snapshot của JVM còn có thể chứa các class được nạp bởi **bootstrap loader**, **hidden class** và **array class**. Các đối tượng đó đều được biểu diễn bằng `Class<?>`, nhưng khác nhau về **khả năng tìm lại theo tên, cách gắn với class loader, vòng đời và tính modifiable**. Đặc biệt, xuất hiện trong danh sách loaded **không đồng nghĩa** class có thể `retransformClasses` hoặc `redefineClasses`.

Bài thuộc mục **Khảo sát khi chạy** trong Java Advance – instrumentation. Mục tiêu là đọc đúng dữ liệu thu từ agent, tránh phân loại sai các class có loader `null`, phân biệt hidden class với array của hidden class và tự kiểm chứng hành vi bằng một ứng dụng Java 17+ có startup agent chạy được.

## 1. Đọc đúng khái niệm “class đang loaded”

Khi JVM truyền đối tượng `Instrumentation` cho `premain` hoặc `agentmain`, agent có thể yêu cầu:

~~~java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
~~~

Đây là **mảnh API minh họa** trong agent đã có biến `Instrumentation instrumentation`, không phải một file Java độc lập. Theo Java SE 17, mảng trả về gồm **classes và interfaces hiện đang loaded**, kể cả **hidden classes/interfaces** và **array classes thuộc mọi loại**.

Ví dụ tên có thể xuất hiện trong một bản ghi của công cụ khảo sát:

~~~text
java.lang.String
java.lang.Object
SurveyApp
HiddenSample/0x000000...
[I
[[I
[Ljava.lang.String;
[LHiddenSample/0x000000...;
~~~

Hậu tố `0x000000...` ở trên chỉ **minh họa** tên hidden class, không phải một ID ổn định hay giá trị stdout của ví dụ. Các chuỗi như `[I` hoặc `[Ljava.lang.String;` là dạng tên array mà `Class.getName()` trả về, không phải tên file `.class` trên đĩa.

Một snapshot là một lát cắt ở một thời điểm:

- Không có nghĩa **mọi file `.class` có trên classpath/module path đều đã loaded**.
- Không có nghĩa mọi class trong snapshot **được một `ClassLoader.loadClass(name)` tìm lại bằng tên**.
- Không có nghĩa những class này đều có bytecode do một file `.class` riêng cung cấp (array type là một phản ví dụ).
- Không có nghĩa tất cả đều có thể sửa bằng `retransformClasses`/`redefineClasses`.
- Không cung cấp một thứ tự class ổn định, một số lượng bất biến hay danh sách được duy trì trực tiếp cho tới khi JVM dừng.

Từ việc tìm ra một `Class<?>`, ta phải tách ít nhất bốn câu hỏi: **loại class gì**, **loader nào**, **discoverable bằng tên không** và **modifiable không**. Gộp bốn câu hỏi thành một biến `isLoaded` sẽ khiến báo cáo sai.

## 2. `getAllLoadedClasses` và `getInitiatedClasses` là hai cách nhìn khác nhau

Java Instrumentation cung cấp hai API thường được so sánh:

~~~java
Class<?>[] all = inst.getAllLoadedClasses();
Class<?>[] initiatedByApp = inst.getInitiatedClasses(appLoader);
Class<?>[] initiatedByBootstrap = inst.getInitiatedClasses(null);
~~~

Đây là **đoạn minh họa**; `inst` và `appLoader` phải là các biến hợp lệ trong agent/app. Trong Java SE 17:

| API | Trả lời điều gì? | Giới hạn không được quên |
| --- | --- | --- |
| `getAllLoadedClasses()` | Những đối tượng `Class<?>` nào JVM đang ghi nhận là loaded? | Bao gồm hidden và array; không yêu cầu tên discoverable |
| `getInitiatedClasses(loader)` | Những class nào `loader` được ghi nhận như **initiating loader**, tìm được bằng tên qua cơ chế load/linkage? | **Không** bao gồm hidden class/interface hoặc array có element type hidden |
| `Class.getClassLoader()` | Loader gắn với một đối tượng class, có thể `null` | `null` không chỉ xảy ra cho named bootstrap class |
| `Class.isHidden()` | Class có thực sự là hidden class? | Không dựa vào substring tên class để tự đoán |
| `Class.isArray()` | `Class<?>` có biểu diễn một kiểu array không? | Array cũng có `Class<?>` dù không có file class riêng |
| `isModifiableClass(clazz)` | Class này có thể thay định nghĩa theo hợp đồng instrumentation không? | Khác với sự có mặt trong inventory |

**`Initiating loader` không luôn là `defining loader`.** Một loader có thể tìm class bằng cách **delegate cho parent loader**; loader gọi là initiating loader trong một quá trình linkage, còn class thực tế do parent định nghĩa. Vì vậy `getInitiatedClasses(loader)` không nên được mô tả đơn giản là “tất cả class do loader này tự define”.

Với `getInitiatedClasses(null)`, tham số `null` biểu thị **bootstrap class loader**: kết quả là các class mà bootstrap loader có thể tìm bằng tên theo contract của API.

Đặc biệt:

- **Hidden class**: có thể nằm trong `getAllLoadedClasses()` nhưng **không** nằm trong bất kỳ `getInitiatedClasses(loader)` nào.
- **Array của hidden class**: cũng có thể có trong all-loaded, nhưng **không** nằm trong initiated list vì element type là hidden.
- **Array có element type thông thường**: có thể có trong danh sách initiated thích hợp, tùy quá trình runtime đã tạo/ghi nhận loại array đó.

Một so sánh số lượng giữa hai API **không phải phép trừ để đếm class bị “thiếu”**. Hai API phục vụ hai câu hỏi khác nhau.

## 3. Bootstrap loader: vì sao `getClassLoader() == null` chưa đủ?

### 3.1. Nhóm built-in loaders

Trên OpenJDK/HotSpot điển hình, hệ thống có bootstrap, platform và application/system class loader:

~~~text
Bootstrap loader           (thường được biểu diễn bằng null)
    |
    v
Platform class loader      (đối tượng ClassLoader)
    |
    v
Application class loader   (đối tượng ClassLoader)
    |
    v
Custom/plugin loaders      (tùy kiến trúc và cơ chế delegation)
~~~

Đây là sơ đồ thường gặp, **không phải yêu cầu mọi custom loader luôn dùng parent-first delegation tuyến tính**. Một số framework/container tạo nhiều loader và chính sách khác nhau.

Ví dụ JDK:

~~~java
System.out.println(String.class.getClassLoader() == null);
System.out.println(Object.class.getClassLoader() == null);
~~~

Hai lệnh này là **mảnh code minh họa**, trên OpenJDK/HotSpot thông thường in `true` và `true`. Không nên suy luận rằng mọi class có tên bắt đầu bằng `java.` đều do bootstrap nạp; còn phải kiểm tra platform loader và các module tương ứng.

### 3.2. Các trường hợp `null` khác

| Đối tượng `Class<?>` | `getClassLoader()` điển hình | Giải thích |
| --- | --- | --- |
| `String.class` | `null` | Named class thuộc bootstrap |
| `Object.class` | `null` | Named class thuộc bootstrap |
| `int.class` | `null` | Primitive type không có defining class loader thông thường |
| `void.class` | `null` | Loại `void`, không phải classfile bình thường |
| `int[][].class` | `null` | Array của primitive, không phải named bootstrap classfile |
| `String[].class` | `null` | Array có element type `String` thuộc bootstrap |
| `SurveyApp.class` | Thường non-null | Class ứng dụng |

Java `ClassLoader` Javadoc cho biết **array classes được runtime tự tạo**, không phải `ClassLoader.defineClass` trực tiếp. Loader mà `Class.getClassLoader()` báo về cho array là loader của **element type**, và mảng của primitive có loader `null`.

Vì vậy **không được** làm:

~~~java
// Mảnh minh họa cách đếm SAI:
if (type.getClassLoader() == null) {
    bootstrapNamedClasses++;
}
~~~

Đoạn trên gộp cả array và primitive vào số liệu của named bootstrap classes. Muốn thống kê named bootstrap, kiểm tra `isArray()`, `isHidden()` và `isPrimitive()` **trước** khi xét loader null.

### 3.3. Bootstrap class có thể modifiable không?

`getClassLoader() == null` **không tự suy ra** `isModifiableClass(type) == false`. Named bootstrap class có thể được VM cho phép sửa definition, tùy JVM/capability/class cụ thể. Muốn retransform còn cần `isRetransformClassesSupported()`.

Tuy vậy, sửa class của JDK là thao tác rất nhạy: có thể ảnh hưởng logging, serialization, class loading, module visibility và JVM runtime. Một method được instrument trong bootstrap class **không mặc nhiên nhìn thấy helper nằm trên application classpath**. Sự có mặt của bootstrap class trong kết quả khảo sát **không phải lời khuyến nghị sửa nó**.

## 4. Hidden class: JVM biết class, nhưng loader không thể tìm bằng binary name

### 4.1. Hidden class hình thành thế nào?

Hidden class là cơ chế của Java 15+ (JEP 371), được runtime/framework dùng cho các implementation classes không cần discover qua tên nhị phân thông thường. Java 17 hỗ trợ tạo bằng `MethodHandles.Lookup.defineHiddenClass(...)`.

Ví dụ:

~~~java
byte[] classFile = Files.readAllBytes(Path.of("HiddenSample.class"));
Class<?> hidden = MethodHandles.lookup()
        .defineHiddenClass(classFile, false)
        .lookupClass();
~~~

Đây là **mảnh minh họa**, cần imports và lookup phù hợp. Ví dụ hoàn chỉnh ở phần 7 dùng `HiddenSample` và `SurveyApp` trong cùng runtime package/module, bảo đảm quyền lookup hợp lệ. Tham số `false` có nghĩa **không yêu cầu initialize ngay** trong thao tác này; class vẫn được JVM **định nghĩa** và đã có `Class<?>`.

Một hidden class:

- Có đối tượng `Class<?>` thật và có thể được reflection/lookup trên chính reference đó.
- `isHidden() == true`; đây là cách phân loại đúng.
- `getName()` trên Java 17+ có phần suffix chứa dấu `/` (ví dụ dạng `HiddenSample/0x...`); **không phải binary name có thể đưa vào `Class.forName` để discover**.
- `getCanonicalName()` thường trả `null`, như demo kiểm thử; không phải lỗi dữ liệu.
- Có loader/module gắn với lookup class theo quy tắc API, nhưng loader không thể tìm nó qua một binary name thông thường.
- Có thể xuất hiện trong `getAllLoadedClasses()`, song bị loại khỏi `getInitiatedClasses(loader)`.
- Không modifiable bằng các cơ chế standard Java agent/JVM TI redefine/retransform.

Điều quan trọng: **loaded ≠ name-discoverable ≠ modifiable**. Một class có thể thỏa vế đầu nhưng không thỏa hai vế còn lại.

### 4.2. Vì sao hidden name không phải “tên class đầy đủ” để cache?

Giả sử log:

~~~text
HiddenSample/0x000000...
HiddenSample/0x000000...
~~~

Hai dòng trên chỉ là **mẫu minh họa** về tiền tố; hậu tố do JVM sinh có thể khác nhau. Không nên cắt suffix rồi dùng `HiddenSample` làm ID duy nhất: có thể tồn tại nhiều hidden classes **khác nhau** bắt nguồn từ một classfile hoặc framework logic tương tự.

Nếu cần xác định một class ở **thời điểm runtime**, dùng đúng đối tượng `Class<?>` và loader/module. Nếu xuất báo cáo dài hạn, dùng ID phiên/deployment do hệ thống cấp, tránh giữ strong references tới mọi hidden `Class<?>` trong một static map của agent khiến class không được unload.

### 4.3. Hidden classes và vòng đời GC

Không có `MethodHandles.Lookup.ClassOption.STRONG`, một hidden class có thể được unload **khi defining loader vẫn reachable**, nếu các reference khác cho phép. Nếu tạo hidden class với `ClassOption.STRONG`, nó có quan hệ strong với loader tương tự named class bình thường.

Vì vậy số hidden classes giữa hai snapshot có thể thay đổi do runtime sinh thêm hoặc class unloading. **Không thấy hidden class trong một snapshot sau** không tự chứng minh API trước đó sai. Ngược lại, **thấy hidden trong snapshot** không nói nó sẽ sống đến cuối tiến trình.

Một lưu ý khi thử nghiệm GC: biến local `hidden`, snapshot `Class<?>[]`, method handle hay cache tĩnh còn giữ class có thể thay đổi điều kiện unload. Đừng dùng một lần `System.gc()` để “chứng minh” class đã hay chưa unload; GC không có thời hạn cam kết.

### 4.4. Hidden không thể sửa bằng cách retransform như named class

Trong OpenJDK thử nghiệm:

~~~text
hidden-in-all=true
hidden-in-app-initiated=false
hidden-modifiable=false
~~~

Mặc dù JVM đã nạp/định nghĩa hidden class, `isModifiableClass(hidden)` vẫn false. **Không** chuyển hidden class từ `getAllLoadedClasses()` thẳng vào `retransformClasses(...)`. Nếu framework cần code đã instrument trong hidden class, nó phải thiết kế sinh bytes phù hợp **trước khi class được define**, không dựa vào việc hot-retransform definition hidden hiện hữu.

## 5. Array class: type có `Class<?>`, nhưng không có `.class` file riêng

### 5.1. Type của mảng và cách đặt tên

Ví dụ:

~~~java
Class<?> one = int[].class;
Class<?> two = int[][].class;
Class<?> three = String[].class;
~~~

mỗi loại có `Class<?>` riêng. Chúng là **array types do runtime tạo** khi cần, không phải class-file definitions như `int[].class` trên ổ đĩa. Cách kiểm tra:

~~~java
System.out.println(int[][].class.isArray());                 // true
System.out.println(int[][].class.getComponentType() == int[].class); // true
System.out.println(int[].class.getComponentType() == int.class);     // true
~~~

Đây là các lệnh minh họa, có thể đưa vào `main`. Với mảng nhiều chiều, `getComponentType()` **chỉ bỏ một cấp array**; muốn element type cuối cùng thì lặp đến khi `!type.isArray()`.

Những dạng `Class.getName()` phổ biến:

| Type | Tên từ `getName()` |
| --- | --- |
| `int[].class` | `[I` |
| `int[][].class` | `[[I` |
| `String[].class` | `[Ljava.lang.String;` |
| `String[][].class` | `[[Ljava.lang.String;` |
| `SurveyApp[].class` | `[LSurveyApp;` khi class ở default package |

Tên bắt đầu bằng `[` là **bình thường**, không phải parse error. Đừng cố đọc một file có tên `[I.class` hoặc nhầm dấu `[` với class trong source code.

### 5.2. Array của hidden class

Bạn có thể tạo array class có element type là một hidden `Class<?>`:

~~~java
Class<?> arrayOfHidden = java.lang.reflect.Array.newInstance(hidden, 0).getClass();
~~~

Đây là **mảnh code minh họa**, với `hidden` đã được tạo như phần trước. Độ dài 0 vẫn đủ để JVM tạo array type và trả đối tượng array, rồi lấy `Class<?>`.

Điều thú vị:

- `arrayOfHidden.isArray()` là `true`.
- `arrayOfHidden.getComponentType() == hidden` là `true` với mảng một chiều.
- `arrayOfHidden` nằm trong `getAllLoadedClasses()` nếu type đó đã được tạo và đang loaded; demo in `true`.
- **Không có** trong `getInitiatedClasses(appLoader)` vì element type là hidden class.
- `isModifiableClass(arrayOfHidden)` là `false` vì bản thân nó là **array class**.

Để phân loại array của hidden class, **không** chỉ gọi `arrayOfHidden.isHidden()`: đây là phép kiểm tra đối với **bản thân class array**, không phải element hidden. Hãy lặp `getComponentType()` tới **element type cuối** và xét `isHidden()` của element.

### 5.3. Array và primitive không modifiable

Java SE 17 quy định `Instrumentation.isModifiableClass()` trả `false` cho **primitive và array classes**. Đây là đặc tính độc lập với việc một phần tử array có thuộc một named class modifiable hay không.

~~~java
inst.isModifiableClass(int.class);      // false
inst.isModifiableClass(int[][].class);  // false
inst.isModifiableClass(String[].class); // false
~~~

Mảnh code trên yêu cầu có `Instrumentation inst`; không phải file độc lập. Có capability `Can-Retransform-Classes: true` cũng **không biến** array/primitive class thành đối tượng modifiable.

**Đừng hiểu lầm:** array có mặt trong survey là hoàn toàn hợp lệ, nhưng không thích hợp làm target redefine/retransform. Với application method cần instrument, hãy chọn named class chứa method đó và kiểm tra class eligibility riêng.

## 6. Một bộ phân loại rõ ràng, không dựa vào tên

Thứ tự hợp lý để phân loại một `Class<?>`:

~~~text
Class<?> type
    |
    +-- type.isArray()? ---- CÓ -> tìm element type cuối cùng
    |                               +-- isHidden()     -> ARRAY_OF_HIDDEN
    |                               +-- isPrimitive()  -> ARRAY_OF_PRIMITIVE
    |                               +-- khác            -> ARRAY_OF_NAMED
    |
    +-- type.isHidden()? --- CÓ -> HIDDEN
    |
    +-- type.isPrimitive()? CÓ -> PRIMITIVE_OR_VOID
    |
    +-- loader == null? ---- CÓ -> NAMED_BOOTSTRAP
    |
    +-- còn lại ------------------> NAMED_NON_BOOTSTRAP
~~~

Một method Java minh họa:

~~~java
static String category(Class<?> type) {
    if (type.isArray()) {
        Class<?> element = type;
        while (element.isArray()) {
            element = element.getComponentType();
        }
        if (element.isHidden()) return "ARRAY_OF_HIDDEN";
        if (element.isPrimitive()) return "ARRAY_OF_PRIMITIVE";
        return "ARRAY_OF_NAMED";
    }
    if (type.isHidden()) return "HIDDEN";
    if (type.isPrimitive()) return "PRIMITIVE_OR_VOID";
    if (type.getClassLoader() == null) return "NAMED_BOOTSTRAP";
    return "NAMED_NON_BOOTSTRAP";
}
~~~

Đây là method có thể chèn vào một class tiện ích; **chưa phải chương trình độc lập**. Lợi ích của thứ tự này là một `int[][].class` không bị ghi nhầm thành một named bootstrap class chỉ vì `getClassLoader() == null`.

Bảng tổng hợp:

| Loại class | `getAllLoadedClasses()` | `getInitiatedClasses()` | `isModifiableClass()` |
| --- | --- | --- | --- |
| Named bootstrap (ví dụ `String`) | Có nếu đang loaded | Có trong tập bootstrap khi discoverable | **Tùy class và JVM** |
| Named class ứng dụng | Có nếu đang loaded | Có trong initiating loader phù hợp | **Tùy class và JVM** |
| Hidden class | Có nếu đang loaded | **Không** | **False** theo agent/JVM TI chuẩn |
| Array của primitive | Có nếu đã tạo/loaded | Tùy điều kiện/runtime discoverability | **False** |
| Array của named class | Có nếu đã tạo/loaded | Có thể có trong initiated set phù hợp | **False** |
| Array của hidden element | Có nếu đã tạo/loaded | **Không** | **False** |
| Primitive và `void` | Có biểu diễn `Class<?>`, nhưng không phải named classfile thường | Không dùng như named-class lookup | **False** |

Bảng là **quy tắc đọc loại dữ liệu**, không phải lời hứa về số lượng/tên class có trong mọi phiên JVM.

## 7. Chạy Java 17+ để thấy cả bootstrap, hidden và array

Đây là ví dụ **hoàn chỉnh**, dùng startup Java agent để nhận `Instrumentation`, sau đó ứng dụng chủ động tạo hidden class và một số array types, rồi lấy hai loại snapshot. Không cần thư viện bên ngoài JDK.

### 7.1. Tệp `SurveyAgent.java`

~~~java
import java.lang.instrument.Instrumentation;

public final class SurveyAgent {
    private static Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent=ready");
    }

    public static Instrumentation instrumentation() {
        return instrumentation;
    }
}
~~~

Trong demo, agent chỉ cung cấp `Instrumentation` cho ứng dụng tự khảo sát. Agent **không** thay bytecode, và việc cho application code gọi vào agent như vậy là để minh họa; production cần chính sách phân quyền và lifecycle phù hợp.

### 7.2. Tệp `HiddenSample.java`

~~~java
public final class HiddenSample {
    public String value() {
        return "hidden";
    }
}
~~~

Classfile này được `javac` tạo ra và sau đó được `SurveyApp` đọc **dưới dạng bytes dữ liệu**. Đừng gọi `new HiddenSample()` trong chương trình demo: mục đích là tạo một **hidden version** bằng `Lookup.defineHiddenClass`, không phải kiểm tra class thường do app loader load theo tên.

### 7.3. Tệp `SurveyApp.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SurveyApp {
    private static boolean contains(Class<?>[] classes, Class<?> target) {
        for (Class<?> candidate : classes) {
            if (candidate == target) return true;
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("HiddenSample.class"));
        Class<?> hidden = MethodHandles.lookup().defineHiddenClass(bytes, false).lookupClass();
        Class<?> hiddenArray = Array.newInstance(hidden, 0).getClass();
        Class<?> intArray = int[][].class;
        Class<?> stringArray = String[].class;
        Class<?> app = SurveyApp.class;
        Class<?> bootstrap = String.class;

        Instrumentation inst = SurveyAgent.instrumentation();
        Class<?>[] all = inst.getAllLoadedClasses();
        Class<?>[] initiatedByApp = inst.getInitiatedClasses(app.getClassLoader());
        Class<?>[] initiatedByBootstrap = inst.getInitiatedClasses(null);

        System.out.println("bootstrap-loader-null=" + (bootstrap.getClassLoader() == null));
        System.out.println("bootstrap-in-all=" + contains(all, bootstrap));
        System.out.println("bootstrap-in-bootstrap-initiated=" + contains(initiatedByBootstrap, bootstrap));
        System.out.println("app-loader-nonnull=" + (app.getClassLoader() != null));
        System.out.println("app-in-all=" + contains(all, app));
        System.out.println("app-in-app-initiated=" + contains(initiatedByApp, app));
        System.out.println("hidden-isHidden=" + hidden.isHidden());
        System.out.println("hidden-name-has-slash=" + hidden.getName().contains("/"));
        System.out.println("hidden-canonical-null=" + (hidden.getCanonicalName() == null));
        System.out.println("hidden-in-all=" + contains(all, hidden));
        System.out.println("hidden-in-app-initiated=" + contains(initiatedByApp, hidden));
        System.out.println("hidden-modifiable=" + inst.isModifiableClass(hidden));
        System.out.println("int-array-isArray=" + intArray.isArray());
        System.out.println("int-array-loader-null=" + (intArray.getClassLoader() == null));
        System.out.println("int-array-in-all=" + contains(all, intArray));
        System.out.println("int-array-modifiable=" + inst.isModifiableClass(intArray));
        System.out.println("string-array-in-all=" + contains(all, stringArray));
        System.out.println("string-array-loader-null=" + (stringArray.getClassLoader() == null));
        System.out.println("hidden-array-isArray=" + hiddenArray.isArray());
        System.out.println("hidden-array-in-all=" + contains(all, hiddenArray));
        System.out.println("hidden-array-in-app-initiated=" + contains(initiatedByApp, hiddenArray));
        System.out.println("hidden-array-modifiable=" + inst.isModifiableClass(hiddenArray));
        System.out.println("primitive-modifiable=" + inst.isModifiableClass(int.class));
    }
}
~~~

**Vì sao bài thực hành có các bước này?**

1. `Files.readAllBytes(Path.of("HiddenSample.class"))` lấy đúng bytes của class đã biên dịch.
2. `Lookup.defineHiddenClass(bytes, false)` tạo một hidden `Class<?>` trong cùng runtime package/module của lookup class.
3. `Array.newInstance(hidden, 0)` tạo array class có hidden element, dù array có length 0.
4. Các type `int[][].class` và `String[].class` bảo đảm mẫu kiểm thử array cụ thể đã có trước khi lấy snapshot.
5. `contains(...)` so sánh **cùng đối tượng `Class<?>` bằng `==`**, không so tên. Hidden suffix khác nhau sẽ không làm hỏng phép kiểm tra.
6. In **boolean có tên rõ nghĩa** thay vì in tất cả class names/số lượng: dễ kiểm chứng hơn trên nhiều JVM.
7. `getAllLoadedClasses()` và `getInitiatedClasses(...)` là **các snapshot riêng**, không có hứa hẹn rằng mọi class của JVM đều bất biến giữa các lần lấy.

### 7.4. Tệp `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: SurveyAgent
~~~

Cần lưu file manifest có xuống dòng cuối. Vì demo **chỉ khảo sát** và gọi `isModifiableClass`, không dùng retransform/redefine, nên không cần cờ `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`.

### 7.5. Biên dịch và chạy

Tạo cấu trúc:

~~~text
survey/
  SurveyAgent.java
  HiddenSample.java
  SurveyApp.java
  agent.mf
~~~

Từ thư mục `survey`, chạy:

~~~bash
javac --release 17 SurveyAgent.java HiddenSample.java SurveyApp.java

jar --create --file survey-agent.jar --manifest agent.mf SurveyAgent.class

java -javaagent:survey-agent.jar SurveyApp
~~~

Cú pháp dùng JDK 17+ và có thể thực hiện từ Bash/CMD/PowerShell trong thư mục chứa các source. Nếu IDE chạy từ working directory khác, `Path.of("HiddenSample.class")` có thể không trỏ đúng tệp; khi đó cần cấu hình working directory nhất quán. Biên dịch `--release 17` giúp classfile/code tương thích Java 17.

### 7.6. Stdout đã kiểm chứng

Đã biên dịch các tệp trên bằng `javac --release 17` và chạy trên OpenJDK 24. **Stdout thực tế:**

~~~text
agent=ready
bootstrap-loader-null=true
bootstrap-in-all=true
bootstrap-in-bootstrap-initiated=true
app-loader-nonnull=true
app-in-all=true
app-in-app-initiated=true
hidden-isHidden=true
hidden-name-has-slash=true
hidden-canonical-null=true
hidden-in-all=true
hidden-in-app-initiated=false
hidden-modifiable=false
int-array-isArray=true
int-array-loader-null=true
int-array-in-all=true
int-array-modifiable=false
string-array-in-all=true
string-array-loader-null=true
hidden-array-isArray=true
hidden-array-in-all=true
hidden-array-in-app-initiated=false
hidden-array-modifiable=false
primitive-modifiable=false
~~~

Đọc thành ba nhóm:

- **Bootstrap:** `String.class` có loader `null`, có trong all-loaded và có trong initiated set của bootstrap.
- **Hidden:** hidden class có `isHidden()==true`, tên chứa `/`, có trong all-loaded nhưng **không** có trong initiated set của app loader và không modifiable.
- **Array:** các array types đã được tạo xuất hiện trong all-loaded, nhưng `isModifiableClass()==false`. Array có element hidden cũng bị loại khỏi initiated set.

`SurveyApp` là đối chứng của named application class: nó có loader khác `null` và xuất hiện trong cả all-loaded lẫn initiated set phù hợp. Các kết quả chính phù hợp với Java SE 17 Javadocs, nhưng việc `String.class.getClassLoader()==null` và chi tiết GC/VM có thể phụ thuộc implementation. **Không hardcode kết quả đếm số class, hidden suffix hoặc thứ tự enumeration trong chương trình thực.**

## 8. Bộ lọc an toàn nếu mục tiêu tiếp theo là retransform

Khi mục đích khảo sát là tìm class có thể instrument, không truyền **tất cả** output của `getAllLoadedClasses()` vào `retransformClasses(...)`.

~~~java
// Mảnh minh họa trong agent, cần biến inst, allowedNames và hàm matchesScope:
if (!inst.isRetransformClassesSupported()) {
    return;
}
for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if (candidate.isArray() || candidate.isHidden() || candidate.isPrimitive()) continue;
    if (!allowedNames.contains(candidate.getName())) continue;
    if (!matchesScope(candidate.getClassLoader(), candidate.getModule())) continue;
    if (!inst.isModifiableClass(candidate)) continue;
    // Ghi nhận ứng viên; chưa retransform đại trà ở đây.
}
~~~

**Đây là mảnh code, không chạy độc lập** vì thiếu các định nghĩa `allowedNames`, `matchesScope` và `inst`. Vai trò của từng bước:

- `isArray()` loại các array class, kể cả array của hidden element.
- `isHidden()` loại hidden class không modifiable.
- `isPrimitive()` là phép bảo vệ bổ sung nếu utility được dùng trên các `Class<?>` ngoài all-loaded snapshot.
- `allowedNames` chỉ nhận named classes/methods thuộc phạm vi thật sự cần instrument.
- `matchesScope` phải kiểm tra defining loader/module đúng, tránh nhiều deployment/plugin có cùng binary name.
- `isModifiableClass` xác nhận class cụ thể được phép sửa definition.
- `isRetransformClassesSupported()` xác nhận **capability chung** của agent/JVM. Hai phép kiểm tra cuối là điều kiện độc lập; có một trong hai là `true` chưa đủ.

Ngay cả khi các check đều qua, còn phải có `ClassFileTransformer` đăng ký với `canRetransform=true`, class-file bytes hợp lệ, không vi phạm giới hạn schema và chính sách vận hành an toàn. Đây là lý do không biến “inventory” thành “hot patch mọi thứ”.

**Named bootstrap class cần thận trọng đặc biệt:** Có thể có class báo `isModifiableClass==true`, nhưng patch sẽ ảnh hưởng toàn JVM và các helper của agent có thể không visible từ bootstrap. Không mặc định đưa những class đó vào allowlist.

## 9. Thu thập số liệu không làm méo kết quả

### 9.1. Không lưu toàn bộ `Class<?>[]` lâu hơn cần thiết

Một agent chạy suốt JVM mà giữ tham chiếu mạnh tới mọi `Class<?>` từ các snapshot sẽ có nguy cơ **pin class loader, hidden classes hoặc plugin deployment cũ**. Tốt hơn:

- Duyệt snapshot trong một phạm vi công việc ngắn.
- Tổng hợp **counters theo category** thay vì lưu tất cả class objects.
- Chỉ lưu tên/metadata có giới hạn và gắn deployment/session ID nếu cần.
- Với thông tin per-class dài hạn, cân nhắc `ClassValue<T>` hoặc cache có lifecycle tương thích class/loader, tránh static strong `Map<Class<?>,...>` không có đường cleanup.
- Không dùng `System.identityHashCode(loader)` làm ID duy nhất vĩnh viễn: hash có thể trùng/reuse và không tự quản lý vòng đời.

Ví dụ minh họa đếm một snapshot:

~~~java
int hidden = 0;
int arrays = 0;
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (clazz.isArray()) arrays++;
    else if (clazz.isHidden()) hidden++;
}
System.out.println("hidden=" + hidden + ", arrays=" + arrays);
~~~

Đoạn này **không có stdout cố định**, vì số class thay đổi theo môi trường, hoạt động ứng dụng/JVM và GC. Khi muốn đếm riêng **arrays có hidden element**, đi xuống `getComponentType()` trước khi tăng bộ đếm.

### 9.2. Ghi rõ phạm vi và thời gian snapshot

Một record khảo sát có thể chứa:

~~~text
timestamp / JVM build / process identity
survey API = ALL_LOADED hoặc INITIATED
class kind = NAMED_BOOTSTRAP / NAMED_APP / HIDDEN / ARRAY_OF_HIDDEN / ...
class name (chỉ khi phù hợp nhu cầu và quyền riêng tư)
loader/module scope trong phiên khảo sát
isModifiableClass result nếu cần
~~~

Đây là **schema minh họa**, không phải file cấu hình có sẵn. Một count “hidden classes = 50” không có timestamp, VM version, phạm vi thống kê hay collector context thường khó so sánh.

Các class trong JVM có thể mang tên framework/ứng dụng nội bộ. Không xuất toàn bộ tên, module và đường dẫn vào logs/telemetry công khai nếu không thực sự cần: nó có thể làm lộ cấu trúc hệ thống và gây high-cardinality metrics.

### 9.3. Snapshot có thể tự gây side effects

Quét hàng nghìn `Class<?>` tiêu tốn thời gian và một mảng tạm khá lớn; reflection, formatter, logger và helper của agent có thể kích hoạt nạp lớp bổ sung. Vì thế:

- Không liên tục quét toàn bộ JVM trên hot request path.
- Tránh in hàng nghìn dòng từ callback class loading hoặc dùng thư viện logging nặng trong transformer.
- Không giả định thứ tự array từ `getAllLoadedClasses` ổn định.
- Nếu câu hỏi là “lớp nào unload sau redeploy”, kết hợp log JVM class unloading, JFR hoặc `jcmd`/heap analysis; đừng chỉ so số đếm tại một lần gọi.
- Dọn snapshot/class references khi xong công việc khảo sát nếu không có nhu cầu lưu chúng.

**GC không deterministic:** Một hidden class mặc định có thể eligible để unload ngay cả khi loader còn sống, nhưng không phải cam kết sẽ được unload tại một mốc thời gian cụ thể. `System.gc()` không phải một lệnh đồng bộ có bảo đảm class unloading.

## 10. Những sai lầm khảo sát thường gặp

| Triệu chứng hoặc nhận định | Vấn đề thực tế | Cách xử lý |
| --- | --- | --- |
| “`getClassLoader()==null` nghĩa là mọi phần tử đều là bootstrap named class” | Lẫn primitive và arrays với bootstrap class | Phân loại array → hidden → primitive → named trước |
| “Hidden class không ở `getAllLoadedClasses`” | Nhầm all-loaded với initiated | Dùng `getAllLoadedClasses`, kiểm tra `isHidden()` |
| “`getInitiatedClasses(appLoader)` thiếu hidden class nên agent sai” | Hidden không discoverable bằng binary name | Đọc đúng hợp đồng của initiated API |
| “Mảng hidden element chắc có trong initiated vì loader của nó là app loader” | Array có element hidden cũng bị loại | Lặp `getComponentType()` đến hidden element |
| “`hidden.getName()` có `/` là tên Java package” | Dấu `/` trong hidden name là phần hậu tố do JVM định danh | Dùng `isHidden` và `Class<?>` identity, không tự ghép `Class.forName` |
| “`[Ljava.lang.String;` là tên file class bất thường” | Đây là array name theo JVM | Nhận diện `isArray` và element type |
| “Array đã loaded thì có thể retransform” | Array luôn không modifiable | Không đưa array vào `retransformClasses` |
| “Ẩn hidden suffix giúp tạo ID duy nhất” | Có thể nhiều hidden classes cùng tên gốc | Không cắt hậu tố rồi coi chuỗi còn lại là class identity |
| “Một class bootstrap chắc chắn không modifiable” | Loader và modifiability là hai chiều khác nhau | Kiểm tra class eligibility và capability, cân nhắc rủi ro |
| “Đếm class mỗi lần phải bằng nhau” | Snapshot thay đổi vì load/unload và GC | Gắn timestamp, VM build, phân tích trend |
| “Có thể dùng `Class.forName` để tìm mọi `Class<?>` trong all-loaded” | Hidden không discoverable, array dùng tên khác | Giữ Class reference, dùng API phù hợp |
| “Lưu snapshot mãi là vô hại” | Strong references có thể giữ classloader và hidden class | Chỉ lưu số liệu tổng hợp hoặc cache có cleanup |
| “Mọi class trong all-loaded đều do một loader tự gọi `defineClass`” | Array do JVM tự tạo, hidden có đường define riêng | Phân biệt class kind trước khi diễn giải |

## 11. Bài tập áp dụng

**Tình huống A.** Tool thấy `String.class` và `int[][].class` cùng có `getClassLoader()==null`. Có nên báo hai “bootstrap loaded named classes”?

**Trả lời:** Không. `String` là named bootstrap class trên OpenJDK điển hình; `int[][]` là **array type của primitive**. Cần xét `isArray()` trước khi phân loại theo loader.

**Tình huống B.** Một hidden class trả `isHidden()==true`, đã có trong all-loaded và có `getClassLoader()==appLoader`, nhưng không có trong `getInitiatedClasses(appLoader)`. API có mâu thuẫn?

**Trả lời:** Không. Hidden class có thể loaded nhưng không discoverable bằng binary name. Initiated list chủ động loại hidden class theo contract.

**Tình huống C.** `Array.newInstance(hidden,0).getClass()` trả một đối tượng. Nó có thể có trong all-loaded không? Có thể retransform không?

**Trả lời:** Array class này có thể có trong snapshot sau khi được tạo, và nó **không modifiable**. Nó cũng bị loại khỏi initiated set vì element type hidden.

**Tình huống D.** `int[][].class.getComponentType()` có trả `int.class`?

**Trả lời:** Không. Trả `int[].class`; cần gọi thêm một lần mới được `int.class`. Hàm phân loại mảng nhiều chiều cần lặp.

**Tình huống E.** Agent muốn tìm class có thể retransform và chỉ kiểm tra `isModifiableClass(type)==true`. Đã đủ chưa?

**Trả lời:** Chưa. Cần thêm `isRetransformClassesSupported()`, đúng classloader/module, transformer capable, classfile hợp lệ và giới hạn cấu trúc. Modifiable không tự cấp capability.

**Tình huống F.** Một hidden class có trong snapshot hôm qua nhưng hôm nay không còn, trong khi app loader vẫn sống. Có chắc là leak hoặc bug?

**Trả lời:** Không. Hidden class không dùng `STRONG` có thể unload độc lập với loader khi GC phù hợp. Cần evidence về lifecycle và GC trước khi kết luận.

**Tình huống G.** Hai loader có thể định nghĩa hai class cùng binary name. Dùng map key bằng `Class.getName()` đủ để phân biệt không?

**Trả lời:** Không. Named class identity cần cả defining loader, còn hidden class có tên không discoverable. Dùng chính `Class<?>` identity ở runtime và ID có lifecycle rõ khi xuất dữ liệu lâu dài.

**Kết luận:** Hãy coi khảo sát runtime là một **inventory có nhiều loại đối tượng `Class<?>`**, không phải danh sách chỉ gồm named, loader-discoverable, modifiable classes. Bootstrap loader giải thích nhiều giá trị loader `null`; hidden class giải thích những class loaded nhưng không discoverable; array class giải thích các kiểu tự phát sinh có tên bắt đầu `[` và không modifiable. Phân loại đúng ba nhóm trước khi thống kê hoặc quyết định retransformation giúp tránh cả báo cáo sai lẫn gọi API không hợp lệ.

### Nguồn chính thức

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, retransformation capability.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isHidden`, `isArray`, `isPrimitive`, `getName`, `getComponentType`, `getClassLoader`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/platform/application loaders và quy tắc loader của array class.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, tên không discoverable, `STRONG` option, class unloading.
- [OpenJDK — JEP 371 Hidden Classes](https://openjdk.org/jeps/371): mục tiêu và semantics của hidden classes.
