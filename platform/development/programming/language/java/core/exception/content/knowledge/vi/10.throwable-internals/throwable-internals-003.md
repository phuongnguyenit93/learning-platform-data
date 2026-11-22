# Stack trace được ghi nhận tại thời điểm nào trong Java?

Khi một exception xảy ra trong Java, stack trace giúp trả lời câu hỏi **“đối tượng lỗi này đã được tạo ra trong đường gọi nào?”**. Nhưng một hiểu nhầm phổ biến là mỗi lệnh `throw` đều tự động chụp một stack trace mới tại vị trí ném. Với `Throwable` thông thường, **stack trace được ghi nhận khi đối tượng exception được khởi tạo** (thông qua cơ chế `fillInStackTrace()` trong quá trình khởi tạo), **không phải tự động làm mới ở mỗi lần `throw e`**.

Điều này giải thích tại sao một exception được tạo trong phương thức A, lưu lại rồi mới ném trong phương thức B thường có frame đầu là **A**, không phải B; cũng giải thích vì sao `throw e` trong `catch` thường giữ lại dấu vết lỗi gốc. Tuy nhiên, Java có API chủ động làm mới hoặc thay thế stack trace và JVM có những ngoại lệ/khả năng tối ưu đặc biệt. Vì vậy cần phân biệt **thời điểm ghi nhận**, **thời điểm ném**, **thời điểm in**, và **stack call hiện tại**.

Bài này làm rõ các thời điểm đó, cách kiểm chứng bằng Java 17+, tác động của rethrow, wrapping, `fillInStackTrace()`, `getStackTrace()`, `setStackTrace()`, suppressed exceptions, constructor đặc biệt và các giới hạn thực tế của dữ liệu stack trace.

## 1. Stack trace là gì?

**Stack trace** của một đối tượng `Throwable` là thông tin về các vị trí gọi phương thức liên quan đến thời điểm stack trace được ghi. Một stack trace thường là chuỗi các phần tử `StackTraceElement`:

```text
java.lang.IllegalStateException: Lỗi ví dụ
    at Example.create(Example.java:12)
    at Example.main(Example.java:20)
```

Đây là **hình thức minh họa**, không phải output cố định của chương trình cụ thể: tên tệp và số dòng thay đổi theo mã nguồn, cách biên dịch và môi trường.

Một `StackTraceElement` có thể cung cấp:

- Tên lớp: `getClassName()`.
- Tên phương thức: `getMethodName()`.
- Tên tệp nguồn: `getFileName()` nếu có.
- Số dòng: `getLineNumber()` nếu có, có thể là số âm biểu thị thiếu thông tin phù hợp.
- Trạng thái phương thức native: `isNativeMethod()`.
- Trong Java hiện đại còn có dữ liệu liên quan module và class loader trong một số trường hợp.

Thông thường, phần tử đầu tiên của mảng `getStackTrace()` biểu thị điểm ghi nhận gần nhất ở mức mã người dùng, sau khi JVM xử lý những frame khởi tạo nội bộ. Tuy nhiên, **không nên coi số lượng, thứ tự hay mức độ đầy đủ của mọi frame là bất biến trong mọi JVM, công cụ biên dịch và cấu hình**.

Stack trace không phải lịch sử tất cả câu lệnh đã chạy; nó là **ảnh chụp ngăn xếp lời gọi**, không phải bản ghi tuần tự toàn bộ sự kiện của chương trình.

## 2. Bốn thời điểm phải phân biệt

| Sự kiện | Ý nghĩa | Có mặc nhiên ghi stack trace mới vào cùng exception không? |
| --- | --- | --- |
| `new SomeException(...)` | Tạo object; constructor `Throwable` thông thường ghi thông tin ngăn xếp | **Có**, theo cơ chế khởi tạo thông thường và nếu writable stack trace được bật |
| `throw e;` | Ném object đang được `e` tham chiếu | **Không**; thông thường giữ stack trace đang có |
| `e.fillInStackTrace();` | Yêu cầu lấp lại stack trace theo ngăn xếp hiện tại | **Có**, nếu object cho phép writable stack trace |
| `e.printStackTrace();` hoặc `e.getStackTrace()` | In hoặc đọc dữ liệu stack trace đã ghi | **Không**; chúng không tự chụp lại đường gọi chỉ vì được truy cập |

Ngoài ra:

- `new WrapperException("...", cause)` tạo **object mới** nên wrapper có stack trace của riêng nó, được ghi tại **nơi tạo wrapper**.
- Exception gốc trong `cause` vẫn là object khác và có thể giữ stack trace được tạo trước đó.
- `e.setStackTrace(array)` **thay thế dữ liệu stack trace hiển thị** bằng dữ liệu do mã cung cấp nếu object cho phép; đây không phải thao tác tự chụp current call stack.
- Một số object `Throwable` có thể được tạo **không ghi stack trace** bằng constructor dành cho lớp con, và JVM có thể bỏ qua/giới hạn thông tin theo cơ chế đặc biệt.

Điểm mấu chốt: **ném exception** và **ghi nhận stack trace** là hai hoạt động khác nhau, dù chúng thường xảy ra gần nhau khi bạn viết `throw new ...`.

## 3. Tại sao `throw new ...` khiến ta tưởng stack trace được tạo ở lúc ném?

Xét:

```java
throw new IllegalArgumentException("Sai tham số");
```

Đây là một **câu lệnh minh họa**. Trong cùng biểu thức có **hai việc** diễn ra gần nhau:

1. `new IllegalArgumentException(...)` tạo object; đường khởi tạo `Throwable` thông thường ghi stack trace.
2. `throw` ném chính object vừa tạo.

Vì khởi tạo và ném nằm ở cùng vị trí mã nguồn, stack trace thường chỉ tới đúng dòng có `throw new`. Nhưng nguyên nhân là **đối tượng được tạo tại đó**, không phải vì Java luôn ghi trace tại mọi vị trí có từ khóa `throw`.

Để chứng minh, tách hai việc ra:

```java
IllegalArgumentException problem =
        new IllegalArgumentException("Sai tham số");
// Có thể có những thao tác khác.
throw problem;
```

Đây là **đoạn minh họa trong một phương thức**. Stack trace thông thường được ghi ở dòng tạo `problem`. Lệnh `throw problem` sau đó không tự làm mới trace.

Quan hệ này đặc biệt quan trọng khi exception được khởi tạo từ một helper, được giữ trong field hoặc được chuyển qua nhiều tầng trước khi ném.

## 4. Ví dụ chạy được: tạo ở A, ném ở B

Lưu chương trình sau thành **`CreationVsThrowDemo.java`**:

```java
public class CreationVsThrowDemo {
    static IllegalStateException makeProblem() {
        return new IllegalStateException("Không hợp lệ");
    }

    static void throwLater(IllegalStateException problem) {
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = makeProblem();
        System.out.println("Tạo xong exception");

        try {
            throwLater(problem);
        } catch (IllegalStateException e) {
            System.out.println("Bắt tại main");
            System.out.println("Frame đầu: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cùng object: " + (e == problem));
        }
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac -encoding UTF-8 --release 17 CreationVsThrowDemo.java
java CreationVsThrowDemo
```

**Stdout chính xác** trong môi trường JVM chuẩn có writable stack trace:

```text
Tạo xong exception
Bắt tại main
Frame đầu: makeProblem
Cùng object: true
```

Frame đầu là `makeProblem`, nơi `new IllegalStateException(...)` thực thi, **không phải `throwLater`**. Mặc dù lệnh `throw` thực sự nằm trong `throwLater`, không có bước chụp lại stack trace tự động chỉ vì một object có sẵn được ném.

Đối tượng bên ngoài handler vẫn là `problem`; phép so sánh `e == problem` là `true`. `getStackTrace()[0]` được dùng trong một ví dụ có trace thông thường; với loại Throwable vô hiệu hóa writable stack trace hoặc tối ưu đặc biệt, mảng có thể rỗng, nên mã chẩn đoán tổng quát phải kiểm tra độ dài.

## 5. Constructor `Throwable` liên quan `fillInStackTrace()` như thế nào?

Các constructor thông thường của `Throwable` ghi nhận thông tin ngăn xếp trong quá trình tạo đối tượng. API `fillInStackTrace()` cung cấp khả năng **lấp lại thông tin stack trace của object theo ngữ cảnh gọi hiện tại**.

Có thể hiểu:

```text
new MyException(...)
    |
    +-- chạy chuỗi constructor Throwable
    |       |
    |       +-- thông thường ghi stack trace hiện tại
    |
    +-- object được sử dụng sau đó
            |
            +-- throw object: không tự chụp lại
            +-- fillInStackTrace(): chủ động chụp lại (nếu writable)
```

Mô hình trên là mô tả **ngữ nghĩa Java**, không phải giả định mọi JVM có cùng mã native nội bộ. Ở mức ứng dụng, điều cần nhớ là thông tin stack trace thông thường gắn với **thời điểm tạo object** và có thể thay đổi khi chủ động gọi `fillInStackTrace()`.

Các lớp con có thể tùy biến việc khởi tạo và quản lý trace. Vì vậy khi xử lý exception do framework, thư viện hoặc JVM tạo, không nên khẳng định chắc chắn mọi object được ghi đúng một lần và không thể thay đổi.

## 6. Ném lại bằng `throw e` có giữ stack trace không?

Thông thường **có**. `throw e` trong handler ném lại **chính object** đã được bắt, nên nó giữ stack trace của object đó nếu không có mã nào sửa trace.

Ví dụ **`RethrowTraceDemo.java`**:

```java
public class RethrowTraceDemo {
    static void origin() {
        throw new IllegalArgumentException("Lỗi tại origin");
    }

    static void middle() {
        try {
            origin();
        } catch (IllegalArgumentException e) {
            System.out.println("Catch giữa: "
                    + e.getStackTrace()[0].getMethodName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalArgumentException e) {
            System.out.println("Catch ngoài: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 RethrowTraceDemo.java
java RethrowTraceDemo
```

**Stdout chính xác** trên Java 17 thông thường:

```text
Catch giữa: origin
Catch ngoài: origin
Message: Lỗi tại origin
```

Khi `origin()` gọi `new IllegalArgumentException(...)`, trace được ghi với frame đầu `origin`. Handler trong `middle` nhận object, đọc trace và thực hiện `throw e`. Handler ngoài nhận cùng object; frame đầu vẫn là `origin`.

**Không hiểu nhầm:** dù trace giữ lại vị trí ban đầu, exception thực sự đã đi qua `middle()`. Stack trace ban đầu đã ghi các frame đang hoạt động lúc khởi tạo; không có nghĩa là trace sẽ tiếp tục dài thêm từng lần rethrow. Muốn ghi nhận một quyết định rethrow quan trọng, có thể log có cấu trúc ở đúng ranh giới hoặc bổ sung exception wrapper với cause theo hợp đồng.

## 7. Chủ động gọi `fillInStackTrace()` sẽ làm thay đổi điểm ghi nhận

`Throwable.fillInStackTrace()` là phương thức public (đồng bộ theo khai báo API) trả về chính `Throwable` sau khi cập nhật thông tin stack trace nếu việc ghi trace được cho phép.

Chương trình **`RefillTraceDemo.java`**:

```java
public class RefillTraceDemo {
    static IllegalStateException createProblem() {
        return new IllegalStateException("Dữ liệu sai");
    }

    static void refreshAndThrow(IllegalStateException problem) {
        System.out.println("Trước refresh: "
                + problem.getStackTrace()[0].getMethodName());
        problem.fillInStackTrace();
        System.out.println("Sau refresh: "
                + problem.getStackTrace()[0].getMethodName());
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = createProblem();

        try {
            refreshAndThrow(problem);
        } catch (IllegalStateException e) {
            System.out.println("Caller thấy: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cùng object: " + (e == problem));
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 RefillTraceDemo.java
java RefillTraceDemo
```

**Stdout chính xác** khi writable trace hoạt động thông thường:

```text
Trước refresh: createProblem
Sau refresh: refreshAndThrow
Caller thấy: refreshAndThrow
Cùng object: true
```

`fillInStackTrace()` **không tạo exception mới**: identity vẫn giữ nguyên. Nhưng nó **thay thế thông tin stack trace gắn với object** bằng thông tin từ vị trí chủ động refresh, nên frame đầu đổi sang `refreshAndThrow`.

Cảnh báo thiết kế: gọi `fillInStackTrace()` có thể khiến vị trí lỗi ban đầu không còn hiển thị như trước, làm chẩn đoán khó hơn. Không nên gọi phương thức này chỉ để làm cho stack trace “trông gần hiện tại hơn” trừ khi có một lý do rõ ràng và thông tin gốc được bảo toàn bằng cơ chế phù hợp.

## 8. `throw e`, `throw new ...` và wrapping có trace khác nhau

Ba lựa chọn cần phân biệt:

| Cách làm | Object ném ra | Vị trí ghi trace thường thấy | Có giữ lỗi gốc ở đâu? |
| --- | --- | --- | --- |
| `throw e;` | Chính object `e` | Thời điểm object `e` được tạo/refresh | Bản thân object đó |
| `throw new IllegalStateException("Lỗi mới");` | Object mới | Nơi tạo object mới | Không giữ object cũ nếu không thiết lập liên kết |
| `throw new IllegalStateException("Lỗi dịch vụ", e);` | Wrapper mới | Nơi tạo wrapper | `wrapper.getCause() == e` |
| `e.fillInStackTrace(); throw e;` | Chính object `e` | Nơi gọi `fillInStackTrace()` | Có thể làm mất trace ban đầu của chính object |

**Wrapping** là cách giữ thêm bối cảnh tầng hiện tại mà không bắt buộc xóa stack trace của exception gốc. Nếu tầng repository ném lỗi I/O, tầng service có thể tạo ngoại lệ mô tả thất bại của service với `cause` là lỗi I/O.

Chữ ký checked/unchecked của wrapper cần tuân thủ hợp đồng Java; việc truyền `cause` không tự biến một checked exception thành unchecked trừ khi **kiểu wrapper** được chọn là unchecked.

## 9. Ví dụ wrapper: hai stack trace ở hai thời điểm

Lưu **`WrapperTraceDemo.java`**:

```java
public class WrapperTraceDemo {
    static void operation() {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }

    static void service() {
        try {
            operation();
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(
                    "Dịch vụ thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException e) {
            System.out.println("Wrapper frame đầu: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Cause frame đầu: "
                    + e.getCause().getStackTrace()[0].getMethodName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 WrapperTraceDemo.java
java WrapperTraceDemo
```

**Stdout chính xác** với writable trace thông thường:

```text
Wrapper frame đầu: service
Cause frame đầu: operation
Cause message: Giá trị không hợp lệ
```

`IllegalArgumentException` được tạo trong `operation`, nên cause giữ trace tại đó. `IllegalStateException` wrapper được tạo trong `service`, nên trace của wrapper có frame đầu `service`. Quan hệ `getCause()` giúp thấy **cả bối cảnh tầng cao lẫn điểm phát sinh gốc**.

Đây là một lý do wrapping với cause thường tốt hơn gọi `fillInStackTrace()` trên exception cũ: wrapper giữ được hai góc nhìn mà không cần ghi đè trace gốc.

## 10. `getStackTrace()` không tự cập nhật theo call stack hiện tại

`getStackTrace()` trả về một mảng `StackTraceElement[]` thể hiện dữ liệu stack trace **đang được lưu trong object**. Gọi phương thức từ caller A, B hoặc C không tự làm cho mảng biến thành ảnh chụp tại A, B hoặc C.

Chẳng hạn:

```java
static String firstFrame(Throwable e) {
    StackTraceElement[] frames = e.getStackTrace();
    return frames.length == 0
            ? "(không có frame)"
            : frames[0].getMethodName();
}
```

Đây là **phương thức minh họa** có thể đặt trong một lớp Java. Nó đọc frame đầu đã có, đồng thời xử lý an toàn trường hợp mảng rỗng. Nó không gọi `fillInStackTrace()`.

Hai lưu ý:

1. **Không chắc chắn mảng luôn có phần tử.** Throwable có thể được tạo với writable trace bị tắt, hoặc trong một số trường hợp JVM có thể không cung cấp các frame mong đợi.
2. **Không nên coi số dòng và tên tệp là khóa dữ liệu ổn định.** Chúng có thể đổi khi sửa source, thiếu debug information, dùng native code, build khác hoặc tối ưu runtime.

Việc gọi `getStackTrace()` ở thời điểm muộn không giúp “quay phim” những call stack đã trôi qua; nó chỉ đọc thông tin object đang lưu.

## 11. `getStackTrace()` trả một mảng có thể chỉnh, nhưng không được sửa nội dung object qua mảng đó

`Throwable.getStackTrace()` trả về **bản sao mảng** (`StackTraceElement[]`), không phải một mảng có thể dùng để sửa trực tiếp trace bên trong object bằng cách thay phần tử.

Ví dụ **`StackTraceCopyDemo.java`**:

```java
public class StackTraceCopyDemo {
    static IllegalStateException create() {
        return new IllegalStateException("Ví dụ");
    }

    public static void main(String[] args) {
        IllegalStateException e = create();

        StackTraceElement[] snapshot = e.getStackTrace();
        String originalMethod = snapshot[0].getMethodName();

        snapshot[0] = new StackTraceElement(
                "FakeClass", "fakeMethod", "Fake.java", 1);

        System.out.println("Snapshot đã sửa: "
                + snapshot[0].getMethodName());
        System.out.println("Object vẫn giữ: "
                + e.getStackTrace()[0].getMethodName());
        System.out.println("Ban đầu: " + originalMethod);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 StackTraceCopyDemo.java
java StackTraceCopyDemo
```

**Stdout chính xác** với trace bình thường:

```text
Snapshot đã sửa: fakeMethod
Object vẫn giữ: create
Ban đầu: create
```

Bạn đã thay phần tử của **mảng local `snapshot`**, không thay thông tin trace trong object. Nếu muốn can thiệp chính thức vào trace của exception, API cung cấp `setStackTrace(...)`; tuy nhiên việc đặt frame giả như vậy không phải hành vi nên làm trong code nghiệp vụ.

`StackTraceElement` là đối tượng biểu diễn một frame; sử dụng chúng cho quan sát/chẩn đoán khác với việc cố sửa lịch sử để làm mất dấu nguồn lỗi.

## 12. `setStackTrace()` thay dữ liệu, không chụp current stack

`Throwable.setStackTrace(StackTraceElement[] stackTrace)` có thể **thay thế** thông tin trace của một Throwable hỗ trợ writable stack trace bằng mảng `StackTraceElement` do bạn cung cấp. Không có bước tự chụp đường gọi hiện tại chỉ vì gọi `setStackTrace`.

Ví dụ minh họa:

```java
Throwable e = new IllegalStateException("Lỗi");
e.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Example", "custom", "Example.java", 7)
});
```

Đây là **khung minh họa**. Sau khi đặt trace nhân tạo, nếu object cho phép writable stack trace, `e.getStackTrace()[0].getMethodName()` sẽ là `"custom"`; điều đó **không** có nghĩa phương thức Java tên `custom` thực sự đã được gọi tại thời điểm lỗi.

API sẽ kiểm tra tính hợp lệ của mảng được truyền, ví dụ không chấp nhận mảng `null` hoặc phần tử `null`. Nó sao chép mảng để tránh việc người gọi thay đổi dữ liệu đã đặt chỉ bằng cách sửa mảng bên ngoài.

Về thực hành, **đừng làm giả trace để “sửa lỗi”**. Khi cần thêm ngữ cảnh, hãy dùng message, error code, wrapper với cause, hoặc log có cấu trúc; khi cần biết call stack hiện tại, sử dụng API quan sát stack hiện tại thay vì viết frame giả vào Throwable.

## 13. Phân biệt stack trace đã ghi với call stack đang chạy

Đối tượng `Throwable` chứa **dữ liệu chẩn đoán được ghi ở một thời điểm**. Call stack hiện tại của thread là một cấu trúc đang thay đổi liên tục theo lời gọi và lệnh trả về.

Các API quan sát stack hiện tại gồm `Thread.currentThread().getStackTrace()` hoặc `StackWalker` (Java 9+). Chúng phục vụ mục đích khác với việc đọc trace cũ từ exception.

Ví dụ **`LiveVsStoredStackDemo.java`**:

```java
public class LiveVsStoredStackDemo {
    static Exception make() {
        return new Exception("Tạo trong make");
    }

    static void inspect(Exception e) {
        System.out.println("Lỗi được tạo tại: "
                + e.getStackTrace()[0].getMethodName());

        boolean hasInspect = StackWalker.getInstance()
                .walk(stream -> stream.anyMatch(
                        frame -> frame.getMethodName().equals("inspect")));
        System.out.println("Call stack hiện tại có inspect: " + hasInspect);
    }

    public static void main(String[] args) {
        Exception e = make();
        inspect(e);
    }
}
```

Chạy Java 17:

```bash
javac -encoding UTF-8 --release 17 LiveVsStoredStackDemo.java
java LiveVsStoredStackDemo
```

**Stdout chính xác** trên Java 17 thông thường:

```text
Lỗi được tạo tại: make
Call stack hiện tại có inspect: true
```

`e.getStackTrace()` vẫn cho biết `make`, thời điểm tạo exception. `StackWalker` quan sát ngăn xếp **đang hoạt động** khi lời gọi `inspect` diễn ra, nên có frame của `inspect`.

Không nhầm hai kiểu thông tin: nếu muốn biết exception ban đầu phát sinh từ đâu, hãy đọc trace gắn với exception; nếu muốn biết code đang chạy qua những lời gọi nào **ở hiện tại**, hãy dùng API cho current stack.

## 14. `printStackTrace()` diễn ra muộn nhưng không có nghĩa trace được ghi muộn

Có thể tạo exception ở thời điểm T1, ném ở T2, bắt ở T3, rồi in ở T4:

```java
Throwable e = new IllegalStateException("Lỗi ví dụ"); // T1
// ...
throw e; // T2
```

Đây là **mã khung**. Nếu caller bắt được và thực hiện `e.printStackTrace()` tại T4, việc in diễn ra T4, nhưng stack trace được trình bày thường vẫn là dữ liệu đã ghi ở T1, trừ khi có API hoặc cơ chế khác sửa dữ liệu trong khoảng đó.

Phân biệt:

- `getMessage()`: trả thông điệp, không phải trace.
- `toString()`: mô tả ngắn thường gồm tên lớp và message, không phải danh sách frame.
- `getStackTrace()`: trả dữ liệu frame trong object.
- `printStackTrace()`: thực hiện **hành động in** thông tin exception và trace, có thể kèm cause và suppressed.
- `fillInStackTrace()`: **thay đổi dữ liệu trace**, không phải lệnh in.
- `setStackTrace()`: **gán dữ liệu frame do caller cung cấp**.

Theo API chuẩn, `printStackTrace()` không đối số in ra `System.err`, không phải `System.out`. Khi lệnh in stdout và stderr xen kẽ, thứ tự hiển thị thực tế giữa hai stream có thể khác nhau; đừng kiểm thử dựa trên một thứ tự gộp không được đảm bảo.

## 15. Cause có trace riêng; suppressed exceptions cũng có trace riêng

Một exception có thể tham chiếu **cause** và danh sách **suppressed exceptions**:

```java
IllegalArgumentException root =
        new IllegalArgumentException("Lỗi chính");

IllegalStateException wrapped =
        new IllegalStateException("Lỗi dịch vụ", root);

wrapped.addSuppressed(
        new IllegalStateException("Không cleanup được"));
```

Đây là **đoạn mã minh họa trong một phương thức**, không có `main`. Ba `Throwable` là **ba object**. Mỗi object được tạo ở một thời điểm tương ứng nên mỗi object thông thường mang trace riêng. Gắn object A làm cause hoặc suppressed của B **không tự chụp lại stack trace của A**.

Với `try-with-resources`:

1. Công việc chính ném exception A.
2. Khi rời khối, `close()` có thể ném exception B.
3. Java giữ A là **primary** và gắn B vào `A.getSuppressed()` khi thích hợp.
4. A và B có trace riêng: A gắn với nơi A được tạo, B gắn với nơi B được tạo/điền trace.

Ví dụ **`SuppressedFramesDemo.java`**:

```java
public class SuppressedFramesDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Lỗi close");
        }
    }

    static void work() {
        throw new IllegalArgumentException("Lỗi work");
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            work();
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: "
                    + e.getStackTrace()[0].getMethodName());
            Throwable closing = e.getSuppressed()[0];
            System.out.println("Suppressed: "
                    + closing.getStackTrace()[0].getMethodName());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 SuppressedFramesDemo.java
java SuppressedFramesDemo
```

**Stdout chính xác** trên Java 17 thông thường:

```text
Primary: work
Suppressed: close
```

Trace của A bắt đầu ở `work`; trace của B bắt đầu ở `close`. Việc A chứa B trong danh sách suppressed không gộp hai mảng frame thành một ảnh chụp và không làm B đổi thành exception tạo ở `work`.

Trong chương trình tổng quát, phải kiểm tra `getSuppressed().length` trước khi lấy phần tử `[0]`. Ví dụ này cố ý thiết kế resource luôn ném khi đóng và thân luôn ném, nên kết quả có một suppressed exception.

## 16. Constructor có thể tắt writable stack trace

Từ Java 7, `Throwable` có constructor dành cho lớp con:

```java
protected Throwable(String message,
                    Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace)
```

Tham số cuối, `writableStackTrace`, kiểm soát khả năng ghi stack trace của object. Khi đặt `false`, object được tạo theo chế độ **không ghi stack trace**, và các thao tác `fillInStackTrace()` hoặc `setStackTrace()` trên object đó không hoạt động như cách thông thường. `getStackTrace()` trả mảng rỗng.

Ví dụ chạy được **`NoWritableTraceDemo.java`**:

```java
public class NoWritableTraceDemo {
    static class SilentTraceException extends Exception {
        SilentTraceException(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        SilentTraceException problem =
                new SilentTraceException("Không ghi stack");

        System.out.println("Ban đầu: "
                + problem.getStackTrace().length);
        problem.fillInStackTrace();
        System.out.println("Sau fill: "
                + problem.getStackTrace().length);

        try {
            throw problem;
        } catch (SilentTraceException e) {
            System.out.println("Sau throw: "
                    + e.getStackTrace().length);
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NoWritableTraceDemo.java
java NoWritableTraceDemo
```

**Stdout chính xác:**

```text
Ban đầu: 0
Sau fill: 0
Sau throw: 0
Message: Không ghi stack
```

Đây là minh chứng trực tiếp rằng **không phải mọi `Throwable` đều có frame để đọc**, kể cả khi object đã được tạo, ném và bắt. Mã `e.getStackTrace()[0]` không an toàn nếu áp dụng tùy tiện cho mọi exception.

Tắt writable stack trace có thể được sử dụng có chủ đích trong một số exception được tạo rất thường xuyên để giảm overhead, nhưng đánh đổi khả năng chẩn đoán. Đừng tắt stack trace chỉ để che một bug hoặc vì muốn log ngắn đi.

## 17. `fillInStackTrace()` không bắt buộc mọi subclass phải hành xử giống hệt

`Throwable.fillInStackTrace()` có thể được **override** trong lớp con không final. Ngoài constructor có tham số `writableStackTrace`, một subclass có thể điều chỉnh chính sách thu thập dấu vết của nó.

Hệ quả:

- Không giả định mọi exception của thư viện đều có stack trace được ghi tại constructor theo cùng cách.
- Không giả định gọi `fillInStackTrace()` sẽ luôn tạo frame nếu object hoặc subclass đã được thiết kế không giữ trace.
- Không thao tác trực tiếp với các chi tiết nội bộ của `Throwable`; dùng API công khai và kiểm tra khả năng có mảng rỗng.
- Nếu tạo custom exception có hành vi đặc biệt, hãy tài liệu hóa tác động của nó tới logging, debug và các công cụ quan sát lỗi.

Với những ngoại lệ thông thường kế thừa `RuntimeException` hoặc `Exception` mà không override cơ chế này và không tắt writable trace, quy tắc học tập hiệu quả vẫn là: **constructor ghi trace; `throw e` giữ nguyên; `fillInStackTrace()` làm mới**.

## 18. Các trường hợp JVM đặc biệt

Ngoại lệ do JVM tạo ra có thể khác với `new` do mã ứng dụng gọi. Trên một số JVM/phiên bản/cấu hình, có những tối ưu để **bỏ qua hoặc rút gọn stack trace** của một số exception xảy ra lặp đi lặp lại ở vị trí thường gặp. Trong HotSpot có khái niệm tối ưu thường gọi là **fast-throw** đối với một số implicit exceptions; hành vi thực tế phụ thuộc JVM, cờ vận hành và hoàn cảnh.

Bởi vậy:

- Không dựa vào giả định mọi `NullPointerException` do JVM tự ném đều có đầy đủ stack frames.
- Không dùng một lần chạy để suy luận cứng về tối ưu stack trace của tất cả JVM.
- Không phụ thuộc vào số frame hoặc số dòng cố định cho hệ thống giám sát.
- Một exception `new IllegalArgumentException(...)` thông thường và một implicit VM-thrown exception không nhất thiết được tạo/ghi trace theo cùng đường nội bộ.
- Khi cần phân tích hiệu năng hoặc sai khác theo JVM, hãy xem thông tin của phiên bản JVM thật đang chạy và cấu hình logging/profiling, thay vì thay đổi code nghiệp vụ dựa trên giả thuyết.

**Cảnh báo:** “Stack trace thiếu frame” không tự chứng minh exception bị che giấu hoặc giả mạo. Nó có thể xuất phát từ chế độ tạo Throwable, từ tối ưu, thiếu thông tin debug hoặc từ việc có code sửa trace.

## 19. Vì sao không nên tái sử dụng cùng một instance exception?

Về mặt ngôn ngữ, bạn có thể tạo một object exception rồi ném lại nhiều lần:

```java
static final IllegalStateException SHARED =
        new IllegalStateException("Lỗi dùng chung");

static void run() {
    throw SHARED;
}
```

Đây là **lớp/phương thức minh họa chưa đầy đủ**. Vấn đề: `SHARED` được tạo khi class khởi tạo, nên stack trace có thể phản ánh **điểm khởi tạo static field**, không phản ánh lần gọi `run()` cụ thể. Nếu cùng object được ném ở nhiều luồng hoặc nhiều yêu cầu, thông tin lỗi không phân biệt được các lần phát sinh theo call stack mới.

Điều này còn có thể gây rủi ro khi code khác thay đổi suppressed exceptions hoặc stack trace của cùng object và nhiều luồng đọc chung.

Trong đa số ứng dụng:

- **Tạo exception mới cho mỗi lần thất bại thực sự** để có dấu vết phù hợp.
- Để lỗi lan truyền tự nhiên bằng `throw e` khi cần bảo toàn object gốc.
- Nếu cần thêm ngữ cảnh ở tầng khác, cân nhắc wrapper có `cause` thay vì dùng lại một exception static.
- Không biến exception object thành nơi tích lũy trạng thái của nhiều request độc lập.

Một số framework hoặc thư viện tối ưu đặc thù có thể cố ý tái sử dụng exception không stack trace; đó là lựa chọn cần cân nhắc về chẩn đoán và hiệu năng, không phải mẫu mặc định cho code nghiệp vụ.

## 20. Kiểm tra thời điểm ghi trace bằng test ổn định

Nếu viết bài test về stack trace, tránh kiểm tra một chuỗi đầy đủ chứa số dòng và tên tệp, vì chi tiết dễ thay đổi. Thay vào đó, với một exception được tạo chủ động và có writable trace, kiểm tra **tên phương thức đầu tiên** hoặc **identity** của object theo hợp đồng của ví dụ.

Ví dụ **`TraceAssertionsDemo.java`**:

```java
public class TraceAssertionsDemo {
    static IllegalStateException make() {
        return new IllegalStateException("Lỗi");
    }

    static void relay(IllegalStateException e) {
        throw e;
    }

    public static void main(String[] args) {
        IllegalStateException problem = make();

        try {
            relay(problem);
            throw new AssertionError("Đã không ném lỗi");
        } catch (IllegalStateException e) {
            if (e != problem) {
                throw new AssertionError("Đã đổi object");
            }

            StackTraceElement[] frames = e.getStackTrace();
            if (frames.length == 0
                    || !"make".equals(frames[0].getMethodName())) {
                throw new AssertionError("Sai thời điểm ghi trace");
            }

            System.out.println("PASS: tạo ở make, rethrow không làm mới");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 TraceAssertionsDemo.java
java TraceAssertionsDemo
```

**Stdout chính xác** với Throwable thông thường:

```text
PASS: tạo ở make, rethrow không làm mới
```

Bài test sử dụng `throw new AssertionError(...)` để biểu diễn kết quả sai nên **không phụ thuộc cờ `-ea`** của lệnh `assert`. Việc kiểm tra mảng frame rỗng khiến test thất bại có thông báo rõ ràng khi gặp môi trường không phù hợp giả thiết writable trace của ví dụ.

Trong test tích hợp tổng quát trên nhiều JVM, hãy cân nhắc mức độ kiểm chứng cần thiết: không nên phụ thuộc frame đầu cụ thể của VM-thrown exception hoặc tính ổn định của format `printStackTrace()`.

## 21. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Mỗi lần `throw e` đều ghi stack trace ở dòng `throw`.” | Với Throwable thông thường, `throw e` ném object đã có, không tự làm mới trace. |
| “`throw new E(...)` chứng minh `throw` tự chụp trace.” | Trong biểu thức đó, việc `new` tạo Throwable ngay trước `throw` là nguyên nhân thông thường. |
| “`getStackTrace()` ghi lại call stack tại lúc đọc.” | Nó trả dữ liệu trace trong object; không tự gọi `fillInStackTrace()`. |
| “`printStackTrace()` tạo trace mới.” | Nó in thông tin đang có, không phải thao tác làm mới. |
| “`fillInStackTrace()` tạo object mới.” | Nó trả về chính Throwable và có thể cập nhật trace của object hiện tại. |
| “Rethrow làm mất trace gốc.” | `throw e` thông thường giữ trace gốc; wrapper mới có trace riêng và có thể giữ nguyên nhân. |
| “`setStackTrace` là ảnh chụp call stack hiện tại.” | Nó đặt mảng frame do caller cung cấp, không tự chụp current stack. |
| “Sửa phần tử của mảng `getStackTrace()` sửa luôn exception.” | API trả bản sao mảng; muốn đặt trace dùng `setStackTrace`. |
| “Mọi Throwable luôn có ít nhất một frame.” | Có thể rỗng do writableStackTrace=false hoặc hành vi JVM đặc biệt. |
| “Stack trace là lịch sử mọi method từng chạy.” | Nó là dữ liệu tại một thời điểm, không phải event log theo thời gian. |
| “Cause và suppressed dùng chung trace của wrapper.” | Mỗi object có trace riêng, nếu có. |
| “Tên tệp và số dòng trong stack trace luôn cố định.” | Chúng có thể đổi do source, thông tin debug, JVM và các cơ chế khác. |
| “Tạo exception trước để tái sử dụng giúp biết mọi vị trí ném.” | Trace có thể chỉ vị trí **tạo ban đầu**, gây chẩn đoán sai về vị trí ném sau. |
| “Tắt stack trace không ảnh hưởng xử lý lỗi.” | Có thể vẫn ném/bắt object, nhưng mất thông tin chẩn đoán quan trọng. |

## 22. Câu hỏi tự kiểm tra

**Câu 1.** `Exception e = new Exception("x");` ở phương thức A, rồi `throw e` ở B. Stack trace thường bắt đầu từ đâu?  
**Đáp án:** Từ thời điểm object được tạo/điền trace, thường là phương thức A, không tự đổi thành B vì `throw e`.

**Câu 2.** `catch (Exception e) { throw e; }` có tự khởi tạo một exception mới không?  
**Đáp án:** Không. Nó ném lại cùng object nếu `e` không bị gán sang object khác.

**Câu 3.** `e.fillInStackTrace()` khác `e.printStackTrace()` thế nào?  
**Đáp án:** `fillInStackTrace()` yêu cầu cập nhật stack trace của object (nếu hỗ trợ), còn `printStackTrace()` in thông tin trace hiện tại ra stream.

**Câu 4.** Lệnh `new ServiceException("...", cause)` có làm trace của `cause` trở thành trace của wrapper không?  
**Đáp án:** Không. Wrapper là object mới có trace riêng tại nơi tạo; `cause` giữ trace của nó.

**Câu 5.** `getStackTrace()` trả mảng rỗng thì đọc `[0]` được không?  
**Đáp án:** Không. Cần kiểm tra `length > 0`; Throwable có thể không lưu frame.

**Câu 6.** Sau khi lấy `StackTraceElement[] a = e.getStackTrace()`, thay `a[0]` có tự thay đổi object không?  
**Đáp án:** Không. `getStackTrace()` trả bản sao của mảng stack trace.

**Câu 7.** `setStackTrace(...)` có phải cách an toàn để lấy đường gọi hiện tại không?  
**Đáp án:** Không. Nó thay thông tin bằng mảng được truyền vào; để quan sát current stack, có `StackWalker` hoặc API thread phù hợp.

**Câu 8.** Với `try-with-resources`, exception ở `close()` có stack trace riêng không?  
**Đáp án:** Thông thường có nếu là Throwable được tạo tại `close()`. Khi lỗi công việc chính cũng xảy ra, lỗi đóng được giữ ở `getSuppressed()` của primary.

**Câu 9.** Có thể tạo Throwable nhưng không thu stack trace không?  
**Đáp án:** Có. Lớp con có thể dùng constructor với `writableStackTrace=false`; một số cơ chế đặc biệt của JVM cũng có thể làm trace trống hoặc thiếu frame.

**Câu 10.** Nếu cùng một exception instance được ném lại ở hai request, hai lần ném có tự tạo hai dấu vết riêng không?  
**Đáp án:** Không. Nếu không refresh hoặc thay trace, cùng object giữ thông tin cũ. Điều này khiến việc tái sử dụng một exception instance chung thường không thích hợp cho chẩn đoán.

**Câu 11.** Vì sao kiểm thử exact `Exception.java:123` là mong manh?  
**Đáp án:** Số dòng, tên tệp, debug info và cách runtime trình bày trace có thể thay đổi. Hãy xác nhận đặc điểm ổn định hơn theo phạm vi test.

**Câu 12.** `Thread.currentThread().getStackTrace()` có phải chính mảng của một exception đã tạo trước không?  
**Đáp án:** Không. Nó quan sát ngăn xếp thực thi của thread; exception lưu thông tin riêng từ thời điểm capture.

## 23. Checklist thực hành

Khi cần giải thích một stack trace trong dự án Java:

1. Xác định exception được **tạo** tại đâu; phân biệt `throw new ...` với `throw existing`.
2. Kiểm tra có **rethrow** qua `catch` hay các tầng chuyển tiếp không.
3. Tìm xem mã có gọi `fillInStackTrace()` hoặc `setStackTrace()` làm thay đổi dữ liệu chẩn đoán không.
4. Nếu có **wrapper**, kiểm tra `getCause()` để truy vị trí tạo exception gốc.
5. Nếu có **try-with-resources**, kiểm tra `getSuppressed()` để tìm lỗi cleanup và trace riêng của nó.
6. Không bỏ qua khả năng **mảng trace rỗng**, thiếu frame hoặc writable stack trace bị vô hiệu hóa.
7. Không nhầm `printStackTrace()` (thời điểm in) với thời điểm ghi thông tin vào object.
8. Không dựa trên wording message hoặc số dòng làm cơ sở logic nghiệp vụ.
9. Nếu cần thêm ngữ cảnh, ưu tiên logging rõ ràng và wrapper với `cause` thay vì ghi đè trace gốc.
10. Nếu cần current stack, cân nhắc `StackWalker` hoặc API thread thay vì đọc exception được tạo trước.
11. Nếu lỗi do JVM tự phát sinh, thận trọng với khả năng tối ưu và cấu hình của JVM.
12. Trong kiểm thử, khẳng định hành vi có ý nghĩa và cân nhắc độ ổn định giữa các JVM, phiên bản và chế độ chạy.

## 24. Ghi nhớ trọng tâm

**Với `Throwable` thông thường, stack trace được ghi khi đối tượng exception được khởi tạo, không tự được ghi lại mỗi khi có `throw e`.** Lệnh `throw new E(...)` trông như ghi tại chỗ ném vì object được tạo ngay trong biểu thức ném. `throw e` giữ object và trace hiện có; `fillInStackTrace()` có thể chủ động cập nhật trace, còn wrapper mới có trace tại nơi tạo và giữ exception cũ thông qua `cause`.

`getStackTrace()` và `printStackTrace()` là hoạt động **đọc/in**, không phải cơ chế chụp lại stack hiện tại. Khi trace bị vô hiệu hóa, được sửa hoặc chịu tối ưu JVM, nó có thể rỗng hoặc thiếu những frame người lập trình mong đợi.

Để chẩn đoán chính xác, luôn tách ba câu hỏi: **Exception được tạo/ghi trace lúc nào? Object đã được ném hoặc ném lại ở đâu? Thông tin được đọc hoặc in lúc nào?** Trả lời đúng ba câu này giúp nhận diện nguyên nhân gốc mà không nhầm vị trí quan sát với vị trí phát sinh lỗi.
