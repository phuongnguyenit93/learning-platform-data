# Xung đột tên (name clash) do cùng chữ ký sau xóa kiểu trong Java Generics

Một lớp Java có thể khai báo các phương thức cùng tên nhưng nhận kiểu tham số khác nhau. Tuy nhiên, khi tham số có generic, **hai chữ ký trông khác nhau ở mã nguồn vẫn có thể xóa kiểu (type erasure) thành cùng dạng tham số ở bytecode**. Nếu các phương thức này không tạo thành quan hệ ghi đè hợp lệ, trình biên dịch báo **name clash** và từ chối chương trình.

Ví dụ điển hình:

```java
// KHÔNG BIÊN DỊCH: ví dụ cố ý gây name clash.
import java.util.List;

class DuplicateProcessor {
    void process(List<String> names) { }
    void process(List<Integer> ids) { }
}
```

Cả `List<String>` và `List<Integer>` đều có erasure là `List`. Với Java, việc đổi **đối số kiểu** của một kiểu tham số hóa không đủ để tạo hai overload có chữ ký khác nhau sau erasure.

Bài này giải thích cách tự tính erasure, vì sao xung đột xuất hiện khi overload hoặc kế thừa, khi nào ghi đè là hợp lệ, vai trò của bridge method và cách thiết kế API để tránh name clash.

## 1. Cần phân biệt ba khái niệm: overload, override và name clash

**Overloading (nạp chồng):** có nhiều phương thức cùng tên nhưng **danh sách kiểu tham số** khác nhau để trình biên dịch phân giải lời gọi. Ví dụ `send(String)` và `send(Integer)` là hai overload hợp lệ.

**Overriding (ghi đè):** phương thức của lớp con hoặc lớp triển khai thay thế hành vi của một phương thức được kế thừa theo các quy tắc chữ ký, khả năng truy cập, kiểu trả về và các điều kiện khác của Java. Ghi đè có thể liên quan generics và bridge method.

**Name clash:** hai phương thức dẫn đến chữ ký bị xung đột theo quy tắc ngôn ngữ, chẳng hạn có **cùng erasure nhưng không ghi đè nhau hợp lệ**. Trong trường hợp này, compiler không thể duy trì cả hai như hai overload hợp lệ.

Không phải cứ hai phương thức cùng erasure là sẽ có lỗi: **một override hợp lệ chính là trường hợp cần giữ cùng lời gọi động sau erasure**. Muốn chẩn đoán đúng cần xét cả erasure **và quan hệ kế thừa/ghi đè**.

### Ví dụ nhanh

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `f(List<String>)` cùng `f(List<Integer>)` trong một lớp | Name clash | Cả hai xóa thành `f(List)` |
| `f(List<String>)` cùng `f(Set<Integer>)` | Hợp lệ | Erasure là `f(List)` và `f(Set)` |
| `f(List<String>, int)` cùng `f(List<Integer>, String)` | Hợp lệ | Tham số thứ hai phân biệt chữ ký sau erasure |
| `<T> f(T)` cùng `f(Object)` trong một lớp | Name clash | `T` không bound xóa thành `Object` |
| `<T extends Number> f(T)` cùng `f(Number)` | Name clash | `T` xóa thành `Number` |
| `<T> f(T)` cùng `f(String)` | Hợp lệ | Erasure của tham số lần lượt là `Object` và `String` |
| Lớp con ghi đè `Parent<String>.save(String)` | Có thể hợp lệ | Ghi đè generic đúng quy tắc; compiler tạo bridge nếu cần |

Những dòng minh họa cú pháp trong bảng được hiểu là khai báo trong ngữ cảnh lớp hợp lệ, và các cặp được xét riêng biệt.

## 2. Phương thức có “chữ ký” gì ở mã nguồn và sau erasure?

Trong Java, **không thể overload chỉ bằng kiểu trả về**. Khi phân biệt overload, tên phương thức và kiểu/thứ tự tham số có ý nghĩa; generic type arguments có thể khiến hai danh sách tham số trông khác ở nguồn nhưng không khác sau erasure.

Ví dụ:

```java
// Hai dòng này có vẻ khác nhau ở nguồn:
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> ids) { }
```

Cách tính erasure của cả hai:

```text
save(List<String>)   -> save(List)
save(List<Integer>)  -> save(List)
```

Ở tầng JVM, đối với các phương thức `void`, cả hai sẽ cần descriptor:

```text
(Ljava/util/List;)V
```

Ký hiệu `Ljava/util/List;` đại diện tham số kiểu `java.util.List`, còn `V` biểu thị kết quả `void`. Đây là **cùng descriptor** trong ví dụ trên; JVM không có một descriptor khác nhau mang trực tiếp `String` hay `Integer` của tham số `List<E>`.

Vì vậy, compiler không tạo hai bản phương thức khác nhau chỉ vì hai type argument khác nhau. Vấn đề phải được chặn ngay lúc biên dịch.

### Các quy tắc erasure đủ để phát hiện đa số trường hợp

1. `List<String>`, `List<Integer>`, `List<?>` đều xóa về `List`.
2. `Map<String, Integer>` và `Map<Long, Long>` đều xóa về `Map`.
3. Type variable `T` **không bound** xóa thành `Object`.
4. `T extends Number` xóa thành `Number`.
5. Với nhiều bound, chẳng hạn `T extends Number & Comparable<T>`, erasure của `T` là **bound đầu tiên**, tức `Number`.
6. Kiểu mảng có thành phần generic parameterized cũng bị erasure ở phần tử: `List<String>[]` và `List<Integer>[]` đều dẫn tới dạng mảng của raw `List` về mặt erasure. (Không được tự suy ra rằng mọi phép tạo array generic đều hợp lệ.)

Trong ngữ cảnh chữ ký phương thức, hãy xóa từng loại tham số rồi so sánh toàn bộ **danh sách tham số** theo đúng thứ tự.

## 3. Xung đột overload: đổi type argument chưa đủ

Đây là lỗi phổ biến nhất.

```java
// KHÔNG BIÊN DỊCH. Đây là một file minh họa lỗi, không phải bài tập chạy.
import java.util.List;

class Service {
    void handle(List<String> names) {
        System.out.println("names");
    }

    void handle(List<Integer> ids) {
        System.out.println("ids");
    }
}
```

Compiler báo lỗi kiểu **name clash** vì hai phương thức có cùng erasure. Tên biến `names` và `ids`, nội dung thân phương thức hay việc danh sách thực tế chứa phần tử loại nào đều không làm đổi chữ ký.

Không thể sửa bằng cách đổi tên tham số:

```java
// Vẫn xung đột nếu khai báo trong cùng lớp:
void handle(List<String> a) { }
void handle(List<Integer> b) { }
```

Cũng không thể sửa bằng cách thay kiểu trả về:

```java
// KHÔNG BIÊN DỊCH, chỉ minh họa:
// int read(List<String> a) { return 1; }
// long read(List<Integer> b) { return 2L; }
```

Kiểu trả về không phải tiêu chí phân biệt overload của Java. Hơn nữa, Java còn từ chối hai phương thức chỉ khác kiểu trả về **ngay cả khi không dùng generics**.

### Không chỉ `List`: mọi generic class/interface đều có thể gặp vấn đề

```java
// KHÔNG BIÊN DỊCH nếu cặp phương thức cùng ở một lớp:
void index(java.util.Map<String, Integer> mapping) { }
void index(java.util.Map<Long, Double> mapping) { }
```

Hai tham số đều xóa về `Map`. Tương tự, `Comparable<String>` và `Comparable<Integer>` cùng xóa thành `Comparable`; một API muốn overload dựa riêng vào type argument của chúng sẽ gặp vấn đề tương tự.

## 4. Trường hợp type variable làm mất sự khác biệt

Type variable có thể khiến hai overload viết rất khác nhưng cùng erasure.

```java
// KHÔNG BIÊN DỊCH:
class Operation {
    <T> void put(T value) { }
    void put(Object value) { }
}
```

Vì `T` không giới hạn, `T` xóa thành `Object`:

```text
<T> put(T)     -> put(Object)
put(Object)    -> put(Object)
```

Tương tự:

```java
// KHÔNG BIÊN DỊCH:
class NumberOperation {
    <T extends Number> void put(T value) { }
    void put(Number value) { }
}
```

Cả hai thành `put(Number)`. Lưu ý: erasure của `T extends Number` là **Number**, không phải kiểu concrete mà một lời gọi suy luận ra, ví dụ `Integer`.

Ngược lại, đây là **overload hợp lệ**:

```java
// Snippet: có thể đặt trong cùng lớp.
static <T> void print(T value) {
    System.out.println("Generic: " + value);
}

static void print(String value) {
    System.out.println("String: " + value);
}
```

Sau erasure, phương thức generic nhận `Object`; phương thức còn lại nhận `String`. Hai descriptor khác nhau, nên không có name clash. Khi gọi `print("hello")`, compiler thường chọn overload `String` cụ thể hơn, còn `print(123)` có thể dùng overload generic. **Overload resolution xảy ra tại thời điểm biên dịch dựa trên kiểu tĩnh**, không dựa vào việc JVM thấy một `String` ở runtime rồi tự chọn lại overload.

## 5. Name clash do phương thức kế thừa

Xung đột không chỉ xảy ra khi viết hai phương thức trong cùng lớp. Một lớp con cũng có thể viết một phương thức trông khác nhưng xóa thành chữ ký của phương thức được kế thừa mà **không ghi đè hợp lệ**.

```java
// KHÔNG BIÊN DỊCH:
import java.util.List;

class Base {
    void process(List<String> names) { }
}

class Derived extends Base {
    void process(List<Integer> ids) { }
}
```

Trong `Base`, erasure là `process(List)`; trong `Derived` cũng là `process(List)`. Nhưng `process(List<Integer>)` không phải một override hợp lệ của `process(List<String>)`. Vì vậy compiler không thể vừa xem đây là overload độc lập, vừa xem đây là một ghi đè hợp lệ.

**Bài học:** khi thấy lỗi `name clash` ở lớp con chỉ khai báo **một** phương thức, đừng vội kết luận compiler báo sai. Hãy tra cả các phương thức cùng tên của superclass và interface mà lớp đó kế thừa.

### Hai interface đòi hỏi hai phiên bản generic không tương thích

```java
// Ví dụ KHÔNG HỢP LỆ nếu một lớp cố thực hiện cả hai yêu cầu
// bằng cùng tên và danh sách tham số xóa thành một chữ ký.
interface NameReceiver {
    void receive(java.util.List<String> names);
}

interface IdReceiver {
    void receive(java.util.List<Integer> ids);
}

// Một lớp cố implements cả hai sẽ không thể khai báo hai
// overload receive(List<String>) và receive(List<Integer>) hợp lệ.
```

Điều này cho thấy xung đột có thể bắt nguồn từ **hợp đồng kế thừa nhiều interface**, ngay cả khi mỗi interface riêng lẻ đều biên dịch bình thường. Để thiết kế lại API, có thể thống nhất một hợp đồng generic, dùng tên khác nhau, hoặc chuyển chiến lược xử lý qua một kiểu tham số thực sự phân biệt.

### Vì sao “hai kiểu generic khác nhau” không phải lý do đủ?

Về lý thuyết `List<String>` và `List<Integer>` là **hai kiểu tĩnh bất biến**, không thể gán trực tiếp cho nhau. Nhưng quy tắc overload và override của Java còn cần đáp ứng **sự tương thích của phương thức sau xóa kiểu**. Vì thế hai type argument khác nhau không đảm bảo chữ ký đủ khác để cùng tồn tại.

## 6. Tại sao ghi đè generic hợp lệ không bị coi là name clash?

Xét một lớp cha generic:

```java
class Parent<T> {
    void save(T value) {
        System.out.println("Parent: " + value);
    }
}

class Child extends Parent<String> {
    @Override
    void save(String value) {
        System.out.println("Child: " + value);
    }
}
```

Khi gắn `T = String`, việc `Child.save(String)` ghi đè `Parent<T>.save(T)` là hợp lệ ở mức ngôn ngữ. Nhưng sau erasure, descriptor phương thức của lớp cha nhận `Object`, còn phương thức hiện thực của lớp con nhận `String`.

Compiler giải quyết bằng **bridge method** trong bytecode của lớp con, có hành vi đại ý:

```java
// Pseudocode để hiểu bridge, KHÔNG tự thêm vào Child:
void save(Object value) {
    save((String) value);
}
```

Bridge giúp lời gọi qua `Parent<String> parent = new Child(); parent.save("abc");` vẫn vào phương thức ghi đè `Child.save(String)`. Bridge này là do compiler sinh, có thể được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC` trong bytecode, và được reflection nhận biết bởi `Method.isBridge()`.

Đây **không phải** xung đột overload của hai phương thức người lập trình cố khai báo. Compiler biết đây là quan hệ override hợp lệ, nên nó có thể tạo mã cầu nối mà vẫn bảo toàn tính đa hình. Khi gặp lỗi name clash, phải phân biệt:

- **Hai phương thức không có quan hệ override phù hợp** nhưng trùng erasure: bị từ chối.
- **Một override generic hợp lệ** có descriptor khác sau erasure: compiler có thể chèn bridge để bảo toàn dispatch.

Trong một lớp con, nếu bạn cố tự khai báo một phương thức có chữ ký sau erasure cạnh tranh với bridge cần được sinh, compiler cũng có thể báo lỗi name clash. Đừng viết tay phương thức `save(Object)` để “thay” bridge của `Child.save(String)`; hãy giữ override theo kiểu chuyên biệt và để compiler thực hiện nhiệm vụ này.

## 7. Subsignature và khả năng tương thích với mã cũ

Một điểm tinh tế của Java là quan hệ **subsignature**: Java cho phép một số trường hợp ghi đè khi chữ ký phương thức ở lớp con tương đương với dạng đã xóa của phương thức lớp cha. Quy tắc này phục vụ việc chuyển các thư viện cũ sang generics mà không phá vỡ mọi lớp con hiện có.

Ví dụ ý tưởng:

```java
// Snippet minh họa cơ chế tương thích nguồn khi kế thừa:
class GenericParent {
    <T> void accept(T value) { }
}

class LegacyChild extends GenericParent {
    @Override
    void accept(Object value) { }
}
```

Trong ngữ cảnh này, phương thức `accept(Object)` ở lớp con có thể override phương thức `<T> accept(T)` của lớp cha nhờ chữ ký tương thích theo erasure. Mặc dù cả hai có tham số `Object` trong descriptor, đây là một **ghi đè hợp lệ**, không phải một overload cần phân biệt.

Điều này khác với việc hai phương thức `accept(List<String>)` và `accept(List<Integer>)` cùng có erasure `accept(List)`: chúng không tự tạo thành quan hệ override chỉ vì erasure trùng nhau.

Đừng dùng mẹo “thay hết generic bằng raw type” một cách máy móc để sửa name clash. Raw types và unchecked conversions có thể làm suy yếu kiểm tra kiểu, thay đổi cách chọn overload và che giấu lỗi dữ liệu. Giải pháp đúng phải bảo toàn hợp đồng API và quan hệ kế thừa thực sự.

## 8. Chương trình Java 17+ chứng minh các trường hợp hợp lệ

Lưu toàn bộ mã sau vào tệp **`NameClashDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class NameClashDemo {
    // Hợp lệ: List và Set có erasure khác nhau.
    static void inspect(List<String> values) {
        System.out.println("List: " + values.get(0));
    }

    static void inspect(Set<Integer> values) {
        System.out.println("Set: " + values.iterator().next());
    }

    // Hợp lệ: T extends Number bị xóa thành Number, khác String.
    static <T extends Number> void describe(T value) {
        System.out.println("Number: " + value);
    }

    static void describe(String value) {
        System.out.println("String: " + value);
    }

    // Hợp lệ: T không bound bị xóa thành Object, khác String.
    static <T> void log(T value) {
        System.out.println("Generic: " + value);
    }

    static void log(String value) {
        System.out.println("Specific: " + value);
    }

    static class Parent<T> {
        void save(T value) {
            System.out.println("Parent: " + value);
        }
    }

    static final class Child extends Parent<String> {
        @Override
        void save(String value) {
            System.out.println("Child: " + value.toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        inspect(List.of("Java"));
        inspect(Set.of(7));
        describe(42);
        describe("erasure");
        log("hello");
        log(100);

        Parent<String> parent = new Child();
        parent.save("bridge");

        boolean hasBridge = Arrays.stream(Child.class.getDeclaredMethods())
                .anyMatch(Method::isBridge);
        System.out.println("Bridge method: " + hasBridge);
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 NameClashDemo.java
java NameClashDemo
```

Kết quả:

```text
List: Java
Set: 7
Number: 42
String: erasure
Specific: hello
Generic: 100
Child: BRIDGE
Bridge method: true
```

Diễn giải:

1. `inspect(List<String>)` và `inspect(Set<Integer>)` cùng tên nhưng có **erasure khác nhau**: `List` và `Set`. Vì vậy cả hai tồn tại trong một lớp.
2. `describe(T extends Number)` xóa thành `describe(Number)`, đủ khác `describe(String)`.
3. `log(T)` xóa thành `log(Object)`, đủ khác `log(String)`. Lời gọi `log("hello")` dùng overload `String`; `log(100)` dùng overload generic.
4. `parent.save("bridge")` gọi được logic ghi đè của `Child` thông qua tham chiếu lớp cha đã gắn kiểu `String`.
5. Reflection tìm thấy **bridge method** do compiler tạo ở `Child`. Việc bridge tồn tại chứng minh compiler đã bảo toàn override sau erasure, chứ không phải sinh thêm một lớp `Parent<String>` cho đối số kiểu.

Ví dụ này là chương trình độc lập; các ví dụ **KHÔNG BIÊN DỊCH** trong những mục khác phải được thử riêng, không chép nguyên chúng vào tệp `NameClashDemo.java`.

## 9. Ba cách sửa name clash theo nhu cầu API

### Cách 1: đổi tên phương thức theo ý nghĩa nghiệp vụ

Từ hai overload xung đột:

```java
// Không hợp lệ nếu đặt cùng lớp:
// void process(List<String> names) { }
// void process(List<Integer> ids) { }
```

Chuyển thành:

```java
// Snippet hợp lệ:
void processNames(List<String> names) { /* ... */ }
void processIds(List<Integer> ids) { /* ... */ }
```

Đây thường là cách rõ nghĩa nhất khi mỗi danh sách đòi hỏi nghiệp vụ khác nhau. Nó giữ được kiểm tra kiểu tĩnh và dễ tìm API bằng tên.

### Cách 2: chọn hai kiểu tham số thực sự khác sau erasure

Nếu hai thao tác **vốn có cấu trúc đầu vào khác nhau**, dùng các abstraction phù hợp để erasure vẫn khác:

```java
// Snippet hợp lệ nếu phù hợp nhu cầu thiết kế:
void process(List<String> names) { /* ... */ }
void process(Set<Integer> ids) { /* ... */ }
```

Nhưng đừng đổi `List` thành `Set` chỉ để “lách compiler”: `Set` có ngữ nghĩa khác về phần tử trùng lặp và thứ tự, ảnh hưởng hành vi chương trình. Kiểu tham số phải phản ánh hợp đồng dữ liệu thật.

### Cách 3: dùng một phương thức generic thống nhất

Nếu cả hai kiểu phần tử được xử lý **cùng một thuật toán**, không cần hai overload:

```java
// Snippet hợp lệ: một API cho mọi kiểu T.
static <T> int count(List<T> items) {
    return items.size();
}
```

Có thể gọi `count(List<String>)` hoặc `count(List<Integer>)` mà vẫn được kiểm tra kiểu nguồn; bytecode chỉ cần một phương thức nhận `List`.

Nếu thuật toán khác nhau tùy kiểu phần tử, hãy đưa sự khác biệt vào một **strategy** hoặc callback có kiểu rõ ràng:

```java
// Snippet hợp lệ; chỉ minh họa chữ ký generic dùng callback:
static <T> void processAll(
        List<T> items,
        java.util.function.Consumer<? super T> operation) {
    for (T item : items) {
        operation.accept(item);
    }
}
```

Lúc gọi có thể truyền `processAll(names, System.out::println)`. Như vậy sự khác biệt trong xử lý được thể hiện qua đối số `Consumer`; không cần nhân đôi chữ ký overload dựa trên `List<T>`.

### Cách 4: dùng các kiểu miền riêng khi hợp đồng thực sự khác

Nếu hai tập dữ liệu tương ứng hai loại nghiệp vụ, có thể tạo kiểu wrapper:

```java
// Snippet minh họa Java 17:
record NameBatch(List<String> values) { }
record IdBatch(List<Integer> values) { }

void process(NameBatch names) { /* ... */ }
void process(IdBatch ids) { /* ... */ }
```

Hai kiểu bản ghi `NameBatch` và `IdBatch` là **hai class runtime khác nhau**, do đó phân biệt được overload. Cách này hữu ích khi cần biểu diễn các khái niệm miền thật, kèm validation hay metadata riêng. Không nên tạo wrapper vô cớ chỉ để che một API chưa rõ mục đích.

## 10. Những trường hợp dễ bị hiểu nhầm

**Nhầm 1 — “`List<String>` khác `List<Integer>` nên overload chắc chắn được.”** Sai. Khác nhau ở kiểu tĩnh không đồng nghĩa khác nhau ở chữ ký erasure.

**Nhầm 2 — “Cùng erasure thì mọi override đều lỗi.”** Sai. Override generic hợp lệ có thể cần bridge method; compiler không xử lý nó như hai overload cạnh tranh.

**Nhầm 3 — “Đổi kiểu trả về giải quyết clash.”** Sai. Kiểu trả về không dùng để phân biệt hai overload Java.

**Nhầm 4 — “Tên biến khác nhau tạo thành chữ ký khác.”** Sai. `process(List<String> names)` và `process(List<Integer> ids)` vẫn bị name clash.

**Nhầm 5 — “Giới hạn `T extends Number` vẫn xóa thành `Object`.”** Sai. Erasure của `T` là giới hạn đầu tiên, tức `Number`.

**Nhầm 6 — “Raw type là lối sửa phổ quát.”** Sai. Chuyển sang raw `List` thường giữ nguyên erasure `List`, đồng thời làm mất an toàn kiểu.

**Nhầm 7 — “Compiler nhìn dữ liệu thực bên trong list để chọn overload.”** Sai. Chọn overload dựa trên thông tin kiểu lúc biên dịch, còn `List<String>` không mang một runtime class riêng với `List<Integer>`.

**Nhầm 8 — “Một lớp có hai phương thức cùng tên chỉ khác generic là lỗi do reflection.”** Sai. Name clash được chẩn đoán lúc biên dịch Java, trước khi đến runtime reflection.

**Nhầm 9 — “Bridge method là phương thức overload do lập trình viên phải viết.”** Sai. Bridge là bytecode compiler sinh trong các trường hợp cần thiết để giữ tính đa hình.

## 11. Cách chẩn đoán name clash từng bước

Khi javac báo `name clash: ... have the same erasure` hoặc một thông báo tương tự:

1. **Liệt kê tất cả phương thức cùng tên**, kể cả phương thức của superclass và interface; không chỉ xem phương thức vừa sửa.
2. **Ghi toàn bộ danh sách tham số** của từng phương thức theo thứ tự. Đừng dựa vào tên biến hay kiểu trả về.
3. **Xóa các đối số kiểu:** `List<String>` → `List`; `Map<K,V>` → `Map`.
4. **Xóa type variable theo bound đầu tiên:** `<T>` → `Object`; `<T extends Number>` → `Number`.
5. **So sánh các danh sách tham số đã xóa.** Nếu khác nhau, có thể vẫn là overload hợp lệ (còn phụ thuộc các quy tắc Java khác).
6. **Nếu trùng nhau, kiểm tra có override/subsignature hợp lệ không.** Quan hệ override hợp lệ có thể dùng bridge; hai phương thức không override nhau thì nguy cơ name clash.
7. **Chọn sửa ở mức hợp đồng API:** tên khác, tham số có ý nghĩa khác, một method generic, strategy hoặc wrapper miền; kiểm tra lại các lời gọi và các lớp con liên quan.

Không nên dùng thông báo lỗi như một “gợi ý bỏ generic cho xong”. Compiler đang chỉ ra sự bất nhất trong tập hợp phương thức sau erasure. Việc giải quyết cần nhìn cả thiết kế API và cấu trúc kế thừa.

## 12. Bài tập tự kiểm tra

**Câu 1.** Hai phương thức `void run(List<String> a)` và `void run(List<Integer> b)` cùng thuộc một lớp. Hợp lệ không?

Không. Cả hai thành `run(List)`; không thể tạo hai overload chỉ bằng type argument.

**Câu 2.** Hai phương thức `<T extends Number> void run(T x)` và `void run(String s)` cùng một lớp. Hợp lệ không?

Có. Erasure là `run(Number)` và `run(String)`.

**Câu 3.** `<T> void run(T x)` và `void run(Object x)` cùng một lớp. Hợp lệ không?

Không. Type variable `T` không bound xóa thành `Object`, gây trùng chữ ký.

**Câu 4.** `Child extends Parent<String>` và ghi đè đúng `void save(String)`. Vì sao compiler có thể sinh `save(Object)` trong bytecode mà không báo name clash?

Vì đây là **quan hệ override hợp lệ**, và `save(Object)` là bridge compiler tạo nhằm thực hiện lời gọi động tương thích với erasure của phương thức lớp cha, không phải một overload tự khai báo đang cạnh tranh.

**Câu 5.** Hai method `sum(List<String>, int)` và `sum(List<Integer>, long)` có name clash chỉ do generic không?

Không. Sau erasure chúng là `sum(List,int)` và `sum(List,long)`, nên danh sách tham số vẫn khác nhau. Các điều kiện khác của Java vẫn phải được đáp ứng.

**Câu 6.** API cần xử lý danh sách `String` và `Integer` bằng đúng cùng một thuật toán. Có nhất thiết cần hai overload không?

Không. Dùng một phương thức generic như `<T> void process(List<T> values)` là cách tự nhiên hơn.

## 13. Kết luận và quy tắc thực hành

**Name clash do erasure** xuất hiện khi những phương thức generic có các chữ ký tham số bị xóa về cùng dạng mà **không thể cùng tồn tại theo quy tắc overload/override của Java**. Điểm mấu chốt là so sánh **kiểu tham số sau xóa** và **quan hệ ghi đè**, chứ không chỉ nhìn sự khác nhau giữa các đối số `<String>`, `<Integer>` ở mã nguồn.

Khi thiết kế API generics, đừng overload các phương thức chỉ bằng cách đổi type argument của cùng một generic class. Hãy dùng tên nghiệp vụ rõ ràng, chọn kiểu tham số thực sự khác nhau khi có lý do, hoặc gộp hành vi chung vào một phương thức generic. Với subclass, kiểm tra chữ ký kế thừa và để compiler sinh bridge method cho những override generic hợp lệ.