# Không khởi tạo abstract class hoặc interface bằng constructor thông thường trong Java Reflection

## 1. Hiểu đúng giới hạn của constructor

Trong Java, **abstract class** là lớp chưa được phép tạo đối tượng trực tiếp; **interface** là hợp đồng kiểu, không phải lớp có constructor thông thường. Reflection có thể đọc metadata của các kiểu này nhưng **không làm chúng trở thành kiểu có thể khởi tạo trực tiếp**.

```java
abstract class Animal {
    protected Animal() { }
    abstract String sound();
}

interface Movable {
    void move();
}
```

Những lệnh sau đều không hợp lệ tại thời điểm biên dịch:

```java
// MÃ MINH HỌA KHÔNG BIÊN DỊCH ĐƯỢC
// Animal animal = new Animal();    // Animal là abstract class.
// Movable movable = new Movable(); // Movable là interface.
```

Tương tự, dùng Reflection để tìm `Class` hay constructor **không thể bỏ qua** hạn chế này. Phải tạo một **lớp cụ thể (concrete class)** có thể khởi tạo, rồi tham chiếu đối tượng đó qua kiểu abstract class/interface nếu cần.

**Phân biệt hai trường hợp:**

- Abstract class **có thể khai báo constructor**; constructor đó được thực thi trong quá trình xây dựng một đối tượng của lớp con cụ thể. Tuy nhiên, `Constructor` của abstract class **không thể** tự tạo instance của chính abstract class.
- Interface **không có constructor**. Không thể tìm `Constructor<Interface>` của interface, kể cả bằng `getDeclaredConstructor()`.

## 2. Những API Reflection liên quan

| Thao tác | Abstract class | Interface |
| --- | --- | --- |
| `SomeType.class`, `Class.forName(...)` | Lấy metadata `Class` bình thường | Lấy metadata `Class` bình thường |
| `Class.isInterface()` | `false` | `true` |
| `Modifier.isAbstract(type.getModifiers())` | `true` | Cũng thường `true` vì interface có cờ `abstract` |
| `getDeclaredConstructors()` | Có thể trả về các constructor khai báo trong abstract class | Mảng rỗng |
| `getDeclaredConstructor(parameterTypes...)` | Có thể tìm constructor khớp chữ ký | Ném `NoSuchMethodException` |
| `getConstructor(parameterTypes...)` | Có thể tìm constructor `public` của abstract class | Ném `NoSuchMethodException` |
| `Constructor.newInstance(args...)` | Không tạo được abstract class; có thể ném `InstantiationException` | Không có constructor interface để gọi |
| Khởi tạo lớp triển khai cụ thể | Được, qua constructor của **lớp con concrete** | Được, qua constructor của **lớp implement concrete** |

`getDeclaredConstructor(...)` chỉ **tra cứu khai báo**, còn `Constructor.newInstance(...)` mới **yêu cầu JVM tạo đối tượng**. Tìm được constructor không đồng nghĩa việc gọi constructor đó để tạo instance là hợp lệ.

Các constructor **không được kế thừa**: `Child.class.getConstructor(...)` chỉ tra cứu constructor công khai được khai báo cho `Child` theo quy tắc API, không dùng constructor của `Parent` để tạo `Child`. Đối tượng lớp con được xây dựng bằng constructor của lớp con và constructor lớp cha được gọi trong chuỗi `super(...)`.

## 3. Tại sao abstract class vẫn có constructor?

Constructor của abstract class phục vụ phần trạng thái chung cần khởi tạo cho mọi lớp con.

```java
abstract class Job {
    protected final String name;

    protected Job(String name) {
        this.name = name;
    }

    abstract String run();
}

class EmailJob extends Job {
    EmailJob(String name) {
        super(name); // Gọi constructor của phần Job trong đối tượng EmailJob.
    }

    @Override
    String run() {
        return "EmailJob: " + name;
    }
}
```

Tại `new EmailJob("daily")`, JVM tạo đối tượng có **runtime class `EmailJob`**, đồng thời thực thi `Job(String)` trong chuỗi khởi tạo. Không hề có đối tượng độc lập với runtime class chính xác là abstract `Job`.

Reflection tìm được `Job.class.getDeclaredConstructor(String.class)`, nhưng **gọi `newInstance("daily")` trên chính `Constructor<Job>` đó không tạo một `EmailJob`**. JVM không đoán giúp lớp con. Nó từ chối tạo instance của kiểu abstract.

## 4. Ví dụ Java 17+ đầy đủ và chạy được

Lưu nguyên chương trình sau dưới tên `AbstractConstructorDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;

public class AbstractConstructorDemo {
    public static abstract class Job {
        protected final String name;

        public Job(String name) {
            this.name = name;
        }

        public abstract String run();
    }

    public interface Work {
        String run();
    }

    public static final class RealJob extends Job implements Work {
        public RealJob(String name) {
            super(name);
        }

        @Override
        public String run() {
            return "run:" + name;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Job abstract: "
                + Modifier.isAbstract(Job.class.getModifiers()));

        Constructor<Job> baseCtor =
                Job.class.getDeclaredConstructor(String.class);
        System.out.println("Job constructor parameters: "
                + baseCtor.getParameterCount());

        try {
            baseCtor.newInstance("x");
        } catch (InstantiationException e) {
            System.out.println("Job newInstance: InstantiationException");
        }

        System.out.println("Work interface: " + Work.class.isInterface());
        System.out.println("Work constructors: "
                + Work.class.getDeclaredConstructors().length);

        try {
            Work.class.getDeclaredConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("Work lookup: NoSuchMethodException");
        }

        Constructor<RealJob> realCtor =
                RealJob.class.getConstructor(String.class);
        Job asJob = realCtor.newInstance("demo");
        Work asWork = (Work) asJob;

        System.out.println("concrete class: "
                + asJob.getClass().getSimpleName());
        System.out.println("job call: " + asJob.run());
        System.out.println("interface call: " + asWork.run());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AbstractConstructorDemo.java
java AbstractConstructorDemo
```

Stdout:

```text
Job abstract: true
Job constructor parameters: 1
Job newInstance: InstantiationException
Work interface: true
Work constructors: 0
Work lookup: NoSuchMethodException
concrete class: RealJob
job call: run:demo
interface call: run:demo
```

**Giải thích kết quả:**

1. `Modifier.isAbstract(Job.class.getModifiers())` xác nhận `Job` là abstract.
2. `Job.class.getDeclaredConstructor(String.class)` vẫn tìm thấy constructor có một tham số.
3. `baseCtor.newInstance("x")` thất bại với `InstantiationException` vì kiểu khai báo là abstract; constructor có tồn tại và được tra cứu đúng cũng không thay đổi điều đó.
4. `Work.class.isInterface()` trả `true`; `getDeclaredConstructors()` có kích thước bằng `0`. Tra cứu constructor không tham số của interface ném `NoSuchMethodException`.
5. `RealJob` là lớp cụ thể với constructor `public RealJob(String)`. `realCtor.newInstance("demo")` tạo một đối tượng thật sự có runtime class `RealJob`.
6. Đối tượng `RealJob` có thể được tham chiếu bằng `Job` và `Work`. Kiểu của biến tham chiếu **không phải** bằng chứng rằng JVM đã tạo trực tiếp instance của abstract class/interface.

Trong ví dụ, constructor của `Job` được khai báo `public` để việc truy cập không che lấp lỗi cần học. Nếu constructor abstract class là `protected` hoặc `private`, quy tắc truy cập Reflection có thể gây `IllegalAccessException` hay lỗi quyền khác **trước khi** chạm đến bước kiểm tra tính khởi tạo được.

## 5. Ba nhóm lỗi cần phân biệt

Khi làm việc với constructor, lỗi có thể xảy ra ở **những giai đoạn khác nhau**:

| Giai đoạn | Trường hợp | Kết quả thường gặp |
| --- | --- | --- |
| Tra cứu | `Interface.class.getDeclaredConstructor()` | `NoSuchMethodException` vì interface không có constructor |
| Tra cứu | Tìm sai chữ ký constructor của một lớp, ví dụ `RealJob.class.getConstructor(int.class)` | `NoSuchMethodException` vì chỉ có `RealJob(String)` |
| Tạo instance | `Job.class.getDeclaredConstructor(String.class).newInstance("x")` | `InstantiationException` vì `Job` là abstract |
| Quyền truy cập | Có constructor nhưng caller không được phép dùng nó | `IllegalAccessException` hoặc lỗi truy cập tùy ngữ cảnh |
| Kiểm tra đối số | Số lượng/kiểu đối số không hợp lệ khi gọi `newInstance` | `IllegalArgumentException` |
| Chạy constructor | Constructor concrete thực thi và ném exception | `InvocationTargetException` chứa nguyên nhân gốc |

Đừng bắt duy nhất `NoSuchMethodException` cho toàn bộ quy trình. Lỗi đó thuộc **bước tìm**; `InstantiationException` xảy ra ở **bước tạo**, khi metadata constructor đã có rồi.

`Constructor.newInstance(...)` có thể ném các checked exceptions như `InstantiationException`, `IllegalAccessException`, `InvocationTargetException`, bên cạnh exception do đối số/quyền truy cập. Khi viết code thư viện, hãy xử lý theo ý nghĩa của từng lỗi thay vì cố thử đi thử lại cùng một constructor trên abstract class.

## 6. Kiểm tra kiểu trước khi chọn constructor

Khi class được cung cấp qua cấu hình, annotation scanning hoặc `Class.forName`, hãy kiểm tra tính cụ thể của kiểu trước khi thử khởi tạo:

```java
// Hàm độc lập đặt trong một lớp Java; chỉ minh họa bước kiểm tra.
static boolean isConcreteClass(Class<?> type) {
    int modifiers = type.getModifiers();
    return !type.isInterface()
            && !java.lang.reflect.Modifier.isAbstract(modifiers)
            && !type.isPrimitive()
            && !type.isArray()
            && !type.isAnnotation();
}
```

Bước này phân biệt abstract class và interface với lớp bình thường nhưng **không đủ để bảo đảm mọi `Class<?>` còn lại tạo instance được**. Ví dụ: lớp không có constructor phù hợp; constructor không truy cập được; enum bị hạn chế tạo instance bằng Reflection; `void.class` cũng không biểu diễn lớp có thể khởi tạo. `Class.isInterface()` là tín hiệu trực tiếp để phân biệt interface, vì chỉ kiểm tra `Modifier.isAbstract(...)` sẽ gộp interface với abstract class.

Một quy trình thực tế hơn:

1. Kiểm tra `type.isInterface()` và `Modifier.isAbstract(type.getModifiers())`. Nếu một trong hai đúng, **không dùng constructor trên chính kiểu đó**.
2. Xác định concrete class cần tạo từ cấu hình hay contract đã biết; kiểm tra `expectedType.isAssignableFrom(concreteType)` để xác nhận tương thích.
3. Dùng `concreteType.getDeclaredConstructor(parameterTypes...)` hoặc `getConstructor(...)` theo phạm vi cần tra, và truyền chính xác kiểu tham số.
4. Kiểm tra khả năng truy cập constructor; không mặc định có quyền mở module/package nội bộ.
5. Gọi `newInstance(args...)` trên constructor **của concrete class** và xử lý các lỗi thực thi.

**Không suy diễn** rằng chọn lớp con chỉ bằng cách gọi `getConstructor` trên abstract class: việc tìm subtype cụ thể là trách nhiệm của ứng dụng hoặc container/DI, không phải của `Constructor.newInstance`.

## 7. Dùng abstract class/interface như kiểu tham chiếu hoàn toàn hợp lệ

Một số đoạn code có thể khiến người mới hiểu nhầm rằng “đã tạo interface” hoặc “đã tạo abstract class”.

### 7.1. Concrete subclass

```java
// Khi đã có lớp RealJob trong chương trình đầy đủ:
Job job = new RealJob("billing");
Work work = (Work) job;
```

`new` khởi tạo `RealJob`. Hai biến chỉ giữ tham chiếu được gán theo quy tắc kế thừa/implements.

### 7.2. Anonymous subclass của abstract class

```java
// Đặt trong phương thức có thể truy cập AbstractConstructorDemo.Job:
AbstractConstructorDemo.Job anonymous =
        new AbstractConstructorDemo.Job("one-off") {
            @Override
            public String run() {
                return "anonymous:" + name;
            }
        };
System.out.println(anonymous.run()); // anonymous:one-off
```

Cú pháp `new AbstractConstructorDemo.Job(...) { ... }` tạo **lớp con ẩn danh cụ thể**, có phần cài đặt phương thức abstract. Nó **không** tạo trực tiếp đối tượng có runtime class là `Job`. Mảnh code này minh họa, không phải một chương trình độc lập.

### 7.3. Lambda cho functional interface

```java
// Work là interface có đúng một abstract method như chương trình ở mục 4.
AbstractConstructorDemo.Work action = () -> "lambda";
System.out.println(action.run()); // lambda
```

Lambda cung cấp một đối tượng triển khai functional interface theo cơ chế của Java; **interface `Work` không tự có constructor**. Nếu interface có nhiều abstract methods và không phải functional interface, cú pháp lambda sẽ không hợp lệ.

### 7.4. Dynamic Proxy

`java.lang.reflect.Proxy.newProxyInstance(...)` có thể tạo một **đối tượng proxy thực thi interface** theo `InvocationHandler`, nhưng đối tượng có runtime class là lớp proxy được runtime tạo ra, không phải chính interface. Đây là kỹ thuật tạo implementation động, **khác** với việc gọi constructor của interface. Không dùng proxy như cách mặc định để thay thế thiết kế concrete implementation khi không cần hành vi động.

## 8. Vai trò của constructor cha khi có kế thừa

Thứ tự khởi tạo chuẩn khi gọi `new RealJob("demo")`:

```text
RealJob(String) được chọn làm constructor đích
    |
    v
super(name) gọi Job(String)
    |
    v
Job khởi tạo name
    |
    v
RealJob hoàn tất xây dựng
    |
    v
Đối tượng có runtime class RealJob
```

Đó là lý do abstract class cần và có thể có constructor: **lớp cha phải thiết lập phần trạng thái chung** cho đối tượng lớp con. Java cấm **trực tiếp khởi tạo abstract class**, nhưng không cấm constructor của nó tham gia chuỗi khởi tạo hợp lệ.

Một lưu ý thiết kế: constructor abstract class không nên gọi các phương thức overridable nếu các phương thức ấy phụ thuộc trạng thái mà lớp con chưa khởi tạo. Quy tắc dispatch động có thể kích hoạt implementation của lớp con quá sớm trong lúc constructor cha đang chạy.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng / ngộ nhận | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getDeclaredConstructor` tìm thấy nhưng `newInstance` ném `InstantiationException` | Đang dùng `Constructor` của abstract class | Chọn constructor của concrete subclass |
| `Interface.class.getDeclaredConstructor()` ném `NoSuchMethodException` | Interface không khai báo constructor | Chọn lớp implement hoặc cơ chế tạo implementation phù hợp |
| Nghĩ abstract class không được có constructor | Nhầm giới hạn tạo object với khai báo constructor | Constructor abstract class phục vụ xây dựng subclass |
| Nghĩ gọi `abstractType.getConstructor(...)` sẽ tự tìm subclass | Reflection lookup không tự chọn lớp con | Xác định concrete class tường minh |
| Nghĩ `Class.forName("...")` khởi tạo được interface | `Class.forName` lấy `Class`/nạp và có thể khởi tạo lớp theo ngữ nghĩa API, không tạo instance của kiểu | Phân biệt metadata `Class` với đối tượng triển khai |
| Kiểm tra `Modifier.isAbstract` để phân biệt hai loại | Interface cũng mang modifier `abstract` | Kiểm tra `isInterface()` trước |
| Constructor lớp con không gọi constructor cha | Constructor Java bắt buộc dẫn tới gọi `super(...)` hoặc `this(...)`, trực tiếp hay ngầm định | Xem chuỗi constructor và chữ ký constructor cha |
| Dùng `Class.newInstance()` cũ để tránh lỗi | API cũ đã deprecated; không vượt được abstract/interface | Dùng `getDeclaredConstructor(...).newInstance(...)` trên kiểu concrete |
| Tạo được proxy rồi kết luận interface có constructor | Proxy tạo lớp triển khai động | Kiểm tra `object.getClass()`; hiểu proxy là implementation |

**Ghi nhớ:** **Abstract class có thể có constructor nhưng không được tạo instance trực tiếp; interface không có constructor.** Reflection phản ánh đúng hai quy tắc ấy. Luôn lấy `Constructor` của một **lớp cụ thể có thể khởi tạo**, rồi dùng abstract class/interface làm kiểu tham chiếu nếu phù hợp.

Tham khảo: [Java SE 17 `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`java.lang.reflect.Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html), [JLS §8.1.1.1 — abstract Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.1).