# Rủi ro ghi qua tham chiếu mảng kiểu cha trong Generic Varargs Java

## 1. Vấn đề cần nhận diện

Một phương thức nhận varargs có thể được gọi bằng nhiều đối số như:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

Đây là đoạn phương thức minh họa; cần đặt bên trong class để chạy. Về cơ chế, `String...` là tham số có kiểu mảng `String[]`, và lời gọi `print("A", "B")` có thể được compiler biên dịch bằng cách tạo một mảng chứa hai chuỗi.

Sự nguy hiểm rõ hơn khi kiểu phần tử của varargs là một **kiểu generic không reifiable**, ví dụ:

```java
static void process(java.util.List<String>... lists) {
    // ...
}
```

Bên trong phương thức, `lists` được nhìn như `List<String>[]`, nhưng runtime **không có** component class riêng cho `List<String>`. Mảng dùng để truyền tham số có component type runtime tương ứng với raw `List`.

Nếu code cho một tham chiếu kiểu cha, chẳng hạn `Object[]`, trỏ tới chính mảng đó rồi **ghi** vào mảng:

```java
Object[] alias = lists;
alias[0] = java.util.List.of(123);
```

Java có thể chấp nhận phép ghi vì object `List<Integer>` vẫn là một `List` khi kiểm tra component type runtime. Tuy nhiên, một chỗ khác đang đọc `lists[0]` như `List<String>` có thể ném `ClassCastException` khi lấy `Integer` ra làm `String`.

**Kết luận cốt lõi:**

> Với generic varargs, việc gán mảng cho tham chiếu cha như `Object[]` có thể mở đường **ghi phần tử không đúng đối số kiểu generic** vào chính mảng varargs. Runtime array store check chỉ biết raw component type, còn compiler đã giả định các phần tử tuân theo hợp đồng generic. Hiện tượng lệch giữa hợp đồng và dữ liệu thực là *heap pollution*.

Không phải mọi phép gán sang `Object[]` đều nguy hiểm. Rủi ro cụ thể xuất hiện khi có thao tác ghi không an toàn hoặc làm lộ alias cho mã có thể ghi như vậy.

## 2. Ba cơ chế làm phép ghi qua tham chiếu cha trở nên nguy hiểm

| Cơ chế | Quy tắc quan trọng | Hệ quả trong bài |
| --- | --- | --- |
| **Varargs dùng mảng** | `List<String>...` có kiểu tham số source `List<String>[]`. | Mảng có các slot có thể được thay bằng phép gán chỉ số. |
| **Array covariance** | Một mảng tham chiếu như `List[]` có thể được nhìn qua `Object[]`. | Alias rộng cho phép viết code `alias[0] = newValue`. |
| **Generic erasure** | Component type runtime là `List`, không phải specialization `List<String>`. | JVM không tự kiểm tra type argument String khi thay slot. |

Sự kết hợp cả ba mới là trọng tâm: `Object[]` không tạo bản sao, nên ghi vào alias thay **chính slot của mảng varargs**. Nếu ghi một `String` vào runtime `List[]` thì JVM vẫn có thể ném `ArrayStoreException`; nhưng một `List<Integer>` là List hợp lệ ở cấp runtime nên có thể lọt qua. Lỗi chỉ xuất hiện khi caller dùng list đó dưới hợp đồng `List<String>`, thường tại phép đọc cần String.

Đặc biệt, `new List<String>[2]` bị cấm vì component không reifiable, còn `List<String>...` được phép khai báo với cảnh báo unchecked tương ứng. Bài này tập trung vào **đường ghi qua alias**, không coi mọi alias hay mọi varargs tự động gây heap pollution.

## 3. Một ví dụ chuẩn: array covariance với `String[]`

Trước khi xem generic varargs, hãy chạy một ví dụ mảng bình thường để biết khi nào JVM chặn được thao tác ghi sai.

Tệp **`CovariantArrayDemo.java`**:

```java
public class CovariantArrayDemo {
    public static void main(String[] args) {
        String[] strings = {"Java", "Generics"};
        Object[] alias = strings;

        System.out.println(strings.getClass()
                .getComponentType().getName());

        try {
            alias[0] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }

        System.out.println(strings[0]);
        System.out.println(alias == strings);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CovariantArrayDemo.java
java CovariantArrayDemo
```

Stdout:

```text
java.lang.String
ArrayStoreException
Java
true
```

Lý do:

1. Object mảng có component type runtime là `String`.
2. `Object[] alias = strings` tạo **tham chiếu khác đến cùng object**, không sao chép mảng.
3. `alias[0] = Integer.valueOf(42)` thỏa kiểu tĩnh của `Object[]`, nhưng không thỏa runtime component type của `String[]`.
4. JVM ném `ArrayStoreException` ngay khi ghi; mảng vẫn chứa `"Java"` ở vị trí 0.
5. `alias == strings` là `true`, nhấn mạnh đây là alias chứ không phải copy.

Cơ chế `ArrayStoreException` cho thấy Java arrays có runtime store check. Tuy nhiên, kiểm tra này chỉ mạnh đến mức **kiểu thành phần runtime có thể biểu diễn**.

## 4. Khác biệt khi phần tử mảng là danh sách generic

Giả sử mảng có component type runtime là `java.util.List`. Khi gán vào một phần tử của mảng:

- Một `String` **không** phải `List`, nên JVM có thể từ chối.
- Một `List<String>` là `List`, nên được chấp nhận.
- Một `List<Integer>` cũng là `List`, nên **vẫn được chấp nhận**.
- Runtime không kiểm tra `String` hay `Integer` ở bên trong từng `List`.

Bảng đối chiếu:

| Object mảng thực tế | Object được ghi qua `Object[]` | Runtime array store check | Hợp đồng generic có thể bị phá? |
|---|---|---|---|
| `String[]` | `Integer` | Từ chối bằng `ArrayStoreException` | Không liên quan generic |
| `List[]` | `String` | Từ chối bằng `ArrayStoreException` | Chưa có ghi thành công |
| `List[]` | `List<String>` | Chấp nhận | Phù hợp nếu slot kỳ vọng `List<String>` |
| `List[]` | `List<Integer>` | Chấp nhận | Có nếu slot được xem là `List<String>` |
| `Object[]` | `List<Integer>` | Chấp nhận | Tùy hợp đồng dữ liệu bên ngoài mảng |

Điểm quan trọng là **một mảng `List[]` không biết generic argument của object `List` được lưu**. Việc kiểu mảng runtime có thể chặn một object không phải `List` không đồng nghĩa nó xác minh được `List<String>`.

## 5. Chương trình chính: heap pollution qua `Object[]` alias

Tạo tệp **`UnsafeGenericVarargsDemo.java`**:

```java
import java.util.List;

public class UnsafeGenericVarargsDemo {

    static void corrupt(List<String>... groups) {
        System.out.println(groups.length);

        Object[] alias = groups;
        alias[0] = List.of(42);

        System.out.println(groups[0].size());

        String word = groups[0].get(0);
        System.out.println(word);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UnsafeGenericVarargsDemo.java
java UnsafeGenericVarargsDemo
```

Stdout của **chương trình**:

```text
1
1
ClassCastException
```

`javac` có thể in ghi chú/cảnh báo về thao tác generic varargs không an toàn trong quá trình biên dịch. **Thông báo biên dịch không thuộc stdout của chương trình**. Muốn xem rõ cảnh báo, dùng:

```bash
javac -Xlint:unchecked -Xlint:varargs UnsafeGenericVarargsDemo.java
```

### Diễn giải theo từng dòng

1. `corrupt(List.of("safe"))` truyền một danh sách chuỗi. Method khai báo `List<String>... groups`.
2. Varargs được truyền bằng một mảng. Với generic argument `<String>`, runtime array component chỉ là `List`.
3. `Object[] alias = groups` hợp lệ bởi mảng có tính covariance.
4. `alias[0] = List.of(42)` đặt một `List<Integer>` vào mảng; runtime component `List` vẫn chấp nhận nên **không** ném `ArrayStoreException`.
5. `groups[0].size()` hoạt động: số phần tử là 1, và `size()` không phải lấy `Integer` làm `String`.
6. `String word = groups[0].get(0)` là nơi compiler kỳ vọng kết quả có kiểu `String`. Giá trị thực tế là `Integer`, dẫn tới `ClassCastException`.
7. Khối `catch` in tên exception.

Đây là **heap pollution**: một tham chiếu được xem là mang kiểu tham số hóa (`List<String>[]`) trỏ đến trạng thái thực chứa danh sách không đáp ứng hợp đồng ấy.

Ví dụ này **cố ý không an toàn để học tập**. Không sử dụng thân method `corrupt` trong code sản xuất, và không đặt `@SafeVarargs` lên nó.

## 6. Vì sao câu lệnh `alias[0] = List.of(42)` hợp lệ ở mã nguồn?

Hãy phân biệt ba kiểu tĩnh:

```java
List<String>[] groups; // Một mảng được nhìn với generic component type.
Object[] alias;         // Một tham chiếu mảng kiểu cha.
List<Integer> wrong;    // Một danh sách có phần tử Integer.
```

Đây là các đoạn khai báo minh họa; `groups` và `alias` phải được khởi tạo đúng trước khi dùng trong một method hoàn chỉnh.

Ở mã nguồn, `groups[0]` có kiểu `List<String>`; compiler sẽ từ chối gán trực tiếp một `List<Integer>`:

```java
// Cố ý không hợp lệ nếu đặt trong method và khởi tạo các biến:
groups[0] = List.of(42);
```

Nhưng nếu code tạo alias:

```java
Object[] alias = groups;
alias[0] = List.of(42);
```

thì kiểu tĩnh của phần tử `alias[0]` là `Object`. `List<Integer>` là một object, nên compiler **không có căn cứ từ kiểu `Object[]` để từ chối**. Phép ghi chuyển sang cơ chế runtime array store check.

Vấn đề là runtime chỉ biết mảng có component class raw `List`, nên cho phép `List<Integer>` đi qua. Thông tin `<String>` không được phục hồi ở thời điểm ghi.

**Không phải compiler “quên kiểm tra” `groups[0]`.** Ta đã thay góc nhìn của compiler bằng tham chiếu kiểu cha và đưa thao tác ghi qua một đường không còn gắn với generic component type.

## 7. Alias không phải copy: vì sao thay đổi nhìn thấy từ mọi tham chiếu?

Câu lệnh:

```java
Object[] alias = groups;
```

không tạo mảng mới. `alias` và `groups` đều trỏ tới cùng vùng lưu trữ phần tử mảng. Do đó:

- `alias[0] = ...` làm thay đổi giá trị mà `groups[0]` sẽ đọc.
- `groups[0] = ...` cũng làm thay đổi giá trị mà `alias[0]` đọc.
- Gán `alias = new Object[1]` lại là việc đổi tham chiếu `alias`, **không** thay thế mảng mà `groups` đang trỏ tới.

Phân biệt này quan trọng đối với mọi API nhận hoặc trả mảng. Một method có thể không tự ghi vào mảng, nhưng nếu nó **đưa alias ra bên ngoài** cho mã không đáng tin, nơi khác có thể sửa và gây cùng nguy cơ.

Ví dụ: `return groups;`, đưa `groups` vào một field có thể sửa, hoặc gửi `groups` cho một callback nắm giữ `Object[]` là các tình huống cần phân tích. Không phải thao tác nào cũng tự động gây heap pollution; yếu tố rủi ro là khả năng **sửa nội dung array thông qua alias không duy trì generic contract**.

## 8. Phân biệt `ArrayStoreException` với `ClassCastException`

Hai exception này có thể xuất hiện ở những thời điểm khác nhau:

**`ArrayStoreException`:**

- Thường phát sinh khi lưu một object không tương thích với **runtime component type của mảng**.
- Trong ví dụ `String[]`, lúc ghi `Integer` qua `Object[]`, JVM chặn ngay.
- Trong mảng component `List`, ghi một `String` không phải `List` cũng sẽ bị chặn.

**`ClassCastException`:**

- Có thể phát sinh **muộn**, khi một chỗ sử dụng dữ liệu theo kiểu hẹp hơn mà runtime object không đáp ứng.
- Trong ví dụ generic varargs, đọc phần tử `List<String>.get(0)` và nhận giá trị thực `Integer` làm lỗi.
- Heap pollution đã xảy ra ở dòng ghi; exception là triệu chứng phát hiện ở dòng dùng sau đó.

Vì vậy, “ghi không ném exception” **không chứng minh** phép ghi giữ an toàn kiểu generic.

## 9. Thử mảng wildcard được phép tạo trực tiếp

Java cấm tạo `new List<String>[n]`, nhưng cho phép tạo một mảng có component là wildcard không giới hạn:

```java
List<?>[] groups = new List<?>[2];
```

`List<?>` là kiểu reifiable theo trường hợp wildcard không giới hạn. Một slot có thể giữ bất kỳ danh sách nào, dù danh sách đó chứa chuỗi, số hay kiểu khác.

Tệp **`WildcardArrayDemo.java`**:

```java
import java.util.List;

public class WildcardArrayDemo {

    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];

        groups[0] = List.of("A", "B");
        groups[1] = List.of(10, 20);

        System.out.println(groups.getClass()
                .getComponentType().getName());
        System.out.println(groups[0].get(0));
        System.out.println(groups[1].get(1));

        Object[] alias = groups;
        try {
            alias[0] = "not a list";
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac WildcardArrayDemo.java
java WildcardArrayDemo
```

Stdout:

```text
java.util.List
A
20
ArrayStoreException
```

Ví dụ minh họa một điểm **khác với heap pollution**: `List<?>[]` không hứa mọi slot chứa `List<String>`. Đặt một `List<Integer>` vào slot là hợp lệ theo hợp đồng vì type argument của từng list là chưa biết. Nếu ứng dụng yêu cầu mọi nhóm là `List<String>`, `List<?>[]` không đáp ứng mục tiêu ấy.

Cũng đừng dùng `List<?>[]` rồi ép unchecked sang `List<String>[]` chỉ để tạo một cách dùng nguy hiểm tương tự ví dụ phần 5.

## 10. Không phải mọi trường hợp đọc generic varargs đều nguy hiểm

Một method có thể chỉ đọc các phần tử từ generic varargs và đưa chúng vào một cấu trúc mới:

```java
static <T> void printCount(java.util.List<T>... groups) {
    for (java.util.List<T> group : groups) {
        System.out.println(group.size());
    }
}
```

Đoạn này cần đặt trong class; chưa có `main`. Bản thân việc duyệt và gọi `size()` **không tạo heap pollution**, vì không có thao tác gán danh sách sai kiểu vào mảng và không làm lộ mảng để nơi khác ghi.

Tuy nhiên, khai báo một generic varargs với component non-reifiable vẫn có thể phát cảnh báo từ compiler. Cảnh báo nhằm nhắc người viết và người gọi rằng phương thức đang dùng một cấu trúc mảng không mang đầy đủ type argument ở runtime.

Để coi một triển khai là an toàn, cần xem toàn bộ thân method, các đối tượng nó chuyển mảng cho, và cách nó dùng dữ liệu. “Không nhìn thấy phép gán trực tiếp” là một tín hiệu tốt nhưng **chưa đủ** nếu method vẫn để array alias thoát ra nơi có thể sửa.

## 11. Ví dụ generic varargs an toàn: duyệt và copy dữ liệu

Tạo tệp **`SafeVarargsMergeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsMergeDemo {

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... groups) {
        List<T> output = new ArrayList<>();

        for (List<? extends T> group : groups) {
            output.addAll(group);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = merge(
                List.of("red"), List.of("blue", "green"));

        List<Number> numbers = merge(
                List.of(1, 2), List.of(3.5));

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Biên dịch/chạy với Java 17 trở lên:

```bash
javac SafeVarargsMergeDemo.java
java SafeVarargsMergeDemo
```

Stdout:

```text
[red, blue, green]
[1, 2, 3.5]
```

### Vì sao method này có cơ sở để dùng `@SafeVarargs`?

- Nó chỉ **duyệt** các slot của array varargs.
- Không thay slot trong mảng bằng một danh sách có generic argument khác.
- Không trả về chính mảng, không lưu array vào một field có thể được mã khác truy cập và ghi.
- Dữ liệu được sao chép vào một `ArrayList<T>` mới theo hợp đồng generic.
- Kết quả trả về là `List<T>`, không phải `List<T>[]`, và được chuyển thành một danh sách không thể sửa qua API chuẩn bằng `List.copyOf`.

`@SafeVarargs` là một **lời cam kết của người viết** về cách triển khai dùng varargs parameter; compiler không chứng minh tự động mọi đường thực thi đều an toàn chỉ nhờ annotation.

`List.copyOf` từ chối phần tử `null`. Trong ví dụ, đầu vào không chứa `null`; với dữ liệu cho phép `null`, nên quyết định chính sách khác thay vì giả sử `copyOf` chấp nhận.

## 12. `@SafeVarargs` có tác dụng gì, và không có tác dụng gì?

`java.lang.SafeVarargs` là annotation để biểu đạt rằng người khai báo một method/constructor với varargs có kiểu phần tử không reifiable **cam kết không thực hiện thao tác không an toàn** trên biến varargs của mình.

Nó có thể giảm các cảnh báo unchecked liên quan tới khai báo và lời gọi varargs trong trường hợp được phép.

Điều annotation **không** làm:

- Không đổi runtime array component type từ raw `List` thành `List<String>`.
- Không bổ sung kiểm tra generic argument cho JVM.
- Không ngăn `Object[]` alias viết một `List<Integer>` vào mảng.
- Không tự sao chép hoặc bảo vệ mảng đầu vào.
- Không tự phát hiện mọi thân method nguy hiểm.
- Không cho phép viết trực tiếp `new List<String>[n]`.

Vì vậy, đoạn sau là **một lời cam kết sai**:

```java
// CỐ Ý NGUY HIỂM: không áp dụng mẫu này.
@SafeVarargs
static void unsafe(java.util.List<String>... groups) {
    Object[] alias = groups;
    alias[0] = java.util.List.of(99);
}
```

Một số compiler có thể phát thêm cảnh báo trong thân method dù có annotation; bất kể cảnh báo thế nào, annotation không hợp thức hóa hành vi heap pollution.

### Vị trí được phép áp dụng

Trên Java 17, `@SafeVarargs` được phép trên constructor, method static, method final và private instance methods theo quy tắc ngôn ngữ. Không thể tùy ý đặt lên một instance method public có thể override.

Điều kiện hợp lệ của annotation **khác** với sự an toàn thực sự của phương thức. Một method `static` có thể gắn annotation nhưng vẫn nguy hiểm nếu nó viết sai kiểu hoặc làm lộ array.

## 13. Một lỗi tinh vi: làm lộ mảng thay vì trực tiếp ghi vào nó

Không nhất thiết phải có `alias[0] = ...` ngay trong method chứa varargs thì heap pollution mới có thể xảy ra. Nếu method trả chính array cho caller hoặc lưu ở chỗ có thể truy cập, caller có thể ghi thông qua reference kiểu rộng hơn.

Hãy xem thiết kế **không nên dùng**:

```java
// Đoạn này chỉ minh họa nguy cơ API, cần đặt trong class.
static <T> T[] expose(T... values) {
    return values;
}
```

Khi caller thực sự nhận được một array có component runtime type không đủ cụ thể, phương thức `expose` có thể làm lộ mảng tới code khác. Một nơi khác có quyền sửa array có thể tạo sự lệch kiểu mà caller không lường trước.

Cần phân biệt các trường hợp:

- Với `String...` và caller truyền chuỗi thông thường, array runtime có thể là `String[]`, nên ghi `Integer` qua `Object[]` bị chặn.
- Với `List<String>...`, array runtime có component raw `List`, nên `List<Integer>` có thể lọt qua store check.
- Với `T...` không giới hạn, erasure của `T` là `Object`; array runtime được tạo còn phụ thuộc kiểu cụ thể và ngữ cảnh lời gọi. Không thể suy luận tất cả các trường hợp đều an toàn hoặc đều lỗi từ duy nhất chữ `T...`.

**Nguyên tắc an toàn:** Không làm lộ reference tới generic varargs array cho code có thể thay các phần tử không đúng hợp đồng. Nếu cần giữ dữ liệu, sao chép sang một generic collection có contract rõ ràng hoặc tạo một bản sao phù hợp với API.

## 14. Ví dụ trả về một collection mới thay vì mảng varargs

Tệp **`VarargsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class VarargsSnapshotDemo {

    @SafeVarargs
    static <T> List<T> snapshot(T... values) {
        List<T> result = new ArrayList<>();

        for (T value : values) {
            result.add(value);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words = snapshot("a", "b");
        List<Integer> numbers = snapshot(1, 2, 3);

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Biên dịch/chạy:

```bash
javac VarargsSnapshotDemo.java
java VarargsSnapshotDemo
```

Stdout:

```text
[a, b]
[1, 2, 3]
```

Trong ví dụ này, `snapshot` không cung cấp cho caller quyền truy cập trực tiếp tới array varargs. Nó tạo `ArrayList<T>` mới và trả collection snapshot unmodifiable.

Đây là một mẫu tốt khi nghiệp vụ **cần kết quả là tập dữ liệu** chứ không cần object mảng ban đầu. Lưu ý tính chất *shallow copy*: nếu các phần tử là object mutable, việc sao chép danh sách không sao chép sâu trạng thái của từng phần tử.

## 15. Varargs forwarding: alias có thể xuất hiện qua method khác

Giả sử một phương thức nhận `List<String>...` rồi chuyển nguyên mảng cho một method khác dưới kiểu rộng hơn:

```java
static void acceptsObjects(Object[] values) {
    // Có khả năng ghi vào values.
}

static void forward(java.util.List<String>... groups) {
    acceptsObjects(groups);
}
```

Đây là ví dụ cấu trúc, chưa phải chương trình độc lập. Việc chuyển `groups` cho `acceptsObjects(Object[])` tự nó không gây heap pollution. Nhưng nếu method nhận sau đó ghi `List<Integer>` vào một slot, nó sẽ gây cùng vấn đề dù không nằm trong `forward`.

Do đó, khi review `@SafeVarargs`, không chỉ tìm phép gán trực tiếp. Phải theo dấu mọi nơi array varargs:

- được truyền tới helper;
- được lưu trong field hay callback;
- được trả về hoặc expose qua getter;
- được chuyển thành view hoặc container backed by array mà bên ngoài còn sửa được.

Mục tiêu là biết liệu một đoạn code bên ngoài có thể dùng alias có kiểu rộng để thay slot bằng object sai generic argument hay không.

## 16. Đừng nhầm sửa nội dung list với sửa slot của varargs array

Hãy so sánh hai hành vi:

```java
// Bên trong method nhận List<String>... groups:

groups[0] = java.util.List.of("new");  // Thay slot bằng List<String>.
groups[0].add("x");                    // Thử sửa nội dung list.
```

Các dòng này chỉ minh họa; lời gọi `add` có thể ném `UnsupportedOperationException` nếu danh sách cụ thể không cho sửa, như `List.of`.

**Thay slot của array** và **sửa đối tượng list bên trong slot** là hai thao tác khác nhau:

- `groups[0] = someList` thay một reference trong mảng varargs.
- `groups[0].add(...)` tác động vào object list mà slot đang trỏ đến, không nhất thiết thay reference của slot.
- Nếu list cho phép sửa, việc gọi `add("x")` qua `List<String>` trong code typed là hợp lệ; compiler tiếp tục kiểm tra tham số `String`.
- Tuy nhiên, nếu list được truyền cho helper raw/unchecked, chính nội dung list cũng có thể bị heap pollution bằng cơ chế khác.

Cảnh báo về generic varargs và alias mảng tập trung vào rủi ro runtime array component type không phản ánh đầy đủ generic argument. Nó có thể kết hợp với các rủi ro raw collection khác, nhưng nên phân tích từng đường truy cập riêng.

## 17. `List<String>[]` có thể được khai báo nhưng không trực tiếp `new`

Một số người thấy phương thức:

```java
static void use(java.util.List<String>... groups) { }
```

rồi tưởng có thể khai báo và cấp phát mảng tùy ý:

```java
// CỐ Ý KHÔNG HỢP LỆ:
java.util.List<String>[] arr = new java.util.List<String>[2];
```

Hai trường hợp chịu quy tắc khác nhau.

- **Kiểu khai báo** `List<String>[]` có thể xuất hiện hợp lệ trong tham số/biến.
- **Biểu thức tạo array** `new List<String>[2]` bị cấm vì component type `List<String>` là non-reifiable.
- Generic varargs có cú pháp và cơ chế đặc biệt: compiler có thể tạo array ở call site theo erasure và đưa ra cảnh báo unchecked.
- Một lời gọi có sẵn mảng thay vì danh sách nhiều đối số còn liên quan tới quy tắc *fixed arity* và *variable arity invocation*; không nên đồng nhất mọi lời gọi varargs với việc luôn cấp phát một mảng mới.

**Sự tồn tại của generic varargs không phải ngoại lệ cho phép trực tiếp viết mọi generic array creation expression.**

## 18. Varargs và những cách gọi có thể khác nhau

Method:

```java
static void printAll(String... values) {
    System.out.println(values.length);
}
```

có thể được gọi như:

```java
printAll("A", "B");
printAll(new String[] {"A", "B"});
```

Trong lời gọi thứ nhất, compiler sử dụng cơ chế varargs để truyền hai phần tử. Trong lời gọi thứ hai, caller truyền trực tiếp mảng `String[]` như tham số duy nhất thích hợp với chữ ký.

Với generic varargs, một mảng đã được tạo qua một nguồn khác cũng có thể được truyền vào, nhưng **tính an toàn của nguồn mảng đó** vẫn phải được đánh giá. Nếu array bị heap pollution trước khi truyền, method chỉ đọc có thể nhận dữ liệu sai hợp đồng.

Bài học dành cho người viết API: không chỉ cần xem method có “tự làm bẩn” mảng không, mà còn hiểu mức độ tin cậy của tham số mảng và cách nó được dùng ở các đường gọi khác nhau.

## 19. Các cách tránh generic varargs khi không cần thiết

Nếu bài toán chỉ cần xử lý nhiều danh sách, có thể đổi API sang collection lồng nhau:

```java
static void printCounts(
        java.util.Collection<? extends java.util.List<String>> groups) {
    for (java.util.List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Đoạn này cần đặt trong class. Caller có thể gọi:

```java
printCounts(java.util.List.of(
        java.util.List.of("A", "B"),
        java.util.List.of("C")));
```

Không có array varargs với component `List<String>` non-reifiable được tạo cho lời gọi ấy. Compiler vẫn kiểm tra inner list có type argument `String` khi làm việc qua API typed.

### Ví dụ đầy đủ: không dùng varargs để gộp nhóm

Tệp **`CollectionAlternativeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionAlternativeDemo {

    static <T> List<T> merge(
            Collection<? extends List<? extends T>> groups) {
        List<T> output = new ArrayList<>();

        for (List<? extends T> group : groups) {
            output.addAll(group);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = merge(List.of(
                List.of("A"), List.of("B", "C")));

        System.out.println(words);
    }
}
```

Biên dịch/chạy:

```bash
javac CollectionAlternativeDemo.java
java CollectionAlternativeDemo
```

Stdout:

```text
[A, B, C]
```

Thay vì một mảng varargs, API nhận một collection các danh sách. Nó có thể nhận nhiều nguồn collection được định kiểu phù hợp và không phải phơi bày generic array ở parameter boundary.

Đổi lại, caller phải xây collection chứa các nhóm. Nếu API cần sự tiện lợi của lời gọi `merge(list1, list2)` và đã chứng minh method là an toàn, generic varargs kết hợp `@SafeVarargs` có thể hoàn toàn hợp lý.

## 20. PECS và generic varargs: mở rộng đầu vào an toàn

Trong ví dụ an toàn:

```java
@SafeVarargs
static <T> java.util.List<T> merge(
        java.util.List<? extends T>... groups) {
    // ...
}
```

Tham số `List<? extends T>` diễn tả mỗi nhóm là một nguồn cung cấp phần tử có thể đọc dưới dạng `T`. Đây là áp dụng **Producer Extends** trong PECS.

Nhưng bounded wildcard **không làm array varargs trở thành reifiable**. Nó giảm yêu cầu kiểu của phần tử trong mỗi list ở compile time, đồng thời generic varargs array vẫn có nguy cơ nếu method dùng một alias có thể ghi sai kiểu vào slot.

Phân biệt:

- `? extends T` bảo vệ cách **dùng từng list** trong mã nguồn.
- `Object[] alias` mở đường **thay cả list object** trong array nếu code thực hiện ghi.
- `@SafeVarargs` chỉ hợp lý khi thiết kế method và các helper không tạo ra việc ghi/lộ array không an toàn.

Không thể thay thế kiểm toán aliasing bằng việc chỉ thêm wildcard.

## 21. Nhận diện lỗi trong code review

Đọc một method generic varargs theo trình tự:

1. **Xác định element type của varargs:** `String` là reifiable; `List<String>` không reifiable; `T` không có bound thường bị xóa thành `Object`.
2. **Tìm chỗ array được xem như kiểu cha:** `Object[]`, raw `List[]`, hoặc một helper nhận mảng tương thích.
3. **Tìm mọi thao tác ghi vào slot:** `array[i] = ...`, `System.arraycopy`, `Arrays.fill`, method helper sửa mảng và callback có thể sửa.
4. **Tìm chỗ reference thoát ra:** return array, lưu field, trả view backed by array, ghi vào shared state.
5. **Đối chiếu runtime component type với dữ liệu được ghi:** `List<Integer>` vẫn là raw `List`.
6. **Đánh giá lời gọi đọc dữ liệu:** cast khi đọc theo `List<String>` có thể ném exception muộn.
7. **Xem annotation:** nếu có `@SafeVarargs`, kiểm tra nó phản ánh triển khai thật chứ không chỉ giấu cảnh báo.
8. **Chọn giải pháp:** chỉ đọc và copy; không làm lộ mảng; hoặc chuyển API sang `Collection`/`List`.

### Mẫu code đáng nghi

```java
// Đoạn phân tích, không phải API an toàn.
static void mutate(java.util.List<String>... groups) {
    Object[] values = groups;
    values[0] = java.util.List.of(123);
}
```

Mẫu này có cả ba tín hiệu: generic varargs với non-reifiable component, alias kiểu cha, và thao tác ghi một danh sách không cùng generic argument.

### Mẫu code ít rủi ro hơn

```java
@SafeVarargs
static <T> int count(
        java.util.List<? extends T>... groups) {
    int total = 0;
    for (java.util.List<? extends T> group : groups) {
        total += group.size();
    }
    return total;
}
```

Đoạn trên cần đặt trong class. Nó chỉ đọc `size()` và không làm lộ array; đây là tình huống phù hợp hơn để người viết cân nhắc cam kết `@SafeVarargs`.

## 22. Những hiểu nhầm thường gặp

**Hiểu nhầm 1 — “Mọi `Object[]` alias đều nguy hiểm.”** Không. Việc gán alias không tự làm hỏng dữ liệu; rủi ro tăng khi alias được dùng để ghi hoặc đưa cho code có thể ghi sai kiểu.

**Hiểu nhầm 2 — “Array store check sẽ luôn chặn `List<Integer>` đưa vào `List<String>[]`.”** Không. Runtime component thường chỉ là raw `List`, nên cả hai loại danh sách đều qua được kiểm tra.

**Hiểu nhầm 3 — “`ClassCastException` xuất hiện ngay lúc `alias[0] = List.of(42)`.”** Không trong ví dụ chính. Ghi được chấp nhận; lỗi phát sinh khi phần tử `Integer` bị dùng như `String`.

**Hiểu nhầm 4 — “Có `@SafeVarargs` tức JVM đã reify generic type.”** Không. Annotation không thay đổi erasure hoặc runtime component type.

**Hiểu nhầm 5 — “Không thể khai báo `List<String>...`.”** Có thể khai báo, nhưng compiler đưa ra cảnh báo và quy tắc để giúp nhận diện nguy cơ không reifiable.

**Hiểu nhầm 6 — “`List<?>[]` không thể tạo bằng `new`.”** Có thể tạo `new List<?>[n]` vì wildcard không giới hạn là reifiable theo quy tắc của Java.

**Hiểu nhầm 7 — “`List<?>[]` tương đương `List<String>[]`.”** Không. Loại thứ nhất cho phép nhiều generic arguments khác nhau ở mỗi list; loại thứ hai mang kỳ vọng phần tử là `List<String>`.

**Hiểu nhầm 8 — “Dùng `? extends T` là đủ để an toàn nếu vẫn ghi qua `Object[]`.”** Không. Wildcard ảnh hưởng compile-time operations trên `List`, không ngăn array alias thay cả slot.

**Hiểu nhầm 9 — “Method chỉ forward varargs sang helper chắc chắn an toàn.”** Không. Nếu helper giữ hoặc ghi vào array, vấn đề vẫn tồn tại.

**Hiểu nhầm 10 — “Heap pollution chỉ xảy ra ở varargs.”** Không. Raw types, unchecked casts và các đường API khác cũng có thể gây trạng thái dữ liệu không phù hợp với parameterized type.

**Hiểu nhầm 11 — “Chỉ nên xử lý warning bằng `@SuppressWarnings`.”** Không. Cần hiểu đường dữ liệu và sửa thiết kế; suppress chỉ có thể dùng cho một ranh giới được chứng minh và khoanh vùng.

**Hiểu nhầm 12 — “Chuyển `List<String>...` sang `Collection<List<String>>` làm generic reified.”** Không. Nó loại bỏ rủi ro array alias cụ thể khi không cần array, trong khi Generics vẫn chủ yếu kiểm tra ở compile time.

## 23. Bài tập và đáp án

**Bài 1 — Dự đoán exception**

```java
String[] arr = new String[1];
Object[] alias = arr;
alias[0] = 123;
```

Khi thực thi dòng cuối, exception nào?

**Đáp án:** `ArrayStoreException`, vì runtime component type là `String`.

**Bài 2 — Generic list array**

```java
List<?>[] arr = new List<?>[1];
Object[] alias = arr;
alias[0] = List.of(123);
```

Dòng cuối có phát sinh `ArrayStoreException` không?

**Đáp án:** Không. Runtime component là `List` và `List.of(123)` trả object triển khai `List`. `List<?>[]` không hứa các phần tử là danh sách chuỗi.

**Bài 3 — Heap pollution**

Giả sử có một `List<String>[]` do unchecked conversion/varargs tạo ra và runtime component là `List`. `Object[] alias = array; alias[0] = List.of(123);` có thể thành công không?

**Đáp án:** Có; mảng runtime chỉ kiểm tra raw `List`. Nếu đọc sau đó như `String`, có thể phát sinh `ClassCastException`.

**Bài 4 — Alias hay copy**

```java
Object[] alias = groups;
```

Nó có sao chép mảng không?

**Đáp án:** Không. Nó tạo thêm một tham chiếu tới cùng object array.

**Bài 5 — Annotation**

Có nên gắn `@SafeVarargs` lên method cố tình ghi `List<Integer>` vào mảng `List<String>...` không?

**Đáp án:** Không. Annotation là cam kết an toàn, không phải cơ chế tự bảo vệ.

**Bài 6 — API thay thế**

Một method chỉ cần duyệt các nhóm chuỗi và in số phần tử. Có thể dùng kiểu tham số nào để tránh generic array?

**Đáp án:** `Collection<? extends List<String>>` là lựa chọn phù hợp trong nhiều trường hợp, hoặc `List<List<String>>` nếu cần index và order.

**Bài 7 — Safe use**

Một method varargs chỉ lặp qua các nhóm để tạo `ArrayList<T>` mới rồi trả `List.copyOf`, không ghi vào varargs array hoặc expose array. Có phải ứng viên hợp lý cho `@SafeVarargs` không?

**Đáp án:** Có, khi method thỏa ràng buộc áp dụng annotation và toàn bộ đường gọi/helper thực sự an toàn.

**Bài 8 — Runtime component**

Khi method `void f(List<String>... lists)` được gọi theo varargs, mảng runtime có component class nào?

**Đáp án:** Tương ứng với raw `java.util.List`, không phải class riêng `List<String>`.

**Bài 9 — Ghi list hay sửa phần tử trong list**

`groups[0] = List.of("A")` và `groups[0].add("A")` có cùng nghĩa không?

**Đáp án:** Không. Dòng đầu thay reference ở slot 0; dòng sau sửa nội dung object list đang nằm trong slot (và có thể không được phép nếu list unmodifiable).

**Bài 10 — Phát hiện muộn**

Vì sao lệnh `groups[0].size()` vẫn có thể chạy sau khi slot bị thay bằng `List<Integer>`, nhưng `String s = groups[0].get(0)` lại lỗi?

**Đáp án:** `size()` không đòi phần tử là `String`, còn `get(0)` được dùng trong ngữ cảnh cần `String`, buộc runtime cast kiểm tra giá trị thực.

## 24. Quy trình sửa code và kiểm tra bằng công cụ

Khi nhận một cảnh báo về generic varargs:

1. Biên dịch với `javac -Xlint:unchecked -Xlint:varargs` để xác định vị trí cảnh báo và đường gọi.
2. Kiểm tra element type của varargs có non-reifiable hay không.
3. Tìm alias tới `Object[]` hoặc array type rộng hơn.
4. Xác minh không có ghi sai kiểu vào array slot, kể cả qua helper.
5. Xác minh array không escape tới nơi có thể ghi sai kiểu.
6. Nếu chỉ cần xử lý một tập các nhóm, cân nhắc `Collection<? extends List<T>>`.
7. Nếu varargs thật sự là API tốt nhất, giữ thân method chỉ đọc/copy và xem xét `@SafeVarargs` trong vị trí hợp lệ.
8. Viết test minh họa cả đường nhập hợp lệ và đường thử gây heap pollution có kiểm soát.
9. Tránh assert rằng “compiler không cảnh báo” có nghĩa nội dung thực sự an toàn.
10. Phân biệt `ArrayStoreException` khi gán với `ClassCastException` khi dùng dữ liệu.

### Quan sát descriptor bằng `javap`

Với class `UnsafeGenericVarargsDemo` đã biên dịch:

```bash
javap -p -s UnsafeGenericVarargsDemo
```

Ở mức mô tả kiểu JVM, method `corrupt(List<String>...)` có một tham số là array của raw `List`, với descriptor tiêu biểu:

```text
([Ljava/util/List;)V
```

Ký tự `[` biểu thị array, `L...;` là kiểu tham chiếu, `V` là `void`. Descriptor không mang `<String>`.

Để nhìn kỹ hơn những lệnh gán phần tử và cast:

```bash
javap -p -c UnsafeGenericVarargsDemo
```

Tìm `aastore` cho thao tác lưu phần tử mảng, `invokeinterface`/`invokevirtual` cho lời gọi method, và `checkcast` về `String` khi kết quả của `get()` được nhận như `String`.

Đối với một classfile do `javac` sinh, `javap -v` còn có thể hiển thị `Signature` giữ khai báo generic. Điều đó phục vụ metadata, **không khiến array store check tự kiểm tra được `<String>` ở runtime**.

## 25. Tổng kết

Rủi ro **ghi qua tham chiếu mảng kiểu cha** nằm ở sự kết hợp của:

1. **Generic varargs** có kiểu phần tử non-reifiable như `List<String>`.
2. **Array covariance** cho phép một tham chiếu `Object[]` trỏ đến mảng varargs.
3. **Type erasure** khiến runtime array component chỉ là raw `List`.
4. **Một phép ghi không an toàn** thay slot bằng `List<Integer>` mà JVM không thể phân biệt theo generic argument.
5. **Một phép đọc/cast về sau** vẫn tin hợp đồng `List<String>`, có thể gây `ClassCastException`.

Một `String[]` thường phát hiện ghi sai object ở thời điểm store bằng `ArrayStoreException`, còn mảng varargs của `List<String>` có thể không phát hiện được sai lệch generic argument cho tới lúc đọc.

Để tránh vấn đề, **không ghi qua alias kiểu rộng, không làm lộ mảng varargs cho mã có thể sửa sai kiểu, và ưu tiên chỉ đọc/copy**. Dùng `@SafeVarargs` khi thân method thực sự đáp ứng cam kết an toàn; nếu yêu cầu không cần array, cân nhắc chuyển API sang một `Collection`/`List` generic phù hợp.

### Tài liệu chuẩn

- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): cách khai báo variable arity parameter.
- [Java Language Specification §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): cơ chế đánh giá đối số và tạo mảng varargs khi cần.
- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): các kiểu có đủ thông tin runtime.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure của kiểu generic.
- [Java Language Specification §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): kiểm tra khi ghi vào mảng.
- [Java Language Specification §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): annotation và điều kiện sử dụng.
- [Java SE 17 `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): generic list methods trong các ví dụ.