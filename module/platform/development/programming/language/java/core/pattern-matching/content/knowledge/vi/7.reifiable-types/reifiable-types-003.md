# Reifiable type trong `instanceof`

> **Module:** Java Core Pattern Matching → Generic và reifiable types. Bài sử dụng quy tắc **Java 17** (Java 16+ đã nới lỏng một giới hạn của `instanceof`). Các ví dụ có nhãn **ERROR** là mã cố ý không biên dịch; chương trình độc lập, chạy được nằm ở phần 8.

## Mục tiêu

Sau bài này, bạn có thể giải thích **reifiable type** là gì, nhận diện kiểu generic nào còn đủ thông tin để kiểm tra tại runtime, chọn cách viết `instanceof` và type pattern đúng trong Java 17, đồng thời tránh nhầm lẫn giữa kiểm tra lớp chứa và kiểm tra kiểu phần tử. Bạn cũng sẽ biết **ngoại lệ quan trọng từ Java 16**: có một số phép thử với kiểu tham số hóa *không reifiable* vẫn biên dịch hợp lệ khi **kiểu tĩnh của biểu thức bên trái** cho phép phép downcast được kiểm tra an toàn.

## 1. Vì sao `instanceof` liên quan tới reifiable type?

Java là ngôn ngữ có **generic type**: `List<String>` và `List<Integer>` là hai kiểu tĩnh khác nhau, giúp compiler ngăn thao tác sai kiểu trong mã nguồn. Tuy nhiên, **type erasure** xóa phần lớn thông tin về đối số kiểu (`String`, `Integer`) khi biên dịch sang bytecode.

Ví dụ:

~~~java
java.util.List<String> words = java.util.List.of("Java");
java.util.List<Integer> numbers = java.util.List.of(42);
~~~

Khi chạy, JVM thấy hai đối tượng là các đối tượng thực thi `List`; nó không có một "tem" runtime đáng tin cho biết đối số generic của từng tham chiếu là `String` hay `Integer`. Vì thế, kiểm tra `instanceof List<String>` không thể được diễn giải đơn giản thành “JVM xác nhận mọi phần tử của danh sách là `String`”.

**Reifiable type** là kiểu có thông tin biểu diễn đủ đầy tại runtime theo định nghĩa chính thức của **Java Language Specification (JLS) `4.7**. Những kiểu này thích hợp cho phép thử runtime thông thường, ví dụ `String`, `List<?>`, `String[]`.

Tách hai khái niệm:

- **Kiểu tĩnh (compile-time type)** của biểu thức bên trái: kiểu mà compiler nhìn thấy, ví dụ `Object`, `List<Integer>` hoặc `List<?>`.
- **Kiểu cần thử ở bên phải `instanceof`**: kiểu hoặc pattern được so khớp với giá trị lúc chạy, ví dụ `List<?>` hoặc `ArrayList<Integer>`.

Không phải cứ một tên kiểu generic xuất hiện sau `instanceof` là hợp lệ; điều kiện còn tùy **kiểu tĩnh bên trái** và phiên bản Java.

## 2. Những kiểu nào là reifiable?

Theo JLS `4.7, một kiểu là **reifiable** nếu thuộc một trong các nhóm sau:

1. Kiểu khai báo của lớp/interface **không generic**, chẳng hạn `String` hoặc `Runnable`.
2. Kiểu generic tham số hóa mà **mọi đối số kiểu đều là wildcard không giới hạn (`?`)**, như `List<?>` hoặc `Map<?, ?>`.
3. **Raw type**, như `List` hoặc `Map` (được giữ lại vì tương thích code cũ).
4. **Primitive type**, như `int` và `boolean`, theo định nghĩa chung của reifiability.
5. **Array type** mà kiểu phần tử của mảng là reifiable, như `String[]`, `List<?>[]`.
6. Kiểu lồng nhau mà các thành phần tên kiểu đều reifiable theo điều kiện của JLS.

Lưu ý riêng cho Java 17: dù `int` được JLS xếp là reifiable, **`instanceof` trong Java 17 chỉ nhận target biểu thức và kiểu tham chiếu theo quy tắc của toán tử**, nên `x instanceof int` **không hợp lệ**. Reifiable là thuộc tính của *kiểu*, không phải giấy phép dùng kiểu đó trong mọi vị trí cú pháp.

| Kiểu | Reifiable? | Lý do |
| --- | --- | --- |
| `String`, `Number`, `Runnable` | Có | Lớp/interface không generic |
| `List<?>` | Có | Toàn bộ đối số kiểu là wildcard không giới hạn |
| `Map<?, ?>` | Có | Cả hai đối số đều là `?` |
| `List` | Có | Raw type, nhưng mất kiểm tra generic khi sử dụng |
| `String[]`, `List<?>[]` | Có | Kiểu phần tử của mảng reifiable |
| `List<String>` | **Không** | Đối số cụ thể `String` bị erasure |
| `List<Integer>` | **Không** | Đối số cụ thể `Integer` bị erasure |
| `List<? extends Number>` | **Không** | Wildcard có bound, không phải `?` |
| `List<? super String>` | **Không** | Wildcard có bound |
| `Map<String, ?>` | **Không** | Chưa phải *mọi* đối số đều `?` |
| Biến kiểu `T` trong `<T>` | **Không** | Kiểu `T` không sẵn có đầy đủ tại runtime |
| `List<String>[]` | **Không** | Thành phần `List<String>` không reifiable |

**Chú ý:** Reifiable không có nghĩa là “kiểu chứa mọi thông tin nghiệp vụ”. `List<?>` là reifiable, nhưng chỉ xác nhận đối tượng thuộc một triển khai `List`, **không xác nhận kiểu từng phần tử**.

## 3. Cách viết `instanceof` thường dùng khi đầu vào là `Object`

Có hai hình thức gần nhau:

~~~java
Object input = java.util.List.of("a", "b");

boolean oldForm = input instanceof java.util.List<?>;

if (input instanceof java.util.List<?> items) {
    System.out.println(items.size()); // items có kiểu List<?>.
}
~~~

- `input instanceof List<?>` là **type comparison**, trả về `boolean`.
- `input instanceof List<?> items` là **type pattern**, vừa kiểm tra vừa khai báo biến `items` có kiểu tĩnh `List<?>` nếu match thành công.
- `items` chưa có kiểu `List<String>`. Khi lấy một phần tử bằng `items.get(0)`, bạn chỉ được phép xem nó an toàn như một `Object`; nếu muốn biết nó có phải `String`, phải kiểm tra riêng.
- `input == null` không khớp; cả type comparison lẫn type pattern trong Java 17 đều trả `false` nếu đầu vào là `null`.

Từ `Object`, đây là cách kiểm tra đáng tin cậy khi bạn chưa có chứng cứ tĩnh về đối số generic. Lối viết với wildcard thường nên ưu tiên hơn raw type:

~~~java
Object input = java.util.List.of(1, 2);

// Hợp lệ nhưng dùng raw type:
if (input instanceof java.util.List) {
    System.out.println("Có một danh sách");
}

// Ưu tiên:
if (input instanceof java.util.List<?> elements) {
    System.out.println("Kích thước: " + elements.size());
}
~~~

Raw `List` có thể tạo cảnh báo và mất kiểm tra generic ở các thao tác khác, còn `List<?>` biểu diễn đúng rằng ta **chưa biết kiểu phần tử**.

## 4. Vì sao `Object instanceof List<String>` bị từ chối?

Đoạn sau **cố ý không biên dịch** trong Java 17:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<String> words) { // ERROR
    System.out.println(words.get(0));
}
~~~

Bản dùng type comparison cũng bị từ chối trong cùng điều kiện:

~~~java
Object input = java.util.List.of("a", "b");

boolean ok = input instanceof java.util.List<String>; // ERROR
~~~

**Không phải vì đối tượng tình cờ chứa String hay Integer.** Lỗi do compiler chỉ biết kiểu tĩnh của `input` là `Object`. Một cast từ `Object` sang `List<String>` không thể kiểm tra đầy đủ phần `<String>` khi chạy; đó là *unchecked cast*, nên `instanceof` không cho phép phép thử như vậy từ nguồn `Object`.

Nếu muốn biết một `Object` là danh sách và chứa toàn `String`, cần hai bước riêng:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<?> items) {
    boolean allStrings = items.stream()
            .allMatch(item -> item instanceof String);
    System.out.println(allStrings);
}
~~~

Bước một xác nhận đối tượng là `List`. Bước hai thực sự kiểm tra **mỗi phần tử hiện có**. Với danh sách rỗng, `allMatch` trả `true` theo tính chất logic của lượng từ “mọi”; điều đó vẫn **không chứng minh một tham số generic runtime `String`**. Hãy phân biệt “mọi phần tử hiện tại đều là chuỗi” và “đối tượng mang kiểu generic `List<String>` tại runtime”.

## 5. Ngoại lệ từ Java 16: RHS không reifiable vẫn có thể hợp lệ

Đây là điểm đặc biệt quan trọng, thường bị bỏ sót trong các bài hướng dẫn cũ.

Trước Java 16, **type comparison** sau `instanceof` đòi kiểu tham chiếu phải là reifiable. **Từ Java 16**, yêu cầu này được nới lỏng: một số kiểu tham số hóa không reifiable vẫn được dùng nếu **biểu thức bên trái downcast-compatible với kiểu cần thử**. JLS Java 17 `15.20.2 nêu rõ ví dụ sau.

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>();
boolean check = values instanceof ArrayList<Integer>; // HỢP LỆ từ Java 16.
System.out.println(check); // true
~~~

Ở đây:

- `List<Integer>` là **kiểu tĩnh của target**; compiler đã biết đối số kiểu `Integer` của tham chiếu.
- `ArrayList<Integer>` là lớp triển khai cụ thể hơn của `List<Integer>`; ép kiểu giữa hai kiểu này **được kiểm tra bằng runtime class test**, đồng thời sự phù hợp của `<Integer>` đã có từ thông tin kiểu tĩnh.
- Runtime kiểm tra đối tượng có phải `ArrayList` hay không; **nó không đọc hoặc kiểm tra mọi phần tử là `Integer`**.
- Nếu `values` thực tế tham chiếu đến một triển khai `List` khác, phép thử hợp lệ vẫn trả `false`.

Dạng type pattern tương ứng cũng hợp lệ:

~~~java
List<Integer> values = new ArrayList<>();

if (values instanceof ArrayList<Integer> actual) {
    System.out.println(actual.size()); // actual có kiểu ArrayList<Integer>.
}
~~~

**Không được tổng quát hóa thành “Java 17 cho phép mọi generic trong instanceof”.** Đoạn tiếp theo **cố ý không biên dịch**:

~~~java
List<Integer> values = new ArrayList<>();

boolean wrong = values instanceof ArrayList<String>; // ERROR: generic không tương thích.
~~~

Compiler biết từ `List<Integer>` rằng target không có phép downcast hợp lệ thành `ArrayList<String>` theo quy tắc kiểu của Java. Đổi tên lớp triển khai hay giả định giá trị runtime không vượt qua được phép kiểm tra này.

### Một kiểu không reifiable có thể xuất hiện sau `instanceof` mà vẫn hợp lệ như thế nào?

Có ba câu hỏi cần trả lời:

1. **Kiểu tĩnh của biểu thức bên trái là gì?** `Object` khác với `List<Integer>`.
2. **Kiểu cần thử ở bên phải là gì?** `List<?>` reifiable, `ArrayList<Integer>` không reifiable.
3. **Có phép downcast được kiểm tra hợp lệ giữa hai kiểu hay không?** Nếu hợp lệ, Java 17 có thể chấp nhận ngay cả khi RHS không reifiable; nếu chuyển đổi chỉ có thể unchecked hoặc các đối số generic mâu thuẫn, compiler từ chối.

**So sánh nhanh:**

~~~java
Object obj = new ArrayList<Integer>();
// obj instanceof ArrayList<Integer>; // ERROR: Object không đủ chứng cứ generic.

List<Integer> typed = new ArrayList<>();
boolean ok = typed instanceof ArrayList<Integer>; // OK: kiểu tĩnh giữ Integer.
~~~

Đây là lý do cần nói chính xác **“reifiable thường là lựa chọn thích hợp cho kiểm tra runtime từ Object”**, thay vì phát biểu sai rằng **mọi RHS của instanceof luôn bắt buộc reifiable**.

## 6. Phân biệt type comparison và type pattern trong Java 17

Hai biến thể của `instanceof` có quy tắc bổ sung khác nhau:

~~~java
List<Integer> input = new ArrayList<>();

boolean b = input instanceof List<Integer>; // Hợp lệ: type comparison.
~~~

Tuy nhiên, với **pattern match operator** trong **Java 17**, nếu kiểu tĩnh của biểu thức target đã là **subtype của kiểu pattern**, compiler từ chối một pattern luôn match đối với giá trị khác `null`:

~~~java
List<Integer> input = new ArrayList<>();

if (input instanceof List<Integer> items) { // ERROR ở Java 17.
    System.out.println(items.size());
}
~~~

Cách xử lý trong trường hợp này đơn giản là dùng `input` trực tiếp. Đây là giới hạn về **unconditional pattern** ở Java 17, **khác** với giới hạn reifiable. Đừng lẫn nó với trường hợp `List<Integer> input instanceof ArrayList<Integer> actual` ở phần 5: khi target là interface `List`, nó **chưa chắc** là `ArrayList`.

**Lưu ý phiên bản:** Java 21 điều chỉnh quy tắc dành cho unconditional patterns. Trong bài này, mọi kết luận về lỗi của type pattern bao phủ toàn bộ kiểu tĩnh được giới hạn rõ cho **Java 17**, không áp máy móc cho mọi JDK mới hơn.

## 7. Array và type variable: thêm hai trường hợp dễ nhầm

### 7.1. Array có kiểu phần tử reifiable

~~~java
Object a = new String[] {"a", "b"};
System.out.println(a instanceof String[]); // true

Object b = new java.util.List<?>[] {
    java.util.List.of("x"),
    java.util.List.of(10)
};
System.out.println(b instanceof java.util.List<?>[]); // true
~~~

`String[]` và `List<?>[]` đều reifiable. Nhưng với `List<?>[]`, runtime chỉ có thể xác nhận hình dạng **mảng của danh sách**, không xác nhận phần tử **bên trong từng List** là kiểu nào.

Các kiểu như `List<String>[]` **không reifiable**, và không được tạo trực tiếp bằng `new List<String>[n]`. Cơ chế này ngăn một số trường hợp *heap pollution* do mảng hỗ trợ kiểm tra kiểu thành phần tại runtime nhưng generic arguments lại bị erasure.

### 7.2. Biến kiểu `T` không phải kiểu đích runtime cho `instanceof`

Đoạn sau **cố ý không biên dịch** trong Java 17:

~~~java
static <T> boolean check(Object input) {
    return input instanceof T; // ERROR: không có kiểu runtime T để kiểm tra.
}
~~~

Nếu kiểu cần kiểm tra đến từ tham số runtime, có thể dùng `Class<T>`:

~~~java
static <T> boolean isType(Object value, Class<T> type) {
    return type.isInstance(value);
}

System.out.println(isType("Java", String.class)); // true
System.out.println(isType(42, String.class));     // false
~~~

Đây chỉ là **đoạn minh họa trong ngữ cảnh lớp/phương thức**, chưa phải chương trình độc lập. `Class<T>.isInstance` kiểm tra một **lớp runtime**, không cung cấp `List<String>.class`. Java không hỗ trợ class literal chứa tham số kiểu cụ thể như `List<String>.class`.

### 7.3. `null` và kiểu primitive

Trong Java 17:

- `null instanceof List<?>` là `false` nếu cách viết được đặt trong ngữ cảnh biểu thức hợp lệ.
- `input instanceof List<?> items` không khởi tạo `items` khi `input == null`.
- `int` là kiểu primitive được JLS `4.7 liệt kê là reifiable, nhưng `instanceof int` **không được hỗ trợ trong Java 17**. Với số nguyên đóng hộp, kiểm tra kiểu tham chiếu `Integer` là hợp lệ khi kiểu tĩnh nguồn cho phép.

## 8. Chương trình hoàn chỉnh: kiểm tra đúng kiểu, đúng giới hạn (Java 17)

Lưu nguyên mã dưới đây trong **`ReifiableInstanceofDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReifiableInstanceofDemo {

    static String inspect(Object value) {
        if (!(value instanceof List<?> items)) {
            return "not a list";
        }

        int strings = 0;
        for (Object item : items) {
            if (item instanceof String text) {
                strings++;
            }
        }
        return "list size=" + items.size() + ", strings=" + strings;
    }

    static boolean isArrayListOfIntegers(List<Integer> input) {
        // Không reifiable, nhưng phép thử hợp lệ vì kiểu tĩnh là List<Integer>.
        return input instanceof ArrayList<Integer>;
    }

    static String arrayKind(Object input) {
        if (input instanceof List<?>[] rows) {
            return "array of lists, length=" + rows.length;
        }
        return "not an array of lists";
    }

    public static void main(String[] args) {
        System.out.println(inspect(List.of("A", 10, "B")));
        System.out.println(inspect("not list"));
        System.out.println(inspect(null));

        System.out.println(isArrayListOfIntegers(
                new ArrayList<>(List.of(1, 2))));
        System.out.println(isArrayListOfIntegers(List.of(1, 2)));

        System.out.println(arrayKind(new List<?>[] {
                List.of("X"),
                List.of(7)
        }));
    }
}
~~~

Dùng JDK 17 trở lên để biên dịch theo quy tắc Java 17:

~~~bash
javac --release 17 ReifiableInstanceofDemo.java
java ReifiableInstanceofDemo
~~~

**Stdout chính xác:**

~~~text
list size=3, strings=2
not a list
not a list
true
false
array of lists, length=2
~~~

Đọc kết quả:

1. `List.of("A", 10, "B")` là một `List` có ba phần tử; **hai phần tử** match `String`. Kiểm tra `List<?>` không đòi mọi phần tử cùng kiểu.
2. `"not list"` và `null` đều không match `List<?>`, nên trả `not a list`.
3. `new ArrayList<>(...)` khớp `ArrayList<Integer>` khi target đã được khai báo `List<Integer>`; một danh sách tạo bởi `List.of(...)` không phải `ArrayList`, nên dòng tiếp theo là `false`.
4. Một mảng của `List<?>` được nhận diện đúng; không hề có phép kiểm tra kiểu generic của các phần tử bên trong hai danh sách.

**Giới hạn của kiểm chứng:** ví dụ chứng minh code biên dịch và runtime phân biệt các lớp/danh sách như mô tả; nó không biến generic arguments thành dữ liệu runtime.

## 9. Cast generic và “false sense of safety”

Đây là đoạn **cố ý minh họa rủi ro**, có thể chạy nhưng không nên dùng để kiểm chứng dữ liệu:

~~~java
Object input = java.util.List.of(7, 8);

@SuppressWarnings("unchecked")
java.util.List<String> unsafe = (java.util.List<String>) input;

// Cast ở trên có thể qua được kiểm tra runtime lớp List;
// lỗi thường chỉ bộc lộ khi cố đọc Integer như String.
String first = unsafe.get(0); // ClassCastException.
~~~

Annotation `@SuppressWarnings("unchecked")` chỉ **ẩn cảnh báo**; nó không bổ sung kiểu `String` vào danh sách tại runtime. Tình trạng tham chiếu hoặc cấu trúc generic lưu giá trị không đúng hợp đồng kiểu là một dạng rủi ro *heap pollution*.

**Cách an toàn:** đọc đầu vào như `List<?>`, kiểm tra từng phần tử, và tạo một danh sách kết quả đúng kiểu:

~~~java
static List<String> checkedStrings(Object input) {
    if (!(input instanceof List<?> values)) {
        throw new IllegalArgumentException("Not a list");
    }

    List<String> result = new ArrayList<>();
    for (Object item : values) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Not a string: " + item);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
~~~

Đây là **phương thức minh họa** đặt trong lớp đã import `java.util.List`, `java.util.ArrayList`. Với đầu vào bất biến và chỉ chứa chuỗi, nó tạo bản sao `List<String>` an toàn **mà không cần unchecked cast**. Với danh sách có phần tử khác `String`, nó ném ngoại lệ có chủ đích.

Đừng nhầm:

- `input instanceof List<?>`: xác nhận **loại đối tượng chứa**.
- `item instanceof String`: xác nhận **một phần tử cụ thể**.
- `(List<String>) input`: yêu cầu compiler tin vào cast **không kiểm tra đầy đủ tham số generic**.
- `typedList instanceof ArrayList<Integer>` với target đã là `List<Integer>`: phép thử lớp cụ thể được compiler chấp nhận dựa trên chứng cứ **kiểu tĩnh**, không phải kiểm tra từng phần tử.

## 10. Quy trình chọn phép kiểm tra phù hợp

Khi viết `instanceof` liên quan đến generic:

1. **Xác định kiểu tĩnh bên trái**: `Object`, `List<?>`, `List<Integer>`, hay kiểu khác.
2. **Xác định mục tiêu thực sự**: kiểm tra đối tượng là một danh sách, một lớp triển khai cụ thể, một mảng, hay kiểm tra từng phần tử.
3. **Ưu tiên reifiable type** nếu chưa biết đối số kiểu: `List<?>`, `Map<?, ?>`, `List<?>[]`, `String[]`. Tránh raw type khi có thể.
4. **Nếu RHS không reifiable**, hỏi compiler có thể chứng minh phép downcast được kiểm tra an toàn nhờ kiểu tĩnh không. Ví dụ `List<Integer>` sang `ArrayList<Integer>` là trường hợp hợp lệ trong Java 17.
5. **Nếu cần ràng buộc kiểu phần tử**, kiểm tra từng giá trị và xây dựng kết quả có kiểu chính xác; đừng coi `instanceof List<?>` hoặc unchecked cast là chứng cứ.
6. **Xét null, kiểu tĩnh đã là subtype và phiên bản Java**. `instanceof` trên `null` không match; Java 17 còn có quy tắc chống unconditional **type pattern**.

### Các sai lầm thường gặp

- **“Mọi kiểu sau instanceof phải reifiable trên Java 17.”** Sai. Java 16 đã nới lỏng yêu cầu cho type comparison; Java 17 có thể chấp nhận `List<Integer> instanceof ArrayList<Integer>`.
- **“Java 17 cho phép Object instanceof List<String>.”** Sai. `Object` không bảo đảm kiểu generic `String`; phép chuyển chỉ có thể unchecked.
- **“List<?> là List<String> ở runtime.”** Sai. Wildcard không giới hạn giữ thông tin về lớp danh sách, không về phần tử.
- **“List<? extends Number> cũng reifiable như List<?>.”** Sai. Theo JLS `4.7, wildcard có bound không thỏa điều kiện “mọi đối số đều là unbounded wildcard”.
- **“instanceof kiểm tra từng phần tử.”** Sai. Một danh sách có cả `String` và `Integer` vẫn match `List<?>`.
- **“Raw List tốt hơn List<?> vì reifiable.”** Cả hai reifiable, nhưng `List<?>` thường giữ ràng buộc kiểu tốt hơn.
- **“SuppressWarnings khiến cast generic an toàn.”** Sai. Cảnh báo bị ẩn, thông tin runtime không được bổ sung.
- **“Primitive là reifiable nên dùng instanceof int trong Java 17.”** Sai. Đây là hai quy tắc ngôn ngữ khác nhau.
- **“Pattern và type comparison có mọi luật giống nhau.”** Sai. Java 17 từ chối một số type pattern đã được bảo đảm bởi kiểu tĩnh, dù type comparison tương đương hợp lệ.

## 11. Tự kiểm tra

**Câu 1.** Phân loại `List<?>`, `List<String>`, `Map<?, ?>`, `Map<String, ?>`, `String[]`, `List<?>[]` thành reifiable và không reifiable. Giải thích.

**Câu 2.** Với `Object input = List.of("a")`, biểu thức `input instanceof List<String>` có biên dịch ở Java 17 không? Nếu đổi thành `input instanceof List<?>` thì sao?

**Câu 3.** Với `List<Integer> values = new ArrayList<>()`, tại sao `values instanceof ArrayList<Integer>` lại hợp lệ, dù `ArrayList<Integer>` không reifiable?

**Câu 4.** Với cùng biến `values`, điều gì xảy ra khi thay RHS thành `ArrayList<String>`? Tại sao?

**Câu 5.** `input instanceof List<?> items` trả `true` có chứng minh `items.get(0)` là `String` không? Nêu một cách kiểm tra thực tế.

**Câu 6.** Vì sao `List<Integer> values = new ArrayList<>(); values instanceof List<Integer> items` bị từ chối dưới Java 17, trong khi `values instanceof List<Integer>` (không binding) lại được chấp nhận?

**Câu 7.** `Object array = new List<?>[]{List.of("x"), List.of(42)};`. `array instanceof List<?>[]` trả gì? Có chứng minh các danh sách bên trong có cùng kiểu phần tử không?

**Câu 8.** Vì sao trong phương thức generic `<T> boolean isT(Object x)` không thể dùng `x instanceof T`? Phương án thay thế nào dùng được khi nhận `Class<T>`?

### Đáp án và giải thích

1. **Reifiable:** `List<?>`, `Map<?, ?>`, `String[]`, `List<?>[]`. **Không reifiable:** `List<String>`, `Map<String, ?>`. Với generic tham số hóa, tất cả đối số phải là `?` không giới hạn.
2. **`List<String>`: lỗi biên dịch** do nguồn `Object` không thể downcast kiểm tra đầy đủ đối số generic. **`List<?>`: hợp lệ**, kết quả `true` với đối tượng `List.of("a")`.
3. `List<Integer>` ở nguồn đã mang chứng cứ tĩnh `Integer`; runtime chỉ cần thử xem triển khai có phải `ArrayList`. Đây là nới lỏng từ Java 16.
4. **Lỗi biên dịch**: `ArrayList<String>` không tương thích với `List<Integer>` ở nguồn theo quy tắc cast của Java.
5. **Không**. Đọc phần tử thành `Object` rồi kiểm tra `item instanceof String text` hoặc kiểm tra toàn bộ và sao chép.
6. Ở Java 17, **type pattern bao phủ kiểu tĩnh** bị từ chối là unconditional pattern; type comparison không tạo pattern variable nên không áp dụng đúng giới hạn đó.
7. **`true`**: đây là mảng `List<?>[]`. Không có xác nhận nào về kiểu phần tử ở từng danh sách.
8. `T` là type variable, thông tin type argument không tồn tại đầy đủ tại runtime; có thể dùng `type.isInstance(x)` với một tham số `Class<T> type` để kiểm tra lớp runtime (không xác minh generic arguments).

## Tài liệu tham khảo chính thức

- [Java Language Specification 17, `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): cơ chế xóa kiểu.
- [Java Language Specification 17, `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): định nghĩa chính thức và các nhóm kiểu reifiable.
- [Java Language Specification 17, `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type comparison, pattern match, tính tương thích và thay đổi từ Java 16.
- [Java Language Specification 17, `14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): yêu cầu đối với type pattern và kiểu biến pattern.
- [Java Language Specification 17, `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): checked/unchecked casting conversions.
