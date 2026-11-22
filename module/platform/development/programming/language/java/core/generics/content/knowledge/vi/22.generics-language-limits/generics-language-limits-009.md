# Phân biệt giới hạn ngôn ngữ với giới hạn của một API cụ thể trong Java Generics

Khi một đoạn Java liên quan đến generics không biên dịch hoặc chạy đến một lời gọi rồi ném exception, câu hỏi đầu tiên không nên là “Generics của Java có hạn chế này sao?” mà là: **giới hạn đến từ bản thân ngôn ngữ Java, từ chữ ký/kiểu mà tác giả API lựa chọn, hay từ hợp đồng thực thi của một API/implementation cụ thể?**

Ba tầng này liên quan nhưng không đồng nhất:

1. **Quy tắc ngôn ngữ (language rules):** Java Language Specification (JLS) xác định mã nào hợp lệ, chẳng hạn generics bất biến, không dùng primitive type arguments trong generic thông thường, không tạo `new T[]`, và không dùng type parameter của lớp trong static context. Viết sai sẽ bị compiler từ chối bất kể bạn dùng thư viện nào.
2. **Ràng buộc ở chữ ký API (API type contract):** tác giả thư viện chọn `List<? extends Number>`, `<T extends Number>`, `Consumer<? super T>` hay một overload cụ thể. Compiler áp dụng những ràng buộc này theo quy tắc của Java, nhưng **việc chọn chữ ký** là lựa chọn thiết kế của API, không phải luật mọi generic API bắt buộc phải nhận riêng `Number`.
3. **Hợp đồng runtime của API/implementation:** `List.of` không cho phép phần tử `null` và không hỗ trợ sửa đổi; `ArrayList` có thể thêm phần tử, kể cả `null`; `Arrays.asList` cho phép `set` nhưng không cho thay đổi kích thước. Những khác biệt này thường chỉ lộ ra khi thực thi, dù biến đều có kiểu `List<String>`.

Nắm được ranh giới trên giúp chọn phương pháp khắc phục đúng: **không cố dùng cast để lách một lỗi ngôn ngữ**, cũng không cho rằng mọi lỗi `UnsupportedOperationException` hoặc `NullPointerException` đều do generic type erasure.

## 1. Bản đồ phân loại: lỗi nằm ở tầng nào?

| Tình huống | Tầng chính | Biểu hiện đặc trưng | Hướng xử lý |
| --- | --- | --- | --- |
| `List<int>` | Ngôn ngữ | Lỗi biên dịch: type argument phải là kiểu tham chiếu | Dùng `List<Integer>`, hoặc mảng `int[]` nếu phù hợp |
| `List<String>` gán vào `List<Object>` | Ngôn ngữ | Lỗi biên dịch do invariance | Chọn wildcard/API khác đúng hướng đọc-ghi |
| `new T[10]` với `T` generic | Ngôn ngữ | Lỗi `generic array creation` | Dùng `List<T>`, token hoặc array factory |
| `value instanceof List<String>` với `value` kiểu `Object` | Ngôn ngữ và erasure | Không thể kiểm tra type argument như mong muốn | `instanceof List<?>`, rồi xác thực phần tử |
| `static T cache` trong `class Box<T>` | Ngôn ngữ | Lỗi do `T` lớp không được dùng trong static context | Instance field hoặc static method type parameter riêng |
| Truyền `String` vào hàm khai báo `<T extends Number>` | Chữ ký API | Lỗi biên dịch do bound mà API đặt | Cung cấp `Number` hoặc dùng API có hợp đồng khác |
| `new ArrayList<String>().add(null)` | Hợp đồng API | Được phép đối với `ArrayList` | Quy định riêng null policy nếu cần |
| `List.of("A", (String) null)` | Hợp đồng API | `NullPointerException` | Không truyền null hoặc chọn API phù hợp |
| `List.of("A").add("B")` | Hợp đồng API | `UnsupportedOperationException` | Tạo collection mutable nếu cần thêm |
| `Arrays.asList("A","B").set(0,"X")` | Hợp đồng API | Thành công | Ghi đè được phần tử nhưng không tăng kích thước |
| `Arrays.asList("A","B").add("C")` | Hợp đồng API | `UnsupportedOperationException` | Dùng `new ArrayList<>(...)` |
| Ghi giá trị sai kiểu qua `Collections.checkedList` bằng raw alias | Runtime guard do API cung cấp | `ClassCastException` tại thao tác ghi | Tránh raw alias, duy trì kiểu đúng |
| `List<String> names = raw;` | Ngôn ngữ/generic conversion | Có thể biên dịch với `unchecked warning` | Xác minh dữ liệu và hạn chế raw type |

**Không suy luận chỉ từ tên exception:** một `NullPointerException` cũng có thể do lỗi lập trình thông thường, không phải API cấm null; `ClassCastException` có thể đến từ cast thông thường, heap pollution hoặc wrapper kiểm tra kiểu. Luôn nhìn cả **điều kiện hợp đồng** và **vị trí phát sinh**.

## 2. Quy tắc ngôn ngữ áp dụng bất kể API bên ngoài

**Giới hạn ngôn ngữ** là ràng buộc của Java compiler/JLS, không thay đổi khi bạn đổi từ `ArrayList` sang `LinkedList` hay thư viện của công ty. Hãy dùng **dấu hiệu compile-time** để xác định:

| Trường hợp | Vì sao là quy tắc ngôn ngữ? | Hướng thay thế |
|---|---|---|
| `List<int>` | Generic type argument thông thường phải là reference type | `List<Integer>`, `int[]`, `IntStream` |
| `List<String>` → `List<Object>` | Generic type arguments invariant | Dùng `List<?>` để quan sát, wildcard PECS khi cần đọc/ghi |
| `new T[10]` | Java cấm tạo generic array có component non-reifiable | `List<T>`, `IntFunction<T[]>`, token/factory thích hợp |
| `obj instanceof List<String>` với `obj: Object` | Runtime không xác minh type argument đã erasure | `instanceof List<?>`, kiểm tra phần tử |
| `static T last;` trong `class Box<T>` | Type variable lớp không dùng trực tiếp ở static context | Instance field hoặc static `<U>` method |

Ví dụ nhỏ (đặt trong method với imports phù hợp):

```java
List<String> names = new ArrayList<>();
List<?> view = names;
Object first = view.isEmpty() ? null : view.get(0);
```

`List<?>` **không phải** `List<Object>`: nó cho phép xem danh sách chưa biết type argument mà không cho thêm non-null tùy ý. Tương tự, `String.class` có class token thật nhưng `List<String>.class` không tồn tại; một class token `List.class` không xác thực sâu element type.

Điểm quan trọng để phân loại sự cố: nếu *bất kỳ implementation* `List` nào cũng không giúp đoạn `List<int>` biên dịch, bạn đang gặp luật ngôn ngữ. Trái lại, cùng một `List<String>` có thể `add` thành công, ném `UnsupportedOperationException` hoặc từ chối `null` tùy API. **Đừng nhầm lỗi do type checker với hành vi runtime do implementation/factory quy định.**

## 3. Ràng buộc ở chữ ký API: compiler kiểm tra, nhưng tác giả API chọn hợp đồng

Đây là nhóm dễ bị nhầm thành “Java generic cấm kiểu X”. Xét hai phương thức do người viết API tự tạo:

```java
// Hai phương thức độc lập, có thể cùng tồn tại trong một class.
static <T> T first(java.util.List<T> items) {
    return items.get(0);
}

static <T extends Number> double twice(T number) {
    return number.doubleValue() * 2;
}
```

`first` nhận `List<T>` với `T` là kiểu tham chiếu bất kỳ phù hợp. `twice` giới hạn `T extends Number`; compiler chỉ chấp nhận giá trị có kiểu suy luận phù hợp bound.

```java
record Ticket(int id) {}

Ticket ticket = first(java.util.List.of(new Ticket(7))); // Hợp lệ
double value = twice(3); // Hợp lệ, 3 boxing thành Integer
// twice("3"); // KHÔNG BIÊN DỊCH
```

Điều quan trọng:

- **Luật ngôn ngữ** cho phép định nghĩa generic method với hoặc không có upper bound.
- **Tác giả API** chọn bound `Number` vì muốn gọi `doubleValue()`; compiler sau đó thực thi bound đó theo các quy tắc Java.
- Lỗi `twice("3")` **không** có nghĩa Java cấm dùng `String` với tất cả generic methods. `first(List<String>)` vẫn hợp lệ.

Trong thư viện Java, các chữ ký như `Collections.max(Collection<? extends T>)`, `Comparator<? super T>`, `Function<? super T, ? extends R>` hoặc `Stream<T>` phản ánh những **lựa chọn hợp đồng và quan hệ kiểu cần thiết cho thao tác** của API cụ thể. Chúng vẫn tuân thủ JLS nhưng không biến thành luật rằng mọi generic API phải mang chính xác những wildcard/bounds ấy.

### Chữ ký API và hành vi runtime là hai lớp khác nhau

Một phương thức nhận `List<String>` chưa chắc **được phép sửa** list đó. Chữ ký `List<String>` cho biết **kiểu phần tử dùng ở compile time**, không cho biết list có mutable hay không, có được chứa null hay không, có giới hạn dung lượng hay không.

Tương tự, `List<? extends Number>` có thể cho phép đọc giá trị như `Number`, nhưng sẽ không cho gọi `add(Integer)` thông thường do kiểu wildcard capture chưa xác định. Đây là hạn chế compile-time của kiểu tham số hóa **do API đã chọn**; nếu runtime list đồng thời không sửa được, còn có thêm một hạn chế runtime độc lập.

## 4. Cùng kiểu `List<String>`, ba implementation có hành vi khác nhau

Đây là phản ví dụ rõ nhất cho nhầm lẫn “một kiểu generic luôn quy định cùng khả năng sửa đổi”:

```java
java.util.List<String> mutable = new java.util.ArrayList<>();
java.util.List<String> fixed = java.util.Arrays.asList("A", "B");
java.util.List<String> immutable = java.util.List.of("A", "B");
```

Cả ba biến đều có kiểu tĩnh `List<String>`, do đó compiler biết phần tử có kiểu `String`, có các phương thức `get`, `set`, `add` trong interface `List`. Nhưng implementation/hợp đồng không giống nhau:

| Hành vi | `ArrayList` | `Arrays.asList` | `List.of` |
| --- | --- | --- | --- |
| `get(index)` | Có | Có | Có |
| `set(index, value)` | Có | Có | Không hỗ trợ |
| `add(value)` thay đổi kích thước | Có | Không hỗ trợ | Không hỗ trợ |
| `remove(...)` thay đổi kích thước | Có | Không hỗ trợ | Không hỗ trợ |
| Có thể chứa `null` | Có | Có nếu mảng/phần tử nguồn có null | Không |
| Có runtime exception khi gọi thao tác không hỗ trợ? | Có thể cho thao tác sai điều kiện như chỉ số | `UnsupportedOperationException` khi thêm/xóa | `UnsupportedOperationException` khi sửa |
| Có bản sao riêng với array đầu vào? | Tùy constructor | Là view kích thước cố định được backing bởi array đã cung cấp | Factory tạo unmodifiable list theo hợp đồng |

`Arrays.asList` không trả một `java.util.ArrayList` thông thường: danh sách kích thước cố định gắn với một array. Vì vậy `set` được hỗ trợ nhưng thêm/xóa cấu trúc thì không.

`List.of` là factory tạo **unmodifiable list** không chứa null. Không suy ra “unmodifiable” nghĩa mọi object phần tử đều immutable: nếu phần tử tự nó là object mutable, trạng thái nội bộ của object đó vẫn có thể thay đổi từ nơi khác.

### Tại sao gọi `add` được compiler chấp nhận nhưng runtime từ chối?

Vì chữ ký của `List<E>` có method `boolean add(E e)`; compiler chỉ kiểm tra kiểu tham số `E = String` và tính hợp lệ của lời gọi ở mức ngôn ngữ. Nó không biết chỉ từ biến `List<String>` rằng **đối tượng thực** đang được dùng là implementation unmodifiable.

```java
java.util.List<String> list = java.util.List.of("An");

// Compiler cho phép viết lời gọi vì List<String> có add(String):
// list.add("Binh"); // Runtime: UnsupportedOperationException
```

Dòng có chú thích không cần đưa vào chương trình chạy an toàn; ở demo sẽ bắt exception để minh họa chính xác.

## 5. `null` có phải bị Java Generics cấm không?

**Không.** `List<String>` không có nghĩa “danh sách chỉ nhận các `String` non-null”. Kiểu `String` là reference type; `null` là giá trị có thể gán cho các kiểu tham chiếu theo quy tắc ngôn ngữ, trừ khi API hoặc công cụ phân tích bổ sung đặt chính sách chặt hơn.

Hai đoạn sau có cùng type argument `String`, nhưng hành vi khác nhau:

```java
java.util.List<String> a = new java.util.ArrayList<>();
a.add(null); // Hợp lệ và được ArrayList hỗ trợ

// java.util.List<String> b = java.util.List.of((String) null);
// Runtime: NullPointerException
```

`List.of` thiết kế để từ chối các phần tử null; `ArrayList` chấp nhận chúng. Câu trả lời đúng không phải “generics cấm null”, mà là **API factory `List.of` đặt một hợp đồng null policy cụ thể**.

So sánh thêm:

- `List.copyOf(collection)` tạo unmodifiable list theo hợp đồng và **từ chối phần tử null**.
- `Arrays.asList` cho phép một phần tử null vì list backing của nó có thể chứa null.
- `Objects.requireNonNull(value)` có thể được dùng trong bất kỳ API tự viết nào để áp dụng chính sách non-null, không cần thay đổi generic type argument.

Nếu codebase dùng nullness annotations hoặc các trình phân tích ngoài javac, chúng có thể bổ sung cảnh báo/kiểm tra static ở mức dự án. Đó là **bộ quy tắc bổ sung**, không có nghĩa bản thân `List<String>` của Java tiêu chuẩn đương nhiên cấm null.

## 6. Unmodifiable view khác bản sao: giới hạn cũng là hợp đồng API

Cùng một kiểu tĩnh `List<String>`:

```java
java.util.List<String> source =
        new java.util.ArrayList<>(java.util.List.of("one"));

java.util.List<String> view =
        java.util.Collections.unmodifiableList(source);

java.util.List<String> snapshot =
        java.util.List.copyOf(source);

source.add("two");
System.out.println(view);     // [one, two]
System.out.println(snapshot); // [one]
```

**`Collections.unmodifiableList(source)`** tạo một *view không cho sửa qua view*. Caller không thể gọi `view.add("x")`, nhưng vì view vẫn nhìn vào source, thay đổi trên `source` có thể xuất hiện khi đọc `view`.

**`List.copyOf(source)`** cung cấp kết quả unmodifiable và, với mutable source trong ví dụ, là một snapshot độc lập về **cấu trúc** tại thời điểm sao chép. Sau khi `source.add("two")`, `snapshot` không có phần tử mới.

Cần giữ hai sắc thái:

1. **`List.copyOf` không cam kết mọi lần gọi đều tạo object mới**: nếu nguồn đã là unmodifiable list phù hợp, implementation có thể tái sử dụng object. Đừng dùng `a != b` làm định nghĩa của việc copy.
2. Cả view và snapshot đều **shallow** theo nghĩa không tự clone trạng thái bên trong từng object phần tử mutable. Unmodifiable list không đồng nghĩa immutable object graph.

Đây là khác biệt ở **hợp đồng và tính sở hữu dữ liệu**, không phải sự khác nhau giữa `List<String>` và một dạng generics khác.

## 7. `Collections.checkedList`: API bổ sung runtime type check

Java Generics chủ yếu bảo đảm kiểu ở compile time. Nếu phải tương tác với raw types hoặc mã cũ, `Collections.checkedList` có thể tạo một wrapper kiểm tra class của phần tử **khi phần tử được thêm qua wrapper**:

```java
java.util.List<String> checked =
        java.util.Collections.checkedList(
                new java.util.ArrayList<>(), String.class);

checked.add("ok");

java.util.List raw = checked;
// raw.add(42); // Có unchecked warning; wrapper ném ClassCastException
```

Sự khác nhau:

- **Luật ngôn ngữ:** `List<String>.add(Integer)` bị compiler từ chối ở code typed thông thường; raw alias có thể bỏ qua một phần kiểm tra với warning.
- **Hợp đồng `checkedList`:** wrapper dùng `String.class` để kiểm tra phần tử khi code thao tác **qua wrapper đó**, kể cả lời gọi qua raw alias, và từ chối `Integer`.
- **Giới hạn API:** wrapper không tự duyệt xác minh toàn bộ dữ liệu đã có trước khi bọc và không ngăn một alias khác sửa trực tiếp backing list nếu alias đó vẫn còn.

`checkedList` cũng không biến `List<String>` thành reified generic type trong JVM. Nó thực thi **một runtime guard do thư viện chọn cài đặt** tại các điểm thao tác mà wrapper kiểm soát.

Nếu hệ thống tiếp nhận dữ liệu `Object` không đáng tin, cần kiểm tra từng giá trị trước khi coi nó là `String` — không nên chỉ ép `(List<String>) input` rồi tin vào đối số generic đã bị xóa kiểu.

## 8. Ví dụ Java 17+ chạy được: nhìn cả ba tầng giới hạn

Lưu mã vào **`LanguageVsApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class LanguageVsApiDemo {
    record Ticket(int id) {}

    static <T> T first(List<T> list) {
        return list.get(0);
    }

    // Bound Number là một lựa chọn chữ ký API này.
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        mutable.add("An");
        mutable.add(null);
        System.out.println("ArrayList allows null: " + mutable);

        List<String> fixed = Arrays.asList("A", "B");
        fixed.set(0, "X");
        System.out.println("Arrays.asList allows set: " + fixed);
        try {
            fixed.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "Arrays.asList add: UnsupportedOperationException");
        }

        List<String> immutable = List.of("A", "B");
        try {
            immutable.set(0, "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "List.of set: UnsupportedOperationException");
        }
        try {
            List.of("A", (String) null);
        } catch (NullPointerException ex) {
            System.out.println("List.of null: NullPointerException");
        }

        List<String> source = new ArrayList<>(List.of("one"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);
        source.add("two");

        System.out.println("Unmodifiable view: " + view);
        System.out.println("List.copyOf snapshot: " + copy);

        List<?> unknown = source;
        System.out.println("Wildcard can read: " + unknown.get(0));

        List<String> checked = Collections.checkedList(
                new ArrayList<>(), String.class);
        checked.add("safe");

        List raw = checked;
        try {
            raw.add(42); // Cố ý minh họa unchecked call
        } catch (ClassCastException ex) {
            System.out.println(
                    "CheckedList raw add: ClassCastException");
        }

        System.out.println("Generic first accepts Ticket: "
                + first(List.of(new Ticket(7))).id());
        System.out.println("Bounded method accepts Integer: "
                + twice(3));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked LanguageVsApiDemo.java
java LanguageVsApiDemo
```

Đầu ra chuẩn (không gồm cảnh báo compiler):

```text
ArrayList allows null: [An, null]
Arrays.asList allows set: [X, B]
Arrays.asList add: UnsupportedOperationException
List.of set: UnsupportedOperationException
List.of null: NullPointerException
Unmodifiable view: [one, two]
List.copyOf snapshot: [one]
Wildcard can read: one
CheckedList raw add: ClassCastException
Generic first accepts Ticket: 7
Bounded method accepts Integer: 6.0
```

Diễn giải theo tầng:

1. `mutable.add(null)` được **ngôn ngữ** chấp nhận và **ArrayList API** hỗ trợ.
2. `fixed.set(0, "X")` thành công vì `Arrays.asList` hỗ trợ thay giá trị phần tử; `fixed.add` bị từ chối vì danh sách có kích thước cố định theo **hợp đồng API**.
3. `List.of` từ chối cả `set` và giá trị `null`, nhưng không có lỗi generic syntax nào khi viết các lời gọi đó.
4. `view` theo dõi nội dung source, còn `copy` tạo kết quả không nhìn thấy phần tử thêm sau đó từ mutable source.
5. `List<?> unknown` được compiler chấp nhận để đọc mọi phần tử như `Object`, minh họa quy tắc generic wildcard **ở ngôn ngữ**.
6. Raw alias `List raw` có thể gọi `add(42)` với **unchecked warning**; `checkedList` dùng runtime guard của API để ném `ClassCastException`.
7. `first` chấp nhận record `Ticket` vì tác giả phương thức không ràng buộc `T`; `twice` yêu cầu `Number` vì tác giả đã chọn bound trong chữ ký.

Chương trình độc lập này cố ý tạo một raw alias để so sánh cơ chế runtime của `checkedList`; không dùng raw type như mẫu triển khai trong mã nghiệp vụ.

## 9. Một kiểu `List<String>` không mô tả toàn bộ hành vi

Có thể phân loại thông tin kiểu và hành vi của một `List<String>`:

**Những điều kiểu tĩnh cho biết:** phần tử được coi là `String` trong các thao tác typed bình thường; compiler từ chối `add(Integer)`; `get(i)` có kiểu `String`; có thể dùng các method được interface `List` khai báo theo điều kiện ngôn ngữ.

**Những điều kiểu tĩnh không tự cho biết:** implementation có mutable không; `add` có được hỗ trợ không; null có được chấp nhận không; list có thread-safe không; có giới hạn dung lượng không; view có phản ánh thay đổi của nguồn không; có snapshot không; phương thức có chi phí thuật toán nào.

Vì vậy, chữ ký `List<String>` không đủ để đảm bảo một phương thức sau đây luôn có thể thêm phần tử:

```java
static void appendName(List<String> names) {
    names.add("new");
}
```

Method này **biên dịch được**, nhưng nếu caller đưa `List.of("A")` hoặc `Arrays.asList("A")`, runtime có thể ném `UnsupportedOperationException`.

Tác giả API phải **tài liệu hóa yêu cầu** (ví dụ “tham số phải là mutable list hỗ trợ structural modification”), hoặc thiết kế để không cần sửa tham số:

```java
static List<String> appendedCopy(List<String> names, String next) {
    List<String> result = new java.util.ArrayList<>(names);
    result.add(next);
    return result;
}
```

Cách thứ hai trả danh sách mới và không đòi input là modifiable; nhưng vẫn cần xét null policy, size, nguồn thay đổi đồng thời và các yêu cầu nghiệp vụ khác. Nó là một **lựa chọn hợp đồng API**, không phải hệ quả tự động từ generics.

## 10. Khi nào chữ ký API thất bại lúc biên dịch?

Không phải lỗi compile-time nào cũng chỉ thuần là “hạn chế ngôn ngữ bất biến áp dụng với mọi API”. Nếu phương thức tự khai báo bound:

```java
static <T extends Comparable<? super T>> T greatest(
        java.util.List<T> items) {
    T best = items.get(0);
    for (T next : items) {
        if (next.compareTo(best) > 0) {
            best = next;
        }
    }
    return best;
}
```

Ở đây API lựa chọn yêu cầu `T` có thể so sánh tương thích `Comparable<? super T>`. Nếu truyền một list của type không đáp ứng bound, compiler báo lỗi. Nhưng bạn hoàn toàn có thể viết một method khác không cần so sánh:

```java
static <T> int count(java.util.List<T> items) {
    return items.size();
}
```

`count` nhận nhiều kiểu `T` hơn vì thuật toán không cần quan hệ thứ tự. **Tác giả API chọn yêu cầu thao tác**, còn compiler thực thi yêu cầu ấy bằng luật generic type checking của ngôn ngữ.

Tương tự, `List.of`, `Arrays.asList` và `Collections.unmodifiableList` có chữ ký tổng quát cho nhiều kiểu phần tử nhưng lại có **hợp đồng mutation khác nhau**. Chữ ký tổng quát không đồng nghĩa khả năng thực thi mọi method thuộc interface.

## 11. Kiểu trả về interface và nguyên tắc thiết kế theo hợp đồng

Khi một method trả `List<T>`, nó có thể trả `ArrayList<T>`, `List.of(...)`, một view hoặc một implementation khác, miễn phù hợp các ràng buộc của chữ ký và hợp đồng API đã công bố.

Ví dụ:

```java
static List<String> names() {
    return List.of("An", "Binh");
}
```

Caller có thể đọc, lặp, tìm kiếm, lấy kích thước; nhưng không được mặc định rằng `names().add("C")` luôn chạy thành công.

Lựa chọn của tác giả API:

- **Nếu muốn trả trạng thái không sửa được:** có thể trả `List.copyOf(source)` cùng tài liệu null policy, shallow copy, và xử lý concurrency.
- **Nếu muốn caller sửa danh sách độc lập:** có thể trả `new ArrayList<>(source)` và ghi rõ ownership.
- **Nếu muốn một live view:** có thể trả `Collections.unmodifiableList(source)`, nhưng phải nói rõ thay đổi ở source sẽ được nhìn thấy qua view.
- **Nếu muốn API chỉ đọc:** nhận `Collection<? extends T>` hoặc `Iterable<T>` tùy thao tác cần thiết, thay vì yêu cầu caller có một mutable `List`.

Các lựa chọn này không làm thay đổi hệ thống type erasure hoặc invariance của Java. Chúng nói lên **semantic contract** mà người dùng phải đọc trong Javadoc và kiểm thử.

## 12. Chẩn đoán đúng khi gặp lỗi

### Trường hợp A — Javac báo không tìm được kiểu hoặc không tương thích type argument

Ví dụ:

```java
// List<int> values;              // Sai type argument
// List<Object> o = List.<String>of("A"); // Bất biến generic
```

Đây là nơi cần xem JLS, quy tắc generic, wildcard và kiểu tĩnh. Không có API mutable nào làm cho `List<int>` trở thành cú pháp hợp lệ.

### Trường hợp B — Javac báo bound không thỏa

Ví dụ:

```java
static <T extends Number> T same(T value) {
    return value;
}

// same("Java"); // Lỗi: không thể suy luận T phù hợp Number
```

Đọc chữ ký **API đã chọn** và đánh giá có đang gọi đúng phương thức hay không. Một generic API khác không có bound ấy có thể chấp nhận `String`.

### Trường hợp C — Biên dịch được nhưng `UnsupportedOperationException`

Ví dụ:

```java
List<String> names = List.of("A");
// names.add("B"); // Lỗi runtime dù type đúng
```

Xem implementation và hợp đồng mutation. Chuyển thành `new ArrayList<>(names)` nếu thực sự cần danh sách mutable; đừng ép kiểu `(ArrayList<String>) names` để mong object đổi loại.

### Trường hợp D — Biên dịch được nhưng `NullPointerException` tại factory

Ví dụ:

```java
// List.of("A", (String) null); // Runtime NPE
```

Đọc null policy của API; không quy kết generics cấm null. Nếu null hợp lệ trong dữ liệu nghiệp vụ, chọn collection/factory thích hợp hoặc lọc dữ liệu trước khi gọi.

### Trường hợp E — Unchecked warning và `ClassCastException`

Ví dụ raw alias vượt qua compile-time generic kiểm tra. Có thể phát sinh heap pollution và lỗi runtime khi đọc, hoặc bị `Collections.checkedList` chặn ngay khi thêm.

Hướng xử lý: giới hạn raw types, sửa caller bằng API generic, kiểm tra dữ liệu khi nhận từ nguồn không đáng tin và không dùng `@SuppressWarnings` để tuyên bố dữ liệu an toàn mà không có bằng chứng.

## 13. Bài tập tự kiểm tra

**Câu 1.** Vì sao `List<int>` không thể biên dịch, còn `List<Integer>` có thể?

Vì generic type arguments thông thường của Java yêu cầu kiểu tham chiếu; `int` là primitive, `Integer` là wrapper reference type. Đây là quy tắc ngôn ngữ.

**Câu 2.** `List<String> x = List.of("A"); x.add("B");` lỗi ở đâu?

Lời gọi hợp lệ về kiểu khi biên dịch; khi chạy, implementation tạo bởi `List.of` từ chối thao tác sửa cấu trúc, thường ném `UnsupportedOperationException`. Đây là hợp đồng API.

**Câu 3.** Vì sao `new ArrayList<String>().add(null)` không bị hệ thống generics cấm?

Vì type argument `String` không có nghĩa “non-null”; `ArrayList` cho phép phần tử null. API khác như `List.of` có thể đặt chính sách chặt hơn.

**Câu 4.** `static <T extends Number> void f(T x)` từ chối `f("abc")`. Đó có phải Java cấm `String` trong mọi generic method?

Không. Bound `Number` là lựa chọn chữ ký của chính `f`. Java chỉ thực thi bound ấy khi kiểm tra lời gọi.

**Câu 5.** Hai biến đều có kiểu `List<String>`; một biến đến từ `Arrays.asList`, một biến đến từ `new ArrayList<>()`. Vì sao `add` khác nhau?

Vì khả năng thay đổi kích thước là một phần hợp đồng của implementation, không được đảm bảo bởi type argument `String` hay riêng kiểu interface `List`.

**Câu 6.** `Collections.unmodifiableList(source)` có tạo snapshot hoàn toàn độc lập không?

Không. Nó tạo unmodifiable view, còn sửa đổi qua backing source có thể phản ánh ở view. Với mutable source, `List.copyOf(source)` là lựa chọn thích hợp hơn nếu muốn snapshot cấu trúc.

**Câu 7.** `Collections.checkedList` giúp gì khi gặp raw alias?

Nó kiểm tra runtime class của phần tử khi thao tác qua wrapper và có thể ném `ClassCastException` tại điểm ghi. Nó không thay thế tất cả luật generic compile time hoặc tự xác thực dữ liệu đã có từ trước.

**Câu 8.** Nếu một API chỉ chấp nhận `List<? extends Number>`, nên làm gì khi bạn có `List<String>`?

Xem mục tiêu và chữ ký API: nếu thao tác cần `Number`, truyền `List<String>` là sai hợp đồng. Không cast unchecked để lách; chọn dữ liệu phù hợp hoặc API khác có tính năng bạn cần.

**Câu 9.** Nếu compiler cho phép `list.add("x")` qua biến `List<String>`, có thể kết luận luôn không có runtime exception không?

Không. API có thể từ chối sửa đổi, từ chối null (khi đối số là null), từ chối do trạng thái, hoặc có preconditions khác được tài liệu hóa.

## 14. Checklist khi thiết kế và sử dụng generic API

Trước khi sửa code, hãy trả lời từng câu:

1. **Javac có từ chối mã không?** Nếu có, xem quy tắc type checking/JLS và chữ ký chính xác của method; lỗi compiler có thể phát sinh từ bound do API lựa chọn.
2. **Có runtime exception không?** Xác định method nào ném, implementation cụ thể là gì và precondition nào bị vi phạm.
3. **Kiểu tĩnh cho biết gì?** `List<String>` nói về phần tử ở compile time, không mặc nhiên nói về mutability, nullness hay thread safety.
4. **API có ràng buộc gì ngoài kiểu?** Fixed-size, unmodifiable, view, snapshot, null policy, ordering, comparator, capacity, ownership?
5. **Có unchecked/raw type không?** Nếu có, đánh giá heap pollution và đường truyền dữ liệu sai kiểu.
6. **Giải pháp đúng nằm ở đâu?** Đổi kiểu/thiết kế generic khi luật ngôn ngữ yêu cầu; đổi method/API khi bound không đúng; đổi collection/cách khởi tạo khi hợp đồng runtime không phù hợp.
7. **Có thể giữ API tổng quát hơn không?** Nếu chỉ đọc dữ liệu, cân nhắc `List<?>`, `Collection<? extends T>`, `Iterable<?>` thay vì buộc input phải là mutable list.
8. **Có cần defensive copy không?** Phân biệt unmodifiable view với snapshot và trách nhiệm quản lý alias.
9. **Đã kiểm tra trường hợp rỗng, null và sửa đổi chưa?** Các trường hợp này thường bộc lộ khác biệt API rõ hơn so với việc chọn `T`.
10. **Đang dựa vào tài liệu hay chỉ vào tên kiểu?** Hãy đọc Javadoc và hợp đồng method: compiler không thể chứng minh mọi quy tắc runtime của một implementation.

## 15. Kết luận

**Giới hạn ngôn ngữ Java** quyết định mã generic nào được viết và kiểm tra kiểu như thế nào — ví dụ invariance, type erasure, không dùng `List<int>`, `new T[]`, hoặc `T` của lớp trong static context. **Giới hạn do chữ ký API** quyết định loại đối số, bound và wildcard mà một operation cụ thể chấp nhận. **Giới hạn/hành vi runtime của API** quyết định collection có thêm/xóa được không, có nhận null không, là live view hay snapshot, và có kiểm tra phần tử lúc ghi hay không.

Vì vậy, hai giá trị cùng có kiểu `List<String>` **không nhất thiết có cùng khả năng sửa đổi hoặc chính sách null**. Khi gặp lỗi, hãy phân loại đúng tầng trước: **ngôn ngữ → chữ ký API → hợp đồng runtime**. Cách phân loại này giúp sửa đúng nguyên nhân, giữ an toàn kiểu và tránh những cast/raw workarounds gây lỗi muộn.