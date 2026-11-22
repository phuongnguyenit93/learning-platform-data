# Rà soát generic, varargs và cảnh báo an toàn kiểu trong Java

## 1. Mục tiêu của bài thực hành

Khi rà soát một chương trình Java, mục tiêu không chỉ là “biên dịch được” mà là đảm bảo **dữ liệu thực sự tuân thủ hợp đồng kiểu**. Một `List<String>` không được chứa Integer vì một cast thiếu kiểm tra; một phương thức nhận `List<T>...` không được âm thầm làm hỏng kiểu của mảng varargs; một cảnh báo `unchecked` không nên bị ẩn trước khi người viết hiểu nguyên nhân.

Bài kết hợp ba nội dung hiện vẫn áp dụng với **Java 17+ và các JDK hiện đại**:

1. **Generics** cho phép kiểm tra kiểu ở thời điểm biên dịch, nhưng Java dùng **type erasure** nên runtime thường không biết đầy đủ tham số kiểu `T`.
2. **Varargs** cho phép nhận số lượng đối số thay đổi, nhưng thực chất sử dụng **mảng**. Mảng với phần tử non-reifiable là nơi có thể phát sinh **heap pollution**.
3. **Cảnh báo an toàn kiểu** từ `javac`, đặc biệt `unchecked`, `varargs` và `rawtypes`, cần được điều tra, sửa từ nguồn và kiểm chứng.

Ví dụ sử dụng các API hiện hành: `List.of`, `List.copyOf`, `Class.cast`, `@SafeVarargs`, `@SuppressWarnings` và `-Xlint`. Không cần thư viện bên ngoài, không sử dụng API nội bộ hay kỹ thuật lỗi thời.

Sau bài học, bạn có thể đọc warning, chọn generic/wildcard chính xác, xác định điểm mất bằng chứng kiểu, chứng minh một method varargs có an toàn để annotate, cô lập unchecked cast và chạy được ví dụ Java không có cảnh báo kiểu liên quan.

## 2. Generics và type erasure: hiểu điều compiler biết

Với generic, compiler bảo vệ việc thêm/đọc đúng loại phần tử:

```java
// Mảnh mã minh họa, import java.util.List và java.util.ArrayList.
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
// names.add(42); // Không biên dịch: Integer không phù hợp String.
```

Đây là kiểm tra **tĩnh**. Khi chạy, `ArrayList<String>` và `ArrayList<Integer>` cùng là đối tượng của lớp `ArrayList`; thông tin tham số `String`/`Integer` phần lớn bị xóa (*type erasure*).

Từ đó:

- `value instanceof List<?>` hợp lệ: runtime nhận biết được đối tượng là một `List`.
- `value instanceof List<String>` không hợp lệ vì runtime không thể xác minh tham số `String` của từng phần tử bằng phép đó.
- `(List<String>) unknownObject` có thể bị cảnh báo **unchecked cast**. Runtime có thể chỉ kiểm tra lớp `List`, không kiểm tra từng phần tử; `ClassCastException` có thể xuất hiện **muộn hơn** ở lần đọc.
- Một `List<?>` cho phép đọc các phần tử ở dạng `Object`, trong khi compiler không cho thêm một phần tử tùy ý vì kiểu phần tử thật chưa biết.
- `List<?>` khác `List<Object>`: danh sách `List<String>` gán được cho `List<?>` nhưng không gán được cho `List<Object>`.

**Raw type** như `List values` làm mất ràng buộc kiểu mà generics cung cấp. Chúng vẫn có thể xuất hiện ở ranh giới tích hợp với code cũ hoặc API không khai báo kiểu, nhưng không nên để raw type lan qua nhiều tầng ứng dụng.

Ví dụ cố ý sai:

```java
List raw = new ArrayList();
raw.add(42);
List<String> words = raw; // Unchecked conversion.
String word = words.get(0); // ClassCastException lúc thực thi.
```

Đây là mảnh mã để nhận diện lỗi. Đừng chữa bằng `@SuppressWarnings("unchecked")` trên toàn lớp. Cần phát hiện ranh giới mất kiểu và xác minh dữ liệu trước khi biến nó thành `List<String>`.

## 3. Reifiable và non-reifiable: lý do mảng generic nguy hiểm

**Reifiable** là kiểu có thể được runtime biểu diễn/kiểm tra đủ theo quy tắc Java. `String`, `String[]`, raw `List` và `List<?>` là các ví dụ reifiable. `List<String>` và tham số generic `T` thông thường là **non-reifiable**.

Một mảng Java kiểm tra kiểu phần tử bằng thông tin runtime; một collection generic lại không mang đầy đủ tham số kiểu để kiểm tra như vậy. Vì thế:

```java
String[] names = new String[3];           // Hợp lệ.
// List<String>[] groups = new List<String>[3]; // Lỗi generic array creation.
List<?>[] unknownGroups = new List<?>[3]; // Hợp lệ về kiểu.
```

Đây là mảnh minh họa. `List<?>[]` chỉ xác định thành phần là một List với tham số chưa biết; nó **không** tự đảm bảo phần tử trong từng List là String.

Khi khai báo `List<String>... groups`, compiler xử lý tham số cuối như một array; khi cần truyền nhiều đối số, một mảng runtime kiểu `List[]` có thể được tạo. Mảng đó kiểm tra được đối tượng là `List`, nhưng **không kiểm tra được** tham số `String`. Điều này giải thích tại sao một varargs declaration/call có kiểu non-reifiable thường phát sinh warning.

## 4. Cảnh báo nào cần ưu tiên trong `javac`?

Bật cảnh báo compiler ngay khi review:

```bash
javac -encoding UTF-8 -Xlint:unchecked,varargs,rawtypes YourClass.java
```

Thay `YourClass.java` bằng tên tệp thực. Đây là các tùy chọn hiện hành của `javac`, không phải thư viện kiểm tra bên ngoài.

| Warning | Tình huống hay gặp | Điều cần tìm |
| --- | --- | --- |
| `unchecked` | Cast `Object` sang `List<String>`; gán raw `List` cho typed list; gọi generic thiếu bằng chứng | Compiler không thể chứng minh dữ liệu phù hợp với tham số kiểu |
| `varargs` | Body của method có non-reifiable varargs, đặc biệt xử lý array alias không an toàn | Khả năng heap pollution hoặc method varargs dùng sai hợp đồng |
| `rawtypes` | Khai báo `List`, `Map`, `Class` mà không có tham số | Mất kiểm tra kiểu, thường dẫn đến unchecked operation |
| `cast` | Cast không cần thiết | Khả năng đơn giản hóa, không đồng nghĩa là heap pollution |
| `deprecation` | Dùng API deprecated | Chủ đề tương thích API, cần kiểm tra riêng với kiến thức hiện hành |

`-Xlint:all` có thể bật tất cả warning compiler mà phiên bản `javac` hỗ trợ. `-Werror` có thể làm build thất bại khi còn warning; trước khi áp dụng vào CI, xử lý cảnh báo tồn tại và xác định chính sách ngoại lệ.

**Cách đọc warning có trách nhiệm:** xác định file/dòng và kiểu bị suy luận, lần ngược chỗ dữ liệu được tạo, chỗ bị cast/gán và chỗ được đọc; sửa hợp đồng kiểu rồi biên dịch lại. Warning có thể xuất hiện ở **caller** trong khi lỗi thật nằm trong implementation `varargs`.

## 5. Bounded wildcard: sửa lỗi generic invariance

Dù `Integer extends Number`, `List<Integer>` **không phải subtype** của `List<Number>`:

```java
List<Integer> ints = List.of(1, 2);
// List<Number> nums = ints; // Không biên dịch.
```

Nếu được gán như trên, người dùng `nums` có thể thêm một Double vào danh sách vốn được tạo để chứa Integer. Java generic dùng nguyên tắc **invariance** để ngăn điều đó.

Dùng **PECS — Producer Extends, Consumer Super** khi API có hướng dữ liệu rõ ràng:

- `List<? extends Number>` là **nguồn**: có thể đọc phần tử thành Number, nhưng không được thêm một Number bất kỳ vì phần tử thật có thể là subtype hẹp hơn.
- `List<? super Integer>` là **đích**: có thể thêm Integer, nhưng khi đọc chỉ chắc chắn kiểu Object.
- `List<?>` là danh sách phần tử chưa xác định, phù hợp để duyệt/kiểm tra trước khi chuyển đổi.
- `<T>` và `List<T>` phù hợp khi cần ràng buộc **cùng một kiểu T** qua nhiều tham số hoặc kiểu trả về.

Ví dụ:

```java
// Mảnh mã trong lớp có import java.util.List.
static void appendIntegers(
        List<? super Integer> target,
        List<? extends Integer> source) {
    for (Integer value : source) {
        target.add(value);
    }
}
```

Source có thể là `List<Integer>`, target là `List<Number>` hoặc `List<Object>`. Không cần raw type, cast hay suppression. Nếu method vừa đọc vừa ghi với ràng buộc cùng kiểu, generic `<T>` có thể rõ ràng hơn wildcard; PECS là hướng dẫn thiết kế, không phải phép thay thế mọi tham số bằng wildcard.

## 6. Varargs là array: khi nào có heap pollution?

Ví dụ `int...` an toàn về mặt kiểu phần tử vì `int[]` có kiểm tra runtime phù hợp:

```java
static int sum(int... numbers) {
    int total = 0;
    for (int n : numbers) total += n;
    return total;
}
// sum(1, 2, 3) hoặc sum(new int[]{1, 2, 3}).
```

Rủi ro nằm ở non-reifiable element type như `List<String>...`:

```java
// Mảnh mã có thể tạo warning vì phần tử List<String> non-reifiable.
static void printGroups(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
```

Không phải mỗi warning nghĩa là phương thức đã làm sai dữ liệu. Cần kiểm tra nó có **ghi vào mảng, làm lộ mảng hoặc dùng alias khiến code khác ghi sai kiểu** hay không.

Ví dụ dưới đây **cố ý nguy hiểm** để thấy chính xác cơ chế:

```java
import java.util.List;

class UnsafeVarargs {
    static void corrupt(List<String>... strings) {
        Object[] alias = strings;
        alias[0] = List.of(42);
        String first = strings[0].get(0);
        System.out.println(first);
    }

    public static void main(String[] args) {
        corrupt(List.of("hello"));
    }
}
```

Đây là ví dụ nhận diện anti-pattern, **không nên dùng trong ứng dụng**. Compiler có thể phát warning tại khai báo và lời gọi. Khi chạy, dòng đọc giá trị `strings[0].get(0)` gây `ClassCastException` vì:

1. Mảng runtime chứa các List có kiểu thành phần `List`, không kiểm tra được tham số `String`.
2. `Object[] alias = strings` tạo một tên tham chiếu khác tới cùng mảng (tính covariance của array reference).
3. `alias[0] = List.of(42)` vẫn hợp lệ với array store check runtime vì đối tượng là List.
4. Static type của `strings[0]` vẫn được compiler coi là `List<String>`, nhưng thực tế bên trong có Integer. Đây là **heap pollution**.

Lỗi phát hiện ở bước 4 nhưng **nguồn lỗi nằm ở bước 3**. Một warning ở call site có thể phản ánh rủi ro do implementation method, không nên buộc người gọi tự chịu trách nhiệm sửa.

Khi audit, rà soát `Object[]` alias, raw collection, unchecked casts, mảng generic lưu vào field/static, array varargs bị trả về, và những phương thức đưa data mutable qua ranh giới mà caller vẫn có thể sửa.

## 7. `@SafeVarargs`: lời cam kết, không phải cơ chế kiểm tra runtime

`@SafeVarargs` được dùng khi người viết **đã chứng minh** implementation của method/constructor không xử lý tham số non-reifiable varargs theo cách gây mất an toàn kiểu. Annotation chặn một số unchecked warning ở cả khai báo và nơi gọi, nhưng **không làm method tự động an toàn**.

Trong Java 17+ và các JDK hiện hành, `@SafeVarargs` chỉ hợp lệ trên constructor có varargs hoặc method varargs thuộc một trong các nhóm: `static`, `final`, hoặc `private`. Method instance có thể bị override theo cách thông thường không được annotate như vậy. Annotation trên method không phải varargs cũng là lỗi biên dịch.

Để đánh giá có thể đặt `@SafeVarargs`:

- Không gán phần tử sai kiểu vào array varargs (kể cả qua `Object[]` alias).
- Không trả array varargs ra ngoài hay giữ lại để code khác thay đổi.
- Không thực hiện unchecked cast thiếu bằng chứng đối với element hoặc nested collection.
- Khi sao chép ra collection mới, giữ đúng generic `T` hoặc wildcard mà compiler đã ràng buộc.
- Không nhầm **type safety** với **thread safety**; tham chiếu tới object mutable vẫn cần hợp đồng riêng.

Ví dụ hợp lý:

```java
// Mảnh mã: cần import List, ArrayList và Objects.
@SafeVarargs
static <T> List<T> snapshot(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(Objects.requireNonNull(group));
    }
    return List.copyOf(result);
}
```

Method chỉ **đọc** danh sách và array nhận vào, trả một **List mới**; không ghi/không để lộ mảng varargs. `List.copyOf` (Java 10+) tạo collection không cho thay đổi cấu trúc và từ chối phần tử null. Nó **không deep-copy** những object mutable nằm bên trong.

Không đặt `@SafeVarargs` vào `corrupt` ở ví dụ trên: nó sẽ che warning hữu ích nhưng hành vi nguy hiểm vẫn y nguyên. Compiler có thể cảnh báo thêm khi thân method annotated có thao tác không an toàn; phải sửa implementation. Với `String...`, kiểu phần tử reifiable nên annotation thường không cần thiết và có thể tạo warning dư thừa.

**Phân biệt:** `@SafeVarargs` là assertion về hành vi của method varargs và ảnh hưởng cả call site. `@SuppressWarnings("unchecked")` chỉ yêu cầu compiler bỏ một loại warning trong phạm vi annotate. Hai annotation không có ý nghĩa thay thế cho nhau.

## 8. Khi nào cần `@SuppressWarnings("unchecked")`?

Ưu tiên **loại bỏ nguyên nhân warning**. Nếu một API reflection thực sự không thể biểu đạt quan hệ runtime với generic compile-time, có thể dùng suppression ở **phạm vi nhỏ nhất**, kèm lý do, hợp đồng kiểm tra và test.

Ví dụ minh họa có type token:

```java
// Mảnh mã trong một class Java.
static <T> T[] newArray(Class<T> componentType, int length) {
    @SuppressWarnings("unchecked")
    T[] result = (T[]) java.lang.reflect.Array.newInstance(
            componentType, length);
    return result;
}
```

Phép cast sang `T[]` không thể được compiler chứng minh hoàn toàn do type erasure. Nhưng `Array.newInstance(componentType, length)` tạo mảng có đúng kiểu phần tử runtime mà type token đáng tin cậy chỉ định. Nếu caller tự vi phạm hợp đồng bằng raw/unchecked `Class`, điều kiện đảm bảo không còn.

Trước khi quyết định suppression, xem có thể:

1. Trả về `List<T>` thay cho `T[]` khi không cần mảng.
2. Dùng array generator có type cụ thể, ví dụ `names.toArray(String[]::new)`.
3. Đổi cast cả `List` thành **validate từng phần tử** bằng `Class<T>.cast`.
4. Generic hóa API ở ranh giới thay vì đẩy raw type ra khắp dự án.
5. Viết test cho dữ liệu sai kiểu để chứng minh **thực sự có kiểm tra**.

Nếu vẫn giữ suppression, đặt sát một phép cast, không trên cả class hoặc package. Không dùng `@SuppressWarnings({"unchecked", "varargs"})` diện rộng chỉ để có một build “xanh”.

## 9. Kiểm tra `List<?>` ở ranh giới bằng `Class.cast`

Giả sử parser trả `List<?>` nhưng nghiệp vụ cần `List<String>`. Một cast trực tiếp `(List<String>) value` thường chỉ chứng minh đối tượng bên ngoài là List. Cách an toàn hơn:

```java
// Mảnh mã: cần import java.util.List và ArrayList.
static <T> List<T> checkedCopy(List<?> source, Class<T> type) {
    List<T> result = new ArrayList<>();
    for (Object element : source) {
        result.add(type.cast(element));
    }
    return result;
}
```

`Class.cast` kiểm tra **từng phần tử** ở runtime. Nếu kỳ vọng String mà có Integer, lỗi được phát hiện ngay ở ranh giới adapter, thay vì để dữ liệu ô nhiễm đi sâu trong hệ thống.

Một số giới hạn cần hiểu:

- `Class.cast(null)` trả null; nếu hợp đồng không cho null, dùng `Objects.requireNonNull` khi validate.
- `String.class` kiểm tra String, còn `List.class` **không** thể chứng minh mọi phần tử trong nested `List<String>`. Cần kiểm tra từng cấp theo schema.
- `Collections.checkedList(list, String.class)` là wrapper kiểm tra những lần thêm phần tử thông qua view. Nó **không tự quét** dữ liệu sai đã có trong backing list và không ngăn một alias khác sửa backing list trực tiếp.
- `List.copyOf` giúp có collection mới không chỉnh sửa được, nhưng không kiểm tra generic nested và không deep-copy object mutable.

Đối với dữ liệu biên không đáng tin, **validate + copy** thường tạo hợp đồng rõ ràng hơn một unchecked cast.

## 10. Chương trình chạy được: GenericVarargsAudit.java

Ví dụ tổng hợp ba kỹ thuật: wildcard đúng chiều, `@SafeVarargs` có cơ sở và kiểm tra kiểu từng phần tử mà **không có unchecked cast**.

Lưu chính xác thành **`GenericVarargsAudit.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class GenericVarargsAudit {
    private GenericVarargsAudit() {
    }

    static void appendIntegers(
            List<? super Integer> target,
            List<? extends Integer> source) {
        for (Integer n : source) {
            target.add(n);
        }
    }

    @SafeVarargs
    static <T> List<T> snapshot(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(Objects.requireNonNull(group));
        }
        return List.copyOf(result);
    }

    static <T> List<T> checkedCopy(List<?> source, Class<T> type) {
        List<T> result = new ArrayList<>();
        for (Object element : source) {
            result.add(type.cast(element));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        appendIntegers(numbers, List.of(1, 2, 3));
        System.out.println("numbers=" + numbers);

        List<String> letters =
                snapshot(List.of("A"), List.of("B", "C"));
        System.out.println("snapshot=" + letters);

        List<String> checked =
                checkedCopy(List.of("x", "y"), String.class);
        System.out.println("checked=" + checked);

        try {
            checkedCopy(List.of("x", 42), String.class);
        } catch (ClassCastException ex) {
            System.out.println("rejected="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trên **Java 17+**:

```bash
javac -encoding UTF-8 -Xlint:unchecked,varargs,rawtypes GenericVarargsAudit.java
java GenericVarargsAudit
```

**Stdout chính xác:**

```text
numbers=[1, 2, 3]
snapshot=[A, B, C]
checked=[x, y]
rejected=ClassCastException
```

Chương trình đã được kiểm tra thực thi bằng **JDK 24 trong JShell** với cùng các method và logic chính; output trên khớp giá trị dự kiến. Các API dùng trong mã đều có ở Java 17. Không có thread hoặc I/O bất định; thứ tự phần tử List là thứ tự được thêm.

### Giải thích kết quả

- `appendIntegers` đọc từ `List<? extends Integer>` và thêm Integer vào `List<? super Integer>`. `List<Number>` đích có thể chứa các Integer mà không mất an toàn kiểu.
- `snapshot` nhận các nhóm String, compiler suy luận `T`, chỉ đọc array varargs và tạo danh sách mới. Annotation `@SafeVarargs` phù hợp với implementation. `List.copyOf` tạo snapshot không chỉnh sửa được.
- `checkedCopy` nhận nguồn `List<?>` và kiểm tra từng phần tử bằng `String.class.cast`. Khi gặp Integer, `ClassCastException` xảy ra đúng tại nơi kiểm tra và được bắt để in một thông báo dự kiến.

Nếu thay `List.of("x", 42)` bằng `List.of("x", "y")`, kiểm tra không ném ngoại lệ. Nếu muốn chấp nhận giá trị null, phải thiết kế hợp đồng riêng; `List.of` và `List.copyOf` không chấp nhận null.

## 11. Quy trình rà soát một dự án thực tế

Một lượt review có thể triển khai theo trình tự sau:

**Bước 1 — Bật và thu thập warning.** Dùng `javac -Xlint:unchecked,varargs,rawtypes` hoặc đưa option tương ứng vào compiler task Gradle/Maven. Ghi file, dòng, warning key, kiểu suy luận và caller liên quan. Nếu dùng `-Xlint:all`, phân loại warning không liên quan mà vẫn giữ nguyên đầu ra gốc để review.

**Bước 2 — Tìm điểm mất type information.** Theo dõi raw `List`/`Map`, cast `Object` thành generic collection, khai báo varargs non-reifiable, array alias `Object[]`, mảng `T[]`, field giữ array và các lệnh suppression. Tìm nơi dữ liệu bị **ghi sai** trước khi chỉ sửa dòng ném `ClassCastException`.

**Bước 3 — Sửa thiết kế API.** Chọn `List<T>`, `List<?>`, `? extends T`, `? super T` đúng mục đích. Khi nhận dữ liệu từ ngoài, tạo adapter validate từng phần tử rồi trả typed collection. Nếu API cần nhiều nhóm dữ liệu mà varargs gây phức tạp, có thể đổi sang `Collection<? extends T>` hoặc overload có tên rõ ràng.

**Bước 4 — Xác minh từng `@SafeVarargs`.** Một method static/final/private/constructor hợp lệ về vị trí annotation **chưa đủ**: phải kiểm tra thân method không gây heap pollution, không giữ/để lộ array, không ghi sai kiểu qua alias. Chỉ annotate sau khi có lý do kỹ thuật.

**Bước 5 — Thu hẹp suppression thật sự cần.** Nếu còn cast reflection không thể xóa, dùng `@SuppressWarnings("unchecked")` trên đúng biến cục bộ hoặc method nhỏ, mô tả invariant. Test cả dữ liệu sai kiểu, null, empty, subtype và nhiều phần tử.

**Bước 6 — Biên dịch lại và chạy test.** Đối chiếu warning trước–sau, đảm bảo warning được loại bỏ vì nguyên nhân đã xử lý. Nếu đổi chữ ký method public, kiểm tra call sites, type inference, overload resolution, source/binary compatibility và tests.

Đừng coi **số lượng warning bằng 0** là chứng minh mọi object đã đúng kiểu nếu trong code vẫn có raw type, unchecked cast bị suppression hoặc dữ liệu đến từ nguồn không được validate.

## 12. Tình huống rà soát điển hình

### A. Parser trả danh sách chưa biết kiểu

API chỉ trả `Object` hoặc `List<?>`; service muốn String. Kiểm tra outer object bằng `instanceof List<?>`, sau đó kiểm tra từng phần tử qua `String.class.cast`, tạo `List<String>` mới. Không ép cả collection thành `List<String>` chỉ vì dữ liệu ví dụ đầu tiên có vẻ đúng.

### B. Method nhận nhiều `List<Report>...`

Đọc implementation xem có bao giờ lưu/return array, gán vào `Object[]` hoặc đưa vào vùng có thể ghi từ bên ngoài. Nếu chỉ duyệt và copy dữ liệu đúng kiểu, cân nhắc `@SafeVarargs` khi method đủ điều kiện. Nếu cần lưu các nhóm để xử lý sau, tạo snapshot typed rõ ràng thay vì cho array varargs escape.

### C. Gộp `List<Integer>` và `List<Double>`

Không gán trực tiếp vào `List<Number>`. Với luồng dữ liệu hướng đọc, dùng `List<? extends Number>`; với đích nhận Number, dùng `List<? super Number>`. Khi có nhiều nguồn, có thể định nghĩa một method `appendNumbers(List<? super Number> sink, List<? extends Number> source)` và gọi với từng nguồn.

### D. Dự án có hàng chục `@SuppressWarnings("unchecked")`

Lập danh sách từng điểm dùng, nguồn dữ liệu, bất biến dựa vào type token/schema, tác động khi sai. Thay raw cast bằng adapter typed hoặc chuyển từ mảng generic sang collection khi hợp lý. Nếu vẫn có chỗ cần suppression, đặt ở phạm vi nhỏ và bảo vệ bằng test.

### E. Cảnh báo ở call site nhưng method có annotation

Không khắc phục bằng cách annotate caller. Kiểm tra method khai báo tham số varargs non-reifiable, thân method có an toàn không, có public API nào cần đổi sang collection không. Một annotation sai có thể giấu cảnh báo ở nhiều nơi, khiến lỗi heap pollution xuất hiện ở code rất xa.

## 13. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách tốt hơn |
| --- | --- | --- |
| Dùng `List` raw ở mọi tầng | Mất kiểm tra kiểu và phát sinh unchecked conversion | Dùng `List<T>` hoặc `List<?>` ở đúng ranh giới |
| Ép `(List<String>) value` và tin mọi phần tử là String | Type erasure không xác minh phần tử | Validate từng phần tử, tạo typed copy |
| Coi `List<Integer>` là `List<Number>` | Generic invariant | Dùng bounded wildcard phù hợp |
| Tạo `new List<String>[n]` | Generic array creation bị cấm | Dùng collection hoặc array reifiable |
| Cho varargs array escape ra ngoài | Caller có thể làm heap pollution qua alias | Chỉ đọc/copy, không giữ/return mảng |
| Đặt `@SafeVarargs` khi method có unsafe write | Annotation chỉ che warning, không thay runtime behavior | Sửa code, chứng minh type safety |
| Suppress `unchecked` ở toàn class | Che mất cảnh báo mới trong tương lai | Suppress cực hẹp, ghi invariant và test |
| Dùng `Class<List>` để “xác thực” `List<String>` | Chỉ kiểm tra outer List | Validate nested element types |
| Hiểu `Collections.checkedList` đã sửa mọi phần tử cũ | View không tự kiểm tra toàn bộ backing list | Validate/copy dữ liệu đầu vào |
| Sửa chỗ ném `ClassCastException` bằng cast khác | Nguồn heap pollution vẫn tồn tại | Lần ngược điểm ghi sai kiểu |
| Không chạy `-Xlint` sau refactor | Warning mới có thể phát sinh ở caller | Biên dịch lại với flags thống nhất |

## 14. Tự kiểm tra kiến thức

1. **Vì sao `List<Integer>` không gán được cho `List<Number>`?** Vì nếu cho phép, caller có thể thêm Double vào danh sách Integer.
2. **`List<?>` và `List<Object>` khác nhau ở đâu?** `List<?>` diễn đạt kiểu phần tử chưa biết, nhận được nhiều `List<T>`; `List<Object>` chỉ nhận đúng tham số Object.
3. **Tại sao `List<String>...` có thể cảnh báo?** Vì varargs sử dụng mảng, nhưng `List<String>` không thể xác minh đầy đủ tham số String ở runtime.
4. **Lệnh `Object[] alias = lists; alias[0] = List.of(42)` có nguy cơ gì?** Nó có thể đặt List<Integer> vào mảng mà source tin là List<String>[], tạo heap pollution.
5. **`@SafeVarargs` có tự kiểm tra tính an toàn không?** Không; nó là lời cam kết của người viết method, không thêm runtime checks.
6. **Khi nào `@SuppressWarnings("unchecked")` hợp lý?** Khi có bằng chứng chắc chắn về kiểu runtime mà Java compiler không biểu đạt được, suppression nhỏ và có test.
7. **`Class.cast` kiểm tra được toàn bộ `List<String>` không?** Không; `String.class.cast` chỉ kiểm tra một phần tử String, còn nested collection cần kiểm tra từng cấp.
8. **Phản ứng đầu tiên khi thấy unchecked warning?** Mở vị trí, lần theo nguồn mất kiểm tra kiểu và sửa hợp đồng API; không vội che warning.

## 15. Tài liệu chính thức đang áp dụng

- [Java SE 25 — `javac`, `-Xlint:unchecked`, `varargs`, `rawtypes` và `-Werror`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Java SE 25 — `@SafeVarargs`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SafeVarargs.html).
- [Java Language Specification `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7).
- [Java Language Specification `9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.7).
- [Java SE 25 — `Class.cast`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)).
- [Java SE 25 — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

**Tiêu chí hoàn thành một lần audit:** API thể hiện quan hệ kiểu bằng generic/wildcard đúng, varargs không làm lộ hoặc làm hỏng array, dữ liệu ở ranh giới chưa rõ kiểu được validate thực tế, và các warning bị loại bỏ **vì nguồn rủi ro đã được xử lý**.
