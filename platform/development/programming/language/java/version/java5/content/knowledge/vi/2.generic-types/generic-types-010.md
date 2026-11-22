# Phân biệt List<Object> và List<String>

## 1. Hai hợp đồng khác nhau cho phần tử

`List<E>` mô tả một danh sách có kiểu phần tử là `E`. Khi thay `E` bằng một kiểu cụ thể, trình biên dịch dùng kiểu đó để kiểm tra dữ liệu được thêm vào và xác định kiểu dữ liệu được đọc ra.

- `List<String>`: hợp đồng cho biết phần tử là chuỗi. Đọc phần tử nhận được `String`; thêm một số nguyên vào danh sách này là lỗi biên dịch.
- `List<Object>`: hợp đồng cho biết phần tử được nhìn dưới kiểu `Object`. Có thể thêm nhiều loại đối tượng khác nhau, nhưng khi đọc, ta chỉ biết chắc kết quả có kiểu tĩnh là `Object`.

`String` là kiểu con của `Object`, nhưng điều đó **không khiến `List<String>` trở thành kiểu con của `List<Object>`**. Muốn hiểu vì sao, cần xét cả khả năng đọc lẫn khả năng ghi mà mỗi hợp đồng hứa cung cấp.

Bài này dùng kiến thức generic còn áp dụng trong Java hiện hành. Các ví dụ độc lập chạy với Java 17 trở lên, không cần thư viện ngoài.

## 2. Thêm và đọc phần tử

Các đoạn ngắn trong mục này là câu lệnh đặt trong phương thức, với import `java.util.List` và `java.util.ArrayList`.

### List<String> giữ thông tin rằng phần tử là chuỗi

```java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
String firstName = names.get(0);
int length = firstName.length();
// names.add(42); // Lỗi biên dịch: Integer không phù hợp với String.
```

Với `List<String>`, `get(0)` có kiểu `String`, nên có thể dùng trực tiếp các phương thức chuỗi như `length()`. Không cần ép kiểu kết quả về `String`.

Kiểm tra generic không thay thế kiểm tra chỉ số: `get(0)` vẫn gây `IndexOutOfBoundsException` nếu danh sách rỗng. Nó cũng không bảo đảm một chuỗi khác `null`; chính sách `null` phụ thuộc cách tạo và sử dụng danh sách.

### List<Object> nhận nhiều loại đối tượng, nhưng đọc dưới kiểu Object

```java
List<Object> values = new ArrayList<>();
values.add("An");
values.add(42);
values.add(Boolean.TRUE);
Object firstValue = values.get(0);
// String text = values.get(0); // Lỗi biên dịch: kết quả có kiểu Object.
```

`values.add(42)` thực hiện boxing giá trị `int` thành `Integer`, rồi lưu tham chiếu đối tượng đó. Generic không dùng kiểu nguyên thủy làm đối số: có `List<Integer>`, không có `List<int>`.

Dù phần tử đầu tiên trong lần chạy này thật sự là chuỗi, trình biên dịch dựa vào **hợp đồng của biến `values`**, nên `values.get(0)` có kiểu tĩnh là `Object`. Việc đưa một `String` vào danh sách không làm biến danh sách tự đổi thành `List<String>`.

Muốn thao tác riêng cho chuỗi khi dữ liệu có nhiều kiểu, kiểm tra kiểu thực tế:

```java
Object value = values.get(0);
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Đây là pattern matching cho `instanceof`, dùng được trong Java 17 trở lên. Nếu `value` là `null` hoặc không phải chuỗi, khối `if` không chạy. Ép kiểu trực tiếp `(String) value` mà không biết dữ liệu có thể gây `ClassCastException`.

| Thao tác trên danh sách có thể thay đổi | `List<String>` | `List<Object>` |
| --- | --- | --- |
| `add("text")` | Hợp lệ về kiểu | Hợp lệ về kiểu |
| `add(42)` | Không hợp lệ về kiểu | Hợp lệ, qua boxing |
| Kiểu của kết quả `get(i)` | `String` | `Object` |
| Gọi `length()` trực tiếp trên `get(i)` | Hợp lệ nếu phần tử khác `null` | Không hợp lệ về kiểu |
| Bắt buộc chứa nhiều loại đối tượng? | Không | Không; có thể chỉ chứa chuỗi |

Cụm “hợp lệ về kiểu” chưa bảo đảm thao tác thành công khi chạy: danh sách không cho thay đổi có thể từ chối `add`, dù đối số đúng kiểu.

## 3. Vì sao không gán List<String> cho List<Object>?

Ví dụ sau cố tình để dòng sai trong chú thích:

```java
List<String> messages = new ArrayList<>();
messages.add("ready");
// List<Object> objects = messages; // Lỗi biên dịch.
```

Giả sử phép gán bị cấm ấy được cho phép, hai biến sẽ trỏ đến cùng một danh sách. Theo hợp đồng `List<Object>`, người dùng biến `objects` có quyền thêm `Integer`:

```java
// Kịch bản giả định KHÔNG hợp lệ trong Java:
// List<Object> objects = messages;
// objects.add(100);
// String message = messages.get(1);
```

Lúc này `messages` hứa trả về chuỗi, nhưng vị trí thứ hai lại chứa một số nguyên. Để ngăn sự mâu thuẫn đó, Java từ chối phép gán ngay khi biên dịch.

Tính chất này được gọi là **bất biến theo tham số kiểu (invariance)**. Với hai đối số khác nhau `String` và `Object`, quan hệ kiểu con của đối số không tự truyền qua `List`.

```text
String             → Object                 được phép mở rộng kiểu tham chiếu
List<String>       → List<Object>            không được phép gán
List<String>       → List<?>                 được phép gán
List<Object>       → List<?>                 được phép gán
```

Mở rộng kiểu của **một phần tử** vẫn hợp lệ:

```java
String text = "ready";
Object item = text;
```

Đây không phải việc đổi hợp đồng của cả danh sách. `Object` không cung cấp thao tác để thêm một số nguyên vào chính đối tượng `String` thông qua tham chiếu `item`; còn `List<Object>` lại cung cấp thao tác thêm phần tử vào danh sách.

Chiều ngược lại cũng không hợp lệ: không thể gán một `List<Object>` cho biến `List<String>` chỉ vì tình cờ các phần tử hiện tại đều là chuỗi. Kiểu đã khai báo mô tả khả năng sử dụng danh sách trong suốt chương trình, không chỉ nội dung ở một thời điểm.

## 4. Nhận danh sách bất kỳ bằng List<?>

Nếu một phương thức chỉ cần đọc và in các phần tử, yêu cầu `List<Object>` thường quá hẹp: nó không nhận được đối số đã có kiểu `List<String>`. Dùng **wildcard không giới hạn** `List<?>` để diễn đạt “danh sách có một kiểu phần tử chưa biết”.

```java
static void printElements(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Phương thức minh họa trên đặt trong một lớp và cần import `java.util.List`. Nó nhận được `List<String>`, `List<Integer>` hoặc `List<Object>` mà không ép kiểu. Khi đọc từ `List<?>`, kết quả được nhìn dưới kiểu `Object`.

Khác biệt nằm ở việc ghi:

```java
List<String> words = new ArrayList<>();
List<?> unknown = words;
// unknown.add("hello"); // Lỗi biên dịch: chưa biết kiểu phần tử bị giữ kín.
// unknown.add(7);       // Cũng lỗi biên dịch.
```

Trong trường hợp này đối tượng thật có kiểu phần tử là `String`, nhưng hợp đồng của biến `unknown` không tiết lộ điều đó. Nếu `unknown` trỏ đến danh sách số ở một lần sử dụng khác, thêm chuỗi sẽ không an toàn. Vì vậy, không thể thêm một giá trị khác `null` chỉ dựa trên kiểu `List<?>`.

Về kiểm tra kiểu, `unknown.add(null)` được phép; tuy nhiên, đối tượng danh sách có thể từ chối `null` hoặc từ chối mọi thao tác thêm. Đây không phải lý do để dùng `null` như cách lách hợp đồng.

`List<?>` cũng **không phải bảo đảm bất biến**. Những thao tác như `clear()` hoặc xóa theo chỉ số không cần biết kiểu phần tử để cung cấp một giá trị mới; chúng vẫn có thể thay đổi danh sách nếu đối tượng hỗ trợ. Muốn một API thực sự không cho sửa dữ liệu, cần thiết kế quyền sở hữu và dùng cách bọc/sao chép phù hợp.

| Kiểu | Ý nghĩa | Đọc được dưới kiểu | Thêm giá trị khác `null` |
| --- | --- | --- | --- |
| `List<String>` | Biết kiểu phần tử là chuỗi | `String` | `String` |
| `List<Object>` | Biết kiểu phần tử là `Object` | `Object` | Bất kỳ giá trị tham chiếu phù hợp; số nguyên có boxing |
| `List<?>` | Không biết kiểu phần tử cụ thể | `Object` | Không thể chỉ dựa vào kiểu này |

`List<?>` và `List<? extends Object>` có cùng ý nghĩa giới hạn trên ở đây; dạng `List<?>` thường dễ đọc hơn.

## 5. Chương trình chạy đầy đủ

Lưu thành **`ObjectAndStringListsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ObjectAndStringListsDemo {
    static void show(String label, List<?> items) {
        System.out.println(label + "=" + items);
    }

    static List<String> keepStrings(List<?> items) {
        List<String> result = new ArrayList<>();
        for (Object item : items) {
            if (item instanceof String text) {
                result.add(text);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> topics = new ArrayList<>(List.of("java", "api"));
        String first = topics.get(0);
        System.out.println(first.toUpperCase(Locale.ROOT));

        List<Object> mixed = new ArrayList<>();
        mixed.add("java");
        mixed.add(21);
        mixed.add(Boolean.TRUE);
        show("topics", topics);
        show("mixed", mixed);

        Object second = mixed.get(1);
        if (second instanceof Integer number) {
            System.out.println("next=" + (number + 1));
        }

        List<Object> copied = new ArrayList<>(topics);
        copied.add(99);
        show("copied", copied);
        show("topics after copy", topics);
        show("strings only", keepStrings(mixed));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all ObjectAndStringListsDemo.java
java ObjectAndStringListsDemo
```

Stdout chính xác:

```text
JAVA
topics=[java, api]
mixed=[java, 21, true]
next=22
copied=[java, api, 99]
topics after copy=[java, api]
strings only=[java]
```

`show` nhận cả hai loại danh sách vì tham số là `List<?>`. Nó chỉ đọc và không thêm phần tử. `keepStrings` kiểm tra từng phần tử, tạo danh sách mới và bỏ qua mọi phần tử không phải chuỗi, kể cả `null`.

`mixed.get(1)` có kiểu tĩnh `Object`; nhánh `instanceof Integer number` kiểm tra kiểu thực tế trước khi thực hiện phép cộng. Pattern matching không sửa kiểu khai báo của `mixed` và không đổi các phần tử khác trong danh sách.

## 6. Muốn chuyển dữ liệu thì sao chép hoặc chuyển đổi có chủ đích

### Từ List<String> sang một danh sách mới kiểu List<Object>

Dòng sau trong chương trình là hợp lệ:

```java
List<Object> copied = new ArrayList<>(topics);
```

Nó không gán một tham chiếu `List<String>` vào biến `List<Object>`. Constructor tạo **đối tượng danh sách mới** rồi đưa các tham chiếu phần tử từ nguồn vào. Mỗi chuỗi nguồn đều dùng được ở vị trí `Object`, nên việc sao chép an toàn.

Hai danh sách có cấu trúc độc lập: thêm `99` vào `copied` không thêm nó vào `topics`. Đây vẫn là sao chép nông đối với phần tử. Với các đối tượng có trạng thái có thể thay đổi, hai danh sách có thể cùng giữ tham chiếu đến một đối tượng; sao chép danh sách không tự sao chép sâu đối tượng ấy. Trong ví dụ, các chuỗi bất biến nên không có thao tác sửa nội dung chuỗi tại chỗ.

Nếu đã có danh sách đích có thể thay đổi, `destination.addAll(topics)` với `destination` là `List<Object>` cũng hợp lệ. `addAll` tiếp nhận một collection có kiểu phần tử là kiểu con phù hợp của kiểu phần tử đích.

### Từ List<Object> sang dữ liệu chuỗi

Cần chọn rõ ý nghĩa mong muốn:

1. **Chỉ giữ phần tử vốn là chuỗi:** dùng kiểm tra `instanceof` như `keepStrings`.
2. **Yêu cầu mọi phần tử phải là chuỗi:** kiểm tra từng phần tử và báo lỗi rõ ràng khi gặp dữ liệu sai; đồng thời quyết định có chấp nhận `null` hay không.
3. **Chuyển biểu diễn mọi phần tử thành văn bản:** gọi `String.valueOf(item)` và lưu kết quả vào danh sách mới. Đây là chuyển đổi biểu diễn, không phải chứng minh đối tượng ban đầu là `String`.

Ví dụ cho lựa chọn thứ ba, đặt trong phương thức có biến `mixed`:

```java
List<String> rendered = new ArrayList<>();
for (Object item : mixed) {
    rendered.add(String.valueOf(item));
}
```

`String.valueOf(null)` tạo chuỗi `"null"`. Nếu ứng dụng cần biểu diễn khác cho dữ liệu thiếu, phải xử lý riêng. Đừng nhầm chuỗi `"21"` được tạo từ số nguyên với một phần tử chuỗi đã có sẵn trong nguồn.

Không ép kiểu cả danh sách để bỏ qua lỗi biên dịch. Việc dữ liệu hiện tại có vẻ phù hợp không tạo ra hợp đồng `List<String>` an toàn cho một danh sách vốn cho phép ghi thêm các loại khác.

## 7. Kiểu phần tử không quyết định khả năng thay đổi

Hai khai báo đều đúng về kiểu:

```java
List<Object> editable = new ArrayList<>();
List<Object> fixed = List.of("text", 5);
editable.add(6); // Được phép và đối tượng hỗ trợ.
// fixed.add(6); // Biên dịch được nhưng chạy sẽ ném UnsupportedOperationException.
```

`List<Object>` nói về loại phần tử, không hứa rằng `add` luôn được hỗ trợ. Tương tự, `List<String> fixedWords = List.of("one", "two")` không cho thêm, xóa hay thay phần tử dù kiểu chuỗi là đúng.

`ArrayList` chấp nhận `null`; `List.of` không chấp nhận `null`. Vì vậy, câu “`List<String>` chỉ có chuỗi” cần hiểu là ràng buộc kiểu đối với phần tử khác `null`, không phải một quy tắc tự động cấm `null`.

Khai báo `final List<Object> items` chỉ ngăn gán lại biến, không tự làm đối tượng danh sách bất biến.

## 8. Chọn kiểu theo nhu cầu của API

- Dữ liệu thực sự là một tập hợp chuỗi, và thuật toán cần xử lý chuỗi: dùng `List<String>`.
- Dữ liệu cố ý có nhiều loại đối tượng, và thuật toán xử lý chúng qua hành vi chung hoặc kiểm tra kiểu có chủ đích: cân nhắc `List<Object>`.
- Thuật toán chỉ cần quan sát phần tử mà không phụ thuộc kiểu cụ thể: nhận `List<?>`.
- Thuật toán cần giữ mối quan hệ kiểu giữa đầu vào và đầu ra: cân nhắc một phương thức generic có tham số kiểu riêng, thay vì xóa hết thông tin về `Object`.

Đừng chọn `List<Object>` chỉ vì muốn một tham số “nhận được mọi danh sách”. Nó nhận được nhiều loại **phần tử** khi thao tác ghi, nhưng không phải kiểu cha của mọi kiểu **danh sách**.

Nếu nghiệp vụ có các phần tử khác nhau nhưng cùng một khái niệm, như nhiều loại sự kiện, một kiểu giao diện chung thường diễn đạt ý định rõ hơn việc dùng `Object` rồi kiểm tra từng lớp trong mọi nơi sử dụng. Chỉ đưa `Object` vào API khi sự tổng quát ấy có ý nghĩa.

## 9. Tự kiểm tra

1. Khai báo `List<Object>` chỉ chứa hai chuỗi. Giải thích vì sao `get(0).length()` vẫn không biên dịch, dù người viết biết giá trị đang có là chuỗi.
2. Viết phương thức nhận một danh sách chuỗi hoặc số và in số phần tử. Tham số `List<?>` phù hợp vì không cần thêm giá trị hay gọi API riêng của phần tử.
3. Từ `List<String>`, tạo một `List<Object>` mới bằng constructor sao chép. Thêm số vào bản sao và xác nhận nguồn giữ nguyên cấu trúc.
4. Chạy `keepStrings` với đầu vào gồm `"a"`, `3`, `null`, `"b"`. Kết quả phải chứa đúng `"a"` và `"b"`; có thể tạo đầu vào bằng `ArrayList<Object>` để cho phép `null`.
5. Giải thích tại sao `List<?>` không cho thêm chuỗi nhưng vẫn có thể cho `clear()`. Phân biệt giới hạn kiểm tra kiểu với việc đối tượng hỗ trợ thay đổi.

Khi đọc một khai báo generic, hãy xét đồng thời: phần tử nào được phép đưa vào, kiểu nào chắc chắn nhận được khi đọc ra và danh sách có được chia sẻ với một hợp đồng khác hay không. Cách xét này giải thích trực tiếp sự khác nhau giữa `List<Object>`, `List<String>` và `List<?>`.

## Tài liệu đối chiếu

- [JLS §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2): quan hệ kiểu con của các kiểu có tham số.
- [JLS §5.1.5 — Widening Reference Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.5): mở rộng kiểu tham chiếu và giới hạn của phép chuyển đổi.
- [List — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): kiểu phần tử, thao tác danh sách và các danh sách không cho thay đổi.
