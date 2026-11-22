# Xác định vai trò đọc–ghi của từng tham số theo quy tắc PECS

## 1. Vì sao cần xác định vai trò của tham số?

Khi thiết kế API Java Generics, hai phương thức đều nhận `List<T>` có thể sử dụng danh sách theo cách rất khác nhau: một phương thức chỉ lấy phần tử ra để tính toán, còn phương thức kia chỉ nhận các phần tử mới được ghi vào. Viết tham số là `List<T>` trong mọi trường hợp có thể khiến API từ chối những danh sách hoàn toàn phù hợp với công việc thực tế.

**PECS** là quy tắc lựa chọn wildcard dựa trên vai trò của từng tham số:

- **Producer Extends**: nguồn **cung cấp giá trị kiểu `T` cho thuật toán** → cân nhắc `? extends T`.
- **Consumer Super**: đích **nhận các giá trị kiểu `T` từ thuật toán** → cân nhắc `? super T`.

Đây là quy tắc về **hướng di chuyển của giá trị đối với thuật toán đang viết**, chứ không đơn giản là tham số đứng ở vị trí đầu hay cuối chữ ký, hoặc có được truyền vào phương thức hay không.

Ví dụ:

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) { // Đọc T từ source
        destination.add(element); // Ghi T vào destination
    }
}
```

Trong ví dụ này, `source` là producer dù nó được **truyền vào** phương thức; `destination` là consumer dù nó cũng được **truyền vào** phương thức. Đọc–ghi phải được nhìn từ **bên trong hoạt động của thuật toán**.

## 2. Quy trình xác định vai trò của từng tham số

Với mỗi tham số generic, hãy thực hiện lần lượt:

1. **Xác định kiểu giá trị `T` đang trao đổi.** Đây có thể là `Number`, `String`, `Animal` hoặc tham số kiểu `<T>` được khai báo trên phương thức.
2. **Đọc thân phương thức theo luồng dữ liệu.** Giá trị `T` được **lấy từ** tham số hay được **đưa vào** tham số?
3. **Tách các thao tác phụ khỏi thao tác chính.** `size()`, `isEmpty()` và `contains(Object)` không cung cấp hoặc nhận một giá trị có kiểu phần tử `T` theo cách PECS quan tâm.
4. **Xét quyền cần thiết:** nếu chỉ lấy `T` ra, chọn `? extends T`; nếu chỉ cung cấp `T` cho đích, chọn `? super T`; nếu cần cả đọc và ghi `T` chính xác, xem xét `List<T>` và một tham số kiểu có tên.
5. **Thử lời gọi với các kiểu con/kiểu cha.** Kiểm tra một `List<Integer>` có thể làm nguồn cho phép đọc `Number`; kiểm tra một `List<Object>` có thể làm đích nhận `Integer`.
6. **Đừng vượt quá cam kết của wildcard.** `extends` không bảo đảm danh sách immutable; `super` không bảo đảm giá trị đọc ra là `T`; cả hai vẫn phụ thuộc khả năng sửa đổi thực tế của implementation.

Một bảng quyết định ban đầu:

| Cách tham số được dùng trong phương thức | Vai trò | Lựa chọn điển hình |
|---|---|---|
| Chỉ đọc phần tử dưới kiểu `T` | Producer | `List<? extends T>` |
| Chỉ đưa giá trị `T` vào danh sách | Consumer | `List<? super T>` |
| Vừa đọc phần tử như `T`, vừa ghi phần tử `T` | Cả hai | `List<T>` hoặc thiết kế `<T>` thích hợp |
| Chỉ kiểm tra số lượng, in thông tin chung, không cần kiểu `T` | Không phụ thuộc kiểu phần tử | `List<?>` |
| Cần bảo toàn một quan hệ kiểu giữa nhiều tham số và kết quả | Phụ thuộc hợp đồng | Kết hợp `<T>` với wildcard ở từng vị trí |

Bảng là hướng dẫn thiết kế, **không phải quy tắc đổi chữ ký máy móc**. Chẳng hạn, `List<? extends T>` vẫn có thể gọi `clear()`, và `List<? super T>` vẫn có thể đọc `Object`. Thuật ngữ producer/consumer nhấn mạnh việc **cung cấp hay nhận giá trị của kiểu `T`**.

## 3. Xác định producer từ các thao tác đọc

Giả sử một phương thức cần tính tổng danh sách số:

```java
static double total(List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Phân tích:

- `values` cung cấp từng phần tử bằng `iterator()`/`get()`.
- Phương thức coi mỗi phần tử là `Number` và gọi `doubleValue()`; nó không tạo một phần tử `Number` mới để đưa vào `values`.
- Do đó `values` đóng vai trò **producer của `Number`**. `List<? extends Number>` chấp nhận `List<Number>`, `List<Integer>`, `List<Double>` và các `List<S>` với `S extends Number`.

Nếu khai báo `List<Number>`, lời gọi `total(List<Integer>)` sẽ **không** biên dịch do Generics bất biến (*invariance*), dù `Integer` là lớp con của `Number`.

```java
List<Integer> counts = List.of(2, 3);
List<Double> measurements = List.of(1.5, 2.5);

double a = total(counts);       // 5.0
double b = total(measurements); // 4.0
```

Với `List<? extends Number>`, giá trị đọc từ danh sách có thể dùng như `Number`; nhưng compiler **không cho thêm một `Integer` hoặc `Double` tùy ý vào nó**. Kiểu phần tử ẩn có thể là bất kỳ kiểu con nào của `Number`.

```java
static void inspect(List<? extends Number> values) {
    Number first = values.get(0); // Hợp kiểu, cần danh sách không rỗng
    // values.add(1);              // Không biên dịch
    // values.add(1.5);            // Không biên dịch
}
```

**Lưu ý:** Nếu thuật toán chỉ cần `size()` hoặc in mọi phần tử như `Object`, `List<?>` có thể truyền đạt chính xác mục đích hơn `List<? extends Number>` vì không cần ràng buộc dữ liệu phải là số.

## 4. Xác định consumer từ các thao tác ghi

Xét một phương thức đưa hai số nguyên vào danh sách do bên gọi cung cấp:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Phân tích:

- Thân phương thức **tạo ra** hai giá trị `Integer`.
- `destination` **nhận** chúng bằng `add`.
- Do đó `destination` là **consumer của `Integer`**, phù hợp `List<? super Integer>`.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addDefaults(integers); // Được
addDefaults(numbers);  // Được
addDefaults(objects);  // Được
```

Ba đối số phù hợp vì `Integer` gán được cho `Integer`, `Number` và `Object`. Ngược lại, `List<Double>` không phù hợp với `? super Integer` vì `Double` **không phải kiểu cha của `Integer`**.

Điểm đánh đổi là giá trị được lấy ra từ biến có kiểu `List<? super Integer>` chỉ bảo đảm kiểu tĩnh `Object`:

```java
static void demoReadingConsumer(List<? super Integer> values) {
    Object element = values.get(0); // Hợp kiểu
    // Integer integer = values.get(0); // Không biên dịch
}
```

Điều này hợp lý: một `List<Object>` có thể đã chứa `String` hoặc một đối tượng không phải `Integer` từ trước. Chữ ký consumer chỉ cam kết **đủ rộng để nhận `Integer`**, không cam kết mọi phần tử đang có đều là `Integer`.

`null` có thể được thêm ở mức kiểm tra kiểu với cả `? extends T` và `? super T` vì null tương thích mọi kiểu tham chiếu. Tuy nhiên việc thao tác có thành công lúc chạy hay không phụ thuộc danh sách có cho phép mutation và null. Không dùng khả năng thêm null để kết luận vai trò PECS.

## 5. Khi tham số vừa được đọc vừa được ghi

Một số thao tác **thay thế hoặc biến đổi giá trị cùng kiểu** cần đọc `T` từ danh sách và ghi một giá trị `T` vào chính danh sách ấy. Ví dụ tăng mỗi số nguyên:

```java
static void increment(List<Integer> values) {
    for (int i = 0; i < values.size(); i++) {
        Integer oldValue = values.get(i); // Đọc Integer
        values.set(i, oldValue + 1);      // Ghi Integer
    }
}
```

Ở đây, nếu thay `List<Integer>` thành `List<? extends Integer>` thì có thể đọc dưới kiểu `Integer` nhưng không thể ghi một `Integer` mới. Nếu thay bằng `List<? super Integer>` thì ghi được `Integer` nhưng `get(i)` chỉ an toàn dưới kiểu `Object`. Với đúng hợp đồng “**đọc và ghi lại Integer**”, `List<Integer>` thể hiện quyền cần thiết.

Với thuật toán tổng quát áp dụng một hàm biến đổi giá trị cùng kiểu:

```java
static <T> void transformInPlace(
        List<T> values,
        java.util.function.UnaryOperator<T> transform) {
    for (int i = 0; i < values.size(); i++) {
        T current = values.get(i);
        values.set(i, transform.apply(current));
    }
}
```

Chọn `List<T>` vì phải đọc và ghi **cùng một `T`**. Phương thức không buộc tất cả danh sách phải có tham số kiểu `Object`; `T` được suy luận riêng cho từng lời gọi. Ví dụ `List<String>` và `UnaryOperator<String>` hoàn toàn phù hợp.

Có một ngoại lệ đáng học: **hoán đổi hoặc sao chép trở lại chính các phần tử đã đọc** có thể thực hiện an toàn bằng một helper bắt kiểu wildcard (*wildcard capture*):

```java
static void swapFirstTwo(List<?> values) {
    swapCaptured(values);
}

private static <T> void swapCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

Helper giữ một kiểu `T` ẩn duy nhất cho cả đọc và ghi; nó **không tự tạo một đối tượng `T` mới thuộc kiểu tùy ý**. Đây là tình huống dùng tham số kiểu có tên để kết nối thao tác an toàn, thay vì ép kiểu thô.

## 6. Xác định vai trò riêng của từng tham số trong cùng một phương thức

Một phương thức có thể có nhiều tham số, mỗi tham số thực hiện một vai trò khác nhau. Phân tích **từng vị trí** theo thao tác trên dữ liệu, thay vì áp dụng một wildcard giống nhau cho tất cả.

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
```

Luồng dữ liệu là:

```text
source: List<? extends T>
           │ đọc T
           ▼
        element: T
           │ ghi T
           ▼
destination: List<? super T>
```

- Tham số `source` là **producer**. Có thể lấy từng `T` từ danh sách thực sự có phần tử kiểu `T` hoặc kiểu con.
- Tham số `destination` là **consumer**. Có thể thêm `T` vào danh sách thực sự có kiểu phần tử là `T` hoặc kiểu cha.
- Tham số kiểu có tên `<T>` **liên kết cả hai đầu** để compiler kiểm tra quan hệ kiểu chung.

Ví dụ:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyValues(integers, numbers); // Integer được nhận qua Number
copyValues(integers, objects); // Integer được nhận qua Object
copyValues(numbers, objects);  // Number được nhận qua Object
```

Dù `Integer` là kiểu con của `Number`, `List<Integer>` không phải kiểu con của `List<Number>`. Chính hai wildcard trong **chữ ký phương thức** giúp những lời gọi này được kiểm tra an toàn, không phải Java đã thay đổi quy tắc invariance.

Một `List<? super T>` dùng làm đích có thể đã chứa giá trị thuộc nhiều kiểu con khác nhau. Không suy luận rằng mọi giá trị đọc ra từ đích là `T`.

## 7. Ví dụ Java 17 hoàn chỉnh: ba vai trò trong một API

Tạo tệp `PecsParameterRolesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Predicate;

public class PecsParameterRolesDemo {
    static <T> void copyMatching(
            Iterable<? extends T> source,
            Collection<? super T> destination,
            Predicate<? super T> filter) {
        for (T element : source) {
            if (filter.test(element)) {
                destination.add(element);
            }
        }
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number element : source) {
            total += element.doubleValue();
        }
        return total;
    }

    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static <T> void replaceFirst(List<T> values, T replacement) {
        if (!values.isEmpty()) {
            values.set(0, replacement);
        }
    }

    static void showCount(List<?> values) {
        System.out.println("Input size: " + values.size());
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(1, 2, 3, 4);
        List<Number> selected = new ArrayList<>();
        Predicate<Number> isEven =
                value -> value.intValue() % 2 == 0;

        copyMatching(input, selected, isEven);
        System.out.println("Selected: " + selected);
        System.out.println("Sum: " + sum(selected));

        List<Object> events = new ArrayList<>();
        addDefaults(events);
        System.out.println("Events: " + events);

        replaceFirst(selected, 99);
        System.out.println("After replace: " + selected);

        showCount(input);
    }
}
```

Chạy trong thư mục chứa tệp (JDK 17 trở lên):

```bash
javac PecsParameterRolesDemo.java
java PecsParameterRolesDemo
```

**Stdout:**

```text
Selected: [2, 4]
Sum: 6.0
Events: [10, 20]
After replace: [99, 4]
Input size: 4
```

Cách phân tích từng tham số:

| Tham số | Thao tác trực tiếp | Vai trò với `T` | Chữ ký |
|---|---|---|---|
| `copyMatching.source` | Đọc `T` từ vòng lặp | Producer | `Iterable<? extends T>` |
| `copyMatching.destination` | `add(element)` | Consumer | `Collection<? super T>` |
| `copyMatching.filter` | `test(element)`: nhận `T` | Consumer | `Predicate<? super T>` |
| `sum.source` | Đọc `Number` và tính `doubleValue()` | Producer | `List<? extends Number>` |
| `addDefaults.destination` | `add(Integer)` | Consumer | `List<? super Integer>` |
| `replaceFirst.values` | `get()` và `set()` với cùng `T` | Đọc và ghi | `List<T>` |
| `showCount.values` | `size()` | Không cần `T` | `List<?>` |

**Giải thích các điểm dễ nhầm:**

1. `filter` cũng là **consumer**, mặc dù `Predicate.test` không ghi một phần tử vào danh sách: nó **nhận một giá trị `T` làm đầu vào** để kiểm tra. Do đó `Predicate<Number>` có thể làm bộ lọc cho các phần tử `Integer`.
2. `source` là `Iterable<? extends T>` vì thuật toán chỉ cần khả năng duyệt phần tử; không cần buộc nguồn cung cấp `get(index)` hoặc `List`. Đây là cách chọn interface vừa đủ cho hợp đồng.
3. `destination` dùng `Collection<? super T>` vì chỉ cần `add`, không cần thao tác theo chỉ số. Đích có thể là `List<Number>` dù nguồn là `List<Integer>`.
4. `replaceFirst` sử dụng `List<T>` vì cần đọc và ghi đúng cùng một kiểu `T`. `selected` là `List<Number>`, nên ghi `Integer 99` hợp lệ qua quan hệ `Integer extends Number`.
5. `input` được tạo bởi `List.of(...)` (không sửa đổi được), nhưng chỉ đóng vai trò nguồn nên chương trình không cố thay đổi nó. `selected` và `events` dùng `ArrayList` để cho phép `add` và `set`.

Cần phân biệt kiểm tra **kiểu tĩnh** với runtime. Nếu đưa một đích không sửa đổi được vào `copyMatching`, lời gọi vẫn có thể biên dịch nhưng `destination.add` có thể ném `UnsupportedOperationException`. PECS giúp xác định kiểu nào **được phép nhận**, không tự cấp khả năng sửa dữ liệu cho implementation.

## 8. Nhìn PECS trong các callback và interface chức năng

PECS không chỉ dành cho `List`. Với một tham số kiểu `T`, hãy xem một đối tượng hàm **nhận `T`** hay **cung cấp `T`**.

### `Predicate<? super T>`: một consumer của `T`

`Predicate<T>.test(T value)` nhận một giá trị kiểu `T` và trả về boolean. Nếu thuật toán có phần tử `Integer`, một `Predicate<Number>` vẫn có thể kiểm tra nó như `Number`:

```java
static <T> long countMatching(
        List<? extends T> source,
        java.util.function.Predicate<? super T> condition) {
    long count = 0;
    for (T item : source) {
        if (condition.test(item)) {
            count++;
        }
    }
    return count;
}
```

Đoạn phương thức này là ví dụ độc lập về chữ ký; để biên dịch cần đặt trong một lớp và import `java.util.List`. `source` cung cấp `T`, còn `condition` nhận `T` nên áp dụng hai hướng wildcard khác nhau.

### `Comparator<? super T>`: nhận hai giá trị `T` để so sánh

`List<E>.sort` có chữ ký nhận `Comparator<? super E>`. Comparator không sinh ra `E`; nó **nhận các `E` làm đối số của `compare`**, nên là consumer.

```java
List<Integer> values = new ArrayList<>(List.of(30, 2, 11));
java.util.Comparator<Number> byValue =
        java.util.Comparator.comparingDouble(Number::doubleValue);

values.sort(byValue);
System.out.println(values); // [2, 11, 30]
```

Đây là đoạn minh họa có thể đặt trong `main` với import `java.util.List` và `java.util.ArrayList`. Việc dùng `Comparator<Number>` để sắp xếp `List<Integer>` là hợp lệ vì `Number` có thể nhận mọi `Integer`.

### `Function<? super T, ? extends R>`: có cả đầu vào và đầu ra

`Function<A,B>` **tiêu thụ** một `A` qua `apply(A)` và **sản xuất** một `B` làm kết quả. Vì vậy, trong một API biến đổi `T` sang `R`, có thể chọn:

```java
static <T, R> List<R> map(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

Ví dụ `source` cung cấp `Integer`; một `Function<Number,String>` nhận `Integer` và trả `String` phù hợp. Ở callback, cận dưới cho **đầu vào**, cận trên cho **đầu ra**; cả hai đều bắt nguồn từ hướng dữ liệu đối với thuật toán.

Lưu ý các đoạn `Comparator` và `map` minh họa API trong một lớp Java phù hợp, không phải chương trình độc lập nếu đứng riêng. Chương trình hoàn chỉnh ở mục 7 đã có tệp và stdout xác định.

## 9. Phân biệt `add`, `set`, `get` với thao tác không xác định vai trò

Khi đọc một phương thức, đừng gắn nhãn “consumer” chỉ vì có thao tác **thay đổi dữ liệu**. PECS quan tâm đến dòng giá trị thuộc kiểu `T`:

| Lời gọi | Liên quan đến `T` thế nào? | Ý nghĩa khi chọn wildcard |
|---|---|---|
| `T x = list.get(i)` | Lấy ra `T` | Producer |
| `for (T x : list)` | Lấy ra `T` | Producer |
| `list.add(valueOfTypeT)` | Đưa `T` vào | Consumer |
| `list.set(i, valueOfTypeT)` | Đưa `T` vào vị trí | Consumer, đồng thời cần xem có đọc `T` hay không |
| `list.size()` | Không trao đổi `T` | Không quyết định PECS |
| `list.isEmpty()` | Không trao đổi `T` | Không quyết định PECS |
| `list.contains(anyObject)` | Nhận `Object`, không đòi `T` | Không đủ để kết luận consumer `T` |
| `list.remove(anyObject)` | Nhận `Object` để tìm/xóa | Không đủ để kết luận consumer `T` |
| `list.remove(index)` | Xóa theo chỉ số, có thể trả phần tử `T` | Nếu dùng kết quả như `T` thì có khía cạnh producer |
| `list.clear()` | Xóa hết, không cần cung cấp `T` | Không biến nó thành consumer `T` |

Ví dụ `List<? extends Number>` **có thể** gọi `remove` hoặc `clear()` về mặt kiểm tra kiểu, dù không thêm được `Integer` cụ thể. Khi gọi trên danh sách không cho sửa, những thao tác đó có thể thất bại tại runtime. Vì thế producer không đồng nghĩa “immutable”.

Tương tự, một `List<? super Integer>` có thể gọi `get`, nhưng chỉ đọc an toàn dưới kiểu `Object`. Consumer không có nghĩa “không thể đọc bất cứ gì”.

### Cẩn thận với overload `remove`

`List` có cả `remove(int index)` và `remove(Object o)`:

```java
List<Integer> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);                  // Xóa phần tử tại chỉ số 1
values.remove(Integer.valueOf(30)); // Xóa đối tượng có giá trị 30
```

Nếu đọc phương thức có `remove(1)`, đây là thao tác xóa theo vị trí, không phải “ghi giá trị Integer 1 vào danh sách”. Kiểm tra overload thực tế trước khi phân tích vai trò.

## 10. Khi nào giữ nguyên `List<T>` thay vì wildcard?

PECS là gợi ý tối ưu hợp đồng ở vị trí **chỉ đọc** hoặc **chỉ ghi**. Không nên ép dùng wildcard nếu làm mất một quan hệ kiểu quan trọng.

### Cần đọc và ghi cùng `T`

```java
static <T> void replaceAll(
        List<T> values,
        java.util.function.UnaryOperator<T> op) {
    values.replaceAll(op);
}
```

`List<T>` và `UnaryOperator<T>` biểu thị cùng một kiểu cho đầu vào và kết quả của phép biến đổi. Sử dụng `List<? extends T>` ở vị trí `values` có thể làm việc ghi lại một `T` bất kỳ trở nên không hợp lệ; `List<? super T>` làm mất bảo đảm đọc như `T`.

### Cần một kết quả giữ nguyên kiểu của đầu vào

```java
static <T> T firstOrNull(List<T> values) {
    return values.isEmpty() ? null : values.get(0);
}
```

`firstOrNull(List<String>)` trả về kiểu tĩnh `String`. Nếu dùng `List<?>` và trả về `Object`, bên gọi sẽ mất quan hệ kiểu này. Tuy vậy, có thể dùng một số thiết kế tương đương với `? extends T` tùy nhu cầu suy luận và chữ ký; điểm cần giữ là **type parameter `T` liên hệ đầu vào với đầu ra**.

### Chỉ cần thao tác không phụ thuộc kiểu phần tử

```java
static boolean hasElements(List<?> values) {
    return !values.isEmpty();
}
```

Vì không tạo hay lấy kết quả thuộc một kiểu `T` cần được đặt tên, wildcard không giới hạn `<?>` là hợp đồng đơn giản hơn việc thêm `<T>` không dùng đến.

## 11. Đọc vai trò tham số trong `Collections.copy`

Một ví dụ đáng chú ý khi phân tích **vai trò theo vị trí** là chữ ký của thư viện chuẩn:

```java
static <T> void copy(List<? super T> dest, List<? extends T> src)
```

Trong `Collections.copy(dest, src)`, **tham số đứng trước `dest` là consumer**, còn tham số thứ hai `src` là producer. Điều này ngược với thói quen đặt `source` trước của nhiều helper tự viết: vị trí không quyết định PECS, **thao tác trên giá trị `T` mới quyết định**.

Phương thức dùng `set` để **ghi đè các phần tử đã có**, không `add` để tăng kích thước. Ví dụ với đích `[0, 0, 0]` và nguồn `[7, 8]`, kết quả là `[7, 8, 0]`; nếu đích ngắn hơn nguồn, nó ném `IndexOutOfBoundsException`. Danh sách đích không hỗ trợ thay đổi có thể ném `UnsupportedOperationException`. Các điều kiện này không do wildcard quyết định.


## 12. Một ví dụ sai và cách sửa chữ ký

Giả sử ta muốn gom mọi `Number` từ nguồn vào một danh sách đích:

```java
static void collectWrong(
        List<Number> source,
        List<Number> target) {
    for (Number n : source) {
        target.add(n);
    }
}
```

Phương thức trên biên dịch, nhưng `List<Integer>` không thể truyền vào `source` và `List<Object>` không thể truyền vào `target`. Chữ ký đang giới hạn hơn mức thuật toán yêu cầu.

Quan sát thân hàm:

1. `source` chỉ được đọc qua vòng lặp, cần bảo đảm mỗi giá trị có thể dùng dưới kiểu `Number`.
2. `target` chỉ nhận các giá trị `Number` được lấy từ nguồn, không cần đọc chúng trở lại dưới kiểu `Number`.

Sửa:

```java
static void collectNumbers(
        List<? extends Number> source,
        List<? super Number> target) {
    for (Number n : source) {
        target.add(n);
    }
}
```

Với chữ ký này:

```java
List<Integer> input = List.of(1, 2);
List<Object> output = new ArrayList<>();
collectNumbers(input, output);
System.out.println(output); // [1, 2]
```

Đoạn mẫu cần import `java.util.List` và `java.util.ArrayList`, đặt vào một lớp để biên dịch. Quy tắc sửa là **nới đúng vai trò của từng tham số** nhưng vẫn giữ cận `Number` cho các phép đọc/ghi số.

Không cần chuyển thành raw `List`: raw type bỏ qua kiểm tra tham số kiểu và có thể gây *heap pollution*. Wildcard giữ hợp đồng có thể kiểm tra tại compile time.

## 13. Những bẫy khi phân tích vai trò đọc–ghi

**Bẫy 1 — “Tham số truyền vào là input nên phải dùng `extends`.”** Sai. Trong Java, mọi tham số đều đi vào phương thức, nhưng một tham số có thể đại diện nơi thuật toán ghi kết quả. `destination` thường là consumer `<? super T>`.

**Bẫy 2 — “Producer là danh sách immutable.”** Sai. Producer là vai trò cung cấp dữ liệu cho thuật toán. `List<? extends T>` không ngăn `remove`, `clear` hoặc một số thao tác khác; khả năng sửa đổi do đối tượng thực quyết định.

**Bẫy 3 — “Consumer là không đọc được.”** Sai. `List<? super T>` vẫn đọc được dưới kiểu `Object`, nhưng không bảo đảm mọi phần tử là `T`. Nếu thuật toán cần đọc ra như `T`, hãy xét lại chữ ký.

**Bẫy 4 — “Hễ có `set` là chỉ consumer.”** Chưa đủ. `set` cung cấp một giá trị cho đích, nhưng nếu thuật toán cũng cần đọc giá trị cùng kiểu `T` từ tham số ấy, tham số có cả hai vai trò. Ví dụ `transformInPlace` dùng `List<T>`.

**Bẫy 5 — “`contains` và `remove(Object)` biến tham số thành consumer của `T`.”** Không nhất thiết. Những phương thức này nhận `Object`; cần xem thuật toán có thực sự đưa giá trị kiểu `T` vào vị trí lưu trữ hay không.

**Bẫy 6 — “Mọi interface chức năng chỉ là producer vì trả về một kết quả.”** Sai. `Predicate<T>` và `Comparator<T>` nhận giá trị kiểu `T` nên là consumer của `T`, dù chúng trả về `boolean` hoặc `int`.

**Bẫy 7 — “Một `Function` có cùng vai trò cho cả hai tham số kiểu.”** Sai. `Function<A,B>` nhận `A` và trả `B`; trong ngữ cảnh chuyển đổi, đó thường là `Function<? super A, ? extends B>`.

**Bẫy 8 — “PECS chứng minh chương trình sẽ chạy an toàn trong mọi tình huống.”** Không. Nó kiểm tra **tương thích kiểu**. `IndexOutOfBoundsException`, `UnsupportedOperationException`, `NullPointerException`, dữ liệu không hợp lệ, và các lỗi nghiệp vụ vẫn có thể xảy ra.

## 14. Bài tự kiểm tra vai trò của từng tham số

Với mỗi chữ ký sau, hãy xác định producer, consumer hay cần một kiểu `T` chung:

```java
// A
static double average(List<? extends Number> data);

// B
static void collect(List<? super Integer> target, int value);

// C
static <T> void copy(
        List<? extends T> from,
        List<? super T> to);

// D
static <T> void update(
        List<T> values,
        java.util.function.UnaryOperator<T> change);

// E
static boolean exists(List<?> items);

// F
static <T> long count(
        Iterable<? extends T> input,
        java.util.function.Predicate<? super T> condition);
```

Đây là **chữ ký bài tập**, không phải các phương thức đã có thân và không phải tệp Java biên dịch độc lập.

**Đáp án:**

- **A:** `data` là producer của `Number` vì `average` đọc các giá trị để tính toán; không cần ghi số vào nguồn.
- **B:** `target` là consumer của `Integer` vì nhận giá trị `int` được boxing thành `Integer`. Tham số `value` là một giá trị số, không phải cấu trúc generic cần wildcard.
- **C:** `from` là producer `T`, `to` là consumer `T`; tham số kiểu `<T>` nối hai vai trò.
- **D:** `values` vừa đọc vừa ghi `T`, nên dùng `List<T>`. `change` nhận `T` và trả lại `T`; `UnaryOperator<T>` phản ánh việc biến đổi cùng kiểu.
- **E:** `items` chỉ dùng để hỏi “có phần tử không?”, không cần biết kiểu phần tử; `List<?>` là đủ.
- **F:** `input` là producer của `T`. `condition` nhận từng `T` qua `test` nên là consumer của `T`, dù kết quả `boolean` được dùng để đếm.

Có thể tự kiểm tra thêm bằng cách thay `T = Number` hoặc `T = Integer`, rồi thử đưa `List<Integer>` vào nơi đọc và `List<Object>` vào nơi ghi. Nếu thay `extends` bằng `super` làm hỏng kiểu đọc, hoặc ngược lại, đó là dấu hiệu cần xem lại vai trò.

## 15. Checklist khi thiết kế chữ ký PECS

Trước khi công bố một phương thức generic, hãy trả lời:

1. **Thuật toán đọc những giá trị thuộc kiểu nào?** Nếu nhận giá trị `T` từ tham số, tham số đó thường là producer.
2. **Thuật toán ghi những giá trị thuộc kiểu nào?** Nếu truyền `T` vào tham số, tham số đó thường là consumer.
3. **Tham số nào cần giữ quan hệ cùng kiểu?** Nếu một giá trị đọc phải được ghi lại hoặc trả về với đúng kiểu đó, cân nhắc `<T>` và `List<T>`.
4. **Có tham số nào chỉ gọi thao tác chung?** Nếu không phụ thuộc kiểu phần tử, `<?>` giúp tránh ràng buộc thừa.
5. **Interface tham số đã đủ hẹp chưa?** Nếu chỉ duyệt, `Iterable<? extends T>` có thể đủ; nếu chỉ thêm, `Collection<? super T>` thường đủ; không cần mặc định `List`.
6. **Các kiểu con và cha có được chấp nhận như dự kiến?** Thử các lời gọi `List<Integer>` → `List<Number>` hoặc `List<Object>` mà không dùng raw type.
7. **Các yêu cầu runtime đã rõ chưa?** Với nơi ghi, caller cần truyền collection hỗ trợ mutation; với `Collections.copy`, đích phải có đủ phần tử sẵn có; với dữ liệu null, cần hợp đồng riêng.

Một chữ ký tốt thể hiện **đúng quyền đọc–ghi mà thân phương thức cần**, không trao quyền ghi vào nguồn hay bắt buộc đích phải có đúng kiểu phần tử nếu điều đó không cần thiết.

## 16. Ghi nhớ

PECS là phương pháp **xem mỗi tham số generic đang cung cấp hay nhận giá trị kiểu `T`**. Dùng **`? extends T`** cho tham số cung cấp `T`; dùng **`? super T`** cho tham số nhận `T`. Nếu cả đọc và ghi cùng một kiểu, dùng một tham số kiểu có tên để giữ quan hệ; nếu kiểu phần tử không tham gia thuật toán, `<?>` có thể là lựa chọn rõ ràng nhất.

Mục tiêu của PECS là làm API linh hoạt với các kiểu con/kiểu cha cần thiết **mà vẫn an toàn kiểu tại thời điểm biên dịch**, chứ không chỉ thay vài từ khóa trong chữ ký.