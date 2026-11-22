# Đọc kiểu suy luận bằng công cụ biên dịch và IDE (Java 10+)

*Chủ đề cha: Nền tảng `var`. Các kỹ thuật trong bài sử dụng trình biên dịch `javac`, `javap`, JShell và IDE vẫn hữu ích với Java hiện đại; chương trình chạy được biên dịch theo Java 17 trở lên.*

## 1. Mục tiêu và bản chất của việc “đọc kiểu suy luận”

Sau bài học, bạn có thể:

1. Xác định **kiểu tại thời điểm biên dịch** của biến khai báo bằng `var`.
2. Dùng **IDE** để xem kiểu đã được suy ra, kể cả tham số kiểu generic.
3. Dùng **`javac`** và thông báo lỗi kiểu để xác nhận cách trình biên dịch hiểu một biểu thức.
4. Dùng **JShell `/vars`** để thử nhanh kiểu của các khai báo đơn giản.
5. Dùng **`javap`** kiểm tra thông tin kiểu trong bytecode và bảng debug, đồng thời hiểu giới hạn của cách kiểm tra này.
6. Nhận biết những trường hợp kiểu suy ra khác ý định của người viết và chọn giữa `var` với kiểu tường minh.

Trong Java, `var` là **suy luận kiểu biến cục bộ (local variable type inference)**, xuất hiện từ Java 10. Trình biên dịch suy ra **một kiểu tĩnh** từ biểu thức khởi tạo. Kiểu đó không đổi khi chương trình chạy; Java vẫn kiểm tra phép gán, truy cập thành viên và lời gọi phương thức theo hệ kiểu tĩnh.

Ví dụ:

```java
var amount = 15;                    // int
var label = "Java";                 // String
var languages = java.util.List.of("Java", "Kotlin"); // List<String>
// amount = "mười lăm";             // Lỗi biên dịch: String không thể gán cho int
```

**Ba câu hỏi khác nhau cần phân biệt:**

- *Kiểu tĩnh của biến là gì?* Ví dụ `List<String>`. IDE, compiler và thông tin debug (nếu có) có thể giúp trả lời.
- *Lớp thực tế của đối tượng đang được tham chiếu là gì?* Ví dụ lớp triển khai cụ thể của danh sách, có thể xem bằng `getClass()` khi đối tượng không phải `null`.
- *Giá trị hiện tại của biến là gì?* Ví dụ `["Java", "Kotlin"]`, xem trong debugger khi chương trình tạm dừng.

Không dùng `getClass()` để kết luận kiểu tĩnh hoặc tham số generic. Ví dụ `List<String>` và `List<Integer>` có thể được triển khai bằng cùng một lớp runtime do cơ chế **type erasure**.

## 2. Chương trình mẫu để quan sát kiểu

Tạo tệp **`TypeInferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class TypeInferenceDemo {
    public static void main(String[] args) {
        var count = 4;
        var topics = List.of("Java", "JVM");
        var scores = new ArrayList<Integer>(List.of(7, 8, 9));
        var total = scores.stream()
                .mapToInt(Integer::intValue)
                .sum();
        var mean = scores.stream()
                .mapToInt(Integer::intValue)
                .average()
                .orElse(0.0);

        System.out.println("count=" + count);
        System.out.println("topics=" + topics);
        System.out.println("scores=" + scores);
        System.out.println("total=" + total);
        System.out.println("mean=" + mean);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 TypeInferenceDemo.java
java TypeInferenceDemo
```

Kết quả chuẩn:

```text
count=4
topics=[Java, JVM]
scores=[7, 8, 9]
total=24
mean=8.0
```

Những kiểu cần tìm bằng công cụ:

| Biến | Biểu thức khởi tạo | Kiểu tĩnh suy luận |
| --- | --- | --- |
| `count` | `4` | `int` |
| `topics` | `List.of("Java", "JVM")` | `List<String>` |
| `scores` | `new ArrayList<Integer>(...)` | `ArrayList<Integer>` |
| `total` | `IntStream.sum()` | `int` |
| `mean` | `OptionalDouble.orElse(0.0)` | `double` |

`var` không thay đổi kiểu trả về của API. `sum()` trên `IntStream` trả `int`; `orElse(0.0)` trên `OptionalDouble` trả `double`. Suy luận kiểu dựa vào chữ ký API và kiểu của biểu thức, không dựa vào việc ứng dụng đang in ra giá trị gì.

## 3. Xem kiểu trong IDE: cách nhanh nhất khi đang viết mã

IDE hiện đại phân tích mã bằng ngôn ngữ Java tương ứng với JDK và cấu hình dự án. Với tệp mẫu đang mở:

1. Đặt con trỏ trên **tên biến** `topics`, `scores`, `total` hoặc `mean` (không chỉ nhìn chữ `var`). Mở thông tin kiểu bằng chức năng **hover / Quick Info / Show Type / Type Information** mà IDE cung cấp.
2. Quan sát kiểu hiển thị, nhất là generic như `List<String>` và `ArrayList<Integer>`. Kiểm tra cả **kiểu của biểu thức khởi tạo**, chẳng hạn `List.of(...)`, nếu cần xác định nguồn suy luận.
3. Bật **inlay hints / type hints** cho biến cục bộ nếu IDE có tùy chọn đó. Gợi ý có thể xuất hiện bên cạnh `var` hoặc tên biến, giúp tránh phải hover liên tục.
4. Thử thay `var` bằng **kiểu tường minh** do IDE đề xuất trong refactoring/quick fix, nếu tính năng này có mặt. Đọc bản thay thế trước khi áp dụng: thay đổi kiểu khai báo có thể ảnh hưởng các lời gọi tiếp theo, đặc biệt khi muốn cố ý khai báo theo interface.
5. Chạy build bằng cùng phiên bản Java/language level với dự án để xác nhận IDE và `javac` cùng chấp nhận kiểu đó.

Các ví dụ thao tác phổ biến (tên menu và phím tắt tùy phiên bản/cấu hình):

- **IntelliJ IDEA:** hover hoặc dùng chức năng hiển thị kiểu biểu thức/quick documentation; kiểm tra phần Java **inlay hints** và các gợi ý thay `var` bằng kiểu cụ thể.
- **Eclipse IDE (JDT):** hover lên biến và xem Java type information; có thể dùng công cụ điều hướng/inspection để kiểm tra declaration, generic và kiểu trả về phương thức.
- **Visual Studio Code:** cài Java language support có trình phân tích Java, hover lên tên biến để đọc kiểu; bật các **inlay hints** hỗ trợ bởi Java extension nếu muốn hiện ngay trong editor.

**Không lấy ảnh chụp giá trị debugger làm bằng chứng về kiểu suy luận.** Debugger cho biết giá trị và lớp runtime, trong khi hệ thống phân tích mã của IDE mới trả lời câu hỏi “trình biên dịch hiểu biến này có kiểu gì?”. Một trình soạn thảo chưa tải dự án Java hoặc dùng sai language level có thể hiển thị gợi ý thiếu/chưa chính xác; lúc đó hãy đồng bộ cấu hình JDK và chạy `javac`.

### 3.1. Kiểm tra sự khác nhau giữa kiểu suy luận và kiểu khai báo tường minh

Xem hai khai báo sau:

```java
// Đoạn minh họa bên trong một phương thức:
var one = new ArrayList<String>();
List<String> two = new ArrayList<>();
```

IDE thường cho thấy:

- `one` có kiểu tĩnh **`ArrayList<String>`** vì kiểu được suy ra từ `new ArrayList<String>()`.
- `two` có kiểu tĩnh **`List<String>`** do bạn chủ động khai báo theo interface, dù đối tượng tạo ra cũng là `ArrayList`.

Khi API muốn giấu chi tiết triển khai, kiểu tường minh như `List<String>` có thể truyền đạt hợp đồng rõ hơn. Dùng `var` khi kiểu suy luận đã rõ và là kiểu bạn muốn người đọc dựa vào.

## 4. Hỏi `javac` bằng lỗi biên dịch có chủ đích

### 4.1. `javac` kiểm tra kiểu nhưng không có lệnh chuẩn để liệt kê mọi kiểu `var`

Nếu code đúng, `javac` thường không in ra tên kiểu suy luận. Cách kiểm tra hữu ích khi đang học hoặc sửa lỗi là cố ý viết thao tác sai kiểu và xem compiler phản hồi. Hãy tách phép thử lỗi ra khỏi chương trình đang chạy tốt.

Tạo tệp **`BadInference.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class BadInference {
    public static void main(String[] args) {
        var quantity = 10;
        quantity = "10";                 // Sai: quantity là int

        var names = List.of("An", "Binh");
        names.add(42);                   // Sai: names là List<String>

        var items = new ArrayList<>();   // Suy luận ArrayList<Object>
        items.add("Java");               // Hợp lệ: String là Object
        String first = items.get(0);     // Sai: get trả Object
    }
}
```

Biên dịch để quan sát chẩn đoán:

```bash
javac --release 17 -Xdiags:verbose BadInference.java
```

**Đây là chương trình cố ý không biên dịch được**, nên không có lệnh `java BadInference` hay stdout. Chẩn đoán có thể khác câu chữ theo JDK, nhưng phải thể hiện các ràng buộc sau:

1. `quantity` là `int` nên không thể gán `String`.
2. `names.add(42)` không nhận `int` như một phần tử `String`.
3. `items.get(0)` có kiểu tĩnh `Object` nên không thể gán trực tiếp vào `String`.

Cờ `-Xdiags:verbose` yêu cầu thông tin chẩn đoán chi tiết hơn trong `javac` của OpenJDK hiện đại; cách trình bày cụ thể có thể thay đổi. Không phụ thuộc việc thông báo lỗi in nguyên chữ “inferred type”. Ý nghĩa của lỗi nằm ở **kiểu nguồn, kiểu đích, chữ ký phương thức và tham số generic**.

### 4.2. Bắt lỗi tại ranh giới phương thức để hiểu generic

Một kỹ thuật dễ đọc hơn việc gán sai tùy tiện là viết hàm có tham số kiểu rõ ràng:

```java
// Đoạn minh họa bên trong cùng một lớp:
static void acceptStrings(List<String> values) {
    System.out.println(values.size());
}

static void check() {
    var names = List.of("A", "B");
    acceptStrings(names); // Hợp lệ: names là List<String>

    var unknown = new ArrayList<>();
    // acceptStrings(unknown); // Lỗi: ArrayList<Object> không phải List<String>
}
```

Dòng đã chú thích sẽ lỗi nếu bỏ dấu chú thích. Đây là cách xác nhận một API yêu cầu kiểu gì trong thực tế. Đừng “sửa” bằng ép kiểu không an toàn chỉ để biên dịch qua; hãy xác định đúng kiểu phần tử ngay khi tạo collection:

```java
var known = new ArrayList<String>();
acceptStrings(known); // Hợp lệ
```

Hai đoạn trên **minh họa code trong lớp/phương thức** và không phải hai tệp Java độc lập. Chúng làm rõ ảnh hưởng của suy luận kiểu đến cách dùng API.

## 5. Thử nhanh kiểu trong JShell bằng `/vars`

**JShell** là công cụ REPL đi kèm JDK hiện đại, thích hợp kiểm tra các biểu thức nhỏ mà không cần tạo tệp Java. Khởi động từ terminal:

```bash
jshell
```

Nhập lần lượt các dòng sau trong JShell (không nhập dấu nhắc `jshell>`):

```java
var count = 4;
var topics = java.util.List.of("Java", "JVM");
var scores = new java.util.ArrayList<Integer>();
var empty = new java.util.ArrayList<>();
```

Sau đó nhập **lệnh JShell**, không phải câu lệnh Java:

```text
/vars
```

`/vars` liệt kê các biến JShell, kiểu và giá trị của chúng. Bạn cần quan sát các kiểu tương ứng:

```text
count   -> int
topics  -> java.util.List<String> hoặc List<String>
scores  -> java.util.ArrayList<Integer> hoặc ArrayList<Integer>
empty   -> java.util.ArrayList<Object> hoặc ArrayList<Object>
```

Phần trên là **diễn giải kiểu mong đợi**, không phải transcript stdout bắt buộc; cách rút gọn tên package và định dạng của JShell phụ thuộc phiên bản/feedback mode.

Thử tiếp:

```java
count = "four";
```

JShell từ chối phép gán vì `count` đã có kiểu `int`. Sau đó gõ `/vars` để thấy biến vẫn giữ kiểu tĩnh ban đầu. Dùng `/exit` để thoát.

**Giới hạn của JShell:** `/vars` liệt kê các biến khai báo ở phạm vi phiên JShell; nó không thay cho việc phân tích mọi biến cục bộ sâu bên trong một method, lambda hay ứng dụng lớn. Trường hợp đó, dùng IDE hoặc `javac` trên đúng mã nguồn dự án.

## 6. Kiểm tra bytecode với `javap` và hiểu giới hạn thông tin debug

### 6.1. `javap` quan sát gì?

`javac` chuyển nguồn `.java` thành bytecode `.class`. Với một lớp có thông tin debug, công cụ `javap` có thể hiển thị:

- **LocalVariableTable:** tên biến, phạm vi tồn tại theo bytecode, vị trí slot và biểu diễn kiểu JVM (descriptor) của biến cục bộ.
- **LocalVariableTypeTable:** thông tin chữ ký generic của một số biến, nếu được ghi vào class file.
- **LineNumberTable:** ánh xạ giữa bytecode và dòng mã nguồn.
- Bytecode trong thân phương thức, khi dùng `-c` hoặc `-v`.

Để quan sát chương trình mẫu, biên dịch lại có debug information:

```bash
javac --release 17 -g TypeInferenceDemo.java
javap -v -l TypeInferenceDemo
```

Trong kết quả, tìm tên `main`, phần **LocalVariableTable** và **LocalVariableTypeTable**. Các kiểu đặc trưng có thể xuất hiện:

| Biến | Descriptor JVM / thông tin kiểu | Cách hiểu |
| --- | --- | --- |
| `count`, `total` | `I` | `int` |
| `mean` | `D` | `double` |
| `topics` | `Ljava/util/List;` | `List` sau khi xóa tham số generic |
| `scores` | `Ljava/util/ArrayList;` | `ArrayList` sau khi xóa tham số generic |
| `topics` (generic signature nếu có) | `Ljava/util/List<Ljava/lang/String;>;` | `List<String>` |

Với `scores`, chữ ký generic nếu có tương ứng `ArrayList<Integer>`. Kết quả `javap` thực tế chứa thêm chỉ số constant pool, offset bytecode và thông tin của các biến khác, vì vậy không nên học thuộc bố cục từng dòng. `javap -c -l TypeInferenceDemo` phù hợp nếu muốn xem mã lệnh và bảng biến ngắn gọn hơn.

**Giới hạn rất quan trọng:**

1. **Bytecode không đánh dấu một biến từng được viết bằng `var` hay bằng tên kiểu tường minh.** Ví dụ `var count = 4;` và `int count = 4;` có thể cho kết quả thực thi và thông tin kiểu tương đương.
2. **Generic bị type erasure.** Descriptor `Ljava/util/List;` tự nó không thể cho biết danh sách là `List<String>`. Chữ ký generic có thể được ghi trong debug metadata nhưng không phải bằng chứng rằng runtime lưu tham số kiểu trên từng đối tượng.
3. **Bảng biến cục bộ phụ thuộc cách biên dịch.** Nếu không có debug symbols tương ứng, `LocalVariableTable` hoặc `LocalVariableTypeTable` có thể vắng mặt. Dùng `-g` khi tự tạo tệp thử nghiệm; không kết luận thiếu biến trong mã nguồn chỉ vì không thấy tên trong một tệp `.class` khác.
4. Bytecode không phải công cụ tiện nhất để học suy luận kiểu hằng ngày. IDE và lỗi `javac` thường trực tiếp hơn; `javap` hữu ích khi cần hiểu chính xác phần thông tin nào sống sót sau biên dịch.

### 6.2. Vì sao `getClass()` không thay được `javac` hay IDE?

Xét:

```java
List<String> asInterface = new ArrayList<>();
var asConcrete = new ArrayList<String>();
```

Cả hai có thể trả cùng kết quả từ `getClass()` vì đều tham chiếu đối tượng `ArrayList`. Tuy nhiên kiểu tĩnh là **`List<String>`** cho `asInterface` và **`ArrayList<String>`** cho `asConcrete`. Class runtime cũng không trả về tham số generic `String` của một đối tượng `ArrayList` thông thường. Vì vậy chọn công cụ theo thông tin cần chứng minh: IDE/`javac` cho kiểu tĩnh, debugger và `getClass()` cho đối tượng runtime, `javap` cho biểu diễn sau biên dịch.

## 7. Các mẫu suy luận dễ gây hiểu nhầm

Bảng dưới đây nêu những trường hợp nên kiểm tra bằng hover, JShell và phép gán thử được biên dịch:

| Khai báo | Kiểu được suy ra / kết quả | Vì sao |
| --- | --- | --- |
| `var x = 3;` | `int` | Literal số nguyên mặc định |
| `var x = 3L;` | `long` | Hậu tố `L` |
| `var p = 2.5;` | `double` | Literal số thực mặc định |
| `var text = "Java";` | `String` | Literal chuỗi |
| `var names = List.of("A", "B");` | `List<String>` | Type inference của phương thức generic `List.of` |
| `var values = new ArrayList<String>();` | `ArrayList<String>` | Kiểu phần tử chỉ rõ trong constructor |
| `var values = new ArrayList<>();` | `ArrayList<Object>` | Không có ngữ cảnh đích yêu cầu phần tử cụ thể |
| `var values = List.of();` | `List<Object>` | Không có phần tử để suy ra kiểu hẹp hơn |
| `var size = List.of("A").size();` | `int` | Kiểu trả về của `size()` |
| `var result = true ? 1 : 2.5;` | `double` | Quy tắc kiểu của toán tử điều kiện số |

**Điểm then chốt:** biểu thức khởi tạo được phân tích theo quy tắc Java; `var` chỉ nhận kết quả suy luận. Người đọc không nên nhìn giá trị một lần chạy rồi đoán kiểu.

### 7.1. Những khai báo không hợp lệ

```java
// Tất cả đều cố ý sai; chỉ dùng để nhận diện lỗi:
var x = null;            // Không có kiểu suy luận từ null
var y;                   // Thiếu initializer
var z = {1, 2, 3};       // Array initializer trần cần ngữ cảnh kiểu
var f = value -> value;  // Lambda thiếu target functional interface
```

Cách viết hợp lệ tương ứng:

```java
String x = null;
var z = new int[] {1, 2, 3};
java.util.function.Function<String, String> f = value -> value;
```

Đây là các **đoạn minh họa khai báo**, không phải chương trình Java độc lập. Với lambda, nếu muốn dùng `var`, phải cung cấp ngữ cảnh kiểu của functional interface qua một biểu thức thích hợp; cách tường minh thường dễ đọc hơn. `var` dùng cho biến cục bộ có initializer (và những vị trí hỗ trợ của cú pháp Java), không dùng thay kiểu trả về, kiểu field hoặc tham số của phương thức thông thường.

### 7.2. Đừng nhầm kiểu với tính mutable, nullability hoặc đa hình

- `var names = List.of("An");` có kiểu `List<String>`, nhưng danh sách do `List.of` tạo ra **không cho phép sửa**. Kiểu `List<String>` không tự khẳng định collection có mutable hay không.
- `var maybeName = methodReturningNullableString();` vẫn có kiểu `String` dù giá trị ở runtime có thể là `null`. Nullability cần được phân tích bằng hợp đồng API và kiểm tra phù hợp.
- `var animal = new Dog();` suy ra kiểu `Dog` nếu `Dog` là lớp của biểu thức `new`. Viết `Animal animal = new Dog();` sẽ có kiểu tĩnh `Animal` và vẫn có đối tượng thực tế là `Dog`. Điều này ảnh hưởng thành viên nào có thể gọi được ở compile time.

## 8. Quy trình xử lý một trường hợp suy luận khó

Khi IDE báo lỗi ở biến `var` hoặc code generic không biên dịch được, làm theo thứ tự:

1. **Đọc biểu thức khởi tạo:** nó là literal, constructor, generic factory, method call, lambda hay toán tử điều kiện?
2. **Hover tên biến và biểu thức** trong IDE; ghi lại kiểu đầy đủ, gồm `<T>`, wildcard và array nếu có.
3. **Xem chữ ký phương thức nguồn** bằng điều hướng IDE hoặc Java API: `List.of`, `stream`, `map`, `sum`, `toList`... trả kiểu gì?
4. **Chạy `javac`** với cấu hình Java phù hợp; nếu xảy ra lỗi, dùng `-Xdiags:verbose` để thấy kiểu nguồn/đích hoặc tham số generic mâu thuẫn.
5. **Rút gọn biểu thức trong JShell** và xem `/vars` nếu muốn thử nhanh một initializer độc lập.
6. Chỉ **dùng `javap`** khi cần biết bảng biến, generic signature hoặc bytecode chứa gì; hãy biên dịch có `-g` trong thí nghiệm của mình.
7. **Quyết định cách viết rõ hơn:** giữ `var` nếu suy luận hiển nhiên; ghi kiểu tường minh nếu cần khóa hợp đồng ở interface/generic hoặc tránh `Object` bị suy luận ngoài ý muốn.

Ví dụ cần sửa:

```java
// Khai báo sau có kiểu ArrayList<Object>:
var labels = new ArrayList<>();
labels.add("A");
// String first = labels.get(0);  // Lỗi biên dịch: Object -> String

// Sửa tại nguồn suy luận:
var typedLabels = new ArrayList<String>();
typedLabels.add("A");
String first = typedLabels.get(0); // Hợp lệ
```

Đừng ép kiểu `(String) labels.get(0)` để che đi việc thiếu ràng buộc generic. Sửa kiểu phần tử ở nơi tạo danh sách làm cho các thao tác tiếp theo được kiểm tra đúng từ đầu.

## 9. Bài tự thực hành có kiểm chứng

1. Mở `TypeInferenceDemo.java` trong IDE, ghi kiểu mà IDE hiển thị cho năm biến `count`, `topics`, `scores`, `total` và `mean`. Đối chiếu bảng ở mục 2.
2. Chạy `javac --release 17 TypeInferenceDemo.java` và `java TypeInferenceDemo`. So sánh stdout đúng năm dòng đã nêu.
3. Biên dịch `BadInference.java` với `-Xdiags:verbose`. Với mỗi lỗi, chỉ ra kiểu **nguồn**, kiểu **đích** hoặc tham số generic bị sai. Chương trình lỗi không chạy được là kết quả dự kiến.
4. Mở `jshell`, khai báo `var items = new java.util.ArrayList<>();`, sau đó dùng `/vars`. Kiểm tra vì sao kiểu phần tử là `Object`.
5. Biên dịch lại chương trình mẫu bằng `-g` và xem `javap -v -l TypeInferenceDemo`. Tìm descriptor `I`, `D`, `Ljava/util/List;` và generic signature khi có. Giải thích vì sao metadata này **không cho biết** nguồn viết `var` hay tên kiểu.
6. Thử thay `var scores` bằng `List<Integer> scores` (giữ nguyên initializer). Chương trình vẫn có thể chạy giống nhau, nhưng IDE sẽ báo kiểu **biến** khác: `List<Integer>` thay vì `ArrayList<Integer>`.

**Tiêu chí nắm vững:** tự trả lời được “kiểu tĩnh của biến là gì, tại sao trình biên dịch suy ra kiểu đó, và công cụ nào chứng minh được điều gì?” trước khi dựa vào giá trị runtime. Đây là kỹ năng nền giúp dùng `var` đúng, đọc API generic dễ hơn và sửa lỗi biên dịch Java nhanh hơn.