# Tránh unchecked cast trong code pattern của Java

## 1. Vấn đề: khớp kiểu collection không đồng nghĩa khớp kiểu phần tử

Trong Java, **pattern matching for instanceof** giúp kiểm tra đối tượng và gắn biến đã được kiểm tra kiểu trong cùng một biểu thức. Với các kiểu thông thường, việc này thay thế trực tiếp mẫu **instanceof → cast**:

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return "not a String";
}
~~~

Tuy nhiên, **generics** có một giới hạn quan trọng: JVM thường không lưu đối số kiểu như **String** hay **Integer** của **List<String>**, do cơ chế **type erasure**. Một đối tượng có thể được kiểm tra là **List**, nhưng điều đó chưa chứng minh mọi phần tử của nó là **String**. Nếu tạo biến **List<String>** bằng cách ép kiểu chưa được kiểm tra, chương trình có thể biên dịch với cảnh báo và thất bại khi đọc phần tử.

Mục tiêu của bài này là thay các phép **unchecked cast** bằng phương pháp có bằng chứng về kiểu: **type pattern phù hợp, kiểm tra từng giá trị, dùng API có kiểu tĩnh và sao chép dữ liệu đã xác minh**. Các ví dụ chính chạy với **Java 17+**.

## 2. Checked cast, unchecked cast và lỗi xảy ra lúc nào?

**Cast được kiểm tra (checked cast)** là phép ép kiểu mà runtime có thể kiểm tra tương thích thực tế, chẳng hạn từ **Object** sang **String**:

~~~java
Object value = "Java";
String text = (String) value; // Runtime kiểm tra: giá trị thật sự là String
~~~

Nếu **value** giữ một **Integer**, phép cast này biên dịch nhưng ném **ClassCastException** ngay tại phép cast. Với pattern **value instanceof String text**, nhánh chỉ chạy khi phép khớp thành công; không cần cast thủ công.

**Unchecked cast** xuất hiện khi compiler không thể chứng minh hoàn toàn tính đúng đắn của đối số generic. Ví dụ sau chỉ để phân tích, không đưa vào chương trình chạy an toàn:

~~~java
Object input = java.util.List.of(1, 2);
@SuppressWarnings("unchecked")
java.util.List<String> strings = (java.util.List<String>) input;

// Có thể xảy ra ClassCastException khi đọc phần tử như String.
System.out.println(strings.get(0).length());
~~~

Tại runtime, phép cast sang kiểu generic này chủ yếu kiểm tra đối tượng có phải **List** hay không; nó **không xác minh** rằng các phần tử là chuỗi. Vì vậy cast có thể vượt qua bước đầu, nhưng khi code dùng **strings.get(0)** như **String**, phép kiểm tra kiểu được chèn vào ở vị trí đọc sẽ gặp phần tử **Integer** và gây **ClassCastException**.

Nếu bỏ annotation **@SuppressWarnings("unchecked")**, compiler sẽ cảnh báo *unchecked cast*. Cảnh báo đó cho biết một phần cam kết kiểu **List<String>** chưa được chứng minh. **SuppressWarnings** chỉ ẩn chẩn đoán, không thực hiện kiểm tra runtime và không làm dữ liệu an toàn hơn.

## 3. Reifiable type: JVM biết gì về kiểu generic?

Một kiểu **reifiable** là kiểu có đủ thông tin để có thể xác định biểu diễn kiểu ở runtime. Các trường hợp quan trọng khi dùng **instanceof**:

| Kiểu | Điều có thể kiểm tra tại runtime | Ghi chú |
| --- | --- | --- |
| **String** | Đối tượng có phải String | Có đầy đủ kiểu của lớp |
| **List<?>** | Đối tượng có thuộc List | Không biết kiểu phần tử |
| **Map<?, ?>** | Đối tượng có thuộc Map | Không biết kiểu khóa/giá trị |
| **List** (raw type) | Đối tượng có thuộc List | Mất kiểm tra generic ở compile time |
| **String[]** | Đối tượng có thuộc mảng String | Mảng lưu thông tin kiểu phần tử |
| **List<String>** | Không thể xác nhận đối số String chỉ từ một Object | Generic element type đã bị xóa |
| **Map<String, Integer>** | Không thể xác nhận cả hai đối số kiểu chỉ từ Object | Cần kiểm tra entry hoặc có bằng chứng kiểu khác |

Dạng type pattern phổ biến và an toàn tại ranh giới dữ liệu không rõ kiểu:

~~~java
if (input instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
~~~

Biến **elements** có kiểu **List<?>**. Ta có thể gọi **size()**, lặp qua các phần tử như **Object**, hoặc thêm những phép xử lý không cần biết kiểu thành phần. Ta **không** được xem một phần tử bất kỳ là **String** khi chưa kiểm tra.

Ví dụ sai khi nguồn chỉ có kiểu **Object**:

~~~java
Object input = java.util.List.of("A", "B");

// Lỗi biên dịch: không thể kiểm tra đối số kiểu String từ Object.
// if (input instanceof java.util.List<String> elements) { ... }
~~~

**Một điểm tinh tế của Java 16+:** không phải mọi phép **instanceof** chứa kiểu tham số hóa đều bị cấm. Nếu kiểu tĩnh nguồn đã mang thông tin generic cần thiết, compiler có thể xác nhận phép kiểm tra kiểu cụ thể hơn, ví dụ:

~~~java
java.util.List<String> known = new java.util.ArrayList<>();
if (known instanceof java.util.ArrayList<String> arrayList) {
    System.out.println(arrayList.size());
}
~~~

Trường hợp này hợp lệ trên Java 17 vì **List<String>** ở vế trái đã cung cấp ràng buộc kiểu phần tử, còn pattern chỉ xác minh implementation **ArrayList** cụ thể. **instanceof** không tự đi kiểm tra nội dung từng phần tử. Ngược lại, từ **Object** hoặc **List<?>** chưa được chứng minh, không thể suy ra **List<String>** chỉ nhờ tên lớp collection.

Quy tắc đầy đủ là **kiểu nguồn phải downcast-compatible với kiểu pattern và phép kiểm tra phải có thể được compiler bảo đảm**. Không nên diễn giải đơn giản rằng “Java luôn cấm mọi parameterized type trong instanceof”.

## 4. Vì sao pattern không làm unchecked cast trở nên an toàn?

Xét cách viết sau:

~~~java
static void unsafe(Object input) {
    if (input instanceof java.util.List<?> list) {
        // Cảnh báo unchecked: kiểu phần tử String chưa được chứng minh.
        @SuppressWarnings("unchecked")
        java.util.List<String> strings =
                (java.util.List<String>) list;

        // Một phần tử không phải String có thể gây ClassCastException.
        System.out.println(strings.get(0).length());
    }
}
~~~

**instanceof List<?>** chỉ xác nhận *hình dạng ngoài* là một **List**. Ép **List<?> → List<String>** sau đó vẫn là **unchecked cast**, bởi JVM không kiểm tra từng phần tử theo đối số kiểu generic. Pattern matching giúp loại một phép cast từ **Object** sang **List<?>**; nó không tự chứng minh phần thông tin bị type erasure xóa đi.

Một cách sửa sai khác là ép từng phần tử ngay trong vòng lặp:

~~~java
for (Object value : list) {
    String text = (String) value; // Checked cast; có thể ném ngoại lệ
    System.out.println(text.length());
}
~~~

Cách này **không có unchecked cast**, nhưng nếu dữ liệu bị trộn kiểu, nó sẽ ném **ClassCastException**. Khi đầu vào không đáng tin hoặc muốn trả về kết quả thất bại có kiểm soát, nên dùng **instanceof String text** cho từng phần tử.

## 5. Cách an toàn: kiểm tra collection rồi kiểm tra từng phần tử

Ta có thể nhận một **Object**, kiểm tra nó là **List<?>**, kiểm tra từng phần tử là **String**, rồi tạo danh sách mới có kiểu **List<String>**:

~~~java
static java.util.Optional<java.util.List<String>> readStrings(Object input) {
    if (!(input instanceof java.util.List<?> values)) {
        return java.util.Optional.empty();
    }

    java.util.List<String> checked = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String text)) {
            return java.util.Optional.empty();
        }
        checked.add(text);
    }
    return java.util.Optional.of(java.util.List.copyOf(checked));
}
~~~

Đây là **một phương thức minh họa**; chương trình đầy đủ có **main** nằm ở phần tiếp theo.

Chuỗi bằng chứng về kiểu như sau:

1. **input instanceof List<?> values**: xác minh đầu vào là một danh sách khác **null**, nhưng chưa có thông tin về phần tử.
2. **for (Object value : values)**: đọc từng phần tử dưới kiểu an toàn **Object**.
3. **value instanceof String text**: nếu phần tử không phải **String** (kể cả **null**), trả về **Optional.empty()**.
4. **checked.add(text)**: compiler biết **text** là **String**, nên thêm vào **List<String>** không cần cast.
5. **List.copyOf(checked)**: trả về một danh sách không sửa được, được xây từ những giá trị đã kiểm tra. Tránh đưa danh sách nguồn chưa xác minh ra ngoài dưới một kiểu generic khẳng định quá mức.

Bài này chọn **từ chối toàn bộ danh sách nếu có một phần tử sai kiểu hoặc null**. Đó là chính sách dữ liệu cụ thể, không phải yêu cầu bắt buộc của Java: ứng dụng khác có thể chọn trả về lỗi chi tiết, bỏ phần tử không hợp lệ hoặc cho phép null bằng cấu trúc kết quả khác. Cần ghi rõ chính sách để không thay đổi dữ liệu âm thầm.

Không được hiểu **List.copyOf** như một bộ kiểm tra generic: bước xác minh kiểu nằm ở vòng lặp. **copyOf** chủ yếu giúp tạo kết quả không chỉnh sửa được và không giữ alias danh sách nguồn; nó từ chối phần tử null, và ở đây null đã bị loại trước.

## 6. Ví dụ Java 17 đầy đủ: List, Map và Class<T>

Lưu toàn bộ chương trình thành **SafePatternCollections.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class SafePatternCollections {
    static Optional<List<String>> readStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            return Optional.empty();
        }

        List<String> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof String text)) {
                return Optional.empty();
            }
            result.add(text);
        }
        return Optional.of(List.copyOf(result));
    }

    static <T> Optional<List<T>> checkedList(
            Object input, Class<T> elementType) {
        if (!(input instanceof List<?> values)) {
            return Optional.empty();
        }

        List<T> result = new ArrayList<>();
        for (Object value : values) {
            if (!elementType.isInstance(value)) {
                return Optional.empty();
            }
            result.add(elementType.cast(value));
        }
        return Optional.of(List.copyOf(result));
    }

    static Optional<Map<String, Integer>> readCounts(Object input) {
        if (!(input instanceof Map<?, ?> raw)) {
            return Optional.empty();
        }

        Map<String, Integer> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)
                    || !(entry.getValue() instanceof Integer count)) {
                return Optional.empty();
            }
            result.put(key, count);
        }
        return Optional.of(Map.copyOf(result));
    }

    public static void main(String[] args) {
        System.out.println(
                readStrings(List.of("red", "blue")).orElseThrow());
        System.out.println(
                readStrings(List.of("red", 7)).isPresent());
        System.out.println(
                readStrings(Arrays.asList("red", null)).isPresent());
        System.out.println(readStrings(null).isPresent());

        System.out.println(
                checkedList(List.of(4, 8), Integer.class).orElseThrow());
        System.out.println(
                checkedList(List.of(4, "eight"), Integer.class).isPresent());

        System.out.println(
                readCounts(Map.of("apples", 2)).orElseThrow().get("apples"));
        System.out.println(
                readCounts(Map.of(99, "wrong")).isPresent());
    }
}
~~~

Biên dịch trên **JDK 17+**, bật cảnh báo về unchecked và raw types:

~~~bash
javac -encoding UTF-8 -Xlint:unchecked,rawtypes SafePatternCollections.java
java SafePatternCollections
~~~

Đầu ra chính xác:

~~~text
[red, blue]
false
false
false
[4, 8]
false
2
false
~~~

**Lần lượt giải thích:**

- Danh sách **["red", "blue"]** vượt qua kiểm tra kiểu từng phần tử, trả về **List<String>** an toàn.
- Danh sách chứa **7** bị từ chối; không có ép kiểu mù và không có **ClassCastException** chỉ vì gặp một phần tử khác **String**.
- **Arrays.asList("red", null)** tạo danh sách có một phần tử null. **null instanceof String** là **false**, nên kết quả là **Optional.empty()** theo chính sách đã chọn.
- Chính **input == null** không khớp **List<?>**, trả về kết quả rỗng.
- **checkedList** nhận **Integer.class**; kiểm tra **Class.isInstance** trước rồi dùng **Class.cast** để gắn giá trị vào **T**. Với **[4, 8]** nó thành công; với **[4, "eight"]** nó thất bại có kiểm soát.
- **readCounts** kiểm tra cả kiểu của từng khóa và từng giá trị trong **Map<?, ?>**. Bản đồ có khóa **"apples"** và giá trị **2** được chấp nhận; bản đồ có khóa **Integer** và giá trị **String** bị từ chối.

Chương trình không chứa **unchecked cast** hay raw collection declaration. Lệnh **-Xlint:unchecked,rawtypes** không có cảnh báo từ các thao tác này. **Class.cast** là phép cast có kiểm tra với token lớp **Class<T>**, không phải unchecked cast sang một tham số generic mà runtime không thể xác minh.

Một chi tiết kỹ thuật: **Map.copyOf** không cam kết giữ thứ tự duyệt; ví dụ chỉ tra giá trị qua khóa **"apples"** nên đầu ra ổn định. Nếu ứng dụng cần thứ tự, hãy chọn API và hợp đồng kiểu kết quả phù hợp thay vì dựa vào thứ tự của **Map.copyOf**.

## 7. Class<T> giải quyết được gì, và không giải quyết được gì?

Phương thức tổng quát:

~~~java
static <T> java.util.Optional<T> checkedValue(
        Object input, Class<T> type) {
    return type.isInstance(input)
            ? java.util.Optional.of(type.cast(input))
            : java.util.Optional.empty();
}
~~~

Đây là mã **minh họa phương thức**, không phải chương trình độc lập. Với **String.class** hoặc **Integer.class**, token kiểu cho phép runtime xác minh một đối tượng là instance của lớp tương ứng. **isInstance(null)** trả về **false**, do đó biểu thức **Optional.of(...)** chỉ nhận giá trị đã kiểm tra khác null.

Tuy nhiên, **String.class** cung cấp token cho **String**, còn **List<String>.class** không tồn tại trong Java. Dùng **List.class** chỉ kiểm tra được bản thân danh sách, không kiểm tra phần tử kiểu **String**. Vì vậy, phương thức **checkedList(..., Class<T>)** kết hợp token kiểu với vòng lặp kiểm tra từng phần tử.

Với generic lồng nhau như **List<List<String>>**, một token **Class<List>** không đủ để xác nhận toàn bộ cấu trúc. Phải kiểm tra tầng danh sách bên ngoài, từng danh sách bên trong và từng phần tử **String**, hoặc dùng bộ giải mã/validator chuyên biệt đã định nghĩa hợp đồng dữ liệu.

**Class<T>** hữu ích cho kiểm tra các kiểu tham chiếu có thể biểu diễn bằng class token; nó không thay thế kiểm tra cấu trúc generic lồng nhau hay ràng buộc nghiệp vụ của từng phần tử.

## 8. Các mẫu code thường gặp: chọn giải pháp nào?

| Đầu vào thực tế | Cách viết ưu tiên | Mức bảo đảm |
| --- | --- | --- |
| **Object** có thể là chuỗi | **input instanceof String text** | Biết chắc đối tượng là String khi khớp |
| **Object** có thể là danh sách | **input instanceof List<?> values** | Biết chắc kiểu collection; phần tử vẫn chưa biết |
| **Object** có thể là **List<String>** | **List<?>** + kiểm tra **String** từng phần tử + tạo **List<String>** mới | Biết kiểu từng phần tử đã chấp nhận |
| **Object** có thể là **Map<String,Integer>** | **Map<?,?>** + kiểm tra từng key/value + tạo Map có kiểu | Biết key và value đã kiểm tra |
| **Object** cần thành **T** do caller chọn | **Class<T>.isInstance** rồi **Class<T>.cast** | Kiểm tra được lớp của T bằng token |
| Đã nhận **List<String>** từ API typed đáng tin | Dùng trực tiếp **List<String>** | Type contract do API/caller chịu trách nhiệm |
| Nhận dữ liệu JSON, reflection hoặc thư viện raw | Parse/validate vào DTO hoặc cấu trúc typed tại biên | Hợp đồng kiểu rõ ràng sau khi kiểm tra |
| Chỉ biết đó là **List** và cần đếm phần tử | **List<?>** + **size()** | Không cần ép thành List<String> |

Mục tiêu không phải biến mọi collection thành **List<String>**. Nếu thuật toán chỉ đếm số phần tử, giữ **List<?>** là đủ. Nếu cần xử lý chuỗi, chỉ lúc đó mới cần chứng minh phần tử thực sự là **String**.

## 9. Unchecked cast có thể ẩn ở đâu?

### 9.1. Ép List<?> sang List<String>

~~~java
// Cảnh báo unchecked, dù đã kiểm tra danh sách là List<?>.
List<String> names = (List<String>) unknownList;
~~~

Chuyển sang **List<?>**, rồi kiểm tra từng phần tử và xây danh sách typed. Một phép cast sang raw **List** cũng không chứng minh generic; raw type thường làm mất cảnh báo type safety tại các điểm sử dụng.

### 9.2. Đưa raw type qua ranh giới API

~~~java
// Ví dụ thiết kế yếu: raw type, bỏ thông tin generic của kết quả.
static java.util.List legacyValues() {
    return java.util.List.of("A", 123);
}
~~~

Nếu caller nhận bằng **List<String>**, có thể phát sinh **unchecked conversion**. Với API mới, ưu tiên **List<String>** nếu phần tử thực sự chỉ là String, **List<?>** nếu kiểu phần tử không biết, hoặc mô hình dữ liệu cụ thể nếu là hỗn hợp có chủ đích.

### 9.3. Annotation che cảnh báo mà không chứng minh invariant

~~~java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) arbitraryInput;
~~~

Không nên dùng annotation như một phép sửa kiểu. Nếu bắt buộc tích hợp thư viện cũ không có generic, hãy giới hạn chỗ unchecked cast, kiểm tra dữ liệu bằng test/validation hoặc có invariant rõ ràng và giải thích chính xác tại sao cast an toàn. Tốt nhất là điều chỉnh contract API hoặc xây bản sao typed từ các giá trị được kiểm tra.

### 9.4. Tin rằng Collections.checkedList đã xác minh dữ liệu cũ

**Collections.checkedList(list, String.class)** cung cấp một view kiểm tra kiểu cho thao tác chèn thông qua view ấy. Nó không quét tất cả phần tử đã nằm trong danh sách nguồn và không chặn những thay đổi được thực hiện thông qua một alias khác của danh sách gốc. Vì thế, không được xem nó như bằng chứng rằng một raw list hiện tại đã chứa toàn **String**. Muốn xác nhận nội dung hiện có, vẫn phải duyệt và kiểm tra.

### 9.5. Quên null và thay đổi dữ liệu trong khi kiểm tra

**null** không khớp type pattern của **instanceof**. Ví dụ chọn từ chối null và toàn bộ input không hợp lệ; dự án khác có thể cần trạng thái lỗi chi tiết. Việc đọc qua iterator của collection đang bị sửa đồng thời có thể gặp hành vi không ổn định hoặc **ConcurrentModificationException**; nếu dữ liệu được chia sẻ giữa các thread, phải bảo đảm cơ chế đồng bộ hoặc snapshot thích hợp trước và trong quá trình xác minh. **List.copyOf** chỉ tạo kết quả sau khi việc đọc/kiểm tra kết thúc, không tự sửa các vấn đề cạnh tranh xảy ra trong quá trình ấy.

## 10. Cách refactor từ cast mù sang code pattern

Giả sử code cũ lấy danh sách từ một API trả về **Object**:

~~~java
static int countLongNames(Object response) {
    @SuppressWarnings("unchecked")
    List<String> names = (List<String>) response;
    return (int) names.stream().filter(s -> s.length() >= 3).count();
}
~~~

Bản này vừa có unchecked cast, vừa có thể thất bại khi **response** không phải List hoặc chứa phần tử không phải String. Hướng xử lý an toàn với Java 17:

~~~java
static int countLongNames(Object response) {
    if (!(response instanceof List<?> values)) {
        return 0;
    }
    int count = 0;
    for (Object item : values) {
        if (item instanceof String name && name.length() >= 3) {
            count++;
        }
    }
    return count;
}
~~~

**Hai phương thức chỉ là ví dụ minh họa trong ngữ cảnh có import java.util.List**, chưa phải chương trình có **main**. Bản mới có chính sách **bỏ qua phần tử không phải String**; bản cũ có thể ném ngoại lệ. Nếu hợp đồng yêu cầu **từ chối toàn bộ danh sách khi sai kiểu**, thì phải chọn phương pháp kiểm tra rồi trả lỗi như **readStrings** ở phần 5. **Refactor an toàn** không chỉ là loại warning, mà còn phải quyết định giữ hay thay đổi hành vi lỗi một cách có chủ ý.

Quy trình thực tế:

1. Xác định nguồn dữ liệu và **kiểu tĩnh** của nó: **Object**, **List<?>**, raw **List**, JSON, reflection hay API đã typed.
2. Chỉ rõ **hợp đồng dữ liệu mong muốn**: phần tử loại nào, có cho phép null không, gặp phần tử sai kiểu thì fail hay bỏ qua.
3. Chọn type pattern reifiable hợp lý cho cấu trúc ngoài, ví dụ **List<?>** hoặc **Map<?, ?>**.
4. Kiểm tra từng phần tử, key/value hoặc cấu trúc lồng nhau bằng type pattern và/hoặc **Class.isInstance**.
5. Tạo kết quả typed mới bằng các phép thêm đã được compiler kiểm tra. Tránh cast generic của toàn collection.
6. Bật **-Xlint:unchecked,rawtypes** và review mọi cảnh báo còn lại; thử cả dữ liệu đúng, sai và null.
7. Giữ nguyên hợp đồng nghiệp vụ và xử lý lỗi đã chọn, nhất là khi thay code từ hệ thống cũ.

## 11. Bài tập tự kiểm tra

**Bài 1.** Với **Object value = List.of("a", 3)**, biểu thức **value instanceof List<?> xs** có thể trả về **true** không? Có, vì đối tượng thực tế là List. Có thể gán **List<String> names = (List<String>) xs** mà không cảnh báo không? Không; kiểu phần tử chưa được xác minh.

**Bài 2.** Với **Object value = List.of("a", "b")**, **value instanceof List<String> xs** có hợp lệ trên Java 17 không? Không, vì kiểu tĩnh **Object** không chứng minh đối số kiểu **String** của List. Muốn có **List<String>**, cần nhận typed ngay từ API hoặc kiểm tra các phần tử và xây kết quả mới.

**Bài 3.** **List<String> known = new ArrayList<>()** rồi **known instanceof ArrayList<String> xs** có hợp lệ không? Có trên Java 17: ở đây kiểu tĩnh **List<String>** cung cấp thông tin generic, còn phép kiểm tra tinh chỉnh implementation thành **ArrayList**. Không vì thế mà đối tượng **Object** bất kỳ có thể được thử trực tiếp như **List<String>**.

**Bài 4.** Một danh sách **["a", null]** có được **readStrings** chấp nhận không? Không. **null** không khớp pattern **String**; ví dụ chủ động trả về **Optional.empty()**.

**Bài 5.** **Class<String>.cast** có thể dùng để xác minh **List<String>** bằng một lệnh không? Không. **String.class** chỉ kiểm tra một đối tượng là String; cần lặp qua toàn bộ danh sách hoặc dùng validator cho cấu trúc phức tạp.

## 12. Tài liệu tham khảo

- [JLS 17 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): kiểu nào duy trì đủ thông tin tại runtime.
- [JLS 17 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): checked và unchecked conversion.
- [JLS 17 §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): quy tắc tương thích của type pattern.
- [JLS 17 §15.20.2 — instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): phép so sánh kiểu, phép khớp pattern, và ví dụ về kiểu generic tinh chỉnh từ Java 16.
- [Java SE 17 API — Class.cast / isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): kiểm tra giá trị thông qua class token.

**Kết luận:** **instanceof List<?>** chứng minh giá trị là danh sách, còn **List<String>** hứa rằng các phần tử được dùng như String. Để bảo vệ lời hứa đó tại ranh giới không đáng tin, hãy kiểm tra phần tử và tạo kết quả typed, hoặc tận dụng một API đã cung cấp thông tin generic đúng. Pattern matching giúp loại cast không cần thiết, nhưng không xóa được giới hạn type erasure; hiểu ranh giới này mới là cách tránh unchecked cast một cách thực chất.