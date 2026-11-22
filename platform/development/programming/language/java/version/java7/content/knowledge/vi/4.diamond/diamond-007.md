# Đọc cảnh báo unchecked và kiểm tra an toàn kiểu trong Java Generics

**Ngữ cảnh:** Java 7 — Diamond (`<>`). **Đề bài:** Đọc cảnh báo unchecked và kiểm tra an toàn kiểu.  
**Môi trường thực hành:** JDK 17+; các nguyên tắc generics, type erasure, unchecked conversion và diamond vẫn áp dụng trên Java hiện đại.

Khi viết `List<String> names = new ArrayList<>();`, trình biên dịch suy luận đối số kiểu `String` cho constructor mà vẫn kiểm tra hợp đồng generic. Ngược lại, khi đi qua một `List` *raw*, một phép ép kiểu `(List<String>)` hoặc một API mất thông tin kiểu, trình biên dịch có thể đưa ra **unchecked warning**: *“Tôi không đủ thông tin để chứng minh phép chuyển đổi hoặc thao tác này an toàn về kiểu.”*

Cảnh báo unchecked không đồng nghĩa chương trình **chắc chắn** lỗi khi chạy. Nhưng nó đánh dấu một nơi mà lỗi có thể chỉ lộ ra về sau, ví dụ `ClassCastException` khi đọc một phần tử. Mục tiêu là **đọc đúng cảnh báo, tìm nguồn mất kiểu, khôi phục hợp đồng kiểu hoặc xác thực dữ liệu**, thay vì chỉ tắt cảnh báo.

## 1. Phân biệt compile error, warning và lỗi runtime

| Tình huống | Điều trình biên dịch biết | Kết quả |
| --- | --- | --- |
| `List<String> items = new ArrayList<>();` | Suy luận được `String` từ kiểu đích | Biên dịch an toàn, không có unchecked warning. |
| `items.add(42);` khi `items` là `List<String>` | `Integer` không đáp ứng `String` | **Compile error**: thao tác bị từ chối. |
| `List raw = new ArrayList();` | Kiểu phần tử bị bỏ qua vì dùng raw type | Có thể có **rawtypes warning** nếu bật lint tương ứng. |
| `raw.add(42);` | Không biết tham số kiểu của lời gọi generic `add(E)` | **Unchecked call warning**. |
| `List<String> assumed = raw;` | Không chứng minh được mọi phần tử là `String` | **Unchecked conversion warning**. |
| `(List<String>) unknown` với `unknown` có kiểu không đủ cụ thể | Type erasure ngăn xác minh type argument lúc chạy | Có thể có **unchecked cast warning**. |
| `String s = assumed.get(1);` sau khi dữ liệu sai kiểu đã lọt vào | Compiler tin vào hợp đồng `List<String>` nhưng runtime có thể chứa `Integer` | Có thể ném **ClassCastException** lúc đọc. |

**Sự khác biệt quan trọng:** compile error chặn chương trình sai kiểu đã chứng minh được; unchecked warning nói compiler **không thể chứng minh** phép thao tác an toàn; runtime exception chỉ phát sinh khi thực sự thực hiện một phép toán không tương thích. Đừng xem “biên dịch xong, chạy thử chưa lỗi” là bằng chứng type-safe.

### 1.1. Cảnh báo raw type và unchecked khác nhau

- `rawtypes`: đang dùng kiểu generic mà **không cung cấp type argument**, như `List raw`, `new ArrayList()`, `Map map`.
- `unchecked`: có lời gọi, chuyển đổi hoặc ép kiểu mà compiler **không kiểm chứng đầy đủ** theo generic type argument.
- Một dòng code có thể kéo theo cảnh báo rawtype; các dòng dùng giá trị ấy có thể kéo theo thêm cảnh báo unchecked. Khi sửa, truy tới **điểm đầu tiên làm mất thông tin kiểu**.

Ví dụ `new ArrayList<>()` dùng **diamond** (từ Java 7) và không phải raw constructor. `new ArrayList()` bỏ ngoặc góc nên là **raw constructor**; đây là một khác biệt rất dễ bỏ sót khi đọc code.

## 2. Hiện cảnh báo đầy đủ bằng `javac`

JDK cung cấp các tùy chọn lint để hiện vị trí và loại cảnh báo:

```bash
javac -encoding UTF-8 -Xlint:unchecked -Xlint:rawtypes UncheckedDemo.java
java UncheckedDemo
```

- `-Xlint:unchecked`: in chẩn đoán chi tiết về thao tác generic không được kiểm chứng.
- `-Xlint:rawtypes`: báo những vị trí dùng raw generic type.
- `-encoding UTF-8`: chỉ định mã hóa nguồn để lệnh có thể chạy ổn định trong các môi trường có cấu hình khác nhau.
- Mỗi chẩn đoán có **tệp, vị trí, loại cảnh báo, kiểu mong đợi và kiểu thực tế** tùy trường hợp. Số dòng và nguyên văn thông báo có thể khác nhau giữa các phiên bản JDK; hãy dựa vào **loại** và **biểu thức bị đánh dấu**, không học thuộc toàn bộ văn bản compiler.

Khi chỉ thấy thông báo kiểu “uses unchecked or unsafe operations”, biên dịch lại với `-Xlint:unchecked` để xem **dòng cụ thể**. Đừng vội đặt `@SuppressWarnings("unchecked")` ở mức class để “làm sạch” toàn bộ dự án.

### 2.1. Ví dụ cố ý tạo cảnh báo, rồi quan sát lỗi runtime

Tạo tệp `UncheckedDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class UncheckedDemo {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("first");
        raw.add(42);

        List<String> assumed = raw;
        System.out.println(assumed.get(0));

        try {
            String second = assumed.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("caught ClassCastException");
        }
    }
}
```

Chạy hai lệnh ở đầu phần 2. **Đầu ra chuẩn (stdout)** của chương trình:

```text
first
caught ClassCastException
```

**Đây là ví dụ cố ý không an toàn để học cách đọc cảnh báo; không sao chép mẫu này vào code sản phẩm.** Khi biên dịch với lint, hãy tìm ít nhất ba loại vị trí:

1. `List raw = new ArrayList();`: cả khai báo lẫn khởi tạo đều là raw type; `-Xlint:rawtypes` cho biết đang mất đối số kiểu.
2. `raw.add("first")` và `raw.add(42)`: phương thức `add(E)` được gọi trên `List` raw, nên compiler không ngăn việc thêm hai loại phần tử khác nhau.
3. `List<String> assumed = raw;`: unchecked conversion từ `List` raw sang `List<String>`. Chương trình tuyên bố dữ liệu là chuỗi nhưng **không hề kiểm tra** các phần tử.

Vì `assumed` được khai báo là `List<String>`, code đọc phần tử thứ hai cần nhận `String`. Java thực hiện kiểm tra kiểu tại vị trí cần chuyển đối tượng thành `String`; phần tử thực tế là `Integer` nên phát sinh `ClassCastException`. Việc bắt exception trong ví dụ giúp quan sát lỗi có kiểm soát, **không phải giải pháp sửa kiểu**.

Cách tốt nhất khi ứng dụng **tự tạo và sở hữu** collection là khai báo kiểu ngay từ đầu:

```java
List<String> names = new ArrayList<>();
names.add("first");
// names.add(42); // Compile error, bị chặn trước runtime.
```

Đây là **đoạn minh họa bên trong phương thức**, giả sử đã import `List` và `ArrayList`. Dùng `<>` làm compiler suy luận `String` từ vế trái, thay vì tạo raw collection rồi ép kiểu sau đó.

## 3. Tại sao có unchecked warning? Type erasure

Java generics chủ yếu dùng **type erasure**. Khi biên dịch, compiler kiểm tra `List<String>` và `List<Integer>` theo hợp đồng kiểu, nhưng thông tin `String`/`Integer` của hai collection **không tồn tại như hai class runtime riêng biệt**.

Chẳng hạn:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
System.out.println(names.getClass() == numbers.getClass());
```

Đây là **mã minh họa** trong phạm vi phương thức, có import cần thiết. Kết quả là `true` vì cả hai đối tượng đều là `ArrayList` ở runtime. Điều đó **không xóa** kiểm tra kiểu của compiler: lợi ích của generics chủ yếu diễn ra ở compile time.

Do erasure:

- `value instanceof List<?>` hợp lệ vì chỉ kiểm tra đối tượng là một `List` nào đó.
- `value instanceof List<String>` **không hợp lệ**: JVM không kiểm chứng được đối số kiểu `String` của `List` bằng phép kiểm tra này.
- `List.class.isInstance(value)` cũng chỉ xác minh **lớp List**, không xác minh loại phần tử.
- Cast `(List<String>) value` có thể đưa ra unchecked warning vì phần `<String>` không được runtime kiểm chứng.
- Nếu một API bên ngoài trả dữ liệu kiểu `Object`/raw collection, muốn biến nó thành `List<String>` an toàn cần **kiểm tra toàn bộ phần tử** hoặc một hợp đồng nguồn đáng tin có thể chứng minh được.

**Cảnh báo không tự biến mất chỉ nhờ diamond.** Diamond làm sạch phần tạo đối tượng khi compiler còn thông tin kiểu, nhưng không thể khôi phục tính đúng đắn của dữ liệu đã đi qua một kênh mất kiểu.

## 4. Quy trình đọc một cảnh báo unchecked

Đứng tại vị trí được báo trong output compiler, làm lần lượt:

1. **Tìm biểu thức gây cảnh báo.** Nó thuộc nhóm `raw type`, `unchecked method invocation`, `unchecked conversion`, `unchecked cast` hay `generic varargs`?
2. **Ghi rõ kiểu nguồn và kiểu đích.** Ví dụ nguồn `List` raw, đích `List<String>`; câu hỏi là “ai bảo đảm mọi phần tử thực sự là String?”
3. **Lần theo nguồn dữ liệu.** Collection được tạo ngay trong hàm, trả về từ API cũ, lấy qua reflection, JSON, plugin, thư viện hay cache? Có thể sửa hợp đồng ở nguồn không?
4. **Chọn sửa kiểu gốc trước.** Thêm type arguments vào khai báo và constructor, thay raw API bằng generic API, hay diễn đạt kiểu chưa biết bằng `<?>` để giữ kiểm tra compile time.
5. **Nếu kiểu thật không thể biết trước:** xác thực dữ liệu ở ranh giới, kiểm tra từng phần tử, tạo collection mới có kiểu đúng rồi chuyển cho phần còn lại của hệ thống.
6. **Kiểm tra lại bằng lint và test.** Xác nhận cảnh báo mong muốn đã biến mất, code sai kiểu bị compiler chặn, và input hỗn hợp bị từ chối rõ ràng thay vì nổ ở nơi dùng cách xa nguồn.

Đừng sửa bằng cách gán bừa `Object` thành `String` hoặc cast từ `List<?>` sang `List<String>`. Cast ở đây không khám phá được type argument đã bị xóa; nó thường chỉ dịch chuyển rủi ro sang một vị trí khác.

### 4.1. Khi có thể sửa ngay tại nguồn

**Trước:**

```java
List raw = new ArrayList();
raw.add("alpha");
List<String> items = raw;
```

**Sau:**

```java
List<String> items = new ArrayList<>();
items.add("alpha");
```

Hai khối minh họa này giả định nằm trong một phương thức và có import collection. Bản **sau** khôi phục hợp đồng từ lúc tạo, dùng diamond và không cần unchecked conversion.

Với `Map`, giữ đầy đủ **cả kiểu khóa lẫn kiểu giá trị**:

```java
Map<String, Integer> counts = new HashMap<>();
counts.put("success", 3);
// counts.put(10, "wrong"); // Bị chặn khi biên dịch.
```

Đây là mã minh họa, giả định đã import `Map` và `HashMap`. `new HashMap<>()` suy luận đồng thời `String` và `Integer` theo kiểu ở vế trái.

### 4.2. Khi chỉ biết “một danh sách bất kỳ”: dùng `List<?>`

Nếu code **chỉ cần duyệt, đếm hoặc log dữ liệu** mà không cần biết kiểu phần tử, hãy dùng `List<?>`:

```java
static int countNonNull(List<?> values) {
    int result = 0;
    for (Object value : values) {
        if (value != null) {
            result++;
        }
    }
    return result;
}
```

Đây là phương thức minh họa, đặt trong lớp có import `List`. Wildcard `?` cho biết kiểu phần tử là **chưa biết**, nhưng compiler vẫn bảo vệ thao tác thêm phần tử không phù hợp. Có thể lấy phần tử ra dưới dạng `Object`; không thể tùy ý gọi `values.add("text")` vì kiểu thật của danh sách có thể là `Integer`.

**`List<?>` không có nghĩa “danh sách chắc chắn an toàn để cast sang `List<String>`”.** Nó chỉ diễn đạt trung thực rằng thông tin type argument không có sẵn. Khi cần danh sách chuỗi, phải kiểm tra trước.

## 5. Sửa ở ranh giới dữ liệu: xác thực rồi tạo bản sao có kiểu

Khi nguồn là dữ liệu động hoặc thư viện trả một `List<?>`, một cách an toàn là:

- Nhận đối tượng dưới dạng `List<?>`, không vội tuyên bố `List<String>`.
- Kiểm tra lần lượt mỗi phần tử có đúng kiểu `String` hay không.
- Chỉ sau khi mọi phần tử hợp lệ, đưa vào `List<String>` được tạo bằng diamond.
- Trả bản sao để những người giữ tham chiếu đến collection gốc không thể thêm dữ liệu sai kiểu vào kết quả đã xác thực.

Tạo `ValidatedCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ValidatedCopyDemo {
    static List<String> checkedStrings(List<?> source) {
        if (source == null) {
            throw new IllegalArgumentException("list is required");
        }

        List<String> checked = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            Object element = source.get(i);
            if (!(element instanceof String text)) {
                throw new IllegalArgumentException(
                    "element " + i + " is not String"
                );
            }
            checked.add(text);
        }
        return List.copyOf(checked);
    }

    public static void main(String[] args) {
        System.out.println(
            checkedStrings(List.of("alpha", "beta"))
        );

        try {
            checkedStrings(Arrays.asList("alpha", 42));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 -Xlint:unchecked -Xlint:rawtypes ValidatedCopyDemo.java
java ValidatedCopyDemo
```

**stdout chính xác:**

```text
[alpha, beta]
element 1 is not String
```

Phần quan trọng ở đây là **không có unchecked cast**. Toàn bộ phần tử đều được xác minh trước khi đưa vào danh sách có kiểu `List<String>`. `instanceof String text` là **pattern matching cho instanceof** được chuẩn hóa trong Java 16; mã chạy được trên JDK 17+. `List.of` (Java 9+) tạo danh sách bất biến; `List.copyOf` (Java 10+) trả danh sách không thể thay đổi bằng các phương thức sửa thông thường.

**Ranh giới về `null`:** ví dụ cố ý từ chối `null` vì `null` không thỏa `instanceof String`; `List.copyOf` cũng không cho phép phần tử `null`. Nếu hợp đồng ứng dụng cho phép `null`, phải viết một chính sách khác rõ ràng (và không dùng `List.copyOf` cho danh sách có null). `List.copyOf` không sao chép sâu các đối tượng mutable; ở đây `String` là immutable nên phù hợp.

**Giới hạn:** dù đã copy, nếu phần tử là một đối tượng có thể thay đổi, bản sao collection không tự làm đối tượng đó immutable. Vì vậy khái niệm “kiểu đúng” và “dữ liệu không thể đổi” là hai vấn đề khác nhau.

## 6. Kiểm tra kiểu bằng `Class<T>` khi làm việc với API generic

Một phương thức dùng chung cho nhiều loại phần tử có thể nhận **type token** `Class<T>` và kiểm tra từng phần tử bằng `Class.cast`. Cách này không phát sinh unchecked cast, vì `Class.cast` kiểm tra đối tượng ở runtime theo lớp được truyền vào.

Tạo `ClassTokenDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ClassTokenDemo {
    static <T> List<T> checkedCopy(
            List<?> source,
            Class<T> elementClass) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(elementClass, "elementClass");

        List<T> result = new ArrayList<>();
        for (Object item : source) {
            result.add(elementClass.cast(item));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<?> supplied = List.of(10, 20);
        List<Integer> numbers =
                checkedCopy(supplied, Integer.class);
        System.out.println(numbers);

        try {
            checkedCopy(List.of("10", 20), Integer.class);
        } catch (ClassCastException ex) {
            System.out.println("rejected mixed types");
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:unchecked -Xlint:rawtypes ClassTokenDemo.java
java ClassTokenDemo
```

```text
[10, 20]
rejected mixed types
```

Ở đây:

- `static <T> List<T> checkedCopy(...)` khai báo **generic method type parameter**; lời gọi với `Integer.class` làm `T` được xác định là `Integer`.
- `List<T> result = new ArrayList<>()` dùng diamond và bảo toàn thông tin kiểu trong phần xử lý nội bộ.
- `elementClass.cast(item)` kiểm tra từng đối tượng có thể được coi là `T`; sai kiểu sẽ ném `ClassCastException` **ngay tại ranh giới**, trước khi phần tử sai lọt vào danh sách kết quả.
- `List.copyOf` tạo kết quả không sửa được qua API collection; ví dụ từ chối null theo hợp đồng và không nhằm thay thế deep copy.

**Giới hạn của `Class<T>`:** có thể lấy `String.class` hoặc `Integer.class`, nhưng **không có** literal `List<String>.class`. Khi cần kiểm tra dữ liệu kiểu lồng nhau như `List<List<String>>` hoặc `Map<String, List<Integer>>`, cần xác thực **từng cấp cấu trúc và từng phần tử**, hoặc dùng bộ giải mã dữ liệu có cơ chế diễn tả kiểu generic phù hợp rồi xác thực kết quả. `List.class` chỉ kiểm tra cấp container.

## 7. Diamond và suy luận kiểu: khi *không có warning* vẫn phải đọc kỹ

Không phải mọi vấn đề về kiểu đều sinh unchecked warning. Ví dụ Java 10+ có `var`:

```java
List<String> first = new ArrayList<>();
var second = new ArrayList<String>();
var broad = new ArrayList<>();
```

Đây là **mã minh họa**, giả định import `List`/`ArrayList` và đặt trong phương thức. Trong dòng đầu, target type `List<String>` giúp diamond suy ra `String`. Dòng hai dùng `var` nhưng constructor đã có `String` nên kiểu biến suy ra `ArrayList<String>`. Dòng ba không có ràng buộc kiểu phần tử đủ cụ thể, nên trong tình huống này suy ra `ArrayList<Object>` — **không có unchecked warning**, nhưng rộng hơn ý định nếu ứng dụng chỉ muốn chuỗi.

Tạo `DiamondInferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondInferenceDemo {
    public static void main(String[] args) {
        List<String> typed = new ArrayList<>();
        typed.add("one");

        var broad = new ArrayList<>();
        broad.add("two");
        broad.add(3);

        System.out.println(typed);
        System.out.println(broad);
        System.out.println(
            broad.get(1).getClass().getSimpleName()
        );
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:unchecked -Xlint:rawtypes DiamondInferenceDemo.java
java DiamondInferenceDemo
```

```text
[one]
[two, 3]
Integer
```

Lỗi ở đây, nếu có, nằm ở **ý định thiết kế kiểu**: muốn `List<String>` nhưng lại khai báo khiến compiler chọn `Object`. Compiler **đã kiểm tra đúng hợp đồng `ArrayList<Object>` mà code thực sự yêu cầu**, nên không có lý do phát unchecked warning.

**Cách viết rõ hơn cho ứng dụng hiện đại:** `List<String> values = new ArrayList<>();` nếu muốn expose interface; hoặc `var values = new ArrayList<String>();` khi thực sự cần `var`. Đừng kỳ vọng Java sẽ thay đổi kiểu `broad` sau khi nhìn thấy lệnh `add("two")`.

## 8. Phân biệt những loại unchecked warning thường gặp

### 8.1. Unchecked call

Ví dụ `List raw = ...; raw.add(value);`. Compiler không có kiểu `E` cụ thể để bảo đảm đối số của `add(E)` đúng. **Sửa gốc:** loại bỏ raw declaration và khai báo đúng type argument; nếu dữ liệu thực sự chưa biết, dùng `List<?>` và không thêm bừa.

### 8.2. Unchecked conversion

Ví dụ `List<String> values = raw;`. Compiler không thể chứng minh mọi phần tử raw collection là `String`. **Sửa gốc:** nhận `List<?>` rồi xác thực và copy, hoặc cải tiến API nguồn để trả về `List<String>` với hợp đồng thật sự được thực thi.

### 8.3. Unchecked cast

Ví dụ giả định `Object unknown` là một danh sách:

```java
if (unknown instanceof List<?> values) {
    // Bây giờ có thể kiểm tra từng phần tử của values.
}
// Tránh: List<String> names = (List<String>) unknown;
```

Đây là **đoạn minh họa**, chưa khai báo `unknown`. Kiểm tra `instanceof List<?>` chỉ xác nhận container thuộc loại `List`; **không tự xác nhận** rằng mọi phần tử là `String`. Dùng quy trình ở phần 5 hoặc 6 để chuyển thành danh sách có kiểu.

### 8.4. Generic varargs và heap pollution

Một cảnh báo unchecked khác có thể xuất hiện khi dùng **varargs của kiểu generic không được reifiable**, ví dụ phương thức nhận `List<String>...`. Varargs được hiện thực qua mảng; nếu mảng/alias bị dùng không an toàn, dữ liệu sai kiểu có thể lọt vào và lỗi chỉ xuất hiện khi đọc.

**Heap pollution** là trạng thái một biến kiểu tham số hóa tham chiếu tới đối tượng không phù hợp với kiểu đó (thường do raw/unchecked operation hoặc generic array/varargs). Đừng giải quyết bằng cách thêm cast tùy tiện.

Có thể dùng `@SafeVarargs` trên phương thức hoặc constructor đủ điều kiện **chỉ sau khi kiểm tra phần triển khai thực sự không làm điều gì không an toàn với varargs array**. Annotation này là **cam kết của người viết API**, không phải kiểm chứng tự động. Nếu không chứng minh được, thay thiết kế bằng `List<List<T>>` hoặc đầu vào có cấu trúc generic khác dễ xác minh hơn; tránh suppress cảnh báo cả class.

## 9. Có khi nào được dùng `@SuppressWarnings("unchecked")`?

Đôi khi code tích hợp với API cũ, reflection hoặc hạ tầng generic phức tạp cần một phép ép kiểu mà chương trình biết một **bất biến** không thể biểu diễn đầy đủ cho compiler. Khi đó có thể cần suppression, nhưng phải đáp ứng:

1. **Phạm vi nhỏ nhất:** đặt trên đúng local variable hoặc method liên quan, không tắt cảnh báo toàn package/class nếu không cần.
2. **Có lập luận an toàn:** chứng minh bằng hợp đồng nguồn/đường đi dữ liệu rằng phần tử đáp ứng type argument mong muốn; không chỉ dựa vào “test trên máy tôi thấy đúng”.
3. **Kiểm tra ở ranh giới nếu có thể:** nếu dữ liệu do bên ngoài cung cấp, xác thực từng phần tử hoặc đưa qua API typed trước.
4. **Không giấu cảnh báo khác:** vẫn bật `-Xlint:unchecked` trong CI khi có thể, review vị trí suppression định kỳ.
5. **Không đồng nhất suppression và sửa lỗi:** annotation **chỉ thay đổi chẩn đoán của compiler**; nó không chèn kiểm tra runtime và không ngăn heap pollution.

**Ưu tiên không cần suppression:** ví dụ `ValidatedCopyDemo` và `ClassTokenDemo` tạo kết quả typed bằng các phép kiểm tra thực sự. Nếu phải giữ suppression tại điểm chuyển đổi, code review cần nêu rõ **bất biến nào** bảo đảm phép chuyển đổi đó an toàn.

## 10. Lưu ý về những vấn đề diamond không tự giải quyết

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “Dùng `<>` thì mọi warning mất.” | Diamond chỉ suy luận type argument của constructor; nó không sửa dữ liệu không tin cậy hoặc cast unchecked. |
| “`new ArrayList()` và `new ArrayList<>()` giống nhau.” | Dạng đầu là raw constructor, dạng sau là diamond với generic inference. |
| “Unchecked warning chắc chắn gây exception.” | Warning chỉ báo compiler không chứng minh được; lỗi có thể xảy ra sau đó hoặc không xảy ra. |
| “Không có warning nghĩa là hợp đồng nghiệp vụ đúng.” | `var xs = new ArrayList<>()` có thể suy ra `Object` đúng luật nhưng quá rộng so với nhu cầu. |
| “Ép `(List<String>)` đã kiểm tra hết chuỗi.” | Erasure ngăn runtime kiểm tra type argument chỉ bằng cast đó. |
| “`instanceof List<?>` chứng minh dữ liệu chỉ có String.” | Nó chỉ chứng minh container là List, chưa chứng minh kiểu phần tử. |
| “`Class<List<String>>` lấy được bằng `List<String>.class`.” | Không tồn tại class literal cho parameterized type; kiểm tra các cấp bằng cơ chế khác. |
| “`@SuppressWarnings` làm type-safe.” | Nó chỉ ẩn diagnostics; cần chứng minh hợp đồng hoặc validation thực tế. |
| “`List.copyOf` xử lý được mọi dữ liệu sai kiểu.” | Nó tạo collection unmodifiable, kiểm tra null, nhưng **không tự kiểm tra** type argument tùy ý. |
| “Kiểm tra một phần tử đầu là đủ.” | Với danh sách có dữ liệu động, phải kiểm tra **tất cả** phần tử theo hợp đồng. |

### 10.1. Những ranh giới đặc biệt

**API trả `Object` hoặc raw `Map`:** không tự khẳng định là `Map<String, Integer>`. Kiểm tra đối tượng là `Map<?,?>` trước, sau đó xác thực từng entry: khóa có là `String` và giá trị có là `Integer` không, rồi sao chép vào `Map<String, Integer>`. Với cấu trúc lồng nhau, làm tương tự ở từng cấp.

**Reflection và deserialization:** có thể tạo đối tượng mà hợp đồng generic ở compile time không biết. Cần xác thực dạng dữ liệu theo schema, loại phần tử và các giới hạn nghiệp vụ trước khi đưa vào lõi typed. Một cú cast không thay thế parsing/validation.

**Concurrent mutation:** dù vừa kiểm tra danh sách, thread khác vẫn có thể thay đổi nó trước khi copy nếu dữ liệu dùng chung có thể sửa đồng thời. Ở ranh giới đồng thời, cần bảo đảm sở hữu dữ liệu, snapshot nhất quán hoặc đồng bộ theo hợp đồng; duyệt một collection đang bị sửa không phải phép kiểm chứng atomic.

**External library warnings:** khi warning nằm trong mã do bạn biên dịch, nên sửa ở chỗ gọi API hoặc dùng phiên bản typed được hỗ trợ. Nếu nó phát sinh từ mã thư viện không kiểm soát, xác minh API và ràng buộc kiểu ở nơi nhập dữ liệu; không nên viết phép cast chỉ để loại warning.

## 11. Quy trình thực hành có thể dùng trong code review

Giả sử có warning: “unchecked conversion: required `List<String>`, found `List`”. Hãy trả lời:

1. **Nguồn dữ liệu từ đâu?** Đoạn code nào tạo danh sách? Có thể đổi `List raw` thành `List<String>` ngay ở đó không?
2. **Ai thêm phần tử?** Danh sách có thể chứa `Integer`, `null` hay kiểu bất kỳ không? Có alias raw còn giữ quyền sửa sau khi cast không?
3. **Có thể giữ kiểu chưa biết không?** Nếu chỉ duyệt/đếm, dùng `List<?>` mà không giả vờ đây là danh sách chuỗi.
4. **Nếu downstream cần chuỗi:** kiểm tra mọi phần tử bằng `instanceof String` hoặc `String.class.cast`, copy sang `List<String>` rồi trả kết quả. Chọn chính sách lỗi rõ ràng.
5. **Chạy lint và test:** biên dịch với `-Xlint:unchecked -Xlint:rawtypes`, thử dữ liệu chuẩn, dữ liệu hỗn hợp, `null`, danh sách rỗng và input có thể thay đổi.
6. **Đảm bảo lỗi được chặn gần nguồn:** không để một phần tử kiểu sai lang thang qua nhiều tầng rồi mới phát sinh `ClassCastException` tại code đọc.

Nếu một chiến lược conversion cần giữ nguyên danh sách gốc thay vì copy, phải chứng minh ai sở hữu và có thể sửa dữ liệu, vì bên giữ raw alias có thể tiếp tục thêm dữ liệu sai kiểu. **Bản sao được xác thực** là cách đơn giản để cô lập các ranh giới không tin cậy trong nhiều tình huống.

## 12. Bài luyện tập

**Bài 1 — Tìm warning:** biên dịch `UncheckedDemo` với `-Xlint:unchecked -Xlint:rawtypes`. Phân loại các dòng bị cảnh báo thành rawtype, unchecked call và unchecked conversion. Giải thích vì sao exception chỉ xuất hiện khi chương trình đọc phần tử thứ hai.

**Bài 2 — Sửa ngay tại nguồn:** đổi raw collection trong `UncheckedDemo` thành `List<String>` và `new ArrayList<>()`. Thử thêm `42`; xác nhận lỗi được bắt **khi biên dịch**. Bỏ phần thêm số, bỏ unchecked conversion và bắt exception; chạy lại để chương trình đúng kiểu ngay từ đầu.

**Bài 3 — Xác thực dữ liệu lạ:** chạy `ValidatedCopyDemo` với `List.of("a", "b")`, dữ liệu chứa `Integer`, danh sách rỗng và tham số `null`. Mô tả rõ đường đi xử lý và dữ liệu nào bị từ chối. Bổ sung thông điệp lỗi có chỉ số phần tử.

**Bài 4 — Generic method:** dùng `checkedCopy(List<?>, Class<T>)` tạo `List<Integer>` từ danh sách chưa rõ kiểu. Thử truyền phần tử `String` để quan sát việc từ chối gần nguồn; giải thích vì sao `Class<List<String>>` không thể tạo trực tiếp.

**Bài 5 — Diamond + `var`:** chạy `DiamondInferenceDemo`. Chuyển `var broad = new ArrayList<>()` thành `var broad = new ArrayList<String>()`; thử thêm số `3` và xác nhận compiler chặn thao tác sai kiểu dù không có cảnh báo unchecked.

**Bài 6 — Code review:** một API nhận `Object` chứa `Map<?,?>`, đích cần `Map<String, Integer>`. Viết hàm kiểm tra tất cả entry rồi copy vào `Map<String, Integer>` bằng diamond. Không sử dụng unchecked cast hay tắt warning toàn class.

## 13. Ghi nhớ

- **Đọc warning là tìm lỗ hổng trong chứng cứ về kiểu**: phân biệt rawtype, unchecked call/conversion/cast và lỗi runtime.
- **Diamond `<>` (Java 7+)** bảo toàn generic inference ở constructor khi ngữ cảnh đủ rõ; khác hẳn raw constructor không có ngoặc góc.
- **Ưu tiên sửa tại nguồn**: khai báo `List<String>`/`Map<K,V>` rõ ràng, dùng `new ArrayList<>()`/`new HashMap<>()`, giữ type safety từ đầu.
- **Không biết kiểu thì diễn đạt đúng sự thật** bằng `List<?>`, sau đó xác thực từng phần tử trước khi đưa dữ liệu vào collection typed.
- **Erasure là lý do generic cast có thể unchecked**; `instanceof List<?>` và `Class<T>` chỉ kiểm tra được phần ngữ nghĩa mà chúng thực sự biểu diễn.
- **Không dùng `@SuppressWarnings("unchecked")` như một cách sửa lỗi**. Nếu buộc phải dùng, hạn chế phạm vi và giải thích bất biến chứng minh an toàn.
- **Không có warning vẫn cần xem lại thiết kế kiểu**: `var` kết hợp diamond thiếu target type có thể suy luận `Object`.
- **Code mới trên JDK hiện đại** có thể sử dụng `List.of`, `List.copyOf`, pattern matching `instanceof` và `var` đúng chỗ, đồng thời tiếp tục hưởng lợi từ generics/diamond vốn đã có từ Java 7.
