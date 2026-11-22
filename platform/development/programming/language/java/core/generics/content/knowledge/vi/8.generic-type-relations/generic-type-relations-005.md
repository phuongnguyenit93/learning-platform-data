# Kiểm thử lỗi kiểu mà invariance của Java Generics ngăn chặn

Một trong những lợi ích quan trọng của **invariance** là ngăn code viết sai kiểu ngay từ giai đoạn biên dịch. `List<Integer>` không tự trở thành `List<Number>` dù Integer là subtype của Number, vì `List<Number>` có quyền nhận Double. Nếu Java cho phép alias đó, dữ liệu bên dưới một `List<Integer>` có thể bị ghi sai loại phần tử.

Bài này không chỉ lặp lại lời giải thích invariance. Trọng tâm là **thiết kế phép thử có khả năng phân biệt**:

1. Sai kiểu nào compiler phải **chặn trước khi chạy**?
2. Đường wildcard/copy nào **giữ đúng type contract**?
3. Nếu cố tình vượt compiler bằng **raw alias**, lỗi có xảy ra lúc ghi hay chỉ lúc **đọc dưới kiểu Integer**?
4. Vì sao array lại phát **ArrayStoreException tại thao tác ghi**, khác nhiều generic collection cases?
5. Có thể chuyển lỗi mơ hồ ở cuối pipeline thành **lỗi xác thực ở ranh giới dữ liệu** hay không?

Đây là một bài kiểm thử/regression chứ không phải hướng dẫn dùng raw type trong code production. Toàn bộ thao tác không an toàn dưới đây chỉ dùng trong thử nghiệm có chủ đích.

## 1. Điều compiler ngăn chặn ngay lập tức

Với `Integer <: Number`, phép gán một Integer cho Number hợp lệ. Nhưng hai parameterized types cụ thể của List lại **bất biến**:

~~~java
List<Integer> ids = new ArrayList<>(List.of(1, 2));

// LỖI BIÊN DỊCH nếu bỏ comment:
List<Number> numbers = ids;
~~~

Nếu code trên được chấp nhận, có thể tiếp tục:

~~~java
// Giả định trái luật Java, không phải chương trình runnable:
// numbers.add(3.5);
// Integer later = ids.get(2);
// Double được ghi qua List<Number> nhưng lại bị đọc như Integer.
~~~

**Giá trị của hệ thống kiểu** là loại bỏ hẳn đường ghi chéo nguy hiểm đó. Không phải lỗi được “bắt sau này”: javac từ chối ngay phép gán đầu tiên.

Các lớp triển khai **vẫn có quan hệ subtype nếu giữ đúng đối số kiểu**:

~~~java
ArrayList<Integer> backing = new ArrayList<>();
List<Integer> list = backing;
Collection<Integer> collection = list;
~~~

Đây là kế thừa giữa những **generic declarations** (`ArrayList<E> implements List<E>`, `List<E> extends Collection<E>`), không phải một phép biến đổi Integer thành Number trong vị trí type argument. Để kiểm tra bước đó riêng, hãy nhớ quy tắc invariance vẫn áp dụng cho List<Integer> và Collection<Number>.

## 2. Tạo hai nhóm test tách biệt: compile-time và runtime

Một test chỉ bọc mọi thứ bằng `try/catch(ClassCastException)` là quá rộng. Nó không chứng minh compiler đã ngăn đường gán sai, cũng không chứng minh exception xuất hiện **ở thao tác nào**.

Chia kiểm thử làm hai bộ:

| Bộ test | Đầu vào | Kết quả phải chứng minh |
| --- | --- | --- |
| **Negative compilation** | Source cố gán List<Integer> cho List<Number> | `javac` thất bại với incompatible types. |
| **Type-safe alternative** | Nhìn List<Integer> qua wildcard đọc, copy vào List<Number> mới | Biên dịch/chạy thành công, list gốc không bị ô nhiễm. |
| **Raw alias misuse** | Raw List nhận Double trong list gốc vốn typed Integer | Có unchecked warning; write có thể qua. |
| **Typed read** | Đọc Double bị ghi qua raw alias như Integer | ClassCastException tại điểm dùng phần tử dưới kiểu Integer. |
| **Reified array** | Number[] alias tới Integer[] rồi ghi Double | ArrayStoreException **ngay tại write**. |
| **Boundary validation** | List<?> chứa Integer lẫn Double | Validator từ chối sai phần tử trước khi công bố List<Integer>. |

Tách hai giai đoạn build/run là rất quan trọng: **code bị compiler chặn không thể chạy**. Cần đưa mã cố ý sai biên dịch vào **tệp thử nghiệm riêng**, không lẫn vào một chương trình dự kiến chạy thành công.

## 3. Negative compilation: kiểm tra đúng lỗi bị ngăn chặn

Tệp **CompileShouldFail.java** được thiết kế để **không** biên dịch:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CompileShouldFail {
    public static void main(String[] args) {
        List<Integer> ids = new ArrayList<>(List.of(1, 2));

        // Trình biên dịch phải từ chối dòng dưới:
        List<Number> allNumbers = ids;

        allNumbers.add(3.5);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CompileShouldFail.java
~~~

Kết quả mong đợi: **exit code khác 0**, chẩn đoán đại ý `List<Integer> cannot be converted to List<Number>` hoặc `incompatible types`. Nội dung đầy đủ, vị trí dòng và định dạng thông báo phụ thuộc phiên bản javac; **không hard-code nguyên văn toàn bộ stderr** làm hợp đồng.

Ý nghĩa bài kiểm tra: phép gán sai bị từ chối trước khi `add(3.5)` có cơ hội chạy. Đây là mục tiêu cần duy trì khi refactor public APIs: đừng thay một phương thức nhận `List<Integer>` bằng raw List hay đưa unchecked cast vào chỉ để làm source “compile được”.

### Cách biến negative test thành regression test

Một dự án có test infrastructure có thể compile đoạn nguồn nhỏ bằng `javax.tools.JavaCompiler` trong test process và assert compile status là failure; hoặc dùng bài test compile-fail của build tool. Điểm cần assert là **compile fail đúng ca phân tích**, không phải một lỗi syntax hoàn toàn khác.

Đối với ví dụ Java thuần trong bài này, chạy javac bằng terminal và quan sát exit code là đủ.

## 4. Positive test: truyền qua wildcard và tạo list mới

Khi cần **chỉ đọc Number** từ một List<Integer>, dùng một tham chiếu `List<? extends Number>`:

~~~java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<? extends Number> readable = original;

Number first = readable.get(0); // OK.
// readable.add(3.5);           // Compile error.
~~~

Khi cần **một list thực sự chứa được Double**, tạo `List<Number>` khác:

~~~java
List<Number> independent = new ArrayList<>(original);
independent.add(3.5); // Chỉ sửa list mới.

System.out.println(original);    // [1, 2]
System.out.println(independent); // [1, 2, 3.5]
~~~

Điều này là proof of safety cho một **cách thiết kế khác**, không phải “cast thành List<Number>”. Hai collection có cấu trúc riêng; việc copy danh sách không làm thay đổi type argument của source.

Một biến `List<? super Integer>` có thể dùng làm **đích ghi Integer** khi cần đưa giá trị vào List<Number> hoặc List<Object>. Nhưng khi đọc qua biến này, kiểu bảo đảm chỉ là Object; không tự suy diễn rằng mọi phần tử được đọc là Integer.

**Lưu ý runtime:** một `List.of(...)` vẫn không hỗ trợ `add` dù chữ ký cho phép thao tác theo kiểu. Vì thế positive test dùng `new ArrayList<>(...)` khi thực sự có write.

## 5. Raw alias: lỗi không bắt buộc xuất hiện ngay lúc ghi

Trong một file test riêng:

~~~java
List<Integer> vulnerable = new ArrayList<>(List.of(1));

List raw = vulnerable;
raw.add(3.5); // Unchecked call, có thể ghi Double thành công.

Object observed = vulnerable.get(1); // Đọc theo Object: có thể thành công.

// Integer bad = vulnerable.get(1);
// Nếu thực thi dòng này, ClassCastException khi runtime cần Integer.
~~~

`raw` và `vulnerable` là **cùng một collection object**, không phải bản sao. Raw List làm mất kiểm tra E của `add`, vì vậy ArrayList nhận một Double trong vị trí mà code typed đang xem là Integer.

Ở bytecode, generic `List.get` có erased return type Object; khi caller cần Integer, javac có thể tạo `checkcast java/lang/Integer`. ClassCastException thường xuất hiện tại **typed read / typed usage**, không nhất thiết ngay lúc `raw.add`.

Khi test bug này, hai assertion phải **tách rời**:
1. Kiểm tra raw write thật sự đã làm thay đổi dữ liệu mà chưa ném exception.
2. Chỉ bọc typed read trong đoạn kỳ vọng ClassCastException.

Nếu bọc cả chuỗi khởi tạo–write–read trong một khối catch duy nhất, test có thể pass vì exception từ một operation khác với operation mong muốn.

### Cảnh báo javac

Dùng:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked InvarianceRegressionDemo.java
~~~

Khi code chứa `List raw = vulnerable; raw.add(3.5);`, compiler có thể phát:
- `[rawtypes]` do sử dụng raw List.
- `[unchecked]` tại thao tác add(E) qua raw receiver.

Warnings **không tự là exceptions** và không đồng nghĩa compiler từ chối build, trừ khi project cấu hình quality gate như `-Werror`.

Không dùng `@SuppressWarnings("unchecked")` như một phương thức “sửa lỗi”: suppression chỉ giấu warning, không xác minh tham số kiểu của collection.

## 6. So sánh đối chứng: array bắt lỗi khi ghi

Java arrays có runtime component type (**reified**), nên một Number[] alias có thể trỏ tới mảng thực Integer[], và Java kiểm tra phần tử được ghi có tương thích Integer không:

~~~java
Number[] view = new Integer[1];

try {
    view[0] = 3.5;
} catch (ArrayStoreException ex) {
    System.out.println("arrayWrite=ArrayStoreException");
}
~~~

Lệnh `view[0] = 3.5` biên dịch được vì kiểu tĩnh Number[] chấp nhận Number, nhưng đối tượng mảng thực Integer[] không nhận Double. JVM ném **ArrayStoreException tại write**.

| Trường hợp | Điều gì bị giới hạn/kiểm tra? | Điểm phát hiện lỗi |
| --- | --- | --- |
| `List<Integer> → List<Number>` | Generic invariant assignment | Compile time, không chạy. |
| Raw `add(Double)` vào ArrayList<Integer> | Chỉ có erased Object type ở add; mất generic E check | Có thể không lỗi ở write; dữ liệu bị ô nhiễm. |
| Typed `Integer x = vulnerable.get(1)` | JVM checkcast Integer ở typed usage | ClassCastException nếu phần tử là Double. |
| `Number[] view = new Integer[1]`, ghi Double | Runtime array component Integer | ArrayStoreException ở write. |

Không nên nói “generic type safety hoàn toàn là runtime” hoặc “mảng không an toàn”. Cả hai cơ chế đều có bảo vệ, nhưng **ở những thời điểm và bằng chứng kiểu khác nhau**.

## 7. Validator ở ranh giới dữ liệu: fail sớm có ngữ nghĩa rõ

Trong một API nhận dữ liệu không chắc chắn, không nên trả `List<Integer>` chỉ bằng một unchecked cast từ Object hoặc raw List.

Thay vào đó, nhận `List<?>` và kiểm tra **từng phần tử**:

~~~java
static List<Integer> requireIntegers(List<?> source) {
    List<Integer> checked = new ArrayList<>();

    for (Object item : source) {
        if (!(item instanceof Integer value)) {
            throw new IllegalArgumentException("expected Integer");
        }
        checked.add(value);
    }

    return checked;
}
~~~

Java 17 hỗ trợ pattern matching `instanceof Integer value`. Nếu gặp Double, String hoặc null, hàm ném IllegalArgumentException theo chính sách của ví dụ; dữ liệu sai bị từ chối **ngay tại boundary** chứ không lan sâu tới chỗ code đọc Integer.

Hàm trả một **bản sao** của cấu trúc collection, nên raw alias tới source không thể trực tiếp thêm phần tử vào list kết quả. Tuy nhiên, nếu element là object mutable, đây vẫn là shallow copy; ví dụ hiện dùng Integer bất biến.

Có thể chọn một loại exception/domain validation result khác tùy contract thật. Điều quan trọng là validation thực sự duyệt elements, không giả vờ rằng cast `(List<Integer>) someList` đã kiểm tra tất cả generic arguments.

## 8. Chương trình Java 17 hoàn chỉnh, kiểm thử theo đúng thời điểm

Lưu thành **InvarianceRegressionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class InvarianceRegressionDemo {
    static List<Integer> requireIntegers(List<?> source) {
        List<Integer> checked = new ArrayList<>();
        for (Object item : source) {
            if (!(item instanceof Integer value)) {
                throw new IllegalArgumentException("expected Integer");
            }
            checked.add(value);
        }
        return checked;
    }

    public static void main(String[] args) {
        // Positive path: tạo List<Number> khác thay vì alias.
        List<Integer> original =
                new ArrayList<>(List.of(1, 2));
        List<Number> independent = new ArrayList<>(original);
        independent.add(3.5);

        System.out.println(
                "safe=" + original + " / " + independent
        );

        // Test-only misuse: raw alias vượt generic type checking.
        List<Integer> vulnerable =
                new ArrayList<>(List.of(1));
        List raw = vulnerable;
        raw.add(3.5);

        System.out.println("rawWrite=" + vulnerable.size());

        Object observed = vulnerable.get(1);
        System.out.println("rawAsObject=" + observed);

        try {
            Integer bad = vulnerable.get(1);
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("typedRead=ClassCastException");
        }

        // Array covariance: lỗi ngay tại thao tác ghi.
        Number[] array = new Integer[1];
        try {
            array[0] = 3.5;
        } catch (ArrayStoreException ex) {
            System.out.println("arrayWrite=ArrayStoreException");
        }

        // Validate đầu vào trước khi phát hành List<Integer>.
        try {
            requireIntegers(vulnerable);
        } catch (IllegalArgumentException ex) {
            System.out.println("boundary=IllegalArgumentException");
        }

        System.out.println(
                "validated=" + requireIntegers(List.of(3, 4))
        );
    }
}
~~~

Biên dịch, quan sát warning và chạy:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked InvarianceRegressionDemo.java
java InvarianceRegressionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
safe=[1, 2] / [1, 2, 3.5]
rawWrite=2
rawAsObject=3.5
typedRead=ClassCastException
arrayWrite=ArrayStoreException
boundary=IllegalArgumentException
validated=[3, 4]
~~~

Giải thích thứ tự:
1. **safe:** bản sao Number chứa thêm Double, source Integer giữ nguyên.
2. **rawWrite=2:** thêm Double qua raw alias thành công và tăng size; chưa có CCE.
3. **rawAsObject=3.5:** cùng phần tử được đọc như Object nên không cần cast Integer.
4. **typedRead=ClassCastException:** runtime mới phải đối xử Double như Integer.
5. **arrayWrite=ArrayStoreException:** JVM chặn ghi Double vào Integer[] thật.
6. **boundary=IllegalArgumentException:** validator phát hiện Double theo schema Integer và từ chối.
7. **validated=[3, 4]:** dữ liệu đúng được duyệt và tạo typed copy an toàn.

Đừng gộp negative compilation `CompileShouldFail.java` vào chương trình này. Nó có mục đích riêng: **biên dịch phải thất bại**, trong khi file này **phải compile thành công với một số warnings cố ý** và có output ổn định.

## 9. Những trường hợp test dễ tạo kết luận sai

### “Không có ClassCastException ở raw add, nên dữ liệu an toàn”

Sai. Raw add có thể đi qua erased Object parameter. Lỗi chỉ xuất hiện khi một operation yêu cầu typed result và runtime cast thất bại.

### “List<?> là danh sách immutable”

Sai. `List<?>` là kiểu với type argument chưa biết. Nó ngăn thêm phần tử non-null tùy ý bằng generic API nhưng không ngăn `clear` hay `remove`, và object thực tế vẫn có thể mutable.

### “Một test chỉ có ClassCastException chứng minh invariance đã hoạt động”

Chưa đủ. Invariance bảo vệ ở compile time, nên phải test **compiler reject** cho phép gán sai. ClassCastException xuất hiện sau khi code đã vượt kiểm tra generic hoặc có cast sai ở runtime.

### “Mọi exception cần xử lý bằng catch”

Không. Với một generic API mới, ưu tiên không tạo đường raw alias gây pollution. Chỉ catch exception ở boundary nghiệp vụ thích hợp, đồng thời giữ compiler contracts chính xác.

### “Java generics chặn mọi runtime type errors”

Sai. Generics phát hiện nhiều sai sót tĩnh, nhưng reflection, raw types, unchecked casts/conversions và dữ liệu bên ngoài vẫn cần xử lý có trách nhiệm. Compiler-inserted casts và runtime checks không biến một dữ liệu sai thành đúng.

### “Dùng checkedCast hoặc wrapper là khỏi cần validation”

`Class<Integer>` chỉ giúp kiểm tra từng object là Integer; không xác nhận toàn bộ `List<Integer>` bằng một cast vào List. `Collections.checkedList` có thể kiểm tra những lần insert thông qua wrapper khi có class token phù hợp, nhưng nó không ngăn mutation bypass wrapper qua alias tới backing collection.

## 10. Checklist regression test trước khi chấp nhận refactor

1. **Negative compilation:** xác nhận `List<Number> = List<Integer>` vẫn bị compiler từ chối.
2. **Positive wildcard:** nhận List<Integer> qua `? extends Number` và chỉ đọc.
3. **Positive copy:** xây `List<Number>` mới, thêm Double không sửa source.
4. **Raw warnings:** test path cố ý raw có `rawtypes/unchecked` diagnostics.
5. **Write vs read:** raw insertion đã thành công trước typed read failure.
6. **Object read:** đọc thành Object không tự chứng minh kiểu phần tử.
7. **Correct exception:** typed read phát ClassCastException ở đúng điểm.
8. **Array contrast:** array-store check phát ArrayStoreException tại write.
9. **Boundary validation:** từ chối dữ liệu sai từ List<?> và chấp nhận dữ liệu đúng.
10. **No unchecked workaround:** production API không dùng raw cast để lách invariant type arguments.
11. **Mutability:** positive write dùng collection thật sự sửa được.
12. **Type vs policy:** một List<Integer> đúng kiểu vẫn có thể vi phạm ràng buộc nghiệp vụ như giá trị âm, null policy hoặc giới hạn kích thước.

## 11. Câu hỏi tự kiểm tra

**1.** Invariance của List<T> chặn lỗi ở compile time hay runtime?

**Đáp án:** Chủ yếu ở compile time qua phép gán/call có type arguments không tương thích.

**2.** Có thể gán Integer cho Number không? Có suy ra gán List<Integer> cho List<Number> được không?

**Đáp án:** Có với từng Integer object; không với cả hai parameterized List types cụ thể.

**3.** Nếu raw add(Double) vào một List<Integer> thành công thì khi nào CCE có thể xuất hiện?

**Đáp án:** Khi code typed cần dùng Double như Integer, ví dụ `Integer i = list.get(index)`, chứ không nhất thiết tại raw add.

**4.** Nếu phải nhận List<Integer> để chỉ đọc Number thì có nên tạo List<Number> bản sao?

**Đáp án:** Thường không cần; chọn `List<? extends Number>` ở tham số nhận khi có thể sửa API.

**5.** Nếu phải thêm cả Integer và Double vào collection độc lập thì dùng gì?

**Đáp án:** `List<Number>` thực sự, có thể tạo bằng `new ArrayList<>(sourceIntegers)`.

**6.** Tại sao Number[] view tới Integer[] phát ArrayStoreException ở lệnh ghi Double?

**Đáp án:** JVM biết runtime component type Integer của array, nên chặn giá trị Double tại write.

**7.** Vì sao cast List<?> thành List<Integer> không đủ để xác thực dữ liệu?

**Đáp án:** Erasure không cho kiểm tra generic arguments của tất cả elements; phải validate từng element hoặc có nguồn invariant đáng tin.

**8.** Test chỉ assert một exception chung ở cuối workflow thiếu điều gì?

**Đáp án:** Không xác định nơi và giai đoạn lỗi thực sự xảy ra; có thể pass vì exception từ thao tác không liên quan.

**9.** Khi output của test in `rawAsObject=3.5`, điều đó chứng minh gì?

**Đáp án:** Value thật là Double và khi đọc dưới Object không yêu cầu cast thành Integer. Nó không xác nhận collection an toàn theo hợp đồng Integer.

**10.** Một List<Integer> có bảo đảm không chứa null hoặc chỉ có giá trị dương không?

**Đáp án:** Không. Generic type relationship khác với null/giá trị nghiệp vụ; cần validation và dữ liệu contract riêng.

**Ghi nhớ:** **compiler ngăn alias sai trước khi chạy**; nếu cố ý vượt generic checking, lỗi có thể lộ muộn ở typed read. Thiết kế tốt kết hợp negative compilation tests, positive wildcard/copy tests, diagnostics cho raw paths và validation tại ranh giới để ngăn dữ liệu sai lan vào core application.
