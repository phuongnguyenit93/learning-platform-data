# Kiến thức tiên quyết và trình tự học đề xuất — Java Core: ClassLoader

## Mục tiêu học tập

Trước khi học cơ chế `ClassLoader`, cần hiểu một lớp Java đi từ mã nguồn đến runtime như thế nào. `javac` biên dịch mã thành bytecode; JVM dùng các loader để tìm và định nghĩa lớp khi chạy; sau đó lớp có thể được liên kết và khởi tạo. Việc phân biệt các giai đoạn này giúp giải thích các lỗi khi chạy ứng dụng, thư viện, plugin và framework.

Hoàn thành lộ trình này, bạn cần có khả năng:

- Phân biệt mã nguồn `.java`, bytecode `.class`, JAR, classpath, module path, package và tên nhị phân của lớp.
- Giải thích bằng ví dụ sự khác nhau giữa **loading**, **linking** và **initialization**; nhận ra một `Class<?>` đã tìm được không có nghĩa khối `static` đã chạy.
- Nhận diện ba loader built-in trên Java 9+: **bootstrap**, **platform**, **application/system**, và mô tả thứ tự ủy quyền mặc định.
- Hiểu rằng một kiểu lúc chạy được phân biệt bằng **binary name + defining class loader**, nền tảng cho lỗi ép kiểu trong hệ thống plugin.
- Phân tích `ClassNotFoundException`, `NoClassDefFoundError` và lỗi khởi tạo trước khi quyết định sửa classpath hay thiết kế loader riêng.

Bài này tập trung vào **kiến thức cần học trước và thứ tự học**. Custom ClassLoader, module layer, cơ chế nạp song song và classloader của container được đặt sau phần nền tảng; chúng không phải điều kiện đầu vào.

## 1. Những kiến thức tiên quyết

### 1.1. Bắt buộc trước khi đi vào ClassLoader

| Kiến thức | Vì sao cần | Mức tự kiểm tra |
|---|---|---|
| Java: `class`, `interface`, `extends`, constructor, `static` | Đọc được cách lớp được định nghĩa và khi nào logic tĩnh chạy | Tạo được lớp có `main`, lớp lồng nhau và một `static` block |
| Package, `import`, tên lớp đầy đủ | Loader tìm theo **binary name**; `import` chỉ là tiện ích trong mã nguồn | Phân biệt `java.util.List` với `List`; nhận biết `Outer$Inner` là tên nhị phân của lớp lồng `Outer.Inner` |
| JDK, `javac`, `java` | Tránh nhầm nạp lớp với biên dịch | Tự biên dịch và chạy một chương trình ngoài IDE |
| Output `.class`, JAR và classpath | Hiểu JVM có thể tìm bytecode ở đâu | Biết truyền `-cp` khi chạy và chỉ ra classpath root cho lớp có package |
| JVM mức nhập môn, `Class<?>` và instance | Phân biệt metadata về kiểu với đối tượng của kiểu đó | Phân biệt `Demo.class` và `new Demo()` |
| `Exception`, `Error`, stack trace và `Caused by` | Đọc được dấu hiệu lỗi runtime | Chỉ ra được nguyên nhân sâu nhất của một stack trace đơn giản |

**Bài kiểm tra đầu vào:** tạo tệp `Hello.java` chứa `public class Hello` với `main`, chạy hai lệnh sau từ thư mục chứa tệp:

~~~sh
javac Hello.java
java Hello
~~~

Bạn phải biết `javac` tạo `Hello.class` và `java` khởi động JVM để thực thi lớp. Khi chuyển `Hello` vào `package example;`, bạn phải hiểu tên chạy là `example.Hello` và thư mục chứa `example/Hello.class` (theo cấu trúc package) phải thuộc classpath root, không chỉ là thư mục bất kỳ có tệp source.

### 1.2. Nên biết trước hoặc học ngay trong lộ trình

- **Reflection cơ bản:** `Class.forName`, `getClass()`, `getName()`, `getClassLoader()`. Chưa cần học hết reflection, chỉ cần hiểu `Class<?>` là đối tượng mô tả kiểu.
- **Phân biệt compile-time và runtime dependencies:** ứng dụng có thể biên dịch với một JAR nhưng chạy với JAR khác hoặc thiếu JAR.
- **Tính kế thừa và ép kiểu:** cần để hiểu tại sao các lớp cùng tên vẫn có thể không tương thích khi được định nghĩa bởi hai loader khác nhau.

### 1.3. Chưa cần học sâu ngay

`module-info.java`, `ModuleLayer`, thread context class loader, native JNI, bytecode instrumentation, hot reload, deadlock khi nạp lớp và `registerAsParallelCapable` là các phần nâng cao. Chúng có giá trị sau khi bạn hiểu loader mặc định và có nhu cầu cụ thể. ClassLoader không tự tạo sandbox bảo mật cho mã không tin cậy.

## 2. Sơ đồ thứ tự kiến thức

~~~text
Java class / package / static / error handling
                 |
                 v
javac / java / .class / JAR / classpath
                 |
                 v
JVM loading -> linking -> initialization
                 |
                 v
bootstrap / platform / application ClassLoader
                 |
                 v
parent delegation / Class.forName / Class<?>
                 |
                 v
class identity + lỗi liên quan đến class loading
                 |
                 v
custom loader / plugin / container / JPMS
~~~

Mỗi tầng giải thích vấn đề của tầng sau. Ví dụ, nếu chưa biết classpath trỏ đến đâu, bạn rất dễ nhầm một lỗi thiếu JAR với lỗi do implementation của `loadClass`.

## 3. Trình tự học đề xuất và điều kiện chuyển chặng

### Chặng 1 — Mã nguồn, bytecode và phạm vi tra cứu lớp

**Cần nắm:** `.java` là mã nguồn; `javac` tạo bytecode `.class`; `java` chạy ứng dụng trong JVM. Thư mục output, JAR và `-cp`/`--class-path` quyết định phạm vi lớp ứng dụng có thể tìm lúc chạy theo classpath. `import` không thêm dependency.

**Thực hành:** biên dịch một lớp đơn lẻ; sau đó tạo một lớp trong package. Dùng `javac -d out` (tạo thư mục `out` trước nếu cần) và chạy `java -cp out packageName.Main`. Quan sát cấu trúc `.class` tương ứng với package. Thử `javap -classpath out -c packageName.Main` để thấy file `.class` chứa thông tin bytecode mà JVM có thể xử lý.

**Tự kiểm tra:** vì sao có `import com.example.Service;` nhưng runtime vẫn có thể không tìm thấy `Service`? Vì sao `javac` thành công không bảo đảm `java` tìm được mọi dependency?

**Qua chặng khi:** tự xác định được binary name, classpath root và nơi tạo file `.class`.

### Chặng 2 — Phân biệt loading, linking và initialization

**Cần nắm:**

1. **Loading:** JVM dùng loader để tìm hoặc tạo định nghĩa lớp từ dữ liệu lớp; một đối tượng `Class` tương ứng có thể được sử dụng để biểu diễn kiểu.
2. **Linking:** bao gồm xác minh bytecode (`verification`), chuẩn bị (`preparation`) và giải quyết các tham chiếu biểu tượng (`resolution`). JVM có thể trì hoãn một phần resolution; sơ đồ thứ tự không có nghĩa toàn bộ thao tác diễn ra ngay lập tức.
3. **Initialization:** logic khởi tạo `static` của lớp được thực hiện theo các điều kiện do Java/JVM quy định. Nạp và liên kết một lớp không tự bảo đảm đã chạy khối `static`.

**Thực hành:** tạo một lớp có `static { System.out.println("initialized"); }`, sau đó thử lấy đối tượng `Class<?>` mà chưa yêu cầu initialization; dùng chương trình ở mục 4 để kiểm chứng. Thử nhận diện sự khác nhau giữa `X.class` và khởi tạo `X` bằng sử dụng tích cực.

**Tự kiểm tra:** tại sao “đã load” không đồng nghĩa “đã initialize”? Tại sao lỗi liên kết có thể chỉ xuất hiện khi một đường code thật sự được chạy?

**Qua chặng khi:** mô tả đúng ba giai đoạn và không khẳng định mọi resolution luôn xảy ra cùng một thời điểm.

### Chặng 3 — Các loader có sẵn và mô hình parent delegation

**Cần nắm:** từ Java 9 trở lên, runtime có ba lớp trách nhiệm loader chính:

- **Bootstrap class loader:** loader tích hợp trong JVM; API Java thường biểu diễn nó bằng `null`. Nó nạp những lớp cốt lõi như `java.lang.String`.
- **Platform class loader:** hỗ trợ nhiều lớp API nền tảng; lấy qua `ClassLoader.getPlatformClassLoader()`.
- **Application/System class loader:** thông thường nạp lớp ứng dụng trên classpath; lấy qua `ClassLoader.getSystemClassLoader()`. Môi trường nhúng có thể có cấu hình khác.

Phương thức `ClassLoader.loadClass(name, resolve)` **mặc định** kiểm tra lớp đã nạp, nhờ parent tìm, rồi mới gọi `findClass` nếu cần. Đây là hướng **parent-first**. Parent là quan hệ *ủy quyền nạp lớp*, khác quan hệ `extends` giữa các lớp Java. Custom loader hoặc môi trường plugin có thể đổi chiến lược; do đó parent-first không phải bất biến của mọi ClassLoader.

**Thực hành:** xem kết quả `String.class.getClassLoader()` và `Main.class.getClassLoader()`. Khi loader của `String` trả về `null`, kết luận đúng là API biểu diễn bootstrap, không phải “lớp chưa tồn tại”. Không so sánh chuỗi `toString()` của loader như một tiêu chuẩn cố định giữa các phiên bản JDK.

**Tự kiểm tra:** khi application loader tìm một lớp, trong implementation mặc định parent được hỏi lúc nào? Nếu parent không tìm thấy, phương thức nào thường đảm nhận việc định nghĩa lớp cục bộ?

**Qua chặng khi:** vẽ được luồng delegation và nêu đúng vai trò của bootstrap, platform, application.

### Chặng 4 — Quan sát ClassLoader và thời điểm khởi tạo

**Cần nắm:** `Class<?>` mô tả một kiểu runtime; `getClassLoader()` cho biết loader định nghĩa kiểu đó; `Class.forName(String, boolean, ClassLoader)` cho phép yêu cầu nạp theo binary name với cờ `initialize`. Ngược lại, overload `Class.forName(String)` yêu cầu khởi tạo lớp theo ngữ nghĩa của API. `ClassLoader.loadClass` mặc định không yêu cầu initialization.

**Thực hành:** chạy ví dụ Java hoàn chỉnh ở mục 4. Sau đó đổi `false` thành `true` trong lần gọi đầu và dự đoán stdout trước khi chạy.

**Tự kiểm tra:** dòng nào cho biết có đối tượng `Class`? Dòng nào cho biết `static` block đã chạy? Vì sao đây là hai quan sát khác nhau?

**Qua chặng khi:** dự đoán chính xác kết quả ví dụ và giải thích mỗi lời gọi.

### Chặng 5 — Định danh lớp runtime và ranh giới loader

**Cần nắm:** một lớp trong JVM được phân biệt bằng **cặp (binary name, defining loader)**. Hai loader khác nhau có thể định nghĩa hai lớp có cùng tên nhưng JVM vẫn coi đó là hai kiểu khác nhau. Loader *khởi xướng* yêu cầu tìm lớp có thể chỉ ủy quyền cho parent; nó không nhất thiết là *defining loader* của lớp được trả về.

**Bài tập tư duy:** hai plugin A và B đều có lớp tên `com.example.PluginApi` và mỗi plugin định nghĩa lớp bằng loader riêng. Vì sao một đối tượng được tạo theo `PluginApi` của A không bảo đảm ép kiểu được sang `PluginApi` của B? Một API chung do loader cha định nghĩa có thể giúp hai phía chia sẻ hợp đồng kiểu như thế nào?

**Tự kiểm tra:** chỉ nhìn `Class.getName()` giống nhau đã đủ biết hai `Class` đại diện cùng kiểu chưa? Phải kiểm tra thêm điều gì?

**Qua chặng khi:** giải thích được lỗi `ClassCastException` có liên quan đến loader mà không nhầm nó với cùng package hay cùng tên source.

### Chặng 6 — Chẩn đoán lỗi thật trong ứng dụng

| Dấu hiệu | Diễn giải phù hợp | Việc kiểm tra đầu tiên |
|---|---|---|
| `ClassNotFoundException` | API chủ động tìm lớp theo tên nhưng loader không tìm thấy; checked exception | Binary name, classpath/JAR, loader được truyền vào lời gọi |
| `NoClassDefFoundError` | JVM cần một định nghĩa lớp nhưng không tìm/không dùng được; cũng có thể xảy ra sau lần khởi tạo thất bại trước đó | Đọc `Caused by`, stack trace, classpath runtime và lỗi trước đó |
| `ExceptionInInitializerError` | Logic khởi tạo tĩnh xảy ra exception dẫn tới lỗi khởi tạo | Đọc cause trong `static` initializer, dependency liên quan |
| `ClassCastException` | Ép kiểu sai; trong hệ plugin có thể do các lớp trùng tên nhưng khác loader | Kiểm tra kiểu thực, defining loader và cây kế thừa |
| `NoSuchMethodError` / `NoSuchFieldError` | Thường là thay đổi binary/API version giữa compile và runtime | Kiểm tra version JAR được JVM thực sự dùng |

**Quy trình luyện chẩn đoán:** (1) đọc chính xác lớp và exception/error; (2) lần theo `Caused by`; (3) xác định classpath/module path và version thư viện runtime; (4) hỏi loader nào đang tra cứu/định nghĩa lớp; (5) thiết kế một phép thử nhỏ để xác minh giả thuyết. Khi phù hợp với HotSpot hiện đại, có thể dùng `-Xlog:class+load=info` để quan sát nạp lớp, nhưng không suy đoán nguyên nhân chỉ dựa trên số lượng log.

**Tự kiểm tra:** thiếu một JAR lúc chạy thường thể hiện thế nào so với một ngoại lệ do `static` initializer? Vì sao cần biết chính xác error/exception thay vì chỉ tìm từ “class” trong log?

**Qua chặng khi:** biết phân biệt lỗi tìm theo tên, lỗi lớp phụ thuộc và lỗi khởi tạo, đồng thời có phương pháp xác minh.

### Chặng 7 — Phần nâng cao sau khi đã vững nền tảng

Chỉ học sâu khi bạn có nhu cầu thực tế:

- **Custom ClassLoader:** `findClass`, `defineClass`, đọc bytecode và vòng đời của loader. Theo hướng dẫn của API, thường ưu tiên override `findClass` để giữ ủy quyền của `loadClass`; chỉ override `loadClass` khi chủ đích cần chiến lược khác.
- **Plugin và container:** loader riêng, API chung, cô lập dependency, chiến lược parent-first hoặc cách ưu tiên tìm kiếm khác; phân tích class identity trước khi sửa ép kiểu.
- **Thread context class loader:** cho framework và cơ chế service/provider cần tra cứu theo ngữ cảnh thread; phân biệt với `SomeType.class.getClassLoader()`.
- **Java Platform Module System (JPMS):** `module-info.java`, module path, readability, export/open, module layer. Không đồng nhất module path với classpath.
- **Resource lookup và môi trường thực:** `getResource`/`getResources`, JAR resources, dịch vụ tải động, custom launcher; đây là các trường hợp có thêm phạm vi và quy tắc tra cứu.
- **Concurrency, lỗi an toàn và thiết kế loader:** parallel-capable, locking/deadlock, kiểm tra dữ liệu bytecode và ranh giới bảo mật. Loader tùy chỉnh không tự biến mã không tin cậy thành an toàn.

## 4. Bài thực hành Java 17+ độc lập

Tạo tệp đúng tên **`ClassLoaderLearning.java`**:

~~~java
public class ClassLoaderLearning {
    static class Probe {
        static {
            System.out.println("Probe initialized");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("String uses bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Main uses system loader: "
                + (ClassLoaderLearning.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));

        ClassLoader loader = ClassLoaderLearning.class.getClassLoader();
        Class<?> probe = Class.forName(
                "ClassLoaderLearning$Probe", false, loader);
        System.out.println("Located: " + probe.getName());
        System.out.println("Before explicit initialization");

        Class.forName(probe.getName(), true, probe.getClassLoader());
        System.out.println("After explicit initialization");
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~sh
javac ClassLoaderLearning.java
java ClassLoaderLearning
~~~

Với lệnh gọi launcher JDK tiêu chuẩn ở trên, stdout là:

~~~text
String uses bootstrap: true
Main uses system loader: true
Located: ClassLoaderLearning$Probe
Before explicit initialization
Probe initialized
After explicit initialization
~~~

**Giải thích kết quả:**

1. `String` do bootstrap loader định nghĩa trong môi trường JDK thông thường, nên `getClassLoader() == null` là `true`; `null` không báo lỗi.
2. Với chương trình khởi chạy như trên, `ClassLoaderLearning` dùng system/application loader. Đừng áp đặt kết quả này cho mọi môi trường nhúng/loader được tùy chỉnh.
3. `Class.forName("ClassLoaderLearning$Probe", false, loader)` trả về `Class<?>`, nhưng không yêu cầu khởi tạo `Probe`. Vì vậy dòng `Probe initialized` chưa xuất hiện.
4. Lần gọi tiếp theo với `true` yêu cầu khởi tạo. Khối `static` chạy một lần và được quan sát ở giữa hai dòng “Before”/“After”.
5. Trong cùng định nghĩa lớp đã khởi tạo, lặp lại yêu cầu initialization không chạy lại `static` initializer.

**Bài tập mở rộng ngắn:** chuyển boolean của lần `Class.forName` đầu thành `true`, chạy trong một tiến trình Java mới và giải thích vì sao `Probe initialized` xuất hiện trước dòng `Located`. Đừng nhầm biên dịch lại tệp với làm mới các lớp đã nạp trong một JVM đang chạy.

Ví dụ cố ý không tự triển khai custom loader: người học cần kiểm chứng vòng đời lớp và loader có sẵn trước khi đi vào `defineClass`.

## 5. Chọn điểm bắt đầu theo nền tảng hiện có

| Tình trạng | Nên bắt đầu | Dấu hiệu đã đủ điều kiện chuyển tiếp |
|---|---|---|
| Chưa thành thạo `javac`, `java`, `-cp` | Chặng 1 | Chạy được một lớp có package và biết classpath root |
| Đã viết Java nhưng chưa hiểu vòng đời lớp | Chặng 2 | Phân biệt được load, link, initialize |
| Biết JVM cơ bản nhưng chưa học delegation | Chặng 3 | Nêu được ba built-in loaders và ủy quyền mặc định |
| Đã nắm lý thuyết, muốn có bằng chứng | Chặng 4 + ví dụ | Dự đoán đúng stdout và giải thích từng dòng |
| Đang giải quyết lỗi plugin/dependency | Chặng 5–6 | Xác định được loader, class identity, loại lỗi và giả thuyết |
| Muốn viết loader tùy biến | Chặng 7 | Có trường hợp sử dụng cụ thể và hiểu hệ quả của cách ủy quyền |

Đây là **thứ tự phụ thuộc kiến thức**, không phải kế hoạch có số giờ cứng. Người đã vững prerequisites có thể bắt đầu ở chặng 2–3, nhưng nên làm bài thực hành để xác minh hiểu biết.

## 6. Các hiểu lầm cần tránh

- **“`import` làm JVM tìm ra lớp.”** `import` chỉ hỗ trợ viết source; classpath/module path và loader mới liên quan đến tra cứu lúc chạy.
- **“Có `.class` trên ổ đĩa nghĩa là JVM đã load.”** File có thể chưa từng được yêu cầu trong tiến trình.
- **“Lấy được `Class<?>` tức là khối `static` đã chạy.”** Có thể đã load/link nhưng chưa initialize.
- **“`Class.forName` luôn chỉ load.”** Overload một tham số yêu cầu initialization; overload ba tham số có cờ điều khiển.
- **“`null` từ `getClassLoader` nghĩa là lỗi.”** Với bootstrap-defined classes, kết quả này là bình thường.
- **“Parent loader là superclass.”** Parent trong loader phục vụ ủy quyền, hoàn toàn khác `extends`.
- **“Tên lớp giống nhau chứng minh cùng một kiểu.”** Phải xét thêm defining loader.
- **“Tất cả ClassLoader luôn parent-first.”** Đây là hành vi mặc định; custom loader/framework có thể dùng cách khác.
- **“Mọi lỗi chứa chữ Class đều là thiếu JAR.”** Còn có thất bại khởi tạo, version mismatch, linking và ranh giới loader.
- **“Phải viết custom loader từ đầu.”** Học và quan sát loader có sẵn trước sẽ giúp hiểu vì sao và khi nào cần tùy biến.

## 7. Câu hỏi cuối bài và tiêu chí hoàn tất

1. `javac` và ClassLoader đảm nhận hai trách nhiệm khác nhau thế nào? Vì sao `import` không sửa được lỗi thiếu classpath?
2. Khi `Class.forName(name, false, loader)` trả về, có thể kết luận gì về việc tìm lớp và chưa thể kết luận gì về initialization?
3. Bootstrap, platform và application loader khác nhau ở đâu? Vì sao loader của `String` có thể là `null`?
4. Trong implementation mặc định của `loadClass`, thứ tự kiểm tra lớp đã nạp, parent, `findClass` ra sao?
5. Hai lớp có cùng binary name nhưng defining loader khác nhau có phải cùng một kiểu JVM không?
6. `ClassNotFoundException`, `NoClassDefFoundError` và `ExceptionInInitializerError` đặt ra ba hướng kiểm tra gì khác nhau?
7. Khi chạy trong IDE được nhưng terminal lỗi, bạn sẽ so sánh compiler output, classpath, JAR version và launcher như thế nào?
8. Trong plugin system, vì sao nên cân nhắc để API chung được định nghĩa bởi loader mà cả ứng dụng và plugin đều thấy?

**Tiêu chí đạt:** trả lời được tám câu, tự biên dịch/chạy ví dụ và giải thích đúng thứ tự dòng stdout, đồng thời có khả năng nêu một giả thuyết kiểm chứng được cho lỗi nạp lớp. Khi đó có thể học bài chuyên sâu về class identity, parent delegation, resource lookup và custom loaders mà không thiếu nền tảng.

## 8. Tài liệu chính thức để tra cứu tiếp

- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): built-in loader, delegation, `loadClass`, `findClass` và resources.
- [Java SE 21 — `Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `Class.forName` và cờ `initialize`.
- [JVM Specification, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): Loading, Linking, Initializing và các điều kiện chính thức của JVM.

Tài liệu tham chiếu chọn Java 21 để dễ tra cứu; chương trình minh họa chỉ dùng cú pháp và API có sẵn trên Java 17 trở lên.