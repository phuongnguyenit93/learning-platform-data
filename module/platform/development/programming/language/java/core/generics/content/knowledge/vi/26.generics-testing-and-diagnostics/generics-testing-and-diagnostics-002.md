# Bật `javac -Xlint:unchecked`, `-Xlint:rawtypes` và `-Xlint:varargs` để kiểm tra Java Generics

## 1. Mục tiêu học tập

Java Generics giúp compiler phát hiện sớm nhiều sai lệch về kiểu. Tuy nhiên, khi code dùng **raw types**, thực hiện **unchecked casts/conversions** hoặc khai báo **varargs có kiểu phần tử non-reifiable**, compiler không thể chứng minh đầy đủ an toàn kiểu của mọi thao tác. Một số đoạn code vẫn biên dịch được, nhưng phát cảnh báo thay vì lỗi.

Để nhìn rõ những rủi ro này, hãy chủ động bật các nhóm cảnh báo khi biên dịch:

```bash
javac -Xlint:unchecked -Xlint:rawtypes -Xlint:varargs Example.java
```

Hoặc viết gọn ba key trong một option:

```bash
javac -Xlint:unchecked,rawtypes,varargs Example.java
```

Các lệnh trên dùng cho Java compiler `javac` của JDK, không phải lệnh chạy chương trình `java`. Ba nhóm lint có ý nghĩa khác nhau:

| Tùy chọn | Phạm vi quan sát chủ yếu | Ví dụ rủi ro |
|---|---|---|
| `-Xlint:rawtypes` | Sử dụng tên generic type nhưng **không có type arguments** | `List raw = new ArrayList();` |
| `-Xlint:unchecked` | Phép toán liên quan generic mà compiler **không thể kiểm tra đầy đủ** | `raw.add(123)`, gán raw `List` cho `List<String>` |
| `-Xlint:varargs` | Thao tác tiềm ẩn không an toàn với **varargs parameter** có element type non-reifiable, đặc biệt trong method đã gắn `@SafeVarargs` | Làm lộ alias hoặc ghi vào generic varargs array |

**Không nên hiểu ba cảnh báo là ba loại lỗi độc lập tuyệt đối.** Một đoạn code có thể đồng thời phát nhiều cảnh báo, còn generic varargs cũng có thể phát cảnh báo thuộc nhóm `unchecked`. Vị trí và cách diễn đạt diagnostic cụ thể tùy mã nguồn và phiên bản `javac`.

Bài này cung cấp cú pháp lệnh, giải thích cơ chế, ví dụ Java 17 chạy được với stdout chính xác, cách sửa code, cách review ngoại lệ hợp lý và quy trình kiểm soát cảnh báo trong build/CI.

## 2. Bắt đầu bằng `javac` và phân biệt thời điểm compile/run

Giả sử có tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

Các lệnh:

```bash
javac Hello.java
java Hello
```

Stdout của **chương trình chạy**:

```text
Hello
```

Thông báo **compiler** nếu có được sinh ở bước `javac`; chúng không phải những dòng do `System.out.println` của chương trình tạo ra.

Khi thêm các lint flags:

```bash
javac -Xlint:unchecked,rawtypes,varargs Hello.java
java Hello
```

Đoạn `Hello.java` không có raw/unchecked/generic varargs, nên không có lý do để các nhóm lint này cảnh báo nó.

Lưu ý:

- `javac` phân tích và biên dịch **mã nguồn**.
- `java` chạy class đã được tạo.
- Cảnh báo không đồng nghĩa lệnh compile thất bại; mặc định nhiều cảnh báo vẫn cho phép tạo `.class`.
- Một lỗi biên dịch (*error*) khác với warning.
- Một warning báo hiệu **vấn đề có khả năng gây rủi ro**, không có nghĩa chương trình chắc chắn sẽ ném exception ngay khi chạy.

## 3. Cú pháp chính xác của các tùy chọn

Dạng tách rời:

```bash
javac -Xlint:unchecked -Xlint:rawtypes -Xlint:varargs Main.java
```

Dạng kết hợp:

```bash
javac -Xlint:unchecked,rawtypes,varargs Main.java
```

Dạng bật tất cả các nhóm lint mà phiên bản compiler hỗ trợ:

```bash
javac -Xlint:all Main.java
```

Dạng xem thêm các tùy chọn compiler có sẵn:

```bash
javac --help-extra
```

Các ví dụ dùng `javac` trong JDK 17. Danh sách các lint keys và chi tiết diagnostic có thể thay đổi giữa các phiên bản JDK; khi thiết lập CI, cần cố định JDK hoặc chủ động kiểm tra output trên JDK mục tiêu.

`-Xlint:all` rộng hơn ba nhóm đang học, nên có thể cảnh báo thêm về deprecation, serial, cast, fallthrough hoặc những chủ đề khác. Khi mới rà soát một module Generics, bật đúng ba nhóm sẽ giúp tập trung.

Bạn có thể thêm `-Xdiags:verbose` khi cần diagnostic chi tiết:

```bash
javac -Xdiags:verbose -Xlint:unchecked,rawtypes,varargs Main.java
```

Tùy chọn này không tự sửa chương trình; nó giúp trình bày thông tin lỗi/cảnh báo có thể hữu ích khi điều tra.

## 4. `rawtypes`: raw type là gì?

Raw type là cách dùng một generic class/interface **mà không ghi type arguments**.

Ví dụ:

```java
List raw = new ArrayList();
```

Nếu có import `java.util.List` và `java.util.ArrayList`, dòng trên thường hợp lệ vì Java hỗ trợ raw types để tương thích với mã trước Generics.

Dạng typed tương ứng:

```java
List<String> typed = new ArrayList<>();
```

Điểm khác:

- `List<String>` thông báo cho compiler rằng phần tử cần là `String`.
- `List` raw bỏ thông tin element type trong nhiều phép kiểm tra.
- `new ArrayList()` là raw class instance creation.
- `new ArrayList<>()` dùng **diamond inference**, không phải raw constructor.
- Raw `List` không đồng nghĩa `List<Object>` hoặc `List<?>`.

Bật `-Xlint:rawtypes` để compiler chỉ ra những nơi ta sử dụng tên generic type dưới dạng raw.

**Cảnh báo `rawtypes` không bảo đảm có exception runtime.** Nó nhắc rằng ta đã bước ra khỏi hợp đồng generic rõ ràng và dễ mất kiểm tra kiểu ở những thao tác tiếp theo.

## 5. Ví dụ Java 17: raw `List` gây heap pollution

Tạo tệp **`RawTypesWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypesWarningDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("safe");

        List raw = words;
        raw.add(100);

        System.out.println(words.size());

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch có bật lint:

```bash
javac -Xlint:unchecked,rawtypes,varargs RawTypesWarningDemo.java
java RawTypesWarningDemo
```

Stdout của **chương trình**:

```text
2
ClassCastException
```

Điều xảy ra:

1. `words` được khai báo `List<String>`.
2. `List raw = words` tạo một tham chiếu raw đến **cùng object list**, không tạo bản sao.
3. `raw.add(100)` thực hiện lời gọi `add` qua raw type; ở runtime `ArrayList` nhận `Integer`.
4. `words.size()` vẫn trả `2`, vì việc đếm phần tử không yêu cầu phần tử thứ hai là `String`.
5. `words.get(1)` được dùng ở vị trí `String`; object thực là `Integer`, nên có `ClassCastException`.

Về cảnh báo:

- Dòng `List raw = words` là một raw type usage thuộc phạm vi `rawtypes`.
- Lời gọi `raw.add(100)` thường phát **unchecked call warning** từ `unchecked`.
- Cả hai có thể được nhìn thấy khi bật hai nhóm lint; `varargs` không phải vấn đề của ví dụ này.

**Heap pollution** là trạng thái khi một biến có parameterized type được sử dụng như chứa dữ liệu không thỏa generic contract. Raw operations là một trong các đường dẫn tạo trạng thái ấy.

## 6. Sửa raw type theo mục đích thật của API

Không có một phép thay raw duy nhất đúng cho mọi chương trình.

Nếu list chỉ được dùng để lưu chuỗi:

```java
List<String> words = new ArrayList<>();
words.add("safe");
// words.add(100); // Cố ý sai: compiler từ chối.
```

Nếu thật sự muốn chứa nhiều loại object:

```java
List<Object> mixed = new ArrayList<>();
mixed.add("safe");
mixed.add(100);
```

Nếu code chỉ cần **đọc từ một list với element type chưa biết**:

```java
static void showAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Method minh họa cần đặt trong class và import `List`.

Phân biệt quan trọng:

| Ý định | Dạng đề xuất | Đặc điểm |
|---|---|---|
| Chỉ lưu chuỗi | `List<String>` | Compiler từ chối thêm số |
| Lưu nhiều object type | `List<Object>` | Element type thực sự là `Object` |
| Chấp nhận list bất kỳ, chủ yếu đọc | `List<?>` | Element type chưa biết; hạn chế thêm tùy ý |
| Tương thích API raw không thể đổi ngay | Khoanh vùng raw/unchecked boundary | Kiểm tra dữ liệu và dần thay thế |

Chuyển raw `List` thành `List<Object>` không phải lúc nào cũng hợp lệ: `List<String>` **không** là subtype của `List<Object>` vì generic Java invariant. `List<?>` thường là lựa chọn tốt hơn khi API chỉ cần đọc.

## 7. `unchecked`: compiler không chứng minh được an toàn kiểu

Cảnh báo nhóm `unchecked` xuất hiện khi một phép toán được phép thực hiện vì tính tương thích ngược, nhưng **độ an toàn generic không thể được xác minh hoàn toàn lúc biên dịch**.

Các ví dụ thường gặp:

```java
List raw = new ArrayList();
List<String> typed = raw;
raw.add("A");
```

Đây là đoạn minh họa, cần import `List` và `ArrayList`.

Những trường hợp đáng chú ý:

- **Unchecked conversion:** chuyển từ raw `List` thành `List<String>`.
- **Unchecked method invocation:** gọi generic method thông qua raw receiver.
- **Unchecked cast:** ép một object/raw container thành parameterized type mà runtime không có đủ thông tin generic.
- **Generic varargs:** ở một số khai báo/lời gọi varargs có component non-reifiable, compiler có thể phát cảnh báo thuộc `unchecked`.

`-Xlint:unchecked` giúp hiện rõ những đoạn mà type erasure hoặc raw API làm mất bằng chứng kiểu.

Không nên hiểu mọi cảnh báo `unchecked` đều là bug đang chạy. Một số ranh giới interoperating với legacy API là cần thiết; nhiệm vụ của người viết là **chứng minh và khoanh vùng** chúng, thay vì giấu đi.

## 8. Ví dụ: unchecked conversion từ legacy API

Tạo tệp **`UncheckedConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class UncheckedConversionDemo {

    static List legacy() {
        List result = new ArrayList();
        result.add("hello");
        return result;
    }

    public static void main(String[] args) {
        List<String> names = legacy();

        System.out.println(names.size());
        System.out.println(names.get(0).toUpperCase());
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:unchecked,rawtypes,varargs UncheckedConversionDemo.java
java UncheckedConversionDemo
```

Stdout:

```text
1
HELLO
```

Compiler có thể cảnh báo:

- Raw return type `List` trong chữ ký `legacy`.
- Raw local `List` và raw `new ArrayList()`.
- Unchecked invocation ở `result.add("hello")`.
- Unchecked conversion khi gán kết quả `legacy()` cho `List<String>`.

Dữ liệu demo tình cờ toàn chuỗi nên chương trình chạy tốt, nhưng chữ ký `legacy()` **không cam kết** rằng một caller trong tương lai sẽ chỉ nhận chuỗi. Nếu sửa `legacy()` để thêm số, người gọi có thể nhận `ClassCastException` sau này.

Bài học: **chạy được trên bộ dữ liệu hiện tại không chứng minh một unchecked conversion an toàn.**

## 9. Sửa unchecked conversion bằng việc thay đổi API

Khi có quyền sửa legacy API, giải pháp tốt nhất thường là định kiểu ngay ở nguồn:

```java
static List<String> names() {
    List<String> result = new ArrayList<>();
    result.add("hello");
    return result;
}
```

Method này cần đặt trong class, import `List` và `ArrayList`.

Caller:

```java
List<String> values = names();
```

không cần unchecked conversion. Compiler có thể chặn việc thêm một `Integer` vào `result`.

Nếu không thể sửa API vì thuộc thư viện legacy, hãy tạo một **adapter** nhận `List<?>`, kiểm tra phần tử, rồi tạo một list typed mới:

```java
static <T> List<T> checkedCopy(
        List<?> source,
        Class<T> elementType) {

    List<T> copy = new ArrayList<>();

    for (Object element : source) {
        copy.add(elementType.cast(element));
    }

    return copy;
}
```

Adapter này kiểm tra class runtime của từng phần tử. Khi `elementType = String.class`, một `Integer` sẽ bị từ chối ngay lúc copy.

`Class<T>` chỉ kiểm tra **class cấp phần tử** được truyền; nếu phần tử là `List<String>` hoặc kiểu tham số hóa sâu hơn, cần validator có cấu trúc phù hợp.

## 10. Ví dụ đầy đủ: adapter kiểm tra dữ liệu thay vì unchecked cast

Tệp **`CheckedAdapterDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedAdapterDemo {

    static <T> List<T> checkedCopy(
            List<?> source, Class<T> elementType) {

        List<T> result = new ArrayList<>();
        for (Object value : source) {
            result.add(elementType.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> accepted =
                checkedCopy(List.of("A", "B"), String.class);

        System.out.println(accepted);

        try {
            checkedCopy(List.of("A", 7), String.class);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -Xlint:unchecked,rawtypes,varargs CheckedAdapterDemo.java
java CheckedAdapterDemo
```

Stdout:

```text
[A, B]
ClassCastException
```

Kỹ thuật này tránh việc giả vờ rằng một raw list *đã chắc chắn* là `List<String>`. Nó kiểm tra dữ liệu và **sao chép** qua ranh giới.

Hai giới hạn:

- `List.copyOf` từ chối phần tử `null`; cần chính sách khác nếu nguồn cho phép `null`.
- Bản sao list là **shallow copy**: đối tượng phần tử mutable vẫn có thể bị sửa từ những tham chiếu khác.

## 11. Unchecked cast: một warning có thể báo lỗi sẽ đến muộn

Đặt trong method có import `java.util.List`:

```java
Object input = List.of("Java", 42);
List<String> words = (List<String>) input; // unchecked cast
System.out.println(words.size());         // 2
// String second = words.get(1);         // Khi chạy sẽ ném ClassCastException.
```

Với `javac -Xlint:unchecked,rawtypes,varargs`, dòng cast có thể phát **unchecked warning**; nếu không bật `-Werror`, chương trình vẫn được phép biên dịch. JVM chỉ kiểm tra `input` có phải `List` ở mức runtime class, không xác thực type argument `String`. Do đó `size()` đọc được, nhưng khi giá trị `Integer` bị sử dụng như `String`, một cast cụ thể mới có thể thất bại.

Đừng xem một chương trình chưa ném lỗi là bằng chứng warning vô hại. Nếu dữ liệu chưa tin cậy, nhận `List<?>`, kiểm tra từng phần tử rồi tạo bản sao có kiểu. Bài kiểm thử heap pollution phân tích chi tiết các thời điểm ghi sai, đọc như `Object`, đọc typed và điểm `checkcast` bằng một bộ test độc lập; tại đây trọng tâm là **cảnh báo `unchecked` xuất hiện lúc biên dịch và không được JVM tự biến thành lỗi ngay lập tức**.


## 12. Vì sao Generics và unchecked casts liên hệ với type erasure?

Java thực thi Generics thông thường bằng **type erasure**. Ví dụ, `List<String>` và `List<Integer>` không sinh ra hai runtime class riêng của `List`.

Hệ quả:

- Compiler kiểm tra `List<String>` ở compile time.
- Runtime object list không tự được gắn một class token đặc biệt cho `<String>`.
- JVM có thể kiểm tra `object instanceof List<?>` hoặc cast object thành raw `List`, nhưng không xác minh `<String>` chỉ từ class runtime.
- Nếu có unchecked cast hoặc raw operations, trạng thái chứa dữ liệu sai hợp đồng vẫn có thể xuất hiện.

Cảnh báo không chỉ là vấn đề “code style”; chúng chỉ tới những **ranh giới mà compile-time guarantees yếu đi**.

Khi một unchecked warning thực sự có lý do hợp lệ, hãy nêu rõ invariant được bảo đảm ở đâu. Nếu không thể chứng minh invariant, nên thay bằng một checked adapter hoặc redesign API.

## 13. `varargs`: varargs là mảng ở mức phương thức

Với:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

Đây là method minh họa cần đặt trong class.

`String...` có dạng **variable arity parameter**, nhưng trong thân phương thức `values` là một `String[]`.

Khi phần tử varargs là generic type **non-reifiable**, như:

```java
static void display(List<String>... groups) {
    // ...
}
```

runtime không có class component chuyên biệt `List<String>`. Với lời gọi dạng variable arity, compiler có thể tạo một array có runtime component là raw `List`; từ đây xuất hiện nguy cơ *heap pollution* nếu code làm lộ hoặc ghi array không an toàn.

Cần phân biệt:

- `-Xlint:unchecked`: có thể báo generic varargs có parameterized element type không reifiable tại khai báo/lời gọi.
- `-Xlint:varargs`: tập trung những thao tác **potentially unsafe varargs** trong các ngữ cảnh được compiler nhận diện, đặc biệt ở phần thân khai báo `@SafeVarargs`.
- `@SafeVarargs`: một cam kết của người viết rằng implementation dùng varargs an toàn, **không** làm JVM kiểm tra được generic argument.

Một số cảnh báo generic varargs liên quan đến cả hai nhóm; không nên chỉ bật `varargs` mà tắt `unchecked`.

## 14. Ví dụ Java 17: heap pollution qua alias `Object[]`

Tạo tệp **`UnsafeVarargsDemo.java`**:

```java
import java.util.List;

public class UnsafeVarargsDemo {

    static void unsafe(List<String>... groups) {
        Object[] alias = groups;

        alias[0] = List.of(99);

        System.out.println(groups[0].size());

        try {
            String text = groups[0].get(0);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }

    public static void main(String[] args) {
        unsafe(List.of("safe"));
    }
}
```

Biên dịch/chạy:

```bash
javac -Xlint:unchecked,rawtypes,varargs UnsafeVarargsDemo.java
java UnsafeVarargsDemo
```

Stdout của chương trình:

```text
1
ClassCastException
```

Phân tích:

1. `groups` được nhìn là `List<String>[]`.
2. `Object[] alias = groups` tạo một tham chiếu kiểu cha đến cùng object array.
3. `alias[0] = List.of(99)` chèn một `List<Integer>`, nhưng runtime component type chỉ cần object thuộc raw `List`, nên **không** chặn phép ghi này.
4. `groups[0].size()` không lấy dữ liệu dưới dạng String, nên vẫn chạy.
5. Khi đọc phần tử và gán cho `String`, runtime cast gặp `Integer`, gây `ClassCastException`.

Compiler có thể cảnh báo tại **khai báo method** và **lời gọi generic varargs**. Không nên chép diagnostic compiler thành “stdout cố định”: số lượng cảnh báo, cột chỉ vị trí và cách diễn đạt phụ thuộc phiên bản JDK.

Ví dụ này cố ý không an toàn để học; không dùng như implementation production.

## 15. `@SafeVarargs`: khi nào nên dùng?

Nếu một generic varargs method chỉ duyệt input và sao chép dữ liệu vào collection mới, không thay slot của array, không để array alias thoát ra nơi có thể sửa, có thể cân nhắc `@SafeVarargs`.

Ví dụ:

```java
@SafeVarargs
static <T> List<T> merge(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

Đây là một method minh họa; cần đặt trong class và import `List`, `ArrayList`.

Trong Java 17, annotation `@SafeVarargs` được phép ở các khai báo varargs thích hợp như:

- `static` methods;
- `final` instance methods;
- `private` instance methods;
- constructors.

Nó không được đặt tùy ý lên một public instance method có thể override.

**Quan trọng:** Annotation là tuyên bố của người viết về an toàn implementation; compiler không chứng minh toàn bộ đường dữ liệu là an toàn chỉ vì thấy annotation.

Không gắn `@SafeVarargs` lên method cố tình dùng `Object[]` alias để ghi danh sách sai generic argument, hoặc chuyển array cho helper có khả năng ghi sai kiểu.

## 16. Chương trình `@SafeVarargs` hợp lệ và dễ review

Tạo tệp **`SafeVarargsMergeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsMergeDemo {

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(group);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> names =
                merge(List.of("An"), List.of("Binh", "Chi"));

        List<Number> numbers =
                merge(List.of(1, 2), List.of(3.5));

        System.out.println(names);
        System.out.println(numbers);
    }
}
```

Lệnh:

```bash
javac -Xlint:unchecked,rawtypes,varargs SafeVarargsMergeDemo.java
java SafeVarargsMergeDemo
```

Stdout:

```text
[An, Binh, Chi]
[1, 2, 3.5]
```

Ở đây:

- `groups` chỉ được đọc.
- Không thay array slot bằng `List` có generic argument khác.
- Không trả về `groups` hoặc đưa reference của nó ra bên ngoài.
- Tạo `List<T>` mới, rồi trả một list unmodifiable.

`List.copyOf` từ chối `null` nếu dữ liệu chứa null. Trong ví dụ, các input không có null.

Nếu method chuyển array sang một helper, phải kiểm toán cả helper trước khi khẳng định an toàn. Không chỉ dựa vào việc “trong method này không thấy toán tử `=` trên array”.

## 17. Vì sao `-Xlint:varargs` vẫn có giá trị khi dùng `@SafeVarargs`?

Một hiểu nhầm phổ biến là: **gắn `@SafeVarargs` thì tất cả cảnh báo đều biến mất, nên không cần review nữa**.

Thực tế:

- Annotation có thể suppress một số unchecked warnings ở khai báo và lời gọi generic varargs, vì người viết cam kết implementation an toàn.
- Compiler vẫn có thể đưa ra **cảnh báo ở phần thân method** về những thao tác potentially unsafe trên non-reifiable varargs array khi bật `-Xlint:varargs`.
- Ngay cả khi không có warning ở một đoạn cụ thể, annotation cũng không biến thao tác heap pollution thành hợp lệ về mặt an toàn dữ liệu.

Ví dụ cố ý nguy hiểm:

```java
// Đoạn học thuật: KHÔNG áp dụng @SafeVarargs như mẫu này.
@SafeVarargs
static void unsafeAnnotated(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(123);
}
```

Vì method có `static`, annotation có thể được đặt theo quy tắc vị trí nhưng **cam kết là sai**. Biên dịch với `-Xlint:varargs` giúp lộ các thao tác rủi ro mà compiler có thể nhận diện; không có nghĩa compiler phát hiện được mọi đường alias và mọi helper.

Cách sửa đúng là **loại bỏ thao tác nguy hiểm** hoặc thiết kế lại API, không chỉ chuyển sang `@SuppressWarnings`.

## 18. Chọn `List<T>`/`Collection<T>` thay cho generic varargs khi phù hợp

Nếu mục tiêu là xử lý một nhóm danh sách đã tồn tại, API nhận collection có thể đơn giản hơn:

```java
static <T> List<T> mergeGroups(
        Collection<? extends List<? extends T>> groups) {

    List<T> result = new ArrayList<>();

    for (List<? extends T> group : groups) {
        result.addAll(group);
    }

    return List.copyOf(result);
}
```

Đây là method minh họa; cần import `Collection`, `List`, `ArrayList` và đặt trong class.

Caller dùng:

```java
List<String> merged =
        mergeGroups(List.of(List.of("A"), List.of("B")));
```

Ưu điểm:

- Không cần varargs array có component non-reifiable tại API boundary.
- Generic type information được compiler theo dõi qua `Collection`/`List` trong mã nguồn.
- Method có thể đọc/copy dữ liệu mà không phải giữ một mảng varargs.
- API rõ ràng khi caller đã có collection chứa các nhóm.

Đổi lại, cú pháp gọi có thể dài hơn `merge(group1, group2)`. Nếu varargs thực sự giúp API dễ dùng và implementation đã được chứng minh an toàn, `@SafeVarargs` là lựa chọn hợp lý.

## 19. So sánh ba nhóm lint bằng một ví dụ kết hợp

Tạo tệp **`CombinedWarningsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CombinedWarningsDemo {

    static void acceptLists(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println(group.size());
        }
    }

    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("A");

        List<String> typed = raw;

        acceptLists(typed);
    }
}
```

Biên dịch/chạy:

```bash
javac -Xlint:unchecked,rawtypes,varargs CombinedWarningsDemo.java
java CombinedWarningsDemo
```

Stdout:

```text
1
```

Chỗ nào thuộc nhóm nào?

| Dòng/kiểu thao tác | Nhóm thường liên quan | Lý do |
|---|---|---|
| `List raw` | `rawtypes` | Tên generic type không có argument |
| `new ArrayList()` | `rawtypes` | Dùng raw generic class ở biểu thức tạo |
| `raw.add("A")` | `unchecked` | Invocation qua raw receiver |
| `List<String> typed = raw` | `unchecked` | Unchecked conversion |
| `List<String>... groups` | Thường `unchecked` | Non-reifiable varargs element type |
| `acceptLists(typed)` | Có thể `unchecked` | Variable-arity invocation có generic array component |
| Thân `acceptLists` chỉ đọc | Không nhất thiết cảnh báo `varargs` | Không có unsafe alias/write được chỉ ra |

Không nên tuyên bố `-Xlint:varargs` **chắc chắn** phải phát cảnh báo trong mọi phương thức có dấu `...`. Nó phụ thuộc thao tác, annotation, type reifiability và các luật của compiler.

## 20. Đọc và phân loại một compiler warning

Diagnostics của `javac` thường cho biết:

- File và vị trí line/column liên quan.
- Key hoặc nội dung mô tả loại warning.
- Operation bị coi là raw/unchecked/unsafe.
- Đôi khi thêm thông tin **required/found** hoặc compiler note.

Một ví dụ hình thức thông báo có thể mang dạng:

```text
Example.java:12: warning: [unchecked] unchecked call to ...
```

Đây là **mẫu hình minh họa**, không phải output bắt buộc của một chương trình cụ thể.

Quy trình đọc:

1. Nhìn **source line** trước: thực sự đang gọi method, gán biến, cast hay khai báo varargs?
2. Xác định **nguồn mất generic information**: raw receiver, raw return type, reflection, varargs array.
3. Xác định **hợp đồng cần giữ**: `List<String>` chỉ chứa String, hay chỉ cần `List<?>`?
4. Kiểm tra **nơi dữ liệu vào**: ai có quyền thêm phần tử sai kiểu?
5. Tìm cách làm compiler chứng minh được an toàn: đổi chữ ký typed, wildcard, adapter, factory hoặc redesign.
6. Chỉ dùng suppression khi có invariant rõ và có test.

Cảnh báo tại nơi đọc một giá trị chưa chắc là gốc vấn đề. Có thể bug xảy ra trước đó ở nơi raw `add` chèn dữ liệu sai kiểu.

## 21. `-Werror`: biến warnings thành lỗi build

Đối với codebase đã sạch warning hoặc đang quản lý warning như nợ kỹ thuật, có thể dùng:

```bash
javac -Xlint:unchecked,rawtypes,varargs -Werror Main.java
```

`-Werror` yêu cầu compiler coi việc có warnings là tình huống khiến compilation không thành công. Nó **không** thay đổi ý nghĩa của Generics và không biến các thao tác raw/unchecked thành phép kiểm tra runtime mới.

Một quy trình hợp lý:

1. Bật lint trước để xem cảnh báo hiện có.
2. Phân loại và sửa các trường hợp thực sự nguy hiểm.
3. Ghi lại những ranh giới legacy chưa sửa được.
4. Khoanh vùng suppression có lý do.
5. Khi đã kiểm soát cảnh báo, thêm `-Werror` để ngăn warning mới lọt vào.

Nếu dự án đang có quá nhiều warnings, bật `-Werror` đột ngột có thể làm CI thất bại hàng loạt mà chưa giúp sửa thiết kế. Nên dùng giai đoạn baseline/triage hoặc áp dụng trên module mới trước khi siết toàn hệ thống.

## 22. Ví dụ về quy trình compile và không nhầm stdout

Với `RawTypesWarningDemo.java` đã tạo ở phần trước:

```bash
javac -Xlint:rawtypes RawTypesWarningDemo.java
```

Compiler tập trung vào raw usages. Với:

```bash
javac -Xlint:unchecked RawTypesWarningDemo.java
```

Compiler tập trung vào unchecked operations. Với:

```bash
javac -Xlint:varargs RawTypesWarningDemo.java
```

Không có generic varargs trong file demo, nên nhóm `varargs` không phải trọng tâm.

Với:

```bash
javac -Xlint:unchecked,rawtypes,varargs RawTypesWarningDemo.java
```

ta nhìn tập cảnh báo rộng hơn. Việc gom các nhóm lint **không thay đổi logic chương trình**, nên nếu biên dịch thành công, bước:

```bash
java RawTypesWarningDemo
```

vẫn in:

```text
2
ClassCastException
```

Nếu thêm `-Werror`, bước `javac` có thể thất bại vì warnings, nghĩa là không nên tự chạy một `.class` cũ và tưởng đó là kết quả vừa compile. Hãy phân biệt **compiler build result** với **program run result**.

## 23. `@SuppressWarnings("unchecked")`: chỉ dùng có chứng minh

Có những điểm giao tiếp với legacy API hoặc generic array reflection cần unchecked cast mà compiler không thể chứng minh. Khi đó có thể cân nhắc `@SuppressWarnings("unchecked")` ở phạm vi **nhỏ nhất có thể**.

Ví dụ một helper dựa trên class token:

```java
@SuppressWarnings("unchecked")
static <T> T[] newArray(Class<T> type, int length) {
    return (T[]) java.lang.reflect.Array.newInstance(type, length);
}
```

Đây là method minh họa cần đặt trong class. Khi caller truyền một **reference class token** tương ứng với `T`, array được tạo có runtime component type bằng token ấy, nên invariant hỗ trợ cho cast.

Nhưng cần cân nhắc các trường hợp token primitive, `void.class`, null, hoặc API dùng raw/unchecked để đưa token không đúng. Một thư viện production nên xác định điều kiện đầu vào thay vì coi annotation là bằng chứng tuyệt đối.

Ngược lại, đoạn sau **không có chứng minh an toàn**:

```java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) someUnknownObject;
```

Nếu `someUnknownObject` chứa `List<Integer>`, suppression chỉ giấu warning; lỗi runtime vẫn có thể xảy ra.

Nguyên tắc: **sửa tận gốc nếu có thể; nếu bất khả kháng, khoanh vùng và viết chú thích nêu invariant cùng kiểm thử.**

## 24. `@SuppressWarnings("rawtypes")` và `@SafeVarargs` không thay nhau

Ba công cụ có phạm vi khác nhau:

| Công cụ | Vai trò | Không làm được |
|---|---|---|
| `@SuppressWarnings("rawtypes")` | Suppress một số warnings do raw type usages | Không biến raw `List` thành `List<String>` |
| `@SuppressWarnings("unchecked")` | Suppress warnings do unchecked operations | Không tăng runtime type safety |
| `@SafeVarargs` | Cam kết varargs implementation an toàn tại khai báo hợp lệ | Không tự chứng minh tránh heap pollution |
| `-Xlint:varargs` | Yêu cầu compiler nêu warnings liên quan unsafe varargs operations được nhận diện | Không phải static analyzer toàn năng |
| `-Werror` | Khiến warnings ảnh hưởng kết quả build | Không sửa underlying code |

Có thể một method vừa dùng raw type vừa có unchecked call. Tắt `rawtypes` không nhất thiết tắt `unchecked` và ngược lại.

**Đừng gắn annotation lên toàn bộ class** chỉ để “sạch log”, trừ khi có một rationale rất cụ thể. Nếu cảnh báo mới phát sinh ở đoạn khác trong class, suppression rộng sẽ làm nó khó được phát hiện.

## 25. Ví dụ suppression có phạm vi hẹp: legacy boundary

Giả sử legacy API trả raw `List` và hợp đồng ngoài Java type system bảo đảm nó chỉ chứa `String`. Nếu không thể đổi signature, adapter vẫn nên kiểm tra dữ liệu:

```java
static List<String> legacyStrings(List<?> input) {
    List<String> copy = new ArrayList<>();
    for (Object item : input) {
        copy.add(String.class.cast(item));
    }
    return List.copyOf(copy);
}
```

Không cần unchecked cast cho thiết kế trên. Compiler có thể kiểm tra các loại object được đưa vào bản sao.

Nếu một API thực sự trả một typed object từ một unchecked path mà bạn buộc phải cast, suppression nên đặt sát **biểu thức duy nhất cần cast**, thay vì trên cả file. Ví dụ:

```java
@SuppressWarnings("unchecked")
List<String> result = (List<String>) rawValue;
```

Nhưng không coi đây là code mẫu an toàn cho input chưa kiểm tra; `rawValue` phải đã có **invariant độc lập** bảo đảm element type là `String`, và nên ghi invariant ấy trong comment/tài liệu của wrapper.

Trong mọi trường hợp, lint warnings là công cụ giúp bạn quyết định **có thể tin dữ liệu tới đâu**, không phải bài tập để làm compiler im lặng bằng mọi giá.

## 26. Generic varargs: review các đường alias và escape

Một method có thể không trực tiếp viết:

```java
values[0] = ...;
```

nhưng vẫn nguy hiểm nếu nó chuyển mảng varargs cho code khác có thể ghi sai kiểu hoặc lưu reference ấy.

Checklist review varargs array:

- Có phép `Object[] alias = values` không?
- Có `Arrays.fill(values, ...)`, `System.arraycopy` hoặc helper nào sửa slot không?
- Có lưu `values` vào field, static state hoặc callback không?
- Có trả lại nguyên array hoặc một view backed by array không?
- Có helper nhận raw `Object[]`/raw array để sửa phần tử không?
- Có thao tác cast tới array type khác rồi ghi không?
- Có annotation `@SafeVarargs` không? Nếu có, hợp đồng an toàn đã được chứng minh chưa?

Một method an toàn thường **chỉ đọc varargs parameter** và sao chép nội dung cần giữ sang cấu trúc khác, không đưa alias array ra nơi không kiểm soát được.

Không đánh đồng **sửa object đang nằm trong slot** với **thay slot của mảng**. Cả hai có thể có rủi ro tùy loại object, nhưng heap pollution do generic array alias chủ yếu nói về việc viết một giá trị sai generic argument vào array slot.

## 27. Test chạy được để phát hiện hệ quả của unchecked path

Tạo tệp **`LintRegressionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LintRegressionDemo {

    static List<String> safeStrings(List<?> source) {
        List<String> copy = new ArrayList<>();

        for (Object value : source) {
            copy.add(String.class.cast(value));
        }

        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        System.out.println(
                safeStrings(List.of("A", "B")));

        try {
            safeStrings(List.of("A", 1));
        } catch (ClassCastException ex) {
            System.out.println("Rejected mixed types");
        }

        System.out.println(
                safeStrings(List.of()).isEmpty());
    }
}
```

Lệnh:

```bash
javac -Xlint:unchecked,rawtypes,varargs LintRegressionDemo.java
java LintRegressionDemo
```

Stdout:

```text
[A, B]
Rejected mixed types
true
```

Ở đây adapter có kiểm tra từng phần tử và không cần unchecked cast. Bài test gồm đường dữ liệu đúng, đường dữ liệu sai và list rỗng.

Lint giúp phát hiện các ranh giới không được compiler chứng minh; tests cần kiểm tra **hành vi runtime** với dữ liệu hợp lệ và dữ liệu phá invariant. Hai cách kiểm tra hỗ trợ nhau, không thay thế nhau.

## 28. Hướng dẫn dùng compiler warnings trong dự án nhiều module

Đối với một codebase lớn:

1. **Chuẩn hóa JDK/compiler version** để diagnostic ổn định giữa máy phát triển và CI.
2. **Bật cả ba nhóm** khi compile module xử lý Generics.
3. **Ghi nhận baseline** warnings hiện tại nếu đang có nhiều nợ kỹ thuật.
4. **Ưu tiên lỗi dữ liệu**: raw write gây heap pollution, unchecked conversion từ input không tin cậy, generic varargs làm lộ array.
5. **Tách warnings mới và warnings cũ** nếu cần lộ trình migrate.
6. **Đưa typed adapters** vào ranh giới legacy thay vì lan truyền raw types qua toàn hệ thống.
7. **Chỉ cho phép suppression có rationale**; review từng suppression như một ngoại lệ có kiểm chứng.
8. **Cân nhắc `-Werror` cho module sạch** để ngăn regression.
9. **Giữ test runtime** cho dữ liệu trộn, null, boundary, exceptions.
10. **Theo dõi thay đổi dependencies**: một thư viện cập nhật signature có thể thay lượng raw/unchecked warnings trong caller.

`javac` compile những `.java` nào còn phụ thuộc cách bạn gọi build và classpath/modulepath. Nếu chỉ compile một file demo thì nó không tự rà soát toàn bộ repository; trong dự án thực, phải cấu hình lint flags vào công cụ build đang dùng.

## 29. Cấu hình Maven/Gradle ở mức khái niệm

Trong Maven, plugin chịu trách nhiệm biên dịch Java là **Maven Compiler Plugin**. Các flags có thể được truyền dưới dạng compiler arguments hoặc cấu hình lint tương ứng của phiên bản plugin đang sử dụng.

Trong Gradle, tác vụ kiểu `JavaCompile` có thể nhận các compiler arguments:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll([
        '-Xlint:unchecked',
        '-Xlint:rawtypes',
        '-Xlint:varargs'
    ])
}
```

Đây là đoạn **Gradle Groovy DSL minh họa**, cần đặt trong build script và áp dụng ở dự án dùng Java plugin thích hợp. Không phải một chương trình Java độc lập.

Đối với build scripts Kotlin DSL, cú pháp cấu hình khác; không sao chép nguyên Groovy DSL rồi mong nó chạy trong `.gradle.kts`.

Nếu Maven/Gradle đã quản lý một JDK toolchain, nên thống nhất toolchain với JDK chạy lint local. Muốn triển khai `-Werror`, trước tiên hãy bảo đảm warnings được hiểu và xử lý; không nên suppress đại trà chỉ để build xanh.

Không cần đoán một phiên bản plugin Maven hay Gradle cụ thể nếu dự án đã có build conventions. Chỉ cần yêu cầu quan trọng là flags thực sự đến được **`javac`** trong quá trình compile.

## 30. Khi nào warning có thể bị bỏ sót dù flags đã bật?

Bật `-Xlint` không bảo đảm tìm mọi lỗi Generic.

Ví dụ:

- Dữ liệu sai có thể đến từ runtime reflection hoặc deserialization và chưa gặp cast.
- Một lời gọi qua API typed nhưng internal implementation có bug có thể chưa kích hoạt warning ở caller.
- `@SafeVarargs` tuyên bố an toàn sai nhưng compiler không nhận ra toàn bộ đường alias qua helper.
- Generic element type bị erasure; JVM không tự validate nội dung mọi `List<String>`.
- `@SuppressWarnings` có thể ẩn diagnostic ở đoạn code rủi ro.
- Nếu một file/module không được compile trong lệnh build đó, compiler không thể báo lỗi từ nó.
- Warnings từ thư viện đã biên dịch trước không được tái tạo chỉ bằng compile caller nếu không có source của thư viện.

Vì vậy quy trình chất lượng cần:

**Static type checking + lint warnings + code review + tests runtime + hợp đồng API rõ ràng.**

Các công cụ phân tích bổ sung có thể tìm thêm loại bug khác, nhưng không nên xem một danh sách flags là chứng minh formal correctness.

## 31. Những hiểu nhầm thường gặp

**Hiểu nhầm 1 — `-Xlint:rawtypes` làm raw type không biên dịch.** Không. Nó phát cảnh báo; để warnings làm build fail, thêm `-Werror` hoặc chính sách build phù hợp.

**Hiểu nhầm 2 — `-Xlint:unchecked` và `-Xlint:rawtypes` giống nhau.** Không. Một nhóm chú ý raw usage, nhóm kia chú ý các phép toán không kiểm tra đầy đủ. Một đoạn code có thể thuộc cả hai.

**Hiểu nhầm 3 — `-Xlint:varargs` sẽ cảnh báo mọi method có `...`.** Không. Những varargs với reifiable element type như `String...` thường không có rủi ro generic heap pollution đang xét.

**Hiểu nhầm 4 — Compiler warning là stdout của chương trình.** Không. Diagnostics xuất hiện lúc compile; stdout minh họa là từ `java ClassName`.

**Hiểu nhầm 5 — Dùng `@SuppressWarnings("unchecked")` sửa lỗi.** Không. Nó chỉ tắt warning, không thêm runtime generic validation.

**Hiểu nhầm 6 — `@SafeVarargs` làm JVM biết `List<String>`.** Không. Erasure vẫn áp dụng và mảng có runtime component raw `List`.

**Hiểu nhầm 7 — Đặt `@SafeVarargs` lên method bất kỳ.** Không. Java giới hạn vị trí hợp lệ của annotation.

**Hiểu nhầm 8 — `List<Object>` thay được mọi raw List trong mọi API.** Không. Java Generics invariant; `List<String>` không phải `List<Object>`.

**Hiểu nhầm 9 — `List<?>` giống `List<Object>`.** Không. Wildcard chưa biết hạn chế các thao tác ghi.

**Hiểu nhầm 10 — Có `Class<List<String>>` token từ `List<String>.class`.** Không. Parameterized type đó không có class literal.

**Hiểu nhầm 11 — Unchecked cast qua `List<String>` kiểm tra từng String.** Không. Nó chỉ có thể kiểm tra raw runtime class `List`.

**Hiểu nhầm 12 — `javac -Xlint:all` chỉ bật ba nhóm Generics.** Không. Nó bật nhiều lint categories hơn.

**Hiểu nhầm 13 — Có warning nhưng test pass nghĩa warning vô hại.** Không. Test chỉ chạy trên tập dữ liệu được chọn; type pollution có thể nằm ở đường chưa thử.

**Hiểu nhầm 14 — Không có warning nghĩa không thể có `ClassCastException`.** Không. Warnings không bảo đảm phát hiện mọi nguồn dữ liệu sai.

**Hiểu nhầm 15 — `-Werror` tạo runtime checks mới.** Không. Nó chỉ tác động kết quả build khi có compiler warnings.

**Hiểu nhầm 16 — `javac -Xlint` sẽ rà soát toàn dự án dù chỉ truyền một file.** Không. Chỉ source được compiler xử lý mới có diagnostics trong lần compile ấy.

**Hiểu nhầm 17 — Hễ `varargs` là xóa an toàn bằng cách thêm `@SafeVarargs`.** Không. Phải chứng minh body và helper không gây heap pollution.

**Hiểu nhầm 18 — Dùng raw type để tiết kiệm ký tự.** Dùng diamond hoặc wildcard thường giữ code ngắn mà vẫn có type checks tốt hơn.

## 32. Bài tập có đáp án

### Câu 1 — Nhận diện raw type

```java
List list = new ArrayList();
```

Bật lint key nào để phát hiện raw usage?

**Đáp án:** `-Xlint:rawtypes`.

### Câu 2 — Nhận diện unchecked call

```java
List raw = new ArrayList();
raw.add(123);
```

Lời gọi `add` thường thuộc nhóm cảnh báo nào?

**Đáp án:** `-Xlint:unchecked`, vì method invocation qua raw receiver không được kiểm tra đầy đủ.

### Câu 3 — Unchecked conversion

```java
List<String> strings = raw;
```

Nếu `raw` có kiểu raw `List`, compiler có thể phát cảnh báo gì?

**Đáp án:** Unchecked conversion warning.

### Câu 4 — Heap pollution

Một `List<String>` bị ghi `Integer` qua raw alias rồi đọc như `String` có thể gây lỗi gì?

**Đáp án:** `ClassCastException` ở nơi lấy phần tử Integer và dùng như String.

### Câu 5 — `@SafeVarargs`

Annotation này có tự làm varargs method an toàn không?

**Đáp án:** Không. Nó là cam kết của người viết và không thay đổi runtime component type hay erasure.

### Câu 6 — `-Xlint:varargs`

Có phải mọi method `String... values` sẽ bị cảnh báo không?

**Đáp án:** Không. `String` là reifiable component type; loại rủi ro generic varargs đang xét không tự xuất hiện.

### Câu 7 — Giải pháp cho raw receiver

Nếu API muốn nhận list bất kỳ chỉ để đọc, thay raw `List` bằng kiểu gì?

**Đáp án:** `List<?>` thường phù hợp.

### Câu 8 — `List<Object>` và `List<String>`

Có thể gán `List<String>` cho `List<Object>` không?

**Đáp án:** Không, do invariance của generic Java.

### Câu 9 — `Class.cast`

`String.class.cast(123)` có thể giúp gì ở adapter?

**Đáp án:** Nó phát hiện sai class ở runtime bằng `ClassCastException`, thay vì tin một unchecked cast.

### Câu 10 — Warnings và build

Lệnh nào bật ba nhóm lint và yêu cầu compiler thất bại khi có warning?

**Đáp án:**

```bash
javac -Xlint:unchecked,rawtypes,varargs -Werror Main.java
```

### Câu 11 — Cảnh báo khác error

Warning có luôn chặn việc tạo `.class` không?

**Đáp án:** Không theo mặc định. `-Werror` có thể biến sự hiện diện warnings thành build failure.

### Câu 12 — stdout

Nếu compiler cảnh báo lúc chạy `javac`, warning ấy có thuộc stdout do `System.out.println` của chương trình không?

**Đáp án:** Không. Cần phân biệt hai bước compile và run.

### Câu 13 — Varargs alias

Vì sao `Object[] alias = groups` có thể nguy hiểm với `List<String>... groups`?

**Đáp án:** Alias có thể dùng để ghi `List<Integer>` vào mảng runtime component raw `List`, làm sai hợp đồng generic.

### Câu 14 — Kiểm thử

Sau khi loại warnings, có nên bỏ test kiểm tra dữ liệu sai kiểu?

**Đáp án:** Không. Lint không chứng minh mọi đường runtime và không thay thế kiểm thử.

### Câu 15 — Suppression

Một unchecked cast được cho là an toàn cần điều gì?

**Đáp án:** Invariant có thể giải thích và kiểm chứng, suppression phạm vi hẹp, và test tại ranh giới dữ liệu.

## 33. Checklist thực hành trước khi merge

1. Build bằng đúng **JDK mục tiêu**.
2. Bật `-Xlint:unchecked,rawtypes,varargs`.
3. Ghi nhận toàn bộ warnings phát sinh, phân loại theo vị trí.
4. Đổi raw types thành parameterized types, wildcards hoặc typed adapters khi phù hợp.
5. Tìm unchecked casts/conversions từ legacy input, reflection, collection không tin cậy.
6. Kiểm tra khả năng dữ liệu sai generic argument lọt qua cast hoặc raw alias.
7. Với generic varargs, kiểm tra các đường ghi, truyền helper, aliasing và escape.
8. Chỉ dùng `@SafeVarargs` khi implementation thực sự an toàn và vị trí annotation hợp lệ.
9. Không dùng suppression rộng để che lỗi chưa phân tích.
10. Đối với suppression bắt buộc, ghi lý do và test.
11. Đảm bảo kết quả compile và runtime được kiểm tra riêng.
12. Test với dữ liệu hợp lệ, phần tử sai kiểu, `null` và các boundary cases.
13. Cân nhắc bật `-Werror` khi baseline warnings đã được kiểm soát.
14. Giữ cấu hình compiler flags nhất quán giữa máy phát triển và CI.
15. Nếu build đa module, xác nhận từng module Java cần thiết thực sự được compile với flags.
16. Xem warning mới khi thay dependency hoặc JDK như một tín hiệu cần điều tra.
17. Không mặc định “compile thành công” là “generic API type-safe”.
18. Ưu tiên loại nguyên nhân hơn việc giảm số dòng warning.

## 34. Tổng kết và tài liệu chuẩn

Bật các nhóm lint sau là một bước quan trọng khi học và rà soát Java Generics:

```bash
javac -Xlint:unchecked,rawtypes,varargs Main.java
```

- **`rawtypes`** phát hiện những nơi dùng generic types nhưng thiếu type arguments.
- **`unchecked`** phát hiện các phép toán mà compiler không thể chứng minh đầy đủ về kiểu, như raw calls/conversions hoặc casts với parameterized types.
- **`varargs`** hỗ trợ phát hiện thao tác potentially unsafe trên varargs arrays có generic component non-reifiable, nhất là khi code dùng `@SafeVarargs`.

Đây là **cơ chế cảnh báo ở compile time**, không phải bộ runtime type checks. Những vấn đề về erasure, heap pollution, cast muộn, null, aliasing hoặc API legacy vẫn cần được xử lý bằng thiết kế kiểu rõ ràng và kiểm thử.

Hướng giải quyết đúng là: **bật cảnh báo → đọc nguyên nhân → sửa generic signature hoặc adapter → kiểm toán varargs → test runtime → kiểm soát warning mới trong build/CI**. `@SuppressWarnings`, `@SafeVarargs` và `-Werror` có tác dụng cụ thể nhưng không thể thay thế việc chứng minh an toàn kiểu.

Nguồn tra cứu chính thức:

- [JDK 17 `javac` tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint`, `-Werror`, compiler options.
- [JLS §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): raw types và unchecked behavior.
- [JLS §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments và generics.
- [JLS §4.12.2 — Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2): heap pollution.
- [JLS §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): giới hạn kiểu runtime.
- [JLS §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): variable arity parameters.
- [JLS §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): vị trí annotation và cam kết an toàn.
- [Java SE 17 `java.lang.SafeVarargs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): annotation API.
- [Java SE 17 `java.lang.SuppressWarnings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html): phạm vi suppression.
- [Java SE 17 `java.util.Collections`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): checked collections wrappers và legacy boundaries.