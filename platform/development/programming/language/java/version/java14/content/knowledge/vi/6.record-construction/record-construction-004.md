# Chuẩn hóa tham số trước khi hoàn tất khởi tạo record

> **Ngữ cảnh:** Java 14 — **Khởi tạo record**. `record` từng xuất hiện dưới dạng preview ở Java 14, nhưng đã trở thành tính năng **chính thức từ Java 16 (JEP 395)**. Bài này chỉ dùng cơ chế record đã ổn định trong Java hiện đại; các ví dụ chạy trên JDK còn được hỗ trợ như 21/25 và biên dịch với `--release 17`. Không yêu cầu JDK 14 đã hết vòng đời hoặc `--enable-preview`.

## 1. Học xong bạn làm được gì?

- Diễn giải chính xác thời điểm Java gán các tham số cho **component field** trong **compact canonical constructor**.
- Chuẩn hóa `String`, thứ tự cặp giá trị và collection đầu vào **trước** khi trạng thái record được thiết lập.
- Kết hợp chuẩn hóa với kiểm tra tính hợp lệ (*validation*) mà không tạo đối tượng mang dữ liệu sai.
- Phân biệt **tham số ngầm định** với **trường `private final`** cùng tên trong record.
- So sánh compact constructor, canonical constructor viết đầy đủ và constructor phụ.
- Hiểu ảnh hưởng của chuẩn hóa đến accessor, `equals`, `hashCode` và tính ổn định của giá trị.
- Tránh các biến đổi dữ liệu quá mức, tác dụng phụ bất ngờ và lỗi bất biến nông.

## 2. Bản chất của việc “chuẩn hóa trước khi hoàn tất khởi tạo”

Một record công bố tập thành phần (*components*) có tên, kiểu và thứ tự. Ví dụ:

~~~java
record Topic(String title, String code) {}
~~~

Java tạo constructor nhận `title` và `code`, các trường tương ứng `private final`, accessor `title()`/`code()`, cùng `equals`/`hashCode`/`toString`. Nếu không có quy tắc nào khác, hai chuỗi `" Java "` và `"Java"` là hai giá trị khác nhau. Muốn lưu một giá trị thống nhất, ta có thể **chuẩn hóa tham số ngay lúc tạo record**.

Chuẩn hóa (*normalization*) nghĩa là biến đổi một giá trị đầu vào hợp lệ về **biểu diễn chuẩn** được hợp đồng dữ liệu quy định. Ví dụ:

- Bỏ khoảng trắng thừa ở **đầu/cuối** tên khóa học: `"  Java  "` → `"Java"`.
- Đổi mã phân loại **được nghiệp vụ quy định là không phân biệt hoa/thường** sang chữ hoa: `" core "` → `"CORE"`.
- Nếu một khoảng hai đầu mút được định nghĩa là **không có hướng**, có thể xếp lại từ nhỏ đến lớn.
- Chụp bản sao của danh sách đầu vào để bên ngoài không thay đổi nội dung component sau khi record được tạo.

**Chuẩn hóa khác validation.** Validation trả lời “giá trị có hợp lệ không?”; chuẩn hóa trả lời “biểu diễn chuẩn của giá trị hợp lệ là gì?”. Thường dùng cả hai: kiểm tra `null` trước phép biến đổi, chuẩn hóa, rồi kiểm tra điều kiện trên **giá trị đã chuẩn hóa**.

Đừng tự mặc định mọi dữ liệu đều nên biến đổi. Mã định danh phân biệt hoa/thường, mật khẩu, token, văn bản pháp lý hoặc dữ liệu chữ ký có thể **thay đổi ý nghĩa** nếu bị `strip()` hay `toUpperCase()`. Quy tắc chuẩn phải xuất phát từ **hợp đồng miền dữ liệu**, không phải từ thói quen viết code.

## 3. Compact canonical constructor: cơ chế then chốt

Cách viết chuẩn cho record có bước chuẩn hóa:

~~~java
record Topic(String title, String code) {
    Topic {
        title = title.strip();
        code = code.strip();
    }
}
~~~

Đây là **mảnh khai báo kiểu** nhằm minh họa cú pháp; cần kiểm tra `null` trong code thực tế.

`Topic { ... }` được gọi là **compact canonical constructor**. Nó không ghi lại danh sách tham số `(String title, String code)` vì Java suy ra chúng trực tiếp từ **record header**.

Trong thân compact constructor:

1. `title` là **tham số constructor ngầm định** tên `title`; `code` tương tự.
2. Câu lệnh `title = title.strip();` gán lại **tham số**, chưa gán vào component field.
3. Khi phần thân kết thúc **bình thường**, compiler thực hiện gán ngầm định các giá trị tham số **cuối cùng** vào các component field `private final`, theo thứ tự khai báo trong header.
4. Nếu thân constructor ném ngoại lệ, quá trình khởi tạo không hoàn thành; đối tượng không được trả về cho lời gọi `new`.

Có thể hình dung thứ tự:

~~~text
new Topic(rawTitle, rawCode)
       |
       v
Tham số ngầm định title, code
       |
       v
Kiểm tra null / tiền điều kiện
       |
       v
Chuẩn hóa title, code
       |
       v
Kiểm tra giá trị sau chuẩn hóa
       |
       v
Thân compact constructor hoàn tất bình thường
       |
       v
Java tự gán:
this.title = title
this.code  = code
       |
       v
Record đã khởi tạo; accessor đọc giá trị chuẩn
~~~

**Hai dòng gán `this.title = title` trong sơ đồ chỉ mô tả thao tác compiler bổ sung; bạn KHÔNG viết chúng trong compact constructor.** Gán trực tiếp vào component field tại đó là lỗi biên dịch.

Cơ chế này được định nghĩa trong Java Language Specification `8.10.4.2, vẫn có hiệu lực với các JDK hiện đại. Nó là lý do compact constructor đặc biệt phù hợp cho **validate + normalize**.

## 4. Ví dụ chạy được: chuẩn hóa chuỗi trước khi lưu

Tạo tệp **`TopicNormalizeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

record Topic(String title, String code) {
    Topic {
        Objects.requireNonNull(title, "title");
        Objects.requireNonNull(code, "code");

        title = title.strip();
        code = code.strip().toUpperCase(Locale.ROOT);

        if (title.isEmpty()) {
            throw new IllegalArgumentException("title must not be empty");
        }
        if (code.isEmpty()) {
            throw new IllegalArgumentException("code must not be empty");
        }
    }
}

public class TopicNormalizeDemo {
    public static void main(String[] args) {
        Topic first = new Topic("  Java Record  ", " core ");
        Topic second = new Topic("Java Record", "CORE");

        System.out.println(first.title() + " | " + first.code());
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());

        try {
            new Topic("   ", "core");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid title");
        }

        try {
            new Topic(null, "core");
        } catch (NullPointerException ex) {
            System.out.println("null title");
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 21 hoặc 25** (hoặc JDK đang được hỗ trợ có `--release 17`):

~~~bash
javac --release 17 TopicNormalizeDemo.java
java TopicNormalizeDemo
~~~

**Kết quả chính xác:**

~~~text
Java Record | CORE
true
true
invalid title
null title
~~~

### Giải thích từng bước

- `Objects.requireNonNull(title, "title")` phát hiện `null` trước khi gọi `strip()`. Nếu không kiểm tra tường minh, `title.strip()` vẫn ném `NullPointerException` nhưng thông báo có thể kém rõ và không định vị được hợp đồng dữ liệu.
- `String.strip()` bỏ khoảng trắng ở đầu/cuối theo khái niệm khoảng trắng của Java; **không tự gộp tất cả khoảng trắng bên trong chuỗi**.
- `code.strip().toUpperCase(Locale.ROOT)` chỉ phù hợp vì trong **ví dụ này** mã phân loại `code` được định nghĩa là **không phân biệt hoa/thường**. Dùng `Locale.ROOT` để tránh kết quả đổi chữ theo locale của máy. Không áp dụng tùy tiện phép đổi chữ cho email, token, mật khẩu hoặc mọi định danh.
- Validation `isEmpty()` được đặt **sau** chuẩn hóa, vì `"   "` chỉ trở thành chuỗi rỗng sau `strip()`.
- Sau thân `Topic { ... }`, compiler lưu **`"Java Record"`** và **`"CORE"`** vào các component field. Accessor `first.title()`/`first.code()` đọc những giá trị đã chuẩn.
- Hai record được tạo từ biểu diễn đầu vào khác nhau nhưng chuẩn hóa về cùng cặp component nên `equals` trả `true`. Vì `equals` bằng nhau, `hashCode` cũng phải bằng nhau; không cần kiểm tra giá trị hash cụ thể.
- `new Topic("   ", "core")` ném `IllegalArgumentException`; `new Topic(null, "core")` ném `NullPointerException`. Không đối tượng `Topic` nào được tạo thành công từ hai lời gọi đó.

### Điều kiện nào cần xác định trong nghiệp vụ?

Nếu hệ thống thật cần giữ khoảng trắng trong `title`, hoặc `code` thực sự phân biệt hoa/thường, **không dùng** quy tắc trên. Mục đích của ví dụ là minh họa cách áp dụng một chính sách chuẩn hóa **đã được định nghĩa**, không đưa ra chính sách mặc định cho mọi trường dữ liệu.

## 5. Tham số ngầm định không phải trường record

Trong một compact constructor của `record Topic(String title, String code)`:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `title` trong `Topic { ... }` | Tham số constructor ngầm định `String title`, có thể gán lại trong thân constructor. |
| `title = title.strip();` | Đưa **tham số** về biểu diễn chuẩn. |
| `this.title` | Component field `private final` do Java sinh; không được tự gán trong thân compact constructor. |
| `title()` sau khi khởi tạo | Accessor đọc trường đã được compiler gán bằng tham số cuối cùng. |
| `this.title = title;` trong compact constructor | **Sai**: field assignment này bị Java cấm trong compact constructor. |

Mã **không biên dịch**, dùng để nhận biết lỗi:

~~~java
record WrongTitle(String title) {
    WrongTitle {
        title = title.strip();
        this.title = title; // LỖI: compact constructor tự động gán field
    }
}
~~~

Cách đúng:

~~~java
record CorrectTitle(String title) {
    CorrectTitle {
        title = java.util.Objects.requireNonNull(title).strip();
        if (title.isEmpty()) {
            throw new IllegalArgumentException("blank title");
        }
    }
}
~~~

Lưu ý thêm:

- Không khai báo lại tham số ngay trong thân bằng `String title = ...`: tên `title` đã được Java cấp cho tham số ngầm định. Chỉ **gán lại**: `title = ...`.
- Compact constructor **không được có câu lệnh `return`**, kể cả `return;`. Muốn bác bỏ dữ liệu, dùng ngoại lệ hợp lệ.
- Không gọi `this(...)` hoặc `super(...)` bên trong compact constructor. Việc khởi tạo các component đã được quy định bởi chính cơ chế compact canonical constructor.
- Không thể có **cả** compact canonical constructor và canonical constructor dạng đầy đủ trong **cùng một record**. Chọn **một** cách định nghĩa canonical constructor.
- Không lấy dữ liệu qua accessor khi các field chưa được hoàn tất khởi tạo; sử dụng **tham số ngầm định** để kiểm tra và chuẩn hóa trong thân constructor.

## 6. So sánh compact constructor với canonical constructor dạng đầy đủ

Hai cách dưới đây diễn đạt cùng một chính sách: chuẩn hóa đầu vào rồi lưu kết quả. Đặt cả hai record vào tệp **`ConstructorStyleDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

record CompactTag(String value) {
    CompactTag {
        Objects.requireNonNull(value, "value");
        value = value.strip().toUpperCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank tag");
        }
    }
}

record ExplicitTag(String value) {
    ExplicitTag(String value) {
        Objects.requireNonNull(value, "value");
        value = value.strip().toUpperCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank tag");
        }

        this.value = value;
    }
}

public class ConstructorStyleDemo {
    public static void main(String[] args) {
        CompactTag compact = new CompactTag("  alpha ");
        ExplicitTag explicit = new ExplicitTag("  alpha ");

        System.out.println(compact.value());
        System.out.println(explicit.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConstructorStyleDemo.java
java ConstructorStyleDemo
~~~

Kết quả chính xác:

~~~text
ALPHA
ALPHA
~~~

**Điểm khác biệt quan trọng:**

- `CompactTag { ... }` **không khai báo danh sách tham số và không gán field**; Java ngầm cung cấp cả hai phần đó. Đổi `value` trong thân constructor có tác dụng đến giá trị được lưu.
- `ExplicitTag(String value) { ... }` **khai báo đầy đủ tham số** phù hợp record header; bạn **phải tự gán** field `this.value = value` trên mọi đường kết thúc bình thường. Không phải compiler tự thêm bước gán sau thân như với dạng compact.
- Cả hai đều là **canonical constructor** của record tương ứng, vì chịu trách nhiệm thiết lập tất cả component.
- Trong ví dụ này, dạng compact ngắn, ít lặp header và diễn tả đúng ý định “chỉ kiểm tra và chuẩn hóa tham số trước khi Java lưu”. Dạng đầy đủ hữu ích khi cần kiểm soát chi tiết việc gán component field và các quy tắc hợp lệ của constructor.

**Quy tắc chọn:** Với record mà phần việc chính là xác thực, cắt khoảng trắng, đưa về dạng chuẩn hoặc chụp snapshot đầu vào, ưu tiên **compact constructor**. Chỉ dùng dạng đầy đủ khi có lý do cụ thể.

## 7. Chuẩn hóa bộ số: trường hợp thứ tự không mang ý nghĩa

Chuẩn hóa không giới hạn ở chuỗi. Nếu một đối tượng biểu diễn **đoạn số không có hướng**, hai đầu mút `(3, 9)` và `(9, 3)` có thể được quy định là cùng một giá trị. Khi đó ta có thể sắp xếp **tham số** trước khi hoàn tất constructor.

Tạo tệp **`RangeNormalizeDemo.java`**:

~~~java
record UnorderedRange(int low, int high) {
    UnorderedRange {
        if (low > high) {
            int temporary = low;
            low = high;
            high = temporary;
        }
    }
}

public class RangeNormalizeDemo {
    public static void main(String[] args) {
        UnorderedRange first = new UnorderedRange(9, 3);
        UnorderedRange second = new UnorderedRange(3, 9);

        System.out.println(first.low() + ".." + first.high());
        System.out.println(first.equals(second));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 RangeNormalizeDemo.java
java RangeNormalizeDemo
~~~

Kết quả chính xác:

~~~text
3..9
true
~~~

`temporary` chỉ là biến cục bộ tạm thời; `low` và `high` ở hai phép gán là **tham số**. Khi compact constructor hoàn tất, Java tự thiết lập component field tương ứng. Vì cả hai đầu vào cho cùng cặp `(3, 9)`, `equals` trả `true`.

**Điều kiện quan trọng:** việc đổi chỗ chỉ hợp lệ nếu miền dữ liệu xác định hai đầu mút là **không có hướng**. Với `startTime`/`endTime`, tọa độ hành trình từ A đến B, hoặc mức giá có ý nghĩa riêng cho điểm bắt đầu/kết thúc, tự đổi thứ tự có thể **che giấu lỗi**. Khi đó, hãy **ném `IllegalArgumentException`** nếu thứ tự sai, thay vì “sửa” đầu vào.

## 8. Chuẩn hóa collection: chụp snapshot ngay trong constructor

Trường component của record là `private final`, nhưng `final` **không làm cho nội dung của đối tượng được tham chiếu trở thành bất biến sâu**. Nếu đưa một `ArrayList` mutable vào record mà không xử lý, caller có thể sửa danh sách gốc sau khi record được tạo.

Hãy chuẩn hóa dữ liệu đầu vào thành một **danh sách không sửa đổi được**, tách khỏi danh sách mutable gốc. Tạo tệp **`LessonBatchDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record LessonBatch(String title, List<String> lessons) {
    LessonBatch {
        title = Objects.requireNonNull(title, "title").strip();
        if (title.isEmpty()) {
            throw new IllegalArgumentException("blank title");
        }

        lessons = List.copyOf(Objects.requireNonNull(lessons, "lessons"));
    }
}

public class LessonBatchDemo {
    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("A", "B"));
        LessonBatch batch = new LessonBatch("  Java  ", original);

        original.add("C");

        System.out.println(batch.title());
        System.out.println(batch.lessons());

        try {
            batch.lessons().add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LessonBatchDemo.java
java LessonBatchDemo
~~~

Kết quả chính xác:

~~~text
Java
[A, B]
unmodifiable
~~~

Phân tích:

1. `lessons = List.copyOf(...)` gán lại **tham số ngầm định** sang danh sách không sửa đổi được.
2. Sau khi constructor kết thúc, field `lessons` nhận **tham chiếu đến danh sách đã chuẩn hóa**.
3. Thêm `"C"` vào `original` không thay đổi `batch.lessons()`, vì `List.copyOf` tạo snapshot không sửa đổi được đối với nguồn mutable trong ví dụ.
4. Gọi `batch.lessons().add("D")` ném `UnsupportedOperationException`, được bắt để in `unmodifiable`.
5. `List.copyOf` không chấp nhận phần tử `null`; nếu đó là giá trị đầu vào hợp lệ theo nghiệp vụ thì cần **chính sách khác**.

**Giới hạn:** `List.copyOf` là **bản sao nông**. Nếu danh sách chứa đối tượng mutable, chính các đối tượng đó vẫn có thể thay đổi từ bên ngoài. Khi yêu cầu bất biến sâu, hãy dùng các **kiểu phần tử bất biến**, tạo snapshot của từng phần tử hoặc chọn mô hình dữ liệu khác. Không mô tả record như một bảo đảm bất biến sâu tự động.

Mảng (`int[]`, `String[]`) còn dễ gây nhầm lẫn hơn: accessor mặc định trả tham chiếu mảng, nội dung mảng có thể bị sửa, và `equals` mặc định đối với mảng không so sánh nội dung sâu. Với giá trị record mang ý nghĩa tập dữ liệu, thường ưu tiên kiểu collection phù hợp và có chính sách snapshot rõ ràng.

## 9. Constructor phụ cũng phải đi qua canonical constructor

Một record có thể có **constructor phụ** (non-canonical constructor), nhưng các constructor phụ phải ủy quyền sang một constructor khác của cùng record qua `this(...)`, cuối cùng dẫn tới canonical constructor. Nhờ đó, dữ liệu từ nhiều cách khởi tạo đều đi qua **một nơi chuẩn hóa**.

Tạo tệp **`HandleDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

record Handle(String value) {
    Handle {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank handle");
        }
    }

    Handle() {
        this("guest");
    }
}

public class HandleDemo {
    public static void main(String[] args) {
        Handle defaultHandle = new Handle();
        Handle namedHandle = new Handle("  ALICE ");

        System.out.println(defaultHandle.value());
        System.out.println(namedHandle.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 HandleDemo.java
java HandleDemo
~~~

Kết quả chính xác:

~~~text
guest
alice
~~~

Cách đọc:

- `Handle(String value)` là chữ ký **canonical constructor**, được hiện thực bằng compact constructor `Handle { ... }`.
- `Handle() { this("guest"); }` là constructor phụ, cung cấp một giá trị mặc định hợp lệ rồi ủy quyền tới canonical constructor.
- `new Handle("  ALICE ")` đi trực tiếp qua canonical constructor và được chuẩn hóa thành `"alice"`.
- **Không lặp lại quy tắc chuẩn hóa ở mọi constructor phụ**: tập trung nó tại canonical constructor giúp mọi đường khởi tạo tuân theo cùng một hợp đồng.

Việc có constructor phụ **không làm record trở thành mutable**. Các component field vẫn được gán một lần trong quá trình xây dựng đối tượng.

## 10. Quy tắc thiết kế một chuỗi normalize + validate

Thứ tự thường rõ ràng như sau:

~~~text
Đầu vào
  -> kiểm tra null và lỗi cơ bản
  -> biến đổi theo chính sách miền dữ liệu
  -> kiểm tra các bất biến trên giá trị đã chuẩn hóa
  -> (nếu cần) sao chép phòng vệ các đối tượng mutable
  -> kết thúc compact constructor bình thường
  -> Java tự gán component field
~~~

Thứ tự có thể điều chỉnh theo miền dữ liệu. Ví dụ, muốn bảo toàn báo lỗi của dữ liệu gốc thì kiểm tra một số tiền điều kiện trước khi chuẩn hóa; muốn tránh một tên chỉ có dấu cách thì kiểm tra rỗng **sau** `strip()`. Với danh sách, có thể kiểm tra và chuẩn hóa **từng phần tử** trước `List.copyOf`, nếu hợp đồng yêu cầu.

### Các tiêu chí của hàm chuẩn hóa tốt

- **Có chủ đích:** xuất phát từ quy ước được công bố của component.
- **Ổn định:** cùng input và cùng chính sách cho cùng output; tránh phụ thuộc ngầm vào locale hoặc múi giờ hệ thống.
- **Idempotent:** chuẩn hóa một giá trị đã chuẩn thường không đổi nó nữa: `normalize(normalize(x)).equals(normalize(x))`.
- **Không gây tác dụng phụ:** tránh sửa trực tiếp collection mutable thuộc caller; tránh ghi log dữ liệu nhạy cảm hoặc gọi dịch vụ ngoài trong constructor.
- **Không mất thông tin ngoài ý muốn:** không tự loại dấu tiếng Việt, thay dấu câu, ép chữ hoa hoặc gộp khoảng trắng giữa câu nếu hợp đồng không cho phép.
- **Phát hiện lỗi sớm:** dữ liệu không thể đưa về dạng hợp lệ phải bị từ chối với ngoại lệ rõ ràng.

Một record càng có ý nghĩa **giá trị** thì việc bảo đảm các component nhất quán ngay tại constructor càng đáng giá. Không nên để cùng một thông tin nghiệp vụ tồn tại dưới nhiều biểu diễn mà những người dùng API không lường trước.

## 11. Chuẩn hóa ảnh hưởng thế nào đến equality và dữ liệu lưu giữ?

Record tự tạo `equals`/`hashCode` theo các component nếu bạn không tự khai báo. Điều này dẫn tới một hệ quả tích cực: **so sánh hai record sẽ dựa trên các giá trị đã được lưu**, tức các giá trị **sau chuẩn hóa**.

Ví dụ trong mục 4:

~~~text
new Topic("  Java Record  ", " core ")
            |
            v
Topic[title="Java Record", code="CORE"]

new Topic("Java Record", "CORE")
            |
            v
Topic[title="Java Record", code="CORE"]
~~~

Đây là **sơ đồ giá trị minh họa**, không phải đầu ra yêu cầu của `toString()`. Vì cả hai record có cùng kiểu và cùng cặp component, `equals` trả `true`.

Tuy nhiên:

- Hai record có **component kiểu mảng** có thể không bằng nhau mặc dù nội dung mảng giống nhau, vì `equals` của mảng không so sánh phần tử sâu.
- Nếu component trỏ tới đối tượng mutable mà không chụp snapshot, giá trị quan sát qua accessor có thể thay đổi sau khi khởi tạo; khi dùng record đó làm key của `HashMap`, điều này có thể phá giả định ổn định của hash. Vì vậy cần đặc biệt thận trọng với component mutable.
- Thay đổi quy tắc chuẩn hóa sau khi một API đã phát hành có thể thay đổi `equals`, khóa cache, giá trị lưu DB và cách đối chiếu dữ liệu. Hãy xem đó là **thay đổi hợp đồng dữ liệu**, có kiểm thử và kế hoạch tương thích.

Record không mặc nhiên là cấu trúc “mọi thứ bên trong không đổi”. Tính ổn định của hành vi so sánh phụ thuộc vào **thiết kế component và chính sách chuẩn hóa/snapshot**.

## 12. Những lỗi Java và lỗi nghiệp vụ hay gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Viết `this.name = name.strip();` trong compact constructor | Lỗi biên dịch vì gán trực tiếp component field | Gán lại **tham số**: `name = name.strip();`. |
| Viết `return;` trong compact constructor | Lỗi biên dịch | Kết thúc thân bình thường hoặc ném ngoại lệ nếu dữ liệu không hợp lệ. |
| Gọi `name.strip()` khi `name` có thể `null` | `NullPointerException` thiếu ngữ cảnh | Kiểm tra null trước và nêu tên component. |
| Kiểm tra `isEmpty()` trước `strip()`, không kiểm tra lại sau | `"   "` lọt qua nhưng thành giá trị rỗng | Kiểm tra rỗng sau chuẩn hóa. |
| Dùng `toUpperCase()` không chỉ định locale cho mã kỹ thuật | Có thể phụ thuộc locale mặc định | Với mã không phụ thuộc ngôn ngữ, áp dụng `Locale.ROOT` nếu chính sách cho phép đổi chữ. |
| Tự lowercase email hoặc token trong mọi trường hợp | Có thể thay đổi ý nghĩa dữ liệu | Chỉ thực hiện khi miền dữ liệu xác nhận không phân biệt hoa/thường. |
| Gọi `list.clear()` hoặc `sort()` trực tiếp trên collection của caller để chuẩn hóa | Tác dụng phụ trên dữ liệu bên ngoài | Tạo bản sao riêng rồi biến đổi; dùng `List.copyOf` cho snapshot thích hợp. |
| Nghĩ `List.copyOf` tạo bản sao sâu | Phần tử mutable vẫn có thể thay đổi | Dùng kiểu phần tử bất biến hoặc sao chép từng phần tử. |
| Dùng `record` với mutable component rồi giả định hash không đổi | Dữ liệu làm key trong `HashMap` có thể mất ổn định | Thiết kế component bất biến thực sự hoặc chọn đối tượng khác. |
| Khai báo cả compact và explicit canonical constructor cùng record | Lỗi biên dịch: trùng canonical signature | Chọn một cách định nghĩa canonical constructor. |
| Lặp chuẩn hóa tại các constructor phụ | Dễ lệch quy tắc hoặc bỏ sót đường khởi tạo | Cho constructor phụ ủy quyền về canonical constructor. |
| Biên dịch record bằng `--release 14` | Record chưa là cú pháp chính thức ở Java 14 | Dùng `--release 17` (hoặc target từ Java 16 được compiler hỗ trợ). |

### Hai trường hợp phải tránh “sửa hộ” input

**Tên tài khoản phân biệt chữ hoa/thường:** `"Admin"` và `"admin"` có thể là hai định danh khác nhau theo chính sách hệ thống. Tự chuyển chữ sẽ làm hai giá trị nhập vào bị nhập làm một.

**Khoảng thời gian có hướng:** `start=18:00`, `end=09:00` có thể là lỗi cần báo rõ, hoặc có ý nghĩa kéo dài sang ngày sau. Tự hoán đổi hai đầu mút như ví dụ `UnorderedRange` sẽ làm mất ý nghĩa ban đầu. Mỗi quy tắc chuẩn hóa phải gắn với nghiệp vụ cụ thể.

## 13. Kiểm thử: nguyên tắc và trường hợp cần bao phủ

Không chỉ kiểm tra “có biên dịch”, hãy kiểm tra **giá trị record sau khởi tạo** và **trường hợp bị bác bỏ**.

| Nhóm kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Chuỗi thông thường | `"Java", "CORE"` | Accessor giữ nguyên đúng giá trị. |
| Chuỗi có khoảng trắng thừa | `"  Java  ", " core "` | Với chính sách ví dụ: `"Java", "CORE"`. |
| Giá trị tương đương sau chuẩn hóa | Hai `Topic` có input khác biểu diễn | `equals` bằng `true`, `hashCode` bằng nhau. |
| Chuỗi chỉ chứa khoảng trắng | `"   "` cho `title` | Ném `IllegalArgumentException`, không có record hợp lệ. |
| Component `null` | `null` cho `title` | Ném `NullPointerException` tại bước tiền điều kiện. |
| Khoảng hai đầu mút đảo ngược nhưng vô hướng | `(9, 3)` | Record `UnorderedRange(3, 9)`. |
| Collection mutable từ caller | `ArrayList` sau đó thêm phần tử | Snapshot trong record không thay đổi. |
| Sửa danh sách trả từ accessor | Gọi `add` trên `List.copyOf` | Ném `UnsupportedOperationException`. |
| Constructor phụ | `new Handle()` | Đi qua canonical constructor, tạo `"guest"`. |

Đối với dữ liệu thực tế còn cần trường hợp Unicode, độ dài tối đa, ký tự đặc biệt, phần tử collection `null` và phần tử mutable; tiêu chí cụ thể phải xuất phát từ hợp đồng miền dữ liệu. **Không** giả định `strip()` tự xử lý mọi biến thể khoảng trắng Unicode, cũng không gộp tất cả biến thể chuỗi thành cùng một giá trị nếu chưa có quy tắc rõ ràng.

Có thể chạy lại toàn bộ ví dụ độc lập của bài:

~~~bash
javac --release 17 TopicNormalizeDemo.java
java TopicNormalizeDemo

javac --release 17 ConstructorStyleDemo.java
java ConstructorStyleDemo

javac --release 17 RangeNormalizeDemo.java
java RangeNormalizeDemo

javac --release 17 LessonBatchDemo.java
java LessonBatchDemo

javac --release 17 HandleDemo.java
java HandleDemo
~~~

Các ví dụ đều dùng tính năng record **chính thức** từ Java 16. Lệnh `--release 17` chọn API, cú pháp và class file tương thích với Java 17; bản thân compiler vẫn đến từ JDK hiện đang được cài. Với `javac --help`, kiểm tra trình biên dịch bạn dùng có hỗ trợ `--release 17` hay không.

## 14. Bài tập thực hành

### Bài 1 — Chuẩn hóa mã khóa học

Tạo `record CourseCode(String value)` với compact constructor:

- Bác bỏ `null`, cắt khoảng trắng đầu/cuối.
- Nếu **quy ước hệ thống cho phép** mã không phân biệt hoa/thường, đổi thành chữ hoa bằng `Locale.ROOT`.
- Bác bỏ chuỗi rỗng sau chuẩn hóa.

Kiểm chứng `new CourseCode("  jav-014  ").value()` thành `"JAV-014"` theo quy tắc giả định, và `new CourseCode("   ")` bị bác bỏ.

### Bài 2 — So sánh hai kiểu constructor

Viết hai record khác tên nhưng cùng component `String name`. Một record dùng compact canonical constructor; record còn lại dùng explicit canonical constructor. Cả hai đưa `"  Lan  "` về `"Lan"`. Giải thích **constructor nào phải viết `this.name = name`** và vì sao.

### Bài 3 — Snapshot của dữ liệu đầu vào

Tạo `record Exam(String title, List<String> questions)`. Trong compact constructor, kiểm tra title hợp lệ và dùng `List.copyOf` cho danh sách. Sửa danh sách đầu vào sau khi tạo record; kiểm chứng accessor không nhìn thấy sự thay đổi. Nêu vì sao giải pháp chưa bảo đảm bất biến sâu nếu phần tử không phải kiểu bất biến.

### Bài 4 — Chuẩn hóa hay từ chối?

Với `record Schedule(LocalTime start, LocalTime end)`, nếu `start` muộn hơn `end` trong một lịch **chỉ cho phép trong cùng ngày**, hãy giải thích vì sao ném ngoại lệ hợp lý hơn tự đổi hai tham số. Chỉ viết mã khi bạn đã xác định rõ chính sách xử lý khoảng thời gian đi qua nửa đêm.

### Bài 5 — Kiểm tra tính idempotent

Viết helper `normalizeCode(String input)` và xác nhận:

~~~text
normalizeCode("  core ") -> "CORE"
normalizeCode("CORE")    -> "CORE"
normalizeCode(normalizeCode("  core ")) -> "CORE"
~~~

Dấu mũi tên ở đây mô tả kết quả, **không phải cú pháp Java**. Giải thích vì sao tính ổn định này có lợi khi dữ liệu được khởi tạo ở nhiều nơi.

**Tiêu chí hoàn thành:** chỉ ra được (a) nơi tham số ngầm định được biến đổi; (b) lúc component field được compiler tự gán; (c) cách xử lý dữ liệu không hợp lệ; (d) vì sao bản sao phòng vệ đôi khi bắt buộc; và (e) cách chọn quy tắc không làm mất ý nghĩa đầu vào.

## 15. Nguồn chuẩn để tra cứu

- [Java Language Specification 26, `8.10.4.2 — Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4.2): quy định tham số ngầm định, các điều cấm trong thân constructor và thời điểm compiler gán component field.
- [Oracle Java 25 Language Guide — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): ví dụ canonical và compact constructor, constructor phụ.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế record chính thức từ Java 16.
- [Java SE 25 API — `String.strip()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#strip()): đặc tả việc bỏ khoảng trắng đầu/cuối.
- [Java SE 25 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): danh sách không sửa đổi được, giới hạn phần tử null và sao chép nông.
- [Java SE 25 API — `Locale.ROOT`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html#ROOT): locale trung lập cho biến đổi ký tự không phụ thuộc ngôn ngữ khi chính sách cho phép.

**Ghi nhớ:** trong **compact constructor**, hãy chỉnh **tham số** để đưa dữ liệu hợp lệ về biểu diễn chuẩn; khi thân constructor hoàn tất bình thường, **Java tự lưu giá trị tham số cuối cùng vào các field `private final`**. Đó là cơ chế chính thức, rõ ràng và bền vững để đảm bảo mọi record mới được tạo đáp ứng hợp đồng dữ liệu.