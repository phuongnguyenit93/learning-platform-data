# Quan hệ tương thích giữa các kiểu wildcard

## 1. Hiểu đúng câu hỏi: biến bên phải có gán được cho kiểu bên trái không?

Wildcard `?` biểu diễn một đối số kiểu chưa biết trong kiểu tổng quát. Khi viết `List<? extends Number>`, ta biết kiểu phần tử thực tế là một kiểu nào đó nằm dưới hoặc bằng `Number`; ta chưa biết đó là `Integer`, `Double` hay kiểu cụ thể nào khác.

Bài này xét **tính tương thích khi gán và truyền đối số**, theo kiểu được khai báo tại thời điểm biên dịch. Các quy tắc thuộc generics được đưa vào từ Java 5 và vẫn áp dụng trên Java hiện đại; ví dụ dùng Java 17+.

Dùng quan hệ quen thuộc:

```text
Integer <: Number <: Object
```

Ký hiệu `S <: T` nghĩa là `S` là kiểu con của `T`. Với một phép gán `đích = nguồn`, hãy hỏi: **mọi đối tượng được phép xuất hiện qua kiểu của nguồn có đáp ứng hợp đồng của đích không?**

Đừng chỉ nhìn đối tượng đang được tạo bằng `new`. Ví dụ:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> source = integers;

// List<Integer> target = source; // Không biên dịch.
```

Biến `source` hiện trỏ đến danh sách số nguyên, nhưng kiểu khai báo của nó chỉ cam kết một kiểu phần tử chưa biết là kiểu con của `Number`. Phép gán cuối không được phép dựa vào lịch sử khởi tạo để khẳng định kiểu đó chính xác là `Integer`.

Các đoạn ngắn trong bài là mã minh họa trong một phương thức, với `import java.util.List;` và `import java.util.ArrayList;`. Mục 7 có chương trình hoàn chỉnh.

## 2. Nền tảng: kiểu tổng quát là bất biến

Từ `Integer <: Number`, không được suy ra:

```text
List<Integer> <: List<Number>
```

Hai kiểu `List<Integer>` và `List<Number>` có hợp đồng khác nhau. Một biến `List<Number>` cho phép thêm cả `Integer` lẫn `Double`. Nếu nó được phép trỏ đến `List<Integer>`, thao tác thêm số thực sẽ phá vỡ hợp đồng của danh sách số nguyên.

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Không biên dịch.
// numbers.add(2.5);                // Lý do phép gán trên phải bị cấm.
```

Chiều ngược lại cũng không tự động hợp lệ:

```java
List<Number> numbers = new ArrayList<>();
// List<Integer> integers = numbers; // Không biên dịch.
```

Danh sách số có thể chứa `Double`, nên không thể xem mọi phần tử là `Integer`.

Wildcard tạo ra các kiểu đích linh hoạt hơn bằng cách giảm những điều mà người sử dụng được phép giả định. **Gán sang kiểu wildcard không sao chép danh sách hay đổi kiểu phần tử thực tế**; nó thay đổi góc nhìn kiểu tĩnh đối với cùng đối tượng.

## 3. Cận trên: chiều của quan hệ được giữ nguyên

Với `S <: T`, có thể dùng chuỗi:

```text
List<S> → List<? extends S> → List<? extends T> → List<?>
```

Mũi tên ở đây nghĩa là có thể gán từ trái sang phải, không cần ép kiểu.

Ví dụ:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Integer> integerView = integers;
List<? extends Number> numberView = integerView;
List<? extends Object> objectView = numberView;
List<?> unknownView = objectView;
```

Lý do: nếu kiểu phần tử chưa biết chắc chắn nằm dưới `Integer`, nó cũng chắc chắn nằm dưới `Number`. Khi chuyển sang `numberView`, ta đã bỏ bớt thông tin; không được lấy lại thông tin đó bằng phép gán ngược:

```java
List<? extends Number> numbers = new ArrayList<Double>();
// List<? extends Integer> integers = numbers; // Không biên dịch.
// List<Number> exactNumbers = numbers;        // Không biên dịch.
```

Dòng thứ hai thất bại vì kiểu chưa biết có thể là `Double`. Dòng thứ ba thất bại vì `List<Number>` cho phép thêm một `Number` tùy ý, trong khi `numbers` có thể trỏ đến `List<Double>`.

Qua `List<? extends Number>`, kết quả `get(i)` dùng được như `Number`. Không thể `add` một giá trị `Integer` hay `Double` tùy ý: kiểu phần tử thực tế chưa được biết.

Một cách đọc hữu ích: **mở rộng cận trên làm kiểu đích chấp nhận nhiều nguồn hơn, đồng thời làm thông tin đọc được ít cụ thể hơn**.

## 4. Cận dưới: chiều của quan hệ đảo lại

Với `S <: T`, chiều hợp lệ là:

```text
List<T> → List<? super T> → List<? super S> → List<?>
```

Áp dụng cho `Integer <: Number <: Object`:

```java
List<Object> objects = new ArrayList<>();
List<? super Object> objectSink = objects;
List<? super Number> numberSink = objectSink;
List<? super Integer> integerSink = numberSink;
```

Tại sao `List<? super Number>` gán được cho `List<? super Integer>`?

- `List<? super Number>` có thể đại diện cho danh sách có đối số kiểu là `Number` hoặc `Object`.
- Cả `Number` và `Object` đều là kiểu cha của `Integer`.
- Vì vậy, cả hai đều đáp ứng lời hứa của `List<? super Integer>`: có thể nhận một `Integer`.

Chiều ngược lại không hợp lệ:

```java
List<? super Integer> integers = new ArrayList<Integer>();
// List<? super Number> numbers = integers; // Không biên dịch.
```

Nếu phép gán được phép, người dùng `numbers` có thể thêm `Double` vào danh sách số nguyên.

Điểm dễ nhầm là kiểu trông “rộng” hơn lại cho ít thao tác ghi hơn:

```java
List<Number> actual = new ArrayList<>();
List<? super Number> acceptsNumbers = actual;
List<? super Integer> acceptsIntegers = acceptsNumbers;

acceptsNumbers.add(2.5);   // Hợp lệ: nhận Number.
acceptsIntegers.add(10);   // Hợp lệ: nhận Integer.
// acceptsIntegers.add(2.5); // Không biên dịch: không còn cam kết nhận Double.

Object value = acceptsIntegers.get(0);
// Number n = acceptsIntegers.get(0); // Không biên dịch.
```

Không thể đọc trực tiếp thành `Number` vì một biến `List<? super Integer>` cũng có thể trỏ đến `List<Object>`, nơi đã chứa chuỗi hoặc đối tượng khác. Khi chỉ dựa vào khai báo `List<? super Integer>`, kiểu đọc an toàn là `Object`.

## 5. Bảng gán để tự kiểm tra

Trong bảng, **hàng là kiểu nguồn**, **cột là kiểu đích**. “Có” nghĩa là phép gán trực tiếp hợp lệ, không có ép kiểu hay raw type.

| Kiểu nguồn | `List<Integer>` | `List<Number>` | `List<? extends Number>` | `List<? super Integer>` | `List<? super Number>` | `List<?>` |
| --- | --- | --- | --- | --- | --- | --- |
| `List<Integer>` | Có | Không | Có | Có | Không | Có |
| `List<Number>` | Không | Có | Có | Có | Có | Có |
| `List<Object>` | Không | Không | Không | Có | Có | Có |
| `List<? extends Integer>` | Không | Không | Có | Không | Không | Có |
| `List<? extends Number>` | Không | Không | Có | Không | Không | Có |
| `List<? super Number>` | Không | Không | Không | Có | Có | Có |
| `List<? super Integer>` | Không | Không | Không | Có | Không | Có |
| `List<?>` | Không | Không | Không | Không | Không | Có |

Cách suy luận một ô mà không học thuộc:

1. Liệt kê những đối số kiểu mà nguồn cho phép.
2. Kiểm tra liệu đích có chấp nhận tất cả các khả năng đó không.
3. Kiểm tra lại bằng quyền đọc/ghi mà đích cung cấp.

Ví dụ, nguồn `List<? super Number>` có thể là `List<Object>`, nên nó không gán được cho `List<? extends Number>`. Nguồn `List<? extends Number>` có thể là `List<Double>`, nên nó không gán được cho `List<? super Integer>`.

### 5.1. Một nguồn cụ thể có thể đi vào hai họ wildcard

```java
List<Number> numbers = new ArrayList<>();

List<? extends Number> reader = numbers;
List<? super Integer> writer = numbers;
```

Hai phép gán đều đúng, nhưng không suy ra `reader` gán được cho `writer`. Mỗi biến đã mất một phần thông tin khác nhau.

```java
// writer = reader; // Không biên dịch.
// reader = writer; // Không biên dịch.
```

Quan hệ “cùng nhận được một nguồn” không đồng nghĩa với quan hệ kiểu con giữa hai kiểu đích.

### 5.2. Wildcard không cận không phải danh sách Object

Với khai báo `List<E>`, `List<?>` và `List<? extends Object>` diễn đạt cùng giới hạn không cận. Có thể gán hai chiều giữa chúng.

```java
List<?> any = new ArrayList<String>();
List<? extends Object> alsoAny = any;
any = alsoAny;

// List<Object> objects = any; // Không biên dịch.
```

`List<Object>` biết chính xác đối số kiểu là `Object` và cho phép thêm đối tượng tùy ý. `List<?>` không biết đối số kiểu nên không có quyền đó.

### 5.3. Đừng suy diễn mọi kết luận từ việc lớp là final

Dù `Integer` là `final`, một biểu thức có kiểu `List<? extends Integer>` vẫn không được gán trực tiếp cho `List<Integer>`. Quy tắc chuyển đổi vẫn xử lý wildcard như một đối số kiểu chưa biết; đừng thay nó bằng kiểu cận chỉ vì suy luận ngoài chương trình rằng không có lớp con cụ thể nào.

## 6. Liên hệ giữa tương thích kiểu và quyền thao tác

| Kiểu biến | Kiểu đọc an toàn từ `get` | Giá trị không null có thể truyền trực tiếp cho `add` |
| --- | --- | --- |
| `List<Number>` | `Number` | `Number` và các kiểu con |
| `List<? extends Number>` | `Number` | Không có kiểu cụ thể nào được bảo đảm |
| `List<? super Integer>` | `Object` | `Integer` |
| `List<?>` | `Object` | Không có kiểu cụ thể nào được bảo đảm |

Bảng mô tả **quyền theo kiểu tĩnh**, chưa bảo đảm thao tác thành công lúc chạy. Một `List` không hỗ trợ thay đổi vẫn có thể ném `UnsupportedOperationException`. Khả năng nhận `null` cũng phụ thuộc cách cài đặt.

Wildcard cận trên không biến đối tượng thành bất biến. Chẳng hạn, `clear()` hoặc `remove(Object)` có thể được gọi theo kiểu tĩnh; chúng thành công nếu danh sách hỗ trợ thao tác. Một biến khác trỏ đến cùng danh sách cũng có thể sửa nó.

Quy tắc PECS giúp thiết kế tham số:

- Nguồn cung cấp phần tử kiểu `T`: dùng `? extends T`.
- Đích nhận phần tử kiểu `T`: dùng `? super T`.
- Cần ràng buộc nhiều vị trí dùng cùng một kiểu: khai báo tham số kiểu có tên, chẳng hạn `<T>`.

PECS giải thích hướng đọc/ghi; bảng tương thích giải thích kiểu đối số nào được truyền vào từng tham số.

## 7. Chương trình hoàn chỉnh: cận trên và cận dưới gặp nhau tại T

Lưu thành `WildcardCompatibilityDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCompatibilityDemo {
    static <T> void copyAll(List<? extends T> source,
                            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        integers.add(1);
        integers.add(2);
        integers.add(3);

        List<? extends Integer> narrowReader = integers;
        List<? extends Number> numberReader = narrowReader;

        List<Object> objects = new ArrayList<>();
        List<? super Number> numberWriter = objects;
        List<? super Integer> integerWriter = numberWriter;

        copyAll(numberReader, numberWriter);
        integerWriter.add(4);

        Number first = numberReader.get(0);
        Object firstObject = integerWriter.get(0);

        System.out.println("first = " + first);
        System.out.println("objects = " + objects);
        System.out.println("firstObject = " + firstObject);
        System.out.println("same = " + (objects == integerWriter));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all WildcardCompatibilityDemo.java
java WildcardCompatibilityDemo
```

Stdout chính xác:

```text
first = 1
objects = [1, 2, 3, 4]
firstObject = 1
same = true
```

Trong lời gọi `copyAll(numberReader, numberWriter)`, có thể dùng `T = Number`: nguồn cung cấp các giá trị đọc được thành `Number`, còn đích nhận được `Number`. Việc lấy từng phần tử ra rồi thêm vào đích hợp lệ **không có nghĩa** ta được gán cả biến nguồn cho biến đích; hai thao tác cần những hợp đồng khác nhau.

`copyAll` thực sự sao chép các tham chiếu phần tử vào danh sách đích. Các phép gán `narrowReader`, `numberReader`, `numberWriter`, `integerWriter` chỉ tạo các góc nhìn kiểu tĩnh lên những danh sách đã có. Dòng `same = true` chứng minh hai biến sau cùng trỏ đến một đối tượng.

## 8. Hai giới hạn thường gặp khi áp dụng

### 8.1. Hai dấu hỏi không hứa cùng một kiểu

```java
static void invalidTransfer(List<? extends Number> source,
                            List<? extends Number> destination) {
    // destination.add(source.get(0)); // Không biên dịch.
}
```

Nguồn có thể là `List<Integer>`, đích có thể là `List<Double>`. Cùng cận trên `Number` không làm hai kiểu bị che giấu trở thành một. Trình biên dịch dùng cơ chế bắt giữ wildcard (wildcard capture) để theo dõi các kiểu chưa biết; lỗi có thể đề cập đến `CAP#1`.

Nếu đích cần nhận phần tử, dùng hợp đồng như `copyAll`, thay vì ép kiểu để vượt lỗi. Khi cần giữ nguyên một kiểu phần tử qua nhiều thao tác, một phương thức trợ giúp có `<T>` có thể đặt tên cho kiểu bị bắt giữ. Đó là cách duy trì quan hệ kiểu đã có, không tạo quan hệ mới giữa hai wildcard độc lập.

### 8.2. Quan hệ không tự lan qua lớp bao bên ngoài

```java
List<List<Integer>> nested = new ArrayList<>();

// Không biên dịch: List ở lớp ngoài vẫn bất biến.
// List<List<? extends Number>> bad = nested;

List<? extends List<? extends Number>> good = nested;
```

Mặc dù `List<Integer>` gán được cho `List<? extends Number>`, việc đặt hai kiểu ấy vào một `List` bên ngoài không tự bảo toàn quan hệ.

Nếu phép gán bị cấm ở trên được cho phép, biến `bad` có thể thêm `List<Double>` vào một danh sách vốn chỉ chấp nhận `List<Integer>`. Wildcard ở lớp ngoài trong `good` giới hạn quyền thêm phần tử và khôi phục tính an toàn.

## 9. Luyện suy luận trước khi biên dịch

Giả sử các biến sau đã được khai báo:

```java
List<? extends Integer> a = new ArrayList<Integer>();
List<? extends Number> b = new ArrayList<Number>();
List<? super Number> c = new ArrayList<Object>();
List<? super Integer> d = new ArrayList<Integer>();
List<?> e = new ArrayList<String>();
```

Hãy quyết định từng dòng độc lập có biên dịch không:

| Phép gán | Kết quả | Lý do |
| --- | --- | --- |
| `b = a;` | Có | Cận trên đi từ `Integer` lên `Number` |
| `a = b;` | Không | Nguồn không bảo đảm phần tử nằm dưới `Integer` |
| `d = c;` | Có | Mọi kiểu cha của `Number` cũng là kiểu cha của `Integer` |
| `c = d;` | Không | Nguồn có thể là `List<Integer>`, không nhận được mọi `Number` |
| `e = c;` | Có | Bỏ thông tin cận dưới, giữ góc nhìn kiểu phần tử chưa biết |
| `b = c;` | Không | Nguồn có thể là `List<Object>` |
| `d = b;` | Không | Nguồn có thể là `List<Double>` |
| `List<Number> n = b;` | Không | Cận trên không khẳng định đối số kiểu chính xác là `Number` |

Khi gặp lỗi “incompatible types”, hãy kiểm tra đúng chiều nguồn → đích, xác định cận trên hay cận dưới và dùng một trường hợp phản ví dụ như `List<Double>` hoặc `List<Object>`. Không dùng raw type, ép kiểu không được kiểm tra hay `@SuppressWarnings` để biến một quan hệ không an toàn thành có vẻ hợp lệ.

## Tài liệu đối chiếu

- [JLS §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): quy tắc chứa nhau giữa đối số kiểu.
- [JLS §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2): quan hệ kiểu con khi có đối số kiểu.
- [Oracle — Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html): sơ đồ cận trên và cận dưới.
- [Oracle — Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): quyền đọc/ghi và giới hạn của cách gọi “chỉ đọc”.
