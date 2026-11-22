# Nhận collection của T hoặc kiểu cha của T với `? super T`

Khi một phương thức cần **đưa các giá trị kiểu `T` vào một collection do bên gọi cung cấp**, collection đích không nhất thiết phải khai báo chính xác `Collection<T>`. Nó có thể lưu các phần tử dưới một kiểu rộng hơn, chẳng hạn `Number` hoặc `Object` đối với `Integer`. Java Generics biểu diễn nhu cầu này bằng **lower-bounded wildcard**:

~~~java
Collection<? super Integer> destination;
~~~

Kiểu trên chấp nhận các collection có đối số kiểu là **`Integer` hoặc một kiểu cha của `Integer`**, chẳng hạn `Collection<Integer>`, `Collection<Number>` và `Collection<Object>`. Phương thức có thể thêm `Integer` vào tất cả các collection đó một cách an toàn.

Để hiểu đúng quy tắc, hãy phân biệt **kiểu phần tử của collection thực**, **kiểu tĩnh của tham chiếu wildcard**, và **hướng mà dữ liệu di chuyển**. Cũng cần nhớ rằng `Collection` chỉ có `iterator()` để lấy phần tử; nó không cung cấp `get(index)` như `List`.

## 1. Vì sao cần nhận collection rộng hơn một `Collection<T>` cố định?

Một `Collection<Integer>` **không phải** `Collection<Number>`, dù `Integer` là subtype của `Number`. Nếu có thể gán trực tiếp, phương thức nhận `Collection<Number>` sẽ thêm được `Double` vào cấu trúc mà caller coi là chỉ chứa `Integer`.

~~~java
Collection<Integer> integers = new ArrayList<>();
// Collection<Number> wrong = integers; // Bị compiler từ chối.

Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();
numbers.add(10);
objects.add(10);
~~~

Tuy không thể hoán đổi các kiểu collection bất biến, **cả hai đích đều nhận được `Integer`**. Một API chỉ cần chèn `Integer` nên mô tả *khả năng nhận giá trị*, thay vì đòi đúng một đối số kiểu: `Collection<? super Integer>`. Đây là lý do thực tế để dùng wildcard cận dưới với **giao diện `Collection`**, không chỉ với `List`.

## 2. `? super T` nghĩa là gì?

Trong `Collection<? super T>`:

- `Collection` là giao diện collection tổng quát trong Java.
- `?` là wildcard đại diện cho một kiểu cụ thể **chưa biết tên**.
- `super T` đặt **cận dưới** (lower bound): kiểu ẩn đó phải là `T` hoặc một **supertype** của `T`.
- Vì collection thực có thể lưu `T` dưới chính kiểu `T` hoặc kiểu rộng hơn, việc thêm một giá trị `T` vào nó là an toàn.

Ví dụ với `T = Integer`:

| Kiểu thực của collection | Gán vào `Collection<? super Integer>`? | Lý do |
| --- | --- | --- |
| `Collection<Integer>` | Có | Đối số kiểu đúng bằng cận dưới |
| `Collection<Number>` | Có | `Number` là supertype của `Integer` |
| `Collection<Object>` | Có | `Object` là supertype của `Integer` |
| `Collection<Double>` | Không | `Double` không phải supertype của `Integer` |
| `Collection<String>` | Không | `String` không phải supertype của `Integer` |

Ngoài chuỗi kế thừa lớp `Integer → Number → Object`, một supertype phù hợp cũng có thể là **interface** mà `Integer` triển khai, ví dụ `Serializable`. Vì vậy `Collection<? super Integer>` không chỉ bị giới hạn ở ba kiểu trong bảng: bảng giới thiệu các trường hợp thường gặp.

Có thể hiểu tương đương ở mức ý nghĩa:

> “Tôi không cần biết chính xác collection lưu đối số kiểu nào, miễn là đối số kiểu đó chấp nhận mọi `Integer`.”

Lưu ý: `? super T` dùng trong wildcard. Java **không** cho phép khai báo kiểu tham số bằng cú pháp `<T super Number>`. Khi cần ràng buộc type parameter, cú pháp thông thường là upper bound, ví dụ `<T extends Number>`; cận dưới được diễn đạt tại vị trí wildcard.

## 3. Ví dụ Java 17+: một phương thức thêm số vào ba loại collection

Tạo tệp **`SuperWildcardDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class SuperWildcardDemo {
    private static void addDefaults(Collection<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        Collection<Integer> integers = new ArrayList<>();
        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        addDefaults(integers);
        addDefaults(numbers);
        addDefaults(objects);

        Collection<? super Integer> sink = numbers;
        sink.add(30);

        Object first = sink.iterator().next();

        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("first = " + first);
    }
}
~~~

Biên dịch và chạy trên Java 17 trở lên:

~~~bash
javac SuperWildcardDemo.java
java SuperWildcardDemo
~~~

Stdout chính xác:

~~~text
integers = [10, 20]
numbers = [10, 20, 30]
objects = [10, 20]
first = 10
~~~

Ở ví dụ này:

1. `addDefaults` chỉ quan tâm việc **ghi hai `Integer` vào collection**. Nó không cần biết đối số kiểu chính xác của đích.
2. Cả `Collection<Integer>`, `Collection<Number>` và `Collection<Object>` đều phù hợp với `Collection<? super Integer>`.
3. `sink` là tham chiếu tới cùng đối tượng với `numbers`; `sink.add(30)` thay đổi chính collection `numbers`.
4. `sink.iterator().next()` chỉ có kiểu tĩnh chắc chắn là `Object`. Mặc dù phần tử đầu trong ví dụ là `Integer`, compiler không thể dựa vào giả định ấy cho mọi collection phù hợp wildcard.
5. Chương trình dùng `ArrayList` để thứ tự in phần tử ổn định; `Collection` nói chung không hứa thứ tự duyệt giống thứ tự thêm.

Điểm quan trọng nhất là chữ ký `Collection<? super Integer>` **mở rộng loại đích có thể nhận** mà không làm mất kiểm tra kiểu của các phần tử được thêm.

## 4. Kiểu của giá trị đọc qua `Collection<? super T>`

Một consumer chỉ cam kết **nhận được `T`**, không cam kết mọi phần tử hiện có đều thuộc `T`. Ví dụ `Collection<Object>` có thể chứa `String` trước khi được chuyển qua tham chiếu `Collection<? super Integer>`:

~~~java
Collection<Object> original = new ArrayList<>();
original.add("existing");
Collection<? super Integer> sink = original;
sink.add(7);

Object first = sink.iterator().next(); // "existing"
// Integer wrong = sink.iterator().next(); // Không biên dịch.
~~~

Dùng `iterator().next()`, **không phải `get(0)`**, bởi `Collection` không định nghĩa truy cập chỉ số. Cận dưới chỉ cho phép `add(Integer)`; khi duyệt, kiểu an toàn chung của `Collection<E>` là `Object`. Nếu cần đọc lại thành `Integer`, phải kiểm chứng giá trị cụ thể hoặc chọn một nguồn typed khác. Phân tích hình thức về capture conversion và các trường hợp generic declaration có bound hẹp hơn thuộc chủ đề riêng về **giới hạn kiểu khi đọc**.

## 5. Chọn chữ ký `Collection` theo hướng dữ liệu

| Yêu cầu trong method (giả sử `T=Number`) | Tham số phù hợp | Phần tử đọc an toàn | Giá trị có thể thêm về mặt kiểu |
| --- | --- | --- | --- |
| Chỉ nhận đúng kiểu collection chứa `Number` | `Collection<Number>` | `Number` | `Number` |
| Đọc `Number` từ nhiều collection con | `Collection<? extends Number>` | `Number` | Không tùy ý thêm giá trị non-null |
| Thêm `Number` vào collection của `Number` hoặc kiểu cha | `Collection<? super Number>` | `Object` | `Number` và subtype |
| Không quan tâm element type | `Collection<?>` | `Object` | Không tùy ý thêm giá trị non-null |

`? extends` thiên về **nguồn**, `? super` thiên về **đích**. Với `Collection`, việc đọc thực hiện qua `iterator()` hoặc foreach; muốn `get(i)`/`set(i,...)` thì chuyển sang `List`. Các quy tắc wildcard chỉ bảo đảm **kiểu tĩnh**; `add` có thể thất bại trên unmodifiable collection, hoặc `Set.add` có thể trả `false` khi phần tử đã tồn tại.

Không nên đổi `Collection<? super T>` thành `Collection<Object>`: biến `Collection<Object>` **không** nhận trực tiếp `Collection<Integer>`, dù cả hai có thể tiêu thụ những `Integer` do method cung cấp.

## 6. Áp dụng khi `T` là type parameter của phương thức generic

Một phương thức có thể nhận `T` bất kỳ và thêm vào đích kiểu `T` hoặc supertype của `T`:

~~~java
static <T> void addTwo(Collection<? super T> destination, T a, T b) {
    destination.add(a);
    destination.add(b);
}
~~~

Đây là **một phương thức, cần đặt trong class và import `java.util.Collection`**. Khai báo `<T>` cho compiler suy luận kiểu từ toàn bộ các tham số trong **từng lời gọi**.

Ví dụ khi `T` được chọn là `Integer`:

~~~java
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();

addTwo(numbers, 1, 2); // Hợp lệ.
addTwo(objects, 3, 4); // Hợp lệ.
~~~

Đây là **đoạn lời gọi cần đặt trong class và import `java.util.*`**. Trong mỗi lời gọi, `T` có thể được suy luận thành `Integer`, trong khi collection đích lưu phần tử dưới kiểu `Number` hoặc `Object`.

Để thấy rõ ràng buộc, có thể chỉ định type argument tường minh:

~~~java
MyUtils.<Integer>addTwo(numbers, 1, 2); // Đúng.
MyUtils.<Integer>addTwo(objects, 3, 4); // Đúng.
~~~

Đây là ký pháp minh họa: giả sử `addTwo` là `static` trong class `MyUtils`. Với `T = Integer`, `Collection<? super T>` yêu cầu đích có đối số kiểu là `Integer` hoặc một supertype của nó.

### Điểm tinh tế: đừng gán cố định `T` khi compiler cần suy luận

Nếu `T` là một type parameter của **phương thức**, compiler có thể chọn kiểu thích hợp cho mỗi lần gọi. Nếu `T` là type parameter của **class** hoặc đã được chọn rõ là một kiểu cụ thể, các tham số phải tuân theo kiểu đã chọn.

Chẳng hạn:

~~~java
class IntegerAppender {
    void append(Collection<? super Integer> destination) {
        destination.add(1);
    }
}
~~~

Đây là **class minh họa**, cần import `java.util.Collection`. Phương thức `append` cố định cận dưới là `Integer`. Nó nhận `Collection<Integer>`, `Collection<Number>` hoặc `Collection<Object>`, nhưng không nhận `Collection<Double>`. Bản thân tên kiểu generic và cách `T` được suy luận không tự làm mất các ràng buộc subtype.

## 7. Ví dụ với class và interface tự định nghĩa

`super` không chỉ áp dụng cho ba lớp `Integer`, `Number` và `Object`. Giả sử mô hình nghiệp vụ có `Animal` và `Dog`, trong đó `Dog` là subtype của `Animal`. Một collection lưu `Animal` hay `Object` đều chứa được `Dog`.

Tạo tệp **`AnimalDestinationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class AnimalDestinationDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static void addDogs(Collection<? super Dog> destination) {
        destination.add(new Dog("Bim"));
        destination.add(new Dog("Milo"));
    }

    public static void main(String[] args) {
        Collection<Dog> dogs = new ArrayList<>();
        Collection<Animal> animals = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        addDogs(dogs);
        addDogs(animals);
        addDogs(objects);

        System.out.println("dogs = " + dogs);
        System.out.println("animals = " + animals);
        System.out.println("objects = " + objects);
    }
}
~~~

Chạy:

~~~bash
javac AnimalDestinationDemo.java
java AnimalDestinationDemo
~~~

Stdout chính xác:

~~~text
dogs = [Bim, Milo]
animals = [Bim, Milo]
objects = [Bim, Milo]
~~~

Giải thích:

- `Collection<Dog>` chấp nhận các `Dog` trực tiếp.
- `Collection<Animal>` chấp nhận `Dog` vì `Dog` mở rộng `Animal`.
- `Collection<Object>` chấp nhận `Dog` vì mọi đối tượng `Dog` đều là `Object`.
- Không có unchecked cast. Mỗi collection vẫn giữ đối số kiểu khai báo ban đầu.
- Mỗi lệnh `addDogs` tạo hai đối tượng `Dog` mới trong collection tương ứng; không có việc ba collection cùng chia sẻ cấu trúc danh sách.

Nếu có subtype `Poodle extends Dog`, biểu thức tạo `Poodle` cũng được chèn qua `Collection<? super Dog>` vì mọi `Poodle` đều là `Dog`. Nhưng không được chèn tùy tiện một đối tượng `Animal` không phải `Dog`, bởi đích có thể thực sự là `Collection<Dog>`.

## 8. Sao chép từ collection kiểu con vào collection kiểu cha

Một nhu cầu quen thuộc là **đọc dữ liệu từ nguồn và ghi vào đích**. Ví dụ, nguồn có `Integer`, còn đích lưu `Number`; hoặc nguồn có `Dog`, còn đích lưu `Animal`.

Có thể khai báo phương thức:

~~~java
static <T> void appendAll(Collection<? extends T> source,
                          Collection<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

Đây là **phương thức cần đặt trong class và import `java.util.Collection`**.

- `source` là **producer**: phần tử của nó có kiểu `T` hoặc subtype của `T`; đọc thành `T` hợp lệ.
- `destination` là **consumer**: collection đó có đối số kiểu `T` hoặc supertype của `T`; thêm phần tử `T` hợp lệ.

Tạo chương trình **`CollectionTransferDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionTransferDemo {
    private static <T> void appendAll(
            Collection<? extends T> source,
            Collection<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        Collection<Integer> small = List.of(1, 2);
        Collection<Double> decimals = List.of(3.5, 4.5);

        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        appendAll(small, numbers);
        appendAll(decimals, numbers);
        appendAll(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("small = " + small);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CollectionTransferDemo.java
java CollectionTransferDemo
~~~

Stdout:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
small = [1, 2]
~~~

Ví dụ chứng minh rằng wildcard `super` **đưa phần tử vào đích bằng thao tác hợp lệ**. Nó không biến `Collection<Integer>` thành `Collection<Number>` và không cần ép kiểu.

Thư viện chuẩn đã hỗ trợ mẫu này. Chẳng hạn, `Collection.addAll(Collection<? extends E>)` cho phép thêm các phần tử từ nguồn có subtype phù hợp; còn tiện ích `Collections.addAll(Collection<? super T>, T...)` cho phép thêm nhiều đối tượng kiểu `T` vào một đích có đối số kiểu `T` hoặc supertype của nó.

Đối với `List`, `Collections.copy(List<? super T> dest, List<? extends T> src)` cũng thể hiện PECS, nhưng khác `appendAll`: nó **ghi đè các vị trí sẵn có** và yêu cầu `dest` đã đủ kích thước. Không dùng `Collections.copy` như một cách tự động nối vào cuối danh sách.

## 9. Các thao tác được phép và rủi ro khi đọc

Xét một biến:

~~~java
Collection<? super Integer> destination = new ArrayList<Number>();
~~~

Những thao tác sau hợp lệ về mặt generic:

~~~java
destination.add(10);
destination.add(Integer.valueOf(20));
destination.addAll(List.of(30, 40));
destination.add(null); // Biên dịch, nhưng đích thật có thể cấm null.

boolean hasTen = destination.contains(10);
int size = destination.size();

for (Object item : destination) {
    System.out.println(item);
}

destination.remove(10);
destination.clear();
~~~

Đây là **đoạn minh họa cần import `java.util.*` và đặt trong class**. `Collection.addAll` nhận nguồn có kiểu phần tử phù hợp; `contains` và `remove(Object)` không đòi xác định kiểu phần tử của collection. Vì vậy compiler cho phép.

Ngược lại:

~~~java
// destination.add(2.5); // LỖI: Double không phải Integer.
// destination.add("x"); // LỖI: String không phải Integer.

// Integer first = destination.iterator().next(); // LỖI.
// Number first = destination.iterator().next();  // LỖI.
Object first = destination.iterator().next(); // Hợp lệ nếu không rỗng.
~~~

`iterator().next()` có thể ném `NoSuchElementException` nếu collection rỗng; câu nhận xét “hợp lệ” ở trên chỉ nói **biên dịch và kiểu trả về**, không cam kết collection có phần tử. Khi cần thao tác an toàn, hãy kiểm tra `iterator.hasNext()` trước.

Ngoài ra, `? super T` **không phải phép bảo đảm collection mutable**. Ví dụ `List.of(1, 2)` có kiểu `List<Integer>` và gán được vào `Collection<? super Integer>`, nhưng thêm phần tử sẽ ném `UnsupportedOperationException`. Khả năng thêm về **kiểu** và khả năng sửa của **đối tượng thực** là hai điều độc lập.

### Vì sao kết quả đọc có thể không phải `Integer`?

Chương trình dưới đây chạy được:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class SuperReadDemo {
    public static void main(String[] args) {
        Collection<Object> objects = new ArrayList<>();
        objects.add("text");
        objects.add(99);

        Collection<? super Integer> sink = objects;
        sink.add(100);

        for (Object item : sink) {
            System.out.println(item);
        }
    }
}
~~~

Chạy `javac SuperReadDemo.java` và `java SuperReadDemo` cho stdout:

~~~text
text
99
100
~~~

Tham chiếu `sink` được phép thêm `Integer` vào `Collection<Object>`, nhưng những phần tử tồn tại trước đó vẫn có thể là `String`. Bởi vậy, đọc qua `sink` dưới kiểu `Integer` sẽ là một lời hứa không được bảo đảm.

## 10. So với `List<? super T>`: cùng quan hệ kiểu, khác API container

Bài học này sử dụng `Collection<? super T>` để nói về **collection nói chung**. Nếu API cần truy cập vị trí bằng chỉ số, có thể áp dụng cùng wildcard với `List<? super T>`:

~~~java
List<? super Integer> destination = new ArrayList<Number>();
destination.add(1);
destination.add(2);

Object first = destination.get(0); // Hợp lệ.
// Integer n = destination.get(0); // LỖI BIÊN DỊCH.
~~~

Đây là **đoạn minh họa cần import `java.util.*` và đặt trong class**. Khác biệt giữa `Collection` và `List` nằm ở phương thức giao diện: `List` có `get(index)`, `set(index, element)`; `Collection` không có `get(index)`.

Không nhầm kiểu wildcard với tên implementation:

- `Collection<? super Integer>` **có thể trỏ tới `ArrayList<Integer>`, `HashSet<Number>` hoặc collection khác** nếu đối số kiểu phù hợp.
- `List<? super Integer>` chỉ trỏ được tới đối tượng thực hiện `List` với đối số kiểu phù hợp, không trỏ trực tiếp tới một `HashSet`.

Cần thêm phần tử nhưng không quan tâm thứ tự/chỉ số: ưu tiên tham số `Collection<? super T>` để API chấp nhận nhiều implementation. Cần chức năng chỉ có ở `List`: dùng `List<? super T>`. Một collection kiểu `Set` có thể từ chối thêm một phần tử vì đã tồn tại, nên `add` trả `false`; đây là hợp đồng `Collection` chứ không phải lỗi wildcard.

## 11. Những lỗi phổ biến cần tránh

### Lỗi 1. Dùng `Collection<T>` dù chỉ cần thêm `T`

~~~java
static void addAnswer(Collection<Integer> destination) {
    destination.add(42);
}
~~~

Đây là **phương thức minh họa**. Nếu caller có `Collection<Number>`, phương thức từ chối đầu vào dù collection đó có thể lưu `Integer`. Nếu phương thức chỉ thêm số nguyên, chữ ký phù hợp hơn là:

~~~java
static void addAnswer(Collection<? super Integer> destination) {
    destination.add(42);
}
~~~

### Lỗi 2. Nhầm `super` với việc cho đọc mọi phần tử như `T`

`Collection<? super Integer>` có thể tham chiếu tới `Collection<Object>`. Các phần tử cũ của collection này có thể là bất kỳ `Object` nào, nên một vòng lặp `for (Integer x : collection)` **không biên dịch**. Dùng `Object` để đọc, hoặc thiết kế lại API nếu thực sự cần thông tin kiểu mạnh hơn.

### Lỗi 3. Tưởng `? super T` cho thêm cả mọi supertype của `T`

Khi `T = Integer`, `Double` và `Number` **không** phải các kiểu giá trị được bảo đảm thêm vào `Collection<? super Integer>`. Đích có thể là `Collection<Integer>`. Chỉ thêm các giá trị tương thích `Integer` (bao gồm `null` nếu collection hỗ trợ) là hợp lệ.

### Lỗi 4. Nhầm tính linh hoạt của wildcard với phép gán subtype generic

~~~java
Collection<Integer> xs = new ArrayList<>();
Collection<? super Integer> allowed = xs; // Có.
// Collection<Number> wrong = xs;          // Không.
~~~

`allowed` chỉ là **một góc nhìn dùng wildcard**. Nó không làm đối số kiểu của `xs` đổi thành `Number`.

### Lỗi 5. Ép kiểu unchecked để đạt cùng mục tiêu

~~~java
Collection<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
Collection<Number> forged = (Collection<Number>) (Collection<?>) integers;
forged.add(2.5); // Có thể làm ô nhiễm dữ liệu kiểu Integer.
~~~

Đây là **mã cảnh báo, không phải giải pháp**. Ép kiểu unchecked có thể khiến một collection chứa các phần tử không đúng hợp đồng và gây `ClassCastException` tại thao tác đọc trong tương lai. Trong API chỉ cần chèn số nguyên, `Collection<? super Integer>` diễn đạt nhu cầu thật mà không cần cast.

### Lỗi 6. Dùng `? extends T` cho đối tượng chỉ làm đích nhận

~~~java
static void badSink(Collection<? extends Number> values) {
    // values.add(123); // LỖI BIÊN DỊCH.
}
~~~

Trong trường hợp này `extends` thiết kế cho **nguồn đọc**, không bảo đảm có thể thêm `Integer`. Nếu chỉ cần chèn `Integer`, chọn `Collection<? super Integer>`; nếu cần chèn mọi `Number`, chọn `Collection<? super Number>`.

### Lỗi 7. Bỏ qua giới hạn của container thực

Một lời gọi `destination.add(1)` có thể **biên dịch** nhưng vẫn không thành công vì collection không cho sửa, không nhận `null` hoặc có quy tắc lọc trùng. Generics bảo đảm **tương thích kiểu**, không bảo đảm mọi lệnh sửa sẽ thành công. Đọc tài liệu của implementation khi hành vi runtime quan trọng.

## 12. Tự kiểm tra

Giả sử các biến sau được khai báo bên trong một phương thức, với `import java.util.*;`:

~~~java
Collection<Integer> ints = new ArrayList<>();
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();
Collection<Double> doubles = new ArrayList<>();
Collection<? super Integer> sink = numbers;
~~~

Hãy dự đoán những lệnh sau **biên dịch được không**:

| Biểu thức độc lập | Biên dịch? | Giải thích |
| --- | --- | --- |
| `Collection<? super Integer> a = ints;` | Có | Đối số kiểu là `Integer` |
| `Collection<? super Integer> a = numbers;` | Có | `Number` là supertype của `Integer` |
| `Collection<? super Integer> a = objects;` | Có | `Object` là supertype của `Integer` |
| `Collection<? super Integer> a = doubles;` | Không | `Double` không phải supertype của `Integer` |
| `sink.add(123);` | Có | Autoboxing số nguyên thành `Integer` |
| `sink.add(2.5);` | Không | `Double` không được bảo đảm phù hợp |
| `sink.add((Number) 123);` | Không | Kiểu tĩnh của biểu thức là `Number`, có thể không phải `Integer` |
| `Object x = sink.iterator().next();` | Có | Kiểu bảo đảm khi đọc là `Object` |
| `Integer x = sink.iterator().next();` | Không | Không biết đối số kiểu thực của collection |
| `sink.addAll(List.of(1, 2));` | Có | Collection nguồn cung cấp `Integer` |
| `sink.size();` | Có | Không phụ thuộc kiểu phần tử |
| `sink.clear();` | Có | Hợp lệ về kiểu, runtime tùy khả năng sửa |

Các lệnh trong bảng là **các tình huống độc lập**, không được gom toàn bộ vào một phương thức biên dịch thật vì có dòng cố ý sai kiểu và tên biến `a` lặp lại.

Một câu hỏi tư duy: nếu `Collection<Object> objects` đang chứa chuỗi `"hello"`, rồi được dùng như `Collection<? super Integer>`, tại sao `add(7)` được phép trong khi `Integer i = iterator().next()` bị cấm? Vì **thêm `Integer`** là an toàn cho mọi đích có kiểu cha phù hợp, nhưng **đọc mọi phần tử thành `Integer`** là sai với những giá trị cũ.

## 13. Áp dụng quy tắc trong thiết kế API

Chọn tham số generic theo nhu cầu thao tác cụ thể:

1. **Chỉ cần thêm các giá trị `T` vào collection của caller:** chọn `Collection<? super T>`. Đây là trường hợp chính của bài.
2. **Chỉ cần đọc các giá trị như `T` từ collection của caller:** chọn `Collection<? extends T>`.
3. **Đồng thời đọc và ghi chính xác cùng một kiểu `T`, cần duy trì quan hệ kiểu giữa nhiều tham số/giá trị trả về:** cân nhắc `Collection<T>` hoặc một generic method có type parameter rõ ràng.
4. **Không quan tâm kiểu phần tử và không cần thêm phần tử cụ thể:** `Collection<?>` phù hợp để đếm, kiểm tra trạng thái hoặc duyệt như `Object`.
5. **Cần duy trì thứ tự và thao tác bằng chỉ số:** chọn `List` thay vì `Collection`, nhưng giữ nguyên nguyên tắc `? super T` khi nó là đích tiêu thụ.

**Kết luận:** `Collection<? super T>` có nghĩa “tôi có thể nhận một collection của `T` hoặc một kiểu cha của `T` để **ghi các giá trị `T` một cách an toàn**”. Đây là mảnh ghép **Consumer Super** của nguyên tắc PECS. Đổi lại, không được giả định phần tử đọc ra có kiểu `T`; mức bảo đảm chung là `Object`. Chữ ký đúng giúp API linh hoạt với caller mà vẫn giữ được hàng rào kiểm tra kiểu của Java Generics.