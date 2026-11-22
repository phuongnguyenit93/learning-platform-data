# Hàm khởi tạo chuẩn và hàm khởi tạo chuẩn rút gọn trong Java Record (Java 17+)

Một `record` khai báo **một kiểu dữ liệu có các thành phần (record components) cố định**. Ví dụ `record Point(int x, int y) {}` khai báo hai components `x` và `y`. Java cung cấp các private final fields tương ứng, accessors `x()` và `y()`, đồng thời sinh các hành vi `equals`, `hashCode`, `toString` dựa trên record components nếu bạn không tự khai báo chúng. Điểm trọng tâm của bài là **constructor khởi tạo tất cả các component fields**.

**Canonical constructor (hàm khởi tạo chuẩn)** nhận đúng các tham số tương ứng với **toàn bộ record components, đúng thứ tự, đúng tên và đúng kiểu**. Nếu không khai báo, compiler cung cấp canonical constructor mặc định. Bạn có thể khai báo tường minh với đầy đủ danh sách tham số và tự gán các fields.

**Compact canonical constructor (hàm khởi tạo chuẩn rút gọn)** là dạng ngắn: chỉ viết tên record và một block `Point { ... }`, **không viết danh sách tham số**. Bạn vẫn có thể kiểm tra và chuẩn hóa các tham số; sau khi block hoàn tất bình thường, compiler **tự gán mỗi component field từ tham số tương ứng**. Vì vậy trong compact constructor, bạn **không được tự gán** `this.x = ...`.

Bài thuộc **Java core – class-object**, nhóm **Record**, chủ đề **Hàm khởi tạo chuẩn và hàm khởi tạo chuẩn rút gọn**. Các ví dụ dùng Java **17 trở lên**, không yêu cầu preview features. Mỗi chương trình đầy đủ có tên file, lệnh chạy và stdout đáng tin; các dòng cố tình không hợp lệ được đánh dấu riêng.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Xác định canonical constructor từ record header, không nhầm với constructor overload.
2. Nhận biết canonical constructor được tạo ngầm khi record không tự khai báo.
3. Viết **explicit canonical constructor** với đúng tên/kiểu/thứ tự tham số và gán đầy đủ fields.
4. Viết **compact constructor** để validation, chuẩn hóa dữ liệu và giữ bất biến (*invariants*).
5. Giải thích chính xác **thời điểm compiler gán component fields** trong compact constructor.
6. Biết vì sao compact constructor **không được gán trực tiếp** các component fields.
7. Xử lý `null`, khoảng giá trị, trim/canonicalization và exception khi dữ liệu sai.
8. Viết non-canonical constructors bằng cách **ủy quyền tới constructor khác của cùng record qua `this(...)`**.
9. Hiểu access modifier phù hợp với accessibility của record.
10. Phân biệt component fields final với **tính bất biến sâu** của object mà component reference trỏ tới.
11. Kiểm thử record accessors, equality và tác động của normalization.
12. Chọn dạng constructor dễ đọc, tránh logic khởi tạo trùng lặp.

## 2. Record header quyết định danh sách thành phần

Xem khai báo:

~~~java
record Point(int x, int y) {
}
~~~

Đây là một **top-level record package-private** hoàn chỉnh. Record header `(int x, int y)` khai báo hai components theo đúng thứ tự `x`, `y`. Khi không có constructor do bạn tự viết, compiler tạo canonical constructor tương đương về hành vi với việc nhận `x`, `y` rồi gán hai private final fields tương ứng.

Bạn có thể dùng:

~~~java
Point point = new Point(3, 4);
int first = point.x();
int second = point.y();
~~~

Đây là snippet hợp lệ trong method cùng package; accessors là `x()`, `y()`, **không tự động là** `getX()` hay `getY()`. Không có setter mặc định.

Một điểm quan trọng: **record không chỉ là cách rút ngắn một class viết tay**. Record có hợp đồng cấu trúc về các components, canonical constructor và hành vi dữ liệu minh bạch. Tuy nhiên, nếu component là reference tới object mutable, record không tự biến object đó thành immutable.

## 3. Chương trình hoàn chỉnh 1 — canonical constructor ngầm định

Tạo file **`ImplicitCanonicalDemo.java`**:

~~~java
record Point(int x, int y) {
}

public class ImplicitCanonicalDemo {
    public static void main(String[] args) {
        Point first = new Point(3, 4);
        Point second = new Point(3, 4);
        Point third = new Point(3, 5);

        System.out.println("x=" + first.x());
        System.out.println("y=" + first.y());
        System.out.println("point=" + first);
        System.out.println("equal=" + first.equals(second));
        System.out.println("different=" + first.equals(third));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImplicitCanonicalDemo.java
java ImplicitCanonicalDemo
~~~

**Stdout:**

~~~text
x=3
y=4
point=Point[x=3, y=4]
equal=true
different=false
~~~

Không cần tự viết constructor `Point(int x, int y)`. Với khai báo trên, canonical constructor do compiler cung cấp thiết lập hai fields. `equals` so giá trị các components theo quy tắc record; hai Points cùng x/y được coi là equal.

Tên kiểu `Point` trong cùng file là package-private, còn `ImplicitCanonicalDemo` là public class trùng tên file. Hai top-level declarations như vậy hoàn toàn hợp lệ.

## 4. Chính xác thế nào là canonical constructor?

Với:

~~~java
record Customer(String id, int points, boolean active) {
}
~~~

canonical constructor có danh sách formal parameters tương ứng:

~~~java
Customer(String id, int points, boolean active)
~~~

**Phải khớp toàn bộ** thành phần về **thứ tự, tên, kiểu**. Không phải một constructor chỉ “có cùng số lượng tham số” là đủ. Bạn không được tùy tiện đổi `String id` thành `String customerId` trong một khai báo explicit canonical constructor.

| Thành phần header | Canonical formal parameter |
| --- | --- |
| `String id` | `String id` |
| `int points` | `int points` |
| `boolean active` | `boolean active` |

Một constructor có signature khác, chẳng hạn `Customer(String id)`, là **non-canonical constructor**; nó phải thực hiện constructor invocation phù hợp tới một constructor khác của cùng record, để quá trình khởi tạo đi qua canonical constructor.

Java không cho record khai báo thêm **instance fields riêng** ngoài các fields tương ứng components; record có thể có static fields, instance/static methods và nested types phù hợp. Vì vậy canonical constructor là điểm tập trung lý tưởng để xây dựng invariant của trạng thái record.

## 5. Explicit canonical constructor — bạn tự gán fields

Nếu cần kiểm tra dữ liệu và muốn viết logic gán một cách tường minh:

~~~java
record Coordinate(int row, int column) {
    Coordinate(int row, int column) {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException("negative");
        }

        this.row = row;
        this.column = column;
    }
}
~~~

Đây là **record hợp lệ**. Dòng `this.row = row` và `this.column = column` là trách nhiệm của **explicit canonical constructor**. Vì record component fields là final, mỗi field phải được gán hợp lệ trước khi constructor hoàn tất bình thường.

Nếu bạn quên `this.column = column`, Java sẽ phát hiện field chưa được khởi tạo trên đường hoàn tất constructor; chương trình không biên dịch.

Nếu dữ liệu không hợp lệ, ném `IllegalArgumentException` trong constructor là một lựa chọn phù hợp với nhiều value objects. Cũng có thể dùng loại exception khác theo hợp đồng API, nhưng không nên xây dựng object có trạng thái sai rồi chỉ xử lý khi sử dụng.

## 6. Chương trình hoàn chỉnh 2 — explicit canonical constructor

Tạo file **`ExplicitCanonicalDemo.java`**:

~~~java
record Coordinate(int row, int column) {
    Coordinate(int row, int column) {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException(
                    "coordinates must be non-negative");
        }
        this.row = row;
        this.column = column;
    }
}

public class ExplicitCanonicalDemo {
    public static void main(String[] args) {
        Coordinate a = new Coordinate(2, 5);
        System.out.println("coordinate=" + a);
        System.out.println("row=" + a.row());

        try {
            new Coordinate(-1, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ExplicitCanonicalDemo.java
java ExplicitCanonicalDemo
~~~

**Stdout:**

~~~text
coordinate=Coordinate[row=2, column=5]
row=2
invalid=coordinates must be non-negative
~~~

Bởi constructor tự gán `this.row` và `this.column`, việc bỏ một phép gán có thể làm fail compile. Đổi lại, bạn kiểm soát rõ thời điểm và giá trị được gán, hữu ích khi constructor cần chuyển đổi dữ liệu theo logic phức tạp.

## 7. Compact canonical constructor — cú pháp rút gọn

Vẫn với hai components, có thể viết:

~~~java
record Coordinate(int row, int column) {
    Coordinate {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
~~~

Đây là **record hợp lệ**. `Coordinate { ... }` là **compact canonical constructor**, không viết `(int row, int column)`.

Compiler cung cấp tham số `row`, `column` tương ứng header. Chúng được dùng trực tiếp trong body để validation hoặc normalization. Sau khi body hoàn tất bình thường, compiler thực hiện các phép gán tương ứng:

~~~java
// Mô hình tư duy, không phải code được viết bên trong compact constructor:
// this.row = row;
// this.column = column;
~~~

Đây chỉ là **mô tả hành vi**. Không copy các dòng `this.field = parameter` vào body compact constructor: điều đó trái quy tắc của ngôn ngữ. Hai kiểu constructor có **cùng trách nhiệm khởi tạo trạng thái**, nhưng nơi xuất hiện phép gán field là khác nhau.

## 8. Chương trình hoàn chỉnh 3 — compact constructor validate invariant

Tạo file **`CompactRangeDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException(
                    "start must not exceed end");
        }
    }

    int length() {
        return end - start;
    }
}

public class CompactRangeDemo {
    public static void main(String[] args) {
        Range first = new Range(2, 7);
        Range zero = new Range(5, 5);

        System.out.println("range=" + first);
        System.out.println("length=" + first.length());
        System.out.println("zero=" + zero.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CompactRangeDemo.java
java CompactRangeDemo
~~~

**Stdout:**

~~~text
range=Range[start=2, end=7]
length=5
zero=0
invalid=start must not exceed end
~~~

Constructor rút gọn chỉ kiểm tra mối quan hệ giữa hai tham số. Không có lệnh gán `this.start` và `this.end`, bởi compiler đã xử lý sau khi body hoàn thành.

Method `length()` là method tự định nghĩa thêm, không phải accessor của một record component tên length. Nếu interval theo quy tắc inclusive, cách tính có thể là `end - start + 1`; bài dùng khoảng cách đơn giản `end - start` để tránh nhập nhằng nghiệp vụ.

## 9. Thứ tự khởi tạo: điều gì xảy ra trước và sau body compact?

Đối với một compact constructor:

1. Các đối số của `new RecordType(...)` được đánh giá theo quy tắc Java.
2. Một record object mới được tạo và quá trình construction được thực hiện.
3. Các tham số tương ứng record components đã có giá trị để body constructor sử dụng.
4. Code trong compact constructor chạy: validation, normalization hoặc exception.
5. **Nếu body hoàn tất bình thường**, component fields được gán từ các tham số tương ứng như quy định ngôn ngữ.
6. Construction hoàn tất; caller nhận reference object hợp lệ.

Nếu code ở bước 4 ném exception, đối tượng **không được trả về như kết quả thành công** của `new`. Không có quá trình “tạo record với fields sai rồi sửa về sau”.

**Cảnh báo:** trong compact constructor, đừng đọc trạng thái component fields của `this` để thay cho các tham số cùng tên trước khi chúng được gán. Hãy kiểm tra trực tiếp `start`, `end`, `name` v.v. Việc gọi instance methods có thể đưa `this` chưa khởi tạo hoàn tất ra ngoài hoặc quan sát trạng thái không mong muốn.

## 10. Vì sao `this.component = ...` không hợp lệ trong compact constructor?

Đây là một **đoạn cố ý không biên dịch**:

~~~java
record BadPoint(int x, int y) {
    BadPoint {
        this.x = x; // Lỗi: gán component field trong compact constructor.
        this.y = y; // Lỗi tương tự.
    }
}
~~~

Trong compact constructor, compiler dành riêng việc khởi tạo các component fields cho bước **sau body**. Việc tự gán fields không chỉ dư thừa mà còn **bị cấm**.

Đừng chữa bằng cách bỏ `this.` và viết `x = x;`: câu lệnh ấy chỉ gán một tham số cho chính nó, không thực hiện tác vụ chuẩn hóa nào và khiến code khó đọc.

Nếu muốn tự gán fields, hãy dùng **explicit canonical constructor** với danh sách formal parameters đầy đủ. Nếu muốn kiểm tra/chỉnh giá trị tham số rồi để compiler tự gán, hãy dùng **compact constructor**.

## 11. Compact constructor có thể chuẩn hóa tham số

Các tham số `name` và `email` của compact constructor không bị xem là `final` chỉ vì các component fields là final. Bạn có thể **gán lại chính tham số**, rồi compiler dùng **giá trị mới** để khởi tạo field.

~~~java
record Username(String value) {
    Username {
        if (value == null) {
            throw new IllegalArgumentException("missing name");
        }
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank name");
        }
    }
}
~~~

Đây là một khai báo hợp lệ. Một lời gọi `new Username("  An  ")` sẽ tạo object có `value()` là `"An"`.

Thay đổi **tham số** trong compact body hoàn toàn khác với việc sửa component field sau construction. Component field vẫn được gán một lần trong quá trình tạo record, rồi không thể thay đổi.

**Lưu ý thiết kế:** normalization phải phù hợp domain. Không tự `trim`, lowercase, viết hoa, xóa dấu hay chuẩn hóa Unicode với mọi loại dữ liệu, vì những phép biến đổi ấy có thể làm mất thông tin có ý nghĩa.

## 12. Chương trình hoàn chỉnh 4 — canonicalize dữ liệu chuỗi

Tạo file **`CompactNormalizationDemo.java`**:

~~~java
import java.util.Locale;

record LoginName(String value) {
    LoginName {
        if (value == null) {
            throw new IllegalArgumentException("missing");
        }
        value = value.strip().toLowerCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank");
        }
    }
}

public class CompactNormalizationDemo {
    public static void main(String[] args) {
        LoginName first = new LoginName("  AN  ");
        LoginName second = new LoginName("an");

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("same value="
                + first.equals(second));

        try {
            new LoginName("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CompactNormalizationDemo.java
java CompactNormalizationDemo
~~~

**Stdout:**

~~~text
first=an
second=an
same value=true
invalid=blank
~~~

Hai lời gọi có tham số ban đầu khác nhau, nhưng compact constructor chuẩn hóa thành cùng `value="an"`, nên record-generated `equals` coi chúng bằng nhau.

`Locale.ROOT` được chọn để tránh để một locale mặc định của máy làm khác kết quả lowercasing cho các trường hợp đặc biệt. Chính sách đăng nhập thực tế vẫn cần định nghĩa rõ Unicode normalization, allowed characters và tính duy nhất trên database; ví dụ chỉ minh họa normalization trong constructor.

## 13. Tương đương về invariant: explicit và compact

Cùng ý tưởng buộc chuỗi không null và đã bỏ whitespace đầu/cuối:

**Explicit canonical constructor:**

~~~java
record TagExplicit(String text) {
    TagExplicit(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        this.text = text.strip();
    }
}
~~~

**Compact canonical constructor:**

~~~java
record TagCompact(String text) {
    TagCompact {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        text = text.strip();
    }
}
~~~

Đây là **hai record declarations hợp lệ**. Hai kiểu constructor đều có thể tạo invariant `text` không null và đã strip. Sự khác nhau là:

| Việc | Explicit canonical | Compact canonical |
| --- | --- | --- |
| Viết danh sách parameters | Có, đúng header | Không |
| Truy cập input trong body | Qua tham số `text` | Qua tham số ngầm `text` |
| Tự khởi tạo `this.text` | Phải làm | Không được làm |
| Có thể normalize | Có | Có, bằng cách đổi tham số |
| Quên field assignment gây lỗi | Có thể mắc lỗi compile-time | Compiler gán tự động |
| Chỗ thích hợp | Cần kiểm soát gán phức tạp | Validation/normalization ngắn gọn |

**Cùng invariant không có nghĩa tạo cùng kiểu:** `TagExplicit` và `TagCompact` là hai record types khác nhau. So sánh `new TagExplicit("A")` với `new TagCompact("A")` bằng `equals` không tạo equality xuyên hai kiểu record.

## 14. Chương trình hoàn chỉnh 5 — so sánh hai dạng constructor

Tạo file **`ConstructorFormsDemo.java`**:

~~~java
record ExplicitTag(String text) {
    ExplicitTag(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        this.text = text.strip();
    }
}

record CompactTag(String text) {
    CompactTag {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        text = text.strip();
    }
}

public class ConstructorFormsDemo {
    public static void main(String[] args) {
        ExplicitTag a = new ExplicitTag("  java ");
        CompactTag b = new CompactTag("  java ");

        System.out.println("explicit=" + a.text());
        System.out.println("compact=" + b.text());
        System.out.println("same content="
                + a.text().equals(b.text()));
        System.out.println("different records="
                + a.equals(b));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorFormsDemo.java
java ConstructorFormsDemo
~~~

**Stdout:**

~~~text
explicit=java
compact=java
same content=true
different records=false
~~~

Hai implementations đặt field text thành `"java"` sau normalization. Nhưng `a.equals(b)` false vì hai objects là instances của **hai record types khác nhau**, dù contents của chúng là chuỗi giống nhau.

## 15. `Objects.requireNonNull` và thông điệp lỗi

Với reference components, record **không tự cấm null**. Nếu cần invariant non-null, bạn phải chủ động đặt điều kiện ở constructor:

~~~java
import java.util.Objects;

record ProductCode(String code) {
    ProductCode {
        Objects.requireNonNull(code, "code");
    }
}
~~~

Đây là một khai báo hợp lệ. `new ProductCode(null)` ném `NullPointerException` với message `"code"`. Bạn cũng có thể dùng `IllegalArgumentException` nếu policy của API thích hợp; quan trọng là **nhất quán và tài liệu hóa**.

Khác biệt:

- `Objects.requireNonNull`: không nhận giá trị null, không xử lý blank strings.
- `String.isBlank()`: kiểm tra whitespace Unicode theo `Character.isWhitespace` nếu String không null.
- `String.strip()`: bỏ whitespace đầu/cuối theo quy tắc Java, không tự validate độ dài hay định dạng.
- `List.copyOf(...)`: tạo list unmodifiable từ collection, nhưng từ chối null elements và không deep copy object elements.
- Validate bằng regex hoặc parser: thích hợp khi domain định nghĩa chính xác format.

Hãy xem validation như **hợp đồng public của value object**, không chỉ là một trick cú pháp constructor.

## 16. Chương trình hoàn chỉnh 6 — null, blank và khoảng số

Tạo file **`RecordValidationDemo.java`**:

~~~java
import java.util.Objects;

record AccountInput(String owner, int age) {
    AccountInput {
        Objects.requireNonNull(owner, "owner");
        owner = owner.strip();

        if (owner.isEmpty()) {
            throw new IllegalArgumentException("blank owner");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("invalid age");
        }
    }
}

public class RecordValidationDemo {
    public static void main(String[] args) {
        AccountInput accepted =
                new AccountInput("  An  ", 20);

        System.out.println("accepted=" + accepted);

        try {
            new AccountInput(null, 20);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }

        try {
            new AccountInput("   ", 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getMessage());
        }

        try {
            new AccountInput("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("age=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RecordValidationDemo.java
java RecordValidationDemo
~~~

**Stdout:**

~~~text
accepted=AccountInput[owner=An, age=20]
null=owner
blank=blank owner
age=invalid age
~~~

Constructor rút gọn đảm bảo sau construction, mọi AccountInput hợp lệ có owner khác null/không rỗng sau strip và age trong khoảng quy định. `toString()` được record sinh từ component fields sau khi đã chuẩn hóa.

Không phải chương trình nào cũng nên dùng giới hạn tuổi 150; đó là ví dụ về **policy cụ thể** và cần được điều chỉnh cho domain.

## 17. Canonical constructor không được khai báo `throws` clause

Đây là một khác biệt quan trọng giữa constructor record và constructor class thường. Theo JLS 17, **canonical constructor của record không được có `throws` clause**. Vì vậy đoạn sau là **cố ý không biên dịch**:

~~~java
record InvalidRecord(String raw) {
    InvalidRecord(String raw) throws java.io.IOException {
        this.raw = raw;
    }
}
~~~

Với **compact constructor** cũng không khai báo tham số hoặc `throws` clause:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
record InvalidCompact(String raw) {
    InvalidCompact throws java.io.IOException {
    }
}
~~~

Bạn vẫn có thể ném **unchecked exceptions** như `IllegalArgumentException` hay `NullPointerException` khi validation sai. Nếu validation phụ thuộc I/O gây checked exception, xem xét một **factory method** có tên có thể khai báo `throws`, rồi trả về một record sau khi đã có dữ liệu được xác thực.

Tránh thực hiện I/O phức tạp ngay trong constructor của một record chỉ nhằm đại diện cho value data. Nếu cần nạp file hay truy vấn dịch vụ, tách hoạt động đó khỏi construction.

## 18. Quy tắc access của canonical constructor

Một record có accessibility cụ thể, canonical constructor phải có access **không hẹp hơn** access của record. Ví dụ, record public cần một canonical constructor public nếu bạn tự khai báo explicit/compact canonical constructor.

~~~java
public record PublicPoint(int x, int y) {
    public PublicPoint {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
~~~

Đây là **nội dung hợp lệ của file `PublicPoint.java`**, dùng như một đoạn minh họa. Với public record, modifier `public` được đặt trước compact constructor.

Dạng explicit tương ứng:

~~~java
public record PublicPoint(int x, int y) {
    public PublicPoint(int x, int y) {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
        this.x = x;
        this.y = y;
    }
}
~~~

Đây là **phiên bản thay thế**, không ghép cùng phiên bản compact vào một file do sẽ tạo hai canonical constructors trùng nhau.

Với record package-private, canonical constructor có thể package-private như các demo trước. **Đừng tự làm hẹp quyền truy cập** của canonical constructor public record chỉ vì bạn muốn object được tạo qua một factory; hợp đồng record có các ràng buộc riêng với canonical constructor.

## 19. Không thể có hai canonical constructors khác nhau cho cùng record

Đây là **đoạn cố ý không biên dịch**:

~~~java
record BadPair(int left, int right) {
    BadPair {
        if (left > right) {
            throw new IllegalArgumentException("wrong order");
        }
    }

    BadPair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}
~~~

Hai phần trên đều tuyên bố **cùng canonical constructor**, một dạng compact, một dạng explicit. Compiler không cho phép chúng cùng tồn tại.

Bạn cần **chọn một**:

- Compact khi chỉ cần validate hoặc normalize parameters, để compiler tự gán fields.
- Explicit khi cần kiểm soát trực tiếp việc gán fields và phù hợp các quy tắc strict definite assignment.

Đừng gọi đó là “overload” vì hai constructor có cùng canonical signature; overload phải có **danh sách tham số khác**.

## 20. Non-canonical constructor: phải ủy quyền bằng `this(...)`

Record có thể có các overloaded constructors để hỗ trợ cách tạo thuận tiện, nhưng **mọi non-canonical constructor phải bắt đầu bằng một lời gọi explicit constructor invocation tới constructor khác của cùng record** theo quy tắc Java 17.

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
    }

    Range(int end) {
        this(0, end);
    }
}
~~~

Đây là record hợp lệ:

- `Range(int start, int end)` là compact canonical constructor được tuyên bố qua `Range { ... }`.
- `Range(int end)` là non-canonical overload.
- `this(0, end)` đứng đầu overload, đưa dữ liệu vào canonical constructor.
- Validation tại canonical constructor vẫn chạy với mọi cách tạo thành công.

**Không thể** dùng non-canonical constructor để bỏ qua validation bằng cách tự set fields. Record có thiết kế tập trung component initialization qua canonical constructor.

## 21. Chương trình hoàn chỉnh 7 — overload gọi canonical constructor

Tạo file **`DelegatingRecordConstructorDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
    }

    Range(int end) {
        this(0, end);
    }

    int size() {
        return end - start;
    }
}

public class DelegatingRecordConstructorDemo {
    public static void main(String[] args) {
        Range shortForm = new Range(5);
        Range fullForm = new Range(2, 8);

        System.out.println("short=" + shortForm);
        System.out.println("full=" + fullForm);
        System.out.println("size=" + fullForm.size());

        try {
            new Range(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 DelegatingRecordConstructorDemo.java
java DelegatingRecordConstructorDemo
~~~

**Stdout:**

~~~text
short=Range[start=0, end=5]
full=Range[start=2, end=8]
size=6
invalid=invalid range
~~~

Lời gọi `new Range(-1)` đi qua overload `Range(int end)` rồi tới canonical constructor với `start=0,end=-1`, nơi invariant `start <= end` bị vi phạm và exception được ném.

Một lợi thế quan trọng của việc ủy quyền: **mọi con đường tạo object dùng chung một chỗ validate**.

## 22. Những lỗi phổ biến ở overload

**Cố ý không biên dịch:** non-canonical constructor không gọi `this(...)` đầu tiên:

~~~java
record BadOverload(int value) {
    BadOverload() {
        System.out.println("initializing");
        this(0);
    }
}
~~~

Trong Java 17, một explicit constructor invocation như `this(0)` phải là **statement đầu tiên** của constructor body tương ứng. Không được thêm lệnh log hoặc validation trước nó ở overload.

Một overload khác **cố ý không biên dịch** nếu cố gán component field:

~~~java
record BadOverload(int value) {
    BadOverload() {
        this.value = 0;
    }
}
~~~

Non-canonical constructor không được xây “đường riêng” tự gán component fields, mà phải ủy quyền qua `this(...)` theo quy tắc record. Muốn cấp default value, viết `this(0)`.

**Mẹo thiết kế:** tính biểu thức default đơn giản ngay trong arguments của `this(...)` hoặc đưa logic nặng ra một static helper/factory. Tuyệt đối không tạo vòng `this(...)` constructor delegation vô hạn.

## 23. Null checks và defensive copy cho collection components

Record có các fields final, nhưng nếu một component là `List<String>`, bản thân list có thể mutable. Ví dụ:

~~~java
record Team(String name, java.util.List<String> members) {
}
~~~

Nếu caller tạo `new Team("A", mutableList)` rồi sửa mutableList, record sẽ **quan sát sự thay đổi** vì component reference trỏ tới cùng object. `final` khóa reference field, không làm list immutable.

Một compact constructor có thể tạo **defensive snapshot**:

~~~java
record Team(String name, java.util.List<String> members) {
    Team {
        java.util.Objects.requireNonNull(name, "name");
        java.util.Objects.requireNonNull(members, "members");
        members = java.util.List.copyOf(members);
    }
}
~~~

Đây là record hợp lệ. Sau body, field `members` được gán **list copy** thay vì reference list mà caller truyền vào. `List.copyOf` trả list unmodifiable, từ chối null elements, nhưng **không deep-copy các mutable elements bên trong**.

Nếu component list chứa `String` immutable, pattern này rất phù hợp cho snapshot cấu trúc. Nếu chứa các objects mutable, phải xét thêm quyền sở hữu/deep copy của elements.

## 24. Chương trình hoàn chỉnh 8 — constructor rút gọn chụp snapshot list

Tạo file **`DefensiveCopyRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}

public class DefensiveCopyRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team("Core", source);
        source.add("Binh");

        System.out.println("source=" + source);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutation="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DefensiveCopyRecordDemo.java
java DefensiveCopyRecordDemo
~~~

**Stdout:**

~~~text
source=[An, Binh]
team=[An]
mutation=UnsupportedOperationException
~~~

Record constructor tạo một snapshot cấu trúc có một phần tử An. Caller sửa source sau đó không đổi `team.members()`. Accessor được compiler cung cấp trả list unmodifiable, nên `add` ném UnsupportedOperationException.

**Không suy rằng mọi record luôn immutable sâu**. Kết quả này có được nhờ **defensive copy trong compact constructor**, không chỉ nhờ record declaration.

## 25. Array components: cần xử lý cả lúc khởi tạo và accessor

Với `byte[]`, `int[]`, `String[]`, copy trong constructor chỉ bảo vệ trước việc caller sửa **mảng nguồn**. Record accessor mặc định lại trả **cùng array field reference**; caller có thể sửa mảng bên trong record sau khi tạo.

Một chính sách defensive copy đầy đủ cho array thường cần:

1. Clone input trong compact constructor: `data = data.clone();`.
2. Override accessor `data()` để trả `data.clone()`.
3. Nếu muốn **value equality** theo nội dung mảng, tự thiết kế `equals`/`hashCode` phù hợp; record-generated implementations không tự deep-compare array elements.

Đừng coi `Arrays.equals` và record-generated `equals` tương đương. Với array components, record-generated `equals` dùng equality theo giá trị component object tương ứng, và array không override `Object.equals` để so nội dung.

Đối với data model chủ yếu mang collection, một `List` snapshot có thể đơn giản hơn array nếu API không yêu cầu mảng hiệu năng/interop.

## 26. Chương trình hoàn chỉnh 9 — compact constructor nhận mảng

Để quan sát rõ **compact constructor chuẩn hóa parameter trước khi Java gán component field**, tạo file **`CompactArrayConstructorDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record Samples(int[] values) {
    Samples {
        values = Objects.requireNonNull(values, "values").clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class CompactArrayConstructorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Samples saved = new Samples(source);

        source[0] = 9;
        int[] returned = saved.values();
        returned[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("returned=" + Arrays.toString(returned));
        System.out.println("saved=" + Arrays.toString(saved.values()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CompactArrayConstructorDemo.java
java CompactArrayConstructorDemo
~~~

Stdout:

~~~text
source=[9, 2]
returned=[1, 8]
saved=[1, 2]
~~~

Trong compact constructor, `values` là **parameter** được thay bằng bản sao trước implicit assignment vào final component field. Việc getter trả clone là một **accessor method** được khai báo tường minh, tách biệt với constructor; nếu chỉ copy khi nhận, getter mặc định vẫn có thể làm lộ mảng.

Ví dụ này tập trung **constructor timing và initialization**, không sử dụng `equals` để tránh trộn hai hợp đồng khác nhau. Cách thiết kế value equality cho array component nằm ở bài chuyên biệt về `equals/hashCode/toString`.

## 27. Record generic vẫn dùng canonical constructor theo components

Record có thể khai báo type parameter:

~~~java
record Pair<T>(T first, T second) {
    Pair {
        java.util.Objects.requireNonNull(first, "first");
        java.util.Objects.requireNonNull(second, "second");
    }
}
~~~

Đây là một record hợp lệ. Compact constructor **không** viết lại `<T>` hoặc danh sách `(T first, T second)`; tham số được suy ra từ header.

Trong method có thể viết:

~~~java
Pair<String> pair = new Pair<>("A", "B");
~~~

Đây là snippet hợp lệ. Generic type parameter `T` là một phần của record declaration, không phải type parameter riêng của canonical constructor.

Nếu viết explicit canonical constructor, phải giữ types tương ứng header (`T first`, `T second`), không tạo một generic method/constructor độc lập làm thay đổi signature canonical.

## 28. Chương trình hoàn chỉnh 10 — generic record với compact constructor

Tạo file **`GenericRecordConstructorDemo.java`**:

~~~java
import java.util.Objects;

record Pair<T>(T first, T second) {
    Pair {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");
    }

    Pair<T> swapped() {
        return new Pair<>(second, first);
    }
}

public class GenericRecordConstructorDemo {
    public static void main(String[] args) {
        Pair<String> pair = new Pair<>("A", "B");
        Pair<String> swapped = pair.swapped();

        System.out.println("pair=" + pair);
        System.out.println("swapped=" + swapped);
        System.out.println("same=" + pair.equals(swapped));

        try {
            new Pair<>("A", null);
        } catch (NullPointerException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericRecordConstructorDemo.java
java GenericRecordConstructorDemo
~~~

**Stdout:**

~~~text
pair=Pair[first=A, second=B]
swapped=Pair[first=B, second=A]
same=false
invalid=second
~~~

`swapped()` không sửa record hiện tại: nó tạo **một Pair mới** và chạy lại canonical constructor, do đó invariant non-null được bảo toàn. Đây là cách thể hiện thay đổi dữ liệu theo phong cách value object.

## 29. Khai báo record không đồng nghĩa tự động validation

Với:

~~~java
record Percentage(int value) {
}
~~~

compiler vẫn chấp nhận `new Percentage(-10)` và `new Percentage(1000)`. Vì `int` không có thêm ràng buộc domain, record header tự nó **không** biết khoảng 0–100.

Thêm compact constructor:

~~~java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "outside 0..100");
        }
    }
}
~~~

làm policy thành một phần của **invariant**: mọi call thông thường qua canonical constructor đều phải thỏa khoảng giá trị.

Cần phân biệt **“định nghĩa cấu trúc dữ liệu”** và **“xác định dữ liệu nào được coi là hợp lệ”**. Dạng compact giảm boilerplate, nhưng quyết định ràng buộc vẫn thuộc domain design.

## 30. Chương trình hoàn chỉnh 11 — constructor kiểm tra giới hạn

Tạo file **`PercentageRecordDemo.java`**:

~~~java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "outside 0..100");
        }
    }

    boolean isComplete() {
        return value == 100;
    }
}

public class PercentageRecordDemo {
    public static void main(String[] args) {
        Percentage half = new Percentage(50);
        Percentage full = new Percentage(100);

        System.out.println("half=" + half);
        System.out.println("half complete=" + half.isComplete());
        System.out.println("full complete=" + full.isComplete());

        try {
            new Percentage(101);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PercentageRecordDemo.java
java PercentageRecordDemo
~~~

**Stdout:**

~~~text
half=Percentage[value=50]
half complete=false
full complete=true
invalid=outside 0..100
~~~

Record có method bổ sung `isComplete()` như một hàm tính toán từ component bất biến. Không cần một field `complete` mới được cập nhật riêng — nhờ vậy state không bị trùng lặp.

## 31. Cách viết canonical explicit để chuẩn hóa phức tạp

Compact constructor đủ cho đa số validation/normalization ngắn. Nhưng explicit canonical đôi khi dễ trình bày hơn nếu các giá trị được tính qua nhiều bước và muốn gán field đúng một lần ở cuối.

Ví dụ:

~~~java
record Rectangle(int width, int height) {
    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("non-positive");
        }

        int normalizedWidth = width;
        int normalizedHeight = height;
        this.width = normalizedWidth;
        this.height = normalizedHeight;
    }
}
~~~

Đây là record hợp lệ, nhưng ở ví dụ này các biến `normalizedWidth`, `normalizedHeight` không mang lại lợi ích; compact constructor sẽ ngắn và rõ hơn.

Chỉ nên chọn explicit form khi việc tự điều khiển assignments thực sự cải thiện cách đọc. **Không dùng explicit form để né validation hoặc tạo record fields chưa khởi tạo** — compiler vẫn enforce rules của final fields và canonical constructor.

## 32. Những quy tắc cần nhớ của explicit canonical constructor

Một explicit canonical constructor của record cần tuân các yêu cầu quan trọng:

- Danh sách formal parameters **khớp record components** về tên, kiểu, thứ tự.
- Không được khai báo type parameters riêng cho canonical constructor.
- Không được khai báo `throws` clause.
- Không dùng explicit constructor invocation `this(...)` hoặc `super(...)` trong canonical constructor.
- Không được khai báo lại instance fields tương ứng components để thay thế generated fields.
- Component fields là final; bạn phải thực hiện các assignments hợp lệ và đầy đủ khi constructor hoàn tất bình thường.
- Access của canonical constructor ít nhất bằng access của record.
- Nếu có một canonical constructor do bạn khai báo, compiler **không cung cấp thêm** một canonical constructor mặc định thứ hai.

Dạng compact khác explicit ở chỗ không có formal parameter list và không viết assignments tới component fields.

Các ràng buộc này bảo đảm record construction có cấu trúc dễ dự đoán, tránh một object có nửa số components chưa khởi tạo nhưng vẫn được công bố ra ngoài.

## 33. Những quy tắc cần nhớ của compact canonical constructor

Đối với compact constructor:

- Viết `RecordName { statements }`, **không có parentheses**.
- Formal parameters tương ứng record components được cung cấp ngầm.
- Dùng tên tham số như `name`, `amount`, `items` để validate hoặc normalize.
- Có thể gán lại tham số (`name = name.strip()`) nếu thích hợp.
- **Không gán trực tiếp** `this.name`, `this.amount` v.v.
- Không có `throws` clause và không khai báo type parameters riêng.
- Không đặt explicit constructor invocation `this(...)` hoặc `super(...)` trong body.
- Không viết `return` statement để thoát compact constructor.
- Sau body hoàn tất bình thường, compiler tự gán toàn bộ component fields.
- Nếu body ném unchecked exception, construction thất bại.
- Phải tuân access của canonical constructor theo record access.

Phần lớn record cần validation hoặc defensive copy nên dùng **compact form** vì tránh boilerplate và giảm khả năng quên gán field.

## 34. Không lạm dụng validation khi constructor cần được tái sử dụng

Constructor record cần tạo một object hợp lệ. Nó không nên đảm nhiệm những nhiệm vụ như:

- Tự gọi HTTP API hoặc database để tải tham chiếu ngoài.
- Ghi log chứa password/token nhạy cảm rồi ném exception.
- Tạo thread và công bố `this` trong lúc component fields chưa được gán xong.
- Thực hiện side effects không rollback được trước khi validation hoàn tất.
- Ngầm đổi dữ liệu nghiệp vụ theo quy tắc người gọi không biết.
- Tự làm các operation có blocking/unbounded cost chỉ để “tạo một value”.

Khi tạo dữ liệu cần I/O, dùng một factory/service để xử lý I/O và trả một record đã được kiểm tra. Constructor nên nhanh, deterministic và dễ unit-test nếu có thể.

Trong compact constructor, việc fields được gán **sau body** càng nhấn mạnh không nên công bố `this` từ initializer/constructor. Đừng gọi instance callbacks trong bước chuẩn hóa.

## 35. Record component với mutable object cần thận trọng về equality

Generated record `equals` và `hashCode` dựa trên component values theo hợp đồng của record. Nếu component là một object mutable, có hai nguy cơ:

1. Object mutable thay đổi sau construction có thể làm thay đổi kết quả quan sát qua accessors hoặc equality/hashCode.
2. Với các kiểu như array, equality theo default object identity **không tương đương deep element equality**.

Vì vậy:

- Với `String`, `Integer`, immutable value objects, canonical constructor thường đơn giản.
- Với `List<String>`, có thể tạo `List.copyOf` snapshot.
- Với `Map<K,V>`, có thể cân nhắc `Map.copyOf`, nhưng nhớ null policy và mutable values.
- Với `int[]`, clone ở đầu vào/đầu ra nếu muốn chống mutation, rồi xác định equality riêng.
- Với domain mutable objects, constructor có thể cần defensive copy sâu hoặc đổi representation.

Không nên xem `record` là đồng nghĩa của **deep immutable aggregate**. Java chỉ tự bảo đảm structural constraints của record fields, còn tính bất biến của object graph do bạn thiết kế.

## 36. Constructor được gọi khi tạo qua các đường khác nhau

Trong Java 17, record construction không chỉ xuất hiện với biểu thức `new SomeRecord(...)`. Một số framework, reflection APIs hoặc record serialization cũng có thể dựa vào canonical constructor theo hợp đồng riêng của chúng.

Đối với cơ chế serialization được Java hỗ trợ cho serializable records, canonical constructor đóng vai trò trong quá trình khôi phục record. Điều đó làm validation ở constructor càng quan trọng, nhưng không biến validation thành thay thế cho kiểm soát trust boundary ở application layer.

Trong code nghiệp vụ, nên test rằng mọi đường tạo dữ liệu mà bạn công bố đều **không bỏ qua invariant**. Đừng dựa vào setters để “sửa record sau khi tạo”; record components không có setters do compiler cung cấp.

## 37. Chương trình hoàn chỉnh 12 — introspection các record components

Tạo file **`RecordConstructorReflectionDemo.java`**:

~~~java
import java.lang.reflect.RecordComponent;

record Key(String namespace, String value) {
    Key {
        if (namespace == null || value == null) {
            throw new IllegalArgumentException("missing");
        }
    }
}

public class RecordConstructorReflectionDemo {
    public static void main(String[] args) {
        Class<Key> type = Key.class;

        System.out.println("isRecord=" + type.isRecord());

        for (RecordComponent component :
                type.getRecordComponents()) {
            System.out.println(component.getName() + ":"
                    + component.getType().getSimpleName());
        }

        Key key = new Key("orders", "A1");
        System.out.println("key=" + key);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RecordConstructorReflectionDemo.java
java RecordConstructorReflectionDemo
~~~

**Stdout:**

~~~text
isRecord=true
namespace:String
value:String
key=Key[namespace=orders, value=A1]
~~~

`getRecordComponents()` trả metadata theo thứ tự components như khai báo trong record header. Canonical constructor gắn với chính thứ tự và kiểu ấy. Reflection ở đây dùng để minh họa **cấu trúc của record**, không để sửa final fields.

## 38. Bài tập đọc mã: phân biệt hai constructors

Xem ví dụ:

~~~java
record Interval(int from, int to) {
    Interval {
        if (from > to) {
            throw new IllegalArgumentException("wrong order");
        }
    }

    Interval(int to) {
        this(0, to);
    }
}
~~~

Đây là record hợp lệ.

Hãy tự trả lời trước khi đọc đáp án:

- Constructor nào là canonical?
- Constructor nào là overload/non-canonical?
- Dòng `this(0, to)` gọi cái gì?
- Trong compact constructor, `this.from` và `this.to` được gán ở thời điểm nào?
- `new Interval(-1)` tạo object hay ném exception?
- Tại sao overload không được đặt một lệnh `System.out.println(...)` trước `this(0, to)` theo Java 17?

**Đáp án:** `Interval { ... }` là compact canonical constructor; `Interval(int to)` là non-canonical overload. `this(0,to)` chuyển tới canonical constructor (signature `Interval(int from,int to)`). Compiler gán các component fields sau compact body thành công. `new Interval(-1)` ném IllegalArgumentException vì 0 lớn hơn -1. Trong Java 17, explicit constructor invocation `this(...)` ở overload phải đứng đầu constructor body.

## 39. Bảng so sánh để chọn dạng constructor

| Nhu cầu | Không khai báo constructor | Explicit canonical | Compact canonical |
| --- | --- | --- | --- |
| Chỉ cần gán đúng các components | Tốt nhất | Dài không cần thiết | Không cần thiết |
| Kiểm tra giá trị âm/null | Không đủ | Có | Có, thường gọn nhất |
| Chuẩn hóa String trước khi gán | Không đủ | Có | Có, sửa tham số |
| Defensive copy `List` | Không đủ | Có | Có, sửa tham số |
| Tự kiểm soát assignments của fields | Compiler làm mặc định | Cho phép | **Không cho phép** |
| Bỏ quên assignment một component | Compiler xử lý | Có thể lỗi compile | Compiler xử lý |
| Constructor overload một tham số | Cần thêm overload | Overload gọi canonical | Overload gọi canonical |
| Hợp đồng record minh bạch | Có | Có nếu viết đúng | Có nếu viết đúng |
| Cần gọi I/O/checked exceptions | Nên tách factory | Không khai `throws` ở canonical | Không khai `throws` ở canonical |

Dạng compact không phải “constructor không có tham số”. Nó là **canonical constructor có tham số ngầm** đúng theo record header. Đây là một nhầm lẫn đáng tránh khi mới học.

## 40. Lỗi compile-time thường gặp và hướng sửa

| Dấu hiệu | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Explicit canonical đổi tên tham số | Tên không khớp record header | Giữ đúng tên component |
| Explicit canonical gán thiếu `this.field` | Final field chưa definitely assigned | Gán đủ, hoặc dùng compact |
| Compact constructor gán `this.field` | Component fields do compiler gán sau body | Sửa tham số, không sửa field |
| Khai cả compact và explicit canonical | Hai canonical constructors trùng nhau | Chọn một |
| Viết `RecordName()` tưởng là compact | Đó là overload 0 tham số | Compact phải viết `RecordName { ... }` |
| Overload không có `this(...)` | Non-canonical phải delegate | Gọi constructor khác của cùng record |
| Đặt lệnh trước `this(...)` trong overload | Java 17 yêu cầu invocation đầu tiên | Đưa logic vào helper/arguments |
| Gắn `throws IOException` lên canonical | Bị JLS cấm | Factory/service xử lý checked exception |
| Public record, canonical constructor private | Access hẹp hơn record | Dùng public canonical |
| Dùng `return;` trong compact | Return statement không được phép | Kết thúc block bình thường/throw |
| Quên validate `null` | Record reference component có thể null | `Objects.requireNonNull` |
| Nghĩ field final làm `List` immutable | Chỉ field reference final | `List.copyOf` |
| Clone array đầu vào nhưng accessor trả mảng gốc | Caller vẫn sửa mảng bên trong | Override accessor trả clone |
| Nghĩ array contents tự deep-equal | Array equals theo identity | Thiết kế equality hoặc representation khác |
| Nghĩ constructor nhận giá trị mới sau khi đã tạo record | Fields không setter, record value không mutate theo cách đó | Tạo record mới |
| Đặt nhiều side effects trong compact | Dễ khởi tạo dở dang/lỗi khó hiểu | Factory có tên, validation sớm |
| Coi constructor overload là canonical | Khác signature của header | Delegate tới canonical |
| Gán lại tham số compact tưởng đổi field ngay lập tức | Field gán sau body | Dùng tham số để validate, normalize |

## 41. Quy trình giải thích một constructor record

Khi đọc một đoạn record Java 17, hãy phân tích:

1. **Record header** có components nào, kiểu/tên/thứ tự?
2. **Có khai báo constructor không?** Nếu không, có canonical ngầm định.
3. Nếu thấy `RecordName { ... }`, đó là **compact canonical constructor**.
4. Nếu thấy `RecordName(T1 a, T2 b)`, so với header để biết canonical explicit hay non-canonical overload.
5. Nếu explicit canonical, kiểm tra gán đầy đủ các component fields trên đường hoàn tất bình thường.
6. Nếu compact, kiểm tra validation/normalization trên **parameters**, không có assignment `this.component`.
7. Nếu non-canonical, kiểm tra câu đầu `this(...)` và đường dẫn cuối đến canonical.
8. Kiểm tra access và forbidden `throws` trên canonical.
9. Xem điều kiện null, range, cross-field invariants có được thực thi khi tạo object không.
10. Nếu component giữ mutable object, kiểm tra defensive copying và accessor.
11. Sau cùng mới tính `toString`, `equals`, `hashCode`, output.
12. Nếu có exception, xác định object nào thực sự đã được tạo thành công và side effects nào đã diễn ra.

Hãy xác định tính hợp lệ **lúc biên dịch** trước khi dự đoán stdout; một ví dụ thiếu field assignment hoặc cố gán field trong compact constructor không có output runtime.

## 42. Bài tập tự luyện

**Câu 1.** Với `record Point(int x,int y) {}`, Java cung cấp constructor nào?

**Câu 2.** `Point(int a,int b)` có phải canonical explicit constructor của Point không, dù cùng hai kiểu int?

**Câu 3.** `Point { if(x<0) throw ...; }` có phải constructor không tham số?

**Câu 4.** Trong explicit canonical constructor, ai phải gán `this.x`, `this.y`?

**Câu 5.** Trong compact constructor, ai gán những fields ấy, và khi nào?

**Câu 6.** Có được viết `this.x = x` trong compact constructor không?

**Câu 7.** Có được viết `x = Math.abs(x)` trong compact constructor để normalize tham số không?

**Câu 8.** Vì sao `new Username(" An ")` có thể cho `value()` là `"An"` dù component field final?

**Câu 9.** Một record có compact và explicit canonical constructors cùng lúc được không?

**Câu 10.** Một constructor `Point()` muốn cung cấp mặc định `(0,0)` nên viết gì?

**Câu 11.** Trong Java 17 có thể viết `System.out.println("start"); this(0,0);` bên trong non-canonical constructor không?

**Câu 12.** Compact canonical constructor có được khai báo `throws IOException` không?

**Câu 13.** Nếu một public record khai explicit canonical constructor private, điều gì xảy ra?

**Câu 14.** Record header có tự cấm `null` cho String component không?

**Câu 15.** `List.copyOf` trong compact constructor có tác dụng gì? Có deep-copy mutable elements không?

**Câu 16.** Vì sao constructor clone array input chưa đủ để ngăn caller sửa record state?

**Câu 17.** Hai record instances có array components cùng nội dung nhưng khác array objects có generated equals true không?

**Câu 18.** Record generic `Pair<T>` có thể khai compact constructor `Pair { ... }` không?

**Câu 19.** Constructor overload có được tự gán component fields thay vì `this(...)` không?

**Câu 20.** Khi normalization biến hai inputs khác nhau thành cùng components, generated equals cho kết quả gì nếu record type giống nhau?

**Câu 21.** Nếu code trong compact constructor ném IllegalArgumentException, caller có nhận record object đã hoàn tất không?

**Câu 22.** `name()` và `getName()` khác nhau thế nào với record component `name`?

**Câu 23.** Tại sao không nên gọi callback dùng `this` từ compact constructor trước khi fields được gán?

**Câu 24.** Nếu validation cần đọc file hoặc gọi dịch vụ có checked exception, nên đặt logic ở đâu?

### Đáp án kèm giải thích

1. Canonical `Point(int x,int y)` được compiler sinh nếu không có khai báo constructor thay thế.
2. Không; tên tham số canonical phải khớp header (`x`, `y`).
3. Không; compact có đầy đủ tham số theo header **một cách ngầm định**.
4. Code của explicit canonical constructor phải gán đầy đủ fields khi hoàn tất bình thường.
5. Compiler tự gán sau khi body compact kết thúc bình thường.
6. Không, assignment tới record component fields bị cấm trong compact form.
7. Có thể sửa chính tham số `x` nếu phép chuẩn hóa phù hợp invariant.
8. Constructor đổi parameter trước khi compiler gán field final.
9. Không; chỉ có một canonical constructor cho cùng signature.
10. `Point() { this(0, 0); }` là non-canonical overload hợp lệ.
11. Không, với Java 17 invocation `this(...)` phải đầu tiên.
12. Không; canonical constructor không cho `throws` clause.
13. Lỗi compile vì access hẹp hơn record.
14. Không; phải validate theo domain.
15. Snapshot unmodifiable list structure, không deep-copy mutable elements.
16. Accessor mặc định trả reference array field; cần defensive copy khi xuất ra.
17. Không, generated equals không deep-compare array contents.
18. Có; các parameters và type variable thuộc header.
19. Không; non-canonical phải delegate qua constructor của record.
20. Nếu cùng type và components bằng nhau, record-generated equals true.
21. Không; creation thất bại, exception truyền tới caller.
22. Accessor mặc định là `name()`; Java không mặc định sinh `getName()`.
23. Vì component fields có thể chưa được khởi tạo hoàn tất, làm lộ object/khả năng đọc trạng thái sai.
24. Trong service/factory có hợp đồng I/O/throws rõ rồi tạo record sau khi đã có dữ liệu.

## 43. Checklist thực hành

- [ ] Đã xác định canonical parameter list trực tiếp từ record header.
- [ ] Đã chọn ngầm định, explicit hay compact dựa trên nhu cầu thật.
- [ ] Nếu explicit, các tên/kiểu/thứ tự formal parameters khớp components.
- [ ] Nếu explicit, mọi component fields được gán hợp lệ khi constructor hoàn tất.
- [ ] Nếu compact, body không chứa assignment trực tiếp tới `this.component`.
- [ ] Nếu compact, các parameters được normalize trước phép gán ngầm của compiler.
- [ ] Không có hai canonical constructors cho một record.
- [ ] Mọi overloaded non-canonical constructors đều gọi `this(...)` theo luật Java 17.
- [ ] Không có `throws` clause trên canonical constructor.
- [ ] Accessibility của canonical constructor không hẹp hơn record.
- [ ] Input `null`, blank, invalid ranges được xử lý đúng policy.
- [ ] Các invariants liên quan nhiều components được kiểm tra ở constructor.
- [ ] Các reference components mutable có snapshot/copy policy phù hợp.
- [ ] Với array components, đã cân nhắc defensive accessor và equality/hashCode.
- [ ] Không gọi callbacks làm thoát `this` khi object chưa xây xong.
- [ ] Không đặt I/O nặng và side effects khó rollback vào constructor.
- [ ] Đã kiểm tra accessors `componentName()` và generated `toString`/`equals` đúng kỳ vọng.
- [ ] Đã biên dịch từng demo bằng Java 17+ và so khớp stdout.
- [ ] Các ví dụ cố ý sai được phân biệt rõ với chương trình runnable.

## 44. Tài liệu Java 17 chính thức

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): khái niệm record và các member ngầm định.
- [JLS 17 §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): components, types và thứ tự khai báo.
- [JLS 17 §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical explicit, compact canonical, restrictions và overload.
- [JLS 17 §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): component fields, accessors và `equals`/`hashCode`/`toString`.
- [JLS 17 §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7): explicit constructor invocation và body rules.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): assignment constraints cho final fields.
- [Java SE 17 API — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record base class và giá trị equality.
- [Java SE 17 API — Class.isRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isRecord()): kiểm tra runtime record type.
- [Java SE 17 API — Class.getRecordComponents](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()): metadata record components.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): validation null.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null policy.
- [Java SE 17 API — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(int[],int[])): so nội dung mảng khi cần.
- [JEP 395 — Records (Final)](https://openjdk.org/jeps/395): động cơ thiết kế, canonical constructors và bất biến records.

## 45. Tổng kết

**Canonical constructor** của record luôn gắn với **toàn bộ record components**, đúng thứ tự, tên và kiểu. Khi không cần validation hoặc normalization, để compiler sinh constructor là cách rõ nhất.

Khi cần invariant, bạn có hai lựa chọn:

- **Explicit canonical:** viết `RecordName(T1 a, T2 b)`, kiểm tra dữ liệu rồi **tự gán** `this.a`, `this.b`.
- **Compact canonical:** viết `RecordName { ... }`, kiểm tra hoặc sửa các **tham số ngầm**, rồi **để compiler tự gán** component fields sau khi body hoàn tất bình thường.

Dùng **compact** cho validation, canonicalization và defensive copy đơn giản; dùng **explicit** khi việc tự kiểm soát field assignments thực sự giúp code rõ hơn. Với constructor overload khác signature, phải ủy quyền qua `this(...)` theo quy tắc Java 17 để mọi cách tạo object đi qua validation chung.

Cuối cùng, **record fields final không có nghĩa object graph bất biến sâu**. Nếu components là lists/arrays/mutable types, phải quyết định defensive copying, accessor và equality từ hợp đồng dữ liệu. Một record tốt là một value object có cấu trúc rõ, invariant đáng tin và constructor làm đúng một trách nhiệm: **tạo trạng thái hợp lệ**.
