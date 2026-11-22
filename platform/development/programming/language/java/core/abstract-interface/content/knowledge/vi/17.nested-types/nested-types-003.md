# Phạm vi truy cập của kiểu lồng và cách tham chiếu trong Java

**Kiểu lồng (nested type)** là kiểu được khai báo bên trong một kiểu khác, chẳng hạn class, interface, enum hoặc record nằm trong một class. Khai báo lồng giúp nhóm những kiểu có quan hệ chặt chẽ, kiểm soát nơi có thể sử dụng chúng và thể hiện rõ kiểu nào thuộc về kiểu bao ngoài.

Để dùng kiểu lồng đúng cách, cần phân biệt hai câu hỏi: **kiểu được nhìn thấy ở đâu** (phạm vi và quyền truy cập) và **đối tượng được tạo hoặc kiểu được gọi bằng cú pháp nào** (tham chiếu kiểu lồng tĩnh hay kiểu lồng gắn với một đối tượng bên ngoài).

## 1. Các loại kiểu lồng

Java có một số cách khai báo kiểu bên trong kiểu hoặc khối lệnh khác:

- **Member nested class:** class được khai báo trực tiếp bên trong một class hoặc kiểu khác. Nó có thể là `static` hoặc non-static (inner class).
- **Local class:** class được khai báo trong thân một phương thức, constructor hoặc khối lệnh. Tên kiểu chỉ có hiệu lực trong phạm vi từ vị trí khai báo đến hết khối chứa nó.
- **Anonymous class:** lớp không có tên, được khai báo và khởi tạo tại một biểu thức; thường dùng để triển khai một interface hoặc mở rộng một class ngay tại chỗ.
- **Nested interface, enum và record:** các kiểu này có thể được khai báo bên trong kiểu khác. Nested interface, enum và record là kiểu lồng tĩnh về mặt ngữ nghĩa, nên không cần đối tượng của kiểu bao ngoài để tạo hoặc tham chiếu kiểu đó.

Không phải mọi kiểu được khai báo trong một class đều cần một instance của class bên ngoài. Điểm khác biệt quan trọng nhất là member class `static` so với member class non-static.

## 2. Phạm vi truy cập của member nested type

Với một kiểu lồng được khai báo trực tiếp trong kiểu khác, có thể dùng các mức truy cập `public`, `protected`, package-private (không ghi modifier) hoặc `private`. Các modifier này kiểm soát nơi mã khác được phép tham chiếu **tên kiểu lồng**.

| Modifier | Phạm vi sử dụng điển hình |
| --- | --- |
| `public` | Có thể được tham chiếu từ nơi nhìn thấy kiểu bao ngoài và kiểu lồng. |
| `protected` | Trong cùng package; ngoài package theo quy tắc truy cập `protected`, thường thông qua quan hệ kế thừa. |
| Không ghi modifier | Chỉ trong cùng package. |
| `private` | Trong phạm vi kiểu bao ngoài khai báo kiểu lồng đó. |

Ví dụ khai báo:

```java
public class Library {
    public static class PublicEntry { }
    protected static class ProtectedEntry { }
    static class PackageEntry { }
    private static class PrivateEntry { }
}
```

Các lớp bên ngoài có thể tham chiếu `Library.PublicEntry` khi các điều kiện truy cập khác cũng được đáp ứng. `Library.PrivateEntry` chỉ được dùng trong phạm vi `Library`; việc class bên ngoài có một đối tượng `Library` không làm nó có quyền truy cập kiểu private.

Một kiểu cấp cao nhất (top-level type) chỉ được khai báo `public` hoặc package-private; `private` và `protected` không hợp lệ cho top-level class/interface. Local class và anonymous class cũng không khai báo các modifier truy cập này.

## 3. `static` nested class và inner class khác nhau thế nào?

### `static` nested class

`static` nested class được gắn với tên kiểu bao ngoài, không gắn với một instance cụ thể của kiểu đó. Khi tạo nó, không cần tạo đối tượng bao ngoài trước.

```java
Library.Helper helper = new Library.Helper();
```

Ví dụ trên áp dụng nếu `Helper` là nested class có quyền truy cập phù hợp và constructor có thể được gọi từ vị trí đang viết mã. Từ bên trong `Library`, có thể thường dùng tên ngắn `Helper` nếu không có tên khác gây nhập nhằng.

`static` nested class không có tham chiếu ngầm định tới đối tượng bao ngoài. Vì vậy, nó không thể dùng trực tiếp các field hoặc method instance của `Library` như thể chúng thuộc về chính nó. Nếu cần dữ liệu instance, hãy truyền đối tượng vào qua constructor hoặc method:

```java
Library.Helper helper = new Library.Helper(library);
```

Constructor và chữ ký minh họa này cần được khai báo tương ứng trong `Helper`. Một static nested class vẫn có thể truy cập các thành viên `private` của kiểu bao ngoài khi có đối tượng tham chiếu thích hợp; `private` kiểm soát quyền truy cập theo ngôn ngữ, không bắt buộc phải là cùng một object.

### Non-static member class (inner class)

Inner class gắn với một instance cụ thể của kiểu bao ngoài. Muốn tạo nó từ bên ngoài phạm vi instance của kiểu bao ngoài, trước tiên cần có đối tượng bao ngoài rồi dùng cú pháp `outer.new InnerType()`.

```java
Library library = new Library();
Library.Worker worker = library.new Worker();
```

Đoạn này áp dụng nếu `Worker` là member inner class có thể truy cập được và constructor phù hợp có thể gọi từ vị trí đó. Mỗi đối tượng `Worker` được tạo theo cách này gắn với instance `library` cụ thể.

Bên trong inner class, có thể dùng trực tiếp các field và method instance của đối tượng bao ngoài. Khi cần làm rõ đối tượng đó, dùng `Library.this` (tên kiểu bao ngoài theo ví dụ) để lấy tham chiếu tới instance bao ngoài.

```java
System.out.println(Library.this.toString());
```

`Outer.this` chỉ dùng trong ngữ cảnh inner class thích hợp của `Outer`; không dùng được trong static nested class, static method hoặc mã không có enclosing instance tương ứng.

## 4. Truy cập thành viên `private` giữa kiểu bao ngoài và kiểu lồng

Kiểu lồng có thể truy cập các thành viên `private` của kiểu bao ngoài. Ngược lại, kiểu bao ngoài cũng có thể truy cập thành viên `private` của kiểu lồng. Đây là quyền truy cập giữa các kiểu thuộc cùng nhóm lồng (nest), được Java hỗ trợ theo quy tắc ngôn ngữ.

Điều này không làm các thành viên private trở thành public. Mã không liên quan ở bên ngoài vẫn không được phép truy cập trực tiếp chúng. Ngoài ra, quyền truy cập và việc có sẵn instance là hai vấn đề riêng:

- `static` nested class có thể đọc `Outer.privateStatic` trực tiếp trong phạm vi hợp lệ.
- Muốn dùng `Outer.privateInstance` từ static nested class, phải có một tham chiếu `Outer` thích hợp, ví dụ `outer.privateInstance`.
- Inner class có thể truy cập field hoặc method instance của enclosing object mà nó gắn với.
- `private` trên chính kiểu lồng vẫn giới hạn nơi khác có thể viết tên kiểu đó, kể cả khi constructor hoặc thành viên của kiểu có modifier rộng hơn.

## 5. Local class và anonymous class

### Local class

Local class được khai báo trong một block và chỉ dùng được trong block đó sau vị trí khai báo. Nó không có modifier truy cập như `public` hoặc `private` vì phạm vi đã được xác định bởi block.

Local class có thể truy cập các biến cục bộ và tham số của block bao quanh nếu chúng là `final` hoặc **effectively final** (giá trị không bị gán lại sau khi khởi tạo). Nếu được khai báo trong instance method, nó cũng có thể truy cập thành viên instance của enclosing object.

```java
void printPrefix(String prefix) {
    class Printer {
        void print(String value) {
            System.out.println(prefix + value);
        }
    }
    new Printer().print("Java");
}
```

Trong ví dụ, `prefix` được đọc nhưng không bị gán lại nên là effectively final. Nếu cố gán lại `prefix` sau khi dùng nó trong `Printer`, đoạn mã sẽ không biên dịch.

### Anonymous class

Anonymous class không có tên để khai báo biến theo kiểu lớp cụ thể. Biểu thức tạo lớp vô danh đồng thời tạo ra một instance, thường thông qua một interface hoặc superclass:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
task.run();
```

Không thể khai báo constructor có tên cho anonymous class vì nó không có tên lớp. Các method mới chỉ có trong phần thân anonymous class cũng không thể được gọi thông qua biến kiểu `Runnable` nếu không có một kiểu hoặc giao diện khai báo chúng.

## 6. Ví dụ Java hoàn chỉnh

Chương trình dưới đây cho thấy static nested class nhận tham chiếu tới đối tượng bao ngoài, inner class truy cập enclosing instance, cùng local và anonymous class được dùng trong phạm vi phương thức.

```java
public class NestedTypeAccessDemo {
    private final String name;
    private int visits;
    private static final String APPLICATION = "AccessDemo";

    public NestedTypeAccessDemo(String name) {
        this.name = name;
    }

    private void mark(String from) {
        visits++;
        System.out.println(from + " -> " + name + ", visits=" + visits);
    }

    private static class StaticNested {
        void show(NestedTypeAccessDemo outer) {
            System.out.println("static -> " + outer.name);
            outer.mark("static");
            System.out.println("app -> " + APPLICATION);
        }
    }

    private class Inner {
        void show() {
            System.out.println("inner -> " + name + " / " + NestedTypeAccessDemo.this.name);
            mark("inner");
        }
    }

    private void demonstrateScopedTypes() {
        class Local {
            void show() {
                System.out.println("local -> " + name);
            }
        }
        new Local().show();

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous -> " + name);
            }
        };
        anonymous.run();
    }

    public static void main(String[] args) {
        NestedTypeAccessDemo outer = new NestedTypeAccessDemo("Ada");

        StaticNested nested = new StaticNested();
        nested.show(outer);

        Inner inner = outer.new Inner();
        inner.show();

        outer.demonstrateScopedTypes();
    }
}
```

Lưu mã vào `NestedTypeAccessDemo.java`, sau đó biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac NestedTypeAccessDemo.java
java NestedTypeAccessDemo
```

Stdout chính xác:

```text
static -> Ada
static -> Ada, visits=1
app -> AccessDemo
inner -> Ada / Ada
inner -> Ada, visits=2
local -> Ada
anonymous -> Ada
```

Trong `StaticNested.show`, lớp lồng đọc field private qua `outer.name` và gọi `outer.mark(...)` bằng tham chiếu được truyền vào. Nó không cần enclosing instance ngầm định. `Inner.show` dùng được `name` và `mark` qua enclosing instance; `NestedTypeAccessDemo.this.name` làm rõ chính instance đó. `Local` và anonymous class được tạo, sử dụng trong phương thức chứa chúng.

Các kiểu `StaticNested` và `Inner` được khai báo private để ví dụ thể hiện quyền truy cập bên trong `NestedTypeAccessDemo`. Nếu cần dùng chúng từ class khác, phải chọn modifier phù hợp và giữ constructor/kiểu tham chiếu có thể truy cập được.

## 7. Quy tắc tham chiếu cần nhớ

| Trường hợp | Cú pháp thường dùng |
| --- | --- |
| Tham chiếu kiểu lồng tĩnh từ bên ngoài | `Outer.Nested` |
| Tạo đối tượng của kiểu lồng tĩnh | `new Outer.Nested()` |
| Tham chiếu inner class từ bên ngoài | `Outer.Inner` |
| Tạo inner class gắn với một đối tượng | `outer.new Inner()` |
| Lấy enclosing instance từ inner class | `Outer.this` |
| Tham chiếu local class | Tên lớp chỉ trong block khai báo |
| Anonymous class | Tạo trực tiếp qua biểu thức `new Type() { ... }` |

Các cú pháp trong bảng chỉ hợp lệ khi kiểu và constructor có thể truy cập tại vị trí gọi, và khi kiểu được khai báo đúng loại. Ví dụ, `outer.new Inner()` không áp dụng cho static nested class.

## 8. Lỗi thường gặp

1. **Dùng `new Outer.Inner()` cho inner class:** cú pháp này thiếu instance bao ngoài. Dùng `outer.new Inner()`.
2. **Tạo `Outer.StaticNested` với cú pháp `outer.new StaticNested()`:** static nested class không cần enclosing instance; dùng `new Outer.StaticNested()` khi kiểu có thể truy cập.
3. **Dùng `Outer.this` trong static nested class:** static nested class không có tham chiếu enclosing instance ngầm định. Truyền đối tượng bao ngoài vào nếu cần dữ liệu instance.
4. **Cho rằng nested class không thể truy cập private:** các kiểu lồng trong cùng nest có quyền truy cập private theo quy tắc Java. Điều này không cấp quyền cho mã không liên quan.
5. **Nhầm quyền truy cập của kiểu với quyền truy cập constructor:** muốn tạo instance, cả tên kiểu lẫn constructor phải có thể truy cập từ vị trí sử dụng.
6. **Cho rằng local variable nào cũng được capture:** biến cục bộ hoặc tham số được local/anonymous class sử dụng phải là `final` hoặc effectively final.
7. **Khai báo `private` hoặc `protected` cho top-level class:** modifier này chỉ hợp lệ cho member nested type trong ngữ cảnh phù hợp, không hợp lệ cho top-level type.

## Kết luận

Quyền truy cập quyết định nơi có thể nhắc tới kiểu lồng; `static` hay non-static quyết định kiểu đó có cần instance của kiểu bao ngoài hay không. Dùng `Outer.Nested` cho tên kiểu lồng tĩnh, `outer.new Inner()` cho inner class, và `Outer.this` khi cần tham chiếu rõ ràng tới enclosing instance. Local và anonymous class có phạm vi hẹp hơn, phù hợp khi kiểu chỉ cần phục vụ một đoạn xử lý.