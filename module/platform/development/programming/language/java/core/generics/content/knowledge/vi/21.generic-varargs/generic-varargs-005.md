# Rủi ro làm lộ mảng varargs ra bên ngoài trong Java Generics

## Mục tiêu học tập

Varargs là tính năng giúp viết phương thức nhận nhiều đối số: `log("A", "B", "C")` thay vì tự dựng mảng ở vị trí gọi. Tuy nhiên, tham số khai báo `T... values` thực chất được xử lý như **mảng `T[]`** trong thân phương thức. Khi T là kiểu không *reifiable* (*non-reifiable*), như `List<String>`, mảng runtime không giữ đủ thông tin generic để kiểm tra toàn bộ hợp đồng `List<String>[]`.

Rủi ro nổi bật là **varargs array escape**: phương thức trả thẳng mảng nhận được, lưu vào field, trao nó cho callback không tin cậy, hoặc trả một view dùng chính mảng làm backing storage. Một nơi khác có thể giữ alias mảng và thay một slot bằng đối tượng hợp lệ theo runtime component type nhưng sai tham số generic. Việc này tạo *heap pollution* và có thể dẫn tới `ClassCastException` muộn.

Bài này giúp bạn:

- Mô tả chính xác varargs được truyền dưới dạng mảng và vì sao generics làm phát sinh cảnh báo.
- Hiểu sự khác nhau giữa `String...`, `List<?>...` và `List<String>...`.
- Theo dõi quá trình tạo alias `Object[]`, chèn `List<Integer>` vào `List<String>[]` và lỗi phát sinh khi đọc.
- Đánh giá một phương thức có làm lộ varargs array bằng đường trực tiếp hay gián tiếp.
- Biết tác dụng, điều kiện và giới hạn của `@SafeVarargs`.
- Sửa API bằng snapshot độc lập, giữ bất biến dữ liệu và sử dụng collection có hợp đồng rõ ràng.
- Chạy `javac -Xlint` và viết kiểm thử chống lỗi alias/generic.

## 1. Varargs thực chất là mảng

Ví dụ:

```java
static void show(String... words) {
    System.out.println(words.length);
}
```

Caller có thể viết:

```java
show("A", "B", "C");
show(new String[] {"A", "B", "C"});
```

Trong `show`, biến `words` có kiểu `String[]`. Nó có `length`, hỗ trợ truy cập theo chỉ số và nhận phép gán vào slot nếu code thực hiện. Dạng lời gọi đầu được compiler tổ chức thành mảng trong quá trình gọi varargs; dạng thứ hai có thể đưa chính mảng caller đã tạo vào phương thức theo lời gọi fixed-arity.

Hai dạng khai báo `String... words` và `String[] words` không thể đứng cạnh nhau làm overload chỉ khác dấu ba chấm: bên trong và sau khi biên dịch, tham số varargs được biểu diễn bằng mảng. Dấu `...` thay đổi khả năng gọi với số lượng đối số biến đổi, không tạo ra một container runtime mới.

Với generic:

```java
static <T> void consume(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Trong thân phương thức, `values` có kiểu nguồn `T[]`. Nếu T là biến kiểu không có bound, erasure của T là `Object`. Với kiểu generic sâu hơn như `List<String>`, mảng runtime không có component class riêng mang chính xác tham số String; đó là điểm giao nhau giữa varargs và type erasure.

## 2. Vì sao reifiability và ownership cùng quan trọng?

Trong JVM, mảng mang runtime component class. Với `String[]`, phép ghi Integer qua alias `Object[]` bị `ArrayStoreException`. Còn với generic varargs `List<String>...`, runtime component type của array là `List` và không thể xác nhận type argument String; một `List<Integer>` vẫn qua được array store check.

| Element type của varargs | Reifiable? | Điều cần nhớ |
| --- | --- | --- |
| `String` hoặc `int` | Có | Mảng có runtime component String/int tương ứng. |
| `List<?>` | Có | Chỉ bảo đảm mỗi slot là List, không cam kết kiểu phần tử bên trong. |
| `List<String>`, `List<? extends Number>` | Không | Tham số hóa cụ thể/bounded wildcard không được runtime kiểm tra sâu. |
| `T` trong `<T> void f(T... values)` | Không nói chung | Erasure(T) và cách caller tạo array quyết định runtime component thực. |

**Ngay cả mảng reifiable cũng mutable**: method có thể được truyền chính mảng caller đã tạo. Bài này phân tích điều xảy ra khi method **trả mảng, lưu field hoặc công bố view backed by array**, khiến người khác giữ alias và có thể sửa các slot sau khi method kết thúc. Đây là vấn đề **quyền sở hữu và lifetime của array**, không chỉ là khả năng compiler tạo cảnh báo unchecked.

## 3. Thế nào là làm lộ mảng varargs?

Một phương thức đã **làm lộ** (*escaped*) varargs array nếu một nơi khác có thể giữ lại và sử dụng chính tham chiếu mảng sau khi phương thức kết thúc hoặc trong ngữ cảnh mà phương thức không còn kiểm soát.

Các ví dụ minh họa:

```java
// Nguy hiểm nếu T có kiểu non-reifiable và caller nhận T[]:
static <T> T[] returnArray(T... items) {
    return items;
}

// Cũng làm lộ nếu lưu chính tham chiếu mảng vào field:
// this.cachedItems = items;

// Hoặc giao chính mảng cho callback có thể giữ/chỉnh sửa:
// callback.accept(items);

// Arrays.asList trả view backed by mảng đầu vào:
// return Arrays.asList(items);
```

Các khai báo/đoạn chú thích này dùng để phân tích thiết kế, không phải một chương trình Java độc lập.

Đường escape không chỉ là `return items`. Một **view được chống lưng bởi mảng** cũng có thể tạo alias gián tiếp. Nếu trả `Arrays.asList(items)`, người nhận list có thể sử dụng `set` để sửa phần tử mảng gốc; ngược lại, sửa mảng phản ánh trong list view.

Ngược lại, một phương thức chỉ duyệt các giá trị để tính tổng, kiểm tra điều kiện hoặc copy phần tử sang collection mới thường không cần làm lộ array.

Hai khía cạnh phải đánh giá riêng:

1. **Type safety:** array component runtime có phản ánh đầy đủ loại phần tử generic hay không?
2. **Ownership/mutability:** caller và callee có cùng giữ hoặc sửa một đối tượng array không?

Ngay cả `String...` reifiable vẫn có nguy cơ chia sẻ và sửa mảng đầu vào nếu callee cố giữ hoặc ghi mảng của caller. Nhưng riêng non-reifiable varargs còn có rủi ro **heap pollution** do generic lồng sâu không được kiểm tra ở runtime.

## 4. Cơ chế tạo heap pollution khi mảng bị lộ

Xét phương thức:

```java
// Cần import java.util.List.
static <E> List<E>[] expose(List<E>... groups) {
    return groups;
}
```

Ở mã nguồn, chữ ký trả về `List<E>[]`. Khi caller truyền các đối số `List<String>` dưới dạng varargs, compiler có thể tạo mảng với component type runtime là `List` vì `List<String>` không reifiable.

Sau đó:

```java
List<String>[] escaped = expose(List.of("A"), List.of("B"));
Object[] alias = escaped;
alias[0] = List.of(42);           // Ghi thành công vào mảng List[].
String first = escaped[0].get(0); // ClassCastException lúc đọc.
```

Đây là đoạn trình bày tình huống lỗi; chương trình hoàn chỉnh ở phần 6 sẽ bắt ngoại lệ để hiển thị kết quả.

Phân tích chính xác:

1. `expose` nhận một mảng varargs mới hoặc mảng caller cung cấp; ở lời gọi này compiler tạo mảng có component runtime là List.
2. `return groups` trả chính tham chiếu mảng, không clone và không đổi cấu trúc.
3. Biến `escaped` được khai báo `List<String>[]`; lập trình viên đang tin từng slot trỏ tới một List String.
4. `Object[] alias = escaped` hợp lệ vì mảng tham chiếu của Java có tính hiệp biến (*covariance*).
5. `alias[0] = List.of(42)` ghi một List<Integer> vào mảng runtime List[]. Array store check **không ném lỗi** vì đối tượng được thêm thực sự là một List.
6. `escaped[0].get(0)` đưa ra Integer; code nguồn yêu cầu String. Compiler chèn phép `checkcast String` ở nơi sử dụng kết quả và JVM ném `ClassCastException`.

Kết luận: việc JVM kiểm tra thành phần mảng là List **không đồng nghĩa** kiểm tra được List chứa toàn String. Vì vậy lỗi không nhất thiết xảy ra tại thời điểm alias ghi giá trị không hợp lệ.

### Sơ đồ đường đi

```text
expose(List<String>, List<String>)
    |
    v
mảng runtime List[] (varargs)
    |
    | return groups; -- ESCAPE
    v
List<String>[] escaped
    |
    | Object[] alias = escaped;
    | alias[0] = List.of(42);
    v
mảng List[] vẫn chấp nhận List<Integer>
    |
    | String s = escaped[0].get(0);
    v
List.get() trả Object(Integer)
    |
    | compiler chèn checkcast String
    v
ClassCastException tại caller
```

Đây là một hình thức *heap pollution*: giá trị thực ở slot không còn thỏa hợp đồng `List<String>` mà biến được khai báo. Nơi thay đổi sai dữ liệu và nơi ngoại lệ phát sinh có thể thuộc các module khác nhau.

## 5. Cảnh báo compiler có ý nghĩa gì?

Với phương thức `expose`, chạy:

```bash
javac --release 17 -Xlint:all VarargsEscapeDemo.java
```

Compiler có thể đưa cảnh báo tại **khai báo** và **lời gọi**:

```text
[unchecked] Possible heap pollution from parameterized vararg type List<E>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Hai cảnh báo này đã được kiểm chứng bằng `javac --release 17 -Xlint:all` trong chương trình ở phần 6.

- Cảnh báo thứ nhất: tham số varargs là kiểu non-reifiable; method có khả năng sử dụng mảng theo cách không an toàn.
- Cảnh báo thứ hai: tại điểm gọi varargs, compiler tạo mảng của kiểu đã xóa nên không xác minh đầy đủ phần generic.

**Warning không đồng nghĩa method chắc chắn gây lỗi**; một method chỉ duyệt phần tử và không làm lộ mảng có thể được thiết kế an toàn dù có chữ ký non-reifiable. Nhưng warning là tín hiệu cần review, không phải thứ nên triệt tiêu theo phản xạ.

`@SuppressWarnings("unchecked")` chỉ che các cảnh báo trong phạm vi áp dụng; nó không sửa runtime component type, không tạo copy và không bảo vệ alias. `@SafeVarargs` còn có tác động tới cảnh báo ở call site, nên đòi hỏi trách nhiệm lớn hơn từ tác giả thư viện.

## 6. Ví dụ Java 17 hoàn chỉnh có thể chạy

**Tệp `VarargsEscapeDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class VarargsEscapeDemo {
    static <E> List<E>[] expose(List<E>... groups) {
        return groups;
    }

    @SafeVarargs
    static <T> List<T> snapshot(T... values) {
        List<T> copy = new ArrayList<>(values.length);
        for (T value : values) copy.add(value);
        return List.copyOf(copy);
    }

    @SafeVarargs
    static <T> List<List<T>> snapshotGroups(List<? extends T>... groups) {
        List<List<T>> copy = new ArrayList<>();
        for (List<? extends T> group : groups) {
            copy.add(List.copyOf(group));
        }
        return List.copyOf(copy);
    }

    static void observe(List<?>... groups) {
        for (List<?> group : groups) {
            System.out.println("observed-size=" + group.size());
        }
    }

    public static void main(String[] args) {
        List<String>[] escaped = expose(List.of("A"), List.of("B"));
        System.out.println("runtime-component="
                + escaped.getClass().getComponentType().getSimpleName());

        Object[] alias = escaped;
        alias[0] = List.of(42);
        System.out.println("array-store-accepted=" + escaped.length);

        try {
            String result = escaped[0].get(0);
            System.out.println(result);
        } catch (ClassCastException error) {
            System.out.println("late-failure=" + error.getClass().getSimpleName());
        }

        List<String> flat = snapshot("x", "y");
        System.out.println("flat=" + flat);
        try {
            flat.add("z");
        } catch (UnsupportedOperationException error) {
            System.out.println("flat-is-fixed="
                    + error.getClass().getSimpleName());
        }

        List<List<String>> groups = snapshotGroups(
                List.of("one"), List.of("two"));
        System.out.println("groups=" + groups);
        try {
            groups.get(0).set(0, "changed");
        } catch (UnsupportedOperationException error) {
            System.out.println("inner-is-fixed="
                    + error.getClass().getSimpleName());
        }

        observe(List.of("a"), List.of(3));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all VarargsEscapeDemo.java
java VarargsEscapeDemo
```

**Stdout đã kiểm chứng:**

```text
runtime-component=List
array-store-accepted=2
late-failure=ClassCastException
flat=[x, y]
flat-is-fixed=UnsupportedOperationException
groups=[[one], [two]]
inner-is-fixed=UnsupportedOperationException
observed-size=1
observed-size=1
```

Chương trình cố ý có **hai cảnh báo unchecked** tại `expose` và lời gọi tương ứng. Cảnh báo xuất hiện ở bước `javac`, không nằm trong stdout của `java`.

### 6.1. Mảng đã lộ có component runtime là List

Dòng `runtime-component=List` đến từ `getClass().getComponentType().getSimpleName()`. Mặc dù kiểu tĩnh là `List<String>[]`, mảng thực chứa các đối tượng List mà không có kiểm tra String ở cấp component runtime.

### 6.2. Ghi sai không tạo ArrayStoreException

`Object[] alias` và `escaped` là hai tham chiếu tới **cùng đối tượng mảng**. Ghi `List.of(42)` phù hợp với component runtime List. Vì thế chương trình tiếp tục tới dòng `array-store-accepted=2`; đây không phải bằng chứng dữ liệu generic vẫn đúng.

### 6.3. Lỗi xuất hiện muộn khi đọc

`escaped[0].get(0)` lấy phần tử Integer, nhưng caller đang yêu cầu String. Khi JVM thực thi cast do compiler chèn, ngoại lệ `ClassCastException` được bắt và in. Lúc này code gây heap pollution đã chạy xong.

### 6.4. Hai snapshot không trả mảng varargs

`snapshot` duyệt các phần tử và copy vào List mới. `snapshotGroups` duyệt mảng các nhóm rồi copy từng nhóm thành List mới trước khi trả một List ngoài mới. Không có tham chiếu varargs array trong giá trị trả về, nên caller không thể lấy lại mảng đó qua API này.

`List.copyOf` trả collection không sửa được; đó là lý do chương trình bắt `UnsupportedOperationException` ở hai nơi. Đây là **tính không sửa được về cấu trúc**, không phải deep-copy tự động các object phần tử T.

### 6.5. Khi chỉ cần quan sát, đừng hứa hơn mức cần thiết

`observe(List<?>... groups)` chỉ dùng `size()` trên các nhóm. Nó không đòi hỏi mọi nhóm chứa cùng kiểu tham số cụ thể; `List<?>` phù hợp với nhu cầu này và là reifiable type. Hàm không trả hoặc lưu array.

## 7. Dùng `@SafeVarargs` khi nào?

`@SafeVarargs` là một **cam kết của lập trình viên**: thân phương thức hoặc constructor xử lý varargs của kiểu không reifiable mà không tạo tình huống không an toàn liên quan mảng đó. Annotation cho phép compiler bỏ một số cảnh báo unchecked ở khai báo và call site varargs.

Nó **không**:

- Biến `List<String>` thành reifiable.
- Biến runtime `List[]` thành một mảng có component `List<String>`.
- Tự copy hoặc đóng băng tham số varargs.
- Chặn code khác giữ alias đã bị làm lộ.
- Bảo đảm compiler chứng minh đầy đủ an toàn của thân method.

Không được gắn annotation để che cảnh báo ở mẫu sau:

```java
// MẪU KHÔNG AN TOÀN - không thêm @SafeVarargs:
static <E> List<E>[] expose(List<E>... groups) {
    return groups;
}
```

Ở đây rủi ro phát sinh trực tiếp vì trả mảng ra ngoài. Nếu gắn `@SafeVarargs`, cảnh báo của caller có thể mất nhưng dữ liệu vẫn có thể bị làm sai.

### Điều kiện dùng annotation trong Java 17

`@SafeVarargs` hợp lệ trên constructor hoặc các **phương thức varargs** là `static`, `final` hoặc `private`. Không được gắn tùy ý lên một instance method có thể override. Ví dụ cố ý không biên dịch:

```java
class InvalidSafeVarargs {
    @SafeVarargs
    void instanceMethod(String... values) {}
}
```

Khi kiểm tra bằng `javac --release 17`, compiler từ chối vì method không static/final/private. Ngoài ra, `@SafeVarargs` là thừa khi phần tử varargs đã reifiable, như `String...`, vì không có cảnh báo tương ứng cần suppress.

**Đặc tả Java không coi annotation là chứng minh hình thức.** Compiler có thể cảnh báo với những body trông nguy hiểm, nhưng không bảo đảm phát hiện mọi đường alias. Vì vậy tác giả phải review toàn bộ thân method trước khi annotate.

### Mẫu có thể dùng annotation

```java
@SafeVarargs
static <T> List<T> snapshot(T... values) {
    List<T> copy = new ArrayList<>(values.length);
    for (T value : values) {
        copy.add(value);
    }
    return List.copyOf(copy);
}
```

Đoạn này nằm trong class với import `List` và `ArrayList`. Nó chỉ đọc mảng, sao chép phần tử vào List, rồi trả một cấu trúc mới; không sửa slot varargs, không trả/lưu mảng và không trao tham chiếu mảng cho bên ngoài.

Không nên kết luận từ `@SafeVarargs` rằng mọi dữ liệu về sau an toàn tuyệt đối: phần tử có thể mutable, null có thể không được chấp nhận bởi `List.copyOf` và caller vẫn có thể đã cố tình dùng raw type trước đó. Annotation chỉ nói về cách phương thức xử lý varargs theo hợp đồng.

## 8. View được chống lưng bởi mảng cũng có thể làm lộ alias

Một ví dụ thường gặp:

```java
static <T> List<T> backedView(T... values) {
    return java.util.Arrays.asList(values);
}
```

Đây là mẫu phân tích, không nên tự thêm `@SafeVarargs` khi chưa xem xét đường alias. `Arrays.asList(values)` tạo một List **có kích thước cố định** nhưng backed by mảng `values`. Nó không cho thêm/xóa thay đổi kích thước như ArrayList, nhưng `set` thay slot mảng.

Kiểm tra trên mảng reifiable:

```java
String[] original = {"A", "B"};
List<String> view = java.util.Arrays.asList(original);
view.set(0, "C");
System.out.println(original[0]); // C
```

`original` và `view` cùng truy cập một backing array. Trường hợp này chưa phải heap pollution vì phần tử là String, nhưng cho thấy **lộ alias qua view**. Với mảng varargs của một kiểu non-reifiable, trao view cho bên ngoài có thể làm đường thay đổi khó kiểm soát hơn.

Có thể tạo snapshot cấu trúc bằng cách copy:

```java
List<String> copy =
        List.copyOf(java.util.Arrays.asList(original));
```

`copy` là một List không sửa được độc lập về cấu trúc. Tuy vậy, khi xây dựng một generic varargs method được annotate, việc truyền trực tiếp mảng varargs vào API trung gian như `Arrays.asList(values)` có thể khiến `javac -Xlint:varargs` cảnh báo về khả năng rò rỉ tham chiếu, mặc dù đoạn copy cuối cùng có thể an toàn. Dùng vòng lặp như `snapshot` ở trên có đường dữ liệu trực quan hơn.

## 9. Clone mảng có giải quyết hoàn toàn không?

`values.clone()` trả về một mảng khác với mảng đầu vào, giúp tách **tham chiếu mảng** ở ranh giới. Nhưng điều đó không đồng nghĩa một `List<String>[]` được kiểm tra sâu kiểu String tại runtime.

Giả sử một helper trả về bản clone của mảng có component runtime List; caller có thể tiếp tục viết:

```java
List<String>[] result = /* mảng được trả về, kiểu tĩnh List<String>[] */;
Object[] wider = result;
wider[0] = List.of(99); // Runtime List[] vẫn chấp nhận List<Integer>.
```

Đoạn trên là sơ đồ giả định, không phải chương trình độc lập (biến result cần được tạo bởi một nguồn thích hợp). Mảng clone độc lập vẫn là List[] ở runtime và không có class token `List<String>`. Một alias `Object[]` mới của chính bản clone vẫn có thể gây heap pollution.

Ngoài ra, clone mảng chỉ sao chép **các tham chiếu phần tử**. Nếu phần tử là đối tượng mutable, cả mảng ban đầu và mảng clone còn tham chiếu tới cùng phần tử; việc thay đổi đối tượng đó vẫn hiển thị từ cả hai phía.

Từ đó có ba mức độ phòng vệ:

1. **Không trả mảng input:** giảm rò rỉ alias tới mảng ban đầu.
2. **Không trả mảng non-reifiable nếu không cần:** tránh việc caller có một `List<String>[]` dễ bị alias qua Object[].
3. **Copy dữ liệu và định nghĩa mutability rõ ràng:** với nested lists, copy từng tầng cần bảo vệ; nếu phải bảo đảm bất biến của object phần tử, cần thêm chiến lược deep copy phù hợp nghiệp vụ.

Trong nhiều API, trả `List<List<T>>` độc lập rõ nghĩa hơn trả `List<T>[]`.

## 10. Mảng của caller có thể được truyền thẳng qua varargs

Đừng mặc định compiler luôn tạo mảng mới. Với lời gọi có sẵn một mảng đúng kiểu, varargs method có thể nhận chính mảng đó:

```java
static void edit(String... words) {
    words[0] = "CHANGED";
}

// Trong main:
String[] input = {"A", "B"};
edit(input);
System.out.println(input[0]); // CHANGED
```

Ví dụ này độc lập với vấn đề generic không reifiable, nhưng cho thấy một **rủi ro ownership**: callee sửa mảng input của caller.

Ngược lại, `edit("A", "B")` khiến compiler tổ chức mảng tại vị trí gọi; caller không trực tiếp giữ tham chiếu mảng tạm được tạo theo cách gọi ấy, trừ khi method làm lộ nó.

Nếu contract của bạn muốn **không sửa dữ liệu caller**, đừng ghi các slot varargs. Nếu phải lưu giữ để xử lý bất đồng bộ hoặc sau khi method kết thúc, nên copy với chính sách null/mutability rõ ràng thay vì giữ `values`.

## 11. Làm gì khi cần nhiều nhóm List?

Nếu nghiệp vụ chỉ tính tổng số phần tử:

```java
static int count(List<?>... groups) {
    int result = 0;
    for (List<?> group : groups) {
        result += group.size();
    }
    return result;
}
```

`List<?>` giúp hàm chấp nhận cả `List<String>` và `List<Integer>` mà không hứa các nhóm chứa cùng kiểu T. Phương thức chỉ đọc và trả `int`, không có lý do nào để trả một mảng.

Nếu nghiệp vụ cần giữ dữ liệu lâu hơn:

```java
@SafeVarargs
static <T> List<List<T>> snapshotGroups(List<? extends T>... groups) {
    List<List<T>> copy = new ArrayList<>();
    for (List<? extends T> group : groups) {
        copy.add(List.copyOf(group));
    }
    return List.copyOf(copy);
}
```

Ở đây phương thức tạo các nhóm mới bằng `List.copyOf(group)` và tạo cả List ngoài mới. Không có mảng varargs nào được công bố. Đổi lại, API cần quy định rằng `null` không được chấp nhận bởi `List.copyOf`; các object T mutable không được deep-copy.

### Khi nào chọn `Collection` thay vì varargs?

Nếu caller vốn có collection, một chữ ký nhận `Collection<? extends T>` hoặc `List<? extends T>` thường đủ tốt và tránh tạo thêm varargs array. Varargs phù hợp khi mục tiêu chính là cách gọi ngắn với vài đối số; nó không phải bắt buộc cho mọi API chứa nhiều phần tử.

Cần dùng mảng thực có component runtime như `String[]`? Hãy xem giải pháp nhận `IntFunction<T[]>` (ví dụ `String[]::new`) hoặc `Class<T>`. Đừng ép `Object[]` thành `T[]` mà không có bảo đảm runtime tương ứng.

## 12. Các lỗi phổ biến trong code review

| Nhận định hoặc cách làm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “Tham số `T...` không phải mảng.” | Trong thân method, đó là `T[]`. | Tìm mọi alias/đường gán/lần truyền mảng. |
| “Mảng `List<String>[]` chặn mọi List Integer.” | Runtime component là List; không reify String. | Không lộ array; copy sang cấu trúc typed hợp lý. |
| “Không có `ArrayStoreException` thì không sai.” | Ghi List<Integer> vào List[] được chấp nhận. | Kiểm tra hợp đồng generic và điểm cast muộn. |
| “Thêm `@SafeVarargs` sẽ làm phương thức an toàn.” | Annotation không kiểm tra body hay sao chép. | Chỉ dùng sau khi chứng minh cách xử lý mảng an toàn. |
| “`return items.clone()` luôn giải quyết mọi rủi ro.” | Clone vẫn giữ kiểu mảng non-reifiable và chia sẻ object phần tử. | Đánh giá loại API trả về và copy tầng cần thiết. |
| “`Arrays.asList(items)` tạo List tách biệt.” | List view backed by mảng. | Dùng copy nếu mục tiêu là snapshot. |
| “Dập mọi unchecked warning ở caller là được.” | Làm mất tín hiệu rủi ro, không sửa heap pollution. | Review khai báo, điểm gọi và đường alias. |
| “`List<?>...` hứa mọi nhóm cùng kiểu.” | Wildcard không giới hạn không cam kết loại phần tử cụ thể. | Chọn chữ ký phù hợp đúng mục đích chỉ đọc. |
| “Trả snapshot là deep copy.” | `List.copyOf` chỉ copy cấu trúc, giữ object T. | Nếu cần deep copy, thiết kế riêng theo domain. |
| “Mọi varargs luôn tạo mảng mới.” | Caller có thể truyền mảng sẵn có. | Không ghi vào mảng nếu contract không cho phép. |

## 13. Quy trình kiểm tra và tái hiện lỗi

Khi một `ClassCastException` xuất hiện trong code đọc một `List<String>` từ một mảng hay collection do API varargs tạo, làm theo các bước:

1. **Giữ stack trace đầy đủ** để xác định vị trí `checkcast` thất bại và kiểu thực tế.
2. **Tìm gốc dữ liệu**: phương thức nhận `T...` hoặc `List<T>...` nào đã tạo/trả/lưu mảng?
3. **Kiểm tra chữ ký nguồn**: element type có non-reifiable không, có raw hoặc unchecked cast không?
4. **Tìm đường escape**: `return varargs`, gán field, cache, callback hoặc `Arrays.asList` view.
5. **Tìm alias kiểu rộng**: `Object[]`, raw `List[]`, `Collection[]` hoặc một supertype array.
6. **Tìm lệnh thay slot**: `alias[index] = ...` có thể đã đưa một container đúng kiểu runtime nhưng sai tham số generic.
7. **Bật lint**: `javac --release 17 -Xlint:unchecked,varargs ...`. Đừng che warning trước khi hiểu nó.
8. **Tái hiện có kiểm soát**: xây dựng test bằng các List String, đưa một List Integer qua alias rồi đọc; xác nhận trường hợp cũ thất bại và bản sửa không để lộ mảng.
9. **Refactor điểm sở hữu dữ liệu**: cho callee xử lý tại chỗ hoặc trả snapshot, không trả mảng non-reifiable trừ khi thực sự có lý do thiết kế mạnh.
10. **Đánh giá hợp đồng sau sửa**: null, phần tử mutable, performance copy, thread-safety, phụ thuộc legacy.

Bất kể compiler có hay không có cảnh báo trong một bản build cụ thể, việc một API công khai trao tham chiếu array mutable ra ngoài luôn đáng được xem xét về quyền sở hữu dữ liệu.

### Vì sao lỗi có thể bị trì hoãn?

Sau khi một phần tử mảng `List<String>[]` bị thay bằng `List<Integer>`, code gọi `array.length`, `array[0].size()` hoặc truyền mảng qua nhiều tầng có thể hoạt động bình thường. Lỗi chỉ phát sinh khi chương trình đòi hỏi một phần tử String từ List đang chứa Integer. Vì thế sửa dòng `get(0)` bằng ép kiểu khác thường chỉ che triệu chứng, không sửa nguồn heap pollution.

## 14. Bài tập thực hành

**Bài 1.** Mã dưới đây có an toàn không?

```java
static <T> T[] save(T... values) {
    return values;
}
```

**Đáp án:** Không thể coi là một thiết kế an toàn tổng quát. Nó làm lộ chính array. Nếu T là non-reifiable (đặc biệt khi T là một kiểu generic tham số hóa), caller có thể gặp heap pollution/aliasing. Ngay cả khi T là reifiable, nó vẫn có rủi ro chia sẻ mảng mutable. Không nên gắn `@SafeVarargs` chỉ để che warning.

**Bài 2.** Với `List<String>[]` mà runtime component là List, tại sao `Object[] alias` có thể ghi một `List<Integer>`?

**Đáp án:** Array covariance cho phép alias. Array store check chỉ biết component là List; `List<Integer>` là List ở runtime. JVM không kiểm tra tham số String trong slot.

**Bài 3.** Tại sao lỗi có thể xuất hiện ở `String value = escaped[0].get(0)`?

**Đáp án:** `List.get` sau erasure trả Object. Caller muốn String nên compiler chèn `checkcast String`; nếu phần tử thực là Integer, JVM ném `ClassCastException`.

**Bài 4.** `@SafeVarargs` có nên áp dụng cho một phương thức trả thẳng `List<E>[]` từ `List<E>...` không?

**Đáp án:** Không, vì làm lộ mảng cho caller giữ alias và thay slot. Annotation không thay đổi cơ chế runtime.

**Bài 5.** Một `String[]` truyền vào `void update(String... values)` có bị thay đổi nếu callee ghi `values[0]` không?

**Đáp án:** Có thể. Caller truyền chính mảng đã có, nên hai biến cùng trỏ tới một array. Cần contract quy định quyền sửa.

**Bài 6.** `Arrays.asList(varargs)` có tách khỏi backing array không?

**Đáp án:** Không. Đây là view kích thước cố định, nơi `set` có thể sửa mảng. Nếu cần snapshot độc lập, phải copy.

**Bài 7.** `List.copyOf` có làm một đối tượng T mutable trong list trở nên immutable không?

**Đáp án:** Không. Nó bảo vệ cấu trúc List không sửa được và tạo bản sao collection; bản thân object phần tử vẫn có thể mutable.

**Bài 8.** Nếu chỉ đếm phần tử các nhóm `List<String>` và `List<Integer>`, nên nhận `List<String>...` hay `List<?>...`?

**Đáp án:** `List<?>...` diễn đạt đúng nhu cầu không phụ thuộc kiểu phần tử; chỉ đọc `size` và không trả mảng.

**Bài 9.** Vì sao một method dùng `List<E>...` có warning dù body chỉ đọc?

**Đáp án:** Phần tử varargs không reifiable; compiler cảnh báo theo khả năng heap pollution ở ranh giới mảng. Nếu method thực sự chỉ đọc, không đổi slot, không chuyển mảng tới nơi có thể giữ alias và không làm lộ array, tác giả có thể cân nhắc `@SafeVarargs` khi đủ điều kiện.

**Bài 10.** Có nên trả `List<T>[]` được clone từ varargs để tránh mọi rủi ro không?

**Đáp án:** Clone tách khỏi mảng gốc, nhưng caller vẫn giữ một mảng non-reifiable có runtime component rộng, có thể tạo alias mới và thay slot. Nếu cần giao kết quả dưới dạng nhiều nhóm, `List<List<T>>` thường phù hợp hơn.

## 15. Tổng kết và tài liệu

Mấu chốt là sự kết hợp giữa ba cơ chế: **varargs được hiện thực bằng mảng**, **mảng có tính hiệp biến và mutable**, còn **đối số kiểu generic không reifiable không được JVM kiểm tra sâu**. Khi một mảng `List<String>[]` bị trả hoặc trao ra ngoài, code khác có thể thay một slot bằng `List<Integer>` thông qua `Object[]` mà array store check không cản được. Vi phạm có thể chỉ bộc lộ ở nơi đọc String, dưới dạng `ClassCastException`.

Cách thiết kế đáng tin hơn là giữ mảng varargs trong phạm vi cục bộ, chỉ đọc hoặc chuyển các phần tử sang cấu trúc mới rồi trả kết quả có hợp đồng rõ ràng. `@SafeVarargs` là lời cam kết của tác giả sau khi đã kiểm tra body, không phải phép biến đổi tự động khiến code sai trở nên an toàn.

Đọc thêm các tài liệu Java chính thức:

- [JLS Java SE 17: phần SafeVarargs và heap pollution](https://docs.oracle.com/javase/specs/jls/se17/jls17.pdf)
- [Oracle Java Tutorials: Non-Reifiable Types và generic varargs](https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html)
- [Java API: SafeVarargs annotation](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/SafeVarargs.html)

**Quy tắc thực hành:** Đừng coi tham chiếu mảng varargs là một giá trị vô hại để trả hoặc lưu. Hãy xác định ai có quyền sửa mảng, liệu kiểu phần tử có reifiable không và dữ liệu sẽ được sử dụng ra sao sau khi phương thức kết thúc.
