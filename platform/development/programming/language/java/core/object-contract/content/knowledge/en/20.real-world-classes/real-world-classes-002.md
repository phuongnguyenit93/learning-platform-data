# Phân biệt kiểu khai báo với lớp thực tế của đối tượng trong Java

## 1. Hai loại thông tin trên cùng một biến tham chiếu

Khi đọc mã Java, cần phân biệt **kiểu khai báo** (*declared/static type*) của biến hoặc biểu thức với **lớp thực tế** (*runtime class*) của đối tượng mà tham chiếu đó đang trỏ tới.

```java
Animal pet = new Dog();
```

Đây là **một câu lệnh minh họa** (giả sử `Dog extends Animal`), chưa phải chương trình hoàn chỉnh:

- `Animal` là **kiểu khai báo** của biến `pet`, được trình biên dịch biết trong lúc kiểm tra mã.
- `new Dog()` tạo ra **đối tượng thực tế** thuộc lớp `Dog` lúc chương trình chạy.
- Biến `pet` giữ tham chiếu tới đối tượng `Dog`. Việc biến có kiểu `Animal` không biến đối tượng `Dog` thành đối tượng `Animal` thuần túy.
- Vì `Dog` là lớp con của `Animal`, phép gán này là **upcasting** hợp lệ và không cần ép kiểu tường minh.

Khái niệm tương tự áp dụng khi biến được khai báo bằng một **interface**:

```java
CharSequence text = new StringBuilder("Java");
```

Trong ví dụ này, `CharSequence` là kiểu khai báo, còn `StringBuilder` là lớp thực tế. Interface chỉ quy định hợp đồng mà đối tượng có thể thực hiện; interface tự nó không phải lớp cụ thể được tạo ra bằng `new CharSequence()`.

## 2. Trình biên dịch dùng kiểu khai báo để quyết định điều gì?

Kiểu khai báo chi phối những thao tác có thể viết **hợp lệ tại vị trí mã đang biên dịch**:

- Tên và chữ ký phương thức có thể gọi (phương thức phải được nhìn thấy và phù hợp qua kiểu khai báo).
- Thuộc tính có thể truy cập, bao gồm các quy tắc phạm vi truy cập và cách chọn **field**.
- Cách giải quyết **overloading**: chọn chữ ký khi có nhiều phương thức trùng tên nhưng khác danh sách tham số, dựa trên các kiểu được biết tại thời điểm biên dịch.
- Khả năng gán tham chiếu, các ràng buộc tham số generic và yêu cầu ép kiểu khi cần truy cập API chỉ có ở lớp con.

Ví dụ:

```java
Animal pet = new Dog();
pet.speak();     // Hợp lệ nếu Animal khai báo hoặc kế thừa speak()
// pet.fetch();  // LỖI BIÊN DỊCH nếu chỉ Dog có fetch()
```

Cho dù đối tượng thực tế là `Dog`, trình biên dịch chỉ biết rằng biểu thức `pet` có kiểu `Animal`, nên không cho phép gọi trực tiếp phương thức chỉ tồn tại ở `Dog` mà chưa kiểm tra/ép kiểu.

**Lưu ý về `var`:** `var pet = new Dog()` làm trình biên dịch **suy luận kiểu khai báo là `Dog`** tại chỗ khai báo. `var` không có nghĩa biến trở thành kiểu động hay tự thay đổi kiểu theo đối tượng ở các lần gán sau.

## 3. JVM dùng lớp thực tế để quyết định điều gì?

Đối với các **phương thức thể hiện có thể ghi đè** (overridable instance methods), sau khi chữ ký lời gọi đã được xác định hợp lệ, Java sử dụng **dynamic dispatch**: bản cài đặt được thực thi phụ thuộc vào lớp thực tế của receiver.

```java
class Animal {
    String speak() { return "Animal"; }
}

class Dog extends Animal {
    @Override
    String speak() { return "Dog"; }
}

// Trong một phương thức:
Animal pet = new Dog();
System.out.println(pet.speak()); // Dog
```

Đoạn trên là minh họa nhiều khai báo lớp và lời gọi, chưa phải tệp có `main`. Trình biên dịch chấp nhận `pet.speak()` vì kiểu `Animal` có phương thức `speak()`. Khi chạy, đối tượng receiver là `Dog`, nên bản ghi đè `Dog.speak()` được gọi.

**Không phải mọi thao tác đều dispatch theo lớp thực tế:** truy cập field, chọn overload, gọi phương thức `static` (method hiding) và việc chọn API hợp lệ vẫn phụ thuộc kiểu tại lúc biên dịch. Phương thức `private` không được ghi đè; `final` không thể bị ghi đè; constructor cũng không được override.

## 4. Ví dụ Java 17+ đầy đủ: phương thức, field, overload, cast và `getClass()`

Lưu chương trình sau vào tệp **`DeclaredVsRuntimeTypeDemo.java`**:

```java
public class DeclaredVsRuntimeTypeDemo {
    static class Animal {
        String label = "Animal field";

        String speak() {
            return "Animal.speak";
        }

        String describe(Animal other) {
            return "describe(Animal)";
        }
    }

    static class Dog extends Animal {
        String label = "Dog field";

        @Override
        String speak() {
            return "Dog.speak";
        }

        String describe(Dog other) {
            return "describe(Dog)";
        }

        String fetch() {
            return "fetch";
        }
    }

    static class ServiceDog extends Dog {}

    static class Cat extends Animal {}

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("declared Animal, speak: " + pet.speak());
        System.out.println("declared Animal, field: " + pet.label);
        System.out.println("runtime class: "
                + pet.getClass().getSimpleName());
        System.out.println("instanceof Dog: " + (pet instanceof Dog));
        System.out.println("overload via Animal: "
                + pet.describe(new Dog()));

        Dog dog = (Dog) pet;
        System.out.println("cast Dog, field: " + dog.label);
        System.out.println("overload via Dog: "
                + dog.describe(new Dog()));

        if (pet instanceof Dog matchedDog) {
            System.out.println("pattern instanceof: " + matchedDog.fetch());
        }

        Animal service = new ServiceDog();
        System.out.println("service instanceof Dog: "
                + (service instanceof Dog));
        System.out.println("service exact Dog class: "
                + (service.getClass() == Dog.class));

        Animal missing = null;
        System.out.println("null instanceof Dog: "
                + (missing instanceof Dog));
        try {
            missing.getClass();
        } catch (NullPointerException ex) {
            System.out.println("null.getClass: NullPointerException");
        }

        Animal cat = new Cat();
        try {
            Dog invalid = (Dog) cat;
            System.out.println(invalid.fetch());
        } catch (ClassCastException ex) {
            System.out.println("Cat cast to Dog: ClassCastException");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac DeclaredVsRuntimeTypeDemo.java
java DeclaredVsRuntimeTypeDemo
```

Kết quả:

```text
declared Animal, speak: Dog.speak
declared Animal, field: Animal field
runtime class: Dog
instanceof Dog: true
overload via Animal: describe(Animal)
cast Dog, field: Dog field
overload via Dog: describe(Dog)
pattern instanceof: fetch
service instanceof Dog: true
service exact Dog class: false
null instanceof Dog: false
null.getClass: NullPointerException
Cat cast to Dog: ClassCastException
```

Kết quả chỉ phụ thuộc vào quan hệ lớp và lời gọi được định nghĩa trong ví dụ, không phụ thuộc danh tính tham chiếu hay thứ tự collection.

## 5. Giải thích vì sao các dòng kết quả khác nhau

**Ghi đè phương thức — dùng lớp thực tế.** `pet.speak()` chạy bản của `Dog` dù `pet` được khai báo `Animal`, vì `speak()` là phương thức thể hiện được `Dog` override.

**Field hiding — dùng kiểu của biểu thức truy cập.** Cả `Animal` và `Dog` khai báo field cùng tên `label`. `pet.label` nhìn qua biểu thức kiểu `Animal` nên lấy `"Animal field"`; sau khi ép kiểu, `dog.label` nhìn qua kiểu `Dog` nên lấy `"Dog field"`. Field không có cơ chế override động như instance method. Tình huống hai field cùng tên thường nên tránh vì làm mã khó hiểu.

**Overloading — chọn chữ ký lúc biên dịch.** `pet.describe(new Dog())` chỉ thấy `describe(Animal)` qua kiểu khai báo `Animal`, nên chọn chữ ký này. Khi `dog.describe(new Dog())`, kiểu biểu thức là `Dog`, có cả `describe(Animal)` lẫn `describe(Dog)` và chọn chữ ký đặc hiệu hơn `describe(Dog)`. Trong chương trình này không có ghi đè `describe(Animal)` ở `Dog`, nên kết quả đầu tiên là của phương thức kế thừa.

**Cast không thay đổi đối tượng thực tế.** `(Dog) pet` chỉ tạo một biểu thức có kiểu `Dog` sau khi JVM kiểm tra đối tượng thực tế tương thích. Không có đối tượng mới và bản thân lớp của đối tượng không đổi. Nếu `pet` thực tế là `Cat`, ép xuống `Dog` ném `ClassCastException`.

**`instanceof` kiểm tra tương thích kiểu.** Một `ServiceDog` là lớp con của `Dog`, nên `service instanceof Dog` là `true` dù `service.getClass() == Dog.class` là `false` (lớp thực tế chính xác là `ServiceDog`). Trong Java 17, cú pháp `pet instanceof Dog matchedDog` vừa kiểm tra vừa khai báo biến đã được thu hẹp kiểu bên trong nhánh điều kiện.

## 6. `getClass()` và `instanceof` trả lời hai câu hỏi khác nhau

| Biểu thức | Câu hỏi được trả lời | Ví dụ `new ServiceDog()` |
| --- | --- | --- |
| `obj.getClass() == Dog.class` | Đối tượng có **lớp thực tế chính xác** là `Dog` không? | `false` |
| `obj instanceof Dog` | Đối tượng có là instance của `Dog` **hoặc lớp con của `Dog`** không? | `true` |
| `Dog.class.isInstance(obj)` | Kiểm tra tương thích runtime theo class token | `true` |
| `obj.getClass().getSuperclass()` | Lấy superclass trực tiếp của lớp runtime | `Dog.class` đối với `ServiceDog` |

`Object.getClass()` là phương thức `final` trả về đối tượng `Class<?>` đại diện **lớp thực tế** của receiver. Khi `obj == null`, `obj.getClass()` ném `NullPointerException`; `obj instanceof Dog` trả về `false` khi `obj` là `null`.

Trong hệ thống dùng proxy hoặc lớp con được framework tạo lúc chạy, `getClass()` có thể cho một **lớp proxy**. Vì vậy muốn biết một đối tượng có hỗ trợ interface/kiểu cơ sở hay không, thường nên kiểm tra bằng `instanceof` hoặc API framework thích hợp thay vì chỉ so sánh chính xác `getClass() == SomeClass.class`.

## 7. Liên hệ với hợp đồng `equals()` trong `object-contract`

`equals(Object)` được khai báo trong `java.lang.Object` và có thể được lớp con ghi đè. Vì thế:

```java
Object left = new ValueKey(7);
Object right = new ValueKey(7);
System.out.println(left.equals(right));
```

Đoạn trên giả sử một lớp `ValueKey` có `equals(Object)` thích hợp; tuy **kiểu khai báo của `left` là `Object`**, lời gọi `left.equals(right)` vẫn có thể chạy bản override của lớp runtime `ValueKey` và trả `true` theo giá trị. Nếu `ValueKey` không ghi đè `equals`, mặc định `Object.equals` so sánh danh tính và hai đối tượng `new` khác nhau thường không bằng nhau.

Khi cài đặt `equals`, hai cách kiểm tra kiểu thường gặp là:

```java
if (obj == null || getClass() != obj.getClass()) return false;

// Hoặc trong một chính sách cho phép kiểu con phù hợp:
if (!(obj instanceof ValueKey other)) return false;
```

Đây là **hai phương án thiết kế thay thế**, không phải hai lệnh phải dùng đồng thời. Cách `getClass()` đòi cùng lớp runtime chính xác; cách `instanceof` có thể chấp nhận lớp con. Dù chọn cách nào, `equals()` vẫn phải thỏa tính phản xạ, đối xứng, bắc cầu, nhất quán, xử lý `null`, đồng thời `hashCode()` phải đồng bộ. Đặc biệt, cho phép lớp con bằng lớp cha một chiều có thể vi phạm tính đối xứng hoặc bắc cầu nếu mỗi lớp dùng tiêu chí khác nhau.

Ví dụ lớp giá trị cuối cùng không cho kế thừa:

```java
final class ValueKey {
    private final int id;

    ValueKey(int id) { this.id = id; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof ValueKey other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
```

Đây là **khai báo lớp có thể biên dịch khi đặt vào một tệp Java thích hợp**, không phải chương trình có `main`. Vì `ValueKey` là `final`, kiểm tra `instanceof ValueKey` không tạo vấn đề với các lớp con tự định nghĩa; hai đối tượng `new ValueKey(7)` được coi là bằng nhau theo `id`. Lời gọi `equals` vẫn dispatch về `ValueKey.equals` dù tham chiếu được khai báo là `Object`.

## 8. Ép kiểu an toàn và giới hạn cần nhớ

**Upcast** (lớp con sang lớp cha/interface) là chuyển đổi tham chiếu hợp lệ: `Animal pet = new Dog()`. Nhưng bạn chỉ gọi trực tiếp được các phương thức mà kiểu khai báo nhìn thấy.

**Downcast** (lớp cha/interface sang lớp con) cần kiểm tra runtime: `Dog d = (Dog) pet`. Nếu lớp thực tế không tương thích, JVM ném `ClassCastException`. Java 17 có pattern matching cho `instanceof` để xử lý an toàn và gọn hơn:

```java
if (pet instanceof Dog d) {
    System.out.println(d.fetch());
}
```

Đoạn trên giả định `pet`, `Dog` và `fetch()` như ví dụ lớn. `instanceof` không khiến một đối tượng `Animal` thuần túy trở thành `Dog`; nó chỉ **kiểm tra rồi làm rõ kiểu của tham chiếu** trong nhánh hợp lệ.

**`null` không có lớp thực tế.** Biến `Animal pet = null;` vẫn có kiểu khai báo `Animal`, nhưng không trỏ tới đối tượng nào. Không nên gọi phương thức thể hiện qua `pet` khi nó là `null`. Kiểm tra `pet == null` hoặc `pet instanceof Dog` tùy mục đích (vế sau trả `false` với `null`).

**Generic type không khôi phục trực tiếp từ `getClass()`.** Ví dụ `List<String>` và `List<Integer>` dùng cùng lớp triển khai runtime như `ArrayList` khi tạo bởi `new ArrayList<>()` do cơ chế type erasure. Kiểu tham số `<String>`/`<Integer>` giúp trình biên dịch kiểm tra cách dùng, nhưng `list.getClass()` không cung cấp `Class<List<String>>` riêng để phân biệt chúng ở runtime.

## 9. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `Animal pet = new Dog()` nghĩa là chỉ có đối tượng `Animal` | Đối tượng được tạo là `Dog`; `Animal` là kiểu khai báo của tham chiếu |
| Lời gọi phương thức luôn theo kiểu khai báo | Phương thức thể hiện được override chạy theo lớp receiver thực tế |
| `pet.label` dùng field của `Dog` vì runtime là `Dog` | Truy cập field dùng kiểu của biểu thức (`Animal`) |
| Overload được chọn theo lớp runtime của tham số | Chữ ký overload được quyết định lúc biên dịch theo kiểu áp dụng của biểu thức và tham số |
| `(Dog) pet` tạo một đối tượng `Dog` mới | Ép kiểu chỉ đổi góc nhìn kiểu tham chiếu sau kiểm tra runtime |
| `instanceof Dog` giống `getClass() == Dog.class` | `instanceof` chấp nhận lớp con; `getClass() ==` đòi chính xác lớp runtime |
| Mọi biến tham chiếu đều có đối tượng runtime | Biến có thể `null`; lúc đó không có lớp thực tế của đối tượng |
| Khai báo `Object x = new ValueKey(7)` sẽ luôn gọi `Object.equals` | Nếu `ValueKey` override `equals`, lời gọi chạy bản override theo lớp thực tế |

## 10. Tự kiểm tra

1. `Animal x = new Dog();` — kiểu khai báo của `x` là gì, lớp thực tế là gì? **`Animal` và `Dog`.**
2. `x.speak()` gọi phương thức nào khi `Dog` override `speak`? **`Dog.speak()`** do dynamic dispatch.
3. `x.label` đọc field nào nếu cả hai lớp có field `label`? **Field nhìn thấy qua kiểu `Animal`**.
4. `Animal x = new ServiceDog(); x instanceof Dog` và `x.getClass() == Dog.class` là gì? **`true` và `false`.**
5. `Animal x = null; x.getClass()` có trả `Animal.class` không? **Không**; ném `NullPointerException`.
6. Nếu một phương thức chỉ tồn tại trên `Dog`, có gọi `x.fetch()` trực tiếp khi `x` khai báo là `Animal` được không? **Không**; cần kiểm tra kiểu rồi thu hẹp/ép kiểu tham chiếu.

**Ghi nhớ:** **Kiểu khai báo** quyết định Java cho phép bạn *viết lời gọi nào* và chọn chữ ký/field ở thời điểm biên dịch; **lớp thực tế** quyết định *bản ghi đè nào được thực thi* ở runtime và kết quả của `getClass()`/`instanceof`. Phân biệt hai lớp thông tin này giúp hiểu polymorphism, casting và hợp đồng đối tượng chính xác.