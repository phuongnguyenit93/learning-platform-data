# Java 7 — Varargs an toàn: Sử dụng cảnh báo unchecked, varargs trong kiểm tra mã

## 1. Mục tiêu: biến warning thành tín hiệu review, không phải nhiễu cần tắt

Từ Java 7, Java có annotation **`@SafeVarargs`** để tác giả phương thức khai báo rằng việc dùng varargs với kiểu phần tử generic không thể kiểm tra đầy đủ tại runtime là an toàn. Khả năng này vẫn có ý nghĩa trên Java 17+ và những JDK hiện đại. Nhưng trước khi áp dụng annotation, người review cần hiểu **vì sao compiler cảnh báo**, cảnh báo nằm ở **khai báo hay lời gọi**, và mã thực sự có thể gây **heap pollution** hay không.

Hai nhóm chẩn đoán của `javac` được sử dụng trong quy trình review:

- **`-Xlint:unchecked`:** yêu cầu compiler hiển thị các thao tác generic không thể kiểm tra đầy đủ tại compile-time, bao gồm cảnh báo liên quan tới **khai báo generic varargs** và **tạo mảng generic ở vị trí gọi varargs**. Nhóm này còn bao gồm các phép cast/convert unchecked không liên quan trực tiếp tới varargs.
- **`-Xlint:varargs`:** yêu cầu compiler cảnh báo một số cách sử dụng **tham số varargs có nguy cơ không an toàn trong chính thân phương thức**, đặc biệt hữu ích khi mã đã được gắn `@SafeVarargs`. Tùy mã và JDK, chẩn đoán có thể xuất hiện ở lời gọi hoặc hành vi đưa mảng varargs ra ngoài.

Mục tiêu không phải là loại bỏ mọi warning bằng annotation. Quy trình đúng là **đọc cảnh báo → truy ngược luồng dữ liệu → sửa thiết kế hoặc chứng minh an toàn → chỉ khi đó mới dùng annotation/suppression ở phạm vi hẹp → kiểm thử và review tiếp**.

Bài này đặt trong chủ đề **Varargs an toàn** của Java 7 nhưng sử dụng cú pháp, compiler và API còn phù hợp với JDK 17+. Ví dụ chính có chương trình độc lập; các đoạn sai được đánh dấu rõ ràng. Thông báo compiler có thể thay đổi cách trình bày giữa các phiên bản JDK, vì vậy không nên viết test phụ thuộc nguyên văn mọi chữ trong warning.

## 2. Hiểu gốc rễ: `T...` là một mảng và generics bị type erasure

Cú pháp:

```java
static void printAll(String... items) {
    for (String item : items) {
        System.out.println(item);
    }
}
```

là **phương thức minh họa**, không phải tệp Java độc lập. Tham số `items` trong thân hàm có kiểu `String[]`. Caller có thể gọi `printAll("a", "b")` hoặc `printAll(new String[]{"a", "b"})`. Khi có một mảng phù hợp được truyền sẵn, phương thức nhận tham chiếu mảng đó; varargs không có nghĩa Java luôn copy array.

Với generic:

```java
static void consumeGroups(java.util.List<String>... groups) {
    for (java.util.List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

tham số `groups` có kiểu khai báo `List<String>[]`. Tuy nhiên, do **type erasure**, JVM không lưu type argument `String` trong mỗi `List` để kiểm tra component của mảng. Mảng được tạo tại lời gọi variable-arity có component runtime là `java.util.List`. Compiler không thể xác nhận mọi lần thay thế phần tử mảng luôn là `List<String>`; từ đây mới xuất hiện warning.

### 2.1. Reifiable và non-reifiable khác nhau ra sao?

- **Reifiable type**: thông tin kiểu cần để kiểm tra có sẵn ở runtime theo quy tắc JLS. Ví dụ `String`, `int`, `String[]`, raw `List`, `List<?>`.
- **Non-reifiable type**: thông tin tham số kiểu không được giữ đầy đủ ở runtime. Ví dụ `List<String>`, `Map<String,Integer>`, kiểu biến `T`, và `List<String>[]`.
- `String...` có phần tử reifiable, thường không có cảnh báo do non-reifiable varargs.
- `List<String>...` có phần tử non-reifiable; một mảng chứa `List` ở runtime không kiểm tra được nội dung kiểu `String`.
- `T...` trong phương thức generic cũng thường có phần tử non-reifiable; cần review cách dùng, kể cả khi method chỉ có vài dòng.

**Type erasure không vô hiệu hóa generics.** Compiler vẫn kiểm tra `List<String>` ở mã nguồn; chỉ khi một thao tác unsafe (cast, raw type, array alias, unchecked conversion...) vượt qua bảo đảm đó, chương trình mới có thể đưa dữ liệu sai kiểu vào cấu trúc generic.

### 2.2. Vì sao Java cho phép varargs generic nếu generic array creation bị cấm?

Bạn không thể tự tạo mảng sau theo cách thông thường:

```java
java.util.List<String>[] values = new java.util.List<String>[2];
```

Đoạn này **cố ý không biên dịch** (*generic array creation*): phần tử `List<String>` không phải reifiable.

Nhưng Java vẫn cho phép khai báo `void f(List<String>... xs)` để hỗ trợ API tiện lợi. Compiler có thể phải thực hiện **unchecked generic array creation** khi biến các đối số riêng lẻ thành mảng varargs. Chính sự thỏa hiệp này đòi hỏi người viết và người review phải quan tâm tới warning.

## 3. Hai flag `-Xlint` cần bật khi review

Chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsLintReviewDemo.java
java VarargsLintReviewDemo
```

Đây là lệnh cho **chương trình hoàn chỉnh trong phần 6**. `--release 17` yêu cầu biên dịch theo API/ngôn ngữ của Java 17; `-Xlint:unchecked` và `-Xlint:varargs` mở các nhóm cảnh báo cần quan tâm. Tùy cấu hình compiler, cảnh báo xuất hiện ở **stderr trong bước biên dịch**, không phải stdout khi chạy class.

| Tùy chọn | Điều nó giúp phát hiện | Cách xử lý khi thấy |
| --- | --- | --- |
| `-Xlint:unchecked` | Cast/convert generic không thể kiểm tra, non-reifiable varargs declaration, unchecked array creation ở call site | Xác minh nguồn dữ liệu, kiểu generic và đường heap pollution; ưu tiên sửa thiết kế |
| `-Xlint:varargs` | Một số thao tác có thể không an toàn với tham số varargs, kể cả trong method đã có `@SafeVarargs` | Kiểm tra array alias, mutation, leak/escape, truyền array tới method khác |
| `-Xlint:all` | Tập cảnh báo rộng hơn, bao gồm các nhóm trên | Hợp lý khi CI/team muốn rà quét toàn diện; có thể tạo nhiều cảnh báo ngoài bài varargs |
| `-Werror` | Xem warning của compiler là lỗi build | Chỉ bật theo chính sách dự án sau khi có kế hoạch xử lý warning và cấu hình lint rõ ràng |
| `-Xlint:-unchecked` / `-Xlint:-varargs` | Tắt tương ứng nhóm lint | **Không phải cách sửa:** ẩn tín hiệu an toàn kiểu |

**Điểm cần nhớ:** `-Xlint:unchecked` và `-Xlint:varargs` là hai nhóm khác nhau nhưng bổ sung cho nhau. Không thể kết luận an toàn chỉ vì một nhóm không còn warning. `-Werror` là cơ chế cưỡng chế build, không chứng minh method đúng khi mọi warning đã bị suppress.

### 3.1. Đọc output ở đúng bước

```text
BƯỚC BIÊN DỊCH (javac)
  ├── warning ở khai báo phương thức varargs
  ├── warning ở lời gọi tạo generic array
  └── warning ở thân phương thức/escape khi bật lint phù hợp

BƯỚC CHẠY (java)
  ├── không còn compiler warning
  └── có thể vẫn ném ClassCastException nếu heap pollution thực sự xảy ra
```

Khi báo cáo lỗi, nên lưu **JDK version, lệnh javac, vị trí file/dòng và warning category**, không chỉ screenshot một câu cảnh báo bị cắt. Trong CI, giữ compiler output có thể truy hồi và review theo diff để không bỏ lỡ warning mới.

## 4. Phân biệt ba nơi warning có thể xuất hiện

### 4.1. Cảnh báo ở khai báo method

```java
static void unsafe(java.util.List<String>... groups) {
    // ...
}
```

Method khai báo phần tử varargs `List<String>` là non-reifiable, nên compiler có thể cảnh báo gần:

```text
Possible heap pollution from parameterized vararg type java.util.List<java.lang.String>
```

Thông điệp này không nói rằng mọi lời gọi sẽ sai; nó nhắc reviewer rằng **method đang có quyền truy cập tới một mảng có thể bị ô nhiễm kiểu**.

### 4.2. Cảnh báo ở lời gọi varargs

```java
unsafe(java.util.List.of("alpha"));
```

Vì compiler cần tạo array cho các tham số `List<String>` riêng lẻ, có thể có cảnh báo gần:

```text
unchecked generic array creation for varargs parameter of type java.util.List<java.lang.String>[]
```

Lỗi có thể được phát hiện **ở method khai báo và ở call site**, do hai vị trí cùng có trách nhiệm: tác giả method bảo đảm không ghi/để lộ array, còn caller phải biết lời gọi đang đi qua ranh giới không kiểm tra được hoàn toàn.

### 4.3. Cảnh báo về thân method dù đã có `@SafeVarargs`

Xét thiết kế cố ý nguy hiểm:

```java
@SafeVarargs
static <T> T[] leakArray(T... values) {
    return values; // Làm mảng varargs có thể thoát ra ngoài.
}
```

Snippet là phương thức minh họa **không nên áp dụng**. Trả array có thể làm caller giữ hoặc sửa một array có component runtime không biểu diễn đầy đủ kiểu T. Khi bật `-Xlint:varargs`, compiler có thể cảnh báo vì **mảng non-reifiable varargs thoát ra ngoài method**, dù `@SafeVarargs` đã triệt tiêu một số warning khác.

Không được hiểu rằng cảnh báo body chỉ phát sinh khi return array; những rủi ro khác bao gồm gán thông qua `Object[]`, lưu vào field và truyền array sang mã không an toàn. Compiler không đảm bảo tìm được **tất cả** các tình huống heap pollution.

## 5. Cơ chế heap pollution: khi array check không còn bảo vệ generic type

Ví dụ:

```java
static void unsafe(java.util.List<String>... groups) {
    Object[] alias = groups;
    alias[0] = java.util.List.of(42);
    String value = groups[0].get(0);
    System.out.println(value);
}
```

Đây là **phương thức cố ý không an toàn**. Phân tích:

1. `groups` có kiểu khai báo `List<String>[]`, nhưng mảng được tạo tại runtime có component là `List`.
2. Vì array covariance, có thể gán tham chiếu `groups` cho `Object[] alias`.
3. `alias[0] = List.of(42)` ghi một `List<Integer>`. Runtime chỉ xác nhận được phần tử là một `List`, không thể xác nhận nó là `List<String>`.
4. `groups[0].get(0)` thực sự trả `Integer`. Việc gán vào `String value` làm compiler yêu cầu cast về String; JVM ném `ClassCastException` ở **bước đọc**, có thể cách xa nơi gây ô nhiễm kiểu.

Đây là heap pollution: một biến generic về mặt khai báo hứa kiểu A, nhưng dữ liệu thực tế không tuân thủ A do thao tác unchecked.

### 5.1. Tại sao không bị `ArrayStoreException` ngay lúc ghi?

So sánh hai trường hợp:

```java
Object[] strings = new String[1];
strings[0] = 42; // ArrayStoreException ngay tại thao tác ghi.
```

Với `String[]`, JVM **biết** component type runtime là `String` và từ chối Integer.

```java
Object[] lists = new java.util.List[1];
lists[0] = java.util.List.of(42); // Được phép: vẫn là List.
```

Với `List[]`, JVM chỉ biết component type `List`; không có runtime check cho `String` làm type argument. Chính giới hạn này khiến generic varargs cần sự thận trọng.

### 5.2. Warning không phải bằng chứng bug, và hết warning không phải bằng chứng an toàn

Phương thức chỉ **duyệt và đọc**, không mutate/escape array, thường có thể hoạt động an toàn dù khai báo generic varargs phát warning.

Ngược lại, nếu gắn `@SafeVarargs` sai sự thật, compiler có thể bớt cảnh báo nhưng mã vẫn gây heap pollution hoặc `ClassCastException`. Đánh giá an toàn phải dựa vào **toàn bộ luồng dữ liệu**, không chỉ số warning.

## 6. Chương trình Java 17+ chạy được: tái hiện warning và kiểm thử kết quả

Tạo tệp **`VarargsLintReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class VarargsLintReviewDemo {
    @SafeVarargs
    static <T> List<T> snapshot(T... items) {
        List<T> result = new ArrayList<>();
        for (T item : items) {
            result.add(item);
        }
        return result;
    }

    @SafeVarargs
    static void readOnly(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println("read: " + group.get(0));
        }
    }

    static void unsafe(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String value = groups[0].get(0);
        System.out.println(value);
    }

    public static void main(String[] args) {
        readOnly(List.of("A"), List.of("B"));
        System.out.println("copy: " + snapshot("x", "y"));

        try {
            unsafe(List.of("first"));
        } catch (ClassCastException ex) {
            System.out.println("caught: " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsLintReviewDemo.java
java VarargsLintReviewDemo
```

Phần **biên dịch** có các warning liên quan tới `unsafe(List<String>...)`: một warning tại khai báo và một warning tại lời gọi `unsafe(List.of("first"))` khi bật nhóm lint tương ứng. Đừng đưa các warning đó vào “stdout khi chạy”, vì chúng là chẩn đoán của `javac`. Số dòng/format thông báo có thể khác nhau theo JDK và các cờ khác.

**Stdout khi chạy chương trình:**

```text
read: A
read: B
copy: [x, y]
caught: ClassCastException
```

Phân tích:

- `readOnly` có `@SafeVarargs` và không sửa/làm rò mảng; nó chỉ lấy phần tử đầu trong mỗi `List<String>`. Với các đối số hợp lệ, hành vi an toàn và rõ ràng.
- `snapshot` nhận generic varargs và copy từng phần tử sang `ArrayList` mới; nó **không trả mảng varargs** cho caller.
- `unsafe` có chữ ký varargs generic nhưng lấy alias `Object[]` và thay một `List<String>` bằng `List<Integer>`; runtime check của mảng không phát hiện sai type argument.
- Khi đọc Integer như String, phát sinh `ClassCastException`; catch trong `main` chỉ giúp demo có stdout xác định. **Ứng dụng thật phải sửa nguồn ô nhiễm kiểu**, không nên lấy việc bắt ClassCastException làm biện pháp an toàn.

### 6.1. Vì sao method an toàn vẫn không cần annotation ở mọi trường hợp?

`readOnly` và `snapshot` dùng `@SafeVarargs` vì chúng làm việc với non-reifiable element types trong một bối cảnh cho phép. Nhưng `static void words(String... s)` có phần tử reifiable, compiler không cần cùng mức cảnh báo non-reifiable, nên thông thường **không cần `@SafeVarargs`**.

### 6.2. Cảnh báo trên bản demo là chủ đích

Một lệnh CI như:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs -Werror VarargsLintReviewDemo.java
```

được kỳ vọng **không qua build** vì demo cố ý chứa cảnh báo unsafe. Điều đó minh họa cách `-Werror` cưỡng chế warning, không có nghĩa `javac` sai. Khi triển khai thật, xóa hành vi unsafe hoặc thay API trước khi bật gate, thay vì suppress toàn bộ nhóm warning để “cho qua”.

## 7. Cách review phương thức có `@SafeVarargs`

Annotation chuẩn:

```java
@SafeVarargs
static <T> List<T> snapshot(T... items) {
    List<T> result = new java.util.ArrayList<>();
    for (T item : items) {
        result.add(item);
    }
    return result;
}
```

Đây là **method minh họa**, trong lớp có import List. Lời cam kết hợp lệ ở đây là:

1. Không ghi giá trị sai kiểu vào array `items`.
2. Không trả hoặc lưu tham chiếu `items` cho phần code có thể thao tác không an toàn.
3. Không gọi một method khác được biết là có thể sửa array sai kiểu.
4. Tạo collection mới, đưa từng phần tử sang đó. Caller không nhận một view được backed trực tiếp bởi chính varargs array.

Với mã thực tế, reviewer nên làm **data-flow audit**: từ thời điểm array vào method cho tới mọi nơi nó được đọc, viết, truyền đi, lưu lại hoặc trả về.

### 7.1. Điều kiện được phép gắn annotation

Trên Java 17+, `@SafeVarargs` được phép với:

- **constructor** khai báo varargs;
- phương thức `static`;
- phương thức instance `final`;
- phương thức instance `private` (cho phép từ Java 9).

Các method trên **không thể bị override** theo cách phá vỡ cam kết. Một phương thức instance `public void process(T... args)` không `final`, có thể bị override, không phải nơi hợp lệ để tùy ý gắn `@SafeVarargs`. Annotation cũng không có ý nghĩa trên method không phải varargs.

**Lưu ý lịch sử:** Java 7 giới thiệu `@SafeVarargs`, nhưng việc áp dụng lên phương thức `private` là mở rộng của các phiên bản Java sau. Ví dụ dùng JDK 17+ nên có thể tận dụng quy tắc hiện hành thay vì dạy giới hạn cũ như một giới hạn còn hiệu lực.

### 7.2. Những hành vi cần soi đặc biệt

| Mẫu mã | Câu hỏi review |
| --- | --- |
| `Object[] alias = args;` | Có thao tác ghi qua alias, làm sai kiểu generic không? |
| `args[i] = ...` | Có bảo đảm giá trị phù hợp với loại phần tử ở mọi call site? |
| `return args;` | Có làm array non-reifiable thoát ra ngoài và có thể bị sửa không? |
| `this.saved = args;` | Có lưu một mảng caller có thể sở hữu và sửa về sau không? |
| `otherMethod(args);` | Method khác chỉ đọc hay có thể mutate/retain mảng? |
| `Arrays.asList(args)` | Có trả view backed bởi array trực tiếp cho caller không? |
| `(List<String>[]) raw;` | Cast unchecked dựa vào invariant nào, invariant đó được chứng minh ở đâu? |
| `@SuppressWarnings(...)` | Có che cảnh báo thay vì sửa lỗi, hoặc phạm vi suppress quá rộng không? |

Không phải mọi thao tác như `args[i] = value` đều tự động sai với mọi generic varargs, nhưng **chỉ cần một đường ghi sai kiểu hoặc một đường escape không được kiểm soát** là cam kết `@SafeVarargs` có thể không còn hợp lệ.

### 7.3. Array alias và trách nhiệm với caller

Một caller có thể truyền **mảng đã có**:

```java
String[] originals = {"before"};
someMethod(originals);
```

Với chữ ký `someMethod(String... values)`, method có thể thấy chính array `originals` và mutation có thể ảnh hưởng caller. Do vậy review phải xét **cả lời gọi truyền từng giá trị lẫn lời gọi truyền sẵn mảng**. Đặc biệt nếu method trả view backed bởi array hoặc lưu tham chiếu array, thiết kế cần hợp đồng ownership rõ.

## 8. Cảnh báo `-Xlint:varargs` vẫn đáng chú ý sau @SafeVarargs

Một hiểu lầm phổ biến: “Đã có `@SafeVarargs` thì có thể bỏ qua mọi cảnh báo varargs.” Không đúng.

Ví dụ không nên dùng:

```java
@SafeVarargs
static <T> T[] expose(T... xs) {
    return xs;
}
```

Ở đây tác giả đã tuyên bố an toàn nhưng lại để chính mảng varargs thoát ra. Với kiểu phần tử non-reifiable, việc caller nhận mảng rồi thao tác có thể dẫn tới lỗi kiểu, và compiler có thể phát cảnh báo khi dùng nhóm `-Xlint:varargs`. **Dù một phiên bản compiler không báo ở đúng dòng đó, reviewer vẫn phải kiểm tra ý nghĩa của việc trả mảng.**

Một cách điều chỉnh khi caller cần collection thay vì array:

```java
@SafeVarargs
static <T> List<T> snapshot(T... xs) {
    List<T> copy = new java.util.ArrayList<>(xs.length);
    for (T x : xs) {
        copy.add(x);
    }
    return copy;
}
```

Method minh họa này tạo bản sao **cấu trúc danh sách**, không clone sâu các object bên trong. Nếu element là mutable, cả caller và danh sách mới vẫn tham chiếu cùng object đó. Đảm bảo không làm lộ generic varargs array khác với việc bảo đảm mọi phần tử immutable.

### 8.1. Cẩn thận với `Arrays.asList`

```java
static <T> List<T> viewOf(T... xs) {
    return java.util.Arrays.asList(xs);
}
```

Đoạn minh họa này trả một **list backed bởi array**. Nó không tự động gây lỗi trong mọi trường hợp, nhưng có thể làm mảng varargs bị thay đổi qua list view, tùy caller và kiểu T. Trong phương thức generic varargs, đây là dấu hiệu reviewer phải đánh giá kỹ; không gắn `@SafeVarargs` một cách cơ học.

Nếu thực sự cần một danh sách riêng, `new ArrayList<>(Arrays.asList(xs))` tạo bản sao các phần tử vào một danh sách mới. Hoặc dùng vòng lặp như `snapshot` để ý đồ “không expose array” hiện rõ hơn.

### 8.2. @SafeVarargs có kiểm tra runtime không?

**Không.** Nó không sinh cơ chế runtime bảo vệ `List<String>[]`, không reify `T` và không chặn alias qua `Object[]`. Nó chủ yếu giúp compiler/caller bỏ những cảnh báo cụ thể dựa trên cam kết tác giả, nên cần review càng kỹ khi có annotation.

## 9. Khi nào dùng @SuppressWarnings và dùng thế nào cho có trách nhiệm?

`@SuppressWarnings("unchecked")` là annotation Java hợp lệ cho những thao tác unchecked có lý do cụ thể, nhưng **nó không tương đương `@SafeVarargs`**.

- `@SafeVarargs`: cam kết ở **method/constructor varargs** theo quy tắc của ngôn ngữ, có ảnh hưởng tới cách compiler xử lý cảnh báo tại call site.
- `@SuppressWarnings("unchecked")`: yêu cầu **không hiển thị warning unchecked trong phạm vi được chú thích**; không đưa ra cùng một bảo đảm API cho mọi caller.
- `@SuppressWarnings("varargs")`: có thể được dùng trong các tình huống cụ thể để suppress một cảnh báo varargs đã được chứng minh an toàn, nhưng phải review lý do rất kỹ. Không nên dùng để che cách expose/mutate array nguy hiểm.

Ví dụ phạm vi nhỏ:

```java
static <T> T castFromValidatedBoundary(Object value, Class<T> type) {
    return type.cast(value); // Cast có kiểm tra runtime, không cần unchecked cast.
}
```

Đây là **phương thức minh họa** cho cách **ưu tiên bỏ hẳn unchecked cast** bằng API kiểm tra runtime. Nếu đã có `Class<T>` và dữ liệu phải đúng kiểu, `Class.cast` thường biểu đạt kiểm tra tốt hơn một `(T) value` với type variable bị erased.

Trong những trường hợp không thể thay được một cast unchecked tại ranh giới thư viện/serialization, cần mô tả invariant và thu hẹp suppression tối đa. Ví dụ minh họa một *vùng dữ liệu đã được xác thực bởi một API khác*:

```java
@SuppressWarnings("unchecked")
static <T> List<T> fromTrustedList(Object data) {
    // Chỉ dùng nếu đã có invariant từ bên ngoài rằng:
    // data thực sự là List<T> cho đúng T ở call site.
    return (List<T>) data;
}
```

Snippet trên **không an toàn một cách tự động**; nó chỉ mô tả kỹ thuật suppression. Không thể suy ra `List<T>` bằng cách kiểm tra `data instanceof List<?>`, vì phép kiểm tra đó không chứng minh từng phần tử là T. Code ứng dụng nên có validation thực sự hoặc thiết kế lại API, thay vì đặt tên “Trusted” rồi giả định mọi caller đúng.

**Đối với varargs:** ưu tiên làm phương thức thật sự safe và dùng `@SafeVarargs` trên đúng declaration hợp lệ, thay vì dùng `@SuppressWarnings("unchecked")` trải rộng lên cả class.

## 10. Quy trình triage khi CI xuất hiện cảnh báo varargs/unchecked mới

**Bước 1 — Xác định cảnh báo cụ thể.** Ghi lại file, dòng, mức lint, JDK và vị trí: declaration, callsite hay trong thân method. Nếu warning liên quan generic cast không nằm ở varargs, giải quyết theo đúng nguồn cast, không cố chữa bằng `@SafeVarargs`.

**Bước 2 — Tìm kiểu phần tử varargs.** `String...` hay `List<String>...`? Với `T...`, T bị xóa kiểu thế nào? Điều gì có thể kiểm tra ở runtime?

**Bước 3 — Theo dõi mảng từ đầu vào tới đầu ra.** Tìm `Object[]` alias, `return args`, lưu vào field, truyền cho helper, dùng raw type/unchecked cast và thao tác gán phần tử.

**Bước 4 — Xác định tác động thực tế.** Có thể chèn `List<Integer>` vào nơi được khai báo là `List<String>` không? Có thể làm caller sửa mảng không thuộc sở hữu của mình không? Có thể xuất hiện `ClassCastException` ở nơi khác không?

**Bước 5 — Sửa gốc nếu unsafe.** Bỏ alias và mutation, copy đúng chỗ, dùng collection, đổi chữ ký hoặc phân quyền ownership. **Không bắt `ClassCastException` làm cách xử lý bình thường**.

**Bước 6 — Nếu safe và method không overridable, cân nhắc @SafeVarargs.** Xác nhận method/constructor thuộc nhóm được annotation cho phép; review toàn bộ thân và mọi lời gọi helper. Đừng annotate code chỉ vì build có warning.

**Bước 7 — Bật lại lint để xác nhận.** Dùng cả `-Xlint:unchecked` và `-Xlint:varargs`. Nếu vẫn còn warning, xem đó là trường hợp hợp lệ có invariant rõ hay cần sửa thêm.

**Bước 8 — Thêm test biên.** Lời gọi với một/tất cả phần tử, mảng có sẵn, subtype, kiểu generic lồng nhau, đường lỗi và các đường gọi helper. Test không thay thế review luồng dữ liệu, nhưng giúp phòng regressions.

**Bước 9 — Đánh giá mức độ nợ cảnh báo.** Nếu project hiện có warning cũ, cần kế hoạch xử lý từng nhóm/đường đi thay vì suppress toàn cục. Có thể chỉ áp `-Werror` cho module hoặc đợt code đã được làm sạch để không khóa công việc vì warnings không liên quan.

**Bước 10 — Ghi ngắn quyết định review.** “Safe vì chỉ đọc, không mutate/escape, gọi helper X không giữ array” hữu ích hơn “add @SafeVarargs to silence warning”.

## 11. Trường hợp sửa bằng cách bỏ generic varargs

Khi API bản chất nhận một collection, chữ ký:

```java
static void handleGroups(List<List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

thường rõ ràng hơn `List<String>...` và **không phải tạo mảng varargs có phần tử non-reifiable**. Phương thức này là snippet minh họa, không có `main`.

Caller Java 17+ có thể dùng:

```java
handleGroups(List.of(
        List.of("a", "b"),
        List.of("c")));
```

Cần phân biệt: API `List<List<String>>` không bảo đảm dữ liệu chưa từng bị heap pollution từ chỗ khác, nhưng nó **loại bỏ đúng một đường rủi ro** liên quan tới generic varargs array.

Nếu caller muốn cú pháp truyền nhiều đối số rời rạc, một helper `@SafeVarargs` thật sự safe vẫn có thể là thiết kế tốt. Không có quy tắc “mọi generic varargs đều xấu”; lựa chọn dựa trên semantics và invariant.

### 11.1. Tránh cast array generic để thỏa chữ ký

Phương thức sau không phải cách sửa được khuyến khích:

```java
@SuppressWarnings("unchecked")
static List<String>[] makeGroups(int n) {
    return (List<String>[]) new List<?>[n];
}
```

Đây là ví dụ **unsafe design**: việc cast không kiểm tra được `String` bên trong danh sách. Nó có thể làm compiler im lặng nhưng không tạo runtime check tương đương `List<String>[]` thật. Nếu cần chứa nhiều nhóm, dùng `List<List<String>>`. Nếu bài toán thật sự yêu cầu mảng có component reifiable, dùng một kiểu thành phần reifiable phù hợp và thiết kế kiểm tra explicit.

### 11.2. Lưu dữ liệu dài hạn: copy hay giữ tham chiếu?

Nếu method chỉ cần duyệt rồi kết thúc, không cần lưu mảng. Nếu cần lưu danh sách lâu dài, hãy copy theo hợp đồng, ví dụ tạo `ArrayList` mới. Tuy nhiên **copy cấu trúc** không biến tất cả object bên trong thành immutable. Nếu phần tử mutable và caller tiếp tục sửa chúng, cần thiết kế deep-copy hoặc ownership riêng tùy nghiệp vụ; điều đó không được `@SafeVarargs` giải quyết.

## 12. Lint trong IDE, build và CI: một quy ước có thể áp dụng lâu dài

Một quy trình khả thi cho nhóm Java:

1. **Cùng một JDK toolchain và release mục tiêu** giữa local và CI. Lệnh ví dụ dùng `--release 17`; không giả định mọi JDK đều phát warning với nguyên văn giống nhau.
2. **Đảm bảo compiler thực sự bật cảnh báo**, không chỉ bật một checkbox của IDE mà build không dùng. Với `javac` có thể chạy bằng hai flag đã nêu.
3. **Ưu tiên warning mới trong diff**: không để code mới đưa vào `unsafe varargs` mà không có giải thích.
4. **Có chính sách `@SafeVarargs` trong code review**: reviewer phải kiểm tra nguyên mảng, các lời gọi thứ cấp và cách trả dữ liệu.
5. **Chỉ suppress có mục đích**: vị trí nhỏ nhất, có invariant, có test đủ mạnh; không mặc định suppress cả file/module.
6. **Thực thi gate hợp lý**: `-Werror` khi nhóm đã kiểm soát warning hoặc ở module yêu cầu nghiêm ngặt; không bật trên toàn hệ thống rồi lập tức triệt tiêu mọi warning để build xanh.
7. **Lưu lại output build** khi warning mới xuất hiện; nó giúp đối chiếu category, file, dòng và thay đổi JDK.
8. **Review code sau refactor**: chỉ một helper mới, việc chuyển array vào field hoặc thay `Arrays.asList` thành return view có thể phá cam kết cũ dù annotation không thay đổi.

### 12.1. Ma trận quyết định khi xử lý warning

| Tình huống trong code | Hành động khuyến nghị |
| --- | --- |
| `String...`, không dùng generic non-reifiable | Thường dùng trực tiếp, không cần @SafeVarargs |
| `List<String>...` chỉ đọc, không làm lộ array, method static/final/private | Có thể chứng minh an toàn rồi dùng @SafeVarargs |
| Method ghi qua `Object[]` alias khiến generic type sai | **Sửa mã**, loại bỏ thao tác unsafe |
| Method trả `T[]` non-reifiable cho caller không kiểm soát | Xem lại API, tránh array escape, cân nhắc collection/copy |
| Method có generic unchecked cast không liên quan varargs | Không dùng @SafeVarargs để chữa; xử lý cast hoặc kiểm tra runtime |
| API nhận nhiều nhóm như dữ liệu động | Ưu tiên Collection/List nếu đúng semantics |
| Có warning nhưng chưa rõ nguồn | Giữ warning, điều tra trước khi annotate/suppress |
| Cần suppression ở boundary đã kiểm chứng | Giới hạn phạm vi, ghi invariant, test và review thường xuyên |

## 13. Phân biệt warning với lỗi compile-time và lỗi runtime

| Dạng tín hiệu | Ví dụ | Có chạy được không? | Điều cần làm |
| --- | --- | --- | --- |
| **Unchecked warning** | `List<String>...` và compiler tạo generic array tại callsite | Thường vẫn biên dịch và chạy nếu không bật `-Werror` | Review luồng dữ liệu và chứng minh/sửa safety |
| **Varargs warning** | Expose tham số varargs dù đã gắn @SafeVarargs | Thường là warning, tùy mã/flag | Review array escape và annotation |
| **Compile-time error** | `new List<String>[2]` | Không | Dùng collection hoặc kiểu reifiable phù hợp |
| **Compile-time error** | Gắn @SafeVarargs lên method instance overridable không hợp lệ | Không | Đổi thiết kế/cú pháp, không xóa annotation một cách thiếu review |
| **Runtime ArrayStoreException** | Ghi Integer vào `String[]` | Phương thức chạy tới chỗ ghi rồi lỗi | Sửa phép ghi sai runtime component |
| **Runtime ClassCastException** | Sau heap pollution, đọc Integer như String | Có thể xuất hiện muộn hơn | Sửa chỗ làm ô nhiễm generic type |

**Cảnh báo không phải exception.** Nó không được bắt bằng `try/catch` khi chương trình chạy. Ngược lại, một method có thể gây ClassCastException dù compiler không cảnh báo, nếu hành vi unsafe nằm sau một suppression hoặc phía bên kia ranh giới không kiểm soát.

## 14. Những sai lầm thường gặp khi “dọn warning”

**Sai lầm 1 — Tắt `-Xlint:unchecked` để thấy build sạch.** Warning biến mất khỏi log, rủi ro heap pollution không tự biến mất.

**Sai lầm 2 — Gắn `@SafeVarargs` lên mọi method có dấu `...`.** Annotation dành cho những trường hợp và vị trí hợp lệ; với reifiable `String...` thường không cần. Dùng sai cho method unsafe có thể che cảnh báo tại call site.

**Sai lầm 3 — Nghĩ warning ở callsite là lỗi của caller hoàn toàn.** Tác giả method cũng có trách nhiệm thiết kế xử lý array an toàn. Review cả hai phía.

**Sai lầm 4 — Nghĩ warning ở declaration chứng minh method chắc chắn ném ClassCastException.** Cảnh báo chỉ phản ánh rủi ro kiểu non-reifiable; một method chỉ đọc có thể safe.

**Sai lầm 5 — Dùng `@SuppressWarnings("unchecked")` ở cả class.** Phạm vi quá rộng có thể che các unchecked cast không liên quan và các warning mới được thêm về sau.

**Sai lầm 6 — Bỏ qua `-Xlint:varargs` sau khi có @SafeVarargs.** Một array có thể vẫn bị trả/lưu/truyền đi không an toàn; annotation không phải công cụ chứng minh.

**Sai lầm 7 — Chỉ test lời gọi với các đối số riêng lẻ.** Caller có thể truyền mảng sẵn có; cần xem hợp đồng mutation và ownership.

**Sai lầm 8 — Cho rằng `Arrays.asList(args)` đã copy mảng.** Nó tạo list view backed bởi mảng; trả view có thể khiến array bị sửa ở nơi khác.

**Sai lầm 9 — Sửa warning bằng raw type hoặc cast unchecked không chứng minh.** Nó chỉ dời rủi ro đến runtime; cần tìm cách thể hiện đúng kiểu dữ liệu.

**Sai lầm 10 — Bắt `ClassCastException` thay vì sửa heap pollution.** Khi đọc lỗi xuất hiện, dữ liệu đã bị sai kiểu từ trước; cần tìm và loại bỏ nguồn.

**Sai lầm 11 — Cho rằng `-Werror` tương đương static analysis đầy đủ.** Nó giúp cưỡng chế các warning compiler biết, không đảm bảo mọi API dùng varargs an toàn.

**Sai lầm 12 — Xóa cảnh báo sau khi JDK nâng cấp mà không đọc nội dung mới.** Một loại warning hoặc kiểm tra mới có thể chỉ ra lỗi trước đó chưa được bắt gặp.

## 15. Checklist review PR có generic varargs

Áp dụng cho một PR sửa hoặc bổ sung method dùng `T...`, `List<X>...` hoặc tương tự:

- [ ] Chạy compiler với `-Xlint:unchecked` và `-Xlint:varargs` ở JDK/release mục tiêu.
- [ ] Ghi rõ warning ở declaration, call site hay trong thân method.
- [ ] Hiểu kiểu phần tử là reifiable hay non-reifiable.
- [ ] Xác định runtime component type của mảng được tạo khi gọi varargs.
- [ ] Không có write sai kiểu qua `Object[]` hoặc raw alias.
- [ ] Không có cast unchecked chưa chứng minh invariant.
- [ ] Không có array escape qua return, field, callback hoặc method khác không được kiểm soát.
- [ ] Các lệnh gọi helper từ method đã được review về mutation/retention.
- [ ] Đã xem caller có thể truyền mảng sẵn có; không vô tình làm thay đổi dữ liệu caller.
- [ ] Nếu có `@SafeVarargs`, method/constructor ở vị trí cho phép và implementation **thực sự safe**.
- [ ] Nếu có `@SuppressWarnings`, phạm vi nhỏ nhất với lý do có thể kiểm chứng.
- [ ] Đã cân nhắc collection hoặc copy thay cho generic varargs array nếu phù hợp.
- [ ] Test có dữ liệu nested generic, ranh giới và đường lỗi; không chỉ happy path.
- [ ] Không đưa warning mới vào CI mà không có đánh giá và quyết định rõ.

Checklist này là công cụ review, không thay thế kiểm tra toàn bộ bất biến về dữ liệu và quyền sở hữu. Một ô được tick “đã xem” không chứng minh code an toàn nếu kết luận không có cơ sở.

## 16. Câu hỏi tự đánh giá

**1.** Vì sao `static void f(List<String>... groups)` có thể phát warning dù compiler cho phép biên dịch? — Vì generic type argument `String` của `List<String>` là non-reifiable; mảng varargs runtime không thể kiểm tra kiểu tham số đó đầy đủ.

**2.** Khác nhau giữa `-Xlint:unchecked` và `-Xlint:varargs` là gì? — Nhóm unchecked tập trung vào các thao tác không kiểm tra đầy đủ, bao gồm declaration/callsite generic varargs; nhóm varargs có thể nhấn mạnh các thao tác có nguy cơ trên tham số varargs trong implementation.

**3.** @SafeVarargs có làm runtime biết mảng là `List<String>[]` đầy đủ không? — **Không**. Annotation không thay đổi type erasure và không chặn heap pollution.

**4.** Khi gặp warning về `List<String>...`, có nên sửa ngay thành `@SafeVarargs` mà không đọc thân method? — **Không**. Cần xem mutation, array escape, helper calls và chứng minh an toàn.

**5.** `Object[] a = groups; a[0] = List.of(42);` có bắt buộc ném ArrayStoreException với runtime `List[]` không? — **Không**. Cả `List<Integer>` lẫn `List<String>` đều là List ở runtime, nên lỗi có thể xuất hiện muộn dưới dạng ClassCastException.

**6.** Vì sao `new List<String>[2]` không biên dịch được? — Vì tạo array với component generic non-reifiable không thể được kiểm tra runtime đầy đủ.

**7.** Có thể dùng `@SafeVarargs` cho method instance `private` trên Java 17 không? — **Có**, nếu thực sự safe. Quy tắc cho phép vị trí này từ Java 9.

**8.** Có nên đặt `@SuppressWarnings("unchecked")` trên toàn bộ package để chặn warning? — **Không**. Tối thiểu hóa phạm vi suppression và chứng minh invariant của thao tác.

**9.** `-Werror` làm gì? — Chuyển compiler warning thành build error theo cấu hình; nó không tự sửa hoặc chứng minh an toàn mã nguồn.

**10.** `Arrays.asList(args)` có luôn là snapshot độc lập của generic varargs array không? — **Không**; đó là view backed bởi array. Muốn bản sao, cần copy có chủ đích.

**11.** Khi nào chuyển `List<String>...` sang `List<List<String>>`? — Khi đầu vào bản chất là tập các nhóm, API không cần cú pháp varargs và muốn tránh mảng generic non-reifiable.

**12.** Nếu đoạn mã đã có @SafeVarargs vẫn gây `ClassCastException` sau thao tác ghi qua `Object[]`, phải làm gì? — Sửa thao tác không an toàn và review lại annotation; không dựa vào try/catch để che lỗi.

## Tài liệu chính thức còn áp dụng

- [Java Language Specification 17 §8.4.1 — Formal Parameters / Variable Arity](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): cú pháp varargs và các cảnh báo liên quan kiểu non-reifiable.
- [Java Language Specification 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): mô hình xóa kiểu generic.
- [Java Language Specification 17 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): kiểu có thể được kiểm tra runtime.
- [Java Language Specification 17 §9.6.4.7 — @SafeVarargs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): ý nghĩa và điều kiện sử dụng annotation.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): cam kết về việc dùng non-reifiable varargs.
- [Java SE 17 javac documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint:unchecked`, `-Xlint:varargs`, `-Werror` và `--release`.
- [Java SE 17 API — Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): view backed bởi array, giúp phân biệt với snapshot/copy.

**Ghi nhớ:** **Dùng warning `unchecked` và `varargs` như tín hiệu kiểm tra thiết kế**, không tắt đi bằng phản xạ. Varargs được biểu diễn bằng mảng; generic type argument bị erasure; vì vậy `List<String>...` cần kiểm soát mutation, alias và escape. Chỉ dùng `@SafeVarargs` sau khi chứng minh method an toàn, và chọn `List/Collection` khi đó mới là cấu trúc dữ liệu phù hợp.