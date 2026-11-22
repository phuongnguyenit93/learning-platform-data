# Quy tắc PECS: nguồn cung cấp dùng `extends`, đích nhận dữ liệu dùng `super`

Khi một phương thức Java Generics làm việc với một tập hợp, điều quan trọng là xác định **tập hợp ấy cung cấp dữ liệu cho phương thức hay nhận dữ liệu từ phương thức**. Đây là ý tưởng của **PECS — Producer Extends, Consumer Super**:

- **Producer (nguồn cung cấp):** phương thức **đọc các giá trị kiểu `T`** từ đối tượng đầu vào. Thường khai báo `Collection<? extends T>`, `List<? extends T>` hoặc một dạng generic tương đương.
- **Consumer (đích nhận):** phương thức **ghi các giá trị kiểu `T`** vào đối tượng đầu vào. Thường khai báo `Collection<? super T>` hoặc `List<? super T>`.

`extends` và `super` được chọn theo **vai trò của tham số trong phương thức đang viết**, không phải theo việc đối tượng có khả năng đọc và ghi nói chung. Một `ArrayList<Integer>` có thể được truyền dưới góc nhìn producer trong phương thức tính tổng và dưới góc nhìn consumer trong phương thức thêm số nguyên.

PECS giúp chấp nhận các kiểu con/kiểu cha thích hợp mà **không phá an toàn kiểu**, đặc biệt khi Java generic bất biến (invariant) theo đối số kiểu.

## 1. Bài toán: vì sao không dùng `List<Number>` cho mọi thứ?

Giả sử có `List<Integer>` và `List<Double>`. Vì `Integer` và `Double` đều là `Number`, một phương thức tính tổng phải đọc được cả hai danh sách. Nhưng phép gán này bị cấm:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // LỖI BIÊN DỊCH.
~~~

Đây là **đoạn minh họa sai kiểu**, cần đặt trong class và import `java.util.*` nếu muốn thử biên dịch. Java không coi `List<Integer>` là subtype của `List<Number>`. Nếu cho phép, tham chiếu `numbers` có thể thêm `Double` vào danh sách vốn chỉ chấp nhận `Integer`.

Mặt khác, nếu một phương thức chỉ muốn **thêm `Integer`**, đích có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`: cả ba kiểu đều nhận được một `Integer`.

Hai nhu cầu cần hai hợp đồng riêng:

~~~java
static double sum(List<? extends Number> source) {
    double total = 0.0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}

static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
~~~

Đây là **hai phương thức minh họa**, cần đặt trong class với `import java.util.List;`. `sum` yêu cầu nguồn cung cấp giá trị có thể đọc như `Number`; `addDefaults` yêu cầu đích nhận được các giá trị `Integer`. Chúng cùng khai báo wildcard nhưng theo hai chiều ngược nhau.

## 2. Producer Extends: nguồn cung cấp `? extends T`

Xem chữ ký:

~~~java
static void printNumbers(List<? extends Number> source) {
    for (Number number : source) {
        System.out.println(number);
    }
}
~~~

Nghĩa là: **đối số kiểu cụ thể của danh sách phải là `Number` hoặc subtype của `Number`**. Vì vậy `printNumbers` nhận được `List<Integer>`, `List<Double>`, `List<Number>` và các danh sách số phù hợp khác.

Compiler không biết subtype cụ thể của `source`, nhưng biết **mọi phần tử đọc ra đều sử dụng được như `Number`**:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number first = source.get(0); // Hợp lệ.
Object alsoFirst = source.get(0); // Hợp lệ.

// Integer exact = source.get(0); // LỖI: subtype có thể là Double.
// source.add(3);                // LỖI: subtype thực có thể là Double.
// source.add(3.5);              // LỖI: subtype thực có thể là Integer.
~~~

Đây là **đoạn minh họa cần đặt trong class với `import java.util.*;`**. `source` đang trỏ tới `List<Integer>`, nhưng **hợp đồng kiểu tĩnh** chỉ nói `List<? extends Number>`. Compiler không được lấy thông tin bên ngoài khai báo kiểu này để cho phép thêm `Integer` tùy ý.

Nếu `source.add(3)` được phép, cùng chữ ký ấy có thể đang tham chiếu `List<Double>` và gây sai kiểu. Vì thế, producer thuận tiện để **đọc**, nhưng không thể thêm giá trị không phải `null` thông qua `add`.

### Ví dụ chạy được: đọc nhiều subtype cùng một phương thức

Tạo tệp **`ProducerDemo.java`**:

~~~java
import java.util.List;

public class ProducerDemo {
    private static double sum(List<? extends Number> source) {
        double total = 0.0;
        for (Number n : source) {
            total += n.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4, 6);
        List<Double> doubles = List.of(1.5, 2.5);
        List<Number> mixed = List.of(3, 4.5);

        System.out.println("integers = " + sum(integers));
        System.out.println("doubles = " + sum(doubles));
        System.out.println("mixed = " + sum(mixed));
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac ProducerDemo.java
java ProducerDemo
~~~

Stdout:

~~~text
integers = 12.0
doubles = 4.0
mixed = 7.5
~~~

Một phương thức xử lý được cả ba kiểu danh sách vì phép tính tổng chỉ dùng các thao tác được `Number` bảo đảm. Không có ép kiểu unchecked hoặc sao chép collection.

## 3. Consumer Super: đích nhận `? super T`

Xem chữ ký:

~~~java
static void addNumbers(List<? super Integer> destination) {
    destination.add(5);
    destination.add(10);
}
~~~

Hợp đồng này chấp nhận `List<Integer>`, `List<Number>` hoặc `List<Object>` vì **cả ba đều lưu được phần tử kiểu `Integer`**. Nó không nhận `List<Double>`: `Double` là subtype khác của `Number`, không phải supertype của `Integer`.

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addNumbers(integers); // Hợp lệ.
addNumbers(numbers);  // Hợp lệ.
addNumbers(objects);  // Hợp lệ.

// addNumbers(new ArrayList<Double>()); // LỖI: Double không là supertype của Integer.
~~~

Các đoạn trên minh họa lời gọi một phương thức đã khai báo, cần đặt trong class và import `java.util.*`.

Có thể gọi `destination.add(5)` vì `5` được boxing thành `Integer`. Nhưng compiler không cho phép thêm một `Number` tùy ý:

~~~java
List<? super Integer> destination = new ArrayList<Number>();

destination.add(Integer.valueOf(7)); // Hợp lệ.
destination.add(8);                  // Hợp lệ qua autoboxing.
destination.add(null);               // Hợp lệ về kiểu.
// destination.add(Double.valueOf(1.5)); // LỖI.
// destination.add(new Object());       // LỖI.
~~~

Đây là **đoạn minh họa cần import `java.util.*`**. Lý do: tham chiếu wildcard có thể trỏ tới `List<Integer>`, nên compiler không được cho thêm `Double` hay `Object` vào nó. `null` tương thích với mọi kiểu tham chiếu, nhưng collection thật vẫn có thể cấm `null` hoặc không hỗ trợ sửa.

### Vì sao consumer chỉ cho đọc như `Object`?

`List<? super Integer>` có thể trỏ tới `List<Object>` chứa `String`, `Boolean` hoặc nhiều giá trị khác, nên **không bảo đảm mọi phần tử đang có đều là `Integer`**:

~~~java
List<Object> any = new ArrayList<>();
any.add("hello");
any.add(42);

List<? super Integer> sink = any;
sink.add(7);

Object first = sink.get(0); // Hợp lệ: thực tế là String.
// Integer n = sink.get(0); // LỖI BIÊN DỊCH.
// Number n = sink.get(0);  // LỖI BIÊN DỊCH.
~~~

Do đó, `super` **mạnh ở phía ghi `T`** nhưng **yếu hơn ở phía đọc**: trình biên dịch chỉ cam kết kiểu chung là `Object`. Không suy luận kiểu dữ liệu đã tồn tại chỉ từ những phần tử mà một phương thức vừa thêm vào.

## 4. Ví dụ Java 17+: producer và consumer trong một chương trình

Tạo tệp **`PecsBasicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PecsBasicsDemo {
    private static void printAll(List<? extends Number> source) {
        for (Number n : source) {
            System.out.print(n + " ");
        }
        System.out.println();
    }

    private static void appendIds(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        List<Integer> ids = new ArrayList<>(List.of(1, 2));
        List<Number> numbers = new ArrayList<>(List.of(3.5));
        List<Object> objects = new ArrayList<>();

        printAll(ids);
        printAll(numbers);

        appendIds(ids);
        appendIds(numbers);
        appendIds(objects);

        System.out.println("ids = " + ids);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PecsBasicsDemo.java
java PecsBasicsDemo
~~~

Stdout chính xác:

~~~text
1 2 
3.5 
ids = [1, 2, 10, 20]
numbers = [3.5, 10, 20]
objects = [10, 20]
~~~

Dấu cách ở cuối hai dòng đầu là do `System.out.print(n + " ")`. Nếu muốn không có dấu cách cuối dòng, có thể đổi vòng lặp sang `StringJoiner`; điều đó không liên quan tới PECS.

Ví dụ dùng cùng `List<Integer> ids` làm **producer** khi `printAll(ids)` và **consumer** khi `appendIds(ids)`. Vai trò phụ thuộc **thao tác của hàm**, không phụ thuộc bản chất cố định của đối tượng `ids`.

Danh sách `numbers` chứa một `Double` sẵn có, nhưng vẫn nhận thêm các `Integer` qua `appendIds`. Điều này an toàn với `List<Number>` và minh họa lý do `? super Integer` có ích.

## 5. Ghép cả hai chiều để chuyển phần tử từ nguồn sang đích

Ứng dụng đặc trưng của PECS là **chuyển/sao chép phần tử có subtype cụ thể vào collection nhận một kiểu rộng hơn**.

Chữ ký tổng quát:

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
~~~

Đây là **một phương thức cần đặt trong class với `import java.util.Collection;`**. `T` đại diện cho kiểu mà ta muốn truyền qua ranh giới nguồn–đích.

- `Collection<? extends T>` bảo đảm mọi phần tử đọc từ `source` đều dùng được như `T`.
- `Collection<? super T>` bảo đảm mọi phần tử `T` đều có thể được thêm vào `destination`.
- Phương thức không cần biết subtype cụ thể của nguồn hoặc supertype cụ thể của đích.
- `T` có thể được compiler suy luận trong từng lời gọi hoặc được caller nêu rõ bằng cú pháp `<T>`.

### Chương trình chạy được: chuyển `Integer` và `Double` sang `Number`

Tạo **`PecsTransferDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class PecsTransferDemo {
    private static <T> void appendAll(
            Collection<? extends T> source,
            Collection<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(3.5, 4.5);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(integers, numbers);
        appendAll(doubles, numbers);
        appendAll(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("integers = " + integers);
        System.out.println("doubles = " + doubles);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PecsTransferDemo.java
java PecsTransferDemo
~~~

Stdout:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
integers = [1, 2]
doubles = [3.5, 4.5]
~~~

Các lời gọi thứ nhất và thứ hai nạp những phần tử `Integer`/`Double` vào `List<Number>` mà không bao giờ gán `List<Integer>` trực tiếp sang `List<Number>`. Lời gọi thứ ba nạp các `Number` vào `List<Object>`. Mỗi collection đích có cấu trúc riêng; thêm phần tử không làm thay đổi collection nguồn.

**Lưu ý về aliasing:** bản minh họa giả định nguồn và đích khác nhau. Khi nguồn và đích trỏ tới **cùng một collection mutable**, vòng lặp thêm vào collection trong lúc duyệt chính nó có thể phát sinh `ConcurrentModificationException` hoặc hành vi phụ thuộc implementation. Nếu API cần hỗ trợ trường hợp này, có thể chụp bản sao tạm trước khi thêm, ví dụ `destination.addAll(new ArrayList<T>(source))` trong phương thức generic; nên xác định rõ hợp đồng thay vì ngầm cho rằng luôn an toàn.

## 6. Ví dụ với quan hệ kế thừa nghiệp vụ

PECS không chỉ dành cho kiểu số. Giả sử `Dog` và `Cat` là các subtype của `Animal`. Ta muốn lấy các động vật từ một danh sách loài cụ thể và thêm vào danh sách tổng hợp.

Tạo **`PecsAnimalsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PecsAnimalsDemo {
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

    static class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    private static <T> void copyInto(
            List<? extends T> source,
            List<? super T> destination) {
        destination.addAll(source);
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(new Dog("Bim"), new Dog("Milo"));
        List<Cat> cats = List.of(new Cat("Miu"));
        List<Animal> animals = new ArrayList<>();
        List<Object> everything = new ArrayList<>();

        PecsAnimalsDemo.<Animal>copyInto(dogs, animals);
        PecsAnimalsDemo.<Animal>copyInto(cats, animals);
        PecsAnimalsDemo.<Animal>copyInto(animals, everything);

        System.out.println("animals = " + animals);
        System.out.println("everything = " + everything);
    }
}
~~~

Chạy:

~~~bash
javac PecsAnimalsDemo.java
java PecsAnimalsDemo
~~~

Stdout chính xác:

~~~text
animals = [Bim, Milo, Miu]
everything = [Bim, Milo, Miu]
~~~

Ở các lời gọi trên, ta chọn rõ `T = Animal`:

- `List<Dog>` và `List<Cat>` phù hợp với tham số nguồn `List<? extends Animal>`.
- `List<Animal>` và `List<Object>` phù hợp với tham số đích `List<? super Animal>`.
- Phương thức `copyInto` sử dụng `List.addAll(Collection<? extends E>)` để thêm các phần tử từ nguồn, không làm thay đổi kiểu danh sách gốc.
- Các collection đích chứa **tham chiếu tới cùng các đối tượng Animal** được sao chép từ nguồn, không tự động tạo bản sao sâu của từng đối tượng.

Nếu muốn truyền `List<Dog>` làm **đích của những giá trị `Animal` bất kỳ**, compiler phải từ chối: danh sách chó không được hứa nhận một `Cat`. Đó chính là giới hạn an toàn kiểu mà PECS giữ lại.

## 7. PECS xuất hiện ngay trong thư viện chuẩn Java

Quy tắc không chỉ là mẹo ghi nhớ. Nhiều chữ ký Java Collections Framework đã áp dụng hai chiều wildcard.

### 7.1. `Collection.addAll(Collection<? extends E>)`

Giả sử có `Collection<Number> destination`. Phương thức `addAll` cần **đọc** các phần tử từ đối số và thêm vào collection đích, nên đối số nguồn có dạng `Collection<? extends E>`:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);

numbers.addAll(integers); // Hợp lệ.
numbers.add(3.5);
System.out.println(numbers); // [1, 2, 3.5]
~~~

Đây là **đoạn minh họa cần đặt trong class với `import java.util.*;`**. `numbers` có `E = Number`, do đó nguồn `Collection<? extends Number>` có thể là `List<Integer>`.

### 7.2. `Collections.addAll(Collection<? super T>, T...)`

Phương thức utility `Collections.addAll` thêm nhiều giá trị kiểu `T` vào một collection đích. Vì collection ấy **tiêu thụ** giá trị `T` nên dùng `Collection<? super T>`:

~~~java
Collection<Number> numbers = new ArrayList<>();
Collections.addAll(numbers, 1, 2, 3);
System.out.println(numbers); // [1, 2, 3]
~~~

Đây là **đoạn minh họa cần import `java.util.*`**. Phần `T...` là varargs kiểu `T`, ở ví dụ các `Integer` được đưa vào một `Collection<Number>`.

### 7.3. `Collections.copy`: một consumer được điền theo chỉ số

Chữ ký của `Collections.copy` cũng có nguồn `List<? extends T>` và đích `List<? super T>`, nhưng **đích xuất hiện trước**:

~~~java
// Chữ ký API chuẩn để đọc, không phải phương thức cần khai báo lại:
static <T> void copy(List<? super T> dest, List<? extends T> src)
~~~

Nguồn cung cấp `T`; đích nhận `T` bằng thao tác **`set` trên các vị trí đã có**. Vì vậy `Collections.copy` không nối thêm phần tử, và `dest.size()` phải ít nhất bằng `src.size()`; đích còn phải hỗ trợ ghi đè. Nếu mục tiêu là append, hãy dùng `destination.addAll(source)`. Điều kiện về kích thước và tính mutable là hợp đồng runtime, khác với bảo đảm kiểu của PECS.

### 7.4. `Comparator<? super T>`: consumer không phải collection

Một `Comparator<T>` **nhận hai giá trị `T`** để gọi `compare`, nên `List<Integer>.sort(...)` có thể chấp nhận `Comparator<Number>` thông qua `Comparator<? super Integer>`. Không có phần tử nào được lưu vào comparator: “consumer” ở đây có nghĩa nó **nhận giá trị kiểu `T` làm đầu vào**.

Hai ví dụ API này nối PECS với thư viện chuẩn; bài đọc chữ ký `Collections.copy`, `addAll` và `Comparator` đi sâu vào overload, output, cảnh báo compiler và các ngoại lệ runtime.


## 8. Khi PECS không nên áp dụng máy móc

PECS là nguyên tắc thiết kế **chữ ký API**, không có nghĩa mọi generic parameter phải là wildcard.

### 8.1. Khi vừa đọc và ghi đúng cùng một kiểu `T`

~~~java
static <T> void replaceFirst(List<T> list, T replacement) {
    if (!list.isEmpty()) {
        T previous = list.set(0, replacement);
        System.out.println("old = " + previous);
    }
}
~~~

Đây là **phương thức minh họa cần đặt trong class với `import java.util.List;`**. `List<T>` liên kết kiểu phần tử đọc ra với kiểu giá trị mới được ghi vào. Dùng `List<? extends T>` sẽ cản `set` với giá trị `T` bất kỳ; dùng `List<? super T>` sẽ không cho đọc phần tử ra dưới kiểu `T` như đã viết.

Vì vậy, nếu API thực sự **cả đọc và ghi theo một hợp đồng kiểu xác định**, `List<T>` có thể đúng hơn.

### 8.2. Nếu không cần biết kiểu phần tử

Một phương thức chỉ in kích thước danh sách hoặc kiểm tra rỗng có thể dùng `List<?>`:

~~~java
static boolean hasItems(List<?> values) {
    return !values.isEmpty();
}
~~~

Đây là phương thức minh họa, cần import `java.util.List`. Nó chấp nhận bất kỳ danh sách nào và không cần một cận kiểu `T` cụ thể. Sử dụng `List<? extends Object>` trong trường hợp thông thường có ý nghĩa gần như `List<?>`, nhưng không có lợi ích rõ ràng so với dạng ngắn gọn.

### 8.3. Cẩn thận khi `T` được compiler suy luận

Xem:

~~~java
static <T> void show(List<T> input) {
    System.out.println(input.size());
}
~~~

Phương thức generic này có thể lần lượt nhận `List<Integer>` và `List<String>` ở **các lời gọi riêng biệt**, vì `T` có thể được suy luận khác nhau. Vì thế không nên nói tuyệt đối rằng “chữ ký `List<T>` không bao giờ chấp nhận các kiểu khác nhau”.

Khác biệt cần nắm:

- Khi `T` **đã cố định là `Number`**, `List<T>` chỉ tương thích trực tiếp với `List<Number>`, còn `List<? extends T>` nhận `List<Integer>`, `List<Double>`…
- Khi `T` là type parameter **được suy luận mỗi lần gọi**, `List<T>` vẫn có thể dùng cho những đối số kiểu khác nhau, miễn là ràng buộc của toàn lời gọi phù hợp.
- Wildcard đặc biệt hữu ích khi một phương thức cần **chấp nhận một nguồn subtype và một đích supertype có quan hệ qua cùng `T`**.

Không nên thay mọi `List<T>` bằng `List<? extends T>` chỉ để đạt vẻ “linh hoạt”; hãy nhìn thao tác cụ thể.

## 9. Giới hạn về thay đổi dữ liệu và `null`

`? extends T` thường được mô tả là **read-only view**, nhưng cách diễn đạt này chỉ chính xác nếu hiểu là “không thể tự ý ghi một giá trị kiểu cụ thể mới”.

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = numbers;

source.remove(0); // Hợp lệ về kiểu.
source.clear();    // Hợp lệ về kiểu.
source.add(null);  // Hợp lệ về kiểu; collection thật có thể không chấp nhận.
~~~

Đây là **đoạn minh họa cần import `java.util.*`**. Không có yêu cầu cung cấp một `Number` hay `Integer` để thực hiện `remove`/`clear`, nên compiler cho phép. Với một danh sách bất biến về cấu trúc như `List.of(1, 2)`, các thao tác sửa có thể ném `UnsupportedOperationException`.

`? super T` cũng **không bảo đảm collection thật sửa được**:

~~~java
List<Integer> fixed = List.of(1, 2);
List<? super Integer> sink = fixed;
// sink.add(3); // Biên dịch, nhưng chạy sẽ ném UnsupportedOperationException.
~~~

Đoạn này là minh họa; dòng gọi được chú thích nhằm tránh chương trình lỗi. Java Generics kiểm soát **kiểu dữ liệu**; khả năng sửa, chính sách `null`, lọc trùng và thứ tự phần tử là những đặc tính bổ sung của implementation.

Một chi tiết khác: `? super T` cho phép thêm giá trị thuộc **`T` và các subtype của `T`**, không phải thêm mọi supertype của `T`. Với `? super Integer`, thêm `Integer` hợp lệ nhưng thêm một `Number` có kiểu tĩnh rộng hơn không được bảo đảm.

## 10. Các lỗi hiểu sai PECS thường gặp

**Nhầm lẫn 1: “`extends` chỉ nhận đúng `T`.”** Sai. `List<? extends Number>` nhận cả `List<Integer>` và `List<Double>` vì đó là nguồn có phần tử subtype của `Number`.

**Nhầm lẫn 2: “`super` nhận danh sách của mọi kiểu con.”** Sai. `List<? super Integer>` nhận đối số kiểu `Integer` và các supertype của nó, không nhận `List<Double>` và không nhận `List<Dog>` nếu `Dog` không là supertype của `Integer`.

**Nhầm lẫn 3: “Đọc được thành `T` thì thêm `T` được.”** Sai với `? extends T`. Compiler không biết subtype cụ thể thật sự là gì; việc ghi một `T` tổng quát có thể phá hợp đồng của nguồn.

**Nhầm lẫn 4: “Thêm được `T` thì đọc ra phải là `T`.”** Sai với `? super T`. Collection đích có thể là `List<Object>` chứa những phần tử cũ không phải `T`; đọc qua wildcard chỉ bảo đảm `Object`.

**Nhầm lẫn 5: “`extends` và `super` biến `List<A>` thành `List<B>`.”** Sai. Wildcard cung cấp góc nhìn với phép gán và thao tác được chứng minh an toàn; nó không đổi dữ liệu, không sao chép danh sách và không sửa đối số kiểu của object.

**Nhầm lẫn 6: “Dùng cast unchecked sẽ giải quyết.”** Không an toàn. Ép một `List<Integer>` thành `List<Number>` qua raw hoặc wildcard rồi thêm `Double` có thể gây heap pollution và `ClassCastException` khi đọc kiểu `Integer`. Hãy dùng wildcard đúng vai trò hoặc tạo collection mới nếu cần chứa các loại dữ liệu rộng hơn.

**Nhầm lẫn 7: “`super` luôn cho thêm và `extends` không bao giờ sửa được.”** Đây là sự nhầm lẫn giữa **kiểm tra kiểu** với **khả năng sửa runtime**. Một collection không sửa được vẫn có thể là đối số phù hợp kiểu của `? super T`; `? extends T` vẫn có thể dùng `clear` trên một collection cho phép sửa.

**Nhầm lẫn 8: “`Collections.copy` tự tăng kích thước destination.”** Sai. Nó ghi đè phần tử tại các vị trí hiện có; không tự append. Dùng `addAll` khi muốn tăng số lượng phần tử.

## 11. Bài tập tự kiểm tra kiểu

Giả sử những biến sau được khai báo trong một phương thức với `import java.util.*;`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? extends Number> producer = integers;
List<? super Integer> consumer = numbers;
~~~

Xét **từng lệnh độc lập**:

| Biểu thức | Biên dịch? | Vì sao? |
| --- | --- | --- |
| `producer = doubles;` | Có | `Double` là subtype của `Number` |
| `producer = objects;` | Không | `Object` không phải subtype của `Number` |
| `Number n = producer.get(0);` | Có | Producer bảo đảm đọc như `Number` |
| `producer.add(42);` | Không | Không biết subtype thực của producer |
| `producer.add(null);` | Có | `null` tương thích kiểu tham chiếu; runtime có thể từ chối |
| `consumer = objects;` | Có | `Object` là supertype của `Integer` |
| `consumer = doubles;` | Không | `Double` không phải supertype của `Integer` |
| `consumer.add(42);` | Có | Consumer nhận `Integer` |
| `consumer.add(2.5);` | Không | Đích có thể là `List<Integer>` |
| `Object x = consumer.get(0);` | Có | Consumer chỉ bảo đảm `Object` khi đọc |
| `Integer x = consumer.get(0);` | Không | Collection có thể là `List<Object>` |
| `numbers.addAll(integers);` | Có | `addAll` đọc nguồn `<? extends Number>` |
| `Collections.copy(numbers, integers);` | Có | Chữ ký tuân PECS; đích phải đủ phần tử lúc chạy |

Lệnh `Collections.copy(numbers, integers)` trong trạng thái **`numbers` đang rỗng** sẽ biên dịch nhưng ném `IndexOutOfBoundsException` lúc chạy. Câu hỏi “có biên dịch?” và “có chạy thành công?” phải được phân biệt.

Hãy tự trả lời thêm: một phương thức nhận `Collection<? super Animal>` có thể thêm `Dog`, `Cat` không? **Có**, miễn `Dog` và `Cat` kế thừa `Animal`. Nó có thể đọc mọi phần tử như `Animal` không? **Không**, vì đích có thể là `Collection<Object>` chứa các đối tượng khác loại.

## 12. Quy trình thiết kế chữ ký theo luồng dữ liệu

Khi viết một API generic, có thể thực hiện bốn bước:

1. **Xác định giá trị `T` có đi ra khỏi tham số hay đi vào tham số.** Nếu tham số chủ yếu cung cấp giá trị, nó là producer. Nếu tham số chủ yếu nhận giá trị, nó là consumer.
2. **Chọn cận wildcard phù hợp.** Với producer cần đọc như `T`, sử dụng `? extends T`. Với consumer cần chấp nhận `T`, sử dụng `? super T`.
3. **Kiểm tra thao tác thật trong thân hàm.** Nếu `extends` mà cần thêm một `T` tùy ý, hoặc `super` mà cần đọc chắc chắn là `T`, chữ ký hiện tại không đáp ứng nhu cầu; nên điều chỉnh hợp đồng, dùng `List<T>` hoặc một phương thức generic liên kết kiểu.
4. **Kiểm tra yêu cầu runtime.** Collection có sửa được không, có nhận `null` không, có duy trì thứ tự hay loại trùng không, nguồn và đích có thể là cùng một đối tượng không? Các vấn đề này nằm ngoài bảo đảm của PECS.

Bảng ghi nhớ:

| Vai trò của tham số trong hàm | Kiểu điển hình | Điều được bảo đảm |
| --- | --- | --- |
| Đọc các phần tử như `T` | `Collection<? extends T>` | Mọi phần tử lấy ra là `T` hoặc subtype của `T` |
| Ghi các phần tử `T` | `Collection<? super T>` | Collection nhận được giá trị `T` và subtype của nó |
| Cần cả đọc và ghi cùng kiểu `T` | `Collection<T>`, `List<T>` | Một đối số kiểu cụ thể liên kết các thao tác |
| Không cần biết kiểu phần tử | `Collection<?>` | Có thể duyệt phần tử như `Object` và dùng thao tác không phụ thuộc kiểu |

**PECS = Producer Extends, Consumer Super.** Nguồn dùng `extends` để truyền ra `T` an toàn; đích dùng `super` để nhận `T` an toàn. Hai chiều wildcard mở rộng khả năng tái sử dụng của API trong khi giữ nguyên bất biến generic của Java.