# Phân biệt cảnh báo unchecked, rawtypes và varargs trong Java Generics

## 1. Ba loại cảnh báo: có liên hệ nhưng không đồng nghĩa

Khi biên dịch Java Generics, ba nhóm cảnh báo của `javac` thường xuất hiện cùng nhau:

- **`[rawtypes]`**: một tên class hoặc interface đã khai báo generic được dùng ở dạng **raw type**, ví dụ `List` thay cho `List<String>` hay `List<?>`.
- **`[unchecked]`**: compiler không thể chứng minh đầy đủ an toàn kiểu của một **phép chuyển đổi hoặc lời gọi**, chẳng hạn gọi `add` qua raw `List`, cast sang `List<String>` hoặc chuẩn bị một array cho `List<String>...`.
- **`[varargs]`**: cảnh báo liên quan đến **cách sử dụng tham số varargs không reifiable trong thân phương thức**, đặc biệt khi một phương thức được gắn `@SafeVarargs` lại làm lộ hoặc chuyển tiếp mảng varargs theo cách compiler coi là có thể gây heap pollution.

Một đoạn code có thể có **cả ba** nhóm. Nhưng:
- Raw type **không nhất thiết** tự tạo unchecked warning nếu chỉ khai báo biến mà không thực hiện thao tác nguy hiểm; dùng `-Xlint:rawtypes` để phát hiện dạng khai báo.
- Unchecked warning **không đòi** phải có raw type tường minh: một cast `Object` thành `List<String>` cũng có thể là unchecked.
- Cảnh báo ở khai báo varargs generic như `List<String>...` và lúc caller tạo array thường mang nhãn **`[unchecked]`**, không nhất thiết là `[varargs]`.
- `[varargs]` không phải đồng nghĩa với “bất kỳ phương thức nào có dấu `...`”, mà là category của những thao tác varargs được bộ phân tích của javac nhận diện theo các quy tắc cụ thể.

Mục tiêu không phải “làm mọi warning biến mất bằng annotation”, mà là hiểu **compiler đang thiếu bằng chứng về điều gì** rồi khắc phục ở đúng lớp thiết kế.

## 2. Cách bật chính xác các nhóm cảnh báo

Trên JDK 17 trở lên, biên dịch một tệp:

~~~bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked -Xlint:varargs LintCategoriesDemo.java
~~~

Hoặc viết gọn:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
~~~

Ý nghĩa các tùy chọn:

| Tùy chọn javac | Cảnh báo cần quan sát |
| --- | --- |
| `-Xlint:rawtypes` | Chỗ dùng generic type mà không có type arguments. |
| `-Xlint:unchecked` | Unchecked method invocation, conversion, cast, generic array creation tại varargs và các thao tác không kiểm tra đầy đủ. |
| `-Xlint:varargs` | Cách dùng tham số varargs có nguy cơ gây heap pollution, đặc biệt trong method gắn `@SafeVarargs`. |
| `-Xlint:all` | Bật tất cả nhóm lint được javac hỗ trợ, có thể bao gồm thêm những nhóm không liên quan bài này. |
| `-Werror` | Coi các warning do compilation ghi nhận là lỗi build; **không** làm phép chuyển đổi trở nên an toàn hơn. |

Các thông điệp có thể thay đổi về cách diễn đạt, vị trí dòng, số lượng tùy phiên bản JDK và ngữ cảnh source. Hãy đọc **category trong dấu vuông**, vị trí được đánh dấu và các dòng `required/found` để xác định nguyên nhân.

`javac` đôi lúc chỉ đưa ra ghi chú:

~~~text
Note: ... uses unchecked or unsafe operations.
Note: Recompile with -Xlint:unchecked for details.
~~~

Ghi chú không có nghĩa warning đã được xử lý. Bật `-Xlint:unchecked` để xem thao tác cụ thể. Nếu dự án dùng Gradle/Maven, cấu hình compiler tương ứng hoặc chạy lệnh javac tái hiện với đúng classpath và source release.

## 3. rawtypes — lỗi ở cách ghi tên kiểu

Java định nghĩa:

~~~java
interface List<E> { /* thành viên generic */ }
~~~

Trong thư viện chuẩn, `java.util.List<E>` là interface generic. Nếu viết:

~~~java
List raw = new ArrayList();
~~~

hai chỗ cần chú ý:

1. `List` thiếu type argument E.
2. `new ArrayList()` cũng dùng tên generic `ArrayList<E>` theo dạng raw.

Với `-Xlint:rawtypes`, javac cảnh báo:

~~~text
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
~~~

Trong khi đó:

~~~java
List<String> names = new ArrayList<>();
List<?> unknown = names;
List<Object> anyObjects = new ArrayList<>();
~~~

đều là **parameterized types**, không phải raw. `List<?>` có wildcard, `List<Object>` có type argument Object cụ thể. Diamond `<>` ở `new ArrayList<>()` yêu cầu suy luận type arguments; nó **không** là cách viết raw `new ArrayList()`.

### Không phải kiểu nào thiếu <> cũng là raw

~~~java
String name = "Java";
Integer count = 7;
Object value = name;
Runnable job = () -> System.out.println("run");
~~~

Các kiểu `String`, `Integer`, `Object` và `Runnable` vốn không khai báo type parameter; đây là **non-generic types**. `-Xlint:rawtypes` không phải cảnh báo về mọi tên class viết không có `<...>`, mà chỉ về generic type được dùng raw.

Một lớp không generic vẫn có thể chứa generic method:

~~~java
final class Helpers {
    static <T> T same(T value) {
        return value;
    }
}
~~~

`Helpers` không generic, nên viết `Helpers.same("A")` không phải raw. Tham số kiểu T thuộc về method, không thuộc về class.

### Chỉ thấy rawtypes chưa kết luận đã có ClassCastException

~~~java
List legacy;
~~~

Đây là khai báo raw có thể sinh `[rawtypes]`, nhưng chưa có lời gọi thêm sai phần tử, ép kiểu hoặc thao tác runtime nào. Warning chỉ ra một **điểm mất type arguments**, không chứng minh đã xuất hiện lỗi runtime.

Khi xử lý, hãy xác định type argument phù hợp: `List<String>` nếu biết chắc loại phần tử, `List<?>` nếu chỉ cần đọc mà chưa biết loại, `List<Object>` nếu hợp đồng thật sự chấp nhận mọi Object.

## 4. unchecked — compiler không chứng minh đầy đủ an toàn kiểu

`[unchecked]` thường đi kèm những thao tác có thể hợp lệ ở cú pháp Java nhưng **không được xác thực toàn diện bằng runtime generic information**.

### 4.1. Unchecked call qua raw collection

~~~java
List raw = new ArrayList();
raw.add("Java");
~~~

Vì `raw` không gắn type argument E, lời gọi `add(E)` không được kiểm tra theo một E cụ thể. Với `-Xlint:unchecked`, javac cảnh báo:

~~~text
[unchecked] unchecked call to add(E) as a member of the raw type List
~~~

Lỗi không phải vì String bất hợp lệ với mọi List; vấn đề là **lời gọi qua raw type làm mất ràng buộc loại phần tử**. Cùng tham chiếu raw đó có thể được dùng để thêm Integer vào một danh sách mà alias khác khai báo là `List<String>`.

### 4.2. Unchecked conversion từ raw sang parameterized

~~~java
List raw = new ArrayList();
List<String> strings = raw;
~~~

javac có thể cho phép phép gán vì cơ chế tương thích mã cũ, kèm:

~~~text
[unchecked] unchecked conversion
required: List<String>
found:    List
~~~

Compiler không đi kiểm tra mọi phần tử trong raw List. Một giá trị sai có thể chỉ gây `ClassCastException` khi đọc với kiểu String về sau.

### 4.3. Unchecked cast không cần raw syntax tường minh

~~~java
Object unknown = List.of("A");

@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) unknown;
~~~

Ngay cả khi không khai báo biến raw ở dòng này, cast `(List<String>)` vẫn không thể chứng minh mọi phần tử là String. Nếu bỏ annotation, `-Xlint:unchecked` báo:

~~~text
[unchecked] unchecked cast
~~~

Ở runtime, cast có thể kiểm tra được **lớp/interface List**, nhưng không xác nhận generic argument String. Việc danh sách ví dụ thực sự chứa "A" không khiến kiểu cast trở thành checked cast trong mắt compiler.

### 4.4. Checked cast là trường hợp khác

~~~java
Object input = "Java";
String string = (String) input;
~~~

Cast này nhắm đến class runtime reifiable `String` nên được JVM kiểm tra trực tiếp. Nó có thể ném `ClassCastException` nếu đối tượng sai lớp, nhưng **không vì thế mà là unchecked generic cast**.

Cần phân biệt: “cast có thể lỗi ở runtime” không tương đương “unchecked warning”. Unchecked nói về **điều compiler/runtime không đủ thông tin generic để kiểm tra toàn bộ**.

## 5. Vì sao cảnh báo unchecked và rawtypes thường xuất hiện cùng nhau?

Đây là ví dụ:

~~~java
List raw = new ArrayList();
raw.add("Java");
List<String> typed = raw;
~~~

Đọc theo thứ tự:

| Vị trí | Nhóm cảnh báo | Vấn đề |
| --- | --- | --- |
| `List raw` | `[rawtypes]` | Dùng raw List. |
| `new ArrayList()` | `[rawtypes]` | Khởi tạo raw ArrayList. |
| `raw.add("Java")` | `[unchecked]` | Gọi add qua raw generic receiver. |
| `List<String> typed = raw` | `[unchecked]` | Gán raw collection vào parameterized variable. |

Một đoạn rất ngắn có thể sinh nhiều cảnh báo vì chúng nói về **những thao tác khác nhau**. Sửa khai báo raw nhưng bỏ quên unchecked cast cũng không loại bỏ hết rủi ro. Ngược lại, chỉ suppress `[unchecked]` sẽ **không tự xử lý** thực tế raw types vẫn tồn tại trong code.

Với mã legacy, nên sửa tại nguồn tạo/giao dữ liệu, tránh truyền raw references qua nhiều tầng application. Nếu thật sự chưa biết E, chọn wildcard và validate phần tử trước khi khẳng định một E cụ thể.

## 6. Vì sao một warning có chữ varargs lại thuộc `unchecked`?

`T...` và `List<String>...` là **tham số mảng** ở source. Khi compiler cần tạo array cho một variable-arity invocation với component không reifiable như `List<String>`, runtime array chỉ kiểm tra component `List` mà không kiểm tra String; vì vậy nó có thể phát **`[unchecked]` generic array creation** ở caller, cùng cảnh báo khả năng heap pollution tại method declaration.

```java
static void groups(List<String>... values) {
    System.out.println(values.length);
}
// groups(List.of("A"), List.of("B"));
// Hai warning [unchecked] có thể xuất hiện tại khai báo và nơi gọi.
```

Đoạn minh họa cần import `java.util.List` và lời gọi trong method phù hợp. Cần phân biệt: `new List<String>[2]` là **compile error** do component type không reifiable; nhưng gọi generic varargs có thể vẫn biên dịch kèm warnings. `[varargs]` lại thường chỉ **cách dùng/forward/escape array trong thân method đã được đánh dấu `@SafeVarargs`**, không nhất thiết xuất hiện chỉ vì dấu `...` trong chữ ký.

Đây là khác biệt cốt lõi giữa **phân loại diagnostic** và **nguyên nhân runtime**. Muốn quan sát đủ ba nhóm, dùng `-Xlint:rawtypes,unchecked,varargs` thay vì chỉ bật `-Xlint:varargs`.

## 7. Cảnh báo varargs ở khai báo và call site thường là [unchecked]

Một chương trình có:

~~~java
static void groups(List<String>... values) {
    System.out.println(values.length);
}

static void call() {
    groups(List.of("A"), List.of("B"));
}
~~~

khi bật `-Xlint:unchecked` thường có **hai vị trí cảnh báo**:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Cảnh báo thứ nhất gắn với **declaration** sử dụng `List<String>...`; cảnh báo thứ hai gắn với **call site** cần tạo một generic array backing cho lời gọi.

Điểm dễ gây nhầm: dù thông điệp chứa chữ `vararg`, nhãn lint thực tế thường là **`[unchecked]`**, vì compiler đang nói đến tạo và sử dụng mảng generic có component không reifiable, không có phép kiểm tra kiểu đầy đủ.

Chỉ bật:

~~~bash
javac --release 17 -Xlint:varargs Example.java
~~~

không nhất thiết cho thấy **hai cảnh báo trên ở dạng chi tiết**. Khi debug varargs generics, luôn bật cả `unchecked` để quan sát declaration/call-site warnings.

## 8. [varargs] kiểm tra điều gì trong thân phương thức?

Hãy xét một method được gắn annotation:

~~~java
@SafeVarargs
static <T> T[] expose(T... values) {
    return values;
}
~~~

`@SafeVarargs` là cam kết rằng tác giả **không làm thao tác có thể gây mất an toàn kiểu liên quan đến varargs array**. Nhưng body trên lại trả trực tiếp mảng backing cho caller, một cách làm có thể làm lộ alias và dẫn đến heap pollution hoặc lỗi runtime.

Với `-Xlint:varargs`, javac 17 đưa cảnh báo tại `return values`:

~~~text
[varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter values
~~~

Cảnh báo `[varargs]` thường nhằm vào **việc sử dụng mảng trong body**, ví dụ:
- Trả trực tiếp mảng varargs.
- Truyền mảng vào một API khác mà compiler không thể chứng minh là không sửa/làm lộ alias.
- Các đường thao tác có thể làm varargs array bị phơi ra hoặc dùng không an toàn.

Không phải mọi thao tác đọc `values.length`, duyệt phần tử, hoặc dùng một varargs method đều đương nhiên sinh `[varargs]`.

### Vì sao @SafeVarargs không bị compiler coi là “đã chứng minh an toàn”?

Annotation là **lời cam kết của người viết API**, không phải chứng minh hình thức rằng mọi đường chạy đều an toàn. Compiler có thể cảnh báo khi thấy mẫu đáng ngờ nhưng không phát hiện tất cả hành vi không an toàn xuyên qua lời gọi hàm khác.

Nếu bỏ annotation để lộ `[unchecked]`, rồi sau đó gắn `@SafeVarargs` chỉ để im warning nhưng method vẫn trả mảng, ta đang **che dấu hiệu rủi ro, không giải quyết bất biến**.

Với Java 17, `@SafeVarargs` chỉ được đặt ở constructor hoặc method varargs phù hợp như static, final hay private (không phải một instance method có thể override tùy ý). Nó không khiến type arguments trở thành reifiable.

## 9. Chương trình Java 17+ hoàn chỉnh minh họa cả ba nhóm

Lưu toàn bộ nội dung sau vào **LintCategoriesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LintCategoriesDemo {
    static void rawExample() {
        // [rawtypes] ở hai vị trí sử dụng generic class raw.
        List raw = new ArrayList();

        // [unchecked] vì gọi add trên raw List.
        raw.add("Java");

        // [unchecked] vì chuyển raw List thành List<String>.
        List<String> strings = raw;

        System.out.println("raw=" + strings.get(0));
    }

    static void uncheckedCast() {
        Object unknown = List.of("A");

        // [unchecked] dù không dùng biến raw ở đây.
        List<String> assumed = (List<String>) unknown;

        System.out.println("cast=" + assumed.get(0));
    }

    // [unchecked] declaration/call-site với non-reifiable List<String>.
    static void groups(List<String>... values) {
        System.out.println("groups=" + values.length);
    }

    // Đọc và copy vào collection mới, không trả hoặc phơi mảng.
    @SafeVarargs
    static <T> List<T> safeCopy(T... values) {
        List<T> result = new ArrayList<>();

        for (T value : values) {
            result.add(value);
        }

        return List.copyOf(result);
    }

    // Cố ý vi phạm ý định an toàn: phơi mảng backing cho caller.
    // Khi -Xlint:varargs được bật, javac cảnh báo ngay tại return.
    @SafeVarargs
    static <T> T[] unsafeExpose(T... values) {
        return values;
    }

    public static void main(String[] args) {
        rawExample();
        uncheckedCast();

        groups(List.of("x"), List.of("y"));

        System.out.println(
                "copy=" + safeCopy("A", "B")
        );

        System.out.println(
                "exposed=" + unsafeExpose("a", "b").length
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
java LintCategoriesDemo
~~~

Khi biên dịch với javac 17-compatible, chương trình minh họa sinh các nhóm cảnh báo tương ứng:

~~~text
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked conversion
[unchecked] unchecked cast
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter values
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Danh sách trên **chỉ liệt kê phần lõi của các warning**, không phải chép nguyên văn toàn bộ output của javac (có thể có file path, vị trí dòng, phần `required/found` và tổng số warning). Điều quan trọng là dòng nào có nhãn nào.

**Stdout chính xác của chương trình:**

~~~text
raw=Java
cast=A
groups=2
copy=[A, B]
exposed=2
~~~

Bài dùng `unsafeExpose` như một ví dụ **sai thiết kế**, không phải mẫu nên triển khai ở ứng dụng thật. Vì caller ở đây truyền hai String thật, chương trình vẫn chạy và in `exposed=2`. Việc chạy thành công **không chứng minh** rằng thân method thỏa hợp đồng `@SafeVarargs` cho mọi lời gọi và tương tác alias.

### Tại sao chương trình có warning nhưng không ném exception?

Compiler đang chỉ ra **khả năng** không an toàn do các đường sử dụng raw/unchecked/varargs, không tuyên bố mọi dữ liệu trong ví dụ đã sai. Một danh sách chỉ chứa String và được đọc như String sẽ chạy được dù từng có unchecked conversion. Nhưng cùng kiểu warning đó có thể che đường đưa Integer vào danh sách rồi dẫn tới ClassCastException.

Điều cần sửa là kiến trúc hoặc đường chuyển đổi không được kiểm tra, không phải chỉ xem test này có ném ngoại lệ hay không.

## 10. Bật từng nhóm riêng để xác định nguyên nhân

Vẫn dùng `LintCategoriesDemo.java` như trên:

~~~bash
javac --release 17 -Xlint:rawtypes LintCategoriesDemo.java
javac --release 17 -Xlint:unchecked LintCategoriesDemo.java
javac --release 17 -Xlint:varargs LintCategoriesDemo.java
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
~~~

Tùy chọn đầu tiên làm nổi bật **nơi raw types được sử dụng**; những cảnh báo unchecked chưa được bật chi tiết có thể được tóm lược bằng Note.

Tùy chọn thứ hai cho thấy:
- Lời gọi `raw.add` và chuyển từ raw sang `List<String>`.
- Cast `(List<String>) unknown`.
- Declaration `List<String>...` và call-site generic array creation.

Tùy chọn thứ ba có thể chỉ ra cách body `unsafeExpose` trả tham số varargs ra bên ngoài. Những cảnh báo unchecked khác có thể không được in chi tiết ở lần chạy chỉ bật varargs.

Tùy chọn cuối giúp đặt **mọi vị trí cạnh nhau** để phân biệt: hai warning có cùng nguyên nhân tổng quát “mất khả năng kiểm tra kiểu” nhưng thuộc hai loại thao tác khác nhau.

Nên dùng cùng `--release 17` và cùng nguồn khi đối chiếu, tránh nhầm do các thay đổi compiler hay source-level.

## 11. Phân biệt unchecked conversion, unchecked cast và checked cast

Ba thao tác có vẻ giống nhau nhưng khác bản chất.

### Unchecked conversion

~~~java
List raw = List.of("Java");
List<String> words = raw;
~~~

Gán từ raw List sang `List<String>` được phép do tương thích cũ, nhưng compiler không xác minh mọi phần tử. `[unchecked] unchecked conversion` mô tả đúng điều đó.

### Unchecked cast

~~~java
Object input = List.of(10);
List<String> assumed = (List<String>) input;
~~~

Cast theo `List<String>` không kiểm tra phần tử Integer. Nếu gọi `assumed.get(0)` như String, có thể ném ClassCastException. `[unchecked] unchecked cast` xuất hiện vì runtime không có đủ generic argument information.

### Checked cast

~~~java
Object input = "Java";
String text = (String) input;
~~~

Đích String là class runtime kiểm tra được. Đây là checked reference cast; nếu input thực sự chứa Integer, nó ném ClassCastException ngay, nhưng **không phải cảnh báo unchecked generic**.

Không nên suppress warnings chỉ vì “dù sao Java có cast ở runtime”: cast runtime có thể kiểm tra class, nhưng không chứng minh phần tử lồng nhau đúng generic type arguments.

## 12. Heap pollution: khi nào mối lo ngại thành lỗi thật?

Xét một phương thức varargs sai:

~~~java
static void pollute(List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);

    String text = lists[0].get(0);
    System.out.println(text);
}
~~~

Đây là **mảnh code minh họa**, không phải đoạn đã ghép vào chương trình hoàn chỉnh. Nếu gọi `pollute(List.of("safe"))`, có thể xảy ra:

1. Compiler tạo array có runtime component `List` vì `List<String>` không reifiable.
2. Method nhận array mà kiểu tĩnh là `List<String>[]`.
3. Một alias `Object[]` trỏ đến cùng array.
4. Lệnh gán `List<Integer>` vào phần tử array được JVM chấp nhận do runtime chỉ kiểm tra đó là List.
5. Khi gọi `get(0)` rồi dùng như String, JVM có thể ném `ClassCastException`.

Điểm 4 giải thích vì sao lỗi không nhất thiết là ArrayStoreException tại chỗ gán: runtime component là List, và đối tượng được gán vẫn là một List.

**Nguyên nhân gốc** là thao tác không an toàn qua alias/raw hoặc cách phơi array. Hai warning liên quan declaration/call-site sẽ chỉ ra rủi ro chung, nhưng không chỉ có warning là chứng minh chắc chắn đã xảy ra heap pollution.

### Unsafe varargs không có nghĩa sai trong mọi lời gọi

Một phương thức chỉ đọc các `List<String>` và không phơi array có thể hoạt động an toàn dù kiểu component không reifiable. Nếu tác giả đủ điều kiện và chứng minh an toàn, `@SafeVarargs` được dùng để tránh cảnh báo không cần thiết.

Ngược lại, ngay cả phương thức được gắn `@SafeVarargs` cũng có thể gây lỗi nếu làm lộ hoặc sửa mảng. Annotation không thay đổi hành vi JVM.

## 13. Sửa rawtypes như thế nào?

Với:

~~~java
List raw = new ArrayList();
~~~

chọn thay thế theo hợp đồng:

~~~java
List<String> strings = new ArrayList<>(); // Biết mọi phần tử là String.
List<?> unknown = strings;                // Chưa biết loại khi chỉ đọc.
List<Object> mixed = new ArrayList<>();   // Chủ động cho nhiều loại Object.
~~~

Đừng coi ba kiểu đó tương đương:
- `List<String>` khóa kiểu phần tử là String trong thao tác qua API generic.
- `List<?>` biết tồn tại một kiểu phần tử chưa xác định; compiler chặn thêm tùy ý.
- `List<Object>` chấp nhận mọi Object nhưng **không phải supertype của `List<String>`** vì generic invariance.

Nếu data thật sự đến từ legacy raw API, có thể nhận tạm dạng `List<?>` và duyệt kiểm tra:

~~~java
static List<String> validatedStrings(List<?> input) {
    List<String> result = new ArrayList<>();

    for (Object value : input) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("String required");
        }
        result.add(text);
    }

    return List.copyOf(result);
}
~~~

Đoạn này cần import `java.util.List` và `java.util.ArrayList`, dùng Java 17 pattern matching. Nó từ chối null và tạo kết quả không cho sửa đổi bằng API thông thường. Mục tiêu là **khôi phục một bất biến đã kiểm chứng bằng dữ liệu**, thay vì tự gắn tham số `String` bằng unchecked cast.

## 14. Sửa unchecked mà không phải che warning

Nếu thấy:

~~~java
@SuppressWarnings("unchecked")
List<String> strings = (List<String>) unknown;
~~~

hãy hỏi:
1. Ai tạo `unknown` và cung cấp hợp đồng nào?
2. Runtime có thể kiểm tra top-level object là List không?
3. Có thể duyệt từng phần tử như Object rồi xác nhận String không?
4. Có thể đổi API nguồn để trả ngay `List<String>` không?
5. Có cần defensive copy để ngăn raw alias về sau thay đổi dữ liệu không?

Một cách an toàn ở ranh giới bất kỳ Object:

~~~java
static List<String> checkedCopy(Object source) {
    if (!(source instanceof List<?> unknown)) {
        throw new IllegalArgumentException("List required");
    }

    List<String> result = new ArrayList<>();
    for (Object value : unknown) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("String required");
        }
        result.add(s);
    }

    return List.copyOf(result);
}
~~~

Không cần suppress warning. Dùng `instanceof List<?>` chỉ xác nhận đây là List; chính vòng lặp `instanceof String` mới kiểm tra phần tử.

Đối với cast unchecked **không thể loại bỏ** trong một thư viện generic thấp tầng, giữ annotation thật hẹp và ghi rõ **bất biến bảo đảm cast**, giới hạn các đường ghi, và thử nghiệm các trường hợp sai kiểu. Không nên tắt cảnh báo toàn dự án chỉ để làm compile output sạch.

## 15. Sửa cảnh báo varargs như thế nào?

### 15.1. Nếu API không cần biến số đối số, bỏ varargs

Thay:

~~~java
static void process(List<String>... groups) {
    // ...
}
~~~

bằng:

~~~java
static void process(List<List<String>> groups) {
    // ...
}
~~~

Đây là hướng hợp lý nếu caller thường có collection sẵn. Nó bỏ yêu cầu tạo `List<String>[]` backing array ở call site.

### 15.2. Nếu cần varargs, không sửa hay phơi array

Mẫu có thể an toàn:

~~~java
@SafeVarargs
static <T> List<T> copyValues(T... values) {
    List<T> result = new ArrayList<>();

    for (T value : values) {
        result.add(value);
    }

    return List.copyOf(result);
}
~~~

Body chỉ đọc phần tử, không trả `values`, không gán sai kiểu vào array và không truyền mảng cho API có thể giữ alias. `List.copyOf` không nhận null và là shallow copy; đây là giới hạn riêng của ví dụ.

### 15.3. Nếu compiler báo [varargs] ở return hoặc forward, xem lại ownership

~~~java
@SafeVarargs
static <T> T[] returnBackingArray(T... values) {
    return values; // [varargs] có thể cảnh báo.
}
~~~

Không nên dùng thêm `@SuppressWarnings("varargs")` rồi coi đã khắc phục an toàn. Cần đổi API để tránh phơi array hoặc chứng minh điều kiện đặc biệt khiến alias không thể bị dùng sai. Nếu thư viện bắt buộc trả array, phải xử lý runtime component type và contract của caller.

### 15.4. Không copy nhãn annotation một cách máy móc

`@SafeVarargs` không đặt tùy ý trên một instance method có thể override, và không nên dùng trên method không phải varargs. Nó là hợp đồng cho tác giả, không phải “mẹo” tắt lint.

Các cảnh báo dù bị suppress vẫn có thể phản ánh một bug runtime. Test an toàn phải có trường hợp dữ liệu sai, không chỉ test happy path.

## 16. Tại sao Arrays.asList(values) cũng cần suy nghĩ?

`Arrays.asList(values)` tạo một **fixed-size List backed by array**. Nó không tự sao chép mảng backing:

~~~java
String[] source = {"A", "B"};
List<String> view = java.util.Arrays.asList(source);

view.set(0, "changed");
System.out.println(source[0]); // changed
~~~

Nếu một method có `@SafeVarargs` truyền trực tiếp mảng varargs tới `Arrays.asList` hoặc một method khác, compiler khi bật `-Xlint:varargs` **có thể cảnh báo** ở vị trí forward đó. Một lời gọi method bên ngoài có thể giữ lại hoặc tạo view của chính array, nên việc chuyển tiếp cần được chứng minh an toàn xuyên suốt.

Một mẫu rõ ý định hơn để tránh làm lộ mảng trong `@SafeVarargs` là **tạo collection riêng bằng vòng lặp qua T**, sau đó `List.copyOf` nếu cần kết quả không cho sửa đổi. Compiler không phải giả định một lời gọi ngoài kia có giữ hoặc thay đổi alias của `values` không.

**Quan trọng:** sao chép collection chỉ là **shallow copy**; nếu phần tử T chính nó mutable hoặc là một raw/unchecked List không đúng generic type, chỉ copy danh sách bên ngoài không xác minh mọi phần tử lồng nhau.

## 17. Khi nào dùng @SuppressWarnings?

`@SuppressWarnings` cho phép chỉ rõ category ở một vùng code, ví dụ:

~~~java
@SuppressWarnings("unchecked")
static <T> T controlledCast(Object value) {
    return (T) value;
}
~~~

Đoạn code trên chỉ để minh họa cú pháp, **không tự an toàn**: caller có thể yêu cầu T không tương thích và gặp ClassCastException khi sử dụng kết quả. Không nên dùng y nguyên cho ứng dụng mà không có bằng chứng về kiểu runtime.

Các category thường được truyền dưới dạng string:
- `"rawtypes"` dành cho raw-type diagnostics.
- `"unchecked"` dành cho unchecked operations.
- `"varargs"` dành cho các varargs warnings tương ứng khi compiler hỗ trợ.

Nhưng suppression nên là **biện pháp cuối ở đoạn code nhỏ đã được chứng minh an toàn**. Nên thêm bình luận nêu bất biến:
- Type information được xác thực ở đâu?
- Ai có quyền ghi dữ liệu?
- Tại sao cast này không thể nhận object sai kiểu?
- Tại sao mảng varargs không bị sửa/làm lộ?
- Liệu invariant còn đúng nếu API được kế thừa hay gọi qua raw type?

Suppress cả lớp hoặc cả build sẽ che những warning mới xuất hiện về sau; thực tế tốt là giảm phạm vi đến method, dòng hoặc một biến cần thiết.

## 18. Bảng quyết định nhanh theo warning

| Thông điệp thường gặp | Nhóm | Nguyên nhân gần | Cách xử lý ưu tiên |
| --- | --- | --- | --- |
| `found raw type: List` | `rawtypes` | Dùng tên generic không có type argument. | Chọn `List<T>` hoặc `List<?>` phù hợp. |
| `unchecked call to add(E)` | `unchecked` | Gọi method phụ thuộc E qua raw receiver. | Loại raw alias và dùng generic typed reference. |
| `unchecked conversion` | `unchecked` | Raw List → List<String> không kiểm tra phần tử. | Đổi API nguồn hoặc kiểm tra/copy dữ liệu. |
| `unchecked cast` | `unchecked` | Cast về generic type không reifiable. | Validator hoặc invariant rõ ràng. |
| `Possible heap pollution from parameterized vararg type` | `unchecked` | Khai báo varargs với non-reifiable component. | Xem lại API, dùng @SafeVarargs khi thật sự an toàn. |
| `unchecked generic array creation for varargs parameter` | `unchecked` | Caller đóng gói đối số thành array generic không reifiable. | Dùng API an toàn có @SafeVarargs hoặc collection thay thế. |
| `Varargs method could cause heap pollution ...` | `varargs` | Trong body, mảng varargs có thể bị phơi/chuyển tiếp sai. | Sửa body để tránh unsafe exposure hoặc chứng minh contract. |

Thông điệp cụ thể có thể khác giữa các bản javac. Đừng chỉ tìm từ khóa “varargs” trong văn bản rồi mặc định đó là category `[varargs]`; hãy đọc phần nhãn và vị trí được compiler đánh dấu.

## 19. Checklist review mã generic

1. **Bật đủ lint categories:** `-Xlint:rawtypes,unchecked,varargs` ở mức source release dự án.
2. **Đọc nhãn warning**, không chỉ phần nội dung thông báo.
3. **Tìm kiểu gốc generic:** List<E>, Map<K,V>, Optional<T>, hay một class do dự án định nghĩa.
4. **Xem raw type có do thiết kế không:** ưu tiên wildcard khi không biết type argument.
5. **Xem unchecked chuyển đổi ở đâu:** khai báo, gọi method, ép kiểu, hay varargs call site.
6. **Kiểm tra runtime invariant:** dữ liệu được tạo từ đâu, có alias raw không, có kiểm tra phần tử không.
7. **Nếu varargs:** xác định backing array ở caller, fixed/variable arity, component runtime sau erasure.
8. **Kiểm tra body method được đánh @SafeVarargs:** có trả mảng, lưu vào field, chuyển mảng cho API khác, dùng Object[] alias hoặc array writes không.
9. **Ưu tiên sửa API:** parameterized collections, validator, defensive copy; suppress annotation chỉ khi có chứng minh cụ thể.
10. **Thử trường hợp âm tính:** Integer trong List<String> qua raw alias, generic varargs bị phơi, sai kiểu khi đọc.
11. **Tách compiler diagnostics khỏi stdout:** warnings là dữ liệu phát sinh khi build, không phải kết quả chương trình.
12. **Đừng dùng -Werror thay việc sửa:** nó buộc build thất bại khi có warnings, giúp đảm bảo chất lượng, nhưng không tự làm code an toàn.

Các bước này phù hợp khi chuyển legacy Java code sang generics, thiết kế thư viện API công khai hoặc review việc sử dụng `@SafeVarargs` trong codebase.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `List raw;` có cảnh báo gì khi bật `-Xlint:rawtypes` mà không có thao tác thêm phần tử?

**Đáp án:** `[rawtypes]` vì tên List<E> bị dùng raw. Không bắt buộc có `[unchecked]` nếu chưa làm thao tác nào cần generic type checking.

**Câu 2.** `List<String> values = raw;` cảnh báo gì?

**Đáp án:** `[unchecked] unchecked conversion` vì compiler không chứng minh được raw collection thực sự chỉ chứa String.

**Câu 3.** Một cast `(List<String>) unknown` từ Object có cần raw List variable không mới cảnh báo?

**Đáp án:** Không. `[unchecked] unchecked cast` có thể xuất hiện vì cast đến parameterized type không reifiable, ngay cả khi source là Object.

**Câu 4.** `static void f(List<String>... xs)` và lời gọi `f(List.of("A"))` thường cảnh báo category nào?

**Đáp án:** Khi bật `-Xlint:unchecked`, javac có thể báo `[unchecked]` tại declaration (“Possible heap pollution...”) và call site (“unchecked generic array creation...”); chữ vararg trong message không làm category đổi thành `[varargs]`.

**Câu 5.** `@SafeVarargs static <T> T[] f(T... xs) { return xs; }` có chắc không warning?

**Đáp án:** Không. `-Xlint:varargs` có thể cảnh báo ở `return xs` vì phương thức làm lộ mảng varargs dù đã gắn annotation. Annotation không chứng minh code an toàn.

**Câu 6.** Nếu code có cả rawtypes và unchecked warning, chỉ suppress "rawtypes" đã giải quyết an toàn chưa?

**Đáp án:** Chưa. Raw declaration và unchecked operations phản ánh các vấn đề riêng. Suppress chỉ che diagnostic, không sửa dữ liệu hay invariant.

**Câu 7.** Vì sao `List<String>...` có nguy cơ heap pollution?

**Đáp án:** Tham số là mảng List<String>[] ở source nhưng component runtime sau erasure thường là List. Qua Object[] alias, một List<Integer> vẫn có thể được lưu vào mảng; đọc phần tử đó như String có thể ném ClassCastException.

**Câu 8.** `@SafeVarargs` có tự động kiểm tra từng phần tử của List<String> không?

**Đáp án:** Không. Nó không tạo cơ chế runtime validation và không thay đổi type erasure. Người thiết kế vẫn cần bảo đảm body không gây thao tác array unsafe.

**Câu 9.** Tại sao `List.copyOf(Arrays.asList(values))` trong một method @SafeVarargs vẫn có thể bị `-Xlint:varargs` cảnh báo?

**Đáp án:** Vì method đã chuyển trực tiếp backing array `values` cho API khác. Dù kết quả cuối có thể là bản sao, compiler cảnh báo tại đường forward có thể phơi hoặc sử dụng mảng. Có thể tự duyệt các phần tử vào một collection mới để thể hiện rõ hơn rằng array reference không thoát ra ngoài.

**Câu 10.** Có warning nhưng chương trình vẫn in đúng kết quả có nghĩa warning là sai?

**Đáp án:** Không. Warning thể hiện compiler không chứng minh đầy đủ tính an toàn ở mọi trường hợp. Dữ liệu hiện tại đúng kiểu vẫn có thể chạy, nhưng code khác dùng raw alias/unchecked cast có thể phá invariant.

## 21. Kết luận

**`rawtypes` nói về cách sử dụng một tên kiểu generic không kèm tham số kiểu. `unchecked` nói về thao tác không thể chứng minh đầy đủ an toàn generic. `varargs` nói về những cách sử dụng mảng varargs có thể không an toàn, đặc biệt khi một method được quảng bá bằng `@SafeVarargs` lại làm lộ hoặc chuyển tiếp mảng.**

Điểm phân biệt thực hành quan trọng nhất: **cảnh báo `List<String>...` ở declaration và varargs call site thường mang nhãn `[unchecked]`, còn `[varargs]` có thể gắn với thao tác sử dụng mảng trong body**. Cùng một method có thể làm phát sinh cả hai nhóm.

Hãy dùng compiler warnings như **đầu mối kiểm tra hợp đồng kiểu**, sửa nguyên nhân ở chỗ sinh dữ liệu/API, giữ `@SafeVarargs` và `@SuppressWarnings` ở phạm vi được chứng minh an toàn, và nhớ rằng việc một chương trình chạy đúng trên dữ liệu hiện tại không làm những thao tác unchecked trở thành an toàn cho mọi đầu vào.
