# Các giới hạn overload, instanceof và tạo mảng liên quan xóa kiểu trong Java Generics

## Mục tiêu học tập

Java Generics giúp kiểm tra kiểu ở thời điểm biên dịch, nhưng phần lớn thông tin về *type argument* (ví dụ `String` trong `List<String>`) không tồn tại như một loại đối tượng riêng ở runtime. Cơ chế này gọi là **type erasure** (xóa kiểu). Nó mang lại khả năng tương thích với thư viện Java trước generics, đồng thời tạo ra những giới hạn quan trọng trong ngôn ngữ.

Ba nhóm thường gây bối rối nhất là:

1. **Overload:** không thể định nghĩa hai overload chỉ khác nhau ở `List<String>` và `List<Integer>` vì chữ ký của chúng trùng nhau sau erasure.
2. **`instanceof`:** không thể nhìn một đối tượng kiểu `Object` rồi hỏi bằng `instanceof List<String>` xem nó có “thật sự” là danh sách chỉ chứa String; runtime chỉ xác minh được kiểu container ở cấp phù hợp.
3. **Tạo mảng:** không thể viết `new List<String>[n]` hay `new T[n]` trong generic method, bởi mảng cần component type thực mà JVM có thể kiểm tra.

Bài này đi từ quy tắc ngôn ngữ tới ví dụ **Java 17+ có thể biên dịch/chạy**, các trường hợp lỗi compiler đã được kiểm chứng, cách thiết kế API thay thế, rồi tới bài tập tự kiểm tra.

## 1. Nền tảng: type erasure xóa những gì?

Xét:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Ở mã nguồn, hai tham chiếu có kiểu tham số hóa khác nhau:

- `names.add("An")` hợp lệ, còn `names.add(123)` bị compiler từ chối.
- `numbers.add(123)` hợp lệ, còn `numbers.add("An")` bị compiler từ chối.
- `names.get(0)` được compiler nhìn nhận là `String`.
- `numbers.get(0)` được compiler nhìn nhận là `Integer`.

Nhưng runtime không có một class `ArrayList<String>` khác với `ArrayList<Integer>`. Các instance thông thường cùng dùng lớp `java.util.ArrayList` và giao diện `java.util.List`; `getClass()` không biểu diễn type argument của từng instance.

Erasure có quy tắc cơ bản:

| Khai báo kiểu nguồn | Erasure | Ghi chú |
| --- | --- | --- |
| `List<String>` | `List` | Bỏ thông tin đối số String. |
| `List<Integer>` | `List` | Trùng erasure với List String. |
| `Map<String, Integer>` | `Map` | Cả hai type argument không nằm trong runtime class. |
| `T` không có bound tường minh | `Object` | Bound ngầm là Object. |
| `T extends Number` | `Number` | Erasure của type variable lấy từ bound đầu tiên. |
| `T extends Number & Comparable<T>` | `Number` | Dùng erasure của leftmost bound. |
| `String` | `String` | Không chứa type argument cần xóa. |
| `String[]` | `String[]` | Component type String tồn tại tại runtime. |

Đây là sự đơn giản hóa hữu ích để hiểu cơ chế; class file vẫn có thể chứa metadata generic trong thuộc tính `Signature`, phục vụ reflection và công cụ phân tích. Metadata này **không biến** một List String thành một class runtime riêng có thể được `instanceof` hay array store check xác minh đầy đủ.

Một ví dụ trực giác:

```java
// Mã đặt trong một phương thức có import List, ArrayList:
boolean same = new ArrayList<String>().getClass()
        == new ArrayList<Integer>().getClass();
// same == true
```

Vì hai đối tượng có cùng lớp runtime, các thao tác phụ thuộc trực tiếp vào class descriptor không thể tự phân biệt type argument String hay Integer.

## 2. Giới hạn thứ nhất: không overload chỉ bằng type argument generic

### 2.1. Tình huống bị compiler từ chối

Giả sử bạn muốn cùng tên phương thức xử lý hai loại danh sách:

```java
import java.util.List;

class OverloadErasureClash {
    static void process(List<String> data) {}
    static void process(List<Integer> data) {}
}
```

**Tệp `OverloadErasureClash.java` cố ý không biên dịch.** Kiểm tra bằng:

```bash
javac --release 17 OverloadErasureClash.java
```

Thông báo chính đã kiểm chứng:

```text
name clash: process(List<Integer>) and process(List<String>)
have the same erasure
```

Ở mã nguồn, hai kiểu `List<String>` và `List<Integer>` là khác nhau. Nhưng chữ ký tham số sau erasure của cả hai phương thức đều là `process(List)`. Java không cho phép duy trì chúng như hai overload chỉ khác generic argument.

Để hiểu chính xác, hãy phân biệt:

- **Chữ ký phương thức Java:** tên, danh sách tham số hình thức và các yếu tố liên quan đến tham số kiểu theo quy tắc JLS.
- **Erasure của chữ ký:** thay các kiểu generic trong tham số bằng erasure.
- **JVM method descriptor:** bao gồm cả kiểu trả về ở bytecode, nhưng điều này không có nghĩa Java được overload chỉ bằng kiểu trả về.

Không nên suy ra “generic bị xóa” nghĩa là mọi phần trong phương thức bị xóa: tên và những kiểu tham số không phụ thuộc type argument vẫn phân biệt được các phương thức.

### 2.2. Đổi tên theo mục đích khi hợp đồng thực sự khác

Một giải pháp rõ ràng:

```java
static void logStrings(List<String> values) {
    System.out.println("strings=" + values);
}

static void logIntegers(List<Integer> values) {
    System.out.println("integers=" + values);
}
```

Đây là hai phương thức minh họa đặt trong lớp đã import `List`, cũng xuất hiện trong chương trình hoàn chỉnh ở phần 6.

Ưu điểm: tên method cho biết nghiệp vụ nào áp dụng. Chỉ đổi một vài ký tự để “lách” erasure không phải lúc nào cũng tốt; dùng tên theo ý nghĩa thực sự nếu hai tác vụ khác nhau.

### 2.3. Nếu cùng một thuật toán, thường dùng một generic method

Nếu hai kiểu danh sách cần cùng hành vi, ví dụ chỉ đếm số phần tử, không nên tạo hai overload:

```java
static <E> int count(List<E> values) {
    return values.size();
}
```

Cả `count(List<String>)` và `count(List<Integer>)` ở vị trí gọi đều hợp lệ. Trong method, phần thuật toán không cần biết E là String hay Integer.

Nếu method chỉ quan sát List mà không sử dụng E ở vị trí khác, có thể cân nhắc chữ ký đơn giản hơn:

```java
static int countUnknown(List<?> values) {
    return values.size();
}
```

Chỉ dùng type variable có tên khi cần diễn đạt quan hệ kiểu giữa tham số, kết quả hoặc nhiều vị trí; dùng wildcard khi kiểu phần tử cụ thể không quan trọng đối với contract.

### 2.4. Một tham số khác có thể tạo overload thật

Những overload sau khác nhau ở tham số thực sự không bị xóa giống nhau:

```java
static void process(List<String> data, int mode) {}
static void process(List<Integer> data, String description) {}
```

Erasure tương ứng là `process(List, int)` và `process(List, String)`, nên chúng có thể cùng tồn tại nếu đặt trong một lớp hợp lệ. Tuy nhiên, tham số phụ phải có ý nghĩa thiết kế. Tránh thêm một giá trị giả chỉ để ép overload resolution chạy.

Có thể dùng tên method theo loại nghiệp vụ thay vì tạo các cặp tham số gây khó hiểu cho người gọi.

### 2.5. Type variable có bound cũng có thể clash

Không phải mọi erasure của T đều là Object. Với `T extends Number`, erasure của T là Number:

**Tệp `OverloadBoundClash.java` — không biên dịch:**

```java
class OverloadBoundClash {
    <T extends Number> void take(T n) {}
    void take(Number n) {}
}
```

Kiểm tra:

```bash
javac --release 17 OverloadBoundClash.java
```

Compiler báo dạng:

```text
name clash: take(Number) and <T>take(T) have the same erasure
```

Giải pháp không phải cast T về Object rồi hy vọng hai method khác nhau. Cần một contract khác tên, kiểu tham số khác ở runtime, hoặc gộp logic vào một method phù hợp.

### 2.6. Đừng nhầm overload với override

Quan hệ **override** ở chuỗi kế thừa có quy tắc bổ sung về **subsignature** nhằm bảo toàn khả năng tương thích khi một method trong thư viện cũ được generic hóa. Vì thế có trường hợp method của lớp con dùng chữ ký đã xóa mà vẫn override được method generic của lớp cha.

Điều này **không** cho phép hai overload `process(List<String>)` và `process(List<Integer>)` đứng cùng một lớp. Khi sửa `name clash`, hãy xác định bạn đang xem **hai method được overload** hay **hai method trong quan hệ kế thừa**.

## 3. Giới hạn thứ hai: `instanceof` không kiểm tra sâu type argument

### 3.1. Kiểm tra container là List

Giả sử một giá trị đến từ API không biết trước kiểu:

```java
Object input = List.of("A", 42);
boolean listLike = input instanceof List<?>;
System.out.println(listLike);
```

Đầu ra:

```text
true
```

`instanceof List<?>` chỉ yêu cầu giá trị là một List với kiểu phần tử chưa biết. Runtime có thể xác định điều đó qua class/interface của đối tượng. Nó không cần và **không cố** chứng minh toàn bộ phần tử là String.

Kết quả vẫn là true khi List chứa Integer, vì `List<?>` không cam kết kiểu phần tử cụ thể.

### 3.2. Vì sao `Object instanceof List<String>` bị từ chối?

**Tệp `InstanceofParameterized.java` — cố ý không biên dịch:**

```java
import java.util.List;

class InstanceofParameterized {
    static boolean check(Object value) {
        return value instanceof List<String>;
    }
}
```

Thử:

```bash
javac --release 17 InstanceofParameterized.java
```

Trong môi trường đã kiểm chứng, compiler báo:

```text
Object cannot be safely cast to List<String>
```

Lý do: toán hạng có kiểu tĩnh Object, nhưng `List<String>` không phải kiểu reifiable, nên runtime không thể thực hiện phép thử phân biệt những List có type argument String.

**Cẩn thận với phát biểu tuyệt đối:** trong Java 17, có một số phép `instanceof` dùng kiểu tham số hóa như `List<String>` được compiler cho phép **nếu kiểu tĩnh của toán hạng đã đủ cụ thể để phép cast tương ứng hợp lệ**. Ví dụ sau đã được biên dịch với `--release 17`:

```java
static boolean redundantCheck(List<String> value) {
    return value instanceof List<String>;
}
```

Đây không phải khả năng kiểm tra runtime mới cho từng phần tử: kiểu tĩnh đã biết là `List<String>`, phép thử không phát hiện List bị heap pollution. Vì vậy quy tắc thực hành là **đừng dùng `instanceof List<String>` để kiểm tra dữ liệu không đáng tin**; thay bằng `List<?>` và xác thực từng phần tử. Một lời khẳng định “`instanceof List<String>` luôn luôn không biên dịch trong mọi ngữ cảnh” là không chính xác với Java 17.

### 3.3. `instanceof T` khi T là type variable

**Tệp `InstanceofTypeVariable.java` — cố ý không biên dịch:**

```java
class InstanceofTypeVariable {
    static <T> boolean check(Object value) {
        return value instanceof T;
    }
}
```

Với `javac --release 17`, kết quả có dạng:

```text
Object cannot be safely cast to T
```

T là biến kiểu ở compile time, không tự cung cấp một class token runtime tương ứng với từng lời gọi. Không dùng `T.class` hoặc `instanceof T` để cố truy cập lớp thực.

Nếu cần kiểm tra runtime một kiểu class cụ thể, truyền token từ caller:

```java
static <T> boolean isType(Object value, Class<T> token) {
    return token.isInstance(value);
}
```

Lời gọi `isType("A", String.class)` trả true; `isType(1, String.class)` trả false. Nhưng `List.class` chỉ kiểm tra loại container List, không thể thay thế token `List<String>.class` vì class literal đó không tồn tại.

### 3.4. Cách kiểm tra một List thực sự chứa String

Một phương án:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof List<?> list)) {
        return false;
    }
    for (Object element : list) {
        if (!(element instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Đặt method trong lớp có import `java.util.List`, như chương trình hoàn chỉnh ở phần 6. Method trước hết kiểm tra container và sau đó duyệt mọi phần tử.

Hợp đồng trên chủ động coi `null` là không hợp lệ (vì `null instanceof String` là false). Với list rỗng, kết quả true theo nghĩa “không có phần tử nào vi phạm”. Nếu nghiệp vụ cần ít nhất một String, thêm điều kiện `!list.isEmpty()`.

Lưu ý về **thời điểm kiểm tra**: nếu caller khác có thể sửa danh sách sau khi kiểm tra, kết quả `allStrings` không bảo đảm danh sách sẽ mãi đúng. Để dựng một ranh giới tin cậy, có thể kiểm tra và copy sang collection mới, tránh chia sẻ alias mutable.

### 3.5. Reflection có thể biết khai báo nhưng không chứng minh dữ liệu

Java reflection có `Field.getGenericType()`, `Method.getGenericReturnType()`, `ParameterizedType` và những API tương tự có thể xem metadata kiểu generic từ class file. Nhưng metadata `List<String>` trên một field chỉ mô tả **khai báo kiểu**, không khiến mọi giá trị được đưa vào List tự động vượt qua kiểm tra String ở runtime.

Nếu một List đã bị raw alias chèn Integer, đọc metadata khai báo vẫn cho List<String>; dữ liệu thực vẫn sai. Khi xử lý dữ liệu không tin cậy, phải xác minh phần tử hoặc dùng quá trình deserialize/convert có kiểm tra theo hợp đồng.

## 4. Giới hạn thứ ba: tạo mảng generic

### 4.1. Vì sao mảng cần kiểu phần tử runtime?

Mảng Java là *reified*: đối tượng array giữ component type thực tại runtime. Với:

```java
String[] strings = new String[2];
Object[] alias = strings;
alias[0] = "OK"; // Hợp lệ.
// alias[1] = 42; // ArrayStoreException khi chạy.
```

JVM biết mảng thực là `String[]` nên có thể chặn ghi Integer, dù biến `alias` có kiểu tĩnh `Object[]`. Đây là một bảo vệ runtime đặc trưng của mảng tham chiếu.

Nhưng `List<String>` không có class runtime riêng của List Integer, nên không có component type reified “List of String” để mảng kiểm tra sâu.

### 4.2. Hai cách tạo mảng bị cấm

**Tệp `GenericArrayCreation.java` — cố ý không biên dịch:**

```java
import java.util.List;

class GenericArrayCreation {
    List<String>[] items = new List<String>[2];

    static <T> T[] create(int n) {
        return new T[n];
    }
}
```

Biên dịch:

```bash
javac --release 17 GenericArrayCreation.java
```

Compiler đã được kiểm chứng từ chối cả hai dòng với:

```text
error: generic array creation
```

Ở đây:

- `new List<String>[2]` bị cấm vì `List<String>` là kiểu non-reifiable.
- `new T[n]` bị cấm vì T là type variable không cung cấp class runtime của loại phần tử cần tạo.

Không giải quyết bằng `@SuppressWarnings("unchecked")`: đây là lỗi biên dịch ở biểu thức tạo mảng, không chỉ là warning.

### 4.3. Những mảng có thể tạo

| Biểu thức | Hợp lệ? | Lý do |
| --- | --- | --- |
| `new String[3]` | Có | Component type String là reifiable. |
| `new int[3]` | Có | Mảng nguyên thủy có component runtime int. |
| `new List[3]` | Có | Raw List là reifiable, nhưng làm mất ràng buộc generic khi sử dụng. |
| `new List<?>[3]` | Có | Wildcard không giới hạn; List<?> là reifiable. |
| `new List<String>[3]` | Không | Generic argument String không được reify trong component List. |
| `new List<? extends Number>[3]` | Không | Kiểu parameterized này không phải loại reifiable với mọi argument wildcard không giới hạn. |
| `new T[3]` trong method generic | Không | Type variable không có class token cụ thể. |
| `new String[2][]` | Có | Mảng chiều đầu có hai slot, mỗi slot ban đầu null và mang kiểu String[]. |

Dù `List<?>[]` hợp lệ, mỗi phần tử của array có thể là `List<String>` hoặc `List<Integer>`. Runtime chỉ kiểm tra rằng object được ghi là một List, không kiểm tra loại phần tử của mỗi List.

### 4.4. Nguy cơ nếu cố lách bằng cast không an toàn

Một mẫu rủi ro:

```java
// KHÔNG NÊN DÙNG:
@SuppressWarnings("unchecked")
static <T> T[] fake(int n) {
    return (T[]) new Object[n];
}
```

Mảng thực là `Object[]`. Cast bên trong generic method không biến nó thành `String[]` khi caller yêu cầu String. Đến vị trí gán:

```java
// Khi gọi phương thức fake ở trên:
String[] values = fake(3);
```

runtime có thể ném `ClassCastException` vì Object[] không phải String[]. Xóa kiểu không có nghĩa mảng mất component type runtime.

Một lối lách khác tạo `new List<?>[n]` rồi ép kiểu sang `List<String>[]`. Cast này không xác minh được String trong từng List, nên cho phép heap pollution nếu có đường alias `Object[]` và code ghi `List<Integer>` vào slot. Không nên tạo API dựa vào những cast như vậy.

### 4.5. Tạo mảng bằng factory hoặc Class token

**Dùng `Class<T>`:**

```java
@SuppressWarnings("unchecked")
static <T> T[] newReferenceArray(Class<T> component, int length) {
    if (component.isPrimitive()) {
        throw new IllegalArgumentException("reference type required");
    }
    return (T[]) java.lang.reflect.Array.newInstance(component, length);
}
```

Caller truyền `String.class`, `Integer.class`, v.v. `Array.newInstance` thực sự tạo mảng có component runtime tương ứng. Helper này chủ động từ chối token primitive vì `int[]` không tương đương `Integer[]`.

Cast từ Object về T[] nằm ở một chỗ đã có lập luận an toàn: component token đầu vào được dùng trực tiếp để tạo array thực. Không áp dụng suy luận này cho cast một Object[] tùy ý sang T[].

**Dùng array factory:**

```java
static <T> T[] copyArray(
        Collection<? extends T> source,
        java.util.function.IntFunction<T[]> arrayFactory) {
    return source.toArray(arrayFactory.apply(0));
}
```

Với `String[]::new`, factory cung cấp runtime component type String:

```java
String[] words = copyArray(List.of("C", "D"), String[]::new);
```

Đoạn helper này nằm trong một lớp có import `Collection`, `List` như chương trình hoàn chỉnh. Với dữ liệu đã nằm trong Collection, cách ngắn hơn là gọi thẳng `list.toArray(String[]::new)`.

### 4.6. Khi không cần mảng, hãy dùng List

Nếu mục tiêu chỉ là lưu, thêm, xóa hoặc chuyển phần tử, `List<T>` thường phù hợp hơn `T[]`. Mảng có kích thước cố định, phải tạo component type runtime và có covariance dẫn tới array store check; List có hợp đồng generic compile-time thuận tiện hơn trong ứng dụng thông thường.

Không dùng mảng như một “bản List nhanh hơn” nếu chưa có yêu cầu API hay số liệu hiệu năng phù hợp.

## 5. Phân biệt `List<?>`, raw `List` và `List<Object>`

Ba kiểu này hay bị gộp nhầm khi sửa lỗi erasure:

| Kiểu | Ý nghĩa | An toàn thao tác ghi? |
| --- | --- | --- |
| `List<?>` | Một danh sách có kiểu phần tử chưa biết. | Không thêm được phần tử non-null tùy ý; chỉ đọc thành Object. |
| `List` | Raw type: bỏ tham số generic. | Compiler có thể cho lời gọi ghi với warning unchecked; dễ làm sai hợp đồng một tham chiếu typed khác. |
| `List<Object>` | Danh sách chủ ý chứa Object. | Có thể thêm các Object, nhưng `List<String>` không tự là subtype của nó. |
| `List<? extends Number>` | Phần tử là một subtype chưa biết của Number. | Đọc thành Number; không tự thêm Number tùy ý. |
| `List<? super Integer>` | Container có thể nhận Integer. | Thêm Integer được; đọc an toàn nói chung dưới Object. |

`List<?>` hữu ích cho `instanceof` khi chỉ cần hỏi một đối tượng có phải List không. Nó cũng được xem là reifiable trong phân loại của Java, nên `new List<?>[2]` hợp lệ. Tuy nhiên, ký hiệu wildcard **không tạo lớp List<?> riêng** và không tự xác thực phần tử trong mỗi List.

## 6. Chương trình Java 17 hoàn chỉnh: ba giới hạn và cách áp dụng

**Tệp `ErasureLimitsDemo.java`:**

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.function.IntFunction;

public class ErasureLimitsDemo {
    static void logStrings(List<String> values) {
        System.out.println("strings=" + values);
    }

    static void logIntegers(List<Integer> values) {
        System.out.println("integers=" + values);
    }

    static <E> int count(List<E> values) {
        return values.size();
    }

    static boolean allStrings(Object value) {
        if (!(value instanceof List<?> list)) {
            return false;
        }
        for (Object element : list) {
            if (!(element instanceof String)) {
                return false;
            }
        }
        return true;
    }

    @SuppressWarnings("unchecked")
    static <T> T[] newReferenceArray(Class<T> component, int length) {
        if (component.isPrimitive()) {
            throw new IllegalArgumentException("reference type required");
        }
        return (T[]) Array.newInstance(component, length);
    }

    static <T> T[] copyArray(
            Collection<? extends T> source,
            IntFunction<T[]> arrayFactory) {
        return source.toArray(arrayFactory.apply(0));
    }

    static <T> T checkedCast(Class<T> type, Object value) {
        return type.cast(value);
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B");
        List<Integer> numbers = List.of(10, 20);
        logStrings(words);
        logIntegers(numbers);
        System.out.println("count=" + count(words));
        System.out.println("sameRuntimeClass="
                + (new ArrayList<String>().getClass()
                == new ArrayList<Integer>().getClass()));

        Object mixed = List.of("A", 42);
        System.out.println("instanceofWildcard=" + (mixed instanceof List<?>));
        System.out.println("mixedAllStrings=" + allStrings(mixed));
        System.out.println("wordsAllStrings=" + allStrings(words));

        List<?>[] groups = new List<?>[2];
        groups[0] = words;
        groups[1] = numbers;
        System.out.println("groupSizes=" + groups[0].size()
                + "," + groups[1].size());

        String[] allocated = newReferenceArray(String.class, 2);
        allocated[0] = "X";
        System.out.println("allocated=" + Arrays.toString(allocated));
        try {
            Object[] alias = allocated;
            alias[1] = 42;
        } catch (ArrayStoreException error) {
            System.out.println("arrayStore=" + error.getClass().getSimpleName());
        }

        String[] copied = copyArray(List.of("C", "D"), String[]::new);
        System.out.println("copied=" + Arrays.toString(copied));
        System.out.println("cast=" + checkedCast(String.class, "OK"));
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -Xlint:all ErasureLimitsDemo.java
java ErasureLimitsDemo
```

**Stdout đã kiểm chứng bằng chương trình này:**

```text
strings=[A, B]
integers=[10, 20]
count=2
sameRuntimeClass=true
instanceofWildcard=true
mixedAllStrings=false
wordsAllStrings=true
groupSizes=2,2
allocated=[X, null]
arrayStore=ArrayStoreException
copied=[C, D]
cast=OK
```

Trong phép thử đã thực hiện, `javac --release 17 -Xlint:all` không sinh cảnh báo cho chương trình trên.

### 6.1. Hai method khác tên thay cho overload bị trùng erasure

`logStrings` và `logIntegers` có thể cùng tồn tại vì **khác tên**. Phương thức `count(List<E>)` minh họa một thuật toán áp dụng chung khi không cần phân biệt kiểu phần tử.

### 6.2. Hai ArrayList có cùng runtime class

Biểu thức so sánh `getClass()` in true; generic argument String/Integer không tạo hai class ArrayList khác nhau ở runtime. Điều này giải thích nguyên nhân chung phía sau các giới hạn của bài.

### 6.3. Kiểm tra List container và từng phần tử là hai bước

`mixed instanceof List<?>` trả true vì `mixed` là List. Nhưng `allStrings(mixed)` trả false khi gặp Integer, còn `allStrings(words)` trả true.

Không dùng `instanceof List<String>` để thay phép duyệt kiểu thực trong tình huống nhận Object từ bên ngoài.

### 6.4. Mảng wildcard hợp lệ nhưng không ép các nhóm cùng kiểu

`new List<?>[2]` cho phép đặt `List<String>` ở slot đầu và `List<Integer>` ở slot thứ hai. Tất cả đều đúng hợp đồng List<?>. Dòng `groupSizes=2,2` chỉ kiểm tra kích thước, không hề đọc phần tử String/Integer.

### 6.5. Mảng String thật vẫn có array store check

`Array.newInstance(String.class, 2)` tạo String[]. Khi alias `Object[]` cố ghi Integer, JVM ném `ArrayStoreException`. Đó là cơ chế runtime của mảng, không mâu thuẫn với việc type argument của generic List bị erasure.

### 6.6. Array factory giữ component type chính xác

`String[]::new` cho `copyArray` biết cần String[] thật. Sau khi copy, chương trình in `copied=[C, D]`. Không có phép `(String[]) new Object[n]` sai bản chất.

## 7. Tóm tắt các ví dụ cố ý không biên dịch

Các tệp dưới đây phải lưu/biên dịch **riêng**, không ghép chúng với chương trình hợp lệ ở phần 6.

| Tệp | Thao tác không hợp lệ | Thông báo trọng tâm của javac |
| --- | --- | --- |
| `OverloadErasureClash.java` | `process(List<String>)` cùng `process(List<Integer>)` | `name clash ... same erasure`. |
| `OverloadBoundClash.java` | `take(Number)` cùng `<T extends Number> take(T)` | `same erasure`. |
| `InstanceofParameterized.java` | `Object value instanceof List<String>` | `Object cannot be safely cast to List<String>`. |
| `InstanceofTypeVariable.java` | `Object value instanceof T` | `Object cannot be safely cast to T`. |
| `GenericArrayCreation.java` | `new List<String>[2]`, `new T[n]` | `generic array creation`. |

Đây là những trường hợp lỗi compiler được tái hiện với `javac --release 17`. Thông báo chi tiết và vị trí dấu mũ có thể thay đổi theo phiên bản trình biên dịch, nhưng loại vi phạm nêu ở bảng là điểm cần hiểu.

## 8. Những cách sửa sai thường gặp

### Sai lầm 1: ép toàn bộ tham số List về raw type để overload

Bạn không thể tạo hai overload cùng tên có tham số raw `List` mà vẫn phân biệt được String/Integer theo nội dung; sau erasure chúng vẫn cùng chữ ký. Bỏ generic chỉ khiến code mất kiểm tra phần tử mà không giải quyết thiết kế API.

### Sai lầm 2: dùng cast `(List<String>) value` như phép xác thực

Một cast generic không thể kiểm tra đầy đủ phần tử List ở runtime. Thường JVM chỉ xác minh container là List, còn phần tử có thể sai kiểu. Nếu dữ liệu không tin cậy, duyệt bằng `List<?>` rồi xác thực từng phần tử; có thể tạo bản sao sau khi xác thực để tránh alias bị sửa về sau.

### Sai lầm 3: coi `instanceof List<?>` nghĩa là “chứa String”

Nó chỉ xác nhận đối tượng thuộc loại List. Nó trả true cả với danh sách Integer hoặc danh sách hỗn hợp.

### Sai lầm 4: cho rằng `T.class` hoặc `new T[n]` có thể dùng tự do

Type variable không tự cung cấp runtime class token. Nhận `Class<T>` hoặc factory từ caller nếu thật sự cần kiểm tra/tạo phần tử kiểu cụ thể.

### Sai lầm 5: dùng `(T[]) new Object[n]`

Cast không thay đổi runtime component type Object của mảng. Caller mong String[] có thể gặp ClassCastException khi nhận kết quả.

### Sai lầm 6: tạo `List<?>[]` rồi cast thành `List<String>[]`

Mảng chỉ kiểm tra component List; cast non-reifiable không bổ sung quy tắc String cho phần tử bên trong. Nếu bị ghi List<Integer> qua Object[] alias, có thể gây heap pollution và CCE muộn.

### Sai lầm 7: thêm `@SuppressWarnings("unchecked")` để “sửa lỗi”

Annotation chỉ giảm cảnh báo, không tạo runtime proof hay thay đổi dữ liệu. Nó cũng không thể biến lỗi compiler như `generic array creation` thành mã hợp lệ.

### Sai lầm 8: khẳng định Java 17 cấm mọi biểu thức `instanceof List<String>`

Cần xét kiểu tĩnh của toán hạng và quy tắc cast conversion: một vài trường hợp như `List<String> x; x instanceof List<String>` có thể biên dịch. Nhưng nó không phải phép kiểm tra sâu dữ liệu; tránh dùng nó để xác thực giá trị `Object` chưa rõ nguồn.

## 9. Cách lựa chọn giải pháp theo nhu cầu

| Nhu cầu thực tế | Cách tiếp cận |
| --- | --- |
| Hai hành vi xử lý List String/Integer khác nhau | Đặt tên method khác hoặc thiết kế tham số có khác biệt thật sau erasure. |
| Cùng thuật toán cho mọi List | `<E> method(List<E>)` hoặc `method(List<?>)` khi không cần liên kết E. |
| Kiểm tra một Object có phải List | `value instanceof List<?>` hoặc `List.class.isInstance(value)`. |
| Kiểm tra List chỉ chứa String | Duyệt `List<?>` và `instanceof String` từng phần tử; kiểm soát alias nếu cần. |
| Kiểm tra một Object là String | `value instanceof String`, hoặc `String.class.isInstance(value)`. |
| Method generic cần runtime Class<T> | Caller truyền `Class<T>`; dùng `type.cast(value)` khi phù hợp. |
| Cần `T[]` với component type runtime thật | Caller truyền `Class<T>` và dùng `Array.newInstance`, hoặc truyền `IntFunction<T[]>`. |
| Đổi Collection sang typed array | `collection.toArray(String[]::new)` hoặc overload tương đương. |
| Cần nhiều danh sách generic lồng nhau | Cân nhắc `List<List<T>>` thay vì mảng non-reifiable. |
| Chỉ cần quan sát nhiều List khác kiểu | `List<?>[]` hoặc `List<List<?>>` tùy quyền sở hữu và mutability. |

Đừng chọn mẹo cast chỉ để compiler hết báo lỗi. Cần làm rõ **giới hạn nằm ở overload resolution, ở phép thử runtime, hay ở yêu cầu component type khi tạo mảng**, từ đó thay đổi contract đúng chỗ.

## 10. Quy trình chẩn đoán nhanh

Khi gặp lỗi liên quan erasure:

1. **Đọc đúng thông điệp:** `same erasure`, `cannot be safely cast`, hay `generic array creation`?
2. **Xác định vị trí compile-time/runtime:** đây là lỗi javac hay exception từ JVM khi chạy?
3. **Viết erasure của các tham số:** ví dụ `List<String> → List`, `T extends Number → Number`.
4. **Với overload:** kiểm tra hai danh sách tham số còn khác nhau sau erasure không; nếu không, đổi thiết kế.
5. **Với instanceof:** hỏi JVM có đủ thông tin về kiểu được thử không. Với List<String> từ Object, kiểm tra List<?> rồi duyệt phần tử.
6. **Với array:** hỏi mảng cần component type reifiable nào ở runtime. Dùng factory/token hoặc List.
7. **Đánh giá dữ liệu không đáng tin:** raw type, unchecked cast, reflection và dữ liệu legacy có thể vượt kiểm tra compile-time.
8. **Viết test đúng ranh giới:** compile các ví dụ cấm để thấy lỗi; chạy trường hợp hợp lệ để quan sát output và array store check.
9. **Không triệt tiêu cảnh báo mà chưa hiểu:** warning có thể báo vị trí gây heap pollution và ClassCastException muộn.
10. **Giữ API đơn giản:** người gọi thường nên nhìn thấy hợp đồng rõ ràng thay vì những cast không thể kiểm chứng.

## 11. Bài tập tự kiểm tra

### Câu 1

Có thể viết cả `void save(List<String> x)` và `void save(List<Integer> x)` trong cùng lớp không?

**Đáp án:** Không. Cả hai thành `save(List)` sau erasure, compiler báo name clash.

### Câu 2

Vì sao `void save(List<String> x, int kind)` và `void save(List<Integer> x, String category)` có thể cùng tồn tại?

**Đáp án:** Erasure cho hai danh sách tham số là `(List, int)` và `(List, String)`, khác nhau ở tham số thứ hai. Tuy nhiên cần cân nhắc sự rõ nghĩa khi thiết kế API.

### Câu 3

`<T extends Number> void read(T x)` có thể overload với `void read(Number x)` không?

**Đáp án:** Không trong cùng ngữ cảnh overload ấy; T erases to Number nên cùng erasure.

### Câu 4

`Object obj = List.of(1, 2); obj instanceof List<?>` cho kết quả gì?

**Đáp án:** True, vì obj là List; wildcard không yêu cầu mọi phần tử thuộc String hay kiểu cụ thể khác.

### Câu 5

Có thể dùng `obj instanceof List<String>` để đảm bảo mỗi phần tử là String khi obj có kiểu tĩnh Object không?

**Đáp án:** Không. Phép thử ấy bị compiler từ chối trong ví dụ Object, và runtime không reify type argument String. Kiểm tra List<?> rồi duyệt phần tử.

### Câu 6

Tại sao `List<String> list; list instanceof List<String>` có thể biên dịch trên Java 17?

**Đáp án:** Vì kiểu tĩnh đã đủ cụ thể để xét phép kiểm tra, không phải do JVM có khả năng kiểm tra sâu từng phần tử. Nó không thích hợp cho xác thực dữ liệu không tin cậy.

### Câu 7

Vì sao `new List<String>[5]` bị cấm nhưng `new List<?>[5]` hợp lệ?

**Đáp án:** List<String> không reifiable còn List<?> reifiable khi tất cả đối số là wildcard không giới hạn. Runtime component của List<?>[] vẫn chỉ là List.

### Câu 8

Làm sao viết method generic cấp phát mảng String[] thực?

**Đáp án:** Truyền `String.class` cho helper dùng `Array.newInstance` hoặc truyền `String[]::new` cho helper nhận `IntFunction<T[]>`; không dùng `new T[n]`.

### Câu 9

Một List đã bị raw alias thêm Integer có thể khiến `String s = list.get(0)` báo gì?

**Đáp án:** Có thể ném ClassCastException tại cast do compiler chèn khi caller yêu cầu String. Đây là runtime failure, khác với lỗi generic array creation ở compile time.

### Câu 10

Nên xử lý thế nào nếu hai overload chỉ khác kiểu generic nhưng cùng một thuật toán?

**Đáp án:** Gộp thành một generic method như `<E> int count(List<E>)` hoặc nhận `List<?>` nếu chỉ quan sát. Nếu hai hành vi thật sự khác nhau, dùng tên phương thức phân biệt nghiệp vụ.

## 12. Ghi nhớ

- **Erasure** loại bỏ nhiều type argument của generic khỏi kiểu runtime; `List<String>` và `List<Integer>` có cùng erasure là `List`.
- **Overload** không được chỉ khác nhau ở những type argument đã bị xóa, vì sẽ dẫn đến `name clash`.
- **`instanceof`** không phải công cụ chứng minh mọi phần tử của `List<String>` từ một `Object` là String; `List<?>` là phép thử container, kiểm tra nội dung cần thêm bước.
- **Mảng** phải có component type reifiable để JVM kiểm tra ở runtime; `new T[n]` và `new List<String>[n]` bị cấm.
- **Class token/factory** cung cấp runtime component type cần thiết khi thực sự phải tạo `T[]`.
- **Raw type/unchecked cast** có thể vượt an toàn generic và gây lỗi muộn, không phải cách sửa những giới hạn trên.

Để thiết kế Java API an toàn và dễ hiểu, hãy xác định phần nào của kiểu tồn tại ở compile time, phần nào có thể kiểm tra ở runtime và **đặt hợp đồng tại đúng ranh giới** thay vì cố ép JVM nhận biết type argument mà erasure không giữ lại.
