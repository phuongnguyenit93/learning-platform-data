# Compact constructor và thời điểm gán thành phần trong record

Trong Java hiện đại, `record` là kiểu khai báo dành cho đối tượng biểu diễn một tập dữ liệu cố định theo **record components**. Với record, trình biên dịch tạo các trường `private final` tương ứng với component, các accessor như `name()`, constructor chính (canonical constructor) nếu chưa được khai báo, cùng `equals`, `hashCode` và `toString`.

Khi cần **kiểm tra đầu vào**, **chuẩn hóa giá trị** hoặc **sao chép phòng vệ**, bạn có thể khai báo **compact constructor** thay cho canonical constructor viết đầy đủ. Điểm cốt lõi: trong compact constructor, **body chạy trước; các component field được Java tự gán sau khi body hoàn tất bình thường**. Do đó, đổi giá trị của *tham số ngầm định* trong body sẽ quyết định dữ liệu thật sự được lưu vào record.

Record đã là tính năng chính thức từ Java 16 và vẫn có hiệu lực trong Java 17 trở đi. Bài này sử dụng cú pháp ổn định, chạy trực tiếp trên JDK 17+, không yêu cầu các chế độ preview của giai đoạn phát triển tính năng.

## 1. Record component, trường lưu trữ và tham số constructor

Xét khai báo:

~~~java
record User(String name, int age) {}
~~~

Hai **record components** là `name` và `age`. Từ khai báo đó, Java cung cấp:

- Các trường lưu dữ liệu `private final String name` và `private final int age`, không khai báo thủ công trong record.
- Accessor `name()` và `age()` để đọc dữ liệu. Accessor của record mang tên component, không phải mặc định `getName()` hay `getAge()`.
- Canonical constructor nhận các tham số `(String name, int age)` và khởi tạo hai trường tương ứng.
- Những phương thức đối tượng `equals(Object)`, `hashCode()` và `toString()` dựa trên components.

Để thấy sự khác biệt giữa **tham số** và **trường**, cần nhớ rằng trong constructor có thể tồn tại hai đại diện cùng tên:

| Ký hiệu | Bản chất | Ai tạo ra? | Khi nào có giá trị ý nghĩa? |
|---|---|---|---|
| `name` | Tham số constructor nhận giá trị truyền vào | Khai báo rõ trong canonical constructor đầy đủ, hoặc Java tạo ngầm trong compact constructor | Ngay khi constructor bắt đầu, có thể kiểm tra hoặc gán lại |
| `this.name` | Trường `private final` của đối tượng record | Java tạo từ record component | Trong compact constructor, chỉ được tự khởi tạo từ tham số **sau khi body chạy xong bình thường** |
| `user.name()` | Lời gọi accessor trên đối tượng record đã tạo | Java tạo nếu không tự định nghĩa accessor | Sau khi constructor thành công và `new` trả về đối tượng |

**Không nên đánh đồng ba khái niệm.** Một record component định nghĩa cấu trúc dữ liệu, tham số constructor là giá trị đang được xử lý, còn component field là nơi giá trị cuối được lưu.

## 2. Compact constructor là gì?

Cú pháp:

~~~java
record User(String name, int age) {
    User {
        name = name.strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age is negative");
        }
    }
}
~~~

Đây là một khai báo record **hoàn chỉnh** có thể được dùng trong chương trình Java 17+. Trong body `User { ... }`:

1. Không viết lại danh sách tham số `(String name, int age)`; trình biên dịch tự suy ra từ record header.
2. Tên đơn `name` và `age` chỉ **các tham số ngầm định**, vì vậy được dùng để kiểm tra và có thể thay đổi như tham số thông thường.
3. `name = name.strip();` thay giá trị tham số `name` bằng chuỗi đã loại bỏ khoảng trắng đầu/cuối.
4. Nếu dữ liệu không hợp lệ, `throw` kết thúc constructor bằng ngoại lệ.
5. Nếu body chạy hết **một cách bình thường**, Java tự thực hiện logic tương đương `this.name = name;` rồi `this.age = age;` theo đúng thứ tự khai báo components.

Hai phép gán trong mục 5 là **mô tả về mã khởi tạo ngầm**, không phải đoạn code được phép đặt trực tiếp trong compact constructor. Ghi `this.name = name;` bên trong `User { ... }` sẽ gây **lỗi biên dịch**.

Compact constructor bản thân đã là **canonical constructor** của record. Không thể đồng thời khai báo một compact constructor và một canonical constructor đầy đủ khác có cùng chữ ký.

## 3. Thời điểm Java tự gán component field

Có thể hình dung chuỗi sự kiện khi gọi `new User("  Lan  ", 20)`:

~~~text
Bên gọi chuẩn bị, đánh giá các đối số new User(...)
    ↓
Đối tượng record được cấp phát; constructor bắt đầu
    ↓
Các tham số ngầm định nhận đầu vào:
    name = "  Lan  "
    age  = 20
    ↓
Chạy body của compact constructor:
    name = name.strip()  → "Lan"
    kiểm tra name, age
    ↓
Nếu body hoàn tất bình thường:
    Java tự gán this.name = name  → "Lan"
    Java tự gán this.age  = age   → 20
    (đúng thứ tự components trong record header)
    ↓
Constructor hoàn tất; new trả về User
    ↓
Bên gọi đọc user.name() = "Lan", user.age() = 20
~~~

**Quy tắc quan trọng về thời điểm:**

- **Trước body:** các tham số có giá trị từ đối số của lời gọi constructor.
- **Trong body:** code chạy trên tham số; các component field **chưa được tự gán** bằng các giá trị tham số sau chuẩn hóa. Không viết logic phụ thuộc vào việc accessor/`this.field` đã có trạng thái cuối.
- **Sau body nếu hoàn tất bình thường:** Java gán các trường `final` từ **giá trị hiện tại của tham số**, theo thứ tự components trong record header.
- **Nếu body ném ngoại lệ:** bước gán ngầm ở cuối không chạy, constructor không hoàn tất và lệnh `new` không trả về đối tượng hợp lệ cho bên gọi. Những tác dụng phụ đã thực hiện trước ngoại lệ (log, thao tác ngoại vi) vẫn có thể đã xảy ra.

Lưu ý: “Gán sau body” là **ngữ nghĩa khởi tạo của compact constructor**, không có nghĩa mỗi lần đọc một accessor sau đó sẽ tự gán lại trường. Các trường component có tính `final`; trạng thái được thiết lập trong lúc khởi tạo đối tượng.

### Vì sao thứ tự gán quan trọng?

Trình biên dịch thực hiện phép gán các trường **theo thứ tự khai báo component**. Ví dụ:

~~~java
record Pair(int left, int right) {
    Pair {
        if (left > right) {
            int originalLeft = left;
            left = right;
            right = originalLeft;
        }
    }
}
~~~

Nếu gọi `new Pair(9, 2)`, sau body tham số `left = 2` và `right = 9`. Hai trường được khởi tạo lần lượt với `2` rồi `9`. Kết quả `new Pair(9, 2).left()` là `2` và `right()` là `9`.

Không cần tự gán từng trường; việc gán lại tham số là thao tác phù hợp ở compact constructor. Khi thay đổi **nhiều tham số liên quan**, nên dùng biến tạm như ví dụ để không làm mất giá trị ban đầu giữa các lần gán.

## 4. Ví dụ đầy đủ: kiểm tra, chuẩn hóa và sao chép phòng vệ

Tạo file **`CompactRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CompactRecordDemo {
    record Profile(String name, int level, List<String> labels) {
        Profile {
            System.out.println("constructor: entered");

            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(labels, "labels");

            name = name.strip();
            if (name.isBlank()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (level < 0) {
                throw new IllegalArgumentException("level is negative");
            }

            labels = List.copyOf(labels);
            System.out.println(
                    "constructor: normalized " + name + ";"
                    + level + ";" + labels
            );
        }
    }

    public static void main(String[] args) {
        List<String> inputLabels =
                new ArrayList<>(List.of("java", "record"));

        System.out.println("before new");
        Profile profile = new Profile("  An  ", 3, inputLabels);

        System.out.println(
                "after new: " + profile.name() + ";"
                + profile.level() + ";" + profile.labels()
        );

        inputLabels.add("external");
        System.out.println(
                "after source change: " + profile.labels()
        );

        try {
            new Profile("   ", 3, List.of("java"));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc cao hơn:

~~~bash
javac --release 17 CompactRecordDemo.java
java CompactRecordDemo
~~~

**Standard output chính xác:**

~~~text
before new
constructor: entered
constructor: normalized An;3;[java, record]
after new: An;3;[java, record]
after source change: [java, record]
constructor: entered
invalid: name is blank
~~~

Giải thích theo thời điểm:

1. `before new` được in trước khi chạy constructor.
2. Trong `Profile { ... }`, log `constructor: entered` chạy **trước** chuẩn hóa và trước các phép gán component field ngầm.
3. Body nhận `name = "  An  "` rồi đổi thành `"An"`; kiểm tra `level`; đổi tham số `labels` thành danh sách không sửa được tạo qua `List.copyOf`. Log `constructor: normalized ...` vẫn nằm **trong body**, dùng các **tham số đã chuẩn hóa**.
4. Khi body kết thúc bình thường, Java tự gán lần lượt các trường `name`, `level`, `labels` từ ba tham số vừa xử lý. Sau khi `new` thành công, các accessor phản ánh `An;3;[java, record]`.
5. Thêm `"external"` vào danh sách `inputLabels` ban đầu **không thay đổi** nội dung `profile.labels()` vì `List.copyOf` tạo một ảnh chụp không sửa được của các phần tử tại thời điểm sao chép (trong ví dụ nguồn là `ArrayList` có thể thay đổi).
6. Lần gọi `new Profile("   ", 3, ...)` tiếp theo in `constructor: entered`, rồi ném `IllegalArgumentException` khi phát hiện tên rỗng sau `strip()`. Nó **không** in dòng `constructor: normalized ...` và không trả về đối tượng `Profile` đã khởi tạo thành công.

### Tại sao phải sao chép `labels`?

Trường record có modifier `final` chỉ giữ **tham chiếu không thể gán lại** sau khi constructor hoàn tất. Điều đó **không tự làm bất biến đối tượng được tham chiếu**. Nếu lưu nguyên một `ArrayList` mutable, bên gọi vẫn có thể thêm/xóa phần tử và khiến nội dung nhìn qua accessor thay đổi.

`List.copyOf(labels)` tạo danh sách không sửa được, sao chép các tham chiếu phần tử tại thời điểm gọi; nó từ chối danh sách hoặc phần tử `null`. Với phần tử là `String` (bất biến), việc sao chép như trên đủ cho ví dụ. Với phần tử là đối tượng mutable, đây **không phải deep copy**: vẫn cần đánh giá cách sao chép và bảo vệ từng phần tử nếu yêu cầu bất biến sâu.

## 5. Compact constructor khác canonical constructor đầy đủ thế nào?

Cùng mục tiêu chuẩn hóa mã nhận dạng, có thể chọn **một trong hai cách khai báo** sau. Chúng là hai phiên bản thay thế, **không đặt cả hai trong cùng record**.

**Cách 1 — Compact constructor:**

~~~java
import java.util.Locale;
import java.util.Objects;

record Code(String value) {
    Code {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
    }
}
~~~

**Cách 2 — Canonical constructor đầy đủ:**

~~~java
import java.util.Locale;
import java.util.Objects;

record Code(String value) {
    Code(String value) {
        this.value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
    }
}
~~~

Mỗi code block trên là **một ví dụ độc lập**; chỉ dùng một phiên bản trong một compilation unit. Cả hai cách đều lưu giá trị sau `strip().toUpperCase(Locale.ROOT)`.

| Tiêu chí | Compact constructor | Canonical constructor đầy đủ |
|---|---|---|
| Danh sách tham số trong phần khai báo | Không viết lại; ngầm theo record header | Viết rõ các tham số cùng kiểu, tên và thứ tự tương ứng |
| Xử lý trước khi lưu | Kiểm tra và chuẩn hóa tham số như `value = ...` | Kiểm tra và quyết định biểu thức gán vào từng trường |
| Gán component field | Java **tự gán ở cuối body** | Lập trình viên **phải gán đầy đủ** các component field theo quy tắc definite assignment |
| `this.value = ...` | **Bị cấm trong body** | Là cách gán trực tiếp thích hợp |
| Mức độ diễn đạt | Ngắn và rõ khi chỉ cần validate/normalize/copy | Hữu ích khi cần chủ động điều khiển phép gán và khai báo tham số tường minh |

Ở canonical constructor đầy đủ, nếu bỏ phép gán một component field, chương trình sẽ không qua kiểm tra biên dịch do trường `final` chưa được khởi tạo đầy đủ. Ở compact constructor, trình biên dịch đảm nhận phần đó.

**Lưu ý về visibility:** Nếu khai báo `public record PublicCode(...)`, canonical/compact constructor khai báo tường minh phải có mức truy cập phù hợp, thường là `public PublicCode { ... }`. Ví dụ `Code` ở trên là record package-private nên dùng `Code { ... }` là hợp lệ.

## 6. Các mẫu validate và normalize nên áp dụng

### 6.1. Kiểm tra `null` trước khi gọi phương thức

~~~java
record Person(String name) {
    Person {
        if (name == null) {
            throw new IllegalArgumentException("name is required");
        }
        name = name.strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is blank");
        }
    }
}
~~~

Đây là record độc lập có thể biên dịch. Nếu gọi `name.strip()` trước khi kiểm tra `null`, lỗi có thể là `NullPointerException` thay vì thông báo nghiệp vụ đã thiết kế. Hãy xác định loại ngoại lệ mong muốn và kiểm tra theo thứ tự nhất quán.

### 6.2. Chuẩn hóa bằng cách gán lại tham số

~~~java
record Key(String value) {
    Key {
        value = value.strip();
    }
}
~~~

Trong ví dụ này, `new Key("  AB  ").value()` trả `"AB"`. Ngược lại, chỉ viết `value.strip();` mà **không gán lại** sẽ làm mất kết quả từ `strip()` vì `String` là bất biến. Khi body kết thúc, Java vẫn tự lưu **tham số chưa đổi**.

### 6.3. Validate quan hệ giữa các components

~~~java
record Interval(int start, int end) {
    Interval {
        if (start > end) {
            throw new IllegalArgumentException(
                    "start must not exceed end"
            );
        }
    }
}
~~~

Tham số `start` và `end` đều sẵn có trong body, nên bạn có thể kiểm tra ràng buộc chéo **trước khi lưu**. Với `Interval`, constructor bảo đảm mọi instance được tạo thành công đều có `start() <= end()`.

Nếu yêu cầu nghiệp vụ là **tự hoán đổi** thay vì từ chối, có thể chuẩn hóa bằng biến tạm như ví dụ `Pair`. Hai chính sách có hành vi khác nhau, nên hãy chọn chính sách từ yêu cầu thực tế thay vì âm thầm thay đổi dữ liệu.

### 6.4. Sao chép dữ liệu mutable

~~~java
import java.util.List;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

Sau constructor, accessor `values()` trả một danh sách không sửa được. Tuy nhiên:

- `List.copyOf` có thể ném `NullPointerException` nếu danh sách hoặc phần tử là `null`.
- Cơ chế chỉ bảo vệ **cấu trúc danh sách và việc thay đổi danh sách qua tham chiếu đã lưu**; không tự sao chép sâu từng phần tử.
- Nếu cần giữ nguyên danh sách có thứ tự/điều kiện phần tử khác, hãy xây dựng chính sách validate/copy riêng.

Đây là vấn đề **thiết kế bất biến của dữ liệu**, không phải yêu cầu rằng mọi component của record đều phải là kiểu bất biến.

## 7. Các lỗi thường gặp và thông điệp gốc

### Lỗi A: Gán trực tiếp trường `this.name` trong compact constructor

~~~java
// CỐ Ý SAI: không biên dịch.
record User(String name) {
    User {
        this.name = name.strip();
    }
}
~~~

**Vì sao sai?** Theo quy tắc record, compact constructor không được chứa phép gán đến component field. Hãy viết `name = name.strip();`; Java sẽ tự thực hiện phép gán `this.name = name` **sau khi body hoàn tất bình thường**.

### Lỗi B: Tưởng tham số đã được gán vào field ngay khi vào body

~~~java
// Đoạn minh họa ý tưởng không nên dựa vào.
record Account(String id) {
    Account {
        // Không lấy trạng thái cuối của id từ this.id ở đây.
        id = id.strip();
    }
}
~~~

Trong body của compact constructor, hãy xử lý **tham số `id`**. Không gọi callback, đăng ký listener hoặc đưa `this` ra ngoài trong khi đối tượng chưa khởi tạo xong. Nếu một phương thức khác truy cập object quá sớm, nó có thể quan sát trạng thái chưa hoàn chỉnh, trái với bất biến mong muốn của record.

### Lỗi C: Gọi một phương thức nhưng không lưu kết quả chuẩn hóa

~~~java
record Item(String name) {
    Item {
        name.strip(); // Kết quả bị bỏ đi.
    }
}
~~~

Nếu dùng `new Item("  book  ")`, tham số vẫn là `"  book  "` và giá trị được lưu không được chuẩn hóa. Sửa thành `name = name.strip();`.

### Lỗi D: Viết `return;` để kết thúc compact constructor

~~~java
// CỐ Ý SAI: không biên dịch.
record Item(int count) {
    Item {
        if (count == 0) {
            return;
        }
    }
}
~~~

Body của compact constructor không được chứa `return`. Nếu dữ liệu sai, dùng `throw`; nếu dữ liệu hợp lệ, để body chạy hết và Java tự gán components.

### Lỗi E: Mong record tự động bất biến sâu

~~~java
import java.util.List;

record Box(List<String> items) {}
~~~

Nếu bên gọi truyền vào một `ArrayList` rồi thay đổi danh sách đó, giá trị nhìn qua `Box.items()` có thể thay đổi, dù `items` là trường `final`. Thêm compact constructor với `items = List.copyOf(items);` nếu yêu cầu bản chụp danh sách không sửa được.

### Lỗi F: Kiểm tra dữ liệu sau khi đã đổi giá trị mà không xét yêu cầu

Ví dụ `name = name.strip();` rồi mới từ chối tên rỗng là chính sách có chủ đích. Nhưng nếu nghiệp vụ cần phân biệt tên có khoảng trắng đầu/cuối, việc chuẩn hóa trước kiểm tra có thể làm mất dấu hiệu đầu vào sai. Khi tạo constructor, hãy chọn **quy tắc validation và normalization rõ ràng**, rồi kiểm thử với các biên: `null`, rỗng, toàn khoảng trắng, ký tự Unicode, giá trị âm, danh sách chứa `null`.

### Lỗi G: Hai canonical constructors cho cùng record

~~~java
// CỐ Ý SAI: trùng canonical constructor.
record User(String name) {
    User {
        name = name.strip();
    }

    User(String name) {
        this.name = name;
    }
}
~~~

Compact constructor đã là canonical constructor. Nếu cần constructor nhận ít tham số hơn, định nghĩa constructor **không phải canonical** và ủy quyền cho canonical bằng `this(...)` làm thao tác khởi tạo đầu tiên, theo quy tắc phiên bản Java đang dùng. Không khai báo hai canonical constructors cho cùng chữ ký.

## 8. Cách tự kiểm tra thời điểm gán bằng một sơ đồ

Với compact constructor:

~~~text
Tham số ngầm định của record header được nhận
             ↓
    Kiểm tra và chuẩn hóa
             ↓
          ┌───────────────┐
          │ Body kết thúc?│
          └───────┬───────┘
       bình thường│       ngoại lệ
                 ↓            ↘
       Tự gán fields final     Không gán tại cuối body
       (thứ tự record header)  Constructor thất bại
                 ↓
       new hoàn tất thành công
                 ↓
       Accessor đọc dữ liệu đã lưu
~~~

Khi review, hãy tách **thời điểm xử lý tham số** và **thời điểm ghi vào trường**. Trong code compact constructor, dòng cuối cùng do bạn viết **chưa phải** dòng gán component field; còn một bước khởi tạo ngầm sau body, miễn là body hoàn tất bình thường.

## 9. Checklist thực tế khi tạo compact constructor

1. **Xác định bất biến cần bảo vệ:** component nào không được `null`, giá trị nào bị giới hạn, ràng buộc giữa nhiều components là gì?
2. **Viết điều kiện validate trước khi khởi tạo xong:** chọn ngoại lệ và thông báo phù hợp; không dựa vào dữ liệu field chưa tự gán.
3. **Chuẩn hóa tham số có chủ đích:** nếu gọi phương thức tạo giá trị mới như `strip()`, phải gán lại biến tham số khi muốn lưu kết quả đó.
4. **Sao chép phòng vệ nếu cần:** với collection mutable hoặc kiểu đối tượng tham chiếu khác, đánh giá shallow/deep immutability.
5. **Không tự gán `this.component`:** để trình biên dịch tự gán ở cuối body, tránh code trùng lặp và lỗi biên dịch.
6. **Giữ bất biến trong hành vi accessor:** tránh cung cấp một tham chiếu tới đối tượng mutable mà bên ngoài có thể đổi trạng thái trái với hợp đồng.
7. **Thử cả đường thành công và thất bại:** với đường thành công, kiểm tra accessor nhận giá trị đã chuẩn hóa; với đường thất bại, xác nhận không có instance được trả về và ngoại lệ đúng mong đợi.
8. **Tránh làm lộ `this` khi đang khởi tạo:** không gửi instance ra callback/luồng khác trước khi constructor hoàn tất.

Với một record công khai trong thư viện, cũng cần cân nhắc rằng tên, kiểu và thứ tự components là phần quan trọng của API, vì chúng ảnh hưởng chữ ký canonical constructor và accessor.

## 10. Tự kiểm tra hiểu bài

**Câu 1.** Chạy `new Label("  Java  ")` với đoạn dưới đây thì accessor trả gì?

~~~java
record Label(String value) {
    Label {
        value = value.strip();
    }
}
~~~

**Đáp án:** `"Java"`. Tham số `value` bị gán lại trong body; sau đó Java tự gán trường `this.value` từ tham số đã đổi.

**Câu 2.** Khi nào Java tự gán các component fields trong compact constructor?

**Đáp án:** **Sau khi body hoàn tất bình thường**, theo thứ tự components được khai báo trong record header. Nếu body ném ngoại lệ, giai đoạn gán ngầm ở cuối không diễn ra.

**Câu 3.** Có thể viết `this.value = "ok";` trong compact constructor để bỏ qua tham số không?

**Đáp án:** Không. Đây là phép gán trực tiếp component field bị cấm; hãy thay đổi tham số `value` hoặc dùng canonical constructor viết đầy đủ khi có lý do phù hợp.

**Câu 4.** `final List<String>` có đảm bảo nội dung list bất biến không?

**Đáp án:** Không. `final` ngăn đổi tham chiếu trường, không ngăn đối tượng được tham chiếu bị thay đổi. `List.copyOf` phù hợp khi muốn một danh sách không sửa được, nhưng không tạo bản sao sâu của các phần tử mutable.

**Câu 5.** Nếu body compact constructor ghi log rồi `throw`, log có biến mất không?

**Đáp án:** Không. Tác dụng phụ đã xảy ra vẫn tồn tại; còn constructor thất bại nên bên gọi không nhận được instance được khởi tạo thành công.

**Câu 6.** Trong compact constructor, viết `name.strip();` khác `name = name.strip();` ở đâu?

**Đáp án:** Biểu thức đầu bỏ kết quả mới nên tham số không đổi; biểu thức sau thay giá trị tham số, và giá trị mới trở thành dữ liệu được lưu khi Java tự gán field ở cuối.

## Tài liệu tham khảo

- [Java Language Specification 17 — Record Classes, `8.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): định nghĩa record components, canonical/compact constructor và quy tắc khởi tạo trường.
- [dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): ví dụ validate/normalize và khác nhau giữa constructor compact và canonical đầy đủ.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): tính năng record được chuẩn hóa từ Java 16.

**Ghi nhớ:** `name` trong compact constructor là **tham số có thể chuẩn hóa**, còn `this.name` là **component field final được Java tự gán sau body**. Hiểu đúng mốc thời gian này giúp bạn xây dựng record có dữ liệu hợp lệ ngay sau khi tạo, tránh gán nhầm trường và xử lý dữ liệu tham chiếu một cách an toàn.