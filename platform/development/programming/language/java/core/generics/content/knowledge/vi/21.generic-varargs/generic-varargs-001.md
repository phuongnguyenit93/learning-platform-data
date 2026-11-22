# Ô nhiễm kiểu trong heap (heap pollution) và biến có kiểu tham số hóa

## Mục tiêu

Trong Java Generics, biến `List<String>` hứa với trình biên dịch rằng khi đọc phần tử, chương trình có thể xem phần tử đó là `String`. Tuy nhiên, nếu một đường gọi khác dùng **raw type**, **unchecked conversion/cast** hoặc thao tác thiếu an toàn trên **generic varargs**, cấu trúc dữ liệu thực có thể không còn đáp ứng cam kết. Tình trạng ấy được gọi là **heap pollution (ô nhiễm kiểu trong heap)**.

Bài này thuộc chủ đề **Varargs generic** trong Java Core — Generics. Sau khi học, bạn có thể:

- Giải thích heap pollution theo quan hệ giữa kiểu tham số hóa ở source và đối tượng thực trong heap.
- Phân biệt **heap pollution**, **unchecked warning** và **`ClassCastException`**; chúng liên quan nhưng không đồng nghĩa.
- Chứng minh hai nguồn gây ô nhiễm: raw `List` và **mảng varargs** `List<String>...`.
- Giải thích tại sao phép gán `Object[] alias = groups; alias[0] = List.of(99);` có thể qua được runtime array store check nhưng lời đọc `String` thất bại.
- Dùng `-Xlint:rawtypes`, `-Xlint:unchecked`, `-Xlint:varargs` để đọc những cảnh báo có ích.
- Áp dụng `@SafeVarargs` có trách nhiệm; hiểu giới hạn của annotation và chọn collection/generic method không varargs khi phù hợp.
- Bọc dữ liệu không đáng tin bằng adapter **kiểm tra từng phần tử** thay vì unchecked cast cả collection.

Các chương trình hoàn chỉnh chạy được bằng **Java 17 trở lên**. Các đoạn có comment báo lỗi biên dịch chỉ để phân tích; không được sao chép thành chương trình độc lập mà bỏ comment.

## 1. Heap pollution chính xác là gì?

Một cách diễn đạt chuẩn: **heap pollution xảy ra khi một biến có kiểu tham số hóa tham chiếu tới một đối tượng không tương thích với kiểu tham số hóa ấy**. Đây không phải một lỗi syntax hay exception riêng tên `HeapPollutionException`: nó là **trạng thái không bảo đảm an toàn kiểu**, có thể chưa gây lỗi ngay lúc được tạo ra.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class Illustration {
    static void demonstrate() {
        List<String> names = new ArrayList<>();
        names.add("Java");

        List raw = names;   // Hai biến trỏ cùng một ArrayList.
        raw.add(42);       // Lời gọi unchecked.

        // names được khai báo List<String>, nhưng chứa Integer.
        // String second = names.get(1); // ClassCastException khi chạy.
    }
}
```

Đoạn trên là một lớp minh họa không có `main`; chương trình đầy đủ có output kiểm chứng ở mục 4.

Tại sao compiler không chặn ngay `raw.add(42)`? Kiểu nguồn của biến `raw` là **raw `List`**, đã bỏ đối số kiểu `String`. Phương thức `add` vì thế được dùng mà không có bảo đảm compile-time dành cho `List<String>`; compiler phát cảnh báo unchecked, nhưng không biết rằng biến `raw` đang làm hỏng một cam kết generic của biến khác.

Thao tác `raw.add(42)` không nhất thiết ném exception, bởi runtime class `ArrayList` không có một phiên bản riêng cho `ArrayList<String>`. Lỗi có thể được phát hiện ở một chỗ **đọc/ép kiểu** sau đó: khi compiler kỳ vọng `String` nhưng giá trị thật là `Integer`.

### Ba khái niệm không được đánh đồng

| Khái niệm | Nói về | Ví dụ |
| --- | --- | --- |
| **Heap pollution** | Đối tượng mà một tham chiếu generic tin tưởng không còn phù hợp với tham số kiểu | `List<String>` chứa `Integer` |
| **Unchecked warning** | Compiler không xác minh được toàn bộ tính đúng kiểu của phép gọi/chuyển đổi | `raw.add(42)`, generic varargs không an toàn |
| **`ClassCastException`** | Một phép cast runtime cụ thể thất bại | Lấy `Integer` từ `List<String>` rồi dùng như `String` |

Một cảnh báo unchecked **chỉ báo rủi ro**, không khẳng định heap pollution chắc chắn đã xảy ra. Ngược lại, nếu code đã cố tình lách những kiểm tra kiểu, heap pollution có thể tồn tại trước khi một exception được ném. Đừng sử dụng “chạy không lỗi” làm bằng chứng rằng đường dữ liệu đã an toàn.

## 2. Kiểm tra kiểu của generics và type erasure

`List<E>` được định nghĩa với tham số kiểu `E`; trong `List<String>`, compiler dùng `String` để kiểm tra lời gọi. Ví dụ:

```java
List<String> messages = new ArrayList<>();
messages.add("Hello");
// messages.add(3); // Lỗi biên dịch nếu gọi qua tham chiếu typed.
String first = messages.get(0);
```

Đoạn này giả định có `import java.util.List;` và `import java.util.ArrayList;`.

Đối số kiểu `String` **không tạo một runtime class `List<String>` riêng**. Java generics thực hiện **type erasure**; một lời gọi như `List.get(int)` sử dụng descriptor trả `Object`, còn compiler có thể chèn `checkcast String` tại vị trí đọc kết quả thành `String`.

Đừng hiểu việc xóa kiểu là biến đối tượng `String` thành một `Object` khác. Đối tượng thực vẫn có runtime class `String`; chỉ phần thông tin về **type argument của container** không được JVM thể hiện như một runtime class chuyên biệt.

Hệ quả liên quan tới heap pollution: ở mức runtime, `ArrayList` không thể tự dùng một loại “store check cho `String`” trên mọi lời `add`. Nếu dữ liệu đi qua raw/unchecked path, phần tử sai có thể lọt vào, rồi lỗi xảy ra khi code typed lấy ra.

## 3. Generic varargs: điểm gặp nhau của mảng và type erasure

Trong Java, lời khai báo:

```java
static void show(List<String>... groups) {
    // ...
}
```

sử dụng **varargs**: ở runtime, các đối số varargs được truyền bằng một **mảng**. Nhưng kiểu phần tử `List<String>` là **non-reifiable**: JVM không có runtime class chuyên biệt cho `List<String>`, và không thể tạo trực tiếp `new List<String>[n]` trong Java source.

Điều quan trọng:

- `List<String>...` hợp lệ trong chữ ký varargs, nhưng compiler có thể phát cảnh báo liên quan **possible heap pollution**.
- Mảng runtime nhận phần tử là `List`, không thể kiểm tra type argument `String` của từng danh sách.
- Có thể xem mảng varargs qua một tham chiếu rộng hơn `Object[]` vì array covariance.
- Ghi một `List<Integer>` vào một ô của mảng qua `Object[]` có thể **không** gây `ArrayStoreException`, vì runtime component type vẫn là `List`.
- Lời đọc phần tử với kỳ vọng `String` có thể gây `ClassCastException`.

So sánh hai trường hợp:

```java
String[] texts = {"A"};
Object[] textAlias = texts;
// textAlias[0] = 99; // Biên dịch được, nhưng ArrayStoreException lúc chạy.
```

và:

```java
// Trong một method đang nhận List<String>... groups:
Object[] groupsAlias = groups;
groupsAlias[0] = List.of(99); // JVM vẫn thấy đây là List.
```

Đoạn thứ hai **làm ô nhiễm mảng có kiểu source `List<String>[]`**. Runtime store check chỉ xem đối tượng đưa vào có là `List` không, chứ không thể kiểm tra mọi phần tử bên trong theo type argument `String`. Vì vậy lời gán không bị chặn theo cách `String[]` chặn `Integer`.

Đó là lý do Java hạn chế **generic array creation**, cảnh báo với **non-reifiable varargs** và cung cấp `@SafeVarargs` cho những khai báo có thể được chứng minh an toàn.

## 4. Chương trình A — Thấy heap pollution qua raw type và generic varargs

Tạo tệp **`HeapPollutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    static List<String>[] pollute(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);
        return groups;
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("Java"));
        List raw = words;
        raw.add(42);
        System.out.println("raw contents: " + words);

        try {
            String item = words.get(1);
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("raw read failure: "
                    + ex.getClass().getSimpleName());
        }

        List<String> original = new ArrayList<>(List.of("safe"));
        List<String>[] groups = pollute(original);
        System.out.println("varargs component: "
                + groups.getClass().getComponentType().getName());
        System.out.println("original unaffected: " + original);

        try {
            String item = groups[0].get(0);
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("varargs read failure: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -Xlint:all HeapPollutionDemo.java
java HeapPollutionDemo
```

**Stdout đã kiểm chứng:**

```text
raw contents: [Java, 42]
raw read failure: ClassCastException
varargs component: java.util.List
original unaffected: [safe]
varargs read failure: ClassCastException
```

Với Java 17 và `-Xlint:all`, compiler cũng phát ra **bốn cảnh báo** ở ví dụ được kiểm thử:

- `[unchecked] Possible heap pollution from parameterized vararg type List<String>` tại khai báo `pollute`.
- `[rawtypes]` tại `List raw`.
- `[unchecked]` tại `raw.add(42)`.
- `[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]` tại lời gọi `pollute(original)`.

Văn bản, vị trí và số lượng cảnh báo là đặc thù của phiên bản compiler/tùy chọn lint; chúng là **diagnostics của `javac`**, không phải stdout của chương trình.

### Phần A1 — Raw type phá hợp đồng của `List<String>`

Hai biến `words` và `raw` là **hai tham chiếu tới cùng một `ArrayList`**. Vì `raw` bỏ đối số kiểu, lời `add(42)` có thể chèn một `Integer` vào danh sách mà `words` vẫn tin là `List<String>`.

```text
           List<String> words ---+
                                  +---> ArrayList đang chứa ["Java", 42]
                 List raw -------+
```

Đến lúc `String item = words.get(1)`, code typed cần `String`, compiler đã tạo hành vi cast phù hợp, nhưng đối tượng thật là `Integer`. Chính dòng đọc gây `ClassCastException`, không phải dòng `raw.add(42)`.

### Phần A2 — Generic varargs làm ô nhiễm array, không tự sửa original list

Method:

```java
static List<String>[] pollute(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);
    return groups;
}
```

thực hiện ba việc nguy hiểm:

1. `groups` là một mảng runtime có **component type `List`**, mặc dù compiler biểu diễn nó bằng `List<String>[]` ở source.
2. `Object[] alias = groups` cho phép thao tác qua góc nhìn mảng chứa `Object`.
3. `alias[0] = List.of(99)` thay **ô thứ nhất của mảng groups** bằng danh sách chứa `Integer`. Mảng vẫn chấp nhận vì đối tượng đó là một `List`.
4. Trả `groups` làm tham chiếu tới **mảng đã bị nhiễm** thoát ra ngoài, nơi caller nghĩ có `List<String>[]`.

Dòng:

```text
original unaffected: [safe]
```

cực kỳ quan trọng: phương thức **không thêm `99` vào danh sách `original`**. Nó thay một **phần tử của mảng varargs** — tức thay tham chiếu tới danh sách. Với lời gọi varargs thông thường `pollute(original)`, compiler tạo mảng chuyển đối số, và `original` vẫn giữ phần tử `"safe"`.

Khi code đọc:

```java
String item = groups[0].get(0);
```

nó dựa trên `List<String>[]`, nhưng danh sách tại ô 0 đã chứa `Integer`; phép cast sang `String` thất bại. Đó là heap pollution đi qua **generic varargs**, khác đường raw `List` trước đó.

### Vì sao không ném `ArrayStoreException`?

Mảng thực của `groups` có component type là `java.util.List`. Cả `List<String>` lẫn `List<Integer>` đều có đối tượng runtime thực hiện `List`. Kiểm tra store runtime của mảng không biết type argument đã bị xóa. Ngược lại, nếu cố đưa một `String` trực tiếp vào ô mảng có component class `List`, runtime array store có thể từ chối vì `String` không phải một `List`.

## 5. Vị trí phát hiện lỗi và sự khác nhau giữa ba cơ chế

Một chuỗi diễn biến cần ghi nhớ:

```text
Compile time:
    List<String> x
        |
        +-- x.add(42)                     -> lỗi biên dịch
        |
        +-- raw.add(42)                   -> cảnh báo unchecked

Runtime:
    raw.add(42)                           -> có thể ghi thành công
        |
        v
    List<String> bị ô nhiễm
        |
        v
    String s = x.get(i)                    -> ClassCastException

Generic varargs:
    List<String>... groups
        |
        v
    Object[] alias = groups
        |
        v
    alias[0] = List.of(99)                 -> mảng chỉ kiểm tra component List
        |
        v
    String s = groups[0].get(0)            -> ClassCastException
```

Không phải mọi `ClassCastException` đều bắt nguồn từ heap pollution: cast sai thông thường trên `Object` cũng có thể gây lỗi. Ngược lại, heap pollution chưa chắc ném exception nếu code không đọc/cast dữ liệu sai; đó là lý do test chỉ chạy đường thành công không đủ chứng minh an toàn generic.

**Khác nhau về nơi kiểm tra:**

| Tình huống | Compiler | Runtime | Kết quả |
| --- | --- | --- | --- |
| `List<String>.add(42)` | Bác bỏ | Không chạy | Lỗi biên dịch |
| `List raw = words; raw.add(42)` | Cảnh báo unchecked | `ArrayList` không kiểm tra type argument `String` | Có thể gây heap pollution |
| `Object[]` trỏ `String[]`, ghi `Integer` | Cho phép vì kiểu biến `Object[]` | Kiểm tra component `String` | `ArrayStoreException` |
| `Object[]` trỏ `List<String>[]` của varargs, ghi `List<Integer>` | Có thể không thấy sai qua alias | Chỉ kiểm tra component `List` | Có thể gây heap pollution |
| Đọc `Integer` như `String` | Tin vào kiểu nguồn `List<String>` | `checkcast String` thất bại | `ClassCastException` |

Bảng giả định đúng các đối tượng thực được mô tả và không có logic validation riêng trong container.

## 6. Tại sao `List<String>[]` không được tạo trực tiếp?

Trong Java, đoạn sau là lỗi biên dịch:

```java
// List<String>[] groups = new List<String>[2]; // Generic array creation.
```

Nhưng:

```java
List<?>[] groups = new List<?>[2]; // Hợp lệ.
```

Mảng Java lưu runtime component class và kiểm tra ghi phần tử vào mảng. `List<String>` **không reifiable**: kiểu `String` bên trong không được biểu diễn như lớp runtime riêng cho `List<String>`. Cho phép `new List<String>[2]` sẽ hứa một khả năng kiểm tra mà runtime không thực hiện được.

`List<?>` dùng **unbounded wildcard** và là một reifiable type trong ngữ cảnh này. Mảng `List<?>[]` vẫn có thể chứa các danh sách với loại phần tử khác nhau, vì hợp đồng chỉ nói mỗi ô là một `List` có type argument không xác định; khi đọc qua `List<?>`, phần tử được xem là `Object`, không được giả định là `String`.

Generic varargs `List<String>...` tạo ra vấn đề liên quan: ở source, parameter trông như mảng có thành phần generic; ở bytecode, tham số array được thể hiện theo erased component `List`. Compiler cho phép khai báo varargs vì đó là cơ chế ngôn ngữ hữu ích, đồng thời cảnh báo khi không thể bảo đảm sự an toàn do phần tử không reifiable.

## 7. Phân biệt rủi ro của method, lời gọi và dữ liệu

Trong bài lab, compiler có thể cảnh báo **tại khai báo method**:

```java
static List<String>[] pollute(List<String>... groups)
```

và **tại điểm gọi**:

```java
List<String>[] groups = pollute(original);
```

Hai vị trí cảnh báo giúp bạn phát hiện rủi ro khác nhau:

- **Declaration warning:** method nhận một generic varargs array có thể gây heap pollution. Không phải bản thân chữ ký luôn đã làm sai dữ liệu, nhưng compiler không thể chứng minh từ chữ ký rằng body an toàn.
- **Invocation warning:** khi compiler phải tạo mảng varargs với component không reifiable, lời gọi mang một cấu trúc kiểu không thể kiểm tra đầy đủ ở runtime.
- **Unchecked call/conversion warning:** code có thể đã đi qua raw type hoặc cast không được xác minh, như `raw.add(42)`.

Đừng chỉ tắt cảnh báo ở nơi tiện nhất. Nếu method thuộc quyền sở hữu của bạn, đánh giá **toàn bộ thân method** và quan hệ alias của mảng varargs trước. Nếu method đến từ thư viện, đọc hợp đồng và tránh lối gọi không an toàn.

Khi một `List<String>[]` đã bị nhiễm, trả mảng ra khỏi method làm lỗi khó theo dõi hơn vì caller có thể đọc phần tử sai sau rất nhiều thao tác khác. Đặc biệt nguy hiểm khi lưu mảng varargs vào field dùng chung, trả nó qua API hoặc cung cấp nó cho mã khác sửa.

## 8. Cách viết varargs generic an toàn có chủ đích

Một phương thức chỉ duyệt các nhóm và tạo collection mới có thể tránh ô nhiễm. Ví dụ:

```java
@SafeVarargs
static <T> List<T> merge(List<? extends T>... parts) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> part : parts) {
        result.addAll(part);
    }
    return List.copyOf(result);
}
```

Mẫu này **không ghi** vào array `parts`, không cast/đánh tráo danh sách bên trong, không đưa array varargs ra ngoài để mã khác sửa. Phần tử được thêm vào `result` dưới hợp đồng `T` do compiler kiểm tra. Kết quả trả về là một danh sách mới, không phải bản thân mảng varargs.

### Khi nào được dùng `@SafeVarargs`?

`@SafeVarargs` là **cam kết của tác giả** rằng phần thực thi trên varargs kiểu non-reifiable an toàn. Java cho phép dùng trên constructor, static method, final instance method, và (từ Java 9) private instance method. Không được dùng trên instance method thường có thể override, vì một override có thể vi phạm bảo đảm mà annotation đưa ra.

Annotation:

- Giúp compiler không phát một số cảnh báo unchecked liên quan tới khai báo/lời gọi varargs mà tác giả đã chứng minh an toàn.
- **Không làm JVM lưu generic type arguments** cho mảng.
- **Không tự biến một method nguy hiểm thành an toàn**.
- Không bảo đảm loại bỏ mọi cảnh báo khác phát sinh do các thao tác unchecked thật sự trong body.

Đặc biệt, đừng đặt `@SafeVarargs` lên method `pollute` trong phần 4 chỉ để làm sạch output. Method ấy đã cố ý đặt một `List<Integer>` vào mảng mà caller tin là `List<String>[]`; annotation sẽ đưa ra lời cam kết **sai**.

## 9. Chương trình B — `@SafeVarargs` đúng cách

Tạo tệp **`SafeVarargsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... parts) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> part : parts) {
            result.addAll(part);
        }
        return List.copyOf(result);
    }

    static void showAny(List<?> items) {
        for (Object value : items) {
            System.out.println("seen: " + value);
        }
    }

    public static void main(String[] args) {
        List<String> merged = merge(List.of("An"), List.of("Binh"));
        System.out.println("merged: " + merged);
        showAny(merged);

        List<Number> nums = merge(List.of(1, 2), List.of(3.5));
        System.out.println("numbers: " + nums);
    }
}
```

Chạy:

```bash
javac -Xlint:all SafeVarargsDemo.java
java SafeVarargsDemo
```

**Stdout đã kiểm chứng:**

```text
merged: [An, Binh]
seen: An
seen: Binh
numbers: [1, 2, 3.5]
```

**Tại sao an toàn trong ví dụ này?**

1. `parts` được **đọc**, không bị thay đổi các ô của array.
2. Mọi `part` là một `List<? extends T>`: các phần tử đọc ra có thể dùng như `T`.
3. `result` là một `ArrayList<T>` hoàn toàn mới, không giữ alias tới mảng varargs.
4. Không trả mảng `parts`, không gán nó vào field, không chuyển nó cho mã không kiểm soát.
5. `List.copyOf(result)` trả một list không hỗ trợ các phép sửa đổi thông thường. Trong ví dụ này các phần tử là `String` và `Number` bất biến; `copyOf` không tự tạo immutable sâu cho phần tử mutable nếu có.

Khi gọi `merge(List.of(1, 2), List.of(3.5))` trong ngữ cảnh gán vào `List<Number>`, compiler có thể chọn `T = Number`. Các phần tử `Integer` và `Double` đều có thể được xem như `Number`, nên output hợp lệ.

**Không nên khái quát sai:** `@SafeVarargs` không tuyên bố rằng một phương thức bất kỳ có varargs generic sẽ luôn an toàn. Nó áp dụng khi **body thực sự không có thao tác phá vỡ cam kết generic**.

## 10. Lựa chọn tốt hơn khi không cần varargs

Nếu một API thường xuyên nhận collection từ caller, một chữ ký không varargs có thể diễn đạt ý định rõ hơn:

```java
static <T> List<T> copyOfItems(
        java.util.Collection<? extends T> source) {
    return List.copyOf(source);
}
```

Đây là đoạn method minh họa, cần đặt trong một class có import `java.util.List`. Nó không buộc compiler tạo generic varargs array tại lời gọi.

Hoặc nếu cần nhiều nhóm, dùng một collection chứa các nhóm:

```java
static <T> List<T> flatten(
        List<? extends List<? extends T>> groups) {
    List<T> out = new ArrayList<>();
    for (List<? extends T> group : groups) {
        out.addAll(group);
    }
    return List.copyOf(out);
}
```

Dùng `List<List<String>>` hoặc một biểu thức typed tương thích theo yêu cầu thực tế. Cách này không có array varargs ẩn và tránh một số nguy cơ alias của generic array, nhưng vẫn cần tôn trọng hợp đồng về `null`, quyền sửa collection và concurrency.

**Nguyên tắc lựa chọn:** varargs hợp lý khi API được gọi tiện bằng nhiều đối số rời và method chỉ đọc/tiêu thụ an toàn; collection parameters thường phù hợp hơn khi caller đã có danh sách động hoặc cần hợp đồng ownership rõ.

## 11. Ranh giới dữ liệu từ raw API: kiểm tra phần tử trước khi nhận `List<String>`

Trong mã legacy, không phải lúc nào bạn cũng sửa được API trả raw `List`. Thay vì:

```java
// Không nên tuyên bố dữ liệu an toàn chỉ bằng cast:
// @SuppressWarnings("unchecked")
// List<String> strings = (List<String>) legacyList;
```

hãy nhận `List<?>`, kiểm tra phần tử và tạo kết quả typed mới. Đây là cách đưa lỗi về **ranh giới dữ liệu** thay vì để lỗi xuất hiện muộn ở code nghiệp vụ.

Tạo tệp **`HeapPollutionBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionBoundaryDemo {
    static List<String> checkedStrings(List<?> input) {
        List<String> copy = new ArrayList<>();

        for (int i = 0; i < input.size(); i++) {
            Object value = input.get(i);
            if (!(value instanceof String s)) {
                throw new IllegalArgumentException(
                        "invalid element at index " + i);
            }
            copy.add(s);
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        List<?> good = List.of("A", "B");
        System.out.println("validated: " + checkedStrings(good));

        List<?> bad = List.of("A", 5);
        try {
            checkedStrings(bad);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -Xlint:all HeapPollutionBoundaryDemo.java
java HeapPollutionBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
validated: [A, B]
rejected: invalid element at index 1
```

Hàm `checkedStrings` xác nhận **mọi phần tử** là `String` trước khi trả `List<String>`. Nó không dùng unchecked cast, từ chối `null` (vì `null instanceof String` là `false`), và trả một danh sách mới, không thể bị sửa trực tiếp bằng API list thông thường.

Nếu có một danh sách legacy chứa các object của nhiều kiểu, cần thỏa thuận rõ phải **từ chối**, **chuyển đổi**, hay **bỏ qua có báo cáo** đối với phần tử sai. Cách `checkedStrings` là một chính sách fail-fast, không phải chính sách hợp lý duy nhất.

Khi hệ thống có nhiều luồng cùng sửa collection đầu vào trong lúc validate, muốn cam kết mạnh hơn cần chính sách synchronization/snapshot nhất quán; việc copy từng phần tử trong ví dụ không tự bảo đảm atomic snapshot nếu nguồn bị cập nhật đồng thời.

## 12. Cơ chế cảnh báo: bật đúng công cụ khi tìm heap pollution

Các tùy chọn compile rất hữu ích:

```bash
javac -Xlint:rawtypes -Xlint:unchecked -Xlint:varargs HeapPollutionDemo.java
```

| Nhóm | Ví dụ nhận diện | Cần kiểm tra |
| --- | --- | --- |
| `rawtypes` | `List raw` | Vì sao bỏ type argument và có thể thay bằng generic/wildcard không? |
| `unchecked` | `raw.add(42)`, generic varargs không an toàn, cast không kiểm tra | Dữ liệu có được chứng minh đúng loại không? |
| `varargs` | Thao tác có khả năng thiếu an toàn trong thân varargs method, đặc biệt khi dùng annotation | Body có leak, ghi hoặc alias mảng varargs không? |

Trên chương trình đã chạy, `javac -Xlint:all` phát hiện cả raw type, unchecked call, generic varargs declaration và generic varargs invocation. Bạn có thể dùng `-Xlint:all` trong quá trình rà soát và thu hẹp các nhóm cần theo dõi cho build pipeline sau khi hiểu nguyên nhân.

Trong code thực tế, compiler warnings có thể xuất hiện ở những nơi khác nhau tùy JDK. Không biến chính xác chuỗi văn bản/line number trong ví dụ thành quy tắc nền tảng; điều cần kiểm tra là **bản chất của đường đi dữ liệu và khả năng compiler chứng minh kiểu**.

Thứ tự ưu tiên khi sửa:

1. Không để raw type lan ra khỏi ranh giới legacy.
2. Thay unchecked cast bằng kiểm tra dữ liệu có cấu trúc khi có thể.
3. Kiểm tra mọi generic varargs method có ghi/để lộ array.
4. Cân nhắc loại bỏ varargs nếu không thật cần.
5. Chỉ dùng `@SuppressWarnings("unchecked")` trong phạm vi hẹp có giải thích chứng minh.
6. Chỉ đặt `@SafeVarargs` khi đã rà soát an toàn thân method.

## 13. Quan sát type erasure với `javap`

Sau khi biên dịch `HeapPollutionDemo.java`, chạy:

```bash
javap -s -p HeapPollutionDemo
```

Trích đoạn **đã xác minh**:

```text
static java.util.List<java.lang.String>[] pollute(
    java.util.List<java.lang.String>...);
  descriptor: ([Ljava/util/List;)[Ljava/util/List;
```

Cách đọc: ký hiệu `[` đứng trước type descriptor nghĩa là **mảng**; `Ljava/util/List;` nghĩa là đối tượng `List`. Descriptor `([Ljava/util/List;)[Ljava/util/List;` cho biết method nhận mảng `List[]` và trả mảng `List[]` ở JVM. Phần type argument `String` không xuất hiện trong descriptor — nó chỉ có thể được mô tả trong generic `Signature` metadata.

Đây là bằng chứng rõ ràng vì sao runtime component type của array varargs trong ví dụ là `java.util.List`. JVM có thể kiểm tra object được đưa vào mảng có tương thích với `List`, nhưng **không thể kiểm tra riêng đối số `String`**.

Nếu muốn quan sát thêm bytecode cast tại nơi đọc:

```bash
javap -c -p HeapPollutionDemo
```

Trong `main` có các phép đọc mà kiểu nguồn kỳ vọng `String`; compiler có thể sinh `checkcast java/lang/String`. Cách hiển thị index/offset của opcode phụ thuộc bản biên dịch, nên hãy tập trung vào **method descriptor và opcode**, không học thuộc số dòng bytecode.

## 14. Những lỗi phổ biến cần tránh

**Lỗi 1 — Nghĩ heap pollution là exception riêng.** Heap pollution là một tình trạng an toàn kiểu bị vi phạm, không phải một exception có tên tương ứng. `ClassCastException` là một hậu quả có thể xảy ra khi cast.

**Lỗi 2 — Bỏ qua cảnh báo vì chương trình vẫn chạy.** Một unchecked path có thể chạy qua nhiều test chỉ vì chưa có dữ liệu sai; rủi ro vẫn còn. Bổ sung trường hợp phần tử không phù hợp và đường đọc typed.

**Lỗi 3 — Nghĩ `@SafeVarargs` tự làm method an toàn.** Annotation không tạo runtime check mới. Nếu body viết `alias[0] = List.of(99)` thì vẫn nguy hiểm dù compiler không còn cảnh báo tại lời gọi.

**Lỗi 4 — Nhầm `List<?>[]` với `List<String>[]`.** `List<?>[]` không hứa tất cả phần tử là `List<String>`; không được cast tùy tiện rồi dựa vào đó để đọc chuỗi.

**Lỗi 5 — Cho rằng `ArrayStoreException` sẽ cứu mảng varargs generic.** Runtime array store chỉ biết component `List`, không biết type arguments của mỗi list.

**Lỗi 6 — Không phân biệt việc sửa mảng với sửa collection.** Trong ví dụ `pollute`, `alias[0]` bị thay bằng một list khác; `original` không bị chèn `99`. Khi debug, kiểm tra identity/alias của **array** và **list elements** riêng biệt.

**Lỗi 7 — Coi `List<Object>` là thay thế chung cho `List<String>`.** Generics Java invariant; `List<String>` không phải subtype của `List<Object>`. Dùng `List<?>` để đọc chưa biết kiểu, hoặc `List<T>` đúng miền dữ liệu.

**Lỗi 8 — Dùng unchecked cast cả list thay cho validation.** `(List<String>) raw` không duyệt kiểm tra mọi phần tử. Nó có thể gắn cam kết generic không đúng cho dữ liệu thực.

**Lỗi 9 — Cho rằng chỉ generic varargs mới có heap pollution.** Raw types, unchecked conversions, phản chiếu/thao tác unsafe hoặc API legacy cũng có thể dẫn đến dữ liệu không phù hợp với hợp đồng generic.

**Lỗi 10 — Để mảng varargs thoát ra ngoài scope mà không cân nhắc.** Khi mảng bị giữ trong field hoặc trả ra ngoài, mã khác có thể sửa các slot qua alias, phá cam kết generic mà người đọc phía sau đang tin cậy.

## 15. Bài luyện tập kèm đáp án

### Bài 1 — Nhận biết heap pollution

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(100);
```

**Câu hỏi:** Khi nào heap pollution có thể xảy ra? Có phải `raw.add(100)` chắc chắn ném exception không?

**Đáp án:** sau khi `Integer` đi vào danh sách mà `names` khai báo là `List<String>`, lời hứa generic đã bị vi phạm. `raw.add(100)` có thể ghi thành công với cảnh báo unchecked; lỗi có thể chỉ xuất hiện khi code đọc như `String`.

### Bài 2 — Quan hệ giữa varargs và array covariance

Một method nhận `List<String>... groups`, rồi viết `Object[] x = groups; x[0] = List.of(7)`. Vì sao không nhất thiết có `ArrayStoreException` ngay tại phép gán?

**Đáp án:** runtime component class của array là `List`; `List.of(7)` tạo đối tượng thực hiện `List`. JVM không có thông tin runtime rằng slot ấy phải là `List<String>`.

### Bài 3 — Hai lỗi khác nhau

Một `Object[]` trỏ tới `String[]` bị ghi một `Integer`; một `List<String>` bị ghi `Integer` qua raw type rồi đọc như `String`. Hai loại lỗi thường là gì?

**Đáp án:** mảng `String[]` phát `ArrayStoreException` tại phép ghi; lời đọc `List<String>` đã nhiễm thường phát `ClassCastException`.

### Bài 4 — Cần và không cần `@SafeVarargs`

Method chỉ lặp qua `List<? extends T>... items` để sao chép sang `ArrayList<T>`; không ghi hay trả mảng varargs. Có thể dùng `@SafeVarargs` trên static method đó không?

**Đáp án:** có, nếu tác giả xác minh body không tạo heap pollution/để lộ array. Không nên dùng annotation cho method ghi dữ liệu không phù hợp vào varargs array.

### Bài 5 — Hai nhóm cảnh báo

`-Xlint:rawtypes` và `-Xlint:unchecked` khác nhau như thế nào?

**Đáp án:** `rawtypes` phát hiện kiểu generic được dùng mà không có đối số kiểu (`List raw`), còn `unchecked` phát hiện những thao tác generic không thể kiểm tra đầy đủ (`raw.add(42)`, cast, hoặc generic varargs).

### Bài 6 — Vì sao `List<?>[]` tạo được?

`new List<?>[2]` hợp lệ trong khi `new List<String>[2]` không hợp lệ. Vì sao?

**Đáp án:** `List<?>` với unbounded wildcard là dạng reifiable cho mục đích tạo array, không khẳng định phần tử generic cụ thể. `List<String>` không reifiable nên không thể là component type của một mảng được tạo trực tiếp bằng cú pháp đó.

### Bài 7 — Tạo adapter từ raw API

Một legacy `List` có thể chứa `String`, `Integer`, `null`; bạn cần API trả `List<String>`. Có nên dùng `(List<String>) raw` rồi `@SuppressWarnings` không?

**Đáp án:** không thể coi cast là validation. Nhận dạng `List<?>`, kiểm tra từng phần tử, chọn cách xử lý sai kiểu/`null`, rồi tạo danh sách typed mới như `checkedStrings`.

### Bài 8 — Dùng `javap` để kiểm chứng

Với `static List<String>[] pollute(List<String>... groups)`, descriptor có `String` hay chỉ `List[]`?

**Đáp án:** descriptor dùng `List[]` ở tham số và kết quả: `([Ljava/util/List;)[Ljava/util/List;`. Generic `String` có thể hiện trong Signature metadata, không thuộc descriptor runtime.

## 16. Checklist tự đánh giá

Bạn nên có thể tự giải thích:

1. Heap pollution là gì và vì sao không đồng nghĩa cảnh báo unchecked hoặc một exception.
2. Raw `List` có thể làm hỏng dữ liệu mà biến `List<String>` vẫn đang tham chiếu.
3. Generic varargs được truyền bằng một array runtime có component type bị xóa thành `List`.
4. `Object[]` alias có thể ghi `List<Integer>` vào varargs array mà runtime không kiểm tra `String`.
5. `ClassCastException` có thể xuất hiện muộn tại lời đọc typed; `ArrayStoreException` thuộc cơ chế kiểm tra phần tử mảng thực.
6. `@SafeVarargs` là một cam kết cần được chứng minh, không phải công tắc sửa lỗi an toàn kiểu.
7. `List<?>[]` khác `List<String>[]` ở mức cam kết và khả năng tạo mảng.
8. Đường nâng cấp an toàn là bỏ raw type không cần thiết, kiểm tra dữ liệu ở boundary, giới hạn unchecked casts và tránh thao tác nguy hiểm trên mảng varargs.
9. `javap -s` và `-c` cung cấp bằng chứng về erasure và cast phát sinh ở bytecode.

## Kết luận

**Heap pollution** là khi cam kết của một kiểu tham số hóa không còn phản ánh đúng đối tượng được tham chiếu. Với generic varargs, nguyên nhân đáng chú ý là **mảng runtime chỉ biết component type đã bị xóa**, nên việc ghi một list sai type argument qua `Object[]` có thể lọt qua kiểm tra store. Phép cast khi đọc với kỳ vọng `String` sau đó gây `ClassCastException`.

Hãy dùng generics typed thay raw type, tránh để lộ/sửa array varargs, chỉ áp dụng `@SafeVarargs` sau khi chứng minh body an toàn, và kiểm tra phần tử từ nguồn không đáng tin trước khi công bố `List<String>`. Như vậy Java generics tiếp tục phát huy bảo vệ kiểu ngay từ compiler thay vì đẩy lỗi về runtime.
