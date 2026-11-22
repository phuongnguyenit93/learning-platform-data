# Giới hạn thêm `null` không có nghĩa collection phải chấp nhận `null`

Trong Java Generics, với một biến kiểu `Collection<? extends T>` (ví dụ `List<? extends Number>`), trình biên dịch không cho phép thêm một đối tượng `T` cụ thể tùy ý vì kiểu phần tử thực tế chưa được biết. Tuy nhiên, **`add(null)` vẫn hợp lệ về mặt kiểu**. Điều đó chỉ nói rằng biểu thức `null` có thể được truyền cho tham số mang kiểu tham chiếu chưa biết; **không bảo đảm** collection được trỏ tới có cho thêm phần tử, hoặc có chấp nhận `null` khi chạy.

Đây là hai tầng quy tắc cần phân biệt:

1. **Kiểm tra tại thời điểm biên dịch (compile time):** hệ kiểu generic xác định lời gọi `add(...)` có hợp lệ với `? extends T` hay không.
2. **Hợp đồng và triển khai collection tại thời điểm chạy (runtime):** collection quyết định thao tác thêm có được hỗ trợ và giá trị `null` có được chấp nhận hay không.

Hiểu đúng hai tầng này giúp tránh nhầm lẫn giữa *generic type safety*, *mutability* và *null policy*.

## 1. Vì sao `add(null)` biên dịch được với `? extends T`?

Xét đoạn mã minh họa trong một phương thức:

```java
static void inspect(List<? extends Number> numbers) {
    Number first = numbers.isEmpty() ? null : numbers.get(0); // Hợp lệ.

    // numbers.add(10);   // LỖI BIÊN DỊCH.
    // numbers.add(2.5);  // LỖI BIÊN DỊCH.
    numbers.add(null);    // HỢP LỆ VỀ KIỂU; runtime còn phụ thuộc list.
}
```

`List<? extends Number>` biểu diễn một danh sách mà kiểu phần tử chính xác chưa được biết, nhưng là `Number` hoặc một kiểu con của `Number`. Danh sách ấy có thể là:

- `List<Integer>`;
- `List<Double>`;
- `List<Number>`;
- hoặc một danh sách của kiểu số khác.

Nếu cho `numbers.add(10)`, đối tượng `Integer` có thể bị thêm vào một `List<Double>` thật sự. Vì vậy compiler từ chối. Tương tự, `2.5` là `Double` nên không an toàn cho mọi kiểu phần tử có thể nằm sau dấu `?`.

Ngược lại, **`null` là giá trị đặc biệt có thể chuyển đổi sang mọi kiểu tham chiếu trong hệ kiểu Java thông thường**, kể cả kiểu tham chiếu chưa biết được trình biên dịch tạo ra khi *capture* wildcard. Nó không có kiểu runtime cụ thể như `Integer` hay `Double` có thể làm sai loại phần tử của danh sách.

Có thể hình dung các điều kiện:

```text
List<? extends Number>
          |
          v
Kiểu phần tử thực tế: một kiểu X chưa biết, X extends Number
          |
          +-- add(Integer): Không chắc Integer là X  -> compiler từ chối
          +-- add(Double):  Không chắc Double là X   -> compiler từ chối
          +-- add(null):    null tương thích với X    -> compiler chấp nhận
```

Tính hợp lệ về kiểu của lời gọi `add(null)` **không tự tạo quyền sửa đổi cấu trúc dữ liệu** và cũng **không ghi đè quy tắc cấm `null`** của một triển khai collection.

## 2. Ví dụ đầy đủ: ba kết quả runtime khác nhau

Lưu tệp `ExtendsNullDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Queue;

public class ExtendsNullDemo {
    static void attemptAddNull(String label, Collection<? extends Number> target) {
        try {
            boolean added = target.add(null); // Biên dịch được.
            System.out.println(label + ": added=" + added);
        } catch (UnsupportedOperationException e) {
            System.out.println(label + ": UnsupportedOperationException");
        } catch (NullPointerException e) {
            System.out.println(label + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        ArrayList<Integer> mutable = new ArrayList<>(List.of(1, 2));
        attemptAddNull("ArrayList", mutable);
        System.out.println("contents=" + mutable);

        List<Integer> immutable = List.of(1, 2);
        attemptAddNull("List.of", immutable);

        Queue<Integer> queue = new ArrayDeque<>();
        attemptAddNull("ArrayDeque", queue);
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac ExtendsNullDemo.java
java ExtendsNullDemo
```

Kết quả:

```text
ArrayList: added=true
contents=[1, 2, null]
List.of: UnsupportedOperationException
ArrayDeque: NullPointerException
```

**Phân tích từng trường hợp:**

- **`ArrayList<Integer>`:** là danh sách hỗ trợ thêm phần tử và cho phép lưu `null`. Lời gọi `add(null)` thành công, trả về `true`.
- **`List.of(1, 2)`:** trả về danh sách không sửa đổi. Lời gọi `add(null)` bị từ chối bằng `UnsupportedOperationException`. Bản thân các factory `List.of(...)` cũng không chấp nhận phần tử `null` khi tạo danh sách.
- **`ArrayDeque<Integer>`:** hỗ trợ thêm phần tử không-null, nhưng chủ động cấm `null`. Lời gọi `add(null)` ném `NullPointerException` ngay cả khi queue đang trống và có thể nhận thêm số nguyên.

Điểm chung: cả ba lần gọi đều dùng chữ ký tham số `Collection<? extends Number>` và **đều qua được trình biên dịch**. Kết quả khác nhau vì đối tượng thực tế có hợp đồng runtime khác nhau.

## 3. Hai câu hỏi độc lập: có sửa được không, và có nhận `null` không?

Một collection có thể hỗ trợ thay đổi nhưng cấm `null`; hoặc có thể chứa `null` nhưng không cho thêm phần tử qua một thao tác cụ thể. Vì vậy cần xét ít nhất hai thuộc tính độc lập:

| Collection và cách tạo | Hỗ trợ `add`? | Chấp nhận `null`? | `add(null)` thường cho kết quả |
| --- | --- | --- | --- |
| `new ArrayList<Integer>()` | Có | Có | Thêm `null` thành công |
| `new HashSet<Integer>()` | Có | Có | Thành công lần đầu; nếu đã có `null` thì `add` trả `false` |
| `new ArrayDeque<Integer>()` | Có | Không | `NullPointerException` |
| `new TreeSet<Integer>()` dùng thứ tự tự nhiên | Có | Không | `NullPointerException` |
| `List.of(1, 2)` | Không | Không | `UnsupportedOperationException` |
| `List.copyOf(source)` | Không | Không | `UnsupportedOperationException` |
| `Arrays.asList(1, 2)` | Không hỗ trợ thay đổi kích thước | Có thể chứa `null` | `UnsupportedOperationException` |
| `Collections.unmodifiableList(list)` | Không qua wrapper | Phụ thuộc nội dung danh sách gốc; wrapper không thêm được | `UnsupportedOperationException` |

Bảng giả định lời gọi là `add(null)` trên các triển khai/thể hiện thông thường như nêu trong cột đầu. Với các collection tự viết hoặc cấu hình comparator riêng, hợp đồng có thể khác. Đặc biệt, `TreeSet` với comparator tùy chỉnh cần tuân theo quy tắc của comparator và triển khai, nên không suy rộng hàng “thứ tự tự nhiên” sang mọi `TreeSet`.

**Cần phân biệt ba dạng trạng thái:**

- **Thêm phần tử được:** `add` là thao tác tùy chọn của `Collection`; vài implementation cố tình không hỗ trợ.
- **Chấp nhận `null`:** collection có thể lưu `null` hợp lệ theo hợp đồng của nó.
- **Chứa sẵn `null`:** ngay cả một góc nhìn không cho thêm phần tử vẫn có thể nhìn thấy `null` tồn tại trong backing collection.

Không thể kết luận ba trạng thái này chỉ từ kiểu generic `Collection<? extends T>`.

## 4. Quy tắc `extends` bảo vệ kiểu phần tử, không xác định chính sách `null`

Giả sử:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> values = integers;

values.add(null);       // Biên dịch; ArrayList nhận null.
Number number = values.get(0); // Hợp lệ; number == null.
```

Các phát biểu sau đều đúng đồng thời:

1. Biến `values` không cho phép thêm một giá trị `Integer` cụ thể bằng `values.add(1)`, bởi compiler không biết kiểu phần tử thật sự sau wildcard.
2. Biểu thức `values.add(null)` hợp lệ về kiểu vì `null` có thể dùng ở vị trí đối số mang kiểu tham chiếu chưa biết.
3. Runtime `ArrayList` cho phép thêm `null`; việc đọc ra sau đó có thể trả về `null`.
4. Hệ kiểu Java thông thường không coi tham số `T extends Number` là cam kết các giá trị luôn non-null.

Ngay cả cận kiểu `Number` hay một interface tự định nghĩa cũng **không phải cận non-null**. Trong Java 17 tiêu chuẩn, `T extends Number` nói về quan hệ kiểu danh nghĩa của các đối tượng không-null; nó không cấm giá trị `null`.

Những hệ thống kiểm tra nullness bổ sung có thể áp dụng annotation hoặc luật riêng để cảnh báo hoặc chặn `null`, nhưng đây là cơ chế ngoài những bảo đảm của cú pháp wildcard thông thường.

## 5. Không riêng `add`: truyền `null` vào `set` cũng qua kiểm tra kiểu

Với `List<? extends Number>`, `set(index, element)` yêu cầu phần tử có kiểu chưa biết tương tự `add`. Vì thế:

```java
List<Integer> base = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = base;

// view.set(0, 99); // LỖI BIÊN DỊCH.
view.set(0, null);  // HỢP LỆ VỀ KIỂU; ArrayList chấp nhận null.
System.out.println(base); // [null, 20]
```

Sự hợp lệ về kiểu vẫn không nói rằng danh sách có hỗ trợ `set` hoặc có nhận `null`. Một danh sách không sửa đổi có thể từ chối cả `add` lẫn `set`. Một danh sách có kích thước cố định có thể **cho `set` nhưng cấm `add`**.

Ví dụ Java 17 độc lập, lưu thành `FixedSizeNullDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class FixedSizeNullDemo {
    public static void main(String[] args) {
        List<Integer> fixedSize = Arrays.asList(1, 2);
        List<? extends Number> view = fixedSize;

        view.set(0, null);
        System.out.println("after set=" + fixedSize);

        try {
            view.add(null);
        } catch (UnsupportedOperationException e) {
            System.out.println("add=UnsupportedOperationException");
        }
    }
}
```

```bash
javac FixedSizeNullDemo.java
java FixedSizeNullDemo
```

Kết quả:

```text
after set=[null, 2]
add=UnsupportedOperationException
```

`Arrays.asList` trả về danh sách được hỗ trợ bởi một mảng có độ dài cố định. Nó cho thay đổi giá trị phần tử hiện có qua `set` và có thể chứa `null`, nhưng không cho tăng kích thước bằng `add`. Ví dụ cho thấy “collection nhận `null`” và “thao tác `add` được hỗ trợ” thực sự là hai điều khác nhau.

## 6. Phân biệt hai loại exception khi thêm `null`

Hai exception rất thường gặp:

### `UnsupportedOperationException`

Đây là dấu hiệu collection **không hỗ trợ thao tác được yêu cầu**. Ví dụ `List.of(...)` trả về danh sách không sửa đổi. Một lời gọi như:

```java
List<? extends Number> readOnly = List.of(1, 2);
readOnly.add(null); // Biên dịch, runtime ném UnsupportedOperationException.
```

không trở nên hợp lệ về mặt thay đổi trạng thái chỉ vì đối số là `null`. Bản thân phép thêm đã là thao tác bị cấm.

### `NullPointerException`

Đây có thể là dấu hiệu implementation **cấm giá trị `null`**. Ví dụ:

```java
Queue<? extends Number> numbers = new ArrayDeque<Integer>();
numbers.add(null); // Biên dịch, runtime ném NullPointerException.
```

`ArrayDeque` có thể thêm phần tử `Integer` bình thường thông qua một tham chiếu thích hợp như `Queue<Integer>`, nhưng vẫn từ chối `null`. Do đó `NullPointerException` ở đây phản ánh chính sách dữ liệu chứ không phải lỗi bất biến generics.

Không thể chỉ nhìn `catch (NullPointerException)` mà kết luận chắc chắn nguyên nhân trong mọi chương trình; stack trace, hợp đồng API và vị trí ném exception mới xác định nguyên nhân. Trong ví dụ trên, nguyên nhân được biết rõ từ hợp đồng của `ArrayDeque`.

## 7. `List.of` và `List.copyOf` kiểm tra `null` ngay khi tạo

Một lỗi thường gặp khác là nghĩ chỉ cần gán kết quả sang `List<? extends Number>` thì quy tắc tiếp nhận `null` sẽ thay đổi. Wildcard chỉ là đặc tính kiểu của tham chiếu; nó không sửa hành vi factory.

Lưu thành `NullFactoryDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class NullFactoryDemo {
    public static void main(String[] args) {
        try {
            List<Integer> first = List.of(1, null);
            System.out.println(first);
        } catch (NullPointerException e) {
            System.out.println("List.of rejected null");
        }

        try {
            List<Integer> second = List.copyOf(Arrays.asList(1, null));
            System.out.println(second);
        } catch (NullPointerException e) {
            System.out.println("List.copyOf rejected null");
        }

        List<? extends Number> safe = List.of(1, 2);
        System.out.println("size=" + safe.size());
    }
}
```

```bash
javac NullFactoryDemo.java
java NullFactoryDemo
```

Kết quả:

```text
List.of rejected null
List.copyOf rejected null
size=2
```

- `List.of(1, null)` không tạo thành công danh sách vì factory từ chối `null`.
- `List.copyOf(...)` cũng kiểm tra danh sách nguồn và từ chối nếu có phần tử `null`; nó không âm thầm bỏ `null`.
- Một danh sách hợp lệ do `List.of` trả về có thể được gán cho `List<? extends Number>` để đọc số, nhưng `add(null)` qua tham chiếu ấy vẫn không làm nó trở thành mutable.

Hành vi từ chối `null` của factory và hành vi từ chối thay đổi của danh sách kết quả là hai điều riêng biệt, dù có thể cùng xuất hiện.

## 8. `null` có thể đọc ra dưới kiểu `Number` dù cận wildcard là `Number`

Một ngộ nhận hay gặp: “`? extends Number` bảo đảm mỗi lần `get` trả về một đối tượng `Number` hợp lệ, nên có thể gọi `doubleValue()` ngay.” Thực tế, compiler chỉ bảo đảm kiểu kết quả **tương thích với `Number`**, chứ không bảo đảm giá trị khác `null`.

Ví dụ:

```java
List<Integer> integers = new ArrayList<>();
integers.add(null);

List<? extends Number> source = integers;
Number first = source.get(0); // first == null.

// double x = first.doubleValue(); // Ném NullPointerException nếu chạy.
```

Nếu dữ liệu có thể có `null`, cần xử lý rõ ràng trong thuật toán. Ví dụ phương thức cộng, bỏ qua phần tử `null`:

Lưu thành `NullableNumberSum.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class NullableNumberSum {
    static double sumPresent(List<? extends Number> source) {
        double sum = 0.0;

        for (Number number : source) {
            if (number != null) {
                sum += number.doubleValue();
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
        source.add(null);

        System.out.println(sumPresent(source));
    }
}
```

```bash
javac NullableNumberSum.java
java NullableNumberSum
```

Kết quả:

```text
6.0
```

Đây là **chính sách nghiệp vụ** “bỏ qua phần tử `null`”, không phải mặc định bắt buộc. Trong ứng dụng khác, việc gặp `null` có thể là lỗi dữ liệu và cần ném exception sớm, hoặc cần được biểu diễn bằng một mô hình dữ liệu rõ ràng hơn. Điều quan trọng là không suy từ cận `extends Number` ra cam kết non-null.

## 9. `add(null)` với `?` và `? super T` cũng có hai tầng kiểm tra

Cơ chế `null` không độc quyền của `? extends`. Với tham số generic là kiểu tham chiếu, một biến có `?` hoặc `? super T` cũng có thể cho phép truyền `null` ở những API nhận phần tử:

```java
static void examples(
        List<?> unknown,
        List<? extends Number> numbers,
        List<? super Integer> destination) {

    unknown.add(null);     // Hợp lệ về kiểu.
    numbers.add(null);     // Hợp lệ về kiểu.
    destination.add(null); // Hợp lệ về kiểu.
    destination.add(10);   // Cũng hợp lệ: Integer phù hợp cận dưới.

    // unknown.add(10); // Không biên dịch.
    // numbers.add(10); // Không biên dịch.
}
```

Đoạn này là minh họa chữ ký và kiểm tra kiểu, **không phải** chương trình chạy độc lập. Mọi lời gọi `add` thành công hay ném exception vẫn tùy thuộc danh sách thực tế được truyền vào.

Đối chiếu ý nghĩa:

| Biến | Giá trị không-null có thể thêm bằng `add` | Có thể gọi `add(null)` về mặt kiểu? |
| --- | --- | --- |
| `List<?>` | Không thể chọn tùy ý một giá trị cụ thể | Có |
| `List<? extends Number>` | Không thể chọn tùy ý một `Number` cụ thể | Có |
| `List<? super Integer>` | `Integer` (và kiểu con, nếu có) | Có |
| `List<Integer>` | `Integer` | Có |

Cột cuối **chỉ nói về trình biên dịch**, không phải bảo đảm runtime. Không nên biến bảng này thành “danh sách được phép chứa `null`”; mỗi implementation có quy tắc riêng.

## 10. Khác biệt giữa `add(null)` và ép một giá trị có kiểu sang `null`

Compiler quan tâm **kiểu tĩnh của biểu thức** truyền vào, không chỉ giá trị runtime. Khi một biến có kiểu cụ thể đang chứa `null`, nó vẫn mang kiểu khai báo của biến đó:

```java
static void addExamples(List<? extends Number> target) {
    Integer boxed = null;

    target.add(null);   // Hợp lệ: null literal.
    // target.add(boxed); // Không biên dịch: boxed có kiểu Integer.
    // target.add((Integer) null); // Không biên dịch: biểu thức có kiểu Integer.
    // target.add((Number) null);  // Không biên dịch: biểu thức có kiểu Number.
}
```

Đây là điểm đặc biệt dễ bỏ sót: một đối số có giá trị runtime là `null` **không** tự động được đối xử như *null literal* trong phân tích kiểu. `boxed` vẫn có kiểu `Integer`, và `Integer` không được chứng minh tương thích với kiểu capture cụ thể chưa biết của `? extends Number`.

Tương tự, trong lời gọi như `target.add(getNumberOrNull())`, kiểu trả về khai báo của phương thức có thể là `Number`. Nếu thế compiler vẫn từ chối lời gọi dù tại runtime phương thức có thể trả `null`. Không nên lách kiểm tra bằng raw type hay ép kiểu unchecked; hãy thiết kế lại API cho đúng mục đích.

## 11. Vì sao `add(null)` không phải cách khắc phục giới hạn của producer?

Quy tắc thực hành PECS (*Producer Extends, Consumer Super*) nhắc rằng `? extends T` phù hợp với nguồn **cung cấp** giá trị kiểu `T` cho chương trình. Nó không tuyên bố rằng `? extends T` tuyệt đối không thể có bất kỳ lời gọi thay đổi nào; nó nói rằng **không thể ghi một đối tượng `T` cụ thể tùy ý qua wildcard ấy một cách an toàn**.

Ví dụ:

```java
static double total(List<? extends Number> source) {
    double sum = 0.0;
    for (Number number : source) {
        if (number != null) {
            sum += number.doubleValue();
        }
    }
    return sum;
}
```

Một phương thức chuyên đọc như `total` hoàn toàn **không cần gọi `add(null)`**. Quyền biên dịch được phép thêm `null` chỉ là hệ quả của quy tắc chuyển đổi kiểu, không phải mục đích thiết kế của wildcard `extends`.

Nếu API cần thực sự thêm các giá trị `Integer` vào collection, dùng tham số có khả năng nhận chúng:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Ngay cả `List<? super Integer>` cũng không bảo đảm runtime hỗ trợ sửa đổi. Nếu caller truyền một `List<Number>` không sửa đổi, compiler vẫn chấp nhận kiểu tham số nhưng `add(10)` có thể ném `UnsupportedOperationException`. Lựa chọn wildcard đúng mới giải quyết **an toàn kiểu**; muốn thêm được thật sự còn cần hợp đồng về collection có thể thay đổi.

## 12. Sai lầm thường gặp

### Sai lầm 1: “Compiler cho `add(null)` nên API bảo đảm chấp nhận `null`”

Sai vì kiểm tra kiểu và chính sách dữ liệu là hai tầng. `ArrayDeque` là ví dụ có thể thêm phần tử bình thường nhưng cấm `null`; `List.of` cấm mọi thay đổi cấu trúc.

**Cách làm đúng:** đọc hợp đồng collection cụ thể; không suy luận null policy từ `? extends`.

### Sai lầm 2: “`? extends Number` luôn trả về giá trị không-null”

Sai. `Number n = list.get(0)` hoàn toàn có thể cho `n == null` nếu nguồn chứa `null`. Gọi `n.doubleValue()` cần có bảo đảm không-null từ dữ liệu hoặc kiểm tra trước.

**Cách làm đúng:** xác định chính sách đầu vào và kiểm tra `null` khi cần, độc lập với wildcard.

### Sai lầm 3: “Không hỗ trợ `add` tức là không thể có `null` trong collection”

Sai. `Arrays.asList(1, null)` chứa `null` nhưng có kích thước cố định và không hỗ trợ `add`. `Collections.unmodifiableList(backingList)` cũng có thể hiển thị phần tử `null` của danh sách nền mà không cho thêm phần tử qua wrapper.

**Cách làm đúng:** phân biệt thao tác được hỗ trợ với trạng thái dữ liệu được phép.

### Sai lầm 4: “Chỉ cần ép một `Integer` thành `Number` rồi thêm qua `extends`”

Sai. `target.add((Number) 10)` vẫn không biên dịch với `List<? extends Number>`: compiler không thể khẳng định đối số kiểu thực tế là `Number` thay vì một lớp con khác.

**Cách làm đúng:** sử dụng `List<? super Integer>` nếu cần ghi `Integer`, hoặc một kiểu chính xác `List<Integer>` khi caller và callee đã thống nhất.

### Sai lầm 5: “`(Integer) null` và literal `null` hoàn toàn giống nhau với compiler”

Sai trong ngữ cảnh wildcard capture. Literal `null` chuyển được sang mọi kiểu tham chiếu, còn `(Integer) null` là biểu thức có kiểu tĩnh `Integer`. Vì thế, `target.add((Integer) null)` vẫn không hợp lệ với `List<? extends Number>`.

**Cách làm đúng:** chú ý kiểu tĩnh của biểu thức; đừng dùng cast/raw type để né quy tắc an toàn generic.

### Sai lầm 6: “`List.copyOf` sẽ tự bỏ các phần tử `null`”

Sai. `List.copyOf` từ chối đầu vào có phần tử `null` bằng `NullPointerException`; nếu cần lọc, phải lọc rõ ràng và quyết định xử lý dữ liệu tại lớp nghiệp vụ.

## 13. Thiết kế API để không dựa vào sự cho phép tình cờ của `add(null)`

Nếu một phương thức chỉ dùng collection làm nguồn dữ liệu, nên viết hợp đồng theo hướng đọc:

```java
static double average(List<? extends Number> values) {
    double sum = 0.0;
    int count = 0;

    for (Number number : values) {
        if (number != null) {
            sum += number.doubleValue();
            count++;
        }
    }
    return count == 0 ? 0.0 : sum / count;
}
```

Nếu yêu cầu nghiệp vụ **cấm `null`**, có thể kiểm tra rõ tại ranh giới API thay vì hy vọng wildcard hoặc cận kiểu làm việc ấy:

```java
import java.util.List;
import java.util.Objects;

static void requireNoNullElements(List<? extends Number> source) {
    for (Number value : source) {
        Objects.requireNonNull(value, "source must not contain null");
    }
}
```

Hai ví dụ trên là phương thức minh họa: ví dụ thứ hai có các dòng `import` để dùng trong class Java của ứng dụng. `Objects.requireNonNull` sẽ ném `NullPointerException` với thông điệp chỉ định nếu gặp phần tử `null`; phương thức này không sửa collection và không thay đổi cách generic hoạt động.

Nếu cần xây dựng danh sách mới chỉ chứa giá trị không-null, có thể tạo danh sách đích cụ thể và thêm từng giá trị được kiểm tra. Khi đó sự chấp nhận `null` và tính khả biến nằm trong thiết kế của **đối tượng đích**, chứ không ngầm suy ra từ kiểu `List<? extends Number>` của nguồn.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Với `List<? extends Number> xs`, lời gọi nào qua được trình biên dịch?

```java
xs.add(null);        // A
// xs.add(1);         // B
// xs.add((Integer) null); // C
```

**Đáp án:** A. Biểu thức literal `null` tương thích với kiểu tham chiếu capture; `Integer` không được chứng minh tương thích với mọi kiểu phần tử có thể nằm sau wildcard.

**Câu 2.** Vì sao `List.of(1, 2)` không cho `add(null)` dù compiler chấp nhận lời gọi trên `List<? extends Number>`?

**Đáp án:** `List.of` tạo danh sách không sửa đổi; `add` ném `UnsupportedOperationException` theo hợp đồng collection.

**Câu 3.** Với `ArrayDeque<Integer>`, việc `add(null)` thất bại có phải vì `Integer` không phải kiểu con của `Number` không?

**Đáp án:** Không. Nguyên nhân là `ArrayDeque` cấm `null`; lời gọi đã vượt qua kiểm tra kiểu.

**Câu 4.** Một `List<? extends Number>` chứa `null` có thể trả `null` từ `get(0)` không?

**Đáp án:** Có. Cận `Number` không chứng minh giá trị khác `null`.

**Câu 5.** `Arrays.asList(1, 2)` có thể thực hiện `set(0, null)` nhưng không thực hiện `add(null)`. Vì sao?

**Đáp án:** Danh sách kích thước cố định có thể thay giá trị phần tử đã có bằng `null`, nhưng không hỗ trợ thao tác tăng kích thước.

## 15. Ghi nhớ

- Với `List<? extends T>` và `T` là kiểu tham chiếu, `add(null)` **biên dịch được**; `add(nonNullT)` thường bị từ chối vì kiểu phần tử thực tế chưa biết.
- **Quyền gọi phương thức theo kiểu tĩnh khác với thành công của thao tác tại runtime.** `UnsupportedOperationException` phản ánh khả năng sửa đổi; `NullPointerException` có thể phản ánh chính sách cấm `null`.
- `ArrayList`, `HashSet` có thể chứa `null`; `ArrayDeque` không nhận `null`; `List.of` vừa cấm `null` khi tạo vừa không cho thêm sau khi tạo.
- `set(index, null)` cũng có thể biên dịch qua `List<? extends T>`, nhưng thành công hay không vẫn tùy collection và chỉ số hợp lệ.
- Cận `extends Number` **không phải** cam kết “không có phần tử `null`”. Thuật toán đọc vẫn phải xử lý `null` theo hợp đồng dữ liệu.
- Thiết kế API nên chọn wildcard theo chiều đọc/ghi, đồng thời quy định riêng tính khả biến và chính sách `null` của dữ liệu.

**Kết luận cốt lõi:** `add(null)` được chấp nhận ở bước *kiểm tra kiểu generic* chỉ vì `null` tương thích với kiểu tham chiếu chưa biết. Collection cụ thể có thể chấp nhận, từ chối `null` hoặc từ chối toàn bộ thao tác thêm; phải dựa trên hợp đồng thực tế của collection để biết điều gì sẽ xảy ra.