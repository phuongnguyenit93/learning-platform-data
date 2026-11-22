# Nhận `List<T>` và danh sách của các kiểu con bằng `? extends T`

Một phương thức cần xử lý các giá trị kiểu `T` thường cũng muốn nhận danh sách chứa **kiểu con của `T`**. Trong Java Generics, chữ ký `List<T>` khi `T` đã cố định **không tự nhận** `List<Subtype>` chỉ vì `Subtype extends T`. Cách diễn đạt một *nguồn dữ liệu có phần tử là `T` hoặc một subtype của `T`* là **`List<? extends T>`**.

Ví dụ, `Integer` và `Double` đều là subtype của `Number`:

~~~java
List<Integer> integers = List.of(1, 2, 3);
List<Double> doubles = List.of(1.5, 2.5);

// List<Number> a = integers; // LỖI BIÊN DỊCH.
List<? extends Number> b = integers; // Hợp lệ.
List<? extends Number> c = doubles;  // Hợp lệ.
~~~

Đây là **đoạn minh họa cần đặt trong class và import `java.util.List`**. Dòng gán trực tiếp vào `List<Number>` bị chú thích vì cố ý sai kiểu. Hai dòng sử dụng wildcard hợp lệ mà không ép kiểu không kiểm tra và không sao chép danh sách.

Ý nghĩa quan trọng: **`? extends T` cho phép nhận nhiều kiểu danh sách, đổi lại compiler hạn chế ghi phần tử mới qua tham chiếu đó.** Cần hiểu cả hai mặt để xây dựng API đúng.

## 1. Vì sao `List<T>` không tự nhận `List<Subtype>` khi `T` đã xác định?

Với biến kiểu thường, quan hệ subtype hoạt động như mong đợi:

~~~java
Integer number = 10;
Number wider = number; // Hợp lệ: Integer extends Number.
~~~

Nhưng Java generic **bất biến (invariant)** theo đối số kiểu:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // LỖI BIÊN DỊCH.
~~~

Đây là **đoạn cố ý không biên dịch**, cần import `java.util.List` và `java.util.ArrayList`. Nếu phép gán ấy được phép, mã dùng `numbers` có thể thêm `Double`:

~~~java
numbers.add(3.14); // Chỉ là giả định nếu phép gán sai phía trên được chấp nhận.
~~~

Khi đó, danh sách ban đầu được khai báo `List<Integer>` lại chứa `Double`, gây nguy cơ `ClassCastException` lúc một nơi khác đọc phần tử như `Integer`. Compiler chặn nguy cơ ngay từ phép gán.

Nói bằng quan hệ kiểu:

- `Integer` là subtype của `Number`.
- `List<Integer>` **không** là subtype của `List<Number>`.
- `List<Integer>` có thể được dùng như `List<? extends Number>`.
- `List<Number>` cũng có thể được dùng như `List<? extends Number>`.

Việc `List<Integer>` không phải `List<Number>` là quy tắc **invariance**; việc wildcard upper bound cho phép sử dụng `List<Integer>` ở nơi yêu cầu `List<? extends Number>` là một quan hệ kiểu **được Java chứng minh an toàn**.

## 2. Cách đọc chữ ký `List<? extends T>`

Trong chữ ký:

~~~java
static void process(List<? extends Number> source) {
    // Được đọc mỗi phần tử như Number.
}
~~~

`?` là **wildcard** biểu thị một đối số kiểu chưa được biết chính xác. `extends Number` giới hạn kiểu ẩn đó phải là `Number` hoặc một subtype phù hợp của `Number`.

Nhờ vậy, chữ ký có thể nhận:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

process(numbers);  // Có.
process(integers); // Có.
process(doubles);  // Có.
~~~

Hai đoạn trên là **mã phương thức/lời gọi minh họa**, cần đặt trong class và import `java.util.*`. Chúng cho thấy một phương thức nhận nhiều kiểu đối số mà vẫn có hợp đồng an toàn.

Tuy nhiên, **không phải bất kỳ subtype nào của `Object` cũng được nhận**: `List<String>` không phù hợp `List<? extends Number>` vì `String` không phải subtype của `Number`.

Điều kiện có thể đọc như sau:

> Mỗi phần tử mà danh sách cung cấp đều phải có thể được sử dụng theo hợp đồng `T`.

Điều kiện này quan trọng khi phương thức gọi các API của `T`. Với `Number`, ta có thể gọi `doubleValue()`, `intValue()`, v.v. trên mỗi phần tử dù danh sách thật chứa `Integer` hay `Double`.

## 3. Ví dụ Java 17+ hoàn chỉnh: một hàm nhận cả số nguyên lẫn số thực

Tạo tệp **`ExtendsNumbersDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ExtendsNumbersDemo {
    private static void printNumbers(List<? extends Number> values) {
        System.out.print("values:");
        for (Number value : values) {
            System.out.print(" " + value);
        }
        System.out.println();
    }

    private static double sum(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4, 6));
        List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
        List<Number> mixed = new ArrayList<>(List.of(10, 20.5));

        printNumbers(integers);
        printNumbers(doubles);
        printNumbers(mixed);

        System.out.println("sum integers = " + sum(integers));
        System.out.println("sum doubles = " + sum(doubles));
        System.out.println("sum mixed = " + sum(mixed));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExtendsNumbersDemo.java
java ExtendsNumbersDemo
~~~

Stdout chính xác:

~~~text
values: 2 4 6
values: 1.5 2.5
values: 10 20.5
sum integers = 12.0
sum doubles = 4.0
sum mixed = 30.5
~~~

Phương thức `printNumbers` và `sum` chỉ phụ thuộc vào các hành vi được bảo đảm bởi `Number`, nên không cần biết subtype cụ thể của phần tử. `doubleValue()` là API được khai báo trong `Number`; ở runtime, implementation tương ứng của `Integer` hay `Double` được gọi.

Điểm lợi là **thay đổi phía caller không buộc thay chữ ký hàm**: cùng một hàm có thể làm việc với `List<Integer>`, `List<Double>`, `List<Number>` và danh sách của các subclass `Number` khác.

## 4. Đọc được như `T` nhưng không được tùy tiện ghi `T`

Với một đối số `List<? extends Number>`, mỗi phần tử đọc ra có thể sử dụng an toàn như `Number`, dù danh sách thật mang `Integer` hay `Double`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> input = integers;
Number first = input.get(0);
// input.add(3); // Không biên dịch: kiểu phần tử ẩn có thể là Double.
~~~

Chính vì vậy, chữ ký nhận danh sách của **nhiều subtype** mà không đánh mất kiểm tra kiểu. Nếu dùng `List<Number>`, compiler không cho truyền biến `List<Integer>` trực tiếp. Đặc biệt, việc nhìn nguồn qua wildcard **không tạo list mới** và không chuyển kiểu phần tử lúc runtime.

Phép `add(null)` có thể qua type checking, nhưng thành công lúc chạy còn phụ thuộc chính sách null/mutability của collection; phép `remove` hoặc `clear` cũng có thể hợp kiểu và sửa dữ liệu thật. Các bài tiếp theo tách riêng ba vấn đề **đọc theo upper bound**, **cấm ghi giá trị tùy ý** và **null** để không đồng nhất chúng.

## 5. Giải nghĩa `List<? extends T>` khi `T` là tham số generic

Đến đây, ta đã dùng `Number` như một upper bound cụ thể. Trong phương thức generic, `T` còn có thể là tham số kiểu:

~~~java
static <T> T first(List<? extends T> source) {
    if (source.isEmpty()) {
        throw new IllegalArgumentException("source must not be empty");
    }
    return source.get(0);
}
~~~

Đây là **một phương thức cần đặt trong class và import `java.util.List`**. `T` là kiểu mà caller muốn nhận, còn `? extends T` cho phép phần tử nguồn thuộc `T` hoặc subtype của `T`.

Ví dụ sử dụng với `T` được chỉ định rõ:

~~~java
List<Integer> integers = List.of(10, 20);
List<Double> doubles = List.of(1.5, 2.5);

Number a = MyUtils.<Number>first(integers); // Hợp lệ.
Number b = MyUtils.<Number>first(doubles);  // Hợp lệ.
~~~

Đoạn gọi này chỉ minh họa chữ ký; giả sử phương thức `first` là `static` trong class `MyUtils`. Ký pháp `<Number>` là **explicit type argument** chọn `T = Number`. Khi đó `List<? extends T>` trở thành `List<? extends Number>`, nên nhận được cả danh sách `Integer` và `Double`.

Một cách viết tương đương trong chương trình thật là đặt `first` và lời gọi vào cùng một class rồi gọi `ClassName.<Number>first(...)`.

### Điều dễ nhầm: phương thức generic nhận `List<T>` cũng có thể dùng cho nhiều kiểu

Cần phân biệt **`T` được cố định** với **`T` được suy luận độc lập mỗi lần gọi**:

~~~java
static <T> void show(List<T> values) {
    System.out.println(values.size());
}
~~~

Phương thức trên có thể được gọi lần lượt với `List<Integer>`, `List<String>`, `List<Double>`, vì compiler chọn một `T` phù hợp cho **mỗi lần gọi riêng**:

~~~java
show(List.of(1, 2));     // T có thể là Integer.
show(List.of("a", "b")); // T có thể là String.
~~~

Các đoạn này là **mã phương thức/lời gọi minh họa cần đặt trong class**. Vì vậy câu “`List<T>` không bao giờ nhận danh sách subtype” sẽ là khái quát **sai** nếu không nói rõ `T` đang được xác định như thế nào.

Khác biệt thật sự xuất hiện khi ta **cần duy trì một upper bound đã biết**, chẳng hạn tham số `Number` cố định, hoặc cần giữ liên hệ kiểu giữa nhiều tham số của cùng một phương thức. Khi `T` đã là `Number`, `List<T>` nghĩa là `List<Number>`, còn `List<? extends T>` vẫn nhận `List<Integer>`, `List<Double>` và `List<Number>`.

## 6. Khi hàm cần đọc nguồn và ghi vào đích: ghép `extends` với `super`

Một hàm sao chép các phần tử kiểu `T` có hai vai trò trái ngược nhau:

- **Nguồn (producer)** cung cấp những phần tử có thể dùng như `T`: `List<? extends T>`.
- **Đích (consumer)** phải nhận được mọi phần tử `T`: `List<? super T>`.

Chữ ký phù hợp:

~~~java
static <T> void copyTo(List<? extends T> source,
                       List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

Đây là **phương thức cần đặt trong class và import `java.util.List`**. Nó được bảo đảm an toàn khi caller cung cấp các kiểu tương thích. Công thức dễ nhớ là **PECS — Producer Extends, Consumer Super**.

Tạo chương trình hoàn chỉnh **`GenericCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericCopyDemo {
    static <T> void copyTo(List<? extends T> source,
                           List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(3.5, 4.5);
        List<Number> numbers = new ArrayList<>();

        copyTo(integers, numbers);
        copyTo(doubles, numbers);

        List<Object> objects = new ArrayList<>();
        copyTo(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("integers = " + integers);
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac GenericCopyDemo.java
java GenericCopyDemo
~~~

Stdout chính xác:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
integers = [1, 2]
~~~

Giải thích kiểu:

1. `integers` là `List<Integer>`. Nó là nguồn hợp lệ khi đích là `List<Number>`, vì `Integer` có thể được nhận như `Number`.
2. `doubles` là `List<Double>`. Nó cũng cung cấp các `Number` hợp lệ cho đích.
3. `numbers` là một `List<Number>`, tiếp tục là nguồn hợp lệ cho `List<Object>`.
4. Không có phép gán sai `List<Integer>` sang `List<Number>`; phương thức **duyệt phần tử** rồi thêm từng giá trị vào danh sách khác.
5. `integers` giữ nguyên, vì nguồn không bị thay đổi.

Nếu thật sự chỉ cần “thêm tất cả phần tử” vào collection đích, thư viện chuẩn đã có `Collection.addAll(Collection<? extends E>)`. Tương tự, `Collections.copy` có chữ ký `<T> void copy(List<? super T> dest, List<? extends T> src)`, nhưng chức năng của nó là **ghi đè các vị trí đã có** và yêu cầu đích đủ độ dài. Không nhầm `Collections.copy` với phép nối vào cuối như `addAll`.

## 7. Có thể giữ danh sách gốc và vẫn tạo `List<T>` rộng hơn

Đôi khi phương thức phía sau thực sự yêu cầu `List<Number>` vì cần thêm các `Number` khác loại. Khi đó **không ép** `List<Integer>` thành `List<Number>`; hãy tạo bản sao:

~~~java
List<Integer> integers = List.of(10, 20);

// List<Number> wrong = integers; // Không biên dịch.
List<Number> right = new ArrayList<>(integers);
right.add(2.5);

System.out.println(integers); // [10, 20]
System.out.println(right);    // [10, 20, 2.5]
~~~

Đây là **đoạn mã cần đặt trong class và import `java.util.*`**. Constructor `ArrayList(Collection<? extends E>)` nhận danh sách có phần tử subtype của `E`. Kiểu đích giúp suy luận `E = Number`. Bản sao giữ các tham chiếu tới phần tử, nhưng cấu trúc danh sách là độc lập: thêm vào `right` không làm thay đổi `integers`.

Phân biệt rõ hai nhu cầu:

- **Chỉ cần quan sát hoặc xử lý các phần tử như `T`**: nhận `List<? extends T>`, không bắt caller sao chép.
- **Cần sở hữu collection chứa được nhiều subtype của `T` và thường xuyên thêm giá trị**: tạo/chấp nhận `List<T>` đúng kiểu và sao chép nguồn khi cần.

Wildcard không làm đổi kiểu khai báo của collection thật.

## 8. Khi upper bound là interface hoặc lớp tự định nghĩa

`extends` trong wildcard là cú pháp áp dụng cho **cả class và interface**, không chỉ class. Ví dụ:

~~~java
static int totalLength(List<? extends CharSequence> texts) {
    int total = 0;
    for (CharSequence text : texts) {
        total += text.length();
    }
    return total;
}
~~~

Đây là **phương thức minh họa cần đặt trong class** và import `java.util.List`. Cả `String` và `StringBuilder` đều triển khai `CharSequence`, nên danh sách tương ứng là đầu vào hợp lệ:

~~~java
int x = totalLength(List.of("Hi", "Java"));
int y = totalLength(List.of(new StringBuilder("AB"),
                            new StringBuilder("C")));
~~~

`x` bằng `6` và `y` bằng `3`. Các phần tử có các lớp thực khác nhau nhưng đều cung cấp phương thức `length()` được khai báo bởi `CharSequence`.

Ở đây, `List<? extends CharSequence>` **không** hứa danh sách chứa đúng kiểu `CharSequence`. Nó hứa danh sách chứa một kiểu cụ thể nào đó phù hợp với `CharSequence`. Vì thế phương thức được phép gọi `length()` nhưng không được tự thêm một chuỗi mới qua tham số wildcard.

Wildcard có thể dùng với lớp tự định nghĩa:

~~~java
class Animal {
    String name() { return "animal"; }
}
class Dog extends Animal {
    @Override String name() { return "dog"; }
}

static void printAnimals(List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
~~~

Đây là **các khai báo minh họa**. `printAnimals` nhận `List<Animal>`, `List<Dog>` hoặc một danh sách lớp con khác của `Animal`. Nếu cần gọi phương thức chỉ tồn tại trên `Dog`, phải thu hẹp kiểu một cách an toàn, vì hợp đồng chung chỉ biết `Animal`.

## 9. Wildcard capture: tại sao đôi khi vẫn có thể ghi trở lại cùng kiểu?

Với `List<? extends T>`, ta không được đưa một phần tử `T` tùy ý vào danh sách vì subtype thật chưa biết. Tuy nhiên, nếu phần tử được lấy từ **chính danh sách ấy**, phương thức generic có thể nắm bắt kiểu ẩn (wildcard capture) và sử dụng lại nó.

Tạo tệp **`CaptureSwapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureSwapDemo {
    static void swapFirstTwo(List<? extends Number> values) {
        if (values.size() >= 2) {
            swapCaptured(values, 0, 1);
        }
    }

    private static <E> void swapCaptured(List<E> list, int i, int j) {
        E previous = list.get(i);
        list.set(i, list.get(j));
        list.set(j, previous);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));

        swapFirstTwo(integers);
        swapFirstTwo(doubles);

        System.out.println(integers);
        System.out.println(doubles);
    }
}
~~~

~~~bash
javac CaptureSwapDemo.java
java CaptureSwapDemo
~~~

Stdout chính xác:

~~~text
[2, 1, 3]
[2.5, 1.5]
~~~

Tại điểm gọi `swapCaptured(values, 0, 1)`, compiler nắm bắt subtype ẩn của wildcard thành một tham số kiểu `E` nhất quán. Hai phần tử được hoán đổi **giữa các vị trí trong cùng một danh sách**, nên không thêm phần tử thuộc lớp khác.

Điều này cho thấy `extends` không có nghĩa “cấm sửa mọi thứ”. Nó cấm những thao tác **không chứng minh được an toàn kiểu**; một generic helper có thể chứng minh việc ghi lại chính phần tử thuộc cùng kiểu được phép.

## 10. Phân biệt `List<T>`, `List<? extends T>` và `List<? super T>`

Khi `T` được cố định (chẳng hạn `T = Number`), ta có:

| Chữ ký | Có thể nhận | Đọc với kiểu tĩnh | Thêm `T` được không? | Vai trò thường gặp |
| --- | --- | --- | --- | --- |
| `List<T>` | Danh sách có đối số kiểu chính xác `T` | `T` | Có | Vừa đọc vừa ghi chính xác `T` |
| `List<? extends T>` | Danh sách của `T` hoặc subtype của `T` | `T` | Không (ngoại trừ `null`) | Nguồn dữ liệu |
| `List<? super T>` | Danh sách của `T` hoặc supertype của `T` | `Object` | Có | Đích nhận dữ liệu |
| `List<?>` | Danh sách của kiểu bất kỳ | `Object` | Không (ngoại trừ `null`) | Đọc/quan sát không cần biết kiểu |

Ví dụ `List<? extends Number>` không nhận `List<Object>` vì `Object` **không phải subtype** của `Number`. Ngược lại, `List<? super Number>` nhận được `List<Object>` nhưng **không nhận `List<Integer>`**, vì `Integer` không phải supertype của `Number`.

Đây là hai chiều sử dụng khác nhau của subtype relation. Chỉ nên chọn wildcard theo vai trò dữ liệu trong API.

## 11. Các lỗi phổ biến khi viết API nhận danh sách kiểu con

### Sai lầm 1 — Dùng `List<Number>` cho một hàm chỉ đọc tất cả các loại số

~~~java
static double total(List<Number> values) {
    return values.stream().mapToDouble(Number::doubleValue).sum();
}

// total(List.of(1, 2)); // Có thể lỗi khi đầu vào đã có kiểu List<Integer>.
~~~

Đoạn này là **mã phương thức và ví dụ minh họa**, không phải chương trình độc lập. Với một biến `List<Integer> integers` cố định, `total(integers)` chắc chắn không biên dịch. Khi đầu vào là biểu thức `List.of(1, 2)` chưa có kiểu đích cố định, **target typing** có thể khiến compiler suy luận `Number`, vì vậy không nên dùng duy nhất biểu thức đó để chứng minh lỗi. Cách kiểm tra rõ ràng là:

~~~java
List<Integer> integers = List.of(1, 2);
// total(integers); // LỖI BIÊN DỊCH.
~~~

Nếu `total` chỉ đọc, chữ ký thích hợp thường là `List<? extends Number>`.

### Sai lầm 2 — Tưởng `? extends T` cho phép thêm một subtype bất kỳ

~~~java
static void addPi(List<? extends Number> numbers) {
    // numbers.add(3.14); // LỖI BIÊN DỊCH.
}
~~~

Một danh sách truyền vào có thể là `List<Integer>`, nên thêm `Double` không được bảo đảm an toàn.

### Sai lầm 3 — Tưởng wildcard biến kiểu phần tử thành `T` lúc runtime

`List<? extends Number>` vẫn có thể trỏ tới `List<Integer>`. Wildcard không sao chép, không đổi đối tượng, không thực hiện ép kiểu từng phần tử. Nó thay đổi **những thao tác compiler cho phép qua tham chiếu**.

### Sai lầm 4 — Ép kiểu unchecked để “làm cho gán được”

~~~java
List<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
List<Number> forged = (List<Number>) (List<?>) integers;
forged.add(3.14); // Nguy cơ heap pollution.
~~~

Đây là **mã mô tả nguy cơ**, không phải cách chuyển đổi. `@SuppressWarnings("unchecked")` chỉ giấu cảnh báo; nó không xác minh danh sách có thể chứa `Double`. Một nơi khác đọc phần tử như `Integer` có thể gặp `ClassCastException`.

### Sai lầm 5 — Quên phân biệt giới hạn của generic và khả năng sửa của collection

`ArrayList<Integer>` là collection mutable nhưng vẫn được nhìn dưới kiểu `List<? extends Number>`. Ngược lại, `List.of(1, 2)` là unmodifiable dù tham chiếu khai báo `List<Integer>` hay `List<? extends Number>`. Giới hạn ghi do wildcard và việc collection hỗ trợ sửa là **hai quy tắc độc lập**.

### Sai lầm 6 — Dùng wildcard khi API cần trả về đúng subtype của caller

Nếu cần trả chính xác một phần tử thuộc cùng kiểu với danh sách đầu vào, generic method có thể rõ hơn:

~~~java
static <E> E firstExact(List<E> values) {
    return values.get(0);
}
~~~

Đây là **phương thức minh họa cần đặt trong class**. Khi đầu vào có kiểu `List<Dog>`, compiler có thể suy luận `E = Dog` và kiểu trả về là `Dog`. Với một phương thức chỉ cần tính toán qua API của `Animal`, `List<? extends Animal>` có thể đủ và đơn giản hơn.

## 12. Bài tập tự kiểm tra

Giả sử các dòng sau đã được khai báo bên trong một phương thức và import `java.util.*`:

~~~java
List<Integer> ints = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(2.5, 3.5));
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<? extends Number> input = ints;
~~~

Xác định các lệnh biên dịch được hay không:

| Lệnh | Biên dịch? | Vì sao? |
| --- | --- | --- |
| `List<Number> x = ints;` | Không | Generic invariance |
| `List<? extends Number> x = ints;` | Có | `Integer` là subtype của `Number` |
| `List<? extends Number> x = doubles;` | Có | `Double` là subtype của `Number` |
| `List<? extends Number> x = objects;` | Không | `Object` không phải subtype của `Number` |
| `Number value = input.get(0);` | Có | Phần tử được bảo đảm là `Number` |
| `Integer value = input.get(0);` | Không | Không bảo đảm subtype là `Integer` |
| `input.add(3);` | Không | Không biết kiểu phần tử ẩn |
| `input.add(null);` | Có | `null` tương thích với mọi kiểu tham chiếu; runtime có thể từ chối |
| `input.remove(0);` | Có | Không cần cung cấp phần tử kiểu chưa biết |
| `numbers.addAll(ints);` | Có | `addAll` chấp nhận `Collection<? extends Number>` |
| `objects.addAll(numbers);` | Có | Mọi `Number` cũng là `Object` |

Các ví dụ trong bảng được xem như **lệnh độc lập**; những lệnh đánh dấu “Không” cố ý sai kiểu và không được sao chép vào một chương trình muốn biên dịch thành công.

## 13. Quy tắc ứng dụng

Khi nhận danh sách có kiểu phần tử `T` hoặc các subtype của `T`, hãy xác định phương thức sẽ **làm gì với phần tử**. Nếu chủ yếu **đọc** như `T` và dùng API của `T`, chọn `List<? extends T>`. Nếu cần **ghi** các phần tử `T` vào collection do caller cung cấp, dùng `List<? super T>` cho đích. Nếu cần cả đọc và ghi chính xác một kiểu duy nhất hoặc cần trả về subtype cụ thể, cân nhắc generic method với `<T>`. Nếu cần trộn các subtype khác nhau trong một danh sách mới, tạo `List<T>` thích hợp và sao chép phần tử.

**`List<? extends T>` giải quyết bài toán chấp nhận `List<T>` và danh sách các kiểu con mà không làm mất an toàn kiểu.** Phương thức đổi lấy khả năng đọc linh hoạt bằng việc giới hạn thêm giá trị mới qua góc nhìn wildcard, nhờ đó giữ nguyên hợp đồng của danh sách gốc.