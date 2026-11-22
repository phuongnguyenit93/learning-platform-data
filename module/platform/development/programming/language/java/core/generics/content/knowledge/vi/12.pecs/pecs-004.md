# Khi cùng tham số vừa cung cấp vừa nhận dữ liệu: áp dụng PECS thế nào?

## 1. Bài toán và quy tắc cốt lõi

Quy tắc **PECS** (*Producer Extends, Consumer Super*) giúp chọn wildcard trong Java Generics:

- Một tham số **cung cấp** phần tử để đọc theo kiểu `T` (*producer*) thường thích hợp với `? extends T`.
- Một tham số **nhận** phần tử kiểu `T` để ghi (*consumer*) thường thích hợp với `? super T`.

Nhưng nếu **cùng một tham số**, chẳng hạn cùng một `List`, vừa cung cấp phần tử để đọc vừa nhận phần tử cùng kiểu để ghi, không nên máy móc chọn một trong hai wildcard. Khi cần gắn chặt kiểu phần tử được đọc với kiểu phần tử sẽ ghi, hãy ưu tiên **tham số kiểu được đặt tên**:

```java
static <T> void replaceFirst(List<T> values, T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

Trong chữ ký này, `T` xuất hiện ở cả `List<T>` và `T replacement`, buộc kiểu của giá trị thay thế tương thích với kiểu phần tử của danh sách. Với những phép biến đổi lấy phần tử ra rồi ghi trở lại, có thể dùng `List<T>`, `UnaryOperator<T>` hoặc helper generic `<T>` để giữ cùng một kiểu.

**Nguyên tắc cần nhớ:** PECS là chỉ dẫn theo **vai trò đọc/ghi của tham số**, không phải quy tắc bắt buộc mọi tham số có `List` đều phải khai báo bằng wildcard.

## 2. Vì sao `? extends T` không đủ khi muốn ghi T?

Xét nguồn chỉ cần đọc:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}
```

`source` có thể là `List<Integer>`, `List<Double>` hoặc `List<Number>`. Mọi phần tử đều đọc được dưới dạng `Number`.

Nhưng nếu cùng biến phải nhận một `Number` bất kỳ:

```java
static void wrong(List<? extends Number> values) {
    Number old = values.get(0); // Đúng về kiểu nếu chỉ số hợp lệ
    values.set(0, old);         // LỖI BIÊN DỊCH
    values.add(5);              // LỖI BIÊN DỊCH
}
```

`? extends Number` đại diện cho **một kiểu phần tử cụ thể nhưng chưa biết**. Một danh sách có thể thực sự là `List<Integer>`; giá trị `Number` nhận từ nơi khác có thể là `Double`. Do đó `set` hoặc `add` bằng `Number` bất kỳ không được bảo đảm an toàn.

Ngay cả khi giá trị `old` vừa được đọc từ chính danh sách, cách viết `values.set(0, old)` vẫn sai vì khi khai báo `Number old`, ta chỉ giữ được thông tin `Number`, không còn quan hệ chặt với kiểu capture chưa biết của `values`.

`values.add(null)` và `values.set(0, null)` là ngoại lệ **có thể biên dịch** vì `null` tương thích với kiểu tham chiếu chưa biết. Tuy nhiên, danh sách thực tế có thể không cho phép sửa đổi hoặc từ chối `null`; ngoại lệ này không giải quyết yêu cầu ghi một giá trị `T` hữu ích.

## 3. Vì sao `? super T` không đủ khi cần đọc đúng T?

Giới hạn dưới phù hợp với đích nhận giá trị:

```java
static void appendInteger(List<? super Integer> destination) {
    destination.add(10); // Đúng về kiểu
}
```

`destination` có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`. Mọi danh sách như vậy đều nhận được `Integer`.

Nhưng nếu phương thức cần đọc một `Integer` từ chính đích này:

```java
static void wrongRead(List<? super Integer> values) {
    Integer value = values.get(0); // LỖI BIÊN DỊCH
    Object valueAsObject = values.get(0); // Đúng nếu chỉ số hợp lệ
}
```

Danh sách có thể thực sự là `List<Object>` và chứa các giá trị không phải `Integer`. Vì vậy, phần tử đọc ra qua `? super Integer` chỉ được bảo đảm là `Object`.

Đổi từ `? extends T` sang `? super T` có thể giải quyết quyền **ghi T** nhưng đánh mất bảo đảm **đọc T**. Cả hai wildcard được thiết kế để mô tả **hướng sử dụng dữ liệu**; chúng không thay thế được một quan hệ kiểu chính xác cần duy trì ở cả hai chiều.

## 4. Giải pháp chính: dùng `List<T>` khi cần cùng một T

Khi giá trị được đọc và ghi phải thuộc **cùng một kiểu phần tử**, hãy đặt tên kiểu đó trong chữ ký:

```java
static <T> void replaceFirst(List<T> values, T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

Ví dụ:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
replaceFirst(names, "Chi"); // T là String

List<Integer> ages = new ArrayList<>(List.of(18, 20));
replaceFirst(ages, 21); // T là Integer
```

Phương thức generic là một **khuôn mẫu kiểu**: mỗi lời gọi suy luận một `T` tương thích với các đối số. Sự linh hoạt này khác với một tham số cố định `List<Object>`, vốn không nhận trực tiếp `List<String>` hoặc `List<Integer>` vì generic của Java mặc định bất biến.

Nếu cần viết phép biến đổi mà **giá trị mới bắt nguồn từ giá trị cũ**, dùng `UnaryOperator<T>`:

```java
import java.util.List;
import java.util.function.UnaryOperator;

static <T> void updateFirst(
        List<T> values,
        UnaryOperator<T> operation) {
    if (!values.isEmpty()) {
        T oldValue = values.get(0);
        T newValue = operation.apply(oldValue);
        values.set(0, newValue);
    }
}
```

`UnaryOperator<T>` có dạng `T -> T`, tức là nhận và trả về **cùng T**. Như vậy kiểu của kết quả được phép ghi trở lại `List<T>`.

Ví dụ:

```java
List<String> words = new ArrayList<>(List.of("java", "generics"));
updateFirst(words, String::toUpperCase); // [JAVA, generics]

List<Integer> scores = new ArrayList<>(List.of(3, 4));
updateFirst(scores, n -> n * 10);       // [30, 4]
```

Lưu ý: một `List<T>` có thể là danh sách không hỗ trợ sửa đổi (ví dụ `List.of(...)`). Chữ ký chỉ bảo đảm **an toàn kiểu ở compile-time**, không bảo đảm `set` hoạt động lúc chạy. Trong trường hợp danh sách không hỗ trợ `set`, phương thức có thể ném `UnsupportedOperationException`.

## 5. Khi chỉ có `List<?>`: dùng wildcard capture helper

Đôi khi API bên ngoài chỉ biết một danh sách chứa kiểu bất kỳ:

```java
List<?> unknown = new ArrayList<>(List.of("A", "B"));
```

Nếu cần đổi chỗ **những phần tử đã có**, ta không cần biết kiểu cụ thể, miễn mọi giá trị di chuyển vẫn thuộc **cùng danh sách** và giữ nguyên kiểu đó. Một cách diễn đạt an toàn là gọi helper generic:

```java
static <T> void swapFirstTwo(List<T> values) {
    if (values.size() < 2) {
        return;
    }

    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}

static void reorderUnknown(List<?> values) {
    swapFirstTwo(values);
}
```

Ở lời gọi `swapFirstTwo(values)`, Java có thể **capture wildcard** thành một tham số kiểu `T` cho toàn bộ một lần gọi. Bên trong helper, `get` và `set` sử dụng đúng cùng `T`, vì vậy không cần ép kiểu và không có nguy cơ đưa một kiểu phần tử mới khác loại vào danh sách.

Một phép viết trực tiếp sau thường không biên dịch:

```java
static void badSwap(List<?> values) {
    Object first = values.get(0);
    values.set(0, first); // LỖI BIÊN DỊCH
}
```

`Object` quá rộng so với kiểu phần tử chưa biết. Ngay cả `values.set(0, values.get(0))` cũng có thể bị từ chối do các lần sử dụng wildcard được capture riêng và không liên hệ theo cách mà `set` yêu cầu.

Cũng có thể dùng tiện ích chuẩn:

```java
import java.util.Collections;
import java.util.List;

static void reverseUnknown(List<?> values) {
    Collections.reverse(values);
}

static void swapUnknown(List<?> values) {
    if (values.size() >= 2) {
        Collections.swap(values, 0, 1);
    }
}
```

`Collections.reverse` và `Collections.swap` đều nhận danh sách kiểu wildcard và triển khai thao tác giữ an toàn kiểu cho các phần tử đang có. Chúng vẫn cần danh sách hỗ trợ các phép thay đổi tương ứng; ví dụ, danh sách `List.of` không cho sửa.

**Khác biệt cần nhận ra:** helper có thể **di chuyển, sao chép lại hoặc biến đổi theo cùng T**; nó không cấp quyền chèn tùy ý một `Number` vào một `List<Integer>`.

## 6. Hai trường hợp hay nhầm: một danh sách hai vai trò và hai danh sách hai vai trò

Cách thiết kế phải dựa trên việc **cùng một đối tượng** vừa đọc/ghi hay có **hai tham số khác nhau**.

### Trường hợp A: cùng một danh sách vừa là nguồn vừa là đích

Ví dụ: thay phần tử đầu, hoán đổi hai phần tử, xoay thứ tự, chuẩn hóa chuỗi, áp dụng phép biến đổi `T -> T`.

```java
static <T> void swapFirstTwo(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

**Đề xuất:** `List<T>` cùng tham số kiểu đặt tên `T`. Nếu API chỉ cần đảo thứ tự mà không xử lý cụ thể phần tử, `List<?>` ở API bên ngoài cùng helper/tiện ích thư viện cũng có thể thích hợp.

Lý do: phương thức muốn bảo đảm phần tử lấy từ chính danh sách có thể đặt lại vào danh sách với **cùng kiểu**.

### Trường hợp B: hai danh sách khác nhau, một nguồn đọc và một đích ghi

Ví dụ: sao chép `Integer` từ `List<Integer>` sang `List<Number>` hoặc `List<Object>`.

```java
static <T> void copyAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

**Đề xuất:** áp dụng PECS theo từng tham số: `source` dùng `? extends T`, `destination` dùng `? super T`.

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyAll(integers, numbers); // Đúng
copyAll(integers, objects); // Đúng
```

Nếu viết cứng cả hai bên thành `List<T>`:

```java
static <T> void restrictiveCopy(List<T> src, List<T> dest) {
    dest.addAll(src);
}
```

thì cuộc gọi `restrictiveCopy(List<Integer>, List<Number>)` **không hợp lệ**, vì `List<Integer>` và `List<Number>` không có cùng đối số kiểu `T`. Đây là trường hợp dùng wildcard PECS làm API linh hoạt hơn mà vẫn an toàn.

**Không nên nhầm** phương thức `copyAll` vừa viết với `Collections.copy(destination, source)`: `copyAll` ở đây nối thêm phần tử vào cuối đích, còn `Collections.copy` thay giá trị ở các vị trí đã tồn tại và yêu cầu danh sách đích có đủ phần tử.

Ngoài ra, nếu `source` và `destination` là **cùng một danh sách**, không nên lặp `for-each` qua nó đồng thời `add` vào nó: nhiều triển khai (như `ArrayList`) sẽ phát hiện thay đổi cấu trúc khi đang lặp và ném `ConcurrentModificationException`. Hãy xử lý trường hợp aliasing nếu API cho phép nguồn và đích trùng nhau, chẳng hạn sao chép snapshot trước khi thêm.

## 7. Một tham số vừa đọc và thêm giá trị mới: xác định nghĩa vụ kiểu

Không phải bất cứ trường hợp “đọc rồi ghi” nào cũng chỉ cần `List<T>` mà không cần thiết kế thêm. Hãy xác định **giá trị được ghi đến từ đâu**:

| Tình huống | Kiểu tham số nên dùng | Vì sao |
| --- | --- | --- |
| Chỉ đọc phần tử dưới dạng `T` | `List<? extends T>` | Nguồn có thể có kiểu phần tử hẹp hơn `T` |
| Chỉ nhận giá trị `T` để ghi | `List<? super T>` | Đích có thể có kiểu phần tử rộng hơn `T` |
| Đọc và ghi lại phần tử **cùng kiểu** trong một danh sách | `List<T>` với helper `<T>` khi cần | Giữ liên hệ đúng kiểu giữa `get` và `set` |
| Đọc `T`, áp dụng `T -> T`, rồi ghi lại | `List<T>`, `UnaryOperator<T>` | Kết quả biến đổi luôn đúng `T` |
| Chỉ sắp xếp lại các phần tử hiện có, kiểu thực tế không quan trọng | `List<?>` + `Collections.swap/reverse` hoặc helper `<T>` | Dùng wildcard capture, không thêm kiểu lạ |
| Chuyển phần tử giữa nguồn và đích riêng biệt | `List<? extends T>` và `List<? super T>` | PECS cho đúng mỗi vai trò |
| Thay phần tử bằng giá trị cụ thể kiểu `Number` | Danh sách phải thực sự cho phép nhận `Number`, ví dụ `List<Number>` hoặc `List<? super Number>` | Danh sách `List<Integer>` không nhận được `Double` |

Cần phân biệt **một tham số kiểu `T`** (đại diện cho một kiểu và liên hệ nhiều vị trí) với **wildcard `?`** (kiểu phần tử không biết tại vị trí dùng). Một phương thức generic có thể vừa khai báo `T` vừa dùng wildcard ở những tham số có vai trò riêng biệt.

### 7.1. Giới hạn `T extends Number` có giải quyết được trường hợp vừa đọc vừa ghi?

Có thể giới hạn `T` nếu thuật toán thực sự cần chức năng của `Number`:

```java
static <T extends Number> T first(List<T> values) {
    return values.get(0);
}
```

Nếu muốn **thay** phần tử bằng giá trị `T`, vẫn phải dùng đúng `T`:

```java
static <T extends Number> void replaceFirst(
        List<T> values,
        T replacement) {
    if (!values.isEmpty()) {
        values.set(0, replacement);
    }
}
```

Việc có `<T extends Number>` **không** cho phép thêm một `Double` tùy ý vào `List<T>`, vì `T` có thể là `Integer`. Chữ ký `List<? extends T>` cũng không cho thêm `T` tùy ý vì kiểu phần tử của danh sách có thể hẹp hơn `T`.

### 7.2. Không cần wildcard chỉ để nhận nhiều kiểu List

Một phương thức khai báo `<T> void process(List<T>)` có thể được gọi với cả `List<String>` lẫn `List<Integer>`, mỗi lần suy luận `T` riêng. Do đó không phải dùng `List<?>` chỉ để đạt khả năng nhận nhiều kiểu danh sách.

```java
static <T> void keepSameType(List<T> values) {
    if (!values.isEmpty()) {
        T current = values.get(0);
        values.set(0, current);
    }
}
```

Ví dụ này dùng `set` với chính giá trị cũ để minh họa tính nhất quán kiểu; trong mã thực tế nên thực hiện phép biến đổi có ích hoặc không gọi `set` nếu không cần.

## 8. Ví dụ Java 17+ đầy đủ

Lưu tệp `PecsBothDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.UnaryOperator;

public class PecsBothDemo {
    // Một List vừa cung cấp T vừa nhận lại T.
    static <T> void replaceFirst(
            List<T> values,
            UnaryOperator<T> operation) {
        if (!values.isEmpty()) {
            values.set(0, operation.apply(values.get(0)));
        }
    }

    // Helper sử dụng cùng T cho hai thao tác get và set.
    static <T> void swapFirstTwo(List<T> values) {
        if (values.size() >= 2) {
            T first = values.get(0);
            values.set(0, values.get(1));
            values.set(1, first);
        }
    }

    // API ngoài không cần biết kiểu phần tử cụ thể.
    static void reorderUnknown(List<?> values) {
        swapFirstTwo(values);
    }

    // Hai tham số có vai trò tách biệt: producer và consumer.
    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("cat", "dog", "bird"));
        replaceFirst(words, String::toUpperCase);
        System.out.println("Replace: " + words);

        List<?> unknownWords = words;
        reorderUnknown(unknownWords);
        System.out.println("Swap: " + words);

        List<Integer> scores = new ArrayList<>(List.of(2, 4));
        replaceFirst(scores, x -> x * 10);
        System.out.println("Numbers: " + scores);

        List<Number> numbers = new ArrayList<>();
        copyAll(scores, numbers);
        System.out.println("Copy to numbers: " + numbers);

        List<Object> objects = new ArrayList<>();
        copyAll(words, objects);
        System.out.println("Copy to objects: " + objects);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PecsBothDemo.java
java PecsBothDemo
```

Kết quả chính xác:

```text
Replace: [CAT, dog, bird]
Swap: [dog, CAT, bird]
Numbers: [20, 4]
Copy to numbers: [20, 4]
Copy to objects: [dog, CAT, bird]
```

Diễn giải:

1. `replaceFirst` đọc `String` và ghi lại `String` sau chuyển thành chữ hoa.
2. `reorderUnknown` nhận `List<?>` rồi nhờ helper generic capture kiểu thực tế; hoán đổi được mà không ép kiểu.
3. Cùng phương thức `replaceFirst` nhận `List<Integer>` với phép biến đổi `Integer -> Integer`, chứng minh `T` được suy luận theo từng lời gọi.
4. `copyAll(scores, numbers)` dùng `? extends T` cho nguồn `Integer`, `? super T` cho đích `Number`.
5. `copyAll(words, objects)` cũng an toàn bởi `List<Object>` nhận được các phần tử `String`.

Mọi danh sách trong ví dụ đều là `ArrayList` có thể sửa đổi ở nơi thuật toán cần ghi, nên kết quả không phụ thuộc một thao tác ghi bị cấm bởi `List.of`.

## 9. Những lỗi thường gặp

### 9.1. Cố dùng `? extends T` khi cần cập nhật phần tử

```java
static void incorrect(List<? extends Number> values) {
    Number value = values.get(0);
    values.set(0, value); // Không biên dịch
}
```

**Sửa:** đặt cùng một `T` cho toàn bộ quan hệ đọc/ghi, nếu cần thao tác trên kiểu phần tử thực tế:

```java
static <T extends Number> void correct(List<T> values) {
    if (!values.isEmpty()) {
        T value = values.get(0);
        values.set(0, value);
    }
}
```

Ví dụ `correct` thể hiện tính an toàn kiểu; việc gán lại cùng giá trị trong thực tế không tạo thay đổi nghiệp vụ.

### 9.2. Cố đọc T từ `? super T`

```java
static void incorrect(List<? super Integer> values) {
    Integer first = values.get(0); // Không biên dịch
}
```

**Sửa:** dùng `List<Integer>` hoặc `<T> List<T>` nếu cần đúng kiểu khi đọc; hoặc đọc thành `Object` nếu API chỉ cần xử lý ở mức `Object`.

### 9.3. Khai báo hai tham số cùng `List<T>` một cách không cần thiết

```java
static <T> void copy(List<T> source, List<T> target) {
    target.addAll(source);
}
```

Chữ ký này chặt hơn yêu cầu thực tế nếu nguồn và đích có thể khác tham số kiểu theo hướng an toàn (ví dụ `Integer` sang `Number`). Nên tách vai trò bằng `? extends T` và `? super T` khi cần.

### 9.4. Dùng raw type hoặc unchecked cast để đưa giá trị mới vào List<?>

```java
// Mã nguy hiểm, không nên sử dụng:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List<?> values) {
    List raw = values;
    raw.add("not necessarily correct");
}
```

Nếu `values` đang trỏ tới `List<Integer>`, lệnh trên có thể đưa `String` vào danh sách. Lỗi chỉ có thể xuất hiện sau đó khi nơi khác đọc và ép phần tử thành `Integer`. Đây là **heap pollution**, không phải cách áp dụng PECS.

### 9.5. Tưởng List<T> đồng nghĩa có thể sửa đổi

```java
List<String> immutable = List.of("A", "B");
swapFirstTwo(immutable); // Biên dịch nhưng có thể ném UnsupportedOperationException
```

Hệ thống kiểu generics không bảo đảm khả năng thay đổi nội dung của một `List`. Nếu phương thức có hợp đồng cần sửa dữ liệu, tài liệu API phải nêu rõ yêu cầu danh sách hỗ trợ `set`, `add` hoặc `remove` tương ứng; có thể tạo một `ArrayList` mới nếu không được phép sửa nguồn.

## 10. Tự kiểm tra

Giả sử đã `import java.util.*;`. Hãy xác định trường hợp nào **biên dịch**, thao tác nào có thể **lỗi runtime**, và sửa chữ ký khi cần.

**A — Cùng danh sách vừa đọc vừa ghi**

```java
static <T> void swap(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

**B — Dùng wildcard extends với Number**

```java
static void change(List<? extends Number> list) {
    Number n = list.get(0);
    list.set(0, n);
}
```

**C — Dùng wildcard super với Integer**

```java
static void change(List<? super Integer> list) {
    Integer n = list.get(0);
    list.add(n);
}
```

**D — Copy hai danh sách theo PECS**

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
List<Integer> source = List.of(1, 2);
List<Number> target = new ArrayList<>();
copy(source, target);
```

**E — List<?> gọi helper có type parameter**

```java
static <T> void swapFirstTwo(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
List<?> unknown = new ArrayList<>(List.of("A", "B"));
swapFirstTwo(unknown);
```

Các ví dụ là **mảnh mã minh họa độc lập**: phải đặt phương thức `static` trong một lớp, và các lệnh gọi/khai báo biến tại vị trí hợp lệ; không ghép tất cả phương thức trùng tên vào cùng một lớp rồi suy diễn rằng đó là một tệp hoàn chỉnh.

**Đáp án:**

- **A:** Biên dịch. `List<T>` giữ cùng kiểu cho `get` và `set`; runtime có thể từ chối `set` nếu danh sách không hỗ trợ sửa đổi.
- **B:** Không biên dịch. `Number` là giới hạn trên, không chắc tương thích với kiểu phần tử ẩn của `List<? extends Number>`.
- **C:** Không biên dịch ở phép gán `get` cho `Integer`: `List<? super Integer>` chỉ bảo đảm đọc ra `Object`. Phép `add` một `Integer` đã biết là hợp lệ nếu tách riêng.
- **D:** Biên dịch và chạy thành công với `ArrayList` đích, kết quả `[1, 2]`.
- **E:** Biên dịch và chạy với `ArrayList`; generic method capture wildcard để bảo đảm cùng kiểu phần tử được đọc và ghi.

## 11. Checklist chọn chữ ký API

Khi đứng trước một tham số generic cần đọc và/hoặc ghi, hãy xác định:

1. **Đọc ra giá trị thuộc kiểu nào?** Nếu chỉ cần giao diện của kiểu cha `T`, `? extends T` có thể đủ.
2. **Ghi vào giá trị từ đâu?** Nếu đưa một `T` từ bên ngoài vào, `? super T` là ứng viên.
3. **Cùng một danh sách phải đọc và ghi đúng kiểu thực tế không?** Dùng `List<T>` với tham số kiểu `<T>`, hoặc helper capture wildcard.
4. **Có hai danh sách nguồn/đích riêng biệt không?** Áp dụng PECS cho từng tham số riêng.
5. **Đối tượng có sửa được không?** Kiểm tra hợp đồng runtime của `List`, không suy từ `T`, `extends` hoặc `super`.
6. **Nguồn và đích có thể cùng tham chiếu một danh sách không?** Cân nhắc snapshot/thuật toán không lặp và thêm đồng thời để tránh vấn đề thay đổi cấu trúc.

### Kết luận cần ghi nhớ

Khi **cùng một tham số vừa cung cấp vừa nhận các phần tử cùng kiểu**, dùng **`List<T>` và một tham số kiểu `<T>` được đặt tên** là cách thông dụng nhất để giữ quan hệ kiểu chính xác. Nếu phía ngoài chỉ có `List<?>` hoặc `List<? extends T>`, có thể chuyển việc thao tác phần tử đang có vào helper generic để **capture** kiểu ẩn một cách an toàn. Nếu **hai tham số có hướng dữ liệu tách biệt**, PECS vẫn thích hợp: **`? extends T` ở nguồn, `? super T` ở đích**.
