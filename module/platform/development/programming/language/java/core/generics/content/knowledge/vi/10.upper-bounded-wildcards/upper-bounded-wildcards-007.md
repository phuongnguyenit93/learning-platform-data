# Áp dụng `? extends T` cho đầu vào cung cấp dữ liệu trong Java Generics

Khi một tham số phương thức **cung cấp dữ liệu cho phương thức đọc và xử lý** (*producer/source*), cách khai báo thường thích hợp là **`? extends T`**. Nó cho phép một API chấp nhận danh sách hoặc tập hợp của `T` **và các kiểu con của `T`** trong khi vẫn giữ kiểm tra kiểu tại thời điểm biên dịch.

Ví dụ, một hàm tính tổng chỉ cần lấy các phần tử dưới dạng `Number`. Nó không cần thêm `Number` vào danh sách được truyền vào. Vì vậy tham số `List<? extends Number>` phù hợp hơn `List<Number>`: cả `List<Integer>`, `List<Double>` lẫn `List<Number>` đều dùng được làm nguồn dữ liệu.

Quy tắc này là nửa đầu của **PECS — Producer Extends, Consumer Super**. Bài này tập trung vào nửa **Producer Extends**, nghĩa là cách thiết kế và sử dụng **tham số đầu vào cung cấp phần tử**.

## 1. “Đầu vào cung cấp dữ liệu” nghĩa là gì?

Một collection là **producer** đối với một phương thức khi phương thức đó chủ yếu **lấy phần tử từ collection** để đọc, phân tích, chuyển đổi, tổng hợp hoặc ghi sang một đích khác.

Các tình huống thường gặp:

- Tính tổng, trung bình, cực trị từ danh sách số.
- Đọc danh sách chuỗi để hiển thị hoặc ghi log.
- Duyệt tập hợp đối tượng kế thừa một lớp cha hoặc triển khai một interface chung.
- Sao chép các phần tử từ danh sách nguồn sang một danh sách đích.
- Tạo một kết quả mới từ các phần tử của đầu vào.

**Producer và consumer là vai trò của tham số trong thao tác cụ thể**, không phải đặc điểm bất biến của đối tượng. Cùng một `ArrayList<Integer>` có thể là nguồn dữ liệu đối với phương thức `sum`, nhưng là nơi nhận dữ liệu đối với phương thức `addDefaults`.

Ví dụ mô tả ý định:

```java
static double sum(List<? extends Number> source) {
    double result = 0.0;
    for (Number n : source) {
        result += n.doubleValue();
    }
    return result;
}
```

Tên `source` và vòng lặp `for` cho thấy phương thức chỉ **nhận giá trị do danh sách cung cấp**. Nó không cần biết chính xác danh sách đó có tham số kiểu `Integer`, `Double` hay `BigDecimal`; mọi phần tử đều là `Number` để gọi `doubleValue()`.

Giá trị tính được ở đây dùng số dấu phẩy động `double`, có thể gặp sai số với một số phép tính. Với nghiệp vụ tài chính cần độ chính xác thập phân, nên thiết kế phép tính riêng dùng `BigDecimal`; wildcard không quyết định quy tắc số học.

## 2. Vì sao `List<Number>` quá chặt cho dữ liệu đầu vào?

Một API **chỉ nhận và đọc dữ liệu số** không cần buộc người gọi chuyển `List<Integer>` thành `List<Number>`:

```java
static double sum(Iterable<? extends Number> source) {
    double total = 0;
    for (Number value : source) total += value.doubleValue();
    return total;
}
```

`List<Integer>` không phải subtype của `List<Number>` vì generics invariant. Nhưng `Iterable<? extends Number>` chấp nhận `List<Integer>`, `List<Double>` và `List<Number>`; caller không phải dùng unchecked cast hay tạo bản sao chỉ để thỏa một chữ ký quá chặt.

Bài này lấy **vai trò producer** của tham số làm điểm xuất phát: không chỉ thêm wildcard, mà còn chọn interface đầu vào **nhỏ nhất cần thiết**. Nếu chỉ lặp qua phần tử, `Iterable<? extends Number>` có thể tốt hơn `List<? extends Number>` vì không đòi truy cập chỉ số hoặc method sửa list.

## 3. Cơ chế: đọc an toàn nhờ giới hạn trên

Với `Iterable<? extends CharSequence>`, một phương thức có thể đọc từng phần tử như `CharSequence` và gọi `length()`, `charAt()` hoặc `toString()`:

```java
static int totalLength(Iterable<? extends CharSequence> source) {
    int total = 0;
    for (CharSequence item : source) total += item.length();
    return total;
}
```

Danh sách `String` lẫn danh sách `StringBuilder` đều phù hợp vì hai class triển khai `CharSequence`. Wildcard có upper bound là **interface** vẫn dùng từ khóa `extends`. Cơ chế capture/upper bound đã được trình bày ở đầu chương; ở đây ta ứng dụng nó để **thiết kế một tham số đầu vào tối thiểu, không cần ép kiểu và không buộc caller dùng một container duy nhất**.

## 4. Vì sao producer thường không được thêm phần tử?

Một producer `List<? extends Number>` có thể thật sự là `List<Double>`, nên phép `add(10)` không được compiler cho phép. Cấm chèn giá trị mới giúp API đọc dữ liệu mà không làm mất contract element type của caller.

| Thao tác với `List<? extends Number>` | Compile-time | Ý nghĩa |
| --- | --- | --- |
| `Number n = source.get(0)` | Cho phép | Mọi phần tử thuộc subtype của `Number` |
| `source.add(10)` | Từ chối | Không biết subtype ẩn có nhận `Integer` không |
| `source.add(null)` | Cho phép về kiểu | Runtime có thể cấm null/mutation |
| `source.clear()` | Cho phép về kiểu | Không thêm phần tử mới, nhưng có thể thay dữ liệu |

Trong một **API producer**, điều quan trọng hơn việc kiểm tra lệnh `add` là **hợp đồng hành vi**: method có nên sửa source hay không? Nếu cam kết không sửa, hãy giữ implementation chỉ đọc và test điều đó. `? extends` tự nó không khiến list thành immutable hay read-only tuyệt đối.

## 5. Thiết kế một hàm nhận nhiều loại dữ liệu

Khi phương thức cần xử lý cùng một hành vi của **lớp cha hoặc interface**, hãy dùng giới hạn trên đúng mức.

### 5.1. Nguồn số

```java
static double average(List<? extends Number> source) {
    if (source.isEmpty()) {
        throw new IllegalArgumentException("source must not be empty");
    }

    double total = 0.0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total / source.size();
}
```

Hàm này nhận `List<Integer>`, `List<Long>`, `List<Float>`, `List<Double>`, `List<BigDecimal>`... vì tất cả đều cung cấp `Number`. Nó có quyền đọc, dùng `size()` và `isEmpty()`; không cần ghi vào nguồn.

Lưu ý về hợp đồng hàm: `source` phải không rỗng; nếu không, hàm chủ động ném `IllegalArgumentException`. Nếu người gọi truyền `null`, ví dụ sẽ phát sinh `NullPointerException`; có thể dùng `Objects.requireNonNull(source)` ở API cần báo lỗi rõ hơn.

### 5.2. Nguồn interface chung

```java
static void display(Iterable<? extends CharSequence> source) {
    for (CharSequence text : source) {
        System.out.println(text.length());
    }
}
```

Ví dụ này có thể nhận `List<String>` và `List<StringBuilder>`. Nó chỉ cần thuộc tính chung `length()` của `CharSequence`. Khai báo bằng `Iterable` thay vì `List` còn giúp nhận các nguồn dữ liệu không nhất thiết hỗ trợ truy cập theo chỉ số.

### 5.3. Nguồn lớp cơ sở trong mô hình đối tượng

```java
class Animal {
    String name() {
        return "animal";
    }
}
class Dog extends Animal {
    @Override
    String name() {
        return "dog";
    }
}

static void printNames(Iterable<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

Các khai báo này là **đoạn minh họa cần đặt trong ngữ cảnh lớp/tệp phù hợp**, không phải chương trình độc lập có `main`. `printNames` có thể dùng với `List<Animal>` hoặc `List<Dog>`. Nếu chữ ký là `Iterable<Animal>`, `List<Dog>` không truyền trực tiếp được do invariance.

Điểm chung của cả ba ví dụ: phương thức quan tâm **hành vi đọc qua `T`**, chứ không cần quyền đưa các đối tượng `T` mới vào nguồn.

## 6. Chọn interface đầu vào tối thiểu

Wildcard giúp linh hoạt về **kiểu phần tử**; chọn interface đầu vào còn giúp linh hoạt về **kiểu collection**.

Các lựa chọn:

- `Iterable<? extends T>`: cần `for-each`, không yêu cầu `size()` hoặc truy cập chỉ số.
- `Collection<? extends T>`: cần khả năng duyệt, `size()`, `isEmpty()` hoặc thao tác chung của `Collection`.
- `List<? extends T>`: cần thứ tự và truy cập theo vị trí bằng `get(index)`.
- `Stream<? extends T>`: API thực sự nhận một luồng để thực hiện pipeline; nguồn stream có vòng đời và tính tiêu thụ riêng, nên không mặc nhiên dùng thay `Collection`.

Ví dụ, hàm tính tổng chỉ cần `Iterable`:

```java
static double sum(Iterable<? extends Number> source) {
    double total = 0.0;
    for (Number n : source) {
        total += n.doubleValue();
    }
    return total;
}
```

Điều này vừa thể hiện rằng nguồn **được đọc**, vừa cho phép nhiều implementation đầu vào hơn. Nếu hàm cần `source.size()` thì `Iterable` không cung cấp phương thức đó; lúc ấy dùng `Collection<? extends Number>` hoặc `List<? extends Number>` tùy nhu cầu.

Đừng chọn `List<? extends T>` chỉ vì thói quen nếu thuật toán chỉ cần vòng lặp: interface nhỏ hơn giúp hợp đồng API rõ hơn.

## 7. Sao chép từ producer sang consumer: kết hợp `extends` với `super`

Khi thao tác có **hai tham số**, một tham số cung cấp dữ liệu và một tham số nhận dữ liệu, chữ ký nên thể hiện cả hai vai trò:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Ở đây:

1. `source` là **producer**: cung cấp các giá trị kiểu `T` hoặc kiểu con của `T`, vì vậy dùng `? extends T`.
2. `destination` là **consumer**: chấp nhận các giá trị `T`, vì vậy dùng `? super T`.
3. Biến kiểu `T` kết nối hai vai trò; trình biên dịch xác minh quan hệ khi gọi.

Ví dụ:

```java
List<Integer> integers = List.of(2, 4, 6);
List<Number> numbers = new ArrayList<>();

appendAll(integers, numbers); // Hợp lệ.
System.out.println(numbers);  // [2, 4, 6]
```

Nếu viết cả hai tham số thành `List<?>`, không thể an toàn làm `destination.add(source.get(0))`, vì mỗi wildcard có thể đại diện cho kiểu khác nhau. Nếu viết tham số nguồn thành `List<T>`, API không thể hiện linh hoạt bằng `? extends T` trong trường hợp cần nhận một subtype của `T` đã xác định từ đích.

Đây là một trong các trường hợp PECS hữu ích nhất: **đầu vào cung cấp giá trị → `extends`; đầu ra nhận giá trị → `super`**.

Ví dụ gần gũi của thư viện chuẩn là `Collection.addAll(Collection<? extends E> c)`: đối số `c` được đọc để bổ sung phần tử vào collection đích, nên dùng `? extends E`.

Lưu ý: phương thức `appendAll` viết bằng vòng lặp. Nếu `source` và `destination` tham chiếu cùng một `ArrayList`, thêm phần tử trong lúc đang duyệt có thể dẫn tới `ConcurrentModificationException` hoặc hành vi không mong muốn. Nếu cho phép nguồn và đích trùng nhau, hãy thiết kế yêu cầu rõ ràng và cân nhắc tạo snapshot trước.

## 8. Chương trình Java 17+ chạy được

Ví dụ độc lập sau minh họa nguồn cung cấp số, chuỗi ký tự và thao tác sao chép an toàn sang đích. Không cần thư viện ngoài JDK.

Tạo tệp **`ProducerExtendsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;

public class ProducerExtendsDemo {
    static double sum(Iterable<? extends Number> source) {
        double result = 0.0;
        for (Number n : source) {
            result += n.doubleValue();
        }
        return result;
    }

    static String joinText(Iterable<? extends CharSequence> source) {
        StringJoiner joined = new StringJoiner(" | ");
        for (CharSequence value : source) {
            joined.add(value.toString());
        }
        return joined.toString();
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static List<Number> twice(List<? extends Number> source) {
        List<Number> output = new ArrayList<>();
        for (Number value : source) {
            output.add(value.doubleValue() * 2);
        }
        return output;
    }

    public static void main(String[] args) {
        List<Integer> ints = List.of(2, 4, 6);
        List<Double> doubles = List.of(1.5, 2.5);

        System.out.println("sum integers = " + sum(ints));
        System.out.println("sum doubles = " + sum(doubles));

        List<Number> mixed = new ArrayList<>();
        appendAll(ints, mixed);
        appendAll(doubles, mixed);
        System.out.println("mixed = " + mixed);

        System.out.println("twice = " + twice(doubles));

        List<StringBuilder> words = List.of(
                new StringBuilder("A"),
                new StringBuilder("B"));
        System.out.println("text = " + joinText(words));
    }
}
```

Biên dịch và chạy:

```bash
javac ProducerExtendsDemo.java
java ProducerExtendsDemo
```

**Stdout chính xác:**

```text
sum integers = 12.0
sum doubles = 4.0
mixed = [2, 4, 6, 1.5, 2.5]
twice = [3.0, 5.0]
text = A | B
```

Cách đọc kết quả:

- `sum(ints)` và `sum(doubles)` cùng gọi được vì `Iterable<? extends Number>` chấp nhận hai nguồn phần tử khác nhau; các phần tử được đọc dưới dạng `Number`.
- `appendAll` chuyển giá trị từ hai nguồn riêng biệt vào một `List<Number>` có khả năng nhận cả `Integer` lẫn `Double`.
- `twice` chỉ **đọc** danh sách nguồn và tạo một **danh sách mới** chứa các `Double` được tự động boxing để gán vào `List<Number>`. Nó không chỉnh sửa `doubles`.
- `joinText` chấp nhận `List<StringBuilder>` vì `StringBuilder` triển khai `CharSequence`.

Phần mã minh họa sự khác nhau giữa **kiểu nguồn cho phép đọc rộng** và **kiểu kết quả/đích xác định rõ**. Wildcard trên tham số nguồn không bắt buộc kiểu trả về cũng phải là wildcard.

## 9. So sánh `? extends T`, `T` và `? super T` trong chữ ký

Giả sử có:

```java
static void readNumbers(List<? extends Number> source) { /* đọc */ }
static void updateNumbers(List<Number> list) { /* đọc và thêm Number */ }
static void putIntegers(List<? super Integer> destination) { /* thêm Integer */ }
```

Ba chữ ký phục vụ ba nhu cầu khác nhau:

| Nhu cầu | Kiểu tham số phù hợp | Lý do |
| --- | --- | --- |
| Đọc số từ `List<Integer>`, `List<Double>`, `List<Number>` | `List<? extends Number>` | Mọi phần tử đọc được như `Number` |
| Đọc và thêm `Number` bất kỳ vào đúng một danh sách cho phép mọi `Number` | `List<Number>` | Biết chính xác kiểu phần tử cho cả đọc và ghi |
| Thêm `Integer` vào `List<Integer>` hoặc `List<Number>` hoặc `List<Object>` | `List<? super Integer>` | Đích chắc chắn tiếp nhận `Integer` |
| Chỉ cần duyệt số, không cần `List` cụ thể | `Iterable<? extends Number>` | Hợp đồng nguồn tối thiểu |
| Cần đọc từ nguồn và ghi sang đích khác có quan hệ kiểu | `<T>` với `? extends T` / `? super T` | Mô tả và kiểm tra mối quan hệ |

Bảng này nói về **khả năng được hệ kiểu chấp nhận**, không bảo đảm một collection cụ thể luôn hỗ trợ sửa đổi lúc chạy.

Một lời khuyên thiết kế: nếu phương thức nhận nguồn chỉ để đọc, hãy diễn tả bằng `? extends T` ngay trong chữ ký; đừng yêu cầu người gọi ép kiểu hoặc tự sao chép `List<Integer>` thành `List<Number>` khi không cần.

## 10. Những lỗi và hiểu lầm thường gặp

### 10.1. Dùng `List<Number>` cho tham số chỉ đọc

```java
static void printAll(List<Number> numbers) {
    for (Number n : numbers) {
        System.out.println(n);
    }
}
```

Nếu muốn nhận cả `List<Integer>` và `List<Double>`, đổi tham số thành `List<? extends Number>`. Không nên ép kiểu không an toàn để qua mặt trình biên dịch.

### 10.2. Tưởng `extends` là quyền thêm mọi subtype

Đây là cách hiểu sai:

```java
static void addSample(List<? extends Number> source) {
    // source.add(Integer.valueOf(1)); // LỖI BIÊN DỊCH.
    // source.add(Double.valueOf(2));  // LỖI BIÊN DỊCH.
}
```

`? extends Number` nghĩa là **một kiểu con chưa biết**, không phải danh sách trộn tùy ý mọi kiểu con của `Number`. Khi thật sự cần trộn `Integer` và `Double`, hãy tạo hoặc nhận `List<Number>`.

### 10.3. Nhầm một tham số producer với một đối tượng bất biến

`List<? extends Number>` vẫn có thể tham chiếu tới `ArrayList<Integer>` có thể chỉnh sửa. `clear()` và `remove(...)` có thể biên dịch. Muốn cam kết phương thức không sửa collection thì phải tuân theo thiết kế đó, có thể dùng defensive copy/unmodifiable view khi cần hợp đồng mạnh hơn. **Wildcard không phải một cơ chế bảo đảm bất biến dữ liệu.**

### 10.4. Lạm dụng wildcard cho kiểu trả về

`static List<? extends Number> createNumbers()` có thể hợp lệ, nhưng buộc phía gọi phải xử lý một kiểu phần tử không xác định, kể cả khi người viết API biết chính xác danh sách mình tạo ra.

Nếu trả về một danh sách số có thể thêm nhiều subtype, `List<Number>` thường rõ hơn. Nếu luôn tạo danh sách `Integer`, trả về `List<Integer>` rõ hơn. Ưu tiên wildcard ở **tham số** khi muốn mở rộng những đầu vào được chấp nhận; lựa chọn kiểu trả về theo hợp đồng đầu ra thật sự.

### 10.5. Dùng `List<?>` dù thuật toán cần `Number`

`List<?>` có thể nhận `List<String>`, nên `get()` chỉ sử dụng an toàn như `Object`. Nếu thuật toán gọi `doubleValue()`, giới hạn `? extends Number` giúp trình biên dịch bảo đảm mọi phần tử phù hợp và tránh kiểm tra/ép kiểu không cần thiết.

### 10.6. Nhầm wildcard với generic type parameter

Có thể viết hàm đơn giản chỉ đọc:

```java
static void inspect(List<? extends Number> source) {
    for (Number number : source) {
        System.out.println(number);
    }
}
```

Không nhất thiết phải viết:

```java
static <T extends Number> void inspectTyped(List<T> source) {
    for (T number : source) {
        System.out.println(number);
    }
}
```

Hai chữ ký đều dùng được cho nhiều loại `Number`. Nếu `T` xuất hiện **chỉ một lần** và không cần gọi thêm thao tác yêu cầu một kiểu cụ thể thống nhất, wildcard thường gọn hơn. Khi phải thể hiện **quan hệ giữa nhiều tham số hoặc giữa đầu vào và đầu ra**, generic type parameter `<T>` thường có giá trị hơn.

### 10.7. Cho rằng `extends` tự động chuyển hoặc sao chép danh sách

`List<? extends Number> source = integers` chỉ tạo **tham chiếu** đến cùng danh sách; nó không xây dựng một `List<Number>` mới và không chuyển mọi phần tử thành `Number` theo cách sao chép.

Nếu muốn một danh sách mới có kiểu `List<Number>` để thêm đa dạng số, có thể tạo:

```java
List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(4.5);
```

Constructor này tạo danh sách mới về cấu trúc; các phần tử đã có được sao chép tham chiếu (shallow copy).

### 10.8. Tưởng `List<int>` có thể dùng làm nguồn

Generics Java nhận **kiểu tham chiếu**, nên `List<int>` không hợp lệ. Với số nguyên primitive, dùng `List<Integer>` và cơ chế boxing/unboxing hoặc chọn `IntStream` trong thuật toán mà stream primitive phù hợp hơn.

## 11. Bài tập nhận diện producer

Xét ba phương thức sau và xác định wildcard nào nên dùng:

**Tình huống A — xem tên đối tượng:** Phương thức duyệt danh sách các đối tượng có interface `CharSequence`, gọi `length()` và in kết quả; không thêm gì vào danh sách. Câu trả lời phù hợp là `Iterable<? extends CharSequence>`. Điều này nhận được `List<String>` và `List<StringBuilder>`.

**Tình huống B — tổng hợp số:** Phương thức tính tổng từ `Collection<Integer>`, `Collection<Double>` hoặc `Collection<Number>` bằng `doubleValue()`. Câu trả lời phù hợp là `Collection<? extends Number>` (hoặc `Iterable<? extends Number>` nếu không cần API riêng của `Collection`).

**Tình huống C — thêm phần tử từ nguồn vào đích:** Nguồn `List<Integer>` và đích `List<Number>`, đồng thời muốn thuật toán có thể dùng cho các cặp kiểu tương thích khác. Câu trả lời phù hợp là `<T> void appendAll(List<? extends T> source, List<? super T> destination)`.

Kiểm tra nhanh các khai báo sau:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(1.5, 2.5);
List<? extends Number> source1 = ints;    // Hợp lệ.
List<? extends Number> source2 = doubles; // Hợp lệ.

Number a = source1.get(0);                // Hợp lệ.
// source1.add(3);                        // LỖI BIÊN DỊCH.
// List<Number> nums = ints;              // LỖI BIÊN DỊCH.
```

Điều cần ghi nhớ ở tất cả tình huống: **mở rộng tập kiểu đầu vào được nhận** bằng wildcard chỉ có ý nghĩa khi thao tác thực tế vẫn giữ an toàn kiểu; nếu phương thức cần đưa phần tử vào chính nguồn, hãy đánh giá lại vai trò của tham số và chữ ký.

## Ghi nhớ

- **Producer** là tham số **cung cấp phần tử** cho thuật toán đọc; thường khai báo `? extends T`.
- `? extends T` giúp phương thức đọc được các phần tử như `T` từ collection có kiểu phần tử `T` hoặc subtype của `T`.
- **Generics bất biến**, nên `List<Integer>` không phải `List<Number>`; wildcard giải quyết nhu cầu nhận nguồn rộng hơn.
- `List<? extends T>` **không cho thêm giá trị không-null kiểu cụ thể** vào nguồn, vì kiểu phần tử thật chưa được biết.
- `extends` **không đồng nghĩa immutable**, không tự sao chép danh sách và không bảo đảm collection hỗ trợ sửa đổi.
- Khi có nguồn và đích, kết hợp **`? extends T` cho nguồn** và **`? super T` cho đích**.
- Chọn `Iterable`, `Collection` hoặc `List` theo đúng thao tác mà thuật toán cần; ưu tiên interface nhỏ nhất diễn đạt đủ hợp đồng.

Một chữ ký phương thức được thiết kế đúng vai trò sẽ nhận được nhiều loại đầu vào hơn mà không cần unchecked cast, đồng thời ngăn các thao tác ghi không an toàn ngay từ khi biên dịch.
