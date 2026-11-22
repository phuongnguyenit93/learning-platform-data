# Khi dùng wildcard và khi phải đặt tên tham số kiểu trong Java Generics

## 1. Bài toán thiết kế kiểu: `?` hay `<T>`?

Trong Java generics, **wildcard** `?` biểu diễn một kiểu chưa biết, còn **type parameter có tên** như `T`, `E`, `K` hoặc `V` cho phép nhiều vị trí trong chữ ký phương thức cùng **tham chiếu đến một quan hệ kiểu**. Cả hai có thể làm API linh hoạt, nhưng chúng diễn đạt những thông tin khác nhau.

Ví dụ, một phương thức chỉ cần đếm số phần tử:

~~~java
static int count(List<?> values) {
    return values.size();
}
~~~

Ở đây `?` là đủ: không có lý do gì để đặt tên cho kiểu phần tử. Một chữ ký `static <T> int count(List<T> values)` cũng có thể dùng, nhưng `T` không mang thêm quan hệ hữu ích nào.

Ngược lại, một phương thức lấy phần tử đầu và **trả về đúng kiểu phần tử mà caller cung cấp** cần `T`:

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}
~~~

Với `List<String>`, kết quả có kiểu `String`; với `List<Integer>`, kết quả có kiểu `Integer`. Thay `T` bằng `?` sẽ mất mối liên hệ giữa **kiểu phần tử đầu vào** và **kiểu giá trị trả về**.

Phần còn lại của bài sẽ giúp bạn:

- Chọn đúng `?`, `? extends T` và `? super T` theo hướng dữ liệu của quy tắc **PECS** (*Producer Extends, Consumer Super*).
- Nhận biết thời điểm cần khai báo `<T>` hoặc `<T, R>` để diễn tả quan hệ giữa nhiều vị trí.
- Kết hợp wildcard và type parameter trong **cùng một chữ ký**, thay vì xem chúng là hai lựa chọn loại trừ nhau.
- Hiểu vì sao một phương thức public nhận `List<?>` đôi khi phải gọi một helper `<T>` để giữ **wildcard capture**.
- Tránh các chữ ký quá chặt, quá rộng hoặc buộc caller phải dùng raw type/unchecked cast.

## 2. Cơ chế kiểu: “không cần biết tên” và “cần gọi cùng một tên”

Xem ba chữ ký:

~~~java
static void showAll(List<?> values) { /* ... */ }

static double sum(List<? extends Number> values) { /* ... */ }

static <T> T selectFirst(List<T> values) { return values.get(0); }
~~~

Các đoạn này **minh họa chữ ký**, phải đặt trong một lớp và import `java.util.List` nếu cần biên dịch độc lập.

- `List<?>`: **một kiểu phần tử chưa biết**; mọi phần tử có thể đọc như `Object`. Hữu ích khi thuật toán không cần API riêng của phần tử.
- `List<? extends Number>`: **một subtype chưa biết của `Number`**; mọi phần tử đọc được như `Number`, nên có thể gọi `doubleValue()`.
- `<T> T selectFirst(List<T>)`: đặt tên `T` ở cả input và output. Caller truyền `List<String>` thì được `String`, không cần cast.

Có thể đọc `?` như “kiểu cụ thể là gì không quan trọng với lời hứa của API”. Có thể đọc `T` như “kiểu cụ thể có thể khác nhau giữa những lời gọi, nhưng **các vị trí nhắc tới `T` trong cùng một lời gọi phải thỏa những ràng buộc của `T`**”.

**Lưu ý về chữ ký:** `?` là *type argument* bên trong `List<?>`, `Class<?>`…; bạn **không thể** dùng dấu `?` độc lập làm kiểu trả về theo dạng `static ? first(...)`. Muốn trả về giá trị có kiểu liên hệ với input, cần type variable có tên hoặc một kiểu cụ thể.

## 3. Dùng wildcard khi không cần duy trì danh tính kiểu qua các vị trí

### 3.1. Chỉ quan sát dữ liệu bằng API của `Object`: `?`

~~~java
static void printItems(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

`printItems(List.of("A", "B"))` và `printItems(List.of(1, 2))` đều hợp lệ. Phương thức không quan tâm `String` hay `Integer`; mọi object đều có thể in ra thông qua `println(Object)`.

Biến thể có type parameter sau đây không tăng tính an toàn:

~~~java
static <T> void printItemsWithT(List<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
~~~

Nếu `T` không xuất hiện ở **vị trí nào khác có ý nghĩa** và thân phương thức không yêu cầu giữ danh tính kiểu, wildcard rõ ý định hơn. Đây là **quy tắc thiết kế**; không phải compiler cấm khai báo type parameter dùng một lần.

### 3.2. Chỉ đọc theo một upper bound: `? extends T`

~~~java
static double average(List<? extends Number> numbers) {
    if (numbers.isEmpty()) {
        throw new IllegalArgumentException("empty list");
    }
    double sum = 0;
    for (Number number : numbers) {
        sum += number.doubleValue();
    }
    return sum / numbers.size();
}
~~~

Ví dụ có thể nhận `List<Integer>`, `List<Long>`, `List<Double>`, v.v. Vì thuật toán chỉ cần phương thức có ở `Number` và **không trả về giá trị dưới kiểu subtype gốc**, ta không cần thêm `<T extends Number>`.

So sánh chữ ký:

~~~java
// Đủ rõ khi chỉ dùng Number để đọc:
static double average(List<? extends Number> numbers) { /* ... */ }

// Hợp lệ nhưng T không phục vụ mối liên hệ nào:
static <T extends Number> double averageWithT(List<T> numbers) { /* ... */ }
~~~

Hai khối trên chỉ so sánh **chữ ký** (thân `/* ... */` không cung cấp implementation hoàn chỉnh của phương thức trả `double`). Khi viết code thực, dùng implementation `average` ở phía trên.

**Cơ chế:** với `List<? extends Number>`, compiler chỉ biết phần tử có một kiểu capture `CAP <: Number`. Đọc được `Number`, nhưng không thể `add(Integer)` hay `add(Double)` tùy ý vì `CAP` có thể là subtype khác. Wildcard `extends` phù hợp với nơi **cung cấp dữ liệu để phương thức đọc**.

### 3.3. Chỉ ghi vào một đích: `? super T`

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

Có thể truyền `List<Integer>`, `List<Number>` hoặc `List<Object>`. Cả ba đều chấp nhận giá trị `Integer`.

Với `List<? super Integer>`, compiler **chỉ bảo đảm** kiểu đọc `get(...)` là `Object`, vì danh sách thật có thể là `List<Object>` đã chứa giá trị khác. Hợp đồng ở đây tập trung vào **ghi dữ liệu**. Không cần khai báo `<T extends Integer>` chỉ để thêm các giá trị `Integer` đã biết.

### 3.4. Áp dụng PECS theo vai trò của tham số

| Vai trò mà phương thức cần | Chữ ký thường phù hợp | Lý do |
| --- | --- | --- |
| Chỉ đếm, in hoặc xử lý dưới dạng `Object` | `List<?>` | Không cần biết loại phần tử. |
| Đọc các `Number` | `List<? extends Number>` | Mỗi phần tử chắc chắn là một `Number`. |
| Thêm `Integer` vào danh sách đích | `List<? super Integer>` | Mọi supertype của `Integer` đều nhận được `Integer`. |
| Đọc và ghi lại phần tử dưới **cùng kiểu ẩn** | `List<?>` + helper `<T>`, hoặc `List<T>` | Cần giữ capture type bên trong thao tác. |
| Trả lại chính kiểu phần tử của input | `<T> T first(List<T>)` | Quan hệ input/output đòi tên chung `T`. |
| Nối nguồn vào đích với kiểu liên hệ | `<T> void append(List<? extends T>, List<? super T>)` | `T` nối hai vị trí, wildcard thể hiện producer/consumer. |

PECS xem xét **luồng dữ liệu phần tử đối với phương thức**: tham số là *producer* khi cung cấp phần tử để đọc, *consumer* khi nhận phần tử để ghi. Nó không có nghĩa `? extends` biến collection thành immutable hay `? super` cấm đọc; những thao tác khác vẫn theo API/implementation cụ thể.

## 4. Đặt tên `T` khi phải bảo toàn quan hệ giữa tham số và kết quả

Một API lấy phần tử đầu:

~~~java
static Object firstObject(List<?> values) {
    return values.get(0);
}
~~~

Nó chấp nhận mọi loại danh sách, nhưng caller chỉ nhận được `Object`. Nếu cần trả về loại gốc, dùng:

~~~java
static <T> T firstTyped(List<T> values) {
    return values.get(0);
}

String s = firstTyped(List.of("Lan", "Minh"));
Integer n = firstTyped(List.of(2, 4, 6));
~~~

Đây là ví dụ có các dòng lời gọi đặt trong **phương thức hoặc khối Java hợp lệ**; cần import `List`. Không có cast không kiểm tra. Compiler suy luận `T = String` hoặc `T = Integer` từ argument và ngữ cảnh.

Vậy có nên viết:

~~~java
static <T> T firstFromExtends(List<? extends T> values) {
    return values.get(0);
}
~~~

Cũng **hợp lệ**. Chữ ký này cho phép list có phần tử subtype của `T`; nó còn cho phép type inference chọn `T` rộng hơn dựa vào ngữ cảnh. Sự khác nhau giữa `List<T>` và `List<? extends T>` phải được cân nhắc theo contract, không theo cảm giác “extends luôn tốt hơn”.

Cần lưu ý trường hợp list rỗng: cả `firstTyped` và `firstFromExtends` ở đây đều ném `IndexOutOfBoundsException` nếu gọi `get(0)` khi không có phần tử. Generics chỉ kiểm soát **kiểu**, không bảo đảm list có ít nhất một phần tử.

### 4.1. Khi kết quả có nhiều kiểu quan hệ

Nếu hàm chuyển `T` sang `R`, hai tên có ý nghĩa độc lập:

~~~java
static <T, R> List<R> mapAll(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> output = new ArrayList<>();
    for (T value : source) {
        output.add(mapper.apply(value));
    }
    return output;
}
~~~

Đoạn này là **phương thức minh họa**, đặt trong lớp có import `java.util.List` và `java.util.ArrayList` để biên dịch. Nó cho thấy:

- `T` là kiểu được đọc từ danh sách nguồn.
- `R` là kiểu kết quả tạo ra.
- `? extends T` cho phép source cung cấp subtype của `T`.
- `Function<? super T, ? extends R>` nhận được giá trị `T` và trả về `R` hoặc subtype của `R`.
- `List<R>` thể hiện đầu ra định kiểu chính xác theo `R`.

Sử dụng wildcard **bên trong** khai báo generic `Function<...>` không làm `T`, `R` dư thừa; ngược lại, những tên này giúp nối loại dữ liệu giữa source, mapper và kết quả.

## 5. Đặt tên `T` khi phải diễn đạt quan hệ giữa nhiều tham số

Giả sử ta muốn sao chép từng phần tử **bằng cách thêm vào cuối danh sách đích**. Nguồn có thể chứa `Integer`, trong khi đích được khai báo `List<Number>`.

Dùng một method type parameter để nói rõ rằng nguồn tạo ra `T` và đích nhận được `T`:

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
~~~

Ví dụ hợp lệ:

~~~java
List<Integer> source = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendAll(source, numbers);
appendAll(source, objects);
~~~

**Tại sao không chỉ có wildcard không tên?**

~~~java
// KHÔNG biên dịch: hai dấu ? biểu diễn hai kiểu chưa biết độc lập.
static void badAppend(List<?> source, List<?> target) {
    for (Object element : source) {
        target.add(element); // Không thể xác nhận element có đúng kiểu của target.
    }
}
~~~

`List<?>` không cho compiler biết kiểu của source và target có liên hệ gì. Dùng `<T>` làm **cầu nối** giữa hai tham số. Hai wildcard `? extends T`, `? super T` khiến chữ ký vừa an toàn, vừa không quá hạn chế.

### 5.1. Vì sao `List<T>` ở cả hai phía thường quá chặt?

~~~java
// Có thể quá chặt cho nhu cầu producer -> consumer:
static <T> void appendStrict(List<T> source, List<T> target) {
    target.addAll(source);
}
~~~

Với `List<Integer>` và `List<Number>`, lời gọi `appendStrict(ints, numbers)` không biên dịch: generic `List<T>` là invariant, và một `T` không thể đồng thời bằng `Integer` và `Number` cho hai parameterized types ấy.

Đối với thao tác chuyển phần tử, điều cần chứng minh không phải **hai danh sách có cùng type argument**, mà là **mọi phần tử từ source đều gán được cho target**. `<T> List<? extends T>` và `List<? super T>` diễn đạt đúng sự phụ thuộc đó.

### 5.2. Đối chiếu với API chuẩn

`java.util.Collections.copy` dùng:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src);
~~~

Đây là **chữ ký API**, không phải định nghĩa phương thức có body để tự biên dịch. `copy` **ghi đè các phần tử ở vị trí tương ứng** của đích và yêu cầu đích có đủ phần tử; không dùng giống thao tác `appendAll` thêm vào cuối. Cả hai vẫn chia sẻ cùng kiểu hợp đồng producer/consumer.

Phương thức chuẩn `Collection<E>.addAll(Collection<? extends E> c)` cũng minh họa quy tắc: `E` đã được **đặt tên ở cấp interface** là kiểu phần tử của đích; vì thế tham số source chỉ cần wildcard `? extends E`, không phải khai báo thêm `<S extends E>` dùng một lần.

## 6. Trường hợp đặc biệt: wildcard capture buộc dùng helper `<T>`

Không phải lúc nào một API nhận `List<?>` cũng có thể hoàn thành thao tác trong cùng thân phương thức. Có những thao tác cần **lấy một phần tử và ghi lại nó vào chính collection đó**.

Ví dụ thử hoán đổi phần tử đầu và cuối:

~~~java
// KHÔNG biên dịch:
static void badSwap(List<?> list) {
    list.set(0, list.get(list.size() - 1));
}
~~~

Thoạt nhìn đây là thao tác an toàn vì đọc và ghi vào **cùng một list**. Tuy nhiên mỗi biểu thức liên quan tới kiểu phần tử không tên có thể được compiler xử lý bằng các capture variables khác nhau, nên compiler không thể bảo đảm phép truyền giá trị như cách code ở trên.

Thiết kế đúng là **public API dùng wildcard để nhận bất kỳ list**, còn helper private đặt tên cho capture type:

~~~java
static void swapEnds(List<?> values) {
    swapEndsCaptured(values);
}

private static <T> void swapEndsCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    int lastIndex = values.size() - 1;
    T first = values.get(0);
    values.set(0, values.get(lastIndex));
    values.set(lastIndex, first);
}
~~~

Ở lời gọi `swapEndsCaptured(values)`, type inference và capture conversion cho phép Java đặt tên tạm cho kiểu phần tử duy nhất của **cùng list** thành `T` trong helper. Các lệnh `get`/`set` từ đây dùng chung `T` và không cần cast.

Đây là khác biệt giữa:

- **Bề mặt API:** caller không cần biết kiểu phần tử nên dùng `List<?>`.
- **Implementation:** khi thuật toán phải di chuyển những giá trị cùng kiểu phần tử qua nhiều biểu thức, helper `<T>` có ích để compiler biểu diễn quan hệ ấy.

Nếu caller đưa vào `List.of(...)` bất biến thì phép `set` ném `UnsupportedOperationException` lúc chạy. Ví dụ hoán đổi phải nhận list mutable (như `ArrayList`). Type safety và mutability là hai hợp đồng khác nhau.

## 7. Chương trình Java 17+ hoàn chỉnh, biên dịch và chạy được

Tạo tệp **WildcardOrTypeParameterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardOrTypeParameterDemo {
    static double average(List<? extends Number> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty list");
        }
        double sum = 0.0;
        for (Number value : values) {
            sum += value.doubleValue();
        }
        return sum / values.size();
    }

    static String summary(List<?> values) {
        return "size=" + values.size();
    }

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static void swapEnds(List<?> values) {
        swapEndsCaptured(values);
    }

    private static <T> void swapEndsCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        int lastIndex = values.size() - 1;
        T first = values.get(0);
        values.set(0, values.get(lastIndex));
        values.set(lastIndex, first);
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(2, 4, 6);
        System.out.println("average: " + average(ids));
        System.out.println("summary: " + summary(ids));

        String name = first(List.of("Lan", "Minh"));
        System.out.println("first: " + name);

        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(ids, destination);
        System.out.println("copied: " + destination);

        List<String> names = new ArrayList<>(List.of("A", "B", "C"));
        swapEnds(names);
        System.out.println("swapped: " + names);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:all WildcardOrTypeParameterDemo.java
java WildcardOrTypeParameterDemo
~~~

**Stdout chính xác**:

~~~text
average: 4.0
summary: size=3
first: Lan
copied: [1.5, 2, 4, 6]
swapped: [C, B, A]
~~~

Bài này đã được biên dịch với `javac --release 17 -Xlint:all` và chạy thành công, không có unchecked warning.

Từng phần giải thích một lựa chọn thiết kế:

1. `average` chỉ đọc `Number` nên dùng `? extends Number`.
2. `summary` không cần kiểu phần tử, nên dùng `?`.
3. `first` trả về đúng kiểu phần tử, nên cần type parameter `T`.
4. `appendAll` truyền `T` từ source sang target, nên cần `T` nối hai wildcard.
5. `swapEnds` nhận bất cứ `List<?>` nào, nhưng helper dùng `T` để giữ quan hệ giữa hai phần tử của cùng list.

## 8. Những tình huống cần kiểm tra kỹ trước khi chọn

### 8.1. Khi một container vừa cần đọc vừa cần ghi dữ liệu cùng kiểu

Nếu API cần lấy `T` từ một collection, biến đổi hoặc trao đổi rồi ghi **lại các `T` cùng kiểu**, một `List<T>` có tên hoặc helper capture thường rõ ràng hơn `List<? extends T>` / `List<? super T>`. Quy tắc “producer extends, consumer super” không nhằm ép wildcard vào mọi thao tác khi cùng một biến vừa producer vừa consumer.

Ví dụ:

~~~java
static <T> void replaceFirst(List<T> list, T value) {
    list.set(0, value);
}
~~~

`T` bảo đảm `value` phù hợp với phần tử của `list`. Cần lưu ý `set` có thể ném `IndexOutOfBoundsException` nếu list rỗng hoặc `UnsupportedOperationException` nếu không sửa được.

### 8.2. Type parameter một lần không tự động sai

Nguyên tắc “nếu `T` chỉ được nhắc một lần thì dùng wildcard” là heuristic **thiết kế chữ ký**, không phải quy tắc cú pháp bắt buộc. Có những lý do ngoại lệ: type parameter dùng trong bound của type parameter khác, inference phức tạp, interface contract cần giữ tương thích, hoặc triển khai nội bộ cần tên cho capture type.

Ví dụ, `<T extends Number> void observe(List<T>)` có thể được đơn giản hóa thành `void observe(List<? extends Number>)` khi chỉ cần đọc như `Number`. Nhưng không nên đổi chữ ký công khai tùy tiện nếu việc đổi làm ảnh hưởng binary/source compatibility của hệ thống hiện có; phải đánh giá callers, overloads và phương thức override.

### 8.3. Một tham số kiểu có thể nối nhiều vị trí gián tiếp qua bound

Không bắt buộc chữ `T` phải xuất hiện ở đúng hai tham số. Ví dụ:

~~~java
static <T extends Comparable<? super T>> T chooseMax(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

`T` xuất hiện ở input, output và bound `Comparable<? super T>`. Wildcard `? super T` của `Comparable` nói rằng phép so sánh có thể nhận `T` ngay cả khi implementation so sánh theo một supertype của `T`. Đây là trường hợp type parameter có tên và wildcard **bổ trợ lẫn nhau**.

### 8.4. Vị trí trả về thường nên cung cấp kiểu hữu ích nhất

Một phương thức trả `List<?>` hoặc `List<? extends Number>` có thể là hợp lệ, nhưng caller sẽ phải làm việc qua góc nhìn còn ít thông tin hơn. Nếu method biết chính xác kiểu phần tử hoặc có thể giữ `T` từ tham số đầu vào, trả `List<T>` thường dễ sử dụng hơn.

~~~java
static <T> List<T> mutableCopy(List<? extends T> source) {
    return new ArrayList<>(source);
}
~~~

Caller từ `List<String>` có thể nhận `List<String>`. Khi API chỉ cố ý công bố “một loại Number nào đó” thì kiểu trả về wildcard có thể thích hợp, nhưng cần nhận thức rõ giới hạn với caller.

### 8.5. Named type parameter không đồng nghĩa hai đối số có runtime class giống nhau

Compiler xác minh **khả năng gán/quan hệ kiểu theo chữ ký**, không kiểm tra hai đối tượng có cùng `getClass()`. Ngay cả khi type inference chọn một `T` chung, `T` có thể là interface hoặc superclass.

Ví dụ:

~~~java
static <T extends Number> void acceptPair(T a, T b) {
    System.out.println(a.doubleValue() + b.doubleValue());
}

acceptPair(10, 2.5); // Có thể suy luận T là một supertype phù hợp của Integer và Double.
~~~

Vì vậy “cùng `T`” không nhất thiết có nghĩa **cùng concrete class**. Nó có nghĩa mọi vị trí `T` tuân thủ một hệ ràng buộc kiểu chung mà compiler suy luận được.

## 9. Cách chọn theo một quy trình nhất quán

Khi thiết kế một phương thức generic mới, thực hiện theo thứ tự:

1. **Vẽ đường đi của phần tử:** phương thức lấy dữ liệu từ đâu, đưa dữ liệu đến đâu, có trả lại phần tử hoặc collection mới không?
2. **Tách loại chỉ cần quan sát:** nếu chỉ cần `size()`, `Object` hoặc xử lý không phụ thuộc loại phần tử, thử `<?>`.
3. **Chọn bound cho thao tác một chiều:** chỉ cần đọc `Number` → `? extends Number`; chỉ cần thêm `Integer` → `? super Integer`.
4. **Tìm các quan hệ bắt buộc:** nếu giá trị trả về phải giữ kiểu từ tham số, hoặc nguồn và đích phải tuân thủ quan hệ nào đó, khai báo một tên `<T>` hay `<T,R>`.
5. **Thay các biến kiểu chỉ dùng cho độ linh hoạt:** khi một `S extends T` chỉ có mặt tại một parameterized argument và không góp vào quan hệ khác, cân nhắc viết `? extends T` / `? super T`.
6. **Dùng wildcard capture helper khi cần:** API ngoài có thể nhận `<?>` còn helper bên trong dùng `<T>` để thao tác giữa những phần tử cùng capture.
7. **Biên dịch đúng call site thật:** kiểm tra những lời gọi quan trọng, compiler diagnostics và `javac -Xlint:unchecked`; đừng kết luận chỉ từ một ví dụ lý tưởng.

Bảng quyết định nhanh:

| Tình huống | Lựa chọn | Vì sao |
| --- | --- | --- |
| `print(List<...>)` không quan tâm loại | `List<?>` | Không cần tên kiểu. |
| `sum(List<...>)` chỉ đọc số | `List<? extends Number>` | Đủ bảo đảm `Number`. |
| `fill(List<...>)` chỉ thêm Integer | `List<? super Integer>` | Consumer nhận các `Integer`. |
| `first(...)` trả về loại phần tử đầu vào | `<T> T first(List<T>)` | Nối input và return. |
| `append(source,target)` | `<T> void append(List<? extends T>,List<? super T>)` | Nối source và target. |
| `swap(List<?>)` không muốn lộ kiểu | API `List<?>` + helper `<T>` | Capture cùng kiểu cho `get`/`set`. |
| `map(source,mapper)` trả result kiểu mới | `<T,R>` + wildcard ở source/mapper | Nối source, chuyển đổi, kết quả. |

## 10. Lỗi thường gặp, triệu chứng và hướng sửa

### Lỗi 1 — Dùng `<T>` không mang ý nghĩa

~~~java
static <T> int size(List<T> values) {
    return values.size();
}
~~~

Có thể dùng `static int size(List<?> values)`. `T` ở đây chỉ làm code dài hơn, không bảo toàn quan hệ hữu ích nào.

### Lỗi 2 — Dùng `<?>` rồi mong trả về `T` cụ thể

~~~java
static Object firstUnknown(List<?> values) {
    return values.get(0);
}

// String name = firstUnknown(List.of("Lan")); // KHÔNG biên dịch.
~~~

Nếu cần trả đúng loại, viết `<T> T first(List<T>)`. **Cast xuống subtype** sau khi nhận `Object` không thay thế bằng chứng tĩnh được cung cấp bởi generic method.

### Lỗi 3 — Dùng `extends` tại đích cần ghi

~~~java
static void brokenAdd(List<? extends Number> target) {
    target.add(10); // KHÔNG biên dịch.
}
~~~

Đổi sang `List<? super Integer>` nếu chỉ thêm `Integer`, hoặc dùng `List<Number>` nếu hợp đồng thực sự yêu cầu list phần tử `Number`.

### Lỗi 4 — Dùng `super` tại nguồn cần đọc Number

~~~java
static double brokenSum(List<? super Number> values) {
    double result = 0;
    for (Number n : values) { // KHÔNG biên dịch: phần tử đọc ra chỉ bảo đảm Object.
        result += n.doubleValue();
    }
    return result;
}
~~~

Đổi sang `List<? extends Number>` nếu dùng các phần tử như `Number`.

### Lỗi 5 — Biến mỗi kiểu wildcard thành một `T` duy nhất

Nếu hai tham số **không liên quan**, không nên buộc chúng dùng chung `T`:

~~~java
static void printPairSizes(List<?> left, List<?> right) {
    System.out.println(left.size() + ":" + right.size());
}
~~~

Hàm có thể nhận `List<String>` cùng `List<Integer>`. Không cần ép chúng vào chung một type argument.

### Lỗi 6 — Chữa lỗi kiểu bằng raw `List` hoặc unchecked cast

~~~java
// Cảnh báo/rủi ro: raw type che thông tin kiểu.
List raw = new ArrayList<String>();
List<Integer> ints = raw; // Unchecked conversion.
~~~

Thao tác này không tạo quan hệ subtype đúng và có thể dẫn đến `ClassCastException` khi đọc. Thiết kế lại chữ ký bằng wildcard và type parameter thích hợp, hoặc kiểm tra dữ liệu tại boundary của legacy API.

### Lỗi 7 — Nhầm thông tin của type parameter với giới hạn runtime

Do **type erasure**, `List<String>` và `List<Integer>` không giữ type arguments cụ thể để có thể kiểm tra bằng `instanceof List<String>`. Named `T` giúp **compiler** xác minh quan hệ kiểu; không phải một “bằng chứng runtime” tự động. Nếu cần runtime validation, kiểm tra phần tử thực tế hoặc dùng `Class<T>` token khi phù hợp.

## 11. Ôn tập

1. Muốn in `size()` của mọi list, nên chọn `<T> void f(List<T>)` hay `void f(List<?>)`? **`List<?>`** đơn giản, không đánh mất mối quan hệ cần thiết.
2. Muốn tính tổng `List<Integer>` lẫn `List<Double>` mà chỉ cần `Number.doubleValue()`? **`List<? extends Number>`**.
3. Muốn ghi `Integer` vào `List<Integer>`, `List<Number>` hoặc `List<Object>`? **`List<? super Integer>`**.
4. Vì sao `<T> T first(List<T>)` cần `T`? **Để loại của kết quả liên hệ với loại phần tử đầu vào tại cùng một lời gọi.**
5. Vì sao `appendAll(List<?>, List<?>)` không đủ để chèn phần tử? **Hai kiểu wildcard không được chứng minh có quan hệ producer/consumer; cần type parameter chung để nối hai vị trí.**
6. Vì sao API `swapEnds(List<?>)` vẫn có thể cần helper `<T>`? **Để capture một kiểu phần tử chưa biết và dùng cùng một tên `T` ở cả hai thao tác đọc/ghi.**
7. Có phải `<T>` đảm bảo mọi argument ở runtime cùng một class? **Không.** Type inference có thể chọn một supertype chung.
8. Quy tắc “`T` dùng một lần thì đổi thành `?`” có luôn đúng không? **Không tuyệt đối.** Hãy tìm xem `T` có góp vào bound/return type/quan hệ khác hay ràng buộc của API hiện có không.

## 12. Tài liệu tham khảo

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): giải thích wildcard, type-argument containment và ví dụ khi một type parameter dùng một lần nên thay bằng wildcard.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): cơ sở để chuyển kiểu chưa biết của wildcard thành type variable tạm thời.
- [Oracle Java Tutorials — Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): lựa chọn `extends`/`super` theo producer/consumer và lưu ý với method return types.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): lý do dùng helper generic để nắm bắt wildcard.
- [Java SE 17 API — Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): chữ ký chuẩn kết hợp `<T>`, `? super T` và `? extends T`.
- [Java SE 17 API — Collection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)): `Collection<? extends E>` trong một interface đã đặt tên `E`.
