# `NoSuchElementException` và truy cập khi không có phần tử trong Java

Trong Java, `java.util.NoSuchElementException` là một **unchecked exception** dùng để báo rằng một thao tác **yêu cầu lấy phần tử nhưng không còn phần tử phù hợp để trả về**. Nó thường xuất hiện khi gọi `Iterator.next()` sau phần tử cuối, `Scanner.next()` lúc không còn token, `Optional.get()` khi `Optional` rỗng, hoặc `Queue.remove()` trên hàng đợi trống.

Điểm cốt lõi không phải mọi collection trống đều tự ném `NoSuchElementException`. **Chỉ lời gọi tới một API có hợp đồng lấy phần tử theo kiểu “không có thì ném” mới phát sinh ngoại lệ này**, và từng API có lựa chọn an toàn tương ứng: `hasNext()`, `hasNextLine()`, `poll()`, `peek()`, `isPresent()`, `orElseThrow(...)` hoặc một kiểu kết quả khác.

Bài học làm rõ **lúc nào `NoSuchElementException` xuất hiện, kiểm tra thế nào, xử lý khi nào, vì sao “đã kiểm tra rồi” vẫn có thể thất bại trong chương trình có thay đổi trạng thái, và cách lựa chọn API có hợp đồng phù hợp**. Các chương trình hoàn chỉnh dùng Java 17+ với đầu ra được ghi rõ; đoạn minh họa không độc lập được gắn nhãn riêng.

## 1. Định nghĩa, phân cấp và ý nghĩa

`NoSuchElementException` nằm trong `java.util` và có hệ phân cấp:

```text
java.lang.Object
  └── java.lang.Throwable
       └── java.lang.Exception
            └── java.lang.RuntimeException
                 └── java.util.NoSuchElementException
```

Điều này có nghĩa:

- Nó **không phải checked exception**. Compiler không bắt buộc caller `catch` hoặc khai báo `throws`.
- Nó vẫn là một exception thực sự, có thể bị `throw` và `catch`, có message và stack trace như các loại `Throwable` thông thường.
- Nếu không có handler, nó sẽ lan lên call stack và có thể làm đường xử lý đang chạy kết thúc bất thường.
- Lớp này mô tả một **lời gọi đòi hỏi phần tử nhưng phần tử được yêu cầu không tồn tại theo hợp đồng API**. Nó không tự có nghĩa “cả ứng dụng bị hỏng” hoặc “dữ liệu bị mất”.
- `NoSuchElementException` không là lớp con của `IllegalArgumentException`, `IllegalStateException` hoặc `IndexOutOfBoundsException`; các loại đó cùng thuộc những nhánh unchecked khác nhau.

Bạn cần import:

```java
import java.util.NoSuchElementException;
```

Nếu sử dụng nhiều lớp trong `java.util`, có thể import từng lớp cụ thể. Phần lớn chương trình không cần tự `new NoSuchElementException`: thư viện JDK sẽ ném nó khi một lời gọi truy xuất vượt khỏi điều kiện được cho phép.

## 2. Phân biệt “không có phần tử” với những thất bại khác

Một số tình huống trông giống nhau nhưng thuộc các hợp đồng khác:

| Tình huống | API ví dụ | Kết quả thường gặp |
| --- | --- | --- |
| Iterator đã hết nhưng vẫn gọi lấy tiếp | `Iterator.next()` | `NoSuchElementException` |
| Scanner không còn token | `Scanner.next()` | `NoSuchElementException` |
| Scanner không còn dòng | `Scanner.nextLine()` | `NoSuchElementException` |
| `Optional` rỗng nhưng gọi `get()` | `Optional.get()` | `NoSuchElementException` |
| Hàng đợi trống nhưng gọi `remove()` hoặc `element()` | `Queue` | `NoSuchElementException` |
| Hàng đợi trống và gọi `poll()` hoặc `peek()` | `Queue` | Trả `null` theo hợp đồng, không ném vì rỗng |
| Chỉ số mảng/danh sách nằm ngoài phạm vi | `List.get(index)` | `IndexOutOfBoundsException` |
| Tham chiếu object là `null` và bị dereference | `obj.method()` | `NullPointerException` |
| Scanner đang đóng và bị dùng tiếp | `Scanner.next()` | `IllegalStateException` |
| Scanner còn token nhưng không khớp kiểu yêu cầu | `Scanner.nextInt()` | `InputMismatchException` |
| Gọi `Iterator.remove()` sai trình tự | Nhiều iterator hỗ trợ remove | `IllegalStateException` |
| Collection bị sửa cấu trúc sai cách trong khi lặp | Nhiều iterator fail-fast | Có thể `ConcurrentModificationException` |

**Không dùng một `catch (RuntimeException)` để coi các tình huống này đều là “hết dữ liệu”.** Chúng có nguyên nhân và cách sửa rất khác nhau. Cách suy luận chính xác luôn bắt đầu từ **contract của phương thức đang gọi**, không chỉ từ tên collection.

## 3. Hai họ API: lấy bắt buộc và lấy có tín hiệu rỗng

Nhiều API cung cấp cả hai phong cách:

**Phong cách bắt buộc có phần tử**:

```java
E value = iterator.next();  // Nếu hết thì ném.
E head  = queue.remove();   // Nếu queue rỗng thì ném.
```

Đây là **mã khung minh họa** trong ngữ cảnh có `iterator` và `queue` được khai báo.

**Phong cách có thể không có phần tử**:

```java
if (iterator.hasNext()) {
    E value = iterator.next();
}

E head = queue.poll();  // Trả null khi queue rỗng.
```

Đây cũng là **mã khung minh họa**, chưa có class `E` hoặc phần khai báo biến đầy đủ. Điều quan trọng là lựa chọn API đã thay đổi hợp đồng giữa caller và phương thức:

- Với `next()` hoặc `remove()`, caller nói: “Tôi kỳ vọng phần tử tồn tại; nếu không, đây là lỗi đối với thao tác này”.
- Với `hasNext()` hoặc `poll()`, caller nói: “Không có phần tử là một kết quả có thể xảy ra và tôi sẽ chủ động xử lý”.

Không có một kiểu nào luôn tốt hơn. **Nếu phần tử là bất biến bắt buộc, ném lỗi có thể đúng; nếu hết dữ liệu là nhánh thường gặp, kiểm tra/trả kết quả rỗng thường rõ hơn.**

## 4. `Iterator.next()`: ví dụ kinh điển nhất

`Iterator<E>` có hai phương thức thường dùng:

- `boolean hasNext()`: có thêm phần tử để lặp hay không?
- `E next()`: trả phần tử kế tiếp; ném `NoSuchElementException` nếu không còn phần tử.

Lưu chương trình **`IteratorExhaustionDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorExhaustionDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Bình");
        Iterator<String> iterator = names.iterator();

        System.out.println(iterator.next());
        System.out.println(iterator.next());
        System.out.println("Còn phần tử: " + iterator.hasNext());

        try {
            iterator.next();
            System.out.println("Không đến dòng này");
        } catch (NoSuchElementException e) {
            System.out.println("Đã hết phần tử");
        }
        System.out.println("Kết thúc");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IteratorExhaustionDemo.java
java IteratorExhaustionDemo
```

**Stdout chính xác**:

```text
An
Bình
Còn phần tử: false
Đã hết phần tử
Kết thúc
```

Sau hai lần gọi `next()` thành công, vị trí lặp đã tới cuối danh sách. `hasNext()` trả `false`; lời gọi `next()` thứ ba vi phạm hợp đồng và ném `NoSuchElementException`.

Lỗi không xảy ra khi **tạo iterator** và cũng không tự xảy ra lúc **hasNext() trả false**; nó xảy ra ở **lời gọi đòi lấy phần tử tiếp theo khi không có phần tử đó**.

## 5. Cách duyệt `Iterator` an toàn

Pattern chuẩn:

```java
while (iterator.hasNext()) {
    E item = iterator.next();
    process(item);
}
```

Đây là **mã minh họa**, các tên `E` và `process` đại diện cho kiểu và xử lý thích hợp. Nó thể hiện hợp đồng: **chỉ gọi `next()` khi điều kiện còn phần tử được xác nhận trong luồng duyệt thông thường**.

Ví dụ Java 17 **`SafeIteratorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

public class SafeIteratorDemo {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(2, 4, 6);
        Iterator<Integer> it = numbers.iterator();
        int sum = 0;

        while (it.hasNext()) {
            sum += it.next();
        }

        System.out.println("Tổng: " + sum);
        System.out.println("Đã hết: " + !it.hasNext());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SafeIteratorDemo.java
java SafeIteratorDemo
```

**Stdout chính xác**:

```text
Tổng: 12
Đã hết: true
```

Ưu điểm của pattern:

- Hết dữ liệu là **điều kiện kết thúc vòng lặp**, không phải ngoại lệ dùng để điều khiển vòng lặp bình thường.
- Không cần bắt `NoSuchElementException` trong mỗi vòng.
- Người đọc dễ nhìn thấy điều kiện dừng.
- Có thể tích lũy, lọc và xử lý phần tử mà không suy đoán số phần tử ban đầu.

**Giới hạn:** điều kiện `hasNext()` và lời gọi `next()` chỉ tạo thành một pattern tin cậy khi iterator/nguồn được sử dụng theo đúng hợp đồng và không bị thay đổi bất hợp lệ trong khoảng giữa. Nó không phải lời hứa thread-safe cho mọi iterator.

## 6. Vòng lặp enhanced `for` và khi nào nên dùng

Với một đối tượng `Iterable` thông thường, vòng lặp enhanced `for` sử dụng cơ chế iterator ở bên dưới:

```java
for (String name : names) {
    System.out.println(name);
}
```

Đây là **mã minh họa** với `names` là một `Iterable<String>`. Cú pháp giúp giảm khả năng viết sai trình tự `hasNext()/next()` bằng tay và thích hợp khi chỉ cần lần lượt duyệt phần tử.

Tuy nhiên:

1. Enhanced `for` không thay đổi bản chất của iterator; nếu iterator được cài đặt sai, nó vẫn có thể gặp lỗi runtime.
2. Với collection fail-fast, sửa cấu trúc collection trực tiếp trong khi lặp có thể ném `ConcurrentModificationException`.
3. Nếu cần xóa qua iterator, API `Iterator.remove()` (khi hỗ trợ) có quy tắc riêng; không thay thế bằng cách gọi `collection.remove(...)` tùy tiện trong vòng `for`.
4. Với nguồn dữ liệu lazily loaded hoặc iterator liên quan I/O, cần xét exception, hiệu năng và vòng đời tài nguyên theo API cụ thể.

**Enhanced `for` là cách viết an toàn hơn cho việc duyệt thông thường, không phải cơ chế tự động chống mọi thay đổi đồng thời.**

## 7. Đừng nhầm `next()` hết phần tử với `remove()` sai trạng thái

`Iterator.remove()` có hợp đồng khác `next()`. Trong nhiều iterator có hỗ trợ xóa, gọi `remove()` **trước lần `next()` hợp lệ đầu tiên**, hoặc gọi `remove()` **hai lần sau cùng một `next()`**, sẽ ném `IllegalStateException`.

Ví dụ Java 17 độc lập **`IteratorStateVsElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorStateVsElementDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList("A"));
        Iterator<String> it = values.iterator();

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("Sai trạng thái remove");
        }

        System.out.println("next: " + it.next());
        it.remove();
        System.out.println("Danh sách: " + values);

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Không còn phần tử next");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IteratorStateVsElementDemo.java
java IteratorStateVsElementDemo
```

**Stdout chính xác**:

```text
Sai trạng thái remove
next: A
Danh sách: []
Không còn phần tử next
```

Ở lời gọi đầu, `remove()` sai **thứ tự sử dụng API**, không phải đang cố lấy phần tử tiếp. Sau `next()` và `remove()` thành công, iterator đã hết và lần `next()` tiếp theo mới ném `NoSuchElementException`.

Ngoài ra, một số iterator không hỗ trợ `remove()` và có thể ném `UnsupportedOperationException`. Không suy từ tên method rằng mọi iterator đều cho phép xóa.

## 8. `Scanner.next()`: token hết thì ném

`Scanner` cung cấp các phương thức đọc dữ liệu token từ nguồn:

- `hasNext()`: có token tiếp theo hay không?
- `next()`: lấy token tiếp theo; nếu hết token thì ném `NoSuchElementException`.
- `hasNextInt()` / `nextInt()`: kiểm tra/đọc token dạng `int` theo bộ phân tách và locale/radix phù hợp.
- `hasNextLine()` / `nextLine()`: kiểm tra/đọc dòng thay vì token.

Ví dụ **`ScannerEndDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerEndDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("alpha beta")) {
            System.out.println(scanner.next());
            System.out.println(scanner.next());
            System.out.println("hasNext: " + scanner.hasNext());

            try {
                scanner.next();
            } catch (NoSuchElementException e) {
                System.out.println("Scanner không còn token");
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ScannerEndDemo.java
java ScannerEndDemo
```

**Stdout chính xác**:

```text
alpha
beta
hasNext: false
Scanner không còn token
```

`Scanner("alpha beta")` đọc từ một chuỗi cố định, không phụ thuộc console. Sau hai token, `hasNext()` là `false`, nên `next()` bị từ chối.

Trong ví dụ, `Scanner` triển khai `AutoCloseable`, vì thế dùng `try-with-resources` để quản lý vòng đời. Nhưng lưu ý khi Scanner bọc một nguồn được chia sẻ: **đóng Scanner có thể đóng luôn nguồn bên dưới**; không tự ý đóng `Scanner(System.in)` nếu phần khác của chương trình còn cần dùng `System.in`.

## 9. `Scanner.nextLine()`: hết dòng không giống hết token

`Scanner.nextLine()` hoạt động theo **dòng**, không phải chỉ lấy token phân tách bằng whitespace. Nếu không tìm được dòng mới, nó có thể ném `NoSuchElementException`.

Ví dụ độc lập **`ScannerLineDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("dòng một\ndòng hai")) {
            while (scanner.hasNextLine()) {
                System.out.println("Đọc: " + scanner.nextLine());
            }

            try {
                scanner.nextLine();
            } catch (NoSuchElementException e) {
                System.out.println("Không còn dòng");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ScannerLineDemo.java
java ScannerLineDemo
```

**Stdout chính xác**:

```text
Đọc: dòng một
Đọc: dòng hai
Không còn dòng
```

Tách bạch:

- `hasNext()` kiểm tra **token** còn hay không.
- `hasNextLine()` kiểm tra **dòng** có thể đọc được hay không.
- `next()` đọc token.
- `nextLine()` đọc phần còn lại của dòng hiện tại, không nhất thiết tương ứng một token.

Nếu bạn vừa gọi `nextInt()` rồi `nextLine()`, phần còn lại của dòng chứa số có thể là chuỗi rỗng; đó **không nhất thiết là dấu hiệu đã hết dữ liệu**. Thiết kế parser cần thống nhất chế độ đọc token hay đọc dòng.

## 10. Scanner: còn token nhưng sai định dạng là lỗi khác

`Scanner.nextInt()` có thể phát sinh **`InputMismatchException`** nếu token tiếp theo không thể diễn giải theo kiểu `int` phù hợp. Nó chỉ báo **`NoSuchElementException`** khi không có token để lấy.

Lưu **`ScannerMismatchDemo.java`**:

```java
import java.util.InputMismatchException;
import java.util.NoSuchElementException;
import java.util.Scanner;

public class ScannerMismatchDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("42 abc")) {
            System.out.println("Số: " + scanner.nextInt());

            try {
                scanner.nextInt();
            } catch (InputMismatchException e) {
                System.out.println("Token không phải số nguyên");
            }

            System.out.println("Token còn lại: " + scanner.next());

            try {
                scanner.nextInt();
            } catch (NoSuchElementException e) {
                System.out.println("Đã hết token");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ScannerMismatchDemo.java
java ScannerMismatchDemo
```

**Stdout chính xác**:

```text
Số: 42
Token không phải số nguyên
Token còn lại: abc
Đã hết token
```

Sau `nextInt()` gặp `abc`, Scanner ném `InputMismatchException` và **không tiêu thụ token không khớp**; `next()` sau đó đọc chính `abc`. Lần `nextInt()` cuối gặp EOF nên ném `NoSuchElementException`.

Với Scanner đã bị **đóng**, nhiều thao tác như `next()` sẽ ném `IllegalStateException`. **Không bắt `NoSuchElementException` để giả vờ rằng scanner đã đóng hoặc dữ liệu sai định dạng cũng là EOF.**

## 11. Dùng `hasNextInt()` và lựa chọn xử lý token sai

Nếu input phải là số nguyên, một pattern rõ ràng:

```java
if (!scanner.hasNext()) {
    // Kết thúc nguồn: không có token.
} else if (!scanner.hasNextInt()) {
    String badToken = scanner.next();
    // Ghi nhận/đưa ra lỗi xác thực cho badToken.
} else {
    int value = scanner.nextInt();
    // Xử lý value.
}
```

Đây là **mã khung minh họa**, chưa khai báo `scanner`. Cách xử lý phân biệt ba tình huống:

1. **Không còn dữ liệu**: `hasNext() == false`.
2. **Còn token nhưng không phải int**: `hasNext() == true`, `hasNextInt() == false`.
3. **Có token int hợp lệ**: đọc bằng `nextInt()`.

Trong nguồn có thể thay đổi đồng thời, bản thân việc kiểm tra không là bảo đảm tuyệt đối; cần tuân thủ hợp đồng đồng bộ của nguồn. Với `Scanner` trên input tương tác, phương thức `hasNext()` cũng có thể **chờ dữ liệu**; đừng coi nó là phép kiểm tra tức thời và không blocking trong mọi môi trường.

Một hệ thống xử lý input ổn định nên định nghĩa rõ: token sai sẽ bị loại bỏ, yêu cầu nhập lại, hay làm dừng toàn bộ tác vụ?

## 12. `Optional.get()`: rỗng không có nghĩa là `null`

`Optional<T>` đại diện cho một giá trị có thể **có hoặc không có**. Một `Optional.empty()` không chứa giá trị; gọi `get()` trên nó sẽ ném `NoSuchElementException`.

Ví dụ **`OptionalGetDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;

public class OptionalGetDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("OK");
        Optional<String> missing = Optional.empty();

        System.out.println("Có: " + present.get());
        System.out.println("Rỗng: " + missing.isEmpty());

        try {
            missing.get();
        } catch (NoSuchElementException e) {
            System.out.println("Không có giá trị Optional");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 OptionalGetDemo.java
java OptionalGetDemo
```

**Stdout chính xác**:

```text
Có: OK
Rỗng: true
Không có giá trị Optional
```

`Optional.get()` không trả `null` khi rỗng; nó ném exception. **Cũng không nên nhầm `Optional.empty()` với một `Optional` chứa `null`**: `Optional.of(null)` ném `NullPointerException`, trong khi `Optional.ofNullable(null)` tạo `Optional.empty()`.

Trong Java hiện đại, khi không biết chắc có giá trị, nhiều API khác của Optional thể hiện ý định rõ hơn `get()`.

## 13. Những lựa chọn thay `Optional.get()`

Các lựa chọn thông dụng:

| API | Khi có giá trị | Khi rỗng |
| --- | --- | --- |
| `get()` | Trả giá trị | Ném `NoSuchElementException` |
| `orElse(defaultValue)` | Trả giá trị | Trả fallback được truyền |
| `orElseGet(supplier)` | Trả giá trị | Gọi supplier để tạo fallback |
| `orElseThrow()` | Trả giá trị | Ném `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Trả giá trị | Tạo và ném exception do supplier cung cấp |
| `ifPresent(consumer)` | Gọi consumer | Bỏ qua |
| `ifPresentOrElse(present, empty)` | Chạy nhánh present | Chạy nhánh empty |
| `isPresent()` / `isEmpty()` | Trả boolean | Trả boolean đối ứng |

**Không có lựa chọn nào luôn đúng.** Nếu không có dữ liệu là kết quả bình thường, dùng fallback hoặc nhánh rỗng. Nếu thiếu dữ liệu **vi phạm hợp đồng**, `orElseThrow(...)` với loại exception có ngữ nghĩa cụ thể có thể tốt hơn.

Chú ý: `orElse(value)` đánh giá **đối số `value` trước khi gọi method** theo quy tắc Java, ngay cả khi Optional đang có giá trị; `orElseGet(supplier)` chỉ gọi supplier khi Optional rỗng. Điều này quan trọng nếu fallback tốn kém hoặc có side effect.

## 14. Ví dụ Java 17: fallback của `Optional`

Lưu **`OptionalFallbackDemo.java`**:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String createFallback() {
        System.out.println("Tạo fallback");
        return "mặc định";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("thật");
        Optional<String> empty = Optional.empty();

        System.out.println("orElse: "
                + present.orElse(createFallback()));
        System.out.println("orElseGet: "
                + present.orElseGet(OptionalFallbackDemo::createFallback));
        System.out.println("empty: "
                + empty.orElseGet(OptionalFallbackDemo::createFallback));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 OptionalFallbackDemo.java
java OptionalFallbackDemo
```

**Stdout chính xác**:

```text
Tạo fallback
orElse: thật
orElseGet: thật
Tạo fallback
empty: mặc định
```

Lần gọi `present.orElse(createFallback())` in `Tạo fallback` dù Optional chứa `"thật"`. Ngược lại, `present.orElseGet(...)` không gọi supplier. Với Optional rỗng, `orElseGet` mới tạo fallback.

Hành vi này **không thay đổi ngoại lệ của `get()`**, nhưng giúp chọn API hợp với ý nghĩa rỗng mà không dùng `try/catch NoSuchElementException` như một phần luồng xử lý bình thường.

## 15. `orElseThrow` có hai hình thức khác nhau

- `optional.orElseThrow()`: trả giá trị nếu có; nếu không có thì ném `NoSuchElementException`.
- `optional.orElseThrow(() -> new SomeException(...))`: cho phép caller **chọn loại exception** được tạo khi Optional rỗng.

Ví dụ Java 17 độc lập **`OptionalOrElseThrowDemo.java`**:

```java
import java.util.Optional;

public class OptionalOrElseThrowDemo {
    static String requireName(Optional<String> optional) {
        return optional.orElseThrow(
                () -> new IllegalArgumentException(
                        "name là bắt buộc"));
    }

    public static void main(String[] args) {
        System.out.println(requireName(Optional.of("Lan")));

        try {
            requireName(Optional.empty());
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 OptionalOrElseThrowDemo.java
java OptionalOrElseThrowDemo
```

**Stdout chính xác**:

```text
Lan
Bắt: name là bắt buộc
```

Trong ví dụ, **thiếu tên** là vi phạm tiền điều kiện của API `requireName`, nên `IllegalArgumentException` thể hiện hợp đồng cụ thể hơn là một lỗi truy xuất Optional chung.

Nếu thiếu bản ghi là nhánh nghiệp vụ dự kiến, có thể chọn trả `Optional` lên caller hoặc một kiểu kết quả domain, thay vì ép thành exception.

**Một lưu ý về checked exception:** phiên bản `orElseThrow(exceptionSupplier)` có thể được sử dụng với supplier tạo checked exception; lúc đó phương thức bao ngoài phải catch/declare theo luật checked exceptions của Java. Nó không tự biến checked exception thành unchecked.

## 16. `OptionalInt`, `OptionalLong` và `OptionalDouble`

Java có các lớp Optional chuyên biệt cho primitive, tránh boxing trong một số tình huống:

- `OptionalInt.getAsInt()`
- `OptionalLong.getAsLong()`
- `OptionalDouble.getAsDouble()`

Khi đối tượng tương ứng rỗng, các method bắt buộc phải có phần tử này **ném `NoSuchElementException`**, tương tự `Optional<T>.get()`.

Ví dụ **`PrimitiveOptionalDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.OptionalInt;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt present = OptionalInt.of(7);
        OptionalInt missing = OptionalInt.empty();

        System.out.println("Có: " + present.getAsInt());
        System.out.println("Rỗng: " + missing.isEmpty());

        try {
            missing.getAsInt();
        } catch (NoSuchElementException e) {
            System.out.println("Không có giá trị int");
        }

        System.out.println("Fallback: " + missing.orElse(-1));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Stdout chính xác**:

```text
Có: 7
Rỗng: true
Không có giá trị int
Fallback: -1
```

Không phải vì primitive không có `null` mà `getAsInt()` sẽ luôn có giá trị: **sự vắng mặt được biểu diễn bằng trạng thái của Optional**, và lời gọi bắt buộc có giá trị vẫn có thể thất bại.

## 17. `Queue`: `remove/element` so với `poll/peek`

`java.util.Queue<E>` cung cấp hai bộ thao tác có ngữ nghĩa khác nhau khi hàng đợi trống:

| Mục đích | Ném nếu trống | Trả `null` nếu trống |
| --- | --- | --- |
| Lấy ra và xóa phần tử đầu | `remove()` | `poll()` |
| Chỉ xem phần tử đầu, không xóa | `element()` | `peek()` |

Với một queue trống, `remove()` và `element()` có thể ném `NoSuchElementException`. Trong khi đó, `poll()` và `peek()` trả `null` theo hợp đồng `Queue`.

Lưu **`QueueEmptyDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.Queue;

public class QueueEmptyDemo {
    public static void main(String[] args) {
        Queue<String> queue = new ArrayDeque<>();

        System.out.println("poll rỗng: " + queue.poll());
        System.out.println("peek rỗng: " + queue.peek());

        try {
            queue.remove();
        } catch (NoSuchElementException e) {
            System.out.println("remove rỗng: NoSuchElementException");
        }

        queue.add("A");
        System.out.println("element: " + queue.element());
        System.out.println("remove: " + queue.remove());
        System.out.println("Sau remove rỗng: " + queue.isEmpty());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 QueueEmptyDemo.java
java QueueEmptyDemo
```

**Stdout chính xác**:

```text
poll rỗng: null
peek rỗng: null
remove rỗng: NoSuchElementException
element: A
remove: A
Sau remove rỗng: true
```

Trong ví dụ, `ArrayDeque` không cho phép phần tử `null` nên `poll() == null` là dấu hiệu không có phần tử. **Ở mức interface `Queue` tổng quát, một số implementation có thể cho phép phần tử `null`**, nên caller không được mặc định suy luận y như vậy cho mọi loại queue.

Chọn API theo hợp đồng: một queue đang được dùng như nguồn công việc có thể rỗng bình thường thì `poll()` thường đúng hơn `remove()`.

## 18. `Deque` và stack: `getFirst/removeFirst/pop`

`java.util.Deque<E>` mở rộng các thao tác ở hai đầu hàng đợi. Một số method **ném `NoSuchElementException` khi rỗng**:

- `getFirst()` và `getLast()`: đọc nhưng không xóa.
- `removeFirst()` và `removeLast()`: đọc rồi xóa.
- `pop()`: thao tác stack tương đương lấy và xóa phần tử đầu; ném nếu rỗng.

Những lựa chọn trả tín hiệu rỗng là:

- `peekFirst()` / `peekLast()`.
- `pollFirst()` / `pollLast()`.
- `peek()` / `poll()` ở phía đầu queue.

Ví dụ **`DequeEmptyDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEmptyDemo {
    public static void main(String[] args) {
        Deque<String> stack = new ArrayDeque<>();

        System.out.println("peek rỗng: " + stack.peek());

        try {
            stack.pop();
        } catch (NoSuchElementException e) {
            System.out.println("pop rỗng: NoSuchElementException");
        }

        stack.push("A");
        stack.push("B");

        System.out.println("top: " + stack.getFirst());
        System.out.println("pop: " + stack.pop());
        System.out.println("pop: " + stack.pop());
        System.out.println("poll cuối: " + stack.poll());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 DequeEmptyDemo.java
java DequeEmptyDemo
```

**Stdout chính xác**:

```text
peek rỗng: null
pop rỗng: NoSuchElementException
top: B
pop: B
pop: A
poll cuối: null
```

Nếu dùng `Deque` làm stack, `push`/`pop` biểu diễn ngữ nghĩa LIFO, còn `peek` cho phép kiểm tra phần tử đầu mà không xóa. **Không ném exception để thông báo một stack rỗng theo nhánh bình thường nếu caller có thể chủ động xử lý bằng `peek` hoặc `isEmpty`.**

## 19. Cẩn thận với `null` trong collection

Không nên nói “`NoSuchElementException` chính là giá trị `null`”:

- `NoSuchElementException` là **một đối tượng lỗi**, có loại và stack trace.
- `null` là **giá trị tham chiếu** biểu thị không trỏ tới object.
- `Optional.empty()` là **một object Optional có trạng thái rỗng**, không phải `null`.
- `Queue.poll()` có thể dùng `null` làm tín hiệu rỗng theo hợp đồng của interface.
- Một số collection có thể chứa **phần tử `null` hợp lệ**, nên `null` trả về không phải lúc nào cũng chứng minh không có phần tử.
- `ArrayDeque` không cho phép thêm `null`, vì vậy nó tránh được sự mơ hồ này trong các ví dụ `Queue`/`Deque` ở trên.

Nếu hợp đồng API cho phép phân biệt **“không có phần tử”** và **“có một phần tử mà giá trị là null”**, hãy thiết kế cơ chế trả trạng thái riêng, ví dụ `Optional` (với lưu ý Optional không chứa null), một result object, hoặc kiểm tra cấu trúc theo ngữ cảnh.

**Đừng chuyển bừa `NoSuchElementException` thành `null`** nếu caller của API vốn cần biết đây là vi phạm invariant bất thường.

## 20. `Enumeration.nextElement()` cũng có thể ném

API cũ `java.util.Enumeration<E>` có hai phương thức:

- `hasMoreElements()`: kiểm tra còn phần tử hay không.
- `nextElement()`: lấy phần tử kế tiếp; ném `NoSuchElementException` nếu hết.

Ví dụ **`EnumerationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.Enumeration;
import java.util.NoSuchElementException;

public class EnumerationDemo {
    public static void main(String[] args) {
        Enumeration<String> e =
                Collections.enumeration(Arrays.asList("X"));

        System.out.println("Phần tử: " + e.nextElement());
        System.out.println("Còn: " + e.hasMoreElements());

        try {
            e.nextElement();
        } catch (NoSuchElementException ex) {
            System.out.println("Enumeration đã hết");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 EnumerationDemo.java
java EnumerationDemo
```

**Stdout chính xác**:

```text
Phần tử: X
Còn: false
Enumeration đã hết
```

`Enumeration` xuất hiện trong các API và code cũ; khi tạo thiết kế mới, `Iterator` hoặc API collection/stream phù hợp thường quen thuộc hơn. Nhưng khi sử dụng `Enumeration` từ thư viện, cần giữ đúng **cặp `hasMoreElements()/nextElement()`**, không gọi `nextElement()` đến khi lỗi xảy ra như một giải pháp mặc định.

## 21. `StringTokenizer.nextToken()` khi không còn token

`java.util.StringTokenizer` là API phân tách token lâu đời. `nextToken()` ném `NoSuchElementException` khi không còn token.

Ví dụ Java 17 **`StringTokenizerDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.StringTokenizer;

public class StringTokenizerDemo {
    public static void main(String[] args) {
        StringTokenizer tokenizer = new StringTokenizer("a,b", ",");

        while (tokenizer.hasMoreTokens()) {
            System.out.println("Token: " + tokenizer.nextToken());
        }

        try {
            tokenizer.nextToken();
        } catch (NoSuchElementException e) {
            System.out.println("Không còn token");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 StringTokenizerDemo.java
java StringTokenizerDemo
```

**Stdout chính xác**:

```text
Token: a
Token: b
Không còn token
```

Ví dụ không nhằm khuyến nghị `StringTokenizer` cho mọi parser hiện đại. Nếu yêu cầu parse CSV, JSON hoặc một định dạng có escape/quote, cần thư viện/parser đúng định dạng; việc tách chuỗi bằng token đơn giản có thể không đủ.

Điểm chung là **mọi API có phương thức “lấy phần tử tiếp theo” cần nói rõ hành vi lúc kết thúc**.

## 22. `Stream.findFirst()` trả `Optional`, không tự ném vì stream rỗng

Khi dùng Java Streams:

```java
Optional<String> first = stream.findFirst();
```

Đây là **đoạn minh họa**, với `stream` là `Stream<String>`. Nếu stream không có phần tử, `findFirst()` trả `Optional.empty()`. Bản thân việc gọi `findFirst()` trên stream rỗng **không ném `NoSuchElementException`**.

Exception sẽ xuất hiện nếu caller sau đó **đòi bắt buộc một giá trị từ Optional rỗng** bằng `get()` hoặc `orElseThrow()` không đối số.

Ví dụ độc lập **`StreamOptionalDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.stream.Stream;

public class StreamOptionalDemo {
    public static void main(String[] args) {
        Optional<String> first = Stream.<String>empty().findFirst();

        System.out.println("Có phần tử: " + first.isPresent());
        System.out.println("Fallback: " + first.orElse("không có"));

        try {
            first.orElseThrow();
        } catch (NoSuchElementException e) {
            System.out.println("Bắt: Optional rỗng");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 StreamOptionalDemo.java
java StreamOptionalDemo
```

**Stdout chính xác**:

```text
Có phần tử: false
Fallback: không có
Bắt: Optional rỗng
```

Một lưu ý khác: nhiều thao tác Stream sinh Optional yêu cầu **giá trị phần tử không phải null**; nếu một phần tử `null` được chọn, hành vi có thể liên quan `NullPointerException` chứ không phải `Optional.empty()`. Không nên coi mọi stream có phần tử `null` như một stream trống.

## 23. `List.get(index)` không ném cùng loại với iterator hết

Giả sử `List<String> list = List.of("A", "B")`:

- `list.get(0)` trả `"A"`.
- `list.get(2)` truy cập chỉ số ngoài phạm vi và ném `IndexOutOfBoundsException`.
- `list.iterator().next()` được gọi đến khi iterator hết thì ném `NoSuchElementException`.

Cả hai lỗi đều do một thao tác truy xuất không thể trả phần tử, nhưng **hợp đồng truy xuất khác nhau**:

- `List.get(index)` nhận **vị trí tường minh**. Sai là chỉ số.
- `Iterator.next()` không nhận chỉ số. Sai là **không còn phần tử kế tiếp**.

Ví dụ Java 17 **`IndexVsElementDemo.java`**:

```java
import java.util.List;
import java.util.NoSuchElementException;

public class IndexVsElementDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A");

        try {
            values.get(1);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("List: chỉ số ngoài phạm vi");
        }

        var it = values.iterator();
        System.out.println("Iterator: " + it.next());

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Iterator: không còn phần tử");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 IndexVsElementDemo.java
java IndexVsElementDemo
```

**Stdout chính xác**:

```text
List: chỉ số ngoài phạm vi
Iterator: A
Iterator: không còn phần tử
```

Đừng viết một handler `catch (NoSuchElementException)` với kỳ vọng nó bắt mọi phép truy cập vượt phạm vi collection. Nó **không** tự bắt `IndexOutOfBoundsException`.

## 24. Khi nào nên tự ném `NoSuchElementException`?

Nếu bạn tự cài đặt một **Iterator**, method `next()` cần tuân thủ hợp đồng: khi không còn phần tử, ném `NoSuchElementException`. Đây là tình huống **tự tạo exception phù hợp** vì bạn đang triển khai API tiêu chuẩn.

Ví dụ:

```java
@Override
public E next() {
    if (!hasNext()) {
        throw new NoSuchElementException(
                "Không còn phần tử trong iterator");
    }
    return data[index++];
}
```

Đây là **mã minh họa** bên trong một class implements `Iterator<E>`, có các field `data` và `index` tương ứng. `NoSuchElementException` nên được ném **trước khi truy cập ngoài phạm vi mảng/collection** để giữ contract của iterator, thay vì để một `ArrayIndexOutOfBoundsException` ngẫu nhiên xuất hiện.

Không cần tự ném `NoSuchElementException` trong mọi method tra cứu thất bại của ứng dụng. Nếu ứng dụng có contract “không tìm thấy mã người dùng” là một trường hợp nghiệp vụ dự kiến, một `Optional` hoặc một kiểu kết quả rõ ràng có thể phù hợp hơn.

## 25. Ví dụ tự cài đặt `Iterator` đúng hợp đồng

Lưu **`CustomIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;

public class CustomIteratorDemo {
    static class RangeIterator implements Iterator<Integer> {
        private int current;
        private final int limit;

        RangeIterator(int start, int limit) {
            if (start > limit) {
                throw new IllegalArgumentException(
                        "start không được lớn hơn limit");
            }
            this.current = start;
            this.limit = limit;
        }

        @Override
        public boolean hasNext() {
            return current < limit;
        }

        @Override
        public Integer next() {
            if (!hasNext()) {
                throw new NoSuchElementException(
                        "Range đã hết");
            }
            return current++;
        }
    }

    public static void main(String[] args) {
        RangeIterator it = new RangeIterator(3, 5);

        while (it.hasNext()) {
            System.out.println("Số: " + it.next());
        }

        try {
            it.next();
        } catch (NoSuchElementException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CustomIteratorDemo.java
java CustomIteratorDemo
```

**Stdout chính xác**:

```text
Số: 3
Số: 4
Bắt: Range đã hết
```

Dạng khoảng ở đây là **[start, limit)**, nghĩa là bao gồm start và không bao gồm limit. Khi `current == limit`, `hasNext()` trả false và `next()` ném một `NoSuchElementException` với message do chính class thiết kế.

Ví dụ dùng `Integer` để thực hiện `Iterator<Integer>`; boxing là chi tiết nhỏ chấp nhận được cho mục đích học. Với dãy số rất lớn hoặc yêu cầu hiệu năng, có thể dùng primitive iterator hoặc stream chuyên biệt nếu hợp lý.

Lưu ý về giới hạn số: nếu tự thiết kế iterator số nguyên tổng quát, hãy cân nhắc overflow của `current++` gần `Integer.MAX_VALUE` và điều kiện dừng. Ví dụ khoảng nhỏ ở đây không gặp tình huống đó.

## 26. Khi nào kiểm tra trước tốt hơn catch?

Pattern thông thường:

```java
while (iterator.hasNext()) {
    consume(iterator.next());
}
```

thường tốt hơn pattern dựa trên exception để kết thúc:

```java
while (true) {
    try {
        consume(iterator.next());
    } catch (NoSuchElementException e) {
        break;
    }
}
```

Cả hai là **mã minh họa** với `consume` chưa được định nghĩa. Pattern thứ hai có vấn đề tinh tế: **nếu `consume(...)` cũng ném `NoSuchElementException` từ logic riêng**, handler quá rộng có thể bắt nhầm lỗi của `consume` và coi nó là iterator đã hết.

Khi dùng vòng lặp `hasNext()`, phạm vi điều kiện kết thúc rõ ràng hơn. Nếu vì giao thức đặc biệt bắt buộc dùng exception làm tín hiệu EOF, hãy **thu hẹp phạm vi catch** chỉ quanh lời gọi nguồn và tài liệu hóa lựa chọn đó.

Nguyên tắc: **đừng sử dụng ngoại lệ để điều khiển một nhánh bình thường khi API cung cấp phép kiểm tra hoặc giá trị rỗng rõ ràng**.

## 27. Vì sao `hasNext()` không phải phép khóa đồng thời?

Trong chương trình một luồng tuân thủ hợp đồng iterator, cặp `hasNext()/next()` là cách duyệt chuẩn. Nhưng trong chương trình đa luồng hoặc với nguồn thay đổi từ nơi khác, **kiểm tra rồi thao tác** có thể không nguyên tử.

Ví dụ khung:

```java
if (!queue.isEmpty()) {
    // Thread khác có thể lấy phần tử cuối ở đây.
    String value = queue.remove();
}
```

Đây là **phản ví dụ concurrency**, chưa có khai báo queue. Với một queue chia sẻ phù hợp, thread khác có thể làm queue rỗng **sau `isEmpty()` nhưng trước `remove()`**. Khi đó `remove()` có thể ném `NoSuchElementException`.

Nếu dùng một queue hỗ trợ concurrency, giải pháp thường phù hợp hơn là **thực hiện thao tác nguyên tử theo API queue**:

```java
String value = queue.poll();
if (value == null) {
    // Hàng đợi hiện rỗng, nếu queue không cho phép null element.
} else {
    process(value);
}
```

Đây là **mã minh họa** giả định queue không cho phép phần tử `null` và có hàm `process`. Các queue như `ConcurrentLinkedQueue` hoặc `BlockingQueue` có hợp đồng riêng về thao tác concurrent.

**Không chuyển sang `catch (NoSuchElementException)` để “sửa” race condition một cách mù quáng.** Hãy chọn thao tác có tính nguyên tử/đồng bộ đúng theo cấu trúc dữ liệu và chính sách chờ mong muốn.

## 28. `BlockingQueue`: khi nào không có phần tử là tạm thời?

Với một `BlockingQueue`, queue trống có thể chỉ là trạng thái **tạm thời** vì producer chưa thêm phần tử. Tùy API:

- `poll()`: có thể trả `null` ngay nếu không có phần tử.
- `poll(timeout, unit)`: đợi có giới hạn; trả `null` nếu hết thời gian mà vẫn không lấy được phần tử.
- `take()`: **chờ** cho tới khi có phần tử và có thể ném `InterruptedException` nếu bị ngắt.
- `remove()`: thao tác lấy ngay theo hợp đồng queue; khi trống có thể ném `NoSuchElementException`.

Đây là những **chính sách vận hành khác nhau**, không phải chỉ những biến thể cú pháp của cùng hành vi.

Ví dụ Java 17 độc lập, không dùng thread producer nên đầu ra xác định:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueDemo {
    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        System.out.println("poll: " + queue.poll());
        queue.add("A");
        System.out.println("poll: " + queue.poll());
        System.out.println("empty: " + queue.isEmpty());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 BlockingQueueDemo.java
java BlockingQueueDemo
```

**Stdout chính xác**:

```text
poll: null
poll: A
empty: true
```

Không nên dùng `take()` trong một ví dụ không có producer vì có thể chờ vô hạn. Khi dùng API blocking thực tế, **xử lý interrupt** đúng hợp đồng; không coi `InterruptedException` như `NoSuchElementException`.

## 29. Ngoại lệ khi không có phần tử khác với `ConcurrentModificationException`

Nhiều iterator trên collection như `ArrayList` có cơ chế **fail-fast best-effort** khi phát hiện sửa cấu trúc collection bên ngoài iterator trong lúc lặp. Khi phát hiện tình huống này, iterator có thể ném `ConcurrentModificationException`.

Điều đó **khác** với `NoSuchElementException`:

- `NoSuchElementException`: caller yêu cầu phần tử tiếp theo nhưng **không có phần tử tiếp theo** theo contract.
- `ConcurrentModificationException`: iterator phát hiện **điều kiện sửa đổi cấu trúc không phù hợp** với hợp đồng lặp của nó.

Một thay đổi cấu trúc bất hợp lệ không được giải thích lại là “đã duyệt đến cuối”. **Không bắt `NoSuchElementException` để che sửa collection sai cách**.

Cơ chế fail-fast không phải công cụ đồng bộ đảm bảo phát hiện mọi race; tài liệu JDK mô tả việc phát hiện ở mức nỗ lực tối đa trong các tình huống concurrent/structural modification. Muốn thao tác đồng thời đúng, cần chọn cấu trúc dữ liệu và quy tắc sở hữu phù hợp.

## 30. `NoSuchElementException` có constructor và message không?

Lớp này có thể được tạo trực tiếp với message:

```java
throw new NoSuchElementException(
        "Không còn bản ghi trong cursor");
```

Đây là **câu lệnh minh họa**, cần import `java.util.NoSuchElementException`. Message giúp phân biệt nguồn phần tử nếu có nhiều iterator/cursor.

Giống những `RuntimeException` thông thường, message:

- Được truy cập bằng `getMessage()`.
- Có thể là `null` tùy constructor.
- Không tự đảm bảo stack trace hoặc cause được in khi bạn chỉ gọi `getMessage()`.
- Không nên được phân tích bằng `contains(...)` để điều khiển logic nghiệp vụ.
- Không nên chứa mật khẩu, token hay dữ liệu nhạy cảm.

Nếu bạn **bọc lỗi từ tầng khác** thành một `NoSuchElementException`, phải cân nhắc có phù hợp ngữ nghĩa không. Không nên chuyển mọi sự cố I/O, database hoặc timeout thành “không có phần tử” vì như vậy caller có thể hiểu sai bản chất lỗi.

## 31. Khi nào bắt `NoSuchElementException` là hợp lý?

Có những trường hợp phù hợp:

1. Một API **bắt buộc phải có phần tử** và caller muốn chuyển exception thành trạng thái thất bại ở ranh giới.
2. Adapter phải tuân thủ một giao thức cũ dùng exception làm tín hiệu hết dữ liệu.
3. Unit test cố ý kiểm tra contract `next()` trên iterator đã hết.
4. Một lớp wrapper chuyển exception sang **loại lỗi domain rõ ràng** khi việc không có phần tử thực sự có ý nghĩa đối với API của nó.

Nhưng **không nên bắt chỉ để bỏ qua lỗi** hoặc làm chương trình như thể đã đọc được dữ liệu.

Ví dụ:

```java
try {
    return iterator.next();
} catch (NoSuchElementException e) {
    return DEFAULT_RECORD;
}
```

Đây là **mã khung minh họa**. Chỉ hợp lệ nếu `DEFAULT_RECORD` là fallback thật sự được hợp đồng cho phép và được định nghĩa rõ. Nếu phần tử bắt buộc vì dữ liệu có invariant, việc trả một object giả có thể che vấn đề.

Một cách tốt hơn khi API có lựa chọn rỗng ngay từ đầu là **trả Optional hoặc kiểu kết quả có trạng thái** thay vì bắt ngoại lệ ở mọi lần truy xuất.

## 32. Đừng bắt lỗi ở phạm vi quá rộng

Một anti-pattern:

```java
try {
    while (true) {
        Item item = iterator.next();
        process(item);
    }
} catch (NoSuchElementException ignored) {
    // Cho rằng đã lặp xong.
}
```

Đây là **mã khung phản ví dụ**. Nếu `process(item)` ném `NoSuchElementException` do một cursor khác bên trong, handler sẽ **che nhầm lỗi thực tế** và kết luận rằng iterator bên ngoài đã hết.

Nếu phải xử lý exception của một API đặc biệt, tách vùng catch đúng phạm vi:

```java
Item item;
try {
    item = iterator.next();
} catch (NoSuchElementException endOfIterator) {
    // Xử lý kết thúc nguồn ở đây.
    return;
}
process(item);
```

Đây là **mã minh họa trong một phương thức**. Nhưng với `Iterator` tiêu chuẩn, vòng lặp `hasNext()` vẫn là giải pháp bình thường hơn.

Cần nhớ **vị trí exception được ném** quan trọng ngang với **loại exception**. Một handler có phạm vi quá lớn làm mất ngữ cảnh và có thể nuốt lỗi từ các thao tác không liên quan.

## 33. Kiểm thử hành vi rỗng bằng Java thuần

Một bài test tốt không chỉ xác nhận có exception, mà còn xác nhận:

- Truy xuất khi còn phần tử hoạt động đúng.
- Khi hết, method theo hợp đồng **ném đúng `NoSuchElementException`**.
- Method có tín hiệu rỗng như `hasNext()`, `poll()` hoặc `peek()` trả giá trị dự kiến.
- Không thay đổi trạng thái hoặc làm mất phần tử ngoài ý muốn sau lời gọi thất bại.
- Nếu đó là API có fallback, fallback chỉ chạy theo những điều kiện được công bố.

Ví dụ **`NoSuchElementAssertionsDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Queue;

public class NoSuchElementAssertionsDemo {
    static void expectNoElement(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Thiếu NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("PASS: đã ném NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        Iterator<Integer> iterator = List.of(1).iterator();

        if (iterator.next() != 1 || iterator.hasNext()) {
            throw new AssertionError("Sai trạng thái iterator");
        }

        expectNoElement(iterator::next);

        Queue<String> queue = new ArrayDeque<>();
        if (queue.poll() != null) {
            throw new AssertionError("Queue phải rỗng");
        }

        expectNoElement(queue::remove);
        System.out.println("PASS: hợp đồng rỗng được giữ");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NoSuchElementAssertionsDemo.java
java NoSuchElementAssertionsDemo
```

**Stdout chính xác**:

```text
PASS: đã ném NoSuchElementException
PASS: đã ném NoSuchElementException
PASS: hợp đồng rỗng được giữ
```

`Runnable` cho phép dùng method reference `iterator::next` và `queue::remove` ở đây vì các method đó trả giá trị nhưng lời gọi trong ngữ cảnh `void` của functional interface có thể bỏ qua kết quả. `NoSuchElementException` là unchecked nên không có trở ngại checked `throws`.

Test dùng `throw new AssertionError(...)` để thất bại chủ động, không phụ thuộc cờ `-ea` của từ khóa `assert`.

## 34. Những sai lầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`NoSuchElementException` là checked nên phải khai báo `throws`.” | Sai. Nó thuộc `RuntimeException`, là unchecked. |
| “`hasNext()` trả false sẽ tự ném exception.” | Không. `next()` được gọi khi hết mới ném theo contract iterator. |
| “Mọi collection rỗng đều tự ném `NoSuchElementException`.” | Không. Phụ thuộc method: `peek/poll` có thể trả `null`. |
| “`Queue.remove()` và `Queue.poll()` giống hệt nhau.” | Không. Với queue rỗng, `remove` ném còn `poll` trả `null`. |
| “`Queue.element()` và `Queue.peek()` giống hệt nhau.” | Không. Với queue rỗng, `element` ném còn `peek` trả `null`. |
| “`Deque.pop()` trên stack rỗng trả `null`.” | Sai. `pop` ném `NoSuchElementException` khi rỗng. |
| “`Optional.empty().get()` trả `null`.” | Sai. Nó ném `NoSuchElementException`. |
| “`Optional.orElseThrow()` chỉ tạo unchecked exception khác.” | Không. Bản không tham số ném `NoSuchElementException` khi rỗng. |
| “`orElse(default())` chỉ gọi `default()` khi Optional rỗng.” | Sai. Biểu thức đối số được đánh giá trước lời gọi; dùng `orElseGet` khi cần lazy fallback. |
| “`Scanner.nextInt()` gặp chữ sẽ ném `NoSuchElementException`.” | Khi còn token sai kiểu, thường `InputMismatchException`; khi hết token mới là `NoSuchElementException`. |
| “`Scanner.nextLine()` và `Scanner.next()` luôn tương đương.” | Không. Một cái đọc dòng, một cái đọc token. |
| “`List.get(index)` vượt giới hạn ném `NoSuchElementException`.” | Sai. Thường là `IndexOutOfBoundsException`. |
| “Sau `hasNext()` chắc chắn thread khác không thể thay đổi nguồn.” | Không. Kiểm tra không tự khóa nguồn; cần tuân thủ contract concurrency. |
| “Bắt `NoSuchElementException` quanh toàn bộ vòng lặp là cách tốt nhất.” | Dễ che lỗi phát sinh từ phần xử lý; dùng `hasNext()` khi phù hợp. |
| “`ConcurrentModificationException` có nghĩa iterator hết phần tử.” | Sai. Nó nói về sửa cấu trúc không đúng điều kiện của iterator fail-fast. |
| “Hàng đợi trả `null` luôn nghĩa là rỗng trong mọi implementation.” | Một số `Queue` có thể chứa `null`; xét contract implementation. |
| “`NoSuchElementException` báo dữ liệu hỏng hoặc timeout.” | Không mặc nhiên; các nguyên nhân đó có hợp đồng exception khác. |
| “Catch được exception thì có thể trả thành công.” | Chỉ khi thật sự có fallback hợp lệ; không biến thất bại thành thành công giả. |

## 35. Câu hỏi tự kiểm tra

**1.** `Iterator.hasNext()` trả false. Gọi `next()` sẽ thế nào?  
**Đáp án:** `next()` ném `NoSuchElementException` theo contract của Iterator.

**2.** `NoSuchElementException` là checked hay unchecked?  
**Đáp án:** Unchecked, vì nó kế thừa `RuntimeException`.

**3.** Vì sao vòng lặp `while (it.hasNext()) { it.next(); }` phù hợp hơn dùng exception để dừng?  
**Đáp án:** Điều kiện hết dữ liệu được thể hiện trực tiếp, ít nguy cơ bắt nhầm lỗi từ logic xử lý khác.

**4.** Gọi `Iterator.remove()` trước `next()` trên iterator hỗ trợ xóa có thể ném gì?  
**Đáp án:** `IllegalStateException`, khác với `NoSuchElementException` khi `next()` hết dữ liệu.

**5.** `Queue.remove()` và `Queue.poll()` khác nhau khi queue trống?  
**Đáp án:** `remove()` ném `NoSuchElementException`; `poll()` trả `null`.

**6.** `Queue.element()` và `Queue.peek()` khác nhau khi queue trống?  
**Đáp án:** `element()` ném; `peek()` trả `null`.

**7.** `Deque.pop()` trên deque trống có trả `null` không?  
**Đáp án:** Không. Nó ném `NoSuchElementException`.

**8.** `Optional.empty().get()` trả giá trị gì?  
**Đáp án:** Không trả bình thường; ném `NoSuchElementException`.

**9.** `Optional.empty().orElse("fallback")` trả gì?  
**Đáp án:** `"fallback"`.

**10.** `Optional.empty().orElseThrow(() -> new IllegalStateException(...))` ném gì?  
**Đáp án:** Exception do supplier tạo, trong ví dụ là `IllegalStateException`.

**11.** `OptionalInt.empty().getAsInt()` ném gì?  
**Đáp án:** `NoSuchElementException`.

**12.** `Scanner.nextInt()` gặp token `"abc"` khác gì gặp EOF?  
**Đáp án:** Nếu token tồn tại nhưng không đúng dạng số nguyên thì `InputMismatchException`; nếu không có token thì `NoSuchElementException`.

**13.** Sau `InputMismatchException` do `Scanner.nextInt()`, token sai có tự bị tiêu thụ không?  
**Đáp án:** Không. Có thể đọc hoặc bỏ token ấy bằng cách phù hợp, ví dụ `next()`.

**14.** `Scanner.next()` trên Scanner đã đóng có phải trường hợp “không còn token” thông thường không?  
**Đáp án:** Không. Dùng Scanner đã đóng có thể ném `IllegalStateException`.

**15.** `List.of("A").get(1)` ném `NoSuchElementException` không?  
**Đáp án:** Không. Đây là truy cập chỉ số sai và thường ném `IndexOutOfBoundsException`.

**16.** `Enumeration.nextElement()` khi hết ném gì?  
**Đáp án:** `NoSuchElementException`.

**17.** `StringTokenizer.nextToken()` khi hết token ném gì?  
**Đáp án:** `NoSuchElementException`.

**18.** `Stream.empty().findFirst()` có tự ném `NoSuchElementException` không?  
**Đáp án:** Không. Nó trả `Optional.empty()`; exception phát sinh nếu caller bắt buộc lấy từ Optional rỗng.

**19.** Một thread đã kiểm tra `!queue.isEmpty()`, thread khác rút phần tử cuối trước `queue.remove()`. Điều gì có thể xảy ra?  
**Đáp án:** `remove()` có thể ném `NoSuchElementException`; cần API/đồng bộ thích hợp, ví dụ `poll()` trên queue phù hợp.

**20.** Vì sao không nên dùng `catch (NoSuchElementException)` quanh cả `consume(iterator.next())`?  
**Đáp án:** `consume` có thể tự ném cùng loại exception từ nguồn khác, khiến chương trình hiểu nhầm đó là kết thúc iterator ngoài.

**21.** Khi tự viết `Iterator.next()`, nên làm gì nếu `hasNext() == false`?  
**Đáp án:** Ném `NoSuchElementException` đúng contract, không để một lỗi index ngẫu nhiên thay thế.

**22.** `NoSuchElementException` có đồng nghĩa với `null` không?  
**Đáp án:** Không. Một bên là exception, bên kia là giá trị tham chiếu.

**23.** Một job queue có thể tạm rỗng. Nên chọn `remove()` hay `poll()/take()`?  
**Đáp án:** Tùy chính sách. `poll()` cho phép kết quả rỗng, `take()` trên BlockingQueue chờ phần tử; `remove()` báo exception khi trống.

**24.** Nếu dữ liệu không tìm thấy là một kết quả nghiệp vụ dự kiến, có bắt buộc ném `NoSuchElementException` không?  
**Đáp án:** Không. Có thể trả Optional hoặc kiểu kết quả rõ ràng.

## 36. Checklist thực hành

Khi thấy hoặc muốn ngăn `NoSuchElementException`:

1. **Xác định method thực sự ném:** `next`, `nextLine`, `get`, `remove`, `element`, `pop` hay API khác?
2. **Đọc contract của đúng API:** không suy từ tên collection mà bỏ qua lựa chọn `poll/peek/hasNext`.
3. **Tình huống rỗng có bình thường không?** Nếu bình thường, dùng cách kiểm tra/tín hiệu rỗng.
4. **Có bắt buộc phải có phần tử theo invariant không?** Nếu có, ném đúng loại với thông điệp có ngữ cảnh có thể thích hợp.
5. **Với Iterator, đã dùng `hasNext()` trước `next()` chưa?**
6. **Với Scanner, đã phân biệt token, dòng và định dạng dữ liệu chưa?** Đừng nhầm `InputMismatchException` với EOF.
7. **Với Optional, có thể dùng `orElse`, `orElseGet`, `orElseThrow(supplier)` hoặc `ifPresentOrElse` không?**
8. **Với Queue, có đang dùng `remove/element` khi `poll/peek` phù hợp hơn không?**
9. **Với Deque, có phân biệt `pop` với `poll`, `getFirst` với `peekFirst` không?**
10. **Với List, có nhầm `IndexOutOfBoundsException` với `NoSuchElementException` không?**
11. **Có collection chứa `null` được không?** Đảm bảo tín hiệu `null` không mơ hồ.
12. **Nguồn có thể bị thay đổi đồng thời không?** Kiểm tra race giữa “còn phần tử” và “lấy phần tử”.
13. **Handler có đang bắt phạm vi quá rộng không?** Tránh nuốt một `NoSuchElementException` từ logic khác.
14. **Có vô tình trả thành công giả sau khi bắt lỗi không?**
15. **Có thật sự cần tự tạo class exception riêng không?** Nếu implement Iterator, dùng lớp JDK chuẩn.
16. **Có test đường còn phần tử và đường cạn phần tử chưa?**
17. **Có test trạng thái sau thao tác thất bại không?** Không làm mất phần tử hoặc lệch vị trí iterator.
18. **Trong môi trường đồng thời, đã chọn queue/lock/atomic operation đúng hợp đồng chưa?**
19. **Nếu dùng BlockingQueue, có chính sách timeout và interrupt phù hợp không?**
20. **Log có đủ nguồn và tên thao tác thất bại mà không lộ dữ liệu nhạy cảm không?**

## 37. Kết luận

`NoSuchElementException` là **unchecked exception báo thao tác yêu cầu phần tử nhưng phần tử đó không tồn tại** theo contract của phương thức. Các trường hợp điển hình là `Iterator.next()` khi hết, `Scanner.next()/nextLine()` khi không còn dữ liệu phù hợp, `Optional.get()` khi rỗng, và `Queue.remove()/element()` hoặc `Deque.pop()` khi container trống.

**Đừng biến tình huống rỗng bình thường thành lỗi bằng cách chọn API không phù hợp.** Với Iterator dùng `hasNext()`, với Optional chọn `orElse`/`orElseGet`/`orElseThrow(supplier)` theo hợp đồng, với Queue/Deque cân nhắc `poll/peek`. Nếu phần tử là bắt buộc, exception là cách báo vi phạm có chủ đích và nên đi kèm thông điệp đủ ngữ cảnh khi tự xây API.

Quan trọng nhất: **không đồng nhất “không có phần tử” với “chỉ số sai”, “input sai định dạng”, “scanner đã đóng”, “collection bị sửa đồng thời” hoặc “giá trị null”**. Phân loại đúng nguyên nhân và chọn API đúng hợp đồng giúp chương trình dễ đọc, dễ kiểm thử, không nuốt lỗi và không trả một kết quả thành công giả.
