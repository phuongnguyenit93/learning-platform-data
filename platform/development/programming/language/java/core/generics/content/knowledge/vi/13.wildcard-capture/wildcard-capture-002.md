# Đọc thông báo CAP#1 và "capture of ?" trong Java Generics

## 1. Tại sao javac nhắc đến CAP#1?

Trong Java Generics, một biến có kiểu `List<?>` nói rằng danh sách có **một đối số kiểu nào đó**, nhưng mã đang sử dụng biến không biết đó là `String`, `Integer` hay một kiểu khác. Khi kiểm tra lời gọi generic, trình biên dịch Java (`javac`) có thể tạo một **kiểu nội bộ tạm thời** để biểu diễn đối số kiểu chưa biết. Quá trình đó gọi là **wildcard capture** hoặc **capture conversion**.

Khi báo lỗi, `javac` đôi khi hiển thị một tên do compiler tạo như:

- `CAP#1`: ký hiệu tạm do compiler đặt cho một kiểu đã được capture.
- `capture of ?`: cho biết kiểu ẩn đó đến từ wildcard không giới hạn `?`.
- `capture of ? extends Number`: cho biết kiểu ẩn đến từ wildcard có cận trên `Number`.
- `capture of ? super Integer`: cho biết kiểu ẩn đến từ wildcard có cận dưới `Integer`.

**`CAP#1` không phải là lớp Java, một biến, tên type parameter có thể tự khai báo hay thứ tồn tại độc lập ở runtime.** Đó là cách thông báo chẩn đoán giúp người đọc phân biệt các kiểu ẩn trong phép kiểm tra kiểu tại thời điểm biên dịch. Con số `#1`, `#2`,... chỉ là nhãn nội bộ; không được suy ra thứ tự thực thi hoặc một định danh ổn định giữa các bản JDK.

Ví dụ:

```java
List<String> names = new ArrayList<>();
List<?> unknown = names;
```

Compiler biết `unknown` **đang có kiểu tĩnh `List<?>`**. Khi xử lý một lời gọi nhận phần tử thuộc `E` như `add(E)`, nó có thể xem `E` là một kiểu ẩn `CAP#1` nào đó. Tuy nhiên, không có căn cứ để khẳng định `String` bất kỳ gán được cho kiểu ẩn ấy.

```java
unknown.add("An"); // Lỗi biên dịch: không chứng minh được String là CAP#1
```

Việc nhìn thấy `CAP#1` có nghĩa rất thực tế: **bạn đang cần đưa giá trị hoặc liên hệ hai giá trị với một kiểu mà compiler hiện chưa biết chính xác**.

## 2. Phân biệt kiểu thật, kiểu tĩnh và kiểu capture

Giả sử:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
List<?> view = names;
```

Có ba mức cần tách riêng:

1. **Đối tượng/danh sách thực tế**: `names` và `view` cùng trỏ tới một `ArrayList` đang lưu các chuỗi; `names` được khai báo `List<String>`.
2. **Kiểu tĩnh của biểu thức `view`**: `List<?>`. Mã viết qua biến `view` chỉ được dựa vào hợp đồng của dấu hỏi, không tự suy ra `String`.
3. **Kiểu capture nội bộ**: khi kiểm tra lời gọi, `javac` có thể đặt tên tạm như `CAP#1` cho đối số kiểu ẩn. Đây là chi tiết hỗ trợ type checking; tên này không phải một kiểu nguồn mà ta có thể viết trong Java.

Java Generics sử dụng **type erasure**: đối số kiểu như `String` không được giữ lại dưới dạng một thuộc tính runtime của bản thân đối tượng `ArrayList` để kiểm tra tự động toàn bộ phần tử. Wildcard capture không đọc một “generic type thật” từ heap; nó là phép biến đổi kiểu của compiler nhằm kiểm tra ràng buộc an toàn.

Do đó không thể sửa lỗi bằng cách tìm một lớp tên `CAP#1`, khai báo `CAP#1 value`, hoặc cố “xóa” tên đó bằng một phép ép kiểu tùy tiện.

## 3. Đọc cấu trúc thông báo lỗi từ javac

Ví dụ sau **cố ý không biên dịch**. Đặt vào tệp `BrokenCapture.java` để quan sát compiler:

```java
import java.util.List;

public class BrokenCapture {
    static void appendText(List<?> values) {
        values.add("new");
    }
}
```

Chạy:

```bash
javac -Xdiags:verbose BrokenCapture.java
```

Lệnh này thất bại ở bước biên dịch. **Không có stdout của chương trình**, vì chưa tạo được chương trình chạy. Nội dung và cách trình bày stderr có thể khác nhau theo bản JDK, tùy compiler và tùy ngữ cảnh; không nên học thuộc nguyên văn hay số `CAP`.

Thông báo thường chứa các ý tương đương:

```text
no suitable method found for add(String)
required: CAP#1
found:    String
reason:  String cannot be converted to CAP#1
where CAP#1 is a fresh type-variable from capture of ?
```

Đây là **dạng thông tin minh họa**, không cam kết là toàn bộ stderr chính xác của mọi bản `javac`. Thông báo thực tế có thể liệt kê thêm overload `add(int,E)` hoặc diễn đạt lỗi là `incompatible types`.

Hãy đọc theo thứ tự:

1. **Vị trí lỗi**: lời gọi `values.add("new")`, nhất là tham số được truyền.
2. **`found` / `actual`**: compiler biết đối số bạn cung cấp là `String`.
3. **`required` / `formal`**: phương thức generic `List<E>.add(E)` đang cần một giá trị thuộc kiểu phần tử ẩn, có thể được gọi là `CAP#1`.
4. **`capture of ?`**: kiểu cần thiết đến từ dấu `?` trong `List<?>`.
5. **Kết luận**: chưa có bằng chứng `String` là kiểu phần tử của danh sách. Vấn đề nằm ở hợp đồng kiểu, không phải cú pháp chuỗi hay lỗi JVM.

Khi gặp lỗi dài, hãy tìm tên biến có wildcard, lần ngược tới kiểu tham số của phương thức đang gọi, rồi hỏi: “Tôi đang **đọc** giá trị từ kiểu ẩn hay muốn **ghi** một giá trị có kiểu cụ thể vào kiểu ẩn?”

Tùy thông báo, `javac` có thể nêu `CAP#1 extends Object` hoặc dùng cụm “fresh type-variable”. Những phần này mô tả ràng buộc của kiểu ẩn; chúng không phải gợi ý để đổi `CAP#1` thành `Object`.

## 4. Vì sao `List<?>.add` gây lỗi nhưng `get` đọc được?

`List<E>` có hai thao tác đặc trưng:

```java
E get(int index);
boolean add(E element);
```

Đây là **chữ ký rút gọn** minh họa hai phương thức, không phải chương trình chạy độc lập.

Đối với `List<?>`, `get` cung cấp một giá trị thuộc kiểu ẩn; mọi kiểu đối số của generics đều là kiểu tham chiếu, nên có thể sử dụng giá trị ấy dưới kiểu `Object`:

```java
List<String> names = List.of("An");
List<?> values = names;

Object first = values.get(0); // Hợp lệ
// String text = values.get(0); // Không an toàn theo kiểu tĩnh List<?>
```

Nhưng `add` cần một giá trị **đúng kiểu ẩn**. Compiler không biết kiểu đó:

```java
List<?> values = new ArrayList<String>();

// values.add("An"); // Lỗi vì dấu ? không có nghĩa String
// values.add(42);   // Lỗi vì dấu ? không có nghĩa Integer
values.add(null);    // Hợp lệ về kiểu
```

Chỉ có `null` được phép ở mức type checking vì `null` gán được cho mọi kiểu tham chiếu. Tuy nhiên `List.of(...)` và các danh sách unmodifiable vẫn có thể ném `UnsupportedOperationException` khi sửa đổi; một số implementation có quy tắc riêng đối với null.

**Không nên chữa lỗi CAP bằng raw `List`**. Ép về raw type để gọi `add` bỏ qua kiểm tra tham số generic và có thể tạo *heap pollution*, khiến phần mã đọc danh sách theo kiểu đã khai báo gặp `ClassCastException` muộn hơn.

## 5. `CAP#1 extends Number`: đọc được `Number` nhưng không ghi được `Number`

Với wildcard có cận trên:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number first = source.get(0); // Hợp lệ
// source.add(3);              // Không biên dịch
// source.add(3.5);            // Không biên dịch
// source.add((Number) 3);     // Cũng không biên dịch
```

Compiler có thể mô tả kiểu phần tử là một `CAP#1` với **cận trên `Number`**. Điều nó biết là “`CAP#1` là `Number` hoặc một kiểu con của `Number`”. Vì thế:

- **Đọc** một `CAP#1` rồi gán lên `Number` là an toàn.
- **Ghi** một `Number` hay `Integer` mới vào `CAP#1` chưa chắc an toàn: danh sách có thể là `List<Double>`, `List<Integer>` hoặc `List<Number>`.

Đoạn minh họa lỗi:

```java
static void brokenAdd(List<? extends Number> numbers) {
    // numbers.add(Integer.valueOf(10)); // Không thể gán Integer vào CAP#1 extends Number
}
```

Khi thông báo có `capture of ? extends Number`, hãy đọc nó như **“kiểu ẩn nằm dưới Number”**, không phải **“kiểu ẩn chính là Number”**. Đây là lý do cận trên giúp producer cung cấp giá trị để đọc, nhưng không cấp quyền thêm giá trị mới tùy ý.

## 6. `CAP#1 super Integer`: ghi được `Integer` nhưng khi đọc chỉ chắc chắn là `Object`

Với wildcard có cận dưới:

```java
List<Number> numbers = new ArrayList<>(List.of(1, 2));
List<? super Integer> destination = numbers;

destination.add(3); // Hợp lệ: mọi kiểu phù hợp đều nhận được Integer
Object first = destination.get(0); // Hợp lệ

// Integer exact = destination.get(0); // Không biên dịch
// Number number = destination.get(0);  // Không biên dịch
```

Một `List<? super Integer>` có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`. Một danh sách `List<Object>` có thể chứa các đối tượng khác `Integer` từ trước, nên `get` chỉ bảo đảm kiểu `Object`.

Compiler có thể gắn nhãn `CAP#1` cho đối số kiểu với thông tin về **cận dưới `Integer`** và cận trên tổng quát `Object`. Lỗi khi cố gán kết quả `get` cho `Integer` không có nghĩa `CAP#1` là kiểu con của `Integer`; wildcard `super` giới hạn chiều ngược lại.

Hai cách đọc cần ghi nhớ:

| Wildcard | Compiler biết gì về kiểu ẩn? | Giá trị lấy ra bảo đảm | Giá trị đưa vào được bảo đảm |
|---|---|---|---|
| `?` | Chưa biết kiểu tham số | `Object` | Chỉ `null` về mặt kiểu |
| `? extends Number` | Kiểu ẩn là `Number` hoặc kiểu con | `Number` | Chỉ `null` về mặt kiểu |
| `? super Integer` | Kiểu ẩn là `Integer` hoặc kiểu cha | `Object` | `Integer`, các kiểu con của nó và `null` |
| `Integer` | Kiểu phần tử chính xác là `Integer` | `Integer` | `Integer` và `null` |

Các cột “đưa vào” nói về khả năng compiler cho phép, không bảo đảm danh sách thực tế hỗ trợ mutation hoặc chấp nhận null. Với generic, nguyên tắc PECS vẫn hữu ích: **Producer Extends, Consumer Super**.

## 7. Một lỗi capture tinh tế: lấy ra rồi đặt lại chính phần tử đó

Có trường hợp không hề muốn thêm phần tử lạ: chỉ muốn đưa một phần tử hiện có về đúng danh sách. Dù vậy, đoạn mã sau thường gây lỗi capture trong `javac`:

```java
static void putFirstBack(List<?> values) {
    // values.set(0, values.get(0)); // Lỗi capture wildcard
}
```

Về ý nghĩa, việc đặt lại phần tử vừa lấy ra là an toàn nếu danh sách mutable. Nhưng ở mức biểu thức generic, compiler không nhất thiết giữ được **bằng chứng hai vị trí dùng wildcard trong lời gọi là cùng một kiểu được capture**. Trong thông báo có thể xuất hiện `CAP#1` và `CAP#2` hoặc `Object` và `CAP#1`. Điều đó không có nghĩa danh sách chứa hai lớp phần tử khác nhau; đó là hai nhãn compiler cần để bảo vệ ràng buộc kiểu trong ngữ cảnh kiểm tra này.

Để diễn tả quan hệ “đọc ra `T` rồi ghi lại đúng `T`” rõ ràng, dùng **wildcard capture helper**:

```java
static void putFirstBack(List<?> values) {
    putFirstBackCaptured(values);
}

private static <T> void putFirstBackCaptured(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.set(0, first);
    }
}
```

Đây là các phương thức minh họa có thể đặt vào một lớp Java. `putFirstBackCaptured` có **một tham số kiểu tên `T` nhất quán**: kết quả `get` là `T`, và `set` chấp nhận `T`. Lời gọi helper cho phép compiler suy luận `T` từ wildcard ẩn của danh sách được truyền vào.

Không cần biết tên kiểu thực tế là `String` hay `Integer`. Không dùng raw type, không ép kiểu `(List<T>)`, không tắt kiểm tra compile time.

Tuy nhiên, helper chỉ đảm bảo **an toàn kiểu**; nếu danh sách không cho sửa, `set` vẫn có thể ném `UnsupportedOperationException`. Nếu danh sách rỗng, đoạn trên không thực hiện `set`.

## 8. Ví dụ Java 17 hoàn chỉnh: giữ cùng kiểu ẩn bằng helper

Tạo tệp `WildcardCaptureDiagnosticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class WildcardCaptureDiagnosticsDemo {
    static void repeatFirst(List<?> values) {
        repeatCaptured(values);
    }

    private static <T> void repeatCaptured(List<T> values) {
        if (!values.isEmpty()) {
            T first = values.get(0);
            values.add(first);
        }
    }

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

    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("red", "blue"));
        List<?> unknown = words;

        Object first = unknown.get(0);
        System.out.println("First: " + first);

        repeatFirst(unknown);
        System.out.println("Repeated: " + words);

        swapFirstTwo(unknown);
        System.out.println("Swapped: " + words);

        Collections.swap(unknown, 0, 1);
        System.out.println("Library swap: " + words);

        List<Integer> numbers = List.of(2, 4);
        List<Number> collected = new ArrayList<>();
        copyAll(numbers, collected);
        System.out.println("Collected: " + collected);
    }
}
```

Biên dịch và chạy:

```bash
javac WildcardCaptureDiagnosticsDemo.java
java WildcardCaptureDiagnosticsDemo
```

**Stdout chính xác:**

```text
First: red
Repeated: [red, blue, red]
Swapped: [blue, red, red]
Library swap: [red, blue, red]
Collected: [2, 4]
```

Giải thích:

1. `unknown` có kiểu tĩnh `List<?>`, nên `get(0)` có thể dùng như `Object`. Đối tượng được tham chiếu là `ArrayList<String>`.
2. `repeatFirst` nhận một `List<?>`, gọi helper `repeatCaptured`. Trong helper, `T first = values.get(0)` và `values.add(first)` cùng dùng `T`. Vì `ArrayList` mutable, kết quả là `[red, blue, red]`.
3. `swapFirstTwo` dùng cùng cơ chế để hoán đổi hai phần tử đầu mà không cần tự tạo giá trị kiểu `T` mới. Kết quả là `[blue, red, red]`.
4. `Collections.swap` là API thư viện chấp nhận `List<?>`; nó cho phép hoán đổi phần tử theo chỉ số khi danh sách hỗ trợ `set`. Kết quả là `[red, blue, red]`.
5. `copyAll` minh họa cách nối kiểu giữa **hai danh sách có vai trò khác nhau**: nguồn `List<? extends T>` cung cấp `T`, đích `List<? super T>` nhận `T`. `List<Integer>` và `List<Number>` tương thích theo quy tắc PECS.

Mọi phương thức trong tệp đều có đầy đủ khai báo/import, không dùng raw type và không có unchecked cast. Nếu thay `words` bằng danh sách trả về từ `List.of(...)`, `repeatFirst` và `swapFirstTwo` có thể ném `UnsupportedOperationException` khi cố sửa.

## 9. Vì sao đôi khi thấy CAP#1 và CAP#2 trong cùng một lỗi?

Các ký hiệu `CAP#1`, `CAP#2`,... là những kiểu ẩn nội bộ do compiler đặt tên khi capture các wildcard trong những ngữ cảnh khác nhau. **Không thể mặc định hai wildcard độc lập có cùng kiểu phần tử** chỉ vì cùng được viết là `?`.

Ví dụ:

```java
static void moveOne(List<?> from, List<?> to) {
    // to.add(from.get(0)); // Không biên dịch
}
```

Bên gọi hoàn toàn có thể cung cấp:

```java
List<String> strings = new ArrayList<>(List.of("red"));
List<Integer> integers = new ArrayList<>(List.of(1));

// moveOne(strings, integers); // Nếu thân hàm ghi phần tử, sẽ hỏng kiểu!
```

`from` có thể là `List<String>`, còn `to` là `List<Integer>`. Một helper chỉ đặt cùng tên `T` cho hai danh sách **không thể biến hai kiểu thật khác nhau thành cùng kiểu**.

Nếu muốn sao chép giữa các danh sách có quan hệ kiểu phù hợp, hãy thiết kế hợp đồng ngay trong chữ ký:

```java
static <T> void moveAll(
        List<? extends T> from,
        List<? super T> to) {
    for (T item : from) {
        to.add(item);
    }
}
```

Với `List<String>` làm nguồn và `List<Object>` làm đích, compiler có thể suy luận một `T` phù hợp; với `List<String>` làm nguồn và `List<Integer>` làm đích, không có quan hệ kiểu phù hợp để truyền giá trị theo hợp đồng trên.

**Bài học khi thấy nhiều CAP:** hãy phân biệt “các lần sử dụng của **một danh sách** cần giữ cùng kiểu” với “**hai danh sách khác nhau** mà kiểu phần tử chưa chắc liên hệ”. Nhóm đầu thường giải được bằng helper capture; nhóm sau cần mô hình quan hệ kiểu thực sự hoặc thay đổi thiết kế.

## 10. Khi nào helper capture giải quyết được lỗi?

Helper generic thích hợp khi bạn **cần biểu diễn một quan hệ về cùng kiểu ẩn** mà compiler chưa thể chứng minh trong cách viết trực tiếp qua wildcard.

Mẫu chung:

```java
static void operation(List<?> values) {
    operationCaptured(values);
}

private static <E> void operationCaptured(List<E> values) {
    // Ở đây các thao tác đọc và ghi cùng kiểu E được kiểm tra thống nhất.
}
```

Đây là **mẫu khai báo phương thức**, không phải chương trình độc lập. Tên `E` do tác giả đặt (có thể dùng `T`, `X`...) và khác hoàn toàn với `CAP#1` do compiler tạo.

Một helper **không** hợp thức hóa việc ghi giá trị sai kiểu:

```java
private static <T> void unsafeAttempt(List<T> values) {
    // values.add("new"); // Vẫn lỗi: T chưa chắc là String
}
```

Helper chỉ cấp tên thống nhất cho kiểu ẩn; nó không chứng minh một `String` bất kỳ có thể gán cho mọi `T`.

Khi bài toán chỉ cần một thao tác thư viện sẵn có như `Collections.swap(List<?>, ...)`, dùng API có sẵn có thể rõ ràng hơn viết helper. Khi bài toán chỉ muốn **đọc** giá trị dưới `Object`, không cần helper vì `List<?>` đã đủ.

Nếu cần **ghi `T` từ bên ngoài vào đích**, hãy cân nhắc `List<? super T>`. Nếu cần **đọc `T` từ nguồn**, hãy cân nhắc `List<? extends T>`. Nếu một đối tượng cần vừa đọc vừa ghi đúng một kiểu phần tử, `List<T>` có thể là hợp đồng phù hợp hơn wildcard.

## 11. Những cách xử lý sai cần tránh

### Sai: dùng raw type để vượt qua CAP

```java
static void unsafe(List<?> values) {
    List raw = values;   // Raw type, mất kiểm tra đối số kiểu
    raw.add("new");      // Có thể xuất hiện cảnh báo unchecked
}
```

Ví dụ cố ý minh họa mã **không an toàn**. Nếu `values` đang là `List<Integer>`, dòng cuối có thể chèn `String` vào một danh sách mà các vị trí khác tin là chỉ chứa `Integer`. Sau đó mã đọc theo kiểu `Integer` có thể gặp `ClassCastException`. Cảnh báo `unchecked` không phải lỗi tương đương với capture error; việc xóa cảnh báo không làm phép ghi trở nên an toàn.

### Sai: ép kiểu `List<String>` khi chưa chứng minh phần tử

```java
static void unsafeCast(List<?> values) {
    // Đừng dùng cast như một phương pháp sửa lỗi CAP khi không biết dữ liệu.
    // List<String> strings = (List<String>) values;
}
```

Ép kiểu generic không tự xác nhận từng phần tử do type erasure. Khi nhận dữ liệu chưa tin cậy, hãy kiểm tra từng phần tử rồi sao chép vào một `List<T>` mới nếu cần đảm bảo nội dung theo `T`.

### Sai: chỉ đổi `CAP#1` thành `Object`

Nếu phương thức đòi phần tử của `List<?>`, thay dữ liệu đầu vào thành `Object` không giúp compiler biết kiểu ẩn:

```java
static void broken(List<?> values, Object candidate) {
    // values.add(candidate); // Vẫn không hợp lệ
}
```

Một `List<String>` không thể nhận một `Object` bất kỳ. `Object` là **kiểu cha chung của các kiểu tham chiếu**, không phải tên khác của tham số kiểu ẩn.

### Sai: nghĩ thông báo CAP nói về runtime

Các lỗi `CAP#1` và `capture of ?` đang xét được phát hiện **khi biên dịch**. Chúng khác với `ClassCastException` xảy ra lúc chạy. `-Xdiags:verbose` giúp đọc thông báo chi tiết hơn, còn `@SuppressWarnings("unchecked")` không giải quyết một **compile error** về đối số kiểu không tương thích.

## 12. Bảng dịch nhanh thông báo compiler sang câu hỏi cần giải

| Cụm thường gặp | Cách đọc | Câu hỏi xử lý |
|---|---|---|
| `CAP#1` | Tên tạm của một kiểu ẩn do capture | Kiểu này đến từ wildcard ở đâu? |
| `capture of ?` | Đối số kiểu bất kỳ chưa biết | Tôi có đang cố ghi giá trị vào `List<?>`? |
| `capture of ? extends T` | Kiểu ẩn là `T` hoặc kiểu con | Tôi có đang cố thêm `T` vào nguồn chỉ bảo đảm đọc được như `T`? |
| `capture of ? super T` | Kiểu ẩn là `T` hoặc kiểu cha | Tôi có đang đòi đọc ra `T` trong khi chỉ đảm bảo `Object`? |
| `required CAP#1, found String` | Phương thức cần kiểu ẩn, nhưng được truyền `String` | Ai chứng minh `String` đúng bằng kiểu ẩn? |
| `CAP#1, CAP#2` | Compiler đang theo dõi các kiểu ẩn khác nhau | Hai vị trí có thật sự chia sẻ một kiểu phần tử không? |
| `incompatible types` | Phép gán/truyền tham số vi phạm ràng buộc | Có thể đổi hợp đồng bằng wildcard phù hợp hoặc helper `<T>` không? |

Số thứ tự CAP có thể thay đổi tùy ngữ cảnh; không nên viết logic dựa vào thứ tự nhãn ấy. Thông báo “capture of ...” **không tự động có nghĩa phải ép kiểu**, cũng không chứng minh dữ liệu trong danh sách đã bị hỏng.

## 13. Cách điều tra một lỗi thực tế theo từng bước

Khi gặp một thông báo lớn liên quan đến capture:

1. **Đọc dòng gọi gây lỗi**, không bắt đầu bằng tìm tên `CAP#1` trong project. Xác định `add`, `set`, `get` hay lời gọi một phương thức generic.
2. **Tìm kiểu khai báo của receiver**: `List<?>`, `List<? extends Number>`, `List<? super Integer>` hay một kiểu lồng nhau như `List<List<?>>`.
3. **Tìm tham số kiểu mà phương thức cần**. Ví dụ `add(E)` cần `E` của chính danh sách, `set(int,E)` cần một `E`, còn `get(int)` trả `E`.
4. **Ghi rõ hướng dữ liệu**: phần tử đi **từ danh sách ra** hay **đi vào danh sách**? Hướng này quyết định `extends`/`super` nếu có thể thay đổi chữ ký.
5. **Kiểm tra quan hệ giữa nhiều kiểu ẩn**: cùng một danh sách có thể dùng helper `<T>`; nhiều danh sách độc lập đòi ràng buộc thực sự trong chữ ký.
6. **Chọn sửa đổi nhỏ nhất mà vẫn an toàn kiểu**: dùng `Object` khi chỉ đọc chung, dùng helper capture khi giữ cùng kiểu ẩn, dùng PECS cho nguồn/đích, hoặc dùng `List<T>` nếu cần một kiểu cụ thể.
7. **Biên dịch lại** với `javac -Xdiags:verbose` nếu cần chi tiết; sau khi biên dịch thành công, kiểm tra thêm hành vi runtime như danh sách rỗng hoặc unmodifiable.

Điều quan trọng là **sửa quan hệ kiểu thật của chương trình**, không biến một lỗi compile-time có ích thành một lỗi runtime bằng raw cast.

## 14. Bài tập tự kiểm tra

Cho:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<?> a = integers;
List<? extends Number> b = integers;
List<? super Integer> c = integers;
```

Hãy dự đoán:

1. `a.add(3)` có biên dịch không? Nếu báo `CAP#1`, kiểu ẩn đến từ đâu?
2. `Number x = b.get(0)` có hợp lệ không? `b.add(3)` thì sao?
3. `c.add(3)` có hợp lệ không? `Integer y = c.get(0)` thì sao?
4. `a.set(0, a.get(0))` có thể gây lỗi capture không? Có cách dùng helper nào an toàn hơn?
5. Hai biến `List<?> from` và `List<?> to` có được mặc định cùng kiểu phần tử chỉ vì cùng dùng `?` không?
6. `CAP#1` là một lớp runtime hay chỉ là ký hiệu compiler?

**Đáp án:**

1. Không. `CAP#1` biểu diễn kiểu phần tử ẩn được capture từ `List<?>`; compiler không biết liệu `Integer` có phù hợp.
2. `get` đọc an toàn dưới `Number` vì cận trên; `add(3)` không biên dịch vì kiểu ẩn có thể là một kiểu con khác của `Number`.
3. `add(3)` hợp lệ vì mọi kiểu `? super Integer` đều nhận được `Integer`. `get` chỉ bảo đảm `Object`, nên không gán thẳng cho `Integer`.
4. Có; dùng `static <T> void helper(List<T> values)` và đặt cả `get`/`set` trong helper để cùng kiểu `T` được kiểm tra thống nhất.
5. Không. Hai wildcard có thể biểu diễn hai kiểu phần tử khác nhau; nếu cần sao chép, thiết kế liên hệ kiểu bằng `<T>`, `? extends T` và `? super T`.
6. `CAP#1` là tên nội bộ trong chẩn đoán compiler, không phải lớp runtime. Không thể tạo đối tượng hay khai báo biến mang tên kiểu `CAP#1` trong Java.

## 15. Ghi nhớ

Khi thấy **`CAP#1` / `capture of ?`**, hãy đọc: **“compiler đang theo dõi một kiểu generic có tồn tại nhưng chưa biết chính xác; thao tác của tôi có đang giả định quá nhiều về kiểu ấy không?”**. Nếu thông báo nói `? extends T`, bạn thường biết đủ để **đọc dưới `T`**; nếu nói `? super T`, bạn thường biết đủ để **ghi giá trị `T`**; nếu nói `?`, bạn chủ yếu chỉ có thể đọc an toàn dưới `Object`.

Nếu cần giữ nhất quán **một kiểu ẩn** qua nhiều thao tác trên cùng danh sách, một helper có type parameter `<T>` giúp compiler biểu diễn mối liên hệ đó. Nếu các nguồn/đích thật sự có các kiểu khác nhau, hãy mô tả quan hệ bằng wildcard có cận phù hợp. Cách tiếp cận này giải quyết nguyên nhân của lỗi capture mà vẫn giữ kiểm tra an toàn kiểu của Java Generics.