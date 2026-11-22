# Đọc lỗi incompatible types, capture và incompatible bounds trong Java Generics

## 1. Mục tiêu học tập

Các thông báo lỗi Generics của `javac` thường chứa những từ như `incompatible types`, `capture of ?`, `CAP#1`, `inference variable T has incompatible bounds`, `equality constraints`, `upper bounds` hay `lower bounds`. Chúng trông phức tạp, nhưng phần lớn diễn đạt một câu hỏi rất cụ thể:

> Trình biên dịch có đủ bằng chứng rằng giá trị đang được truyền, gán hoặc trả về thỏa **mọi ràng buộc kiểu** tại vị trí sử dụng hay không?

Muốn sửa đúng, cần xác định lỗi do **quan hệ subtype không hợp lệ**, **wildcard chưa biết bị capture**, hay **hệ suy luận generic không tìm ra một kiểu thỏa đồng thời các điều kiện**. Ba tình huống này liên quan nhau, nhưng không có cùng cách khắc phục.

Bài này giúp bạn:

- Tách một diagnostic `javac` thành vị trí lỗi, `required`, `found`, nguyên nhân và phần `where`.
- Nhận ra Java Generics **invariant**: `List<Integer>` không phải `List<Number>`.
- Hiểu `CAP#1`/`CAP#2` là các kiểu chưa biết được tạo bởi *capture conversion*, không phải một class runtime tên CAP.
- Biết tại sao `List<? extends Number>` đọc Number an toàn nhưng không thêm Integer tùy ý.
- Dùng helper method `<T>` khi cần giữ cùng một kiểu phần tử chưa biết bên trong **một** List.
- Dùng `? extends T` và `? super T` khi chuyển dữ liệu giữa hai collection với quan hệ kiểu rõ ràng.
- Đọc các ràng buộc `equality`, `upper` và `lower` khi compiler báo `incompatible bounds`.
- Phân biệt lỗi generic ở compile time với `ClassCastException`/`ArrayStoreException` phát sinh ở runtime.
- Kiểm tra các ví dụ đúng và sai trên Java 17+, không đoán chừng output hoặc thông điệp compiler.

## 2. Bản đồ ba nhóm lỗi

| Nhóm | Dấu hiệu diagnostic thường gặp | Bản chất |
| --- | --- | --- |
| Không tương thích kiểu | `incompatible types: X cannot be converted to Y` | Kiểu X không thể gán vào vị trí đòi Y theo các phép chuyển đổi được Java cho phép. |
| Wildcard capture | `CAP#1`, `CAP#2`, `capture of ?`, `capture of ? extends Number` | Compiler biểu diễn một kiểu thực nhưng chưa biết phía sau wildcard. |
| Ràng buộc suy luận xung đột | `inference variable T has incompatible bounds` hoặc `inferred type does not conform to upper bound(s)` | Không tìm được type argument T đáp ứng cùng lúc các điều kiện từ target, đối số và bounds. |

Một diagnostic có thể xuất hiện dưới nhiều lớp thông báo. Ví dụ lời gọi `accepts(xs, 10)` có thể bắt đầu bằng “method cannot be applied to given types”, nhưng nguyên nhân bên trong là “inference variable T has incompatible bounds” và còn nhắc `CAP#1`. Vì vậy đừng chỉ đọc dòng đầu hoặc chỉ nhìn từ `error`.

### Cách tiếp cận chung

Đọc lỗi theo thứ tự:

1. **Dòng được chỉ ra:** phép gán, lời gọi, biểu thức trả về hay thao tác `add/set` nào thất bại?
2. **Kiểu đích:** compiler yêu cầu gì (`required`, target type, kiểu của biến)?
3. **Kiểu nguồn:** compiler có gì (`found`, actual argument, expression type)?
4. **Quan hệ cần chứng minh:** subtype, invariant generic, wildcard bound, hoặc type-variable constraint?
5. **Thông tin bổ sung:** `where`, `equality constraints`, `upper bounds`, `lower bounds`, `CAP#n`.
6. **Ý định nghiệp vụ:** muốn đọc, ghi, chuyển kiểu, hay liên kết hai input? Chọn sửa chữ ký đúng mục tiêu, không cast mù quáng.

Để javac đưa thêm bằng chứng, dùng `-Xdiags:verbose`. Các mẫu lỗi ở phần sau đã được chạy bằng:

```bash
javac --release 17 -Xdiags:verbose FileName.java
```

Nội dung chi tiết của thông báo có thể thay đổi giữa các bản JDK; hãy đọc **quan hệ kiểu** mà diagnostic thể hiện, không phụ thuộc vào số thứ tự CAP hoặc cách xuống dòng.

## 3. `incompatible types`: bắt đầu từ quan hệ gán

### 3.1. Invariance: List Integer không phải List Number

**Tệp `IncompatibleInvariant.java` — cố ý không biên dịch:**

```java
import java.util.ArrayList;
import java.util.List;

class IncompatibleInvariant {
    List<Number> values = new ArrayList<Integer>();
}
```

`javac --release 17 -Xdiags:verbose IncompatibleInvariant.java` đã trả về thông báo chính:

```text
error: incompatible types:
ArrayList<Integer> cannot be converted to List<Number>
```

**Tại sao?** Integer là subtype của Number, nhưng generic types thường **invariant**: `List<Integer>` không tự là subtype của `List<Number>`.

Nếu phép gán trên được cho phép, một biến `List<Number>` có thể thêm Double vào đối tượng thật sự là `ArrayList<Integer>`, phá vỡ hợp đồng phần tử Integer:

```java
// Giả sử phép gán bị cấm phía trên được phép:
List<Number> wider = new ArrayList<Integer>();
wider.add(3.14);  // Sẽ làm hỏng danh sách Integer.
```

Đây là mã minh họa *cố ý không hợp lệ*, không phải chương trình có thể chạy.

### 3.2. Cách sửa tùy mục tiêu

**Mục tiêu A — muốn một danh sách có thể chứa mọi Number:**

```java
List<Number> numbers = new ArrayList<>();
numbers.add(10);
numbers.add(3.14);
```

Ở đây object được tạo là `ArrayList<Number>` theo target typing, nên thêm cả Integer và Double là hợp lệ.

**Mục tiêu B — chỉ cần đọc các Number từ List Integer:**

```java
List<Integer> integers = List.of(1, 2);
List<? extends Number> source = integers;
Number first = source.get(0);
```

Wildcard cho phép đọc Number mà **không hứa** rằng caller được thêm một Number tùy ý vào list nguồn.

**Mục tiêu C — cần một bản sao có khả năng thêm các Number khác:**

```java
List<Integer> integers = List.of(1, 2);
List<Number> copy = new ArrayList<>(integers);
copy.add(3.14);
```

Bạn đã tạo một list mới với kiểu phần tử Number. Đây không phải ép `List<Integer>` thành `List<Number>`; dữ liệu được sao chép vào container có contract khác.

### 3.3. Vì sao `List<Number> x = List.of(1, 2)` có thể hợp lệ?

Cần phân biệt:

```java
List<Number> a = List.of(1, 2);             // Hợp lệ.
List<Number> b = new ArrayList<>(List.of(1, 2)); // Hợp lệ.
// List<Number> c = new ArrayList<Integer>();   // Không hợp lệ.
```

Ở hai dòng đầu, compiler có thể dùng **kiểu đích** để suy luận generic arguments của `List.of` hoặc diamond sao cho kết quả có kiểu phù hợp `List<Number>`. Ở dòng cuối, kiểu tham số hóa cụ thể `ArrayList<Integer>` đã được viết tường minh, nên không thể chuyển nó thành `List<Number>`.

Một lỗi debug phổ biến là thấy hai dòng đều “chứa Integer” rồi kết luận compiler hành xử không nhất quán. Thực tế, một bên là **generic method/constructor inference** và bên kia là **invariance của một kiểu đã xác định**.

## 4. Return type cũng có thể tạo `incompatible bounds`

**Tệp `IncompatibleReturn.java` — cố ý không biên dịch:**

```java
import java.util.List;

class IncompatibleReturn {
    static List<String> values() {
        return List.of(1, 2);
    }
}
```

Khi chạy `javac --release 17 -Xdiags:verbose`, thông báo chính đã quan sát:

```text
error: incompatible types: inference variable E has incompatible bounds
    equality constraints: String
    lower bounds: Integer
```

Tại sao nó không chỉ báo đơn giản “Integer cannot be converted to String”?

`List.of(E,E)` là **generic method**. Compiler phải tìm E đáp ứng hai nguồn ràng buộc:

- Giá trị trả về được mong đợi là `List<String>`; điều này ép cấu trúc `List<E>` phù hợp với kiểu đích, tạo điều kiện đòi E=String trong ngữ cảnh này.
- Hai đối số `1`, `2` có kiểu Integer sau boxing; E phải có thể nhận Integer.

Không có E vừa thỏa yêu cầu tương ứng String vừa chứa Integer. Compiler trình bày bài toán như tập ràng buộc **incompatible bounds**.

Cách sửa là đổi **dữ liệu**, **kiểu trả về**, hoặc thực hiện **chuyển đổi có chủ đích**:

```java
static List<String> strings() {
    return List.of("1", "2");
}

static List<Integer> integers() {
    return List.of(1, 2);
}

static List<String> convertNumbers() {
    return List.of(1, 2).stream().map(String::valueOf).toList();
}
```

Không được dùng unchecked cast để biến List Integer thành List String. Nếu nghiệp vụ cần String, phải tạo các String thực.

## 5. Capture conversion: `CAP#1` không phải class runtime

### 5.1. Wildcard biểu diễn một kiểu chưa biết

Khai báo:

```java
List<? extends Number> numbers;
```

có nghĩa là: một List có phần tử thuộc **một subtype cụ thể nào đó của Number mà phía sử dụng chưa biết**. Nó có thể đang là `List<Integer>`, `List<Double>` hoặc một subtype Number khác.

Compiler thực hiện *capture conversion*, gán một tên nội bộ cho kiểu chưa biết ấy, ví dụ `CAP#1`. Tên này chỉ xuất hiện trong chẩn đoán của compiler; nó không tồn tại như một class Java mà bạn có thể `new CAP#1()` hoặc `instanceof CAP#1`.

Với `List<? extends Number>`, compiler biết **CAP là subtype của Number**. Nó **không biết CAP chính là Integer**, dù code vừa đọc ra một Integer từ một đường khác.

### 5.2. Đọc Number được, ghi Integer không chắc an toàn

**Tệp `CaptureAdd.java` — cố ý không biên dịch:**

```java
import java.util.List;

class CaptureAdd {
    static void add(List<? extends Number> numbers) {
        numbers.add(42);
    }
}
```

Chạy:

```bash
javac --release 17 -Xdiags:verbose CaptureAdd.java
```

Đoạn chẩn đoán đã kiểm chứng:

```text
error: no suitable method found for add(int)
method List.add(CAP#1) is not applicable
(argument mismatch; int cannot be converted to CAP#1)
CAP#1 extends Number from capture of ? extends Number
```

Điều này là hợp lý. Caller có thể truyền vào `List<Double>`; nếu method được phép thêm Integer 42, contract Double sẽ bị phá vỡ.

Đọc vẫn được:

```java
static Number firstNumber(List<? extends Number> list) {
    return list.get(0);
}
```

Vì CAP là subtype của Number, giá trị đọc được có thể dùng dưới loại Number.

**Ngoại lệ cần nhớ:** Java cho phép truyền `null` vào nhiều thao tác add với wildcard capture, vì null tương thích mọi reference type. Nhưng điều đó **không** có nghĩa có thể thêm một giá trị non-null tùy ý vào `List<? extends Number>`. Với một API chỉ đọc, đừng dựa vào khả năng thêm null để sửa dữ liệu.

## 6. Tại sao `List<?>.set(index, list.get(...))` vẫn có thể lỗi?

Một tình huống nhìn có vẻ vô lý: cùng một list, lấy phần tử ra rồi gán vào vị trí khác, tại sao compiler lại báo CAP?

**Tệp `CaptureSet.java` — cố ý không biên dịch:**

```java
import java.util.List;

class CaptureSet {
    static void move(List<?> values) {
        values.set(1, values.get(0));
    }
}
```

Với `-Xdiags:verbose`, compiler đã báo:

```text
method set in interface List<E> cannot be applied to given types
required: int,CAP#1
found:    int,CAP#2
reason: argument mismatch; Object cannot be converted to CAP#1
CAP#1 extends Object from capture of ?
CAP#2 extends Object from capture of ?
```

**Cốt lõi:** Hai lần sử dụng một biểu thức có wildcard có thể được capture riêng, nên compiler không có chứng cứ rằng `CAP#1` và `CAP#2` đồng nhất cho thao tác set. Dù con người nhìn thấy cùng một biến `values`, hệ thống kiểu không thể dựa vào hai capture độc lập để tự cho phép ghi.

### 6.1. Cách sửa đúng: generic capture helper

Chuyển đầu vào wildcard **một lần** vào method có một type variable T:

```java
static void replaceSecondUnknown(List<?> values) {
    replaceSecondWithFirst(values);
}

private static <T> void replaceSecondWithFirst(List<T> values) {
    values.set(1, values.get(0));
}
```

Trong helper:

- T đại diện cho **kiểu phần tử chưa biết nhưng nhất quán của một List cụ thể**.
- `get(0)` trả T.
- `set(1, T)` nhận chính T.
- Compiler có bằng chứng đầy đủ để cho phép phép gán.

Caller không cần biết T là gì. Khi gọi helper, capture conversion và generic inference dùng một T để diễn đạt sự nhất quán.

**Điều kiện:** List có ít nhất hai phần tử và phải hỗ trợ `set`. Ví dụ `List.of("A","B")` không cho sửa và sẽ ném `UnsupportedOperationException` ở runtime; helper chỉ giải quyết **vấn đề kiểu**, không bảo đảm collection mutable hoặc chỉ số hợp lệ.

Một test hợp lệ:

```java
List<String> words = new ArrayList<>(List.of("A", "B"));
replaceSecondUnknown(words);
System.out.println(words); // [A, A]
```

Chương trình Java 17 hoàn chỉnh ở phần 11 chứa chính helper và test này.

### 6.2. Khi nào cần helper, khi nào không?

Dùng helper khi:

- Một phương thức public có lý do chính đáng để nhận `List<?>`.
- Bên trong cần làm thao tác kiểu-safe mà các vị trí phải dùng **cùng element type chưa biết**.
- Truyền cả list cho một generic method riêng có thể capture nó một lần thành `List<T>`.

Không cần helper chỉ để đọc các phần tử thành Object hoặc xem `size()`:

```java
static void printSize(List<?> list) {
    System.out.println(list.size());
}
```

Không dùng helper như một phép ép kiểu “giải quyết mọi CAP error”: chỉ nên dùng khi có quan hệ T thực sự có thể chứng minh.

## 7. Hai danh sách wildcard là hai kiểu chưa biết

**Tệp `CaptureAcross.java` — cố ý không biên dịch:**

```java
import java.util.List;

class CaptureAcross {
    static void copy(List<?> source, List<?> destination) {
        destination.add(source.get(0));
    }
}
```

Compiler đã báo dạng:

```text
no suitable method found for add(CAP#1)
method List.add(CAP#2) is not applicable
Object cannot be converted to CAP#2
```

`source` có thể là `List<String>`, còn `destination` là `List<Integer>`. Hai wildcard `?` **không đồng nghĩa cùng một loại**. Không có lý do ngôn ngữ nào cho phép chuyển phần tử từ list nguồn sang list đích vô điều kiện.

Không nên “sửa” bằng cast raw:

```java
// Anti-pattern không an toàn:
((List) destination).add(source.get(0));
```

Cast raw làm compiler bớt kiểm tra, nhưng có thể tạo *heap pollution* và gây `ClassCastException` khi code khác đọc theo generic contract.

### 7.1. PECS: mô tả quan hệ nguồn và đích

Nếu mục tiêu là copy từ subtype T vào container nhận T hoặc supertype T, hãy viết:

```java
static <T> void transferFirst(
        List<? extends T> source,
        List<? super T> target) {
    target.add(source.get(0));
}
```

Đây là công thức **Producer Extends, Consumer Super**:

- `source` sản xuất giá trị T ⇒ `? extends T`.
- `target` tiêu thụ giá trị T ⇒ `? super T`.
- T đặt ở cấp method để **liên kết hai tham số**.

Caller:

```java
List<Integer> source = List.of(4, 7);
List<Number> target = new ArrayList<>(List.of(1.5));

transferFirst(source, target);
System.out.println(target); // [1.5, 4]
```

Đây là copy an toàn: Integer là Number và `List<Number>` có thể nhận Integer. Chú ý `target` mutable; nếu dùng `List.of(...)` làm đích, lỗi runtime về mutability vẫn có thể xảy ra.

### 7.2. Không gán bừa cùng một T cho hai container

Một cách viết khác:

```java
static <T> void transferExact(List<T> source, List<T> target) {
    target.add(source.get(0));
}
```

Phương thức có T chung thật, nhưng nó hạn chế hơn với nhu cầu lấy từ List<Integer> và ghi vào List<Number> vì generics invariant. PECS thể hiện quan hệ rộng hơn mà vẫn kiểm tra được.

**Nguyên tắc:** Capture helper khắc phục vấn đề *một wildcard list cần dùng lại một element type*. PECS giải quyết *hai container có quan hệ subtype/supertype rõ ràng*. Đừng trộn hai bài toán.

## 8. `incompatible bounds`: compiler đang giải một hệ ràng buộc

Một generic method có thể tạo nhiều yêu cầu về một biến kiểu T. Compiler phải tìm type arguments thỏa tất cả cùng lúc.

Có thể hiểu trực quan ba nhóm ràng buộc:

| Diagnostic | Cách đọc trực giác | Ví dụ |
| --- | --- | --- |
| `equality constraints: String` | Trong ngữ cảnh đó, T bị buộc phải bằng String về quan hệ kiểu tham số hóa. | Kiểu đích `List<String>` với generic return `List<E>`. |
| `upper bounds: Number` | T bị ràng buộc phải là subtype của Number (hoặc thoả một giới hạn trên tương ứng). | `<T extends Number>`. |
| `lower bounds: Integer` | T phải là supertype của Integer để chấp nhận một giá trị Integer làm T. | Lời gọi generic nhận Integer. |

Đây là cách đọc hữu ích khi debug; thuật toán inference đầy đủ của JLS còn xử lý compatibility constraints, wildcard bounds, capture, intersection types và nhiều tình huống phức tạp khác. Không nên coi bảng như một trình mô phỏng đầy đủ mọi quy tắc inference.

### 8.1. Ràng buộc từ method bound và đối số xung đột

**Tệp `BoundedWrong.java` — cố ý không biên dịch:**

```java
import java.util.List;

class BoundedWrong {
    static <T extends Number> void use(List<T> numbers) {}

    static void demo() {
        use(List.of("A"));
    }
}
```

Chạy:

```bash
javac --release 17 -Xdiags:verbose BoundedWrong.java
```

Compiler đã in phần trọng tâm:

```text
required: List<T>
found:    List<String>
reason: inference variable E has incompatible bounds
upper bounds: Number,Object
lower bounds: String
```

Method yêu cầu T extends Number, nhưng caller đưa List<String>. String không phải subtype Number. Dù compiler có suy luận E từ `List.of`, không có cách suy luận hợp lệ nào biến String thành Number.

Sửa đúng tùy bài toán:

```java
use(List.of(1, 2));           // T tương thích Integer.
use(List.<Number>of(1, 2));   // Chỉ rõ Number nếu cần.
```

Hoặc nếu method thực sự cần xử lý String, hãy thay đổi bound/thuật toán của method. Đừng ép `(List<Number>)(List<?>) List.of("A")`; cast đó không biến String thành Number.

### 8.2. Ràng buộc từ target type và nhiều đối số

**Tệp `IncompatibleBounds.java` — cố ý không biên dịch:**

```java
class IncompatibleBounds {
    static <T> T first(T a, T b) {
        return a;
    }

    static void demo() {
        String value = first("A", 42);
    }
}
```

Trong Java 17 đã kiểm chứng, diagnostic bắt đầu:

```text
incompatible types: inferred type does not conform to upper bound(s)
inferred: INT#1
upper bound(s): String,Object
```

Tiếp theo là chi tiết về *intersection type* `INT#1` và `INT#2`. Điều cần nắm là compiler có thể suy luận một common supertype cho hai đối số String và Integer, nhưng biểu thức kết quả lại bị yêu cầu là String. Không có bằng chứng rằng kết quả của phương thức tổng quát đó phải là String trong trường hợp pha loại.

Các cách sửa:

```java
String a = first("A", "B"); // Hai đối số String.
Object b = first("A", 42);  // Kết quả dùng dưới Object.
```

Không nên đổi `String value` sang raw Object rồi ép String ở bước sau nếu nghiệp vụ thực sự đòi String; cần xác định chính xác đầu vào và output contract mong muốn.

**Nuance quan trọng:** `<T> T first(T a,T b)` không bắt buộc hai argument có cùng runtime class. Compiler có thể suy luận một supertype chung. Vì vậy loại `Object` trong ví dụ sửa hợp lệ không phải “Java bỏ kiểm tra generics”, mà là một phép suy luận khác phù hợp kiểu đích.

## 9. `CAP#1` và `incompatible bounds` có thể cùng xuất hiện

**Tệp `MethodCaptureWrong.java` — cố ý không biên dịch:**

```java
import java.util.List;

class MethodCaptureWrong {
    static <T> void accepts(List<T> values, T item) {}

    static void demo(List<? extends Number> xs) {
        accepts(xs, 10);
    }
}
```

Chương trình tạo một trường hợp có **cả capture và generic inference**. Diagnostic Java 17 chứa:

```text
required: List<T>,T
found:    List<CAP#1>,int
reason: inference variable T has incompatible bounds
equality constraints: CAP#1
lower bounds: Integer
CAP#1 extends Number from capture of ? extends Number
```

Giải thích:

1. Tham số đầu `List<T>` được nối với `List<? extends Number>`, làm inference có một T gắn với captured element type, gọi là CAP#1.
2. Tham số thứ hai `T item` lại nhận Integer (boxing từ `10`).
3. Compiler không thể chứng minh rằng Integer là chính CAP#1. CAP#1 có thể là Double hoặc subtype Number khác.

Đừng chỉ xem dòng “incompatible bounds” rồi tùy tiện bỏ `extends Number`. Vấn đề là **một type chưa biết đã bị gắn với list, trong khi bạn đòi chèn một Integer không có bằng chứng cùng type**.

### Sửa thế nào?

Nếu method chỉ cần **đọc** list, thay contract:

```java
static void inspect(List<? extends Number> xs, Number other) {
    Number first = xs.get(0);
    System.out.println(first + "," + other);
}
```

Nếu cần thêm Integer vào một list, cần một **consumer**:

```java
static void addInteger(List<? super Integer> destination) {
    destination.add(10);
}
```

Nếu method bắt buộc nhận List<T> cùng một giá trị T, caller phải cung cấp một loại có quan hệ đồng nhất thật, ví dụ:

```java
static <T> void accepts(List<T> values, T item) {
    values.add(item);
}

List<Integer> values = new ArrayList<>();
accepts(values, 10);
```

Mỗi thiết kế tương ứng một nghiệp vụ khác nhau. Không có “một cast chữa mọi incompatible bounds”.

## 10. Hiểu đúng `extends` và `super`

| Tham số | Đọc an toàn | Ghi an toàn | Mục đích |
| --- | --- | --- | --- |
| `List<T>` | T | T | Một loại T cụ thể được đặt tên trong method/class. |
| `List<? extends T>` | T | Chủ yếu không thêm non-null T tùy ý | Producer: cung cấp các subtype của T. |
| `List<? super T>` | Object | T và subtype của T | Consumer: nhận các giá trị T. |
| `List<?>` | Object | Không thêm non-null tùy ý | Không biết element type; phù hợp khi quan sát chung. |

Ví dụ:

```java
List<? extends Number> input = List.of(1, 2);
Number n = input.get(0);       // Hợp lệ.
// input.add(3);               // Không biên dịch.

List<? super Integer> sink = new ArrayList<Number>();
sink.add(3);                   // Hợp lệ.
Object obj = sink.get(0);      // Đọc dưới Object.
```

Đừng nói `List<? extends Number>` “là List Number” theo nghĩa được thêm bất kỳ Number nào: nó có thể được tạo từ một `List<Integer>` không cho phép Double.

Đừng nói `List<? super Integer>` đọc luôn ra Integer: container có thể thật là `List<Object>`, và compiler chỉ bảo đảm kết quả đọc được dưới Object.

## 11. Chương trình Java 17 hoàn chỉnh

**Tệp `GenericDiagnosticsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class GenericDiagnosticsDemo {
    static class Animal {}
    static class Dog extends Animal {}
    static class Cat extends Animal {}

    static <T> void replaceSecondWithFirst(List<T> list) {
        list.set(1, list.get(0));
    }

    static void replaceSecondUnknown(List<?> list) {
        replaceSecondWithFirst(list);
    }

    static <T> void transferFirst(
            List<? extends T> source, List<? super T> target) {
        target.add(source.get(0));
    }

    static <T extends Number & Comparable<T>> T max(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    static <T> T first(T a, T b) {
        return a;
    }

    static void showBounds(List<? extends Number> list) {
        Number value = list.get(0);
        System.out.println("readNumber=" + value);
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(List.of(new Dog()));
        List<? extends Animal> animals = dogs;
        System.out.println("extendsReadable=" + (animals.get(0) instanceof Dog));

        List<? super Dog> dogSink = new ArrayList<Animal>();
        dogSink.add(new Dog());
        System.out.println("superSize=" + dogSink.size());

        List<String> words = new ArrayList<>(List.of("A", "B"));
        replaceSecondUnknown(words);
        System.out.println("captureHelper=" + words);

        List<Integer> source = List.of(4, 7);
        List<Number> target = new ArrayList<>(List.of(1.5));
        transferFirst(source, target);
        System.out.println("transfer=" + target);

        showBounds(List.of(42));
        System.out.println("boundedMax=" + max(3, 8));
        System.out.println("targetTyped=" + first("A", "B"));
        System.out.println("wildcardCount="
                + Collections.frequency(List.of(1, 1, 2), 1));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -Xlint:all GenericDiagnosticsDemo.java
java GenericDiagnosticsDemo
```

**Stdout đã kiểm chứng:**

```text
extendsReadable=true
superSize=1
captureHelper=[A, A]
transfer=[1.5, 4]
readNumber=42
boundedMax=8
targetTyped=A
wildcardCount=2
```

Chương trình này biên dịch bằng `javac --release 17 -Xlint:all` mà không có warning trong phép thử.

### 11.1. Producer/consumer với kế thừa

`List<Dog>` có thể được dùng dưới `List<? extends Animal>`; đọc được Animal, nhưng không thêm Cat tùy ý. `List<? super Dog>` nhận Dog an toàn, tuy nhiên đọc lại chỉ bảo đảm Object.

### 11.2. Capture helper hoạt động vì chỉ có một T

`replaceSecondUnknown` gọi `replaceSecondWithFirst`. Trong helper, cả giá trị lấy từ `get(0)` và tham số `set(1,...)` cùng một T, nên kết quả `[A,A]` hợp lệ.

### 11.3. PECS chuyển Integer sang Number

`transferFirst` đọc Integer từ nguồn rồi thêm vào một `List<Number>`. Không cần cast, không làm ô nhiễm heap.

### 11.4. Bound của T trong `max`

`<T extends Number & Comparable<T>>` yêu cầu cả hành vi Number và khả năng tự so sánh theo Comparable<T>. Gọi `max(3,8)` cho kết quả 8; không phải mọi cặp Number khác subtype đều thỏa cùng một T. Khi type arguments khác nhau, có thể cần thuật toán/Comparator khác.

### 11.5. Generic method có target type hợp lệ

`first("A","B")` trả giá trị String dưới target String; không mâu thuẫn inference. Đối chiếu trường hợp `String s = first("A",42)` ở phần 8, compiler không có cùng đảm bảo.

## 12. Bảng các tệp lỗi cố ý để luyện đọc

Mỗi ví dụ sau là **một tệp riêng biệt**, không ghép với `GenericDiagnosticsDemo.java` rồi mong build vẫn thành công.

| Tên tệp | Dòng gây lỗi | Chẩn đoán trung tâm |
| --- | --- | --- |
| `IncompatibleInvariant.java` | `List<Number> x = new ArrayList<Integer>();` | `incompatible types ... cannot be converted` |
| `IncompatibleReturn.java` | `return List.of(1,2)` khi return `List<String>` | `inference variable E has incompatible bounds`; equality String, lower Integer |
| `CaptureAdd.java` | `List<? extends Number>.add(42)` | `int cannot be converted to CAP#1` |
| `CaptureSet.java` | `List<?>.set(1,list.get(0))` | `required CAP#1, found CAP#2` |
| `CaptureAcross.java` | `destination.add(source.get(0))` với hai `List<?>` | Hai capture độc lập không chứng minh tương thích |
| `IncompatibleBounds.java` | `String s = first("A",42)` | `inferred type does not conform to upper bound(s)` |
| `BoundedWrong.java` | `use(List.of("A"))` với `T extends Number` | Upper Number xung đột lower String |
| `MethodCaptureWrong.java` | `accepts(xs,10)` với `xs:List<? extends Number>` | Equality CAP#1 xung đột lower Integer |

Một bài test negative compile nên đảm bảo javac **trả mã lỗi khác 0** và message thuộc loại kỳ vọng, chứ không chỉ kiểm tra chương trình “không in gì”. Các diagnostic trên đã được tái hiện với Java 17 và chế độ verbose.

## 13. Lệnh compiler giúp phân tích tốt hơn

### 13.1. Bật diagnostics chi tiết

```bash
javac --release 17 -Xdiags:verbose IncompatibleBounds.java
```

Chế độ verbose thường hiển thị `required/found`, các capture variables và nhiều chi tiết constraint hơn.

### 13.2. Bật cảnh báo generics

```bash
javac --release 17 -Xlint:unchecked,rawtypes GenericDiagnosticsDemo.java
```

Nếu nguồn có raw types hoặc unchecked casts, cảnh báo có thể giúp tìm nơi quan hệ generic bị mất. Trong chương trình hoàn chỉnh phần 11, những lỗi minh họa đã được sửa mà không cần unchecked cast.

### 13.3. Phân biệt lỗi và warning

- `incompatible types`, `generic array creation`, `name clash` và một số lỗi `capture` ở compile time **chặn build**.
- `unchecked cast`/`rawtypes` thường là **cảnh báo** trong ngữ cảnh được Java cho phép.
- `ClassCastException` và `ArrayStoreException` là **ngoại lệ runtime**, thường sau khi có raw alias/unchecked operation hoặc ghi sai vào mảng covariant.

Không nên dùng `@SuppressWarnings("unchecked")` như “cách sửa” cho một lời gọi `add` không hợp lệ. Annotation không biến CAP#1 thành Integer, không tạo quan hệ subtype còn thiếu và không làm thay đổi dữ liệu.

### 13.4. Dùng negative tests đúng cách

Một cách học có hệ thống:

1. Lưu mỗi đoạn lỗi vào tệp mang tên lớp đúng như trong bảng.
2. Biên dịch riêng một tệp.
3. Ghi phần `required`, `found` và `where` hoặc constraints.
4. Chỉ sửa **một yếu tố hợp đồng** mỗi lần: target type, type bound, wildcard hay generic helper.
5. Biên dịch lại để xác nhận.
6. Thêm test chạy cho trường hợp sau sửa, nhất là với collection mutation.

Không đặt nhiều lỗi độc lập vào cùng một file rồi kết luận từ lỗi đầu tiên; lỗi đầu có thể làm compiler bỏ qua hoặc suy luận khác với những dòng sau.

## 14. Khi nào nên sửa chữ ký method, khi nào nên sửa caller?

### 14.1. Lỗi ở caller

Nếu API yêu cầu `List<Number>` vì bên trong cần thêm cả Integer và Double, caller nên truyền một list Number có thật:

```java
List<Number> values = new ArrayList<>();
values.add(10);
values.add(3.5);
```

Không nới API thành `List<? extends Number>` nếu method thật sự **cần ghi Number** vào list. Wildcard extends sẽ cấm hoạt động đó.

### 14.2. Lỗi ở API

Nếu API chỉ tính tổng phần tử Number nhưng lại yêu cầu `List<Number>`, chữ ký có thể quá chặt:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number x : values) {
        total += x.doubleValue();
    }
    return total;
}
```

Phương thức này nhận được `List<Integer>`, `List<Double>` và `List<Number>`. Nó không ghi nên wildcard extends diễn đạt chính xác mục đích.

### 14.3. Lỗi do hợp đồng mơ hồ

Nếu method cố gắng chèn một đối tượng Integer vào `List<? extends Number>`, bạn cần quyết định:

- Chỉ đọc? Không gọi `add`.
- Ghi Integer? Nhận `List<? super Integer>`.
- Ghi một T phù hợp với list? Dùng `List<T>` và tham số T liên quan, bắt caller cung cấp list typed đúng.
- Sao chép phần tử giữa hai container? Dùng `List<? extends T>` và `List<? super T>`.

Sửa generic error không chỉ là làm compiler im lặng; đó là **xác định quyền đọc/ghi và mức đảm bảo dữ liệu của API**.

## 15. Một số thông điệp trông giống nhau nhưng nguyên nhân khác nhau

### “Found List<String>, required List<T>”

Có thể là:

- T đã bị bound `extends Number`.
- T bị ràng buộc bởi một argument khác.
- T được suy luận từ target return type.
- CAP của một wildcard yêu cầu kiểu chưa biết nhất quán.

Hãy đọc `where` và các constraints trước khi thêm một cast.

### “Required CAP#1, found CAP#2”

Có thể là hai wildcard độc lập hoặc hai capture của những biểu thức wildcard mà compiler không chứng minh là cùng kiểu. Nếu chỉ thao tác với **một list**, generic capture helper có thể tạo một T thống nhất. Nếu chuyển dữ liệu giữa **hai list**, cần quan hệ nguồn/đích được diễn đạt bằng chữ ký và đôi khi không có cách an toàn để làm thao tác mà caller yêu cầu.

### “Inference variable T has incompatible bounds”

Các ràng buộc đang xung đột. Không nhất thiết là “compiler Java quá yếu” hoặc “generic phức tạp nên bỏ qua”. Hãy vẽ ba nguồn constraint:

```text
Target / return context
        |
        v
Inference variable T <---- actual arguments
        ^
        |
Declared bounds / wildcards

T phải thỏa tất cả các mũi tên ràng buộc.
```

Nếu chúng không thể cùng đúng, cần đổi một yêu cầu hoặc đổi dữ liệu — ví dụ không thể yêu cầu List<String> từ `List.of(1,2)` mà không chuyển Integer thành String.

## 16. Common supertype và giao cắt kiểu (*intersection types*)

Trong `String s = first("A",42)`, `javac` có thể in `INT#1`, `INT#2` cùng các interface như `Serializable` và `Comparable`. Đây là mô tả **kiểu giao cắt do suy luận** tạo ra để biểu diễn một kiểu chung phức tạp của các argument. Nó không có nghĩa runtime tạo một class tên `INT#1`.

Đừng cố học thuộc danh sách interface mà compiler in ra ở từng JDK. Phần quan trọng là:

- Generic method muốn tìm một T cho cả String và Integer.
- Target yêu cầu kết quả được dùng dưới String.
- Common supertype suy luận không nhất thiết là subtype của String.
- Do đó phép gán bị chặn.

Một giải pháp đọc được và trung thực là đổi target thành Object nếu nghiệp vụ cho phép, hoặc làm đồng nhất loại đầu vào. Một cast String chỉ có thể là một quyết định runtime có rủi ro, không thay thế được bằng chứng compile-time.

## 17. Capture conversion không phải wildcard covariance tùy ý

Wildcard cho phép một số quan hệ gán:

```java
List<Integer> a = List.of(1, 2);
List<? extends Number> b = a;
Number n = b.get(0);
```

Nhưng khi đã dùng b, compiler cần nhớ “một loại cụ thể nào đó extends Number” thay vì giả định nó là Number. Capture conversion là cách formal hóa điều này.

Tương tự:

```java
List<Number> sink = new ArrayList<>();
List<? super Integer> consumer = sink;
consumer.add(5);
Object readBack = consumer.get(0);
```

`? super Integer` cho phép ghi Integer, nhưng loại đọc tổng quát là Object vì container thật có thể là List<Object>.

Không nhầm wildcard với array covariance: `Number[]` có thể tham chiếu một `Integer[]`, nhưng JVM kiểm tra array store và có thể ném `ArrayStoreException`; generics chủ yếu bảo vệ qua compiler, và subtype relation giữa `List<Integer>` với `List<Number>` không hoạt động như array covariance.

## 18. Lỗi hiểu nhầm thường gặp

| Nhận định | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Integer extends Number nên List<Integer> extends List<Number>.” | Generic invariance. | Đọc qua `List<? extends Number>` hoặc copy vào List<Number>. |
| “`? extends Number` có nghĩa có thể thêm mọi Number.” | Element type có thể là Integer/Double cụ thể chưa biết. | Chỉ đọc Number, hoặc đổi API thành consumer. |
| “CAP#1 là class có thể cast tới.” | CAP là biến nội bộ của capture conversion. | Diễn đạt quan hệ bằng helper `<T>` hoặc bounds. |
| “Hai `List<?>` có cùng dấu ? nên cùng kiểu.” | Mỗi wildcard có thể chỉ một element type khác. | Không copy tùy ý; dùng PECS nếu có subtype relation. |
| “`List<?>.set(i,list.get(j))` chắc chắn compile.” | Các capture có thể khác nhau tại hai biểu thức. | Capture helper lấy List<T> một lần. |
| “Generic helper sẽ giải quyết mọi CAP error.” | Không thể chứng minh hai wildcard list độc lập đồng kiểu. | Dùng typed source/destination phù hợp hoặc đổi nghiệp vụ. |
| “`lower bounds: Integer` nghĩa T phải là Integer.” | Nó thường đòi T chấp nhận Integer, không nhất thiết chính là Integer. | Xem cả equality/upper bounds. |
| “Thêm cast unchecked là giải pháp.” | Cast làm mất kiểm tra, không làm dữ liệu đổi kiểu. | Sửa API/target hoặc chuyển đổi giá trị thật. |
| “Incompatible bounds luôn do sai `extends` trong khai báo.” | Constraints còn đến từ return target, đối số và wildcard. | Đọc toàn bộ diagnostic. |
| “Build chạy thì giá trị generic luôn đúng runtime.” | Raw types/unchecked operations có thể gây heap pollution. | Giữ warnings và kiểm tra boundaries. |
| “Mọi list thêm được khi generic compile.” | List immutable có thể ném UnsupportedOperationException. | Tách type safety khỏi mutability contract. |

## 19. Quy trình debug thực tế

1. **Cô lập tệp và biểu thức** làm compiler báo lỗi. Đừng sửa đồng loạt tất cả generic parameters.
2. **Chạy `javac --release 17 -Xdiags:verbose`** để xem các phần constraint đầy đủ.
3. **Xác định kiểu tĩnh** của mọi đối số, biến đích và kiểu trả về method.
4. **Kiểm tra invariance:** Có đang cố đặt `List<Subclass>` vào `List<Superclass>` không?
5. **Tìm wildcard:** Nếu có `? extends`, `? super` hoặc `?`, xác định method đang đọc hay ghi.
6. **Đọc CAP:** Các CAP có đến từ cùng một List cần capture helper, hay hai List chưa có quan hệ được chứng minh?
7. **Đọc constraints:** T bị equality, upper và lower bounds gì từ từng vị trí?
8. **Tìm xung đột thực:** String không extends Number; Integer không thể được bảo đảm phù hợp với một CAP có thể là Double.
9. **Chọn sửa theo nghiệp vụ:** Đổi target, đổi dữ liệu, chuyển đổi phần tử, dùng wildcard, helper generic, PECS hoặc class token khi thật sự có kiểm tra runtime.
10. **Biên dịch lại cả trường hợp hợp lệ và không hợp lệ.** Phải chắc lỗi đã biến mất đúng lý do, không do unchecked warning bị che.
11. **Chạy test mutability và logic.** Một method compile hợp lệ vẫn có thể bị `IndexOutOfBoundsException` hoặc `UnsupportedOperationException`.
12. **Review public API:** Giữ generic contract rõ và đơn giản; đừng buộc caller ép raw type để gọi.

## 20. Bài tập và đáp án

### Bài 1: Vì sao không gán trực tiếp?

```java
List<Number> values = new ArrayList<Integer>();
```

**Đáp án:** Generic invariance. `ArrayList<Integer>` không phải subtype của `List<Number>`; nếu được gán, caller có thể thêm Double vào danh sách Integer.

### Bài 2: Khi nào `List<? extends Number>` phù hợp?

**Đáp án:** Khi method chỉ cần **đọc** các giá trị có thể dùng dưới Number và không thêm Number bất kỳ vào nguồn.

### Bài 3: `CAP#1` nghĩa là gì?

**Đáp án:** Một type variable mới do compiler sinh khi capture một wildcard; ví dụ một subtype chưa biết của Number. Nó không phải class runtime.

### Bài 4: `List<?>` lấy một phần tử rồi set lại tại slot khác bị lỗi, nên làm gì?

**Đáp án:** Truyền List<?> vào một helper `<T>` nhận `List<T>`; bên trong helper, get và set cùng dùng T. Đảm bảo list mutable và chỉ số hợp lệ.

### Bài 5: Có thể copy từ `List<?>` sang một `List<?>` khác không?

**Đáp án:** Không tổng quát. Hai wildcard có thể đại diện hai kiểu khác nhau. Cần nguồn `? extends T` và đích `? super T` hoặc một hợp đồng typed khác.

### Bài 6: `lower bounds: Integer` có nghĩa T đúng bằng Integer không?

**Đáp án:** Không nhất thiết. Nó thường yêu cầu T là supertype đủ để nhận một Integer; phải xem thêm equality và upper constraints.

### Bài 7: `<T extends Number> void use(List<T>)` có nhận List String không?

**Đáp án:** Không. String không subtype Number, nên compiler có thể báo incompatible bounds.

### Bài 8: `String s = first("A",42)` khó suy luận vì sao?

**Đáp án:** Hai đầu vào khác kiểu có thể dẫn compiler đến common supertype không bảo đảm là String, trong khi target lại yêu cầu String.

### Bài 9: `List<String> values() { return List.of(1,2); }` cần sửa gì?

**Đáp án:** Trả List Integer nếu đúng dữ liệu, trả các chuỗi String, hoặc chuyển Integer sang String thực sự. Không dùng unchecked cast.

### Bài 10: Khi nào dùng `List<? super Integer>`?

**Đáp án:** Khi API cần **ghi Integer** vào một collection có thể là List<Integer>, List<Number> hoặc List<Object>. Khi đọc kết quả nói chung chỉ bảo đảm Object.

### Bài 11: Helper generic có giải quyết `accepts(xs,10)` với xs `List<? extends Number>` không?

**Đáp án:** Không tự động. Kiểu phần tử của xs có thể là Double; không có bằng chứng Integer thuộc đúng captured type ấy. Cần thay contract hoặc chọn list/giá trị tương thích.

### Bài 12: Vì sao cần test runtime sau khi sửa lỗi compile?

**Đáp án:** Type safety không bảo đảm list hỗ trợ sửa, có đủ phần tử hoặc dữ liệu đầu vào thỏa hợp đồng nghiệp vụ. `List.of` vẫn có thể ném UnsupportedOperationException khi set/add.

## 21. Tổng kết

Ba nhóm thông điệp lớn đều bắt nguồn từ một nguyên tắc: **compiler chỉ cho phép thao tác khi có thể chứng minh các quan hệ kiểu cần thiết.**

- `incompatible types`: quan hệ gán/return không hợp lệ, chẳng hạn `List<Integer>` không thể dùng như `List<Number>`.
- `capture of ?` và `CAP#n`: kiểu phần tử tồn tại nhưng chưa biết; không tự coi mọi wildcard là một kiểu giống nhau.
- `incompatible bounds`: generic inference phải thỏa cùng lúc target, arguments và bounds; khi constraints xung đột, không có type argument hợp lệ.

Chọn hướng sửa theo **quyền đọc/ghi và quan hệ thật sự của dữ liệu**: wildcard extends cho producer, super cho consumer, generic helper cho một capture thống nhất, PECS để chuyển giữa hai collection có quan hệ subtype, và chuyển đổi dữ liệu thật khi muốn đổi element type. Đừng lấy unchecked cast làm phương án mặc định.

**Ghi nhớ:** Khi thấy `CAP#1` hay “incompatible bounds”, hãy hỏi *compiler đang thiếu bằng chứng về quan hệ kiểu nào?* — rồi sửa chính quan hệ đó trong thiết kế API.
