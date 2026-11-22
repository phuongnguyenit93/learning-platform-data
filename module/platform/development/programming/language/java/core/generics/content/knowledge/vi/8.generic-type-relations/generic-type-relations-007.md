# Quan hệ kiểu giữa các wildcard có giới hạn

## 1. Mục tiêu và bối cảnh

Trong Java Generics, một quan hệ kế thừa giữa hai kiểu phần tử **không tự động tạo ra quan hệ kế thừa giữa hai kiểu generic**. Ví dụ, vì `Integer` là kiểu con của `Number`, ta có thể gán `Integer` cho biến `Number`, nhưng không thể gán `List<Integer>` cho biến `List<Number>`.

Wildcard có giới hạn giúp mô tả chính xác nhóm kiểu phần tử mà một tham số generic chấp nhận. Bài này tập trung vào **quan hệ kiểu giữa các cách sử dụng wildcard**: khi nào một `List<? extends A>` có thể gán cho `List<? extends B>`, khi nào một `List<? super A>` có thể gán cho `List<? super B>`, và tại sao hai chiều lại ngược nhau.

Sau bài học, bạn cần tự xác định được chiều gán hợp lệ, phân biệt khả năng đọc/ghi, viết API với PECS, và giải thích được các lỗi biên dịch liên quan đến wildcard.

## 2. Ba khái niệm nền tảng

Giả sử `Integer` là subtype của `Number` và `Number` là subtype của `Object`:

```text
Integer <: Number <: Object
```

Ký hiệu `S <: T` nghĩa là một giá trị có kiểu `S` có thể được dùng ở nơi cần `T` theo quan hệ subtype. Với `List`, hãy phân biệt:

- `List<Integer>`: phần tử có kiểu chính xác `Integer` theo khai báo generic.
- `List<? extends Number>`: danh sách với kiểu phần tử **chưa biết**, nhưng kiểu đó là `Number` hoặc subtype của `Number`.
- `List<? super Integer>`: danh sách với kiểu phần tử **chưa biết**, nhưng kiểu đó là `Integer` hoặc supertype của `Integer`.

Wildcard không làm thay đổi kiểu runtime của đối tượng. Nó thay đổi điều mà **trình biên dịch có thể bảo đảm** khi ta sử dụng tham chiếu generic.

### 2.1. Tính bất biến (invariance)

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // LỖI BIÊN DỊCH
```

Nếu dòng gán trên được phép, mã phía sau có thể gọi `numbers.add(3.14)` và phá vỡ lời hứa rằng `integers` chỉ chứa `Integer`. Do đó, `List<Integer>` và `List<Number>` không có quan hệ subtype chỉ vì `Integer <: Number`.

### 2.2. Wildcard là một kiểu phần tử chưa biết

`List<? extends Number>` không đồng nghĩa với `List<Number>`: danh sách thực tế có thể là `List<Integer>`, `List<Double>`, hoặc `List<Number>`. Tương tự, `List<? super Integer>` có thể tham chiếu đến `List<Integer>`, `List<Number>` hoặc `List<Object>`.

Dấu `?` mang ý nghĩa **có một kiểu thực tế cụ thể nhưng ta không biết chính xác là kiểu nào**. Vì vậy, không được tùy tiện xem nó là `Number`, `Integer` hay `Object` theo ý muốn.

## 3. Quy tắc quan hệ kiểu của `? extends`

Với `A <: B`, quan hệ sau là hợp lệ khi hai bên dùng cùng một kiểu generic `G`:

```text
G<? extends A> <: G<? extends B>
```

Đây là **chiều mở rộng cận trên**: một danh sách có cận trên hẹp (`Integer`) có thể được dùng như danh sách có cận trên rộng hơn (`Number`). Lý do: mọi kiểu không vượt quá `Integer` cũng không vượt quá `Number`.

```java
List<? extends Integer> source = List.of(10, 20);
List<? extends Number> target = source; // HỢP LỆ
Number value = target.get(0);           // HỢP LỆ
```

Chiều ngược lại không an toàn:

```java
List<? extends Number> source = List.of(1.5, 2.5);
// List<? extends Integer> target = source; // LỖI BIÊN DỊCH
```

`source` có thể thực chất là `List<Double>`. Java không thể bảo đảm tất cả phần tử là `Integer`.

Điểm quan trọng: **điều đang thay đổi là giới hạn wildcard**, không phải Java đang cho phép `List<Integer>` trở thành `List<Number>`.

### 3.1. Các gán hợp lệ từ kiểu cụ thể

```java
List<Integer> ints = List.of(1, 2);
List<? extends Integer> a = ints;
List<? extends Number> b = ints;
List<? extends Object> c = ints;
List<?> d = ints;
```

Tất cả đều hợp lệ. Mỗi biến `a`–`d` chứa cùng tham chiếu tới danh sách ban đầu, nhưng càng mở rộng cận trên, trình biên dịch càng biết ít về kiểu phần tử khi đọc.

### 3.2. Hệ quả khi đọc và ghi

Với `List<? extends Number>`:

- Đọc phần tử dưới dạng `Number` được, vì mọi kiểu được chấp nhận đều là subtype của `Number`.
- Không thể thêm `Integer`, `Double` hay một `Number` bất kỳ, vì kiểu phần tử thực tế có thể là một subtype khác.
- `add(null)` được phép về mặt kiểu (nếu cấu trúc danh sách hỗ trợ thao tác thêm), vì `null` tương thích với mọi kiểu tham chiếu.

```java
List<? extends Number> numbers = new ArrayList<Integer>();
Number n = numbers.get(0); // Mã chỉ minh họa kiểm tra kiểu; list rỗng nên không chạy dòng này.
// numbers.add(123);       // LỖI BIÊN DỊCH
numbers.add(null);         // Được phép về kiểu; ArrayList ở ví dụ là mutable.
```

Nhớ rằng **được phép biên dịch** không có nghĩa một implementation nhất định luôn cho phép thay đổi: `List.of(...)` là immutable và có thể ném `UnsupportedOperationException` ngay cả với thao tác thay đổi hợp lệ về kiểu.

## 4. Quy tắc quan hệ kiểu của `? super`

Vẫn giả sử `A <: B`. Với cận dưới, quan hệ đảo chiều:

```text
G<? super B> <: G<? super A>
```

Ví dụ:

```java
List<? super Number> source = new ArrayList<Object>();
List<? super Integer> target = source; // HỢP LỆ
target.add(7);                        // HỢP LỆ
```

Giải thích: mọi kiểu có thể chứa `Number` (như `Number` hay `Object`) chắc chắn cũng chứa được `Integer`. Nhưng một danh sách chỉ bảo đảm chứa được `Integer` chưa chắc chứa được mọi `Number` (ví dụ `Double`).

Chiều ngược không hợp lệ:

```java
List<? super Integer> source = new ArrayList<Integer>();
// List<? super Number> target = source; // LỖI BIÊN DỊCH
```

Nếu dòng gán được phép, `target.add(3.14)` sẽ đưa `Double` vào một `List<Integer>`.

### 4.1. Các gán hợp lệ từ kiểu cụ thể

```java
List<Integer> ints = new ArrayList<>();
List<Number> nums = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = ints;
List<? super Integer> b = nums;
List<? super Integer> c = objects;

List<? super Number> d = nums;
List<? super Number> e = objects;
// List<? super Number> f = ints; // LỖI BIÊN DỊCH
```

### 4.2. Hệ quả khi đọc và ghi

Với `List<? super Integer>`:

- Có thể thêm `Integer` và subtype của `Integer` (trong thực tế `Integer` là `final`).
- Không thể thêm `Number` tùy ý, vì danh sách thực tế có thể chỉ là `List<Integer>`.
- Giá trị đọc ra chỉ được bảo đảm có kiểu `Object`: kiểu phần tử thực tế có thể là `Integer`, `Number` hoặc `Object`.

```java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(42);
Object item = sink.get(0);
// Integer value = sink.get(0); // LỖI BIÊN DỊCH: chỉ bảo đảm Object.
// sink.add(3.14);              // LỖI BIÊN DỊCH: Double không phải Integer.
```

Ép kiểu `(Integer) item` chỉ hợp lệ về runtime nếu đối tượng thực sự là `Integer`; wildcard không cho phép suy luận điều đó cho mọi phần tử.

## 5. Sơ đồ quan hệ và cách ghi nhớ

Với `Integer <: Number <: Object`, các mũi tên sau biểu thị phép gán từ trái sang phải là hợp lệ:

```text
Nhánh cận trên (? extends):
List<Integer>
    -> List<? extends Integer>
    -> List<? extends Number>
    -> List<? extends Object> (tương đương về cận với List<?>)

Nhánh cận dưới (? super):
List<Object>
    -> List<? super Number>
    -> List<? super Integer>
    -> List<?>

Ngoài ra:
List<Number> -> List<? extends Number>
List<Number> -> List<? super Number>
List<Number> -> List<? super Integer>
List<Integer> -> List<? super Integer>
```

| Bài toán | Chiều quan hệ khi `A <: B` | Điều được bảo đảm |
| --- | --- | --- |
| Cận trên `extends` | `G<? extends A> <: G<? extends B>` | Đọc được ít nhất như `B` |
| Cận dưới `super` | `G<? super B> <: G<? super A>` | Có thể ghi các giá trị kiểu `A` |
| Generic cụ thể | `G<A>` **không** suy ra `G<B>` | Bất biến đối với tham số kiểu |
| Không giới hạn `?` | Các cách dùng `G<T>`, `G<? extends T>`, `G<? super T>` đều có thể gán vào `G<?>` | Đọc an toàn như `Object` |

Khi xét sơ đồ, không suy ra `List<? extends Number>` và `List<? super Integer>` có quan hệ subtype trực tiếp với nhau. Cả hai có thể tham chiếu cùng một `List<Number>`, nhưng một biến kiểu thứ nhất không tự động gán được cho biến kiểu thứ hai: mỗi biến có những bảo đảm khác nhau.

## 6. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Lưu thành tệp `WildcardRelationsDemo.java`. Chương trình minh họa **cả hai chiều gán hợp lệ** và truyền dữ liệu từ producer sang consumer.

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardRelationsDemo {
    static <T> void copyAll(List<? extends T> source, List<? super T> target) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);

        // Cận trên: Integer -> Number.
        List<? extends Integer> integerProducer = integers;
        List<? extends Number> numberProducer = integerProducer;
        Number first = numberProducer.get(0);

        // Cận dưới: super Number -> super Integer.
        List<Object> objects = new ArrayList<>();
        List<? super Number> numberConsumer = objects;
        List<? super Integer> integerConsumer = numberConsumer;
        integerConsumer.add(3);

        Object inserted = integerConsumer.get(0);

        List<Number> numbers = new ArrayList<>();
        copyAll(integers, numbers);

        System.out.println(first);
        System.out.println(objects);
        System.out.println(inserted);
        System.out.println(numbers);
    }
}
```

Biên dịch và chạy:

```bash
javac WildcardRelationsDemo.java
java WildcardRelationsDemo
```

Kết quả stdout chính xác:

```text
1
[3]
3
[1, 2]
```

Trong `copyAll`, `source` sản xuất giá trị kiểu `T` (`? extends T`), còn `target` nhận giá trị kiểu `T` (`? super T`). Với `T = Integer`, `List<Integer>` là nguồn hợp lệ và `List<Number>` là đích hợp lệ. Ví dụ tự xây dựng phương thức `copyAll` theo nghĩa **append** vào đích; khác với `Collections.copy(dest, src)`, vốn yêu cầu danh sách đích đã có đủ vị trí phần tử để thay thế.

## 7. PECS và thiết kế API

**PECS = Producer Extends, Consumer Super**: chọn wildcard theo **cách phương thức dùng dữ liệu**.

Nếu một tham số chỉ cung cấp phần tử cho ta đọc, dùng `? extends T`:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number number : values) {
        total += number.doubleValue();
    }
    return total;
}
```

`sum` dùng được với `List<Integer>`, `List<Double>`, `List<Number>` mà không phải ép kiểu hoặc copy danh sách.

Nếu một tham số chỉ nhận phần tử ta đưa vào, dùng `? super T`:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

`addDefaults` dùng được với `List<Integer>`, `List<Number>`, `List<Object>`.

Nếu một phương thức cần vừa **đọc thành T** vừa **ghi T** theo cùng kiểu phần tử chính xác, nhiều trường hợp nên dùng một type parameter `<T>` thay cho wildcard mơ hồ:

```java
static <T> void duplicateFirst(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.add(first);
    }
}
```

Đây là đoạn khai báo phương thức minh họa, không phải chương trình độc lập. Tham số `List<T>` giữ được tương quan giữa kiểu dữ liệu đọc ra và kiểu dữ liệu được phép ghi vào.

## 8. Quan hệ giữa hai wildcard khác hướng

Không có quy tắc chung nào cho phép đổi tự do `extends` sang `super`:

```java
List<? extends Number> producer = List.of(1, 2);
// List<? super Integer> consumer = producer; // LỖI BIÊN DỊCH
```

Một `producer` hợp lệ có thể là `List<Double>`; danh sách đó không phải nơi có thể chèn `Integer`. Tương tự:

```java
List<? super Integer> consumer = new ArrayList<Object>();
// List<? extends Number> producer = consumer; // LỖI BIÊN DỊCH
```

Danh sách ở biến `consumer` có thể là `List<Object>`, trong đó có các phần tử không phải `Number`. Muốn chuyển vai trò một cách an toàn, thiết kế phương thức nhận nguồn và đích riêng, hoặc giữ một tham chiếu có kiểu cụ thể tại nơi khởi tạo thay vì ép kiểu không kiểm tra.

Một điểm tinh tế: việc **hai kiểu wildcard có thể chấp nhận cùng một đối tượng** không chứng minh chúng là subtype của nhau. Subtyping đòi hỏi phép gán phải an toàn với *mọi* đối tượng phù hợp với kiểu nguồn, không chỉ trường hợp cụ thể đang thấy.

## 9. Quan hệ khi generic và wildcard lồng nhau

Wildcard ở cấp trong không tự động làm generic cấp ngoài trở nên biến thiên.

```java
List<List<Integer>> nested = new ArrayList<>();

// List<List<? extends Number>> invalid = nested; // LỖI BIÊN DỊCH

List<? extends List<? extends Number>> valid = nested; // HỢP LỆ
```

Dòng thứ nhất sai vì tham số trực tiếp của `List` ngoài là `List<Integer>` và `List<? extends Number>`, hai kiểu khác nhau; `List` ngoài vẫn bất biến. Dòng cuối hợp lệ vì `? extends` ở lớp ngoài cho phép kiểu phần tử là subtype của `List<? extends Number>`, bao gồm `List<Integer>`.

Quy tắc thực hành: đánh giá quan hệ **tại từng cấp generic**. Đừng chỉ nhìn thấy `extends Number` ở bên trong rồi suy ra mọi lớp `List` bao ngoài đều gán được.

### 9.1. Quan hệ giữa interface generic khác nhau

Hai vế không bắt buộc cùng là `List` nếu có quan hệ interface/class thực sự. Ví dụ:

```java
List<Integer> ints = List.of(1, 2);
Collection<? extends Number> numbers = ints; // HỢP LỆ
Iterable<? extends Number> items = numbers;  // HỢP LỆ
```

Ở đây ta kết hợp hai cơ chế: `List<E>` kế thừa `Collection<E>`, `Collection<E>` kế thừa `Iterable<E>`, và cận wildcard `Integer <: Number`. Không được áp dụng điều này cho hai generic không có quan hệ kế thừa phù hợp.

## 10. Wildcard capture và giới hạn suy luận

Khi dùng một biến `List<?>`, trình biên dịch có thể tạm đặt một tên nội bộ (capture) cho kiểu phần tử chưa biết. Ta không thể dùng hai phép đọc và ghi rời rạc để giả định kiểu đó là `Object`:

```java
static void replaceFirstWithItself(List<?> list) {
    if (!list.isEmpty()) {
        // list.set(0, list.get(0)); // Thường LỖI BIÊN DỊCH do capture không khớp.
    }
}
```

Một phương thức helper có `<T>` có thể giữ kiểu capture nhất quán:

```java
static void swapFirstTwo(List<?> list) {
    swapCaptured(list);
}

private static <T> void swapCaptured(List<T> list) {
    if (list.size() >= 2) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }
}
```

Hai phương thức trên là đoạn mã minh họa để đặt bên trong một class có `import java.util.List;`. Helper không cần biết `T` cụ thể, chỉ cần chứng minh giá trị lấy từ cùng danh sách luôn được ghi trở lại theo cùng `T`. Với danh sách immutable, thao tác `set` vẫn có thể ném `UnsupportedOperationException` khi chạy.

Wildcard capture không làm biến `List<? extends Number>` có thể thêm `Integer` tùy ý, cũng không biến `List<? super Integer>` thành nơi đọc chắc chắn được `Integer`. Nó chỉ giữ liên hệ kiểu khi thuật toán thực sự an toàn.

## 11. Lỗi phổ biến và cách sửa

| Nhận định hoặc thao tác sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `List<Integer>` gán thẳng cho `List<Number>` | Generic bất biến | Nhận `List<? extends Number>` để đọc, hoặc copy phần tử vào một `List<Number>` mới |
| `List<? extends Number>` cho `add(1)` | Kiểu phần tử có thể là `Double` | Dùng `List<? super Integer>` nếu cần thêm `Integer` |
| Đọc `Integer` trực tiếp từ `List<? super Integer>` | Danh sách có thể chứa phần tử `Number` hoặc `Object` khác | Đọc dưới dạng `Object`; chỉ kiểm tra/ép kiểu khi có cơ sở runtime |
| Nghĩ `? super Integer` là subtype của `? super Number` | Chiều cận dưới ngược lại | Nhớ `? super Number` có thể gán cho `? super Integer` |
| Gán `List<? extends Number>` cho `List<? extends Integer>` | Cận trên bị thu hẹp, có thể chứa `Double` | Giữ cận `Number` hoặc chứng minh kiểu thực tế bằng thiết kế API |
| Dùng raw `List` để tránh lỗi | Mất kiểm tra kiểu, có nguy cơ `ClassCastException` | Dùng wildcard hoặc type parameter |
| Ép kiểu không kiểm tra `(List<Number>)(List<?>) ints` | Che lỗi bất biến, có thể phá hợp đồng kiểu | Dùng generic method, wildcard phù hợp hoặc tạo danh sách mới |
| Tưởng wildcard quyết định mutability | Kiểm tra kiểu và hỗ trợ thay đổi runtime là hai việc độc lập | Phân biệt lỗi biên dịch với `UnsupportedOperationException` |

Không thể viết wildcard có đồng thời hai cận như `? extends Number super Integer`. Nếu cần thể hiện ràng buộc phức tạp, cân nhắc type parameter và thiết kế lại API. Cú pháp cận giao nhau như `<T extends Number & Comparable<T>>` thuộc về khai báo type parameter, không đồng nghĩa với việc viết `? extends Number & Comparable<?>` như một wildcard thông thường.

Ngoài ra, generic trong Java chủ yếu được kiểm tra lúc biên dịch và bị xóa thông tin type argument khi chạy (type erasure). Bạn không thể dùng `instanceof List<? extends Number>` để kiểm tra subtype element của danh sách ở runtime; `instanceof List<?>` kiểm tra được loại raw tổng quát nhưng không xác thực kiểu phần tử.

## 12. Bài tập tự kiểm tra

Giả sử đã có:

```java
List<Integer> ints = new ArrayList<>();
List<Number> nums = new ArrayList<>();
List<Object> objs = new ArrayList<>();
```

Hãy dự đoán từng dòng độc lập có biên dịch hay không:

```java
List<? extends Number> q1 = ints;                    // (1)
List<? super Integer> q2 = nums;                      // (2)
List<? super Number> q3 = ints;                       // (3)
List<? extends Integer> q4 = nums;                    // (4)
List<? super Number> q5 = objs;                       // (5)
List<? super Integer> q6 = q5;                        // (6)
List<? extends Number> q7 = q1;                       // (7)
List<? super Integer> q8 = q1;                        // (8)
```

**Đáp án:** (1) đúng vì `Integer <: Number`; (2) đúng vì `Number` chứa được `Integer`; (3) sai vì `List<Integer>` không chứa được mọi `Number`; (4) sai vì `List<Number>` không bảo đảm chỉ có `Integer`; (5) đúng vì `Object` là supertype của `Number`; (6) đúng theo chiều cận dưới (`? super Number` sang `? super Integer`); (7) đúng vì cùng kiểu wildcard; (8) sai vì producer chưa chắc nhận được `Integer`.

**Tự trả lời thêm:** Một `List<? extends Number>` có đọc được thành `Object` không? **Có**: `Number` là subtype của `Object`. Một `List<? super Integer>` có gọi `add(null)` được không? **Có về mặt kiểu** (nếu danh sách cho phép sửa). Hai điều này không đảo ngược các quy tắc chính.

## 13. Checklist khi đọc lỗi generic của trình biên dịch

1. Xác định kiểu phần tử cơ sở `A`, `B` và quan hệ subtype thực sự (nếu có).
2. Xem đối tượng đang được **đọc**, **ghi**, hay cần cả hai.
3. Với `extends`, nhớ cận trên rộng hơn cho phép nhận nguồn có cận hẹp hơn.
4. Với `super`, nhớ cận dưới hẹp hơn cho phép nhận nguồn có cận rộng hơn.
5. Kiểm tra mỗi lớp generic lồng nhau; không bỏ qua invariance ở lớp ngoài.
6. Nếu phép gán vẫn sai, hỏi liệu cần một tham số `<T>` liên kết source/target, thay vì ép kiểu raw.
7. Sau khi biên dịch thành công, kiểm tra riêng khả năng thay đổi danh sách ở runtime.

## 14. Tài liệu đọc thêm

- Oracle Java Tutorials — [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html): sơ đồ quan hệ `extends` và `super`.
- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): nguyên tắc producer/consumer.
- Java Language Specification (Java SE 17), [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): cú pháp wildcard và quy tắc containment.

**Điểm cần nắm:** Với `A <: B`, ta có `G<? extends A> <: G<? extends B>`, nhưng `G<? super B> <: G<? super A>`. Hai quy tắc này cho phép mô tả API đọc/ghi linh hoạt mà vẫn bảo toàn kiểm tra kiểu của Java.