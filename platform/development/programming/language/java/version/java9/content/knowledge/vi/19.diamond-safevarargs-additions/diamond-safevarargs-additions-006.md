# Phân biệt an toàn kiểu thực tế với việc bỏ cảnh báo trong Java Generics

Khi làm việc với Java Generics, một cảnh báo như unchecked cast hoặc unchecked conversion có nghĩa là trình biên dịch không thể chứng minh phép chuyển đổi kiểu là an toàn. Thêm `@SuppressWarnings("unchecked")` chỉ làm ẩn cảnh báo đó. Annotation không kiểm tra dữ liệu, không chuyển đổi phần tử và không bổ sung kiểm tra kiểu lúc chạy.

Muốn phân biệt mã thực sự an toàn với mã chỉ im lặng trước cảnh báo, cần xem xét cả hợp đồng kiểu ở thời điểm biên dịch, dữ liệu thực tế tại ranh giới chạy chương trình và những invariant bảo đảm kiểu của từng phần tử.

## 1. An toàn kiểu trong Generics hoạt động ở đâu?

Generics giúp trình biên dịch kiểm tra kiểu khi biên dịch. Ví dụ:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
String first = names.get(0);
~~~

Trình biên dịch biết `names` chỉ nhận `String`, nên từ chối thao tác thêm một kiểu không tương thích:

~~~java
List<String> names = new ArrayList<>();
names.add(42); // Lỗi biên dịch: int không thể chuyển thành String
~~~

Đây là kiểm tra kiểu thực tế do hệ thống kiểu của Java thực hiện. Không cần ép kiểu thủ công khi đọc phần tử.

### Generics có tính bất biến

`List<Integer>` không phải kiểu con của `List<Number>`, dù `Integer` là kiểu con của `Number`.

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // Không biên dịch
~~~

Nếu phép gán đó được chấp nhận, mã có thể thêm một `Double` qua biến `numbers` vào danh sách vốn chỉ dành cho `Integer`. Tính bất biến ngăn lỗi này ngay ở thời điểm biên dịch.

Khi cần làm việc với nhiều kiểu con của một kiểu chung, hãy dùng wildcard có giới hạn thay vì ép kiểu:

- `List<? extends Number>`: nguồn dữ liệu có phần tử thuộc một kiểu con chưa xác định của `Number`. Có thể đọc an toàn dưới dạng `Number`; không thể thêm một `Integer` tùy ý vì danh sách thực tế có thể là `List<Double>`.
- `List<? super Integer>`: đích nhận dữ liệu có kiểu phần tử là `Integer` hoặc một kiểu cha của nó. Có thể thêm `Integer`; khi đọc, chỉ có thể dựa chắc chắn vào kiểu `Object`.
- `List<?>`: danh sách có kiểu phần tử chưa biết. Có thể đọc dưới dạng `Object`; không thể thêm phần tử tùy ý, ngoại trừ `null`.

Quy tắc thường dùng là PECS: Producer Extends, Consumer Super. Wildcard giúp biểu diễn đúng vai trò đọc hoặc ghi và tránh nhiều phép ép kiểu không cần thiết.

## 2. Vì sao trình biên dịch phát cảnh báo unchecked?

Cảnh báo unchecked xuất hiện khi trình biên dịch không có đủ thông tin kiểu để xác nhận phép chuyển đổi. Những nguồn thường gặp gồm:

- Ép một giá trị `Object` hoặc `List<?>` sang `List<String>`.
- Chuyển một collection không có tham số kiểu sang một collection có tham số kiểu.
- Gọi hoặc triển khai varargs có kiểu phần tử generic không thể reify.
- Làm việc tại ranh giới với thư viện hoặc dữ liệu được cung cấp mà thông tin generic đã mất.

Một cảnh báo không chứng minh rằng dữ liệu chắc chắn sai. Nó cho biết trình biên dịch chưa có bằng chứng để bảo đảm dữ liệu đúng. Mã có thể an toàn nhờ một invariant bên ngoài, nhưng invariant đó phải được giải thích và bảo vệ bằng thiết kế hoặc kiểm tra thực tế.

### Type erasure giới hạn điều gì ở runtime?

Java thực hiện type erasure: thông tin tham số kiểu generic được loại bỏ hoặc thay bằng giới hạn kiểu phù hợp khi biên dịch. Vì vậy, JVM không thể kiểm tra trực tiếp rằng một đối tượng là `List<String>` thay vì `List<Integer>`.

Có thể kiểm tra kiểu ngoài của collection bằng một kiểu reifiable:

~~~java
if (value instanceof List<?> values) {
    // Đã biết value là một List, nhưng chưa biết kiểu từng phần tử.
}
~~~

Không thể dùng `instanceof List<String>`, vì `List<String>` không phải kiểu reifiable. Kiểm tra `instanceof List<?>` chỉ xác nhận đối tượng là một List; nó không xác nhận nội dung đều là chuỗi.

Khi đọc phần tử qua một biến `List<String>`, trình biên dịch có thể chèn phép cast sang `String`. Nếu danh sách thực tế chứa một `Integer`, lỗi `ClassCastException` có thể chỉ xuất hiện ở lần đọc phần tử đó. Đây là lý do một unchecked cast có thể làm lỗi xuất hiện xa vị trí gây ra nó.

## 3. SuppressWarnings chỉ ẩn thông báo

Ví dụ sau biên dịch mà không hiển thị cảnh báo unchecked vì annotation đã yêu cầu trình biên dịch bỏ qua cảnh báo tại phạm vi phương thức:

~~~java
@SuppressWarnings("unchecked")
static List<String> assumeStrings(List<?> values) {
    return (List<String>) values;
}
~~~

Phép cast trên không duyệt danh sách và không kiểm tra từng phần tử. Nó trả về cùng đối tượng với một kiểu khai báo khác. Nếu danh sách chứa phần tử không phải `String`, lỗi có thể phát sinh khi phần tử được đọc như `String`.

Các điểm cần nhớ:

- `@SuppressWarnings("unchecked")` không biến phép cast unchecked thành checked cast.
- Annotation không tạo bản sao, không lọc dữ liệu và không chuyển đổi phần tử.
- Annotation không ngăn thư viện khác thêm dữ liệu sai vào cùng đối tượng.
- Lỗi runtime vẫn có thể xảy ra tại vị trí đọc hoặc sử dụng phần tử.
- Phạm vi suppression càng rộng thì càng khó phát hiện một thao tác unchecked mới được thêm vào sau này.

Vì vậy, không dùng annotation chỉ để làm sạch cửa sổ Problems hoặc làm cho build không còn cảnh báo. Trước khi suppression, hãy xác định chính xác vì sao compiler không chứng minh được phép chuyển đổi và invariant nào bảo đảm phép chuyển đổi đúng.

## 4. Kiểm tra dữ liệu thực tế tại ranh giới

Khi nhận collection từ dữ liệu bên ngoài, API không có generic đầy đủ hoặc một vùng mã không kiểm soát được, hãy coi nội dung là chưa đáng tin cậy. Có thể xác nhận kiểu ngoài bằng `List<?>`, sau đó kiểm tra từng phần tử và tạo một collection mới có kiểu rõ ràng.

Ví dụ:

~~~java
static List<String> validatedCopy(List<?> values) {
    List<String> result = new ArrayList<>(values.size());

    for (Object value : values) {
        if (!(value instanceof String text)) {
            String actualType = value == null
                ? "null"
                : value.getClass().getSimpleName();

            throw new IllegalArgumentException(
                "Expected String but got " + actualType
            );
        }

        result.add(text);
    }

    return List.copyOf(result);
}
~~~

Sau vòng lặp, mọi phần tử đã được xác nhận là `String`. Collection kết quả được tạo mới và chỉ chứa các giá trị đã kiểm tra. `List.copyOf` trả về danh sách không sửa đổi được và cũng từ chối phần tử null; ví dụ đã kiểm tra null trước khi thêm.

Nếu chỉ cần kiểm tra một đối tượng đơn lẻ, có thể dùng `Class<T>.cast(value)` để thực hiện kiểm tra kiểu runtime theo class token. Với cấu trúc generic lồng nhau, class token thông thường không chứa đủ thông tin như `List<String>`; cần kiểm tra từng tầng hoặc dùng cơ chế type token/decoder có hỗ trợ kiểu generic.

Không nên cast cả collection chỉ vì đã kiểm tra được một vài phần tử. Muốn kết luận collection an toàn, cần bảo đảm mọi phần tử đều đúng kiểu và không có đường ghi khác làm thay đổi invariant sau khi kiểm tra.

## 5. Ví dụ Java chạy được: suppression không làm dữ liệu an toàn

Ví dụ dưới đây cố ý tạo một danh sách có cả chuỗi và số nguyên. Phương thức `uncheckedView` che cảnh báo, còn `validatedCopy` kiểm tra từng phần tử trước khi trả về danh sách có kiểu rõ ràng.

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericSafetyVsWarningSuppression {
    @SuppressWarnings("unchecked")
    private static List<String> uncheckedView(List<?> values) {
        return (List<String>) values;
    }

    private static List<String> validatedCopy(List<?> values) {
        List<String> result = new ArrayList<>(values.size());

        for (Object value : values) {
            if (!(value instanceof String text)) {
                String actualType = value == null
                    ? "null"
                    : value.getClass().getSimpleName();

                throw new IllegalArgumentException(
                    "Expected String but got " + actualType
                );
            }

            result.add(text);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<?> mixed = List.of("alpha", 42);

        System.out.println("-- unchecked cast --");
        List<String> assumed = uncheckedView(mixed);
        System.out.println("cast returned");
        System.out.println("first=" + assumed.get(0));

        try {
            System.out.println("second=" + assumed.get(1));
        } catch (ClassCastException ex) {
            System.out.println("read failure="
                + ex.getClass().getSimpleName());
        }

        System.out.println("-- validate elements --");
        System.out.println("valid="
            + validatedCopy(List.of("A", "B")));

        try {
            validatedCopy(mixed);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName()
                + ": " + ex.getMessage());
        }
    }
}
~~~

Lưu mã trong tệp `GenericSafetyVsWarningSuppression.java`, sau đó biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all GenericSafetyVsWarningSuppression.java
java GenericSafetyVsWarningSuppression
~~~

Kết quả stdout:

~~~text
-- unchecked cast --
cast returned
first=alpha
read failure=ClassCastException
-- validate elements --
valid=[A, B]
invalid=IllegalArgumentException: Expected String but got Integer
~~~

Phân tích:

1. `uncheckedView` trả về được một biến khai báo là `List<String>`; annotation chỉ che cảnh báo tại phép cast.
2. Phần tử đầu là chuỗi nên đọc được bình thường. Phần tử thứ hai là `Integer`; khi đọc qua `List<String>`, cast do trình biên dịch chèn vào thất bại và ném `ClassCastException`.
3. `validatedCopy` duyệt toàn bộ danh sách trước khi trả về. Danh sách hợp lệ tạo được bản sao chỉ chứa chuỗi.
4. Danh sách trộn chuỗi và số bị từ chối ngay tại ranh giới bằng `IllegalArgumentException`, nên mã gọi không nhận một `List<String>` chứa dữ liệu sai kiểu.

## 6. Khi nào suppression có thể được chấp nhận?

Có trường hợp compiler không thể suy ra một invariant dù mã đã có cơ chế bảo đảm. Khi đó suppression có thể hợp lý, nhưng phải có bằng chứng cụ thể.

Trước khi thêm `@SuppressWarnings("unchecked")`, cần trả lời được:

1. Giá trị đến từ đâu và ai kiểm soát nó?
2. Cơ chế nào bảo đảm kiểu thực tế của tất cả phần tử?
3. Có đường ghi nào khác có thể phá vỡ invariant không?
4. Nếu dữ liệu không đúng, lỗi được phát hiện ở đâu?
5. Có thể thay bằng wildcard, API generic, kiểm tra runtime hoặc bản sao đã xác thực không?

Nếu không chứng minh được các điều kiện trên, hãy giữ cảnh báo và sửa thiết kế.

### Đặt suppression ở phạm vi nhỏ nhất

Nếu suppression thật sự cần thiết, hãy đặt trên biến hoặc phương thức nhỏ nhất chứa đúng phép chuyển đổi, không đặt ở cấp lớp hay toàn package. Viết comment nêu invariant và nguồn bảo đảm invariant đó. Người bảo trì phải có thể kiểm tra bằng mã hoặc hợp đồng API, thay vì phải tin vào một lời khẳng định chung chung.

Ví dụ về hình thức tổ chức:

~~~java
// Invariant: phần tử được tạo duy nhất từ bộ giải mã đã xác thực kiểu.
@SuppressWarnings("unchecked")
List<String> decoded = (List<String>) trustedDecoderResult;
~~~

Đoạn này chỉ là mẫu về phạm vi annotation. Chỉ sử dụng khi `trustedDecoderResult` thực sự được bảo đảm chứa toàn bộ phần tử String bởi bộ giải mã và không có đường ghi không an toàn. Tên biến hoặc comment tự nó không tạo ra bảo đảm.

## 7. Phân biệt @SuppressWarnings và @SafeVarargs

Hai annotation có mục đích khác nhau:

- `@SuppressWarnings("unchecked")` yêu cầu compiler không báo một nhóm cảnh báo tại phạm vi được chú thích.
- `@SafeVarargs` là lời cam kết rằng việc triển khai phương thức hoặc constructor varargs không thực hiện thao tác gây heap pollution qua mảng varargs generic.

Varargs generic có rủi ro vì tham số varargs được biểu diễn bằng mảng ở runtime trong khi kiểu phần tử generic có thể đã bị type erasure. Annotation `@SafeVarargs` không thêm kiểm tra runtime và không tự làm phương thức an toàn.

Chỉ dùng `@SafeVarargs` khi phần thân phương thức không ghi phần tử sai kiểu vào mảng varargs, không để lộ mảng có thể bị sửa theo cách phá vỡ kiểu, và không chuyển mảng cho mã không đáng tin cậy. Annotation này áp dụng cho constructor và phương thức varargs có khai báo `static`, `final` hoặc `private`; từ Java 9, phương thức instance private cũng được phép dùng.

Nếu không chứng minh được cam kết đó, hãy thiết kế API nhận `List<T>` hoặc một collection có kiểu rõ ràng thay vì dựa vào annotation.

## 8. Các cách thiết kế giúp tránh unchecked warning

- Khai báo tham số kiểu ở API ngay từ đầu, ví dụ `List<String>` thay vì `List`.
- Dùng wildcard khi chỉ cần đọc hoặc ghi theo một quan hệ kiểu, theo nguyên tắc PECS.
- Dùng `List<?>` ở ranh giới chưa biết kiểu, rồi xác thực phần tử trước khi chuyển thành collection có kiểu cụ thể.
- Ưu tiên tạo collection mới đã xác thực thay vì cast và tiếp tục dùng đối tượng đầu vào.
- Dùng `Class<T>.cast` cho kiểm tra một giá trị theo class token.
- Không ép một mảng `Object[]` hoặc mảng raw sang `T[]` rồi coi đó là an toàn. Ưu tiên collection generic; mảng và generic có quy tắc runtime khác nhau.
- Tránh raw type vì nó làm mất kiểm tra tham số kiểu và thường kéo theo unchecked conversion ở những nơi khác.
- Bật `-Xlint:unchecked` hoặc `-Xlint:all` khi cần rà soát cảnh báo trong quá trình phát triển.
- Giữ suppression cục bộ, có comment nêu invariant và có kiểm thử cho dữ liệu đúng lẫn dữ liệu sai.

## 9. Những hiểu nhầm thường gặp

- **Ẩn cảnh báo đồng nghĩa với sửa lỗi:** sai. Suppression chỉ thay đổi báo cáo của compiler.
- **Cast sang `List<String>` sẽ kiểm tra tất cả phần tử:** sai. Type erasure không cho phép JVM kiểm tra tham số kiểu generic đó.
- **Kiểm tra `instanceof List<?>` chứng minh danh sách chỉ chứa String:** sai. Nó chỉ xác nhận kiểu ngoài là List.
- **Nếu phần tử đầu tiên đọc được thì cả danh sách an toàn:** sai. Phần tử sai kiểu có thể nằm ở bất kỳ vị trí nào.
- **Wildcard là cách tắt kiểm tra kiểu:** sai. Wildcard mô tả chính xác mức kiểu có thể đọc hoặc ghi an toàn.
- **Mọi unchecked warning đều có nghĩa dữ liệu chắc chắn sai:** sai. Nó có nghĩa compiler không chứng minh được tính an toàn; người viết phải cung cấp invariant hoặc kiểm tra còn thiếu.
- **Thêm comment cạnh annotation là đủ:** sai. Comment phải mô tả một invariant có thể xác minh bằng mã hoặc hợp đồng API.

## 10. Tài liệu tham khảo chính thức

- [Java Language Specification — Types, Type Erasure, Reifiable Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html): hệ thống kiểu generic, type erasure, raw types và reifiable types.
- [Java Language Specification — Conversions and Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html): các phép chuyển đổi kiểu và unchecked conversion.
- [SuppressWarnings — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SuppressWarnings.html): phạm vi và mục đích của annotation suppression.
- [SafeVarargs — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SafeVarargs.html): hợp đồng của annotation cho varargs generic.
- [Dev.java — Generics](https://dev.java/learn/generics/): cách khai báo và sử dụng generic types trong Java.