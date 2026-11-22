# Xóa kiểu trong chữ ký phương thức và kiểu mảng (Java Generics)

## 1. Bức tranh tổng quan

**Type erasure** (xóa kiểu) là cơ chế Java sử dụng để biên dịch phần lớn thông tin kiểu generic thành dạng phù hợp với các lớp và chữ ký phương thức trên JVM. Khi bạn viết `List<String>`, `List<Integer>`, `T`, `T[]`, hoặc một phương thức `<T> T identity(T value)`, trình biên dịch kiểm tra chúng bằng thông tin generic, rồi phát sinh bytecode có những kiểu đã được xóa.

Bài này tập trung vào **hai nơi có hệ quả rõ nhất**:

1. **Chữ ký phương thức**: tham số, kiểu trả về, overload, override và những phương thức bridge compiler có thể tạo.
2. **Kiểu mảng**: kiểu phần tử mảng ở runtime, mảng chứa type variable hoặc generic parameterized type, tính *reifiable*, và cách tạo mảng an toàn.

Đọc xong, bạn có thể dự đoán chữ ký bytecode của một phương thức generic, phân tích lỗi `name clash`/`generic array creation`, hiểu vì sao mảng và `List<T>` có quy tắc khác nhau, cũng như dùng `javap` và reflection để kiểm tra.

Đây là cơ chế **biên dịch và biểu diễn kiểu**. Erasure không xóa đối tượng khỏi bộ nhớ và cũng không biến mọi kiểm tra kiểu thành một phép kiểm tra muộn tùy ý ở runtime.

## 2. Quy tắc xóa kiểu cho chữ ký generic

Những quy tắc cần nắm:

| Kiểu trong source | Dạng sau erasure | Lý do |
| --- | --- | --- |
| Type variable `T` không có bound tường minh | `Object` | Bound mặc định là `Object`. |
| `<T extends Number>` | `Number` | Type variable được thay bằng bound đầu tiên. |
| `<T extends Number & Comparable<T>>` | `Number` | Trong nhiều bound, **bound đầu tiên** được dùng để xóa `T`. |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable` (raw) | Bound đầu tiên là interface `Comparable<T>`, bản thân kiểu tham số hóa cũng bị xóa. |
| `List<String>` | `List` (raw ở mức bytecode descriptor) | Kiểu đối số `String` không tham gia descriptor. |
| `Map<String, List<Integer>>` | `Map` | Các type argument lồng nhau không còn trong descriptor. |
| `T[]` khi `T` không có bound tường minh | `Object[]` | Xóa kiểu thành phần `T` trước, vẫn giữ số chiều mảng. |
| `T[]` với `T extends Number` | `Number[]` | Kiểu thành phần được xóa về `Number`. |
| `List<T>[]` | `List[]` | Mảng vẫn là mảng; kiểu thành phần `List<T>` bị xóa thành `List`. |

Quy tắc “bound đầu tiên” đòi hỏi thứ tự khai báo hợp lệ của Java: nếu có bound là lớp thì bound lớp phải đứng trước các bound interface. Các bound còn lại vẫn được compiler dùng **khi kiểm tra source**; chúng không đồng nghĩa với việc JVM giữ nhiều kiểu tham số trong một descriptor.

Một ví dụ ngắn:

```java
static <T> T identity(T value) {
    return value;
}

static <T extends Number> T keep(T value) {
    return value;
}
```

Ở mức *method descriptor* JVM, chúng tương ứng với:

```text
identity: (Ljava/lang/Object;)Ljava/lang/Object;
keep:     (Ljava/lang/Number;)Ljava/lang/Number;
```

Ký pháp JVM:

- `L...;` biểu thị kiểu tham chiếu class/interface, dấu `/` phân tách package.
- Các kiểu bên trong `(...)` là tham số theo thứ tự.
- Phần sau `)` là kiểu trả về.
- `V` biểu thị `void`; dấu `[` đứng trước biểu thị một chiều mảng. Ví dụ `[Ljava/lang/String;` là `String[]`.

**Lưu ý:** Descriptor và **generic Signature attribute** trong class file có vai trò khác nhau. Descriptor ghi dạng xóa kiểu dùng để liên kết lời gọi tại JVM; Signature, nếu có, có thể lưu siêu dữ liệu generic để compiler và reflection xem lại. Đừng kết luận “generic không tồn tại ở đâu trong `.class`” — điều đúng là **mỗi đối tượng `List<String>` không mang một tham số `String` runtime riêng có thể kiểm tra bằng `instanceof List<String>`**.

## 3. Xóa kiểu ở tham số và kết quả phương thức

### 3.1. Phương thức generic tự khai báo type variable

Xem phương thức:

```java
static <T> T identity(T value) {
    return value;
}
```

Từ góc nhìn source:

```java
String s = identity("Java");
Integer n = identity(5);
```

Compiler suy luận `T` riêng cho từng lời gọi. Nhưng phương thức trong bytecode không nhân đôi cho mỗi kiểu:

```text
identity(Object) -> Object
```

Chữ ký JVM chỉ có một thân phương thức. Compiler có thể chèn `checkcast` tại vị trí **sử dụng kết quả** khi ngữ cảnh cần kiểu cụ thể như `String`. Nó cũng tận dụng các chuyển đổi boxing/unboxing theo quy tắc của Java.

Không vì thế mà `identity` có thể trả `String` từ một input `Integer` khi source khai báo `String s = identity(5);`: bước kiểm tra generic đã ngăn lỗi trước khi chạy.

### 3.2. Type variable của class cũng bị xóa

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Trong bytecode, trường và chữ ký cơ bản sẽ dùng `Number`:

```text
value: Number
Box(Number)
get() -> Number
```

Khi viết `Box<Integer> box = new Box<>(7); Integer n = box.get();`, kiểu đích `Integer` vẫn được compiler kiểm tra, và bytecode của nơi gọi có thể cần cast từ `Number` sang `Integer`.

Nếu khai báo hai biến `Box<Integer>` và `Box<Double>`, không có hai định nghĩa class `Box` chuyên biệt. Java generics chủ yếu dùng **một class đã xóa kiểu**, khác với cơ chế chuyên biệt hóa template theo từng tham số kiểu ở một số ngôn ngữ khác.

### 3.3. Type bound phối hợp: erasure khác kiểm tra source

```java
static <T extends Number & Comparable<T>> T greater(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Tại source, `T` phải đồng thời là `Number` và thực hiện `Comparable<T>`, nên gọi được `compareTo`. Vì `Number` đứng đầu, descriptor là:

```text
(Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;
```

Điều này **không có nghĩa** JVM sẽ tự coi mọi `Number` là `Comparable`: compiler phát sinh thao tác bytecode phù hợp để truy cập interface cần dùng và vẫn bảo vệ ràng buộc generic ở compile time. Ví dụ `greater(4, 9)` hợp lệ vì `Integer` phù hợp các bound; đừng truyền một lớp `Number` tùy ý không triển khai `Comparable` rồi trông chờ erasure kiểm tra giúp.

## 4. Xung đột chữ ký sau xóa kiểu: `name clash`

Java **không cho overload chỉ dựa vào type argument generic** nếu hai khai báo có cùng chữ ký sau erasure:

```java
import java.util.List;

class InvalidOverloads {
    void print(List<String> strings) {}

    void print(List<Integer> numbers) {} // Lỗi biên dịch: name clash
}
```

Hai phương thức trên đều có tham số bị xóa thành `List`, tương ứng:

```text
print(Ljava/util/List;)V
```

Đổi tên biến tham số hoặc đổi `String` thành `Long` không giúp gì. JVM không có đủ thông tin phân biệt hai lời gọi này theo type argument, nên compiler ngăn chúng ngay từ source.

Cách sửa tùy mục đích:

```java
import java.util.List;

class DistinctOperations {
    void printStrings(List<String> strings) {}
    void printNumbers(List<Integer> numbers) {}
}
```

Hoặc viết **một phương thức generic** khi hành vi xử lý chung thực sự giống nhau:

```java
static <T> void printAll(List<T> items) {
    items.forEach(System.out::println);
}
```

Nếu nghiệp vụ cần dispatch theo loại phần tử, cân nhắc API hoặc strategy mang type token (`Class<T>`) **khi cần**, thay vì giả định `List<String>` và `List<Integer>` sẽ có hai lớp runtime riêng.

Phân biệt với overload có raw parameter khác nhau: `work(List<String>)` và `work(ArrayList<Integer>)` **có thể** là hai overload vì erasure cho tham số đầu lần lượt là `List` và `ArrayList`. Vấn đề không nằm ở việc phương thức “có generic”, mà là **chữ ký sau erasure có trùng** theo quy tắc Java hay không.

### 4.1. Kiểu trả về không giúp phân biệt overload

Hai phương thức cùng tên, cùng danh sách kiểu tham số mà chỉ khác kiểu trả về không tạo thành overload hợp lệ trong Java:

```java
// Minh họa không biên dịch:
String pick() { return "a"; }
Integer pick() { return 1; }
```

Trên class file, descriptor gồm cả return type, nhưng **quy tắc khai báo và lựa chọn overload của ngôn ngữ Java** không cho bạn viết hai phương thức khác nhau chỉ bằng kiểu trả về. Các phương thức bridge mà compiler có thể tạo là trường hợp phục vụ override ở bytecode, không phải một tính năng cho phép programmer overload theo return type.

## 5. Override với generic và phương thức bridge

Type erasure có thể làm **descriptor của method được override khác chữ ký implementation**. Ví dụ:

```java
class Parent<T> {
    T value() { return null; }
}
class Child extends Parent<String> {
    @Override String value() { return "child"; }
}
```

Trong `Parent<T>`, `value()` bị xóa về `()Ljava/lang/Object;`. `Child.value()` trả `String` nên compiler có thể phát sinh một **bridge method** synthetic trả `Object` để lời gọi đa hình qua `Parent<String>` vẫn dispatch đúng. Kiểm chứng bằng `javap -v` hoặc `Method.isBridge()`. Đây **không phải** specialization của `Parent<T>`, và không phải method nào có generic cũng cần bridge.

Bài về **first bound** giải thích thêm trường hợp descriptor bridge dùng `Number` thay vì `Object`. Bài hiện tại tiếp tục trọng tâm về **chữ ký method và kiểu mảng sau erasure**.

## 6. Mảng trong JVM khác generic container

**Mảng có kiểu thành phần runtime**: một `String[]` biết tại runtime thành phần là `String`, còn `Number[]` biết thành phần là `Number`. Java mảng là **covariant**, ví dụ `String[]` có thể gán cho `Object[]`, và JVM kiểm tra khi ghi phần tử:

```java
String[] names = new String[1];
Object[] objects = names;
objects[0] = 42; // ArrayStoreException khi chạy
```

Ngược lại, `List<String>` không phải subtype của `List<Object>` vì generic Java **invariant**:

```java
List<String> names = List.of("Java");
// List<Object> objects = names; // Lỗi biên dịch
```

Sự khác biệt này là một nguyên nhân quan trọng khiến Java **không cho tạo trực tiếp mảng của đa số kiểu generic không reifiable**: cơ chế kiểm tra phần tử runtime của mảng không thể biết đầy đủ type argument để bảo vệ `List<String>[]`.

### 6.1. Kiểu reifiable là gì?

Một kiểu được gọi là *reifiable* nếu thông tin runtime của nó đủ để biểu diễn kiểu đó theo những điều kiện của ngôn ngữ Java. Một số trường hợp thường dùng:

- `String`, `Integer`, `Number`, các primitive type, và `String[]` là reifiable.
- `List` raw type và `List<?>` với **tất cả** type argument là wildcard không giới hạn là reifiable.
- `List<String>`, `List<? extends Number>`, type variable `T` không phải kiểu reifiable.
- Mảng có kiểu thành phần reifiable cũng là reifiable, ví dụ `List<?>[]`.

Đây là lý do:

```java
String[] names = new String[2];      // Hợp lệ
List<?>[] all = new List<?>[2];      // Hợp lệ
// List<String>[] bad = new List<String>[2]; // generic array creation
// T[] bad = new T[2];                       // Không hợp lệ trong generic context
```

Dòng `List<?>[]` không cho phép bạn nhét tùy ý phần tử sai vào một `List<String>` mà không được kiểm tra. Nó chỉ nói mỗi ô là một `List<?>`; ta đọc giá trị từng phần tử như `Object` nếu không có thông tin kiểu hẹp hơn.

### 6.2. Array type sau erasure vẫn giữ số chiều

Với các chữ ký:

```java
static <T> T[] sameArray(T[] input) {
    return input;
}

// Khai báo minh họa:
static <T extends Number> T[] echoNumbers(T[] input) {
    return input;
}
```

Dạng descriptor tương ứng là:

```text
sameArray:   ([Ljava/lang/Object;)[Ljava/lang/Object;
echoNumbers: ([Ljava/lang/Number;)[Ljava/lang/Number;
```

Dấu `[` không biến mất; chỉ **kiểu thành phần** là `Object` hoặc bound `Number`. Nếu là `T[][]` với `T` không bound, erasure là `Object[][]`, descriptor bắt đầu bằng `[[`.

Ở runtime, mảng **thực tế** được truyền có thể là `String[]`, và `sameArray` trả lại đúng mảng đó (không cần tạo một `Object[]` mới). Erasure của chữ ký không hề sửa kiểu mảng runtime của đối tượng đã được tạo.

### 6.3. Mảng của parameterized type trong khai báo vẫn có thể hợp lệ

So sánh hai tình huống:

```java
// Chỉ là khai báo trường, không cấp phát mảng:
List<String>[] buckets;
```

và:

```java
// Không biên dịch:
List<String>[] buckets = new List<String>[5];
```

**Khai báo** biến kiểu mảng chứa `List<String>` được phép; **tạo** mảng bằng `new List<String>[5]` thì không được, vì component type không reifiable. Một số API cũ cung cấp giá trị có kiểu này qua cast unchecked; điều đó không biến kiểu thành reifiable hoặc làm thao tác đọc hoàn toàn an toàn.

Tránh cách:

```java
// Minh họa workaround kém an toàn; KHÔNG khuyến nghị:
@SuppressWarnings("unchecked")
List<String>[] values = (List<String>[]) new List<?>[2];
```

Array runtime chỉ kiểm tra phần tử có là `List` hay không, không kiểm tra `List<String>`. Một alias dạng `Object[]` có thể đưa `List<Integer>` vào mảng, làm phát sinh **heap pollution**; khi đọc phần tử theo giả định `String`, chương trình có thể ném `ClassCastException`.

## 7. Tạo và xử lý mảng generic một cách an toàn

### 7.1. Nhận mảng do bên gọi cung cấp

Phương thức generic có thể **nhận, trả lại hoặc sao chép** một mảng kiểu `T[]` mà không tự dùng `new T[...]`:

```java
static <T> T[] duplicate(T[] input) {
    return input.clone();
}
```

`clone()` trên mảng giữ kiểu thành phần runtime của mảng gốc. Nếu `input` là `String[]`, mảng trả về cũng là `String[]`. Bản sao này là *shallow copy*: nếu phần tử là đối tượng mutable, chúng vẫn có thể được chia sẻ qua hai mảng.

### 7.2. Để bên gọi cấp phát qua constructor reference

Khi cần tạo mảng mới với component type phù hợp, truyền factory:

```java
import java.util.function.IntFunction;

static <T> T[] createArray(int length, IntFunction<T[]> factory) {
    if (length < 0) {
        throw new IllegalArgumentException("length must be >= 0");
    }
    return factory.apply(length);
}

// Bên trong một phương thức:
String[] names = createArray(3, String[]::new);
Integer[] ages = createArray(2, Integer[]::new);
```

Phương thức không giả định runtime class của `T` là gì; factory cung cấp mảng thật. Nên kiểm tra contract của factory trong API công khai nếu bạn cần đảm bảo length không bị thay đổi.

Một lựa chọn khác là dùng `java.lang.reflect.Array.newInstance(componentClass, length)` rồi cast sang `T[]`, nhưng Java không thể kiểm tra cast theo type variable ở runtime, thường phải đặt cast unchecked trong một hàm được đóng gói và kiểm thử cẩn thận. Với API hiện đại, factory `IntFunction<T[]>` hoặc `Collection.toArray(T[]::new)` thường rõ nghĩa hơn.

### 7.3. Dùng `List<T>` khi không thật sự cần mảng

Nếu dữ liệu cần kích thước động và API không bắt buộc array, `List<T>` là lựa chọn dễ dùng:

```java
List<String> names = new ArrayList<>();
names.add("Java");
names.add("Generics");
String first = names.get(0);
```

Khi thật sự cần mảng để gọi API khác:

```java
String[] array = names.toArray(String[]::new); // Java 11+
```

Tạo array tại ranh giới sử dụng giúp duy trì kiểm tra kiểu compile time của `List<T>`, đồng thời cung cấp đúng component type runtime của `String[]`.

### 7.4. Generic varargs và `@SafeVarargs`

Varargs thực chất được truyền dưới dạng **mảng**. Khai báo:

```java
static <T> void inspect(List<T>... groups) {
    // ...
}
```

liên quan tới mảng có component type không reifiable. Compiler có thể cảnh báo về *possible heap pollution* ở khai báo hoặc *unchecked generic array creation* tại lời gọi. Một ví dụ method được thiết kế chỉ **đọc mảng varargs và sao chép dữ liệu**:

```java
import java.util.ArrayList;
import java.util.List;

@SafeVarargs
static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

`@SafeVarargs` là cam kết của **người viết phương thức** rằng thân phương thức không thực hiện thao tác không an toàn với varargs array. Annotation không tự chứng minh tính đúng đắn, không làm mất erasure và không “biến” mảng generic thành một mảng reifiable. Trong Java 17, nó chỉ được áp dụng cho các phương thức hợp lệ như `static`, `final`, hoặc instance method `private` (và constructor); không gắn bừa lên phương thức instance có thể override.

Đặc biệt không để varargs array bị trả ra ngoài, ghi vào nó phần tử không cùng `T`, hoặc chuyển sang phương thức khác gây heap pollution nếu chưa kiểm soát đầy đủ hợp đồng. Nếu người dùng API thấy cảnh báo unchecked, hãy kiểm tra **cách phương thức xử lý array thật** trước khi dùng `@SafeVarargs`.

## 8. Ví dụ độc lập: chạy và quan sát erasure bằng Java 17

Ví dụ sau kiểm chứng các dạng chính: type variable không bound/bound, mảng `T[]`, mảng `List<?>[]`, override sinh bridge và Reflection API.

Tạo tệp **`ErasureSignatureDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class ErasureSignatureDemo {
    static final class Box<T extends Number> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T identity(T value) {
        return value;
    }

    static <T extends Number & Comparable<T>> T greater(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T> T[] sameArray(T[] input) {
        return input;
    }

    static List<?>[] wildcardArray() {
        return new List<?>[] { List.of("Java"), List.of(17) };
    }

    static class Parent<T> {
        T value() {
            return null;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String value() {
            return "child";
        }
    }

    public static void main(String[] args) throws Exception {
        Box<Integer> box = new Box<>(7);
        String[] values = {"a", "b"};

        System.out.println(identity("ok"));
        System.out.println(greater(4, 9));
        System.out.println(box.get());
        System.out.println(Arrays.toString(sameArray(values)));
        System.out.println(wildcardArray()[0].get(0));
        System.out.println(new Child().value());

        Method identity = ErasureSignatureDemo.class.getDeclaredMethod(
                "identity", Object.class);
        Method greater = ErasureSignatureDemo.class.getDeclaredMethod(
                "greater", Number.class, Number.class);
        Method sameArray = ErasureSignatureDemo.class.getDeclaredMethod(
                "sameArray", Object[].class);
        Method bridge = Arrays.stream(Child.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("identity: "
                + identity.getReturnType().getSimpleName()
                + " / " + identity.getGenericReturnType().getTypeName());
        System.out.println("greater: "
                + greater.getReturnType().getSimpleName()
                + " / " + greater.getGenericReturnType().getTypeName());
        System.out.println("sameArray: "
                + sameArray.getReturnType().getTypeName()
                + " / " + sameArray.getGenericReturnType().getTypeName());
        System.out.println("bridge: " + bridge.getName()
                + " -> " + bridge.getReturnType().getSimpleName());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac --release 17 ErasureSignatureDemo.java
java ErasureSignatureDemo
```

Stdout chính xác:

```text
ok
9
7
[a, b]
Java
child
identity: Object / T
greater: Number / T
sameArray: java.lang.Object[] / T[]
bridge: value -> Object
```

Giải thích những dòng cuối:

- `getReturnType()` nhìn **kiểu raw sau erasure**: `Object`, `Number`, `Object[]`.
- `getGenericReturnType()` đọc **khai báo generic**, vì class file có thông tin Signature tương ứng: `T`, `T`, `T[]`.
- `Child` có một phương thức bridge (`isBridge() == true`) trả `Object` để khớp với chữ ký đã xóa của `Parent.value()`.
- Không có dòng nào chứng minh một instance `List<String>` giữ tham số `String` như một trường runtime của chính đối tượng list.

### 8.1. Xem descriptor thật bằng `javap`

Sau lệnh `javac`, chạy:

```bash
javap -p -s ErasureSignatureDemo
javap -p -s 'ErasureSignatureDemo$Box'
javap -p -s 'ErasureSignatureDemo$Child'
```

Lưu ý dấu nháy đơn quanh tên lớp lồng khi chạy trong Unix shell để tránh `$` bị khai triển như biến môi trường. Trong PowerShell cũng có thể dùng chuỗi nháy đơn như trên.

Các đoạn quan trọng của đầu ra:

```text
static <T> T identity(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

static <T extends java.lang.Number & java.lang.Comparable<T>> T greater(T, T);
  descriptor: (Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;

static <T> T[] sameArray(T[]);
  descriptor: ([Ljava/lang/Object;)[Ljava/lang/Object;
```

Với `ErasureSignatureDemo$Box`, các thành phần đáng quan sát gồm:

```text
private final T value;
  descriptor: Ljava/lang/Number;

T get();
  descriptor: ()Ljava/lang/Number;
```

Với `ErasureSignatureDemo$Child`, bạn sẽ thấy **hai** phương thức `value()` ở mức class file, với descriptor:

```text
()Ljava/lang/String;
()Ljava/lang/Object;
```

Dùng thêm:

```bash
javap -v -p 'ErasureSignatureDemo$Child'
```

để xem các cờ `ACC_BRIDGE`/`ACC_SYNTHETIC` của phương thức forwarding. `javap -s` vừa cho bạn xem chữ ký generic dưới dạng dễ đọc vừa hiển thị descriptor JVM; vì vậy hãy tìm đúng dòng `descriptor` khi đánh giá erasure.

### 8.2. Vì sao `getDeclaredMethod` dùng `Object.class` và `Number.class`?

Trong chương trình:

```java
getDeclaredMethod("identity", Object.class)
getDeclaredMethod("greater", Number.class, Number.class)
getDeclaredMethod("sameArray", Object[].class)
```

Reflection nhận **các kiểu tham số runtime**, tức là những kiểu ở descriptor đã xóa. Nếu thử tìm `identity(String.class)` bạn sẽ không tìm thấy một overload `identity(String)`: compiler không tạo riêng phương thức cho `String`.

Reflection có API `getGenericParameterTypes()` / `getGenericReturnType()` để xem **khai báo generic còn lưu trong metadata**, nhưng không dùng metadata ấy để xác định tham số kiểu của mọi lời gọi hoặc phần tử thật đang nằm trong collection. Đừng nhầm sự tồn tại của Signature attribute với khả năng runtime tự phân biệt `List<String>` và `List<Integer>`.

## 9. Các lỗi dễ gặp khi phối hợp phương thức và mảng

### Lỗi 1: tưởng `T[]` và `Object[]` giống nhau ở mọi cấp

Erasure có thể biến **chữ ký** `T[]` thành `Object[]`, nhưng bạn không thể lấy một mảng `Object[]` bất kỳ, ép vô điều kiện sang `String[]` rồi mong nó hoạt động. Runtime mảng vẫn biết component type thật và cast sai sẽ gây `ClassCastException`:

```java
Object[] objects = new Object[2];
// String[] strings = (String[]) objects; // Cast có thể biên dịch nhưng lỗi runtime
```

Phân biệt **method descriptor đã xóa** với **kiểu class thực của một mảng** khi debug.

### Lỗi 2: nhầm `new List<?>[n]` với `new List<String>[n]`

Cái đầu hợp lệ vì `List<?>` là reifiable; cái sau không hợp lệ vì `List<String>` không reifiable. Dấu `?` ở đây không phải một cách “bỏ qua hết type safety”, mà phản ánh rằng không có lời hứa cụ thể về kiểu phần tử của từng List.

### Lỗi 3: dùng `@SuppressWarnings("unchecked")` để “chữa” erasure

Suppress chỉ ẩn cảnh báo; cast không được kiểm tra vẫn tồn tại. Chỉ dùng khi API buộc tương tác với legacy hoặc runtime reflection, và bạn có invariant rõ ràng để chứng minh kiểu phần tử được bảo toàn. Với mảng, ưu tiên constructor reference, factory hoặc chuyển dữ liệu qua collection.

### Lỗi 4: chọn overload hoặc override theo type argument

Sau erasure, `List<String>` và `List<Integer>` có cùng raw type `List`; hai phương thức cùng tên, cùng tham số raw tương ứng có thể `name clash`. Với subclass generic, đôi khi compiler **cần** tạo bridge dù bạn không viết phương thức đó. Hãy kiểm tra `javap` trước khi kết luận lớp có một “phương thức lạ” do thư viện khác thêm.

### Lỗi 5: tin rằng xóa kiểu làm biến mất mọi thông tin generic

`javap -v` có thể hiển thị Signature attribute; `Method.getGenericReturnType()` có thể trả `TypeVariable`, `ParameterizedType` hoặc `GenericArrayType`. Nhưng metadata mô tả **khai báo**, không luôn nói được loại phần tử thực tế của mỗi instance tại runtime.

### Lỗi 6: bỏ qua `ArrayStoreException` vì compile time đã chấp nhận phép gán

Mảng có covariance và store check khi chạy. Ví dụ `Object[] alias = new String[1]` hợp lệ, nhưng ghi `Integer` qua alias sẽ ném `ArrayStoreException`. Điều này khác lỗi `ClassCastException` do đọc sai generic ở collection sau heap pollution; hai loại lỗi có nguyên nhân khác nhau.

## 10. Quy trình chẩn đoán một lỗi liên quan erasure

Khi gặp `name clash`, `generic array creation`, `ClassCastException`, `ArrayStoreException`, hoặc phương thức override hoạt động khó hiểu:

1. **Viết lại kiểu source đầy đủ** gồm type variable, type argument, bound và mọi chiều mảng.
2. **Tính erasure**: type variable về bound đầu tiên (hoặc `Object`), parameterized type về raw type, array xóa kiểu thành phần nhưng giữ số chiều.
3. **So sánh chữ ký phương thức sau erasure** để tìm overload trùng nhau; với override, so sánh descriptor lớp cha/lớp con để nhận diện bridge có thể cần.
4. **Kiểm tra kiểu runtime thực** khi dữ liệu là mảng (`getClass().getComponentType()`) hoặc khi có cast unchecked.
5. **Dùng `javap -p -s`**, và `javap -v` khi cần biết bridge/Signature; dùng reflection với các kiểu tham số đã xóa.
6. **Thay đổi hợp đồng API đúng chỗ**: đổi tên overload, dùng một phương thức generic, chọn collection hoặc array factory, tránh raw/unchecked cast.
7. **Biên dịch và thử runtime** với cả đầu vào hợp lệ lẫn đầu vào dễ lộ lỗi (mảng khác component type, nhiều subtype, subclass overriding).

Bảng quyết định nhanh:

| Tình huống | Kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `print(List<String>)` xung đột `print(List<Integer>)` | Cùng descriptor `List` | Đổi tên theo chức năng hoặc hợp nhất thành phương thức generic. |
| `T[] result = new T[n]` | Component `T` không reifiable | Nhận array factory `IntFunction<T[]>` hoặc mảng từ caller. |
| `List<String>[] x = new List<String>[n]` | Component parameterized không reifiable | Dùng `List<List<String>>` hoặc `List<?>[]` nếu wildcard đúng ý nghĩa. |
| Caller cần `String` nhưng `getReturnType()` trả `Object` | Descriptor đã erasure | Xem `getGenericReturnType()` và cast do compiler sinh; đừng kỳ vọng reflection truy xuất specialization riêng. |
| `Child` xuất hiện thêm method synthetic trả `Object` | Generic override có bridge | Xem cờ `ACC_BRIDGE`, quan hệ override và class hierarchy. |
| `String[]` qua alias `Object[]` nhận `Integer` | Runtime store check | Tránh ghi sai component type; sửa cấu trúc dữ liệu nếu cần đa kiểu. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Sau erasure, descriptor cho phương thức bên dưới là gì?

```java
static <T extends Number> T[] echo(T[] input) {
    return input;
}
```

<details>
<summary>Đáp án</summary>

`([Ljava/lang/Number;)[Ljava/lang/Number;` vì `T` bị xóa về bound `Number`, còn kiểu mảng vẫn giữ một chiều.

</details>

**Câu 2.** Tại sao không được overload `find(List<String>)` và `find(List<Integer>)` trong cùng một lớp?

<details>
<summary>Đáp án</summary>

Cả hai danh sách tham số bị xóa thành `List` nên không còn khác biệt về chữ ký phương thức theo quy tắc overload Java; compiler báo `name clash`.

</details>

**Câu 3.** Tại sao `new List<?>[3]` hợp lệ nhưng `new List<String>[3]` không hợp lệ?

<details>
<summary>Đáp án</summary>

Mảng yêu cầu kiểu thành phần reifiable; `List<?>` reifiable còn `List<String>` thì không. JVM runtime component check không thể xác minh riêng type argument `String`.

</details>

**Câu 4.** Một lớp con override `T get()` của lớp cha generic với `String get()`. Vì sao bytecode lớp con có thể chứa cả `Object get()`?

<details>
<summary>Đáp án</summary>

`T` ở lớp cha không bound bị xóa thành `Object`; compiler sinh một bridge synthetic chuyển tiếp tới `String get()` nhằm giữ dispatch đa hình qua reference kiểu lớp cha.

</details>

**Câu 5.** `getGenericReturnType()` của `identity` hiển thị `T`. Điều đó có chứng minh mỗi lần gọi `identity(5)` tạo một phương thức bytecode mới cho `Integer`?

<details>
<summary>Đáp án</summary>

Không. `T` là metadata về **khai báo** generic của một phương thức, trong khi descriptor thực dùng `Object`. Compiler kiểm tra suy luận kiểu cho từng lời gọi; nó không tạo specialization mới của `identity` cho mỗi kiểu tham số.

</details>

## 12. Ghi nhớ

Để đọc đúng erasure, phải tách **ba tầng**: kiểu generic mà Java compiler kiểm tra ở source, **descriptor JVM** sau xóa kiểu và **kiểu runtime thật của đối tượng/mảng**. Trong chữ ký phương thức, `T` trở thành `Object` hoặc bound đầu tiên; `List<String>` và `List<Integer>` đều về `List`; override generic có thể cần bridge. Trong kiểu mảng, `T[]` erases thành `Object[]` hoặc mảng của bound, nhưng JVM vẫn kiểm tra component type của mảng được tạo. Đây là nền tảng để tránh overload trùng chữ ký, cast unchecked nguy hiểm và tạo mảng generic sai cách.