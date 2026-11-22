# Phân biệt `List<?>` và `List<Object>`

## 1. Hai cách khai báo trả lời hai câu hỏi khác nhau

Trong Java, `Object` là lớp cha của các kiểu tham chiếu, nhưng điều đó không có nghĩa `List<Object>` là kiểu cha của mọi `List<T>`.

- `List<Object>`: danh sách có kiểu phần tử được khai báo chính xác là `Object`. Qua tham chiếu này, có thể truyền các giá trị thuộc những kiểu tham chiếu khác nhau vào phương thức nhận phần tử.
- `List<?>`: danh sách có một kiểu phần tử chưa biết. Ký hiệu đại diện không giới hạn (unbounded wildcard) `?` cho phép nhận danh sách có kiểu phần tử bất kỳ, nhưng phần mã đang giữ tham chiếu này không được tùy ý chọn kiểu phần tử để thêm vào.

Có thể hình dung: `List<Object>` là một chiếc hộp được thiết kế nhận nhiều loại đồ; `List<?>` là chiếc hộp có nhãn kiểu bị che đi. Chiếc hộp thứ hai vẫn có quy tắc riêng, chỉ là mã đang sử dụng chưa biết quy tắc đó.

Sự khác nhau này thuộc hệ thống kiểu generic, vẫn được sử dụng trong Java hiện đại. Không cần dùng kiểu thô (raw type) hoặc ép kiểu không kiểm tra để giải quyết bài toán.

## 2. Vì sao `List<String>` không phải `List<Object>`?

Quan hệ `String` là kiểu con của `Object` không tự chuyển thành quan hệ `List<String>` là kiểu con của `List<Object>`. Với cùng lớp generic `List`, đối số kiểu có tính bất biến (invariance).

Đoạn sau chỉ minh họa lỗi, không phải chương trình chạy độc lập:

```java
List<String> names = new ArrayList<>();
names.add("Lan");

// List<Object> objects = names; // Lỗi biên dịch.
```

Nếu phép gán bị cấm này được cho phép, mã sử dụng `objects` có thể gọi `objects.add(100)`. Cùng danh sách đó sau đó được đọc qua `names` như thể mọi phần tử đều là `String`. Quy tắc bất biến ngăn tình huống vi phạm kiểu ngay khi biên dịch.

Ngược lại, phép gán dưới đây hợp lệ:

```java
List<String> names = new ArrayList<>();
List<?> unknown = names;
```

Qua `unknown`, trình biên dịch không cho thêm một `Integer` hay một `String` tùy ý. Vì vậy, việc tham chiếu tới danh sách chuỗi dưới dạng `List<?>` không làm mất bảo đảm kiểu của `names`. Cả hai biến vẫn trỏ đến cùng danh sách; không có thao tác sao chép hay chuyển đổi phần tử.

## 3. So sánh các thao tác quan trọng

Bảng dưới nói về khả năng được hệ thống kiểu chấp nhận. Việc thực hiện có thành công khi chạy hay không còn phụ thuộc đối tượng danh sách cụ thể và các điều kiện như chỉ số hợp lệ.

| Thao tác | `List<?>` | `List<Object>` |
| --- | --- | --- |
| Nhận một biến kiểu `List<String>` | Có | Không |
| Nhận một biến kiểu `List<Integer>` | Có | Không |
| Nhận một biến kiểu `List<Object>` | Có | Có |
| Đọc `get(i)` vào biến `Object` | Có | Có |
| Đọc trực tiếp `get(i)` vào biến `String` | Không | Không |
| Thêm một `String`, `Integer` hoặc `Object` khác `null` | Không qua tham chiếu này | Có về mặt kiểu |
| Gọi `add(null)` | Hợp lệ về mặt kiểu | Hợp lệ về mặt kiểu |
| Gọi `clear()`, `remove(int)` | Hợp lệ về mặt kiểu | Hợp lệ về mặt kiểu |
| Gọi `contains(Object)`, `remove(Object)` | Hợp lệ về mặt kiểu | Hợp lệ về mặt kiểu |

### Đọc được dưới dạng `Object`

```java
List<?> values = List.of("Java", "Spring");
Object first = values.get(0);
// String text = values.get(0); // Lỗi: kiểu phần tử chưa được biết là String.
```

Với `List<Object>`, việc một phần tử thực tế đang là chuỗi cũng không làm kiểu trả về của `get` tự biến thành `String`:

```java
List<Object> values = new ArrayList<>();
values.add("Java");
Object first = values.get(0);
// String text = values.get(0); // Vẫn lỗi biên dịch.
```

Khi cần xử lý riêng một kiểu, có thể kiểm tra kiểu bằng `instanceof` trước. Tuy nhiên, nếu nghiệp vụ thực chất chỉ chứa chuỗi, `List<String>` thường biểu đạt yêu cầu rõ hơn một danh sách hỗn hợp cần kiểm tra từng phần tử.

### Không được thêm giá trị khác `null` tùy ý vào `List<?>`

```java
List<?> values = new ArrayList<String>();
// values.add("Java");       // Lỗi biên dịch.
// values.add(42);           // Lỗi biên dịch.
// values.add(new Object()); // Lỗi biên dịch.
values.add(null);            // Hợp lệ; ArrayList cho phép null.
```

Dù người đọc nhìn thấy `new ArrayList<String>()`, biểu thức `values` vẫn có kiểu tĩnh `List<?>`. Quyền thao tác được kiểm tra từ kiểu tĩnh của biểu thức đang sử dụng.

`null` là ngoại lệ vì có thể chuyển thành mọi kiểu tham chiếu. Điều đó chỉ giải thích tính hợp lệ khi biên dịch; một danh sách cấm `null`, hoặc không hỗ trợ thay đổi, có thể từ chối thao tác khi chạy. Đừng dùng `add(null)` như một giải pháp để lách ý nghĩa kiểu dữ liệu.

## 4. `List<?>` không phải danh sách bất biến

Ký hiệu `?` hạn chế việc truyền vào một phần tử có kiểu chưa xác định; nó không loại bỏ mọi phương thức thay đổi danh sách.

Ví dụ minh họa trong một phương thức:

```java
List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
List<?> view = names;

view.remove(0); // Hợp lệ: tham số là chỉ số int.
System.out.println(names); // [Minh]

view.clear();
System.out.println(names); // []
```

Cũng có thể gọi `view.remove("Minh")`, vì chữ ký của overload này nhận `Object`, không nhận `E`. `size()`, `isEmpty()`, `contains(...)`, duyệt bằng vòng lặp và lấy phần tử dưới dạng `Object` đều dùng được.

Cần phân biệt ba điều:

1. **Kiểu tham chiếu** quyết định trình biên dịch cho phép gọi gì.
2. **Đối tượng danh sách cụ thể** quyết định thao tác thay đổi có được hỗ trợ khi chạy không.
3. **Đối tượng phần tử** có thể vẫn thay đổi trạng thái được, ngay cả khi cấu trúc danh sách không cho sửa.

Ví dụ, `List.of(...)` tạo danh sách không cho thay đổi cấu trúc hoặc thay thế phần tử. Gán nó vào `List<Object>` không làm danh sách trở thành có thể sửa; gán một `ArrayList` vào `List<?>` cũng không làm danh sách bất biến. Đây là hai vấn đề độc lập. Xem hợp đồng của [List trong Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

## 5. Chọn chữ ký phương thức theo nhu cầu

### Chỉ cần đọc các đối tượng mà không quan tâm kiểu phần tử

Dùng `List<?>` để nhận được cả danh sách chuỗi, danh sách số và danh sách đối tượng:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Nếu thay tham số bằng `List<Object>`, lời gọi với một biến `List<String>` sẽ bị từ chối, dù thân phương thức chỉ cần in phần tử. Tham số `List<Object>` đặt ra ràng buộc chặt hơn nhu cầu thực tế.

### Chủ động thiết kế danh sách chứa nhiều kiểu giá trị

Dùng `List<Object>` khi phần tử thực sự được mô hình hóa là những đối tượng bất kỳ:

```java
List<Object> row = new ArrayList<>();
row.add("Lan");
row.add(25);   // int được boxing thành Integer.
row.add(true); // boolean được boxing thành Boolean.
```

Đây là lựa chọn có chủ đích về mô hình dữ liệu. Nếu ba giá trị có vai trò cố định như tên, tuổi và trạng thái kích hoạt, một lớp hoặc `record` với trường có tên thường rõ ràng hơn. Không nên chọn `List<Object>` chỉ vì muốn phương thức nhận mọi danh sách.

### Cần biết thêm về kiểu phần tử hoặc mối quan hệ giữa các tham số

- Cần đọc các giá trị như `Number`: cân nhắc `List<? extends Number>`.
- Cần thêm `Integer` vào danh sách `Integer`, `Number` hoặc `Object`: cân nhắc `List<? super Integer>`.
- Cần dùng cùng một kiểu trong nhiều vị trí, chẳng hạn đọc rồi trả về chính kiểu đó: dùng tham số kiểu như `<T> T first(List<T> values)`.

Các chữ ký này giải quyết nhu cầu khác nhau; không thể thay tất cả bằng `List<Object>` hoặc bằng `List<?>` mà vẫn giữ nguyên hợp đồng.

## 6. Giới hạn “không biết kiểu” và kỹ thuật capture

Một lỗi thường gặp là nghĩ đọc rồi ghi lại chính giá trị vừa đọc luôn hợp lệ trực tiếp:

```java
static void resetFirst(List<?> values) {
    // values.set(0, values.get(0)); // Lỗi biên dịch do capture.
}
```

Một phương thức trợ giúp generic có thể đặt tên `T` cho kiểu đang được che bởi wildcard:

```java
static void resetFirst(List<?> values) {
    resetFirstCaptured(values);
}

private static <T> void resetFirstCaptured(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.set(0, first);
    }
}
```

Trong phương thức trợ giúp, cùng một `T` liên kết kiểu đọc từ `get` với kiểu nhận vào của `set`. Đây là cách giữ nguyên an toàn kiểu, không phải biến `List<?>` thành `List<Object>`. Thao tác `set` vẫn có thể bị đối tượng danh sách không cho sửa từ chối khi chạy.

Cơ chế ngôn ngữ đứng sau cách này là [capture conversion, JLS §5.1.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.10). Không cần nắm toàn bộ thuật toán của trình biên dịch để sử dụng nguyên tắc: đặt tên kiểu khi cần duy trì quan hệ giữa các thao tác.

## 7. Chương trình hoàn chỉnh để quan sát sự khác biệt

Lưu mã sau vào `WildcardVsObject.java`. Chương trình dùng Java 17 trở lên; không cần thư viện ngoài.

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardVsObject {
    static void printAll(String label, List<?> values) {
        System.out.println(label + values);
    }

    static void addMarker(List<Object> values) {
        values.add("marker");
        values.add(7);
    }

    private static <T> void resetFirst(List<T> values) {
        if (!values.isEmpty()) {
            T first = values.get(0);
            values.set(0, first);
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
        List<Integer> numbers = List.of(1, 2);
        List<Object> mixed = new ArrayList<>();

        addMarker(mixed);
        printAll("names = ", names);
        printAll("numbers = ", numbers);
        printAll("mixed = ", mixed);

        List<?> unknown = names;
        Object first = unknown.get(0);
        System.out.println("first = " + first);

        resetFirst(unknown);
        unknown.remove(0);
        printAll("names after remove = ", names);

        unknown.add(null);
        printAll("names after null = ", names);

        List<Object> copy = new ArrayList<>(names);
        copy.add(99);
        printAll("copy = ", copy);
        printAll("original = ", names);

        // addMarker(names);         // Không nhận List<String>.
        // List<Object> bad = names; // Không có phép gán này.
        // unknown.add("An");       // Không biết kiểu phần tử của unknown.
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 WildcardVsObject.java
java WildcardVsObject
```

Kết quả chuẩn:

```text
names = [Lan, Minh]
numbers = [1, 2]
mixed = [marker, 7]
first = Lan
names after remove = [Minh]
names after null = [Minh, null]
copy = [Minh, null, 99]
original = [Minh, null]
```

Ba quan sát cần rút ra:

- `printAll(List<?>)` nhận được cả ba kiểu danh sách.
- `unknown` và `names` cùng trỏ đến một đối tượng, nên xóa hoặc thêm `null` qua `unknown` được nhìn thấy qua `names`.
- `new ArrayList<>(names)` tạo một danh sách mới có kiểu phần tử đích là `Object`. Thêm `99` vào bản sao không thêm số vào danh sách chuỗi gốc. Đây là sao chép nông: các tham chiếu phần tử được sao chép, không phải tự động sao chép sâu các đối tượng phần tử.

## 8. Những nhầm lẫn cần tránh

**“`?` chính là `Object`.”** Không. `Object` là một kiểu cụ thể; `?` che một kiểu cụ thể chưa biết. Việc đọc được dưới dạng `Object` không đồng nghĩa được ghi mọi `Object`.

**“`List<Object>` nhận mọi loại `List`.”** Không. Nó nhận danh sách có đối số kiểu phù hợp là `Object`, không nhận một biến `List<String>` chỉ vì `String` kế thừa `Object`.

**“`List<?>` chỉ đọc và bảo đảm dữ liệu không đổi.”** Không. Nó hạn chế việc truyền phần tử chưa biết kiểu; nhiều thao tác thay đổi vẫn hợp lệ, và một tham chiếu khác cũng có thể sửa cùng đối tượng.

**“Ép kiểu sang `List<Object>` là cách mở quyền ghi.”** Đừng giải quyết sự bất tương thích bằng ép kiểu không kiểm tra hoặc kiểu thô. Làm vậy có thể phá vỡ bảo đảm của danh sách mà mã khác vẫn coi là `List<String>`. Hãy sửa hợp đồng phương thức, dùng wildcard có cận phù hợp hoặc tạo bản sao đúng kiểu.

**“Nhìn phần tử đầu tiên là đủ biết kiểu của cả danh sách.”** Không. Danh sách có thể rỗng, có `null`, hoặc được khai báo chứa nhiều kiểu. Nội dung quan sát được không thay thế khai báo kiểu.

## 9. Tự kiểm tra

Cho đoạn mã minh họa sau:

```java
List<String> a = new ArrayList<>(List.of("A"));
List<?> b = a;
List<Object> c = new ArrayList<>(a);
```

Hãy dự đoán từng dòng độc lập, với trạng thái ban đầu như trên:

1. `b.add("B");`
2. `c.add("B");`
3. `b.clear();`
4. `Object item = b.get(0);`
5. `List<Object> d = b;`

Đáp án:

1. Lỗi biên dịch: không thể chọn `String` làm kiểu phần tử chưa biết.
2. Hợp lệ và thêm vào danh sách bản sao `c`; `a` không đổi.
3. Hợp lệ và làm rỗng cùng danh sách mà `a` trỏ tới.
4. Hợp lệ; ở trạng thái ban đầu, `item` tham chiếu đến chuỗi `"A"`.
5. Lỗi biên dịch: không thể coi danh sách có kiểu phần tử chưa biết là danh sách nhận mọi `Object`.

Khi chọn giữa hai kiểu, hãy hỏi: mã cần **chấp nhận một danh sách mà không quan tâm kiểu phần tử** hay cần **ghi nhiều loại đối tượng vào danh sách được khai báo chứa `Object`**? Câu hỏi thứ nhất dẫn đến `List<?>`; câu hỏi thứ hai mới phù hợp với `List<Object>`.
