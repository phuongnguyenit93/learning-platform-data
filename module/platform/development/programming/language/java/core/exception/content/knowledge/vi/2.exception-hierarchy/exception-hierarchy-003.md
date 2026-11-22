# Error và VirtualMachineError trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Đặt `Error` và `VirtualMachineError` đúng vị trí trong cây `Throwable`.
- Phân biệt `Error` với `Exception`/`RuntimeException` và hiểu vì sao `Error` thuộc nhóm *unchecked*.
- Nhận diện các loại `VirtualMachineError` phổ biến, nguyên nhân thường gặp và phạm vi ảnh hưởng của chúng.
- Biết giới hạn của `catch`, `finally`, cơ chế báo lỗi không được bắt và lựa chọn xử lý an toàn khi tài nguyên JVM gặp sự cố.
- Phân tích một tình huống cụ thể mà không nhầm “lỗi nghiêm trọng” với “JVM chắc chắn đã dừng”.

Các lớp trong bài thuộc `java.lang`, không cần `import`.

## 2. Vị trí trong hệ phân cấp ngoại lệ

`Throwable` là kiểu gốc của những đối tượng có thể được `throw` và `catch` trong Java. Hai nhánh quan trọng của nó là `Exception` và `Error`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   └── java.lang.RuntimeException
    │       └── ... (các ngoại lệ không kiểm tra khác)
    └── java.lang.Error
        ├── java.lang.AssertionError
        ├── java.lang.LinkageError
        │   ├── java.lang.NoClassDefFoundError
        │   └── java.lang.ExceptionInInitializerError
        └── java.lang.VirtualMachineError (abstract)
            ├── java.lang.InternalError
            │   └── java.util.zip.ZipError
            ├── java.lang.OutOfMemoryError
            ├── java.lang.StackOverflowError
            └── java.lang.UnknownError
```

Đây là **sơ đồ các nhánh tiêu biểu**, không phải danh sách đầy đủ tất cả lớp con của `Error`. Bốn lớp con **trực tiếp** của `VirtualMachineError` trong Java 17 là `InternalError`, `OutOfMemoryError`, `StackOverflowError` và `UnknownError`. `ZipError` là ví dụ về lớp con **gián tiếp** thông qua `InternalError`.

Quan hệ “là một” vận hành theo kế thừa:

- Mỗi `OutOfMemoryError` đều là một `VirtualMachineError`, `Error` và `Throwable`.
- Mỗi `AssertionError` đều là một `Error`, nhưng không phải `VirtualMachineError`.
- Một `IOException` thuộc nhánh `Exception`, không thuộc nhánh `Error`.

### `Error` có phải checked exception không?

Không. Trong kiểm tra ngoại lệ lúc biên dịch, `Error` và mọi lớp con được coi là *unchecked*, tương tự `RuntimeException`. Trình biên dịch không buộc phương thức khai báo `throws OutOfMemoryError` và không buộc người gọi viết `catch`.

Điều này **không có nghĩa** lỗi không thể bị bắt; `catch (Error e)` hoặc `catch (Throwable t)` vẫn khớp về mặt cú pháp và kiểu. Nó có nghĩa Java không yêu cầu lập trình viên xử lý chúng bằng cơ chế checked exception, vì đa số tình huống không thể sửa đúng ở tầng nghiệp vụ.

## 3. `Error`: ý nghĩa và ranh giới với `Exception`

Theo hợp đồng của Java API, `Error` biểu thị những vấn đề nghiêm trọng mà một ứng dụng thông thường không được kỳ vọng sẽ cố bắt để tiếp tục như không có chuyện gì xảy ra. Không phải mọi `Error` đều phát sinh từ bộ máy JVM bị hỏng.

| Nhóm | Ví dụ | Ý nghĩa thông thường | Hướng xử lý |
| --- | --- | --- | --- |
| Checked `Exception` | `IOException`, `SQLException` | Sự cố mà mã gọi thường được yêu cầu xét xử lý/khai báo | Bắt, khôi phục, trả lỗi hoặc truyền tiếp phù hợp |
| `RuntimeException` | `IllegalArgumentException`, `NullPointerException` | Lỗi sử dụng API, trạng thái hoặc bất biến của chương trình | Sửa lỗi nguồn; bắt ở ranh giới cần thiết |
| `Error` không thuộc `VirtualMachineError` | `AssertionError`, `NoClassDefFoundError` | Vi phạm giả định hoặc sự cố liên kết/nạp lớp | Sửa cấu hình, dependency hoặc lỗi chương trình |
| `VirtualMachineError` | `OutOfMemoryError`, `StackOverflowError` | JVM gặp sự cố nội tại hoặc cạn tài nguyên cần thiết | Thu thập bằng chứng, khắc phục nguyên nhân, đánh giá khả năng tiếp tục tiến trình |

**Hai điểm dễ nhầm:**

1. `NoClassDefFoundError` không phải `ClassNotFoundException`. Lỗi đầu thuộc `LinkageError → Error`; ngoại lệ sau thuộc `Exception` và là checked exception. Chúng có tình huống phát sinh và giao diện xử lý khác nhau.
2. `AssertionError` thường phát sinh từ một lệnh `assert` bị vi phạm (khi assertion được bật), hoặc do mã chủ động tạo. Nó là `Error` nhưng bản thân nó không chứng minh JVM đã cạn bộ nhớ hay gặp lỗi nội tại.

Không nên tự tạo `new Error(...)` hay `new OutOfMemoryError(...)` để mô tả dữ liệu không hợp lệ, tài khoản không tồn tại hoặc giao dịch bị từ chối. Hãy dùng kiểu ngoại lệ biểu diễn đúng lỗi nghiệp vụ/lập trình.

## 4. `VirtualMachineError` là gì?

Khai báo lớp trong Java 17:

```java
public abstract class VirtualMachineError extends Error
```

Lớp này dùng để báo JVM bị hỏng hoặc không còn tài nguyên cần thiết để tiếp tục hoạt động bình thường. Nó là **abstract**, vì vậy thông thường bạn làm việc với các lớp con cụ thể.

| Lớp con trực tiếp | Ý nghĩa | Nguồn gốc thường gặp / hướng điều tra |
| --- | --- | --- |
| `OutOfMemoryError` | JVM không cấp phát được bộ nhớ/tài nguyên theo yêu cầu | Heap đầy, giữ tham chiếu quá lâu, Metaspace hoặc giới hạn bộ nhớ/tài nguyên khác; cần xem thông điệp và môi trường |
| `StackOverflowError` | Ngăn xếp thực thi của một luồng bị tràn | Đệ quy vô hạn, đệ quy quá sâu, vòng gọi hàm lặp lại |
| `InternalError` | JVM báo lỗi nội bộ bất ngờ | Đối chiếu phiên bản JDK/JVM, native library, log JVM; có thể cần báo lỗi cho nhà cung cấp |
| `UnknownError` | JVM báo lỗi nghiêm trọng nhưng không xác định được bản chất cụ thể | Phân tích thông tin sự cố và log JVM; không phỏng đoán từ riêng tên lớp |

### 4.1. `OutOfMemoryError`

Thông điệp lỗi cung cấp gợi ý rất quan trọng, nhưng **không có một thông điệp chuẩn duy nhất cho mọi JVM**. Trên HotSpot/JDK phổ biến, có thể gặp:

- `Java heap space`: vùng heap không đáp ứng yêu cầu cấp phát.
- `GC overhead limit exceeded`: chính sách kiểm tra GC của VM nhận thấy phần lớn thời gian dành cho GC với rất ít bộ nhớ thu hồi được.
- `Metaspace`: không có đủ vùng nhớ cho metadata của lớp.
- `unable to create native thread`: không tạo được luồng hệ điều hành; có thể do giới hạn tài nguyên của tiến trình/hệ thống.

Một `OutOfMemoryError` **không mặc định là “Java heap bị đầy”**. Tùy loại cấp phát và runtime, lỗi có thể liên quan đến bộ nhớ ngoài heap, không gian địa chỉ, giới hạn container hoặc tài nguyên hệ điều hành. Thông điệp cụ thể và JVM đang dùng quyết định hướng chẩn đoán.

Một lần cấp phát quá lớn cũng có thể bị từ chối dù chương trình vẫn có thể thực hiện những công việc khác. Vì thế, nhận định “cứ `OutOfMemoryError` là cả tiến trình ngay lập tức chết” là sai. Tuy nhiên, khi lỗi liên quan đến cạn tài nguyên thật, **không được mặc định trạng thái ứng dụng còn an toàn để phục vụ tiếp**.

### 4.2. `StackOverflowError`

Mỗi luồng có vùng stack cho các lần gọi phương thức, biến cục bộ và các thông tin thực thi cần thiết. Nếu chương trình liên tục đệ quy hoặc tạo chuỗi gọi quá sâu, nhu cầu stack vượt giới hạn và JVM có thể ném `StackOverflowError`.

Ví dụ **chỉ để đọc, không chạy**:

```java
// Ví dụ minh họa sai: không có điều kiện dừng.
static void recurseForever() {
    recurseForever();
}
```

Cách xử lý đúng là tìm điều kiện dừng bị thiếu, giảm độ sâu đệ quy, hoặc đổi thuật toán sang dạng lặp/ngăn xếp dữ liệu khi phù hợp. Tăng kích thước stack chỉ có thể làm thay đổi ngưỡng gặp lỗi, không chữa đệ quy vô hạn.

Một `StackOverflowError` có thể chỉ làm hỏng công việc của **một luồng**, không bắt buộc mọi luồng và toàn bộ JVM dừng ngay. Dù vậy, tiếp tục xử lý yêu cầu thất bại như thành công sẽ che giấu lỗi thuật toán.

### 4.3. `InternalError` và `UnknownError`

Hai lớp này gợi ý vấn đề trong tầng runtime hoặc thao tác mức thấp; rất khó xác định nguyên nhân chỉ từ tên lớp. Khi gặp chúng, cần giữ thông điệp lỗi, stack trace, thông tin JDK, môi trường và các log liên quan. `InternalError` cũng có các lớp con gián tiếp chuyên biệt, chẳng hạn `java.util.zip.ZipError`; đừng khẳng định mọi trường hợp `InternalError` đều là lỗi VM “tự nhiên” mà không xem call site.

## 5. Ví dụ chạy được: kiểm tra quan hệ kế thừa

Tạo file `ErrorHierarchyDemo.java`:

```java
public class ErrorHierarchyDemo {
    public static void main(String[] args) {
        System.out.println("Error parent: "
                + Error.class.getSuperclass().getSimpleName());
        System.out.println("VirtualMachineError parent: "
                + VirtualMachineError.class.getSuperclass().getSimpleName());
        System.out.println("OutOfMemoryError is VirtualMachineError: "
                + VirtualMachineError.class.isAssignableFrom(OutOfMemoryError.class));
        System.out.println("StackOverflowError is Error: "
                + Error.class.isAssignableFrom(StackOverflowError.class));
        System.out.println("AssertionError is VirtualMachineError: "
                + VirtualMachineError.class.isAssignableFrom(AssertionError.class));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ErrorHierarchyDemo.java
java ErrorHierarchyDemo
```

Kết quả chuẩn:

```text
Error parent: Throwable
VirtualMachineError parent: Error
OutOfMemoryError is VirtualMachineError: true
StackOverflowError is Error: true
AssertionError is VirtualMachineError: false
```

`Class.isAssignableFrom(Other.class)` kiểm tra liệu một đối tượng của `Other` có thể gán cho kiểu bên trái hay không. Ví dụ kiểm tra cấu trúc lớp một cách an toàn: **không tạo lỗi tài nguyên thật**.

## 6. Một `Error` không được bắt ảnh hưởng gì đến luồng?

Cơ chế lan truyền ngoại lệ vẫn áp dụng cho `Error`:

1. Khi được ném, JVM tìm `catch` phù hợp từ khung gọi hiện tại rồi đi ngược lên chuỗi lời gọi.
2. `catch (Exception e)` **không bắt** các đối tượng `Error`, vì hai nhánh tách biệt.
3. `catch (Error e)`, `catch (VirtualMachineError e)` (nếu là lớp con của loại này), hoặc `catch (Throwable t)` có thể khớp.
4. Nếu một lỗi thoát ra khỏi `Thread.run()`, cơ chế xử lý lỗi không bắt của luồng (`UncaughtExceptionHandler`) có thể nhận nó. Luồng đó kết thúc, nhưng điều này **không đồng nghĩa** mọi luồng đã kết thúc hoặc JVM buộc dừng.
5. Nếu JVM bị kết thúc đột ngột hoặc không còn tài nguyên, các bước thông thường như log, hook, `finally` hoặc handler **không có bảo đảm tuyệt đối** sẽ chạy và hoàn tất.

### Ví dụ chạy được: handler nhận `AssertionError` ở một luồng

Ví dụ này cố ý dùng `AssertionError` để **minh họa việc lan truyền của `Error` mà không gây cạn tài nguyên JVM**. `AssertionError` không phải `VirtualMachineError`.

Tạo file `UncaughtErrorDemo.java`:

```java
public class UncaughtErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("demo"); },
                "demo-worker"
        );

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println(thread.getName() + ": "
                        + failure.getClass().getSimpleName())
        );

        worker.start();
        worker.join();
        System.out.println("main continues");
    }
}
```

```bash
javac UncaughtErrorDemo.java
java UncaughtErrorDemo
```

Kết quả:

```text
demo-worker: AssertionError
main continues
```

`join()` khiến luồng chính chờ worker kết thúc, nên thứ tự hai dòng in là xác định trong ví dụ. Trong một hệ thống thật, nếu `VirtualMachineError` phát sinh vì thiếu bộ nhớ hoặc lỗi VM, **đừng dựa vào việc handler vẫn có thể cấp phát bộ nhớ, tạo chuỗi hoặc ghi log thành công**.

## 7. Xử lý thực tế: phòng ngừa, chẩn đoán và quyết định phục hồi

### 7.1. Khi thiết kế mã Java

- **Bắt lỗi theo mục đích.** Một ứng dụng thường bắt `Exception` hoặc các kiểu ngoại lệ cụ thể tại ranh giới xử lý có khả năng phục hồi. Tránh `catch (Throwable)` bao trùm rồi trả “thành công” cho yêu cầu.
- **Không nuốt `VirtualMachineError`.** Nếu một lớp hạ tầng đặc biệt phải bắt nó để ghi nhận trạng thái hoặc dọn dẹp tối thiểu, cần ném lại và tuân theo chính sách xử lý sự cố của tiến trình. Mã bắt lỗi chưa chắc chạy an toàn nếu tài nguyên đã cạn.
- **Không retry vô hạn** sau `OutOfMemoryError`/`StackOverflowError`. Retry cùng workload thường lặp lỗi, làm nghẽn hệ thống và che nguyên nhân.
- **Không dùng `System.gc()` như bảo đảm khắc phục `OutOfMemoryError`.** Đây chỉ là lời đề nghị thu gom rác, không đảm bảo thu hồi đủ tài nguyên.
- **Dùng `finally` và try-with-resources cho dọn dẹp bình thường**, nhưng đừng coi chúng là cơ chế phục hồi chắc chắn sau sự cố JVM nghiêm trọng.

Mẫu minh họa cách “bắt để truyền tiếp”, **là mảnh phương thức có thể đặt vào một lớp Java**, không phải chương trình `main` độc lập:

```java
static void executeBoundary(Runnable task) {
    try {
        task.run();
    } catch (VirtualMachineError fatal) {
        // Nếu có cơ chế ghi nhận an toàn và đã kiểm chứng, thực hiện tối thiểu ở đây.
        // Không biến sự cố thành kết quả thành công.
        throw fatal;
    }
}
```

Nếu ranh giới không cần thực hiện thao tác đặc biệt, **không cần thêm `catch` này**: để lỗi tự lan truyền thường đơn giản và an toàn hơn. Đừng dùng mã ví dụ trên như cam kết rằng JVM sẽ tiếp tục hoạt động được.

### 7.2. Khi vận hành ứng dụng

| Triệu chứng | Bằng chứng nên xem | Hướng sửa bền vững |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Dung lượng heap, heap dump, tốc độ cấp phát, đối tượng bị giữ tham chiếu | Sửa leak/giữ dữ liệu quá lâu; giới hạn cache/batch; điều chỉnh bộ nhớ dựa trên đo đạc |
| `OutOfMemoryError` liên quan Metaspace/native thread | Thông điệp đầy đủ, số lớp/class loader, số luồng, giới hạn OS/container | Tìm class loader leak, thread leak hoặc giới hạn tài nguyên |
| `StackOverflowError` | Chuỗi frame lặp trong stack trace, đường đi đệ quy, input gây lỗi | Thêm điểm dừng đúng, sửa vòng gọi, giảm độ sâu hoặc thay thuật toán |
| `InternalError`/`UnknownError` | Toàn bộ thông điệp, stack trace, log VM, phiên bản/bản phân phối JDK, native dependencies | Khoanh vùng runtime/native code; nâng cấp hoặc cung cấp ca tái hiện |

Ở môi trường HotSpot, `-XX:+HeapDumpOnOutOfMemoryError` có thể cấu hình tạo heap dump khi gặp `OutOfMemoryError`; cân nhắc dung lượng đĩa, dữ liệu nhạy cảm và chính sách vận hành. Đây là tùy chọn đặc thù triển khai JVM, không phải điều Java Language Specification bảo đảm cho mọi VM.

Quy trình ứng phó phù hợp là xác định phạm vi sự cố, giữ bằng chứng đủ để chẩn đoán, ngừng hoặc cách ly workload lỗi khi cần, rồi sửa nguyên nhân. Tại hệ thống được giám sát bởi orchestrator/process supervisor, chính sách restart có thể hữu ích sau sự cố tài nguyên nghiêm trọng; **restart không thay thế sửa leak, vô hạn đệ quy hoặc giới hạn cấu hình sai**.

## 8. Các ngộ nhận phổ biến

**“`catch (Exception)` sẽ bắt mọi thứ có thể ném.”** Sai. `Throwable` bao gồm cả `Exception` lẫn `Error`; `catch (Exception)` không bắt `Error`.

**“Mọi `Error` đều do JVM bị lỗi.”** Sai. `AssertionError` có thể là lỗi giả định của ứng dụng; `NoClassDefFoundError` có thể bắt nguồn từ classpath/dependency hoặc khởi tạo lớp thất bại.

**“Có `OutOfMemoryError` thì heap luôn đầy.”** Sai. Tình huống cấp phát, Metaspace, giới hạn thread và bộ nhớ native phải được phân biệt theo thông điệp và môi trường.

**“`StackOverflowError` buộc toàn bộ JVM phải thoát.”** Sai. Lỗi có thể phát sinh trong một luồng; tuy nhiên công việc đó thất bại và nguyên nhân đệ quy cần được sửa.

**“Bắt `VirtualMachineError` rồi thử lại mãi là phục hồi.”** Sai. Việc đó không đảm bảo tài nguyên hoặc trạng thái ứng dụng được phục hồi và có thể làm sự cố nặng thêm.

**“`finally` luôn chạy dù JVM đã chết.”** Sai. `finally` tham gia vào quá trình rời khối lệnh thông thường, nhưng không thể đảm bảo thực thi khi tiến trình/VM kết thúc bất thường.

## 9. Tự kiểm tra

1. **`OutOfMemoryError` có phải checked exception?** Không. Nó kế thừa `VirtualMachineError → Error → Throwable`, thuộc unchecked.
2. **`catch (RuntimeException e)` có bắt `StackOverflowError`?** Không. `StackOverflowError` thuộc nhánh `Error`.
3. **`AssertionError` có thuộc `VirtualMachineError`?** Không. Cả hai đều thuộc `Error` nhưng ở những nhánh khác nhau.
4. **Nếu một worker thread ném `Error` không được bắt, JVM có buộc kết thúc ngay?** Không. Thông thường luồng lỗi kết thúc; việc JVM tiếp tục hay chấm dứt còn phụ thuộc các luồng và tình trạng runtime.
5. **Đọc tên lỗi hay stack trace có đủ chẩn đoán `OutOfMemoryError`?** Không luôn đủ. Cần thông điệp đầy đủ cùng dữ liệu tài nguyên và bối cảnh vận hành.

## 10. Tài liệu chuẩn

- Java SE 17 API — [`Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html).
- Java SE 17 API — [`VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html).
- Java SE 17 API — [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html).
- Java Language Specification 17 — [`11.2 Compile-Time Checking of Exceptions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2).

Nắm được nhánh kế thừa giúp chọn `catch` đúng kiểu; hiểu nguyên nhân giúp chọn cách phục hồi đúng mức. Đối với `VirtualMachineError`, cần đặc biệt ưu tiên chẩn đoán, giữ bằng chứng và khắc phục nguồn gây cạn tài nguyên hoặc lỗi runtime.
