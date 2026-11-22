# Tra cứu hằng bằng values() và valueOf()

## 1. Hai nhu cầu khác nhau: liệt kê và tìm theo tên

Với enum:

```java
enum TaskState {
    NEW,
    IN_PROGRESS,
    DONE
}
```

Java cung cấp ngầm định hai phương thức static trên chính kiểu `TaskState`:

```java
public static TaskState[] values()
public static TaskState valueOf(String name)
```

Đây là các chữ ký để giải thích API, không phải mã khai báo lại trong enum.

| Phương thức | Câu hỏi được trả lời | Kết quả |
| --- | --- | --- |
| `TaskState.values()` | Kiểu này có những hằng nào? | Mảng chứa các hằng theo thứ tự khai báo |
| `TaskState.valueOf(name)` | Tên khai báo này ứng với hằng nào? | Một hằng đã tồn tại, hoặc ngoại lệ nếu đầu vào không hợp lệ |

`valueOf` không tạo hằng mới. `values` không cho sửa tập hằng của enum. Cả hai giúp truy cập tập giá trị đã được định nghĩa trong kiểu.

Các cơ chế này vẫn áp dụng trên Java hiện đại. Ví dụ chạy độc lập bên dưới dùng Java 17+.

## 2. values(): liệt kê theo thứ tự khai báo

### 2.1. Mảng có kiểu phần tử cụ thể

```java
TaskState[] states = TaskState.values();
```

Không cần cast từ `Object[]`. Với enum khác, kiểu mảng tương ứng cũng khác.

Thứ tự là:

```text
NEW
IN_PROGRESS
DONE
```

theo thứ tự đã viết trong khai báo. Đây không phải thứ tự chữ cái, nhãn hiển thị hay thứ tự lấy từ cơ sở dữ liệu.

Ví dụ duyệt:

```java
for (TaskState state : TaskState.values()) {
    System.out.println(state.name());
}
```

Vòng lặp hữu ích khi cần sinh danh sách lựa chọn, kiểm tra mọi hằng hoặc tạo một cấu trúc ánh xạ dựa trên tập giá trị.

### 2.2. Mảng trả về không phải nơi định nghĩa enum

```java
TaskState[] states = TaskState.values();
states[0] = TaskState.DONE;

System.out.println(TaskState.values()[0]); // NEW
```

Thay đổi mảng nhận được không đổi định nghĩa hằng và không làm lần gọi `values()` tiếp theo mất `NEW`.

Cần tách hai lớp dữ liệu:

- Mảng chứa các tham chiếu tới hằng.
- Những đối tượng hằng enum đã tồn tại.

Mảng của từng lần gọi có thể được xử lý như dữ liệu riêng. Các phần tử vẫn tham chiếu tới những hằng dùng chung; nếu enum có trường mutable, việc sửa trường đó là một vấn đề khác với sửa mảng.

### 2.3. Thứ tự khai báo không phải mã định danh ổn định

Có thể đọc `values()[0]`, nhưng đó là truy cập theo vị trí. Nếu thêm hoặc sắp xếp lại hằng, vị trí có thể thay đổi.

Không dùng:

```java
TaskState state = TaskState.values()[externalNumber];
```

như một quy tắc chuyển mã nghiệp vụ nếu `externalNumber` cần ổn định qua các phiên bản. Chỉ số ngoài mảng còn có thể gây `ArrayIndexOutOfBoundsException`.

Nếu bên ngoài dùng mã số hoặc mã chuỗi riêng, cần định nghĩa trường mã và hàm tra cứu theo mã đó.

## 3. valueOf(): tên phải khớp chính xác

### 3.1. Đầu vào là tên hằng, không phải nhãn

```java
TaskState state = TaskState.valueOf("IN_PROGRESS");
System.out.println(state == TaskState.IN_PROGRESS); // true
```

Phương thức trả đúng đối tượng hằng đã tồn tại. Nó không dựng một đối tượng mới chứa tên `"IN_PROGRESS"`.

Chuỗi được đối chiếu với tên khai báo của hằng, tương ứng với `name()`.

### 3.2. Phân biệt chữ hoa–thường và giữ nguyên khoảng trắng

| Đầu vào | Kết quả với enum trên |
| --- | --- |
| `"NEW"` | `TaskState.NEW` |
| `"IN_PROGRESS"` | `TaskState.IN_PROGRESS` |
| `"in_progress"` | `IllegalArgumentException` |
| `" IN_PROGRESS "` | `IllegalArgumentException` |
| `""` | `IllegalArgumentException` |
| `"CANCELLED"` | `IllegalArgumentException` |
| `null` | `NullPointerException` |

`valueOf` không tự cắt khoảng trắng, không tự đổi chữ hoa và không trả `null` khi không tìm thấy.

Nếu đầu vào được tạo trong mã nguồn và đã biết là tên hợp lệ, dùng trực tiếp `valueOf` có thể phù hợp. Nếu đầu vào do người dùng hoặc hệ thống bên ngoài gửi, cần quyết định cách báo lỗi hoặc chuẩn hóa trước khi tra cứu.

### 3.3. Ghi đè toString() không thay đổi valueOf()

Một enum có thể dùng `toString()` để biểu diễn thân thiện, hoặc có trường `label` như `"Đang xử lý"`. Những chuỗi đó không tự trở thành tên được `valueOf` chấp nhận.

Quan hệ cần nhớ:

```text
name()      → tên chính xác trong khai báo
toString()  → biểu diễn chuỗi, có thể được ghi đè
code/label  → dữ liệu do người viết thiết kế
valueOf()   → tìm theo name, không theo mọi biểu diễn khác
```

Nếu dùng `valueOf` để đọc dữ liệu đã lưu bằng tên, đổi tên hằng có thể phá vỡ khả năng đọc dữ liệu cũ. Khi định dạng bên ngoài cần mã ổn định độc lập với tên Java, hãy thiết kế mã riêng và quy tắc tương thích tương ứng.

## 4. Hai dạng valueOf và cách dùng trong mã tổng quát

### 4.1. Khi biết cụ thể kiểu enum

```java
TaskState state = TaskState.valueOf("DONE");
```

Phương thức static này được cung cấp trên `TaskState`, với kiểu trả về chính xác là `TaskState`.

### 4.2. Khi kiểu enum được truyền bằng Class<E>

`java.lang.Enum` có một phương thức static tổng quát:

```java
static <E extends Enum<E>> E valueOf(Class<E> enumType, String name)
```

Đây là chữ ký API để giải thích, không phải phần cài đặt.

Cách gọi:

```java
TaskState state = Enum.valueOf(TaskState.class, "DONE");
```

Với utility có tham số `Class<E>`, dạng này giữ quan hệ giữa thẻ kiểu và kết quả:

```java
static <E extends Enum<E>> E parseExact(Class<E> enumType, String name) {
    return Enum.valueOf(enumType, name);
}
```

`E extends Enum<E>` ràng buộc `E` là một kiểu enum phù hợp. `Class<E>` cung cấp thông tin lớp thực thi. Không cần raw type hoặc cast không được kiểm tra.

`enumType` hoặc `name` là `null` đều không hợp lệ. `Enum.valueOf` cũng không phải nơi tự suy ra kiểu enum chỉ từ một chuỗi; nhiều enum có thể cùng có hằng `NEW`.

Không có một lời gọi `Enum.values()` chung tương đương `TaskState.values()`. Khi đã có `Class<E>` và cần liệt kê bằng API lớp, `enumType.getEnumConstants()` là một lựa chọn khác, nhưng cần giữ đúng hợp đồng về kiểu enum. Với kiểu cụ thể, `TaskState.values()` thường rõ ràng hơn.

## 5. Thiết kế một lớp xử lý đầu vào

### 5.1. Giữ chế độ chính xác khi hợp đồng yêu cầu chính xác

Nếu một giao thức quy định tên hằng viết hoa và không có khoảng trắng thừa, đầu vào sai nên được báo là sai. Chuẩn hóa tự động có thể che lỗi từ hệ thống gửi.

Một API nghiêm ngặt có thể gọi trực tiếp `TaskState.valueOf(raw)` rồi chuyển lỗi sang cách báo lỗi phù hợp với giao thức.

### 5.2. Chỉ chuẩn hóa khi đó là một phần hợp đồng

Với ô nhập liệu thân thiện, có thể chọn:

1. `null` hoặc chuỗi trống sau khi bỏ khoảng trắng → không có kết quả.
2. Bỏ khoảng trắng ở hai đầu bằng `strip()`.
3. Đổi sang chữ hoa bằng `toUpperCase(Locale.ROOT)`.
4. Gọi `Enum.valueOf`.
5. Tên không tồn tại → `Optional.empty()`.

`Locale.ROOT` giúp việc đổi hoa–thường của định danh kỹ thuật không phụ thuộc locale mặc định của máy, chẳng hạn khác biệt chữ cái ở một số ngôn ngữ.

Đây là quy tắc do API thêm vào, không phải hành vi mặc định của `valueOf`. Mẫu này phù hợp với quy ước tên hằng chữ hoa như enum trong bài; nó không phải bộ chuẩn hóa đúng cho mọi enum có quy tắc đặt tên khác.

Nếu cần phân biệt “thiếu dữ liệu”, “rỗng” và “không nhận diện được”, chỉ một `Optional.empty()` chưa đủ thông tin. Khi đó dùng một mô hình lỗi hoặc kết quả chi tiết phù hợp.

### 5.3. Bắt đúng ngoại lệ

Sau khi xử lý `null` tường minh, một wrapper có thể bắt riêng `IllegalArgumentException` do tên không hợp lệ. Không nên bắt `Exception` hoặc `Throwable` rồi coi mọi lỗi là “không tìm thấy”.

Các lỗi cấu hình hoặc lỗi lập trình khác cần còn khả năng được phát hiện đúng ngữ cảnh.

## 6. Chương trình hoàn chỉnh

Lưu thành `EnumLookupDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;

public class EnumLookupDemo {
    public enum TaskState {
        NEW,
        IN_PROGRESS,
        DONE
    }

    static <E extends Enum<E>> Optional<E> parseNormalized(
            Class<E> enumType, String raw) {
        Objects.requireNonNull(enumType, "enumType");

        if (raw == null) {
            return Optional.empty();
        }

        String name = raw.strip().toUpperCase(Locale.ROOT);
        if (name.isEmpty()) {
            return Optional.empty();
        }

        try {
            return Optional.of(Enum.valueOf(enumType, name));
        } catch (IllegalArgumentException failure) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println("all = " + Arrays.toString(TaskState.values()));

        TaskState[] local = TaskState.values();
        local[0] = TaskState.DONE;
        System.out.println("after array change = "
                + Arrays.toString(TaskState.values()));

        TaskState exact = TaskState.valueOf("IN_PROGRESS");
        System.out.println("exact = " + exact.name());
        System.out.println("same constant = "
                + (exact == TaskState.IN_PROGRESS));

        try {
            TaskState.valueOf("in_progress");
        } catch (IllegalArgumentException failure) {
            System.out.println("lowercase exact = rejected");
        }

        TaskState normalized = parseNormalized(
                TaskState.class, " in_progress ").orElseThrow();
        System.out.println("normalized = " + normalized.name());
        System.out.println("unknown = "
                + parseNormalized(TaskState.class, "cancelled").isEmpty());
        System.out.println("null input = "
                + parseNormalized(TaskState.class, null).isEmpty());
        System.out.println("blank input = "
                + parseNormalized(TaskState.class, "   ").isEmpty());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EnumLookupDemo.java
java EnumLookupDemo
```

Stdout chính xác:

```text
all = [NEW, IN_PROGRESS, DONE]
after array change = [NEW, IN_PROGRESS, DONE]
exact = IN_PROGRESS
same constant = true
lowercase exact = rejected
normalized = IN_PROGRESS
unknown = true
null input = true
blank input = true
```

Ví dụ tách rõ hai hợp đồng:

- `TaskState.valueOf` giữ nguyên quy tắc tên chính xác của Java.
- `parseNormalized` thêm một chính sách đầu vào được công bố, rồi sử dụng `Enum.valueOf` để tra cứu.

Việc sửa mảng cục bộ không sửa tập hằng. Việc phân tích thành công trả lại hằng hiện có, nên so sánh với `TaskState.IN_PROGRESS` bằng `==` cho kết quả `true`.

## 7. Tra cứu theo thuộc tính riêng: dùng values() với quy tắc rõ ràng

Nếu enum có mã ngoài khác tên khai báo:

```java
enum ResultKind {
    SUCCESS("ok"),
    FAILURE("error");

    private final String code;

    ResultKind(String code) {
        this.code = code;
    }

    static Optional<ResultKind> fromCode(String code) {
        Objects.requireNonNull(code, "code");
        for (ResultKind kind : values()) {
            if (kind.code.equals(code)) {
                return Optional.of(kind);
            }
        }
        return Optional.empty();
    }
}
```

Đây là một lớp enum minh họa riêng, cần import `Objects` và `Optional`.

`ResultKind.valueOf("SUCCESS")` hợp lệ. `ResultKind.valueOf("ok")` không hợp lệ. `ResultKind.fromCode("ok")` theo phương thức tự viết thì trả `SUCCESS`.

Vòng lặp trên `values()` cho phép áp dụng một tiêu chí ngoài tên, nhưng phải quyết định:

- Mã có phân biệt chữ hoa–thường không?
- Có cho `null` không?
- Không tìm thấy thì trả gì hoặc ném gì?
- Nếu hai hằng trùng mã, đó là lỗi khai báo hay chọn hằng đầu tiên?

Với ít hằng và tra cứu không dày đặc, một vòng lặp rõ ràng có thể đủ. Nếu cần một bảng tra cứu dùng lại, xây nó sau khi các hằng đã khởi tạo, kiểm tra mã trùng và bảo vệ map khỏi sửa ngoài ý muốn. Không đăng ký vào một trường map static chưa sẵn sàng ngay trong hàm tạo enum.

## 8. Các lưu ý về tần suất gọi và dữ liệu công bố

### 8.1. Không gọi values() lặp lại chỉ để duyệt cùng một mảng

Viết:

```java
for (TaskState state : TaskState.values()) {
    System.out.println(state);
}
```

rõ ràng hơn việc gọi `TaskState.values()` nhiều lần ở điều kiện và thân một vòng lặp theo chỉ số. Một lần lấy mảng rồi duyệt là đủ cho một lượt xử lý.

Trong cách triển khai thông thường của `javac`, `values()` trả một bản sao mảng chứa các tham chiếu hằng. Khi tối ưu đoạn gọi rất thường xuyên, có thể đo đạc rồi chọn cấu trúc lưu dùng lại phù hợp; đừng đánh đổi tính rõ ràng chỉ từ phỏng đoán.

Nếu cache một mảng nội bộ, không trả thẳng mảng mutable đó ra ngoài để người dùng thay đổi cache. Tập hằng vẫn cố định nhưng bộ dữ liệu công bố của API có thể bị hỏng.

### 8.2. Không suy diễn độ phức tạp thành một hợp đồng không có

`valueOf` là API chuẩn để tìm theo tên; không cần tự viết vòng lặp tên chỉ vì cho rằng nó “chắc phải nhanh hơn”. Chi tiết tối ưu nội bộ của JDK không phải phần cần lặp lại trong API ứng dụng.

Với tìm kiếm thuộc tính riêng, lựa chọn vòng lặp hoặc map phụ thuộc số hằng, tần suất và hợp đồng. Đo đạc khi hiệu năng thật sự quan trọng.

## 9. Những lỗi dễ gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mong `valueOf` trả `null` khi sai tên | Nhầm hợp đồng thất bại | Bắt đúng lỗi hoặc viết wrapper có hợp đồng riêng |
| Truyền nhãn hiển thị vào `valueOf` | Nhầm nhãn với `name()` | Dùng hàm tra cứu thuộc tính nếu cần |
| Truyền tên có khoảng trắng hoặc sai hoa–thường | Không có chuẩn hóa mặc định | Giữ chính xác hoặc chuẩn hóa tường minh |
| Sửa mảng `values()` để “xóa hằng” | Nhầm mảng kết quả với định nghĩa enum | Tạo danh sách lọc riêng cho nhu cầu hiển thị |
| Dùng vị trí mảng làm mã lưu ổn định | Thứ tự khai báo có thể thay đổi | Khai báo mã ngoài rõ ràng |
| Đổi tên hằng nhưng bỏ qua dữ liệu đã lưu | Tên có thể là một phần định dạng trao đổi | Thiết kế và chuyển đổi định dạng có chủ đích |
| Gọi `Enum.values()` | Không có phương thức liệt kê chung như vậy | Dùng kiểu enum cụ thể hoặc API `Class` phù hợp |
| Bắt mọi lỗi rồi trả rỗng | Che mất lỗi khác | Giới hạn vùng thử và loại ngoại lệ cần xử lý |

## 10. Cách chọn đúng thao tác

- Cần toàn bộ hằng: dùng `TaskState.values()`.
- Cần hằng theo đúng tên Java: dùng `TaskState.valueOf(name)`.
- Kiểu enum được truyền bằng `Class<E>`: dùng `Enum.valueOf(enumType, name)`.
- Đầu vào thân thiện cần chuẩn hóa: viết một lớp xử lý có quy tắc rõ ràng.
- Cần tra theo mã hoặc nhãn riêng: viết một API tra thuộc tính, không ép `valueOf` làm công việc khác.

Sự phân biệt này giữ được một định nghĩa enum rõ ràng, đồng thời làm cho quy tắc tiếp nhận dữ liệu bên ngoài dễ hiểu và kiểm chứng.

## Tài liệu đối chiếu

- [JLS §8.9.3 — Enum Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3): các phương thức `values()` và `valueOf(String)` được khai báo ngầm định.
- [Java Enum.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)): yêu cầu khớp tên và các ngoại lệ.
- [Java String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#toUpperCase(java.util.Locale)) và [Locale.ROOT](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html#ROOT): chuẩn hóa chữ hoa theo locale được chọn tường minh.
