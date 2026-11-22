# Quan hệ giữa `var`, suy luận kiểu và khả năng đọc mã (Java 10+)

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `var` giúp trình biên dịch suy luận kiểu nhưng Java vẫn là ngôn ngữ **kiểu tĩnh**.
- Dự đoán kiểu thật của biến được khai báo bằng `var`, nhất là với kiểu nguyên thủy, collection và generic.
- Phân biệt đoạn mã ngắn hơn với đoạn mã **dễ đọc và dễ bảo trì hơn**; chọn `var` hoặc kiểu tường minh theo ngữ cảnh.
- Nhận ra các khai báo không hợp lệ, vấn đề mất kiểu đích (target type) và rủi ro khi refactor.

**Phạm vi:** `var` cho biến cục bộ được giới thiệu từ Java 10 và tiếp tục được hỗ trợ trong Java hiện đại. Bài chỉ trình bày các quy tắc và thực hành còn áp dụng; ví dụ chạy độc lập dùng Java 17+.

## 2. Ba khái niệm liên hệ với nhau như thế nào?

**`var` là một cách viết khai báo**; **suy luận kiểu (type inference) là việc của trình biên dịch**; **khả năng đọc mã (readability) là trải nghiệm của người đọc**. Ba khái niệm có liên quan nhưng không đồng nghĩa:

1. Khi thấy `var tênBiến = biểuThức;`, trình biên dịch xác định kiểu của biểu thức khởi tạo và dùng kiểu suy luận được làm kiểu tĩnh của biến.
2. Sau khai báo, kiểm tra kiểu, truy cập phương thức, khả năng gán lại và báo lỗi biên dịch diễn ra như khi bạn viết kiểu đó tường minh.
3. Người đọc không nhìn thấy trực tiếp kiểu bên trái; họ cần suy ra từ **tên biến, biểu thức bên phải và ngữ cảnh gần đó**. Nếu các tín hiệu rõ ràng, `var` giảm sự lặp; nếu mơ hồ, `var` làm tăng công sức đọc.

Ví dụ hai khai báo dưới có cùng kiểu tĩnh và cùng ý nghĩa:

```java
String greeting = "Xin chào";
var greeting2 = "Xin chào";   // trình biên dịch suy luận String
```

`var` **không** có nghĩa “biến nhận mọi kiểu như `var` trong JavaScript”, không hoãn quyết định kiểu đến thời gian chạy, cũng không có nghĩa kiểu mặc định là `Object`.

```java
var quantity = 10;  // int
quantity = 20;      // hợp lệ
// quantity = "20"; // LỖI BIÊN DỊCH: String không gán được cho int
```

> Câu hỏi đúng khi review không phải “Có dùng được `var` không?” mà là “Người đọc có nhận ra **giá trị, kiểu và vai trò** của biến nhanh hơn không?”.

## 3. Trình biên dịch suy luận kiểu từ đâu?

Với biến cục bộ khai báo bằng `var`, trình biên dịch tính kiểu của **biểu thức khởi tạo** như một biểu thức độc lập (*standalone expression*) rồi xác định kiểu của biến. Những phép gán về sau **không khiến kiểu ban đầu đổi theo**.

| Khai báo | Kiểu được suy luận | Lý do |
| --- | --- | --- |
| `var index = 0;` | `int` | Literal nguyên không có hậu tố mặc định là `int`. |
| `var limit = 100L;` | `long` | Hậu tố `L` biểu thị `long`. |
| `var ratio = 0.5;` | `double` | Literal thực mặc định là `double`. |
| `var active = true;` | `boolean` | Kiểu rõ từ literal. |
| `var title = "Java";` | `String` | Biểu thức chuỗi. |
| `var length = title.length();` | `int` | `String.length()` trả về `int`. |
| `var names = java.util.List.of("Lan", "An");` | `List<String>` | Các đối số cho phép suy luận tham số generic. |
| `var names = new java.util.ArrayList<String>();` | `ArrayList<String>` | Kiểu của biểu thức `new` là lớp cụ thể. |

Bảng trên gồm các ví dụ độc lập về mặt khai báo; những tên bị lặp nằm trong **các ngữ cảnh riêng**. Đây là suy luận kiểu của **biến cục bộ**, khác với suy luận tham số generic ở toán tử `<>` hoặc ở lời gọi phương thức generic, dù các cơ chế có tương tác với nhau.

Hai hệ quả quan trọng:

- **Kiểu suy luận là kiểu thực của biểu thức**, không tự động là interface bạn có thể muốn. `var list = new ArrayList<String>();` có kiểu `ArrayList<String>`, trong khi `List<String> list = new ArrayList<>();` có kiểu khai báo `List<String>`.
- **Không còn kiểu đích tường minh ở vế trái** để hỗ trợ một số suy luận generic. Vì vậy thay kiểu tường minh bằng `var` đôi khi làm **thay đổi** kiểu được suy luận, chứ không chỉ rút ngắn cú pháp.

### Kiểu suy luận không đổi sau lần gán đầu

```java
var message = "ready"; // String
message = "done";      // được
// message = 42;       // sai kiểu, không biên dịch
```

Ngay cả khi một phương thức được gọi trong biểu thức khởi tạo có thể trả về `null` lúc chạy, kiểu khai báo vẫn cố định: `var value = map.get("missing");` lấy **kiểu trả về** của `get`, chứ không suy luận kiểu “null”.

## 4. `var` được phép và không được phép ở đâu?

`var` là **tên kiểu được dành riêng** (*reserved type name*) trong những vị trí khai báo phù hợp, không phải từ khóa thay thế mọi kiểu của Java.

**Dùng được (Java 10+):**

- Biến cục bộ trong thân phương thức/khối lệnh, kèm biểu thức khởi tạo: `var userName = "Lan";`.
- Biến khởi tạo trong vòng `for` cơ bản: `for (var i = 0; i < 3; i++)`.
- Biến duyệt trong enhanced `for`: `for (var name : names)`.
- Biến tài nguyên trong `try-with-resources`: `try (var reader = Files.newBufferedReader(path)) { ... }`, với biểu thức cho ra kiểu phù hợp làm tài nguyên.
- Biến cục bộ `final`: `final var count = 3;`. `final` cấm gán lại biến, **không** mặc nhiên khiến đối tượng có thể thay đổi trở thành bất biến.

**Không dùng được trong các trường hợp sau** (các ví dụ được cố ý ghi là sai và không phải chương trình chạy độc lập):

```java
// var missing;                    // Không có initializer
// var nothing = null;             // Literal null không cho ra kiểu để suy luận
// var calc = x -> x * 2;          // Lambda cần một kiểu đích
// var length = String::length;    // Method reference cần một kiểu đích
// var numbers = {1, 2, 3};       // Array initializer trần cần kiểu đích
// var a = 1, b = 2;              // Không khai báo nhiều biến cùng lúc bằng var
// class Box { var value = 1; }   // Không dùng var cho field
// void set(var value) { }        // Không dùng var làm kiểu tham số phương thức
```

Cách viết đúng cho một số trường hợp:

```java
int[] numbers = {1, 2, 3};
var otherNumbers = new int[] {1, 2, 3}; // suy luận int[]

java.util.function.IntUnaryOperator twice = x -> x * 2;
java.util.function.ToIntFunction<String> getLength = String::length;
String nullable = null;
```

Các dòng đúng ở trên là những **khai báo minh họa trong khối lệnh** (không phải toàn bộ một tệp Java).

**Phân biệt phiên bản:** Từ **Java 11**, `var` còn có thể dùng cho **tham số của lambda có kiểu suy luận**; mọi tham số trong cùng danh sách phải dùng thống nhất cách viết. Ví dụ, trong ngữ cảnh thích hợp:

```java
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (var left, var right) -> left + right;
```

Đây là phần mở rộng có hiệu lực trong Java hiện đại; không nhầm nó với khả năng của bản phát hành Java 10 ban đầu. `var` vẫn không dùng để thay kiểu trả về hoặc tham số của phương thức thông thường.

## 5. Vì sao `var` có thể giúp mã dễ đọc hơn?

Một khai báo dễ đọc cung cấp đủ thông tin trả lời ba câu hỏi: **biến này đại diện cho gì, giá trị đến từ đâu, và ta có thể làm gì với nó?**

### Trường hợp 1: Kiểu được lặp rõ ở phía phải

```java
java.util.ArrayList<String> names = new java.util.ArrayList<String>();

// Gọn hơn, vẫn thấy ngay ArrayList<String>:
var names2 = new java.util.ArrayList<String>();
```

Bỏ phần lặp cho phép người đọc tập trung vào tên `names2` và giá trị khởi tạo.

### Trường hợp 2: Kiểu rõ qua API và ngữ cảnh gần

```java
java.util.List<String> names = java.util.List.of("Lan", "An");

for (var name : names) {           // name là String
    var upperName = name.toUpperCase(); // upperName là String
    System.out.println(upperName);
}
```

`var` hợp lý vì tên biến thể hiện vai trò, nguồn là `List<String>`, phạm vi ngắn và thao tác dễ hiểu. Việc dùng `var` ở đây không buộc người đọc tra cứu một phương thức xa lạ.

### Trường hợp 3: Kiểu trung gian quá dài, làm lu mờ luồng xử lý

```java
java.util.Map<String, Integer> scores =
        java.util.Map.of("Lan", 10, "An", 8);

for (var entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
```

`entry` có kiểu `Map.Entry<String, Integer>`. Việc không nhắc lại kiểu dài cho phép vòng lặp bộc lộ ý định là xử lý từng cặp khóa–giá trị.

## 6. Khi nào viết kiểu tường minh dễ đọc hơn?

### Trường hợp 1: Biểu thức khởi tạo che giấu kiểu

So sánh hai cách viết minh họa (giả sử `service` và các phương thức đã được định nghĩa):

```java
var result = service.fetch();                 // Kiểu và vai trò khó thấy
java.util.List<String> names = service.fetchNames(); // Hợp đồng kiểu rõ hơn
```

Không phải cứ gặp lời gọi phương thức là phải tránh `var`. Chẳng hạn `var count = names.size();` vẫn dễ hiểu nếu `names` đã có ngữ cảnh rõ. Hãy ưu tiên sự rõ ràng của **tên phương thức, tên biến và kiểu hợp đồng**.

### Trường hợp 2: Kiểu là một phần của ý định thiết kế

```java
java.util.List<String> pending = new java.util.ArrayList<>();
```

Khai báo này cố ý thể hiện rằng phần mã còn lại chỉ phụ thuộc vào **interface `List<String>`**. Nếu viết:

```java
var pending = new java.util.ArrayList<String>();
```

thì kiểu của `pending` là `ArrayList<String>`. Điều đó hoàn toàn hợp lệ với biến cục bộ nhỏ, nhưng người đọc không còn thấy trực tiếp ranh giới trừu tượng qua kiểu khai báo. Khi muốn thể hiện ranh giới này rõ ràng, giữ `List<String>`.

Một khác biệt kiểm tra kiểu:

```java
{
    java.util.List<String> items = new java.util.ArrayList<>();
    items = new java.util.LinkedList<>(); // Hợp lệ: cả hai đều là List<String>
}
{
    var items = new java.util.ArrayList<String>();
    // items = new java.util.LinkedList<String>(); // LỖI: items có kiểu ArrayList<String>
}
```

Hai khối độc lập có cùng tên biến để minh họa sự khác nhau. Không có quy tắc rằng **mọi** biến cục bộ phải khai báo theo interface: chọn theo nhu cầu bảo trì và mức độ phụ thuộc vào lớp cụ thể.

### Trường hợp 3: Kiểu số hoặc chuyển đổi kiểu mang ý nghĩa

```java
long timeoutMillis = 1000; // mục đích lưu bằng long
var timeout = 1000;        // suy luận int
var timeoutLong = 1000L;   // suy luận long
```

Khi bề rộng kiểu là một phần của hợp đồng dữ liệu, `long`, `double` hay một kiểu cụ thể có thể truyền tải ý định tốt hơn. Không thay máy móc `long x = 1;` thành `var x = 1;` vì điều đó đổi kiểu từ `long` sang `int`.

## 7. Hai bẫy quan trọng nhất: `var` + generic và `var` + literal

### 7.1. `var` kết hợp với diamond `<>`

```java
java.util.List<String> a = new java.util.ArrayList<>();
var b = new java.util.ArrayList<String>();
var c = new java.util.ArrayList<>();
```

- `a`: kiểu khai báo `List<String>`, còn diamond suy luận `String` từ vế trái.
- `b`: kiểu suy luận `ArrayList<String>` vì kiểu phần tử được ghi ở constructor.
- `c`: kiểu suy luận `ArrayList<Object>` vì không có dữ kiện nào xác định phần tử là `String`. `c.add("x")` và `c.add(123)` đều có thể hợp lệ; đó có thể là sai ý định.

Tương tự, `var empty = java.util.List.of();` không tự biết kiểu phần tử bạn muốn và thường được suy luận là `List<Object>`. Nếu cần danh sách `String` rỗng, hãy viết:

```java
java.util.List<String> emptyA = java.util.List.of();
var emptyB = java.util.List.<String>of();
```

Dùng một trong các cách trên để giữ thông tin kiểu; **đừng giả định generic luôn suy luận đúng ý định**.

### 7.2. `var` và literal nguyên thủy

```java
var a = 1;       // int
var b = 1L;      // long
var c = 1.0;     // double
var d = 1.0f;    // float
var flag = true; // boolean
```

Literal `1` là `int` ngay cả khi bạn định sử dụng số đó như `long`. Với giá trị ban đầu lấy từ biến hoặc lời gọi phương thức, `var` còn phụ thuộc **kiểu khai báo của nguồn**, không phải kiểu bạn mong muốn. Khi ý nghĩa của kiểu số quan trọng, viết tường minh hoặc dùng hậu tố/chuyển đổi phù hợp.

## 8. `var` không quyết định tính bất biến, an toàn null hay tốc độ

- **Không phải dynamic typing:** kiểu được chốt tại thời điểm biên dịch. Gán sai kiểu vẫn báo lỗi.
- **Không tự cấm `null`:** `var result = map.get(key);` hợp lệ nếu `get` có kiểu trả về xác định, kể cả khi kết quả thực tế là `null`. Chỉ `var result = null;` bị cấm vì không suy ra được kiểu từ literal `null`.
- **Không mặc định `final`:** `var n = 1; n = 2;` hợp lệ. `final var n = 1;` cấm gán lại `n`.
- **`final var` không khóa trạng thái đối tượng:** đối tượng mutable vẫn có thể thay đổi qua phương thức của nó.
- **Không phải mẹo tăng hiệu năng:** `var` thay cách biểu diễn kiểu trong mã nguồn; hiệu năng do chương trình, cấu trúc dữ liệu và JVM quyết định, không được bảo đảm thay đổi chỉ vì dùng `var`.

Ví dụ minh họa về `final var` trong một khối lệnh:

```java
final var labels = new java.util.ArrayList<String>();
labels.add("Java"); // Được: thay đổi nội dung đối tượng
// labels = new java.util.ArrayList<String>(); // Sai: gán lại biến final
```

## 9. Ví dụ Java 17+ chạy độc lập: cân bằng `var` và kiểu tường minh

Tạo tệp **`VarReadabilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class VarReadabilityDemo {
    public static void main(String[] args) {
        // Kiểu tường minh nêu hợp đồng của nguồn dữ liệu.
        List<String> rawNames = List.of(" Lan ", "Minh", "  An");

        // Kiểu constructor rõ; var tránh lặp ArrayList<String>.
        var cleanNames = new ArrayList<String>();

        // Biến trong vòng lặp có phạm vi nhỏ và kiểu dễ suy ra.
        for (var rawName : rawNames) {
            var cleanName = rawName.trim();
            cleanNames.add(cleanName);
        }

        // int tường minh khiến ý nghĩa của phép đếm dễ thấy.
        int numberOfNames = cleanNames.size();

        System.out.println(cleanNames);
        System.out.println("First: " + cleanNames.get(0));
        System.out.println("Count: " + numberOfNames);

        // entry có kiểu Map.Entry<String, Integer>.
        Map<String, Integer> points = Map.of("Lan", 3, "Minh", 5);
        for (var entry : points.entrySet()) {
            if (entry.getKey().equals("Lan")) {
                System.out.println("Lan points: " + entry.getValue());
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 VarReadabilityDemo.java
java VarReadabilityDemo
```

Đầu ra chuẩn:

```text
[Lan, Minh, An]
First: Lan
Count: 3
Lan points: 3
```

**Giải thích từng quyết định:**

1. `rawNames` có kiểu `List<String>`: hợp đồng collection thể hiện ngay ở ranh giới dữ liệu.
2. `cleanNames` có kiểu suy luận `ArrayList<String>`: constructor chứa đủ thông tin, phạm vi là một phương thức.
3. `rawName` và `cleanName` đều là `String`: loại giá trị rõ từ phần tử của `rawNames` và `String.trim()`.
4. `numberOfNames` dùng `int` tường minh: giúp người đọc nhận ra vai trò của kết quả đếm; `var` ở đây cũng biên dịch được nhưng không nhất thiết tốt hơn.
5. `entry` có kiểu `Map.Entry<String, Integer>`: `var` làm vòng lặp bớt nhiễu bởi kiểu generic dài.

Lưu ý: thứ tự duyệt của `Map.of` không nên được giả định; ví dụ chỉ in phần tử có khóa `"Lan"` nên kết quả vẫn xác định.

## 10. Quy trình chọn `var` khi viết hoặc review mã

Hãy kiểm tra theo thứ tự:

1. **Có hợp lệ không?** Đây có phải biến cục bộ có initializer phù hợp và dự án dùng Java hỗ trợ `var` không?
2. **Kiểu thực sự được suy luận là gì?** Xét constructor, kiểu trả về của phương thức, tham số generic, literal và kiểu đích có bị mất không.
3. **Người đọc có thể đoán nhanh không?** Tên biến và vế phải có cho biết vai trò/kiểu mà không cần nhảy đến định nghĩa xa không?
4. **Phạm vi có nhỏ không?** Biến chỉ được dùng vài dòng gần khai báo, hay kéo dài xuyên cả phương thức?
5. **Có ý định kiểu cần làm rõ không?** Interface, generic, kiểu số, tính tương thích khi gán lại hoặc hợp đồng dữ liệu có đáng hiển thị ở vế trái không?
6. **Đọc ngoài IDE vẫn dễ hiểu chứ?** Đừng phụ thuộc hoàn toàn vào thao tác rê chuột xem kiểu khi review diff, tài liệu hoặc log.

Quy tắc thực hành: **dùng `var` khi dữ kiện về kiểu đã rõ và loại bỏ lặp thực sự giúp dễ đọc; dùng kiểu tường minh khi kiểu tự nó truyền tải ý định**. Một phương thức hoàn toàn có thể sử dụng cả hai, như ví dụ trên.

### Những lỗi review phổ biến

| Dấu hiệu | Rủi ro | Cách cải thiện |
| --- | --- | --- |
| `var x = service.get();` với tên `x` chung chung | Người đọc phải tra cứu để biết vai trò và kiểu. | Đặt tên nêu vai trò; khi kiểu là thông tin quan trọng, viết kiểu tường minh. |
| `var values = new ArrayList<>();` | Phần tử có thể bị suy luận thành `Object`. | `new ArrayList<String>()` hoặc `List<String> values = new ArrayList<>();`. |
| Thay `long duration = 1;` thành `var duration = 1;` | Kiểu chuyển từ `long` sang `int`. | Giữ `long` hoặc dùng `1L` nếu phù hợp. |
| `var` cho biến dùng xuyên phương thức dài | Khó lần lại kiểu và tác động của refactor. | Thu hẹp phạm vi, tách hàm hoặc khai báo rõ kiểu. |
| Chỉ đổi mọi khai báo thành `var` để giảm số ký tự | Có thể che giấu hợp đồng, không cải thiện khả năng hiểu. | Đánh giá từng khai báo theo ngữ cảnh. |

## 11. Tự kiểm tra

**Câu 1.** Trong một khối lệnh, `var values = new ArrayList<>();` (đã import `ArrayList`) có kiểu phần tử nào? Làm sao tạo một `ArrayList<String>` rõ ràng?

**Câu 2.** `var total = 0;` có tự trở thành `double` khi sau đó gán `total = 2.5;` không?

**Câu 3.** Vì sao `var f = (String s) -> s.length();` không biên dịch, trong khi `ToIntFunction<String> f = s -> s.length();` hợp lệ (đã import interface)?

**Câu 4.** Khi nào `List<String> items = new ArrayList<>();` thể hiện ý định tốt hơn `var items = new ArrayList<String>();`?

**Câu 5.** `final var list = new ArrayList<String>(); list.add("x");` có hợp lệ không?

**Đáp án và lý do:**

1. `ArrayList<Object>`. Cách rõ ràng: `var values = new ArrayList<String>();` hoặc `ArrayList<String> values = new ArrayList<>();`.
2. Không. `total` là `int` cố định; gán `double` gây lỗi biên dịch. Dùng `double total = 0;` hoặc `var total = 0.0;` nếu cần kiểu `double`.
3. Lambda cần kiểu đích của functional interface để suy luận; `var` không cung cấp kiểu đích ấy. `ToIntFunction<String>` xác định chữ ký nhận `String`, trả về `int`.
4. Khi cần nêu rõ hợp đồng theo interface, tránh phụ thuộc vào `ArrayList` hoặc có thể đổi implementation mà vẫn giữ kiểu biến là `List<String>`.
5. Hợp lệ. `final` cấm gán lại tham chiếu `list`; đối tượng `ArrayList` vẫn mutable.

## 12. Ghi nhớ và tài liệu chính thức

- `var` **ẩn tên kiểu ở khai báo, không xóa kiểu khỏi hệ thống kiểu của Java**.
- **Compiler** quan tâm biểu thức khởi tạo và quy tắc suy luận; **người đọc** quan tâm tên, ý nghĩa, phạm vi và hợp đồng kiểu.
- Sự ngắn gọn chỉ có giá trị khi giữ lại thông tin cần thiết; **cùng một dự án nên dùng `var` và kiểu tường minh một cách có chủ đích**.
- Đừng bỏ qua generic `<>`, literal số và ranh giới interface vì đây là nơi việc đổi cú pháp có thể làm đổi kiểu.

Tham khảo quy tắc và hướng dẫn vẫn áp dụng:
- [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [OpenJDK Project Amber – FAQ về local-variable type inference](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md).
- [OpenJDK Project Amber – Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md).
- [Java Language Specification, `14.4 – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4).
