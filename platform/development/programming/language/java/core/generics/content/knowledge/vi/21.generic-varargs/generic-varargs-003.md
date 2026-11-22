# Cảnh báo tại nơi khai báo và nơi gọi phương thức varargs trong Java Generics

## 1. Tình huống mở đầu

Java cho phép phương thức nhận số lượng đối số thay đổi (*varargs*) qua dấu `...`:

```java
static void show(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

Cách gọi:

```java
show("Java", "Generics");
```

rất tiện vì người gọi không phải tự tạo `String[]`. Khi kết hợp varargs với **Generics**, tình hình phức tạp hơn:

```java
static void showFirst(List<String>... lists) {
    System.out.println(lists[0].get(0));
}

// Ở một method khác:
showFirst(List.of("Java"), List.of("Generics"));
```

`javac` có thể phát **hai cảnh báo tại hai vị trí khác nhau**:

- **Tại khai báo** `List<String>... lists`: `Possible heap pollution from parameterized vararg type List<String>`.
- **Tại lời gọi** `showFirst(...)`: `unchecked generic array creation for varargs parameter of type List<String>[]`.

Cả hai liên quan đến cơ chế **mảng varargs và type erasure**, nhưng không đồng nghĩa rằng compiler đã phát hiện lỗi thực tế trong dữ liệu. Chúng là tín hiệu: kiểu mảng được dùng để truyền đối số có kiểu thành phần **không reifiable**, nên compiler/runtime không thể xác minh mọi type argument bằng array store check.

Bài này giải thích khi nào cảnh báo xuất hiện, vì sao chúng chỉ đến các vị trí khác nhau, lúc nào có rủi ro *heap pollution*, cách đọc `javac -Xlint`, phân biệt varargs reifiable và generic varargs, và cách thiết kế hoặc chú thích API an toàn bằng `@SafeVarargs` khi có đủ cơ sở.

## 2. Varargs thực chất là một tham số mảng

Ở source:

```java
static void printAll(String... items) {
    for (String item : items) {
        System.out.println(item);
    }
}
```

Tham số `items` **bên trong phương thức** có kiểu `String[]`. Lời gọi:

```java
printAll("a", "b");
```

thường được compiler xử lý như một lời gọi truyền mảng `String[]` chứa các đối số.

Bạn cũng có thể gọi bằng mảng có sẵn:

```java
String[] names = {"a", "b"};
printAll(names);
```

Một varargs method về bản chất có tham số mảng ở vị trí cuối cùng; vì thế:

```java
static void take(List<String>... groups) {
    System.out.println(groups.length);
}
```

có tham số `groups` kiểu source là **`List<String>[]`**, dù cú pháp được viết dưới dạng `...`.

Vấn đề: Java không cho biểu thức tạo mảng thông thường:

```java
// Không hợp lệ:
List<String>[] array = new List<String>[2];
```

vì `List<String>` không phải **reifiable type**. Thế nhưng cú pháp varargs lại cho phép compiler xử lý lời gọi `take(List.of("a"), List.of("b"))` bằng một mảng runtime có component `List`. Đây chính là chỗ cần cảnh báo.

### 2.1. Hai cách gọi varargs

Giả sử:

```java
static void count(String... words) {
    System.out.println(words.length);
}
```

Có hai hình thức quan trọng:

```java
count("a", "b");                 // Variable-arity invocation.
count(new String[] {"a", "b"});  // Fixed-arity invocation với array thật.
```

Ở cách gọi thứ nhất, compiler sắp xếp các đối số thành array. Ở cách gọi thứ hai, caller chủ động cung cấp array.

Với `List<T>...`, cảnh báo **tại lời gọi** thường nhắm đến trường hợp compiler phải tạo array varargs **ngầm** với kiểu thành phần non-reifiable. Một lời gọi dùng sẵn array có thể không phát đúng cảnh báo “unchecked generic array creation” tại dòng gọi, nhưng cách array đó được tạo/lấy từ đâu vẫn phải được kiểm tra. Không nên chỉ dựa vào việc dòng gọi không có warning để kết luận API an toàn.

## 3. Vì sao kiểu thành phần của varargs quan trọng?

Mảng Java giữ runtime component type:

```java
String[] strings = new String[1];
Object[] alias = strings;
alias[0] = 123; // ArrayStoreException.
```

JVM biết mảng thật là `String[]` và từ chối giá trị `Integer`.

Nhưng với:

```java
List<String> words = List.of("Java");
List<Integer> ids = List.of(123);
```

`List<String>` và `List<Integer>` đều có runtime interface cơ bản là `List`; type argument không được chuyên biệt hóa thành class runtime riêng.

Do đó nếu có một array chứa `List` và code đưa `List<Integer>` vào ô mà code khác **tin** là `List<String>`, array store check chỉ xác minh object là `List` — nó không duyệt từng phần tử bên trong.

Trong trường hợp varargs:

```java
static void method(List<String>... groups) {
    // Trong method, groups là List<String>[] ở source.
}
```

type erasure khiến JVM không có component class runtime cho `List<String>` riêng biệt. Compiler cảnh báo rằng code bên trong hoặc các alias có thể phá hợp đồng phần tử của array/list.

### 3.1. Reifiable và non-reifiable

| Loại varargs | Kiểu thành phần của array | Cảnh báo unchecked varargs thông thường? |
| --- | --- | --- |
| `String... values` | `String` reifiable | Không |
| `int... values` | Primitive `int` | Không |
| `List<?>... groups` | `List<?>` reifiable | Không, nếu không có thao tác unchecked khác |
| `Map<?, ?>... maps` | `Map<?, ?>` reifiable | Không vì chính varargs component |
| `List... groups` | Raw `List` reifiable | Không vì non-reifiable component; có thể có cảnh báo `rawtypes` |
| `List<String>... groups` | `List<String>` non-reifiable | Có thể có warning ở khai báo và lời gọi |
| `List<? extends Number>... groups` | Wildcard có bound, non-reifiable | Có thể có warning |
| `<T> void run(T... values)` | `T` không reifiable | Có thể có warning |
| `<T> void run(List<T>... groups)` | `List<T>` không reifiable | Có thể có warning |

**Dấu `?` chỉ đủ cho reifiability khi là wildcard hoàn toàn không giới hạn và tất cả type arguments ở kiểu tham số hóa đều như vậy.** `List<? extends Number>` vẫn là non-reifiable; không thể coi nó tương đương `List<?>`.

Một warning được gắn với varargs component **không có nghĩa** mọi code dùng generic đều không an toàn. Chẳng hạn một method `<T> T first(List<T> values)` không phải varargs, nên không có cơ chế array ngầm này.

## 4. Cảnh báo tại nơi khai báo phương thức

Xem:

```java
static void printFirst(List<String>... groups) {
    System.out.println(groups[0].get(0));
}
```

Khi bật:

```bash
javac --release 17 -Xlint:unchecked VarargsWarningDemo.java
```

`javac` phát warning ở vị trí khai báo varargs:

```text
warning: [unchecked] Possible heap pollution from parameterized vararg type List<String>
```

Thông báo này có nghĩa **về mặt cấu trúc**, tham số cuối được biểu diễn như một array có component `List<String>` non-reifiable, và heap pollution *có thể* xảy ra khi thao tác không an toàn trên array hoặc alias.

Nó không chứng minh thân `printFirst` đã ghi sai bất kỳ phần tử nào. Nếu chỉ đọc và không làm array thoát ra ngoài, method đó có thể thực tế an toàn. Compiler vẫn cảnh báo vì kiểu khai báo tạo điều kiện cho các thao tác không kiểm tra được.

### 4.1. Khai báo method có type parameter riêng

```java
static <T> int countElements(List<T>... groups) {
    int total = 0;
    for (List<T> group : groups) {
        total += group.size();
    }
    return total;
}
```

Ở đây `T` là type parameter của **method**, còn mỗi đối số varargs là một `List<T>`. `List<T>` non-reifiable, nên compiler phát cảnh báo:

```text
warning: [unchecked] Possible heap pollution from parameterized vararg type List<T>
```

Đừng nhầm type variable của method với phần tử của array. Java không có cách tạo một class array runtime có component specialization `List<T>` với `T` thay đổi theo từng lời gọi.

### 4.2. Cảnh báo ở khai báo có thể tồn tại dù thân method chỉ đọc

```java
static <T> int countElements(List<T>... groups) {
    int result = 0;
    for (List<T> group : groups) {
        result += group.size();
    }
    return result;
}
```

Method chỉ đọc `size`, không sửa `groups` hay danh sách con. Rủi ro trong implementation này thấp nếu không có alias bên ngoài sửa array. Nhưng compiler không phải một hệ thống chứng minh tổng quát cho mọi thiết kế method generic varargs.

Điều cần làm là **review invariant và cách xử lý array**: có ghi vào slot không, có tiết lộ array cho code khác không, có alias bằng `Object[]` không, có ép kiểu hoặc truyền array sang API không kiểm soát không? Sau review, mới cân nhắc `@SafeVarargs` nếu phương thức đủ điều kiện.

## 5. Cảnh báo tại nơi gọi phương thức

Định nghĩa:

```java
static void printFirst(List<String>... groups) {
    System.out.println(groups[0].get(0));
}
```

Lời gọi:

```java
printFirst(List.of("Java"), List.of("Generics"));
```

có thể phát cảnh báo:

```text
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Nội dung chính xác của thông báo có thể khác theo context suy luận kiểu, nhưng ý nghĩa là: compiler phải cung cấp array chứa các đối số varargs mà kiểu thành phần ở source là `List<String>` — một kiểu non-reifiable — nên việc tạo/đưa array đó qua ranh giới varargs không được kiểm tra generic đầy đủ.

**Điểm phân biệt:** cảnh báo khai báo nói API nhận varargs với kiểu thành phần không reifiable; cảnh báo ở lời gọi nói **tại đây** compiler đang tạo/cung cấp array varargs non-reifiable.

### 5.1. Type inference khiến thông báo ở lời gọi có kiểu cụ thể

Với:

```java
static <T> int countElements(List<T>... groups) {
    int count = 0;
    for (List<T> group : groups) count += group.size();
    return count;
}
```

Lời gọi:

```java
countElements(List.of("A", "B"), List.of("C"));
```

khi `javac` suy luận `T = String` có thể sinh:

```text
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Ở khai báo, thông báo dùng `List<T>`; ở lời gọi, type inference đã xác định `String`, nên thông báo có thể hiển thị `List<String>[]`. Đây không phải mâu thuẫn: cùng một rủi ro được nhìn từ **hai bối cảnh khác nhau**.

Không được kết luận rằng vì caller tự tạo `List.of("A")` có generic type safety, mảng varargs `List<String>[]` chắc chắn reifiable. Collection được tạo an toàn và cách **đóng gói vào array generic** là hai vấn đề khác nhau.

### 5.2. Một phương thức có thể sinh hai warning

Bật lint cho cùng file có thể thấy warning tại cả dòng định nghĩa:

```java
static void printFirst(List<String>... groups) { ... }
```

và dòng sử dụng:

```java
printFirst(List.of("Java"));
```

Hai warning không phải compiler đếm một lỗi hai lần. Chúng phản ánh **hai bề mặt rủi ro**: thiết kế API và việc tạo mảng tại caller.

Bạn có thể xử lý một trong hai nhưng vẫn còn vấn đề khác nếu phương thức hoặc lời gọi khác tiếp tục sử dụng cấu trúc không kiểm soát.

## 6. Tại sao compiler cảnh báo dù body trông vô hại?

Một method chỉ đọc `size()` của `List<String>...` có thể chạy đúng mà vẫn có **declaration/call-site warnings**: type argument String không reifiable trong array được chuẩn bị cho varargs call. Heap pollution chỉ **thực sự hình thành** khi có đường ghi/cast làm một biến generic chứa dữ liệu không đúng hợp đồng.

Đường gây lỗi điển hình:

```java
static void corrupt(List<String>... groups) {
    Object[] alias = groups;       // Cùng mảng, không copy.
    alias[0] = List.of(42);       // Component runtime chỉ là List.
    String item = groups[0].get(0); // ClassCastException khi đọc.
}
```

Phương thức minh họa trên cần import `java.util.List`, đặt trong class và **không dùng production**. Nếu thử ghi một String trực tiếp vào array runtime List[], JVM lại có thể phát `ArrayStoreException`. Vì thế array store check **vẫn tồn tại**, chỉ không nhận biết generic argument bên trong List.

Khi chẩn đoán, đừng suy từ việc có warning rằng code chắc chắn làm sai dữ liệu. Hãy tìm thao tác ghi/escape cụ thể rồi quyết định có thể cam kết `@SafeVarargs` hay nên thay API. **Nội dung chính của bài này là hai vị trí cảnh báo**: declaration mô tả nguy cơ của signature; call site mô tả việc tạo array non-reifiable tại lần gọi.

## 7. `@SafeVarargs` giải quyết điều gì?

Java có annotation:

```java
@SafeVarargs
```

Dùng khi tác giả một varargs method hoặc constructor **cam kết** implementation không thực hiện các thao tác không an toàn trên array varargs có component non-reifiable.

Ví dụ method an toàn:

```java
@SafeVarargs
static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Method này:

- Chỉ duyệt các danh sách nguồn.
- Đưa phần tử vào một `ArrayList<T>` mới bằng API generic đã được kiểm tra.
- Không ghi một list sai kiểu vào array `groups`.
- Không công bố array `groups` cho code khác sửa.
- Trả **list mới**, không trả array varargs hoặc alias tới nó.

Đây là trường hợp có thể có cơ sở để dùng `@SafeVarargs`. Khi có annotation hợp lệ, compiler có thể bỏ những warning *unchecked generic varargs* ở **khai báo và nơi gọi** liên quan tới method đó.

**Quan trọng:** annotation **không** làm `List<T>` reifiable, không tạo runtime component type mới, không validate từng phần tử và không tự chứng minh code an toàn.

### 7.1. `@SafeVarargs` khác `@SuppressWarnings("unchecked")`

`@SuppressWarnings("unchecked")` là suppression cảnh báo trong một phạm vi nhất định, có thể áp dụng cho nhiều loại thao tác unchecked khác nhau.

`@SafeVarargs` là lời cam kết đặc thù cho varargs method/constructor về cách sử dụng non-reifiable varargs parameter. Nó tác động tới các cảnh báo varargs có liên quan, bao gồm ở caller, nhưng không phải một chứng nhận được JVM cưỡng chế.

Đừng gắn `@SafeVarargs` lên một method chỉ để làm output lint sạch khi body còn gán alias hoặc đưa list sai kiểu vào array.

### 7.2. Điều kiện áp dụng annotation trong Java 17

`@SafeVarargs` được phép tại:

- `static` varargs method.
- `final` instance varargs method.
- `private` instance varargs method (được phép từ Java 9).
- Constructor có tham số varargs.

Nó không hợp lệ trên một instance method **có thể bị override** và không hợp lệ trên method **không phải varargs**.

Ví dụ hợp lệ về **vị trí gắn**:

```java
@SafeVarargs
static <T> void staticMethod(T... values) {
    // Phải bảo đảm nội dung xử lý an toàn.
}
```

```java
class Example {
    @SafeVarargs
    private final <T> void privateMethod(T... values) {
        // Cần bảo đảm hợp đồng an toàn.
    }
}
```

Khai báo `private final` ở đây chỉ minh họa điều kiện được phép; `private` đã đủ cho vị trí gắn annotation trong Java 17. Đừng nhầm việc annotation hợp lệ về cú pháp với việc method thực sự an toàn.

### 7.3. Compiler có thể cảnh báo ngay trong method dù đã có annotation

Xét method **không an toàn**, cố tình gắn annotation sai về ngữ nghĩa:

```java
@SafeVarargs
static <T> void lie(List<T>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42);
}
```

Với:

```bash
javac --release 17 -Xlint:varargs -Xlint:unchecked UnsafeAnnotationDemo.java
```

`javac` đã được kiểm chứng phát warning ở dòng alias:

```text
warning: [varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter groups
```

Điều này cho thấy ngay cả khi annotation khiến một số cảnh báo varargs tại khai báo/caller biến mất, các thao tác có vẻ không an toàn trong body vẫn có thể bị `-Xlint:varargs` cảnh báo.

**Không nên để annotation này trong code thật** khi method có khả năng phá type invariant. Hãy sửa thiết kế body, không chỉ dập warning.

## 8. Những hành vi khiến varargs API không an toàn

Khi review phương thức có `List<T>...` hoặc `T...`, hãy chú ý:

### 8.1. Ghi vào array qua alias rộng

```java
Object[] alias = groups;
alias[0] = List.of(42);
```

Đây là ví dụ kinh điển gây heap pollution với `List<T>[]`. Dù `groups` khai báo là `List<String>[]`, runtime array chỉ biết component `List`.

### 8.2. Trả nguyên varargs array

```java
@SafeVarargs // Không phải lời khuyên dùng annotation ở đây.
static <T> List<T>[] expose(List<T>... groups) {
    return groups;
}
```

Nếu array lọt ra ngoài cho caller hoặc mã khác giữ và sửa, invariant có thể bị phá. Với `-Xlint:varargs`, compiler có thể cảnh báo về việc để non-reifiable varargs array thoát khỏi phạm vi kiểm soát.

Nếu mục tiêu là trả dữ liệu, hãy cân nhắc trả `List<List<T>>` mới hoặc một cấu trúc immutable/copy đã được thiết kế, không tiết lộ array varargs.

### 8.3. Truyền array cho code không kiểm soát

```java
static void forward(Object[] values) {
    // Method này có thể thay các phần tử trong array.
}
```

Nếu một method có generic varargs gọi một API nhận `Object[]` rồi cho phép API đó sửa array, không thể khẳng định varargs an toàn chỉ vì code hiện tại không trực tiếp gán `groups[0]`.

Một *safe varargs method* cần kiểm soát cả alias và những method được gọi với array. **Không có thao tác ghi trong vài dòng hiện tại chưa đủ** nếu array có thể escape tới nơi khác.

### 8.4. Mở quyền ghi vào các list con

Ngay cả khi array không được ghi trực tiếp, code dùng raw alias của từng list để thêm phần tử sai kiểu vẫn có thể gây heap pollution:

```java
List raw = groups[0];
raw.add(42); // Unchecked call có thể phá List<String>.
```

Đây là vấn đề raw type kết hợp với varargs. Tránh raw alias, unchecked cast và mutation khi hợp đồng type argument không được bảo đảm.

## 9. Varargs reifiable: khi nào không cần `@SafeVarargs`?

### 9.1. `List<?>...`

```java
static int countUnknown(List<?>... groups) {
    int total = 0;
    for (List<?> group : groups) {
        total += group.size();
    }
    return total;
}
```

`List<?>` là reifiable vì type argument là wildcard không giới hạn. Do đó parameter của varargs này không gặp cùng cảnh báo về non-reifiable component.

Call hợp lệ:

```java
int count = countUnknown(
        List.of("a"),
        List.of(1, 2)
);
// count == 3
```

Dấu `?` không cho phép bạn đọc phần tử thành một kiểu cụ thể như `String` nếu chưa kiểm tra. Nhưng method chỉ tính kích thước nên không cần biết type argument.

**Chỉ thay `List<T>...` bằng `List<?>...` khi quan hệ kiểu `T` thực sự không cần thiết.** Nếu method phải liên kết kiểu đầu vào với kết quả (`List<T>`), xóa `T` có thể làm API mất type safety hoặc khả năng suy luận kiểu có ý nghĩa.

### 9.2. `String...`, `int...`

```java
static int sum(int... values) {
    int result = 0;
    for (int value : values) result += value;
    return result;
}
```

`int` là kiểu primitive reifiable. `String` cũng reifiable. Những varargs này không có rủi ro **generic array component non-reifiable** như `List<T>...`.

Method vẫn có thể chứa lỗi logic hoặc mutation không mong muốn, nhưng đó không phải cảnh báo unchecked generic array creation đang xét.

### 9.3. `List<?>...` không đồng nghĩa `List<String>...`

Nếu API phải bảo đảm tất cả nhóm chứa `String`, `List<?>...` không tự kiểm tra điều đó. `List<?>` có thể chứa `String`, `Integer`, `Boolean` và các giá trị khác. Đổi chữ ký chỉ để làm warning biến mất có thể nới lỏng hợp đồng sai mục đích.

Khi cần cùng một kiểu `T`, dùng generics phù hợp, hoặc cân nhắc truyền `List<? extends List<T>>` thay cho varargs nếu muốn tránh array ngầm.

## 10. Ví dụ Java 17 hoàn chỉnh: cả hai vị trí cảnh báo

Tạo tệp **`VarargsWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class VarargsWarningDemo {
    static void printFirst(List<String>... batches) {
        System.out.println("first=" + batches[0].get(0));
    }

    static <T> int countElements(List<T>... batches) {
        int total = 0;
        for (List<T> batch : batches) total += batch.size();
        return total;
    }

    @SafeVarargs
    static <T> List<T> flatten(List<? extends T>... batches) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> batch : batches) result.addAll(batch);
        return result;
    }

    static int countUnknown(List<?>... batches) {
        int total = 0;
        for (List<?> batch : batches) total += batch.size();
        return total;
    }

    static <T> T corruptAndRead(List<T>... batches) {
        Object[] alias = batches;
        alias[0] = List.of(42);
        return batches[0].get(0);
    }

    public static void main(String[] args) {
        printFirst(List.of("Java"), List.of("Generics"));

        System.out.println("count="
                + countElements(List.of("A", "B"), List.of("C")));

        System.out.println("flatten="
                + flatten(List.of(1, 2), List.of(3)));

        System.out.println("unknown="
                + countUnknown(List.of("x"), List.of(1, 2)));

        try {
            String item = corruptAndRead(List.of("safe"));
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("pollution=" + ex.getClass().getSimpleName());
        }
    }
}
```

Lưu ý `import java.util.Arrays` không được dùng trong body; đây là import thừa không ảnh hưởng biên dịch và có thể bỏ khi đưa code vào dự án. Ba method `printFirst`, `countElements`, `corruptAndRead` **cố ý giữ chữ ký non-reifiable varargs không có `@SafeVarargs`** để người học quan sát warning. Trong đó `corruptAndRead` cố tình không an toàn; không đưa vào production.

Biên dịch:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsWarningDemo.java
```

Với source trên, `javac` đã phát **6 cảnh báo**:

| Vị trí | Nhóm cảnh báo | Nội dung chính |
| --- | --- | --- |
| Khai báo `printFirst(List<String>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<String>` |
| Khai báo `countElements(List<T>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<T>` |
| Khai báo `corruptAndRead(List<T>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<T>` |
| Lời gọi `printFirst(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |
| Lời gọi `countElements(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |
| Lời gọi `corruptAndRead(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |

Không có cảnh báo varargs từ `flatten(...)` vì annotation được dùng trên method tĩnh có body an toàn trong ví dụ. `countUnknown(...)` không cần annotation vì component `List<?>` reifiable.

Tên class, số dòng, đường dẫn source và một phần chi tiết diagnostic có thể phụ thuộc JDK. Hãy quan sát **thông điệp** và vị trí khai báo/lời gọi, thay vì khẳng định caret luôn ở cùng một cột.

Chạy:

```bash
java VarargsWarningDemo
```

Stdout chính xác:

```text
first=Java
count=3
flatten=[1, 2, 3]
unknown=3
pollution=ClassCastException
```

### 10.1. Diễn giải output

`first=Java` và `count=3` cho thấy method generic varargs có thể thực thi đúng dù có compiler warning. Warning báo **rủi ro cấu trúc**, không phải dữ liệu chắc chắn đang bị sai.

`flatten=[1, 2, 3]` minh họa cách gom phần tử vào list mới không làm varargs array escape hoặc bị thay bởi list sai kiểu.

`unknown=3` chứng minh một API dùng `List<?>...` vẫn có thể xử lý nhiều loại list mà không cần một type variable liên kết chúng.

`pollution=ClassCastException` là hậu quả có chủ đích từ method unsafe: nó ghi `List<Integer>` qua alias `Object[]` rồi caller dùng giá trị như `String`.

## 11. Ví dụ cho biết `@SafeVarargs` không phải chứng nhận an toàn

Một tệp minh họa riêng **`UnsafeAnnotationDemo.java`**:

```java
import java.util.List;

class UnsafeAnnotationDemo {
    @SafeVarargs
    static <T> void lie(List<T>... groups) {
        Object[] objects = groups;
        objects[0] = List.of(42);
    }

    static void invoke() {
        lie(List.of("ok"));
    }
}
```

Biên dịch:

```bash
javac --release 17 -Xlint:varargs -Xlint:unchecked UnsafeAnnotationDemo.java
```

`javac` đã cảnh báo:

```text
warning: [varargs] Varargs method could cause heap pollution
from non-reifiable varargs parameter groups
```

Cảnh báo nằm tại thao tác dùng alias của varargs array. Annotation không làm body an toàn và không bảo đảm mọi compiler/toolchain có thể xác minh tất cả nguy cơ thực tế.

**Cách sửa:** bỏ alias có quyền ghi không kiểm soát; không thay list trong varargs array bằng dữ liệu có type argument khác; nếu chỉ cần dữ liệu đầu ra, tạo collection mới với kiểu rõ ràng.

### 11.1. Annotation bị từ chối ở phương thức không hợp lệ

Tệp minh họa lỗi **`InvalidAnnotationDemo.java`**:

```java
import java.util.List;

class InvalidAnnotationDemo {
    @SafeVarargs
    void notFinal(List<String>... values) {
    }

    @SafeVarargs
    static void notVarargs(List<String> values) {
    }
}
```

Chạy:

```bash
javac --release 17 InvalidAnnotationDemo.java
```

Compiler từ chối cả hai trường hợp:

```text
Invalid SafeVarargs annotation. Instance method ... is neither final nor private.
Invalid SafeVarargs annotation. Method ... is not a varargs method.
```

Những ví dụ này dùng để nhận diện giới hạn cú pháp của `@SafeVarargs`; chúng **cố tình không biên dịch**.

Không nên thay `void notFinal` thành `final void notFinal` chỉ nhằm qua compiler nếu bản thân method vẫn làm heap pollution. Annotation vừa cần **đúng vị trí**, vừa cần **đúng cam kết an toàn**.

## 12. Cách xử lý cảnh báo hợp lý khi thiết kế API

Khi thấy warning ở khai báo hoặc lời gọi, đừng lập tức thêm suppression. Hãy quyết định theo nhu cầu thật của API.

### Hướng A — Dùng `List<?>...` nếu chỉ quan sát các list

```java
static int totalSize(List<?>... lists) {
    int total = 0;
    for (List<?> list : lists) total += list.size();
    return total;
}
```

Hợp đồng rõ ràng: nhận nhiều list có type argument bất kỳ, chỉ tính size. Không cần `<T>`, vì không có quan hệ cùng `T` phải bảo toàn.

### Hướng B — Dùng collection bên ngoài thay varargs array

Nếu caller đã có nhiều list cùng một kiểu `T`, có thể nhận `List<? extends List<? extends T>>` hoặc chữ ký phù hợp hơn với nghiệp vụ:

```java
static <T> List<T> flattenGroups(
        List<? extends List<? extends T>> groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Đây là method minh họa cần import `java.util.List` và `java.util.ArrayList`. Cách gọi:

```java
List<String> result = flattenGroups(
        List.of(List.of("a", "b"), List.of("c")));
```

Không cần compiler tự tạo một `List<T>[]` varargs array. Phương pháp này thường phù hợp khi số nhóm đã có sẵn trong collection hoặc cấu trúc cần chia sẻ giữa nhiều API.

### Hướng C — Giữ varargs nhưng chứng minh method an toàn

Nếu fluent API cần cú pháp truyền nhiều đối số tiện lợi, giữ `List<? extends T>...` nhưng:

- Không ghi phần tử sai kiểu vào array.
- Không trả/giữ/thả array tới mã có thể sửa.
- Không tạo raw/unchecked alias phá contract.
- Chỉ dùng giá trị đọc được qua API generic được compiler kiểm tra.
- Trả collection mới hoặc kết quả immutable khi hợp đồng phù hợp.
- Gắn `@SafeVarargs` **chỉ khi** method/constructor thuộc nhóm được phép và các điều kiện an toàn đã được chứng minh.

### Hướng D — Sửa nguồn dữ liệu hoặc ownership

Một method có vẻ chỉ đọc nhưng nhận được array hoặc list mutable từ bên ngoài vẫn cần hiểu ownership. Nếu code khác giữ alias và sửa đồng thời, vấn đề có thể vượt ra ngoài generic varargs warning (đồng bộ hóa, snapshot, validation). Không giả định `@SafeVarargs` làm đầu vào immutable hoặc thread-safe.

## 13. Đọc warning theo vị trí và loại

Một cách chẩn đoán từng bước:

1. **Bật lint rõ ràng**: `javac -Xlint:unchecked -Xlint:varargs`.
2. **Xác định caret nằm ở khai báo hay lời gọi**; đừng chỉ nhìn số warnings.
3. Tại khai báo, ghi lại component type của varargs: `T`, `List<T>`, `List<String>`, `List<?>`, `String`.
4. Tại lời gọi, kiểm tra compiler có phải tạo mảng varargs ngầm hay caller truyền array có sẵn; xem type inference chọn `T` thành gì.
5. Xem body: có `Object[]` alias, gán array slot, trả varargs array hoặc truyền sang code có thể sửa không?
6. Kiểm tra các raw types, unchecked casts, thao tác với list con và luồng dữ liệu bên ngoài.
7. Chọn sửa API (`List<?>...`, collection ngoài) hoặc giữ generic varargs với `@SafeVarargs` khi có chứng cứ.
8. Biên dịch lại với lint và chạy cả đường hợp lệ/đường lỗi để xác nhận đã giải quyết **nguyên nhân**, không chỉ ẩn thông báo.

### 13.1. Bảng chẩn đoán nhanh

| Thông báo/hiện tượng | Nơi xuất hiện thường gặp | Cách đọc đúng |
| --- | --- | --- |
| `Possible heap pollution from parameterized vararg type List<T>` | Khai báo method | Parameter varargs có component non-reifiable. |
| `unchecked generic array creation for varargs parameter ...` | Lời gọi varargs | Compiler tạo array ngầm mà type argument không được runtime kiểm tra. |
| `[varargs] Varargs method could cause heap pollution ...` | Bên trong method có `@SafeVarargs`, khi bật lint phù hợp | Có thao tác trên varargs array có thể mất type safety. |
| `[rawtypes] found raw type: List` | Khai báo dùng raw List | Đây là vấn đề raw type; khác việc `List<T>` non-reifiable. |
| `ClassCastException` khi nhận generic result | Runtime, thường tại chỗ đọc/nhận | Có thể dữ liệu bị heap pollution trước đó do alias/cast. |
| `ArrayStoreException` khi ghi vào array | Runtime tại phép gán | Object không phù hợp với **runtime component class** của array. |
| Không còn warning sau `@SafeVarargs` | Khai báo/caller | Chưa chứng minh method an toàn; cần review body. |

### 13.2. Khi build chỉ báo “uses unchecked or unsafe operations”

Nếu chạy `javac` không bật chi tiết lint, compiler có thể chỉ phát một ghi chú yêu cầu biên dịch lại với `-Xlint:unchecked`. Hãy dùng lệnh:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsWarningDemo.java
```

để thấy vị trí cụ thể. Đừng tìm cách fix qua việc đổi `-nowarn`, tắt hết compiler warnings hoặc suppression ở cấp cả package.

## 14. Những lỗi tư duy thường gặp

**Lỗi 1 — Warning ở khai báo chứng minh method đã ghi sai dữ liệu.** Không đúng. Compiler báo về khả năng heap pollution từ component non-reifiable, kể cả khi body chỉ đọc.

**Lỗi 2 — Warning ở lời gọi là một lỗi mới không liên quan method signature.** Không đúng. Nó phản ánh thao tác tạo mảng varargs ngầm cho một method có component non-reifiable; có liên hệ trực tiếp với signature và type inference.

**Lỗi 3 — Generic type argument chắc chắn được kiểm tra trong một `List<String>[]`.** Không đúng. Runtime array thường chỉ kiểm tra component class `List`, không duyệt các phần tử bên trong list.

**Lỗi 4 — `@SafeVarargs` làm mọi lời gọi an toàn.** Không đúng. Nó là lời cam kết của tác giả. Method sai vẫn có thể gây heap pollution và `ClassCastException`.

**Lỗi 5 — Dùng `@SuppressWarnings("unchecked")` là đã giải quyết vấn đề.** Không đúng. Nó chỉ ẩn cảnh báo, không làm runtime có thêm thông tin kiểu hay kiểm tra dữ liệu.

**Lỗi 6 — `List<?>...` cũng có warning giống `List<T>...`.** Với đúng component `List<?>` reifiable, warning non-reifiable varargs component không phát sinh. Vẫn có thể có warning khác nếu code dùng raw/cast không an toàn.

**Lỗi 7 — Cứ thấy `List<T>...` thì phải đổi ngay thành `List<?>...`.** Nếu method cần liên kết một `T` giữa input và output, đổi sang wildcard có thể làm mất tính chính xác của API. Đánh giá mục đích trước khi sửa.

**Lỗi 8 — Chỉ kiểm tra body tại một thời điểm mà quên array alias có thể escape.** Một array truyền sang method khác, trả ra ngoài hoặc lưu lại để sửa sau vẫn có thể phá invariant. Review toàn bộ đường dữ liệu.

**Lỗi 9 — Compiler warning biến mất nghĩa là dữ liệu đã được validate.** Không. Một API có thể im lint nhưng dữ liệu từ raw/legacy hoặc nguồn ngoài vẫn sai. Generic type checking, runtime validation và ownership là các trách nhiệm khác nhau.

## 15. Bài thực hành

### Bài 1 — Nhận diện hai nơi cảnh báo

Cho method:

```java
static void visit(List<String>... lists) {
    System.out.println(lists.length);
}
```

và call:

```java
visit(List.of("A"), List.of("B"));
```

Nếu bật `-Xlint:unchecked`, những vị trí nào có thể được cảnh báo?

<details>
<summary>Đáp án</summary>

Tại khai báo: `Possible heap pollution from parameterized vararg type List<String>`. Tại lời gọi: `unchecked generic array creation for varargs parameter of type List<String>[]`. Chúng mô tả hai khía cạnh của cùng cấu trúc mảng non-reifiable.

</details>

### Bài 2 — Vì sao `List<?>...` khác `List<String>...`?

<details>
<summary>Đáp án</summary>

`List<?>` là reifiable vì argument là wildcard không giới hạn; `List<String>` không reifiable. JVM có thể tạo mảng component `List` cho cả một số cấu trúc, nhưng việc dùng generic component `List<String>` trong varargs mang rủi ro về type argument không kiểm tra được, khiến compiler phát cảnh báo.

</details>

### Bài 3 — Có nên gắn `@SafeVarargs`?

```java
static <T> T wrong(List<T>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42);
    return groups[0].get(0);
}
```

<details>
<summary>Đáp án</summary>

Không. Body ghi một `List<Integer>` vào array có source component `List<T>`, có thể tạo heap pollution. Phải sửa body/thiết kế trước, không gắn annotation chỉ để làm warning ở caller biến mất.

</details>

### Bài 4 — Khi nào nên chọn collection bên ngoài thay varargs?

<details>
<summary>Đáp án</summary>

Khi caller đã có danh sách nhóm, cần truyền qua nhiều tầng hoặc không cần cú pháp tiện lợi của `...`, nhận một `List<? extends List<? extends T>>` hay cấu trúc domain phù hợp có thể tránh array varargs ngầm và giữ generic contract rõ ràng.

</details>

### Bài 5 — Một method `static` với `@SafeVarargs` đã được compiler chấp nhận. Có phải body luôn an toàn không?

<details>
<summary>Đáp án</summary>

Không. `static` chỉ là điều kiện hợp lệ về vị trí annotation; người viết vẫn phải bảo đảm không tạo heap pollution. `-Xlint:varargs` có thể cảnh báo về thao tác alias hoặc exposure của non-reifiable varargs array.

</details>

### Bài 6 — `@SafeVarargs` có thể gắn vào instance method không `final`, không `private` trên Java 17 không?

<details>
<summary>Đáp án</summary>

Không. Instance method có thể bị override không đủ điều kiện gắn `@SafeVarargs`; trên Java 17 chỉ các instance varargs methods `final` hoặc `private` là hợp lệ, cùng với `static` methods và constructors có varargs.

</details>

## 16. Kết luận

**Cảnh báo ở khai báo** generic varargs cho biết signature nhận một array có component không reifiable, tạo khả năng heap pollution. **Cảnh báo ở lời gọi** cho biết compiler đang tạo/cung cấp một generic varargs array mà type arguments không thể kiểm tra đầy đủ ở runtime. Hai thông báo quan hệ với nhau nhưng nằm ở hai vị trí khác nhau của chương trình.

`@SafeVarargs` chỉ nên được dùng khi method hợp lệ về vị trí annotation **và** có cơ sở bảo đảm array varargs không bị ghi sai, không escape tới code không kiểm soát và không làm hỏng dữ liệu qua raw alias. Nếu không cần liên kết kiểu `T`, `List<?>...` có thể là một API reifiable phù hợp. Nếu cần giữ quan hệ generic mà không muốn dùng varargs array, cân nhắc truyền collection bên ngoài.

Với Java Generics, loại bỏ cảnh báo đúng cách nghĩa là **giữ hợp đồng kiểu và kiểm soát dữ liệu**, không chỉ làm compiler im lặng.