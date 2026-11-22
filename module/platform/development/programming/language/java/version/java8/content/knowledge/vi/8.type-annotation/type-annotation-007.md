# Pluggable type system và kiểm tra tĩnh trong Java

Java là ngôn ngữ có **hệ thống kiểu tĩnh** (*static type system*): trình biên dịch `javac` kiểm tra kiểu của biểu thức, biến, phương thức, phép gán và generic trước khi chạy. Nhưng kiểu Java thông thường **không diễn đạt hết mọi ràng buộc** của ứng dụng. Ví dụ, hai giá trị đều có kiểu `String` nhưng một giá trị được phép `null`, giá trị kia phải khác `null`; hai chuỗi cùng kiểu `String` nhưng một là dữ liệu chưa tin cậy và một đã được xác thực.

**Pluggable type system** (hệ thống kiểu có thể bổ sung) cho phép gắn thêm **type qualifiers** bằng annotation và dùng **trình kiểm tra kiểu bổ sung** (*pluggable type checker*) để phát hiện vi phạm ngay khi biên dịch. Java 8 đưa ra cú pháp **type annotations**, đặc biệt là `@Target(ElementType.TYPE_USE)` và `TYPE_PARAMETER`, làm nền tảng cho cách mô tả thuộc tính của **cách một kiểu được sử dụng**.

Điểm phải nhớ:

> **Type annotation chỉ mang thông tin. Muốn thông tin đó trở thành quy tắc kiểm tra tĩnh bổ sung, phải có checker thực sự hiểu annotation ấy và phải chạy checker trong quy trình build.** Chỉ viết `@NonNull` hoặc `@Nullable` không tự khiến `javac` chuẩn chứng minh mã không dereference null.

Bài này dùng các đặc tính **vẫn còn hiệu lực trong Java hiện đại**. Mã Java tự chứa chạy trên **JDK 17+** được kiểm chứng độc lập. Phần cấu hình **Checker Framework** là ví dụ dùng thư viện kiểm tra ngoài JDK, được ghi rõ điều kiện cài đặt; không nhầm ví dụ chạy với JDK chuẩn và ví dụ đòi plugin.

## 1. Kiểm tra kiểu tĩnh gốc của Java làm được gì?

Java kiểm tra sẵn các quan hệ kiểu cơ bản:

~~~java
String label = "ready";
int size = label.length();

// int invalid = label; // SAI: String không chuyển thành int.
~~~

Java cũng kiểm tra generic:

~~~java
List<String> messages = new ArrayList<>();
messages.add("hello");
// messages.add(42); // SAI: Integer không phù hợp List<String>.
~~~

Hai đoạn trên chỉ là **mã minh họa trong phương thức**, với `import java.util.*;`. Compiler phát hiện phép gán và phép thêm phần tử sai **trước runtime**.

Tuy vậy, Java thông thường vẫn có thể chấp nhận:

~~~java
String title = null;
System.out.println(title.length()); // Có thể ném NullPointerException khi chạy.
~~~

Hoặc:

~~~java
int total = distance + duration; // Cả hai là int; đơn vị đo có thể không tương thích.
~~~

Ví dụ thứ hai giả sử `distance` và `duration` là các biến `int` đã khai báo. Compiler chỉ thấy hai số nguyên, không biết một số biểu diễn mét còn số kia biểu diễn giây. Những đặc tính như **nullness, độ tin cậy của đầu vào, đơn vị đo, trạng thái khởi tạo, hợp đồng khóa đồng bộ và tính hợp lệ của regex** có thể cần kiểm tra chuyên biệt.

**Hệ thống kiểu bổ sung không thay thế Java type checking**. Nó đặt thêm ràng buộc lên những kiểu đã có. Một chương trình `String` và `List<String>` đúng với Java chưa chắc thỏa các hợp đồng nullness hoặc trust mà dự án đã công bố.

## 2. Ba thành phần của một pluggable type system

Một mô hình đơn giản gồm ba lớp:

1. **Type qualifier annotation**: ký hiệu gắn trên vị trí sử dụng kiểu, ví dụ `@Nullable String`, `List<@NonNull String>`. Annotation cho biết thuộc tính được tuyên bố.
2. **Quy tắc kiểm tra**: định nghĩa các qualifier có quan hệ gì, điều kiện gán/return/tham số nào hợp lệ và khi nào được refinement. Ví dụ một giá trị chứng minh được `@NonNull String` có thể chuyển đến nơi chấp nhận `@Nullable String`; chiều ngược lại cần chứng minh thêm.
3. **Công cụ thực thi checker**: tích hợp `javac`, annotation processing, compiler plugin, build tool hoặc IDE để áp dụng quy tắc lên code và đưa ra diagnostics.

Mô hình:

~~~text
Java source + type-use annotations
             |
             v
Java compiler (cú pháp và kiểu Java cơ bản)
             |
             +--> pluggable checker được bật trong build
                       |
                       +--> đọc qualifier + default rules
                       +--> kiểm tra phép gán, lời gọi, return
                       +--> phân tích control flow và refinement
                       +--> báo lỗi vi phạm hợp đồng bổ sung
             |
             v
Class files nếu build được phép hoàn thành
~~~

Đây là **sơ đồ khái niệm**; cơ chế cài đặt và thứ tự hoạt động cụ thể tùy công cụ. Không phải mọi checker đều dùng một pipeline giống nhau hoặc bảo đảm mọi lỗi thuộc tính sẽ được tìm ra.

### Type qualifier không tạo “một class Java mới”

`@NonNull String` và `@Nullable String` **không phải hai class khác nhau của JVM**. Java vẫn dùng class `String`. Các qualifier là phần thông tin thêm cho checker khi phân tích kiểu; việc kiểm tra quan hệ qualifier thường diễn ra ở **compile time**.

Nếu công cụ kiểm tra không chạy, JVM không tự đọc `@NonNull` để chặn phép gán sai. Tùy `@Retention`, annotation có thể còn trong class file hoặc hiện ra qua reflection, nhưng **metadata còn tồn tại không đồng nghĩa với runtime validation**.

## 3. Type annotation từ Java 8: gắn lên *type use*

Java có annotation từ trước Java 8, chẳng hạn `@Override` hay `@Deprecated`. **Type annotation** mở rộng vị trí được phép gắn annotation vào **cách dùng một kiểu**, không chỉ vào khai báo method/class/field.

### 3.1. `TYPE_USE`

~~~java
import java.lang.annotation.*;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface DemoNonEmpty {
}
~~~

Đây là **khai báo annotation minh họa**; chưa phải một checker. `@Target(TYPE_USE)` cho phép annotation xuất hiện tại các vị trí *type use* hợp lệ của Java, ví dụ:

~~~java
@DemoNonEmpty String title = "hello";
List<@DemoNonEmpty String> labels = new ArrayList<>();
~~~

Trong ví dụ, `@DemoNonEmpty` là **tên do ta tự đặt**. `javac` biết vị trí annotation là hợp lệ; **nó không biết “chuỗi không được rỗng” có nghĩa gì** trừ khi có một checker được viết và bật để kiểm tra hợp đồng đó.

Nếu đổi thành:

~~~java
@DemoNonEmpty String title = "";
~~~

thì **`javac` chuẩn vẫn có thể biên dịch**, vì annotation tự định nghĩa chưa có static checker. Đoạn này mang ý nghĩa ngược với annotation nhưng không vi phạm luật kiểu gốc của Java.

### 3.2. `TYPE_PARAMETER`

`ElementType.TYPE_PARAMETER` cho phép gắn annotation lên **khai báo tham số kiểu**:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface DocumentedTypeParameter {}

class Holder<@DocumentedTypeParameter T> {
    private T value;
}
~~~

Đây là các khai báo minh họa. Phân biệt:

- `class Holder<@X T>`: annotation nằm trên **khai báo type parameter `T`**.
- `List<@X String>`: annotation nằm trên **type argument `String` đang được sử dụng**.

Nếu `@Target` khai báo cả `TYPE_USE` và `TYPE_PARAMETER` thì một annotation có thể phục vụ các vị trí tương ứng. Theo `ElementType`, `TYPE_USE` còn bao gồm một số declaration context liên quan đến khai báo kiểu/type parameter; đừng suy đoán scope chỉ bằng tên enum mà không đọc `@Target` và đặc tả.

### 3.3. Đừng nhầm *declaration annotation* với *type annotation*

~~~java
@Override
public String toString() {
    return "ok";
}
~~~

`@Override` kiểm tra **quan hệ override của khai báo method**, không phải nullness của kiểu `String` trả về.

Một annotation `@Target(ElementType.METHOD)` nằm trên **khai báo phương thức**; `@Target(ElementType.TYPE_USE)` có thể dùng trên **return type** hay thành phần của một generic type. Một annotation có thể cho phép nhiều target, nhưng ý nghĩa của từng vị trí vẫn do công cụ hiểu nó quyết định.

## 4. Qualifier tại từng cấp của generic: vị trí rất quan trọng

Hãy tưởng tượng `@Nullable` và `@NonNull` là qualifier được một checker nullness nhận biết:

~~~java
@Nullable List<@NonNull String> maybeList;
@NonNull List<@Nullable String> valuesWithMissingElements;
~~~

Đây là **cú pháp minh họa cần bộ annotation tương ứng trên classpath** (ví dụ từ Checker Framework) và ngữ nghĩa nullness do checker quy định.

| Kiểu có qualifier | Ý nghĩa dự kiến trong nullness checker |
| --- | --- |
| `@Nullable String` | Giá trị String có thể là `null` |
| `@NonNull String` | Không được null theo hợp đồng qualifier |
| `@Nullable List<@NonNull String>` | **List reference** có thể null, các element theo contract không null nếu có list |
| `@NonNull List<@Nullable String>` | List reference không null, nhưng từng element có thể null |
| `List<@Nullable String>` | Qualifier phần tử là nullable; nullness của chính list theo default của checker |
| `List<@NonNull String>` | Element là non-null; nullness của chính list theo default của checker |

**Không được** diễn giải `List<@Nullable String>` là “list có thể null”. Annotation nằm ở **element type**, không phải outer reference. Phân biệt hai cấp này giúp tìm lỗi nullness trong collections, Optional, Map và nested generics.

Ví dụ với Map:

~~~java
Map<@NonNull String, @Nullable String> lookup;
~~~

Đây là mô hình “khóa không null, giá trị có thể null” theo hợp đồng checker đã chọn. Nó không khiến mọi `Map` tự áp đặt điều kiện đó: cần checker, default rules và tài liệu API phù hợp.

### Annotation trên array

Java còn hỗ trợ type annotations trên từng chiều array. Cú pháp có thể ít trực giác:

~~~java
@NonNull String @Nullable [] array;
~~~

Với kiểu nullness checker phù hợp, qualifier ngay trước `String` hướng tới element/reference loại String, còn qualifier trước dấu `[]` hướng tới **array reference** tại chiều đó. Nếu array nhiều chiều, vị trí qualifier càng quan trọng. Đừng tự diễn giải hai annotation này chỉ như “hai nhãn trên biến”; hãy kiểm tra JLS và hướng dẫn checker khi annotate array phức tạp.

## 5. Annotation đơn lẻ không đủ: cần quy tắc subtyping và kiểm tra dữ liệu

Một checker nullness có thể dùng mô hình thứ tự qualifier:

~~~text
         @Nullable T
             ^
             |
         @NonNull T
~~~

Sơ đồ biểu diễn một **quan hệ subtyping bổ sung về nullness** thường dùng: giá trị chắc chắn non-null có thể được sử dụng nơi chấp nhận nullable; giá trị *có thể null* không được tự động chuyển ngược thành chắc chắn non-null.

Ví dụ khái niệm:

~~~java
@NonNull String always = "ready";
@Nullable String sometimes = fetchLabel();

sometimes = always; // Hợp đồng nullness thường cho phép.
always = sometimes; // Checker cần bằng chứng sometimes không null.
~~~

Đây là **mã minh họa**; `fetchLabel()` phải có trong ứng dụng và annotations phải đến từ checker cụ thể. Thông thường qualifier trên return type của `fetchLabel()` cũng cần được khai báo/thu nhận đúng.

Suy luận của compiler Java về `String` không tự suy ra `@NonNull String` trong mọi hoàn cảnh. Checker có thể bổ sung **flow-sensitive analysis**:

~~~java
static int safeLength(@Nullable String value) {
    if (value == null) {
        return 0;
    }
    return value.length();
}
~~~

Với một Nullness Checker phù hợp, sau `if (value == null) return 0;`, nhánh còn lại chứng minh `value` khác null, vì vậy `value.length()` hợp lệ. Công cụ có thể áp dụng phép *refinement* dựa vào control flow, không chỉ đọc một nhãn cố định.

Lưu ý: refinement có thể khác nhau giữa local variables, fields có thể bị thread khác thay đổi, aliases và methods có side effect. Không nên suy diễn rằng một check null ở đầu phương thức bảo đảm tất cả dereference trong code đồng thời luôn an toàn.

## 6. Ví dụ thực tế: Checker Framework và Nullness Checker

**Checker Framework** là một hệ sinh thái pluggable type checking đang được duy trì. Nó bổ sung các qualifier và checker dùng với Java compiler để kiểm tra những hợp đồng mạnh hơn kiểu Java gốc.

Các checker tiêu biểu trong tài liệu hiện hành gồm:

- **Nullness Checker:** phát hiện những dereference hoặc phép truyền/gán có nguy cơ vi phạm hợp đồng nullness.
- **Initialization Checker:** hỗ trợ bảo đảm các field cần khởi tạo được xử lý đúng.
- **Tainting Checker:** theo dõi dữ liệu chưa được tin cậy khi nó đi qua chương trình, phát hiện việc đưa vào vị trí đòi dữ liệu an toàn theo các quy tắc tương ứng.
- **Regex Checker:** giúp kiểm tra cú pháp regex và một số điều kiện về nhóm capture theo qualifier.
- **Resource Leak Checker:** hỗ trợ kiểm tra hợp đồng đóng/tài nguyên.
- **Index Checker, Lock Checker...:** dùng type qualifiers/analysis cho những loại lỗi khác nhau.

**Mỗi checker có phạm vi và giả định riêng**. Không được hiểu rằng cài Checker Framework một lần thì mọi danh mục rủi ro trên đều được kiểm tra tự động. Cần chọn, bật, cấu hình và đánh giá kết quả của từng checker.

### 6.1. Một bug nullness mà `javac` thông thường có thể bỏ qua

Ví dụ **dùng phụ thuộc bên ngoài**, không thể biên dịch bằng JDK nguyên bản nếu thiếu thư viện annotation:

~~~java
import org.checkerframework.checker.nullness.qual.Nullable;

public class NullnessCase {
    static int broken(@Nullable String text) {
        return text.length(); // Nullness Checker báo nguy cơ dereference.
    }

    static int safe(@Nullable String text) {
        if (text == null) {
            return 0;
        }
        return text.length();
    }
}
~~~

Mã này dùng `@Nullable` thật của Checker Framework, không phải `@DemoNonEmpty` do ta tự định nghĩa. Khi có thư viện annotation và **Nullness Checker** đang chạy, `broken` phải bị cảnh báo/lỗi vì `text` có thể null; `safe` minh họa nhánh kiểm tra null.

Cần phân biệt hai cách build:

1. **`javac` có thư viện chứa `@Nullable` nhưng không chạy checker**: Java kiểm tra annotation tồn tại và vị trí hợp lệ, nhưng **không tự áp quy tắc Nullness Checker**; `broken` vẫn có thể qua compile thông thường.
2. **`javac` chạy Nullness Checker phù hợp**: checker bổ sung phân tích luồng điều khiển và chặn trường hợp vi phạm nullness theo hợp đồng của nó.

### 6.2. Cách bật checker

Theo hướng dẫn chính thức, sau khi cài Checker Framework và cấu hình các JAR đúng phiên bản/JDK, có thể chạy checker bằng tùy chọn:

~~~bash
javac -processor org.checkerframework.checker.nullness.NullnessChecker NullnessCase.java
~~~

**Lệnh trên là dạng lõi minh họa**, không phải lệnh tự đủ trong một thư mục trống: cần dùng **Checker Framework javac wrapper** hoặc cấu hình đúng annotation classpath, processor path và các phụ thuộc cần thiết. Hướng dẫn [Running a checker](https://checkerframework.org/manual/#running-a-checker) và [Installation](https://checkerframework.org/manual/#installation) giải thích cách cài, chạy bằng Maven/Gradle/IDE và tùy chọn tương ứng.

Với bản phân phối của Checker Framework, hướng dẫn còn có cách dùng wrapper javac của bộ cài để hỗ trợ cấu hình classpath và compiler integration. Nếu dự án sử dụng Maven/Gradle, nên đưa checker vào **bước build nhất quán** thay vì chỉ chạy thủ công một file tại máy người lập trình.

**Không tuyên bố `NullnessCase.java` đã được Checker Framework chạy trong ví dụ này**: nó là ví dụ hướng dẫn dùng plugin bên ngoài. Chương trình `PluggableTypesDemo.java` ở phần 10 mới là ví dụ có thể chạy bằng JDK 17 chuẩn và được kiểm tra stdout thực tế.

### 6.3. Lưu ý quan trọng cho JDK 23+

Từ **JDK 23**, `javac` **không còn tự động chạy annotation processors chỉ vì chúng tình cờ nằm trên classpath** như một số cấu hình cũ. Build cần khai báo/đề nghị thực hiện annotation processing bằng tùy chọn phù hợp, chẳng hạn `-processor`, processor path hoặc chính sách `-proc:full` tùy JDK/build system.

Vì vậy, khi chuyển phiên bản JDK hoặc hệ thống build:

- Xác minh checker **thực sự chạy** trong CI, không chỉ có JAR trong dependencies.
- Kiểm tra log/diagnostics hoặc dùng một **negative compile test**: đưa vào code cố ý vi phạm contract và yêu cầu build phải thất bại.
- Dùng cấu hình rõ ràng, tương thích với phiên bản Checker Framework và compiler đang sử dụng.
- Không tắt processing bằng `-proc:none` khi kỳ vọng một checker annotation-processor đang hoạt động.

Điểm này rất quan trọng với yêu cầu **kiến thức hiện hành**. Cách cấu hình phụ thuộc vào phiên bản JDK và compiler, vì vậy nên ưu tiên tài liệu chính thức của công cụ đang dùng thay vì sao chép những hướng dẫn bootclasspath/processor cũ cho JDK 8.

## 7. Vì sao chỉ có `@Retention(RUNTIME)` cũng không kiểm tra được?

`@Retention` mô tả annotation được giữ đến đâu:

| Retention | Tác dụng chính | Có đồng nghĩa với static checker không? |
| --- | --- | --- |
| `SOURCE` | Chỉ tồn tại trong source ở giai đoạn biên dịch | Không; processor/checker vẫn có thể đọc annotation phù hợp trong source |
| `CLASS` | Ghi trong class file nhưng thường không hiển thị qua reflection runtime thông thường | Không |
| `RUNTIME` | Ghi trong class file và có thể truy vấn qua reflection thích hợp | Không |

`@Retention(RUNTIME)` không có nghĩa JVM sẽ **kiểm tra dữ liệu lúc chạy**. Muốn bảo đảm đầu vào không rỗng khi gọi method, vẫn có thể cần một runtime guard:

~~~java
static String requireNonEmpty(String input) {
    if (input == null || input.isEmpty()) {
        throw new IllegalArgumentException("empty");
    }
    return input;
}
~~~

Đây là method minh họa được dùng lại trong chương trình đầy đủ. Runtime guard bảo vệ ngay tại biên giới gọi; static checker có thể cảnh báo lỗi **trước khi chạy** với những trường hợp công cụ suy luận được.

Hai cách **bổ sung** cho nhau:
- Static checker: bắt lỗi sớm, làm rõ hợp đồng và tăng chất lượng code.
- Runtime guard/validation: bảo vệ dữ liệu từ HTTP/JSON/database, reflection, native code, plugin không được kiểm tra hoặc môi trường thực thi khác.

Không nên bỏ mọi validation runtime chỉ vì dự án đã có nullness checker, nhất là với **dữ liệu không tin cậy và boundary bên ngoài**.

## 8. Kiểm tra tĩnh cần phân biệt với annotation processing thông thường

Java cung cấp cơ chế `javax.annotation.processing` (JSR 269) để công cụ đọc các annotation và phần tử chương trình trong lúc biên dịch. **Annotation processor** có thể sinh mã, sinh tài nguyên hoặc báo diagnostic; nhiều công cụ sử dụng hạ tầng compiler/processor để tích hợp.

**Nhưng không phải mọi annotation processor là pluggable type checker**:

| Loại công cụ | Mục tiêu điển hình | Có nhất thiết phân tích qualifier subtyping/flow không? |
| --- | --- | --- |
| Java compiler type checker cơ bản | Kiểm tra kiểu gốc, generics, access, override | Không |
| Code generator dùng annotation processing | Tạo source, mapping, builder, metadata | Không |
| Pluggable type checker | Thêm qualifier và kiểm tra hợp đồng của chúng | Có, trong phạm vi checker |
| Linter/static analyzer | Báo pattern rủi ro hoặc code smell | Không nhất thiết có một qualifier type hierarchy |
| Runtime validator | Xác thực giá trị thực khi chương trình chạy | Không, đó không phải chứng minh tĩnh |

Ví dụ một processor có thể đọc `@GenerateBuilder` để sinh class và không quan tâm nullness. Một Nullness Checker có thể kết hợp qualifier hierarchy, default rules, phân tích flow và annotation trên signature. Sự khác biệt nằm ở **mục đích và phân tích được thực hiện**, không phải công cụ có dùng từ “annotation” hay không.

### “Pluggable” không có nghĩa “mọi thứ thay thế được”

Một checker có thể đưa ra kết luận dựa trên giả định như: thư viện ngoài được mô tả chính xác, annotations đáng tin, reflection/dynamic loading được xử lý phù hợp và các đoạn mã unchecked được quản lý. Kết luận của nó **có phạm vi**. Một thư viện cố ý khai báo sai `@NonNull` trong khi trả null có thể phá điều kiện checker dựa vào, nhất là nếu mã thư viện không nằm trong phạm vi được phân tích.

Với API công khai, đừng dùng annotation mạnh như `@NonNull` để che dữ liệu thực chất nullable. **Contract sai còn nguy hiểm hơn contract không có**, vì nó tạo cảm giác an toàn giả.

## 9. Quy trình xây dựng hệ thống kiểm tra tĩnh trong dự án

Một lộ trình triển khai hiện hành, có thể áp dụng vào CI:

1. **Chọn lỗi cần giảm**: ví dụ `NullPointerException` trong domain layer; hoặc lỗi tài nguyên không được đóng; hoặc dữ liệu chưa được kiểm tra đi đến sensitive sink.
2. **Chọn checker có phạm vi phù hợp**: Nullness/Tainting/Resource Leak/Index... dựa trên tài liệu, khả năng hỗ trợ JDK và thư viện đang dùng.
3. **Thiết lập cấu hình build có thể tái lập**: khóa phiên bản tool, khai báo annotation dependencies, processor path, compiler/plugin settings và JDK toolchain.
4. **Đặt qualifier ở các ranh giới ý nghĩa**: method parameters, return types, field types và generic elements. Tránh annotation dày đặc ở mọi local variable nếu checker đã có suy luận flow phù hợp.
5. **Khai báo/kiểm tra default rules**: ví dụ Nullness Checker có thể coi một số type use không ghi rõ là non-null theo mặc định, nhưng có ngoại lệ và cấu hình; không suy ra “không viết annotation” luôn có cùng nghĩa ở mọi checker.
6. **Chạy checker, sửa lỗi thật**: ưu tiên sửa contract hoặc xử lý null/kiểm tra dữ liệu thay vì tắt warning hàng loạt.
7. **Bổ sung stub/annotation cho thư viện thiếu metadata** nếu checker hỗ trợ, thay vì sửa mã nguồn thư viện không thuộc quyền sở hữu.
8. **Thử một ví dụ cố ý sai** để chắc chắn checker thực sự được bật; cần phân biệt lỗi Java gốc với lỗi chỉ checker mới tìm được.
9. **Đưa bước kiểm tra vào CI** và thống nhất chính sách warning/error, phạm vi source cần kiểm tra, chế độ tăng dần và thời gian build.
10. **Giữ runtime validation ở input boundary**, vì static analysis không thay thế xác thực dữ liệu ngoài hệ thống.

### Ví dụ negative test cho Nullness Checker

~~~java
import org.checkerframework.checker.nullness.qual.Nullable;

class NegativeNullnessTest {
    static int length(@Nullable String s) {
        return s.length(); // Chỉ checker nullness mới cảnh báo vi phạm hợp đồng này.
    }
}
~~~

Đoạn mã là **một file khác dùng để kiểm tra cấu hình tool**; cần checker-qual trên classpath và Nullness Checker hoạt động. Nếu chỉ compile bằng `javac` chuẩn với annotation dependency, việc không có diagnostics **không chứng minh** hệ thống nullness checker đã chạy. Khi checker chạy đúng, dòng dereference phải bị báo theo hợp đồng Nullness Checker.

Nên có thêm **positive test** tương ứng:

~~~java
import org.checkerframework.checker.nullness.qual.Nullable;

class PositiveNullnessTest {
    static int length(@Nullable String s) {
        return s == null ? 0 : s.length();
    }
}
~~~

Trong cấu hình phù hợp, trường hợp này cho thấy checker nhận ra kiểm tra null và có thể chấp nhận. Hai file là ví dụ riêng; không nhập cả hai class vào một file `public` không đúng tên.

## 10. Chương trình Java 17+ độc lập: type-use metadata ≠ enforcement

Chương trình sau tự định nghĩa annotation `@DemoNonEmpty` với `@Target(TYPE_USE, TYPE_PARAMETER)`, giữ metadata đến runtime để kiểm tra bằng reflection. Nó **cố ý** đặt annotation trên chuỗi rỗng: `javac` chuẩn vẫn cho biên dịch vì **chưa hề có checker nào diễn giải “NonEmpty”**. Sau đó chương trình dùng runtime guard để minh họa cách thực thi hợp đồng ở một ranh giới khác.

Lưu thành **PluggableTypesDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class PluggableTypesDemo {
    @Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
    @Retention(RetentionPolicy.RUNTIME)
    @interface DemoNonEmpty {}

    static final class MessageBox {
        List<@DemoNonEmpty String> values =
                List.of("hello", "java");
        @DemoNonEmpty String headline = "hello";
    }

    static String display(@DemoNonEmpty String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    static String requireNonEmpty(String value) {
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        return value;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field valuesField = MessageBox.class.getDeclaredField("values");
        AnnotatedParameterizedType annotated =
                (AnnotatedParameterizedType) valuesField.getAnnotatedType();
        boolean elementTagged =
                annotated.getAnnotatedActualTypeArguments()[0]
                        .isAnnotationPresent(DemoNonEmpty.class);

        Field headlineField = MessageBox.class.getDeclaredField("headline");
        boolean fieldTypeTagged = headlineField.getAnnotatedType()
                .isAnnotationPresent(DemoNonEmpty.class);

        Method displayMethod = PluggableTypesDemo.class
                .getDeclaredMethod("display", String.class);
        boolean parameterTagged =
                displayMethod.getAnnotatedParameterTypes()[0]
                        .isAnnotationPresent(DemoNonEmpty.class);

        @DemoNonEmpty String invalid = "";
        List<@DemoNonEmpty String> alsoInvalid = List.of("");

        System.out.println("elementTagged=" + elementTagged);
        System.out.println("fieldTypeTagged=" + fieldTypeTagged);
        System.out.println("parameterTagged=" + parameterTagged);
        System.out.println("annotationDoesNotCheck=" + invalid.isEmpty());
        System.out.println("nestedUnchecked=" + alsoInvalid.get(0).isEmpty());
        System.out.println("valid=" + display(requireNonEmpty("safe")));
        try {
            requireNonEmpty(invalid);
        } catch (IllegalArgumentException expected) {
            System.out.println("runtimeGuard=" + expected.getMessage());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 PluggableTypesDemo.java
java PluggableTypesDemo
~~~

**Stdout đã kiểm chứng bằng chạy thực tế:**

~~~text
elementTagged=true
fieldTypeTagged=true
parameterTagged=true
annotationDoesNotCheck=true
nestedUnchecked=true
valid=SAFE
runtimeGuard=empty
~~~

### Giải thích từng kết quả

1. `elementTagged=true`: reflection đọc được annotation đặt trên **type argument `String`** nằm trong `List<...>`, không phải annotation trên khai báo field `values`.
2. `fieldTypeTagged=true`: reflection đọc annotation của **field type** `@DemoNonEmpty String`.
3. `parameterTagged=true`: reflection đọc annotation của **kiểu tham số** của method `display`.
4. `annotationDoesNotCheck=true`: `@DemoNonEmpty String invalid = "";` vẫn được `javac` chấp nhận. Đây là ví dụ **chủ động minh họa giới hạn** của annotation, không phải khuyến nghị viết contract sai.
5. `nestedUnchecked=true`: ngay cả `List<@DemoNonEmpty String>` cũng có thể chứa chuỗi rỗng nếu không có checker/rule tương ứng. Java generic checking chỉ biết element type là String.
6. `valid=SAFE`: `requireNonEmpty("safe")` chạy validation runtime rồi `display` chuyển thành chữ hoa.
7. `runtimeGuard=empty`: khi gọi `requireNonEmpty(invalid)` với chuỗi rỗng, runtime guard thực sự ném `IllegalArgumentException`; chương trình bắt và in message.

**Đừng nhầm reflection với type checking:** ở đây reflection chỉ **đọc metadata** từ type-use annotations có retention `RUNTIME`. Nó không kiểm tra semantic value. Đặc biệt, `MessageBox` chỉ phục vụ minh họa vị trí gắn annotation; chương trình không khai báo `@DemoNonEmpty` là qualifier được Checker Framework nhận biết. **Nếu muốn bảo đảm static NonEmpty**, cần định nghĩa qualifier đúng quy tắc của một checker và xây dựng/triển khai checker phân tích giá trị phù hợp, hoặc dùng checker có hợp đồng tương đương đã được hỗ trợ.

## 11. Pluggable types và an toàn ở các API hiện đại

### 11.1. Kiểm tra nullness cho Optional

`Optional<T>` thể hiện có hoặc không có giá trị trong một container theo API Java; nó **không làm `@Nullable` trên mọi kiểu trở nên dư thừa**. Ví dụ method có thể trả `Optional<String>` thay vì trả String nullable, nhưng các tham số, fields và phần tử collections vẫn có thể cần hợp đồng nullness riêng.

~~~java
Optional<String> maybeName = Optional.ofNullable(source);
String printable = maybeName.orElse("(missing)");
~~~

Đoạn minh họa giả định `source` là String có thể null và đã import `java.util.Optional`. `Optional` giúp diễn tả một số nhánh vắng mặt rõ ràng; một checker bổ sung có thể phân tích hợp đồng Optional hoặc nullness theo scope riêng. Không dùng `Optional.get()` vô điều kiện và nghĩ rằng pluggable nullness checker tự sửa mọi sai lầm.

### 11.2. Checker cho dữ liệu không tin cậy

Một type qualifier có thể biểu diễn **tainted** / **untainted**, dùng các quy tắc để theo dõi giá trị được nhận từ nguồn không tin cậy và những điểm tiêu thụ cần dữ liệu đã được xử lý đúng.

Ví dụ khái niệm:

~~~java
@Tainted String raw = requestParameter();
@Untainted String cleaned = validateAndNormalize(raw);
sendToSensitiveSink(cleaned);
~~~

**Đây chỉ là pseudocode minh họa contract**, không phải chương trình độc lập: `@Tainted`, `@Untainted`, `requestParameter`, `validateAndNormalize` và `sendToSensitiveSink` phải được khai báo/tích hợp theo công cụ cụ thể. Bản thân Java không có các qualifier này trong `java.lang`, và một hàm đặt tên `validateAndNormalize` không tự động tạo chứng nhận rằng dữ liệu an toàn.

**Quan trọng về bảo mật:** với SQL, giải pháp mặc định an toàn là **prepared statements với parameter binding**; không thay bằng việc dựa duy nhất vào annotation hoặc một hàm “sanitize” chung chung. Checker cung cấp thêm một tầng bảo vệ, không thay công cụ phòng vệ phù hợp từng sink.

### 11.3. Regex, resource và trạng thái đối tượng

Qualifier có thể diễn đạt các thuộc tính không nằm trong kiểu cơ bản như “chuỗi đã biết là regex hợp lệ” hoặc “tài nguyên đang cần đóng”. Một checker có thể theo dõi những thuộc tính ấy qua các lệnh Java. Nhưng mỗi domain cần **mô hình riêng**; không thể dùng `@NonNull` để kiểm tra mọi lỗi regex, hoặc dùng `@Regex` để bảo đảm tài nguyên sẽ được đóng.

Chọn checker theo **loại bug cần giảm** và xác minh phạm vi hỗ trợ: checker nào cũng có những điều kiện ngoại lệ, default rules và loại code không phân tích được hoàn toàn.

## 12. Rủi ro và giới hạn phải hiểu

| Tình huống | Vì sao dễ hiểu nhầm | Cách xử lý đúng |
| --- | --- | --- |
| Chỉ thêm annotation vào source | Nghĩ annotation tự cưỡng chế nghĩa | Bật checker đúng loại và đưa vào build |
| Có `@Retention(RUNTIME)` | Nghĩ JVM sẽ validate | Retention chỉ cho biết metadata được giữ đến đâu |
| Code được `javac` chấp nhận | Nghĩ hợp đồng nullness đã được chứng minh | Chạy negative test với checker và xem diagnostics |
| Checker bật trên một module nhưng không chạy ở module khác | Build có phạm vi kiểm tra không đồng nhất | Khai báo rõ phạm vi và kiểm tra CI |
| Thư viện ngoài không có qualifier | Checker phải dựa vào giả định/defaults có thể thiếu chính xác | Dùng annotation stubs hoặc signature metadata theo hướng dẫn |
| Kết quả checker sạch | Nghĩ không cần kiểm tra dữ liệu từ bên ngoài | Giữ validation runtime ở trust boundary |
| `List<@Nullable T>` | Nhầm list reference nullable | Annotation nằm trên element type |
| `@Nullable List<T>` | Nhầm element nullable | Annotation nằm trên outer list type |
| Mã raw/unchecked cast | Có thể làm suy yếu các cam kết kiểu | Giảm unchecked cast và kiểm soát API boundary |
| Annotation và checker dùng phiên bản không tương thích | Có thể lỗi compile hoặc sai cấu hình | Khóa version tool, JDK và hướng dẫn build |
| Tự định nghĩa `@NonEmpty` | Nghĩ công cụ nullness mặc định sẽ hiểu | Phải chọn checker có semantics tương ứng hoặc viết custom checker |
| Tắt warning quá rộng | Che lỗi nghiêm trọng | Chỉ suppress ở phạm vi hẹp, có lý do và test |
| Reflection, native code hoặc dữ liệu động | Thông tin runtime vượt khỏi phạm vi phân tích tĩnh | Dùng kiểm tra ranh giới và contract chính xác |
| Phân tích flow trên object chia sẻ | State có thể đổi qua alias/thread khác | Kết hợp thread-safety, immutable design hoặc synchronization |
| Một checker báo an toàn | Nghĩ mọi loại lỗi đều biến mất | Kết luận chỉ đúng cho loại bug và giả định mà checker kiểm tra |

### Điều gì là “static guarantee”?

Một checker mạnh có thể hứa hẹn phát hiện một loại lỗi nhất định **trong đoạn code được kiểm tra dưới các giả định của checker**. Những giả định như đúng annotations của thư viện, không dùng lối tắt unsafe và phạm vi phân tích đầy đủ là phần của lời bảo đảm. Hãy đọc phần *What the checker guarantees* trong manual của checker đang dùng.

Không nên viết “đã cài Nullness Checker, toàn bộ ứng dụng không bao giờ có NPE” nếu vẫn có mã ngoại vi, reflection, unchecked assumptions, processor chưa chạy ở một số module hoặc runtime dữ liệu chưa được kiểm tra.

## 13. Bảng quyết định: lúc nào cần pluggable type checker?

| Dấu hiệu trong dự án | Pluggable checker có thể hữu ích khi... | Biện pháp song hành |
| --- | --- | --- |
| Nhiều NPE từ dữ liệu null không được công bố | Muốn hợp đồng nullness có thể kiểm tra giữa method/modules | Validation đầu vào, test null cases |
| Nhiều nguồn dữ liệu không tin cậy | Muốn theo dõi nguồn/sink với quy tắc taint rõ | Parameterized queries, escaping theo context |
| Dùng regex từ nhiều nơi | Muốn bắt lỗi regex đã biết ở compile time | Test với input thực |
| Dùng resource có lifecycle phức tạp | Muốn kiểm tra khả năng leak/close obligation | Try-with-resources, integration tests |
| Lẫn đơn vị đo / chỉ số | Muốn bổ sung qualifier và luật phép toán | Kiểu domain rõ, property tests |
| Có API Java public lớn | Muốn contract cho field/return/generic elements | JavaDoc, semantic versioning, runtime boundary checks |
| Dự án rất nhỏ, ít rủi ro | Chi phí cấu hình có thể vượt lợi ích | Java typing gốc + test/validation |

Checker mang lại lợi ích rõ nhất khi **hợp đồng bổ sung có giá trị trên nhiều điểm gọi** và được **thực thi nhất quán**. Nếu một ràng buộc chỉ áp dụng cho một nhánh nghiệp vụ duy nhất, một **domain type** hay runtime validation có thể đơn giản và bền hơn một hệ qualifier tùy biến phức tạp.

## 14. Bài tập tự kiểm tra

1. `@Target(TYPE_USE)` cho phép annotation xuất hiện ở những vị trí nào khác với `@Target(METHOD)`? Hãy nêu ví dụ với generic type argument.
2. Vì sao `@DemoNonEmpty String x = "";` vẫn có thể biên dịch bằng `javac` chuẩn?
3. Phân biệt `@Nullable List<@NonNull String>` với `@NonNull List<@Nullable String>`. Vị trí nào mô tả nullness của collection, vị trí nào của element?
4. Nếu một Nullness Checker biết `@NonNull String` là subtype của `@Nullable String`, phép gán theo chiều nào luôn an toàn hơn?
5. Vì sao `if (value == null) return;` giúp checker cho phép dereference `value` ở phía sau trong nhiều trường hợp?
6. `@Retention(RUNTIME)` có tự triển khai runtime validation không? Reflection có thể đọc type-use annotation trong Java như thế nào?
7. So sánh code generator annotation processor và pluggable static type checker. Vì sao không thể đồng nhất chúng?
8. Khi nâng lên JDK 23+, điều gì có thể xảy ra nếu build dựa vào processor auto-discovery không cấu hình tường minh?
9. Hãy viết một negative compile test với `@Nullable String` và `text.length()`; build có phụ thuộc nhưng không chạy checker có được coi là kiểm thử thành công không?
10. Vì sao một checker nullness không đồng nghĩa bảo vệ khỏi SQL injection? Công cụ nào phải dùng với câu lệnh SQL chứa dữ liệu người dùng?
11. Nêu ba nơi nên đặt qualifier trước khi phủ annotations lên mọi local variable: tham số API, return type và generic element types.
12. Khi dùng một thư viện không có nullness annotations, bạn sẽ bổ sung metadata một cách bảo trì được bằng cách nào?
13. Mã có `List<String>` nhưng chứa logic phân biệt chuỗi “trusted” và “untrusted”. Kiểu Java gốc còn thiếu thông tin gì?
14. Tại sao type erasure không biến mọi `List<@Nullable String>` thành một kiểu runtime khác với `List<String>`?
15. Hãy mô tả một quy trình CI chứng minh checker thực sự hoạt động thay vì chỉ có dependencies trên classpath.

## 15. Tài liệu chính thức và tiếp tục học

- [Java Language Specification — `9.7.4 Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.7.4)
- [Java Language Specification — `4.11 Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.11)
- [Java SE 17 — `ElementType.TYPE_USE` và `TYPE_PARAMETER`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Checker Framework Manual — Introduction, Nullness Checker và Running a checker](https://checkerframework.org/manual/)
- [Checker Framework — Nullness Checker](https://checkerframework.org/manual/#nullness-checker)
- [OpenJDK — JDK 23 annotation processing default change](https://inside.java/2024/06/18/quality-heads-up/)
- [javac Tool Reference — `-processor` / `-proc`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)

**Kết luận:** **Type-use annotation** cho phép mô tả thuộc tính trên kiểu Java ở những vị trí tinh hơn như generic elements và method parameters. **Pluggable type checker** mới là thành phần biến thông tin qualifier thành kiểm tra tĩnh có ý nghĩa, dựa trên quan hệ qualifier và phân tích mã. Trong Java hiện đại, hãy **bật checker rõ ràng trong build/CI, xác minh bằng negative test, giữ contract đúng và tiếp tục validation runtime ở ranh giới dữ liệu không tin cậy**. Không đánh đồng annotation, reflection, annotation processing và static type checking.
