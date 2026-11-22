# Kết hợp record pattern với type pattern trong Java 21

Trong Java, **type pattern** giúp kiểm tra kiểu và đặt tên cho **cả đối tượng**, còn **record pattern** giúp kiểm tra record rồi **tách các thành phần** của nó. Khi kết hợp hai loại pattern, ta có thể vừa nhận diện cấu trúc của dữ liệu, vừa chọn cách giữ nguyên hoặc tách tiếp từng thành phần tùy nhu cầu.

Bài này dùng **Java 21 trở lên**. Pattern matching cho `instanceof` ổn định từ Java 16 (JEP 394); record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) chính thức từ Java 21. Các ví dụ Java 21 trong bài không cần `--enable-preview`.

## 1. Phân biệt hai pattern trước khi kết hợp

Giả sử có record:

```java
record Point(int x, int y) {}
```

Với một biến `Object input` đang chứa `new Point(2, 3)`, so sánh:

```java
// Type pattern: lấy cả đối tượng Point.
if (input instanceof Point p) {
    System.out.println(p.x() + p.y()); // 5
}

// Record pattern: tách trực tiếp hai thành phần.
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

- `Point p` là **type pattern**: kiểm tra `input` có phải `Point` hay không và ràng buộc toàn bộ đối tượng vào `p`. Muốn đọc thành phần thì dùng accessor `p.x()`, `p.y()`.
- `Point(int x, int y)` là **record pattern**: kiểm tra đối tượng `Point` rồi áp dụng tiếp hai component patterns `int x` và `int y`, từ đó có ngay hai biến `x` và `y`.
- `int x`, `int y` là các **type patterns ở vị trí thành phần** của record pattern. Vì thế ngay một record pattern đơn giản đã có thể bao gồm các type patterns.
- Không có thao tác “giải nén bằng phép gán” kiểu `(x, y) = point` trong Java 21; cú pháp deconstruction ở đây được dùng trong ngữ cảnh pattern matching như `instanceof` và `case`.

Cả hai cách đều **đọc** record hiện có. Chúng không gọi constructor để tạo record mới và không thay đổi các thành phần của record.

## 2. Mô hình dữ liệu cần phối hợp nhiều pattern

Xét một record ngoài chứa nhiều kiểu dữ liệu:

```java
record Point(int x, int y) {}
record Owner(String name) {}
record Envelope(String id, Object payload, Owner owner) {}
```

`Envelope` gồm:

| Thành phần | Kiểu khai báo | Ý nghĩa |
| --- | --- | --- |
| `id` | `String` | Mã của phong bì dữ liệu |
| `payload` | `Object` | Nội dung có thể là `Point`, `String` hoặc một kiểu khác |
| `owner` | `Owner` | Thông tin người sở hữu, bản thân cũng là record |

Do `payload` có kiểu khai báo `Object` nên không thể biết trước nội dung có thực sự là `Point` hay `String`. Mục tiêu của việc kết hợp patterns là **kiểm tra kiểu tại đúng vị trí** và chỉ lấy những biến đã được xác nhận.

## 3. Dùng type pattern trực tiếp trong record pattern

Ví dụ đầu tiên chỉ tách record ngoài, còn với `payload` và `owner` ta giữ nguyên đối tượng đã khớp:

```java
Object candidate = new Envelope(
        "E1", new Point(2, 3), new Owner("Lan"));

if (candidate instanceof Envelope(String id, Point p, Owner owner)) {
    System.out.println(id);        // E1
    System.out.println(p.x());     // 2
    System.out.println(owner.name()); // Lan
}
```

Đọc biểu thức `Envelope(String id, Point p, Owner owner)` từ ngoài vào trong:

1. `Envelope(...)` là **record pattern**. `candidate` phải là một `Envelope` khác `null`.
2. `String id` là **component type pattern** cho thành phần thứ nhất (khai báo `String`). Nó tạo biến `id`.
3. `Point p` là **component type pattern** đặt trên thành phần `payload` (khai báo `Object`). Nó chỉ khớp khi nội dung thực sự là một đối tượng `Point`; biến `p` giữ **cả đối tượng** `Point`.
4. `Owner owner` là **component type pattern** cho thành phần thứ ba (khai báo `Owner`); biến `owner` giữ record `Owner` để gọi `owner.name()`.

Nếu `payload` chứa một `String`, pattern ở bước 3 không khớp và toàn bộ phép `instanceof` trả `false`. Không cần ép kiểu thủ công từ `Object` sang `Point`.

Ở đây Java vẫn tách `Envelope`, nhưng ta chủ động **không tách tiếp** hai đối tượng `Point` và `Owner`. Cách này phù hợp khi cần gọi accessor hoặc chuyển cả đối tượng cho phương thức khác.

## 4. Lồng record pattern bên cạnh type pattern

Nếu cần ngay tọa độ và tên chủ sở hữu, thay `Point p` và `Owner owner` bằng các record patterns lồng nhau:

```java
Object candidate = new Envelope(
        "E1", new Point(2, 3), new Owner("Lan"));

if (candidate instanceof
        Envelope(String id, Point(int x, int y), Owner(String name))) {
    System.out.println(id + ": (" + x + "," + y + "), owner=" + name);
    // E1: (2,3), owner=Lan
}
```

Cấu trúc:

```text
Envelope(
    String id,               // Type pattern cho thành phần id
    Point(int x, int y),     // Record pattern cho payload
    Owner(String name)       // Record pattern cho owner
)
```

- `Envelope(...)` là record pattern ngoài.
- `String id` là type pattern trực tiếp trong `Envelope`.
- `Point(int x, int y)` là record pattern lồng cho `payload`; bên trong nó có hai type patterns `int x` và `int y`.
- `Owner(String name)` là record pattern lồng cho `owner`; bên trong là type pattern `String name`.
- Các biến `id`, `x`, `y`, `name` chỉ được sử dụng tại các vị trí trình biên dịch biết **toàn bộ pattern đã khớp thành công**.

Lệnh khớp đi theo cấu trúc khai báo record, **không dựa vào tên biến**. `Point(int a, int b)` vẫn tách thành phần `x` vào `a` và thành phần `y` vào `b`.

### Một số kết quả khớp

| Dữ liệu | Pattern lồng ở trên | Nguyên nhân |
| --- | --- | --- |
| `Envelope("E1", new Point(2,3), new Owner("Lan"))` | Khớp | Đúng ba thành phần và cấu trúc con |
| `Envelope("E2", "hello", new Owner("Minh"))` | Không khớp | `payload` không phải `Point` |
| `Envelope("E3", new Point(9,9), null)` | Không khớp | Record pattern `Owner(...)` không nhận `null` |
| `Envelope("E4", new Point(0,0), new Owner(null))` | Khớp | `Owner` tồn tại; component type pattern `String name` có thể nhận `null` |
| `null` | Không khớp | Record pattern ngoài `Envelope(...)` không nhận `null` |

Chi tiết về `null` ở các component type patterns được phân tích tại mục 7.

## 5. Kết hợp một record pattern với nhiều loại type pattern khác nhau

Đối với trường `payload` khai báo `Object`, ta có thể đặt type pattern `String text` thay vì nested record pattern `Point(...)`:

```java
Object candidate = new Envelope(
        "E2", "hello", new Owner("Minh"));

if (candidate instanceof Envelope(
        String id, String text, Owner(var ownerName))) {
    System.out.println(id + " text=" + text + ", owner=" + ownerName);
    // E2 text=hello, owner=Minh
}
```

Ở ví dụ này:

- `String id` khớp thành phần `id` đã khai báo `String`.
- `String text` nằm trên thành phần `payload` khai báo `Object`. Nó **kiểm tra kiểu tại thời điểm chạy** và chỉ nhận payload là `String` khác `null`.
- `Owner(var ownerName)` là record pattern lồng trong `Envelope`. `var ownerName` suy ra kiểu thành phần `name` là `String`.

`var` trong record pattern là cách suy luận kiểu **tĩnh** dựa vào khai báo record. Đây không phải biến kiểu động. Nếu viết `Envelope(var id, var payload, var owner)` thì các kiểu suy ra lần lượt là `String`, `Object`, `Owner`, và không có điều kiện ràng buộc rằng `payload` thực sự là `Point` hay `String`.

### Giữ nguyên record con hay tiếp tục tách?

Hai phiên bản dưới đây kiểm tra được cùng tình huống `payload` là `Point`, nhưng khác kiểu dữ liệu mà nhánh thành công sử dụng:

```java
// Giữ toàn bộ Point rồi đọc accessor.
if (candidate instanceof Envelope(var id, Point p, var owner)) {
    System.out.println(p.x());
}

// Tách Point để có ngay hai biến int.
if (candidate instanceof Envelope(var id, Point(var x, var y), var owner)) {
    System.out.println(x);
}
```

Đặt `Point p` khi cần chuyển `p` cho phương thức khác; đặt `Point(var x, var y)` khi cần trực tiếp từng thành phần. Cả hai đều chỉ khớp khi payload thực sự là `Point` khác `null`.

## 6. Kết hợp phép khớp nối tiếp với &&

Không phải mọi phép phối hợp đều cần nằm trong **một** nested record pattern. Ta có thể tách record ngoài rồi kiểm tra thành phần bằng type pattern khác qua `&&`:

```java
if (candidate instanceof Envelope(var id, var payload, var owner)
        && payload instanceof Point p) {
    System.out.println(id + " has point x=" + p.x());
}
```

Vế trái kiểm tra `candidate` là `Envelope` và tạo biến `payload` (kiểu tĩnh `Object`). Vế phải kiểm tra `payload` có phải `Point` rồi đặt cả đối tượng vào `p`. Vì toán tử `&&` đánh giá từ trái sang phải và chỉ đánh giá vế phải khi vế trái đúng, `payload` đã nằm trong phạm vi hợp lệ khi tới `payload instanceof Point p`.

Biểu thức này tương tự mục đích lọc dữ liệu của:

```java
if (candidate instanceof Envelope(var id, Point p, var owner)) {
    System.out.println(id + " has point x=" + p.x());
}
```

Với cấu trúc đơn giản, phiên bản record pattern lồng ngắn hơn; với nhiều phép kiểm tra độc lập hoặc cần dùng biến `payload` theo nhiều hướng, phiên bản `&&` có thể tiện hơn.

**Lưu ý phạm vi:** nếu dùng `||` hoặc cố đọc biến pattern tại chỗ mà nhánh khớp chưa được bảo đảm, mã có thể không biên dịch. Đừng dựa vào tên biến trùng nhau để coi chúng luôn tồn tại ngoài điều kiện.

## 7. Khác biệt quan trọng khi gặp null

Quy tắc dễ nhầm là: **record pattern không khớp đối tượng record `null`**, nhưng **type pattern ở vị trí thành phần record có thể khớp `null` nếu nó là pattern không điều kiện (unconditional) đối với kiểu khai báo của thành phần**.

Với `record Envelope(String id, Object payload, Owner owner)`, xét:

```java
Object candidate = new Envelope(null, null, new Owner(null));
```

Các biểu thức sau có kết quả:

```java
candidate instanceof Envelope(String id, var payload, var owner)
// true: String id không điều kiện với thành phần khai báo String;
//       các biến id và payload có thể nhận null.

candidate instanceof Envelope(var id, String text, var owner)
// false: String text yêu cầu payload Object thực sự là String khác null.

candidate instanceof Envelope(var id, var payload, Owner(String name))
// true: Owner khác null và component String name có thể nhận null.
```

Ba biểu thức trên là các ví dụ minh họa, không phải những dòng lệnh Java độc lập được đặt trong một phương thức hoàn chỉnh. Kết quả cũng được kiểm chứng trong chương trình chạy đầy đủ ở mục 9.

Nếu record con `owner` bằng `null`, pattern `Owner(String name)` hoặc `Owner(var name)` **không khớp**. Nếu `owner` tồn tại nhưng `owner.name() == null`, type pattern `String name` trong `Owner(...)` có thể khớp thành phần `null` vì nó không điều kiện đối với kiểu `String` đã khai báo.

Phân biệt rõ **cấp ngoài**:

```java
Object candidate = null;

if (candidate instanceof Envelope(var id, var payload, var owner)) {
    // Không chạy: candidate là null.
}
```

Và cần nhớ rằng **top-level type pattern** trong `instanceof` cũng không khớp giá trị `null`, ví dụ `candidate instanceof String s` trả `false` khi `candidate == null`. Khả năng component type pattern nhận `null` là quy tắc riêng khi pattern được áp dụng vào thành phần của record.

Đừng gọi `name.length()` hoặc `id.length()` ngay chỉ vì record pattern đã khớp: biến thuộc kiểu tham chiếu có thể mang giá trị `null`. Kiểm tra bằng `== null` hoặc đặt ràng buộc trong constructor record khi nghiệp vụ yêu cầu.

## 8. Kết hợp nhiều pattern trong switch

`switch` Java 21 cho phép phân loại các dạng payload ngay trong `case`. Khi có các nhánh hẹp và một nhánh rộng, hãy đặt các nhánh cụ thể trước:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "input=null";
        case Envelope(String id, Point(int x, int y), Owner(String name)) ->
                id + " point=(" + x + "," + y + "), owner=" + name;
        case Envelope(String id, String text, Owner(var name)) when !text.isBlank() ->
                id + " text=" + text + ", owner=" + name;
        case Envelope(var id, var payload, var owner) -> "Other envelope: " + id;
        default -> "Not an envelope";
    };
}
```

- Nhánh **Point**: record pattern `Envelope` kết hợp type pattern `String id` và hai record patterns lồng `Point`, `Owner`; chỉ khớp khi các record cần tách đều tồn tại.
- Nhánh **String**: `String text` kiểm tra kiểu thực của `payload`. `when !text.isBlank()` chỉ được đánh giá sau khi mọi pattern trong case đã khớp, nên gọi `text.isBlank()` an toàn tại đây.
- Nhánh **Envelope còn lại**: `var` ở từng thành phần nhận toàn bộ giá trị thành phần, kể cả `null`. Nhánh này xử lý payload kiểu khác hoặc cấu trúc con không đủ điều kiện cho hai nhánh trước.
- `case null` xử lý **selector `value` bằng `null`**; nó không xử lý mọi thành phần `null` bên trong record.
- `default` xử lý đối tượng không phải `Envelope`.

**Thứ tự và dominance:** `case Envelope(var id, var payload, var owner)` là một case rộng, khớp mọi `Envelope` khác `null`. Nếu đặt nó trước case `Envelope(String id, Point(...), Owner(...))`, case cụ thể phía sau sẽ bị che (*dominated*) và Java có thể từ chối biên dịch. Khi điều kiện guard có ý nghĩa, đặt case có `when` trước case tương ứng tổng quát.

Trong một `switch` với selector có thể `null`, đừng mặc định `default` xử lý `null`: nêu rõ `case null` nếu cần hành vi riêng; nếu không, selector `null` có thể dẫn tới `NullPointerException`.

## 9. Chương trình hoàn chỉnh chạy trên Java 21+

Lưu nguyên mã sau thành tệp **`PatternCompositionDemo.java`**:

```java
public class PatternCompositionDemo {
    record Point(int x, int y) {}
    record Owner(String name) {}
    record Envelope(String id, Object payload, Owner owner) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "input=null";
            case Envelope(String id, Point(int x, int y), Owner(String name)) ->
                    id + " point=(" + x + "," + y + "), owner=" + name;
            case Envelope(String id, String text, Owner(var name)) when !text.isBlank() ->
                    id + " text=" + text + ", owner=" + name;
            case Envelope(var id, var payload, var owner) -> "Other envelope: " + id;
            default -> "Not an envelope";
        };
    }

    static String inspectPayload(Object value) {
        if (value instanceof Envelope(var id, var payload, var owner)
                && payload instanceof Point p) {
            return id + " has point x=" + p.x();
        }
        return "not point";
    }

    public static void main(String[] args) {
        Object a = new Envelope("E1", new Point(2, 3), new Owner("Lan"));
        Object b = new Envelope("E2", "hello", new Owner("Minh"));
        Object c = new Envelope("E3", new Point(9, 9), null);
        Object d = new Envelope(null, null, new Owner(null));
        Object e = "test";
        for (Object v : new Object[]{a, b, c, d, e, null}) {
            System.out.println(describe(v));
        }
        System.out.println(inspectPayload(a));
        System.out.println(inspectPayload(b));
        System.out.println("null id type: "
                + (d instanceof Envelope(String id, var payload, var owner)));
        System.out.println("null payload String: "
                + (d instanceof Envelope(var id, String text, var owner)));
        System.out.println("null owner record: "
                + (c instanceof Envelope(var id, var payload, Owner(var name))));
        Object f = new Envelope("E4", new Point(0, 0), new Owner(null));
        System.out.println("null name type: "
                + (f instanceof Envelope(String id, Point(var x, var y), Owner(String name))));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 -encoding UTF-8 PatternCompositionDemo.java
java PatternCompositionDemo
```

**Đầu ra chính xác:**

```text
E1 point=(2,3), owner=Lan
E2 text=hello, owner=Minh
Other envelope: E3
Other envelope: null
Not an envelope
input=null
E1 has point x=2
not point
null id type: true
null payload String: false
null owner record: false
null name type: true
```

Giải thích theo thứ tự:

1. `E1` chứa `Point` và `Owner` khác `null` nên khớp nhánh record patterns lồng, tách `x=2`, `y=3`, `name="Lan"`.
2. `E2` chứa payload `String` không rỗng nên khớp nhánh `String text` và guard `!text.isBlank()`.
3. `E3` chứa `Point` nhưng `owner == null`, nên pattern `Owner(String name)` thất bại; case `Envelope(var id, var payload, var owner)` rộng hơn bắt lại.
4. `d` là `Envelope` có `id == null` và `payload == null`; nó vẫn khớp case `Envelope(var ...)` và phép nối chuỗi tạo `Other envelope: null`.
5. Đối tượng `String` đi vào `default`; selector `null` vào `case null`.
6. Phương thức `inspectPayload` tách `Envelope` bằng `var`, rồi dùng type pattern `Point p` để kiểm tra riêng payload. Với `E1` nó thành công, với `E2` thì không.
7. Bốn dòng cuối là các phép thử `null` tại thành phần: type pattern `String id` được áp dụng vào thành phần đã khai báo `String` có thể nhận `null`; `String text` áp dụng vào `Object` không nhận `null`; record pattern `Owner(...)` không nhận record `null`; nhưng component type pattern `String name` trong `Owner` nhận được giá trị tên `null`.

Chương trình đã được biên dịch với `javac --release 21` và chạy để kiểm chứng đầu ra.

## 10. Những lỗi thường gặp khi kết hợp

1. **Đồng nhất type pattern và record pattern.** `Point p` giữ nguyên một đối tượng `Point`; `Point(int x, int y)` tách hai thành phần. Chọn đúng ý định trước khi viết.
2. **Đặt pattern sai vị trí trong record.** Với `Envelope(String id, Object payload, Owner owner)`, pattern ở vị trí thứ hai kiểm tra `payload`, không kiểm tra `owner`. Tên biến không thay đổi thứ tự khai báo.
3. **Sai số lượng component patterns.** `Envelope` có ba thành phần; record pattern `Envelope(...)` phải cung cấp đủ ba component patterns theo cấu trúc Java 21.
4. **Thấy `Object` rồi tự ép kiểu khi chưa khớp.** Dùng `Point p` hoặc `String text` để kiểm tra payload trước khi đọc dữ liệu chuyên biệt; tránh ép kiểu có thể gây `ClassCastException`.
5. **Cho rằng type pattern ở mọi vị trí đều từ chối null.** `String id` trên thành phần đã khai báo `String` có thể nhận `null`, trong khi `String text` trên thành phần `Object` yêu cầu giá trị `String` khác `null`.
6. **Cho rằng record pattern lồng chấp nhận record con null.** `Owner(String name)` không khớp nếu `owner == null`; để giữ giá trị có thể null, dùng `var owner` rồi kiểm tra khi cần.
7. **Dùng biến pattern ngoài phạm vi chắc chắn khớp.** Phạm vi các biến trong `if`, `&&` và `switch` phụ thuộc vào luồng điều khiển; hãy để compiler xác nhận nơi sử dụng.
8. **Đưa case rộng lên trước case cụ thể.** `Envelope(var id, var payload, var owner)` có thể che nhánh kiểm tra `Point` hoặc `String` ở phía sau.
9. **Nhầm biến `var` với đối tượng động.** Kiểu của `var` được suy ra tại lúc biên dịch từ record; `var payload` có kiểu `Object`, không tự động thành `Point` dù giá trị thực là `Point`.
10. **Nhầm record pattern với cú pháp tạo đối tượng.** `new Envelope(...)` tạo record; `Envelope(...)` trong `instanceof`/`case` là cú pháp kiểm tra và tách dữ liệu.

## 11. Tự kiểm tra

**Câu 1.** Với `Object o = new Envelope("A", new Point(7, 8), new Owner("Ha"));`, pattern `Envelope(String id, Point p, Owner(String name))` có khớp không? Biến `p` là gì?

*Đáp án:* Có; `p` là **cả record `Point(7, 8)`**, nên có thể gọi `p.x()` để nhận `7`. Nếu muốn biến tọa độ trực tiếp, dùng `Point(int x, int y)`.

**Câu 2.** Với `new Envelope("B", "abc", new Owner("Ha"))`, pattern `Envelope(var id, Point p, var owner)` có khớp không?

*Đáp án:* Không. Component type pattern `Point p` áp dụng vào payload kiểu thực `String` nên không khớp.

**Câu 3.** Trong `Envelope(String id, Point(var x, var y), Owner(var name))`, kiểu tĩnh của `x`, `y`, `name` là gì?

*Đáp án:* `int`, `int`, `String`. `var` lấy kiểu từ định nghĩa thành phần của các record `Point` và `Owner`.

**Câu 4.** Vì sao `case Envelope(var id, var payload, var owner)` phải ở sau các case phân loại `Point`, `String`?

*Đáp án:* Đây là một record pattern đủ rộng để khớp mọi `Envelope` khác `null`. Nếu đặt trước, nó che những case chuyên biệt phía sau.

**Tài liệu chính thức:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
