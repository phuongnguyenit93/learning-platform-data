# Thêm T và các đối tượng kiểu con của T vào wildcard `? super T`

## 1. Mục tiêu

Trong Java Generics, `? super T` là **wildcard có cận dưới**. Nếu một phương thức nhận `List<? super T>`, nó có thể **thêm phần tử kiểu `T` và mọi kiểu con của `T`** vào danh sách, miễn là danh sách cho phép thay đổi ở runtime.

Ví dụ, `List<? super Number>` có thể nhận `Number`, `Integer`, `Double` và các lớp con khác của `Number`. Nhưng điều đó **không** có nghĩa tham chiếu này nhận được một `Object` bất kỳ: `Object` là **kiểu cha** của `Number`, không phải kiểu con.

Bài học giải thích tại sao quy tắc này an toàn, vai trò của **kiểu tĩnh** khi biên dịch, cách viết hàm nhận dữ liệu (consumer), giới hạn khi đọc và những lỗi thường gặp.

Sau bài học, bạn có thể:
- Xác định chính xác kiểu nào được truyền vào `add` trên `Collection<? super T>`.
- Chứng minh bằng quan hệ subtype vì sao thêm `T` hoặc subtype của `T` là hợp lệ.
- Phân biệt `List<? super T>`, `List<T>`, `List<? extends T>` và `List<?>` tại điểm ghi dữ liệu.
- Dùng generic method để chuyển dữ liệu từ nguồn kiểu con vào đích có kiểu rộng hơn.
- Phân biệt lỗi compile-time với lỗi danh sách không cho phép sửa ở runtime.

## 2. Phạm vi kiểu mà `List<? super T>` cho phép ghi

Xét `List<? super Number>`: kiểu phần tử ẩn có thể là `Number` hoặc một supertype của `Number`, ví dụ `Object`. Do đó:

~~~java
List<? super Number> sink = new ArrayList<Object>();
sink.add(3.5);      // Double <: Number: đúng.
sink.add(10);       // Integer <: Number: đúng.
// sink.add("text"); // String không phải Number: lỗi biên dịch.
~~~

Không thể gán `List<Integer>` vào `List<? super Number>`, vì `List<Integer>` không chấp nhận mọi `Number` (ví dụ `Double`). Đặc điểm riêng cần phân tích ở bài này là **loại của biểu thức được thêm**: cả `T` và subtype `S <: T` đều phù hợp, nhưng một biểu thức mang kiểu tĩnh *cha hơn T* không được tự ý thêm, ngay cả khi object runtime thực chất là subtype của `T`.

## 3. Chứng minh quy tắc thêm `T` và subtype của `T`

Đặt:

- `E`: kiểu phần tử thực tế của collection, nhưng chưa biết chính xác.
- `T`: cận dưới trong `Collection<? super T>`.
- `S`: kiểu của một giá trị muốn thêm.

Định nghĩa `? super T` bảo đảm `T` là subtype của `E`: `T <: E`.

Nếu `S` là `T` hoặc subtype của `T`, thì `S <: T`.

Theo tính bắc cầu của quan hệ subtype:

```text
S <: T <: E

S là subtype của T
T là subtype của kiểu phần tử thực tế E
=> S là subtype của E
=> Có thể thêm giá trị kiểu S vào Collection<E>
```

Vì lý do này, trình biên dịch cho phép cả `add(valueOfT)` và `add(valueOfSubtypeOfT)`.

### 3.1. Ví dụ bằng `Number`

```java
List<? super Number> sink = new ArrayList<Object>();

sink.add(Integer.valueOf(10)); // Integer <: Number: hợp lệ
sink.add(Double.valueOf(2.5)); // Double <: Number: hợp lệ
sink.add(Long.valueOf(7L));    // Long <: Number: hợp lệ
sink.add((Number) 8);          // Number: hợp lệ
sink.add(null);                // null: hợp lệ về kiểm tra kiểu

// sink.add(new Object());     // SAI: Object không phải subtype của Number.
// sink.add("hello");          // SAI: String không phải subtype của Number.
```

Đây là đoạn mã **minh họa**, cần đặt trong một phương thức cùng `import java.util.*;` nếu muốn biên dịch. Đối tượng thực tế là `ArrayList<Object>`, nhưng API của biến `sink` chỉ bảo đảm phép thêm `Number` và subtype.

### 3.2. Phép boxing không làm thay đổi ý nghĩa cận dưới

```java
List<? super Number> sink = new ArrayList<Number>();
sink.add(10);     // int được boxing thành Integer, rồi upcast về Number.
sink.add(3.14);   // double được boxing thành Double, rồi upcast về Number.
```

Trong code trên, `10` và `3.14` ban đầu là primitive. Trình biên dịch có thể áp dụng **autoboxing** để biến chúng thành `Integer` và `Double`, vốn là subtype của `Number`. Đừng nhầm đây là bằng chứng rằng primitive `int` hay `double` là subtype của `Number`: quan hệ subtype ở đây là giữa các **kiểu tham chiếu** sau boxing.

## 4. Ví dụ với một cây kế thừa nhiều cấp

Giả sử có:

```text
Object
  └── Animal
        ├── Bird
        └── Mammal
              ├── Dog
              └── Cat
```

Với biến `List<? super Mammal>`, kiểu phần tử thực tế có thể là `Mammal`, `Animal` hoặc `Object`. Cả ba kiểu đó đều chứa được `Mammal`, `Dog` và `Cat`.

```java
List<? super Mammal> sink = new ArrayList<Animal>();

sink.add(new Mammal("Mia")); // ĐÚNG: chính Mammal.
sink.add(new Dog("Rex"));    // ĐÚNG: Dog <: Mammal.
sink.add(new Cat("Luna"));   // ĐÚNG: Cat <: Mammal.

// sink.add(new Animal("Any")); // SAI: Animal là supertype của Mammal.
// sink.add(new Bird("Sky"));   // SAI: Bird không phải subtype của Mammal.
// sink.add(new Object());      // SAI: Object không phải subtype của Mammal.
```

Các class trên được định nghĩa đầy đủ trong chương trình chạy ở phần 7. Đoạn này chỉ diễn tả kiểm tra kiểu. Quy tắc không phụ thuộc lớp có tên gì: nếu `S <: T` thì một giá trị có kiểu tĩnh `S` có thể truyền cho `add` của `List<? super T>`.

**Chú ý về “các đối tượng kiểu con”:** tham chiếu có thể chỉ tới đối tượng runtime là `Dog`, nhưng nếu biến được khai báo kiểu `Animal`, trình biên dịch xử lý nó như `Animal` và chưa cho thêm vào `List<? super Mammal>`. Phần 6 phân tích trường hợp này.

## 5. Ba kiểu collection thực tế có thể làm đích ghi

Với `T = Mammal`, các kiểu đích sau đều được nhận:

```java
List<Mammal> mammals = new ArrayList<>();
List<Animal> animals = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Mammal> first = mammals; // E = Mammal.
List<? super Mammal> second = animals; // E = Animal.
List<? super Mammal> third = objects; // E = Object.

first.add(new Dog("D1"));
second.add(new Dog("D2"));
third.add(new Dog("D3"));
```

Điều đáng chú ý là **kiểu thực tế `E` có thể khác nhau**, nhưng mọi kiểu trong ba trường hợp đều đủ rộng để nhận `Mammal` và subtype của `Mammal`.

Không thể suy ngược rằng `List<Dog>` cũng hợp lệ:

```java
List<Dog> dogs = new ArrayList<>();
// List<? super Mammal> wrong = dogs; // LỖI BIÊN DỊCH
```

Nếu cho phép gán như thế, `wrong.add(new Cat("Luna"))` sẽ vi phạm lời hứa rằng danh sách gốc chỉ chứa `Dog`.

**Quy tắc chọn biến đích:** các `List<T>`, `List<SupertypeOfT>` có thể gán cho `List<? super T>`; `List<SubtypeOfT>` thì không.

## 6. Kiểu tĩnh quyết định phép `add`

Trình biên dịch Java kiểm tra việc thêm dựa trên **kiểu khai báo của biểu thức**, không dựa trên subclass mà đối tượng tình cờ mang ở runtime.

Giả sử `Dog extends Mammal extends Animal`:

```java
List<? super Mammal> sink = new ArrayList<Object>();

Dog dog = new Dog("Rex");
Mammal mammal = dog;
Animal animal = dog;
Object object = dog;

sink.add(dog);    // ĐÚNG: kiểu tĩnh Dog <: Mammal.
sink.add(mammal); // ĐÚNG: kiểu tĩnh Mammal.

// sink.add(animal); // SAI: kiểu tĩnh Animal, dù runtime là Dog.
// sink.add(object); // SAI: kiểu tĩnh Object, dù runtime là Dog.
```

Điều này bảo vệ chương trình. Nếu `Animal animal` được chấp nhận chỉ nhờ đối tượng hiện tại là `Dog`, cùng một dòng code sẽ không an toàn khi biến `animal` trỏ đến `Bird`.

Nếu chương trình thực sự cần thu hẹp kiểu từ `Animal` xuống `Mammal`, phải xác minh runtime:

```java
Animal candidate = new Dog("Max");
if (candidate instanceof Mammal mammalValue) {
    sink.add(mammalValue); // ĐÚNG: mammalValue có kiểu tĩnh Mammal.
}
```

`instanceof` với pattern variable được hỗ trợ chính thức từ Java 16, do đó chạy được trên Java 17+. Không nên ép kiểu mù quáng `(Mammal) candidate` vì với `Bird` sẽ ném `ClassCastException`.

### 6.1. Trường hợp subtype được suy luận trong một phương thức

```java
static <T> void appendOne(List<? super T> target, T value) {
    target.add(value);
}
```

Vì tham số `target` bảo đảm chứa được `T`, phương thức có thể thêm chính `value`. Ví dụ `appendOne(new ArrayList<Animal>(), new Dog("Rocky"))` là hợp lệ; Java có thể suy luận type argument đáp ứng cả nguồn `Dog` và đích `Animal`.

Không cần ép kiểu raw `List` để khiến lời gọi biên dịch.

## 7. Chương trình Java 17+ đầy đủ

Lưu thành file **`SuperWildcardInsertDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class SuperWildcardInsertDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return getClass().getSimpleName() + "(" + name + ")";
        }
    }

    static class Mammal extends Animal {
        Mammal(String name) {
            super(name);
        }
    }

    static final class Dog extends Mammal {
        Dog(String name) {
            super(name);
        }
    }

    static final class Cat extends Mammal {
        Cat(String name) {
            super(name);
        }
    }

    static final class Bird extends Animal {
        Bird(String name) {
            super(name);
        }
    }

    static <T> void appendAll(
            Collection<? super T> destination,
            Iterable<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Animal> animals = new ArrayList<>();
        List<? super Mammal> sink = animals;

        sink.add(new Mammal("Mia"));
        sink.add(new Dog("Rex"));
        sink.add(new Cat("Luna"));

        Mammal asMammal = new Dog("Max");
        sink.add(asMammal);

        List<Mammal> more = List.of(
                new Dog("Bolt"),
                new Cat("Coco")
        );
        appendAll(animals, more);

        Object first = sink.get(0);
        System.out.println("animals=" + animals);
        System.out.println("first=" + first);

        List<Object> mixed = new ArrayList<>();
        mixed.add("existing");
        List<? super Mammal> anotherSink = mixed;
        anotherSink.add(new Dog("Jet"));
        System.out.println("mixed=" + mixed);
    }
}
```

Biên dịch/chạy:

```bash
javac SuperWildcardInsertDemo.java
java SuperWildcardInsertDemo
```

Kết quả stdout chính xác:

```text
animals=[Mammal(Mia), Dog(Rex), Cat(Luna), Dog(Max), Dog(Bolt), Cat(Coco)]
first=Mammal(Mia)
mixed=[existing, Dog(Jet)]
```

Giải thích:

1. `sink` tham chiếu đến `List<Animal>`, được phép vì `Animal` là supertype của `Mammal`.
2. `sink.add` lần lượt nhận `Mammal`, `Dog`, `Cat` và biến kiểu tĩnh `Mammal` đang chứa đối tượng `Dog`.
3. `appendAll` nhận `List<Mammal>` làm nguồn và `List<Animal>` làm đích, vì `T = Mammal` đáp ứng cả cận trên của nguồn và cận dưới của đích.
4. Đọc `sink.get(0)` chỉ được đảm bảo là `Object` theo kiểu của biểu thức, mặc dù đối tượng runtime in ra là `Mammal(Mia)`.
5. `mixed` vốn có sẵn một `String`. Nó vẫn có thể được nhìn qua `List<? super Mammal>` và thêm `Dog`, bởi danh sách thực tế có kiểu `List<Object>`.

Chương trình không cần thư viện ngoài JDK.

## 8. Không suy ngược kiểu dữ liệu đã có từ quyền `add`

`List<? super Mammal>` có thể là `List<Object>`, nơi đã có `String` hay `Bird`. Việc thêm `new Dog(...)` thành công về mặt kiểu không làm mọi phần tử đọc ra trở thành `Mammal`:

~~~java
List<Object> actual = new ArrayList<>();
actual.add("before");
List<? super Mammal> sink = actual;
sink.add(new Dog("Rex"));
Object first = sink.get(0); // "before"
// Mammal m = sink.get(0); // Không biên dịch.
~~~

Như vậy **quyền thêm `T` và subtype** là trọng tâm của bài; khi cần đọc phần tử thành một kiểu mạnh hơn `Object`, phải chọn một producer thích hợp hoặc kiểm tra từng object. Một trường hợp cần đọc và ghi đúng cùng type parameter có thể dùng `List<T>` thay vì wildcard consumer.

## 9. So sánh khả năng thêm của các wildcard

Giả sử `Dog <: Mammal <: Animal <: Object`:

| Kiểu tham chiếu | Có thể thêm `Dog`? | Có thể thêm `Mammal`? | Kiểu đọc an toàn tối thiểu |
| --- | --- | --- | --- |
| `List<Mammal>` | Có | Có | `Mammal` |
| `List<? super Mammal>` | Có | Có | `Object` |
| `List<? super Dog>` | Có | Không được bảo đảm | `Object` |
| `List<? extends Mammal>` | Không được bảo đảm | Không được bảo đảm | `Mammal` |
| `List<?>` | Không được bảo đảm | Không được bảo đảm | `Object` |
| `List<Animal>` | Có | Có | `Animal` |

“Không được bảo đảm” có nghĩa lời gọi `add` với đối tượng non-null thuộc kiểu tương ứng **không được trình biên dịch chấp nhận**, kể cả khi đối tượng thực tế tình cờ có đủ khả năng chứa dữ liệu.

Đối với `List<? extends Mammal>`, danh sách thực tế có thể là `List<Cat>`, nên không thể thêm `Dog`. Đối với `List<?>`, kiểu phần tử thực tế có thể là bất kỳ kiểu tham chiếu nào, nên không thể tùy ý thêm một `Mammal` hoặc `Dog`.

### 9.1. Không đảo nhầm quan hệ giữa hai cận `super`

Nếu `Dog <: Mammal` thì một đích chắc chắn nhận **mọi Mammal** cũng nhận được **Dog**:

~~~java
List<? super Mammal> mammals = new ArrayList<Animal>();
List<? super Dog> dogs = mammals; // Hợp lệ.
dogs.add(new Dog("D"));
~~~

Chiều `List<? super Dog>` sang `List<? super Mammal>` không được bảo đảm: nguồn có thể thực sự là `List<Dog>`, không nhận `Cat`. Đây là một phép gán **reference kiểu wildcard**, không phải việc `List<Dog>` trở thành subtype của `List<Mammal>`. Bài chuyên về quan hệ hai wildcard cận dưới phân tích kỹ type-argument containment và cách chuyển tiếp method.

## 10. Cách ứng dụng: phương thức nhận dữ liệu từ nhiều subtype

Khi API chỉ muốn **thêm dữ liệu** vào một collection, nên chọn kiểu tham số `Collection<? super T>` hoặc `List<? super T>`:

```java
static void collectMammals(
        Collection<? super Mammal> destination,
        Mammal first,
        Mammal second) {
    destination.add(first);
    destination.add(second);
}
```

Phương thức trên chấp nhận `Collection<Mammal>`, `Collection<Animal>`, `Collection<Object>`. Caller có thể truyền cả `Dog` và `Cat` cho các tham số `Mammal` nhờ upcasting tham chiếu.

### 10.1. Hàm copy tổng quát với `extends` và `super`

Mẫu được dùng trong chương trình chạy:

```java
static <T> void appendAll(
        Collection<? super T> destination,
        Iterable<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
```

- `source` là **producer**: nó cho ra một `T` hoặc subtype của `T`.
- `destination` là **consumer**: nó nhận được một `T` và mọi subtype của `T`.
- Khi foreach lấy `T element`, truyền trực tiếp `element` vào `add` là an toàn.

Mẫu này thể hiện **PECS — Producer Extends, Consumer Super**. `appendAll` ở đây **nối thêm** từng phần tử; khác với `Collections.copy(destination, source)`, vốn ghi đè các vị trí đã tồn tại và yêu cầu danh sách đích có kích thước đủ lớn.

Một số API trong thư viện Java cũng sử dụng khả năng ghi an toàn của wildcard `super`, chẳng hạn `Collections.copy(List<? super T> dest, List<? extends T> src)`. Khi đọc các chữ ký này, hãy liên hệ trực tiếp tới khả năng thêm/nhận `T`.

### 10.2. Đích có interface thay vì concrete class

Nếu chỉ cần `add`, khai báo `Collection<? super T>` thường linh hoạt hơn `ArrayList<? super T>` vì caller có thể truyền implementation khác nhau:

```java
static void saveNames(Collection<? super String> target) {
    target.add("Lan");
    target.add("Minh");
}
```

`String` là `final`, nên không có subclass `String` do người dùng tự tạo. Tuy nhiên quy tắc thêm `T` vẫn áp dụng: có thể thêm `String` vào `Collection<String>`, `Collection<CharSequence>`, `Collection<Object>`, vì các kiểu phần tử ấy là `String` hoặc supertype của `String`.

## 11. Kiểu interface và đa hình

Quy tắc không chỉ đúng với kế thừa `extends` giữa class. Nếu `Dog implements Pet`, thì `Dog` là subtype của interface `Pet`. Vì thế:

```java
interface Pet {
    String getName();
}

class Dog implements Pet {
    @Override
    public String getName() {
        return "Rex";
    }
}

List<? super Pet> pets = new ArrayList<Object>();
pets.add(new Dog()); // HỢP LỆ: Dog <: Pet.
```

Đây là ví dụ độc lập về một interface tên `Pet`, không dùng chung class `Dog` trong chương trình phần 7. Đặt các khai báo trong một tệp với `import java.util.*;` nếu chạy thử.

Một đối tượng có thể triển khai nhiều interface. Nếu `T` là một interface, mọi lớp implements hoặc kế thừa interface đó đều có thể được thêm khi kiểu tĩnh của biểu thức phù hợp.

Không thể thêm tùy tiện một kiểu khác **chỉ vì nó có những phương thức tương tự**. Java là ngôn ngữ nominal typing: quan hệ subtype phải có từ khai báo `extends`/`implements` hoặc các quy tắc subtype được ngôn ngữ công nhận.

## 12. Các giới hạn bên ngoài quy tắc kiểu

### 12.1. Compile-time cho phép không đồng nghĩa runtime cho phép sửa

```java
List<? super Number> sink = List.<Number>of(1, 2, 3);
sink.add(4); // Biên dịch được, nhưng ném UnsupportedOperationException.
```

`List.of(...)` trả về danh sách **không thể sửa**. Wildcard chỉ mô tả an toàn kiểu dữ liệu, không cấp quyền thay đổi cấu trúc danh sách.

Điều tương tự áp dụng cho `Collections.unmodifiableList(...)` hoặc một `Collection` tự viết không hỗ trợ `add`.

### 12.2. `null` là trường hợp riêng

```java
List<? super Mammal> sink = new ArrayList<Animal>();
sink.add(null); // HỢP LỆ về kiểm tra kiểu.
```

`null` tương thích với mọi kiểu tham chiếu. Nó không phải là đối tượng có subtype cụ thể của `Mammal`; vì vậy không nên coi việc thêm `null` là bằng chứng rằng mọi đối tượng bất kỳ cũng được thêm.

Collection implementation có thể cấm `null`, ví dụ nhiều implementation bất biến hoặc collection có hợp đồng không chứa null. Khi đó thao tác có thể thất bại tại runtime.

### 12.3. Tính bất biến của generic vẫn được giữ nguyên

```java
List<Dog> dogs = new ArrayList<>();
// List<Mammal> mammals = dogs; // SAI: List<T> invariant.
```

Dùng `? super T` để cung cấp **một góc nhìn ghi an toàn** vào các kiểu phần tử rộng hơn; nó không khiến `List<Dog>` tự biến thành `List<Mammal>`, và không cho phép lẫn `Cat` vào `List<Dog>`.

### 12.4. Không lạm dụng raw type và unchecked cast

```java
List<Dog> dogs = new ArrayList<>();
// List<? super Mammal> invalid = dogs; // SAI.
// List<? super Mammal> forced = (List) dogs; // Raw cast nguy hiểm.
```

Ép kiểu raw có thể che cảnh báo và khiến mã thêm `Cat` vào danh sách được khai báo `List<Dog>`. Khi lấy phần tử ra theo `Dog`, chương trình có thể ném `ClassCastException`. Cách sửa đúng là điều chỉnh kiểu collection đích (ví dụ `List<Mammal>` hoặc `List<Animal>`), hoặc điều chỉnh hợp đồng của phương thức theo dữ liệu cần hỗ trợ.

## 13. Bảng tình huống đúng/sai

Với cây kiểu `Dog, Cat <: Mammal <: Animal <: Object` và khai báo:

```java
List<? super Mammal> sink = new ArrayList<Animal>();
```

| Biểu thức | Biên dịch? | Lý do |
| --- | --- | --- |
| `sink.add(new Mammal("M"))` | Có | Kiểu chính xác `Mammal` |
| `sink.add(new Dog("D"))` | Có | `Dog <: Mammal` |
| `sink.add(new Cat("C"))` | Có | `Cat <: Mammal` |
| `sink.add(new Animal("A"))` | Không | `Animal` là kiểu cha của `Mammal` |
| `sink.add(new Bird("B"))` | Không | `Bird` không phải subtype của `Mammal` |
| `sink.add(new Object())` | Không | `Object` không phải subtype của `Mammal` |
| `sink.add(null)` | Có | `null` tương thích mọi kiểu tham chiếu |
| `Object x = sink.get(0)` | Có | Đọc ra bảo đảm là `Object` |
| `Mammal m = sink.get(0)` | Không | Kiểu đọc không được bảo đảm là `Mammal` |
| `sink.add((Mammal) animal)` | Có ở compile-time | Runtime cast chỉ an toàn nếu `animal` thực sự là `Mammal` |

Các biểu thức trong bảng giả sử class `Animal`, `Mammal`, `Dog`, `Cat`, `Bird` như phần 7, và biến `animal` ở dòng cuối đã được khai báo kiểu `Animal`.

## 14. Lỗi phổ biến khi thiết kế phương thức ghi

### Lỗi 1: Đọc `super` theo hướng ngược

Sai: “`List<? super Mammal>` là danh sách chỉ thêm `Animal` hoặc `Object`.”

Đúng: `Animal`/`Object` là những **kiểu phần tử thực tế có thể của danh sách**. Khi thao tác thông qua tham chiếu wildcard, chỉ việc thêm `Mammal` hoặc subtype của `Mammal` là được bảo đảm.

### Lỗi 2: Chọn `? extends T` cho đối số cần `add`

```java
// static void addDog(List<? extends Mammal> sink) {
//     sink.add(new Dog("Rex")); // SAI.
// }
```

Nguồn có kiểu `List<? extends Mammal>` có thể thực chất là `List<Cat>`. Nếu phương thức muốn nhận `Dog`, khai báo `List<? super Dog>` (được cả `List<Dog>`, `List<Mammal>`, `List<Animal>`, `List<Object>`). Nếu nó muốn nhận mọi `Mammal`, dùng `List<? super Mammal>`.

### Lỗi 3: Cho rằng runtime subtype luôn đủ

```java
Animal animal = new Dog("Rex");
// sink.add(animal); // SAI vì kiểu tĩnh Animal.
```

Cách sửa là biểu diễn đúng hợp đồng kiểu ngay từ đầu (`Mammal mammal = new Dog("Rex")`) hoặc dùng `instanceof Mammal m` khi phải xử lý đối tượng `Animal` không rõ subtype.

### Lỗi 4: Gắn kiểu `List<? super T>` cho mọi tham số

Nếu phương thức **chỉ đọc** phần tử là `T`, `? extends T` thường thích hợp hơn. Nếu vừa đọc thành `T` vừa ghi `T`, cần bảo toàn liên hệ kiểu bằng `List<T>` hoặc phương thức generic `<T>`.

Không có một wildcard tối ưu cho mọi hướng dữ liệu.

### Lỗi 5: Bỏ qua mutability và kiểm tra lỗi runtime

`Collection<? super T>` chỉ bảo đảm lời gọi `add(T)` **an toàn về kiểu**. Nó không buộc mọi implementation hỗ trợ thêm; caller phải truyền một collection phù hợp với hợp đồng phương thức nếu thao tác sửa dữ liệu là bắt buộc.

## 15. Bài tập tự đánh giá

Cho:

```java
class Vehicle {}
class Car extends Vehicle {}
class Taxi extends Car {}
class Bike extends Vehicle {}
```

### Bài 1: Quyết định lời gọi `add`

```java
List<? super Car> destination = new ArrayList<Vehicle>();

destination.add(new Car());  // (1)
destination.add(new Taxi()); // (2)
// destination.add(new Vehicle()); // (3)
// destination.add(new Bike());    // (4)
destination.add(null);       // (5)
```

**Đáp án:** (1), (2) hợp lệ vì `Car` là cận dưới và `Taxi <: Car`; (5) hợp lệ về kiểu. (3), (4) sai vì `Vehicle` và `Bike` không phải subtype của `Car`.

### Bài 2: Chọn danh sách nguồn hợp lệ

Cho `List<? super Car> sink`, hãy cho biết kiểu danh sách nào có thể gán cho biến này: `List<Car>`, `List<Vehicle>`, `List<Object>`, `List<Taxi>`.

**Đáp án:** `List<Car>`, `List<Vehicle>`, `List<Object>` đều hợp lệ; `List<Taxi>` không hợp lệ, vì không thể thêm một `Car` bất kỳ vào `List<Taxi>`.

### Bài 3: So sánh kiểu tĩnh và kiểu thực tế

```java
Vehicle a = new Taxi();
Car b = new Taxi();

// sink.add(a); // (1)
sink.add(b);    // (2)
```

**Đáp án:** (1) sai dù runtime là `Taxi`, vì `a` có kiểu tĩnh `Vehicle`. (2) đúng vì `b` có kiểu tĩnh `Car`.

### Bài 4: Vì sao không đọc được `Car`?

```java
List<Object> objects = new ArrayList<>();
objects.add("not a vehicle");
List<? super Car> sink = objects;

// Car c = sink.get(0);
Object value = sink.get(0);
```

**Đáp án:** `sink` có thể tham chiếu tới `List<Object>` chứa các kiểu khác. `get` chỉ bảo đảm trả về `Object`. Nếu ép kiểu thành `Car` với phần tử đầu tiên là chuỗi, chương trình ném `ClassCastException`.

### Bài 5: Điền wildcard hợp lý

Một phương thức cần nhận từng phần tử kiểu `Car` hoặc subtype từ một nguồn và thêm vào một collection có thể chứa `Car`. Chữ ký nào phù hợp?

```java
static void transfer(
        Collection<? super Car> destination,
        Iterable<? extends Car> source) {
    for (Car car : source) {
        destination.add(car);
    }
}
```

**Đáp án:** Đích dùng `? super Car` vì **tiêu thụ** `Car`; nguồn dùng `? extends Car` vì **sản xuất** `Car`. Phương thức này nhận được nguồn `Iterable<Taxi>` và đích `Collection<Vehicle>`.

## 16. Checklist khi cần thêm phần tử vào generic collection

1. Xác định `T`: kiểu tối thiểu mà collection nhận phải hỗ trợ.
2. Nếu tham số là đích ghi, dùng `Collection<? super T>` hoặc interface tổng quát phù hợp.
3. Kiểm tra **kiểu tĩnh `S` của biểu thức được thêm**: yêu cầu `S <: T` hoặc `S = T`.
4. Kiểm tra kiểu phần tử thực tế của collection (`E`) có phải `T` hoặc supertype của `T` hay không.
5. Không suy luận subtype chỉ từ đối tượng runtime khi biến khai báo kiểu rộng hơn.
6. Đừng mặc định `get()` trả về `T` trên một biến `? super T`: mặc định an toàn là `Object`.
7. Kiểm tra collection có hỗ trợ `add` và chính sách `null` ở runtime.
8. Tránh raw type hoặc unchecked cast để lách lỗi biên dịch.

## 17. Tài liệu tham khảo

- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): quy tắc consumer và cách chọn `? super T`.
- Oracle Java Tutorials — [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html): ví dụ và cách dùng wildcard cận dưới.
- Java Language Specification, Java SE 17 — [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): kiểu đối số wildcard và quan hệ cận.
- Java API — [Collection.add(E)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#add(E)): hợp đồng thêm phần tử, các trường hợp không hỗ trợ thao tác và ngoại lệ runtime.

**Ghi nhớ cốt lõi:** Với `List<? super T>`, mọi giá trị có **kiểu tĩnh là `T` hoặc subtype của `T`** đều có thể truyền vào `add` một cách an toàn về kiểu. Cận `super` mô tả kiểu phần tử thực tế của collection đủ rộng để tiếp nhận các giá trị ấy; khi đọc từ tham chiếu wildcard, trình biên dịch vẫn chỉ bảo đảm `Object`.