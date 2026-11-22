# Đọc nested record pattern từ ngoài vào trong (Java 21+)

## 1. Ý tưởng chính

**Nested record pattern** (record pattern lồng nhau) giúp kiểm tra và tách một cấu trúc gồm nhiều `record` nằm trong nhau. Khi đọc một biểu thức lồng nhiều cặp ngoặc, hãy **bắt đầu từ record ngoài cùng, xác định từng component theo thứ tự khai báo, rồi đi sâu vào component nào có record pattern tiếp theo**. Cuối cùng, các biến ở lá nhận giá trị để sử dụng trong phần thân `if` hoặc `case`.

Ví dụ tổng quát:

```java
Outer(var first, Inner(var second, Leaf(var third, var fourth)))
```

Đọc bằng lời: “Giá trị phải là `Outer`; component thứ nhất gán vào `first`; component thứ hai phải là `Inner`; component thứ nhất của `Inner` gán vào `second`; component còn lại phải là `Leaf`; hai component của `Leaf` gán vào `third` và `fourth`.”

**Yêu cầu phiên bản:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) đều là tính năng chính thức từ **Java 21**. Các ví dụ sử dụng JDK 21+, không cần `--enable-preview`. Dù `record` đã có từ Java 16, Java 17 chưa hỗ trợ cú pháp record pattern lồng nhau ở trạng thái chính thức.

Sau bài này, người học có thể đọc đúng kiểu và thứ tự từng component, giải thích vì sao một tầng không khớp, đặt `when` sau quá trình tách, và chọn mức độ lồng nhau vừa đủ thay vì tách mọi thứ.

## 2. Đọc cấu trúc dữ liệu trước khi đọc pattern

Xét bốn record:

```java
record Point(int x, int y) {}
record Address(String city, Point point) {}
record Person(String name, Address address) {}
record Parcel(String code, Person receiver) {}
```

Một `Parcel` chứa `Person`; người đó chứa `Address`; địa chỉ chứa `Point`. Có thể biểu diễn cây kiểu như sau:

```text
Parcel
├── code: String
└── receiver: Person
    ├── name: String
    └── address: Address
        ├── city: String
        └── point: Point
            ├── x: int
            └── y: int
```

Mỗi cặp ngoặc trong record pattern biểu thị **danh sách pattern cho các component của đúng record đó**. Tên biến mới trong pattern không quyết định vị trí; vị trí phải khớp khai báo record. Chẳng hạn:

```java
Parcel(var code, Person(var name, Address(var city, Point(var x, var y))))
```

Đọc từ ngoài vào trong:

| Tầng | Phần pattern | Điều cần xác nhận | Biến được ràng buộc |
| --- | --- | --- | --- |
| 1 | `Parcel(..., ...)` | Đầu vào là một `Parcel` không-null | Chưa có, trước khi tách component |
| 1 → lá | `var code` | Component thứ nhất của `Parcel` là `code` | `code` có kiểu `String` |
| 2 | `Person(..., ...)` | `Parcel.receiver()` là một `Person` không-null | Các biến của `Person` sẽ được xét |
| 2 → lá | `var name` | Component thứ nhất của `Person` là `name` | `name` có kiểu `String` |
| 3 | `Address(..., ...)` | `Person.address()` là một `Address` không-null | Các biến của `Address` sẽ được xét |
| 3 → lá | `var city` | Component thứ nhất của `Address` là `city` | `city` có kiểu `String` |
| 4 | `Point(..., ...)` | `Address.point()` là một `Point` không-null | Các biến của `Point` sẽ được xét |
| 4 → lá | `var x, var y` | Hai component kiểu `int` của `Point` | `x` và `y` có kiểu `int` |

**Cách đọc nhanh:** mỗi khi gặp `Type(`, đi vào một record mới; gặp `var tên` hoặc pattern lá thì dừng đào sâu tại component đó; gặp `)` thì quay ra record cha. Dấu phẩy phân cách component **trong cùng một record**, không phân cách các tầng.

Đây là mô hình tư duy để giải thích cấu trúc và điều kiện khớp, không phải cam kết rằng JVM sẽ tạo các đối tượng trung gian hoặc thực hiện từng dòng như một chương trình tuần tự. Record pattern không tạo bản sao; nó kiểm tra kiểu và đọc component bằng accessor hiện có.

## 3. Theo vết với một đối tượng cụ thể

Giả sử có:

```java
Parcel parcel = new Parcel(
    "PK-21",
    new Person(
        "An",
        new Address("Hà Nội", new Point(3, 4))
    )
);
```

Kiểm tra:

```java
if (parcel instanceof Parcel(
        var code,
        Person(var name,
            Address(var city, Point(var x, var y))))) {
    System.out.println(code + " | " + name + " | " + city
        + " | " + x + " | " + y);
}
```

Đây là **đoạn mã minh họa dùng các record vừa khai báo**, chưa phải tệp chạy độc lập. Kết quả in ra nếu đặt trong chương trình phù hợp:

```text
PK-21 | An | Hà Nội | 3 | 4
```

Hãy lần theo cấu trúc, theo đúng thứ tự các nhánh component:

1. **Ngoài cùng:** đối tượng `parcel` là `Parcel`. Thành phần đầu tiên `code` nhận `"PK-21"`.
2. **Vào receiver:** component thứ hai phải khớp `Person(...)`. Đây là kiểm tra trên giá trị của `parcel.receiver()`; nếu nhận `null`, việc khớp thất bại tại đây.
3. **Vào Person:** `name` nhận `"An"`. Component `address` phải khớp `Address(...)`.
4. **Vào Address:** `city` nhận `"Hà Nội"`. Component `point` phải khớp `Point(...)`.
5. **Vào Point:** `x` nhận `3`, `y` nhận `4`; không còn record pattern lồng sâu.
6. **Quay ra:** nếu **tất cả** các pattern con khớp, toàn bộ `Parcel(...)` khớp; các biến `code`, `name`, `city`, `x`, `y` có thể dùng trong thân `if`.

Nếu tầng `Point(...)` không khớp thì **toàn bộ** nested pattern không khớp. Chương trình không “tách một phần rồi chạy thân `if`”; các biến chỉ khả dụng trong nhánh mà toàn bộ pattern thành công.

## 4. Ví dụ Java 21 hoàn chỉnh: đọc sâu và lùi về tầng nông hơn

Tạo tệp **`NestedReadingDemo.java`**:

```java
public class NestedReadingDemo {
    record Point(int x, int y) {}
    record Address(String city, Point point) {}
    record Person(String name, Address address) {}
    record Parcel(String code, Person receiver) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Giá trị null";

            // Đọc sâu đến Point, sau đó dùng guard để kiểm tra tên.
            case Parcel(
                    var code,
                    Person(var name,
                        Address(var city, Point(var x, var y))))
                    when name != null && code != null ->
                code + ": " + name + " ở " + city
                    + ", điểm (" + x + ", " + y + ")";

            // Point không tồn tại: dừng ở Address rồi nhận point.
            case Parcel(
                    var code,
                    Person(var name, Address(var city, var point)))
                    when point == null ->
                code + ": thiếu tọa độ";

            // Address không tồn tại: dừng ở Person rồi nhận address.
            case Parcel(
                    var code,
                    Person(var name, var address))
                    when address == null ->
                code + ": thiếu địa chỉ";

            // Person không tồn tại: dừng ở Parcel rồi nhận receiver.
            case Parcel(var code, var receiver)
                    when receiver == null ->
                code + ": thiếu người nhận";

            // Cấu trúc là Parcel nhưng chưa đạt điều kiện nhánh trên.
            case Parcel(var code, var receiver) ->
                code + ": dữ liệu chưa hợp lệ";

            default -> "Không phải bưu kiện";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Parcel(
            "PK-21",
            new Person("An", new Address("Hà Nội", new Point(3, 4))))));

        System.out.println(describe(new Parcel(
            "PK-22",
            new Person("Bình", new Address("Huế", null)))));

        System.out.println(describe(new Parcel(
            "PK-23", new Person("Chi", null))));

        System.out.println(describe(new Parcel("PK-24", null)));

        System.out.println(describe(new Parcel(
            "PK-25",
            new Person(null, new Address("Đà Nẵng", new Point(5, 6))))));

        System.out.println(describe("abc"));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 NestedReadingDemo.java
java NestedReadingDemo
```

Kết quả dự kiến:

```text
PK-21: An ở Hà Nội, điểm (3, 4)
PK-22: thiếu tọa độ
PK-23: thiếu địa chỉ
PK-24: thiếu người nhận
PK-25: dữ liệu chưa hợp lệ
Không phải bưu kiện
Giá trị null
```

**Vì sao chọn được nhánh tương ứng?**

- **PK-21:** mọi record từ `Parcel` đến `Point` đều tồn tại; `code` và `name` không null, nên nested pattern và `when` cùng thành công.
- **PK-22:** `Address.point()` là `null`, vì thế nested `Point(var x, var y)` thất bại. Nhánh thứ hai chỉ đòi `Address` hiện hữu; `var point` nhận `null` và guard `point == null` đúng.
- **PK-23:** `Person.address()` là `null`, nhánh thứ nhất và thứ hai (đều đòi `Address(...)`) không khớp. Nhánh thứ ba tách tới `Person` rồi nhận `address == null`.
- **PK-24:** `Parcel.receiver()` là `null`, các nhánh chứa `Person(...)` không khớp. `var receiver` trong nhánh thứ tư nhận null và guard đúng.
- **PK-25:** nested record pattern **vẫn khớp về mặt cấu trúc** vì `var name` trực tiếp trên component `String` có thể nhận null. Guard `name != null` là `false`; các guard kiểm tra thiếu point/address/receiver tiếp theo cũng sai, nên chạy nhánh `Parcel(var code, var receiver)` cuối.
- `"abc"` không phải `Parcel` nên vào `default`; còn selector `null` được xử lý bởi `case null`.

Điểm nổi bật của ví dụ là **độ sâu đọc có thể thay đổi theo mục đích từng nhánh**: có nhánh đi tận `Point`, nhánh dừng ở `Address`, có nhánh chỉ xét `Parcel`. Tất cả vẫn dựa trên cùng một khai báo record.

## 5. Phân biệt pattern đi sâu và biến nhận nguyên component

Hai cú pháp sau **không tương đương về điều kiện khớp**:

```java
// Kiểm tra point là Point không-null, tách tiếp x và y.
Parcel(var code, Person(var name,
    Address(var city, Point(var x, var y))))

// Không yêu cầu point là Point không-null;
// biến point nhận nguyên component Address.point().
Parcel(var code, Person(var name,
    Address(var city, var point)))
```

Với `record Address(String city, Point point)`, biến `point` ở mẫu thứ hai có kiểu suy luận là `Point`; nó có thể là null, vì `var point` là type pattern vô điều kiện cho chính component kiểu `Point`. Mẫu đầu dùng **record pattern** `Point(...)`, mà giá trị null thì không khớp.

Cũng vậy:

```java
Parcel(var code, Person(var name, var address))
Parcel(var code, var receiver)
```

Dòng thứ nhất kiểm tra `Person` không-null rồi giữ nguyên `Address` trong biến `address`; dòng thứ hai không đào vào `Person`, chỉ giữ nguyên `receiver`.

Nếu một component không cần tách sâu, hãy dừng ở `var` hoặc một type pattern phù hợp. Không cần viết pattern cho mọi tầng chỉ để lấy một biến ở tầng trên.

## 6. Quy tắc `null` ở từng tầng

Đọc nested pattern từ ngoài vào trong cũng là cách xác định **null ở đâu sẽ làm pattern thất bại**.

| Giá trị | `Parcel(var code, var receiver)` | `Parcel(var code, Person(var name, var address))` | Pattern lồng tới `Point(var x, var y)` |
| --- | --- | --- | --- |
| `new Parcel("A", null)` | Khớp: `receiver == null` | Không khớp: `Person(...)` cần non-null | Không khớp |
| `new Parcel("B", new Person("An", null))` | Khớp | Khớp: `address == null` | Không khớp: `Address(...)` cần non-null |
| `new Parcel("C", new Person("An", new Address("Huế", null)))` | Khớp | Khớp | Không khớp: `Point(...)` cần non-null |
| `new Parcel("D", new Person(null, new Address("Huế", new Point(1, 2))))` | Khớp | Khớp: `name == null` | Khớp về cấu trúc; guard khác có thể từ chối |
| `null` (chính selector) | Không khớp record pattern | Không khớp | Không khớp |

**Cần phân biệt ba quy tắc:**

1. **Bản thân record pattern không khớp null**, tại bất kỳ độ sâu nào: `Person(...)` hoặc `Point(...)` yêu cầu giá trị ở tầng đó là record thực sự.
2. **Type pattern trực tiếp trên một component của record có thể khớp null nếu vô điều kiện cho kiểu component đó**. `var name` trên `String name` và `var receiver` trên `Person receiver` là các ví dụ; chúng ràng buộc cả giá trị null. Đừng áp dụng máy móc quy tắc của `instanceof String s` ở cấp cao nhất vào `var s` nằm trong record pattern.
3. **Selector `switch` là null** cần được xử lý riêng. `case null` là cách biểu đạt rõ ràng; đừng kỳ vọng `default` tự thay thế nhánh null trong pattern matching switch.

Record pattern kiểm tra **cấu trúc**, không tự động kiểm tra bất biến nghiệp vụ như “tên không được trống” hay “mã bưu kiện bắt buộc có”. Muốn đảm bảo dữ liệu hợp lệ ngay từ đầu, xác thực trong constructor của record; muốn lọc khi xử lý, dùng guard `when`.

## 7. `when` chạy sau khi toàn bộ nested pattern khớp

Với `switch`, có thể lọc thêm một điều kiện:

```java
case Parcel(
        var code,
        Person(var name, Address(var city, Point(var x, var y))))
        when x >= 0 && y >= 0 ->
    "Điểm có hai tọa độ không âm";
```

Thứ tự **về ý nghĩa** là: đầu vào khớp `Parcel` → component phải khớp từng pattern lồng nhau → các biến `x`, `y` được ràng buộc → đánh giá guard `when` → chạy nhánh nếu guard đúng. Nếu guard sai, `switch` xét nhánh tiếp theo phù hợp. Guard không “cứu” một tầng đã thất bại: nếu `Point` là null, biểu thức `x >= 0` không được đánh giá bằng giá trị `x` giả định nào.

Các biến pattern chỉ có phạm vi trong nơi compiler xác định pattern đã khớp, bao gồm `when` và thân nhánh thành công. Không thể sử dụng `x` hoặc `name` bên ngoài phạm vi ấy.

**Sắp xếp nhánh từ cụ thể đến tổng quát.** Mẫu sau **cố ý không biên dịch** vì nhánh tổng quát che nhánh cụ thể:

```java
// Ví dụ lỗi dominance, không phải chương trình chạy.
return switch (input) {
    case Parcel p -> "Mọi Parcel";
    case Parcel(var code, Person(var name, var address)) ->
        "Không tới được nhánh này";
    default -> "Khác";
};
```

`case Parcel p` đã nhận mọi `Parcel` không-null; nhánh sau bị **dominated**. Đổi vị trí hai nhánh, hoặc dùng nhánh cụ thể/`when` trước rồi dùng nhánh tổng quát để dự phòng.

## 8. So sánh với truy cập accessor thủ công

Nếu không dùng nested pattern, điều kiện tương tự thường phải được diễn đạt bằng nhiều kiểm tra và truy cập:

```java
// Minh họa khái niệm; giả sử input thuộc phạm vi phương thức.
if (input instanceof Parcel p
        && p.receiver() != null
        && p.receiver().address() != null
        && p.receiver().address().point() != null) {
    String code = p.code();
    String name = p.receiver().name();
    String city = p.receiver().address().city();
    int x = p.receiver().address().point().x();
    int y = p.receiver().address().point().y();
    // Dùng code, name, city, x, y...
}
```

Cách thủ công có thể phù hợp khi chỉ dùng một component, cần kiểm tra từng bước có thông báo lỗi riêng, hoặc cần xử lý null theo chính sách phức tạp. Còn nested pattern diễn đạt gọn **“đầu vào có đúng cấu trúc cần tách hay không?”** và ràng buộc biến trực tiếp:

```java
if (input instanceof Parcel(
        var code,
        Person(var name, Address(var city, Point(var x, var y))))) {
    // Dùng code, name, city, x, y...
}
```

Hai đoạn trên chỉ tương đương **về ý định kiểm tra cấu trúc không-null của các record lồng nhau**, không phải phép thay thế cơ học cho mọi logic: record có thể chứa các component null, accessor tùy biến có thể có hành vi đặc biệt, và phép gọi accessor thủ công có thể lặp lại.

Nếu accessor của record tùy biến ném ngoại lệ, quá trình matching có thể kết thúc bằng `MatchException` (có nguyên nhân gốc). Vì thế record/accessor nên đơn giản và ổn định, tránh tác dụng phụ bất ngờ.

## 9. Phương pháp đọc và gỡ lỗi khi gặp pattern rất sâu

Khi gặp một biểu thức dài, áp dụng trình tự sau:

1. **Tìm dấu mở đầu:** pattern bắt đầu bằng record nào? Đối tượng đưa vào có thể mang kiểu đó không?
2. **Đọc khai báo record:** viết ra component theo **thứ tự** của record, không tự gán tên tùy tiện. Mỗi record pattern phải có đúng số component.
3. **Thụt lề theo dấu ngoặc:** mỗi `Type(` tạo một tầng. Gắn pattern thứ nhất với component thứ nhất, pattern thứ hai với component thứ hai.
4. **Đánh dấu lá:** `var v` hoặc `Type v` nhận component vào biến; `OtherRecord(...)` buộc đi sâu và yêu cầu record đó không-null.
5. **Xác định điểm thất bại gần nhất:** hỏi “tầng nào thiếu hoặc sai kiểu?”. Nếu một nested record không khớp, toàn bộ mẫu ngoài thất bại và chuyển sang nhánh khác.
6. **Đọc guard sau cùng:** chỉ khi các tầng khớp mới xét `when`. Với `switch`, kiểm tra thứ tự nhánh và lỗi dominance.
7. **Kiểm tra đầu ra bằng dữ liệu cụ thể:** thử một trường hợp đầy đủ, một trường hợp thiếu record ở mỗi tầng, một trường hợp guard sai, và selector null.

Ví dụ viết lại cho dễ nhìn:

```java
Parcel(
    var code,
    Person(
        var name,
        Address(
            var city,
            Point(
                var x,
                var y
            )
        )
    )
)
```

Mặc dù trải nhiều dòng, đây vẫn là **một pattern duy nhất**, không phải lời gọi constructor `new Parcel(...)`, và các tên `code`, `name`, `city`, `x`, `y` ở đây là **biến được khai báo bởi pattern**, không phải đối số truyền vào constructor.

## 10. Lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết `Parcel(Person(...), var code)` nhưng compiler báo sai | Thứ tự component không khớp `record Parcel(String code, Person receiver)` | Đọc khai báo record trước, sắp đúng vị trí `code` rồi `receiver`. |
| Thiếu hoặc thừa một pattern con | Mỗi record pattern phải đủ số component đã khai báo | Đếm component theo từng cặp ngoặc của từng record. |
| Dùng `Point(...)` với một class thông thường | `Type(...)` là record pattern, chỉ dùng với **record class** | Dùng type pattern cho class thường hoặc đổi mô hình dữ liệu khi phù hợp. |
| `Point(...)` không khớp dù `Address` tồn tại | `Address.point()` là null hoặc giá trị không phù hợp kiểu | Đọc đến tầng `Point` rồi kiểm tra dữ liệu; dùng nhánh nông hơn nếu cần xử lý null. |
| Nghĩ `var name` loại bỏ null | Type pattern trực tiếp trên component có thể **null-matching** | Dùng guard `name != null` hoặc kiểm tra ở constructor. |
| Truy cập `x` sau `switch`/`if` | Biến pattern chỉ trong phạm vi được đảm bảo khớp | Dùng trong thân nhánh hoặc trả kết quả ra ngoài. |
| Nhánh chuyên biệt không thể tới | Đặt nhánh tổng quát ở trước, gây dominance | Đưa nested pattern/guard cụ thể lên trước. |
| `javac` không nhận `record pattern` | Đang dùng JDK dưới 21 hoặc thiết lập ngôn ngữ cũ | Kiểm tra `javac -version` và biên dịch bằng `--release 21` trên JDK 21+. |
| Muốn bỏ qua component bằng `_` trên Java 21 thường | Unnamed patterns là tính năng preview ở Java 21 | Dùng `var unused` có tên hoặc cấu hình preview có chủ đích; bài này chỉ dùng cú pháp ổn định. |

## 11. Bài tập tự kiểm tra

Với `Parcel(var code, Person(var name, Address(var city, Point(var x, var y))))`:

1. Giải thích tại sao `new Parcel("A", null)` không khớp dù ngoài cùng vẫn là `Parcel`. Hãy nêu chính xác tầng thất bại.
2. Viết một pattern nhận `Parcel` có `receiver` khác null nhưng **không yêu cầu** `address` khác null. Đáp án gợi ý: `Parcel(var code, Person(var name, var address))`.
3. Thêm nhánh `when x == y` để nhận riêng những `Point` nằm trên đường `x = y` và đặt đúng thứ tự với nhánh tổng quát.
4. Dùng bảng ở mục 6 dự đoán nhánh được chọn khi `Address.point()` là null và khi `Person.name()` là null; chạy ví dụ để đối chiếu.
5. Đổi `Point(var x, var y)` thành `var point` tại đúng vị trí, giải thích biến mới có kiểu gì và cấu trúc còn được kiểm tra sâu đến đâu.

**Ghi nhớ:** đọc pattern **từ ngoài vào trong theo khai báo component**; `Record(...)` bắt buộc tầng đó là record không-null; `var` có thể giữ nguyên component kể cả null; mọi tầng phải khớp trước khi guard chạy; chọn nhánh cụ thể trước nhánh tổng quát.

## Tài liệu tham khảo

- [Oracle Java 21 — Record Patterns, Nested Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — `14.30, Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
