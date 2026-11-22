# Static initializer và vòng lặp phụ thuộc khởi tạo trong Java 15+

## 1. Mục tiêu và phạm vi

Khi một chương trình Java tải các lớp mới hoặc **sinh class file tại runtime**, chúng ta cần phân biệt rõ việc **định nghĩa lớp (define)**, **liên kết (link)** và **khởi tạo (initialize)**. Một lớp đã được JVM biết đến **chưa chắc đã chạy `static { ... }`**. Việc gọi các trường/phương thức static có thể kích hoạt class initialization; nếu initializer của A lại dùng B và initializer của B lại dùng A, ta có **vòng lặp phụ thuộc khởi tạo (circular initialization dependency)**.

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` bổ sung một tình huống thực tế: framework có thể tạo nhiều **hidden classes** từ class-file bytes và lựa chọn khởi tạo ngay hay để tới lần dùng đầu tiên. Vì vậy, bài học kết hợp **quy tắc Java Language Specification hiện hành** với API **hidden class** chính thức của Java 15+.

Sau bài này, bạn có thể:

1. Phân biệt **loading / linking / preparation / initialization** và thứ tự chạy static field initializer, static block.
2. Biết lúc nào `<clinit>` được kích hoạt, lúc nào `SomeClass.class` hoặc đọc `.class` **không** chạy static initializer.
3. Giải thích một vòng A → B → A trong **cùng thread** vì sao có thể đọc **giá trị mặc định** thay vì gây đệ quy vô hạn.
4. Nhận biết tình huống **deadlock giữa nhiều thread** khi chúng đang khởi tạo những lớp phụ thuộc chéo.
5. Dùng `defineHiddenClass(bytes, true/false)`, `Lookup.ensureInitialized(Class<?>)` và `MethodHandle` đúng cách.
6. Xử lý `ExceptionInInitializerError` / `NoClassDefFoundError` và thiết kế sinh mã tránh initialization cycle.

Bài chỉ dùng cơ chế Java vẫn được hỗ trợ. Không dùng `Unsafe.defineAnonymousClass` hay các API nội bộ, không cần preview và không yêu cầu triển khai ứng dụng mới trên runtime Java 15 đã hết vòng đời hỗ trợ.

## 2. Bốn giai đoạn của vòng đời lớp

### 2.1. Loading — JVM tìm hoặc nhận định nghĩa lớp

Một lớp thông thường có thể được class loader nạp từ `.class`/JAR. Với hidden class, `MethodHandles.Lookup.defineHiddenClass` nhận **mảng byte `ClassFile` hợp lệ** và nhờ JVM định nghĩa một lớp không có binary name tra cứu như lớp thường.

**Loading hoặc định nghĩa chưa đồng nghĩa với chạy code trong static initializer.** Việc đọc resource bằng `Class.getResourceAsStream(...)` chỉ lấy bytes, bản thân thao tác đọc **không** thực thi `<clinit>` của lớp nằm trong resource.

### 2.2. Linking — verification, preparation và resolution

Trước khi một lớp được sử dụng, JVM phải kiểm tra và chuẩn bị cấu trúc của lớp:

- **Verification:** xác minh tính hợp lệ của class file/bytecode theo quy tắc JVM.
- **Preparation:** cấp trạng thái cho các trường static và gán **giá trị mặc định** ban đầu: `0` cho `int`, `false` cho `boolean`, `null` cho biến tham chiếu. Các constant variables có quy tắc xử lý riêng.
- **Resolution:** phân giải các symbolic references tới class/field/method khác; một số bước phân giải có thể thực hiện một cách **lười** khi thực sự cần.

Sự thật quan trọng nhất của bài: **giá trị mặc định tồn tại trước khi initializer gán giá trị bạn viết trong source**. Với `static int x = compute();`, `x` ban đầu có thể ở trạng thái `0` trong quá trình preparation; giá trị trả từ `compute()` chỉ được gán khi initialization chạy đến khai báo đó.

### 2.3. Initialization — thực thi `<clinit>`

Java compiler tổng hợp phần khởi tạo static thành công việc tương đương một phương thức JVM đặc biệt tên `<clinit>`. Nó gồm những biểu thức khởi tạo trường static và các block `static { ... }` được sắp xếp theo **thứ tự xuất hiện trong source**.

```java
class Registry {
    static int first = init("first", 1);
    static {
        System.out.println("block");
    }
    static int second = init("second", first + 1);

    static int init(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }
}
```

Đây là **lớp minh họa**, chưa có `main`. Khi một thao tác hợp lệ kích hoạt `Registry` initialization, thứ tự in là:

```text
first=1
block
second=2
```

Không diễn giải việc class loader đọc file `Registry.class` là chắc chắn sẽ in các dòng trên. Phải có **điều kiện kích hoạt khởi tạo**.

### 2.4. Khởi tạo class chỉ một lần cho một identity

Trong trạng thái bình thường, mỗi **class identity trên JVM** được khởi tạo thành công **một lần**, không phải một lần trên mỗi biến tham chiếu hay mỗi method call. Class identity phụ thuộc cách định nghĩa lớp/loader; hai hidden classes được định nghĩa **hai lần từ cùng bytes** vẫn là **hai class khác nhau**, mỗi lớp có static state và initialization riêng.

Khi initializer hoàn thành, các thread khác có thể tiếp tục sử dụng class đã khởi tạo. Nếu initializer thất bại, class identity ấy chuyển sang trạng thái **erroneous**, không được tự thử lại `<clinit>` ở lần truy cập kế tiếp.

## 3. Khi nào Java thực sự chạy static initializer?

Theo JLS `12.4.1`, những tác vụ thường kích hoạt initialization của lớp liên quan gồm:

| Thao tác | Có thể kích hoạt khởi tạo? | Ghi chú |
| --- | --- | --- |
| `new SomeClass()` | **Có** | Class cần được khởi tạo trước khi tạo instance |
| Gọi phương thức `static` được khai báo trong class | **Có** | Ví dụ `SomeClass.run()` |
| Đọc/ghi trường `static` không phải constant variable | **Có** | Ví dụ `SomeClass.counter` |
| Đọc hằng compile-time `static final int LIMIT = 10;` | **Thông thường không** | Giá trị **constant variable** có thể được inline, không tạo active use khởi tạo lớp khai báo |
| Đánh giá `SomeClass.class` | **Không tự nó** | Lấy đối tượng `Class<?>` không tương đương khởi tạo |
| `Class.forName("pkg.SomeClass")` | **Có**, với named class và phương thức một tham số | Cách này khác việc chỉ lấy metadata |
| `Class.forName(name, false, loader)` | **Không yêu cầu khởi tạo ngay** | Áp dụng cho named class; `false` là cờ initialize |
| Đọc `SomeClass.class` như **resource bytes** | **Không tự nó** | `getResourceAsStream` chỉ đọc dữ liệu binary |
| `Lookup.defineHiddenClass(bytes, true)` | **Có** | JVM định nghĩa và khởi tạo hidden class trước khi trả về |
| `Lookup.defineHiddenClass(bytes, false)` | **Chưa khởi tạo chỉ vì lời gọi** | Class được định nghĩa, liên kết; một active use về sau vẫn khởi tạo |
| `Lookup.ensureInitialized(targetClass)` | **Có**, nếu chưa khởi tạo | API Java 15+, yêu cầu class có thể truy cập bởi Lookup |
| Gọi `MethodHandle` trỏ tới phương thức static của lớp chưa khởi tạo | **Có** | Lần invoke handle là active use; chỉ tạo handle chưa nhất thiết khởi tạo |

**Hai ngoại lệ hay gây nhầm:**

- **Hằng compile-time**: `static final int X = 7;` thường không kích hoạt initialization khi được truy cập như constant variable. Nhưng `static final int X = readConfig();` **không** là constant variable vì initializer không phải constant expression; đọc `X` sẽ kích hoạt initialization.
- **Superclass và interface**: trước khi khởi tạo một class, JVM phải khởi tạo superclass cần thiết và những superinterfaces khai báo default methods theo đặc tả, nếu chưa khởi tạo. Không suy ra việc chỉ “nhắc tới một kiểu” trong source đã làm toàn bộ kiểu liên quan chạy static block.

Không phụ thuộc vào những **side effects trong static block** khi chỉ muốn tra cứu kiểu, đọc resource hoặc kiểm tra metadata.

## 4. Vòng phụ thuộc A → B → A cùng một thread

Giả sử hai lớp phụ thuộc nhau ngay khi gán các trường static:

```java
class A {
    static int value = B.value + 1;
}

class B {
    static int value = A.value + 1;
}
```

Đây là hai **lớp minh họa**; đoạn này chưa có `main`. Nếu **A** được active-use trước, JVM có thể thực hiện quá trình sau:

1. JVM **prepare** A; `A.value` nhận giá trị mặc định `0`.
2. Bắt đầu initialize A; tới biểu thức `B.value + 1`.
3. Truy cập `B.value` làm B được initialize. Trong B, tới biểu thức `A.value + 1`.
4. JVM nhận ra **A đang được chính thread này khởi tạo**. Theo JLS `12.4.2`, yêu cầu initialize lặp lại ở cùng thread được coi hoàn tất ngay; nó **không đệ quy chạy lại toàn bộ initializer A**.
5. Do `A.value` chưa được gán giá trị từ biểu thức ở bước 2, B quan sát `A.value == 0`, tính `B.value = 1`.
6. B hoàn tất; A tiếp tục tính `A.value = 2` và hoàn tất.

Kết quả sau đó: **`A.value == 2` và `B.value == 1`**. Đây là minh chứng **khởi tạo vòng không nhất thiết gây `StackOverflowError`**. Nhưng việc đọc **giá trị mặc định của class chưa khởi tạo xong** có thể tạo kết quả sai nghiệp vụ.

Nếu **B được initialize trước**, đường đi ngược lại có thể dẫn đến **`A.value == 1`, `B.value == 2`**. Vì thế **đừng thiết kế logic dựa trên thứ tự active use ngẫu nhiên**.

**Quan trọng:** đây là trường hợp **cùng thread** và các field khác class; hạn chế **illegal forward reference** khi dùng trực tiếp trường khai báo sau trong chính class vẫn tồn tại ở compile time. Không lấy việc ví dụ biên dịch để kết luận mọi vòng tham chiếu đều an toàn.

## 5. Hai thread và nguy cơ deadlock khi khởi tạo chéo

Java đồng bộ hóa quá trình initialization của **từng class identity**. Khi class C đang được thread T1 khởi tạo, một thread T2 cần initialize C có thể phải **đợi T1 hoàn thành**.

Một kịch bản nguy hiểm của runtime code động:

| Thời điểm | Thread T1 | Thread T2 |
| --- | --- | --- |
| 1 | Bắt đầu initialize A | Bắt đầu initialize B |
| 2 | `A.<clinit>` cần sử dụng B | `B.<clinit>` cần sử dụng A |
| 3 | Đợi B hoàn tất (B do T2 khởi tạo) | Đợi A hoàn tất (A do T1 khởi tạo) |
| 4 | Không tiến được | Không tiến được |

Đây là **mô hình deadlock có thể xảy ra**, không phải output bảo đảm của một đoạn mã. Thứ tự scheduler có thể khiến một thread khởi tạo cả A và B trước, lúc đó không deadlock nhưng vẫn có thể thấy **trạng thái chưa hoàn chỉnh** như mục 4.

**Không nên viết ví dụ cố tình tạo deadlock để học bằng cách chạy trong process chính.** Khi thread bị mắc trong class initialization, việc xử lý timeout và chẩn đoán khó hơn một phương thức thông thường. Để kiểm thử sản phẩm, dùng fixture có timeout ở tiến trình tách biệt và thu thread dumps/logs theo công cụ JVM phù hợp.

### Cách ngăn từ thiết kế

- Giữ `static { ... }` **ngắn**, tránh công việc cần I/O, network, lock phức tạp hoặc start thread rồi `join()` để đợi.
- Tránh initializer của A truy cập `static` của B nếu B lại phụ thuộc A; thiết kế **dependency graph không có cycle ở giai đoạn khởi tạo**.
- Đưa việc kết nối đối tượng/đọc cấu hình/tạo generated classes sang **bootstrap method** tường minh, sau khi các class metadata đã sẵn sàng.
- Thay một global static field được khởi tạo chéo bằng **constructor injection** hoặc truyền một cấu hình immutable đã xây dựng ở bước riêng.
- Với generated bytecode, xác định thứ tự **define → link → initialize → expose** phù hợp, không để các static initializer tự chạy side effect của nhau ngoài ý muốn.

## 6. Hidden class Java 15: `initialize = true` và `false`

Chữ ký chính:

```java
MethodHandles.Lookup defined = lookup.defineHiddenClass(
        classFileBytes, false);
Class<?> hidden = defined.lookupClass();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Lookup phải có **full privilege access**, bytes phải là class file hợp lệ có internal name **cùng package** lookup class. Hidden class đã được JVM định nghĩa/liên kết khi method trả về.

### `defineHiddenClass(bytes, true)`

- Định nghĩa class từ bytes mới.
- JVM **khởi tạo class** ngay trong lời gọi.
- Nếu `<clinit>` có side effect hoặc ném lỗi, chúng xảy ra **trước khi phương thức trả về**.
- Phù hợp khi runtime cần bảo đảm mọi static state của lớp đã hoàn tất trước khi phát hành reference cho bộ phận khác.

### `defineHiddenClass(bytes, false)`

- Định nghĩa/link class, **chưa yêu cầu initialization**.
- Nếu sau đó tạo `MethodHandle` tới static method, riêng bước tra cứu handle không có nghĩa method đã được gọi; **invocation** handle mới kích hoạt class initialization khi cần.
- Nếu framework cần chủ động khởi tạo khi đã sẵn sàng, dùng `defined.ensureInitialized(hidden)` hoặc một active use thích hợp.
- **Không đồng nghĩa “vĩnh viễn bỏ qua static initializer”**. Một static method call, static field access hoặc thao tác kích hoạt khác vẫn chạy initializer theo quy tắc JVM.

### Có thể sử dụng `Lookup.ensureInitialized(Class<?>)`

Từ Java 15, `MethodHandles.Lookup.ensureInitialized(targetClass)` cho phép yêu cầu khởi tạo một class cụ thể khi `Lookup` có quyền truy cập. Nó trả về `Class<?>` sau khi class đã initialized, hoặc theo đặc tả cũng có thể trả về khi **class đang được chính thread hiện tại khởi tạo**; vì vậy đừng xem lời gọi đệ quy trong cùng `<clinit>` là hàng rào đợi “mọi field đã gán xong”.

```java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classFileBytes, false);
Class<?> hidden = hiddenLookup.lookupClass();

// Khi framework đã chuẩn bị xong dependency:
hiddenLookup.ensureInitialized(hidden);
```

Đây là đoạn minh họa, yêu cầu `lookup` và `classFileBytes` đã được tạo. Tránh gọi `ensureInitialized` trong chuỗi static initializers đang phụ thuộc chéo: nó chỉ chuyển **thời điểm** bắt đầu initialization, không tự phá được vòng phụ thuộc A ↔ B.

**Mỗi lần gọi `defineHiddenClass` tạo một class identity mới**, kể cả khi cùng `byte[]`. Hai hidden classes có static state riêng và mỗi class chạy initializer riêng. Không dùng `Class.forName` để tìm lại hidden class theo `Class.getName()`; nó không có binary name discoverable như class thường. Giữ `Lookup`, `Class<?>` hoặc `MethodHandle` cần thiết.

## 7. Ví dụ hoàn chỉnh Java 15+: vòng cùng thread, hidden class eager/lazy, lỗi khởi tạo

Ví dụ này có ba tình huống trong **một file Java**: (1) A/B dependency cycle cùng thread; (2) lấy bytes của class lồng rồi định nghĩa **hai hidden classes** từ cùng bytes, một lazy và một eager; (3) initializer ném exception để quan sát class trở thành erroneous. Không cần thư viện ngoài.

### 7.1. Tạo file `src/demo/InitializationCycleDemo.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class InitializationCycleDemo {
    static class A {
        static int value = B.value + 1;
        static {
            System.out.println("A.<clinit> value=" + value);
        }
    }

    static class B {
        static int value = A.value + 1;
        static {
            System.out.println("B.<clinit> value=" + value);
        }
    }

    static class HiddenTemplate {
        static {
            System.out.println("HiddenTemplate.<clinit>");
        }

        static int answer() {
            return 42;
        }
    }

    static class Broken {
        static final int ANSWER = compute();

        static int compute() {
            throw new IllegalStateException("bad configuration");
        }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("cycle-start");
        System.out.println("A.value=" + A.value);
        System.out.println("B.value=" + B.value);

        byte[] bytes;
        try (InputStream in = InitializationCycleDemo.class
                .getResourceAsStream(
                        "InitializationCycleDemo$HiddenTemplate.class")) {
            if (in == null) {
                throw new IOException("Missing HiddenTemplate class resource");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Define, link; do not initialize the first hidden class yet.
        MethodHandles.Lookup lazy = lookup.defineHiddenClass(bytes, false);
        System.out.println("after-lazy-define");

        // A SECOND hidden class is defined and initialized immediately.
        MethodHandles.Lookup eager = lookup.defineHiddenClass(bytes, true);
        System.out.println("after-eager-define");
        System.out.println("same-hidden-class="
                + (lazy.lookupClass() == eager.lookupClass()));

        // Looking up the handle is separate from invoking it.
        MethodHandle answer = lazy.findStatic(
                lazy.lookupClass(),
                "answer",
                MethodType.methodType(int.class));

        // Invocation triggers initialization of the lazy hidden class.
        System.out.println("lazy-answer=" + (int) answer.invokeExact());

        try {
            System.out.println(Broken.ANSWER);
        } catch (ExceptionInInitializerError error) {
            System.out.println("first-error="
                    + error.getClass().getSimpleName());
        }
        try {
            System.out.println(Broken.ANSWER);
        } catch (NoClassDefFoundError error) {
            System.out.println("second-error="
                    + error.getClass().getSimpleName());
        }
    }
}
```

### 7.2. Biên dịch và chạy

Đứng ở thư mục chứa `src`. Dùng một JDK hiện đại còn được hỗ trợ có `javac` nhận `--release 15` (ví dụ JDK 21):

```bash
javac --release 15 -encoding UTF-8 -d out src/demo/InitializationCycleDemo.java
java -cp out demo.InitializationCycleDemo
```

`javac` tự tạo các file class của nested classes trong `out/demo`, gồm `InitializationCycleDemo$HiddenTemplate.class`. `getResourceAsStream(...)` tìm resource cùng package `demo` và đọc class file **ở dạng binary**, không yêu cầu load/initialize class mẫu theo tên.

**Stdout chính xác cho lần chạy bình thường, không sử dụng concurrency:**

```text
cycle-start
B.<clinit> value=1
A.<clinit> value=2
A.value=2
B.value=1
after-lazy-define
HiddenTemplate.<clinit>
after-eager-define
same-hidden-class=false
HiddenTemplate.<clinit>
lazy-answer=42
first-error=ExceptionInInitializerError
second-error=NoClassDefFoundError
```

### 7.3. Giải thích từng phần của output

**Phần A/B:**

- `main` dùng `A.value` đầu tiên, kích hoạt initialize A.
- A đang initialize cần `B.value`, nên B bắt đầu initialize.
- B cần `A.value`, nhưng chính thread đó đã đang initialize A: JVM không khởi tạo A lần nữa, nên B đọc giá trị mặc định `0` của `A.value` và gán `B.value=1`.
- B in `B.<clinit> value=1`, hoàn tất. A tiếp tục gán `A.value=2` và in `A.<clinit> value=2`.
- Hai dòng `A.value` và `B.value` bên ngoài là trạng thái **sau khi** chuỗi initialize đã hoàn thành.

**Phần hidden class:**

- `lookup.defineHiddenClass(bytes, false)` chỉ define/link lớp hidden thứ nhất, nên **không in** `HiddenTemplate.<clinit>` trước `after-lazy-define`.
- `lookup.defineHiddenClass(bytes, true)` định nghĩa lớp thứ hai và **chạy initializer** ngay, nên xuất hiện dòng `HiddenTemplate.<clinit>` trước `after-eager-define`.
- Hai hidden classes khác identity: `same-hidden-class=false`. Dùng cùng mảng bytes không khiến JVM tái sử dụng class đã định nghĩa.
- `lazy.findStatic(...)` tạo method handle; khi `answer.invokeExact()` được **gọi**, lớp thứ nhất mới initialize, vì thế in `HiddenTemplate.<clinit>` **lần thứ hai**, rồi method trả `42` và `main` in `lazy-answer=42`.
- `MethodType.methodType(int.class)` mô tả method không có tham số, trả `int`. Cast `(int)` ở `invokeExact()` bắt buộc để chữ ký call site khớp chính xác với method handle.

**Phần initializer thất bại:**

- `Broken.ANSWER` là `static final int` nhưng **không phải constant variable**, vì được gán bởi lời gọi `compute()` chứ không phải constant expression. Vì vậy lần đọc đầu tiên bắt buộc initialize Broken.
- `compute()` ném `IllegalStateException`. JVM quấn exception không thuộc loại `Error` vào `ExceptionInInitializerError`, đánh dấu class **erroneous**, rồi lời gọi bên ngoài in `first-error=ExceptionInInitializerError`.
- Lần truy cập tiếp theo với **cùng class identity/loader** không chạy lại initializer; JVM ném `NoClassDefFoundError`, nên in `second-error=NoClassDefFoundError`. Không kết luận class file biến mất: đây là hậu quả trạng thái initialization thất bại trước đó.

**Tại sao không in tên class hidden?** `Class.getName()` của hidden class có suffix JVM-generated và không ổn định. Đưa nó vào expected output sẽ khiến kiểm thử phụ thuộc runtime. Ví dụ chỉ so sánh identity và in kết quả ổn định.

## 8. Các trường hợp khó: phụ thuộc được sinh ra và initialization không kiểm soát

### 8.1. Sinh nhiều hidden classes rồi khởi tạo chéo

Giả sử framework định nghĩa hidden class A và B, rồi logic initializer của A muốn gọi method static của B, đồng thời initializer của B muốn gọi lại A. Rủi ro giống class thường, nhưng còn khó hơn vì **hidden class không tra cứu được theo binary name thông thường**. Bạn phải giữ `Class<?>`, `Lookup`, `MethodHandle` của mỗi lớp và cấp các reference đúng lúc.

Phân biệt hai loại quan hệ:

- **Dependency ở bytecode:** class file chứa constant-pool symbolic references tới các **lớp có tên**. Các references này được resolution theo quy tắc JVM, class loader và module.
- **Dependency động của framework:** host truyền một method handle, static field, callback hay object tham chiếu tới hidden class mới cho lớp khác. Đó là quan hệ do runtime của bạn quản lý, không có nghĩa JVM sẽ tự tìm hidden class bằng tên.

Trong trường hợp thứ hai, nếu bạn kích hoạt initializer trước khi **mọi dependency cần thiết đã được cấp**, initializer có thể thấy `null`, giá trị mặc định hoặc ném exception. Vì thế cần dựng cấu trúc phụ thuộc trước, rồi mới cho những hoạt động static có side effect chạy.

### 8.2. Thứ tự define rồi initialize không tự giải quyết tất cả cycle

```text
Tạo bytes A, B
    ↓
defineHiddenClass(bytesA, false)
defineHiddenClass(bytesB, false)
    ↓
Liên kết references/callbacks cần thiết ở host
    ↓
Khởi tạo từng lớp theo thứ tự đã thiết kế
    ↓
Công bố API/MethodHandles cho caller khác
```

Đây là **sơ đồ kiến trúc tham khảo**, không phải code Java độc lập. Chỉ vì gọi `defineHiddenClass(..., false)` cho cả hai không có nghĩa cycle được chữa: nếu khi khởi tạo A nó vẫn bắt đầu khởi tạo B và B lại cần giá trị chưa hoàn thiện của A, vấn đề còn nguyên.

Một giải pháp bền vững hơn là **phá vòng ở giai đoạn initializer** bằng cách chuyển kết nối A↔B sang một bước `bootstrap()` rõ ràng. Ví dụ một đối tượng `RuntimeContext` được host xây dựng sau khi định nghĩa các lớp, rồi truyền các dependency bất biến/handles vào callback khi các lớp thực sự sử dụng chúng. `static { ... }` nên hạn chế việc cần các lớp khác ở trạng thái đã initialized.

### 8.3. Việc tạo MethodHandle khác việc gọi

```java
MethodHandles.Lookup h =
        lookup.defineHiddenClass(bytes, false);
MethodHandle mh = h.findStatic(
        h.lookupClass(),
        "run",
        MethodType.methodType(void.class));

// Chỉ khi invoke, method và class của nó thực sự được dùng.
mh.invokeExact();
```

Đây là **đoạn minh họa** yêu cầu bytes và method `run()` thật sự tồn tại. `findStatic` xác minh chữ ký/quyền theo API và tạo handle; class initialization thường được kích hoạt **khi handle thực thi static method**, không phải do dòng lấy `Class<?>` hoặc định nghĩa class. Đừng dùng `findStatic` như lời hứa rằng constructor hay static data đã sẵn sàng.

### 8.4. Thứ tự khi có superclass và interface

Theo JLS, khi một class được initialized, các superclass cần thiết được khởi tạo trước; những superinterfaces khai báo **default methods** cũng thuộc các trường hợp cần chú ý. Thứ tự này có thể làm xuất hiện dependency ẩn mà người viết `static { ... }` không thấy nếu chỉ nhìn class hiện tại.

Đặc biệt, một generated class có supertype thuộc một framework khác có thể kích hoạt initializer của supertype trước chính nó. Kiểm tra cả **superclass/interface graph** khi chẩn đoán thứ tự output và lỗi initialization.

## 9. Lỗi, exception và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách chẩn đoán/xử lý |
| --- | --- | --- |
| Giá trị static là `0`/`false`/`null` trong lúc khởi tạo | Vòng phụ thuộc cùng thread làm đọc giá trị chuẩn bị mặc định | Xác định A → B → A, chuyển dependency sang bootstrap sau initialization |
| Chương trình treo lúc dùng class lần đầu | Có thể có deadlock giữa các thread initialize chéo | Thu thread dump/JVM diagnostics; kiểm tra luồng `<clinit>` và chỗ chờ class initialization |
| `ExceptionInInitializerError` | Exception không phải `Error` ném ra khi `<clinit>` đang chạy | Kiểm tra `getCause()`, cấu hình, file/network hoặc dependency ném lỗi |
| `NoClassDefFoundError` sau một lần lỗi initializer | Class đã ở trạng thái **erroneous** | Tìm lỗi khởi tạo **đầu tiên** trong log; không chỉ xử lý lần ném sau |
| `ClassFormatError` / `VerifyError` | Class file bytes hỏng hoặc bytecode không hợp lệ | Kiểm tra binary bytes, verifier, bytecode generator, version |
| `UnsupportedClassVersionError` | JVM không hỗ trợ version class file | Dùng `javap -verbose`, kiểm tra runtime, biên dịch `--release` phù hợp |
| `IllegalAccessException` tại `defineHiddenClass` | Lookup không có **full privilege access** | Lấy lookup đúng từ trusted class/module; kiểm tra modes |
| `IllegalArgumentException` tại `defineHiddenClass` | Internal name của bytes không cùng package với lookup class, hoặc điều kiện đầu vào khác vi phạm | Kiểm tra package/internal name và class file |
| `NoSuchMethodException` với `findStatic` | Tên/method type không tồn tại | Kiểm tra signature trong class file |
| `WrongMethodTypeException` với `invokeExact` | Kiểu tại call site không khớp chính xác `MethodHandle` | Khai báo/cast kiểu chính xác; hiểu khác biệt `invoke` và `invokeExact` |
| Runtime phụ thuộc GC cho việc dỡ hidden class | Reference hoặc `ClassOption.STRONG` còn giữ lifecycle | Quản lý cache, handles, instances; không giả định dỡ ngay |
| Chạy initializer nhiều lần dù tưởng chỉ có “một lớp” | Framework định nghĩa **nhiều hidden class identities** từ cùng bytes | Theo dõi `Class<?>` identity và số lần `defineHiddenClass` |

### 9.1. Không “bắt rồi chạy tiếp” một cách mù quáng

Sau initialization thất bại, class cụ thể có thể ở trạng thái erroneous, nên lần gọi khác sẽ không khởi tạo lại như lần đầu. Cách xử lý đúng là **khắc phục nguyên nhân ban đầu** và xây lại một runtime/class identity hợp lệ khi thực sự cần, thường trong một quy trình khởi động mới hoặc theo cơ chế lifecycle của framework. Một hidden class khác được định nghĩa mới cũng là **identity khác**, nhưng điều này **không tự khắc phục** nguyên nhân lỗi và không nên dùng như “retry thần kỳ”.

Tránh dùng `catch (Throwable ignored)` để biến mọi lỗi class initialization thành giá trị mặc định. `Error` và các lỗi verify/link có thể phản ánh trạng thái runtime không phù hợp để tiếp tục xử lý dữ liệu như không có gì xảy ra.

### 9.2. Chẩn đoán mà không phụ thuộc lịch scheduler

- Ghi log **thứ tự kích hoạt** và class identity, không chỉ tên đơn giản; với hidden class, tên có suffix động.
- Kiểm tra các method `static` gọi ở ngay đầu `<clinit>`, các phụ thuộc vào static field và các class được tạo lúc bootstrap.
- Kiểm tra `initialize=true/false` và chỗ gọi `Lookup.ensureInitialized` hoặc `MethodHandle.invokeExact`.
- Dùng `javap -c -p` (hoặc công cụ quan sát bytecode) để xem `<clinit>` và thứ tự tham chiếu khi mã nguồn được **sinh tự động**.
- Với nghi vấn deadlock, dùng thread dump/tracing trong môi trường tách biệt và kiểm tra các thread liên quan; đừng tạo một test có thể treo vô hạn trên tiến trình ứng dụng chính.
- Xác nhận class file version phù hợp: `--release 15` tạo class file **major version 59**, có thể kiểm tra bằng `javap -verbose`.

## 10. Mẫu thiết kế tránh vòng khởi tạo

### Phương án A: bỏ side effects khỏi static initializer

Thay vì:

```java
// Chỉ minh họa rủi ro, không phải chương trình hoàn chỉnh.
class A {
    static final Service service = B.createService();
}
class B {
    static final Client client = A.createClient();
}
```

hãy tạo các class ít phụ thuộc hơn và xây graph ở bước bootstrap:

```java
// Minh họa cấu trúc, cần định nghĩa Service, Client, A, B trong dự án.
final class RuntimeBootstrap {
    static RuntimeContext start(Config config) {
        A a = new A();
        B b = new B();
        RuntimeContext context = new RuntimeContext(a, b, config);
        context.initialize();
        return context;
    }
}
```

Hai đoạn này chỉ diễn đạt ý tưởng, **không phải chương trình Java độc lập** vì các kiểu ví dụ chưa được định nghĩa. Mục tiêu là chuyển logic kết nối/chia sẻ state sang một phương thức có kiểm soát và tránh cho `A.<clinit>`/`B.<clinit>` phụ thuộc chéo.

### Phương án B: immutable constants khi thực sự là hằng

Với giá trị tính hoàn toàn độc lập, có thể dùng constant expression:

```java
final class Limits {
    static final int MAX_ITEMS = 100;
    static final String PREFIX = "item-";
}
```

Các trường này là **constant variables** (nếu đáp ứng đầy đủ điều kiện JLS), có thể được compiler inline vào caller và không yêu cầu chạy initializer của class khai báo khi chỉ đọc chúng.

**Nhưng:** thay đổi giá trị hằng có thể đòi **biên dịch lại caller** do inlining; đừng dùng constant variables như một cơ chế “đọc cấu hình runtime”. Một giá trị tính từ môi trường hoặc hàm không phải constant expression, và việc truy cập có thể kích hoạt initialization.

### Phương án C: chủ động điều phối initialization trong runtime sinh mã

- Sinh/kiểm tra class bytes theo cùng package của lookup class.
- Định nghĩa hidden classes với `initialize=false` nếu cần hoàn tất wiring của runtime trước khi initializer chạy.
- Tránh cho `<clinit>` tự kích hoạt khởi tạo lớp sinh động khác có tham chiếu vòng.
- Khi dependency graph đã hợp lệ, dùng `ensureInitialized` hoặc active use có chủ đích, sau đó mới expose `MethodHandle` cho các thread xử lý request.
- Quy định rõ ownership/lifecycle: `STRONG` chỉ khi cần giữ class cùng defining loader; quản lý cache của `Class<?>` và `MethodHandle`.
- Viết test lặp lại trên JVM mục tiêu, nhưng không coi scheduler khác nhau là cách giải quyết cycle.

## 11. Checklist ôn tập và tự kiểm tra

1. Đã phân biệt **prepare = giá trị mặc định** với **initialize = chạy static field initializers và static blocks** chưa?
2. Class nào được **active use đầu tiên**, và lần truy cập đó có phải constant variable được inline không?
3. Có đường A → B → A trong khởi tạo static? Nếu có, một thread sẽ đọc giá trị mặc định nào?
4. Có nhiều thread có thể initialize các class phụ thuộc chéo cùng lúc? Nếu có, đã loại bỏ nguy cơ **đợi nhau không tiến** chưa?
5. Với hidden class, class bytes có hợp lệ và cùng package lookup class không?
6. `Lookup` có full privilege access đúng phạm vi chưa? `initialize=true/false` có được lựa chọn có chủ đích không?
7. Đã tách **tạo method handle** khỏi **invoke handle**, và dùng `ensureInitialized` đúng thời điểm chưa?
8. Khi initializer lỗi, có xem **lỗi đầu tiên** thay vì chỉ nhìn `NoClassDefFoundError` ở lần tiếp theo không?
9. Khi kiểm thử nhiều hidden classes sinh từ cùng bytes, có nhận ra đó là **những class identities khác nhau** không?
10. Các static initializer có làm I/O, giữ lock, start/join thread hoặc tham chiếu chéo không cần thiết không?
11. Đã kiểm tra code generated bằng `javap`, test init order và timeout phù hợp cho các tình huống đa luồng chưa?
12. Runtime JDK dùng trong vận hành có còn được nhà cung cấp hỗ trợ và tương thích class file version không?

## 12. Tài liệu chính thức còn áp dụng

- **Java Language Specification, `12.4.1 và `12.4.2`:** các trường hợp kích hoạt class initialization, đồng bộ hóa và xử lý đệ quy cùng thread: https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4
- **Java Virtual Machine Specification `5.5 Initialization`:** active use của bytecode và MethodHandle, các trạng thái khởi tạo: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5
- **Java SE 15 `MethodHandles.Lookup.defineHiddenClass` / `ensureInitialized`:** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Java SE hiện đại `MethodHandles.Lookup`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **OpenJDK JEP 371 — Hidden Classes (Java 15):** https://openjdk.org/jeps/371
- **Java SE 15 `ExceptionInInitializerError` và `NoClassDefFoundError`:** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/ExceptionInInitializerError.html và https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/NoClassDefFoundError.html

Những cơ chế này thuộc Java/JVM chính thức và **vẫn còn áp dụng trong Java hiện đại**. Với hệ thống sinh mã, kết quả đúng và ổn định không chỉ phụ thuộc class file hợp lệ mà còn phụ thuộc **thời điểm initialization, dependency graph và sự tương tác giữa các thread**.
