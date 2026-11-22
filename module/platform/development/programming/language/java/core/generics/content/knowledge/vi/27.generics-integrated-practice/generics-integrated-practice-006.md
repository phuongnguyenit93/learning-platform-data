# Tái hiện raw type và heap pollution rồi sửa tại nguồn trong Java Generics

## 1. Mục tiêu của bài thực hành

Java Generics giúp compiler ngăn một `List<String>` nhận nhầm `Integer`, nhưng sự bảo đảm đó có thể bị phá vỡ khi chương trình dùng **raw type**, cast không được kiểm chứng, generic varargs không an toàn, hoặc truyền dữ liệu qua các API legacy không còn thông tin generic đầy đủ.

Hiện tượng **heap pollution** xảy ra khi một biến có kiểu tham số hóa trỏ tới một đối tượng không thỏa kiểu tham số hóa được kỳ vọng. Trong ví dụ trọng tâm, biến được khai báo `List<String>` nhưng chính danh sách ấy lại chứa một `Integer` sau khi có code gọi `add` thông qua tham chiếu raw `List`.

Bài này tập trung vào **thực hành tái hiện → đọc cảnh báo và lỗi → truy ra điểm gây ô nhiễm → sửa tại nguồn → kiểm tra không tái phát**, thay vì chỉ đặt `@SuppressWarnings` quanh các cảnh báo.

Bạn sẽ học cách:

- Phân biệt `List` raw, `List<Object>`, `List<?>` và `List<String>`.
- Tái hiện việc ghi Integer vào một danh sách có hợp đồng String qua raw alias.
- Giải thích tại sao câu lệnh ghi có thể chạy xong nhưng `ClassCastException` lại xảy ra **ở phía đọc**.
- Bật `-Xlint:rawtypes,unchecked` và hiểu các cảnh báo nào cần sửa ở dòng nào.
- Viết lại một API legacy thành generic method với kiểu đúng ngay ở điểm thêm phần tử.
- Xây dựng ranh giới kiểm tra dữ liệu `List<?>` trước khi chuyển sang `List<String>`.
- Dùng `Class<T>.cast` và `Collections.checkedList` đúng phạm vi, biết rõ những giới hạn của chúng.
- Tái hiện một trường hợp heap pollution khác liên quan đến generic varargs.
- Kiểm tra code Java 17 hợp lệ, phân biệt compile error, compiler warning và runtime exception.

## 2. Từ generic safety đến lỗ hổng do raw type

Trong mã typed bình thường:

```java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
// names.add(42); // Không biên dịch.
```

Compiler biết method `List<String>.add` yêu cầu String. Nếu cố truyền 42, compiler sẽ không cho build. Đây là chỗ generic type checking có giá trị nhất: lỗi bị ngăn **ngay tại điểm ghi**.

Nhưng Java còn hỗ trợ **raw type** để tương thích với mã trước Java 5:

```java
List raw = names;
raw.add(42);
```

Raw `List` không khai báo type argument, làm compiler mất thông tin về kiểu phần tử ở tham chiếu `raw`. Lời gọi `raw.add(42)` có thể được chấp nhận **kèm cảnh báo unchecked**, trong khi object thực vẫn là đúng `ArrayList` mà `names` đang tham chiếu. Sau lời gọi, `names` có thể chứa một Integer không phù hợp với `List<String>`.

Đây không phải do Java tạo hai danh sách khác nhau. Hai biến `names` và `raw` là **hai alias** tới cùng object. Không có bản sao tự sinh khi bạn gán `List raw = names`.

### Những kiểu dễ nhầm

| Kiểu tham chiếu | Ý nghĩa | Khả năng ghi/đọc |
| --- | --- | --- |
| `List<String>` | Hợp đồng phần tử là String. | `add(String)` được; `get` được nhìn nhận là String. |
| `List<Object>` | Hợp đồng cho phép phần tử Object. | Có thể thêm String, Integer và Object theo API; không tự nhận phép gán từ `List<String>`. |
| `List<?>` | Có một kiểu phần tử chưa biết. | Đọc an toàn dưới Object; không thêm một giá trị non-null tùy ý. |
| `List` raw | Bỏ type argument của giao diện generic. | Có thể gọi `add(42)` với cảnh báo unchecked; dễ phá hợp đồng của alias typed khác. |

**`List<Object>` không phải cách viết mới của raw `List`.** `List<Object>` vẫn là một parameterized type được compiler kiểm tra. `List<?>` cũng không phải raw: nó giữ ràng buộc rằng kiểu phần tử tồn tại nhưng chưa biết, và ngăn thao tác ghi thiếu bằng chứng.

Một ví dụ:

```java
List<String> names = new ArrayList<>();
List<?> view = names;
Object item = view.isEmpty() ? null : view.get(0);

// view.add(42); // Không biên dịch.
```

`List<?>` là một view **không thể thêm giá trị non-null tùy ý theo kiểu tĩnh**, nhưng không có nghĩa collection tự trở thành immutable. Nếu một alias typed khác sửa được danh sách, view sẽ quan sát nội dung thay đổi; một số thao tác như `clear()` hoặc chèn `null` cũng tùy API và collection cụ thể. Vì vậy “read-only” ở đây là cách nói về **khả năng ghi phần tử typed**, không phải lời hứa bất biến toàn diện.

## 3. Tái hiện heap pollution do raw alias

Đầu tiên, lưu chương trình `RawHeapPollutionDemo.java` ở phần 7 và chạy đúng lệnh biên dịch. Đây là một đoạn rút gọn để hiểu cốt lõi:

```java
static void legacyAppend(List raw) {
    raw.add(42);
}

List<String> names = new ArrayList<>(List.of("An"));
legacyAppend(names);

System.out.println(names); // [An, 42]
String second = names.get(1); // ClassCastException ở runtime.
```

Đoạn này minh họa method và các lệnh cần đặt trong class/main thích hợp; chương trình hoàn chỉnh ở phần 7 có imports và bắt exception.

Diễn tiến:

1. Caller tạo một `ArrayList` và giữ nó dưới tham chiếu `List<String>`.
2. `legacyAppend(List raw)` nhận **cùng object** thông qua một tham số raw.
3. `raw.add(42)` chèn một Integer. Không có kiểm tra runtime trong ArrayList rằng type argument của alias ban đầu là String.
4. In danh sách cho kết quả `[An, 42]` vì `toString()` có thể trình bày cả String lẫn Integer dưới Object.
5. `String second = names.get(1)` yêu cầu String. Compiler đã chấp nhận phép đọc theo type argument của `names`.
6. Khi kết quả thực là Integer, phép cast sang String do compiler chèn tại vị trí sử dụng thất bại và ném `ClassCastException`.

**Điểm gây lỗi thật sự là dòng `raw.add(42)`, không phải lỗi thiết kế của getter String.** Exception chỉ biểu hiện ở phía đọc. Đó là lý do thông báo stack trace và nơi dữ liệu bị làm sai có thể ở cách nhau rất xa trong codebase.

### Hai cảnh báo compiler điển hình

Khi bật:

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawHeapPollutionDemo.java
```

Compiler đã được kiểm chứng tạo hai cảnh báo từ code raw của ví dụ:

```text
[rawtypes] found raw type: List
[unchecked] unchecked call to add(E) as a member of the raw type List
```

Cảnh báo thứ nhất chỉ ra tham số `List raw` thiếu type arguments. Cảnh báo thứ hai đánh dấu đúng thao tác ghi mà compiler không thể bảo đảm an toàn.

Đừng xem đây là “warning vô hại vì code vẫn chạy”. Code **thực sự đã chèn sai loại phần tử**.

## 4. Vì sao exception nổ lúc đọc thay vì lúc ghi?

Generic type erasure khiến `List<String>` và `List<Integer>` không có hai runtime class riêng. Ở bytecode, lời gọi `List.get(int)` trả về `Object` theo erased signature. Compiler có thể chèn một `checkcast java/lang/String` tại điểm caller sử dụng giá trị dưới kiểu String.

Từ góc nhìn khái niệm:

```java
// Logic nguồn:
String second = names.get(1);

// Minh họa công việc tương đương sau erasure:
Object element = names.get(1);
String second = (String) element;
```

Đây là **minh họa cơ chế**, không phải mã nguồn javac xuất nguyên xi. JVM có thể tối ưu hóa hoặc tạo bytecode khác tùy ngữ cảnh, nhưng về nguyên tắc, kết quả của `get` phải tương thích với String tại điểm sử dụng.

Vì vậy:

```java
System.out.println(names);       // Có thể in [An, 42].
Object value = names.get(1);     // Có thể đọc Integer dưới Object.
String text = names.get(1);      // ClassCastException.
```

Nếu debug chỉ tập trung vào dòng `String text = ...`, bạn có thể sửa nhầm bằng cách thêm cast hoặc đổi text thành Object. Việc ấy **không sửa dữ liệu bị ô nhiễm** và có thể chỉ dời lỗi sang chỗ khác.

### Tại sao không có `ArrayStoreException`?

Array Java là reified: một `String[]` thực giữ thông tin component type String và JVM có thể chặn Object[] alias ghi Integer bằng `ArrayStoreException`.

Một `ArrayList<String>` thông thường không mang runtime component type “String” như mảng String[]; bản thân ArrayList lưu các tham chiếu Object. Vì vậy ghi qua raw API có thể đi qua, và lỗi chỉ bộc lộ khi một thao tác sau đó đòi String.

**Khác biệt:** `ArrayStoreException` gắn với runtime array component checking; `ClassCastException` trong ví dụ gắn với ép kiểu tại phía sử dụng. Cùng là lỗi kiểu runtime, nhưng nguyên nhân và điểm kiểm tra khác nhau.

## 5. Quy trình tìm nguồn ô nhiễm trong dự án

Khi production báo `ClassCastException: Integer cannot be cast to String` ở một getter generic:

1. **Xác định collection bị lỗi**: instance nào, ai tạo, được chia sẻ cho những method nào?
2. **Kiểm tra đường alias**: có biến `List raw`, `Map raw`, `Collection raw`, hoặc Object[] alias không?
3. **Tìm cảnh báo unchecked/rawtypes**: đây thường là nơi compiler đã mất khả năng kiểm tra dữ liệu.
4. **Tìm các thao tác ghi**: `add`, `set`, `put`, `addAll`, reflection hay adapters từ API legacy.
5. **Kiểm tra cast unchecked**: có `(List<String>) unknown` mà không validate phần tử không?
6. **Xem dữ liệu runtime thật**: in `getClass().getName()` của phần tử lỗi dưới tham chiếu Object thay vì ép String lại.
7. **Sửa tại ranh giới ghi**: dùng signature typed hoặc kiểm tra dữ liệu đầu vào, không chỉ bắt `ClassCastException` ở getter.
8. **Thêm test regression**: chứng minh thao tác ghi Integer bị compiler từ chối hoặc boundary trả lỗi chủ động.
9. **Xem các alias cũ có còn giữ mutable reference không**: bản vá signature mới có thể chưa đủ nếu API cũ vẫn chia sẻ collection.
10. **Nâng kiểm tra build**: tập trung loại bỏ `rawtypes` và `unchecked` mới, sau đó siết build khi khả thi.

Nếu ứng dụng lưu dữ liệu từ JSON, JDBC, phản chiếu hoặc kết nối thư viện cũ, hãy xác định cả nơi **convert từ Object sang domain type**. Một phép cast parameterized chỉ xác nhận lớp container ở mức có thể kiểm tra, không chứng minh từng phần tử đúng.

## 6. Sửa tại nguồn: biến API raw thành API typed

Điểm ô nhiễm trong ví dụ:

```java
static void legacyAppend(List raw) {
    raw.add(42);
}
```

Nếu method có nghiệp vụ **thêm tên**, sửa thành:

```java
static void appendName(List<String> target, String name) {
    target.add(name);
}
```

Caller:

```java
List<String> names = new ArrayList<>(List.of("An"));
appendName(names, "Binh");
// appendName(names, 42); // Compile error.
```

Bây giờ compiler có đủ bằng chứng để từ chối một Integer ngay ở boundary. Không cần `@SuppressWarnings` và không cần đợi getter bị crash.

### Một compile error được kiểm chứng

**Tệp `TypedListRejectsWrongValue.java` — cố ý không biên dịch:**

```java
import java.util.List;

class TypedListRejectsWrongValue {
    static void append(List<String> names) {
        names.add(42);
    }
}
```

Chạy:

```bash
javac --release 17 -Xdiags:verbose TypedListRejectsWrongValue.java
```

Compiler báo trọng tâm:

```text
no suitable method found for add(int)
method List.add(String) is not applicable
(argument mismatch; int cannot be converted to String)
```

Đây là hành vi mong muốn: type error bị phát hiện ở lúc biên dịch, trước khi dữ liệu sai được chèn vào collection.

### Nếu nghiệp vụ thực sự nhận nhiều kiểu thì sao?

Không phải mọi method raw nên được đổi thành `List<String>`. Nếu method có trách nhiệm thêm **một giá trị đúng kiểu mà caller chỉ định**, hãy dùng một generic method:

```java
static <T> void appendTyped(List<T> target, T value) {
    target.add(value);
}
```

Tuy nhiên đừng mặc định rằng `<T> void appendTyped(List<T>,T)` luôn bắt caller truyền hai biểu thức có cùng exact runtime class; inference cần được phân tích theo cả các ràng buộc, có thể chọn supertype chung trong những ngữ cảnh thích hợp. Nếu contract bắt buộc danh sách String, signature cụ thể `List<String>` là rõ nhất.

Nếu method **chỉ đọc** collection của mọi kiểu:

```java
static void printElements(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

`List<?>` phù hợp hơn raw List vì giữ nguyên giới hạn kiểu ở compile time. Nó không cho phép thêm tùy ý một Object vào list vốn có thể là List<String>.

## 7. Chương trình Java 17 hoàn chỉnh: tái hiện và sửa

**Tệp `RawHeapPollutionDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;

public class RawHeapPollutionDemo {
    static void legacyAppend(List raw) {
        raw.add(42);
    }

    static void appendName(List<String> target, String name) {
        target.add(name);
    }

    static List<String> checkedStringCopy(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object item : input) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException("not String: " + item);
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    static <T> List<T> checkedCopy(List<?> input, Class<T> type) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(type.cast(item));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An"));
        legacyAppend(names);
        System.out.println("runtimeContent=" + names);

        try {
            String second = names.get(1);
            System.out.println("read=" + second);
        } catch (ClassCastException error) {
            System.out.println("rawFailure="
                    + error.getClass().getSimpleName());
        }

        List<String> fixed = new ArrayList<>(List.of("An"));
        appendName(fixed, "Binh");
        System.out.println("typed=" + fixed);

        System.out.println("checked="
                + checkedStringCopy(List.of("A", "B")));

        try {
            checkedStringCopy(names);
        } catch (IllegalArgumentException error) {
            System.out.println("rejected=" + error.getMessage());
        }

        System.out.println("tokenCopy="
                + checkedCopy(List.of("C", "D"), String.class));

        try {
            checkedCopy(List.of("A", 42), String.class);
        } catch (ClassCastException error) {
            System.out.println("tokenRejected="
                    + error.getClass().getSimpleName());
        }

        List<?> readOnlyView = names;
        System.out.println("unknownSize=" + readOnlyView.size());
        System.out.println("unknownElement="
                + readOnlyView.get(1).getClass().getSimpleName());
    }
}
```

**Biên dịch với cảnh báo được bật:**

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawHeapPollutionDemo.java
java RawHeapPollutionDemo
```

Lưu ý: Chương trình này **cố tình dùng raw API sai**, nên compiler phát hai warning như phần 3. Những warning là một phần của bài thực hành, không phải lỗi của môi trường JDK.

**Stdout đã chạy và kiểm chứng:**

```text
runtimeContent=[An, 42]
rawFailure=ClassCastException
typed=[An, Binh]
checked=[A, B]
rejected=not String: 42
tokenCopy=[C, D]
tokenRejected=ClassCastException
unknownSize=2
unknownElement=Integer
```

### Đọc từng kết quả

- `runtimeContent=[An, 42]`: raw write đã thay đổi cùng một object mà typed reference đang giữ.
- `rawFailure=ClassCastException`: exception xuất hiện tại lúc lấy phần tử thứ hai dưới kiểu String.
- `typed=[An, Binh]`: sau khi sửa method signature thành `List<String>`, thao tác thêm đúng loại được compiler kiểm soát.
- `checked=[A, B]`: boundary tạo bản sao đã xác thực từng phần tử là String.
- `rejected=not String: 42`: boundary phát hiện input sai và báo lỗi có ý nghĩa nghiệp vụ, thay vì để CCE phát sinh muộn.
- `tokenCopy=[C, D]`: phiên bản có `Class<T>` tạo bản sao typed sau khi gọi `type.cast` cho từng giá trị.
- `tokenRejected=ClassCastException`: type token chặn Integer khi caller yêu cầu String.
- `unknownSize=2` và `unknownElement=Integer`: một `List<?>` vẫn quan sát được object sai dưới Object mà không cần cast sang String.

### Tại sao code có thể compile mà vẫn có warning?

`javac` hỗ trợ raw types vì Java cần tương thích mã cũ. Dù `raw.add(42)` không được kiểm tra generic đầy đủ, javac vẫn cho biên dịch nếu tình huống chỉ gây warning và không vi phạm những ràng buộc bắt buộc khác. Đây là **cảnh báo về an toàn kiểu**, và chương trình chứng minh bằng runtime failure rằng cảnh báo có thể là lỗi thật.

Trong code production không chủ đích minh họa, nên sửa raw method và dần đặt chính sách build giảm/loại bỏ warning.

## 8. Dữ liệu đã đến dưới `List<?>`: kiểm tra và copy an toàn

Đôi khi dữ liệu từ bên ngoài chỉ có thể được biết là một danh sách chưa rõ kiểu phần tử:

```java
List<?> rawInput = someExternalApi();
```

Đây là cú pháp minh họa; `someExternalApi` phải do ứng dụng cung cấp, không có sẵn trong JDK.

**Không thể** chuyển dữ liệu thành List String chỉ bằng:

```java
// KHÔNG AN TOÀN:
@SuppressWarnings("unchecked")
List<String> names = (List<String>) rawInput;
```

Cast từ `List<?>` sang `List<String>` là unchecked, vì JVM không kiểm tra mọi phần tử generic ở runtime. Một cast thành công chỉ cho biết container phù hợp mức runtime có thể xác minh; phần tử bên trong có thể vẫn là Integer.

### Cách sửa: duyệt dưới Object rồi xây collection typed mới

```java
static List<String> checkedStringCopy(List<?> input) {
    List<String> result = new ArrayList<>();
    for (Object item : input) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("not String: " + item);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

Ưu điểm:

1. Mỗi phần tử được kiểm tra trước khi đưa vào List String.
2. Chỉ các giá trị thật sự là String mới được thêm vào `result`.
3. Không cần unchecked cast.
4. Trả về một snapshot không sửa được về mặt cấu trúc, giúp tránh một alias mutable bên ngoài sửa collection mới sau khi validation.
5. Nếu gặp một giá trị không phải String, exception xuất hiện **ngay tại ranh giới dữ liệu**, kèm thông điệp dễ xác định.

Ví dụ:

```java
List<String> a = checkedStringCopy(List.of("A", "B"));
// checkedStringCopy(List.of("A", 42)); // IllegalArgumentException.
```

Phải làm rõ chính sách null: `null instanceof String` trả false, nên hàm này chủ động từ chối null. `List.copyOf` cũng không nhận phần tử null. Đây là lựa chọn contract cụ thể, không phải một tính chất tự động của mọi List String.

### Defensive copy không phải deep copy

`List.copyOf(result)` tạo collection không sửa được về mặt cấu trúc, không tự làm immutable các object bên trong. Với String điều đó ít vấn đề vì String immutable; với `List<MutableEntity>`, những MutableEntity vẫn có thể thay đổi trạng thái. Nếu cần deep immutability, phải clone/convert object thành dữ liệu bất biến phù hợp.

## 9. Generic boundary dùng `Class<T>`

Khi một adapter phải hỗ trợ nhiều kiểu runtime đơn giản, có thể nhận type token:

```java
static <T> List<T> checkedCopy(List<?> input, Class<T> type) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(type.cast(item));
    }
    return List.copyOf(result);
}
```

Caller:

```java
List<String> names = checkedCopy(List.of("A", "B"), String.class);
List<Integer> ids = checkedCopy(List.of(1, 2), Integer.class);
```

`Class<T>.cast` là một runtime check dựa trên Class token. Nếu một giá trị không tương thích với String.class, nó ném ClassCastException tại boundary.

**Giới hạn cần hiểu:**

- `String.class` kiểm tra String, `Integer.class` kiểm tra Integer.
- Không tồn tại class literal `List<String>.class` để kiểm tra sâu nested type arguments.
- `List.class` chỉ kiểm tra container List, không kiểm tra từng String bên trong.
- `Class.cast(null)` chấp nhận null; nhưng ví dụ `checkedCopy` dùng `List.copyOf` nên null sẽ bị từ chối ở bước copy. Nếu null là dữ liệu hợp lệ trong nghiệp vụ, cần một contract và implementation khác.

Một framework nhận mô tả `Type`/`ParameterizedType` có thể biết expected generic element type, nhưng vẫn phải **tự thực hiện validation/deserialization**. Metadata không biến JVM thành cơ chế tự kiểm tra mọi kiểu generic lồng nhau.

## 10. `Collections.checkedList`: chặn raw write động tại boundary

Nếu vẫn phải tương tác với một API legacy giữ tham chiếu `List` raw và có thể gọi `add`, `Collections.checkedList` cung cấp **dynamic type-checking view** cho các thao tác ghi đi qua wrapper.

Ví dụ:

```java
List<String> checkedNames =
        Collections.checkedList(new ArrayList<>(), String.class);

checkedNames.add("An");
List raw = checkedNames; // Raw alias tại boundary legacy.
raw.add(42);             // ClassCastException ngay tại thao tác ghi.
```

Đoạn trên cần import `Collections`, `ArrayList`, `List` và cố ý tạo warning khi dùng raw.

Ý nghĩa: wrapper biết String.class, nên kiểm tra phần tử được thêm qua wrapper ở runtime. Đây là một tuyến phòng vệ bổ sung khi không thể sửa toàn bộ code legacy ngay lập tức.

### Chương trình kiểm chứng hành vi wrapper

**Tệp `CheckedBoundaryDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CheckedBoundaryDemo {
    static List<String> makeCheckedNames() {
        return Collections.checkedList(new ArrayList<>(), String.class);
    }

    static void legacyWrite(List raw, Object value) {
        raw.add(value);
    }

    public static void main(String[] args) {
        List<String> checkedNames = makeCheckedNames();
        checkedNames.add("An");
        try {
            legacyWrite(checkedNames, 42);
        } catch (ClassCastException e) {
            System.out.println("writeRejected="
                    + e.getClass().getSimpleName());
        }
        System.out.println("checkedContents=" + checkedNames);

        List<String> storage = new ArrayList<>(List.of("An"));
        List<String> wrapper =
                Collections.checkedList(storage, String.class);
        legacyWrite(storage, 42);
        System.out.println("wrapperDidNotRetroactivelyValidate="
                + wrapper);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -Xlint:rawtypes,unchecked CheckedBoundaryDemo.java
java CheckedBoundaryDemo
```

Code cố ý có raw `List` và unchecked write ở `legacyWrite`, nên compiler phát hai warnings về raw type/unchecked call trong kiểm thử.

**Stdout đã kiểm chứng:**

```text
writeRejected=ClassCastException
checkedContents=[An]
wrapperDidNotRetroactivelyValidate=[An, 42]
```

### Hai giới hạn quan trọng của checked wrapper

**Thứ nhất:** checked wrapper **không tự quét để sửa hoặc bác bỏ tất cả phần tử đã có** trong collection khi vừa được tạo. Nếu collection gốc đã polluted, việc bọc nó không tự làm dữ liệu sạch.

**Thứ hai:** nếu code vẫn giữ một alias trực tiếp tới collection gốc, thao tác ghi qua alias đó **đi vòng qua wrapper**. Trong ví dụ, biến `storage` vẫn truy cập ArrayList gốc nên `legacyWrite(storage, 42)` thành công và wrapper nhìn thấy `[An,42]` sau đó.

Do đó, checked view là tuyến bảo vệ hữu ích ở boundary đã được kiểm soát, nhưng không thay thế việc bỏ raw aliases và sửa signature API. Hạn chế quyền truy cập collection gốc nếu bạn muốn mọi thao tác đi qua wrapper.

## 11. Heap pollution khác: generic varargs và mảng không reifiable

Heap pollution không chỉ đến từ raw `List`. Một nguồn khác là **generic varargs**, nơi compiler phải kết hợp parameterized types với array ở runtime.

Xem ví dụ cố ý không an toàn:

**Tệp `UnsafeVarargsPollutionDemo.java`:**

```java
import java.util.List;

public class UnsafeVarargsPollutionDemo {
    static void corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String item = groups[0].get(0);
        System.out.println(item);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("A"), List.of("B"));
        } catch (ClassCastException error) {
            System.out.println("varargsFailure="
                    + error.getClass().getSimpleName());
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 -Xlint:all UnsafeVarargsPollutionDemo.java
java UnsafeVarargsPollutionDemo
```

**Đã kiểm chứng:** `javac` phát hai cảnh báo chính:

```text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Stdout:

```text
varargsFailure=ClassCastException
```

### Diễn tiến trong trường hợp varargs

1. Tham số `List<String>... groups` được biểu diễn qua một mảng mà component runtime không thể phân biệt List String với List Integer.
2. Mảng danh sách được nhìn qua alias `Object[]`.
3. `alias[0] = List.of(42)` vượt được array store check vì phần tử mới vẫn là một List ở cấp runtime.
4. `groups[0].get(0)` trả Integer, nhưng phía sử dụng muốn String.
5. ClassCastException nổ khi kiểu String được yêu cầu.

Đây là **đường gây heap pollution khác**, không phải lỗi raw List ban đầu. Nó cho thấy vì sao một signature nhìn có generic vẫn có thể gặp nguy hiểm nếu code dùng non-reifiable varargs array sai cách.

### Không che bằng `@SafeVarargs` một cách máy móc

`@SafeVarargs` là lời cam kết của tác giả rằng body không thao tác không an toàn với varargs theo những trường hợp được compiler cho phép khai báo annotation. **Method `corrupt` ở trên không an toàn**, vì nó cố ý ghi một List Integer vào vị trí dự kiến List String. Không được gắn `@SafeVarargs` chỉ để tắt warning.

Nếu API thật sự cần nhận nhiều danh sách, hãy cân nhắc một tham số `List<? extends List<String>>` hoặc một collection typed của các group, hoặc viết varargs method không ghi/không công khai mảng, rồi đánh giá an toàn trước khi sử dụng annotation hợp lệ.

## 12. Vì sao `@SuppressWarnings("unchecked")` không sửa được lỗi?

Annotation chỉ yêu cầu compiler không hiển thị một loại cảnh báo ở phạm vi được chỉ định. Nó không:

- Kiểm tra phần tử trong một `List`.
- Chuyển Integer thành String.
- Khôi phục generic type arguments đã bị erasure.
- Chặn raw alias ghi sai dữ liệu.
- Ngăn `ClassCastException`.
- Sửa generic varargs implementation không an toàn.

Ví dụ:

```java
@SuppressWarnings("unchecked")
static List<String> unsafeAssumeStrings(Object obj) {
    return (List<String>) obj;
}
```

Phương thức có thể trả một List thực sự chứa Integer. Caller đọc một phần tử dưới String sẽ gặp lỗi. Việc warning biến mất không có nghĩa dữ liệu đã sạch.

### Khi nào suppress có thể được xem xét?

Một adapter legacy đôi khi cần cast mà compiler không chứng minh được, nhưng lập trình viên có bằng chứng từ protocol/schema/validation riêng. Trong trường hợp đó:

1. Xác minh bằng chứng **trước cast**; tốt nhất là validate dữ liệu khi có thể.
2. Giới hạn phạm vi suppress vào **một biến hoặc một method adapter nhỏ**, không tắt toàn class/package tùy tiện.
3. Ghi rõ invariant mà adapter dựa vào.
4. Viết test có cả input đúng và sai kiểu.
5. Ưu tiên thay đổi API upstream để cast không còn cần thiết.

Tuyệt đối không xem suppress là bước “sửa tại nguồn”. Sửa tại nguồn nghĩa là phục hồi một contract typed và bảo vệ boundary chèn/nhận dữ liệu.

## 13. Phân biệt heap pollution và các lỗi liên quan

| Hiện tượng | Nơi xuất hiện | Dấu hiệu |
| --- | --- | --- |
| Raw type | Mã nguồn Java | `List raw` thay vì `List<String>`/`List<?>`. |
| Unchecked operation | Biên dịch | `[unchecked] unchecked call`, cast hoặc generic array creation. |
| Heap pollution | Trạng thái kiểu của reference/đối tượng trong chương trình | Tham chiếu typed nhìn dữ liệu không thực sự phù hợp với type argument. |
| ClassCastException | Runtime | Code yêu cầu String nhưng gặp Integer. |
| ArrayStoreException | Runtime | Array có component type runtime ngăn ghi object sai loại. |
| Compile-time type error | Biên dịch | `List<String>.add(42)` bị từ chối ngay. |
| UnsupportedOperationException | Runtime | Collection không cho thao tác sửa, dù kiểu phần tử phù hợp. |
| NullPointerException | Runtime | Dữ liệu null vi phạm contract của thao tác, chẳng hạn `List.copyOf`. |

Một collection có thể **vừa heap-polluted vừa có thể in ra bình thường**. Heap pollution là sai phạm về contract kiểu, không nhất thiết làm chương trình crash ngay lập tức.

Một method có generic type signature hợp lệ vẫn có thể không an toàn nếu dùng unchecked cast hoặc alias không kiểm soát. Compiler bảo vệ **những đường đi có đủ thông tin kiểu**, không chứng minh toàn bộ logic runtime của mọi thư viện bên ngoài.

## 14. Sửa tại nguồn: kế hoạch chuyển đổi API legacy thực tế

Trong dự án lớn, xóa raw types có thể phải đi theo từng bước vì có API cũ và consumer chưa cập nhật.

### Giai đoạn A — Cô lập và đo warning

Chạy:

```bash
javac --release 17 -Xlint:rawtypes,unchecked *.java
```

Lệnh wildcard có cách mở rộng khác nhau tùy shell/IDE/build tool; trong Maven/Gradle, cấu hình tương ứng cho JavaCompile/Javac nếu cần. Với ví dụ bài này, hãy compile từng file riêng như hướng dẫn.

Phân loại warnings:

- Raw declarations do chính code đang kiểm soát.
- Unchecked calls/assignments từ API cũ.
- Casts cố ý nhưng chưa có validation.
- Generic varargs và các thao tác array alias.
- Reflection/deserialization boundaries.

Ưu tiên sửa **đường ghi vào collection typed** vì nó có thể làm hỏng dữ liệu được chia sẻ cho nhiều consumer.

### Giai đoạn B — Cung cấp API mới an toàn

Ví dụ API cũ:

```java
void addRecords(List list, Object item);
```

Thiết kế typed tùy domain:

```java
void addNames(List<String> names, String name);
```

hoặc generic method:

```java
<T> void addRecord(List<T> target, T item);
```

Các chữ ký ở trên là declaration mô tả thiết kế; cần class/interface và implementation khi đưa vào project.

Với input bên ngoài chưa xác định type argument, dùng `List<?>` để đọc và validation/copy để tạo data structure typed mới.

### Giai đoạn C — Giữ tương thích có kiểm soát

Nếu còn caller cũ dùng raw API, có thể tạm tạo một **adapter nhỏ**:

- Không để raw list tiếp tục đi sâu vào core business logic.
- Chuyển Object sang domain type ở boundary.
- Từ chối sai loại với thông báo rõ.
- Trả collection typed mới thay vì phát tán alias mutable.
- Dùng dynamic checked view chỉ ở những nơi chưa thể sửa caller, nhớ giới hạn alias và dữ liệu tồn tại.

Không nên chỉ đổi kiểu biến local `List raw` thành `List<String>` bằng unchecked cast mà không kiểm tra phần tử; đó là **đổi nhãn type**, không đổi dữ liệu.

### Giai đoạn D — Siết build sau khi đã sửa

Khi các warning chủ động được xử lý, có thể cấu hình compiler để phát hiện những thao tác raw/unchecked mới:

```bash
javac --release 17 -Xlint:rawtypes,unchecked -Werror SafeSource.java
```

`-Werror` khiến warning làm compile thất bại, nên chỉ bật sau khi codebase có baseline phù hợp. Khi cần tạm migration, khoanh vùng legacy adapter với tài liệu rõ ràng và deadline kỹ thuật, không tắt cảnh báo vô hạn.

### Giai đoạn E — Regression tests

Nên có hai chiều kiểm thử:

- **Tích cực:** API typed nhận String và tạo output đúng.
- **Tiêu cực:** cố thêm Integer vào List<String> không compile hoặc boundary runtime chủ động từ chối nó.

Tách các test compile-negative thành file/tình huống riêng để build chính không bị hỏng có chủ đích.

## 15. Những bẫy thường gặp khi di chuyển từ raw sang generic

**Bẫy 1 — Dùng `List<Object>` để thay raw ở mọi chỗ.** Điều này thay đổi contract, thường không nhận được `List<String>` vì invariance. Nếu chỉ đọc bất kỳ list, `List<?>` thích hợp hơn.

**Bẫy 2 — Cast `List<?>` sang `List<String>` để tiện dùng.** Compiler không xác minh được String trong từng phần tử; cast unchecked có thể che heap pollution.

**Bẫy 3 — Chỉ bắt `ClassCastException` ở nơi đọc.** Bạn mới che triệu chứng; điểm raw write vẫn làm hỏng dữ liệu mà consumer khác có thể đọc.

**Bẫy 4 — Gắn `@SuppressWarnings("unchecked")` lên cả class.** Cảnh báo biến mất nhưng kiểm tra generic vẫn bị bỏ qua tại các nơi nguy hiểm.

**Bẫy 5 — Xem `Collections.checkedList` như phép làm sạch dữ liệu.** Checked view không quét sửa nội dung có sẵn và không chặn thao tác qua alias tới backing list.

**Bẫy 6 — Tin type erasure đồng nghĩa runtime không kiểm tra kiểu nào.** JVM vẫn kiểm tra casts, ArrayStore, Class tokens và các phép kiểm tra đối tượng reifiable. Chỉ **type argument không reified** không được JVM tự xác minh sâu.

**Bẫy 7 — Tưởng `List<?>` immutable.** View wildcard ngăn nhiều kiểu add tại compile time nhưng không khiến backing collection bất biến.

**Bẫy 8 — Đổ lỗi cho compiler vì cảnh báo raw List.** Raw types được giữ để tương thích lịch sử; cảnh báo là tín hiệu cho phép bạn tìm và cải thiện điểm mất type information.

**Bẫy 9 — Tự dùng mảng `List<String>[]` và ép kiểu không an toàn.** Các mảng generic non-reifiable dễ dẫn tới heap pollution, nhất là qua Object[] alias hoặc varargs.

**Bẫy 10 — Nghĩ cast checked với Class token giải quyết nested List<String>.** `Class<List>` chỉ biết List; cần validate các phần tử String riêng.

**Bẫy 11 — Bỏ qua tính mutable của nguồn.** Copy hoặc validate một lần không đảm bảo alias mutable bên ngoài không sửa nguồn sau này. Trả bản sao mới không share backing collection giúp tách ranh giới.

**Bẫy 12 — Quên null contract.** `type.cast(null)` không tự bác bỏ null, nhưng `List.copyOf` không chấp nhận null; thống nhất rõ chính sách của adapter.

## 16. Kỹ thuật kiểm tra dữ liệu bị ô nhiễm mà không gây CCE mới

Khi nghi một `List<String>` đã bị chèn sai loại, **đừng lập tức duyệt dưới biến String**:

```java
// Có thể ClassCastException khi gặp phần tử không phải String:
for (String name : names) {
    System.out.println(name.length());
}
```

Thay vào đó, quan sát qua `List<?>`/Object:

```java
List<?> unknown = names;
for (Object item : unknown) {
    System.out.println(item == null
            ? "null"
            : item.getClass().getName());
}
```

Với dữ liệu chứa String và Integer, bạn sẽ thấy các class runtime thật thay vì buộc cast từng phần tử thành String. Đây là một bước **chẩn đoán**, không làm sạch collection.

Sau khi tìm được giá trị sai:

1. Xác minh đường ghi đưa nó vào.
2. Sửa nơi ghi và signature liên quan.
3. Quyết định có nên loại bỏ/convert data cũ không.
4. Trả về một collection mới đã validate, nếu consumer cần invariant rõ.
5. Thêm test bảo vệ cả dữ liệu cũ và data flow mới.

Lưu ý khi in dữ liệu cá nhân hoặc nhạy cảm để debug: chỉ log class/type và thông tin tối thiểu, tránh tự in toàn bộ nội dung khi không cần.

## 17. So sánh ba cách bảo vệ boundary

| Cách | Kiểm tra gì? | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| `List<String>` trong signature | Compiler kiểm tra những lời gọi typed. | Ngăn lỗi ngay điểm viết code. | Raw/unchecked legacy code vẫn có thể vượt qua. |
| `checkedStringCopy(List<?>)` | Từng phần tử String khi copy. | Chặn sai dữ liệu và tạo snapshot mới. | O(n) để duyệt; tự định nghĩa chính sách null/loại lỗi. |
| `checkedCopy(List<?>,Class<T>)` | `Class.cast` từng phần tử. | Tái dùng cho nhiều runtime classes. | Không xác minh nested generic arguments. |
| `Collections.checkedList(backing,String.class)` | Các thao tác chèn phần tử đi qua wrapper. | Bảo vệ runtime tại đường ghi legacy. | Không validate dữ liệu cũ; alias backing có thể đi vòng. |

Không cần áp dụng **tất cả** mọi nơi. Với ứng dụng đã typed sạch, signature và compiler thường đủ ở phần lớn core logic. Boundary từ dữ liệu ngoài cần validation/copy. Wrapper thích hợp như biện pháp phòng vệ bổ sung khi vẫn phải hỗ trợ writer legacy.

## 18. Luyện tập và đáp án

### Bài 1 — Lỗi xuất hiện ở đâu?

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
String s = names.get(0);
```

**Đáp án:** Ghi raw chấp nhận kèm warning; ở bước đọc thành String, `ClassCastException` có thể xảy ra. Điểm phải sửa đầu tiên là `raw.add(42)` hoặc chữ ký API cho phép raw write.

### Bài 2 — Có thể dùng `List<Object>` thay `List<?>` để nhận mọi danh sách typed không?

**Đáp án:** Không. `List<String>` không là subtype của `List<Object>`. `List<?>` phù hợp cho API quan sát mọi List mà không tự cho phép thêm phần tử tùy ý.

### Bài 3 — `List<?>` có xóa phần tử sai không?

**Đáp án:** Không. Nó chỉ thay đổi những điều compiler cho phép qua tham chiếu đó; object phía dưới và mọi alias vẫn giữ nguyên dữ liệu.

### Bài 4 — Vì sao getter generic có thể ném ClassCastException khi setter raw chạy xong?

**Đáp án:** Erasure khiến runtime List không kiểm tra deep generic String ở raw write. Khi kết quả `get` được dùng dưới String, compiler có thể chèn cast và phát hiện Integer.

### Bài 5 — Cảnh báo nào nên xem trọng?

**Đáp án:** `[rawtypes]` ở khai báo raw và `[unchecked] unchecked call` ở thao tác ghi là hai tín hiệu trực tiếp của việc mất kiểm tra kiểu. Chúng có thể là nguyên nhân heap pollution.

### Bài 6 — Sửa `void addName(List raw,Object value)` thế nào?

**Đáp án:** Nếu nghiệp vụ thêm String, đổi thành `void addName(List<String> names,String value)`; compiler sẽ chặn Integer ở caller.

### Bài 7 — Khi chưa biết kiểu phần tử của input?

**Đáp án:** Nhận `List<?>`, duyệt từng Object, kiểm tra `instanceof String` rồi copy vào `List<String>` mới. Không cast nguyên danh sách mà không validate.

### Bài 8 — Class token có kiểm tra được `List<String>` không?

**Đáp án:** `String.class` kiểm tra từng String khi bạn gọi `cast` trên phần tử. `List.class` chỉ kiểm tra container, không có `List<String>.class` để JVM quét toàn bộ list.

### Bài 9 — Vì sao `Collections.checkedList` không đủ nếu còn alias backing?

**Đáp án:** Checked wrapper chỉ chặn thao tác đi qua wrapper. Raw writer dùng alias tới backing list có thể chèn sai loại đi vòng.

### Bài 10 — `@SafeVarargs` có được dùng để che warning cho method cố ý ghi List Integer vào mảng List String không?

**Đáp án:** Không. Annotation chỉ hợp lý khi implementation có cam kết an toàn tương ứng; việc đánh dấu một method không an toàn không sửa heap pollution.

### Bài 11 — Heap pollution và ClassCastException có luôn xảy ra cùng một dòng không?

**Đáp án:** Không. Heap pollution có thể được tạo từ raw write, còn CCE xảy ra muộn ở consumer đọc dưới kiểu String.

### Bài 12 — Cách kiểm tra class thật của phần tử mà không cast String?

**Đáp án:** Dùng `List<?>`, duyệt `Object`, sau đó `item.getClass()` với kiểm tra null. Đây là bước chẩn đoán, không phải thay thế validation/copy.

### Bài 13 — Vì sao `String[]` khác `List<String>`?

**Đáp án:** Mảng String giữ component type runtime và có array store check; List<String> bị type erasure ở runtime class và không tự kiểm tra String qua raw List write.

### Bài 14 — Nên xử lý dữ liệu cũ đã polluted thế nào sau khi sửa API?

**Đáp án:** Không mặc định dữ liệu tự sạch. Kiểm tra hoặc chuyển từng phần tử, loại bỏ giá trị không hợp lệ theo contract, tạo collection mới nếu cần và thêm regression tests.

### Bài 15 — Có thể coi code compile không warning là bảo đảm tuyệt đối mọi dữ liệu runtime hợp lệ không?

**Đáp án:** Không. Dữ liệu bên ngoài, reflection, thư viện native, raw legacy và một số unchecked boundary có thể ảnh hưởng. Nhưng việc loại bỏ raw/unchecked trong core logic là bước quan trọng để compiler kiểm tra tốt nhất có thể.

## 19. Checklist khi sửa bug heap pollution

1. **Tái hiện đúng input** khiến danh sách typed chứa phần tử sai.
2. **Ghi lại nơi tạo object** và các alias cùng trỏ vào nó.
3. **Bật compiler warning** với `-Xlint:rawtypes,unchecked`.
4. **Tìm dòng ghi đầu tiên thiếu kiểm tra kiểu**: raw add/set/put, cast, varargs alias.
5. **Định nghĩa invariant mong muốn**: ví dụ mỗi phần tử bắt buộc String và không null.
6. **Sửa signature ở nguồn**: `List<String>` hoặc `List<T>` theo mục tiêu thực tế.
7. **Dùng `List<?>` nếu chỉ đọc**, không thay bằng raw type.
8. **Kiểm tra dữ liệu đến từ ngoài** trước khi nhận dưới kiểu mạnh hơn.
9. **Tạo defensive copy** khi cần ngăn alias mutable làm hỏng dữ liệu sau validation.
10. **Cân nhắc checked wrappers** nếu còn API legacy ghi dữ liệu, nhớ giới hạn backing alias.
11. **Không suppress warning vô căn cứ**; khoanh vùng adapter cần thiết.
12. **Test biên dịch âm** để chắc ghi sai bị compiler từ chối.
13. **Test runtime âm** cho input không hợp lệ ở boundary.
14. **Kiểm tra null, mutability, nested generics và varargs** nếu liên quan.
15. **Đọc lại stack trace**: sau bản sửa, lỗi phải được chặn tại nguồn/boundary thay vì CCE muộn.
16. **Kiểm tra các consumer khác** đã từng dùng shared collection để phát hiện dư âm dữ liệu polluted.

## 20. Tổng kết

Raw type cho phép code Java legacy bỏ type arguments trên một tham chiếu generic. Nếu raw alias ghi giá trị sai vào collection, biến typed khác vẫn nhìn cùng object nhưng đang giữ dữ liệu vi phạm contract — đó là **heap pollution**. Java có thể cảnh báo ở điểm ghi nhưng ném `ClassCastException` muộn tại vị trí đọc.

Giải pháp đúng không phải che stack trace, thêm cast hoặc `@SuppressWarnings`. Hãy **sửa tại nguồn** bằng signature typed, tránh raw aliases, kiểm tra dữ liệu ngay boundary khi type chưa biết, và tạo snapshot mới nếu cần giữ invariant trước các writer bên ngoài. `Collections.checkedList` hoặc `Class<T>` là các công cụ phụ trợ hữu ích, nhưng mỗi công cụ có phạm vi bảo vệ riêng.

**Nguyên tắc quan trọng nhất:** Nơi dữ liệu đi vào collection typed phải là nơi hợp đồng kiểu được kiểm tra. Khi bạn khôi phục đúng ranh giới đó, compiler có thể giúp ngăn lỗi ngay từ lúc viết code, thay vì để một consumer bất kỳ chịu hậu quả ở runtime.
