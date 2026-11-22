# Dấu `?` biểu diễn một kiểu chưa biết trong Java Generics

## 1. Dấu `?` nói gì về kiểu dữ liệu?

Trong Java Generics, `?` là **wildcard** (ký tự đại diện cho một đối số kiểu). Khi được viết không kèm ràng buộc như `List<?>`, nó được gọi là **unbounded wildcard**. Dấu `?` mang nghĩa: *có một kiểu phần tử cụ thể nào đó, nhưng tại vị trí sử dụng này ta không biết kiểu ấy là gì*.

```java
List<String> strings = new ArrayList<>();
List<Integer> integers = new ArrayList<>();

List<?> first = strings;   // Kiểu phần tử thực của danh sách là String
List<?> second = integers; // Kiểu phần tử thực của danh sách là Integer
```

Cả `first` và `second` đều có kiểu khai báo `List<?>`, nhưng chúng tham chiếu đến các danh sách có tham số kiểu khác nhau. Với `first`, kiểu ẩn bên trong dấu hỏi là `String`; với `second`, kiểu ẩn là `Integer`. Compiler **không cho mã đang sử dụng biến `List<?>` tự ý giả định** đó là `String` hay `Integer`.

Nói chính xác hơn, `List<?>` mô tả “một `List<T>` với `T` nào đó chưa biết”, không mô tả “một danh sách có thể thay đổi tự do giữa mọi kiểu phần tử”. Java sẽ giữ sự an toàn này trong kiểm tra kiểu tại thời điểm biên dịch (*compile time*).

Lưu ý: `?` không phải là tên của một lớp, một kiểu dữ liệu độc lập, một giá trị `null`, hoặc “bất kỳ giá trị nào” theo nghĩa muốn ghi gì cũng được. Nó là cú pháp chỉ **một đối số kiểu chưa được xác định**.

## 2. Tại sao cần biểu diễn một kiểu chưa biết?

Giả sử ta cần một hàm chỉ in các phần tử, bất kể danh sách chứa chuỗi, số hay đối tượng khác. Hàm không cần thêm phần tử, cũng không cần giữ lại kiểu cụ thể khi trả kết quả.

```java
static void printAll(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Hàm này nhận được `List<String>`, `List<Integer>`, `List<Customer>` hoặc `List<Object>`. Khai báo `List<?>` diễn tả đúng ý định rằng thuật toán **không phụ thuộc vào tham số kiểu `E`** của `List<E>`.

Nếu khai báo tham số `List<Object>`, ta lại không thể truyền trực tiếp `List<String>`: generic trong Java là **bất biến** (*invariant*). Nếu khai báo raw `List`, ta đánh mất kiểm tra an toàn đối số kiểu và dễ phát sinh thao tác `unchecked`. Wildcard vừa cho phép tiếp nhận danh sách có nhiều tham số kiểu khác nhau, vừa giữ giới hạn thao tác cần thiết.

## 3. Hiểu `?` qua phép gán

Ví dụ sau mô tả những phép gán hợp lệ:

```java
List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
List<Integer> ages = new ArrayList<>(List.of(20, 25));
List<Object> mixed = new ArrayList<>(List.of("Java", 21));

List<?> unknownNames = names; // Hợp lệ
List<?> unknownAges = ages;   // Hợp lệ
List<?> unknownMixed = mixed; // Hợp lệ
```

Các phép gán ấy không tạo bản sao danh sách. `unknownNames` và `names` trỏ đến **cùng một đối tượng**. Wildcard chỉ thay đổi thông tin kiểu mà đoạn mã qua biến mới được phép dựa vào.

Hai phép gán sau **không biên dịch**:

```java
List<String> names = new ArrayList<>();
List<?> anyNames = names;

// List<Object> objects = names;     // Lỗi: List<String> không phải List<Object>
// List<String> recovered = anyNames; // Lỗi: dấu ? chưa chắc là String
```

Compiler nhận `List<String>` làm `List<?>` vì không cần biết chính xác `String` để thực hiện các thao tác chung. Nhưng chiều ngược lại đòi hỏi bằng chứng rằng kiểu ẩn là `String`; chỉ biết `?` là chưa đủ.

Không nên đánh đồng “**nhận được** danh sách của bất kỳ kiểu phần tử nào” với “**cho phép thêm** bất kỳ loại phần tử nào vào danh sách”.

## 4. Đọc dữ liệu qua `List<?>`: biết được gì?

`List<E>.get(int)` vốn trả về `E`. Khi biến có kiểu `List<?>`, compiler giữ `E` như một kiểu ẩn, nhưng mọi phần tử thuộc kiểu tham chiếu đều có thể nhìn dưới kiểu `Object`. Vì vậy:

```java
List<String> names = List.of("Lan", "Minh");
List<?> items = names;

Object first = items.get(0);     // Hợp lệ
int count = items.size();        // Hợp lệ
boolean found = items.contains("Lan"); // Hợp lệ: contains nhận Object

// String text = items.get(0);  // Lỗi: compiler không biết ? là String
```

Có thể xử lý từng phần tử bằng kiểm tra kiểu khi thực sự cần:

```java
for (Object element : items) {
    if (element instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

Biểu thức `element instanceof String` kiểm tra đối tượng **tại runtime**. Nó không biến cả `List<?>` thành `List<String>`: danh sách có thể chứa kiểu phần tử khác trong những ngữ cảnh khác.

Các thao tác không phụ thuộc tham số kiểu như `size()`, `isEmpty()`, `iterator()`, `contains(Object)` và `toString()` vẫn dùng được. Với `iterator()`, mỗi phần tử có thể được nhận qua biến `Object` hoặc xử lý theo tham số kiểu ẩn trong một phương thức generic phụ.

## 5. Vì sao không thể thêm một phần tử tùy ý?

Hãy tưởng tượng compiler cho phép mã sau:

```java
List<String> names = new ArrayList<>(List.of("Lan"));
List<?> items = names;

// items.add(123); // Bị cấm khi biên dịch
```

Nếu `items.add(123)` được phép, chính `names` sẽ chứa một `Integer` dù cam kết là `List<String>`. Các lệnh đọc kiểu `String` sau này có thể gặp `ClassCastException`. Việc **từ chối thêm giá trị có kiểu cụ thể** bảo vệ lời cam kết của danh sách gốc.

Về nguyên tắc, với `List<?>`:

- `items.add("text")`: không biên dịch vì `?` có thể là `Integer`.
- `items.add(123)`: không biên dịch vì `?` có thể là `String`.
- `items.set(0, "text")`: không biên dịch vì không biết kiểu cần gán.
- `items.add(null)`: **biên dịch được**, do `null` có thể gán cho bất kỳ kiểu tham chiếu nào.

Ví dụ một danh sách mutable:

```java
List<String> names = new ArrayList<>(List.of("Lan"));
List<?> unknown = names;
unknown.add(null);              // Được phép ở mức kiểm tra kiểu
System.out.println(names);     // [Lan, null]
```

Việc `add(null)` biên dịch được **không đảm bảo mọi danh sách đều cho thêm null**: `List.of(...)` tạo danh sách không thể sửa đổi; một số implementation còn có quy định riêng về null. Trong các trường hợp đó lời gọi sửa đổi có thể ném exception. Quy tắc type-checking và khả năng mutation của implementation là hai vấn đề riêng.

## 6. Wildcard không giới hạn không làm danh sách bất biến

`List<?>` cấm thêm một giá trị non-null có kiểu tùy ý, nhưng **không cấm mọi thay đổi**. Các phương thức không cần cung cấp một phần tử thuộc kiểu ẩn, như `clear()`, `remove(Object)` và `remove(int)`, vẫn hợp lệ ở thời điểm biên dịch:

```java
List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
List<?> view = names;
view.remove("Lan");
System.out.println(names); // [Minh]
```

Hai biến cùng trỏ một `ArrayList`; wildcard không tự tạo bản sao. **Hợp lệ về kiểu không đồng nghĩa chạy được:** `List.of(...)` không hỗ trợ sửa đổi và có thể ném `UnsupportedOperationException`. Nếu caller thực sự không được phép thay đổi dữ liệu, phải cấp một unmodifiable view/snapshot thích hợp thay vì chỉ dùng wildcard.

## 7. Minh họa Java 17 hoàn chỉnh

Tạo tệp `UnknownWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class UnknownWildcardDemo {
    static void printAll(List<?> values) {
        for (Object value : values) {
            System.out.println("Value: " + value);
        }
    }

    static void swapFirstTwo(List<?> values) {
        swapCaptured(values);
    }

    private static <T> void swapCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
        List<Integer> numbers = new ArrayList<>(List.of(3, 5));

        printAll(names);
        printAll(numbers);

        List<?> unknown = names;
        Object first = unknown.get(0);
        System.out.println("First: " + first);

        swapFirstTwo(unknown);
        System.out.println("After swap: " + names);

        unknown.add(null);
        System.out.println("After null: " + names);

        Object payload = numbers;
        if (payload instanceof List<?> found) {
            System.out.println("Size: " + found.size());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac UnknownWildcardDemo.java
java UnknownWildcardDemo
```

**Stdout chính xác:**

```text
Value: Lan
Value: Minh
Value: 3
Value: 5
First: Lan
After swap: [Minh, Lan]
After null: [Minh, Lan, null]
Size: 2
```

Giải thích cơ chế:

1. `printAll` chỉ đọc phần tử qua kiểu `Object`, nên có thể nhận danh sách chứa `String` hoặc `Integer`.
2. `unknown` trỏ cùng đối tượng với `names`: kết quả hoán đổi và thêm null qua `unknown` đều thấy được khi in `names`.
3. `swapFirstTwo` giữ nguyên khai báo `List<?>` cho bên gọi, rồi dùng `swapCaptured` để compiler gán một tên kiểu `T` nhất quán cho đối số kiểu ẩn; cách làm này **không đưa kiểu phần tử lạ vào danh sách**.
4. `instanceof List<?>` hợp lệ vì đây là dạng kiểm tra được ở runtime rằng `payload` là một `List`; điều kiện ấy **không xác định** kiểu phần tử cụ thể.

Ví dụ dùng `ArrayList` vì danh sách hỗ trợ `set` và `add(null)`. Nếu thay `names` bằng `List.of("Lan", "Minh")`, mã vẫn thỏa nhiều điều kiện kiểu tĩnh nhưng `set` hoặc `add` có thể ném `UnsupportedOperationException`.

## 8. Wildcard capture: khi cần làm việc với kiểu ẩn

Trong một biểu thức generic, compiler có thể gán tạm một ký hiệu nội bộ như `CAP#1` để biểu diễn kiểu mà dấu `?` đang che giấu. Đây là *wildcard capture*. Một số thao tác lấy một phần tử rồi đặt trở lại danh sách có thể khó kiểm tra nếu mã trực tiếp làm việc với `List<?>`:

```java
static void putFirstBack(List<?> items) {
    // items.set(0, items.get(0)); // Có thể báo lỗi capture type
}
```

Dùng helper có type parameter rõ ràng:

```java
static void putFirstBack(List<?> items) {
    putFirstBackCaptured(items);
}

private static <T> void putFirstBackCaptured(List<T> items) {
    if (!items.isEmpty()) {
        T first = items.get(0);
        items.set(0, first);
    }
}
```

Vì `items.get(0)` và `items.set(0, first)` đều dùng cùng `T`, compiler chứng minh được giá trị lấy ra sẽ hợp với vị trí ghi vào. Lưu ý: helper có thể thay đổi dữ liệu nhưng chỉ đặt lại phần tử thuộc **cùng kiểu `T`**; helper không cấp quyền thêm một giá trị tùy ý như `Integer` vào `List<String>`. Cả hai đoạn trên là **đoạn minh họa phương thức**, không phải hai phương thức cùng được đặt trong một lớp; để chạy hãy chọn phiên bản có helper.

### Hai dấu hỏi không mặc nhiên chỉ cùng một kiểu

```java
static void inspectPair(List<?> left, List<?> right) {
    Object first = left.get(0);
    Object second = right.get(0);
    System.out.println(first + " / " + second);

    // right.set(0, left.get(0)); // Không đảm bảo an toàn: hai ? có thể khác kiểu
}
```

`left` có thể là `List<String>`, còn `right` có thể là `List<Integer>`. Dù cả hai cùng mang kiểu `List<?>`, ta **không có bằng chứng** hai tham số kiểu ẩn giống nhau.

Nếu cần ràng buộc hai danh sách có cùng một kiểu phần tử, dùng một tham số kiểu được đặt tên:

```java
static <T> void copyFirst(List<? extends T> source, List<? super T> target) {
    if (!source.isEmpty() && !target.isEmpty()) {
        target.set(0, source.get(0));
    }
}
```

Ví dụ `List<String>` là nguồn và `List<Object>` là đích sẽ hợp lệ. Ràng buộc `extends/super` ở đây nằm ngoài wildcard không giới hạn nhưng minh họa vì sao một ký hiệu `T` chung cho phép compiler kiểm soát quan hệ giữa nhiều vị trí.

## 9. `?` có mặt ở đâu, và không phải là gì?

Dấu hỏi xuất hiện ở vị trí **đối số kiểu** của một kiểu generic khi không cần biết đối số cụ thể:

```java
List<?> unknownElements;
Set<?> unknownMembers;
Map<?, ?> unknownKeysAndValues;
Class<?> unknownClass;
```

Ví dụ `Map<?, ?>` không biết kiểu khóa và kiểu giá trị; có thể đọc qua `Object` và gọi các phương thức tra cứu chung nhưng không thể tự ý `put` cặp khóa/giá trị khác null vì các kiểu ẩn chưa xác định. `Class<?>` biểu diễn một đối tượng `Class` cho kiểu nào đó chưa biết, hữu ích cho các API phản chiếu chỉ cần làm việc với đối tượng `Class`.

Ngược lại, các cách viết sau **không phải khai báo Java hợp lệ**:

```java
// class Box<?> { }             // Không được dùng ? để khai báo tham số kiểu
// List<?> list = new ArrayList<?>(); // Không được dùng wildcard khi tạo đối tượng
// <?> void process() { }        // Không được dùng ? để khai báo tham số kiểu phương thức
```

Khi định nghĩa lớp hoặc phương thức generic, cần **tham số kiểu có tên** như `T` hoặc `E`. Khi tạo đối tượng, hãy dùng kiểu thực hoặc diamond `<>` để compiler suy luận:

```java
List<?> view = new ArrayList<String>(); // Hợp lệ
List<?> inferred = new ArrayList<>();    // Hợp lệ; compiler suy luận kiểu đối số
```

Một điểm nữa là generics trong Java dùng *type erasure*: runtime không lưu lại `String` hay `Integer` như một kiểm tra phần tử trong đối tượng `ArrayList`. Vì vậy:

```java
Object input = List.of("x");
boolean isList = input instanceof List<?>; // Hợp lệ: kiểm tra là List
// boolean isStrings = input instanceof List<String>; // Không hợp lệ
```

`instanceof List<?>` không chứng minh các phần tử đều cùng kiểu cụ thể nào. Nó chỉ xác nhận đối tượng mang kiểu `List` ở runtime; tham số kiểu vẫn là ẩn số.

## 10. Khi nào nên viết `List<?>`, khi nào dùng `<T>`?

Dùng `List<?>` khi điều bạn muốn nói thật sự là **“kiểu phần tử không liên quan tới việc tôi đang làm”**:

```java
static boolean hasAnyElement(List<?> values) {
    return !values.isEmpty();
}

static void describe(List<?> values) {
    System.out.println("Count = " + values.size());
}
```

Dùng một type parameter có tên `<T>` khi cần **truyền thông tin kiểu** giữa tham số và kết quả, hoặc giữa nhiều tham số:

```java
static <T> T firstOrNull(List<T> values) {
    return values.isEmpty() ? null : values.get(0);
}
```

Với `List<String>`, lời gọi `firstOrNull` trả về kiểu tĩnh `String`; với `List<Integer>`, kết quả là kiểu tĩnh `Integer`. Nếu đổi tham số thành `List<?>` và kết quả thành `Object`, API sẽ làm mất mối liên hệ kiểu có ích ấy.

Nhìn chung, nếu bên gọi cần truyền vào một danh sách bất kỳ để API chỉ đọc/đếm/in, `List<?>` là hợp đồng gọn và an toàn. Nếu thuật toán cần nhận và trả lại **cùng kiểu phần tử**, `<T>` thể hiện mối quan hệ rõ hơn. Nếu cần **thêm giá trị thuộc một họ kiểu xác định**, wildcard có giới hạn như `? super T` có thể phù hợp hơn; đó là một yêu cầu khác với “không biết kiểu nào”.

## 11. Lỗi hiểu sai thường gặp

| Quan niệm | Điều đúng |
|---|---|
| “`?` nghĩa là `Object`.” | `?` là tham số kiểu chưa biết; `Object` là một kiểu xác định. |
| “`List<?>` chứa được mọi thứ.” | Nó có thể **tham chiếu** nhiều loại `List<T>`, nhưng không thể thêm tùy tiện vào một danh sách được tham chiếu. |
| “Không thêm được nên `List<?>` là immutable.” | Vẫn có thể `clear`, `remove`, `add(null)` khi implementation hỗ trợ. |
| “Hai biến `List<?>` chắc chắn có cùng kiểu phần tử.” | Mỗi dấu hỏi có thể biểu diễn một kiểu ẩn khác nhau. |
| “`instanceof List<?>` chứng minh kiểu phần tử.” | Nó chỉ kiểm tra đối tượng là `List` ở runtime. |
| “Muốn đọc `String` thì ép `List<?>` thành `List<String>`.” | Ép kiểu không tự kiểm tra từng phần tử; hãy dùng bằng chứng kiểu ở API hoặc kiểm tra từng đối tượng khi cần. |
| “Dùng raw `List` cũng an toàn như wildcard.” | Raw type bỏ mất kiểm tra tham số kiểu và có nguy cơ gây heap pollution. |

## 12. Tự kiểm tra và đáp án

Cho đoạn mã:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
List<?> unknown = numbers;
```

Hãy tự trả lời trước khi xem đáp án:

1. `unknown.get(0)` có thể gán thẳng cho biến `Integer` hay chỉ có thể gán an toàn cho `Object`?
2. `unknown.add(30)` có biên dịch không, dù danh sách thật là `List<Integer>`?
3. `unknown.add(null)` có biên dịch không, và ở đây có làm thay đổi `numbers` không?
4. `unknown.remove(0)` có biên dịch không? Trong `List`, overload nào được chọn khi truyền số nguyên `0`?
5. Có thể thay tham số của `printAll(List<?>)` bằng `List<Object>` mà vẫn truyền `List<Integer>` vào được không?

**Đáp án:** (1) Chỉ gán an toàn cho `Object` vì compiler chỉ biết `?`; (2) Không, vì kiểu tĩnh không cho phép ghi `Integer` vào kiểu ẩn; (3) Có, và `ArrayList` chấp nhận null nên `numbers` nhận thêm phần tử null; (4) Có, chọn `remove(int index)` và xóa phần tử ở chỉ số 0 nếu có, không phải xóa đối tượng `Integer.valueOf(0)`; (5) Không, bởi `List<Integer>` không phải `List<Object>`.

## 13. Ghi nhớ bản chất của unbounded wildcard

**`?` nghĩa là “một kiểu chưa biết”, không phải “một kiểu tùy tiện được phép ghi”.** `List<?>` cho phép mã làm việc với một danh sách mà không cần biết đối số kiểu của nó, miễn thao tác không đòi hỏi việc tự ý cung cấp phần tử thuộc kiểu ẩn. Đọc phần tử dưới `Object` là an toàn; thêm một giá trị `String` hay `Integer` ngẫu nhiên thì không. Khi cần liên kết cùng kiểu ẩn trong nhiều thao tác, hãy dùng wildcard capture qua helper có tham số `<T>`.