# Tính bất biến của generic và tính hiệp biến của mảng trong Java

## 1. Mục tiêu và bối cảnh

Trong Java, `Integer` kế thừa `Number`, nhưng hai khai báo sau **không** có cùng quy tắc gán:

- `Integer[]` có thể gán cho biến kiểu `Number[]`: **mảng có tính hiệp biến (covariance)** đối với kiểu phần tử tham chiếu.
- `List<Integer>` không thể gán cho biến kiểu `List<Number>`: **generic mặc định bất biến (invariance)** theo tham số kiểu.

Phân biệt hai quy tắc này giúp tránh lỗi biên dịch khi thiết kế API với `List<T>`, hiểu `ArrayStoreException`, và sử dụng `? extends` / `? super` đúng mục đích. Bài này xét **quan hệ kiểu**; bản thân từ khóa `extends` trong wildcard không biến `List<Integer>` thành `List<Number>`.

## 2. Nền tảng: quan hệ kiểu con

Giả sử `Integer` là kiểu con của `Number`, ký hiệu `Integer <: Number`. Khi đó:

```java
Number n = Integer.valueOf(42); // Hợp lệ: Integer là một Number
Object o = n;                   // Hợp lệ: Number là một Object
```

Tuy nhiên, quan hệ giữa **kiểu phần tử** không tự động quyết định quan hệ giữa các kiểu chứa phần tử:

| Biểu thức kiểu | Có phải quan hệ kiểu con hợp lệ? | Lý do |
| --- | --- | --- |
| `Integer <: Number` | Có | Kế thừa lớp |
| `Integer[] <: Number[]` | Có | Hiệp biến của mảng tham chiếu |
| `List<Integer> <: List<Number>` | Không | Bất biến của tham số generic |
| `List<Integer> <: List<? extends Number>` | Có | Wildcard giới hạn trên chấp nhận danh sách số |
| `List<Number> <: List<? super Integer>` | Có | Wildcard giới hạn dưới chấp nhận kiểu chứa Integer |

Dấu `<:` trong bảng là ký hiệu giải thích quan hệ kiểu con, không phải cú pháp Java.

## 3. Tính bất biến của generic (invariance)

Với cùng một kiểu generic, chẳng hạn `List<T>`, Java **không** coi `List<Integer>` là kiểu con của `List<Number>`, và cũng không coi chiều ngược lại là hợp lệ, dù `Integer` là kiểu con của `Number`.

```java
import java.util.List;

List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = integers; // LỖI BIÊN DỊCH: incompatible types
```

Đây là lỗi có chủ đích của hệ thống kiểu. Giả sử phép gán trên được phép:

```java
// GIẢ ĐỊNH (không biên dịch được trong Java):
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers;
numbers.add(3.14);                 // Double cũng là Number
Integer value = integers.get(0);  // Không thể an toàn nếu phần tử là Double
```

`List<Number>` cho phép thêm `Double`, `Long` hoặc `Integer`. Ngược lại, một `List<Integer>` phải giữ đúng phần tử kiểu `Integer`. Nếu cùng một đối tượng được xem qua cả hai kiểu trên, khả năng ghi qua biến `List<Number>` sẽ phá hợp đồng của biến `List<Integer>`. **Bất biến ngăn nguy cơ này ngay khi biên dịch.**

Cần phân biệt hai tình huống:

```java
List<Integer> a = new ArrayList<Integer>(); // Đúng
List<Integer> b = new ArrayList<>();        // Đúng: suy luận kiểu
List<Number>  c = new ArrayList<Integer>(); // Sai: tham số kiểu khác nhau
```

`ArrayList<Integer>` là một `List<Integer>` vì `ArrayList<T>` triển khai `List<T>` với **cùng** `T`; điều đó không làm cho `List<Integer>` trở thành `List<Number>`.

Muốn có một `List<Number>` độc lập từ các phần tử `Integer`, hãy tạo danh sách đích và sao chép giá trị:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(integers); // Đúng: tạo list khác
numbers.add(3.14);                                // Đúng: list đích chứa Number
```

Điều này là **sao chép các tham chiếu phần tử vào một cấu trúc chứa mới**, không phải ép kiểu giữa `List<Integer>` và `List<Number>`.

## 4. Tính hiệp biến của mảng (array covariance)

Với các kiểu phần tử **tham chiếu**, nếu `Integer <: Number` thì `Integer[] <: Number[]`. Do đó:

```java
Integer[] integers = {1, 2};
Number[] numbers = integers; // Hợp lệ ở thời điểm biên dịch
numbers[0] = 3;              // Hợp lệ: Integer được lưu vào Integer[]
numbers[1] = 3.14;           // Biên dịch được, nhưng ném ArrayStoreException
```

Biến `numbers` có kiểu khai báo `Number[]`, song đối tượng mảng thật được tạo là `Integer[]`. JVM vẫn biết **kiểu phần tử thực tế** của mảng. Khi phép gán phần tử xảy ra, JVM kiểm tra giá trị có tương thích với kiểu phần tử thực tế không. `Double` không thể nằm trong `Integer[]`, nên câu lệnh cuối ném `ArrayStoreException` ngay tại lúc ghi; các phần tử trước đó không bị biến đổi thành `Double`.

Vì vậy, hiệp biến mảng **không bảo đảm mọi thao tác ghi đều an toàn tĩnh**. Java chấp nhận phép gán kiểu mảng nhưng có kiểm tra lúc chạy để giữ an toàn kiểu. Mảng tồn tại từ trước khi generics được bổ sung vào Java; quy tắc hiệp biến được giữ nhằm tương thích với thiết kế ngôn ngữ và API đã có.

Lưu ý phân biệt kiểu mảng:

- `String[]` có thể được nhìn qua `Object[]` vì `String` là kiểu tham chiếu con của `Object`.
- `int[]` **không** là `Number[]` hoặc `Object[]` vì `int` là kiểu nguyên thủy. Tuy vậy, chính đối tượng `int[]` vẫn có thể gán cho biến kiểu `Object`.
- Gán sai phần tử vào mảng tham chiếu có thể gây `ArrayStoreException`; ép kiểu sai một tham chiếu mảng có thể gây `ClassCastException`. Đây là hai thao tác và hai lỗi khác nhau.

## 5. Tại sao hành vi giữa generic và mảng khác nhau?

Có hai đặc điểm cốt lõi:

1. **Mảng mang thông tin kiểu phần tử lúc chạy (reified)**. Một đối tượng `new Integer[2]` biết các vị trí của nó yêu cầu `Integer`. JVM kiểm tra khi ghi.
2. **Phần lớn thông tin tham số generic bị xóa khi biên dịch (type erasure)**. Tại runtime, đối tượng `ArrayList<String>` và `ArrayList<Integer>` nhìn chung đều dùng cùng lớp `ArrayList`; JVM không có kiểm tra kiểu phần tử cụ thể cho mỗi lời gọi thêm phần tử tương tự kiểm tra cửa hàng của mảng.

Với generics, trình biên dịch chủ động chặn phép gán có thể làm hỏng kiểu từ sớm. Với mảng tham chiếu, trình biên dịch cho phép quan hệ hiệp biến và JVM có thể chặn một phép ghi không an toàn khi chạy.

Không nên suy ra rằng **mọi** kiểm tra generic đều biến mất. Trình biên dịch vẫn chèn các phép chuyển kiểu thích hợp tại vị trí sử dụng và JVM vẫn kiểm tra các cast được chèn đó. Type erasure cũng không đồng nghĩa mọi cách dùng raw type hoặc unchecked cast đều an toàn.

## 6. Dùng wildcard để mô tả API với nhiều kiểu phần tử

Wildcard làm biểu thức kiểu linh hoạt hơn mà không phá quy tắc bất biến của `List<T>`.

### 6.1. `? extends Number`: nhận nguồn để đọc

```java
List<Integer> integers = List.of(1, 2);
List<Double> doubles = List.of(1.5, 2.5);

List<? extends Number> first = integers; // Đúng
List<? extends Number> second = doubles; // Đúng

Number x = first.get(0); // Đúng: đọc dưới dạng Number
first.add(10);           // LỖI BIÊN DỊCH
```

`List<? extends Number>` nghĩa là danh sách có kiểu phần tử **một kiểu chưa biết** nằm trong họ `Number`, ví dụ `Integer` hoặc `Double`. Đọc phần tử như `Number` là an toàn; thêm `Integer` vào một danh sách có thể thực chất là `List<Double>` thì không an toàn. Vì vậy `add` không nhận giá trị phần tử thông thường; `add(null)` về mặt kiểu là ngoại lệ hợp lệ nhưng thường không có giá trị nghiệp vụ.

Ví dụ phương thức đọc tổng:

```java
static double sum(List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Phương thức nhận `List<Integer>`, `List<Double>` hoặc `List<Number>` mà không yêu cầu người gọi sao chép dữ liệu. Kết quả là `double`, nên vẫn cần hiểu giới hạn độ chính xác của `double` nếu xử lý tiền tệ hoặc số nguyên rất lớn.

### 6.2. `? super Integer`: nhận đích để ghi

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);     // Đúng: thêm Integer
destination.add(20);     // Đúng
Object item = destination.get(0); // Chỉ đảm bảo là Object
```

Kiểu phần tử thực tế của `List<? super Integer>` có thể là `Integer`, `Number` hoặc `Object`. Mọi danh sách như thế nhận được một giá trị `Integer`, nhưng kết quả đọc ra không thể tự động coi là `Integer` hoặc `Number` bởi có thể là `List<Object>` với các đối tượng khác.

### 6.3. Quy tắc PECS và phương thức sao chép

**PECS = Producer Extends, Consumer Super**: nguồn sinh phần tử để đọc dùng `extends`; đích nhận phần tử để ghi dùng `super`.

```java
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Ví dụ `appendAll(List<Number>, List<Integer>)` hợp lệ. Đây là phương thức **nối thêm** vào cuối đích. Không nhầm nó với `Collections.copy(destination, source)`: phương thức của thư viện **ghi đè theo chỉ số** và yêu cầu danh sách đích có sẵn đủ số phần tử.

Nếu một API **vừa đọc vừa ghi cùng kiểu cụ thể** (chẳng hạn thay thế, hoán đổi giá trị), dùng `List<T>` hoặc helper có type parameter rõ ràng sẽ thường thích hợp hơn wildcard.

## 7. Ví dụ Java 17+ đầy đủ, chạy được

Tạo tệp `QuanHeKieuDemo.java` với nội dung:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class QuanHeKieuDemo {
    static <T> void appendAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(10, 20);
        List<? extends Number> readable = integers;
        System.out.println("Extends read: " + readable.get(0));

        List<Number> numbers = new ArrayList<>();
        List<? super Integer> writable = numbers;
        writable.add(30);
        System.out.println("Super read: " + writable.get(0));

        appendAll(numbers, integers);
        System.out.println("Destination: " + numbers);

        Integer[] actual = {1, 2};
        Number[] view = actual; // Mảng hiệp biến
        System.out.println("Array read: " + view[0]);

        try {
            view[0] = 3.5; // Double không thể lưu vào Integer[]
        } catch (ArrayStoreException exception) {
            System.out.println(
                    "Array store blocked: " + exception.getClass().getSimpleName());
        }
        System.out.println("Array after: " + Arrays.toString(actual));

        List<?>[] genericViews = new List<?>[1];
        genericViews[0] = List.of("x");
        System.out.println("Unbounded wildcard: " + genericViews[0].get(0));
    }
}
```

Biên dịch và chạy trong thư mục có tệp trên:

```bash
javac -encoding UTF-8 QuanHeKieuDemo.java
java QuanHeKieuDemo
```

Đầu ra chính xác:

```text
Extends read: 10
Super read: 30
Destination: [30, 10, 20]
Array read: 1
Array store blocked: ArrayStoreException
Array after: [1, 2]
Unbounded wildcard: x
```

Phân tích thứ tự: `readable` đọc `Integer` như `Number`; `writable` thêm `Integer` vào một `List<Number>`; `appendAll` bổ sung 10 và 20. Mảng thật là `Integer[]`, nên ghi `3.5` bị chặn, còn `[1, 2]` được giữ nguyên. Phần cuối minh họa một mảng chứa các danh sách có wildcard không giới hạn.

## 8. Vì sao không tạo mảng của kiểu generic cụ thể?

Khai báo sau **không biên dịch**:

```java
List<String>[] words = new List<String>[2]; // generic array creation: không hợp lệ
```

Giả sử cách tạo trên hợp lệ. Do erasure, kiểu phần tử runtime không thể phân biệt `List<String>` và `List<Integer>`. Nếu tham chiếu mảng được đưa qua `Object[]`, kiểm tra khi gán phần tử có thể nhìn thấy cùng một kiểu thô `List` và không phát hiện sự sai lệch tham số kiểu `String`. Điều đó phá bảo đảm kiểu của `List<String>[]`. Vì vậy Java cấm tạo trực tiếp các mảng có kiểu phần tử tham số hóa không reifiable.

Ngược lại, trường hợp sau **hợp lệ**:

```java
List<?>[] lists = new List<?>[2];
lists[0] = List.of("a");
lists[1] = List.of(1, 2);
Object first = lists[0].get(0);
```

`List<?>` là kiểu có wildcard không giới hạn, thuộc các trường hợp **reifiable** được phép làm kiểu phần tử của biểu thức tạo mảng. Tuy nhiên, khi đọc danh sách qua `List<?>`, kiểu phần tử chỉ được bảo đảm là `Object`; không thể khẳng định toàn bộ danh sách chứa `String` hay `Integer`.

Trong ứng dụng, khi cần tập hợp danh sách, thường ưu tiên `List<List<String>>` hoặc cấu trúc generic tương ứng thay cho mảng generic. Tránh né bằng raw type, unchecked cast hoặc `@SuppressWarnings("unchecked")` không tự làm kiểu dữ liệu trở nên an toàn.

## 9. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gán `List<Integer>` cho `List<Number>` | Lỗi biên dịch | Nếu chỉ đọc, dùng `List<? extends Number>`; nếu cần danh sách độc lập, tạo `new ArrayList<Number>(integers)` |
| Tưởng `List<? extends Number>` cho phép `add(1)` | Lỗi biên dịch | Dùng `List<? super Integer>` khi mục tiêu là nhận `Integer` |
| Đọc `List<? super Integer>` thẳng thành `Integer` | Lỗi biên dịch | Đọc thành `Object`, hoặc dùng cấu trúc kiểu chính xác hơn |
| Tưởng `Number[] a = new Integer[2]` cho phép ghi `Double` | `ArrayStoreException` lúc chạy | Tạo mảng thật `new Number[2]` nếu cần chứa nhiều loại `Number` |
| Tạo `new List<String>[2]` | Lỗi biên dịch | Dùng `List<List<String>>`, hoặc `List<?>[]` khi thật sự cần mảng kiểu này |
| Dùng raw `List` để lách bất biến | Cảnh báo unchecked, nguy cơ `ClassCastException` sau này | Giữ type parameter và wildcard rõ ràng |

Đặc biệt, `Arrays.asList(1, 2)` tạo một `List<Integer>` có kích thước cố định; đổi biến tham chiếu sang wildcard không làm nó trở thành `List<Number>` hoặc trở thành danh sách có thể thêm phần tử. **Quan hệ kiểu** và **khả năng thay đổi cấu trúc** của từng triển khai danh sách là hai vấn đề độc lập.

## 10. Tự kiểm tra

Với mỗi đoạn, dự đoán **biên dịch được hay không**, và nếu biên dịch được thì có lỗi runtime hay không:

```java
// A
List<? extends Number> a = List.of(1, 2);
Number n = a.get(0);

// B
List<Number> b = List.of(1, 2);

// C
Number[] c = new Integer[1];
c[0] = 1.5;

// D
List<? super Integer> d = new ArrayList<Object>();
d.add(7);
Object o = d.get(0);

// E
Object[] e = new int[2];
```

**Đáp án giải thích:**

- **A:** Hợp lệ, đọc phần tử kiểu `Number`. `List.of(1, 2)` suy ra `List<Integer>`, chấp nhận được ở vị trí `? extends Number`.
- **B:** Hợp lệ: lời gọi `List.of` được suy luận kiểu `Number` theo **target typing** của vế trái; khác với việc lấy một biến đã có kiểu `List<Integer>` rồi gán cho `List<Number>`. Danh sách trả về là bất biến theo nghĩa **không cho thay đổi dữ liệu (unmodifiable)**, một khái niệm riêng với **invariance** của kiểu generic.
- **C:** Biên dịch được; phép ghi `Double` vào đối tượng `Integer[]` ném `ArrayStoreException`.
- **D:** Hợp lệ; `List<Object>` là một đích có thể nhận `Integer`, và khi đọc qua `? super Integer` chỉ suy ra `Object`.
- **E:** Không biên dịch: `int[]` không phải `Object[]`. Có thể viết `Object e = new int[2];` nếu cần tham chiếu tới cả đối tượng mảng.

### Ghi nhớ

`List<S>` và `List<T>` vẫn bất biến dù `S <: T`. Mảng tham chiếu `S[]` hiệp biến với `T[]`, nhưng việc ghi sai phần tử có thể bị JVM từ chối lúc chạy. Khi thiết kế API generic, dùng `? extends T` để đọc từ nguồn và `? super T` để ghi vào đích; dùng tham số kiểu cố định `T` khi phải duy trì quan hệ kiểu chặt chẽ trong cả hai chiều.
