# Ảnh hưởng của thay đổi biểu thức khởi tạo đến kiểu biến (`var` – Java 10+)

## 1. Mục tiêu và nguyên tắc quan trọng nhất

Với khai báo biến cục bộ `var name = expression;`, trình biên dịch Java xác định **kiểu tĩnh** của `name` từ **kiểu của biểu thức khởi tạo** `expression` ngay tại lần biên dịch đó. Vì vậy, nếu lập trình viên **sửa biểu thức khởi tạo trong mã nguồn** rồi biên dịch lại, kiểu được suy luận cho `name` có thể thay đổi, dù tên biến và từ `var` vẫn giữ nguyên.

```java
// Phiên bản A:
var amount = 100;  // amount có kiểu int

// Phiên bản B: thay dòng khai báo ở trên, không đặt cả hai cùng một khối
var amount = 100L; // amount có kiểu long
```

Đây là sự **thay đổi kiểu giữa hai phiên bản mã nguồn**. Nó **khác** với việc gán lại giá trị khi chương trình chạy:

```java
var amount = 100; // int đã được xác định
amount = 200;     // amount vẫn là int
// amount = 200L; // Lỗi: không được tự gán long vào int
```

Java tiếp tục kiểm tra kiểu tại thời điểm biên dịch; `var` **không** phải kiểu động và không “học” kiểu mới từ các phép gán về sau. Quy tắc được đưa vào Java 10 và còn áp dụng trong Java hiện đại.

Sau bài này, bạn sẽ biết dự đoán thay đổi kiểu khi chỉnh literal, toán tử, lời gọi phương thức, constructor, biểu thức điều kiện và generic; phân tích tác động tới phép gán, API, overload và khả năng đọc mã; kiểm tra an toàn khi refactor.

## 2. Cơ chế: vì sao chỉ thay vế phải có thể đổi kiểu vế trái?

Giả sử có một dòng:

```java
var result = calculate();
```

Trình biên dịch thực hiện các bước về mặt kiểu:

1. Xác định kiểu của **biểu thức khởi tạo** `calculate()`, bao gồm việc chọn overload, suy luận generic và các quy tắc của chính biểu thức.
2. Với `var`, xem biểu thức khởi tạo theo ngữ cảnh **standalone** (không có kiểu đích tường minh từ vế trái) và xác định kiểu khai báo của biến, theo các quy tắc trong Java Language Specification `14.4.
3. Kiểm tra những phép gán, phép toán, truy cập thành viên và lời gọi phương thức về sau dựa trên **kiểu tĩnh đã suy luận**.

Nếu sửa `calculate()` thành một biểu thức khác, bước 1 có thể có kết quả khác; bước 2 suy luận kiểu mới; bước 3 vì vậy có thể **biên dịch được, lỗi biên dịch hoặc chọn phương thức khác**.

**Cần phân biệt ba thứ:**

- **Biểu thức khởi tạo:** đoạn mã bên phải dấu `=` lúc khai báo, ví dụ `5 / 2`.
- **Kiểu tĩnh của biến:** kiểu mà trình biên dịch ấn định cho tên biến, ví dụ `int`.
- **Giá trị lúc chạy / lớp runtime:** kết quả thực thi và (đối với tham chiếu) lớp thực tế của đối tượng. Giá trị hoặc đối tượng có thể đổi mà kiểu tĩnh vẫn giữ nguyên.

Điểm thường bị bỏ qua: `var` có thể khiến một thay đổi nhỏ ở **vế phải** lan tác động sang nhiều dòng ở phía dưới.

## 3. Thay literal: `int`, `long`, `double`, `float`, `String`

Literal là nguồn dễ thấy nhất của kiểu suy luận.

| Phiên bản trước | Kiểu trước | Phiên bản sau | Kiểu sau | Hệ quả |
| --- | --- | --- | --- | --- |
| `var n = 1;` | `int` | `var n = 1L;` | `long` | Phạm vi số rộng hơn; overload được chọn có thể đổi. |
| `var x = 1.0;` | `double` | `var x = 1.0f;` | `float` | Độ chính xác và kiểu tham số phương thức có thể khác. |
| `var code = 65;` | `int` | `var code = 'A';` | `char` | Cùng có giá trị số liên quan nhưng kiểu tĩnh khác. |
| `var value = 42;` | `int` | `var value = "42";` | `String` | Phép cộng/so sánh và API dùng được thay đổi. |
| `var flag = true;` | `boolean` | `var flag = "true";` | `String` | Không thể dùng chuỗi thay điều kiện `if`. |
| `var data = 3;` | `int` | `var data = 3.0;` | `double` | Phép toán và kết quả chuyển đổi có thể khác. |

Những dòng trong bảng là **các phiên bản thay thế nhau**, không phải khai báo trùng tên trong một khối.

Ví dụ tác động ngay tới đoạn mã phía sau:

```java
// Phiên bản A:
var price = 100;          // int
int discounted = price - 10;

// Phiên bản B: thay khai báo, các dòng dùng price cần xem xét lại
var price = 100.0;        // double
// int discounted = price - 10; // Lỗi: kết quả double không gán ngầm cho int
double discounted = price - 10;
```

Lỗi ở phiên bản B là hệ quả của **kiểu biểu thức khởi tạo mới**. Cách sửa phụ thuộc nghiệp vụ: dùng `double`, giữ `int`, hoặc chọn cách biểu diễn số tiền phù hợp. Không tự ép kiểu thu hẹp chỉ để xóa lỗi biên dịch nếu có nguy cơ mất dữ liệu.

### Literal nguyên thủy và kiểu bao (wrapper)

```java
var count = 1;                 // int
var boxedCount = Integer.valueOf(1); // Integer
```

Thay literal bằng phương thức trả `Integer` khiến biến từ **kiểu nguyên thủy** chuyển sang **kiểu tham chiếu**. Từ đó, ví dụ `boxedCount = null;` là phép gán hợp lệ, còn `count = null;` không hợp lệ. Trường hợp unboxing một `Integer` đang bằng `null` có thể gây `NullPointerException`.

## 4. Thay biểu thức tính toán: không chỉ đổi kiểu mà có thể đổi kết quả

Kiểu của một biểu thức tính toán được xác định từ quy tắc Java cho toán tử và các toán hạng.

```java
var averageA = 5 / 2;   // int, kết quả 2
var averageB = 5.0 / 2; // double, kết quả 2.5
```

Chỉ cần thêm `.0` ở một toán hạng là **phép chia nguyên** thành **phép chia số thực**, đồng thời kiểu biến đổi từ `int` thành `double`. Điều này ảnh hưởng cả kết quả và lời gọi phương thức về sau.

```java
var totalA = 1 + 2;     // int
var totalB = 1 + 2L;    // long: numeric promotion
var text = "1" + 2;     // String, giá trị "12"
```

Ở phép cộng chuỗi, dấu `+` thực hiện nối chuỗi; việc thay một toán hạng số thành chuỗi sẽ thay **ý nghĩa** của biểu thức, không đơn thuần thay kiểu.

**Lưu ý khi dùng ép kiểu:** 

```java
var a = (long) 5;  // long
var b = (int) 5L;  // int
```

Phép ép kiểu **nằm trong initializer** là một phần quyết định kiểu suy luận. Nếu ép kiểu thu hẹp, cần xem xét giới hạn giá trị và khả năng mất dữ liệu. Để thể hiện rõ kiểu đích quan trọng, khai báo kiểu tường minh cũng là lựa chọn tốt.

## 5. Thay initializer có thể đổi overload được gọi

Java chọn overload dựa trên **kiểu tĩnh của các đối số** tại thời điểm biên dịch.

Giả sử có hai phương thức:

```java
static String display(int x)  { return "int:" + x; }
static String display(long x) { return "long:" + x; }
```

Khi khai báo:

```java
var number = 7;   // int
display(number);  // Chọn display(int)
```

Nếu **thay dòng khai báo** thành `var number = 7L;`, phép gọi `display(number)` có thể chọn `display(long)`.

Đó là một thay đổi hành vi có thể xảy ra **dù dòng gọi phương thức giữ nguyên**. Vì vậy khi thay initializer của `var`, cần kiểm tra những phương thức bị overload, biểu thức số và generic API sử dụng biến.

## 6. Thay constructor: kiểu cụ thể và khả năng gán lại thay đổi

Xem hai lựa chọn khởi tạo danh sách:

```java
// Phương án A:
var items = new java.util.ArrayList<String>(); // ArrayList<String>

// Phương án B: thay initializer A bằng biểu thức này
var items = java.util.List.<String>of();       // List<String>
```

Ở phương án A, kiểu tĩnh của `items` là **`ArrayList<String>`**. Ở phương án B, kiểu tĩnh là **`List<String>`**. Hai kiểu có thể cùng dùng được các phương thức trong interface `List`, nhưng không hoàn toàn tương đương.

**Ảnh hưởng 1 – khả năng đổi implementation:**

```java
// Phương án A, nếu items có kiểu ArrayList<String>:
// items = new java.util.LinkedList<String>(); // Lỗi: LinkedList không là ArrayList

// Phương án B, nếu items có kiểu List<String>:
items = new java.util.LinkedList<String>();    // Hợp lệ
```

**Ảnh hưởng 2 – API hiện ra qua kiểu tĩnh:** Nếu biến có kiểu interface `List<String>`, mã chỉ có thể gọi trực tiếp các thành viên được khai báo trên `List` (và các supertype của nó). Một phương thức riêng của `ArrayList` không còn sẵn trên biến đó chỉ vì runtime có thể chứa một `ArrayList`.

**Ảnh hưởng 3 – tính mutable:** `List.of(...)` trả về danh sách không cho phép chỉnh sửa bằng `add`/`remove`. `ArrayList` là cấu trúc dữ liệu cho phép chỉnh sửa. Cần xét **tính chất runtime của đối tượng** riêng với kiểu tĩnh. Việc cả hai biểu thức có thể tạo ra cùng kiểu interface **không bảo đảm** khả năng sửa nội dung giống nhau.

### Khi muốn khai báo ranh giới kiểu rõ ràng

```java
java.util.List<String> items = new java.util.ArrayList<>();
```

Kiểu khai báo vẫn là `List<String>` ngay cả khi sau này đổi initializer thành `new LinkedList<>()`. Đây là một lợi ích quan trọng của **kiểu tường minh** khi bạn muốn cam kết code chỉ phụ thuộc vào interface.

## 7. Thay constructor generic: diamond `<>` và mất target type

Một thay đổi initializer nhỏ có thể khiến kiểu generic rộng hơn ý định.

```java
var names = new java.util.ArrayList<String>(); // ArrayList<String>
```

Nếu đổi thành:

```java
var names = new java.util.ArrayList<>(); // ArrayList<Object>
```

Kiểu phần tử chuyển từ `String` sang `Object`. Vì vế trái chỉ có `var`, biểu thức `new ArrayList<>()` không nhận được target type `ArrayList<String>` hoặc `List<String>` từ khai báo. Với constructor rỗng này, trình biên dịch không có dữ kiện đủ để chọn `String`, nên suy luận `Object`.

Hậu quả:

```java
var values = new java.util.ArrayList<>();
values.add("An");
values.add(10); // Biên dịch được: values có kiểu ArrayList<Object>
```

Nếu muốn danh sách chuỗi:

```java
var names = new java.util.ArrayList<String>(); 
// Hoặc:
java.util.List<String> otherNames = new java.util.ArrayList<>();
```

Trường hợp khai báo kiểu tường minh `List<String> otherNames` cung cấp target type để diamond suy luận `String`.

### Factory method không có đối số cũng dễ suy luận quá rộng

```java
var empty = java.util.List.of();            // List<Object>
var strings = java.util.List.<String>of();  // List<String>
java.util.List<String> more = java.util.List.of();
```

Các ví dụ này biên dịch, nhưng khác kiểu phần tử. Đừng chờ đến khi gọi `add` hay sử dụng collection ở phía dưới rồi mới nghĩ kiểu generic có thể tự đổi theo dữ liệu thêm vào.

### Đừng kết luận rằng mọi biểu thức có diamond đều suy luận `Object`

```java
var names = new java.util.ArrayList<>(java.util.List.of("An"));
// ArrayList<String>: constructor nhận Collection<String>, cung cấp dữ kiện để suy luận
```

Suy luận generic phụ thuộc vào **toàn bộ biểu thức và ràng buộc kiểu**, bao gồm đối số constructor, chứ không phụ thuộc riêng vào việc có dấu `<>`.

## 8. Thay lời gọi phương thức: kiểu trả về được khai báo quyết định kiểu `var`

```java
static java.util.List<String> loadNames() {
    return new java.util.ArrayList<>(java.util.List.of("An"));
}
```

Khi gọi:

```java
var names = loadNames(); // Kiểu tĩnh: List<String>
```

Mặc dù implementation của `loadNames()` hiện trả về đối tượng `ArrayList<String>`, kiểu của biểu thức gọi phương thức là **`List<String>`** theo khai báo của phương thức. Nếu nội bộ `loadNames()` đổi sang trả `LinkedList` nhưng **chữ ký vẫn là `List<String>`**, kiểu suy luận của `names` không đổi.

Trái lại, nếu **sửa initializer** thành `new ArrayList<String>()`, biến sẽ có kiểu `ArrayList<String>`; các phép gán và thành viên sử dụng phía sau có thể thay đổi.

Khi refactor:

- Đọc **kiểu trả về khai báo** của phương thức được gọi, kể cả phương thức generic.
- Xem initializer có đang gọi một **overload khác** sau khi đổi tham số hay không.
- Đừng suy luận kiểu biến từ **lớp runtime** của đối tượng được trả về.
- Nếu kiểu trả về là một generic/wildcard phức tạp, chọn kiểu tường minh để thể hiện hợp đồng khi có ích cho người đọc.

Ví dụ lời gọi static factory:

```java
var fixed = java.util.List.of("An", "Binh"); // List<String>
var mutable = new java.util.ArrayList<String>(fixed); // ArrayList<String>
```

Hai initializer có cùng dữ liệu ban đầu nhưng khác kiểu tĩnh và khả năng thay đổi nội dung của đối tượng.

## 9. Biểu thức điều kiện và `null`: kiểu đến từ toàn biểu thức

Với toán tử ba ngôi `condition ? whenTrue : whenFalse`, trình biên dịch xác định kiểu của **biểu thức điều kiện theo quy tắc của Java**. `var` suy luận từ kiểu kết quả đó.

```java
boolean enabled = true;
var level = enabled ? 1 : 2L;      // long
var state = enabled ? "ON" : "OFF"; // String
var optional = enabled ? "ON" : null; // String
```

Một thay đổi ở một nhánh có thể làm kiểu suy luận đổi theo:

```java
var count = enabled ? 1 : 2;      // int
var countLong = enabled ? 1 : 2L; // long
```

**`var value = null;` không hợp lệ** vì literal `null` trực tiếp không có kiểu để suy luận, nhưng `var value = (String) null;` có kiểu `String`. Tương tự, biểu thức điều kiện `enabled ? "ON" : null` có kiểu `String`, nên hợp lệ với `var`.

Cần tránh kết luận kiểu của mọi biểu thức điều kiện chỉ bằng cách nhìn một nhánh. Với tham chiếu và generic phức tạp, Java có những quy tắc kết hợp kiểu (bao gồm kiểu chung tối thiểu thích hợp). Nếu kiểu chung không hiển nhiên hoặc quan trọng với API, hãy kiểm tra bằng trình biên dịch và cân nhắc kiểu khai báo tường minh.

## 10. Thay initializer đôi khi khiến `var` không còn hợp lệ

Không phải biểu thức nào cũng có kiểu thích hợp trong ngữ cảnh `var`.

### 10.1. Literal `null`

```java
var text = "Hello"; // Hợp lệ, String
// var text = null;  // Lỗi: không thể suy luận kiểu từ null
String text = null; // Hợp lệ với kiểu tường minh
```

Đây là ba **phương án thay thế nhau**, không đặt các khai báo trùng tên trong cùng khối.

### 10.2. Lambda hoặc method reference không có target type

```java
// var parser = Integer::parseInt; // Lỗi: method reference cần target type
// var parser = s -> Integer.parseInt(s); // Lỗi: lambda cần target type

java.util.function.ToIntFunction<String> parser = Integer::parseInt;
// parser.applyAsInt("42") trả về int 42
```

`var` không cung cấp kiểu functional interface cho lambda hoặc method reference độc lập. Đổi từ lời gọi một factory có kiểu rõ sang lambda/method reference trần có thể biến mã hợp lệ thành mã lỗi biên dịch.

### 10.3. Phương thức trả về `void`

```java
// var value = System.out.println("Hello"); // Lỗi: không có giá trị trả về
```

`println(...)` hợp lệ như một statement nhưng không tạo ra giá trị có kiểu dùng làm initializer cho biến. Dùng một lời gọi trả về giá trị, hoặc tách thao tác in ra thành câu lệnh riêng.

### 10.4. Array initializer trần

```java
var numbers = new int[] {1, 2, 3}; // Hợp lệ, int[]
// var numbers = {1, 2, 3};         // Lỗi: cần ngữ cảnh kiểu mảng
```

Dùng `new int[] {...}` nếu muốn `var` suy luận kiểu mảng.

### 10.5. Tự tham chiếu hoặc bỏ initializer

```java
// var next = next + 1; // Lỗi: không tự tham chiếu trong initializer
// var next;            // Lỗi: var đòi hỏi initializer
```

Việc cố sửa initializer thành một biểu thức lệ thuộc chính biến chưa khai báo không giải quyết được vấn đề; cần một giá trị nguồn đã xác định kiểu.

## 11. Kiểu mới ảnh hưởng đến những thao tác phía sau ra sao?

Sau khi sửa initializer, cần xem lại **toàn bộ phạm vi của biến**. Những thay đổi thực tế có thể gồm:

| Nơi sử dụng biến | Trước khi sửa initializer | Sau khi sửa initializer | Cần kiểm tra |
| --- | --- | --- | --- |
| Phép gán lại | `int n` nhận `int` | `long n` có thể nhận `int` và `long` | Khả năng gán và chuyển đổi ngầm. |
| Toán tử | `int` chia nguyên | `double` chia thực | Giá trị tính toán và làm tròn. |
| Overload | `f(int)` được chọn | `f(long)` có thể được chọn | Hành vi phương thức. |
| Collection | `ArrayList<String>` | `ArrayList<Object>` | Độ an toàn generic và API của phần tử. |
| Kiểu interface | `ArrayList<String>` | `List<String>` | Thành viên truy cập được, đổi implementation. |
| Tham chiếu nullable | `int` | `Integer` | Có thể gán `null`, rủi ro unboxing. |
| Null initializer | Biểu thức có kiểu | Literal `null` | Mã có còn biên dịch không? |
| Factory method | API khai báo trả `List<String>` | Constructor trả `ArrayList<String>` | Kiểu tĩnh và tính mutable. |

**Không phải lúc nào đổi initializer cũng đổi kiểu.** Chẳng hạn:

```java
var name = "An";      // String
// Thay initializer thành:
var name = "Binh";    // vẫn String
```

Hoặc:

```java
var names = java.util.List.of("An");          // List<String>
// Đổi initializer:
var names = java.util.List.copyOf(java.util.List.of("Binh")); // vẫn List<String>
```

Hai điều kiện quan trọng để đánh giá tác động là **kiểu tĩnh của biểu thức mới** và **những nơi sử dụng biến**; dữ liệu hay hình thức biểu thức thay đổi không tự động đồng nghĩa kiểu phải thay đổi.

## 12. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`InitializerTypeImpactDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class InitializerTypeImpactDemo {
    static String display(int value) {
        return "int:" + value;
    }

    static String display(long value) {
        return "long:" + value;
    }

    static List<String> loadNames() {
        return new ArrayList<>(List.of("An", "Binh"));
    }

    public static void main(String[] args) {
        var whole = 5 / 2;            // int
        var decimal = 5.0 / 2;        // double

        var small = 7;                // int
        var large = 7L;               // long

        var fixed = List.of("An", "Binh"); // List<String>
        var mutable = new ArrayList<String>(fixed); // ArrayList<String>
        mutable.add("Mai");

        var unknownType = new ArrayList<>(); // ArrayList<Object>
        unknownType.add("An");
        unknownType.add(42);

        var fromMethod = loadNames(); // List<String>
        fromMethod = new LinkedList<>(List.of("Lan"));

        var state = true ? "ready" : null; // String
        var choice = true ? 1 : 2L;        // long
        var view = (CharSequence) "abc";   // CharSequence

        System.out.println("whole=" + whole);
        System.out.println("decimal=" + decimal);
        System.out.println("small=" + display(small));
        System.out.println("large=" + display(large));
        System.out.println("fixed=" + fixed);
        System.out.println("mutable=" + mutable);
        System.out.println("unknownType=" + unknownType);
        System.out.println("fromMethod=" + fromMethod);
        System.out.println("state=" + state);
        System.out.println("choice=" + choice);
        System.out.println("viewLength=" + view.length());
    }
}
```

Lệnh trong thư mục chứa tệp (JDK 17+):

```bash
javac -encoding UTF-8 InitializerTypeImpactDemo.java
java InitializerTypeImpactDemo
```

**stdout chính xác:**

```text
whole=2
decimal=2.5
small=int:7
large=long:7
fixed=[An, Binh]
mutable=[An, Binh, Mai]
unknownType=[An, 42]
fromMethod=[Lan]
state=ready
choice=1
viewLength=3
```

### Đọc kết quả theo sự thay đổi biểu thức

- `whole` và `decimal` chỉ khác một literal `5`/`5.0` nhưng có kiểu và giá trị phép chia khác nhau.
- `small`/`large` là `int`/`long` nên gọi overload `display` khác nhau.
- `fixed` được khai báo dựa trên biểu thức factory `List.of`; `mutable` dựa trên constructor `new ArrayList<String>`; kiểu tĩnh và khả năng sửa đối tượng khác nhau.
- `unknownType` nhận cả `String` và `Integer` vì constructor diamond rỗng tạo `ArrayList<Object>`.
- `fromMethod` có kiểu `List<String>` vì đó là kiểu trả về khai báo của `loadNames()`, dù phương thức tạo `ArrayList` bên trong. Vì thế biến có thể nhận `LinkedList<String>` mới.
- `state` là `String` vì kiểu toàn bộ biểu thức điều kiện là `String`; `choice` là `long` vì biểu thức số phối hợp `int` và `long`.
- `view` có kiểu tĩnh `CharSequence` do cast ở initializer; các phương thức sử dụng được được kiểm tra trên `CharSequence`.

## 13. Chiến lược refactor an toàn

Trước khi đổi initializer của một khai báo `var`:

1. **Ghi nhận kiểu cũ.** Dùng thông tin kiểu của IDE hoặc đọc kiểu của toàn bộ biểu thức theo JLS; với generic, xem đủ tham số kiểu.
2. **Xác định kiểu mới trước khi sửa các dòng khác.** Kiểm tra literal, phép toán, constructor, tham số generic, factory hoặc chữ ký phương thức.
3. **Xem mọi nơi biến được sử dụng.** Đặc biệt là phép gán lại, lời gọi overload, thao tác chỉ có ở lớp con, phép toán số, phương thức generic và truy cập member.
4. **Chạy biên dịch và test có ý nghĩa.** Một số thay đổi gây lỗi biên dịch; một số vẫn biên dịch nhưng đổi hành vi, như chia nguyên sang chia thực hoặc phương thức overload khác.
5. **Đảm bảo ý định kiểu rõ ràng khi review.** Nếu refactor thường xuyên đổi implementation hoặc kiểu là hợp đồng quan trọng, cân nhắc viết kiểu tường minh.
6. **Chỉ thêm ép kiểu khi có lý do nghiệp vụ.** Ép kiểu để “giữ nguyên kiểu cũ” có thể che mất chuyển đổi dữ liệu hoặc làm mất độ chính xác.

### Minh họa trước–sau: giữ hợp đồng interface

Trước:

```java
var data = new java.util.ArrayList<String>(); // ArrayList<String>
// data = new java.util.LinkedList<String>();  // lỗi biên dịch
```

Sau, nếu chủ đích là thay được implementation:

```java
java.util.List<String> data = new java.util.ArrayList<>();
data = new java.util.LinkedList<>(); // hợp lệ
```

Khi đổi `ArrayList` sang `LinkedList`, khai báo tường minh `List<String>` giúp hợp đồng kiểu vẫn ổn định. Không cần cố viết `var data = (List<String>) new ArrayList<String>();` nếu kiểu tường minh diễn đạt ý định rõ hơn.

### Minh họa trước–sau: giữ tính toán số nguyên

Nếu phép chia nguyên là chủ đích:

```java
var pageCount = 5 / 2; // int, giá trị 2
```

Nếu muốn kết quả thập phân:

```java
var average = 5.0 / 2; // double, giá trị 2.5
```

Hãy thay mã theo yêu cầu nghiệp vụ cụ thể, vì lựa chọn kiểu trực tiếp tác động giá trị tính toán.

## 14. Bài tập tự kiểm tra

Mỗi đoạn là một phương án **độc lập**, không chạy đồng thời các khai báo trùng tên.

**Câu 1.** `var x = 1;` chuyển thành `var x = 1L;` thì kiểu thay đổi thế nào? `x = 2;` còn hợp lệ không?

**Câu 2.** `var p = 4 / 2;` chuyển thành `var p = 4.0 / 2;` thì kiểu và giá trị `p` thay đổi thế nào?

**Câu 3.** Kiểu `items` của `var items = new ArrayList<>();` là gì (giả sử đã import `ArrayList`)? Nếu thay bằng `new ArrayList<String>()`, điều gì thay đổi?

**Câu 4.** Với phương thức `List<String> loadNames()`, `var names = loadNames();` có kiểu gì? Nếu bên trong phương thức đổi `new ArrayList<>()` thành `new LinkedList<>()` mà chữ ký giữ nguyên, kiểu `names` có đổi không?

**Câu 5.** Tại sao `var value = "42";` và `var value = 42;` không dùng được thay thế tùy ý ở các phép toán?

**Câu 6.** `var action = () -> System.out.println("Hi");` có hợp lệ không? Cách sửa?

**Câu 7.** Khi sửa `var something = List.of("A");` thành `var something = new ArrayList<String>(List.of("A"));`, bạn cần xem lại những gì ngoài tên kiểu?

**Đáp án:**

1. Từ `int` sang `long`. `x = 2;` vẫn hợp lệ vì `int` chuyển sang `long` khi gán.
2. Từ `int` với giá trị `2` sang `double` với giá trị `2.0`; kiểu thay đổi dù giá trị biểu diễn có thể cùng ý nghĩa số học trong ví dụ này.
3. `new ArrayList<>()` trong ngữ cảnh `var` và không có đối số được suy luận là `ArrayList<Object>`; `new ArrayList<String>()` cho `ArrayList<String>`, tăng kiểm tra kiểu phần tử.
4. `List<String>`. Không đổi khi chỉ thay implementation trong thân phương thức mà chữ ký trả về vẫn là `List<String>`.
5. `"42"` là `String`, `42` là `int`; toán tử và phương thức áp dụng khác nhau, có thể khác kết quả hoặc lỗi biên dịch.
6. Không hợp lệ vì lambda thiếu target type. Ví dụ `Runnable action = () -> System.out.println("Hi");`.
7. Kiểu tĩnh từ `List<String>` thành `ArrayList<String>`; đối tượng từ danh sách không sửa được thành danh sách cho sửa được; kiểm tra API, phép gán, logic phụ thuộc tính mutable và test.

## 15. Tóm tắt và nguồn tham khảo đang còn hiệu lực

- Khi dùng `var`, **kiểu biến phụ thuộc vào toàn bộ kiểu của initializer** ở lần biên dịch hiện tại.
- **Sửa initializer trong mã nguồn** có thể đổi kiểu sau khi biên dịch lại; **gán lại giá trị lúc chạy** không khiến biến đổi kiểu.
- Literal, phép toán, cast, lời gọi phương thức, constructor, generic, diamond `<>` và biểu thức điều kiện đều có thể ảnh hưởng kiểu suy luận.
- Đổi initializer có thể tác động đến **overload, kiểm tra gán, độ chính xác số, API khả dụng, generic type và hành vi runtime**.
- `var` không có target type tường minh ở vế trái; để giữ hợp đồng kiểu khi thay implementation, đôi khi dùng kiểu tường minh là lựa chọn dễ bảo trì hơn.

Tài liệu chính thức:

- [Java Language Specification SE 26 – `14.4 Local Variable Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.4): suy luận kiểu `var` từ initializer theo standalone expression.
- [Java Language Specification SE 26 – `15.2 Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.2): biểu thức và ngữ cảnh kiểu.
- [Java Language Specification SE 26 – `15.25 Conditional Operator](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.25): kiểu của biểu thức điều kiện.
- [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế `var` từ Java 10.
- [OpenJDK Project Amber – Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): cân bằng giữa suy luận kiểu và khả năng đọc mã.
