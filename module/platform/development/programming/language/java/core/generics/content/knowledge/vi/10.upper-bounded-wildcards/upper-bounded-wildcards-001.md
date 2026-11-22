# Ý nghĩa của `? extends T` trong Java Generics

## 1. `? extends T` biểu diễn điều gì?

Trong Java Generics, `? extends T` là **upper-bounded wildcard** (wildcard có cận trên). Cú pháp này nói rằng đối số kiểu thực sự của một kiểu generic là **một kiểu chưa biết, nhưng kiểu đó phải là `T` hoặc một kiểu con của `T`**.

```java
List<? extends Number> values;
```

Trong khai báo trên, `values` có thể tham chiếu tới `List<Number>`, `List<Integer>`, `List<Double>`, `List<Long>` và các `List<S>` khác khi `S` là kiểu con của `Number`. Tuy nhiên, tại vị trí dùng biến `values`, trình biên dịch không biết chính xác `S` là kiểu nào.

Có hai phần cần đọc riêng:

- **`?`**: đại diện cho một đối số kiểu chưa biết; nó không phải `Object` và không có nghĩa được ghi giá trị tùy ý.
- **`extends T`**: ràng buộc đối số kiểu chưa biết phải thuộc tập `T` và các kiểu con của `T`; `T` được gọi là *upper bound* (cận trên).

Từ `extends` trong wildcard là một **ràng buộc kiểu**. Nó dùng được cả khi cận trên là một lớp (`Number`) và khi cận trên là một interface (`CharSequence`, `Comparable<?>`...). Không cần cận trên `T` là lớp kế thừa trực tiếp; quan hệ kiểu con gián tiếp cũng hợp lệ.

```java
List<Integer> integers = new ArrayList<>();
List<Double> doubles = new ArrayList<>();
List<Number> numbers = new ArrayList<>();

List<? extends Number> a = integers;
List<? extends Number> b = doubles;
List<? extends Number> c = numbers;
```

Cả ba phép gán đều hợp lệ. Đây là **các phép gán tham chiếu**, không tạo danh sách mới và không chuyển mọi phần tử sang `Number` trong bộ nhớ.

**Điểm quan trọng:** `? extends Number` nói *kiểu phần tử của danh sách nằm dưới cận Number*, chứ không nói *mỗi lần thêm có thể chọn bất kỳ kiểu con nào của Number*.

## 2. Mô hình kiểu ẩn: tại sao biết cận trên vẫn chưa biết kiểu chính xác?

Hãy tưởng tượng một phương thức nhận `List<? extends Number>`. Một bên gọi có thể đưa vào danh sách chỉ chứa `Integer`, bên khác đưa vào danh sách chỉ chứa `Double`. Trong thân phương thức, ta không biết lời gọi nào sẽ xuất hiện.

```java
static void inspect(List<? extends Number> source) {
    Number value = source.get(0); // Hợp lệ khi danh sách không rỗng
}
```

Trình biên dịch có đủ thông tin để kết luận rằng **mọi phần tử đọc ra đều có thể được xem như `Number`**. Nhưng không đủ thông tin để kết luận một `Integer` mới có thể được ghi vào một danh sách vốn có thể là `List<Double>`.

Có thể hình dung mối quan hệ như sau:

```text
                   Number
               /      |      \
          Integer   Double   Long
               \      |      /
          ? extends Number
          (một kiểu ẩn thuộc nhóm trên)
```

Sơ đồ chỉ minh họa các khả năng của cận trên; dấu `?` **không thay đổi kiểu thực** của từng danh sách đang được tham chiếu.

Thực tế, compiler có thể dùng một *capture type* nội bộ (ví dụ một tên biểu diễn kiểu ẩn như `CAP#1`) để ghi nhớ ràng buộc. Ta không viết tên kiểu nội bộ ấy trong mã nguồn. Điều quan trọng là các thao tác trên `List<? extends Number>` vẫn phải an toàn cho **mọi** kiểu có thể được thay thế vào dấu hỏi.

## 3. Tính bất biến của Generics và vai trò của `extends`

Dù `Integer extends Number`, Java Generics là **invariant** (bất biến đối với đối số kiểu): `List<Integer>` không phải là kiểu con của `List<Number>`.

Đây là đoạn minh họa lỗi biên dịch:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));

// List<Number> numbers = integers; // Không biên dịch
```

Nếu phép gán được phép, người dùng `numbers` có thể thêm `Double` vào một danh sách được hứa chỉ chứa `Integer`. Java ngăn điều đó bằng kiểm tra tại thời điểm biên dịch.

Khi API chỉ **cần lấy ra các giá trị như `Number`**, có thể nới hợp đồng đầu vào thành:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}
```

Giờ cả `List<Integer>` và `List<Double>` đều là đối số hợp lệ. API vẫn bảo đảm các phần tử đọc ra dùng được dưới kiểu `Number`.

| Kiểu đối số truyền vào | `List<Number>` | `List<? extends Number>` |
|---|---|---|
| `List<Number>` | Được | Được |
| `List<Integer>` | Không | Được |
| `List<Double>` | Không | Được |
| `List<java.math.BigDecimal>` | Không | Được |
| `List<Object>` | Không | Không |
| `List<String>` | Không | Không |

`Object` là kiểu cha của `Number`, nên `List<Object>` không đáp ứng `? extends Number`. `String` không kế thừa `Number`. Nhớ rằng việc chấp nhận một đối số danh sách phụ thuộc **tham số kiểu khai báo** của nó, không phải chỉ nhìn vào vài phần tử tình cờ đang có.

## 4. Quyền đọc: cận trên giúp compiler đảm bảo điều gì?

Với `List<? extends Number>`, mọi phần tử đọc ra đều gán an toàn cho `Number` hoặc `Object`:

```java
List<Integer> integers = List.of(10, 20, 30);
List<? extends Number> source = integers;

Number first = source.get(0);  // Được
Object same = source.get(0);   // Được
int size = source.size();      // Được
double value = first.doubleValue();

// Integer exact = source.get(0); // Không được: ? có thể là Double
```

Có thể gọi các phương thức được định nghĩa trên `Number`, chẳng hạn `intValue()`, `longValue()`, `doubleValue()`. Không thể gọi một phương thức chỉ thuộc `Integer` trực tiếp từ giá trị có kiểu tĩnh `Number` nếu chưa kiểm tra hoặc chuyển kiểu phù hợp.

Ví dụ:

```java
static void printAsDouble(List<? extends Number> source) {
    for (Number item : source) {
        System.out.println(item.doubleValue());
    }
}
```

Phương thức này được xác định hợp lệ bởi **cận trên** của wildcard. Nếu cận trên là `CharSequence`, phần tử đọc ra có thể dùng như `CharSequence` và gọi `length()`; không thể giả định đó là `String`.

Chú ý: `source.get(0)` chỉ hợp lệ lúc chạy nếu danh sách có phần tử. `extends` không bảo đảm danh sách không rỗng, không ngăn giá trị `null`, không bảo đảm danh sách mutable, cũng không đảm bảo các giá trị số phù hợp nghiệp vụ. Ví dụ phép `doubleValue()` có thể mất độ chính xác với số nguyên rất lớn hoặc `BigDecimal`; ràng buộc kiểu và độ chính xác số học là hai vấn đề riêng.

## 5. Quyền ghi: vì sao không thể thêm `Integer`, `Double`, hay `Number`?

Khai báo:

```java
List<? extends Number> source = new ArrayList<Integer>();
```

Phía sau `source` có thể là `List<Integer>`. Nếu compiler cho thêm một `Double` thì hợp đồng danh sách gốc bị phá vỡ. Nhưng ngay cả `source.add(123)` cũng không được phép, vì ở một lời gọi khác `source` hoàn toàn có thể tham chiếu `List<Double>`.

```java
List<? extends Number> source =
        new ArrayList<Integer>(List.of(1, 2, 3));

// source.add(42);            // Lỗi biên dịch
// source.add(2.5);           // Lỗi biên dịch
// source.add((Number) 42);   // Vẫn lỗi biên dịch
// source.set(0, 42);         // Lỗi biên dịch
```

Dù đối số ghi là một `Number`, ta chỉ biết kiểu ẩn `S extends Number`. Từ “`Integer` là một `Number`” không suy ra “`Integer` có thể gán cho mọi `S` thuộc các kiểu con của `Number`”.

Một ngoại lệ về type checking là `null`:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> view = integers;

view.add(null); // Biên dịch được vì null có thể gán cho mọi kiểu tham chiếu
```

`ArrayList` ở ví dụ này cho phép null và danh sách thực sự được thêm null. Nhưng **không phải mọi implementation của `List` đều cho phép sửa đổi hoặc thêm null**. Ví dụ `List.of(...)` là danh sách không sửa đổi được; thao tác `add` sẽ ném `UnsupportedOperationException`. Phân biệt rõ **một thao tác được chấp nhận về kiểu** với **một thao tác thành công lúc chạy**.

## 6. Wildcard `extends` không biến danh sách thành immutable

`List<? extends Number>` giới hạn **kiểu giá trị được phép chèn qua tham chiếu**, không biến đối tượng nguồn thành immutable. Nếu nguồn thực là `ArrayList<Integer>`, một alias `List<Integer>` khác vẫn có thể thay đổi phần tử, và những thao tác không cần cung cấp phần tử mới như `clear()` hoặc `remove(int)` vẫn biên dịch qua wildcard.

```java
List<Integer> original = new ArrayList<>(List.of(4, 5, 6));
List<? extends Number> source = original;
source.remove(0);
System.out.println(original); // [5, 6]
```

Với một danh sách unmodifiable, thao tác xóa có thể ném `UnsupportedOperationException`. Muốn bảo vệ nội dung, cần cơ chế quản lý alias, wrapper không sửa được hoặc snapshot; bài riêng về **wildcard và tính bất biến** sẽ phân tích chi tiết các lựa chọn đó.

## 7. Ví dụ Java 17 hoàn chỉnh: đọc, chuyển dữ liệu và giữ an toàn kiểu

Tạo tệp `ExtendsWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ExtendsWildcardDemo {
    static double sum(List<? extends Number> source) {
        double result = 0;
        for (Number n : source) {
            result += n.doubleValue();
        }
        return result;
    }

    static void transfer(
            List<? extends Number> source,
            List<? super Number> destination) {
        for (Number n : source) {
            destination.add(n);
        }
    }

    static void swapFirstTwo(List<? extends Number> source) {
        swapCaptured(source);
    }

    private static <E extends Number> void swapCaptured(List<E> values) {
        if (values.size() < 2) {
            return;
        }
        E first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20, 30));
        List<Double> doubles = List.of(1.5, 2.5);

        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(doubles));

        List<Number> combined = new ArrayList<>();
        transfer(integers, combined);
        transfer(doubles, combined);
        System.out.println("Combined: " + combined);

        List<? extends Number> view = integers;
        Number first = view.get(0);
        System.out.println("First: " + first);

        swapFirstTwo(view);
        System.out.println("After swap: " + integers);

        view.add(null);
        System.out.println("After null: " + integers);
    }
}
```

Biên dịch và chạy:

```bash
javac ExtendsWildcardDemo.java
java ExtendsWildcardDemo
```

Stdout:

```text
Integer sum: 60.0
Double sum: 4.0
Combined: [10, 20, 30, 1.5, 2.5]
First: 10
After swap: [20, 10, 30]
After null: [20, 10, 30, null]
```

Phân tích chương trình:

1. `sum` nhận nguồn có đối số kiểu là `Number` hoặc bất kỳ kiểu con nào. Cơ thể hàm chỉ cần đọc mỗi phần tử dưới kiểu `Number` và lấy `doubleValue()`.
2. `transfer` dùng nguồn `List<? extends Number>` để đọc các số an toàn. Đích `List<? super Number>` là danh sách có kiểu phần tử `Number` hoặc một kiểu cha của nó (`Object`), nên cho phép thêm các giá trị `Number`. `combined` là một `List<Number>` mới, không phải alias của `integers` hoặc `doubles`.
3. `view` cùng tham chiếu `integers`. `get(0)` trả về giá trị có thể đọc an toàn dưới kiểu `Number`.
4. `swapFirstTwo` không tạo một `Integer` hoặc `Double` mới để thêm vào danh sách. Nó đổi chỗ hai phần tử đã có, thông qua helper giữ cùng kiểu phần tử ẩn. Phần 8 giải thích cơ chế này.
5. `view.add(null)` hợp lệ ở mức biên dịch. Vì đối tượng thực là `ArrayList<Integer>`, việc thêm null thành công và kết quả hiển thị trong `integers`. Nếu gọi lại `sum(integers)` sau bước này, vòng lặp sử dụng `n.doubleValue()` trên null sẽ gây `NullPointerException`; ví dụ chủ động tính tổng trước khi thêm null.

Các kết quả số trong ví dụ đều biểu diễn chính xác ở dạng `double` nên stdout xác định rõ. Trong ứng dụng cần tính tiền hoặc độ chính xác thập phân, không nên dùng phép cộng `doubleValue()` thay cho mô hình số học phù hợp.

## 8. Wildcard capture: có thể hoán đổi phần tử như thế nào?

Mỗi `? extends Number` là một **kiểu phần tử chưa biết nhưng nhất quán**. Khi cần ghi lại chính những phần tử đã lấy từ cùng danh sách, helper generic có thể *capture* kiểu ẩn đó:

```java
static void swapFirstTwo(List<? extends Number> source) {
    swapCaptured(source);
}
private static <E extends Number> void swapCaptured(List<E> xs) {
    if (xs.size() < 2) return;
    E first = xs.get(0);
    xs.set(0, xs.get(1));
    xs.set(1, first);
}
```

Compiler cho ghi `E` đã lấy từ chính `xs`, **không** cho thêm một `Number` bất kỳ vào `List<? extends Number>`. Nếu list không cho phép `set`, lời gọi vẫn có thể thất bại lúc chạy. Chương trình hoàn chỉnh ở mục 7 đã minh họa việc hoán đổi; bài về **giới hạn thêm `T`** tiếp tục chứng minh wildcard capture.

## 9. Quy tắc PECS: tại sao `extends` phù hợp với nguồn dữ liệu?

**PECS — Producer Extends, Consumer Super**: nếu tham số cung cấp phần tử mà thuật toán **đọc**, dùng `? extends T`; nếu tham số là nơi thuật toán **ghi** các phần tử `T`, dùng `? super T`.

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) destination.add(value);
}
```

Chữ ký nối một producer chứa `T` hoặc subtype với một consumer có thể nhận `T`. Ví dụ nguồn `List<Integer>`, đích `List<Number>` hợp lệ. Đây là một **quy tắc lựa chọn tham số API**, không hứa source immutable hay destination mutable. Phần thiết kế API đầu vào cung cấp dữ liệu ở cuối chương giải thích cách chọn cả `Iterable`/`Collection`/`List` theo thao tác cần thiết.

## 10. `extends` dùng được với interface

Trong cú pháp wildcard, `extends` dùng cả với interface, ngay cả khi một lớp dùng từ khóa `implements` để triển khai interface đó.

```java
static void showLengths(List<? extends CharSequence> texts) {
    for (CharSequence text : texts) {
        System.out.println(text.length());
    }
}
```

Hàm này nhận `List<String>` hoặc `List<StringBuilder>` vì cả `String` và `StringBuilder` đều triển khai `CharSequence`.

```java
List<String> names = List.of("An", "Binh");
List<StringBuilder> builders =
        List.of(new StringBuilder("Java"));

showLengths(names);
showLengths(builders);
```

Chú ý không thể viết `texts.add("new")` bên trong hàm. Dù `String` là `CharSequence`, danh sách thực tế có thể là `List<StringBuilder>`. Chỉ có **bảo đảm khi đọc** rằng phần tử có thể sử dụng như `CharSequence`.

Khi cần giới hạn bằng nhiều interface, Java có thể khai báo type parameter có nhiều bound, ví dụ `<T extends Number & Comparable<T>>`; đây là cú pháp type parameter có tên và là bài toán khác với wildcard đơn giản `? extends T`. Mỗi wildcard `? extends ...` thường diễn tả một cận trên theo cú pháp kiểu đã chọn.

## 11. So sánh `? extends T`, `T`, `?` và `? super T`

| Cách khai báo với `Number` | Nhận những kiểu danh sách nào? | Kiểu đọc an toàn | Thêm `Integer` bất kỳ? |
|---|---|---|---|
| `List<Number>` | `List<Number>` | `Number` | Có |
| `List<? extends Number>` | `List<Number>` và `List` của các kiểu con `Number` | `Number` | Không |
| `List<?>` | `List` với đối số kiểu bất kỳ | `Object` | Không |
| `List<? super Number>` | `List<Number>`, `List<Object>` | `Object` | Có |

Ở bảng này, “thêm” chỉ là **được compiler cho phép**; đối tượng thực vẫn có thể không hỗ trợ sửa đổi.

`List<?>` và `List<? extends Object>` mang ý nghĩa rất gần nhau: mọi đối số kiểu tham chiếu đều nằm dưới `Object`, nên cận `Object` không giúp nâng mức đảm bảo khi đọc lên cao hơn `Object`. Ngược lại, `List<? extends Number>` đem lại thông tin hữu ích rằng các phần tử thuộc họ `Number`.

Với `List<? super Number>`, giá trị lấy ra chỉ chắc chắn có kiểu `Object` vì danh sách có thể khai báo kiểu phần tử là `Object`. Đổi lại, ta có thể thêm `Number` và các kiểu con, ví dụ `Integer`. Đây là đối xứng **đọc từ cận trên, ghi theo cận dưới**.

## 12. Những lỗi suy luận thường gặp

**Lỗi 1 — “`extends` nghĩa là có thể thêm mọi kiểu con.”** Không. `List<? extends Number>` có thể thực sự là `List<Double>`; thêm một `Integer` là không an toàn. Chỉ cần biết upper bound chưa biết được kiểu chính xác để ghi.

**Lỗi 2 — “`List<Integer>` là `List<Number>`.”** Không. Java Generics bất biến; dùng `List<? extends Number>` khi mục tiêu là chấp nhận nhiều nguồn để đọc như `Number`.

**Lỗi 3 — “Đọc được `Number` thì ghi được `Number`.”** Không. Thông tin đủ để **đọc lên kiểu cha** không đủ để ghi một kiểu cha vào nơi có thể cần kiểu con cụ thể.

**Lỗi 4 — “`extends` làm danh sách immutable.”** Không. `clear()` hoặc `remove(...)` vẫn hợp lệ theo kiểu. Mutability là hợp đồng của implementation và cách cung cấp đối tượng.

**Lỗi 5 — “`? extends Number` chắc chắn là `Integer` nếu trước mắt thấy toàn số nguyên.”** Không. Compiler dựa vào **kiểu tĩnh và upper bound**, không tự suy luận kiểu generic từ những phần tử tình cờ quan sát. `List<Number>` hoàn toàn có thể đang chứa một loạt `Integer` mà vẫn không phải `List<Integer>`.

**Lỗi 6 — “Ép `(List<Integer>)` sẽ biến một `List<? extends Number>` thành danh sách số nguyên an toàn.”** Việc ép kiểu không tự kiểm chứng phần tử do type erasure; có thể nhận cảnh báo unchecked và để lại lỗi runtime muộn. Ưu tiên thiết kế API đủ ràng buộc kiểu hoặc kiểm tra dữ liệu khi buộc phải xử lý nguồn không tin cậy.

**Lỗi 7 — “`? extends T` là cú pháp tạo đối tượng.”** Không. Wildcard là cú pháp đối số kiểu tại nơi sử dụng; không thể viết `new ArrayList<? extends Number>()`. Có thể tạo `new ArrayList<Integer>()` và gán tham chiếu cho biến `List<? extends Number>`.

## 13. Bài tập tự kiểm tra

Cho mã:

```java
List<Integer> ints = new ArrayList<>(List.of(2, 4, 6));
List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
List<? extends Number> source = ints;
```

Hãy dự đoán:

1. `source.get(0)` gán được cho `Number` hay `Integer` mà không cần ép kiểu?
2. `source.add(7)` có biên dịch không? `source.add(null)` có biên dịch không?
3. `source.clear()` có biên dịch không và nó ảnh hưởng `ints` thế nào?
4. `List<Number> numbers = ints;` có biên dịch không?
5. `source = doubles;` có biên dịch không? Sau phép gán, `source.get(0)` an toàn ở kiểu tĩnh nào?
6. `List<? extends Number> data = new ArrayList<Object>();` có hợp lệ không?

**Đáp án và lý do:**

1. Gán cho `Number` (hoặc `Object`) an toàn; compiler không biết kiểu ẩn chính xác là `Integer`.
2. `add(7)` không biên dịch vì kiểu ẩn có thể không phải `Integer`. `add(null)` biên dịch vì null tương thích mọi kiểu tham chiếu; mức runtime phụ thuộc implementation.
3. `clear()` biên dịch. Ở đây `source` và `ints` cùng trỏ đến `ArrayList` mutable, nên `ints` sẽ trống sau khi xóa.
4. Không. `List<Integer>` không phải `List<Number>`.
5. Có. `List<Double>` cũng thỏa `? extends Number`; sau phép gán vẫn chỉ bảo đảm đọc dưới kiểu `Number`.
6. Không. `Object` là kiểu cha, không phải `Number` hay kiểu con của `Number`.

## 14. Nguyên tắc áp dụng

Chọn **`? extends T`** khi API cần **lấy giá trị từ một nguồn có phần tử thuộc `T` hoặc kiểu con của `T`**, và không cần tự ý thêm một giá trị `T` mới vào chính nguồn ấy. Upper bound cho phép đọc kết quả như `T` mà vẫn nhận nhiều loại `List<S>` an toàn ở compile time. Dù vậy, dấu `?` vẫn biểu thị kiểu ẩn: quyền ghi bị giới hạn để bảo vệ danh sách gốc, và khả năng sửa đổi thực tế do đối tượng `List` quyết định.

Nếu code cần ghi `T` vào danh sách, cân nhắc `? super T`; nếu cần giữ quan hệ kiểu chính xác giữa đầu vào và đầu ra hoặc giữa nhiều tham số, cân nhắc một type parameter có tên như `<T>`.