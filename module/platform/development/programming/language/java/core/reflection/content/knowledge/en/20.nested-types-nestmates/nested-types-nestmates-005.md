# Static nested class khác non-static inner class trong Java

## 1. Bản chất của hai loại member class

Trong Java, một lớp có thể được khai báo trực tiếp bên trong thân lớp khác. Hai hình thức **member class** thường gặp là:

- **Static nested class**: member class có từ khóa `static`. Mỗi đối tượng của nó **không cần gắn với một đối tượng** của lớp bao ngoài (`enclosing instance`).
- **Non-static inner class** (thường gọi ngắn là **inner class**): member class không có `static`. Khi được khởi tạo theo cách thông thường, mỗi đối tượng của nó gắn với **một đối tượng cụ thể** của lớp bao ngoài.

Ví dụ cú pháp:

```java
class Outer {
    static class Nested { }
    class Inner { }
}
```

Cả hai đều là kiểu thành viên của `Outer` và có tên nguồn `Outer.Nested`, `Outer.Inner`. Từ khóa `static` ở đây nói về **mối quan hệ với đối tượng bao ngoài**, không biến mọi thành viên hay mọi phương thức bên trong `Nested` thành `static`.

> Điểm cốt lõi: `Outer.Nested` được tạo độc lập với instance `Outer`; còn một instance `Outer.Inner` cần một enclosing instance `Outer`.

## 2. So sánh nhanh

| Tiêu chí | `static class Nested` | `class Inner` |
| --- | --- | --- |
| Có enclosing instance `Outer` ngầm định? | Không | Có, khi khởi tạo như member inner class |
| Khởi tạo ngoài `Outer` | `new Outer.Nested()` | `outer.new Inner()` |
| Đọc trực tiếp trường instance của `Outer` | Không; cần tham chiếu `Outer` tường minh | Có; qua enclosing instance |
| Đọc trực tiếp thành viên `static` của `Outer` | Có (theo phạm vi truy cập) | Có (theo phạm vi truy cập) |
| Truy cập thành viên `private` của `Outer` | Có thể, nếu có tham chiếu đối tượng khi cần | Có thể, gồm trường instance của enclosing instance |
| Tham chiếu `Outer.this` | Không hợp lệ | Hợp lệ trong ngữ cảnh có enclosing instance |
| Kiểu dùng trong Reflection | `isMemberClass()==true`, `Modifier.isStatic(... )==true` | `isMemberClass()==true`, `Modifier.isStatic(... )==false` |
| Constructor thể hiện qua Reflection | Không có tham số enclosing instance do tư cách static nested | Với member inner class thông thường, có thêm tham số `Outer` đứng đầu |

**Lưu ý về `private`:** Hai lớp trong cùng nest của Java có thể truy cập các thành viên private của nhau theo quy tắc ngôn ngữ/JVM. Vì thế, **khả năng truy cập private không phải điểm phân biệt** giữa static nested và inner; điểm phân biệt là có hay không có đối tượng bao ngoài ngầm định.

## 3. Khởi tạo và truy cập trạng thái — ví dụ chạy được

Lưu toàn bộ chương trình dưới tên `NestedVsInnerDemo.java`:

```java
import java.lang.reflect.Modifier;

public class NestedVsInnerDemo {
    private final String label;
    private static int created;

    public NestedVsInnerDemo(String label) {
        this.label = label;
        created++;
    }

    public static class StaticNested {
        public String count() {
            return "Đã tạo outer: " + created;
        }

        public String labelOf(NestedVsInnerDemo outer) {
            return outer.label; // private hợp lệ; outer truyền tường minh
        }
    }

    public class Inner {
        private final int id;

        public Inner(int id) {
            this.id = id;
        }

        public String describe() {
            return label + " #" + id; // label thuộc enclosing instance
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        NestedVsInnerDemo a = new NestedVsInnerDemo("A");
        NestedVsInnerDemo b = new NestedVsInnerDemo("B");

        StaticNested nested = new StaticNested();
        Inner first = a.new Inner(1);
        Inner second = b.new Inner(2);

        System.out.println(nested.count());
        System.out.println(nested.labelOf(a));
        System.out.println(first.describe());
        System.out.println(second.describe());

        Class<?> staticType = StaticNested.class;
        Class<?> innerType = Inner.class;
        System.out.println(Modifier.isStatic(staticType.getModifiers()));
        System.out.println(Modifier.isStatic(innerType.getModifiers()));
        System.out.println(
                staticType.getDeclaredConstructor().getParameterCount());
        System.out.println(
                innerType.getDeclaredConstructor(
                        NestedVsInnerDemo.class, int.class)
                        .getParameterCount());
        System.out.println(
                innerType.getNestHost() == NestedVsInnerDemo.class);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 NestedVsInnerDemo.java
java NestedVsInnerDemo
```

Kết quả chuẩn:

```text
Đã tạo outer: 2
A
A #1
B #2
true
false
0
2
true
```

Giải thích từng quan sát:

1. `new StaticNested()` không cần instance `NestedVsInnerDemo`. Phương thức `count()` đọc trường `created` mang tính lớp; `labelOf(a)` muốn đọc `label` phải nhận `a` một cách tường minh.
2. `a.new Inner(1)` và `b.new Inner(2)` tạo hai inner object gắn với hai outer object khác nhau. Cùng phương thức `describe()` nhưng kết quả mang nhãn `A` và `B`.
3. `Modifier.isStatic(Class#getModifiers())` cho kết quả `true` với static nested class, `false` với non-static inner class.
4. Trong Reflection, constructor của `StaticNested` không tham số; constructor `Inner(int)` xuất hiện với **hai** tham số: enclosing `NestedVsInnerDemo` đứng trước `int`. Đây là một chi tiết quan trọng khi gọi `getDeclaredConstructor(...)`.
5. `Inner.class.getNestHost()` trỏ đến lớp bao ngoài; điều này phản ánh **nest membership** của JVM và không có nghĩa mọi nested class đều giữ tham chiếu đến một outer instance.

## 4. Tại sao cách khởi tạo khác nhau?

Với static nested class:

```java
Outer.Nested n = new Outer.Nested();
```

Với non-static member inner class:

```java
Outer outer = new Outer();
Outer.Inner i = outer.new Inner();
```

Ở câu lệnh thứ hai, biểu thức `outer` chỉ rõ đối tượng bao ngoài nào được gắn với `i`. Trong một phương thức instance của `Outer`, ta cũng có thể viết `new Inner()`, vì `this` của `Outer` đang hiện diện. Trong `static` method của `Outer`, không có `Outer.this` nên không thể gọi `new Inner()` nếu chưa tạo/chỉ định outer instance.

Hai cách viết dễ nhầm:

```java
class Outer {
    static class Nested { }
    class Inner { }
}

// Hợp lệ:
Outer.Nested a = new Outer.Nested();
Outer host = new Outer();
Outer.Inner b = host.new Inner();

// Không hợp lệ (chỉ minh họa, KHÔNG đặt vào file chạy):
// Outer.Inner wrong1 = new Outer.Inner();
// Outer.Nested wrong2 = host.new Nested();
```

Một static nested class cũng có thể có **các instance field, instance method và constructor** của chính nó. `static` ở khai báo lớp lồng chỉ bỏ yêu cầu liên kết đến đối tượng `Outer`.

## 5. `this`, `Outer.this` và quyền truy cập

Bên trong `Inner`, `this` là đối tượng inner hiện tại; `Outer.this` là enclosing object. Cách truy cập được định vị theo phạm vi tên, nên có thể dùng qualified `this` để xử lý tên bị che khuất:

```java
class House {
    private String name = "nhà";

    class Room {
        private String name = "phòng";

        String describe() {
            return this.name + " trong " + House.this.name;
        }
    }
}
```

Trong `Room`, `House.this.name` đọc trực tiếp trạng thái outer object mà không cần truyền `House` vào constructor do người viết khai báo. Static nested class **không có** `House.this`; nếu cần `name` của một `House`, phải nhận `House` qua tham số, trường instance hoặc nguồn tham chiếu hợp lệ khác.

Cả hai loại member class vẫn chịu luật `public`, `protected`, package-private và `private` khi được dùng từ các vị trí ngoài enclosing class. Một static nested class có thể đọc `private static` member của `Outer`, và có thể đọc `private` instance member thông qua một `Outer` được truyền vào. Do đó không nên diễn đạt sai rằng static nested class “không truy cập được private của Outer”.

## 6. Góc nhìn bytecode và Reflection

Java source dùng `Outer.Inner`, nhưng tên nhị phân thông thường của member class là `Outer$Inner` (`Class#getName()` trả tên nhị phân). Hai file class sẽ thường là `Outer$Nested.class` và `Outer$Inner.class`. Ký tự `$` trong tên file **không đủ** để kết luận kiểu đó là static hay inner; hãy dùng metadata từ `Class`.

Có thể kiểm tra:

```java
Class<?> type = Outer.Inner.class;
boolean member = type.isMemberClass();
Class<?> owner = type.getDeclaringClass();
boolean staticMember =
        java.lang.reflect.Modifier.isStatic(type.getModifiers());
```

- `isMemberClass()` nhận diện **member class**, giúp phân biệt với local/anonymous class; cả static nested và member inner đều cho `true`.
- `getDeclaringClass()` trả `Outer.class` cho cả hai member class. `getEnclosingClass()` cũng cho biết lớp bao quanh trong trường hợp member class nhưng có ý nghĩa rộng hơn với local/anonymous class.
- `Modifier.isStatic(type.getModifiers())` giúp phân loại hai dạng member class đã nêu.
- `getDeclaredConstructors()` hoặc `getDeclaredConstructor(...)` cho thấy chữ ký constructor ở mức JVM. Constructor của member inner class thường có tham số outer đầu tiên; khi dùng Reflection để tạo nó phải truyền enclosing instance thích hợp.

Ví dụ cách tạo inner qua Reflection (đặt trong ngữ cảnh có `Outer` và `Outer.Inner` như trên):

```java
Outer outer = new Outer();
var ctor = Outer.Inner.class.getDeclaredConstructor(Outer.class);
Outer.Inner inner = ctor.newInstance(outer);
```

Ví dụ này áp dụng khi `Inner` được khai báo **không có tham số constructor tường minh** và constructor phản chiếu có thể truy cập từ nơi gọi. Nếu có constructor `Inner(int id)` như chương trình chính, cần tra `getDeclaredConstructor(Outer.class, int.class)` rồi gọi `newInstance(outer, id)`. Có thể cần `setAccessible(true)` khi thành viên không accessible, nhưng việc mở truy cập còn phụ thuộc cơ chế đóng gói của Java module system.

Đừng dựa vào tên trường do compiler tạo ra (ví dụ `this$0`) để tìm enclosing instance: tên, tối ưu hóa lưu trữ tham chiếu và cờ synthetic là chi tiết biên dịch có thể khác giữa compiler/JDK. Hãy dựa vào quan hệ ngữ nghĩa của Java, `getDeclaringClass()`, modifier và chữ ký constructor thực tế.

### “Nested” khác “nestmate” của JVM

Từ Java 11, JVM có khái niệm **nest host/nest members** phục vụ quyền truy cập private giữa những class cùng nest. `Class#getNestHost()` và `Class#getNestMembers()` phản ánh quan hệ này. **Static nested class cũng có thể là nestmate của Outer**; quan hệ nestmate không bắt buộc có enclosing instance. Ngược lại, `static` là thuộc tính của member class khi khai báo và tác động đến cách gắn outer instance. Vì vậy không thể nhìn riêng `getNestHost()` để suy ra một class có phải non-static inner hay không.

## 7. Một số ranh giới ngôn ngữ dễ nhầm

- **Inner class không đồng nghĩa với mọi lớp lồng.** Non-static member class là inner class; local class và anonymous class cũng thuộc nhóm inner class theo thuật ngữ Java. Bài này so sánh **hai member class**; dùng `isMemberClass()` trước khi suy luận bằng modifier.
- **Static nested class không kế thừa Outer.** `Outer.Nested` và `Outer.Inner` không tự động là subclass của `Outer`; chúng chỉ được khai báo trong không gian tên/phạm vi của `Outer`.
- **Generic type của Outer:** một member inner class có thể dùng type parameter của enclosing class, ví dụ `class Box<T> { class Entry { T value; } }`. Static nested class không tự dùng `T` của `Box<T>`; nó cần tự khai báo type parameter, ví dụ `static class Entry<U> { U value; }`.
- **Static member trong inner class:** trên Java 17, inner class có thể khai báo static member theo quy tắc hiện hành. Câu nói “inner class tuyệt đối không có static member” là kiến thức cũ và không nên áp dụng cho Java hiện đại (hạn chế đã được nới từ Java 16).
- **Class trong interface:** member class khai báo trong interface là `public static` ngầm định; nó không phải non-static inner class của một interface instance.
- **GC và vòng đời:** nếu một đối tượng inner còn tham chiếu đến enclosing instance, việc lưu inner trong cấu trúc sống lâu có thể giữ outer sống lâu ngoài dự định. Với callback/listener, cân nhắc static nested class nếu không cần trạng thái outer. Điều đó không có nghĩa cứ tạo inner class là gây memory leak.

## 8. Chọn loại nào trong thiết kế?

**Ưu tiên static nested class** khi kiểu lồng chỉ phục vụ tổ chức mã, builder, helper, result/DTO hoặc thuật toán và **không cần** dùng trực tiếp trạng thái của một đối tượng outer. Điều này khiến phụ thuộc vào outer instance rõ ràng hơn và tránh giữ outer reference vô tình.

**Dùng non-static inner class** khi mỗi đối tượng con có quan hệ tự nhiên, chặt chẽ với một outer instance và cần đọc/ghi trực tiếp trạng thái của đúng instance đó, ví dụ iterator hay view được gắn với trạng thái một collection. Khi dùng, chủ động cân nhắc tính đóng gói, vòng đời và số lượng instance được tạo.

Quy tắc nhận diện thực hành: hỏi **“Mỗi instance của lớp lồng có cần biết nó thuộc về instance Outer nào không?”** Nếu có, non-static inner có thể phù hợp; nếu không, static nested thường đơn giản hơn.

## 9. Tự kiểm tra

1. Vì sao `new Outer.Inner()` không hợp lệ bên ngoài instance context, nhưng `new Outer.Nested()` hợp lệ?
2. Hai object `a.new Inner()` và `b.new Inner()` sử dụng trạng thái outer khác nhau như thế nào?
3. Static nested class có được đọc trường `private` instance của `Outer` không? Cần điều kiện gì?
4. Vì sao Reflection thấy tham số `Outer` thêm vào constructor của member inner class?
5. `getNestHost() == Outer.class` có đủ chứng minh đó là non-static inner class không?

**Đáp án gợi ý:** (1) Inner cần enclosing instance; static nested thì không. (2) Mỗi inner gắn với đối tượng outer lúc tạo. (3) Có, nếu có tham chiếu `Outer` thích hợp và quyền truy cập hợp lệ. (4) Constructor cần biết enclosing object. (5) Không, static nested cũng có thể thuộc cùng nest.

**Ghi nhớ:** Hãy phân biệt ba câu hỏi độc lập khi đọc Reflection: *nó có được khai báo là member class không?* (`isMemberClass`), *member class đó có modifier static không?* (`Modifier.isStatic`), và *nó có cùng nest JVM với Outer không?* (`getNestHost`). Chỉ câu hỏi thứ hai phân biệt trực tiếp hai loại member class trong bài.