# Chuyển từ kiểu tham số hóa sang raw type trong Java Generics

Một **kiểu tham số hóa (parameterized type)** cung cấp thông tin đối số kiểu, chẳng hạn `List<String>`, `Map<String, Integer>` hay `Box<Customer>`. **Raw type (kiểu thô)** là cách dùng tên một lớp hoặc interface generic mà không viết các đối số kiểu tương ứng: `List`, `Map` hoặc `Box`.

Khi viết `List raw = typed;` với `typed` có kiểu `List<String>`, Java cho phép phép gán này để tương tác với mã cũ. Tuy nhiên, kể từ điểm sử dụng biến `raw`, trình biên dịch **không còn áp dụng hợp đồng phần tử `String` khi gọi những thao tác thông qua biến raw**. Sự chuyển đổi đó đặc biệt nguy hiểm nếu mã khác thêm phần tử không tương thích vào cùng collection.

Bài học quan trọng nhất: **chuyển từ kiểu tham số hóa sang raw type không tạo danh sách mới, không xóa các phần tử và không kiểm tra hoặc đổi kiểu dữ liệu đang lưu**. Nó thay đổi **thông tin kiểu mà trình biên dịch sử dụng đối với tham chiếu**, trong khi hai biến vẫn có thể cùng trỏ đến một đối tượng runtime.

## 1. Định nghĩa và cú pháp

Ví dụ với thư viện collections:

```java
import java.util.ArrayList;
import java.util.List;

// Mã minh họa; đặt trong phương thức hoặc chương trình Java hợp lệ.
List<String> names = new ArrayList<>();
names.add("An");

List raw = names; // Chuyển từ List<String> sang raw List
```

Ở đây:

- `List<String>`: biết rằng các phương thức generic của `List<E>` đang được dùng với `E = String`.
- `List`: raw type của interface `List<E>`; việc gọi các phương thức chịu tác động của erasure và các quy tắc dùng raw type.
- `raw = names`: gán cùng một **tham chiếu** sang biến có kiểu tĩnh ít thông tin hơn; không hề sao chép collection.
- `new ArrayList<>()`: tạo đối tượng `ArrayList` như bình thường; cú pháp diamond `<>` để compiler suy luận đối số kiểu tại nguồn, không tạo một class runtime `ArrayList<String>` mới.

Raw type được Java duy trì chủ yếu để hỗ trợ **migration compatibility** với API và mã nguồn cũ có trước generics. Trong code hiện đại, hãy khai báo kiểu tham số hóa hoặc wildcard khi có thể.

### Phân biệt raw type với các kiểu gần giống

```java
// Từng dòng là một cách khai báo tham chiếu khác nhau:
List<String> exact;     // Phần tử String
List<?> unknown;        // List của một kiểu phần tử chưa biết
List<Object> objects;   // List có E = Object
List raw;               // Raw List, bỏ kiểm tra generic tại điểm dùng raw
```

`List<?>` **không phải** raw type; nó là kiểu tham số hóa với wildcard, vẫn được trình biên dịch kiểm tra an toàn theo những khả năng có thể chứng minh. `List<Object>` cũng không tương đương `List<String>`: generic Java bất biến, nên không thể gán `List<String>` trực tiếp vào `List<Object>`.

## 2. Chiều chuyển đổi `List<String>` → `List`: hợp lệ nhưng mất bảo đảm ở bên nhận

Xét ví dụ:

```java
List<String> names = new ArrayList<>();
names.add("An");

List raw = names;  // Hợp lệ
Object item = raw.get(0);
raw.add(42);       // Hợp lệ về cú pháp, có unchecked warning
```

Theo kiểu tĩnh `List<String>`, `names.add(42)` **không biên dịch** vì `42` được boxing thành `Integer` chứ không phải `String`. Nhưng `raw.add(42)` vẫn biên dịch: sử dụng raw `List` khiến đối số của phương thức `add(E)` được xét theo kiểu đã xóa là `Object`.

Như vậy, thao tác nguy hiểm là **dùng tham chiếu raw để ghi phần tử**, chứ bản thân lệnh `List raw = names;` chưa làm hỏng dữ liệu.

Với `javac -Xlint:rawtypes -Xlint:unchecked`, bạn nên kiểm tra hai loại chẩn đoán:

- **`rawtypes`**: nơi dùng kiểu generic mà bỏ đối số kiểu, ví dụ khai báo `List raw`.
- **`unchecked`**: thao tác không được compiler bảo đảm an toàn generic, ví dụ `raw.add(42)`.

Các cảnh báo có thể khác nhau về nội dung trình bày theo JDK và lựa chọn compiler. Không nên đồng nhất việc một phép gán sang raw được phép với việc mọi thao tác tiếp theo qua raw đều an toàn.

### Không tạo bản sao và không có “lớp raw” riêng

Với cùng một đối tượng:

```java
// Snippet minh họa cùng phương thức:
List<String> typed = new ArrayList<>();
List raw = typed;
System.out.println(typed == raw); // true
```

Hai biến cùng tham chiếu tới **một** collection. Java generics thông thường sử dụng type erasure, nên `List<String>` và raw `List` là hai cách nhìn qua hệ thống kiểu tại nguồn; chúng không đại diện cho hai bản sao dữ liệu.

Nếu `raw.add(123)`, `typed` có thể đọc thấy phần tử `Integer` qua cùng collection. Tại thời điểm đọc theo `String`, compiler có thể chèn ép kiểu runtime và phát sinh `ClassCastException`.

## 3. Nhìn trước chiều ngược: raw → parameterized không tự kiểm tra dữ liệu

Chiều đang học là **`List<String>` → raw `List`**: hợp lệ, nhưng phần mã dùng biến raw mất ràng buộc phần tử `String`. Chiều ngược **raw `List` → `List<String>`** cũng thường được compiler cho phép để tương thích mã cũ, nhưng nó phát **unchecked conversion warning**:

```java
List<String> typed = new ArrayList<>();
List raw = typed;              // Chuyển sang raw
raw.add(42);                   // Unchecked call, có thể làm hỏng dữ liệu
List<String> recovered = raw; // Unchecked conversion, KHÔNG xác thực String
```

Đây là snippet trong method, cần import `java.util.List` và `java.util.ArrayList`. Không có bản sao hay việc quét từng phần tử trong các phép gán này; `recovered` có thể nhìn thấy phần tử `Integer`.

| Chiều | Bằng chứng compiler còn thiếu |
|---|---|
| Typed → raw | Các lời gọi qua receiver raw không còn được kiểm tra theo argument cũ |
| Raw → typed | Không chứng minh được dữ liệu thực phù hợp type argument mới |

Nếu chỉ cần duyệt mà chưa biết element type, dùng `List<?>`. Nếu cần trả `List<String>` đáng tin cậy, kiểm tra từng phần tử và quản lý alias; riêng **unchecked cast/conversion** không giải quyết được. Phần quan trọng của bài này vẫn là tác động của **typed → raw** tới các thao tác tiếp theo.

## 4. Heap pollution: mã biên dịch được nhưng dữ liệu trái với kiểu khai báo

```java
// Snippet cố ý tạo dữ liệu sai kiểu:
List<String> names = new ArrayList<>();
names.add("An");

List raw = names;
raw.add(42);                // Lẫn Integer vào List<String>
String first = names.get(1); // Có thể ném ClassCastException
```

Tình huống một biến kiểu parameterized trỏ đến dữ liệu không còn thỏa hợp đồng kiểu mà nó tuyên bố được gọi là **heap pollution**. Trong ví dụ, heap pollution xảy ra sau khi thêm `Integer` qua raw `List`.

Tại sao lỗi thường xuất hiện **khi đọc**, thay vì ngay lúc thêm?

1. `raw.add(42)` được kiểm tra theo erasure của `List.add(E)`, có tham số tương ứng `Object`, nên runtime collection cho phép thêm `Integer`.
2. Biến `names` vẫn được compiler nhìn như `List<String>`. Khi biểu thức `names.get(1)` phải tạo kết quả kiểu `String`, bytecode có thể có `checkcast java/lang/String`.
3. `Integer` không thể cast sang `String`, nên xuất hiện `ClassCastException`.

Không phải mọi lần đọc raw đều ném lỗi. Ví dụ `Object x = names.get(1)` có thể nhận `Integer` như một `Object`; lỗi phụ thuộc thao tác cần kiểm tra kiểu cụ thể tại runtime.

Đây là lý do một lời cảnh báo unchecked đáng xem xét ngay cả khi chương trình chạy “bình thường” trong vài trường hợp thử.

## 5. Type erasure liên quan gì tới chuyển đổi sang raw?

Java generics sử dụng **xóa kiểu (type erasure)**: type parameter không có bound được xóa thành `Object`, còn type parameter có bound được xóa thành bound đầu tiên. Ví dụ, khi dùng `List<E>`, `E` có erasure là `Object`, vì thế các thao tác generic được nhìn qua raw receiver có thể nhận/trả `Object`.

Tuy nhiên, **không phải mọi raw generic method đều trả `Object`**. Xét:

```java
// Snippet minh họa chữ ký, không phải chương trình độc lập.
class NumericBox<N extends Number> {
    private N value;

    NumericBox(N value) {
        this.value = value;
    }

    N get() {
        return value;
    }

    void set(N value) {
        this.value = value;
    }
}
```

Khi dùng raw `NumericBox`, `N` có erasure là `Number`. Vì vậy `rawBox.get()` có kiểu trả về `Number` khi quan sát theo kiểu đã xóa; `rawBox.set(1.5)` có thể thực hiện với `Double` vì phương thức nhận `Number`, dù không còn ràng buộc một đối số kiểu cụ thể.

```java
// Snippet tiếp tục ví dụ NumericBox:
NumericBox<Integer> integers = new NumericBox<>(10);
NumericBox rawBox = integers;
Number current = rawBox.get(); // Hợp lệ; không phải mặc định Object
rawBox.set(1.5);               // Unchecked call; có thể gây heap pollution
// Integer later = integers.get(); // Có thể ném ClassCastException
```

Vì vậy, **raw type là cách sử dụng khai báo generic khi bỏ type argument ở nguồn**; **erasure là cơ chế biên dịch** giải thích vì sao những chữ ký generic ấy có thể được dùng ở dạng đã xóa. Hai khái niệm liên quan nhưng không hoàn toàn đồng nghĩa.

## 6. Chương trình Java 17+ thực thi đầy đủ

Lưu tệp **`RawTypeConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeConversionDemo {
    static List<String> checkedCopy(List<?> values) {
        List<String> result = new ArrayList<>();

        for (Object value : values) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(
                        "Phan tu khong phai String");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh"));

        // Chuyển từ parameterized type sang raw type:
        List raw = names;
        System.out.println("Cung doi tuong: " + (raw == names));
        System.out.println("Doc qua raw: " + raw.get(0));

        // Thao tác sai kiểu qua raw receiver (unchecked):
        raw.add(42);
        System.out.println("Sau raw.add: " + names);

        try {
            String third = names.get(2);
            System.out.println(third);
        } catch (ClassCastException exception) {
            System.out.println("Doc sai kieu: ClassCastException");
        }

        // Chuyển ngược từ raw sang parameterized type (unchecked):
        List<String> uncheckedBack = raw;
        System.out.println("Gan raw ve List<String> cung doi tuong: "
                + (uncheckedBack == names));

        // Đọc qua wildcard nhưng không xác nhận phần tử là String:
        List<?> readOnlyView = names;
        System.out.println("Qua List<?>: " + readOnlyView.get(0));

        try {
            checkedCopy(readOnlyView);
        } catch (IllegalArgumentException exception) {
            System.out.println("Kiem tra du lieu: tu choi Integer");
        }

        List<String> clean = checkedCopy(List.of("Lan", "Mai"));
        System.out.println("Ban sao an toan: " + clean);
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked RawTypeConversionDemo.java
java RawTypeConversionDemo
```

**Standard output** của chương trình (không bao gồm cảnh báo do compiler in khi biên dịch):

```text
Cung doi tuong: true
Doc qua raw: An
Sau raw.add: [An, Binh, 42]
Doc sai kieu: ClassCastException
Gan raw ve List<String> cung doi tuong: true
Qua List<?>: An
Kiem tra du lieu: tu choi Integer
Ban sao an toan: [Lan, Mai]
```

Ý nghĩa từng nhóm:

- `Cung doi tuong: true`: chuyển sang raw chỉ làm đổi **kiểu tĩnh của biến**, không clone danh sách.
- `raw.add(42)`: là ví dụ cố ý gây heap pollution để nhìn thấy hậu quả; không dùng trong code nghiệp vụ.
- `ClassCastException`: xuất hiện khi kết quả lấy từ danh sách phải được xem là `String` nhưng giá trị thực là `Integer`.
- `List<String> uncheckedBack = raw`: compiler có thể cảnh báo dù runtime vẫn chỉ có cùng một danh sách. Việc không ném lỗi ngay lúc gán **không bảo đảm** mọi phần tử đúng kiểu.
- `List<?> readOnlyView`: hạn chế những thao tác thêm phần tử không tương thích qua view này. Nó không lọc hoặc khôi phục dữ liệu đã bị làm bẩn.
- `checkedCopy`: kiểm tra từng phần tử thực tế trước khi xây dựng một `ArrayList<String>` mới; nhờ đó kết quả được bảo đảm theo quy tắc kiểm tra trong hàm. Ví dụ vẫn giữ nguyên danh sách nguồn.

Chạy với `-Xlint:rawtypes` và `-Xlint:unchecked` còn giúp thấy chỗ dùng raw type, thao tác `add` không an toàn và phép chuyển raw → `List<String>`. Phần cảnh báo là kết quả của **lệnh biên dịch**, không phải standard output được liệt kê ở trên.

## 7. So sánh raw type với `List<?>`: tại sao wildcard tốt hơn khi không biết kiểu phần tử?

Khi một API chỉ cần xem các phần tử mà không cần biết kiểu cụ thể, dùng:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Lời gọi `printAll(List<String>)` hoặc `printAll(List<Integer>)` đều hợp lệ. Kiểu `List<?>` nói rõ “đây là một danh sách với kiểu phần tử chưa biết” và **giữ các quy tắc generic**, do đó không cho phép thêm tùy ý `String`, `Integer` hay `Object` qua tham chiếu `List<?>`. Thông thường chỉ có thể thêm `null` qua `add`, vì `null` tương thích mọi kiểu tham chiếu.

Đối chiếu:

```java
// Snippet minh họa, không biên dịch dòng được chú thích lỗi.
List<String> source = new ArrayList<>();
List<?> wildcard = source;
List raw = source;

// wildcard.add("A"); // Lỗi biên dịch: không biết capture type
raw.add("A");         // Có thể biên dịch nhưng unchecked warning
Object value = wildcard.get(0); // Hợp lệ nếu có phần tử
```

Việc ví dụ cuối cần danh sách có phần tử trước khi gọi `get(0)` chỉ liên quan tới giới hạn chỉ số; `List<?>` không tự ngăn `IndexOutOfBoundsException`.

Đối với một collection nhận giá trị hoặc cung cấp giá trị theo kiểu cụ thể, có thể dùng wildcard có bound:

- `List<? extends Number>`: phù hợp khi cần đọc phần tử như `Number`.
- `List<? super Integer>`: phù hợp khi cần thêm `Integer` vào consumer, nhưng đọc trở ra chỉ có thể mặc định là `Object`.

Đây là ý tưởng **PECS (Producer Extends, Consumer Super)**. Dùng wildcard đúng mục tiêu vẫn cho phép tương tác linh hoạt mà không cần raw type.

## 8. Phương thức nhận raw type có thể làm hỏng hợp đồng của bên gọi

Giả sử API cũ khai báo:

```java
// Mã minh họa API cũ; không phải chương trình độc lập.
static void legacyAppend(List values) {
    values.add(100);
}
```

Bên gọi mới truyền `List<String>`:

```java
List<String> names = new ArrayList<>(List.of("An"));
legacyAppend(names); // Hợp lệ, nhưng API raw có thể thêm Integer
```

Compiler của bên gọi không thể chứng minh thân `legacyAppend` có giữ đúng `String` hay không. Nếu phương thức thật sự thêm `Integer`, danh sách của bên gọi bị ô nhiễm kiểu và lỗi có thể chỉ xuất hiện khi lấy ra kiểu `String`.

Với code mà bạn kiểm soát, hãy dùng một phương thức generic đúng hợp đồng:

```java
static <T> void append(List<T> values, T value) {
    values.add(value);
}

// append(names, "Binh"); // Hợp lệ
// append(names, 100);    // Bị từ chối khi không có suy luận kiểu phù hợp
```

Đối với chữ ký generic trên, nếu biến `names` là `List<String>`, việc truyền thêm giá trị `Integer` không thể được chấp nhận chỉ bằng cách “suy luận T thành Object”, vì `List<T>` là bất biến. Đây là ràng buộc hữu ích giúp giữ dữ liệu đúng kiểu.

### API cũ không sửa được thì xử lý thế nào?

Có thể chọn một trong những hướng sau tùy hợp đồng:

1. **Không cho API cũ sửa trực tiếp dữ liệu quan trọng:** truyền một bản sao hoặc view không cho chỉnh sửa khi API chỉ cần đọc; cần nhớ rằng nếu API cũ thật sự cố `add`, nó sẽ thất bại.
2. **Kiểm tra và sao chép dữ liệu khi nhận về:** dùng `List<?>` để đọc phần tử như `Object`, kiểm tra `instanceof` hoặc `Class<T>.cast`, rồi tạo collection tham số hóa mới.
3. **Viết adapter tại biên hệ thống:** cô lập raw type và unchecked conversion tại một chỗ nhỏ, tài liệu hóa điều kiện an toàn, tránh để raw type lan khắp ứng dụng.
4. **Generic hóa chữ ký khi có quyền sửa mã nguồn:** thêm type parameter hoặc wildcard phù hợp, sau đó sửa các caller và chạy kiểm tra compiler.

Việc `Collections.unmodifiableList` hay `List.copyOf` có phù hợp còn phụ thuộc API có cần sửa list hay không, có chấp nhận `null` không và bạn muốn view hay bản sao. Không có giải pháp chuyển đổi tự động nào bảo đảm biến một `List` raw không đáng tin thành `List<String>` chỉ bằng một cast.

## 9. Ép kiểu `(List<String>) raw` có an toàn hơn phép gán không?

Không. Xét:

```java
// Snippet minh họa unchecked cast:
List raw = new ArrayList();
raw.add(42);
List<String> converted = (List<String>) raw;
```

Cast từ raw `List` sang `List<String>` không kiểm tra được `String` là kiểu phần tử của từng giá trị tại runtime. Vì Java generics bị xóa kiểu, một phép cast tới kiểu parameterized như vậy thường chỉ kiểm tra được phần cấu trúc kiểu raw mà runtime hỗ trợ, không thể duyệt và xác nhận mọi phần tử.

Nếu một phần tử sai kiểu, `String s = converted.get(0)` mới có thể ném `ClassCastException`. Do đó, **thêm cast tường minh không phải là giải pháp xác thực dữ liệu**. Hãy dùng quy trình chuyển đổi có kiểm tra, như `checkedCopy(List<?>)` ở ví dụ hoàn chỉnh.

Nếu phải duy trì một unchecked cast do hợp đồng thư viện bên ngoài đã được chứng minh, có thể đặt nó trong một adapter riêng với phạm vi `@SuppressWarnings("unchecked")` tối thiểu. Tuy nhiên, cần có bất biến đủ mạnh bảo đảm nguồn dữ liệu phù hợp và kiểm thử đường đi dữ liệu, không được xem annotation là biện pháp sửa lỗi runtime.

## 10. Tác động của raw type tới method invocation

Sử dụng raw receiver có thể khiến kiểu tham số và kết quả quan sát được của các thành viên generic thay đổi theo erasure:

```java
// Snippet chỉ minh họa, không độc lập.
class Store<T> {
    private T item;

    void set(T value) {
        item = value;
    }

    T get() {
        return item;
    }
}

Store<String> typed = new Store<>();
Store rawStore = typed;    // Raw Store
rawStore.set(123);        // Unchecked call
Object value = rawStore.get();
// String text = typed.get(); // Có thể ClassCastException
```

Ở đây, type parameter `T` không bound nên `Store<T>.set` và `Store<T>.get` được xem theo kiểu đã xóa `Object` khi gọi qua raw receiver. Nhưng nếu type parameter có bound, kiểu đã xóa có thể là `Number`, `CharSequence` hoặc bound đầu tiên phù hợp.

Khi một lớp generic có **phương thức generic riêng**, cách dùng raw receiver cũng có thể ảnh hưởng việc xem chữ ký các instance member theo quy tắc raw type. Không nên tự giả định rằng mọi phương thức gọi qua raw receiver đều giữ được toàn bộ suy luận generic như khi dùng tham chiếu parameterized. Cách chắc chắn là để biến/caller mang kiểu tham số hóa đúng hoặc wildcard, rồi để compiler kiểm tra các lời gọi.

**Static member** của class generic không phụ thuộc một instance gắn type argument riêng; không viết `Store<String>.someStaticMethod()` để tạo một bản static method cho từng kiểu `T`.

## 11. Những điều raw type không làm

- **Không tạo một đối tượng mới.** `List raw = typed;` giữ nguyên tham chiếu.
- **Không biến phần tử `String` thành `Object` theo nghĩa thay đổi runtime class.** `String` vẫn là đối tượng `String`; chỉ cách compiler nhìn giá trị thay đổi.
- **Không đồng nghĩa với `List<Object>`.** Một raw `List` nhận được `List<String>` trong khi `List<Object>` không thể nhận trực tiếp `List<String>`.
- **Không làm runtime tự kiểm tra toàn bộ nội dung.** Chuyển ngược hoặc cast sang `List<String>` không duyệt xác thực các phần tử.
- **Không bỏ mọi kiểm tra kiểu Java.** Raw `List` vẫn là một `List`, và các ràng buộc không liên quan generic, kiểm tra cast thông thường, giới hạn truy cập và cú pháp Java vẫn tồn tại.
- **Không khiến `List<String>` và `List<Integer>` được phép gán trực tiếp cho nhau.** Tính bất biến của generic vẫn được áp dụng tại mã nguồn có tham số kiểu.
- **Không có nghĩa mọi lỗi xảy ra ở `raw.add`.** Dữ liệu sai kiểu thường chỉ lộ ra khi phía code parameterized cần đọc thành kiểu cụ thể.

## 12. Khi nào việc sử dụng raw type còn có lý do?

Raw type chủ yếu xuất hiện khi tương tác với code hoặc API cũ được thiết kế trước generics, hoặc tại một số ranh giới tích hợp khó tránh. Trong những tình huống đó:

1. Giới hạn raw type trong adapter nhỏ, đặt tên rõ chức năng.
2. Dùng compiler warnings `-Xlint:rawtypes` và `-Xlint:unchecked` như tín hiệu để tìm đường đi có nguy cơ heap pollution.
3. Đánh giá API có **được phép ghi** vào collection không; chỉ dùng view không cho chỉnh sửa khi hợp đồng cho phép.
4. Khi dữ liệu đến từ nguồn không đáng tin, kiểm tra từng phần tử rồi sao chép sang kiểu đúng; đừng chỉ cast.
5. Tránh loại bỏ cảnh báo bằng `@SuppressWarnings` ở cả lớp hoặc cả dự án.

Trong code Java mới, nếu chưa biết kiểu phần tử, **ưu tiên `List<?>` thay vì raw `List`**. Nếu biết kiểu cần đọc hoặc ghi, dùng kiểu tham số hóa hoặc bounded wildcard tương ứng.

## 13. Bài tập tự kiểm tra

**Câu 1.** `List<String> strings = new ArrayList<>(); List raw = strings;` có tạo một danh sách mới không?

Không. `strings == raw` là `true` vì chúng là hai tham chiếu tới cùng đối tượng.

**Câu 2.** Tại sao `raw.add(42)` có thể biên dịch khi `strings.add(42)` không biên dịch?

Qua raw receiver, ràng buộc type argument `String` không được áp dụng cho `add(E)`; chữ ký erasure có thể nhận `Object`. Compiler thường đưa ra cảnh báo unchecked.

**Câu 3.** `List<String> casted = (List<String>) raw;` có kiểm tra tất cả các phần tử thành `String` không?

Không. Cast tới parameterized collection có hạn chế do type erasure; để xác thực nội dung cần tự kiểm tra từng phần tử hoặc dùng nguồn có hợp đồng bảo đảm.

**Câu 4.** `List<?> unknown = strings;` có an toàn hơn `List raw = strings;` không?

Có nếu cần nhận một danh sách với kiểu phần tử chưa biết mà vẫn muốn compiler ngăn việc thêm giá trị tùy ý. Nhưng `List<?>` không tự khắc phục heap pollution đã xảy ra trước đó.

**Câu 5.** Vì sao `List<String> back = raw;` bị cảnh báo unchecked?

Vì compiler không có bằng chứng rằng mọi phần tử đang lưu trong raw list thỏa `String`; phép gán không thực hiện quét nội dung để xác nhận.

**Câu 6.** Có thể dùng `List<Object> objects = strings;` để thay cho raw type không?

Không. `List<String>` không phải subtype của `List<Object>` vì generic Java bất biến. Nếu cần xem mọi phần tử ở mức `Object`, cân nhắc `List<?>` hoặc wildcard phù hợp.

## 14. Quy tắc ghi nhớ

```text
List<String> typed = ...;
List raw = typed;          // Cho phép; cùng đối tượng, mất thông tin generic ở biến raw
raw.add(42);              // Unchecked; có thể gây heap pollution
List<String> back = raw;  // Unchecked conversion; KHÔNG xác thực lại phần tử
List<?> view = typed;     // View tham số hóa an toàn hơn khi chưa biết type argument
```

**Kết luận:** chuyển từ **kiểu tham số hóa sang raw type** là sự chuyển đổi hợp lệ để duy trì khả năng tương tác với mã Java cũ, nhưng làm mất một phần kiểm tra kiểu generic ở các thao tác qua tham chiếu raw. Rủi ro lớn nhất là mã raw sửa collection dùng chung bằng dữ liệu sai kiểu và lỗi chỉ bộc lộ khi code parameterized đọc lại. Với mã mới, hãy giữ kiểu tham số hóa hoặc wildcard, cô lập API cũ và kiểm tra dữ liệu thực trước khi chuyển trở lại kiểu cụ thể.