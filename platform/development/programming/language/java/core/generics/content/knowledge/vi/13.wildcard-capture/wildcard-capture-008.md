# Phân biệt giải quyết lỗi bằng capture với ép kiểu không kiểm tra trong Java Generics

Trong Java Generics, khi trình biên dịch báo lỗi liên quan đến `capture of ?`, có hai hướng xử lý rất khác nhau:

- **Wildcard capture và generic helper**: giúp trình biên dịch **chứng minh** một thao tác thực sự an toàn về kiểu, thường là lấy phần tử từ một collection rồi dùng lại với **chính collection có cùng kiểu phần tử ẩn**.
- **Unchecked cast**: yêu cầu trình biên dịch **tin vào khẳng định của lập trình viên** mà không thể kiểm tra đầy đủ đối số kiểu generic. Mã có thể biên dịch, nhưng giả định sai có thể gây **heap pollution** và `ClassCastException` khi chạy.

Hai kỹ thuật không tương đương. Một lời gọi generic helper dựa trên capture giữ được kiểm tra kiểu tại thời điểm biên dịch; một ép kiểu không kiểm tra có thể vượt qua chốt kiểm tra đó. Đây là sự khác biệt về **bằng chứng an toàn kiểu**, chứ không chỉ khác cú pháp hoặc có/không có cảnh báo.

## 1. Tình huống xuất phát: `List<?>` và kiểu phần tử chưa biết

Giả sử cần viết một phương thức hoán đổi hai vị trí trong một danh sách có kiểu phần tử bất kỳ:

```java
static void swapWrong(List<?> list, int i, int j) {
    Object saved = list.get(i);
    // list.set(i, list.get(j)); // LỖI BIÊN DỊCH.
    // list.set(j, saved);       // LỖI BIÊN DỊCH.
}
```

Đây là **đoạn minh họa lỗi**, không phải chương trình chạy độc lập. `List<?>` có nghĩa danh sách chứa **một kiểu phần tử nào đó chưa biết**. Khi đọc qua wildcard không giới hạn, giá trị có thể dùng như `Object`; nhưng `set` đòi giá trị đúng **kiểu phần tử ẩn** của danh sách.

Thử viết trực tiếp cũng không được:

```java
static void stillWrong(List<?> list) {
    // list.set(0, list.get(0)); // LỖI BIÊN DỊCH.
}
```

Dù thao tác đặt lại chính phần tử đang có là an toàn về ý tưởng, các lần sử dụng biểu thức mang wildcard không được tự động thống nhất thành một tên kiểu `T` chung trong lời gọi `set`. `javac` có thể báo `capture#1 of ?` hoặc `Object cannot be converted to capture#...`. Số thứ tự của capture trong thông báo không phải API ổn định.

Có thể xử lý lỗi này bằng **generic helper** mà không cần ép kiểu.

## 2. Giải bằng generic helper: giữ quan hệ kiểu, không giả mạo type argument

Khi muốn **nhân bản phần tử đầu trong chính một list**, API ngoài có thể nhận `List<?>`, còn helper dùng một type parameter:

```java
static void duplicateFirst(List<?> values) {
    duplicateCaptured(values);
}

private static <T> void duplicateCaptured(List<T> values) {
    if (!values.isEmpty()) {
        T value = values.get(0);
        values.add(value);
    }
}
```

Đây là các method minh họa cần import `java.util.List` và đặt trong class. Ở lời gọi helper, compiler capture `?` từ **một list cụ thể** và suy luận `T`; kết quả `get(0)` và tham số của `add` cùng dùng `T`. Không có phép cast giả định kiểu phần tử là `Object` hay `String`.

So sánh với một hướng làm sai:

```java
// KHÔNG dùng khi chưa chứng minh generic element type:
@SuppressWarnings("unchecked")
static void unsafeInsert(List<?> list) {
    List<String> forged = (List<String>) list;
    forged.add("not necessarily the right type");
}
```

Cast chỉ kiểm tra raw runtime `List`, không chứng minh mọi phần tử vốn là `String`. Nó có thể làm ô nhiễm `List<Integer>` rồi ném `ClassCastException` ở một lần đọc khác. **Generic helper bảo toàn một quan hệ kiểu đã có; unchecked cast tự khẳng định một quan hệ chưa được chứng minh.**

`duplicateFirst` vẫn cần list mutable; với `List.of` có thể có `UnsupportedOperationException`. Nếu cần thay hai phần tử, `Collections.swap` hoặc helper capture tương tự đều phù hợp. Điểm kiểm tra trong bài này là **chỗ nào có type proof và chỗ nào chỉ che cảnh báo**, không phải cài đặt swap.

## 3. Unchecked cast là gì và tại sao nguy hiểm?

**Unchecked cast** là phép ép kiểu mà JVM không thể kiểm tra đầy đủ đối số kiểu generic, ví dụ từ `List<?>` thành `List<String>`:

```java
static List<String> trustMe(List<?> source) {
    return (List<String>) source; // Unchecked cast warning.
}
```

Đoạn mã trên **biên dịch nhưng sinh cảnh báo unchecked** (nếu không bị tắt cảnh báo). Bởi **type erasure**, đối số `<String>` của `List<String>` thường không được kiểm tra ở runtime. JVM có thể xác minh đối tượng là một `List`, nhưng không có bằng chứng mọi phần tử trong đó là `String`.

Hãy xét:

```java
List<Integer> integers = new ArrayList<>(List.of(7, 8));
List<?> unknown = integers;
List<String> strings = (List<String>) unknown; // Cảnh báo unchecked.

String s = strings.get(0); // ClassCastException khi chạy.
```

Phép cast ở dòng thứ ba thường **không ném** `ClassCastException` vì đối tượng thật là một `List`. Lỗi xuất hiện tại `strings.get(0)` khi kết quả đọc được coi là `String` và runtime cast cần thiết phát hiện giá trị thực là `Integer`.

Tính an toàn kiểu đã mất: biến có kiểu biên dịch `List<String>` thực chất tham chiếu một danh sách được tạo và sử dụng như `List<Integer>`.

Điểm quan trọng:

- **Capture helper** dùng đúng biến kiểu `T` do compiler chứng minh; không đòi người dùng khẳng định `T` là kiểu cụ thể nào.
- **Unchecked cast** tự khẳng định đối số kiểu là `String` hoặc một kiểu khác mà compiler không đủ thông tin để xác minh.
- Type erasure **không làm cast trở nên an toàn**; nó chính là một lý do phép kiểm tra tham số generic không thể hoàn tất tại runtime.
- Việc chương trình chưa phát sinh `ClassCastException` ngay lập tức **không chứng minh** cast là đúng.

Không nên đánh đồng unchecked cast với một ép kiểu runtime thông thường như `Object o = "x"; String s = (String) o;`: ép kiểu từ `Object` sang `String` có kiểm tra kiểu thực ở runtime. Với `List<String>`, phần đối số kiểu `<String>` không được kiểm tra đầy đủ.

## 4. So sánh bản chất của hai cách xử lý

| Tiêu chí | Capture + generic helper | Unchecked cast |
| --- | --- | --- |
| Mục đích | Đặt tên một kiểu ẩn và bảo toàn quan hệ kiểu đã tồn tại | Khẳng định một kiểu tham số hóa mà compiler không kiểm chứng đầy đủ |
| Ví dụ | `<T> void swapCaptured(List<T>)` | `(List<String>) someListOfUnknownElementType` |
| Cần biết kiểu thực là `String`/`Integer`? | Không | Thường phải **giả định** hoặc xác minh bằng cách khác |
| Kiểm tra an toàn kiểu | Compiler chứng minh các thao tác trên `T` | Kiểm tra đối số generic có thể thiếu |
| Cảnh báo `unchecked` | Không, nếu helper được viết đúng | Thường có |
| Nguy cơ heap pollution do chính kỹ thuật | Không tạo ra khi dùng đúng | Có, nếu giả định sai |
| Thất bại runtime | Vẫn có thể do chỉ số, mutable, null, v.v. | Ngoài các lỗi thường gặp còn có `ClassCastException` do giả định kiểu sai |
| Dùng tốt nhất | Thao tác nội bộ với một wildcard hoặc ràng buộc kiểu rõ ràng | Chỉ ở ranh giới dữ liệu đã được chứng minh bởi hợp đồng ngoài hệ kiểu |

**Kết luận sử dụng:** trước một lỗi `capture of ?`, kiểm tra liệu có thể viết helper `<T>` nhận một tham số kiểu cụ thể và giữ nguyên quan hệ kiểu trong thân phương thức hay không. Một cast chỉ để compiler im lặng không phải lời giải thích cho tính đúng đắn.

## 5. Minh họa heap pollution: ghi sai kiểu qua raw type

**Heap pollution** xảy ra khi một biến thuộc kiểu tham số hóa tham chiếu đối tượng không phù hợp với kiểu tham số hóa mà biến đó tuyên bố. Unchecked cast và raw type là những con đường có thể tạo điều kiện cho vấn đề này.

Ví dụ rủi ro, **không dùng trong code ứng dụng**:

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static void pollute(List<Integer> numbers) {
    List raw = numbers;
    raw.add("wrong"); // Bỏ qua kiểm tra phần tử Integer.
}

static void caller() {
    List<Integer> numbers = new ArrayList<>(List.of(10));
    pollute(numbers);

    Integer value = numbers.get(1); // ClassCastException khi chạy.
}
```

Hệ kiểu `List<Integer>` yêu cầu mọi phần tử được lấy ra dưới dạng `Integer`. Nhưng raw reference cho phép thêm một `String`. Lúc `get(1)` được dùng làm `Integer`, runtime cast do compiler sinh ra có thể phát hiện sai kiểu và ném `ClassCastException`.

Một cách rủi ro tương tự là ép `List<?>` sang `List<String>` rồi tiếp tục thêm phần tử `String` vào danh sách thật `List<Integer>`. Lần đọc dưới dạng `Integer` ở phía chủ sở hữu có thể thất bại về sau, rất xa nơi thực hiện unchecked cast.

Không phải mọi unchecked cast đều tức khắc làm hỏng nội dung danh sách. Nhưng nó mở ra khả năng sai kiểu vì **lời hứa của kiểu tham số hóa chưa được xác minh**.

## 6. Vì sao `@SuppressWarnings("unchecked")` không phải giải pháp?

Ví dụ:

```java
@SuppressWarnings("unchecked")
static List<String> uncheckedStrings(List<?> source) {
    return (List<String>) source;
}
```

Annotation `@SuppressWarnings("unchecked")` chỉ **ẩn cảnh báo của compiler trong phạm vi được áp dụng**. Nó không:

- Kiểm tra các phần tử của `source`.
- Biến `Integer` thành `String`.
- Thêm kiểm tra generic bị thiếu vào bytecode.
- Ngăn `ClassCastException` hoặc heap pollution.
- Tạo ra quan hệ capture giữa hai kiểu wildcard khác nhau.

Nếu thật sự có một hợp đồng ngoài hệ kiểu bảo đảm cast đúng, hãy đặt annotation ở **phạm vi nhỏ nhất**, ghi rõ nguồn bảo đảm, kiểm tra ranh giới nếu có thể, và không để kiểu sai lan rộng.

Ví dụ một phương thức thư viện cũ trả về raw `List` có thể cần xử lý tương thích. Nhưng đó là bài toán **tin cậy dữ liệu legacy**, không phải lý do dùng unchecked cast để sửa lỗi có thể giải quyết bằng generic helper.

## 7. Cách an toàn khi cần một danh sách có kiểu cụ thể: kiểm tra phần tử và sao chép

Khi thực sự phải chuyển từ `List<?>` sang `List<String>`, capture không thể chứng minh rằng mọi phần tử đều là `String`: wildcard có thể biểu thị `Integer`, `Double` hoặc kiểu khác. Có thể kiểm tra **từng phần tử tại runtime** bằng `Class.cast` và xây một danh sách mới:

```java
static <T> List<T> checkedCopy(
        List<?> source, Class<T> elementType) {
    List<T> destination = new ArrayList<>();
    for (Object item : source) {
        destination.add(elementType.cast(item));
    }
    return destination;
}
```

Ví dụ sử dụng (các import thuộc `java.util`):

```java
List<?> unknown = List.of("a", "b");
List<String> strings = checkedCopy(unknown, String.class);
System.out.println(strings); // [a, b]
```

Nếu gọi `checkedCopy(List.of(1, 2), String.class)`, nó ném `ClassCastException` **trong lúc kiểm tra phần tử**; không trả về một `List<String>` sai kiểu.

Đây là một kỹ thuật khác với capture helper:

- `checkedCopy` **có kiểm tra runtime theo `Class<T>`** rồi tạo collection mới.
- `swapCaptured` **không kiểm tra runtime để đoán `T`**; compiler giữ quan hệ phần tử trong cùng collection.
- `Class<T>` ở ví dụ nhận các lớp có reifiable runtime class token như `String.class`. Không thể có `List<String>.class` để kiểm tra đệ quy một cấu trúc generic bất kỳ bằng `Class.cast`.
- `Class.cast(null)` trả về `null`, nên một nguồn chứa null có thể được sao chép với phần tử null. Việc collection đích cho phép null phụ thuộc implementation; `ArrayList` trong ví dụ cho phép.

Nếu không cần tạo collection mới, có thể **kiểm tra từng phần tử tại ranh giới sử dụng** bằng `instanceof`/`Class.cast` mà không cast cả danh sách thành một kiểu tham số hóa cụ thể. Chi phí kiểm tra và sao chép được đánh đổi để lấy an toàn kiểu rõ ràng khi xử lý dữ liệu không tin cậy.

## 8. Capture chỉ giải quyết quan hệ kiểu có thật

Giả sử hai danh sách được khai báo:

```java
List<?> left = List.of(1, 2);
List<?> right = List.of("a", "b");
```

Không có phép chuyển phần tử tổng quát an toàn từ `right` sang `left`:

```java
static void copyUnknown(List<?> target, List<?> source) {
    // target.add(source.get(0)); // LỖI BIÊN DỊCH.
}
```

Một helper nhận hai `List<T>` cũng **không** giải quyết được khi chỉ có hai đối số wildcard độc lập:

```java
static <T> void requiresSameType(List<T> a, List<T> b) {
    a.addAll(b);
}

static void fails(List<?> a, List<?> b) {
    // requiresSameType(a, b); // LỖI BIÊN DỊCH.
}
```

Hai dấu `?` có thể ứng với hai kiểu khác nhau. Compiler không có bằng chứng rằng một `T` duy nhất phù hợp với cả hai tham số `List<T>`. Thậm chí truyền cùng một biến `List<?>` hai lần cho hai tham số `List<T>` cũng có thể bị từ chối do các capture tại từng vị trí đối số là độc lập.

**Không được sửa bằng**:

```java
@SuppressWarnings("unchecked")
static void fakeCopy(List<?> target, List<?> source) {
    List<Object> forgedTarget = (List<Object>) target;
    forgedTarget.addAll(source); // Có thể chèn String vào List<Integer>.
}
```

Đoạn mã này chỉ minh họa hướng làm sai. Ép `List<?>` thành `List<Object>` không chứng minh rằng `target` là danh sách dành cho mọi loại `Object`. Nó có thể phá hợp đồng phần tử của danh sách thật.

Khi dữ liệu nguồn–đích có quan hệ kiểu xác định, hãy **thể hiện quan hệ ngay trong chữ ký**:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    destination.addAll(source);
}
```

`source` cung cấp giá trị dùng được như `T`, `destination` chấp nhận `T`. Đây là ứng dụng **Producer Extends, Consumer Super (PECS)**. Ví dụ `List<Integer>` có thể là nguồn cho `List<Number>`, không cần unchecked cast. Nếu hai loại phần tử không có quan hệ phù hợp, lời gọi bị từ chối như mong muốn.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sau chạy được với JDK 17 trở lên. Nó thể hiện ba hành vi khác nhau:

1. **Capture helper:** hoán đổi và lặp lại phần tử trong một danh sách mà vẫn an toàn kiểu.
2. **Generic nguồn–đích:** chuyển các `Integer` sang đích `List<Number>` có quan hệ kiểu hợp lệ.
3. **Unchecked cast/raw:** giả định sai hoặc ghi sai kiểu dẫn tới `ClassCastException`. Hai ngoại lệ được bắt để chương trình minh họa vẫn hoàn tất.

Lưu thành tệp **`CaptureVsCastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureVsCastDemo {
    static void swap(List<?> list, int i, int j) {
        swapCaptured(list, i, j);
    }

    private static <T> void swapCaptured(List<T> list, int i, int j) {
        T old = list.get(i);
        list.set(i, list.get(j));
        list.set(j, old);
    }

    static void duplicateFirst(List<?> list) {
        duplicateCaptured(list);
    }

    private static <T> void duplicateCaptured(List<T> list) {
        if (!list.isEmpty()) {
            list.add(list.get(0));
        }
    }

    static <T> void appendAll(
            List<? extends T> src, List<? super T> dst) {
        dst.addAll(src);
    }

    @SuppressWarnings("unchecked")
    static List<String> uncheckedStrings(List<?> list) {
        return (List<String>) list;
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void pollute(List<Integer> integers) {
        List raw = integers;
        raw.add("wrong");
    }

    public static void main(String[] args) {
        List<Integer> ints = new ArrayList<>(List.of(1, 2, 3));
        swap(ints, 0, 2);
        duplicateFirst(ints);
        System.out.println("ints = " + ints);

        List<String> words = new ArrayList<>(List.of("a", "b"));
        swap(words, 0, 1);
        System.out.println("words = " + words);

        List<Number> numbers = new ArrayList<>();
        appendAll(ints, numbers);
        System.out.println("numbers = " + numbers);

        List<String> forged = uncheckedStrings(ints);
        try {
            String value = forged.get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println(
                    "unchecked read: " + ex.getClass().getSimpleName());
        }

        List<Integer> polluted = new ArrayList<>(List.of(10));
        pollute(polluted);
        try {
            Integer value = polluted.get(1);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println(
                    "raw write: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CaptureVsCastDemo.java
java CaptureVsCastDemo
```

Stdout chính xác:

```text
ints = [3, 2, 1, 3]
words = [b, a]
numbers = [3, 2, 1, 3]
unchecked read: ClassCastException
raw write: ClassCastException
```

Giải thích kết quả:

- Hai danh sách đầu tiên được hoán đổi thành công bằng capture helper, không có chèn phần tử sai kiểu.
- `duplicateFirst` đọc phần tử đầu và thêm lại **chính kiểu đó** thông qua helper `List<T>`, nên `ints` thành `[3, 2, 1, 3]`.
- `appendAll` truyền các `Integer` sang `List<Number>` nhờ giới hạn `extends/super`.
- `uncheckedStrings(ints)` không xác minh các phần tử thuộc `String`; lỗi bộc lộ khi đọc kết quả dưới dạng `String`.
- `pollute` dùng raw type để thêm `String` vào `List<Integer>`; lần đọc dưới dạng `Integer` thất bại.

Các hàm `uncheckedStrings` và `pollute` chỉ dùng để **chứng minh hậu quả của code không an toàn**. Không sao chép chúng vào code sản phẩm như một giải pháp sửa lỗi generics.

### Kiểm chứng cách sao chép có kiểm tra kiểu

Nếu cần chuyển dữ liệu từ một `List<?>` không tin cậy thành danh sách phần tử `String`, có thể dùng chương trình độc lập sau.

Lưu thành **`CheckedCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedCopyDemo {
    static <T> List<T> checkedCopy(
            List<?> source, Class<T> elementType) {
        List<T> result = new ArrayList<>();
        for (Object item : source) {
            result.add(elementType.cast(item));
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> strings = List.of("a", "b");
        System.out.println(
                "verified = " + checkedCopy(strings, String.class));

        try {
            checkedCopy(List.of(1, 2), String.class);
        } catch (ClassCastException ex) {
            System.out.println(
                    "checked mismatch: " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac CheckedCopyDemo.java
java CheckedCopyDemo
```

Stdout:

```text
verified = [a, b]
checked mismatch: ClassCastException
```

Sự khác biệt nằm ở vị trí kiểm tra: `checkedCopy` xác minh ngay khi nhận từng phần tử, còn unchecked cast toàn bộ `List<?>` có thể tạo ra một tham chiếu sai kiểu và chỉ lỗi muộn khi đọc hoặc sử dụng dữ liệu.

## 10. Quy trình quyết định khi gặp lỗi generics

Khi gặp thông báo `incompatible types` hoặc `capture#... of ?`, hãy đi theo các bước sau.

### Bước 1: Xác định thao tác đọc hay ghi

`List<?>` đọc ra `Object` an toàn, nhưng không cho phép thêm giá trị không-null tùy ý. `List<? extends Number>` cho đọc như `Number`; `List<? super Integer>` cho thêm `Integer` nhưng đọc chung như `Object`.

Nếu chỉ cần đọc, có thể không cần helper:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

### Bước 2: Kiểm tra có một kiểu ẩn cần duy trì xuyên suốt không

Một thao tác cần lấy rồi đặt lại phần tử **trong cùng danh sách** thường là trường hợp phù hợp với `<T> void helper(List<T>)`. Giá trị đọc từ `List<T>` có đúng kiểu `T` để đưa lại vào chính danh sách ấy.

Không dùng cast chỉ vì không biết tên `T`. Một helper có thể giữ thông tin mà compiler đã có nhưng chưa thể biểu diễn qua wildcard ngoài.

### Bước 3: Kiểm tra có nhiều wildcard độc lập không

Nếu một phương thức nhận `List<?> a` và `List<?> b`, chúng **có thể có hai kiểu khác nhau**. Capture không chứng minh chúng bằng nhau. Hãy xem nguồn và đích có một quan hệ `<T>` thực sự hay không, và thể hiện bằng `? extends T`/`? super T` khi thích hợp.

### Bước 4: Nếu thật sự cần kiểu cụ thể, kiểm tra tại ranh giới

Một API muốn `List<String>` từ dữ liệu không xác định phải có bằng chứng nguồn đúng kiểu. Có thể kiểm tra từng phần tử, sao chép và tạo danh sách đã xác minh. Tránh khẳng định cả danh sách chỉ bằng `(List<String>) source`.

### Bước 5: Chỉ dùng unchecked cast khi có lý do kiểm chứng được

Tích hợp raw API cũ có thể buộc phải cast không kiểm tra. Khi đó nên:

- Xác định rõ **hợp đồng bên ngoài nào bảo đảm kiểu phần tử**.
- Thu hẹp vùng chứa raw type/unchecked cast và dùng `@SuppressWarnings("unchecked")` chỉ sát lời gọi cần thiết.
- Xác minh dữ liệu nếu hợp đồng không thể tin cậy.
- Không trả tham chiếu có kiểu khai báo sai ra phần còn lại của chương trình.
- Kiểm tra đường đọc và đường ghi, vì lỗi có thể phát sinh muộn và không ở dòng cast.

Cảnh báo unchecked là thông tin hữu ích của compiler; loại bỏ cảnh báo bằng annotation không thay cho phân tích an toàn kiểu.

## 11. Các hiểu lầm phổ biến

### “Capture conversion chính là một kiểu cast”

**Sai.** Capture đưa wildcard thành biến kiểu ẩn để compiler giải quyết ràng buộc; không có ép kiểu runtime từ `Integer` sang `String` và không biến tham số kiểu của danh sách thật. Một unchecked cast khẳng định một kiểu tham số hóa mới mà compiler chưa chứng minh được.

### “Ép sang `List<Object>` an toàn vì mọi đối tượng là `Object`”

**Sai.** `Integer` là `Object` nhưng `List<Integer>` không phải `List<Object>`. Nếu danh sách vốn chỉ cho phép `Integer`, tham chiếu giả dạng `List<Object>` có thể thêm `String` hoặc kiểu khác và làm hỏng hợp đồng generic.

### “Không có `ClassCastException` ngay dòng cast tức là cast đúng”

**Sai.** Type erasure khiến đối số `<String>` trong `List<String>` không thể được kiểm tra như một lớp runtime đầy đủ. Lỗi có thể xuất hiện khi đọc phần tử, khi gán kết quả sang kiểu cụ thể, hoặc sau một lần ghi gây heap pollution.

### “Dùng cùng một `List<?>` hai lần là đủ để suy ra hai `T` bằng nhau”

**Không chắc.** Mỗi lần capture của biểu thức wildcard có thể được xử lý độc lập. Một helper `<T> void helper(List<T>)` dùng **một tham số** giữ được một `T` trong thân phương thức; helper `<T> void helper(List<T>, List<T>)` có thể không nhận được hai biểu thức `List<?>` dù cùng tham chiếu ban đầu.

### “`@SuppressWarnings` làm cast được kiểm tra”

**Sai.** Annotation chỉ ảnh hưởng chẩn đoán của trình biên dịch. Nó không tạo kiểm tra phần tử ở runtime, không khôi phục đối số kiểu đã bị erasure, và không sửa heap pollution.

### “Capture helper bảo đảm chương trình không thể lỗi runtime”

**Sai.** Capture đảm bảo quan hệ kiểu trong thao tác generic, nhưng chỉ số sai vẫn có thể gây `IndexOutOfBoundsException`, danh sách bất biến có thể gây `UnsupportedOperationException`, và dữ liệu đã bị làm ô nhiễm từ raw code khác có thể gây `ClassCastException`.

### “Thêm generic helper là đủ để di chuyển mọi phần tử giữa hai `List<?>`”

**Sai.** Hai wildcard có thể khác kiểu thật. Cần hợp đồng quan hệ giữa source/destination; nếu không có quan hệ đó, việc ép kiểu để di chuyển phần tử chỉ che giấu rủi ro.

## 12. Bài tập tự kiểm tra

Cho:

```java
List<Integer> ids = new ArrayList<>(List.of(1, 2));
List<?> unknown = ids;
```

Hãy đánh giá:

| Biểu thức/hướng xử lý | Kết quả | Giải thích |
| --- | --- | --- |
| `Object x = unknown.get(0)` | Hợp lệ | Đọc wildcard không giới hạn thành `Object` |
| `unknown.add("a")` | Lỗi biên dịch | Không biết kiểu phần tử thật |
| `unknown.set(0, unknown.get(0))` | Lỗi biên dịch | Kiểu capture của thao tác ghi chưa được nối với giá trị đọc |
| `swap(unknown, 0, 1)` với generic helper | Hợp lệ | Capture vào một `List<T>` giúp đọc/ghi cùng `T` |
| `List<String> bad = (List<String>) unknown` | Có thể biên dịch với cảnh báo unchecked | Không chứng minh được phần tử là `String` |
| `String s = bad.get(0)` với danh sách `ids` ban đầu | `ClassCastException` khi chạy | Phần tử thật là `Integer` |
| `@SuppressWarnings("unchecked")` trên cast | Không sửa an toàn kiểu | Chỉ ẩn cảnh báo |
| `checkedCopy(unknown, Integer.class)` | Hợp lệ, trả bản sao `List<Integer>` | Kiểm tra runtime từng phần tử |
| `checkedCopy(unknown, String.class)` | `ClassCastException` ở bước chuyển | Phần tử thực không phải `String` |

Câu về `set/get` là minh họa lỗi compile-time theo cách viết trực tiếp; helper cho phép thao tác tương đương với một `T` dùng nhất quán. Các lời gọi `get(0)` còn yêu cầu danh sách không rỗng khi chạy.

## Ghi nhớ

- **Capture + generic helper** giúp compiler giữ một kiểu ẩn nhất quán khi thao tác trên cùng dữ liệu generic; đây là cách sửa lỗi an toàn khi quan hệ kiểu đã có thật.
- **Unchecked cast** tuyên bố một đối số kiểu mà compiler không thể kiểm tra đầy đủ; giả định sai có thể gây heap pollution và `ClassCastException`.
- **`@SuppressWarnings("unchecked")` chỉ ẩn cảnh báo**, không nâng mức an toàn của cast.
- Capture không làm hai wildcard độc lập thành cùng kiểu; khi cần dữ liệu đi giữa nguồn và đích, hãy diễn đạt quan hệ kiểu bằng `<T>`, `? extends T` và `? super T`.
- Nếu không biết kiểu phần tử nhưng API thật sự cần một danh sách kiểu cụ thể, hãy xác minh phần tử tại runtime hoặc dựa trên hợp đồng dữ liệu được chứng minh, thay vì cast mù.
- **Thông báo `capture of ?` là lời nhắc xem lại quan hệ kiểu**, không phải chỉ dẫn thêm một cast.

Một thiết kế generics tốt làm cho thao tác an toàn được **chứng minh bởi chữ ký và compiler**. Khi phải vượt qua ranh giới hệ kiểu, lập trình viên cần chứng cứ cụ thể hoặc kiểm tra runtime phù hợp, đồng thời giới hạn nơi chứa giả định không được compiler xác nhận.
