# Varargs generic được biểu diễn bằng mảng trong Java

## 1. Hiểu đúng bản chất của T...

Varargs (*variable-length arguments*) cho phép gọi một phương thức với số lượng đối số thay đổi mà không phải tự viết mảng trong mỗi lời gọi:

~~~java
static void log(String... messages) {
    for (String message : messages) {
        System.out.println(message);
    }
}

log("Java", "Generics", "Varargs");
~~~

Điểm kỹ thuật quan trọng: `String...` **không tạo một cơ chế lưu trữ mới**. Tham số `messages` ở trong phương thức là một **mảng String[]**.

Tương tự, một phương thức generic:

~~~java
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

có tham số `values` với kiểu tĩnh là **T[]**, tức **mảng các T**, chứ không phải một danh sách động riêng biệt.

Chữ ký `T...` có một cách đọc thực dụng:

> Phương thức nhận một tham số cuối cùng có kiểu mảng T[], và cú pháp varargs cho phép compiler đóng gói một số lượng đối số riêng lẻ thành array tại điểm gọi khi sử dụng dạng gọi có số lượng đối số thay đổi.

Đây là cội nguồn của cả sự tiện lợi lẫn các cảnh báo khi `T` là generic type không reifiable.

## 2. Varargs không phải ArrayList, và cũng không phải nhiều tham số độc lập

So sánh:

~~~java
static int count(String... items) {
    return items.length;
}
~~~

Có thể gọi:

~~~java
count();                       // Không có phần tử.
count("A");                    // Một phần tử.
count("A", "B");               // Hai phần tử.
count(new String[] {"A","B"}); // Truyền một mảng trực tiếp.
~~~

Trong thân hàm, biến `items` luôn là **String[]**. Nó có thuộc tính `length`, hỗ trợ truy cập chỉ số `items[0]`, và không có `add` như một List.

Biểu thức `count("A", "B")` được biên dịch theo cơ chế gọi có số lượng đối số thay đổi, tương đương về ý nghĩa với việc truyền một `String[]` chứa hai phần tử. Còn `count(new String[]{"A","B"})` truyền mảng do caller đã tạo.

Không được hình dung rằng phương thức varargs nhận hai biến riêng rẽ tên `items0` và `items1`. **Tại runtime, đây vẫn là một tham số mảng.**

Với generic varargs, quy tắc tương ứng:

~~~java
static <T> int countGeneric(T... items) {
    return items.length;
}
~~~

`items` có kiểu tĩnh `T[]`. Nhưng vì `T` là biến kiểu được Java generics xử lý qua type erasure, ta phải cẩn thận về **runtime component type** của mảng được tạo tại call site.

## 3. Quy tắc khai báo varargs trong method và constructor

Trong một method declaration, varargs parameter phải nằm ở vị trí **cuối cùng**:

~~~java
static <T> void describe(String title, T... items) {
    System.out.println(title + ": " + items.length);
}
~~~

Hai kiểu gọi có thể hợp lệ:

~~~java
describe("Languages", "Java", "Go");
describe("Numbers", 1, 2, 3);
~~~

Compiler suy luận T theo các đối số và ngữ cảnh lời gọi. Cả hai đều được đưa vào phương thức qua tham số mảng.

Những dạng sau **cố ý không biên dịch**:

~~~java
// static <T> void wrong(T... items, String title) { }
// Varargs parameter không được đứng trước một tham số khác.

// static void wrong(String... first, Integer... second) { }
// Một danh sách tham số không được có hai varargs parameters.
~~~

Ký hiệu `...` khai báo một tham số kiểu mảng nhưng có cách gọi thuận tiện. Nó không phải loại generic thứ hai và không biến T thành một giá trị runtime có thể kiểm tra sâu.

## 4. Hai giai đoạn: nguồn Java và phương thức trong bytecode

Giả sử:

~~~java
static <T> void inspect(T... values) {
    System.out.println(values.length);
}
~~~

Ở **Java source**:
- `T` là type parameter của method.
- `T...` là varargs, tức tham số `T[]` ở phía thân hàm.
- Khi caller truyền các đối số riêng lẻ, compiler lựa chọn và chuẩn bị array phù hợp theo quy tắc suy luận kiểu và varargs invocation.

Sau **type erasure**:
- Nếu T không có bound tường minh, erasure của T là Object.
- Method descriptor có tham số mảng **Object[]**.
- Call site có thể truyền array runtime kiểu cụ thể như String[], vì **String[] là subtype của Object[]**.

Ví dụ:

~~~java
inspect("Java", "Kotlin");
~~~

Ở một biên dịch thông thường, compiler có thể tạo một **String[]** tại caller rồi chuyển nó thành Object[] theo quan hệ array subtype để gọi method đã xóa kiểu. Method nhận được vẫn là array có runtime component class String, dù chữ ký đã xóa của tham số là Object[].

Đây là hai điều khác nhau:
1. **Kiểu của tham số sau erasure trong method descriptor** có thể là Object[].
2. **Kiểu thực của đối tượng array được truyền vào** có thể là String[] hoặc List[].

Không nên diễn giải câu “T bị xóa thành Object” thành “mọi array truyền qua T... đều có runtime component Object”. Điều đó sai vì runtime class của array được tạo ở caller vẫn được giữ.

### Bound của T tác động đến erasure

~~~java
static <T extends Number> void inspectNumbers(T... numbers) {
    System.out.println(numbers.length);
}
~~~

Ở đây T bị xóa về bound `Number` thay vì Object, nên tham số sau erasure có dạng `Number[]`. Khi gọi với các Integer, caller vẫn có thể truyền runtime array Integer[] tương thích với Number[].

Vì vậy, muốn phân tích chính xác bytecode, phải xem **cận của T**, kiểu của các đối số và ngữ cảnh gọi, thay vì luôn nói varargs generic chỉ là Object[].

## 5. Vì sao T... có thể có cảnh báo generic array creation?

Java cho phép khai báo:

~~~java
static void consume(List<String>... groups) {
    System.out.println(groups.length);
}
~~~

Dạng này hợp lệ ở source; bên trong `groups` là **List<String>[]** theo kiểu tĩnh.

Nhưng Java không cho tạo mảng trực tiếp:

~~~java
// List<String>[] groups = new List<String>[2];
// Lỗi: generic array creation.
~~~

`List<String>` không phải **reifiable type**: một runtime List object không mang đủ generic type argument String để JVM kiểm chứng từng phần tử.

Khi gọi:

~~~java
consume(List.of("A"), List.of("B"));
~~~

compiler vẫn phải đóng gói các đối số varargs vào **một array**. Nó tạo một array có component runtime là **List**, không phải một runtime class riêng biệt `List<String>`. Vì vậy compiler có thể cảnh báo:

~~~text
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Thông điệp chính xác có thể khác theo phiên bản javac. Cảnh báo cho biết bước tạo array ở dạng varargs không duy trì được đầy đủ cam kết type arguments.

Đây là cách Java cho phép các API varargs generic tiện dụng tồn tại, nhưng cảnh báo ở các trường hợp compiler không thể chứng minh được an toàn.

## 6. Generic array creation bị cấm ở source nhưng varargs vẫn có thể được gọi

Hai câu sau không tương đương về quy tắc ngôn ngữ:

~~~java
// List<String>[] direct = new List<String>[2]; // Không biên dịch.

consume(List.of("A"), List.of("B")); // Có thể biên dịch với warning.
~~~

Dòng thứ nhất là một **array creation expression tường minh** có component type không reifiable, bị Java cấm.

Dòng thứ hai là **variable arity invocation** của một method được khai báo varargs. Compiler được phép tạo array thích hợp để thực thi lời gọi, nhưng có thể báo unchecked warning về sự không an toàn của generic array backing.

Vì vậy không nên ghi nhớ giản lược rằng “Java không thể tạo bất kỳ mảng nào cho generic”. Chính xác hơn:

> Java cấm một số biểu thức tạo array với component type không reifiable; lời gọi varargs có thể được chuyển thành việc truyền một array đã xóa generic, kéo theo cảnh báo và khả năng heap pollution.

Nếu phương thức dùng mảng đó đúng cách và không phơi ra alias nguy hiểm, API có thể hoạt động an toàn. Nếu thân phương thức hoặc bên ngoài lạm dụng array covariance/raw reference, dữ liệu sai kiểu có thể lọt vào.

## 7. Mảng varargs thuộc quyền sở hữu của ai?

Với một lời gọi các đối số riêng lẻ:

~~~java
inspect("A", "B");
~~~

compiler thường tạo array tại **điểm gọi**, sau đó truyền reference vào method. Method nhận một tham chiếu đến array ấy; không có quy tắc bắt buộc phải sao chép tất cả phần tử trước khi dùng.

Với:

~~~java
String[] existing = {"A", "B"};
inspect(existing);
~~~

lời gọi có thể diễn ra ở dạng **fixed arity invocation**: caller truyền array `existing` trực tiếp làm tham số cuối. Khi đó, nếu body của method thay đổi `values[0]`, nó có thể thay đổi chính `existing[0]`.

Mối quan hệ alias rất quan trọng khi thiết kế API:
- Một method chỉ đọc array rồi tính kết quả thường dễ chứng minh an toàn hơn.
- Một method sửa array, lưu array vào trường static/instance hoặc trả trực tiếp array có thể khiến caller và callee quan sát những thay đổi của nhau.
- Với **non-reifiable component type**, việc alias array qua Object[] là một đường tạo **heap pollution** đặc biệt nguy hiểm.

Không được giả định “vì tham số khai báo T... nên Java tự copy phần tử”. Varargs chủ yếu thay đổi cách viết lời gọi và cách compiler đóng gói đối số, **không tự cung cấp ownership hoặc immutability**.

## 8. Hệ quả của việc biểu diễn varargs generic bằng mảng

Ở **phương thức** nhận `List<String>... groups`, kiểu source của tham số là `List<String>[]`, nhưng runtime component của array là `List`. Vì vậy một alias `Object[]` có thể thay slot bằng một đối tượng `List<Integer>` mà runtime store check vẫn chấp nhận:

```java
static void unsafe(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);           // Vẫn là một List ở runtime.
    String text = groups[0].get(0);   // ClassCastException.
}
```

Dùng đoạn này **chỉ để tái hiện lỗi**, với import `java.util.List` và lời gọi `unsafe(List.of("safe"))`; nó cố ý gây cảnh báo unchecked tại declaration/call site. Trong trường hợp mảng thật là `String[]`, ghi Integer qua `Object[]` bị `ArrayStoreException` ngay tại phép ghi vì JVM biết component type String. Nhưng với mảng `List[]`, JVM không kiểm tra được type argument String trong từng list.

Cần phân biệt **mảng do compiler tạo để thực hiện variable-arity invocation** với **mảng caller truyền sẵn ở fixed-arity invocation**: method không tự sao chép mảng trong mọi trường hợp. Việc gán qua alias chỉ thay slot trong mảng, không nhất thiết sửa nội dung object List ban đầu. Bài này tập trung vào cách **varargs → array**; các bài sau phân tích kỹ rủi ro ghi alias, làm lộ mảng và cách đọc compiler diagnostics.

## 9. Chương trình Java 17+ chạy được

Lưu nội dung sau thành **GenericVarargsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;

public class GenericVarargsDemo {
    // Chỉ quan sát array, không sửa hoặc làm lộ reference.
    @SafeVarargs
    static <T> void inspect(String tag, T... values) {
        System.out.println(
                tag + " length=" + values.length
                        + " component="
                        + values.getClass()
                                .getComponentType()
                                .getTypeName()
        );
    }

    // Không trả chính mảng varargs; tạo bản sao qua List.copyOf.
    @SafeVarargs
    static <T> List<T> safeCopy(T... values) {
        return List.copyOf(Arrays.asList(values));
    }

    // Đọc các List<String> mà không thay đổi mảng hoặc trả alias.
    @SafeVarargs
    static void showGroups(List<String>... groups) {
        System.out.println(
                "groups component="
                        + groups.getClass()
                                .getComponentType()
                                .getTypeName()
        );
        System.out.println(
                "groups=" + Arrays.toString(groups)
        );
    }

    // CỐ Ý KHÔNG AN TOÀN: để minh họa heap pollution.
    static void unsafe(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);

        try {
            String first = groups[0].get(0);
            System.out.println(first);
        } catch (ClassCastException error) {
            System.out.println("unsafe=ClassCastException");
        }
    }

    public static void main(String[] args) {
        // Compiler tạo array khi gọi bằng nhiều phần tử riêng lẻ.
        inspect("strings", "Java", "Go");

        // Truyền một array thật do caller đã có.
        String[] explicit = {"A", "B"};
        inspect("explicit", explicit);

        // Khi T là List<String>, runtime component là raw List.
        inspect("lists", List.of("x"), List.of("y"));

        // Snapshot an toàn cho các đối số String thông thường.
        System.out.println(
                "copy=" + safeCopy("red", "blue")
        );

        // Không sửa hoặc làm lộ array varargs.
        showGroups(List.of("A"), List.of("B"));

        // Tạo lỗi có kiểm soát để quan sát ranh giới an toàn.
        unsafe(List.of("safe"));
    }
}
~~~

Biên dịch ở mức ngôn ngữ Java 17:

~~~bash
javac --release 17 -Xlint:unchecked GenericVarargsDemo.java
java GenericVarargsDemo
~~~

**Cảnh báo biên dịch được dự kiến** tại method `unsafe` và lời gọi `unsafe(List.of("safe"))` vì method không an toàn sử dụng `List<String>...` với component không reifiable. Cảnh báo đại ý:

~~~text
Possible heap pollution from parameterized vararg type List<String>
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Các warning này không nằm trong stdout của chương trình.

**Stdout chính xác:**

~~~text
strings length=2 component=java.lang.String
explicit length=2 component=java.lang.String
lists length=2 component=java.util.List
copy=[red, blue]
groups component=java.util.List
groups=[[A], [B]]
unsafe=ClassCastException
~~~

### Những điểm cần đọc từ output

**`strings ... java.lang.String`:** khi T suy ra String và caller đưa hai chuỗi riêng lẻ, mảng thực tế có component String.

**`explicit ... java.lang.String`:** lời gọi truyền sẵn String[] cũng cho runtime component String. Output giống nhau nhưng đường truyền tham số có thể khác: caller đã tự tạo mảng thay vì compiler cần gói nhiều đối số.

**`lists ... java.util.List`:** khi T suy ra List<String>, runtime component của array được tạo là List. Điều này không chứng minh mọi phần tử của mảng là List<String> theo runtime check.

**`copy=[red, blue]`:** method sao chép phần tử vào một List không cho phép sửa đổi bằng các phương thức bình thường. Với đối số đầu vào không null như trong ví dụ, `List.copyOf` thành công. Đây là một thiết kế hữu ích để không trả chính array varargs ra ngoài.

**`groups ... java.util.List`:** showGroups đọc mảng List[] mà compiler tạo; method không tạo đường ghi vào mảng backing.

**`unsafe=ClassCastException`:** một List<Integer> được đưa vào mảng dùng như List<String>[] qua Object[] alias, và lỗi được phát hiện khi đọc phần tử đó dưới dạng String.

## 10. @SafeVarargs có ý nghĩa gì?

`@SafeVarargs` là annotation mà tác giả method/constructor dùng để cam kết việc triển khai **không thực hiện các thao tác có nguy cơ làm hỏng an toàn kiểu liên quan đến tham số varargs**. Nó có thể làm compiler không phát những cảnh báo varargs/unchecked tương ứng ở vị trí khai báo và call sites thích hợp.

Ví dụ hợp lý:

~~~java
@SafeVarargs
static <T> List<T> snapshot(T... values) {
    return List.copyOf(Arrays.asList(values));
}
~~~

Method chỉ đọc phần tử và tạo List mới, không trả mảng, không gán sai kiểu vào mảng, không lưu một alias sửa được đến mảng. Khi các giá trị đầu vào phù hợp, cách dùng này có thể an toàn đối với vấn đề heap pollution của varargs array.

**Không có phép kiểm tra runtime mới** do annotation tạo ra. `@SafeVarargs` không khiến `List<String>` thành reifiable, không làm component array biến thành List<String> ở runtime, và không tự kiểm tra từng phần tử của các List.

Nếu gắn `@SafeVarargs` vào phương thức `unsafe`, annotation không biến body đó thành an toàn. Nó chỉ đưa ra **một lời cam kết sai**, có thể che các cảnh báo ở call site; code vẫn có thể ném ClassCastException. Javac có thể đưa ra cảnh báo bổ sung hoặc không phát hiện tất cả mẫu không an toàn, nên **tác giả API phải tự chứng minh** phương thức tuân thủ hợp đồng.

### Những vị trí Java 17 cho phép @SafeVarargs

Annotation có thể áp dụng cho:
- Constructor có varargs.
- Method `static` có varargs.
- Method `final` có varargs.
- Method `private` có varargs.

Không sử dụng `@SafeVarargs` trên một instance method thông thường **có thể override** vì lời cam kết của triển khai hiện tại không chứng minh được những implementation ở lớp con cũng an toàn.

Một method dù `static` hay `final` nhưng không phải varargs cũng không phải nơi thích hợp để đặt annotation này.

### @SafeVarargs và @SuppressWarnings có giống nhau không?

Không hoàn toàn:

- `@SafeVarargs` thông báo về tính an toàn của **varargs declaration**, có hiệu lực liên quan đến cảnh báo ở lời gọi.
- `@SuppressWarnings("unchecked")` là chỉ thị suppress các cảnh báo unchecked trong phạm vi được đặt; nó không đưa ra bảo đảm ngữ nghĩa được compiler chứng minh.
- Cả hai **không kiểm tra runtime generic arguments**.

Đừng dùng bất kỳ annotation nào để giấu cảnh báo của một method đã biết có thể sửa array bằng Object[] alias không an toàn.

## 11. Xem varargs trong bytecode bằng javap

Sau khi biên dịch:

~~~bash
javap -p GenericVarargsDemo
javap -c -p GenericVarargsDemo
javap -v -p GenericVarargsDemo
~~~

Điểm cần quan sát:

1. Chữ ký method ở trình đọc class file có dấu varargs, nhưng đây vẫn là **array parameter**.
2. Với `<T> void inspect(String,T...)`, phương thức bị erasure về một descriptor dùng tham số String và Object[] vì T không có bound.
3. Ở `main`, những lời gọi variable arity có thể được javac biến thành việc tạo các array bằng bytecode tương ứng, ví dụ `anewarray java/lang/String` và `anewarray java/util/List`.
4. Với `List<String>...`, descriptor của mảng varargs dùng List[] sau erasure.
5. `javap -v` hiển thị các cờ method như **ACC_VARARGS** khi phù hợp.

Đừng dựa vào offset chỉ thị hay thứ tự bytecode chính xác của một bản javac. Điều cần hiểu là mỗi lời gọi varargs phải được quy về cách truyền **một tham số mảng** tại runtime, và generic arguments không được giữ trong array component class.

### Fixed arity so với variable arity

Với chữ ký:

~~~java
static void emit(String... values) { }
~~~

Hai lời gọi sau có thể đi theo hai dạng khác nhau:

~~~java
String[] existing = {"A", "B"};

emit(existing); // Truyền array có sẵn.
emit("A", "B"); // Compiler đóng gói hai đối số thành array.
~~~

Không phải compiler “luôn tạo thêm một mảng” ở mọi lời gọi varargs. Nếu caller truyền đúng một array phù hợp và lời gọi được giải quyết ở fixed arity, array đó được dùng trực tiếp.

## 12. Generic varargs với wildcard và reifiable type

Không phải mọi varargs có chứa generic syntax đều gây cảnh báo unchecked.

Ví dụ:

~~~java
static void inspectUnknown(List<?>... groups) {
    for (List<?> group : groups) {
        System.out.println(group.size());
    }
}
~~~

`List<?>` là parameterized type với **unbounded wildcard**, được xem là **reifiable type**. Vì vậy Java cho phép biểu thức:

~~~java
List<?>[] groups = new List<?>[2];
~~~

Và method `inspectUnknown(List<?>... groups)` có thể dùng loại tham số mảng này mà không vướng vấn đề tạo array có component type `List<String>` không reifiable.

Tuy nhiên, `List<?>` không bảo đảm phần tử của từng danh sách là String, Number hay một kiểu cụ thể nào. Sự “reifiable” ở đây chỉ tương ứng với việc runtime có thể nhận diện đối tượng là List mà **không phải kiểm tra generic type argument cụ thể**.

Tương tự:
- `Map<?, ?>...` có các type arguments là wildcard không giới hạn.
- `List<String>...` có type argument cụ thể String, không reifiable.
- `List<? extends Number>...` có wildcard có bound, không thuộc trường hợp chỉ wildcard không giới hạn.

Đừng đồng nhất “có dấu `<...>`” với “chắc chắn phải cảnh báo”. Cần kiểm tra **loại tham số generic có reifiable hay không**.

## 13. varargs của List<String> khác List<List<String>>

Cùng một mục tiêu “nhận nhiều danh sách chuỗi”, hai API có hình dạng khác nhau:

~~~java
static void processVarargs(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}

static void processList(List<List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
~~~

`processVarargs` thuận tiện khi caller có số ít các List riêng lẻ:

~~~java
processVarargs(List.of("A"), List.of("B"));
~~~

Nhưng compiler phải xây hoặc nhận một mảng `List<String>[]` theo cơ chế varargs; với component không reifiable, có thể có unchecked warnings và nguy cơ alias/heap pollution nếu method xử lý không an toàn.

`processList` nhận một **List gồm các List<String>**:

~~~java
processList(List.of(List.of("A"), List.of("B")));
~~~

Không có bước tạo `List<String>[]` bắt buộc. Compiler vẫn kiểm tra đúng generic types ở API. Khi không cần cú pháp varargs, dạng collection lồng nhau thường giúp API tránh mảng generic và các cảnh báo liên quan.

Đừng nghĩ List<List<String>> tự khiến dữ liệu hoàn toàn miễn nhiễm với unchecked casts hoặc raw types. Nhưng nó **không yêu cầu mảng varargs có component non-reifiable** trong đường truyền thông thường.

## 14. Vì sao trả trực tiếp T[] từ một varargs method có thể nguy hiểm?

Hãy xem:

~~~java
@SafeVarargs // Đặt thế này không phải cam kết an toàn đúng đắn.
static <T> T[] expose(T... values) {
    return values; // Làm lộ array backing cho caller.
}
~~~

Nếu caller truyền mảng đã tồn tại, trả mảng có thể làm lộ cùng một reference. Nếu caller gọi bằng các đối số có generic type không reifiable, mảng backing có thể là một array của raw runtime component khác với kỳ vọng của code về tính bất biến hoặc generic arguments.

Một phương thức chỉ làm `return values` không chắc gây lỗi ngay trong mọi tình huống; rủi ro phụ thuộc đường gọi và việc caller làm gì tiếp với array. Nhưng **trả trực tiếp alias của mảng varargs** là một thiết kế khó chứng minh an toàn chung, đặc biệt nếu sau đó người khác có thể sửa nó qua array covariance/raw reference.

Nếu cần kết quả là collection, sao chép:

~~~java
@SafeVarargs
static <T> List<T> toListCopy(T... values) {
    return List.copyOf(Arrays.asList(values));
}
~~~

Đoạn này giữ kiểu generic của phần tử trong chữ ký API và không trả array backing. `List.copyOf` từ chối phần tử null và thực hiện sao chép shallow: các đối tượng T bên trong vẫn là cùng object nếu chúng mutable.

Nếu cần một array mới, phải xem xét **runtime component type** cụ thể; không thể giả định `new Object[values.length]` ép thành T[] sẽ hoạt động khi caller mong đợi String[].

## 15. Khi nào bắt gặp null với varargs?

Cú pháp varargs có một góc cạnh liên quan đến **null**:

~~~java
static void show(String... values) {
    System.out.println(values == null ? "null array" : values.length);
}
~~~

Một lời gọi `show()` truyền mảng rỗng theo dạng variable arity; nhưng `show((String[]) null)` cố ý truyền **null làm chính tham số array**, không phải mảng với một phần tử null.

~~~java
show();                  // In 0.
show((String[]) null);   // In "null array".
show((String) null);     // Một phần tử null: in 1.
~~~

Một lời gọi `show(null)` không ghi kiểu ép có thể dẫn đến cảnh báo mơ hồ về cách sử dụng varargs/array parameter, tùy method và overload. Để tránh nhầm, hãy phân biệt rõ **null array** với **array chứa phần tử null**.

Trong `safeCopy`, nếu caller truyền `(String[]) null`, lời gọi có thể đưa null array vào body; `Arrays.asList(values)` không tương đương một array bình thường trong trường hợp đó, nên API nên định rõ null handling hoặc dùng `Objects.requireNonNull(values)` trước khi xử lý.

Điều này không trực tiếp là lỗi type erasure, nhưng là hệ quả của việc **tham số varargs thực chất là array**.

## 16. Cách đọc các cảnh báo compiler

Với `javac --release 17 -Xlint:unchecked`, một phương thức varargs generic không an toàn có thể sinh hai nhóm cảnh báo:

**Cảnh báo ở khai báo**:

~~~text
Possible heap pollution from parameterized vararg type List<String>
~~~

Nó nói rằng phương thức sử dụng varargs với component generic không reifiable, có thể gây heap pollution. Không phải compiler đã chứng minh thực tế dữ liệu bị hỏng ở mọi lời gọi.

**Cảnh báo ở call site**:

~~~text
unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Nó nói rằng việc compiler chuẩn bị array để thực hiện variable-arity call không bảo đảm an toàn generic đầy đủ.

Một số phương thức đã được xem là an toàn theo `@SafeVarargs` có thể không tạo những warnings này, nhưng đó là do **hợp đồng của tác giả**, không vì JVM tự kiểm tra generic arguments.

Các warnings không phải stdout của ứng dụng. Khi viết tài liệu hoặc kiểm thử, hãy tách rõ kết quả biên dịch và kết quả chạy.

## 17. Checklist thiết kế varargs generic an toàn

Khi viết phương thức `<T> f(T... values)` hoặc `f(List<String>... groups)`, hãy tự kiểm:

1. **Varargs có thật sự cần thiết?** Nếu người dùng thường có collection, nhận `List<T>` hoặc `Collection<T>` có thể rõ và an toàn hơn.
2. **Kiểu phần tử của array có reifiable không?** `String`, `List<?>` khác `List<String>`.
3. **Body có gán qua `Object[]` hoặc raw alias không?** Đây là dấu hiệu heap pollution.
4. **Body có lưu hoặc trả thẳng array không?** Có thể làm lộ alias và khó kiểm soát kiểu phần tử.
5. **Có truyền array sang code có thể sửa không?** An toàn cần xét **transitive**, không chỉ vài dòng trong method hiện tại.
6. **Có sao chép hay chỉ giữ reference?** `Arrays.asList(values)` là một fixed-size List view backed by array, trong khi `List.copyOf` tạo một List không cho sửa đổi và không tiếp tục phơi trực tiếp mảng.
7. **Có null array hoặc null elements không?** Cần hợp đồng rõ ràng.
8. **Có dùng `@SafeVarargs` không?** Chỉ gắn khi đã chứng minh an toàn. Annotation không biến kiểu non-reifiable thành reifiable.
9. **Có kiểm thử qua compiler warnings không?** Bật `-Xlint:unchecked`; kiểm tra đặc biệt các lời gọi varargs generic.
10. **Có alias và nhiều callers không tin cậy không?** Nếu có, ưu tiên thiết kế không để thao tác ghi vào backing array ngoài tầm kiểm soát.

Nếu ví dụ trong code cần intentionally unsafe behavior để dạy học, tách rõ khỏi API production và bắt lỗi tại đúng chỗ để chương trình minh họa có thể tiếp tục chạy.

## 18. Những ngộ nhận thường gặp

### “T... được Java giữ như một số lượng tham số runtime không xác định”

Không đúng. Một varargs parameter là **một tham số array**; compiler biến lời gọi nhiều đối số thành dạng truyền array khi cần.

### “T... luôn trở thành Object[] tại runtime”

Không đúng. Method descriptor sau erasure có thể là Object[] hoặc array của bound, nhưng runtime array truyền vào có thể là String[] hoặc List[] theo cách caller tạo.

### “Nếu new List<String>[n] bị cấm thì List<String>... cũng bị cấm”

Không đúng. Java cho phép **khai báo varargs parameter non-reifiable** và sử dụng cơ chế generic array creation tại điểm gọi với cảnh báo nếu cần.

### “@SafeVarargs kiểm tra mọi phần tử trong List<String>”

Không đúng. Annotation không thực hiện runtime validation; nó chỉ liên quan đến cam kết an toàn trong cách method xử lý varargs array và warnings của compiler.

### “ArrayStoreException sẽ ngăn mọi List<Integer> lọt vào List<String>[]”

Không đúng. Runtime component của array sau erasure có thể chỉ là List; List<Integer> vẫn là một List. Sai generic argument thường lộ khi đọc phần tử như String và xảy ra `ClassCastException`.

### “Trả Arrays.asList(values) chắc chắn không làm lộ mảng”

Không đúng. `Arrays.asList` trả một fixed-size list **được backed bởi array đầu vào**. Thay đổi list bằng `set` hoặc thay đổi array có thể ảnh hưởng lẫn nhau. Nếu mục tiêu là tránh alias, hãy dùng giải pháp sao chép phù hợp như `List.copyOf`, đồng thời xem xét mutable elements.

### “Phương thức có @SafeVarargs chắc chắn an toàn”

Không đúng. Compiler không thể chứng minh toàn diện cách mọi body và những hàm được gọi xử lý dữ liệu. Nếu tác giả annotation vi phạm hợp đồng, vẫn có nguy cơ heap pollution.

## 19. Câu hỏi tự kiểm tra

**1.** Trong phương thức `static <T> void f(T... xs)`, kiểu của xs bên trong thân hàm là gì?

**Đáp án:** `T[]` ở source Java. Sau erasure, descriptor sử dụng array của erasure(T), mặc định là Object[] nếu T không có bound tường minh.

**2.** Compiler cần tạo gì khi caller viết `f("A", "B")`?

**Đáp án:** Theo dạng gọi variable arity, compiler đóng gói hai String vào một array thích hợp và truyền array làm tham số varargs. Runtime method nhận một array.

**3.** Vì sao `f(List.of("A"), List.of("B"))` có thể tạo array runtime có component type List thay vì List<String>?

**Đáp án:** `List<String>` không reifiable do erasure. Component runtime chỉ biểu diễn được raw List; unchecked generic array creation có thể được báo.

**4.** Tại sao `Object[] alias = groups; alias[0] = List.of(123);` trong method nhận `List<String>...` có thể thành công?

**Đáp án:** Array backing có runtime component là List, nên List<Integer> vẫn phù hợp lớp runtime cần gán. Array store không kiểm tra String trong generic argument.

**5.** Lỗi gì có thể xảy ra khi gọi `String s = groups[0].get(0)` sau khi mảng bị nhiễm?

**Đáp án:** `ClassCastException` khi runtime phát hiện phần tử Integer không thể dùng như String.

**6.** `@SafeVarargs` có làm `new List<String>[2]` trở nên hợp lệ không?

**Đáp án:** Không. Annotation không thay đổi quy tắc array creation với non-reifiable component types.

**7.** Gửi `String[]` vào `f(T... values)` có tạo bản sao tự động không?

**Đáp án:** Không nhất thiết. Nếu lời gọi ở dạng fixed arity và truyền array tương thích, method có thể nhận chính array caller đã tạo.

**8.** Với bài toán “nhận nhiều danh sách chuỗi” mà không cần cú pháp varargs, cấu trúc nào thường tránh rủi ro generic array?

**Đáp án:** `List<List<String>>`, vì không cần xây `List<String>[]` tại điểm gọi.

**9.** `List<?>...` và `List<String>...` có giống nhau về tính reifiable không?

**Đáp án:** Không. `List<?>` chỉ chứa unbounded wildcard nên reifiable; `List<String>` có type argument cụ thể và không reifiable.

**10.** Vì sao `List.copyOf(Arrays.asList(values))` thường là hướng đáng cân nhắc thay vì trả thẳng values?

**Đáp án:** Nó tạo một List không cho sửa đổi bằng API thông thường và không tiếp tục phơi ra backing varargs array. Tuy nhiên sao chép chỉ shallow, từ chối null, và không thay thế xác thực dữ liệu bên trong các object mutable.

## 20. Ghi nhớ

**`T...` là cú pháp varargs cho một tham số `T[]`.** Ở runtime, JVM nhận array; với generic type variables, chữ ký method chịu type erasure, còn call site có thể tạo array mang runtime component cụ thể hoặc raw component khi các type arguments không reifiable.

Điểm nguy hiểm xuất hiện rõ với `List<String>...`: backing array runtime có thể là List[], cho phép alias Object[] đưa một List<Integer> vào và làm hỏng cam kết List<String>[]. Cảnh báo unchecked phản ánh nguy cơ đó.

Khi thiết kế API:
- Không sửa hoặc làm lộ backing array của varargs khi điều đó có thể phá bất biến kiểu.
- Chỉ sử dụng `@SafeVarargs` sau khi chứng minh body và những đường gọi liên quan an toàn.
- Ưu tiên copy hoặc nhận `List<T>`/`List<List<T>>` khi không cần varargs.
- Kiểm tra compiler warnings và nắm rõ chỗ nào xảy ra array store check, chỗ nào xảy ra cast khi đọc generic value.

Hiểu được mối liên hệ giữa **varargs → array → erasure → unchecked warnings → heap pollution** sẽ giúp dùng generic varargs đúng và tránh các lỗi chỉ bộc lộ muộn tại runtime.
