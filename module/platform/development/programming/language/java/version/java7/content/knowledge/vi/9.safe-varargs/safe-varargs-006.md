# Kiểm tra điều kiện sử dụng annotation theo mức ngôn ngữ — `@SafeVarargs`

## 1. Bối cảnh: cùng một annotation nhưng không phải phiên bản Java nào cũng cho dùng ở cùng vị trí

`@SafeVarargs` được giới thiệu từ **Java 7** nhằm hỗ trợ các phương thức hoặc constructor có **varargs với kiểu phần tử không reifiable**, thường là generic, ví dụ `List<String>...` hay `T...`. Annotation này là một **cam kết của người viết thư viện** rằng phần thân phương thức/constructor không thực hiện các thao tác khiến tham số varargs bị sử dụng không an toàn.

Tuy nhiên, **điều kiện được phép đặt `@SafeVarargs` phụ thuộc mức ngôn ngữ Java**:

- **Java 7 và Java 8:** được áp dụng cho **constructor có varargs**, **phương thức `static` có varargs**, và **phương thức `final` có varargs**.
- **Java 9 trở đi:** ngoài ba trường hợp trên, được phép đặt trên **phương thức instance `private` có varargs**, kể cả không khai báo `final`.
- **Mọi mức ngôn ngữ đang xét:** không được đặt trên phương thức/constructor **không có varargs**; không được đặt trên phương thức instance có thể bị override như phương thức `public`/`protected` thông thường không `final`.

Đây là **quy tắc kiểm tra tại thời điểm biên dịch**, không phải tính năng runtime được bật/tắt khi chương trình chạy. Một đoạn code có thể hợp lệ khi biên dịch với `javac --release 17` nhưng bị từ chối với `javac --release 8`, dù đang sử dụng cùng một JDK để chạy compiler.

Điểm quan trọng nhất của bài: **kiểm tra cả (1) varargs thật, (2) vị trí được phép annotate theo mức ngôn ngữ, và (3) tính an toàn thực tế**. Đủ điều kiện cú pháp **không** tự động chứng minh rằng cách xử lý varargs là an toàn.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt `T... items` (varargs) với `T[] items` hoặc `List<T> items` (khai báo fixed-arity).
2. Biết chính xác khi nào `@SafeVarargs` hợp lệ với constructor, `static`, `final` và `private`.
3. Giải thích thay đổi từ **Java 9** và kiểm chứng bằng `javac --release 8` so với `javac --release 9`.
4. Phân biệt **compile error** do vi phạm điều kiện áp dụng, **unchecked warning** do generic varargs, **redundant annotation warning**, và **lỗi runtime** do heap pollution.
5. Hiểu phạm vi suppress warning của `@SafeVarargs` khác `@SuppressWarnings("unchecked")`.
6. Review mã nguồn Java 17+ theo quy tắc hiện hành, không trộn điều kiện cũ của Java 7/8 vào mọi dự án.

**Lưu ý về Special Note của module:** Các ví dụ chính dùng Java 17+ và JLS/API hiện hành. Quy tắc Java 7/8 chỉ được nhắc đến để kiểm tra **tính tương thích source level** khi đọc mã hoặc cấu hình toolchain, không được dùng như hướng dẫn cố định cho code mới.

## 2. `@SafeVarargs` là gì và nó tác động đến đâu?

Kiểu annotation được khai báo trong `java.lang`:

~~~java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.CONSTRUCTOR, ElementType.METHOD})
public @interface SafeVarargs {}
~~~

Đây là **mô tả ý nghĩa khai báo**, không phải một file Java độc lập và không cần sao chép định nghĩa này vào dự án. `SafeVarargs` đã có sẵn trong Java; `@Target` cho biết annotation dành cho **constructor** hoặc **method**, không dành cho field, class, biến cục bộ hay parameter riêng lẻ.

Theo [Java SE 26 API — SafeVarargs](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/SafeVarargs.html), annotation đưa ra lời khẳng định của lập trình viên về việc phương thức/constructor không sử dụng tham số varargs theo cách có thể không an toàn. Nó giúp compiler không báo một số **unchecked warning** liên quan tới khai báo và lời gọi varargs với loại phần tử **không reifiable**.

Ví dụ phương thức generic:

~~~java
@SafeVarargs
public static <T> List<T> copy(T... values) {
    List<T> result = new ArrayList<>();
    Collections.addAll(result, values);
    return result;
}
~~~

Đây là **đoạn phương thức**, không phải chương trình chạy độc lập; cần các import `java.util.*` phù hợp. Phương thức:

- Có `T... values` nên là **variable-arity method**.
- Có modifier `static` nên được phép mang `@SafeVarargs` từ Java 7.
- Chỉ **đọc** các phần tử và sao chép sang collection có kiểu `T`; không dùng alias `Object[]` để nhét kiểu khác vào mảng varargs, không trả trực tiếp hoặc lưu tham chiếu mảng varargs cho mã không đáng tin chỉnh sửa.
- Có thể được gọi như `copy("A", "B")`, với compiler suy luận `T = String`.

**Phân biệt “được phép annotate” và “thực sự an toàn”:** Compiler kiểm tra các **điều kiện cú pháp/vị trí** nêu ở các mục sau; nó không chứng minh toàn bộ logic nội bộ là type-safe. `@SafeVarargs` không thay thế review, test và kiểm tra bất biến của API.

## 3. Ma trận điều kiện theo phiên bản Java

Bảng dưới đây là trọng tâm của bài. Trong mỗi trường hợp, giả sử tham số cuối là một varargs hợp lệ, chẳng hạn `List<T>... groups`.

| Loại khai báo | Java 7 | Java 8 | Java 9+ | Vì sao |
| --- | --- | --- | --- | --- |
| Constructor có varargs | **Hợp lệ** | **Hợp lệ** | **Hợp lệ** | Constructor không bị override |
| Phương thức `static` có varargs | **Hợp lệ** | **Hợp lệ** | **Hợp lệ** | Static method không bị override theo đa hình |
| Phương thức instance `final` có varargs | **Hợp lệ** | **Hợp lệ** | **Hợp lệ** | Không thể override |
| Phương thức instance `private` **không `final`** có varargs | **Không hợp lệ** | **Không hợp lệ** | **Hợp lệ** | Java 9 mở rộng quy tắc sang private instance method |
| Phương thức instance `public`/`protected` không `final` có varargs | **Không hợp lệ** | **Không hợp lệ** | **Không hợp lệ** | Có khả năng bị override |
| Phương thức `abstract` có varargs | **Không hợp lệ** | **Không hợp lệ** | **Không hợp lệ** | Không thuộc loại static/final/private hợp lệ |
| Phương thức `default` trong interface có varargs | Chưa có cú pháp default method | **Không hợp lệ** nếu chỉ là default, không private/static | **Không hợp lệ** nếu chỉ là default | Default interface method có thể bị override |
| Phương thức `static` trong interface có varargs | Chưa có cú pháp static interface method | **Hợp lệ** | **Hợp lệ** | Java 8+ cho phép static method trong interface |
| Khai báo **không có `...`** | **Không hợp lệ** | **Không hợp lệ** | **Không hợp lệ** | Không phải varargs |
| Dùng annotation trên class, field hoặc local variable | **Không hợp lệ** | **Không hợp lệ** | **Không hợp lệ** | Không thuộc `@Target({CONSTRUCTOR, METHOD})` |

Các trường hợp “chưa có cú pháp” phản ánh sự khác biệt **của chính mức ngôn ngữ**. Không diễn giải bảng như thể cú pháp interface Java 8 đã tồn tại ở Java 7.

### 3.1. Quy tắc chính xác ở Java hiện hành

Theo [JLS Java SE 26 §9.6.4.7](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.6.4.7), compiler phải từ chối khi:

1. Một **fixed-arity method hoặc constructor** có `@SafeVarargs`.
2. Một **variable-arity instance method** có `@SafeVarargs` nhưng **không phải `static`, không `final` và không `private`**.

Constructor là trường hợp riêng: không yêu cầu hay có thể khai báo `static`/`final` cho constructor. Kiểm tra “static/final/private” ở điều kiện thứ hai áp dụng cho **method**.

### 3.2. Vì sao có giới hạn “không bị override”?

`@SafeVarargs` có tác động vượt ra ngoài method body, vì nó ảnh hưởng tới cảnh báo ở **điểm gọi phương thức**. Nếu một instance method còn có thể được override, một subclass có thể triển khai logic khác, thậm chí không an toàn. Annotation trên method ở lớp cha không thể bảo đảm an toàn của mọi implementation có thể xuất hiện qua dynamic dispatch.

- Method `static` bị *hiding*, không bị override theo ngữ nghĩa instance dispatch.
- Method `final` không thể bị override.
- Method `private` không tham gia overriding theo cách ấy.
- Constructor không bị override.

Java 9 đã thừa nhận thêm trường hợp `private` vào điều kiện hợp lệ. Điều này **không có nghĩa** Java 7/8 vốn đã cho phép `@SafeVarargs` trên mọi private instance method.

### 3.3. Một bẫy: class `final` không thay thế modifier `final` của method

Xét:

~~~java
public final class Example {
    @SafeVarargs
    public <T> void take(List<T>... values) { }
}
~~~

Đây là **đoạn cố ý không biên dịch** (giả sử đã import `List`). Dù class là `final` nên không có subclass nào override được, JLS yêu cầu chính **method** có modifier `static`, `final` hoặc `private`; việc *class* là `final` không đáp ứng điều kiện cú pháp ấy.

Nếu an toàn về logic và cần dùng annotation, có thể sửa method thành `public final <T> void take(...)`, hoặc chuyển thành `static`/`private` nếu thiết kế API cho phép. Không thêm modifier chỉ để che warning khi method thực tế còn thao tác không an toàn.

## 4. Phân biệt varargs thực với tham số mảng và collection

Điều kiện đầu tiên là khai báo phải thực sự là **variable arity**, nhận biết qua dấu ba chấm `...` ở **tham số cuối cùng**.

| Khai báo | Có varargs? | Có thể dùng `@SafeVarargs` nếu loại method hợp lệ? |
| --- | --- | --- |
| `static <T> void f(T... xs)` | **Có** | **Có**, nếu phần thân an toàn |
| `static void f(List<String>... xs)` | **Có** | **Có**, nếu phần thân an toàn |
| `static void f(String... xs)` | **Có** | **Có về cú pháp**, nhưng có thể bị cảnh báo annotation thừa |
| `static void f(String[] xs)` | **Không** | **Không**, dù tham số runtime là array |
| `static void f(List<String>[] xs)` | **Không** | **Không**, đây là fixed-arity array parameter |
| `static void f(List<String> xs)` | **Không** | **Không**, là một collection |
| `static void f(int count, T... xs)` | **Có** | **Có**, vì `T... xs` ở cuối |
| `static void f(T... xs, int count)` | **Không hợp lệ** | Bản thân khai báo varargs sai vì varargs không ở cuối |

**Phân biệt type và syntax:** Một varargs parameter được biểu diễn bằng array ở runtime, nhưng khai báo `T[]` **không tự biến thành varargs**. `@SafeVarargs` yêu cầu cú pháp variable-arity ở declaration, không chỉ yêu cầu một biến kiểu array.

### 4.1. Ví dụ lỗi compiler nếu không có dấu ba chấm

File `InvalidFixedArity.java` — **cố ý không biên dịch**:

~~~java
import java.util.List;

public class InvalidFixedArity {
    @SafeVarargs
    public static void take(List<String> values) { }
}
~~~

~~~bash
javac --release 17 InvalidFixedArity.java
~~~

**Kết quả:** Compile error, vì `take(List<String>)` là fixed-arity method. Nó đã là `static` nhưng **static không thể bù cho việc thiếu varargs**. Kết quả này được kiểm chứng bằng `javac` trên JDK 24 ở chế độ `--release 17`; nội dung thông báo lỗi có thể khác trên các compiler khác.

### 4.2. Tại sao không gắn `@SafeVarargs` mọi nơi cho nhất quán?

`@SafeVarargs` không phải annotation trang trí. Nó thông báo với compiler rằng lập trình viên đã kiểm tra an toàn kiểu trong xử lý một **non-reifiable varargs array**. Gắn vào method không varargs gây lỗi; gắn vào method có tham số `String...` có thể hợp lệ nhưng không giúp giảm cảnh báo generic varargs nào cả.

Nếu API đã nhận `Collection<T>` hoặc `List<T>` và không có nhu cầu varargs, **đừng chuyển nó thành `T...` chỉ để được dùng annotation**. Chọn chữ ký API theo cách caller sử dụng và theo an toàn kiểu, không theo nhu cầu che diagnostic.

## 5. Vì sao generic varargs thường có `unchecked warning`?

Java dùng **type erasure** cho phần lớn generic type arguments. Một kiểu như `List<String>` không reifiable đầy đủ ở runtime; trong khi varargs được triển khai bằng array. Tương tác giữa array, erasure và generic type khiến compiler phải cảnh báo rủi ro về **heap pollution**.

Ví dụ khai báo:

~~~java
static void inspect(List<String>... groups) {
    System.out.println(groups.length);
}
~~~

Đây là **đoạn phương thức minh họa** cần import `List`. Khi biên dịch với `-Xlint:unchecked`, compiler thường cảnh báo việc khai báo varargs có phần tử kiểu `List<String>` có thể gây heap pollution. Lời gọi như:

~~~java
inspect(List.of("a"));
~~~

cũng có thể gây cảnh báo về việc tạo generic array cho varargs argument. `List.of` là API Java 9+; đoạn minh họa nhắm Java 17+, không phải tính năng Java 7.

**Một phương thức có thể hoạt động an toàn về mặt logic mà vẫn phát sinh cảnh báo:** compiler không phải lúc nào cũng chứng minh được toàn bộ method body không sửa mảng theo cách không an toàn hoặc không làm alias của mảng thoát ra. `@SafeVarargs` là cơ chế để tác giả API **cam kết** sau khi đã review.

### 5.1. Thế nào là reifiable?

Một số kiểu có đủ thông tin ở runtime để tương tác với array mà không có cảnh báo generic varargs tương ứng, ví dụ `String`, `Object` và kiểu nguyên thủy. Trái lại, `List<String>` hoặc một type variable `T` thông thường **không reifiable**.

Do đó:

~~~java
@SafeVarargs
static void log(String... values) {
    System.out.println(values.length);
}
~~~

là **hợp lệ về điều kiện cú pháp**, nhưng compiler được khuyến khích cảnh báo **redundant SafeVarargs annotation**, vì phần tử `String` đã reifiable. Đây là **warning**, không phải lý do bắt buộc từ chối khai báo. Thực tế với `javac --release 17 -Xlint:varargs`, chương trình trên xuất hiện cảnh báo redundant.

**Chỉ dùng annotation khi có vấn đề generic varargs thật sự để giải quyết.** Trường hợp kiểu phần tử an toàn sẵn không cần annotate.

## 6. Ví dụ hoàn chỉnh Java 17+: constructor, static, final và private

Tạo file `SafeVarargsCasesDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SafeVarargsCasesDemo {
    final int stored;

    @SafeVarargs
    public <T> SafeVarargsCasesDemo(List<? extends T>... groups) {
        int count = 0;
        for (List<? extends T> group : groups) {
            count += group.size();
        }
        stored = count;
    }

    @SafeVarargs
    public static <T> List<T> copy(T... items) {
        List<T> result = new ArrayList<>();
        Collections.addAll(result, items);
        return result;
    }

    @SafeVarargs
    public final <T> List<T> snapshot(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return result;
    }

    @SafeVarargs
    private <T> int count(List<? extends T>... groups) {
        int result = 0;
        for (List<? extends T> group : groups) {
            result += group.size();
        }
        return result;
    }

    public int privateCount() {
        return count(List.of("one"), List.of("two", "three"));
    }

    public static void main(String[] args) {
        SafeVarargsCasesDemo demo = new SafeVarargsCasesDemo(
                List.of(1), List.of(2, 3));

        System.out.println("copy=" + copy("A", "B"));
        System.out.println("constructor=" + demo.stored);
        System.out.println("final=" +
                demo.snapshot(List.of("x"), List.of("y", "z")));
        System.out.println("private=" + demo.privateCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:unchecked SafeVarargsCasesDemo.java
java SafeVarargsCasesDemo
~~~

Stdout đã kiểm chứng:

~~~text
copy=[A, B]
constructor=3
final=[x, y, z]
private=3
~~~

Phân tích từng vị trí:

1. **Constructor `SafeVarargsCasesDemo(List<? extends T>... groups)`:** constructor có varargs nên được phép annotate. Nó chỉ duyệt các group và đếm phần tử.
2. **Method `static copy(T... items)`:** được phép từ Java 7. Nó tạo `ArrayList<T>` và sao chép phần tử, không ghi vào array varargs hay làm array thoát ra cho caller chỉnh sửa.
3. **Method instance `final snapshot(...)`:** được phép từ Java 7. Nó sao chép dữ liệu vào collection mới; method không bị override.
4. **Method instance `private count(...)`:** được phép annotate ở Java 9+ ngay cả không ghi `final`. Nó chỉ đọc độ dài các danh sách.
5. `List.of(...)` là API Java **9+** và chương trình được kiểm tra ở `--release 17`. Không thể dùng nguyên văn chương trình này để kiểm thử source level Java 7/8.
6. Không có chuyện annotation tự làm các list bất biến; sự an toàn của ví dụ đến từ **phần thân không làm hỏng mảng hoặc ép kiểu sai**. Code này dùng các collection mới và thao tác đọc hợp lệ.

### 6.1. Cách viết tương thích source level Java 7/8

Nếu bắt buộc phát hành thư viện cho Java 7/8, dùng constructor, static method hoặc final instance method và chỉ dùng API được mức ngôn ngữ/thư viện mục tiêu hỗ trợ. Ví dụ trong Java 7:

~~~java
@SafeVarargs
public static <T> java.util.List<T> copy(T... values) {
    java.util.List<T> result = new java.util.ArrayList<T>();
    java.util.Collections.addAll(result, values);
    return result;
}
~~~

Đây là **phương thức minh họa**, không phải chương trình độc lập. Nó cho thấy vị trí annotation hợp lệ từ Java 7. Với code Java hiện hành, có thể dùng diamond, `List.of` và những API mới hơn nếu dự án hỗ trợ; không buộc code mới phải dùng cú pháp cũ. Điểm cần kiểm chứng là **source compatibility**, không phải sao chép toàn bộ phong cách Java 7.

## 7. So sánh trực tiếp `--release 8` và `--release 9` cho method `private`

Đây là phép thử quan trọng nhất để phân biệt hai mức ngôn ngữ. Cùng một file có thể được biên dịch với hai mức release khác nhau.

Tạo file `PrivateEligibilityDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;

public class PrivateEligibilityDemo {
    @SafeVarargs
    private <T> int size(List<T>... groups) {
        int total = 0;
        for (List<T> group : groups) {
            total += group.size();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(new PrivateEligibilityDemo()
                .size(Arrays.asList("a"), Arrays.asList("b", "c")));
    }
}
~~~

### 7.1. Biên dịch ở source level Java 8

~~~bash
javac --release 8 PrivateEligibilityDemo.java
~~~

**Kết quả:** **Lỗi biên dịch**. Với Java 8, một `private` instance method chưa `final` không thuộc các trường hợp được phép gắn `@SafeVarargs`. Trong lần kiểm thử với JDK 24, compiler báo ý nghĩa tương đương “invalid SafeVarargs annotation; instance method is not final”.

Các warning riêng về tùy chọn release cũ (nếu toolchain phát sinh) **không làm thay đổi lý do chính của compile error**. Văn bản diagnostic và số dòng không phải stdout chuẩn để so sánh từng ký tự.

### 7.2. Biên dịch ở source level Java 9

~~~bash
javac --release 9 PrivateEligibilityDemo.java
java PrivateEligibilityDemo
~~~

Stdout:

~~~text
3
~~~

Cùng một phương thức `private` bây giờ **hợp lệ**, vì Java 9 đã mở rộng điều kiện của `@SafeVarargs`. `Arrays.asList` là API phù hợp cho phép thử này trên cả Java 8 và Java 9, nên **khác biệt nằm ở quy tắc annotation**, không phải ở việc vô tình gọi một API mới.

**Quan trọng về môi trường:** `--release N` chỉ có tác dụng với các release mà **JDK đang dùng để biên dịch thực sự hỗ trợ**. Hãy chạy `javac --help` để xem những release có thể chọn. Nếu JDK hiện hành đã bỏ hỗ trợ biên dịch tới một release quá cũ, dùng toolchain/JDK riêng thích hợp để kiểm chứng, không bỏ `--release` rồi kết luận code tương thích.

### 7.3. Mục đích của `--release`

Khi chọn `--release 8`, `javac` áp dụng ngôn ngữ và API công khai tương ứng với release 8 (trong giới hạn compiler hỗ trợ), thay vì chỉ đặt target classfile version. Nó giúp phát hiện các cú pháp/method API chỉ xuất hiện ở bản mới.

- `javac --release 8 ...`: kiểm tra điều kiện annotation trước Java 9.
- `javac --release 9 ...`: kiểm tra việc private instance method đã được phép.
- `javac --release 17 ...`: phù hợp ví dụ học tập và nhiều dự án Java 17+.
- Khi phát hành thư viện, hãy dùng **minimum Java version mà người tiêu dùng thực sự cần hỗ trợ**, không chỉ version đang chạy trên máy lập trình viên.

Không nhầm `--release` với một chế độ kiểm tra runtime. Compiler quyết định annotation hợp lệ **ngay khi biên dịch source**.

## 8. Ba tình huống compiler phải từ chối

### 8.1. Method instance có thể bị override

Tạo `InvalidOverrideable.java` — **cố ý không biên dịch**:

~~~java
import java.util.List;

public class InvalidOverrideable {
    @SafeVarargs
    public <T> void take(List<T>... groups) { }
}
~~~

~~~bash
javac --release 17 InvalidOverrideable.java
~~~

Dù có varargs, method `take` không `static`, không `final`, không `private`, nên compile error. Không được giả định mọi public method có varargs đều được annotate. Nếu là API cần override, **không dùng `@SafeVarargs`** ở method đó. Cân nhắc thay chữ ký API bằng `Collection`/`List` nếu muốn tránh các vấn đề generic varargs, hoặc chỉ gắn annotation ở helper hợp lệ mà thực sự an toàn.

### 8.2. Method fixed-arity

File `InvalidFixedArity.java` ở mục 4 đã minh họa trường hợp `@SafeVarargs` trên method không có dấu `...`. Nó bị compiler từ chối ở mọi mức release đang xét. Hãy xem chính chữ ký method, không chỉ kiểu array của nó sau erasure.

### 8.3. Class `final` nhưng method không có modifier hợp lệ

Tạo `InvalidFinalClassMethod.java` — **cố ý không biên dịch**:

~~~java
import java.util.List;

public final class InvalidFinalClassMethod {
    @SafeVarargs
    public <T> void take(List<T>... groups) { }
}
~~~

~~~bash
javac --release 17 InvalidFinalClassMethod.java
~~~

**Kết quả:** Compiler từ chối. Modifier `final` của **class** không thay điều kiện compiler yêu cầu ở **method declaration**.

Một cách sửa nếu API phù hợp và phần thân an toàn:

~~~java
@SafeVarargs
public final <T> void take(List<T>... groups) {
    for (List<T> group : groups) {
        System.out.println(group.size());
    }
}
~~~

Đây là **đoạn method trong một class**, không phải chương trình độc lập. Việc thêm `final` ngăn override; chỉ làm nếu điều đó không phá hợp đồng mở rộng lớp. Còn nếu class đã `final` thì method cũng không bị subclass override trong thực tế, nhưng **quy tắc annotation vẫn yêu cầu modifier trên chính method**.

**Không dùng `@SafeVarargs` trên `abstract` hoặc `default` method có thể bị override.** Nếu có lời gọi generic varargs tại một interface method, cân nhắc API nhận collection hoặc cung cấp static helper an toàn cho những nơi thực sự cần.

## 9. Phân biệt lỗi cú pháp với warning và lỗi runtime

Có ba lớp vấn đề hoàn toàn khác nhau:

| Loại | Ví dụ | Điều gì xảy ra? | Cách xử lý |
| --- | --- | --- | --- |
| **Compile error về vị trí annotation** | `@SafeVarargs public <T> void f(T... xs)` trên method không final | Không tạo classfile hợp lệ | Chọn loại method/constructor được phép; không ép compiler bỏ qua |
| **Compile error vì không phải varargs** | `@SafeVarargs static void f(String[] xs)` | Không tạo classfile hợp lệ | Bỏ annotation hoặc thiết kế varargs đúng nhu cầu |
| **Unchecked warning từ generic varargs** | `static void f(List<String>... xs)` không annotate | Có thể biên dịch, nhưng có cảnh báo | Chứng minh body an toàn rồi dùng `@SafeVarargs` ở chỗ hợp lệ, hoặc đổi API |
| **Redundant annotation warning** | `@SafeVarargs static void f(String... xs)` | Biên dịch được, compiler có thể cảnh báo thừa | Bỏ annotation không có tác dụng hữu ích |
| **Runtime `ClassCastException`** | `@SafeVarargs` nhưng code dùng alias mảng để nhét `List<Integer>` vào vị trí `List<String>` | Có thể biên dịch mà vẫn lỗi lúc chạy | Sửa thiết kế/logic, không coi annotation là chứng minh an toàn |

### 9.1. Chương trình quan sát unchecked warning

Tạo `WarningsDemo.java`:

~~~java
import java.util.List;

public class WarningsDemo {
    static void unsafeDeclaration(List<String>... groups) {
        System.out.println(groups.length);
    }

    @SafeVarargs
    static void verified(List<String>... groups) {
        System.out.println(groups.length);
    }

    public static void main(String[] args) {
        unsafeDeclaration(List.of("a"));
        verified(List.of("b"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:unchecked WarningsDemo.java
java WarningsDemo
~~~

Stdout của **lệnh `java`**:

~~~text
1
1
~~~

Trong lần kiểm thử, `javac -Xlint:unchecked` tạo **hai warning** liên quan tới `unsafeDeclaration`: một tại khai báo non-reifiable varargs, một tại lời gọi. Còn `verified` không tạo hai warning tương ứng nhờ annotation. Thông báo compiler nằm trên **luồng diagnostic của `javac`**, không phải stdout của chương trình.

Tên `unsafeDeclaration` ở đây nói rằng **chưa xác nhận/anotate là an toàn**, chứ body ví dụ thực tế chỉ đọc độ dài và không có thao tác gây lỗi. Đây chính là lý do `@SafeVarargs` có ích với method đã được review.

### 9.2. Annotation trên kiểu reifiable: có thể chỉ là warning thừa

Tạo file `RedundantMarkerDemo.java`:

~~~java
public class RedundantMarkerDemo {
    @SafeVarargs
    public static void log(String... words) {
        System.out.println(words.length);
    }

    public static void main(String[] args) {
        log("A", "B");
    }
}
~~~

~~~bash
javac --release 17 -Xlint:varargs RedundantMarkerDemo.java
java RedundantMarkerDemo
~~~

Stdout:

~~~text
2
~~~

Compiler có thể đưa ra cảnh báo annotation thừa, vì `String` là **reifiable element type**. JDK kiểm thử đã phát sinh warning đó. **Đây không phải compile error** do thiếu điều kiện static/final/private hay varargs — cả hai điều kiện đều được thỏa mãn.

## 10. `@SafeVarargs` không làm mã không an toàn trở nên an toàn

JLS và JavaDoc cảnh báo rằng một method **có thể đáp ứng điều kiện được phép annotate nhưng vẫn làm hỏng tính an toàn kiểu**. Vì generic varargs được biểu diễn bằng array, một alias kiểu `Object[]` có thể cho phép ghi một danh sách sai đối số kiểu vào vị trí đang được xem là `List<String>`.

Tạo file `UnsafePromiseDemo.java` — **chương trình chạy được nhưng cố ý chứa lỗi thiết kế**:

~~~java
import java.util.List;

public class UnsafePromiseDemo {
    @SafeVarargs
    static void corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String value = groups[0].get(0);
        System.out.println(value);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("a"));
        } catch (ClassCastException ex) {
            System.out.println("caught=ClassCastException");
        }
    }
}
~~~

~~~bash
javac --release 17 UnsafePromiseDemo.java
java UnsafePromiseDemo
~~~

Stdout:

~~~text
caught=ClassCastException
~~~

**Tại sao mã này vẫn biên dịch?**

1. Method `corrupt` có `List<String>...` và là `static`, nên **hợp lệ về vị trí của `@SafeVarargs`**.
2. Varargs được biểu diễn bằng mảng. Gán nó cho `Object[] alias` tạo tham chiếu tới cùng mảng.
3. `alias[0] = List.of(42)` đặt một `List<Integer>` vào mảng mà code đang tin là chứa `List<String>`. Do erasure, Java không thể kiểm tra thành phần generic ở runtime tại chỗ ghi này.
4. Khi lấy `groups[0].get(0)` dưới dạng `String`, một phép kiểm tra kiểu runtime thất bại, gây `ClassCastException`.
5. Annotation **không tạo kiểm tra runtime mới** và không biến logic thành an toàn. Nó còn làm giảm cảnh báo tại call site, nên lời khẳng định sai càng nguy hiểm.

Đây là ví dụ **cố ý không nên áp dụng trong sản phẩm**; chỉ dùng để hiểu tại sao cần review method body trước khi annotate. Đừng sử dụng `@SuppressWarnings("unchecked")` hay ép kiểu để “sửa” lỗi này; sửa thao tác làm biến dạng mảng varargs.

Nguồn: [Java SE 26 API — SafeVarargs](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/SafeVarargs.html), trong đó có ví dụ về aliasing và heap pollution tương tự.

### 10.1. Checklist trước khi cam kết an toàn

Trước khi đặt `@SafeVarargs` lên một method:

- **Đọc toàn bộ method body:** có gán giá trị mới vào phần tử mảng varargs không? Có alias `Object[]`/raw type để ghi phần tử sai generic type không?
- **Xem array có thoát ra ngoài không:** có trả trực tiếp, lưu vào field dùng lâu dài hoặc truyền cho method không đáng tin có thể sửa mảng không?
- **Xem từng method được gọi:** nếu truyền mảng cho helper khác, helper có giữ reference hoặc ghi dữ liệu không hợp lệ không?
- **Không tin riêng static/final/private:** các modifier chỉ bảo đảm **không override được**, không chứng minh body là type-safe.
- **Không tin việc code chạy được với một input:** heap pollution có thể chỉ nổ khi một kiểu phần tử khác được thêm vào hoặc khi một nhánh hiếm gặp thực thi.
- **Viết test có dữ liệu generic khác nhau:** kiểm tra các edge case, aliasing và phần tử không thuộc kiểu mong muốn.
- **Nếu chưa đủ tự tin:** ưu tiên API nhận `Collection<T>`/`List<T>` hoặc một giải pháp không cần non-reifiable varargs array.

## 11. `@SafeVarargs` so với `@SuppressWarnings("unchecked")`

Hai annotation này **không tương đương**.

| Tiêu chí | `@SafeVarargs` | `@SuppressWarnings("unchecked")` |
| --- | --- | --- |
| Mục đích | Lời cam kết an toàn cho **non-reifiable varargs** | Tắt những unchecked warning trong một phạm vi mã |
| Vị trí hợp lệ | Chỉ constructor/method varargs và modifier hợp lệ theo version | Nhiều loại declaration khác nhau theo `@Target` |
| Hiệu ứng tại call site | **Có thể tắt warning** về generic varargs array creation ở caller | **Không tự tắt** warning tại các call site nằm ngoài phạm vi được annotate |
| Chứng minh method body an toàn? | **Không**, tác giả phải bảo đảm | **Không** |
| Chặn `ClassCastException` runtime? | **Không** | **Không** |
| Cách dùng nên ưu tiên | Method generic varargs được review kỹ, thuộc loại không override | Unchecked operation cục bộ có lý do/bằng chứng rõ ràng, scope hẹp |

Ví dụ:

~~~java
@SuppressWarnings("unchecked")
static void inspect(List<String>... groups) {
    System.out.println(groups.length);
}
~~~

Đây là **đoạn method minh họa**. Annotation có thể che warning tại khai báo trong phạm vi method, nhưng **không được coi nó là hợp đồng an toàn cho mọi call site**. Lời gọi ở nơi khác vẫn có thể bị cảnh báo tạo generic array.

Ngược lại, một method varargs đã được kiểm tra an toàn và có modifier hợp lệ nên sử dụng `@SafeVarargs` đúng mục đích thay vì che warning rộng rãi. Nếu compiler còn cảnh báo thao tác không an toàn **bên trong method** dù đã annotate, cần xem lại logic chứ không vội chồng thêm `@SuppressWarnings`.

**Không dùng annotation thay cho type-safe API.** Với API mới, nếu gọi varargs không đem lại lợi thế rõ ràng, có thể nhận `Collection<T>`; việc này tránh nhu cầu tạo mảng chứa kiểu không reifiable ở điểm gọi.

## 12. Kiểm tra theo source level trong dự án

Khi sửa hoặc review code có `@SafeVarargs`, cần biết **phiên bản Java tối thiểu dùng để biên dịch source**, không chỉ xem lệnh `java -version` của máy đang chạy.

### 12.1. Bước xác minh tối thiểu

~~~bash
javac -version
javac --help
javac --release 17 -Xlint:unchecked Example.java
~~~

Đây là các **lệnh mẫu**, chỉ chạy được sau khi có file `Example.java` tương ứng. Không có một stdout cố định cho `javac --help` hoặc compiler diagnostics; chúng phụ thuộc phiên bản JDK.

Quy trình thực tế:

1. **Đọc cấu hình build:** kiểm tra `--release`, Maven `maven.compiler.release`, hoặc Gradle Java toolchain và các compiler arguments tương ứng.
2. **Xác định minimum source/API release** yêu cầu bởi sản phẩm/thư viện.
3. **Kiểm tra chữ ký:** tham số cuối có `...` không? Có phải generic/non-reifiable varargs không?
4. **Kiểm tra vị trí:** constructor, `static`, `final`, hoặc `private` (private chỉ được annotate từ Java 9).
5. **Chạy compiler với mức đúng:** không mặc định build thành công trên Java 17 nghĩa là tương thích Java 8.
6. **Bật lint:** `-Xlint:unchecked` và khi hữu ích `-Xlint:varargs`, rồi phân biệt warning declaration, invocation, redundant annotation và thao tác không an toàn.
7. **Đọc method body và test:** compiler cho đặt annotation chưa chứng minh method không có heap pollution.
8. **Trước khi đổi modifier:** xem có phá API/khả năng override hợp lệ của thư viện hay không.
9. **Không che lỗi compile-time:** nếu compiler từ chối việc đặt `@SafeVarargs`, cần sửa chữ ký hoặc vị trí annotation; `@SuppressWarnings` không biến cú pháp sai thành hợp lệ.

### 12.2. Java release khác với Java runtime

Nếu đã biên dịch class bằng `--release 17`, việc người dùng chạy application trên JVM có version cao hơn không biến source code thành Java 8-compatible. Ngược lại, ở dự án có minimum release 8, một helper `private @SafeVarargs` không được phép **ngay từ bước biên dịch**, dù CI chạy trên JDK 17 hoặc 24.

Không dùng việc “annotation vẫn có sẵn ở runtime” để suy đoán source compatibility. `@SafeVarargs` có `RetentionPolicy.RUNTIME` nhưng **hạn chế áp dụng của nó được compiler kiểm tra khi biên dịch**.

### 12.3. Maven và Gradle: điểm cần quan sát

Nếu dự án dùng Maven, xem:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **đoạn cấu hình XML minh họa** trong `pom.xml`, không phải tệp hoàn chỉnh. Hãy chọn số release theo dự án. Với mức 8, method `private @SafeVarargs` sẽ không hợp lệ về ngôn ngữ.

Với Gradle, có thể cấu hình Java toolchain và/hoặc `options.release` tương ứng với target. **Toolchain chọn JDK biên dịch**; `--release` hoặc cấu hình release xác định ngôn ngữ/API được kiểm tra. Cần kiểm tra cấu hình build thực tế, tránh nhầm việc Gradle/Maven dùng một JDK mới với quyền được dùng mọi tính năng ngôn ngữ của JDK đó.

**Nếu compiler không hỗ trợ `--release 8`:** hãy dùng JDK/toolchain có khả năng xác thực release đó, thay vì bỏ qua kiểm tra rồi tuyên bố API hỗ trợ Java 8.

## 13. Những trường hợp đặc biệt và giới hạn

### 13.1. Phương thức `final` trong một class có thể được kế thừa

Một instance method `final` vẫn được kế thừa theo quy tắc ngôn ngữ (trừ các ràng buộc khác), nhưng **không được override**. Vì thế `@SafeVarargs` trên method `final` có varargs là hợp lệ; method không cần nằm trong một class `final`.

File `FinalMethodDemo.java`:

~~~java
import java.util.List;

public class FinalMethodDemo {
    @SafeVarargs
    public final <T> int sumSizes(List<T>... groups) {
        int sum = 0;
        for (List<T> group : groups) {
            sum += group.size();
        }
        return sum;
    }

    public static void main(String[] args) {
        FinalMethodDemo demo = new FinalMethodDemo();
        System.out.println(
                demo.sumSizes(List.of(3), List.of(4, 5)));
    }
}
~~~

~~~bash
javac --release 17 FinalMethodDemo.java
java FinalMethodDemo
~~~

Stdout:

~~~text
3
~~~

Ví dụ cho thấy **class không cần `final`**; chỉ cần method được khai báo `final` và phần thân xử lý varargs an toàn.

### 13.2. Constructor không thể là `static` hoặc `final`

Không đặt modifier method lên constructor chỉ để hợp thức hóa `@SafeVarargs`. Một constructor **có varargs** được phép mang annotation từ Java 7. Việc constructor dùng generic type parameters hay class generic không phải điều kiện bắt buộc; điều kiện chính vẫn là nó thực sự variable-arity và phần thân không gây lỗi an toàn kiểu nếu đã cam kết.

### 13.3. Method `private` trong Java 9+ không bắt buộc ghi `final`

Vì private method không bị override theo ngữ nghĩa Java, Java 9 thêm nó vào danh sách hợp lệ. Cố ý thêm `final` vào mọi private helper chỉ để giữ tính tương thích giả định thường là không cần thiết **nếu minimum language level là Java 9+**.

Tuy nhiên, nếu xuất bản thư viện hỗ trợ Java 8, một private method chưa `final` **không thể** dùng annotation ở source level Java 8. Thay đổi modifier có thể làm compiler chấp nhận nhưng vẫn cần bảo đảm logic thật sự an toàn.

### 13.4. Interface method và khả năng override

Từ Java 8, interface có static method; từ Java 9, interface có private methods. Các method này có thể đủ điều kiện `@SafeVarargs` nếu là varargs và phù hợp các điều kiện khác. Trái lại, **default method** bình thường của interface có thể bị override, nên không thể gắn `@SafeVarargs` chỉ vì nó có body.

Không khuyến khích dùng trick về modifier để tránh compiler ở API công khai: nếu method cần dynamic dispatch, hãy giữ hợp đồng mở rộng và thiết kế cách truyền dữ liệu an toàn, ví dụ collection.

### 13.5. Chuyện gì xảy ra khi thêm `@SafeVarargs` vào method overrideable của class `final`?

Như `InvalidFinalClassMethod` đã kiểm chứng, việc class `final` không làm biến mất điều kiện về modifier **của method**. Đây là bẫy không nên bỏ qua khi tự xây linter hoặc review code dựa trên “thực tế class không thể kế thừa”.

### 13.6. Chuyện gì xảy ra nếu method vẫn có warning dù đã annotate?

Compiler được khuyến khích cảnh báo khi phần thân có thao tác varargs không an toàn, và có thể cảnh báo annotation thừa với reifiable element types. Vì vậy:

- **Không khẳng định** `@SafeVarargs` khiến build luôn sạch mọi warning.
- **Không khẳng định** có warning tức mọi cách đặt annotation đều sai cú pháp.
- **Không khẳng định** không có warning chứng minh runtime an toàn.
- Hãy đọc **loại diagnostic** cụ thể và đối chiếu JLS/Javadoc.

Đặc biệt, compiler có thể chưa phát hiện được một số biến thể aliasing làm heap pollution. Test và code review vẫn là yêu cầu thiết yếu.

## 14. Tình huống vận dụng

### 14.1. Đang sửa thư viện Java 8 nhưng CI chạy trên JDK mới

Bạn gặp:

~~~java
@SafeVarargs
private <T> void collect(List<T>... groups) {
    // Chỉ đọc các nhóm.
}
~~~

**Vấn đề:** CI chạy JDK 17 không đồng nghĩa `--release 8` cho phép. Nếu project phải phát hành cho Java 8, declaration này không hợp lệ.

**Cách giải quyết:** Xem lại minimum Java release; nếu bắt buộc là 8, dùng một helper `static` hoặc method `final` thích hợp (khi không làm sai contract API) và kiểm tra an toàn logic. Nếu project thực sự đã chuyển minimum lên 17 thì có thể giữ `private @SafeVarargs`.

### 14.2. Public API đang để override nhưng bị warning generic varargs

Bạn gặp:

~~~java
public <T> void accept(List<T>... groups) {
    // ...
}
~~~

Không được gắn `@SafeVarargs` trực tiếp vào method overrideable này. Có thể:

- Chuyển sang `public <T> void accept(List<T> groups)` nếu thực tế chỉ cần một danh sách.
- Nếu cần nhiều danh sách, xem việc nhận `List<? extends List<? extends T>>` hoặc một cấu trúc phù hợp hơn.
- Nếu API cần varargs để thuận tiện cho caller, triển khai việc xử lý trong một **helper static/final/private hợp lệ** đã được kiểm tra an toàn, nhưng không giả định helper sẽ tự loại mọi warning phát sinh ở public method còn overrideable.

Không thay signature một cách cơ học gây phá source/binary compatibility mà chưa đánh giá tác động đến người dùng thư viện.

### 14.3. Method `static` có `String...` nhưng đã được annotate

Trường hợp này hợp lệ về cú pháp. Vì `String` là kiểu phần tử reifiable, annotation thường là **dư thừa**. Bỏ `@SafeVarargs` giúp ý nghĩa code rõ ràng và tránh warning thừa. Không cần đổi `String...` thành `List<String>...` để “biện minh” annotation.

### 14.4. Có `@SafeVarargs` nhưng test vẫn bị `ClassCastException`

Không xử lý bằng thêm `@SuppressWarnings`. Hãy xem method có ghi vào `Object[]` alias của generic varargs array, trả/giữ mảng để mã bên ngoài mutate, hoặc đưa vào API raw không an toàn không. Sau khi sửa, test nhiều kiểu dữ liệu và đường lỗi.

## 15. Checklist review ngắn gọn

Khi review một declaration có `@SafeVarargs`, đi theo thứ tự:

1. **Bài toán có đúng là varargs?** Tham số cuối có dấu `...`; method/constructor không chỉ nhận array/collection thông thường.
2. **Source level nào?** Đọc cấu hình build, `--release` và minimum Java version.
3. **Constructor hay method?** Constructor varargs được phép từ Java 7; method phải `static`/`final`, hoặc `private` khi Java 9+.
4. **Method có thể bị override không?** Nếu có, annotation không hợp lệ.
5. **Có nhầm class `final` với method `final` không?** Compiler xét modifier của method declaration.
6. **Generic element có non-reifiable không?** Nếu chỉ `String...`/`int...`, annotation thường không hữu ích.
7. **Method body thực sự an toàn không?** Không làm heap pollution, không để alias mảng bị mutate sai kiểu.
8. **Diagnostic thuộc loại nào?** Compile error, unchecked warning, redundant warning hay lỗi runtime?
9. **Warning tại caller có còn không?** `@SafeVarargs` và `@SuppressWarnings` có phạm vi tác dụng khác nhau.
10. **Đã kiểm tra build theo release mục tiêu và test chưa?** Không dùng kết quả biên dịch mặc định của máy phát triển thay cho kiểm tra compatibility.
11. **Có lựa chọn API rõ hơn không?** Nếu varargs không cần thiết, cân nhắc collection an toàn kiểu.
12. **Có cập nhật tài liệu thiết kế không?** Khi dùng `@SafeVarargs` trên API công khai, cam kết của người viết thư viện cần được bảo vệ trong các lần refactor sau.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `@SafeVarargs static <T> void f(T... xs)` có hợp lệ từ Java 7 không?  
**Đáp án:** Có về điều kiện áp dụng vì phương thức `static` có varargs. Cần kiểm tra body thật sự an toàn trước khi dùng annotation.

**Câu 2.** `@SafeVarargs private <T> void f(List<T>... xs)` biên dịch với `--release 8` không?  
**Đáp án:** Không nếu method `private` không `final`. Từ Java 9 mới bổ sung trường hợp private instance method.

**Câu 3.** Cũng phương thức trên nhưng `--release 9` có hợp lệ không?  
**Đáp án:** Có về vị trí annotation; an toàn logic phải kiểm tra riêng.

**Câu 4.** `@SafeVarargs public void f(List<String>... xs)` trong một class `final` có hợp lệ không?  
**Đáp án:** Không, nếu chính method không `final`, `static` hoặc `private`. Compiler kiểm tra modifier method.

**Câu 5.** Constructor generic có varargs có cần modifier `final` để dùng annotation?  
**Đáp án:** Không. Constructor có varargs tự thuộc nhóm được phép; constructor không khai báo `final`.

**Câu 6.** `@SafeVarargs static void f(List<String>[] values)` có hợp lệ không?  
**Đáp án:** Không. Khai báo dùng `[]`, không phải `...`; đây là fixed-arity method.

**Câu 7.** `@SafeVarargs static void f(String... xs)` có phải compile error?  
**Đáp án:** Không. Thường chỉ redundant warning vì `String` reifiable và annotation không cần thiết.

**Câu 8.** `@SafeVarargs` có bảo đảm không bao giờ có `ClassCastException` không?  
**Đáp án:** Không. Ví dụ `UnsafePromiseDemo` vẫn bị runtime exception vì code làm heap pollution.

**Câu 9.** Vì sao `@SuppressWarnings("unchecked")` không hoàn toàn thay thế `@SafeVarargs`?  
**Đáp án:** Nó có phạm vi cục bộ; không tự đảm bảo suppression cho những unchecked warning do varargs array creation ở call site khác. Hai annotation có ý nghĩa khác nhau.

**Câu 10.** Có thể nhận `List<List<String>>` thay cho generic varargs khi không cần cú pháp nhiều đối số không?  
**Đáp án:** Có thể, nếu API và hợp đồng dùng phù hợp. Collection tránh nhu cầu tạo non-reifiable generic varargs array, nhưng thay đổi API cần đánh giá tương thích.

**Câu 11.** Dùng JDK 24 để build code hỗ trợ Java 8 có được dùng private `@SafeVarargs` chỉ vì JDK mới không?  
**Đáp án:** Không, nếu build với `--release 8`. Source-level rule vẫn là của Java 8.

**Câu 12.** Annotation đã có `RetentionPolicy.RUNTIME` thì compiler còn kiểm tra vị trí không?  
**Đáp án:** Có. Retention và điều kiện hợp lệ khi biên dịch là hai chuyện độc lập.

## 17. Nguồn chính thức

- [Java SE 26 JLS §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.6.4.7): quy tắc hiện hành về vị trí annotation, varargs bắt buộc, hiệu ứng cảnh báo tại call site và tính không thể override.
- [Java SE 26 API — `SafeVarargs`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/SafeVarargs.html): `@Target`, điều kiện compile error, redundant warnings, ví dụ aliasing gây `ClassCastException` dù đã annotate.
- [Java SE 26 JLS §8.4.1 — Formal Parameters](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.4.1): varargs parameter, array type, unchecked warnings khi kiểu phần tử non-reifiable.
- [Java SE 26 JLS §4.7 — Reifiable Types](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.7): phân biệt kiểu reifiable và non-reifiable.
- [Java SE 26 JLS §4.12.2 — Heap Pollution](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.12.2): lý do mảng varargs với generic có thể dẫn đến dữ liệu sai kiểu.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): cải tiến Java 9 cho phép `@SafeVarargs` trên private instance methods.
- [Oracle — Small Language Changes in Java SE 9](https://docs.oracle.com/en/java/javase/13/language/small-language-changes.html): xác nhận mốc Java 9 và loại method được phép. Tài liệu phát hành trước đây được dùng để xác nhận **mốc thay đổi**, không thay JLS hiện hành.
- [Java SE 7 JLS §9.6.3.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se7/html/jls-9.html#jls-9.6.3.7): bằng chứng lịch sử về tập điều kiện ban đầu của Java 7; không dùng bản cũ thay cho quy tắc Java hiện hành.
- [Dev.java — Type Erasure and Generic Varargs](https://dev.java/learn/language/fp/generics/type-erasure/): minh họa heap pollution và lý do API cần cam kết an toàn khi dùng generic varargs.

**Ghi nhớ:** `@SafeVarargs` là **cam kết an toàn của tác giả API**, không phải “phép màu” làm generic varargs an toàn ở runtime. Kiểm tra điều kiện theo **mức ngôn ngữ được biên dịch**: có `...`, annotation ở constructor hoặc method `static`/`final`; từ Java 9 thêm `private`. Phân biệt lỗi sử dụng annotation với unchecked warning và lỗi heap pollution thật, rồi chỉ giữ annotation ở nơi đã được chứng minh an toàn.