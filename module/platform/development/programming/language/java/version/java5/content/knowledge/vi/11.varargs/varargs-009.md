# Varargs generic, kiểu không reifiable và cảnh báo an toàn kiểu

## 1. Vấn đề: cú pháp gọn vẫn phải đi qua một mảng

Varargs giúp gọi phương thức bằng một dãy đối số, nhưng tham số mà thân phương thức nhận vẫn là mảng. Khi kết hợp với generic, hai cơ chế gặp nhau:

- Mảng giữ thông tin về kiểu thành phần tại lúc chạy và kiểm tra kiểu khi ghi phần tử.
- Generic kiểm tra nhiều ràng buộc tại lúc biên dịch; thông tin đối số kiểu thường bị xóa khỏi biểu diễn kiểu tại lúc chạy.

Vì vậy, `String...` và `List<String>...` không có cùng mức thông tin kiểm tra kiểu trong mảng. Mảng biết nó chứa `String` hay chứa `List`; một đối tượng mảng không phân biệt được “mỗi phần tử phải là `List<String>`” với “mỗi phần tử là `List<Long>`”.

Bài này đi theo chuỗi: **kiểu còn nhận diện được khi chạy → mảng varargs được tạo thế nào → nguy cơ làm sai giả định về kiểu → đọc cảnh báo → chứng minh một phương thức an toàn**. Mã sử dụng Java 17+; các quy tắc được trình bày vẫn áp dụng hiện nay.

## 2. Kiểu reifiable và không reifiable

**Kiểu reifiable** là kiểu có đủ thông tin để được biểu diễn tại lúc chạy theo quy tắc của ngôn ngữ. Có thể hiểu thực dụng rằng JVM không cần khôi phục một đối số kiểu đã bị xóa để nhận diện kiểu đó.

**Kiểu không reifiable** thiếu một phần thông tin kiểu ấy tại lúc chạy. Ví dụ, JVM có thể nhận diện một đối tượng là `List`, nhưng không thể dùng một kiểm tra kiểu trực tiếp để xác minh toàn bộ đối tượng ấy là `List<String>`.

Một số trường hợp thường gặp:

| Kiểu | Reifiable? | Ý nghĩa trong bài |
|---|---|---|
| `String` | Có | Mảng `String[]` kiểm tra phần tử ghi vào theo kiểu `String` |
| `Object` | Có | `Object...` không tạo cảnh báo generic-varargs chỉ vì kiểu phần tử |
| `int` | Có | `int...` dùng mảng `int[]` |
| `List<?>` | Có | Không khẳng định đối số kiểu cụ thể của từng danh sách |
| `List<String>` | Không | Đối số kiểu `String` không tồn tại trong kiểu thành phần mảng lúc chạy |
| `List<? extends Number>` | Không | Wildcard có cận này không tương đương wildcard không giới hạn `?` |
| `T` trong phương thức generic | Không | Không có một kiểu thành phần cụ thể cho mọi lần gọi |
| `String[]` | Có | Kiểu mảng có thành phần reifiable |
| `List<?>[]` | Có | Thành phần `List<?>` reifiable |
| `List<String>[]` | Không | Thành phần `List<String>` không reifiable |

Phân loại chính thức nằm trong [JLS §4.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7). Không đồng nhất “có generic” với “luôn không reifiable”: `List<?>` là phản ví dụ cần nhớ.

### Liên hệ với việc tạo mảng

Đoạn minh họa sau có chủ đích chứa dòng không biên dịch:

```java
// Giả sử đã import java.util.List.
List<?>[] allowed = new List<?>[2]; // Hợp lệ.
// List<String>[] rejected = new List<String>[2]; // Lỗi generic array creation.
```

Có thể khai báo biến hoặc tham số có kiểu `List<String>[]`, nhưng không được trực tiếp tạo mảng bằng `new List<String>[2]`. Với `T` là biến kiểu của phương thức, `new T[2]` cũng không hợp lệ.

Chuyển sang `List<?>[]` không giúp lấy lại ràng buộc “mọi danh sách chỉ chứa chuỗi”: khi đọc phần tử của `List<?>`, mã chỉ biết kết quả là `Object`, trừ khi có thông tin bổ sung được kiểm tra hợp lệ.

## 3. Vì sao generic-varargs hợp lệ nhưng có cảnh báo?

Hai khai báo sau là các mảnh mã để đặt trong một lớp:

```java
static <T> void process(T... values) {
    // values có kiểu khai báo T[].
}

static void processGroups(java.util.List<String>... groups) {
    // groups có kiểu khai báo List<String>[].
}
```

Ngôn ngữ cho phép các khai báo này. Khi một lời gọi varargs cần tạo mảng với kiểu thành phần không reifiable, trình biên dịch không thể tạo đối tượng mảng có đủ thông tin đối số kiểu như kiểu khai báo đòi hỏi.

Ví dụ quan sát được trong các chương trình ở dưới:

- `processGroups(List.of("A"), List.of("B"))` cần mảng varargs có thành phần lúc chạy là `List`, không phải một kiểu riêng biệt `List<String>`.
- Một lời gọi trực tiếp `asArray("A", "B")` có thể tạo `String[]`, vì kiểu cụ thể được xác định ngay ở lời gọi.
- Trong thân một phương thức generic `forward(T value)`, lời gọi `asArray(value)` không biết `T` là `String`. Với `T` không có cận tường minh như ví dụ, mảng được tạo có thành phần `Object`.

Do đó, không được kết luận rằng mọi `T...` đều nhận một đối tượng `Object[]`. Kiểu thực tế phụ thuộc vào lời gọi, kiểu đã suy luận và việc mảng có được truyền trực tiếp hay không. Với biến kiểu có cận, kiểu xóa còn có thể là cận tương ứng, chẳng hạn `Number`.

Cảnh báo là tín hiệu rằng trình biên dịch không thể xác minh trọn vẹn ràng buộc kiểu qua cơ chế mảng này. Nó không có nghĩa mọi lời gọi chắc chắn hỏng, cũng không chứng minh rằng một thân phương thức cụ thể đã an toàn.

## 4. Nhiễm bẩn vùng nhớ heap là gì?

**Nhiễm bẩn vùng nhớ heap (heap pollution)** xảy ra khi một biến có kiểu tham số hóa tham chiếu tới đối tượng không đáp ứng kiểu tham số hóa mà mã đang giả định.

Trong generic-varargs, tình huống dễ quan sát là:

1. Phương thức nhận một mảng được nhìn như `List<String>[]`.
2. Cùng mảng ấy bị truy cập qua tham chiếu rộng hơn là `Object[]`.
3. Mã ghi một `List<Long>` vào một vị trí.
4. Kiểm tra ghi mảng chỉ thấy “đây là một `List`”, nên không chặn được sự khác biệt `String`/`Long`.
5. Khi đọc theo giả định `List<String>`, phép ép kiểu do trình biên dịch chèn vào có thể thất bại bằng `ClassCastException`.

Nơi gây sai kiểu và nơi phát hiện sai kiểu có thể nằm ở hai câu lệnh khác nhau. Vì thế, thấy ngoại lệ khi đọc một chuỗi chưa có nghĩa câu lệnh đọc là nguyên nhân ban đầu.

### So sánh với kiểm tra của mảng String[]

Nếu mảng thực tế là `String[]`, việc ghi một `Long` qua tham chiếu `Object[]` bị chặn ngay bằng `ArrayStoreException`. Với mảng thành phần `List`, cả `List<String>` và `List<Long>` đều vượt qua kiểm tra thành phần mảng. Kiểm tra mảng vẫn hoạt động, nhưng nó không có thông tin đối số generic để kiểm tra sâu hơn.

## 5. Thí nghiệm có chủ đích không an toàn

Chương trình sau dùng để quan sát cảnh báo và ngoại lệ. Không lấy các phương thức `readSecondGroup`, `asArray` và `forward` làm mẫu API an toàn.

Lưu tệp `GenericVarargsRiskDemo.java`:

```java
import java.util.List;

public class GenericVarargsRiskDemo {
    static String readSecondGroup(List<String>... groups) {
        System.out.println("component=" + groups.getClass().getComponentType().getName());
        Object[] exposed = groups;
        exposed[1] = List.of(99L);
        return groups[1].get(0);
    }

    static <T> T[] asArray(T... values) {
        return values;
    }

    static <T> T[] forward(T value) {
        return asArray(value);
    }

    public static void main(String[] args) {
        try {
            String text = readSecondGroup(List.of("A"), List.of("B"));
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("generic list read: ClassCastException");
        }
        try {
            Object[] actualStrings = new String[] {"A"};
            actualStrings[0] = 99L;
        } catch (ArrayStoreException ex) {
            System.out.println("String array write: ArrayStoreException");
        }
        String[] direct = asArray("A", "B");
        System.out.println("direct component="
                + direct.getClass().getComponentType().getName());
        try {
            String[] indirect = forward("A");
            System.out.println(indirect.length);
        } catch (ClassCastException ex) {
            System.out.println("forwarded array: ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked,varargs GenericVarargsRiskDemo.java
java GenericVarargsRiskDemo
```

Ở bước biên dịch, `javac` cảnh báo tại:

- Khai báo `List<String>... groups`: nguy cơ heap pollution từ kiểu phần tử tham số hóa.
- Khai báo `T... values`: nguy cơ tương tự với biến kiểu.
- Lời gọi `asArray(value)` trong `forward`: tạo mảng generic cho varargs mà không thể kiểm tra đầy đủ.
- Lời gọi `readSecondGroup(...)`: tạo mảng varargs cho kiểu `List<String>[]`.

Cách trình bày và số dòng của chẩn đoán có thể khác giữa phiên bản trình biên dịch. Với mã trên, `javac` JDK 21 phát ra bốn cảnh báo `[unchecked]`. Chương trình vẫn biên dịch được vì lệnh này không dùng `-Werror`.

Stdout khi chạy:

```text
component=java.util.List
generic list read: ClassCastException
String array write: ArrayStoreException
direct component=java.lang.String
forwarded array: ClassCastException
```

### Thí nghiệm 1: List[] không kiểm tra đối số kiểu

`component=java.util.List` cho thấy mảng nhận được trong `readSecondGroup` có thành phần thực tế là `List`. Lệnh ghi `List.of(99L)` qua `exposed[1]` hợp lệ đối với kiểm tra ghi của đối tượng mảng này. Lệnh đọc `groups[1].get(0)` lại được sử dụng như một chuỗi; giá trị thực tế là `Long`, nên phát sinh `ClassCastException`.

Trong thí nghiệm riêng với `String[]`, việc ghi `99L` bị chặn ngay và in ra `ArrayStoreException`. Hai loại ngoại lệ phản ánh hai vị trí kiểm tra khác nhau.

### Thí nghiệm 2: trả mảng T[] làm lộ một giả định sai

Lời gọi trực tiếp:

```java
String[] direct = asArray("A", "B");
```

tạo mảng `String[]`, như stdout đã cho thấy. Nhưng đường đi gián tiếp là:

```text
main yêu cầu String[]
    → forward("A")
        → trong forward, tham số chỉ có kiểu T
            → asArray(value) tạo Object[] trong ví dụ này
                → trả về rồi bị dùng như String[]
                    → ClassCastException
```

Không có thao tác ghi phần tử sai kiểu nào trong `asArray`; rủi ro ở đây là **trả nguyên mảng varargs ra ngoài**, khiến nơi gọi kỳ vọng một kiểu mảng cụ thể mà đối tượng thực tế không có.

Bài học là “không sửa mảng” chưa đủ để kết luận an toàn. Phải xét cả việc mảng bị trả về, được lưu vào một trường hay được chuyển cho đoạn mã khác. Sao chép bằng `clone()` cũng giữ kiểu mảng thực tế; nó không tự biến `Object[]` thành `String[]`.

## 6. @SafeVarargs là lời cam kết của người viết

`@SafeVarargs` cho biết tác giả đã kiểm tra rằng thân phương thức hoặc constructor không thực hiện thao tác có thể làm mất an toàn kiểu trên tham số varargs.

Theo [tài liệu API SafeVarargs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SafeVarargs.html), annotation này bỏ các cảnh báo unchecked liên quan tới kiểu phần tử varargs không reifiable và việc tạo mảng tham số hóa ở nơi gọi. Nó không thêm kiểm tra kiểu tại lúc chạy và không biến mảng thành cấu trúc lưu giữ đối số generic.

Trên Java 17+, có thể đặt annotation trên:

| Nơi khai báo | Điều kiện |
|---|---|
| Phương thức `static` | Phải là phương thức varargs |
| Phương thức `final` | Phải là phương thức varargs |
| Phương thức `private` | Phải là phương thức varargs |
| Constructor | Phải là constructor varargs |

Phương thức thực thể có thể bị override, không phải `final` hay `private`, không được dùng annotation này. Phương thức không có varargs cũng không được dùng nó.

Các mảnh khai báo dưới đây chỉ minh họa điều kiện đặt annotation:

```java
@SafeVarargs
static <T> void staticMethod(T... items) { }

@SafeVarargs
final <T> void finalMethod(T... items) { }

@SafeVarargs
private <T> void privateMethod(T... items) { }

// Không hợp lệ: phương thức thực thể này có thể bị override.
// @SafeVarargs
// public <T> void overridableMethod(T... items) { }
```

Đối với `String...`, `Object...` hoặc `int...`, kiểu phần tử đã reifiable; annotation không cần thiết để xử lý vấn đề generic-varargs và `javac -Xlint:varargs` có thể báo nó dư thừa.

### Chứng minh an toàn trước khi gắn annotation

Với một phương thức generic-varargs, hãy lần theo mảng đầu vào:

- Có ghi phần tử thông qua một tham chiếu rộng hơn hoặc một phép ép kiểu không kiểm tra không?
- Có trả chính mảng ấy hoặc lưu mảng vào nơi mã khác có thể truy cập không?
- Có truyền mảng cho phương thức khác không? Nếu có, hợp đồng và cách dùng mảng ở nơi nhận đã được kiểm tra chưa?
- Kết quả trả về có độc lập với cấu trúc mảng đầu vào không?
- Những ràng buộc về null và kiểu phần tử có được giải thích riêng không?

Đây là cách thẩm định, không phải một bộ quy tắc cú pháp bảo đảm tự động. Có thể chuyển mảng cho một hàm hỗ trợ đã được chứng minh an toàn; không được suy ra an toàn chỉ vì tên hàm ấy trông có vẻ chỉ đọc.

Gắn `@SafeVarargs` lên mã sai có thể làm im đi tín hiệu quan trọng tại nơi gọi. Trình biên dịch có thể phát hiện một số cách sử dụng nguy hiểm trong thân phương thức, nhưng việc không còn cảnh báo không thay thế cho phân tích luồng tham chiếu.

## 7. Ví dụ an toàn: gom nội dung vào List mới

Mục tiêu của phương thức dưới đây là nhận nhiều danh sách và trả về một danh sách kết quả mới. Nó không cần trả mảng `T[]`.

Lưu tệp `SafeGenericVarargsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeGenericVarargsDemo {
    @SafeVarargs
    static <T> List<T> combine(List<? extends T>... groups) {
        Objects.requireNonNull(groups, "groups");
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(Objects.requireNonNull(group, "group"));
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> words = combine(List.of("Java"), List.of("generics", "varargs"));
        List<Number> numbers = SafeGenericVarargsDemo.<Number>combine(
                List.of(1, 2), List.of(3.5));
        List<String> empty = combine();
        System.out.println(words);
        System.out.println(numbers);
        System.out.println(empty);
        words.add("safe");
        System.out.println(words);
    }
}
```

Biên dịch nghiêm ngặt và chạy:

```shell
javac --release 17 -Xlint:all -Werror SafeGenericVarargsDemo.java
java SafeGenericVarargsDemo
```

Kết quả:

```text
[Java, generics, varargs]
[1, 2, 3.5]
[]
[Java, generics, varargs, safe]
```

Vì sao lời cam kết an toàn phù hợp với `combine`?

1. Phương thức chỉ duyệt mảng `groups`; nó không ghi danh sách khác kiểu vào các vị trí của mảng.
2. Nó không trả mảng varargs, không lưu mảng vào trường và không đưa cả mảng cho nơi khác giữ.
3. Mỗi danh sách có kiểu `List<? extends T>`: các phần tử đọc được có thể thêm vào danh sách đích `List<T>` một cách hợp lệ.
4. Kết quả là `ArrayList<T>` mới, không phải một cách đổi nhãn kiểu cho mảng đầu vào.

Ví dụ `Number` cho phép kết hợp danh sách số nguyên và danh sách số thực dưới kiểu kết quả `List<Number>`. Mã chỉ rõ đối số kiểu `<Number>` để người học nhìn thấy ràng buộc này.

Phương thức cấm mảng `groups` null và cấm một danh sách nguồn null. Nó không tự cấm phần tử null bên trong một danh sách nguồn; `ArrayList` đích có thể chứa chúng. Đó là hợp đồng null riêng, không phải điều mà `@SafeVarargs` xác nhận.

Danh sách kết quả có cấu trúc mới, nhưng các phần tử vẫn là cùng những tham chiếu được đọc từ nguồn. Đây không phải bản sao sâu của từng đối tượng. Việc thêm `"safe"` trong ví dụ chỉ sửa danh sách kết quả.

## 8. Đọc và xử lý cảnh báo đúng chỗ

| Dấu hiệu | Câu hỏi cần kiểm tra | Hướng xử lý |
|---|---|---|
| `Possible heap pollution from parameterized vararg type` tại khai báo | Thân phương thức dùng mảng như thế nào? | Sửa thiết kế hoặc chứng minh an toàn trước khi đặt `@SafeVarargs` |
| `unchecked generic array creation` tại lời gọi | Lời gọi có cần tạo mảng thành phần không reifiable không? | Kiểm tra hợp đồng của phương thức và phương án dùng collection |
| `[varargs]` trong thân phương thức đã có annotation | Mảng có bị lộ, bị ép kiểu hay bị dùng theo cách nguy hiểm không? | Sửa luồng tham chiếu; không bỏ qua chỉ vì đã có annotation |
| Không có cảnh báo | Toàn bộ đường đi của dữ liệu đã hợp lệ chưa? | Vẫn xem xét logic; annotation là cam kết của người viết |

`@SuppressWarnings("unchecked")` và `@SafeVarargs` không cùng ý nghĩa:

- `@SuppressWarnings` yêu cầu trình biên dịch bỏ chẩn đoán trong phạm vi được đánh dấu; nó không phát biểu hợp đồng an toàn của varargs.
- `@SafeVarargs` dành riêng cho cam kết về thao tác trên mảng varargs và ảnh hưởng cả cảnh báo liên quan tại nơi gọi.

Không nên thay việc phân tích bằng một annotation bỏ cảnh báo rộng. Đặc biệt, không thêm `@SuppressWarnings({"unchecked", "varargs"})` chỉ để làm một phương thức trả `T[]` trông sạch cảnh báo.

Nếu không cần cú pháp nhiều đối số, một API nhận `List<List<String>>` hoặc một collection phù hợp có thể tránh nhu cầu tạo mảng generic-varargs. Chọn kiểu collection theo yêu cầu đọc/ghi thực tế; không đổi sang collection rồi thực hiện các phép ép kiểu unchecked tương tự.

Nếu thật sự phải tạo một mảng kết quả có kiểu thành phần cụ thể, thiết kế API có thể nhận bộ tạo mảng như `IntFunction<T[]>`. Khi đó người gọi cung cấp cách tạo, chẳng hạn `String[]::new`, thay vì yêu cầu mã generic đoán kiểu thành phần đã bị xóa. Đây là một lựa chọn thiết kế khác, không phải tác dụng của `@SafeVarargs`.

## 9. Bài tập tự kiểm tra

### Câu 1

Vì sao `List<?>...` không có cùng cảnh báo về kiểu phần tử không reifiable như `List<String>...`?

**Đáp án:** `List<?>` là kiểu reifiable và không khẳng định một đối số kiểu cụ thể như `String`. Đổi sang `List<?>` cũng làm thay đổi những gì thân phương thức có thể biết về phần tử của từng danh sách; nó không phải cách viết khác giữ nguyên toàn bộ hợp đồng `List<String>`.

### Câu 2

Một phương thức `static <T> T[] keep(T... values)` chỉ trả `values`, không sửa phần tử. Có đủ cơ sở để đặt `@SafeVarargs` không?

**Đáp án:** Không chỉ dựa vào lý do “không ghi”. Trả nguyên mảng làm lộ mảng varargs; đường gọi qua phương thức generic có thể tạo mảng với kiểu thực tế không đáp ứng kỳ vọng kiểu mảng cụ thể của nơi nhận. Thí nghiệm `forward` cho thấy lỗi này.

### Câu 3

Đặt `@SafeVarargs` có khiến JVM kiểm tra rằng mọi phần tử của một `List<String>` thật sự là `String` không?

**Đáp án:** Không. Annotation không thêm bộ kiểm tra kiểu phần tử lúc chạy; nó thể hiện kết luận đã được người viết thẩm định.

### Câu 4

Phương thức `combine` trả danh sách mới thì có phải sao chép sâu mọi phần tử không?

**Đáp án:** Không. Nó tạo cấu trúc danh sách kết quả độc lập và chép tham chiếu phần tử. An toàn của việc dùng mảng varargs, quyền sửa cấu trúc collection và khả năng biến đổi đối tượng phần tử là những vấn đề cần phân biệt.

Khi gặp generic-varargs, hãy xác định **kiểu mảng thực tế**, rồi theo dõi **mọi nơi có thể ghi hoặc giữ mảng**. Chỉ sau đó mới quyết định giữ thiết kế, thay bằng collection hay công bố lời cam kết `@SafeVarargs`.
