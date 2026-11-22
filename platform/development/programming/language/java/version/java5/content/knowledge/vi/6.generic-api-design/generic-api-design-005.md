# Truyền Class<T> để kiểm tra kiểu lúc chạy

## 1. Bài toán: đã có T ở mã nguồn nhưng cần kiểm tra một Object

Một phương thức generic có thể liên kết kiểu đầu vào và đầu ra bằng `T`. Tuy nhiên, `T` không tự trở thành một biến kiểu có thể hỏi ở runtime.

Ví dụ, ý tưởng sau không biên dịch:

```java
static <T> Class<T> typeOfT() {
    return T.class; // Khong bien dich: khong lay class literal cua bien kieu
}
```

Đây là đoạn cố ý không biên dịch để chỉ ra giới hạn của biến kiểu.

Nếu phương thức nhận một `Object` từ vùng dữ liệu chưa biết kiểu và cần kiểm tra “đây có phải một chuỗi không?”, nó cần thêm thông tin runtime. Một cách trực tiếp là bên gọi truyền **đối tượng mô tả lớp (class token)** như `String.class`.

Chữ ký:

```java
static <T> T read(Class<T> expected, Object value) {
    return expected.cast(value);
}
```

liên kết hai điều:

- `expected` cho runtime biết lớp hoặc interface cần kiểm tra.
- `Class<T>` cho trình biên dịch biết kết quả có quan hệ với kiểu `T` nào.

Cơ chế này vẫn dùng trong Java hiện nay. Các ví dụ hoàn chỉnh bên dưới chạy với JDK 17 trở lên và không cần ép kiểu unchecked.

## 2. Class<T> là gì?

`Class<T>` là kiểu của đối tượng mô tả một kiểu runtime. Ví dụ:

```java
Class<String> textType = String.class;
Class<Integer> integerType = Integer.class;
Class<Number> numberType = Number.class;
Class<CharSequence> sequenceType = CharSequence.class;
Class<String[]> arrayType = String[].class;
```

Đây là các khai báo minh họa có thể đặt trong một phương thức.

`String.class` không phải một chuỗi. Nó là một đối tượng `Class` mô tả lớp `String`. Ta truyền nó vào phương thức giống như truyền một dữ liệu mô tả kiểu.

`Class` không chỉ đại diện cho lớp thông thường. Nó còn có thể mô tả interface, kiểu mảng và các kiểu nguyên thủy. Ý nghĩa của tham số `T` được nêu trong [API Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html).

### Class<T> và Class<?> có vai trò khác nhau

- `Class<T>` giữ một mối liên hệ có tên với `T`, hữu ích khi kết quả cần có kiểu `T`.
- `Class<?>` phù hợp khi chỉ cần mô tả một kiểu chưa biết để ghi log, so sánh hoặc kiểm tra một điều kiện.
- `Class<? extends Number>` mô tả một token cho `Number` hoặc một kiểu con của `Number`.

Ví dụ:

```java
Class<?> unknownType = String.class;
Class<? extends Number> someNumberType = Integer.class;
// Class<Number> wrong = Integer.class; // Khong bien dich
```

`Class<Integer>` không phải `Class<Number>`. Nếu muốn một token chính xác của `Number`, dùng `Number.class`. Nếu muốn nhận token của một kiểu số bất kỳ, giới hạn wildcard thể hiện đúng yêu cầu đó.

## 3. Ba thao tác cần phân biệt

### 3.1. isInstance: kiểm tra một giá trị

```java
Object value = Integer.valueOf(42);
boolean matches = Number.class.isInstance(value);
```

Kết quả `matches` là `true` vì một `Integer` có thể được sử dụng như `Number`.

`isInstance`:

- Nhận một đối tượng.
- Trả `boolean`.
- Xét tính tương thích với lớp hoặc interface do token mô tả.
- Trả `false` với `null`.

Nó tương ứng với câu hỏi “giá trị này có phải một thể hiện phù hợp với kiểu runtime đó không?”.

Khi lớp cần kiểm tra đã biết cố định ở mã nguồn, `value instanceof String text` thường gọn hơn. `Class<T>` hữu ích khi kiểu cần kiểm tra là một tham số của API.

### 3.2. cast: kiểm tra và trả kết quả có kiểu T

```java
Object value = "hello";
String text = String.class.cast(value);
```

`cast` trả lại **cùng tham chiếu**, được nhìn dưới kiểu `T` của token. Nó không tạo bản sao và không chuyển nội dung của đối tượng.

Nếu giá trị khác `null` không tương thích, nó ném `ClassCastException`:

```java
// String text = String.class.cast(42); // ClassCastException
```

`String.class.cast(42)` không biến số `42` thành chuỗi `"42"`. Nếu muốn chuyển đổi dữ liệu, phải gọi một thao tác chuyển đổi thực sự, chẳng hạn `String.valueOf(...)` theo nhu cầu.

Bản thân `Class.cast(null)` trả `null`. Nếu API cần từ chối `null`, phải đặt chính sách đó riêng.

### 3.3. isAssignableFrom: kiểm tra quan hệ giữa hai kiểu

```java
boolean acceptsInteger =
        Number.class.isAssignableFrom(Integer.class); // true

boolean acceptsNumber =
        Integer.class.isAssignableFrom(Number.class); // false
```

Cách đọc đúng:

```text
KieuDich.isAssignableFrom(KieuNguon)
```

Hỏi: “Một tham chiếu của kiểu nguồn có thể được nhìn như kiểu đích theo quan hệ kiểu tương ứng không?”

Nó nhận **hai token kiểu**, không nhận một đối tượng dữ liệu. Thứ tự quan trọng: `Number` nhận được `Integer`, nhưng một `Number` bất kỳ có thể là `Double` nên không mặc định dùng được như `Integer`.

Với các token nguyên thủy, thao tác này không thay thế các quy tắc chuyển đổi số, đóng hộp hoặc mở hộp của biểu thức Java.

### Bảng chọn thao tác

| Cần biết điều gì? | Dùng |
| --- | --- |
| Một `Object` có phù hợp với token không? | `expected.isInstance(value)` |
| Lấy cùng giá trị dưới kiểu gắn với token, sai thì báo lỗi | `expected.cast(value)` |
| Một kiểu có thể làm nguồn cho kiểu đích không? | `target.isAssignableFrom(source)` |
| Đối tượng có đúng chính lớp đó, không nhận kiểu con? | So sánh `value.getClass() == expected` sau kiểm tra `null` |

Kiểm tra đúng lớp và kiểm tra tương thích theo kế thừa là hai yêu cầu khác nhau. Đừng thay một yêu cầu bằng yêu cầu kia chỉ vì cả hai đều có thể dùng `Class`.

## 4. Thiết kế hợp đồng: sai kiểu là lỗi hay không có kết quả?

Có ít nhất hai hợp đồng hợp lý.

### Yêu cầu bắt buộc phải đúng kiểu

```java
static <T> T requireValue(Class<T> expected, Object value)
```

Nếu dữ liệu sai kiểu, báo lỗi. Nếu `null` không được phép, từ chối nó rõ ràng.

Điều này phù hợp với một ranh giới dữ liệu nơi sai kiểu có nghĩa đầu vào vi phạm hợp đồng.

### Thử lấy giá trị nếu phù hợp

```java
static <T> Optional<T> matchingValue(Class<T> expected, Object value)
```

Nếu giá trị không phù hợp hoặc là `null`, trả `Optional.empty()`. Đừng dùng ngoại lệ như luồng xử lý thông thường khi “không khớp” là một kết quả được dự kiến.

Hai chữ ký là các mảnh API minh họa, được triển khai đầy đủ ở phần sau.

### Quyết định riêng đối với token null và primitive

Trong ví dụ của bài:

- Token `Class` không được `null`.
- Chỉ nhận token cho kiểu tham chiếu.
- Token mô tả kiểu nguyên thủy hoặc `void` bị từ chối.
- `requireValue` từ chối giá trị `null`.
- `matchingValue` coi giá trị `null` là không có kết quả.
- Danh sách đã xác thực không chứa phần tử `null`.

Những quy tắc này là lựa chọn của API ví dụ. Không được suy ra rằng mọi API dùng `Class<T>` đều tự động có cùng chính sách.

## 5. Chương trình đầy đủ: kiểm tra giá trị và danh sách

Lưu thành `RuntimeClassTokenDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class RuntimeClassTokenDemo {
    private static <T> Class<T> referenceType(Class<T> expected) {
        Objects.requireNonNull(expected, "expected");
        if (expected.isPrimitive()) {
            throw new IllegalArgumentException("reference type required");
        }
        return expected;
    }

    static <T> T requireValue(Class<T> expected, Object value) {
        Class<T> type = referenceType(expected);
        return type.cast(Objects.requireNonNull(value, "value"));
    }

    static <T> Optional<T> matchingValue(Class<T> expected, Object value) {
        Class<T> type = referenceType(expected);
        return type.isInstance(value)
                ? Optional.of(type.cast(value))
                : Optional.empty();
    }

    static <T> List<T> validatedList(Class<T> elementType, Object source) {
        referenceType(elementType);
        if (!(source instanceof List<?> values)) {
            throw new IllegalArgumentException("a list is required");
        }

        List<T> copy = new ArrayList<>();
        for (Object value : values) {
            copy.add(requireValue(elementType, value));
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        String text = requireValue(String.class, "hello");
        Number number = requireValue(Number.class, 42);
        CharSequence sequence =
                requireValue(CharSequence.class, new StringBuilder("abc"));

        System.out.println("text = " + text);
        System.out.println("number = " + number);
        System.out.println("sequence length = " + sequence.length());
        System.out.println("optional right = "
                + matchingValue(String.class, text).orElse("none"));
        System.out.println("optional wrong = "
                + matchingValue(String.class, 42).orElse("none"));
        System.out.println("optional null = "
                + matchingValue(String.class, null).orElse("none"));

        Object candidate = Integer.valueOf(42);
        System.out.println("Number <- Integer = "
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Integer <- Number = "
                + Integer.class.isAssignableFrom(Number.class));
        System.out.println("Number isInstance = "
                + Number.class.isInstance(candidate));
        System.out.println("exact Number = "
                + (candidate.getClass() == Number.class));
        System.out.println("Class.cast(null) is null = "
                + (String.class.cast(null) == null));
        System.out.println("primitive accepts boxed = "
                + int.class.isInstance(candidate));
        System.out.println("wrapper accepts boxed = "
                + Integer.class.isInstance(candidate));

        List<String> names =
                validatedList(String.class, List.of("An", "Binh"));
        System.out.println("validated names = " + names);

        String[] array = requireValue(
                String[].class, new String[] {"left", "right"});
        System.out.println("checked array = " + Arrays.toString(array));
        System.out.println("List token accepts integer list = "
                + List.class.isInstance(List.of(1, 2)));

        try {
            requireValue(String.class, 42);
        } catch (ClassCastException exception) {
            System.out.println("wrong value rejected");
        }

        try {
            validatedList(String.class, List.of("An", 42));
        } catch (ClassCastException exception) {
            System.out.println("wrong list element rejected");
        }

        try {
            requireValue(String.class, null);
        } catch (NullPointerException exception) {
            System.out.println("null value rejected");
        }

        try {
            requireValue(int.class, 42);
        } catch (IllegalArgumentException exception) {
            System.out.println("primitive token rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror RuntimeClassTokenDemo.java
java RuntimeClassTokenDemo
```

Stdout:

```text
text = hello
number = 42
sequence length = 3
optional right = hello
optional wrong = none
optional null = none
Number <- Integer = true
Integer <- Number = false
Number isInstance = true
exact Number = false
Class.cast(null) is null = true
primitive accepts boxed = false
wrapper accepts boxed = true
validated names = [An, Binh]
checked array = [left, right]
List token accepts integer list = true
wrong value rejected
wrong list element rejected
null value rejected
primitive token rejected
```

### 5.1. Vì sao kết quả có kiểu đúng mà không cần (T)?

Trong `requireValue`:

```java
Class<T> type = referenceType(expected);
return type.cast(Objects.requireNonNull(value, "value"));
```

`Class.cast` vốn có kiểu trả về `T`. Tham số kiểu của token và kiểu trả về của phương thức được liên kết qua cùng `T`.

Khi gọi:

```java
String text = requireValue(String.class, someObject);
```

token `String.class` thiết lập quan hệ với `String`. Nếu dữ liệu runtime phù hợp, kết quả dùng được như `String`.

Ngược lại:

```java
// String wrong = requireValue(Integer.class, 7); // Khong bien dich
```

không thể coi kết quả gắn với `Integer.class` là `String`. Đây là phần bảo vệ của hệ kiểu ở thời điểm biên dịch, bổ sung cho phép kiểm tra lúc chạy.

`someObject` trong đoạn trên là biến minh họa cho một `Object` đã có; chương trình đầy đủ sử dụng các đối số cụ thể.

### 5.2. Kiểu cha và interface đều có thể là token kiểm tra

`Number.class` chấp nhận đối tượng `Integer`. `CharSequence.class` chấp nhận `StringBuilder`.

Điều đó khác với:

```java
candidate.getClass() == Number.class
```

Trong chương trình, `candidate` thực tế là `Integer`, nên điều kiện đúng lớp `Number` là `false` nhưng `Number.class.isInstance(candidate)` là `true`.

Nếu nghiệp vụ cho phép kiểu con, dùng quan hệ tương thích. Nếu nghiệp vụ thật sự yêu cầu chính xác một lớp cụ thể, hãy công bố yêu cầu đó rồi mới kiểm tra đúng lớp.

### 5.3. isInstance và cast dùng cùng một mức thông tin

`matchingValue` gọi `isInstance` trước và `cast` sau. Cả hai cùng dựa trên token nên khi token mô tả kiểu tham chiếu và giá trị khớp, phép `cast` không phải một sự suy đoán mới.

Đối tượng không tự đổi lớp giữa hai lời gọi. Với một container có thể bị thay đổi nội dung, việc lớp ngoài khớp không đồng nghĩa nội dung được giữ nguyên; đó là một vấn đề khác phải kiểm soát khi xác thực dữ liệu bên trong.

### 5.4. requireValue và matchingValue có chính sách null khác nhau

Chương trình cho thấy:

- `String.class.cast(null)` tự nó trả `null`.
- `requireValue(String.class, null)` bị `Objects.requireNonNull` từ chối.
- `matchingValue(String.class, null)` trả `Optional.empty()` vì `isInstance(null)` là `false`.

Không phải `Class.cast` tự áp dụng chính sách cấm `null`. Chính phương thức bao ngoài đã chọn điều đó.

## 6. Primitive token khác wrapper token

Một điểm dễ nhầm:

```java
Class<Integer> primitiveToken = int.class;
Class<Integer> wrapperToken = Integer.class;
```

Cả hai khai báo đều được phép ở hệ generic, nhưng hai token mô tả **hai kiểu runtime khác nhau**: `int` và `Integer`.

Một giá trị đi qua tham số `Object` không còn là một giá trị nguyên thủy trực tiếp; nếu truyền `42`, nó được đóng hộp thành `Integer`.

Vì vậy:

```java
Integer.class.isInstance(42); // true
int.class.isInstance(42);     // false
```

`int.class.cast(42)` không phải thao tác mở hộp. Nó không chuyển một đối tượng wrapper thành một “đối tượng int”, vì kiểu nguyên thủy không có thể hiện đối tượng như vậy.

Helper `referenceType` trong chương trình từ chối token primitive để API kiểm tra đối tượng có hợp đồng nhất quán. `Class.isPrimitive()` cũng nhận diện token `void`, nên token đó bị từ chối cùng nhóm.

Nếu một API cần làm việc với cả giá trị nguyên thủy và wrapper, phải định nghĩa riêng cách chuẩn hóa token và chuyển đổi dữ liệu. Không mặc định rằng các phương thức kiểm tra lớp áp dụng mọi quy tắc chuyển đổi của biểu thức số trong Java.

## 7. Giới hạn quan trọng: Class<T> không mô tả đầy đủ List<String>

Không thể viết:

```java
// Class<List<String>> type = List<String>.class; // Cu phap khong hop le
```

Class literal không nhận một kiểu có đối số như `List<String>`. Quy tắc được định nghĩa ở [JLS: Class Literals](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.8.2).

`List.class` mô tả lớp/interface ngoài `List`, không mang một đối số `String` riêng để runtime kiểm tra phần tử.

Chương trình in:

```text
List token accepts integer list = true
```

vì danh sách số nguyên vẫn là một `List`. Điều này không xác thực nó như `List<String>`.

### Cách xác thực một danh sách phần tử đơn giản

`validatedList(String.class, source)` thực hiện các bước:

1. Xác nhận token phần tử phù hợp hợp đồng.
2. Kiểm tra cấu trúc ngoài bằng `source instanceof List<?>`.
3. Duyệt từng giá trị bên trong.
4. Dùng `String.class.cast` cho từng phần tử khác `null`.
5. Tạo danh sách mới có kiểu `List<String>` và không cho sửa cấu trúc.

Mỗi phần tử được kiểm tra bằng token có khả năng mô tả chính kiểu của nó. Không có một phép ép unchecked cho cả danh sách.

Nếu một phần tử sai, ví dụ ném `ClassCastException`. Nếu không phải danh sách, phương thức ném `IllegalArgumentException`. Phần tử `null` bị từ chối theo chính sách chung.

### Dữ liệu lồng nhau cần một mô hình kiểm tra mạnh hơn

Đối với `List<List<String>>`, một `Class<?>` cho kiểu ngoài không thể tự chứng minh toàn bộ cấu trúc và kiểu phần tử ở mọi tầng.

Có thể cần:

- Thuật toán duyệt và xác thực từng tầng.
- Một đối tượng mô tả kiểu phong phú hơn.
- Một bộ giải mã có thông tin kiểu và quy tắc dữ liệu tương ứng.

Một đối tượng `Type` từ reflection có thể mô tả thông tin generic ở khai báo, nhưng việc có mô tả không tự kiểm tra nội dung của một đối tượng. Vẫn cần thuật toán diễn giải và xác thực phù hợp.

### Kiểm tra xong rồi phải giữ hợp đồng

Nếu chỉ duyệt danh sách nguồn rồi trả lại chính nguồn bằng phép ép unchecked, một alias khác có thể tiếp tục chèn phần tử không phù hợp.

Ví dụ tạo bản sao mới trước khi trả kết quả để tách cấu trúc khỏi thay đổi về sau của nguồn. Nó không sao chép sâu đối tượng phần tử và không tự hỗ trợ nguồn bị sửa đồng thời trong lúc duyệt.

## 8. Kiểu mảng là một trường hợp kiểm tra được trực tiếp

`String[].class` là token hợp lệ:

```java
String[] values = requireValue(
        String[].class,
        new String[] {"left", "right"});
```

Runtime biết đối tượng đó là mảng của `String`. Token không chỉ nói “đây là một `Object` chứa vài chuỗi”.

Ngược lại, một `Object[]` đang chứa các phần tử đều là chuỗi vẫn có lớp runtime là `Object[]`. `String[].class.cast(...)` không đổi nó thành `String[]`.

Nếu cần chuyển dữ liệu từ một tập hợp hoặc mảng rộng sang mảng hẹp hơn, phải tạo mảng đích đúng kiểu và kiểm tra hoặc sao chép từng phần tử qua một API thích hợp.

`Class<T>` giúp kiểm tra một kiểu mảng có thể được biểu diễn lúc chạy; nó không tạo một lớp runtime riêng cho `List<String>[]`.

## 9. Class<?> chỉ để kiểm tra thì không cần ép thành Class<T>

Nếu một hàm chỉ trả `boolean`, có thể dùng:

```java
static boolean matches(Class<?> expected, Object value) {
    return expected.isInstance(value);
}
```

Đây là phương thức minh họa, giả định token khác `null`. Nó không cần biết một `T` có tên vì không trả lại giá trị có kiểu gắn với token.

Ngược lại, nếu API hứa trả về `T`, giữ `Class<T>` trong chữ ký giúp trình biên dịch kiểm tra quan hệ giữa token và kết quả. Không nhận một `Class<?>` rồi ép tùy tiện thành `Class<T>` chỉ để làm compiler im lặng.

Cũng không nên ép `Integer.class` thành `Class<String>` qua kiểu rộng. Làm sai token phá bằng chứng mà toàn bộ API đang dựa vào. `Class.cast` an toàn khi mối quan hệ của token không bị người gọi làm sai bằng những thao tác unchecked.

## 10. Những điều token không tự bảo đảm

### Không chuyển đổi dữ liệu

Token `Integer.class` không phân tích chuỗi `"123"` thành số. Token `String.class` không định dạng một số thành văn bản.

### Không kiểm tra quy tắc nghiệp vụ

Một giá trị `Integer` âm vẫn đúng kiểu `Integer`. Nếu yêu cầu tuổi không âm hoặc mã nằm trong một phạm vi, phải kiểm tra điều kiện đó sau kiểm tra kiểu.

### Không cần đối tượng có constructor công khai

Kiểm tra `isInstance` hoặc `cast` chỉ kiểm tra một đối tượng đã tồn tại. Nó không đòi constructor không đối số và không tạo một thể hiện mới. Đừng ghép cơ chế kiểm tra kiểu với việc tự động khởi tạo nếu API không có yêu cầu đó.

### Không xác thực sâu đối tượng bất kỳ

`User.class.cast(value)` chứng minh giá trị phù hợp với kiểu `User` ở mức runtime, không chứng minh mọi trường dữ liệu bên trong đáp ứng quy tắc miền.

### Không thay thế instanceof khi kiểu đã cố định

Với một kiểm tra cục bộ duy nhất đã biết là chuỗi, `value instanceof String text` có thể dễ đọc hơn. Dùng `Class<T>` khi API cần nhận kiểu kiểm tra như dữ liệu và giữ quan hệ kiểu cho người gọi.

## 11. Lỗi thường gặp và cách chọn đúng

| Lỗi | Vấn đề | Cách nghĩ phù hợp |
| --- | --- | --- |
| Gọi `T.class` trong phương thức generic | Không có class literal cho biến kiểu | Nhận `Class<T>` từ bên gọi |
| Viết `value instanceof T` | Không thể kiểm tra một biến kiểu như lớp cụ thể | Dùng token mô tả kiểu có thể kiểm tra |
| Đảo chiều `isAssignableFrom` | Trả kết quả trái với khả năng gán dự kiến | Đặt kiểu đích bên trái |
| Dùng `getClass() == expected` khi muốn nhận kiểu con | Từ chối các đối tượng tương thích | Dùng `isInstance` |
| Tưởng `cast` chuyển số thành chuỗi | Phép kiểm tra ép kiểu không chuyển dữ liệu | Dùng hàm chuyển đổi |
| Tưởng `cast(null)` tự báo lỗi | Bản thân phép cast chấp nhận `null` | Công bố và kiểm tra chính sách riêng |
| Dùng `List.class` để xác thực `List<String>` | Chỉ kiểm tra được cấu trúc ngoài | Duyệt phần tử hoặc dùng bộ xác thực có cấu trúc |
| Ép `Class<?>` thành `Class<T>` tùy ý | Làm mất bằng chứng token-kết quả | Giữ quan hệ kiểu từ chữ ký API |

## 12. Thực hành tự kiểm tra

### Bài 1: Token và kết quả

Có thể viết `String text = requireValue(Integer.class, 7)` không?

**Đáp án:** không. Kiểu kết quả được liên kết với token `Integer.class`, không phù hợp với `String`.

### Bài 2: Chấp nhận kiểu con

Với `Object value = Integer.valueOf(5)`, hai biểu thức `Number.class.isInstance(value)` và `value.getClass() == Number.class` có cùng kết quả không?

**Đáp án:** không. Biểu thức thứ nhất là `true` vì số nguyên là một `Number`; biểu thức thứ hai là `false` vì lớp thực là `Integer`.

### Bài 3: Thứ tự isAssignableFrom

Muốn hỏi “một Integer có thể được dùng như Number không?”, viết token nào bên trái?

**Đáp án:** `Number.class.isAssignableFrom(Integer.class)`. Kiểu đích đứng bên trái.

### Bài 4: Danh sách số nguyên

`List.class.isInstance(List.of(1, 2))` trả `true`. Có thể kết luận đó là `List<String>` không?

**Đáp án:** không. Token chỉ kiểm tra được kiểu ngoài `List`. Muốn có danh sách chuỗi đã xác thực, cần kiểm tra từng phần tử và giữ hợp đồng sau khi kiểm tra.

### Bài 5: Primitive

Vì sao `int.class.isInstance(42)` là `false`?

**Đáp án:** đối số qua `Object` được đóng hộp thành `Integer`, còn token mô tả kiểu nguyên thủy `int`. `isInstance` không thực hiện mở hộp để biến nó thành thể hiện của primitive.

Một token `Class<T>` tạo cầu nối có giới hạn giữa hệ kiểu ở mã nguồn và kiểm tra kiểu runtime: nó vừa mang kiểu kiểm tra, vừa liên kết kết quả với `T`. Thiết kế đúng cần giữ nguyên bằng chứng đó và công bố rõ những phần token chưa thể kiểm tra.
