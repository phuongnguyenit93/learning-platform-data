# Tra cứu constructor public hoặc declared trong Java Reflection

## 1. Vì sao cần tra cứu Constructor?

Trong Java, `Constructor` là thành phần dùng để tạo instance của một lớp. Java Reflection cung cấp `java.lang.reflect.Constructor<T>` để tìm, liệt kê và đọc thông tin constructor tại runtime. Nhờ vậy, thư viện dependency injection, serializer, ORM, test framework và công cụ chẩn đoán có thể chọn constructor dựa trên class nhận được lúc chạy.

Ví dụ, khi chỉ có `Class<?> type`, chương trình không thể luôn viết trực tiếp `new SomeClass(...)` vì chưa biết trước tên lớp hoặc chữ ký constructor. Reflection cho phép khám phá constructor qua `type.getConstructor(...)`, `type.getDeclaredConstructor(...)` và các biến thể lấy danh sách. Tuy nhiên, **tra cứu metadata** khác với **được phép gọi constructor**: tìm thấy constructor `private` không tự cấp quyền tạo đối tượng.

Bài học tập trung vào sự khác nhau giữa hai họ API **public** và **declared**, cách chọn đúng overload, phạm vi truy cập và những trường hợp đặc biệt dễ gây `NoSuchMethodException` hoặc `IllegalAccessException`. Ví dụ sử dụng Java 17 trở lên.

## 2. Bốn API quan trọng nhất

| Mục đích | API trong `Class<T>` | Kết quả | Phạm vi |
| --- | --- | --- | --- |
| Tìm một constructor public | `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor `public` với chính xác danh sách kiểu tham số |
| Liệt kê constructor public | `getConstructors()` | `Constructor<?>[]` | Toàn bộ constructor `public` khai báo ở lớp |
| Tìm một constructor được khai báo trực tiếp | `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor đúng chữ ký, bất kể `public`, `protected`, package-private hay `private` |
| Liệt kê toàn bộ constructor được khai báo trực tiếp | `getDeclaredConstructors()` | `Constructor<?>[]` | Mọi constructor của lớp, bất kể access modifier |

Các dạng tra cứu đơn lẻ thường ném `NoSuchMethodException` nếu không tìm được constructor phù hợp; các dạng lấy danh sách trả về mảng (có thể rỗng) và **không bảo đảm thứ tự phần tử**.

**Khác biệt cốt lõi:** từ `Declared` ở đây có nghĩa *được khai báo trong class hiện tại*, không có nghĩa “constructor chỉ dành cho private” hay “tắt kiểm tra truy cập”. Chẳng hạn, `getDeclaredConstructor()` vẫn tìm được constructor `public` nếu class khai báo constructor không tham số đó.

### Constructor không được kế thừa

Khác với method hay field, **constructor không được kế thừa** từ superclass. Do đó `Child.class.getConstructors()` không bao giờ liệt kê constructor của `Parent`. Cả hai họ API luôn xét constructor của chính lớp mà đối tượng `Class` đại diện.

Nói cách khác, đối lập `getConstructor()` và `getDeclaredConstructor()` chủ yếu là **phạm vi modifier public** so với **mọi modifier**, không phải lựa chọn “kế thừa” hay “không kế thừa”.

## 3. Tra cứu đúng chữ ký: tên constructor không cần truyền vào

Không có tham số tên khi tra cứu constructor. Class đã xác định tên kiểu sở hữu; phương thức chỉ nhận **danh sách kiểu tham số theo đúng thứ tự**.

```java
Constructor<User> noArgs = User.class.getConstructor();
Constructor<User> byName =
        User.class.getDeclaredConstructor(String.class);
Constructor<User> byNameAndAge =
        User.class.getDeclaredConstructor(String.class, int.class);
```

Đây là đoạn minh họa bên trong phương thức có xử lý hoặc khai báo `NoSuchMethodException`; giả định `User` thực sự khai báo các constructor tương ứng, và đã import `java.lang.reflect.Constructor`.

Các nguyên tắc chọn chữ ký:

- `getConstructor()` hoặc `getDeclaredConstructor()` không truyền đối số yêu cầu constructor **không tham số**.
- `String.class, int.class` **khác** `int.class, String.class`. Thứ tự tham số phải trùng.
- `int.class` khác `Integer.class`, và `long.class` khác `int.class`. Reflection **không tự boxing/unboxing hoặc primitive widening trong giai đoạn tìm chữ ký**.
- Với `String... args`, signature ở runtime dùng `String[]`; tra cứu bằng `String[].class`.
- Với kiểu generic `List<String>`, metadata chữ ký đã qua **type erasure** dùng `List.class`. Không có biểu thức `List<String>.class` hợp lệ.
- Kiểu tham số là các đối tượng `Class<?>`; không truyền chuỗi `"String"` hay `"int"` vào API `getConstructor`.

Hai constructor overload này khác chữ ký:

```java
public User(String name) { /* ... */ }
public User(String name, int age) { /* ... */ }
```

Không được suy luận “Java tự chọn constructor khớp nhất” cho phương thức tra cứu: đây là phép tìm **chữ ký chính xác**, không phải phân giải overload khi compiler biên dịch lệnh `new User(...)`.

## 4. Ví dụ hoàn chỉnh Java 17: public so với declared

Ví dụ sau cố ý có bốn constructor: hai `public`, một `protected` và một `private`. Một lớp `Child` cũng được thêm vào để chứng minh constructor không được kế thừa.

Lưu **toàn bộ** vào tệp `ConstructorLookupDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class ConstructorLookupDemo {
    private static String signature(Constructor<?> ctor) {
        return "(" + Arrays.stream(ctor.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ")) + ")";
    }

    private static String signatures(Constructor<?>[] ctors) {
        return Arrays.stream(ctors).map(ConstructorLookupDemo::signature)
                .sorted().collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        Class<Account> type = Account.class;
        System.out.println("public: " + signatures(type.getConstructors()));
        System.out.println("declared: " + signatures(type.getDeclaredConstructors()));

        Constructor<Account> protectedOne =
                type.getDeclaredConstructor(String.class);
        System.out.println("declared String: "
                + Modifier.toString(protectedOne.getModifiers()));

        Constructor<Account> privateTwo =
                type.getDeclaredConstructor(String.class, int.class);
        System.out.println("private accessible: " + privateTwo.canAccess(null));
        try {
            privateTwo.newInstance("Ada", 3);
        } catch (IllegalAccessException expected) {
            System.out.println("private call: IllegalAccessException");
        }

        Constructor<Account> publicVarargs = type.getConstructor(int[].class);
        System.out.println("varargs marker: " + publicVarargs.isVarArgs());
        Account account = type.getConstructor().newInstance();
        System.out.println("created: " + account.label());

        try {
            type.getConstructor(String.class);
        } catch (NoSuchMethodException expected) {
            System.out.println("public String lookup: NoSuchMethodException");
        }

        System.out.println("child public: "
                + signatures(Child.class.getConstructors()));
    }
}

class Account {
    private final String owner;
    private final int level;

    public Account() { this("guest", 0); }
    protected Account(String owner) { this(owner, 1); }
    private Account(String owner, int level) {
        this.owner = owner;
        this.level = level;
    }
    public Account(int... levels) { this("levels", levels.length); }

    public String label() { return owner + ":" + level; }
}

class Parent {
    public Parent(int value) {}
}

class Child extends Parent {
    public Child() { super(0); }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ConstructorLookupDemo.java
java ConstructorLookupDemo
```

Kết quả chuẩn, đã kiểm tra bằng JDK 21 với `javac --release 17`:

```text
public: [(), (int[])]
declared: [(), (String), (String, int), (int[])]
declared String: protected
private accessible: false
private call: IllegalAccessException
varargs marker: true
created: guest:0
public String lookup: NoSuchMethodException
child public: [()]
```

### 4.1. Tại sao danh sách public và declared khác nhau?

`Account.class.getConstructors()` thấy đúng hai constructor `public`: `Account()` và `Account(int... levels)`. Tại bytecode level, varargs biểu diễn bằng mảng `int[]` nên chương trình in chữ ký `(int[])`.

`Account.class.getDeclaredConstructors()` thấy **cả bốn** constructor khai báo ngay trong `Account`: hai `public`, một `protected`, một `private`. Mỗi thành viên trả về dưới dạng đối tượng `Constructor<?>`.

Để kết quả dễ đọc và có thể kiểm thử, hàm `signatures` dùng `sorted()`. **Không dùng thứ tự mảng do Reflection trả về làm thứ tự ưu tiên**, ví dụ không chọn `getDeclaredConstructors()[0]` rồi giả định đó là constructor không tham số.

### 4.2. Vì sao getDeclaredConstructor thành công nhưng không gọi được?

`getDeclaredConstructor(String.class, int.class)` tìm được constructor `private`. Tuy vậy, chương trình `ConstructorLookupDemo` là **lớp top-level độc lập** với `Account`, nên không có quyền gọi constructor `private` thông thường.

- `privateTwo.canAccess(null)` trả `false`.
- `privateTwo.newInstance("Ada", 3)` ném `IllegalAccessException`.
- Không có lời gọi `setAccessible(true)` trong chương trình.

Điểm này minh họa hai khía cạnh độc lập: **tra cứu metadata** và **quyền sử dụng metadata để tạo đối tượng**. Nếu đặt caller bên trong một nestmate hợp lệ của lớp khai báo, hoặc có cấu hình quyền truy cập khác, kết quả kiểm tra có thể khác.

### 4.3. Vì sao getConstructor(String.class) báo không có constructor?

`Account` có `protected Account(String owner)`, nên phiên bản `getDeclaredConstructor(String.class)` thành công. `getConstructor(String.class)` chỉ tìm constructor `public` và ném `NoSuchMethodException`, dù chữ ký tồn tại. Đây là lỗi lựa chọn **API tra cứu**, không phải do Java không nhận ra `String.class`.

### 4.4. Vì sao constructor của Parent không xuất hiện ở Child?

`Parent` khai báo `public Parent(int value)`; `Child` chỉ khai báo `public Child()`. `Child.class.getConstructors()` do đó chỉ có `Child()`. Mỗi constructor khởi tạo một lớp cụ thể; lệnh `super(0)` bên trong `Child()` gọi constructor cha theo cơ chế khởi tạo đối tượng thông thường, **không làm constructor cha trở thành thành viên kế thừa**.

## 5. Đọc metadata từ Constructor<?>

Sau khi tìm được đối tượng `Constructor<?>`, có thể xem các thông tin sau:

| API | Ý nghĩa |
| --- | --- |
| `getDeclaringClass()` | Lớp khai báo và sở hữu constructor |
| `getParameterCount()` | Số tham số trong chữ ký runtime |
| `getParameterTypes()` | Mảng kiểu tham số dạng `Class<?>[]` theo thứ tự |
| `getGenericParameterTypes()` | Kiểu tham số dạng `Type[]`, hỗ trợ phân tích generic signature khi có |
| `getParameters()` | Mảng `Parameter[]` để xem tên/annotation/modifier của tham số |
| `getExceptionTypes()` | Các kiểu checked/unchecked exception được khai báo trong `throws` |
| `getModifiers()` | Modifier của constructor, kết hợp `Modifier.isPublic`, `isPrivate`, `isProtected` |
| `isVarArgs()` | Constructor có khai báo biến tham số `...` hay không |
| `isSynthetic()` | Constructor có được compiler sinh dưới dạng synthetic hay không |
| `isAnnotationPresent(...)` | Kiểm tra annotation runtime trên constructor |

Ví dụ đoạn sau đặt **bên trong một phương thức**, giả định `Account` giống phần trước:

```java
Constructor<Account> ctor =
        Account.class.getDeclaredConstructor(String.class, int.class);

System.out.println(ctor.getDeclaringClass().getSimpleName()); // Account
System.out.println(ctor.getParameterCount());                 // 2
System.out.println(Modifier.isPrivate(ctor.getModifiers())); // true
```

Nếu dùng `getParameters()[i].getName()` để làm tài liệu API, cần nhớ **tên tham số thực tế không luôn được giữ trong class file**. Trong ví dụ Java thuần, thêm cờ `javac -parameters ...` nếu cần lưu tên tham số, nếu không có thể nhận tên tổng hợp như `arg0`, `arg1`. Để phân tích annotation hoặc generic type thực sự, ưu tiên API metadata tương ứng thay vì suy luận từ `toString()`.

Có thể dùng `Constructor.toGenericString()` để xem biểu diễn dễ đọc; nhưng nếu cần output bền vững giữa môi trường, hãy trích các trường metadata một cách có cấu trúc và tự định dạng.

## 6. Tra cứu metadata khác với tạo object

`getConstructor(...)` và `getDeclaredConstructor(...)` chỉ tìm chữ ký; chưa thực thi code khởi tạo. Sau lookup, `ctor.newInstance(args)` mới kiểm tra quyền, đối số và tạo instance. Chẳng hạn, từ ví dụ `Account` phía trên: `Account.class.getConstructor().newInstance().label()` trả `guest:0`.

Constructor khai báo varargs như `Account(int... levels)` có chữ ký runtime là `int[]`. Muốn truyền một mảng như một argument, dùng `getConstructor(int[].class).newInstance((Object) new int[]{1, 2, 3})`. Đối số phải khớp chữ ký đã chọn; Reflection không phân giải overload khi lookup.

## 7. Đã tìm thấy constructor nhưng không gọi được

`getDeclaredConstructor` thấy cả constructor `private`; nó không bỏ qua Java access checks. `canAccess(null)` kiểm tra trạng thái truy cập hiện tại với `Constructor`. Nếu framework cần deep reflection, `trySetAccessible()` có thể trả `false` vì JPMS: package trong named module thường phải được `opens` thích hợp. Vì vậy cần xem cả quyền truy cập của declaring class, không chỉ modifier constructor.

Ưu tiên public API/factory khi có thể. Nếu buộc mở quyền, kiểm tra kết quả và xử lý `IllegalAccessException` hoặc `InaccessibleObjectException` một cách minh bạch.

## 8. Những chữ ký khác cú pháp Java thông thường

- Không có lời gọi `getConstructor()` thành công nếu class chỉ khai báo constructor có tham số; compiler không tự sinh no-arg constructor trong trường hợp này.
- Non-static inner class có thêm tham số enclosing instance ở đầu, khác với static nested class.
- Generic `List<String>` bị erasure còn `List.class` khi lookup; varargs `String...` trở thành `String[].class`.
- Abstract class có thể có constructor nhưng không tạo được object trực tiếp; interface, array và primitive không có constructor class thông thường. Constructor enum có giới hạn tạo instance riêng.
- Constructor của superclass không xuất hiện trong danh sách constructor của subclass, dù code subclass gọi `super(...)`.

Những trường hợp đó không thay đổi quy tắc chính: `Class.get[Declared]Constructor` khớp **chính xác số lượng, thứ tự, và kiểu runtime** của từng tham số.

## 9. Chẩn đoán đúng bước thất bại

| Kết quả | Kiểm tra đầu tiên |
| --- | --- |
| `NoSuchMethodException` | Chữ ký và phạm vi public/declared của API tra cứu |
| `IllegalAccessException` | Caller, declaring class, visibility và module |
| `IllegalArgumentException` | Số lượng và kiểu đối số thực tế của `newInstance` |
| `InstantiationException` | Class có abstract không |
| `InvocationTargetException` | `getCause()` để tìm throwable từ quá trình chạy constructor |
| `ExceptionInInitializerError` | Static initialization xảy ra trước constructor |

Không `catch (Exception ignored)` rồi suy luận mọi lỗi đều là tra cứu thất bại. Việc phân biệt lookup, access, khởi tạo class và khởi tạo instance giúp sửa đúng nguyên nhân.

## 10. Chọn chiến lược tra cứu trong ứng dụng

Nếu một framework muốn tạo đối tượng từ metadata, nên định nghĩa **quy tắc chọn constructor** minh bạch:

1. Biết rõ `Class<?>` đích, phạm vi constructor được hỗ trợ và liệu có cần các constructor không public.
2. Nếu có chữ ký cụ thể, ưu tiên `getConstructor(types...)` hoặc `getDeclaredConstructor(types...)` theo chính sách quyền.
3. Nếu cần khám phá nhiều constructor, lấy danh sách với `getConstructors()` hoặc `getDeclaredConstructors()`; **lọc theo loại tham số/annotation** và sắp xếp theo tiêu chí của ứng dụng.
4. Trước khi tạo đối tượng, kiểm tra kiểu tham số, khả năng truy cập, module và ngữ nghĩa nghiệp vụ; không sử dụng constructor ngẫu nhiên vì `array[0]` xuất hiện đầu tiên.
5. Khi chạy `newInstance`, phân biệt ngoại lệ từ cơ chế Reflection với lỗi phát sinh bên trong constructor.

Ví dụ, nếu đang tìm constructor `public` nhận một chuỗi, có thể gọi:

```java
Constructor<?> selected =
        type.getConstructor(String.class);
```

Đoạn trên phù hợp khi đã biết chính xác chữ ký; không cần duyệt toàn bộ danh sách. Ngược lại, nếu framework hỗ trợ injection nhiều tham số theo annotation và có quy tắc chọn overload, cần đọc toàn bộ metadata liên quan và xác định chiến lược chọn dứt khoát, thay vì thử từng constructor cho đến khi không ném lỗi.

Với class là một loại runtime có thể được tạo động, nhớ rằng sự tồn tại của constructor phù hợp chỉ chứng minh điều kiện **cần**, không phải toàn bộ điều kiện **đủ**: constructor có thể bị giới hạn quyền, khởi tạo lớp thất bại hoặc phần thân có side effect.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `Account.class.getConstructor(String.class)` không tìm được constructor dù lớp khai báo `Account(String)`?

**Đáp án:** Constructor đó là `protected`. `getConstructor` chỉ tìm constructor `public`; `getDeclaredConstructor(String.class)` tìm được vì xét mọi modifier.

**Câu 2.** Khác biệt giữa `Account.class.getConstructors()` và `Account.class.getDeclaredConstructors()` là gì?

**Đáp án:** Cách đầu liệt kê constructor `public`; cách thứ hai liệt kê toàn bộ constructor khai báo ngay trong `Account`, kể cả non-public.

**Câu 3.** Có thể lấy constructor `Account(int... values)` bằng `getConstructor(int.class)` không?

**Đáp án:** Không. Runtime signature dùng `int[]`, nên phải `getConstructor(int[].class)`.

**Câu 4.** `Child.class.getConstructors()` có chứa `Parent(int)` hay không?

**Đáp án:** Không. Constructor không kế thừa; `Child` chỉ có constructor của chính nó.

**Câu 5.** Vì sao tìm được một constructor `private` không bảo đảm `ctor.newInstance()` thành công?

**Đáp án:** Metadata lookup và kiểm tra quyền thực thi là hai việc độc lập. Caller ngoài quyền truy cập thông thường có thể bị `IllegalAccessException`, hoặc bị giới hạn bởi module khi cố bỏ qua kiểm tra.

**Câu 6.** Vì sao `getDeclaredConstructor(int.class)` có thể thất bại với `Outer.Inner` dù source viết `Inner(int)`?

**Đáp án:** Inner class không static có tham số outer-instance ngầm định trong chữ ký runtime, thường cần tìm với `(Outer.class, int.class)`.

**Câu 7.** Có thể dùng `Constructor.newInstance` để tạo enum constant mới không?

**Đáp án:** Không. Reflection không cho phép tạo enum mới qua constructor theo cách này.

**Ghi nhớ:** `getConstructor(s)` tra cứu **constructor public của chính class**, còn `getDeclaredConstructor(s)` tra cứu **mọi constructor khai báo trực tiếp trong class**. Cả hai đều dựa trên **đúng danh sách kiểu tham số**; việc có metadata chưa đồng nghĩa có quyền gọi. Với code runtime linh hoạt, hãy xem modifier, declaring class, varargs/generic signature và giới hạn của `newInstance` trước khi khởi tạo đối tượng.
