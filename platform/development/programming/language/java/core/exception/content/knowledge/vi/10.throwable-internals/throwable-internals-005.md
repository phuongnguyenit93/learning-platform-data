# `getStackTrace()` và cấu trúc `StackTraceElement` trong Java

> **Chủ đề:** Java Core → Exception → Đối tượng `Throwable`. Phương thức `Throwable.getStackTrace()` cho phép chương trình đọc một mảng `StackTraceElement[]` mô tả những vị trí gọi phương thức gắn với một đối tượng lỗi. Hiểu từng frame, vị trí tạo Throwable, nguồn dữ liệu và giới hạn của stack trace giúp chẩn đoán lỗi chính xác mà không phụ thuộc mù quáng vào số dòng hoặc chuỗi `printStackTrace()`.

## 1. Stack trace là gì?

Khi chương trình Java gọi các phương thức lồng nhau, runtime quản lý các *stack frame* tương ứng với các lần gọi. Một stack trace trên `Throwable` là bản mô tả ngăn xếp liên quan đến thời điểm thông tin trace được **ghi lại**, thường là lúc đối tượng `Throwable` được tạo.

Ví dụ:

```text
main()
  └── runOrder()
        └── parseQuantity()
              └── new NumberFormatException(...)
```

Một bản trace tiêu biểu chứa:

```text
0: OrderApp.parseQuantity(OrderApp.java:18)
1: OrderApp.runOrder(OrderApp.java:10)
2: OrderApp.main(OrderApp.java:29)
```

Đây chỉ là **minh họa**, số dòng thay đổi theo mã nguồn. Frame chỉ số `0` thường gần nhất với điểm ghi nhận trace; các frame sau thể hiện những lời gọi dẫn tới vị trí đó.

Điều cần phân biệt:

- **Call stack đang hoạt động:** ngăn xếp của thread tại một thời điểm.
- **Stack trace của `Throwable`:** thông tin đã được ghi trong đối tượng lỗi. Sau khi ngoại lệ được bắt hoặc ném lại, dữ liệu đó không nhất thiết phản ánh call stack *hiện tại*.
- **Stack trace được in:** dạng văn bản phục vụ con người, ví dụ từ `printStackTrace()`; không giống mảng dữ liệu có cấu trúc lấy bằng `getStackTrace()`.

Stack trace hữu ích cho debugging, ghi log, truy vết tầng gọi và xác định vị trí tạo lỗi, nhưng **không** tự giải thích nguyên nhân nghiệp vụ. Cần kết hợp với thông điệp, `cause`, các suppressed exceptions và ngữ cảnh dữ liệu.

## 2. API cốt lõi: `Throwable.getStackTrace()`

Phương thức công khai:

```java
public StackTraceElement[] getStackTrace()
```

Cách dùng:

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException e) {
    StackTraceElement[] frames = e.getStackTrace();
    for (StackTraceElement frame : frames) {
        System.out.println(frame.getClassName() + "."
                + frame.getMethodName());
    }
}
```

Đây là **mảnh code minh họa** đặt trong method. Không nên xem stdout của đoạn này là cố định, vì stack có thể bao gồm frame thư viện JDK, compiler và cấu trúc gọi thực tế.

Các đặc điểm chính:

1. Kết quả là **mảng `StackTraceElement[]`, không phải `String`**.
2. Mỗi phần tử mô tả một frame: lớp, phương thức, tệp nguồn, dòng mã và một số thông tin bổ sung.
3. Frame đầu tiên (chỉ số `0`) là vị trí trên cùng trong trace được lưu, thường gần nhất với nơi `Throwable` ghi nhận ngăn xếp.
4. Mảng trả về **không phải `null`**, nhưng có thể có **độ dài bằng 0** nếu thông tin stack không khả dụng hoặc đối tượng được cấu hình không lưu trace.
5. `getStackTrace()` trả **bản sao của mảng**: thay phần tử trong mảng trả về không tự thay đổi trace nằm trong `Throwable`.
6. Việc gọi phương thức này **không ném lại exception** và không tự cập nhật nó thành stack của caller hiện tại.
7. Trên các JVM, stack trace có thể thiếu một số frame hoặc thông tin; không nên phụ thuộc vào số lượng hay vị trí frame tuyệt đối trong production.

### 2.1. Vì sao trả về mảng thay vì chuỗi?

Mảng giúp code phân tích một frame mà không phải tách chuỗi hiển thị theo dấu ngoặc, dấu hai chấm hoặc khoảng trắng. Bạn có thể lấy:

- `getClassName()` để biết tên lớp.
- `getMethodName()` để biết phương thức.
- `getFileName()` để biết tên file nguồn khi có thông tin.
- `getLineNumber()` để biết số dòng khi có thông tin.
- `isNativeMethod()` để nhận diện frame của native method.
- Thông tin module/class loader trên Java hiện đại nếu có.

Chuỗi từ `StackTraceElement.toString()` phù hợp để hiển thị và log; các phương thức getter phù hợp hơn khi muốn xử lý dữ liệu có cấu trúc.

## 3. Cấu trúc `StackTraceElement`

`java.lang.StackTraceElement` đại diện cho **một vị trí của một lời gọi** trong stack trace. Một đối tượng không phải exception, không có `getCause()` và không phải là nơi người dùng thực hiện `catch`. Nó là một **phần tử mô tả** trong mảng do `Throwable` cung cấp.

Các API đáng nhớ:

| API trên `StackTraceElement` | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getClassName()` | Tên nhị phân của lớp khai báo phương thức | Có thể bao gồm package, lớp lồng nhau với ký hiệu `$` |
| `getMethodName()` | Tên phương thức tại frame | Constructor thường có dạng `<init>` trong thông tin trace; tên không phải chữ ký đầy đủ |
| `getFileName()` | Tên file nguồn khi có | Có thể trả về `null` |
| `getLineNumber()` | Dòng của vị trí thực thi | Giá trị âm nghĩa là không có số dòng nguồn; không dựa vào số dòng cố định |
| `isNativeMethod()` | Frame có phải phương thức native không | Có thể có frame native không gắn với số dòng Java |
| `getClassLoaderName()` | Tên class loader khi được ghi trong frame | Java 9+; có thể là `null` |
| `getModuleName()` | Tên module khi được ghi trong frame | Java 9+; có thể là `null` |
| `getModuleVersion()` | Phiên bản module khi được ghi trong frame | Java 9+; có thể là `null` |
| `toString()` | Biểu diễn một frame cho người đọc | Không phải định dạng dữ liệu bền vững để parse |
| `equals()`, `hashCode()` | So sánh các frame theo các trường dữ liệu | Dùng khi cần kiểm tra/cấu trúc tập hợp |

**Quan trọng:** `StackTraceElement` là một đối tượng mang thông tin frame; nó không tự chứa toàn bộ stack. Để đọc một trace đầy đủ, cần duyệt **mảng** các phần tử đó.

### 3.1. Giá trị đặc biệt của file và line

Không nên viết:

```java
// Không an toàn nếu file name không có:
String file = frame.getFileName().toUpperCase();
```

Vì `getFileName()` có thể là `null`. Tương tự, `getLineNumber()` có thể âm. Nếu code cần thông tin vị trí:

```java
String file = frame.getFileName();
int line = frame.getLineNumber();

String location = (file != null && line >= 0)
        ? file + ":" + line
        : "Vị trí nguồn không khả dụng";
```

Đây là đoạn minh họa trong method có biến `frame` thích hợp. `line == -2` thường biểu thị frame native theo biểu diễn Java; **kiểm tra `isNativeMethod()`** rõ nghĩa hơn khi cần phân loại native.

### 3.2. `getClassName()` không phải `Class<?>`

`getClassName()` trả về **`String`**, không phải một đối tượng `Class`. Không nhất thiết nên gọi `Class.forName(frame.getClassName())`: việc tải class có thể thất bại, sử dụng sai class loader, hoặc có side effect không cần thiết. Để log/chẩn đoán, chuỗi tên lớp thường là đủ.

### 3.3. Phương thức có thể bị trùng tên

Hai phương thức overload có cùng `getMethodName()` nhưng khác tham số. Một `StackTraceElement` không chứa đầy đủ danh sách parameter types để tự khôi phục chữ ký overload. Nếu cần tìm chính xác overload gây lỗi, kết hợp tên lớp, tên method, file/dòng và mã nguồn tương ứng, hoặc công cụ debug có dữ liệu phong phú hơn.

## 4. Java 17 — ví dụ đầu tiên: đọc ba frame đầu của lỗi

Tạo file **`StackTraceBasicsDemo.java`**:

```java
public class StackTraceBasicsDemo {
    static void leaf() {
        throw new IllegalArgumentException("Số lượng không hợp lệ");
    }

    static void middle() {
        leaf();
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalArgumentException e) {
            StackTraceElement[] frames = e.getStackTrace();
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Frame count >= 3: "
                    + (frames.length >= 3));

            for (int i = 0; i < 3; i++) {
                System.out.println(i + ": "
                        + frames[i].getClassName() + "."
                        + frames[i].getMethodName());
            }
            System.out.println("File đầu: "
                    + frames[0].getFileName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 StackTraceBasicsDemo.java
java StackTraceBasicsDemo
```

**Stdout khi chạy trực tiếp `java StackTraceBasicsDemo` như trên:**

```text
Loại: IllegalArgumentException
Frame count >= 3: true
0: StackTraceBasicsDemo.leaf
1: StackTraceBasicsDemo.middle
2: StackTraceBasicsDemo.main
File đầu: StackTraceBasicsDemo.java
```

Giải thích:

1. `leaf()` **tạo** `IllegalArgumentException` khi chạy `new`, nên frame đầu phản ánh `leaf`.
2. `middle()` là caller của `leaf()`, nên thường đứng sau.
3. `main()` gọi `middle()`, nên là frame kế tiếp.
4. `getFileName()` trả tên file nguồn đã được compiler ghi nhận. Nếu biên dịch theo cấu hình debug/source metadata khác hoặc chạy qua framework/hạ tầng bổ sung, thông tin file và frame có thể khác; đừng kiểm tra chuỗi này như điều kiện nghiệp vụ.
5. Code ví dụ cố tình **không in số dòng** vì thay đổi một dòng trong tệp có thể làm số dòng của stack trace thay đổi.

Trong ứng dụng thực tế, không được giả định luôn tồn tại ba frame. Ví dụ học tập có đường gọi cụ thể nên minh họa ba phần tử; với thư viện hoặc ngoại lệ cấu hình khác, cần kiểm tra `frames.length` trước khi truy cập chỉ số.

### 4.1. Nhớ đọc frame đầu theo đúng ngữ cảnh

Một frame đầu thuộc thư viện Java như `Integer.parseInt` không có nghĩa “lỗi nằm trong JDK”. Nó có thể chỉ là nơi thư viện **phát hiện** và ném lỗi vì input do caller truyền vào. Nên đọc tiếp các frame caller của ứng dụng để tìm nơi input sai được đưa vào.

Ví dụ `NumberFormatException` có thể khởi tạo trong logic parse của thư viện, còn vấn đề thực sự là validation ở tầng gọi. Trace là **manh mối vị trí**, không phải kết luận nguyên nhân cuối cùng.

## 5. `getStackTrace()` đọc dấu vết đã có, không tự ghi dấu vết mới

Với `Throwable` thông thường, constructor tạo exception đồng thời ghi stack trace. Ném lại **chính instance đó** bằng `throw error;` không mặc nhiên ghi lại trace tại vị trí ném, và gọi `getStackTrace()` không chụp call stack hiện tại. Do đó một frame đầu thuộc phương thức tạo exception có thể vẫn xuất hiện ngay cả khi lỗi được bắt ở tầng cao.

~~~java
IllegalStateException error =
        new IllegalStateException("created here");
StackTraceElement[] frames = error.getStackTrace();
if (frames.length > 0) {
    System.out.println(frames[0].getMethodName());
}
~~~

Đây là mảnh minh họa bên trong phương thức, không cam kết tên frame cố định. Khi cần xem **thời điểm ghi và sự khác biệt giữa tạo/throw/rethrow**, xem bài về thời điểm ghi stack trace; khi cần **chủ động cập nhật**, xem bài `fillInStackTrace`. Bài này tập trung đọc mảng frame và các trường của `StackTraceElement`.

## 6. `getStackTrace()` trả bản sao của mảng

Lời gọi:

```java
StackTraceElement[] snapshot = error.getStackTrace();
```

trả **mảng mới** chứa các phần tử `StackTraceElement`. Các đối tượng phần tử là kiểu bất biến; việc thay `snapshot[0]` bằng một object mới chỉ thay mảng bạn giữ, không sửa mảng trace bên trong `error`.

Nếu muốn chủ động thay trace của một `Throwable`, Java có API `setStackTrace(StackTraceElement[])`. API đó cũng xử lý bảo vệ dữ liệu bằng sao chép mảng truyền vào. Nó hữu ích trong một số framework/chẩn đoán đặc biệt, nhưng ít cần với code nghiệp vụ thông thường.

### 6.1. Java 17 — minh họa defensive copy và `setStackTrace()`

Tạo **`StackTraceCopyDemo.java`**:

```java
public class StackTraceCopyDemo {
    public static void main(String[] args) {
        Throwable error = new Throwable("demo");

        StackTraceElement[] snapshot = error.getStackTrace();
        System.out.println("Trước sửa mảng: "
                + snapshot[0].getMethodName());

        snapshot[0] = new StackTraceElement(
                "fake.Wrong", "wrong", "Wrong.java", 1);

        System.out.println("Trong Throwable: "
                + error.getStackTrace()[0].getMethodName());

        StackTraceElement[] synthetic = {
                new StackTraceElement(
                        "demo.Service", "execute", "Service.java", 42)
        };
        error.setStackTrace(synthetic);

        synthetic[0] = new StackTraceElement(
                "other.Class", "changed", "Changed.java", 99);

        System.out.println("Đã đặt trace: "
                + error.getStackTrace()[0]);
        System.out.println("Số frame mới: "
                + error.getStackTrace().length);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StackTraceCopyDemo.java
java StackTraceCopyDemo
```

Stdout:

```text
Trước sửa mảng: main
Trong Throwable: main
Đã đặt trace: demo.Service.execute(Service.java:42)
Số frame mới: 1
```

Thử nghiệm có hai lớp bảo vệ:

1. Sau khi sửa `snapshot[0]`, trace đọc lại từ `error` **vẫn chứa `main`**.
2. Sau `setStackTrace(synthetic)`, việc sửa chính mảng `synthetic` không ảnh hưởng trace đã được đặt.

**Không nên dùng `setStackTrace()` để giả mạo nguồn gốc lỗi trong hệ thống thật**. Ví dụ này chỉ giải thích API và cách sao chép. Các công cụ log và giám sát thường tin các frame, nên việc tùy ý thay dữ liệu có thể làm sai chẩn đoán.

### 6.2. Các ràng buộc của `setStackTrace()`

- `setStackTrace(null)` không hợp lệ.
- Mảng chứa phần tử `null` không hợp lệ.
- Với Throwable có cấu hình **writable stack trace = false**, lời gọi `setStackTrace(...)` không có tác dụng theo hợp đồng API.
- Không nên giả định mảng tự tăng/giảm theo stack hiện tại: trace là dữ liệu gắn với đối tượng `Throwable`.

`StackTraceElement` có constructor công khai cho phép tạo phần tử từ các trường cụ thể, nhưng dựng frame bằng tay **không tạo một lời gọi phương thức thật**. Đây là dữ liệu mô tả, không phải thay đổi call stack JVM.

## 7. Tạo và khám phá một `StackTraceElement` độc lập

Một `StackTraceElement` có thể được tạo thủ công:

```java
new StackTraceElement(
        "example.InventoryService",
        "reserve",
        "InventoryService.java",
        27);
```

Bốn tham số lần lượt là tên lớp khai báo, tên phương thức, tên file nguồn và dòng nguồn. Có constructor mở rộng trên Java hiện đại chứa thông tin class loader/module, nhưng khi học Java Core thường chỉ cần bốn trường này trước.

### 7.1. Java 17 — khám phá getter của một frame

Tạo **`StackTraceElementFieldsDemo.java`**:

```java
public class StackTraceElementFieldsDemo {
    public static void main(String[] args) {
        StackTraceElement frame = new StackTraceElement(
                "example.InventoryService",
                "reserve",
                "InventoryService.java",
                27);

        System.out.println("Class: " + frame.getClassName());
        System.out.println("Method: " + frame.getMethodName());
        System.out.println("File: " + frame.getFileName());
        System.out.println("Line: " + frame.getLineNumber());
        System.out.println("Native: " + frame.isNativeMethod());
        System.out.println("Formatted: " + frame);

        StackTraceElement nativeFrame = new StackTraceElement(
                "example.NativeBridge", "callNative", null, -2);
        System.out.println("Native frame: "
                + nativeFrame.isNativeMethod());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StackTraceElementFieldsDemo.java
java StackTraceElementFieldsDemo
```

Stdout:

```text
Class: example.InventoryService
Method: reserve
File: InventoryService.java
Line: 27
Native: false
Formatted: example.InventoryService.reserve(InventoryService.java:27)
Native frame: true
```

Ví dụ này tự tạo frame để đầu ra không phụ thuộc line number thực tế của file Java. Nó chứng minh cách đọc các trường API, **không khẳng định** một phương thức `InventoryService.reserve()` thật đã chạy.

### 7.2. Native frame và số dòng âm

Trong cấu trúc frame, một số dòng âm có ý nghĩa không có line source bình thường. Trường hợp `lineNumber == -2` được sử dụng để biểu diễn native method; `isNativeMethod()` trả `true`. Khi in `toString()`, native frame có thể được hiển thị theo dạng `Native Method`.

Với số dòng không khả dụng, hãy hiển thị “không rõ” thay vì coi nó là dòng -1 của file nguồn. Nếu dùng dữ liệu trace cho analytics, cần có nhánh xử lý `getFileName() == null` và `getLineNumber() < 0`.

## 8. `printStackTrace()` so với `getStackTrace()`

Cả hai đều liên quan đến stack trace, nhưng mục đích khác nhau.

| API | Kết quả | Khi nên dùng |
| --- | --- | --- |
| `e.printStackTrace()` | In một biểu diễn phục vụ con người ra `System.err` theo mặc định | Chẩn đoán nhanh trong ví dụ nhỏ |
| `e.printStackTrace(PrintStream)` | In ra stream đã chỉ định | Công cụ chuyên dụng, tương thích API cũ |
| `e.printStackTrace(PrintWriter)` | In ra writer đã chỉ định | Tích hợp nguồn xuất khác |
| `e.getStackTrace()` | Trả mảng `StackTraceElement[]` | Duyệt/filter frame, phân tích cấu trúc |
| `e.getCause()` | Trả nguyên nhân nếu có | Chẩn đoán chuỗi exception wrapping |
| `e.getSuppressed()` | Trả mảng exception phụ nếu có | Chẩn đoán lỗi thứ cấp, đặc biệt từ try-with-resources |

`getStackTrace()` chỉ trả stack của **chính Throwable đó**. Nó không tự nối các frame của `getCause()` hoặc suppressed exceptions thành một mảng duy nhất.

Trong khi đó, `printStackTrace()` mặc định hiển thị thêm chuỗi `Caused by` và những ngoại lệ `Suppressed` theo định dạng của nền tảng. Đó là lý do hai thao tác đôi khi cho cảm giác “lượng thông tin khác nhau”.

### 8.1. Chương trình Java 17 — cause và suppressed không nằm trong cùng mảng

Tạo **`ThrowableTraceRelationsDemo.java`**:

```java
import java.io.IOException;

public class ThrowableTraceRelationsDemo {
    public static void main(String[] args) {
        IOException root = new IOException("Nguồn đọc lỗi");
        IllegalStateException wrapper =
                new IllegalStateException("Không hoàn tất", root);
        wrapper.addSuppressed(new IOException("Đóng thất bại"));

        System.out.println("Wrapper: "
                + wrapper.getClass().getSimpleName());
        System.out.println("Wrapper top: "
                + wrapper.getStackTrace()[0].getMethodName());
        System.out.println("Cause: "
                + wrapper.getCause().getClass().getSimpleName());
        System.out.println("Suppressed: "
                + wrapper.getSuppressed()[0]
                        .getClass().getSimpleName());
        System.out.println("Cause là frame trong mảng? "
                + (wrapper.getStackTrace() instanceof StackTraceElement[]));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ThrowableTraceRelationsDemo.java
java ThrowableTraceRelationsDemo
```

Stdout:

```text
Wrapper: IllegalStateException
Wrapper top: main
Cause: IOException
Suppressed: IOException
Cause là frame trong mảng? true
```

Dòng cuối chứng minh kiểu trả về của `getStackTrace()` là mảng frame, **không phải** danh sách ngoại lệ nguyên nhân; tuy nhiên chỉ biểu thị kiểu bằng `instanceof` nên không nên hiểu đó là phép kiểm tra cause thực tế.

Để hiển thị đầy đủ một báo cáo lỗi, nên log **đối tượng `Throwable`** qua logger phù hợp, hoặc duyệt `getCause()` và `getSuppressed()` nếu đang viết công cụ phân tích cấu trúc. Tránh log chỉ `e.getMessage()` rồi đánh mất những quan hệ cần cho debug.

### 8.2. Không nhầm `getStackTrace()` với chuỗi do logger tạo

Logger có thể thêm timestamp, thread name, correlation id, tên ứng dụng, stack-trace shortening và masking dữ liệu. Mảng `StackTraceElement[]` **không** tự chứa toàn bộ trường này. Do đó để truy vết request, phải truyền context qua logging/tracing thích hợp; chỉ một stack trace không thay thế hệ thống quan sát ứng dụng.

## 9. Hiểu stack trace từ exception được bọc

Xét:

```java
try {
    loadFile();
} catch (java.io.IOException original) {
    throw new IllegalStateException("Không tải được cấu hình", original);
}
```

Đây là mảnh minh họa; `loadFile()` phải tồn tại và khai báo/throw `IOException` thích hợp.

- `original.getStackTrace()` mô tả đường gọi dẫn đến **IOException gốc**.
- Đối tượng `IllegalStateException` được tạo trong handler có **trace riêng**, thường bắt đầu ở vị trí tạo wrapper.
- `wrapper.getCause()` liên kết sang exception gốc.
- `wrapper.getStackTrace()` **không tự chứa toàn bộ frame của original**.
- `printStackTrace()` của wrapper thường có phần `Caused by` để giúp người đọc nhìn cả hai trace, đôi khi rút gọn những frame chung.

Trong hệ thống thực tế, dùng constructor nhận `cause` như `new IllegalStateException("...", original)` thường tốt hơn chỉ sao chép message. Nếu bỏ cause, mối liên kết giữa hai exception sẽ không còn sẵn trong dữ liệu Throwable.

### 9.1. Handler `catch` không chọn theo frame

Một `catch (IOException e)` được chọn theo **kiểu runtime của đối tượng exception đang ném**, không theo tên lớp xuất hiện ở bất kỳ `StackTraceElement` nào. Trace có thể chứa frame của `java.io`, nhưng điều đó không biến `IllegalStateException` thành `IOException`.

Tương tự, một wrapper `IllegalStateException` có `cause` là `IOException` sẽ bị `catch(IllegalStateException)` hoặc `catch(Exception)` bắt, không tự chuyển vào `catch(IOException)`.

## 10. Độ tin cậy và giới hạn của stack trace

Stack trace rất có ích, nhưng nó không phải bản ghi hoàn hảo của mọi sự kiện.

### 10.1. Không được giả định có số dòng ổn định

Số dòng thay đổi khi thêm comment, refactor hoặc tối ưu build. Thông tin debug/source có thể vắng mặt. Kiểm thử tốt thường xác nhận **kiểu exception và kết quả hành vi**; nếu cần kiểm tra frame, kiểm tra tên method/class có ý nghĩa ở phạm vi được kiểm soát, không hardcode `StackTraceElement.toString()` với một line number.

### 10.2. Trace có thể thiếu hoặc rút gọn

Một `Throwable` có thể có trace rỗng nếu thông tin không được cung cấp hoặc bị vô hiệu hóa. JVM cũng có quyền tối ưu một số đường exception. Ví dụ, một số JVM có thể lược bớt stack trace của các exception lặp lại nhiều lần ở các tình huống hiệu năng đặc thù.

Không viết code nghiệp vụ dựa trên `getStackTrace()[0]` mà không kiểm tra `length > 0` nếu dữ liệu đến từ exception bất kỳ.

### 10.3. Trace là dữ liệu của Throwable, không phải ảnh chụp thread hiện tại

Nếu một exception được tạo ở thread A rồi truyền qua queue và xử lý ở thread B, `e.getStackTrace()` thường vẫn biểu diễn vị trí **tạo/capture trước đó**, không phải call stack hiện tại của B. Để quan sát stack của thread đang chạy, có thể dùng `Thread.currentThread().getStackTrace()` hoặc `StackWalker` (Java 9+), nhưng đây là API khác với stack của Throwable.

### 10.4. Stack trace có chi phí

Việc điền stack trace lúc tạo Throwable và lấy/định dạng frame có chi phí CPU/bộ nhớ. Không nên tạo exception hàng triệu lần như cơ chế điều khiển luồng thông thường hoặc gọi `printStackTrace()` ở mỗi vòng lặp hiệu năng cao. Nếu thực sự cần exception nhẹ trong một hot path, đó là tối ưu chuyên biệt phải được đo đạc và cân nhắc hậu quả mất chẩn đoán.

### 10.5. Bảo mật và quyền riêng tư

Tên class/method, đường xử lý, đôi khi tên file nguồn/module có thể tiết lộ cấu trúc ứng dụng. Trong hệ thống API công khai, không nên trả toàn bộ stack trace cho người dùng cuối. Hãy log có kiểm soát ở phía server, dùng correlation id cho người dùng và lọc thông tin nhạy cảm theo chính sách logging. Stack trace cũng không bảo đảm chứa giá trị tham số; không được suy đoán input chỉ từ tên frame.

## 11. Thực hành viết bộ lọc frame đúng cách

Giả sử muốn tìm frame đầu tiên thuộc package ứng dụng. **Không** dựa vào vị trí thứ hai hay thứ ba một cách tuyệt đối; duyệt đến khi gặp frame phù hợp.

Ví dụ hàm tiện ích:

```java
static StackTraceElement findAppFrame(
        Throwable error, String packagePrefix) {
    for (StackTraceElement frame : error.getStackTrace()) {
        if (frame.getClassName().startsWith(packagePrefix)) {
            return frame;
        }
    }
    return null;
}
```

Đây là method minh họa phải đặt trong lớp; không chứa `main`. Kết quả có thể là `null` nếu không có frame khớp.

Một số lưu ý:

- Prefix `"com.example"` có thể khớp cả `com.exampleOther`. Nếu muốn giới hạn package chính xác, cân nhắc `"com.example."` cùng xử lý lớp ở package gốc.
- Tên lớp có thể là lớp nội bộ/lambda với tên compiler sinh ra; không đảm bảo naming ổn định giữa build.
- Frame stack có thể thiếu metadata, nhưng `getClassName()` là thông tin cốt lõi của frame.
- Không dùng việc tìm frame làm logic phân quyền, chống gian lận hoặc xác thực caller. Mã có thể thay trace bằng `setStackTrace()` và môi trường runtime còn nhiều yếu tố khác.

### 11.1. Dùng `StackWalker` khi cần stack đang chạy

Kể từ Java 9, `java.lang.StackWalker` cung cấp API truy cập stack **hiện hành** theo luồng xử lý, phù hợp với một số công cụ profiling hoặc tracing. Nó không phải bản thay thế trực tiếp cho `Throwable.getStackTrace()`:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Xem vị trí và đường gọi khi lỗi được ghi vào Throwable | `throwable.getStackTrace()` |
| In lỗi cùng cause/suppressed phục vụ debug | Logger ghi `Throwable`, hoặc `printStackTrace()` khi học tập |
| Lấy stack hiện tại của thread | `Thread.currentThread().getStackTrace()` hoặc `StackWalker` |
| Theo dõi luồng request qua nhiều thread/service | Distributed tracing, correlation id, logging context |
| Hiểu nguyên nhân nghiệp vụ của một exception | Kết hợp kiểu, thông điệp, cause, dữ liệu đầu vào, log |

Đừng trộn lẫn một stack trace **đã capture** với call stack **đang hoạt động**.

## 12. Các lỗi lập trình dễ mắc

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `e.getStackTrace().toString()` rồi mong ra các frame | Đây là `toString()` của **mảng**, không tự nối phần tử thành stack trace đọc được | Duyệt từng frame, dùng `Arrays.toString(...)` nếu chỉ cần hiển thị đơn giản, hoặc logger ghi Throwable |
| Luôn truy cập `getStackTrace()[0]` | Mảng có thể rỗng | Kiểm tra độ dài trước |
| Hardcode line number trong test | Dòng thay đổi theo mã nguồn/compiler | Test kiểu/hành vi, hoặc frame method/class cần thiết |
| Cho rằng `getStackTrace()` luôn trả stack của dòng `throw` gần nhất | Trace thường được capture lúc tạo Throwable, không tự refresh mỗi lần rethrow | Hiểu `fillInStackTrace()` và vòng đời đối tượng |
| Sửa `frames[0]` rồi kỳ vọng Throwable thay đổi | Mảng trả về là defensive copy | Chỉ dùng `setStackTrace()` khi thật sự có lý do chẩn đoán đặc biệt |
| Xem `getStackTrace()` là danh sách cause | Trace là mảng **frame**, không phải chuỗi Throwable | Dùng `getCause()` và `getSuppressed()` riêng |
| Bắt exception bằng tên class xuất hiện trong frame | Handler `catch` dựa vào kiểu thực tế của exception đang ném | Dùng loại exception phù hợp |
| Gọi `getFileName().length()` không kiểm tra | File name có thể `null` | Kiểm tra `null` |
| Dùng số dòng âm như vị trí file thực | Âm biểu thị không có số dòng hợp lệ hoặc frame native | Dùng `isNativeMethod()` và fallback |
| Dùng tên method để xác định overload chính xác | Không có parameter signature trong `StackTraceElement` | Kết hợp file/dòng, mã nguồn, debugger |
| Log đầy đủ stack ra HTTP response | Có thể làm lộ cấu trúc nội bộ ứng dụng | Giữ log ở môi trường được kiểm soát |
| Nuốt exception chỉ vì đã in stack | In lỗi không phải phục hồi hay rollback | Truyền failure, xử lý hoặc ném lại theo hợp đồng |

### 12.1. Đừng quá phụ thuộc vào `printStackTrace()`

Trong dự án thật, một logger có hỗ trợ exception thường phù hợp hơn vì đi kèm mức log, timestamp, request id, cấu hình định dạng và vị trí lưu. Nhưng nếu logger chỉ được truyền `e.getMessage()`, bạn có thể **đánh mất stack trace**; cần dùng API logger cho phép truyền Throwable theo đúng framework.

Đây là nguyên tắc thiết kế, không phải lời khuyên dùng một thư viện log cụ thể.

## 13. Các câu hỏi thường gặp

### 13.1. `getStackTrace()` có làm exception bị bắt hoặc ném đi không?

Không. Nó chỉ đọc dữ liệu stack trace đã gắn với đối tượng. Muốn ném, dùng `throw`; muốn bắt, dùng `try/catch`.

### 13.2. `getStackTrace()` trả `null` không?

Theo hợp đồng API, nó trả một mảng `StackTraceElement[]`, có thể là mảng **rỗng** nếu không có thông tin. Vì thế kiểm tra `frames.length` thay vì so sánh `frames == null` trong code Java thông thường.

### 13.3. Vì sao frame đầu là `parseInt` thay vì method ứng dụng?

Bởi một exception được tạo ở nơi thư viện phát hiện lỗi. Đọc **các frame tiếp theo** để tìm lời gọi từ ứng dụng đã cung cấp dữ liệu không hợp lệ.

### 13.4. `Throwable.getStackTrace()` và `Thread.getStackTrace()` khác nhau thế nào?

Một bên lấy trace **đã lưu trong đối tượng Throwable**, một bên lấy stack của thread tương ứng tại lúc yêu cầu. Hai mảng có thể khác về thời điểm, thứ tự và nội dung.

### 13.5. `setStackTrace()` có sửa call stack JVM không?

Không. Nó thay **dữ liệu mô tả** lưu trong Throwable, không đẩy/pop frame của thread. Không dùng nó để điều khiển thực thi.

### 13.6. Một frame có thể không có tên tệp hoặc số dòng không?

Có. `getFileName()` có thể là `null`, `getLineNumber()` có thể âm. Không phụ thuộc rằng mọi frame đều trỏ được về một dòng nguồn trên máy phát triển.

### 13.7. `getStackTrace()` có hiển thị suppressed exception không?

Nó chỉ trả trace của đối tượng hiện tại. Muốn xem suppressed, gọi `getSuppressed()`; muốn xem nguyên nhân, gọi `getCause()`. Dạng in của `printStackTrace()` thường kết hợp các phần này để dễ đọc.

### 13.8. Mỗi lần `throw` một exception cũ, trace có tự thay đổi không?

Không mặc định. `throw e;` giữ cùng đối tượng và dữ liệu đã capture. Nếu tạo wrapper mới có cause là `e`, wrapper có trace riêng.

## 14. Bài tập có đáp án định hướng

### Bài 1 — Dự đoán thứ tự frame

Chạy `StackTraceBasicsDemo`, đổi thành chuỗi `main → outer → middle → leaf`. Dự đoán các frame đầu tiên. **Định hướng:** frame gần điểm tạo exception đứng trước; các caller dần xuất hiện phía sau.

### Bài 2 — Rethrow và capture

Trong `RethrowTraceDemo`, chuyển lời gọi `saved.fillInStackTrace()` sang một phương thức `refresh(saved)` rồi xem `getStackTrace()[0].getMethodName()` là gì. **Định hướng:** khi stack được chụp lại bên trong `refresh`, frame đầu phản ánh vị trí mới, không phải `create`.

### Bài 3 — Bản sao mảng

Trong `StackTraceCopyDemo`, tạo hai mảng bằng hai lần gọi `getStackTrace()`. Thay phần tử `0` trong mảng thứ nhất; mảng thứ hai và giá trị đọc lại có bị thay không? **Không**, vì các mảng là các snapshot riêng về tham chiếu phần tử.

### Bài 4 — Frame không có vị trí nguồn

Tạo `new StackTraceElement("a.B", "run", null, -1)`. In `getFileName()` và `getLineNumber()`. Viết hàm hiển thị fallback “unknown source” khi file hoặc line thiếu; tránh `NullPointerException`.

### Bài 5 — Cause và suppressed

Viết một `IOException original`, một `IllegalStateException wrapper` có `cause` là `original`, rồi thêm một suppressed `IOException` vào wrapper. In class name của mỗi đối tượng qua API phù hợp. **Định hướng:** một trace frame không phải một exception cause.

### Bài 6 — Kiểm thử ổn định

Tạo JUnit test xác nhận `getStackTrace()` có ít nhất một frame trong một tình huống được kiểm soát. Tránh assert giá trị dòng; có thể kiểm tra `getClassName()`/`getMethodName()`. Với exception tùy biến bị tắt writableStackTrace, test cần nhận mảng rỗng theo hợp đồng.

### Bài 7 — Thiết kế log

Một REST API gặp lỗi dữ liệu. So sánh: trả toàn bộ stack trace cho người dùng; trả mã lỗi cùng correlation id và log Throwable phía server. **Định hướng:** giải pháp thứ hai giúp chẩn đoán mà ít lộ cấu trúc nội bộ hơn.

## 15. Checklist sử dụng `getStackTrace()` đúng cách

- [ ] Tôi biết mảng trả về chứa **`StackTraceElement`**, không phải các đối tượng `Throwable` chưa?
- [ ] Tôi hiểu thứ tự frame từ điểm capture đến các caller không?
- [ ] Tôi đã phân biệt thời điểm **tạo/capture** exception với thời điểm `throw`/`catch` chưa?
- [ ] Tôi có kiểm tra `frames.length` trước khi đọc phần tử `0` không?
- [ ] Tôi tránh phụ thuộc tuyệt đối vào file/line/method name giữa các build/runtime chứ?
- [ ] Tôi đã xử lý `getFileName() == null` và `getLineNumber() < 0` chưa?
- [ ] Tôi nhớ `getStackTrace()` trả mảng sao chép, không thể sửa Throwable bằng thay phần tử mảng không?
- [ ] Nếu dùng `setStackTrace()`, tôi có hiểu đó là thay dữ liệu chẩn đoán, không thay call stack JVM không?
- [ ] Tôi đã phân biệt frame, `cause` và suppressed exception chưa?
- [ ] Tôi hiểu `printStackTrace()` phù hợp quan sát trực tiếp, còn `getStackTrace()` phù hợp xử lý dữ liệu có cấu trúc chưa?
- [ ] Tôi không dùng trace làm cơ chế kiểm tra quyền, xác minh caller hay điều kiện thành công của nghiệp vụ chứ?
- [ ] Việc ghi log/hiển thị stack đã phù hợp yêu cầu bảo mật và quyền riêng tư chưa?
- [ ] Tôi có test cả trường hợp trace bình thường và trace rỗng/thiếu metadata nếu API nhận lỗi bên ngoài không?

**Ghi nhớ:** `Throwable.getStackTrace()` trả một mảng các frame `StackTraceElement` mô tả đường gọi được ghi nhận của **chính đối tượng Throwable**. Đọc từng frame bằng `getClassName()`, `getMethodName()`, `getFileName()`, `getLineNumber()` và `isNativeMethod()`; kiểm tra mảng rỗng/metadata thiếu; phân biệt trace của wrapper với `cause`/`suppressed`. Stack trace là công cụ chẩn đoán, không phải hợp đồng nghiệp vụ hay ảnh chụp stack hiện tại của mọi thread.