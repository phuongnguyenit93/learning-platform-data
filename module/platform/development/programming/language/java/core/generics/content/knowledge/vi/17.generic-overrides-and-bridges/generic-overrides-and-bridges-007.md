# Vì sao không thể overload chỉ bằng `List<String>` và `List<Integer>`? Chọn thiết kế API thay thế

Giả sử một dịch vụ phải xử lý hai loại danh sách:

- `List<String>` chứa tên nhân viên; cần nối các tên thành báo cáo.
- `List<Integer>` chứa điểm số; cần cộng các điểm thành tổng.

Ý tưởng ban đầu là viết hai phương thức cùng tên:

~~~java
import java.util.List;

class InvalidProcessor {
    void process(List<String> names) {
        System.out.println(String.join(", ", names));
    }

    void process(List<Integer> scores) {
        System.out.println(scores.stream().mapToInt(Integer::intValue).sum());
    }
}
~~~

**Class này cố ý không biên dịch.** Trong Java Generics, `List<String>` và `List<Integer>` khác nhau về quy tắc kiểm tra kiểu ở source, nhưng chúng đều bị **type erasure** thành `java.util.List` ở bytecode. Cả hai phương thức muốn có chữ ký nguồn phân biệt được bằng cùng một danh sách tham số đã xóa:

~~~text
process(List<String>)    -> process(List)
process(List<Integer>)   -> process(List)
~~~

Khi hai khai báo cùng nằm trong một class và không tạo quan hệ override hợp lệ, compiler báo **name clash**. Bài này tập trung vào bước tiếp theo của lập trình viên: **chọn API đúng với mục đích nghiệp vụ thay vì tìm cách vượt qua compiler**.

## 1. Điều compiler thực sự cần để overload

Overload được phân giải ở compile time bằng tên method và các kiểu tham số theo quy tắc Java, không phải bằng cách JVM nhìn các phần tử trong List rồi chọn nhánh ở runtime.

Nếu hai phương thức đều có kiểu trả về `void`, descriptor giả định của chúng sẽ cùng là:

~~~text
(Ljava/util/List;)V
~~~

`(Ljava/util/List;)` mô tả một tham số `java.util.List`, còn `V` là `void`. Các type arguments `String` và `Integer` không tạo hai erased parameter types riêng. Trong class file, generic `Signature` metadata có thể ghi type arguments của những **phương thức hợp lệ**; nó không cho phép Java tuyên bố hai overload đụng nhau chỉ bằng cách thêm Generic Signature khác nhau.

Cần phân biệt ba khái niệm:

| Khái niệm | Ví dụ | Ảnh hưởng tới vấn đề |
| --- | --- | --- |
| Generic type argument | `List<String>` khác `List<Integer>` | Compiler dùng để kiểm tra phần tử; hai kiểu đều erasure thành List. |
| Overload parameter type | `process(String)` và `process(Integer)` | Hai erased parameter types khác nhau, overload hợp lệ. |
| Override | `Parent<T>.save(T)` được `Child extends Parent<String>` ghi đè bằng `save(String)` | Compiler có thể tạo bridge để giữ dispatch, **không phải** hai overload khác type arguments. |

**Không sửa** bằng cách thay `void` thành kiểu trả về khác, đổi tên biến `names`/`scores`, thêm type parameter `<T>` vào một method, hoặc viết `@SuppressWarnings("unchecked")`. Những thao tác đó không tạo một danh sách tham số phân biệt được sau erasure.

### Kiểm chứng lỗi compile riêng

Lưu code `InvalidProcessor` ở trên thành **InvalidProcessor.java**, chạy:

~~~bash
javac --release 17 InvalidProcessor.java
~~~

Kết quả mong đợi: **javac thất bại**, với chẩn đoán chứa khái niệm name clash hoặc same erasure. Đừng cố ghép file này vào chương trình runnable của phần 6: nó cố ý dùng làm **negative compilation test**, không phải ví dụ runtime.

## 2. Chọn một trong bốn chiến lược theo nhu cầu

| Nhu cầu thật | Thiết kế ưu tiên | Vì sao |
| --- | --- | --- |
| Hai hành vi **khác nhau hoàn toàn** | Hai tên method có nghĩa, như `joinNames` và `sumScores` | Tên đã mô tả hợp đồng và tránh overload gây bất ngờ. |
| **Một thuật toán** dùng được cho nhiều phần tử | Một method `<T>` hoặc method nhận `List<?>` | Không nhân đôi logic chỉ để phân biệt kiểu phần tử. |
| Một pipeline giống nhau, **hành vi mỗi phần tử khác nhau** | Generic method nhận `Function`/`Consumer` | Compiler type-check callback tại từng lời gọi. |
| Phải giữ **cùng tên process**, nhưng đầu vào là hai khái niệm miền khác nhau | Hai wrapper types riêng, ví dụ records `Names` và `Scores` | JVM có hai erased parameter classes khác nhau. |
| Muốn **xác minh** kiểu phần tử khi nhận dữ liệu không tin cậy | Một method kèm `Class<?>`/validator | Runtime token kiểm tra dữ liệu, không biến two List overloads thành hợp lệ. |

Đây là các lựa chọn về **hợp đồng API**, không chỉ cú pháp để vượt lỗi javac. Đổi từ chữ ký công khai `process(List...)` đã phát hành sang `process(Names)` có thể là **breaking change** với callers/binaries cũ; muốn tiến hóa thư viện phải có kế hoạch chuyển đổi, overload adapter được phép bởi Java, versioning và kiểm tra tương thích.

## 3. Phương án A: đặt tên theo nghiệp vụ

Khi các thuật toán bản chất khác nhau, code dễ hiểu nhất thường có **hai tên khác nhau**:

~~~java
static String joinNames(List<String> names) {
    return String.join(", ", names);
}

static int sumScores(List<Integer> scores) {
    return scores.stream().mapToInt(Integer::intValue).sum();
}
~~~

Ý nghĩa của `joinNames` và `sumScores` hiển thị ngay trong API. Không cần ép kiểu và không tạo tên method chung mơ hồ với yêu cầu xử lý khác nhau.

Khi sử dụng:

~~~java
String report = joinNames(List.of("Lan", "Mai"));
int total = sumScores(List.of(5, 7));
~~~

`report` là `"Lan, Mai"`, `total` là `12`. Hai method có tên khác nhau nên không có nguy cơ erased-signature collision.

**Điểm đánh đổi:** Nếu nhiều phiên bản thực sự làm **cùng một thao tác duyệt** và chỉ khác callback, tách nhiều method có thể làm trùng code. Khi đó dùng generic method chung thường tốt hơn.

## 4. Phương án B: một generic method với hành vi được truyền vào

Một method **không cần biết cụ thể T** có thể xử lý List<T> theo cùng một thuật toán:

~~~java
static <T, R> List<R> mapAll(
        List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> transform) {

    List<R> output = new ArrayList<>();

    for (T item : source) {
        output.add(transform.apply(item));
    }

    return output;
}
~~~

Nó **không** tạo hai overload `mapAll(List<String>)` và `mapAll(List<Integer>)`; đây là **một** generic method được compiler suy luận type arguments cho mỗi lời gọi.

~~~java
List<Integer> lengths = mapAll(
        List.of("a", "abcd"), String::length
);

List<Integer> squares = mapAll(
        List.of(2, 3), n -> n * n
);
~~~

Kết quả:

~~~text
lengths=[1, 4]
squares=[4, 9]
~~~

Ở lời gọi đầu, compiler biết phần tử của nguồn là String và callback trả Integer. Ở lời gọi thứ hai, phần tử là Integer và lambda tạo Integer. Callback có các tham số wildcard `? super T`, `? extends R` để dùng đúng vai trò nhận T/trả R theo nhu cầu.

### Vì sao không đặt generic method ở mọi nơi?

Nếu body chỉ `System.out.println(value)` và không liên hệ kiểu đầu vào với kết quả/đối số khác, một tham số `List<?>` có thể đủ. Nếu nghiệp vụ thật sự cần gọi API chỉ có ở String hoặc Integer, một `<T>` không giới hạn **không tự cho phép gọi String.length() hoặc Number.intValue() trên mọi T**. Khi đó chọn callback, bound phù hợp hoặc tách phương thức theo nghiệp vụ.

**Kết luận:** một generic method chỉ tốt khi nó mô tả đúng **cấu trúc thuật toán chung**, không phải thủ thuật đánh lừa name clash.

## 5. Phương án C: wrapper types giúp overload hợp lệ và rõ miền dữ liệu

Đôi khi một entry point tên `process` được thiết kế để nhận **hai loại yêu cầu có ý nghĩa miền nghiệp vụ khác nhau**. Ta có thể dùng records riêng:

~~~java
record Names(List<String> items) {}
record Scores(List<Integer> items) {}

static String process(Names request) {
    return String.join("|", request.items());
}

static String process(Scores request) {
    int total = 0;
    for (int value : request.items()) {
        total += value;
    }
    return "scores=" + total;
}
~~~

Hai phương thức có parameter types `Names` và `Scores`. Đây là **hai runtime classes riêng**, vì vậy erased descriptors cũng khác nhau. Overload hợp lệ mà không cần dựa vào runtime generic arguments.

Tại điểm gọi:

~~~java
process(new Names(List.of("Lan", "Mai")));
process(new Scores(List.of(5, 7)));
~~~

Compiler xác định overload nhờ class thực sự của đối số. Các record không có mối quan hệ subtype với nhau, nên lời gọi trần `process(null)` **có thể mơ hồ**: cả hai overload nhận null mà không có một overload cụ thể hơn. Đây là vấn đề API khi overload bằng hai reference types ngang hàng, **không** phải lỗi erasure.

### Record không tự deep-immutable

`record Names(List<String> items)` có field tham chiếu cuối cùng (*final component*), nhưng một List mutable vẫn có thể bị sửa qua alias. Nếu yêu cầu API nhận một snapshot độc lập và không sửa được, có thể dùng **compact constructor**:

~~~java
record Names(List<String> items) {
    Names {
        items = List.copyOf(items);
    }
}
~~~

`List.copyOf` tạo list không cho sửa và từ chối null elements; đây là *shallow copy* đối với các element references. Chữ ký record bảo vệ cấu trúc collection nhưng không tự làm mọi element object bất biến.

**Khi nào chọn wrappers:** input type chứa các quy tắc riêng, metadata hay validation thực sự có giá trị. Đừng tạo thêm hai class chỉ để đổi tên một tiện ích nhỏ mà có thể gọi `joinNames`/`sumScores` một cách rõ ràng hơn.

## 6. Chương trình Java 17 hoàn chỉnh: so sánh wrapper, callback và runtime validation

Lưu thành **ListOverloadApiDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class ListOverloadApiDemo {
    record Names(List<String> items) {
        Names {
            items = List.copyOf(items);
        }
    }

    record Scores(List<Integer> items) {
        Scores {
            items = List.copyOf(items);
        }
    }

    static String process(Names batch) {
        return "names=" + String.join("|", batch.items());
    }

    static String process(Scores batch) {
        int total = 0;
        for (int score : batch.items()) {
            total += score;
        }
        return "scores=" + total;
    }

    static <T, R> List<R> mapAll(
            List<? extends T> source,
            Function<? super T, ? extends R> transform) {

        List<R> output = new ArrayList<>();
        for (T value : source) {
            output.add(transform.apply(value));
        }
        return output;
    }

    static boolean allElements(
            List<?> values, Class<?> elementType) {

        for (Object value : values) {
            if (!elementType.isInstance(value)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        System.out.println(
                process(new Names(List.of("Lan", "Mai")))
        );

        System.out.println(
                process(new Scores(List.of(5, 7)))
        );

        System.out.println(
                "lengths=" + mapAll(
                        List.of("a", "abcd"),
                        String::length
                )
        );

        System.out.println(
                "squares=" + mapAll(
                        List.of(2, 3),
                        number -> number * number
                )
        );

        System.out.println(
                "strings=" + allElements(
                        List.of("a", "b"), String.class
                )
        );

        System.out.println(
                "mixed=" + allElements(
                        List.of(1, "b"), String.class
                )
        );

        System.out.println(
                "sameRuntimeClass=" +
                (new ArrayList<String>().getClass()
                        == new ArrayList<Integer>().getClass())
        );
    }
}
~~~

Biên dịch/chạy bằng Java 17:

~~~bash
javac --release 17 -Xlint:all ListOverloadApiDemo.java
java ListOverloadApiDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
names=Lan|Mai
scores=12
lengths=[1, 4]
squares=[4, 9]
strings=true
mixed=false
sameRuntimeClass=true
~~~

Đọc kết quả theo hợp đồng:

1. **`names` và `scores`:** cùng tên `process` nhưng hai tham số **thực sự là Names/Scores**, khác runtime class và erasure. Record compact constructors phòng ngừa list bị thay đổi qua chính reference đầu vào sau khi xây bản snapshot.
2. **`lengths` và `squares`:** **một method `mapAll`** dùng hai lần; callback quyết định phép biến đổi cụ thể trong từng lần gọi.
3. **`strings` và `mixed`:** `Class<?>.isInstance` kiểm tra **từng phần tử thực** của List<?>. Nó không phải cách tạo hai overload bằng List<String> và List<Integer>.
4. **`sameRuntimeClass`:** đối tượng ArrayList của hai parameterizations sử dụng cùng runtime class. Không được suy từ class equality thành quan hệ subtype giữa List<String> và List<Integer>.

### Giới hạn của validation bằng Class

`allElements` trả `false` khi gặp bất kỳ object nào không phải instance của class token (kể cả null). Đây là **chính sách kiểm tra minh họa**; nghiệp vụ khác có thể cho phép null, hoặc yêu cầu thu thập tất cả lỗi thay vì boolean.

`Class<String>` cho phép kiểm tra từng object là String, nhưng `Class<List<String>>` không có class literal tương đương `List<String>.class` để chứng minh toàn bộ danh sách lồng nhau đã đúng type arguments. Việc kiểm tra cấu trúc generic lồng nhau đòi validator qua từng tầng hoặc schema phù hợp.

## 7. Phương án D: truyền type token hoặc strategy có ý nghĩa

Nếu API của bạn cần **một method duy nhất** và muốn người gọi công bố loại phần tử dự kiến, có thể chọn:

~~~java
static <T> boolean validate(
        List<T> values, Class<T> elementType) {

    for (T value : values) {
        if (!elementType.isInstance(value)) {
            return false;
        }
    }
    return true;
}
~~~

Chữ ký này có một generic method; compiler cố gắng liên hệ type argument của List và Class theo cùng T tại call site. Một lời gọi có source typed đúng cũng phải hiểu rằng **raw/unchecked aliases có thể phá contract**, vì vậy kiểm tra runtime elements vẫn hữu ích khi dữ liệu không tin cậy.

Cần tránh hiểu nhầm:

~~~java
// VẪN KHÔNG HỢP LỆ: hai phương thức cùng erased tham số (List, Class).
// void process(List<String> items, Class<String> token) {}
// void process(List<Integer> items, Class<Integer> token) {}
~~~

Đổi `Class<String>` thành `Class<Integer>` chỉ đổi type argument của một generic class nữa; erasure vẫn là `Class`. Token hữu ích **làm dữ liệu/validation cho một method**, không phải như một trục overload mới nếu raw parameter types không đổi.

Một lựa chọn khác là **strategy interface**: caller truyền đối tượng xử lý mà API gọi tới qua một contract. Strategy phù hợp hơn khi hành vi có trạng thái, cấu hình, nhiều bước hoặc cần tái sử dụng, trong khi một Function/Consumer gọn hơn cho biến đổi đơn giản.

## 8. Overload được phép nhưng dễ gây hiểu nhầm

Hai method dưới đây có erased parameter types khác nhau và có thể cùng tồn tại:

~~~java
static void process(java.util.Collection<String> names) {}
static void process(java.util.List<Integer> scores) {}
~~~

Erasure lần lượt là Collection và List; chúng không va chạm như hai tham số cùng List. Tuy nhiên, đây là một thiết kế **dễ đánh lừa người đọc**:

- Method selection dựa vào kiểu tĩnh của đối số và overload resolution; nó không tự nhìn kiểu phần tử ở runtime để quyết định nhánh.
- Danh sách String có thể được nhìn qua Collection<String> hoặc một kiểu trung gian; các loại collection và wildcard khiến call sites khó suy luận.
- Một số lời gọi có inference hoặc null có thể gặp lựa chọn overload bất ngờ/không áp dụng được.

Vì thế nếu ý định nghiệp vụ thực sự là **tách tên và điểm số**, hai tên rõ ràng hoặc hai wrapper classes thường bền vững hơn cách tạo khác biệt raw container type một cách gượng ép.

Thêm một tham số giả `boolean isString` để làm khác arity chỉ vì compiler cấm hai List overload cũng khiến callers khó hiểu. Chỉ thêm discriminator nếu nó biểu thị **một thuộc tính nghiệp vụ cần thiết** và được validate/diễn đạt rõ.

## 9. Không nhầm name clash với bridge của override

Một method trong superclass generic:

~~~java
class Box<T> {
    T echo(T value) {
        return value;
    }
}

class StringBox extends Box<String> {
    @Override
    String echo(String value) {
        return value.toUpperCase();
    }
}
~~~

`StringBox.echo(String)` **ghi đè hợp lệ** phương thức chuyên biệt hóa từ Box<String>. Compiler có thể sinh bridge `echo(Object)` để giữ dynamic dispatch sau erasure.

Đây là tình huống **khác** với hai khai báo cạnh nhau:

~~~java
// CỐ Ý KHÔNG HỢP LỆ:
// void echo(List<String> names) {}
// void echo(List<Integer> numbers) {}
~~~

Bridge method chỉ giúp duy trì một **override đã hợp lệ** từ source Java khi descriptors cần được nối. Nó không cứu một cặp overload không hợp lệ vì cùng erasure. Đừng thêm bridge thủ công hoặc dựa vào runtime generic argument để dispatch.

## 10. API evolution: chọn lời gọi dễ dùng, không chỉ chữ ký biên dịch được

Trước khi chốt phương án, cần hỏi:

1. **Hai hành vi có thật sự khác nhau?** Nếu có, tên `joinNames` và `sumScores` thể hiện ý nghĩa tốt hơn `process` chung chung.
2. **Có chung một pipeline không?** Nếu có, một generic method với callback tránh duplicate logic.
3. **Input có hai miền dữ liệu rõ ràng không?** Nếu có, records/classes wrapper khác nhau có thể cho overload hợp lệ và chứa validation phù hợp.
4. **Dữ liệu đến từ raw/JSON/Reflection không?** Nếu có, cần xác thực runtime thực sự; đừng xem unchecked cast hoặc List<?> như một validator.
5. **Code đã phát hành hay mới thiết kế?** Với API cũ, thay method descriptors có thể làm binary clients cũ gặp `NoSuchMethodError`. Chọn migration path phù hợp thay vì phá ngay hợp đồng.
6. **Sẽ thêm kiểu phần tử thứ ba sau này không?** Nếu sẽ mở rộng nhiều kiểu, callback/strategy hoặc domain interfaces có thể thuận tiện hơn việc nhân đôi overloads và wrappers.

Khi buộc phải duy trì binary compatibility, một adapter có **tên và descriptor cũ** có thể giữ các callers đã biên dịch; điều này đòi kiểm tra thực tế với class files cũ và mới. Không tự cho rằng thêm một overload mới lúc nào cũng không thay đổi source overload resolution hoặc hành vi callers sau recompile.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `process(List<String>)` và `process(List<Integer>)` cùng class không hợp lệ?

**Đáp án:** Erasure của hai tham số đều là List, dẫn đến name clash. Type arguments chỉ giúp compiler kiểm tra nguồn, không tạo runtime classes riêng cho mỗi List<E>.

**Câu 2.** Hai records `Names` và `Scores` khác nhau có thể làm tham số hai overload `process` không?

**Đáp án:** Có. Hai erased parameter types thực sự khác nhau; null không có target cụ thể có thể gây overload ambiguity.

**Câu 3.** Nếu muốn một thuật toán xử lý nhiều loại danh sách với callback khác nhau, nên dùng gì?

**Đáp án:** Một generic method nhận `Function<? super T,? extends R>` hay `Consumer<? super T>` theo dòng dữ liệu, không tạo hai List<E> overloads.

**Câu 4.** Thêm `Class<String>` và `Class<Integer>` làm tham số thứ hai có tự giải quyết erased collision không?

**Đáp án:** Không. `Class<String>` và `Class<Integer>` cùng erasure là Class, nên cả hai method vẫn có erased parameter list (List, Class).

**Câu 5.** Hai ArrayList có cùng runtime class chứng minh generic type arguments bằng nhau không?

**Đáp án:** Không. Erasure làm runtime classes thông thường không chứa type arguments theo cách đó. Không dùng `getClass()` để suy List<String> từ data.

**Câu 6.** `process(Collection<String>)` và `process(List<Integer>)` có hợp lệ về kiểu tham số không?

**Đáp án:** Có thể có, vì erased parameter types là Collection và List. Nhưng về thiết kế API dễ gây nhầm; phải xét overload resolution và type tĩnh thực sự.

**Câu 7.** Bridge methods có giúp khai báo hai overload chỉ khác List<String>/List<Integer> không?

**Đáp án:** Không. Bridge phục vụ dynamic dispatch của override hợp lệ; còn name clash khiến source không biên dịch được từ đầu.

**Câu 8.** Nếu library trước đây phát hành một public method nhận List và nay đổi sang wrapper Names, clients .class cũ tự chạy được không?

**Đáp án:** Không thể mặc định. Method descriptor đã đổi, nên cần adapter/compatibility plan hoặc rebuild clients; kiểm thử binary clients cũ với library mới.

**Ghi nhớ:** **đừng cố phân biệt hai overload bằng generic arguments vốn bị erasure**. Hãy quyết định xem API cần hai **tên nghiệp vụ**, **một generic pipeline**, hay **hai domain types thật**; chỉ dùng runtime token khi nó phục vụ validation hoặc logic đã được thiết kế rõ, không dùng như thủ thuật tạo overload. 
