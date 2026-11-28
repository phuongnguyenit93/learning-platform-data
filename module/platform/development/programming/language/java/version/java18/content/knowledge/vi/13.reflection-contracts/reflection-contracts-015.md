# getDeclaredConstructor() và Constructor.newInstance(): chữ ký, đối số và ngoại lệ được bọc

## 1. Bài toán và mục tiêu

Trong mô-đun **JAVA_VERSION_JAVA18**, chúng ta kiểm chứng hợp đồng của các API Java vẫn có giá trị trên JDK hiện đại. Bên cạnh UTF-8 mặc định, simple web server, snippet trong Javadoc và các API phân giải tên, chương **Hợp đồng reflection** tập trung vào việc tìm và gọi thành viên Java thông qua reflection. Hai thao tác cần phân biệt ở bài này là:

1. `Class.getDeclaredConstructor(Class<?>... parameterTypes)`: **tìm hàm tạo theo chữ ký khai báo** và trả về đối tượng `Constructor<T>`.
2. `Constructor<T>.newInstance(Object... initargs)`: **thực sự khởi tạo đối tượng** bằng hàm tạo đã tìm được, với các giá trị đối số tại thời điểm gọi.

Một đoạn mã reflection có thể thất bại vì **không tìm thấy đúng chữ ký**, **không có quyền gọi**, **đối số không hợp lệ**, hoặc **chính mã bên trong constructor ném ngoại lệ**. Các trường hợp đó có loại ngoại lệ khác nhau; phân biệt đúng giúp chẩn đoán lỗi và xây dựng thư viện sử dụng reflection an toàn hơn.

Sau bài học, bạn sẽ biết:

- Viết danh sách `Class<?>` khớp chính xác các kiểu tham số trong khai báo, kể cả kiểu nguyên thủy, mảng và constructor varargs.
- Phân biệt kiểm tra chữ ký tại `getDeclaredConstructor` với chuyển đổi giá trị đối số tại `newInstance`.
- Xác định vì sao `NoSuchMethodException`, `IllegalArgumentException`, `IllegalAccessException`, `InvocationTargetException` và `ExceptionInInitializerError` có ý nghĩa khác nhau.
- Lấy **nguyên nhân gốc** bằng `InvocationTargetException.getCause()`, kể cả khi constructor tự ném `IllegalArgumentException`.
- Nhận diện giới hạn quyền truy cập do khai báo `private` và hệ thống module Java (JPMS) trên JDK hiện đại.
- Viết phép kiểm chứng có thể chạy trên JDK 18 trở lên, chỉ dùng API vẫn được hỗ trợ.

## 2. Mô hình hai giai đoạn: tra cứu rồi mới gọi

```text
Lớp cần tạo: Report.class
        |
        | getDeclaredConstructor(String.class, int.class)
        v
Constructor<Report>  (đại diện cho đúng một khai báo)
        |
        | newInstance("job-7", 3)
        v
Report instance, hoặc ngoại lệ từ tầng reflection / mã constructor
```

| Giai đoạn | Đầu vào | Quy tắc quan trọng | Kiểu lỗi điển hình |
| --- | --- | --- | --- |
| Tra cứu constructor | Các đối tượng `Class<?>` biểu thị kiểu tham số | So khớp **đúng chữ ký khai báo**, theo số lượng và thứ tự tham số | `NoSuchMethodException` |
| Kiểm tra khả năng truy cập | Constructor đã tìm được, ngữ cảnh người gọi | Tìm thấy không đồng nghĩa được phép gọi; `private` và JPMS vẫn có hiệu lực | `IllegalAccessException` khi gọi |
| Gọi constructor | Các giá trị `Object...` tại thời điểm chạy | Kiểm tra số lượng, kiểu và chuyển đổi cho phép; có thể unbox và nới rộng kiểu số nguyên thủy | `IllegalArgumentException` trực tiếp |
| Chạy thân constructor | Các đối số đã hợp lệ và có quyền truy cập | Ngoại lệ do **thân hàm tạo ném ra** được phản chiếu bằng ngoại lệ bọc | `InvocationTargetException` |

**Không thể dùng các giá trị như `"abc"` hoặc `42` để tra cứu chữ ký.** `getDeclaredConstructor` nhận kiểu tham số thông qua `String.class`, `int.class`, v.v. Ngược lại, `newInstance` nhận chính các giá trị đó.

### 2.1. Chữ ký phải khớp chính xác

Cho lớp:

```java
public class Ticket {
    public Ticket(String code, int attempts) {}
    public Ticket(String code, Integer attempts, boolean enabled) {}
    private Ticket() {}
}
```

Các truy vấn hợp lệ:

```java
Constructor<Ticket> a =
        Ticket.class.getDeclaredConstructor(String.class, int.class);
Constructor<Ticket> b =
        Ticket.class.getDeclaredConstructor(
                String.class, Integer.class, boolean.class);
Constructor<Ticket> c =
        Ticket.class.getDeclaredConstructor();
```

Những truy vấn dưới đây **không tìm thấy** constructor tương ứng:

```java
// Sai kiểu: Integer.class khác int.class ở giai đoạn tra cứu.
Ticket.class.getDeclaredConstructor(String.class, Integer.class);

// Sai thứ tự: (int, String) không phải (String, int).
Ticket.class.getDeclaredConstructor(int.class, String.class);

// Sai số lượng: khai báo có (String, int), không có (String).
Ticket.class.getDeclaredConstructor(String.class);
```

Mỗi dòng ở khối cuối đều có thể ném `NoSuchMethodException`. Sự khác biệt giữa `int.class` và `Integer.class` đặc biệt quan trọng: **autoboxing không được áp dụng khi tìm chữ ký**. Dấu `throws` của constructor cũng không tham gia so khớp chữ ký.

`getDeclaredConstructor()` không tham số tìm hàm tạo **không nhận tham số**. Nếu lớp chỉ khai báo constructor có tham số, Java không tự sinh thêm constructor mặc định không tham số để reflection có thể tìm thấy.

### 2.2. “Declared” không có nghĩa “được phép gọi”

`getDeclaredConstructor` tìm constructor **được khai báo trong chính lớp đích**, gồm `public`, `protected`, package-private và `private`. Constructor không được kế thừa từ lớp cha.

Khả năng **nhìn thấy metadata** và quyền **thực thi** là hai việc khác nhau. Một constructor `private` có thể được tìm thấy nhưng `newInstance` vẫn ném `IllegalAccessException` nếu không đủ quyền truy cập tại ngữ cảnh gọi. Đây là điều cần kiểm chứng riêng, nhất là giữa các module.

Trong trường hợp chỉ cần constructor công khai, `Class.getConstructor(...)` cho phép tìm hàm tạo `public`. Khi cần metadata của tất cả hàm tạo được khai báo, `getDeclaredConstructors()` trả về danh sách để khảo sát; không dựa vào thứ tự phần tử như một hợp đồng sắp xếp.

### 2.3. Kiểm tra chữ ký thực tế của `Constructor`

```java
Constructor<Ticket> constructor =
        Ticket.class.getDeclaredConstructor(String.class, int.class);

System.out.println(constructor.getDeclaringClass());
System.out.println(constructor.getParameterCount());
System.out.println(Arrays.toString(constructor.getParameterTypes()));
System.out.println(Arrays.toString(constructor.getExceptionTypes()));
System.out.println(constructor.isVarArgs());
```

`getParameterTypes()` là các kiểu tham số theo biểu diễn JVM. `getExceptionTypes()` cho biết ngoại lệ được **khai báo** trong `throws`, không có nghĩa runtime chỉ ném những ngoại lệ đó. Khi tham số có generic như `List<String>`, kiểu dùng để tra cứu là `List.class` do cơ chế type erasure; có thể dùng `getGenericParameterTypes()` nếu cần khảo sát metadata generic riêng.

## 3. Quy tắc đối số khi gọi `newInstance`

Chữ ký của phương thức là:

```java
public T newInstance(Object... initargs)
        throws InstantiationException,
               IllegalAccessException,
               IllegalArgumentException,
               InvocationTargetException
```

`Object...` là cơ chế varargs **của phương thức reflection**, không chứng minh constructor đích chấp nhận số lượng tham số tùy ý. Trước khi gọi thân constructor, reflection kiểm tra danh sách đối số và các phép chuyển đổi được cho phép.

### 3.1. Giai đoạn gọi có thể unbox và widening

Ví dụ constructor khai báo `Ticket(String, int)`:

```java
Constructor<Ticket> ctor =
        Ticket.class.getDeclaredConstructor(String.class, int.class);

// Java đóng gói literal 3 thành Integer khi truyền qua Object...
// Reflection có thể mở hộp Integer thành int để gọi Ticket(String, int).
Ticket ok = ctor.newInstance("T-17", 3);

// Sai: String "3" không chuyển thành số int bằng reflection.
ctor.newInstance("T-17", "3"); // IllegalArgumentException trực tiếp
```

Khi một đối số chứa giá trị primitive đã được đóng gói, reflection có thể **unbox** và thực hiện chuyển đổi **widening primitive** nếu tương thích. Nhưng nó không tự phân tích chuỗi số và không hỗ trợ các chuyển đổi narrowing tùy ý. `null` không thể được truyền vào tham số primitive như `int`.

Điểm dễ nhầm: ở bước tra cứu, `getDeclaredConstructor(String.class, Integer.class)` vẫn **không khớp** constructor `Ticket(String, int)`, dù ở bước gọi có thể truyền đối tượng `Integer` tới tham số `int`.

### 3.2. Constructor có varargs được phản chiếu thành tham số mảng

Cho:

```java
public class Labels {
    public Labels(String... values) {}
}
```

Chữ ký thực tế của constructor là **một tham số `String[]`**:

```java
Constructor<Labels> ctor =
        Labels.class.getDeclaredConstructor(String[].class);

// Truyền một String[] làm một đối số reflection:
Labels labels = ctor.newInstance((Object) new String[] {"red", "blue"});

// Không được kỳ vọng reflection tự đóng gói hai String
// thành một String[] để khớp constructor:
ctor.newInstance("red", "blue"); // IllegalArgumentException
```

Ép kiểu `(Object)` rất quan trọng: nó yêu cầu Java truyền nguyên mảng `String[]` như **một phần tử** của `Object...`. Nếu bỏ ép kiểu, trình biên dịch có thể hiểu mảng đầu vào là mảng varargs của chính lời gọi `Constructor.newInstance`, dẫn đến danh sách đối số reflection không như mong đợi.

Trong reflection, `isVarArgs()` trả lời constructor có được khai báo varargs hay không; nhưng bạn vẫn phải chủ động đưa vào đối tượng mảng phù hợp với chữ ký `getParameterTypes()`.

### 3.3. Lớp thành viên không static có tham số ngầm

Một inner class không `static` mang liên kết với đối tượng lớp ngoài; constructor ở cấp bytecode có thể có tham số bổ sung cho đối tượng lớp ngoài:

```java
public class Container {
    public class Entry {
        public Entry(String id) {}
    }
}
```

Khi tra cứu bằng reflection:

```java
Constructor<Container.Entry> ctor =
        Container.Entry.class.getDeclaredConstructor(
                Container.class, String.class);

Container.Entry entry = ctor.newInstance(new Container(), "E-1");
```

Ở ví dụ này, truyền duy nhất `"E-1"` sẽ không đủ đối số. Để tránh suy đoán các tham số do trình biên dịch tạo, hãy khảo sát `getParameterTypes()` và `getParameters()` trên lớp thực tế đang chạy.

## 4. Những ngoại lệ cần phân loại đúng

| Thao tác | Ngoại lệ hoặc lỗi | Ý nghĩa cần ghi nhận |
| --- | --- | --- |
| `getDeclaredConstructor(...)` | `NoSuchMethodException` | Không tìm thấy constructor khai báo với **đúng** danh sách kiểu tham số yêu cầu |
| `newInstance(...)` | `IllegalArgumentException` **trực tiếp** | Số lượng hoặc kiểu đối số không phù hợp, chuyển đổi không hợp lệ; việc tạo enum bằng reflection cũng bị từ chối |
| `newInstance(...)` | `IllegalAccessException` | Không có quyền thực thi constructor tại ngữ cảnh gọi |
| `newInstance(...)` | `InstantiationException` | Không thể tạo đối tượng vì lớp khai báo không thể khởi tạo theo cách đó, chẳng hạn lớp trừu tượng |
| `newInstance(...)` | `InvocationTargetException` | **Mã constructor được gọi** đã ném một `Throwable`; đối tượng ngoại lệ gốc nằm ở `getCause()` |
| Khởi tạo lớp do `newInstance(...)` kích hoạt | `ExceptionInInitializerError` | Quá trình khởi tạo lớp tĩnh thất bại; tách khỏi ngoại lệ do thân constructor chủ động ném |
| Cố mở quyền truy cập sâu | `InaccessibleObjectException` có thể phát sinh với `setAccessible(true)` | Module không cho phép thao tác mở truy cập theo yêu cầu |

Bảng nêu các nhánh đặc trưng để xử lý, không phải danh sách mọi `RuntimeException` hay `Error` có thể xuất hiện trong chương trình Java.

### 4.1. `InvocationTargetException`: lớp vỏ và nguyên nhân gốc

Giả sử có:

```java
public Order(String id) {
    if (id.isBlank()) {
        throw new IllegalArgumentException("id must not be blank");
    }
}
```

Nếu gọi `newInstance("")` với **chữ ký đúng**, ngoại lệ `IllegalArgumentException` do **thân constructor** ném sẽ được bọc trong `InvocationTargetException`. Ngược lại, gọi sai số lượng đối số như `newInstance("A", 2)` có thể ném `IllegalArgumentException` **trực tiếp từ reflection** trước khi constructor được chạy.

Cách xử lý:

```java
try {
    constructor.newInstance("");
} catch (InvocationTargetException wrapped) {
    Throwable original = wrapped.getCause();
    // Chẩn đoán theo loại và thông điệp của original.
}
```

`getCause()` cho biết nguyên nhân do constructor ném, có thể là ngoại lệ checked, ngoại lệ unchecked hoặc một `Error`. Khi thiết kế ứng dụng, không tự ý nuốt nguyên nhân, không chỉ in mỗi thông điệp của `InvocationTargetException`; cần lưu lại cause/stack trace để tìm được vị trí ném thực sự.

### 4.2. Ngoại lệ của constructor khác với thất bại khởi tạo lớp tĩnh

Nếu lời gọi lần đầu kích hoạt khởi tạo một lớp và khối khởi tạo tĩnh thất bại, JVM có thể phát sinh `ExceptionInInitializerError` trước khi thân constructor thực sự chạy. Không nên quy lỗi này thành “constructor nhận sai tham số”.

Sau khi một lớp đã thất bại trong quá trình khởi tạo, các lần sử dụng tiếp theo còn có thể gặp `NoClassDefFoundError` liên quan đến trạng thái khởi tạo lỗi. Vì vậy khi phân tích log cần giữ thời điểm và stack trace của **lỗi đầu tiên**.

## 5. Ví dụ Java đầy đủ: kiểm chứng cả hai giai đoạn

Chương trình dưới đây chạy bằng JDK 18 trở lên. Nó minh họa:

- Tìm đúng constructor `(String, int)` và khởi tạo thành công.
- Lỗi **tra cứu sai chữ ký** với `Integer.class`.
- Lỗi **gọi với giá trị sai kiểu** (chuỗi `"three"`) trước khi vào thân constructor.
- Constructor ném `IOException` checked hoặc `IllegalArgumentException` unchecked; **cả hai** đều được bao trong `InvocationTargetException` khi gọi qua reflection.

Lưu thành `ConstructorContractsDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;

public class ConstructorContractsDemo {
    public static final class Report {
        private final String id;
        private final int retries;

        public Report(String id, int retries) throws IOException {
            if (id == null || id.isBlank()) {
                throw new IOException("id is required");
            }
            if (retries < 0) {
                throw new IllegalArgumentException("retries must be >= 0");
            }
            this.id = id;
            this.retries = retries;
        }

        @Override
        public String toString() {
            return "Report[id=" + id + ", retries=" + retries + "]";
        }
    }

    private static void expectConstructorFailure(
            Constructor<Report> ctor,
            String id,
            int retries,
            Class<? extends Throwable> causeType)
            throws ReflectiveOperationException {
        try {
            ctor.newInstance(id, retries);
            throw new AssertionError("Expected constructor to throw");
        } catch (InvocationTargetException wrapped) {
            Throwable original = wrapped.getCause();
            if (!causeType.isInstance(original)) {
                throw new AssertionError("Unexpected cause", original);
            }
            System.out.println("Constructor threw: "
                    + original.getClass().getSimpleName()
                    + " - " + original.getMessage());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<Report> ctor =
                Report.class.getDeclaredConstructor(
                        String.class, int.class);

        System.out.println("Parameters: "
                + Arrays.toString(ctor.getParameterTypes()));
        System.out.println("Declared throws: "
                + Arrays.toString(ctor.getExceptionTypes()));

        // int 3 được đóng gói khi truyền qua Object..., rồi
        // được reflection mở hộp để khớp int trong constructor.
        Report good = ctor.newInstance("job-7", 3);
        System.out.println("Created: " + good);

        try {
            Report.class.getDeclaredConstructor(
                    String.class, Integer.class);
            throw new AssertionError("Expected NoSuchMethodException");
        } catch (NoSuchMethodException expected) {
            System.out.println("Lookup: NoSuchMethodException");
        }

        try {
            ctor.newInstance("job-7", "three");
            throw new AssertionError("Expected argument mismatch");
        } catch (IllegalArgumentException expected) {
            System.out.println("Call: IllegalArgumentException (direct)");
        }

        // Checked exception do thân constructor ném.
        expectConstructorFailure(ctor, "", 3, IOException.class);

        // Unchecked exception do thân constructor ném.
        // Nó vẫn được bọc, KHÁC IllegalArgumentException trực tiếp bên trên.
        expectConstructorFailure(
                ctor, "job-7", -1, IllegalArgumentException.class);
    }
}
```

Chạy:

```bash
javac ConstructorContractsDemo.java
java ConstructorContractsDemo
```

Kết quả điển hình (đã rút gọn tên lớp trong dòng metadata):

```text
Parameters: [class java.lang.String, int]
Declared throws: [class java.io.IOException]
Created: Report[id=job-7, retries=3]
Lookup: NoSuchMethodException
Call: IllegalArgumentException (direct)
Constructor threw: IOException - id is required
Constructor threw: IllegalArgumentException - retries must be >= 0
```

Đây là kết quả của chính ví dụ khi sử dụng các lớp cục bộ và public constructor như đã viết; không phụ thuộc máy chủ, DNS, hay thư viện thứ ba. Nếu sửa kiểu tham số hoặc quyền truy cập, loại lỗi và đường xử lý sẽ thay đổi.

### Bóc tách bằng chứng từ từng thử nghiệm

| Thử nghiệm | Bằng chứng trong log | Kết luận hợp lệ |
| --- | --- | --- |
| `getDeclaredConstructor(String.class, int.class)` | Nhận `Constructor<Report>` và in `[String, int]` | Tìm thấy đúng chữ ký đã khai báo |
| `newInstance("job-7", 3)` | Có `Report` mới | Đối số chuyển đổi hợp lệ, constructor chạy thành công |
| `getDeclaredConstructor(String.class, Integer.class)` | `NoSuchMethodException` | Không có constructor với cặp kiểu khai báo tương ứng |
| `newInstance("job-7", "three")` | `IllegalArgumentException` trực tiếp | Mismatch đối số ở tầng gọi reflection |
| `newInstance("", 3)` | `InvocationTargetException` có cause `IOException` | Constructor được gọi và chủ động ném `IOException` |
| `newInstance("job-7", -1)` | `InvocationTargetException` có cause `IllegalArgumentException` | Chính logic kiểm tra của constructor ném ngoại lệ runtime |

**Sai lầm phổ biến:** đặt `catch (IllegalArgumentException)` duy nhất rồi tin rằng đã bắt được mọi `IllegalArgumentException` có thể xuất hiện. Nếu ngoại lệ được ném **từ bên trong** constructor, khi gọi qua reflection phải kiểm tra `InvocationTargetException.getCause()`.

## 6. Constructor không public và giới hạn module

Ví dụ:

```java
public class SecretKeyBox {
    private SecretKeyBox(String key) {
        // Kiểm soát việc khởi tạo ở lớp này.
    }
}
```

Có thể nhận metadata:

```java
Constructor<SecretKeyBox> ctor =
        SecretKeyBox.class.getDeclaredConstructor(String.class);
```

Nhưng việc gọi:

```java
SecretKeyBox value = ctor.newInstance("demo");
```

chỉ thành công khi ngữ cảnh gọi có đủ quyền truy cập. `getDeclaredConstructor` **không tự nâng quyền** cho constructor. Trong cùng một nest (ví dụ lớp ngoài và lớp lồng nhau), quy tắc truy cập private có thể cho phép gọi; vì vậy cũng không được khẳng định cứ gặp `private` là `newInstance` luôn ném `IllegalAccessException`.

Khi thật sự cần quyền truy cập sâu và hợp đồng/module cho phép, có thể kiểm tra:

```java
Constructor<SecretKeyBox> ctor =
        SecretKeyBox.class.getDeclaredConstructor(String.class);

if (ctor.trySetAccessible()) {
    SecretKeyBox value = ctor.newInstance("demo");
    System.out.println(value);
} else {
    System.out.println("Không được phép mở quyền truy cập");
}
```

`trySetAccessible()` cho biết có bật được khả năng bỏ qua các kiểm tra truy cập Java thông thường hay không. Trong môi trường JPMS, package thuộc module khác có thể cần được **open** thích hợp cho module gọi; việc `export` chỉ dành cho truy cập các thành viên public không tương đương với quyền reflection sâu trên thành viên private. Không giả định `trySetAccessible` luôn trả về `true`.

Bật quyền truy cập sâu có tác động đến đóng gói và bảo trì. Nếu bạn sở hữu API, một factory hoặc constructor public có hợp đồng rõ ràng thường thuận lợi hơn cho người sử dụng. Khi không sở hữu lớp/module đích, hãy tôn trọng ranh giới module thay vì cố ép truy cập bằng các tùy chọn cấu hình thiếu kiểm soát.

## 7. Các trường hợp biên còn áp dụng trên JDK hiện đại

### 7.1. Constructor của enum không thể được gọi theo cách này

JVM hạn chế việc khởi tạo thêm hằng enum ngoài các hằng đã khai báo. Dù reflection có thể nhìn thấy metadata của constructor enum, `Constructor.newInstance` không cho tạo enum instance mới và có thể ném `IllegalArgumentException`. Không dùng reflection để tự tạo giá trị enum.

### 7.2. Không khởi tạo được lớp abstract

Một lớp trừu tượng có thể khai báo constructor để lớp con gọi, và `getDeclaredConstructor` có thể tìm thấy constructor đó. Tuy nhiên `Constructor.newInstance` không thể trực tiếp tạo đối tượng từ lớp abstract; `InstantiationException` là một nhánh thất bại tương ứng.

### 7.3. Records cũng cần đúng chữ ký

Record là kiểu Java còn được hỗ trợ. Với record:

```java
record Point(int x, int y) {}

Constructor<Point> ctor =
        Point.class.getDeclaredConstructor(int.class, int.class);
Point point = ctor.newInstance(2, 5);
```

Constructor canonical của record nhận đúng các kiểu và thứ tự thành phần record. Nếu constructor hoặc quá trình kiểm tra tính hợp lệ ném ngoại lệ, quy tắc `InvocationTargetException` vẫn được áp dụng khi gọi bằng reflection.

### 7.4. Tham số generic và overload

Chữ ký runtime dựa trên kiểu sau erasure; ví dụ constructor `Store(List<String>)` được tìm bằng `List.class`, không có token `List<String>.class`. Nếu một lớp có nhiều overload, hãy xác định chính xác constructor cần gọi trước khi truyền dữ liệu. Không suy đoán rằng reflection sẽ tự chọn overload “gần nhất” như cách trình biên dịch xử lý một lời gọi Java trong mã nguồn.

### 7.5. Phản xạ có chi phí và ảnh hưởng đến thiết kế

Reflection hữu ích cho framework, thư viện mapping, serializer hoặc công cụ kiểm tra runtime, nhưng làm giảm khả năng trình biên dịch xác minh trước kiểu tham số. Với tuyến xử lý gọi lặp lại, nên tìm và kiểm tra `Constructor<?>` tại thời điểm cấu hình, sau đó tái sử dụng metadata phù hợp, thay vì liên tục dò tên và chữ ký mỗi lần tạo đối tượng. Tuy nhiên hiệu năng cụ thể phải được đo trên JDK và workload thật; bản thân việc dùng reflection không đủ để khẳng định một mức chậm cố định.

Khi cần liên kết lời gọi động với hợp đồng kiểu mạnh hơn, Java cũng có API `java.lang.invoke.MethodHandle`; đó là một cơ chế riêng với quy tắc kiểu và lỗi khác, không nên lấy hành vi `MethodHandle` để suy diễn cho `Constructor.newInstance`.

## 8. Bài tập kiểm chứng có hướng dẫn

**Bài 1 — Chữ ký và boxing.** Cho constructor `Account(long id, String owner)`. Viết câu lệnh tra cứu chính xác; dự đoán sự khác nhau giữa:

```java
Account.class.getDeclaredConstructor(long.class, String.class);
Account.class.getDeclaredConstructor(Long.class, String.class);
```

Kỳ vọng: biểu thức đầu tìm được constructor; biểu thức sau ném `NoSuchMethodException` nếu lớp không có thêm overload `(Long, String)`. Trong khi đó, ở giai đoạn gọi constructor `(long, String)`, một giá trị `Long` có thể được unbox phù hợp.

**Bài 2 — Ngoại lệ cùng tên ở hai tầng.** Sửa `Report` để khi `retries > 10` thì constructor ném `IllegalArgumentException("too many retries")`. Thử gọi `ctor.newInstance("ok", "11")` và `ctor.newInstance("ok", 11)`. Cần ghi hai loại đường xử lý: trường hợp đầu sai kiểu đối số nên ném `IllegalArgumentException` trực tiếp; trường hợp sau vào thân constructor rồi ném `InvocationTargetException` có cause `IllegalArgumentException`.

**Bài 3 — Varargs và mảng.** Tạo class có constructor `Tags(String... tags)`. Kiểm tra `getParameterCount()`, `getParameterTypes()`, `isVarArgs()`; so sánh `newInstance((Object) new String[]{"a", "b"})` với `newInstance("a", "b")`. Giải thích lý do phương thức Java `newInstance(Object...)` không tự làm thay thao tác đóng gói varargs cho constructor đích.

**Bài 4 — Quyền truy cập.** Đặt lớp có constructor private ở một module/package khác, dùng `getDeclaredConstructor` để lấy metadata và kiểm tra kết quả gọi cùng `trySetAccessible()` trong bối cảnh module thực tế. Ghi rõ package có `opens` hay không; không suy đoán mọi JDK đều cho truy cập chỉ vì metadata đã được tìm thấy.

**Bài 5 — Phân tích stack trace.** Một hệ thống báo `InvocationTargetException` ở tầng framework. Xác định cause, loại `Throwable` gốc, stack trace và dữ liệu đầu vào của constructor. Nếu cause là `IOException` hoặc `IllegalArgumentException`, nhận diện nó thuộc logic ứng dụng nào thay vì nhầm với lỗi tra cứu `NoSuchMethodException`.

## 9. Ghi nhớ hợp đồng API

1. `getDeclaredConstructor(Class<?>...)` **tìm chữ ký khai báo chính xác**, bao gồm kiểu nguyên thủy, thứ tự, số lượng tham số; không áp dụng boxing như khi gọi.
2. `Constructor.newInstance(Object...)` **nhận giá trị đối số**, thực hiện kiểm tra và các chuyển đổi reflection cho phép, rồi mới chạy constructor.
3. `NoSuchMethodException` xảy ra ở bước **tra cứu**; `IllegalArgumentException` trực tiếp thường cho thấy vấn đề ở bước **truyền đối số**; `IllegalAccessException` liên quan quyền thực thi.
4. Ngoại lệ do **thân constructor** ném được bọc trong `InvocationTargetException`; dùng `getCause()` để phân tích nguyên nhân gốc, kể cả khi đó là `IllegalArgumentException`.
5. `getDeclaredConstructor` trả metadata cho cả constructor private nhưng không cam kết quyền gọi. Quy tắc truy cập Java và hệ thống module vẫn có hiệu lực.
6. Constructor varargs thể hiện bằng kiểu mảng trong chữ ký phản xạ; non-static inner class có thể có tham số đối tượng lớp ngoài; record cũng cần chữ ký đúng.
7. Kiểm chứng hành vi trên chính JDK đang chạy, xử lý ngoại lệ theo tầng phát sinh và giữ lại cause/stack trace để chẩn đoán.

Các nguyên tắc trên tiếp tục phù hợp trên JDK hiện đại và giúp kiểm chứng hợp đồng reflection mà không phụ thuộc API lỗi thời hoặc giả định về chi tiết nội bộ của JVM.
