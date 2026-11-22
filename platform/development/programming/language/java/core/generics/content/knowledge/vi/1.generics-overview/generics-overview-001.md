# Java Generics: tái sử dụng mã an toàn kiểu

Generics (kiểu tổng quát) cho phép lớp, interface và phương thức nhận **kiểu dữ liệu làm tham số**. Nhờ đó, cùng một thuật toán hoặc cấu trúc dữ liệu có thể làm việc với nhiều kiểu đối tượng, trong khi trình biên dịch vẫn kiểm tra việc truyền và nhận giá trị có đúng kiểu hay không. Đây là nền tảng của các API quen thuộc như `List<String>`, `Set<Long>` và `Map<String, Integer>`.

Sau bài này, bạn có thể giải thích vì sao mã dùng `Object` dễ gây lỗi ép kiểu, đọc và viết khai báo `<T>`, phân biệt lỗi được phát hiện khi biên dịch với lỗi chỉ xảy ra lúc chạy, và nhận biết các giới hạn cơ bản của generics.

## 1. Bài toán trước khi có generics: tái sử dụng bằng `Object`

Giả sử ứng dụng cần một hộp giữ một giá trị. Nếu viết riêng `StringBox`, `IntegerBox`, `UserBox`..., ta lặp lại cấu trúc và logic gần như giống hệt nhau. Cách làm chung là lưu giá trị dưới kiểu `Object`, vì mọi lớp tham chiếu trong Java đều kế thừa `Object`.

```java
final class LegacyBox {
    private final Object value;

    LegacyBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Cách sử dụng:

```java
LegacyBox box = new LegacyBox("Java");
String language = (String) box.get(); // Người gọi phải ép kiểu.

LegacyBox another = new LegacyBox(42);
String errorLater = (String) another.get(); // Biên dịch được; lỗi khi chạy.
```

Dòng cuối biên dịch được vì trình biên dịch chỉ biết `get()` trả về `Object` và phép ép sang `String` là một phép ép kiểu tham chiếu hợp lệ về cú pháp. Khi chạy, đối tượng thực tế là `Integer`, nên Java ném `ClassCastException`.

Ở đây có ba vấn đề:

1. **Mất thông tin kiểu khi sử dụng API:** chữ ký `Object get()` không cho người gọi biết chắc hộp đang chứa gì.
2. **Phải ép kiểu thủ công:** mã gọi dài hơn và dễ nhầm; không được trình biên dịch bảo đảm giá trị bên trong đúng kiểu mong muốn.
3. **Lỗi xuất hiện muộn:** việc đưa một kiểu vào hộp rồi lấy ra dưới kiểu khác có thể chỉ thất bại khi nhánh code đó được chạy.

`Object` giúp *tái sử dụng phần lưu trữ*, nhưng không mô tả được ràng buộc “hộp này chỉ lưu chuỗi” ngay trong hợp đồng của kiểu dữ liệu.

## 2. Generics giải quyết điều gì?

Thay kiểu cố định `Object` bằng một **tham số kiểu** (type parameter), ví dụ `T`:

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Trong khai báo `class Box<T>`, `T` là một tên đại diện cho kiểu tham chiếu sẽ được chỉ định khi sử dụng lớp. `Box<String>` và `Box<Integer>` là hai cách *tham số hóa* cùng định nghĩa `Box<T>`:

```java
Box<String> text = new Box<>("hello");
text.set("Java");
String value = text.get(); // Không cần ép kiểu tường minh.

Box<Integer> number = new Box<>(42);
int result = number.get(); // Integer được tự động unbox thành int.

// text.set(42); // KHÔNG biên dịch: yêu cầu String, nhưng nhận int.
```

**Phân biệt ba vị trí cú pháp:**

| Cú pháp | Ý nghĩa |
| --- | --- |
| `class Box<T>` | Khai báo lớp tổng quát; `T` là tham số kiểu. |
| `Box<String>` | Sử dụng lớp với đối số kiểu (type argument) là `String`. |
| `new Box<>(...)` | Toán tử kim cương `<>` yêu cầu trình biên dịch suy luận đối số kiểu từ ngữ cảnh. |

Tên `T` chỉ là quy ước, có thể đặt tên khác rõ nghĩa hơn. Các tên thường gặp gồm `T` (Type), `E` (Element), `K` (Key), `V` (Value). Chúng không phải từ khóa Java.

Điểm cốt lõi là **mối liên hệ kiểu dữ liệu xuyên suốt API**: đối số truyền vào constructor và `set(T)` phải phù hợp với `T`, còn `get()` trả về chính `T`. Trình biên dịch kiểm tra mối liên hệ đó khi gọi phương thức. Một phiên bản lớp duy nhất phục vụ nhiều kiểu mà vẫn cho phản hồi lỗi sớm.

## 3. Ví dụ hoàn chỉnh chạy với Java 17+

Tạo tệp `Main.java` với nội dung sau. Chương trình đặt cách dùng `Object` cạnh `Box<T>` và sử dụng thêm một phương thức tổng quát.

```java
import java.util.List;

public class Main {
    static final class LegacyBox {
        private final Object value;

        LegacyBox(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }
    }

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Danh sách rỗng");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        LegacyBox legacy = new LegacyBox("Java");
        String oldText = (String) legacy.get();
        System.out.println("Legacy: " + oldText);

        legacy = new LegacyBox(42);
        // String errorLater = (String) legacy.get(); // ClassCastException khi chạy.

        Box<String> text = new Box<>("Java");
        text.set("Generics");
        String word = text.get();
        System.out.println("Box<String>: " + word);

        Box<Integer> number = new Box<>(42);
        System.out.println("Box<Integer>: " + number.get());

        System.out.println("first String: " + first(List.of("A", "B")));
        System.out.println("first Integer: " + first(List.of(10, 20)));
        // text.set(42); // Lỗi biên dịch: Integer không phù hợp String.
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả chuẩn:

```text
Legacy: Java
Box<String>: Generics
Box<Integer>: 42
first String: A
first Integer: 10
```

Các dòng có chú thích về lỗi được cố ý để ở trạng thái comment. Nếu bỏ `//` trước `text.set(42)`, ví dụ sẽ **không biên dịch**: đó chính là cơ chế phát hiện sai kiểu sớm. Nếu bỏ `//` trước phép ép `legacy.get()` sang `String`, chương trình có thể ném `ClassCastException` tại dòng ấy, vì `legacy` đang chứa `Integer`.

## 4. Phương thức tổng quát: tái sử dụng thuật toán

Generics không chỉ áp dụng cho lớp. Phương thức cũng có thể **tự khai báo** tham số kiểu:

```java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    return values.get(0);
}
```

`<T>` **đứng trước kiểu trả về** `T`: đó là phần khai báo tham số kiểu riêng của phương thức. Tham số `List<T>` bảo đảm kiểu của phần tử đầu vào và kiểu trả về liên hệ với nhau.

Ví dụ:

```java
String name = first(List.of("An", "Bình")); // T được suy luận là String.
Integer id = first(List.of(101, 102));     // T được suy luận là Integer.
```

Chỉ một thuật toán lấy phần tử đầu tiên được dùng cho cả chuỗi lẫn số nguyên. Trình biên dịch suy luận `T` dựa trên kiểu đối số và ngữ cảnh lời gọi; đôi khi bạn cũng có thể viết đối số kiểu tường minh, chẳng hạn `Main.<String>first(List.of("An"))`.

Lưu ý: generics **không tự kiểm tra dữ liệu rỗng**. Kiểm tra `values.isEmpty()` ở trên là quy tắc nghiệp vụ của phương thức để tránh việc `get(0)` gây `IndexOutOfBoundsException`. An toàn kiểu và hợp lệ của giá trị là hai khía cạnh khác nhau.

## 5. Vì sao lỗi sai kiểu được phát hiện sớm?

Hãy so sánh một danh sách dùng `Object` với danh sách có kiểu phần tử xác định:

```java
List<Object> mixed = new java.util.ArrayList<>();
mixed.add("Java");
mixed.add(100); // Hợp lệ: cả String và Integer đều là Object.

List<String> languages = new java.util.ArrayList<>();
languages.add("Java");
// languages.add(100); // Không biên dịch: phần tử phải là String.

String firstLanguage = languages.get(0); // Không cần cast.
```

Bộ biên dịch Java kiểm tra các thao tác như `add`, `set`, kết quả `get` theo **đối số kiểu trong biểu thức**. Những lời gọi không thỏa hợp đồng bị từ chối khi biên dịch, trước khi chương trình được chạy. Điều này rất hữu ích khi đổi API hoặc tái cấu trúc mã: các chỗ gọi không còn phù hợp thường hiện ra ngay dưới dạng lỗi biên dịch.

| Tiêu chí | API chỉ dùng `Object` | API dùng generics |
| --- | --- | --- |
| Tái sử dụng một cấu trúc cho nhiều kiểu | Có | Có |
| Diễn đạt kiểu giá trị qua chữ ký API | Mơ hồ: thường chỉ là `Object` | Rõ: `Box<String>`, `List<Integer>` |
| Đọc giá trị về kiểu cụ thể | Thường phải cast | Thường không cần cast tường minh |
| Ngăn truyền nhầm kiểu ở lời gọi thông thường | Không | Có, khi biên dịch |
| Loại bỏ tuyệt đối `ClassCastException` | Không | **Không**; mã raw/unchecked hoặc mã cũ vẫn có thể gây lỗi |

Generics cũng giúp IDE gợi ý phương thức và tái cấu trúc chính xác hơn vì thông tin kiểu được giữ trong API.

## 6. Các tình huống nên dùng generics

**Cấu trúc dữ liệu:** khi danh sách chỉ nên chứa tên người dùng, dùng `List<String>` thay vì `List<Object>`. Với từ điển số lượng theo mã sản phẩm, dùng `Map<String, Integer>` để mô tả rõ kiểu khóa và giá trị:

```java
java.util.Map<String, Integer> quantities = new java.util.HashMap<>();
quantities.put("SKU-01", 5);
Integer count = quantities.get("SKU-01");
```

**Thành phần dùng lại:** một `Box<T>` có thể giữ `String`, `Integer` hoặc kiểu miền nghiệp vụ như `Order`, mà không sao chép một lớp hộp mới cho mỗi loại. Nếu có hai kiểu liên hệ độc lập, một lớp có thể khai báo nhiều tham số kiểu, ví dụ `Pair<K, V>`.

**Tiện ích xử lý dữ liệu:** phương thức như `first(List<T>)` tái sử dụng thao tác mà vẫn giữ kiểu trả về cho từng lời gọi. Đây là lý do thư viện Java Collections dùng generics rộng rãi: hợp đồng kiểu mạnh trong khi không cần nhân bản thuật toán cho từng kiểu phần tử.

**Khi nào chưa cần dùng:** nếu lớp chỉ xử lý duy nhất một kiểu với quy tắc riêng, khai báo cụ thể như `UserService` thường dễ hiểu hơn. Tránh thêm `<T>` chỉ để tạo cảm giác “tổng quát”; tham số kiểu nên thể hiện **mối quan hệ kiểu thật sự** giữa tham số đầu vào, kết quả và trạng thái.

## 7. Những giới hạn cần hiểu từ đầu

### 7.1. Generics không phải kiểm tra kiểu động toàn diện

Java triển khai generics chủ yếu bằng **type erasure** (xóa kiểu): trình biên dịch kiểm tra ràng buộc kiểu ở nguồn rồi xóa phần lớn thông tin đối số kiểu khỏi mã thực thi, thêm các phép ép kiểu cần thiết tại một số điểm sử dụng. Vì vậy, `List<String>` và `List<Integer>` dùng cùng một lớp triển khai `ArrayList` ở thời gian chạy; bạn không thể viết `value instanceof List<String>` để kiểm tra kiểu phần tử chính xác.

Việc kiểm tra lúc biên dịch vẫn có ích rất lớn, nhưng **không bảo đảm mọi đường đi đều an toàn** nếu dữ liệu đi qua API cũ, phép ép kiểu không kiểm chứng hoặc loại raw.

### 7.2. Tránh kiểu raw và cảnh báo `unchecked`

Kiểu `List` không có đối số kiểu là *raw type*, chủ yếu dành cho tương thích với mã Java cũ:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names; // Raw type: mất bảo đảm kiểu tại biến này.
raw.add(123);              // Có cảnh báo unchecked; có thể làm bẩn danh sách.
// String name = names.get(0); // Có thể ClassCastException nếu đọc trúng Integer.
```

Đoạn trên chỉ để chỉ ra rủi ro, **không phải mẫu sử dụng được khuyến nghị**. Ưu tiên khai báo có đủ đối số kiểu (`List<String>`) và không bỏ qua cảnh báo `unchecked` một cách máy móc. Lỗi `ClassCastException` vẫn có thể xảy ra khi đọc phần tử bị đưa vào qua `raw`.

### 7.3. Đối số kiểu phải là kiểu tham chiếu

`Box<int>` **không hợp lệ**; dùng `Box<Integer>`. Java hỗ trợ boxing/unboxing tự động khi chuyển giữa `int` và `Integer`. Tương tự, `List<double>` không hợp lệ, còn `List<Double>` hợp lệ.

### 7.4. Các kiểu tổng quát không tự có quan hệ kế thừa

Dù `Integer` là một lớp con của `Number`, `List<Integer>` **không phải** lớp con của `List<Number>`. Nếu cho phép gán như vậy, người dùng có thể thêm `Double` vào một danh sách thực chất chỉ chứa `Integer`. Generics mặc định bất biến (invariant). Wildcard như `? extends Number` hoặc `? super Integer` giải quyết một số nhu cầu linh hoạt hơn, nhưng thuộc bước học về ràng buộc kiểu và wildcard sau khi đã nắm phần cơ bản.

### 7.5. Generic type không tự bảo đảm mọi ràng buộc nghiệp vụ

`Box<String>` vẫn có thể giữ `null`; `List<Integer>` vẫn có thể chứa số âm. Generics đảm bảo sự phù hợp **về loại dữ liệu** trong các lời gọi được kiểm tra, không tự xác minh “chuỗi không rỗng”, “số dương” hay “đã được xác thực”. Các yêu cầu đó phải được xử lý bằng kiểm tra giá trị riêng.

## 8. Lỗi thường gặp và cách tránh

- **Dùng `Object` dù đã biết kiểu:** kết quả buộc nơi gọi cast và làm suy yếu hợp đồng API. Hãy đưa tham số kiểu vào lớp hoặc phương thức khi có mối quan hệ kiểu cần giữ.
- **Khai báo raw type** (`List items`): dễ gây cảnh báo `unchecked` và lỗi lúc chạy. Dùng `List<Item>` hoặc kiểu phần tử đúng yêu cầu.
- **Nghĩ generics “đổi kiểu đối tượng” ở thời gian chạy:** `T` là công cụ mô tả và kiểm tra kiểu trong mã nguồn; không phải cơ chế biến một `Integer` thành `String`.
- **Viết sai vị trí `<T>` của phương thức:** phải khai báo `static <T> T first(...)`, không chỉ viết `static T first(...)` nếu `T` chưa được khai báo trong phạm vi hợp lệ.
- **Nhầm an toàn kiểu với kiểm tra dữ liệu:** `List<String>` không ngăn chuỗi rỗng, `null` hoặc dữ liệu từ bên ngoài không đạt yêu cầu.
- **Lạm dụng ép kiểu unchecked để bỏ qua trình biên dịch:** chỉ ép kiểu khi có căn cứ rõ ràng về kiểu thực và có thể kiểm chứng ranh giới dữ liệu.

## 9. Tự kiểm tra

**Tình huống 1:** Hai lời gọi `new Box<String>("A")` và `new Box<Integer>(1)` có yêu cầu tạo hai định nghĩa lớp `Box` khác nhau không?

**Đáp án:** Không. Cùng một `Box<T>` được tái sử dụng với hai đối số kiểu khác nhau; trình biên dịch kiểm tra riêng các lời gọi theo kiểu đã chọn.

**Tình huống 2:** Vì sao `String s = (String) legacy.get()` có thể thất bại khi chạy, còn `Box<String> b; b.set(100)` bị từ chối khi biên dịch?

**Đáp án:** `LegacyBox.get()` khai báo trả `Object`, nên ép kiểu có thể được chấp nhận dù giá trị thực không phải `String`. Với `Box<String>`, tham số của `set` được xác định là `String`, nên truyền số nguyên không phù hợp với chữ ký phương thức đã tham số hóa.

**Tình huống 3:** Có thể gán `List<Integer>` cho biến `List<Number>` vì `Integer extends Number` không?

**Đáp án:** Không. Hai kiểu danh sách đó không có quan hệ subtype theo cách ấy; cơ chế bất biến giúp ngăn việc thêm loại số không phù hợp vào danh sách.

## Kết luận

Generics giải quyết một vấn đề thiết kế rất thực tế: **viết một cấu trúc hoặc thuật toán một lần và tái sử dụng cho nhiều kiểu mà vẫn giữ hợp đồng kiểu rõ ràng**. Cú pháp như `Box<T>`, `List<String>` và `static <T> T first(List<T>)` giúp đưa nhiều lỗi từ lúc chạy sang lúc biên dịch, giảm nhu cầu ép kiểu và khiến API dễ đọc hơn. Hãy bắt đầu bằng việc chỉ dùng kiểu tổng quát khi có quan hệ kiểu cần biểu diễn, tránh raw type và luôn kiểm tra ràng buộc giá trị độc lập với an toàn kiểu.