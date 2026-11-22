# `@SafeVarargs`: Khi nào được dùng cho phương thức và constructor trong Java?

`@SafeVarargs` là annotation thuộc `java.lang`, dùng để **cam kết rằng phần thân phương thức hoặc constructor nhận varargs không thực hiện thao tác không an toàn với tham số varargs**. Nó đặc biệt hữu ích với **generic varargs** có phần tử kiểu *non-reifiable*, ví dụ `List<String>...`, `T...` hoặc `List<? extends T>...`, nơi trình biên dịch thường cảnh báo về nguy cơ *heap pollution*.

Tuy nhiên, `@SafeVarargs` **không khiến kiểu generic trở thành reifiable**, không thêm runtime check cho đối số kiểu, và không bảo đảm an toàn bằng phép màu. Trách nhiệm chứng minh tính an toàn thuộc về người viết phương thức/constructor.

**Trên Java 17+, có thể áp dụng `@SafeVarargs` cho:**

- **Constructor** có khai báo tham số varargs.
- **Phương thức `static`** có khai báo tham số varargs.
- **Phương thức instance `final`** có khai báo tham số varargs.
- **Phương thức `private`** có khai báo tham số varargs, bao gồm cả `private static` và `private` instance (khả năng dùng cho `private` instance được hỗ trợ từ Java 9).

Không được dùng annotation này cho một **phương thức instance thông thường có thể bị override** (chẳng hạn `public`/package-private/protected không `final`, không `static`), hoặc cho phương thức **không có `...`**.

## 1. Ôn lại varargs và generic varargs

Varargs cho phép caller truyền một số lượng đối số thay đổi mà không phải tự tạo mảng tại điểm gọi:

```java
// Snippet: phương thức có thể đặt trong một class.
static void show(String... names) {
    for (String name : names) {
        System.out.println(name);
    }
}

// Cách gọi:
show("An", "Binh");
show(new String[] { "An", "Binh" });
```

Trong thân phương thức, `names` thực chất là **`String[]`**. Java compiler có thể tạo mảng thích hợp khi gọi theo cú pháp nhiều đối số hoặc sử dụng mảng đã truyền trong lời gọi fixed-arity tương thích.

Varargs về cơ bản là một cú pháp dành cho **tham số mảng cuối cùng**; không phải một kiểu container generic mới.

Vấn đề xuất hiện khi kiểu phần tử của mảng varargs là một type variable hoặc parameterized type không reifiable:

```java
// Snippet có thể biên dịch, nhưng có thể bị cảnh báo:
static void process(java.util.List<String>... groups) {
    for (java.util.List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Tương đương về kiểu tham số ở phần thân: `groups` có kiểu `List<String>[]`. Nhưng Java **không cho phép khởi tạo trực tiếp** `new List<String>[n]`, vì `List<String>` không reifiable. Khi compiler phải xử lý varargs tại điểm gọi, nó có thể dùng mảng dựa trên erasure và phát cảnh báo unchecked, cho thấy không thể xác minh tất cả type arguments ở runtime.

Vì vậy, không nên suy luận rằng “cú pháp `List<String>...` biên dịch được” đồng nghĩa `List<String>[]` có thể được tạo và kiểm tra đầy đủ như `String[]`.

## 2. Lý do cần một cam kết riêng cho generic varargs

Với `static void process(List<String>... groups)`, tham số trong body là `List<String>[]` ở cấp source, nhưng component runtime của mảng chỉ thể hiện `List` sau erasure. Một `Object[]` alias có thể thay slot bằng `List<Integer>` mà array store check không kiểm tra được phần String trong generic argument.

```java
// Đoạn cố ý sai để hiểu rủi ro, không được gắn @SafeVarargs:
static void unsafe(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42);
    String value = groups[0].get(0); // ClassCastException.
}
```

Đoạn trên cần import `java.util.List` và được đặt trong một class. **Bản thân khai báo varargs non-reifiable chưa phải heap pollution**; chính đường ghi sai mới phá hợp đồng kiểu. Compiler có thể phát cảnh báo tại khai báo và lời gọi vì nó không chứng minh tổng quát rằng những đường như trên bị loại bỏ.

`@SafeVarargs` có ý nghĩa khi người viết có thể cam kết **body và các helper không tạo/để lộ thao tác không an toàn trên array**, và lời khai báo thuộc một nhóm được phép trong Java 17. Điều kiện đặt annotation và cam kết về hành vi là **hai phép kiểm tra riêng**; phần tiếp theo tập trung vào điều kiện cú pháp và ý nghĩa của annotation.

## 3. `@SafeVarargs` thực chất làm gì?

Annotation được dùng trên declaration varargs được phép, ví dụ:

```java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Nó nói với compiler rằng **người viết phương thức đã xác minh phần thân không làm hỏng tính an toàn kiểu của mảng varargs**. Tác dụng nổi bật là compiler **không phát một số cảnh báo unchecked liên quan đến khai báo và lời gọi generic varargs này**.

Cụ thể, annotation thường giúp giảm:

- Cảnh báo tại **declaration site**, ví dụ cảnh báo có thể có heap pollution từ tham số có kiểu varargs non-reifiable.
- Cảnh báo tại **call site** về việc tạo mảng generic không kiểm tra đầy đủ được khi gọi một phương thức varargs non-reifiable đã được đánh dấu an toàn.

Tuy nhiên:

- Nó **không bảo đảm** phần thân an toàn; compiler không chứng minh được tất cả tình huống.
- Nó **không biến** `List<String>`, `T` hay `List<T>[]` thành reifiable.
- Nó **không cho phép** một phương thức instance tùy ý có thể bị override nhận annotation.
- Nó **không tắt mọi cảnh báo** không liên quan trong method body. Những raw/unchecked operations được viết trực tiếp trong thân vẫn cần được xem xét riêng.
- Nó **không làm thay đổi** cơ chế truyền varargs thành array, type erasure hay runtime dispatch.

Hãy hiểu `@SafeVarargs` là **một lời cam kết được compiler tin cậy trong phạm vi varargs**, không phải biện pháp sửa lỗi an toàn kiểu tại runtime.

## 4. Những declaration nào được gắn `@SafeVarargs` trên Java 17+?

| Declaration | Được phép? | Lý do |
| --- | --- | --- |
| `@SafeVarargs static <T> void f(T... xs)` | Có | `static` không bị override |
| `@SafeVarargs final <T> void f(T... xs)` | Có | `final` instance method không bị override |
| `@SafeVarargs private <T> void f(T... xs)` | Có, Java 9+ | `private` instance method không bị override |
| `@SafeVarargs private static <T> void f(T... xs)` | Có | Đồng thời `private` và `static` |
| `@SafeVarargs C(T... xs)` trên constructor | Có | Constructor không phải phương thức override |
| `@SafeVarargs public <T> void f(T... xs)` không `final` | Không | Instance method có thể bị override |
| `@SafeVarargs protected <T> void f(T... xs)` không `final` | Không | Instance method có thể bị override |
| `@SafeVarargs void f(T value)` | Không | Không có tham số varargs |
| `@SafeVarargs abstract void f(T... xs)` | Không | Không thuộc nhóm static/final/private/contructor được phép; không có thân để cam kết |

Bảng mô tả từng declaration độc lập; với class hoặc interface thực tế, vẫn cần đáp ứng các quy tắc Java khác như tính hợp lệ của modifier, signature và kiểu tham số.

### Vì sao chỉ những nhóm không bị override?

Annotation liên quan đến **hành vi của thân phương thức varargs**. Nếu một phương thức có thể bị override, bên gọi có thể dispatch đến phần thân khác; compiler không thể dựa vào một lời cam kết an toàn gắn với declaration dễ bị thay thế.

Constructor không bị override. `static` method bị *hiding* chứ không bị override bằng dispatch instance; `final` instance method không thể bị override; `private` instance method không được kế thừa theo cơ chế override.

Trên Java 8 trở về trước, điều kiện đối với `private` instance method khác Java 9+. Khi viết code Java 17, có thể dùng `@SafeVarargs` trên `private` instance varargs đúng cú pháp.

## 5. `@SafeVarargs` cho constructor

Một constructor có thể nhận generic varargs và sao chép dữ liệu sang collection riêng:

```java
import java.util.Arrays;
import java.util.List;

final class Batch<T> {
    private final List<T> values;

    @SafeVarargs
    Batch(T... items) {
        values = List.copyOf(Arrays.asList(items));
    }

    List<T> values() {
        return values;
    }
}
```

Khi caller dùng:

```java
Batch<String> names = new Batch<>("An", "Binh");
```

constructor nhận mảng `T...` và **không công khai mảng ấy**. Nó sao chép các phần tử vào một `List` không thể sửa cấu trúc bằng `List.copyOf`. Cách này tránh giữ một alias mảng varargs do caller có thể thay đổi sau đó.

Lưu ý về hợp đồng: `List.copyOf` không chấp nhận phần tử `null`. Nếu cần cho phép null, phải chọn cách lưu trữ khác và tài liệu hóa quy tắc rõ ràng.

**Chỉ giữ lại `T[] items` trong field và trả nó ra ngoài chưa chắc an toàn.** Array varargs có thể chính là mảng caller truyền vào; việc lưu reference cho tương lai cần phân tích khả năng alias và mutation, không chỉ dựa vào kiểu `T[]` được viết ở nguồn.

## 6. `@SafeVarargs` cho static generic varargs method

Một ví dụ hữu ích là hợp nhất nhiều danh sách generic theo hướng **chỉ đọc**:

```java
@SafeVarargs
static <T> java.util.List<T> merge(
        java.util.List<? extends T>... parts) {
    java.util.List<T> output = new java.util.ArrayList<>();

    for (java.util.List<? extends T> part : parts) {
        output.addAll(part);
    }

    return java.util.List.copyOf(output);
}
```

Cách gọi:

```java
java.util.List<String> both =
        merge(java.util.List.of("An"), java.util.List.of("Binh"));
```

Phương thức duyệt các `List<? extends T>` rồi thêm phần tử vào `List<T>` mới; không ghi một list sai kiểu vào các slot của mảng `parts`; không expose mảng `parts` cho code khác.

Khi dùng với `List.of`/`List.copyOf`, cần nhớ các API này không nhận null. Nếu nghiệp vụ cho phép null, có thể chọn `ArrayList` và một kết quả/mô hình sở hữu phù hợp.

**Tại sao generic wildcard `? extends T` hữu ích?** Từng danh sách nguồn chỉ cần sản xuất các giá trị có thể được xem như `T`; không cần phải là `List<T>` đúng chính xác. Nhưng việc wildcard phù hợp **không tự tạo** an toàn cho varargs; phần thân vẫn phải tránh heap pollution và rò rỉ mảng.

## 7. `final` instance method và `private` instance method

Hai nhóm này hợp lệ trong Java 17:

```java
class Reporter {
    @SafeVarargs
    final <T> int count(T... items) {
        return items.length;
    }

    @SafeVarargs
    private <T> String format(T... items) {
        return java.util.Arrays.toString(items);
    }

    String report() {
        return format("An", "Binh") + ": " + count(1, 2);
    }
}
```

Trong trường hợp này:

- `count` là `final` nên lớp con không thể override.
- `format` là `private` nên không tham gia override từ subclass.
- Cả hai nhận varargs thật bằng dấu `...`.
- Nội dung chỉ đọc mảng hoặc dựng chuỗi từ các phần tử; chúng không dùng `Object[]` alias để đưa một giá trị trái kiểu vào mảng tham số.

Một phương thức **`private static`** cũng được phép:

```java
@SafeVarargs
private static <T> T first(T... items) {
    return items[0];
}
```

Ví dụ giả định caller bảo đảm ít nhất một phần tử; trong code thực tế nên kiểm tra độ dài và báo lỗi thích hợp cho trường hợp rỗng. Khả năng dùng `@SafeVarargs` không đồng nghĩa method body tự xử lý mọi lỗi ngoài vấn đề type safety.

## 8. Những cách dùng sai bị compiler từ chối

### 8.1. Đặt trên method không phải varargs

```java
// KHÔNG BIÊN DỊCH:
class InvalidOne {
    @SafeVarargs
    static <T> void copy(T value) {
    }
}
```

`T value` là một tham số thường; method không có `...`. Annotation chỉ áp dụng cho **declaration có variable arity parameter**.

### 8.2. Đặt trên instance method có thể override

```java
// KHÔNG BIÊN DỊCH:
class InvalidTwo {
    @SafeVarargs
    public <T> void send(T... items) {
    }
}
```

`send` ở đây không `final`, không `private`, không `static`, cũng không phải constructor. Việc phương thức có type parameter `T` **không đủ** để annotation hợp lệ.

Sửa theo thiết kế:

```java
// Những hướng sửa độc lập về declaration:
class ValidTwo {
    @SafeVarargs
    public final <T> void send(T... items) {
        for (T item : items) {
            System.out.println(item);
        }
    }
}
```

Nếu phương thức phải có khả năng override, **không nên thêm `final` chỉ để dập cảnh báo** mà không cân nhắc thiết kế. Khi đó, có thể bỏ annotation, thay varargs bằng `List<T>`, hoặc đổi API thành một phương thức helper `static`/`private` thích hợp.

### 8.3. Annotation hợp lệ không có nghĩa body an toàn

```java
// Có thể biên dịch dù mang hành vi không an toàn:
@SafeVarargs
static void dangerous(java.util.List<String>... lists) {
    Object[] array = lists;
    array[0] = java.util.List.of(42);
    String item = lists[0].get(0); // ClassCastException
}
```

Lỗi này **không được sửa** bằng `@SafeVarargs`. Ngược lại, nó cho thấy người viết phương thức đã đưa ra **một lời cam kết sai**.

## 9. Chương trình Java 17+ hoàn chỉnh: trường hợp hợp lệ và phản ví dụ

Lưu mã sau thành **`SafeVarargsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SafeVarargsDemo {
    static final class Batch<T> {
        private final List<T> values;

        @SafeVarargs
        Batch(T... items) {
            values = List.copyOf(Arrays.asList(items));
        }

        List<T> values() {
            return values;
        }
    }

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... parts) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> part : parts) {
            result.addAll(part);
        }
        return List.copyOf(result);
    }

    @SafeVarargs
    private static <T> T first(T... items) {
        return items[0];
    }

    @SafeVarargs
    final <T> int count(T... items) {
        return items.length;
    }

    @SafeVarargs
    private <T> String show(T... items) {
        return Arrays.toString(items);
    }

    // KHÔNG AN TOÀN: chỉ giữ để chứng minh annotation không bảo vệ runtime.
    @SafeVarargs
    static void dangerous(List<String>... lists) {
        Object[] array = lists;
        array[0] = List.of(42);
        String ignored = lists[0].get(0);
    }

    public static void main(String[] args) {
        System.out.println("Constructor: "
                + new Batch<>("An", "Binh").values());
        System.out.println("Static method: "
                + merge(List.of("a"), List.of("b", "c")));
        System.out.println("Private static: " + first("A", "B"));

        SafeVarargsDemo demo = new SafeVarargsDemo();
        System.out.println("Final instance: " + demo.count(1, 2, 3));
        System.out.println("Private instance: " + demo.show("x", "y"));

        try {
            dangerous(List.of("safe"));
        } catch (ClassCastException exception) {
            System.out.println("Wrong @SafeVarargs: ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 -Xlint:varargs -Xlint:unchecked SafeVarargsDemo.java
java SafeVarargsDemo
```

**Standard output** của chương trình:

```text
Constructor: [An, Binh]
Static method: [a, b, c]
Private static: A
Final instance: 3
Private instance: [x, y]
Wrong @SafeVarargs: ClassCastException
```

Giải thích kết quả:

1. Constructor `Batch(T...)` hợp lệ; nó sao chép nội dung thành một list không thể sửa cấu trúc.
2. Static `merge(List<? extends T>...)` duyệt từng danh sách an toàn và trả list mới.
3. `private static first`, `final count` và `private show` minh họa những declaration hợp lệ cho annotation trên Java 17.
4. Phương thức `dangerous` cũng được phép **về mặt vị trí đặt annotation**, nhưng cố ý thay phần tử mảng varargs bằng một `List<Integer>` qua `Object[]`. Sau đó lấy `Integer` thành `String` và ném `ClassCastException`.
5. `try/catch` bao phản ví dụ cuối giúp toàn bộ chương trình vẫn chạy hết và cho thấy chính xác lỗi bị bắt.

Lệnh `javac -Xlint:varargs` có thể phát **cảnh báo bên trong phương thức `dangerous`** vì thao tác alias/mutation đáng ngờ. Đó là hành vi hữu ích: `@SafeVarargs` không phải một cam kết được compiler chứng minh hoặc một lá chắn loại bỏ mọi thông báo về code không an toàn.

**Không dùng phương thức `dangerous` trong ứng dụng thật.** Nó chỉ là phản ví dụ có kiểm soát, giúp phân biệt “annotation được phép đặt” với “lời cam kết an toàn là đúng”.

## 10. Những hoạt động nào thường an toàn với mảng varargs?

Một thân phương thức được đánh dấu `@SafeVarargs` nên được xem xét kỹ theo dữ liệu đi qua tham số varargs.

### 10.1. Duyệt để đọc, không sửa array slots

```java
@SafeVarargs
static <T> void visit(java.util.function.Consumer<? super T> action,
                       T... values) {
    for (T value : values) {
        action.accept(value);
    }
}
```

Phương thức không gán một object không tương thích vào `values[i]` và không trả mảng `values` trực tiếp. Nhưng khi đánh giá tính an toàn hoàn toàn, vẫn phải xem **`action` làm gì**: callback không đáng tin có thể gây tác dụng phụ hoặc ném exception. Việc callback không được cấp tham chiếu mảng `values` tự thân giúp tránh một đường rò rỉ array, song mọi invariants khác của nghiệp vụ vẫn cần kiểm soát.

### 10.2. Sao chép sang container typed mới

```java
@SafeVarargs
static <T> java.util.List<T> snapshot(T... values) {
    return java.util.List.copyOf(java.util.Arrays.asList(values));
}
```

Việc trả về một `List` mới thay vì tham chiếu array varargs giúp tách bộ chứa. Tuy nhiên `List.copyOf` không chấp nhận null và chỉ thực hiện **shallow copy**; đối tượng phần tử mutable vẫn có thể thay đổi trạng thái.

### 10.3. Những điều cần cảnh giác

Không nên đánh dấu an toàn một method nếu phần thân:

- Gán phần tử không đúng type argument vào array varargs qua `Object[]`, raw type hoặc unchecked alias.
- Trả trực tiếp mảng varargs `T[]` ra ngoài hoặc giữ một alias có thể bị sửa theo cách không kiểm soát, khiến caller tin vào một runtime component type không phù hợp.
- Truyền mảng đến phương thức khác mà bạn không kiểm soát, nơi nó có thể bị sửa hoặc rò rỉ.
- Thực hiện cast unchecked và ghi dữ liệu trái hợp đồng generic, rồi dựa vào annotation để che cảnh báo.
- Phá hợp đồng bằng dữ liệu không phù hợp dù việc tạo mảng varargs lúc đầu hợp lệ.

Các điểm này là **tiêu chí phân tích an toàn**, không phải lệnh cấm cú pháp đối với mọi thao tác trả array. Có API trả mảng có thể được chứng minh an toàn trong điều kiện rất cụ thể; tuy nhiên, với generic varargs non-reifiable, việc làm lộ trực tiếp mảng là nơi dễ tạo heap pollution và lời hứa kiểu sai, nên mặc định cần tránh.

## 11. Cảnh báo ở declaration và call site: phân biệt rõ

Không có annotation:

```java
// Snippet: javac có thể cảnh báo tại declaration.
static void log(java.util.List<String>... messages) {
    for (java.util.List<String> list : messages) {
        System.out.println(list);
    }
}
```

Một lời gọi:

```java
log(java.util.List.of("a"), java.util.List.of("b"));
```

Khi compiler phải sắp xếp các `List<String>` thành một array varargs, kiểu phần tử `List<String>` là non-reifiable. Vì vậy, compiler có thể cảnh báo **unchecked generic array creation for varargs parameter** ở nơi gọi.

Nếu đã kiểm tra phần thân `log` là an toàn, có thể đổi declaration thành:

```java
@SafeVarargs
static void log(java.util.List<String>... messages) {
    for (java.util.List<String> list : messages) {
        System.out.println(list);
    }
}
```

Cảnh báo varargs liên quan thường được giảm hoặc bỏ tại declaration và các call sites của method được đánh dấu. Nhưng nếu method còn sử dụng raw types không an toàn bên trong, `-Xlint:unchecked` hoặc `-Xlint:varargs` vẫn có thể chỉ ra hành vi cần điều tra.

### Không nên dùng `@SuppressWarnings("unchecked")` thay bừa `@SafeVarargs`

`@SuppressWarnings("unchecked")` là cơ chế tổng quát hơn để ẩn cảnh báo trong phạm vi nguồn có annotation. Nó không cam kết chính thức về độ an toàn của **varargs method** với caller, và có thể che các unchecked operations khác nếu đặt quá rộng.

`@SafeVarargs` giao tiếp hợp đồng tới cả nơi khai báo và nơi gọi. Chỉ nên dùng khi method/constructor thỏa điều kiện cho phép và được chứng minh an toàn; không dùng nó chỉ để “hết warning”.

## 12. Các câu hỏi dễ nhầm về generic varargs

### `@SafeVarargs` có bắt buộc với mọi varargs không?

**Không.** `String...`, `int...`, `Object...` thông thường có reifiable component types và có thể không gây cảnh báo generic varargs cần giải quyết. Dùng `@SafeVarargs` chỉ khi có lý do, tránh annotation dư thừa trên các varargs element types đã reifiable.

### `List<?>...` có luôn cần `@SafeVarargs` không?

`List<?>` là kiểu tham số hóa với toàn wildcard không bound và thuộc nhóm **reifiable**, nên tình huống khác `List<String>...`. Compiler có thể coi một `List<?>[]` là mảng với component type reifiable. Không nên gắn annotation theo thói quen chỉ vì thấy dấu `< >`.

### Có thể dùng `@SafeVarargs` để sửa `new T[10]` không?

**Không.** Annotation chỉ áp dụng cho declaration có tham số varargs và không làm type variable `T` reifiable. Biểu thức `new T[n]` vẫn bị cấm trong generic class/method.

### Nó có khiến một phương thức có thể override trở nên `final` không?

**Không.** `@SafeVarargs` không thay đổi modifier. Nếu method không thuộc nhóm được phép, phải sửa thiết kế (ví dụ `final` khi thực sự hợp lý) hoặc không dùng annotation.

### Annotation có tự ngăn heap pollution lúc runtime không?

**Không.** Code `dangerous` trong chương trình chạy cho thấy method được annotate sai vẫn có thể tạo dữ liệu sai kiểu và gây `ClassCastException`.

### Dùng trên constructor của class generic có hợp lệ không?

**Có.** Ví dụ `Batch(T...)` trong chương trình chạy. Constructor không bị override nên được phép; nhưng vẫn phải tự đảm bảo phần thân không làm hỏng array varargs.

### Dùng trên method instance `private` có hợp lệ từ khi nào?

Từ **Java 9**. Trên Java 17+ được dùng; trên các phiên bản Java trước đó, cần xem quy tắc hỗ trợ tương ứng thay vì giả định mã nguồn sẽ compile được ở mọi mức `--release`.

## 13. Quy trình tự kiểm tra trước khi thêm annotation

Trước khi viết `@SafeVarargs`, hãy đi qua checklist:

1. **Có varargs thật không?** Tham số cuối phải có `...`.
2. **Đúng loại declaration chưa?** Constructor, `static`, `final`, hoặc `private` instance method (Java 9+).
3. **Element type có non-reifiable không?** Với `T...`, `List<String>...`, `List<? extends T>...`, nguy cơ thường đáng chú ý. Với `String...` hoặc `List<?>...`, annotation có thể thừa.
4. **Có ghi vào array slots không?** Đặc biệt kiểm tra các phép gán qua `Object[]`, raw type hoặc reflection.
5. **Mảng có bị rò rỉ không?** Kiểm tra `return values`, field assignment, callback và các phương thức được gọi bên ngoài.
6. **Có unchecked operations khác không?** Không dùng annotation làm lá chắn che những chỗ chưa được chứng minh an toàn.
7. **Caller có thể truyền array trực tiếp không?** Varargs method cũng có thể được gọi với mảng có sẵn; phân tích nguy cơ alias khi method sửa hoặc giữ array.
8. **Bản sao có độc lập không?** Nếu cần lưu/trả tập phần tử, tạo container mới hoặc sao chép theo hợp đồng, tránh cho code khác thay đổi mảng varargs.
9. **Đã thử `javac -Xlint:varargs -Xlint:unchecked` chưa?** Cảnh báo là dấu hiệu cần xem, kể cả khi annotation hợp lệ về cú pháp.
10. **Đã có test dữ liệu bất thường chưa?** Thử null, empty array, các kiểu phần tử khác nhau và các trường hợp raw/unchecked nếu ranh giới API có thể gặp chúng.

Với code thư viện được nhiều nơi gọi, chi phí review cẩn thận thấp hơn rất nhiều so với việc xuất hiện `ClassCastException` tại một vị trí xa nơi heap pollution được tạo.

## 14. Bài tập tự kiểm tra

**Câu 1.** `@SafeVarargs static <T> void f(T... items)` có hợp lệ trên Java 17 không?

Có, vì đây là static varargs method. Nhưng body phải thực sự an toàn để lời cam kết đúng.

**Câu 2.** `@SafeVarargs public <T> void f(T... items)` trong một class không `final`, method không `final`, có hợp lệ không?

Không. Đây là instance method có thể bị override. Cần xem lại API, thêm `final` nếu thiết kế cho phép, hoặc bỏ annotation.

**Câu 3.** `@SafeVarargs private <T> void f(T... items)` có hợp lệ với Java 17 không?

Có. Java 9+ cho phép annotation trên private instance varargs method.

**Câu 4.** Có thể dùng `@SafeVarargs` cho constructor của `final class Bag<T>` nhận `T... values` không?

Có. Constructor không bị override; nhưng vẫn phải đảm bảo không gây heap pollution hoặc làm lộ array không an toàn.

**Câu 5.** Phương thức `dangerous(List<String>...)` đã có annotation nhưng ghi `List<Integer>` qua `Object[]`. Nó có an toàn không?

Không. Annotation không ngăn thao tác sai; mã có thể ném `ClassCastException` khi giá trị được đọc như `String`.

**Câu 6.** Vì sao `@SafeVarargs` giúp giảm cảnh báo ở call site?

Nó thông báo lời cam kết của tác giả rằng method không thực hiện thao tác không an toàn với tham số varargs, nên compiler có thể tin tưởng giảm những cảnh báo về generic array creation của lời gọi tương ứng.

**Câu 7.** Một method chỉ có `String... names` có cần `@SafeVarargs` không?

Thông thường không. `String` là reifiable và mảng varargs `String[]` có component type runtime rõ ràng; annotation có thể bị compiler nhận xét là không cần thiết.

**Câu 8.** `@SafeVarargs` có cho phép `new List<String>[3]` trong thân phương thức không?

Không. Generic array creation có component type non-reifiable vẫn bị cấm.

## 15. Kết luận

`@SafeVarargs` là **cam kết an toàn của tác giả** dành cho các constructor/method có tham số varargs, đặc biệt khi element type không reifiable. Trên Java 17+, annotation được phép trên **constructor, phương thức static, final instance và private instance** có varargs. Nó giúp xử lý các cảnh báo generic varargs tại declaration/call site, nhưng **không thay đổi erasure và không ngăn mã sai kiểu ở runtime**.

Khi sử dụng, hãy đảm bảo phần thân không ghi phần tử trái kiểu vào array varargs, không làm rò rỉ mảng theo cách phá an toàn kiểu, và không dùng unchecked tricks thiếu kiểm soát. Nếu không thể đưa ra lập luận an toàn chắc chắn, hãy giữ cảnh báo để điều tra hoặc thiết kế API khác, chẳng hạn dùng `List<T>` thay cho generic varargs.