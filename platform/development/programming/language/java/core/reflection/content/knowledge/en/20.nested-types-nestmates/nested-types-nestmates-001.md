# `getClasses()` khác `getDeclaredClasses()` trong Java Reflection

## 1. Hai phương thức trả về điều gì?

Khi dùng Reflection, mỗi đối tượng `Class<?>` mô tả một kiểu Java. Hai phương thức sau đều trả về `Class<?>[]` đại diện cho **kiểu thành viên lồng bên trong** (member class/member interface) của kiểu đang xét:

- `clazz.getClasses()`: lấy **các kiểu thành viên `public`** được khai báo ở chính kiểu đó **và các kiểu thành viên `public` được kế thừa từ lớp cha**.
- `clazz.getDeclaredClasses()`: lấy **tất cả kiểu thành viên khai báo trực tiếp** trong kiểu đó, bất kể `public`, `protected`, package-private hay `private`; **không lấy kiểu thành viên được kế thừa**.

Tên phương thức có ý nghĩa quan trọng: `getClasses()` hướng tới *public members* nhìn theo lớp hiện tại; `getDeclaredClasses()` hướng tới *declarations* trực tiếp ở lớp hiện tại. Cả hai trả về **kiểu thành viên** (nested types), không phải mọi lớp mà chương trình sử dụng, mọi kiểu trong package hay tất cả lớp đã được JVM nạp.

| Tiêu chí | `getClasses()` | `getDeclaredClasses()` |
| --- | --- | --- |
| Điều kiện truy cập | Chỉ thành viên `public` | Mọi mức truy cập |
| Thành viên khai báo trực tiếp | Có, nếu `public` | Có, không phân biệt mức truy cập |
| Thành viên từ lớp cha | Có, nếu là thành viên `public` được kế thừa | Không |
| Lớp local trong phương thức | Không | Không |
| Lớp anonymous tạo trong phương thức | Không | Không |
| Kiểu lồng trong một kiểu thành viên khác | Không tự đệ quy | Không tự đệ quy |
| Kiểu dữ liệu trả về | `Class<?>[]` | `Class<?>[]` |

**Member type** là kiểu được khai báo trực tiếp trong phần thân của một class hoặc interface. Nhóm này có thể gồm nested class, nested interface, enum, record và annotation interface. Nested class có thể là `static` hoặc inner class không `static`; sự khác biệt giữa hai phương thức ở đây dựa vào **quyền truy cập và nơi khai báo**, không dựa vào việc lớp lồng có `static` hay không.

## 2. Ví dụ chạy được trên Java 17+

Lưu toàn bộ chương trình dưới tên **`NestedReflectionDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestedReflectionDemo {
    public static class Base {
        public static class BasePublic {}
        protected static class BaseProtected {}
        private static class BasePrivate {}
    }

    public static class Derived extends Base {
        public static class OwnPublic {}
        protected static class OwnProtected {}
        static class OwnPackage {}
        private static class OwnPrivate {}
        public interface Marker {}
        public enum State { READY }
        public record Key(int id) {}

        public void sample() {
            class Local {}
            Object anonymous = new Object() {};
        }
    }

    private static void show(String label, Class<?>[] types) {
        String names = Arrays.stream(types)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " -> " + names);
    }

    public static void main(String[] args) {
        show("getClasses()", Derived.class.getClasses());
        show("getDeclaredClasses()", Derived.class.getDeclaredClasses());
        show("Base.getDeclaredClasses()", Base.class.getDeclaredClasses());
    }
}
```

Biên dịch và chạy:

```bash
javac NestedReflectionDemo.java
java NestedReflectionDemo
```

Kết quả:

```text
getClasses() -> [BasePublic, Key, Marker, OwnPublic, State]
getDeclaredClasses() -> [Key, Marker, OwnPackage, OwnPrivate, OwnProtected, OwnPublic, State]
Base.getDeclaredClasses() -> [BasePrivate, BaseProtected, BasePublic]
```

Chương trình cố ý dùng `sorted()` trước khi in vì **API không cam kết thứ tự phần tử** trong các mảng trả về. Kết quả đã được kiểm tra khi biên dịch và chạy; các tên được in theo thứ tự chữ cái.

### Giải thích kết quả

1. `Derived.class.getClasses()` có `OwnPublic`, `Marker`, `State`, `Key` vì chúng là kiểu thành viên `public` khai báo tại `Derived`. Nó còn có `BasePublic` vì kiểu này là thành viên `public` được kế thừa từ `Base`.
2. `Derived.class.getClasses()` **không có** `OwnProtected`, `OwnPackage`, `OwnPrivate`, `BaseProtected` hoặc `BasePrivate`: các kiểu đó không phải thành viên `public` được trả về.
3. `Derived.class.getDeclaredClasses()` có đầy đủ bảy kiểu thành viên khai báo trực tiếp tại `Derived`, từ `public` đến `private`; **không có** `BasePublic` vì `BasePublic` được khai báo ở `Base`.
4. `Base.class.getDeclaredClasses()` cho thấy cả ba kiểu được khai báo trực tiếp tại `Base`. Việc kiểu đó `private` hay `protected` không khiến nó bị loại khỏi kết quả của `getDeclaredClasses()`.
5. `Local` và lớp anonymous trong `sample()` không xuất hiện trong hai kết quả: chúng nằm trong phương thức, không phải member type khai báo trực tiếp trong thân `Derived`.

**Điểm dễ nhầm:** `getDeclaredClasses()` cho phép *nhìn thấy metadata* của kiểu `private`, nhưng điều này không tự động cho phép truy cập constructor, field hay method không công khai của kiểu đó. Quyền truy cập khi thao tác sâu hơn bằng Reflection vẫn chịu các quy tắc truy cập và giới hạn module của Java.

## 3. Phạm vi khai báo và phạm vi kế thừa

Xét cấu trúc:

```text
Base
├── public BasePublic
├── protected BaseProtected
└── private BasePrivate
     ↑
   Derived extends Base
   ├── public OwnPublic
   ├── protected OwnProtected
   ├── package-private OwnPackage
   ├── private OwnPrivate
   ├── public Marker (interface)
   ├── public State (enum)
   └── public Key (record)
```

- Muốn biết `Derived` **tự khai báo** những nested types nào, dùng `Derived.class.getDeclaredClasses()`.
- Muốn biết các **public member types của `Derived`**, bao gồm loại được kế thừa từ superclass, dùng `Derived.class.getClasses()`.
- Muốn khảo sát **mọi nested type được khai báo trong từng lớp của chuỗi kế thừa**, phải duyệt từng lớp rồi gọi `getDeclaredClasses()` riêng. Kết quả khảo sát như vậy **không đồng nghĩa** với các thành viên thực sự có thể kế thừa/truy cập ở lớp con; ví dụ, thành viên `private` của lớp cha vẫn xuất hiện khi khảo sát trực tiếp lớp cha.

Ví dụ minh họa cách duyệt lớp cha (đoạn dưới là fragment đặt trong một phương thức có sẵn biến `Class<?> target`):

```java
for (Class<?> current = target;
     current != null;
     current = current.getSuperclass()) {
    for (Class<?> nested : current.getDeclaredClasses()) {
        System.out.println(current.getName() + " declares " + nested.getName());
    }
}
```

Vòng lặp này chỉ đi theo **superclass chain** và in ra những khai báo trực tiếp của từng lớp; nó không tự duyệt superinterface hay các kiểu lồng nhiều tầng. Khi cần xử lý interface hoặc nested type đệ quy, phải xác định rõ tiêu chí tìm kiếm và bổ sung việc duyệt tương ứng.

## 4. Không nhầm với các API liên quan

- `getDeclaringClass()`: từ một kiểu thành viên, tìm kiểu **khai báo trực tiếp** nó. Ví dụ, `Derived.OwnPublic.class.getDeclaringClass()` trả về `Derived.class`.
- `getEnclosingClass()`: tìm lớp bao quanh về mặt khai báo; hữu ích cả với một số trường hợp local/anonymous class. Đây là câu hỏi khác với việc liệt kê member types.
- `getNestHost()` và `getNestMembers()`: nói về **nestmate** của JVM, liên quan đến quy tắc truy cập private giữa các lớp cùng nest. Danh sách nestmate không phải là kết quả tương đương của `getDeclaredClasses()` hay `getClasses()`.
- `getDeclaredMethods()`, `getDeclaredFields()` và `getDeclaredConstructors()`: liệt kê các loại thành viên khác, không thay thế cho việc tìm nested class/interface.

Hai phương thức chính đều chỉ xét **một cấp member type**. Nếu `Outer` khai báo `Inner` và `Inner` lại khai báo `Deep`, thì `Outer.class.getDeclaredClasses()` có thể chứa `Inner`, nhưng **không trực tiếp chứa `Deep`**. Muốn tìm `Deep`, tiếp tục xét `Inner.class.getDeclaredClasses()`.

## 5. Chọn phương thức trong thực tế

| Nhu cầu | Lựa chọn và lý do |
| --- | --- |
| Hiển thị các nested type `public` mà một lớp cung cấp cho người dùng API, kể cả loại kế thừa | `getClasses()` |
| Viết công cụ phân tích cấu trúc khai báo của một lớp, kể cả nested type `private` | `getDeclaredClasses()` |
| Tìm tất cả khai báo nested type ở nhiều lớp trong chuỗi kế thừa | Duyệt superclass và gọi `getDeclaredClasses()` trên từng lớp |
| Tìm lớp local, anonymous hoặc mọi class đã nạp | Hai phương thức trên không giải quyết trực tiếp |
| Tìm thành viên của nested type ở độ sâu lớn hơn một cấp | Tự duyệt đệ quy từ các member type tìm được |

Khi xây dựng bộ quét metadata, có thể cần xử lý kiểu trùng tên đơn giản ở nhiều lớp. Để định danh chắc chắn, nên dùng `Class.getName()` hoặc so sánh chính đối tượng `Class<?>`, thay vì chỉ dựa vào `getSimpleName()`. Cũng không nên dựa vào vị trí phần tử trong mảng vì thứ tự không được bảo đảm.

## 6. Những lỗi hiểu sai thường gặp

1. **“`getDeclaredClasses()` lấy cả kiểu của cha vì nó lấy mọi mức truy cập.”** Sai. “Declared” giới hạn vào những member types **khai báo trực tiếp tại kiểu nhận lệnh gọi**.
2. **“`getClasses()` lấy tất cả nested class của lớp hiện tại.”** Sai. Nó chỉ trả về **public member types**; `protected`, package-private và `private` bị loại.
3. **“Hai API chỉ nhận `static nested class`.”** Sai. Inner member class không `static` cũng là một kiểu thành viên và được xử lý theo cùng quy tắc về nơi khai báo/quyền truy cập.
4. **“`getDeclaredClasses()` trả về lớp local và anonymous.”** Sai. Chúng không phải member classes khai báo trực tiếp trong thân kiểu đang xét.
5. **“Phần tử đầu tiên luôn là kiểu khai báo đầu tiên.”** Sai. Không có hợp đồng về thứ tự; phải sắp xếp trước khi cần output ổn định.
6. **“Thấy `private nested class` trong kết quả có nghĩa gọi được constructor private.”** Sai. Liệt kê metadata và quyền truy cập để tạo đối tượng/gọi thành viên là hai vấn đề khác nhau.

## 7. Tự kiểm tra

**Câu hỏi:** Nếu `Parent` có `public static class Shared` và `private static class Secret`, còn `Child extends Parent` có `private static class Internal`, thì:

- `Child.class.getClasses()` có kiểu nào trong ba kiểu trên?
- `Child.class.getDeclaredClasses()` có kiểu nào trong ba kiểu trên?
- Cách nào tìm được `Secret` bằng Reflection?

**Đáp án:** `getClasses()` của `Child` có `Shared`; `getDeclaredClasses()` của `Child` có `Internal`; muốn liệt kê metadata của `Secret` thì gọi `Parent.class.getDeclaredClasses()`. Đây là ví dụ điển hình cho việc **`public` + kế thừa** khác với **khai báo trực tiếp + mọi mức truy cập**.

## Tài liệu tham khảo

- [Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): hợp đồng của `getClasses()`, `getDeclaredClasses()` và các phương thức liên quan.
- [Java Language Specification, `8.5 — Member Class and Interface Declarations`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.5): định nghĩa member classes và member interfaces.
