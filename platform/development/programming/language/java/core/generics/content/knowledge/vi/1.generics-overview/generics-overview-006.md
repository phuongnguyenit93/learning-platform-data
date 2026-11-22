# Phân biệt tính tổng quát về kiểu với kế thừa và đa hình trong Java

Generics, kế thừa và đa hình đều giúp chương trình Java linh hoạt hơn, nhưng mỗi cơ chế giải một vấn đề riêng. Khi đọc các ví dụ như `List<Dog>`, `Dog extends Animal` và `Animal animal = new Dog()`, hãy phân biệt **quan hệ kiểu**, **mức độ tổng quát của thuật toán** và **cách chọn hành vi lúc chạy**.

## 1. Định nghĩa và bản chất

**Generics (tính tổng quát về kiểu)** cho phép khai báo lớp, interface hoặc phương thức có *tham số kiểu* (`T`, `E`, `K`, `V`...). Cùng cấu trúc hoặc thuật toán dùng được với nhiều kiểu, và trình biên dịch giữ lại mối liên hệ kiểu giữa đối số, biến chứa và kết quả. Ví dụ `Box<String>` và `Box<Dog>` dùng chung định nghĩa `Box<T>`; phương thức `<T> T first(List<T> items)` trả về đúng kiểu phần tử của danh sách đầu vào. Không cần có lớp cha/con giữa `String` và `Dog` để dùng chung thuật toán generic.

**Kế thừa (inheritance)** định nghĩa quan hệ “is-a”: `Dog extends Animal` nghĩa là `Dog` là subtype của `Animal`, thừa hưởng những thành phần có thể kế thừa và có thể mở rộng/override hành vi. `implements` xác lập quan hệ một lớp hiện thực interface; interface cũng có thể `extends` interface khác. Kế thừa lớp còn có thể tái sử dụng mã nhưng chỉ nên dùng khi quan hệ phân loại thực sự đúng.

**Đa hình (polymorphism)** nghĩa là dùng một giao diện/kiểu chung để làm việc với nhiều hình thái cụ thể. Trong **đa hình subtype tại runtime**, một tham chiếu `Animal` có thể trỏ đến `Dog` hoặc `Cat`; lời gọi phương thức instance bị override, ví dụ `animal.sound()`, chạy triển khai ứng với đối tượng thực tế. Trình biên dịch kiểm tra rằng `Animal` có phương thức `sound()`; runtime quyết định override nào chạy.

Một số tài liệu xếp generics vào **đa hình tham số (parametric polymorphism)**, còn override qua cha/interface vào **đa hình subtype (subtype polymorphism)**. Đây là hai nghĩa khác nhau của từ “đa hình”. Khi so sánh ba cơ chế trong Java, “đa hình” thường ám chỉ tính đa hình hành vi qua override và dynamic dispatch.

| Câu hỏi thiết kế | Generics | Kế thừa | Đa hình subtype |
|---|---|---|---|
| Giải quyết gì? | Dùng lại cấu trúc/thuật toán, giữ quan hệ kiểu | Tổ chức subtype và hợp đồng có thể kế thừa | Gọi chung nhưng hành vi khác nhau |
| Cú pháp tiêu biểu | `class Box<T>`, `<T> T id(T x)` | `extends`, `implements` | Override phương thức instance |
| Chọn/kiểm tra chủ yếu khi nào? | Compile time; Java generics thông thường dùng type erasure | Quan hệ subtype được kiểm tra khi biên dịch | Runtime chọn override theo đối tượng |
| Có cần các subtype không? | Không | Có quan hệ subtype | Thường có nhiều implementation của lớp cha/interface |
| Có khiến `List<Dog>` thành `List<Animal>`? | Không | Không | Không |

## 2. Chương trình minh họa đủ ba cơ chế

Ví dụ chạy độc lập với Java 17 trở lên. Lưu đúng tên **`GenericVsInheritanceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericVsInheritanceDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        String sound() {
            return "(unknown)";
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }
    }

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    static <T extends Animal> String soundOf(T animal) {
        return animal.sound();
    }

    static <T> void copy(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(new Dog("Milu"), new Dog("Bong"));

        Dog firstDog = first(dogs);
        System.out.println("generic: " + firstDog.name());

        Animal baseRef = firstDog;
        System.out.println("polymorphism: " + baseRef.sound());
        System.out.println("bound: " + soundOf(firstDog));

        Box<Dog> box = new Box<>(firstDog);
        System.out.println("box: " + box.get().name());

        List<? extends Animal> view = dogs;
        System.out.println("wildcard: " + view.get(1).name());

        List<Animal> copied = new ArrayList<>();
        copy(dogs, copied);
        System.out.println("copy count: " + copied.size());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac GenericVsInheritanceDemo.java
java GenericVsInheritanceDemo
```

Stdout chính xác:

```text
generic: Milu
polymorphism: woof
bound: woof
box: Milu
wildcard: Bong
copy count: 2
```

Tách từng kết quả:

1. `first(dogs)` dùng **phương thức generic**; trình biên dịch suy luận `T` là `Dog`, nên biến nhận kết quả có kiểu `Dog` và không cần cast. Nó hoạt động với `List<String>`, `List<Integer>`... mà không cần những lớp này có cha chung do người viết định nghĩa. Hàm giả định danh sách không rỗng; gọi với danh sách rỗng sẽ ném `IndexOutOfBoundsException`.
2. `Dog extends Animal` tạo quan hệ **kế thừa**. Phép gán `Animal baseRef = firstDog` là upcast hợp lệ vì `Dog` là `Animal`. Không cần generics để gán một đối tượng con vào biến kiểu cha.
3. `baseRef.sound()` in `woof` do **đa hình runtime**: biến tĩnh là `Animal`, nhưng đối tượng được tạo bởi `new Dog(...)`; bản override ở `Dog` thực thi.
4. `Box<T>` dùng **generics** để lưu và trả về cùng kiểu `T`. `Box<Dog>` không phải subclass của `Box<Animal>`. Lời gọi `box.get()` được kiểm tra kiểu trả về là `Dog` khi biên dịch.
5. `<T extends Animal>` là **ràng buộc tham số kiểu**: `soundOf` có thể gọi `animal.sound()` vì mọi `T` hợp lệ đều là subtype của `Animal`. Nó sử dụng quan hệ kế thừa sẵn có, không tạo ra lớp con mới.
6. `List<? extends Animal>` cho phép xem danh sách `List<Dog>` để đọc phần tử dưới kiểu `Animal`; phương thức generic `copy` dùng wildcard ở nguồn và đích để chép các đối tượng vào `List<Animal>` an toàn.

## 3. Bẫy quan trọng: kế thừa của phần tử không truyền sang danh sách

Giả sử có `Dog extends Animal`. Điều sau đây **không biên dịch**:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = dogs; // Lỗi incompatible types
```

Trong Java, generic parameterized type thông thường là **invariant (bất biến)**: `Dog` là subtype của `Animal` nhưng `List<Dog>` không là subtype của `List<Animal>`. Điều này bảo vệ tính an toàn kiểu.

Hãy tưởng tượng phép gán trên được cho phép: qua biến `animals`, chương trình có thể thêm `Cat` vào danh sách `dogs`; sau đó một lệnh đọc `Dog d = dogs.get(0)` có thể nhận nhầm `Cat`. Trình biên dịch ngăn chuyện này từ đầu.

Khi cần một mức tổng quát hơn, chọn wildcard theo hướng sử dụng:

- **Đọc:** `List<? extends Animal> view = dogs;`. Biến `view` có thể đọc `Animal a = view.get(0)`. Không được `view.add(new Dog(...))`: kiểu cụ thể đứng sau `?` là chưa biết (có thể chính là `Cat`). Chỉ giá trị `null` là ngoại lệ cho thao tác thêm.
- **Ghi:** `List<? super Dog> target = new ArrayList<Animal>();`. Có thể `target.add(new Dog(...))`. Khi đọc từ `target`, kiểu bảo đảm chung là `Object`, vì đích có thể là danh sách của `Dog`, `Animal` hay `Object`.
- **Đọc và ghi đúng một kiểu:** dùng `List<Dog>` nếu cần biết chính xác cả hai chiều.
- **Kiểu không xác định:** `List<?>` có thể đọc dưới kiểu `Object` nhưng không thêm phần tử không-null. `List<?>` khác `List<Object>`: danh sách `List<Object>` cho phép thêm `String`, `Dog` hay `Object` tùy ý.

Quy tắc nhớ **PECS: Producer Extends, Consumer Super**. Nguồn *cung cấp* phần tử thì dùng `? extends T`; đích *nhận* phần tử thì dùng `? super T`. Wildcard này diễn đạt phạm vi kiểu của container, không phải tạo subtype giữa `List<Dog>` và `List<Animal>`.

## 4. Khi nào cần tham số kiểu có bound, khi nào chỉ cần lớp cha?

So sánh hai chữ ký độc lập sau:

```java
static void printSound(Animal animal) {
    System.out.println(animal.sound());
}

static <T extends Animal> T echoSound(T animal) {
    System.out.println(animal.sound());
    return animal;
}
```

- `printSound(Animal)` đủ dùng khi chỉ cần hành vi chung `sound()`, không có yêu cầu bảo toàn kiểu con của kết quả.
- `echoSound(T)` có giá trị vì **liên kết kiểu đối số với kiểu trả về**. Nếu truyền `Dog`, trình biên dịch có thể suy luận kết quả là `Dog`; nếu thay bằng `Animal echoSound(Animal)`, người gọi chỉ nhận kiểu tĩnh `Animal`.
- Bound `T extends Animal` cho phép thân phương thức dùng các thành viên hợp lệ của `Animal`. Nó không đảm bảo mọi phương thức riêng của `Dog` sẽ có trên `T`, vì `T` có thể là subtype khác.

`<T extends Animal>` là **named type parameter** có upper bound. `? extends Animal` là **wildcard** không tên. Dùng `T` khi cần diễn đạt ràng buộc giữa hai hay nhiều vị trí trong API; dùng wildcard khi không phải tham chiếu lại cùng một kiểu chưa biết. Không thêm `<T>` chỉ để hàm trông tổng quát hơn: `void log(Animal a)` rõ ràng hơn `<T extends Animal> void log(T a)` nếu `T` không đem lại bảo đảm bổ sung.

Bound có thể gồm nhiều hợp đồng, chẳng hạn `<T extends Animal & Runnable>` (nếu có class bound thì class đó phải đứng trước các interface bound). Các bound ảnh hưởng cách kiểm tra kiểu lúc biên dịch; phương thức override vẫn được phân phối theo đối tượng thật khi chạy.

## 5. Thời điểm kiểm tra kiểu và chọn hành vi

**Generics chủ yếu là cơ chế compile-time.** Trình biên dịch kiểm tra kiểu phần tử, suy luận `T`, ràng buộc và các phép gán. Java generics thông thường dùng **type erasure**: `T` không bound thường được xóa thành `Object`, còn `T extends Animal` xóa về bound `Animal`. Trình biên dịch có thể chèn cast và tạo bridge method khi cần duy trì semantics của override sau erasure. Vì thế hai đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` đều là instance của lớp runtime `ArrayList`; chúng không là hai lớp được “chuyên biệt hóa” riêng.

**Đa hình subtype tại runtime vẫn có thông tin lớp thực tế.** Khi `Animal a = new Dog("Milu")`, đối tượng thực sự là `Dog`, nên lệnh gọi phương thức instance có override `a.sound()` chạy bản `Dog.sound()`. Không có yêu cầu lưu `T = Dog` tại runtime để thực hiện điều này.

Không thể kiểm tra `value instanceof List<String>` trong Java vì tham số kiểu cụ thể `String` bị xóa và không kiểm tra được theo cách đó. Có thể kiểm tra `value instanceof List<?>` nhưng chỉ biết nó là `List`, không kết luận phần tử bên trong là `String`.

Cũng cần phân biệt **overriding** và **overloading**:

- **Overriding**: lớp con/interface implementation đưa ra triển khai mới của phương thức instance có chữ ký override hợp lệ; runtime chọn triển khai theo đối tượng.
- **Overloading**: cùng tên phương thức nhưng khác danh sách tham số; lựa chọn overload dựa trên kiểu tĩnh của đối số và quy tắc biên dịch, chứ không tự chuyển sang overload khác vì đối tượng runtime là `Dog`.

Generics có thể tham gia vào chọn overload lúc biên dịch nhưng **không thay thế dispatch của phương thức override**.

## 6. Chọn cơ chế trong thiết kế thực tế

| Nhu cầu | Cách biểu đạt | Vì sao |
|---|---|---|
| Hộp chứa đúng kiểu dữ liệu mà người gọi chọn | `Box<T>` | Lưu/đọc theo `T`, tránh cast |
| Thuật toán trả về phần tử cùng kiểu danh sách đầu vào | `<T> T first(List<T> xs)` | Giữ liên hệ kiểu giữa tham số và kết quả |
| Nhiều loài có âm thanh khác nhau | `Animal.sound()` được `Dog`, `Cat` override | Một lời gọi chung, hành vi runtime khác nhau |
| Nhiều lớp triển khai một dịch vụ thống nhất | `interface Service`; các lớp `implements Service` | Đa hình qua hợp đồng chung mà không bắt buộc lớp cha cụ thể |
| Hàm chỉ cần đọc mọi subtype của Animal | `List<? extends Animal>` | Chấp nhận `List<Dog>`, `List<Cat>` để đọc |
| Hàm muốn thêm Dog vào danh sách có khả năng chứa Dog | `List<? super Dog>` | Đảm bảo thao tác ghi an toàn |
| Hàm nhận và trả chính subtype của Animal | `<T extends Animal> T process(T input)` | Ràng buộc kiểu đầu vào/đầu ra |

Một API có thể kết hợp cả ba cơ chế: interface/lớp cha diễn tả **hợp đồng hành vi**; implementation override phần **hành vi riêng**; generics bảo vệ **quan hệ kiểu** của cấu trúc hay thuật toán. Chỉ thêm abstraction thực sự phục vụ yêu cầu.

## 7. Lỗi tư duy và lỗi biên dịch thường gặp

1. **“Bound `extends` nghĩa là khai báo một lớp con.”** Sai. `<T extends Animal>` là ràng buộc tham số kiểu. `class Dog extends Animal` mới tạo quan hệ kế thừa lớp.
2. **“`Dog extends Animal` nên `List<Dog> extends List<Animal>`.”** Sai do tính bất biến của tham số kiểu. Giải quyết bằng wildcard hoặc copy từng phần tử theo API phù hợp.
3. **“Với `List<? extends Animal>` có thể thêm bất cứ `Dog` nào.”** Sai vì tham số kiểu cụ thể của danh sách là ẩn; danh sách có thể là `List<Cat>`.
4. **“Dùng `Object` hoàn toàn tương đương `<T>`.”** `Object identity(Object x)` làm mất thông tin kiểu cụ thể của kết quả; `<T> T identity(T x)` cho trình biên dịch giữ mối liên hệ đầu vào–đầu ra.
5. **“Generics luôn tồn tại nguyên vẹn tại runtime.”** Sai do erasure thông thường. Không dùng `instanceof List<String>` để xác định phần tử; cần kiểm tra từng phần tử hoặc thiết kế cách mang type token thích hợp khi thật sự cần.
6. **“Ép kiểu hoặc raw type giải quyết được mọi vấn đề generic.”** Raw `List` và unchecked cast làm yếu kiểm tra biên dịch và có thể gây `ClassCastException` về sau. Ưu tiên chữ ký generic/wildcard đúng thay vì né kiểm tra kiểu.
7. **“Java 17 chấp nhận `List<int>` hoặc `new T()`.”** Sai. Type argument phải là kiểu tham chiếu (dùng `Integer`, có autoboxing); không thể trực tiếp khởi tạo `new T()` vì `T` không chỉ ra constructor runtime. Khi cần tạo phần tử generic, có thể nhận `Supplier<T>` hoặc factory.
8. **“Thêm generic là đã có đa hình runtime.”** Sai. `Box<T>` có thể không override phương thức nào. Dynamic dispatch đến từ các override của phương thức instance và đối tượng runtime, không từ tên `T`.

## 8. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `Dog extends Animal`, biến `Animal a = new Dog("Milu")` gọi `a.sound()`. Nếu `Dog` override `sound()` thì chạy phiên bản nào? **Đáp án:** `Dog.sound()` nhờ đa hình runtime.

**Câu 2.** Có thể gán `List<Dog>` trực tiếp vào `List<Animal>` không? **Đáp án:** không; generics invariant. Có thể nhận danh sách qua `List<? extends Animal>` khi cần đọc phần tử dưới kiểu `Animal`.

**Câu 3.** `<T> T identity(T x)` làm được gì hơn `Object identity(Object x)`? **Đáp án:** giữ được kiểu tĩnh của giá trị trả về dựa vào đối số, tránh cast tại điểm gọi.

**Câu 4.** Một tham số `List<? super Dog>` cho phép thêm `Dog`; tại sao khi lấy phần tử chỉ bảo đảm `Object`? **Đáp án:** kiểu cụ thể có thể là `Dog`, `Animal` hoặc `Object`, không biết chính xác hơn.

**Câu 5.** Hàm chỉ in `animal.sound()` có bắt buộc `<T extends Animal>` không? **Đáp án:** không; `void printSound(Animal animal)` là đủ nếu không cần giữ kiểu `T` ở vị trí khác.

**Câu 6.** `Box<Dog>` có là subtype của `Box<Animal>` không? **Đáp án:** không, trừ khi chính kiểu `Box` có một quan hệ subtype khác được định nghĩa tường minh; generic instantiation không tự kế thừa nhau.

Khi gặp bài toán mới, tự hỏi: **Các đối tượng có cùng hợp đồng nào?** → lớp cha/interface. **Chúng triển khai hành vi khác nhau ra sao?** → override và đa hình runtime. **Một cấu trúc hoặc thuật toán cần bảo toàn quan hệ kiểu nào?** → generics, bound, wildcard. Phân biệt được ba câu hỏi đó là nền tảng để viết API Java an toàn và dễ dùng.
