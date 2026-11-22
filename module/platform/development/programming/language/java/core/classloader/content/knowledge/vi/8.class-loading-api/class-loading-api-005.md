# `resolveClass` và sự khác biệt với khởi tạo lớp (class initialization)

> **Ngữ cảnh:** Java Core → ClassLoader → API nạp lớp. Bài này giải thích chính xác `ClassLoader.resolveClass(Class<?>)` làm gì, nó liên hệ thế nào với `loadClass`/`defineClass`, và vì sao **liên kết (linking)** một lớp không đồng nghĩa với **khởi tạo (initialization)**. Nội dung theo hợp đồng Java SE và JVM Specification; ví dụ độc lập dùng Java 17+.

## 1. Câu trả lời trọng tâm

Trong một `ClassLoader` tùy biến, đoạn mã:

~~~java
Class<?> type = loadClass("example.Widget");
resolveClass(type);
~~~

có nghĩa **yêu cầu nạp `example.Widget` nếu chưa được nạp, rồi liên kết lớp được trả về nếu cần**. Nó **không** có nghĩa “gọi static initializer của `Widget`”. Vì `resolveClass` là `protected final`, đoạn mã này chỉ hợp lệ **trong thân một subclass của `ClassLoader`** (hoặc ngữ cảnh Java được phép truy cập protected member); đây là **snippet minh họa**, không phải chương trình độc lập.

Để yêu cầu **khởi tạo** một lớp bằng API rõ ràng, có thể sử dụng:

~~~java
Class.forName("example.Widget", true, suitableLoader);
~~~

với `suitableLoader` là loader phù hợp. Overload ba tham số với `initialize=true` yêu cầu khởi tạo class/interface; `false` không yêu cầu khởi tạo. Lúc khởi tạo, các giá trị `ConstantValue` được áp dụng và phương thức `<clinit>` (nếu có) được thực thi theo quy tắc JVM/JLS.

**Phân biệt ngay:**

| Khái niệm/API | Ý nghĩa | Chắc chắn chạy `static { ... }` của lớp đích? |
| --- | --- | --- |
| `ClassLoader.loadClass(String)` | Tìm/trả về `Class<?>` qua loader và delegation, mặc định không request resolution bằng boolean `true` | **Không** |
| `ClassLoader.loadClass(String, boolean)` | Phương thức protected: có thể yêu cầu `resolveClass` khi `resolve=true` | **Không** |
| `ClassLoader.resolveClass(Class<?>)` | **Links** class đã có `Class<?>`; API gọi tên hơi gây hiểu nhầm | **Không** |
| `Class.forName(name, false, loader)` | Tra cứu `Class<?>` qua loader mà **không yêu cầu initialize** | **Không** |
| `Class.forName(name, true, loader)` | Tra cứu và yêu cầu **initialize** class/interface tương ứng | **Có nếu cần**, nhưng `<clinit>` có thể không tồn tại, đã chạy trước đó hoặc không có side effect |
| `new Widget()` | Tạo instance; phải bảo đảm class liên quan đã được initialize trước khi dùng | **Chạy khi là lần active use yêu cầu initialization** |
| `Widget.someStaticMethod()` | Gọi static method; kích hoạt initialization của lớp/interface khai báo method | **Chạy khi cần** |
| Đọc `Widget.someStaticNonconstantField` | Đọc field `static` không phải constant variable | **Chạy khi cần** |
| Đọc `Widget.COMPILE_TIME_CONSTANT` từ mã đã compile | Có thể dùng giá trị đã inline, không cần initialize class khai báo | **Không chỉ vì thao tác này** |

“Chạy `<clinit>`” không nên hiểu là *luôn có dòng log*. Nhiều lớp không có `<clinit>`, một lớp đã initialized sẽ không chạy lại, và static initializer không buộc phải in ra màn hình.

## 2. Ba giai đoạn của một runtime class

JVM Specification `5` định nghĩa ba nhóm công việc: **loading**, **linking**, **initialization**.

~~~text
                  LOADING
         Đọc/tạo runtime class và Class<?> token
                       |
                       v
                  LINKING
         +-----------------------------+
         | Verification                | kiểm tra class file/type safety
         | Preparation                 | tạo static fields; giá trị mặc định
         | Resolution                  | giải symbolic references khi cần
         +-----------------------------+
                       |
                       v
                INITIALIZATION
        gán ConstantValue theo quy tắc JVMS
        chạy <clinit> nếu được định nghĩa
        ghi trạng thái initialized / erroneous
~~~

Đây là sơ đồ **logic**; JVM có thể resolve các symbolic references **lười hoặc sớm** trong phạm vi đặc tả. Không suy ra mọi reference đã được resolve ngay khi `resolveClass` trả về.

### 2.1. Loading

Loading tìm binary representation, tạo runtime class/interface hoặc array class và có thể yêu cầu thêm các class khác. Với class thông thường, runtime identity là **(binary name, defining class loader)**.

Ví dụ hai custom loaders có thể cùng trả về tên `org.example.Plugin` nhưng là hai runtime types khác nhau nếu **mỗi loader tự define** class đó. Ngược lại, khi hai loaders đều delegate tới cùng parent, kết quả có thể là đúng một `Class<?>`.

`ClassLoader.loadClass(name)` thường trả về kiểu đã tồn tại hoặc tìm kiểu mới, và **không được lấy thành công của lời gọi làm bằng chứng initializer đã chạy**.

### 2.2. Linking

Linking gồm:

1. **Verification:** bảo đảm dữ liệu class file hợp lệ và tuân thủ các ràng buộc type safety. Một class file sai có thể dẫn tới `VerifyError` hoặc các `LinkageError` phù hợp.
2. **Preparation:** tạo các static fields và đưa chúng về giá trị **mặc định** (`0`, `false`, `null`...), **chưa** thực hiện biểu thức khởi tạo Java.
3. **Resolution:** chuyển tham chiếu tượng trưng trong runtime constant pool thành tham chiếu thực; có thể gồm class, field, method, method handle, dynamic constant, call site và kiểm tra accessibility/loader constraints. JVM có quyền lựa chọn thời điểm giải quyết trong giới hạn quy định.

Tên API **`resolveClass`** dễ gây hiểu lầm vì nghe giống chỉ thực hiện phần *resolution*. Tài liệu `ClassLoader` nói rõ: **“Links the specified class.”** Nghĩa là mục đích của API này là **linking**, không phải “ép giải toàn bộ symbolic references ngay lập tức”.

### 2.3. Initialization

Initialization thực hiện công việc mang tính hành vi:

- Gán giá trị từ `ConstantValue` cho các field thích hợp trước khi chạy `<clinit>`.
- Chạy code của static field initializers/static initializer blocks mà compiler kết hợp vào `<clinit>` nếu có.
- Phối hợp thread khác đang chờ initialization của cùng runtime class.
- Đảm bảo các điều kiện liên quan đến superclass và những superinterfaces có default methods, tùy ngữ cảnh class/interface theo thuật toán JLS.
- Đánh dấu initialized khi thành công, hoặc **erroneous** nếu thất bại.

JVM bắt buộc class phải được verify/prepare trước khi initialize; tuy nhiên một JVM vẫn có thể resolve thêm reference sau khi class đã initialized. Vì vậy “đã initialize” cũng **không** chứng minh mọi symbolic reference của class đã được resolve từ trước.

## 3. Hợp đồng chính xác của `ClassLoader.resolveClass`

Chữ ký API Java SE:

~~~java
protected final void resolveClass(Class<?> c)
~~~

Các đặc điểm:

- **`protected`:** một đoạn `main` bình thường không thể tùy ý gọi `someLoader.resolveClass(c)` từ bên ngoài. Class loader tùy biến có thể gọi bên trong subclass; Java access rules vẫn áp dụng.
- **`final`:** subclass **không được override** hành vi `resolveClass`. Nếu muốn kiểm soát cách nạp, override điểm mở rộng thích hợp như `findClass`, hoặc `loadClass` khi thật sự cần chính sách delegation khác.
- **`void`:** phương thức không trả `Class`; kết quả class token vốn đã được truyền vào.
- **Đối số `null`:** ném `NullPointerException`, không biến thành `ClassNotFoundException`.
- **Gọi khi class đã linked:** chỉ trả về bình thường; không có nghĩa static initializer sẽ chạy lại.
- **Gọi với class chưa linked:** VM thực hiện liên kết theo quy định. Các lỗi verification/linkage vẫn có thể được phát hiện, nhưng thời điểm lỗi của một symbolic reference cụ thể phụ thuộc quy tắc resolution.
- **Không phải public API để initialize:** không có tham số `initialize` và cũng không có “`resolveClass(true)`”.

Lưu ý có **hai lớp tên gọi**:

- `ClassLoader.resolveClass(Class<?>)` = API từ loader để **link class**.
- **JVM resolution (`JVMS 5.4.3`)** = hoạt động xử lý một **symbolic reference** trong constant pool. Đây là một phần của linking, nhưng không đồng nghĩa việc gọi `resolveClass` buộc tất cả references được resolve lập tức.

### 3.1. API này thường được gọi từ đâu?

Trong triển khai mặc định của `ClassLoader.loadClass(String, boolean)`, thuật toán được mô tả theo dạng:

~~~java
// Pseudocode: rút gọn thuật toán API; KHÔNG phải implementation chuẩn.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = (parent != null)
                    ? parent.loadClass(name)
                    : findBootstrapClassOrNull(name);
        } catch (ClassNotFoundException ignored) {
            // Tiếp tục tìm trong loader hiện tại.
        }
        if (c == null) {
            c = findClass(name);
        }
    }
    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

Đoạn trên chỉ giải thích **tư tưởng delegation + link**, không phải mã copy để compile: các helper nội bộ như `findBootstrapClassOrNull`, quyền truy cập biến `parent` và xử lý đặc biệt tùy JDK không phải toàn bộ API công khai cho subclass.

Điểm then chốt: cờ `resolve` là **“link class nếu yêu cầu”**, **không phải “initialize class”**. Nó không phải tham số của overload public `loadClass(String)`. Muốn kiểm soát cờ từ mã ứng dụng thì thường tạo **một phương thức của subclass** gọi protected overload, như ở ví dụ hoàn chỉnh bên dưới.

### 3.2. `loadClass(String)` mặc định và `loadClass(name, resolve)`

Theo hợp đồng `ClassLoader`, overload một tham số được triển khai qua protected overload với `resolve=false`:

~~~java
public Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return loadClass(name, false);
}
~~~

Vì thế gọi `loader.loadClass("pkg.Target")` **không yêu cầu** `resolveClass` theo luồng mặc định. Tuy nhiên JVM/loader có thể đã link class trước đó hoặc liên kết sớm theo implementation; không được suy luận class chắc chắn ở trạng thái “chưa link” chỉ vì cờ `false`.

Nội dung `resolve=false` mang ý nghĩa **không chủ động yêu cầu bước link qua API này**, chứ không phải một lệnh “cấm JVM link class đến hết chương trình”. Trong khi đó `resolve=true` cũng **không** biến lời gọi thành explicit class initialization.

## 4. Ví dụ độc lập: `resolveClass` không chạy static initializer

Tệp **`LinkVsInit.java`**:

~~~java
public class LinkVsInit {
    static class Target {
        static {
            System.out.println("Target initialized");
        }

        static int answer = 42;
    }

    static final class ProbeLoader extends ClassLoader {
        ProbeLoader() {
            super(LinkVsInit.class.getClassLoader());
        }

        Class<?> loadAndLink(String binaryName)
                throws ClassNotFoundException {
            Class<?> result = loadClass(binaryName, false);
            resolveClass(result);
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        ProbeLoader loader = new ProbeLoader();

        System.out.println("1. before load/link");
        Class<?> token = loader.loadAndLink("LinkVsInit$Target");
        System.out.println("2. after link: " + token.getName());

        Class.forName("LinkVsInit$Target", false, loader);
        System.out.println("3. after forName(false)");

        Class.forName("LinkVsInit$Target", true, loader);
        System.out.println("4. after forName(true)");

        System.out.println("5. answer=" + Target.answer);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 LinkVsInit.java
java -cp . LinkVsInit
~~~

**Stdout:**

~~~text
1. before load/link
2. after link: LinkVsInit$Target
3. after forName(false)
Target initialized
4. after forName(true)
5. answer=42
~~~

Diễn giải:

1. `LinkVsInit.Target` là lớp lồng tĩnh; binary name dùng trong API là `LinkVsInit$Target`.
2. `ProbeLoader` có parent là loader nạp class ứng dụng `LinkVsInit`. Khi gọi `loadClass`, nó **delegate** nên `Target` thường được **định nghĩa bởi application loader**, không phải bởi chính `ProbeLoader`.
3. `resolveClass(token)` yêu cầu link, không kích hoạt `static{}`: vì thế thông báo “Target initialized” **chưa xuất hiện** trước dòng số 3.
4. `Class.forName(..., false, loader)` không yêu cầu init; dòng số 3 vẫn in trước thông báo từ block static.
5. `Class.forName(..., true, loader)` yêu cầu initialization lần đầu; block static in “Target initialized”, initializer field đặt `answer=42`.
6. Lần truy cập `Target.answer` sau đó dùng runtime class đã initialized nên không in thông báo lần thứ hai.

**Điểm kiểm chứng:** Thành công của `resolveClass` **không làm class initialized**, kể cả khi class đã linked. Việc ba lệnh truy xuất dùng đúng cùng một `Class<?>` do parent định nghĩa giúp thí nghiệm tránh nhiễu do class identity khác.

Nếu chạy chương trình lại trong **một JVM mới**, block sẽ lại chạy ở runtime class mới của tiến trình mới. Nếu chạy nhiều thao tác trong **cùng JVM và cùng defining loader**, initialization hoàn tất sẽ không lặp lại.

## 5. Nhận diện thao tác kích hoạt khởi tạo

Một đối tượng `Class<?>` mô tả kiểu runtime; hành động dùng kiểu mới quyết định có yêu cầu khởi tạo hay không. Với lớp chưa được khởi tạo:

- `T.class`, `loader.loadClass(name)` và `Class.forName(name, false, loader)` có thể lấy `Class<?>` nhưng không chủ động chạy `<clinit>`.
- `resolveClass(type)` yêu cầu **linking**, vẫn không kích hoạt `<clinit>`. Thí nghiệm `LinkVsInit` ở mục 4 kiểm chứng trực tiếp.
- `Class.forName(name, true, loader)`, `new T()`, gọi static method của `T` và đọc static field không phải constant variable là những thao tác có thể đòi initialization.
- Đọc compile-time constant như `static final int VALUE = 7` có thể được compiler in-line nên không tự gây khởi tạo. Với tên array class, `Class.forName` không khởi tạo element class chỉ do phép tìm mảng.

Khi chẩn đoán, hãy kiểm tra **thao tác active use đầu tiên** của class; dòng log nạp class hoặc kết quả `resolveClass` thành công chưa đủ để kết luận initializer đã chạy.

## 6. Tại sao “đã link” không có nghĩa “đã resolve mọi reference”?

Giả sử class `A` có bytecode gọi `B.work()`. Runtime constant pool của `A` chứa symbolic reference đến class/method liên quan. JVM có thể:

- Xử lý một số symbolic reference ngay khi verify/link class.
- Hoãn việc resolve đến khi instruction liên quan thực sự được thực thi.
- Nạp class phụ trợ trong lúc verify hoặc liên kết, nhưng vẫn chưa initialize chúng.
- Áp dụng loader constraints và access checks khi resolution yêu cầu.

JVMS cho phép **eager hoặc lazy resolution**, nhưng vẫn có ràng buộc về vị trí có thể ném lỗi khi một reference được sử dụng và về một số loại dynamic constants/call sites. Do đó không thể đưa ra lời hứa chung:

> “`resolveClass(A.class)` thành công ⇒ mọi method/field/class được `A` tham chiếu đều đã tồn tại, kiểm tra quyền thành công và chắc chắn các câu lệnh dùng chúng sẽ không ném `LinkageError`.”

Lời hứa trên **sai**. `resolveClass` là API link class; không phải bộ quét dependency transitive hay validator tuyệt đối mọi call site. `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError` hoặc lỗi linkage khác vẫn có thể xuất hiện về sau ở điểm sử dụng một reference.

### 6.1. Loading, verifying, preparing, resolving phụ thuộc nhau nhưng không nhất thiết đồng thời

Một JVM tuân thủ đặc tả đảm bảo:

- Class được load trước khi link.
- Class được verify và prepare hoàn tất trước khi initialize.
- Resolution có thể còn diễn ra **sau thời điểm initialization** đối với một số symbolic references theo chiến lược implementation và giới hạn JVMS.
- Nếu lỗi resolution được phát hiện, nó phải được ném ở điểm hành động của chương trình có thể trực tiếp hoặc gián tiếp cần linkage đó.
- Class có thể đã được load bởi loader A thông qua delegation nhưng **defining loader** thực tế là B. Loading constraints đảm bảo type safety trong những tương tác liên loader.

Hệ quả thực hành: một smoke test chỉ gọi `loadClass(..., true)` hoặc `resolveClass` không thay thế được **integration test thực thi** các API cần dùng. Việc tìm được class chưa chắc phù hợp ABI, module access hay cách sử dụng trong runtime của ứng dụng.

## 7. Khi tự viết `ClassLoader`: đặt `resolveClass` ở đâu?

### 7.1. Trường hợp thường gặp: override `findClass`, giữ `loadClass` mặc định

Nếu bạn chỉ cần bổ sung nguồn bytecode, hãy ưu tiên override `findClass(String)`. Logic parent-first, cache `findLoadedClass`, khóa nạp lớp và cờ `resolve` được `ClassLoader.loadClass` mặc định đảm nhận.

Ví dụ **minh họa phần thân subclass**:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = obtainClassBytes(name); // hàm riêng bạn phải cung cấp
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Đây **không phải chương trình Java chạy độc lập** vì `obtainClassBytes` là hàm giả định dùng để đọc bytes. Ý tưởng chính: `findClass` **định nghĩa** class rồi trả về. Nếu caller đi qua `loadClass(name, true)`, implementation mặc định sẽ gọi `resolveClass`. Không bắt buộc gọi `resolveClass` bên trong `findClass` để mọi thứ “đúng chuẩn”.

### 7.2. Khi override `loadClass(String, boolean)`

Một loader child-first hoặc có chính sách package riêng phải xử lý đúng cache, lock và resolution:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> type = findLoadedClass(name);

        if (type == null) {
            if (isOwnedPackage(name)) {
                try {
                    type = findClass(name);
                } catch (ClassNotFoundException ex) {
                    type = super.loadClass(name, false);
                }
            } else {
                type = super.loadClass(name, false);
            }
        }

        if (resolve) {
            resolveClass(type);
        }
        return type;
    }
}
~~~

Đây là **pseudocode Java** trong subclass: `isOwnedPackage` và `findClass` phụ thuộc triển khai, nên không được copy nguyên vào dự án chưa định nghĩa hai phương thức ấy. Phần chính cần thấy là **`resolveClass(type)` chỉ thực hiện khi cờ `resolve` là `true`**, sau khi có `Class<?>`.

Các nguyên tắc để tránh hỏng loader:

1. Dùng `findLoadedClass(name)` để không cố `defineClass` lặp lại cùng binary name.
2. Đồng bộ theo `getClassLoadingLock(name)` như contract của `ClassLoader`; nếu muốn **parallel capable** phải đăng ký và bảo đảm loader hỗ trợ đúng cơ chế.
3. Giữ consistency: cùng một name đã được loader ghi nhận initiating loader phải trả về đúng `Class` đó trong những lần gọi tương ứng.
4. Đừng định nghĩa lại classes của core Java hoặc shared interfaces thuộc host/plugin boundary theo chính sách child-first không kiểm soát.
5. Hiểu `resolve=true` chỉ yêu cầu **link**, không chạy `<clinit>`.
6. Xử lý `ClassNotFoundException` (không tìm class) khác với `LinkageError` (lỗi binary/verification/constraints), và đừng nuốt lỗi linkage để “thử loader khác” một cách mù quáng.
7. Không gọi `Class.forName(..., true, ...)` tùy tiện trong code nạp plugin nếu chủ đích chỉ kiểm tra sự hiện diện của class; nó có thể chạy side effects static.

### 7.3. `defineClass` và `resolveClass` là hai việc riêng

`defineClass(String, byte[], int, int)` chuyển class bytes thành một runtime `Class<?>` được **defining loader** tạo. `resolveClass(clazz)` là lời gọi bổ sung để link class đó nếu cần. Một số custom loaders chủ động gọi cả hai:

~~~java
Class<?> defined = defineClass(name, bytes, 0, bytes.length);
resolveClass(defined);
return defined;
~~~

Snippet trên chỉ hợp lệ **trong một `ClassLoader` subclass** có sẵn `name` và `bytes`. Nó không tạo object instance và **không** gọi `<clinit>`. Nếu class có initializer thực hiện I/O, tạo thread hoặc gọi service, những hành vi ấy không tự bắt đầu chỉ vì bạn `defineClass` rồi `resolveClass`. Chúng có thể bắt đầu khi về sau gọi `new`, static method, static nonconstant field hoặc reflection yêu cầu initialization.

**Không nên coi `defineClass` tức “mã bytecode đã sẵn sàng cho mọi lời gọi”.** Trạng thái chuẩn bị và lỗi resolution có thể xuất hiện về sau. Hãy phân tách chính sách deploy/nạp với chính sách kích hoạt plugin.

## 8. Một ví dụ giải thích lỗi xảy ra ở initialization, không phải linking

Tệp **`InitFailureAfterLink.java`**:

~~~java
public class InitFailureAfterLink {
    static class Broken {
        static int value = compute();

        private static int compute() {
            System.out.println("running Broken.<clinit>");
            throw new IllegalStateException("missing configuration");
        }
    }

    static class ProbeLoader extends ClassLoader {
        ProbeLoader() {
            super(InitFailureAfterLink.class.getClassLoader());
        }

        Class<?> link(String name) throws ClassNotFoundException {
            Class<?> type = loadClass(name, false);
            resolveClass(type);
            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        ProbeLoader probe = new ProbeLoader();
        Class<?> type = probe.link("InitFailureAfterLink$Broken");
        System.out.println("linked: " + type.getName());

        try {
            Class.forName("InitFailureAfterLink$Broken", true, probe);
        } catch (ExceptionInInitializerError error) {
            System.out.println("initialization failed: "
                    + error.getCause().getClass().getSimpleName());
        }

        try {
            Class.forName("InitFailureAfterLink$Broken", true, probe);
        } catch (NoClassDefFoundError error) {
            System.out.println("later use: "
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 InitFailureAfterLink.java
java -cp . InitFailureAfterLink
~~~

Stdout:

~~~text
linked: InitFailureAfterLink$Broken
running Broken.<clinit>
initialization failed: IllegalStateException
later use: NoClassDefFoundError
~~~

Phân tích:

- `probe.link` trả về thành công: class được load/link nhưng **chưa initialized**, nên method `compute()` chưa chạy.
- `Class.forName(..., true, probe)` yêu cầu initialization; compiler đã đặt lời gọi `compute()` vào `<clinit>`. `IllegalStateException` (không phải `Error`) được JVM bọc bằng `ExceptionInInitializerError`.
- Runtime class sau đó ở trạng thái **erroneous**; lần yêu cầu initialization kế tiếp của **cùng class identity** gặp `NoClassDefFoundError`. Điều đó không chứng minh file `.class` biến mất và không có tác dụng gọi lại `resolveClass` để sửa.
- Một bản class cùng tên do **loader khác tự định nghĩa** là runtime class identity khác, nhưng việc tạo loader mới không giải quyết nguyên nhân “missing configuration”; cần sửa nguồn lỗi.

**Lưu ý:** Cả `ExceptionInInitializerError` và `NoClassDefFoundError` là subclasses của `Error`, thuộc failure class initialization; với một class file hỏng hoặc truy cập module sai, lỗi có thể xảy ra sớm hơn trong loading/linking. Không nên gộp mọi failure của class loader thành một exception duy nhất.

## 9. Phân biệt ba nhóm lỗi khi debug

| Giai đoạn hoặc tình huống | Biểu hiện phổ biến | Điều nên kiểm tra |
| --- | --- | --- |
| Tìm class bằng tên thất bại | `ClassNotFoundException` từ `loadClass`/`Class.forName` | Loader, binary name, class path/module path, JAR, cơ chế delegation |
| Class file version VM không hỗ trợ | `UnsupportedClassVersionError` | `java -version`, `javap -verbose` major version, `javac --release` |
| Bytecode không hợp lệ | `ClassFormatError`, `VerifyError` | Bytecode generator/instrumentation, phiên bản class file |
| Binary contract khác lúc biên dịch | `NoSuchMethodError`, `NoSuchFieldError`, `IncompatibleClassChangeError` | Dependency version, classpath/module graph, loader chọn class nào |
| Quy tắc visibility/loading constraints | `IllegalAccessError` hoặc `LinkageError` phù hợp | JPMS readability/exports, runtime package, class identity |
| Tính toán static initializer thất bại | `ExceptionInInitializerError` hoặc `Error` gốc | `<clinit>`, static fields, cấu hình, side effects đầu tiên |
| Class đã erroneous sau lần initialize thất bại | `NoClassDefFoundError` | Lần lỗi initialization **trước** đó trong cùng runtime class |
| Cố dùng protected `resolveClass` ngoài subclass | **Compile-time access error** | Quyền truy cập Java, không phải lỗi loading của JVM |
| Gọi `resolveClass(null)` trong subclass | `NullPointerException` | Đối số null, không phải “class chưa load” |

**Cảnh báo quan trọng:** Bảng nêu triệu chứng *thường gặp*, không phải khẳng định JVM luôn ném mỗi loại lỗi tại một bước cố định. JVM cho phép eager/lazy resolution có kiểm soát, nên một lỗi binary dependency có thể chỉ xuất hiện khi thực thi instruction cụ thể.

### 9.1. Vì sao chỉ gọi `resolveClass` không đủ test toàn bộ dependency?

Mã plugin có thể chứa tham chiếu symbolic đến `LibraryV2.doWork()` nhưng runtime chỉ cung cấp `LibraryV1`. Nếu JVM chưa cần resolve method reference đó trong quá trình link ban đầu, `resolveClass` có thể trả về bình thường. Khi code thực sự gọi method, JVM có thể ném `NoSuchMethodError`.

Do vậy test phải **thực thi đường đi nghiệp vụ cần hỗ trợ**, không dừng ở `Class<?> c = loader.loadClass(name)` hay `resolveClass(c)`. Đồng thời cần test startup, static initialization, quyền module, và cả interaction giữa class loaders.

## 10. `resolveClass` có chủ động load superclass/dependency không?

Các giai đoạn class loading và verification/linking có thể yêu cầu tải thêm các class/interface như superclass hoặc những lớp cần để verify descriptor/hierarchy. Nhưng không nên suy luận từ đó rằng:

- **Mọi** class mà source import đều phải đã được nạp sau `resolveClass`.
- **Mọi** class xuất hiện trong method body đều đã initialized.
- Tất cả static fields của các class phụ trợ đã nhận giá trị từ initializer.
- Loader con chắc chắn đã tự define class nếu nó gọi `resolveClass`.

Một class có thể được loaded/linked mà các dependency ở đường code chưa chạy vẫn chưa được sử dụng; các reference có thể chờ resolve theo chính sách JVM. Import Java là khái niệm cú pháp compile-time, không phải danh sách phụ thuộc class loader phải nạp ngay.

**Điểm hay bị bỏ sót:** Khi `ClassLoader` subclass gọi `resolveClass(c)`, `c` có thể đến từ **parent delegation**. Lời gọi link không biến subclass thành **defining loader** của `c`. Quan sát đúng:

~~~java
Class<?> c = someLoader.loadClass("java.lang.String");
System.out.println(c.getClassLoader() == null);
~~~

Với runtime Java phổ biến nơi `String` thuộc bootstrap loader, chương trình in `true`. Nhưng đây chỉ là snippet nằm trong class có biến `someLoader` hợp lệ; không nên in tên implementation nội bộ để suy ra class identity.

## 11. Linking ≠ initialization trong ứng dụng thực

### 11.1. Plugin discovery

Một host muốn hiển thị danh sách plugins có thể chỉ **load class token** của provider để xác minh metadata, không muốn tạo database connection hoặc thread từ static initializer. Thông thường:

1. Dùng metadata/JAR descriptor để tìm candidate.
2. Dùng `Class.forName(binaryName, false, pluginLoader)` khi cần token.
3. Kiểm tra contract bằng `SharedApi.class.isAssignableFrom(candidate)` với **SharedApi do loader chung định nghĩa**.
4. Chỉ khi đã chọn provider và sẵn sàng start lifecycle, thực hiện reflection/constructor/static entry point theo API cần dùng.

**Đừng dùng `resolveClass` như “safe dry run” tuyệt đối:** việc link vẫn có thể nạp/verify class khác, tốn chi phí, gặp lỗi linkage hoặc kích hoạt hành vi do custom loader của bạn tự cài đặt. Bên cạnh đó, thao tác reflection tiếp theo có thể làm class initialize tùy method và API cụ thể.

### 11.2. Framework dependency injection và reflection

Việc framework đọc `Class<?>`, annotations, method/field metadata có thể xảy ra trước khi object được tạo. Nhưng không nên khẳng định mọi reflection API đều không kích hoạt initialization: phải đọc contract của API được gọi. Ví dụ `Class.forName(name,true,loader)` cố ý init, còn `Class.forName(name,false,loader)` không yêu cầu init.

Nếu cấu hình framework có lỗi `ExceptionInInitializerError`, trước hết xác định **thao tác active use nào xảy ra trước** thay vì mặc định quy lỗi cho bước “scan class”. Tương tự, lỗi `NoClassDefFoundError` ở lần truy cập sau có thể phản ánh một initialization failure từ startup.

### 11.3. Hot reload và class-loader isolation

Mỗi class thường được initialize tối đa một lần **theo runtime class identity**. Khi host tạo loader mới và **define** cùng binary name thành một class mới, class mới có trạng thái static riêng và có thể được initialized riêng. Nếu loader mới chỉ delegate về class cũ, `resolveClass` hay `Class.forName(...,true,loaderMoi)` không tạo một phiên bản kiểu mới.

Vì vậy, khi hot reload:

- Ghi rõ **defining loader** của API dùng chung và plugin classes.
- Đừng dùng `resolveClass` để mong “reset” static state.
- Dọn thread/callback/cache/`ThreadLocal` để loader cũ có thể được GC theo điều kiện của runtime; `URLClassLoader.close()` không đảm bảo unload tức thì.
- Xử lý plugin lifecycle bằng API rõ ràng, tránh đặt toàn bộ startup/teardown trong static initializer.

## 12. Những giới hạn và chi tiết triển khai cần nêu đúng

- **Không thể gọi trực tiếp `<clinit>` từ Java source** như method thông thường. Compiler tạo nội dung từ static initializers; VM quyết định thời điểm initialization theo quy tắc.
- **`resolveClass` không phải synonym của `Class.forName(..., true, ...)`**. Một API link; một API yêu cầu initialize.
- **`loadClass(name, false)` không cam kết class hoàn toàn chưa linked**. Nó chỉ không chủ động request `resolveClass` theo đường API này.
- **`resolveClass` không cam kết eager resolution toàn bộ runtime constant pool**; JVMS cho phép lazy resolution.
- **`resolveClass` không phải method public** và không dùng để thay Java module readability/access checks.
- **Không có guarantee về thứ tự log “class loaded”, “class linked”, “class initialized”** như một chuỗi duy nhất trên mọi JVM; log là quan sát của triển khai, không thay đặc tả.
- **Có thể gặp lỗi linker trước initializer**. Ví dụ class file sai major version hay bytecode verification failure. Nhưng không giả định một lỗi symbolic reference nhất định sẽ được phát hiện ngay lần gọi `resolveClass`.
- **Không dùng cờ `resolve=true` để ép reload class**. Cùng class token đã linked thì lời gọi no-op; reload thực sự phụ thuộc runtime class mới do defining loader khác tạo.
- **Initialization an toàn phối hợp giữa threads**, nhưng việc cập nhật mutable static state sau init vẫn cần đồng bộ riêng theo Java Memory Model.
- **Class path/module path có thể đổi runtime identity/access**, nhưng không đổi định nghĩa của `resolveClass` trong Java SE API.

## 13. Cách quan sát trên JDK 17+ mà không nhầm log với đặc tả

### 13.1. `javap` cho biết mã `<clinit>` có tồn tại không

Biên dịch `LinkVsInit.java` trước, rồi:

~~~bash
javap -c -p 'LinkVsInit$Target'
~~~

Trong PowerShell và Unix shell, dấu nháy đơn bảo vệ dấu `$` của binary name. `javap` thường hiển thị phần khởi tạo class dưới tiêu đề `static {};`. Phần đó chứa bytecode in “Target initialized” và gán `answer=42`. Việc tìm thấy đoạn bytecode **không** nói nó đã thực thi trong một process cụ thể.

### 13.2. Unified logging của HotSpot

Nếu dùng OpenJDK/HotSpot có hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info LinkVsInit
java -Xlog:class+init=info LinkVsInit
java -Xlog:help
~~~

- `class+load` cho thấy các sự kiện load; tải class **không đồng nghĩa** init.
- `class+init` cho phép quan sát một số sự kiện khởi tạo trên JVM/hệ thống hỗ trợ tag đó; đầu ra có thể rất dài.
- `-Xlog` là cơ chế logging của JVM triển khai, không phải API chung mọi Java Virtual Machine phải hỗ trợ. Kiểm tra `java -Xlog:help` khi chuyển JDK/vendor.

**Không parse message format của HotSpot để suy ra quy tắc ngôn ngữ.** Dùng chương trình in mốc “before/after” và đối chiếu JVMS/JLS để hiểu hành vi.

### 13.3. Quan sát trong debugger

Debugger có thể tự đánh giá expression hoặc gọi method qua reflection, từ đó **gây initialization ngoài ý định thí nghiệm**. Khi so sánh `resolveClass` với `Class.forName(true)`, chạy chương trình qua command line và không evaluate static fields trong debugger trước khi đọc stdout. Nếu lớp đã initialized do một thao tác khác, thí nghiệm sẽ không có dòng “Target initialized” ở vị trí kỳ vọng.

## 14. Checklist chọn API đúng

| Mục tiêu | API/kỹ thuật phù hợp | Vì sao |
| --- | --- | --- |
| Biết lớp có thể tìm theo tên qua loader không | `loader.loadClass(binaryName)` | Tra cứu class; không chủ động init theo hợp đồng mặc định |
| Có class token nhưng cần yêu cầu link trong loader tùy biến | `resolveClass(token)` bên trong subclass | Explicit link; không tự kích hoạt `<clinit>` |
| Lấy class token mà muốn trì hoãn init | `Class.forName(binaryName,false,loader)` | Không yêu cầu init |
| Muốn chắc class được initialize trước khi vào lifecycle tiếp theo | `Class.forName(binaryName,true,loader)` | Yêu cầu init theo runtime identity |
| Chạy ứng dụng bình thường | `new`/static method/field access | JVM tự link/init khi cần; không thêm `resolveClass` thủ công |
| Khẳng định class đã load đúng bản | `clazz.getClassLoader()`, `clazz.getModule()`, source/dependency | Kiểm tra class identity/nguồn class |
| Bắt vấn đề binary compatibility | Thực thi đường code thực + integration tests | `resolveClass` không bảo đảm mọi symbolic reference đã resolve |
| Debug lỗi init | Đọc `ExceptionInInitializerError.getCause()` và log đầu tiên | Phân biệt initialization failure và class not found |

### 14.1. Những câu hỏi “đúng/sai” có đáp án

1. “`resolveClass` gọi `<clinit>` của lớp được truyền vào.” — **Sai**.
2. “`resolveClass` là `protected final void` trong `ClassLoader`.” — **Đúng**.
3. “`resolveClass` buộc resolve mọi method/field reference trong constant pool trước khi trả về.” — **Sai**.
4. “`loadClass(name, false)` sẽ khiến class chắc chắn vẫn chưa link.” — **Sai**.
5. “`Class.forName(name, false, loader)` không yêu cầu initialize class.” — **Đúng**.
6. “`Class.forName(name, true, loader)` initialize lại mỗi lần gọi.” — **Sai**.
7. “Static initializer có thể ném lỗi sau khi `resolveClass` từng trả thành công.” — **Đúng**.
8. “Một class có thể load và link xong, rồi mới gặp `NoSuchMethodError` tại call site.” — **Đúng** nếu resolution method reference được thực hiện muộn theo JVMS.
9. “`resolveClass(c)` đổi defining loader của `c` thành loader đang gọi.” — **Sai**.
10. “Nếu code được định nghĩa bởi loader khác với tên class giống hệt, đó có thể là runtime class riêng và khởi tạo riêng.” — **Đúng**.

## 15. Tài liệu gốc để tự đối chiếu

1. [`ClassLoader.resolveClass` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html#resolveClass(java.lang.Class)) — `protected final`; tài liệu xác định chức năng chính là **link specified class**, đồng thời ghi tên method hơi gây nhầm.
2. [`ClassLoader.loadClass(String, boolean)` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)) — trình tự `findLoadedClass` → delegation → `findClass` → `resolveClass` khi flag true.
3. [`Class.forName` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)) — ý nghĩa của tham số `initialize`.
4. [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3) — class identity, defining/initiating class loaders.
5. [JVMS 5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4) — verification, preparation, resolution và sự linh hoạt eager/lazy.
6. [JVMS 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5) — `ConstantValue`, `<clinit>`, triggers và trạng thái erroneous.
7. [JLS 12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4) — active use, superclasses, superinterfaces và cơ chế phối hợp thread.

**Tóm ý:** `resolveClass` là công cụ **linking** của `ClassLoader`, không phải lời gọi chạy static initializer. Cờ `resolve` trong `loadClass` không đồng nghĩa `initialize` trong `Class.forName`. Muốn hiểu lỗi class loading chính xác, luôn tách **loading → linking (verification/preparation/resolution) → initialization** và nhớ JVM có thể giải symbolic references ở thời điểm khác nhau.
