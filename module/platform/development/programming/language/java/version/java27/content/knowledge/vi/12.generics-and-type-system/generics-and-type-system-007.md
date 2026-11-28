# Thiết kế generic API và kiểm soát varargs với SafeVarargs

Trong Java 27, **generics** cho phép lớp, interface và phương thức diễn đạt quan hệ kiểu dữ liệu ngay trong chữ ký API. Mục tiêu không chỉ là giảm ép kiểu: một generic API tốt giúp trình biên dịch ngăn lỗi, cho phép dùng lại logic với nhiều kiểu và mô tả chính xác thứ mà người gọi được phép đọc hoặc ghi.

Khi kết hợp generics với **varargs** (tham số có số lượng đối số thay đổi), xuất hiện một ranh giới quan trọng: generic thường được kiểm tra tại thời điểm biên dịch và trải qua **type erasure**, trong khi varargs được triển khai thông qua **mảng**, vốn có kiểm tra kiểu phần tử ở thời điểm chạy. Sự khác biệt này có thể dẫn tới **heap pollution** và cảnh báo **unchecked**.

Annotation **@SafeVarargs** được dùng khi lập trình viên có thể bảo đảm một phương thức hoặc constructor varargs **không thực hiện thao tác không an toàn** với đối số varargs. Nó là một cam kết về tính an toàn kiểu, không phải công cụ tự động sửa một đoạn mã nguy hiểm.

Bài này tập trung vào những cơ chế và API vẫn đang được sử dụng trong Java 27; các ví dụ có thể dùng trong mã Java hiện đại mà không cần API lỗi thời.

## 1. Generic API là gì?

Một API generic dùng **type parameter** thay cho việc cố định một kiểu dữ liệu cụ thể. Ví dụ, một hộp chứa một giá trị có thể mang kiểu **T**:

~~~java
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T value() {
        return value;
    }
}
~~~

Người dùng khai báo kiểu cụ thể tại điểm sử dụng:

~~~java
Box<String> title = new Box<>("Java 27");
Box<Integer> count = new Box<>(27);

String name = title.value();
int number = count.value();
~~~

Ở đây:

- **Box<T>** là một generic class, còn **T** là type parameter.
- **Box<String>** và **Box<Integer>** là các parameterized type.
- Dấu **<>** khi tạo đối tượng là *diamond operator*, cho phép trình biên dịch suy luận đối số kiểu.
- Method **value()** trả về đúng kiểu được chỉ định, không cần ép kiểu thủ công ở phía người dùng.

So với API dùng **Object** cho mọi dữ liệu, generic API giúp thể hiện ràng buộc tại thời điểm biên dịch:

~~~java
Box<String> box = new Box<>("text");

// Integer value = box.value(); // Lỗi biên dịch: String không phải Integer.
~~~

Generics **không** làm cho kiểu của các đối tượng trở nên hoàn toàn khả dụng ở thời điểm chạy. Java vẫn dùng type erasure cho phần lớn thông tin tham số kiểu; hệ quả được trình bày ở phần sau.

## 2. Ưu tiên phương thức generic khi quan hệ kiểu chỉ thuộc một thao tác

Không phải mọi thao tác generic đều cần một generic class. Nếu type parameter chỉ liên quan tới một method, khai báo generic method giúp API nhỏ và chính xác hơn.

~~~java
public final class Pairs {
    private Pairs() {}

    public static <T> boolean sameReference(T first, T second) {
        return first == second;
    }
}
~~~

Dấu **<T>** nằm **trước kiểu trả về** và khai báo type parameter của method. Tuy nhiên, phương thức **sameReference()** so sánh danh tính tham chiếu, không phải so sánh nội dung. Với mục tiêu so sánh giá trị của hai đối tượng, nên dùng **Objects.equals()**:

~~~java
import java.util.Objects;

public final class Equality {
    private Equality() {}

    public static <T> boolean sameValue(T first, T second) {
        return Objects.equals(first, second);
    }
}
~~~

Trong ví dụ này, type parameter **T** không bổ sung nhiều ràng buộc cần thiết vì **Objects.equals(Object, Object)** đã đáp ứng trực tiếp công việc. Đây là một bài học thiết kế quan trọng: **đừng đưa generic vào chỉ để có cú pháp generic**.

Ngược lại, nếu kiểu đầu vào và đầu ra cần liên hệ với nhau, type parameter có giá trị rõ rệt:

~~~java
import java.util.Objects;
import java.util.function.UnaryOperator;

public final class Transforms {
    private Transforms() {}

    public static <T> T applyTwice(T value, UnaryOperator<T> operator) {
        Objects.requireNonNull(operator, "operator");
        return operator.apply(operator.apply(value));
    }
}
~~~

Ví dụ:

~~~java
String result = Transforms.applyTwice("a", text -> text + "!");

System.out.println(result); // a!!
~~~

Chữ ký **<T> T applyTwice(T, UnaryOperator<T>)** bảo đảm đầu vào, toán tử và kết quả có kiểu tương thích. Đó là ràng buộc thật sự mà generic API mang lại.

## 3. Tính bất biến kiểu (invariance) của generics

Một nhầm lẫn phổ biến: nếu **Dog extends Animal**, liệu **List<Dog>** có phải kiểu con của **List<Animal>** không?

Câu trả lời là **không**. Generic type trong Java nhìn chung là **invariant** theo đối số kiểu.

~~~java
class Animal {}
class Dog extends Animal {}

List<Dog> dogs = new java.util.ArrayList<>();

// List<Animal> animals = dogs; // Không hợp lệ.
~~~

Nếu phép gán này được cho phép, mã bên ngoài có thể thêm một đối tượng **Animal** không phải **Dog** vào danh sách vốn chỉ dành cho **Dog**:

~~~java
// Giả sử được phép, đây sẽ là lỗ hổng kiểu:
// List<Animal> animals = dogs;
// animals.add(new Animal());
// Dog firstDog = dogs.get(0);
~~~

Generics ngăn lỗi như vậy ngay ở thời điểm biên dịch.

### Wildcard cho khả năng đọc

Nếu API chỉ cần **đọc** các đối tượng như **Animal**, có thể nhận danh sách của những kiểu con:

~~~java
import java.util.List;

static void printAnimals(List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.getClass().getSimpleName());
    }
}
~~~

Phương thức chấp nhận **List<Animal>**, **List<Dog>** và các danh sách của lớp con khác. Tuy nhiên, không thể tùy ý thêm một **Animal** vào **List<? extends Animal>** vì danh sách thực tế có thể chỉ chứa **Dog**.

### Wildcard cho khả năng ghi

Nếu API cần **ghi** các đối tượng **Dog**, dùng lower-bounded wildcard:

~~~java
import java.util.Collection;

static void addDog(Collection<? super Dog> destination) {
    destination.add(new Dog());
}
~~~

**Collection<? super Dog>** có thể là **Collection<Dog>**, **Collection<Animal>** hoặc **Collection<Object>**. Mã có thể thêm **Dog**, nhưng khi đọc lại một phần tử, chỉ có thể chắc chắn kiểu tối thiểu là **Object**.

### PECS: producer extends, consumer super

Nguyên tắc **PECS** tóm tắt ý định:

- **Producer extends:** nguồn dữ liệu chỉ cần cho phép đọc các giá trị kiểu **T** thì dùng **? extends T**.
- **Consumer super:** đích dữ liệu cần chấp nhận các giá trị kiểu **T** thì dùng **? super T**.

Ví dụ một phương thức chuyển phần tử:

~~~java
import java.util.Collection;

static <T> void appendAll(
        Collection<? super T> destination,
        Iterable<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

Sử dụng:

~~~java
List<Dog> dogs = List.of(new Dog(), new Dog());
List<Animal> animals = new java.util.ArrayList<>();

appendAll(animals, dogs);

System.out.println(animals.size()); // 2
~~~

Hợp đồng **appendAll()** mở rộng tập dữ liệu có thể truyền vào mà vẫn giữ an toàn kiểu. Không cần ép kiểu hoặc sử dụng raw type.

## 4. Chọn wildcard hay type parameter?

**Wildcard** diễn đạt một quan hệ kiểu có thể thay đổi ở một vị trí. **Type parameter** thường hữu ích khi cần liên kết nhiều vị trí trong cùng chữ ký.

Ví dụ, phương thức chỉ đọc một collection:

~~~java
static void displayAll(Iterable<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

Không cần viết **<T> void displayAll(Iterable<T>)** chỉ để sử dụng T đúng một lần nếu không có lý do bổ sung về hợp đồng.

Ngược lại, một generic method có thể kết nối kiểu của nguồn, đích và kết quả:

~~~java
import java.util.Collection;
import java.util.List;

static <T> List<T> copyIntoList(Collection<? extends T> source) {
    return List.copyOf(source);
}
~~~

Ở đây, **T** mô tả kiểu phần tử của danh sách trả về, còn **? extends T** cho phép nhận collection chứa kiểu con phù hợp. **List.copyOf()** trả về danh sách không cho phép sửa và không chấp nhận phần tử null.

### Bounded type parameter

Khi logic cần khả năng cụ thể từ đối tượng, hãy khai báo giới hạn kiểu:

~~~java
static <T extends Comparable<? super T>> T larger(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

Giới hạn **T extends Comparable<? super T>** yêu cầu **T** có thể được so sánh với các giá trị kiểu T. Dùng **? super T** trong giới hạn giúp chấp nhận những kiểu triển khai **Comparable** với một kiểu cha phù hợp.

~~~java
String greater = larger("apple", "banana");

System.out.println(greater); // banana
~~~

Nếu dùng **Comparator<? super T>** do người gọi truyền vào, API còn có thể kiểm soát tiêu chí so sánh mà không yêu cầu mọi kiểu triển khai **Comparable**.

## 5. Thiết kế chữ ký dễ hiểu và khả năng suy luận kiểu

Generic API tốt nên để người dùng gọi tự nhiên mà không cần ghi type witness hoặc ép kiểu phức tạp.

Ví dụ:

~~~java
static <T> List<T> singleton(T element) {
    return List.of(element);
}

List<String> words = singleton("Java");
List<Integer> numbers = singleton(27);
~~~

Trình biên dịch suy luận T từ đối số, kiểu đích và ngữ cảnh gọi.

### Tránh raw type

Raw type bỏ thông tin đối số kiểu và làm mất một phần khả năng kiểm tra của trình biên dịch:

~~~java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList<String>();

raw.add(42); // Thao tác qua raw type có cảnh báo unchecked.
~~~

Đừng dùng raw type chỉ để tránh lỗi tương thích generic. Nếu thật sự không biết loại phần tử và chỉ cần đọc, **List<?>** thường phù hợp hơn:

~~~java
List<?> unknown = List.of("A", "B");

Object first = unknown.get(0);
// unknown.add("C"); // Không thể thêm giá trị tùy ý.
~~~

**List<?>** biểu diễn danh sách thuộc kiểu phần tử chưa biết nhưng vẫn giữ một mức an toàn kiểu; nó không phải là bí danh của **List<Object>**.

### Đừng buộc người gọi truyền concrete collection

Nếu chỉ duyệt dữ liệu, chữ ký **Iterable<? extends T>** có thể phù hợp hơn **ArrayList<T>**. Nếu cần truy cập phần tử theo vị trí hoặc giữ thứ tự, **List<? extends T>** có thể cần thiết.

Thiết kế nên phản ánh **khả năng thật sự cần dùng**, không phải chi tiết triển khai hiện tại.

## 6. Vì sao generics và mảng có quy tắc khác nhau?

Mảng Java có kiểu thành phần tại thời điểm chạy và cho phép quan hệ subtype theo kiểu phần tử tham chiếu. Cơ chế này có kiểm tra runtime:

~~~java
Object[] objects = new String[1];

// objects[0] = Integer.valueOf(42);
// Nếu thực thi, thao tác trên sẽ ném ArrayStoreException.
~~~

Biến **objects** khai báo kiểu **Object[]**, nhưng mảng thực tế có kiểu **String[]**. JVM kiểm tra kiểu phần tử khi ghi để ngăn một **Integer** được đưa vào mảng String.

Trong khi đó, các kiểu generic như **List<String>** và **List<Integer>** không có những mảng runtime riêng biệt theo từng đối số kiểu. Sau type erasure, thông tin đối số kiểu không còn khả dụng theo cách cho phép JVM kiểm tra trực tiếp phần tử như với **String[]**.

Do đó, Java không cho phép trực tiếp tạo mảng có kiểu thành phần generic không reifiable:

~~~java
// List<String>[] groups = new List<String>[3];
// Lỗi biên dịch: generic array creation.
~~~

Nếu cần tập hợp danh sách, thường có thể dùng một **List<List<String>>** thay vì generic array:

~~~java
List<List<String>> groups = new java.util.ArrayList<>();

groups.add(List.of("A", "B"));
groups.add(List.of("C"));
~~~

Đây là cách biểu diễn đơn giản hơn khi không có yêu cầu đặc biệt phải dùng mảng.

## 7. Reifiable và non-reifiable type

Một kiểu **reifiable** là kiểu có đủ thông tin để JVM biểu diễn và kiểm tra ở thời điểm chạy theo các quy tắc của Java.

Ví dụ thường gặp:

- **String** và **String[]** là kiểu reifiable.
- **int** và **int[]** là kiểu reifiable.
- **List<?>** là parameterized type reifiable vì mọi đối số kiểu đều là wildcard không giới hạn.
- **List<String>**, **List<Integer>** và type variable **T** nói chung **không reifiable**.

Đối số kiểu của **List<String>** không được lưu như một kiểu runtime riêng mà JVM có thể kiểm tra qua **instanceof List<String>**.

~~~java
Object value = List.of("A");

if (value instanceof List<?>) {
    System.out.println("It is a list");
}

// if (value instanceof List<String>) { ... }
// Không hợp lệ: không thể kiểm tra trực tiếp List<String> theo runtime.
~~~

Ranh giới giữa reifiable và non-reifiable là nguyên nhân chính khiến **generic varargs** cần được xem xét cẩn thận.

## 8. Varargs thực chất là một tham số mảng

Từ khóa varargs trong khai báo dùng dấu **...**:

~~~java
static int sum(int... numbers) {
    int total = 0;

    for (int number : numbers) {
        total += number;
    }

    return total;
}
~~~

Người gọi có thể truyền số lượng đối số thay đổi:

~~~java
System.out.println(sum());         // 0
System.out.println(sum(1, 2, 3));  // 6

int[] values = {4, 5};
System.out.println(sum(values));   // 9
~~~

Về mặt triển khai và chữ ký, tham số **int... numbers** được xử lý dưới dạng **int[] numbers**. Ở lời gọi varargs với các đối số riêng lẻ, trình biên dịch sắp xếp chúng vào mảng; nếu đã có mảng tương thích, người gọi có thể truyền trực tiếp mảng đó.

Một quy tắc cú pháp quan trọng: một method chỉ được có **tối đa một tham số varargs**, và tham số này phải **đứng cuối danh sách tham số**.

~~~java
static void record(String category, String... entries) {
    System.out.println(category + ": " + entries.length);
}
~~~

Các varargs kiểu **String...**, **int...** thường không có vấn đề an toàn kiểu đặc thù của generic varargs vì kiểu thành phần của chúng là reifiable.

## 9. Generic varargs và cảnh báo của trình biên dịch

Kết hợp varargs với parameterized type:

~~~java
import java.util.List;

static void printGroups(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
~~~

Kiểu biểu kiến của **groups** là **List<String>[]**, trong khi kiểu phần tử generic **List<String>** không reifiable. JVM không thể trực tiếp kiểm tra từng danh sách trong mảng có thật sự là **List<String>** hay không.

Vì vậy, trình biên dịch có thể cảnh báo:

- **Possible heap pollution from parameterized vararg type ...** tại vị trí khai báo method.
- **Unchecked generic array creation for varargs parameter ...** tại điểm gọi.

Thông điệp chính xác phụ thuộc vào trình biên dịch và cấu hình cảnh báo. Cảnh báo không khẳng định mọi lời gọi đều đang gây lỗi; nó cho biết an toàn kiểu không được bảo đảm tự động trong mọi cách triển khai.

Ví dụ:

~~~java
printGroups(List.of("red", "blue"), List.of("green"));
~~~

Bản thân việc duyệt và in các phần tử có thể an toàn. Vấn đề là **method nhận được một mảng varargs mà runtime không thể xác nhận đầy đủ kiểu generic của mỗi phần tử**, và phần thân method có khả năng làm điều nguy hiểm với nó.

## 10. Heap pollution là gì?

**Heap pollution** xuất hiện khi một biến hoặc cấu trúc lưu trữ có kiểu tham số hóa chứa một giá trị không phù hợp với kiểu mà mã nguồn tin tưởng.

Ví dụ sau cố ý minh họa thao tác **không an toàn**, không nên dùng làm mẫu triển khai API:

~~~java
import java.util.List;

class UnsafeVarargsDemo {
    static void corrupt(List<String>... groups) {
        Object[] array = groups;

        // Thay một List<String> bằng List<Integer>.
        // Runtime chỉ biết đây là mảng List[].
        array[0] = List.of(42);

        // Biên dịch dựa trên lời hứa groups[0] là List<String>.
        String text = groups[0].get(0);
        System.out.println(text);
    }

    public static void main(String[] args) {
        corrupt(List.of("safe"));
    }
}
~~~

Chuỗi sự kiện:

1. Lời gọi varargs tạo một mảng để giữ các đối tượng **List**.
2. Phép gán **Object[] array = groups** làm lộ cùng mảng thông qua một tham chiếu rộng hơn.
3. **array[0] = List.of(42)** đặt một **List<Integer>** vào vị trí mà mã nguồn của method kỳ vọng là **List<String>**.
4. Khi chạy **String text = groups[0].get(0)**, mã cần chuyển giá trị phần tử sang String nhưng nhận **Integer**, dẫn tới **ClassCastException**.

Điểm đáng chú ý: phép gán phần tử mảng ở bước 3 có thể qua được kiểm tra kiểu runtime vì mảng kiểm tra kiểu **List**, không kiểm tra đối số generic **String** bên trong.

Ví dụ cố ý tạo **heap pollution** để minh họa rủi ro. Tuyệt đối không thêm **@SafeVarargs** vào phương thức **corrupt()** để che cảnh báo: annotation sẽ tạo một cam kết sai về tính an toàn.

## 11. @SafeVarargs có ý nghĩa gì?

**java.lang.SafeVarargs** là annotation dùng cho constructor hoặc method có tham số varargs. Khi gắn annotation, người viết API tuyên bố rằng phần triển khai không thực hiện những thao tác không an toàn đối với tham số varargs và có thể sử dụng mà không phải phát cảnh báo unchecked liên quan tại lời gọi theo cơ chế tương ứng.

Ví dụ với một method chỉ đọc danh sách:

~~~java
import java.util.List;

class Reports {
    @SafeVarargs
    static void printAll(List<String>... groups) {
        for (List<String> group : groups) {
            for (String entry : group) {
                System.out.println(entry);
            }
        }
    }
}
~~~

Trong ví dụ, method chỉ duyệt mảng và các danh sách, không ghi giá trị có kiểu sai vào mảng và không lưu hoặc trả về mảng varargs để mã khác thay đổi. Với điều kiện các đối số tuân thủ hợp đồng kiểu, cách triển khai này là ví dụ phù hợp cho **@SafeVarargs**.

### Annotation không tạo phép kiểm tra kiểu runtime

**@SafeVarargs**:

- Không biến một **List<String>[]** thành mảng có kiểm tra generic runtime đầy đủ.
- Không khiến Java bỏ type erasure.
- Không tự sao chép mảng.
- Không ngăn phần thân method cố tình ghi phần tử không đúng kiểu.
- Không thay thế việc thiết kế một API an toàn.

Một phần mã nguy hiểm **không trở nên an toàn** chỉ vì được đánh dấu **@SafeVarargs**. Trình biên dịch có thể phát thêm cảnh báo khi phát hiện một số thao tác đáng nghi trong phần thân method (ví dụ với tùy chọn cảnh báo thích hợp), nhưng không thể chứng minh hoàn toàn an toàn cho mọi triển khai.

### Khi nào cần annotation?

Với varargs của kiểu **reifiable** như **String...** hoặc **int...**, thường không có cảnh báo unchecked generic-array đặc thù để cần xử lý. **@SafeVarargs** có giá trị nhất khi làm việc với varargs có thành phần **non-reifiable**, chẳng hạn **T...** hoặc **List<String>...**.

## 12. @SafeVarargs được phép đặt ở đâu?

Java giới hạn nơi có thể sử dụng **@SafeVarargs** vì một method có thể bị ghi đè sẽ khó giữ lời hứa an toàn cho những phần triển khai chưa biết trước.

Trong Java hiện đại, có thể gắn **@SafeVarargs** cho:

| Vị trí | Được phép? | Lý do |
|---|---|---|
| **static** varargs method | Có | Static method không bị override theo đa hình instance |
| **final** instance varargs method | Có | Lớp con không thể ghi đè method |
| **private** instance varargs method | Có | Private method không bị ghi đè; hỗ trợ từ Java 9 |
| Constructor có varargs | Có | Constructor không bị ghi đè |
| Instance method có thể bị override | Không | Không bảo đảm phần triển khai của lớp con |
| Abstract method hoặc default interface method có thể bị override | Không | Không đáp ứng yêu cầu không thể ghi đè |
| Method không có tham số varargs | Không | Annotation chỉ dành cho method/constructor varargs |

Ví dụ các dạng hợp lệ:

~~~java
import java.util.Arrays;
import java.util.List;

final class SafeFactory<T> {
    private final List<T> items;

    @SafeVarargs
    SafeFactory(T... items) {
        this.items = List.copyOf(Arrays.asList(items));
    }

    @SafeVarargs
    static <E> List<E> snapshot(E... values) {
        return List.copyOf(Arrays.asList(values));
    }

    @SafeVarargs
    private final void inspect(T... values) {
        for (T value : values) {
            System.out.println(value);
        }
    }

    List<T> items() {
        return items;
    }
}
~~~

Constructor, static method và private final method ở trên đều nằm trong những vị trí được phép. **private final** là kết hợp hợp lệ nhưng **final** không cần thiết để private method đủ điều kiện sử dụng annotation.

**Không được** gắn **@SafeVarargs** lên một instance method có thể override rồi kỳ vọng trình biên dịch bỏ qua hạn chế. Nếu method cần cho lớp con ghi đè, có thể thiết kế lại API để không dùng generic varargs ở ranh giới đó.

## 13. Mẫu an toàn: sao chép phòng vệ thay vì trả mảng varargs

Một factory generic nhận varargs có thể tạo một **snapshot** bất biến của các phần tử:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public final class Snapshots {
    private Snapshots() {}

    @SafeVarargs
    public static <T> List<T> immutableOf(T... elements) {
        Objects.requireNonNull(elements, "elements");
        return List.copyOf(Arrays.asList(elements));
    }
}
~~~

Sử dụng:

~~~java
List<String> colors = Snapshots.immutableOf("red", "green", "blue");

System.out.println(colors); // [red, green, blue]
~~~

Phân tích tính an toàn:

1. **elements** được nhận dưới dạng mảng varargs.
2. Phương thức không ghi phần tử kiểu khác vào mảng.
3. **Arrays.asList(elements)** tạo một view của mảng để đọc các phần tử.
4. **List.copyOf(...)** tạo danh sách không sửa được, giữ thứ tự phần tử và không cho phép null.
5. Method chỉ trả danh sách kết quả, **không** trả về view do **Arrays.asList()** tạo ra hay chính mảng **elements**.

Vì thế, mảng varargs không bị lộ ra ngoài qua kết quả trả về của method. Nếu người gọi truyền một mảng có sẵn, những chỉnh sửa về sau lên mảng đó không làm thay đổi snapshot được trả về. Tuy nhiên, việc tạo snapshot chỉ sao chép **tham chiếu phần tử**, không sao chép sâu các đối tượng có thể thay đổi trạng thái.

### Khác biệt với Arrays.asList()

~~~java
String[] source = {"A", "B"};

List<String> view = Arrays.asList(source);

source[0] = "Changed";

System.out.println(view.get(0)); // Changed
~~~

**Arrays.asList()** tạo danh sách có kích thước cố định được **backed by** mảng. Nó không cung cấp bản sao phòng vệ độc lập khỏi mảng đầu vào. Đừng trả trực tiếp view này nếu API cần bảo đảm rằng người dùng không thể quan sát thay đổi trên mảng nội bộ.

**List.copyOf()** tạo danh sách không sửa được theo hợp đồng của Java Collections; trong tình huống **Arrays.asList(source)** này, kết quả không còn phụ thuộc vào việc thay đổi phần tử của **source** sau đó.

## 14. Mẫu an toàn: gộp các List bằng generic varargs

Một trường hợp thực tế: gộp nhiều danh sách các kiểu con vào một danh sách kết quả có kiểu chung.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class MergeLists {
    private MergeLists() {}

    @SafeVarargs
    public static <T> List<T> flatten(List<? extends T>... groups) {
        Objects.requireNonNull(groups, "groups");

        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(Objects.requireNonNull(group, "group"));
        }

        return List.copyOf(result);
    }
}
~~~

Ví dụ:

~~~java
List<Integer> integers = List.of(1, 2);
List<Double> decimals = List.of(3.5, 4.5);

List<Number> all = MergeLists.flatten(integers, decimals);

System.out.println(all); // [1, 2, 3.5, 4.5]
~~~

Ý nghĩa của chữ ký:

- **<T>** là kiểu phần tử chung của kết quả.
- **List<? extends T>...** cho phép các danh sách nguồn chứa các kiểu con phù hợp của T.
- Lặp qua **groups** chỉ để đọc; phương thức không ghi vào mảng varargs.
- Không giữ lại **groups**, không trả về mảng, không truyền mảng cho mã bên ngoài có thể sửa.
- Kết quả dùng **List.copyOf()**, nên không bị sửa qua API danh sách trả về.

Đây là ví dụ phù hợp với **@SafeVarargs**, đồng thời áp dụng PECS vào một API thật sự.

### Trường hợp null

**List.copyOf()** không chấp nhận phần tử null. Vì vậy, **flatten()** ở trên từ chối null trong danh sách nguồn khi tạo kết quả; ví dụ cũng từ chối mảng varargs null và một phần tử danh sách nguồn null.

Nếu miền nghiệp vụ thực sự cho phép phần tử null, cần thiết kế và ghi rõ hợp đồng phù hợp thay vì dùng **List.copyOf()** rồi mặc nhiên cho rằng null được bảo toàn.

## 15. Những điều cần tránh với varargs generic

### Không trả trực tiếp mảng varargs

Ví dụ không nên dùng:

~~~java
static <T> T[] exposed(T... values) {
    return values;
}
~~~

Phương thức trả về chính mảng nhận được. Nếu mảng này có thể được quan sát và chỉnh sửa qua một tham chiếu khác, API có nguy cơ gặp thay đổi không kiểm soát hoặc tương tác kiểu không an toàn.

Với trường hợp cần một mảng kết quả, hợp đồng phải xác định rõ kiểu mảng và việc sao chép. Một cách thiết kế hiện đại là nhận một **IntFunction<T[]>** để người gọi cung cấp factory tạo mảng phù hợp:

~~~java
import java.util.List;
import java.util.function.IntFunction;

static <T> T[] copyToArray(
        List<? extends T> source,
        IntFunction<T[]> arrayFactory) {
    return source.toArray(arrayFactory.apply(source.size()));
}
~~~

Ví dụ:

~~~java
String[] names = copyToArray(
        List.of("Lan", "Minh"),
        String[]::new);
~~~

Ở đây, người gọi cung cấp cách tạo **String[]**. Không cần tạo một mảng **T[]** bằng cú pháp bị Java cấm.

### Không ghi phần tử generic không tương thích vào mảng

Mã như sau là nguy hiểm:

~~~java
static void overwrite(List<String>... groups) {
    Object[] rawArrayView = groups;
    rawArrayView[0] = List.of(123);
}
~~~

Hãy tránh ép hoặc mở rộng tham chiếu mảng để có thể ghi giá trị sai kiểu. Điều này trực tiếp phá vỡ cam kết của một API generic.

### Không lưu mảng varargs ở nơi khác

Ví dụ không nên dùng:

~~~java
class Holder {
    private static Object[] lastValues;

    static <T> void remember(T... values) {
        lastValues = values;
    }
}
~~~

Một mảng varargs bị lưu trong trạng thái dùng chung có thể bị đọc hoặc sửa ngoài ngữ cảnh lời gọi ban đầu. Tác hại phụ thuộc cách mảng được sử dụng sau đó, nhưng đây không phải mô hình đáng tin cậy để cam kết **@SafeVarargs**.

Nếu cần lưu dữ liệu lâu dài, hãy sao chép vào cấu trúc dữ liệu có hợp đồng rõ ràng thay vì giữ mảng do caller hoặc compiler cung cấp.

### Tránh truyền mảng cho helper không đáng tin cậy

Ngay cả khi method hiện tại không trực tiếp ghi phần tử, việc chuyển mảng varargs sang một helper có thể thay đổi hoặc làm lộ nó cũng khiến lời hứa **@SafeVarargs** không còn đáng tin.

Không đánh giá tính an toàn chỉ bằng việc tìm một câu lệnh gán trong phần thân. Cần xem toàn bộ đường đi của mảng: **ai nhận được tham chiếu, ai có thể sửa, và mảng có thoát khỏi phạm vi lời gọi không**.

## 16. Chọn Collection thay cho varargs khi nào?

Varargs hữu ích khi người dùng thường truyền một số lượng phần tử nhỏ ngay tại lời gọi:

~~~java
List<String> tags = Snapshots.immutableOf("java", "generics", "api");
~~~

Nhưng varargs không phải lúc nào cũng là API tốt nhất. Nếu nguồn dữ liệu đã tồn tại dưới dạng **Collection<T>**, ép người gọi phải chuyển thành mảng có thể làm API khó dùng và tạo thêm các vấn đề kiểu.

Ví dụ:

~~~java
import java.util.Collection;
import java.util.List;

static <T> List<T> snapshot(Collection<? extends T> source) {
    return List.copyOf(source);
}
~~~

Người gọi có thể truyền trực tiếp một collection có sẵn:

~~~java
List<String> existing = List.of("A", "B");
List<String> copied = snapshot(existing);
~~~

Tùy nhu cầu, có thể cung cấp một overload cho **Collection** và một overload varargs an toàn. Tuy nhiên, hãy cân nhắc khả năng nhập nhằng overload và số lượng API công khai; không nên tạo nhiều overload chỉ vì có thể.

| Tình huống | Hướng thiết kế đáng cân nhắc |
|---|---|
| Gọi với vài phần tử tường minh | Varargs có thể dễ đọc |
| Dữ liệu đã ở dạng List/Collection | Nhận Collection hoặc Iterable trực tiếp |
| Muốn duy trì kiểu phần tử và đọc từ nguồn | **Collection<? extends T>** hoặc **Iterable<? extends T>** |
| Muốn thêm phần tử kiểu T vào đích | **Collection<? super T>** |
| Muốn tạo snapshot không sửa được | **List.copyOf()**, với chính sách null rõ ràng |
| Muốn mảng đúng kiểu runtime | Nhận array factory hoặc kiểu **Class<T>** phù hợp; không tự tạo **new T[]** |
| Varargs chứa kiểu non-reifiable | Kiểm tra heap pollution và chỉ dùng **@SafeVarargs** khi thật sự an toàn |

## 17. @SuppressWarnings không thay thế @SafeVarargs

**@SuppressWarnings("unchecked")** yêu cầu trình biên dịch không hiển thị một nhóm cảnh báo trong phạm vi áp dụng. Nó không nói riêng về hợp đồng an toàn của phương thức varargs với người gọi.

**@SafeVarargs** được thiết kế cho trường hợp constructor/method varargs đủ điều kiện và **thực sự an toàn**, để tránh cảnh báo phát sinh từ non-reifiable varargs ở khai báo và điểm gọi theo quy tắc Java.

Không nên áp dụng **@SuppressWarnings("unchecked")** lên cả lớp hoặc cả file chỉ để làm sạch output compiler. Nếu không thể tránh một phép ép kiểu unchecked trong nội bộ một generic API, hãy:

1. Chọn cách thiết kế không cần ép kiểu trước.
2. Nếu vẫn cần, giới hạn suppression ở phạm vi nhỏ nhất hợp lý.
3. Giải thích rõ vì sao phép chuyển kiểu an toàn dựa trên bất biến cụ thể.
4. Có kiểm thử với các kiểu dữ liệu thực sự được hỗ trợ.

Ví dụ sử dụng **Class<T>** để kiểm tra kiểu runtime mà không cần unchecked cast:

~~~java
import java.util.Objects;

public final class TypedValues {
    private TypedValues() {}

    public static <T> T requireType(Object value, Class<T> type) {
        return Objects.requireNonNull(type, "type").cast(value);
    }
}
~~~

Sử dụng:

~~~java
String text = TypedValues.requireType("hello", String.class);
Integer number = TypedValues.requireType(10, Integer.class);
~~~

**Class.cast()** thực hiện kiểm tra kiểu theo token được truyền vào. Tuy nhiên, **String.class** chỉ cung cấp thông tin kiểu String; cách này **không** giải quyết việc kiểm tra đầy đủ một kiểu như **List<String>** ở runtime sau erasure.

## 18. Ví dụ tổng hợp: xây dựng generic API an toàn

Ví dụ sau là một chương trình độc lập thể hiện:

- Generic factory nhận varargs và sao chép phòng vệ.
- Phương thức nhận nhiều nguồn có kiểu phần tử khác nhau thông qua bounded wildcard.
- Phương thức nguồn/đích theo PECS.
- Không rò rỉ mảng varargs.
- **@SafeVarargs** đặt đúng vào static method không thể bị override.
- Dùng collection thay cho varargs khi dữ liệu đã ở dạng collection.

Lưu vào tệp **GenericApiDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

public final class GenericApiDemo {
    private GenericApiDemo() {}

    @SafeVarargs
    public static <T> List<T> snapshot(T... values) {
        Objects.requireNonNull(values, "values");
        return List.copyOf(Arrays.asList(values));
    }

    @SafeVarargs
    public static <T> List<T> merge(List<? extends T>... groups) {
        Objects.requireNonNull(groups, "groups");

        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(Objects.requireNonNull(group, "group"));
        }

        return List.copyOf(result);
    }

    public static <T> void appendAll(
            Collection<? super T> destination,
            Iterable<? extends T> source) {
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");

        for (T item : source) {
            destination.add(item);
        }
    }

    public static void main(String[] args) {
        // 1. Factory generic, varargs kiểu T.
        List<String> names = snapshot("Lan", "Minh", "An");
        System.out.println(names);

        // 2. Dữ liệu gốc là mảng: kết quả là snapshot độc lập.
        String[] input = {"first", "second"};
        List<String> snapshot = snapshot(input);
        input[0] = "changed";

        System.out.println(snapshot.get(0));

        // 3. Gộp các danh sách kiểu con của Number.
        List<Number> numbers = merge(
                List.of(1, 2),
                List.of(3.5, 4.5));

        System.out.println(numbers);

        // 4. Dùng PECS để thêm Dog vào Collection<Animal>.
        class Animal {}
        class Dog extends Animal {}

        List<Dog> dogs = List.of(new Dog(), new Dog());
        List<Animal> animals = new ArrayList<>();

        appendAll(animals, dogs);
        System.out.println(animals.size());

        // 5. Kết quả snapshot không cho phép chỉnh sửa.
        try {
            names.add("New");
        } catch (UnsupportedOperationException exception) {
            System.out.println("immutable list");
        }
    }
}
~~~

Kết quả:

~~~text
[Lan, Minh, An]
first
[1, 2, 3.5, 4.5]
2
immutable list
~~~

Giải thích:

1. **snapshot(T... values)** nhận mảng tham số và dùng **List.copyOf()** để tạo danh sách không sửa được, tách khỏi các thay đổi phần tử trên mảng nguồn.
2. **merge(List<? extends T>... groups)** đọc các danh sách nguồn và trả một kết quả dùng kiểu chung **T**; nó không sửa hoặc làm lộ mảng varargs.
3. **appendAll(Collection<? super T>, Iterable<? extends T>)** dùng wildcard đúng vai trò để chấp nhận nguồn kiểu con và đích kiểu cha.
4. **@SafeVarargs** hợp lệ vì hai phương thức varargs đều là **static**, và phần triển khai không gây heap pollution hay làm lộ mảng.
5. **List.copyOf()** từ chối phần tử null, nên các factory mẫu ở đây cam kết không hỗ trợ phần tử null. Không nên thêm một quy tắc cho phép null mà quên thay đổi cách tạo kết quả.
6. **UnsupportedOperationException** trong ví dụ chỉ minh họa danh sách trả về không hỗ trợ thao tác **add()**; thiết kế API không dựa trên việc bắt ngoại lệ để sửa danh sách.

Ví dụ không chạy kiểm thử hiệu năng hay đo bộ nhớ. Khi cần tối ưu, hãy đo hành vi thực tế thay vì tự giả định rằng varargs hoặc collection luôn nhanh hơn trong mọi trường hợp.

## 19. Các lỗi và cảnh báo thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cảnh báo **unchecked generic array creation** | Gọi varargs có thành phần non-reifiable | Xác định method có an toàn không; dùng **@SafeVarargs** đúng chỗ hoặc đổi sang Collection |
| Cảnh báo **Possible heap pollution** | Khai báo generic varargs mà compiler không thể bảo đảm an toàn | Rà soát mảng varargs, không sửa sai kiểu, không để mảng thoát |
| **ClassCastException** xuất hiện muộn | Giá trị sai kiểu đã vào cấu trúc generic qua thao tác unchecked | Tìm nguồn heap pollution; không chỉ chữa bằng ép kiểu |
| **ArrayStoreException** | Ghi phần tử không tương thích với kiểu mảng runtime | Tôn trọng kiểu thành phần của mảng; tránh array covariance không an toàn |
| Không thể **new T[]** | Type parameter không reifiable ở runtime | Dùng collection, hoặc nhận array factory |
| **List<Dog>** không gán được vào **List<Animal>** | Generic invariance | Dùng wildcard theo khả năng đọc/ghi |
| **@SafeVarargs** báo lỗi biên dịch | Đặt lên method không varargs hoặc có thể bị ghi đè | Chỉ gắn lên varargs static, final, private hoặc constructor |
| Có **@SafeVarargs** nhưng vẫn gặp ClassCastException | Annotation không bảo vệ runtime và không sửa unsafe code | Loại bỏ heap pollution thật sự trong triển khai |
| Danh sách bất biến vẫn phản ánh thay đổi trong phần tử | Sao chép danh sách chỉ là shallow copy | Thiết kế phần tử bất biến hoặc sao chép sâu khi có yêu cầu |
| Dùng **@SuppressWarnings("unchecked")** trên phạm vi quá rộng | Che cảnh báo thay vì giải quyết nguyên nhân | Dùng suppression tối thiểu, giải thích và kiểm thử |
| Method varargs nhận null gây lỗi | Mảng varargs hoặc phần tử không đáp ứng hợp đồng | Dùng kiểm tra null và mô tả API rõ ràng |

## 20. Checklist thiết kế generic API và SafeVarargs

Trước khi công khai một generic API trong Java 27, hãy tự hỏi:

- Type parameter có thực sự mô tả quan hệ giữa đầu vào, đầu ra hoặc nhiều tham số không?
- Nếu chỉ đọc dữ liệu, wildcard **? extends T** hoặc **?** có thể làm API linh hoạt hơn không?
- Nếu thêm giá trị kiểu T vào đích, **? super T** có phù hợp hơn không?
- Phương thức có đang yêu cầu một concrete collection mà không thật sự cần không?
- Có raw type, unchecked cast hoặc giả định sai về thông tin generic tại runtime không?
- Generic array có thật sự cần thiết hay dùng **List** sẽ an toàn và dễ hiểu hơn?
- Varargs là lợi ích thực sự của người gọi hay chỉ tạo thêm một kiểu tham số khó kiểm soát?
- Với generic varargs, có thao tác ghi vào mảng, chuyển sang **Object[]**, lưu mảng vào field hoặc trả mảng ra ngoài không?
- Có truyền mảng varargs cho helper mà không biết chắc helper sẽ làm gì không?
- Nếu dùng **@SafeVarargs**, method/constructor có thuộc vị trí hợp lệ và lời hứa an toàn có đúng không?
- Kết quả trả về là view, snapshot hay collection có thể sửa? Chính sách null có được nói rõ không?
- Đã kiểm thử lời gọi với nhiều kiểu phần tử (bao gồm subtype) và trường hợp đầu vào không hợp lệ chưa?

## Kết luận

Generic API tốt thể hiện được **quan hệ kiểu dữ liệu** bằng type parameter và wildcard mà không buộc người gọi phải ép kiểu hoặc dùng raw type. Nguyên tắc **PECS** giúp xác định cách thiết kế nguồn đọc và đích ghi; **bounded type** giúp API yêu cầu đúng khả năng mà đối tượng phải có.

Khi kết hợp generics với varargs, cần nhớ rằng varargs là một **mảng ở runtime**, còn những đối số generic như **List<String>** thường **không reifiable**. Vì vậy, có thể xuất hiện heap pollution và cảnh báo unchecked. Chỉ gắn **@SafeVarargs** khi phương thức hoặc constructor nằm ở vị trí hợp lệ **và** phần triển khai thực sự không làm hỏng an toàn kiểu hay làm lộ mảng varargs không an toàn.

Trong Java 27, lựa chọn mặc định đáng tin cậy thường là: **dùng abstraction thích hợp, sao chép phòng vệ khi cần, giữ hợp đồng null rõ ràng và ưu tiên an toàn kiểu hơn việc chỉ làm biến mất cảnh báo trình biên dịch**.
