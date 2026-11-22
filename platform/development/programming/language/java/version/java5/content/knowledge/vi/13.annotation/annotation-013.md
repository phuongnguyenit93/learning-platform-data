# @SuppressWarnings và giới hạn phạm vi tắt cảnh báo

## Cảnh báo cho biết điều gì?

Trình biên dịch có thể chấp nhận một chương trình nhưng vẫn cảnh báo rằng một thao tác cần được kiểm tra thêm. Chẳng hạn, phép ép kiểu liên quan đến kiểu tổng quát có thể hợp lệ về cú pháp, song trình biên dịch không có đủ thông tin để xác nhận an toàn kiểu.

Cách xử lý đầu tiên là đọc thông báo và sửa thiết kế nếu có thể. Khi đã có lập luận rõ ràng rằng một thao tác cụ thể an toàn, ta có thể dùng `@SuppressWarnings` để tắt nhóm cảnh báo tương ứng tại đúng vị trí đó. Annotation này có sẵn trong `java.lang`, không cần `import`.

Bài học tập trung vào ba câu hỏi: cảnh báo nào đang bị tắt, phạm vi nào chịu ảnh hưởng và điều gì chứng minh đoạn mã vẫn đúng. Ví dụ dùng Java 17+ và các API vẫn đang được sử dụng.

## Cú pháp và các nhóm cảnh báo

`value()` của `SuppressWarnings` là một mảng chuỗi. Với một giá trị, có thể viết `@SuppressWarnings("unchecked")`; với nhiều giá trị, dùng `@SuppressWarnings({"unchecked", "rawtypes"})`. Việc thêm tên nhóm phải dựa trên cảnh báo thật. Xem [quy định ngôn ngữ về `SuppressWarnings`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.5).

| Khóa | Điều cần hiểu |
| --- | --- |
| `unchecked` | Có thao tác mà trình biên dịch không kiểm tra đầy đủ được tính an toàn kiểu, ví dụ một số phép ép kiểu có kiểu tổng quát |
| `deprecation` | Sử dụng API đã bị đánh dấu không còn được khuyến nghị |
| `removal` | Sử dụng API đã bị đánh dấu dự kiến loại bỏ; đây là nhóm riêng với `deprecation` |
| `rawtypes` | Khóa của `javac` cho việc dùng kiểu tổng quát mà không cung cấp đối số kiểu |

Không xem các khóa của IDE hay công cụ phân tích khác là khóa chuẩn của mọi trình biên dịch. Với `javac`, chạy `javac --help-lint` để xem danh sách được hỗ trợ. Tên sai hoặc không được nhận biết không đảm bảo làm quá trình biên dịch thất bại; vì vậy cần kiểm chứng rằng cảnh báo mong muốn thực sự đã được xử lý. Xem [API `SuppressWarnings`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SuppressWarnings.html).

`unchecked` và `rawtypes` giải quyết hai nhóm khác nhau. Thêm `unchecked` không phải cách sửa khai báo như `List items`; trong mã mới, nên dùng kiểu có đối số phù hợp, chẳng hạn `List<String>` hoặc `List<?>`, tùy ý nghĩa dữ liệu.

## Chọn phạm vi nhỏ nhất

Annotation tác động tới khai báo được đánh dấu và phần mã nằm trong phạm vi đó. Những vị trí thường dùng gồm khai báo lớp, phương thức, hàm tạo, trường và biến cục bộ. Đặt ở cấp lớp sẽ ảnh hưởng rộng hơn đặt ở một biến trong một phương thức.

Ví dụ, nếu một phép ép kiểu nằm trong phần khởi tạo biến, hãy đặt annotation ngay trên **khai báo biến đó**. Các phép ép kiểu khác được thêm về sau trong phương thức vẫn cần được trình biên dịch kiểm tra.

Phạm vi tắt cảnh báo được cộng dồn từ các khai báo bao ngoài. Một annotation ở phương thức không bật lại nhóm cảnh báo đã bị lớp bao ngoài tắt; `@SuppressWarnings({})` cũng không phải lệnh bật lại. Muốn thu hẹp, phải di chuyển hoặc bỏ annotation ở phạm vi rộng. Đây là quy tắc phạm vi, không phải cơ chế kế thừa qua `extends`. Xem [phạm vi tác động trong API `SuppressWarnings`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SuppressWarnings.html).

Không thể tùy ý đặt annotation này trước một câu lệnh `return`, một câu lệnh gán hay một khối `if`. Khi phép ép kiểu đang nằm trong `return`, có thể tách thành biến cục bộ để có một khai báo phù hợp làm nơi đặt annotation.

## Ví dụ hoàn chỉnh: một phép ép kiểu có căn cứ và một phép ép kiểu sai

Giả sử cần tạo mảng có kiểu phần tử xác định khi chạy. `Array.newInstance` tạo mảng theo `Class` được truyền vào nhưng trả về `Object`; phép chuyển kết quả thành `T[]` phát sinh cảnh báo `unchecked`.

Ta sẽ đối chiếu hai cách tạo mảng. Cách thứ nhất dùng đúng kiểu phần tử và giải thích căn cứ an toàn ngay tại phép ép kiểu. Cách thứ hai cố tình tạo `Object[]` rồi giả định đó là `T[]`, nhằm quan sát lỗi mà suppression không ngăn được.

Lưu toàn bộ mã sau trong tệp `SuppressionScopeDemo.java`:

```java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.Objects;

public final class SuppressionScopeDemo {
    private SuppressionScopeDemo() {
    }

    static <T> T[] newArray(Class<T> componentType, int length) {
        Objects.requireNonNull(componentType, "componentType");
        if (componentType.isPrimitive()) {
            throw new IllegalArgumentException("reference type required");
        }

        // Safe: the array is created with the same reference type as Class<T>.
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(componentType, length);
        return result;
    }

    // Deliberately wrong: used only to demonstrate the runtime failure.
    static <T> T[] unsafeArray(int length) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) new Object[length];
        return result;
    }

    public static void main(String[] args) {
        String[] names = newArray(String.class, 2);
        names[0] = "An";
        names[1] = "Binh";
        System.out.println(Arrays.toString(names));
        System.out.println(names.getClass().getComponentType().getSimpleName());

        try {
            String[] invalid = unsafeArray(2);
            System.out.println(invalid.length);
        } catch (ClassCastException ex) {
            System.out.println("unsafe: ClassCastException");
        }
    }
}
```

Chạy bằng JDK 17 trở lên tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror SuppressionScopeDemo.java
java SuppressionScopeDemo
```

Với mã nguyên vẹn, lệnh biên dịch thành công. Stdout chính xác:

```text
[An, Binh]
String
unsafe: ClassCastException
```

### Vì sao `newArray` có căn cứ an toàn?

- `Class<T>` gắn đối số kiểu `T` với kiểu thành phần được dùng để tạo mảng; ở lời gọi đầu tiên, đó là `String.class`.
- `Array.newInstance(String.class, 2)` tạo một `String[]` thật, không phải một `Object[]` chứa các chuỗi.
- Kiểm tra `isPrimitive()` loại bỏ trường hợp như `int.class`. Mảng `int[]` không phải mảng các đối tượng `Integer`; không thể dùng nhánh tạo mảng nguyên thủy này để trả về `T[]`.
- Phép ép kiểu duy nhất cần tắt cảnh báo nằm ngay trong phần khởi tạo `result`. Chú thích giải thích **vì sao** nó an toàn, không chỉ lặp lại tên cảnh báo.

Lập luận dựa trên việc bên gọi sử dụng `Class<T>` đúng kiểu. Không dùng raw type hay các phép ép kiểu không được kiểm tra để giả mạo một `Class<T>` không khớp với kiểu thực.

### Vì sao `unsafeArray` vẫn thất bại?

`new Object[length]` tạo `Object[]`. Nó không trở thành `String[]` chỉ vì bên gọi suy luận `T` là `String`. Do xóa kiểu, phần thân phương thức có thể trả mảng đó ra ngoài, nhưng khi gán kết quả vào `String[]`, phép kiểm tra kiểu lúc chạy thất bại.

Ở đây, cả hai phép ép kiểu đều đã tắt cảnh báo. Tuy vậy, chỉ phương thức đầu tạo đúng kiểu mảng. `@SuppressWarnings` không chuyển đổi đối tượng, không thêm kiểm tra kiểu và không bắt ngoại lệ. `unsafeArray` là phản ví dụ có chủ ý, không phải mẫu để đưa vào mã ứng dụng.

## Tự xác minh phạm vi suppression

Thực hiện từng thử nghiệm riêng trên bản sao của ví dụ:

1. Chỉ bỏ annotation ngay trước `result` trong `newArray`, rồi chạy lại đúng lệnh `javac`. Cảnh báo `unchecked` xuất hiện ở phép ép kiểu đó và `-Werror` khiến biên dịch thất bại.
2. Khôi phục annotation, sau đó bỏ annotation trong `unsafeArray`. Cảnh báo tại phép ép kiểu ở phương thức này xuất hiện; annotation trong `newArray` không che nó.
3. Di chuyển suppression lên khai báo lớp và bỏ hai annotation cục bộ. Cả hai phép ép kiểu đều bị tắt cảnh báo. Lệnh biên dịch thành công nhưng lỗi lúc chạy của `unsafeArray` vẫn xảy ra.
4. Khôi phục hai annotation cục bộ để các cảnh báo mới ở nơi khác vẫn được phát hiện.

Không phụ thuộc vào nguyên văn thông báo chẩn đoán: số dòng, cách diễn đạt và ngôn ngữ có thể khác giữa các bản JDK. Điều cần quan sát là nhóm `[unchecked]`, vị trí phép ép kiểu và trạng thái thành công/thất bại của lệnh.

## Sửa thiết kế trước khi tắt cảnh báo

Một suppression chỉ hợp lý khi ta biết rõ giới hạn mà hệ thống kiểu chưa biểu diễn được. Nếu có cách diễn đạt yêu cầu bằng API an toàn kiểu, nên chọn cách đó.

Chẳng hạn, nếu chỉ cần tạo mảng rỗng trong một luồng xử lý nội bộ và nơi gọi đã biết kiểu, có thể truyền hàm tạo mảng thay vì tự ép kiểu. Đoạn sau là phương thức độc lập có thể đặt trong một lớp; cần `import java.util.function.IntFunction`:

```java
static <T> T[] createArray(IntFunction<T[]> factory, int length) {
    return factory.apply(length);
}
```

Lời gọi trong một phương thức:

```java
String[] names = createArray(String[]::new, 2);
```

Không có phép ép kiểu cần suppression ở đây. Chọn giải pháp theo dữ liệu đầu vào thật: `Class<T>` phù hợp khi kiểu đến từ metadata lúc chạy; hàm tạo `String[]::new` phù hợp khi nơi gọi biết kiểu và có thể cung cấp cách tạo mảng.

Tương tự, khi cần kiểm tra từng phần tử của dữ liệu tổng quát, có thể dùng `Class.cast` và tạo một tập hợp mới đã kiểm tra. Không ép cả một `List<?>` thành `List<String>` chỉ vì một vài phần tử đầu tiên đang là chuỗi.

## Giới hạn cần nhớ

`@SuppressWarnings` có retention `SOURCE`: đây là chỉ dẫn trong mã nguồn cho quá trình biên dịch, không phải cấu hình để framework đọc bằng reflection khi chạy. Nó không tắt lỗi cú pháp, lỗi kiểu thực sự hoặc ngoại lệ lúc chạy. Xem [khai báo API `SuppressWarnings`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/SuppressWarnings.html).

Không phải mọi chẩn đoán đều gắn với một khai báo có thể đánh dấu. Ví dụ, tài liệu `javac` nêu rằng cảnh báo `path` về phần tử đường dẫn không hợp lệ không thể được tắt bằng annotation này. `-Xlint:all` bật các nhóm cảnh báo lint mà `javac` hỗ trợ, còn `-Werror` làm lệnh thất bại khi phát sinh cảnh báo. Xem [các tùy chọn của `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

Cảnh báo IDE, trình phân tích tĩnh hoặc annotation processor có thể có cơ chế cấu hình riêng. Suppression được một công cụ nhận biết không đảm bảo công cụ khác xử lý giống vậy.

Tránh dùng một khóa tắt toàn bộ cảnh báo dựa trên thói quen của IDE. Đồng thời, việc biên dịch với suppression và `-Werror` thành công chỉ chứng minh các cảnh báo còn bật không làm lệnh thất bại; nó không chứng minh mọi cảnh báo tiềm ẩn đã được sửa hay mọi đường chạy đều đúng.

## Quy trình áp dụng trong mã thật

1. Bật cảnh báo phù hợp, đọc chính xác nhóm và vị trí phát sinh.
2. Thử bỏ phép ép kiểu, sửa đối số kiểu hoặc thay API bằng phương án an toàn hơn.
3. Nếu suppression vẫn cần thiết, viết được lập luận an toàn dựa trên kiểu dữ liệu, cách tạo và cách sử dụng.
4. Đặt đúng khóa trên khai báo nhỏ nhất có hiệu lực; ưu tiên biến cục bộ thay vì cả phương thức khi làm được.
5. Ghi chú căn cứ ngay gần annotation và kiểm thử hành vi liên quan.
6. Bỏ suppression khi thay đổi mã đã loại bỏ nguyên nhân; nhiều cấu hình biên dịch không tự báo một suppression đã trở nên thừa.

Với ví dụ trên, người đọc cần chỉ ra được căn cứ của `newArray`, nguyên nhân thất bại của `unsafeArray` và lý do không đặt `@SuppressWarnings("unchecked")` lên cả lớp chỉ để lệnh biên dịch thành công.