# Cân bằng tính linh hoạt, độ dễ hiểu và khả năng suy luận kiểu trong Java Generic API

Một API có thể đúng về mặt hệ kiểu mà **khó gọi, khó đọc và khó nâng cấp**. Ngược lại, một chữ ký quá đơn giản có thể buộc caller phải sao chép dữ liệu hoặc ép kiểu không an toàn. Khi phát hành một API generic, mục tiêu là cân bằng ba yếu tố:

1. **Linh hoạt đúng nhu cầu:** nhận những nguồn/đích khác type arguments nhưng vẫn giữ ràng buộc cần thiết.
2. **Rõ hợp đồng:** chỉ nhìn tên method, parameters và kết quả là người đọc hiểu luồng dữ liệu, mutability và các điều kiện cần.
3. **Compiler dễ suy luận:** phần lớn call sites không phải ép kiểu, gõ explicit type witness hay cast lambda để javac chọn một lời gọi.

Bài này là **bài tổng hợp theo tình huống review API**, không lặp lại toàn bộ chứng minh invariance, PECS hoặc wildcard capture. Ta sẽ cùng thiết kế một pipeline xử lý events, đánh giá nhiều chữ ký thay thế, thử inference tại nơi gọi, kiểm tra ví dụ Java 17 và tìm rủi ro khi đổi public API.

## 1. Bắt đầu từ nơi gọi: mỗi quyết định phục vụ một yêu cầu

Giả sử ứng dụng có hai loại sự kiện:

~~~java
interface Tagged {
    String tag();
}
record Alert(String tag) implements Tagged {}
record Note(String tag) implements Tagged {}
~~~

Cần:
- Lấy những `Alert` có tag bắt đầu bằng `"a"`.
- Biến chúng thành danh sách String để hiển thị.
- Đưa kết quả đã chọn vào một collection theo dõi chung.
- Chỉnh sửa nội dung của một danh sách Alert mutable mà **giữ nguyên type argument Alert**.
- Gộp Alert và Note thành một danh sách Tagged mà không làm sai collection gốc.

Trước khi viết `<T>`, hãy phác thảo call sites mong muốn:

~~~java
List<Alert> alerts = List.of(
        new Alert("alpha"),
        new Alert("beta"),
        new Alert("atlas"));

Predicate<Tagged> beginsA =
        event -> event.tag().startsWith("a");

List<Tagged> chosen = select(alerts, beginsA);
List<String> labels = mapAll(chosen, Tagged::tag);

List<Object> audit = new ArrayList<>();
appendAll(chosen, audit);
~~~

Mục tiêu là viết được những lời gọi ấy **không unchecked cast và không copy chỉ để vượt incompatibility do type arguments**. Chữ ký API được thiết kế ngược từ nhu cầu đã xác định.

### Ba câu hỏi phải trả lời cho từng phương thức

- **Dữ liệu chảy về đâu?** Chỉ đọc nguồn, ghi vào đích, hay vừa đọc vừa ghi cùng nơi?
- **Kiểu được liên kết ở đâu?** Cần cùng T giữa source và output, hay chỉ một interface chung như Tagged?
- **Giá trị trả ra thuộc hợp đồng nào?** Một List<T> mới, Optional<T>, số lượng, hay side effect trên collection cũ?

Không cần type variable ở mọi method. Ví dụ chỉ lấy số lượng nên đủ dùng:

~~~java
static int count(Collection<?> values) {
    return values.size();
}
~~~

Chữ ký này không kém an toàn hơn một `<T> int count(Collection<T>)` trong trường hợp chỉ gọi `size()`; ngược lại, nó cho người đọc biết element type không liên quan.

## 2. Chấm một chữ ký theo ba chiều

| Tiêu chí | Câu hỏi review | Dấu hiệu chưa tốt |
| --- | --- | --- |
| **Linh hoạt** | Có nhận được List<Alert>, List<Note>, List<Tagged> khi thuật toán chỉ cần Tagged? | Caller phải copy sang List<Tagged> chỉ để gọi hàm đọc. |
| **Rõ nghĩa** | Tham số nào bị sửa? Kết quả có alias nguồn không? | Tên `copy` nhưng lại append vào đích, hoặc tên `select` nhưng trả view mutable không báo. |
| **Suy luận kiểu** | Java tự biết T/R từ arguments, callback và expected type? | Hầu hết callers phải viết `.<Tagged>` hoặc ép lambda vì chữ ký/overloads mơ hồ. |
| **Hạn chế runtime** | Null, empty, mutability, order, exception và partial failure có rõ? | Generic signature đúng nhưng implementation làm sai kỳ vọng dữ liệu. |
| **Tương thích** | Thay chữ ký có đổi erased descriptor, nguồn gọi hay overload resolution? | Một cải tiến PECS làm client binary cũ mất method. |

Không cần API “tổng quát nhất”: một method chỉ phục vụ domain cụ thể thường nên nhận interface domain cụ thể. Type parameters và wildcards là công cụ diễn đạt hợp đồng, không phải thành tích cần tối đa hóa.

## 3. Thiết kế nguồn đọc: `? extends T` và callback nhận supertype

Đối với phép lọc, chúng ta muốn caller truyền danh sách Alert **và** một Predicate biết làm việc với interface Tagged.

~~~java
static <T> List<T> select(
        Iterable<? extends T> source,
        Predicate<? super T> predicate) {

    List<T> result = new ArrayList<>();

    for (T value : source) {
        if (predicate.test(value)) {
            result.add(value);
        }
    }

    return result;
}
~~~

Cấu trúc có chủ đích:
- `Iterable<? extends T>`: chỉ cần duyệt phần tử từ producer, không cần index hoặc mutation.
- `Predicate<? super T>`: predicate tiêu thụ T, nên có thể là một predicate nhận supertype như Tagged.
- `List<T>`: caller nhận **collection mới** với element type được suy luận; không phải wildcard result làm hạn chế thao tác không cần thiết.

Ở call site:

~~~java
List<Tagged> chosen = select(alerts, beginsA);
~~~

Compiler có thể chọn T phù hợp với Alert ở nguồn, Tagged ở predicate và **target type List<Tagged>**. Do đó callers không cần cast List<Alert> thành List<Tagged> — phép cast đó vốn không hợp lệ dưới invariance.

Một biến thể:

~~~java
List<Alert> chosenAlerts = select(alerts, beginsA);
~~~

cũng có thể hợp lệ. Trong trường hợp này T được suy luận phù hợp với Alert. Cùng một generic method hỗ trợ cả hai cách yêu cầu output mà không ghi sai type arguments của nguồn.

### Biến `var` và target typing

~~~java
var selected = select(alerts, beginsA);
~~~

`var` không viết rõ expected type List<Tagged> ở vế trái. Compiler suy luận theo những ràng buộc còn lại, và kết quả có thể khác với lời gọi có target type tường minh. Không nên dạy rằng `var` luôn suy ra **ý định nghiệp vụ** của caller.

Nếu downstream cần chính xác `List<Tagged>`, khai báo kiểu đích tường minh thường tốt hơn việc bắt caller thêm unchecked cast sau đó.

## 4. Biến đổi kết quả: đặt tên T/R theo chiều dữ liệu

Một mapper đọc dữ liệu thuộc T và **sản xuất loại kết quả R mới**:

~~~java
static <T, R> List<R> mapAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper) {

    List<R> result = new ArrayList<>();

    for (T value : source) {
        result.add(mapper.apply(value));
    }

    return result;
}
~~~

Có hai ràng buộc đáng được đặt tên:
- `T` liên kết elements nguồn với input của mapper.
- `R` liên kết output mapper với elements của list kết quả.

Gọi:

~~~java
List<String> names = mapAll(chosen, Tagged::tag);
~~~

`Tagged::tag` là method reference có target functional interface được suy luận từ lời gọi. Không cần `Function<Object,Object>`, cũng không cần ép kiểu toàn bộ list xuống Object.

**Nhưng** nếu API chỉ có nhiệm vụ cụ thể “lấy tag từ Tagged”, một method `List<String> tags(Iterable<? extends Tagged>)` có thể dễ hiểu hơn generic `mapAll`. Chỉ tạo một helper tổng quát khi nó thật sự giảm lặp và có nhiều use cases hợp lý.

### Đừng lạm dụng interface rộng

Nếu method cần `get(index)` hoặc `replaceAll`, nhận `List<T>` thay vì `Iterable<T>` vì cần hành vi của List. Ngược lại, một method chỉ lặp không cần bắt caller cấp random-access list.

Một interface quá rộng **về quyền thao tác** làm implementation thiếu contract; một interface quá hẹp **về dạng collection** buộc caller làm adapter vô ích.

## 5. Đích nhận dữ liệu: dùng PECS nhưng không che side effects

Khi muốn append các events vào collection theo dõi:

~~~java
static <T> void appendAll(
        Iterable<? extends T> source,
        Collection<? super T> destination) {

    for (T value : source) {
        destination.add(value);
    }
}
~~~

Chữ ký mô tả một chiều:
- Source đọc ra T.
- Destination nhận T hoặc subtype của T thích hợp.
- Một `<T>` liên kết hai phía; hai dấu `?` hoàn toàn độc lập **không chứng minh** chúng có thể trao đổi elements.

Ví dụ:

~~~java
List<Object> audit = new ArrayList<>();
appendAll(chosen, audit);
~~~

Không có ý định đọc giá trị từ audit rồi ghi ngược về source. Nếu cần trao đổi hai chiều giữa danh sách, phải thiết kế một hợp đồng mạnh hơn, có thể yêu cầu `List<T>` ở cả hai phía.

Đặt tên `appendAll` rõ rằng destination **tăng thêm phần tử**. Phương thức JDK `Collections.copy(dest,src)` cũng dùng PECS nhưng **thay theo index** và đòi destination có đủ size; đừng bắt chước tên `copy` mà thay hành vi.

Cần mô tả thêm nếu public:
- Destination phải hỗ trợ `add`, không phải mọi Collection đều mutable.
- Nếu source/destination có alias và thực hiện append khi đang iterate, hành vi có thể lỗi hoặc không phù hợp; có thể yêu cầu không alias hoặc snapshot.
- Nếu `add` ném exception ở giữa, một số phần tử có thể đã được thêm; không tự hứa atomic operation.
- Collection có thể không giữ duplicates hoặc iteration order theo cách người dùng kỳ vọng.

Generics chỉ giải quyết **tính tương thích của phần tử**, không giải quyết hết các điều kiện runtime này.

## 6. Khi cần đọc rồi ghi lại cùng loại, giữ `List<T>`

Một phép sửa tại chỗ:

~~~java
static <T> void rewrite(
        List<T> values,
        UnaryOperator<T> editor) {

    values.replaceAll(editor);
}
~~~

Chữ ký này có chủ đích dùng **exact named T**: đọc T, biến đổi thành T, ghi T về **cùng list**. Nó không phải bài toán “source producer, target consumer” độc lập.

Ví dụ:

~~~java
List<Alert> editable = new ArrayList<>(alerts);

rewrite(editable,
        alert -> new Alert(alert.tag().toUpperCase()));
~~~

Nếu thay toàn bộ thành `List<? extends Tagged>` thì compiler không thể bảo đảm một Tagged bất kỳ có thể ghi vào một list thực tế đang là List<Alert>. Nếu dùng `List<? super Alert>`, phía đọc chỉ được bảo đảm như Object. Quan hệ một T có tên là phần hợp đồng cần giữ.

Chọn `List<T>` hay `Map<K,V>` khi method cần đọc và cập nhật cùng type contract; dùng wildcard khi có một chiều linh hoạt. **Đừng dùng raw cast để đánh lừa hệ kiểu.**

## 7. Một ví dụ Java 17 hoàn chỉnh để đánh giá cả pipeline

Lưu tệp **GenericApiDecisionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;

public class GenericApiDecisionDemo {
    interface Tagged {
        String tag();
    }

    record Alert(String tag) implements Tagged {}
    record Note(String tag) implements Tagged {}

    static int count(Collection<?> values) {
        return values.size();
    }

    static <T> List<T> select(
            Iterable<? extends T> source,
            Predicate<? super T> predicate) {

        List<T> result = new ArrayList<>();
        for (T value : source) {
            if (predicate.test(value)) {
                result.add(value);
            }
        }
        return result;
    }

    static <T, R> List<R> mapAll(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    static <T> void appendAll(
            Iterable<? extends T> source,
            Collection<? super T> destination) {

        for (T value : source) {
            destination.add(value);
        }
    }

    static <T> void rewrite(
            List<T> values, UnaryOperator<T> mapper) {

        values.replaceAll(mapper);
    }

    public static void main(String[] args) {
        List<Alert> alerts = List.of(
                new Alert("alpha"),
                new Alert("beta"),
                new Alert("atlas")
        );

        Predicate<Tagged> beginsA =
                event -> event.tag().startsWith("a");

        List<Tagged> chosen = select(alerts, beginsA);
        System.out.println(
                "chosen=" + mapAll(chosen, Tagged::tag)
        );
        System.out.println("count=" + count(chosen));

        List<Object> audit = new ArrayList<>();
        appendAll(chosen, audit);
        System.out.println("audit=" + audit.size());

        List<Alert> editable = new ArrayList<>(alerts);
        rewrite(editable,
                alert -> new Alert(
                        alert.tag().toUpperCase()));
        System.out.println(
                "edited=" + mapAll(editable, Alert::tag)
        );

        List<Note> notes = List.of(new Note("gamma"));
        List<Tagged> all = new ArrayList<>();
        appendAll(alerts, all);
        appendAll(notes, all);
        System.out.println(
                "all=" + mapAll(all, Tagged::tag)
        );
        System.out.println(
                "source=" + mapAll(alerts, Alert::tag)
        );
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -Xlint:all GenericApiDecisionDemo.java
java GenericApiDecisionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
chosen=[alpha, atlas]
count=2
audit=2
edited=[ALPHA, BETA, ATLAS]
all=[alpha, beta, atlas, gamma]
source=[alpha, beta, atlas]
~~~

**Tại sao đây là ví dụ về quyết định thiết kế, không chỉ demo syntax?**

- `chosen`: kết quả List<Tagged> được suy luận theo type target, dù nguồn là List<Alert>.
- `mapAll`: trả List<String> từ callback Tagged::tag mà caller không cast.
- `audit`: source đọc như Tagged, đích List<Object> nhận được nhờ `? super T`; phương thức có side effect rõ.
- `editable`: phép sửa tại chỗ giữ chính loại Alert; nguồn List.of không bị sửa.
- `all`: ghép Alert và Note vào danh sách Tagged mà không ép kiểu một List<Alert> thành List<Tagged>.
- `source`: nguồn ban đầu còn nguyên, cho thấy những thao tác nào tạo list mới và thao tác nào thay đổi nơi khác.

Thử thay `Predicate<Tagged>` bằng một predicate chỉ nhận `Note`. Compiler phải từ chối lời gọi `select(alerts, predicateOfNote)` nếu không có kiểu T thỏa ràng buộc; không dùng unchecked cast để làm cho lời gọi sai ý nghĩa chạy được.

## 8. Target typing, lambda và type inference: lỗi thường nằm ở call site

Một generic method có thể dùng thông tin từ:
- Argument types.
- Target type ở assignment, return hoặc invocation contexts theo quy tắc Java.
- Functional interface target của lambda/method reference.
- Bounds và wildcard constraints của các type variables.

Bởi vậy, **cùng tên method không bảo đảm mọi lời gọi chọn cùng một T**:

~~~java
List<Alert> onlyAlerts = select(alerts, beginsA);
List<Tagged> anyTagged = select(alerts, beginsA);
~~~

Cả hai cách dùng giữ quan hệ được compiler kiểm tra; chúng không làm ArrayList/List mang runtime class riêng cho từng type parameter.

### Khi inference không rõ, sửa hợp đồng trước

Một mẹo debug được phép là tách lời gọi thành các biến trung gian có type rõ:

~~~java
Predicate<Tagged> selectedByTag =
        element -> element.tag().startsWith("a");

List<Tagged> filtered =
        select(alerts, selectedByTag);

List<String> labels =
        mapAll(filtered, Tagged::tag);
~~~

Đừng bắt caller lặp đi lặp lại `(Function<...>)`, raw `List` hoặc `MyApi.<Object>...` chỉ để chữa một API thiết kế quá khó suy luận.

Dù vậy, **một số explicit type witness** là hợp lý trong trường hợp hiếm gặp, đặc biệt khi mục đích lựa chọn T không thể hiện rõ từ đối số. Đánh giá API dựa trên các use cases thường nhật, không đòi inference thần kỳ ở mọi expression.

## 9. Overload dễ nhập nhằng: đừng tạo hai functional targets ngang nhau

Hai overload sau có erased parameters khác nhau nên có thể cùng tồn tại:

~~~java
static void load(
        java.util.function.Supplier<String> source) {}

static void load(
        java.util.concurrent.Callable<String> source) {}
~~~

Nhưng lời gọi:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
// load(() -> "ready");
~~~

có thể **ambiguous** vì lambda không tự mang một functional interface class cụ thể. Compiler không nên phải đoán xem tác giả muốn Supplier hay Callable chỉ từ body trả String.

Cách giải quyết:
- Đặt hai tên diễn đạt nghiệp vụ (`loadFromSupplier`, `loadFromCallable`) nếu hợp đồng xử lý khác nhau.
- Chọn một functional interface làm public contract nếu hai overload chỉ gây trùng nghĩa.
- Khi thực sự cần hai overloads, caller có thể cung cấp một biến typed, chẳng hạn:

~~~java
java.util.function.Supplier<String> supplier =
        () -> "ready";

// load(supplier); // Sẽ chọn overload Supplier.
~~~

Nếu hai overload đều nhận `List<String>` và `List<Integer>`, vấn đề còn sớm hơn: do erasure chúng **cùng erased signature** và không thể khai báo cạnh nhau trong một class. Không cố dùng runtime type arguments để dispatch, vì Java overload resolution dựa trên compile-time types.

## 10. Public API: linh hoạt hơn chưa chắc tương thích với bản cũ

Giả sử bản v1 công bố:

~~~java
void inspect(List<Tagged> events)
~~~

Bản v2 muốn chấp nhận nhiều nguồn và đổi thành:

~~~java
void inspect(Collection<? extends Tagged> events)
~~~

Bản mới có thể tốt hơn về **source flexibility**, nhưng raw parameter class đã đổi **List → Collection**. JVM method descriptor vì thế thay đổi. Một client `.class` cũ có thể vẫn tìm phương thức nhận List, và gặp lỗi liên kết như NoSuchMethodError nếu descriptor cũ không được giữ lại.

Trong khi đó, đổi một type argument/wildcard trên cùng raw List đôi khi giữ descriptor tương đương, **nhưng** source overload resolution, generic signature/reflection và type inference có thể thay đổi.

Đừng suy rằng “chỉ sửa phần chữ trong dấu `<...>` thì chắc chắn tương thích”. Cần phân biệt:
1. **Source compatibility:** caller có biên dịch lại với v2?
2. **Binary compatibility:** caller `.class` từ v1 còn liên kết với v2?
3. **Behavioral compatibility:** null, order, mutation, exceptions và semantics có đổi?
4. **Reflection/tool compatibility:** generic Signature metadata hoặc bounds có khác?

### Cách kiểm chứng một thay đổi public API

~~~bash
# Biên dịch các phiên bản v1/v2 ở thư mục class riêng.
javap -p -s YourLibraryClass
javap -v YourLibraryClass

# Chạy client đã biên dịch bằng v1 cùng library v2,
# KHÔNG biên dịch lại client ở phép thử binary compatibility.
~~~

Nếu đổi bounds của type variable, đặc biệt leftmost bound, erased return/parameter descriptors có thể đổi dù tên method vẫn vậy. Khi thư viện đã phát hành, không sửa API dựa trên cảm giác một chữ ký “dễ đọc hơn”; đối chiếu class files và thử binary client cũ.

## 11. Những yếu tố hệ kiểu không bảo đảm

| Điều hệ kiểu thể hiện | Điều vẫn phải ghi trong hợp đồng |
| --- | --- |
| Source cho phép đọc T, destination cho phép nhận T. | Destination có mutable không, append có thể partial failure không. |
| Return type là List<T>. | List mới hay view, mutable hay unmodifiable, có alias dữ liệu không. |
| Callback nhận T và trả R. | Callback có thể ném exception, thay đổi trạng thái, trả null không. |
| `Optional<T>` chứa giá trị T khi có. | Không tìm thấy khác lỗi dữ liệu, Optional.empty() được dùng khi nào. |
| `Comparator<? super T>` có thể so sánh T. | Null ordering, tính nhất quán, sort stability theo contract. |
| `Class<T>` đại diện một runtime class. | Không phải type token tự xác thực nested type arguments. |
| Type parameter có bounds. | Bounds không mô tả domain semantics, limits hoặc authorization. |

Ví dụ `List.copyOf(source)` không cho sửa cấu trúc list qua API thông thường và không cho null elements, nhưng nó không deep-copy các element objects mutable. Nếu user đồng thời thay đổi source không đồng bộ, việc lấy snapshot cũng cần chính sách thread safety riêng.

Một API dễ dùng cần tài liệu hóa các điều kiện runtime **ngắn và chính xác** thay vì giả định generics tự giải quyết mọi thứ.

## 12. Ma trận kiểm thử trước khi phát hành

Đừng chỉ viết một happy path với List<String>. Hãy dùng những call sites đại diện:

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Producer subtype | `List<Alert>` có thể dùng ở method chỉ đọc Tagged. |
| Supertype consumer | `Collection<Object>` có thể nhận Tagged. |
| Same-type mutation | `List<Alert>` không cho ghi Note khi API giữ T=Alert. |
| Callback supertype | `Predicate<Tagged>` dùng được trên nguồn Alert. |
| Callback result type | Mapper `Tagged::tag` cho kết quả `List<String>`. |
| Target typing | Cả `List<Alert>` và `List<Tagged>` ở assignment contexts thích hợp. |
| Return-only type contract | Đầu ra giữ được kiểu cần thiết, không phải Object gây cast muộn. |
| Overload ambiguity | Lambda trần không bị giao hai functional target không phân biệt nổi. |
| Immutable source | Không thử sửa trực tiếp danh sách `List.of`. |
| Mutable destination | `appendAll` xử lý đúng ngữ nghĩa thêm vào cuối; alias/partial failure có chính sách. |
| Binary compatibility | Giữ client `.class` cũ khi test đổi descriptors. |
| Invalid generic calls | Source code sai bị compiler từ chối; không suppress để test qua. |

### Negative compilation: ba ví dụ phải bị từ chối

Để từng đoạn vào **file thử nghiệm riêng**, không ghép vào chương trình runnable.

**A — Invariance:**

~~~java
List<Alert> alerts = new ArrayList<>();
// List<Tagged> notAllowed = alerts; // Compile error.
~~~

**B — Sai chiều dữ liệu:**

~~~java
List<? extends Tagged> source = new ArrayList<Alert>();
// source.add(new Note("bad")); // Compile error.
~~~

**C — Ghi nhầm loại vào một list chính xác:**

~~~java
List<Alert> alerts = new ArrayList<>();
// rewrite(alerts, alert -> new Note(alert.tag()));
// Compile error: UnaryOperator<Alert> phải trả Alert.
~~~

Bởi các dòng sai đã được comment, file chứa chúng có thể được làm **runnable test harness** nếu đặt trong class phù hợp. Để thực sự làm *negative compilation test*, bỏ comment đúng dòng đang kiểm tra và xác nhận `javac` trả exit code khác 0. Không nhầm một comment có diễn giải lỗi với bằng chứng compiler đã thực sự bị test.

## 13. Trình tự sửa một chữ ký API đang khó dùng

Một quy trình review tiết kiệm công sức:

1. **Viết hai call sites hợp lệ điển hình và một call site phải bị từ chối**. Nếu không diễn đạt được, có thể contract chưa rõ.
2. **Chọn mức abstraction**: Iterable để duyệt, Collection để thêm, List để dùng index/mutation, domain interface khi thuật toán phụ thuộc hành vi nghiệp vụ.
3. **Vẽ luồng dữ liệu**: producer → mapper → consumer, hoặc read/modify/write cùng T.
4. **Đặt type variables chỉ ở những quan hệ cần giữ**, tránh `<T>` thừa trong hàm chỉ `size()`.
5. **Áp dụng wildcard ở ranh giới dữ liệu một chiều**, không dùng wildcard để che quan hệ hai chiều hoặc thay đổi kiểu phần tử bằng cast.
6. **Cho output một type hữu ích**, thường `List<R>`/`Optional<T>` thay vì `Object`/wildcard result không cần thiết.
7. **Kiểm tra Java inference** với lambda/method reference, target type rõ và `var`.
8. **Rà overloads**: xung đột erasure, ambiguous lambda, null hoặc compiler chọn overload khác ý định.
9. **Viết contract runtime**: null, empty, mutability, aliasing, ordering, error behavior.
10. **Nếu API đã public, kiểm tra source/binary compatibility** bằng javac, javap và client đã compile với phiên bản cũ.
11. **Ghi Javadoc ngắn về quan hệ type parameters và ràng buộc ngoài hệ kiểu**, không chép lại chữ ký mà thiếu hành vi.
12. **Chỉ tối ưu complexity khi có ích thực tế**; một generic framework mới không tốt hơn một method domain ngắn nếu chỉ có một use case.

## 14. Câu hỏi đánh giá cuối chương

**1.** Method chỉ đếm số phần tử của bất kỳ Collection. Có cần `<T>` không?

**Đáp án:** Không cần nếu không có ràng buộc với các vị trí khác; `Collection<?>` rõ hơn.

**2.** Tại sao `List<Alert>` không gán trực tiếp vào `List<Tagged>`?

**Đáp án:** Generic type arguments invariant. List<Tagged> có thể nhận Note, trong khi List<Alert> không thể.

**3.** Vì sao method `select` trả `List<T>` nhưng nhận `Iterable<? extends T>`?

**Đáp án:** Input chỉ cấp các giá trị có thể dùng như T; output được tạo mới với element type T liên quan tới caller/target type.

**4.** Tại sao callback trong `select` là `Predicate<? super T>`?

**Đáp án:** Predicate tiêu thụ T; một predicate nhận supertypes của T vẫn xử lý được mọi T.

**5.** Tại sao `rewrite` dùng `List<T>` và `UnaryOperator<T>`, không `List<? extends T>`?

**Đáp án:** Nó phải đọc rồi ghi lại cùng element type trên cùng list; wildcard producer không cho ghi tùy ý một T mới.

**6.** Tại sao `load(() -> "ready")` có thể ambiguous nếu overload Supplier<String> và Callable<String>?

**Đáp án:** Lambda trần tương thích với hai functional target ngang hàng, javac không có đủ khác biệt để chọn.

**7.** Khi nào một generic helper `mapAll` thực sự đáng tạo?

**Đáp án:** Khi có nhiều phép biến đổi cùng cấu trúc và việc giữ quan hệ T→R giúp caller tránh duplicate code/casts; không phải vì cú pháp phức tạp hơn trông tốt hơn.

**8.** `List<Tagged> chosen = select(alerts, beginsA)` có làm alerts thành List<Tagged> không?

**Đáp án:** Không. select xây kết quả mới theo hợp đồng T, nguồn vẫn là List<Alert> và không bị ép thành một parameterized type khác.

**9.** Thay tham số public từ List sang Collection có thể phá client đã compile không?

**Đáp án:** Có. Erased method descriptor đổi từ List sang Collection, nên binary client cũ có thể không tìm được method descriptor nó đã liên kết.

**10.** Generic signature có đủ hứa `appendAll` atomic/thread-safe không?

**Đáp án:** Không. Type safety là một tầng contract; atomicity, mutability, concurrent modification và partial failures cần quy định/kiểm chứng riêng.

**Kết luận:** Chữ ký generic tốt nhất không phải chữ ký dài nhất hay ngắn nhất. Nó là **chữ ký đơn giản nhất vẫn đủ quan hệ kiểu**, nhận đúng các call sites an toàn, để compiler suy luận tự nhiên và giải thích rõ hành vi mà hệ kiểu không mô tả. Khi API được phát hành rộng rãi, **tính tương thích** là chiều đánh giá bắt buộc bên cạnh độ linh hoạt, tính dễ hiểu và suy luận kiểu.
