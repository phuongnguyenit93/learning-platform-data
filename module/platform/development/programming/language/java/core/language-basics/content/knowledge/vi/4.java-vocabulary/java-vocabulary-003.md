# Từ khóa dành riêng và từ khóa theo ngữ cảnh trong Java 17

Trong Java, không phải từ nào trông giống tiếng Anh cũng được dùng làm tên biến hoặc tên lớp. Một số từ có ý nghĩa **cố định** với ngôn ngữ; một số chỉ có vai trò đặc biệt trong **cấu trúc cú pháp cụ thể**.

Ví dụ, `class` luôn là từ khóa dành riêng, nhưng `module` có thể là tên biến bình thường ở ngoài cú pháp module. Phân biệt đúng hai nhóm này giúp bạn đặt tên hợp lệ, đọc code Java 17 và hiểu thông báo lỗi của `javac`.

**Mục tiêu:** nhận diện từ khóa dành riêng, từ khóa theo ngữ cảnh, literal và identifier thường; viết/chạy một ví dụ kết hợp `var`, `record`, `yield` và `sealed`; sửa các lỗi đặt tên.

## 1. Bốn loại dễ nhầm

| Loại | Ví dụ Java 17 | Quy tắc quan trọng |
| --- | --- | --- |
| **Từ khóa dành riêng** (*reserved keyword*) | `class`, `int`, `public`, `return`, `if`, `switch` | Không được dùng làm identifier thông thường, bất kể vị trí |
| **Từ khóa theo ngữ cảnh** (*contextual/restricted keyword*) | `var`, `record`, `yield`, `sealed`, `permits`, `non-sealed`, `module`, `requires` | Chỉ có ý nghĩa đặc biệt trong những ngữ cảnh Java quy định; mỗi từ có hạn chế riêng |
| **Literal** | `true`, `false`, `null` | **Không phải từ khóa**, nhưng cũng không được dùng làm tên biến/lớp |
| **Identifier thường** | `score`, `main`, `String`, `System` | Là tên do lập trình viên khai báo hoặc tên API, chịu quy tắc đặt tên và phạm vi |

`String` là một **lớp**, không phải từ khóa kiểu primitive như `int`. `main` là tên phương thức theo quy ước điểm vào, cũng không phải từ khóa. Java phân biệt chữ hoa/thường: `Class` không phải token `class`, nhưng chọn tên `Class` dễ gây nhầm nên thường không đáng làm.

## 2. Từ khóa dành riêng: bị cấm làm tên ở mọi ngữ cảnh identifier

Các nhóm thông dụng:

| Nhóm | Từ khóa | Công dụng ví dụ |
| --- | --- | --- |
| Khai báo và truy cập | `class`, `interface`, `enum`, `public`, `private`, `protected` | Định nghĩa kiểu, chỉ định phạm vi truy cập |
| Điều khiển luồng | `if`, `else`, `for`, `while`, `switch`, `case`, `break`, `continue`, `return` | Chọn nhánh, lặp, kết thúc |
| Kiểu primitive | `boolean`, `byte`, `short`, `int`, `long`, `char`, `float`, `double` | Khai báo dữ liệu primitive |
| Đối tượng và kế thừa | `new`, `this`, `super`, `extends`, `implements`, `instanceof` | Tạo đối tượng, truy cập, quan hệ kiểu |
| Ngoại lệ | `try`, `catch`, `finally`, `throw`, `throws` | Xử lý và khai báo ngoại lệ |
| Thành viên/hành vi khác | `static`, `final`, `abstract`, `void`, `synchronized`, `volatile`, `transient`, `native`, `strictfp` | Định nghĩa cách dùng thành viên và kiểu |
| Tổ chức mã | `package`, `import`, `default`, `do`, `assert` | Package, nhập kiểu, cú pháp tương ứng |

Đây là **nhóm ví dụ minh họa**, không phải danh sách được sắp theo thứ tự xuất hiện trong đặc tả Java. Hai từ `const` và `goto` cũng **được dành riêng** dù không được Java dùng làm câu lệnh. Ký tự gạch dưới đơn lẻ `_` **không thể** làm identifier kể từ Java 9; nhưng `_value` vẫn là một identifier hợp lệ trong Java 17.

Các dòng sau **cố ý không biên dịch**:

~~~java
int class = 3;       // Sai: class là từ khóa dành riêng.
int return = 5;      // Sai: return là từ khóa dành riêng.
int _ = 1;           // Sai trên Java 17: _ bị dành riêng.
int true = 2;        // Sai: true là literal, không phải identifier.
~~~

Đổi tên để biểu thị nghĩa của giá trị:

~~~java
int classSize = 3;
int returnCount = 5;
int _value = 1;
boolean enabled = true;
~~~

**Lưu ý:** `true`, `false` và `null` là literal (`boolean`/null literal), *không nằm trong nhóm keyword*, nhưng việc dùng chúng như identifier vẫn sai. “Không phải keyword” không đồng nghĩa “dùng làm tên được”.

## 3. Từ khóa theo ngữ cảnh: vị trí cú pháp quyết định ý nghĩa

Java 17 có những từ chỉ được coi là thành phần cú pháp đặc biệt ở ngữ cảnh phù hợp:

| Từ | Khi mang nghĩa đặc biệt | Ngoài ngữ cảnh đó |
| --- | --- | --- |
| `var` | Suy luận kiểu của một biến cục bộ từ biểu thức khởi tạo | Có thể dùng `var` làm **tên biến**, nhưng không dùng làm tên kiểu do đây là *restricted type name* |
| `record` | Khai báo record, ví dụ `record Point(int x, int y) {}` | Có thể dùng `record` làm tên biến bình thường |
| `yield` | Trả một giá trị từ khối trong `switch` expression | Có thể là tên biến; một số cách dùng làm tên lời gọi phương thức không đủ điều kiện bị hạn chế |
| `sealed`, `permits` | Khai báo kiểu sealed và các kiểu được phép kế thừa/triển khai | Không tự động bị cấm làm tên biến ở mọi nơi |
| `non-sealed` | Cho phép một subtype trực tiếp của sealed type mở lại khả năng kế thừa | Đây là dạng có dấu nối đặc biệt; **không** phải một identifier thông thường |
| `module`, `open`, `requires`, `exports`, `opens`, `to`, `uses`, `provides`, `with`, `transitive` | Cú pháp khai báo module trong `module-info.java` | Nhiều từ trong số này vẫn có thể dùng làm identifier ở mã Java thường |

Một số thuật ngữ đặc tả Java phân biệt *contextual keywords*, *restricted keywords* và *restricted identifiers/type names*. Khi học, điểm cần nắm không phải tất cả cùng một quy tắc cấm, mà là **từng từ có vị trí được phép và bị hạn chế riêng**.

### Ví dụ 1: `var` không làm Java trở thành ngôn ngữ kiểu động

~~~java
var total = 12;       // Trình biên dịch suy luận total có kiểu int.
total = 15;           // Hợp lệ.
// total = "muoi lam"; // Sai: String không gán cho int.

int var = 7;          // Hợp lệ trong Java 17: var là tên biến.
~~~

`var` dùng để **suy luận kiểu của biến cục bộ**, không phải kiểu “nhận mọi giá trị”. Những đoạn sau không hợp lệ:

~~~java
// var x = null;     // Không suy luận được kiểu từ null.
// var x;            // Không có initializer để suy luận kiểu.
// class var {}      // Không hợp lệ: var là restricted type name.
~~~

Đặt tên biến `var` tuy hợp lệ nhưng dễ làm người đọc hiểu nhầm; nên chọn tên theo ý nghĩa dữ liệu.

### Ví dụ 2: `record` và `yield` chỉ đặc biệt khi dùng đúng cú pháp

~~~java
record Point(int x, int y) {} // Java 17: khai báo kiểu record.

int record = 5;                // Hợp lệ: tên biến thông thường.
~~~

Một `switch` expression có thể dùng `yield` trong khối để cung cấp giá trị:

~~~java
int score = 8;
String result = switch (score) {
    case 0 -> "Chua hoc";
    default -> {
        yield score > 0 ? "Da hoc" : "Khong hop le";
    }
};
~~~

Ở đây, `switch`, `case` và `default` là từ khóa dành riêng; `yield` mang nghĩa đặc biệt trong khối của `switch` expression. Đừng hiểu `yield` như `return` cho cả phương thức: nó trả giá trị cho **switch expression**, không tự kết thúc phương thức bao ngoài.

### Ví dụ 3: `sealed` kiểm soát kiểu con

~~~java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}

record Failure(int code) implements Result {}
~~~

`Result` là sealed interface; chỉ các subtype được cho phép mới trực tiếp triển khai nó. Hai record trên ngầm là `final`, nên thỏa yêu cầu đối với các kiểu trực tiếp được phép kế thừa/triển khai. Khi cần giữ một nhánh cho phép kế thừa tiếp, Java còn có modifier `non-sealed` cho subtype trực tiếp thích hợp.

Không nên cố dùng `non-sealed` như một tên biến có dấu `-`: dấu nối ở đây thuộc cú pháp đặc biệt, không phải ký tự hợp lệ tùy ý trong identifier.

## 4. Chương trình Java 17+ chạy được: so sánh ngay trong mã

Tạo tệp **`KeywordContextDemo.java`**:

~~~java
public class KeywordContextDemo {
    record Session(String title, int minutes) {}

    sealed interface Outcome permits Good, Bad {}

    record Good(String message) implements Outcome {}

    record Bad(int code) implements Outcome {}

    static String label(int minutes) {
        return switch (minutes) {
            case 0 -> "chua hoc";
            default -> {
                yield minutes > 0 ? "da hoc" : "gia tri am";
            }
        };
    }

    public static void main(String[] args) {
        int module = 2;  // module là tên biến hợp lệ ở đây.
        int record = 3;  // record là tên biến hợp lệ ở đây.

        var session = new Session("Java", 45);
        Outcome outcome = new Good("ok");

        System.out.println("module=" + module);
        System.out.println("record=" + record);
        System.out.println(
                "session=" + session.title() + ":" + session.minutes());
        System.out.println("label(0)=" + label(0));
        System.out.println("label(3)=" + label(record));
        System.out.println(
                "outcome=" + outcome.getClass().getSimpleName());
    }
}
~~~

**Giải thích:** `record Session` khai báo một record; `int record = 3` dùng cùng chuỗi ký tự làm tên biến ở ngữ cảnh khác. `var session` suy luận kiểu `Session`. `yield` trả giá trị cho `switch` expression. `sealed` và `permits` đặt ranh giới các subtype của `Outcome`. `module` là tên biến, không phải khai báo module.

### Biên dịch và chạy (Windows PowerShell hoặc Linux/Bash)

Lưu mã UTF-8, mở terminal trong thư mục chứa tệp, xác minh JDK 17+:

~~~bash
java -version
javac -version
~~~

Sau đó dùng cùng lệnh ở cả hai môi trường:

~~~bash
javac --release 17 -encoding UTF-8 KeywordContextDemo.java
java KeywordContextDemo
~~~

**Kết quả dự kiến:**

~~~text
module=2
record=3
session=Java:45
label(0)=chua hoc
label(3)=da hoc
outcome=Good
~~~

`--release 17` yêu cầu compiler hỗ trợ cú pháp và API nền tảng Java 17. Nếu dùng đúng JDK 17, chỉ cần `javac -encoding UTF-8 KeywordContextDemo.java` cũng đủ cho ví dụ này.

Một lợi ích của chương trình là **không cần tự tạo package, module hoặc thư viện ngoài** để thấy sự khác biệt giữa các ngữ cảnh.

## 5. Vì sao tên trong `module-info.java` trông như keyword?

Hệ thống module của Java có cú pháp dành riêng cho tệp khai báo module. Ví dụ **minh họa cú pháp**, không phải một dự án hoàn chỉnh:

~~~java
module learning.demo {
    requires java.logging;
}
~~~

Trong nội dung `module-info.java`, từ `module` và `requires` là thành phần cú pháp module declaration. Nhưng ở chương trình thông thường, `int module = 2;` vẫn hợp lệ. Đừng đặt đoạn minh họa module này vào trong lớp `KeywordContextDemo`: đó là **vị trí cú pháp khác** và cần dự án module được bố trí tương ứng.

Ví dụ này chỉ nhằm nhận biết *context*. Việc tổ chức module path, đóng gói module và `requires` nằm ngoài mục tiêu bài học về từ vựng Java.

## 6. Lỗi biên dịch thường gặp và cách sửa

| Đoạn mã / tình huống | Loại lỗi hoặc nhầm lẫn | Cách xử lý |
| --- | --- | --- |
| `int class = 1;` | `class` là reserved keyword | Đổi thành `classCount` |
| `int _ = 1;` | `_` bị dành riêng trong Java 17 | Đổi thành `_count` hoặc `count` |
| `int true = 1;` | `true` là literal, không là identifier | Dùng `boolean enabled = true;` |
| `class record {}` | `record` bị hạn chế khi làm tên kiểu | Đổi tên lớp, ví dụ `RecordExample` |
| `var value = null;` | Không thể suy luận kiểu | Dùng kiểu tường minh, nếu null là giá trị hợp lệ |
| `var number;` | Không có initializer | Khởi tạo khi khai báo hoặc chọn kiểu tường minh |
| `yield 1;` ngoài ngữ cảnh cho phép | `yield` không phải statement trả giá trị chung | Dùng `return` trong phương thức hoặc `yield` trong switch expression phù hợp |
| `non-sealed` ở lớp không liên quan sealed hierarchy | Modifier không hợp lệ ở vị trí đó | Chỉ dùng trên subtype trực tiếp của sealed type khi đáp ứng quy tắc |

**Phân biệt:** từ khóa sai vị trí có thể dẫn đến **lỗi cú pháp**; tên kiểu bị hạn chế có thể dẫn đến lỗi **khai báo**; `var` không thể suy luận kiểu thường dẫn đến lỗi **kiểu**. Thông báo `javac` cụ thể thay đổi theo phiên bản, nên tập trung vào cấu trúc mã và ngữ cảnh.

## 7. Bài tập thực hành

**Bài 1 — Phân loại:** Trong `class`, `record`, `main`, `true`, `var`, `int`, `String`, `null`, hãy chia thành keyword dành riêng, contextual/restricted keyword, literal và identifier/tên API.

*Đáp án:* Dành riêng: `class`, `int`. Theo ngữ cảnh/hạn chế: `record`, `var`. Literal: `true`, `null`. Tên thường/API: `main`, `String`.

**Bài 2 — Dự đoán:** Vì sao `int module = 2;` chạy được nhưng `int class = 2;` không biên dịch?

*Đáp án:* `module` có nghĩa đặc biệt trong ngữ cảnh khai báo module, còn `class` luôn là reserved keyword.

**Bài 3 — Tự thử lỗi:** Trong chương trình `KeywordContextDemo.java`, thêm thử `int return = 1;` vào `main`, biên dịch, đọc thông báo rồi bỏ dòng sai. Có thể dùng `returnCount` thay thế không?

*Đáp án:* Có, `returnCount` là identifier hợp lệ; `return` thì không.

**Bài 4 — Thay đổi switch:** Gọi thêm `label(-1)` rồi dự đoán kết quả. Giải thích vì sao `yield` trong nhánh `default` có thể đưa kết quả về biến/lời gọi chứa `switch` expression.

*Đáp án:* Trả chuỗi `gia tri am`. `yield` cung cấp giá trị của `switch` expression.

**Bài 5 — Không nhầm từ khóa với tên API:** Tại sao `String`, `System`, `println`, `main` không phải keyword, dù xuất hiện nhiều trong chương trình Java?

*Đáp án:* Chúng là tên kiểu/phương thức theo thư viện hoặc quy ước, chứ không phải token cú pháp dành riêng của ngôn ngữ. Cách sử dụng chúng phải đúng khai báo, phạm vi và kiểu.

## Checklist ghi nhớ

- [ ] Nhận diện reserved keyword như `class`, `if`, `return` và `int`.
- [ ] Không dùng `true`, `false`, `null` hoặc `_` làm identifier.
- [ ] Giải thích được vì sao `var` chỉ suy luận kiểu ở những vị trí cho phép nhưng biến vẫn có kiểu tĩnh.
- [ ] Phân biệt `record` dùng khai báo kiểu với `record` làm tên biến.
- [ ] Biết `yield` có ý nghĩa đặc biệt trong `switch` expression.
- [ ] Nhận diện `sealed`, `permits`, `non-sealed` mà không nhầm chúng thành tên tự do.
- [ ] Biết `module`, `requires` và các từ liên quan có ngữ cảnh khai báo module.
- [ ] Biên dịch, chạy được ví dụ bằng `javac --release 17` và `java`.

**Ghi nhớ:** Từ khóa **dành riêng** bị khóa ở mọi vị trí identifier; từ khóa **theo ngữ cảnh** chỉ mang ý nghĩa cú pháp đặc biệt ở cấu trúc thích hợp và có những giới hạn riêng. `true`/`false`/`null` là literal, không phải keyword, nhưng cũng không phải tên hợp lệ. Khi không chắc, hãy nhìn **ngữ cảnh cú pháp** và thử biên dịch một ví dụ Java 17 tối thiểu.
