# Wildcard, PECS và phương sai trong API generic

Trong Java 27, **generics** giúp biểu diễn mối quan hệ kiểu tại thời điểm biên dịch: `List<String>` chứa các phần tử được sử dụng như `String`, còn `List<Integer>` chứa các phần tử được sử dụng như `Integer`. Tuy nhiên, khi thiết kế API dùng collections, một phương thức chỉ cần đọc số có nên nhận đúng `List<Number>`? Một phương thức chỉ cần thêm `Integer` có thực sự cần đúng `List<Integer>`?

Câu trả lời dẫn đến ba khái niệm quan trọng:

- **Wildcard** (`?`): ký hiệu một kiểu đối số chưa biết, có thể đi kèm cận trên `extends` hoặc cận dưới `super`.
- **Phương sai (variance)**: cách quan hệ subtype của phần tử được phản ánh qua kiểu generic của đối tượng chứa phần tử. Trong Java, generic types thông thường **bất biến** (*invariant*), nhưng wildcard tạo các *góc nhìn* linh hoạt hơn.
- **PECS** (*Producer Extends, Consumer Super*): nguyên tắc chọn wildcard theo việc một tham số **cung cấp dữ liệu cho** hay **nhận dữ liệu từ** mã của chúng ta.

Bài học này thuộc chương **Generics và hệ thống kiểu** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Tất cả cú pháp và API được trình bày đều tiếp tục áp dụng trong Java SE 27; không dựa vào raw types hay kỹ thuật legacy để giải quyết lỗi generic.

## 1. Vì sao `List<Dog>` không phải `List<Animal>`?

Giả sử `Dog` là subtype của `Animal`:

```java
class Animal {
    final String name;

    Animal(String name) {
        this.name = name;
    }
}

final class Dog extends Animal {
    Dog(String name) {
        super(name);
    }
}

final class Cat extends Animal {
    Cat(String name) {
        super(name);
    }
}
```

Một `Dog` là một `Animal`, nhưng phép gán sau **không hợp lệ**:

```java
List<Dog> dogs = new ArrayList<>();
// List<Animal> animals = dogs; // Lỗi biên dịch
```

Nếu phép gán đó được phép, mã dùng `animals` sẽ có thể thêm `Cat` vào danh sách thực tế vốn được khai báo chỉ chứa `Dog`:

```java
// Giả sử phép gán sai ở trên được chấp nhận:
// animals.add(new Cat("Mimi"));
// Dog first = dogs.get(0); // Vi phạm bảo đảm kiểu Dog
```

Để ngăn tình huống này, Java coi `List<Dog>` và `List<Animal>` là hai parameterized types khác nhau; không có quan hệ subtype trực tiếp giữa chúng chỉ vì `Dog extends Animal`. Đây là **invariance**:

```text
Dog <: Animal
    |
    +-- Không suy ra: List<Dog> <: List<Animal>
```

Ngược lại, bản thân các triển khai `ArrayList<Dog>` vẫn có thể gán cho giao diện `List<Dog>` vì quan hệ subtype giữa các **generic classes/interfaces** tương ứng:

```java
ArrayList<Dog> arrayList = new ArrayList<>();
List<Dog> dogs = arrayList; // Hợp lệ
```

Khi chỉ cần duyệt các phần tử như `Animal`, ta nên dùng **wildcard** thay vì ép `List<Dog>` thành `List<Animal>`.

## 2. Ba dạng wildcard cần nhớ

| Kiểu tham số | Ý nghĩa trực quan | Đọc ra an toàn | Ghi một giá trị không-null vào được? |
| --- | --- | --- | --- |
| `List<?>` | List của **một kiểu chưa biết** | `Object` | Không thể thêm một giá trị tùy ý |
| `List<? extends Number>` | List của **một kiểu chưa biết là subtype của Number** | `Number` | Không thể thêm `Number` hay `Integer` tùy ý |
| `List<? super Integer>` | List của **một kiểu chưa biết là supertype của Integer** | `Object` | Có thể thêm `Integer` |
| `List<Integer>` | List có đối số kiểu chính xác là `Integer` | `Integer` | Có thể thêm `Integer` |

Những nhận xét trong bảng nói về **an toàn kiểu tại compile time**, không phải collection có mutable hay không. Ví dụ, `List.of(1, 2)` là một list không sửa được dù ta tham chiếu nó bằng `List<Integer>`; khi gọi `add` vẫn có thể ném `UnsupportedOperationException` lúc chạy.

Trong một generic type có cận khác `Object`, kiểu đọc an toàn của `?` có thể chặt hơn. Ví dụ với `class Box<T extends Number>`, tham chiếu `Box<?>` vẫn cho phép đọc giá trị theo cận `Number`. Khi nói “đọc ra `Object`”, các ví dụ trong bài dùng `List<E>` có cận mặc định là `Object`.

## 3. Unbounded wildcard: `<?>`

`List<?>` nghĩa là “list của một loại phần tử nào đó nhưng **chưa biết loại nào**”. Nó không đồng nghĩa với `List<Object>`.

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}

printAll(List.of("Java", "27"));
printAll(List.of(10, 20, 30));
```

`printAll` không cần biết loại phần tử. Mỗi phần tử đều là một tham chiếu có thể sử dụng như `Object`, nên `List<?>` phù hợp với mục tiêu đọc tổng quát.

Trái lại:

```java
static void printObjects(List<Object> values) {
    values.forEach(System.out::println);
}

List<String> names = List.of("Java", "27");
// printObjects(names); // Lỗi biên dịch: List<String> không là List<Object>
```

`List<Object>` hứa rằng mã trong phương thức có thể thêm **bất kỳ `Object` nào**; vì thế không được nhận danh sách kiểu `String` như một `List<Object>`.

### 3.1. Thao tác nào được phép trên `List<?>`?

```java
List<?> items = new ArrayList<String>(List.of("A", "B"));
Object first = items.get(0); // Hợp lệ
int size = items.size();     // Hợp lệ

// items.add("C");           // Lỗi biên dịch
// items.add(42);            // Lỗi biên dịch
items.add(null);             // Hợp lệ về kiểu, nếu List cho phép sửa
items.clear();               // Hợp lệ về kiểu, nếu List cho phép sửa
```

Giới hạn “không ghi” của wildcard không đồng nghĩa collection **bất biến**. Mã vẫn có thể xóa phần tử, sắp xếp hoặc thêm `null` trong các trường hợp được phép về kiểu và triển khai list hỗ trợ. Chỉ nên xem `<?>` là **góc nhìn không biết chính xác kiểu phần tử**, không phải một wrapper bảo vệ khỏi mọi phép sửa.

### 3.2. Khi nào dùng `<?>`?

Chọn `<?>` khi thuật toán **không cần liên hệ** kiểu phần tử với tham số hay kết quả khác, ví dụ in nội dung, kiểm tra `size()`, đếm số phần tử hoặc xóa toàn bộ các phần tử nếu API có chủ đích làm vậy.

Nếu mục tiêu là đọc phần tử theo một kiểu cụ thể, cần một **upper-bounded wildcard** như `? extends Number`.

## 4. Upper-bounded wildcard: `? extends T`

`? extends T` biểu diễn một kiểu cụ thể nhưng chưa biết, có upper bound là `T`. Kiểu đó có thể là `T` hoặc một subtype của `T`.

```java
static double total(List<? extends Number> numbers) {
    double result = 0;
    for (Number number : numbers) {
        result += number.doubleValue();
    }
    return result;
}

double a = total(List.of(1, 2, 3));
double b = total(List.of(1.25, 2.75));
```

Phương thức này chấp nhận `List<Integer>`, `List<Double>`, `List<Long>` và `List<Number>` (nếu chúng đáp ứng cận trên). Điều thuật toán cần chỉ là đọc mỗi phần tử như một `Number`.

### 4.1. Vì sao không thêm được `Integer`?

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> numbers = integers;

Number first = numbers.get(0); // Hợp lệ
// numbers.add(3);             // Lỗi biên dịch
// numbers.add(3.14);          // Lỗi biên dịch
```

`numbers` có thể đang tham chiếu tới `List<Integer>`, `List<Double>` hay một list của subtype khác. Dù `Integer` và `Double` đều là `Number`, compiler không thể chứng minh việc thêm một trong hai kiểu là an toàn với **mọi** kiểu phần tử có thể có.

Ngay cả việc thêm một biến `Number` cũng không an toàn:

```java
Number value = Integer.valueOf(5);
// numbers.add(value); // Vẫn lỗi biên dịch
```

Quy tắc này bảo vệ phần tử gốc khỏi bị chèn dữ liệu không đúng kiểu. Như với `<?>`, `add(null)` vẫn được phép ở mức kiểu, và các phép xóa có thể hợp lệ; vì thế “producer” không có nghĩa API hoàn toàn bất biến.

### 4.2. Covariance ở vị trí sử dụng

Một `List<Dog>` có thể được xem qua tham chiếu `List<? extends Animal>`:

```java
List<Dog> dogs = new ArrayList<>();
List<? extends Animal> animals = dogs;
```

Góc nhìn `List<? extends Animal>` mang tính **covariant** với subtype của `Animal`. Nhưng đây là **use-site variance của wildcard**, không phải khẳng định `List<T>` tự nhiên là covariant. Việc đọc như `Animal` an toàn bởi vì mọi `Dog` đều là `Animal`; việc thêm một `Animal` bất kỳ bị cấm.

## 5. Lower-bounded wildcard: `? super T`

`? super T` mô tả một kiểu phần tử chưa biết nhưng là **supertype của `T`**. Với `? super Integer`, list đích có thể thực sự là `List<Integer>`, `List<Number>` hoặc `List<Object>`.

```java
List<? super Integer> sink = new ArrayList<Number>();

sink.add(10);
sink.add(Integer.valueOf(20));

Object first = sink.get(0); // Chỉ được bảo đảm là Object
// Integer number = sink.get(0); // Lỗi biên dịch
```

Vì mọi supertype của `Integer` đều có thể chứa một giá trị `Integer`, việc thêm `Integer` là an toàn. Tuy nhiên, khi đọc ra, không thể giả định phần tử chắc chắn là `Integer`: một `List<Object>` có thể đã chứa các kiểu đối tượng khác trước đó.

```java
static void putSample(List<? super Integer> destination) {
    destination.add(42);
}

putSample(new ArrayList<Integer>());
putSample(new ArrayList<Number>());
putSample(new ArrayList<Object>());
```

### 5.1. Contravariance ở vị trí sử dụng

Giả sử `Dog extends Animal`. Một thao tác chỉ **nhận `Dog`** có thể ghi vào list kiểu `Dog`, `Animal` hoặc `Object`:

```java
static void registerDog(List<? super Dog> registry, Dog dog) {
    registry.add(dog);
}

List<Animal> animals = new ArrayList<>();
registerDog(animals, new Dog("Milo"));
```

Góc nhìn `List<? super Dog>` là một dạng **contravariant use-site view**. Type system cho phép dùng “đích chấp nhận phạm vi rộng hơn” khi phương thức chỉ cần cung cấp `Dog` để ghi.

Không nhầm `super` với “có thể thêm bất kỳ supertype nào”. Với `List<? super Dog>`, ta có thể thêm `Dog` (và subtype của `Dog` nếu có), chứ **không** được tự ý thêm một `Animal` bất kỳ, vì list thực tế có thể là `List<Dog>`.

## 6. PECS: Producer Extends, Consumer Super

**PECS** là quy tắc ghi nhớ khi thiết kế tham số generic:

> **Producer Extends, Consumer Super.** Nếu một nguồn *cung cấp `T`* cho thuật toán, cân nhắc `? extends T`. Nếu một đích *nhận `T`* từ thuật toán, cân nhắc `? super T`.

Chữ “producer/consumer” ở đây nói về **vai trò của đối tượng trong thuật toán**, không phải class nào cũng tự nhiên chỉ đọc hoặc chỉ ghi.

| Vai trò của tham số | Tác vụ | Kiểu nên cân nhắc |
| --- | --- | --- |
| Nguồn (producer) | Đọc phần tử dưới dạng `T` | `Iterable<? extends T>` |
| Đích (consumer) | Thêm các giá trị kiểu `T` | `Collection<? super T>` |
| Không quan tâm phần tử | Chỉ lấy kích thước hoặc duyệt dưới dạng `Object` | `Collection<?>` |
| Đọc **và** ghi cùng kiểu chính xác | Phải giữ quan hệ cùng một kiểu phần tử | `List<T>`, dùng type parameter `T` |

### 6.1. Ví dụ phương thức sao chép kiểu PECS

```java
import java.util.Collection;

static <T> void appendAll(
        Collection<? super T> destination,
        Iterable<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
```

Sử dụng:

```java
List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();

appendAll(numbers, integers);
System.out.println(numbers); // [1, 2, 3]
```

Diễn giải:

1. `source` **sinh** các giá trị có thể dùng như `T`, nên dùng `Iterable<? extends T>`.
2. `destination` **nhận** giá trị `T`, nên dùng `Collection<? super T>`.
3. Phương thức không cần biết hoặc thay đổi kiểu phần tử cụ thể của hai collection.
4. `Iterable` và `Collection` là kiểu tham số rộng vừa đủ cho thao tác cần thiết; không ép người gọi phải truyền `List` nếu ta chỉ duyệt nguồn và thêm vào đích.

Đích phải hỗ trợ `add` về mặt runtime. Truyền một collection không sửa được có thể dẫn đến `UnsupportedOperationException`. Ngoài ra, nếu `source` và `destination` cùng tham chiếu đến một collection, việc vừa duyệt vừa thêm có thể gây kết quả bất ngờ hoặc `ConcurrentModificationException`, tùy loại collection. Một API thực tế nên quy định rõ trường hợp alias này.

### 6.2. Ví dụ `Collections.copy` trong thư viện chuẩn

Java Collections Framework có API với hình dạng PECS:

```java
public static <T> void copy(
        List<? super T> destination,
        List<? extends T> source);
```

Đó là chữ ký của `Collections.copy` (được viết lại theo tên tham số dễ đọc). Nó **ghi đè các phần tử đã có trong đích**, chứ không thêm phần tử vào cuối như `appendAll` ở trên.

```java
import java.util.Collections;

List<Integer> source = List.of(10, 20);
List<Number> destination =
        new ArrayList<>(List.of(0, 0, 0));

Collections.copy(destination, source);
System.out.println(destination); // [10, 20, 0]
```

Với `Collections.copy`, kích thước của `destination` phải **ít nhất bằng** kích thước `source`, và list đích phải hỗ trợ thay thế phần tử qua `set`. Tạo `new ArrayList<>()` rỗng rồi gọi `Collections.copy` với nguồn không rỗng sẽ gây `IndexOutOfBoundsException`.

Đây là khác biệt giữa một **hợp đồng API** và chỉ nhìn vào chữ ký generic: PECS mô tả kiểu an toàn, nhưng không nói hết các tiền điều kiện về kích thước hoặc khả năng sửa collection.

## 7. Khi nào *không* nên dùng wildcard?

PECS là nguyên tắc chọn wildcard **khi phù hợp**, không phải yêu cầu mọi chữ ký generic đều phải chứa `extends` hoặc `super`.

### 7.1. Đọc và ghi cùng chính xác một kiểu

Nếu thuật toán cần lấy phần tử từ một list và ghi lại vào **chính list đó**, việc giữ cùng một type parameter `T` thường rõ ràng hơn:

```java
static <T> void duplicateFirst(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.add(first);
    }
}
```

`List<T>` đảm bảo cùng một `T` dùng cho cả `get` và `add`. Dù chỉ cần làm việc với một list, phương thức có thể được gọi với `List<String>`, `List<Integer>` hoặc `List<Dog>` mà không phải ép kiểu.

Tương tự, một phương thức **cần liên kết kiểu đầu vào với kết quả** nên khai báo type parameter:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

Integer n = first(List.of(10, 20));
String s = first(List.of("A", "B"));
```

Nếu chỉ viết `Object first(List<?> values)`, thông tin “kiểu phần tử đầu vào cũng là kiểu trả về” sẽ bị mất tại call site.

### 7.2. Khi wildcard khiến quan hệ kiểu khó đọc

Một type parameter đặt tên (`T`, `E`, `K`, `V`, `R`) là lựa chọn tốt khi **một kiểu xuất hiện ở nhiều vị trí có quan hệ với nhau**: input, output, callback hoặc nhiều tham số cần cùng kiểu.

Ngược lại, nếu một tham số là nguồn độc lập chỉ cần đọc, `List<? extends Number>` thường dễ hiểu hơn phương thức chỉ để thực hiện cùng việc đó với `<T extends Number>` mà không sử dụng `T` ở chỗ nào khác.

## 8. Wildcard trong các API generic hiện đại

Nguyên lý PECS xuất hiện rộng rãi trong Java SE 27, không chỉ ở `Collection`.

### 8.1. `List.sort(Comparator<? super E>)`

`List<E>` có phương thức:

```java
void sort(Comparator<? super E> comparator);
```

Một `Comparator<Animal>` biết cách so sánh `Animal` cũng đủ khả năng so sánh `Dog`:

```java
Comparator<Animal> byName =
        Comparator.comparing(a -> a.name);

List<Dog> dogs = new ArrayList<>(
        List.of(new Dog("Milo"), new Dog("Ace")));

dogs.sort(byName);
```

Comparator là **consumer** đối với mỗi `Dog` được truyền vào phương thức so sánh, vì vậy `? super Dog` là lựa chọn hợp lý. Nếu chữ ký cố định `Comparator<Dog>`, ta sẽ không dùng được một comparator tổng quát có khả năng so sánh mọi `Animal`.

### 8.2. `Consumer<? super T>` và `Predicate<? super T>`

Các callback nhận giá trị kiểu `T` từ API thường dùng lower-bounded wildcard:

```java
Consumer<Number> showNumber =
        number -> System.out.println(number.doubleValue());

List<Integer> integers = List.of(1, 2, 3);
integers.forEach(showNumber);
```

`Iterable<T>.forEach` nhận `Consumer<? super T>`. Một consumer xử lý `Number` tất nhiên có thể nhận `Integer`.

`Stream<T>.filter` nhận `Predicate<? super T>`. Predicate kiểm tra `Number` cũng có thể dùng để lọc stream của `Integer`:

```java
Predicate<Number> positive = n -> n.doubleValue() > 0;
List<Integer> positives = List.of(-1, 0, 2, 4)
        .stream()
        .filter(positive)
        .toList();
```

`Stream.toList()` trả về list không sửa được; đừng dựa vào khả năng thêm phần tử của kết quả.

### 8.3. `Stream.map(Function<? super T, ? extends R>)`

Chữ ký của `map` thể hiện **hai chiều phương sai** trên cùng một callback:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

- `Function` **nhận** mỗi phần tử `T` từ stream, nên kiểu đầu vào là `? super T`.
- `Function` **tạo ra** kết quả được xem như `R`, nên kiểu đầu ra là `? extends R`.

Ví dụ:

```java
Function<Number, String> label =
        number -> "value=" + number;

Stream<CharSequence> texts =
        List.of(1, 2, 3).stream().map(label);

System.out.println(texts.toList());
// [value=1, value=2, value=3]
```

Ở đây, stream nguồn chứa `Integer`; function chấp nhận `Number` (supertype của `Integer`) và trả `String` (subtype của `CharSequence`). Cả hai phía cùng hợp lệ nhờ wildcard.

### 8.4. `Map`, `Optional` và các kiểu generic khác

Tư duy producer/consumer không chỉ áp dụng cho list:

```java
Map<String, ? extends Number> metrics = Map.of(
        "requests", 42,
        "errors", 2);

Number requests = metrics.get("requests");
// metrics.put("new", 3); // Không được phép thêm Number tùy ý
```

Nếu cần điền `Integer` vào một map, một chữ ký kiểu `Map<String, ? super Integer>` có thể phù hợp tùy API. Tuy vậy, với map còn phải xét **khả năng ghi key** và **khả năng đọc value** độc lập. Wildcard chỉ ở vị trí value không thay đổi ràng buộc của key.

Một `Optional<? extends Number>` phù hợp khi chỉ cần lấy giá trị số không biết subtype cụ thể. Không áp dụng PECS máy móc thành “dùng `super` nếu muốn thay đổi Optional” vì `Optional` là container không có các thao tác thêm/sửa phần tử kiểu `List.add`.

## 9. Wildcard capture: khi cần giúp compiler “đặt tên” kiểu chưa biết

`List<?>` không phải list có kiểu phần tử `Object`. Compiler coi dấu `?` là một kiểu chưa biết nhưng **cố định đối với một vị trí capture**. Việc chuyển wildcard thành type variable nội bộ được gọi là **capture conversion** (JLS `5.1.10).

Xét yêu cầu hoán đổi hai phần tử đầu của list bất kỳ. Trực tiếp cố ghi hai giá trị với `List<?>` có thể gây lỗi liên quan đến `capture of ?`:

```java
// Ví dụ về hướng viết không phù hợp với wildcard:
// static void swapFirstTwo(List<?> values) {
//     values.set(0, values.get(1)); // Lỗi capture trong ngữ cảnh này
// }
```

Giải pháp là **generic helper**: nắm giữ kiểu capture bằng một tên `T` và dùng nó nhất quán trong thân phương thức.

```java
static void swapFirstTwo(List<?> values) {
    if (values.size() >= 2) {
        swapFirstTwoCaptured(values);
    }
}

private static <T> void swapFirstTwoCaptured(List<T> values) {
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

Khi gọi `swapFirstTwoCaptured(values)`, compiler có thể **capture** kiểu phần tử thực của đối số và suy ra `T` cho lần gọi đó. Nhờ vậy, mọi lệnh `get` và `set` trong helper dùng cùng `T`, không cần unchecked cast.

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
swapFirstTwo(names);
System.out.println(names); // [Binh, An]
```

List phải hỗ trợ `set` mới thực hiện được việc hoán đổi. Java cũng cung cấp `Collections.swap(List<?> list, int i, int j)` cho công việc này; ví dụ helper ở đây nhằm giải thích cơ chế type inference/capture, không phải thay thế API chuẩn.

## 10. Phương sai trong Java: bất biến, đồng biến và nghịch biến

Ba thuật ngữ thường gặp:

| Thuật ngữ | Quan hệ mong muốn khi `Dog <: Animal` | Hình thức trong Java |
| --- | --- | --- |
| **Bất biến (invariance)** | `List<Dog>` không là subtype của `List<Animal>` | `List<T>` với đối số kiểu cụ thể |
| **Đồng biến (covariance)** | Có thể đọc `Dog` qua góc nhìn biết chúng đều là `Animal` | `List<? extends Animal>` |
| **Nghịch biến (contravariance)** | Đích xử lý `Animal` có thể nhận giá trị `Dog` | `List<? super Dog>` hoặc `Consumer<? super Dog>` |

Nói chính xác, wildcard trong Java cho phép **use-site variance**: người sử dụng generic type chọn ràng buộc ở vị trí tham số. Java không viết declaration-site variance bằng ký hiệu tương tự `out T` hay `in T` trên khai báo type parameter của class.

### 10.1. Mảng Java không tuân theo cùng quy tắc generic

Array có quan hệ subtype mang tính covariance:

```java
Integer[] integers = new Integer[1];
Number[] numbers = integers; // Hợp lệ khi biên dịch

// numbers[0] = Double.valueOf(3.14);
// Nếu chạy: ArrayStoreException vì mảng thực sự là Integer[]
```

Việc mảng cho phép gán như trên phải được bảo vệ bằng **runtime store check**. Ngược lại, Java generics thường ngăn phép gán không an toàn tại compile time, ví dụ `List<Number> numbers = new ArrayList<Integer>()` không hợp lệ.

Không suy luận từ covariance của array rằng `List<T>` cũng covariance. Đây là hai cơ chế type system khác nhau.

### 10.2. Wildcard không có nghĩa tự động chuyển kiểu đối tượng

`List<? extends Animal>` không tạo bản sao của một `List<Dog>` và không chuyển tất cả phần tử thành instance của `Animal`. Nó chỉ là **kiểu tham chiếu** cho phép mã đọc các phần tử với mức đảm bảo kiểu `Animal`.

Tương tự, `List<? super Dog>` không làm list đang giữ `Dog` thay đổi cách lưu trữ. Những giới hạn ghi/đọc đến từ Java compiler và chữ ký generic.

## 11. Cận của type parameter và cận của wildcard khác nhau

Hai cú pháp dùng từ `extends` nhưng có mục đích khác nhau:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

Ở đây, `T` là **type parameter có tên**. Mã gọi có thể nhận lại chính kiểu được suy ra:

```java
Integer result = identity(Integer.valueOf(7));
```

Trong khi đó:

```java
static Number firstNumber(List<? extends Number> values) {
    return values.get(0);
}
```

Ký hiệu `? extends Number` là **wildcard argument**, không đặt tên cho một type parameter mà các vị trí khác trong method có thể dùng lại.

Khi cần bảo toàn subtype cụ thể, có thể khai báo:

```java
static <T extends Number> T firstTyped(List<T> values) {
    return values.get(0);
}

Integer firstInteger = firstTyped(List.of(1, 2));
Double firstDouble = firstTyped(List.of(1.5, 2.5));
```

Quy tắc thiết kế: **wildcard** cho quan hệ kiểu một chiều và độc lập; **named type parameter** cho những ràng buộc cần liên kết nhiều vị trí trong cùng một API.

## 12. Giới hạn của erasure và vì sao không dùng raw types

Thông tin type argument như `String`, `Dog` hoặc `Integer` phần lớn được compiler kiểm tra rồi bị **type erasure** trong biểu diễn runtime của Java. Vì thế:

```java
Object value = List.of("Java");

if (value instanceof List<?>) {
    System.out.println("This is a List");
}

// if (value instanceof List<String>) { }
// Lỗi: không thể kiểm tra đầy đủ type argument String tại runtime
```

`List<?>` là kiểu reifiable cho phép `instanceof`, nhưng không chứng minh phần tử có kiểu `String` hay `Integer`. Nếu dữ liệu không đáng tin cậy, cần kiểm tra từng phần tử hoặc dùng abstraction có hợp đồng rõ.

### 12.1. Không thay wildcard bằng raw type

Kiểu `List` không có đối số kiểu là **raw type**, được giữ để tương thích với code cũ. Raw type có thể tạo unchecked warning và phá an toàn kiểu:

```java
// Chỉ minh họa điều KHÔNG nên làm:
List<String> names = new ArrayList<>();
// List raw = names;
// raw.add(123);         // Unchecked warning và gây heap pollution
// String text = names.get(0); // Có thể ném ClassCastException
```

Với API hiện đại Java 27, nếu không cần biết kiểu phần tử, dùng `List<?>` thay vì raw `List`. Nếu cần đọc số, dùng `List<? extends Number>`. Nếu cần ghi số `Integer`, dùng `List<? super Integer>`. Không che unchecked warning bằng `@SuppressWarnings("unchecked")` nếu chưa chứng minh việc cast an toàn.

### 12.2. Wildcard không phải cú pháp tạo đối tượng

Ta có thể khai báo:

```java
List<? extends Number> values = new ArrayList<Integer>();
```

Nhưng không thể tạo `new ArrayList<? extends Number>()`. Wildcard dùng trong **type arguments ở chỗ mô tả ràng buộc**, không phải một kiểu cụ thể để khởi tạo. Khi tạo object, chọn kiểu phần tử cụ thể hoặc dùng diamond inference:

```java
List<Number> values = new ArrayList<>();
```

### 12.3. Generic type arguments là kiểu tham chiếu

Không thể viết `List<int>` vì `int` là primitive. Hãy dùng `List<Integer>` hoặc một abstraction dành cho primitive nếu bài toán chủ yếu xử lý số:

```java
List<Integer> ids = List.of(1, 2, 3);
int sum = ids.stream().mapToInt(Integer::intValue).sum();
```

`mapToInt` trả về `IntStream` nên tránh biểu diễn mỗi phép toán bằng stream generic của wrapper.

## 13. Thiết kế API: vài quyết định thực tế

### 13.1. Chọn interface hẹp nhất cho nhiệm vụ

Nếu chỉ cần duyệt các giá trị `Number`, có thể nhận `Iterable<? extends Number>` thay vì `List<? extends Number>`, bởi phương thức không cần truy cập theo chỉ số.

```java
static double sum(Iterable<? extends Number> values) {
    double result = 0;
    for (Number n : values) {
        result += n.doubleValue();
    }
    return result;
}
```

Nếu phương thức cần sắp xếp hoặc sửa phần tử theo chỉ số, một `List<T>` mới là abstraction thích hợp. Việc chọn đúng interface có thể quan trọng không kém việc chọn đúng wildcard.

### 13.2. Đừng biến mọi tham số thành `<?>`

Chữ ký `void process(List<?> values)` linh hoạt nhưng không nói rõ phần tử phải có thuộc tính gì. Nếu thuật toán cần `doubleValue()`, hãy dùng `? extends Number`. Nếu cần gọi `compareTo`, cân nhắc `Comparable` và cận type parameter thích hợp.

Hợp đồng type system nên thể hiện yêu cầu tối thiểu nhưng đủ mạnh của thuật toán.

### 13.3. Đừng trả về wildcard khi người dùng cần kiểu xác định

Một API trả `List<? extends Animal>` có thể làm người gọi khó thêm phần tử hoặc khó duy trì thông tin subtype. Nếu phương thức **sở hữu** danh sách và biết rõ kiểu kết quả, nên cân nhắc trả `List<Animal>`, `List<Dog>` hoặc `List<T>` (khi cần bảo toàn `T`), thay vì dùng wildcard không cần thiết.

Wildcard thường hữu ích nhất ở **tham số đầu vào**. Tuy nhiên, cũng có API hợp lý trả wildcard; phải dựa vào hợp đồng cụ thể, không áp dụng lệnh cấm tuyệt đối.

### 13.4. Hai tham số cùng phải có quan hệ kiểu nào?

Nếu nguồn tạo `T` và đích nhận `T`, dùng cả hai chiều PECS:

```java
static <T> void transfer(
        Collection<? super T> destination,
        Iterable<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Nếu yêu cầu chính xác cùng một `T` ở cả hai nơi, không phải là “nguồn/đích linh hoạt”, dùng `List<T>` cho những tham số cần ràng buộc tương đương. Sự khác nhau nằm ở chính **hợp đồng API**, không phải cố làm chữ ký càng nhiều wildcard càng tốt.

## 14. Ví dụ tổng hợp chạy được với Java 27

Lưu code sau vào `Demo.java`. Ví dụ có đủ một nguồn producer, một đích consumer, một comparator contravariant và một callback `Function` dùng cả hai chiều wildcard.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class Demo {
    static class Animal {
        final String name;

        Animal(String name) {
            this.name = name;
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
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
        List<Integer> source = List.of(10, 20, 30);
        List<Number> destination = new ArrayList<>();
        appendAll(destination, source);
        System.out.println(destination); // [10, 20, 30]

        List<Dog> dogs = new ArrayList<>(
                List.of(new Dog("Milo"), new Dog("Ace")));
        Comparator<Animal> byName =
                Comparator.comparing(a -> a.name);
        dogs.sort(byName);
        System.out.println(
                dogs.stream().map(d -> d.name).toList()); // [Ace, Milo]

        Function<Number, String> label = n -> "id=" + n;
        Stream<CharSequence> labels = source.stream().map(label);
        System.out.println(labels.toList());
        // [id=10, id=20, id=30]
    }
}
```

Biên dịch và chạy:

```shell
javac Demo.java
java Demo
```

Không cần `--enable-preview`. Java wildcard, PECS và những API liên quan ở đây đều là các thành phần ổn định của Java SE 27.

## 15. Các lỗi phổ biến và cách sửa

| Tình huống | Vấn đề | Cách tiếp cận |
| --- | --- | --- |
| Gán `List<Dog>` cho `List<Animal>` | Generic invariant | Dùng `List<? extends Animal>` nếu chỉ cần đọc |
| Dùng `List<Object>` để nhận mọi loại list | Không nhận được `List<String>` vì invariance | Dùng `List<?>` khi không cần kiểu cụ thể |
| Thêm `Integer` vào `List<? extends Number>` | Không biết subtype phần tử thực | Dùng `List<Number>` nếu sở hữu list, hoặc `? super Integer` cho đích |
| Đọc `Integer` từ `List<? super Integer>` | Chỉ bảo đảm phần tử là `Object` | Đọc thành `Object` hoặc thiết kế lại hợp đồng |
| Coi `? extends T` là immutable | Wildcard không ngăn xóa/đổi cấu trúc qua mọi API | Dùng collection không sửa được khi cần immutability |
| Truyền list rỗng làm đích `Collections.copy` | Đích chưa có đủ vị trí | Chuẩn bị list đích đủ phần tử hoặc dùng API append |
| Dùng wildcard khi cần liên kết kiểu trả về | Mất thông tin subtype | Dùng named type parameter `<T>` |
| Không xử lý lỗi `capture of ?` | Compiler chưa thể liên hệ kiểu chưa biết | Dùng generic helper có type parameter `T` |
| Ép raw type để gọi API | Unchecked warning, heap pollution | Dùng bounded wildcard hoặc generic method đúng nghĩa |
| Nhầm `List<?>` với `List<Object>` | Hai type có khả năng ghi khác nhau | Chọn theo vai trò mã gọi |
| Nhầm array covariance với generic | Array có runtime store check khác generic | Không suy từ `Number[]` sang `List<Number>` |
| Viết `new ArrayList<?>()` | Wildcard không phải type argument khởi tạo hợp lệ | Dùng `new ArrayList<>()` |
| Viết `List<int>` | Generic type arguments cần kiểu tham chiếu | Dùng `List<Integer>` hoặc `IntStream` |

## 16. Checklist trước khi công bố API generic

1. **Tham số này là nguồn hay đích dữ liệu?** Xác định vai trò tại đúng vị trí sử dụng.
2. **Nếu chỉ đọc như `T`, `? extends T` có diễn đạt tốt hơn `T` không?**
3. **Nếu chỉ nhận `T`, `? super T` có cho phép nhiều loại đích hợp lệ hơn không?**
4. **Nếu không cần kiểu phần tử, có dùng `<?>` thay raw type không?**
5. **Nếu cần giữ quan hệ kiểu giữa nhiều tham số và kết quả, có nên dùng `<T>`?**
6. **Giao diện tham số có quá cụ thể không?** Có thật sự cần `List`, hay `Iterable`/`Collection` đã đủ?
7. **Khả năng sửa dữ liệu của đối tượng đã được quy định chưa?** Wildcard không bảo đảm collection mutable hay immutable.
8. **Có nguy cơ alias hoặc concurrent modification khi vừa đọc vừa ghi không?** Kiểu an toàn không tự giải quyết cấu trúc dữ liệu và phối hợp luồng.
9. **Có unchecked cast/raw type không cần thiết không?** Ưu tiên type-safe API và generic helper.
10. **Các trường hợp cần lỗi có rõ ràng không?** Ví dụ kích thước đích của `Collections.copy` hoặc list không hỗ trợ `set`.

## 17. Tổng kết

Java generic types mặc định **bất biến**: `List<Dog>` không phải subtype của `List<Animal>`. Wildcard mở rộng khả năng sử dụng API mà vẫn bảo vệ an toàn kiểu lúc biên dịch:

- `<?>`: không biết kiểu phần tử, thích hợp khi không cần ràng buộc với kiểu cụ thể.
- `? extends T`: đọc các phần tử an toàn như `T`; nguồn **producer**.
- `? super T`: ghi các giá trị kiểu `T` an toàn; đích **consumer**.
- `<T>`: đặt tên kiểu khi cần liên kết nhiều vị trí, đặc biệt khi phải vừa đọc vừa ghi cùng kiểu.

**PECS — Producer Extends, Consumer Super** không chỉ là một mẹo ghi nhớ: nó giúp đưa những ràng buộc tối thiểu và đúng hướng vào chữ ký phương thức. Các API như `Collections.copy`, `List.sort`, `Iterable.forEach` và `Stream.map` cho thấy cách áp dụng tư duy này trong thư viện Java 27.

Hãy phân biệt **an toàn kiểu**, **quyền sửa collection** và **tính bất biến dữ liệu**: một chữ ký generic đúng chưa đảm bảo collection hỗ trợ sửa, không tránh được alias/concurrency và cũng không thay thế việc xác thực dữ liệu nghiệp vụ. Một API tốt kết hợp wildcard hợp lý, named type parameters khi cần và hợp đồng rõ ràng về hành vi.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §4.5 Parameterized Types và §4.5.1 Wildcards](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.5.1) — cận trên, cận dưới, wildcard type arguments và quan hệ containment.
- [Java Language Specification, Java SE 27 — §4.10 Subtyping](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.10) — subtype trong Java, gồm parameterized types và arrays.
- [Java Language Specification, Java SE 27 — §5.1.10 Capture Conversion](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.1.10) — quy tắc capture wildcard và generic helper.
- [Collections (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html) — `copy`, `swap`, `addAll`, các chữ ký dùng wildcard.
- [List (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html) — `sort(Comparator<? super E>)`, `add`, `set` và hợp đồng list.
- [Iterable (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Iterable.html) — `forEach(Consumer<? super T>)`.
- [Stream (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html) — `filter(Predicate<? super T>)` và `map(Function<? super T, ? extends R>)`.
