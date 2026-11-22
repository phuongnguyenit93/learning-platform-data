# Kiểu con của đối số không tự tạo quan hệ kiểu con cho generic

Trong Java, quan hệ kế thừa giữa hai **đối số kiểu** không tự động trở thành quan hệ kế thừa giữa hai **kiểu generic** được tạo từ chúng. Đây là tính **bất biến (invariance)** của generic. Nắm vững quy tắc này giúp tránh lỗi gán kiểu, thiết kế API đọc/ghi dữ liệu đúng và chọn wildcard phù hợp.

## 1. Phân biệt quan hệ kiểu của phần tử và của container

Vì `Integer` là kiểu con của `Number`, ta có thể gán một `Integer` cho biến `Number`:

```java
Integer integer = 42;
Number number = integer; // Hợp lệ: Integer là kiểu con của Number.
```

Nhưng quan hệ đó **không** suy ra:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // LỖI BIÊN DỊCH.
```

Viết theo ký hiệu quan hệ kiểu con:

- `Integer <: Number` là đúng.
- `List<Integer> <: List<Number>` là **sai**.
- `ArrayList<Integer> <: List<Integer>` là **đúng**, vì `ArrayList<E>` triển khai `List<E>` với cùng đối số kiểu `Integer`.
- `List<Integer> <: List<? extends Number>` là **đúng**; vế phải là một kiểu có wildcard, không phải `List<Number>`.

Quy tắc áp dụng tương tự cho `Set<String>` và `Set<Object>`, `Map<String, Integer>` và `Map<String, Number>`, hoặc `Box<Dog>` và `Box<Animal>`: mỗi cách tham số hóa kiểu phải được xét riêng, dù một hoặc nhiều đối số có quan hệ kế thừa. Generic Java không mặc định hiệp biến hay phản biến theo đối số kiểu.

**Chú ý:** `List<Number>` hoàn toàn có thể chứa các đối tượng `Integer`, `Double`, `Long`... vì từng phần tử ấy là `Number`. Điều này khác với việc gán **cả một** `List<Integer>` vào biến `List<Number>`.

## 2. Vì sao Java cấm phép gán tưởng như hợp lý?

Giả sử trình biên dịch cho phép `List<Integer>` được xem là `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
// Giả sử phép gán sau được cho phép (thực tế là LỖI BIÊN DỊCH):
List<Number> numbers = integers;

numbers.add(3.14);           // Double cũng là Number, nên nhìn từ numbers là hợp lệ.
Integer value = integers.get(0); // Nhưng danh sách Integer đã chứa Double!
```

Hai biến cùng trỏ tới một danh sách. Nếu cho phép phép gán, hợp đồng “mọi phần tử của `List<Integer>` là `Integer`” có thể bị phá vỡ thông qua biến `List<Number>`. Java chặn lỗi ngay tại **thời điểm biên dịch**, thay vì cho phép kiểu phần tử của danh sách bị thay đổi sai.

Đây là lý do bản chất, không đơn thuần là hạn chế cú pháp. Bất biến bảo vệ an toàn kiểu khi cấu trúc dữ liệu có cả khả năng **đọc** lẫn **ghi**.

## 3. Ví dụ Java 17 chạy được: kiểu phần tử khác với kiểu danh sách

Lưu thành `InvarianceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InvarianceDemo {
    static void printNumbers(List<? extends Number> values) {
        for (Number number : values) {
            System.out.println(number);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2));

        // List<Number> invalid = integers; // Không biên dịch.
        List<? extends Number> readable = integers; // Hợp lệ.
        System.out.println(readable.get(0));

        List<Number> numbers = new ArrayList<>();
        numbers.add(3);   // Integer được xem như Number.
        numbers.add(2.5); // Double được xem như Number.
        System.out.println(numbers);

        printNumbers(integers); // Nhận List<Integer> qua wildcard.
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac InvarianceDemo.java
java InvarianceDemo
```

Kết quả:

```text
1
[3, 2.5]
1
2
```

Trong ví dụ này, `List<Number>` cho phép thêm nhiều lớp con của `Number` vào danh sách do chính nó quản lý. Biến `readable` chỉ mang cam kết “danh sách có một kiểu phần tử cụ thể nào đó là kiểu con của `Number`”; trình biên dịch chưa biết kiểu cụ thể đó là `Integer` hay `Double`. Vì vậy, `readable.get(0)` đọc ra dưới kiểu `Number`, nhưng `readable.add(3)` sẽ không biên dịch.

## 4. Wildcard biểu diễn quan hệ tương thích cần thiết

Java dùng **wildcard** để cho phép API làm việc với các generic có đối số kiểu khác nhau mà không phá vỡ bất biến của `List<T>`.

| Khai báo | Chấp nhận các ví dụ | Đọc ra | Có thể thêm phần tử nào? |
| --- | --- | --- | --- |
| `List<Number>` | `List<Number>` | `Number` | `Number` và các kiểu con của nó |
| `List<? extends Number>` | `List<Integer>`, `List<Double>`, `List<Number>` | `Number` | Không thêm được giá trị `Number` cụ thể; chỉ `null` được phép về mặt kiểu |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>` | `Object` | `Integer` và kiểu con của `Integer` (nếu có) |
| `List<?>` | `List<String>`, `List<Integer>`, v.v. | `Object` | Chỉ `null` được phép về mặt kiểu |

Bảng mô tả quyền **theo hệ kiểu tĩnh**. Danh sách thực tế còn có thể không hỗ trợ sửa đổi, ví dụ danh sách tạo bằng `List.of(...)` sẽ ném `UnsupportedOperationException` khi gọi thao tác thay đổi ngay cả khi biểu thức hợp lệ về kiểu.

### 4.1. `? extends Number`: phù hợp khi **đọc** các giá trị số

`List<? extends Number>` có nghĩa là “danh sách của một kiểu chưa biết, nhưng kiểu đó là `Number` hoặc kiểu con của `Number`”. Vì thế:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number n = source.get(0); // Hợp lệ.
Object o = source.get(0); // Hợp lệ.

// source.add(3);   // Không biên dịch.
// source.add(3.5); // Không biên dịch.
```

Với `source.add(3)`, compiler không thể khẳng định kiểu phần tử thực sự của `source` là `Integer`; nó cũng có thể là `List<Double>`. Việc đọc dưới kiểu `Number` thì an toàn trong mọi trường hợp. `extends` ở wildcard bao gồm chính kiểu cận trên: `List<Number>` cũng gán được cho `List<? extends Number>`.

### 4.2. `? super Integer`: phù hợp khi **ghi** `Integer`

`List<? super Integer>` có nghĩa là “danh sách của một kiểu chưa biết, nhưng kiểu đó là `Integer` hoặc kiểu cha của `Integer`”. Ta có thể thêm `Integer`, vì mọi danh sách phù hợp đều nhận giá trị này:

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);    // Hợp lệ.
destination.add(20);    // Hợp lệ.
Object item = destination.get(0); // Chỉ chắc chắn đọc ra Object.

// Number n = destination.get(0); // Không biên dịch.
// destination.add(2.5);         // Không biên dịch.
```

Nếu kiểu thật là `List<Object>`, thao tác đọc cũng chỉ bảo đảm `Object`. Nếu kiểu thật là `List<Integer>`, `Double` không thể được thêm vào. Đây là hai giới hạn cần giữ để wildcard an toàn.

### 4.3. `?`: chấp nhận mọi đối số kiểu, nhưng ít khả năng thao tác

`List<?>` thích hợp khi chỉ cần duyệt, đếm, kiểm tra rỗng hoặc xem phần tử dưới kiểu `Object`:

```java
static void printSize(List<?> items) {
    System.out.println(items.size());
}
```

`List<?>` **không** tương đương `List<Object>`. Một `List<String>` có thể truyền cho `List<?>`, nhưng không thể gán cho `List<Object>`. Và `List<?>` không cho phép thêm tùy ý `Object`.

## 5. Ví dụ hoàn chỉnh: PECS, đọc từ source và ghi vào destination

Quy tắc thực hành **PECS** là *Producer Extends, Consumer Super*:

- **Producer:** tham số chủ yếu cung cấp giá trị cho hàm → `? extends T`.
- **Consumer:** tham số chủ yếu nhận giá trị do hàm thêm vào → `? super T`.

Ví dụ lưu thành `WildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardDemo {
    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number number : source) {
            total += number.doubleValue();
        }
        return total;
    }

    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        System.out.println(sum(integers));
        addDefaults(numbers);
        addDefaults(objects);

        System.out.println(numbers);
        System.out.println(objects);
        Object first = objects.get(0);
        System.out.println(first);
    }
}
```

```bash
javac WildcardDemo.java
java WildcardDemo
```

Kết quả:

```text
6.0
[10, 20]
[10, 20]
10
```

`sum` có thể xử lý `List<Integer>`, `List<Double>` hoặc `List<Number>` vì nó chỉ lấy giá trị ra và dùng API của `Number`. `addDefaults` có thể ghi hai số nguyên vào `List<Integer>`, `List<Number>` hoặc `List<Object>` vì tất cả những kiểu đích này đều nhận `Integer`.

PECS là hướng dẫn chọn kiểu tham số theo chiều luân chuyển dữ liệu, **không** phải quy tắc rằng mọi danh sách luôn phải khai báo wildcard. Khi hàm vừa đọc vừa thêm cùng kiểu `T`, một `List<T>` với tham số kiểu cụ thể có thể thích hợp hơn.

## 6. Generic method giúp nối hai cấu trúc có đối số khác nhau

Khi cả đầu vào và đầu ra phải dùng chung một quan hệ kiểu, dùng **tham số kiểu của phương thức** kết hợp wildcard. Đây là cách diễn đạt trực tiếp yêu cầu “đọc các giá trị thuộc `T` hoặc kiểu con và chuyển vào nơi nhận `T` hoặc kiểu cha”.

Lưu thành `TransferDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class TransferDemo {
    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        copyAll(integers, numbers);
        System.out.println(numbers);

        List<String> words = List.of("Java", "Generics");
        List<Object> objects = new ArrayList<>();
        copyAll(words, objects);
        System.out.println(objects);
    }
}
```

```bash
javac TransferDemo.java
java TransferDemo
```

Kết quả:

```text
[1, 2, 3]
[Java, Generics]
```

Hai lời gọi hoạt động mà không cần ép kiểu. Trình biên dịch suy luận một `T` thỏa quan hệ cận trên/cận dưới tại mỗi lời gọi. Với `copyAll(integers, numbers)`, `Integer` phù hợp làm `T`: `List<Integer>` cung cấp phần tử kiểu `Integer` và `List<Number>` nhận được chúng.

**Giới hạn của ví dụ:** nguồn và đích nên là những danh sách thích hợp cho việc sao chép; không dùng vòng lặp này để khẳng định mọi cách đọc-ghi đồng thời trên cùng danh sách, hoặc trên những danh sách bị thay đổi đồng thời từ thread khác, đều an toàn. Các vấn đề đó độc lập với quy tắc bất biến của generic.

## 7. Kế thừa class/interface generic vẫn hợp lệ nếu đối số kiểu khớp

Đừng nhầm quy tắc bất biến với việc Java cấm kế thừa giữa các kiểu generic. Quan hệ kế thừa khai báo trong class/interface vẫn có hiệu lực:

```java
ArrayList<Integer> arrayList = new ArrayList<>();
List<Integer> list = arrayList; // Đúng: ArrayList<Integer> implements List<Integer>.
```

Tương tự, xét khai báo:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class IntegerBox extends Box<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
```

Khi đó:

```java
Box<Integer> first = new IntegerBox(42); // Hợp lệ.
Box<? extends Number> second = new IntegerBox(42); // Hợp lệ.

// Box<Number> wrong = new IntegerBox(42); // Không biên dịch.
```

`IntegerBox` kế thừa trực tiếp `Box<Integer>`, không kế thừa `Box<Number>`. Để biên dịch riêng đoạn này, đặt hai class trong cùng nguồn với tên file tùy ý và một class có `main` nếu muốn chạy; các đoạn ở mục này nhằm minh họa quan hệ kiểu, không phải chương trình có đầu ra.

Với interface tự định nghĩa, quy tắc cũng vậy: nếu `interface Repository<T>` thì `Repository<Dog>` không tự là kiểu con của `Repository<Animal>` chỉ vì `Dog extends Animal`.

## 8. Cận kiểu của tham số generic không làm kiểu generic hiệp biến

Khai báo:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T getValue() {
        return value;
    }
}
```

Cận `T extends Number` chỉ giới hạn **đối số kiểu được phép** khi tạo `NumberBox<T>`, ví dụ `Integer`, `Double` hoặc `Number`. Nó không tạo quan hệ kiểu con giữa `NumberBox<Integer>` và `NumberBox<Number>`:

```java
NumberBox<Integer> intBox = new NumberBox<>(10);

// NumberBox<Number> wrong = intBox; // Không biên dịch.
NumberBox<? extends Number> readOnlyView = intBox; // Hợp lệ.
Number value = readOnlyView.getValue();             // Hợp lệ.
```

Hai ý “`T` buộc phải thuộc họ `Number`” và “các bản tham số hóa `NumberBox<T>` có quan hệ kế thừa với nhau” là hai vấn đề khác nhau.

## 9. Bất biến còn áp dụng khi generic lồng nhau

Một bẫy thường gặp là cho rằng có wildcard ở **tầng trong** thì danh sách ở **tầng ngoài** cũng tự tương thích:

```java
List<List<Integer>> matrix = new ArrayList<>();

// List<List<? extends Number>> wrong = matrix; // Không biên dịch.
List<? extends List<? extends Number>> view = matrix; // Hợp lệ.
```

`List<Integer>` phù hợp với `List<? extends Number>`, nhưng điều đó không khiến `List<List<Integer>>` phù hợp với `List<List<? extends Number>>`. Tầng `List<...>` bên ngoài vẫn bất biến. Wildcard ở tầng ngoài cho phép đọc các danh sách con phù hợp mà không cho phép thêm tùy ý danh sách con mới.

Khi thiết kế API lồng nhiều generic, cần xét quan hệ kiểu **ở từng tầng**. Chỉ thêm wildcard ở những tầng mà API thực sự cần tính linh hoạt; tránh biến chữ ký thành khó đọc không cần thiết.

## 10. Phân biệt với array: array hiệp biến nhưng có kiểm tra khi chạy

Array Java cho phép `Integer[]` gán vào `Number[]`, khác với `List<Integer>` và `List<Number>`. Sự linh hoạt của array đi cùng một phép kiểm tra kiểu lúc chạy.

Lưu thành `ArrayContrast.java`:

```java
public class ArrayContrast {
    public static void main(String[] args) {
        Number[] values = new Integer[1]; // Hợp lệ với array.
        values[0] = 1;                     // Integer: hợp lệ lúc chạy.

        try {
            values[0] = 3.14; // Double không thể nằm trong Integer[] thật.
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
```

```bash
javac ArrayContrast.java
java ArrayContrast
```

Kết quả:

```text
ArrayStoreException
```

Trong khi đó, generic của Java kiểm tra phần lớn quan hệ giữa các đối số kiểu lúc biên dịch; thông tin đối số kiểu thường bị **xóa kiểu (type erasure)** trong bytecode. Type erasure **không có nghĩa** `List<Integer>` có thể gán an toàn cho `List<Number>`. Chính quy tắc bất biến tại lúc biên dịch bảo vệ hợp đồng phần tử. Ép kiểu không kiểm tra hoặc raw type có thể phá an toàn kiểu và dẫn đến `ClassCastException` ở một chỗ đọc về sau; đó không phải cách giải quyết hợp lệ cho phép gán bị từ chối.

## 11. Lỗi phổ biến và cách sửa

### Lỗi 1: yêu cầu `List<Number>` dù hàm chỉ đọc

```java
static double average(List<Number> values) { // Quá chặt nếu chỉ cần đọc.
    return values.stream().mapToDouble(Number::doubleValue).average().orElse(0);
}
```

Nếu muốn nhận cả `List<Integer>` và `List<Double>`, đổi tham số thành:

```java
static double average(List<? extends Number> values) {
    return values.stream().mapToDouble(Number::doubleValue).average().orElse(0);
}
```

Việc đổi chữ ký không biến danh sách đầu vào thành `List<Number>`; nó chỉ mô tả chính xác nhu cầu **đọc** của hàm.

### Lỗi 2: thêm phần tử qua `? extends Number`

```java
List<? extends Number> values = new ArrayList<Integer>();
// values.add(100); // Không biên dịch dù 100 là Integer.
```

Nếu hàm cần thêm giá trị `Integer` vào các danh sách có khả năng nhận nó, cân nhắc `List<? super Integer>`. Nếu muốn sở hữu một danh sách chứa nhiều loại `Number`, tạo `List<Number>` mới:

```java
List<Number> values = new ArrayList<>();
values.add(100);
values.add(3.14);
```

### Lỗi 3: nghĩ `List<?>` là `List<Object>`

```java
List<String> strings = List.of("a", "b");
List<?> anything = strings; // Hợp lệ.

// List<Object> objects = strings; // Không biên dịch.
```

`List<Object>` có thể nhận thêm `Object`; `List<?>` thì không. Hai kiểu có lời hứa khác nhau về dữ liệu.

### Lỗi 4: ép kiểu qua raw type để lách trình biên dịch

```java
List<Integer> integers = new ArrayList<>();
// Tránh cách sau: raw type và unchecked conversion đánh mất bảo đảm an toàn.
// List<Number> unsafe = (List) integers;
```

Không dùng cách này trong code ứng dụng. Thiết kế lại chữ ký với `? extends`, `? super`, phương thức generic, hoặc tạo danh sách đích có đối số kiểu thực sự phù hợp.

### Lỗi 5: chỉ xét quan hệ kế thừa của một đối số trong generic nhiều tham số

`Map<String, Integer>` không trở thành `Map<String, Number>` chỉ vì `Integer extends Number`. Nếu API chỉ đọc giá trị, có thể cân nhắc một chữ ký theo nhu cầu cụ thể, chẳng hạn `Map<String, ? extends Number>`. Điều tương tự xảy ra ở các generic lồng nhau như mục 9.

### Lỗi 6: nhầm bất biến với khả năng thay đổi của collection

Wildcard mô tả khả năng đọc/ghi **theo kiểu**. Nó không bảo đảm collection là mutable, thread-safe, có thứ tự hay không chứa `null`. Ví dụ `List.of(1, 2)` là danh sách không sửa đổi; cố `add` sẽ thất bại lúc chạy dù khai báo là `List<Integer>`.

## 12. Cách chọn chữ ký API

Hãy tự hỏi dữ liệu được dùng theo hướng nào:

1. **Muốn một danh sách có thể chứa nhiều loại `Number` và tự thêm chúng:** dùng `List<Number>`.
2. **Muốn nhận danh sách bất kỳ có phần tử thuộc họ `Number` để đọc:** dùng `List<? extends Number>`.
3. **Muốn truyền các `Integer` vào một danh sách nhận được chúng:** dùng `List<? super Integer>`.
4. **Chỉ cần xem kích thước, duyệt dưới kiểu `Object` hoặc kiểm tra rỗng:** dùng `List<?>`.
5. **Muốn liên kết an toàn kiểu đầu vào và đầu ra:** dùng phương thức generic `<T>` kết hợp `? extends T` và `? super T` theo chiều dữ liệu.
6. **Muốn vừa đọc và ghi chính xác cùng một kiểu phần tử do caller quyết định:** cân nhắc `List<T>`; wildcard không phải lúc nào cũng cần.

Một số câu hỏi tự kiểm tra:

- `List<Integer>` có gán trực tiếp cho `List<Number>` không? **Không.**
- `List<Integer>` có truyền cho `List<? extends Number>` không? **Có.**
- Một `List<? extends Number>` có cho phép thêm `Integer` không? **Không**, vì kiểu phần tử cụ thể chưa biết.
- `List<Number>` có truyền cho `List<? super Integer>` không? **Có.**
- Một `List<? super Integer>` có cho phép đọc trực tiếp ra `Integer` không? **Không**, chỉ chắc chắn là `Object`.
- `ArrayList<Integer>` có là kiểu con của `List<Integer>` không? **Có**, do quan hệ triển khai interface cùng đối số kiểu.

**Ghi nhớ:** quan hệ `S extends T` không làm `G<S>` trở thành kiểu con của `G<T>`. Khi muốn nhận nhiều cách tham số hóa của một generic, hãy thể hiện đúng yêu cầu đọc/ghi bằng wildcard hoặc tham số kiểu của phương thức.