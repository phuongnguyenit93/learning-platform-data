# Pattern với raw type và cảnh báo trong Java 21

Một **raw type** là cách sử dụng một kiểu generic mà **bỏ qua danh sách type argument**. Ví dụ, `List` là raw type của `List<E>`, còn `List<String>` và `List<?>` đều có khai báo type argument. Với pattern matching, Java 21 cho phép viết:

```java
static void examine(Object value) {
    if (value instanceof java.util.List raw) {
        System.out.println("Size: " + raw.size());
    }
}
```

Type pattern `List raw` có thể khớp với một đối tượng `List`, nhưng **không chứng minh được kiểu phần tử**. Vì `raw` có kiểu raw `List`, trình biên dịch mất thông tin generic mà mã nguồn vốn có thể sử dụng. Khi bật `javac -Xlint:rawtypes`, khai báo raw type có thể bị cảnh báo; khi gọi các thao tác ghi giá trị vào raw collection, `javac -Xlint:unchecked` thường tiếp tục cảnh báo.

Điều quan trọng: **pattern khớp thành công không đồng nghĩa dữ liệu trong collection an toàn về kiểu**. Hãy phân biệt kiểm tra kiểu thực tế của collection, kiểu tĩnh của pattern variable và kiểm tra từng phần tử.

## 1. Raw type khác với kiểu generic đầy đủ như thế nào?

Với `java.util.List<E>`:

```java
java.util.List<String> names; // E được chỉ định là String
java.util.List<?> unknown;    // Có type argument wildcard: kiểu phần tử chưa biết
java.util.List raw;           // Raw type: bỏ hẳn type argument
```

Đây là các khai báo minh họa, không phải một chương trình độc lập; cần khởi tạo biến trước khi dùng chúng.

| Cách viết | Ý nghĩa của kiểu tĩnh | Khả năng thêm phần tử |
| --- | --- | --- |
| `List<String>` | Phần tử được kiểm tra theo `String` khi biên dịch | Có thể `add(String)` |
| `List<?>` | Danh sách có một kiểu phần tử **chưa xác định** | Không thể `add` một giá trị khác `null` tùy ý |
| `List` (raw) | Bỏ kiểm tra type argument ở những thao tác liên quan | Lời gọi `add(...)` có thể biên dịch nhưng phát cảnh báo unchecked |

Raw type tồn tại chủ yếu để tương thích với mã Java được viết trước khi có generics và các API cũ. Nó không phải cách viết rút gọn có cùng mức an toàn kiểu với `List<?>`. Với mã mới, nên dùng kiểu có tham số hoặc wildcard thích hợp.

## 2. Vì sao `instanceof List raw` lại hợp lệ?

Java triển khai generic chủ yếu thông qua **type erasure**: nhiều thông tin về type argument không còn sẵn để kiểm tra ở runtime. Một `ArrayList<String>` và một `ArrayList<Integer>` đều có lớp runtime là `ArrayList`, vì vậy một phép `instanceof List` chỉ xác nhận đối tượng triển khai interface `List`.

**Raw type là reifiable**: kiểu raw như `List` có biểu diễn đủ để kiểm tra bản thân kiểu tại runtime. Type pattern sau hợp lệ khi `value` là `Object`:

```java
if (value instanceof java.util.List raw) {
    Object first = raw.isEmpty() ? null : raw.get(0);
    System.out.println(first);
}
```

Đoạn code cần đặt trong một method có biến `value`. Dù pattern khớp, biến `first` chỉ được xem là `Object`, vì `raw.get(0)` không có cam kết kiểu `String`.

Một `List<String>` hay `List<Integer>` đều có thể khớp với `List raw`. Do đó, **không thể suy từ pattern `List raw` rằng các phần tử là chuỗi, số nguyên hay một kiểu cụ thể khác**.

## 3. Raw pattern không kiểm tra được `List<String>` tại runtime

Giả sử một biến chỉ có kiểu tĩnh `Object`:

```java
Object data = java.util.List.of("A", "B");

if (data instanceof java.util.List<?> list) {
    System.out.println(list.size()); // hợp lệ
}

// KHÔNG BIÊN DỊCH khi data có kiểu tĩnh Object:
// if (data instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

`List<String>` thường **không reifiable**: thông tin `String` không thể được xác minh chỉ bằng một type test trên `Object`. Ngược lại, `List<?>` có toàn bộ type argument là wildcard không giới hạn, nên có thể dùng trong runtime type test.

Có những trường hợp Java cho phép một parameterized type pattern khi **kiểu tĩnh của biểu thức** đã mang ràng buộc generic phù hợp. Điều đó không tạo thêm khả năng kiểm tra type argument bị xóa ở runtime. Với dữ liệu động đi vào qua `Object`, đừng dựa vào cú pháp `List<String>` để chứng minh tất cả phần tử là `String`.

Một cách xử lý an toàn:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        return false;
    }
    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Method này trả `false` nếu dữ liệu không phải `List`, nếu có bất kỳ phần tử khác `String`, hoặc nếu có phần tử `null`. Đối với danh sách rỗng, vòng lặp không tìm thấy phần tử vi phạm nên trả `true`. Đây là quy tắc “mọi phần tử đều là String”; nếu nghiệp vụ cần yêu cầu danh sách không rỗng, hãy thêm `!items.isEmpty()`.

## 4. Hai nhóm cảnh báo cần đọc riêng: `rawtypes` và `unchecked`

Bật chế độ cảnh báo cụ thể khi biên dịch:

```bash
javac -Xlint:rawtypes,unchecked RawTypePatternDemo.java
```

Lệnh trên vẫn **biên dịch** mã hợp lệ và phát các cảnh báo tương ứng qua luồng chẩn đoán của compiler; số dòng và câu chữ cụ thể có thể khác theo phiên bản JDK. Hai nhóm cảnh báo thường gặp:

### `rawtypes`: dùng tên generic mà thiếu type argument

```java
java.util.List rawList = new java.util.ArrayList<String>();

if (value instanceof java.util.List rawPattern) {
    System.out.println(rawPattern.size());
}
```

Đây là đoạn minh họa bên trong một method có biến `value`. Việc dùng `List` không có `<...>` là sử dụng raw type; `-Xlint:rawtypes` giúp phát hiện các chỗ này.

### `unchecked`: thao tác không được generic type checker xác nhận trọn vẹn

```java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List raw = strings; // raw type
raw.add(123);                // unchecked call to add(E)
```

Java cho phép lời gọi `raw.add(123)` vì `raw` không giữ ràng buộc `E=String` tại mức kiểm tra tĩnh. Compiler thường cảnh báo **unchecked call**, nhưng không tự chặn lệnh. Đối tượng `ArrayList` thực tế nhận `Integer` vào danh sách vốn được tham chiếu như `List<String>`.

Các phép ép từ raw collection sang collection có type argument cũng có thể tạo **unchecked cast/assignment**:

```java
java.util.List raw = new java.util.ArrayList();
// java.util.List<String> strings = raw; 
// Có thể biên dịch với cảnh báo unchecked conversion; không xác thực phần tử.
```

Cảnh báo `rawtypes` báo **thiếu type argument trong kiểu**, còn `unchecked` báo **một phép thao tác/chuyển đổi không thể kiểm chứng đủ an toàn kiểu**. Chúng liên quan nhưng không đồng nghĩa. Mã có thể phát một hoặc cả hai loại.

## 5. Nguy cơ heap pollution và `ClassCastException`

**Heap pollution** xảy ra khi một biến có kiểu parameterized tham chiếu tới đối tượng hoặc cấu trúc dữ liệu chứa giá trị không phù hợp với kiểu mà biến đó cam kết. Raw collection là một con đường phổ biến dẫn tới tình huống này.

Ví dụ:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Lan");

java.util.List raw = names;
raw.add(123); // unchecked warning

String first = names.get(0);  // "Lan": vẫn đọc được
// String second = names.get(1); // biên dịch được, ném ClassCastException khi chạy
```

Tại runtime, generic erasure khiến `ArrayList` không tự kiểm tra rằng giá trị được thêm qua `raw` bắt buộc là `String`. Nhưng khi mã đọc qua `List<String>`, compiler chèn kiểm tra kiểu cần thiết cho kết quả trả về; `Integer` không thể trở thành `String`, nên phát sinh `ClassCastException`.

**`instanceof List raw` không tạo ra heap pollution chỉ bằng việc khớp.** Nguy cơ xuất hiện khi sử dụng quyền truy cập raw để thêm giá trị sai kiểu hoặc khi ép kiểu không kiểm tra. Vì vậy, việc chỉ đọc `size()` hoặc đọc phần tử như `Object` khác với việc ghi phần tử qua raw reference.

Cũng cần phân biệt: một `List<Integer>` khớp thành công với `List raw` là **đúng theo semantics** của runtime type check; đó không phải lỗi của pattern matching. Lỗi là suy luận thêm rằng danh sách ấy chứa `String` mà chưa kiểm chứng.

## 6. Pattern variable có kiểu raw thì mất gì?

Trong:

```java
static void printItems(Object input) {
    if (input instanceof java.util.List raw) {
        for (Object item : raw) {
            System.out.println(item);
        }
    }
}
```

Biến `raw` được khai báo bởi type pattern và có **kiểu raw `List`**. Nó vẫn có thể gọi `size()`, `isEmpty()`, `get(int)` và lặp qua các phần tử như `Object`. Tuy nhiên, trình biên dịch không còn kiểm tra `add` theo type argument gốc của collection.

Ngoài ra, **flow scoping** vẫn áp dụng như với các pattern variable khác: `raw` chỉ có hiệu lực tại các vị trí mà phép khớp `input instanceof List raw` chắc chắn đúng. Raw type không giúp biến vượt qua phạm vi control flow và không biến `null` thành giá trị khớp.

So sánh với wildcard:

```java
static void readSafely(Object input) {
    if (input instanceof java.util.List<?> items) {
        for (Object item : items) {
            if (item instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
        // items.add("new"); // lỗi biên dịch: không biết element type của List<?>
    }
}
```

`items` cho phép đọc phần tử dưới dạng `Object` như raw list, nhưng **chặn việc thêm một giá trị cụ thể** có thể không phù hợp với type argument chưa biết. Việc kiểm tra từng phần tử bằng `instanceof String text` mới chứng minh phần tử đó là chuỗi.

## 7. Với `switch`, ưu tiên `List<?>` và guard phù hợp

Java 21 hỗ trợ pattern matching cho `switch`. Khi selector có kiểu `Object`, có thể dùng một pattern `List<?>` rồi kiểm tra trạng thái:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "null";
        case java.util.List<?> list when list.isEmpty() -> "empty list";
        case java.util.List<?> list -> "list of size " + list.size();
        default -> "other";
    };
}
```

Nhánh thứ nhất xử lý selector `null`, hai nhánh `List<?>` phân biệt danh sách rỗng và không rỗng, còn `default` bao phủ các kiểu khác.

Bạn *có thể* viết `case java.util.List raw -> ...` để khớp raw type, nhưng thường không có lợi khi chỉ cần đọc cấu trúc. Wildcard dễ diễn đạt “có một `List`, chưa biết phần tử là kiểu gì” hơn và giúp tránh cảnh báo `rawtypes`.

Cần nhớ `when list.isEmpty()` chỉ kiểm tra **danh sách có rỗng hay không**; nó không khẳng định phần tử của danh sách không rỗng là `String`. Muốn kiểm tra nội dung, vẫn cần duyệt phần tử hoặc sử dụng một lớp dữ liệu có hợp đồng kiểu rõ ràng.

## 8. Đọc code cũ dùng raw type: cách xử lý có kiểm soát

Một số API legacy trả về `List`, `Map` hoặc `Class` raw. Khi gặp chúng:

1. **Nhận diện ranh giới raw**: API nào trả hoặc nhận raw type, chỗ nào phát `rawtypes` hay `unchecked`.
2. **Kiểm tra hình dạng bên ngoài bằng pattern reifiable**: ví dụ `input instanceof List<?> list` hay `input instanceof Map<?, ?> map`.
3. **Kiểm tra từng phần tử hoặc key/value** theo yêu cầu nghiệp vụ trước khi sử dụng như kiểu cụ thể.
4. **Tạo collection có kiểu rõ ràng** nếu cần trả `List<String>`, thay vì ép kiểu mù từ `List`.
5. **Cô lập đoạn raw nếu bắt buộc**: giữ raw reference ở phạm vi nhỏ, và nếu thực sự cần `@SuppressWarnings("rawtypes")` hoặc `@SuppressWarnings("unchecked")`, chỉ đặt annotation tại vị trí hẹp nhất đã được kiểm tra và ghi rõ cơ sở an toàn.

Ví dụ chuyển dữ liệu động thành danh sách chuỗi đã xác minh:

```java
static java.util.List<String> checkedCopy(Object input) {
    if (!(input instanceof java.util.List<?> list)) {
        throw new IllegalArgumentException("Expected a List");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : list) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Non-String element");
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

`List.copyOf` tạo một danh sách không thể sửa qua API của nó; ở đây mọi phần tử đã được xác minh là `String` khác `null`, nên không bị lỗi do phần tử `null`. Kết quả có kiểu `List<String>` đúng nhờ **đọc và kiểm tra từng phần tử**, không phải do unchecked cast.

Cách kiểm tra này tốn chi phí duyệt danh sách. Với dữ liệu có thể bị thay đổi đồng thời trong lúc kiểm tra, cần thêm hợp đồng đồng bộ hoặc nhận bản snapshot đáng tin cậy; việc duyệt đơn lẻ không đảm bảo tránh mọi cuộc đua dữ liệu.

## 9. Chương trình hoàn chỉnh: cảnh báo lúc biên dịch và lỗi lúc chạy

Tạo file **`RawTypePatternDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypePatternDemo {
    static String inspect(Object input) {
        if (input instanceof List raw) {
            Object first = raw.isEmpty() ? null : raw.get(0);
            return "raw list, first-is-String=" + (first instanceof String);
        }
        return "not a list";
    }

    static boolean allStrings(Object input) {
        if (!(input instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        System.out.println(inspect(names));
        System.out.println(allStrings(names));

        List raw = names;
        raw.add(123); // unchecked call: phá vỡ hợp đồng List<String>

        System.out.println(allStrings(names));
        try {
            String second = names.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }

        Object numbers = List.of(1, 2);
        System.out.println(inspect(numbers));
        System.out.println(allStrings(numbers));
    }
}
```

Biên dịch bằng **JDK 21**, bật cảnh báo để quan sát việc sử dụng raw type:

```bash
javac --release 21 -Xlint:rawtypes,unchecked RawTypePatternDemo.java
java RawTypePatternDemo
```

Bước biên dịch sẽ phát cảnh báo liên quan đến raw type và unchecked call; chẩn đoán cảnh báo **không nằm trong stdout của chương trình**. Nếu compiler được cấu hình coi cảnh báo là lỗi (ví dụ thêm `-Werror`), phải xử lý cảnh báo trước khi chạy.

Stdout của lệnh `java`:

```text
raw list, first-is-String=true
true
false
ClassCastException
raw list, first-is-String=false
false
```

Tại sao có kết quả ấy?

- Ban đầu `names` chứa `"Lan"`; cả `List raw` và `List<?>` đều khớp với đối tượng `ArrayList`. Phần tử đầu là `String`, `allStrings(names)` trả `true`.
- `raw.add(123)` thêm một `Integer` vào cùng đối tượng mà `names` nhìn như `List<String>`. Đó là đường gây heap pollution.
- `allStrings(names)` sau đó trả `false` vì đã kiểm tra được phần tử `Integer` không phải `String`.
- `names.get(1)` đọc theo kiểu tĩnh `List<String>` và gây `ClassCastException` ở lần đọc phần tử sai kiểu; catch bắt lỗi để chương trình tiếp tục.
- `List.of(1, 2)` vẫn khớp `List raw` dù chứa `Integer`; việc khớp raw không nói gì về type argument.

Ví dụ cố ý sử dụng raw type để **tái hiện cảnh báo và hậu quả**. Trong mã sản phẩm, không nên gọi `add` qua raw reference khi chưa bảo đảm kiểu phần tử.

## 10. Những hiểu nhầm cần tránh

**“Raw pattern kiểm tra luôn generic argument.”** Sai. `instanceof List raw` chỉ khớp runtime `List`; nó không chứng minh `List<String>`.

**“Nếu không có `ClassCastException` thì raw collection an toàn.”** Sai. Lỗi có thể chỉ xuất hiện muộn khi code khác đọc phần tử với kiểu mong đợi, hoặc có thể chưa từng được kích hoạt trong một đường chạy cụ thể.

**“`List<?>` biết phần tử là kiểu gì.”** Sai. `List<?>` giữ sự không chắc chắn của element type một cách an toàn hơn: đọc dưới dạng `Object`, không ghi tùy ý. Muốn có `String` phải kiểm tra từng phần tử.

**“Chỉ cần `@SuppressWarnings` là sửa được vấn đề.”** Sai. Annotation chỉ ẩn hoặc giảm chẩn đoán compiler cho phạm vi được áp dụng; nó không thêm kiểm tra runtime, không khôi phục type argument và không loại bỏ heap pollution.

**“Mọi `instanceof List<String>` đều có thể kiểm tra ở runtime.”** Sai. Trong tình huống dữ liệu chỉ có kiểu `Object`, generic argument không thể xác nhận bằng type test đó. Sự cho phép ở một số ngữ cảnh được ràng buộc bởi kiểu tĩnh không biến Java thành hệ thống runtime-check đầy đủ cho generic type argument.

**“Raw type pattern được phép là nên dùng.”** Không hẳn. Trong mã mới, `List<?> list` hoặc `Map<?, ?> map` thường rõ ý định hơn, hỗ trợ compiler kiểm tra an toàn kiểu và tránh cảnh báo không cần thiết.

## 11. Cách quyết định trong thực tế

Khi cần kiểm tra dữ liệu động:

- Muốn biết có phải một `List` hay không? Dùng `instanceof List<?> list`.
- Muốn biết có phải `List` chứa toàn `String` hay không? Khớp `List<?>`, sau đó xác minh **mọi phần tử** theo chính sách với `null` và danh sách rỗng.
- Muốn nhận một `List<String>` để sử dụng lâu dài? Tạo danh sách có kiểu từ dữ liệu đã kiểm tra, hoặc nhận đầu vào từ API generic có hợp đồng rõ ràng.
- Gặp raw type từ thư viện cũ? Đặt ranh giới kiểm tra dữ liệu và thu hẹp phạm vi thao tác raw; đọc cảnh báo `rawtypes` và `unchecked` trước khi quyết định có thể bỏ qua hay không.
- Muốn thử hành vi thực tế? Biên dịch với `-Xlint:rawtypes,unchecked`, chạy kiểm thử cả trường hợp phần tử sai kiểu và kiểm tra điểm có thể ném `ClassCastException`.

**Ghi nhớ:** raw type là một kiểu có thể kiểm tra ở runtime, nên raw type pattern có thể hợp lệ trong Java 21; nhưng **reifiable không đồng nghĩa giữ được type argument**. Khi mục tiêu là an toàn generic, `List<?>` cộng kiểm tra phần tử và một hợp đồng dữ liệu rõ ràng thường là lựa chọn tốt hơn.
