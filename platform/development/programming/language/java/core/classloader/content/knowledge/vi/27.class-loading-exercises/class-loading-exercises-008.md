# Tái hiện NoClassDefFoundError và lỗi khởi tạo lớp trong Java

Một ứng dụng Java có thể biên dịch thành công rồi thất bại khi chạy với `java.lang.NoClassDefFoundError`. Nhiều người nhìn tên lỗi và kết luận đơn giản rằng “file `.class` không tồn tại”. Điều này **đúng trong một số tình huống nhưng không phải tất cả**. Một class **có thể vẫn nằm trên classpath và đã được JVM tìm thấy**, nhưng vì **static initialization thất bại**, các lần sử dụng class sau đó vẫn ném `NoClassDefFoundError: Could not initialize class ...`.

Bài thực hành này dùng Java 17+ để tái hiện độc lập hai nhóm lỗi:

1. **Thiếu dependency tại runtime:** `app.MissingDemo` đã biên dịch khi `lib.Helper` còn tồn tại, nhưng lúc chạy chỉ cung cấp output của ứng dụng. JVM không tìm được class cần liên kết: xuất hiện `NoClassDefFoundError`; nguyên nhân (*cause*) trong thí nghiệm là `ClassNotFoundException`.
2. **Lỗi class initialization (`<clinit>`):** class `demo.Broken` được tìm thấy, nhưng static initializer ném `IllegalStateException`. Lần active use đầu tiên thấy `ExceptionInInitializerError`, lớp chuyển sang trạng thái **erroneous**; lần active use tiếp theo trong **cùng JVM, cùng định nghĩa class** thấy `NoClassDefFoundError`.

Mục tiêu: hiểu thứ tự **loading → linking → initialization**, phân biệt ba lỗi `ClassNotFoundException`, `ExceptionInInitializerError` và `NoClassDefFoundError`; biết viết thí nghiệm biên dịch/chạy đúng, giải thích stdout đã kiểm chứng, xác định nguyên nhân gốc bằng stack trace/cause/loader và xử lý đúng khi ứng dụng hoặc plugin đã nạp class lỗi.

## 1. Đặt vấn đề: tìm không được class hay class đã khởi tạo thất bại?

Hãy xem ba thông báo:

```text
java.lang.ClassNotFoundException: lib.Helper

java.lang.NoClassDefFoundError: lib/Helper

java.lang.NoClassDefFoundError: Could not initialize class demo.Broken
```

Các thông báo có thể trông giống nhau, nhưng nói về những bước khác nhau:

| Tình huống | Loại throwable thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Ứng dụng gọi `ClassLoader.loadClass("lib.Helper")` theo tên nhưng loader không thấy | `ClassNotFoundException` (*checked exception*) | Tên class, loader cụ thể, classpath/module path |
| Bytecode đã compile cần `lib.Helper` nhưng runtime không tìm được định nghĩa | `NoClassDefFoundError` (*LinkageError*) | Compile/runtime dependencies, loader, file JAR, class root |
| Class được tìm thấy, static initializer ném `RuntimeException` ở lần đầu | `ExceptionInInitializerError` (*LinkageError*) | Lỗi thực sự trong `static { ... }` hoặc static field initialization |
| Sau khi class đã rơi vào trạng thái khởi tạo lỗi, code lại active-use cùng class | `NoClassDefFoundError` | Tìm **lần khởi tạo thất bại đầu tiên** trong log, không chỉ nhìn lỗi về sau |

Với `NoClassDefFoundError`, **message và cause là dữ liệu chẩn đoán, không phải API ổn định để parse bằng chuỗi cứng**. Nội dung của thông báo có thể khác theo JVM hoặc cách tình huống phát sinh.

## 2. Thứ bậc lỗi trong java.lang

```text
java.lang.Throwable
├── Exception
│   └── ReflectiveOperationException
│       └── ClassNotFoundException
└── Error
    └── LinkageError
        ├── NoClassDefFoundError
        ├── ExceptionInInitializerError
        ├── NoSuchMethodError
        ├── NoSuchFieldError
        ├── IllegalAccessError
        └── ...
```

- `ClassNotFoundException` là **checked exception** thường xuất hiện từ lời gọi tìm class bằng tên như `Class.forName(...)` và `ClassLoader.loadClass(...)`.
- `NoClassDefFoundError` và `ExceptionInInitializerError` là **Error thuộc họ LinkageError**.
- `catch (Exception ex)` **không bắt** được hai Error này. Trong phòng lab có thể cố ý `catch (LinkageError)` để quan sát hai lần sử dụng; **không nên che lỗi liên kết trong nghiệp vụ production**.
- Một `NoClassDefFoundError` có thể có `getCause()==ClassNotFoundException` khi thiếu class; nhưng nếu lớp đã ở trạng thái erroneous, cause **có thể là lỗi khởi tạo trước đó**. Vì thế phải đọc cả cause chain.

## 3. Ba giai đoạn của vòng đời class

Theo JLS/JVMS, khi sử dụng class, JVM có các công việc phân biệt:

```text
LOAD
  |
  | JVM/class loader tìm binary class definition và tạo Class<?> runtime
  v
LINK
  |
  +-- Verify: kiểm tra tính hợp lệ của bytecode
  +-- Prepare: chuẩn bị static fields với giá trị mặc định
  +-- Resolve: nối symbolic references tới class/field/method
  |            (một số resolution có thể được trì hoãn)
  v
INITIALIZE
  |
  +-- Khởi tạo superclass/superinterfaces cần thiết
  +-- Gán static fields theo initializer
  +-- Chạy static blocks theo thứ tự văn bản
  v
READY hoặc ERRONEOUS
```

### Loading

`ClassLoader.loadClass("demo.Broken")` thường tải hoặc tìm class nhưng **không yêu cầu chạy static initializer ngay**. Class `Broken` có thể đã được biểu diễn bởi một `Class<?>` hợp lệ dù `<clinit>` chưa chạy.

### Linking

Trong giai đoạn verification/preparation/resolution, bytecode có thể tham chiếu tới classes chưa được nạp vào thời điểm ban đầu. JVM có quyền trì hoãn một số symbolic reference resolution; vì vậy lỗi dependency có thể chỉ xuất hiện **khi thực thi code path tương ứng**. Không giả định mọi dependency thiếu đều làm ứng dụng chết ngay lúc bắt đầu.

### Initialization

Khi chương trình lần đầu *active use* một class, JVM đảm bảo class được initialize theo quy tắc Java. Static field initializers và `static { ... }` được thực hiện trong thứ tự thích hợp. Nếu initializer hoàn thành bình thường, class sẵn sàng. Nếu initializer thất bại, class có thể bị đánh dấu **erroneous**; các lần khởi tạo tiếp theo của **cùng runtime class** không được tự retry như một constructor thông thường.

**Đây là nền tảng để hiểu vì sao “file class vẫn còn trên đĩa” nhưng sau lần lỗi đầu lại xuất hiện `NoClassDefFoundError`.**

## 4. Lab A — Thiếu thư viện ở runtime, tái hiện NoClassDefFoundError

Mục tiêu: tạo một dependency `lib.Helper` riêng khỏi ứng dụng. Biên dịch ứng dụng với dependency đầy đủ rồi **cố ý bỏ thư mục dependency khỏi runtime classpath**.

### 4.1 Cấu trúc dự án

```text
ncdfe-lab/
├── src/
│   ├── lib/
│   │   └── Helper.java
│   └── app/
│       └── MissingDemo.java
├── lib-classes/               (output của Helper)
└── app-classes/               (output của MissingDemo)
```

Tạo `lib-classes` và `app-classes` trước khi biên dịch. Chạy các lệnh từ **thư mục `ncdfe-lab`**, không phải từ `src`.

### 4.2 Tạo thư viện

File `src/lib/Helper.java`:

```java
package lib;

public final class Helper {
    public static String message() {
        return "Helper available";
    }
}
```

Class `lib.Helper` là dependency của ứng dụng. Compiler cần thấy API `message()` để biên dịch thành công.

### 4.3 Tạo consumer

File `src/app/MissingDemo.java`:

```java
package app;

import lib.Helper;

public final class MissingDemo {
    public static void main(String[] args) {
        System.out.println("app started");

        try {
            System.out.println(Helper.message());
        } catch (NoClassDefFoundError error) {
            System.out.println("error="
                    + error.getClass().getSimpleName());
            System.out.println("missing=" + error.getMessage());

            Throwable cause = error.getCause();
            System.out.println("cause="
                    + (cause == null
                       ? "<none>"
                       : cause.getClass().getSimpleName()));
        }
    }
}
```

**Vì sao cố ý bắt `NoClassDefFoundError`?** Chỉ để thí nghiệm in được loại lỗi, tên class không tìm được và cause thay vì kết thúc JVM với stack trace dài. Một ứng dụng thật phải sửa runtime deployment; nó không nên coi dependency thiếu là một nhánh nghiệp vụ bình thường.

### 4.4 Biên dịch với đúng dependency

```bash
javac --release 17 -d lib-classes src/lib/Helper.java
javac --release 17 -cp lib-classes -d app-classes src/app/MissingDemo.java
```

- Lệnh đầu tạo `lib-classes/lib/Helper.class`.
- Lệnh sau cho `javac` thấy `lib.Helper` qua `-cp lib-classes` và tạo `app-classes/app/MissingDemo.class`.
- `-d` chỉ định output root; package paths được tạo tương ứng.
- **Không thêm cả hai source files vào một lần `javac` rồi cùng output**, vì thí nghiệm cần **tách được output dependency khỏi output ứng dụng**.

### 4.5 Trường hợp đối chứng — runtime classpath đúng

**Windows** dùng `;` làm path separator:

```bash
java -cp "app-classes;lib-classes" app.MissingDemo
```

**Linux/macOS** dùng `:`:

```bash
java -cp "app-classes:lib-classes" app.MissingDemo
```

Stdout đã được biên dịch/chạy kiểm chứng:

```text
app started
Helper available
```

`app.MissingDemo` và `lib.Helper` đều được loader thấy. Không có lỗi linkage.

### 4.6 Trường hợp lỗi — chỉ bỏ dependency ở runtime

**Không recompile**. Chạy:

```bash
java -cp app-classes app.MissingDemo
```

Stdout đã được kiểm chứng:

```text
app started
error=NoClassDefFoundError
missing=lib/Helper
cause=ClassNotFoundException
```

Giải thích chính xác:

1. JVM tìm được `app.MissingDemo` từ `app-classes`; do đó chương trình in `app started`.
2. Khi thực thi lời gọi `Helper.message()`, bytecode cần resolve class `lib.Helper`.
3. Runtime classpath **không có `lib-classes`**, nên loader không tìm được định nghĩa class đó.
4. Bytecode use nhận `NoClassDefFoundError`; cause trong thí nghiệm là `ClassNotFoundException`.
5. Đây là **thiếu dependency trong runtime classpath**, không phải static initializer của `Helper` bị lỗi (vì `Helper` chưa được tìm thấy).

Tên trong message dùng dấu gạch chéo `lib/Helper` theo VM internal representation, trong khi Java binary name viết `lib.Helper`. Không lấy dấu slash trong lỗi làm bằng chứng rằng source code phải import bằng slash.

### 4.7 Đối chiếu bytecode của ứng dụng

```bash
javap -classpath app-classes -c -verbose app.MissingDemo
```

Trong constant pool/bytecode của chương trình đã chạy, phần đáng chú ý:

```text
Methodref ... // lib/Helper.message:()Ljava/lang/String;
Class ...     // lib/Helper
...
invokestatic ... // Method lib/Helper.message:()Ljava/lang/String;
```

`javap` chứng minh **caller đã compile against `lib.Helper`**, còn runtime thiếu định nghĩa mà symbolic reference ấy cần. Các chỉ số constant pool (`#21`, `#22`, ...) có thể khác khi source/compiler thay đổi; phần quan trọng là **owner, method name và descriptor**.

**Kết luận Lab A:** class có tồn tại **lúc biên dịch**, nhưng vắng mặt khỏi nguồn loader thấy **lúc chạy**. Thêm dependency đúng vào runtime classpath sẽ làm cùng binary client chạy được mà không cần sửa code.

## 5. Lab B — Static initializer thất bại rồi NoClassDefFoundError xuất hiện ở lần sau

Lab này cố ý **không xóa class file nào**. Class `demo.Broken` luôn có trên runtime classpath. Ta làm `static { ... }` ném một exception tại lần khởi tạo đầu tiên.

### 5.1 Cấu trúc

```text
ncdfe-lab/
├── init-src/
│   └── demo/
│       ├── Broken.java
│       └── InitDemo.java
└── init-classes/             (output riêng)
```

Tạo thêm `init-src/demo` và `init-classes` bên cạnh các thư mục của Lab A.

### 5.2 Class Broken có static initializer chủ động lỗi

File `init-src/demo/Broken.java`:

```java
package demo;

public final class Broken {
    public static int number;

    static {
        System.out.println("<clinit> entered");

        if (Boolean.parseBoolean(
                System.getProperty("lab.fail", "true"))) {
            throw new IllegalStateException("boom");
        }

        number = 42;
    }
}
```

Giải thích:

- JVM thực hiện static initialization khi class được active-use lần đầu theo JLS.
- `System.getProperty("lab.fail", "true")` mặc định bằng `"true"` nếu không truyền JVM property.
- `Boolean.parseBoolean(...)` được tính lúc chạy, nên compiler chấp nhận static initializer có nhánh có thể ném exception (không phải một khối bị chứng minh luôn thất bại ở compile-time).
- `IllegalStateException` **không phải subclass của `Error`**, nên JLS yêu cầu JVM bọc nó thành `ExceptionInInitializerError` khi quá trình initialization thất bại.
- Nếu property là `false`, static initializer đặt `number = 42` và class khởi tạo thành công.
- `number` là non-final field, nên đọc nó qua `Broken.number` thật sự kích hoạt class initialization nếu chưa initialized.

### 5.3 Consumer cố active-use hai lần trong cùng JVM

File `init-src/demo/InitDemo.java`:

```java
package demo;

public final class InitDemo {
    public static void main(String[] args) {
        System.out.println("loaded without init="
                + Broken.class.getName());

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(
                        "attempt " + attempt + " value=" + Broken.number);
            } catch (LinkageError error) {
                System.out.println(
                        "attempt " + attempt + " error="
                        + error.getClass().getSimpleName());

                Throwable cause = error.getCause();
                System.out.println("cause="
                        + (cause == null
                           ? "<none>"
                           : cause.getClass().getSimpleName()));
            }
        }
    }
}
```

**Điểm mấu chốt:** `Broken.class` dùng để lấy class literal; nó **không tự bắt buộc chạy `<clinit>`**. Nhưng đọc `Broken.number` — một static field không phải constant variable — là **active use** và yêu cầu class được initialize.

Lệnh `catch (LinkageError)` chỉ dành cho lab để in rõ lần đầu/lần sau; không dùng cách “bắt lỗi rồi chạy tiếp” làm giải pháp phục hồi class trong production.

### 5.4 Biên dịch

```bash
javac --release 17 -d init-classes init-src/demo/Broken.java init-src/demo/InitDemo.java
```

Kết quả có:

```text
init-classes/demo/Broken.class
init-classes/demo/InitDemo.class
```

**Cả hai class files hiện diện** trong runtime path. Không xóa/thay `Broken.class` ở bất kỳ bước nào của Lab B.

### 5.5 Chạy mặc định — class khởi tạo thất bại

```bash
java -cp init-classes demo.InitDemo
```

Stdout **đã chạy kiểm chứng**:

```text
loaded without init=demo.Broken
<clinit> entered
attempt 1 error=ExceptionInInitializerError
cause=IllegalStateException
attempt 2 error=NoClassDefFoundError
cause=ExceptionInInitializerError
```

Giải thích lần lượt:

1. `loaded without init=demo.Broken`: JVM có `Class<?>` cho `Broken`, nhưng chưa chạy static initializer; câu lệnh class literal không active-use class theo cách bắt buộc initialization.
2. `<clinit> entered`: khi đọc `Broken.number` lần đầu, JVM thực hiện static initialization.
3. `attempt 1 error=ExceptionInInitializerError`: static block ném `IllegalStateException("boom")`; JVM bọc lỗi khởi tạo vào `ExceptionInInitializerError`.
4. `cause=IllegalStateException`: nguyên nhân gốc mà người phát triển cần sửa nằm trong static initializer, không phải vấn đề classpath.
5. `attempt 2 error=NoClassDefFoundError`: JVM ghi nhận `demo.Broken` đã ở trạng thái **erroneous** sau lần init thất bại, nên không chạy lại `<clinit>` của cùng class.
6. `cause=ExceptionInInitializerError`: JVM của thí nghiệm còn giữ chuỗi nguyên nhân liên quan tới lần init trước. **Không giả định mọi JVM luôn đóng gói cause theo đúng cùng format**; hãy tìm lỗi đầu tiên trong log.

Không có dòng `<clinit> entered` lần thứ hai. Đó là bằng chứng thực tế rằng **static initializer không được retry tự động**.

### 5.6 Chạy một tiến trình mới với property sửa đúng

Chạy **JVM mới**:

```bash
java -Dlab.fail=false -cp init-classes demo.InitDemo
```

Với PowerShell trên Windows, nếu cần quote để shell không diễn giải dấu gạch ngang/syntax, có thể dùng:

```powershell
java '-Dlab.fail=false' -cp init-classes demo.InitDemo
```

Stdout đã xác minh:

```text
loaded without init=demo.Broken
<clinit> entered
attempt 1 value=42
attempt 2 value=42
```

Lúc này class initialization hoàn thành bình thường. Trong cùng tiến trình, lần truy cập thứ hai không chạy `<clinit>` nữa vì class đã initialized.

**Điều quan trọng:** Đây là **tiến trình mới**. Việc sửa property **sau khi class đã erroneous trong cùng runtime class definition** không khiến `<clinit>` tự chạy lại. Để phục hồi class definition lỗi trong một ứng dụng có custom loader, thường cần sửa nguyên nhân và tạo **định nghĩa mới trong class loader mới** theo lifecycle plugin phù hợp, hoặc restart JVM; không thể “reset erroneous flag” bằng Java API công khai.

## 6. So sánh Lab A và Lab B bằng bằng chứng

| Câu hỏi | Lab A: Thiếu class runtime | Lab B: Static initialization thất bại |
| --- | --- | --- |
| Class cần dùng tồn tại trong runtime output? | **Không**: `lib.Helper` bị loại khỏi runtime classpath | **Có**: `demo.Broken.class` ở `init-classes` |
| Caller đã compile được? | Có, compile với `lib-classes` | Có, cả `Broken` và `InitDemo` compile cùng nhau |
| Điểm làm lỗi phát sinh | Link class `lib.Helper` khi gọi `Helper.message()` | Active use `Broken.number` lần đầu |
| Lỗi quan sát đầu tiên | `NoClassDefFoundError` | `ExceptionInInitializerError` |
| Cause trong thí nghiệm | `ClassNotFoundException` | `IllegalStateException` |
| Lỗi khi thử lại trong cùng JVM | Không thể dựa vào một kiểu message chung; còn phụ thuộc loader/linkage state | `NoClassDefFoundError` vì class đã ở trạng thái erroneous |
| Hướng sửa | Đưa đúng class/JAR vào **runtime classpath/loader** | Sửa lỗi static initializer/config và tạo quá trình init mới hợp lệ |
| Cần recompile caller không? | Không nếu dependency binary tương thích và được deploy đúng | Không nếu code nguyên nhân và config đã đúng, nhưng class erroneous cũ không tự hồi phục |
| Classloader quan trọng thế nào? | Loader không thấy `lib.Helper` | Identity/trạng thái erroneous gắn với một class definition được loader định nghĩa |
| Có phải `ClassNotFoundException` trực tiếp từ API reflection? | Không: caller dùng bytecode method reference, nên hiện `NoClassDefFoundError` | Không: class đã được tìm thấy và bắt đầu initialize |

Vì **cùng một lỗi cuối `NoClassDefFoundError` có nhiều nguyên nhân**, chẩn đoán phải bắt đầu từ **đường diễn biến trước đó và cause chain**.

## 7. Theo dõi cause chain thay vì chỉ tên lỗi

Trong production, stack trace đầy đủ có thể cho thấy:

**Thiếu dependency:**

```text
java.lang.NoClassDefFoundError: lib/Helper
    ...
Caused by: java.lang.ClassNotFoundException: lib.Helper
    ...
```

**Static initializer lỗi lần đầu:**

```text
java.lang.ExceptionInInitializerError
    ...
Caused by: java.lang.IllegalStateException: boom
    at demo.Broken.<clinit>(Broken.java:...)
    ...
```

**Sử dụng lại class đã erroneous:**

```text
java.lang.NoClassDefFoundError: Could not initialize class demo.Broken
    ...
```

Đây là **các mẫu rút gọn, không phải stdout cố định**; stack trace line numbers và cách trình bày causes khác nhau theo JVM/build.

Cách đọc:

1. **Loại throwable đầu tiên ở log lịch sử**: trước `NoClassDefFoundError` có `ExceptionInInitializerError` không?
2. **Message**: là binary name bị thiếu `lib/Helper` hay câu “Could not initialize class ...”?
3. **Cause**: `ClassNotFoundException`, `IllegalStateException`, `NullPointerException` hay một lỗi khác?
4. **Frame `<clinit>`**: nếu có, đối chiếu static field initializer/static block tại class tương ứng.
5. **Loader và CodeSource**: class thực tế do loader nào định nghĩa, lấy từ JAR nào?
6. **Thời điểm**: startup, request đầu tiên, task plugin hay redeploy?

**Đừng cắt mất dòng `Caused by` khi chuyển log cho người điều tra.** Một `NoClassDefFoundError` muộn thường chỉ là hậu quả, không phải nguyên nhân đầu.

## 8. Thao tác nào thực sự kích hoạt class initialization?

JLS `12.4.1` mô tả những hoạt động yêu cầu init class/interface, ví dụ:

| Thao tác | Có yêu cầu initialization của class khi cần? | Ghi chú |
| --- | --- | --- |
| `new Broken()` | Có | Class được initialize trước khi instance construction hoàn tất |
| Đọc static field **không phải constant variable** (`Broken.number`) | Có | Demo sử dụng cách này |
| Ghi static field (`Broken.number = 5`) | Có | Nếu thao tác thực sự reference field của class |
| Gọi static method (`Broken.run()`) | Có | Active use |
| `Class.forName("demo.Broken")` | Có | Overload một tham số yêu cầu init |
| `Class.forName("demo.Broken", true, loader)` | Có | Loader chỉ định tường minh |
| `Class.forName("demo.Broken", false, loader)` | Không yêu cầu init ngay | Có thể load/link, chưa chạy static initializer |
| `loader.loadClass("demo.Broken")` | Không yêu cầu init ngay | Loader sẽ tìm `Class<?>`, không mặc nhiên chạy `<clinit>` |
| `Broken.class` | Không tự yêu cầu init | Vì vậy dòng đầu Lab B in trước static block |
| Đọc constant variable `static final int LIMIT = 5` | Thường **không** gây init class khai báo constant | Compiler có thể inline compile-time constant |
| Reflective operations cụ thể kích hoạt initialization | Tùy API | Đọc JavaDoc của method, đừng suy toàn bộ reflection đều giống nhau |

Một ví dụ kiểm tra laziness:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("demo.Broken", false, loader);
System.out.println("loaded class=" + type.getName());

// Tới đây chưa yêu cầu Broken.<clinit> phải chạy.
// Nếu gọi với initialize=true từ đây, có thể ném
// ExceptionInInitializerError khi property lab.fail=true.
```

Đây là **đoạn minh họa trong method xử lý `ClassNotFoundException`**. Không dùng nó như một file độc lập; các labs ở trên đã có file đầy đủ và stdout kiểm chứng.

### Không nhầm load, resolve và initialize

- `loadClass`: tìm class, có thể delegate parent; kết quả `Class<?>` không có nghĩa initializer đã chạy.
- `resolveClass`: dùng cho linking theo ClassLoader API; không đồng nghĩa static initialization.
- `initialize=true` trong `Class.forName`: yêu cầu class initialization khi cần.
- `new`: yêu cầu init class trước khi khởi tạo instance phù hợp.

Một class có thể **load được** nhưng không **initialize được**. Đây chính là Lab B.

## 9. Chính xác JVM làm gì khi static initializer ném lỗi?

Theo JLS 17 `12.4.2, với một class `C`:

1. JVM đồng bộ quanh **initialization lock** liên quan đến `C`.
2. Nếu `C` đã initialized, return thành công.
3. Nếu `C` đang initialized bởi thread khác, thread hiện tại có thể phải chờ.
4. Nếu `C` đã ở trạng thái **erroneous**, JVM **ném `NoClassDefFoundError`** thay vì cố init lại.
5. Nếu chưa, JVM chuẩn bị thực hiện superclass/superinterfaces initialization cần thiết.
6. JVM chạy static fields/static blocks của `C` theo thứ tự văn bản tương ứng.
7. Nếu hoàn thành bình thường, đánh dấu class **fully initialized**.
8. Nếu initializer kết thúc bất thường, đánh dấu class **erroneous**, đánh thức threads chờ và phát lỗi phù hợp.

### Tại sao lần đầu có ExceptionInInitializerError?

Khi initializer ném một `Throwable E`:

- Nếu `E` **không** phải `Error` hoặc subclass của `Error`, JVM bọc E trong một `ExceptionInInitializerError` khi đủ điều kiện theo quy trình `12.4.2`.
- Nếu `E` **đã là Error**, JVM có thể phát chính Error đó ở lần thất bại đầu tiên, **không bắt buộc bọc thành `ExceptionInInitializerError`**.
- Khi class đã erroneous, những lần yêu cầu init tiếp theo dẫn tới `NoClassDefFoundError`.

Vì vậy câu “lần đầu lỗi static initializer **luôn** là `ExceptionInInitializerError`” là **sai**. Demo dùng `IllegalStateException` để có trường hợp rõ, dễ học.

### Nếu nhiều threads cùng active-use class thì sao?

Initialization được JVM điều phối và đồng bộ theo class; không phải hai threads có quyền đồng thời chạy cùng một `<clinit>` độc lập. Nếu một thread đang initialize class, thread khác có thể chờ. Nếu init thất bại, các threads tới sau có thể thấy class erroneous và `NoClassDefFoundError`.

**Không viết ứng dụng retry `Broken.number` trong loop nhiều lần với hy vọng class tự khởi tạo lại.** Nếu trạng thái đã erroneous, retry cùng runtime class không khắc phục nguyên nhân.

## 10. Constructor exception khác class initializer exception

Ví dụ một constructor ném lỗi:

```java
public final class FailingObject {
    public FailingObject() {
        throw new IllegalStateException("constructor failed");
    }
}
```

Đây là class Java có thể biên dịch nhưng **không chứa method `main`**. Nếu class initialization của `FailingObject` bình thường, việc constructor của **một object** ném `IllegalStateException` **không tự đánh dấu cả class erroneous**.

Cần phân biệt:

- `static { throw ... }` / static field initializer hỏng → lỗi **class initialization** (có thể đánh dấu erroneous).
- Instance field initializer hay constructor hỏng → lỗi **instance construction**; không mặc nhiên làm class erroneous.
- Superclass static initializer hỏng → class đang khởi tạo có thể bị ảnh hưởng theo quy trình init hierarchy.
- Method bình thường ném exception → không tự làm class erroneous.

Không chỉ nhìn “stack trace xảy ra khi `new Broken()`” mà kết luận lỗi constructor. `new` có thể kích hoạt class initialization **trước** khi constructor chạy.

## 11. Tại sao đổi property giữa chừng không sửa được class erroneous?

Trong Lab B, `lab.fail` được đọc trong `<clinit>`. Giả sử trong cùng JVM ta chạy:

```java
try {
    int ignored = Broken.number;
} catch (LinkageError error) {
    System.setProperty("lab.fail", "false");
}

int value = Broken.number; // Vẫn có thể ném NoClassDefFoundError.
```

Đây là **đoạn minh họa trong class `demo` đã import/nhìn thấy `Broken`**, không phải file chạy độc lập. Property đã sửa nhưng **quá trình static initialization của cùng `Class<?>` không tự chạy lại**.

Các cách xử lý phù hợp:

- **Ứng dụng thường:** sửa cấu hình/dependency/initializer rồi khởi động lại JVM.
- **Plugin có loader riêng:** dừng plugin, cleanup tất cả listeners/threads/TCCL/instances, sửa artifact hoặc cấu hình, tạo **class loader mới** để có runtime class definition mới, rồi khởi tạo lại theo lifecycle đúng.
- **Không thể:** gọi `Class.forName` nhiều lần và mong một `Class<?>` erroneous tự reset.
- **Không nên:** cố gọi `System.gc()` hay `URLClassLoader.close()` rồi dùng lại class trong **cùng loader đã define**. Close không sửa class initialization state.

Tạo loader mới **không bảo đảm** thành công nếu nguyên nhân vẫn còn (ví dụ DB config, secret thiếu, native library lỗi); nó chỉ tạo cơ hội cho một định nghĩa class mới được initialize với trạng thái phù hợp.

## 12. Thực hành phân biệt ClassNotFoundException với NoClassDefFoundError

Một câu hỏi phổ biến: “Tại sao dùng `Class.forName` ra `ClassNotFoundException`, nhưng gọi method lại ra `NoClassDefFoundError`?”

Xét:

```java
Class.forName("lib.Helper");
```

Đây là **đoạn minh họa** trong method khai báo/handle `ClassNotFoundException`. Vì API được yêu cầu tìm class bằng **chuỗi tên**, nếu loader không thấy class, nó thường ném **checked `ClassNotFoundException`** trực tiếp.

Ngược lại:

```java
System.out.println(lib.Helper.message());
```

Đây là **đoạn minh họa**, giả định caller đã compile against `lib.Helper`. JVM resolve symbolic reference trong bytecode để thực hiện call; nếu class definition thiếu, VM có thể ném **`NoClassDefFoundError`**.

Hình dung:

```text
API lookup theo tên:
    Class.forName("lib.Helper")
          |
          +-- loader không tìm thấy
          |
          +-- ClassNotFoundException (checked)

Bytecode reference:
    invokestatic lib/Helper.message:()Ljava/lang/String;
          |
          +-- JVM cần class khi linking
          +-- không tìm được definition
          |
          +-- NoClassDefFoundError (LinkageError)
              [cause có thể là ClassNotFoundException]
```

**Cả hai vẫn có thể bắt nguồn từ classpath sai**, nhưng loại throwable phụ thuộc **đường gọi/API** và **điểm JVM đang tìm/resolve**. Đừng coi hai exception/error là synonym.

## 13. Classpath root: sửa đúng lỗi của Lab A

Trong Lab A, file đúng ở:

```text
lib-classes/
└── lib/
    └── Helper.class
```

Với binary name `lib.Helper`, **classpath root phải là thư mục `lib-classes`**, không phải `lib-classes/lib`. JVM dùng package path `lib/Helper.class` tương đối từ từng root.

**Sai:**

```bash
java -cp lib-classes/lib app.MissingDemo
```

Lệnh trên còn thiếu output của `app.MissingDemo`; ngay cả nếu thêm app root, `lib-classes/lib` vẫn **không phải root đúng** cho `lib.Helper`.

**Đúng với hai directories:**

```bash
# Linux/macOS
java -cp "app-classes:lib-classes" app.MissingDemo
```

```powershell
# Windows PowerShell
java -cp 'app-classes;lib-classes' app.MissingDemo
```

Nếu dependency nằm trong JAR, phải để root archive có entry `lib/Helper.class` và đưa JAR vào runtime classpath thích hợp:

```bash
jar --create --file helper.jar -C lib-classes .
```

Sau đó ví dụ trên Linux/macOS:

```bash
java -cp "app-classes:helper.jar" app.MissingDemo
```

Windows thay `:` bằng `;`.

**Mẹo:** thêm JAR/đường dẫn vào **compile classpath** không tự thêm vào **runtime classpath**. Tương tự, IDE thấy dependency không chứng minh script/Docker/server/plugin loader khi chạy sẽ nhìn thấy dependency ấy.

## 14. Khi class thực sự có mặt nhưng JVM vẫn báo NoClassDefFoundError

Ngoài static initialization failure, một số nguyên nhân khác cần kiểm tra:

| Tình huống | Cơ chế | Hướng chẩn đoán |
| --- | --- | --- |
| File `Helper.class` có trên đĩa nhưng đặt sai **classpath root** | Loader không tìm theo đúng binary name path | So package với output root |
| JAR có class nhưng không nằm trong runtime `-cp` | Compilation và deployment không đồng bộ | In runtime classpath và JAR list |
| Plugin class chỉ có trong loader con | Parent loader không tự tìm xuống child | Kiểm tra defining/initiating loader, TCCL nếu API dùng TCCL |
| JAR có trên module path nhưng module chưa resolved | Observable không đồng nghĩa resolved | Kiểm tra `--module-path`, `--add-modules` và JPMS dependency graph |
| Class phụ thuộc vào **một dependency khác** bị thiếu | Class đầu có thể load, đến linkage mới thiếu class phụ | Đọc **tên class trong message/cause** và stack trace |
| Class đã erroneous do lỗi static block | Subsequent active use ném NCDFE dù `.class` tồn tại | Tìm `ExceptionInInitializerError` / original initializer error trước đó |
| Đổi binary name/package nhưng còn file cũ | Bytecode caller yêu cầu tên khác | `javap`, kiểm tra binary name và build artifacts |
| JAR/class files cũ bị shadow bởi parent-loader version | JVM nạp API khác với artifact đang xem | `Class.getClassLoader()`, CodeSource, `-Xlog:class+load=info` |
| Code được biên dịch với API version không còn tương thích | Member reference hỏng | Có thể là `NoSuchMethodError` / `NoSuchFieldError`, không nhất thiết NCDFE |
| Class file hỏng hoặc version không hỗ trợ | Verification/format/version lỗi | `ClassFormatError` / `UnsupportedClassVersionError` có thể xuất hiện |

Không sửa bằng cách thêm hàng loạt JAR ngẫu nhiên. Cần xác định **tên class cần resolve** và **loader đang thực hiện lookup**.

## 15. Chẩn đoán bằng javap, CodeSource, class loading logs

### 15.1 Xem tham chiếu bytecode

Lab A:

```bash
javap -classpath app-classes -c -verbose app.MissingDemo
```

Tìm `lib/Helper` và `invokestatic`. Thao tác xác nhận caller binary **thật sự phụ thuộc** `lib.Helper`, dù source hiện tại có thể đã thay đổi.

### 15.2 Xác nhận runtime class có thể được loader nào tìm

Một helper minh họa:

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL=" + loader);
System.out.println("resource=" +
        loader.getResource("lib/Helper.class"));
```

Đây là **đoạn minh họa trong method**, giả định TCCL khác null. Resource URL khác null **chỉ chứng minh loader có thể tìm resource đó**, không đủ để kết luận class sẽ verify/link/init thành công; module access và class loading policy có thể khác đường resource lookup.

Nếu class được load thành công, kiểm tra:

```java
Class<?> type = lib.Helper.class;
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource cs =
        (pd == null ? null : pd.getCodeSource());

System.out.println("source="
        + (cs == null ? "<unknown>" : cs.getLocation()));
```

Đây là **đoạn minh họa**, giả định code đã compile có `lib.Helper`. CodeSource có thể null; với loader riêng, source có thể khác runtime classpath mà host in ra. Không dùng đoạn này khi class chưa load được rồi bỏ qua lỗi gốc; khi đó log class loading/deployment paths hữu ích hơn.

### 15.3 HotSpot class load logs

```bash
java -Xlog:class+load=info -cp "app-classes:lib-classes" app.MissingDemo
```

Dòng trên dành Linux/macOS; trên Windows thay `:` bằng `;`. HotSpot có thể in nhiều sự kiện load, giúp xác định class nào được nạp và nguồn nếu thông tin log có. Nhưng log `class+load` không tự chỉ ra **giá trị bên trong static initializer** gây lỗi. Với Lab B, stack trace tới `demo.Broken.<clinit>` và cause `IllegalStateException` quan trọng hơn.

### 15.4 Đừng dùng mọi log sau lỗi làm nguyên nhân

Trong server, một lỗi init duy nhất lúc startup có thể khiến **hàng trăm requests về sau** log `NoClassDefFoundError: Could not initialize class ...`. Nếu chỉ đọc log ở request thứ 100, bạn thấy hậu quả. Hãy tìm **lần đầu** static initializer chạy và exception thật từ config, resource, network, null value hoặc service discovery.

Đôi khi lớp static initializer gọi tới lớp khác mà lớp ấy khởi tạo lỗi. Khi đó cause chain có nhiều class; cần lần theo tới đoạn `<clinit>` và exception ban đầu.

## 16. Lỗi static initialization thực tế đến từ đâu?

Trong thí nghiệm ta chủ động ném `IllegalStateException("boom")`. Trong ứng dụng thật, static initializer có thể hỏng bởi:

- `NullPointerException` khi đọc config chưa được thiết lập.
- `IllegalArgumentException` từ việc parse path/URL/charset/timezone không hợp lệ.
- `ExceptionInInitializerError` từ một dependency có static initialization bị lỗi trước.
- `SecurityException` hoặc `IllegalAccessError` khi thao tác bị runtime/module access hạn chế.
- `UnsatisfiedLinkError` lúc load native library trong static block.
- `ServiceConfigurationError` khi initializer dùng `ServiceLoader` với provider metadata hỏng.
- `NoClassDefFoundError` do dependency khác thiếu đúng lúc initializer gọi đến.
- `OutOfMemoryError` hoặc tài nguyên hệ thống không đủ.
- Thứ tự static initialization giữa nhiều classes dẫn tới trạng thái chưa sẵn sàng hoặc chu trình phụ thuộc phức tạp.

Vì vậy một class initialization failure **không nhất thiết bắt đầu bằng `IllegalStateException`**. Lab B chỉ chọn lỗi này để minh họa rõ quy tắc wrapping.

**Thiết kế tốt:** hạn chế I/O, network, database, native load hoặc service discovery có thể fail trong static initializer nếu chúng phụ thuộc trạng thái vận hành thay đổi. Ưu tiên một **explicit initialization method**, factory hoặc lifecycle `start()` trả lỗi có kiểm soát và hỗ trợ retry/rollback ở mức ứng dụng.

### Ví dụ anti-pattern

```java
public final class GlobalClient {
    static final Connection CONNECTION = openDatabaseOrThrow();

    private GlobalClient() { }

    static Connection connection() {
        return CONNECTION;
    }

    // openDatabaseOrThrow và Connection là thành phần minh họa.
}
```

Đây là **pseudocode**, không phải file độc lập: `Connection`/`openDatabaseOrThrow` chưa khai báo. Nếu cơ sở dữ liệu chưa sẵn sàng lúc class initialization, class có thể rơi vào trạng thái erroneous vĩnh viễn trong runtime class đó. Thay bằng explicit lifecycle/DI/resource management sẽ giúp thông báo lỗi và retry theo chính sách ứng dụng.

## 17. Kết quả khác nhau giữa class literal, static field và static constant

Một thí nghiệm phụ cần hiểu:

```java
package demo;

public class ConstantExample {
    public static final int LIMIT = 10;
    public static int dynamicValue = init();

    private static int init() {
        System.out.println("initializing ConstantExample");
        return 20;
    }
}
```

Đây là **class độc lập có thể biên dịch**, chưa có `main`.

Khi mã khách compile cùng API truy cập `ConstantExample.LIMIT`, compiler có thể **inline** số `10`. Việc chỉ đọc constant variable ấy **không buộc class init**. Nhưng đọc `dynamicValue` sẽ kích hoạt initialization và có thể in `initializing ConstantExample`.

Đừng sử dụng `static final int` compile-time constant làm trigger khi muốn kiểm tra `<clinit>`. Trong Lab B, ta dùng **`public static int number`**, đảm bảo thao tác đọc là active use.

Cũng không suy rằng tất cả `static final` đều là compile-time constant: `static final Object X = new Object()` không phải constant variable theo nghĩa JLS.

## 18. Quan hệ lỗi khởi tạo với classloader và hot reload

Theo JVMS, runtime class identity bao gồm **binary name và defining class loader**. Hai custom classloader khác nhau có thể tự define hai bản `demo.Broken` cùng tên.

```text
OldPluginLoader
    |
    +-- demo.Broken (class definition A)
           +-- initialization failed
           +-- state: ERRONEOUS

NewPluginLoader
    |
    +-- demo.Broken (class definition B)
           +-- independent class initialization state
           +-- may succeed after config fix
```

Đây là sơ đồ khái niệm, không phải API VM để trực tiếp đọc `ERRONEOUS`. Một new loader **chỉ tạo một cơ hội mới** nếu nó thật sự define class mới, thay vì delegate về bản class lỗi ở parent loader.

Trong plugin host:

1. **Shared API** ở parent loader để host/plugin thống nhất interface identity.
2. **Plugin implementation** được custom loader riêng định nghĩa.
3. Nếu implementation class erroneous, stop/cleanup plugin theo lifecycle.
4. Tránh host static caches, TCCL, threads, listeners giữ class/loader cũ khi undeploy.
5. Tạo loader mới trỏ tới artifact/config đã sửa và reinitialize plugin.
6. Kiểm tra new loader thực sự define `demo.Broken`; nếu parent đã define class cùng tên, delegation có thể vẫn trả definition cũ.
7. Không coi `URLClassLoader.close()` là “reset class initialization”; close chỉ quản lý URL search path/JAR handles.

**Không cố chữa lỗi initialization bằng reflection vào private fields hoặc `Unsafe` để ép class chạy `<clinit>` lại.** Không có hợp đồng Java SE công khai đảm bảo thao tác như vậy là an toàn/đúng semantics.

## 19. Module path và vấn đề “class có trên đĩa nhưng không load được”

Từ Java 9, code có thể nằm trên classpath (unnamed module) hoặc module path (named/automatic module). Một JAR có mặt trên `--module-path` chỉ khiến nó **observable**; module còn phải được **resolved** theo graph và class access còn chịu exports/opens/readability.

Ví dụ một ứng dụng classpath cố dùng class trong named module chưa resolved có thể cần `--add-modules module.name` hoặc quan hệ dependency thích hợp. Tuy nhiên **không lấy `--add-modules` làm giải pháp chung cho mọi NoClassDefFoundError**. Hãy xác định class được nạp bởi loader nào, module nào chứa class, module graph có resolved không, và root cause có thực sự do discovery hay là erroneous initialization.

Với Lab A/B trong bài, **chỉ dùng classpath** và không có `module-info.java`, nên dễ tách hai vấn đề gốc mà không trộn thêm JPMS resolution.

## 20. Các bài kiểm thử bổ sung nên thử

### Bài tập 1 — Xóa app class thay vì lib class

Giữ `lib-classes` nhưng chạy:

```bash
java -cp lib-classes app.MissingDemo
```

Launcher sẽ **không tìm được main class `app.MissingDemo`**. Thông báo launcher như “Could not find or load main class ...” khác với trường hợp main đã chạy rồi JVM thiếu class `lib.Helper`. Đừng khẳng định mọi kiểu main startup failure đều phải mang cùng throwable như Lab A.

### Bài tập 2 — Sửa runtime classpath của Lab A

Thêm lại `lib-classes` mà **không biên dịch lại client**. Kết quả đã kiểm chứng là `app started` rồi `Helper available`. Vì lỗi gốc là deployment path, không phải source API.

### Bài tập 3 — Đổi giá trị property của Lab B trước startup

Chạy:

```bash
java -Dlab.fail=false -cp init-classes demo.InitDemo
```

Dự đoán kết quả trước khi xem: static block chạy **một lần**, cả hai lần đọc static field đều in `42`. Đây là trường hợp đối chứng đã được chạy kiểm chứng.

### Bài tập 4 — Đổi property sau lỗi đầu trong cùng JVM

Sửa `InitDemo` để trong `catch` đầu tiên gọi `System.setProperty("lab.fail", "false")` rồi thử đọc `Broken.number` lần nữa. Theo JLS, vẫn không tự reinitialize class definition erroneous. Hãy so với khởi động JVM mới và giải thích sự khác nhau.

### Bài tập 5 — Thay IllegalStateException bằng Error

Trong `Broken`, thay lời ném trong static initializer bằng `throw new AssertionError("boom");` trong một nhánh runtime. Dự đoán:

- Lần đầu initializer kết thúc với một subclass của `Error`, có thể chính `AssertionError` được phát, không nhất thiết có `ExceptionInInitializerError`.
- Lần active use tiếp theo của class erroneous dẫn tới `NoClassDefFoundError`.

**Đây là bài tập dự đoán theo JLS**, không phải stdout của hai labs đã chạy. Khi viết code để quan sát, `catch (LinkageError)` của `InitDemo` không bắt `AssertionError` vì `AssertionError` là nhánh `Error` khác; nếu muốn trình diễn, dùng một harness có `catch (Throwable)` chỉ trong lab và tuyệt đối không che lỗi tương tự trong production.

### Bài tập 6 — Constructor lỗi không làm class erroneous

Tạo một class có constructor ném `IllegalArgumentException`. Hai lần gọi constructor đều có thể ném exception từ constructor mới; static initialization của class vẫn có thể đã thành công. So với Lab B để hiểu trạng thái per-class khác per-instance.

### Bài tập 7 — Xem lần lỗi đầu tiên trong log nhiều threads

Chạy nhiều threads cùng active-use một class có static block ngủ ngắn rồi ném lỗi. Tránh viết tests phụ thuộc thứ tự scheduling; điều cần quan sát là **một initialization attempt** được đồng bộ ở cấp class, và các callers về sau thấy erroneous state. Đọc JLS `12.4.2` để hiểu lock/wait rules.

## 21. Bảng chẩn đoán nhanh khi triển khai thực tế

| Triệu chứng | Câu hỏi trước tiên | Hướng sửa |
| --- | --- | --- |
| `NoClassDefFoundError: pkg/Type`, cause `ClassNotFoundException` | JAR/runtime root có đúng không? Loader thấy class đó không? | Sửa runtime classpath/module path/delegation |
| `NoClassDefFoundError: Could not initialize class pkg.Type` | Lần init đầu đã lỗi gì? Có `<clinit>` frame không? | Sửa static initializer/config, tạo init mới hợp lệ |
| `ExceptionInInitializerError` | Static field/block nào ném exception gốc? | Đọc `getCause()` và stack trace, sửa nguyên nhân |
| `ClassNotFoundException` từ `Class.forName` | Name/loader được truyền có đúng không? | Chọn loader phù hợp, xác minh binary name |
| `NoSuchMethodError` | Caller compile với API nào, runtime nạp API nào? | Binary compatibility/version alignment |
| `NoSuchFieldError` | Field name + descriptor còn không? | So `javap` caller/runtime |
| `UnsupportedClassVersionError` | Bytecode được compile cho JDK cao hơn runtime? | Chọn JDK/build target phù hợp |
| `IllegalAccessError` | Member tồn tại nhưng access/module exports có phù hợp? | Sửa access/module graph, không chỉ thêm classpath |
| `UnsatisfiedLinkError` trong `<clinit>` | Native library/ABI/path và loader ownership? | Sửa native dependency, xem lỗi đầu tiên |
| Lỗi chỉ xảy ra trong plugin | Plugin dùng parent/child loader nào? API shared version nào? | Kiểm tra loader identity, artifact, lifecycle |
| Lỗi mất sau restart nhưng tái diễn khi startup config sai | Static initializer chạy sớm trước config | Sắp xếp init/config hoặc chuyển sang explicit lifecycle |
| Rất nhiều NCDFE cùng class sau một lỗi EIIE | Class đã erroneous; requests sau cùng chịu hậu quả | Tìm exception đầu tiên, sửa root cause rồi restart/redeploy |

## 22. Checklist chẩn đoán theo thứ tự

1. **Ghi nguyên throwable và cause chain.** Không chỉ chép dòng `NoClassDefFoundError`.
2. **Xác định tên class được yêu cầu.** `lib/Helper`, `demo.Broken`, hay dependency khác ở cause?
3. **Hỏi main class đã chạy chưa.** Launcher không tìm main class khác với JVM thiếu dependency ở một code path.
4. **Kiểm tra class có trên runtime output/JAR không.** `jar --list` và filesystem path.
5. **So compile và runtime classpath.** `javac -cp` không tự truyền cho `java -cp`.
6. **Xác định classpath root từ package.** `lib.Helper` cần entry `lib/Helper.class` tương đối root.
7. **Xác định loader cụ thể.** App loader, plugin loader, TCCL của API nào, JPMS layer nào?
8. **Xác minh code source và duplicate JARs** khi có nhiều versions cùng class name.
9. **Nếu thấy `<clinit>`, đọc lần lỗi đầu tiên.** `NullPointerException`, config, native, SPI, missing dependency?
10. **Nếu class erroneous, không retry cùng class vô hạn.** Sửa root cause và dùng JVM/class definition mới phù hợp.
11. **Nếu là plugin, stop và cleanup trước reload.** Không giữ TCCL/tasks/cache trỏ tới loader cũ.
12. **Dùng `javap` để xem bytecode references**, nhất là khi source đang khác artifact.
13. **Chạy lại hai đối chứng.** Đầy đủ vs thiếu dependency; initializer fail vs initializer success.
14. **Thêm integration test dùng runtime artifact thật**, không chỉ dựa vào IDE/test compile.
15. **Quan sát logs từ startup**, không chỉ lỗi thứ N sau khi service đã chạy lâu.

## 23. Câu hỏi tự kiểm tra có đáp án

**1.** Tại sao Lab A compile được nhưng runtime vẫn lỗi?

**Đáp án:** `javac` thấy `lib.Helper` từ `lib-classes` lúc compile, nhưng `java -cp app-classes` không thấy dependency khi symbolic reference cần được resolve.

**2.** Trong Lab A, vì sao in `app started` trước khi báo lỗi?

**Đáp án:** JVM đã nạp/chạy được main class; lỗi chỉ xuất hiện khi code path thực sự gọi `Helper.message()` và cần `lib.Helper`.

**3.** Tại sao Lab B cho kết quả `ExceptionInInitializerError` rồi `NoClassDefFoundError`?

**Đáp án:** Lần đầu `Broken.number` kích hoạt static initializer ném `IllegalStateException` (được JVM bọc EIIE). Class chuyển sang erroneous; lần sau JLS quy định không retry, ném NCDFE.

**4.** Vì sao `Broken.class.getName()` không in `<clinit> entered`?

**Đáp án:** Class literal không tự yêu cầu class initialization. `Broken.number` là active use thực sự.

**5.** Có thể sửa `System.setProperty("lab.fail","false")` sau EIIE rồi đọc `Broken.number` lại thành công trong cùng definition không?

**Đáp án:** Không theo JLS cho class đã erroneous; phải sửa nguyên nhân và tạo runtime class definition mới/khởi động lại theo cách phù hợp.

**6.** `ClassNotFoundException` và `NoClassDefFoundError` khác cấp bậc như thế nào?

**Đáp án:** CNFE là checked `Exception`; NCDFE là `LinkageError`. Chúng xuất hiện ở API/đường resolution khác nhau dù có thể cùng do class missing.

**7.** Nếu static initializer ném trực tiếp `AssertionError`, lần đầu có luôn EIIE không?

**Đáp án:** Không. EIIE wrapping áp dụng khi thrown E không phải Error/subclass; `AssertionError` có thể được phát trực tiếp.

**8.** Nếu chỉ constructor ném exception, class có tự erroneous không?

**Đáp án:** Không mặc nhiên. Constructor error là lỗi instance construction; class initialization có thể đã hoàn thành.

**9.** `NoClassDefFoundError: Could not initialize class ...` có nghĩa JVM không đọc được file class không?

**Đáp án:** Không nhất thiết; thường class đã được tìm/nạp nhưng init thất bại trước đó. Cần tìm lỗi `<clinit>` đầu.

**10.** Vì sao đổi plugin JAR trong cùng class loader có thể không sửa lỗi initialization?

**Đáp án:** Runtime class definition đã được định nghĩa và đánh dấu erroneous; loader không tự định nghĩa lại class cùng tên. Cần deployment/loader mới cùng cleanup và root-cause fix.

**11.** Vì sao không nên đặt network connection setup trong static initializer?

**Đáp án:** Lỗi tạm thời lúc startup có thể biến class thành erroneous, không có retry tự động như một service lifecycle; quản lý explicit init/close dễ kiểm soát hơn.

**12.** Nếu source hiện tại không còn import `lib.Helper` nhưng bytecode deployed vẫn tham chiếu, cần xem gì?

**Đáp án:** `javap -c -verbose` trên **caller.class deployed** và build artifacts; source IDE không phải bằng chứng bytecode đang chạy.

## Kết luận

**`NoClassDefFoundError` không đồng nghĩa duy nhất “thiếu `.class` trên đĩa”.** Nó có thể xuất hiện khi JVM không tìm được class cần link (**Lab A**), hoặc khi JVM yêu cầu initialize lại một class đã thất bại và đang ở trạng thái **erroneous** (**Lab B**).

Cách xử lý đúng phải dựa trên **lần lỗi đầu + cause + bước JVM đang thực hiện**:

- **Thiếu class lúc chạy:** sửa runtime dependency/classpath/module/loader visibility.
- **Static initializer thất bại:** sửa root cause trong `<clinit>`/config, rồi dùng lần khởi tạo hợp lệ với JVM/class definition mới; không retry cùng class erroneous vô hạn.
- **Lỗi API version/access khác:** đối chiếu đúng throwable, bytecode và defining loader trước khi sửa.

Khi thực hành, hãy giữ **hai đối chứng chạy được**: một runtime có/không có dependency, và một JVM có/không có property gây initializer failure. Kết hợp chúng với JLS `12.4.2` sẽ giúp đọc chính xác những lỗi `NoClassDefFoundError` khó nhất trong server và plugin systems.

**Tài liệu chính thức Java SE 17:**

- [`NoClassDefFoundError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html) — class definition không còn được tìm thấy khi JVM/loader cần.
- [`ClassNotFoundException` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html) — checked exception khi tìm class bằng tên.
- [`ExceptionInInitializerError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html) — lỗi xảy ra trong static initializer.
- [JLS 17 §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1) — các trường hợp active use.
- [JLS 17 §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2) — trạng thái initialized/erroneous, EIIE wrapping và subsequent NCDFE.
- [JVMS 17 §5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — symbolic resolution và class loading.
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass` và delegation.
