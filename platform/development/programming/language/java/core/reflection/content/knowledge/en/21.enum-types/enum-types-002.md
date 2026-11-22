# Thứ tự hằng enum và khi `getEnumConstants()` trả về `null`

Khi một công cụ chỉ nhận được `Class<?>` lúc chạy, nó có thể cần biết kiểu đó có phải enum không và nếu có thì gồm những hằng nào. Ví dụ, công cụ tạo biểu mẫu cần liệt kê lựa chọn, còn bộ kiểm tra cấu hình cần biết các giá trị hợp lệ.

`Class.getEnumConstants()` giải quyết việc liệt kê này mà không cần biết tên enum khi viết công cụ. Có hai quy tắc cần nắm: **các hằng được trả về theo thứ tự khai báo**; **`null` khác với một mảng enum rỗng**. Ngoài ra, lớp thực tế của một hằng enum có phần thân riêng có thể khác lớp khai báo enum.

## 1. Hiểu đúng giá trị trả về

Chữ ký API trên `Class<T>` là:

```java
public T[] getEnumConstants()
```

Đây là chữ ký để tra cứu API, không phải một phương thức cần tự cài đặt. Nếu biến có kiểu `Class<Stage>`, lời gọi trả kiểu `Stage[]`. Nếu chỉ có `Class<?>`, có thể nhận kết quả vào `Object[]` rồi kiểm tra trước khi sử dụng.

Theo [hợp đồng của `Class.getEnumConstants()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getEnumConstants()), kết quả là các hằng theo thứ tự khai báo, hoặc `null` khi đối tượng `Class` không đại diện cho một khai báo enum.

| Kiểu được truy vấn | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Enum có hằng | Mảng chứa các hằng | Có tập lựa chọn để duyệt |
| Enum không có hằng | Mảng độ dài `0` | Là enum, nhưng tập hằng rỗng |
| Lớp thông thường, interface, kiểu nguyên thủy hoặc kiểu mảng | `null` | Kiểu đang xét không phải khai báo enum |

Không gọi `.length`, dùng vòng `for` hoặc tạo luồng từ kết quả trước khi phân biệt các trường hợp này. Nếu nhận `null`, bạn chưa có một mảng để duyệt.

## 2. Thứ tự khai báo không phải thứ tự tên

Giả sử enum được khai báo như sau:

```java
enum Stage {
    REVIEW, DRAFT, PUBLISHED
}
```

Kết quả duyệt là `REVIEW`, `DRAFT`, `PUBLISHED`, không phải thứ tự bảng chữ cái. `Stage.values()` cũng trả các hằng theo thứ tự khai báo; phương thức này được khai báo ngầm cho từng enum theo [JLS về thành viên enum](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9.3).

Mỗi hằng có `ordinal()` bắt đầu từ `0`, tương ứng vị trí khai báo. `name()` cho tên khai báo; `toString()` có thể được ghi đè để tạo nhãn hiển thị. Đó là những vai trò khác nhau trong [API `Enum`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html).

Trong ví dụ trên, `REVIEW.ordinal()` là `0` dù từ `DRAFT` đứng trước nó khi sắp xếp tên. Vì vậy, cần xác định bạn muốn bảo toàn thứ tự khai báo hay muốn tạo một thứ tự hiển thị riêng.

## 3. Thí nghiệm Java 17+ chạy độc lập

Chương trình sau kiểm tra thứ tự, enum rỗng, kiểu không phải enum, lớp riêng của hằng và cách từ chối đầu vào không phù hợp.

Lưu toàn bộ vào **`EnumConstantsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;

public class EnumConstantsDemo {
    enum Stage {
        REVIEW, DRAFT, PUBLISHED
    }

    enum Empty {
    }

    enum Flavor {
        BASIC,
        CUSTOM {
            @Override
            public String toString() {
                return "Custom label";
            }
        }
    }

    private static String names(Class<?> type) {
        Object[] constants = type.getEnumConstants();
        if (constants == null) {
            return "null";
        }
        return Arrays.stream(constants)
                .map(value -> ((Enum<?>) value).name())
                .toList()
                .toString();
    }

    private static Object[] requireEnumConstants(Class<?> type) {
        Objects.requireNonNull(type, "type");
        Object[] constants = type.getEnumConstants();
        if (constants == null) {
            throw new IllegalArgumentException(
                    type.getTypeName() + " is not an enum declaration");
        }
        return constants;
    }

    public static void main(String[] args) {
        System.out.println("Stage constants = " + names(Stage.class));
        System.out.println("Stage values = " + Arrays.toString(Stage.values()));
        for (Stage stage : Stage.class.getEnumConstants()) {
            System.out.println(stage.name() + " ordinal = " + stage.ordinal());
        }

        Stage[] sorted = Stage.class.getEnumConstants();
        Arrays.sort(sorted, Comparator.comparing(Stage::name));
        System.out.println("Sorted by name = " + Arrays.toString(sorted));
        System.out.println("Declaration order = " + names(Stage.class));

        System.out.println("Empty is enum = " + Empty.class.isEnum());
        System.out.println("Empty constants = " + names(Empty.class));
        System.out.println("Empty count = " + Empty.class.getEnumConstants().length);

        System.out.println("String constants = " + names(String.class));
        System.out.println("Enum constants = " + names(Enum.class));
        System.out.println("Array constants = " + names(Stage[].class));
        System.out.println("int constants = " + names(int.class));

        Enum<?> selected = Flavor.CUSTOM;
        System.out.println("CUSTOM instanceof Enum = " + (selected instanceof Enum<?>));
        System.out.println("BASIC runtime is enum = " + Flavor.BASIC.getClass().isEnum());
        System.out.println("CUSTOM runtime is enum = " + selected.getClass().isEnum());
        System.out.println("CUSTOM runtime constants = " + names(selected.getClass()));
        System.out.println("CUSTOM declaring is Flavor = "
                + (selected.getDeclaringClass() == Flavor.class));
        System.out.println("CUSTOM declaring constants = "
                + names(selected.getDeclaringClass()));
        System.out.println("CUSTOM name = " + selected.name());
        System.out.println("CUSTOM display = " + selected);

        System.out.println("Required Stage count = "
                + requireEnumConstants(Stage.class).length);
        System.out.println("Required Empty count = "
                + requireEnumConstants(Empty.class).length);
        try {
            requireEnumConstants(String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("Required String = " + ex.getClass().getSimpleName());
        }
        try {
            Enum.valueOf(Stage.class, "MISSING");
        } catch (IllegalArgumentException ex) {
            System.out.println("Missing name = " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 EnumConstantsDemo.java
java EnumConstantsDemo
```

Kết quả:

```text
Stage constants = [REVIEW, DRAFT, PUBLISHED]
Stage values = [REVIEW, DRAFT, PUBLISHED]
REVIEW ordinal = 0
DRAFT ordinal = 1
PUBLISHED ordinal = 2
Sorted by name = [DRAFT, PUBLISHED, REVIEW]
Declaration order = [REVIEW, DRAFT, PUBLISHED]
Empty is enum = true
Empty constants = []
Empty count = 0
String constants = null
Enum constants = null
Array constants = null
int constants = null
CUSTOM instanceof Enum = true
BASIC runtime is enum = true
CUSTOM runtime is enum = false
CUSTOM runtime constants = null
CUSTOM declaring is Flavor = true
CUSTOM declaring constants = [BASIC, CUSTOM]
CUSTOM name = CUSTOM
CUSTOM display = Custom label
Required Stage count = 3
Required Empty count = 0
Required String = IllegalArgumentException
Missing name = IllegalArgumentException
```

`names()` dùng `name()` để in tên hằng, tránh nhầm với nhãn `toString()` đã được ghi đè. Phép ép về `Enum<?>` chỉ thực hiện sau khi `getEnumConstants()` đã cho mảng không `null`; các phần tử lúc đó là các hằng enum.

## 4. Đọc kết quả và áp dụng đúng

### Bảo toàn hoặc thay đổi thứ tự một cách có chủ đích

`Stage constants` và `Stage values` cùng in `[REVIEW, DRAFT, PUBLISHED]`. Chương trình sau đó lấy mảng vào biến `sorted` và sắp xếp theo `Stage::name`, tạo `[DRAFT, PUBLISHED, REVIEW]`.

Lần đọc lại bằng `getEnumConstants()` vẫn cho thứ tự khai báo ban đầu. Việc sắp xếp mảng cục bộ không đổi khai báo enum, không thay hằng `REVIEW` thành một hằng khác và không đổi `ordinal()` của nó.

Nếu thứ tự khai báo đã là thứ tự mong muốn của biểu mẫu, hãy duyệt trực tiếp kết quả. Nếu giao diện cần một thứ tự khác, biểu diễn quy tắc đó rõ ràng bằng bộ so sánh hoặc thuộc tính thứ tự riêng.

Không dùng thứ tự của `getDeclaredFields()` để thay cho hợp đồng thứ tự của enum. Mảng trường dữ liệu có mục đích mô tả thành viên, còn bài toán ở đây cần danh sách **giá trị hằng enum**.

### Enum rỗng là đầu vào hợp lệ

`Empty.class.isEnum()` cho `true`, còn `Empty.class.getEnumConstants()` cho `[]` với độ dài `0`. Enum không bắt buộc phải có ít nhất một hằng; cú pháp thân enum cho phép không có danh sách hằng.

Với một công cụ chọn giá trị, kết quả này có thể có nghĩa là không có lựa chọn nào để hiển thị. Nó không có nghĩa kiểu đầu vào sai. Đây là lý do không nên gộp `null` với mảng rỗng ngay từ đầu.

### Tại sao `Enum.class`, kiểu mảng và kiểu nguyên thủy cho `null`?

Trong thí nghiệm, `String.class`, `Enum.class`, `Stage[].class` và `int.class` đều cho `null`.

- `String` là một lớp thông thường.
- `Enum` là lớp cơ sở chung, không phải một khai báo `enum` chứa tập hằng riêng.
- `Stage[]` là kiểu mảng, dù kiểu phần tử của nó là enum.
- `int` là kiểu nguyên thủy.

Nếu đang xử lý kiểu mảng và thực sự muốn tìm hằng của kiểu phần tử, cần xác định kiểu phần tử rồi kiểm tra nó. Không nên xem mọi kiểu chứa enum như chính enum.

## 5. Lớp riêng của hằng không phải khai báo enum

Trong thí nghiệm, `Flavor.CUSTOM` có thân lớp riêng ghi đè `toString()` nên `selected.getClass()` là một lớp con ẩn danh. Vì vậy, `selected.getClass().isEnum()` là `false`, và `getEnumConstants()` trên lớp con đó trả `null`. Trái lại, `selected.getDeclaringClass() == Flavor.class`, và gọi `getEnumConstants()` trên `Flavor.class` trả cả `BASIC` lẫn `CUSTOM`.

Khi cầm một hằng `Enum<?>`, dùng `getDeclaringClass()` để tìm tập hằng cùng kiểu. Trường hợp này củng cố việc **`null` phụ thuộc Class đang được hỏi**, không đồng nghĩa một hằng có thân riêng đã biến mất khỏi enum. Bài về `getClass` và `getDeclaringClass` phân tích chi tiết cơ chế lớp con ẩn danh và cách chuẩn hóa khóa kiểu.

## 6. Xử lý `null` theo hợp đồng của công cụ

Hai cách xử lý sau phục vụ hai nhu cầu khác nhau.

**Công cụ khám phá nhiều loại kiểu:** `names()` chấp nhận `Class<?>` bất kỳ. Nó kiểm tra `constants == null` và báo rằng kiểu không phải khai báo enum; mảng rỗng vẫn được trình bày thành `[]`.

**Công cụ chỉ chấp nhận enum:** `requireEnumConstants()` trong ví dụ từ chối kiểu khác bằng `IllegalArgumentException`. Tên hàm và lỗi thể hiện rõ điều kiện sử dụng. `Empty.class` vẫn được chấp nhận và trả số hằng bằng `0`.

Không tự chuyển mọi kết quả `null` thành mảng rỗng nếu chương trình cần phân biệt đầu vào sai với enum hợp lệ không có hằng. Nếu cố ý chuẩn hóa chúng, hãy ghi rõ quyết định đó trong hợp đồng của chính công cụ.

Cũng cần phân biệt **phương thức trả `null`** với **biến nhận lời gọi là `null`**. Nếu biến `Class<?> type` là `null`, biểu thức `type.getEnumConstants()` ném `NullPointerException` ngay khi gọi; nó không trả một kết quả để bạn kiểm tra. Vì thế hàm mẫu dùng `Objects.requireNonNull(type, "type")` cho đầu vào.

### Không nhầm với tra cứu một tên hằng

`getEnumConstants()` liệt kê tập hằng; `Enum.valueOf(Stage.class, "MISSING")` tìm một tên cụ thể. Lời gọi thứ hai trong thí nghiệm ném `IllegalArgumentException` vì không có tên đó, không trả `null`.

Tên được tra cứu phải khớp chính xác, kể cả hoa thường và không có khoảng trắng thừa. Đó là hợp đồng riêng của [API `Enum.valueOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)), không được suy ra từ cách `getEnumConstants()` xử lý kiểu không phải enum.

## 7. Lưu ý về tên, số thứ tự và khả năng bảo trì

`ordinal()` mô tả vị trí khai báo tại phiên bản hiện tại. Nếu thêm một hằng ở đầu hoặc đổi vị trí, số thứ tự của các hằng phía sau thay đổi. Vì vậy, dùng nó làm mã lưu trữ lâu dài có thể khiến cùng một số được hiểu thành giá trị khác sau khi cập nhật chương trình.

Ví dụ, với `[REVIEW, DRAFT, PUBLISHED]`, số `0` trỏ đến `REVIEW`. Nếu sau này chuyển `DRAFT` lên đầu, số `0` lại trỏ đến `DRAFT`. Khi cần mã nghiệp vụ ổn định, hãy thiết kế mã riêng và quy tắc tra cứu tương ứng.

`name()` giữ tên khai báo, còn `toString()` trong thí nghiệm biến `CUSTOM` thành `Custom label`. Sự thay đổi nhãn này không đổi tên hằng, vị trí khai báo hay lớp enum sở hữu nó. Công cụ nên chọn rõ đang cần tên kỹ thuật hay nội dung hiển thị.

## 8. Lỗi thường gặp và bài tự kiểm tra

| Lỗi | Cách tránh |
| --- | --- |
| Dùng ngay `.length` mà chưa kiểm tra `null` | Phân loại kết quả trước khi duyệt |
| Xem enum rỗng là kiểu không phải enum | Phân biệt `[]` với `null` |
| Giả định thứ tự là bảng chữ cái | Dựa vào thứ tự khai báo hoặc sắp xếp tường minh |
| Kiểm tra enum chỉ bằng việc đối tượng kế thừa `Enum` | Khi cần tập hằng, xác định đúng lớp khai báo enum |
| Dùng `constant.getClass()` cho mọi hằng | Với một hằng enum, dùng `getDeclaringClass()` để tìm enum sở hữu |
| Xem `toString()` như tên hằng luôn cố định | Dùng `name()` khi cần đúng tên khai báo |
| Lưu `ordinal()` như một mã nghiệp vụ ổn định | Dùng mã riêng khi cần tính ổn định qua thay đổi |
| Nghĩ tên không có trong `valueOf` sẽ trả `null` | Xử lý `IllegalArgumentException` theo hợp đồng tra cứu |

Hãy thử các thay đổi sau và dự đoán trước khi chạy:

1. Đưa `PUBLISHED` lên đầu `Stage`: kết quả liệt kê và `ordinal()` thay đổi thế nào?
2. Thêm một hằng vào `Empty`: sự khác biệt giữa mảng rỗng và `null` còn được xác định bằng điều gì?
3. Bỏ phần thân riêng của `CUSTOM`: vì sao kết quả từ `getClass()` có thể thay đổi?
4. Đổi nhãn `Custom label`: `name()`, `getDeclaringClass()` và thứ tự hằng có đổi không?

Sau bài này, bạn cần tự xác định được: đang nhận một kiểu hay một giá trị enum, kiểu đó có phải chính khai báo enum không, và công cụ của mình muốn bảo toàn thứ tự khai báo hay tạo thứ tự khác.
